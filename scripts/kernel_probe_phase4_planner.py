"""kernel_probe_phase4_planner.py — Phase 4 PlannerAgent E2E probe.

Drives the real PlannerAgent through one full pipeline turn
(SKETCH → EXPAND → VALIDATE → COMMIT) by:

  1. Booting the kernel in test mode (StubProviderPlugin).
  2. Subscribing to TOPIC_PLAN_READY / TOPIC_PLAN_FAILED / TOPIC_PLAN_CANCELLED
     on the planner's own event_port (PlannerEventBusAdapter).
  3. Emitting a minimal PlanRequest on TOPIC_PLAN_REQUEST.
  4. Waiting up to N seconds for a terminal event.
  5. Reporting which stage failed (if any) + payload shape on success.

Notes:
  - The kernel HIGH-tier path currently uses an inline PassthroughPlannerStub
    in the Concierge FSM and does NOT invoke PlannerAgent. This probe
    bypasses the FSM entirely — it talks to the planner directly.
  - SKETCH / EXPAND / VALIDATE all call the LLM via ILLMPort. In test mode
    the gateway routes to the model_hub stub, which may be rejected by
    `model_hub.router._validate()` (Phase 2 surfaced this on HIL flow).
  - COMMIT (PLAN-03) is deterministic, no LLM.

Run:
    $env:PYTHONPATH="D:\\familyos"; $env:PYTHONIOENCODING="utf-8"
    python -m scripts.kernel_probe_phase4_planner
    python -m scripts.kernel_probe_phase4_planner --json data/kernel_probe_planner.json
    python -m scripts.kernel_probe_phase4_planner --timeout 60
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
from k1.planner.events import (
    TOPIC_DELTA,
    TOPIC_PLAN_CANCELLED,
    TOPIC_PLAN_FAILED,
    TOPIC_PLAN_READY,
    TOPIC_PLAN_REQUEST,
)
from scripts._probe_common import _C_DIM, ProbeReport, _attr, _c

# shared probe state for cross-function references (planner instance)
_PROBE_STATE: dict[str, Any] = {}


def _summarize_payload(payload: Any) -> str:
    """Return a short repr of an event payload."""
    if payload is None:
        return "None"
    if hasattr(payload, "to_dict"):
        try:
            d = payload.to_dict()
            return repr({k: d[k] for k in list(d.keys())[:6]})
        except Exception:  # noqa: BLE001
            pass
    if isinstance(payload, dict):
        return repr({k: payload[k] for k in list(payload.keys())[:6]})
    return repr(payload)[:200]


async def probe_planner_agent_wiring(svc: Any, report: ProbeReport) -> Any:
    """Validate the planner agent is alive + return the event_port."""
    layer = "Planner Wiring"
    planner = _attr(svc, "_planner")
    if planner is None:
        report.add(layer, "agent", "FAIL", None, "kernel._planner is None")
        return None
    report.add(layer, "agent", "OK", type(planner).__name__)

    task = _attr(svc, "_planner_task")
    if task is None:
        report.add(layer, "task", "FAIL", None, "no asyncio task — agent not running")
        return None
    if task.done():
        exc = task.exception() if not task.cancelled() else None
        report.add(layer, "task", "FAIL", "done", f"agent stopped: {exc!r}" if exc else "cancelled")
        return None
    report.add(layer, "task", "OK", "running")

    running = _attr(planner, "_running")
    if not running:
        report.add(layer, "agent._running", "FAIL", running, "agent claims not running")

    pipeline = _attr(planner, "_pipeline")
    if pipeline is None:
        report.add(layer, "pipeline", "FAIL", None, "no PipelineController")
        return None
    report.add(layer, "pipeline", "OK", type(pipeline).__name__)

    event_port = _attr(planner, "_event_port")
    if event_port is None:
        report.add(layer, "event_port", "FAIL", None, "agent has no event_port")
        return None
    report.add(layer, "event_port", "OK", type(event_port).__name__)
    return event_port


async def probe_drive_one_turn(event_port: Any, report: ProbeReport, timeout_s: float) -> None:
    layer = "Planner E2E"

    # Build minimal PlanRequest
    try:
        from k1.orchestrator.types import PlanRequest
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "import_PlanRequest", "FAIL", None, f"{type(exc).__name__}: {exc}")
        return

    request = PlanRequest(
        intent="Probe: book a family trip to Lake Tahoe next weekend",
        trace_id=f"probe-trace-{uuid.uuid4().hex[:8]}",
    )
    report.add(
        layer, "request", "INFO", f"intent={request.intent[:48]}... rid={request.request_id[:12]}"
    )

    # Subscribe to terminal topics
    captured: list[tuple[str, Any]] = []
    delta_count = [0]
    handles: list[Any] = []

    if not hasattr(event_port, "subscribe"):
        report.add(layer, "subscribe_capability", "FAIL", None, "event_port has no subscribe()")
        return

    def _on_ready(*args: Any, **kwargs: Any) -> None:
        evt = args[1] if len(args) >= 2 else (args[0] if args else None)
        captured.append((TOPIC_PLAN_READY, evt))

    def _on_failed(*args: Any, **kwargs: Any) -> None:
        evt = args[1] if len(args) >= 2 else (args[0] if args else None)
        captured.append((TOPIC_PLAN_FAILED, evt))

    def _on_cancelled(*args: Any, **kwargs: Any) -> None:
        evt = args[1] if len(args) >= 2 else (args[0] if args else None)
        captured.append((TOPIC_PLAN_CANCELLED, evt))

    def _on_delta(*args: Any, **kwargs: Any) -> None:
        delta_count[0] += 1

    try:
        for topic, handler in (
            (TOPIC_PLAN_READY, _on_ready),
            (TOPIC_PLAN_FAILED, _on_failed),
            (TOPIC_PLAN_CANCELLED, _on_cancelled),
            (TOPIC_DELTA, _on_delta),
        ):
            try:
                handles.append(event_port.subscribe(topic, handler))
            except Exception as exc:  # noqa: BLE001
                report.add(
                    layer, f"subscribe.{topic}", "FAIL", None, f"{type(exc).__name__}: {exc}"
                )
                return
    finally:
        pass

    # Emit the request via the bus
    try:
        event_port.emit(TOPIC_PLAN_REQUEST, request)
    except Exception as exc:  # noqa: BLE001
        report.add(layer, "emit_plan_request", "FAIL", None, f"{type(exc).__name__}: {exc}")
        return
    report.add(layer, "emit_plan_request", "OK", TOPIC_PLAN_REQUEST)

    # Wait for terminal event or timeout
    t0 = time.perf_counter()
    deadline = t0 + min(timeout_s, 5.0)  # short window for bus path
    terminal: tuple[str, Any] | None = None
    while time.perf_counter() < deadline:
        for c in captured:
            if c[0] in (TOPIC_PLAN_READY, TOPIC_PLAN_FAILED, TOPIC_PLAN_CANCELLED):
                terminal = c
                break
        if terminal is not None:
            break
        await asyncio.sleep(0.1)

    if terminal is None:
        # Bus path failed (likely payload-shape mismatch). Fall back to direct
        # mailbox enqueue to verify the pipeline itself runs.
        report.add(
            layer,
            "bus_path",
            "FAIL",
            None,
            "no terminal event via bus emit (payload normalization mismatch?)",
        )
        report.add(layer, "fallback", "INFO", "trying direct mailbox enqueue")
        try:
            # Reach into agent — direct path
            from k1.kernel.adapters.model_hub_llm_bus import ModelHubLLMBusAdapter  # noqa: F401
        except Exception:  # noqa: BLE001
            pass
        # Find planner and enqueue directly
        # (planner is already accessible via outer scope in run_probe;
        # we re-locate via event_port owner — fall back to None if hidden)
        # Simpler: use captured module globals
        _planner = _PROBE_STATE.get("planner")
        if _planner is None:
            report.add(layer, "direct_enqueue", "FAIL", None, "planner reference lost")
        else:
            try:
                _planner._on_plan_request(TOPIC_PLAN_REQUEST, request)
                report.add(layer, "direct_enqueue", "OK", "called _on_plan_request directly")
            except Exception as exc:  # noqa: BLE001
                report.add(layer, "direct_enqueue", "FAIL", None, f"{type(exc).__name__}: {exc}")
                return
            # Wait again
            t1 = time.perf_counter()
            deadline2 = t1 + (timeout_s - (t1 - t0))
            while time.perf_counter() < deadline2:
                for c in captured:
                    if c[0] in (TOPIC_PLAN_READY, TOPIC_PLAN_FAILED, TOPIC_PLAN_CANCELLED):
                        terminal = c
                        break
                if terminal is not None:
                    break
                await asyncio.sleep(0.1)

    elapsed_ms = (time.perf_counter() - t0) * 1000
    report.add(layer, "deltas_observed", "INFO", delta_count[0])

    if terminal is None:
        report.add(
            layer,
            "terminal_event",
            "FAIL",
            None,
            f"no terminal event within {timeout_s:.0f}s ({elapsed_ms:.0f}ms elapsed)",
        )
        return

    topic, payload = terminal
    if topic == TOPIC_PLAN_READY:
        report.add(
            layer,
            "terminal_event",
            "OK",
            f"PLAN_READY in {elapsed_ms:.0f}ms",
            _summarize_payload(payload),
        )
        # Inspect plan shape
        d = (
            payload.to_dict()
            if hasattr(payload, "to_dict")
            else (payload if isinstance(payload, dict) else {})
        )
        steps = d.get("steps") if isinstance(d, dict) else None
        if isinstance(steps, list):
            report.add(layer, "plan.steps", "OK" if steps else "WARN", len(steps))
        plan_id = d.get("plan_id") if isinstance(d, dict) else None
        report.add(layer, "plan.plan_id", "OK" if plan_id else "WARN", plan_id)
    elif topic == TOPIC_PLAN_FAILED:
        report.add(
            layer,
            "terminal_event",
            "FAIL",
            f"PLAN_FAILED in {elapsed_ms:.0f}ms",
            _summarize_payload(payload),
        )
    elif topic == TOPIC_PLAN_CANCELLED:
        report.add(
            layer,
            "terminal_event",
            "WARN",
            f"PLAN_CANCELLED in {elapsed_ms:.0f}ms",
            _summarize_payload(payload),
        )


async def probe_pipeline_stages(svc: Any, report: ProbeReport) -> None:
    """Read-only inspect each stage on the pipeline so we know what was wired."""
    layer = "Planner Stages"
    planner = _attr(svc, "_planner")
    pipeline = _attr(planner, "_pipeline") if planner else None
    if pipeline is None:
        return
    for stage_attr in ("_sketch", "_expand", "_validate", "_commit"):
        obj = _attr(pipeline, stage_attr)
        if obj is None:
            report.add(layer, stage_attr.lstrip("_"), "FAIL", None, "stage not wired")
        else:
            report.add(layer, stage_attr.lstrip("_"), "OK", type(obj).__name__)


# ── runner ─────────────────────────────────────────────────────────────


async def run_probe(json_path: str | None, timeout_s: float) -> int:
    print("=" * 72)
    print(_c("  K1 Kernel Probe — Phase 4 (Planner E2E)", "\x1b[1m"))
    print("=" * 72)

    cfg = KernelConfig(model_mode="test")
    t0 = time.perf_counter()
    runtime = await start_kernel(cfg)
    boot_s = time.perf_counter() - t0
    print(f"  Boot: {boot_s:.2f}s\n")

    report = ProbeReport()
    svc = runtime._service

    # planner.start() runs in a background task — wait for _running=True
    planner = _attr(svc, "_planner")
    _PROBE_STATE["planner"] = planner
    wait_t0 = time.perf_counter()
    while planner is not None and not _attr(planner, "_running", False):
        if time.perf_counter() - wait_t0 > 5.0:
            break
        await asyncio.sleep(0.05)
    ready_ms = (time.perf_counter() - wait_t0) * 1000
    report.add(
        "Planner Wiring",
        "agent_ready_wait",
        "OK" if _attr(planner, "_running", False) else "WARN",
        f"{ready_ms:.0f}ms",
    )

    event_port = await probe_planner_agent_wiring(svc, report)
    await probe_pipeline_stages(svc, report)

    if event_port is not None:
        await probe_drive_one_turn(event_port, report, timeout_s)

    report.render("K1 Kernel Probe — Phase 4 (Planner E2E)")

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
    ap.add_argument(
        "--timeout", type=float, default=30.0, help="seconds to wait for terminal event"
    )
    args = ap.parse_args()
    return asyncio.run(run_probe(args.json, args.timeout))


if __name__ == "__main__":
    sys.exit(main())
