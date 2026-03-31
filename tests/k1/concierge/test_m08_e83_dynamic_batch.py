"""
Tests for M8 E8.3 -- Dynamic Batch Window + Digest Mode.

Covers:
  - 8.3.1: schedule_weave_flush() dynamic window helper
  - 8.3.2: FSMTurnState DEFER path (mark_deferred, drain_deferred)
  - 8.3.3: DigestPayload dataclass + from_results factory
  - 8.3.4: WEAVE template urgency_label + emotional_context placeholders
  - 8.3.5: sort_results_for_delivery() result ordering

Test count: ~85 tests across 8 test classes.
"""

from __future__ import annotations

import time

import pytest

from k1.concierge.fsm.turn_state import FSMTurnState
from k1.concierge.prompt.mode import PromptMode
from k1.concierge.prompt.scenario_templates import SCENARIO_DATA_TEMPLATES
from k1.concierge.protocols.weave_policy import (
    EMOTIONAL_GATE_OPEN,
    EMOTIONAL_GATE_SUPPRESS_ALL_NON_SAFETY,
    EMOTIONAL_GATE_SUPPRESS_TRIVIAL,
    DigestPayload,
    WeaveDecision,
    WeaveDecisionResult,
    _extract_domain,
    _one_line_summary,
    _result_sort_key,
    generate_emotional_context,
    generate_urgency_label,
    schedule_weave_flush,
    sort_results_for_delivery,
)

# =====================================================================
# Helpers
# =====================================================================


def _make_result(
    task_id: str = "task_1",
    urgency: str = "normal",
    domain: str = "",
    result: dict | None = None,
    queued_at_ns: int = 0,
) -> dict:
    """Create a pending result dict matching FSMTurnState.enqueue_result format."""
    r: dict = {
        "task_id": task_id,
        "result": result or {},
        "envelope_id": f"env_{task_id}",
        "parent_id": f"par_{task_id}",
        "queued_at_ns": queued_at_ns or time.monotonic_ns(),
        "urgency": urgency,
    }
    if domain:
        r["domain"] = domain
    return r


def _make_envelope_stub(envelope_id: str = "env_1", parent_id: str = "par_1"):
    """Minimal envelope stub for turn_state.enqueue_result."""

    class Stub:
        pass

    s = Stub()
    s.envelope_id = envelope_id
    s.parent_id = parent_id
    return s


# =====================================================================
# 8.3.1 -- schedule_weave_flush tests
# =====================================================================


class TestScheduleWeaveFlush:
    """8.3.1: Dynamic batch window scheduling helper."""

    def test_immediate_decision_returns_immediate_mode(self):
        result = WeaveDecisionResult(decision=WeaveDecision.IMMEDIATE, window_ms=0)
        sched = schedule_weave_flush(result)
        assert sched["mode"] == "immediate"
        assert sched["window_ms"] == 0
        assert sched["decision"] == "IMMEDIATE"

    def test_batch_with_positive_window_returns_delayed(self):
        result = WeaveDecisionResult(decision=WeaveDecision.BATCH, window_ms=750)
        sched = schedule_weave_flush(result)
        assert sched["mode"] == "delayed"
        assert sched["window_ms"] == 750
        assert sched["decision"] == "BATCH"

    def test_digest_with_window_returns_delayed(self):
        result = WeaveDecisionResult(decision=WeaveDecision.DIGEST, window_ms=15000)
        sched = schedule_weave_flush(result)
        assert sched["mode"] == "delayed"
        assert sched["window_ms"] == 15000
        assert sched["decision"] == "DIGEST"

    def test_defer_returns_skip(self):
        result = WeaveDecisionResult(decision=WeaveDecision.DEFER, window_ms=0)
        sched = schedule_weave_flush(result)
        assert sched["mode"] == "skip"
        assert sched["decision"] == "DEFER"

    def test_suppress_returns_skip(self):
        result = WeaveDecisionResult(decision=WeaveDecision.SUPPRESS, window_ms=0)
        sched = schedule_weave_flush(result)
        assert sched["mode"] == "skip"
        assert sched["decision"] == "SUPPRESS"

    def test_defer_with_nonzero_window_still_skips(self):
        result = WeaveDecisionResult(decision=WeaveDecision.DEFER, window_ms=500)
        sched = schedule_weave_flush(result)
        assert sched["mode"] == "skip"

    def test_suppress_with_nonzero_window_still_skips(self):
        result = WeaveDecisionResult(decision=WeaveDecision.SUPPRESS, window_ms=100)
        sched = schedule_weave_flush(result)
        assert sched["mode"] == "skip"

    def test_reasoning_is_forwarded(self):
        result = WeaveDecisionResult(
            decision=WeaveDecision.BATCH,
            window_ms=500,
            reasoning="R9: default",
        )
        sched = schedule_weave_flush(result)
        assert sched["reasoning"] == "R9: default"

    def test_batch_zero_window_is_immediate(self):
        result = WeaveDecisionResult(decision=WeaveDecision.BATCH, window_ms=0)
        sched = schedule_weave_flush(result)
        assert sched["mode"] == "immediate"

    def test_digest_zero_window_is_immediate(self):
        result = WeaveDecisionResult(decision=WeaveDecision.DIGEST, window_ms=0)
        sched = schedule_weave_flush(result)
        assert sched["mode"] == "immediate"


# =====================================================================
# 8.3.2 -- DEFER path in FSMTurnState
# =====================================================================


class TestDeferPath:
    """8.3.2: Deferred results management in FSMTurnState."""

    def test_initial_deferred_is_empty(self):
        ts = FSMTurnState()
        assert ts.deferred_results == []
        assert ts.has_deferred_results is False

    def test_mark_deferred_moves_results(self):
        ts = FSMTurnState()
        env = _make_envelope_stub()
        ts.enqueue_result("t1", {"data": 1}, env, urgency="low")
        ts.enqueue_result("t2", {"data": 2}, env, urgency="low")
        assert ts.depth == 2

        force = ts.mark_deferred(max_consecutive_defers=5)
        assert force == []
        assert ts.depth == 0  # pending drained
        assert len(ts.deferred_results) == 2
        assert ts.has_deferred_results is True

    def test_mark_deferred_with_explicit_results(self):
        ts = FSMTurnState()
        items = [_make_result("t1"), _make_result("t2")]
        force = ts.mark_deferred(results=items, max_consecutive_defers=5)
        assert force == []
        assert len(ts.deferred_results) == 2
        assert ts.deferred_results[0]["defer_count"] == 1
        assert ts.deferred_results[0]["deferred"] is True

    def test_mark_deferred_increments_defer_count(self):
        ts = FSMTurnState()
        items = [_make_result("t1")]
        items[0]["defer_count"] = 3
        force = ts.mark_deferred(results=items, max_consecutive_defers=5)
        assert force == []
        assert ts.deferred_results[0]["defer_count"] == 4

    def test_mark_deferred_force_delivers_after_max(self):
        ts = FSMTurnState()
        items = [_make_result("t1")]
        items[0]["defer_count"] = 5  # will become 6, exceeds max of 5
        force = ts.mark_deferred(results=items, max_consecutive_defers=5)
        assert len(force) == 1
        assert force[0]["task_id"] == "t1"
        assert force[0]["defer_count"] == 6
        assert len(ts.deferred_results) == 0

    def test_mark_deferred_mixed_force_and_defer(self):
        ts = FSMTurnState()
        items = [
            _make_result("t1"),  # defer_count will be 1
            _make_result("t2"),  # defer_count will be 6 -> force
        ]
        items[1]["defer_count"] = 5
        force = ts.mark_deferred(results=items, max_consecutive_defers=5)
        assert len(force) == 1
        assert force[0]["task_id"] == "t2"
        assert len(ts.deferred_results) == 1
        assert ts.deferred_results[0]["task_id"] == "t1"

    def test_drain_deferred_returns_and_clears(self):
        ts = FSMTurnState()
        items = [_make_result("t1"), _make_result("t2")]
        ts.mark_deferred(results=items)
        assert ts.has_deferred_results is True

        drained = ts.drain_deferred()
        assert len(drained) == 2
        assert ts.has_deferred_results is False
        assert ts.deferred_results == []

    def test_drain_deferred_empty_returns_empty(self):
        ts = FSMTurnState()
        drained = ts.drain_deferred()
        assert drained == []

    def test_reset_clears_deferred(self):
        ts = FSMTurnState()
        items = [_make_result("t1")]
        ts.mark_deferred(results=items)
        assert ts.has_deferred_results is True

        ts.reset()
        assert ts.has_deferred_results is False
        assert ts.deferred_results == []
        assert ts.depth == 0

    def test_deferred_results_preserve_original_data(self):
        ts = FSMTurnState()
        items = [_make_result("t1", urgency="low", domain="travel")]
        ts.mark_deferred(results=items)
        deferred = ts.deferred_results[0]
        assert deferred["task_id"] == "t1"
        assert deferred["urgency"] == "low"
        assert deferred["domain"] == "travel"
        assert deferred["deferred"] is True
        assert deferred["defer_count"] == 1


# =====================================================================
# 8.3.3 -- DigestPayload tests
# =====================================================================


class TestDigestPayload:
    """8.3.3: DigestPayload dataclass and from_results factory."""

    def test_empty_results_produces_empty_digest(self):
        dp = DigestPayload.from_results([])
        assert dp.result_count == 0
        assert dp.groups == ()
        assert dp.summary_text == "No results to summarize."

    def test_single_result_digest(self):
        results = [
            _make_result(
                "t1",
                urgency="low",
                domain="travel",
                result={"summary": "Hotel booked at Hilton"},
            )
        ]
        dp = DigestPayload.from_results(results)
        assert dp.result_count == 1
        assert len(dp.groups) == 1
        assert dp.groups[0][0] == "travel"
        assert "Hotel booked at Hilton" in dp.summary_text

    def test_multiple_domains_grouped(self):
        results = [
            _make_result("t1", domain="travel", result={"summary": "Flight confirmed"}),
            _make_result("t2", domain="health", result={"summary": "Appointment set"}),
            _make_result("t3", domain="travel", result={"summary": "Hotel booked"}),
        ]
        dp = DigestPayload.from_results(results)
        assert dp.result_count == 3
        # Should have 2 groups: travel (2 items) and health (1 item)
        domains = [g[0] for g in dp.groups]
        assert "travel" in domains
        assert "health" in domains

    def test_critical_domain_sorted_first(self):
        results = [
            _make_result("t1", domain="weather", urgency="low"),
            _make_result("t2", domain="safety", urgency="critical"),
        ]
        dp = DigestPayload.from_results(results)
        # Safety domain (has critical) should come first
        assert dp.groups[0][0] == "safety"

    def test_digest_window_ms_stored(self):
        dp = DigestPayload.from_results([], window_ms=20_000)
        assert dp.total_window_ms == 20_000

    def test_frozen_immutable(self):
        dp = DigestPayload.from_results([])
        with pytest.raises(AttributeError):
            dp.result_count = 5  # type: ignore[misc]

    def test_to_dict_serialization(self):
        results = [
            _make_result("t1", domain="travel", result={"summary": "Booked"}),
        ]
        dp = DigestPayload.from_results(results, window_ms=10_000)
        d = dp.to_dict()
        assert d["result_count"] == 1
        assert d["total_window_ms"] == 10_000
        assert len(d["groups"]) == 1
        assert d["groups"][0]["domain"] == "travel"
        assert isinstance(d["groups"][0]["summaries"], list)

    def test_domain_inferred_from_task_id_prefix(self):
        results = [
            _make_result("travel_hotel_123", result={"summary": "Done"}),
        ]
        dp = DigestPayload.from_results(results)
        assert dp.groups[0][0] == "travel"

    def test_domain_defaults_to_general(self):
        results = [
            _make_result("xyz", result={"summary": "Done"}),
        ]
        dp = DigestPayload.from_results(results)
        assert dp.groups[0][0] == "general"

    def test_summary_text_multiline_for_multi_domain(self):
        results = [
            _make_result("t1", domain="travel", result={"summary": "Flight ok"}),
            _make_result("t2", domain="health", result={"summary": "Appt ok"}),
        ]
        dp = DigestPayload.from_results(results)
        lines = dp.summary_text.strip().split("\n")
        assert len(lines) == 2

    def test_multi_item_domain_shows_count(self):
        results = [
            _make_result("t1", domain="travel", result={"summary": "A"}),
            _make_result("t2", domain="travel", result={"summary": "B"}),
            _make_result("t3", domain="travel", result={"summary": "C"}),
        ]
        dp = DigestPayload.from_results(results)
        assert "3 tasks" in dp.summary_text


# =====================================================================
# 8.3.3 / 8.3.5 -- Domain extraction and sort key helpers
# =====================================================================


class TestDomainExtraction:
    """Helpers: _extract_domain, _one_line_summary, _result_sort_key."""

    def test_explicit_domain_field(self):
        assert _extract_domain({"domain": "Travel"}) == "travel"

    def test_domain_from_result_subdict(self):
        assert _extract_domain({"result": {"domain": "Health"}}) == "health"

    def test_domain_from_task_id_prefix(self):
        assert _extract_domain({"task_id": "travel_hotel_123"}) == "travel"

    def test_domain_fallback_general(self):
        assert _extract_domain({"task_id": "x"}) == "general"

    def test_domain_empty_dict(self):
        assert _extract_domain({}) == "general"

    def test_one_line_summary_from_summary_key(self):
        s = _one_line_summary("t1", {"summary": "Hotel booked"})
        assert s == "Hotel booked"

    def test_one_line_summary_from_description_key(self):
        s = _one_line_summary("t1", {"description": "Flight confirmed"})
        assert s == "Flight confirmed"

    def test_one_line_summary_truncates(self):
        long_val = "A" * 200
        s = _one_line_summary("t1", {"summary": long_val})
        assert len(s) <= 120

    def test_one_line_summary_fallback(self):
        s = _one_line_summary("t1", {})
        assert "t1" in s

    def test_one_line_summary_non_dict(self):
        s = _one_line_summary("t1", "plain string result")
        assert s == "plain string result"

    def test_one_line_summary_none_result(self):
        s = _one_line_summary("t1", None)
        assert "t1" in s

    def test_result_sort_key_critical_first(self):
        crit = _result_sort_key({"urgency": "critical", "domain": "a"})
        norm = _result_sort_key({"urgency": "normal", "domain": "a"})
        low = _result_sort_key({"urgency": "low", "domain": "a"})
        assert crit < norm < low

    def test_result_sort_key_domain_grouping(self):
        a = _result_sort_key({"urgency": "normal", "domain": "alpha"})
        b = _result_sort_key({"urgency": "normal", "domain": "beta"})
        assert a < b  # alpha < beta alphabetically

    def test_result_sort_key_fifo_within_domain(self):
        first = _result_sort_key({"urgency": "normal", "domain": "a", "queued_at_ns": 100})
        second = _result_sort_key({"urgency": "normal", "domain": "a", "queued_at_ns": 200})
        assert first < second


# =====================================================================
# 8.3.5 -- sort_results_for_delivery tests
# =====================================================================


class TestSortResultsForDelivery:
    """8.3.5: Result ordering before weave delivery."""

    def test_empty_list(self):
        assert sort_results_for_delivery([]) == []

    def test_single_result(self):
        results = [_make_result("t1")]
        sorted_r = sort_results_for_delivery(results)
        assert len(sorted_r) == 1

    def test_critical_before_normal(self):
        results = [
            _make_result("t1", urgency="normal"),
            _make_result("t2", urgency="critical"),
        ]
        sorted_r = sort_results_for_delivery(results)
        assert sorted_r[0]["task_id"] == "t2"
        assert sorted_r[1]["task_id"] == "t1"

    def test_critical_before_low(self):
        results = [
            _make_result("t1", urgency="low"),
            _make_result("t2", urgency="critical"),
        ]
        sorted_r = sort_results_for_delivery(results)
        assert sorted_r[0]["task_id"] == "t2"

    def test_domain_grouping(self):
        now = time.monotonic_ns()
        results = [
            _make_result("t1", domain="travel", queued_at_ns=now),
            _make_result("t2", domain="health", queued_at_ns=now + 1),
            _make_result("t3", domain="travel", queued_at_ns=now + 2),
        ]
        sorted_r = sort_results_for_delivery(results)
        # health < travel alphabetically, all normal urgency
        assert sorted_r[0]["domain"] == "health"
        assert sorted_r[1]["domain"] == "travel"
        assert sorted_r[2]["domain"] == "travel"

    def test_fifo_within_domain(self):
        now = time.monotonic_ns()
        results = [
            _make_result("t2", domain="travel", queued_at_ns=now + 100),
            _make_result("t1", domain="travel", queued_at_ns=now),
        ]
        sorted_r = sort_results_for_delivery(results)
        assert sorted_r[0]["task_id"] == "t1"
        assert sorted_r[1]["task_id"] == "t2"

    def test_urgency_trumps_domain(self):
        now = time.monotonic_ns()
        results = [
            _make_result("t1", urgency="low", domain="alpha", queued_at_ns=now),
            _make_result("t2", urgency="critical", domain="zeta", queued_at_ns=now),
        ]
        sorted_r = sort_results_for_delivery(results)
        assert sorted_r[0]["task_id"] == "t2"  # critical first

    def test_does_not_mutate_original(self):
        results = [
            _make_result("t1", urgency="low"),
            _make_result("t2", urgency="critical"),
        ]
        original_order = [r["task_id"] for r in results]
        sort_results_for_delivery(results)
        assert [r["task_id"] for r in results] == original_order

    def test_complex_mixed_ordering(self):
        now = time.monotonic_ns()
        results = [
            _make_result("t1", urgency="low", domain="travel", queued_at_ns=now + 1),
            _make_result("t2", urgency="critical", domain="safety", queued_at_ns=now),
            _make_result("t3", urgency="normal", domain="travel", queued_at_ns=now + 2),
            _make_result("t4", urgency="normal", domain="health", queued_at_ns=now + 3),
            _make_result("t5", urgency="low", domain="weather", queued_at_ns=now + 4),
        ]
        sorted_r = sort_results_for_delivery(results)
        # Expected order: t2 (critical), then normal by domain, then low by domain
        assert sorted_r[0]["task_id"] == "t2"  # critical/safety
        # normals: health before travel (alpha)
        assert sorted_r[1]["task_id"] == "t4"  # normal/health
        assert sorted_r[2]["task_id"] == "t3"  # normal/travel
        # lows: travel before weather (alpha)
        assert sorted_r[3]["task_id"] == "t1"  # low/travel
        assert sorted_r[4]["task_id"] == "t5"  # low/weather


# =====================================================================
# 8.3.4 -- Urgency label and emotional context generators
# =====================================================================


class TestGenerateUrgencyLabel:
    """8.3.4: Urgency label generation for WEAVE template."""

    def test_empty_results_informational(self):
        label = generate_urgency_label([])
        assert "Informational" in label

    def test_critical_result_urgent_label(self):
        results = [_make_result("t1", urgency="critical")]
        label = generate_urgency_label(results)
        assert "URGENT" in label

    def test_urgent_result_urgent_label(self):
        results = [_make_result("t1", urgency="urgent")]
        label = generate_urgency_label(results)
        assert "URGENT" in label

    def test_normal_results_informational(self):
        results = [_make_result("t1", urgency="normal")]
        label = generate_urgency_label(results)
        assert "Informational" in label

    def test_low_results_informational(self):
        results = [_make_result("t1", urgency="low")]
        label = generate_urgency_label(results)
        assert "Informational" in label

    def test_digest_decision_summary_label(self):
        results = [_make_result("t1", urgency="low")]
        label = generate_urgency_label(results, decision=WeaveDecision.DIGEST)
        assert "Summary" in label

    def test_mixed_urgency_uses_critical(self):
        results = [
            _make_result("t1", urgency="low"),
            _make_result("t2", urgency="critical"),
        ]
        label = generate_urgency_label(results)
        assert "URGENT" in label


class TestGenerateEmotionalContext:
    """8.3.4: Emotional context generation for WEAVE template."""

    def test_open_gate_neutral_valence(self):
        ctx = generate_emotional_context(EMOTIONAL_GATE_OPEN, 0.0)
        assert "neutral" in ctx.lower()

    def test_open_gate_positive_valence(self):
        ctx = generate_emotional_context(EMOTIONAL_GATE_OPEN, 0.6)
        assert "positive" in ctx.lower()

    def test_open_gate_slightly_negative(self):
        ctx = generate_emotional_context(EMOTIONAL_GATE_OPEN, -0.3)
        assert "low" in ctx.lower() or "warm" in ctx.lower()

    def test_suppress_trivial_gate(self):
        ctx = generate_emotional_context(EMOTIONAL_GATE_SUPPRESS_TRIVIAL, -0.6)
        assert "negative" in ctx.lower() or "gentle" in ctx.lower()

    def test_suppress_all_gate(self):
        ctx = generate_emotional_context(EMOTIONAL_GATE_SUPPRESS_ALL_NON_SAFETY, -0.9)
        assert "crisis" in ctx.lower()

    def test_affect_band_included_when_negative(self):
        ctx = generate_emotional_context(EMOTIONAL_GATE_OPEN, -0.3, "grief")
        assert "grief" in ctx.lower()

    def test_default_values(self):
        ctx = generate_emotional_context()
        assert "neutral" in ctx.lower()


# =====================================================================
# 8.3.4 -- WEAVE template placeholder tests
# =====================================================================


class TestWeaveTemplatePlaceholders:
    """8.3.4: WEAVE scenario template includes urgency and emotional fields."""

    def test_weave_template_has_urgency_label(self):
        template = SCENARIO_DATA_TEMPLATES[PromptMode.WEAVE]
        assert "{urgency_label}" in template

    def test_weave_template_has_emotional_context(self):
        template = SCENARIO_DATA_TEMPLATES[PromptMode.WEAVE]
        assert "{emotional_context}" in template

    def test_weave_template_still_has_result_count(self):
        template = SCENARIO_DATA_TEMPLATES[PromptMode.WEAVE]
        assert "{result_count}" in template

    def test_weave_template_still_has_results_summary(self):
        template = SCENARIO_DATA_TEMPLATES[PromptMode.WEAVE]
        assert "{results_summary}" in template

    def test_weave_template_still_has_current_thread(self):
        template = SCENARIO_DATA_TEMPLATES[PromptMode.WEAVE]
        assert "{current_thread}" in template

    def test_weave_template_format_with_all_fields(self):
        template = SCENARIO_DATA_TEMPLATES[PromptMode.WEAVE]
        formatted = template.format(
            urgency_label="URGENT -- present prominently",
            emotional_context="User affect is neutral. Standard weave.",
            result_count=2,
            results_summary="Hotel booked. Flight confirmed.",
            current_thread="dinner plans",
        )
        assert "URGENT" in formatted
        assert "neutral" in formatted
        assert "2 background" in formatted
        assert "Hotel booked" in formatted
        assert "dinner plans" in formatted

    def test_weave_template_priority_line_before_content(self):
        template = SCENARIO_DATA_TEMPLATES[PromptMode.WEAVE]
        lines = template.strip().split("\n")
        # Priority line should be early in template (after header)
        priority_idx = next(i for i, line in enumerate(lines) if "urgency_label" in line)
        emotional_idx = next(i for i, line in enumerate(lines) if "emotional_context" in line)
        results_idx = next(i for i, line in enumerate(lines) if "result_count" in line)
        # Priority and emotional guidance come before the results
        assert priority_idx < results_idx
        assert emotional_idx < results_idx

    def test_standard_template_unchanged(self):
        """STANDARD template still has async_results_context for DEFER injection."""
        template = SCENARIO_DATA_TEMPLATES[PromptMode.STANDARD]
        assert "{async_results_context}" in template

    def test_standard_template_no_urgency_label(self):
        """STANDARD template should NOT have urgency_label (that's WEAVE-only)."""
        template = SCENARIO_DATA_TEMPLATES[PromptMode.STANDARD]
        assert "{urgency_label}" not in template


# =====================================================================
# Integration: schedule_weave_flush + WeavePolicy
# =====================================================================


class TestScheduleFlushIntegration:
    """Integration tests: schedule_weave_flush with real WeavePolicy outputs."""

    def test_immediate_from_policy_rule1(self):
        """R1 IMMEDIATE produces immediate flush schedule."""
        from k1.concierge.protocols.weave_policy import WeavePolicy, WeaveSignal

        policy = WeavePolicy()
        signal = WeaveSignal(
            fsm_state="LISTENING",
            user_idle_ms=15000,
            pending_count=1,
        )
        result = policy.decide(signal)
        sched = schedule_weave_flush(result)
        assert sched["mode"] == "immediate"

    def test_batch_from_policy_rule9(self):
        """R9 default BATCH produces delayed flush schedule."""
        from k1.concierge.protocols.weave_policy import WeavePolicy, WeaveSignal

        policy = WeavePolicy()
        signal = WeaveSignal(
            fsm_state="THINKING",
            pending_count=1,
            user_idle_ms=0,
        )
        result = policy.decide(signal)
        sched = schedule_weave_flush(result)
        assert sched["mode"] == "delayed"
        assert sched["window_ms"] == 500  # default batch

    def test_defer_from_policy_rule3(self):
        """R3 DEFER (user typing) produces skip flush schedule."""
        from k1.concierge.protocols.weave_policy import WeavePolicy, WeaveSignal

        policy = WeavePolicy()
        signal = WeaveSignal(
            fsm_state="THINKING",
            user_typing=True,
            pending_count=1,
        )
        result = policy.decide(signal)
        sched = schedule_weave_flush(result)
        assert sched["mode"] == "skip"

    def test_digest_from_policy_rule6(self):
        """R6 DIGEST produces delayed flush with large window."""
        from k1.concierge.protocols.weave_policy import WeavePolicy, WeaveSignal

        policy = WeavePolicy()
        signal = WeaveSignal(
            fsm_state="THINKING",
            pending_count=3,
            pending_urgency_profile={"critical": 0, "normal": 0, "low": 3},
            user_idle_ms=0,
        )
        result = policy.decide(signal)
        sched = schedule_weave_flush(result)
        assert sched["mode"] == "delayed"
        assert sched["window_ms"] == 15000
        assert sched["decision"] == "DIGEST"

    def test_suppress_from_policy_rule4(self):
        """R4 SUPPRESS produces skip flush schedule."""
        from k1.concierge.protocols.weave_policy import WeavePolicy, WeaveSignal

        policy = WeavePolicy()
        signal = WeaveSignal(
            fsm_state="THINKING",
            emotional_gate="suppress_all_non_safety",
            pending_count=1,
        )
        result = policy.decide(signal)
        sched = schedule_weave_flush(result)
        assert sched["mode"] == "skip"
        assert sched["decision"] == "SUPPRESS"
