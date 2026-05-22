"""Deep Agents context store adapter backed by ContextSeek (unified ContextItem API)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from contextseek.bridges.base import AdapterCapability
from contextseek.bridges.base import AdapterSpec
from contextseek.bridges.compat import DEEPAGENTS_AVAILABLE

if TYPE_CHECKING:
    from contextseek.client.contextseek import ContextSeek
    from contextseek.domain import ContextItem, RetrieveResponse


@dataclass
class ContextStore:
    """Context adapter for agent-scoped and user-scoped memory access.

    Uses the unified ContextSeek client with add()/retrieve() API.
    """

    client: "ContextSeek"
    scope: str

    @classmethod
    def spec(cls) -> AdapterSpec:
        return AdapterSpec(
            name="contextseek.deepagents.context_store",
            framework="deepagents",
            capabilities=(AdapterCapability.CONTEXT_STORE, AdapterCapability.RETRIEVAL),
            description="Deep Agents context-store adapter using unified ContextItem API.",
            required_packages=("deepagents",),
        )

    @classmethod
    def validate_environment(cls) -> tuple[bool, str | None]:
        if DEEPAGENTS_AVAILABLE:
            return True, None
        return False, "deepagents package is required for native Deep Agents integration."

    @classmethod
    def from_client(cls, client: "ContextSeek", *, scope: str) -> "ContextStore":
        return cls(client=client, scope=scope)

    def put_memory(
        self,
        content: str,
        *,
        tags: list[str] | None = None,
        source: str = "deepagents",
        source_type: str = "agent_inference",
    ) -> "ContextItem":
        """Store one memory item for Deep Agents runtime via add()."""
        return self.client.add(
            content,
            scope=self.scope,
            source=source,
            source_type=source_type,
            tags=tags or ["deepagents", "memory"],
        )

    def get_memory(self, ref: str) -> "ContextItem | None":
        """Fetch one context item by ID via ranked retrieval."""
        response = self.client.retrieve(ref, scope=self.scope, k=1)
        if response.items:
            return response.items[0].item
        return None

    def search_memory(self, query: str, *, k: int = 20) -> "RetrieveResponse":
        """Search for context items relevant to a query."""
        return self.client.retrieve(query, scope=self.scope, k=k)

    def recall(
        self,
        query: str,
        *,
        k: int = 10,
        full: bool = False,
        stage: Any = None,
        tags: list[str] | None = None,
    ) -> "RetrieveResponse":
        """Recall ranked hits for runtime context injection."""
        return self.client.retrieve(
            query,
            scope=self.scope,
            k=k,
            full=full,
            stage=stage,
            tags=tags,
        )

    def load_working_set(self, query: str, *, k: int = 10) -> "RetrieveResponse":
        """Load top-k context candidates via retrieve()."""
        return self.client.retrieve(query, scope=self.scope, k=k)

    def forget(self, ref: str, *, reason: str = "deepagents runtime") -> None:
        """Remove a context item via forget()."""
        self.client.forget(ref, scope=self.scope, reason=reason)

    def feedback(self, ref: str, *, score: float, reason: str = "") -> None:
        """Provide feedback on a context item."""
        self.client.feedback(ref, scope=self.scope, score=score, reason=reason)
