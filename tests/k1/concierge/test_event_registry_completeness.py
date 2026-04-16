"""
tests.k1.concierge.test_event_registry_completeness
E-0.5.23 I-0.5.23.2: Registry completeness + round-trip tests.

Validates:
    1. Every CanonicalEventMeta subclass is present in EVENT_TYPE_REGISTRY.
    2. deserialize_event round-trip preserves domain fields for the
       6 newly registered types (Phase1Classified, TaskRouted,
       HITLRequestedEvent, HITLResolvedEvent, HITLTimedOutEvent,
       HITLBlockedRedEvent).
    3. from_payload ↔ to_payload idempotence for new types.
"""

from __future__ import annotations

import pytest

from k1.concierge.events.base import CanonicalEventMeta
from k1.concierge.events.conversation import Phase1Classified, TaskRouted
from k1.concierge.events.hitl import (
    HITLBlockedRedEvent,
    HITLRequestedEvent,
    HITLResolvedEvent,
    HITLTimedOutEvent,
)
from k1.concierge.events.registry import EVENT_TYPE_REGISTRY, deserialize_event

# =========================================================================
# Helpers
# =========================================================================


def _all_subclasses(cls: type) -> set[type]:
    """Recursively collect every concrete subclass of *cls*."""
    result: set[type] = set()
    for sub in cls.__subclasses__():
        result.add(sub)
        result.update(_all_subclasses(sub))
    return result


_CANONICAL_FIELDS = {
    "event_id",
    "event_type",
    "session_id",
    "correlation_id",
    "causation_id",
    "parent_event_id",
    "task_id",
    "actor",
    "ts_utc",
    "priority",
    "payload_schema_version",
}


# =========================================================================
# 1. Completeness: every CanonicalEventMeta subclass is registered
# =========================================================================


class TestRegistryCompleteness:
    """Every concrete subclass of CanonicalEventMeta must appear in the registry."""

    def test_all_subclasses_registered(self) -> None:
        registered_classes = set(EVENT_TYPE_REGISTRY.values())
        all_subclasses = _all_subclasses(CanonicalEventMeta)
        missing = all_subclasses - registered_classes
        assert not missing, (
            f"Unregistered CanonicalEventMeta subclasses: " f"{sorted(c.__name__ for c in missing)}"
        )

    def test_no_duplicate_class_in_registry(self) -> None:
        classes = list(EVENT_TYPE_REGISTRY.values())
        seen: set[type] = set()
        dupes: list[str] = []
        for cls in classes:
            if cls in seen:
                dupes.append(cls.__name__)
            seen.add(cls)
        assert not dupes, f"Duplicate classes in registry: {dupes}"

    def test_all_event_type_keys_are_strings(self) -> None:
        for key in EVENT_TYPE_REGISTRY:
            assert isinstance(key, str), f"Non-string key: {key!r}"
            assert key.strip(), f"Empty/whitespace key: {key!r}"


# =========================================================================
# 2. Round-trip: deserialize_event(evt.to_payload()) preserves all fields
# =========================================================================


class TestPhase1ClassifiedRoundTrip:
    """Phase1Classified domain fields survive serialize → deserialize."""

    @pytest.fixture
    def evt(self) -> Phase1Classified:
        return Phase1Classified(
            session_id="s-1",
            correlation_id="c-1",
            causation_id="cause-1",
            actor="classifier",
            turn_number=5,
            complexity_tier="HIGH",
            intent_primary="book_flight",
            domain_primary="travel",
            safety_band="GREEN",
            emotion_primary="neutral",
            classification_latency_ms=12.5,
            is_degraded=False,
        )

    def test_roundtrip_type(self, evt: Phase1Classified) -> None:
        result = deserialize_event(evt.to_payload())
        assert isinstance(result, Phase1Classified)

    def test_roundtrip_domain_fields(self, evt: Phase1Classified) -> None:
        result = deserialize_event(evt.to_payload())
        assert result is not None
        assert result.turn_number == 5
        assert result.complexity_tier == "HIGH"
        assert result.intent_primary == "book_flight"
        assert result.domain_primary == "travel"
        assert result.safety_band == "GREEN"
        assert result.emotion_primary == "neutral"
        assert result.classification_latency_ms == 12.5
        assert result.is_degraded is False

    def test_roundtrip_canonical_fields(self, evt: Phase1Classified) -> None:
        result = deserialize_event(evt.to_payload())
        assert result is not None
        assert result.session_id == "s-1"
        assert result.correlation_id == "c-1"
        assert result.actor == "classifier"

    def test_double_roundtrip_idempotent(self, evt: Phase1Classified) -> None:
        p1 = evt.to_payload()
        r1 = deserialize_event(p1)
        assert r1 is not None
        p2 = r1.to_payload()
        assert p1 == p2


class TestTaskRoutedRoundTrip:
    """TaskRouted domain fields survive serialize → deserialize."""

    @pytest.fixture
    def evt(self) -> TaskRouted:
        return TaskRouted(
            session_id="s-2",
            correlation_id="c-2",
            causation_id="cause-2",
            actor="router",
            task_id="t-42",
            assigned_tier="MED",
            routing_path="direct",
            budget_limit=100,
        )

    def test_roundtrip_type(self, evt: TaskRouted) -> None:
        result = deserialize_event(evt.to_payload())
        assert isinstance(result, TaskRouted)

    def test_roundtrip_domain_fields(self, evt: TaskRouted) -> None:
        result = deserialize_event(evt.to_payload())
        assert result is not None
        assert result.task_id == "t-42"
        assert result.assigned_tier == "MED"
        assert result.routing_path == "direct"
        assert result.budget_limit == 100

    def test_double_roundtrip_idempotent(self, evt: TaskRouted) -> None:
        p1 = evt.to_payload()
        r1 = deserialize_event(p1)
        assert r1 is not None
        p2 = r1.to_payload()
        assert p1 == p2


class TestHITLRequestedRoundTrip:
    """HITLRequestedEvent domain fields survive serialize → deserialize."""

    @pytest.fixture
    def evt(self) -> HITLRequestedEvent:
        return HITLRequestedEvent(
            session_id="s-3",
            correlation_id="c-3",
            causation_id="cause-3",
            actor="hitl_coordinator",
            pending_hil_id="hil-001",
            hil_type="clarification",
            parent_task_id="t-10",
            safety_band="AMBER",
            hil_deadline_ms=30000,
            resume_token="tok-abc",
            device_id="dev-1",
        )

    def test_roundtrip_type(self, evt: HITLRequestedEvent) -> None:
        result = deserialize_event(evt.to_payload())
        assert isinstance(result, HITLRequestedEvent)

    def test_roundtrip_domain_fields(self, evt: HITLRequestedEvent) -> None:
        result = deserialize_event(evt.to_payload())
        assert result is not None
        assert result.pending_hil_id == "hil-001"
        assert result.hil_type == "clarification"
        assert result.parent_task_id == "t-10"
        assert result.safety_band == "AMBER"
        assert result.hil_deadline_ms == 30000
        assert result.resume_token == "tok-abc"
        assert result.device_id == "dev-1"

    def test_double_roundtrip_idempotent(self, evt: HITLRequestedEvent) -> None:
        p1 = evt.to_payload()
        r1 = deserialize_event(p1)
        assert r1 is not None
        p2 = r1.to_payload()
        assert p1 == p2


class TestHITLResolvedRoundTrip:
    """HITLResolvedEvent domain fields survive serialize → deserialize."""

    @pytest.fixture
    def evt(self) -> HITLResolvedEvent:
        return HITLResolvedEvent(
            session_id="s-4",
            correlation_id="c-4",
            causation_id="cause-4",
            actor="hitl_coordinator",
            pending_hil_id="hil-002",
            hil_type="approval",
            parent_task_id="t-20",
            decision_branch="approved_with_mods",
            has_merged_params=True,
            device_id="dev-2",
        )

    def test_roundtrip_type(self, evt: HITLResolvedEvent) -> None:
        result = deserialize_event(evt.to_payload())
        assert isinstance(result, HITLResolvedEvent)

    def test_roundtrip_domain_fields(self, evt: HITLResolvedEvent) -> None:
        result = deserialize_event(evt.to_payload())
        assert result is not None
        assert result.pending_hil_id == "hil-002"
        assert result.hil_type == "approval"
        assert result.parent_task_id == "t-20"
        assert result.decision_branch == "approved_with_mods"
        assert result.has_merged_params is True
        assert result.device_id == "dev-2"

    def test_double_roundtrip_idempotent(self, evt: HITLResolvedEvent) -> None:
        p1 = evt.to_payload()
        r1 = deserialize_event(p1)
        assert r1 is not None
        p2 = r1.to_payload()
        assert p1 == p2


class TestHITLTimedOutRoundTrip:
    """HITLTimedOutEvent domain fields survive serialize → deserialize."""

    @pytest.fixture
    def evt(self) -> HITLTimedOutEvent:
        return HITLTimedOutEvent(
            session_id="s-5",
            correlation_id="c-5",
            causation_id="cause-5",
            actor="timeout_monitor",
            pending_hil_id="hil-003",
            hil_type="selection",
            parent_task_id="t-30",
            timeout_ms=60000,
            elapsed_ms=60123,
        )

    def test_roundtrip_type(self, evt: HITLTimedOutEvent) -> None:
        result = deserialize_event(evt.to_payload())
        assert isinstance(result, HITLTimedOutEvent)

    def test_roundtrip_domain_fields(self, evt: HITLTimedOutEvent) -> None:
        result = deserialize_event(evt.to_payload())
        assert result is not None
        assert result.pending_hil_id == "hil-003"
        assert result.hil_type == "selection"
        assert result.parent_task_id == "t-30"
        assert result.timeout_ms == 60000
        assert result.elapsed_ms == 60123

    def test_double_roundtrip_idempotent(self, evt: HITLTimedOutEvent) -> None:
        p1 = evt.to_payload()
        r1 = deserialize_event(p1)
        assert r1 is not None
        p2 = r1.to_payload()
        assert p1 == p2


class TestHITLBlockedRedRoundTrip:
    """HITLBlockedRedEvent domain fields survive serialize → deserialize."""

    @pytest.fixture
    def evt(self) -> HITLBlockedRedEvent:
        return HITLBlockedRedEvent(
            session_id="s-6",
            correlation_id="c-6",
            causation_id="cause-6",
            actor="safety_gate",
            capability_name="send_email",
            safety_band="RED",
            reason="red_band_blocked",
        )

    def test_roundtrip_type(self, evt: HITLBlockedRedEvent) -> None:
        result = deserialize_event(evt.to_payload())
        assert isinstance(result, HITLBlockedRedEvent)

    def test_roundtrip_domain_fields(self, evt: HITLBlockedRedEvent) -> None:
        result = deserialize_event(evt.to_payload())
        assert result is not None
        assert result.capability_name == "send_email"
        assert result.safety_band == "RED"
        assert result.reason == "red_band_blocked"

    def test_double_roundtrip_idempotent(self, evt: HITLBlockedRedEvent) -> None:
        p1 = evt.to_payload()
        r1 = deserialize_event(p1)
        assert r1 is not None
        p2 = r1.to_payload()
        assert p1 == p2


# =========================================================================
# 3. Negative: unregistered event_type returns None
# =========================================================================


class TestDeserializeEdgeCases:
    """deserialize_event handles missing/unknown event_type gracefully."""

    def test_unknown_event_type_returns_none(self) -> None:
        result = deserialize_event({"event_type": "no.such.event"})
        assert result is None

    def test_missing_event_type_returns_none(self) -> None:
        result = deserialize_event({"session_id": "s-1"})
        assert result is None

    def test_empty_payload_returns_none(self) -> None:
        result = deserialize_event({})
        assert result is None
