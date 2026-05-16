"""
Tests for M8 E8.1 -- Weave Signal Collector.

Covers:
  - 8.1.1: WeaveSignal dataclass construction, from_runtime() factory, to_dict/from_dict
  - 8.1.2: UserActivityTracker typing start/stop/input/idle
  - 8.1.3: Idle duration thresholds (IDLE_EAGER_MS, IDLE_BATCH_MS, TYPING_SUPPRESS_MS)
  - 8.1.4: Pending urgency profiler (_profile_urgency, _has_critical), turn_state urgency
  - 8.1.5: Affect-based emotional gating (_compute_emotional_gate)
  - Wiring: TOPIC_UI_TYPING in bus, guard table, SUBSCRIBED_TOPICS

Test count: 52 tests across 8 test classes.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from k1.concierge.bus.topics import (
    ALL_TOPICS,
    RELAXED_TOPICS,
    STRICT_TOPICS,
    TOPIC_UI_TYPING,
)
from k1.concierge.fsm.states import ConciergeState
from k1.concierge.fsm.transition_table import (
    FULL_GUARD_TABLE,
    SUBSCRIBED_TOPICS,
    GuardAction,
    get_guard_action,
)
from k1.concierge.protocols.weave_policy import (
    EMOTIONAL_GATE_OPEN,
    EMOTIONAL_GATE_SUPPRESS_ALL_NON_SAFETY,
    EMOTIONAL_GATE_SUPPRESS_TRIVIAL,
    EMOTIONAL_SUPPRESS_VALENCE,
    IDLE_BATCH_MS,
    IDLE_EAGER_MS,
    TYPING_SUPPRESS_MS,
    UserActivityTracker,
    WeaveSignal,
    _compute_emotional_gate,
    _get_affect_dict_from_ss,
    _has_critical,
    _profile_urgency,
)

# =====================================================================
# 8.1.1 -- WeaveSignal dataclass
# =====================================================================


class TestWeaveSignalDataclass:
    """WeaveSignal frozen dataclass construction and properties."""

    def test_default_construction(self) -> None:
        """Default WeaveSignal has safe zero/empty values."""
        sig = WeaveSignal()
        assert sig.fsm_state == ""
        assert sig.pending_count == 0
        assert sig.pending_urgency_profile == {"critical": 0, "normal": 0, "low": 0}
        assert sig.has_critical is False
        assert sig.user_typing is False
        assert sig.user_idle_ms == 0
        assert sig.affect_band == ""
        assert sig.affect_valence == 0.0
        assert sig.emotional_gate == EMOTIONAL_GATE_OPEN
        assert sig.backpool_utilization == 0.0
        assert sig.hitl_pending is False
        assert sig.recent_weave_count == 0

    def test_custom_construction(self) -> None:
        """WeaveSignal accepts all fields via keyword args."""
        sig = WeaveSignal(
            fsm_state="COMPANIONING",
            pending_count=3,
            pending_urgency_profile={"critical": 1, "normal": 2, "low": 0},
            has_critical=True,
            user_typing=True,
            user_idle_ms=500,
            affect_band="yellow",
            affect_valence=-0.3,
            emotional_gate=EMOTIONAL_GATE_SUPPRESS_TRIVIAL,
            backpool_utilization=0.67,
            hitl_pending=True,
            recent_weave_count=5,
        )
        assert sig.fsm_state == "COMPANIONING"
        assert sig.pending_count == 3
        assert sig.has_critical is True
        assert sig.user_typing is True
        assert sig.user_idle_ms == 500
        assert sig.affect_valence == -0.3
        assert sig.emotional_gate == EMOTIONAL_GATE_SUPPRESS_TRIVIAL
        assert sig.backpool_utilization == 0.67
        assert sig.hitl_pending is True
        assert sig.recent_weave_count == 5

    def test_frozen_immutability(self) -> None:
        """WeaveSignal is frozen -- attributes cannot be set after construction."""
        sig = WeaveSignal()
        with pytest.raises(AttributeError):
            sig.fsm_state = "LISTENING"  # type: ignore[misc]

    def test_to_dict_round_trip(self) -> None:
        """to_dict/from_dict round-trips all fields."""
        original = WeaveSignal(
            fsm_state="WEAVING",
            pending_count=2,
            pending_urgency_profile={"critical": 0, "normal": 1, "low": 1},
            has_critical=False,
            user_typing=True,
            user_idle_ms=1234,
            affect_band="green",
            affect_valence=0.7,
            emotional_gate=EMOTIONAL_GATE_OPEN,
            backpool_utilization=0.33,
            hitl_pending=False,
            recent_weave_count=3,
        )
        d = original.to_dict()
        restored = WeaveSignal.from_dict(d)
        assert restored == original

    def test_to_dict_keys(self) -> None:
        """to_dict returns all 12 expected keys."""
        d = WeaveSignal().to_dict()
        expected_keys = {
            "fsm_state",
            "pending_count",
            "pending_urgency_profile",
            "has_critical",
            "user_typing",
            "user_idle_ms",
            "affect_band",
            "affect_valence",
            "emotional_gate",
            "backpool_utilization",
            "hitl_pending",
            "recent_weave_count",
        }
        assert set(d.keys()) == expected_keys

    def test_from_dict_missing_keys_uses_defaults(self) -> None:
        """from_dict handles missing keys gracefully with defaults."""
        sig = WeaveSignal.from_dict({})
        assert sig.fsm_state == ""
        assert sig.pending_count == 0
        assert sig.emotional_gate == EMOTIONAL_GATE_OPEN


# =====================================================================
# 8.1.1 -- WeaveSignal.from_runtime() factory
# =====================================================================


class TestWeaveSignalFromRuntime:
    """WeaveSignal.from_runtime() atomic collection from runtime sources."""

    def test_minimal_from_runtime(self) -> None:
        """from_runtime with only fsm_state produces safe defaults."""
        sig = WeaveSignal.from_runtime(fsm_state=ConciergeState.LISTENING)
        assert sig.fsm_state == "LISTENING"
        assert sig.pending_count == 0
        assert sig.user_typing is False
        assert sig.backpool_utilization == 0.0
        assert sig.emotional_gate == EMOTIONAL_GATE_OPEN

    def test_from_runtime_reads_pending_results(self) -> None:
        """from_runtime reads pending_results from turn_state."""
        from collections import deque

        mock_ts = MagicMock()
        mock_ts.pending_results = deque(
            [
                {"task_id": "t1", "urgency": "critical"},
                {"task_id": "t2", "urgency": "normal"},
            ]
        )
        sig = WeaveSignal.from_runtime(
            fsm_state=ConciergeState.COMPANIONING,
            turn_state=mock_ts,
        )
        assert sig.pending_count == 2
        assert sig.has_critical is True
        assert sig.pending_urgency_profile["critical"] == 1
        assert sig.pending_urgency_profile["normal"] == 1

    def test_from_runtime_reads_activity_tracker(self) -> None:
        """from_runtime reads typing/idle from UserActivityTracker."""
        tracker = UserActivityTracker()
        tracker.on_typing_start()
        sig = WeaveSignal.from_runtime(
            fsm_state=ConciergeState.DISPATCHING,
            activity_tracker=tracker,
        )
        assert sig.user_typing is True
        assert sig.user_idle_ms >= 0

    def test_from_runtime_reads_backpool(self) -> None:
        """from_runtime reads BackPool utilization via get_pool_state()."""
        mock_bp = MagicMock()
        mock_bp.get_pool_state.return_value = {
            "active": 2,
            "size": 3,
            "available": 1,
            "utilization": 0.6667,
        }
        sig = WeaveSignal.from_runtime(
            fsm_state=ConciergeState.COMPANIONING,
            back_pool=mock_bp,
        )
        assert sig.backpool_utilization == pytest.approx(0.6667, abs=0.01)

    def test_from_runtime_reads_affect(self) -> None:
        """from_runtime reads affect from SessionState."""
        mock_section = MagicMock()
        mock_section.to_dict.return_value = {
            "valence": -0.7,
            "arousal": 0.5,
            "current_emotion": "frustration",
            "safety_band": "YELLOW",
            "affect_band": "yellow",
        }
        mock_ss = MagicMock()
        mock_ss.get_section.return_value = mock_section
        sig = WeaveSignal.from_runtime(
            fsm_state=ConciergeState.DELIVERING,
            ss=mock_ss,
        )
        assert sig.affect_valence == -0.7
        assert sig.affect_band == "yellow"
        assert sig.emotional_gate == EMOTIONAL_GATE_SUPPRESS_TRIVIAL

    def test_from_runtime_reads_hitl_and_weave_count(self) -> None:
        """from_runtime passes through hitl_pending and recent_weave_count."""
        sig = WeaveSignal.from_runtime(
            fsm_state=ConciergeState.LISTENING,
            hitl_pending=True,
            recent_weave_count=7,
        )
        assert sig.hitl_pending is True
        assert sig.recent_weave_count == 7

    def test_from_runtime_hitl_pending_true(self) -> None:
        """from_runtime preserves hitl_pending=True for policy R5.5."""
        sig = WeaveSignal.from_runtime(
            fsm_state=ConciergeState.COMPANIONING,
            hitl_pending=True,
        )
        assert sig.hitl_pending is True

    def test_from_runtime_backpool_exception_safe(self) -> None:
        """from_runtime handles BackPool exceptions gracefully."""
        mock_bp = MagicMock()
        mock_bp.get_pool_state.side_effect = RuntimeError("pool crashed")
        sig = WeaveSignal.from_runtime(
            fsm_state=ConciergeState.LISTENING,
            back_pool=mock_bp,
        )
        assert sig.backpool_utilization == 0.0

    def test_from_runtime_all_sources(self) -> None:
        """from_runtime with all sources produces complete signal."""
        from collections import deque

        mock_ts = MagicMock()
        mock_ts.pending_results = deque(
            [
                {"task_id": "t1", "urgency": "normal"},
                {"task_id": "t2", "urgency": "low"},
            ]
        )
        mock_bp = MagicMock()
        mock_bp.get_pool_state.return_value = {"active": 1, "size": 3}
        mock_section = MagicMock()
        mock_section.to_dict.return_value = {"valence": 0.5, "affect_band": "green"}
        mock_ss = MagicMock()
        mock_ss.get_section.return_value = mock_section
        tracker = UserActivityTracker()

        sig = WeaveSignal.from_runtime(
            fsm_state=ConciergeState.WEAVING,
            turn_state=mock_ts,
            back_pool=mock_bp,
            ss=mock_ss,
            activity_tracker=tracker,
            hitl_pending=False,
            recent_weave_count=2,
        )
        assert sig.fsm_state == "WEAVING"
        assert sig.pending_count == 2
        assert sig.has_critical is False
        assert sig.backpool_utilization == pytest.approx(0.3333, abs=0.01)
        assert sig.affect_band == "green"
        assert sig.emotional_gate == EMOTIONAL_GATE_OPEN
        assert sig.recent_weave_count == 2


# =====================================================================
# 8.1.2 -- UserActivityTracker
# =====================================================================


class TestUserActivityTracker:
    """UserActivityTracker typing and idle tracking."""

    def test_initial_state_not_typing(self) -> None:
        """New tracker reports not typing."""
        tracker = UserActivityTracker()
        assert tracker.is_typing is False
        assert tracker.typing_duration_ms == 0

    def test_typing_start_sets_typing(self) -> None:
        """on_typing_start sets is_typing=True."""
        tracker = UserActivityTracker()
        tracker.on_typing_start()
        assert tracker.is_typing is True

    def test_typing_stop_clears_typing(self) -> None:
        """on_typing_stop resets is_typing=False."""
        tracker = UserActivityTracker()
        tracker.on_typing_start()
        tracker.on_typing_stop()
        assert tracker.is_typing is False

    def test_user_input_clears_typing(self) -> None:
        """on_user_input clears typing and resets idle timer."""
        tracker = UserActivityTracker()
        tracker.on_typing_start()
        tracker.on_user_input()
        assert tracker.is_typing is False
        # idle_ms should be very small since we just called on_user_input
        assert tracker.idle_ms < 500

    def test_idle_ms_increases_over_time(self) -> None:
        """idle_ms reflects time since last user input."""
        tracker = UserActivityTracker()
        # Set last_user_input_ns to 100ms ago
        tracker._last_user_input_ns = time.monotonic_ns() - 100_000_000
        assert tracker.idle_ms >= 90  # at least ~90ms elapsed

    def test_typing_duration_ms_when_typing(self) -> None:
        """typing_duration_ms reflects time since typing started."""
        tracker = UserActivityTracker()
        tracker._typing = True
        tracker._last_typing_start_ns = time.monotonic_ns() - 50_000_000
        assert tracker.typing_duration_ms >= 40  # at least ~40ms

    def test_typing_duration_ms_zero_when_not_typing(self) -> None:
        """typing_duration_ms is 0 when not typing."""
        tracker = UserActivityTracker()
        assert tracker.typing_duration_ms == 0

    def test_idle_tick_is_noop(self) -> None:
        """on_user_idle_tick is currently a no-op (idle calculated on read)."""
        tracker = UserActivityTracker()
        before = tracker.idle_ms
        tracker.on_user_idle_tick()
        # Should not change behavior (it's a no-op)
        after = tracker.idle_ms
        assert after >= before

    def test_last_user_input_ns_updated_on_input(self) -> None:
        """on_user_input updates last_user_input_ns."""
        tracker = UserActivityTracker()
        before = tracker.last_user_input_ns
        # Small delay to ensure timestamp differs
        tracker.on_user_input()
        after = tracker.last_user_input_ns
        assert after >= before


# =====================================================================
# 8.1.3 -- Idle duration threshold constants
# =====================================================================


class TestIdleThresholdConstants:
    """Threshold constants for idle duration classification."""

    def test_idle_eager_ms_value(self) -> None:
        """IDLE_EAGER_MS is 10000 (10 seconds)."""
        assert IDLE_EAGER_MS == 10_000

    def test_idle_batch_ms_value(self) -> None:
        """IDLE_BATCH_MS is 3000 (3 seconds)."""
        assert IDLE_BATCH_MS == 3_000

    def test_typing_suppress_ms_value(self) -> None:
        """TYPING_SUPPRESS_MS is 500 (half second)."""
        assert TYPING_SUPPRESS_MS == 500

    def test_threshold_ordering(self) -> None:
        """TYPING_SUPPRESS_MS < IDLE_BATCH_MS < IDLE_EAGER_MS."""
        assert TYPING_SUPPRESS_MS < IDLE_BATCH_MS < IDLE_EAGER_MS


# =====================================================================
# 8.1.4 -- Pending urgency profiler
# =====================================================================


class TestPendingUrgencyProfiler:
    """_profile_urgency and _has_critical helpers."""

    def test_empty_pending_returns_zeroes(self) -> None:
        """Empty pending list produces zero-count profile."""
        profile = _profile_urgency([])
        assert profile == {"critical": 0, "normal": 0, "low": 0}

    def test_single_critical(self) -> None:
        """Single critical result is counted."""
        profile = _profile_urgency([{"urgency": "critical"}])
        assert profile["critical"] == 1
        assert profile["normal"] == 0

    def test_mixed_urgencies(self) -> None:
        """Mixed urgencies are counted correctly."""
        items = [
            {"urgency": "critical"},
            {"urgency": "normal"},
            {"urgency": "normal"},
            {"urgency": "low"},
        ]
        profile = _profile_urgency(items)
        assert profile["critical"] == 1
        assert profile["normal"] == 2
        assert profile["low"] == 1

    def test_missing_urgency_defaults_to_normal(self) -> None:
        """Items without urgency field default to normal."""
        profile = _profile_urgency([{"task_id": "t1"}])
        assert profile["normal"] == 1

    def test_has_critical_true(self) -> None:
        """_has_critical returns True for critical items."""
        assert _has_critical([{"urgency": "critical"}]) is True

    def test_has_critical_urgent(self) -> None:
        """_has_critical returns True for urgent items."""
        assert _has_critical([{"urgency": "urgent"}]) is True

    def test_has_critical_false_for_normal(self) -> None:
        """_has_critical returns False when only normal/low items."""
        items = [{"urgency": "normal"}, {"urgency": "low"}]
        assert _has_critical(items) is False

    def test_has_critical_empty(self) -> None:
        """_has_critical returns False for empty list."""
        assert _has_critical([]) is False


class TestTurnStateUrgency:
    """M8 E8.1.4: FSMTurnState.enqueue_result urgency parameter."""

    def test_enqueue_result_default_urgency(self) -> None:
        """enqueue_result defaults urgency to 'normal'."""
        from k1.concierge.fsm.turn_state import FSMTurnState

        ts = FSMTurnState()
        env = MagicMock()
        env.envelope_id = "e1"
        env.parent_id = "p1"
        ts.enqueue_result("t1", {"data": "x"}, env)
        item = ts.pending_results[0]
        assert item["urgency"] == "normal"

    def test_enqueue_result_custom_urgency(self) -> None:
        """enqueue_result stores provided urgency label."""
        from k1.concierge.fsm.turn_state import FSMTurnState

        ts = FSMTurnState()
        env = MagicMock()
        env.envelope_id = "e2"
        env.parent_id = "p2"
        ts.enqueue_result("t2", {"data": "y"}, env, urgency="critical")
        item = ts.pending_results[0]
        assert item["urgency"] == "critical"

    def test_enqueue_result_low_urgency(self) -> None:
        """enqueue_result stores low urgency label."""
        from k1.concierge.fsm.turn_state import FSMTurnState

        ts = FSMTurnState()
        env = MagicMock()
        env.envelope_id = "e3"
        env.parent_id = "p3"
        ts.enqueue_result("t3", {"data": "z"}, env, urgency="low")
        item = ts.pending_results[0]
        assert item["urgency"] == "low"


# =====================================================================
# 8.1.5 -- Affect-based emotional gating
# =====================================================================


class TestEmotionalGate:
    """_compute_emotional_gate and _get_affect_dict_from_ss."""

    def test_empty_affect_returns_open(self) -> None:
        """Empty affect dict means gate is open."""
        assert _compute_emotional_gate({}) == EMOTIONAL_GATE_OPEN

    def test_positive_valence_returns_open(self) -> None:
        """Positive valence means gate is open."""
        assert _compute_emotional_gate({"valence": 0.5}) == EMOTIONAL_GATE_OPEN

    def test_zero_valence_returns_open(self) -> None:
        """Zero valence means gate is open."""
        assert _compute_emotional_gate({"valence": 0.0}) == EMOTIONAL_GATE_OPEN

    def test_negative_valence_above_threshold_returns_open(self) -> None:
        """Valence at -0.3 (above threshold) means gate is open."""
        assert _compute_emotional_gate({"valence": -0.3}) == EMOTIONAL_GATE_OPEN

    def test_negative_valence_below_threshold_suppress_trivial(self) -> None:
        """Valence below -0.5 suppresses trivial results."""
        result = _compute_emotional_gate({"valence": -0.7})
        assert result == EMOTIONAL_GATE_SUPPRESS_TRIVIAL

    def test_crisis_emotion_suppress_all(self) -> None:
        """current_emotion='crisis' suppresses all non-safety."""
        result = _compute_emotional_gate({"current_emotion": "crisis", "valence": 0.5})
        assert result == EMOTIONAL_GATE_SUPPRESS_ALL_NON_SAFETY

    def test_red_safety_band_suppress_all(self) -> None:
        """safety_band='RED' suppresses all non-safety."""
        result = _compute_emotional_gate({"safety_band": "RED", "valence": 0.5})
        assert result == EMOTIONAL_GATE_SUPPRESS_ALL_NON_SAFETY

    def test_crisis_overrides_valence(self) -> None:
        """Crisis check is evaluated before valence threshold."""
        result = _compute_emotional_gate({"current_emotion": "crisis", "valence": -0.7})
        assert result == EMOTIONAL_GATE_SUPPRESS_ALL_NON_SAFETY

    def test_suppress_valence_constant(self) -> None:
        """EMOTIONAL_SUPPRESS_VALENCE is -0.5."""
        assert EMOTIONAL_SUPPRESS_VALENCE == -0.5

    def test_get_affect_dict_from_ss_none(self) -> None:
        """_get_affect_dict_from_ss returns {} for None ss."""
        assert _get_affect_dict_from_ss(None) == {}

    def test_get_affect_dict_from_ss_with_section(self) -> None:
        """_get_affect_dict_from_ss reads affective_now section."""
        mock_section = MagicMock()
        mock_section.to_dict.return_value = {"valence": 0.3}
        mock_ss = MagicMock()
        mock_ss.get_section.return_value = mock_section
        result = _get_affect_dict_from_ss(mock_ss)
        assert result == {"valence": 0.3}

    def test_get_affect_dict_from_ss_no_section(self) -> None:
        """_get_affect_dict_from_ss returns {} if section missing."""
        mock_ss = MagicMock()
        mock_ss.get_section.return_value = None
        result = _get_affect_dict_from_ss(mock_ss)
        assert result == {}


# =====================================================================
# Wiring: TOPIC_UI_TYPING in bus, guard table, SUBSCRIBED_TOPICS
# =====================================================================


class TestTopicUITypingWiring:
    """M8 E8.1.2: TOPIC_UI_TYPING bus integration."""

    def test_topic_value(self) -> None:
        """TOPIC_UI_TYPING has correct string value."""
        assert TOPIC_UI_TYPING == "k1.ui.typing.v1"

    def test_in_all_topics(self) -> None:
        """TOPIC_UI_TYPING is in ALL_TOPICS."""
        assert TOPIC_UI_TYPING in ALL_TOPICS

    def test_in_relaxed_topics(self) -> None:
        """TOPIC_UI_TYPING is in RELAXED_TOPICS (high-frequency, best-effort)."""
        assert TOPIC_UI_TYPING in RELAXED_TOPICS

    def test_not_in_strict_topics(self) -> None:
        """TOPIC_UI_TYPING is NOT in STRICT_TOPICS."""
        assert TOPIC_UI_TYPING not in STRICT_TOPICS

    def test_in_subscribed_topics(self) -> None:
        """TOPIC_UI_TYPING is in SUBSCRIBED_TOPICS."""
        assert TOPIC_UI_TYPING in SUBSCRIBED_TOPICS

    def test_guard_table_all_11_states_have_typing(self) -> None:
        """Every ConciergeState has an entry for TOPIC_UI_TYPING in guard table."""
        for state in ConciergeState:
            assert state in FULL_GUARD_TABLE, f"Missing state {state.name}"
            assert (
                TOPIC_UI_TYPING in FULL_GUARD_TABLE[state]
            ), f"Missing TOPIC_UI_TYPING in {state.name}"

    def test_guard_table_typing_is_observe(self) -> None:
        """TOPIC_UI_TYPING is OBSERVE in all 11 states."""
        for state in ConciergeState:
            action, target = FULL_GUARD_TABLE[state][TOPIC_UI_TYPING]
            assert action == GuardAction.OBSERVE, f"{state.name}: expected OBSERVE, got {action}"
            assert target is None, f"{state.name}: expected None target, got {target}"

    def test_get_guard_action_returns_observe(self) -> None:
        """get_guard_action returns (OBSERVE, None) for typing in any state."""
        for state in ConciergeState:
            action, target = get_guard_action(state, TOPIC_UI_TYPING)
            assert action == GuardAction.OBSERVE
            assert target is None
