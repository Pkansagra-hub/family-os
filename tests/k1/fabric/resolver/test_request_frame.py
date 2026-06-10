"""GAP-P1-016 — Tests for BackTaskEnvelope, RequestFrame, RequestFrameBuilder.

Spec: Epic 3.1, 3.2, 3.3, 3.6.
"""

from __future__ import annotations

import json
import uuid

import pytest

from k1.fabric.resolver.back_task_envelope import (
    VALID_SAFETY_BANDS,
    VALID_TIERS,
    BackTaskEnvelope,
    BackTaskEnvelopeError,
    parse_back_task_envelope,
)
from k1.fabric.resolver.request_frame import (
    PersonRef,
    RequestFrame,
    RequestFrameIntent,
    ResourceRef,
    TimeWindowHint,
)
from k1.fabric.resolver.request_frame_builder import (
    RequestFrameBuilder,
    build_frame_from_dict,
)

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

_MINIMAL_PAYLOAD = {
    "task_id": "task-1",
    "trace_id": "trace-1",
    "session_id": "sess-1",
    "actor_id": "actor-a",
    "space_id": "space-1",
    "tier": "MEDIUM",
    "safety_band": "GREEN",
    "task_dispatch": {
        "intents": [
            {
                "intent_id": "intent-1",
                "action": "Add dentist appointment",
                "domain": "family",
                "operation_hint": "create",
                "resource_kind_hint": "calendar_event",
                "subject_hint": "dentist appointment",
                "params": {
                    "person_hint": "Riley",
                    "date": "next Monday",
                },
            },
        ],
        "actor_role": "parent",
    },
}


# ══════════════════════════════════════════════════════════════════════
# TestBackTaskEnvelope
# ══════════════════════════════════════════════════════════════════════


class TestBackTaskEnvelope:
    """parse_back_task_envelope — valid parse, invalid tier, missing fields, budget defaults."""

    def test_parse_valid(self):
        env = parse_back_task_envelope(_MINIMAL_PAYLOAD)
        assert isinstance(env, BackTaskEnvelope)
        assert env.task_id == "task-1"
        assert env.trace_id == "trace-1"
        assert env.tier == "MEDIUM"
        assert env.safety_band == "GREEN"
        assert isinstance(env.envelope_id, str)
        assert len(env.envelope_id) > 0

    def test_reject_invalid_tier(self):
        payload = {**_MINIMAL_PAYLOAD, "tier": "SUPER_LOW"}
        with pytest.raises(BackTaskEnvelopeError, match="tier"):
            parse_back_task_envelope(payload)

    def test_reject_invalid_safety_band(self):
        payload = {**_MINIMAL_PAYLOAD, "safety_band": "BLUE"}
        with pytest.raises(BackTaskEnvelopeError, match="safety_band"):
            parse_back_task_envelope(payload)

    def test_reject_missing_task_id(self):
        payload = {**_MINIMAL_PAYLOAD, "task_id": None}
        with pytest.raises(BackTaskEnvelopeError, match="task_id"):
            parse_back_task_envelope(payload)

    def test_reject_missing_trace_id(self):
        payload = {**_MINIMAL_PAYLOAD, "trace_id": ""}
        with pytest.raises(BackTaskEnvelopeError, match="trace_id"):
            parse_back_task_envelope(payload)

    def test_reject_missing_session_id(self):
        payload = {**_MINIMAL_PAYLOAD, "session_id": None}
        with pytest.raises(BackTaskEnvelopeError, match="session_id"):
            parse_back_task_envelope(payload)

    def test_reject_missing_actor_id(self):
        payload = {**_MINIMAL_PAYLOAD, "actor_id": ""}
        with pytest.raises(BackTaskEnvelopeError, match="actor_id"):
            parse_back_task_envelope(payload)

    def test_reject_non_dict_payload(self):
        with pytest.raises(BackTaskEnvelopeError, match="payload"):
            parse_back_task_envelope("not a dict")

    def test_optional_fields_default(self):
        env = parse_back_task_envelope(_MINIMAL_PAYLOAD)
        assert env.session_state_ref is None
        assert env.grounding_envelope_id is None
        assert env.temporal_anchor_id is None
        assert env.spatial_context_id is None
        assert isinstance(env.submitted_at, str)
        assert len(env.submitted_at) > 0

    def test_optional_fields_present(self):
        payload = {
            **_MINIMAL_PAYLOAD,
            "session_state_ref": "ss-1",
            "grounding_envelope_id": "g-1",
            "temporal_anchor_id": "ta-1",
            "spatial_context_id": "sc-1",
            "submitted_at": "2026-06-05T12:00:00",
        }
        env = parse_back_task_envelope(payload)
        assert env.session_state_ref == "ss-1"
        assert env.grounding_envelope_id == "g-1"
        assert env.temporal_anchor_id == "ta-1"
        assert env.spatial_context_id == "sc-1"
        assert env.submitted_at == "2026-06-05T12:00:00"

    def test_to_dict(self):
        env = parse_back_task_envelope(_MINIMAL_PAYLOAD)
        d = env.to_dict()
        assert d["task_id"] == "task-1"
        assert "budget" not in d  # budget belongs to Back, not Fabric


# ══════════════════════════════════════════════════════════════════════
# TestRequestFrameBuilder
# ══════════════════════════════════════════════════════════════════════


class TestRequestFrameBuilder:
    """builds frame from envelope with explicit hints — NO keyword guessing."""

    def test_builds_frame_from_envelope(self):
        env = parse_back_task_envelope(_MINIMAL_PAYLOAD)
        builder = RequestFrameBuilder()
        frame = builder.build(env)

        assert isinstance(frame, RequestFrame)
        assert frame.request_id.startswith("req-")
        assert frame.task_id == "task-1"
        assert frame.trace_id == "trace-1"
        assert frame.actor_id == "actor-a"
        assert frame.space_id == "space-1"
        assert len(frame.intents) == 1
        assert frame.target_tier == "tier2"
        assert frame.resolution_mode == "execution"

    def test_operation_hint_preserved(self):
        """Builder copies operation_hint from Back — does NOT derive it."""
        env = parse_back_task_envelope(_MINIMAL_PAYLOAD)
        builder = RequestFrameBuilder()
        frame = builder.build(env)
        assert frame.intents[0].operation_hint == "create"

    def test_resource_kind_hint_preserved(self):
        """Builder copies resource_kind_hint from Back — does NOT derive it."""
        env = parse_back_task_envelope(_MINIMAL_PAYLOAD)
        builder = RequestFrameBuilder()
        frame = builder.build(env)
        assert frame.intents[0].resource_kind_hint == "calendar_event"

    def test_handles_missing_operation_hint(self):
        payload = {
            **_MINIMAL_PAYLOAD,
            "task_dispatch": {
                "intents": [
                    {
                        "action": "do something",
                    },
                ],
                "actor_role": "parent",
            },
        }
        env = parse_back_task_envelope(payload)
        builder = RequestFrameBuilder()
        frame = builder.build(env)
        # operation_hint defaults to "" when not provided by Back
        assert frame.intents[0].operation_hint == ""

    def test_handles_multiple_intents(self):
        payload = {
            **_MINIMAL_PAYLOAD,
            "task_dispatch": {
                "intents": [
                    {
                        "intent_id": "i1",
                        "action": "Add event",
                        "operation_hint": "create",
                        "resource_kind_hint": "calendar_event",
                        "params": {"person_hint": "Riley"},
                    },
                    {
                        "intent_id": "i2",
                        "action": "List tasks",
                        "operation_hint": "list",
                        "resource_kind_hint": "task",
                        "params": {"assignee": "Morgan"},
                    },
                ],
            },
        }
        env = parse_back_task_envelope(payload)
        builder = RequestFrameBuilder()
        frame = builder.build(env)
        assert len(frame.intents) == 2
        assert frame.intents[0].operation_hint == "create"
        assert frame.intents[1].operation_hint == "list"
        assert len(frame.person_refs) >= 2  # Riley + Morgan

    def test_resolves_time_window(self):
        payload = {
            **_MINIMAL_PAYLOAD,
            "task_dispatch": {
                "intents": [
                    {
                        "action": "Add event",
                        "operation_hint": "create",
                        "params": {
                            "date": "tomorrow",
                            "time_phrase": "3pm",
                        },
                    },
                ],
            },
        }
        env = parse_back_task_envelope(payload)
        builder = RequestFrameBuilder()
        frame = builder.build(env)
        assert frame.time_window_hint is not None
        assert "tomorrow" in frame.time_window_hint.raw_phrase.lower()
        assert frame.time_window_hint.confidence in ("high", "medium")

    def test_person_refs_extracted(self):
        env = parse_back_task_envelope(_MINIMAL_PAYLOAD)
        builder = RequestFrameBuilder()
        frame = builder.build(env)
        assert len(frame.person_refs) >= 1
        assert frame.person_refs[0].raw == "Riley"

    def test_resource_refs_extracted(self):
        payload = {
            **_MINIMAL_PAYLOAD,
            "task_dispatch": {
                "intents": [
                    {
                        "action": "Add to Riley's calendar",
                        "operation_hint": "create",
                        "resource_kind_hint": "calendar_event",
                        "params": {"calendar_hint": "Riley's calendar"},
                    },
                ],
            },
        }
        env = parse_back_task_envelope(payload)
        builder = RequestFrameBuilder()
        frame = builder.build(env)
        assert len(frame.resource_refs) >= 1

    def test_safety_context_populated(self):
        env = parse_back_task_envelope(_MINIMAL_PAYLOAD)
        builder = RequestFrameBuilder()
        frame = builder.build(env)
        assert frame.safety_context["safety_band"] == "GREEN"
        assert frame.safety_context["actor_role"] == "parent"
        assert frame.safety_context["session_id"] == "sess-1"
        assert "budget" not in frame.safety_context  # budget is Back concern

    def test_empty_intents_produces_empty_frame(self):
        """When Back provides no intents, builder returns empty frame — no manufacturing."""
        payload = {
            **_MINIMAL_PAYLOAD,
            "task_dispatch": {"intents": [], "user_phrase": "do something"},
        }
        env = parse_back_task_envelope(payload)
        builder = RequestFrameBuilder()
        frame = builder.build(env)
        assert len(frame.intents) == 0
        assert frame.safety_context["safety_band"] == "GREEN"

    def test_no_keyword_guessing(self):
        """The builder does NOT use OPERATION_KEYWORDS or RESOURCE_KIND_KEYWORDS.
        Verify that a phrase that would match old keywords is NOT auto-classified."""
        payload = {
            **_MINIMAL_PAYLOAD,
            "task_dispatch": {
                "intents": [
                    {
                        "action": "Add an event to the calendar",
                        # No operation_hint, no resource_kind_hint from Back
                    },
                ],
            },
        }
        env = parse_back_task_envelope(payload)
        builder = RequestFrameBuilder()
        frame = builder.build(env)
        # Without Back providing hints, they should be default (empty/None)
        assert frame.intents[0].operation_hint == ""
        assert frame.intents[0].resource_kind_hint is None


# ══════════════════════════════════════════════════════════════════════
# TestRequestFrameTypes
# ══════════════════════════════════════════════════════════════════════


class TestRequestFrameTypes:
    """All dataclass fields present, frozen=True, serialization roundtrip."""

    def test_all_request_frame_fields(self):
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[],
        )
        assert frame.request_id == "req-1"
        assert frame.target_tier == "tier2"
        assert frame.resolution_mode == "execution"

    def test_request_frame_frozen(self):
        frame = RequestFrame(
            request_id="req-1",
            task_id="task-1",
            trace_id="trace-1",
            actor_id="actor-a",
            space_id="space-1",
            intents=[],
        )
        with pytest.raises(Exception):  # FrozenInstanceError or dataclass error
            frame.request_id = "changed"

    def test_request_frame_intent_frozen(self):
        intent = RequestFrameIntent(
            intent_id="i1",
            action="test",
            operation_hint="create",
        )
        with pytest.raises(Exception):
            intent.operation_hint = "changed"

    def test_person_ref_defaults(self):
        pr = PersonRef(raw="Riley", confidence="high")
        assert pr.needs_resolution is True

    def test_resource_ref_defaults(self):
        rr = ResourceRef(raw="calendar", resource_kind_hint="calendar_event")
        assert rr.confidence == "medium"
        assert rr.needs_resolution is True

    def test_time_window_hint_defaults(self):
        tw = TimeWindowHint(raw_phrase="tomorrow")
        assert tw.resolved_start is None
        assert tw.confidence == "medium"

    def test_build_frame_from_dict(self):
        frame = build_frame_from_dict(
            {
                "intents": [
                    {
                        "intent_id": "i1",
                        "action": "create event",
                        "operation_hint": "create",
                        "resource_kind_hint": "calendar_event",
                    },
                ],
                "person_refs": [{"raw": "Riley", "confidence": "high"}],
            },
            actor_id="actor-a",
            space_id="space-1",
        )
        assert len(frame.intents) == 1
        assert len(frame.person_refs) == 1
        assert frame.actor_id == "actor-a"
        assert frame.space_id == "space-1"

    def test_build_frame_from_dict_no_intents(self):
        frame = build_frame_from_dict({}, actor_id="a", space_id="s")
        assert len(frame.intents) == 0
        assert frame.actor_id == "a"
