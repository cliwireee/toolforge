"""Toolforge CLI entrypoint."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer
from rich.console import Console
from rich.markup import escape

from toolforge import __version__
from toolforge.core.audit import (
    DEFAULT_TOP_N,
    PROJECTION_NOTE,
    TOKENIZER_NOTE,
    audit_tools,
    print_report,
)
from toolforge.core.models import AuditReport, ServerAudit, ToolProfile
from toolforge.core.tokens import TokenizerUnavailableError
from toolforge.core.toolspec import ToolDefinitionError, load_tools_file
from toolforge.mcp._compat import MCPUnavailableError, require_mcp
from toolforge.mcp.discovery import (
    DEFAULT_TIMEOUT,
    DiscoveryResult,
    MCPConfigError,
    SkippedServer,
    StdioServerSpec,
    discover,
    load_mcp_config,
    spec_from_command,
)
from toolforge.utils.config import PROJECT_CONFIG_NAME, ConfigError, load_config, select_profile

app = typer.Typer(
    name="toolforge",
    help="Progressive MCP tooling that keeps your context lean.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
# Errors and progress go to stderr: stdout carries --json output and, for
# `serve`, the MCP protocol itself.
err_console = Console(stderr=True)

STARTER_CONFIG = """\
# Toolforge configuration
# https://github.com/cliwireee/toolforge

active_profile = "default"

[profiles.default]
description = "Balanced progressive loading"
# Policy for tools not matched below: "lazy", "always", "code_mode" or "deny".
default_policy = "lazy"
# Warn when tools with policy "always" cost more than this many tokens.
max_always_load_tokens = 8000

# Patterns: "tool", "server:tool" or "server:*"; wildcards such as "*:delete_*" work.
# deny wins over everything; a non-empty allow list hides every tool it does not match.
# allow = []
# deny = ["*:delete_*"]

# Per-server policies (override default_policy)
# [profiles.default.server_policies]
# github = "lazy"
# filesystem = "always"
"""


def _fail(message: str, code: int = 1) -> NoReturn:
    err_console.print(f"[red]Error:[/red] {escape(message)}")
    raise typer.Exit(code=code)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"toolforge {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            help="Show version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    pass


def _load_profile(name: str | None, no_config: bool) -> tuple[ToolProfile, str]:
    """Return the profile to apply and a human-readable description of its source."""
    if no_config:
        if name:
            _fail("--profile cannot be combined with --no-config.")
        return ToolProfile(name="default"), "built-in defaults"
    try:
        config = load_config()
        profile = select_profile(config, name)
    except ConfigError as exc:
        _fail(str(exc))
    if config.source_path is None:
        return profile, "built-in defaults"
    source = Path(config.source_path)
    if source.is_relative_to(Path.cwd()):
        source = source.relative_to(Path.cwd())
    return profile, str(source)


def _live_specs(
    command: str | None, mcp_config: Path | None, server_name: str
) -> tuple[list[StdioServerSpec], list[SkippedServer]]:
    try:
        if command is not None:
            return [spec_from_command(command, name=server_name)], []
        assert mcp_config is not None
        specs, skipped = load_mcp_config(mcp_config)
    except MCPConfigError as exc:
        _fail(str(exc))
    if not specs and not any(s.is_error for s in skipped):
        reasons = "".join(f"\n  - {s.name}: {s.reason}" for s in skipped)
        _fail(f"No stdio servers to audit in {mcp_config}.{reasons}")
    return specs, skipped


def _run_discovery(
    specs: list[StdioServerSpec], timeout: float, quiet: bool
) -> list[DiscoveryResult]:
    if not specs:
        return []
    try:
        require_mcp()
    except MCPUnavailableError as exc:
        _fail(str(exc))
    if quiet or not err_console.is_terminal:
        return discover(specs, timeout=timeout)
    with err_console.status(f"Starting {len(specs)} MCP server(s) and reading tools/list…"):
        return discover(specs, timeout=timeout)


@app.command()
def audit(
    tools_file: Annotated[
        Path | None,
        typer.Option(
            "--tools",
            "-t",
            help="JSON file of tool definitions: a list or an object with a 'tools' list "
            "(MCP, Anthropic or OpenAI format).",
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    command: Annotated[
        str | None,
        typer.Option(
            "--command",
            "-c",
            help="Start a stdio MCP server with this command line and audit its live tools.",
        ),
    ] = None,
    mcp_config: Annotated[
        Path | None,
        typer.Option(
            "--mcp-config",
            help="Audit every stdio server in an MCP client config "
            "(.mcp.json, Cursor mcp.json, claude_desktop_config.json).",
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    server_name: Annotated[
        str,
        typer.Option(
            "--server", "-s", help="Server name for the report (with --tools / --command)."
        ),
    ] = "local",
    top: Annotated[
        int, typer.Option("--top", min=0, help="How many expensive tools to show per server.")
    ] = DEFAULT_TOP_N,
    json_output: Annotated[
        bool, typer.Option("--json", help="Emit machine-readable JSON instead of tables.")
    ] = False,
    profile_name: Annotated[
        str | None,
        typer.Option(
            "--profile", "-p", help="Config profile for the 'with profile' projection."
        ),
    ] = None,
    no_config: Annotated[
        bool,
        typer.Option("--no-config", help=f"Ignore {PROJECT_CONFIG_NAME} and the user config."),
    ] = False,
    timeout: Annotated[
        float, typer.Option("--timeout", min=1.0, help="Seconds to wait for each live server.")
    ] = DEFAULT_TIMEOUT,
) -> None:
    """
    Estimate the token cost of MCP tool definitions.

    Read tools from a JSON file (--tools), from a live stdio server
    (--command), or from every server in an MCP client config (--mcp-config).
    """
    chosen = [opt for opt, value in (("--tools", tools_file), ("--command", command),
                                     ("--mcp-config", mcp_config)) if value is not None]
    if not chosen:
        err_console.print(
            "[yellow]Nothing to audit.[/yellow] Pass one of:\n"
            "  toolforge audit --tools my-tools.json\n"
            '  toolforge audit --command "npx -y @modelcontextprotocol/server-everything"\n'
            "  toolforge audit --mcp-config .mcp.json"
        )
        raise typer.Exit(code=1)
    if len(chosen) > 1:
        _fail(f"Use only one of --tools, --command or --mcp-config (got {', '.join(chosen)}).")

    profile, profile_source = _load_profile(profile_name, no_config)

    collected: list[tuple[str, str, list[dict[str, Any]]]] = []  # (server, source, tools)
    errors: list[str] = []
    notes = [TOKENIZER_NOTE, PROJECTION_NOTE, f"Profile '{profile.name}' from {profile_source}."]

    if tools_file is not None:
        try:
            collected.append((server_name, "file", load_tools_file(tools_file)))
        except ToolDefinitionError as exc:
            _fail(str(exc))
    else:
        specs, skipped = _live_specs(command, mcp_config, server_name)
        for skip in skipped:
            (errors if skip.is_error else notes).append(f"{skip.name}: {skip.reason}")
        for result in _run_discovery(specs, timeout, quiet=json_output):
            if result.error is not None:
                errors.append(f"{result.spec.name}: {result.error}")
            else:
                collected.append((result.spec.name, "live", result.tools or []))

    try:
        audits = [
            audit_tools(tools, name, source=source, profile=profile)
            for name, source, tools in collected
        ]
    except TokenizerUnavailableError as exc:
        _fail(str(exc))

    report = AuditReport.from_servers(
        audits, notes=notes, profile_name=profile.name, errors=errors
    )

    if json_output:
        # Single-server modes keep the ServerAudit shape; --mcp-config (or any
        # failure) emits the full AuditReport.
        payload: ServerAudit | AuditReport = (
            audits[0] if len(audits) == 1 and mcp_config is None and not errors else report
        )
        typer.echo(payload.model_dump_json(indent=2))
    else:
        print_report(report, top_n=top)

    if errors:
        raise typer.Exit(code=1)


@app.command()
def version() -> None:
    """Show the installed version."""
    console.print(f"toolforge {__version__}")


@app.command()
def init(
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite existing config if present.")
    ] = False,
) -> None:
    """
    Create a starter Toolforge configuration in the current directory.
    """
    config_path = Path(PROJECT_CONFIG_NAME)
    if config_path.exists() and not force:
        _fail(f"{config_path} already exists. Use --force to overwrite.")

    config_path.write_text(STARTER_CONFIG, encoding="utf-8")
    console.print(f"[green]Created[/green] {config_path}")
    console.print("Edit the file to define profiles and policies, then run `toolforge audit`.")


@app.command()
def serve(
    profile_name: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Config profile whose allow/deny rules apply."),
    ] = None,
    no_config: Annotated[
        bool,
        typer.Option("--no-config", help=f"Ignore {PROJECT_CONFIG_NAME} and the user config."),
    ] = False,
) -> None:
    """
    Start Toolforge as an MCP server over stdio (progressive tool loading).

    Register it in your MCP client config (Claude Code .mcp.json, Cursor
    mcp.json) with command "toolforge" and args ["serve"].
    """
    from toolforge.mcp.server import build_server

    profile, _ = _load_profile(profile_name, no_config)
    try:
        server = build_server(profile)
    except MCPUnavailableError as exc:
        _fail(str(exc))
    server.run()


if __name__ == "__main__":
    app()
