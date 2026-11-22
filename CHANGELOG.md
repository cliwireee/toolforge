# Changelog

All notable changes to Toolforge will be documented in this file.

## [Unreleased]

### Fixed
- `toolforge serve` failed on a fresh install: `mcp>=1.0.0` resolves to mcp 2.x, which removed
  `mcp.server.fastmcp`, and the error wrongly said the package was missing. The server now supports
  mcp 1.x (`FastMCP`) and 2.x (`MCPServer`); the extra is pinned to `mcp>=1.20,<3`, and "not installed"
  is reported separately from "unsupported version".
- `estimate_context_cost(tools_json=...)` rejected every real input, because the MCP SDK json-decodes
  string arguments for `str | None` parameters. `register_tools` and `estimate_context_cost` now accept
  JSON text or the decoded list/object.
- The CLI downloaded the tokenizer vocabulary at import time, so even `--version`, `--help` and `init`
  crashed offline. The vocabulary now loads on first use, with an actionable error if unavailable.
- `toolforge --version` exited with "Missing command".
- `audit --top` was ignored (the table always showed 8 tools).
- Malformed tool JSON (non-object entries, `{"tools": "..."}`) crashed with a traceback; all input is
  now validated with a list of precise problems, in the CLI and in the MCP server.
- `.toolforge.toml` had no effect: `server_policies` was never parsed, the config was never used, broken
  TOML was silently ignored and invalid values raised raw tracebacks. Config errors are now reported
  with the file and field; unknown keys are rejected.
- Tool descriptions containing special-token text such as `<|endoftext|>` crashed token counting.
- Tool and server names containing `[...]` were swallowed or mangled as Rich markup.
- JSON output reported `"source": "live"` for file audits.
- `get_tool_schema` silently returned the first match when a name existed on several servers.
- `datetime.utcnow()` deprecation warnings; timestamps are now timezone-aware UTC.
- CI was red: ruff errors fixed, and mypy strict now passes and runs in CI.

### Added
- Live audits: `audit --command "<server command>"` and `audit --mcp-config <file>` start stdio MCP
  servers (Claude Code, Cursor, Claude Desktop and VS Code config formats) and audit their `tools/list`,
  with pagination, timeouts, `${VAR}` expansion and captured server stderr on failure.
- Profile projection in audits: per-tool policy and the up-front cost under the active profile;
  `--profile` and `--no-config` options for `audit` and `serve`.
- Allow/deny patterns with wildcards (`tool`, `server:tool`, `server:*`), applied by `serve` too.
- Anthropic (`input_schema`) and OpenAI (`parameters`) tool formats are accepted.
- Duplicate tool-name warning; always-load budget warning (`max_always_load_tokens`).
- `clear_registry(server_name=...)`; `always`-policy tools are listed with full schemas.
- `py.typed` marker; tests for CLI, config, policy, registry, server and live discovery; CI job for
  mcp 1.x; wheel smoke test.

### Changed
- Token counts are labelled as cl100k_base estimates (it is OpenAI's tokenizer, not Claude's).
- MCP responses use compact JSON, tool descriptions are concise, and output schemas are disabled, so
  the meta-tools themselves cost fewer tokens.
- Lightweight descriptions are cut on a word boundary with "…".
- Removed unused dependencies (`httpx`, `tomli`); the version is single-sourced from `__init__.py`.
- README: install from GitHub (the PyPI name `toolforge` belongs to another project).

## [0.1.0] – 2026-11-22

### Added
- Accurate token estimation for MCP tool definitions (cl100k_base)
- `toolforge audit` CLI command with rich table output and JSON mode
- `toolforge init` to create a starter `.toolforge.toml`
- `toolforge serve` – progressive MCP server with:
  - `register_tools`
  - `list_lightweight_tools`
  - `get_tool_schema`
  - `estimate_context_cost`
  - `clear_registry`
- Core models, configuration scaffolding, and unit tests
- GitHub Actions CI (lint + test + package build)
- SECURITY.md, CODE_OF_CONDUCT.md, issue templates, PR template
- Polished README with badges and clear problem statement
- MIT license
