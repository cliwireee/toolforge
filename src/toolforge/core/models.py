"""Pydantic models used across Toolforge."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ToolCost(BaseModel):
    name: str
    name_tokens: int = 0
    description_tokens: int = 0
    input_schema_tokens: int = 0
    structural_tokens: int = 0
    total_tokens: int = 0


class ServerAudit(BaseModel):
    server_name: str
    tool_count: int = 0
    total_tokens: int = 0
    avg_tokens_per_tool: float = 0.0
    tools: list[ToolCost] = Field(default_factory=list)
    measured_at: datetime = Field(default_factory=datetime.utcnow)
    source: str = "unknown"  # "live", "config", "cache"
    warnings: list[str] = Field(default_factory=list)


class AuditReport(BaseModel):
    servers: list[ServerAudit] = Field(default_factory=list)
    grand_total_tokens: int = 0
    grand_total_tools: int = 0
    measured_at: datetime = Field(default_factory=datetime.utcnow)
    notes: list[str] = Field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Servers audited : {len(self.servers)}",
            f"Total tools     : {self.grand_total_tools}",
            f"Total tokens    : {self.grand_total_tokens:,}",
        ]
        if self.grand_total_tokens > 30_000:
            lines.append("⚠️  High context tax detected. Consider progressive loading.")
        return "\n".join(lines)


class LoadPolicy(str, Enum):
    ALWAYS = "always"          # full schema always in context
    LAZY = "lazy"              # only name + short description until requested
    CODE_MODE = "code_mode"    # prefer code-mode execution path
    DENY = "deny"              # never expose


class ToolProfile(BaseModel):
    name: str
    description: str = ""
    # Explicit allow / deny
    allow: list[str] = Field(default_factory=list)   # tool names or "server:*"
    deny: list[str] = Field(default_factory=list)
    # Per-server policy overrides
    server_policies: dict[str, LoadPolicy] = Field(default_factory=dict)
    # Global defaults
    default_policy: LoadPolicy = LoadPolicy.LAZY
    max_always_load_tokens: int = 8_000
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ToolforgeConfig(BaseModel):
    """User / project configuration."""
    active_profile: str = "default"
    profiles: dict[str, ToolProfile] = Field(default_factory=dict)
    cache_dir: str | None = None
    enable_security_checks: bool = True
    anthropic_api_key_env: str = "ANTHROPIC_API_KEY"
