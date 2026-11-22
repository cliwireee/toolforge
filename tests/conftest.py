"""Shared fixtures.

By default every test runs with a deterministic offline tokenizer: a real
``tiktoken.Encoding`` with one token per byte and no merges. Tests marked
``real_tokenizer`` use the real cl100k_base vocabulary instead; they are skipped
when it cannot be loaded, except in CI (``CI`` env var set), where they fail.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
import tiktoken

from toolforge.core import tokens
from toolforge.utils import config as config_module

FIXTURES = Path(__file__).parent / "fixtures"


def byte_encoding() -> tiktoken.Encoding:
    return tiktoken.Encoding(
        name="toolforge-test-bytes",
        pat_str=r"""\s+|\S+""",
        mergeable_ranks={bytes([i]): i for i in range(256)},
        special_tokens={"<|endoftext|>": 256},
    )


@pytest.fixture(autouse=True)
def offline_tokenizer(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    if request.node.get_closest_marker("real_tokenizer") is None:
        encoding = byte_encoding()
        monkeypatch.setattr(tokens, "get_encoding", lambda: encoding)
    yield


@pytest.fixture
def real_encoding() -> tiktoken.Encoding:
    try:
        return tokens.get_encoding()
    except tokens.TokenizerUnavailableError as exc:
        if os.environ.get("CI"):
            pytest.fail(f"real tokenizer required in CI: {exc}")
        pytest.skip(f"cl100k_base vocabulary unavailable offline: {exc}")


@pytest.fixture(autouse=True)
def isolated_user_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Never read the developer's real ~/.config/toolforge during tests."""
    user_dir = tmp_path / "user-config"
    monkeypatch.setattr(config_module, "default_config_dir", lambda: user_dir)
    return user_dir


@pytest.fixture
def sample_tools_file() -> Path:
    return FIXTURES / "sample_tools.json"
