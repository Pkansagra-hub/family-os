"""
TextVectorCoordinator - GAP-001 Milestone 3 (Issue 3.3)

Coordinates the full text + vector generation flow:
1. Fetch source texts from st_hipp_events
2. Generate embedding_text using layer-specific generator
3. Create embedding_vector using UltraBERT

Called by each layer writer during INSERT.

GAP Reference: GAP_001 Section 6 (Recommended Architecture)
Spec Reference: D:\\familyos\\docs\\plans\\GAP_001_MILESTONE_3_R7_WRITER_UPDATES.md
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from k0.modules.consolidation.algorithms.text_generators import get_generator

from .embedding_generator import EmbeddingGenerator
from .source_text_fetcher import (
    AsyncDBConnection,
    FetchedSourceTexts,
    SourceTextFetcher,
)

logger = logging.getLogger(__name__)


@dataclass
class TextVectorResult:
    """
    Result of text + vector generation.

    Contains all fields needed for GAP-001 inline storage:
    - source_texts_json: Original event texts (JSON array)
    - embedding_text: Generated text for semantic search
    - embedding_vector: 768-dim UltraBERT embedding as bytes
    - embedding_model: Model version for reproducibility

    Attributes:
        source_texts_json: JSON array of source texts
        embedding_text: Generated text for embedding
        embedding_vector: 768-dim as bytes (3072 bytes), or None if generation failed
        embedding_model: Model version (e.g., "ultrabert-v2.1.0"), or None
    """

    source_texts_json: str
    embedding_text: str
    embedding_vector: Optional[bytes]
    embedding_model: Optional[str]

    @property
    def has_vector(self) -> bool:
        """True if embedding vector was successfully generated."""
        return self.embedding_vector is not None


class TextVectorCoordinator:
    """
    Coordinates text fetching, generation, and embedding.

    This is the main orchestrator for GAP-001 text+vector generation.
    Each layer writer calls this during INSERT to populate the new columns.

    Flow:
        1. Fetch source texts from st_hipp_events (or via episodes)
        2. Get layer-specific text generator
        3. Generate embedding_text using template + summarization
        4. Create embedding_vector using UltraBERT

    Usage:
        coordinator = TextVectorCoordinator()
        result = await coordinator.process(
            layer="st_epi",
            record_data={"episode_id": "...", "primary_location": "Home", ...},
            source_event_ids=["evt_1", "evt_2"],
            conn=connection,
        )
        # Use result.source_texts_json, result.embedding_text, etc.
    """

    def __init__(
        self,
        text_fetcher: Optional[SourceTextFetcher] = None,
        embedding_gen: Optional[EmbeddingGenerator] = None,
    ):
        """
        Initialize coordinator with fetcher and generator.

        Args:
            text_fetcher: SourceTextFetcher instance (creates default if None)
            embedding_gen: EmbeddingGenerator instance (creates default if None)
        """
        self._fetcher = text_fetcher or SourceTextFetcher()
        self._embedder = embedding_gen or EmbeddingGenerator()

    async def process(
        self,
        layer: str,
        record_data: Dict[str, Any],
        source_event_ids: List[str],
        conn: AsyncDBConnection,
    ) -> TextVectorResult:
        """
        Full flow: fetch → generate text → create embedding.

        Args:
            layer: Target layer (st_epi, st_sem, st_social, etc.)
            record_data: Record fields for template generation
            source_event_ids: Event IDs to fetch texts from
            conn: Database connection

        Returns:
            TextVectorResult with all generated fields
        """
        # 1. Fetch source texts
        fetched = await self._fetcher.fetch_for_events(source_event_ids, conn)

        return await self._process_with_texts(layer, record_data, fetched)

    async def process_for_episodes(
        self,
        layer: str,
        record_data: Dict[str, Any],
        source_episode_ids: List[str],
        conn: AsyncDBConnection,
    ) -> TextVectorResult:
        """
        Process for layers that reference episodes instead of events.

        For st_sem and st_social which use source_episodes_json,
        this resolves episode_ids → event_ids first.

        Args:
            layer: Target layer (st_sem, st_social)
            record_data: Record fields for template generation
            source_episode_ids: Episode IDs to resolve and fetch texts from
            conn: Database connection

        Returns:
            TextVectorResult with all generated fields
        """
        # 1. Fetch source texts via episode resolution
        fetched = await self._fetcher.fetch_for_episodes(source_episode_ids, conn)

        return await self._process_with_texts(layer, record_data, fetched)

    async def process_without_fetch(
        self,
        layer: str,
        record_data: Dict[str, Any],
        source_texts: Optional[List[str]] = None,
    ) -> TextVectorResult:
        """
        Process without database fetch (for layers with explicit texts).

        For layers like st_prospective where the text is already
        in record_data (e.g., intention_description), no fetch needed.

        Args:
            layer: Target layer
            record_data: Record fields for template generation
            source_texts: Optional pre-fetched texts

        Returns:
            TextVectorResult with generated fields
        """
        import json

        texts = source_texts or []
        fetched = FetchedSourceTexts(
            texts=texts,
            event_ids=[],
            missing_count=0,
            texts_json=json.dumps(texts, ensure_ascii=False),
        )

        return await self._process_with_texts(layer, record_data, fetched)

    async def _process_with_texts(
        self,
        layer: str,
        record_data: Dict[str, Any],
        fetched: FetchedSourceTexts,
    ) -> TextVectorResult:
        """
        Core processing with already-fetched texts.

        Args:
            layer: Target layer
            record_data: Record fields
            fetched: Pre-fetched source texts

        Returns:
            TextVectorResult
        """
        # 2. Get layer-specific generator
        try:
            generator = get_generator(layer)
        except KeyError:
            logger.warning(f"TextVectorCoordinator: no generator for layer '{layer}'")
            return TextVectorResult(
                source_texts_json=fetched.texts_json,
                embedding_text="",
                embedding_vector=None,
                embedding_model=None,
            )

        # 3. Generate embedding text
        try:
            generated = generator.generate(record_data, fetched.texts)
            embedding_text = generated.embedding_text
        except Exception as e:
            logger.error(f"TextVectorCoordinator: text generation failed: {e}")
            embedding_text = ""

        # 4. Create embedding vector
        embedding_vector = None
        embedding_model = None

        if embedding_text:
            try:
                embedding = await self._embedder.generate(embedding_text)
                if embedding:
                    embedding_vector = embedding.vector_bytes
                    embedding_model = embedding.model_id
            except Exception as e:
                logger.error(f"TextVectorCoordinator: embedding failed: {e}")

        if fetched.missing_count > 0:
            logger.debug(
                f"TextVectorCoordinator: {fetched.missing_count} source events "
                f"not found for layer {layer}"
            )

        return TextVectorResult(
            source_texts_json=fetched.texts_json,
            embedding_text=embedding_text,
            embedding_vector=embedding_vector,
            embedding_model=embedding_model,
        )


# Module-level singleton for convenience
_coordinator: Optional[TextVectorCoordinator] = None


def get_coordinator() -> TextVectorCoordinator:
    """
    Get singleton TextVectorCoordinator instance.

    Returns:
        Shared TextVectorCoordinator instance
    """
    global _coordinator
    if _coordinator is None:
        _coordinator = TextVectorCoordinator()
    return _coordinator
