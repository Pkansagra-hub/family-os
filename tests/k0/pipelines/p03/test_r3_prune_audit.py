"""
Tests for PruneAuditLogger.

Issue: 4.3.10
Spec Reference: Dossier §1.4.7 (lines 1800-2060), §6.20
"""

from __future__ import annotations

import json

import pytest

from k0.modules.consolidation.algorithms.prune_audit_logger import (
    InMemoryAuditStore,
    PruneAction,
    PruneAuditLogger,
    PruneAuditLoggerConfig,
    PruneAuditRecord,
    PruneDecisionContext,
    build_prune_context,
    determine_prune_action,
    parse_inputs_json,
    parse_outputs_json,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def store() -> InMemoryAuditStore:
    """In-memory audit store fixture."""
    return InMemoryAuditStore()


@pytest.fixture
def debug_logger() -> PruneAuditLogger:
    """Logger in debug mode (100% logging)."""
    config = PruneAuditLoggerConfig(is_debug=True)
    return PruneAuditLogger(config=config)


@pytest.fixture
def production_logger() -> PruneAuditLogger:
    """Logger in production mode (10% logging)."""
    config = PruneAuditLoggerConfig(is_debug=False)
    return PruneAuditLogger(config=config)


@pytest.fixture
def sample_context() -> PruneDecisionContext:
    """Sample decision context fixture."""
    return PruneDecisionContext(
        memory_id="mem_123",
        source_table="st_epi",
        decay_factor=0.05,
        effective_lambda=0.01,
        days_since_access=30,
        access_count=5,
        is_immune=False,
        threshold_used=0.10,
        threshold_name="archive",
    )


# =============================================================================
# 4.3.10.T1: TOMBSTONE Always Logged
# =============================================================================


class TestTombstoneAlwaysLogged:
    """Test TOMBSTONE always logged (100%)."""

    @pytest.mark.asyncio
    async def test_tombstone_always_logged(
        self,
        production_logger: PruneAuditLogger,
        store: InMemoryAuditStore,
    ) -> None:
        """TOMBSTONE logs 100% regardless of sample rate."""
        context = PruneDecisionContext(
            memory_id="mem_tombstone",
            source_table="st_epi",
            decay_factor=0.005,
            effective_lambda=0.01,
            days_since_access=365,
            access_count=1,
            is_immune=False,
            threshold_used=0.01,
            threshold_name="tombstone",
        )

        # Log 100 TOMBSTONE decisions - all should be logged
        for i in range(100):
            await production_logger.log_prune_decision(
                action=PruneAction.TOMBSTONE,
                context=context,
                space_id="space_1",
                tenant_id="tenant_1",
                cycle_id=f"cycle_{i}",
                store=store,
            )

        assert store.count_by_action(PruneAction.TOMBSTONE) == 100

    def test_tombstone_should_log_always_true(self, production_logger: PruneAuditLogger) -> None:
        """should_log returns True for TOMBSTONE."""
        assert production_logger.should_log(PruneAction.TOMBSTONE) is True


# =============================================================================
# 4.3.10.T2: ARCHIVE Sampled in Production
# =============================================================================


class TestArchiveSampling:
    """Test ARCHIVE sampling behavior."""

    @pytest.mark.asyncio
    async def test_archive_sampled_production(
        self,
        production_logger: PruneAuditLogger,
        store: InMemoryAuditStore,
        sample_context: PruneDecisionContext,
    ) -> None:
        """ARCHIVE sampled at ~10% in production."""
        # Log 1000 ARCHIVE decisions
        for i in range(1000):
            await production_logger.log_prune_decision(
                action=PruneAction.ARCHIVE,
                context=sample_context,
                space_id="space_1",
                tenant_id="tenant_1",
                cycle_id=f"cycle_{i}",
                store=store,
            )

        logged = store.count_by_action(PruneAction.ARCHIVE)
        # Should be approximately 10% (100 ± 50)
        assert 50 < logged < 200, f"Expected ~100, got {logged}"


# =============================================================================
# 4.3.10.T3: ARCHIVE Logged 100% in Debug
# =============================================================================


class TestDebugMode:
    """Test debug mode (100% logging)."""

    @pytest.mark.asyncio
    async def test_archive_logged_debug(
        self,
        debug_logger: PruneAuditLogger,
        store: InMemoryAuditStore,
        sample_context: PruneDecisionContext,
    ) -> None:
        """ARCHIVE logged 100% in debug mode."""
        # Log 100 ARCHIVE decisions
        for i in range(100):
            await debug_logger.log_prune_decision(
                action=PruneAction.ARCHIVE,
                context=sample_context,
                space_id="space_1",
                tenant_id="tenant_1",
                cycle_id=f"cycle_{i}",
                store=store,
            )

        assert store.count_by_action(PruneAction.ARCHIVE) == 100

    @pytest.mark.asyncio
    async def test_skip_logged_debug(
        self,
        debug_logger: PruneAuditLogger,
        store: InMemoryAuditStore,
    ) -> None:
        """SKIP logged 100% in debug mode."""
        context = PruneDecisionContext(
            memory_id="mem_skip",
            source_table="st_sem",
            decay_factor=0.50,
            effective_lambda=0.01,
            days_since_access=5,
            access_count=10,
            is_immune=False,
            threshold_used=0.10,
            threshold_name="archive",
        )

        for i in range(50):
            await debug_logger.log_prune_decision(
                action=PruneAction.SKIP,
                context=context,
                space_id="space_1",
                tenant_id="tenant_1",
                cycle_id=f"cycle_{i}",
                store=store,
            )

        assert store.count_by_action(PruneAction.SKIP) == 50


# =============================================================================
# 4.3.10.T4: SKIP Sampled
# =============================================================================


class TestSkipSampling:
    """Test SKIP sampling behavior."""

    @pytest.mark.asyncio
    async def test_skip_sampled(
        self,
        production_logger: PruneAuditLogger,
        store: InMemoryAuditStore,
    ) -> None:
        """SKIP decisions follow sample rate."""
        context = PruneDecisionContext(
            memory_id="mem_skip",
            source_table="st_sem",
            decay_factor=0.50,
            effective_lambda=0.01,
            days_since_access=5,
            access_count=10,
            is_immune=False,
            threshold_used=0.10,
            threshold_name="archive",
        )

        for i in range(1000):
            await production_logger.log_prune_decision(
                action=PruneAction.SKIP,
                context=context,
                space_id="space_1",
                tenant_id="tenant_1",
                cycle_id=f"cycle_{i}",
                store=store,
            )

        logged = store.count_by_action(PruneAction.SKIP)
        # Should be approximately 10%
        assert 50 < logged < 200, f"Expected ~100, got {logged}"


# =============================================================================
# 4.3.10.T5: Audit Record Complete
# =============================================================================


class TestAuditRecordComplete:
    """Test audit record completeness."""

    @pytest.mark.asyncio
    async def test_audit_record_complete(
        self,
        debug_logger: PruneAuditLogger,
        store: InMemoryAuditStore,
    ) -> None:
        """All fields populated correctly."""
        context = PruneDecisionContext(
            memory_id="mem_complete",
            source_table="st_epi",
            decay_factor=0.08,
            effective_lambda=0.015,
            days_since_access=45,
            access_count=3,
            is_immune=False,
            threshold_used=0.10,
            threshold_name="archive",
        )

        audit_id = await debug_logger.log_prune_decision(
            action=PruneAction.ARCHIVE,
            context=context,
            space_id="space_test",
            tenant_id="tenant_test",
            cycle_id="cycle_complete",
            store=store,
        )

        assert audit_id is not None

        records = store.get_all_records()
        assert len(records) == 1

        record = records[0]
        assert record.audit_id == audit_id
        assert record.memory_id == "mem_complete"
        assert record.source_table == "st_epi"
        assert record.action == PruneAction.ARCHIVE
        assert record.formula_used == "UnifiedDecayFormula"
        assert record.formula_version == "1.0"
        assert record.space_id == "space_test"
        assert record.tenant_id == "tenant_test"
        assert record.cycle_id == "cycle_complete"
        assert record.confidence == pytest.approx(0.08, abs=0.001)
        assert record.threshold_used == pytest.approx(0.10, abs=0.001)
        assert record.threshold_name == "archive"
        assert record.outcome_evaluated is False
        assert record.created_at > 0


# =============================================================================
# 4.3.10.T6: Explanation Human Readable
# =============================================================================


class TestExplanationReadable:
    """Test human-readable explanations."""

    @pytest.mark.asyncio
    async def test_archive_explanation(
        self,
        debug_logger: PruneAuditLogger,
        store: InMemoryAuditStore,
        sample_context: PruneDecisionContext,
    ) -> None:
        """ARCHIVE explanation is understandable."""
        await debug_logger.log_prune_decision(
            action=PruneAction.ARCHIVE,
            context=sample_context,
            space_id="space_1",
            tenant_id="tenant_1",
            cycle_id="cycle_1",
            store=store,
        )

        record = store.get_all_records()[0]
        explanation = record.explanation

        assert "ARCHIVE" in explanation
        assert "decay_factor" in explanation
        assert "threshold" in explanation
        assert "accessed" in explanation.lower()
        assert "resurrected" in explanation.lower()

    @pytest.mark.asyncio
    async def test_tombstone_explanation(
        self,
        debug_logger: PruneAuditLogger,
        store: InMemoryAuditStore,
    ) -> None:
        """TOMBSTONE explanation mentions permanent."""
        context = PruneDecisionContext(
            memory_id="mem_tombstone",
            source_table="st_epi",
            decay_factor=0.005,
            effective_lambda=0.01,
            days_since_access=365,
            access_count=1,
            is_immune=False,
            threshold_used=0.01,
            threshold_name="tombstone",
        )

        await debug_logger.log_prune_decision(
            action=PruneAction.TOMBSTONE,
            context=context,
            space_id="space_1",
            tenant_id="tenant_1",
            cycle_id="cycle_1",
            store=store,
        )

        record = store.get_all_records()[0]
        explanation = record.explanation

        assert "TOMBSTONE" in explanation
        assert "PERMANENT" in explanation

    @pytest.mark.asyncio
    async def test_skip_explanation(
        self,
        debug_logger: PruneAuditLogger,
        store: InMemoryAuditStore,
    ) -> None:
        """SKIP explanation mentions retained."""
        context = PruneDecisionContext(
            memory_id="mem_skip",
            source_table="st_sem",
            decay_factor=0.50,
            effective_lambda=0.01,
            days_since_access=5,
            access_count=10,
            is_immune=False,
            threshold_used=0.10,
            threshold_name="archive",
        )

        await debug_logger.log_prune_decision(
            action=PruneAction.SKIP,
            context=context,
            space_id="space_1",
            tenant_id="tenant_1",
            cycle_id="cycle_1",
            store=store,
        )

        record = store.get_all_records()[0]
        assert "SKIP" in record.explanation
        assert "retained" in record.explanation.lower()

    @pytest.mark.asyncio
    async def test_immune_explanation(
        self,
        debug_logger: PruneAuditLogger,
        store: InMemoryAuditStore,
    ) -> None:
        """Immune entity explanation mentions decay_immune."""
        context = PruneDecisionContext(
            memory_id="mem_immune",
            source_table="st_kg_dom",
            decay_factor=0.95,
            effective_lambda=0.01,
            days_since_access=0,
            access_count=100,
            is_immune=True,
            threshold_used=0.0,
            threshold_name="immune",
        )

        await debug_logger.log_prune_decision(
            action=PruneAction.SKIP,
            context=context,
            space_id="space_1",
            tenant_id="tenant_1",
            cycle_id="cycle_1",
            store=store,
        )

        record = store.get_all_records()[0]
        assert "decay_immune" in record.explanation


# =============================================================================
# 4.3.10.T7: inputs_json Valid
# =============================================================================


class TestInputsJson:
    """Test inputs_json parsing."""

    @pytest.mark.asyncio
    async def test_inputs_json_valid(
        self,
        debug_logger: PruneAuditLogger,
        store: InMemoryAuditStore,
        sample_context: PruneDecisionContext,
    ) -> None:
        """inputs_json parses correctly."""
        await debug_logger.log_prune_decision(
            action=PruneAction.ARCHIVE,
            context=sample_context,
            space_id="space_1",
            tenant_id="tenant_1",
            cycle_id="cycle_1",
            store=store,
        )

        record = store.get_all_records()[0]
        inputs = json.loads(record.inputs_json)

        assert inputs["decay_factor"] == pytest.approx(0.05, abs=0.001)
        assert inputs["effective_lambda"] == pytest.approx(0.01, abs=0.001)
        assert inputs["days_since_access"] == 30
        assert inputs["access_count"] == 5
        assert inputs["is_immune"] is False


# =============================================================================
# 4.3.10.T8: outputs_json Valid
# =============================================================================


class TestOutputsJson:
    """Test outputs_json parsing."""

    @pytest.mark.asyncio
    async def test_outputs_json_valid(
        self,
        debug_logger: PruneAuditLogger,
        store: InMemoryAuditStore,
        sample_context: PruneDecisionContext,
    ) -> None:
        """outputs_json parses correctly."""
        await debug_logger.log_prune_decision(
            action=PruneAction.ARCHIVE,
            context=sample_context,
            space_id="space_1",
            tenant_id="tenant_1",
            cycle_id="cycle_1",
            store=store,
        )

        record = store.get_all_records()[0]
        outputs = json.loads(record.outputs_json)

        assert outputs["action"] == "ARCHIVE"
        assert outputs["threshold_used"] == pytest.approx(0.10, abs=0.001)
        assert outputs["threshold_name"] == "archive"


# =============================================================================
# 4.3.10.T9: Get Decision History
# =============================================================================


class TestGetDecisionHistory:
    """Test get_decision_history method."""

    @pytest.mark.asyncio
    async def test_get_decision_history(
        self,
        debug_logger: PruneAuditLogger,
        store: InMemoryAuditStore,
    ) -> None:
        """History query returns correct records."""
        # Log multiple decisions for same memory
        context = PruneDecisionContext(
            memory_id="mem_history",
            source_table="st_epi",
            decay_factor=0.08,
            effective_lambda=0.01,
            days_since_access=30,
            access_count=5,
            is_immune=False,
            threshold_used=0.10,
            threshold_name="archive",
        )

        for i in range(5):
            await debug_logger.log_prune_decision(
                action=PruneAction.ARCHIVE,
                context=context,
                space_id="space_1",
                tenant_id="tenant_1",
                cycle_id=f"cycle_{i}",
                store=store,
            )

        # Get history
        history = await debug_logger.get_decision_history(
            memory_id="mem_history",
            store=store,
            limit=3,
        )

        assert len(history) == 3
        # Should be sorted by created_at descending
        for record in history:
            assert record["memory_id"] == "mem_history"

    @pytest.mark.asyncio
    async def test_get_decision_history_empty(
        self,
        debug_logger: PruneAuditLogger,
        store: InMemoryAuditStore,
    ) -> None:
        """History returns empty for unknown memory."""
        history = await debug_logger.get_decision_history(
            memory_id="unknown",
            store=store,
        )

        assert history == []


# =============================================================================
# 4.3.10.T10: outcome_evaluated Starts False
# =============================================================================


class TestOutcomeEvaluated:
    """Test outcome_evaluated initial state."""

    @pytest.mark.asyncio
    async def test_outcome_evaluated_false_initially(
        self,
        debug_logger: PruneAuditLogger,
        store: InMemoryAuditStore,
        sample_context: PruneDecisionContext,
    ) -> None:
        """outcome_evaluated starts FALSE."""
        await debug_logger.log_prune_decision(
            action=PruneAction.ARCHIVE,
            context=sample_context,
            space_id="space_1",
            tenant_id="tenant_1",
            cycle_id="cycle_1",
            store=store,
        )

        record = store.get_all_records()[0]
        assert record.outcome_evaluated is False
        assert record.outcome_success is None
        assert record.evaluated_at is None


# =============================================================================
# 4.3.10.T11: Config Validation
# =============================================================================


class TestConfigValidation:
    """Test configuration validation."""

    def test_default_config_valid(self) -> None:
        """Default config passes validation."""
        config = PruneAuditLoggerConfig()
        config.validate()  # Should not raise

    def test_invalid_sample_rate_production(self) -> None:
        """Invalid sample_rate_production raises."""
        config = PruneAuditLoggerConfig(sample_rate_production=1.5)
        with pytest.raises(ValueError, match="sample_rate_production"):
            config.validate()

    def test_invalid_sample_rate_debug(self) -> None:
        """Invalid sample_rate_debug raises."""
        config = PruneAuditLoggerConfig(sample_rate_debug=-0.1)
        with pytest.raises(ValueError, match="sample_rate_debug"):
            config.validate()

    def test_invalid_retention_days(self) -> None:
        """Invalid retention_days raises."""
        config = PruneAuditLoggerConfig(retention_days=0)
        with pytest.raises(ValueError, match="retention_days"):
            config.validate()

    def test_sample_rate_property(self) -> None:
        """sample_rate property returns correct value."""
        debug_config = PruneAuditLoggerConfig(is_debug=True)
        assert debug_config.sample_rate == 1.0

        prod_config = PruneAuditLoggerConfig(is_debug=False)
        assert prod_config.sample_rate == 0.10


# =============================================================================
# 4.3.10.T12: Disabled Logger
# =============================================================================


class TestDisabledLogger:
    """Test disabled logger behavior."""

    @pytest.mark.asyncio
    async def test_disabled_returns_none(
        self,
        store: InMemoryAuditStore,
        sample_context: PruneDecisionContext,
    ) -> None:
        """Disabled logger returns None."""
        config = PruneAuditLoggerConfig(enabled=False)
        logger = PruneAuditLogger(config=config)

        result = await logger.log_prune_decision(
            action=PruneAction.TOMBSTONE,  # Would normally always log
            context=sample_context,
            space_id="space_1",
            tenant_id="tenant_1",
            cycle_id="cycle_1",
            store=store,
        )

        assert result is None
        assert store.count_by_action(PruneAction.TOMBSTONE) == 0


# =============================================================================
# 4.3.10.T13: Helper Functions
# =============================================================================


class TestHelperFunctions:
    """Test helper functions."""

    def test_determine_prune_action_tombstone(self) -> None:
        """Decay < 0.01 returns TOMBSTONE."""
        action, threshold, name = determine_prune_action(
            decay_factor=0.005,
            is_immune=False,
        )

        assert action == PruneAction.TOMBSTONE
        assert threshold == 0.01
        assert name == "tombstone"

    def test_determine_prune_action_archive(self) -> None:
        """Decay < 0.10 returns ARCHIVE."""
        action, threshold, name = determine_prune_action(
            decay_factor=0.05,
            is_immune=False,
        )

        assert action == PruneAction.ARCHIVE
        assert threshold == 0.10
        assert name == "archive"

    def test_determine_prune_action_skip(self) -> None:
        """Decay >= 0.10 returns SKIP."""
        action, threshold, name = determine_prune_action(
            decay_factor=0.50,
            is_immune=False,
        )

        assert action == PruneAction.SKIP
        assert threshold == 0.10
        assert name == "archive"

    def test_determine_prune_action_immune(self) -> None:
        """Immune entity returns SKIP."""
        action, threshold, name = determine_prune_action(
            decay_factor=0.005,  # Would be TOMBSTONE if not immune
            is_immune=True,
        )

        assert action == PruneAction.SKIP
        assert name == "immune"

    def test_build_prune_context(self) -> None:
        """build_prune_context returns correct tuple."""
        action, context = build_prune_context(
            memory_id="mem_1",
            source_table="st_epi",
            decay_factor=0.05,
            effective_lambda=0.01,
            days_since_access=30,
            access_count=5,
            is_immune=False,
        )

        assert action == PruneAction.ARCHIVE
        assert context.memory_id == "mem_1"
        assert context.threshold_used == 0.10

    def test_parse_inputs_json(self) -> None:
        """parse_inputs_json parses correctly."""
        json_str = '{"decay_factor": 0.05, "is_immune": false}'
        inputs = parse_inputs_json(json_str)

        assert inputs["decay_factor"] == 0.05
        assert inputs["is_immune"] is False

    def test_parse_outputs_json(self) -> None:
        """parse_outputs_json parses correctly."""
        json_str = '{"action": "ARCHIVE", "threshold_used": 0.10}'
        outputs = parse_outputs_json(json_str)

        assert outputs["action"] == "ARCHIVE"
        assert outputs["threshold_used"] == 0.10


# =============================================================================
# 4.3.10.T14: Counter Tracking
# =============================================================================


class TestCounterTracking:
    """Test internal counter tracking."""

    @pytest.mark.asyncio
    async def test_logged_count_tracked(
        self,
        debug_logger: PruneAuditLogger,
        store: InMemoryAuditStore,
        sample_context: PruneDecisionContext,
    ) -> None:
        """Logged count is tracked."""
        await debug_logger.log_prune_decision(
            action=PruneAction.ARCHIVE,
            context=sample_context,
            space_id="space_1",
            tenant_id="tenant_1",
            cycle_id="cycle_1",
            store=store,
        )

        assert debug_logger.get_logged_count(PruneAction.ARCHIVE) == 1

    def test_reset_counts(
        self,
        debug_logger: PruneAuditLogger,
    ) -> None:
        """reset_counts clears counters."""
        debug_logger._logged_count["ARCHIVE"] = 10
        debug_logger._sampled_out_count["SKIP"] = 20
        debug_logger.reset_counts()

        assert debug_logger.get_logged_count(PruneAction.ARCHIVE) == 0
        assert debug_logger.get_sampled_out_count(PruneAction.SKIP) == 0


# =============================================================================
# 4.3.10.T15: PruneDecisionContext
# =============================================================================


class TestPruneDecisionContext:
    """Test PruneDecisionContext dataclass."""

    def test_to_inputs_dict(self, sample_context: PruneDecisionContext) -> None:
        """to_inputs_dict returns correct dict."""
        inputs = sample_context.to_inputs_dict()

        assert inputs["decay_factor"] == 0.05
        assert inputs["effective_lambda"] == 0.01
        assert inputs["days_since_access"] == 30
        assert inputs["access_count"] == 5
        assert inputs["is_immune"] is False

    def test_to_outputs_dict(self, sample_context: PruneDecisionContext) -> None:
        """to_outputs_dict returns correct dict."""
        outputs = sample_context.to_outputs_dict(PruneAction.ARCHIVE)

        assert outputs["action"] == "ARCHIVE"
        assert outputs["threshold_used"] == 0.10
        assert outputs["threshold_name"] == "archive"


# =============================================================================
# 4.3.10.T16: PruneAuditRecord
# =============================================================================


class TestPruneAuditRecord:
    """Test PruneAuditRecord dataclass."""

    def test_to_dict(self) -> None:
        """to_dict returns correct dict."""
        record = PruneAuditRecord(
            audit_id="audit_123",
            memory_id="mem_123",
            source_table="st_epi",
            action=PruneAction.ARCHIVE,
            formula_used="UnifiedDecayFormula",
            formula_version="1.0",
            inputs_json='{"decay_factor": 0.05}',
            outputs_json='{"action": "ARCHIVE"}',
            explanation="ARCHIVE decision",
            decision_id="audit_123",
            space_id="space_1",
            tenant_id="tenant_1",
            cycle_id="cycle_1",
            confidence=0.05,
            created_at=1704067200000,
            threshold_used=0.10,
            threshold_name="archive",
        )

        d = record.to_dict()

        assert d["audit_id"] == "audit_123"
        assert d["action"] == "ARCHIVE"
        assert d["outcome_evaluated"] is False
