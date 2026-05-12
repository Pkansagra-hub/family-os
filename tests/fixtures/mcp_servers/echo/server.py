"""Echo MCP server — in-tree fixture for MS-5 PR#2 transport tests.

Run via ``python -m tests.fixtures.mcp_servers.echo.server``. Exposes
two tools:

* ``echo`` — returns the structured ``message`` argument verbatim.
* ``add`` — sums two integers; lets us verify input_schema validation.

Implemented with fastmcp's :class:`FastMCP` so the wire format matches
exactly what real adapters will use. No network, no auth, no secrets
— purely local stdio JSON-RPC.
"""

from __future__ import annotations

from fastmcp import FastMCP

mcp: FastMCP = FastMCP(name="family-os-echo")


@mcp.tool
def echo(message: str) -> dict[str, str]:
    """Return the message back to the caller."""
    return {"message": message}


@mcp.tool
def add(a: int, b: int) -> dict[str, int]:
    """Sum two integers."""
    return {"sum": a + b}


if __name__ == "__main__":
    mcp.run()
