"""
Unit tests for ReconciliationRecorder — Issue 5.1.4

Tests the reconciliation decision recording for audit trail and
st_hipp_events.reconciliation_json population.

Spec Reference:
    - Dossier §4.7.3 (Reconciliation Decision Recording)
    - M5_EXECUTION.md Issue 5.1.4
"""

from __future__ import annotations

import json

import pytest

from k0.modules.consolidation.staging.reconciliation_recorder import (
    ReconciliationRecord,
    ReconciliationRecorder,
    parse_reconciliation_json,
    summarize_decisions,
)
from k0.pipelines.p03.event_state import P03EventState, ReconciliationAction

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def recorder() -> ReconciliationRecorder:
    """Provide a ReconciliationRecorder with fixed timestamp."""
    return ReconciliationRecorder(timestamp_provider=lambda: 1735689600000)


def make_event(
    event_id: str = "evt_001",
    action: ReconciliationAction = ReconciliationAction.CREATE,
    match_id: str | None = None,
    match_layer: str | None = None,
    similarity: float = 0.0,
    confidence: float = 0.9,
    reason: str = "Test reason",
) -> P03EventState:
    """Factory to create P03EventState with reconciliation fields."""
    event = P03EventState(event_id=event_id)
    event.set_reconciliation(
        action=action,
        match_id=match_id,
        match_layer=match_layer,
        similarity=similarity,
        confidence=confidence,
        reason=reason,
    )
    return event


# =============================================================================
# Test: ReconciliationRecord Dataclass
# =============================================================================


class TestReconciliationRecord:
    """Tests for ReconciliationRecord dataclass."""

    def test_create_with_all_fields(self):
        """Create record with all fields populated."""
        record = ReconciliationRecord(
            event_id="evt_001",
            reconciliation_action="REINFORCE",
            best_match_id="epi-001",
            best_match_layer="st_epi",
            similarity_score=0.89,
            confidence=0.92,
            reconciliation_reason="High similarity match",
            decision_timestamp_ms=1735689600000,
        )

        assert record.event_id == "evt_001"
        assert record.reconciliation_action == "REINFORCE"
        assert record.best_match_id == "epi-001"
        assert record.best_match_layer == "st_epi"
        assert record.similarity_score == 0.89
        assert record.confidence == 0.92
        assert record.decision_timestamp_ms == 1735689600000

    def test_create_for_new_record(self):
        """Create record for CREATE action (no match)."""
        record = ReconciliationRecord(
            event_id="evt_002",
            reconciliation_action="CREATE",
            best_match_id=None,
            best_match_layer=None,
            similarity_score=0.0,
            confidence=0.85,
            reconciliation_reason="No matching pattern found",
            decision_timestamp_ms=1735689600000,
        )

        assert record.best_match_id is None
        assert record.best_match_layer is None

    def test_validates_action(self):
        """Invalid action should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid reconciliation_action"):
            ReconciliationRecord(
                event_id="evt_001",
                reconciliation_action="INVALID_ACTION",
                best_match_id=None,
                best_match_layer=None,
                similarity_score=0.0,
                confidence=0.0,
                reconciliation_reason="",
                decision_timestamp_ms=0,
            )

    def test_clamps_similarity_score(self):
        """Similarity score should be clamped to [0, 1]."""
        record = ReconciliationRecord(
            event_id="evt_001",
            reconciliation_action="REINFORCE",
            best_match_id="epi-001",
            best_match_layer="st_epi",
            similarity_score=1.5,  # Above max
            confidence=0.9,
            reconciliation_reason="Test",
            decision_timestamp_ms=0,
        )

        assert record.similarity_score == 1.0

    def test_clamps_confidence(self):
        """Confidence should be clamped to [0, 1]."""
        record = ReconciliationRecord(
            event_id="evt_001",
            reconciliation_action="CREATE",
            best_match_id=None,
            best_match_layer=None,
            similarity_score=0.0,
            confidence=-0.5,  # Below min
            reconciliation_reason="Test",
            decision_timestamp_ms=0,
        )

        assert record.confidence == 0.0

    def test_to_dict(self):
        """to_dict() produces correct structure."""
        record = ReconciliationRecord(
            event_id="evt_001",
            reconciliation_action="EXTEND",
            best_match_id="sem-001",
            best_match_layer="st_sem",
            similarity_score=0.756789,
            confidence=0.823456,
            reconciliation_reason="Pattern extended",
            decision_timestamp_ms=1735689600000,
        )

        d = record.to_dict()

        assert d["action"] == "EXTEND"
        assert d["match_id"] == "sem-001"
        assert d["match_layer"] == "st_sem"
        assert d["similarity"] == 0.7568  # Rounded to 4 decimals
        assert d["confidence"] == 0.8235  # Rounded to 4 decimals
        assert d["reason"] == "Pattern extended"
        assert d["decided_at_ms"] == 1735689600000

    def test_to_json(self):
        """to_json() produces valid compact JSON."""
        record = ReconciliationRecord(
            event_id="evt_001",
            reconciliation_action="CREATE",
            best_match_id=None,
            best_match_layer=None,
            similarity_score=0.0,
            confidence=0.9,
            reconciliation_reason="New pattern",
            decision_timestamp_ms=1735689600000,
        )

        json_str = record.to_json()

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed["action"] == "CREATE"

        # Should be compact (no spaces)
        assert " " not in json_str.replace("New pattern", "")


# =============================================================================
# Test: ReconciliationRecorder.record
# =============================================================================


class TestRecorderRecord:
    """Tests for record() method."""

    def test_record_reinforce_action(self, recorder: ReconciliationRecorder):
        """Record REINFORCE action with match."""
        event = make_event(
            action=ReconciliationAction.REINFORCE,
            match_id="epi-001",
            match_layer="st_epi",
            similarity=0.92,
            confidence=0.95,
            reason="Strong match to existing episode",
        )

        record = recorder.record(event)

        assert record.event_id == "evt_001"
        assert record.reconciliation_action == "REINFORCE"
        assert record.best_match_id == "epi-001"
        assert record.best_match_layer == "st_epi"
        assert record.similarity_score == 0.92
        assert record.confidence == 0.95
        assert record.decision_timestamp_ms == 1735689600000

    def test_record_create_action(self, recorder: ReconciliationRecorder):
        """Record CREATE action (no match)."""
        event = make_event(
            action=ReconciliationAction.CREATE,
            match_id=None,
            match_layer=None,
            similarity=0.0,
            confidence=0.8,
            reason="No matching truth record",
        )

        record = recorder.record(event)

        assert record.reconciliation_action == "CREATE"
        assert record.best_match_id is None
        assert record.best_match_layer is None

    def test_record_with_explicit_timestamp(self, recorder: ReconciliationRecorder):
        """Record with explicit timestamp override."""
        event = make_event()

        record = recorder.record(event, timestamp_ms=9999999999999)

        assert record.decision_timestamp_ms == 9999999999999

    @pytest.mark.parametrize("action", list(ReconciliationAction))
    def test_record_all_actions(
        self,
        recorder: ReconciliationRecorder,
        action: ReconciliationAction,
    ):
        """All 8 ReconciliationAction values can be recorded."""
        event = make_event(action=action)

        record = recorder.record(event)

        assert record.reconciliation_action == action.value


# =============================================================================
# Test: ReconciliationRecorder.record_batch
# =============================================================================


class TestRecorderRecordBatch:
    """Tests for record_batch() method."""

    def test_record_batch_returns_dict(self, recorder: ReconciliationRecorder):
        """record_batch returns dict mapping event_id to record."""
        events = [
            make_event(event_id="evt_001", action=ReconciliationAction.CREATE),
            make_event(
                event_id="evt_002", action=ReconciliationAction.REINFORCE, match_id="epi-001"
            ),
            make_event(event_id="evt_003", action=ReconciliationAction.SKIP),
        ]

        records = recorder.record_batch(events)

        assert len(records) == 3
        assert "evt_001" in records
        assert "evt_002" in records
        assert "evt_003" in records
        assert records["evt_001"].reconciliation_action == "CREATE"
        assert records["evt_002"].reconciliation_action == "REINFORCE"
        assert records["evt_003"].reconciliation_action == "SKIP"

    def test_batch_same_timestamp(self, recorder: ReconciliationRecorder):
        """All records in batch get the same timestamp."""
        events = [
            make_event(event_id="evt_001"),
            make_event(event_id="evt_002"),
        ]

        records = recorder.record_batch(events)

        ts1 = records["evt_001"].decision_timestamp_ms
        ts2 = records["evt_002"].decision_timestamp_ms
        assert ts1 == ts2


# =============================================================================
# Test: ReconciliationRecorder.to_json
# =============================================================================


class TestRecorderToJson:
    """Tests for JSON serialization."""

    def test_to_json_compact(self, recorder: ReconciliationRecorder):
        """to_json produces compact JSON."""
        event = make_event()
        record = recorder.record(event)

        json_str = recorder.to_json(record)

        assert "action" in json_str
        # Compact format has no spaces after colons/commas
        assert ": " not in json_str

    def test_batch_to_json(self, recorder: ReconciliationRecorder):
        """batch_to_json produces dict of JSON strings."""
        events = [
            make_event(event_id="evt_001"),
            make_event(event_id="evt_002"),
        ]
        records = recorder.record_batch(events)

        json_dict = recorder.batch_to_json(records)

        assert len(json_dict) == 2
        assert isinstance(json_dict["evt_001"], str)
        # Verify parseable
        parsed = json.loads(json_dict["evt_001"])
        assert "action" in parsed


# =============================================================================
# Test: ReconciliationRecorder.validate_record
# =============================================================================


class TestRecorderValidation:
    """Tests for validate_record() method."""

    def test_valid_reinforce_record(self, recorder: ReconciliationRecorder):
        """Valid REINFORCE record passes validation."""
        event = make_event(
            action=ReconciliationAction.REINFORCE,
            match_id="epi-001",
            match_layer="st_epi",
            similarity=0.9,
            confidence=0.95,
            reason="Good match",
        )
        record = recorder.record(event)

        warnings = recorder.validate_record(record)

        assert warnings == []

    def test_reinforce_without_match_warns(self, recorder: ReconciliationRecorder):
        """REINFORCE without match_id generates warning."""
        record = ReconciliationRecord(
            event_id="evt_001",
            reconciliation_action="REINFORCE",
            best_match_id=None,  # Missing!
            best_match_layer=None,  # Missing!
            similarity_score=0.0,  # Zero!
            confidence=0.9,
            reconciliation_reason="Test",
            decision_timestamp_ms=0,
        )

        warnings = recorder.validate_record(record)

        assert len(warnings) >= 2
        assert any("best_match_id" in w for w in warnings)

    def test_create_with_match_warns(self, recorder: ReconciliationRecorder):
        """CREATE with match_id generates warning."""
        record = ReconciliationRecord(
            event_id="evt_001",
            reconciliation_action="CREATE",
            best_match_id="spurious-001",  # Should not be present
            best_match_layer=None,
            similarity_score=0.0,
            confidence=0.9,
            reconciliation_reason="New pattern",
            decision_timestamp_ms=0,
        )

        warnings = recorder.validate_record(record)

        assert any("CREATE" in w and "best_match_id" in w for w in warnings)

    def test_missing_reason_warns(self, recorder: ReconciliationRecorder):
        """Missing reason generates warning."""
        record = ReconciliationRecord(
            event_id="evt_001",
            reconciliation_action="CREATE",
            best_match_id=None,
            best_match_layer=None,
            similarity_score=0.0,
            confidence=0.9,
            reconciliation_reason="",  # Empty!
            decision_timestamp_ms=0,
        )

        warnings = recorder.validate_record(record)

        assert any("reason" in w.lower() for w in warnings)


# =============================================================================
# Test: Utility Functions
# =============================================================================


class TestUtilityFunctions:
    """Tests for module-level utility functions."""

    def test_parse_reconciliation_json(self):
        """Parse JSON back to ReconciliationRecord."""
        json_str = '{"action":"REINFORCE","match_id":"epi-001","match_layer":"st_epi","similarity":0.89,"confidence":0.92,"reason":"Match found","decided_at_ms":1735689600000}'

        record = parse_reconciliation_json(json_str)

        assert record.reconciliation_action == "REINFORCE"
        assert record.best_match_id == "epi-001"
        assert record.best_match_layer == "st_epi"
        assert record.similarity_score == 0.89
        assert record.confidence == 0.92
        assert record.decision_timestamp_ms == 1735689600000

    def test_parse_json_with_nulls(self):
        """Parse JSON with null values."""
        json_str = '{"action":"CREATE","match_id":null,"match_layer":null,"similarity":0,"confidence":0.8,"reason":"New","decided_at_ms":0}'

        record = parse_reconciliation_json(json_str)

        assert record.best_match_id is None
        assert record.best_match_layer is None

    def test_summarize_decisions(self):
        """Summarize counts by action."""
        records = {
            "evt_001": ReconciliationRecord("evt_001", "CREATE", None, None, 0, 0.9, "r1", 0),
            "evt_002": ReconciliationRecord("evt_002", "CREATE", None, None, 0, 0.9, "r2", 0),
            "evt_003": ReconciliationRecord(
                "evt_003", "REINFORCE", "m1", "st_epi", 0.9, 0.9, "r3", 0
            ),
            "evt_004": ReconciliationRecord("evt_004", "SKIP", None, None, 0, 0, "r4", 0),
        }

        counts = summarize_decisions(records)

        assert counts["CREATE"] == 2
        assert counts["REINFORCE"] == 1
        assert counts["SKIP"] == 1


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_special_characters_in_reason(self, recorder: ReconciliationRecorder):
        """Reason with special characters serializes correctly."""
        event = make_event(reason='Quote: "test" and backslash: \\')
        record = recorder.record(event)

        json_str = record.to_json()
        parsed = json.loads(json_str)

        assert 'Quote: "test"' in parsed["reason"]

    def test_empty_event_id(self, recorder: ReconciliationRecorder):
        """Empty event_id from parse is handled."""
        json_str = '{"action":"CREATE","match_id":null,"match_layer":null,"similarity":0,"confidence":0.8,"reason":"New","decided_at_ms":0}'

        record = parse_reconciliation_json(json_str)

        # Parsed record has empty event_id (not stored in JSON)
        assert record.event_id == ""

    def test_contradict_action(self, recorder: ReconciliationRecorder):
        """CONTRADICT action is recorded correctly."""
        event = make_event(
            action=ReconciliationAction.CONTRADICT,
            match_id="sem-001",
            match_layer="st_sem",
            similarity=0.6,
            confidence=0.7,
            reason="Conflicting information detected",
        )

        record = recorder.record(event)

        assert record.reconciliation_action == "CONTRADICT"
        assert record.best_match_id == "sem-001"
