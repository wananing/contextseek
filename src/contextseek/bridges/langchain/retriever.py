"""LangChain retriever adapter for ContextSeek (unified ContextItem API)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from contextseek.bridges.base import AdapterCapability
from contextseek.bridges.base import AdapterSpec
from contextseek.bridges.compat import BaseRetriever
from contextseek.bridges.compat import CallbackManagerForRetrieverRun
from contextseek.bridges.compat import ConfigDict
from contextseek.bridges.compat import Document
from contextseek.bridges.compat import LANGCHAIN_RETRIEVER_AVAILABLE

if TYPE_CHECKING:
    from contextseek.client.contextseek import ContextSeek
    from contextseek.domain import Stage


def _to_documents(
    *,
    client: "ContextSeek",
    scope: str,
    query: str,
    k: int,
    stage: "Stage | None" = None,
) -> list[Document]:
    """Convert ContextSeek ranked hits to LangChain Documents."""
    response = client.retrieve(query, scope=scope, k=k)
    docs: list[Document] = []
    for hit in response:
        if stage is not None and hit.item.stage != stage:
            continue
        page_content = hit.item.summary or hit.item.content_text
        docs.append(
            Document(
                page_content=page_content,
                metadata={
                    "id": hit.item.id,
                    "score": hit.score,
                    "stage": hit.item.stage.value if hit.item.stage else None,
                    "stage_confidence": hit.stage_confidence,
                    "provenance_summary": hit.provenance_summary,
                    "scope": hit.item.scope,
                    "tags": list(hit.item.tags),
                    "recall_path": hit.recall_path,
                },
            )
        )
    return docs


_SPEC = AdapterSpec(
    name="contextseek.langchain.retriever",
    framework="langchain",
    capabilities=(AdapterCapability.RETRIEVAL,),
    description="LangChain BaseRetriever adapter for ContextSeek unified ContextItem API.",
    required_packages=("langchain-core",),
)


if LANGCHAIN_RETRIEVER_AVAILABLE:

    class ContextSeekRetriever(BaseRetriever):
        """Retriever adapter aligned with `langchain_core.BaseRetriever`.

        Uses the new unified ContextSeek client with scope-based access.
        """

        client: Any
        scope: str
        k: int = 20
        stage: Any = None  # Optional[Stage]

        model_config = ConfigDict(arbitrary_types_allowed=True)

        def _get_relevant_documents(
            self, query: str, *, run_manager: CallbackManagerForRetrieverRun
        ) -> list[Document]:
            del run_manager
            return _to_documents(
                client=self.client,
                scope=self.scope,
                query=query,
                k=self.k,
                stage=self.stage,
            )

        def get_relevant_documents(self, query: str) -> list[Document]:
            """Compatibility alias for legacy LangChain usage."""
            return self.invoke(query)

        @classmethod
        def spec(cls) -> AdapterSpec:
            return _SPEC

        @classmethod
        def validate_environment(cls) -> tuple[bool, str | None]:
            return True, None

        @classmethod
        def from_client(
            cls,
            client: "ContextSeek",
            *,
            scope: str,
            k: int = 20,
            stage: "Stage | None" = None,
        ) -> "ContextSeekRetriever":
            return cls(client=client, scope=scope, k=k, stage=stage)

else:

    @dataclass
    class ContextSeekRetriever(BaseRetriever):  # type: ignore[no-redef]
        """Retriever adapter with fallback behavior."""

        client: Any
        scope: str
        k: int = 20
        stage: Any = None

        def get_relevant_documents(self, query: str) -> list[Document]:
            return _to_documents(
                client=self.client,
                scope=self.scope,
                query=query,
                k=self.k,
                stage=self.stage,
            )

        @classmethod
        def spec(cls) -> AdapterSpec:
            return _SPEC

        @classmethod
        def validate_environment(cls) -> tuple[bool, str | None]:
            return False, "langchain-core is required for native retriever integration."

        @classmethod
        def from_client(
            cls,
            client: "ContextSeek",
            *,
            scope: str,
            k: int = 20,
            stage: "Stage | None" = None,
        ) -> "ContextSeekRetriever":
            return cls(client=client, scope=scope, k=k, stage=stage)
