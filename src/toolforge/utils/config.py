"""Configuration loading and helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tomllib
from platformdirs import user_config_dir

from toolforge.core.models import ToolforgeConfig, ToolProfile, LoadPolicy


def default_config_dir() -> Path:
    return Path(user_config_dir("toolforge", "toolforge"))


def load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as f:
        return tomllib.load(f)


def load_config(project_root: Path | None = None) -> ToolforgeConfig:
    """
    Load configuration with the following precedence:
    1. Project-local .toolforge.toml
    2. User config (~/.config/toolforge/config.toml)
    3. Built-in defaults
    """
    candidates: list[Path] = []
    if project_root is None:
        project_root = Path.cwd()

    candidates.append(project_root / ".toolforge.toml")
    candidates.append(default_config_dir() / "config.toml")

    data: dict[str, Any] = {}
    for path in candidates:
        if path.is_file():
            try:
                data = load_toml(path)
                break
            except Exception:
                continue

    # Minimal parsing for v0.1 – expand later
    profiles: dict[str, ToolProfile] = {}
    raw_profiles = data.get("profiles", {})
    for name, pdata in raw_profiles.items():
        if not isinstance(pdata, dict):
            continue
        profiles[name] = ToolProfile(
            name=name,
            description=pdata.get("description", ""),
            allow=pdata.get("allow", []),
            deny=pdata.get("deny", []),
            default_policy=LoadPolicy(pdata.get("default_policy", "lazy")),
            max_always_load_tokens=int(pdata.get("max_always_load_tokens", 8000)),
        )

    if "default" not in profiles:
        profiles["default"] = ToolProfile(name="default")

    return ToolforgeConfig(
        active_profile=data.get("active_profile", "default"),
        profiles=profiles,
    )
