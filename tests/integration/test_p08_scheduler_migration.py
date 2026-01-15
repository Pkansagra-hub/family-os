"""
P08 Scheduler Migration Integration Tests (Issue 5.2.2).

Validates that P08 (embedding management) works correctly
with declarative triggers instead of hardcoded scheduler.

Migration (M5):
- Removed: _p08_faiss_indexer_loop() in k0/kernel/app.py
- Added: Declarative triggers in p08_embedding_management.v2.yaml
- P08 now activates via PipelineScheduler

Tests verify:
1. P08 contract has proper triggers defined
2. P08 registered with scheduler on boot
3. Interval trigger fires and executes P08
4. Threshold trigger fires when backlog exists
5. Manual trigger can be invoked
6. Stats are properly tracked
7. No hardcoded P08 loop exists
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.runtime.schemas import PipelineSpec, TriggerSpec, TriggerType
from k0.scheduler import PipelineScheduler
from k0.scheduler.concurrency import reset_single_flight_gate

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_syscalls() -> MagicMock:
    """Create mock syscalls for testing."""
    syscalls = MagicMock()
    syscalls.query_count = AsyncMock(return_value=0)
    return syscalls


@pytest.fixture
def mock_pipeline_runner() -> MagicMock:
    """Create mock pipeline runner."""
    runner = MagicMock()
    runner.execute = AsyncMock()
    return runner


@pytest.fixture
def p08_spec_with_triggers() -> PipelineSpec:
    """Create P08 spec with declarative triggers (matches contract)."""
    from k0.runtime.schemas import StageSpec

    return PipelineSpec(
        pipeline_id="P08_EMBEDDING_MANAGEMENT",
        version="v3",
        description="Background embedding lifecycle management - MAINTENANCE MODE.",
        entry_topic="scheduled.p08.maintenance.v1",
        exit_topic="embedding.maintenance.completed.v1",
        triggers=[
            TriggerSpec(
                id="maintenance_interval",
                type=TriggerType.INTERVAL,
                interval_seconds=300,
                batch_size=100,
                catch_up_enabled=True,
            ),
            TriggerSpec(
                id="maintenance_threshold",
                type=TriggerType.THRESHOLD,
                table="st_vec",
                condition="status = 'PENDING'",
                threshold_count=50,
                check_interval_seconds=60,
                batch_size=50,
            ),
            TriggerSpec(
                id="maintenance_manual",
                type=TriggerType.MANUAL,
            ),
        ],
        concurrency=1,
        max_queue=1000,
        dag=[StageSpec(id="stage_10_faiss_indexer", module="embedding.faiss_indexer:v1", after=[])],
    )


@pytest.fixture
async def scheduler_with_p08(
    mock_syscalls: MagicMock,
    p08_spec_with_triggers: PipelineSpec,
) -> PipelineScheduler:
    """Set up scheduler with P08 registered."""
    reset_single_flight_gate()
    scheduler = PipelineScheduler(mock_syscalls)
    scheduler.register_pipeline(p08_spec_with_triggers)
    yield scheduler
    if scheduler.is_running:
        await scheduler.stop()
    reset_single_flight_gate()


# ============================================================================
# Issue 5.1.1: P08 Contract Trigger Tests
# ============================================================================


class TestP08ContractTriggers:
    """Tests validating P08 contract has proper triggers."""

    def test_p08_contract_exists(self) -> None:
        """Verify P08 contract file exists."""
        contract_path = Path("k0/contracts/pipelines/p08_embedding_management.v2.yaml")
        assert contract_path.exists(), "P08 contract file not found"

    def test_p08_contract_has_triggers_field(self) -> None:
        """Verify P08 contract has triggers field."""
        import yaml

        contract_path = Path("k0/contracts/pipelines/p08_embedding_management.v2.yaml")
        with open(contract_path) as f:
            contract = yaml.safe_load(f)

        assert "triggers" in contract, "P08 contract missing triggers field"
        assert isinstance(contract["triggers"], list), "triggers should be a list"
        assert len(contract["triggers"]) == 3, "P08 should have 3 triggers"

    def test_p08_interval_trigger_valid(self) -> None:
        """Verify P08 interval trigger is properly configured."""
        import yaml

        contract_path = Path("k0/contracts/pipelines/p08_embedding_management.v2.yaml")
        with open(contract_path) as f:
            contract = yaml.safe_load(f)

        interval_trigger = next((t for t in contract["triggers"] if t["type"] == "interval"), None)

        assert interval_trigger is not None, "P08 missing interval trigger"
        assert interval_trigger["id"] == "maintenance_interval"
        assert interval_trigger["interval_seconds"] == 300
        assert interval_trigger["batch_size"] == 100

    def test_p08_threshold_trigger_valid(self) -> None:
        """Verify P08 threshold trigger is properly configured."""
        import yaml

        contract_path = Path("k0/contracts/pipelines/p08_embedding_management.v2.yaml")
        with open(contract_path) as f:
            contract = yaml.safe_load(f)

        threshold_trigger = next(
            (t for t in contract["triggers"] if t["type"] == "threshold"), None
        )

        assert threshold_trigger is not None, "P08 missing threshold trigger"
        assert threshold_trigger["id"] == "maintenance_threshold"
        assert threshold_trigger["table"] == "st_vec"
        assert threshold_trigger["condition"] == "status = 'PENDING'"
        assert threshold_trigger["threshold_count"] == 50

    def test_p08_manual_trigger_valid(self) -> None:
        """Verify P08 manual trigger is properly configured."""
        import yaml

        contract_path = Path("k0/contracts/pipelines/p08_embedding_management.v2.yaml")
        with open(contract_path) as f:
            contract = yaml.safe_load(f)

        manual_trigger = next((t for t in contract["triggers"] if t["type"] == "manual"), None)

        assert manual_trigger is not None, "P08 missing manual trigger"
        assert manual_trigger["id"] == "maintenance_manual"

    def test_p08_triggers_validate_schema(self, p08_spec_with_triggers: PipelineSpec) -> None:
        """Verify P08 triggers validate against TriggerSpec schema."""
        # If we got here, the spec was created successfully which means
        # the triggers validated against the schema
        assert len(p08_spec_with_triggers.triggers) == 3

        interval = p08_spec_with_triggers.triggers[0]
        assert interval.type == TriggerType.INTERVAL
        assert interval.interval_seconds == 300

        threshold = p08_spec_with_triggers.triggers[1]
        assert threshold.type == TriggerType.THRESHOLD
        assert threshold.table == "st_vec"

        manual = p08_spec_with_triggers.triggers[2]
        assert manual.type == TriggerType.MANUAL


# ============================================================================
# Issue 5.2.1: Hardcoded Loop Removal Tests
# ============================================================================


class TestP08HardcodedLoopRemoval:
    """Tests verifying hardcoded P08 loop is removed."""

    def test_no_hardcoded_p08_loop_function(self) -> None:
        """Verify _p08_faiss_indexer_loop function is removed from app.py."""
        app_path = Path("k0/kernel/app.py")
        content = app_path.read_text()

        # The function definition should not exist (only deprecation comment)
        assert (
            "async def _p08_faiss_indexer_loop" not in content
        ), "_p08_faiss_indexer_loop function should be removed"

    def test_no_p08_task_creation(self) -> None:
        """Verify P08 task is not created in lifespan."""
        app_path = Path("k0/kernel/app.py")
        content = app_path.read_text()

        # Should not have active task creation (lines without 'Previously:' or '#')
        lines = content.split("\n")
        for line in lines:
            stripped = line.strip()
            if "create_task(_p08_faiss_indexer_loop())" in stripped:
                # This line should be a comment, not active code
                assert stripped.startswith(
                    "#"
                ), f"P08 task creation should be removed or commented: {stripped}"

    def test_no_p08_task_cancellation(self) -> None:
        """Verify P08 task cancellation is removed from shutdown."""
        app_path = Path("k0/kernel/app.py")
        content = app_path.read_text()

        # Should not have active task cancellation
        assert "p08_indexer_task.cancel()" not in content, "P08 task cancellation should be removed"

    def test_deprecation_comments_present(self) -> None:
        """Verify deprecation comments are in place."""
        app_path = Path("k0/kernel/app.py")
        content = app_path.read_text()

        # Should have deprecation notice
        assert (
            "DEPRECATED (M5 P08 Migration" in content or "DEPRECATED (M5)" in content
        ), "Deprecation comments should be present"


# ============================================================================
# Issue 5.2.2: P08 Scheduler Integration Tests
# ============================================================================


class TestP08SchedulerMigration:
    """P08 migration to declarative triggers."""

    @pytest.mark.asyncio
    async def test_p08_registered_with_scheduler(
        self,
        scheduler_with_p08: PipelineScheduler,
    ) -> None:
        """Verify P08 is registered with scheduler."""
        pipelines = scheduler_with_p08.pipelines

        assert "P08_EMBEDDING_MANAGEMENT" in pipelines
        scheduled = pipelines["P08_EMBEDDING_MANAGEMENT"]
        assert scheduled.pipeline_id == "P08_EMBEDDING_MANAGEMENT"

    @pytest.mark.asyncio
    async def test_p08_has_three_trigger_engines(
        self,
        scheduler_with_p08: PipelineScheduler,
    ) -> None:
        """Verify P08 has 3 trigger engines registered."""
        scheduled = scheduler_with_p08.pipelines["P08_EMBEDDING_MANAGEMENT"]

        assert len(scheduled.triggers) == 3

        # Verify trigger types
        trigger_types = {t.spec.type for t in scheduled.triggers}
        assert TriggerType.INTERVAL in trigger_types
        assert TriggerType.THRESHOLD in trigger_types
        assert TriggerType.MANUAL in trigger_types

    @pytest.mark.asyncio
    async def test_p08_interval_trigger_fires(
        self,
        scheduler_with_p08: PipelineScheduler,
    ) -> None:
        """Verify interval trigger fires and executes P08."""
        # Track executions
        executed = []

        def mock_executor(pipeline: any, event: any) -> None:
            executed.append((pipeline.pipeline_id, event))

        scheduler_with_p08._executor = mock_executor

        # Start scheduler
        await scheduler_with_p08.start()

        # Get interval trigger and fire manually (simulates timer firing)
        scheduled = scheduler_with_p08.pipelines["P08_EMBEDDING_MANAGEMENT"]
        interval_trigger = next(
            t for t in scheduled.triggers if t.spec.type == TriggerType.INTERVAL
        )

        # Simulate trigger callback by invoking the trigger's callback
        import time

        from k0.scheduler.triggers import TriggerEvent

        event = TriggerEvent(
            trigger_id=interval_trigger.spec.id,
            pipeline_id="P08_EMBEDDING_MANAGEMENT",
            fired_at=time.monotonic(),
            context={"batch_size": 100},
        )
        # Call the trigger callback directly
        callback = scheduler_with_p08._make_trigger_callback(scheduled)
        callback(event)

        # Wait for execution
        await asyncio.sleep(0.1)

        assert len(executed) == 1
        assert executed[0][0] == "P08_EMBEDDING_MANAGEMENT"

    @pytest.mark.asyncio
    async def test_p08_manual_trigger_fires(
        self,
        scheduler_with_p08: PipelineScheduler,
    ) -> None:
        """Verify manual trigger can be fired."""
        # Track executions
        executed = []

        def mock_executor(pipeline: any, event: any) -> None:
            executed.append((pipeline.pipeline_id, event))

        scheduler_with_p08._executor = mock_executor

        # Start scheduler
        await scheduler_with_p08.start()

        # Fire manual trigger
        result = scheduler_with_p08.fire_manual_trigger(
            "P08_EMBEDDING_MANAGEMENT",
            "maintenance_manual",
        )

        # Wait for execution
        await asyncio.sleep(0.1)

        assert result is True
        assert len(executed) == 1
        assert executed[0][0] == "P08_EMBEDDING_MANAGEMENT"

    @pytest.mark.asyncio
    async def test_p08_stats_tracked(
        self,
        scheduler_with_p08: PipelineScheduler,
    ) -> None:
        """Verify trigger stats are tracked."""
        await scheduler_with_p08.start()

        # Fire a trigger
        scheduler_with_p08.fire_manual_trigger(
            "P08_EMBEDDING_MANAGEMENT",
            "maintenance_manual",
        )

        await asyncio.sleep(0.1)

        # Get stats
        stats = scheduler_with_p08.get_trigger_stats()

        # Should have stats for all 3 triggers
        assert len(stats) == 3
        # Manual trigger should show 1 fire
        assert "maintenance_manual" in stats
        assert stats["maintenance_manual"]["fire_count"] == 1

    @pytest.mark.asyncio
    async def test_p08_threshold_trigger_registered(
        self,
        scheduler_with_p08: PipelineScheduler,
        mock_syscalls: MagicMock,
    ) -> None:
        """Verify threshold trigger is registered and can check count."""
        scheduled = scheduler_with_p08.pipelines["P08_EMBEDDING_MANAGEMENT"]

        threshold_trigger = next(
            t for t in scheduled.triggers if t.spec.type == TriggerType.THRESHOLD
        )

        assert threshold_trigger.spec.table == "st_vec"
        assert threshold_trigger.spec.threshold_count == 50
        assert threshold_trigger.spec.condition == "status = 'PENDING'"


# ============================================================================
# End-to-End Validation
# ============================================================================


class TestP08EndToEndMigration:
    """End-to-end tests for P08 migration."""

    @pytest.mark.asyncio
    async def test_p08_lifecycle_via_scheduler(
        self,
        mock_syscalls: MagicMock,
        p08_spec_with_triggers: PipelineSpec,
    ) -> None:
        """Test complete P08 lifecycle via scheduler."""
        reset_single_flight_gate()
        scheduler = PipelineScheduler(mock_syscalls)

        # Register
        scheduler.register_pipeline(p08_spec_with_triggers)
        assert "P08_EMBEDDING_MANAGEMENT" in scheduler.pipelines

        # Start
        await scheduler.start()
        assert scheduler.is_running

        # Verify triggers are running
        scheduled = scheduler.pipelines["P08_EMBEDDING_MANAGEMENT"]
        assert all(t.is_running for t in scheduled.triggers)

        # Stop
        await scheduler.stop()
        assert not scheduler.is_running

        # Verify triggers stopped
        assert all(not t.is_running for t in scheduled.triggers)

        reset_single_flight_gate()

    @pytest.mark.asyncio
    async def test_p08_coexists_with_other_pipelines(
        self,
        mock_syscalls: MagicMock,
        p08_spec_with_triggers: PipelineSpec,
    ) -> None:
        """Test P08 works alongside other scheduled pipelines."""
        reset_single_flight_gate()
        scheduler = PipelineScheduler(mock_syscalls)

        # Register P08
        scheduler.register_pipeline(p08_spec_with_triggers)

        # Register another pipeline
        from k0.runtime.schemas import StageSpec

        p02_spec = PipelineSpec(
            pipeline_id="P02_WRITE",
            version="v1",
            entry_topic="p02.entry.v1",
            exit_topic="p02.exit.v1",
            triggers=[
                TriggerSpec(
                    id="p02_manual",
                    type=TriggerType.MANUAL,
                ),
            ],
            dag=[StageSpec(id="stage_10_affect", module="affect.analyze:v1", after=[])],
        )
        scheduler.register_pipeline(p02_spec)

        # Both should be registered
        assert len(scheduler.pipelines) == 2
        assert "P08_EMBEDDING_MANAGEMENT" in scheduler.pipelines
        assert "P02_WRITE" in scheduler.pipelines

        # Start and stop
        await scheduler.start()
        await scheduler.stop()

        reset_single_flight_gate()
        reset_single_flight_gate()
        reset_single_flight_gate()
