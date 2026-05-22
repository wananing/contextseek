"""DataPlug protocol — streaming ingestion adapters for ContextSeek.

A DataPlug is any source that can stream structured events into the
ContextSeek graph.  Implementations wrap specific data sources (git logs,
Slack channels, document crawlers, etc.) behind a uniform iterator
interface so that `ContextSeek.plug()` can consume them generically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Protocol, runtime_checkable


@dataclass
class PlugMeta:
    """Descriptor for a DataPlug — its identity and default source type."""

    name: str
    """Unique plug identifier (e.g. 'github_commits', 'slack_channel')."""

    source_type: str
    """Maps to a SourceType enum value (e.g. 'document', 'trace_extraction')."""

    description: str = ""
    """Human-readable description of what this plug provides."""


@dataclass
class RawEvent:
    """A single event emitted by a DataPlug's stream.

    RawEvents are the normalised unit of ingestion. They carry content
    and minimal metadata; the ContextSeek client is responsible for
    constructing full ContextItems from them.
    """

    content: str | dict
    """The event payload — plain text or a structured dict."""

    source: str
    """Source identifier (e.g. commit SHA, message URL, file path)."""

    tags: list[str] | None = None
    """Optional tags to attach to the resulting ContextItem."""

    metadata: dict = field(default_factory=dict)
    """Extra key-value pairs the plug can supply (passed to provenance context)."""


@runtime_checkable
class DataPlug(Protocol):
    """Protocol for streaming data sources.

    Any object implementing `stream()` and `metadata()` can be registered
    via `ContextSeek.plug()`.

    Example::

        class GitCommitPlug:
            def __init__(self, repo_path: str):
                self._repo_path = repo_path

            def metadata(self) -> PlugMeta:
                return PlugMeta(
                    name="git_commits",
                    source_type="document",
                    description="Git commit messages",
                )

            def stream(self) -> Iterator[RawEvent]:
                # ... yield RawEvent for each commit
                ...
    """

    def stream(self) -> Iterator[RawEvent]:
        """Yield raw events from the underlying data source.

        Implementations should be lazy — events are consumed on demand by
        the ContextSeek client. If the source is unbounded, the plug should
        document its own stopping criteria.
        """
        ...

    def metadata(self) -> PlugMeta:
        """Return plug metadata (name, source_type, description)."""
        ...
