"""
Toolforge MCP server – progressive / lazy tool loading.

This server exposes a small set of meta-tools that let an agent:
1. Discover available tools with minimal token cost (names + short descriptions)
2. Request full schemas only when needed
3. Estimate the context cost of a set of tools

The registry is in memory and lasts for the lifetime of the server process.
Future versions will proxy real upstream MCP servers and implement
true progressive disclosure + code-mode execution.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Annotated, Any

from pydantic import Field

from toolforge.core.models import HIGH_SERVER_TOKENS, ToolProfile
from toolforge.core.registry import ToolLookupError, ToolRegistry
from toolforge.core.tokens import TokenizerUnavailableError, estimate_server_tokens
from toolforge.core.toolspec import ToolDefinitionError, parse_tools, parse_tools_json
from toolforge.mcp._compat import server_class

INSTRUCTIONS = (
    "Progressive tool loading: register_tools once, browse with list_lightweight_tools, "
    "then fetch full schemas with get_tool_schema only for tools you will call."
)

# Accept JSON text *or* the decoded structure. The MCP SDK json-decodes string
# arguments for any parameter not typed exactly `str`, and agents often send a
# real array anyway, so a plain `str | None` parameter rejects valid input.
ToolsInput = Annotated[
    str | list[Any] | dict[str, Any],
    Field(description='Tool definitions: a list or {"tools": [...]}, as JSON or JSON text.'),
]


def _compact(obj: Any) -> str:
    # Compact JSON: responses land in the model's context, so whitespace costs tokens.
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def _parse_input(value: str | list[Any] | dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(value, str):
        return parse_tools_json(value, source="tools_json")
    return parse_tools(value, source="tools_json")


def build_tools(registry: ToolRegistry) -> list[tuple[Callable[..., str], str]]:
    """Return the meta-tool functions bound to ``registry``, with their descriptions."""

    def register_tools(tools_json: ToolsInput, server_name: str = "default") -> str:
        try:
            tools = _parse_input(tools_json)
        except ToolDefinitionError as exc:
            return f"Nothing registered. {exc}"
        result = registry.register(tools, server_name)
        parts = [f"Registered {result.registered} tools under server '{server_name}'."]
        if result.replaced:
            parts.append(f"{result.replaced} replaced earlier definitions.")
        if result.denied:
            denied = ", ".join(result.denied)
            parts.append(f"Skipped {len(result.denied)} denied by profile: {denied}.")
        parts.append(f"Total in registry: {len(registry)}")
        return " ".join(parts)

    def list_lightweight_tools(server_name: str | None = None) -> str:
        items = registry.list_lightweight(server_name)
        if not items:
            if server_name:
                return f"No tools registered for server '{server_name}'."
            return "No tools registered. Use register_tools first."
        return _compact(items)

    def get_tool_schema(tool_name: str, server_name: str | None = None) -> str:
        try:
            server, tool = registry.get(tool_name, server_name)
        except ToolLookupError as exc:
            return str(exc)
        return _compact({**tool, "server": server})

    def estimate_context_cost(tools_json: ToolsInput | None = None) -> str:
        if tools_json is None or tools_json == "":
            tools = [tool for _, tool in registry.items()]
        else:
            try:
                tools = _parse_input(tools_json)
            except ToolDefinitionError as exc:
                return str(exc)
        if not tools:
            return "No tools to estimate."

        try:
            stats = estimate_server_tokens(tools)
        except TokenizerUnavailableError as exc:
            return str(exc)
        report = {
            "tool_count": stats["tool_count"],
            "total_tokens": stats["total_tokens"],
            "avg_tokens_per_tool": stats["avg_tokens_per_tool"],
            "top_expensive": [
                {"name": t["name"], "tokens": t["total"]} for t in stats["tools"][:10]
            ],
            "advice": (
                "High cost – prefer progressive loading."
                if stats["total_tokens"] > HIGH_SERVER_TOKENS
                else "Reasonable cost for full loading."
            ),
            "note": "Estimates (cl100k_base); Claude's tokenizer differs.",
        }
        return _compact(report)

    def clear_registry(server_name: str | None = None) -> str:
        removed = registry.clear(server_name)
        scope = f" for server '{server_name}'" if server_name else ""
        return f"Cleared {removed} tools from the registry{scope}."

    return [
        (
            register_tools,
            "Register MCP tool definitions for progressive access. Afterwards use "
            "list_lightweight_tools and get_tool_schema instead of loading every full schema.",
        ),
        (
            list_lightweight_tools,
            "List registered tools as name + short description (token-cheap). "
            "Optionally filter by server_name.",
        ),
        (
            get_tool_schema,
            "Return the full definition of one registered tool. Pass server_name if the "
            "name exists on several servers.",
        ),
        (
            estimate_context_cost,
            "Estimate the token cost of tool definitions (tools_json), or of the whole "
            "registry if omitted.",
        ),
        (
            clear_registry,
            "Remove all registered tools, or only those of server_name.",
        ),
    ]


def build_server(profile: ToolProfile | None = None, registry: ToolRegistry | None = None) -> Any:
    """Create the MCP server object (``MCPServer`` on mcp 2.x, ``FastMCP`` on 1.x)."""
    cls = server_class()
    server = cls("toolforge", instructions=INSTRUCTIONS)
    for fn, description in build_tools(registry or ToolRegistry(profile)):
        # structured_output=False keeps the tool definitions free of output schemas,
        # which would add tokens to every agent that loads this server.
        server.add_tool(fn, description=description, structured_output=False)
    return server


def main(profile: ToolProfile | None = None) -> None:
    build_server(profile).run()


if __name__ == "__main__":
    main()
