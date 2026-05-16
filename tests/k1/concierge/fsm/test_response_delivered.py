"""M0.E1.I2: ResponseDelivered delivery-intent ordering tests."""

from __future__ import annotations

import json
from typing import Any

from k1.bus.envelope import Envelope, PayloadFormat, Priority
from k1.concierge.bus.setup import create_poc_bus, create_poc_router
from k1.concierge.bus.topics import TOPIC_FINAL_RESPONSE
from k1.concierge.events.conversation import ResponseDelivered, ResponseFinalDecided
from k1.concierge.fsm.controller import ConciergeController
from k1.concierge.fsm.states import ConciergeState


class RecordingLedger:
    session_id = "m0-response-delivered"

    def __init__(self) -> None:
        self.events: list[Any] = []

    def append_sync(self, event: Any) -> int:
        self.events.append(event)
        return len(self.events)


def _final_response_env(text: str = "done") -> Envelope:
    return Envelope(
        topic=TOPIC_FINAL_RESPONSE,
        payload=json.dumps({"text": text}).encode(),
        payload_format=PayloadFormat.JSON,
        priority=Priority.INTERACTIVE,
        envelope_id=42,
        cognitive_trace_id="trace-m0",
        session_id="session-m0",
        request_id="request-m0",
        created_ns=1_000,
    )


def test_response_delivered_is_appended_before_side_effect_executor(
    monkeypatch,
) -> None:
    bus = create_poc_bus(capture=True)
    router = create_poc_router()
    ctrl = ConciergeController(bus=bus, router=router)
    ledger = RecordingLedger()
    ctrl.set_ledger(ledger)
    ctrl._state = ConciergeState.DISPATCHING
    ctrl._turn_number = 1

    executor_observed_events: list[str] = []

    def spy_executor(_decision, _envelope) -> None:  # type: ignore[no-untyped-def]
        executor_observed_events.extend(event.event_type for event in ledger.events)

    monkeypatch.setattr(ctrl, "_execute_response_final_decision", spy_executor)

    ctrl._on_response_final(_final_response_env("hello from Front"))

    assert [event.event_type for event in ledger.events[:2]] == [
        ResponseFinalDecided().event_type,
        ResponseDelivered().event_type,
    ]
    assert executor_observed_events[:2] == [
        ResponseFinalDecided().event_type,
        ResponseDelivered().event_type,
    ]
    assert isinstance(ledger.events[0], ResponseFinalDecided)
    assert isinstance(ledger.events[1], ResponseDelivered)
    assert ledger.events[1].text_preview == "hello from Front"
    assert ledger.events[1].entry_type == "final"
