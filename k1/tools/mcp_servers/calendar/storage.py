"""
k1.tools.mcp_servers.calendar.storage -- Calendar SQLite storage backend.

Provides async-compatible calendar event persistence using SQLite.
All operations are synchronous internally (SQLite is local and fast)
but exposed via async interface for consistency with MCP server pattern.

Storage location:
  - Production: ~/.familyos/calendar.db
  - Testing: in-memory SQLite (":memory:")

Thread safety: SQLite connections are per-instance. Each CalendarStorage
instance manages its own connection. Not shared across threads.

References:
  - fabric_tool_implementation_plan.md Phase 1, Section 3.1.2
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from k1.tools.mcp_servers.calendar.models import CalendarEvent

logger = logging.getLogger(__name__)

# Default database path
DEFAULT_DB_PATH = ":memory:"


class CalendarStorageError(Exception):
    """Base exception for calendar storage operations."""


class CalendarStorage:
    """
    SQLite-backed calendar event storage.

    Manages the full lifecycle of calendar events: create, list, delete.
    Uses a single SQLite connection with WAL mode for read concurrency.

    Args:
        db_path: Path to SQLite database file.
            Use ":memory:" for in-memory testing.
    """

    __slots__ = ("_db_path", "_conn")

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._initialize()

    def _initialize(self) -> None:
        """Create connection and ensure schema exists."""
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        if self._db_path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                event_id    TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                start_time  TEXT NOT NULL,
                end_time    TEXT NOT NULL,
                location    TEXT,
                description TEXT,
                attendees   TEXT,
                created_at  TEXT NOT NULL
            )
        """
        )
        self._conn.commit()
        logger.debug("CalendarStorage initialized (db=%s)", self._db_path)

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    async def create_event(
        self,
        title: str,
        start_time: str,
        end_time: str,
        location: Optional[str] = None,
        description: Optional[str] = None,
        attendees: Optional[List[str]] = None,
    ) -> CalendarEvent:
        """
        Create and persist a new calendar event.

        Args:
            title: Event title (required).
            start_time: ISO 8601 datetime (required).
            end_time: ISO 8601 datetime (required).
            location: Optional location.
            description: Optional description.
            attendees: Optional list of attendee names.

        Returns:
            The created CalendarEvent with generated event_id.

        Raises:
            CalendarStorageError: If database write fails.
        """
        event_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        attendees_str = ",".join(attendees) if attendees else ""

        try:
            assert self._conn is not None
            self._conn.execute(
                """
                INSERT INTO events (event_id, title, start_time, end_time,
                                    location, description, attendees, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    title,
                    start_time,
                    end_time,
                    location or "",
                    description or "",
                    attendees_str,
                    created_at,
                ),
            )
            self._conn.commit()
        except sqlite3.Error as exc:
            raise CalendarStorageError(f"Failed to create event: {exc}") from exc

        return CalendarEvent(
            event_id=event_id,
            title=title,
            start_time=start_time,
            end_time=end_time,
            location=location,
            description=description,
            attendees=tuple(attendees or []),
            created_at=created_at,
        )

    async def list_events(
        self,
        start_date: str,
        end_date: str,
        max_results: int = 50,
    ) -> List[CalendarEvent]:
        """
        List events within a date range, sorted by start_time.

        Args:
            start_date: Range start (ISO 8601 date, inclusive).
            end_date: Range end (ISO 8601 date, inclusive).
            max_results: Maximum events to return (default 50).

        Returns:
            List of CalendarEvent sorted by start_time ascending.
        """
        try:
            assert self._conn is not None
            cursor = self._conn.execute(
                """
                SELECT event_id, title, start_time, end_time,
                       location, description, attendees, created_at
                FROM events
                WHERE start_time >= ? AND start_time <= ?
                ORDER BY start_time ASC
                LIMIT ?
                """,
                (start_date, end_date + "T23:59:59", max_results),
            )
            rows = cursor.fetchall()
        except sqlite3.Error as exc:
            raise CalendarStorageError(f"Failed to list events: {exc}") from exc

        events: List[CalendarEvent] = []
        for row in rows:
            attendees_raw = row["attendees"]
            attendees_tuple = (
                tuple(a.strip() for a in attendees_raw.split(",") if a.strip())
                if attendees_raw
                else ()
            )
            events.append(
                CalendarEvent(
                    event_id=row["event_id"],
                    title=row["title"],
                    start_time=row["start_time"],
                    end_time=row["end_time"],
                    location=row["location"] or None,
                    description=row["description"] or None,
                    attendees=attendees_tuple,
                    created_at=row["created_at"],
                )
            )
        return events

    async def delete_event(self, event_id: str) -> bool:
        """
        Delete an event by ID.

        Args:
            event_id: The unique event identifier.

        Returns:
            True if an event was deleted, False if not found.
        """
        try:
            assert self._conn is not None
            cursor = self._conn.execute(
                "DELETE FROM events WHERE event_id = ?",
                (event_id,),
            )
            self._conn.commit()
            return cursor.rowcount > 0
        except sqlite3.Error as exc:
            raise CalendarStorageError(f"Failed to delete event: {exc}") from exc

    async def get_event(self, event_id: str) -> Optional[CalendarEvent]:
        """
        Get a single event by ID.

        Args:
            event_id: The unique event identifier.

        Returns:
            CalendarEvent if found, None otherwise.
        """
        try:
            assert self._conn is not None
            cursor = self._conn.execute(
                """
                SELECT event_id, title, start_time, end_time,
                       location, description, attendees, created_at
                FROM events
                WHERE event_id = ?
                """,
                (event_id,),
            )
            row = cursor.fetchone()
        except sqlite3.Error as exc:
            raise CalendarStorageError(f"Failed to get event: {exc}") from exc

        if row is None:
            return None

        attendees_raw = row["attendees"]
        attendees_tuple = (
            tuple(a.strip() for a in attendees_raw.split(",") if a.strip()) if attendees_raw else ()
        )
        return CalendarEvent(
            event_id=row["event_id"],
            title=row["title"],
            start_time=row["start_time"],
            end_time=row["end_time"],
            location=row["location"] or None,
            description=row["description"] or None,
            attendees=attendees_tuple,
            created_at=row["created_at"],
        )

    async def count_events(self) -> int:
        """Return total number of events in storage."""
        assert self._conn is not None
        cursor = self._conn.execute("SELECT COUNT(*) FROM events")
        return cursor.fetchone()[0]
