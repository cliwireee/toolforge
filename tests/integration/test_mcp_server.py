"""Server tests against the installed MCP SDK (1.x FastMCP or 2.x MCPServer)."""

from __future__ import annotations

import json
from typing import Any

import pytest

pytest.importorskip("mcp")

from toolforge.core.models import ToolProfile  # noqa: E402
from toolforge.mcp.server import build_server  # noqa: E402

EXPECTED = {
    "register_tools",
    "list_lightweight_tools",
    "get_tool_schema",
    "estimate_context_cost",
    "clear_registry",
}


def result_text(result: Any) -> str:
    """Text of a call_tool result (mcp 2.x: CallToolResult; 1.x: list of content blocks)."""
    content = getattr(result, "content", result)
    if isinstance(content, tuple):  # some 1.x versions return (content, structured)
        content = content[0]
    return "".join(getattr(block, "text", "") for block in content)


async def call(server: Any, name: str, **arguments: Any) -> str:
    return result_text(await server.call_tool(name, arguments))


async def test_exposes_lean_meta_tools() -> None:
    server = build_server()
    tools = await server.list_tools()
    assert {t.name for t in tools} == EXPECTED
    for tool in tools:
        dumped = tool.model_dump(by_alias=True, exclude_none=True)
        assert "outputSchema" not in dumped  # structured_output=False keeps them lean
        assert dumped["description"] and "\n" not in dumped["description"]


async def test_register_list_get_roundtrip() -> None:
    server = build_server()
    tools = [
        {"name": "search", "description": "Search. " * 40, "inputSchema": {"type": "object"}},
        {"name": "read", "description": "Read a file."},
    ]
    out = await call(server, "register_tools", tools_json=json.dumps(tools), server_name="gh")
    assert "Registered 2 tools under server 'gh'" in out

    listing = json.loads(await call(server, "list_lightweight_tools"))
    assert [e["name"] for e in listing] == ["search", "read"]
    assert len(listing[0]["description"]) <= 120

    schema = json.loads(await call(server, "get_tool_schema", tool_name="search"))
    assert schema["inputSchema"] == {"type": "object"} and schema["server"] == "gh"

    estimate = json.loads(await call(server, "estimate_context_cost"))
    assert estimate["tool_count"] == 2 and estimate["total_tokens"] > 0

    assert "Cleared 2 tools" in await call(server, "clear_registry")
    assert "No tools registered" in await call(server, "list_lightweight_tools")


@pytest.mark.parametrize("as_text", [True, False])
async def test_estimate_accepts_json_text_and_structures(as_text: bool) -> None:
    """Regression: the SDK json-decodes string args for `str | None` params, so the
    original estimate_context_cost(tools_json=...) rejected every real input."""
    server = build_server()
    tools: list[dict[str, Any]] = [{"name": "a", "description": "A tool."}, {"name": "b"}]
    arg: Any = json.dumps(tools) if as_text else tools
    estimate = json.loads(await call(server, "estimate_context_cost", tools_json=arg))
    assert estimate["tool_count"] == 2

    out = await call(server, "register_tools", tools_json={"tools": tools}, server_name="s")
    assert "Registered 2 tools" in out


async def test_invalid_input_is_reported_to_the_agent() -> None:
    server = build_server()
    out = await call(server, "register_tools", tools_json='["oops"]')
    assert out.startswith("Nothing registered.")
    assert "tools[0]: expected an object" in out

    out = await call(server, "estimate_context_cost", tools_json='{"not": "tools"}')
    assert "object with a 'tools' key" in out


async def test_profile_rules_apply_to_server() -> None:
    server = build_server(ToolProfile(name="p", deny=["*:delete_*"]))
    tools = [{"name": "delete_repo"}, {"name": "search"}]
    out = await call(server, "register_tools", tools_json=json.dumps(tools), server_name="gh")
    assert "Skipped 1 denied by profile: delete_repo" in out
    assert "not found" in await call(server, "get_tool_schema", tool_name="delete_repo")
