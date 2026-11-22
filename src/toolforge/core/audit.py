"""Audit engine: estimate the token cost of MCP tool definitions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from toolforge.core.models import (
    HIGH_SERVER_TOKENS,
    MAX_RECOMMENDED_TOOLS,
    AuditReport,
    LoadPolicy,
    ServerAudit,
    ToolCost,
    ToolProfile,
)
from toolforge.core.policy import is_lazy, resolve_policy
from toolforge.core.tokens import count_json_tokens, estimate_server_tokens
from toolforge.core.toolspec import duplicate_names, lightweight_entry, load_tools_file

console = Console()

DEFAULT_TOP_N = 15

TOKENIZER_NOTE = (
    "Token counts are estimates using tiktoken's cl100k_base encoding (OpenAI's tokenizer). "
    "Claude's tokenizer is not public and differs, so treat numbers as approximate."
)
PROJECTION_NOTE = (
    "'With profile' counts always-loaded tools at full cost and lazy tools as the "
    "name + short description listing `toolforge serve` returns. It excludes "
    "Toolforge's own meta-tools."
)


def lightweight_tokens(tool: dict[str, Any], server: str) -> int:
    """Estimated tokens of the lightweight listing entry for ``tool``."""
    return count_json_tokens(lightweight_entry(tool, server))


def audit_tools(
    tools: list[dict[str, Any]],
    server_name: str = "unknown",
    *,
    source: str = "unknown",
    profile: ToolProfile | None = None,
) -> ServerAudit:
    """Audit the (already validated) tool definitions of one server.

    With a ``profile``, every tool also gets its effective policy and the
    up-front token cost it would have under that profile.
    """
    stats = estimate_server_tokens(tools)
    by_name = {t["name"]: t for t in tools}

    tool_costs: list[ToolCost] = []
    for t in stats["tools"]:
        policy: LoadPolicy | None = None
        projected: int | None = None
        if profile is not None:
            policy = resolve_policy(profile, server_name, t["name"])
            if policy is LoadPolicy.ALWAYS:
                projected = t["total"]
            elif is_lazy(policy):
                source_tool = by_name.get(t["name"], {"name": t["name"]})
                projected = lightweight_tokens(source_tool, server_name)
            else:
                projected = 0
        tool_costs.append(
            ToolCost(
                name=t["name"],
                name_tokens=t["name_tokens"],
                description_tokens=t["description_tokens"],
                input_schema_tokens=t["input_schema_tokens"],
                structural_tokens=t["structural_tokens"],
                total_tokens=t["total"],
                policy=policy,
                projected_tokens=projected,
            )
        )

    warnings: list[str] = []
    if stats["total_tokens"] > HIGH_SERVER_TOKENS:
        warnings.append(
            f"High cost: {stats['total_tokens']:,} tokens. "
            "Strongly consider progressive / lazy loading."
        )
    if stats["tool_count"] > MAX_RECOMMENDED_TOOLS:
        warnings.append(
            f"{stats['tool_count']} tools may degrade tool-selection quality. "
            "Anthropic guidance suggests staying under ~30–50 active tools."
        )
    dupes = duplicate_names(tools)
    if dupes:
        shown = ", ".join(dupes[:5]) + (" ..." if len(dupes) > 5 else "")
        warnings.append(f"Duplicate tool names (each copy is counted): {shown}")

    projected_total: int | None = None
    if profile is not None:
        projected_total = sum(c.projected_tokens or 0 for c in tool_costs)
        always_cost = sum(c.total_tokens for c in tool_costs if c.policy is LoadPolicy.ALWAYS)
        if always_cost > profile.max_always_load_tokens:
            warnings.append(
                f"Always-loaded tools cost {always_cost:,} tokens, over the profile "
                f"'{profile.name}' budget of {profile.max_always_load_tokens:,}."
            )

    return ServerAudit(
        server_name=server_name,
        tool_count=stats["tool_count"],
        total_tokens=stats["total_tokens"],
        avg_tokens_per_tool=stats["avg_tokens_per_tool"],
        tools=tool_costs,
        source=source,
        warnings=warnings,
        projected_tokens=projected_total,
    )


def print_server_audit(
    audit: ServerAudit, show_tools: bool = True, top_n: int = DEFAULT_TOP_N
) -> None:
    """Pretty-print a single server audit."""
    console.print()
    console.rule(f"[bold]{escape(audit.server_name)}[/bold]")
    line = (
        f"Tools: {audit.tool_count}   |   "
        f"Total tokens: [bold cyan]{audit.total_tokens:,}[/bold cyan]   |   "
        f"Avg/tool: {audit.avg_tokens_per_tool}"
    )
    if audit.projected_tokens is not None:
        line += f"   |   With profile: [bold green]{audit.projected_tokens:,}[/bold green]"
    console.print(line)

    for w in audit.warnings:
        console.print(f"[yellow]⚠ {escape(w)}[/yellow]")

    if show_tools and audit.tools and top_n > 0:
        has_policy = any(t.policy is not None for t in audit.tools)
        table = Table(title=f"Top {min(top_n, len(audit.tools))} most expensive tools")
        table.add_column("Tool", style="cyan", no_wrap=True)
        if has_policy:
            table.add_column("Policy")
        table.add_column("Total", justify="right")
        table.add_column("Schema", justify="right")
        table.add_column("Desc", justify="right")
        table.add_column("Name", justify="right")

        for t in audit.tools[:top_n]:
            row = [escape(t.name)]
            if has_policy:
                row.append(t.policy.value if t.policy else "")
            row += [
                f"{t.total_tokens:,}",
                f"{t.input_schema_tokens:,}",
                f"{t.description_tokens:,}",
                f"{t.name_tokens:,}",
            ]
            table.add_row(*row)
        console.print(table)


def print_report(report: AuditReport, top_n: int = DEFAULT_TOP_N) -> None:
    """Pretty-print a full multi-server audit report."""
    console.print()
    console.rule("[bold green]Toolforge Audit Report[/bold green]")
    console.print(escape(report.summary()))
    console.print()

    for server in sorted(report.servers, key=lambda s: s.total_tokens, reverse=True):
        print_server_audit(server, show_tools=True, top_n=top_n)

    if report.errors:
        console.print()
        console.rule("[red]Not audited[/red]")
        for err in report.errors:
            console.print(f"[red]✗[/red] {escape(err)}")

    if report.notes:
        console.print()
        console.rule("Notes")
        for note in report.notes:
            console.print(f"• {escape(note)}")


def load_tools_from_json(path: Path) -> list[dict[str, Any]]:
    """Load and validate tool definitions from a JSON file.

    Kept for backwards compatibility; see :func:`toolforge.core.toolspec.load_tools_file`.
    """
    return load_tools_file(path)
