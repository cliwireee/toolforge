# Toolforge

**Progressive MCP tooling that keeps your context lean.**

[![CI](https://github.com/cliwireee/toolforge/actions/workflows/ci.yml/badge.svg)](https://github.com/cliwireee/toolforge/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

Toolforge measures the token cost of MCP tool definitions and gives coding agents (Claude Code, Cursor, Codex, etc.) a progressive way to discover and load tools — so you stop paying the full context tax on every turn.

## Why this exists

Every MCP tool definition (name + description + JSON schema) is loaded into the model context *before any work happens*. Real measurements from the community show:

| Setup | Typical token cost |
|-------|--------------------|
| Median single server | ~4.7k tokens |
| Typical 5-server setup | ~55k tokens |
| Heavy / unoptimized servers | 100k–247k tokens |

That cost is paid on every turn, shrinks the usable context window, raises your bill, and can degrade tool-selection quality.

Toolforge attacks this problem directly.

## Features

- **Live audit** – start the stdio servers from your Claude Code / Cursor / Claude Desktop config and measure what they actually expose
- **File audit** – measure any JSON dump of tool definitions (MCP, Anthropic or OpenAI format); handy for CI
- **Clear breakdowns** – per-tool and per-server tables so you know what is expensive
- **Profile projection** – see what your `.toolforge.toml` allow/deny rules and load policies would cost up front
- **Progressive MCP server** – register tools once, then expose only lightweight names + short descriptions until the agent asks for a full schema
- **Local-first** – no required cloud services

## Install

```bash
# From source
git clone https://github.com/cliwireee/toolforge.git
cd toolforge
pip install -e ".[mcp]"

# Or straight from GitHub
pip install "toolforge[mcp] @ git+https://github.com/cliwireee/toolforge"
```

> **Note:** Toolforge is not on PyPI yet, and the name `toolforge` there belongs to an unrelated
> Wikimedia library — `pip install toolforge` installs *that* package, not this one.

The `[mcp]` extra (MCP Python SDK, `mcp>=1.20,<3`; both the 1.x and 2.x lines are supported) is needed for `serve`, `--command` and `--mcp-config`. File audits only need the base install.

## Audit tool definitions

```bash
# Every stdio server in a Claude Code / Cursor / Claude Desktop config
toolforge audit --mcp-config .mcp.json

# One server, started from a command line
toolforge audit --command "npx -y @modelcontextprotocol/server-github" --server github

# A JSON file: a list of tools, or {"tools": [...]} as returned by tools/list
toolforge audit --tools tools.json --server my-github-mcp
```

Useful options:

| Option | Meaning |
|--------|---------|
| `--top N` | Show the N most expensive tools per server (default 15, `0` hides the table) |
| `--json` | Machine-readable output. `--tools` / `--command` emit one `ServerAudit`; `--mcp-config` emits the full `AuditReport` |
| `--profile NAME` | Profile used for the "with profile" projection (default: `active_profile`) |
| `--no-config` | Ignore config files and use built-in defaults |
| `--timeout S` | Seconds to wait for each live server (default 60) |

`audit` exits with status 1 if any server could not be audited, so it can gate CI jobs.

**Live audits run the configured commands on your machine**, exactly as your MCP client would. Servers inherit your environment plus the entry's `env`; `${VAR}` and `${VAR:-default}` are expanded. Remote (HTTP/SSE) entries and entries with `"disabled": true` are skipped and listed in the report notes. Server stderr is captured and shown only when a server fails.

### How accurate are the numbers?

Counts are **estimates** using tiktoken's `cl100k_base` encoding, which is OpenAI's tokenizer. Claude's tokenizer is not public and differs, so use the numbers to compare tools and servers and to find outliers, not as an exact bill. Each tool also gets a fixed 12-token allowance for the surrounding JSON structure; that constant is an approximation.

tiktoken downloads the vocabulary the first time tokens are counted and caches it. Set `TIKTOKEN_CACHE_DIR` to choose the cache location (for example to pre-seed an offline machine). Commands that do not count tokens — `--version`, `init`, `serve` — never need it.

## Configure profiles

```bash
toolforge init   # writes .toolforge.toml
```

```toml
active_profile = "default"

[profiles.default]
default_policy = "lazy"          # lazy | always | code_mode | deny
max_always_load_tokens = 8000    # warn when "always" tools cost more than this
allow = []                       # empty = everything visible
deny = ["*:delete_*"]

[profiles.default.server_policies]
github = "lazy"
filesystem = "always"
```

Patterns are `tool`, `server:tool` or `server:*`, with shell-style wildcards in both parts. For each tool, the first matching rule wins:

1. matches a `deny` pattern → **deny**
2. `allow` is non-empty and nothing matches → **deny**
3. its server is in `server_policies` → that policy
4. otherwise → `default_policy`

The project's `.toolforge.toml` takes precedence over the user config (`~/.config/toolforge/config.toml` on Linux); the first file found is used and files are not merged. Invalid values, unknown keys and broken TOML are reported as errors rather than silently ignored.

In the audit, the **with profile** figure counts `always` tools at full cost, `lazy` / `code_mode` tools as the lightweight listing entry `toolforge serve` returns, and `deny` tools as zero. It does not include Toolforge's own meta-tools.

## Run the progressive MCP server

```bash
toolforge serve
```

Add it to your Claude Code / Cursor MCP config:

```json
{
  "mcpServers": {
    "toolforge": {
      "command": "toolforge",
      "args": ["serve"]
    }
  }
}
```

The agent can then use:

1. `register_tools` – load a batch of tool definitions into the progressive registry
2. `list_lightweight_tools` – get names + short descriptions only (cheap); `always` tools are listed in full
3. `get_tool_schema` – pull the full schema for tools it actually needs
4. `estimate_context_cost` – see the token impact before loading everything
5. `clear_registry` – drop all registered tools, or one server's

The active profile's allow/deny rules apply: denied tools are never registered. The registry lives in memory for the lifetime of the server process.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,mcp]"
pytest
ruff check src tests
mypy
```

Tests run offline with a deterministic stand-in tokenizer. Tests marked `real_tokenizer` use the real `cl100k_base` vocabulary: they are skipped when it cannot be downloaded, and required in CI.

## Roadmap

- True proxy mode that sits in front of upstream MCP servers
- Remote (HTTP/SSE) servers in live audits
- Exact Claude token counts via Anthropic's token-counting API
- Code-mode execution path for heavy tool sets
- Security / abandonment signals for MCP packages
- Smarter ranking of which tools to surface first

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Good first issues are labelled.

## License

MIT – see [LICENSE](LICENSE).

## Security

See [SECURITY.md](SECURITY.md) for how to report vulnerabilities.
