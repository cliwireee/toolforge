"""Live discovery: launch stdio MCP servers and read their ``tools/list``.

Supports the ``mcpServers`` JSON format used by Claude Code (``.mcp.json``),
Claude Desktop and Cursor (``mcp.json``), plus VS Code's ``servers`` key.
Remote (HTTP/SSE) servers are skipped for now.

Launching a server runs the command from the config on this machine, exactly
as your MCP client would.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from toolforge.core.toolspec import ToolDefinitionError, parse_tools
from toolforge.mcp._compat import require_mcp

DEFAULT_TIMEOUT = 60.0
DEFAULT_CONCURRENCY = 4
_MAX_PAGES = 100
_STDERR_TAIL_LINES = 5
_REMOTE_TYPES = {"http", "sse", "streamable-http", "streamablehttp", "ws", "websocket"}
_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


class MCPConfigError(ValueError):
    """An MCP client config file (or --command line) cannot be used."""


class DiscoveryError(RuntimeError):
    """A server could not be started or did not answer tools/list."""


@dataclass(frozen=True)
class StdioServerSpec:
    name: str
    command: str
    args: tuple[str, ...] = ()
    # Extra environment variables, applied on top of the current environment.
    env: Mapping[str, str] | None = None
    cwd: str | None = None


@dataclass(frozen=True)
class SkippedServer:
    name: str
    reason: str
    # True for problems the user must fix (bad entry, missing variable);
    # False for servers that are intentionally not audited (remote, disabled).
    is_error: bool = False


@dataclass
class DiscoveryResult:
    spec: StdioServerSpec
    tools: list[dict[str, Any]] | None = None
    error: str | None = None


def spec_from_command(command_line: str, name: str = "local") -> StdioServerSpec:
    """Build a spec from a shell-style command line such as ``npx -y some-server``."""
    try:
        argv = shlex.split(command_line, posix=os.name != "nt")
    except ValueError as exc:
        raise MCPConfigError(f"Cannot parse --command: {exc}") from exc
    if os.name == "nt":
        argv = [a[1:-1] if len(a) >= 2 and a[0] == a[-1] == '"' else a for a in argv]
    if not argv:
        raise MCPConfigError("--command is empty")
    return StdioServerSpec(name=name, command=argv[0], args=tuple(argv[1:]))


def expand_vars(value: str, environ: Mapping[str, str], missing: list[str]) -> str:
    """Expand ``${VAR}`` and ``${VAR:-default}``; record unset variables in ``missing``."""

    def repl(match: re.Match[str]) -> str:
        name, default = match.group(1), match.group(2)
        if name in environ:
            return environ[name]
        if default is not None:
            return default
        missing.append(name)
        return ""

    return _VAR.sub(repl, value)


def _parse_entry(
    name: str, entry: Any, base_dir: Path, environ: Mapping[str, str]
) -> StdioServerSpec | SkippedServer:
    if not isinstance(entry, dict):
        return SkippedServer(name, "entry must be an object", is_error=True)
    if entry.get("disabled") is True:
        return SkippedServer(name, "disabled in config")
    kind = str(entry.get("type", "")).lower()
    if kind in _REMOTE_TYPES or ("url" in entry and "command" not in entry):
        return SkippedServer(
            name, f"remote server ({kind or 'url'}) – only stdio servers are supported"
        )

    command = entry.get("command")
    args = entry.get("args", [])
    env = entry.get("env", {})
    cwd = entry.get("cwd")
    if not isinstance(command, str) or not command.strip():
        return SkippedServer(name, "'command' must be a non-empty string", is_error=True)
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        return SkippedServer(name, "'args' must be a list of strings", is_error=True)
    if not isinstance(env, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in env.items()
    ):
        return SkippedServer(name, "'env' must map strings to strings", is_error=True)
    if cwd is not None and not isinstance(cwd, str):
        return SkippedServer(name, "'cwd' must be a string", is_error=True)

    missing: list[str] = []
    command = expand_vars(command, environ, missing)
    args = [expand_vars(a, environ, missing) for a in args]
    env = {k: expand_vars(v, environ, missing) for k, v in env.items()}
    cwd_path = base_dir if cwd is None else base_dir / expand_vars(cwd, environ, missing)
    if missing:
        names = ", ".join(dict.fromkeys(missing))
        return SkippedServer(name, f"environment variable(s) not set: {names}", is_error=True)

    return StdioServerSpec(name=name, command=command, args=tuple(args), env=env, cwd=str(cwd_path))


def load_mcp_config(
    path: Path, environ: Mapping[str, str] | None = None
) -> tuple[list[StdioServerSpec], list[SkippedServer]]:
    """Parse an MCP client config file into launchable specs and skipped entries.

    Servers run with the config file's directory as working directory unless an
    entry sets ``cwd`` (relative paths are resolved against that directory).
    """
    env = os.environ if environ is None else environ
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MCPConfigError(f"Invalid JSON in {path}: {exc.msg} (line {exc.lineno})") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise MCPConfigError(f"Cannot read {path}: {exc}") from exc

    servers = None
    if isinstance(data, dict):
        servers = data.get("mcpServers", data.get("servers"))
    if not isinstance(servers, dict):
        raise MCPConfigError(f"{path}: expected an object with an 'mcpServers' (or 'servers') map")

    specs: list[StdioServerSpec] = []
    skipped: list[SkippedServer] = []
    base_dir = path.resolve().parent
    for name, entry in servers.items():
        parsed = _parse_entry(str(name), entry, base_dir, env)
        if isinstance(parsed, SkippedServer):
            skipped.append(parsed)
        else:
            specs.append(parsed)
    return specs, skipped


def _tool_to_dict(tool: Any) -> dict[str, Any]:
    if isinstance(tool, dict):
        return tool
    dumped: dict[str, Any] = tool.model_dump(by_alias=True, exclude_none=True, mode="json")
    return dumped


async def list_all_tools(session: Any) -> list[dict[str, Any]]:
    """Call tools/list, following pagination cursors, and return plain dicts."""
    from mcp.types import PaginatedRequestParams

    tools: list[dict[str, Any]] = []
    cursor: str | None = None
    seen: set[str] = set()
    for _ in range(_MAX_PAGES):
        if cursor is None:
            result = await session.list_tools()
        else:
            result = await session.list_tools(params=PaginatedRequestParams(cursor=cursor))
        tools.extend(_tool_to_dict(t) for t in result.tools)
        # mcp 2.x names the attribute next_cursor; mcp 1.x uses nextCursor.
        cursor = getattr(result, "next_cursor", None) or getattr(result, "nextCursor", None)
        if not cursor or cursor in seen:
            break
        seen.add(cursor)
    return tools


def _describe(exc: BaseException) -> str:
    if isinstance(exc, BaseExceptionGroup):
        return "; ".join(dict.fromkeys(_describe(e) for e in exc.exceptions))
    text = str(exc).strip()
    if isinstance(exc, FileNotFoundError) and exc.filename:
        return f"command not found: {exc.filename}"
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


def _stderr_tail(errlog: IO[str]) -> str:
    try:
        errlog.seek(0)
        lines = [line.rstrip() for line in errlog.read().splitlines() if line.strip()]
    except (OSError, ValueError):
        return ""
    if not lines:
        return ""
    tail = "\n    ".join(lines[-_STDERR_TAIL_LINES:])
    return f"\n  server stderr (last lines):\n    {tail}"


async def fetch_tools(
    spec: StdioServerSpec, timeout: float = DEFAULT_TIMEOUT
) -> list[dict[str, Any]]:
    """Start one stdio server, initialise a session and return its tool definitions."""
    require_mcp()
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=spec.command,
        args=list(spec.args),
        env={**os.environ, **(spec.env or {})},
        cwd=spec.cwd,
    )
    # Server logs go to a temp file instead of cluttering the report; the tail
    # is attached to the error message when something goes wrong.
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as errlog:
        try:
            with anyio.fail_after(timeout):
                async with stdio_client(params, errlog=errlog) as (read, write):  # noqa: SIM117
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        return await list_all_tools(session)
        except TimeoutError:
            raise DiscoveryError(
                f"no tools/list answer within {timeout:g}s" + _stderr_tail(errlog)
            ) from None
        except Exception as exc:
            raise DiscoveryError(_describe(exc) + _stderr_tail(errlog)) from exc


def discover(
    specs: list[StdioServerSpec],
    timeout: float = DEFAULT_TIMEOUT,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> list[DiscoveryResult]:
    """Fetch and validate the tools of several servers concurrently.

    One failing server never aborts the others; its result carries ``error``.
    """
    require_mcp()
    import anyio

    results = [DiscoveryResult(spec=spec) for spec in specs]

    async def run_one(result: DiscoveryResult, limiter: anyio.CapacityLimiter) -> None:
        async with limiter:
            try:
                raw = await fetch_tools(result.spec, timeout)
                result.tools = parse_tools(raw, source=f"server '{result.spec.name}'")
            except (DiscoveryError, ToolDefinitionError) as exc:
                result.error = str(exc)

    async def run_all() -> None:
        limiter = anyio.CapacityLimiter(max(1, concurrency))
        async with anyio.create_task_group() as tg:
            for result in results:
                tg.start_soon(run_one, result, limiter)

    anyio.run(run_all)
    return results
