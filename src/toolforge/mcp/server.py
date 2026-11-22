"""
Toolforge MCP server – progressive / lazy tool loading.

This server exposes a small set of meta-tools that let an agent:
1. Discover available tools with minimal token cost (names + short descriptions)
2. Request full schemas only when needed
3. Estimate the context cost of a set of tools

Future versions will proxy real upstream MCP servers and implement
true progressive disclosure + code-mode execution.
"""

from __future__ import annotations

import json
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
    _HAS_MCP = True
except ImportError:
    _HAS_MCP = False
    FastMCP = None  # type: ignore

from toolforge.core.tokens import estimate_server_tokens

# In-memory registry of tools the agent has "registered" for progressive access.
_REGISTRY: dict[str, dict[str, Any]] = {}


def _make_server():
    if not _HAS_MCP:
        raise RuntimeError(
            "The 'mcp' package is required to run the Toolforge MCP server.\n"
            "Install it with: pip install mcp\n"
            "Or: pip install toolforge[mcp]  (once published)"
        )

    mcp = FastMCP("toolforge")

    @mcp.tool()
    def register_tools(tools_json: str, server_name: str = "default") -> str:
        """
        Register a list of MCP tool definitions for progressive access.

        Pass a JSON string that is either a list of tool objects or
        {"tools": [...]}. After registration the agent can call
        list_lightweight_tools and get_tool_schema instead of loading
        every full schema into context.
        """
        try:
            data = json.loads(tools_json)
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}"

        if isinstance(data, dict) and "tools" in data:
            tools = data["tools"]
        elif isinstance(data, list):
            tools = data
        else:
            return "Expected a list of tools or an object with a 'tools' key."

        if not isinstance(tools, list):
            return "Tools must be a list."

        count = 0
        for t in tools:
            if not isinstance(t, dict) or "name" not in t:
                continue
            key = f"{server_name}:{t['name']}"
            _REGISTRY[key] = {**t, "_server": server_name}
            count += 1

        return (
            f"Registered {count} tools under server '{server_name}'. "
            f"Total in registry: {len(_REGISTRY)}"
        )

    @mcp.tool()
    def list_lightweight_tools(server_name: str | None = None) -> str:
        """
        Return a compact list of registered tools (name + short description only).

        This is intentionally token-cheap so the agent can see what is available
        without paying the full schema cost.
        """
        items = []
        for key, tool in _REGISTRY.items():
            if server_name and tool.get("_server") != server_name:
                continue
            name = tool.get("name", key)
            desc = (tool.get("description") or "")[:120]
            items.append(
                {"name": name, "server": tool.get("_server"), "description": desc}
            )

        if not items:
            return "No tools registered. Use register_tools first."

        return json.dumps(items, indent=2)

    @mcp.tool()
    def get_tool_schema(tool_name: str, server_name: str = "default") -> str:
        """
        Return the full schema for a single tool.

        Call this only for tools you actually intend to use. Prefer
        list_lightweight_tools for discovery.
        """
        key = f"{server_name}:{tool_name}"
        tool = _REGISTRY.get(key)
        if tool is None:
            matches = [t for t in _REGISTRY.values() if t.get("name") == tool_name]
            if not matches:
                return f"Tool '{tool_name}' not found in registry."
            tool = matches[0]

        clean = {k: v for k, v in tool.items() if not k.startswith("_")}
        return json.dumps(clean, indent=2)

    @mcp.tool()
    def estimate_context_cost(tools_json: str | None = None) -> str:
        """
        Estimate the token cost of a set of tool definitions.

        If tools_json is omitted, estimates the cost of everything currently
        in the registry.
        """
        if tools_json:
            try:
                data = json.loads(tools_json)
                tools = data.get("tools", data) if isinstance(data, dict) else data
            except json.JSONDecodeError as e:
                return f"Invalid JSON: {e}"
        else:
            tools = [
                {k: v for k, v in t.items() if not k.startswith("_")}
                for t in _REGISTRY.values()
            ]

        if not tools:
            return "No tools to estimate."

        stats = estimate_server_tokens(tools)
        top = stats["tools"][:10]

        report = {
            "tool_count": stats["tool_count"],
            "total_tokens": stats["total_tokens"],
            "avg_tokens_per_tool": stats["avg_tokens_per_tool"],
            "top_expensive": [
                {"name": t["name"], "tokens": t["total"]} for t in top
            ],
            "advice": (
                "High cost – prefer progressive loading."
                if stats["total_tokens"] > 15_000
                else "Reasonable cost for full loading."
            ),
        }
        return json.dumps(report, indent=2)

    @mcp.tool()
    def clear_registry() -> str:
        """Clear all registered tools from the progressive registry."""
        n = len(_REGISTRY)
        _REGISTRY.clear()
        return f"Cleared {n} tools from the registry."

    return mcp


def main() -> None:
    server = _make_server()
    server.run()


if __name__ == "__main__":
    main()
