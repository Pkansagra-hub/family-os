"""
SourceTextFetcher - GAP-001 Milestone 3 (Issue 3.1)

Fetches source event texts from st_hipp_events before decay.
Used by R7 writers to populate source_texts_json.

CRITICAL TIMING CONSTRAINT:
    st_hipp_events.text DECAYS in 20 days!
    R7 MUST fetch texts BEFORE decay window expires.

GAP Reference: GAP_001 Section 1.1 (Text Preservation)
Spec Reference: D:\\familyos\\docs\\plans\\GAP_001_MILESTONE_3_R7_WRITER_UPDATES.md
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, List, Protocol

logger = logging.getLogger(__name__)


class AsyncDBConnection(Protocol):
    """Protocol for async database connection (asyncpg compatible)."""

    async def fetch(self, query: str, *args: Any) -> List[Any]: ...


@dataclass
class FetchedSourceTexts:
    """
    Result of fetching source texts from st_hipp_events.

    Attributes:
        texts: Ordered list of event texts (by created_at ASC)
        event_ids: Corresponding event IDs for each text
        missing_count: Events not found (already decayed or archived)
        texts_json: Pre-serialized JSON array for direct storage
    """

    texts: List[str] = field(default_factory=list)
    event_ids: List[str] = field(default_factory=list)
    missing_count: int = 0
    texts_json: str = "[]"

    @property
    def found_count(self) -> int:
        """Number of texts successfully fetched."""
        return len(self.texts)

    @property
    def total_requested(self) -> int:
        """Total events requested (found + missing)."""
        return self.found_count + self.missing_count

    def is_complete(self) -> bool:
        """True if all requested events were found."""
        return self.missing_count == 0


class SourceTextFetcher:
    """
    Fetches source texts from st_hipp_events.

    This service retrieves the original event texts for a list of event IDs,
    preserving temporal order. Missing events (already decayed) are tracked
    but do not cause failures.

    Usage:
        fetcher = SourceTextFetcher()
        result = await fetcher.fetch_for_events(event_ids, connection)
        print(result.texts)       # ["First event text", "Second event text"]
        print(result.texts_json)  # '["First event text", "Second event text"]'
    """

    # Maximum events to fetch in a single query (prevent memory issues)
    MAX_BATCH_SIZE = 500

    async def fetch_for_events(
        self,
        event_ids: List[str],
        conn: AsyncDBConnection,
    ) -> FetchedSourceTexts:
        """
        Fetch texts for given event IDs from st_hipp_events.

        Retrieves event texts ordered by creation time. Events that have
        already decayed or been archived are counted as missing.

        Args:
            event_ids: List of st_hipp_events.event_id values
            conn: Database connection (asyncpg)

        Returns:
            FetchedSourceTexts with texts, metadata, and pre-serialized JSON
        """
        if not event_ids:
            return FetchedSourceTexts(
                texts=[],
                event_ids=[],
                missing_count=0,
                texts_json="[]",
            )

        # Deduplicate while preserving order
        seen = set()
        unique_ids = []
        for eid in event_ids:
            if eid and eid not in seen:
                seen.add(eid)
                unique_ids.append(eid)

        if not unique_ids:
            return FetchedSourceTexts(
                texts=[],
                event_ids=[],
                missing_count=0,
                texts_json="[]",
            )

        # Batch if too many
        if len(unique_ids) > self.MAX_BATCH_SIZE:
            logger.warning(
                f"SourceTextFetcher: truncating {len(unique_ids)} events to {self.MAX_BATCH_SIZE}"
            )
            unique_ids = unique_ids[: self.MAX_BATCH_SIZE]

        try:
            rows = await conn.fetch(
                """
                SELECT event_id, text
                FROM st_hipp_events
                WHERE event_id = ANY($1)
                  AND text IS NOT NULL
                  AND text != ''
                  AND (archival_status IS NULL OR archival_status = 'ACTIVE')
                ORDER BY created_at ASC
                """,
                unique_ids,
            )
        except Exception as e:
            logger.error(f"SourceTextFetcher: query failed: {e}")
            return FetchedSourceTexts(
                texts=[],
                event_ids=[],
                missing_count=len(unique_ids),
                texts_json="[]",
            )

        texts = []
        found_ids = []
        for row in rows:
            text = row["text"]
            if text:  # Double-check non-empty
                texts.append(text)
                found_ids.append(row["event_id"])

        missing = len(unique_ids) - len(found_ids)

        if missing > 0:
            logger.debug(
                f"SourceTextFetcher: {missing}/{len(unique_ids)} events not found "
                "(may have decayed or been archived)"
            )

        return FetchedSourceTexts(
            texts=texts,
            event_ids=found_ids,
            missing_count=missing,
            texts_json=json.dumps(texts, ensure_ascii=False),
        )

    async def fetch_for_episodes(
        self,
        episode_ids: List[str],
        conn: AsyncDBConnection,
    ) -> FetchedSourceTexts:
        """
        Fetch texts for episodes by resolving episode_ids → event_ids first.

        For layers that reference episodes (st_sem, st_social) instead of
        events directly, this method first looks up st_epi.source_events_json
        and then fetches the underlying event texts.

        Args:
            episode_ids: List of st_epi.episode_id values
            conn: Database connection (asyncpg)

        Returns:
            FetchedSourceTexts with texts from underlying events
        """
        if not episode_ids:
            return FetchedSourceTexts(
                texts=[],
                event_ids=[],
                missing_count=0,
                texts_json="[]",
            )

        # Deduplicate
        seen = set()
        unique_eps = []
        for eid in episode_ids:
            if eid and eid not in seen:
                seen.add(eid)
                unique_eps.append(eid)

        if not unique_eps:
            return FetchedSourceTexts(
                texts=[],
                event_ids=[],
                missing_count=0,
                texts_json="[]",
            )

        # Get source_events_json for each episode
        try:
            rows = await conn.fetch(
                """
                SELECT episode_id, source_events_json
                FROM st_epi
                WHERE episode_id = ANY($1)
                  AND source_events_json IS NOT NULL
                """,
                unique_eps,
            )
        except Exception as e:
            logger.error(f"SourceTextFetcher: episode lookup failed: {e}")
            return FetchedSourceTexts(
                texts=[],
                event_ids=[],
                missing_count=len(unique_eps),
                texts_json="[]",
            )

        # Flatten all event IDs from episodes
        all_event_ids = []
        for row in rows:
            events_json = row["source_events_json"]
            if events_json:
                try:
                    event_ids_list = json.loads(events_json)
                    if isinstance(event_ids_list, list):
                        all_event_ids.extend(event_ids_list)
                except json.JSONDecodeError:
                    logger.warning(
                        f"SourceTextFetcher: invalid source_events_json for episode {row['episode_id']}"
                    )

        if not all_event_ids:
            return FetchedSourceTexts(
                texts=[],
                event_ids=[],
                missing_count=0,
                texts_json="[]",
            )

        # Now fetch texts for all event IDs
        return await self.fetch_for_events(all_event_ids, conn)
