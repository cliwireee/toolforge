# Contributing to Toolforge

Thank you for your interest in improving Toolforge.

## Development Setup

```bash
git clone https://github.com/cliwireee/toolforge.git
cd toolforge
python -m venv .venv
source .venv/bin/activate   # or Windows equivalent
pip install -e ".[dev,mcp]"
pytest
ruff check src tests
mypy
```

Tests run offline: a deterministic stand-in tokenizer replaces `cl100k_base` unless a test is
marked `real_tokenizer` (skipped offline, required in CI). Live-discovery tests start a tiny MCP
server from `tests/fixtures/demo_server.py`.

## Good First Issues

Look for issues labelled `good first issue`. Typical starter tasks:

- Improve token estimation accuracy against real Claude `/context` output
- Add more example tool fixtures for tests
- Expand the `init` command with additional profile templates
- Documentation improvements

## Pull Request Process

1. Fork the repository and create a feature branch.
2. Add tests for new behaviour.
3. Ensure `pytest`, `ruff check src tests` and `mypy` pass.
4. Open a PR with a clear description of the problem and solution.

## Code Style

- Python 3.11+
- Type hints required on public functions
- Keep the core dependency set small
- Prefer explicit, readable code over cleverness

## Reporting Bugs

Please include:

- Toolforge version
- Python version
- Exact command that failed
- Sample tool JSON (redacted) if relevant
