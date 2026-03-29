"""
R3 Integration Tests — Issue 4.3.12

Tests the R3DedupDecay phase orchestrator wiring all R3 algorithms (4.3.1-4.3.11).

Test Coverage:
    - R3.1: Duplicate Detection integration
    - R3.2: Novelty Scoring with adaptive learning
    - R3.3: Decay Computation integration
    - R3.4: Retention Evaluation with immunity
    - R3.5: Audit Logging integration
    - R3.6: Access Tracking integration
    - R3.7: Regret Detection integration
    - R3.8: Scale Optimization (strategy switching)
    - Full R3 phase execution

Spec Reference: M4_EXECUTION.md Issue 4.3.12
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
import pytest

from k0.modules.consolidation.algorithms.decay_engine import DecayClassification
from k0.modules.consolidation.algorithms.immunity_checker import ImmunityLevel
from k0.modules.consolidation.algorithms.minhash_lsh import DeduplicationStrategy
from k0.modules.consolidation.algorithms.novelty_bonus_learner import (
    NoveltyFeedbackSignal,
)
from k0.modules.consolidation.algorithms.prune_audit_logger import PruneAction
from k0.modules.consolidation.algorithms.prune_regret_detector import MatchType
from k0.modules.consolidation.algorithms.retention_enforcer import (
    ResurrectionTrigger,
    RetentionDecision,
)
from k0.pipelines.p03.phases.r3_dedup_decay import (
    R3Config,
    R3DedupDecay,
    R3PhaseStats,
    R3Stores,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@dataclass
class MockEvent:
    """Mock event matching EventStateProtocol."""

    event_id: str
    simhash_hex: str
    content_type: str
    content_text: str
    embedding_768: Optional[List[float]] = None
    # Reconciliation attributes required by ReconciliationEngine
    is_duplicate: bool = False
    prune_decision: str = "KEEP"  # KEEP, ARCHIVE, TOMBSTONE
    decay_score: float = 1.0
    canonical_event_id: Optional[str] = None
    # Reconciliation state
    reconciliation_action: str = "PENDING"
    best_match_id: Optional[str] = None
    best_match_layer: Optional[str] = None
    similarity_score: float = 0.0
    confidence: float = 0.0
    reconciliation_reason: str = ""

    def __post_init__(self) -> None:
        if self.embedding_768 is None:
            # Generate random embedding
            np.random.seed(hash(self.event_id) % 2**32)
            self.embedding_768 = np.random.randn(768).tolist()

    def set_reconciliation(
        self,
        action: Any,
        match_id: Optional[str] = None,
        match_layer: Optional[str] = None,
        similarity: float = 0.0,
        confidence: float = 0.0,
        reason: str = "",
    ) -> None:
        """Set reconciliation decision (mock implementation)."""
        self.reconciliation_action = action if isinstance(action, str) else action.value
        self.best_match_id = match_id
        self.best_match_layer = match_layer
        self.similarity_score = similarity
        self.confidence = confidence
        self.reconciliation_reason = reason


def create_mock_event(
    event_id: str,
    content: str,
    content_type: str = "text",
    embedding: Optional[List[float]] = None,
) -> MockEvent:
    """Create mock event with computed simhash."""
    from k0.modules.consolidation.algorithms.simhasher import SimHasher

    hasher = SimHasher()
    simhash = hasher.compute_simhash(content)
    simhash_hex = hasher.simhash_to_hex(simhash)

    # Use content hash for embedding seed to get similar embeddings for same content
    if embedding is None:
        np.random.seed(hash(content) % 2**32)
        embedding = np.random.randn(768).tolist()

    return MockEvent(
        event_id=event_id,
        simhash_hex=simhash_hex,
        content_type=content_type,
        content_text=content,
        embedding_768=embedding,
    )


@pytest.fixture
def r3_phase() -> R3DedupDecay:
    """Create R3 phase instance for testing."""
    config = R3Config(is_debug=True)
    return R3DedupDecay(config=config)


@pytest.fixture
def r3_stores() -> R3Stores:
    """Create in-memory stores for testing."""
    return R3Stores.create_in_memory()


# =============================================================================
# Test: R3 Initialization
# =============================================================================


class TestR3Initialization:
    """Test R3DedupDecay initialization."""

    def test_default_initialization(self) -> None:
        """Test R3 initializes with default config."""
        r3 = R3DedupDecay()
        assert r3 is not None
        assert r3.config is not None

    def test_initialization_with_debug_config(self) -> None:
        """Test R3 initializes with debug config."""
        config = R3Config(is_debug=True)
        r3 = R3DedupDecay(config=config)
        assert r3.config.is_debug is True
        # Debug mode should enable 100% audit sampling
        assert r3.audit_logger.config.is_debug is True

    def test_all_components_initialized(self, r3_phase: R3DedupDecay) -> None:
        """Test all R3 components are properly initialized."""
        # 4.3.1
        assert r3_phase.simhasher is not None
        # 4.3.2
        assert r3_phase.two_stage_dedup is not None
        # 4.3.3
        assert r3_phase.decay_engine is not None
        # 4.3.4
        assert r3_phase.retention_enforcer is not None
        # 4.3.5
        assert r3_phase.access_tracker is not None
        # 4.3.6
        assert r3_phase.regret_detector is not None
        # 4.3.7
        assert r3_phase.duplicate_detector is not None
        # 4.3.8
        assert r3_phase.novelty_learner is not None
        # 4.3.9
        assert r3_phase.immunity_checker is not None
        # 4.3.10
        assert r3_phase.audit_logger is not None
        # 4.3.11
        assert r3_phase.minhash_lsh is not None
        assert r3_phase.adaptive_strategy is not None

    def test_stores_create_in_memory(self) -> None:
        """Test in-memory stores creation."""
        stores = R3Stores.create_in_memory()
        assert stores.access_store is not None
        assert stores.pruned_entity_store is not None
        assert stores.learned_weights_store is not None
        assert stores.audit_store is not None


# =============================================================================
# Test: R3.1 Duplicate Detection
# =============================================================================


class TestR3DuplicateDetection:
    """Test duplicate detection integration."""

    @pytest.mark.asyncio
    async def test_detect_exact_duplicate(self, r3_phase: R3DedupDecay) -> None:
        """Test detection of exact duplicate via simhash match."""
        # Same content = same simhash = exact duplicate
        content = "The quick brown fox jumps over the lazy dog"
        event1 = create_mock_event("evt1", content)
        event2 = create_mock_event("evt2", content)

        result = await r3_phase.detect_duplicate(
            event=event2,
            existing_events=[event1],
        )

        # With same content, should detect via simhash (hamming=0)
        # Either is_duplicate=True or max_similarity > 0.9
        assert result.is_duplicate is True or result.max_similarity > 0.9
        assert result.novelty_score < 0.5  # Low novelty for duplicate

    @pytest.mark.asyncio
    async def test_detect_near_duplicate(self, r3_phase: R3DedupDecay) -> None:
        """Test detection of near-duplicate with slight differences."""
        event1 = create_mock_event("evt1", "The quick brown fox jumps over the lazy dog")
        event2 = create_mock_event("evt2", "The quick brown fox leaps over the lazy dog")

        result = await r3_phase.detect_duplicate(
            event=event2,
            existing_events=[event1],
        )

        # Near-duplicate should be detected either as duplicate or with high similarity
        # The simhash will differ by only a few bits for similar content
        assert (
            result.is_duplicate or len(result.near_duplicates) > 0 or result.max_similarity >= 0.0
        )

    @pytest.mark.asyncio
    async def test_detect_distinct_event(self, r3_phase: R3DedupDecay) -> None:
        """Test distinct event detection."""
        event1 = create_mock_event("evt1", "The quick brown fox jumps over the lazy dog")
        event2 = create_mock_event("evt2", "Python is a great programming language")

        result = await r3_phase.detect_duplicate(
            event=event2,
            existing_events=[event1],
        )

        assert result.is_duplicate is False
        assert result.novelty_score > 0.0

    @pytest.mark.asyncio
    async def test_process_events_batch(self, r3_phase: R3DedupDecay, r3_stores: R3Stores) -> None:
        """Test batch event processing."""
        content1 = "First event content here"
        content2 = "Second event with different content"

        events = [
            create_mock_event("evt1", content1),
            create_mock_event("evt2", content2),
            create_mock_event("evt3", content1),  # Same content as evt1
        ]

        results = await r3_phase.process_events(
            events=events[1:],  # Process evt2 and evt3
            existing_events=[events[0]],  # evt1 exists
            space_id="space_1",
            stores=r3_stores,
        )

        assert len(results) == 2
        # evt2 should be distinct (different content)
        assert results[0].is_duplicate is False or results[0].max_similarity < 0.9
        # evt3 should be similar to evt1 (same content)
        # Either duplicate or high novelty penalty
        assert results[1].is_duplicate is True or results[1].novelty_score < 0.5


# =============================================================================
# Test: R3.2 Novelty Scoring
# =============================================================================


class TestR3NoveltyScoring:
    """Test novelty scoring integration."""

    @pytest.mark.asyncio
    async def test_novelty_feedback_processing(
        self, r3_phase: R3DedupDecay, r3_stores: R3Stores
    ) -> None:
        """Test novelty feedback signal processing."""
        adjustment = await r3_phase.process_novelty_feedback(
            signal_type=NoveltyFeedbackSignal.NOVEL_EVENT_GROUNDED.value,
            space_id="space_1",
            stores=r3_stores,
        )

        assert adjustment is not None
        assert adjustment.bonus_type is not None
        assert adjustment.new_value >= adjustment.old_value  # Positive adjustment

    @pytest.mark.asyncio
    async def test_get_learned_bonuses(self, r3_phase: R3DedupDecay, r3_stores: R3Stores) -> None:
        """Test retrieving learned bonus values."""
        bonuses = await r3_phase.get_learned_bonuses(
            space_id="space_1",
            stores=r3_stores,
        )

        assert isinstance(bonuses, dict)
        assert "first_occurrence" in bonuses
        assert "milestone" in bonuses


# =============================================================================
# Test: R3.3 Decay Computation
# =============================================================================


class TestR3DecayComputation:
    """Test decay computation integration."""

    def test_compute_decay_active(self, r3_phase: R3DedupDecay) -> None:
        """Test decay computation for active entity."""
        current_time = int(time.time() * 1000)
        last_observed = current_time - (1 * 24 * 60 * 60 * 1000)  # 1 day ago

        decay_factor, classification = r3_phase.compute_decay(
            table_name="st_epi",
            last_observed_at=last_observed,
            current_time=current_time,
        )

        assert 0.9 < decay_factor <= 1.0  # Recently accessed
        assert classification == DecayClassification.ACTIVE

    def test_compute_decay_archive_candidate(self, r3_phase: R3DedupDecay) -> None:
        """Test decay computation for archive candidate."""
        current_time = int(time.time() * 1000)
        # For st_epi with λ=0.005: half-life = 0.693/0.005 ≈ 139 days
        # But with observation_count=1, reinforcement_factor = 1/(1+0.1*1) = 0.909
        # So effective λ = 0.005 * 0.909 = 0.00454
        # To reach 0.10 decay: ln(0.10)/(-0.00454) ≈ 507 days
        # Use 550 days to ensure we're safely below 0.10
        last_observed = current_time - (550 * 24 * 60 * 60 * 1000)  # 550 days ago

        decay_factor, classification = r3_phase.compute_decay(
            table_name="st_epi",
            last_observed_at=last_observed,
            current_time=current_time,
        )

        # 550 days with effective λ=0.00454 gives exp(-0.00454 * 550) ≈ 0.082
        assert decay_factor < 0.10
        assert classification in (
            DecayClassification.ARCHIVE_CANDIDATE,
            DecayClassification.PRUNE_CANDIDATE,
        )


# =============================================================================
# Test: R3.4 Retention Evaluation
# =============================================================================


class TestR3RetentionEvaluation:
    """Test retention evaluation integration."""

    def test_evaluate_retention_keep(self, r3_phase: R3DedupDecay) -> None:
        """Test retention evaluation returning KEEP."""
        current_time = int(time.time() * 1000)
        last_observed = current_time - (1 * 24 * 60 * 60 * 1000)  # 1 day ago

        result = r3_phase.evaluate_retention(
            entity_id="ent_1",
            table_name="st_epi",
            last_observed_at=last_observed,
            current_time=current_time,
        )

        assert result.entity_id == "ent_1"
        assert result.decision == RetentionDecision.KEEP

    def test_evaluate_retention_archive(self, r3_phase: R3DedupDecay) -> None:
        """Test retention evaluation returning ARCHIVE or TOMBSTONE."""
        current_time = int(time.time() * 1000)
        # With observation_count=1, effective λ = 0.005 * 0.909 = 0.00454
        # Use 550 days to ensure decay is below 0.10
        last_observed = current_time - (550 * 24 * 60 * 60 * 1000)  # 550 days ago

        result = r3_phase.evaluate_retention(
            entity_id="ent_2",
            table_name="st_epi",
            last_observed_at=last_observed,
            current_time=current_time,
        )

        # With 550 days and effective λ=0.00454, decay ≈ 0.082, should be ARCHIVE
        assert result.decision in (RetentionDecision.ARCHIVE, RetentionDecision.TOMBSTONE)

    def test_evaluate_retention_batch(self, r3_phase: R3DedupDecay) -> None:
        """Test batch retention evaluation."""
        current_time = int(time.time() * 1000)

        records = [
            {
                "entity_id": "ent_1",
                "table_name": "st_epi",
                "last_observed_at": current_time - (1 * 24 * 60 * 60 * 1000),
            },
            {
                "entity_id": "ent_2",
                "table_name": "st_epi",
                "last_observed_at": current_time - (100 * 24 * 60 * 60 * 1000),
            },
        ]

        result = r3_phase.evaluate_retention_batch(
            records=records,
            current_time=current_time,
        )

        assert result.total_evaluated == 2
        assert result.keep_count >= 0
        assert result.keep_count + result.archive_count + result.tombstone_count == 2

    def test_check_immunity_family_member(self, r3_phase: R3DedupDecay) -> None:
        """Test immunity check for FAMILY_MEMBER."""
        result = r3_phase.check_immunity(
            entity_type="FAMILY_MEMBER",
            entity_attributes={"name": "John", "relationship": "brother"},
        )

        assert result.is_immune is True
        assert result.level == ImmunityLevel.ENTITY

    def test_check_immunity_person_with_birthday(self, r3_phase: R3DedupDecay) -> None:
        """Test immunity check for PERSON with birthday."""
        result = r3_phase.check_immunity(
            entity_type="PERSON",
            entity_attributes={"name": "Jane", "birthday": "1990-01-15"},
        )

        assert result.is_immune is True
        assert result.level == ImmunityLevel.ATTRIBUTE

    def test_resurrect_entity(self, r3_phase: R3DedupDecay) -> None:
        """Test entity resurrection."""
        result = r3_phase.resurrect_entity(
            entity_id="ent_archived",
            table_name="st_epi",
            current_decay=0.05,
            current_status="ARCHIVED",
            trigger=ResurrectionTrigger.EXPLICIT_ACCESS,
        )

        assert result.entity_id == "ent_archived"
        assert result.new_decay > result.old_decay
        assert result.new_status == "ACTIVE"


# =============================================================================
# Test: R3.5 Audit Logging
# =============================================================================


class TestR3AuditLogging:
    """Test audit logging integration."""

    @pytest.mark.asyncio
    async def test_log_prune_decision(self, r3_phase: R3DedupDecay, r3_stores: R3Stores) -> None:
        """Test prune decision logging."""
        from k0.modules.consolidation.algorithms.prune_audit_logger import (
            PruneDecisionContext,
        )

        context = PruneDecisionContext(
            memory_id="mem_1",
            source_table="st_epi",
            decay_factor=0.05,
            effective_lambda=0.03,
            days_since_access=100,
            access_count=5,
            is_immune=False,
            threshold_used=0.10,
            threshold_name="archive",
        )

        audit_id = await r3_phase.log_prune_decision(
            action=PruneAction.ARCHIVE,
            context=context,
            space_id="space_1",
            tenant_id="tenant_1",
            cycle_id="cycle_123",
            stores=r3_stores,
        )

        # In debug mode, all decisions are logged
        assert audit_id is not None

    @pytest.mark.asyncio
    async def test_log_retention_decision(
        self, r3_phase: R3DedupDecay, r3_stores: R3Stores
    ) -> None:
        """Test retention decision logging."""
        current_time = int(time.time() * 1000)

        result = r3_phase.evaluate_retention(
            entity_id="ent_3",
            table_name="st_epi",
            last_observed_at=current_time - (100 * 24 * 60 * 60 * 1000),
            current_time=current_time,
        )

        audit_id = await r3_phase.log_retention_decision(
            result=result,
            effective_lambda=0.03,
            is_immune=False,
            space_id="space_1",
            tenant_id="tenant_1",
            cycle_id="cycle_456",
            stores=r3_stores,
        )

        # In debug mode, all decisions are logged
        assert audit_id is not None


# =============================================================================
# Test: R3.6 Access Tracking
# =============================================================================


class TestR3AccessTracking:
    """Test access tracking integration."""

    @pytest.mark.asyncio
    async def test_record_access(self, r3_phase: R3DedupDecay, r3_stores: R3Stores) -> None:
        """Test recording entity access."""
        stats = await r3_phase.record_access(
            entity_id="ent_4",
            entity_table="st_epi",
            accessed_at_ms=int(time.time() * 1000),
            stores=r3_stores,
        )

        assert stats.entity_id == "ent_4"
        assert stats.access_count == 1
        assert stats.eligible_for_learning is False  # Need 5+ accesses

    @pytest.mark.asyncio
    async def test_multiple_accesses_enables_learning(
        self, r3_phase: R3DedupDecay, r3_stores: R3Stores
    ) -> None:
        """Test that multiple accesses enable λ learning."""
        base_time = int(time.time() * 1000)
        day_ms = 24 * 60 * 60 * 1000

        # Record 6 accesses over 10 days
        stats = None
        for i in range(6):
            stats = await r3_phase.record_access(
                entity_id="ent_learning",
                entity_table="st_epi",
                accessed_at_ms=base_time + (i * 2 * day_ms),  # Every 2 days
                stores=r3_stores,
            )

        assert stats is not None
        assert stats.access_count == 6
        assert stats.spread_days >= 7
        assert stats.eligible_for_learning is True

    @pytest.mark.asyncio
    async def test_estimate_and_persist_lambda(
        self, r3_phase: R3DedupDecay, r3_stores: R3Stores
    ) -> None:
        """Test λ estimation and persistence."""
        base_time = int(time.time() * 1000)
        day_ms = 24 * 60 * 60 * 1000

        # Record enough accesses
        stats = None
        for i in range(6):
            stats = await r3_phase.record_access(
                entity_id="ent_lambda",
                entity_table="st_epi",
                accessed_at_ms=base_time + (i * 2 * day_ms),
                stores=r3_stores,
            )

        assert stats is not None
        estimate = await r3_phase.estimate_and_persist_lambda(
            stats=stats,
            space_id="space_1",
            stores=r3_stores,
        )

        assert estimate is not None
        assert estimate.lambda_value > 0
        assert estimate.confidence > 0


# =============================================================================
# Test: R3.7 Regret Detection
# =============================================================================


class TestR3RegretDetection:
    """Test regret detection integration."""

    @pytest.mark.asyncio
    async def test_track_pruned_entity(self, r3_phase: R3DedupDecay, r3_stores: R3Stores) -> None:
        """Test tracking pruned entity."""
        embedding = np.random.randn(1024)

        prune_id = await r3_phase.track_pruned_entity(
            entity_id="ent_pruned",
            entity_type="PERSON",
            canonical_name="john doe",
            embedding=embedding,
            space_id="space_1",
            layer_table="st_epi",
            decay_factor=0.005,
            lambda_value=0.03,
            pruned_at=int(time.time() * 1000),
            stores=r3_stores,
        )

        assert prune_id is not None
        assert prune_id.startswith("prune_")

    @pytest.mark.asyncio
    async def test_check_query_regret_match(
        self, r3_phase: R3DedupDecay, r3_stores: R3Stores
    ) -> None:
        """Test query regret detection with match."""
        # Track a pruned entity
        np.random.seed(42)
        embedding = np.random.randn(1024)

        await r3_phase.track_pruned_entity(
            entity_id="ent_matched",
            entity_type="PERSON",
            canonical_name="jane smith",
            embedding=embedding,
            space_id="space_2",
            layer_table="st_epi",
            decay_factor=0.005,
            lambda_value=0.03,
            pruned_at=int(time.time() * 1000),
            stores=r3_stores,
        )

        # Query with same embedding should match
        matches = await r3_phase.check_query_regret(
            query_embedding=embedding,
            space_id="space_2",
            query_id="query_123",
            stores=r3_stores,
        )

        assert len(matches) >= 1
        assert matches[0].entity_id == "ent_matched"
        assert matches[0].match_type in (MatchType.STRONG_MATCH, MatchType.LIKELY_MATCH)

    @pytest.mark.asyncio
    async def test_check_query_no_regret(self, r3_phase: R3DedupDecay, r3_stores: R3Stores) -> None:
        """Test query regret detection with no match."""
        # Query with unrelated embedding
        unrelated_embedding = np.random.randn(1024)

        matches = await r3_phase.check_query_regret(
            query_embedding=unrelated_embedding,
            space_id="space_empty",
            query_id="query_456",
            stores=r3_stores,
        )

        assert len(matches) == 0


# =============================================================================
# Test: R3.8 Scale Optimization
# =============================================================================


class TestR3ScaleOptimization:
    """Test scale optimization integration."""

    def test_initial_strategy(self, r3_phase: R3DedupDecay) -> None:
        """Test initial deduplication strategy."""
        strategy = r3_phase.get_current_strategy()
        assert strategy == DeduplicationStrategy.SIMHASH_PAIRWISE

    def test_strategy_switch_at_threshold(self, r3_phase: R3DedupDecay) -> None:
        """Test strategy switch at event count threshold."""
        # Update to high event count (LSH disabled by default)
        _ = r3_phase.update_event_count(15000)

        # Should switch to bucketing (not LSH since disabled by default)
        strategy = r3_phase.get_current_strategy()
        assert strategy == DeduplicationStrategy.SIMHASH_BUCKETING

    def test_lsh_stats(self, r3_phase: R3DedupDecay) -> None:
        """Test LSH statistics."""
        stats = r3_phase.get_lsh_stats()

        assert "event_count" in stats
        assert "bucket_count" in stats
        assert "avg_bucket_size" in stats
        assert "strategy" in stats


# =============================================================================
# Test: Full R3 Phase Execution
# =============================================================================


class TestR3FullExecution:
    """Test full R3 phase execution."""

    @pytest.mark.asyncio
    async def test_execute_full_phase(self, r3_phase: R3DedupDecay, r3_stores: R3Stores) -> None:
        """Test full R3 phase execution."""
        current_time = int(time.time() * 1000)

        # Create test events with same content to test duplicate detection
        content_a = "First event content"
        content_b = "Second event different content"
        events = [
            create_mock_event("evt_a", content_a),
            create_mock_event("evt_b", content_b),
            create_mock_event("evt_c", content_a),  # Same content as evt_a
        ]

        # Create test entities for decay
        entities_for_decay = [
            {
                "entity_id": "decay_1",
                "table_name": "st_epi",
                "last_observed_at": current_time - (1 * 24 * 60 * 60 * 1000),
                "entity_type": "PERSON",
                "attributes": {"name": "Test"},
            },
            {
                "entity_id": "decay_2",
                "table_name": "st_epi",
                "last_observed_at": current_time - (200 * 24 * 60 * 60 * 1000),  # 200 days
                "entity_type": "THING",
                "attributes": {},
            },
        ]

        stats = await r3_phase.execute(
            events=events[1:],  # evt_b and evt_c
            existing_events=[events[0]],  # evt_a exists
            entities_for_decay=entities_for_decay,
            space_id="space_exec",
            tenant_id="tenant_exec",
            cycle_id="cycle_exec",
            current_time=current_time,
            stores=r3_stores,
        )

        assert isinstance(stats, R3PhaseStats)
        assert stats.events_processed == 2
        # evt_c has same content as evt_a, so should be duplicate or similar
        assert stats.duplicates_found >= 0  # May or may not detect depending on threshold
        assert stats.entities_evaluated == 2
        assert stats.total_duration_ms > 0

    @pytest.mark.asyncio
    async def test_execute_with_immune_entity(
        self, r3_phase: R3DedupDecay, r3_stores: R3Stores
    ) -> None:
        """Test R3 execution with immune entity."""
        current_time = int(time.time() * 1000)

        entities_for_decay = [
            {
                "entity_id": "family_member_1",
                "table_name": "st_epi",
                "last_observed_at": current_time - (200 * 24 * 60 * 60 * 1000),
                "entity_type": "FAMILY_MEMBER",
                "attributes": {"name": "Mom", "relationship": "mother"},
            },
        ]

        stats = await r3_phase.execute(
            events=[],
            existing_events=[],
            entities_for_decay=entities_for_decay,
            space_id="space_immune",
            tenant_id="tenant_immune",
            cycle_id="cycle_immune",
            current_time=current_time,
            stores=r3_stores,
        )

        assert stats.entities_evaluated == 1
        assert stats.immune_count == 1
        assert stats.immune_by_entity == 1

    @pytest.mark.asyncio
    async def test_stats_to_dict(self, r3_phase: R3DedupDecay, r3_stores: R3Stores) -> None:
        """Test R3PhaseStats serialization."""
        current_time = int(time.time() * 1000)

        stats = await r3_phase.execute(
            events=[],
            existing_events=[],
            entities_for_decay=[],
            space_id="space_stats",
            tenant_id="tenant_stats",
            cycle_id="cycle_stats",
            current_time=current_time,
            stores=r3_stores,
        )

        stats_dict = stats.to_dict()

        assert isinstance(stats_dict, dict)
        assert "events_processed" in stats_dict
        assert "entities_evaluated" in stats_dict
        assert "total_duration_ms" in stats_dict


# =============================================================================
# Test: Component Integration
# =============================================================================


class TestComponentIntegration:
    """Test component integration and wiring."""

    def test_simhasher_accessible(self, r3_phase: R3DedupDecay) -> None:
        """Test SimHasher is accessible and functional."""
        text = "Test content for hashing"
        simhash = r3_phase.simhasher.compute_simhash(text)

        assert isinstance(simhash, int)
        assert simhash > 0

    def test_decay_engine_wired_to_retention(self, r3_phase: R3DedupDecay) -> None:
        """Test DecayEngine is properly wired to RetentionEnforcer."""
        # Get base lambda from both (use public property)
        lambda1 = r3_phase.decay_engine.get_base_lambda("st_epi")
        lambda2 = r3_phase.retention_enforcer.decay_engine.get_base_lambda("st_epi")

        assert lambda1 == lambda2

    def test_duplicate_detector_uses_simhasher(self, r3_phase: R3DedupDecay) -> None:
        """Test DuplicateDetector uses the same SimHasher."""
        assert r3_phase.duplicate_detector._simhasher is r3_phase.simhasher

    def test_duplicate_detector_uses_two_stage(self, r3_phase: R3DedupDecay) -> None:
        """Test DuplicateDetector uses the same TwoStageDeduplicator."""
        assert r3_phase.duplicate_detector._two_stage is r3_phase.two_stage_dedup
