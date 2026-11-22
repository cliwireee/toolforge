"""Unit tests for token estimation."""

from toolforge.core.tokens import count_tokens, estimate_tool_tokens, estimate_server_tokens


def test_count_tokens_empty():
    assert count_tokens("") == 0


def test_count_tokens_simple():
    # "hello" is 1 token in cl100k_base
    assert count_tokens("hello") == 1


def test_estimate_tool_tokens_minimal():
    tool = {
        "name": "read_file",
        "description": "Read a file from disk",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"}
            },
            "required": ["path"]
        }
    }
    result = estimate_tool_tokens(tool)
    assert result["total"] > 0
    assert result["name_tokens"] > 0
    assert result["description_tokens"] > 0
    assert result["input_schema_tokens"] > 0
    assert result["total"] == (
        result["name_tokens"]
        + result["description_tokens"]
        + result["input_schema_tokens"]
        + result["structural_tokens"]
    )


def test_estimate_server_tokens():
    tools = [
        {
            "name": "tool_a",
            "description": "A",
            "inputSchema": {"type": "object", "properties": {}},
        },
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
    assert stats["total_tokens"] > 0
    assert len(stats["tools"]) == 2
    # Most expensive first
    assert stats["tools"][0]["total"] >= stats["tools"][1]["total"]
    # Name string is preserved
    assert isinstance(stats["tools"][0]["name"], str)
