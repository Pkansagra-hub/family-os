"""
R5 Skip Conditions Tests — Issue 8.1.2

Test Categories:
1. Mode-based skip - R5 skipped when mode is DISABLED
2. Backlog-based skip - R5 skipped when pending > threshold
3. Time window skip - R5 skipped when remaining time < threshold
4. No skip conditions - R5 executes when all conditions pass
5. Metrics emission - Verify skip metrics are emitted correctly
6. Envelope state - Verify r5_skipped and r5_skip_reason are set

References:
- M8_EXECUTION.md Issue 8.1.2: R5 Skip Conditions + Accounting
- Dossier §4.6.7: R5 Complexity Assessment
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from k0.pipelines.p03 import P03BatchEnvelope, P03CycleContext
from k0.pipelines.p03.phase_interface import P03RunnerContext
from k0.pipelines.p03.phases.r5_dream_explorer import R5DreamExplorer, R5SkipReason
from k0.pipelines.p03.r5_config import R5Config, R5Mode

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sample_context() -> P03CycleContext:
    """Create a sample cycle context with normal conditions."""
    return P03CycleContext.create(
        tenant_id="tenant-1",
        space_id="space-1",
        event_ids=["evt-1", "evt-2", "evt-3"],
        trigger_type="MANUAL",
        trigger_reason="Test run",
        pending_before=100,  # Well below threshold
        deadline_ms=300000,  # 5 minute deadline
    )


@pytest.fixture
def high_backlog_context() -> P03CycleContext:
    """Create context with high backlog (> 1000)."""
    return P03CycleContext.create(
        tenant_id="tenant-1",
        space_id="space-1",
        event_ids=["evt-1", "evt-2"],
        trigger_type="INTERVAL",
        trigger_reason="Scheduled",
        pending_before=1500,  # Above 1000 threshold
        deadline_ms=300000,
    )


@pytest.fixture
def sample_envelope(sample_context: P03CycleContext) -> P03BatchEnvelope:
    """Create a sample batch envelope."""
    return P03BatchEnvelope.create(sample_context)


@pytest.fixture
def high_backlog_envelope(high_backlog_context: P03CycleContext) -> P03BatchEnvelope:
    """Create envelope with high backlog."""
    return P03BatchEnvelope.create(high_backlog_context)


@pytest.fixture
def mock_metrics_registry() -> MagicMock:
    """Create mock metrics registry."""
    registry = MagicMock()
    registry.emit_r5_skip = MagicMock()
    registry.set_r5_mode = MagicMock()
    registry.emit_r5_duration = MagicMock()
    registry.emit_r5_insights = MagicMock()
    registry.emit_r5_counterfactuals = MagicMock()
    registry.emit_r5_routine_optimizations = MagicMock()
    registry.emit_r5_prospective_memories = MagicMock()
    registry.emit_r5_mcts_decisions = MagicMock()
    return registry


@pytest.fixture
def mock_syscalls() -> MagicMock:
    """Create mock syscalls."""
    return MagicMock()


@pytest.fixture
def mock_logger() -> MagicMock:
    """Create mock logger."""
    return MagicMock()


@pytest.fixture
def runner_context(
    mock_syscalls: MagicMock,
    mock_logger: MagicMock,
    mock_metrics_registry: MagicMock,
) -> P03RunnerContext:
    """Create a sample runner context with metrics registry."""
    ctx = P03RunnerContext.create(
        syscalls=mock_syscalls,
        logger=mock_logger,
        qos_band="GREEN",
        priority=50,
        config={"backlog_threshold": 1000},
    )
    ctx.metrics_registry = mock_metrics_registry
    return ctx


@pytest.fixture
def runner_context_no_metrics(
    mock_syscalls: MagicMock,
    mock_logger: MagicMock,
) -> P03RunnerContext:
    """Create runner context without metrics registry."""
    return P03RunnerContext.create(
        syscalls=mock_syscalls,
        logger=mock_logger,
        qos_band="GREEN",
        priority=50,
    )


# =============================================================================
# TEST MODE-BASED SKIP
# =============================================================================


class TestModeBasedSkip:
    """Test R5 skip when mode is DISABLED."""

    def test_skip_when_mode_disabled(
        self,
        sample_envelope: P03BatchEnvelope,
        runner_context: P03RunnerContext,
    ) -> None:
        """R5 should be skipped when mode is DISABLED."""
        config = R5Config(mode=R5Mode.DISABLED)
        r5 = R5DreamExplorer(config)

        should_skip, reason = r5.should_skip(sample_envelope, runner_context)

        assert should_skip is True
        assert reason == R5SkipReason.DISABLED

    def test_no_skip_when_mode_enabled(
        self,
        sample_envelope: P03BatchEnvelope,
        runner_context: P03RunnerContext,
    ) -> None:
        """R5 should NOT be skipped when mode is ENABLED."""
        config = R5Config(mode=R5Mode.ENABLED)
        r5 = R5DreamExplorer(config)

        should_skip, reason = r5.should_skip(sample_envelope, runner_context)

        assert should_skip is False
        assert reason == ""

    def test_no_skip_when_mode_shadow(
        self,
        sample_envelope: P03BatchEnvelope,
        runner_context: P03RunnerContext,
    ) -> None:
        """R5 should NOT be skipped when mode is SHADOW."""
        config = R5Config(mode=R5Mode.SHADOW)
        r5 = R5DreamExplorer(config)

        should_skip, reason = r5.should_skip(sample_envelope, runner_context)

        assert should_skip is False
        assert reason == ""

    def test_no_skip_when_mode_enabled_low(
        self,
        sample_envelope: P03BatchEnvelope,
        runner_context: P03RunnerContext,
    ) -> None:
        """R5 should NOT be skipped when mode is ENABLED_LOW."""
        config = R5Config(mode=R5Mode.ENABLED_LOW)
        r5 = R5DreamExplorer(config)

        should_skip, reason = r5.should_skip(sample_envelope, runner_context)

        assert should_skip is False
        assert reason == ""


# =============================================================================
# TEST BACKLOG-BASED SKIP
# =============================================================================


class TestBacklogBasedSkip:
    """Test R5 skip when backlog exceeds threshold."""

    def test_skip_when_backlog_exceeded(
        self,
        high_backlog_envelope: P03BatchEnvelope,
        runner_context: P03RunnerContext,
    ) -> None:
        """R5 should be skipped when pending > 1000."""
        config = R5Config(mode=R5Mode.ENABLED, backlog_threshold=1000)
        r5 = R5DreamExplorer(config)

        should_skip, reason = r5.should_skip(high_backlog_envelope, runner_context)

        assert should_skip is True
        assert reason == R5SkipReason.BACKLOG_EXCEEDED

    def test_no_skip_when_backlog_below_threshold(
        self,
        sample_envelope: P03BatchEnvelope,
        runner_context: P03RunnerContext,
    ) -> None:
        """R5 should NOT be skipped when pending < threshold."""
        config = R5Config(mode=R5Mode.ENABLED, backlog_threshold=1000)
        r5 = R5DreamExplorer(config)

        should_skip, reason = r5.should_skip(sample_envelope, runner_context)

        assert should_skip is False
        assert reason == ""

    def test_no_skip_at_exact_threshold(
        self,
        runner_context: P03RunnerContext,
    ) -> None:
        """R5 should NOT be skipped when pending == threshold (not >)."""
        # Create context with exactly 1000 pending
        context = P03CycleContext.create(
            tenant_id="tenant-1",
            space_id="space-1",
            event_ids=["evt-1"],
            trigger_type="MANUAL",
            trigger_reason="Test",
            pending_before=1000,  # Exactly at threshold
        )
        envelope = P03BatchEnvelope.create(context)

        config = R5Config(mode=R5Mode.ENABLED, backlog_threshold=1000)
        r5 = R5DreamExplorer(config)

        should_skip, reason = r5.should_skip(envelope, runner_context)

        # > 1000 means 1001+, so 1000 should NOT trigger skip
        assert should_skip is False
        assert reason == ""

    def test_custom_backlog_threshold(
        self,
        runner_context: P03RunnerContext,
    ) -> None:
        """R5 should respect custom backlog threshold."""
        context = P03CycleContext.create(
            tenant_id="tenant-1",
            space_id="space-1",
            event_ids=["evt-1"],
            trigger_type="MANUAL",
            trigger_reason="Test",
            pending_before=600,  # Above custom 500 threshold
        )
        envelope = P03BatchEnvelope.create(context)

        config = R5Config(mode=R5Mode.ENABLED, backlog_threshold=500)
        r5 = R5DreamExplorer(config)

        should_skip, reason = r5.should_skip(envelope, runner_context)

        assert should_skip is True
        assert reason == R5SkipReason.BACKLOG_EXCEEDED


# =============================================================================
# TEST TIME WINDOW SKIP
# =============================================================================


class TestTimeWindowSkip:
    """Test R5 skip when remaining time is too low."""

    def test_skip_when_time_window_exceeded(
        self,
        runner_context: P03RunnerContext,
    ) -> None:
        """R5 should be skipped when remaining time < 60 seconds."""
        # Create context that will have < 60 seconds remaining
        # Use a deadline_ms of 10000 (10 seconds) which is definitely < 60
        context = P03CycleContext.create(
            tenant_id="tenant-1",
            space_id="space-1",
            event_ids=["evt-1"],
            trigger_type="MANUAL",
            trigger_reason="Test",
            pending_before=100,
            deadline_ms=10000,  # 10 second deadline - will be < 60s remaining
        )
        envelope = P03BatchEnvelope.create(context)

        config = R5Config(mode=R5Mode.ENABLED, min_remaining_window_seconds=60)
        r5 = R5DreamExplorer(config)

        should_skip, reason = r5.should_skip(envelope, runner_context)

        assert should_skip is True
        assert reason == R5SkipReason.TIME_WINDOW_EXCEEDED

    def test_no_skip_when_sufficient_time(
        self,
        sample_envelope: P03BatchEnvelope,
        runner_context: P03RunnerContext,
    ) -> None:
        """R5 should NOT be skipped when remaining time >= threshold."""
        config = R5Config(mode=R5Mode.ENABLED, min_remaining_window_seconds=60)
        r5 = R5DreamExplorer(config)

        should_skip, reason = r5.should_skip(sample_envelope, runner_context)

        assert should_skip is False
        assert reason == ""

    def test_custom_time_threshold(
        self,
        runner_context: P03RunnerContext,
    ) -> None:
        """R5 should respect custom time threshold."""
        # Create context with 2 minute deadline (will have ~120s remaining)
        context = P03CycleContext.create(
            tenant_id="tenant-1",
            space_id="space-1",
            event_ids=["evt-1"],
            trigger_type="MANUAL",
            trigger_reason="Test",
            pending_before=100,
            deadline_ms=120000,  # 2 minute deadline
        )
        envelope = P03BatchEnvelope.create(context)

        # With 180 second threshold, should skip
        config = R5Config(mode=R5Mode.ENABLED, min_remaining_window_seconds=180)
        r5 = R5DreamExplorer(config)

        should_skip, reason = r5.should_skip(envelope, runner_context)

        assert should_skip is True
        assert reason == R5SkipReason.TIME_WINDOW_EXCEEDED


# =============================================================================
# TEST SKIP PRIORITY
# =============================================================================


class TestSkipPriority:
    """Test skip condition priority (mode checked first)."""

    def test_mode_disabled_takes_priority_over_backlog(
        self,
        high_backlog_envelope: P03BatchEnvelope,
        runner_context: P03RunnerContext,
    ) -> None:
        """Mode disabled should be reported even if backlog also exceeded."""
        config = R5Config(mode=R5Mode.DISABLED, backlog_threshold=1000)
        r5 = R5DreamExplorer(config)

        should_skip, reason = r5.should_skip(high_backlog_envelope, runner_context)

        assert should_skip is True
        # Mode disabled is checked first
        assert reason == R5SkipReason.DISABLED

    def test_backlog_takes_priority_over_time(
        self,
        runner_context: P03RunnerContext,
    ) -> None:
        """Backlog exceeded should be reported before time window check."""
        # High backlog AND low time
        context = P03CycleContext.create(
            tenant_id="tenant-1",
            space_id="space-1",
            event_ids=["evt-1"],
            trigger_type="MANUAL",
            trigger_reason="Test",
            pending_before=1500,  # Above threshold
            deadline_ms=10000,  # Low time remaining
        )
        envelope = P03BatchEnvelope.create(context)

        config = R5Config(mode=R5Mode.ENABLED)
        r5 = R5DreamExplorer(config)

        should_skip, reason = r5.should_skip(envelope, runner_context)

        assert should_skip is True
        # Backlog is checked before time
        assert reason == R5SkipReason.BACKLOG_EXCEEDED


# =============================================================================
# TEST METRICS EMISSION
# =============================================================================


class TestMetricsEmission:
    """Test that skip metrics are emitted correctly."""

    @pytest.mark.asyncio
    async def test_skip_emits_metrics(
        self,
        sample_envelope: P03BatchEnvelope,
        runner_context: P03RunnerContext,
        mock_metrics_registry: MagicMock,
    ) -> None:
        """R5 skip should emit p03_r5_skipped_decisions metric."""
        config = R5Config(mode=R5Mode.DISABLED)
        r5 = R5DreamExplorer(config)

        await r5.run(sample_envelope, runner_context)

        # Verify skip counter was incremented
        mock_metrics_registry.emit_r5_skip.assert_called_once()
        call_args = mock_metrics_registry.emit_r5_skip.call_args
        assert call_args.kwargs["tenant_id"] == "tenant-1"
        assert call_args.kwargs["skip_reason"] == R5SkipReason.DISABLED

    @pytest.mark.asyncio
    async def test_skip_sets_mode_gauge(
        self,
        sample_envelope: P03BatchEnvelope,
        runner_context: P03RunnerContext,
        mock_metrics_registry: MagicMock,
    ) -> None:
        """R5 skip should set p03_r5_mode gauge."""
        config = R5Config(mode=R5Mode.DISABLED)
        r5 = R5DreamExplorer(config)

        await r5.run(sample_envelope, runner_context)

        # Verify mode gauge was set
        mock_metrics_registry.set_r5_mode.assert_called_once_with(
            tenant_id="tenant-1",
            mode_value=0,  # DISABLED = 0
        )

    @pytest.mark.asyncio
    async def test_no_metrics_when_registry_none(
        self,
        sample_envelope: P03BatchEnvelope,
        runner_context_no_metrics: P03RunnerContext,
    ) -> None:
        """R5 should not crash when metrics_registry is None."""
        config = R5Config(mode=R5Mode.DISABLED)
        r5 = R5DreamExplorer(config)

        # Should not raise
        result = await r5.run(sample_envelope, runner_context_no_metrics)
        assert result.is_skipped


# =============================================================================
# TEST ENVELOPE STATE
# =============================================================================


class TestEnvelopeState:
    """Test that envelope state is updated correctly on skip."""

    @pytest.mark.asyncio
    async def test_envelope_marked_skipped(
        self,
        sample_envelope: P03BatchEnvelope,
        runner_context: P03RunnerContext,
    ) -> None:
        """Envelope should have r5_skipped=True after skip."""
        config = R5Config(mode=R5Mode.DISABLED)
        r5 = R5DreamExplorer(config)

        await r5.run(sample_envelope, runner_context)

        assert sample_envelope.phases.r5_skipped is True

    @pytest.mark.asyncio
    async def test_envelope_skip_reason_set(
        self,
        sample_envelope: P03BatchEnvelope,
        runner_context: P03RunnerContext,
    ) -> None:
        """Envelope should have r5_skip_reason set after skip."""
        config = R5Config(mode=R5Mode.DISABLED)
        r5 = R5DreamExplorer(config)

        await r5.run(sample_envelope, runner_context)

        assert sample_envelope.phases.r5_skip_reason == R5SkipReason.DISABLED

    @pytest.mark.asyncio
    async def test_envelope_not_marked_skipped_on_success(
        self,
        sample_envelope: P03BatchEnvelope,
        runner_context: P03RunnerContext,
    ) -> None:
        """Envelope should have r5_skipped=False after successful execution."""
        config = R5Config(mode=R5Mode.ENABLED)
        r5 = R5DreamExplorer(config)

        await r5.run(sample_envelope, runner_context)

        assert sample_envelope.phases.r5_skipped is False
        assert sample_envelope.phases.r5_skip_reason is None


# =============================================================================
# TEST PHASE RESULT
# =============================================================================


class TestPhaseResult:
    """Test that phase result is correct."""

    @pytest.mark.asyncio
    async def test_skip_returns_skip_status(
        self,
        sample_envelope: P03BatchEnvelope,
        runner_context: P03RunnerContext,
    ) -> None:
        """Phase result should have SKIP status when skipped."""
        config = R5Config(mode=R5Mode.DISABLED)
        r5 = R5DreamExplorer(config)

        result = await r5.run(sample_envelope, runner_context)

        assert result.is_skipped is True
        assert result.skip_reason == R5SkipReason.DISABLED

    @pytest.mark.asyncio
    async def test_success_returns_done_status(
        self,
        sample_envelope: P03BatchEnvelope,
        runner_context: P03RunnerContext,
    ) -> None:
        """Phase result should have DONE status when executed."""
        config = R5Config(mode=R5Mode.ENABLED)
        r5 = R5DreamExplorer(config)

        result = await r5.run(sample_envelope, runner_context)

        assert result.is_success is True

    @pytest.mark.asyncio
    async def test_result_includes_duration(
        self,
        sample_envelope: P03BatchEnvelope,
        runner_context: P03RunnerContext,
    ) -> None:
        """Phase result should include duration_ms."""
        config = R5Config(mode=R5Mode.DISABLED)
        r5 = R5DreamExplorer(config)

        result = await r5.run(sample_envelope, runner_context)

        assert result.duration_ms >= 0


# =============================================================================
# TEST IDEMPOTENCY KEY
# =============================================================================


class TestIdempotencyKey:
    """Test idempotency key generation."""

    def test_idempotency_key_format(
        self,
        sample_envelope: P03BatchEnvelope,
    ) -> None:
        """Idempotency key should follow pattern p03:r5:{cycle_id}:{batch_id}."""
        r5 = R5DreamExplorer()

        key = r5.idempotency_key(sample_envelope)

        assert key.startswith("p03:r5:")
        assert sample_envelope.context.cycle_id in key
        assert sample_envelope.context.batch_id in key

    def test_idempotency_key_deterministic(
        self,
        sample_envelope: P03BatchEnvelope,
    ) -> None:
        """Same envelope should produce same idempotency key."""
        r5 = R5DreamExplorer()

        key1 = r5.idempotency_key(sample_envelope)
        key2 = r5.idempotency_key(sample_envelope)

        assert key1 == key2
