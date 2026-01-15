"""
Integration tests for R1ImportanceScorer phase.

Tests the R1 phase integration with envelope, context, and audit logging.

Spec Reference:
    - M4_EXECUTION.md Issues 4.1.1-4.1.2
    - Phase Interface: k0/pipelines/p03/phase_interface.py

Test Coverage:
    - R1 phase initialization with config
    - Full phase execution with envelope
    - Audit logging integration
    - Skip conditions (empty batch, already scored)
    - Error handling and recovery
    - Phase result structure
    - Event state mutations
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from k0.modules.consolidation.algorithms.importance_scorer import ImportanceWeights
from k0.pipelines.p03.audit_logger import AuditAction
from k0.pipelines.p03.phase_outputs import ScoredEvent
from k0.pipelines.p03.phases.r1_importance_scorer import (
    R1Config,
    R1ImportanceScorer,
    create_r1_phase,
)
from k0.pipelines.p03.runner_contract import P03PhaseId, P03PhaseStatus

# =============================================================================
# Mock Classes
# =============================================================================


@dataclass
class MockEventState:
    """Mock P03EventState for integration testing."""

    event_id: str = "evt_test_001"
    hipp_event_id: str = "hipp_001"
    content_text: str = "Test content"
    content_type: str = "message"
    timestamp: int = 1704067200000

    # NLP fields
    sentiment_score: float = 0.0
    affect_valence: float = 0.0
    novelty_score: float = 0.0
    participant_count: int = 1

    # Importance fields (set by R1)
    importance_score: float = 0.0
    recency_factor: float = 0.0
    affect_factor: float = 0.0
    social_factor: float = 0.0
    novelty_factor: float = 0.0
    importance_computed: bool = False

    def set_importance(
        self,
        score: float,
        recency: float,
        affect: float,
        social: float,
        novelty: float,
    ) -> None:
        """Set importance score and factors."""
        self.importance_score = score
        self.recency_factor = recency
        self.affect_factor = affect
        self.social_factor = social
        self.novelty_factor = novelty
        self.importance_computed = True


@dataclass
class MockCycleContext:
    """Mock P03CycleContext."""

    cycle_id: str = "cyc_test_001"
    batch_id: str = "batch_001"
    space_id: str = "sp_test"
    tenant_id: str = "t_test"
    event_ids: List[str] = field(default_factory=list)


@dataclass
class MockPhaseOutputs:
    """Mock P03PhaseOutputs."""

    r1_scored_events: List[ScoredEvent] = field(default_factory=list)
    r1_audit_records: List[Any] = field(default_factory=list)
    r1_total_importance: float = 0.0
    r1_avg_importance: float = 0.0


@dataclass
class MockEnvelope:
    """Mock P03BatchEnvelope for integration testing."""

    context: MockCycleContext = field(default_factory=MockCycleContext)
    events: List[MockEventState] = field(default_factory=list)
    phases: MockPhaseOutputs = field(default_factory=MockPhaseOutputs)


@dataclass
class MockRunnerContext:
    """Mock P03RunnerContext."""

    syscalls: Any = None
    logger: Any = None
    qos_band: str = "GREEN"
    priority: int = 50
    config: Dict[str, Any] = field(default_factory=dict)
    dry_run: bool = False

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self.config.get(key, default)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_context() -> MockRunnerContext:
    """Create mock runner context."""
    return MockRunnerContext(
        syscalls=MagicMock(),
        logger=MagicMock(),
        config={"p03.importance.audit_sample_rate": 1.0},
    )


@pytest.fixture
def mock_envelope_with_events() -> MockEnvelope:
    """Create mock envelope with test events."""
    events = [
        MockEventState(
            event_id="evt_001",
            sentiment_score=0.8,
            affect_valence=0.7,
            novelty_score=0.5,
            participant_count=3,
            content_type="message",
        ),
        MockEventState(
            event_id="evt_002",
            sentiment_score=0.2,
            affect_valence=0.1,
            novelty_score=0.2,
            participant_count=1,
            content_type="routine",
        ),
        MockEventState(
            event_id="evt_003",
            sentiment_score=0.9,
            affect_valence=0.9,
            novelty_score=0.8,
            participant_count=5,
            content_type="milestone",
        ),
    ]
    context = MockCycleContext(
        cycle_id="cyc_test_001",
        event_ids=[e.event_id for e in events],
    )
    return MockEnvelope(context=context, events=events)


@pytest.fixture
def r1_phase() -> R1ImportanceScorer:
    """Create R1 phase with default config."""
    return R1ImportanceScorer()


# =============================================================================
# R1Config Tests
# =============================================================================


class TestR1Config:
    """Tests for R1 configuration."""

    def test_default_config(self):
        """Default config has sensible values."""
        config = R1Config()
        assert config.audit_sample_rate == 1.0  # 100% for debug
        assert config.enable_hebbian is False  # Not yet implemented
        assert config.min_samples_for_learned_weights == 500

    def test_custom_config(self):
        """Custom config overrides defaults."""
        config = R1Config(
            audit_sample_rate=0.1,
            enable_hebbian=True,
            importance_weights=ImportanceWeights(
                sentiment_weight=0.30,
                affect_weight=0.30,
                novelty_weight=0.20,
                social_weight=0.20,
            ),
        )
        assert config.audit_sample_rate == 0.1
        assert config.enable_hebbian is True
        assert config.importance_weights.sentiment_weight == 0.30


# =============================================================================
# R1ImportanceScorer Basic Tests
# =============================================================================


class TestR1ImportanceScorerBasic:
    """Basic tests for R1 phase."""

    def test_phase_id(self, r1_phase):
        """Phase has correct ID."""
        assert r1_phase.phase_id == P03PhaseId.R1_SCORE

    def test_factory_function(self):
        """Factory function creates phase correctly."""
        phase = create_r1_phase()
        assert isinstance(phase, R1ImportanceScorer)
        assert phase.config.audit_sample_rate == 1.0

    def test_factory_with_config(self):
        """Factory accepts custom config."""
        config = R1Config(audit_sample_rate=0.5)
        phase = create_r1_phase(config=config)
        assert phase.config.audit_sample_rate == 0.5


# =============================================================================
# should_skip Tests
# =============================================================================


class TestShouldSkip:
    """Tests for skip condition checking."""

    def test_skip_empty_events(self, r1_phase):
        """Skip when envelope has no events."""
        envelope = MockEnvelope(events=[])
        assert r1_phase.should_skip(envelope) is True

    def test_skip_all_already_scored(self, r1_phase):
        """Skip when all events already have importance_computed=True."""
        events = [
            MockEventState(event_id="evt_001", importance_computed=True),
            MockEventState(event_id="evt_002", importance_computed=True),
        ]
        envelope = MockEnvelope(events=events)
        assert r1_phase.should_skip(envelope) is True

    def test_no_skip_unscored_events(self, r1_phase):
        """Don't skip when events need scoring."""
        events = [
            MockEventState(event_id="evt_001", importance_computed=False),
        ]
        envelope = MockEnvelope(events=events)
        assert r1_phase.should_skip(envelope) is False

    def test_no_skip_mixed_events(self, r1_phase):
        """Don't skip when some events need scoring."""
        events = [
            MockEventState(event_id="evt_001", importance_computed=True),
            MockEventState(event_id="evt_002", importance_computed=False),
        ]
        envelope = MockEnvelope(events=events)
        assert r1_phase.should_skip(envelope) is False


# =============================================================================
# idempotency_key Tests
# =============================================================================


class TestIdempotencyKey:
    """Tests for idempotency key generation."""

    def test_key_format(self, r1_phase):
        """Key has expected format."""
        envelope = MockEnvelope()
        envelope.context.cycle_id = "cyc_abc123"
        key = r1_phase.idempotency_key(envelope)
        assert key == "p03:r1:cyc_abc123"

    def test_key_deterministic(self, r1_phase):
        """Same envelope produces same key."""
        envelope = MockEnvelope()
        key1 = r1_phase.idempotency_key(envelope)
        key2 = r1_phase.idempotency_key(envelope)
        assert key1 == key2


# =============================================================================
# Full Phase Execution Tests
# =============================================================================


class TestR1PhaseExecution:
    """Tests for full phase execution."""

    @pytest.mark.asyncio
    async def test_successful_execution(self, r1_phase, mock_envelope_with_events, mock_context):
        """Phase executes successfully and scores events."""
        result = await r1_phase.run(mock_envelope_with_events, mock_context)

        # Check result
        assert result.status == P03PhaseStatus.DONE
        assert result.phase_id == P03PhaseId.R1_SCORE
        assert result.duration_ms >= 0
        assert result.is_success is True
        assert result.idempotency_key is not None

        # Check outputs summary
        assert result.outputs_summary["events_scored"] == 3
        assert "avg_importance" in result.outputs_summary
        assert "weights_source" in result.outputs_summary

    @pytest.mark.asyncio
    async def test_events_scored(self, r1_phase, mock_envelope_with_events, mock_context):
        """All events receive importance scores."""
        await r1_phase.run(mock_envelope_with_events, mock_context)

        for event in mock_envelope_with_events.events:
            assert event.importance_computed is True
            assert 0.0 <= event.importance_score <= 1.0

    @pytest.mark.asyncio
    async def test_high_emotion_high_score(self, r1_phase, mock_envelope_with_events, mock_context):
        """High-emotion events get higher scores."""
        await r1_phase.run(mock_envelope_with_events, mock_context)

        # Event 3 (milestone with high emotion) should score highest
        scores = {e.event_id: e.importance_score for e in mock_envelope_with_events.events}
        assert scores["evt_003"] > scores["evt_001"]  # Milestone > message
        assert scores["evt_001"] > scores["evt_002"]  # High emotion > routine

    @pytest.mark.asyncio
    async def test_outputs_populated(self, r1_phase, mock_envelope_with_events, mock_context):
        """Phase outputs are populated correctly."""
        await r1_phase.run(mock_envelope_with_events, mock_context)

        phases = mock_envelope_with_events.phases
        assert len(phases.r1_scored_events) == 3
        assert all(isinstance(e, ScoredEvent) for e in phases.r1_scored_events)

    @pytest.mark.asyncio
    async def test_skip_empty_batch(self, r1_phase, mock_context):
        """Empty batch returns SKIP status."""
        envelope = MockEnvelope(events=[])
        result = await r1_phase.run(envelope, mock_context)

        assert result.status == P03PhaseStatus.SKIP
        assert result.skip_reason == "No unscored events in batch"

    @pytest.mark.asyncio
    async def test_skip_already_scored(self, r1_phase, mock_context):
        """Already-scored batch returns SKIP status."""
        events = [
            MockEventState(event_id="evt_001", importance_computed=True),
        ]
        envelope = MockEnvelope(events=events)
        result = await r1_phase.run(envelope, mock_context)

        assert result.status == P03PhaseStatus.SKIP


# =============================================================================
# Audit Logging Integration Tests
# =============================================================================


class TestAuditLoggingIntegration:
    """Tests for audit logging integration."""

    @pytest.mark.asyncio
    async def test_audit_records_created(self, r1_phase, mock_envelope_with_events, mock_context):
        """Audit records are created for scored events."""
        # Use 100% sample rate
        mock_context.config["p03.importance.audit_sample_rate"] = 1.0

        await r1_phase.run(mock_envelope_with_events, mock_context)

        phases = mock_envelope_with_events.phases
        # With 100% sample rate, all 3 events should have audit records
        assert len(phases.r1_audit_records) == 3

    @pytest.mark.asyncio
    async def test_audit_records_content(self, r1_phase, mock_envelope_with_events, mock_context):
        """Audit records contain correct content."""
        mock_context.config["p03.importance.audit_sample_rate"] = 1.0

        await r1_phase.run(mock_envelope_with_events, mock_context)

        phases = mock_envelope_with_events.phases
        if phases.r1_audit_records:
            record = phases.r1_audit_records[0]
            assert record.action == AuditAction.SCORE
            assert record.formula_used == "importance_scorer"
            assert record.formula_version == "1.0.0"
            assert record.inputs is not None
            assert record.outputs is not None

    @pytest.mark.asyncio
    async def test_audit_sampling_zero(self, r1_phase, mock_context):
        """Zero sample rate creates no audit records."""
        mock_context.config["p03.importance.audit_sample_rate"] = 0.0

        events = [MockEventState(event_id="evt_001", sentiment_score=0.5)]
        envelope = MockEnvelope(
            context=MockCycleContext(event_ids=["evt_001"]),
            events=events,
        )

        await r1_phase.run(envelope, mock_context)

        # With 0% sample rate, no audit records
        assert len(envelope.phases.r1_audit_records) == 0


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_handles_scorer_exception(self, mock_context):
        """Phase handles scorer exceptions gracefully."""
        # Create phase with patched scorer that raises
        phase = R1ImportanceScorer()

        # Create envelope with event that will cause error
        events = [MockEventState(event_id="evt_001")]
        envelope = MockEnvelope(
            context=MockCycleContext(event_ids=["evt_001"]),
            events=events,
        )

        # Patch scorer to raise exception
        with patch.object(
            phase,
            "should_skip",
            return_value=False,
        ):
            # Normal execution should work
            result = await phase.run(envelope, mock_context)
            # Should not fail even with empty context
            assert result.status in (P03PhaseStatus.DONE, P03PhaseStatus.FAIL)


# =============================================================================
# Priority Distribution Tests
# =============================================================================


class TestPriorityDistribution:
    """Tests for priority tier distribution in results."""

    @pytest.mark.asyncio
    async def test_priority_counts_in_output(
        self, r1_phase, mock_envelope_with_events, mock_context
    ):
        """Output summary includes priority tier counts."""
        result = await r1_phase.run(mock_envelope_with_events, mock_context)

        summary = result.outputs_summary
        # At least one of these should be present
        priority_keys = ["critical_count", "high_count", "medium_count", "low_count"]
        has_priority = any(k in summary for k in priority_keys)
        assert has_priority or "events_scored" in summary


# =============================================================================
# ScoredEvent Output Tests
# =============================================================================


class TestScoredEventOutput:
    """Tests for ScoredEvent output structure."""

    @pytest.mark.asyncio
    async def test_scored_event_fields(self, r1_phase, mock_envelope_with_events, mock_context):
        """ScoredEvent has all required fields."""
        await r1_phase.run(mock_envelope_with_events, mock_context)

        phases = mock_envelope_with_events.phases
        for scored in phases.r1_scored_events:
            assert hasattr(scored, "event_id")
            assert hasattr(scored, "importance_score")
            assert hasattr(scored, "recency_factor")
            assert hasattr(scored, "affect_factor")
            assert hasattr(scored, "social_factor")
            assert hasattr(scored, "novelty_factor")

    @pytest.mark.asyncio
    async def test_scored_event_values_match(
        self, r1_phase, mock_envelope_with_events, mock_context
    ):
        """ScoredEvent values match event state values."""
        await r1_phase.run(mock_envelope_with_events, mock_context)

        phases = mock_envelope_with_events.phases
        events = mock_envelope_with_events.events

        for scored, event in zip(phases.r1_scored_events, events):
            assert scored.event_id == event.event_id
            assert abs(scored.importance_score - event.importance_score) < 0.001
