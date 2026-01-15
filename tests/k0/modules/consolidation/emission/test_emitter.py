"""
Tests for EventEmitter — Issue 5.2.11

Tests for R8 bus event emission via outbox pattern.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from k0.modules.consolidation.emission.emitter import (
    CircuitBreakerConfig,
    EmitResult,
    EventEmitter,
    EventTopic,
    create_event_emitter,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_uow():
    """Create mock UnitOfWork with outbox staging."""
    uow = MagicMock()
    uow.stage_outbox = MagicMock()
    return uow


@pytest.fixture
def mock_envelope():
    """Create mock P03BatchEnvelope."""
    envelope = MagicMock()
    envelope.context.cycle_id = "cycle_001"
    envelope.context.tenant_id = "tenant_abc"
    envelope.context.space_id = "space_xyz"
    envelope.phase_statuses = {}
    return envelope


@pytest.fixture
def mock_summary():
    """Create mock ReconciliationSummary."""
    summary = MagicMock()
    summary.total_events = 100
    summary.consolidated_count = 80
    summary.duplicate_count = 10
    summary.pruned_count = 5
    summary.pending_review_count = 5
    summary.action_breakdown = (
        ("CREATE", 20),
        ("REINFORCE", 50),
        ("EVOLVE", 5),
        ("PRUNE", 5),
    )
    summary.layer_write_counts = (
        ("st_event", 30),
        ("st_entity", 20),
        ("st_sem", 5),
        ("st_kg_edges", 10),
    )
    summary.kg_entity_count = 15
    summary.kg_edge_count = 10
    summary.gap_count = 3
    summary.cycle_duration_ms = 500
    return summary


@pytest.fixture
def emitter():
    """Create EventEmitter with default config."""
    return EventEmitter()


@pytest.fixture
def emitter_with_config():
    """Create EventEmitter with custom circuit breaker config."""
    config = CircuitBreakerConfig(
        failure_threshold=3,
        reset_timeout_ms=30000,
        queue_on_failure=True,
    )
    return EventEmitter(circuit_config=config)


# ============================================================================
# EventTopic Tests
# ============================================================================


class TestEventTopic:
    """Tests for EventTopic enum."""

    def test_all_topics_defined(self):
        """All required event topics are defined."""
        topics = list(EventTopic)
        assert len(topics) == 7  # Issue 8.1.13: Added INSIGHT_GENERATED

        assert EventTopic.CONSOLIDATION_COMPLETE.value == "p03.consolidation.complete.v1"
        assert EventTopic.PATTERN_DETECTED.value == "p03.pattern.detected.v1"
        assert EventTopic.TRUTH_REINFORCED.value == "p03.truth.reinforced.v1"
        assert EventTopic.TRUTH_CREATED.value == "p03.truth.created.v1"
        assert EventTopic.TRUTH_EVOLVED.value == "p03.truth.evolved.v1"
        assert EventTopic.MEMORY_PRUNED.value == "p03.memory.pruned.v1"
        # Issue 8.1.13: R5 insight event topic
        assert EventTopic.INSIGHT_GENERATED.value == "p03.insight.generated.v1"


# ============================================================================
# EmitResult Tests
# ============================================================================


class TestEmitResult:
    """Tests for EmitResult dataclass."""

    def test_default_values(self):
        """EmitResult initializes with correct defaults."""
        result = EmitResult()

        assert result.total_emitted == 0
        assert result.by_topic == {}
        assert result.failed == []
        assert result.duration_ms == 0

    def test_success_property_true_no_failures(self):
        """success is True when no failures."""
        result = EmitResult(total_emitted=5)
        assert result.success is True

    def test_success_property_false_with_failures(self):
        """success is False when failures exist."""
        result = EmitResult(total_emitted=5, failed=["fp_001"])
        assert result.success is False

    def test_by_topic_tracking(self):
        """by_topic correctly tracks event counts."""
        result = EmitResult()
        result.by_topic["p03.consolidation.complete.v1"] = 1
        result.by_topic["p03.truth.created.v1"] = 3

        assert result.by_topic["p03.consolidation.complete.v1"] == 1
        assert result.by_topic["p03.truth.created.v1"] == 3


# ============================================================================
# CircuitBreakerConfig Tests
# ============================================================================


class TestCircuitBreakerConfig:
    """Tests for CircuitBreakerConfig."""

    def test_default_values(self):
        """CircuitBreakerConfig has correct defaults."""
        config = CircuitBreakerConfig()

        assert config.failure_threshold == 5
        assert config.reset_timeout_ms == 60000
        assert config.queue_on_failure is True

    def test_custom_values(self):
        """CircuitBreakerConfig accepts custom values."""
        config = CircuitBreakerConfig(
            failure_threshold=10,
            reset_timeout_ms=120000,
            queue_on_failure=False,
        )

        assert config.failure_threshold == 10
        assert config.reset_timeout_ms == 120000
        assert config.queue_on_failure is False


# ============================================================================
# EventEmitter Tests
# ============================================================================


class TestEventEmitter:
    """Tests for EventEmitter class."""

    @pytest.mark.asyncio
    async def test_emit_all_emits_completion_event(
        self, emitter, mock_uow, mock_envelope, mock_summary
    ):
        """emit_all always emits completion event."""
        result = await emitter.emit_all(mock_uow, mock_envelope, mock_summary)

        assert result.total_emitted > 0
        assert EventTopic.CONSOLIDATION_COMPLETE.value in result.by_topic
        assert result.by_topic[EventTopic.CONSOLIDATION_COMPLETE.value] == 1

    @pytest.mark.asyncio
    async def test_emit_all_emits_action_events(
        self, emitter, mock_uow, mock_envelope, mock_summary
    ):
        """emit_all emits events based on action_breakdown."""
        result = await emitter.emit_all(mock_uow, mock_envelope, mock_summary)

        # Should have REINFORCE event (50 count)
        assert EventTopic.TRUTH_REINFORCED.value in result.by_topic

        # Should have CREATE events (20 count, 5 st_sem + 15 other)
        # This creates both PATTERN_DETECTED and TRUTH_CREATED
        assert EventTopic.PATTERN_DETECTED.value in result.by_topic
        assert EventTopic.TRUTH_CREATED.value in result.by_topic

        # Should have EVOLVE event (5 count)
        assert EventTopic.TRUTH_EVOLVED.value in result.by_topic

        # Should have PRUNE event (5 count)
        assert EventTopic.MEMORY_PRUNED.value in result.by_topic

    @pytest.mark.asyncio
    async def test_emit_all_stages_outbox_entries(
        self, emitter, mock_uow, mock_envelope, mock_summary
    ):
        """emit_all stages OutboxEntry for each event."""
        await emitter.emit_all(mock_uow, mock_envelope, mock_summary)

        # Should have staged multiple events
        assert mock_uow.stage_outbox.call_count >= 5  # At least 5 event types

    @pytest.mark.asyncio
    async def test_emit_all_returns_duration_ms(
        self, emitter, mock_uow, mock_envelope, mock_summary
    ):
        """emit_all records duration in milliseconds."""
        result = await emitter.emit_all(mock_uow, mock_envelope, mock_summary)

        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_emit_completion_only(self, emitter, mock_uow, mock_envelope, mock_summary):
        """emit_completion emits only completion event."""
        result = await emitter.emit_completion(mock_uow, mock_envelope, mock_summary)

        assert result.total_emitted == 1
        assert EventTopic.CONSOLIDATION_COMPLETE.value in result.by_topic
        assert len(result.by_topic) == 1

    @pytest.mark.asyncio
    async def test_emit_all_no_actions(self, emitter, mock_uow, mock_envelope, mock_summary):
        """emit_all handles empty action_breakdown."""
        mock_summary.action_breakdown = ()
        mock_summary.layer_write_counts = ()

        result = await emitter.emit_all(mock_uow, mock_envelope, mock_summary)

        # Should still emit completion
        assert result.total_emitted == 1
        assert EventTopic.CONSOLIDATION_COMPLETE.value in result.by_topic

    @pytest.mark.asyncio
    async def test_outbox_entry_structure(self, emitter, mock_uow, mock_envelope, mock_summary):
        """Staged OutboxEntry has correct structure."""
        await emitter.emit_completion(mock_uow, mock_envelope, mock_summary)

        # Get the staged entry
        call_args = mock_uow.stage_outbox.call_args
        entry = call_args[0][0]

        assert entry.tenant_id == "tenant_abc"
        assert entry.space_id == "space_xyz"
        assert entry.driver == "p03"
        assert entry.op_kind == EventTopic.CONSOLIDATION_COMPLETE.value
        assert "complete:cycle_001" in entry.fingerprint

        # Verify payload is valid JSON
        payload = json.loads(entry.payload.decode("utf-8"))
        assert payload["cycle_id"] == "cycle_001"
        assert "summary" in payload
        assert "completed_at" in payload


# ============================================================================
# Circuit Breaker Tests
# ============================================================================


class TestCircuitBreaker:
    """Tests for circuit breaker behavior."""

    @pytest.mark.asyncio
    async def test_circuit_opens_after_threshold(self, mock_uow, mock_envelope, mock_summary):
        """Circuit opens after failure threshold reached."""
        config = CircuitBreakerConfig(failure_threshold=2, reset_timeout_ms=60000)
        emitter = EventEmitter(circuit_config=config)

        # Simulate failures
        emitter._failures = 2
        emitter._last_failure_ms = 9999999999999  # Future time

        assert emitter._is_circuit_open() is True

    def test_circuit_closed_below_threshold(self, emitter_with_config):
        """Circuit stays closed below failure threshold."""
        emitter_with_config._failures = 2

        assert emitter_with_config._is_circuit_open() is False

    def test_reset_circuit_breaker(self, emitter_with_config):
        """reset_circuit_breaker clears failure state."""
        emitter_with_config._failures = 5
        emitter_with_config._last_failure_ms = 1000

        emitter_with_config.reset_circuit_breaker()

        assert emitter_with_config._failures == 0
        assert emitter_with_config._last_failure_ms == 0


# ============================================================================
# Factory Tests
# ============================================================================


class TestCreateEventEmitter:
    """Tests for create_event_emitter factory."""

    def test_creates_with_defaults(self):
        """Factory creates emitter with default config."""
        emitter = create_event_emitter()

        assert isinstance(emitter, EventEmitter)
        assert emitter._circuit_config.failure_threshold == 5

    def test_creates_with_custom_config(self):
        """Factory creates emitter with custom config."""
        config = CircuitBreakerConfig(failure_threshold=10)
        emitter = create_event_emitter(circuit_config=config)

        assert emitter._circuit_config.failure_threshold == 10


# ============================================================================
# Issue 8.1.13 — Insight Event Emission Tests
# ============================================================================


def make_insight(insight_id: str, **overrides):
    """Create a mock Insight for testing."""
    from k0.pipelines.p03.phase_outputs import Insight

    defaults = {
        "insight_id": insight_id,
        "insight_type": "BRIDGE",
        "concept_a_id": "concept_001",
        "concept_b_id": "concept_002",
        "pmi_score": 4.5,
        "novelty_score": 0.85,
        "relevance_score": 0.75,
        "natural_language": f"Insight {insight_id} connects concepts",
        "evidence_ids": ["ev1", "ev2"],
    }
    defaults.update(overrides)
    return Insight(**defaults)


class TestEmitInsightEvents:
    """Tests for Issue 8.1.13 emit_insight_events method."""

    @pytest.mark.asyncio
    async def test_emit_single_insight(self, emitter, mock_uow, mock_envelope):
        """emit_insight_events emits single insight event."""
        insights = [make_insight("insight_001")]

        result = await emitter.emit_insight_events(mock_uow, mock_envelope, insights)

        assert result.total_emitted == 1
        assert mock_uow.stage_outbox.call_count == 1

    @pytest.mark.asyncio
    async def test_emit_multiple_insights(self, emitter, mock_uow, mock_envelope):
        """emit_insight_events emits multiple insight events."""
        insights = [
            make_insight("insight_001"),
            make_insight("insight_002"),
            make_insight("insight_003"),
        ]

        result = await emitter.emit_insight_events(mock_uow, mock_envelope, insights)

        assert result.total_emitted == 3
        assert mock_uow.stage_outbox.call_count == 3

    @pytest.mark.asyncio
    async def test_emit_insight_correct_topic(self, emitter, mock_uow, mock_envelope):
        """emit_insight_events uses correct topic."""
        insights = [make_insight("insight_001")]

        await emitter.emit_insight_events(mock_uow, mock_envelope, insights)

        # Check the staged outbox entry
        call_args = mock_uow.stage_outbox.call_args
        entry = call_args[0][0]
        assert entry.op_kind == "p03.insight.generated.v1"

    @pytest.mark.asyncio
    async def test_emit_insight_deterministic_fingerprint(
        self, emitter, mock_uow, mock_envelope
    ):
        """emit_insight_events uses deterministic idempotency key."""
        insights = [make_insight("insight_001")]
        mock_envelope.context.cycle_id = "cycle_ABC"

        await emitter.emit_insight_events(mock_uow, mock_envelope, insights)

        call_args = mock_uow.stage_outbox.call_args
        entry = call_args[0][0]
        # Pattern: {cycle_id}:insight:{insight_id}
        assert entry.fingerprint == "cycle_ABC:insight:insight_001"

    @pytest.mark.asyncio
    async def test_emit_insight_payload_fields(self, emitter, mock_uow, mock_envelope):
        """emit_insight_events includes all required payload fields."""
        import json

        insight = make_insight(
            "insight_001",
            insight_type="PATTERN",
            concept_a_id="entity_A",
            concept_b_id="entity_B",
            pmi_score=5.0,
            novelty_score=0.9,
            relevance_score=0.8,
            natural_language="A relates to B",
            evidence_ids=["e1", "e2", "e3"],
        )

        await emitter.emit_insight_events(mock_uow, mock_envelope, [insight])

        call_args = mock_uow.stage_outbox.call_args
        entry = call_args[0][0]
        payload = json.loads(entry.payload.decode("utf-8"))

        assert payload["insight_id"] == "insight_001"
        assert payload["insight_type"] == "PATTERN"
        assert payload["concept_a_id"] == "entity_A"
        assert payload["concept_b_id"] == "entity_B"
        assert payload["pmi_score"] == 5.0
        assert payload["novelty_score"] == 0.9
        assert payload["relevance_score"] == 0.8
        assert payload["confidence"] == 0.8  # Same as relevance_score
        assert payload["description"] == "A relates to B"
        assert payload["supporting_evidence"] == ["e1", "e2", "e3"]
        assert "generated_at" in payload

    @pytest.mark.asyncio
    async def test_emit_insight_empty_list(self, emitter, mock_uow, mock_envelope):
        """emit_insight_events handles empty list."""
        result = await emitter.emit_insight_events(mock_uow, mock_envelope, [])

        assert result.total_emitted == 0
        assert mock_uow.stage_outbox.call_count == 0

    @pytest.mark.asyncio
    async def test_emit_insight_result_tracking(self, emitter, mock_uow, mock_envelope):
        """emit_insight_events correctly tracks results."""
        insights = [make_insight("insight_001"), make_insight("insight_002")]

        result = await emitter.emit_insight_events(mock_uow, mock_envelope, insights)

        assert result.total_emitted == 2
        assert EventTopic.INSIGHT_GENERATED.value in result.by_topic
        assert result.by_topic[EventTopic.INSIGHT_GENERATED.value] == 2
        assert result.success is True
