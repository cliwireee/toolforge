"""Pydantic models used across Toolforge."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

# Thresholds shared by the CLI report and the MCP server's advice.
HIGH_SERVER_TOKENS = 25_000  # one server / one set of tools
HIGH_TOTAL_TOKENS = 30_000  # everything in a report
MAX_RECOMMENDED_TOOLS = 40


def _utcnow() -> datetime:
    return datetime.now(UTC)


class LoadPolicy(StrEnum):
    ALWAYS = "always"  # full schema always in context
    LAZY = "lazy"  # only name + short description until requested
    CODE_MODE = "code_mode"  # prefer code-mode execution path (treated like lazy for now)
    DENY = "deny"  # never expose


class ToolCost(BaseModel):
    name: str
    name_tokens: int = 0
    description_tokens: int = 0
    input_schema_tokens: int = 0
    structural_tokens: int = 0
    total_tokens: int = 0
    # Set when a profile was applied to the audit.
    policy: LoadPolicy | None = None
    projected_tokens: int | None = None


class ServerAudit(BaseModel):
    server_name: str
    tool_count: int = 0
    total_tokens: int = 0
    avg_tokens_per_tool: float = 0.0
    tools: list[ToolCost] = Field(default_factory=list)
    measured_at: datetime = Field(default_factory=_utcnow)
    source: str = "unknown"  # "file", "live", "config", "cache"
    warnings: list[str] = Field(default_factory=list)
    # Up-front cost under the applied profile (None when no profile was applied).
    projected_tokens: int | None = None


class AuditReport(BaseModel):
    servers: list[ServerAudit] = Field(default_factory=list)
    grand_total_tokens: int = 0
    grand_total_tools: int = 0
    measured_at: datetime = Field(default_factory=_utcnow)
    notes: list[str] = Field(default_factory=list)
    profile_name: str | None = None
    projected_total_tokens: int | None = None
    # Servers that could not be audited (e.g. a live server failed to start).
    errors: list[str] = Field(default_factory=list)

    @classmethod
    def from_servers(
        cls,
        servers: list[ServerAudit],
        *,
        notes: list[str] | None = None,
        profile_name: str | None = None,
        errors: list[str] | None = None,
    ) -> AuditReport:
        projected = [s.projected_tokens for s in servers]
        return cls(
            servers=servers,
            grand_total_tokens=sum(s.total_tokens for s in servers),
            grand_total_tools=sum(s.tool_count for s in servers),
            notes=notes or [],
            profile_name=profile_name,
            projected_total_tokens=(
                sum(p for p in projected if p is not None)
                if servers and all(p is not None for p in projected)
                else None
            ),
            errors=errors or [],
        )

    def summary(self) -> str:
        lines = [
            f"Servers audited : {len(self.servers)}",
            f"Total tools     : {self.grand_total_tools}",
            f"Total tokens    : {self.grand_total_tokens:,}",
        ]
        if self.projected_total_tokens is not None and self.profile_name is not None:
            saved = self.grand_total_tokens - self.projected_total_tokens
            pct = ""
            if self.grand_total_tokens:
                pct = f" ({saved / self.grand_total_tokens:.0%} less)"
            lines.append(
                f"With profile    : {self.projected_total_tokens:,} up front "
                f"['{self.profile_name}']{pct}"
            )
        if self.grand_total_tokens > HIGH_TOTAL_TOKENS:
            lines.append("⚠️  High context tax detected. Consider progressive loading.")
        return "\n".join(lines)


class ToolProfile(BaseModel):
    # Reject unknown keys so a typo such as `defualt_policy` is reported
    # instead of being silently ignored.
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    # Patterns: "tool", "server:tool", "server:*"; shell-style wildcards allowed.
    allow: list[str] = Field(default_factory=list)
    deny: list[str] = Field(default_factory=list)
    # Per-server policy overrides, keyed by server name.
    server_policies: dict[str, LoadPolicy] = Field(default_factory=dict)
    default_policy: LoadPolicy = LoadPolicy.LAZY
    max_always_load_tokens: int = Field(default=8_000, ge=0)
    created_at: datetime = Field(default_factory=_utcnow)


class ToolforgeConfig(BaseModel):
    """User / project configuration."""

    model_config = ConfigDict(extra="forbid")

    active_profile: str = "default"
    profiles: dict[str, ToolProfile] = Field(default_factory=dict)
    cache_dir: str | None = None
    enable_security_checks: bool = True
    anthropic_api_key_env: str = "ANTHROPIC_API_KEY"
    # Path of the file this config was loaded from; None for built-in defaults.
    source_path: str | None = None
