"""Tests for temporal event bus adapter envelope metadata."""

from __future__ import annotations

import json
from typing import Any

from k1.temporal.adapters.event_bus_adapter import EventBusAdapter
from k1.temporal.events import TEMPORAL_ANCHOR_CREATED


class _CaptureBus:
    def __init__(self) -> None:
        self.published: list[Any] = []

    def publish(self, envelope: Any) -> None:
        self.published.append(envelope)


async def test_event_bus_adapter_preserves_session_id_on_envelope() -> None:
    bus = _CaptureBus()
    adapter = EventBusAdapter(bus)

    await adapter.publish(
        TEMPORAL_ANCHOR_CREATED,
        {
            "session_id": "s-temporal",
            "trace_id": "tr-temporal",
            "anchor_id": "a-temporal",
        },
    )

    assert len(bus.published) == 1
    envelope = bus.published[0]
    assert envelope.topic == TEMPORAL_ANCHOR_CREATED
    assert envelope.session_id == "s-temporal"
    assert envelope.cognitive_trace_id == "tr-temporal"
    assert json.loads(envelope.payload.decode("utf-8"))["session_id"] == "s-temporal"
