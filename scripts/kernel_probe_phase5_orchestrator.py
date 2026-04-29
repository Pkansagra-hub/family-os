"""kernel_probe_phase5_orchestrator.py — Phase 5 Orchestrator DAG + Saga probe.

Drives the kernel-resident OrchestratorService through a real
multi-wave DAG by injecting a CommittedPlan directly into
``OrchestratorService.process()`` after seeding ``pending_plans``.

What it verifies (per user's Phase plan):
  - Static wiring: ``svc._orchestrator`` exists, initialized, mailbox loop
    + reaper task alive, port types are real (not Mock*).
  - Multi-step DAG: 3 steps in 2 waves (s1 + s2 parallel, s3 depends on
    both) executes via ``DAGExecutor.execute()``.
  - Real Fabric path: orchestrator routes through
    ``FabricGatewayAdapter`` -> shared_fabric, with ``TestMCPTransport``
    injected (Phase 3 pattern) so MCP-typed contracts execute.
  - Event emission: ``ORCH_DAG_COMPLETED`` is published on the kernel
    event bus and captured.
  - Result aggregation: ``AggregatedResult.to_dict()`` shape matches
    expected fields (success, plan_id, step_results, compensations).
  - Saga compensation surface: build a plan with ``has_side_effects=True``
    + ``compensation`` set on a step that succeeds, then force a later
    step to fail. Inspect ``AggregatedResult.compensations``. Per
    ``orchestrator_service.py`` L931 ("V1: Saga.compensate() not yet
    wired"), this is expected to surface as 0 compensations on the
    returned result; we record it as INFO/WARN documenting current
    behavior so any future implementation flips this to OK without
    changing the probe.

Notes:
  - Bypasses the mailbox loop: calls ``process(plan)`` directly to avoid
    racing the reaper / mailbox dequeue. Equivalent to the path the
    loop would take.
  - Uses kernel's MockPlannerAdapter (default) — we never call planner.
  - Uses kernel's real shared_fabric — we exercise the actual capability
    registry + provider resolution.

Run:
    $env:PYTHONPATH="D:\\familyos"; $env:PYTHONIOENCODING="utf-8"
    python -m scripts.kernel_probe_phase5_orchestrator
    python -m scripts.kernel_probe_phase5_orchestrator --json data/kernel_probe_phase5.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from typing import Any

from k1.concierge.config.kernel import KernelConfig
from k1.kernel.bootstrap import start_kernel, stop_kernel
from k1.orchestrator.events import (
    ORCH_DAG_COMPLETED,
    ORCH_DAG_STARTED,
    ORCH_DELTA_V1,
    ORCH_SAGA_COMPENSATING,
    ORCH_STEP_COMPLETED,
    ORCH_STEP_FAILED,
)
from scripts._probe_common import _C_DIM, ProbeReport, _attr, _c

# ── transport injection (reused from Phase 3) ──────────────────────────


def _inject_test_mcp_transport(fabric: Any, report: ProbeReport) -> Any:
    """Patch provider_factory._port_deps['mcp_transport'] with TestMCPTransport."""
    layer = "Fabric Wiring"
    facade = _attr(fabric, "facade")
    pf = _attr(facade, "_provider_factory") if facade else None
    if pf is None:
        report.add(layer, "provider_factory", "FAIL", None, "facade._provider_factory missing")
        return None
    try:
        from k1.fabric.adapters.test_mcp_transport import TestMCPTransport
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "TestMCPTransport_import", "FAIL", None, f"{exc}")
        return None
    port_deps = _attr(pf, "_port_deps", {}) or {}
    transport = TestMCPTransport(connected=True)
    port_deps["mcp_transport"] = transport
    pf._port_deps = port_deps
    report.add(layer, "mcp_transport.injected", "OK", type(transport).__name__)
    return transport


# ── orchestrator wiring inspection ─────────────────────────────────────


def probe_orchestrator_wiring(svc: Any, report: ProbeReport) -> Any:
    layer = "Orchestrator Wiring"
    orch = _attr(svc, "_orchestrator")
    if orch is None:
        report.add(layer, "orchestrator", "FAIL", None, "kernel._orchestrator is None")
        return None
    report.add(layer, "orchestrator", "OK", type(orch).__name__)

    initialized = _attr(orch, "initialized", False)
    running = _attr(orch, "running", False)
    report.add(layer, "initialized", "OK" if initialized else "FAIL", initialized)
    report.add(layer, "running", "OK" if running else "FAIL", running)

    loop_task = _attr(orch, "_loop_task")
    reaper_task = _attr(orch, "_reaper_task")
    report.add(
        layer,
        "loop_task",
        "OK" if loop_task is not None and not loop_task.done() else "FAIL",
        type(loop_task).__name__ if loop_task else None,
    )
    report.add(
        layer,
        "reaper_task",
        "OK" if reaper_task is not None and not reaper_task.done() else "WARN",
        type(reaper_task).__name__ if reaper_task else None,
    )

    # Port types (expecting real adapters, not Mock*)
    fabric_port = _attr(orch, "_fabric_port")
    planner_port = _attr(orch, "_planner_port")
    state_port = _attr(orch, "_state_port")
    delta_port = _attr(orch, "_delta_port")
    bridge_port = _attr(orch, "_bridge_port")
    event_port = _attr(orch, "_event_port")

    report.add(
        layer,
        "fabric_port",
        "OK" if "Mock" not in type(fabric_port).__name__ else "WARN",
        type(fabric_port).__name__,
    )
    report.add(layer, "planner_port", "INFO", type(planner_port).__name__)
    report.add(layer, "state_port", "INFO", type(state_port).__name__)
    report.add(layer, "delta_port", "INFO", type(delta_port).__name__)
    report.add(layer, "bridge_port", "INFO", type(bridge_port).__name__)
    report.add(layer, "event_port", "INFO", type(event_port).__name__)

    return orch


# ── pick a registered capability ───────────────────────────────────────


def _pick_capability(fabric: Any, report: ProbeReport) -> str | None:
    layer = "Plan Build"
    facade = _attr(fabric, "facade")
    registry = _attr(fabric, "registry") or (_attr(facade, "_registry") if facade else None)
    if registry is None:
        report.add(layer, "registry", "FAIL", None, "no registry")
        return None
    try:
        contracts = list(registry.list_all())
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "list_all", "FAIL", None, f"{exc}")
        return None
    # Prefer tool.* (lowest blast radius)
    pref = ["tool.", "agent.", "workflow."]
    for prefix in pref:
        for c in contracts:
            name = _attr(c, "capability_name") or _attr(c, "name") or ""
            if name.startswith(prefix):
                report.add(layer, "selected_capability", "OK", name)
                return name
    if contracts:
        name = _attr(contracts[0], "capability_name") or _attr(contracts[0], "name") or "?"
        report.add(layer, "selected_capability", "WARN", name, "no tool.* contract found")
        return name
    report.add(layer, "selected_capability", "FAIL", None, "registry empty")
    return None


# ── plan builders ──────────────────────────────────────────────────────


def _build_diamond_plan(capability: str, *, request_id: str, trace_id: str) -> Any:
    """3-step diamond: s1 + s2 (wave 0) -> s3 (wave 1) all using same cap.

    All steps declare ``safety_band_min=AMBER`` so write-tier capabilities
    pass the Fabric band check (GREEN<AMBER would be denied).
    """
    from k1.orchestrator.types import CommittedPlan, PlanStep

    steps = [
        PlanStep(
            id="s1", capability=capability, params={"probe": "wave0a"}, safety_band_min="AMBER"
        ),
        PlanStep(
            id="s2", capability=capability, params={"probe": "wave0b"}, safety_band_min="AMBER"
        ),
        PlanStep(
            id="s3",
            capability=capability,
            params={"probe": "wave1"},
            deps=["s1", "s2"],
            safety_band_min="AMBER",
        ),
    ]
    return CommittedPlan(
        plan_id=f"plan-{uuid.uuid4().hex[:8]}",
        request_id=request_id,
        intent="phase5 diamond probe",
        steps=steps,
        dependencies={"s3": ["s1", "s2"]},
        trace_id=trace_id,
    )


def _build_saga_plan(capability: str, *, request_id: str, trace_id: str) -> Any:
    """2-step plan: s1 has side-effects + compensation, s2 fails at execution.

    Both steps use the same real capability so ConstraintResolver.validate()
    passes (it requires every capability_name to exist in the registry).
    Failure is induced naturally by the TestMCPTransport returning dummy
    data that fails the contract's output schema validation
    (``error_code=output_validation_failed``), which surfaces as
    ``StepStatus.FAILED`` from the StepRunner.

    This exercises the saga compensation surface: s1 succeeds at execute()
    with has_side_effects=True, then s2 fails. If saga compensation were
    wired, s1.compensation would run and AggregatedResult.compensations
    would be non-empty. Per orchestrator_service.py L931, this is a known
    V1 deferral.
    """
    from k1.orchestrator.types import CommittedPlan, PlanStep

    steps = [
        PlanStep(
            id="s1",
            capability=capability,
            params={"probe": "side_effect"},
            has_side_effects=True,
            compensation=capability,
            safety_band_min="AMBER",
        ),
        PlanStep(
            id="s2",
            capability=capability,
            params={"probe": "downstream_fail"},
            deps=["s1"],
            safety_band_min="AMBER",
        ),
    ]
    return CommittedPlan(
        plan_id=f"plan-saga-{uuid.uuid4().hex[:8]}",
        request_id=request_id,
        intent="phase5 saga probe",
        steps=steps,
        dependencies={"s2": ["s1"]},
        trace_id=trace_id,
    )


# ── seed pending context + run ─────────────────────────────────────────


def _seed_pending(orch: Any, plan: Any) -> None:
    from k1.fabric.ports.state_reader import SessionSnapshot
    from k1.orchestrator.types import PendingPlanContext, TaskEnvelope

    envelope = TaskEnvelope(
        intent="phase5 probe",
        trace_id=plan.trace_id,
        tier="HIGH",
        context={"session_id": "probe-session"},
    )
    snapshot = SessionSnapshot(session_id="probe-session")
    orch._pending_plans[plan.request_id] = PendingPlanContext(
        request_id=plan.request_id,
        task_envelope=envelope,
        state_snapshot=snapshot,
    )


def _subscribe_topics(orch: Any, topics: list[str]) -> tuple[list[tuple[str, Any]], list[Any]]:
    """Subscribe to orchestrator topics on the kernel event bus.

    Returns (captured, handles).
    """
    captured: list[tuple[str, Any]] = []
    handles: list[Any] = []
    event_port = _attr(orch, "_event_port")
    # EventSubscriptionAdapter wraps the kernel event_port.
    underlying = _attr(event_port, "_event_port") or event_port
    if underlying is None or not hasattr(underlying, "subscribe"):
        return captured, handles
    for topic in topics:

        def _mk(t: str):
            # EventPortProdAdapter calls handler(topic, data) -- accept *args
            # so we work with both 1-arg and 2-arg subscriber contracts.
            def _h(*args: Any) -> None:
                payload = args[-1] if args else None
                captured.append((t, payload))

            return _h

        try:
            h = underlying.subscribe(topic, _mk(topic))
            handles.append(h)
        except Exception:  # noqa: BLE001
            pass
    return captured, handles


async def probe_diamond_dag(orch: Any, fabric: Any, capability: str, report: ProbeReport) -> None:
    layer = "Orchestrator DAG"
    plan = _build_diamond_plan(
        capability,
        request_id=f"req-{uuid.uuid4().hex[:8]}",
        trace_id=f"trace-{uuid.uuid4().hex[:8]}",
    )
    _seed_pending(orch, plan)

    captured, _handles = _subscribe_topics(
        orch,
        [
            ORCH_DAG_STARTED,
            ORCH_DAG_COMPLETED,
            ORCH_STEP_COMPLETED,
            ORCH_STEP_FAILED,
            ORCH_DELTA_V1,
        ],
    )

    t0 = time.perf_counter()
    try:
        result = await asyncio.wait_for(orch.process(plan), timeout=20.0)
    except asyncio.TimeoutError:
        report.add(layer, "process", "FAIL", None, "timed out after 20s")
        return
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "process", "FAIL", None, f"raised {type(exc).__name__}: {exc}")
        return
    elapsed_ms = (time.perf_counter() - t0) * 1000
    report.add(layer, "process_result", "INFO", str(result), f"{elapsed_ms:.0f}ms")

    # Drain subscribers
    await asyncio.sleep(0.1)

    # Inspect captured events
    by_topic: dict[str, int] = {}
    for t, _ in captured:
        by_topic[t] = by_topic.get(t, 0) + 1
    report.add(layer, "events_by_topic", "INFO", by_topic)

    report.add(
        layer,
        "ORCH_DAG_COMPLETED",
        "OK" if by_topic.get(ORCH_DAG_COMPLETED, 0) > 0 else "FAIL",
        by_topic.get(ORCH_DAG_COMPLETED, 0),
    )
    report.add(
        layer,
        "ORCH_DAG_STARTED",
        "OK" if by_topic.get(ORCH_DAG_STARTED, 0) > 0 else "WARN",
        by_topic.get(ORCH_DAG_STARTED, 0),
        "v1: dag.started may not be emitted",
    )

    # Pull AggregatedResult payload from the dag.completed event if present
    agg_payload = None
    for t, evt in captured:
        if t == ORCH_DAG_COMPLETED:
            payload = _attr(evt, "payload", evt)
            if isinstance(payload, dict):
                agg_payload = payload.get("result") or payload
            break
    if agg_payload:
        report.add(
            layer,
            "agg.fields",
            "INFO",
            sorted(list(agg_payload.keys()))[:12] if isinstance(agg_payload, dict) else None,
        )
        if isinstance(agg_payload, dict):
            report.add(
                layer,
                "agg.total_steps",
                "OK" if agg_payload.get("total_steps") == 3 else "WARN",
                agg_payload.get("total_steps"),
            )
            report.add(
                layer,
                "agg.completed",
                "INFO",
                agg_payload.get("completed"),
            )
            report.add(
                layer,
                "agg.failed",
                "INFO",
                agg_payload.get("failed"),
            )
            report.add(
                layer,
                "agg.success",
                "OK" if agg_payload.get("success") else "WARN",
                agg_payload.get("success"),
                f"plan_id={agg_payload.get('plan_id')}",
            )


async def probe_saga_compensation(orch: Any, capability: str, report: ProbeReport) -> None:
    layer = "Orchestrator Saga"
    plan = _build_saga_plan(
        capability,
        request_id=f"req-saga-{uuid.uuid4().hex[:8]}",
        trace_id=f"trace-saga-{uuid.uuid4().hex[:8]}",
    )
    _seed_pending(orch, plan)

    captured, _handles = _subscribe_topics(
        orch,
        [
            ORCH_DAG_COMPLETED,
            ORCH_STEP_FAILED,
            ORCH_SAGA_COMPENSATING,
        ],
    )

    try:
        result = await asyncio.wait_for(orch.process(plan), timeout=20.0)
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "process", "FAIL", None, f"raised {type(exc).__name__}: {exc}")
        return
    report.add(layer, "process_result", "INFO", str(result))

    await asyncio.sleep(0.1)

    by_topic: dict[str, int] = {}
    for t, _ in captured:
        by_topic[t] = by_topic.get(t, 0) + 1
    report.add(layer, "events_by_topic", "INFO", by_topic)

    saga_count = by_topic.get(ORCH_SAGA_COMPENSATING, 0)
    # Per orchestrator_service.py L931: V1 saga compensate not wired.
    # Surface this as INFO so a future fix flips it to OK without code change.
    report.add(
        layer,
        "ORCH_SAGA_COMPENSATING",
        "OK" if saga_count > 0 else "INFO",
        saga_count,
        "V1: Saga.compensate() not wired (orchestrator_service.py L931)" if saga_count == 0 else "",
    )

    # Pull compensations list out of dag.completed payload
    for t, evt in captured:
        if t == ORCH_DAG_COMPLETED:
            payload = _attr(evt, "payload", evt)
            if isinstance(payload, dict):
                agg = payload.get("result") or payload
                if isinstance(agg, dict):
                    comps = agg.get("compensations") or []
                    report.add(
                        layer,
                        "compensations.count",
                        "OK" if comps else "INFO",
                        len(comps),
                        "V1 deferred: empty list expected" if not comps else "",
                    )
                    report.add(
                        layer,
                        "agg.failed",
                        "OK" if agg.get("failed", 0) >= 1 else "WARN",
                        agg.get("failed"),
                        "expected >=1 (s2 cannot resolve)",
                    )
            break


# ── runner ─────────────────────────────────────────────────────────────


async def run_probe(json_path: str | None) -> int:
    print("=" * 72)
    print(_c("  K1 Kernel Probe — Phase 5 (Orchestrator DAG + Saga)", "\x1b[1m"))
    print("=" * 72)

    cfg = KernelConfig(model_mode="test")
    t0 = time.perf_counter()
    runtime = await start_kernel(cfg)
    boot_s = time.perf_counter() - t0
    print(f"  Boot: {boot_s:.2f}s\n")

    report = ProbeReport()
    svc = runtime._service
    sessions = _attr(svc, "_sessions", {})
    session = next(iter(sessions.values())) if sessions else None
    # The orchestrator uses svc._shared_fabric (kernel-level), NOT the
    # per-session fabric. We must inject TestMCPTransport into the same
    # provider_factory the orchestrator's FabricGatewayAdapter resolves
    # against, otherwise MCP-typed providers fail to instantiate.
    shared_fabric = _attr(svc, "_shared_fabric")
    session_fabric = _attr(session, "fabric") if session else None

    if shared_fabric is None:
        report.add("Boot", "shared_fabric", "FAIL", None, "svc._shared_fabric is None")
    else:
        _inject_test_mcp_transport(shared_fabric, report)
        # Belt-and-suspenders: also inject into session fabric so any
        # capability lookup helpers that read from it still work.
        if session_fabric is not None and session_fabric is not shared_fabric:
            _inject_test_mcp_transport(session_fabric, report)

    orch = probe_orchestrator_wiring(svc, report)

    if orch is not None and shared_fabric is not None:
        capability = _pick_capability(shared_fabric, report)
        if capability:
            await probe_diamond_dag(orch, shared_fabric, capability, report)
            await probe_saga_compensation(orch, capability, report)

    report.render("K1 Kernel Probe — Phase 5 (Orchestrator DAG + Saga)")

    if json_path:
        out = {
            "boot_seconds": boot_s,
            "counts": report.counts(),
            "probes": [
                {
                    "layer": p.layer,
                    "name": p.name,
                    "status": p.status,
                    "value": repr(p.value),
                    "note": p.note,
                }
                for p in report.probes
            ],
        }
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, default=repr)
        print(_c(f"  JSON written: {json_path}", _C_DIM))

    print(_c("  Tearing down...", _C_DIM))
    await stop_kernel(runtime)
    return report.exit_code()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    return asyncio.run(run_probe(args.json))


if __name__ == "__main__":
    sys.exit(main())
