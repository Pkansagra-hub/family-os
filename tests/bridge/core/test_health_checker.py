"""MS-3b Epic 3b.1 \u2014 K0HealthChecker async poll loop + transition events.

Complements ``tests/bridge/test_health.py`` (the legacy synchronous-API
suite). These tests target the new behaviours added for offline tolerance:

* ``EventBus`` integration: every state change publishes a
  :class:`HealthTransition` event.
* ``OFFLINE \u2192 ONLINE`` transition emits at least the event the drain
  worker subscribes to.
* Real ``httpx`` poll loop against a real FastAPI loopback that can be
  toggled between healthy / 503 / unresponsive.
* Jittered cadence (\u00b110%).

No mocks: a real FastAPI app on an ephemeral port via ``uvicorn`` config
or via ``httpx.ASGITransport`` for in-process probes.
"""

from __future__ import annotations

import asyncio
import random
import statistics
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI, Response

from bridge.core.events import EventBus, HealthTransition
from bridge.core.health import (
    K0AvailabilityStatus,
    K0HealthChecker,
    K0HealthState,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


def _make_app(state: dict) -> FastAPI:
    """FastAPI loopback whose /healthz response is controlled by ``state``.

    state["mode"] in {"ok", "503", "hang"}; "hang" sleeps for 60s.
    """
    app = FastAPI()

    @app.head("/healthz")
    async def healthz() -> Response:
        if state["mode"] == "hang":
            await asyncio.sleep(60)
            return Response(status_code=200)
        if state["mode"] == "503":
            return Response(status_code=503)
        return Response(status_code=200)

    return app


@pytest.fixture
async def loopback() -> AsyncIterator[tuple[str, dict]]:
    """Real FastAPI app; we drive probes via ``httpx.ASGITransport`` to keep
    the test in-process while still exercising the real httpx code path.
    """
    state: dict = {"mode": "ok"}
    app = _make_app(state)
    transport = httpx.ASGITransport(app=app)
    # Patch httpx.AsyncClient so the checker's lazy import hits the transport.
    original = httpx.AsyncClient

    class _Patched(original):  # type: ignore[misc]
        def __init__(self, *args, **kwargs):
            kwargs.setdefault("transport", transport)
            super().__init__(*args, **kwargs)

    httpx.AsyncClient = _Patched  # type: ignore[assignment]
    try:
        yield ("http://k0.test", state)
    finally:
        httpx.AsyncClient = original  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_k0_health_state_alias_matches_legacy_enum():
    assert K0HealthState is K0AvailabilityStatus


async def test_transition_event_published_on_offline_to_online(bus: EventBus):
    hc = K0HealthChecker(failure_threshold=2, event_bus=bus)
    queue = bus.subscribe(HealthTransition)
    # Start ONLINE so subsequent failures generate transitions.
    hc.record_success(latency_ms=10)
    # Drive to OFFLINE
    hc.record_failure("boom")
    hc.record_failure("boom")
    assert hc.status is K0AvailabilityStatus.OFFLINE
    # Recover
    hc.record_success(latency_ms=10)
    assert hc.status is K0AvailabilityStatus.ONLINE

    seen: list[HealthTransition] = []
    while not queue.empty():
        seen.append(queue.get_nowait())
    transitions = [(e.from_state, e.to_state) for e in seen]
    assert ("OFFLINE", "ONLINE") in transitions
    assert ("ONLINE", "DEGRADED") in transitions
    assert ("DEGRADED", "OFFLINE") in transitions


async def test_no_event_when_state_does_not_change(bus: EventBus):
    hc = K0HealthChecker(failure_threshold=3, event_bus=bus)
    queue = bus.subscribe(HealthTransition)
    hc.record_success(latency_ms=10)  # OFFLINE -> ONLINE = 1 event
    hc.record_success(latency_ms=10)  # ONLINE -> ONLINE = 0 events
    hc.record_success(latency_ms=10)  # ONLINE -> ONLINE = 0 events
    count = 0
    while not queue.empty():
        queue.get_nowait()
        count += 1
    assert count == 1


async def test_force_offline_emits_transition_event(bus: EventBus):
    hc = K0HealthChecker(event_bus=bus)
    hc.record_success(latency_ms=10)
    queue = bus.subscribe(HealthTransition)
    hc.force_offline("manual_shutdown")
    evt = queue.get_nowait()
    assert evt.to_state == "OFFLINE"
    assert evt.reason == "manual_shutdown"


async def test_poll_loop_drives_state_via_real_httpx(loopback, bus: EventBus):
    base_url, state = loopback
    state["mode"] = "ok"
    hc = K0HealthChecker(
        event_bus=bus,
        target_url=base_url,
        poll_interval_s=0.05,
        probe_timeout_s=2.0,
        failure_threshold=2,
    )
    await hc.start()
    try:
        # Wait for ONLINE
        for _ in range(40):
            if hc.status is K0AvailabilityStatus.ONLINE:
                break
            await asyncio.sleep(0.05)
        assert hc.status is K0AvailabilityStatus.ONLINE

        # Flip backend to 503; expect DEGRADED -> OFFLINE eventually
        state["mode"] = "503"
        for _ in range(40):
            if hc.status is K0AvailabilityStatus.OFFLINE:
                break
            await asyncio.sleep(0.05)
        assert hc.status is K0AvailabilityStatus.OFFLINE

        # Recover
        state["mode"] = "ok"
        for _ in range(40):
            if hc.status is K0AvailabilityStatus.ONLINE:
                break
            await asyncio.sleep(0.05)
        assert hc.status is K0AvailabilityStatus.ONLINE
    finally:
        await hc.stop()


async def test_poll_interval_is_jittered_within_ten_percent():
    """Drive the jitter computation directly; assert the spread is bounded.

    We hit ``_next_sleep_s`` 200 times with a deterministic Random and
    assert that all samples lie within \u00b110% of the configured interval
    and that the empirical std dev is non-zero (i.e. jitter actually
    fires).
    """
    hc = K0HealthChecker(
        target_url="http://example.invalid",
        poll_interval_s=1.0,
        rng=random.Random(0xBEEF),
    )
    samples = [hc._next_sleep_s() for _ in range(200)]  # noqa: SLF001
    assert all(0.9 <= s <= 1.1 for s in samples)
    assert statistics.stdev(samples) > 0.0


async def test_stop_is_idempotent_and_safe_when_never_started():
    hc = K0HealthChecker(target_url="http://example.invalid")
    await hc.stop()  # should not raise
    await hc.start()
    await hc.stop()
    await hc.stop()  # second stop is a no-op
