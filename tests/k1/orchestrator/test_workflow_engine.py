"""WorkflowEngine tests (Epic 7.1.5) with factory-backed real adapters.

All tests obtain WorkflowEngine via OrchestratorFactory and use real in-memory
(or SQLite) adapters. No fake adapter classes are introduced in this suite.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import patch
from uuid import UUID

import pytest

from k1.fabric.types import CapabilityResult
from k1.orchestrator.adapters.mock_fabric_adapter import MockFabricAdapter
from k1.orchestrator.adapters.test_delta_adapter import TestDeltaAdapter
from k1.orchestrator.adapters.test_event_adapter import TestEventAdapter
from k1.orchestrator.adapters.test_mailbox_adapter import TestMailboxAdapter
from k1.orchestrator.adapters.test_workflow_storage_adapter import TestWorkflowStorageAdapter
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.types import (
    AggregatedResult,
    PlanStep,
    ProcessingContext,
    ProcessResult,
    RegistryEntry,
    StepResult,
    StepStatus,
    TriggerType,
    WorkflowRunRequest,
)
from k1.orchestrator.workflows.cross_workflow_resolver import MaxDepthError
from k1.orchestrator.workflows.persistence.sqlite_adapter import SQLiteWorkflowAdapter
from k1.orchestrator.workflows.workflow_engine import WorkflowEngine
from k1.orchestrator.workflows.workflow_types import TriggerSpec, WorkflowSpec


async def _svc():
    service = await OrchestratorFactory.create_standalone()
    engine: WorkflowEngine = service._workflow_engine  # type: ignore[assignment]
    fabric: MockFabricAdapter = service._fabric_port  # type: ignore[assignment]
    storage: TestWorkflowStorageAdapter = engine.registry._storage  # type: ignore[assignment]
    delta: TestDeltaAdapter = service._delta_port  # type: ignore[assignment]
    event: TestEventAdapter = service._event_port  # type: ignore[assignment]
    mailbox: TestMailboxAdapter = service._mailbox  # type: ignore[assignment]
    return service, engine, fabric, storage, delta, event, mailbox


def _entry(name: str, *, safety_band_min: str = "GREEN") -> RegistryEntry:
    return RegistryEntry(
        name=name,
        provider_type="tool",
        safety_band_min=safety_band_min,
        availability="AVAILABLE",
    )


def _step(
    sid: str,
    capability: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    deps: Optional[List[str]] = None,
) -> PlanStep:
    return PlanStep(
        id=sid,
        capability=capability,
        params=params or {},
        deps=deps or [],
    )


def _spec(
    workflow_id: str,
    *,
    name: str = "wf",
    steps: Optional[List[PlanStep]] = None,
    dependencies: Optional[Dict[str, List[str]]] = None,
    trigger: Optional[TriggerSpec] = None,
    active: bool = True,
    version: str = "1.0.0",
) -> WorkflowSpec:
    return WorkflowSpec(
        workflow_id=workflow_id,
        name=name,
        source_plan_id=f"plan-{workflow_id}",
        version=version,
        trigger=trigger or TriggerSpec(type=TriggerType.MANUAL),
        steps=steps or [_step("s1", "tool.echo")],
        dependencies=dependencies or {},
        active=active,
    )


def _req(workflow_id: str, *, trace_id: str = "trace-1") -> WorkflowRunRequest:
    return WorkflowRunRequest(
        workflow_id=workflow_id,
        version="1.0.0",
        trigger_type=TriggerType.MANUAL,
        trace_id=trace_id,
    )


def _ctx(trace_id: str = "trace-1") -> ProcessingContext:
    return ProcessingContext(trace_id=trace_id, request_id=f"req-{trace_id}", tier="HIGH")


class TestWorkflowRegistryViaEngine:
    @pytest.mark.asyncio
    async def test_save_and_load_workflow(self) -> None:
        _, engine, _, _, _, _, _ = await _svc()
        spec = _spec("wf-reg-1", name="daily")

        workflow_id = await engine.registry.save(spec)
        loaded = await engine.registry.get(workflow_id)

        assert workflow_id == "wf-reg-1"
        assert loaded is not None
        assert loaded.name == "daily"

    @pytest.mark.asyncio
    async def test_list_active_and_soft_delete(self) -> None:
        _, engine, _, _, _, _, _ = await _svc()
        await engine.registry.save(_spec("wf-reg-2", name="active", active=True))
        await engine.registry.save(_spec("wf-reg-3", name="inactive", active=False))

        active_before = await engine.registry.list_active()
        assert {w.workflow_id for w in active_before} == {"wf-reg-2"}

        await engine.registry.delete("wf-reg-2")
        active_after = await engine.registry.list_active()
        assert active_after == []

    @pytest.mark.asyncio
    async def test_duplicate_name_is_rejected(self) -> None:
        _, engine, _, _, _, _, _ = await _svc()
        await engine.registry.save(_spec("wf-reg-4", name="same-name"))

        with pytest.raises(ValueError, match="already exists"):
            await engine.registry.save(_spec("wf-reg-5", name="same-name"))


class TestCompilerViaEngine:
    @pytest.mark.asyncio
    async def test_compile_success_returns_committed_plan(self) -> None:
        _, engine, fabric, _, _, _, _ = await _svc()
        fabric.register_capability("tool.compile.ok", _entry("tool.compile.ok"))
        spec = _spec(
            "wf-comp-1",
            steps=[_step("s1", "tool.compile.ok", params={"x": 1})],
        )

        result = await engine.compiler.compile(spec)

        assert result.success is True
        assert result.compiled_plan is not None
        assert result.compiled_plan.steps[0].capability == "tool.compile.ok"

    @pytest.mark.asyncio
    async def test_compile_unknown_capability_creates_gap(self) -> None:
        _, engine, _, storage, delta, _, _ = await _svc()
        spec = _spec("wf-comp-2", steps=[_step("s1", "tool.compile.missing")])

        result = await engine.compiler.compile(spec)

        assert result.success is False
        assert result.compiled_plan is None
        assert any(g.gap_type == "CAPABILITY_REMOVED" for g in result.gaps)
        assert any(g.workflow_id == "wf-comp-2" for g in storage.gaps)
        delta.assert_emitted("k1.orchestration.gap.detected", count=1)


class TestSchedulerViaEngine:
    @pytest.mark.asyncio
    async def test_scheduler_start_stop_lifecycle(self) -> None:
        _, engine, _, _, _, _, _ = await _svc()

        await engine.scheduler.start()
        assert engine.scheduler.running is True

        await engine.scheduler.stop()
        assert engine.scheduler.running is False

    @pytest.mark.asyncio
    async def test_manual_trigger_enqueues_workflow_request(self) -> None:
        _, engine, _, storage, _, _, mailbox = await _svc()
        spec = _spec("wf-sch-1", trigger=TriggerSpec(type=TriggerType.MANUAL))
        await engine.registry.save(spec)
        await storage.save_trigger(spec.workflow_id, spec.trigger)

        await engine.scheduler._tick()

        assert mailbox.depth() == 1
        msg = mailbox.dequeue()
        assert isinstance(msg, WorkflowRunRequest)
        assert msg.workflow_id == "wf-sch-1"
        assert msg.trigger_type == TriggerType.MANUAL

        next_fire, last_fire = storage.trigger_times["wf-sch-1"]
        assert last_fire > 0
        assert next_fire > 1.0e20  # MANUAL uses MAX_FLOAT sentinel

    @pytest.mark.asyncio
    async def test_cron_trigger_updates_next_fire_and_last_fire(self) -> None:
        _, engine, _, storage, _, _, mailbox = await _svc()
        trigger = TriggerSpec(type=TriggerType.CRON, schedule="*/5 * * * *")
        spec = _spec("wf-sch-2", trigger=trigger)
        await engine.registry.save(spec)
        await storage.save_trigger(spec.workflow_id, spec.trigger)

        await engine.scheduler._tick()

        assert mailbox.depth() == 1
        next_fire, last_fire = storage.trigger_times["wf-sch-2"]
        assert next_fire > last_fire


class TestGapDetectorViaEngine:
    @pytest.mark.asyncio
    async def test_capability_removed_deactivates_workflow(self) -> None:
        _, engine, _, storage, delta, _, _ = await _svc()
        spec = _spec("wf-gap-1", steps=[_step("s1", "tool.gap.missing")])
        await engine.registry.save(spec)

        await engine.gap_detector._process_capability("tool.gap.missing")

        loaded = await engine.registry.get("wf-gap-1")
        assert loaded is not None
        assert loaded.active is False
        assert len(storage.gaps) >= 1
        assert any(topic == "k1.orchestration.gap.detected" for topic, _, _ in delta.emitted)

    @pytest.mark.asyncio
    async def test_no_affected_workflows_is_noop(self) -> None:
        _, engine, _, storage, delta, _, _ = await _svc()
        await engine.registry.save(_spec("wf-gap-2", steps=[_step("s1", "tool.other")]))

        before = len(storage.gaps)
        await engine.gap_detector._process_capability("tool.unrelated")

        assert len(storage.gaps) == before
        assert delta.get_emitted("k1.orchestration.gap.detected") == []


class TestCrossWorkflowViaEngine:
    @pytest.mark.asyncio
    async def test_resolve_subworkflow_plan(self) -> None:
        _, engine, fabric, _, _, _, _ = await _svc()
        fabric.register_capability("tool.sub.action", _entry("tool.sub.action"))
        await engine.registry.save(_spec("subwf", steps=[_step("s1", "tool.sub.action")]))

        parent_step = _step("p1", "workflow.run.subwf")
        resolved = await engine.cross_resolver.resolve(parent_step, {}, current_depth=1)

        assert resolved is not None
        assert resolved.request_id == "subwf"

    @pytest.mark.asyncio
    async def test_depth_guard_enforces_max_depth(self) -> None:
        _, engine, fabric, _, _, _, _ = await _svc()
        fabric.register_capability("tool.sub.action", _entry("tool.sub.action"))
        await engine.registry.save(_spec("subwf2", steps=[_step("s1", "tool.sub.action")]))

        parent_step = _step("p1", "workflow.run.subwf2")
        max_depth = engine.cross_resolver._depth_guard.max_depth

        with pytest.raises(MaxDepthError):
            await engine.cross_resolver.resolve(parent_step, {}, current_depth=max_depth)


class TestExecuteWorkflowViaEngine:
    @pytest.mark.asyncio
    async def test_execute_workflow_success(self) -> None:
        _, engine, fabric, storage, _, _, _ = await _svc()
        fabric.register_capability("tool.exec.ok", _entry("tool.exec.ok"))
        await engine.registry.save(_spec("wf-run-1", steps=[_step("s1", "tool.exec.ok")]))

        result = await engine.execute_workflow(
            _req("wf-run-1", trace_id="trace-run-1"), _ctx("trace-run-1")
        )

        assert result == ProcessResult.COMPLETED
        runs = await storage.get_runs("wf-run-1")
        assert len(runs) >= 1
        assert runs[0].status.value in {"COMPLETED", "RUNNING"}

    @pytest.mark.asyncio
    async def test_execute_workflow_compile_failure(self) -> None:
        _, engine, _, storage, _, _, _ = await _svc()
        await engine.registry.save(_spec("wf-run-2", steps=[_step("s1", "tool.exec.missing")]))

        result = await engine.execute_workflow(
            _req("wf-run-2", trace_id="trace-run-2"), _ctx("trace-run-2")
        )

        assert result == ProcessResult.FAILED
        runs = await storage.get_runs("wf-run-2")
        assert len(runs) >= 1
        assert runs[0].status.value == "FAILED"

    @pytest.mark.asyncio
    async def test_execute_workflow_partial_failure_returns_degraded(self) -> None:
        _, engine, fabric, _, _, _, _ = await _svc()
        fabric.register_capability("tool.exec.ok2", _entry("tool.exec.ok2"))
        fabric.register_capability("tool.exec.fail2", _entry("tool.exec.fail2"))
        fabric.script_result(
            "tool.exec.fail2",
            CapabilityResult.failure_result(
                request_id="r-fail",
                error_code="boom",
                error_message="failed",
                retriable=False,
                provider_id="mock",
                trace_id="trace-run-3",
            ),
        )

        await engine.registry.save(
            _spec(
                "wf-run-3",
                steps=[_step("s1", "tool.exec.ok2"), _step("s2", "tool.exec.fail2")],
                dependencies={},
            )
        )

        result = await engine.execute_workflow(
            _req("wf-run-3", trace_id="trace-run-3"), _ctx("trace-run-3")
        )

        assert result == ProcessResult.DEGRADED

    @pytest.mark.asyncio
    async def test_concurrent_run_aborts_previous_running_run(self) -> None:
        _, engine, fabric, _, delta, _, _ = await _svc()
        fabric.register_capability("tool.exec.concurrent", _entry("tool.exec.concurrent"))
        await engine.registry.save(_spec("wf-run-4", steps=[_step("s1", "tool.exec.concurrent")]))

        async def _slow_execute(self: Any, plan: Any, snapshot: Any) -> AggregatedResult:
            await asyncio.sleep(0.05)
            return AggregatedResult.from_dag(
                plan_id=plan.plan_id,
                step_results=[
                    StepResult(
                        step_id="s1",
                        capability_name="tool.exec.concurrent",
                        status=StepStatus.COMPLETED,
                        result=CapabilityResult.success_result(
                            request_id="r-ok",
                            data={"ok": True},
                            provider_id="mock",
                            trace_id=plan.trace_id,
                        ),
                    )
                ],
                compensations=[],
                trace_id=plan.trace_id,
                duration_ms=50,
            )

        with patch.object(type(engine._dag_executor), "execute", _slow_execute):
            t1 = asyncio.create_task(
                engine.execute_workflow(_req("wf-run-4", trace_id="trace-a"), _ctx("trace-a"))
            )
            await asyncio.sleep(0.01)
            r2 = await engine.execute_workflow(
                _req("wf-run-4", trace_id="trace-b"), _ctx("trace-b")
            )
            r1 = await t1

        assert r1 in {ProcessResult.COMPLETED, ProcessResult.DEGRADED}
        assert r2 in {ProcessResult.COMPLETED, ProcessResult.DEGRADED}
        assert any(
            topic == "k1.orchestration.workflow.run_aborted" for topic, _, _ in delta.emitted
        )

    @pytest.mark.asyncio
    async def test_cron_trigger_generates_fresh_root_trace(self) -> None:
        _, engine, fabric, _, delta, _, _ = await _svc()
        fabric.register_capability("tool.exec.cron", _entry("tool.exec.cron"))
        await engine.registry.save(_spec("wf-run-cron", steps=[_step("s1", "tool.exec.cron")]))

        req = WorkflowRunRequest(
            workflow_id="wf-run-cron",
            version="1.0.0",
            trigger_type=TriggerType.CRON,
            trace_id="",
            trigger_context={"triggered_at": 1700000000.0},
        )
        ctx = _ctx("ctx-trace-cron")

        result = await engine.execute_workflow(req, ctx)

        assert result in {ProcessResult.COMPLETED, ProcessResult.DEGRADED}
        started = [p for t, p, _ in delta.emitted if t == "k1.orchestration.workflow.run_started"]
        assert started
        emitted_trace = started[-1]["trace_id"]
        assert emitted_trace != "ctx-trace-cron"
        UUID(emitted_trace)

    @pytest.mark.asyncio
    async def test_parent_trace_id_is_propagated_in_context(self) -> None:
        _, engine, fabric, _, _, _, _ = await _svc()
        fabric.register_capability("tool.exec.parent", _entry("tool.exec.parent"))
        await engine.registry.save(_spec("wf-run-parent", steps=[_step("s1", "tool.exec.parent")]))

        req = WorkflowRunRequest(
            workflow_id="wf-run-parent",
            version="1.0.0",
            trigger_type=TriggerType.EVENT,
            trace_id="child-trace",
            trigger_context={"parent_trace_id": "parent-trace-1"},
        )
        ctx = _ctx("child-trace")

        result = await engine.execute_workflow(req, ctx)

        assert result in {ProcessResult.COMPLETED, ProcessResult.DEGRADED}
        assert ctx.parent_trace_id == "parent-trace-1"


class TestWorkflowEngineSaveWorkflow:
    @pytest.mark.asyncio
    async def test_save_workflow_v1_returns_failed(self) -> None:
        _, engine, _, _, _, _, _ = await _svc()
        from k1.orchestrator.types import WorkflowSaveRequest

        req = WorkflowSaveRequest(
            committed_plan_id="plan-x",
            workflow_name="save-me",
            trigger_spec=TriggerSpec(type=TriggerType.MANUAL),
            trace_id="trace-save",
        )

        result = await engine.save_workflow(req, _ctx("trace-save"))

        assert result == ProcessResult.FAILED


class TestSQLitePersistenceViaWorkflowEngine:
    @pytest.mark.asyncio
    async def test_sqlite_workflow_save_load_roundtrip(self, tmp_path: Path) -> None:
        db = SQLiteWorkflowAdapter(str(tmp_path / "wf_roundtrip.db"))
        service = await OrchestratorFactory.create_for_testing(overrides={"storage": db})
        engine: WorkflowEngine = service._workflow_engine  # type: ignore[assignment]

        try:
            spec = _spec("wf-sql-1", name="sqlite-roundtrip", steps=[_step("s1", "tool.sql.ok")])
            await engine.registry.save(spec)
            loaded = await engine.registry.get("wf-sql-1")

            assert loaded is not None
            assert loaded.name == "sqlite-roundtrip"
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_sqlite_trigger_state_survives_restart(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "wf_restart.db")

        db1 = SQLiteWorkflowAdapter(db_path)
        try:
            await db1.save_workflow(_spec("wf-sql-2", steps=[_step("s1", "tool.sql.ok")]))
            await db1.save_trigger("wf-sql-2", TriggerSpec(type=TriggerType.MANUAL))
            await db1.update_trigger_state("wf-sql-2", next_fire=100.0, last_fire=10.0)
        finally:
            db1.close()

        db2 = SQLiteWorkflowAdapter(db_path)
        try:
            due_50 = await db2.get_due_triggers(50.0)
            due_150 = await db2.get_due_triggers(150.0)

            assert due_50 == []
            assert any(wf_id == "wf-sql-2" for wf_id, _ in due_150)
        finally:
            db2.close()

    @pytest.mark.asyncio
    async def test_sqlite_run_manifest_audit_trail_written(self, tmp_path: Path) -> None:
        db = SQLiteWorkflowAdapter(str(tmp_path / "wf_runs.db"))
        service = await OrchestratorFactory.create_for_testing(overrides={"storage": db})
        engine: WorkflowEngine = service._workflow_engine  # type: ignore[assignment]
        fabric: MockFabricAdapter = service._fabric_port  # type: ignore[assignment]

        try:
            fabric.register_capability("tool.sql.exec", _entry("tool.sql.exec"))
            await engine.registry.save(_spec("wf-sql-3", steps=[_step("s1", "tool.sql.exec")]))

            outcome = await engine.execute_workflow(
                _req("wf-sql-3", trace_id="trace-sql-3"), _ctx("trace-sql-3")
            )
            runs = await db.get_runs("wf-sql-3", limit=10)

            assert outcome in {ProcessResult.COMPLETED, ProcessResult.DEGRADED}
            assert len(runs) >= 1
            assert any(r.get("workflow_id") == "wf-sql-3" for r in runs)
        finally:
            db.close()
