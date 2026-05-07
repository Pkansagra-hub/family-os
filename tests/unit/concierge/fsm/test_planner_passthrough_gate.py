"""M16.E1.I3 — PassthroughPlannerStub gate.

When ``allow_planner_passthrough`` is False (production default) and no
orchestrator is wired, HIGH-tier dispatch must surface the missing
orchestrator loudly via :class:`OrchestratorNotWired` AND publish a
``task.failed`` envelope on the session bus, instead of silently
collapsing the HIGH task into a 1-step MEDIUM plan via the legacy
PassthroughPlannerStub.

When ``allow_planner_passthrough`` is True, the legacy stub path is
preserved (test/dev contexts).
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from k1.concierge.fsm.controller import ConciergeController, OrchestratorNotWired
from k1.concierge.task.complexity import ComplexityTier
from k1.concierge.task.dispatch import TaskDispatch
from k1.concierge.task.intent import TaskIntent


def _make_controller(
    *, allow_passthrough: bool
) -> tuple[ConciergeController, MagicMock, MagicMock]:
    """Build a minimally-wired controller bypassing the heavy __init__."""
    ctrl = object.__new__(ConciergeController)
    bus = MagicMock()
    router = MagicMock()
    ctrl._bus = bus
    ctrl._router = router
    ctrl._ss = None
    ctrl._active_task_ids = set()
    ctrl._control_ext = MagicMock()
    ctrl._orchestrator = None
    ctrl._weave_batcher = None
    ctrl._allow_planner_passthrough = allow_passthrough
    ctrl._state = MagicMock(name="EXECUTING")
    return ctrl, bus, router


def _make_envelope() -> MagicMock:
    envelope = MagicMock()
    envelope.envelope_id = 7
    envelope.topic = "k1.orchestration.task.dispatch.v1"
    return envelope


def _make_dispatch() -> TaskDispatch:
    return TaskDispatch(
        intents=[TaskIntent(action="plan_trip", params={})],
        tier=ComplexityTier.HIGH,
        safety_band="GREEN",
    )


def test_high_tier_no_orchestrator_strict_raises() -> None:
    ctrl, bus, router = _make_controller(allow_passthrough=False)
    dispatch = _make_dispatch()
    envelope = _make_envelope()

    with pytest.raises(OrchestratorNotWired):
        ctrl._route_via_orchestrator(envelope, dispatch)

    # task.failed envelope must be published before the raise so the
    # FSM/Front observe a deterministic outcome.
    failed_topics = [call.args[0].topic for call in bus.publish.call_args_list]
    assert "k1.orchestration.task.failed.v1" in failed_topics

    # Locate the task.failed envelope and assert payload shape.
    failed_env = next(
        call.args[0]
        for call in bus.publish.call_args_list
        if call.args[0].topic == "k1.orchestration.task.failed.v1"
    )
    payload = json.loads(failed_env.payload.decode())
    assert payload["error_code"] == "ORCH_NOT_WIRED"
    assert payload["reason"] == "orchestrator_not_wired"

    # Strict mode must NOT route the envelope to Back.
    assert router.deliver.called is False


def test_high_tier_no_orchestrator_passthrough_allowed() -> None:
    ctrl, bus, router = _make_controller(allow_passthrough=True)
    dispatch = _make_dispatch()
    envelope = _make_envelope()

    # Legacy passthrough must NOT raise and must NOT publish task.failed.
    ctrl._route_via_orchestrator(envelope, dispatch)

    failed_topics = [call.args[0].topic for call in bus.publish.call_args_list]
    assert "k1.orchestration.task.failed.v1" not in failed_topics

    # Legacy path falls through to Back via MEDIUM routing.
    assert router.deliver.called
