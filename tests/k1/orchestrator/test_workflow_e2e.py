"""Epic 7.3.3 -- WORKFLOW tier end-to-end integration tests.

Goal:
- Validate workflow pipeline through public API:
  WorkflowRunRequest -> process() -> WorkflowEngine -> compile -> DAG execute.
- Use OrchestratorFactory with real test adapters (no mocks).
- Assert real wiring across scheduler, storage, bridge audit, and emitted events.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from k1.orchestrator.events import ORCH_DAG_COMPLETED, ORCH_DAG_STARTED
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.types import (
    PlanStep,
    ProcessResult,
    RegistryEntry,
    TriggerSpec,
    TriggerType,
    WorkflowRunRequest,
)
from k1.orchestrator.workflows.cross_workflow_resolver import MaxDepthError
from k1.orchestrator.workflows.workflow_types import WorkflowSpec


def _entry(name: str) -> RegistryEntry:
    return RegistryEntry(
        name=name,
        provider_type="mock",
        safety_band_min="GREEN",
        availability="AVAILABLE",
        estimated_duration_ms=100,
    )


def _step(sid: str, capability: str, *, deps: list[str] | None = None) -> PlanStep:
    return PlanStep(id=sid, capability=capability, deps=deps or [], params={})


def _workflow_spec(
    workflow_id: str,
    *,
    trigger: TriggerSpec,
    steps: list[PlanStep],
    dependencies: dict[str, list[str]] | None = None,
    version: str = "1.0.0",
) -> WorkflowSpec:
    return WorkflowSpec(
        workflow_id=workflow_id,
        name=f"wf-{workflow_id}",
        source_plan_id=f"plan-{workflow_id}",
        version=version,
        trigger=trigger,
        steps=steps,
        dependencies=dependencies or {},
        active=True,
    )


def _run_req(
    workflow_id: str, *, trigger_type: TriggerType, trace_id: str | None = None
) -> WorkflowRunRequest:
    return WorkflowRunRequest(
        workflow_id=workflow_id,
        version="1.0.0",
        trigger_type=trigger_type,
        trace_id=trace_id or str(uuid4()),
    )


def _assert_dag_completed_payload_shape(payload: dict) -> None:
    required = {"trace_id", "success", "completed", "failed", "cancelled", "skipped"}
    missing = sorted(required.difference(payload.keys()))
    assert not missing, f"Missing ORCH_DAG_COMPLETED payload keys: {missing}"


async def _svc():
    service = await OrchestratorFactory.create_standalone()
    engine = service._workflow_engine
    storage = engine.registry._storage
    return (
        service,
        service._fabric_port,
        service._delta_port,
        service._bridge_port,
        service._mailbox,
        engine,
        storage,
        service._state_port,
    )


class TestWorkflowE2E:
    @pytest.mark.asyncio
    async def test_simple_two_step_workflow_compile_execute_success(self) -> None:
        service, fabric, delta, bridge, _, engine, storage, _ = await _svc()
        wf_id = "wf-e2e-simple"

        fabric.register_capability("tool.wf.a", _entry("tool.wf.a"))
        fabric.register_capability("tool.wf.b", _entry("tool.wf.b"))
        spec = _workflow_spec(
            wf_id,
            trigger=TriggerSpec(type=TriggerType.MANUAL),
            steps=[_step("s1", "tool.wf.a"), _step("s2", "tool.wf.b", deps=["s1"])],
            dependencies={"s2": ["s1"]},
        )
        await engine.registry.save(spec)

        result = await service.process(_run_req(wf_id, trigger_type=TriggerType.MANUAL))

        assert result == ProcessResult.COMPLETED
        fabric.assert_called("tool.wf.a", times=1)
        fabric.assert_called("tool.wf.b", times=1)
        delta.assert_emitted(ORCH_DAG_STARTED, count=1)
        completed = delta.get_emitted(ORCH_DAG_COMPLETED)
        assert len(completed) == 1
        _assert_dag_completed_payload_shape(completed[0])
        assert completed[0]["success"] is True
        assert storage.runs.get(wf_id)
        bridge.assert_audit_written(count=1)

    @pytest.mark.asyncio
    async def test_workflow_with_capability_gap_emits_proactive_gap_and_fails_gracefully(
        self,
    ) -> None:
        service, _, delta, _, _, engine, storage, _ = await _svc()
        wf_id = "wf-e2e-gap"
        spec = _workflow_spec(
            wf_id,
            trigger=TriggerSpec(type=TriggerType.MANUAL),
            steps=[_step("s1", "tool.wf.missing")],
        )
        await engine.registry.save(spec)

        result = await service.process(_run_req(wf_id, trigger_type=TriggerType.MANUAL))

        assert result == ProcessResult.FAILED
        assert storage.gaps, "Expected compiler to persist proactive gap(s)"
        gap_topics = [t for t, _, _ in delta.emitted if t == "k1.orchestration.gap.detected"]
        assert gap_topics

    @pytest.mark.asyncio
    async def test_event_triggered_workflow_enqueued_then_processed(self) -> None:
        service, fabric, _, _, mailbox, engine, storage, _ = await _svc()
        wf_id = "wf-e2e-event"
        fabric.register_capability("tool.wf.event", _entry("tool.wf.event"))
        spec = _workflow_spec(
            wf_id,
            trigger=TriggerSpec(type=TriggerType.EVENT, event_topic="k1.demo.event.v1"),
            steps=[_step("s1", "tool.wf.event")],
        )
        await engine.registry.save(spec)
        await storage.save_trigger(wf_id, spec.trigger)

        await engine.scheduler._tick()

        msg = mailbox.dequeue()
        assert isinstance(msg, WorkflowRunRequest)
        assert msg.workflow_id == wf_id
        assert msg.trigger_type == TriggerType.EVENT

        result = await service.process(msg)
        assert result == ProcessResult.COMPLETED
        fabric.assert_called("tool.wf.event", times=1)

    @pytest.mark.asyncio
    async def test_scheduled_cron_workflow_runs_when_due(self) -> None:
        service, fabric, _, _, mailbox, engine, storage, _ = await _svc()
        wf_id = "wf-e2e-cron"
        fabric.register_capability("tool.wf.cron", _entry("tool.wf.cron"))
        trig = TriggerSpec(type=TriggerType.CRON, schedule="*/5 * * * *")
        spec = _workflow_spec(wf_id, trigger=trig, steps=[_step("s1", "tool.wf.cron")])
        await engine.registry.save(spec)
        await storage.save_trigger(wf_id, trig)

        await engine.scheduler._tick()

        msg = mailbox.dequeue()
        assert isinstance(msg, WorkflowRunRequest)
        assert msg.workflow_id == wf_id
        assert msg.trigger_type == TriggerType.CRON

        result = await service.process(msg)
        assert result == ProcessResult.COMPLETED
        fabric.assert_called("tool.wf.cron", times=1)

    @pytest.mark.asyncio
    async def test_cron_not_due_does_not_enqueue_workflow(self) -> None:
        service, _, _, _, mailbox, engine, storage, _ = await _svc()
        wf_id = "wf-e2e-cron-not-due"
        trig = TriggerSpec(type=TriggerType.CRON, schedule="*/5 * * * *")
        spec = _workflow_spec(wf_id, trigger=trig, steps=[_step("s1", "tool.none")])
        await engine.registry.save(spec)
        await storage.save_trigger(wf_id, trig)
        # Set far-future next_fire so _tick sees not-due trigger.
        await storage.update_trigger_state(wf_id, next_fire=10**12, last_fire=0.0)

        await engine.scheduler._tick()

        assert mailbox.depth() == 0

    @pytest.mark.asyncio
    async def test_run_manifest_persisted_in_workflow_storage(self) -> None:
        service, fabric, _, _, _, engine, storage, _ = await _svc()
        wf_id = "wf-e2e-manifest"
        fabric.register_capability("tool.wf.persist", _entry("tool.wf.persist"))
        await engine.registry.save(
            _workflow_spec(
                wf_id,
                trigger=TriggerSpec(type=TriggerType.MANUAL),
                steps=[_step("s1", "tool.wf.persist")],
            )
        )

        result = await service.process(_run_req(wf_id, trigger_type=TriggerType.MANUAL))

        assert result == ProcessResult.COMPLETED
        runs = await storage.get_runs(wf_id)
        assert runs
        assert runs[0].workflow_id == wf_id
        assert runs[0].compiled_hash

    @pytest.mark.asyncio
    async def test_run_manifest_audit_written_with_execution_details(self) -> None:
        service, fabric, _, bridge, _, engine, _, _ = await _svc()
        wf_id = "wf-e2e-audit"
        fabric.register_capability("tool.wf.audit", _entry("tool.wf.audit"))
        await engine.registry.save(
            _workflow_spec(
                wf_id,
                trigger=TriggerSpec(type=TriggerType.MANUAL),
                steps=[_step("s1", "tool.wf.audit")],
            )
        )

        result = await service.process(_run_req(wf_id, trigger_type=TriggerType.MANUAL))

        assert result == ProcessResult.COMPLETED
        assert bridge.audit_log, "Expected DAG execution audit to be written"
        manifest, trace_id = bridge.audit_log[-1]
        assert manifest.get("trace_id") == trace_id
        assert "completed" in manifest
        assert "failed" in manifest
        assert "duration_ms" in manifest

    @pytest.mark.asyncio
    async def test_workflow_lifecycle_events_emitted(self) -> None:
        service, fabric, delta, _, _, engine, _, _ = await _svc()
        wf_id = "wf-e2e-events"
        fabric.register_capability("tool.wf.events", _entry("tool.wf.events"))
        await engine.registry.save(
            _workflow_spec(
                wf_id,
                trigger=TriggerSpec(type=TriggerType.MANUAL),
                steps=[_step("s1", "tool.wf.events")],
            )
        )

        result = await service.process(_run_req(wf_id, trigger_type=TriggerType.MANUAL))

        assert result == ProcessResult.COMPLETED
        topics = [topic for topic, _, _ in delta.emitted]
        assert "k1.orchestration.workflow.run_started" in topics
        assert ORCH_DAG_STARTED in topics
        assert ORCH_DAG_COMPLETED in topics
        assert "k1.orchestration.workflow.run_completed" in topics

    @pytest.mark.asyncio
    async def test_trace_id_propagates_to_workflow_and_dag_events(self) -> None:
        service, fabric, delta, _, _, engine, _, _ = await _svc()
        wf_id = "wf-e2e-trace"
        trace_id = str(uuid4())
        fabric.register_capability("tool.wf.trace", _entry("tool.wf.trace"))
        await engine.registry.save(
            _workflow_spec(
                wf_id,
                trigger=TriggerSpec(type=TriggerType.MANUAL),
                steps=[_step("s1", "tool.wf.trace")],
            )
        )

        result = await service.process(
            _run_req(wf_id, trigger_type=TriggerType.MANUAL, trace_id=trace_id)
        )

        assert result == ProcessResult.COMPLETED
        for topic, payload, emitted_trace_id in delta.emitted:
            if topic in {
                ORCH_DAG_STARTED,
                ORCH_DAG_COMPLETED,
                "k1.orchestration.workflow.run_started",
                "k1.orchestration.workflow.run_completed",
            }:
                assert emitted_trace_id == trace_id
                if "trace_id" in payload:
                    assert payload["trace_id"] == trace_id

    @pytest.mark.asyncio
    async def test_workflow_contract_compliance_unknown_workflow_fails(self) -> None:
        service, _, _, _, _, _, _, _ = await _svc()

        result = await service.process(
            _run_req("wf-does-not-exist", trigger_type=TriggerType.MANUAL)
        )

        assert result == ProcessResult.FAILED

    @pytest.mark.asyncio
    async def test_orch12_depth_guard_is_configured_and_enforced(self) -> None:
        service, _, _, _, _, engine, _, _ = await _svc()
        depth_guard = engine.cross_resolver._depth_guard
        assert depth_guard.max_depth == 3

        with pytest.raises(MaxDepthError):
            depth_guard.check(4)

    @pytest.mark.asyncio
    async def test_actor_isolation_distinct_runs_have_distinct_run_ids(self) -> None:
        service, fabric, _, _, _, engine, storage, _ = await _svc()
        wf_a = "wf-e2e-a"
        wf_b = "wf-e2e-b"
        fabric.register_capability("tool.wf.isolation.a", _entry("tool.wf.isolation.a"))
        fabric.register_capability("tool.wf.isolation.b", _entry("tool.wf.isolation.b"))
        await engine.registry.save(
            _workflow_spec(
                wf_a,
                trigger=TriggerSpec(type=TriggerType.MANUAL),
                steps=[_step("s1", "tool.wf.isolation.a")],
            )
        )
        await engine.registry.save(
            _workflow_spec(
                wf_b,
                trigger=TriggerSpec(type=TriggerType.MANUAL),
                steps=[_step("s1", "tool.wf.isolation.b")],
            )
        )

        r1 = await service.process(_run_req(wf_a, trigger_type=TriggerType.MANUAL))
        r2 = await service.process(_run_req(wf_b, trigger_type=TriggerType.MANUAL))

        assert r1 == ProcessResult.COMPLETED
        assert r2 == ProcessResult.COMPLETED
        runs_a = await storage.get_runs(wf_a)
        runs_b = await storage.get_runs(wf_b)
        assert runs_a and runs_b
        assert runs_a[0].run_id != runs_b[0].run_id

        assert r1 == ProcessResult.COMPLETED
        assert r2 == ProcessResult.COMPLETED
        runs_a = await storage.get_runs(wf_a)
        runs_b = await storage.get_runs(wf_b)
        assert runs_a and runs_b
        assert runs_a[0].run_id != runs_b[0].run_id

        assert r1 == ProcessResult.COMPLETED
        assert r2 == ProcessResult.COMPLETED
        runs_a = await storage.get_runs(wf_a)
        runs_b = await storage.get_runs(wf_b)
        assert runs_a and runs_b
        assert runs_a[0].run_id != runs_b[0].run_id

        assert r1 == ProcessResult.COMPLETED
        assert r2 == ProcessResult.COMPLETED
        runs_a = await storage.get_runs(wf_a)
        runs_b = await storage.get_runs(wf_b)
        assert runs_a and runs_b
        assert runs_a[0].run_id != runs_b[0].run_id
