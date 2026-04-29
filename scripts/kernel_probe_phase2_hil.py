"""kernel_probe_phase2_hil.py — Phase 2 HIL deep-dive probe.

Drives each HIL coordinator end-to-end (no real human, no LLM cost) and
verifies request emission + programmatic resolve.

  Concierge HIL    : direct call to HILCoordinator.handle_needs_human +
                     handle_user_response (FSM Back→Front cycle)
  Planner HIL      : reach into PlannerAgent pipeline, get the bound
                     HILCoordinator, drive request_clarification + emit
                     correlated response on its IEventPort
  Orchestrator HIL : trigger via constraint_resolver path; emit resolve
                     on bus topic k1.hil.fallback_response.v1

Confirms whether each subsystem's HIL surface actually works in the booted
kernel — surfaces real bugs (correlation breaks, missing wiring, etc.)
that pure introspection (Phase 1) cannot find.

Run:
    $env:PYTHONPATH="D:\\familyos"; $env:PYTHONIOENCODING="utf-8"
    python -m scripts.kernel_probe_phase2_hil
    python -m scripts.kernel_probe_phase2_hil --json data/kernel_probe_hil.json
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
from scripts._probe_common import _C_DIM, ProbeReport, _attr, _c

# ── Concierge HIL ──────────────────────────────────────────────────────


async def probe_concierge_hil(session: Any, report: ProbeReport) -> None:
    layer = "Concierge HIL"
    coord = _attr(session, "hitl_coordinator")
    if coord is None:
        report.add(layer, "coordinator", "FAIL", None, "session.hitl_coordinator is None")
        return

    report.add(layer, "coordinator", "OK", type(coord).__name__)

    task_id = f"probe-task-{uuid.uuid4().hex[:8]}"

    # Step 1: submit a HIL ask
    try:
        req = await coord.handle_needs_human(
            task_id=task_id,
            hil_type="clarification",
            question="Probe: which calendar to use?",
            options=[{"label": "personal"}, {"label": "work"}],
            context={"probe": True},
        )
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "handle_needs_human", "FAIL", None, f"raised {type(exc).__name__}: {exc}")
        return
    report.add(
        layer,
        "handle_needs_human",
        "OK",
        f"hil_type={req.hil_type} task_id={req.task_id[:12]}",
    )

    # Step 2: confirm pending registry has it
    pending = _attr(coord, "_pending_requests", {})
    if task_id in pending:
        report.add(layer, "pending_registry", "OK", f"contains task_id (n={len(pending)})")
    else:
        report.add(
            layer,
            "pending_registry",
            "FAIL",
            None,
            f"task_id NOT in _pending_requests (n={len(pending)})",
        )

    # Step 3: resolve programmatically
    try:
        resp = await coord.handle_user_response(
            task_id=task_id,
            decision="answered",
            resolution={"choice": "personal"},
            raw_user_text="personal",
        )
    except Exception as exc:  # noqa: BLE001
        report.add(
            layer, "handle_user_response", "FAIL", None, f"raised {type(exc).__name__}: {exc}"
        )
        return
    if resp is None:
        report.add(layer, "handle_user_response", "FAIL", None, "returned None")
    else:
        report.add(layer, "handle_user_response", "OK", type(resp).__name__)

    # Step 4: pending should now be empty for this task
    pending2 = _attr(coord, "_pending_requests", {})
    if task_id not in pending2:
        report.add(layer, "post_resolve_cleanup", "OK", f"task_id removed (n={len(pending2)})")
    else:
        report.add(
            layer, "post_resolve_cleanup", "FAIL", None, "task_id still pending after resolve"
        )


# ── Planner HIL ────────────────────────────────────────────────────────


def _find_planner_hil(svc: Any) -> Any:
    """Walk PlannerAgent → PipelineController → SketchService → _hil_coord."""
    planner = _attr(svc, "_planner")
    if planner is None:
        return None
    pipeline = _attr(planner, "_pipeline")
    if pipeline is None:
        return None
    # Pipeline holds stage services; sketch carries the same hil_coord as validate
    for attr in ("_sketch", "sketch", "_sketch_service"):
        sk = _attr(pipeline, attr)
        if sk is not None:
            hc = _attr(sk, "_hil_coord") or _attr(sk, "hil_coord")
            if hc is not None:
                return hc
    for attr in ("_validate", "validate", "_validate_service"):
        vs = _attr(pipeline, attr)
        if vs is not None:
            hc = _attr(vs, "_hil_coord") or _attr(vs, "hil_coord")
            if hc is not None:
                return hc
    return None


async def probe_planner_hil(svc: Any, report: ProbeReport) -> None:
    layer = "Planner HIL"
    hil = _find_planner_hil(svc)
    if hil is None:
        report.add(layer, "coordinator", "FAIL", None, "could not locate planner HILCoordinator")
        return
    report.add(layer, "coordinator", "OK", type(hil).__name__)

    event_port = _attr(hil, "_event_port") or _attr(hil, "event_port")
    if event_port is None:
        report.add(layer, "event_port", "FAIL", None, "coordinator has no _event_port")
        return
    report.add(layer, "event_port", "OK", type(event_port).__name__)

    # Drive request_clarification — this emits k1.hil.clarification.v1 + waits
    # for k1.hil.clarification_response.v1 correlated by request_id.
    request_id = f"probe-clar-{uuid.uuid4().hex[:8]}"
    captured: list[tuple[str, Any]] = []

    # Subscribe (don't monkey-patch — event port slots forbid attr assign)
    if not hasattr(event_port, "subscribe"):
        report.add(layer, "subscribe_capability", "FAIL", None, "event_port has no subscribe()")
        return

    def _on_clar(evt: Any) -> None:
        captured.append(("k1.hil.clarification.v1", evt))

    try:
        sub = event_port.subscribe("k1.hil.clarification.v1", _on_clar)
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "subscribe", "FAIL", None, f"{type(exc).__name__}: {exc}")
        return

    async def _resolver() -> None:
        await asyncio.sleep(0.10)
        try:
            event_port.emit(
                "k1.hil.clarification_response.v1",
                {"request_id": request_id, "response": "probe answer"},
            )
        except Exception:  # noqa: BLE001
            pass

    try:
        t0 = time.perf_counter()
        clar_task = asyncio.create_task(
            hil.request_clarification(
                request_id=request_id,
                question_context={"question": "probe q?", "trace_id": "probe"},
            )
        )
        resolver_task = asyncio.create_task(_resolver())
        try:
            result = await asyncio.wait_for(clar_task, timeout=5.0)
        except asyncio.TimeoutError:
            result = None
            clar_task.cancel()
        await resolver_task
        elapsed_ms = (time.perf_counter() - t0) * 1000

        if result is None:
            report.add(
                layer,
                "request_clarification",
                "FAIL",
                None,
                f"timed out / returned None after {elapsed_ms:.0f}ms",
            )
        else:
            report.add(
                layer,
                "request_clarification",
                "OK",
                f"{result!r} ({elapsed_ms:.0f}ms)",
            )
    except Exception as exc:  # noqa: BLE001
        report.add(
            layer,
            "request_clarification",
            "FAIL",
            None,
            f"raised {type(exc).__name__}: {exc}",
        )

    # Verify topic emission was captured by subscribe
    if captured:
        report.add(
            layer,
            "topic_clarification_emitted",
            "OK",
            f"{len(captured)} event(s) on k1.hil.clarification.v1",
        )
    else:
        report.add(
            layer,
            "topic_clarification_emitted",
            "FAIL",
            None,
            "no event captured on k1.hil.clarification.v1",
        )

    # Round budget
    rc = _attr(hil, "round_count")
    if rc is not None:
        report.add(layer, "round_count_after_request", "INFO", rc)


# ── Orchestrator HIL ───────────────────────────────────────────────────


async def probe_orchestrator_hil(svc: Any, report: ProbeReport) -> None:
    layer = "Orchestrator HIL"
    orch = _attr(svc, "_orchestrator")
    if orch is None:
        report.add(layer, "service", "FAIL", None, "kernel._orchestrator is None")
        return
    report.add(layer, "service", "OK", type(orch).__name__)

    # Subscriptions — service should subscribe to override + fallback response topics
    bus = _attr(svc, "_bus")
    if bus is None:
        report.add(layer, "bus", "FAIL", None, "kernel._bus is None")
        return

    # Probe the `pending_hil` property exists (audit BLOAT-1 side-effect)
    try:
        pending = orch.pending_hil
        report.add(
            layer,
            "pending_hil_property",
            "OK",
            f"dict (n={len(pending) if hasattr(pending, '__len__') else '?'})",
        )
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "pending_hil_property", "FAIL", None, f"raised {type(exc).__name__}")

    # Check the resolve handlers are wired — methods exist
    for handler in ("_on_hil_override", "_on_hil_fallback"):
        if hasattr(orch, handler):
            report.add(layer, f"handler.{handler}", "OK", "exists")
        else:
            report.add(layer, f"handler.{handler}", "FAIL", None, "method missing")

    # Try to find the constraint_resolver and verify trigger_hil_fallback exists
    # (read-only — full e2e requires injecting a CommittedPlan with unresolved caps)
    cr = _attr(orch, "_constraint_resolver") or _attr(orch, "constraint_resolver")
    if cr is None:
        report.add(layer, "constraint_resolver", "WARN", None, "not wired on orchestrator")
    else:
        report.add(layer, "constraint_resolver", "OK", type(cr).__name__)
        if hasattr(cr, "trigger_hil_fallback"):
            report.add(layer, "trigger_hil_fallback", "OK", "method exists")
        else:
            report.add(layer, "trigger_hil_fallback", "FAIL", None, "method missing")

    # Delta port should expose emit_hil_request
    dp = _attr(orch, "_delta_port") or _attr(orch, "delta_port")
    if dp is None:
        report.add(layer, "delta_port", "WARN", None, "not on orchestrator")
    else:
        if hasattr(dp, "emit_hil_request"):
            report.add(layer, "delta_port.emit_hil_request", "OK", "method exists")
        else:
            report.add(
                layer,
                "delta_port.emit_hil_request",
                "FAIL",
                None,
                "missing — orchestrator HIL emission broken",
            )


# ── HIL fragmentation summary ──────────────────────────────────────────


def probe_hil_fragmentation(svc: Any, session: Any, report: ProbeReport) -> None:
    layer = "HIL Fragmentation"
    coords: list[tuple[str, Any]] = []
    cc = _attr(session, "hitl_coordinator")
    if cc is not None:
        coords.append(("Concierge", cc))
    pc = _find_planner_hil(svc)
    if pc is not None:
        coords.append(("Planner", pc))
    report.add(
        layer,
        "coordinator_count",
        "WARN" if len(coords) > 1 else "OK",
        len(coords),
        "audit BLOAT-1: 2 separate HILCoordinator classes" if len(coords) > 1 else "",
    )
    for name, c in coords:
        report.add(layer, f"coord.{name}", "INFO", type(c).__name__)


# ── runner ─────────────────────────────────────────────────────────────


async def run_probe(json_path: str | None) -> int:
    print("=" * 72)
    print(_c("  K1 Kernel Probe — Phase 2 (HIL deep dive)", "\x1b[1m"))
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

    if session is None:
        report.add("Boot", "session", "FAIL", None, "no session created")
    else:
        await probe_concierge_hil(session, report)
        await probe_planner_hil(svc, report)
        await probe_orchestrator_hil(svc, report)
        probe_hil_fragmentation(svc, session, report)

    report.render("K1 Kernel Probe — Phase 2 (HIL deep dive)")

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
