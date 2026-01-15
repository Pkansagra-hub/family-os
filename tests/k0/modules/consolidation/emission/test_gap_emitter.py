"""
Tests for GapEmitterModule — Issue 5.2.12

Tests for P06 Active Learning gap emission with deduplication and capping.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.modules.consolidation.emission.gap_emitter import (
    DEFAULT_TTL_HOURS,
    GAP_TOPIC,
    MAX_GAPS_PER_CYCLE,
    QUESTION_TEMPLATES,
    GapEmitStats,
    GapEmitterConfig,
    GapEmitterModule,
    create_gap_emitter,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_uow():
    """Create mock UnitOfWork with async connection and outbox staging."""
    uow = MagicMock()
    uow.connection = AsyncMock()
    uow.connection.execute = AsyncMock(return_value="INSERT 0 1")
    uow.stage_outbox = MagicMock()
    return uow


@pytest.fixture
def mock_envelope():
    """Create mock P03BatchEnvelope."""
    envelope = MagicMock()
    envelope.context.cycle_id = "cycle_001"
    envelope.context.tenant_id = "tenant_abc"
    envelope.context.space_id = "space_xyz"
    return envelope


def make_gap_candidate(
    gap_id: str,
    gap_type: str = "AMBIGUOUS_ENTITY",
    related_entity_id: str = "entity_001",
    entropy_score: float = 0.7,
    priority: int = 80,
    context_json: str = "{}",
    candidate_values: list | None = None,
) -> MagicMock:
    """Create mock GapCandidate."""
    gap = MagicMock()
    gap.gap_id = gap_id
    gap.gap_type = gap_type
    gap.related_entity_id = related_entity_id
    gap.entropy_score = entropy_score
    gap.priority = priority
    gap.context_json = context_json
    gap.candidate_values = candidate_values or ["value_a", "value_b"]
    return gap


@pytest.fixture
def sample_gaps():
    """Create sample list of GapCandidates."""
    return [
        make_gap_candidate("gap_001", "AMBIGUOUS_ENTITY", "entity_001", 0.7),
        make_gap_candidate("gap_002", "CONTRADICTION", "entity_002", 0.9),
        make_gap_candidate("gap_003", "LOW_CONFIDENCE_EDGE", "entity_003", 0.5),
    ]


@pytest.fixture
def gap_emitter():
    """Create GapEmitterModule with default config."""
    return GapEmitterModule()


@pytest.fixture
def gap_emitter_with_config():
    """Create GapEmitterModule with custom config."""
    config = GapEmitterConfig(
        max_gaps_per_cycle=5,
        ttl_hours=24,
        deduplicate=True,
        dedup_window_ms=1800000,  # 30 min
    )
    return GapEmitterModule(config=config)


# ============================================================================
# Constants Tests
# ============================================================================


class TestConstants:
    """Tests for module constants."""

    def test_max_gaps_per_cycle(self):
        """MAX_GAPS_PER_CYCLE has correct value."""
        assert MAX_GAPS_PER_CYCLE == 50

    def test_default_ttl_hours(self):
        """DEFAULT_TTL_HOURS is 7 days."""
        assert DEFAULT_TTL_HOURS == 168  # 7 * 24

    def test_gap_topic(self):
        """GAP_TOPIC has correct value."""
        assert GAP_TOPIC == "p03.gap.detected.v1"

    def test_question_templates_all_types(self):
        """QUESTION_TEMPLATES covers all gap types."""
        expected_types = {
            "AMBIGUOUS_ENTITY",
            "LOW_CONFIDENCE_EDGE",
            "MISSING_ATTRIBUTE",
            "CONTRADICTION",
            "CONCEPT_DRIFT",
            "STRUCTURAL_HOLE",
            "STALE_ANCHOR",
        }
        assert set(QUESTION_TEMPLATES.keys()) == expected_types


# ============================================================================
# GapEmitStats Tests
# ============================================================================


class TestGapEmitStats:
    """Tests for GapEmitStats dataclass."""

    def test_default_values(self):
        """GapEmitStats initializes with correct defaults."""
        stats = GapEmitStats()

        assert stats.total_received == 0
        assert stats.emitted == 0
        assert stats.deduplicated == 0
        assert stats.capped == 0
        assert stats.by_type == {}
        assert stats.by_priority == {}
        assert stats.duration_ms == 0

    def test_skipped_property(self):
        """skipped returns sum of deduplicated and capped."""
        stats = GapEmitStats(deduplicated=5, capped=3)
        assert stats.skipped == 8

    def test_tracking(self):
        """Stats correctly track emission counts."""
        stats = GapEmitStats(total_received=10, emitted=7, deduplicated=2, capped=1)

        assert stats.total_received == 10
        assert stats.emitted == 7
        assert stats.skipped == 3


# ============================================================================
# GapEmitterConfig Tests
# ============================================================================


class TestGapEmitterConfig:
    """Tests for GapEmitterConfig."""

    def test_default_values(self):
        """GapEmitterConfig has correct defaults."""
        config = GapEmitterConfig()

        assert config.topic == "p03.gap.detected.v1"
        assert config.max_gaps_per_cycle == 50
        assert config.ttl_hours == 168
        assert config.deduplicate is True
        assert config.dedup_window_ms == 3600000
        assert config.emit_to_outbox is True
        assert config.persist_to_queue is True

    def test_custom_values(self):
        """GapEmitterConfig accepts custom values."""
        config = GapEmitterConfig(
            max_gaps_per_cycle=25,
            ttl_hours=48,
            deduplicate=False,
            emit_to_outbox=False,
        )

        assert config.max_gaps_per_cycle == 25
        assert config.ttl_hours == 48
        assert config.deduplicate is False
        assert config.emit_to_outbox is False


# ============================================================================
# GapEmitterModule Tests
# ============================================================================


class TestGapEmitterModule:
    """Tests for GapEmitterModule class."""

    @pytest.mark.asyncio
    async def test_emit_empty_gaps(self, gap_emitter, mock_uow, mock_envelope):
        """emit handles empty gap list."""
        stats = await gap_emitter.emit(mock_uow, [], mock_envelope)

        assert stats.total_received == 0
        assert stats.emitted == 0
        assert mock_uow.stage_outbox.call_count == 0

    @pytest.mark.asyncio
    async def test_emit_all_gaps(self, gap_emitter, mock_uow, mock_envelope, sample_gaps):
        """emit processes all gaps when under cap."""
        stats = await gap_emitter.emit(mock_uow, sample_gaps, mock_envelope)

        assert stats.total_received == 3
        assert stats.emitted == 3
        assert stats.capped == 0

    @pytest.mark.asyncio
    async def test_emit_stages_outbox_entries(
        self, gap_emitter, mock_uow, mock_envelope, sample_gaps
    ):
        """emit stages OutboxEntry for each gap."""
        await gap_emitter.emit(mock_uow, sample_gaps, mock_envelope)

        # Each gap should be staged to outbox
        assert mock_uow.stage_outbox.call_count == 3

    @pytest.mark.asyncio
    async def test_emit_persists_to_queue(self, gap_emitter, mock_uow, mock_envelope, sample_gaps):
        """emit persists gaps to st_learning_queue."""
        await gap_emitter.emit(mock_uow, sample_gaps, mock_envelope)

        # Each gap should trigger a DB insert
        assert mock_uow.connection.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_emit_returns_duration(self, gap_emitter, mock_uow, mock_envelope, sample_gaps):
        """emit records duration in milliseconds."""
        stats = await gap_emitter.emit(mock_uow, sample_gaps, mock_envelope)

        assert stats.duration_ms >= 0


class TestPrioritySorting:
    """Tests for priority-based gap sorting."""

    @pytest.mark.asyncio
    async def test_high_priority_first(self, gap_emitter, mock_uow, mock_envelope):
        """Gaps are sorted by priority (highest first)."""
        gaps = [
            make_gap_candidate("gap_low", "MISSING_ATTRIBUTE", "e1", 0.5),  # priority 30
            make_gap_candidate("gap_high", "CONTRADICTION", "e2", 0.9),  # priority 100
            make_gap_candidate("gap_mid", "LOW_CONFIDENCE_EDGE", "e3", 0.6),  # priority 50
        ]

        await gap_emitter.emit(mock_uow, gaps, mock_envelope)

        # Verify order by checking staged outbox calls
        calls = mock_uow.stage_outbox.call_args_list
        assert len(calls) == 3

        # First call should be CONTRADICTION (priority 100)
        first_entry = calls[0][0][0]
        first_payload = json.loads(first_entry.payload.decode("utf-8"))
        assert first_payload["gap_type"] == "CONTRADICTION"


class TestDeduplication:
    """Tests for gap deduplication."""

    @pytest.mark.asyncio
    async def test_deduplicates_same_type_entity(self, gap_emitter, mock_uow, mock_envelope):
        """Deduplicates gaps with same type and entity."""
        gaps = [
            make_gap_candidate("gap_001", "AMBIGUOUS_ENTITY", "entity_same", 0.7),
            make_gap_candidate("gap_002", "AMBIGUOUS_ENTITY", "entity_same", 0.8),
            make_gap_candidate("gap_003", "AMBIGUOUS_ENTITY", "entity_same", 0.6),
        ]

        stats = await gap_emitter.emit(mock_uow, gaps, mock_envelope)

        assert stats.total_received == 3
        assert stats.emitted == 1
        assert stats.deduplicated == 2

    @pytest.mark.asyncio
    async def test_no_dedup_different_entities(self, gap_emitter, mock_uow, mock_envelope):
        """No deduplication for different entities."""
        gaps = [
            make_gap_candidate("gap_001", "AMBIGUOUS_ENTITY", "entity_001", 0.7),
            make_gap_candidate("gap_002", "AMBIGUOUS_ENTITY", "entity_002", 0.8),
        ]

        stats = await gap_emitter.emit(mock_uow, gaps, mock_envelope)

        assert stats.emitted == 2
        assert stats.deduplicated == 0

    @pytest.mark.asyncio
    async def test_reset_cycle_clears_dedup(self, gap_emitter, mock_uow, mock_envelope):
        """reset_cycle clears deduplication tracking."""
        gap = make_gap_candidate("gap_001", "AMBIGUOUS_ENTITY", "entity_001", 0.7)

        # Emit once
        await gap_emitter.emit(mock_uow, [gap], mock_envelope)

        # Reset cycle
        gap_emitter.reset_cycle()

        # Emit same gap again - should not be deduplicated
        stats = await gap_emitter.emit(mock_uow, [gap], mock_envelope)

        assert stats.emitted == 1
        assert stats.deduplicated == 0


class TestCapping:
    """Tests for gap cap enforcement."""

    @pytest.mark.asyncio
    async def test_caps_to_max(self, mock_uow, mock_envelope):
        """Caps gaps to max_gaps_per_cycle."""
        config = GapEmitterConfig(max_gaps_per_cycle=2)
        emitter = GapEmitterModule(config=config)

        gaps = [
            make_gap_candidate(f"gap_{i}", "AMBIGUOUS_ENTITY", f"entity_{i}", 0.5) for i in range(5)
        ]

        stats = await emitter.emit(mock_uow, gaps, mock_envelope)

        assert stats.total_received == 5
        assert stats.emitted == 2
        assert stats.capped == 3

    @pytest.mark.asyncio
    async def test_high_priority_not_capped(self, mock_uow, mock_envelope):
        """High priority gaps are emitted before capping."""
        config = GapEmitterConfig(max_gaps_per_cycle=1)
        emitter = GapEmitterModule(config=config)

        gaps = [
            make_gap_candidate("gap_low", "MISSING_ATTRIBUTE", "e1", 0.5),  # priority 30
            make_gap_candidate("gap_high", "CONTRADICTION", "e2", 0.9),  # priority 100
        ]

        await emitter.emit(mock_uow, gaps, mock_envelope)

        # Only CONTRADICTION should be emitted (highest priority)
        entry = mock_uow.stage_outbox.call_args[0][0]
        payload = json.loads(entry.payload.decode("utf-8"))
        assert payload["gap_type"] == "CONTRADICTION"


class TestOutboxEntryStructure:
    """Tests for OutboxEntry structure."""

    @pytest.mark.asyncio
    async def test_outbox_entry_fields(self, gap_emitter, mock_uow, mock_envelope):
        """Staged OutboxEntry has correct fields."""
        gap = make_gap_candidate("gap_001", "AMBIGUOUS_ENTITY", "entity_001", 0.7)

        await gap_emitter.emit(mock_uow, [gap], mock_envelope)

        entry = mock_uow.stage_outbox.call_args[0][0]

        assert entry.tenant_id == "tenant_abc"
        assert entry.space_id == "space_xyz"
        assert entry.driver == "p06"
        assert entry.op_kind == "p03.gap.detected.v1"
        assert "gap:gap_001" in entry.fingerprint

    @pytest.mark.asyncio
    async def test_outbox_payload_structure(self, gap_emitter, mock_uow, mock_envelope):
        """Outbox payload has correct structure."""
        context = {"conflicting_truths": ["truth_a", "truth_b"]}
        gap = make_gap_candidate(
            "gap_001",
            "AMBIGUOUS_ENTITY",
            "entity_001",
            0.7,
            context_json=json.dumps(context),
        )

        await gap_emitter.emit(mock_uow, [gap], mock_envelope)

        entry = mock_uow.stage_outbox.call_args[0][0]
        payload = json.loads(entry.payload.decode("utf-8"))

        assert payload["gap_id"] == "gap_001"
        assert payload["tenant_id"] == "tenant_abc"
        assert payload["space_id"] == "space_xyz"
        assert payload["gap_type"] == "AMBIGUOUS_ENTITY"
        assert payload["importance_score"] == 0.7
        assert payload["priority"] == 80
        assert "context" in payload
        assert "ttl_hours" in payload
        assert "detected_at" in payload


class TestQuestionTemplates:
    """Tests for question template generation."""

    def test_get_question_template_known_type(self, gap_emitter):
        """Returns correct template for known gap type."""
        gap = make_gap_candidate("gap_001", "AMBIGUOUS_ENTITY", "entity_001", 0.7)
        template = gap_emitter._get_question_template(gap)

        assert template == "Which of these best matches '{entity}'?"

    def test_get_question_template_unknown_type(self, gap_emitter):
        """Returns default template for unknown gap type."""
        gap = make_gap_candidate("gap_001", "UNKNOWN_TYPE", "entity_001", 0.7)
        template = gap_emitter._get_question_template(gap)

        assert template == "Can you clarify this?"


class TestStatsTracking:
    """Tests for emission statistics tracking."""

    @pytest.mark.asyncio
    async def test_by_type_tracking(self, gap_emitter, mock_uow, mock_envelope, sample_gaps):
        """Stats track counts by gap type."""
        stats = await gap_emitter.emit(mock_uow, sample_gaps, mock_envelope)

        assert "AMBIGUOUS_ENTITY" in stats.by_type
        assert "CONTRADICTION" in stats.by_type
        assert "LOW_CONFIDENCE_EDGE" in stats.by_type

    @pytest.mark.asyncio
    async def test_by_priority_tracking(self, gap_emitter, mock_uow, mock_envelope, sample_gaps):
        """Stats track counts by priority."""
        stats = await gap_emitter.emit(mock_uow, sample_gaps, mock_envelope)

        # Sample gaps have priorities: 80, 100, 50
        assert 80 in stats.by_priority
        assert 100 in stats.by_priority
        assert 50 in stats.by_priority


# ============================================================================
# Factory Tests
# ============================================================================


class TestCreateGapEmitter:
    """Tests for create_gap_emitter factory."""

    def test_creates_with_defaults(self):
        """Factory creates emitter with default config."""
        emitter = create_gap_emitter()

        assert isinstance(emitter, GapEmitterModule)
        assert emitter.config.max_gaps_per_cycle == 50

    def test_creates_with_custom_config(self):
        """Factory creates emitter with custom config."""
        config = GapEmitterConfig(max_gaps_per_cycle=25)
        emitter = create_gap_emitter(config=config)

        assert emitter.config.max_gaps_per_cycle == 25


# ============================================================================
# Queue Persistence Tests
# ============================================================================


class TestQueuePersistence:
    """Tests for st_learning_queue persistence."""

    @pytest.mark.asyncio
    async def test_persist_insert_sql(self, gap_emitter, mock_uow, mock_envelope):
        """Persist uses correct SQL structure."""
        gap = make_gap_candidate("gap_001", "AMBIGUOUS_ENTITY", "entity_001", 0.7)

        await gap_emitter.emit(mock_uow, [gap], mock_envelope)

        # Verify INSERT was called
        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]

        assert "INSERT INTO st_learning_queue" in sql
        assert "ON CONFLICT (id) DO NOTHING" in sql

    @pytest.mark.asyncio
    async def test_no_persist_when_disabled(self, mock_uow, mock_envelope):
        """No DB insert when persist_to_queue is False."""
        config = GapEmitterConfig(persist_to_queue=False)
        emitter = GapEmitterModule(config=config)

        gap = make_gap_candidate("gap_001", "AMBIGUOUS_ENTITY", "entity_001", 0.7)

        await emitter.emit(mock_uow, [gap], mock_envelope)

        # No DB insert, but outbox should still be staged
        assert mock_uow.connection.execute.call_count == 0
        assert mock_uow.stage_outbox.call_count == 1

    @pytest.mark.asyncio
    async def test_no_outbox_when_disabled(self, mock_uow, mock_envelope):
        """No outbox staging when emit_to_outbox is False."""
        config = GapEmitterConfig(emit_to_outbox=False)
        emitter = GapEmitterModule(config=config)

        gap = make_gap_candidate("gap_001", "AMBIGUOUS_ENTITY", "entity_001", 0.7)

        await emitter.emit(mock_uow, [gap], mock_envelope)

        # DB insert, but no outbox staging
        assert mock_uow.connection.execute.call_count == 1
        assert mock_uow.stage_outbox.call_count == 0
