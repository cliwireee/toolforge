"""Accurate token counting for MCP tool definitions."""

from __future__ import annotations

import json
from typing import Any

import tiktoken

# Claude / Anthropic models use cl100k_base (same as GPT-4 family for practical purposes)
_ENCODING = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Return the number of tokens in the given text."""
    if not text:
        return 0
    return len(_ENCODING.encode(text))


def count_json_tokens(obj: Any) -> int:
    """Serialize an object to JSON and count its tokens."""
    try:
        text = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError):
        text = str(obj)
    return count_tokens(text)


def estimate_tool_tokens(tool: dict[str, Any]) -> dict[str, int]:
    """
    Estimate token cost of a single MCP tool definition.

    Returns a breakdown:
    - name_tokens
    - description_tokens
    - input_schema_tokens
    - structural_tokens
    - total
    """
    name = tool.get("name", "")
    description = tool.get("description", "") or ""
    input_schema = tool.get("inputSchema") or tool.get("input_schema") or {}

    name_tokens = count_tokens(name)
    desc_tokens = count_tokens(description)
    schema_tokens = count_json_tokens(input_schema)

    # MCP tool list entries also carry a small amount of structural overhead
    # (JSON keys, commas, etc.). We add a small constant that matches observed
    # real-world measurements.
    structural = 12

    return {
        "name_tokens": name_tokens,
        "description_tokens": desc_tokens,
        "input_schema_tokens": schema_tokens,
        "structural_tokens": structural,
        "total": name_tokens + desc_tokens + schema_tokens + structural,
    }


def estimate_server_tokens(tools: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Estimate total token cost for a list of tools from one MCP server.

    Returns aggregate stats plus per-tool breakdown.
    """
    if not tools:
        return {
            "tool_count": 0,
            "total_tokens": 0,
            "avg_tokens_per_tool": 0,
            "tools": [],
        }

    per_tool = []
    total = 0
    for t in tools:
        breakdown = estimate_tool_tokens(t)
        per_tool.append(
            {
                "name": t.get("name", "<unnamed>"),
                **breakdown,
            }
        )
        total += breakdown["total"]

    return {
        "tool_count": len(tools),
        "total_tokens": total,
        "avg_tokens_per_tool": round(total / len(tools), 1),
        "tools": sorted(per_tool, key=lambda x: x["total"], reverse=True),
    }
