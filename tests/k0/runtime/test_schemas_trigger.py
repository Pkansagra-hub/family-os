"""
Tests for TriggerSpec and TriggerType schema models.

Issue 1.1.1: Create TriggerSpec Pydantic Model
ADR: ADR-K004 Capability Mesh Architecture
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from k0.runtime.schemas import TriggerSpec, TriggerType


class TestTriggerType:
    """Tests for TriggerType enum."""

    def test_phase1_types_available(self):
        """Verify Phase 1 trigger types are available."""
        assert TriggerType.INTERVAL == "interval"
        assert TriggerType.THRESHOLD == "threshold"
        assert TriggerType.MANUAL == "manual"

    def test_phase2_types_available(self):
        """Verify Phase 2 trigger types are available (for forward compatibility)."""
        assert TriggerType.CRON == "cron"
        assert TriggerType.IDLE == "idle"


class TestTriggerSpecInterval:
    """Tests for interval trigger specification."""

    def test_trigger_spec_interval_valid(self):
        """Valid interval trigger with all required fields."""
        trigger = TriggerSpec(
            id="embedding_indexer_interval",
            type=TriggerType.INTERVAL,
            interval_seconds=300,
        )
        assert trigger.id == "embedding_indexer_interval"
        assert trigger.type == TriggerType.INTERVAL
        assert trigger.interval_seconds == 300
        assert trigger.catch_up_enabled is True  # default

    def test_trigger_spec_interval_with_batch_size(self):
        """Interval trigger with optional batch_size."""
        trigger = TriggerSpec(
            id="batch_processor",
            type=TriggerType.INTERVAL,
            interval_seconds=60,
            batch_size=100,
        )
        assert trigger.batch_size == 100

    def test_trigger_spec_interval_missing_seconds_raises(self):
        """Interval trigger without interval_seconds raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            TriggerSpec(
                id="bad_interval",
                type=TriggerType.INTERVAL,
                # Missing interval_seconds
            )
        assert "interval_seconds required" in str(exc_info.value)

    def test_trigger_spec_interval_min_seconds(self):
        """Interval seconds must be at least 1."""
        with pytest.raises(ValidationError):
            TriggerSpec(
                id="too_fast",
                type=TriggerType.INTERVAL,
                interval_seconds=0,
            )

    def test_trigger_spec_interval_max_seconds(self):
        """Interval seconds must not exceed 86400 (1 day)."""
        with pytest.raises(ValidationError):
            TriggerSpec(
                id="too_slow",
                type=TriggerType.INTERVAL,
                interval_seconds=86401,
            )


class TestTriggerSpecThreshold:
    """Tests for threshold trigger specification."""

    def test_trigger_spec_threshold_valid(self):
        """Valid threshold trigger with all required fields."""
        trigger = TriggerSpec(
            id="embedding_indexer_threshold",
            type=TriggerType.THRESHOLD,
            table="st_vec",
            condition="status = 'READY'",
            threshold_count=50,
        )
        assert trigger.table == "st_vec"
        assert trigger.condition == "status = 'READY'"
        assert trigger.threshold_count == 50
        assert trigger.check_interval_seconds == 60  # default

    def test_trigger_spec_threshold_custom_check_interval(self):
        """Threshold trigger with custom check interval."""
        trigger = TriggerSpec(
            id="fast_check",
            type=TriggerType.THRESHOLD,
            table="st_outbox",
            threshold_count=10,
            check_interval_seconds=5,
        )
        assert trigger.check_interval_seconds == 5

    def test_trigger_spec_threshold_missing_table_raises(self):
        """Threshold trigger without table raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            TriggerSpec(
                id="bad_threshold",
                type=TriggerType.THRESHOLD,
                threshold_count=50,
                # Missing table
            )
        assert "table required" in str(exc_info.value)

    def test_trigger_spec_threshold_missing_count_raises(self):
        """Threshold trigger without threshold_count raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            TriggerSpec(
                id="bad_threshold",
                type=TriggerType.THRESHOLD,
                table="st_vec",
                # Missing threshold_count
            )
        assert "threshold_count required" in str(exc_info.value)


class TestTriggerSpecCron:
    """Tests for cron trigger specification (Phase 2)."""

    def test_trigger_spec_cron_valid(self):
        """Valid cron trigger with expression."""
        trigger = TriggerSpec(
            id="nightly_consolidation",
            type=TriggerType.CRON,
            cron_expression="0 2 * * *",
        )
        assert trigger.cron_expression == "0 2 * * *"

    def test_trigger_spec_cron_missing_expression_raises(self):
        """Cron trigger without cron_expression raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            TriggerSpec(
                id="bad_cron",
                type=TriggerType.CRON,
                # Missing cron_expression
            )
        assert "cron_expression required" in str(exc_info.value)


class TestTriggerSpecIdle:
    """Tests for idle trigger specification (Phase 2)."""

    def test_trigger_spec_idle_valid(self):
        """Valid idle trigger with idle_seconds."""
        trigger = TriggerSpec(
            id="idle_processor",
            type=TriggerType.IDLE,
            idle_seconds=30,
        )
        assert trigger.idle_seconds == 30
        assert trigger.min_pending == 1  # default

    def test_trigger_spec_idle_with_min_pending(self):
        """Idle trigger with custom min_pending."""
        trigger = TriggerSpec(
            id="idle_batch",
            type=TriggerType.IDLE,
            idle_seconds=60,
            min_pending=10,
        )
        assert trigger.min_pending == 10

    def test_trigger_spec_idle_missing_seconds_raises(self):
        """Idle trigger without idle_seconds raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            TriggerSpec(
                id="bad_idle",
                type=TriggerType.IDLE,
                # Missing idle_seconds
            )
        assert "idle_seconds required" in str(exc_info.value)


class TestTriggerSpecManual:
    """Tests for manual trigger specification."""

    def test_trigger_spec_manual_valid(self):
        """Valid manual trigger with minimal fields."""
        trigger = TriggerSpec(
            id="manual_consolidation",
            type=TriggerType.MANUAL,
        )
        assert trigger.id == "manual_consolidation"
        assert trigger.type == TriggerType.MANUAL

    def test_trigger_spec_manual_with_batch_size(self):
        """Manual trigger with optional batch_size."""
        trigger = TriggerSpec(
            id="manual_batch",
            type=TriggerType.MANUAL,
            batch_size=500,
        )
        assert trigger.batch_size == 500


class TestTriggerSpecValidation:
    """Tests for TriggerSpec general validation."""

    def test_trigger_spec_invalid_type_raises(self):
        """Invalid trigger type raises ValidationError."""
        with pytest.raises(ValidationError):
            TriggerSpec(
                id="bad_trigger",
                type="unknown",  # type: ignore
            )

    def test_trigger_spec_id_pattern(self):
        """Trigger ID must match pattern ^[a-z0-9_]+$."""
        # Valid
        trigger = TriggerSpec(
            id="valid_id_123",
            type=TriggerType.MANUAL,
        )
        assert trigger.id == "valid_id_123"

        # Invalid - uppercase
        with pytest.raises(ValidationError):
            TriggerSpec(
                id="Invalid_ID",
                type=TriggerType.MANUAL,
            )

        # Invalid - hyphen
        with pytest.raises(ValidationError):
            TriggerSpec(
                id="invalid-id",
                type=TriggerType.MANUAL,
            )

    def test_trigger_spec_catch_up_disabled(self):
        """catch_up_enabled can be set to False."""
        trigger = TriggerSpec(
            id="no_catchup",
            type=TriggerType.INTERVAL,
            interval_seconds=300,
            catch_up_enabled=False,
        )
        assert trigger.catch_up_enabled is False
