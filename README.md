# Toolforge

**Progressive MCP tooling that keeps your context lean.**

[![CI](https://github.com/cliwireee/toolforge/actions/workflows/ci.yml/badge.svg)](https://github.com/cliwireee/toolforge/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

Toolforge measures the real token cost of MCP tool definitions and gives coding agents (Claude Code, Cursor, Codex, etc.) a progressive way to discover and load tools — so you stop paying the full context tax on every turn.

## Why this exists

Every MCP tool definition (name + description + JSON schema) is loaded into the model context *before any work happens*. Real measurements from the community show:

| Setup | Typical token cost |
|-------|--------------------|
| Median single server | ~4.7k tokens |
| Typical 5-server setup | ~55k tokens |
| Heavy / unoptimized servers | 100k–247k tokens |

That cost is paid on every turn, shrinks the usable context window, raises your bill, and can degrade tool-selection quality.

Toolforge attacks this problem directly.

## Features (v0.1)

- **Accurate audit** – measure token cost of any set of MCP tool definitions (`cl100k_base`)
- **Clear breakdowns** – per-tool and per-server tables so you know what is expensive
- **Progressive MCP server** – register tools once, then expose only lightweight names + short descriptions until the agent asks for a full schema
- **Project config** – `.toolforge.toml` profiles for allow/deny and load policies
- **Local-first** – no required cloud services; optional Anthropic key only for future ranking features

## Quick Start

```bash
# From source
git clone https://github.com/cliwireee/toolforge.git
cd toolforge
pip install -e ".[dev]"

# Or once published
pip install toolforge
```

### Audit tool definitions

```bash
# Dump tools from your agent / MCP inspector into a JSON file, then:
toolforge audit --tools tools.json --server my-github-mcp
```

### Start the progressive MCP server

```bash
# Requires: pip install mcp
toolforge serve
```

Add to your Claude Code / Cursor MCP config:

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

Then the agent can:

1. `register_tools` – load a batch of tool definitions into the progressive registry
2. `list_lightweight_tools` – get names + short descriptions only (cheap)
3. `get_tool_schema` – pull the full schema for tools it actually needs
4. `estimate_context_cost` – see the token impact before loading everything

### Create a project config

```bash
toolforge init
```

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check src tests
```

## Roadmap

- Live discovery of configured MCP servers (Claude Code / Cursor configs)
- True proxy mode that sits in front of upstream MCP servers
- Code-mode execution path for heavy tool sets
- Security / abandonment signals for MCP packages
- Smarter ranking of which tools to surface first

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Good first issues are labelled.

## License

MIT – see [LICENSE](LICENSE).

## Security

See [SECURITY.md](SECURITY.md) for how to report vulnerabilities.
