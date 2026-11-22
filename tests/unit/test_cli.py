"""CLI tests (typer CliRunner, offline tokenizer)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import Result
from typer.testing import CliRunner

from toolforge import __version__
from toolforge.cli.main import app
from toolforge.core import tokens
from toolforge.core.tokens import TokenizerUnavailableError

try:  # click < 8.2 mixes stderr into stdout unless told otherwise
    runner = CliRunner(mix_stderr=False)  # type: ignore[call-arg,unused-ignore]
except TypeError:  # click >= 8.2 always captures stderr separately
    runner = CliRunner()
WIDE = {"COLUMNS": "250"}


def out(result: Result) -> str:
    """Everything the user saw: stdout followed by stderr."""
    return result.stdout + (result.stderr or "")


def text(output: str) -> str:
    """Collapse whitespace so assertions do not depend on terminal wrapping."""
    return " ".join(output.split())


@pytest.fixture(autouse=True)
def in_tmp_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_version_flag_without_command() -> None:
    """Regression: `toolforge --version` used to fail with 'Missing command'."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0, out(result)
    assert result.stdout.strip() == f"toolforge {__version__}"


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_audit_requires_a_source() -> None:
    result = runner.invoke(app, ["audit"], env=WIDE)
    assert result.exit_code == 1
    assert "Nothing to audit" in out(result)


def test_audit_rejects_multiple_sources(sample_tools_file: Path) -> None:
    result = runner.invoke(
        app, ["audit", "--tools", str(sample_tools_file), "--command", "x"], env=WIDE
    )
    assert result.exit_code == 1
    assert "Use only one of" in text(out(result))


def test_audit_table_and_top(sample_tools_file: Path) -> None:
    result = runner.invoke(
        app, ["audit", "--tools", str(sample_tools_file), "-s", "github"], env=WIDE
    )
    assert result.exit_code == 0, out(result)
    shown = text(out(result))
    assert "Top 4 most expensive tools" in shown
    assert "With profile" in shown and "Policy" in shown
    assert "cl100k_base" in shown

    args = ["audit", "--tools", str(sample_tools_file), "--top"]
    result = runner.invoke(app, [*args, "2"], env=WIDE)
    assert result.exit_code == 0
    assert "Top 2 most expensive tools" in text(out(result))

    result = runner.invoke(app, [*args, "0"], env=WIDE)
    assert result.exit_code == 0
    assert "most expensive tools" not in out(result)


def test_audit_json(sample_tools_file: Path) -> None:
    result = runner.invoke(app, ["audit", "--tools", str(sample_tools_file), "--json"])
    assert result.exit_code == 0, out(result)
    data = json.loads(result.stdout)
    assert data["source"] == "file"
    assert data["server_name"] == "local"
    assert data["tool_count"] == 4
    assert {t["policy"] for t in data["tools"]} == {"lazy"}
    assert data["projected_tokens"] < data["total_tokens"]


@pytest.mark.parametrize(
    ("content", "fragment"),
    [
        ('["oops", 5]', "tools[0]: expected an object, got str"),
        ('{"tools": "nope"}', "expected a list of tools, got str"),
        ("[{", "invalid JSON"),
    ],
)
def test_audit_bad_input_is_a_clean_error(tmp_path: Path, content: str, fragment: str) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(content, encoding="utf-8")
    result = runner.invoke(app, ["audit", "--tools", str(bad)], env=WIDE)
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)  # no traceback
    assert fragment in text(out(result))


def test_markup_in_names_is_not_interpreted(tmp_path: Path) -> None:
    tools = tmp_path / "t.json"
    tools.write_text(json.dumps([{"name": "[bold]sneaky[/bold]"}]), encoding="utf-8")
    result = runner.invoke(app, ["audit", "--tools", str(tools), "-s", "[red]srv"], env=WIDE)
    assert result.exit_code == 0, out(result)
    assert "[bold]sneaky[/bold]" in out(result)
    assert "[red]srv" in out(result)


def test_audit_uses_project_config(sample_tools_file: Path, in_tmp_cwd: Path) -> None:
    (in_tmp_cwd / ".toolforge.toml").write_text(
        '[profiles.default]\ndeny = ["*:delete_*"]\n'
        '[profiles.default.server_policies]\ngithub = "always"\n',
        encoding="utf-8",
    )
    result = runner.invoke(
        app, ["audit", "--tools", str(sample_tools_file), "-s", "github", "--json"]
    )
    assert result.exit_code == 0, out(result)
    policies = {t["name"]: t["policy"] for t in json.loads(result.stdout)["tools"]}
    assert policies["delete_branch"] == "deny"
    assert policies["search_issues"] == "always"


def test_invalid_config_is_reported(sample_tools_file: Path, in_tmp_cwd: Path) -> None:
    (in_tmp_cwd / ".toolforge.toml").write_text(
        '[profiles.default]\ndefault_policy = "bogus"\n', encoding="utf-8"
    )
    result = runner.invoke(app, ["audit", "--tools", str(sample_tools_file)], env=WIDE)
    assert result.exit_code == 1
    assert "profiles.default.default_policy" in text(out(result))

    # --no-config ignores the broken file
    result = runner.invoke(app, ["audit", "--tools", str(sample_tools_file), "--no-config"])
    assert result.exit_code == 0, out(result)


def test_unknown_profile(sample_tools_file: Path) -> None:
    result = runner.invoke(
        app, ["audit", "--tools", str(sample_tools_file), "--profile", "nope"], env=WIDE
    )
    assert result.exit_code == 1
    assert "Profile 'nope' is not defined" in text(out(result))


def test_tokenizer_unavailable_is_a_clean_error(
    sample_tools_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable() -> None:
        raise TokenizerUnavailableError("Could not load the 'cl100k_base' tokenizer vocabulary")

    monkeypatch.setattr(tokens, "get_encoding", unavailable)
    result = runner.invoke(app, ["audit", "--tools", str(sample_tools_file)], env=WIDE)
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "tokenizer vocabulary" in out(result)


def test_init_creates_valid_config_and_respects_force(
    in_tmp_cwd: Path, sample_tools_file: Path
) -> None:
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, out(result)
    config = in_tmp_cwd / ".toolforge.toml"
    assert config.is_file()

    result = runner.invoke(app, ["init"], env=WIDE)
    assert result.exit_code == 1
    assert "already exists" in out(result)

    config.write_text("# custom\n", encoding="utf-8")
    result = runner.invoke(app, ["init", "--force"])
    assert result.exit_code == 0
    assert "active_profile" in config.read_text(encoding="utf-8")

    # The generated file is accepted by the audit's config loader.
    result = runner.invoke(app, ["audit", "--tools", str(sample_tools_file)])
    assert result.exit_code == 0, out(result)


def test_serve_reports_config_errors_on_stderr(in_tmp_cwd: Path) -> None:
    (in_tmp_cwd / ".toolforge.toml").write_text("broken = [", encoding="utf-8")
    result = runner.invoke(app, ["serve"], env=WIDE)
    assert result.exit_code == 1
    assert result.stdout == ""  # stdout is reserved for the MCP protocol
    assert "Invalid TOML" in out(result)
