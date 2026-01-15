"""
Tests for P03 Consolidation Pipeline Trigger Specifications.

Issue 1.3.1: Implement P03 trigger specs (INTERVAL/THRESHOLD/MANUAL)

Validates:
1. P03 YAML triggers conform to TriggerSpec schema
2. PipelineScheduler.register_pipeline() creates all trigger engines
3. Each trigger type is correctly configured
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from k0.runtime.schemas import TriggerSpec, TriggerType
from k0.scheduler.scheduler import PipelineScheduler, PipelineState
from k0.scheduler.triggers import (
    IntervalTriggerEngine,
    ManualTriggerEngine,
    ThresholdTriggerEngine,
    create_trigger_engine,
)

# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def p03_yaml_path() -> Path:
    """Path to P03 consolidation pipeline YAML."""
    return (
        Path(__file__).parents[4] / "k0" / "contracts" / "pipelines" / "p03_consolidation.v1.yaml"
    )


@pytest.fixture
def p03_yaml_content(p03_yaml_path: Path) -> dict:
    """Load P03 pipeline YAML content."""
    with open(p03_yaml_path) as f:
        return yaml.safe_load(f)


@pytest.fixture
def p03_trigger_specs(p03_yaml_content: dict) -> list[TriggerSpec]:
    """Parse P03 triggers into TriggerSpec objects."""
    triggers = p03_yaml_content.get("triggers", [])
    return [TriggerSpec(**trigger) for trigger in triggers]


@pytest.fixture
def mock_syscalls() -> MagicMock:
    """Create mock syscalls for threshold trigger."""
    syscalls = MagicMock()
    syscalls.query_count = AsyncMock(return_value=0)
    return syscalls


@pytest.fixture
def mock_pipeline_spec(p03_yaml_content: dict, p03_trigger_specs: list[TriggerSpec]) -> MagicMock:
    """Create mock pipeline spec from P03 YAML."""
    spec = MagicMock()
    spec.pipeline_id = p03_yaml_content["pipeline_id"]
    spec.triggers = p03_trigger_specs
    return spec


# ============================================================
# YAML Schema Validation Tests
# ============================================================


class TestP03YamlTriggerSchema:
    """Validate P03 YAML triggers conform to TriggerSpec schema."""

    def test_yaml_file_exists(self, p03_yaml_path: Path) -> None:
        """P03 pipeline YAML must exist."""
        assert p03_yaml_path.exists(), f"P03 YAML not found at {p03_yaml_path}"

    def test_yaml_has_triggers_section(self, p03_yaml_content: dict) -> None:
        """P03 YAML must have triggers section."""
        assert "triggers" in p03_yaml_content, "Missing 'triggers' section in YAML"
        assert isinstance(p03_yaml_content["triggers"], list), "triggers must be a list"

    def test_exactly_three_triggers(self, p03_yaml_content: dict) -> None:
        """P03 must have exactly 3 triggers (INTERVAL, THRESHOLD, MANUAL)."""
        triggers = p03_yaml_content.get("triggers", [])
        assert len(triggers) == 3, f"Expected 3 triggers, got {len(triggers)}"

    def test_all_triggers_parse_to_triggerspec(self, p03_trigger_specs: list[TriggerSpec]) -> None:
        """All P03 triggers must successfully parse into TriggerSpec objects."""
        # If we get here, parsing succeeded (fixture would fail otherwise)
        assert len(p03_trigger_specs) == 3

    def test_each_trigger_has_unique_id(self, p03_trigger_specs: list[TriggerSpec]) -> None:
        """Each trigger must have a unique ID."""
        ids = [spec.id for spec in p03_trigger_specs]
        assert len(ids) == len(set(ids)), f"Duplicate trigger IDs: {ids}"

    def test_trigger_ids_follow_naming_convention(
        self, p03_trigger_specs: list[TriggerSpec]
    ) -> None:
        """Trigger IDs should follow p03_ prefix convention."""
        for spec in p03_trigger_specs:
            assert spec.id.startswith("p03_"), f"Trigger ID '{spec.id}' should start with 'p03_'"


# ============================================================
# Interval Trigger Tests
# ============================================================


class TestP03IntervalTrigger:
    """Tests for P03 INTERVAL trigger configuration."""

    @pytest.fixture
    def interval_spec(self, p03_trigger_specs: list[TriggerSpec]) -> TriggerSpec:
        """Get the INTERVAL trigger spec."""
        for spec in p03_trigger_specs:
            if spec.type == TriggerType.INTERVAL:
                return spec
        pytest.fail("No INTERVAL trigger found in P03 YAML")

    def test_interval_trigger_exists(self, interval_spec: TriggerSpec) -> None:
        """P03 must have an INTERVAL trigger."""
        assert interval_spec.type == TriggerType.INTERVAL

    def test_interval_is_90_minutes(self, interval_spec: TriggerSpec) -> None:
        """INTERVAL trigger must fire every 90 minutes (5400 seconds)."""
        assert (
            interval_spec.interval_seconds == 5400
        ), f"Expected 5400 seconds (90 min), got {interval_spec.interval_seconds}"

    def test_interval_id(self, interval_spec: TriggerSpec) -> None:
        """INTERVAL trigger should have correct ID."""
        assert interval_spec.id == "p03_interval_90m"

    def test_interval_catch_up_enabled(self, interval_spec: TriggerSpec) -> None:
        """INTERVAL trigger should have catch_up enabled for missed runs."""
        assert interval_spec.catch_up_enabled is True

    def test_interval_engine_creation(self, interval_spec: TriggerSpec) -> None:
        """INTERVAL spec should create IntervalTriggerEngine."""
        engine = create_trigger_engine(interval_spec, "P03_CONSOLIDATION")
        assert isinstance(engine, IntervalTriggerEngine)
        assert engine.pipeline_id == "P03_CONSOLIDATION"
        assert engine.spec == interval_spec


# ============================================================
# Threshold Trigger Tests
# ============================================================


class TestP03ThresholdTrigger:
    """Tests for P03 THRESHOLD trigger configuration."""

    @pytest.fixture
    def threshold_spec(self, p03_trigger_specs: list[TriggerSpec]) -> TriggerSpec:
        """Get the THRESHOLD trigger spec."""
        for spec in p03_trigger_specs:
            if spec.type == TriggerType.THRESHOLD:
                return spec
        pytest.fail("No THRESHOLD trigger found in P03 YAML")

    def test_threshold_trigger_exists(self, threshold_spec: TriggerSpec) -> None:
        """P03 must have a THRESHOLD trigger."""
        assert threshold_spec.type == TriggerType.THRESHOLD

    def test_threshold_monitors_st_hipp_events(self, threshold_spec: TriggerSpec) -> None:
        """THRESHOLD trigger must monitor st_hipp_events table."""
        assert threshold_spec.table == "st_hipp_events"

    def test_threshold_condition_is_pending_status(self, threshold_spec: TriggerSpec) -> None:
        """THRESHOLD condition must filter for PENDING consolidation_status."""
        assert threshold_spec.condition == "consolidation_status = 'PENDING'"

    def test_threshold_count_is_500(self, threshold_spec: TriggerSpec) -> None:
        """THRESHOLD must trigger at 500+ pending events."""
        assert threshold_spec.threshold_count == 500

    def test_threshold_check_interval(self, threshold_spec: TriggerSpec) -> None:
        """THRESHOLD should check every 60 seconds."""
        assert threshold_spec.check_interval_seconds == 60

    def test_threshold_id(self, threshold_spec: TriggerSpec) -> None:
        """THRESHOLD trigger should have correct ID."""
        assert threshold_spec.id == "p03_threshold_500"

    def test_threshold_engine_creation(
        self,
        threshold_spec: TriggerSpec,
        mock_syscalls: MagicMock,
    ) -> None:
        """THRESHOLD spec should create ThresholdTriggerEngine."""
        engine = create_trigger_engine(
            threshold_spec,
            "P03_CONSOLIDATION",
            syscalls=mock_syscalls,
        )
        assert isinstance(engine, ThresholdTriggerEngine)
        assert engine.pipeline_id == "P03_CONSOLIDATION"
        assert engine.spec == threshold_spec

    def test_threshold_engine_requires_syscalls(self, threshold_spec: TriggerSpec) -> None:
        """THRESHOLD engine creation should fail without syscalls."""
        with pytest.raises(ValueError, match="requires syscalls"):
            create_trigger_engine(threshold_spec, "P03_CONSOLIDATION", syscalls=None)


# ============================================================
# Manual Trigger Tests
# ============================================================


class TestP03ManualTrigger:
    """Tests for P03 MANUAL trigger configuration."""

    @pytest.fixture
    def manual_spec(self, p03_trigger_specs: list[TriggerSpec]) -> TriggerSpec:
        """Get the MANUAL trigger spec."""
        for spec in p03_trigger_specs:
            if spec.type == TriggerType.MANUAL:
                return spec
        pytest.fail("No MANUAL trigger found in P03 YAML")

    def test_manual_trigger_exists(self, manual_spec: TriggerSpec) -> None:
        """P03 must have a MANUAL trigger."""
        assert manual_spec.type == TriggerType.MANUAL

    def test_manual_id(self, manual_spec: TriggerSpec) -> None:
        """MANUAL trigger should have correct ID."""
        assert manual_spec.id == "p03_manual"

    def test_manual_engine_creation(self, manual_spec: TriggerSpec) -> None:
        """MANUAL spec should create ManualTriggerEngine."""
        engine = create_trigger_engine(manual_spec, "P03_CONSOLIDATION")
        assert isinstance(engine, ManualTriggerEngine)
        assert engine.pipeline_id == "P03_CONSOLIDATION"
        assert engine.spec == manual_spec

    @pytest.mark.asyncio
    async def test_manual_engine_can_fire(self, manual_spec: TriggerSpec) -> None:
        """MANUAL engine should allow explicit fire() calls."""
        engine = ManualTriggerEngine(manual_spec, "P03_CONSOLIDATION")
        callback = MagicMock()

        # Start the engine
        await engine.start(callback)

        # Fire manually (synchronous, no context param)
        result = engine.fire()

        assert result is True
        assert engine.fire_count == 1

        # Callback should be invoked
        callback.assert_called_once()
        event = callback.call_args[0][0]
        assert event.trigger_id == "p03_manual"
        assert event.pipeline_id == "P03_CONSOLIDATION"

        await engine.stop()


# ============================================================
# PipelineScheduler Integration Tests
# ============================================================


class TestP03SchedulerIntegration:
    """Test PipelineScheduler correctly creates P03 trigger engines."""

    def test_register_pipeline_creates_all_engines(
        self,
        mock_pipeline_spec: MagicMock,
        mock_syscalls: MagicMock,
    ) -> None:
        """register_pipeline() should create all 3 trigger engines."""
        scheduler = PipelineScheduler(syscalls=mock_syscalls)
        scheduler.register_pipeline(mock_pipeline_spec)

        # Get the registered pipeline
        assert mock_pipeline_spec.pipeline_id in scheduler.pipelines
        scheduled = scheduler.pipelines[mock_pipeline_spec.pipeline_id]

        # Should have 3 triggers
        assert len(scheduled.triggers) == 3

        # Verify each type
        trigger_types = {type(t).__name__ for t in scheduled.triggers}
        assert "IntervalTriggerEngine" in trigger_types
        assert "ThresholdTriggerEngine" in trigger_types
        assert "ManualTriggerEngine" in trigger_types

    def test_register_pipeline_state_is_registered(
        self,
        mock_pipeline_spec: MagicMock,
        mock_syscalls: MagicMock,
    ) -> None:
        """Registered pipeline should have REGISTERED state."""
        scheduler = PipelineScheduler(syscalls=mock_syscalls)
        scheduler.register_pipeline(mock_pipeline_spec)

        scheduled = scheduler.pipelines[mock_pipeline_spec.pipeline_id]
        assert scheduled.state == PipelineState.REGISTERED

    def test_get_pipeline_trigger_by_id(
        self,
        mock_pipeline_spec: MagicMock,
        mock_syscalls: MagicMock,
    ) -> None:
        """Should be able to retrieve triggers by ID."""
        scheduler = PipelineScheduler(syscalls=mock_syscalls)
        scheduler.register_pipeline(mock_pipeline_spec)

        scheduled = scheduler.pipelines[mock_pipeline_spec.pipeline_id]

        # Find manual trigger by ID
        manual_triggers = [t for t in scheduled.triggers if t.spec.id == "p03_manual"]
        assert len(manual_triggers) == 1
        assert isinstance(manual_triggers[0], ManualTriggerEngine)

    @pytest.mark.asyncio
    async def test_scheduler_starts_all_triggers(
        self,
        mock_pipeline_spec: MagicMock,
        mock_syscalls: MagicMock,
    ) -> None:
        """start() should start all trigger engines."""
        scheduler = PipelineScheduler(syscalls=mock_syscalls)
        scheduler.register_pipeline(mock_pipeline_spec)

        await scheduler.start()

        scheduled = scheduler.pipelines[mock_pipeline_spec.pipeline_id]
        assert scheduled.state == PipelineState.RUNNING

        for trigger in scheduled.triggers:
            assert trigger.is_running, f"Trigger {trigger.spec.id} should be running"

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_scheduler_stops_all_triggers(
        self,
        mock_pipeline_spec: MagicMock,
        mock_syscalls: MagicMock,
    ) -> None:
        """stop() should stop all trigger engines."""
        scheduler = PipelineScheduler(syscalls=mock_syscalls)
        scheduler.register_pipeline(mock_pipeline_spec)

        await scheduler.start()
        await scheduler.stop()

        scheduled = scheduler.pipelines[mock_pipeline_spec.pipeline_id]
        assert scheduled.state == PipelineState.STOPPED

        for trigger in scheduled.triggers:
            assert not trigger.is_running, f"Trigger {trigger.spec.id} should be stopped"


# ============================================================
# Dossier Appendix D.5 Compliance Tests
# ============================================================


class TestP03DossierCompliance:
    """Verify P03 triggers match dossier Appendix D.5 specifications."""

    def test_interval_matches_dossier(self, p03_trigger_specs: list[TriggerSpec]) -> None:
        """INTERVAL trigger should match dossier: 90 minutes."""
        interval = next((s for s in p03_trigger_specs if s.type == TriggerType.INTERVAL), None)
        assert interval is not None

        # Dossier specifies 90 minute cycle
        ninety_minutes = 90 * 60
        assert interval.interval_seconds == ninety_minutes

    def test_threshold_matches_dossier(self, p03_trigger_specs: list[TriggerSpec]) -> None:
        """THRESHOLD trigger should match dossier: 500 pending events."""
        threshold = next((s for s in p03_trigger_specs if s.type == TriggerType.THRESHOLD), None)
        assert threshold is not None

        # Dossier specifies 500 pending threshold
        assert threshold.threshold_count == 500
        assert threshold.table == "st_hipp_events"
        assert "PENDING" in (threshold.condition or "")

    def test_manual_trigger_present(self, p03_trigger_specs: list[TriggerSpec]) -> None:
        """MANUAL trigger should exist for admin/debug use."""
        manual = next((s for s in p03_trigger_specs if s.type == TriggerType.MANUAL), None)
        assert manual is not None, "Dossier requires MANUAL trigger for admin use"


# ============================================================
# Issue 1.3.2: Manual Trigger Context Propagation Tests
# ============================================================


class TestManualTriggerContextPropagation:
    """Tests for manual trigger context/payload propagation (Issue 1.3.2)."""

    @pytest.fixture
    def manual_spec(self) -> TriggerSpec:
        """Create a manual trigger spec."""
        return TriggerSpec(id="test_manual", type=TriggerType.MANUAL)

    @pytest.mark.asyncio
    async def test_fire_with_context(self, manual_spec: TriggerSpec) -> None:
        """ManualTriggerEngine.fire() should accept and propagate context."""
        engine = ManualTriggerEngine(manual_spec, "P03_CONSOLIDATION")
        events: list = []

        def callback(event) -> None:
            events.append(event)

        await engine.start(callback)

        # Fire with context
        context = {
            "reason": "Test manual trigger",
            "options": {"skip_r5": True, "max_events": 100},
        }
        result = engine.fire(context=context)

        assert result is True
        assert len(events) == 1

        event = events[0]
        assert event.context == context
        assert event.context["reason"] == "Test manual trigger"
        assert event.context["options"]["skip_r5"] is True
        assert event.context["options"]["max_events"] == 100

        await engine.stop()

    @pytest.mark.asyncio
    async def test_fire_without_context(self, manual_spec: TriggerSpec) -> None:
        """ManualTriggerEngine.fire() with no context should use empty dict."""
        engine = ManualTriggerEngine(manual_spec, "P03_CONSOLIDATION")
        events: list = []

        def callback(event) -> None:
            events.append(event)

        await engine.start(callback)
        result = engine.fire()

        assert result is True
        assert len(events) == 1
        assert events[0].context == {}

        await engine.stop()

    @pytest.mark.asyncio
    async def test_scheduler_fire_manual_with_context(
        self,
        mock_syscalls: MagicMock,
    ) -> None:
        """PipelineScheduler.fire_manual_trigger() should propagate context."""
        scheduler = PipelineScheduler(syscalls=mock_syscalls)

        # Create mock pipeline spec with manual trigger
        spec = MagicMock()
        spec.pipeline_id = "P03_CONSOLIDATION"
        spec.triggers = [TriggerSpec(id="p03_manual", type=TriggerType.MANUAL)]

        scheduler.register_pipeline(spec)
        await scheduler.start()

        # Capture events via callback
        events: list = []
        scheduled = scheduler.pipelines["P03_CONSOLIDATION"]
        manual_trigger = next(t for t in scheduled.triggers if t.spec.id == "p03_manual")
        original_callback = manual_trigger._callback

        def capture_callback(event):
            events.append(event)
            if original_callback:
                original_callback(event)

        manual_trigger._callback = capture_callback

        # Fire with context
        context = {
            "reason": "Admin debug run",
            "options": {"skip_r5": False, "max_events": 500},
        }
        result = scheduler.fire_manual_trigger("P03_CONSOLIDATION", "p03_manual", context=context)

        assert result is True
        assert len(events) == 1
        assert events[0].context == context

        await scheduler.stop()


class TestP03ManualTriggerOptions:
    """Tests for P03ManualTriggerOptions dataclass (Issue 1.3.2)."""

    def test_from_trigger_context_full(self) -> None:
        """Parse all options from trigger context."""
        from k0.pipelines.p03.context import P03ManualTriggerOptions

        context = {
            "reason": "Manual consolidation before demo",
            "options": {
                "skip_r5": True,
                "max_events": 1000,
                "space_id": "space_123",
                "tenant_id": "tenant_456",
            },
        }

        opts = P03ManualTriggerOptions.from_trigger_context(context)

        assert opts.reason == "Manual consolidation before demo"
        assert opts.skip_r5 is True
        assert opts.max_events == 1000
        assert opts.space_id == "space_123"
        assert opts.tenant_id == "tenant_456"

    def test_from_trigger_context_minimal(self) -> None:
        """Parse with minimal context (defaults applied)."""
        from k0.pipelines.p03.context import P03ManualTriggerOptions

        context = {"reason": "Quick test"}

        opts = P03ManualTriggerOptions.from_trigger_context(context)

        assert opts.reason == "Quick test"
        assert opts.skip_r5 is False
        assert opts.max_events is None
        assert opts.space_id is None
        assert opts.tenant_id is None

    def test_from_trigger_context_empty(self) -> None:
        """Parse with empty context (all defaults)."""
        from k0.pipelines.p03.context import P03ManualTriggerOptions

        opts = P03ManualTriggerOptions.from_trigger_context({})

        assert opts.reason == "Manual trigger (no reason provided)"
        assert opts.skip_r5 is False
        assert opts.max_events is None

    def test_to_dict_roundtrip(self) -> None:
        """to_dict should produce dict that can be parsed back."""
        from k0.pipelines.p03.context import P03ManualTriggerOptions

        original = P03ManualTriggerOptions(
            reason="Test reason",
            skip_r5=True,
            max_events=500,
            space_id="space_1",
            tenant_id="tenant_1",
        )

        as_dict = original.to_dict()
        parsed = P03ManualTriggerOptions.from_trigger_context(as_dict)

        assert parsed.reason == original.reason
        assert parsed.skip_r5 == original.skip_r5
        assert parsed.max_events == original.max_events
        assert parsed.space_id == original.space_id
        assert parsed.tenant_id == original.tenant_id

    def test_should_skip_r5(self) -> None:
        """should_skip_r5() returns skip_r5 value."""
        from k0.pipelines.p03.context import P03ManualTriggerOptions

        opts_skip = P03ManualTriggerOptions(reason="test", skip_r5=True)
        opts_no_skip = P03ManualTriggerOptions(reason="test", skip_r5=False)

        assert opts_skip.should_skip_r5() is True
        assert opts_no_skip.should_skip_r5() is False

    def test_get_effective_batch_size_with_override(self) -> None:
        """get_effective_batch_size respects max_events when set."""
        from k0.pipelines.p03.context import P03ManualTriggerOptions

        opts = P03ManualTriggerOptions(reason="test", max_events=100)

        # Override is smaller than default
        assert opts.get_effective_batch_size(500) == 100

        # Override is larger than default - should cap at default
        assert opts.get_effective_batch_size(50) == 50

    def test_get_effective_batch_size_without_override(self) -> None:
        """get_effective_batch_size uses default when max_events not set."""
        from k0.pipelines.p03.context import P03ManualTriggerOptions

        opts = P03ManualTriggerOptions(reason="test")

        assert opts.get_effective_batch_size(500) == 500

    def test_immutable(self) -> None:
        """P03ManualTriggerOptions should be immutable (frozen)."""
        from k0.pipelines.p03.context import P03ManualTriggerOptions

        opts = P03ManualTriggerOptions(reason="test")

        with pytest.raises(AttributeError):
            opts.reason = "new reason"  # type: ignore


# ============================================================
# Issue 1.3.3: Overlap Policy Validation Tests
# ============================================================


class TestP03OverlapPolicy:
    """Validate P03 overlap policy matches dossier §4.10 requirements."""

    @pytest.fixture
    def gate(self):
        """Create a fresh SingleFlightGate for testing."""
        from k0.scheduler.concurrency import SingleFlightGate

        return SingleFlightGate()

    @pytest.mark.asyncio
    async def test_interval_trigger_skipped_when_running(self, gate) -> None:
        """
        Dossier §4.10: INTERVAL triggers use SKIP policy.
        Repeated fires during in-flight run should be skipped.
        """
        import asyncio

        # Acquire and mark P03 as running
        result1 = await gate.try_acquire("P03_CONSOLIDATION", "p03_interval_90m", "interval")
        assert result1 is True
        gate.mark_running("P03_CONSOLIDATION", asyncio.create_task(asyncio.sleep(10)))

        # Second interval trigger should be SKIPPED
        result2 = await gate.try_acquire("P03_CONSOLIDATION", "p03_interval_90m", "interval")
        assert result2 is False

        # Check stats show skip (not queue)
        stats = gate.get_stats("P03_CONSOLIDATION")
        assert stats.total_skipped == 1
        assert stats.total_queued == 0

    @pytest.mark.asyncio
    async def test_threshold_trigger_queued_when_running(self, gate) -> None:
        """
        Dossier §4.10: THRESHOLD triggers use QUEUE policy (depth 1).
        Repeated fires during in-flight run should queue one pending run.
        """
        import asyncio

        # Acquire and mark P03 as running
        result1 = await gate.try_acquire("P03_CONSOLIDATION", "p03_threshold_500", "threshold")
        assert result1 is True
        gate.mark_running("P03_CONSOLIDATION", asyncio.create_task(asyncio.sleep(10)))

        # Second threshold trigger should be QUEUED
        result2 = await gate.try_acquire("P03_CONSOLIDATION", "p03_threshold_500", "threshold")
        assert result2 is False

        # Check stats show queue (not skip)
        stats = gate.get_stats("P03_CONSOLIDATION")
        assert stats.total_queued == 1
        assert stats.total_skipped == 0

    @pytest.mark.asyncio
    async def test_manual_trigger_queued_when_running(self, gate) -> None:
        """
        Dossier §4.10: MANUAL triggers use QUEUE policy (depth 1).
        Repeated fires during in-flight run should queue one pending run.
        """
        import asyncio

        # Acquire and mark P03 as running
        result1 = await gate.try_acquire("P03_CONSOLIDATION", "p03_manual", "manual")
        assert result1 is True
        gate.mark_running("P03_CONSOLIDATION", asyncio.create_task(asyncio.sleep(10)))

        # Second manual trigger should be QUEUED
        result2 = await gate.try_acquire("P03_CONSOLIDATION", "p03_manual", "manual")
        assert result2 is False

        # Check stats show queue (not skip)
        stats = gate.get_stats("P03_CONSOLIDATION")
        assert stats.total_queued == 1
        assert stats.total_skipped == 0

    @pytest.mark.asyncio
    async def test_threshold_coalesces_to_one_pending(self, gate) -> None:
        """
        Dossier §4.10: Queue depth = 1 means coalescing.
        Multiple threshold fires should coalesce to single pending run.
        """
        import asyncio

        # Acquire and mark P03 as running
        await gate.try_acquire("P03_CONSOLIDATION", "p03_threshold_500", "threshold")
        gate.mark_running("P03_CONSOLIDATION", asyncio.create_task(asyncio.sleep(10)))

        # Fire threshold 3 more times
        await gate.try_acquire("P03_CONSOLIDATION", "p03_threshold_500", "threshold")
        await gate.try_acquire("P03_CONSOLIDATION", "p03_threshold_500", "threshold")
        await gate.try_acquire("P03_CONSOLIDATION", "p03_threshold_500", "threshold")

        # Stats should show 3 queued operations (all coalesced)
        stats = gate.get_stats("P03_CONSOLIDATION")
        assert stats.total_queued == 3

        # But release should only return ONE pending run (coalesced)
        pending = await gate.release("P03_CONSOLIDATION")
        assert pending is not None
        assert pending.trigger_id == "p03_threshold_500"

        # No more pending after release
        assert not gate.is_running("P03_CONSOLIDATION")

    @pytest.mark.asyncio
    async def test_manual_coalesces_to_one_pending(self, gate) -> None:
        """
        Dossier §4.10: Manual triggers also coalesce (depth 1).
        Multiple manual fires should coalesce to single pending run.
        """
        import asyncio

        # Acquire and mark P03 as running
        await gate.try_acquire("P03_CONSOLIDATION", "p03_manual", "manual")
        gate.mark_running("P03_CONSOLIDATION", asyncio.create_task(asyncio.sleep(10)))

        # Fire manual 2 more times
        await gate.try_acquire("P03_CONSOLIDATION", "p03_manual_2", "manual")
        await gate.try_acquire("P03_CONSOLIDATION", "p03_manual_3", "manual")

        # Release should return only the LAST pending (coalesced)
        pending = await gate.release("P03_CONSOLIDATION")
        assert pending is not None
        assert pending.trigger_id == "p03_manual_3"  # Latest wins

    @pytest.mark.asyncio
    async def test_interval_fires_skipped_during_threshold_run(self, gate) -> None:
        """
        Mixed triggers: If running from THRESHOLD, INTERVAL should still SKIP.
        Policy is based on the incoming trigger type, not the running trigger.
        """
        import asyncio

        # Start from threshold trigger
        await gate.try_acquire("P03_CONSOLIDATION", "p03_threshold_500", "threshold")
        gate.mark_running("P03_CONSOLIDATION", asyncio.create_task(asyncio.sleep(10)))

        # Interval fires - should be SKIPPED (not queued)
        result = await gate.try_acquire("P03_CONSOLIDATION", "p03_interval_90m", "interval")
        assert result is False

        stats = gate.get_stats("P03_CONSOLIDATION")
        assert stats.total_skipped == 1
        assert stats.total_queued == 0

    @pytest.mark.asyncio
    async def test_threshold_queued_during_interval_run(self, gate) -> None:
        """
        Mixed triggers: If running from INTERVAL, THRESHOLD should QUEUE.
        Policy is based on the incoming trigger type, not the running trigger.
        """
        import asyncio

        # Start from interval trigger
        await gate.try_acquire("P03_CONSOLIDATION", "p03_interval_90m", "interval")
        gate.mark_running("P03_CONSOLIDATION", asyncio.create_task(asyncio.sleep(10)))

        # Threshold fires - should be QUEUED
        result = await gate.try_acquire("P03_CONSOLIDATION", "p03_threshold_500", "threshold")
        assert result is False

        stats = gate.get_stats("P03_CONSOLIDATION")
        assert stats.total_queued == 1
        assert stats.total_skipped == 0


class TestP03OverlapPolicyMapping:
    """Test that P03 trigger types map to correct overlap policies."""

    def test_interval_maps_to_skip(self) -> None:
        """INTERVAL trigger type should map to SKIP policy."""
        from k0.scheduler.concurrency import OverlapPolicy, SingleFlightGate

        gate = SingleFlightGate()
        policy = gate._get_overlap_policy("interval")
        assert policy == OverlapPolicy.SKIP

    def test_threshold_maps_to_queue(self) -> None:
        """THRESHOLD trigger type should map to QUEUE policy."""
        from k0.scheduler.concurrency import OverlapPolicy, SingleFlightGate

        gate = SingleFlightGate()
        policy = gate._get_overlap_policy("threshold")
        assert policy == OverlapPolicy.QUEUE

    def test_manual_maps_to_queue(self) -> None:
        """MANUAL trigger type should map to QUEUE policy."""
        from k0.scheduler.concurrency import OverlapPolicy, SingleFlightGate

        gate = SingleFlightGate()
        policy = gate._get_overlap_policy("manual")
        assert policy == OverlapPolicy.QUEUE

    def test_case_insensitive(self) -> None:
        """Policy lookup should be case-insensitive."""
        from k0.scheduler.concurrency import OverlapPolicy, SingleFlightGate

        gate = SingleFlightGate()

        assert gate._get_overlap_policy("INTERVAL") == OverlapPolicy.SKIP
        assert gate._get_overlap_policy("Interval") == OverlapPolicy.SKIP
        assert gate._get_overlap_policy("THRESHOLD") == OverlapPolicy.QUEUE
        assert gate._get_overlap_policy("MANUAL") == OverlapPolicy.QUEUE

    def test_unknown_type_defaults_to_queue(self) -> None:
        """Unknown trigger types should default to QUEUE (safe default)."""
        from k0.scheduler.concurrency import OverlapPolicy, SingleFlightGate

        gate = SingleFlightGate()
        policy = gate._get_overlap_policy("unknown_future_type")
        assert policy == OverlapPolicy.QUEUE


# ============================================================
# Issue 1.3.5: R0TriggerInputs Tests
# ============================================================


class TestR0TriggerInputs:
    """Tests for R0TriggerInputs dataclass (Issue 1.3.5)."""

    def test_frozen(self) -> None:
        """R0TriggerInputs is immutable."""
        from k0.pipelines.p03.context import R0TriggerInputs

        inputs = R0TriggerInputs(
            trigger_type="INTERVAL",
            trigger_reason="Test",
            trigger_id="test_id",
            fired_at_ms=1704067200000,
        )
        with pytest.raises(Exception):
            inputs.trigger_type = "MANUAL"  # type: ignore

    def test_defaults(self) -> None:
        """R0TriggerInputs has sensible defaults."""
        from k0.pipelines.p03.context import R0TriggerInputs

        inputs = R0TriggerInputs(
            trigger_type="INTERVAL",
            trigger_reason="Test",
            trigger_id="test_id",
            fired_at_ms=1704067200000,
        )
        assert inputs.max_events is None
        assert inputs.threshold_count is None
        assert inputs.batch_size == 500
        assert inputs.deadline_ms == 300000
        assert inputs.qos_band == "AMBER"
        assert inputs.skip_r5 is False
        assert inputs.target_space_id is None
        assert inputs.target_tenant_id is None

    def test_from_trigger_event_interval(self) -> None:
        """Create R0TriggerInputs from INTERVAL trigger."""
        from k0.pipelines.p03.context import R0TriggerInputs

        inputs = R0TriggerInputs.from_trigger_event(
            trigger_type="interval",
            trigger_id="p03_interval_90m",
            fired_at_ms=1704067200000,
            batch_size=1000,
        )
        assert inputs.trigger_type == "INTERVAL"
        assert inputs.trigger_id == "p03_interval_90m"
        assert inputs.trigger_reason == "Scheduled interval consolidation"
        assert inputs.batch_size == 1000
        assert inputs.get_effective_batch_size() == 1000

    def test_from_trigger_event_threshold(self) -> None:
        """Create R0TriggerInputs from THRESHOLD trigger."""
        from k0.pipelines.p03.context import R0TriggerInputs

        inputs = R0TriggerInputs.from_trigger_event(
            trigger_type="threshold",
            trigger_id="p03_threshold_500",
            fired_at_ms=1704067200000,
            threshold_count=523,
            batch_size=500,
        )
        assert inputs.trigger_type == "THRESHOLD"
        assert inputs.threshold_count == 523
        assert inputs.trigger_reason == "Threshold reached: 523 pending events"

    def test_from_trigger_event_manual_with_context(self) -> None:
        """Create R0TriggerInputs from MANUAL trigger with context."""
        from k0.pipelines.p03.context import R0TriggerInputs

        context = {
            "reason": "Pre-demo consolidation",
            "options": {
                "skip_r5": True,
                "max_events": 200,
                "space_id": "space_abc",
            },
        }
        inputs = R0TriggerInputs.from_trigger_event(
            trigger_type="manual",
            trigger_id="p03_manual",
            fired_at_ms=1704067200000,
            context=context,
            batch_size=500,
        )
        assert inputs.trigger_type == "MANUAL"
        assert inputs.trigger_reason == "Pre-demo consolidation"
        assert inputs.skip_r5 is True
        assert inputs.max_events == 200
        assert inputs.target_space_id == "space_abc"
        assert inputs.get_effective_batch_size() == 200  # min(200, 500)

    def test_effective_batch_size_with_override(self) -> None:
        """max_events overrides batch_size (takes minimum)."""
        from k0.pipelines.p03.context import R0TriggerInputs

        inputs = R0TriggerInputs(
            trigger_type="MANUAL",
            trigger_reason="Test",
            trigger_id="test",
            fired_at_ms=1704067200000,
            max_events=100,
            batch_size=500,
        )
        assert inputs.get_effective_batch_size() == 100

    def test_effective_batch_size_override_larger_than_default(self) -> None:
        """max_events larger than batch_size still respects batch_size."""
        from k0.pipelines.p03.context import R0TriggerInputs

        inputs = R0TriggerInputs(
            trigger_type="MANUAL",
            trigger_reason="Test",
            trigger_id="test",
            fired_at_ms=1704067200000,
            max_events=1000,
            batch_size=500,
        )
        # min(1000, 500) = 500
        assert inputs.get_effective_batch_size() == 500


class TestR0TriggerInputsBackpressure:
    """Tests for R0TriggerInputs backpressure policy (Issue 1.3.5)."""

    def test_backpressure_select_full(self) -> None:
        """SELECT_FULL when capacity exceeds pending."""
        from k0.pipelines.p03.context import BackpressureAction, R0TriggerInputs

        inputs = R0TriggerInputs(
            trigger_type="INTERVAL",
            trigger_reason="Test",
            trigger_id="test",
            fired_at_ms=1704067200000,
            batch_size=500,
        )
        action = inputs.evaluate_backpressure(pending_count=300, available_capacity=1000)
        assert action == BackpressureAction.SELECT_FULL

    def test_backpressure_select_reduced(self) -> None:
        """SELECT_REDUCED when capacity is limited but >= half batch."""
        from k0.pipelines.p03.context import BackpressureAction, R0TriggerInputs

        inputs = R0TriggerInputs(
            trigger_type="INTERVAL",
            trigger_reason="Test",
            trigger_id="test",
            fired_at_ms=1704067200000,
            batch_size=500,
        )
        # Capacity (300) < pending (1000) but >= batch_size // 2 (250)
        action = inputs.evaluate_backpressure(pending_count=1000, available_capacity=300)
        assert action == BackpressureAction.SELECT_REDUCED

    def test_backpressure_defer(self) -> None:
        """DEFER when capacity is too low."""
        from k0.pipelines.p03.context import BackpressureAction, R0TriggerInputs

        inputs = R0TriggerInputs(
            trigger_type="INTERVAL",
            trigger_reason="Test",
            trigger_id="test",
            fired_at_ms=1704067200000,
            batch_size=500,
        )
        # Capacity (100) < batch_size // 2 (250)
        action = inputs.evaluate_backpressure(pending_count=1000, available_capacity=100)
        assert action == BackpressureAction.DEFER

    def test_backpressure_zero_capacity(self) -> None:
        """DEFER when capacity is zero."""
        from k0.pipelines.p03.context import BackpressureAction, R0TriggerInputs

        inputs = R0TriggerInputs(
            trigger_type="INTERVAL",
            trigger_reason="Test",
            trigger_id="test",
            fired_at_ms=1704067200000,
        )
        action = inputs.evaluate_backpressure(pending_count=100, available_capacity=0)
        assert action == BackpressureAction.DEFER


class TestR0TriggerInputsFilters:
    """Tests for R0TriggerInputs filter methods (Issue 1.3.5)."""

    def test_has_space_filter_false(self) -> None:
        """has_space_filter returns False when no space targeted."""
        from k0.pipelines.p03.context import R0TriggerInputs

        inputs = R0TriggerInputs(
            trigger_type="INTERVAL",
            trigger_reason="Test",
            trigger_id="test",
            fired_at_ms=1704067200000,
        )
        assert inputs.has_space_filter() is False

    def test_has_space_filter_true(self) -> None:
        """has_space_filter returns True when space targeted."""
        from k0.pipelines.p03.context import R0TriggerInputs

        inputs = R0TriggerInputs(
            trigger_type="MANUAL",
            trigger_reason="Test",
            trigger_id="test",
            fired_at_ms=1704067200000,
            target_space_id="space_123",
        )
        assert inputs.has_space_filter() is True

    def test_has_tenant_filter_false(self) -> None:
        """has_tenant_filter returns False when no tenant targeted."""
        from k0.pipelines.p03.context import R0TriggerInputs

        inputs = R0TriggerInputs(
            trigger_type="INTERVAL",
            trigger_reason="Test",
            trigger_id="test",
            fired_at_ms=1704067200000,
        )
        assert inputs.has_tenant_filter() is False

    def test_has_tenant_filter_true(self) -> None:
        """has_tenant_filter returns True when tenant targeted."""
        from k0.pipelines.p03.context import R0TriggerInputs

        inputs = R0TriggerInputs(
            trigger_type="MANUAL",
            trigger_reason="Test",
            trigger_id="test",
            fired_at_ms=1704067200000,
            target_tenant_id="tenant_abc",
        )
        assert inputs.has_tenant_filter() is True


class TestR0TriggerInputsSerialization:
    """Tests for R0TriggerInputs serialization (Issue 1.3.5)."""

    def test_to_dict(self) -> None:
        """to_dict includes all fields and computed effective_batch_size."""
        from k0.pipelines.p03.context import R0TriggerInputs

        inputs = R0TriggerInputs(
            trigger_type="MANUAL",
            trigger_reason="Test reason",
            trigger_id="test_id",
            fired_at_ms=1704067200000,
            max_events=100,
            batch_size=500,
            deadline_ms=60000,
            qos_band="RED",
            skip_r5=True,
            target_space_id="space_1",
            target_tenant_id="tenant_1",
        )
        d = inputs.to_dict()

        assert d["trigger_type"] == "MANUAL"
        assert d["trigger_reason"] == "Test reason"
        assert d["trigger_id"] == "test_id"
        assert d["fired_at_ms"] == 1704067200000
        assert d["max_events"] == 100
        assert d["batch_size"] == 500
        assert d["deadline_ms"] == 60000
        assert d["qos_band"] == "RED"
        assert d["skip_r5"] is True
        assert d["target_space_id"] == "space_1"
        assert d["target_tenant_id"] == "tenant_1"
        assert d["effective_batch_size"] == 100  # min(100, 500)
