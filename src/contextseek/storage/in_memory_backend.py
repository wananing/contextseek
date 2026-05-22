"""In-memory seekvfs BackendProtocol implementation.

Plugs into `seekvfs.VFS` as a backend for local usage and tests. Stores
one entry per VFS path in a flat dict — scheme-agnostic, so the scheme
that VFS was built with flows through unchanged.
"""

from __future__ import annotations

import fnmatch
from datetime import UTC
from datetime import datetime

from seekvfs import BackendProtocol
from seekvfs.exceptions import NotFoundError
from seekvfs.models import FileData
from seekvfs.models import FileInfo
from seekvfs.models import GrepMatch
from seekvfs.models import SearchHit
from seekvfs.models import SearchResult


def _to_bytes(content: bytes | str) -> bytes:
    return content if isinstance(content, bytes) else content.encode("utf-8")


class InMemoryBackend(BackendProtocol):
    """Flat in-memory K/V backend implementing `seekvfs.BackendProtocol`."""

    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}
        self._mtime: dict[str, datetime] = {}

    def write(self, path: str, content: bytes | str) -> None:
        self._data[path] = _to_bytes(content)
        self._mtime[path] = datetime.now(tz=UTC)

    def read(self, path: str, hint: str | None = None) -> FileData:
        if path not in self._data:
            raise NotFoundError(path)
        return FileData(self._data[path], "utf-8")

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
        q_low = query.lower()
        hits: list[SearchHit] = []
        searched: list[str] = []
        for path, data in self._data.items():
            if path_pattern is not None and not fnmatch.fnmatch(path, path_pattern):
                continue
            searched.append(path)
            text = data.decode("utf-8", errors="replace")
            score = 1.0 if q_low and q_low in text.lower() else 0.0
            if score_threshold is not None and score < score_threshold:
                continue
            if score <= 0:
                continue
            hits.append(SearchHit(path=path, snippet="", score=score))
        return SearchResult(query=query, hits=hits[:limit], searched_paths=searched)

    def ls(
        self,
        path: str,
        pattern: str | None = None,
        recursive: bool = False,
    ) -> list[FileInfo]:
        prefix = path if path.endswith("/") else path + "/"
        out: list[FileInfo] = []
        for key, data in self._data.items():
            if not key.startswith(prefix):
                continue
            rest = key[len(prefix):]
            if not recursive and "/" in rest:
                continue
            if pattern is not None and not fnmatch.fnmatch(rest, pattern):
                continue
            out.append(
                FileInfo(
                    path=key,
                    size=len(data),
                    mtime=self._mtime.get(key, datetime.now(tz=UTC)),
                    is_dir=False,
                )
            )
        out.sort(key=lambda fi: fi.path)
        return out

    def edit(self, path: str, old: str, new: str) -> int:
        if path not in self._data:
            raise NotFoundError(path)
        text = self._data[path].decode("utf-8", errors="replace")
        count = text.count(old)
        if count == 0:
            return 0
        self._data[path] = text.replace(old, new).encode("utf-8")
        self._mtime[path] = datetime.now(tz=UTC)
        return count

    def grep(
        self,
        pattern: str,
        path_pattern: str | None = None,
    ) -> list[GrepMatch]:
        out: list[GrepMatch] = []
        for path, data in self._data.items():
            if path_pattern is not None and not fnmatch.fnmatch(path, path_pattern):
                continue
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            for idx, line in enumerate(text.splitlines(), start=1):
                if pattern in line:
                    out.append(GrepMatch(path=path, line_number=idx, line=line))
        return out

    def delete(self, path: str) -> None:
        if path not in self._data:
            raise NotFoundError(path)
        del self._data[path]
        self._mtime.pop(path, None)

    def initialize(self) -> None:
        pass

    def close(self) -> None:
        pass


__all__ = ["InMemoryBackend"]
