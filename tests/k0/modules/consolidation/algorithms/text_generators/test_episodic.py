"""
Unit tests for EpisodicTextGenerator.

GAP Reference: GAP_001_CROSS_LAYER_VECTOR_LINKING.md §4
Milestone: GAP_001_MILESTONE_2_SUMMARY_GENERATOR.md Issue 2.10
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict

import pytest

from k0.modules.consolidation.algorithms.embedding_text_generator import (
    TextGenerationStrategy,
)
from k0.modules.consolidation.algorithms.text_generators.episodic import (
    EpisodicTextGenerator,
)


class TestEpisodicTextGenerator:
    """Tests for EpisodicTextGenerator."""

    @pytest.fixture
    def generator(self) -> EpisodicTextGenerator:
        """Create generator instance."""
        return EpisodicTextGenerator()

    def test_layer_property(self, generator: EpisodicTextGenerator) -> None:
        """Test layer property returns correct value."""
        assert generator.layer == "st_epi"

    def test_basic_generation(self, generator: EpisodicTextGenerator) -> None:
        """Test basic text generation."""
        record_data = {"episode_id": "ep_123"}
        source_texts = ["Had dinner", "At restaurant"]

        result = generator.generate(record_data, source_texts)

        assert result.layer == "st_epi"
        assert result.record_id == "ep_123"
        assert "episode" in result.embedding_text.lower()
        assert result.strategy_used == TextGenerationStrategy.CONCATENATE

    def test_with_existing_summary(self, generator: EpisodicTextGenerator) -> None:
        """Test generation with pre-computed summary."""
        record_data = {
            "episode_id": "ep_123",
            "summary": "Family dinner at Italian restaurant",
        }

        result = generator.generate(record_data)

        assert "Family dinner at Italian restaurant" in result.embedding_text

    def test_temporal_context_morning(self, generator: EpisodicTextGenerator) -> None:
        """Test temporal context for morning."""
        # Friday 8am UTC
        friday_8am = datetime(2025, 1, 17, 8, 0, 0, tzinfo=timezone.utc)
        record_data = {
            "episode_id": "ep_123",
            "start_ts": int(friday_8am.timestamp() * 1000),
        }

        result = generator.generate(record_data, ["Had coffee"])

        assert "Friday" in result.embedding_text
        assert "morning" in result.embedding_text

    def test_temporal_context_evening(self, generator: EpisodicTextGenerator) -> None:
        """Test temporal context for evening."""
        # Saturday 7pm UTC
        saturday_7pm = datetime(2025, 1, 18, 19, 0, 0, tzinfo=timezone.utc)
        record_data = {
            "episode_id": "ep_123",
            "start_ts": int(saturday_7pm.timestamp() * 1000),
        }

        result = generator.generate(record_data, ["Had dinner"])

        assert "Saturday" in result.embedding_text
        assert "evening" in result.embedding_text

    def test_duration_included(self, generator: EpisodicTextGenerator) -> None:
        """Test that duration is included when available."""
        start = datetime(2025, 1, 17, 18, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 1, 17, 20, 0, 0, tzinfo=timezone.utc)

        record_data = {
            "episode_id": "ep_123",
            "start_ts": int(start.timestamp() * 1000),
            "end_ts": int(end.timestamp() * 1000),
        }

        result = generator.generate(record_data, ["Event"])

        # 2 hour duration
        assert "2h" in result.embedding_text

    def test_location_context(self, generator: EpisodicTextGenerator) -> None:
        """Test location context is included."""
        record_data = {
            "episode_id": "ep_123",
            "location_json": {"name": "Thai Orchid Restaurant"},
        }

        result = generator.generate(record_data, ["Had dinner"])

        assert "Thai Orchid Restaurant" in result.embedding_text
        assert "Context" in result.embedding_text

    def test_participants_single(self, generator: EpisodicTextGenerator) -> None:
        """Test single participant."""
        record_data = {
            "episode_id": "ep_123",
            "participants": ["Mom"],
        }

        result = generator.generate(record_data, ["Event"])

        assert "with Mom" in result.embedding_text

    def test_participants_two(self, generator: EpisodicTextGenerator) -> None:
        """Test two participants."""
        record_data = {
            "episode_id": "ep_123",
            "participants": ["Mom", "Dad"],
        }

        result = generator.generate(record_data, ["Event"])

        assert "with Mom and Dad" in result.embedding_text

    def test_participants_many(self, generator: EpisodicTextGenerator) -> None:
        """Test many participants - now lists all for groups up to 5."""
        record_data = {
            "episode_id": "ep_123",
            "participants": ["Mom", "Dad", "Sister", "Brother", "Grandma"],
        }

        result = generator.generate(record_data, ["Event"])

        # With 5 participants, all should be listed (threshold is 5)
        assert "Mom" in result.embedding_text
        assert "Dad" in result.embedding_text
        assert "Grandma" in result.embedding_text

    def test_strategy_concatenate(self, generator: EpisodicTextGenerator) -> None:
        """Test CONCATENATE strategy for few texts."""
        record_data = {"episode_id": "ep_123"}
        source_texts = ["First event", "Second event"]

        result = generator.generate(record_data, source_texts)

        assert result.strategy_used == TextGenerationStrategy.CONCATENATE

    def test_strategy_textrank(self, generator: EpisodicTextGenerator) -> None:
        """Test TEXTRANK strategy for moderate texts."""
        record_data = {"episode_id": "ep_123"}
        source_texts = ["Event 1", "Event 2", "Event 3", "Event 4", "Event 5"]

        result = generator.generate(record_data, source_texts)

        assert result.strategy_used == TextGenerationStrategy.TEXTRANK

    def test_strategy_narrative_arc(self, generator: EpisodicTextGenerator) -> None:
        """Test NARRATIVE_ARC strategy for many texts."""
        record_data = {"episode_id": "ep_123"}
        source_texts = [f"Event {i}" for i in range(10)]

        result = generator.generate(record_data, source_texts)

        assert result.strategy_used == TextGenerationStrategy.NARRATIVE_ARC

    def test_source_texts_json(self, generator: EpisodicTextGenerator) -> None:
        """Test source texts are stored as JSON."""
        record_data = {"episode_id": "ep_123"}
        source_texts = ["Text 1", "Text 2"]

        result = generator.generate(record_data, source_texts)

        parsed = json.loads(result.source_texts_json)
        assert parsed == source_texts

    def test_no_source_texts(self, generator: EpisodicTextGenerator) -> None:
        """Test handling of no source texts."""
        record_data = {"episode_id": "ep_123"}

        result = generator.generate(record_data)

        assert result.source_texts_json == "[]"
        assert "episode" in result.embedding_text.lower()

    def test_full_record(self, generator: EpisodicTextGenerator) -> None:
        """Test with fully populated record."""
        friday_6pm = datetime(2025, 1, 17, 18, 0, 0, tzinfo=timezone.utc)
        friday_8pm = datetime(2025, 1, 17, 20, 0, 0, tzinfo=timezone.utc)

        record_data: Dict[str, Any] = {
            "episode_id": "ep_family_dinner",
            "start_ts": int(friday_6pm.timestamp() * 1000),
            "end_ts": int(friday_8pm.timestamp() * 1000),
            "location_json": {"name": "Thai Orchid"},
            "participants": ["Mom", "Dad"],
        }
        source_texts = [
            "Arrived at restaurant",
            "Ordered spring rolls",
            "Had wonderful conversation",
        ]

        result = generator.generate(record_data, source_texts)

        assert "Friday evening" in result.embedding_text
        assert "2h" in result.embedding_text
        assert "Thai Orchid" in result.embedding_text
        assert "with Mom and Dad" in result.embedding_text
        assert result.record_id == "ep_family_dinner"
