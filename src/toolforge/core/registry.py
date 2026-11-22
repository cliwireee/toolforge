"""In-memory registry behind the progressive MCP server.

Kept free of any MCP SDK imports so the logic is testable on its own.
The registry lives for the lifetime of the server process; it is not persisted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from toolforge.core.models import LoadPolicy, ToolProfile
from toolforge.core.policy import resolve_policy
from toolforge.core.toolspec import lightweight_entry


class ToolLookupError(LookupError):
    """A tool could not be resolved unambiguously."""


@dataclass
class RegisterResult:
    server: str
    registered: int = 0
    replaced: int = 0
    denied: list[str] = field(default_factory=list)


class ToolRegistry:
    """Tools registered for progressive disclosure, keyed by (server, tool name)."""

    def __init__(self, profile: ToolProfile | None = None) -> None:
        self.profile = profile
        self._tools: dict[tuple[str, str], dict[str, Any]] = {}

    def __len__(self) -> int:
        return len(self._tools)

    def policy_for(self, server: str, tool: str) -> LoadPolicy:
        if self.profile is None:
            return LoadPolicy.LAZY
        return resolve_policy(self.profile, server, tool)

    def register(self, tools: list[dict[str, Any]], server: str) -> RegisterResult:
        """Register validated tool definitions. Tools denied by the profile are skipped."""
        result = RegisterResult(server=server)
        for tool in tools:
            name = tool["name"]
            if self.policy_for(server, name) is LoadPolicy.DENY:
                result.denied.append(name)
                continue
            key = (server, name)
            if key in self._tools:
                result.replaced += 1
            self._tools[key] = dict(tool)
            result.registered += 1
        return result

    def items(self, server: str | None = None) -> list[tuple[str, dict[str, Any]]]:
        """(server, tool) pairs in registration order, optionally for one server."""
        return [(s, t) for (s, _), t in self._tools.items() if server is None or s == server]

    def list_lightweight(self, server: str | None = None) -> list[dict[str, Any]]:
        """Cheap listing: lazy tools as name + short description, always-load tools in full."""
        entries = []
        for srv, tool in self.items(server):
            entry = lightweight_entry(tool, srv)
            if self.policy_for(srv, tool["name"]) is LoadPolicy.ALWAYS:
                entry["description"] = tool.get("description", "")
                entry["inputSchema"] = tool.get("inputSchema", {})
            entries.append(entry)
        return entries

    def get(self, tool_name: str, server: str | None = None) -> tuple[str, dict[str, Any]]:
        """Resolve a tool by name, optionally scoped to a server.

        Raises :class:`ToolLookupError` when the tool is unknown, or when the
        name exists on several servers and no server was given.
        """
        if server is not None:
            tool = self._tools.get((server, tool_name))
            if tool is not None:
                return server, tool
            elsewhere = [s for (s, n) in self._tools if n == tool_name]
            hint = f" It is registered on: {', '.join(elsewhere)}." if elsewhere else ""
            raise ToolLookupError(
                f"Tool '{tool_name}' is not registered on server '{server}'.{hint}"
            )

        matches = [(s, t) for (s, n), t in self._tools.items() if n == tool_name]
        if not matches:
            raise ToolLookupError(
                f"Tool '{tool_name}' not found in registry. Use list_lightweight_tools to see "
                "what is available."
            )
        if len(matches) > 1:
            servers = ", ".join(s for s, _ in matches)
            raise ToolLookupError(
                f"Tool '{tool_name}' exists on several servers ({servers}); pass server_name."
            )
        return matches[0]

    def clear(self, server: str | None = None) -> int:
        """Remove all tools (or one server's tools); return how many were removed."""
        keys = [k for k in self._tools if server is None or k[0] == server]
        for k in keys:
            del self._tools[k]
        return len(keys)
