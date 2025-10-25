"""Integration tests for the K1 event bus runtime.

Validates behaviour mandated by ADR-0004a (Layer 1→2 event bus contract),
ADR-0045d (backpressure handling), and ADR-0061 (overflow policy telemetry).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, cast

from prometheus_client import REGISTRY
from ward import fixture, test  # type: ignore[attr-defined]

from k1.l5_infrastructure.event_bus import event_bus as event_bus_module
from k1.l5_infrastructure.event_bus.event_bus import EventBus
from k1.l5_infrastructure.event_bus.schemas import (EventBase, EventTopic,
                                                    IntentDetectedEvent)

_TRACE_ID = "5f2d4c7a8b3e41e8a9d9c6f1b2a4d687"
_SESSION_ID = "session_56789"
_TIMESTAMP = datetime(2025, 10, 24, 12, 0, 0, tzinfo=timezone.utc)


def _intent_event(**overrides: Any) -> IntentDetectedEvent:
    payload: Dict[str, Any] = {
        "session_id": _SESSION_ID,
        "cognitive_trace_id": _TRACE_ID,
        "timestamp": _TIMESTAMP,
        "intent": "weather_query",
        "confidence": 0.91,
        "tier": "T1_RULE",
        "entities": {"location": "San Francisco"},
    }
    payload.update(overrides)
    return IntentDetectedEvent(**payload)


@fixture
async def event_bus() -> AsyncGenerator[EventBus, None]:
    bus = EventBus()
    yield bus
    await bus.shutdown()


@test("event bus delivers payloads to topic subscribers without copying")
async def _(event_bus_fixture=event_bus) -> None:
    bus = cast(EventBus, event_bus_fixture)
    delivered = asyncio.Event()
    received: List[IntentDetectedEvent] = []

    async def handler(event: EventBase) -> None:
        received.append(cast(IntentDetectedEvent, event))
        delivered.set()

    handle = bus.subscribe(EventTopic.INTENT_DETECTED, handler)
    try:
        event = _intent_event()
        await bus.publish(event)
        await asyncio.wait_for(delivered.wait(), timeout=0.2)
    finally:
        await handle.unsubscribe()

    assert received, "Expected subscriber to receive at least one event"
    assert received[0] is event, "Events should be delivered by reference (zero-copy)"


@test("wildcard subscriptions receive matching topics")
async def _(event_bus_fixture=event_bus) -> None:
    bus = cast(EventBus, event_bus_fixture)
    received = asyncio.Event()
    topics: List[str] = []

    async def wildcard_handler(event: EventBase) -> None:
        topics.append(event.topic.value)
        received.set()

    handle = bus.subscribe("intent_*", wildcard_handler)
    try:
        await bus.publish(_intent_event(intent="set_alarm"))
        await asyncio.wait_for(received.wait(), timeout=0.2)
    finally:
        await handle.unsubscribe()

    assert topics == [EventTopic.INTENT_DETECTED.value]


@test("queue overflow drops oldest event and records overflow metric")
async def _(event_bus_fixture=event_bus) -> None:
    bus = cast(EventBus, event_bus_fixture)
    original_start = event_bus_module._Subscriber.start

    def start_without_task(self) -> None:  # type: ignore[override]
        self.task = None

    event_bus_module._Subscriber.start = start_without_task
    try:
        async def handler(event: EventBase) -> None:  # pragma: no cover - not invoked
            return None

        handle = bus.subscribe(EventTopic.INTENT_DETECTED, handler, queue_depth=1)
        try:
            subscriber = bus._subscribers[handle._subscriber_id]  # type: ignore[attr-defined]
            topic_value = EventTopic.INTENT_DETECTED.value
            metric_name = "k1_intelligence_event_bus_overflow_total"
            labels = {"topic": topic_value, "subscriber": subscriber.name}

            baseline = REGISTRY.get_sample_value(metric_name, labels) or 0.0

            first = _intent_event(intent="first_intent")
            second = _intent_event(intent="second_intent")

            await subscriber.enqueue(topic_value, first)
            assert subscriber.queue.qsize() == 1

            await subscriber.enqueue(topic_value, second)
            assert subscriber.queue.qsize() == 1, "Queue depth should remain capped"

            latest = subscriber.queue.get_nowait()
            assert latest is second

            updated = REGISTRY.get_sample_value(metric_name, labels) or 0.0
            assert updated - baseline == 1.0, "Expected overflow counter to increment by one"
        finally:
            await handle.unsubscribe()
    finally:
        event_bus_module._Subscriber.start = original_start
        event_bus_module._Subscriber.start = original_start
        finally:
            await handle.unsubscribe()
    finally:
        event_bus_module._Subscriber.start = original_start
