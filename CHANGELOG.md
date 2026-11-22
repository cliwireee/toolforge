# Changelog

All notable changes to Toolforge will be documented in this file.

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
