"""Tests for top-level TemporalService."""

from __future__ import annotations

from typing import Any, Mapping

from k1.temporal.service import TemporalService


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
        return self._next("a")

    def new_window_id(self) -> str:
        return self._next("w")

    def new_resolution_id(self) -> str:
        return self._next("r")


class _State:
    def __init__(self) -> None:
        self.payloads: dict[str, Mapping[str, Any]] = {}

    async def write_section(self, session_id: str, payload: Mapping[str, Any]) -> None:
        self.payloads[session_id] = payload

    async def read_section(self, session_id: str) -> Mapping[str, Any] | None:
        return self.payloads.get(session_id)


class _Events:
    def __init__(self) -> None:
        self.events: list[tuple[str, Mapping[str, Any]]] = []

    async def publish(self, topic: str, payload: Mapping[str, Any]) -> None:
        self.events.append((topic, payload))


async def test_temporal_service_refresh_resolve_and_projection() -> None:
    state = _State()
    events = _Events()
    service = TemporalService(clock=_Clock(), id_port=_Ids(), state_port=state, event_port=events)

    snapshot = await service.refresh_turn(
        "s1", turn_id="t1", candidates=("tomorrow", "unclear someday")
    )
    assert snapshot.anchor.timezone == "UTC"
    assert state.payloads["s1"]["anchor"]["anchor_id"] == snapshot.anchor.anchor_id

    resolution = await service.resolve_expression("s1", "next week")
    projection = await service.build_projection("s1", "front")

    assert resolution.needs_clarification is False
    assert projection.anchor.anchor_id == snapshot.anchor.anchor_id
    assert any(topic == "k1.temporal.anchor.created.v1" for topic, _payload in events.events)
    assert any(topic == "k1.temporal.expression.ambiguous.v1" for topic, _payload in events.events)
