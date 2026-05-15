"""M3-L5..M3-L8 live-kernel ModelHub probes.

Coverage:
  M3-L5 | MESSAGE-FLOW | ModelHub CHAT request → completed event fires on bus | I3.7.1
  M3-L6 | NEGATIVE     | create_standalone() leaves event_port=None (ISSUE-M01) | xfail
  M3-L7 | MESSAGE-FLOW | Cache hit on identical CHAT, miss on TOOL_CALL | I3.7.2/.3
  M3-L8 | NEGATIVE     | All providers' CBs OPEN → NoEligibleProviderError | I3.7.5
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from k1.kernel.service import KernelConfig, KernelService
from k1.model_hub.factory import ModelHubFactory
from k1.model_hub.manifest import CircuitBreakerConfig as MHCircuitBreakerConfig
from k1.model_hub.types import (
    CapabilityType,
    ChatPayload,
    HubRequest,
    Message,
    NoEligibleProviderError,
    RequestConstraints,
    ToolCallPayload,
    ToolDefinition,
)

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Shared helpers (mirrors m3_l1_l4 helpers)
# ---------------------------------------------------------------------------

_TOPIC_MH_COMPLETED = "k1.model_hub.request.completed.v1"
_TOPIC_MH_FAILED = "k1.model_hub.request.failed.v1"

# Stub provider ID registered by KernelService in model_mode="test"
_STUB_PROVIDER_ID = "stub"


def _active_task_snapshot() -> set[asyncio.Task[object]]:
    current = asyncio.current_task()
    return {task for task in asyncio.all_tasks() if task is not current and not task.done()}


def _recipe_a(tmp_path: Path, **overrides: Any) -> KernelConfig:
    values: dict[str, Any] = {
        "test_mode": True,
        "model_mode": "test",
        "ordered_bus": True,
        "session_mode": "standalone",
        "bridge_enabled": False,
        "bridge_offline_ok": True,
        "otel_enabled": False,
        "enable_hitl": False,
        "enable_hil_service": False,
        "enable_self_model": False,
        "enable_family_tools": False,
        "sessionstate_db_path": str(tmp_path / "ssm.db"),
        "workflow_db_path": str(tmp_path / "workflows.db"),
        "bridge_outbox_path": str(tmp_path / "bridge.db"),
    }
    values.update(overrides)
    return KernelConfig(**values)


async def _assert_no_task_leaks(baseline_tasks: set[asyncio.Task[object]]) -> None:
    await asyncio.sleep(0)
    leaked = _active_task_snapshot() - baseline_tasks
    assert leaked == set(), f"Leaked tasks: {[task.get_name() for task in leaked]}"


async def _cleanup_service(
    svc: KernelService,
    baseline_tasks: set[asyncio.Task[object]],
    session_id: str | None = None,
) -> None:
    if session_id is not None and session_id in svc._sessions:
        await svc.destroy_session(session_id)
    if svc.is_running:
        await svc.shutdown()
    await _assert_no_task_leaks(baseline_tasks)


def _raw_bus(bus: Any) -> Any:
    return getattr(bus, "inner", bus)


def _decode_mh_payload(envelope: Any) -> dict[str, Any]:
    return json.loads(envelope.payload.decode("utf-8"))


def _make_chat_request(trace_id: str, session_id: str = "") -> HubRequest:
    """Build a minimal CHAT HubRequest."""
    return HubRequest(
        capability=CapabilityType.CHAT,
        payload=ChatPayload(
            messages=[Message(role="user", content="hello from m3 live probe")],
        ),
        constraints=RequestConstraints(consumer_id="m3-live-test"),
        trace_id=trace_id,
        session_id=session_id,
    )


def _make_tool_call_request(trace_id: str, session_id: str = "") -> HubRequest:
    """Build a minimal TOOL_CALL HubRequest."""
    return HubRequest(
        capability=CapabilityType.TOOL_CALL,
        payload=ToolCallPayload(
            messages=[Message(role="user", content="please call a tool")],
            tools=[
                ToolDefinition(
                    name="probe_tool",
                    description="M3 live probe tool",
                    parameters={},
                )
            ],
        ),
        constraints=RequestConstraints(consumer_id="m3-live-test"),
        trace_id=trace_id,
        session_id=session_id,
    )


# ---------------------------------------------------------------------------
# M3-L5 — MESSAGE-FLOW: CHAT request emits completed event on K1 bus
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_m3_l5_modelhub_chat_emits_completed_event_on_bus(
    tmp_path: Path,
) -> None:
    """I3.7.1 — Live kernel ModelHub CHAT pipeline publishes
    k1.model_hub.request.completed.v1 on the shared K1 bus with
    matching trace_id.

    Confirms:
      - MHEventBusAdapter(bus=svc._bus) is wired in model_mode="test".
      - The RequestRouter._publish() path reaches the real bus.
      - The event envelope carries the correct trace_id and request_id.
    """
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()

        trace_id = "trace-m3-l5-chat"
        hub_req = _make_chat_request(trace_id)

        captured: list[Any] = []
        raw_bus = _raw_bus(svc._bus)
        handle_completed = raw_bus.subscribe(_TOPIC_MH_COMPLETED, captured.append)

        try:
            response = await svc._model_hub.execute(hub_req)

            # Give bus a tick to dispatch handlers
            await asyncio.sleep(0)

            assert response is not None, "ModelHub.execute() returned None"

            # Assert the completed event fired
            assert (
                len(captured) >= 1
            ), f"Expected at least 1 event on {_TOPIC_MH_COMPLETED}, got {len(captured)}"

            # Decode and validate payload
            payload = _decode_mh_payload(captured[0])
            assert (
                payload.get("trace_id") == trace_id
            ), f"trace_id mismatch: expected {trace_id!r}, got {payload.get('trace_id')!r}"
            assert payload.get("request_id") == hub_req.request_id, (
                f"request_id mismatch: expected {hub_req.request_id!r}, "
                f"got {payload.get('request_id')!r}"
            )
            assert payload.get("capability") == CapabilityType.CHAT.value, (
                f"capability mismatch: expected {CapabilityType.CHAT.value!r}, "
                f"got {payload.get('capability')!r}"
            )
        finally:
            raw_bus.unsubscribe(handle_completed)

    finally:
        await _cleanup_service(svc, baseline_tasks)


# ---------------------------------------------------------------------------
# M3-L6 — NEGATIVE/xfail: create_standalone() leaves event_port unwired
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.xfail(
    strict=True,
    reason=(
        "ISSUE-M01: ModelHubFactory.create_standalone() does not wire event_port "
        "into RequestRouter — all bus-topic publications are silently suppressed."
    ),
)
async def test_m3_l6_create_standalone_event_port_not_wired_gap(
    tmp_path: Path,  # noqa: ARG001
) -> None:
    """ISSUE-M01 GAP locked in.

    ModelHubFactory.create_standalone() builds the RequestRouter without an
    event_port (event_port=None). As a result, every _publish() call inside
    the pipeline is a no-op — all 10 event topics are silently suppressed.

    This test asserts the DESIRED behaviour (event_port is wired). Because
    create_standalone() does NOT wire it today, the assertion fails and
    pytest records an expected failure (xfail), confirming the gap.

    Fix: create_standalone() should accept an optional event_port argument
    and pass it to RequestRouter, matching the behaviour of create_with_ports().
    """
    hub = ModelHubFactory.create_standalone()
    # Desired: event_port is wired (not None)
    # Actual:  event_port is None  → assertion FAILS → xfail confirms ISSUE-M01
    assert (
        hub._router._event_port is not None
    ), "ISSUE-M01: create_standalone() left event_port=None in RequestRouter"


# ---------------------------------------------------------------------------
# M3-L7 — MESSAGE-FLOW: Cache hit on identical CHAT, miss on TOOL_CALL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_m3_l7_cache_hit_on_repeated_chat_miss_on_tool_call(
    tmp_path: Path,
) -> None:
    """I3.7.2 / I3.7.3 — ResponseCache honours capability skip rules.

    * Identical CHAT requests → second call returns the same HubResponse
      object (r1 is r2), confirming the LRU cache was hit.
    * TOOL_CALL requests with the same payload → each call produces a fresh
      HubResponse object (tc1 is not tc2), confirming TOOL_CALL is in the
      skip-capabilities set and is never cached.
    """
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()

        # --- CHAT: first request populates cache; second hits it ------------
        trace_id_chat = "trace-m3-l7-chat"
        # Use same HubRequest object for both calls to guarantee identical
        # cache key (capability + payload + model_id + temperature + session_id).
        chat_req = _make_chat_request(trace_id_chat)

        r1 = await svc._model_hub.execute(chat_req)
        r2 = await svc._model_hub.execute(chat_req)

        assert r1 is r2, (
            "Expected second identical CHAT request to return the cached HubResponse "
            "object (same Python identity), but got a new object — cache miss."
        )

        # --- TOOL_CALL: cache skip rule in effect ---------------------------
        trace_id_tc = "trace-m3-l7-toolcall"
        tool_req = _make_tool_call_request(trace_id_tc)

        tc1 = await svc._model_hub.execute(tool_req)
        tc2 = await svc._model_hub.execute(tool_req)

        assert tc1 is not tc2, (
            "Expected TOOL_CALL requests to bypass the cache (each produces a fresh "
            "HubResponse), but got the same object — TOOL_CALL was incorrectly cached."
        )

    finally:
        await _cleanup_service(svc, baseline_tasks)


# ---------------------------------------------------------------------------
# M3-L8 — NEGATIVE: All providers' CBs OPEN → NoEligibleProviderError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_m3_l8_all_circuit_breakers_open_raises_no_eligible_provider(
    tmp_path: Path,
) -> None:
    """I3.7.5 / MH-14 — When every registered provider's CB is OPEN,
    CapabilityRouter returns an empty eligible list and RequestRouter raises
    NoEligibleProviderError instead of silently falling back.

    Procedure:
      1. Boot Recipe A (StubProviderPlugin registered as "stub").
      2. Reach into the shared CircuitBreakerManager and register the stub
         provider with a low threshold config.
      3. Record 3 consecutive failures to trip the CB to OPEN.
      4. Execute a CHAT request → assert NoEligibleProviderError.
    """
    svc = KernelService(config=_recipe_a(tmp_path))
    baseline_tasks = _active_task_snapshot()

    try:
        await svc.startup()

        # Reach into the shared CB manager (same object used by both
        # CapabilityRouter and ProviderDispatcher).
        circuit_mgr = svc._model_hub._router._dispatcher._circuit_mgr

        # Register the stub provider with a 3-failure threshold (default).
        cb_cfg = MHCircuitBreakerConfig(
            failure_threshold=3,
            failure_window_s=60,
            cooldown_s=30,
        )
        circuit_mgr.register_provider(_STUB_PROVIDER_ID, cb_cfg)

        # Trip the CB to OPEN by recording threshold failures.
        for _ in range(cb_cfg.failure_threshold):
            circuit_mgr.record_failure(_STUB_PROVIDER_ID)

        # Verify CB is now OPEN before making the request.
        from k1.model_hub.types import CircuitState

        state = circuit_mgr.get_state(_STUB_PROVIDER_ID)
        assert state == CircuitState.OPEN, (
            f"Expected CB to be OPEN after {cb_cfg.failure_threshold} failures, " f"got {state}"
        )

        # Execute CHAT → CapabilityRouter sees 0 eligible providers → error.
        hub_req = _make_chat_request("trace-m3-l8-cb-open")
        with pytest.raises(NoEligibleProviderError):
            await svc._model_hub.execute(hub_req)

    finally:
        await _cleanup_service(svc, baseline_tasks)
