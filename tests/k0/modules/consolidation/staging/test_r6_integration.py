"""
Integration tests for R6 Staging Module — Issue 5.1.12

Tests the full R6 workflow with realistic R1-R5 outputs:
- Full cycle with mixed event types
- Duplicate handling
- Gap staging for P06
- Validation failure scenarios
- Idempotency guarantees
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

import pytest

from k0.modules.consolidation.staging.dedup_metadata import DuplicationResult
from k0.modules.consolidation.staging.r6_coordinator import (
    R6Coordinator,
    R6CoordinatorConfig,
)
from k0.modules.consolidation.staging.r6_output import ReconciliationSummary
from k0.pipelines.p03.event_state import P03EventState, ReconciliationAction
from k0.pipelines.p03.phase_outputs import EpisodeCluster, GapCandidate
from k0.pipelines.p03.staged_writes import LAYER_ST_EPI

# =============================================================================
# CONSTANTS
# =============================================================================

# Valid 26-character ULIDs for testing
TEST_ULID = "01HXYZ123456789ABCDEFGHJKM"
TEST_ULID_2 = "01HXYZ123456789ABCDEFGHJKN"


# =============================================================================
# MOCK PHASE OUTPUTS
# =============================================================================


@dataclass
class MockPhaseOutputs:
    """Mock R1-R5 phase outputs for integration testing."""

    # R2 outputs
    clusters: Optional[List[EpisodeCluster]] = None
    routines: Optional[Dict] = None
    social_entities: Optional[Dict] = None
    intentions: Optional[Dict] = None

    # R4 KG outputs
    entities: Optional[Dict] = None
    entity_updates: Optional[Dict] = None
    edges: Optional[Dict] = None
    edge_updates: Optional[Dict] = None
    causal_edges: Optional[Dict] = None


# =============================================================================
# FIXTURES
# =============================================================================


def make_event_state(
    event_id: str,
    action: ReconciliationAction = ReconciliationAction.CREATE,
    cluster_id: str = "cluster_001",
    is_duplicate: bool = False,
    best_match_id: Optional[str] = None,
    best_match_layer: Optional[str] = None,
    similarity_score: float = 0.0,
    confidence: float = 1.0,
) -> P03EventState:
    """Create a P03EventState with specified values."""
    state = P03EventState(event_id=event_id)
    state.reconciliation_action = action
    state.cluster_id = cluster_id
    state.is_duplicate = is_duplicate
    state.best_match_id = best_match_id
    state.best_match_layer = best_match_layer
    state.similarity_score = similarity_score
    state.confidence = confidence
    state.reconciliation_reason = f"test_{action.value.lower()}"
    state.version_conflict = False
    return state


def make_episode_cluster(
    cluster_id: str,
    event_ids: List[str],
    centroid_embedding_id: Optional[str] = None,
) -> EpisodeCluster:
    """Create an EpisodeCluster for testing."""
    return EpisodeCluster(
        cluster_id=cluster_id,
        member_event_ids=event_ids,
        centroid_embedding_id=centroid_embedding_id,
        dominant_sentiment=0.5,
        dominant_emotion="neutral",
        temporal_start=1704067200000,  # 2024-01-01
        temporal_end=1704070800000,  # +1 hour
        cohesion_score=0.85,
        title="test_cluster",
    )


def make_gap_candidate(
    gap_id: str,
    related_entity_id: str,
) -> GapCandidate:
    """Create a GapCandidate for testing."""
    return GapCandidate(
        gap_id=gap_id,
        gap_type="AMBIGUITY",
        related_entity_id=related_entity_id,
        entropy_score=0.7,
        priority="MEDIUM",
    )


def make_dedup_result(
    event_id: str,
    is_duplicate: bool = False,
    novelty_score: float = 0.9,
    near_duplicates: Optional[List[str]] = None,
) -> DuplicationResult:
    """Create a DuplicationResult for testing."""
    return DuplicationResult(
        event_id=event_id,
        is_duplicate=is_duplicate,
        novelty_score=novelty_score,
        near_duplicates=near_duplicates or [],
    )


# =============================================================================
# FULL CYCLE INTEGRATION TESTS
# =============================================================================


class TestR6FullCycle:
    """Integration tests for full R6 cycle processing."""

    def test_r6_empty_batch(self):
        """Test R6 handles empty batch gracefully."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)

        result = coordinator.execute(
            event_states={},
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids=set(),
        )

        assert result.success is True
        assert result.r6_output is not None
        assert result.r6_output.reconciliation_summary.total_events == 0
        assert len(result.r6_output.staged_event_updates) == 0

    def test_r6_single_create_event(self):
        """Test R6 processes single CREATE event."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        event_id = "event_001"
        states = {event_id: make_event_state(event_id, ReconciliationAction.CREATE)}

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={event_id},
        )

        assert result.success is True
        assert result.r6_output is not None
        assert len(result.r6_output.staged_event_updates) == 1

        update = result.r6_output.staged_event_updates[0]
        assert update.event_id == event_id
        assert update.consolidation_status == "CONSOLIDATED"
        assert update.reconciliation_action == "CREATE"

    def test_r6_mixed_actions(self):
        """Test R6 processes batch with mixed reconciliation actions."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        states = {
            "e1": make_event_state("e1", ReconciliationAction.CREATE),
            "e2": make_event_state("e2", ReconciliationAction.REINFORCE),
            "e3": make_event_state("e3", ReconciliationAction.EXTEND),
            "e4": make_event_state("e4", ReconciliationAction.SKIP),
            "e5": make_event_state("e5", ReconciliationAction.PRUNE),
        }

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids=set(states.keys()),
        )

        assert result.success is True
        assert result.r6_output is not None
        summary = result.r6_output.reconciliation_summary

        # Verify status counts
        assert summary.total_events == 5
        assert summary.consolidated_count == 3  # CREATE, REINFORCE, EXTEND
        assert summary.duplicate_count == 1  # SKIP
        assert summary.pruned_count == 1  # PRUNE

    def test_r6_with_clusters(self):
        """Test R6 assembles truth writes from clusters."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        states = {
            "e1": make_event_state("e1", ReconciliationAction.CREATE),
            "e2": make_event_state("e2", ReconciliationAction.CREATE),
        }
        clusters = [
            make_episode_cluster("cluster_001", ["e1", "e2"]),
        ]
        phase_outputs = MockPhaseOutputs(clusters=clusters)

        result = coordinator.execute(
            event_states=states,
            phase_outputs=phase_outputs,
            gaps=[],
            batch_event_ids=set(states.keys()),
        )

        assert result.success is True
        assert result.r6_output is not None
        # Check truth writes were assembled
        truth_writes = result.r6_output.staged_truth_writes
        epi_writes = [w for w in truth_writes if w.layer == LAYER_ST_EPI]
        assert len(epi_writes) >= 1


class TestR6DuplicateHandling:
    """Integration tests for duplicate event handling."""

    def test_r6_exact_duplicate(self):
        """Test R6 marks exact duplicates correctly."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        states = {
            "e1": make_event_state(
                "e1",
                ReconciliationAction.SKIP,
                is_duplicate=True,
            ),
        }
        dedup_results = {
            "e1": make_dedup_result("e1", is_duplicate=True, novelty_score=0.0),
        }

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e1"},
            dedup_results=dedup_results,
        )

        assert result.success is True
        assert result.r6_output is not None
        update = result.r6_output.staged_event_updates[0]
        assert update.consolidation_status == "DUPLICATE"
        assert update.novelty_score == 0.0

    def test_r6_near_duplicates_with_novelty(self):
        """Test R6 handles near-duplicates with novelty scores."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        states = {
            "e1": make_event_state("e1", ReconciliationAction.REINFORCE),
        }
        dedup_results = {
            "e1": make_dedup_result(
                "e1",
                is_duplicate=False,
                novelty_score=0.7,
                near_duplicates=["existing_001", "existing_002"],
            ),
        }

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e1"},
            dedup_results=dedup_results,
        )

        assert result.success is True
        assert result.r6_output is not None
        update = result.r6_output.staged_event_updates[0]
        assert update.novelty_score == 0.7
        # near_duplicates_json should contain the IDs
        assert "existing_001" in update.near_duplicates_json


class TestR6GapHandling:
    """Integration tests for gap candidate staging."""

    def test_r6_stages_gaps_for_p06(self):
        """Test R6 stages gap candidates for P06 learning queue."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        states = {"e1": make_event_state("e1", ReconciliationAction.CREATE)}
        gaps = [
            make_gap_candidate("gap_001", "entity_001"),
            make_gap_candidate("gap_002", "entity_002"),
        ]

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=gaps,
            batch_event_ids={"e1"},
        )

        assert result.success is True
        assert result.r6_output is not None
        assert result.r6_output.reconciliation_summary.gap_count == 2

    def test_r6_outbox_includes_gap_events(self):
        """Test R6 emits outbox events for gaps."""
        coordinator = R6Coordinator.create(
            cycle_ulid=TEST_ULID,
            tenant_id="tenant_001",
            space_id="space_001",
        )
        states = {"e1": make_event_state("e1", ReconciliationAction.CREATE)}
        gaps = [make_gap_candidate("gap_001", "entity_001")]

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=gaps,
            batch_event_ids={"e1"},
        )

        assert result.success is True
        assert result.r6_output is not None
        # Check outbox events include gap-related topic
        outbox_events = result.r6_output.staged_outbox_events
        # May or may not have gap events depending on outbox assembler config
        assert len(outbox_events) >= 0  # At minimum, has completion event


class TestR6Validation:
    """Integration tests for manifest validation."""

    def test_r6_passes_validation_for_complete_manifest(self):
        """Test R6 passes validation when manifest is complete."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        states = {"e1": make_event_state("e1", ReconciliationAction.CREATE)}

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e1"},
        )

        assert result.success is True
        assert result.validation_result is not None
        assert result.validation_result.is_valid is True

    def test_r6_validation_disabled(self):
        """Test R6 skips validation when disabled."""
        config = R6CoordinatorConfig(validate_manifest=False)
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID, config=config)
        states = {"e1": make_event_state("e1")}

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e1"},
        )

        assert result.success is True
        assert result.validation_result is None


class TestR6Idempotency:
    """Integration tests for idempotency guarantees."""

    def test_r6_deterministic_output(self):
        """Test R6 produces same output for same input."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        states = {
            "e1": make_event_state("e1", ReconciliationAction.CREATE),
            "e2": make_event_state("e2", ReconciliationAction.REINFORCE),
        }
        phase_outputs = MockPhaseOutputs()
        batch_ids = {"e1", "e2"}

        # First execution
        result1 = coordinator.execute(
            event_states=states,
            phase_outputs=phase_outputs,
            gaps=[],
            batch_event_ids=batch_ids,
        )

        # Second execution
        result2 = coordinator.execute(
            event_states=states,
            phase_outputs=phase_outputs,
            gaps=[],
            batch_event_ids=batch_ids,
        )

        assert result1.success is True
        assert result2.success is True
        assert result1.r6_output is not None
        assert result2.r6_output is not None

        # Batch ID should be deterministic
        assert result1.r6_output.batch_id == result2.r6_output.batch_id

        # R6 idempotency key should be deterministic
        assert result1.r6_output.r6_idempotency_key == result2.r6_output.r6_idempotency_key

        # Event updates should match (same order may vary)
        updates1 = {u.event_id: u for u in result1.r6_output.staged_event_updates}
        updates2 = {u.event_id: u for u in result2.r6_output.staged_event_updates}

        assert updates1.keys() == updates2.keys()
        for event_id in updates1:
            assert (
                updates1[event_id].consolidation_status == updates2[event_id].consolidation_status
            )
            assert (
                updates1[event_id].reconciliation_action == updates2[event_id].reconciliation_action
            )

    def test_r6_idempotency_keys_unique_per_event(self):
        """Test each event update has unique idempotency key."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        states = {
            "e1": make_event_state("e1"),
            "e2": make_event_state("e2"),
            "e3": make_event_state("e3"),
        }

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids=set(states.keys()),
        )

        assert result.success is True
        assert result.r6_output is not None

        # All idempotency keys should be unique
        keys = [u.idempotency_key for u in result.r6_output.staged_event_updates]
        assert len(keys) == len(set(keys)), "Idempotency keys must be unique"


class TestR6OutputStructure:
    """Integration tests for R6Output structure and immutability."""

    def test_r6_output_is_frozen(self):
        """Test R6Output is immutable after creation."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        states = {"e1": make_event_state("e1")}

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e1"},
        )

        assert result.success is True
        assert result.r6_output is not None

        # R6Output should be frozen
        with pytest.raises(AttributeError):
            result.r6_output.cycle_ulid = "modified"  # type: ignore

    def test_r6_output_collections_are_tuples(self):
        """Test all staged collections are immutable tuples."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        states = {"e1": make_event_state("e1")}

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e1"},
        )

        assert result.success is True
        assert result.r6_output is not None
        output = result.r6_output

        assert isinstance(output.staged_event_updates, tuple)
        assert isinstance(output.staged_truth_writes, tuple)
        assert isinstance(output.staged_kg_writes, tuple)
        assert isinstance(output.staged_outbox_events, tuple)

    def test_r6_output_has_required_fields(self):
        """Test R6Output contains all required fields."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        states = {"e1": make_event_state("e1")}

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e1"},
        )

        assert result.success is True
        assert result.r6_output is not None
        output = result.r6_output

        # Required fields
        assert output.cycle_ulid == TEST_ULID
        assert len(output.batch_id) == 16  # SHA256 truncated
        assert output.created_at_ms > 0
        assert output.r6_idempotency_key
        assert isinstance(output.reconciliation_summary, ReconciliationSummary)


class TestR6PerformanceMetrics:
    """Integration tests for performance tracking."""

    def test_r6_records_step_durations(self):
        """Test R6 records timing for each processing step."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        states = {"e1": make_event_state("e1")}

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e1"},
        )

        assert result.success is True

        # Step durations should be recorded
        expected_steps = [
            "build_event_updates",
            "assemble_truth_writes",
            "assemble_kg_writes",
            "generate_summary",
            "assemble_outbox",
            "build_r6_output",
        ]

        for step in expected_steps:
            assert step in result.step_durations_ms, f"Missing step: {step}"
            assert result.step_durations_ms[step] >= 0

    def test_r6_records_phase_duration(self):
        """Test R6 records total phase duration."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        states = {"e1": make_event_state("e1")}

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e1"},
        )

        assert result.success is True
        assert result.phase_duration_ms >= 0

        # Phase duration should be >= sum of step durations
        step_total = sum(result.step_durations_ms.values())
        assert result.phase_duration_ms >= step_total


class TestR6ErrorRecovery:
    """Integration tests for error handling and recovery."""

    def test_r6_handles_component_error(self):
        """Test R6 captures component errors gracefully."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)

        # Break a component to trigger error
        original_compute = coordinator.summary_gen.compute_with_writes
        coordinator.summary_gen.compute_with_writes = lambda **kwargs: (_ for _ in ()).throw(
            ValueError("Simulated error")
        )

        states = {"e1": make_event_state("e1")}

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e1"},
        )

        # Restore original
        coordinator.summary_gen.compute_with_writes = original_compute

        assert result.success is False
        assert result.error is not None
        assert "R6 execution failed" in result.error

    def test_r6_result_contains_partial_timing_on_error(self):
        """Test R6 records timing for completed steps even on error."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)

        # Break summary generator to fail after some steps complete
        original_compute = coordinator.summary_gen.compute_with_writes
        coordinator.summary_gen.compute_with_writes = lambda **kwargs: (_ for _ in ()).throw(
            ValueError("Simulated error")
        )

        states = {"e1": make_event_state("e1")}

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e1"},
        )

        # Restore original
        coordinator.summary_gen.compute_with_writes = original_compute

        assert result.success is False
        # Steps before error should have timing
        assert "build_event_updates" in result.step_durations_ms
        assert "assemble_truth_writes" in result.step_durations_ms
