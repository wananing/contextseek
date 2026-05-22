"""Structured errors shared by SDK, HTTP and MCP layers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ContextSeekError(ValueError):
    """Business-level error with stable machine-readable metadata."""

    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.message

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details or {},
        }


def invalid_namespaces(
    values: list[str], *, reason: str = "invalid"
) -> ContextSeekError:
    """Return a consistent namespace validation error."""
    return ContextSeekError(
        code="invalid_namespaces",
        message=f"invalid namespaces: {', '.join(sorted(set(values)))}",
        details={"namespaces": values, "reason": reason},
    )
