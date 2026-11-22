"""Tests for the progressive tool registry (no MCP SDK needed)."""

from __future__ import annotations

import pytest

from toolforge.core.models import LoadPolicy, ToolProfile
from toolforge.core.registry import ToolLookupError, ToolRegistry
from toolforge.core.toolspec import parse_tools

TOOLS = parse_tools(
    [
        {
            "name": "search",
            "description": "Search things. " * 20,
            "inputSchema": {"type": "object"},
        },
        {"name": "delete_repo", "description": "Delete a repository."},
    ]
)


def test_register_list_get_clear() -> None:
    reg = ToolRegistry()
    result = reg.register(TOOLS, "github")
    assert (result.registered, result.replaced, result.denied) == (2, 0, [])
    assert len(reg) == 2

    listing = reg.list_lightweight()
    assert [e["name"] for e in listing] == ["search", "delete_repo"]
    assert all(set(e) == {"name", "server", "description"} for e in listing)
    assert len(listing[0]["description"]) <= 120

    server, tool = reg.get("search")
    assert server == "github" and tool["inputSchema"] == {"type": "object"}

    assert reg.clear("other") == 0
    assert reg.clear() == 2 and len(reg) == 0


def test_reregistering_replaces() -> None:
    reg = ToolRegistry()
    reg.register(TOOLS, "github")
    assert reg.register(TOOLS[:1], "github").replaced == 1
    assert len(reg) == 2


def test_profile_denies_and_always_loads() -> None:
    profile = ToolProfile(
        name="p", deny=["*:delete_*"], server_policies={"github": LoadPolicy.ALWAYS}
    )
    reg = ToolRegistry(profile)
    result = reg.register(TOOLS, "github")
    assert result.denied == ["delete_repo"]
    assert result.registered == 1

    (entry,) = reg.list_lightweight()
    assert entry["inputSchema"] == {"type": "object"}  # always-load: full definition
    assert entry["description"] == TOOLS[0]["description"]

    with pytest.raises(ToolLookupError, match="not found"):
        reg.get("delete_repo")


def test_ambiguous_and_scoped_lookup() -> None:
    reg = ToolRegistry()
    reg.register(TOOLS, "github")
    reg.register(TOOLS, "gitlab")

    with pytest.raises(ToolLookupError, match=r"several servers \(github, gitlab\)"):
        reg.get("search")
    assert reg.get("search", "gitlab")[0] == "gitlab"
    assert len(reg.list_lightweight("github")) == 2

    with pytest.raises(ToolLookupError, match="registered on: github, gitlab"):
        reg.get("search", "jira")
