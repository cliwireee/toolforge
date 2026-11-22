"""Token estimation for MCP tool definitions.

Counts use tiktoken's ``cl100k_base`` encoding. That is OpenAI's tokenizer, not
Claude's: Anthropic does not publish the tokenizer Claude uses, so every number
produced here is an *estimate*. It is good for comparing tools and servers with
each other and for spotting outliers; it is not an exact bill.

The encoding is loaded lazily on first use. tiktoken downloads the vocabulary
the first time it is needed and caches it (see ``TIKTOKEN_CACHE_DIR``), so
commands that never count tokens keep working offline.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, TypedDict

import tiktoken

ENCODING_NAME = "cl100k_base"

# Allowance for the JSON keys and punctuation that wrap each tool entry when a
# client serialises it ({"name": ..., "description": ..., "input_schema": ...}).
# This is an approximation, not a measured constant.
STRUCTURAL_TOKENS_PER_TOOL = 12

# Keys that may hold a tool's argument schema, in priority order:
# MCP (inputSchema), Anthropic API (input_schema), OpenAI function calling (parameters).
SCHEMA_KEYS = ("inputSchema", "input_schema", "parameters")


class TokenizerUnavailableError(RuntimeError):
    """The tokenizer vocabulary could not be loaded (usually: first run while offline)."""


class ToolTokens(TypedDict):
    name_tokens: int
    description_tokens: int
    input_schema_tokens: int
    structural_tokens: int
    total: int


class NamedToolTokens(ToolTokens):
    name: str


class ServerTokens(TypedDict):
    tool_count: int
    total_tokens: int
    avg_tokens_per_tool: float
    tools: list[NamedToolTokens]


def _short_error(exc: BaseException, limit: int = 200) -> str:
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
    return text if len(text) <= limit else text[: limit - 1] + "…"


@lru_cache(maxsize=1)
def get_encoding() -> tiktoken.Encoding:
    """Return the shared encoding, loading (and possibly downloading) it once."""
    try:
        return tiktoken.get_encoding(ENCODING_NAME)
    except Exception as exc:  # network errors, proxy refusals, corrupt cache, ...
        raise TokenizerUnavailableError(
            f"Could not load the '{ENCODING_NAME}' tokenizer vocabulary "
            f"({type(exc).__name__}: {_short_error(exc)}).\n"
            "tiktoken downloads it on first use and caches it afterwards. Run once with "
            "network access, or set TIKTOKEN_CACHE_DIR to a directory that already "
            "contains the cached vocabulary."
        ) from exc


def count_tokens(text: str) -> int:
    """Return the estimated number of tokens in ``text``.

    Special-token markers such as ``<|endoftext|>`` are counted as ordinary text
    instead of raising, because tool descriptions are arbitrary user content.
    """
    if not text:
        return 0
    return len(get_encoding().encode_ordinary(text))


def count_json_tokens(obj: Any) -> int:
    """Serialise ``obj`` as compact JSON and count its tokens."""
    try:
        text = json.dumps(obj, separators=(",", ":"), ensure_ascii=False, default=str)
    except ValueError:  # e.g. circular references in programmatic input
        text = str(obj)
    return count_tokens(text)


def tool_schema(tool: dict[str, Any]) -> Any:
    """Return the argument schema of a tool in MCP, Anthropic or OpenAI format."""
    for key in SCHEMA_KEYS:
        value = tool.get(key)
        if value is not None:
            return value
    return {}


def estimate_tool_tokens(tool: dict[str, Any]) -> ToolTokens:
    """Estimate the token cost of a single tool definition.

    Returns a breakdown with ``name_tokens``, ``description_tokens``,
    ``input_schema_tokens``, ``structural_tokens`` and ``total``.
    """
    name = tool.get("name") or ""
    description = tool.get("description") or ""

    name_tokens = count_tokens(str(name))
    desc_tokens = count_tokens(str(description))
    schema_tokens = count_json_tokens(tool_schema(tool))
    structural = STRUCTURAL_TOKENS_PER_TOOL

    return {
        "name_tokens": name_tokens,
        "description_tokens": desc_tokens,
        "input_schema_tokens": schema_tokens,
        "structural_tokens": structural,
        "total": name_tokens + desc_tokens + schema_tokens + structural,
    }


def estimate_server_tokens(tools: list[dict[str, Any]]) -> ServerTokens:
    """Estimate the total token cost of the tools exposed by one MCP server.

    Returns aggregate stats plus a per-tool breakdown sorted most expensive first.
    """
    per_tool: list[NamedToolTokens] = []
    for tool in tools:
        breakdown = estimate_tool_tokens(tool)
        per_tool.append({"name": str(tool.get("name") or "<unnamed>"), **breakdown})

    total = sum(t["total"] for t in per_tool)
    return {
        "tool_count": len(per_tool),
        "total_tokens": total,
        "avg_tokens_per_tool": round(total / len(per_tool), 1) if per_tool else 0.0,
        "tools": sorted(per_tool, key=lambda t: t["total"], reverse=True),
    }
