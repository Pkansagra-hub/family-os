"""kernel_probe_phase2_hil.py -- Phase 2 HIL deep-dive probe (post-E7).

Verifies the unified HumanInTheLoopService:
  * is constructed exactly once at S2.5 and shared across every
    subsystem that needs HIL (Concierge, Planner FSM, Fabric facade);
  * actually exchanges request/response envelopes on the bus for each
    of the 5 ``HILKind`` flavours.

A scripted user (`_ScriptedUser`) subscribes to ``TOPIC_HIL_REQUEST``
and replies on ``TOPIC_HIL_RESPONSE`` with canned payloads, mirroring
the production wire shape (JSON-encoded ``HILEnvelope`` /
``HILResponseEnvelope``).

Run::

    $env:PYTHONPATH = "D:\\familyos"
    $env:PYTHONIOENCODING = "utf-8"
    python scripts/kernel_probe_phase2_hil.py
    python scripts/kernel_probe_phase2_hil.py --json data/kernel_probe_hil.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
import time
import uuid
from typing import Any, Callable

from k1.bus.envelope.envelope import Envelope, Priority
from k1.concierge.config.kernel import KernelConfig
from k1.hil.service import HumanInTheLoopService
from k1.hil.topics import TOPIC_HIL_REQUEST, TOPIC_HIL_RESPONSE
from k1.hil.types import (
    ApprovalRequest,
    CapabilityContractView,
    CapabilityGateRequest,
    ClarificationRequest,
    HILEnvelope,
    HILKind,
    HILResponseEnvelope,
    NeedsHumanRequest,
    OverrideRequest,
)
from k1.kernel.bootstrap import start_kernel, stop_kernel
from scripts._probe_common import _C_DIM, ProbeReport, _attr, _c

ResponseFn = Callable[[HILEnvelope], dict[str, Any]]


def _now_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# Scripted user
# ---------------------------------------------------------------------------


class _ScriptedUser:
    """Minimal HIL responder: subscribe to REQUEST, publish RESPONSE."""

    def __init__(self, bus: Any) -> None:
        self._bus = bus
        self._handle: Any = None
        self._lock = threading.RLock()
        self._scripts: dict[HILKind, ResponseFn] = {}
        self.received: list[HILEnvelope] = []

    def script(self, kind: HILKind, fn: ResponseFn) -> None:
        with self._lock:
            self._scripts[kind] = fn

    def start(self) -> None:
        if self._handle is None:
            self._handle = self._bus.subscribe(TOPIC_HIL_REQUEST, self._on_request)

    def stop(self) -> None:
        if self._handle is not None:
            try:
                self._bus.unsubscribe(self._handle)
            except Exception:
                pass
            self._handle = None

    def _on_request(self, envelope: Any) -> None:
        try:
            data = json.loads(envelope.payload.decode("utf-8"))
            req = HILEnvelope.from_dict(data)
        except Exception:
            return

        with self._lock:
            self.received.append(req)
            handler = self._scripts.get(req.kind)
        if handler is None:
            return

        try:
            payload = handler(req)
        except Exception:
            return

        resp = HILResponseEnvelope(
            hil_request_id=req.hil_request_id,
            kind=req.kind,
            responded_at_ms=_now_ms(),
            payload=dict(payload),
            timed_out=False,
        )
        raw = json.dumps(resp.to_dict(), separators=(",", ":"), default=str).encode("utf-8")
        try:
            self._bus.publish(
                Envelope(
                    topic=TOPIC_HIL_RESPONSE,
                    payload=raw,
                    cognitive_trace_id=req.trace_id,
                    priority=Priority.INTERACTIVE,
                )
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Probes
# ---------------------------------------------------------------------------


def probe_hil_singleton(svc: Any, session: Any, report: ProbeReport) -> None:
    """The same HumanInTheLoopService must be visible everywhere."""

    layer = "HIL Singleton"

    kernel_hil = _attr(svc, "_hil_service")
    if kernel_hil is None:
        report.add(
            layer,
            "kernel._hil_service",
            "FAIL",
            None,
            "S2.5 did not construct HumanInTheLoopService",
        )
        return
    if not isinstance(kernel_hil, HumanInTheLoopService):
        report.add(
            layer,
            "kernel._hil_service",
            "FAIL",
            type(kernel_hil).__name__,
            "expected HumanInTheLoopService",
        )
        return
    report.add(layer, "kernel._hil_service", "OK", type(kernel_hil).__name__)

    # Concierge
    concierge_hil = _attr(session, "hil_port") or _attr(session, "hitl_coordinator")
    if concierge_hil is None:
        report.add(layer, "session.hil_port", "FAIL", None, "concierge has no hil_port")
    elif concierge_hil is kernel_hil:
        report.add(layer, "session.hil_port", "OK", "is kernel._hil_service")
    else:
        report.add(
            layer,
            "session.hil_port",
            "FAIL",
            type(concierge_hil).__name__,
            "concierge hil_port is NOT the kernel singleton",
        )

    # FSM
    concierge = _attr(session, "concierge")
    fsm = _attr(concierge, "controller") or _attr(concierge, "fsm")
    fsm_hil = _attr(fsm, "_hil_port")
    if fsm_hil is None:
        report.add(layer, "fsm._hil_port", "FAIL", None, "FSM hil_port not wired")
    elif fsm_hil is kernel_hil:
        report.add(layer, "fsm._hil_port", "OK", "is kernel._hil_service")
    else:
        report.add(
            layer,
            "fsm._hil_port",
            "FAIL",
            type(fsm_hil).__name__,
            "FSM hil_port is NOT the kernel singleton",
        )

    # Fabric facade (per-session fabric is a Fabric container -> .facade)
    fabric = _attr(session, "fabric")
    facade = _attr(fabric, "facade") or fabric
    fabric_hil = _attr(facade, "_hil_port")
    if fabric_hil is None:
        report.add(
            layer,
            "fabric.facade._hil_port",
            "FAIL",
            None,
            "session fabric facade has no _hil_port",
        )
    elif fabric_hil is kernel_hil:
        report.add(layer, "fabric.facade._hil_port", "OK", "is kernel._hil_service")
    else:
        report.add(
            layer,
            "fabric.facade._hil_port",
            "FAIL",
            type(fabric_hil).__name__,
            "fabric facade hil_port is NOT the kernel singleton",
        )

    # Shared fabric (S3-built)
    shared = _attr(svc, "_shared_fabric")
    shared_facade = _attr(shared, "facade") or shared
    shared_hil = _attr(shared_facade, "_hil_port")
    if shared_hil is None:
        report.add(
            layer,
            "shared_fabric.facade._hil_port",
            "WARN",
            None,
            "shared fabric facade has no _hil_port",
        )
    elif shared_hil is kernel_hil:
        report.add(layer, "shared_fabric.facade._hil_port", "OK", "is kernel._hil_service")
    else:
        report.add(
            layer,
            "shared_fabric.facade._hil_port",
            "FAIL",
            type(shared_hil).__name__,
            "shared fabric facade hil_port is NOT the kernel singleton",
        )


async def probe_round_trips(svc: Any, report: ProbeReport) -> None:
    """Drive one real round-trip per HILKind through the singleton."""

    layer = "HIL Round-Trips"
    hil = _attr(svc, "_hil_service")
    if hil is None:
        report.add(layer, "service", "FAIL", None, "no _hil_service to drive")
        return

    bus = _attr(svc, "_bus")
    if bus is None:
        report.add(layer, "bus", "FAIL", None, "no kernel._bus")
        return

    user = _ScriptedUser(bus)
    user.start()
    try:
        # 1. CLARIFICATION
        user.script(HILKind.CLARIFICATION, lambda req: {"answer": "use the personal calendar"})
        try:
            clar = await asyncio.wait_for(
                hil.ask_clarification(
                    ClarificationRequest(
                        caller_key="probe.clar",
                        trace_id=f"probe-{uuid.uuid4().hex[:8]}",
                        question_context={"question": "which calendar?"},
                        synthesize_with_llm=False,
                        pre_formed_question="which calendar?",
                        timeout_ms=5_000,
                    )
                ),
                timeout=10.0,
            )
            if clar.answer == "use the personal calendar":
                report.add(layer, "clarification", "OK", clar.answer)
            else:
                report.add(
                    layer,
                    "clarification",
                    "FAIL",
                    clar.answer,
                    "answer mismatch / timed_out",
                )
        except Exception as exc:  # noqa: BLE001
            report.add(layer, "clarification", "FAIL", None, f"{type(exc).__name__}: {exc}")

        # 2. APPROVAL
        user.script(
            HILKind.APPROVAL,
            lambda req: {"decision": "approve"},
        )
        try:
            appr = await asyncio.wait_for(
                hil.request_approval(
                    ApprovalRequest(
                        caller_key="probe.appr",
                        trace_id=f"probe-{uuid.uuid4().hex[:8]}",
                        summary="run probe plan",
                        side_effects=["data_write"],
                        safety_assessment="AMBER",
                        timeout_ms=5_000,
                    )
                ),
                timeout=10.0,
            )
            if appr.decision == "approve":
                report.add(layer, "approval", "OK", appr.decision)
            else:
                report.add(layer, "approval", "FAIL", appr.decision, "decision mismatch")
        except Exception as exc:  # noqa: BLE001
            report.add(layer, "approval", "FAIL", None, f"{type(exc).__name__}: {exc}")

        # 3. NEEDS_HUMAN
        user.script(
            HILKind.NEEDS_HUMAN,
            lambda req: {
                "decision": "answered",
                "resolution": {"choice": "personal"},
                "raw_user_text": "personal",
            },
        )
        try:
            nh = await asyncio.wait_for(
                hil.needs_human(
                    NeedsHumanRequest(
                        caller_key="probe.nh",
                        task_id=f"task-{uuid.uuid4().hex[:8]}",
                        trace_id=f"probe-{uuid.uuid4().hex[:8]}",
                        hil_type="clarification",
                        question="probe needs human?",
                        timeout_ms=5_000,
                    )
                ),
                timeout=10.0,
            )
            if nh.decision == "answered":
                report.add(layer, "needs_human", "OK", nh.decision)
            else:
                report.add(layer, "needs_human", "FAIL", nh.decision, "decision mismatch")
        except Exception as exc:  # noqa: BLE001
            report.add(layer, "needs_human", "FAIL", None, f"{type(exc).__name__}: {exc}")

        # 4. OVERRIDE
        user.script(
            HILKind.OVERRIDE,
            lambda req: {"choice": "override", "selected_alternative": {"capability": "alt"}},
        )
        try:
            ov = await asyncio.wait_for(
                hil.request_override(
                    OverrideRequest(
                        caller_key="probe.ov",
                        request_id=f"req-{uuid.uuid4().hex[:8]}",
                        trace_id=f"probe-{uuid.uuid4().hex[:8]}",
                        plan_id=f"plan-{uuid.uuid4().hex[:8]}",
                        unresolved_capabilities=["fake.cap"],
                        timeout_ms=5_000,
                    )
                ),
                timeout=10.0,
            )
            if ov.choice == "override":
                report.add(layer, "override", "OK", ov.choice)
            else:
                report.add(layer, "override", "FAIL", ov.choice, "choice mismatch")
        except Exception as exc:  # noqa: BLE001
            report.add(layer, "override", "FAIL", None, f"{type(exc).__name__}: {exc}")

        # 5. CAPABILITY_GATE (AMBER + side-effects -> forces real prompt)
        user.script(
            HILKind.CAPABILITY_GATE,
            lambda req: {"approved": True, "reason": "probe approves"},
        )
        try:
            view = CapabilityContractView(
                name="probe.capability",
                safety_band_min="AMBER",
                requires_human_confirmation=True,
                side_effects=[{"kind": "data_write", "description": "probe write"}],
                description="probe capability gate",
            )
            gd = await asyncio.wait_for(
                hil.gate_capability(
                    CapabilityGateRequest(
                        caller_key="probe.gate",
                        trace_id=f"probe-{uuid.uuid4().hex[:8]}",
                        capability_name="probe.capability",
                        contract=view,
                        params={},
                        params_summary="",
                        timeout_ms=5_000,
                    )
                ),
                timeout=10.0,
            )
            if gd.user_approved is True:
                report.add(layer, "capability_gate", "OK", gd.outcome.value)
            else:
                report.add(
                    layer,
                    "capability_gate",
                    "FAIL",
                    gd.outcome.value,
                    f"user_approved={gd.user_approved}",
                )
        except Exception as exc:  # noqa: BLE001
            report.add(layer, "capability_gate", "FAIL", None, f"{type(exc).__name__}: {exc}")

        report.add(
            layer,
            "scripted_user_received",
            "INFO",
            len(user.received),
        )
    finally:
        user.stop()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


async def run_probe(json_path: str | None) -> int:
    print("=" * 72)
    print(_c("  K1 Kernel Probe -- Phase 2 (HIL deep dive)", "\x1b[1m"))
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
        probe_hil_singleton(svc, session, report)
        await probe_round_trips(svc, report)

    report.render("K1 Kernel Probe -- Phase 2 (HIL deep dive)")

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
