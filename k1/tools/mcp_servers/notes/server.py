"""
k1.tools.mcp_servers.notes.server -- Notes MCP Server (FastMCP, stdio).

Built with FastMCP -- decorator-based tool registration replaces
hand-rolled JSON-RPC routing. Compare with the Phase 1-2 servers
(calendar, weather) that used manual message dispatch.

Usage:
  python -m k1.tools.mcp_servers.notes.server

Testing:
  from fastmcp import Client
  async with Client(mcp) as client:
      result = await client.call_tool("notes_list", {})

References:
  - fabric_tool_implementation_plan.md Phase 3, Section 5.1
  - https://gofastmcp.com
"""

from __future__ import annotations

import logging
from typing import Optional

from fastmcp import FastMCP

from k1.tools.mcp_servers.notes.storage import NoteStorage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Server + Storage
# ---------------------------------------------------------------------------

_storage: Optional[NoteStorage] = None


def _get_storage() -> NoteStorage:
    """Return the active NoteStorage instance."""
    global _storage
    if _storage is None:
        _storage = NoteStorage(db_path=":memory:")
    return _storage


def set_storage(storage: NoteStorage) -> None:
    """Inject a storage instance (for testing)."""
    global _storage
    _storage = storage


mcp = FastMCP(
    "notes-mcp",
    instructions="Family notes management. Create, list, and search notes.",
)

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def notes_list(
    tag: str | None = None,
    max_results: int = 50,
) -> dict:
    """List all notes, optionally filtered by tag.

    Args:
        tag: Optional tag to filter notes by.
        max_results: Maximum notes to return (default 50, max 200).

    Returns:
        Dictionary with 'notes' list and 'count'.
    """
    storage = _get_storage()
    notes = await storage.list_notes(tag=tag, max_results=max_results)
    return {
        "notes": [n.to_summary() for n in notes],
        "count": len(notes),
    }


@mcp.tool()
async def notes_create(
    title: str,
    content: str,
    tags: str = "",
) -> dict:
    """Create a new note.

    Args:
        title: Note title.
        content: Note body text.
        tags: Comma-separated tags (optional).

    Returns:
        Dictionary with 'note_id' and 'status'.
    """
    if not title:
        raise ValueError("title is required")
    if not content:
        raise ValueError("content is required")

    storage = _get_storage()
    note = await storage.create_note(title=title, content=content, tags=tags)
    return {
        "note_id": note.note_id,
        "status": "created",
    }


@mcp.tool()
async def notes_search(
    query: str,
    max_results: int = 20,
) -> dict:
    """Search notes by keyword in title and content.

    Args:
        query: Search keyword or phrase.
        max_results: Maximum results to return (default 20, max 100).

    Returns:
        Dictionary with 'results' list and 'count'.
    """
    if not query:
        raise ValueError("query is required")

    storage = _get_storage()
    notes = await storage.search_notes(query=query, max_results=max_results)
    return {
        "results": [n.to_search_result() for n in notes],
        "count": len(notes),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def create_server(db_path: str = ":memory:") -> FastMCP:
    """
    Create and configure the notes MCP server.

    Args:
        db_path: SQLite database path. Default ":memory:" for testing.

    Returns:
        Configured FastMCP instance.
    """
    set_storage(NoteStorage(db_path=db_path))
    return mcp


if __name__ == "__main__":
    create_server()
    mcp.run()
