"""Tests for the audit engine."""

from __future__ import annotations

from pathlib import Path

from toolforge.core.audit import audit_tools, lightweight_tokens
from toolforge.core.models import (
    HIGH_SERVER_TOKENS,
    MAX_RECOMMENDED_TOOLS,
    AuditReport,
    LoadPolicy,
    ToolProfile,
)
from toolforge.core.toolspec import load_tools_file, parse_tools


def test_audit_basic(sample_tools_file: Path) -> None:
    tools = load_tools_file(sample_tools_file)
    audit = audit_tools(tools, "github", source="file")

    assert audit.server_name == "github"
    assert audit.source == "file"
    assert audit.tool_count == 4
    assert audit.total_tokens == sum(t.total_tokens for t in audit.tools)
    totals = [t.total_tokens for t in audit.tools]
    assert totals == sorted(totals, reverse=True)
    assert audit.tools[0].name == "search_issues"
    assert audit.warnings == []
    assert audit.projected_tokens is None
    assert all(t.policy is None for t in audit.tools)


def test_high_cost_and_many_tools_warnings() -> None:
    big = parse_tools([{"name": "big", "description": "x" * (HIGH_SERVER_TOKENS + 1)}])
    assert any("High cost" in w for w in audit_tools(big).warnings)

    many = parse_tools([{"name": f"t{i}"} for i in range(MAX_RECOMMENDED_TOOLS + 1)])
    assert any("tool-selection quality" in w for w in audit_tools(many).warnings)


def test_duplicate_names_warning() -> None:
    tools = parse_tools([{"name": "a"}, {"name": "a"}])
    audit = audit_tools(tools)
    assert audit.tool_count == 2  # both copies are counted
    assert any("Duplicate tool names" in w and "a" in w for w in audit.warnings)


def test_profile_projection(sample_tools_file: Path) -> None:
    tools = load_tools_file(sample_tools_file)
    profile = ToolProfile(name="lean", deny=["*:delete_*"], default_policy=LoadPolicy.LAZY)
    always = ToolProfile(name="always", default_policy=LoadPolicy.ALWAYS)

    lean = audit_tools(tools, "github", profile=profile)
    by_name = {t.name: t for t in lean.tools}
    assert by_name["delete_branch"].policy is LoadPolicy.DENY
    assert by_name["delete_branch"].projected_tokens == 0
    search = by_name["search_issues"]
    assert search.policy is LoadPolicy.LAZY
    search_def = next(t for t in tools if t["name"] == "search_issues")
    assert search.projected_tokens == lightweight_tokens(search_def, "github")
    assert search.projected_tokens < search.total_tokens
    assert lean.projected_tokens == sum(t.projected_tokens or 0 for t in lean.tools)

    full = audit_tools(tools, "github", profile=always)
    assert full.projected_tokens == full.total_tokens


def test_always_load_budget_warning(sample_tools_file: Path) -> None:
    tools = load_tools_file(sample_tools_file)
    profile = ToolProfile(name="tight", default_policy=LoadPolicy.ALWAYS, max_always_load_tokens=10)
    audit = audit_tools(tools, "github", profile=profile)
    assert any("over the profile 'tight' budget of 10" in w for w in audit.warnings)


def test_report_from_servers_and_summary(sample_tools_file: Path) -> None:
    tools = load_tools_file(sample_tools_file)
    profile = ToolProfile(name="default")
    a = audit_tools(tools, "one", profile=profile)
    b = audit_tools(tools[:2], "two", profile=profile)

    report = AuditReport.from_servers([a, b], profile_name="default", errors=["x: failed"])
    assert report.grand_total_tools == 6
    assert report.grand_total_tokens == a.total_tokens + b.total_tokens
    assert report.projected_total_tokens == (a.projected_tokens or 0) + (b.projected_tokens or 0)
    assert report.errors == ["x: failed"]
    summary = report.summary()
    assert "With profile" in summary and "['default']" in summary and "less)" in summary


def test_report_without_profile_has_no_projection() -> None:
    audit = audit_tools(parse_tools([{"name": "a"}]))
    report = AuditReport.from_servers([audit])
    assert report.projected_total_tokens is None
    assert "With profile" not in report.summary()


def test_measured_at_is_timezone_aware() -> None:
    audit = audit_tools(parse_tools([{"name": "a"}]))
    assert audit.measured_at.tzinfo is not None
