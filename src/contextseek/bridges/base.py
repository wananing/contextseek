"""Unified bridge contract for framework integrations (LangChain, DeepAgents)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from typing import Protocol
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from contextseek.client.contextseek import ContextSeek


class AdapterCapability(StrEnum):
    """Capabilities exposed by a framework adapter."""

    RETRIEVAL = "retrieval"
    MEMORY = "memory"
    TRACE_SINK = "trace_sink"
    CONTEXT_STORE = "context_store"


@dataclass(frozen=True)
class AdapterSpec:
    """Static metadata used for adapter discovery and validation."""

    name: str
    framework: str
    capabilities: tuple[AdapterCapability, ...]
    description: str
    required_packages: tuple[str, ...] = ()
    version: str = "v2"


class AdapterContract(Protocol):
    """Standard class-level contract all adapters should implement."""

    @classmethod
    def spec(cls) -> AdapterSpec:
        """Return static adapter metadata."""

    @classmethod
    def validate_environment(cls) -> tuple[bool, str | None]:
        """Validate adapter runtime dependencies."""

    @classmethod
    def from_client(cls, client: "ContextSeek", **kwargs: Any) -> Any:
        """Create adapter instance from a unified `ContextSeek` client."""
