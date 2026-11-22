"""Tiny stdio MCP server used by the live-discovery tests (works on mcp 1.x and 2.x)."""

from toolforge.mcp._compat import server_class

server = server_class()("demo")


def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


def echo(text: str) -> str:
    """Echo the given text back."""
    return text


def search_issues(query: str, limit: int = 10) -> str:
    """Search issues in a repository by free-text query."""
    return f"{query}:{limit}"


for fn in (add, echo, search_issues):
    server.add_tool(fn)

if __name__ == "__main__":
    server.run()
