"""Tests for configuration loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from toolforge.cli.main import STARTER_CONFIG
from toolforge.core.models import LoadPolicy
from toolforge.utils.config import (
    ConfigError,
    find_config_file,
    load_config,
    parse_config,
    select_profile,
)


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_defaults_without_any_file(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    assert config.source_path is None
    assert config.active_profile == "default"
    assert config.profiles["default"].default_policy is LoadPolicy.LAZY


def test_parses_full_profile_including_server_policies(tmp_path: Path) -> None:
    write(
        tmp_path / ".toolforge.toml",
        """
active_profile = "lean"

[profiles.lean]
description = "Lean"
default_policy = "lazy"
max_always_load_tokens = 2000
allow = ["github:*"]
deny = ["*:delete_*"]

[profiles.lean.server_policies]
github = "always"
filesystem = "deny"
""",
    )
    config = load_config(tmp_path)
    profile = select_profile(config)
    assert config.source_path == str(tmp_path / ".toolforge.toml")
    assert profile.name == "lean"
    assert profile.allow == ["github:*"]
    assert profile.deny == ["*:delete_*"]
    assert profile.max_always_load_tokens == 2000
    assert profile.server_policies == {"github": LoadPolicy.ALWAYS, "filesystem": LoadPolicy.DENY}
    assert "default" in config.profiles  # always available


def test_starter_config_from_init_is_valid() -> None:
    import tomllib

    config = parse_config(tomllib.loads(STARTER_CONFIG))
    assert select_profile(config).max_always_load_tokens == 8000


@pytest.mark.parametrize(
    ("toml", "fragment"),
    [
        ('[profiles.default]\ndefault_policy = "bogus"', "profiles.default.default_policy"),
        ("[profiles.default]\ndefualt_policy = 'lazy'", "profiles.default.defualt_policy"),
        ('[profiles.default.server_policies]\ngithub = "sometimes"', "server_policies.github"),
        ("[profiles.default]\nmax_always_load_tokens = -5", "max_always_load_tokens"),
        ('active_profile = "missing"', "active_profile: 'missing' is not defined"),
        ("unknown_key = 1", "unknown_key"),
        ("profiles = 3", "'profiles' must be a table"),
    ],
)
def test_invalid_values_are_reported(tmp_path: Path, toml: str, fragment: str) -> None:
    write(tmp_path / ".toolforge.toml", toml)
    with pytest.raises(ConfigError) as info:
        load_config(tmp_path)
    assert fragment in str(info.value)


def test_broken_toml_is_reported_not_ignored(tmp_path: Path) -> None:
    path = write(tmp_path / ".toolforge.toml", "broken = [")
    with pytest.raises(ConfigError, match="Invalid TOML") as info:
        load_config(tmp_path)
    assert str(path) in str(info.value)


def test_user_config_used_when_no_project_file(tmp_path: Path, isolated_user_config: Path) -> None:
    write(isolated_user_config / "config.toml", 'active_profile = "default"\n')
    project = tmp_path / "project"
    project.mkdir()
    assert find_config_file(project) == isolated_user_config / "config.toml"


def test_project_file_wins_over_user_config(tmp_path: Path, isolated_user_config: Path) -> None:
    write(isolated_user_config / "config.toml", "broken = [")  # would fail if read
    project_file = write(tmp_path / ".toolforge.toml", 'active_profile = "default"\n')
    assert find_config_file(tmp_path) == project_file
    assert load_config(tmp_path).source_path == str(project_file)


def test_select_unknown_profile(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Profile 'nope' is not defined"):
        select_profile(load_config(tmp_path), "nope")
