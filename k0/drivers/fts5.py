"""
PostgreSQL Full-Text Search Driver - Outbox Worker Implementation

Purpose:
    Processes outbox entries with alias='st_fts' to index episodic memory text
    into PostgreSQL tsvector for fast full-text search.

Architecture:
    - Reads from st_hipp_events (enriched hippocampus data)
    - Indexes into st_hipp_fts table with tsvector column
    - Supports ranking, phrase queries, and boolean operators
    - Emits completion event to bus

Contract:
    - apply(entry: OutboxEntry) -> None
    - build_driver() factory function
    - Async context manager support (__aenter__/__aexit__)

Performance:
    - Target: <20ms P95 per event
    - Batch indexing: 128 events per UnitOfWork
    - Incremental updates (no full reindex required)

Usage (from outbox worker):
    driver = await build_driver()
    async with driver:
        for entry in outbox_batch:
            await driver.apply(entry)
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncpg

    from k0.storage.outbox import OutboxEntry

from k0.db.connection import connection_scope

logger = logging.getLogger(__name__)


class FTSDriver:
    """
    PostgreSQL full-text search indexer for episodic memory events.

    Uses async connection pool for all database access.
    """

    def __init__(self):
        """
        Initialize FTS driver.

        Uses global connection pool (configured by kernel) for all database access.
        No instance-level database path or connection needed.
        """
        pass

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        pass

    async def _ensure_fts_table(self, conn: "asyncpg.Connection"):
        """
        Create FTS table with tsvector if not exists.

        Args:
            conn: asyncpg connection

        Schema:
            - event_id (TEXT, primary key)
            - tenant_id (TEXT, for multi-tenancy)
            - space_id (TEXT, for ACL filtering)
            - text (TEXT, main searchable content)
            - text_normalized (TEXT, lowercased for fuzzy matching)
            - entities (TEXT, searchable entity list)
            - activity_type (TEXT, for activity filtering)
            - event_time_utc (BIGINT, for time-based ranking)
            - content_tsvector (tsvector, generated column for FTS)
        """
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS st_hipp_fts (
                event_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                space_id TEXT NOT NULL,
                text TEXT,
                text_normalized TEXT,
                entities TEXT,
                activity_type TEXT,
                event_time_utc BIGINT,
                content_tsvector tsvector GENERATED ALWAYS AS (
                    setweight(to_tsvector('english', COALESCE(text, '')), 'A') ||
                    setweight(to_tsvector('english', COALESCE(entities, '')), 'B')
                ) STORED
            )
            """
        )
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_hipp_fts_tsvector
            ON st_hipp_fts USING GIN(content_tsvector)
            """
        )
        logger.debug("PostgreSQL FTS table st_hipp_fts ensured")

    async def apply(self, entry: "OutboxEntry") -> None:
        """
        Process outbox entry - index event into PostgreSQL FTS.

        Args:
            entry: Outbox entry with alias='st_fts'

        Payload Schema:
            {
                "event_id": "evt_...",
                "wal_pos": 123,
                "action": "index" | "delete"
            }

        Raises:
            ValueError: If payload missing required fields
            asyncpg.PostgresError: If database operation fails
        """
        async with connection_scope() as conn:
            # Ensure FTS table exists (idempotent)
            await self._ensure_fts_table(conn)

            try:
                # Parse payload
                payload = json.loads(entry.payload)
                event_id = payload.get("event_id")
                action = payload.get("action", "index")

                if not event_id:
                    raise ValueError(f"Missing event_id in payload: {entry.payload}")

                logger.debug(f"FTS: Processing {action} for event_id={event_id}")

                if action == "index":
                    await self._index_event(conn, event_id)
                elif action == "delete":
                    await self._delete_event(conn, event_id)
                else:
                    raise ValueError(f"Unknown action: {action}")

            except json.JSONDecodeError as e:
                logger.error(f"FTS: Invalid JSON payload: {entry.payload}", exc_info=e)
                raise

    async def _index_event(self, conn: "asyncpg.Connection", event_id: str):
        """
        Index event from st_hipp_events into FTS table.

        Args:
            conn: asyncpg connection
            event_id: Event identifier to index
        """
        # Read enriched event from st_hipp_events
        row = await conn.fetchrow(
            """
            SELECT
                event_id,
                tenant_id,
                space_id,
                text,
                text_normalized,
                entities_json,
                activity_type,
                event_time_utc
            FROM st_hipp_events
            WHERE event_id = $1
            """,
            event_id,
        )

        if not row:
            logger.warning(f"FTS: Event {event_id} not found in st_hipp_events (may be deleted)")
            return

        # Parse entities JSON (for searchable entity list)
        entities_json = row["entities_json"] or "[]"
        try:
            entities_list = json.loads(entities_json)
            entities_text = " ".join(entities_list) if entities_list else ""
        except json.JSONDecodeError:
            entities_text = ""
            logger.warning(f"FTS: Invalid entities_json for {event_id}")

        # Insert into FTS table (or update if exists)
        await conn.execute(
            """
            INSERT INTO st_hipp_fts(
                event_id,
                tenant_id,
                space_id,
                text,
                text_normalized,
                entities,
                activity_type,
                event_time_utc
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT(event_id) DO UPDATE SET
                text = EXCLUDED.text,
                text_normalized = EXCLUDED.text_normalized,
                entities = EXCLUDED.entities,
                activity_type = EXCLUDED.activity_type,
                event_time_utc = EXCLUDED.event_time_utc
            """,
            row["event_id"],
            row["tenant_id"],
            row["space_id"],
            row["text"],
            row["text_normalized"],
            entities_text,
            row["activity_type"],
            row["event_time_utc"],
        )

        logger.info(f"FTS: Indexed event {event_id}")

    async def _delete_event(self, conn: "asyncpg.Connection", event_id: str):
        """
        Delete event from FTS table.

        Args:
            conn: asyncpg connection
            event_id: Event identifier to delete
        """
        await conn.execute(
            """
            DELETE FROM st_hipp_fts WHERE event_id = $1
            """,
            event_id,
        )

        logger.info(f"FTS: Deleted event {event_id}")


async def build_driver() -> FTSDriver:
    """
    Factory function to build FTSDriver instance.

    Uses global connection pool configured by kernel bootstrap.
    No environment variables needed - pool is already configured.

    Returns:
        Configured FTSDriver instance
    """
    return FTSDriver()
