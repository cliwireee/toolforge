"""Configuration loading and helpers."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir
from pydantic import ValidationError

from toolforge.core.models import ToolforgeConfig, ToolProfile

PROJECT_CONFIG_NAME = ".toolforge.toml"


class ConfigError(ValueError):
    """A Toolforge config file could not be read or is invalid."""


def default_config_dir() -> Path:
    return Path(user_config_dir("toolforge", "toolforge"))


def load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as f:
        return tomllib.load(f)


def find_config_file(project_root: Path | None = None) -> Path | None:
    """Return the config file that applies, or None.

    Precedence (first existing file wins; files are not merged):
    1. ``<project_root>/.toolforge.toml`` (default: current directory)
    2. the user config, e.g. ``~/.config/toolforge/config.toml``
    """
    root = Path.cwd() if project_root is None else project_root
    for path in (root / PROJECT_CONFIG_NAME, default_config_dir() / "config.toml"):
        if path.is_file():
            return path
    return None


def _format_validation_error(exc: ValidationError, prefix: str) -> list[str]:
    problems = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in (prefix, *err["loc"]) if part != "")
        problems.append(f"{loc}: {err['msg']}")
    return problems


def parse_config(data: dict[str, Any], source: Path | None = None) -> ToolforgeConfig:
    """Validate decoded TOML data into a :class:`ToolforgeConfig`."""
    where = str(source) if source else "config"
    raw_profiles = data.get("profiles", {})
    if not isinstance(raw_profiles, dict):
        raise ConfigError(f"{where}: 'profiles' must be a table, e.g. [profiles.default]")

    problems: list[str] = []
    profiles: dict[str, ToolProfile] = {}
    for name, pdata in raw_profiles.items():
        if not isinstance(pdata, dict):
            problems.append(f"profiles.{name}: must be a table ([profiles.{name}])")
            continue
        try:
            profiles[name] = ToolProfile.model_validate({**pdata, "name": name})
        except ValidationError as exc:
            problems.extend(_format_validation_error(exc, f"profiles.{name}"))

    top_level = {k: v for k, v in data.items() if k != "profiles"}
    profiles.setdefault("default", ToolProfile(name="default"))
    try:
        config = ToolforgeConfig.model_validate(
            {**top_level, "profiles": profiles, "source_path": str(source) if source else None}
        )
    except ValidationError as exc:
        problems.extend(_format_validation_error(exc, ""))
        config = None

    if config is not None and config.active_profile not in config.profiles:
        problems.append(
            f"active_profile: '{config.active_profile}' is not defined "
            f"(available: {', '.join(sorted(config.profiles))})"
        )
    if problems or config is None:
        raise ConfigError(f"Invalid config {where}:\n" + "\n".join(f"  - {p}" for p in problems))
    return config


def load_config(project_root: Path | None = None, *, path: Path | None = None) -> ToolforgeConfig:
    """Load the applicable configuration, or built-in defaults if none exists.

    Raises :class:`ConfigError` for unreadable files, invalid TOML and invalid
    values, instead of silently falling back to defaults.
    """
    config_path = path if path is not None else find_config_file(project_root)
    if config_path is None:
        return parse_config({})
    try:
        data = load_toml(config_path)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {config_path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Cannot read {config_path}: {exc.strerror or exc}") from exc
    return parse_config(data, source=config_path)


def select_profile(config: ToolforgeConfig, name: str | None = None) -> ToolProfile:
    """Return the named profile, or the config's active profile."""
    wanted = name or config.active_profile
    try:
        return config.profiles[wanted]
    except KeyError:
        raise ConfigError(
            f"Profile '{wanted}' is not defined "
            f"(available: {', '.join(sorted(config.profiles))})"
        ) from None
