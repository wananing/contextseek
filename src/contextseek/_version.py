"""Package version (single source: ``pyproject.toml`` via installed metadata)."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version


def get_version() -> str:
    """Return the installed ``contextseek`` distribution version."""
    try:
        return version("contextseek")
    except PackageNotFoundError:
        return "0.0.0+unknown"


__version__ = get_version()
