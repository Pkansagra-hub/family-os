"""Tests for ``EventEmitter`` (§E15.0.4)."""

from __future__ import annotations

import pytest

from k1.tools.family.base import BaseEntity, WriteContext
from k1.tools.family.events import EventEmitter
from tests.k1.tools.family._stubs import (
    PingToolService,
    RaisingSsePublisher,
    RaisingSyncOutbox,
    RecordingSsePublisher,
    RecordingSyncOutbox,
)


def _ctx() -> WriteContext:
    return WriteContext(user_id="u1", trace_id="t1", role="parent")


def test_requires_publisher() -> None:
    with pytest.raises(ValueError):
        EventEmitter(None)  # type: ignore[arg-type]


def test_topic_for_uses_canonical_format() -> None:
    defn = PingToolService.DEFINITION
    action = defn.find_action("ping")
    assert EventEmitter.topic_for("ping", action) == "family.ping.ping.compute.v1"  # type: ignore[arg-type]


def test_emit_write_publishes_envelope() -> None:
    pub = RecordingSsePublisher()
    outbox = RecordingSyncOutbox()
    emitter = EventEmitter(pub, outbox)
    defn = PingToolService.DEFINITION
    action = defn.find_action("ping")
    eid = emitter.emit_write(defn, action, {"pong": True}, _ctx())  # type: ignore[arg-type]

    assert eid
    assert len(pub.published) == 1
    topic, env = pub.published[0]
    assert topic == "family.ping.ping.compute.v1"
    assert env["adapter"] == "ping"
    assert env["action"] == "ping"
    assert env["kind"] == "compute"
    assert env["payload"] == {"pong": True}
    assert env["actor"]["user_id"] == "u1"
    assert env["actor"]["role"] == "parent"
    assert env["trace_id"] == "t1"

    # outbox got the same envelope (best-effort).
    assert len(outbox.enqueued) == 1
    assert outbox.enqueued[0]["id"] == eid


def test_emit_write_swallows_publisher_errors() -> None:
    emitter = EventEmitter(RaisingSsePublisher())
    defn = PingToolService.DEFINITION
    action = defn.find_action("ping")
    # Must not raise.
    eid = emitter.emit_write(defn, action, {"pong": True}, _ctx())  # type: ignore[arg-type]
    assert eid


def test_emit_write_swallows_outbox_errors() -> None:
    emitter = EventEmitter(RecordingSsePublisher(), RaisingSyncOutbox())
    defn = PingToolService.DEFINITION
    action = defn.find_action("ping")
    # Must not raise.
    eid = emitter.emit_write(defn, action, {"pong": True}, _ctx())  # type: ignore[arg-type]
    assert eid


def test_emit_entity_write_typed_payload() -> None:
    pub = RecordingSsePublisher()
    emitter = EventEmitter(pub)
    defn = PingToolService.DEFINITION
    action = defn.find_action("ping")
    e = BaseEntity(id="e1", actor="u1")
    eid = emitter.emit_entity_write(defn, action, "create", e, _ctx())  # type: ignore[arg-type]

    assert eid
    _, env = pub.published[0]
    assert env["payload"]["op"] == "create"
    assert env["payload"]["entity"]["id"] == "e1"
