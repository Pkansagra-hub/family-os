"""
Tests for M8 E8.4 -- Policy Integration, Fallback, and Observability.

Covers:
  - 8.4.1: WeaveIntegrationRouter (route_decision, route_with_result)
  - 8.4.2: TypingPolicyReEvaluator (on_typing_start, on_typing_stop)
  - 8.4.3: WeaveFallbackHandler (fallback_decide, safe_decide)
  - 8.4.4: WeaveMetricsCollector (record_decision, to_metrics_dict, to_event)
  - 8.4.5: WeaveQueue (add_result, drain, set_front_busy, set_policy_window)

Test count: ~95 tests across 9 test classes.
"""

from __future__ import annotations

import time

import pytest

from poc.k1_poc.fsm.states import ConciergeState
from poc.k1_poc.protocols.weave_policy import (
    _ACTION_TO_DECISION,
    _FALLBACK_WINDOW_MS,
    EMOTIONAL_GATE_OPEN,
    EMOTIONAL_GATE_SUPPRESS_ALL_NON_SAFETY,
    EMOTIONAL_GATE_SUPPRESS_TRIVIAL,
    ReEvalResult,
    RoutingResult,
    TypingPolicyReEvaluator,
    WeaveDecision,
    WeaveDecisionResult,
    WeaveFallbackHandler,
    WeaveIntegrationRouter,
    WeaveMetricsCollector,
    WeavePolicy,
    WeaveQueue,
    WeaveSignal,
)
from poc.k1_poc.protocols.weave_state import get_weave_action

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


def _make_result(
    task_id: str = "task_1",
    urgency: str = "normal",
    domain: str = "",
    result: dict | None = None,
) -> dict:
    """Build a result dict for WeaveQueue tests."""
    r: dict = {
        "task_id": task_id,
        "result": result or {},
        "envelope_id": f"env_{task_id}",
        "urgency": urgency,
        "queued_at_ns": time.monotonic_ns(),
    }
    if domain:
        r["domain"] = domain
    return r


# =====================================================================
# 8.4.1 -- WeaveIntegrationRouter tests
# =====================================================================


class TestRoutingResultDataclass:
    """RoutingResult frozen dataclass basic behavior."""

    def test_default_values(self):
        r = RoutingResult()
        assert r.action == "suppress"
        assert r.window_ms == 0
        assert r.reasoning == ""

    def test_custom_values(self):
        dr = WeaveDecisionResult(
            decision=WeaveDecision.BATCH,
            window_ms=300,
        )
        r = RoutingResult(
            action="schedule_flush",
            window_ms=300,
            decision=dr,
            reasoning="test",
        )
        assert r.action == "schedule_flush"
        assert r.window_ms == 300
        assert r.decision is dr

    def test_frozen(self):
        r = RoutingResult()
        with pytest.raises(AttributeError):
            r.action = "flush_now"


class TestWeaveIntegrationRouter:
    """8.4.1: Router maps policy decision to action tags."""

    @pytest.fixture()
    def policy(self):
        return WeavePolicy()

    @pytest.fixture()
    def router(self, policy):
        return WeaveIntegrationRouter(policy)

    def test_policy_property(self, router, policy):
        assert router.policy is policy

    def test_route_immediate(self, router):
        # LISTENING + idle > 10s -> IMMEDIATE
        signal = _make_signal(
            fsm_state=ConciergeState.LISTENING.name,
            user_idle_ms=15_000,
        )
        result = router.route_decision(signal)
        assert result.action == "flush_now"
        assert result.window_ms == 0
        assert result.decision.decision == WeaveDecision.IMMEDIATE

    def test_route_batch(self, router):
        # Default batch path (rule 9)
        signal = _make_signal(
            fsm_state=ConciergeState.COMPANIONING.name,
            user_idle_ms=500,
            pending_count=1,
        )
        result = router.route_decision(signal)
        assert result.action == "schedule_flush"
        assert result.window_ms > 0
        assert result.decision.decision == WeaveDecision.BATCH

    def test_route_defer(self, router):
        # User typing -> DEFER
        signal = _make_signal(user_typing=True, user_idle_ms=0)
        result = router.route_decision(signal)
        assert result.action == "mark_deferred"
        assert result.window_ms == 0
        assert result.decision.decision == WeaveDecision.DEFER

    def test_route_digest(self, router):
        # 3+ low-urgency pending -> DIGEST
        signal = _make_signal(
            fsm_state=ConciergeState.COMPANIONING.name,
            pending_count=3,
            pending_urgency_profile={"critical": 0, "normal": 0, "low": 3},
            user_idle_ms=500,
        )
        result = router.route_decision(signal)
        assert result.action == "schedule_digest"
        assert result.window_ms > 0
        assert result.decision.decision == WeaveDecision.DIGEST

    def test_route_suppress(self, router):
        # Emotional gate: suppress all non-safety
        signal = _make_signal(
            emotional_gate=EMOTIONAL_GATE_SUPPRESS_ALL_NON_SAFETY,
            fsm_state=ConciergeState.COMPANIONING.name,
            user_idle_ms=500,
        )
        result = router.route_decision(signal)
        assert result.action == "suppress"
        assert result.decision.decision == WeaveDecision.SUPPRESS

    def test_route_with_result_immediate(self, router):
        dr = WeaveDecisionResult(
            decision=WeaveDecision.IMMEDIATE,
            window_ms=0,
        )
        result = router.route_with_result(dr)
        assert result.action == "flush_now"

    def test_route_with_result_batch(self, router):
        dr = WeaveDecisionResult(
            decision=WeaveDecision.BATCH,
            window_ms=400,
        )
        result = router.route_with_result(dr)
        assert result.action == "schedule_flush"
        assert result.window_ms == 400

    def test_route_with_result_defer(self, router):
        dr = WeaveDecisionResult(decision=WeaveDecision.DEFER, window_ms=0)
        result = router.route_with_result(dr)
        assert result.action == "mark_deferred"

    def test_route_with_result_digest(self, router):
        dr = WeaveDecisionResult(
            decision=WeaveDecision.DIGEST,
            window_ms=15_000,
        )
        result = router.route_with_result(dr)
        assert result.action == "schedule_digest"
        assert result.window_ms == 15_000

    def test_route_with_result_suppress(self, router):
        dr = WeaveDecisionResult(
            decision=WeaveDecision.SUPPRESS,
            window_ms=0,
        )
        result = router.route_with_result(dr)
        assert result.action == "suppress"

    def test_routing_reasoning_contains_decision_name(self, router):
        signal = _make_signal(
            fsm_state=ConciergeState.LISTENING.name,
            user_idle_ms=15_000,
        )
        result = router.route_decision(signal)
        assert "IMMEDIATE" in result.reasoning
        assert "flush_now" in result.reasoning

    def test_routing_all_five_decisions_reachable(self, router):
        """All 5 WeaveDecision values produce distinct action tags."""
        actions_seen = set()
        for decision_val in WeaveDecision:
            dr = WeaveDecisionResult(
                decision=decision_val,
                window_ms=(
                    500
                    if decision_val
                    in (
                        WeaveDecision.BATCH,
                        WeaveDecision.DIGEST,
                    )
                    else 0
                ),
            )
            result = router.route_with_result(dr)
            actions_seen.add(result.action)

        assert actions_seen == {
            "flush_now",
            "schedule_flush",
            "mark_deferred",
            "schedule_digest",
            "suppress",
        }


# =====================================================================
# 8.4.2 -- TypingPolicyReEvaluator tests
# =====================================================================


class TestReEvalResultDataclass:
    """ReEvalResult dataclass basics."""

    def test_default_values(self):
        r = ReEvalResult()
        assert r.action == "no_change"
        assert r.new_decision is None
        assert r.reasoning == ""

    def test_custom_values(self):
        dr = WeaveDecisionResult(decision=WeaveDecision.DEFER)
        r = ReEvalResult(
            action="cancel_timer",
            new_decision=dr,
            reasoning="typing",
        )
        assert r.action == "cancel_timer"
        assert r.new_decision is dr

    def test_frozen(self):
        r = ReEvalResult()
        with pytest.raises(AttributeError):
            r.action = "restart_timer"


class TestTypingPolicyReEvaluator:
    """8.4.2: Typing-based policy re-evaluation."""

    @pytest.fixture()
    def policy(self):
        return WeavePolicy()

    @pytest.fixture()
    def evaluator(self, policy):
        return TypingPolicyReEvaluator(policy, debounce_ms=500)

    def test_policy_property(self, evaluator, policy):
        assert evaluator.policy is policy

    def test_debounce_ms_property(self, evaluator):
        assert evaluator.debounce_ms == 500

    def test_custom_debounce(self, policy):
        e = TypingPolicyReEvaluator(policy, debounce_ms=300)
        assert e.debounce_ms == 300

    # -- on_typing_start --

    def test_typing_start_no_active_timer(self, evaluator):
        signal = _make_signal(user_typing=True)
        result = evaluator.on_typing_start(signal, has_active_timer=False)
        assert result.action == "no_change"

    def test_typing_start_with_timer_cancels(self, evaluator):
        signal = _make_signal(user_typing=True, user_idle_ms=0)
        result = evaluator.on_typing_start(signal, has_active_timer=True)
        assert result.action == "cancel_timer"
        assert result.new_decision is not None
        assert result.new_decision.decision == WeaveDecision.DEFER

    def test_typing_start_critical_overrides(self, evaluator):
        # Critical urgency prevents DEFER even when typing
        signal = _make_signal(
            user_typing=True,
            has_critical=True,
            pending_urgency_profile={"critical": 1, "normal": 0, "low": 0},
            fsm_state=ConciergeState.LISTENING.name,
            user_idle_ms=15_000,
        )
        result = evaluator.on_typing_start(signal, has_active_timer=True)
        # Policy rule 2 fires: critical + gate open -> IMMEDIATE
        # So typing_start returns no_change (timer keeps running)
        assert result.action == "no_change"
        assert result.new_decision is not None
        assert result.new_decision.decision == WeaveDecision.IMMEDIATE

    # -- on_typing_stop --

    def test_typing_stop_no_pending(self, evaluator):
        signal = _make_signal(user_typing=False)
        result = evaluator.on_typing_stop(
            signal,
            has_pending_results=False,
        )
        assert result.action == "no_change"

    def test_typing_stop_restarts_timer(self, evaluator):
        signal = _make_signal(
            user_typing=False,
            user_idle_ms=5_000,
            pending_count=1,
            fsm_state=ConciergeState.COMPANIONING.name,
        )
        result = evaluator.on_typing_stop(
            signal,
            has_pending_results=True,
        )
        assert result.action == "restart_timer"
        assert result.new_decision is not None
        assert result.new_decision.decision in (
            WeaveDecision.BATCH,
            WeaveDecision.IMMEDIATE,
        )

    def test_typing_stop_still_defer_gate(self, evaluator):
        # Emotional gate suppresses trivial + no critical -> DEFER
        signal = _make_signal(
            user_typing=False,
            user_idle_ms=5_000,
            pending_count=1,
            emotional_gate=EMOTIONAL_GATE_SUPPRESS_TRIVIAL,
            has_critical=False,
            fsm_state=ConciergeState.COMPANIONING.name,
        )
        result = evaluator.on_typing_stop(
            signal,
            has_pending_results=True,
        )
        assert result.action == "no_change"
        assert result.new_decision.decision == WeaveDecision.DEFER

    def test_typing_stop_digest_restarts(self, evaluator):
        # 3+ low pending -> DIGEST, which also triggers restart
        signal = _make_signal(
            user_typing=False,
            user_idle_ms=500,
            pending_count=3,
            pending_urgency_profile={"critical": 0, "normal": 0, "low": 3},
            fsm_state=ConciergeState.COMPANIONING.name,
        )
        result = evaluator.on_typing_stop(
            signal,
            has_pending_results=True,
        )
        assert result.action == "restart_timer"
        assert result.new_decision.decision == WeaveDecision.DIGEST

    def test_typing_stop_suppress_no_restart(self, evaluator):
        signal = _make_signal(
            user_typing=False,
            emotional_gate=EMOTIONAL_GATE_SUPPRESS_ALL_NON_SAFETY,
            fsm_state=ConciergeState.COMPANIONING.name,
            user_idle_ms=500,
        )
        result = evaluator.on_typing_stop(
            signal,
            has_pending_results=True,
        )
        assert result.action == "no_change"
        assert result.new_decision.decision == WeaveDecision.SUPPRESS


# =====================================================================
# 8.4.3 -- WeaveFallbackHandler tests
# =====================================================================


class TestFallbackConstants:
    """Verify fallback mapping constants."""

    def test_action_to_decision_keys(self):
        expected = {"immediate", "queue_weave", "queue", "chain", "dead_letter"}
        assert set(_ACTION_TO_DECISION.keys()) == expected

    def test_immediate_maps_to_immediate(self):
        assert _ACTION_TO_DECISION["immediate"] == WeaveDecision.IMMEDIATE

    def test_queue_weave_maps_to_batch(self):
        assert _ACTION_TO_DECISION["queue_weave"] == WeaveDecision.BATCH

    def test_queue_maps_to_batch(self):
        assert _ACTION_TO_DECISION["queue"] == WeaveDecision.BATCH

    def test_chain_maps_to_batch(self):
        assert _ACTION_TO_DECISION["chain"] == WeaveDecision.BATCH

    def test_dead_letter_maps_to_suppress(self):
        assert _ACTION_TO_DECISION["dead_letter"] == WeaveDecision.SUPPRESS

    def test_fallback_window_ms(self):
        assert _FALLBACK_WINDOW_MS == 500


class TestWeaveFallbackHandler:
    """8.4.3: Deterministic fallback mode."""

    @pytest.fixture()
    def handler(self):
        return WeaveFallbackHandler()

    def test_fallback_window_property(self, handler):
        assert handler.fallback_window_ms == 500

    def test_custom_fallback_window(self):
        h = WeaveFallbackHandler(fallback_window_ms=1000)
        assert h.fallback_window_ms == 1000

    # -- fallback_decide for each state --

    def test_fallback_listening_immediate(self, handler):
        result = handler.fallback_decide(ConciergeState.LISTENING)
        assert result.decision == WeaveDecision.IMMEDIATE
        assert result.window_ms == 0
        assert "fallback" in result.reasoning

    def test_fallback_proactive_wake_immediate(self, handler):
        result = handler.fallback_decide(ConciergeState.PROACTIVE_WAKE)
        assert result.decision == WeaveDecision.IMMEDIATE
        assert result.window_ms == 0

    def test_fallback_companioning_batch(self, handler):
        result = handler.fallback_decide(ConciergeState.COMPANIONING)
        assert result.decision == WeaveDecision.BATCH
        assert result.window_ms == 500

    def test_fallback_dispatching_batch(self, handler):
        result = handler.fallback_decide(ConciergeState.DISPATCHING)
        assert result.decision == WeaveDecision.BATCH
        assert result.window_ms == 500

    def test_fallback_delivering_batch(self, handler):
        result = handler.fallback_decide(ConciergeState.DELIVERING)
        assert result.decision == WeaveDecision.BATCH
        assert result.window_ms == 500

    def test_fallback_weaving_batch(self, handler):
        result = handler.fallback_decide(ConciergeState.WEAVING)
        assert result.decision == WeaveDecision.BATCH
        assert result.window_ms == 500

    def test_fallback_all_states_produce_valid_decision(self, handler):
        """Every ConciergeState produces a valid WeaveDecision."""
        for state in ConciergeState:
            result = handler.fallback_decide(state)
            assert isinstance(result, WeaveDecisionResult)
            assert result.decision in WeaveDecision
            assert "fallback" in result.reasoning

    def test_fallback_matches_static_table(self, handler):
        """Verify fallback aligns with get_weave_action for all states."""
        for state in ConciergeState:
            action = get_weave_action(state)
            result = handler.fallback_decide(state)
            expected_decision = _ACTION_TO_DECISION.get(
                action.value,
                WeaveDecision.BATCH,
            )
            assert result.decision == expected_decision, (
                f"State {state.name}: action={action.value} -> "
                f"expected {expected_decision.name}, "
                f"got {result.decision.name}"
            )

    def test_fallback_reasoning_includes_state(self, handler):
        result = handler.fallback_decide(ConciergeState.CLARIFYING_USER)
        assert "CLARIFYING_USER" in result.reasoning
        assert "fallback" in result.reasoning

    # -- safe_decide --

    def test_safe_decide_uses_policy_when_enabled(self, handler):
        policy = WeavePolicy()
        signal = _make_signal(
            fsm_state=ConciergeState.LISTENING.name,
            user_idle_ms=15_000,
        )
        result = handler.safe_decide(
            policy,
            signal,
            ConciergeState.LISTENING,
            policy_enabled=True,
        )
        # Policy R1: LISTENING + idle > 10s -> IMMEDIATE
        assert result.decision == WeaveDecision.IMMEDIATE

    def test_safe_decide_uses_fallback_when_disabled(self, handler):
        policy = WeavePolicy()
        signal = _make_signal(
            fsm_state=ConciergeState.LISTENING.name,
            user_idle_ms=15_000,
        )
        result = handler.safe_decide(
            policy,
            signal,
            ConciergeState.LISTENING,
            policy_enabled=False,
        )
        # Fallback: LISTENING -> IMMEDIATE
        assert result.decision == WeaveDecision.IMMEDIATE
        assert "fallback" in result.reasoning

    def test_safe_decide_catches_policy_exception(self, handler):

        class BadPolicy:
            def decide(self, signal):
                raise RuntimeError("policy error")

        signal = _make_signal()
        result = handler.safe_decide(
            BadPolicy(),
            signal,
            ConciergeState.COMPANIONING,
            policy_enabled=True,
        )
        assert result.decision == WeaveDecision.BATCH
        assert result.window_ms == 500
        assert "fallback" in result.reasoning

    def test_safe_decide_returns_policy_result_on_success(self, handler):
        policy = WeavePolicy()
        signal = _make_signal(
            user_typing=True,
            user_idle_ms=0,
            fsm_state=ConciergeState.COMPANIONING.name,
        )
        result = handler.safe_decide(
            policy,
            signal,
            ConciergeState.COMPANIONING,
            policy_enabled=True,
        )
        # Policy R3: user_typing -> DEFER
        assert result.decision == WeaveDecision.DEFER


# =====================================================================
# 8.4.4 -- WeaveMetricsCollector tests
# =====================================================================


class TestWeaveMetricsCollector:
    """8.4.4: Per-session metrics tracking."""

    @pytest.fixture()
    def collector(self):
        return WeaveMetricsCollector()

    def test_initial_state(self, collector):
        assert collector.weave_count == 0
        assert collector.digest_count == 0
        assert collector.defer_count == 0
        assert collector.suppress_count == 0
        assert collector.batch_count == 0
        assert collector.immediate_count == 0
        assert collector.fallback_count == 0
        assert collector.total_delivered == 0
        assert collector.avg_latency_ms == 0.0
        assert collector.user_acknowledged_rate == 0.0

    def test_record_immediate(self, collector):
        dr = WeaveDecisionResult(decision=WeaveDecision.IMMEDIATE)
        collector.record_decision(dr, latency_ms=50.0)
        assert collector.weave_count == 1
        assert collector.immediate_count == 1
        assert collector.total_delivered == 1
        assert collector.avg_latency_ms == 50.0

    def test_record_batch(self, collector):
        dr = WeaveDecisionResult(decision=WeaveDecision.BATCH, window_ms=500)
        collector.record_decision(dr, latency_ms=600.0)
        assert collector.weave_count == 1
        assert collector.batch_count == 1
        assert collector.total_delivered == 1

    def test_record_defer(self, collector):
        dr = WeaveDecisionResult(decision=WeaveDecision.DEFER)
        collector.record_decision(dr)
        assert collector.defer_count == 1
        assert collector.total_delivered == 0

    def test_record_digest(self, collector):
        dr = WeaveDecisionResult(
            decision=WeaveDecision.DIGEST,
            window_ms=15_000,
        )
        collector.record_decision(dr, latency_ms=15_500.0)
        assert collector.digest_count == 1
        assert collector.total_delivered == 1

    def test_record_suppress(self, collector):
        dr = WeaveDecisionResult(decision=WeaveDecision.SUPPRESS)
        collector.record_decision(dr)
        assert collector.suppress_count == 1
        assert collector.total_delivered == 0

    def test_record_fallback(self, collector):
        dr = WeaveDecisionResult(decision=WeaveDecision.BATCH, window_ms=500)
        collector.record_decision(dr, fallback_used=True)
        assert collector.fallback_count == 1
        assert collector.weave_count == 1

    def test_multiple_decisions(self, collector):
        decisions = [
            (WeaveDecision.IMMEDIATE, 50.0),
            (WeaveDecision.BATCH, 600.0),
            (WeaveDecision.BATCH, 550.0),
            (WeaveDecision.DEFER, 0.0),
            (WeaveDecision.DIGEST, 15_000.0),
            (WeaveDecision.SUPPRESS, 0.0),
        ]
        for d, lat in decisions:
            dr = WeaveDecisionResult(decision=d, window_ms=500 if d == WeaveDecision.BATCH else 0)
            collector.record_decision(dr, latency_ms=lat)

        assert collector.weave_count == 3  # 1 IMMEDIATE + 2 BATCH
        assert collector.immediate_count == 1
        assert collector.batch_count == 2
        assert collector.digest_count == 1
        assert collector.defer_count == 1
        assert collector.suppress_count == 1
        assert collector.total_delivered == 4  # IMMEDIATE + 2 BATCH + DIGEST

    def test_avg_latency_ms(self, collector):
        for lat in [100.0, 200.0, 300.0]:
            dr = WeaveDecisionResult(decision=WeaveDecision.IMMEDIATE)
            collector.record_decision(dr, latency_ms=lat)
        assert collector.avg_latency_ms == pytest.approx(200.0)

    def test_avg_latency_zero_without_samples(self, collector):
        assert collector.avg_latency_ms == 0.0

    def test_record_acknowledgement(self, collector):
        dr = WeaveDecisionResult(decision=WeaveDecision.IMMEDIATE)
        collector.record_decision(dr)
        collector.record_acknowledgement()
        assert collector.user_acknowledged_rate == pytest.approx(1.0)

    def test_acknowledged_rate_partial(self, collector):
        for _ in range(4):
            dr = WeaveDecisionResult(decision=WeaveDecision.BATCH, window_ms=500)
            collector.record_decision(dr)
        collector.record_acknowledgement()
        collector.record_acknowledgement()
        assert collector.user_acknowledged_rate == pytest.approx(0.5)

    def test_acknowledged_rate_zero_delivered(self, collector):
        assert collector.user_acknowledged_rate == 0.0

    def test_to_metrics_dict(self, collector):
        dr = WeaveDecisionResult(decision=WeaveDecision.IMMEDIATE)
        collector.record_decision(dr, latency_ms=42.0)
        m = collector.to_metrics_dict()
        assert m["weave_count"] == 1
        assert m["immediate_count"] == 1
        assert m["batch_count"] == 0
        assert m["defer_count"] == 0
        assert m["suppress_count"] == 0
        assert m["digest_count"] == 0
        assert m["total_delivered"] == 1
        assert m["acknowledged"] == 0
        assert m["avg_latency_ms"] == pytest.approx(42.0)
        assert m["latency_samples"] == 1
        assert m["user_acknowledged_rate"] == pytest.approx(0.0)
        assert m["fallback_count"] == 0

    def test_to_event(self, collector):
        dr = WeaveDecisionResult(decision=WeaveDecision.BATCH, window_ms=500)
        collector.record_decision(dr, latency_ms=100.0)
        event = collector.to_event(session_id="sess_42")
        assert event["session_id"] == "sess_42"
        assert event["weave_count"] == 1
        assert event["avg_latency_ms"] == pytest.approx(100.0)

    def test_reset(self, collector):
        for d in WeaveDecision:
            dr = WeaveDecisionResult(decision=d, window_ms=500)
            collector.record_decision(dr, latency_ms=100.0)
        collector.record_acknowledgement()
        collector.reset()
        assert collector.weave_count == 0
        assert collector.digest_count == 0
        assert collector.defer_count == 0
        assert collector.suppress_count == 0
        assert collector.fallback_count == 0
        assert collector.total_delivered == 0
        assert collector.avg_latency_ms == 0.0
        assert collector.user_acknowledged_rate == 0.0

    def test_latency_not_recorded_for_defer(self, collector):
        dr = WeaveDecisionResult(decision=WeaveDecision.DEFER)
        collector.record_decision(dr, latency_ms=9999.0)
        assert collector.avg_latency_ms == 0.0

    def test_latency_not_recorded_for_suppress(self, collector):
        dr = WeaveDecisionResult(decision=WeaveDecision.SUPPRESS)
        collector.record_decision(dr, latency_ms=9999.0)
        assert collector.avg_latency_ms == 0.0

    def test_zero_latency_not_recorded(self, collector):
        dr = WeaveDecisionResult(decision=WeaveDecision.IMMEDIATE)
        collector.record_decision(dr, latency_ms=0.0)
        assert collector.avg_latency_ms == 0.0


# =====================================================================
# 8.4.5 -- WeaveQueue tests
# =====================================================================


class TestWeaveQueue:
    """8.4.5: Consolidated weave queue with policy delegation."""

    @pytest.fixture()
    def queue(self):
        return WeaveQueue(max_depth=4, batch_window_ms=500)

    def test_initial_state(self, queue):
        assert queue.pending_count == 0
        assert queue.queued_count == 0
        assert queue.drain_count == 0
        assert queue.batch_window_ms == 500
        assert queue.is_empty is True
        assert queue.total_count == 0

    def test_add_result_to_pending(self, queue):
        r = _make_result("t1")
        evicted = queue.add_result(r)
        assert evicted is None
        assert queue.pending_count == 1

    def test_add_multiple_results(self, queue):
        for i in range(3):
            queue.add_result(_make_result(f"t{i}"))
        assert queue.pending_count == 3

    def test_drain_returns_pending(self, queue):
        for i in range(3):
            queue.add_result(_make_result(f"t{i}"))
        results = queue.drain()
        assert len(results) == 3
        assert queue.pending_count == 0
        assert queue.drain_count == 1

    def test_drain_empty(self, queue):
        results = queue.drain()
        assert results == []
        assert queue.drain_count == 0

    def test_overflow_eviction(self, queue):
        for i in range(4):
            queue.add_result(_make_result(f"t{i}"))
        evicted = queue.add_result(_make_result("t4"))
        assert evicted is not None
        assert evicted["task_id"] == "t0"
        assert queue.pending_count == 4

    def test_front_busy_queues(self, queue):
        queue.set_front_busy(True)
        queue.add_result(_make_result("t1"))
        assert queue.pending_count == 0
        assert queue.queued_count == 1

    def test_front_busy_release_moves_to_pending(self, queue):
        queue.set_front_busy(True)
        queue.add_result(_make_result("t1"))
        queue.add_result(_make_result("t2"))
        queue.set_front_busy(False)
        assert queue.pending_count == 2
        assert queue.queued_count == 0

    def test_front_busy_overflow(self, queue):
        queue.set_front_busy(True)
        for i in range(4):
            queue.add_result(_make_result(f"t{i}"))
        evicted = queue.add_result(_make_result("t4"))
        assert evicted is not None
        assert evicted["task_id"] == "t0"

    def test_set_policy_window(self, queue):
        queue.set_policy_window(300)
        assert queue.batch_window_ms == 300

    def test_set_policy_window_negative_clamped(self, queue):
        queue.set_policy_window(-100)
        assert queue.batch_window_ms == 0

    def test_is_empty_property(self, queue):
        assert queue.is_empty is True
        queue.add_result(_make_result("t1"))
        assert queue.is_empty is False
        queue.drain()
        assert queue.is_empty is True

    def test_total_count_includes_queued(self, queue):
        queue.add_result(_make_result("t1"))
        queue.set_front_busy(True)
        queue.add_result(_make_result("t2"))
        assert queue.total_count == 2

    def test_drain_preserves_order(self, queue):
        for i in range(3):
            queue.add_result(_make_result(f"t{i}"))
        results = queue.drain()
        assert [r["task_id"] for r in results] == ["t0", "t1", "t2"]

    def test_multiple_drains(self, queue):
        queue.add_result(_make_result("t1"))
        results1 = queue.drain()
        queue.add_result(_make_result("t2"))
        results2 = queue.drain()
        assert len(results1) == 1
        assert len(results2) == 1
        assert queue.drain_count == 2

    def test_front_busy_then_drain(self, queue):
        queue.set_front_busy(True)
        queue.add_result(_make_result("t1"))
        queue.set_front_busy(False)
        results = queue.drain()
        assert len(results) == 1
        assert results[0]["task_id"] == "t1"


# =====================================================================
# Integration tests: Router + Fallback + Metrics
# =====================================================================


class TestE84Integration:
    """Cross-component integration: router + fallback + metrics."""

    def test_router_fallback_metrics_pipeline(self):
        """Full pipeline: signal -> router -> fallback -> metrics."""
        policy = WeavePolicy()
        router = WeaveIntegrationRouter(policy)
        fallback = WeaveFallbackHandler()
        metrics = WeaveMetricsCollector()

        signal = _make_signal(
            fsm_state=ConciergeState.LISTENING.name,
            user_idle_ms=15_000,
        )

        # Router decides
        routing = router.route_decision(signal)
        assert routing.action == "flush_now"

        # Record in metrics
        metrics.record_decision(routing.decision, latency_ms=45.0)
        assert metrics.weave_count == 1
        assert metrics.immediate_count == 1

    def test_fallback_used_in_metrics(self):
        """Fallback path records correctly in metrics."""
        fallback = WeaveFallbackHandler()
        metrics = WeaveMetricsCollector()

        result = fallback.fallback_decide(ConciergeState.COMPANIONING)
        metrics.record_decision(result, latency_ms=510.0, fallback_used=True)

        assert metrics.fallback_count == 1
        assert metrics.batch_count == 1
        assert metrics.weave_count == 1

    def test_typing_reevaluation_with_queue(self):
        """Typing signal -> re-evaluate -> results stay in queue."""
        policy = WeavePolicy()
        evaluator = TypingPolicyReEvaluator(policy)
        queue = WeaveQueue()

        # Add result
        queue.add_result(_make_result("t1"))

        # User starts typing
        signal = _make_signal(user_typing=True, user_idle_ms=0)
        result = evaluator.on_typing_start(
            signal,
            has_active_timer=True,
        )
        assert result.action == "cancel_timer"

        # Results still in queue
        assert queue.pending_count == 1

        # User stops typing
        signal2 = _make_signal(
            user_typing=False,
            user_idle_ms=5_000,
            pending_count=1,
            fsm_state=ConciergeState.COMPANIONING.name,
        )
        result2 = evaluator.on_typing_stop(
            signal2,
            has_pending_results=True,
        )
        assert result2.action == "restart_timer"

        # Drain and verify
        results = queue.drain()
        assert len(results) == 1

    def test_safe_decide_all_states(self):
        """safe_decide with enabled=True produces valid results for all states."""
        policy = WeavePolicy()
        fallback = WeaveFallbackHandler()

        for state in ConciergeState:
            signal = _make_signal(
                fsm_state=state.name,
                user_idle_ms=15_000,
                pending_count=1,
            )
            result = fallback.safe_decide(
                policy,
                signal,
                state,
                policy_enabled=True,
            )
            assert isinstance(result, WeaveDecisionResult)
            assert result.decision in WeaveDecision

    def test_safe_decide_disabled_all_states(self):
        """safe_decide with enabled=False uses fallback for all states."""
        policy = WeavePolicy()
        fallback = WeaveFallbackHandler()

        for state in ConciergeState:
            signal = _make_signal(fsm_state=state.name)
            result = fallback.safe_decide(
                policy,
                signal,
                state,
                policy_enabled=False,
            )
            assert "fallback" in result.reasoning

    def test_end_to_end_session_metrics(self):
        """Simulate a short session and verify final metrics."""
        policy = WeavePolicy()
        fallback = WeaveFallbackHandler()
        metrics = WeaveMetricsCollector()
        queue = WeaveQueue()

        # 3 results arrive
        for i in range(3):
            queue.add_result(_make_result(f"t{i}"))

        # Decision: BATCH
        signal = _make_signal(
            fsm_state=ConciergeState.COMPANIONING.name,
            user_idle_ms=5_000,
            pending_count=3,
        )
        decision = fallback.safe_decide(
            policy,
            signal,
            ConciergeState.COMPANIONING,
        )
        metrics.record_decision(decision, latency_ms=550.0)

        # 1 result deferred
        dr_defer = WeaveDecisionResult(decision=WeaveDecision.DEFER)
        metrics.record_decision(dr_defer)

        # 1 suppressed
        dr_suppress = WeaveDecisionResult(decision=WeaveDecision.SUPPRESS)
        metrics.record_decision(dr_suppress)

        # User acknowledged 1
        metrics.record_acknowledgement()

        event = metrics.to_event(session_id="test_session")
        assert event["session_id"] == "test_session"
        assert event["weave_count"] == 1
        assert event["defer_count"] == 1
        assert event["suppress_count"] == 1
        assert event["total_delivered"] == 1
        assert event["acknowledged"] == 1
        assert event["user_acknowledged_rate"] == pytest.approx(1.0)
