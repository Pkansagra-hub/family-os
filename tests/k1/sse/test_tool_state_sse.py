"""E15.10 — SSE Subscription in K1 tests.

Covers:
1. BusSsePublisher.publish() calls the injected forward callable.
2. TOPIC_TOOL_STATE_CHANGED has the expected string value.
3. DEFAULT_RULES maps ``k1.tool_state`` prefix to BEST_EFFORT.
4. pseudo-K0 SSE endpoint fan-out: push event → streaming client receives it.
5. KernelService._consume_tool_sse() publishes received events to the bus.
6. WebSocketRenderer.send_tool_refresh() broadcasts the correct shape.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# 1. BusSsePublisher.publish() calls the injected forward callable
# ---------------------------------------------------------------------------


def test_bus_sse_publisher_calls_forward():
    from k1.tools.family.sse_adapters import BusSsePublisher

    received: list[tuple[str, dict]] = []

    def _forward(topic: str, payload: dict) -> None:
        received.append((topic, payload))

    pub = BusSsePublisher(forward=_forward)
    pub.publish("k1.tool_state.changed.v1", {"tool": "tasks", "action": "create"})

    assert len(received) == 1
    topic, payload = received[0]
    assert topic == "k1.tool_state.changed.v1"
    assert payload["tool"] == "tasks"


# ---------------------------------------------------------------------------
# 2. TOPIC_TOOL_STATE_CHANGED constant value
# ---------------------------------------------------------------------------


def test_topic_constant_value():
    from k1.concierge.bus.topics import TOPIC_TOOL_STATE_CHANGED

    assert TOPIC_TOOL_STATE_CHANGED == "k1.tool_state.changed.v1"


# ---------------------------------------------------------------------------
# 3. Timing rule: k1.tool_state → BEST_EFFORT
# ---------------------------------------------------------------------------


def test_timing_rule_is_best_effort():
    from k1.bus.envelope import DeliveryMode
    from k1.bus.timing.defaults import DEFAULT_RULES

    assert DEFAULT_RULES.get("k1.tool_state") == DeliveryMode.BEST_EFFORT


# ---------------------------------------------------------------------------
# 4. pseudo-K0 SSE fan-out: push via broadcast_sse, client stream receives it
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pseudo_k0_sse_fanout():
    """broadcast_sse() puts a frame on all registered queues."""
    from fastapi import FastAPI

    from scripts.pseudo_k0.server import broadcast_sse

    app = FastAPI()
    app.state.sse_broker = {}

    # Simulate a connected subscriber by registering a queue manually.
    q: asyncio.Queue = asyncio.Queue(maxsize=256)
    app.state.sse_broker["tool_state.changed.v1"] = [q]

    broadcast_sse(app, "tool_state.changed.v1", {"tool": "tasks", "action": "done"})

    assert not q.empty()
    frame: str = await asyncio.wait_for(q.get(), timeout=1.0)
    assert frame.startswith("data: ")
    data = json.loads(frame[6:])
    assert data["tool"] == "tasks"
    assert data["action"] == "done"


# ---------------------------------------------------------------------------
# 5. KernelService._consume_tool_sse() publishes events to the K1 bus
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_consume_tool_sse_publishes_to_bus():
    """_consume_tool_sse() should publish one Envelope per SSE frame."""
    from k1.bus.envelope import Envelope
    from k1.concierge.bus.topics import TOPIC_TOOL_STATE_CHANGED

    fake_config = MagicMock()
    fake_config.selfmodel_space_id = "family:test"

    published: list[Envelope] = []
    fake_bus = MagicMock()
    fake_bus.publish.side_effect = published.append

    # First call: yield one event.  Second call: raise CancelledError so the
    # while-True loop in _consume_tool_sse exits instead of hanging forever.
    call_count = 0

    async def _fake_subscribe_sse(topics, space_id=""):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            yield {"tool": "tasks", "action": "create", "space_id": space_id}
        else:
            raise asyncio.CancelledError

    from k1.kernel.adapters.live_bridge_adapter import LiveBridgeAdapter

    fake_bridge = MagicMock(spec=LiveBridgeAdapter)
    fake_bridge.subscribe_sse = _fake_subscribe_sse

    from k1.kernel.service import KernelService

    svc = object.__new__(KernelService)
    svc._config = fake_config
    svc._bus = fake_bus
    svc._bridge = fake_bridge

    await svc._consume_tool_sse()

    assert len(published) == 1
    env = published[0]
    assert env.topic == TOPIC_TOOL_STATE_CHANGED
    payload = json.loads(env.payload)
    assert payload["tool"] == "tasks"
    assert payload["space_id"] == "family:test"


# ---------------------------------------------------------------------------
# 6. WebSocketRenderer.send_tool_refresh() broadcasts the correct shape
# ---------------------------------------------------------------------------


def test_renderer_send_tool_refresh():
    from ui.web.renderer import WebSocketRenderer

    broadcast_calls: list[dict[str, Any]] = []

    renderer = object.__new__(WebSocketRenderer)
    renderer._broadcast_sync = broadcast_calls.append  # type: ignore[method-assign]

    renderer.send_tool_refresh("tasks", space_id="family:test")

    assert len(broadcast_calls) == 1
    msg = broadcast_calls[0]
    assert msg["type"] == "tool_refresh"
    assert msg["adapter"] == "tasks"
    assert msg["space_id"] == "family:test"
    assert "timestamp" in msg
