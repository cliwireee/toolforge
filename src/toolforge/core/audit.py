"""Audit engine: measure real token cost of MCP tool definitions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

from toolforge.core.models import AuditReport, ServerAudit, ToolCost
from toolforge.core.tokens import estimate_server_tokens, estimate_tool_tokens

console = Console()


def audit_tools(tools: list[dict[str, Any]], server_name: str = "unknown") -> ServerAudit:
    """Audit a list of tool definitions belonging to one server."""
    stats = estimate_server_tokens(tools)

    tool_costs = [
        ToolCost(
            name=t["name"],
            name_tokens=t.get("name_tokens", 0),
            description_tokens=t.get("description_tokens", 0),
            input_schema_tokens=t.get("input_schema_tokens", 0),
            structural_tokens=t.get("structural_tokens", 0),
            total_tokens=t.get("total", 0),
        )
        for t in stats["tools"]
    ]

    warnings: list[str] = []
    if stats["total_tokens"] > 25_000:
        warnings.append(
            f"High cost: {stats['total_tokens']:,} tokens. "
            "Strongly consider progressive / lazy loading."
        )
    if stats["tool_count"] > 40:
        warnings.append(
            f"{stats['tool_count']} tools may degrade tool-selection quality. "
            "Anthropic guidance suggests staying under ~30–50 active tools."
        )

    return ServerAudit(
        server_name=server_name,
        tool_count=stats["tool_count"],
        total_tokens=stats["total_tokens"],
        avg_tokens_per_tool=stats["avg_tokens_per_tool"],
        tools=tool_costs,
        source="live",
        warnings=warnings,
    )


def print_server_audit(audit: ServerAudit, show_tools: bool = True, top_n: int = 15) -> None:
    """Pretty-print a single server audit."""
    console.print()
    console.rule(f"[bold]{audit.server_name}[/bold]")
    console.print(
        f"Tools: {audit.tool_count}   |   "
        f"Total tokens: [bold cyan]{audit.total_tokens:,}[/bold cyan]   |   "
        f"Avg/tool: {audit.avg_tokens_per_tool}"
    )

    for w in audit.warnings:
        console.print(f"[yellow]⚠ {w}[/yellow]")

    if show_tools and audit.tools:
        table = Table(title=f"Top {min(top_n, len(audit.tools))} most expensive tools")
        table.add_column("Tool", style="cyan", no_wrap=True)
        table.add_column("Total", justify="right")
        table.add_column("Schema", justify="right")
        table.add_column("Desc", justify="right")
        table.add_column("Name", justify="right")

        for t in audit.tools[:top_n]:
            table.add_row(
                t.name,
                f"{t.total_tokens:,}",
                f"{t.input_schema_tokens:,}",
                f"{t.description_tokens:,}",
                f"{t.name_tokens:,}",
            )
        console.print(table)


def print_report(report: AuditReport) -> None:
    """Pretty-print a full multi-server audit report."""
    console.print()
    console.rule("[bold green]Toolforge Audit Report[/bold green]")
    console.print(report.summary())
    console.print()

    for server in sorted(report.servers, key=lambda s: s.total_tokens, reverse=True):
        print_server_audit(server, show_tools=True, top_n=8)

    if report.notes:
        console.print()
        console.rule("Notes")
        for note in report.notes:
            console.print(f"• {note}")


def load_tools_from_json(path: Path) -> list[dict[str, Any]]:
    """Load a list of tool definitions from a JSON file (for offline testing)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "tools" in data:
        return data["tools"]
    if isinstance(data, list):
        return data
    raise ValueError(f"Unexpected JSON structure in {path}")
