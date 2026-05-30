"""Regression coverage for Front temporal session binding."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

from k1.bus.envelope import Envelope
from k1.concierge.react.loop import ReactResult


class _EmptySessionState:
    def get_section(self, name: str) -> Any:
        raise KeyError(name)


class _CaptureBus:
    def __init__(self) -> None:
        self.published: list[Any] = []

    def publish(self, envelope: Any) -> None:
        self.published.append(envelope)


class _TemporalRecorder:
    session_id = "web-678195ff"

    def __init__(self) -> None:
        self.refresh_session_id: str | None = None
        self.projection_session_id: str | None = None
        self.refresh_kwargs: dict[str, Any] = {}

    async def refresh_turn(self, session_id: str | None, **kwargs: Any) -> Any:
        self.refresh_session_id = session_id
        self.refresh_kwargs = kwargs
        return SimpleNamespace(session_id=session_id)

    async def build_projection(self, session_id: str | None, consumer: str) -> None:
        self.projection_session_id = session_id
        return None


def test_front_handler_uses_bound_temporal_session_when_envelope_session_empty(monkeypatch) -> None:
    from k1.concierge.actors import front as front_module

    async def _fake_react_loop(**_: Any) -> ReactResult:
        return ReactResult(status="ok", text="ok", dispatched_tasks=[])

    monkeypatch.setattr(front_module, "react_loop", _fake_react_loop)
    monkeypatch.setattr(front_module, "_write_runtime_prompt_dump", lambda **_: None)

    temporal = _TemporalRecorder()
    bus = _CaptureBus()
    tool_dispatcher = SimpleNamespace(ctx=SimpleNamespace(session_id="", cognitive_trace_id=""))
    envelope = Envelope(
        topic="k1.user.message.v1",
        payload=json.dumps({"text": "what day is tomorrow?", "device_id": "alex_phone"}).encode(
            "utf-8"
        ),
        session_id="",
        cognitive_trace_id="tr-front-temporal",
    )

    asyncio.run(
        front_module.front_handler(
            envelope=envelope,
            model=SimpleNamespace(),
            ss=_EmptySessionState(),
            bus=bus,
            tool_dispatcher=tool_dispatcher,
            all_tool_schemas=[],
            temporal=temporal,
        )
    )

    assert temporal.refresh_session_id == "web-678195ff"
    assert temporal.projection_session_id == "web-678195ff"
    assert temporal.refresh_kwargs["device_id"] == "alex_phone"
    assert temporal.refresh_kwargs["installation_id"] == "alex_phone"
    assert tool_dispatcher.ctx.session_id == "web-678195ff"
    assert bus.published
    assert {envelope.session_id for envelope in bus.published} == {"web-678195ff"}
