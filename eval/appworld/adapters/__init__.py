"""Adapter registry for AppWorld evaluation."""

from __future__ import annotations

from .base import AgentAdapter
from .baseline import BaselineAdapter
from .official_simplified import OfficialSimplifiedAdapter
from .contextseek_react import ContextSeekReactAdapter


_REGISTRY: dict[str, type[AgentAdapter]] = {
    "baseline": BaselineAdapter,
    "official_simplified": OfficialSimplifiedAdapter,
    "contextseek_react": ContextSeekReactAdapter,
}


def get_adapter_class(name: str) -> type[AgentAdapter]:
    """Resolve an adapter class by config name."""
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        known = ", ".join(sorted(_REGISTRY))
        raise ValueError(f"unknown AppWorld adapter {name!r}; expected one of: {known}") from exc


__all__ = ["AgentAdapter", "get_adapter_class"]
