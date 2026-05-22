"""Helpers for tolerant LLM output parsing."""

from __future__ import annotations

import json
import re
from typing import Any


def extract_json_object(text: str) -> dict[str, Any]:
    """Best-effort parse for a JSON object from raw LLM output."""
    raw = text.strip()
    if not raw:
        return {}

    # Strip fenced code block wrappers when present.
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    # First try: parse full payload directly.
    parsed = _load_dict(raw)
    if parsed is not None:
        return parsed

    # Fallback: pick the first JSON object-like slice.
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {}
    parsed = _load_dict(match.group(0))
    return parsed or {}


def _load_dict(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except Exception:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None

