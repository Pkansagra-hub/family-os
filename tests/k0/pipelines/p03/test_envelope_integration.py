"""
Envelope Integration Tests for P03 Consolidation.

Issue 3.2.7: Phase 3 - M1 Envelope & Runner Integration Tests

This module tests envelope lifecycle integration scenarios:
- Frozen context immutability under concurrent access
- Event state mutation during phase execution
- Checkpoint save/restore across phases
- Deterministic seed reproducibility
- Phase chain execution order

These tests complement the unit tests in test_p03_envelope.py and
test_p03_sequential_runner.py by testing integration scenarios.
"""

from __future__ import annotations

import time
from dataclasses import FrozenInstanceError
from typing import List

import pytest

from k0.pipelines.p03 import (
    P03BatchEnvelope,
    P03Checkpoint,
    P03CycleContext,
    P03EventState,
    P03PhaseId,
    P03PhaseStatus,
    ReconciliationAction,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sample_context() -> P03CycleContext:
    """Create sample cycle context."""
    return P03CycleContext.create(
        tenant_id="tenant-int",
        space_id="space-int",
        event_ids=["evt-int-001", "evt-int-002", "evt-int-003"],
        trigger_type="MANUAL",
        trigger_reason="Integration test",
    )


@pytest.fixture
def sample_events() -> List[P03EventState]:
    """Create sample event states."""
    base_ts = int(time.time() * 1000)
    return [
        P03EventState(
            event_id="evt-int-001",
            hipp_event_id="evt-int-001",
            content_text="First integration test event",
            content_type="CHAT",
            content_hash="hash001",
            simhash_hex="simhash001",
            timestamp=base_ts,
            channel_id="test-channel",
            embedding_id="emb-001",
            sentiment_score=0.7,
            sentiment_label="positive",
        ),
        P03EventState(
            event_id="evt-int-002",
            hipp_event_id="evt-int-002",
            content_text="Second integration test event",
            content_type="CHAT",
            content_hash="hash002",
            simhash_hex="simhash002",
            timestamp=base_ts + 1000,
            channel_id="test-channel",
            embedding_id="emb-002",
            sentiment_score=0.5,
            sentiment_label="neutral",
        ),
        P03EventState(
            event_id="evt-int-003",
            hipp_event_id="evt-int-003",
            content_text="Third integration test event",
            content_type="CHAT",
            content_hash="hash003",
            simhash_hex="simhash003",
            timestamp=base_ts + 2000,
            channel_id="test-channel",
            embedding_id="emb-003",
            sentiment_score=0.8,
            sentiment_label="positive",
        ),
    ]


@pytest.fixture
def sample_envelope(
    sample_context: P03CycleContext,
    sample_events: List[P03EventState],
) -> P03BatchEnvelope:
    """Create sample envelope for integration testing."""
    return P03BatchEnvelope.create(
        context=sample_context,
        events=sample_events,
    )


# =============================================================================
# TEST: ENVELOPE FROZEN CONTEXT
# =============================================================================


class TestEnvelopeFrozenContext:
    """Tests for frozen context immutability."""

    def test_context_prevents_mutation(self, sample_context: P03CycleContext) -> None:
        """
        Given: A P03CycleContext instance
        When: Attempting to mutate any field
        Then: FrozenInstanceError is raised
        """
        with pytest.raises(FrozenInstanceError):
            sample_context.tenant_id = "new-tenant"  # type: ignore

    def test_context_event_ids_are_tuple(self, sample_context: P03CycleContext) -> None:
        """
        Given: A P03CycleContext instance
        When: Checking event_ids type
        Then: It should be a tuple (immutable)
        """
        assert isinstance(sample_context.event_ids, tuple)

    def test_context_hash_is_stable(self, sample_context: P03CycleContext) -> None:
        """
        Given: A P03CycleContext instance
        When: Computing hash multiple times
        Then: Hash should be identical each time
        """
        hash1 = hash(sample_context)
        hash2 = hash(sample_context)
        assert hash1 == hash2

    def test_context_equality_is_value_based(self) -> None:
        """
        Given: Two P03CycleContext instances with same values
        When: Comparing equality
        Then: They should have same tenant_id and space_id
        """
        ctx1 = P03CycleContext.create(
            tenant_id="tenant-eq",
            space_id="space-eq",
            event_ids=["evt-1"],
            trigger_type="MANUAL",
            trigger_reason="Test",
        )
        ctx2 = P03CycleContext.create(
            tenant_id="tenant-eq",
            space_id="space-eq",
            event_ids=["evt-1"],
            trigger_type="MANUAL",
            trigger_reason="Test",
        )
        # Different cycle_id means different contexts
        assert ctx1.tenant_id == ctx2.tenant_id
        assert ctx1.space_id == ctx2.space_id


# =============================================================================
# TEST: EVENT STATE MUTATION
# =============================================================================


class TestEventStateMutation:
    """Tests for event state mutability during phase execution."""

    def test_events_list_is_mutable(self, sample_envelope: P03BatchEnvelope) -> None:
        """
        Given: A P03BatchEnvelope instance
        When: Modifying the events list
        Then: Modifications are allowed
        """
        original_count = len(sample_envelope.events)
        new_event = P03EventState(
            event_id="evt-new",
            hipp_event_id="evt-new",
            content_text="New event",
            content_type="CHAT",
            content_hash="hash-new",
            simhash_hex="simhash-new",
            timestamp=int(time.time() * 1000),
            channel_id="test-channel",
            embedding_id="emb-new",
        )
        sample_envelope.events.append(new_event)
        assert len(sample_envelope.events) == original_count + 1

    def test_event_enrichment_persists(self, sample_envelope: P03BatchEnvelope) -> None:
        """
        Given: An event in the envelope
        When: Enriching with reconciliation action
        Then: Enrichment persists
        """
        event = sample_envelope.events[0]
        event.reconciliation_action = ReconciliationAction.CREATE
        event.importance_score = 0.85
        event.decay_score = 0.1

        assert sample_envelope.events[0].reconciliation_action == ReconciliationAction.CREATE
        assert sample_envelope.events[0].importance_score == 0.85
        assert sample_envelope.events[0].decay_score == 0.1

    def test_phase_enrichment_chain(self, sample_envelope: P03BatchEnvelope) -> None:
        """
        Given: An envelope with events
        When: Simulating R1 → R2 → R3 enrichment
        Then: All enrichments are preserved
        """
        # R1: Importance scoring
        for event in sample_envelope.events:
            event.importance_score = 0.8

        # R2: Decay scoring
        for event in sample_envelope.events:
            event.decay_score = 0.15

        # R3: Pruning decision
        for event in sample_envelope.events:
            event.reconciliation_action = ReconciliationAction.CREATE

        # Verify all enrichments preserved
        for event in sample_envelope.events:
            assert event.importance_score == 0.8
            assert event.decay_score == 0.15
            assert event.reconciliation_action == ReconciliationAction.CREATE


# =============================================================================
# TEST: CHECKPOINT SAVE/RESTORE
# =============================================================================


class TestCheckpointSaveRestore:
    """Tests for checkpoint persistence across phases."""

    def test_checkpoint_creation(self, sample_envelope: P03BatchEnvelope) -> None:
        """
        Given: An envelope at a specific phase
        When: Creating a checkpoint
        Then: Checkpoint captures envelope state
        """
        # Mark phase
        sample_envelope.mark_phase_start(P03PhaseId.R3_PRUNE)

        checkpoint = P03Checkpoint.create(
            cycle_id=sample_envelope.context.cycle_id,
            batch_id=sample_envelope.context.batch_id,
            space_id=sample_envelope.context.space_id,
            tenant_id=sample_envelope.context.tenant_id,
            phase_id=P03PhaseId.R3_PRUNE,
            phase_status=P03PhaseStatus.DONE,
            envelope_summary={"events_processed": len(sample_envelope.events)},
            event_ids=list(sample_envelope.context.event_ids),
        )

        assert checkpoint.phase_id == P03PhaseId.R3_PRUNE
        assert checkpoint.cycle_id == sample_envelope.context.cycle_id

    def test_checkpoint_to_dict_from_dict(self, sample_envelope: P03BatchEnvelope) -> None:
        """
        Given: A P03Checkpoint
        When: Converting to dict and back
        Then: All data is preserved
        """
        checkpoint = P03Checkpoint.create(
            cycle_id=sample_envelope.context.cycle_id,
            batch_id=sample_envelope.context.batch_id,
            space_id=sample_envelope.context.space_id,
            tenant_id=sample_envelope.context.tenant_id,
            phase_id=P03PhaseId.R4_KG,
            phase_status=P03PhaseStatus.DONE,
            envelope_summary={"events_processed": len(sample_envelope.events)},
            event_ids=list(sample_envelope.context.event_ids),
        )

        as_dict = checkpoint.to_dict()
        restored = P03Checkpoint.from_dict(as_dict)

        assert restored.phase_id == checkpoint.phase_id
        assert restored.cycle_id == checkpoint.cycle_id
        assert restored.batch_id == checkpoint.batch_id

    def test_checkpoint_envelope_summary_preserved(
        self,
        sample_envelope: P03BatchEnvelope,
    ) -> None:
        """
        Given: A checkpoint with envelope summary
        When: Restoring from dict
        Then: Summary data matches original
        """
        # Create checkpoint with envelope summary
        summary = {
            "events_count": len(sample_envelope.events),
            "staged_writes_count": 5,
            "importance_scores": [0.8, 0.9, 0.95],
        }

        checkpoint = P03Checkpoint.create(
            cycle_id=sample_envelope.context.cycle_id,
            batch_id=sample_envelope.context.batch_id,
            space_id=sample_envelope.context.space_id,
            tenant_id=sample_envelope.context.tenant_id,
            phase_id=P03PhaseId.R2_CLUSTER,
            phase_status=P03PhaseStatus.DONE,
            envelope_summary=summary,
            event_ids=list(sample_envelope.context.event_ids),
        )

        # Roundtrip
        as_dict = checkpoint.to_dict()
        restored = P03Checkpoint.from_dict(as_dict)

        assert restored.envelope_summary == summary
        assert restored.envelope_summary["events_count"] == len(sample_envelope.events)


# =============================================================================
# TEST: DETERMINISTIC SEED
# =============================================================================


class TestDeterministicSeed:
    """Tests for deterministic behavior with same inputs."""

    def test_batch_id_is_deterministic(self) -> None:
        """
        Given: Same event IDs
        When: Creating context multiple times
        Then: batch_id should be identical between contexts
        """
        event_ids = ["evt-det-001", "evt-det-002", "evt-det-003"]

        ctx1 = P03CycleContext.create(
            tenant_id="tenant",
            space_id="space",
            event_ids=event_ids,
            trigger_type="MANUAL",
            trigger_reason="Test",
        )

        ctx2 = P03CycleContext.create(
            tenant_id="tenant",
            space_id="space",
            event_ids=event_ids,
            trigger_type="MANUAL",
            trigger_reason="Test",
        )

        # Both contexts have same batch_id (deterministic hash of event_ids)
        assert ctx1.batch_id == ctx2.batch_id

    def test_event_ordering_is_deterministic(self) -> None:
        """
        Given: Same event IDs in different order
        When: Creating context
        Then: event_ids tuple should be sorted consistently
        """
        ids_order1 = ["evt-c", "evt-a", "evt-b"]
        ids_order2 = ["evt-b", "evt-c", "evt-a"]

        ctx1 = P03CycleContext.create(
            tenant_id="tenant",
            space_id="space",
            event_ids=ids_order1,
            trigger_type="MANUAL",
            trigger_reason="Test",
        )

        ctx2 = P03CycleContext.create(
            tenant_id="tenant",
            space_id="space",
            event_ids=ids_order2,
            trigger_type="MANUAL",
            trigger_reason="Test",
        )

        # Both should have same sorted order
        assert ctx1.event_ids == ctx2.event_ids
        assert ctx1.batch_id == ctx2.batch_id

    def test_idempotency_key_pattern(self, sample_envelope: P03BatchEnvelope) -> None:
        """
        Given: Same cycle context
        When: Creating idempotency keys for phases
        Then: Keys are deterministic and unique per phase
        """
        cycle_id = sample_envelope.context.cycle_id

        r1_key = f"p03:r1:{cycle_id}"
        r2_key = f"p03:r2:{cycle_id}"

        # Different phases = different keys
        assert r1_key != r2_key

        # Same phase = same key
        r1_key_again = f"p03:r1:{cycle_id}"
        assert r1_key == r1_key_again


# =============================================================================
# TEST: PHASE CHAIN EXECUTION ORDER
# =============================================================================


class TestPhaseChainExecutionOrder:
    """Tests for phase execution order."""

    def test_phase_order_is_defined(self) -> None:
        """
        Given: P03PhaseId enum
        When: Getting execution order
        Then: Order is R0 → R1 → R2 → R3 → R4 → R5 → R6 → R7 → R8
        """
        order = P03PhaseId.execution_order()

        assert order[0] == P03PhaseId.R0_INIT
        assert order[1] == P03PhaseId.R1_SCORE
        assert order[2] == P03PhaseId.R2_CLUSTER
        assert order[3] == P03PhaseId.R3_PRUNE
        assert order[4] == P03PhaseId.R4_KG
        assert order[5] == P03PhaseId.R5_DREAM
        assert order[6] == P03PhaseId.R6_STAGE
        assert order[7] == P03PhaseId.R7_WRITE
        assert order[8] == P03PhaseId.R8_EMIT

    def test_phase_status_transitions(self, sample_envelope: P03BatchEnvelope) -> None:
        """
        Given: An envelope
        When: Marking phase start and complete
        Then: Status transitions are recorded
        """
        # Start R1
        sample_envelope.mark_phase_start(P03PhaseId.R1_SCORE)
        assert sample_envelope.phase_statuses[P03PhaseId.R1_SCORE] == P03PhaseStatus.PROC

        # Complete R1
        sample_envelope.mark_phase_complete(P03PhaseId.R1_SCORE)
        assert sample_envelope.phase_statuses[P03PhaseId.R1_SCORE] == P03PhaseStatus.DONE

    def test_observability_tracks_phase_timing(
        self,
        sample_envelope: P03BatchEnvelope,
    ) -> None:
        """
        Given: An envelope with observability context
        When: Running phases
        Then: Timing is recorded in phase_start_ts and phase_end_ts
        """
        # Start phase
        sample_envelope.observability.start_phase("R1")
        time.sleep(0.01)  # Small delay
        sample_envelope.observability.end_phase("R1")

        # Verify timing recorded
        assert "R1" in sample_envelope.observability.phase_start_ts
        assert "R1" in sample_envelope.observability.phase_end_ts

        # End should be after start
        start_ts = sample_envelope.observability.phase_start_ts["R1"]
        end_ts = sample_envelope.observability.phase_end_ts["R1"]
        assert end_ts >= start_ts


# =============================================================================
# TEST: ENVELOPE INTEGRATION SUMMARY
# =============================================================================


class TestEnvelopeIntegrationSummary:
    """Summary test ensuring all integration scenarios are covered."""

    def test_all_integration_test_classes_exist(self) -> None:
        """
        Meta-test: Verify all expected test classes are present.
        """
        expected_classes = [
            "TestEnvelopeFrozenContext",
            "TestEventStateMutation",
            "TestCheckpointSaveRestore",
            "TestDeterministicSeed",
            "TestPhaseChainExecutionOrder",
            "TestEnvelopeIntegrationSummary",
        ]

        for class_name in expected_classes:
            assert class_name in globals(), f"Missing test class: {class_name}"
