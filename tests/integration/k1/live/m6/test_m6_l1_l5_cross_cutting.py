"""M6-L1..M6-L5 live-kernel cross-cutting probes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from k1.bus.envelope import Envelope, PayloadFormat
from k1.fabric.adapters.null_state_reader import NullSessionStateReaderAdapter
from k1.fabric.adapters.sessionstate_reader import SessionStateReaderAdapter
from k1.fabric.adapters.test_state_reader import TestSessionStateReaderAdapter
from k1.hil.service import HumanInTheLoopService
from k1.hil.topics import TOPIC_HIL_REQUEST, TOPIC_HIL_RESPONSE
from k1.hil.types import ApprovalRequest, HILKind, HILResponseEnvelope
from k1.kernel.adapters.session_routing_reader import SessionRoutingStateReader
from k1.kernel.service import KernelService
from k1.orchestrator.adapters.mock_state_read_adapter import MockStateReadAdapter
from k1.orchestrator.adapters.state_read_adapter import StateReadAdapter
from k1.planner.adapters.session_state_adapter import SessionStateReadAdapter
from k1.selfmodel.kernel import SelfModelHandle, SelfModelServiceBundle
from tests.integration.k1.live.m6.helpers import active_task_snapshot as _active_task_snapshot
from tests.integration.k1.live.m6.helpers import cleanup_service as _cleanup_service
from tests.integration.k1.live.m6.helpers import fabric_state_reader as _fabric_state_reader
from tests.integration.k1.live.m6.helpers import recipe_a as _recipe_a
from tests.integration.k1.live.m6.helpers import recipe_b_hil as _recipe_b_hil
from tests.integration.k1.live.m6.helpers import recipe_c_selfmodel as _recipe_c_selfmodel

pytestmark = pytest.mark.integration


def _planner_state_adapter(svc: KernelService) -> Any:
    return svc._planner._pipeline._sketch._tool_router._state_read


@pytest.mark.asyncio
async def test_m6_l1_orchestrator_planner_fabric_read_live_session_state(
    tmp_path: Path,
) -> None:
    """Orch, Planner, and Fabric state readers resolve the live per-session SSM."""
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))
    session_id = "m6l1"

    try:
        await svc.startup()
        session = await svc.create_session(session_id)

        routing_reader = svc._session_routing_reader
        assert isinstance(routing_reader, SessionRoutingStateReader)
        assert routing_reader._session_lookup(session_id) is session.session_state

        shared_fabric_reader = _fabric_state_reader(svc._shared_fabric)
        assert shared_fabric_reader is routing_reader
        assert not isinstance(shared_fabric_reader, NullSessionStateReaderAdapter)
        assert not isinstance(shared_fabric_reader, TestSessionStateReaderAdapter)

        orchestrator_state_port = svc._orchestrator._state_port
        assert isinstance(orchestrator_state_port, StateReadAdapter)
        assert not isinstance(orchestrator_state_port, MockStateReadAdapter)
        assert orchestrator_state_port._reader is routing_reader

        planner_state_port = _planner_state_adapter(svc)
        assert isinstance(planner_state_port, SessionStateReadAdapter)
        assert planner_state_port._reader is routing_reader

        planner_snapshot = await planner_state_port.read_sections(
            ["control"],
            session_id=session_id,
        )
        assert planner_snapshot.session_id == session_id
        assert planner_state_port._reader._session_lookup(session_id) is session.session_state

        session_fabric_reader = _fabric_state_reader(session.fabric)
        assert isinstance(session_fabric_reader, SessionStateReaderAdapter)
        assert not isinstance(session_fabric_reader, NullSessionStateReaderAdapter)
        assert session_fabric_reader._manager is session.session_state
        assert session_fabric_reader._session_id == session_id
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
async def test_m6_l2_hil_approval_round_trip_on_live_session_bus(tmp_path: Path) -> None:
    """Recipe B HIL approval publishes a request and resolves from session-bus response."""
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_b_hil(tmp_path))
    session_id = "m6l2"

    try:
        await svc.startup()
        session = await svc.create_session(session_id)
        hil_service = session.hil_port
        assert isinstance(hil_service, HumanInTheLoopService)

        subscriptions = session.bus.list_subscriptions()
        assert any(topic == TOPIC_HIL_RESPONSE for topic, _ in subscriptions)

        requests: list[dict[str, Any]] = []

        def approve_request(envelope: Envelope) -> None:
            request = json.loads(envelope.payload.decode("utf-8"))
            requests.append(request)
            response = HILResponseEnvelope(
                hil_request_id=request["hil_request_id"],
                kind=HILKind.APPROVAL,
                responded_at_ms=request["created_at_ms"] + 1,
                payload={"decision": "approve"},
            ).to_dict()
            session.bus.publish(
                Envelope(
                    topic=TOPIC_HIL_RESPONSE,
                    payload=json.dumps(response, separators=(",", ":")).encode("utf-8"),
                    cognitive_trace_id=request["trace_id"],
                    session_id=session_id,
                    payload_format=PayloadFormat.JSON,
                )
            )

        handle = session.bus.subscribe(TOPIC_HIL_REQUEST, approve_request)
        try:
            response = await hil_service.request_approval(
                ApprovalRequest(
                    caller_key="m6:l2",
                    trace_id="trace-m6-l2",
                    summary="Approve a cross-cutting M6 probe.",
                    side_effects=["records green HIL evidence"],
                    timeout_ms=5_000,
                )
            )
        finally:
            session.bus.unsubscribe(handle)

        assert response.decision == "approve"
        assert response.timed_out is False
        assert len(requests) == 1
        assert requests[0]["kind"] == HILKind.APPROVAL.value
        assert requests[0]["caller_key"] == "m6:l2"
        assert requests[0]["trace_id"] == "trace-m6-l2"
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
async def test_m6_l3_selfmodel_gate_is_step_zero_on_front_and_back_dispatchers(
    tmp_path: Path,
) -> None:
    """Recipe C installs one SelfModelHandle gate on both live dispatchers."""
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_c_selfmodel(tmp_path))

    try:
        await svc.startup()
        session = await svc.create_session("m6l3")
        handle = session.self_model

        assert isinstance(handle, SelfModelHandle)
        assert handle.bundle is svc.self_model_bundle
        assert handle.gate is not None
        assert session.concierge.self_model is handle
        assert session.front_dispatcher.policy_gate == handle.gate.evaluate
        assert session.back_dispatcher.policy_gate == handle.gate.evaluate
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
async def test_m6_l4_selfmodel_bundle_health_ok_on_live_kernel(tmp_path: Path) -> None:
    """Recipe C exposes a healthy SelfModel bundle on the running kernel."""
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_c_selfmodel(tmp_path))

    try:
        await svc.startup()
        bundle = svc.self_model_bundle
        assert isinstance(bundle, SelfModelServiceBundle)

        health = bundle.health()
        assert health["status"] == "ok"
        assert health["constitution"]["available"] is True
        assert health["constitution"]["safe_mode"] is False
        assert health["family_space_id"] == "family:m6"
        assert health["store"]["kind"] == "SQLiteProjectionStore"
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason=(
        "M6 supervision gap: k1/supervision is an empty stub and KernelService "
        "has no parent/child cancellation tree yet."
    ),
)
async def test_m6_l5_parent_task_cancel_cascades_to_children_without_orphans(
    tmp_path: Path,
) -> None:
    """Desired future behavior: parent cancellation reaches all child traces."""
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))

    try:
        await svc.startup()
        await svc.create_session("m6l5")
        supervision_tree = getattr(svc, "_supervision_tree", None)
        assert supervision_tree is not None, "KernelService has no supervision tree wired"
        cancel_parent = getattr(supervision_tree, "cancel_parent_task", None)
        assert callable(cancel_parent), "supervision tree cannot cancel a parent task"

        result = await cancel_parent("parent-task", reason="test_cancel")
        assert result.child_traces_cancelled
        assert result.orphan_envelopes == []
    finally:
        await _cleanup_service(svc, baseline_tasks)
