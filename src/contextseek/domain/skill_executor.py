"""Skill export — converts skill ContextItems to LLM/agent integration formats.

Skills are ContextItems with stage=skill. ContextSeek's responsibility is
store + retrieve + export. Execution is handled by the external agent runtime.
"""

from __future__ import annotations

import warnings
from typing import Any

from contextseek.domain.context_item import ContextItem
from contextseek.domain.stages import Stage


def _skill_name(skill: ContextItem) -> str:
    if isinstance(skill.content, dict):
        return skill.content.get("name", skill.id[:8])
    return skill.id[:8]


def _skill_desc(skill: ContextItem) -> str:
    if isinstance(skill.content, dict):
        return skill.content.get("description", "")
    return ""


def _skill_type(skill: ContextItem) -> str:
    if isinstance(skill.content, dict):
        return skill.content.get("skill_type", "prompt")
    return "prompt"


def _empty_schema() -> dict[str, Any]:
    return {"type": "object", "properties": {}}


def _tool_parameters(skill: ContextItem) -> dict[str, Any]:
    """Extract JSON schema parameters from skill content."""
    if isinstance(skill.content, dict):
        params = skill.content.get("parameters")
        if isinstance(params, dict):
            return params
        # mcp-type: inputSchema is the equivalent
        schema = skill.content.get("inputSchema")
        if isinstance(schema, dict):
            return schema
    return _empty_schema()


class SkillExporter:
    """Converts skill ContextItems to LLM/agent integration formats.

    Supports three skill_type values:
    - "prompt"  — Markdown body; exported as a no-arg function whose description
                  contains the full instruction document (Hermes / SuperAGI style)
    - "tool"    — JSON schema parameters; exported as a standard function tool
    - "mcp"     — MCP inputSchema; exported as an MCP tool definition
    """

    # ── Single-item export ────────────────────────────────────────────────

    def to_openai_function(self, item: ContextItem) -> dict[str, Any]:
        """→ {"type": "function", "function": {name, description, parameters}}"""
        name = _skill_name(item)
        desc = _skill_desc(item)
        stype = _skill_type(item)

        if stype == "prompt":
            body = item.content.get("body", "") if isinstance(item.content, dict) else ""
            description = f"{desc}\n\n{body}".strip() if body else desc
            parameters = _empty_schema()
        else:
            description = desc
            parameters = _tool_parameters(item)

        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
        }

    def to_anthropic_tool(self, item: ContextItem) -> dict[str, Any]:
        """→ {"name": ..., "description": ..., "input_schema": {...}}"""
        name = _skill_name(item)
        desc = _skill_desc(item)
        stype = _skill_type(item)

        if stype == "prompt":
            body = item.content.get("body", "") if isinstance(item.content, dict) else ""
            description = f"{desc}\n\n{body}".strip() if body else desc
            input_schema = _empty_schema()
        else:
            description = desc
            input_schema = _tool_parameters(item)

        return {
            "name": name,
            "description": description,
            "input_schema": input_schema,
        }

    def to_mcp_tool(self, item: ContextItem) -> dict[str, Any]:
        """→ {"name": ..., "description": ..., "inputSchema": {...}}"""
        name = _skill_name(item)
        desc = _skill_desc(item)
        stype = _skill_type(item)

        if stype == "mcp" and isinstance(item.content, dict):
            schema = item.content.get("inputSchema", _empty_schema())
        else:
            schema = _tool_parameters(item)

        return {
            "name": name,
            "description": desc,
            "inputSchema": schema,
        }

    def to_prompt_block(self, item: ContextItem) -> str:
        """→ Markdown block with name / description / body."""
        name = _skill_name(item)
        desc = _skill_desc(item)
        body = ""
        if isinstance(item.content, dict):
            body = item.content.get("body", "")

        parts = [f"### {name}"]
        if desc:
            parts.append(desc)
        if body:
            parts.append(body)
        return "\n\n".join(parts)

    def to_hermes_skill_md(self, item: ContextItem) -> str:
        """→ Full SKILL.md content (YAML frontmatter + Markdown body)."""
        name = _skill_name(item)
        desc = _skill_desc(item)
        version = "1.0.0"
        tags: list[str] = []
        body = ""

        if isinstance(item.content, dict):
            version = item.content.get("version", version)
            tags = item.content.get("tags", [])
            body = item.content.get("body", "")

        tag_str = ", ".join(tags) if tags else ""
        frontmatter = (
            "---\n"
            f"name: {name}\n"
            f"description: {desc}\n"
            f"version: {version}\n"
        )
        if tag_str:
            frontmatter += f"tags: [{tag_str}]\n"
        frontmatter += "---\n"

        return frontmatter + "\n" + body if body else frontmatter

    def to_system_prompt(self, items: list[ContextItem]) -> str:
        """→ Multi-skill Hermes-style system prompt block.

        Format::
            <available_skills>
            ### skill-name
            description …

            body …

            ### skill-name-2
            …
            </available_skills>
        """
        if not items:
            return ""
        blocks = [self.to_prompt_block(it) for it in items]
        inner = "\n\n---\n\n".join(blocks)
        return f"<available_skills>\n{inner}\n</available_skills>"

    # ── Batch export ──────────────────────────────────────────────────────

    def batch_to_openai(self, items: list[ContextItem]) -> list[dict[str, Any]]:
        """Batch export tool/mcp skills as OpenAI tools list."""
        return [self.to_openai_function(it) for it in items]

    def batch_to_anthropic(self, items: list[ContextItem]) -> list[dict[str, Any]]:
        """Batch export tool/mcp skills as Anthropic tools list."""
        return [self.to_anthropic_tool(it) for it in items]


# ── Backward-compat stubs ─────────────────────────────────────────────────


class SkillExecutor:
    """Deprecated: use SkillExporter for format conversion.

    ContextSeek no longer executes skills — execution is handled by the
    external agent runtime. This class is kept for import compatibility only.
    """

    def execute(self, skill: ContextItem, *, args: dict[str, Any] | None = None) -> dict[str, Any]:
        warnings.warn(
            "SkillExecutor.execute() is deprecated. ContextSeek no longer executes skills. "
            "Use SkillExporter to export skills to your agent runtime's format.",
            DeprecationWarning,
            stacklevel=2,
        )
        if skill.stage != Stage.skill:
            msg = f"item {skill.id} is not a skill (stage={skill.stage})"
            raise ValueError(msg)
        return {"warning": "SkillExecutor is deprecated", "skill_id": skill.id}

    def register(self, *args: Any, **kwargs: Any) -> None:
        warnings.warn("SkillExecutor is deprecated.", DeprecationWarning, stacklevel=2)

    def register_default(self, *args: Any, **kwargs: Any) -> None:
        warnings.warn("SkillExecutor is deprecated.", DeprecationWarning, stacklevel=2)


__all__ = ["SkillExporter", "SkillExecutor"]
