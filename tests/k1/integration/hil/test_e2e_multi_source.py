"""E8.M2.6 — Multi-source convergence end-to-end.

Verifies the singleton invariant from the HIL Unification Plan: a single
``HumanInTheLoopService`` instance handles concurrent requests from
planner, concierge, and fabric surfaces, each with a distinct
``hil_request_id`` and an independently-routed response.

Per E8 exit criteria:
  1. The same ``HumanInTheLoopService`` services all three surfaces.
  2. Three distinct ``hil_request_id`` values are observed.
  3. Each scripted response routes to the correct caller (responses do
     not cross-contaminate; callers receive their kind-specific payload).
  4. Total wall time is < 1s — requests fan out concurrently rather
     than serialising.

No mocks; only the user is simulated.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from k1.hil.types import (
    CapabilityContractView,
    CapabilityGateRequest,
    ClarificationRequest,
    GateOutcome,
    HILKind,
    NeedsHumanRequest,
)


@pytest.mark.asyncio
async def test_three_surfaces_resolve_concurrently(
    kernel_service, hil_user_simulator
) -> None:
    """Planner / concierge / fabric requests fan out and resolve in parallel."""

    # Distinct kind-specific scripts so we can prove no cross-contamination.
    hil_user_simulator.script(
        HILKind.CLARIFICATION,
        lambda req: {"answer": f"clar::{req.payload.get('question', '')}"},
    )
    hil_user_simulator.script(
        HILKind.NEEDS_HUMAN,
        lambda req: {
            "decision": "selected",
            "resolution": {"selected_option": 1, "task_id": req.payload.get("task_id")},
        },
    )
    hil_user_simulator.script(
        HILKind.CAPABILITY_GATE,
        lambda req: {"approved": True, "reason": f"ok::{req.payload.get('capability_name')}"},
    )

    hil = kernel_service.hil_service

    clar_req = ClarificationRequest(
        caller_key="planner:multi-source",
        trace_id="trace-multi-clar",
        question_context={"goal": "demo"},
        synthesize_with_llm=False,
        pre_formed_question="Q1",
        timeout_ms=2000,
    )
    nh_req = NeedsHumanRequest(
        caller_key="concierge:task-multi",
        task_id="task-multi",
        trace_id="trace-multi-nh",
        hil_type="selection",
        question="pick one",
        options=[{"label": "A"}, {"label": "B"}],
        timeout_ms=2000,
    )
    gate_req = CapabilityGateRequest(
        caller_key="fabric:calendar_delete_event",
        trace_id="trace-multi-gate",
        capability_name="calendar_delete_event",
        contract=CapabilityContractView(
            name="calendar_delete_event",
            safety_band_min="AMBER",
            requires_human_confirmation=None,
            side_effects=[],
            description="multi-source gate",
        ),
        params={"event_id": "evt-1"},
        params_summary="event_id=evt-1",
        timeout_ms=2000,
    )

    t0 = time.monotonic()
    clar_resp, nh_resp, gate_resp = await asyncio.gather(
        hil.ask_clarification(clar_req),
        hil.needs_human(nh_req),
        hil.gate_capability(gate_req),
    )
    elapsed_ms = (time.monotonic() - t0) * 1000.0

    # Per-response correctness (no cross-contamination).
    assert clar_resp.timed_out is False
    assert clar_resp.answer == "clar::Q1"

    assert nh_resp.timed_out is False
    assert nh_resp.decision == "selected"
    assert nh_resp.resolution == {"selected_option": 1, "task_id": "task-multi"}

    assert gate_resp.outcome is GateOutcome.ASK_APPROVED
    assert gate_resp.user_approved is True
    assert gate_resp.reason == "ok::calendar_delete_event"

    # Three distinct hil_request_ids.
    ids = {clar_resp.hil_request_id, nh_resp.hil_request_id, gate_resp.hil_request_id}
    assert len(ids) == 3
    assert all(ids)  # no empty sentinels

    # Concurrency budget per E8 exit criteria.
    assert elapsed_ms < 1000.0, f"multi-source took {elapsed_ms:.1f}ms (>1s)"

    # The simulator saw exactly one envelope per kind, with matching ids.
    assert len(hil_user_simulator.received) == 3
    by_kind = {env.kind: env for env in hil_user_simulator.received}
    assert set(by_kind) == {
        HILKind.CLARIFICATION,
        HILKind.NEEDS_HUMAN,
        HILKind.CAPABILITY_GATE,
    }
    assert by_kind[HILKind.CLARIFICATION].caller_key == "planner:multi-source"
    assert by_kind[HILKind.NEEDS_HUMAN].caller_key == "concierge:task-multi"
    assert by_kind[HILKind.CAPABILITY_GATE].caller_key == "fabric:calendar_delete_event"
    # Wire ids match the response ids.
    assert {env.hil_request_id for env in hil_user_simulator.received} == ids


@pytest.mark.asyncio
async def test_single_service_instance_shared_across_surfaces(
    kernel_service,
) -> None:
    """All four downstream subsystems share the SAME ``HumanInTheLoopService``."""

    svc = kernel_service
    session = await svc.create_session("e8-m26-share")
    try:
        the_one = svc.hil_service
        assert the_one is not None
        assert svc._orchestrator._constraint_resolver._hil_port is the_one  # type: ignore[attr-defined]
        assert svc._planner._pipeline._hil_port is the_one  # type: ignore[attr-defined]
        assert svc._shared_fabric.facade._hil_port is the_one  # type: ignore[attr-defined]
        assert session.concierge.hil_port is the_one
        assert session.concierge.fsm._hil_port is the_one
    finally:
        await svc.destroy_session("e8-m26-share")
