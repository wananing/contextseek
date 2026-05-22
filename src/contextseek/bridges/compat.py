"""Compatibility shims for optional framework dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from typing import Any

try:
    from pydantic import ConfigDict
except ImportError:  # pragma: no cover

    def ConfigDict(**kwargs: Any) -> dict[str, Any]:  # type: ignore[misc]
        """Fallback ConfigDict shim when pydantic is unavailable."""
        return kwargs


try:
    from langchain_core.callbacks import CallbackManagerForRetrieverRun
    from langchain_core.documents import Document
    from langchain_core.retrievers import BaseRetriever

    LANGCHAIN_RETRIEVER_AVAILABLE = True
except ImportError:  # pragma: no cover - fallback when langchain-core isn't installed.
    LANGCHAIN_RETRIEVER_AVAILABLE = False

    class CallbackManagerForRetrieverRun:  # type: ignore[no-redef]
        """Fallback callback manager."""

    @dataclass
    class Document:  # type: ignore[override,no-redef]
        """Fallback document compatible with basic usage."""

        page_content: str
        metadata: dict[str, Any]

    class BaseRetriever:  # type: ignore[no-redef]
        """Fallback base retriever."""

        def invoke(self, query: str) -> list[Document]:
            return self.get_relevant_documents(query)


try:
    from langchain_core.chat_history import BaseChatMessageHistory
    from langchain_core.messages import AIMessage
    from langchain_core.messages import BaseMessage
    from langchain_core.messages import HumanMessage
    from langchain_core.messages import SystemMessage

    LANGCHAIN_MEMORY_AVAILABLE = True
except ImportError:  # pragma: no cover - fallback when langchain-core isn't installed.
    LANGCHAIN_MEMORY_AVAILABLE = False

    @dataclass
    class BaseMessage:  # type: ignore[override,no-redef]
        """Fallback message model."""

        content: str
        type: str = "human"

    @dataclass
    class HumanMessage(BaseMessage):  # type: ignore[no-redef]
        """Fallback human message."""

        type: str = "human"

    @dataclass
    class AIMessage(BaseMessage):  # type: ignore[no-redef]
        """Fallback AI message."""

        type: str = "ai"

    @dataclass
    class SystemMessage(BaseMessage):  # type: ignore[no-redef]
        """Fallback system message."""

        type: str = "system"

    class BaseChatMessageHistory:  # type: ignore[no-redef]
        """Fallback message history base."""

        @property
        def messages(self) -> list[BaseMessage]:
            return []

        def add_messages(self, messages: list[BaseMessage]) -> None:
            del messages

        def clear(self) -> None:
            return None


def package_available(name: str) -> bool:
    """Return whether an optional package can be imported."""
    return find_spec(name) is not None


DEEPAGENTS_AVAILABLE = package_available("deepagents")
