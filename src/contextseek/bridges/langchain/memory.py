"""LangChain memory adapter for ContextSeek (unified ContextItem API)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from contextseek.bridges.base import AdapterCapability
from contextseek.bridges.base import AdapterSpec
from contextseek.bridges.compat import AIMessage
from contextseek.bridges.compat import BaseChatMessageHistory
from contextseek.bridges.compat import BaseMessage
from contextseek.bridges.compat import ConfigDict
from contextseek.bridges.compat import HumanMessage
from contextseek.bridges.compat import LANGCHAIN_MEMORY_AVAILABLE
from contextseek.bridges.compat import SystemMessage

if TYPE_CHECKING:
    from contextseek.client.contextseek import ContextSeek
    from contextseek.domain import ContextItem


def _message_from_type(message_type: str, content: str) -> BaseMessage:
    if message_type == "ai":
        return AIMessage(content=content)
    if message_type == "system":
        return SystemMessage(content=content)
    return HumanMessage(content=content)


def _item_to_message(item: "ContextItem") -> BaseMessage | None:
    """Convert a ContextItem back into a LangChain message."""
    tags = item.tags or []
    content_text = item.content_text
    if not content_text:
        return None
    if "ai" in tags:
        return AIMessage(content=content_text)
    if "system" in tags:
        return SystemMessage(content=content_text)
    return HumanMessage(content=content_text)


# Tags on every message written by _write_message; must match orchestrator's ALL-tags rule.
_LANGCHAIN_TAG_FILTER = frozenset({"langchain", "message"})


def _langchain_stored_items(client: Any, scope: str, k: int) -> list[Any]:
    """Last ``k`` LangChain-tagged items in ``scope``, chronological order.

    Uses :meth:`ContextSeek.items` (full enumeration) instead of ``retrieve`` so
    conversation lines are not ranked out by unrelated semantic hits.
    """
    ordered = client.items(scope=scope)
    tagged = [it for it in ordered if _LANGCHAIN_TAG_FILTER.issubset(set(it.tags or []))]
    return tagged[-k:] if k else tagged


def _all_langchain_stored_items(client: Any, scope: str) -> list[Any]:
    ordered = client.items(scope=scope)
    return [it for it in ordered if _LANGCHAIN_TAG_FILTER.issubset(set(it.tags or []))]


_SPEC = AdapterSpec(
    name="contextseek.langchain.memory",
    framework="langchain",
    capabilities=(AdapterCapability.MEMORY,),
    description="LangChain chat history adapter backed by ContextSeek unified ContextItem API.",
    required_packages=("langchain-core",),
)


if LANGCHAIN_MEMORY_AVAILABLE:

    @dataclass
    class ContextSeekMemory(BaseChatMessageHistory):
        """Message history adapter aligned with `langchain_core` contracts.

        Uses the unified ContextSeek client with add()/retrieve() API.
        """

        client: Any
        scope: str
        memory_key: str = "history"
        input_key: str = "input"
        output_key: str = "output"
        k: int = 10

        model_config = ConfigDict(arbitrary_types_allowed=True)

        @property
        def messages(self) -> list[BaseMessage]:
            """Return messages loaded from LangChain-tagged items in this scope."""
            messages: list[BaseMessage] = []
            for item in _langchain_stored_items(self.client, self.scope, self.k):
                msg = _item_to_message(item)
                if msg is not None:
                    messages.append(msg)
            return messages

        def add_messages(self, messages: list[BaseMessage]) -> None:
            """Append LangChain messages into ContextSeek via add()."""
            for message in messages:
                self._write_message(str(message.content), message_type=message.type)

        def load_memory_variables(self, _: dict[str, Any]) -> dict[str, str]:
            """Compatibility helper for chain memory usage."""
            items = [str(message.content) for message in self.messages]
            return {self.memory_key: "\n".join(items)}

        def save_context(
            self, inputs: dict[str, Any], outputs: dict[str, Any], *, source: str = "langchain"
        ) -> "ContextItem":
            """Persist latest interaction and return the output ContextItem."""
            self._write_message(
                str(inputs.get(self.input_key, "")), message_type="human", source=source
            )
            return self._write_message(
                str(outputs.get(self.output_key, "")), message_type="ai", source=source
            )

        def clear(self) -> None:
            """Clear all langchain messages in this scope via forget()."""
            for item in _all_langchain_stored_items(self.client, self.scope):
                ref = self.client.resolver.ref_for(self.scope, item.id)
                self.client.forget(ref, scope=self.scope, reason="langchain memory clear")

        def _write_message(
            self, content: str, *, message_type: str, source: str = "langchain"
        ) -> "ContextItem":
            return self.client.add(
                content,
                scope=self.scope,
                source=source,
                source_type="human_input",
                tags=["langchain", "message", message_type],
            )

        @classmethod
        def spec(cls) -> AdapterSpec:
            return _SPEC

        @classmethod
        def validate_environment(cls) -> tuple[bool, str | None]:
            return True, None

        @classmethod
        def from_client(
            cls, client: "ContextSeek", *, scope: str, k: int = 10
        ) -> "ContextSeekMemory":
            return cls(client=client, scope=scope, k=k)

else:

    @dataclass
    class ContextSeekMemory(BaseChatMessageHistory):  # type: ignore[no-redef]
        """Fallback memory adapter when langchain-core is unavailable."""

        client: Any
        scope: str
        memory_key: str = "history"
        input_key: str = "input"
        output_key: str = "output"
        k: int = 10

        @property
        def messages(self) -> list[BaseMessage]:
            messages: list[BaseMessage] = []
            for item in _langchain_stored_items(self.client, self.scope, self.k):
                msg = _item_to_message(item)
                if msg is not None:
                    messages.append(msg)
            return messages

        def add_messages(self, messages: list[BaseMessage]) -> None:
            for message in messages:
                self._write_message(str(message.content), message_type=message.type)

        def load_memory_variables(self, _: dict[str, Any]) -> dict[str, str]:
            items = [str(message.content) for message in self.messages]
            return {self.memory_key: "\n".join(items)}

        def save_context(
            self, inputs: dict[str, Any], outputs: dict[str, Any], *, source: str = "langchain"
        ) -> "ContextItem":
            self._write_message(
                str(inputs.get(self.input_key, "")), message_type="human", source=source
            )
            return self._write_message(
                str(outputs.get(self.output_key, "")), message_type="ai", source=source
            )

        def clear(self) -> None:
            for item in _all_langchain_stored_items(self.client, self.scope):
                ref = self.client.resolver.ref_for(self.scope, item.id)
                self.client.forget(ref, scope=self.scope, reason="langchain memory clear")

        def _write_message(
            self, content: str, *, message_type: str, source: str = "langchain"
        ) -> "ContextItem":
            return self.client.add(
                content,
                scope=self.scope,
                source=source,
                source_type="human_input",
                tags=["langchain", "message", message_type],
            )

        @classmethod
        def spec(cls) -> AdapterSpec:
            return _SPEC

        @classmethod
        def validate_environment(cls) -> tuple[bool, str | None]:
            return False, "langchain-core is required for native chat history integration."

        @classmethod
        def from_client(
            cls, client: "ContextSeek", *, scope: str, k: int = 10
        ) -> "ContextSeekMemory":
            return cls(client=client, scope=scope, k=k)
