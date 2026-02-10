"""
Tests for Issue 4.5.7 -- Agent creation lifecycle events.

Covers:
  - 3 event dataclasses: AgentCreatedEvent, AgentExpiredEvent,
    MetaOperationBlockedEvent
  - 3 topic constants: TOPIC_AGENT_CREATED, TOPIC_AGENT_EXPIRED,
    TOPIC_META_OP_BLOCKED
  - 3 EventEmitter methods: emit_agent_created, emit_agent_expired,
    emit_meta_blocked
  - EmitterForBuildLike protocol satisfaction
  - Frozen immutability guarantees
  - EMITTED_TOPICS registry completeness
  - events/__init__.py export completeness
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict

import pytest

from k1.fabric.core.agent_builder import EmitterForBuildLike
from k1.fabric.events.event_emitter import EventEmitter
from k1.fabric.events.fabric_events import (
    EMITTED_TOPICS,
    TOPIC_AGENT_CREATED,
    TOPIC_AGENT_EXPIRED,
    TOPIC_META_OP_BLOCKED,
    AgentCreatedEvent,
    AgentExpiredEvent,
    MetaOperationBlockedEvent,
)

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Test adapter -- records emitted events (NO MOCKS)
# ---------------------------------------------------------------------------


class RecordingEventPort:
    """Real event port that records all emitted events."""

    def __init__(self) -> None:
        self.events: list[tuple[str, Dict[str, Any]]] = []

    def emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        self.events.append((event_type, dict(payload)))


# ===================================================================
# Section 1: Topic constants
# ===================================================================


class TestTopicConstants:
    """Verify topic constant values and naming convention."""

    def test_topic_agent_created_value(self) -> None:
        assert TOPIC_AGENT_CREATED == "k1.fabric.agent.created.v1"

    def test_topic_agent_expired_value(self) -> None:
        assert TOPIC_AGENT_EXPIRED == "k1.fabric.agent.expired.v1"

    def test_topic_meta_op_blocked_value(self) -> None:
        assert TOPIC_META_OP_BLOCKED == "k1.fabric.meta.operation.blocked.v1"

    def test_all_three_in_emitted_topics(self) -> None:
        assert TOPIC_AGENT_CREATED in EMITTED_TOPICS
        assert TOPIC_AGENT_EXPIRED in EMITTED_TOPICS
        assert TOPIC_META_OP_BLOCKED in EMITTED_TOPICS


# ===================================================================
# Section 2: AgentCreatedEvent dataclass
# ===================================================================


class TestAgentCreatedEvent:
    """AgentCreatedEvent construction, to_dict, and immutability."""

    def test_construction_defaults(self) -> None:
        e = AgentCreatedEvent(agent_name="test-agent")
        assert e.agent_name == "test-agent"
        assert e.created_by == ""
        assert e.tools_granted == ()
        assert e.domain == ()
        assert e.prompt_template == ""
        assert e.ephemeral is True
        assert e.session_id == ""
        assert e.trace_id == ""
        assert e.timestamp_iso == ""
        assert isinstance(e.timestamp_ms, int)

    def test_construction_full(self) -> None:
        e = AgentCreatedEvent(
            agent_name="research-bot",
            created_by="orchestrator",
            tools_granted=("search", "summarize"),
            domain=("research",),
            prompt_template="You are a research assistant.",
            ephemeral=False,
            session_id="sess-001",
            trace_id="trace-001",
            timestamp_iso="2025-01-01T00:00:00Z",
            timestamp_ms=1000,
        )
        assert e.agent_name == "research-bot"
        assert e.tools_granted == ("search", "summarize")
        assert e.domain == ("research",)
        assert e.ephemeral is False
        assert e.timestamp_ms == 1000

    def test_to_dict(self) -> None:
        e = AgentCreatedEvent(
            agent_name="a",
            created_by="b",
            tools_granted=("t1",),
            domain=("d1", "d2"),
            prompt_template="p",
            ephemeral=True,
            session_id="s",
            trace_id="tr",
            timestamp_iso="iso",
            timestamp_ms=42,
        )
        d = e.to_dict()
        assert d["agent_name"] == "a"
        assert d["tools_granted"] == ["t1"]  # tuple -> list
        assert d["domain"] == ["d1", "d2"]  # tuple -> list
        assert d["timestamp_ms"] == 42

    def test_to_dict_returns_new_dict(self) -> None:
        e = AgentCreatedEvent(agent_name="x")
        d1 = e.to_dict()
        d2 = e.to_dict()
        assert d1 is not d2

    def test_frozen(self) -> None:
        e = AgentCreatedEvent(agent_name="x")
        with pytest.raises(dataclasses.FrozenInstanceError):
            e.agent_name = "y"  # type: ignore[misc]

    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(AgentCreatedEvent)


# ===================================================================
# Section 3: AgentExpiredEvent dataclass
# ===================================================================


class TestAgentExpiredEvent:
    """AgentExpiredEvent construction, to_dict, and immutability."""

    def test_construction_defaults(self) -> None:
        e = AgentExpiredEvent(agent_name="dead-agent")
        assert e.agent_name == "dead-agent"
        assert e.created_at_iso == ""
        assert e.expired_at_iso == ""
        assert e.invocations == 0
        assert e.trace_id == ""
        assert isinstance(e.timestamp_ms, int)

    def test_construction_full(self) -> None:
        e = AgentExpiredEvent(
            agent_name="old-bot",
            created_at_iso="2025-01-01T00:00:00Z",
            expired_at_iso="2025-01-01T01:00:00Z",
            invocations=15,
            trace_id="tr-exp",
            timestamp_ms=9999,
        )
        assert e.invocations == 15
        assert e.timestamp_ms == 9999

    def test_to_dict(self) -> None:
        e = AgentExpiredEvent(
            agent_name="a",
            created_at_iso="c",
            expired_at_iso="x",
            invocations=3,
            trace_id="t",
            timestamp_ms=100,
        )
        d = e.to_dict()
        assert d["agent_name"] == "a"
        assert d["invocations"] == 3
        assert d["timestamp_ms"] == 100

    def test_frozen(self) -> None:
        e = AgentExpiredEvent(agent_name="x")
        with pytest.raises(dataclasses.FrozenInstanceError):
            e.invocations = 5  # type: ignore[misc]

    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(AgentExpiredEvent)


# ===================================================================
# Section 4: MetaOperationBlockedEvent dataclass
# ===================================================================


class TestMetaOperationBlockedEvent:
    """MetaOperationBlockedEvent construction, to_dict, and immutability."""

    def test_construction_defaults(self) -> None:
        e = MetaOperationBlockedEvent()
        assert e.operation == ""
        assert e.violation_type == ""
        assert e.requested_by == ""
        assert e.details == {}
        assert e.trace_id == ""
        assert isinstance(e.timestamp_ms, int)

    def test_construction_full(self) -> None:
        e = MetaOperationBlockedEvent(
            operation="create_agent",
            violation_type="budget_exceeded",
            requested_by="user-007",
            details={"budget": "5", "current": "5"},
            trace_id="tr-blk",
            timestamp_ms=500,
        )
        assert e.operation == "create_agent"
        assert e.details == {"budget": "5", "current": "5"}

    def test_to_dict(self) -> None:
        e = MetaOperationBlockedEvent(
            operation="op",
            violation_type="gate_closed",
            requested_by="r",
            details={"k": "v"},
            trace_id="t",
            timestamp_ms=77,
        )
        d = e.to_dict()
        assert d["operation"] == "op"
        assert d["details"] == {"k": "v"}
        assert d["timestamp_ms"] == 77

    def test_to_dict_details_is_copy(self) -> None:
        original = {"a": "b"}
        e = MetaOperationBlockedEvent(details=original)
        d = e.to_dict()
        assert d["details"] is not original  # defensive copy

    def test_frozen(self) -> None:
        e = MetaOperationBlockedEvent()
        with pytest.raises(dataclasses.FrozenInstanceError):
            e.operation = "x"  # type: ignore[misc]

    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(MetaOperationBlockedEvent)


# ===================================================================
# Section 5: EventEmitter -- emit_agent_created
# ===================================================================


class TestEmitAgentCreated:
    """EventEmitter.emit_agent_created method."""

    def test_emits_correct_topic(self) -> None:
        port = RecordingEventPort()
        emitter = EventEmitter(event_port=port)
        emitter.emit_agent_created(agent_name="a", trace_id="t1")
        assert len(port.events) == 1
        topic, _ = port.events[0]
        assert topic == TOPIC_AGENT_CREATED

    def test_payload_contains_all_fields(self) -> None:
        port = RecordingEventPort()
        emitter = EventEmitter(event_port=port)
        emitter.emit_agent_created(
            agent_name="bot",
            created_by="user",
            tools_granted=["search"],
            domain=["research"],
            prompt_template="tmpl",
            ephemeral=False,
            session_id="sess",
            trace_id="tr",
        )
        _, payload = port.events[0]
        assert payload["agent_name"] == "bot"
        assert payload["created_by"] == "user"
        assert payload["tools_granted"] == ["search"]
        assert payload["domain"] == ["research"]
        assert payload["prompt_template"] == "tmpl"
        assert payload["ephemeral"] is False
        assert payload["session_id"] == "sess"
        assert payload["cognitive_trace_id"] == "tr"  # FAB-09
        assert "timestamp_ms" in payload

    def test_fab09_trace_id_enforced(self) -> None:
        port = RecordingEventPort()
        emitter = EventEmitter(event_port=port)
        emitter.emit_agent_created(agent_name="x", trace_id="fab09-test")
        _, payload = port.events[0]
        assert payload["cognitive_trace_id"] == "fab09-test"

    def test_no_port_silently_drops(self) -> None:
        emitter = EventEmitter(event_port=None)
        # Must not raise
        emitter.emit_agent_created(agent_name="a", trace_id="t")

    def test_tools_granted_none_becomes_empty_list(self) -> None:
        port = RecordingEventPort()
        emitter = EventEmitter(event_port=port)
        emitter.emit_agent_created(agent_name="a", trace_id="t")
        _, payload = port.events[0]
        assert payload["tools_granted"] == []

    def test_domain_none_becomes_empty_list(self) -> None:
        port = RecordingEventPort()
        emitter = EventEmitter(event_port=port)
        emitter.emit_agent_created(agent_name="a", trace_id="t")
        _, payload = port.events[0]
        assert payload["domain"] == []


# ===================================================================
# Section 6: EventEmitter -- emit_agent_expired
# ===================================================================


class TestEmitAgentExpired:
    """EventEmitter.emit_agent_expired method."""

    def test_emits_correct_topic(self) -> None:
        port = RecordingEventPort()
        emitter = EventEmitter(event_port=port)
        emitter.emit_agent_expired(agent_name="old", trace_id="t")
        assert len(port.events) == 1
        topic, _ = port.events[0]
        assert topic == TOPIC_AGENT_EXPIRED

    def test_payload_contains_all_fields(self) -> None:
        port = RecordingEventPort()
        emitter = EventEmitter(event_port=port)
        emitter.emit_agent_expired(
            agent_name="old",
            created_at_iso="2025-01-01T00:00:00Z",
            expired_at_iso="2025-01-01T01:00:00Z",
            invocations=10,
            trace_id="tr-e",
        )
        _, payload = port.events[0]
        assert payload["agent_name"] == "old"
        assert payload["created_at_iso"] == "2025-01-01T00:00:00Z"
        assert payload["expired_at_iso"] == "2025-01-01T01:00:00Z"
        assert payload["invocations"] == 10
        assert payload["cognitive_trace_id"] == "tr-e"
        assert "timestamp_ms" in payload

    def test_no_port_silently_drops(self) -> None:
        emitter = EventEmitter(event_port=None)
        emitter.emit_agent_expired(agent_name="a", trace_id="t")


# ===================================================================
# Section 7: EventEmitter -- emit_meta_blocked
# ===================================================================


class TestEmitMetaBlocked:
    """EventEmitter.emit_meta_blocked method."""

    def test_emits_correct_topic(self) -> None:
        port = RecordingEventPort()
        emitter = EventEmitter(event_port=port)
        emitter.emit_meta_blocked(operation="create", trace_id="t")
        assert len(port.events) == 1
        topic, _ = port.events[0]
        assert topic == TOPIC_META_OP_BLOCKED

    def test_payload_contains_all_fields(self) -> None:
        port = RecordingEventPort()
        emitter = EventEmitter(event_port=port)
        emitter.emit_meta_blocked(
            operation="create_agent",
            violation_type="budget_exceeded",
            requested_by="user-1",
            details={"budget": "5"},
            trace_id="tr-b",
        )
        _, payload = port.events[0]
        assert payload["operation"] == "create_agent"
        assert payload["violation_type"] == "budget_exceeded"
        assert payload["requested_by"] == "user-1"
        assert payload["details"] == {"budget": "5"}
        assert payload["cognitive_trace_id"] == "tr-b"
        assert "timestamp_ms" in payload

    def test_details_none_becomes_empty_dict(self) -> None:
        port = RecordingEventPort()
        emitter = EventEmitter(event_port=port)
        emitter.emit_meta_blocked(operation="x", trace_id="t")
        _, payload = port.events[0]
        assert payload["details"] == {}

    def test_no_port_silently_drops(self) -> None:
        emitter = EventEmitter(event_port=None)
        emitter.emit_meta_blocked(operation="x", trace_id="t")


# ===================================================================
# Section 8: EmitterForBuildLike Protocol satisfaction
# ===================================================================


class TestEmitterForBuildLikeProtocol:
    """EventEmitter satisfies the EmitterForBuildLike Protocol."""

    def test_isinstance_check(self) -> None:
        port = RecordingEventPort()
        emitter = EventEmitter(event_port=port)
        assert isinstance(emitter, EmitterForBuildLike)

    def test_none_port_satisfies_protocol(self) -> None:
        emitter = EventEmitter(event_port=None)
        assert isinstance(emitter, EmitterForBuildLike)


# ===================================================================
# Section 9: events/__init__.py exports
# ===================================================================


class TestEventsExports:
    """Validate events package re-exports all 4.5.7 symbols."""

    def test_topic_constants_exported(self) -> None:
        from k1.fabric.events import TOPIC_AGENT_CREATED as t1
        from k1.fabric.events import TOPIC_AGENT_EXPIRED as t2
        from k1.fabric.events import TOPIC_META_OP_BLOCKED as t3

        assert t1 == "k1.fabric.agent.created.v1"
        assert t2 == "k1.fabric.agent.expired.v1"
        assert t3 == "k1.fabric.meta.operation.blocked.v1"

    def test_event_classes_exported(self) -> None:
        from k1.fabric.events import AgentCreatedEvent as ace
        from k1.fabric.events import AgentExpiredEvent as aee
        from k1.fabric.events import MetaOperationBlockedEvent as mobe

        assert dataclasses.is_dataclass(ace)
        assert dataclasses.is_dataclass(aee)
        assert dataclasses.is_dataclass(mobe)

    def test_all_list_contains_new_symbols(self) -> None:
        import k1.fabric.events as events_pkg

        all_names = set(events_pkg.__all__)
        expected = {
            "TOPIC_AGENT_CREATED",
            "TOPIC_AGENT_EXPIRED",
            "TOPIC_META_OP_BLOCKED",
            "AgentCreatedEvent",
            "AgentExpiredEvent",
            "MetaOperationBlockedEvent",
        }
        assert expected.issubset(all_names)

    def test_all_list_count(self) -> None:
        """__all__ must have exactly 45 entries (was 39, +6 from 4.5.7)."""
        import k1.fabric.events as events_pkg

        assert len(events_pkg.__all__) == 45
        assert expected.issubset(all_names)

    def test_all_list_count(self) -> None:
        """__all__ must have exactly 45 entries (was 39, +6 from 4.5.7)."""
        import k1.fabric.events as events_pkg

        assert len(events_pkg.__all__) == 45
