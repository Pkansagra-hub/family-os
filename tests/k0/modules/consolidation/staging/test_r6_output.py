"""
Unit tests for R6Output, StagedEventUpdate, and StagedWritesContainer.

Issue: 5.1.1
Spec Reference:
    - Dossier §4.7 (R6 — Staging Table Updates)
    - M5_EXECUTION.md Issue 5.1.1

These tests verify:
    1. StagedEventUpdate creation and validation
    2. ReconciliationSummary aggregation
    3. StagedWritesContainer accumulation and deduplication
    4. R6Output immutability and serialization
    5. Dependency-ordered write retrieval
"""

from __future__ import annotations

import json

import pytest

from k0.modules.consolidation.staging.r6_output import (
    STATUS_CONSOLIDATED,
    STATUS_DUPLICATE,
    STATUS_PENDING_REVIEW,
    STATUS_PRUNED,
    VALID_CONSOLIDATION_STATUSES,
    R6Output,
    ReconciliationSummary,
    StagedEventUpdate,
    StagedWritesContainer,
)
from k0.pipelines.p03.context import generate_ulid
from k0.pipelines.p03.staged_writes import (
    LAYER_ST_EPI,
    LAYER_ST_HIPP_EVENTS,
    LAYER_ST_KG_DOM,
    LAYER_ST_KG_EDGES,
    LAYER_ST_SEM,
    StagedOutboxEvent,
    StagedWrite,
    WriteOperation,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def cycle_ulid() -> str:
    """Generate a test cycle ULID."""
    return generate_ulid()


@pytest.fixture
def batch_id() -> str:
    """Generate a test batch ID."""
    return "test_batch_123456"


@pytest.fixture
def sample_event_update() -> StagedEventUpdate:
    """Create a sample StagedEventUpdate."""
    return StagedEventUpdate(
        event_id=generate_ulid(),
        consolidation_status=STATUS_CONSOLIDATED,
        near_duplicates_json="[]",
        novelty_score=0.85,
        episode_cluster_id="cluster_001",
        reconciliation_action="REINFORCE",
        best_match_id="epi_001",
        best_match_layer="st_epi",
        similarity_score=0.92,
        confidence=0.88,
        reconciliation_reason="High similarity to existing episode",
        idempotency_key="p03:staging:test:event_001",
    )


@pytest.fixture
def sample_truth_write() -> StagedWrite:
    """Create a sample truth layer write."""
    return StagedWrite.insert(
        layer=LAYER_ST_EPI,
        record_id="epi_test_001",
        data={"title": "Test Episode", "summary": "Test summary"},
        phase="R6",
        event_ids=["event_001", "event_002"],
    )


@pytest.fixture
def sample_kg_entity_write() -> StagedWrite:
    """Create a sample KG entity write."""
    return StagedWrite.insert(
        layer=LAYER_ST_KG_DOM,
        record_id="entity_test_001",
        data={"canonical_name": "Test Entity", "entity_type": "PERSON"},
        phase="R4",
        event_ids=["event_001"],
    )


@pytest.fixture
def sample_kg_edge_write() -> StagedWrite:
    """Create a sample KG edge write."""
    return StagedWrite.insert(
        layer=LAYER_ST_KG_EDGES,
        record_id="edge_test_001",
        data={"source_id": "entity_001", "target_id": "entity_002", "relation": "KNOWS"},
        phase="R4",
        event_ids=["event_001"],
    )


@pytest.fixture
def sample_outbox_event() -> StagedOutboxEvent:
    """Create a sample outbox event."""
    return StagedOutboxEvent.create(
        topic="p03.pattern.detected.v1",
        payload={"pattern_id": "pattern_001", "confidence": 0.9},
        phase="R8",
        priority=50,
    )


# =============================================================================
# STAGED EVENT UPDATE TESTS
# =============================================================================


class TestStagedEventUpdate:
    """Tests for StagedEventUpdate dataclass."""

    def test_create_valid_update(self) -> None:
        """Test creating a valid StagedEventUpdate."""
        update = StagedEventUpdate(
            event_id="test_event_001",
            consolidation_status=STATUS_CONSOLIDATED,
            idempotency_key="p03:staging:test:001",
        )

        assert update.event_id == "test_event_001"
        assert update.consolidation_status == STATUS_CONSOLIDATED
        assert update.near_duplicates_json == "[]"
        assert update.novelty_score == 1.0
        assert update.reconciliation_action == "PENDING"
        assert update.created_at_ms > 0

    def test_all_status_values_valid(self) -> None:
        """Test that all defined status values are accepted."""
        for status in VALID_CONSOLIDATION_STATUSES:
            update = StagedEventUpdate(
                event_id=f"event_{status}",
                consolidation_status=status,
                idempotency_key=f"key_{status}",
            )
            assert update.consolidation_status == status

    def test_invalid_status_raises_error(self) -> None:
        """Test that invalid status raises ValueError."""
        with pytest.raises(ValueError, match="Invalid consolidation_status"):
            StagedEventUpdate(
                event_id="test_event",
                consolidation_status="INVALID_STATUS",
                idempotency_key="test_key",
            )

    def test_hashable_for_deduplication(self, sample_event_update: StagedEventUpdate) -> None:
        """Test that StagedEventUpdate is hashable."""
        # Should not raise
        hash_value = hash(sample_event_update)
        assert isinstance(hash_value, int)

        # Same event_id + key should have same hash
        update2 = StagedEventUpdate(
            event_id=sample_event_update.event_id,
            consolidation_status=STATUS_DUPLICATE,  # Different status
            idempotency_key=sample_event_update.idempotency_key,
        )
        assert hash(sample_event_update) == hash(update2)

    def test_equality_based_on_id_and_key(self, sample_event_update: StagedEventUpdate) -> None:
        """Test equality comparison."""
        update2 = StagedEventUpdate(
            event_id=sample_event_update.event_id,
            consolidation_status=STATUS_DUPLICATE,  # Different status
            idempotency_key=sample_event_update.idempotency_key,
        )
        assert sample_event_update == update2

        update3 = StagedEventUpdate(
            event_id="different_event",
            consolidation_status=sample_event_update.consolidation_status,
            idempotency_key=sample_event_update.idempotency_key,
        )
        assert sample_event_update != update3

    def test_to_record_data(self, sample_event_update: StagedEventUpdate) -> None:
        """Test conversion to record data dict."""
        data = sample_event_update.to_record_data()

        assert data["consolidation_status"] == STATUS_CONSOLIDATED
        assert data["near_duplicates_json"] == "[]"
        assert data["novelty_score"] == 0.85
        assert data["episode_cluster_id"] == "cluster_001"
        assert data["reconciliation_action"] == "REINFORCE"
        assert data["best_match_id"] == "epi_001"
        assert data["best_match_layer"] == "st_epi"
        assert data["similarity_score"] == 0.92
        assert data["confidence"] == 0.88
        assert "consolidated_at_ms" in data

    def test_to_staged_write(self, sample_event_update: StagedEventUpdate) -> None:
        """Test conversion to StagedWrite."""
        write = sample_event_update.to_staged_write()

        assert write.layer == LAYER_ST_HIPP_EVENTS
        assert write.operation == WriteOperation.UPDATE
        assert write.record_id == sample_event_update.event_id
        assert write.source_phase == "R6"
        assert sample_event_update.event_id in write.source_event_ids

    def test_json_serialization_roundtrip(self, sample_event_update: StagedEventUpdate) -> None:
        """Test JSON serialization and deserialization."""
        json_str = sample_event_update.to_json()
        restored = StagedEventUpdate.from_json(json_str)

        assert restored.event_id == sample_event_update.event_id
        assert restored.consolidation_status == sample_event_update.consolidation_status
        assert restored.novelty_score == sample_event_update.novelty_score
        assert restored.reconciliation_action == sample_event_update.reconciliation_action


# =============================================================================
# RECONCILIATION SUMMARY TESTS
# =============================================================================


class TestReconciliationSummary:
    """Tests for ReconciliationSummary dataclass."""

    def test_create_default_summary(self) -> None:
        """Test creating summary with defaults."""
        summary = ReconciliationSummary()

        assert summary.total_events == 0
        assert summary.consolidated_count == 0
        assert summary.duplicate_count == 0
        assert summary.pruned_count == 0
        assert summary.pending_review_count == 0
        assert summary.total_writes == 0

    def test_create_populated_summary(self) -> None:
        """Test creating summary with values."""
        summary = ReconciliationSummary(
            total_events=100,
            consolidated_count=80,
            duplicate_count=15,
            pruned_count=3,
            pending_review_count=2,
            action_breakdown=(("REINFORCE", 50), ("CREATE", 30), ("SKIP", 20)),
            layer_write_counts=(("st_epi", 40), ("st_sem", 20)),
            kg_entity_count=25,
            kg_edge_count=35,
            gap_count=5,
            total_writes=100,
            cycle_duration_ms=5000,
        )

        assert summary.total_events == 100
        assert summary.consolidated_count == 80
        assert summary.kg_entity_count == 25

    def test_summary_is_frozen(self) -> None:
        """Test that ReconciliationSummary is immutable."""
        summary = ReconciliationSummary(total_events=10)

        with pytest.raises(Exception):  # FrozenInstanceError
            summary.total_events = 20  # type: ignore

    def test_to_dict(self) -> None:
        """Test conversion to dict."""
        summary = ReconciliationSummary(
            total_events=50,
            consolidated_count=40,
            action_breakdown=(("REINFORCE", 30), ("CREATE", 10)),
        )
        result = summary.to_dict()

        assert result["total_events"] == 50
        assert result["consolidated_count"] == 40
        assert result["action_breakdown"] == {"REINFORCE": 30, "CREATE": 10}

    def test_to_json(self) -> None:
        """Test JSON serialization."""
        summary = ReconciliationSummary(total_events=25)
        json_str = summary.to_json()
        parsed = json.loads(json_str)

        assert parsed["total_events"] == 25


# =============================================================================
# STAGED WRITES CONTAINER TESTS
# =============================================================================


class TestStagedWritesContainer:
    """Tests for StagedWritesContainer class."""

    def test_create_empty_container(self, cycle_ulid: str, batch_id: str) -> None:
        """Test creating an empty container."""
        container = StagedWritesContainer(cycle_ulid, batch_id)

        assert container.cycle_ulid == cycle_ulid
        assert container.batch_id == batch_id
        assert container.event_update_count == 0
        assert container.truth_write_count == 0
        assert container.kg_write_count == 0
        assert container.outbox_event_count == 0
        assert container.total_writes == 0

    def test_add_event_update(
        self,
        cycle_ulid: str,
        batch_id: str,
        sample_event_update: StagedEventUpdate,
    ) -> None:
        """Test adding event updates."""
        container = StagedWritesContainer(cycle_ulid, batch_id)

        result = container.add_event_update(sample_event_update)

        assert result is True
        assert container.event_update_count == 1

    def test_add_duplicate_event_update_rejected(
        self,
        cycle_ulid: str,
        batch_id: str,
        sample_event_update: StagedEventUpdate,
    ) -> None:
        """Test that duplicate event updates are rejected."""
        container = StagedWritesContainer(cycle_ulid, batch_id)

        container.add_event_update(sample_event_update)
        result = container.add_event_update(sample_event_update)

        assert result is False
        assert container.event_update_count == 1

    def test_add_truth_write(
        self,
        cycle_ulid: str,
        batch_id: str,
        sample_truth_write: StagedWrite,
    ) -> None:
        """Test adding truth layer writes."""
        container = StagedWritesContainer(cycle_ulid, batch_id)

        result = container.add_truth_write(sample_truth_write)

        assert result is True
        assert container.truth_write_count == 1

    def test_add_kg_layer_to_truth_raises_error(
        self,
        cycle_ulid: str,
        batch_id: str,
        sample_kg_entity_write: StagedWrite,
    ) -> None:
        """Test that adding KG layer to truth_write raises error."""
        container = StagedWritesContainer(cycle_ulid, batch_id)

        with pytest.raises(ValueError, match="Use add_kg_write"):
            container.add_truth_write(sample_kg_entity_write)

    def test_add_kg_write(
        self,
        cycle_ulid: str,
        batch_id: str,
        sample_kg_entity_write: StagedWrite,
        sample_kg_edge_write: StagedWrite,
    ) -> None:
        """Test adding KG entity and edge writes."""
        container = StagedWritesContainer(cycle_ulid, batch_id)

        result1 = container.add_kg_write(sample_kg_entity_write)
        result2 = container.add_kg_write(sample_kg_edge_write)

        assert result1 is True
        assert result2 is True
        assert container.kg_write_count == 2

    def test_add_non_kg_layer_to_kg_raises_error(
        self,
        cycle_ulid: str,
        batch_id: str,
        sample_truth_write: StagedWrite,
    ) -> None:
        """Test that adding non-KG layer to kg_write raises error."""
        container = StagedWritesContainer(cycle_ulid, batch_id)

        with pytest.raises(ValueError, match="Use add_truth_write"):
            container.add_kg_write(sample_truth_write)

    def test_add_outbox_event(
        self,
        cycle_ulid: str,
        batch_id: str,
        sample_outbox_event: StagedOutboxEvent,
    ) -> None:
        """Test adding outbox events."""
        container = StagedWritesContainer(cycle_ulid, batch_id)

        result = container.add_outbox_event(sample_outbox_event)

        assert result is True
        assert container.outbox_event_count == 1

    def test_get_status_counts(self, cycle_ulid: str, batch_id: str) -> None:
        """Test status count aggregation."""
        container = StagedWritesContainer(cycle_ulid, batch_id)

        # Add updates with different statuses
        for i, status in enumerate(
            [
                STATUS_CONSOLIDATED,
                STATUS_CONSOLIDATED,
                STATUS_CONSOLIDATED,
                STATUS_DUPLICATE,
                STATUS_DUPLICATE,
                STATUS_PRUNED,
                STATUS_PENDING_REVIEW,
            ]
        ):
            update = StagedEventUpdate(
                event_id=f"event_{i}",
                consolidation_status=status,
                idempotency_key=f"key_{i}",
            )
            container.add_event_update(update)

        counts = container.get_status_counts()

        assert counts[STATUS_CONSOLIDATED] == 3
        assert counts[STATUS_DUPLICATE] == 2
        assert counts[STATUS_PRUNED] == 1
        assert counts[STATUS_PENDING_REVIEW] == 1

    def test_get_action_breakdown(self, cycle_ulid: str, batch_id: str) -> None:
        """Test action breakdown aggregation."""
        container = StagedWritesContainer(cycle_ulid, batch_id)

        actions = ["REINFORCE", "REINFORCE", "CREATE", "EXTEND", "SKIP"]
        for i, action in enumerate(actions):
            update = StagedEventUpdate(
                event_id=f"event_{i}",
                consolidation_status=STATUS_CONSOLIDATED,
                reconciliation_action=action,
                idempotency_key=f"key_{i}",
            )
            container.add_event_update(update)

        breakdown = container.get_action_breakdown()

        assert breakdown["REINFORCE"] == 2
        assert breakdown["CREATE"] == 1
        assert breakdown["EXTEND"] == 1
        assert breakdown["SKIP"] == 1

    def test_cannot_add_after_finalization(
        self,
        cycle_ulid: str,
        batch_id: str,
        sample_event_update: StagedEventUpdate,
    ) -> None:
        """Test that adds fail after finalization."""
        container = StagedWritesContainer(cycle_ulid, batch_id)
        container.add_event_update(sample_event_update)

        # Finalize
        container.to_r6_output()

        # Now adds should fail
        new_update = StagedEventUpdate(
            event_id="new_event",
            consolidation_status=STATUS_CONSOLIDATED,
            idempotency_key="new_key",
        )
        with pytest.raises(RuntimeError, match="finalized"):
            container.add_event_update(new_update)

    def test_to_r6_output(
        self,
        cycle_ulid: str,
        batch_id: str,
        sample_event_update: StagedEventUpdate,
        sample_truth_write: StagedWrite,
        sample_kg_entity_write: StagedWrite,
        sample_outbox_event: StagedOutboxEvent,
    ) -> None:
        """Test R6Output generation."""
        container = StagedWritesContainer(cycle_ulid, batch_id)

        container.add_event_update(sample_event_update)
        container.add_truth_write(sample_truth_write)
        container.add_kg_write(sample_kg_entity_write)
        container.add_outbox_event(sample_outbox_event)

        output = container.to_r6_output()

        assert output.cycle_ulid == cycle_ulid
        assert output.batch_id == batch_id
        assert output.event_count == 1
        assert output.total_truth_writes == 1
        assert output.total_kg_writes == 1
        assert output.total_outbox_events == 1
        assert output.r6_idempotency_key.startswith("p03:r6:")

    def test_to_json_before_finalization(
        self,
        cycle_ulid: str,
        batch_id: str,
        sample_event_update: StagedEventUpdate,
    ) -> None:
        """Test JSON checkpoint before finalization."""
        container = StagedWritesContainer(cycle_ulid, batch_id)
        container.add_event_update(sample_event_update)

        json_str = container.to_json()
        parsed = json.loads(json_str)

        assert parsed["cycle_ulid"] == cycle_ulid
        assert parsed["event_update_count"] == 1
        assert parsed["finalized"] is False


# =============================================================================
# R6 OUTPUT TESTS
# =============================================================================


class TestR6Output:
    """Tests for R6Output dataclass."""

    def test_r6_output_is_frozen(
        self,
        cycle_ulid: str,
        batch_id: str,
        sample_event_update: StagedEventUpdate,
    ) -> None:
        """Test that R6Output is immutable."""
        container = StagedWritesContainer(cycle_ulid, batch_id)
        container.add_event_update(sample_event_update)
        output = container.to_r6_output()

        with pytest.raises(Exception):  # FrozenInstanceError
            output.cycle_ulid = "new_ulid"  # type: ignore

    def test_validation_requires_cycle_ulid(self, batch_id: str) -> None:
        """Test that empty cycle_ulid raises error."""
        with pytest.raises(ValueError, match="cycle_ulid is required"):
            R6Output(
                cycle_ulid="",
                batch_id=batch_id,
                staged_event_updates=(),
                staged_truth_writes=(),
                staged_kg_writes=(),
                staged_outbox_events=(),
                reconciliation_summary=ReconciliationSummary(),
                created_at_ms=1234567890000,
                r6_idempotency_key="test_key",
            )

    def test_validation_requires_batch_id(self, cycle_ulid: str) -> None:
        """Test that empty batch_id raises error."""
        with pytest.raises(ValueError, match="batch_id is required"):
            R6Output(
                cycle_ulid=cycle_ulid,
                batch_id="",
                staged_event_updates=(),
                staged_truth_writes=(),
                staged_kg_writes=(),
                staged_outbox_events=(),
                reconciliation_summary=ReconciliationSummary(),
                created_at_ms=1234567890000,
                r6_idempotency_key="test_key",
            )

    def test_get_all_writes_ordered(
        self,
        cycle_ulid: str,
        batch_id: str,
    ) -> None:
        """Test dependency-ordered write retrieval."""
        container = StagedWritesContainer(cycle_ulid, batch_id)

        # Add writes in non-dependency order
        epi_write = StagedWrite.insert(
            layer=LAYER_ST_EPI,
            record_id="epi_001",
            data={"title": "Episode 1"},
            phase="R6",
        )
        kg_entity_write = StagedWrite.insert(
            layer=LAYER_ST_KG_DOM,
            record_id="entity_001",
            data={"name": "Entity 1"},
            phase="R4",
        )
        kg_edge_write = StagedWrite.insert(
            layer=LAYER_ST_KG_EDGES,
            record_id="edge_001",
            data={"relation": "KNOWS"},
            phase="R4",
        )
        event_update = StagedEventUpdate(
            event_id="event_001",
            consolidation_status=STATUS_CONSOLIDATED,
            idempotency_key="key_001",
        )

        # Add in non-dependency order
        container.add_event_update(event_update)
        container.add_truth_write(epi_write)
        container.add_kg_write(kg_edge_write)
        container.add_kg_write(kg_entity_write)

        output = container.to_r6_output()
        ordered_writes = output.get_all_writes_ordered()

        # Verify order: kg_dom before kg_edges before epi before hipp_events
        layers = [w.layer for w in ordered_writes]
        assert layers.index(LAYER_ST_KG_DOM) < layers.index(LAYER_ST_KG_EDGES)
        assert layers.index(LAYER_ST_KG_EDGES) < layers.index(LAYER_ST_EPI)
        assert layers.index(LAYER_ST_EPI) < layers.index(LAYER_ST_HIPP_EVENTS)

    def test_to_json(
        self,
        cycle_ulid: str,
        batch_id: str,
        sample_event_update: StagedEventUpdate,
    ) -> None:
        """Test R6Output JSON serialization."""
        container = StagedWritesContainer(cycle_ulid, batch_id)
        container.add_event_update(sample_event_update)
        output = container.to_r6_output()

        json_str = output.to_json()
        parsed = json.loads(json_str)

        assert parsed["cycle_ulid"] == cycle_ulid
        assert parsed["batch_id"] == batch_id
        assert "reconciliation_summary" in parsed
        assert "created_at_ms" in parsed

    def test_to_summary_dict(
        self,
        cycle_ulid: str,
        batch_id: str,
        sample_event_update: StagedEventUpdate,
        sample_truth_write: StagedWrite,
    ) -> None:
        """Test R6Output summary dict generation."""
        container = StagedWritesContainer(cycle_ulid, batch_id)
        container.add_event_update(sample_event_update)
        container.add_truth_write(sample_truth_write)
        output = container.to_r6_output()

        summary = output.to_summary_dict()

        assert summary["cycle_ulid"] == cycle_ulid
        assert summary["event_count"] == 1
        assert summary["total_truth_writes"] == 1
        assert summary["total_writes"] == 2  # 1 event + 1 truth

    def test_total_writes_property(
        self,
        cycle_ulid: str,
        batch_id: str,
    ) -> None:
        """Test total_writes calculation."""
        container = StagedWritesContainer(cycle_ulid, batch_id)

        # Add 3 event updates
        for i in range(3):
            container.add_event_update(
                StagedEventUpdate(
                    event_id=f"event_{i}",
                    consolidation_status=STATUS_CONSOLIDATED,
                    idempotency_key=f"key_{i}",
                )
            )

        # Add 2 truth writes
        for i in range(2):
            container.add_truth_write(
                StagedWrite.insert(
                    layer=LAYER_ST_EPI,
                    record_id=f"epi_{i}",
                    data={"title": f"Episode {i}"},
                    phase="R6",
                )
            )

        # Add 1 KG write
        container.add_kg_write(
            StagedWrite.insert(
                layer=LAYER_ST_KG_DOM,
                record_id="entity_001",
                data={"name": "Entity 1"},
                phase="R4",
            )
        )

        output = container.to_r6_output()

        assert output.event_count == 3
        assert output.total_truth_writes == 2
        assert output.total_kg_writes == 1
        assert output.total_writes == 6  # 3 + 2 + 1


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestStagingIntegration:
    """Integration tests for R6 staging workflow."""

    def test_full_r6_workflow(self) -> None:
        """Test complete R6 staging workflow."""
        cycle_ulid = generate_ulid()
        batch_id = "integration_test_batch"

        # Create container
        container = StagedWritesContainer(cycle_ulid, batch_id)

        # Simulate processing 5 events with different outcomes
        statuses = [
            (STATUS_CONSOLIDATED, "REINFORCE"),
            (STATUS_CONSOLIDATED, "CREATE"),
            (STATUS_CONSOLIDATED, "EXTEND"),
            (STATUS_DUPLICATE, "SKIP"),
            (STATUS_PENDING_REVIEW, "CONTRADICT"),
        ]

        for i, (status, action) in enumerate(statuses):
            update = StagedEventUpdate(
                event_id=f"event_{i:03d}",
                consolidation_status=status,
                reconciliation_action=action,
                idempotency_key=f"p03:staging:{cycle_ulid}:event_{i:03d}",
            )
            container.add_event_update(update)

        # Add some truth writes
        container.add_truth_write(
            StagedWrite.insert(
                layer=LAYER_ST_EPI,
                record_id="epi_001",
                data={"title": "Test Episode"},
                phase="R6",
            )
        )
        container.add_truth_write(
            StagedWrite.insert(
                layer=LAYER_ST_SEM,
                record_id="sem_001",
                data={"pattern": "Test Pattern"},
                phase="R6",
            )
        )

        # Add KG writes
        container.add_kg_write(
            StagedWrite.insert(
                layer=LAYER_ST_KG_DOM,
                record_id="entity_001",
                data={"name": "Person A"},
                phase="R4",
            )
        )
        container.add_kg_write(
            StagedWrite.insert(
                layer=LAYER_ST_KG_EDGES,
                record_id="edge_001",
                data={"relation": "KNOWS"},
                phase="R4",
            )
        )

        # Add outbox events
        container.add_outbox_event(
            StagedOutboxEvent.create(
                topic="p03.cycle.completed.v1",
                payload={"cycle_ulid": cycle_ulid},
                phase="R8",
            )
        )

        # Finalize
        output = container.to_r6_output()

        # Verify summary
        summary = output.reconciliation_summary
        assert summary.total_events == 5
        assert summary.consolidated_count == 3
        assert summary.duplicate_count == 1
        assert summary.pending_review_count == 1
        assert summary.kg_entity_count == 1
        assert summary.kg_edge_count == 1

        # Verify totals
        assert output.event_count == 5
        assert output.total_truth_writes == 2
        assert output.total_kg_writes == 2
        assert output.total_outbox_events == 1
        assert output.total_writes == 9  # 5 events + 2 truth + 2 KG

        # Verify ordered writes
        ordered = output.get_all_writes_ordered()
        assert len(ordered) == 9

        # Verify idempotency key format
        assert output.r6_idempotency_key.startswith("p03:r6:")
        assert cycle_ulid in output.r6_idempotency_key

    def test_empty_cycle_produces_valid_output(self) -> None:
        """Test that an empty cycle still produces valid R6Output."""
        cycle_ulid = generate_ulid()
        batch_id = "empty_batch"

        container = StagedWritesContainer(cycle_ulid, batch_id)
        output = container.to_r6_output()

        assert output.event_count == 0
        assert output.total_writes == 0
        assert output.reconciliation_summary.total_events == 0
        assert len(output.get_all_writes_ordered()) == 0
