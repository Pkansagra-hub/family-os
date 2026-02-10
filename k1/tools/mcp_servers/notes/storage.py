"""
k1.tools.mcp_servers.notes.storage -- SQLite storage for notes.

Same pattern as CalendarStorage: async methods wrapping synchronous
SQLite operations with in-memory support for testing.

References:
  - k1/tools/mcp_servers/calendar/storage.py (pattern)
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import List, Optional

from k1.tools.mcp_servers.notes.models import Note


class NoteStorage:
    """
    SQLite-backed storage for notes.

    Args:
        db_path: SQLite database path. Use ":memory:" for testing.
    """

    __slots__ = ("_conn",)

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                note_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    async def create_note(
        self,
        title: str,
        content: str,
        tags: str = "",
    ) -> Note:
        """Create and persist a new note."""
        note = Note(
            title=title,
            content=content,
            tags=tuple(t.strip() for t in tags.split(",") if t.strip()) if tags else (),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._conn.execute(
            "INSERT INTO notes (note_id, title, content, tags, created_at) VALUES (?, ?, ?, ?, ?)",
            (note.note_id, note.title, note.content, ",".join(note.tags), note.created_at),
        )
        self._conn.commit()
        return note

    async def list_notes(
        self,
        tag: Optional[str] = None,
        max_results: int = 50,
    ) -> List[Note]:
        """List notes, optionally filtered by tag, ordered by created_at desc."""
        max_results = min(max_results, 200)

        if tag:
            rows = self._conn.execute(
                "SELECT * FROM notes WHERE tags LIKE ? ORDER BY created_at DESC LIMIT ?",
                (f"%{tag}%", max_results),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM notes ORDER BY created_at DESC LIMIT ?",
                (max_results,),
            ).fetchall()

        return [self._row_to_note(row) for row in rows]

    async def search_notes(
        self,
        query: str,
        max_results: int = 20,
    ) -> List[Note]:
        """Search notes by keyword in title and content."""
        max_results = min(max_results, 100)
        rows = self._conn.execute(
            """
            SELECT * FROM notes
            WHERE title LIKE ? OR content LIKE ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (f"%{query}%", f"%{query}%", max_results),
        ).fetchall()
        return [self._row_to_note(row) for row in rows]

    async def get_note(self, note_id: str) -> Optional[Note]:
        """Get a single note by ID."""
        row = self._conn.execute("SELECT * FROM notes WHERE note_id = ?", (note_id,)).fetchone()
        return self._row_to_note(row) if row else None

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    @staticmethod
    def _row_to_note(row: sqlite3.Row) -> Note:
        tags_str = row["tags"]
        tags = tuple(t.strip() for t in tags_str.split(",") if t.strip()) if tags_str else ()
        return Note(
            note_id=row["note_id"],
            title=row["title"],
            content=row["content"],
            tags=tags,
            created_at=row["created_at"],
        )
