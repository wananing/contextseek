"""On-disk file backend for seekvfs.

Each VFS path maps to a single file under ``root_dir``. Scheme-agnostic:
the scheme that arrives on every input path is preserved on every output
path. Contrast with :class:`seekvfs_recipes.minimal.FileBackend`, which
hardcodes ``seekvfs://``.
"""

from __future__ import annotations

import fnmatch
import threading
from datetime import UTC
from datetime import datetime
from pathlib import Path

from seekvfs import BackendProtocol
from seekvfs import SCHEME
from seekvfs.exceptions import NotFoundError
from seekvfs.models import FileData
from seekvfs.models import FileInfo
from seekvfs.models import GrepMatch
from seekvfs.models import SearchHit
from seekvfs.models import SearchResult


def _to_bytes(content: bytes | str) -> bytes:
    return content if isinstance(content, bytes) else content.encode("utf-8")


def _split_scheme(path: str) -> tuple[str, str]:
    """Split ``scheme://rel`` → ``("scheme://", "rel")``. Bare path → ``("", path)``."""
    i = path.find("://")
    if i == -1:
        return "", path
    return path[: i + 3], path[i + 3:]


class FileBackend(BackendProtocol):
    """On-disk K/V backend implementing `seekvfs.BackendProtocol`.

    Args:
        root_dir: directory to hold stored files. Created on ``initialize``.
        scheme: scheme to prepend when reconstructing paths in contexts
            where none can be inferred from input (e.g. ``search`` with
            ``path_pattern=None``). Defaults to ``seekvfs://``. Pass
            ``"agentseek://"`` (or whatever you passed to ``VFS(scheme=...)``)
            to keep paths round-trippable.
    """

    def __init__(self, root_dir: str | Path, scheme: str = SCHEME) -> None:
        self._root = Path(root_dir).resolve()
        self._scheme = scheme
        self._edit_lock = threading.Lock()

    def _local(self, path: str) -> Path:
        _, rel = _split_scheme(path)
        return self._root / rel

    def _reconstruct(self, fp: Path, scheme: str) -> str:
        rel = fp.relative_to(self._root).as_posix()
        return scheme + rel

    def _scheme_of(self, *hints: str | None) -> str:
        """Pick a scheme from the first input that carries one, else default."""
        for h in hints:
            if h is None:
                continue
            s, _ = _split_scheme(h)
            if s:
                return s
        return self._scheme

    def write(self, path: str, content: bytes | str) -> None:
        fp = self._local(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_bytes(_to_bytes(content))

    def read(self, path: str, hint: str | None = None) -> FileData:
        fp = self._local(path)
        if not fp.exists():
            raise NotFoundError(path)
        return FileData(fp.read_bytes(), "utf-8")

    def read_full(self, path: str) -> FileData:
        return self.read(path)

    def read_batch(self, paths: list[str]) -> dict[str, FileData]:
        return {p: self.read(p) for p in paths}

    def search(
        self,
        query: str,
        path_pattern: str | None = None,
        limit: int = 10,
        score_threshold: float | None = None,
        *,
        query_embedding: list[float] | None = None,
    ) -> SearchResult:
        # query_embedding is accepted for protocol compatibility but is not
        # consumed: this backend only does keyword matching.
        del query_embedding
        scheme = self._scheme_of(path_pattern)
        q_low = query.lower()
        hits: list[SearchHit] = []
        searched: list[str] = []
        for fp in self._root.rglob("*"):
            if not fp.is_file():
                continue
            vfs_path = self._reconstruct(fp, scheme)
            if path_pattern is not None and not fnmatch.fnmatch(vfs_path, path_pattern):
                continue
            try:
                data = fp.read_bytes()
            except OSError:
                continue
            searched.append(vfs_path)
            text = data.decode("utf-8", errors="replace")
            score = 1.0 if q_low and q_low in text.lower() else 0.0
            if score_threshold is not None and score < score_threshold:
                continue
            if score <= 0:
                continue
            hits.append(SearchHit(path=vfs_path, snippet="", score=score))
        return SearchResult(query=query, hits=hits[:limit], searched_paths=searched)

    def ls(
        self,
        path: str,
        pattern: str | None = None,
        recursive: bool = False,
    ) -> list[FileInfo]:
        scheme_in, rel = _split_scheme(path)
        scheme = scheme_in or self._scheme
        rel_prefix = rel if rel.endswith("/") else rel + "/"
        local_dir = (self._root / rel_prefix.rstrip("/")) if rel_prefix != "/" else self._root
        out_prefix = scheme + rel_prefix

        out: list[FileInfo] = []
        if not local_dir.exists():
            return out
        candidates = local_dir.rglob("*") if recursive else local_dir.iterdir()
        for fp in candidates:
            if not fp.is_file():
                continue
            rest = fp.relative_to(local_dir).as_posix()
            if pattern is not None and not fnmatch.fnmatch(rest, pattern):
                continue
            stat = fp.stat()
            out.append(
                FileInfo(
                    path=out_prefix + rest,
                    size=stat.st_size,
                    mtime=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                    is_dir=False,
                )
            )
        out.sort(key=lambda fi: fi.path)
        return out

    def edit(self, path: str, old: str, new: str) -> int:
        fp = self._local(path)
        with self._edit_lock:
            if not fp.exists():
                raise NotFoundError(path)
            text = fp.read_bytes().decode("utf-8", errors="replace")
            count = text.count(old)
            if count == 0:
                return 0
            fp.write_bytes(text.replace(old, new).encode("utf-8"))
            return count

    def grep(
        self,
        pattern: str,
        path_pattern: str | None = None,
    ) -> list[GrepMatch]:
        scheme = self._scheme_of(path_pattern)
        out: list[GrepMatch] = []
        for fp in self._root.rglob("*"):
            if not fp.is_file():
                continue
            vfs_path = self._reconstruct(fp, scheme)
            if path_pattern is not None and not fnmatch.fnmatch(vfs_path, path_pattern):
                continue
            try:
                text = fp.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for idx, line in enumerate(text.splitlines(), start=1):
                if pattern in line:
                    out.append(GrepMatch(path=vfs_path, line_number=idx, line=line))
        return out

    def delete(self, path: str) -> None:
        fp = self._local(path)
        if not fp.exists():
            raise NotFoundError(path)
        fp.unlink()
        parent = fp.parent
        while parent != self._root:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent

    def initialize(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        pass


__all__ = ["FileBackend"]
