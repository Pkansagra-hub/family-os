"""
Tests for P03GapEmitter (Issue 3.2.3).

Tests cover:
- Gap persistence to st_learning_queue
- Gap staging to outbox
- Deduplication within time window
- Priority calculation by gap type
- Idempotency via gap_id fingerprint
- Metrics tracking in observability context
"""

from __future__ import annotations

from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.pipelines.p03 import (
    GAP_PRIORITY_MAP,
    GapCandidate,
    GapEmitResult,
    GapType,
    P03BatchEnvelope,
    P03CycleContext,
    P03GapEmitter,
    P03GapEmitterConfig,
)

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def mock_connection() -> MagicMock:
    """Create a mock asyncpg connection."""
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value="INSERT 1")
    conn.fetchrow = AsyncMock(return_value=None)  # No duplicates by default
    return conn


@pytest.fixture
def mock_uow(mock_connection: MagicMock) -> MagicMock:
    """Create a mock UnitOfWork with connection."""
    uow = MagicMock()
    uow.connection = mock_connection
    uow.stage_outbox = MagicMock()
    return uow


@pytest.fixture
def sample_cycle_context() -> P03CycleContext:
    """Create sample cycle context."""
    return P03CycleContext.create(
        tenant_id="tenant-test-001",
        space_id="space-test-001",
        event_ids=["evt-001", "evt-002"],
        trigger_type="MANUAL",
        trigger_reason="Test",
    )


@pytest.fixture
def sample_envelope(sample_cycle_context: P03CycleContext) -> P03BatchEnvelope:
    """Create sample envelope for testing."""
    return P03BatchEnvelope.create(
        context=sample_cycle_context,
        events=[],
    )


@pytest.fixture
def sample_gaps() -> List[GapCandidate]:
    """Create sample gap candidates."""
    return [
        GapCandidate(
            gap_id="gap-001",
            gap_type="AMBIGUOUS_ENTITY",
            related_entity_id="entity-001",
            entropy_score=0.8,
            priority="HIGH",
            context_json="{}",
            candidate_values=["val1", "val2"],
        ),
        GapCandidate(
            gap_id="gap-002",
            gap_type="LOW_CONFIDENCE_EDGE",
            related_entity_id="entity-002",
            entropy_score=0.5,
            priority="MEDIUM",
            context_json="{}",
            candidate_values=[],
        ),
        GapCandidate(
            gap_id="gap-003",
            gap_type="CONTRADICTION",
            related_entity_id="entity-003",
            entropy_score=0.9,
            priority="HIGH",
            context_json="{}",
            candidate_values=["a", "b", "c"],
        ),
    ]


@pytest.fixture
def gap_emitter() -> P03GapEmitter:
    """Create gap emitter with default config."""
    return P03GapEmitter()


# =============================================================================
# GAP TYPE ENUM TESTS
# =============================================================================


class TestGapType:
    """Tests for GapType enum."""

    def test_gap_type_values_match_migration(self) -> None:
        """GapType values should match migration 0037 CHECK constraint."""
        expected = {
            "AMBIGUOUS_ENTITY",
            "LOW_CONFIDENCE_EDGE",
            "MISSING_ATTRIBUTE",
            "CONTRADICTION",
            "CONCEPT_DRIFT",
            "STRUCTURAL_HOLE",
            "STALE_ANCHOR",
        }
        actual = {gt.value for gt in GapType}
        assert actual == expected

    def test_from_string_valid_type(self) -> None:
        """from_string should parse valid gap types."""
        assert GapType.from_string("AMBIGUOUS_ENTITY") == GapType.AMBIGUOUS_ENTITY
        assert GapType.from_string("contradiction") == GapType.CONTRADICTION
        assert GapType.from_string("STALE_ANCHOR") == GapType.STALE_ANCHOR

    def test_from_string_legacy_type(self) -> None:
        """from_string should map legacy gap types."""
        assert GapType.from_string("AMBIGUITY") == GapType.AMBIGUOUS_ENTITY
        assert GapType.from_string("LOW_CONFIDENCE") == GapType.LOW_CONFIDENCE_EDGE
        assert GapType.from_string("MISSING") == GapType.MISSING_ATTRIBUTE
        assert GapType.from_string("SEMANTIC_CONFLICT") == GapType.CONTRADICTION

    def test_from_string_unknown_type(self) -> None:
        """from_string should default to AMBIGUOUS_ENTITY for unknown types."""
        assert GapType.from_string("UNKNOWN_TYPE") == GapType.AMBIGUOUS_ENTITY


# =============================================================================
# GAP PRIORITY TESTS
# =============================================================================


class TestGapPriority:
    """Tests for gap priority calculation."""

    def test_priority_map_covers_all_types(self) -> None:
        """GAP_PRIORITY_MAP should have entries for all GapTypes."""
        for gap_type in GapType:
            assert gap_type in GAP_PRIORITY_MAP

    def test_contradiction_highest_priority(self) -> None:
        """CONTRADICTION should have highest priority (100)."""
        assert GAP_PRIORITY_MAP[GapType.CONTRADICTION] == 100

    def test_missing_attribute_lowest_priority(self) -> None:
        """MISSING_ATTRIBUTE should have lowest priority (30)."""
        assert GAP_PRIORITY_MAP[GapType.MISSING_ATTRIBUTE] == 30

    def test_calculate_priority(self, gap_emitter: P03GapEmitter) -> None:
        """_calculate_priority should return correct scores."""
        assert gap_emitter._calculate_priority(GapType.CONTRADICTION) == 100
        assert gap_emitter._calculate_priority(GapType.AMBIGUOUS_ENTITY) == 80
        assert gap_emitter._calculate_priority(GapType.STRUCTURAL_HOLE) == 70


# =============================================================================
# GAP EMITTER CONFIGURATION TESTS
# =============================================================================


class TestGapEmitterConfig:
    """Tests for P03GapEmitterConfig."""

    def test_default_config(self) -> None:
        """Default config should have expected values."""
        config = P03GapEmitterConfig()
        assert config.topic == "p03.gap.detected.v1"
        assert config.deduplicate is True
        assert config.dedup_window_ms == 3600000  # 1 hour
        assert config.default_expires_ms == 604800000  # 7 days
        assert config.max_attempts == 3

    def test_custom_config(self) -> None:
        """Custom config should override defaults."""
        config = P03GapEmitterConfig(
            topic="custom.topic",
            deduplicate=False,
            dedup_window_ms=1000,
        )
        assert config.topic == "custom.topic"
        assert config.deduplicate is False
        assert config.dedup_window_ms == 1000


# =============================================================================
# GAP ID GENERATION TESTS
# =============================================================================


class TestGapIdGeneration:
    """Tests for gap ID generation."""

    def test_generate_gap_id(
        self,
        gap_emitter: P03GapEmitter,
        sample_gaps: List[GapCandidate],
    ) -> None:
        """_generate_gap_id should create unique, idempotent IDs."""
        cycle_id = "cycle-001"
        gap = sample_gaps[0]

        gap_id = gap_emitter._generate_gap_id(cycle_id, gap)

        assert gap_id == f"p03:gap:{cycle_id}:{gap.related_entity_id}:{gap.gap_type}"

    def test_gap_id_is_deterministic(
        self,
        gap_emitter: P03GapEmitter,
        sample_gaps: List[GapCandidate],
    ) -> None:
        """Same inputs should produce same gap_id (idempotent)."""
        cycle_id = "cycle-001"
        gap = sample_gaps[0]

        id1 = gap_emitter._generate_gap_id(cycle_id, gap)
        id2 = gap_emitter._generate_gap_id(cycle_id, gap)

        assert id1 == id2


# =============================================================================
# GAP DEDUPLICATION TESTS
# =============================================================================


class TestGapDeduplication:
    """Tests for gap deduplication."""

    @pytest.mark.asyncio
    async def test_is_duplicate_returns_false_when_not_found(
        self,
        gap_emitter: P03GapEmitter,
        mock_uow: MagicMock,
    ) -> None:
        """_is_duplicate should return False when gap not in DB."""
        mock_uow.connection.fetchrow = AsyncMock(return_value=None)

        result = await gap_emitter._is_duplicate(mock_uow, "gap-id-new")

        assert result is False

    @pytest.mark.asyncio
    async def test_is_duplicate_returns_true_when_found(
        self,
        gap_emitter: P03GapEmitter,
        mock_uow: MagicMock,
    ) -> None:
        """_is_duplicate should return True when gap exists in window."""
        mock_uow.connection.fetchrow = AsyncMock(return_value={"id": "gap-id-exists"})

        result = await gap_emitter._is_duplicate(mock_uow, "gap-id-exists")

        assert result is True

    @pytest.mark.asyncio
    async def test_emit_gaps_skips_duplicates(
        self,
        gap_emitter: P03GapEmitter,
        mock_uow: MagicMock,
        sample_envelope: P03BatchEnvelope,
        sample_gaps: List[GapCandidate],
    ) -> None:
        """emit_gaps should skip duplicate gaps."""
        # First gap is duplicate, rest are new
        mock_uow.connection.fetchrow = AsyncMock(side_effect=[{"id": "dup"}, None, None])

        result = await gap_emitter.emit_gaps(mock_uow, sample_gaps, sample_envelope)

        assert result.total == 3
        assert result.emitted == 2
        assert result.deduplicated == 1

    @pytest.mark.asyncio
    async def test_emit_gaps_no_dedup_when_disabled(
        self,
        mock_uow: MagicMock,
        sample_envelope: P03BatchEnvelope,
        sample_gaps: List[GapCandidate],
    ) -> None:
        """emit_gaps should not deduplicate when config.deduplicate=False."""
        emitter = P03GapEmitter(P03GapEmitterConfig(deduplicate=False))

        result = await emitter.emit_gaps(mock_uow, sample_gaps, sample_envelope)

        assert result.total == 3
        assert result.emitted == 3
        assert result.deduplicated == 0
        # fetchrow should not be called for dedup checks
        mock_uow.connection.fetchrow.assert_not_called()


# =============================================================================
# GAP PERSISTENCE TESTS
# =============================================================================


class TestGapPersistence:
    """Tests for gap persistence to st_learning_queue."""

    @pytest.mark.asyncio
    async def test_persist_to_queue_inserts_gap(
        self,
        gap_emitter: P03GapEmitter,
        mock_uow: MagicMock,
        sample_gaps: List[GapCandidate],
    ) -> None:
        """_persist_to_queue should INSERT into st_learning_queue."""
        gap = sample_gaps[0]

        await gap_emitter._persist_to_queue(
            mock_uow,
            gap,
            GapType.AMBIGUOUS_ENTITY,
            "tenant-001",
            "space-001",
            "cycle-001",
            "gap-id-001",
        )

        mock_uow.connection.execute.assert_called_once()
        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]
        assert "INSERT INTO st_learning_queue" in sql
        assert "ON CONFLICT (id) DO NOTHING" in sql

    @pytest.mark.asyncio
    async def test_persist_includes_all_required_columns(
        self,
        gap_emitter: P03GapEmitter,
        mock_uow: MagicMock,
        sample_gaps: List[GapCandidate],
    ) -> None:
        """_persist_to_queue should set all required columns."""
        gap = sample_gaps[0]

        await gap_emitter._persist_to_queue(
            mock_uow,
            gap,
            GapType.AMBIGUOUS_ENTITY,
            "tenant-001",
            "space-001",
            "cycle-001",
            "gap-id-001",
        )

        call_args = mock_uow.connection.execute.call_args
        sql = call_args[0][0]
        # Check required columns are in INSERT
        assert "tenant_id" in sql
        assert "space_id" in sql
        assert "gap_type" in sql
        assert "entity_id" in sql
        assert "entropy_score" in sql
        assert "status" in sql
        assert "created_at" in sql
        assert "expires_at" in sql


# =============================================================================
# OUTBOX STAGING TESTS
# =============================================================================


class TestOutboxStaging:
    """Tests for gap event staging to outbox."""

    @pytest.mark.asyncio
    async def test_stage_to_outbox_calls_uow(
        self,
        gap_emitter: P03GapEmitter,
        mock_uow: MagicMock,
        sample_gaps: List[GapCandidate],
    ) -> None:
        """_stage_to_outbox should call uow.stage_outbox."""
        gap = sample_gaps[0]

        await gap_emitter._stage_to_outbox(
            mock_uow,
            gap,
            GapType.AMBIGUOUS_ENTITY,
            "tenant-001",
            "space-001",
            "cycle-001",
            "gap-id-001",
        )

        mock_uow.stage_outbox.assert_called_once()

    @pytest.mark.asyncio
    async def test_outbox_entry_has_correct_fields(
        self,
        gap_emitter: P03GapEmitter,
        mock_uow: MagicMock,
        sample_gaps: List[GapCandidate],
    ) -> None:
        """Outbox entry should have correct driver, topic, fingerprint."""
        gap = sample_gaps[0]

        await gap_emitter._stage_to_outbox(
            mock_uow,
            gap,
            GapType.AMBIGUOUS_ENTITY,
            "tenant-001",
            "space-001",
            "cycle-001",
            "gap-id-001",
        )

        entry = mock_uow.stage_outbox.call_args[0][0]
        assert entry.driver == "p03"
        assert entry.op_kind == "p03.gap.detected.v1"
        assert entry.fingerprint == "gap-id-001"
        assert entry.tenant_id == "tenant-001"
        assert entry.space_id == "space-001"

    def test_build_payload_includes_required_fields(
        self,
        gap_emitter: P03GapEmitter,
        sample_gaps: List[GapCandidate],
    ) -> None:
        """_build_payload should include all required event fields."""
        gap = sample_gaps[0]

        payload = gap_emitter._build_payload(
            gap,
            GapType.AMBIGUOUS_ENTITY,
            "tenant-001",
            "space-001",
            "cycle-001",
            "gap-id-001",
        )

        assert payload["gap_id"] == "gap-id-001"
        assert payload["cycle_id"] == "cycle-001"
        assert payload["tenant_id"] == "tenant-001"
        assert payload["space_id"] == "space-001"
        assert payload["gap_type"] == "AMBIGUOUS_ENTITY"
        assert payload["related_entity_id"] == gap.related_entity_id
        assert payload["entropy_score"] == gap.entropy_score
        assert payload["priority"] == 80  # AMBIGUOUS_ENTITY priority
        assert "detected_at" in payload


# =============================================================================
# EMIT GAPS INTEGRATION TESTS
# =============================================================================


class TestEmitGapsIntegration:
    """Integration tests for emit_gaps."""

    @pytest.mark.asyncio
    async def test_emit_gaps_returns_result(
        self,
        gap_emitter: P03GapEmitter,
        mock_uow: MagicMock,
        sample_envelope: P03BatchEnvelope,
        sample_gaps: List[GapCandidate],
    ) -> None:
        """emit_gaps should return GapEmitResult with counts."""
        result = await gap_emitter.emit_gaps(mock_uow, sample_gaps, sample_envelope)

        assert isinstance(result, GapEmitResult)
        assert result.total == 3
        assert result.emitted == 3
        assert result.deduplicated == 0

    @pytest.mark.asyncio
    async def test_emit_gaps_records_by_type(
        self,
        gap_emitter: P03GapEmitter,
        mock_uow: MagicMock,
        sample_envelope: P03BatchEnvelope,
        sample_gaps: List[GapCandidate],
    ) -> None:
        """emit_gaps should track counts by gap type."""
        result = await gap_emitter.emit_gaps(mock_uow, sample_gaps, sample_envelope)

        assert result.by_type["AMBIGUOUS_ENTITY"] == 1
        assert result.by_type["LOW_CONFIDENCE_EDGE"] == 1
        assert result.by_type["CONTRADICTION"] == 1

    @pytest.mark.asyncio
    async def test_emit_gaps_records_metrics(
        self,
        gap_emitter: P03GapEmitter,
        mock_uow: MagicMock,
        sample_envelope: P03BatchEnvelope,
        sample_gaps: List[GapCandidate],
    ) -> None:
        """emit_gaps should record metrics in observability context."""
        await gap_emitter.emit_gaps(mock_uow, sample_gaps, sample_envelope)

        counters = sample_envelope.observability.counters
        assert "p03.r8.gaps.detected" in counters
        assert counters["p03.r8.gaps.detected"] == 3
        # Check per-type metrics
        assert "p03.r8.gaps.emitted.ambiguous_entity" in counters
        assert "p03.r8.gaps.emitted.low_confidence_edge" in counters
        assert "p03.r8.gaps.emitted.contradiction" in counters

    @pytest.mark.asyncio
    async def test_emit_gaps_empty_list(
        self,
        gap_emitter: P03GapEmitter,
        mock_uow: MagicMock,
        sample_envelope: P03BatchEnvelope,
    ) -> None:
        """emit_gaps should handle empty gap list."""
        result = await gap_emitter.emit_gaps(mock_uow, [], sample_envelope)

        assert result.total == 0
        assert result.emitted == 0
        mock_uow.connection.execute.assert_not_called()
        mock_uow.stage_outbox.assert_not_called()

    @pytest.mark.asyncio
    async def test_emit_gaps_persists_and_stages_each(
        self,
        gap_emitter: P03GapEmitter,
        mock_uow: MagicMock,
        sample_envelope: P03BatchEnvelope,
        sample_gaps: List[GapCandidate],
    ) -> None:
        """emit_gaps should persist to queue AND stage to outbox for each gap."""
        await gap_emitter.emit_gaps(mock_uow, sample_gaps, sample_envelope)

        # 3 gaps = 3 INSERT calls
        assert mock_uow.connection.execute.call_count == 3
        # 3 gaps = 3 stage_outbox calls
        assert mock_uow.stage_outbox.call_count == 3
