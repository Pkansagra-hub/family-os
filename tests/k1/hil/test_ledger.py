"""Tests for HILLedgerAdapter (E1.M1.6)."""

from __future__ import annotations

from k1.hil.ledger import HILLedgerAdapter
from k1.hil.types import HILEnvelope, HILKind, HILResponseEnvelope


def _env() -> HILEnvelope:
    return HILEnvelope(
        hil_request_id="abc",
        kind=HILKind.CLARIFICATION,
        caller_key="planner:p",
        trace_id="t",
        created_at_ms=1_000,
        timeout_ms=60_000,
        payload={"q": "hi"},
    )


def test_no_writer_is_noop() -> None:
    adapter = HILLedgerAdapter(None)
    env = _env()
    adapter.write_requested(env)
    adapter.write_resolved(
        env,
        HILResponseEnvelope(
            hil_request_id="abc",
            kind=HILKind.CLARIFICATION,
            responded_at_ms=2_000,
            payload={"answer": "y"},
        ),
    )
    adapter.write_timed_out(env)
    adapter.write_blocked(env, "policy")


class _RecordingWriter:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def write_event(self, event_type: str, payload: dict) -> None:
        self.events.append({"event_type": event_type, "payload": payload})


def test_write_requested_uses_write_event() -> None:
    w = _RecordingWriter()
    adapter = HILLedgerAdapter(w)
    adapter.write_requested(_env())
    assert len(w.events) == 1
    assert w.events[0]["event_type"] == "hil.requested"
    assert w.events[0]["payload"]["hil_request_id"] == "abc"
    assert w.events[0]["payload"]["caller_key"] == "planner:p"


def test_round_trip_request_and_resolve() -> None:
    w = _RecordingWriter()
    adapter = HILLedgerAdapter(w)
    env = _env()
    adapter.write_requested(env)
    adapter.write_resolved(
        env,
        HILResponseEnvelope(
            hil_request_id="abc",
            kind=HILKind.CLARIFICATION,
            responded_at_ms=2_500,
            payload={"answer": "y"},
        ),
    )
    assert [e["event_type"] for e in w.events] == ["hil.requested", "hil.resolved"]
    assert w.events[1]["payload"]["duration_ms"] == 1_500


def test_writer_with_append_shape() -> None:
    class _A:
        def __init__(self) -> None:
            self.entries: list[dict] = []

        def append(self, entry: dict) -> None:
            self.entries.append(entry)

    a = _A()
    HILLedgerAdapter(a).write_timed_out(_env())
    assert len(a.entries) == 1
    assert a.entries[0]["event_type"] == "hil.timed_out"


def test_writer_failure_is_swallowed() -> None:
    class _Boom:
        def write_event(self, event_type: str, payload: dict) -> None:
            raise RuntimeError("disk full")

    HILLedgerAdapter(_Boom()).write_requested(_env())  # must not raise


def test_write_blocked_event_shape() -> None:
    w = _RecordingWriter()
    HILLedgerAdapter(w).write_blocked(_env(), "policy_violation")
    assert w.events[0]["event_type"] == "hil.blocked"
    assert w.events[0]["payload"]["reason"] == "policy_violation"
