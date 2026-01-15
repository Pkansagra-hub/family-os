"""Tests for P03 Audit Logger.

Tests the audit logging functionality for consolidation decisions.

Spec Reference: Dossier §6.20, §14.10
Issue: 2.2.2
"""

from __future__ import annotations

import json

import pytest

from k0.pipelines.p03.audit_logger import (
    EXPLANATION_TEMPLATES,
    AuditAction,
    AuditRecord,
    P03AuditLogger,
    create_audit_logger,
    redact_pii_fields,
)

# =============================================================================
# TEST FIXTURES
# =============================================================================


@pytest.fixture
def audit_logger() -> P03AuditLogger:
    """Create a test audit logger."""
    return P03AuditLogger(
        space_id="sp_test_123",
        tenant_id="t_test_1",
        cycle_id="cyc_test_abc",
    )


# =============================================================================
# TEST AuditAction ENUM
# =============================================================================


class TestAuditAction:
    """Tests for AuditAction enum."""

    def test_all_actions_have_templates(self):
        """Verify every action has an explanation template."""
        for action in AuditAction:
            assert action in EXPLANATION_TEMPLATES, f"Missing template for {action}"

    def test_action_values_match_check_constraint(self):
        """Verify action values match st_consolidation_audit CHECK constraint."""
        expected_values = {
            "REINFORCE",
            "DECAY",
            "ARCHIVE",
            "MERGE",
            "CREATE",
            "EXTEND",
            "PRUNE",
            "SKIP",
            "CONTRADICT",
            "SCORE",  # Added in Issue 4.1.2 for importance scoring
        }
        actual_values = {action.value for action in AuditAction}
        assert actual_values == expected_values


# =============================================================================
# TEST PII REDACTION
# =============================================================================


class TestPiiRedaction:
    """Tests for PII redaction functionality."""

    def test_redact_removes_red_band_fields(self):
        """Verify RED-band fields are removed."""
        data = {
            "memory_id": "mem_123",
            "raw_content": "secret user data",
            "email": "user@example.com",
            "strength": 0.5,
        }
        redacted = redact_pii_fields(data)

        assert "memory_id" in redacted
        assert "strength" in redacted
        assert "raw_content" not in redacted
        assert "email" not in redacted

    def test_redact_case_insensitive(self):
        """Verify redaction is case-insensitive."""
        data = {
            "RAW_CONTENT": "should be removed",
            "Password": "secret",
            "safe_field": "ok",
        }
        redacted = redact_pii_fields(data)

        assert "safe_field" in redacted
        assert "RAW_CONTENT" not in redacted
        assert "Password" not in redacted

    def test_redact_empty_dict(self):
        """Verify empty dict returns empty dict."""
        assert redact_pii_fields({}) == {}

    def test_redact_no_pii(self):
        """Verify dict with no PII is unchanged."""
        data = {"a": 1, "b": "test", "c": [1, 2, 3]}
        redacted = redact_pii_fields(data)
        assert redacted == data


# =============================================================================
# TEST AuditRecord
# =============================================================================


class TestAuditRecord:
    """Tests for AuditRecord dataclass."""

    def test_default_values(self):
        """Verify default values are set correctly."""
        record = AuditRecord()

        assert record.audit_id  # Should be generated
        assert len(record.audit_id) == 26  # ULID length
        assert record.action == AuditAction.SKIP
        assert record.outcome_evaluated is False
        assert record.created_at > 0  # Should be current timestamp

    def test_generate_explanation_with_params(self):
        """Verify explanation generation with template params."""
        record = AuditRecord(
            action=AuditAction.REINFORCE,
            formula_used="hebbian_v2",
            confidence=0.85,
        )
        explanation = record.generate_explanation({"old_strength": 0.5, "new_strength": 0.7})

        assert "hebbian_v2" in explanation
        assert "0.85" in explanation
        assert "0.50" in explanation or "0.5" in explanation
        assert "0.70" in explanation or "0.7" in explanation

    def test_generate_explanation_missing_params(self):
        """Verify explanation handles missing params gracefully."""
        record = AuditRecord(
            memory_id="mem_123",
            action=AuditAction.CREATE,
        )
        # Missing initial_strength param
        explanation = record.generate_explanation({})

        # Should fall back to basic explanation
        assert "CREATE" in explanation or "mem_123" in explanation

    def test_to_db_row_redacts_pii(self):
        """Verify to_db_row redacts PII from inputs/outputs."""
        record = AuditRecord(
            memory_id="mem_123",
            source_table="st_epi",
            action=AuditAction.REINFORCE,
            space_id="sp_1",
            tenant_id="t_1",
            inputs={"strength": 0.5, "raw_content": "secret"},
            outputs={"new_strength": 0.7, "email": "user@test.com"},
        )
        row = record.to_db_row()

        # Parse JSON to verify redaction
        inputs_json = json.loads(row["inputs_json"])
        outputs_json = json.loads(row["outputs_json"])

        assert "strength" in inputs_json
        assert "raw_content" not in inputs_json
        assert "new_strength" in outputs_json
        assert "email" not in outputs_json

    def test_to_db_row_all_columns(self):
        """Verify to_db_row returns all 20 columns."""
        record = AuditRecord(
            memory_id="mem_123",
            source_table="st_epi",
            action=AuditAction.REINFORCE,
            space_id="sp_1",
            tenant_id="t_1",
        )
        row = record.to_db_row()

        expected_columns = {
            "audit_id",
            "memory_id",
            "source_table",
            "action",
            "formula_used",
            "formula_version",
            "inputs_json",
            "outputs_json",
            "explanation",
            "decision_id",
            "space_id",
            "tenant_id",
            "cycle_id",
            "confidence",
            "created_at",
            "threshold_used",
            "threshold_name",
            "outcome_evaluated",
            "outcome_success",
            "evaluated_at",
        }
        assert set(row.keys()) == expected_columns

    def test_action_serialized_as_string(self):
        """Verify action enum is serialized as string value."""
        record = AuditRecord(action=AuditAction.MERGE)
        row = record.to_db_row()
        assert row["action"] == "MERGE"


# =============================================================================
# TEST P03AuditLogger
# =============================================================================


class TestP03AuditLogger:
    """Tests for P03AuditLogger class."""

    def test_initialization(self, audit_logger: P03AuditLogger):
        """Verify logger initializes with correct context."""
        assert audit_logger.space_id == "sp_test_123"
        assert audit_logger.tenant_id == "t_test_1"
        assert audit_logger.cycle_id == "cyc_test_abc"
        assert audit_logger.record_count() == 0

    def test_log_decision_creates_record(self, audit_logger: P03AuditLogger):
        """Verify log_decision creates and stores a record."""
        record = audit_logger.log_decision(
            memory_id="mem_xyz",
            source_table="st_epi",
            action=AuditAction.REINFORCE,
            formula_used="hebbian_v2",
            confidence=0.85,
        )

        assert record.memory_id == "mem_xyz"
        assert record.source_table == "st_epi"
        assert record.action == AuditAction.REINFORCE
        assert record.formula_used == "hebbian_v2"
        assert record.confidence == 0.85
        assert record.space_id == "sp_test_123"
        assert record.tenant_id == "t_test_1"
        assert record.cycle_id == "cyc_test_abc"
        assert audit_logger.record_count() == 1

    def test_log_decision_idempotent(self, audit_logger: P03AuditLogger):
        """Verify logging same audit_id twice is idempotent."""
        fixed_id = "01HQTEST123456ABCDEFGH"

        record1 = audit_logger.log_decision(
            memory_id="mem_1",
            source_table="st_epi",
            action=AuditAction.CREATE,
            audit_id=fixed_id,
        )

        record2 = audit_logger.log_decision(
            memory_id="mem_1",
            source_table="st_epi",
            action=AuditAction.CREATE,
            audit_id=fixed_id,
        )

        # Should return same record, not create duplicate
        assert record1.audit_id == record2.audit_id
        assert audit_logger.record_count() == 1

    def test_log_multiple_decisions(self, audit_logger: P03AuditLogger):
        """Verify multiple decisions are tracked."""
        audit_logger.log_decision(
            memory_id="mem_1",
            source_table="st_epi",
            action=AuditAction.REINFORCE,
        )
        audit_logger.log_decision(
            memory_id="mem_2",
            source_table="st_kg_dom",
            action=AuditAction.CREATE,
        )
        audit_logger.log_decision(
            memory_id="mem_3",
            source_table="st_sem",
            action=AuditAction.DECAY,
        )

        assert audit_logger.record_count() == 3
        assert audit_logger.has_records() is True

    def test_get_pending_records(self, audit_logger: P03AuditLogger):
        """Verify get_pending_records returns copies."""
        audit_logger.log_decision(
            memory_id="mem_1",
            source_table="st_epi",
            action=AuditAction.REINFORCE,
        )

        records = audit_logger.get_pending_records()
        assert len(records) == 1
        assert records[0].memory_id == "mem_1"

    def test_get_pending_db_rows(self, audit_logger: P03AuditLogger):
        """Verify get_pending_db_rows returns database-ready dicts."""
        audit_logger.log_decision(
            memory_id="mem_1",
            source_table="st_epi",
            action=AuditAction.REINFORCE,
            inputs={"strength": 0.5},
        )

        rows = audit_logger.get_pending_db_rows()
        assert len(rows) == 1
        assert isinstance(rows[0], dict)
        assert rows[0]["memory_id"] == "mem_1"
        assert rows[0]["action"] == "REINFORCE"

    def test_clear_pending(self, audit_logger: P03AuditLogger):
        """Verify clear_pending removes all records."""
        audit_logger.log_decision(
            memory_id="mem_1",
            source_table="st_epi",
            action=AuditAction.REINFORCE,
        )
        audit_logger.log_decision(
            memory_id="mem_2",
            source_table="st_kg_dom",
            action=AuditAction.CREATE,
        )

        cleared = audit_logger.clear_pending()
        assert cleared == 2
        assert audit_logger.record_count() == 0
        assert audit_logger.has_records() is False

    def test_explanation_generated_automatically(self, audit_logger: P03AuditLogger):
        """Verify explanation is generated from template."""
        record = audit_logger.log_decision(
            memory_id="mem_1",
            source_table="st_epi",
            action=AuditAction.SKIP,
            template_params={"skip_reason": "duplicate event"},
        )

        assert record.explanation is not None
        assert "duplicate event" in record.explanation

    def test_pii_redacted_from_inputs(self, audit_logger: P03AuditLogger):
        """Verify PII is redacted from inputs in db rows."""
        audit_logger.log_decision(
            memory_id="mem_1",
            source_table="st_epi",
            action=AuditAction.REINFORCE,
            inputs={"strength": 0.5, "raw_content": "secret user message"},
        )

        rows = audit_logger.get_pending_db_rows()
        inputs_json = json.loads(rows[0]["inputs_json"])

        assert "strength" in inputs_json
        assert "raw_content" not in inputs_json


# =============================================================================
# TEST FACTORY FUNCTION
# =============================================================================


class TestCreateAuditLogger:
    """Tests for create_audit_logger factory function."""

    def test_creates_logger(self):
        """Verify factory creates configured logger."""
        logger = create_audit_logger(
            space_id="sp_1",
            tenant_id="t_1",
            cycle_id="cyc_1",
        )

        assert isinstance(logger, P03AuditLogger)
        assert logger.space_id == "sp_1"
        assert logger.tenant_id == "t_1"
        assert logger.cycle_id == "cyc_1"

    def test_creates_logger_without_cycle_id(self):
        """Verify factory works without cycle_id."""
        logger = create_audit_logger(
            space_id="sp_1",
            tenant_id="t_1",
        )

        assert logger.cycle_id is None


# =============================================================================
# TEST ALL DECISION TYPES
# =============================================================================


class TestAllDecisionTypes:
    """Verify at least one audit record per decision type works."""

    @pytest.fixture
    def logger(self) -> P03AuditLogger:
        return P03AuditLogger(
            space_id="sp_1",
            tenant_id="t_1",
            cycle_id="cyc_1",
        )

    @pytest.mark.parametrize("action", list(AuditAction))
    def test_decision_type(self, logger: P03AuditLogger, action: AuditAction):
        """Verify each decision type can be logged."""
        record = logger.log_decision(
            memory_id=f"mem_{action.value}",
            source_table="st_epi",
            action=action,
            confidence=0.75,
        )

        assert record.action == action
        assert record.explanation is not None
        row = record.to_db_row()
        assert row["action"] == action.value
