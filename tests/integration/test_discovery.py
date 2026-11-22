"""Live discovery tests: real stdio servers started as subprocesses."""

from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("mcp")

from click.testing import Result  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

from toolforge.cli.main import app  # noqa: E402
from toolforge.mcp.discovery import (  # noqa: E402
    MCPConfigError,
    StdioServerSpec,
    discover,
    expand_vars,
    list_all_tools,
    load_mcp_config,
    spec_from_command,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"
SRC = Path(__file__).parent.parent.parent / "src"
DEMO = FIXTURES / "demo_server.py"
# Make the demo server importable even without an editable install.
ENV = {"PYTHONPATH": os.pathsep.join(filter(None, [str(SRC), os.environ.get("PYTHONPATH")]))}
try:  # click < 8.2 mixes stderr into stdout unless told otherwise
    runner = CliRunner(mix_stderr=False)  # type: ignore[call-arg,unused-ignore]
except TypeError:  # click >= 8.2 always captures stderr separately
    runner = CliRunner()


def out(result: Result) -> str:
    return result.stdout + (result.stderr or "")


def demo_spec(name: str = "demo") -> StdioServerSpec:
    return StdioServerSpec(name=name, command=sys.executable, args=(str(DEMO),), env=ENV)


def python_spec(name: str, code: str) -> StdioServerSpec:
    return StdioServerSpec(name=name, command=sys.executable, args=("-c", code), env=ENV)


def test_discovers_tools_from_live_server() -> None:
    (result,) = discover([demo_spec()], timeout=60)
    assert result.error is None, result.error
    assert result.tools is not None
    by_name = {t["name"]: t for t in result.tools}
    assert set(by_name) == {"add", "echo", "search_issues"}
    assert by_name["add"]["inputSchema"]["required"] == ["a", "b"]
    assert by_name["echo"]["description"] == "Echo the given text back."


def test_failures_are_isolated_and_explained() -> None:
    results = discover(
        [
            demo_spec(),
            python_spec("crashes", "import sys; print('boom: missing token', file=sys.stderr); "
                        "sys.exit(3)"),
            StdioServerSpec(name="missing", command="definitely-not-a-real-command-xyz"),
            python_spec("hangs", "import time; time.sleep(60)"),
        ],
        timeout=5,
    )
    by_name = {r.spec.name: r for r in results}
    assert by_name["demo"].error is None and by_name["demo"].tools

    crashed = by_name["crashes"].error or ""
    assert "boom: missing token" in crashed  # stderr tail is attached

    assert "definitely-not-a-real-command-xyz" in (by_name["missing"].error or "")
    assert "no tools/list answer within 5s" in (by_name["hangs"].error or "")


async def test_list_all_tools_follows_cursors() -> None:
    pages = {
        None: SimpleNamespace(tools=[{"name": "a"}], next_cursor="p2"),
        "p2": SimpleNamespace(tools=[{"name": "b"}], next_cursor="p3"),
        "p3": SimpleNamespace(tools=[{"name": "c"}], next_cursor="p2"),  # loop guard
    }
    calls: list[Any] = []

    class FakeSession:
        async def list_tools(self, params: Any = None) -> SimpleNamespace:
            cursor = params.cursor if params is not None else None
            calls.append(cursor)
            return pages[cursor]

    tools = await list_all_tools(FakeSession())
    assert [t["name"] for t in tools] == ["a", "b", "c"]
    assert calls == [None, "p2", "p3"]


def test_spec_from_command() -> None:
    spec = spec_from_command('npx -y "@scope/server name" --flag', name="x")
    assert spec.command == "npx"
    assert spec.args == ("-y", "@scope/server name", "--flag")
    with pytest.raises(MCPConfigError, match="empty"):
        spec_from_command("   ")
    with pytest.raises(MCPConfigError, match="Cannot parse"):
        spec_from_command('npx "unterminated')


def test_expand_vars() -> None:
    missing: list[str] = []
    env = {"TOKEN": "abc"}
    assert expand_vars("${TOKEN}-${NOPE:-dflt}-${GONE}", env, missing) == "abc-dflt-"
    assert missing == ["GONE"]


def test_load_mcp_config(tmp_path: Path) -> None:
    config = tmp_path / ".mcp.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "demo": {"command": "python", "args": ["server.py", "${HOME_DIR}"],
                             "env": {"KEY": "${API_KEY:-none}"}},
                    "remote": {"type": "http", "url": "https://example.invalid/mcp"},
                    "sse": {"url": "https://example.invalid/sse"},
                    "off": {"command": "x", "disabled": True},
                    "needs_env": {"command": "x", "env": {"T": "${UNSET_VAR}"}},
                    "bad_args": {"command": "x", "args": "not-a-list"},
                    "no_command": {"args": []},
                    "sub": {"command": "x", "cwd": "pkg"},
                }
            }
        ),
        encoding="utf-8",
    )
    specs, skipped = load_mcp_config(config, environ={"HOME_DIR": "/h"})

    by_name = {s.name: s for s in specs}
    assert set(by_name) == {"demo", "sub"}
    assert by_name["demo"].args == ("server.py", "/h")
    assert by_name["demo"].env == {"KEY": "none"}
    assert by_name["demo"].cwd == str(tmp_path.resolve())
    assert by_name["sub"].cwd == str(tmp_path.resolve() / "pkg")

    reasons = {s.name: (s.is_error, s.reason) for s in skipped}
    assert reasons["remote"][0] is False and "remote server (http)" in reasons["remote"][1]
    assert reasons["sse"][0] is False
    assert reasons["off"] == (False, "disabled in config")
    assert reasons["needs_env"] == (True, "environment variable(s) not set: UNSET_VAR")
    assert reasons["bad_args"][0] is True
    assert reasons["no_command"][0] is True


@pytest.mark.parametrize(
    ("content", "fragment"),
    [("{", "Invalid JSON"), ('{"other": {}}', "'mcpServers'"), ("[]", "'mcpServers'")],
)
def test_load_mcp_config_rejects_bad_files(tmp_path: Path, content: str, fragment: str) -> None:
    config = tmp_path / "mcp.json"
    config.write_text(content, encoding="utf-8")
    with pytest.raises(MCPConfigError, match=fragment):
        load_mcp_config(config)


def test_vscode_servers_key(tmp_path: Path) -> None:
    config = tmp_path / "mcp.json"
    config.write_text(json.dumps({"servers": {"a": {"command": "x"}}}), encoding="utf-8")
    specs, _ = load_mcp_config(config)
    assert [s.name for s in specs] == ["a"]


def test_cli_audit_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYTHONPATH", ENV["PYTHONPATH"])
    command = shlex.join([sys.executable, str(DEMO)])
    result = runner.invoke(app, ["audit", "--command", command, "-s", "demo", "--json"])
    assert result.exit_code == 0, out(result)
    data = json.loads(result.stdout)
    assert data["source"] == "live"
    assert data["server_name"] == "demo"
    assert data["tool_count"] == 3


def test_cli_audit_mcp_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    config = tmp_path / ".mcp.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "demo": {"command": sys.executable, "args": [str(DEMO)], "env": ENV},
                    "broken": {"command": sys.executable, "args": ["-c", "raise SystemExit(2)"]},
                    "remote": {"type": "http", "url": "https://example.invalid/mcp"},
                }
            }
        ),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["audit", "--mcp-config", str(config), "--json", "--timeout", "30"])
    assert result.exit_code == 1  # one server failed
    report = json.loads(result.stdout)
    assert [s["server_name"] for s in report["servers"]] == ["demo"]
    assert report["grand_total_tools"] == 3
    assert any(e.startswith("broken:") for e in report["errors"])
    assert any("remote server (http)" in n for n in report["notes"])


def test_cli_mcp_config_without_stdio_servers(tmp_path: Path) -> None:
    config = tmp_path / "mcp.json"
    config.write_text(json.dumps({"mcpServers": {"r": {"url": "https://x.invalid"}}}),
                      encoding="utf-8")
    result = runner.invoke(app, ["audit", "--mcp-config", str(config)], env={"COLUMNS": "250"})
    assert result.exit_code == 1
    assert "No stdio servers to audit" in out(result)
