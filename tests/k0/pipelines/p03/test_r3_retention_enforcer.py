"""
Tests for RetentionEnforcer.

Issue: 4.3.4
Spec Reference: M4_EXECUTION.md, Dossier 4.4.1.2
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from k0.modules.consolidation.algorithms.decay_engine import (
    MS_PER_DAY,
    DecayClassification,
    DecayConfig,
    UnifiedDecayEngine,
)
from k0.modules.consolidation.algorithms.retention_enforcer import (
    RESURRECTION_ALERT_THRESHOLD,
    RESURRECTION_BASE,
    RESURRECTION_CARRY,
    RESURRECTION_FLOOR,
    ResurrectionResult,
    ResurrectionTrigger,
    RetentionDecision,
    RetentionEnforcer,
)

if TYPE_CHECKING:
    pass


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def enforcer() -> RetentionEnforcer:
    """Default enforcer fixture."""
    return RetentionEnforcer()


@pytest.fixture
def custom_enforcer() -> RetentionEnforcer:
    """Enforcer with custom decay config."""
    config = DecayConfig(
        archive_threshold=0.15,
        tombstone_threshold=0.02,
    )
    engine = UnifiedDecayEngine(config)
    return RetentionEnforcer(decay_engine=engine)


@pytest.fixture
def logger() -> logging.Logger:
    """Logger fixture for testing log output."""
    return logging.getLogger("test_retention")


# =============================================================================
# 4.3.4.T1: Retention Decision Tests
# =============================================================================


class TestRetentionDecision:
    """Test retention decision evaluation."""

    def test_active_record_keeps(self, enforcer: RetentionEnforcer) -> None:
        """Active record (high decay) → KEEP."""
        now = 1700000000000
        recent = now - (7 * MS_PER_DAY)  # 7 days ago

        result = enforcer.evaluate(
            entity_id="mem_123",
            table_name="st_epi",
            last_observed_at=recent,
            current_time=now,
        )

        assert result.decision == RetentionDecision.KEEP
        assert result.classification == DecayClassification.ACTIVE
        assert result.current_decay > 0.5

    def test_archive_candidate_archives(self, enforcer: RetentionEnforcer) -> None:
        """Archive candidate (low decay) → ARCHIVE."""
        now = 1700000000000
        # For st_epi with λ=0.005 and reinforcement factor
        # Need to be below 0.10 archive threshold
        # decay = exp(-0.00455 × days) < 0.10
        # days > ln(10) / 0.00455 ≈ 507 days
        old = now - (600 * MS_PER_DAY)

        result = enforcer.evaluate(
            entity_id="mem_456",
            table_name="st_epi",
            last_observed_at=old,
            current_time=now,
        )

        assert result.decision == RetentionDecision.ARCHIVE
        assert result.classification == DecayClassification.ARCHIVE_CANDIDATE
        assert 0.01 <= result.current_decay < 0.10

    def test_prune_candidate_tombstones(self, enforcer: RetentionEnforcer) -> None:
        """Prune candidate (very low decay) → TOMBSTONE."""
        now = 1700000000000
        # Need decay < 0.01 (tombstone threshold)
        # For st_hipp_events with λ=0.100
        # decay = exp(-0.0909 × days) < 0.01
        # days > ln(100) / 0.0909 ≈ 50.7 days
        very_old = now - (60 * MS_PER_DAY)

        result = enforcer.evaluate(
            entity_id="mem_789",
            table_name="st_hipp_events",
            last_observed_at=very_old,
            current_time=now,
        )

        assert result.decision == RetentionDecision.TOMBSTONE
        assert result.classification == DecayClassification.PRUNE_CANDIDATE
        assert result.current_decay < 0.01

    def test_already_archived_keeps(self, enforcer: RetentionEnforcer) -> None:
        """Already archived record → KEEP (no re-archive)."""
        now = 1700000000000
        old = now - (600 * MS_PER_DAY)

        result = enforcer.evaluate(
            entity_id="mem_archived",
            table_name="st_epi",
            last_observed_at=old,
            current_time=now,
            current_status="ARCHIVED",
        )

        # Should keep (already archived), not re-archive
        assert result.decision == RetentionDecision.KEEP
        assert "Already archived" in result.reason

    def test_already_tombstoned_keeps(self, enforcer: RetentionEnforcer) -> None:
        """Already tombstoned record → KEEP (no re-tombstone)."""
        now = 1700000000000
        very_old = now - (100 * MS_PER_DAY)

        result = enforcer.evaluate(
            entity_id="mem_tomb",
            table_name="st_hipp_events",
            last_observed_at=very_old,
            current_time=now,
            current_status="TOMBSTONE",
        )

        assert result.decision == RetentionDecision.KEEP
        assert "Already tombstoned" in result.reason


class TestRetentionResultFields:
    """Test RetentionResult contains correct fields."""

    def test_result_has_entity_id(self, enforcer: RetentionEnforcer) -> None:
        """Result includes entity_id."""
        result = enforcer.evaluate(
            entity_id="test_entity",
            table_name="st_epi",
            last_observed_at=1700000000000,
            current_time=1700000000000,
        )
        assert result.entity_id == "test_entity"

    def test_result_has_table_name(self, enforcer: RetentionEnforcer) -> None:
        """Result includes table_name."""
        result = enforcer.evaluate(
            entity_id="test",
            table_name="st_sem",
            last_observed_at=1700000000000,
            current_time=1700000000000,
        )
        assert result.table_name == "st_sem"

    def test_result_has_days_since_access(self, enforcer: RetentionEnforcer) -> None:
        """Result includes days_since_access."""
        now = 1700000000000
        ten_days_ago = now - (10 * MS_PER_DAY)

        result = enforcer.evaluate(
            entity_id="test",
            table_name="st_epi",
            last_observed_at=ten_days_ago,
            current_time=now,
        )

        assert abs(result.days_since_access - 10.0) < 0.001

    def test_result_has_importance_score(self, enforcer: RetentionEnforcer) -> None:
        """Result includes importance_score."""
        result = enforcer.evaluate(
            entity_id="test",
            table_name="st_epi",
            last_observed_at=1700000000000,
            current_time=1700000000000,
            importance_score=0.85,
        )
        assert result.importance_score == 0.85


# =============================================================================
# 4.3.4.T2: Resurrection Formula Tests
# =============================================================================


class TestResurrectionFormula:
    """Test resurrection decay formula: max(0.70, 0.50 + old_decay × 0.50)."""

    def test_resurrection_constants(self) -> None:
        """Verify resurrection constants from spec."""
        assert RESURRECTION_FLOOR == 0.70
        assert RESURRECTION_BASE == 0.50
        assert RESURRECTION_CARRY == 0.50

    def test_zero_decay_resurrects_to_floor(self, enforcer: RetentionEnforcer) -> None:
        """decay=0.0 → new_decay = max(0.70, 0.50) = 0.70."""
        new_decay = enforcer.compute_resurrection_decay(0.0)
        assert new_decay == 0.70

    def test_low_decay_resurrects_to_floor(self, enforcer: RetentionEnforcer) -> None:
        """decay=0.05 → new_decay = max(0.70, 0.50 + 0.025) = 0.70."""
        new_decay = enforcer.compute_resurrection_decay(0.05)
        assert new_decay == 0.70

    def test_mid_decay_resurrects_above_floor(self, enforcer: RetentionEnforcer) -> None:
        """decay=0.50 → new_decay = max(0.70, 0.50 + 0.25) = 0.75."""
        new_decay = enforcer.compute_resurrection_decay(0.50)
        expected = RESURRECTION_BASE + 0.50 * RESURRECTION_CARRY
        assert abs(new_decay - expected) < 0.001
        assert new_decay == 0.75

    def test_high_decay_preserves_some(self, enforcer: RetentionEnforcer) -> None:
        """decay=0.80 → new_decay = 0.50 + 0.40 = 0.90."""
        new_decay = enforcer.compute_resurrection_decay(0.80)
        expected = 0.50 + 0.80 * 0.50
        assert abs(new_decay - expected) < 0.001
        assert new_decay == 0.90

    def test_full_decay_caps_at_one(self, enforcer: RetentionEnforcer) -> None:
        """decay=1.0 → new_decay = min(1.0, 0.50 + 0.50) = 1.0."""
        new_decay = enforcer.compute_resurrection_decay(1.0)
        assert new_decay == 1.0


# =============================================================================
# 4.3.4.T3: Resurrection Process Tests
# =============================================================================


class TestResurrectionProcess:
    """Test resurrection of archived/tombstoned records."""

    def test_resurrect_archived_record(self, enforcer: RetentionEnforcer) -> None:
        """Resurrect archived record with EXPLICIT_ACCESS trigger."""
        result = enforcer.resurrect(
            entity_id="mem_old",
            table_name="st_epi",
            current_decay=0.05,
            current_status="ARCHIVED",
            trigger=ResurrectionTrigger.EXPLICIT_ACCESS,
            current_time=1700000000000,
        )

        assert result.entity_id == "mem_old"
        assert result.table_name == "st_epi"
        assert result.trigger == ResurrectionTrigger.EXPLICIT_ACCESS
        assert result.old_decay == 0.05
        assert result.new_decay == 0.70  # Floor
        assert result.old_status == "ARCHIVED"
        assert result.new_status == "ACTIVE"
        assert result.resurrection_count == 1

    def test_resurrect_tombstoned_record(self, enforcer: RetentionEnforcer) -> None:
        """Resurrect tombstoned record with SEARCH_RESULT trigger."""
        result = enforcer.resurrect(
            entity_id="mem_tomb",
            table_name="st_sem",
            current_decay=0.001,
            current_status="TOMBSTONE",
            trigger=ResurrectionTrigger.SEARCH_RESULT,
            current_time=1700000000000,
        )

        assert result.old_status == "TOMBSTONE"
        assert result.new_status == "ACTIVE"
        assert result.new_decay == 0.70

    def test_all_trigger_types(self, enforcer: RetentionEnforcer) -> None:
        """All resurrection triggers work correctly."""
        triggers = [
            ResurrectionTrigger.EXPLICIT_ACCESS,
            ResurrectionTrigger.ASSOCIATION_HIT,
            ResurrectionTrigger.SEARCH_RESULT,
            ResurrectionTrigger.CONSOLIDATION_RESCUE,
        ]

        for trigger in triggers:
            result = enforcer.resurrect(
                entity_id=f"mem_{trigger.value}",
                table_name="st_epi",
                current_decay=0.03,
                current_status="ARCHIVED",
                trigger=trigger,
                current_time=1700000000000,
            )
            assert result.trigger == trigger
            assert result.new_status == "ACTIVE"


class TestResurrectionCounting:
    """Test resurrection count tracking and alerting."""

    def test_resurrection_count_increments(self, enforcer: RetentionEnforcer) -> None:
        """Each resurrection increments count."""
        entity_id = "mem_counting"
        table_name = "st_epi"

        for i in range(1, 4):
            result = enforcer.resurrect(
                entity_id=entity_id,
                table_name=table_name,
                current_decay=0.05,
                current_status="ARCHIVED",
                trigger=ResurrectionTrigger.EXPLICIT_ACCESS,
                current_time=1700000000000 + i * 1000,
            )
            assert result.resurrection_count == i

    def test_resurrection_count_getter(self, enforcer: RetentionEnforcer) -> None:
        """get_resurrection_count returns correct count."""
        entity_id = "mem_get_count"
        table_name = "st_sem"

        # Initially 0
        assert enforcer.get_resurrection_count(entity_id, table_name) == 0

        # After resurrections
        for _ in range(2):
            enforcer.resurrect(
                entity_id=entity_id,
                table_name=table_name,
                current_decay=0.05,
                current_status="ARCHIVED",
                trigger=ResurrectionTrigger.SEARCH_RESULT,
            )

        assert enforcer.get_resurrection_count(entity_id, table_name) == 2

    def test_resurrection_count_reset(self, enforcer: RetentionEnforcer) -> None:
        """reset_resurrection_count clears count."""
        entity_id = "mem_reset"
        table_name = "st_epi"

        # Create some resurrections
        for _ in range(3):
            enforcer.resurrect(
                entity_id=entity_id,
                table_name=table_name,
                current_decay=0.05,
                current_status="ARCHIVED",
                trigger=ResurrectionTrigger.EXPLICIT_ACCESS,
            )

        assert enforcer.get_resurrection_count(entity_id, table_name) == 3

        # Reset
        enforcer.reset_resurrection_count(entity_id, table_name)
        assert enforcer.get_resurrection_count(entity_id, table_name) == 0

    def test_alert_threshold_constant(self) -> None:
        """Verify alert threshold from spec."""
        assert RESURRECTION_ALERT_THRESHOLD == 3

    def test_high_resurrection_count_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Logs warning when resurrection count >= threshold."""
        enforcer = RetentionEnforcer()
        entity_id = "mem_alert"
        table_name = "st_epi"

        with caplog.at_level(logging.WARNING):
            # Resurrect threshold times
            for _ in range(RESURRECTION_ALERT_THRESHOLD):
                enforcer.resurrect(
                    entity_id=entity_id,
                    table_name=table_name,
                    current_decay=0.05,
                    current_status="ARCHIVED",
                    trigger=ResurrectionTrigger.EXPLICIT_ACCESS,
                )

        # Should have logged a warning
        assert "High resurrection count" in caplog.text
        assert entity_id in caplog.text


# =============================================================================
# 4.3.4.T4: Batch Evaluation Tests
# =============================================================================


class TestBatchEvaluation:
    """Test batch retention evaluation."""

    def test_empty_batch(self, enforcer: RetentionEnforcer) -> None:
        """Empty batch returns zero counts."""
        result = enforcer.evaluate_batch([], current_time=1700000000000)

        assert result.total_evaluated == 0
        assert result.keep_count == 0
        assert result.archive_count == 0
        assert result.tombstone_count == 0
        assert result.results == []

    def test_mixed_decisions_batch(self, enforcer: RetentionEnforcer) -> None:
        """Batch with mixed decisions counts correctly."""
        now = 1700000000000

        records = [
            # Recent → KEEP
            {
                "entity_id": "mem_1",
                "table_name": "st_epi",
                "last_observed_at": now - (7 * MS_PER_DAY),
            },
            # Very old (st_hipp_events) → ARCHIVE
            {
                "entity_id": "mem_2",
                "table_name": "st_hipp_events",
                "last_observed_at": now - (30 * MS_PER_DAY),
            },
            # Extremely old (st_hipp_events) → TOMBSTONE
            {
                "entity_id": "mem_3",
                "table_name": "st_hipp_events",
                "last_observed_at": now - (60 * MS_PER_DAY),
            },
        ]

        result = enforcer.evaluate_batch(records, current_time=now)

        assert result.total_evaluated == 3
        assert result.keep_count == 1
        assert result.archive_count == 1
        assert result.tombstone_count == 1
        assert len(result.results) == 3

    def test_batch_result_summary(self, enforcer: RetentionEnforcer) -> None:
        """BatchRetentionResult.summary() returns correct stats."""
        now = 1700000000000
        records = [
            {
                "entity_id": "mem_1",
                "table_name": "st_epi",
                "last_observed_at": now,
            },
            {
                "entity_id": "mem_2",
                "table_name": "st_epi",
                "last_observed_at": now,
            },
        ]

        result = enforcer.evaluate_batch(records, current_time=now)
        summary = result.summary()

        assert summary["total"] == 2
        assert summary["keep"] == 2
        assert summary["archive"] == 0
        assert summary["tombstone"] == 0
        assert "evaluation_time_ms" in summary

    def test_batch_with_optional_fields(self, enforcer: RetentionEnforcer) -> None:
        """Batch handles optional fields correctly."""
        now = 1700000000000

        records = [
            {
                "entity_id": "mem_full",
                "table_name": "st_epi",
                "last_observed_at": now - (100 * MS_PER_DAY),
                "current_status": "ACTIVE",
                "importance_score": 0.9,
                "confidence_score": 0.8,
                "observation_count": 10,
            },
            {
                "entity_id": "mem_minimal",
                "table_name": "st_epi",
                "last_observed_at": now,
            },
        ]

        result = enforcer.evaluate_batch(records, current_time=now)

        assert result.total_evaluated == 2
        # Full record with high importance should still be healthy
        assert result.results[0].importance_score == 0.9


# =============================================================================
# 4.3.4.T5: Integration with DecayEngine Tests
# =============================================================================


class TestDecayEngineIntegration:
    """Test integration with UnifiedDecayEngine."""

    def test_uses_custom_engine(self, custom_enforcer: RetentionEnforcer) -> None:
        """Custom engine thresholds are respected."""
        now = 1700000000000
        # Custom: archive=0.15, tombstone=0.02
        # Need decay between 0.02 and 0.15

        # Find appropriate time for decay in range
        # For st_epi: decay = exp(-0.00455 × days)
        # At 0.15: days ≈ ln(1/0.15) / 0.00455 ≈ 417 days
        # At 0.02: days ≈ ln(1/0.02) / 0.00455 ≈ 859 days
        old = now - (500 * MS_PER_DAY)

        result = custom_enforcer.evaluate(
            entity_id="mem_custom",
            table_name="st_epi",
            last_observed_at=old,
            current_time=now,
        )

        # With custom thresholds, should be ARCHIVE_CANDIDATE
        assert result.classification == DecayClassification.ARCHIVE_CANDIDATE

    def test_get_config(self, enforcer: RetentionEnforcer) -> None:
        """get_config returns decay engine config."""
        config = enforcer.get_config()

        assert config.archive_threshold == 0.10
        assert config.tombstone_threshold == 0.01

    def test_importance_affects_retention(self, enforcer: RetentionEnforcer) -> None:
        """High importance extends retention."""
        now = 1700000000000
        # Time that would normally cause archival
        old = now - (600 * MS_PER_DAY)

        # Without importance
        result_low = enforcer.evaluate(
            entity_id="mem_low",
            table_name="st_epi",
            last_observed_at=old,
            current_time=now,
            importance_score=0.0,
        )

        # With high importance
        result_high = enforcer.evaluate(
            entity_id="mem_high",
            table_name="st_epi",
            last_observed_at=old,
            current_time=now,
            importance_score=1.0,
        )

        # High importance should have higher decay
        assert result_high.current_decay > result_low.current_decay


# =============================================================================
# 4.3.4.T6: Logging and Audit Tests
# =============================================================================


class TestLoggingAndAudit:
    """Test logging and audit trail."""

    def test_resurrect_logs_info(self, caplog: pytest.LogCaptureFixture) -> None:
        """Resurrection logs info message."""
        enforcer = RetentionEnforcer()

        with caplog.at_level(logging.INFO):
            enforcer.resurrect(
                entity_id="mem_log",
                table_name="st_epi",
                current_decay=0.05,
                current_status="ARCHIVED",
                trigger=ResurrectionTrigger.EXPLICIT_ACCESS,
            )

        assert "Resurrected" in caplog.text
        assert "mem_log" in caplog.text
        assert "st_epi" in caplog.text

    def test_log_resurrection_audit(self, caplog: pytest.LogCaptureFixture) -> None:
        """log_resurrection creates audit entry."""
        enforcer = RetentionEnforcer()

        result = ResurrectionResult(
            entity_id="mem_audit",
            table_name="st_sem",
            trigger=ResurrectionTrigger.SEARCH_RESULT,
            old_decay=0.03,
            new_decay=0.70,
            old_status="ARCHIVED",
            new_status="ACTIVE",
            resurrected_at=1700000000000,
            resurrection_count=2,
        )

        with caplog.at_level(logging.INFO):
            enforcer.log_resurrection(result)

        assert "RESURRECTION_AUDIT" in caplog.text
        assert "mem_audit" in caplog.text
        assert "st_sem" in caplog.text
        assert "SEARCH_RESULT" in caplog.text


# =============================================================================
# 4.3.4.T7: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_same_time_returns_high_decay(self, enforcer: RetentionEnforcer) -> None:
        """No time elapsed → decay=1.0 → KEEP."""
        now = 1700000000000
        result = enforcer.evaluate(
            entity_id="mem_now",
            table_name="st_epi",
            last_observed_at=now,
            current_time=now,
        )

        assert result.current_decay == 1.0
        assert result.decision == RetentionDecision.KEEP

    def test_negative_time_delta(self, enforcer: RetentionEnforcer) -> None:
        """Future observation time → decay=1.0 (clock skew tolerance)."""
        now = 1700000000000
        future = now + (1 * MS_PER_DAY)

        result = enforcer.evaluate(
            entity_id="mem_future",
            table_name="st_epi",
            last_observed_at=future,
            current_time=now,
        )

        assert result.current_decay == 1.0
        assert result.decision == RetentionDecision.KEEP

    def test_very_old_record(self, enforcer: RetentionEnforcer) -> None:
        """Very old record (10 years) → TOMBSTONE."""
        now = 1700000000000
        ten_years_ago = now - (3650 * MS_PER_DAY)

        result = enforcer.evaluate(
            entity_id="mem_ancient",
            table_name="st_hipp_events",
            last_observed_at=ten_years_ago,
            current_time=now,
        )

        assert result.decision == RetentionDecision.TOMBSTONE
        assert result.current_decay < 0.01

    def test_resurrection_result_fields(self) -> None:
        """ResurrectionResult has all expected fields."""
        result = ResurrectionResult(
            entity_id="test",
            table_name="st_epi",
            trigger=ResurrectionTrigger.EXPLICIT_ACCESS,
            old_decay=0.05,
            new_decay=0.70,
            old_status="ARCHIVED",
        )

        assert result.entity_id == "test"
        assert result.table_name == "st_epi"
        assert result.trigger == ResurrectionTrigger.EXPLICIT_ACCESS
        assert result.old_decay == 0.05
        assert result.new_decay == 0.70
        assert result.old_status == "ARCHIVED"
        assert result.new_status == "ACTIVE"  # Default
        assert result.resurrected_at == 0  # Default
        assert result.resurrection_count == 1  # Default
