"""Load-policy resolution for tools under a :class:`ToolProfile`.

Pattern syntax (used by ``allow`` and ``deny``):

* ``"search"``          – a tool named ``search`` on any server
* ``"github:search"``   – the ``search`` tool on the ``github`` server
* ``"github:*"``        – every tool on the ``github`` server
* shell-style wildcards work in both parts: ``"*:delete_*"``, ``"git*:create_*"``

Resolution order for a tool (first match wins):

1. it matches any ``deny`` pattern                  → ``deny``
2. ``allow`` is non-empty and it matches no pattern → ``deny``
3. its server has an entry in ``server_policies``   → that policy
4. otherwise                                        → ``default_policy``

``allow`` filters what is visible; it does not override a server policy of
``deny``.
"""

from __future__ import annotations

from fnmatch import fnmatchcase

from toolforge.core.models import LoadPolicy, ToolProfile


def matches(pattern: str, server: str, tool: str) -> bool:
    """Return True if ``pattern`` selects ``tool`` on ``server`` (case-sensitive)."""
    if ":" in pattern:
        server_pattern, _, tool_pattern = pattern.partition(":")
        return fnmatchcase(server, server_pattern) and fnmatchcase(tool, tool_pattern or "*")
    return fnmatchcase(tool, pattern)


def resolve_policy(profile: ToolProfile, server: str, tool: str) -> LoadPolicy:
    """Return the effective load policy of ``tool`` on ``server``."""
    if any(matches(p, server, tool) for p in profile.deny):
        return LoadPolicy.DENY
    if profile.allow and not any(matches(p, server, tool) for p in profile.allow):
        return LoadPolicy.DENY
    return profile.server_policies.get(server, profile.default_policy)


def is_lazy(policy: LoadPolicy) -> bool:
    """Lazy and code-mode tools are both surfaced as lightweight entries for now."""
    return policy in (LoadPolicy.LAZY, LoadPolicy.CODE_MODE)
