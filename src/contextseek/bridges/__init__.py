"""Framework bridges (LangChain, DeepAgents) and discovery registry."""

from contextseek.bridges.base import AdapterCapability
from contextseek.bridges.base import AdapterContract
from contextseek.bridges.base import AdapterSpec
from contextseek.bridges.registry import get_adapter
from contextseek.bridges.registry import list_adapter_specs
from contextseek.bridges.registry import register_adapter
from contextseek.bridges.registry import register_builtin_adapters

__all__ = [
    "AdapterCapability",
    "AdapterContract",
    "AdapterSpec",
    "get_adapter",
    "list_adapter_specs",
    "register_adapter",
    "register_builtin_adapters",
]
