"""Unified LLM invocation and response coercion helpers."""

from __future__ import annotations

from typing import Any

from contextseek.llm.parsers import extract_json_object


def coerce_response_text(resp: Any) -> str:
    """Best-effort conversion of an LLM response to plain text."""
    content = getattr(resp, "content", resp)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for chunk in content:
            if isinstance(chunk, str):
                parts.append(chunk)
            elif isinstance(chunk, dict) and "text" in chunk:
                parts.append(str(chunk["text"]))
        return "".join(parts)
    return str(content)


def invoke_text(llm: Any, prompt: str) -> str:
    """Invoke a chat model with one human message and return text."""
    if llm is None:
        return ""
    try:
        from langchain_core.messages import HumanMessage

        resp = llm.invoke([HumanMessage(content=prompt)])
    except Exception:
        return ""
    return coerce_response_text(resp).strip()


def invoke_json(llm: Any, prompt: str) -> dict[str, Any]:
    """Invoke a chat model and parse a JSON object from the output."""
    return extract_json_object(invoke_text(llm, prompt))

