"""Unit tests for token estimation."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import tiktoken

from toolforge.core import tokens
from toolforge.core.tokens import (
    STRUCTURAL_TOKENS_PER_TOOL,
    TokenizerUnavailableError,
    count_json_tokens,
    count_tokens,
    estimate_server_tokens,
    estimate_tool_tokens,
)


def test_count_tokens_empty() -> None:
    assert count_tokens("") == 0


def test_count_tokens_uses_encoding() -> None:
    # The offline test encoding is one token per byte.
    assert count_tokens("hello") == 5


@pytest.mark.real_tokenizer
def test_count_tokens_real_cl100k(real_encoding: tiktoken.Encoding) -> None:
    # "hello" is 1 token in cl100k_base
    assert count_tokens("hello") == 1


def test_special_token_text_is_counted_not_rejected() -> None:
    # tiktoken's encode() raises on "<|endoftext|>" by default; descriptions are
    # arbitrary text, so it must be counted as ordinary text.
    assert count_tokens("before <|endoftext|> after") == len("before <|endoftext|> after")


def test_count_json_tokens_compact_and_unicode() -> None:
    assert count_json_tokens({"a": 1}) == len('{"a":1}')
    assert count_json_tokens({"k": "é"}) == len('{"k":"é"}'.encode())


def test_estimate_tool_tokens_minimal() -> None:
    tool = {
        "name": "read_file",
        "description": "Read a file from disk",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    }
    result = estimate_tool_tokens(tool)
    assert result["name_tokens"] == len("read_file")
    assert result["description_tokens"] == len("Read a file from disk")
    assert result["input_schema_tokens"] > 0
    assert result["structural_tokens"] == STRUCTURAL_TOKENS_PER_TOOL
    assert result["total"] == (
        result["name_tokens"]
        + result["description_tokens"]
        + result["input_schema_tokens"]
        + result["structural_tokens"]
    )


@pytest.mark.parametrize("key", ["inputSchema", "input_schema", "parameters"])
def test_estimate_tool_tokens_reads_all_schema_formats(key: str) -> None:
    schema = {"type": "object", "properties": {"q": {"type": "string"}}}
    assert estimate_tool_tokens({"name": "t", key: schema})["input_schema_tokens"] == (
        count_json_tokens(schema)
    )


def test_estimate_server_tokens() -> None:
    tools = [
        {"name": "tool_a", "description": "A", "inputSchema": {"type": "object", "properties": {}}},
        {
            "name": "tool_b",
            "description": "B longer description here",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "x": {"type": "string", "description": "something"},
                    "y": {"type": "integer"},
                },
            },
        },
    ]
    stats = estimate_server_tokens(tools)
    assert stats["tool_count"] == 2
    assert stats["total_tokens"] == sum(t["total"] for t in stats["tools"])
    assert [t["name"] for t in stats["tools"]] == ["tool_b", "tool_a"]  # most expensive first
    assert stats["avg_tokens_per_tool"] == round(stats["total_tokens"] / 2, 1)


def test_estimate_server_tokens_empty() -> None:
    assert estimate_server_tokens([]) == {
        "tool_count": 0,
        "total_tokens": 0,
        "avg_tokens_per_tool": 0.0,
        "tools": [],
    }


def test_get_encoding_wraps_load_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.undo()  # use the real, cached loader
    tokens.get_encoding.cache_clear()

    def boom(name: str) -> tiktoken.Encoding:
        raise ConnectionError("network unreachable")

    monkeypatch.setattr(tiktoken, "get_encoding", boom)
    with pytest.raises(TokenizerUnavailableError, match="TIKTOKEN_CACHE_DIR"):
        tokens.get_encoding()
    tokens.get_encoding.cache_clear()


def _offline_env(tmp_path: Path) -> dict[str, str]:
    """Environment in which tiktoken cannot download or find its vocabulary."""
    env = {**os.environ}
    env["TIKTOKEN_CACHE_DIR"] = str(tmp_path / "empty-tiktoken-cache")
    for var in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        env[var] = "http://127.0.0.1:9"  # nothing listens on the discard port
    env.pop("NO_PROXY", None)
    env.pop("no_proxy", None)
    env["COLUMNS"] = "200"
    return env


def _toolforge(args: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "toolforge.cli.main", *args],
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_cli_works_offline_without_tokenizer(tmp_path: Path, sample_tools_file: Path) -> None:
    """Regression: importing the CLI used to download the vocabulary and crash offline."""
    env = _offline_env(tmp_path)

    version = _toolforge(["--version"], env, tmp_path)
    assert version.returncode == 0, version.stderr
    assert version.stdout.startswith("toolforge ")

    init = _toolforge(["init"], env, tmp_path)
    assert init.returncode == 0, init.stderr
    assert (tmp_path / ".toolforge.toml").is_file()

    audit = _toolforge(["audit", "--tools", str(sample_tools_file)], env, tmp_path)
    assert audit.returncode == 1
    assert "Could not load the 'cl100k_base' tokenizer vocabulary" in audit.stderr
    assert "Traceback" not in audit.stderr
