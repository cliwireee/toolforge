"""Tests for MCP SDK detection (the mcp 2.x FastMCP removal broke `serve`)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from toolforge.cli.main import app
from toolforge.mcp import _compat
from toolforge.mcp._compat import MCPUnavailableError, _version_tuple, require_mcp


@pytest.mark.parametrize(
    ("text", "expected"),
    [("2.3.0", (2, 3, 0)), ("1.20", (1, 20)), ("2.0.0rc1", (2, 0, 0)), ("1.2.dev3", (1, 2))],
)
def test_version_tuple(text: str, expected: tuple[int, ...]) -> None:
    assert _version_tuple(text) == expected


def test_missing_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_compat.importlib.util, "find_spec", lambda name: None)
    with pytest.raises(MCPUnavailableError, match=r"pip install \"mcp>=1.20,<3\""):
        require_mcp()


@pytest.mark.parametrize("found", ["1.9.4", "1.19.0", "3.0.0"])
def test_unsupported_versions(monkeypatch: pytest.MonkeyPatch, found: str) -> None:
    monkeypatch.setattr(_compat, "installed_version", lambda: found)
    with pytest.raises(MCPUnavailableError, match=f"mcp {found} is installed"):
        require_mcp()


@pytest.mark.parametrize("found", ["1.20.0", "1.30.0", "2.3.0"])
def test_supported_versions(monkeypatch: pytest.MonkeyPatch, found: str) -> None:
    pytest.importorskip("mcp")
    monkeypatch.setattr(_compat, "installed_version", lambda: found)
    assert require_mcp() == found


def test_server_class_matches_installed_major() -> None:
    pytest.importorskip("mcp")
    cls = _compat.server_class()
    major = _version_tuple(_compat.installed_version() or "0")[0]
    assert cls.__name__ == ("MCPServer" if major >= 2 else "FastMCP")


def test_serve_without_sdk_is_a_clean_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    def unavailable() -> None:
        raise MCPUnavailableError("The 'mcp' package is required for this command.")

    monkeypatch.setattr(_compat, "server_class", unavailable)
    import toolforge.mcp.server as server_module

    monkeypatch.setattr(server_module, "server_class", unavailable)
    result = CliRunner().invoke(app, ["serve", "--no-config"])
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
