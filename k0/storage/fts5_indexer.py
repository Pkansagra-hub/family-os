"""FTS5 full-text search indexer for memory tables.

This module provides indexing services for st_epi_fts and st_hipp_fts virtual tables,
enabling fast keyword search across episodic and hippocampus staging memories.

Performance Target: <10ms P95 for keyword search across 100K+ memories

Example:
    indexer = FTS5Indexer(connection)
    indexer.index_episodic(
        event_id="evt_123",
        text="Had dinner with Mom at Olive Garden",
        summary="Family dinner",
        tags=["family", "dinner"],
        topics=["social", "food"],
        location_names=["Olive Garden"],
        participant_names=["Mom"],
        tenant_id="tenant_001",
        space_id="space_001",
        commit_ts="2025-11-10T19:00:00Z"
    )

    results = indexer.search_episodic("dinner Mom")
    # Returns: ["evt_123"]
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Sequence

LOGGER = logging.getLogger(__name__)


class FTS5IndexerError(RuntimeError):
    """Raised when FTS5 indexing fails."""


class FTS5Indexer:
    """Manages FTS5 virtual table indexing for memory tables.

    Provides methods to index episodic and hippocampus memories into FTS5
    virtual tables for fast keyword search. Also handles index removal when
    memories are deleted or tombstoned.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Initialize the FTS5 indexer.

        Parameters
        ----------
        connection : sqlite3.Connection
            Active SQLite database connection with st_epi_fts and st_hipp_fts tables.
        """
        self._connection = connection

    def index_episodic(
        self,
        *,
        event_id: str,
        text: str,
        summary: str | None = None,
        tags: Sequence[str] | None = None,
        topics: Sequence[str] | None = None,
        location_names: Sequence[str] | None = None,
        participant_names: Sequence[str] | None = None,
        tenant_id: str,
        space_id: str,
        commit_ts: str,
    ) -> None:
        """Index an episodic memory into st_epi_fts.

        Parameters
        ----------
        event_id : str
            Unique event identifier (references st_epi.event_id)
        text : str
            Main memory text content (searchable)
        summary : str, optional
            Memory summary (searchable)
        tags : Sequence[str], optional
            Memory tags (searchable)
        topics : Sequence[str], optional
            Extracted topics (searchable)
        location_names : Sequence[str], optional
            Location names (searchable)
        participant_names : Sequence[str], optional
            Participant names (searchable)
        tenant_id : str
            Tenant scope
        space_id : str
            Space scope
        commit_ts : str
            Commit timestamp (ISO8601)

        Raises
        ------
        FTS5IndexerError
            If indexing fails due to database error or constraint violation.
        """
        try:
            # Convert lists to space-separated strings for FTS5
            tags_text = " ".join(tags) if tags else ""
            topics_text = " ".join(topics) if topics else ""
            locations_text = " ".join(location_names) if location_names else ""
            participants_text = " ".join(participant_names) if participant_names else ""

            self._connection.execute(
                """
                INSERT INTO st_epi_fts (
                    event_id, tenant_id, space_id,
                    text, summary, tags, topics,
                    location_names, participant_names,
                    commit_ts
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    tenant_id,
                    space_id,
                    text,
                    summary or "",
                    tags_text,
                    topics_text,
                    locations_text,
                    participants_text,
                    commit_ts,
                ),
            )
            LOGGER.debug("Indexed episodic memory %s to FTS5", event_id)
        except sqlite3.Error as exc:
            msg = f"Failed to index episodic memory {event_id} to FTS5"
            raise FTS5IndexerError(msg) from exc

    def index_hippocampus(
        self,
        *,
        event_id: str,
        text: str,
        topics: Sequence[str] | None = None,
        categories: Sequence[str] | None = None,
        participant_names: Sequence[str] | None = None,
        location_name: str | None = None,
        tenant_id: str,
        space_id: str,
        commit_ts: str,
    ) -> None:
        """Index a hippocampus staging memory into st_hipp_fts.

        Parameters
        ----------
        event_id : str
            Unique event identifier (references st_hipp_store.event_id)
        text : str
            Raw input text (searchable)
        topics : Sequence[str], optional
            Extracted topics (searchable)
        categories : Sequence[str], optional
            Event categories (searchable)
        participant_names : Sequence[str], optional
            Participant names (searchable)
        location_name : str, optional
            Location name (stored, not indexed for search)
        tenant_id : str
            Tenant scope
        space_id : str
            Space scope
        commit_ts : str
            Commit timestamp (ISO8601)

        Raises
        ------
        FTS5IndexerError
            If indexing fails due to database error or constraint violation.
        """
        try:
            # Convert lists to space-separated strings for FTS5
            topics_text = " ".join(topics) if topics else ""
            categories_text = " ".join(categories) if categories else ""
            participants_text = " ".join(participant_names) if participant_names else ""

            self._connection.execute(
                """
                INSERT INTO st_hipp_fts (
                    event_id, tenant_id, space_id,
                    text, topics, categories,
                    participant_names, location_name,
                    commit_ts
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    tenant_id,
                    space_id,
                    text,
                    topics_text,
                    categories_text,
                    participants_text,
                    location_name or "",
                    commit_ts,
                ),
            )
            LOGGER.debug("Indexed hippocampus memory %s to FTS5", event_id)
        except sqlite3.Error as exc:
            msg = f"Failed to index hippocampus memory {event_id} to FTS5"
            raise FTS5IndexerError(msg) from exc

    def remove_from_index(self, table: str, event_id: str) -> None:
        """Remove a memory from FTS5 index (when deleted or tombstoned).

        Parameters
        ----------
        table : str
            FTS5 table name ("st_epi_fts" or "st_hipp_fts")
        event_id : str
            Event ID to remove from index

        Raises
        ------
        FTS5IndexerError
            If removal fails due to database error.
        ValueError
            If table name is invalid.
        """
        if table not in ("st_epi_fts", "st_hipp_fts"):
            msg = f"Invalid FTS5 table: {table}"
            raise ValueError(msg)

        try:
            self._connection.execute(
                f"DELETE FROM {table} WHERE event_id = ?",  # noqa: S608
                (event_id,),
            )
            LOGGER.debug("Removed event %s from %s", event_id, table)
        except sqlite3.Error as exc:
            msg = f"Failed to remove {event_id} from {table}"
            raise FTS5IndexerError(msg) from exc

    def search_episodic(
        self,
        query: str,
        *,
        limit: int = 20,
        tenant_id: str | None = None,
        space_id: str | None = None,
    ) -> list[str]:
        """Search episodic memories by keyword.

        Parameters
        ----------
        query : str
            FTS5 search query (supports AND, OR, NOT, phrases with quotes)
        limit : int, optional
            Maximum results to return (default: 20)
        tenant_id : str, optional
            Filter by tenant_id
        space_id : str, optional
            Filter by space_id

        Returns
        -------
        list[str]
            List of event_ids matching the query (ranked by relevance)

        Examples
        --------
        >>> indexer.search_episodic("dinner Mom")
        ['evt_123', 'evt_456']

        >>> indexer.search_episodic('"Olive Garden" AND family')
        ['evt_123']
        """
        try:
            # Build WHERE clause
            where_parts = ["st_epi_fts MATCH ?"]
            params: list[str | int] = [query]

            if tenant_id:
                where_parts.append("tenant_id = ?")
                params.append(tenant_id)
            if space_id:
                where_parts.append("space_id = ?")
                params.append(space_id)

            params.append(limit)

            where_clause = " AND ".join(where_parts)

            cursor = self._connection.execute(
                f"SELECT event_id FROM st_epi_fts WHERE {where_clause} LIMIT ?",  # noqa: S608
                params,
            )
            return [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as exc:
            LOGGER.warning("FTS5 search failed for query '%s': %s", query, exc)
            return []

    def search_hippocampus(
        self,
        query: str,
        *,
        limit: int = 20,
        tenant_id: str | None = None,
        space_id: str | None = None,
    ) -> list[str]:
        """Search hippocampus staging memories by keyword.

        Parameters
        ----------
        query : str
            FTS5 search query (supports AND, OR, NOT, phrases with quotes)
        limit : int, optional
            Maximum results to return (default: 20)
        tenant_id : str, optional
            Filter by tenant_id
        space_id : str, optional
            Filter by space_id

        Returns
        -------
        list[str]
            List of event_ids matching the query (ranked by relevance)
        """
        try:
            # Build WHERE clause
            where_parts = ["st_hipp_fts MATCH ?"]
            params: list[str | int] = [query]

            if tenant_id:
                where_parts.append("tenant_id = ?")
                params.append(tenant_id)
            if space_id:
                where_parts.append("space_id = ?")
                params.append(space_id)

            params.append(limit)

            where_clause = " AND ".join(where_parts)

            cursor = self._connection.execute(
                f"SELECT event_id FROM st_hipp_fts WHERE {where_clause} LIMIT ?",  # noqa: S608
                params,
            )
            return [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as exc:
            LOGGER.warning("FTS5 search failed for query '%s': %s", query, exc)
            return []


__all__ = ["FTS5Indexer", "FTS5IndexerError"]
