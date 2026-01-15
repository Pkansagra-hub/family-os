"""Full-text search indexer for memory tables - Async PostgreSQL.

This module provides indexing services for st_epi_fts and st_hipp_fts tables,
enabling fast keyword search across episodic and hippocampus staging memories.
Uses PostgreSQL tsvector/GIN indexing instead of SQLite FTS5.

Performance Target: <10ms P95 for keyword search across 100K+ memories

Example:
    async with connection_scope() as conn:
        indexer = FTSIndexer(conn)
        await indexer.index_episodic(
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

        results = await indexer.search_episodic("dinner Mom")
        # Returns: ["evt_123"]
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    import asyncpg

LOGGER = logging.getLogger(__name__)


class FTSIndexerError(RuntimeError):
    """Raised when FTS indexing fails."""


class FTSIndexer:
    """Manages PostgreSQL tsvector indexing for memory tables.

    Provides methods to index episodic and hippocampus memories into
    PostgreSQL tables with tsvector columns for fast keyword search.
    Also handles index removal when memories are deleted or tombstoned.
    """

    def __init__(self, connection: asyncpg.Connection) -> None:
        """Initialize the FTS indexer.

        Parameters
        ----------
        connection : asyncpg.Connection
            Active PostgreSQL database connection with st_epi_fts and st_hipp_fts tables.
        """
        self._connection = connection

    async def index_episodic(
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
        FTSIndexerError
            If indexing fails due to database error or constraint violation.
        """
        try:
            # Convert lists to space-separated strings for full-text indexing
            tags_text = " ".join(tags) if tags else ""
            topics_text = " ".join(topics) if topics else ""
            locations_text = " ".join(location_names) if location_names else ""
            participants_text = " ".join(participant_names) if participant_names else ""

            await self._connection.execute(
                """
                INSERT INTO st_epi_fts (
                    event_id, tenant_id, space_id,
                    text, summary, tags, topics,
                    location_names, participant_names,
                    commit_ts
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (event_id) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id,
                    space_id = EXCLUDED.space_id,
                    text = EXCLUDED.text,
                    summary = EXCLUDED.summary,
                    tags = EXCLUDED.tags,
                    topics = EXCLUDED.topics,
                    location_names = EXCLUDED.location_names,
                    participant_names = EXCLUDED.participant_names,
                    commit_ts = EXCLUDED.commit_ts
                """,
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
            )
            LOGGER.debug("Indexed episodic memory %s to FTS", event_id)
        except Exception as exc:
            msg = f"Failed to index episodic memory {event_id} to FTS"
            raise FTSIndexerError(msg) from exc

    async def index_hippocampus(
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
        FTSIndexerError
            If indexing fails due to database error or constraint violation.
        """
        try:
            # Convert lists to space-separated strings for full-text indexing
            topics_text = " ".join(topics) if topics else ""
            categories_text = " ".join(categories) if categories else ""
            participants_text = " ".join(participant_names) if participant_names else ""

            await self._connection.execute(
                """
                INSERT INTO st_hipp_fts (
                    event_id, tenant_id, space_id,
                    text, topics, categories,
                    participant_names, location_name,
                    commit_ts
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (event_id) DO UPDATE SET
                    tenant_id = EXCLUDED.tenant_id,
                    space_id = EXCLUDED.space_id,
                    text = EXCLUDED.text,
                    topics = EXCLUDED.topics,
                    categories = EXCLUDED.categories,
                    participant_names = EXCLUDED.participant_names,
                    location_name = EXCLUDED.location_name,
                    commit_ts = EXCLUDED.commit_ts
                """,
                event_id,
                tenant_id,
                space_id,
                text,
                topics_text,
                categories_text,
                participants_text,
                location_name or "",
                commit_ts,
            )
            LOGGER.debug("Indexed hippocampus memory %s to FTS", event_id)
        except Exception as exc:
            msg = f"Failed to index hippocampus memory {event_id} to FTS"
            raise FTSIndexerError(msg) from exc

    async def remove_from_index(self, table: str, event_id: str) -> None:
        """Remove a memory from FTS index (when deleted or tombstoned).

        Parameters
        ----------
        table : str
            FTS table name ("st_epi_fts" or "st_hipp_fts")
        event_id : str
            Event ID to remove from index

        Raises
        ------
        FTSIndexerError
            If removal fails due to database error.
        ValueError
            If table name is invalid.
        """
        if table not in ("st_epi_fts", "st_hipp_fts"):
            msg = f"Invalid FTS table: {table}"
            raise ValueError(msg)

        try:
            await self._connection.execute(
                f"DELETE FROM {table} WHERE event_id = $1",  # noqa: S608
                event_id,
            )
            LOGGER.debug("Removed event %s from %s", event_id, table)
        except Exception as exc:
            msg = f"Failed to remove {event_id} from {table}"
            raise FTSIndexerError(msg) from exc

    async def search_episodic(
        self,
        query: str,
        *,
        limit: int = 20,
        tenant_id: str | None = None,
        space_id: str | None = None,
    ) -> list[str]:
        """Search episodic memories by keyword.

        Uses PostgreSQL plainto_tsquery for natural language queries.

        Parameters
        ----------
        query : str
            Search query (natural language, will be converted to tsquery)
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
        >>> await indexer.search_episodic("dinner Mom")
        ['evt_123', 'evt_456']

        >>> await indexer.search_episodic("Olive Garden family")
        ['evt_123']
        """
        try:
            # Build WHERE clause with PostgreSQL full-text search
            # Combine all searchable columns into a single tsvector
            where_parts = [
                """
                (
                    to_tsvector('english', text) ||
                    to_tsvector('english', COALESCE(summary, '')) ||
                    to_tsvector('english', COALESCE(tags, '')) ||
                    to_tsvector('english', COALESCE(topics, '')) ||
                    to_tsvector('english', COALESCE(location_names, '')) ||
                    to_tsvector('english', COALESCE(participant_names, ''))
                ) @@ plainto_tsquery('english', $1)
                """
            ]
            params: list[str | int] = [query]
            param_idx = 2

            if tenant_id:
                where_parts.append(f"tenant_id = ${param_idx}")
                params.append(tenant_id)
                param_idx += 1
            if space_id:
                where_parts.append(f"space_id = ${param_idx}")
                params.append(space_id)
                param_idx += 1

            params.append(limit)
            where_clause = " AND ".join(where_parts)

            rows = await self._connection.fetch(
                f"""
                SELECT event_id FROM st_epi_fts
                WHERE {where_clause}
                ORDER BY ts_rank(
                    to_tsvector('english', text) ||
                    to_tsvector('english', COALESCE(summary, '')),
                    plainto_tsquery('english', $1)
                ) DESC
                LIMIT ${param_idx}
                """,
                *params,
            )
            return [row["event_id"] for row in rows]
        except Exception as exc:
            LOGGER.warning("FTS search failed for query '%s': %s", query, exc)
            return []

    async def search_hippocampus(
        self,
        query: str,
        *,
        limit: int = 20,
        tenant_id: str | None = None,
        space_id: str | None = None,
    ) -> list[str]:
        """Search hippocampus staging memories by keyword.

        Uses PostgreSQL plainto_tsquery for natural language queries.

        Parameters
        ----------
        query : str
            Search query (natural language, will be converted to tsquery)
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
            # Build WHERE clause with PostgreSQL full-text search
            where_parts = [
                """
                (
                    to_tsvector('english', text) ||
                    to_tsvector('english', COALESCE(topics, '')) ||
                    to_tsvector('english', COALESCE(categories, '')) ||
                    to_tsvector('english', COALESCE(participant_names, ''))
                ) @@ plainto_tsquery('english', $1)
                """
            ]
            params: list[str | int] = [query]
            param_idx = 2

            if tenant_id:
                where_parts.append(f"tenant_id = ${param_idx}")
                params.append(tenant_id)
                param_idx += 1
            if space_id:
                where_parts.append(f"space_id = ${param_idx}")
                params.append(space_id)
                param_idx += 1

            params.append(limit)
            where_clause = " AND ".join(where_parts)

            rows = await self._connection.fetch(
                f"""
                SELECT event_id FROM st_hipp_fts
                WHERE {where_clause}
                ORDER BY ts_rank(
                    to_tsvector('english', text),
                    plainto_tsquery('english', $1)
                ) DESC
                LIMIT ${param_idx}
                """,
                *params,
            )
            return [row["event_id"] for row in rows]
        except Exception as exc:
            LOGGER.warning("FTS search failed for query '%s': %s", query, exc)
            return []


# Backward compatibility aliases
FTS5Indexer = FTSIndexer
FTS5IndexerError = FTSIndexerError

__all__ = ["FTSIndexer", "FTSIndexerError", "FTS5Indexer", "FTS5IndexerError"]
