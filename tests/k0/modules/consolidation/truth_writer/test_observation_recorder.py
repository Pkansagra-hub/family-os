"""
Unit tests for ObservationRecorder.

Tests the observation recording service that persists holistic context
to st_observations during truth layer INSERT/MERGE operations.

Issue: 7.4
Spec Reference: docs/plans/temporal_fix.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Tuple

import pytest

from k0.modules.consolidation.algorithms.observation_context import ObservationContext
from k0.modules.consolidation.truth_writer.observation_recorder import (
    VALID_LAYERS,
    ObservationRecorder,
    get_observation_recorder,
)

# =============================================================================
# Mock UoW
# =============================================================================


class MockConnection:
    """Mock database connection that captures SQL calls."""

    def __init__(self):
        self.execute_calls: List[Tuple[str, Tuple[Any, ...]]] = []

    async def execute(self, sql: str, *args: Any) -> None:
        """Capture SQL and arguments."""
        self.execute_calls.append((sql, args))


@dataclass
class MockUnitOfWork:
    """Mock UnitOfWork with captured SQL."""

    connection: MockConnection


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_uow() -> MockUnitOfWork:
    """Create mock UnitOfWork."""
    return MockUnitOfWork(connection=MockConnection())


@pytest.fixture
def recorder() -> ObservationRecorder:
    """Create ObservationRecorder instance."""
    return ObservationRecorder()


@pytest.fixture
def full_context() -> ObservationContext:
    """Create context with all fields populated."""
    return ObservationContext(
        observed_at=1704067200000,
        anchor_time_utc=1704067100000,
        original_temporal_expr="tomorrow at 3pm",
        time_of_day_bucket="AFTERNOON",
        circadian_slot="ACTIVE",
        is_weekend=False,
        day_of_week="Wednesday",
        sentiment_score=0.8,
        sentiment_label="positive",
        affect_valence=0.6,
        affect_arousal=0.4,
        dominant_emotion="joy",
        salience_score=0.7,
        salience_band="HIGH",
        novelty_score=0.5,
        ingress_channel="voice",
        ingress_source="alexa",
        device_kind="speaker",
        location_name="Home",
        location_type="home",
        geohash_6="9q8yyz",
        social_context="family",
        social_intimacy="close",
        is_solo_event=False,
        num_participants=3,
        observation_type="REINFORCEMENT",
        confidence=0.95,
        source_event_id="evt_abc123",
        consolidation_cycle_id="cycle_xyz",
    )


@pytest.fixture
def minimal_context() -> ObservationContext:
    """Create context with only required fields."""
    return ObservationContext(observed_at=1704067200000)


# =============================================================================
# Test ObservationRecorder.record()
# =============================================================================


class TestRecord:
    """Test single observation recording."""

    @pytest.mark.asyncio
    async def test_record_generates_ulid(
        self,
        recorder: ObservationRecorder,
        mock_uow: MockUnitOfWork,
        minimal_context: ObservationContext,
    ):
        """Verify record() returns a ULID."""
        obs_id = await recorder.record(
            uow=mock_uow,
            layer="st_epi",
            record_id="episode_123",
            context=minimal_context,
            tenant_id="tenant_1",
        )

        # ULID is 26 characters
        assert len(obs_id) == 26
        assert obs_id.isalnum()

    @pytest.mark.asyncio
    async def test_record_executes_insert(
        self,
        recorder: ObservationRecorder,
        mock_uow: MockUnitOfWork,
        minimal_context: ObservationContext,
    ):
        """Verify record() executes INSERT SQL."""
        await recorder.record(
            uow=mock_uow,
            layer="st_sem",
            record_id="pattern_456",
            context=minimal_context,
            tenant_id="tenant_1",
        )

        assert len(mock_uow.connection.execute_calls) == 1
        sql, args = mock_uow.connection.execute_calls[0]
        assert "INSERT INTO st_observations" in sql

    @pytest.mark.asyncio
    async def test_record_passes_all_context_fields(
        self,
        recorder: ObservationRecorder,
        mock_uow: MockUnitOfWork,
        full_context: ObservationContext,
    ):
        """Verify all context fields are passed to SQL."""
        await recorder.record(
            uow=mock_uow,
            layer="st_epi",
            record_id="episode_123",
            context=full_context,
            tenant_id="tenant_1",
        )

        sql, args = mock_uow.connection.execute_calls[0]

        # Check positional args (32 total)
        assert len(args) == 32

        # Verify key values
        # args[0] = observation_id (ULID)
        assert args[1] == "tenant_1"  # tenant_id
        assert args[2] == "st_epi"  # layer
        assert args[3] == "episode_123"  # record_id
        assert args[4] == 1704067200000  # observed_at
        assert args[5] == "REINFORCEMENT"  # observation_type
        assert args[6] == "evt_abc123"  # source_event_id
        assert args[7] == 0.95  # confidence -> observation_weight
        assert args[8] == 0.8  # sentiment_score
        assert args[9] == "positive"  # sentiment_label

    @pytest.mark.asyncio
    async def test_record_validates_layer(
        self,
        recorder: ObservationRecorder,
        mock_uow: MockUnitOfWork,
        minimal_context: ObservationContext,
    ):
        """Verify record() rejects invalid layers."""
        with pytest.raises(ValueError, match="Invalid layer"):
            await recorder.record(
                uow=mock_uow,
                layer="invalid_table",
                record_id="record_123",
                context=minimal_context,
                tenant_id="tenant_1",
            )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("layer", VALID_LAYERS)
    async def test_record_accepts_valid_layers(
        self,
        recorder: ObservationRecorder,
        mock_uow: MockUnitOfWork,
        minimal_context: ObservationContext,
        layer: str,
    ):
        """Verify record() accepts all valid layers."""
        obs_id = await recorder.record(
            uow=mock_uow,
            layer=layer,
            record_id="record_123",
            context=minimal_context,
            tenant_id="tenant_1",
        )

        assert obs_id is not None
        assert len(mock_uow.connection.execute_calls) == 1

    @pytest.mark.asyncio
    async def test_record_handles_none_optional_fields(
        self,
        recorder: ObservationRecorder,
        mock_uow: MockUnitOfWork,
        minimal_context: ObservationContext,
    ):
        """Verify None values are passed correctly for optional fields."""
        await recorder.record(
            uow=mock_uow,
            layer="st_kg_dom",
            record_id="entity_789",
            context=minimal_context,
            tenant_id="tenant_1",
        )

        sql, args = mock_uow.connection.execute_calls[0]

        # Most optional fields should be None
        assert args[8] is None  # sentiment_score
        assert args[9] is None  # sentiment_label
        assert args[31] is None  # original_temporal_expr


# =============================================================================
# Test ObservationRecorder.record_batch()
# =============================================================================


class TestRecordBatch:
    """Test batch observation recording."""

    @pytest.mark.asyncio
    async def test_record_batch_returns_all_ids(
        self,
        recorder: ObservationRecorder,
        mock_uow: MockUnitOfWork,
        minimal_context: ObservationContext,
    ):
        """Verify record_batch() returns all observation IDs."""
        observations = [
            ("st_epi", "episode_1", minimal_context, "tenant_1"),
            ("st_sem", "pattern_1", minimal_context, "tenant_1"),
            ("st_kg_dom", "entity_1", minimal_context, "tenant_1"),
        ]

        obs_ids = await recorder.record_batch(uow=mock_uow, observations=observations)

        assert len(obs_ids) == 3
        assert all(len(oid) == 26 for oid in obs_ids)
        assert len(set(obs_ids)) == 3  # All unique

    @pytest.mark.asyncio
    async def test_record_batch_executes_multiple_inserts(
        self,
        recorder: ObservationRecorder,
        mock_uow: MockUnitOfWork,
        minimal_context: ObservationContext,
    ):
        """Verify record_batch() executes multiple INSERT statements."""
        observations = [
            ("st_epi", "episode_1", minimal_context, "tenant_1"),
            ("st_epi", "episode_2", minimal_context, "tenant_1"),
        ]

        await recorder.record_batch(uow=mock_uow, observations=observations)

        assert len(mock_uow.connection.execute_calls) == 2

    @pytest.mark.asyncio
    async def test_record_batch_empty_list(
        self, recorder: ObservationRecorder, mock_uow: MockUnitOfWork
    ):
        """Verify record_batch() handles empty list."""
        obs_ids = await recorder.record_batch(uow=mock_uow, observations=[])

        assert obs_ids == []
        assert len(mock_uow.connection.execute_calls) == 0


# =============================================================================
# Test Convenience Methods
# =============================================================================


class TestConvenienceMethods:
    """Test record_for_insert() and record_for_merge()."""

    @pytest.mark.asyncio
    async def test_record_for_insert_sets_first_seen(
        self,
        recorder: ObservationRecorder,
        mock_uow: MockUnitOfWork,
        minimal_context: ObservationContext,
    ):
        """Verify record_for_insert() sets observation_type to FIRST_SEEN."""
        await recorder.record_for_insert(
            uow=mock_uow,
            layer="st_epi",
            record_id="episode_new",
            context=minimal_context,
            tenant_id="tenant_1",
        )

        sql, args = mock_uow.connection.execute_calls[0]
        assert args[5] == "FIRST_SEEN"  # observation_type

    @pytest.mark.asyncio
    async def test_record_for_merge_sets_reinforcement(
        self,
        recorder: ObservationRecorder,
        mock_uow: MockUnitOfWork,
        minimal_context: ObservationContext,
    ):
        """Verify record_for_merge() sets observation_type to REINFORCEMENT."""
        await recorder.record_for_merge(
            uow=mock_uow,
            layer="st_sem",
            record_id="pattern_existing",
            context=minimal_context,
            tenant_id="tenant_1",
        )

        sql, args = mock_uow.connection.execute_calls[0]
        assert args[5] == "REINFORCEMENT"  # observation_type

    @pytest.mark.asyncio
    async def test_record_for_insert_preserves_other_context(
        self,
        recorder: ObservationRecorder,
        mock_uow: MockUnitOfWork,
        full_context: ObservationContext,
    ):
        """Verify record_for_insert() preserves other context fields."""
        await recorder.record_for_insert(
            uow=mock_uow,
            layer="st_social",
            record_id="relationship_new",
            context=full_context,
            tenant_id="tenant_1",
        )

        sql, args = mock_uow.connection.execute_calls[0]

        # Other fields should be preserved
        assert args[4] == 1704067200000  # observed_at
        assert args[8] == 0.8  # sentiment_score
        assert args[16] == "voice"  # ingress_channel


# =============================================================================
# Test Singleton
# =============================================================================


class TestSingleton:
    """Test get_observation_recorder() singleton."""

    def test_get_observation_recorder_returns_instance(self):
        """Verify get_observation_recorder() returns an instance."""
        recorder = get_observation_recorder()
        assert isinstance(recorder, ObservationRecorder)

    def test_get_observation_recorder_returns_same_instance(self):
        """Verify get_observation_recorder() returns the same instance."""
        recorder1 = get_observation_recorder()
        recorder2 = get_observation_recorder()
        assert recorder1 is recorder2


# =============================================================================
# Test Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_record_with_zero_timestamp(
        self, recorder: ObservationRecorder, mock_uow: MockUnitOfWork
    ):
        """Verify record() handles zero timestamp."""
        context = ObservationContext(observed_at=0)

        obs_id = await recorder.record(
            uow=mock_uow,
            layer="st_epi",
            record_id="episode_1",
            context=context,
            tenant_id="tenant_1",
        )

        assert obs_id is not None
        sql, args = mock_uow.connection.execute_calls[0]
        assert args[4] == 0  # observed_at

    @pytest.mark.asyncio
    async def test_record_with_unicode_location(
        self, recorder: ObservationRecorder, mock_uow: MockUnitOfWork
    ):
        """Verify record() handles unicode in location_name."""
        context = ObservationContext(
            observed_at=1704067200000,
            location_name="東京駅",
            location_type="transit",
        )

        _ = await recorder.record(
            uow=mock_uow,  # type: ignore[arg-type]
            layer="st_epi",
            record_id="episode_1",
            context=context,
            tenant_id="tenant_1",
        )

        sql, args = mock_uow.connection.execute_calls[0]
        assert args[19] == "東京駅"  # location_name

    @pytest.mark.asyncio
    async def test_record_with_extreme_sentiment_values(
        self, recorder: ObservationRecorder, mock_uow: MockUnitOfWork
    ):
        """Verify record() handles extreme sentiment values."""
        context = ObservationContext(
            observed_at=1704067200000,
            sentiment_score=0.0,
            affect_valence=-1.0,
            affect_arousal=1.0,
        )

        _ = await recorder.record(
            uow=mock_uow,  # type: ignore[arg-type]
            layer="st_sem",
            record_id="pattern_1",
            context=context,
            tenant_id="tenant_1",
        )

        sql, args = mock_uow.connection.execute_calls[0]
        assert args[8] == 0.0  # sentiment_score
        assert args[10] == -1.0  # affect_valence
        assert args[11] == 1.0  # affect_arousal
