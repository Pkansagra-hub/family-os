"""M6-X1..M6-X15 cross-component integration probes."""

from __future__ import annotations

import asyncio
import inspect
import json
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

import k1.concierge.actors.back as back_mod
from k1.bus.envelope import Envelope, PayloadFormat
from k1.bus.factory import BusFactory
from k1.concierge.actors.back import _maybe_rebind_back_dispatcher, back_cancel_handler
from k1.concierge.bus.builders import build_task_cancel, build_task_resume
from k1.concierge.llm.types import ToolCallResult
from k1.concierge.protocols.cancellation import CancellationToken, CancelReason
from k1.concierge.protocols.suspension import (
    SuspensionLimitExceeded,
    SuspensionRequest,
    SuspensionResolution,
    SuspensionType,
)
from k1.concierge.react.loop import ReactResult, react_loop
from k1.concierge.tools.dispatcher import create_back_dispatcher
from k1.concierge.tools.implementations import ToolContext
from k1.hil.service import HumanInTheLoopService
from k1.hil.suspension import SuspensionManager
from k1.hil.topics import TOPIC_HIL_REQUEST, TOPIC_HIL_RESPONSE
from k1.hil.types import (
    ApprovalRequest,
    CapabilityContractView,
    CapabilityGateRequest,
    GateOutcome,
    HILKind,
    HILResponseEnvelope,
)
from k1.kernel.service import KernelService
from k1.orchestrator.factory import _NullHILAdapter as OrchestratorNullHILAdapter
from k1.planner.factory import _NullHILAdapter as PlannerNullHILAdapter
from k1.selfmodel.adapters.recall_citation_wrapper import RecallCitationWrapper
from k1.selfmodel.contracts.policy import PolicyDecision, PolicyVerdict, ReasonCode
from k1.selfmodel.contracts.situation import SituationFrame
from k1.selfmodel.kernel import SelfModelHandle, SelfModelServiceBundle
from k1.selfmodel.service.errors import ConstitutionUnavailableError
from tests.integration.k1.live.m6.helpers import active_task_snapshot as _active_task_snapshot
from tests.integration.k1.live.m6.helpers import cleanup_service as _cleanup_service
from tests.integration.k1.live.m6.helpers import recipe_a as _recipe_a
from tests.integration.k1.live.m6.helpers import recipe_b_hil as _recipe_b_hil
from tests.integration.k1.live.m6.helpers import recipe_c_selfmodel as _recipe_c_selfmodel
from tests.integration.k1.live.m6.helpers import recipe_c_selfmodel_hil as _recipe_c_selfmodel_hil

pytestmark = pytest.mark.integration


class _RequireConfirmationEvaluator:
    def evaluate(self, *_args: Any, **_kwargs: Any) -> PolicyVerdict:
        return PolicyVerdict(
            decision=PolicyDecision.REQUIRE_CONFIRMATION,
            reason=ReasonCode.NEEDS_CONFIRMATION,
            detail="m6-x confirmation probe",
        )


def _decode(envelope: Envelope) -> dict[str, Any]:
    return json.loads(envelope.payload.decode("utf-8"))


async def _approve_next_hil_request(session: Any, requests: list[dict[str, Any]]) -> Any:
    def approve(envelope: Envelope) -> None:
        request = _decode(envelope)
        requests.append(request)
        response = HILResponseEnvelope(
            hil_request_id=request["hil_request_id"],
            kind=HILKind(request["kind"]),
            responded_at_ms=request["created_at_ms"] + 1,
            payload={"decision": "approve", "approved": True},
        ).to_dict()
        session.bus.publish(
            Envelope(
                topic=TOPIC_HIL_RESPONSE,
                payload=json.dumps(response, separators=(",", ":")).encode("utf-8"),
                cognitive_trace_id=request["trace_id"],
                session_id=session.session_id,
                payload_format=PayloadFormat.JSON,
            )
        )

    return session.bus.subscribe(TOPIC_HIL_REQUEST, approve)


def _module_root() -> Path:
    return Path(__file__).resolve().parents[5]


@pytest.mark.asyncio
async def test_m6_x1_selfmodel_policy_gate_identity_after_p35(tmp_path: Path) -> None:
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_c_selfmodel(tmp_path))

    try:
        await svc.startup()
        session = await svc.create_session("m6x1")
        handle = session.self_model

        assert isinstance(handle, SelfModelHandle)
        assert handle.gate is not None
        assert session.front_dispatcher.policy_gate == handle.gate.evaluate
        assert session.back_dispatcher.policy_gate == handle.gate.evaluate
        assert session.front_dispatcher in handle._installed_dispatchers
        assert session.back_dispatcher in handle._installed_dispatchers
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
async def test_m6_x2_selfmodel_install_uninstall_is_idempotent(tmp_path: Path) -> None:
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_c_selfmodel(tmp_path))

    try:
        await svc.startup()
        session = await svc.create_session("m6x2")
        handle = session.self_model
        assert isinstance(handle, SelfModelHandle)
        assert handle.gate is not None

        original_dispatchers = tuple(handle._installed_dispatchers)
        original_wrapped = tuple(handle._wrapped_contexts)
        front_recall = session.front_ctx.recall_fn
        back_recall = session.back_ctx.recall_fn

        handle.install_into_session(
            front_dispatcher=session.front_dispatcher,
            back_dispatcher=session.back_dispatcher,
            front_ctx=session.front_ctx,
            back_ctx=session.back_ctx,
        )

        assert tuple(handle._installed_dispatchers) == original_dispatchers
        assert tuple(handle._wrapped_contexts) == original_wrapped
        assert session.front_ctx.recall_fn is front_recall
        assert session.back_ctx.recall_fn is back_recall

        originals_by_ctx = {id(ctx): original for ctx, original in original_wrapped}
        handle.uninstall_from_session()

        assert handle._installed_dispatchers == []
        assert handle._wrapped_contexts == []
        assert session.front_dispatcher.policy_gate is None
        assert session.back_dispatcher.policy_gate is None
        if id(session.front_ctx) in originals_by_ctx:
            assert session.front_ctx.recall_fn is originals_by_ctx[id(session.front_ctx)]
            assert not isinstance(session.front_ctx.recall_fn, RecallCitationWrapper)
        if id(session.back_ctx) in originals_by_ctx:
            assert session.back_ctx.recall_fn is originals_by_ctx[id(session.back_ctx)]
            assert not isinstance(session.back_ctx.recall_fn, RecallCitationWrapper)

        handle.uninstall_from_session()
        assert session.front_dispatcher.policy_gate is None
        assert session.back_dispatcher.policy_gate is None
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
async def test_m6_x3_back_rebind_preserves_policy_gate_and_hil_approval_resumes_dispatch(
    tmp_path: Path,
) -> None:
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_c_selfmodel_hil(tmp_path))

    try:
        await svc.startup()
        session = await svc.create_session("m6x3")
        handle = session.self_model
        assert isinstance(handle, SelfModelHandle)
        assert handle.gate is not None

        rebound = _maybe_rebind_back_dispatcher(session.back_dispatcher, "HIGH", session.bus)
        try:
            assert rebound.ctx is session.back_dispatcher.ctx
            assert rebound.policy_gate == handle.gate.evaluate

            handle.gate._evaluator = _RequireConfirmationEvaluator()
            handle.gate._frame_provider = lambda _tool_call: SituationFrame(
                actor_id=handle.actor_id,
                situation_kind=handle.situation_kind,
            )
            requests: list[dict[str, Any]] = []
            sub = await _approve_next_hil_request(session, requests)
            try:
                result = await rebound.policy_gate(
                    ToolCallResult(
                        id="call-m6-x3",
                        name="send_message",
                        arguments={"body": "confirm me"},
                    )
                )
            finally:
                session.bus.unsubscribe(sub)

            assert result is None
            assert len(requests) == 1
            assert requests[0]["kind"] == HILKind.APPROVAL.value
            assert requests[0]["caller_key"].startswith("selfmodel:gate:")
        finally:
            rebound.set_policy_gate(None)
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
async def test_m6_x4_selfmodel_bundle_shutdown_closes_owned_sqlite_once(
    tmp_path: Path,
) -> None:
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_c_selfmodel(tmp_path))

    try:
        await svc.startup()
        bundle = svc.self_model_bundle
        assert isinstance(bundle, SelfModelServiceBundle)
        assert bundle._owns_store is True

        store = bundle.store
        bundle.shutdown()
        assert bundle._owns_store is False
        with pytest.raises(sqlite3.ProgrammingError):
            store._conn.execute("SELECT 1")

        bundle.shutdown()
        assert bundle._owns_store is False
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
async def test_m6_x5_selfmodel_disabled_skips_bundle_gates_and_topics(tmp_path: Path) -> None:
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path))

    try:
        await svc.startup()
        session = await svc.create_session("m6x5")

        assert svc.self_model_bundle is None
        assert session.self_model is None
        assert session.concierge.self_model is None
        assert session.front_dispatcher.policy_gate is None
        assert session.back_dispatcher.policy_gate is None
        assert not any(
            topic.startswith("k1.selfmodel.") for topic, _ in session.bus.list_subscriptions()
        )
        assert not any(event["phase"] == "S2.6_complete" for event in svc.lifecycle_events())
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
async def test_m6_x6_selfmodel_health_reports_ok_degraded_and_safe_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_c_selfmodel(tmp_path))

    try:
        await svc.startup()
        bundle = svc.self_model_bundle
        assert isinstance(bundle, SelfModelServiceBundle)
        assert bundle.health()["status"] == "ok"

        def raise_unavailable() -> None:
            raise ConstitutionUnavailableError("m6-x degraded")

        monkeypatch.setattr(bundle.constitution, "get_active", raise_unavailable)
        bundle.safe_mode = False
        assert bundle.health()["status"] == "degraded"

        bundle.safe_mode = True
        assert bundle.health()["status"] == "safe_mode"
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
async def test_m6_x7_hil_session_bus_subscription_and_approval_future_resolution(
    tmp_path: Path,
) -> None:
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_b_hil(tmp_path))

    try:
        await svc.startup()
        session = await svc.create_session("m6x7")
        hil_service = session.hil_port
        assert isinstance(hil_service, HumanInTheLoopService)
        assert any(topic == TOPIC_HIL_RESPONSE for topic, _ in session.bus.list_subscriptions())

        kernel_requests: list[Envelope] = []
        kernel_sub = svc._bus.subscribe(TOPIC_HIL_REQUEST, kernel_requests.append)
        requests: list[dict[str, Any]] = []
        session_sub = await _approve_next_hil_request(session, requests)
        try:
            response = await hil_service.request_approval(
                ApprovalRequest(
                    caller_key="m6:x7",
                    trace_id="trace-m6-x7",
                    summary="Approve M6-X7.",
                    timeout_ms=5_000,
                )
            )
        finally:
            session.bus.unsubscribe(session_sub)
            svc._bus.unsubscribe(kernel_sub)

        assert response.decision == "approve"
        assert response.timed_out is False
        assert len(requests) == 1
        assert kernel_requests == []
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
async def test_m6_x8_green_no_side_effect_capability_gate_short_circuits_without_hil_request(
    tmp_path: Path,
) -> None:
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_b_hil(tmp_path))

    try:
        await svc.startup()
        session = await svc.create_session("m6x8")
        requests: list[Envelope] = []
        sub = session.bus.subscribe(TOPIC_HIL_REQUEST, requests.append)
        try:
            decision = await session.hil_port.gate_capability(
                CapabilityGateRequest(
                    caller_key="m6:x8",
                    trace_id="trace-m6-x8",
                    capability_name="safe.read",
                    contract=CapabilityContractView(
                        name="safe.read",
                        safety_band_min="GREEN",
                        requires_human_confirmation=None,
                        side_effects=[],
                    ),
                )
            )
            await asyncio.sleep(0)
        finally:
            session.bus.unsubscribe(sub)

        assert decision.outcome is GateOutcome.ALLOW
        assert decision.hil_request_id is None
        assert requests == []
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.asyncio
async def test_m6_x9_suspension_manager_limits_and_timeout_auto_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timed_out: asyncio.Event = asyncio.Event()
    timeout_task_ids: list[str] = []

    async def on_timeout(task_id: str) -> None:
        timeout_task_ids.append(task_id)
        timed_out.set()

    mgr = SuspensionManager(on_timeout_fn=on_timeout)
    try:
        await mgr.suspend(
            SuspensionRequest(
                task_id="m6x9-limit",
                suspension_type=SuspensionType.CLARIFICATION,
                question="one?",
            )
        )
        with pytest.raises(ValueError):
            await mgr.suspend(
                SuspensionRequest(
                    task_id="m6x9-limit",
                    suspension_type=SuspensionType.APPROVAL,
                    question="concurrent?",
                )
            )
        await mgr.resolve(SuspensionResolution(task_id="m6x9-limit", resolution="one"))
        await mgr.suspend(
            SuspensionRequest(
                task_id="m6x9-limit",
                suspension_type=SuspensionType.SELECTION,
                question="two?",
            )
        )
        await mgr.resolve(SuspensionResolution(task_id="m6x9-limit", resolution="two"))
        with pytest.raises(SuspensionLimitExceeded):
            await mgr.suspend(
                SuspensionRequest(
                    task_id="m6x9-limit",
                    suspension_type=SuspensionType.CLARIFICATION,
                    question="three?",
                )
            )

        monkeypatch.setattr(
            SuspensionRequest,
            "timeout_seconds",
            property(lambda _self: 0.001),
        )
        await mgr.suspend(
            SuspensionRequest(
                task_id="m6x9-timeout",
                suspension_type=SuspensionType.APPROVAL,
                question="timeout?",
            )
        )
        await asyncio.wait_for(timed_out.wait(), timeout=1.0)
        assert timeout_task_ids == ["m6x9-timeout"]
        assert not mgr.is_suspended("m6x9-timeout")
    finally:
        mgr.reset()
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_m6_x10_back_resume_handler_rereads_fresh_session_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class PromptSection:
        def __init__(self, text: str) -> None:
            self._text = text

        def to_prompt(self) -> str:
            return self._text

    class ChangingSS:
        def __init__(self) -> None:
            self.belief_reads = 0

        def get_section(self, name: str) -> Any:
            if name == "beliefs_active":
                self.belief_reads += 1
                return PromptSection(f"belief-version-{self.belief_reads}")
            return None

    ss = ChangingSS()
    stale_snapshot = back_mod._read_ss_snapshot(ss)
    assert "belief-version-1" in stale_snapshot["beliefs_prompt"]

    captured: dict[str, Any] = {}

    async def fake_react_loop(**kwargs: Any) -> ReactResult:
        captured.update(kwargs)
        return ReactResult(status="complete", data={"final_answer": "done"})

    monkeypatch.setattr(back_mod, "react_loop", fake_react_loop)

    bus = BusFactory.create_local_ordered(capture=False)
    dispatcher = create_back_dispatcher(
        tier="simple",
        ctx=ToolContext(session_manager=ss),
        bus=bus,
    )
    envelope = build_task_resume(
        payload={
            "task_id": "m6x10",
            "resolution": {"additional_info": "use the fresh state"},
            "resume_context": {
                "original_task": {"task_id": "m6x10", "tier": "LOW", "action": "probe"},
                "react_history": [{"role": "assistant", "content": "asked"}],
                "hil_type": "clarification",
            },
        }
    )
    envelope = Envelope(
        topic=envelope.topic,
        payload=envelope.payload,
        session_id="m6x10-session",
        request_id="req-m6x10",
        cognitive_trace_id="trace-m6-x10",
        payload_format=PayloadFormat.JSON,
    )

    try:
        result = await back_mod.back_resume_handler(
            envelope=envelope,
            model=object(),
            ss=ss,
            bus=bus,
            tool_dispatcher=dispatcher,
        )
    finally:
        bus.close()

    assert result.status == "complete"
    assert "belief-version-2" in captured["system_prompt"]
    assert "belief-version-1" not in captured["system_prompt"]


@pytest.mark.asyncio
async def test_m6_x11_hil_disabled_uses_null_adapters_and_no_hil_topics(tmp_path: Path) -> None:
    baseline_tasks = _active_task_snapshot()
    svc = KernelService(config=_recipe_a(tmp_path, enable_hitl=True, enable_hil_service=False))

    try:
        await svc.startup()
        session = await svc.create_session("m6x11")

        assert svc.hil_service is None
        assert svc._shared_fabric.facade._hil_port is None
        assert session.fabric.facade._hil_port is None
        assert session.hil_port is None
        assert session.concierge.hil_port is None
        assert session.concierge.fsm._hil_port is None
        assert isinstance(svc._orchestrator.hil_port, OrchestratorNullHILAdapter)
        assert isinstance(svc._planner._pipeline._hil_port, PlannerNullHILAdapter)

        emitted: list[Envelope] = []
        handles = [
            session.bus.subscribe(TOPIC_HIL_REQUEST, emitted.append),
            session.bus.subscribe(TOPIC_HIL_RESPONSE, emitted.append),
        ]
        try:
            await svc._planner._pipeline._hil_port.request_approval(
                ApprovalRequest(
                    caller_key="m6:x11:planner-null",
                    trace_id="trace-m6-x11-planner",
                    summary="null planner approval",
                )
            )
            await svc._orchestrator.hil_port.request_approval(
                ApprovalRequest(
                    caller_key="m6:x11:orch-null",
                    trace_id="trace-m6-x11-orch",
                    summary="null orchestrator approval",
                )
            )
            await asyncio.sleep(0)
        finally:
            for handle in handles:
                session.bus.unsubscribe(handle)

        assert emitted == []
    finally:
        await _cleanup_service(svc, baseline_tasks)


@pytest.mark.xfail(
    strict=True,
    reason="M6-X12 gap: k1.supervision is still an empty stub and KernelService has no supervision tree.",
)
def test_m6_x12_supervision_tree_is_shipped_and_wired_into_kernel() -> None:
    import k1.supervision as supervision

    assert hasattr(supervision, "SupervisionTree")
    assert any("supervision" in name for name, _ in inspect.getmembers(KernelService))


@pytest.mark.asyncio
async def test_m6_x13_back_cancel_handler_stops_react_loop_before_model_execution() -> None:
    token = CancellationToken(task_id="m6x13")
    env = build_task_cancel(payload={"task_id": "m6x13"})

    back_cancel_handler(envelope=env, fsm_state=None, cancel_token=token)

    assert token.is_cancelled is True
    assert token.cancel_reason == CancelReason.USER_REQUESTED

    async def check_cancelled() -> bool:
        return token.is_cancelled

    model = AsyncMock()
    model.execute = AsyncMock()
    result = await react_loop(
        actor="back",
        system_prompt="Back",
        messages=[],
        tools=[],
        max_iterations=10,
        model=model,
        tool_dispatcher=AsyncMock(),
        on_text_response=AsyncMock(),
        cancellation_check=check_cancelled,
        trace_id="trace-m6-x13",
    )

    assert result.status == "cancelled"
    model.execute.assert_not_called()


@pytest.mark.xfail(
    strict=True,
    reason=(
        "M6-X14 gap: learning/retention/scheduler/tracing are stub packages "
        "with no shipped session-bus wiring yet."
    ),
)
def test_m6_x14_stub_cluster_modules_are_shipped_and_session_wired() -> None:
    root = _module_root() / "k1"
    for package in ("learning", "retention", "scheduler", "tracing"):
        package_dir = root / package
        shipped_py = [path for path in package_dir.glob("*.py") if path.name != "__init__.py"]
        assert shipped_py, f"k1/{package} has no shipped Python implementation"


def test_m6_x15_learning_loop_does_not_write_session_state() -> None:
    learning_dir = _module_root() / "k1" / "learning"
    direct_write_markers = (
        "SessionStateManager",
        "DirectWriterAdapter",
        "request_mutation",
        "mutate(",
        "write_section",
        "writer_port",
    )

    offenders: list[str] = []
    for path in learning_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if any(marker in text for marker in direct_write_markers):
            offenders.append(str(path.relative_to(_module_root())))

    assert offenders == []
