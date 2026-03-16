"""SummaryRegenerator -- rebuilds summary and embedding_text for truth records (M9.6).

For episodic layer: builds StructuredEpisodeSummary JSON + embedding_text.
For all other layers: rebuilds embedding_text using layer-specific template generator.
No LLM -- all generation is template-based + extractive (TextRank).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from k0.modules.consolidation.reconciliation.hooks.episode_summary import build_structured_summary

logger = logging.getLogger(__name__)


# -- Protocols for dependency injection (testing without real DB/services) --


class TextCoordinatorLike(Protocol):
    """Minimal interface matching TextVectorCoordinator.process()."""

    async def process(
        self,
        layer: str,
        record_data: dict[str, Any],
        source_event_ids: list[str],
        conn: Any,
    ) -> Any: ...


class EventFetcherLike(Protocol):
    """Fetches event rows from st_hipp_events by event_id."""

    async def fetch(self, event_ids: list[str], conn: Any) -> list[dict[str, Any]]: ...


# -- Default implementations --


class DefaultEventFetcher:
    """Fetches event rows from st_hipp_events."""

    _COLUMNS = (
        "event_id",
        "conversation_anchor_ms",
        "event_time_utc",
        "user_message",
        "sentiment_label",
        "emotions_json",
        "intent_ultrabert",
        "salience_band",
        "ingress_channel",
        "affect_valence",
        "affect_arousal",
        "narrative_thread_id",
        "participants_json",
    )

    async def fetch(self, event_ids: list[str], conn: Any) -> list[dict[str, Any]]:
        if not event_ids:
            return []
        cols = ", ".join(self._COLUMNS)
        placeholders = ", ".join(f"${i + 1}" for i in range(len(event_ids)))
        sql = f"SELECT {cols} FROM st_hipp_events WHERE event_id IN ({placeholders})"  # noqa: S608
        rows = await conn.fetch(sql, *event_ids)
        return [dict(r) for r in rows]


# -- Result type --


@dataclass
class SummaryRegenResult:
    """Output of a single summary regeneration."""

    embedding_text: str | None = None
    summary_json: str | None = None
    embedding_model: str | None = None
    source_texts_json: str | None = None


# -- Main class --


class SummaryRegenerator:
    """Regenerates summary text and embedding_text for truth records.

    For episodic layer: builds StructuredEpisodeSummary JSON + embedding_text.
    For all other layers: rebuilds embedding_text using layer-specific template generator.
    No LLM -- all generation is template-based + extractive.
    """

    def __init__(
        self,
        text_coordinator: TextCoordinatorLike | None = None,
        event_fetcher: EventFetcherLike | None = None,
    ) -> None:
        self._coordinator = text_coordinator
        self._event_fetcher = event_fetcher or DefaultEventFetcher()

    async def regenerate(
        self,
        layer: str,
        record_id: str,
        spec: Any,
        source_event_ids: list[str],
        record_data: dict[str, Any],
        conn: Any = None,
    ) -> SummaryRegenResult:
        """Regenerate summary content for a truth record.

        For st_epi:
            1. Fetch source events from st_hipp_events
            2. Build StructuredEpisodeSummary
            3. Regenerate embedding_text via TextVectorCoordinator
            4. Return structured JSON + new embedding_text

        For other layers:
            1. Regenerate embedding_text via TextVectorCoordinator
            2. Return new embedding_text (no structured summary)
        """
        if layer == "st_epi":
            return await self._regenerate_episodic(record_id, source_event_ids, record_data, conn)
        return await self._regenerate_generic(layer, source_event_ids, record_data, conn)

    async def _regenerate_episodic(
        self,
        record_id: str,
        source_event_ids: list[str],
        record_data: dict[str, Any],
        conn: Any,
    ) -> SummaryRegenResult:
        events = await self._event_fetcher.fetch(source_event_ids, conn)
        structured = build_structured_summary(events, record_data)
        summary_json = structured.to_json()

        tv_result = await self._run_coordinator("st_epi", record_data, source_event_ids, conn)

        return SummaryRegenResult(
            embedding_text=tv_result.embedding_text if tv_result else None,
            summary_json=summary_json,
            embedding_model=tv_result.embedding_model if tv_result else None,
            source_texts_json=tv_result.source_texts_json if tv_result else None,
        )

    async def _regenerate_generic(
        self,
        layer: str,
        source_event_ids: list[str],
        record_data: dict[str, Any],
        conn: Any,
    ) -> SummaryRegenResult:
        tv_result = await self._run_coordinator(layer, record_data, source_event_ids, conn)
        return SummaryRegenResult(
            embedding_text=tv_result.embedding_text if tv_result else None,
            summary_json=None,
            embedding_model=tv_result.embedding_model if tv_result else None,
            source_texts_json=tv_result.source_texts_json if tv_result else None,
        )

    async def _run_coordinator(
        self,
        layer: str,
        record_data: dict[str, Any],
        source_event_ids: list[str],
        conn: Any,
    ) -> Any | None:
        if self._coordinator is None:
            logger.warning("No TextVectorCoordinator configured; skipping text regen")
            return None
        return await self._coordinator.process(
            layer=layer,
            record_data=record_data,
            source_event_ids=source_event_ids,
            conn=conn,
        )
