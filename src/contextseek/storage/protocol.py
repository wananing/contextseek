"""Protocol for seekvfs adapters."""

from __future__ import annotations

from typing import Any
from typing import Protocol
from typing import runtime_checkable


@runtime_checkable
class SeekVFSAdapter(Protocol):
    """Minimal VFS adapter protocol for semantic layer."""

    def write(self, ref: str, payload: dict[str, Any]) -> None:
        """Write an object payload to a URI."""

    def read(self, ref: str) -> dict[str, Any] | None:
        """Read payload by URI."""

    def search(
        self,
        prefix: str,
        query: str,
        *,
        k: int,
        query_embedding: list[float] | None = None,
    ) -> list[dict[str, Any]]:
        """Search payloads under namespace prefix.

        Args:
            query_embedding: Optional precomputed query vector. When set, backends
                may use ANN recall directly; when omitted, fall back to FTS-only.
                Back-compat: legacy implementations may ignore this argument.
        """

    def ls(self, prefix: str) -> list[str]:
        """List object references under prefix."""

    def delete(self, ref: str) -> bool:
        """Delete payload by URI."""


class HashIndexMixin:
    """Mixin that adds find_by_hash to adapters that maintain a hash → ref index.

    This is an optional fast-path for write-time exact-duplicate detection.
    Adapters that cannot answer hash lookups efficiently should NOT inherit
    from this mixin; callers access the method via ``getattr`` so the absence
    is handled gracefully.
    """

    def find_by_hash(self, prefix: str, hash_value: str) -> str | None:
        """Return the ref of an item under *prefix* whose ``payload['hash']`` matches.

        Returns ``None`` when no match exists or the index is unavailable.
        """
        return None


class GeoSearchMixin:
    """Mixin that adds geo_search / is_point_within_zone to adapters backed by OceanBaseGeoBackend.

    The default implementations return empty results so the retrieval pipeline
    degrades gracefully when the backend is not geo-capable.
    """

    def geo_search(
        self,
        geo_query: "Any",
        *,
        prefix: str,
        k: int,
    ) -> list[dict]:
        """Return payloads near / within the geo_query geometry.

        Returns:
            List of payload dicts with at least ``ref`` and ``score`` fields,
            in the same format as :meth:`SeekVFSAdapter.search`.
        """
        return []

    def is_point_within_zone(
        self,
        point: "Any",
        *,
        zone_type: str,
        scope: str,
    ) -> bool:
        """Return True if *point* lies inside any polygon of *zone_type* within *scope*."""
        return False


class SyncCapableMixin:
    """Mixin that marks a backend as supporting O(1) sync-table operations.

    Both ``SeekDBBackend`` and ``OceanBaseBackend`` inherit this mixin.
    Calling code detects sync capability via ``isinstance(backend, SyncCapableMixin)``
    rather than a rigid class check.

    All methods have safe default no-op implementations so that backends that
    have not yet created the sync tables remain functional.
    """

    def ensure_sync_table(self) -> None: ...

    def meta_get(self, key: str) -> str | None:
        return None

    def meta_set(self, key: str, value: str) -> None: ...

    def sync_hashes_for_scope(self, scope: str) -> set[str]:
        return set()

    def sync_hash_add(self, scope: str, hash_val: str) -> None: ...

    def sync_hashes_add_batch(self, scope: str, hashes: set[str]) -> None: ...

    def sync_files_for_scope(self, scope: str) -> dict[str, tuple[float, str]]:
        return {}

    def sync_file_record(
        self, scope: str, path: str, mtime: float, content_hash: str
    ) -> None: ...

    def visible_count_for_scope(self, scope: str) -> int:
        return 0


class VectorSearchMixin:
    """Mixin that adds vector_search to adapters backed by a vector store.

    Deprecated: no longer called by ``VectorRecallRoute`` (which now routes
    through ``SeekVFSAdapter.search(query_embedding=...)``). Retained because
    ``VectorMemoryAdapter`` still inherits from it and external callers may
    depend on the explicit vector-search method.

    Adapters that support vector similarity search should inherit from this
    mixin and override ``vector_search``.  The default implementation returns
    an empty list so that callers (e.g. ``VectorRecallRoute``) can safely
    check for the method via ``getattr`` and get a graceful fallback.
    """

    def vector_search(
        self,
        prefix: str,
        query_vector: list[float],
        *,
        k: int,
    ) -> list[dict[str, Any]]:
        """Return payloads whose vector is most similar to *query_vector*.

        Args:
            prefix: Namespace URI prefix to scope the search.
            query_vector: Dense embedding of the query.
            k: Maximum number of results.

        Returns:
            List of payload dicts with at least ``ref`` and ``score`` keys.
            Each dict's ``score`` should be a normalised similarity value in
            ``[0, 1]`` (higher = more similar).
        """
        return []
