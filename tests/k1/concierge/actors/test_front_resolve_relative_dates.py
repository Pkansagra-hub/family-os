"""M2-E1: Front resolves relative dates before task dispatch."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Mapping

import pytest

from k1.bus.envelope import Envelope
from k1.concierge.react.loop import ReactResult
from k1.temporal.service import TemporalService


class _EmptySessionState:
    def get_section(self, name: str) -> Any:
        raise KeyError(name)


class _CaptureBus:
    def __init__(self) -> None:
        self.published: list[Any] = []

    def publish(self, envelope: Any) -> None:
        self.published.append(envelope)


class _Clock:
    def now_utc(self) -> str:
        return "2025-01-15T12:00:00+00:00"

    def monotonic_ms(self) -> int:
        return 1


class _Ids:
    def __init__(self) -> None:
        self.count = 0

    def _next(self, prefix: str) -> str:
        self.count += 1
        return f"{prefix}-{self.count}"

    def new_anchor_id(self) -> str:
        return self._next("anchor")

    def new_window_id(self) -> str:
        return self._next("window")

    def new_resolution_id(self) -> str:
        return self._next("resolution")


class _State:
    def __init__(self) -> None:
        self.payloads: dict[str, Mapping[str, Any]] = {}

    async def write_section(self, session_id: str, payload: Mapping[str, Any]) -> None:
        self.payloads[session_id] = payload

    async def read_section(self, session_id: str) -> Mapping[str, Any] | None:
        return self.payloads.get(session_id)


def _temporal_service() -> TemporalService:
    return TemporalService(clock=_Clock(), id_port=_Ids(), state_port=_State())


def _envelope(text: str) -> Envelope:
    return Envelope(
        topic="k1.session.user.input.v1",
        payload=json.dumps({"text": text}).encode("utf-8"),
        session_id="s-front-m2",
        cognitive_trace_id="tr-front-m2",
    )


def _task_dispatch_payloads(bus: _CaptureBus) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for envelope in bus.published:
        if getattr(envelope, "topic", "") == "k1.orchestration.task.dispatch.v1":
            payloads.append(json.loads(envelope.payload.decode("utf-8")))
    return payloads


@pytest.mark.asyncio
async def test_front_resolves_tomorrow_into_dispatch_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from k1.concierge.actors import front as front_module

    async def _fake_react_loop(**_: Any) -> ReactResult:
        return ReactResult(
            status="complete",
            text="",
            dispatched_tasks=[
                {
                    "task_id": "task-m2-tomorrow",
                    "intents": [
                        {
                            "action": "check calendar",
                            "domain": "calendar",
                            "params": {"subject_ref": "subject_ref", "date": "tomorrow"},
                        }
                    ],
                    "reference_context": {"subject_ref": "subject_ref"},
                    "tier": "LOW",
                    "safety_band": "GREEN",
                }
            ],
        )

    monkeypatch.setattr(front_module, "react_loop", _fake_react_loop)
    monkeypatch.setattr(front_module, "_write_runtime_prompt_dump", lambda **_: None)

    bus = _CaptureBus()
    tool_dispatcher = SimpleNamespace(ctx=SimpleNamespace(session_id="", cognitive_trace_id=""))

    await front_module.front_handler(
        envelope=_envelope("What does subject_ref have tomorrow?"),
        model=SimpleNamespace(),
        ss=_EmptySessionState(),
        bus=bus,
        tool_dispatcher=tool_dispatcher,
        all_tool_schemas=[],
        temporal=_temporal_service(),
    )

    payload = _task_dispatch_payloads(bus)[0]
    refs = payload["resolved_temporal_refs"]
    tomorrow = refs["tomorrow"]

    assert tomorrow["resolution_kind"] == "window"
    assert tomorrow["window"]["start_local"] == "2025-01-16T00:00:00+00:00"
    assert tomorrow["window"]["end_local"] == "2025-01-17T00:00:00+00:00"
    assert payload["reference_context"]["resolved_temporal_refs"] == refs
    assert payload["reference_context"]["grounding"]["resolved_temporal_refs"] == refs


@pytest.mark.asyncio
async def test_front_marks_ambiguous_temporal_field_without_guessing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from k1.concierge.actors import front as front_module

    async def _fake_react_loop(**_: Any) -> ReactResult:
        return ReactResult(
            status="complete",
            text="",
            dispatched_tasks=[
                {
                    "task_id": "task-m2-ambiguous",
                    "intents": [
                        {
                            "action": "schedule reminder",
                            "domain": "reminders",
                            "params": {"subject_ref": "subject_ref", "date": "someday"},
                        }
                    ],
                    "tier": "LOW",
                    "safety_band": "GREEN",
                }
            ],
        )

    monkeypatch.setattr(front_module, "react_loop", _fake_react_loop)
    monkeypatch.setattr(front_module, "_write_runtime_prompt_dump", lambda **_: None)

    bus = _CaptureBus()
    tool_dispatcher = SimpleNamespace(ctx=SimpleNamespace(session_id="", cognitive_trace_id=""))

    await front_module.front_handler(
        envelope=_envelope("Schedule it someday."),
        model=SimpleNamespace(),
        ss=_EmptySessionState(),
        bus=bus,
        tool_dispatcher=tool_dispatcher,
        all_tool_schemas=[],
        temporal=_temporal_service(),
    )

    payload = _task_dispatch_payloads(bus)[0]

    assert payload["requires_temporal_clarification"] is True
    assert payload["resolved_temporal_refs"]["someday"]["needs_clarification"] is True
    assert payload["temporal_clarification_reasons"] == {"someday": "unknown_expression"}
    assert payload["reference_context"]["requires_temporal_clarification"] is True
