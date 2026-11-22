"""Parsing and validation of tool definitions.

Accepted input shapes:

* a JSON list of tools, or an object with a ``"tools"`` list (``tools/list`` result);
* MCP tools (``inputSchema``), Anthropic API tools (``input_schema``) and
  OpenAI function tools (``parameters``, optionally wrapped as
  ``{"type": "function", "function": {...}}``).

Every tool is normalised to the MCP shape (``name``, ``description``,
``inputSchema``). Other keys (``title``, ``annotations``, ...) are preserved.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from toolforge.core.tokens import SCHEMA_KEYS

# Length of the description shown in lightweight listings.
SHORT_DESCRIPTION_CHARS = 120

_MAX_REPORTED_PROBLEMS = 10


class ToolDefinitionError(ValueError):
    """Input is not a usable list of tool definitions."""

    def __init__(self, problems: list[str], source: str = "input") -> None:
        self.problems = problems
        self.source = source
        shown = problems[:_MAX_REPORTED_PROBLEMS]
        extra = len(problems) - len(shown)
        lines = [f"Invalid tool definitions in {source}:"] + [f"  - {p}" for p in shown]
        if extra > 0:
            lines.append(f"  ... and {extra} more problem(s)")
        super().__init__("\n".join(lines))


def _type_name(value: Any) -> str:
    return "null" if value is None else type(value).__name__


def _unwrap_openai(tool: dict[str, Any]) -> dict[str, Any]:
    inner = tool.get("function")
    if tool.get("type") == "function" and isinstance(inner, dict):
        return {**inner}
    return tool


def _normalise_tool(index: int, raw: Any, problems: list[str]) -> dict[str, Any] | None:
    where = f"tools[{index}]"
    if not isinstance(raw, dict):
        problems.append(f"{where}: expected an object, got {_type_name(raw)}")
        return None

    tool = _unwrap_openai(raw)
    name = tool.get("name")
    if not isinstance(name, str) or not name.strip():
        problems.append(f"{where}: 'name' must be a non-empty string")
        return None
    where = f"{where} ({name!r})"

    description = tool.get("description")
    if description is None:
        description = ""
    elif not isinstance(description, str):
        problems.append(f"{where}: 'description' must be a string, got {_type_name(description)}")
        return None

    schema: Any = {}
    for key in SCHEMA_KEYS:
        if tool.get(key) is not None:
            schema = tool[key]
            break
    if not isinstance(schema, dict):
        problems.append(f"{where}: input schema must be an object, got {_type_name(schema)}")
        return None

    normalised = {k: v for k, v in tool.items() if k not in SCHEMA_KEYS}
    normalised["name"] = name
    normalised["description"] = description
    normalised["inputSchema"] = schema
    return normalised


def parse_tools(data: Any, *, source: str = "input") -> list[dict[str, Any]]:
    """Validate and normalise decoded JSON into a list of tool definitions.

    Raises :class:`ToolDefinitionError` listing every problem found, so a bad
    entry never surfaces later as an ``AttributeError`` deep in the audit.
    """
    if isinstance(data, dict) and "tools" in data:
        data = data["tools"]
    elif isinstance(data, dict):
        raise ToolDefinitionError(
            ["expected a list of tools or an object with a 'tools' key; got an object "
             f"with keys {sorted(data)[:5]}"],
            source,
        )
    if not isinstance(data, list):
        raise ToolDefinitionError(
            [f"expected a list of tools, got {_type_name(data)}"], source
        )

    problems: list[str] = []
    tools = [_normalise_tool(i, raw, problems) for i, raw in enumerate(data)]
    if problems:
        raise ToolDefinitionError(problems, source)
    return [t for t in tools if t is not None]


def parse_tools_json(text: str, *, source: str = "input") -> list[dict[str, Any]]:
    """Decode a JSON string and validate it with :func:`parse_tools`."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ToolDefinitionError(
            [f"invalid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})"], source
        ) from exc
    return parse_tools(data, source=source)


def load_tools_file(path: Path) -> list[dict[str, Any]]:
    """Read, decode and validate a JSON file of tool definitions."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ToolDefinitionError(
            [f"file is not valid UTF-8 text ({exc.reason})"], str(path)
        ) from exc
    except OSError as exc:
        raise ToolDefinitionError([f"cannot read file: {exc.strerror or exc}"], str(path)) from exc
    return parse_tools_json(text, source=str(path))


def duplicate_names(tools: list[dict[str, Any]]) -> list[str]:
    """Return tool names that occur more than once, in first-seen order."""
    seen: set[str] = set()
    dupes: dict[str, None] = {}
    for tool in tools:
        name = tool["name"]
        if name in seen:
            dupes[name] = None
        seen.add(name)
    return list(dupes)


_WHITESPACE = re.compile(r"\s+")


def short_description(description: str, limit: int = SHORT_DESCRIPTION_CHARS) -> str:
    """Collapse whitespace and truncate on a word boundary, marking the cut with '…'."""
    text = _WHITESPACE.sub(" ", description).strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    space = cut.rfind(" ")
    if space >= limit // 2:  # avoid chopping to almost nothing on one long word
        cut = cut[:space]
    return cut.rstrip(" ,;:.-") + "…"


def lightweight_entry(tool: dict[str, Any], server: str) -> dict[str, Any]:
    """The cheap listing entry an agent sees for a lazily loaded tool."""
    return {
        "name": tool["name"],
        "server": server,
        "description": short_description(tool.get("description") or ""),
    }
