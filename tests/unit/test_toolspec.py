"""Tests for tool-definition parsing and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from toolforge.core.toolspec import (
    ToolDefinitionError,
    duplicate_names,
    lightweight_entry,
    load_tools_file,
    parse_tools,
    parse_tools_json,
    short_description,
)


def test_accepts_list_and_tools_object() -> None:
    tool = {"name": "a", "description": "x", "inputSchema": {"type": "object"}}
    assert parse_tools([tool]) == parse_tools({"tools": [tool]})


def test_normalises_anthropic_and_openai_formats() -> None:
    schema = {"type": "object", "properties": {"q": {"type": "string"}}}
    anthropic = {"name": "a", "description": "A", "input_schema": schema}
    openai_flat = {"name": "b", "parameters": schema}
    openai_wrapped = {"type": "function", "function": {"name": "c", "parameters": schema}}

    tools = parse_tools([anthropic, openai_flat, openai_wrapped])

    assert [t["name"] for t in tools] == ["a", "b", "c"]
    for t in tools:
        assert t["inputSchema"] == schema
        assert "input_schema" not in t and "parameters" not in t
    assert tools[1]["description"] == ""  # missing description becomes ""


def test_preserves_extra_keys() -> None:
    tool = {"name": "a", "title": "Pretty A", "annotations": {"readOnlyHint": True}}
    parsed = parse_tools([tool])[0]
    assert parsed["title"] == "Pretty A"
    assert parsed["annotations"] == {"readOnlyHint": True}
    assert parsed["inputSchema"] == {}


@pytest.mark.parametrize(
    ("data", "fragment"),
    [
        ("nope", "expected a list of tools, got str"),
        ({"tools": "nope"}, "expected a list of tools, got str"),
        ({"name": "single"}, "object with a 'tools' key"),
        (["oops", 5], "tools[0]: expected an object, got str"),
        ([{"description": "no name"}], "tools[0]: 'name' must be a non-empty string"),
        ([{"name": "  "}], "'name' must be a non-empty string"),
        ([{"name": "a", "description": 3}], "'description' must be a string, got int"),
        ([{"name": "a", "inputSchema": []}], "input schema must be an object, got list"),
    ],
)
def test_rejects_invalid_input(data: object, fragment: str) -> None:
    with pytest.raises(ToolDefinitionError) as info:
        parse_tools(data)
    assert fragment in str(info.value)


def test_reports_every_problem_at_once() -> None:
    with pytest.raises(ToolDefinitionError) as info:
        parse_tools(["x", {"name": "ok"}, 7])
    assert info.value.problems == [
        "tools[0]: expected an object, got str",
        "tools[2]: expected an object, got int",
    ]


def test_problem_list_is_capped() -> None:
    with pytest.raises(ToolDefinitionError) as info:
        parse_tools(list(range(25)))
    assert "... and 15 more problem(s)" in str(info.value)


def test_parse_tools_json_reports_position() -> None:
    with pytest.raises(ToolDefinitionError, match=r"invalid JSON: .*line 1, column"):
        parse_tools_json("[{", source="x.json")


def test_load_tools_file_errors(tmp_path: Path) -> None:
    binary = tmp_path / "bin.json"
    binary.write_bytes(b"\xff\xfe\x00junk")
    with pytest.raises(ToolDefinitionError, match="not valid UTF-8"):
        load_tools_file(binary)

    with pytest.raises(ToolDefinitionError, match="cannot read file"):
        load_tools_file(tmp_path / "missing.json")


def test_duplicate_names() -> None:
    tools = parse_tools([{"name": "a"}, {"name": "b"}, {"name": "a"}, {"name": "a"}])
    assert duplicate_names(tools) == ["a"]


def test_short_description() -> None:
    assert short_description("  Read   a\nfile  ") == "Read a file"
    long = "word " * 60
    short = short_description(long)
    assert len(short) <= 120
    assert short.endswith("word…")
    # A single huge word is cut hard rather than reduced to nothing.
    assert short_description("x" * 300) == "x" * 119 + "…"


def test_lightweight_entry() -> None:
    entry = lightweight_entry({"name": "a", "description": "Does A.  Really."}, "gh")
    assert entry == {"name": "a", "server": "gh", "description": "Does A. Really."}
