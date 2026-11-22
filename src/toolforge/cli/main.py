"""Toolforge CLI entrypoint."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from toolforge import __version__
from toolforge.core.audit import audit_tools, load_tools_from_json, print_report
from toolforge.core.models import AuditReport

app = typer.Typer(
    name="toolforge",
    help="Progressive MCP tooling that keeps your context lean.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit."),
) -> None:
    if version:
        console.print(f"toolforge {__version__}")
        raise typer.Exit()


@app.command()
def audit(
    tools_file: Optional[Path] = typer.Option(
        None,
        "--tools",
        "-t",
        help="JSON file containing a list of MCP tool definitions (or {'tools': [...]}).",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
    server_name: str = typer.Option("local", "--server", "-s", help="Name to use for this server in the report."),
    top: int = typer.Option(15, "--top", help="How many expensive tools to show."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON instead of a table."),
) -> None:
    """
    Measure the token cost of MCP tool definitions.

    You can pass a JSON file of tools (useful for offline analysis or CI),
    or later versions will auto-discover running MCP servers.
    """
    if tools_file is None:
        console.print(
            "[yellow]No --tools file provided.[/yellow]\n"
            "Example:\n"
            "  toolforge audit --tools my-tools.json\n\n"
            "Tip: In Claude Code you can dump current tools with the tool inspector "
            "or by asking the agent to write them to a file."
        )
        raise typer.Exit(code=1)

    try:
        tools = load_tools_from_json(tools_file)
    except Exception as e:
        console.print(f"[red]Failed to load tools:[/red] {e}")
        raise typer.Exit(code=1)

    server_audit = audit_tools(tools, server_name=server_name)

    if json_output:
        console.print_json(server_audit.model_dump_json(indent=2))
        return

    report = AuditReport(
        servers=[server_audit],
        grand_total_tokens=server_audit.total_tokens,
        grand_total_tools=server_audit.tool_count,
        notes=[
            "Token counts use cl100k_base (Claude / GPT-4 family).",
            "Real context cost can be slightly higher due to surrounding JSON structure.",
        ],
    )
    print_report(report)


@app.command()
def version() -> None:
    """Show the installed version."""
    console.print(f"toolforge {__version__}")


@app.command()
def init(
    force: bool = typer.Option(False, "--force", help="Overwrite existing config if present."),
) -> None:
    """
    Create a starter Toolforge configuration in the current directory.
    """
    config_path = Path(".toolforge.toml")
    if config_path.exists() and not force:
        console.print(f"[yellow]{config_path} already exists. Use --force to overwrite.[/yellow]")
        raise typer.Exit(code=1)

    starter = '''# Toolforge configuration
# https://github.com/cliwireee/toolforge

active_profile = "default"

[profiles.default]
description = "Balanced progressive loading"
default_policy = "lazy"
max_always_load_tokens = 8000

# Explicit allow / deny (tool names or "server_name:*")
# allow = []
# deny = []

# Per-server overrides
# [profiles.default.server_policies]
# github = "lazy"
# filesystem = "always"
'''
    config_path.write_text(starter, encoding="utf-8")
    console.print(f"[green]Created[/green] {config_path}")
    console.print("Edit the file to define profiles and policies, then run `toolforge audit`.")


@app.command()
def serve() -> None:
    """
    Start Toolforge as an MCP server (progressive tool loading).

    Add this to your Claude Code / Cursor MCP config, for example:

        {
          "mcpServers": {
            "toolforge": {
              "command": "toolforge",
              "args": ["serve"]
            }
          }
        }
    """
    from toolforge.mcp.server import main as mcp_main
    mcp_main()


if __name__ == "__main__":
    app()
