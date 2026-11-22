"""Compatibility layer over the MCP Python SDK (supported: mcp >= 1.20, < 3).

mcp 2.x renamed ``mcp.server.fastmcp.FastMCP`` to ``mcp.server.mcpserver.MCPServer``.
Both classes share the API Toolforge uses (constructor ``name`` and
``instructions``, ``add_tool``, ``run``), so this module only picks the class.
SDK objects are typed as ``Any`` on purpose: their types differ between majors.
"""

from __future__ import annotations

import importlib
import importlib.util
import re
from importlib.metadata import PackageNotFoundError, version
from typing import Any

MIN_VERSION = (1, 20)
MAX_MAJOR_EXCLUSIVE = 3
INSTALL_HINT = 'pip install "mcp>=1.20,<3"'


class MCPUnavailableError(RuntimeError):
    """The MCP SDK is missing or is a version Toolforge does not support."""


def installed_version() -> str | None:
    try:
        return version("mcp")
    except PackageNotFoundError:
        return None


def _version_tuple(text: str) -> tuple[int, ...]:
    """Leading numeric release parts: "2.0.0rc1" -> (2, 0, 0), "1.2.dev3" -> (1, 2)."""
    parts: list[int] = []
    for piece in text.split("."):
        match = re.match(r"\d+", piece)
        if match is None:
            break
        parts.append(int(match.group()))
        if match.end() != len(piece):  # pre-release suffix such as "0rc1"
            break
    return tuple(parts)


def require_mcp() -> str:
    """Return the installed SDK version, or raise :class:`MCPUnavailableError`."""
    if importlib.util.find_spec("mcp") is None:
        raise MCPUnavailableError(
            f"The 'mcp' package is required for this command. Install it with: {INSTALL_HINT}"
        )
    found = installed_version() or "unknown"
    parsed = _version_tuple(found)
    if parsed and (parsed < MIN_VERSION or parsed[0] >= MAX_MAJOR_EXCLUSIVE):
        raise MCPUnavailableError(
            f"mcp {found} is installed, but Toolforge supports mcp >=1.20,<3. "
            f"Fix it with: {INSTALL_HINT}"
        )
    return found


def server_class() -> Any:
    """Return ``MCPServer`` (mcp 2.x) or ``FastMCP`` (mcp 1.x)."""
    found = require_mcp()
    for module_name, attr in (
        ("mcp.server.mcpserver", "MCPServer"),  # mcp >= 2
        ("mcp.server.fastmcp", "FastMCP"),  # mcp 1.x
    ):
        try:
            return getattr(importlib.import_module(module_name), attr)
        except (ImportError, AttributeError):
            continue
    raise MCPUnavailableError(
        f"mcp {found} is installed but provides neither MCPServer nor FastMCP. "
        f"Fix it with: {INSTALL_HINT}"
    )
