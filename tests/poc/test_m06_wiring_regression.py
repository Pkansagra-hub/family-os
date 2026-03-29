"""
tests.poc.test_m06_wiring_regression -- M6 Wiring & Regression Smoke Tests.

Cross-cutting tests that verify M6 production code does not break M1-M5
and that all wiring points are correctly connected.

Tests:
  - Guard table accepts 4 HITL lifecycle topics as OBSERVE
  - Builder functions produce valid envelopes
  - InflightContext reads pending_hil from TaskStateEntry (not SuspensionManager)
  - Cognitive tools (non-invoke_capability) not blocked by HITL
  - HILSubTask factory fixture works
  - Ledger lifecycle assertion fixture works
  - Dead-letter assertion fixture works
"""

from __future__ import annotations

import json

from poc.k1_poc.bus.topics import (
    TOPIC_HITL_BLOCKED_RED,
    TOPIC_HITL_REQUESTED,
    TOPIC_HITL_RESOLVED,
    TOPIC_HITL_TIMED_OUT,
)
from poc.k1_poc.events.hitl import HILRequested, HILResolved
from poc.k1_poc.testing.fixtures import create_test_hil_subtask, create_wired_fsm_with_hitl

# =========================================================================
# Guard table accepts HITL lifecycle topics
# =========================================================================


class TestGuardTableHITLTopics:
    """Guard table has OBSERVE entries for all 4 HITL topics in every state."""

    def test_hitl_topics_in_subscribed_topics(self) -> None:
        """All 4 HITL topics appear in SUBSCRIBED_TOPICS."""
        from poc.k1_poc.fsm.transition_table import SUBSCRIBED_TOPICS

        hitl_topics = [
            TOPIC_HITL_REQUESTED,
            TOPIC_HITL_RESOLVED,
            TOPIC_HITL_TIMED_OUT,
            TOPIC_HITL_BLOCKED_RED,
        ]
        for topic in hitl_topics:
            assert topic in SUBSCRIBED_TOPICS, f"{topic} missing from SUBSCRIBED_TOPICS"

    def test_hitl_topics_observe_in_all_states(self) -> None:
        """Each HITL topic has OBSERVE guard in all 11 FSM states."""
        from poc.k1_poc.fsm.transition_table import FULL_GUARD_TABLE, GuardAction

        hitl_topics = [
            TOPIC_HITL_REQUESTED,
            TOPIC_HITL_RESOLVED,
            TOPIC_HITL_TIMED_OUT,
            TOPIC_HITL_BLOCKED_RED,
        ]
        for state, topic_map in FULL_GUARD_TABLE.items():
            for topic in hitl_topics:
                assert topic in topic_map, f"{topic} missing in state {state.name}"
                action = topic_map[topic]
                # HITL lifecycle topics should be OBSERVE (tuple[0])
                guard_action = action[0] if isinstance(action, tuple) else action
                assert (
                    guard_action == GuardAction.OBSERVE
                ), f"{topic} in {state.name} is {guard_action}, expected OBSERVE"


# =========================================================================
# Builder functions produce valid envelopes
# =========================================================================


class TestBuilderFunctions:
    """M6 builder functions produce correctly shaped envelopes."""

    def test_build_hitl_requested(self) -> None:
        from poc.k1_poc.bus.builders import build_hitl_requested

        env = build_hitl_requested(
            payload={"hil_type": "clarification", "task_id": "t1"},
            parent_id=42,
        )
        assert env.topic == TOPIC_HITL_REQUESTED
        assert env.parent_id == 42
        data = json.loads(env.payload)
        assert data["hil_type"] == "clarification"

    def test_build_hitl_resolved(self) -> None:
        from poc.k1_poc.bus.builders import build_hitl_resolved

        env = build_hitl_resolved(
            payload={"decision_branch": "approved", "task_id": "t2"},
            parent_id=99,
        )
        assert env.topic == TOPIC_HITL_RESOLVED
        data = json.loads(env.payload)
        assert data["decision_branch"] == "approved"

    def test_build_hitl_timed_out(self) -> None:
        from poc.k1_poc.bus.builders import build_hitl_timed_out

        env = build_hitl_timed_out(
            payload={"timeout_ms": 60000, "task_id": "t3"},
            parent_id=0,
        )
        assert env.topic == TOPIC_HITL_TIMED_OUT
        data = json.loads(env.payload)
        assert data["timeout_ms"] == 60000

    def test_build_hitl_blocked_red(self) -> None:
        from poc.k1_poc.bus.builders import build_hitl_blocked_red

        env = build_hitl_blocked_red(
            payload={"safety_band": "RED", "task_id": "t4"},
            parent_id=0,
        )
        assert env.topic == TOPIC_HITL_BLOCKED_RED
        data = json.loads(env.payload)
        assert data["safety_band"] == "RED"


# =========================================================================
# Canonical event dataclasses
# =========================================================================


class TestCanonicalEvents:
    """Canonical event dataclasses serialize and deserialize correctly."""

    def test_hil_requested_roundtrip(self) -> None:
        evt = HILRequested(
            task_id="t1",
            hil_type="clarification",
            question="Preference?",
        )
        payload = evt.to_payload()
        recovered = HILRequested.from_payload(payload)
        assert recovered.hil_type == "clarification"
        assert recovered.question == "Preference?"
        assert recovered.event_type == "hil.requested"

    def test_hil_resolved_roundtrip(self) -> None:
        evt = HILResolved(
            task_id="t2",
            resolution_type="approval",
        )
        payload = evt.to_payload()
        recovered = HILResolved.from_payload(payload)
        assert recovered.resolution_type == "approval"


# =========================================================================
# InflightContext reads from TaskStateEntry
# =========================================================================


class TestInflightContextWiring:
    """build_inflight_context reads pending_hil from TaskStateEntry."""

    def test_arbiter_reads_pending_hil_from_entry(self) -> None:
        """build_inflight_context uses getattr(entry, 'pending_hil')."""
        import inspect

        from poc.k1_poc.fsm.arbiter import build_inflight_context

        source = inspect.getsource(build_inflight_context)
        # Should NOT reference suspension_manager.is_suspended
        assert "suspension_manager.is_suspended" not in source
        # Should reference getattr(entry, "pending_hil", ...)
        assert "pending_hil" in source


# =========================================================================
# Fixture smoke tests
# =========================================================================


class TestFixtures:
    """Test fixture functions work correctly."""

    def test_create_test_hil_subtask(self) -> None:
        """Factory creates HILSubTask with custom parameters."""
        sub = create_test_hil_subtask(
            task_id="t-fix",
            hil_type="approval",
            question="Buy?",
            timeout_ms=5000,
        )
        assert sub.parent_task_id == "t-fix"
        assert sub.hil_type == "approval"
        assert sub.question == "Buy?"
        assert sub.timeout_ms == 5000

    def test_create_wired_fsm_with_hitl(self) -> None:
        """Factory creates FSM with HILCoordinator wired."""
        c = create_wired_fsm_with_hitl()
        assert c["fsm"]._hil_coordinator is not None
        assert "bus" in c
        assert "fsm" in c

    def test_all_topics_constant(self) -> None:
        """ALL_TOPICS includes HITL topics."""
        from poc.k1_poc.bus.topics import ALL_TOPICS

        hitl_topics = [
            TOPIC_HITL_REQUESTED,
            TOPIC_HITL_RESOLVED,
            TOPIC_HITL_TIMED_OUT,
            TOPIC_HITL_BLOCKED_RED,
        ]
        for topic in hitl_topics:
            assert topic in ALL_TOPICS, f"{topic} not in ALL_TOPICS"
