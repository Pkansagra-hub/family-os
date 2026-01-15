"""
Tests for ManifestValidator — Issue 5.1.9

Tests R6Output manifest validation before R7 commit.
"""

import pytest

from k0.modules.consolidation.staging.manifest_validator import (
    ManifestValidator,
    is_valid_manifest,
    summarize_validation,
    validate_r6_output,
)
from k0.modules.consolidation.staging.r6_output import (
    R6Output,
    ReconciliationSummary,
    StagedEventUpdate,
)
from k0.pipelines.p03.staged_writes import (
    LAYER_ST_EPI,
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


def make_staged_write(
    layer: str = LAYER_ST_EPI,
    record_id: str = "rec_001",
    idempotency_key: str = "p03:write:cycle:st_epi:rec_001",
    **overrides,
) -> StagedWrite:
    """Create a StagedWrite with defaults."""
    defaults = {
        "write_id": "write_001",
        "layer": layer,
        "operation": WriteOperation.INSERT,
        "record_id": record_id,
        "record_data": {},
        "idempotency_key": idempotency_key,
        "source_phase": "R6",
        "expected_version": 0,
        "source_event_ids": [],
    }
    defaults.update(overrides)
    return StagedWrite(**defaults)


def make_kg_entity_write(
    entity_id: str,
    **overrides,
) -> StagedWrite:
    """Create a KG entity write."""
    return make_staged_write(
        layer=LAYER_ST_KG_DOM,
        record_id=entity_id,
        idempotency_key=f"p03:write:cycle:st_kg_dom:{entity_id}",
        write_id=f"write_{entity_id}",
        **overrides,
    )


def make_kg_edge_write(
    edge_id: str,
    source_id: str,
    target_id: str,
    **overrides,
) -> StagedWrite:
    """Create a KG edge write."""
    return make_staged_write(
        layer=LAYER_ST_KG_EDGES,
        record_id=edge_id,
        idempotency_key=f"p03:write:cycle:st_kg_edges:{edge_id}",
        write_id=f"write_{edge_id}",
        record_data={"source_id": source_id, "target_id": target_id},
        **overrides,
    )


def make_staged_event_update(
    event_id: str,
    version_conflict: bool = False,
    **overrides,
) -> StagedEventUpdate:
    """Create a StagedEventUpdate with defaults."""
    defaults = {
        "event_id": event_id,
        "version_conflict": version_conflict,
        "consolidation_status": "CONSOLIDATED",
        "near_duplicates_json": "[]",
        "novelty_score": 0.5,
        "episode_cluster_id": "cluster_001",
        "reconciliation_action": "CREATE",
        "best_match_id": None,
        "best_match_layer": None,
        "similarity_score": 0.0,
        "confidence": 0.9,
        "reconciliation_reason": "test",
        "idempotency_key": f"p03:update:cycle:st_hipp_events:{event_id}",
        "created_at_ms": 1000000,
    }
    defaults.update(overrides)
    return StagedEventUpdate(**defaults)


def make_outbox_event(
    topic: str = "p03.consolidation.complete.v1",
    **overrides,
) -> StagedOutboxEvent:
    """Create a StagedOutboxEvent with defaults."""
    defaults = {
        "event_id": "outbox_001",
        "topic": topic,
        "payload": {},
        "source_phase": "R6",
        "idempotency_key": "R6:event:outbox_001",  # Issue 8.1.13
        "priority": 10,
        "created_at_ms": 1000000,
    }
    defaults.update(overrides)
    return StagedOutboxEvent(**defaults)


def make_summary(**overrides) -> ReconciliationSummary:
    """Create a ReconciliationSummary with defaults."""
    defaults = {
        "total_events": 10,
        "consolidated_count": 5,
        "duplicate_count": 2,
        "pruned_count": 1,
        "pending_review_count": 2,
        "action_breakdown": (),
        "layer_write_counts": (),
        "kg_entity_count": 0,
        "kg_edge_count": 0,
        "gap_count": 0,
        "total_writes": 5,
        "cycle_duration_ms": 1000,
    }
    defaults.update(overrides)
    return ReconciliationSummary(**defaults)


def make_r6_output(
    event_updates: tuple = (),
    truth_writes: tuple = (),
    kg_writes: tuple = (),
    outbox_events: tuple = (),
    **overrides,
) -> R6Output:
    """Create an R6Output with defaults."""
    defaults = {
        "cycle_ulid": "01ABC123",
        "batch_id": "batch_001",
        "staged_event_updates": event_updates,
        "staged_truth_writes": truth_writes,
        "staged_kg_writes": kg_writes,
        "staged_outbox_events": outbox_events,
        "reconciliation_summary": make_summary(),
        "created_at_ms": 1000000,
        "r6_idempotency_key": "p03:r6:01ABC123",
    }
    defaults.update(overrides)
    return R6Output(**defaults)


@pytest.fixture
def validator() -> ManifestValidator:
    """Create validator with default config."""
    return ManifestValidator()


# =============================================================================
# TEST VALIDATOR INIT
# =============================================================================


class TestValidatorInit:
    """Tests for ManifestValidator initialization."""

    def test_init_empty_existing_entities(self):
        """Default validator has empty existing entity set."""
        v = ManifestValidator()
        assert v.existing_entity_ids == set()

    def test_init_with_existing_entities(self):
        """Validator accepts existing entity IDs."""
        existing = {"ent_001", "ent_002"}
        v = ManifestValidator(existing_entity_ids=existing)
        assert v.existing_entity_ids == existing


# =============================================================================
# TEST LAYER VALIDATION
# =============================================================================


class TestLayerValidation:
    """Tests for layer validity checks."""

    def test_valid_layers_pass(self, validator):
        """Writes with valid layers pass validation."""
        writes = [
            make_staged_write(layer=LAYER_ST_EPI),
            make_staged_write(layer=LAYER_ST_SEM, record_id="rec_002"),
        ]
        r6 = make_r6_output(
            truth_writes=tuple(writes),
            outbox_events=(make_outbox_event(),),
            event_updates=(make_staged_event_update("e1"),),
        )
        result = validator.validate(r6, {"e1"})
        assert result.is_valid
        assert len(result.errors) == 0

    def test_invalid_layer_fails(self, validator):
        """Write with invalid layer fails validation."""
        writes = [make_staged_write(layer="invalid_layer")]
        r6 = make_r6_output(
            truth_writes=tuple(writes),
            outbox_events=(make_outbox_event(),),
            event_updates=(make_staged_event_update("e1"),),
        )
        result = validator.validate(r6, {"e1"})

        assert not result.is_valid
        assert result.dlq_reason == "invalid_layer"
        assert any("invalid_layer" in e for e in result.errors)


# =============================================================================
# TEST IDEMPOTENCY KEY VALIDATION
# =============================================================================


class TestIdempotencyKeyValidation:
    """Tests for idempotency key format validation."""

    def test_valid_keys_pass(self, validator):
        """Valid idempotency keys pass validation."""
        writes = [
            make_staged_write(idempotency_key="p03:write:cycle:st_epi:rec"),
            make_staged_write(
                idempotency_key="R6:st_sem:rec_002",
                record_id="rec_002",
            ),
        ]
        r6 = make_r6_output(
            truth_writes=tuple(writes),
            outbox_events=(make_outbox_event(),),
            event_updates=(make_staged_event_update("e1"),),
        )
        result = validator.validate(r6, {"e1"})
        assert result.is_valid

    def test_empty_key_fails(self, validator):
        """Empty idempotency key fails validation."""
        writes = [make_staged_write(idempotency_key="")]
        r6 = make_r6_output(
            truth_writes=tuple(writes),
            outbox_events=(make_outbox_event(),),
            event_updates=(make_staged_event_update("e1"),),
        )
        result = validator.validate(r6, {"e1"})

        assert not result.is_valid
        assert result.dlq_reason == "malformed_idempotency_key"

    def test_malformed_key_fails(self, validator):
        """Key with too few parts fails validation."""
        writes = [make_staged_write(idempotency_key="ab")]
        r6 = make_r6_output(
            truth_writes=tuple(writes),
            outbox_events=(make_outbox_event(),),
            event_updates=(make_staged_event_update("e1"),),
        )
        result = validator.validate(r6, {"e1"})

        assert not result.is_valid

    def test_invalid_phase_prefix_fails(self, validator):
        """Key with invalid phase prefix fails."""
        writes = [make_staged_write(idempotency_key="invalid:layer:id")]
        r6 = make_r6_output(
            truth_writes=tuple(writes),
            outbox_events=(make_outbox_event(),),
            event_updates=(make_staged_event_update("e1"),),
        )
        result = validator.validate(r6, {"e1"})

        assert not result.is_valid


# =============================================================================
# TEST FK INTEGRITY
# =============================================================================


class TestFKIntegrity:
    """Tests for foreign key integrity validation."""

    def test_edges_with_staged_entities_pass(self, validator):
        """Edges referencing staged entities pass."""
        entity = make_kg_entity_write("ent_001")
        edge = make_kg_edge_write("edge_001", "ent_001", "ent_001")

        r6 = make_r6_output(
            kg_writes=(entity, edge),
            outbox_events=(make_outbox_event(),),
            event_updates=(make_staged_event_update("e1"),),
        )
        result = validator.validate(r6, {"e1"})
        assert result.is_valid

    def test_edges_with_existing_entities_pass(self):
        """Edges referencing existing entities pass."""
        validator = ManifestValidator(existing_entity_ids={"ent_existing"})
        edge = make_kg_edge_write("edge_001", "ent_existing", "ent_existing")

        r6 = make_r6_output(
            kg_writes=(edge,),
            outbox_events=(make_outbox_event(),),
            event_updates=(make_staged_event_update("e1"),),
        )
        result = validator.validate(r6, {"e1"})
        assert result.is_valid

    def test_orphan_source_detected(self, validator):
        """Orphan source_id is detected."""
        edge = make_kg_edge_write("edge_001", "orphan_source", "orphan_target")

        r6 = make_r6_output(
            kg_writes=(edge,),
            outbox_events=(make_outbox_event(),),
            event_updates=(make_staged_event_update("e1"),),
        )
        result = validator.validate(r6, {"e1"})

        assert not result.is_valid
        assert result.dlq_reason == "orphan_fk_reference"
        assert any("orphan_source" in e for e in result.errors)

    def test_orphan_target_detected(self, validator):
        """Orphan target_id is detected."""
        entity = make_kg_entity_write("ent_001")
        edge = make_kg_edge_write("edge_001", "ent_001", "orphan_target")

        r6 = make_r6_output(
            kg_writes=(entity, edge),
            outbox_events=(make_outbox_event(),),
            event_updates=(make_staged_event_update("e1"),),
        )
        result = validator.validate(r6, {"e1"})

        assert not result.is_valid
        assert any("orphan_target" in e for e in result.errors)


# =============================================================================
# TEST EVENT COVERAGE
# =============================================================================


class TestEventCoverage:
    """Tests for event coverage validation."""

    def test_all_events_covered_pass(self, validator):
        """All batch events having updates passes."""
        updates = (
            make_staged_event_update("e1"),
            make_staged_event_update("e2"),
        )
        r6 = make_r6_output(
            event_updates=updates,
            outbox_events=(make_outbox_event(),),
        )
        result = validator.validate(r6, {"e1", "e2"})
        assert result.is_valid

    def test_missing_event_fails(self, validator):
        """Missing event coverage fails validation."""
        updates = (make_staged_event_update("e1"),)
        r6 = make_r6_output(
            event_updates=updates,
            outbox_events=(make_outbox_event(),),
        )
        result = validator.validate(r6, {"e1", "e2", "e3"})

        assert not result.is_valid
        assert result.dlq_reason == "missing_event_coverage"
        assert any("Missing event coverage" in e for e in result.errors)


# =============================================================================
# TEST OUTBOX MINIMUM
# =============================================================================


class TestOutboxMinimum:
    """Tests for outbox event minimum validation."""

    def test_with_outbox_pass(self, validator):
        """With at least one outbox event passes."""
        r6 = make_r6_output(
            event_updates=(make_staged_event_update("e1"),),
            outbox_events=(make_outbox_event(),),
        )
        result = validator.validate(r6, {"e1"})
        assert result.is_valid

    def test_zero_outbox_fails(self, validator):
        """Zero outbox events fails validation."""
        r6 = make_r6_output(
            event_updates=(make_staged_event_update("e1"),),
            outbox_events=(),
        )
        result = validator.validate(r6, {"e1"})

        assert not result.is_valid
        assert result.dlq_reason == "zero_outbox_events"


# =============================================================================
# TEST DUPLICATE RECORDS
# =============================================================================


class TestDuplicateRecords:
    """Tests for duplicate record_id detection."""

    def test_unique_records_pass(self, validator):
        """Unique record_ids pass."""
        writes = [
            make_staged_write(record_id="rec_001", write_id="w1"),
            make_staged_write(record_id="rec_002", write_id="w2"),
        ]
        r6 = make_r6_output(
            truth_writes=tuple(writes),
            outbox_events=(make_outbox_event(),),
            event_updates=(make_staged_event_update("e1"),),
        )
        result = validator.validate(r6, {"e1"})
        assert result.is_valid

    def test_duplicate_in_same_layer_fails(self, validator):
        """Duplicate record_id in same layer fails."""
        writes = [
            make_staged_write(layer=LAYER_ST_EPI, record_id="rec_001", write_id="w1"),
            make_staged_write(layer=LAYER_ST_EPI, record_id="rec_001", write_id="w2"),
        ]
        r6 = make_r6_output(
            truth_writes=tuple(writes),
            outbox_events=(make_outbox_event(),),
            event_updates=(make_staged_event_update("e1"),),
        )
        result = validator.validate(r6, {"e1"})

        assert not result.is_valid
        assert result.dlq_reason == "duplicate_record_ids"

    def test_same_id_different_layers_ok(self, validator):
        """Same record_id in different layers is allowed."""
        writes = [
            make_staged_write(layer=LAYER_ST_EPI, record_id="rec_001", write_id="w1"),
            make_staged_write(
                layer=LAYER_ST_SEM,
                record_id="rec_001",
                write_id="w2",
                idempotency_key="R6:st_sem:rec_001",
            ),
        ]
        r6 = make_r6_output(
            truth_writes=tuple(writes),
            outbox_events=(make_outbox_event(),),
            event_updates=(make_staged_event_update("e1"),),
        )
        result = validator.validate(r6, {"e1"})
        assert result.is_valid


# =============================================================================
# TEST VERSION CONFLICTS
# =============================================================================


class TestVersionConflicts:
    """Tests for version conflict threshold."""

    def test_no_conflicts_pass(self, validator):
        """No version conflicts passes."""
        updates = tuple(make_staged_event_update(f"e{i}") for i in range(10))
        r6 = make_r6_output(
            event_updates=updates,
            outbox_events=(make_outbox_event(),),
        )
        result = validator.validate(r6, {f"e{i}" for i in range(10)})
        assert result.is_valid
        assert result.stats["version_conflicts"] == 0

    def test_under_threshold_pass_with_warning(self, validator):
        """Conflicts under 10% pass with warning."""
        # 1 conflict out of 20 = 5% < 10%
        updates = [make_staged_event_update(f"e{i}") for i in range(20)]
        updates[0] = make_staged_event_update("e0", version_conflict=True)
        r6 = make_r6_output(
            event_updates=tuple(updates),
            outbox_events=(make_outbox_event(),),
        )
        result = validator.validate(r6, {f"e{i}" for i in range(20)})

        assert result.is_valid
        assert len(result.warnings) == 1
        assert "conflicts detected" in result.warnings[0]

    def test_over_threshold_fails(self, validator):
        """Conflicts over 10% fails with DLQ."""
        # 3 conflicts out of 10 = 30% > 10%
        updates = [make_staged_event_update(f"e{i}") for i in range(10)]
        updates[0] = make_staged_event_update("e0", version_conflict=True)
        updates[1] = make_staged_event_update("e1", version_conflict=True)
        updates[2] = make_staged_event_update("e2", version_conflict=True)
        r6 = make_r6_output(
            event_updates=tuple(updates),
            outbox_events=(make_outbox_event(),),
        )
        result = validator.validate(r6, {f"e{i}" for i in range(10)})

        assert not result.is_valid
        assert result.dlq_reason == "version_conflict_threshold_exceeded"


# =============================================================================
# TEST STATS COMPUTATION
# =============================================================================


class TestStatsComputation:
    """Tests for stats computation."""

    def test_stats_computed(self, validator):
        """Stats are computed correctly."""
        writes = [
            make_staged_write(layer=LAYER_ST_EPI, record_id="r1", write_id="w1"),
            make_staged_write(
                layer=LAYER_ST_SEM,
                record_id="r2",
                write_id="w2",
                idempotency_key="R6:st_sem:r2",
            ),
        ]
        outbox = [
            make_outbox_event(topic="p03.consolidation.complete.v1", event_id="o1"),
            make_outbox_event(topic="p03.gap.detected.v1", event_id="o2"),
        ]
        updates = [make_staged_event_update("e1")]

        r6 = make_r6_output(
            truth_writes=tuple(writes),
            outbox_events=tuple(outbox),
            event_updates=tuple(updates),
        )
        result = validator.validate(r6, {"e1"})

        assert result.stats["total_writes"] == 2
        assert result.stats["outbox_events"] == 2
        assert result.stats["event_updates"] == 1
        assert result.stats["writes_by_layer"][LAYER_ST_EPI] == 1
        assert result.stats["writes_by_layer"][LAYER_ST_SEM] == 1


# =============================================================================
# TEST UTILITY FUNCTIONS
# =============================================================================


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_validate_r6_output(self):
        """validate_r6_output convenience function works."""
        r6 = make_r6_output(
            event_updates=(make_staged_event_update("e1"),),
            outbox_events=(make_outbox_event(),),
        )
        result = validate_r6_output(r6, {"e1"})
        assert result.is_valid

    def test_is_valid_manifest(self):
        """is_valid_manifest returns boolean."""
        r6 = make_r6_output(
            event_updates=(make_staged_event_update("e1"),),
            outbox_events=(make_outbox_event(),),
        )
        assert is_valid_manifest(r6, {"e1"}) is True

    def test_summarize_validation(self, validator):
        """summarize_validation returns summary dict."""
        r6 = make_r6_output(
            event_updates=(make_staged_event_update("e1"),),
            outbox_events=(make_outbox_event(),),
        )
        result = validator.validate(r6, {"e1"})
        summary = summarize_validation(result)

        assert summary["is_valid"] is True
        assert summary["error_count"] == 0
        assert summary["warning_count"] == 0
        assert summary["dlq_reason"] is None
