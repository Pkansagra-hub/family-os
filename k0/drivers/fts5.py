"""
FTS5 Full-Text Search Driver - Outbox Worker Implementation

Purpose:
    Processes outbox entries with alias='st_fts' to index episodic memory text
    into SQLite FTS5 virtual tables for fast full-text search.

Architecture:
    - Reads from st_hipp_events (enriched hippocampus data)
    - Indexes into FTS5 virtual table (st_hipp_fts)
    - Supports ranking, phrase queries, and NEAR operators
    - Emits completion event to bus

Contract:
    - apply(entry: OutboxEntry) -> None
    - build_driver() factory function
    - Context manager support (__enter__/__exit__)

Performance:
    - Target: <20ms P95 per event
    - Batch indexing: 128 events per UnitOfWork
    - Incremental updates (no full reindex required)

Usage (from outbox worker):
    driver = build_driver()
    with driver:
        for entry in outbox_batch:
            driver.apply(entry)
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from k0.storage.outbox import OutboxEntry

from k0.uow.connection_pool import connection_scope

logger = logging.getLogger(__name__)


class FTS5Driver:
    """
    FTS5 full-text search indexer for episodic memory events.

    Uses thread-local connections from the connection pool to support
    background outbox worker threads.
    """

    def __init__(self):
        """
        Initialize FTS5 driver.

        Uses global connection pool (configured by kernel) for all database access.
        No instance-level database path or connection needed.
        """
        pass

    def _ensure_fts_table(self, conn):
        """
        Create FTS5 virtual table if not exists.

        Args:
            conn: SQLite connection (thread-local)

        Schema:
            - event_id (TEXT, primary key linkage)
            - tenant_id (TEXT, for multi-tenancy)
            - space_id (TEXT, for ACL filtering)
            - text (TEXT, main searchable content)
            - text_normalized (TEXT, lowercased for fuzzy matching)
            - entities (TEXT, searchable entity list)
            - activity_type (TEXT, for activity filtering)
            - event_time_utc (INTEGER, for time-based ranking)
        """
        # Create FTS5 virtual table with tokenize=porter for stemming
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS st_hipp_fts USING fts5(
                event_id UNINDEXED,
                tenant_id UNINDEXED,
                space_id UNINDEXED,
                text,
                text_normalized,
                entities,
                activity_type UNINDEXED,
                event_time_utc UNINDEXED,
                tokenize='porter unicode61'
            )
        """
        )
        conn.commit()
        logger.debug("FTS5 virtual table st_hipp_fts ensured")

    def apply(self, entry: OutboxEntry) -> None:
        """
        Process outbox entry - index event into FTS5.

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
            sqlite3.Error: If database operation fails
        """
        # Use thread-local connection from pool
        with connection_scope() as conn:
            conn.row_factory = sqlite3.Row

            # Ensure FTS5 table exists (idempotent)
            self._ensure_fts_table(conn)

            try:
                # Parse payload
                payload = json.loads(entry.payload)
                event_id = payload.get("event_id")
                action = payload.get("action", "index")

                if not event_id:
                    raise ValueError(f"Missing event_id in payload: {entry.payload}")

                logger.debug(f"FTS5: Processing {action} for event_id={event_id}")

                if action == "index":
                    self._index_event(conn, event_id)
                elif action == "delete":
                    self._delete_event(conn, event_id)
                else:
                    raise ValueError(f"Unknown action: {action}")

            except json.JSONDecodeError as e:
                logger.error(f"FTS5: Invalid JSON payload: {entry.payload}", exc_info=e)
                conn.rollback()
                raise
            except Exception as e:
                logger.error(f"FTS5: Failed to process entry {entry.id}", exc_info=e)
                conn.rollback()
                raise

    def _index_event(self, conn, event_id: str):
        """
        Index event from st_hipp_events into FTS5.

        Args:
            conn: SQLite connection (thread-local)
            event_id: Event identifier to index
        """
        # Read enriched event from st_hipp_events
        cursor = conn.execute(
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
            WHERE event_id = ?
        """,
            (event_id,),
        )

        row = cursor.fetchone()
        if not row:
            logger.warning(f"FTS5: Event {event_id} not found in st_hipp_events (may be deleted)")
            return

        # Parse entities JSON (for searchable entity list)
        entities_json = row["entities_json"] or "[]"
        try:
            entities_list = json.loads(entities_json)
            entities_text = " ".join(entities_list) if entities_list else ""
        except json.JSONDecodeError:
            entities_text = ""
            logger.warning(f"FTS5: Invalid entities_json for {event_id}")

        # Insert into FTS5 (or replace if exists)
        conn.execute(
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
                text = excluded.text,
                text_normalized = excluded.text_normalized,
                entities = excluded.entities,
                activity_type = excluded.activity_type,
                event_time_utc = excluded.event_time_utc
        """,
            (
                row["event_id"],
                row["tenant_id"],
                row["space_id"],
                row["text"],
                row["text_normalized"],
                entities_text,
                row["activity_type"],
                row["event_time_utc"],
            ),
        )

        conn.commit()
        logger.info(f"FTS5: Indexed event {event_id}")

    def _delete_event(self, conn, event_id: str):
        """
        Delete event from FTS5 index.

        Args:
            conn: SQLite connection (thread-local)
            event_id: Event identifier to delete
        """
        conn.execute(
            """
            DELETE FROM st_hipp_fts WHERE event_id = ?
        """,
            (event_id,),
        )

        conn.commit()
        logger.info(f"FTS5: Deleted event {event_id}")


def build_driver() -> FTS5Driver:
    """
    Factory function to build FTS5Driver instance.

    Uses global connection pool configured by kernel bootstrap.
    No environment variables needed - pool is already configured.

    Returns:
        Configured FTS5Driver instance
    """
    return FTS5Driver()
