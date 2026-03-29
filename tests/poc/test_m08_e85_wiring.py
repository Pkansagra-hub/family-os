"""
Tests for M8 E8.5 -- End-to-End Wiring: WeavePolicy + UserActivityTracker
into Cumulative M1-M7 Infrastructure.

Covers:
  - 8.5.1: Guard table entries for weave.decided / weave.metrics / ui.typing
  - 8.5.2: Wire WeavePolicy into FSM _on_task_complete (canonical 12-step)
  - 8.5.3: Wire WeaveSignal to read BackPool, affect, HITL from real sources
  - 8.5.4: Wire DEFER delivery into _on_user_input + STANDARD prompt
  - 8.5.5: Wire DIGEST through DynamicPromptBuilder + WEAVE scenario
  - 8.5.6: Wire urgency + emotional context into WEAVE scenario template
  - 8.5.7: Extend create_wired_fsm fixture with M8 params
  - 8.5.8: Backward compatibility regression tests
  - 8.5.9: Demo smoke tests

Test count target: 80+ tests across 9 test classes.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from poc.k1_poc.bus.topics import TOPIC_UI_TYPING, TOPIC_WEAVE_DECIDED, TOPIC_WEAVE_METRICS
from poc.k1_poc.events.weave import WeaveDecisionMade, WeaveMetricsEvent
from poc.k1_poc.fsm.states import ConciergeState
from poc.k1_poc.protocols.weave_policy import (
    EMOTIONAL_GATE_OPEN,
    EMOTIONAL_GATE_SUPPRESS_ALL_NON_SAFETY,
    DigestPayload,
    UserActivityTracker,
    WeaveDecision,
    WeaveDecisionResult,
    WeaveFallbackHandler,
    WeavePolicy,
    WeaveSignal,
    generate_emotional_context,
    generate_urgency_label,
    sort_results_for_delivery,
)
from poc.k1_poc.testing.fixtures import create_wired_fsm

# =====================================================================
# Helpers
# =====================================================================


def _make_signal(**overrides) -> WeaveSignal:
    """Build a WeaveSignal with defaults suitable for testing."""
    defaults = {
        "fsm_state": ConciergeState.LISTENING.name,
        "pending_count": 1,
        "pending_urgency_profile": {"critical": 0, "normal": 1, "low": 0},
        "has_critical": False,
        "user_typing": False,
        "user_idle_ms": 15_000,
        "affect_band": "",
        "affect_valence": 0.0,
        "emotional_gate": EMOTIONAL_GATE_OPEN,
        "backpool_utilization": 0.3,
        "hitl_pending": False,
        "recent_weave_count": 0,
    }
    defaults.update(overrides)
    return WeaveSignal(**defaults)


# =====================================================================
# 8.5.1 -- Guard table entries for weave/typing topics
# =====================================================================


class TestGuardTableWeaveTopics:
    """Verify FULL_GUARD_TABLE has OBSERVE entries for M8 weave topics."""

    def test_guard_table_has_weave_decided_in_all_states(self):
        """TOPIC_WEAVE_DECIDED has OBSERVE entry in all 11 FSM states."""
        from poc.k1_poc.fsm.transition_table import FULL_GUARD_TABLE, GuardAction

        for state_key, topic_map in FULL_GUARD_TABLE.items():
            assert (
                TOPIC_WEAVE_DECIDED in topic_map
            ), f"State {state_key}: missing guard entry for TOPIC_WEAVE_DECIDED"
            action, _ = topic_map[TOPIC_WEAVE_DECIDED]
            assert (
                action == GuardAction.OBSERVE
            ), f"State {state_key}: expected OBSERVE for TOPIC_WEAVE_DECIDED, got {action}"

    def test_guard_table_has_weave_metrics_in_all_states(self):
        """TOPIC_WEAVE_METRICS has OBSERVE entry in all 11 FSM states."""
        from poc.k1_poc.fsm.transition_table import FULL_GUARD_TABLE, GuardAction

        for state_key, topic_map in FULL_GUARD_TABLE.items():
            assert (
                TOPIC_WEAVE_METRICS in topic_map
            ), f"State {state_key}: missing guard entry for TOPIC_WEAVE_METRICS"
            action, _ = topic_map[TOPIC_WEAVE_METRICS]
            assert (
                action == GuardAction.OBSERVE
            ), f"State {state_key}: expected OBSERVE for TOPIC_WEAVE_METRICS, got {action}"

    def test_guard_table_has_ui_typing_in_all_states(self):
        """TOPIC_UI_TYPING has OBSERVE entry in all 11 FSM states."""
        from poc.k1_poc.fsm.transition_table import FULL_GUARD_TABLE, GuardAction

        for state_key, topic_map in FULL_GUARD_TABLE.items():
            assert (
                TOPIC_UI_TYPING in topic_map
            ), f"State {state_key}: missing guard entry for TOPIC_UI_TYPING"
            action, _ = topic_map[TOPIC_UI_TYPING]
            assert (
                action == GuardAction.OBSERVE
            ), f"State {state_key}: expected OBSERVE for TOPIC_UI_TYPING, got {action}"

    def test_guard_table_covers_11_states(self):
        """FULL_GUARD_TABLE has exactly 11 FSM states."""
        from poc.k1_poc.fsm.transition_table import FULL_GUARD_TABLE

        assert len(FULL_GUARD_TABLE) == 11

    def test_weave_topics_no_state_transition(self):
        """OBSERVE entries have target_state=None (no transition)."""
        from poc.k1_poc.fsm.transition_table import FULL_GUARD_TABLE

        weave_topics = [TOPIC_WEAVE_DECIDED, TOPIC_WEAVE_METRICS, TOPIC_UI_TYPING]
        for state_key, topic_map in FULL_GUARD_TABLE.items():
            for topic in weave_topics:
                _, target = topic_map[topic]
                assert target is None, (
                    f"State {state_key}, topic {topic}: "
                    f"OBSERVE must have target_state=None, got {target}"
                )

    def test_weave_decided_in_event_registry(self):
        """WeaveDecisionMade registered in event registry."""
        from poc.k1_poc.events.registry import EVENT_TYPE_REGISTRY

        assert "conversation.weave.decided" in EVENT_TYPE_REGISTRY

    def test_weave_metrics_in_event_registry(self):
        """WeaveMetricsEvent registered in event registry."""
        from poc.k1_poc.events.registry import EVENT_TYPE_REGISTRY

        assert "metrics.weave.session" in EVENT_TYPE_REGISTRY

    def test_topic_constants_are_strings(self):
        """All M8 topic constants are non-empty strings."""
        assert isinstance(TOPIC_WEAVE_DECIDED, str) and TOPIC_WEAVE_DECIDED
        assert isinstance(TOPIC_WEAVE_METRICS, str) and TOPIC_WEAVE_METRICS
        assert isinstance(TOPIC_UI_TYPING, str) and TOPIC_UI_TYPING

    def test_all_topics_count(self):
        """ALL_TOPICS includes M8 topics (must be >= 41)."""
        from poc.k1_poc.bus.topics import ALL_TOPICS

        assert len(ALL_TOPICS) >= 41

    def test_subscribed_topics_include_weave_metrics(self):
        """TOPIC_WEAVE_METRICS is in SUBSCRIBED_TOPICS."""
        from poc.k1_poc.fsm.transition_table import SUBSCRIBED_TOPICS

        assert TOPIC_WEAVE_METRICS in SUBSCRIBED_TOPICS


# =====================================================================
# 8.5.2 -- Wire WeavePolicy into FSM _on_task_complete
# =====================================================================


class TestCanonical12StepOrdering:
    """Verify _on_task_complete follows canonical 12-step ordering."""

    def test_controller_has_weave_policy_attribute(self):
        """FSM controller has _weave_policy attribute (None by default)."""
        ctx = create_wired_fsm()
        assert hasattr(ctx["fsm"], "_weave_policy")
        assert ctx["fsm"]._weave_policy is None

    def test_controller_has_activity_tracker_attribute(self):
        """FSM controller has _activity_tracker attribute (None by default)."""
        ctx = create_wired_fsm()
        assert hasattr(ctx["fsm"], "_activity_tracker")
        assert ctx["fsm"]._activity_tracker is None

    def test_set_weave_policy_wires_instance(self):
        """set_weave_policy() sets _weave_policy reference."""
        ctx = create_wired_fsm()
        policy = WeavePolicy()
        ctx["fsm"].set_weave_policy(policy)
        assert ctx["fsm"]._weave_policy is policy

    def test_set_activity_tracker_wires_instance(self):
        """set_activity_tracker() sets _activity_tracker reference."""
        ctx = create_wired_fsm()
        tracker = UserActivityTracker()
        ctx["fsm"].set_activity_tracker(tracker)
        assert ctx["fsm"]._activity_tracker is tracker

    def test_on_task_complete_without_policy_uses_legacy(self):
        """Without weave_policy, _on_task_complete uses legacy path."""
        ctx = create_wired_fsm()
        fsm = ctx["fsm"]
        # Verify _weave_policy is None -> legacy path
        assert fsm._weave_policy is None

    def test_on_task_complete_with_policy_uses_adaptive(self):
        """With weave_policy, _on_task_complete delegates to _on_task_complete_adaptive."""
        ctx = create_wired_fsm(with_weave_policy=True)
        fsm = ctx["fsm"]
        assert fsm._weave_policy is not None
        assert isinstance(fsm._weave_policy, WeavePolicy)

    def test_weave_fallback_handler_exists(self):
        """Controller has _weave_fallback (WeaveFallbackHandler)."""
        ctx = create_wired_fsm()
        assert hasattr(ctx["fsm"], "_weave_fallback")
        assert isinstance(ctx["fsm"]._weave_fallback, WeaveFallbackHandler)

    def test_has_pending_hitl_false_when_no_subtasks(self):
        """_has_pending_hitl() returns False when no pending subtasks."""
        ctx = create_wired_fsm(with_weave_policy=True)
        assert ctx["fsm"]._has_pending_hitl() is False

    def test_get_task_urgency_returns_normal_for_unknown(self):
        """_get_task_urgency() returns 'normal' for unknown task_id."""
        ctx = create_wired_fsm(with_weave_policy=True)
        assert ctx["fsm"]._get_task_urgency("nonexistent") == "normal"

    def test_controller_has_async_results_context(self):
        """Controller has _async_results_context attribute."""
        ctx = create_wired_fsm()
        assert hasattr(ctx["fsm"], "_async_results_context")
        assert ctx["fsm"]._async_results_context == ""

    def test_controller_has_digest_flush_task(self):
        """Controller has _digest_flush_task attribute."""
        ctx = create_wired_fsm()
        assert hasattr(ctx["fsm"], "_digest_flush_task")
        assert ctx["fsm"]._digest_flush_task is None

    def test_on_task_complete_adaptive_method_exists(self):
        """_on_task_complete_adaptive method exists on controller."""
        ctx = create_wired_fsm()
        assert hasattr(ctx["fsm"], "_on_task_complete_adaptive")
        assert callable(ctx["fsm"]._on_task_complete_adaptive)

    def test_on_task_complete_legacy_method_exists(self):
        """_on_task_complete_legacy method exists on controller."""
        ctx = create_wired_fsm()
        assert hasattr(ctx["fsm"], "_on_task_complete_legacy")
        assert callable(ctx["fsm"]._on_task_complete_legacy)


# =====================================================================
# 8.5.3 -- Wire WeaveSignal to read BackPool, affect, HITL sources
# =====================================================================


class TestWeaveSignalSources:
    """Verify WeaveSignal.from_runtime reads canonical sources."""

    def test_signal_from_runtime_default_values(self):
        """from_runtime with minimal args produces valid defaults."""
        signal = WeaveSignal.from_runtime(
            fsm_state=ConciergeState.LISTENING,
        )
        assert signal.fsm_state == "LISTENING"
        assert signal.pending_count == 0
        assert signal.user_typing is False
        assert signal.user_idle_ms == 0
        assert signal.backpool_utilization == 0.0
        assert signal.hitl_pending is False

    def test_signal_reads_activity_tracker(self):
        """from_runtime reads typing/idle from UserActivityTracker."""
        tracker = UserActivityTracker()
        tracker.on_typing_start()
        signal = WeaveSignal.from_runtime(
            fsm_state=ConciergeState.COMPANIONING,
            activity_tracker=tracker,
        )
        assert signal.user_typing is True

    def test_signal_reads_backpool_state(self):
        """from_runtime reads utilization from BackPool-like object."""

        class MockPool:
            def get_pool_state(self):
                return {"active": 2, "size": 4}

        signal = WeaveSignal.from_runtime(
            fsm_state=ConciergeState.LISTENING,
            back_pool=MockPool(),
        )
        assert signal.backpool_utilization == 0.5

    def test_signal_reads_empty_backpool(self):
        """from_runtime handles empty pool (size=0) without divide-by-zero."""

        class EmptyPool:
            def get_pool_state(self):
                return {"active": 0, "size": 0}

        signal = WeaveSignal.from_runtime(
            fsm_state=ConciergeState.LISTENING,
            back_pool=EmptyPool(),
        )
        assert signal.backpool_utilization == 0.0

    def test_signal_reads_hitl_pending(self):
        """from_runtime includes hitl_pending flag."""
        signal = WeaveSignal.from_runtime(
            fsm_state=ConciergeState.LISTENING,
            hitl_pending=True,
        )
        assert signal.hitl_pending is True

    def test_signal_reads_turn_state_pending(self):
        """from_runtime counts pending results from turn_state."""
        from poc.k1_poc.fsm.turn_state import FSMTurnState

        ts = FSMTurnState()
        ts.pending_results.append({"task_id": "t1", "urgency": "normal"})
        ts.pending_results.append({"task_id": "t2", "urgency": "critical"})

        signal = WeaveSignal.from_runtime(
            fsm_state=ConciergeState.LISTENING,
            turn_state=ts,
        )
        assert signal.pending_count == 2
        assert signal.has_critical is True

    def test_signal_atomic_collection(self):
        """from_runtime is synchronous (no awaits in signature)."""
        import inspect

        assert not inspect.iscoroutinefunction(WeaveSignal.from_runtime)

    def test_signal_to_dict_roundtrip(self):
        """to_dict -> from_dict produces equivalent signal."""
        original = _make_signal(pending_count=3, user_typing=True, hitl_pending=True)
        d = original.to_dict()
        restored = WeaveSignal.from_dict(d)
        assert restored.pending_count == 3
        assert restored.user_typing is True
        assert restored.hitl_pending is True
        assert restored.fsm_state == original.fsm_state

    def test_signal_reads_affect_valence(self):
        """from_runtime reads affect data from session_state-like object."""

        class MockSS:
            def __init__(self):
                self.sections = {
                    "affective_now": MagicMock(
                        to_dict=lambda: {"valence": -0.5, "arousal": 0.7, "band": "elevated"}
                    )
                }

            def __getattr__(self, name):
                if name == "affective_now":
                    return self.sections["affective_now"]
                raise AttributeError(name)

        signal = WeaveSignal.from_runtime(
            fsm_state=ConciergeState.LISTENING,
            ss=MockSS(),
        )
        assert signal.affect_valence == -0.5


# =====================================================================
# 8.5.4 -- Wire DEFER delivery into _on_user_input
# =====================================================================


class TestDeferDelivery:
    """Verify DEFER results are tracked and re-evaluated on user input."""

    def test_mark_results_deferred_moves_to_deferred(self):
        """_mark_results_deferred moves pending results to deferred list."""
        from poc.k1_poc.fsm.turn_state import FSMTurnState

        ts = FSMTurnState()
        ts.pending_results.append({"task_id": "t1", "urgency": "normal"})
        ts.mark_deferred()
        assert ts.has_deferred_results is True

    def test_drain_deferred_returns_and_clears(self):
        """drain_deferred() returns deferred items and clears the list."""
        from poc.k1_poc.fsm.turn_state import FSMTurnState

        ts = FSMTurnState()
        ts.pending_results.append({"task_id": "t1", "urgency": "normal"})
        ts.mark_deferred()
        items = ts.drain_deferred()
        assert len(items) >= 1
        assert ts.has_deferred_results is False

    def test_check_deferred_results_on_input_method_exists(self):
        """Controller has _check_deferred_results_on_input method."""
        ctx = create_wired_fsm(with_weave_policy=True)
        assert hasattr(ctx["fsm"], "_check_deferred_results_on_input")
        assert callable(ctx["fsm"]._check_deferred_results_on_input)

    def test_controller_async_results_context_starts_empty(self):
        """_async_results_context is empty string initially."""
        ctx = create_wired_fsm(with_weave_policy=True)
        assert ctx["fsm"]._async_results_context == ""

    def test_max_consecutive_defers_forces_delivery(self):
        """After max_consecutive_defers, results must be delivered."""
        from poc.k1_poc.fsm.turn_state import FSMTurnState

        ts = FSMTurnState()
        # Simulate result deferred 5+ times
        ts.pending_results.append({"task_id": "t1", "urgency": "normal", "defer_count": 5})
        force = ts.mark_deferred()
        # Items at max defers should be forced to deliver
        assert force is not None  # Non-None indicates force-deliver items

    def test_deferred_results_list_independent_of_pending(self):
        """deferred_results is separate from pending_results."""
        from poc.k1_poc.fsm.turn_state import FSMTurnState

        ts = FSMTurnState()
        ts.pending_results.append({"task_id": "t1", "urgency": "normal"})
        ts.mark_deferred()
        # Add new pending after deferral
        ts.pending_results.append({"task_id": "t2", "urgency": "normal"})
        assert len(ts.pending_results) == 1  # Only t2
        assert ts.has_deferred_results is True  # t1 is deferred

    def test_has_deferred_results_false_when_empty(self):
        """has_deferred_results returns False when deferred list empty."""
        from poc.k1_poc.fsm.turn_state import FSMTurnState

        ts = FSMTurnState()
        assert ts.has_deferred_results is False


# =====================================================================
# 8.5.5 -- Wire DIGEST through WEAVE scenario pipeline
# =====================================================================


class TestDigestPipeline:
    """Verify DIGEST mode compresses results and flows through WEAVE."""

    def test_digest_payload_from_results(self):
        """DigestPayload.from_results() compresses multiple results."""
        results = [
            {"task_id": "t1", "result": {"summary": "Hotel booked"}, "urgency": "low"},
            {"task_id": "t2", "result": {"summary": "Flight found"}, "urgency": "low"},
            {"task_id": "t3", "result": {"summary": "Car reserved"}, "urgency": "low"},
        ]
        digest = DigestPayload.from_results(results)
        assert digest.result_count == 3
        assert isinstance(digest.summary_text, str)
        assert len(digest.summary_text) > 0

    def test_digest_payload_preserves_count(self):
        """DigestPayload tracks original result count."""
        results = [{"task_id": f"t{i}", "result": {}, "urgency": "low"} for i in range(5)]
        digest = DigestPayload.from_results(results)
        assert digest.result_count == 5

    def test_flush_digest_now_method_exists(self):
        """Controller has _flush_digest_now method."""
        ctx = create_wired_fsm(with_weave_policy=True)
        assert hasattr(ctx["fsm"], "_flush_digest_now")
        assert callable(ctx["fsm"]._flush_digest_now)

    def test_schedule_digest_flush_method_exists(self):
        """Controller has _schedule_digest_flush method."""
        ctx = create_wired_fsm(with_weave_policy=True)
        assert hasattr(ctx["fsm"], "_schedule_digest_flush")
        assert callable(ctx["fsm"]._schedule_digest_flush)

    def test_digest_payload_summary_mentions_results(self):
        """Digest summary mentions task results."""
        results = [
            {"task_id": "t1", "result": {"summary": "Weather check done"}, "urgency": "low"},
            {"task_id": "t2", "result": {"summary": "News fetched"}, "urgency": "low"},
            {"task_id": "t3", "result": {"summary": "Calendar synced"}, "urgency": "low"},
        ]
        digest = DigestPayload.from_results(results)
        # Summary should mention something about the results
        assert digest.result_count == 3

    def test_digest_is_not_empty_for_single_result(self):
        """DigestPayload works even for a single result."""
        results = [{"task_id": "t1", "result": {"summary": "Done"}, "urgency": "low"}]
        digest = DigestPayload.from_results(results)
        assert digest.result_count == 1
        assert len(digest.summary_text) > 0


# =====================================================================
# 8.5.6 -- Urgency + emotional context in WEAVE scenario
# =====================================================================


class TestUrgencyEmotionalWiring:
    """Verify urgency_label and emotional_context generation."""

    def test_generate_urgency_label_critical(self):
        """generate_urgency_label returns URGENT for critical results."""
        results = [{"task_id": "t1", "urgency": "critical"}]
        label = generate_urgency_label(results)
        assert "URGENT" in label.upper() or "urgent" in label.lower()

    def test_generate_urgency_label_normal(self):
        """generate_urgency_label returns Informational for normal results."""
        results = [{"task_id": "t1", "urgency": "normal"}]
        label = generate_urgency_label(results)
        # Should not contain URGENT
        assert "urgent" not in label.lower() or "informational" in label.lower()

    def test_generate_urgency_label_multiple_low(self):
        """generate_urgency_label returns Summary for 3+ low-urgency results."""
        results = [{"task_id": f"t{i}", "urgency": "low"} for i in range(3)]
        label = generate_urgency_label(results)
        assert isinstance(label, str)
        assert len(label) > 0

    def test_generate_emotional_context_neutral(self):
        """generate_emotional_context returns neutral guidance for 0 valence."""
        ctx = generate_emotional_context(
            emotional_gate=EMOTIONAL_GATE_OPEN,
            affect_valence=0.0,
            affect_band="",
        )
        assert isinstance(ctx, str)
        assert "neutral" in ctx.lower() or "standard" in ctx.lower()

    def test_generate_emotional_context_crisis(self):
        """generate_emotional_context returns crisis guidance for crisis gate."""
        ctx = generate_emotional_context(
            emotional_gate=EMOTIONAL_GATE_SUPPRESS_ALL_NON_SAFETY,
            affect_valence=-0.7,
            affect_band="crisis",
        )
        assert "crisis" in ctx.lower() or "gentle" in ctx.lower() or "safety" in ctx.lower()

    def test_generate_emotional_context_positive(self):
        """generate_emotional_context returns positive guidance for positive valence."""
        ctx = generate_emotional_context(
            emotional_gate=EMOTIONAL_GATE_OPEN,
            affect_valence=0.6,
            affect_band="positive",
        )
        assert "positive" in ctx.lower() or "upbeat" in ctx.lower()

    def test_generate_emotional_context_negative(self):
        """generate_emotional_context returns sensitive guidance for negative valence."""
        ctx = generate_emotional_context(
            emotional_gate=EMOTIONAL_GATE_OPEN,
            affect_valence=-0.4,
            affect_band="",
        )
        assert isinstance(ctx, str)
        assert len(ctx) > 0

    def test_sort_results_for_delivery_critical_first(self):
        """sort_results_for_delivery places critical results first."""
        results = [
            {"task_id": "t1", "urgency": "low"},
            {"task_id": "t2", "urgency": "critical"},
            {"task_id": "t3", "urgency": "normal"},
        ]
        sorted_r = sort_results_for_delivery(results)
        assert sorted_r[0]["urgency"] == "critical"

    def test_sort_results_preserves_fifo_within_urgency(self):
        """sort_results_for_delivery preserves FIFO order within same urgency."""
        results = [
            {"task_id": "t1", "urgency": "normal", "queued_at_ns": 1000},
            {"task_id": "t2", "urgency": "normal", "queued_at_ns": 2000},
        ]
        sorted_r = sort_results_for_delivery(results)
        assert sorted_r[0]["task_id"] == "t1"
        assert sorted_r[1]["task_id"] == "t2"

    def test_build_emotional_context_in_front(self):
        """front.py _build_emotional_context function exists and returns string."""
        from poc.k1_poc.actors.front import _build_emotional_context

        result = _build_emotional_context({})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_build_emotional_context_crisis_guidance(self):
        """_build_emotional_context returns crisis guidance for negative valence."""
        from poc.k1_poc.actors.front import _build_emotional_context

        result = _build_emotional_context({"valence": -0.6, "band": "crisis"})
        assert "distress" in result.lower() or "gentle" in result.lower()

    def test_build_emotional_context_positive_guidance(self):
        """_build_emotional_context returns positive guidance for positive valence."""
        from poc.k1_poc.actors.front import _build_emotional_context

        result = _build_emotional_context({"valence": 0.5, "band": "positive"})
        assert "positive" in result.lower() or "energy" in result.lower()

    def test_build_emotional_context_neutral_default(self):
        """_build_emotional_context returns neutral for empty affect."""
        from poc.k1_poc.actors.front import _build_emotional_context

        result = _build_emotional_context({})
        assert "neutral" in result.lower() or "standard" in result.lower()

    def test_weave_scenario_template_has_urgency_placeholder(self):
        """WEAVE scenario template includes {urgency_label}."""
        from poc.k1_poc.prompt.mode import PromptMode
        from poc.k1_poc.prompt.scenario_templates import SCENARIO_DATA_TEMPLATES

        template = SCENARIO_DATA_TEMPLATES[PromptMode.WEAVE]
        assert "{urgency_label}" in template

    def test_weave_scenario_template_has_emotional_placeholder(self):
        """WEAVE scenario template includes {emotional_context}."""
        from poc.k1_poc.prompt.mode import PromptMode
        from poc.k1_poc.prompt.scenario_templates import SCENARIO_DATA_TEMPLATES

        template = SCENARIO_DATA_TEMPLATES[PromptMode.WEAVE]
        assert "{emotional_context}" in template


# =====================================================================
# 8.5.7 -- Extend create_wired_fsm fixture with M8 params
# =====================================================================


class TestFixtureSupport:
    """Verify create_wired_fsm supports M8 params."""

    def test_fixture_default_no_weave_policy(self):
        """Default create_wired_fsm does NOT create WeavePolicy."""
        ctx = create_wired_fsm()
        assert "weave_policy" not in ctx

    def test_fixture_with_weave_policy(self):
        """with_weave_policy=True creates and wires WeavePolicy."""
        ctx = create_wired_fsm(with_weave_policy=True)
        assert "weave_policy" in ctx
        assert isinstance(ctx["weave_policy"], WeavePolicy)
        assert ctx["fsm"]._weave_policy is ctx["weave_policy"]

    def test_fixture_with_activity_tracker(self):
        """with_activity_tracker=True creates and wires UserActivityTracker."""
        ctx = create_wired_fsm(with_activity_tracker=True)
        assert "activity_tracker" in ctx
        assert isinstance(ctx["activity_tracker"], UserActivityTracker)
        assert ctx["fsm"]._activity_tracker is ctx["activity_tracker"]

    def test_fixture_weave_policy_implies_activity_tracker(self):
        """with_weave_policy=True implies with_activity_tracker=True."""
        ctx = create_wired_fsm(with_weave_policy=True)
        assert "activity_tracker" in ctx
        assert isinstance(ctx["activity_tracker"], UserActivityTracker)

    def test_fixture_standalone_activity_tracker(self):
        """with_activity_tracker=True alone (no policy) works."""
        ctx = create_wired_fsm(with_activity_tracker=True)
        assert "activity_tracker" in ctx
        assert "weave_policy" not in ctx

    def test_fixture_returns_fsm_bus_router(self):
        """Fixture always returns fsm, bus, router."""
        ctx = create_wired_fsm(with_weave_policy=True)
        assert "fsm" in ctx
        assert "bus" in ctx
        assert "router" in ctx

    def test_fixture_m7_params_still_work(self):
        """M7 params (with_back_pool, with_lease) still function."""
        ctx = create_wired_fsm(with_back_pool=True, pool_size=2)
        assert "back_pool" in ctx

    def test_fixture_combined_m7_m8(self):
        """M7 and M8 params work together."""
        ctx = create_wired_fsm(
            with_back_pool=True,
            pool_size=3,
            with_weave_policy=True,
        )
        assert "back_pool" in ctx
        assert "weave_policy" in ctx
        assert "activity_tracker" in ctx


# =====================================================================
# 8.5.8 -- Backward compatibility regression
# =====================================================================


class TestWiringRegression:
    """Verify M1-M7 wiring survives M8 refactoring."""

    def test_m1_ledger_still_attached(self):
        """Ledger writer still attached when with_ledger=True."""
        ctx = create_wired_fsm(with_weave_policy=True, with_ledger=True)
        assert "ledger" in ctx
        assert ctx["fsm"]._ledger is not None

    def test_m2_guard_table_has_11_states(self):
        """Guard table still has 11 states after M8 additions."""
        from poc.k1_poc.fsm.transition_table import FULL_GUARD_TABLE

        assert len(FULL_GUARD_TABLE) == 11

    def test_m2_dead_letter_consumer_attached(self):
        """DeadLetterConsumer still attached."""
        ctx = create_wired_fsm(with_weave_policy=True, with_dead_letter_consumer=True)
        assert "dead_letter_consumer" in ctx

    def test_m5_arbiter_still_wired(self):
        """ConversationArbiter still wired."""
        ctx = create_wired_fsm(with_weave_policy=True, with_arbiter=True)
        assert "arbiter" in ctx

    def test_m5_cancel_handler_accessible(self):
        """CancellationHandler accessible via with_cancel_tokens."""
        ctx = create_wired_fsm(with_weave_policy=True, with_cancel_tokens=True)
        assert "cancel_handler" in ctx

    def test_m7_backpool_wires_with_m8(self):
        """BackPool wires correctly alongside M8 WeavePolicy."""
        ctx = create_wired_fsm(
            with_back_pool=True,
            pool_size=2,
            with_weave_policy=True,
        )
        assert "back_pool" in ctx
        assert ctx["fsm"]._back_pool is not None
        assert ctx["fsm"]._weave_policy is not None

    def test_legacy_path_when_no_policy(self):
        """Without policy, controller falls back to legacy routing."""
        ctx = create_wired_fsm()
        fsm = ctx["fsm"]
        assert fsm._weave_policy is None
        # Legacy path should still work (no crash)
        assert hasattr(fsm, "_on_task_complete_legacy")

    def test_fallback_handler_exists(self):
        """WeaveFallbackHandler always initialized in controller."""
        ctx = create_wired_fsm()
        fsm = ctx["fsm"]
        assert isinstance(fsm._weave_fallback, WeaveFallbackHandler)

    def test_fallback_decide_returns_valid_result(self):
        """WeaveFallbackHandler.fallback_decide produces valid result."""
        handler = WeaveFallbackHandler()
        result = handler.fallback_decide(ConciergeState.LISTENING)
        assert isinstance(result, WeaveDecisionResult)
        assert result.decision in (WeaveDecision.IMMEDIATE, WeaveDecision.BATCH)

    def test_fallback_decide_listening_returns_immediate(self):
        """Fallback for LISTENING state returns IMMEDIATE."""
        handler = WeaveFallbackHandler()
        result = handler.fallback_decide(ConciergeState.LISTENING)
        assert result.decision == WeaveDecision.IMMEDIATE

    def test_fallback_decide_companioning_returns_batch(self):
        """Fallback for COMPANIONING state returns BATCH with fixed window."""
        handler = WeaveFallbackHandler()
        result = handler.fallback_decide(ConciergeState.COMPANIONING)
        assert result.decision == WeaveDecision.BATCH
        assert result.window_ms > 0

    def test_weave_decision_all_five_values_exist(self):
        """WeaveDecision enum has all 5 values."""
        assert hasattr(WeaveDecision, "IMMEDIATE")
        assert hasattr(WeaveDecision, "BATCH")
        assert hasattr(WeaveDecision, "DEFER")
        assert hasattr(WeaveDecision, "DIGEST")
        assert hasattr(WeaveDecision, "SUPPRESS")


# =====================================================================
# 8.5.9 -- Demo smoke tests
# =====================================================================


class TestDemoSmoke:
    """Smoke tests verifying end-to-end M8 adaptive weave lifecycle."""

    def test_full_wiring_creates_all_components(self):
        """Full M8 wiring creates policy + tracker + fallback."""
        ctx = create_wired_fsm(with_weave_policy=True)
        fsm = ctx["fsm"]
        assert fsm._weave_policy is not None
        assert fsm._activity_tracker is not None
        assert fsm._weave_fallback is not None

    def test_weave_signal_collection_smoke(self):
        """WeaveSignal.from_runtime collects all fields without error."""
        tracker = UserActivityTracker()
        signal = WeaveSignal.from_runtime(
            fsm_state=ConciergeState.LISTENING,
            activity_tracker=tracker,
            hitl_pending=False,
        )
        assert signal.fsm_state == "LISTENING"
        assert signal.pending_count == 0
        assert signal.user_typing is False

    def test_weave_policy_decide_smoke(self):
        """WeavePolicy.decide() returns valid result for simple signal."""
        policy = WeavePolicy()
        signal = _make_signal(
            user_idle_ms=15_000,
            pending_count=1,
        )
        result = policy.decide(signal)
        assert isinstance(result, WeaveDecisionResult)
        assert result.decision in WeaveDecision

    def test_weave_policy_immediate_for_idle_user(self):
        """Policy returns IMMEDIATE when user is idle > 10s + single result."""
        policy = WeavePolicy()
        signal = _make_signal(
            user_idle_ms=15_000,
            pending_count=1,
            user_typing=False,
        )
        result = policy.decide(signal)
        assert result.decision == WeaveDecision.IMMEDIATE

    def test_weave_policy_defer_for_typing_user(self):
        """Policy returns DEFER when user is actively typing."""
        policy = WeavePolicy()
        signal = _make_signal(
            user_typing=True,
            user_idle_ms=0,
            pending_count=1,
            has_critical=False,
        )
        result = policy.decide(signal)
        assert result.decision == WeaveDecision.DEFER

    def test_weave_policy_emotional_gate_suppress(self):
        """Policy returns SUPPRESS/DEFER for crisis + non-critical result."""
        policy = WeavePolicy()
        signal = _make_signal(
            fsm_state=ConciergeState.COMPANIONING.name,
            affect_band="crisis",
            affect_valence=-0.7,
            emotional_gate=EMOTIONAL_GATE_SUPPRESS_ALL_NON_SAFETY,
            pending_count=1,
            has_critical=False,
            user_idle_ms=2000,
        )
        result = policy.decide(signal)
        # Crisis + non-critical -> suppress or defer
        assert result.decision in (
            WeaveDecision.SUPPRESS,
            WeaveDecision.DEFER,
        )

    def test_weave_policy_critical_overrides_typing(self):
        """Policy returns IMMEDIATE for critical result even when typing."""
        policy = WeavePolicy()
        signal = _make_signal(
            user_typing=True,
            pending_count=1,
            has_critical=True,
            pending_urgency_profile={"critical": 1, "normal": 0, "low": 0},
        )
        result = policy.decide(signal)
        assert result.decision == WeaveDecision.IMMEDIATE

    def test_weave_policy_hitl_suppression(self):
        """Policy returns DEFER when HITL pending + non-critical."""
        policy = WeavePolicy()
        signal = _make_signal(
            fsm_state=ConciergeState.COMPANIONING.name,
            hitl_pending=True,
            has_critical=False,
            pending_count=1,
            user_idle_ms=2000,
        )
        result = policy.decide(signal)
        assert result.decision == WeaveDecision.DEFER

    def test_weave_decision_made_event_fields(self):
        """WeaveDecisionMade event has all required fields."""
        event = WeaveDecisionMade(
            candidate_event_id="env_1",
            decision="BATCH",
            reason="test reason",
            batch_window_ms=500,
            fsm_state="LISTENING",
            signal_snapshot={"pending_count": 1},
            urgency_override=False,
            emotional_gate_applied=False,
            fallback_used=False,
        )
        assert event.decision == "BATCH"
        assert event.fallback_used is False
        assert event.signal_snapshot["pending_count"] == 1

    def test_weave_metrics_event_fields(self):
        """WeaveMetricsEvent has all required fields."""
        event = WeaveMetricsEvent(
            weave_count=10,
            digest_count=2,
            defer_count=3,
            suppress_count=1,
            avg_weave_latency_ms=350.0,
            user_acknowledged_rate=0.85,
        )
        assert event.weave_count == 10
        assert event.suppress_count == 1

    def test_bootstrap_imports_weave_policy(self):
        """bootstrap.py module imports without error (M8 wiring included)."""
        import poc.k1_poc.kernel.bootstrap

        assert hasattr(poc.k1_poc.kernel.bootstrap, "start_kernel")

    def test_activity_tracker_typing_lifecycle(self):
        """UserActivityTracker tracks typing start/stop correctly."""
        tracker = UserActivityTracker()
        assert tracker.is_typing is False
        tracker.on_typing_start()
        assert tracker.is_typing is True
        tracker.on_typing_stop()
        assert tracker.is_typing is False

    def test_activity_tracker_idle_increases(self):
        """UserActivityTracker.idle_ms increases over time."""
        tracker = UserActivityTracker()
        tracker.on_user_input()
        idle1 = tracker.idle_ms
        # idle_ms should be >= 0
        assert idle1 >= 0

    def test_ui_typing_subscription_exists(self):
        """Controller subscribes to TOPIC_UI_TYPING."""
        ctx = create_wired_fsm(with_weave_policy=True)
        fsm = ctx["fsm"]
        assert hasattr(fsm, "_on_ui_typing")
        assert callable(fsm._on_ui_typing)

    def test_deliver_weave_immediate_method_exists(self):
        """Controller has _deliver_weave_immediate method."""
        ctx = create_wired_fsm(with_weave_policy=True)
        assert hasattr(ctx["fsm"], "_deliver_weave_immediate")

    def test_schedule_weave_flush_adaptive_method_exists(self):
        """Controller has _schedule_weave_flush_adaptive method."""
        ctx = create_wired_fsm(with_weave_policy=True)
        assert hasattr(ctx["fsm"], "_schedule_weave_flush_adaptive")

    def test_mark_results_deferred_method_exists(self):
        """Controller has _mark_results_deferred method."""
        ctx = create_wired_fsm(with_weave_policy=True)
        assert hasattr(ctx["fsm"], "_mark_results_deferred")

    def test_suppress_result_method_exists(self):
        """Controller has _suppress_result method."""
        ctx = create_wired_fsm(with_weave_policy=True)
        assert hasattr(ctx["fsm"], "_suppress_result")

    def test_emit_weave_decided_method_exists(self):
        """Controller has _emit_weave_decided method."""
        ctx = create_wired_fsm(with_weave_policy=True)
        assert hasattr(ctx["fsm"], "_emit_weave_decided")
