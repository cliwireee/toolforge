# Toolforge

**Progressive MCP tooling that keeps your context lean.**

Toolforge measures the real token cost of MCP tool definitions, helps you prune expensive servers, and provides progressive / on-demand loading so your coding agents (Claude Code, Cursor, Codex, etc.) stop paying the full context tax on every turn.

## The Problem

Every MCP tool definition (name + description + JSON schema) is loaded into the model context *before* any work happens. Real measurements show:

- Median server ≈ 4.7k tokens
- Typical 5-server setup ≈ 55k tokens
- Heavy servers can exceed 100k–247k tokens

This burns money, reduces available context, and makes tool selection worse.

## What Toolforge Does (v0.1)

- **Accurate audit** of tool definition token cost (cl100k_base)
- Clear per-tool and per-server breakdowns
- Starter project configuration (`.toolforge.toml`)
- Foundation for progressive loading and code-mode (coming next)

Later versions will add:

- Live discovery of configured MCP servers
- Toolforge itself as an MCP server that exposes only lightweight tool names until requested
- Code-mode execution path for heavy tool sets
- Security / abandonment signals
- Project-scoped profiles and allow/deny lists

## Quick Start

```bash
# Install (once packaging is published)
pip install toolforge
# or
uvx toolforge ...

# Or from source
cd toolforge
pip install -e ".[dev]"
```

### Audit a set of tools

```bash
# Dump tools from your agent or MCP inspector into tools.json, then:
toolforge audit --tools tools.json --server my-github-mcp
```

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

## License

MIT

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Good first issues will be labelled.

---

Built for the Claude / MCP developer ecosystem. Local-first. No required cloud services.
