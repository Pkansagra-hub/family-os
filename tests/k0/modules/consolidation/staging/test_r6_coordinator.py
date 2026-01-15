"""
Tests for R6Coordinator — Issue 5.1.11

Tests R6 phase orchestration of all sub-components.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from unittest.mock import Mock

from k0.modules.consolidation.staging.dedup_metadata import DuplicationResult
from k0.modules.consolidation.staging.r6_coordinator import (
    R6Coordinator,
    R6CoordinatorConfig,
    R6CoordinatorResult,
    create_r6_coordinator,
)
from k0.pipelines.p03.event_state import P03EventState, ReconciliationAction
from k0.pipelines.p03.phase_outputs import GapCandidate
from k0.pipelines.p03.staged_writes import (
    LAYER_ST_EPI,
    StagedOutboxEvent,
    StagedWrite,
    WriteOperation,
)

# =============================================================================
# CONSTANTS
# =============================================================================

# Valid 26-character ULID for testing (Crockford base32)
TEST_ULID = "01HXYZ123456789ABCDEFGHJKM"
TEST_ULID_2 = "01HXYZ123456789ABCDEFGHJKN"

# =============================================================================
# FIXTURES
# =============================================================================


def make_event_state(
    event_id: str = "event_001",
    action: ReconciliationAction = ReconciliationAction.CREATE,
    cluster_id: str = "cluster_001",
) -> P03EventState:
    """Create a P03EventState with specified action."""
    state = P03EventState(event_id=event_id)
    state.reconciliation_action = action
    state.cluster_id = cluster_id
    state.best_match_id = None
    state.best_match_layer = None
    state.similarity_score = 0.0
    state.confidence = 1.0
    state.reconciliation_reason = "test"
    state.version_conflict = False
    return state


def make_staged_write(
    layer: str = LAYER_ST_EPI,
    record_id: str = "rec_001",
    write_id: str = "write_001",
) -> StagedWrite:
    """Create a StagedWrite with defaults."""
    return StagedWrite(
        write_id=write_id,
        layer=layer,
        operation=WriteOperation.INSERT,
        record_id=record_id,
        record_data={},
        idempotency_key=f"p03:write:cycle:{layer}:{record_id}",
        source_phase="R6",
        expected_version=0,
        source_event_ids=[],
    )


def make_gap_candidate(event_id: str = "event_001") -> GapCandidate:
    """Create a GapCandidate for testing."""
    return GapCandidate(
        gap_id=f"gap_{event_id}",
        gap_type="AMBIGUITY",
        related_entity_id=event_id,
        entropy_score=0.5,
        priority="MEDIUM",
    )


@dataclass
class MockPhaseOutputs:
    """Mock phase outputs for testing."""

    clusters: Optional[Dict] = None
    routines: Optional[Dict] = None
    social_entities: Optional[Dict] = None
    intentions: Optional[Dict] = None
    entities: Optional[Dict] = None
    entity_updates: Optional[Dict] = None
    edges: Optional[Dict] = None
    edge_updates: Optional[Dict] = None
    causal_edges: Optional[Dict] = None


@dataclass
class MockOutboxAssemblyResult:
    """Mock outbox assembly result."""

    events: List[StagedOutboxEvent] = field(default_factory=list)


# =============================================================================
# COORDINATOR CONFIG TESTS
# =============================================================================


class TestR6CoordinatorConfig:
    """Tests for R6CoordinatorConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = R6CoordinatorConfig()

        assert config.dry_run is False
        assert config.validate_manifest is True
        assert config.emit_metrics is True

    def test_custom_values(self):
        """Test custom configuration values."""
        config = R6CoordinatorConfig(
            dry_run=True,
            validate_manifest=False,
            emit_metrics=False,
        )

        assert config.dry_run is True
        assert config.validate_manifest is False
        assert config.emit_metrics is False


# =============================================================================
# COORDINATOR RESULT TESTS
# =============================================================================


class TestR6CoordinatorResult:
    """Tests for R6CoordinatorResult dataclass."""

    def test_default_success(self):
        """Test default result is success."""
        result = R6CoordinatorResult()

        assert result.success is True
        assert result.r6_output is None
        assert result.validation_result is None
        assert result.error is None
        assert result.phase_duration_ms == 0
        assert result.step_durations_ms == {}

    def test_with_r6_output(self):
        """Test result with R6Output can be stored."""
        # Create minimal R6Output using R6Coordinator
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        exec_result = coordinator.execute(
            event_states={},
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids=set(),
        )

        result = R6CoordinatorResult(
            success=True,
            r6_output=exec_result.r6_output,
            phase_duration_ms=100,
        )

        assert result.r6_output is not None

    def test_failure_with_error(self):
        """Test failure result with error message."""
        result = R6CoordinatorResult(
            success=False,
            error="Test error",
        )

        assert result.success is False
        assert result.error == "Test error"


# =============================================================================
# COORDINATOR FACTORY TESTS
# =============================================================================


class TestR6CoordinatorCreate:
    """Tests for R6Coordinator.create() factory method."""

    def test_create_with_defaults(self):
        """Test creating coordinator with default settings."""
        coordinator = R6Coordinator.create(
            cycle_ulid=TEST_ULID,
        )

        assert coordinator is not None
        assert coordinator.status_marker is not None
        assert coordinator.dedup_populator is not None
        assert coordinator.recon_recorder is not None
        assert coordinator.idempotency_gen is not None
        assert coordinator.truth_assembler is not None
        assert coordinator.kg_assembler is not None
        assert coordinator.outbox_assembler is not None
        assert coordinator.validator is not None
        assert coordinator.summary_gen is not None

    def test_create_with_tenant_and_space(self):
        """Test creating coordinator with tenant/space IDs."""
        coordinator = R6Coordinator.create(
            cycle_ulid=TEST_ULID,
            tenant_id="tenant_001",
            space_id="space_001",
        )

        assert coordinator.outbox_assembler is not None

    def test_create_with_existing_entity_ids(self):
        """Test creating coordinator with existing entity IDs."""
        existing_ids = {"entity_1", "entity_2"}
        coordinator = R6Coordinator.create(
            cycle_ulid=TEST_ULID,
            existing_entity_ids=existing_ids,
        )

        assert coordinator.validator is not None

    def test_create_with_config(self):
        """Test creating coordinator with custom config."""
        config = R6CoordinatorConfig(dry_run=True)
        coordinator = R6Coordinator.create(
            cycle_ulid=TEST_ULID,
            config=config,
        )

        assert coordinator.config.dry_run is True


class TestCreateR6Coordinator:
    """Tests for create_r6_coordinator utility function."""

    def test_create_basic(self):
        """Test basic coordinator creation."""
        coordinator = create_r6_coordinator(cycle_ulid=TEST_ULID)

        assert coordinator is not None
        assert coordinator.config.dry_run is False

    def test_create_with_dry_run(self):
        """Test coordinator creation with dry_run."""
        coordinator = create_r6_coordinator(
            cycle_ulid=TEST_ULID,
            dry_run=True,
        )

        assert coordinator.config.dry_run is True

    def test_create_with_all_params(self):
        """Test coordinator creation with all parameters."""
        coordinator = create_r6_coordinator(
            cycle_ulid=TEST_ULID,
            tenant_id="tenant_001",
            space_id="space_001",
            existing_entity_ids={"entity_1"},
            dry_run=True,
        )

        assert coordinator is not None


# =============================================================================
# COORDINATOR EXECUTE TESTS
# =============================================================================


class TestR6CoordinatorExecute:
    """Tests for R6Coordinator.execute() method."""

    def test_execute_empty_batch(self):
        """Test executing with empty event states."""
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

    def test_execute_single_event(self):
        """Test executing with single event."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        event_id = "event_001"
        states = {event_id: make_event_state(event_id)}

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={event_id},
        )

        assert result.success is True
        assert result.r6_output is not None
        assert len(result.r6_output.staged_event_updates) == 1
        assert result.r6_output.reconciliation_summary.total_events == 1

    def test_execute_multiple_events(self):
        """Test executing with multiple events."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        states = {
            "e1": make_event_state("e1", ReconciliationAction.CREATE),
            "e2": make_event_state("e2", ReconciliationAction.REINFORCE),
            "e3": make_event_state("e3", ReconciliationAction.SKIP),
        }

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e1", "e2", "e3"},
        )

        assert result.success is True
        assert result.r6_output is not None
        assert len(result.r6_output.staged_event_updates) == 3

    def test_execute_records_step_durations(self):
        """Test step durations are recorded."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        states = {"e1": make_event_state("e1")}

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e1"},
        )

        assert "build_event_updates" in result.step_durations_ms
        assert "assemble_truth_writes" in result.step_durations_ms
        assert "assemble_kg_writes" in result.step_durations_ms
        assert "generate_summary" in result.step_durations_ms
        assert "assemble_outbox" in result.step_durations_ms
        assert "build_r6_output" in result.step_durations_ms

    def test_execute_records_phase_duration(self):
        """Test phase duration is recorded."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        states = {"e1": make_event_state("e1")}

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e1"},
        )

        assert result.phase_duration_ms >= 0

    def test_execute_with_gaps(self):
        """Test executing with gap candidates."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        states = {"e1": make_event_state("e1")}
        gaps = [make_gap_candidate("e1")]

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=gaps,
            batch_event_ids={"e1"},
        )

        assert result.success is True
        assert result.r6_output is not None
        assert result.r6_output.reconciliation_summary.gap_count == 1

    def test_execute_with_dedup_results(self):
        """Test executing with dedup results."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        states = {"e1": make_event_state("e1")}
        dedup_result = DuplicationResult(
            event_id="e1",
            is_duplicate=False,
            novelty_score=0.8,
            near_duplicates=[],
        )

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e1"},
            dedup_results={"e1": dedup_result},
        )

        assert result.success is True
        assert result.r6_output is not None
        # Check novelty score was applied
        update = result.r6_output.staged_event_updates[0]
        assert update.novelty_score == 0.8


class TestR6CoordinatorValidation:
    """Tests for R6Coordinator manifest validation."""

    def test_validation_enabled_by_default(self):
        """Test manifest validation is enabled by default."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)

        assert coordinator.config.validate_manifest is True

    def test_validation_passes_for_valid_manifest(self):
        """Test validation passes for valid manifest."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        states = {"e1": make_event_state("e1")}

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e1"},
        )

        assert result.success is True
        assert result.validation_result is not None
        assert result.validation_result.is_valid is True

    def test_validation_skipped_when_disabled(self):
        """Test validation is skipped when disabled."""
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
        assert "validate_manifest" not in result.step_durations_ms


class TestR6CoordinatorBuildEventUpdates:
    """Tests for R6Coordinator._build_event_updates()."""

    def test_builds_update_for_each_event(self):
        """Test builds update for each event."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        states = {
            "e1": make_event_state("e1", ReconciliationAction.CREATE),
            "e2": make_event_state("e2", ReconciliationAction.SKIP),
        }

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e1", "e2"},
        )

        assert result.r6_output is not None
        updates = result.r6_output.staged_event_updates
        assert len(updates) == 2

        # Find updates by event_id
        update_map = {u.event_id: u for u in updates}
        assert "e1" in update_map
        assert "e2" in update_map

    def test_update_includes_reconciliation_action(self):
        """Test update includes reconciliation action."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        states = {"e1": make_event_state("e1", ReconciliationAction.PRUNE)}

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e1"},
        )

        assert result.r6_output is not None
        update = result.r6_output.staged_event_updates[0]
        assert update.reconciliation_action == "PRUNE"

    def test_update_includes_idempotency_key(self):
        """Test update includes idempotency key."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        states = {"e1": make_event_state("e1")}

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e1"},
        )

        assert result.r6_output is not None
        update = result.r6_output.staged_event_updates[0]
        assert update.idempotency_key is not None
        assert "e1" in update.idempotency_key


class TestR6CoordinatorBatchId:
    """Tests for R6Coordinator._compute_batch_id()."""

    def test_batch_id_is_deterministic(self):
        """Test batch ID is deterministic for same event IDs."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        states = {"e1": make_event_state("e1")}

        result1 = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e1", "e2", "e3"},
        )

        result2 = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e3", "e1", "e2"},  # Different order
        )

        assert result1.r6_output is not None
        assert result2.r6_output is not None
        assert result1.r6_output.batch_id == result2.r6_output.batch_id

    def test_different_events_produce_different_batch_ids(self):
        """Test different event IDs produce different batch IDs."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        states1 = {"e1": make_event_state("e1")}
        states2 = {"e2": make_event_state("e2")}

        result1 = coordinator.execute(
            event_states=states1,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e1"},
        )

        result2 = coordinator.execute(
            event_states=states2,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e2"},
        )

        assert result1.r6_output is not None
        assert result2.r6_output is not None
        assert result1.r6_output.batch_id != result2.r6_output.batch_id


class TestR6CoordinatorErrorHandling:
    """Tests for R6Coordinator error handling."""

    def test_handles_exception_gracefully(self):
        """Test exceptions are handled and returned as error."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)

        # Create a mock that raises an exception
        coordinator.summary_gen.compute_with_writes = Mock(side_effect=ValueError("Test error"))

        result = coordinator.execute(
            event_states={"e1": make_event_state("e1")},
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e1"},
        )

        assert result.success is False
        assert result.error is not None
        assert "R6 execution failed" in result.error
        assert "Test error" in result.error
        assert result.phase_duration_ms >= 0


# =============================================================================
# R6 OUTPUT INTEGRATION TESTS
# =============================================================================


class TestR6CoordinatorR6Output:
    """Integration tests for R6Output generation."""

    def test_r6_output_has_cycle_ulid(self):
        """Test R6Output has correct cycle_ulid."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID_2)
        states = {"e1": make_event_state("e1")}

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e1"},
        )

        assert result.r6_output is not None
        assert result.r6_output.cycle_ulid == TEST_ULID_2

    def test_r6_output_has_idempotency_key(self):
        """Test R6Output has R6 idempotency key."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        states = {"e1": make_event_state("e1")}

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e1"},
        )

        assert result.r6_output is not None
        assert result.r6_output.r6_idempotency_key is not None
        assert "R6" in result.r6_output.r6_idempotency_key

    def test_r6_output_has_created_at_ms(self):
        """Test R6Output has created_at_ms timestamp."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        states = {"e1": make_event_state("e1")}

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e1"},
        )

        assert result.r6_output is not None
        assert result.r6_output.created_at_ms > 0

    def test_r6_output_staged_collections_are_tuples(self):
        """Test staged collections in R6Output are tuples (frozen)."""
        coordinator = R6Coordinator.create(cycle_ulid=TEST_ULID)
        states = {"e1": make_event_state("e1")}

        result = coordinator.execute(
            event_states=states,
            phase_outputs=MockPhaseOutputs(),
            gaps=[],
            batch_event_ids={"e1"},
        )

        assert result.r6_output is not None
        assert isinstance(result.r6_output.staged_event_updates, tuple)
        assert isinstance(result.r6_output.staged_truth_writes, tuple)
        assert isinstance(result.r6_output.staged_kg_writes, tuple)
        assert isinstance(result.r6_output.staged_outbox_events, tuple)
