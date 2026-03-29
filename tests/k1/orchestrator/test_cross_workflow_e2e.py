"""Epic 7.3.4 -- CROSS-WORKFLOW end-to-end integration tests.

These tests validate cross-workflow wiring through public API entry points:
  WorkflowRunRequest -> OrchestratorService.process() -> WorkflowEngine path.

Notes on current V1 wiring:
- Cross-workflow capability resolution exists in CrossWorkflowResolver.
- Public process() path executes each workflow run with single-DAG concurrency guard.
- Nested run depth guard is validated via resolver guard configuration/enforcement.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from k1.fabric.types import CapabilityResult
from k1.orchestrator.events import ORCH_DAG_COMPLETED, ORCH_DAG_STARTED
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.types import (
    AdapterError,
    ErrorSeverity,
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


def _step(step_id: str, capability: str, *, deps: list[str] | None = None) -> PlanStep:
    return PlanStep(id=step_id, capability=capability, deps=deps or [], params={})


def _workflow_spec(
    workflow_id: str,
    *,
    trigger: TriggerSpec,
    steps: list[PlanStep],
    dependencies: dict[str, list[str]] | None = None,
) -> WorkflowSpec:
    return WorkflowSpec(
        workflow_id=workflow_id,
        name=f"wf-{workflow_id}",
        source_plan_id=f"plan-{workflow_id}",
        version="1.0.0",
        trigger=trigger,
        steps=steps,
        dependencies=dependencies or {},
        active=True,
    )


def _run_req(
    workflow_id: str,
    *,
    trigger_type: TriggerType,
    trace_id: str | None = None,
    depth: int | None = None,
) -> WorkflowRunRequest:
    trigger_context = {}
    if depth is not None:
        trigger_context["depth"] = depth

    return WorkflowRunRequest(
        workflow_id=workflow_id,
        version="1.0.0",
        trigger_type=trigger_type,
        trace_id=trace_id or str(uuid4()),
        trigger_context=trigger_context,
    )


async def _svc():
    service = await OrchestratorFactory.create_for_testing()
    engine = service._workflow_engine
    storage = engine.registry._storage
    return (
        service,
        service._fabric_port,
        service._delta_port,
        service._bridge_port,
        engine,
        storage,
    )


class TestCrossWorkflowE2E:
    @pytest.mark.asyncio
    async def test_parent_then_child_runs_and_parent_continues(self) -> None:
        service, fabric, delta, _, engine, storage = await _svc()

        parent_id = "wf-cross-parent-1"
        child_id = "wf-cross-child-1"

        fabric.register_capability("workflow.run.child.1", _entry("workflow.run.child.1"))
        fabric.register_capability("tool.parent.final.1", _entry("tool.parent.final.1"))
        fabric.register_capability("tool.child.leaf.1", _entry("tool.child.leaf.1"))

        fabric.script_result(
            "workflow.run.child.1",
            CapabilityResult.success_result(
                request_id="r-parent-child",
                data={"child_workflow_id": child_id, "child_status": "COMPLETED"},
                provider_id="mock",
                trace_id="t-parent-child",
            ),
        )

        await engine.registry.save(
            _workflow_spec(
                child_id,
                trigger=TriggerSpec(type=TriggerType.MANUAL),
                steps=[_step("c1", "tool.child.leaf.1")],
            )
        )
        await engine.registry.save(
            _workflow_spec(
                parent_id,
                trigger=TriggerSpec(type=TriggerType.MANUAL),
                steps=[
                    _step("p1", "workflow.run.child.1"),
                    _step("p2", "tool.parent.final.1", deps=["p1"]),
                ],
                dependencies={"p2": ["p1"]},
            )
        )

        parent_result = await service.process(
            _run_req(parent_id, trigger_type=TriggerType.MANUAL, depth=1)
        )
        child_result = await service.process(
            _run_req(child_id, trigger_type=TriggerType.MANUAL, depth=2)
        )

        assert parent_result == ProcessResult.COMPLETED
        assert child_result == ProcessResult.COMPLETED
        fabric.assert_called("workflow.run.child.1", times=1)
        fabric.assert_called("tool.parent.final.1", times=1)
        fabric.assert_called("tool.child.leaf.1", times=1)

        parent_runs = await storage.get_runs(parent_id)
        child_runs = await storage.get_runs(child_id)
        assert parent_runs
        assert child_runs

        topics = [topic for topic, _, _ in delta.emitted]
        assert topics.count("k1.orchestration.workflow.run_started") >= 2
        assert topics.count("k1.orchestration.workflow.run_completed") >= 2

    @pytest.mark.asyncio
    async def test_depth1_depth2_depth3_chain_all_succeed(self) -> None:
        service, fabric, _, _, engine, storage = await _svc()

        wf1 = "wf-cross-l1"
        wf2 = "wf-cross-l2"
        wf3 = "wf-cross-l3"

        fabric.register_capability("tool.cross.l1", _entry("tool.cross.l1"))
        fabric.register_capability("tool.cross.l2", _entry("tool.cross.l2"))
        fabric.register_capability("tool.cross.l3", _entry("tool.cross.l3"))

        await engine.registry.save(
            _workflow_spec(
                wf1,
                trigger=TriggerSpec(type=TriggerType.MANUAL),
                steps=[_step("s1", "tool.cross.l1")],
            )
        )
        await engine.registry.save(
            _workflow_spec(
                wf2,
                trigger=TriggerSpec(type=TriggerType.MANUAL),
                steps=[_step("s1", "tool.cross.l2")],
            )
        )
        await engine.registry.save(
            _workflow_spec(
                wf3,
                trigger=TriggerSpec(type=TriggerType.MANUAL),
                steps=[_step("s1", "tool.cross.l3")],
            )
        )

        r1 = await service.process(_run_req(wf1, trigger_type=TriggerType.MANUAL, depth=1))
        r2 = await service.process(_run_req(wf2, trigger_type=TriggerType.MANUAL, depth=2))
        r3 = await service.process(_run_req(wf3, trigger_type=TriggerType.MANUAL, depth=3))

        assert r1 == ProcessResult.COMPLETED
        assert r2 == ProcessResult.COMPLETED
        assert r3 == ProcessResult.COMPLETED

        assert await storage.get_runs(wf1)
        assert await storage.get_runs(wf2)
        assert await storage.get_runs(wf3)

    @pytest.mark.asyncio
    async def test_depth_guard_allows_one_to_three(self) -> None:
        service, _, _, _, engine, _ = await _svc()
        guard = engine.cross_resolver._depth_guard

        guard.check(1)
        guard.check(2)
        guard.check(3)

        await service.shutdown()

    @pytest.mark.asyncio
    async def test_depth_guard_blocks_fourth_level(self) -> None:
        service, _, _, _, engine, _ = await _svc()
        guard = engine.cross_resolver._depth_guard

        assert guard.max_depth == 3
        with pytest.raises(MaxDepthError):
            guard.check(4)

        await service.shutdown()

    @pytest.mark.asyncio
    async def test_concurrent_same_workflow_second_request_is_deferred_while_first_active(
        self,
    ) -> None:
        service, fabric, _, _, engine, storage = await _svc()
        wf_id = "wf-cross-concurrency"

        fabric.register_capability("tool.cross.slow", _entry("tool.cross.slow"))
        fabric.script_timeout("tool.cross.slow", delay_s=0.2)

        await engine.registry.save(
            _workflow_spec(
                wf_id,
                trigger=TriggerSpec(type=TriggerType.MANUAL),
                steps=[_step("s1", "tool.cross.slow")],
            )
        )

        t1 = asyncio.create_task(service.process(_run_req(wf_id, trigger_type=TriggerType.MANUAL)))
        await asyncio.sleep(0.02)

        r2 = await service.process(_run_req(wf_id, trigger_type=TriggerType.CRON))
        r1 = await t1

        assert r2 == ProcessResult.DEFERRED
        assert r1 in {ProcessResult.COMPLETED, ProcessResult.DEGRADED}

        runs = await storage.get_runs(wf_id)
        assert runs

    @pytest.mark.asyncio
    async def test_fresh_run_starts_after_previous_finishes(self) -> None:
        service, fabric, _, _, engine, storage = await _svc()
        wf_id = "wf-cross-fresh-after-active"

        fabric.register_capability("tool.cross.fresh", _entry("tool.cross.fresh"))
        await engine.registry.save(
            _workflow_spec(
                wf_id,
                trigger=TriggerSpec(type=TriggerType.MANUAL),
                steps=[_step("s1", "tool.cross.fresh")],
            )
        )

        r1 = await service.process(_run_req(wf_id, trigger_type=TriggerType.MANUAL))
        r2 = await service.process(_run_req(wf_id, trigger_type=TriggerType.CRON))

        assert r1 == ProcessResult.COMPLETED
        assert r2 == ProcessResult.COMPLETED

        runs = await storage.get_runs(wf_id)
        assert len(runs) >= 2

    @pytest.mark.asyncio
    async def test_child_failure_payload_can_be_handled_and_parent_continues(self) -> None:
        service, fabric, _, _, engine, _ = await _svc()
        parent_id = "wf-cross-parent-continue"

        fabric.register_capability(
            "workflow.run.child.fail.handled", _entry("workflow.run.child.fail.handled")
        )
        fabric.register_capability("tool.parent.continue", _entry("tool.parent.continue"))

        fabric.script_result(
            "workflow.run.child.fail.handled",
            CapabilityResult.success_result(
                request_id="r-child-fail-handled",
                data={"child_status": "FAILED", "handled": True},
                provider_id="mock",
                trace_id="t-child-fail-handled",
            ),
        )

        await engine.registry.save(
            _workflow_spec(
                parent_id,
                trigger=TriggerSpec(type=TriggerType.MANUAL),
                steps=[
                    _step("p1", "workflow.run.child.fail.handled"),
                    _step("p2", "tool.parent.continue", deps=["p1"]),
                ],
                dependencies={"p2": ["p1"]},
            )
        )

        result = await service.process(_run_req(parent_id, trigger_type=TriggerType.MANUAL))

        assert result == ProcessResult.COMPLETED
        fabric.assert_called("workflow.run.child.fail.handled", times=1)
        fabric.assert_called("tool.parent.continue", times=1)

    @pytest.mark.asyncio
    async def test_child_failure_as_step_failure_causes_parent_failure(self) -> None:
        service, fabric, _, _, engine, _ = await _svc()
        parent_id = "wf-cross-parent-fail"

        fabric.register_capability(
            "workflow.run.child.fail.hard", _entry("workflow.run.child.fail.hard")
        )
        fabric.register_capability("tool.parent.never", _entry("tool.parent.never"))

        fabric.script_error(
            "workflow.run.child.fail.hard",
            AdapterError(
                severity=ErrorSeverity.TERMINAL,
                adapter_name="mock_fabric",
                operation="execute",
                error_code="CHILD_FAILED",
                error_message="child workflow failed",
                trace_id="t-child-fail-hard",
            ),
        )

        await engine.registry.save(
            _workflow_spec(
                parent_id,
                trigger=TriggerSpec(type=TriggerType.MANUAL),
                steps=[
                    _step("p1", "workflow.run.child.fail.hard"),
                    _step("p2", "tool.parent.never", deps=["p1"]),
                ],
                dependencies={"p2": ["p1"]},
            )
        )

        result = await service.process(_run_req(parent_id, trigger_type=TriggerType.MANUAL))

        assert result == ProcessResult.FAILED
        fabric.assert_called("workflow.run.child.fail.hard", times=1)
        fabric.assert_not_called("tool.parent.never")

    @pytest.mark.asyncio
    async def test_run_manifest_persisted_per_workflow_level(self) -> None:
        service, fabric, _, _, engine, storage = await _svc()

        ids = [
            "wf-cross-manifest-parent",
            "wf-cross-manifest-child",
            "wf-cross-manifest-grandchild",
        ]
        caps = ["tool.cross.manifest.p", "tool.cross.manifest.c", "tool.cross.manifest.g"]

        for wf_id, cap in zip(ids, caps):
            fabric.register_capability(cap, _entry(cap))
            await engine.registry.save(
                _workflow_spec(
                    wf_id,
                    trigger=TriggerSpec(type=TriggerType.MANUAL),
                    steps=[_step("s1", cap)],
                )
            )

        for depth, wf_id in enumerate(ids, start=1):
            r = await service.process(_run_req(wf_id, trigger_type=TriggerType.MANUAL, depth=depth))
            assert r == ProcessResult.COMPLETED

        for wf_id in ids:
            runs = await storage.get_runs(wf_id)
            assert runs, f"Expected run manifest for {wf_id}"
            assert runs[0].workflow_id == wf_id

    @pytest.mark.asyncio
    async def test_events_emitted_per_workflow_level(self) -> None:
        service, fabric, delta, _, engine, _ = await _svc()

        ids = ["wf-cross-events-parent", "wf-cross-events-child", "wf-cross-events-grandchild"]
        caps = ["tool.cross.events.p", "tool.cross.events.c", "tool.cross.events.g"]

        for wf_id, cap in zip(ids, caps):
            fabric.register_capability(cap, _entry(cap))
            await engine.registry.save(
                _workflow_spec(
                    wf_id,
                    trigger=TriggerSpec(type=TriggerType.MANUAL),
                    steps=[_step("s1", cap)],
                )
            )

        for depth, wf_id in enumerate(ids, start=1):
            r = await service.process(_run_req(wf_id, trigger_type=TriggerType.MANUAL, depth=depth))
            assert r == ProcessResult.COMPLETED

        topics = [topic for topic, _, _ in delta.emitted]
        assert topics.count("k1.orchestration.workflow.run_started") >= 3
        assert topics.count("k1.orchestration.workflow.run_completed") >= 3
        assert topics.count(ORCH_DAG_STARTED) >= 3
        assert topics.count(ORCH_DAG_COMPLETED) >= 3

    @pytest.mark.asyncio
    async def test_trace_propagation_across_multi_workflow_runs(self) -> None:
        service, fabric, delta, _, engine, _ = await _svc()

        wf_a = "wf-cross-trace-a"
        wf_b = "wf-cross-trace-b"
        trace_a = str(uuid4())
        trace_b = str(uuid4())

        fabric.register_capability("tool.cross.trace.a", _entry("tool.cross.trace.a"))
        fabric.register_capability("tool.cross.trace.b", _entry("tool.cross.trace.b"))

        await engine.registry.save(
            _workflow_spec(
                wf_a,
                trigger=TriggerSpec(type=TriggerType.MANUAL),
                steps=[_step("s1", "tool.cross.trace.a")],
            )
        )
        await engine.registry.save(
            _workflow_spec(
                wf_b,
                trigger=TriggerSpec(type=TriggerType.MANUAL),
                steps=[_step("s1", "tool.cross.trace.b")],
            )
        )

        r1 = await service.process(
            _run_req(wf_a, trigger_type=TriggerType.MANUAL, trace_id=trace_a)
        )
        r2 = await service.process(
            _run_req(wf_b, trigger_type=TriggerType.MANUAL, trace_id=trace_b)
        )

        assert r1 == ProcessResult.COMPLETED
        assert r2 == ProcessResult.COMPLETED

        seen = {trace_a: 0, trace_b: 0}
        for topic, payload, emitted_trace_id in delta.emitted:
            if (
                topic
                in {
                    ORCH_DAG_STARTED,
                    ORCH_DAG_COMPLETED,
                    "k1.orchestration.workflow.run_started",
                    "k1.orchestration.workflow.run_completed",
                }
                and emitted_trace_id in seen
            ):
                seen[emitted_trace_id] += 1
                if isinstance(payload, dict) and "trace_id" in payload:
                    assert payload["trace_id"] == emitted_trace_id

        assert seen[trace_a] > 0
        assert seen[trace_b] > 0

    @pytest.mark.asyncio
    async def test_audit_written_for_each_workflow_level(self) -> None:
        service, fabric, _, bridge, engine, _ = await _svc()

        ids = ["wf-cross-audit-parent", "wf-cross-audit-child", "wf-cross-audit-grandchild"]
        caps = ["tool.cross.audit.p", "tool.cross.audit.c", "tool.cross.audit.g"]

        for wf_id, cap in zip(ids, caps):
            fabric.register_capability(cap, _entry(cap))
            await engine.registry.save(
                _workflow_spec(
                    wf_id,
                    trigger=TriggerSpec(type=TriggerType.MANUAL),
                    steps=[_step("s1", cap)],
                )
            )

        baseline = len(bridge.audit_log)
        for wf_id in ids:
            result = await service.process(_run_req(wf_id, trigger_type=TriggerType.MANUAL))
            assert result == ProcessResult.COMPLETED

        assert len(bridge.audit_log) >= baseline + 3
