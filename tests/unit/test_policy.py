"""Tests for allow/deny/policy resolution."""

from __future__ import annotations

import pytest

from toolforge.core.models import LoadPolicy, ToolProfile
from toolforge.core.policy import is_lazy, matches, resolve_policy


@pytest.mark.parametrize(
    ("pattern", "server", "tool", "expected"),
    [
        ("search", "github", "search", True),
        ("search", "jira", "search", True),
        ("search", "github", "search_issues", False),
        ("search*", "github", "search_issues", True),
        ("github:search", "github", "search", True),
        ("github:search", "jira", "search", False),
        ("github:*", "github", "anything", True),
        ("github:", "github", "anything", True),
        ("*:delete_*", "fs", "delete_file", True),
        ("git*:create_*", "gitlab", "create_mr", True),
        ("Search", "github", "search", False),  # case-sensitive
    ],
)
def test_matches(pattern: str, server: str, tool: str, expected: bool) -> None:
    assert matches(pattern, server, tool) is expected


def test_default_policy_applies() -> None:
    profile = ToolProfile(name="p", default_policy=LoadPolicy.ALWAYS)
    assert resolve_policy(profile, "s", "t") is LoadPolicy.ALWAYS


def test_server_policy_overrides_default() -> None:
    profile = ToolProfile(name="p", server_policies={"fs": LoadPolicy.ALWAYS})
    assert resolve_policy(profile, "fs", "read") is LoadPolicy.ALWAYS
    assert resolve_policy(profile, "github", "read") is LoadPolicy.LAZY


def test_deny_wins_over_everything() -> None:
    profile = ToolProfile(
        name="p",
        allow=["github:*"],
        deny=["*:delete_*"],
        server_policies={"github": LoadPolicy.ALWAYS},
    )
    assert resolve_policy(profile, "github", "delete_branch") is LoadPolicy.DENY
    assert resolve_policy(profile, "github", "search") is LoadPolicy.ALWAYS


def test_allow_list_hides_unmatched_tools() -> None:
    profile = ToolProfile(name="p", allow=["github:*", "read_file"])
    assert resolve_policy(profile, "github", "search") is LoadPolicy.LAZY
    assert resolve_policy(profile, "fs", "read_file") is LoadPolicy.LAZY
    assert resolve_policy(profile, "fs", "write_file") is LoadPolicy.DENY


def test_allow_does_not_override_server_deny() -> None:
    profile = ToolProfile(
        name="p", allow=["github:search"], server_policies={"github": LoadPolicy.DENY}
    )
    assert resolve_policy(profile, "github", "search") is LoadPolicy.DENY


def test_is_lazy() -> None:
    assert is_lazy(LoadPolicy.LAZY) and is_lazy(LoadPolicy.CODE_MODE)
    assert not is_lazy(LoadPolicy.ALWAYS) and not is_lazy(LoadPolicy.DENY)
