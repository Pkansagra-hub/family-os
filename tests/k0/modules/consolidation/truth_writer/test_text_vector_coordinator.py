"""
Unit tests for GAP-001 TextVectorCoordinator and related services.

Tests for Issue 3.1-3.3:
    - SourceTextFetcher
    - EmbeddingGenerator
    - TextVectorCoordinator

These tests verify the inline vector generation flow that
populates source_texts_json, embedding_text, embedding_vector,
and embedding_model during consolidation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from k0.modules.consolidation.truth_writer.embedding_generator import (
    EmbeddingGenerator,
    GeneratedEmbedding,
)
from k0.modules.consolidation.truth_writer.source_text_fetcher import (
    FetchedSourceTexts,
    SourceTextFetcher,
)
from k0.modules.consolidation.truth_writer.text_vector_coordinator import (
    TextVectorCoordinator,
    TextVectorResult,
    get_coordinator,
)

# Constants from implementation
MODEL_ID = "ultrabert-v2.1.0"
DIMENSION = 768


# =============================================================================
# SourceTextFetcher Tests (Issue 3.1)
# =============================================================================


class TestFetchedSourceTexts:
    """Tests for FetchedSourceTexts dataclass."""

    def test_from_texts_single(self) -> None:
        """Single text is converted correctly."""
        result = FetchedSourceTexts(
            texts=["hello world"],
            event_ids=["e1"],
            missing_count=0,
            texts_json='["hello world"]',
        )

        assert result.texts == ["hello world"]
        assert result.texts_json == '["hello world"]'
        assert result.found_count == 1

    def test_from_texts_multiple(self) -> None:
        """Multiple texts stored correctly."""
        result = FetchedSourceTexts(
            texts=["first", "second", "third"],
            event_ids=["e1", "e2", "e3"],
            missing_count=0,
            texts_json='["first", "second", "third"]',
        )

        assert len(result.texts) == 3
        assert result.found_count == 3

    def test_from_texts_empty_list(self) -> None:
        """Empty list produces empty result."""
        result = FetchedSourceTexts(
            texts=[],
            event_ids=[],
            missing_count=0,
            texts_json="[]",
        )

        assert result.texts == []
        assert result.found_count == 0

    def test_found_and_missing_counts(self) -> None:
        """found_count and missing_count work correctly."""
        result = FetchedSourceTexts(
            texts=["one", "two"],
            event_ids=["e1", "e2"],
            missing_count=3,
            texts_json='["one", "two"]',
        )

        assert result.found_count == 2
        assert result.missing_count == 3
        assert result.total_requested == 5
        assert not result.is_complete()

    def test_is_complete(self) -> None:
        """is_complete returns True when no missing events."""
        complete = FetchedSourceTexts(
            texts=["text"], event_ids=["e1"], missing_count=0, texts_json='["text"]'
        )
        incomplete = FetchedSourceTexts(
            texts=["text"], event_ids=["e1"], missing_count=1, texts_json='["text"]'
        )

        assert complete.is_complete()
        assert not incomplete.is_complete()


class TestSourceTextFetcher:
    """Tests for SourceTextFetcher service."""

    @pytest.fixture
    def mock_connection(self) -> AsyncMock:
        """Create mock database connection."""
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])
        return conn

    @pytest.fixture
    def fetcher(self) -> SourceTextFetcher:
        """Create fetcher instance."""
        return SourceTextFetcher()

    @pytest.mark.asyncio
    async def test_fetch_for_events_empty_list(
        self, fetcher: SourceTextFetcher, mock_connection: AsyncMock
    ) -> None:
        """Empty event list returns empty result."""
        result = await fetcher.fetch_for_events([], mock_connection)

        assert result.found_count == 0
        mock_connection.fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_for_events_with_results(
        self, fetcher: SourceTextFetcher, mock_connection: AsyncMock
    ) -> None:
        """Events with texts are fetched and combined."""
        mock_connection.fetch.return_value = [
            {"event_id": "e1", "text": "First event text"},
            {"event_id": "e2", "text": "Second event text"},
        ]

        result = await fetcher.fetch_for_events(["e1", "e2"], mock_connection)

        assert result.found_count == 2
        assert len(result.texts) == 2
        assert "First event" in result.texts[0]
        assert "Second event" in result.texts[1]

    @pytest.mark.asyncio
    async def test_fetch_for_events_missing_event(
        self, fetcher: SourceTextFetcher, mock_connection: AsyncMock
    ) -> None:
        """Missing events (decayed) are handled gracefully."""
        # Only one of two events exists
        mock_connection.fetch.return_value = [
            {"event_id": "e1", "text": "Only this one exists"},
        ]

        result = await fetcher.fetch_for_events(["e1", "e2"], mock_connection)

        assert len(result.texts) == 1
        assert result.missing_count == 1

    @pytest.mark.asyncio
    async def test_fetch_for_events_null_text(
        self, fetcher: SourceTextFetcher, mock_connection: AsyncMock
    ) -> None:
        """Events with NULL text field are excluded."""
        mock_connection.fetch.return_value = [
            {"event_id": "e1", "text": None},
            {"event_id": "e2", "text": "Valid text"},
        ]

        result = await fetcher.fetch_for_events(["e1", "e2"], mock_connection)

        assert len(result.texts) == 1
        assert result.texts[0] == "Valid text"

    @pytest.mark.asyncio
    async def test_fetch_for_episodes_resolves_to_events(
        self, fetcher: SourceTextFetcher, mock_connection: AsyncMock
    ) -> None:
        """Episode IDs are resolved to event IDs then fetched."""
        # First query: resolve episodes to events
        mock_connection.fetch.side_effect = [
            # Episode resolution query - returns source_events_json
            [
                {"source_events_json": '["e1", "e2"]'},
            ],
            # Event text fetch query
            [
                {"event_id": "e1", "text": "Event one"},
                {"event_id": "e2", "text": "Event two"},
            ],
        ]

        result = await fetcher.fetch_for_episodes(["ep1"], mock_connection)

        assert result.found_count == 2
        assert len(result.texts) == 2


# =============================================================================
# EmbeddingGenerator Tests (Issue 3.2)
# =============================================================================


class TestGeneratedEmbedding:
    """Tests for GeneratedEmbedding dataclass."""

    def test_dataclass_fields(self) -> None:
        """GeneratedEmbedding has correct structure."""
        result = GeneratedEmbedding(
            vector_bytes=b"\x00" * 3072,
            model_id=MODEL_ID,
            dimension=DIMENSION,
        )

        assert len(result.vector_bytes) == 3072
        assert result.model_id == MODEL_ID
        assert result.dimension == DIMENSION


class TestEmbeddingGenerator:
    """Tests for EmbeddingGenerator service."""

    @pytest.fixture
    def generator(self) -> EmbeddingGenerator:
        """Create generator instance."""
        return EmbeddingGenerator()

    @pytest.mark.asyncio
    async def test_generate_empty_text(self, generator: EmbeddingGenerator) -> None:
        """Empty text returns None."""
        result = await generator.generate("")

        assert result is None

    @pytest.mark.asyncio
    async def test_generate_whitespace_only(self, generator: EmbeddingGenerator) -> None:
        """Whitespace-only text returns None."""
        result = await generator.generate("   \n\t   ")

        assert result is None

    @pytest.mark.asyncio
    async def test_generate_with_text(self, generator: EmbeddingGenerator) -> None:
        """Non-empty text produces embedding."""
        with patch.object(generator, "_get_ultrabert_embedding") as mock_get:
            mock_get.return_value = [0.1] * DIMENSION

            result = await generator.generate("test input")

            assert result is not None
            assert result.model_id == MODEL_ID
            assert len(result.vector_bytes) == DIMENSION * 4

    @pytest.mark.asyncio
    async def test_generate_ultrabert_failure(self, generator: EmbeddingGenerator) -> None:
        """UltraBERT failure returns None."""
        with patch.object(generator, "_get_ultrabert_embedding") as mock_get:
            mock_get.return_value = None

            result = await generator.generate("test input")

            assert result is None


# =============================================================================
# TextVectorCoordinator Tests (Issue 3.3)
# =============================================================================


class TestTextVectorResult:
    """Tests for TextVectorResult dataclass."""

    def test_has_vector_true(self) -> None:
        """has_vector returns True when vector present."""
        result = TextVectorResult(
            source_texts_json='["text"]',
            embedding_text="text",
            embedding_vector=b"\x00" * 3072,
            embedding_model=MODEL_ID,
        )

        assert result.has_vector

    def test_has_vector_false(self) -> None:
        """has_vector returns False when vector is None."""
        result = TextVectorResult(
            source_texts_json='["text"]',
            embedding_text="text",
            embedding_vector=None,
            embedding_model=None,
        )

        assert not result.has_vector


class TestTextVectorCoordinator:
    """Tests for TextVectorCoordinator orchestrator."""

    @pytest.fixture
    def mock_fetcher(self) -> MagicMock:
        """Create mock SourceTextFetcher."""
        fetcher = MagicMock(spec=SourceTextFetcher)
        fetcher.fetch_for_events = AsyncMock(
            return_value=FetchedSourceTexts(
                texts=["Test text"],
                event_ids=["e1"],
                missing_count=0,
                texts_json='["Test text"]',
            )
        )
        fetcher.fetch_for_episodes = AsyncMock(
            return_value=FetchedSourceTexts(
                texts=["Test text"],
                event_ids=["e1"],
                missing_count=0,
                texts_json='["Test text"]',
            )
        )
        return fetcher

    @pytest.fixture
    def mock_embedder(self) -> MagicMock:
        """Create mock EmbeddingGenerator."""
        generator = MagicMock(spec=EmbeddingGenerator)
        generator.generate = AsyncMock(
            return_value=GeneratedEmbedding(
                vector_bytes=b"\x00" * 3072,
                model_id=MODEL_ID,
                dimension=DIMENSION,
            )
        )
        return generator

    @pytest.fixture
    def coordinator(
        self, mock_fetcher: MagicMock, mock_embedder: MagicMock
    ) -> TextVectorCoordinator:
        """Create coordinator with mocked dependencies."""
        return TextVectorCoordinator(
            text_fetcher=mock_fetcher,
            embedding_gen=mock_embedder,
        )

    @pytest.fixture
    def mock_connection(self) -> AsyncMock:
        """Create mock database connection."""
        return AsyncMock()

    @pytest.fixture
    def sample_record_data(self) -> dict:
        """Sample record data for testing."""
        return {
            "episode_id": "ep_123",
            "primary_location": "Home",
            "duration_ms": 3600000,
        }

    @pytest.mark.asyncio
    async def test_process_empty_events(
        self,
        coordinator: TextVectorCoordinator,
        mock_connection: AsyncMock,
        mock_fetcher: MagicMock,
        sample_record_data: dict,
    ) -> None:
        """Empty event list still processes (with empty source texts)."""
        mock_fetcher.fetch_for_events.return_value = FetchedSourceTexts(
            texts=[], event_ids=[], missing_count=0, texts_json="[]"
        )

        with patch(
            "k0.modules.consolidation.truth_writer.text_vector_coordinator.get_generator"
        ) as mock_gen:
            mock_text_gen = MagicMock()
            mock_text_gen.generate = MagicMock(return_value="Generated text")
            mock_gen.return_value = mock_text_gen

            result = await coordinator.process(
                layer="st_epi",
                record_data=sample_record_data,
                source_event_ids=[],
                conn=mock_connection,
            )

            assert isinstance(result, TextVectorResult)

    @pytest.mark.asyncio
    async def test_process_with_events(
        self,
        coordinator: TextVectorCoordinator,
        mock_connection: AsyncMock,
        mock_fetcher: MagicMock,
        sample_record_data: dict,
    ) -> None:
        """Events are fetched, combined, and embedded."""
        with patch(
            "k0.modules.consolidation.truth_writer.text_vector_coordinator.get_generator"
        ) as mock_gen:
            # Mock the text generator to return an object with embedding_text attr
            mock_result = MagicMock()
            mock_result.embedding_text = "Generated text"
            mock_text_gen = MagicMock()
            mock_text_gen.generate = MagicMock(return_value=mock_result)
            mock_gen.return_value = mock_text_gen

            result = await coordinator.process(
                layer="st_epi",
                record_data=sample_record_data,
                source_event_ids=["e1", "e2"],
                conn=mock_connection,
            )

            assert result.source_texts_json is not None
            assert result.embedding_text == "Generated text"
            mock_fetcher.fetch_for_events.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_for_episodes(
        self,
        coordinator: TextVectorCoordinator,
        mock_connection: AsyncMock,
        mock_fetcher: MagicMock,
        sample_record_data: dict,
    ) -> None:
        """Episodes are resolved to events then processed."""
        with patch(
            "k0.modules.consolidation.truth_writer.text_vector_coordinator.get_generator"
        ) as mock_gen:
            mock_text_gen = MagicMock()
            mock_text_gen.generate = MagicMock(return_value="Generated text")
            mock_gen.return_value = mock_text_gen

            result = await coordinator.process_for_episodes(
                layer="st_sem",
                record_data=sample_record_data,
                source_episode_ids=["ep1"],
                conn=mock_connection,
            )

            mock_fetcher.fetch_for_episodes.assert_called_once()
            assert result.embedding_text is not None

    @pytest.mark.asyncio
    async def test_process_without_fetch(
        self,
        coordinator: TextVectorCoordinator,
        mock_embedder: MagicMock,
        sample_record_data: dict,
    ) -> None:
        """Direct text embedding without fetch."""
        with patch(
            "k0.modules.consolidation.truth_writer.text_vector_coordinator.get_generator"
        ) as mock_gen:
            mock_text_gen = MagicMock()
            mock_text_gen.generate = MagicMock(return_value="Generated text")
            mock_gen.return_value = mock_text_gen

            result = await coordinator.process_without_fetch(
                layer="st_prospective",
                record_data=sample_record_data,
                source_texts=["Pre-fetched text"],
            )

            assert result.embedding_text is not None


class TestGetCoordinator:
    """Tests for singleton coordinator factory."""

    def test_get_coordinator_returns_instance(self) -> None:
        """get_coordinator returns a TextVectorCoordinator."""
        result = get_coordinator()

        assert isinstance(result, TextVectorCoordinator)

    def test_get_coordinator_is_singleton(self) -> None:
        """get_coordinator returns same instance."""
        first = get_coordinator()
        second = get_coordinator()

        assert first is second
