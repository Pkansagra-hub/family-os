"""
tests.poc.test_m11_obs_e112 -- E11.2 ReAct Loop & Actor Telemetry

Covers issues 11.2.1 through 11.2.4:
    11.2.1  ReAct loop fallback path structured counters
    11.2.2  Front per-mode quality metrics
    11.2.3  Back per-tier quality metrics
    11.2.4  End-to-end turn latency breakdown (TurnTimer -- tested in E11.1)

Acceptance criteria from v3_milestones.md:
    - Every ReAct loop completion emits a summary metric event
    - Degenerate, budget exhausted, forced-text, cancel, normal paths each
      increment their counter
    - Labels include actor, mode, and tier for filtering
    - Per-mode invocation count, iteration count, tool call count emitted
    - HITL_RELAY with tool calls triggers alert
    - Per-tier invocation count, budget utilization, suspension count emitted
    - Budget utilization histogram enables tier calibration analysis
    - Cancel-to-exit latency tracked for each cancelled task
"""

from __future__ import annotations

from poc.k1_poc.obs.actor_metrics import (
    MODE_EXPECTATIONS,
    TIER_BUDGET_LIMITS,
    BackOutcome,
    FrontOutcome,
    classify_budget_utilization,
    record_back_metrics,
    record_front_metrics,
)
from poc.k1_poc.obs.metrics import MetricsCollector
from poc.k1_poc.obs.react_metrics import (
    ALL_EXIT_PATHS,
    EXIT_BUDGET_EXHAUSTED,
    EXIT_CANCELLED,
    EXIT_DEGENERATE,
    EXIT_FORCED_TEXT,
    EXIT_NORMAL,
    EXIT_SUSPENDED,
    ReactLoopOutcome,
    build_react_loop_summary,
    classify_exit_path,
    record_react_loop_metrics,
)

# =====================================================================
# 11.2.1 -- classify_exit_path
# =====================================================================


class TestClassifyExitPath:
    """Exit path classification from ReactResult status."""

    def test_normal_completion(self) -> None:
        assert classify_exit_path("complete") == EXIT_NORMAL

    def test_degenerate(self) -> None:
        assert classify_exit_path("complete", degenerate_count=1) == EXIT_DEGENERATE

    def test_budget_exhausted(self) -> None:
        assert classify_exit_path("budget_exhausted") == EXIT_BUDGET_EXHAUSTED

    def test_forced_text(self) -> None:
        assert classify_exit_path("complete", forced_text=True) == EXIT_FORCED_TEXT

    def test_cancelled(self) -> None:
        assert classify_exit_path("cancelled") == EXIT_CANCELLED

    def test_suspended(self) -> None:
        assert classify_exit_path("suspended") == EXIT_SUSPENDED

    def test_cancelled_takes_precedence_over_degenerate(self) -> None:
        assert classify_exit_path("cancelled", degenerate_count=3) == EXIT_CANCELLED

    def test_budget_exhausted_takes_precedence_over_forced(self) -> None:
        assert classify_exit_path("budget_exhausted", forced_text=True) == EXIT_BUDGET_EXHAUSTED

    def test_forced_text_takes_precedence_over_degenerate(self) -> None:
        assert (
            classify_exit_path("complete", forced_text=True, degenerate_count=1) == EXIT_FORCED_TEXT
        )

    def test_all_exit_paths_are_strings(self) -> None:
        for path in ALL_EXIT_PATHS:
            assert isinstance(path, str)

    def test_all_paths_covered(self) -> None:
        assert len(ALL_EXIT_PATHS) == 6


# =====================================================================
# 11.2.1 -- record_react_loop_metrics
# =====================================================================


class TestRecordReactLoopMetrics:
    """ReAct loop structured metrics emission."""

    def _mc(self) -> MetricsCollector:
        return MetricsCollector(session_id="s1")

    def test_normal_front_completion(self) -> None:
        mc = self._mc()
        outcome = ReactLoopOutcome(
            actor="front",
            status="complete",
            iterations_used=3,
            iterations_budget=6,
            tool_calls_total=5,
            parallel_tool_calls=2,
            sequential_tool_calls=3,
            duration_ms=1500.0,
            mode="STANDARD",
            dispatched_tasks=1,
            has_text=True,
        )
        record_react_loop_metrics(mc, outcome)

        # Completion count by exit path
        assert (
            mc.get_counter(
                "react_loop.front.completion_count",
                {"actor": "front", "mode": "STANDARD", "exit_path": "normal"},
            )
            == 1.0
        )

        # Normal completion counter
        assert (
            mc.get_counter(
                "react_loop.front.normal_completion_count",
                {"actor": "front", "mode": "STANDARD"},
            )
            == 1.0
        )

        # Iteration histogram
        hist = mc.get_histogram(
            "react_loop.front.iteration_count",
            {"actor": "front", "mode": "STANDARD"},
        )
        assert hist == [3.0]

        # Utilization histogram
        util = mc.get_histogram(
            "react_loop.front.iteration_utilization",
            {"actor": "front", "mode": "STANDARD"},
        )
        assert util == [0.5]

        # Tool calls
        assert mc.get_histogram(
            "react_loop.front.tool_call_count",
            {"actor": "front", "mode": "STANDARD"},
        ) == [5.0]

        # Duration
        assert mc.get_histogram(
            "react_loop.front.duration_ms",
            {"actor": "front", "mode": "STANDARD"},
        ) == [1500.0]

        # Dispatched tasks
        assert mc.get_histogram(
            "react_loop.front.dispatched_task_count",
            {"actor": "front", "mode": "STANDARD"},
        ) == [1.0]

    def test_degenerate_exit(self) -> None:
        mc = self._mc()
        outcome = ReactLoopOutcome(
            actor="front",
            status="complete",
            degenerate_count=2,
            iterations_used=6,
            iterations_budget=6,
            mode="STANDARD",
        )
        record_react_loop_metrics(mc, outcome)

        assert (
            mc.get_counter(
                "react_loop.front.completion_count",
                {"actor": "front", "mode": "STANDARD", "exit_path": "degenerate"},
            )
            == 1.0
        )
        # Degenerate counter incremented twice: once from exit path, once from count > 0
        assert (
            mc.get_counter(
                "react_loop.front.degenerate_count",
                {"actor": "front", "mode": "STANDARD"},
            )
            >= 1.0
        )

    def test_budget_exhausted_exit(self) -> None:
        mc = self._mc()
        outcome = ReactLoopOutcome(
            actor="back",
            status="budget_exhausted",
            iterations_used=8,
            iterations_budget=8,
            tier="MEDIUM",
        )
        record_react_loop_metrics(mc, outcome)

        assert (
            mc.get_counter(
                "react_loop.back.completion_count",
                {"actor": "back", "tier": "MEDIUM", "exit_path": "budget_exhausted"},
            )
            == 1.0
        )
        assert (
            mc.get_counter(
                "react_loop.back.budget_exhausted_count",
                {"actor": "back", "tier": "MEDIUM"},
            )
            == 1.0
        )

    def test_cancelled_exit(self) -> None:
        mc = self._mc()
        outcome = ReactLoopOutcome(
            actor="back",
            status="cancelled",
            iterations_used=2,
            iterations_budget=8,
            tier="MEDIUM",
        )
        record_react_loop_metrics(mc, outcome)

        assert (
            mc.get_counter(
                "react_loop.back.cancel_exit_count",
                {"actor": "back", "tier": "MEDIUM"},
            )
            == 1.0
        )

    def test_suspended_exit(self) -> None:
        mc = self._mc()
        outcome = ReactLoopOutcome(
            actor="back",
            status="suspended",
            iterations_used=3,
            iterations_budget=8,
            tier="HIGH",
        )
        record_react_loop_metrics(mc, outcome)

        assert (
            mc.get_counter(
                "react_loop.back.suspended_count",
                {"actor": "back", "tier": "HIGH"},
            )
            == 1.0
        )

    def test_forced_text_exit(self) -> None:
        mc = self._mc()
        outcome = ReactLoopOutcome(
            actor="front",
            status="complete",
            forced_text=True,
            iterations_used=6,
            iterations_budget=6,
            mode="STANDARD",
        )
        record_react_loop_metrics(mc, outcome)

        assert (
            mc.get_counter(
                "react_loop.front.forced_text_count",
                {"actor": "front", "mode": "STANDARD"},
            )
            == 1.0
        )

    def test_validator_rejection_count(self) -> None:
        mc = self._mc()
        outcome = ReactLoopOutcome(
            actor="front",
            status="complete",
            validator_rejections=3,
            iterations_used=4,
            iterations_budget=6,
            mode="STANDARD",
        )
        record_react_loop_metrics(mc, outcome)

        assert (
            mc.get_counter(
                "react_loop.front.validator_rejection_count",
                {"actor": "front", "mode": "STANDARD"},
            )
            == 3.0
        )

    def test_disabled_collector_noop(self) -> None:
        mc = MetricsCollector(session_id="s1", enabled=False)
        outcome = ReactLoopOutcome(actor="front", status="complete")
        record_react_loop_metrics(mc, outcome)
        assert mc.pending_count() == 0

    def test_none_collector_noop(self) -> None:
        # Should not raise
        outcome = ReactLoopOutcome(actor="front", status="complete")
        record_react_loop_metrics(None, outcome)  # type: ignore[arg-type]

    def test_parallel_sequential_tool_calls(self) -> None:
        mc = self._mc()
        outcome = ReactLoopOutcome(
            actor="front",
            status="complete",
            parallel_tool_calls=3,
            sequential_tool_calls=2,
            tool_calls_total=5,
            iterations_used=2,
            iterations_budget=6,
            mode="STANDARD",
        )
        record_react_loop_metrics(mc, outcome)

        assert mc.get_histogram(
            "react_loop.front.parallel_tool_calls",
            {"actor": "front", "mode": "STANDARD"},
        ) == [3.0]
        assert mc.get_histogram(
            "react_loop.front.sequential_tool_calls",
            {"actor": "front", "mode": "STANDARD"},
        ) == [2.0]

    def test_zero_duration_not_emitted(self) -> None:
        mc = self._mc()
        outcome = ReactLoopOutcome(
            actor="front",
            status="complete",
            duration_ms=0.0,
            iterations_used=1,
            iterations_budget=6,
            mode="STANDARD",
        )
        record_react_loop_metrics(mc, outcome)

        assert (
            mc.get_histogram(
                "react_loop.front.duration_ms",
                {"actor": "front", "mode": "STANDARD"},
            )
            == []
        )

    def test_zero_budget_no_utilization(self) -> None:
        mc = self._mc()
        outcome = ReactLoopOutcome(
            actor="front",
            status="complete",
            iterations_used=0,
            iterations_budget=0,
            mode="STANDARD",
        )
        record_react_loop_metrics(mc, outcome)

        # No utilization histogram when budget is 0
        assert (
            mc.get_histogram(
                "react_loop.front.iteration_utilization",
                {"actor": "front", "mode": "STANDARD"},
            )
            == []
        )

    def test_explicit_exit_path_overrides_classification(self) -> None:
        mc = self._mc()
        outcome = ReactLoopOutcome(
            actor="front",
            status="complete",
            exit_path="forced_text",
            degenerate_count=0,
            iterations_used=6,
            iterations_budget=6,
            mode="STANDARD",
        )
        record_react_loop_metrics(mc, outcome)

        assert (
            mc.get_counter(
                "react_loop.front.completion_count",
                {"actor": "front", "mode": "STANDARD", "exit_path": "forced_text"},
            )
            == 1.0
        )


# =====================================================================
# 11.2.1 -- build_react_loop_summary
# =====================================================================


class TestBuildReactLoopSummary:
    """Structured summary for bus emission."""

    def test_summary_keys(self) -> None:
        outcome = ReactLoopOutcome(
            actor="front",
            status="complete",
            iterations_used=3,
            iterations_budget=6,
            tool_calls_total=5,
            parallel_tool_calls=2,
            sequential_tool_calls=3,
            duration_ms=1500.0,
            mode="STANDARD",
            dispatched_tasks=1,
        )
        summary = build_react_loop_summary(outcome)

        assert summary["metric_name"] == "react_loop.summary"
        assert summary["actor"] == "front"
        assert summary["mode"] == "STANDARD"
        assert summary["iterations_used"] == 3
        assert summary["iterations_budget"] == 6
        assert summary["tool_calls"] == 5
        assert summary["exit_path"] == "normal"
        assert summary["duration_ms"] == 1500.0

    def test_summary_with_degenerate(self) -> None:
        outcome = ReactLoopOutcome(
            actor="front",
            status="complete",
            degenerate_count=2,
            iterations_used=6,
            iterations_budget=6,
        )
        summary = build_react_loop_summary(outcome)
        assert summary["exit_path"] == "degenerate"
        assert summary["degenerate_count"] == 2

    def test_summary_with_explicit_exit_path(self) -> None:
        outcome = ReactLoopOutcome(
            actor="back",
            status="suspended",
            exit_path="suspended",
        )
        summary = build_react_loop_summary(outcome)
        assert summary["exit_path"] == "suspended"


# =====================================================================
# 11.2.2 -- record_front_metrics (per-mode)
# =====================================================================


class TestRecordFrontMetrics:
    """Front actor per-mode quality metrics."""

    def _mc(self) -> MetricsCollector:
        return MetricsCollector(session_id="s1")

    def test_standard_mode_metrics(self) -> None:
        mc = self._mc()
        outcome = FrontOutcome(
            mode="STANDARD",
            status="complete",
            iterations_used=3,
            iterations_budget=6,
            tool_call_count=4,
            dispatched_tasks=1,
            duration_ms=2000.0,
        )
        alerts = record_front_metrics(mc, outcome)

        # Invocation count
        assert mc.get_counter("front.mode.invocation_count", {"mode": "STANDARD"}) == 1.0

        # Iterations used
        assert mc.get_histogram("front.mode.iterations_used", {"mode": "STANDARD"}) == [3.0]

        # Tool calls
        assert mc.get_histogram("front.mode.tool_calls", {"mode": "STANDARD"}) == [4.0]

        # Dispatched tasks
        assert mc.get_histogram("front.mode.dispatched_tasks", {"mode": "STANDARD"}) == [1.0]

        # Duration
        assert mc.get_histogram("front.mode.duration_ms", {"mode": "STANDARD"}) == [2000.0]

        # Utilization
        util = mc.get_histogram("front.mode.iteration_utilization", {"mode": "STANDARD"})
        assert util == [0.5]

        # No alerts for normal STANDARD
        assert alerts == []

    def test_hitl_relay_tool_call_alert(self) -> None:
        mc = self._mc()
        outcome = FrontOutcome(
            mode="HITL_RELAY",
            status="complete",
            iterations_used=1,
            iterations_budget=1,
            tool_call_count=2,  # Should be 0!
        )
        alerts = record_front_metrics(mc, outcome)

        # Alert triggered for tool calls > 0 in HITL_RELAY
        assert len(alerts) >= 1
        tool_alert = [a for a in alerts if "excess_tool_calls" in a["rule"]]
        assert len(tool_alert) == 1
        assert tool_alert[0]["mode"] == "HITL_RELAY"
        assert tool_alert[0]["actual_tools"] == 2
        assert tool_alert[0]["expected_max_tools"] == 0

    def test_hitl_relay_no_tools_no_alert(self) -> None:
        mc = self._mc()
        outcome = FrontOutcome(
            mode="HITL_RELAY",
            status="complete",
            iterations_used=1,
            iterations_budget=1,
            tool_call_count=0,
        )
        alerts = record_front_metrics(mc, outcome)
        assert alerts == []

    def test_weave_mode(self) -> None:
        mc = self._mc()
        outcome = FrontOutcome(
            mode="WEAVE",
            status="complete",
            iterations_used=2,
            iterations_budget=3,
            tool_call_count=1,
        )
        alerts = record_front_metrics(mc, outcome)
        assert mc.get_counter("front.mode.invocation_count", {"mode": "WEAVE"}) == 1.0
        assert alerts == []

    def test_present_excess_iterations_alert(self) -> None:
        mc = self._mc()
        outcome = FrontOutcome(
            mode="PRESENT",
            status="complete",
            iterations_used=5,
            iterations_budget=6,
            tool_call_count=1,
        )
        alerts = record_front_metrics(mc, outcome)

        iter_alert = [a for a in alerts if "excess_iterations" in a["rule"]]
        assert len(iter_alert) == 1
        assert iter_alert[0]["actual_iters"] == 5

    def test_degenerate_count_per_mode(self) -> None:
        mc = self._mc()
        outcome = FrontOutcome(
            mode="STANDARD",
            status="complete",
            degenerate_count=3,
            iterations_used=6,
            iterations_budget=6,
        )
        record_front_metrics(mc, outcome)

        assert mc.get_counter("front.mode.degenerate_count", {"mode": "STANDARD"}) == 3.0

    def test_multiple_modes_tracked_separately(self) -> None:
        mc = self._mc()

        record_front_metrics(
            mc,
            FrontOutcome(
                mode="STANDARD", status="complete", iterations_used=3, iterations_budget=6
            ),
        )
        record_front_metrics(
            mc,
            FrontOutcome(mode="WEAVE", status="complete", iterations_used=1, iterations_budget=3),
        )

        assert mc.get_counter("front.mode.invocation_count", {"mode": "STANDARD"}) == 1.0
        assert mc.get_counter("front.mode.invocation_count", {"mode": "WEAVE"}) == 1.0

    def test_disabled_collector_noop(self) -> None:
        mc = MetricsCollector(session_id="s1", enabled=False)
        outcome = FrontOutcome(mode="STANDARD", status="complete")
        alerts = record_front_metrics(mc, outcome)
        assert alerts == []
        assert mc.pending_count() == 0

    def test_none_collector_noop(self) -> None:
        outcome = FrontOutcome(mode="STANDARD", status="complete")
        alerts = record_front_metrics(None, outcome)  # type: ignore[arg-type]
        assert alerts == []

    def test_unknown_mode_no_expectations(self) -> None:
        mc = self._mc()
        outcome = FrontOutcome(
            mode="CUSTOM_MODE",
            status="complete",
            iterations_used=10,
            tool_call_count=20,
            iterations_budget=10,
        )
        alerts = record_front_metrics(mc, outcome)
        # No mode expectations -> no alerts
        assert alerts == []
        assert mc.get_counter("front.mode.invocation_count", {"mode": "CUSTOM_MODE"}) == 1.0

    def test_mode_expectations_all_defined(self) -> None:
        """All expected modes have expectations defined."""
        expected_modes = {
            "HITL_RELAY",
            "HITL_RESOLVE",
            "WEAVE",
            "PRESENT",
            "STANDARD",
            "INTERRUPT",
            "ERROR",
            "CANCEL",
        }
        assert expected_modes == set(MODE_EXPECTATIONS.keys())

    def test_zero_duration_not_emitted(self) -> None:
        mc = self._mc()
        outcome = FrontOutcome(mode="STANDARD", status="complete", duration_ms=0.0)
        record_front_metrics(mc, outcome)
        assert mc.get_histogram("front.mode.duration_ms", {"mode": "STANDARD"}) == []

    def test_zero_dispatched_tasks_not_emitted(self) -> None:
        mc = self._mc()
        outcome = FrontOutcome(mode="STANDARD", status="complete", dispatched_tasks=0)
        record_front_metrics(mc, outcome)
        assert mc.get_histogram("front.mode.dispatched_tasks", {"mode": "STANDARD"}) == []


# =====================================================================
# 11.2.3 -- record_back_metrics (per-tier)
# =====================================================================


class TestRecordBackMetrics:
    """Back actor per-tier quality metrics."""

    def _mc(self) -> MetricsCollector:
        return MetricsCollector(session_id="s1")

    def test_low_tier_normal(self) -> None:
        mc = self._mc()
        outcome = BackOutcome(
            tier="LOW",
            status="complete",
            iterations_used=2,
            budget_limit=4,
            tool_call_count=3,
            duration_ms=1000.0,
        )
        alerts = record_back_metrics(mc, outcome)

        assert mc.get_counter("back.tier.invocation_count", {"tier": "LOW"}) == 1.0
        assert mc.get_histogram("back.tier.iterations_used", {"tier": "LOW"}) == [2.0]
        assert mc.get_histogram("back.tier.budget_utilization", {"tier": "LOW"}) == [0.5]
        assert mc.get_histogram("back.tier.tool_calls", {"tier": "LOW"}) == [3.0]
        assert mc.get_histogram("back.tier.duration_ms", {"tier": "LOW"}) == [1000.0]
        assert alerts == []

    def test_medium_tier_budget_exhaustion_alert(self) -> None:
        mc = self._mc()
        outcome = BackOutcome(
            tier="MEDIUM",
            status="budget_exhausted",
            iterations_used=8,
            budget_limit=8,
        )
        alerts = record_back_metrics(mc, outcome)

        # Budget utilization = 1.0
        assert mc.get_histogram("back.tier.budget_utilization", {"tier": "MEDIUM"}) == [1.0]

        # Alert triggered
        assert len(alerts) == 1
        assert alerts[0]["rule"] == "back.tier.budget_exhaustion"
        assert alerts[0]["tier"] == "MEDIUM"
        assert alerts[0]["utilization"] == 1.0

    def test_high_tier_suspension(self) -> None:
        mc = self._mc()
        outcome = BackOutcome(
            tier="HIGH",
            status="suspended",
            iterations_used=3,
            budget_limit=12,
        )
        alerts = record_back_metrics(mc, outcome)

        assert mc.get_counter("back.tier.suspension_count", {"tier": "HIGH"}) == 1.0
        assert alerts == []

    def test_cancel_to_exit_latency(self) -> None:
        mc = self._mc()
        outcome = BackOutcome(
            tier="MEDIUM",
            status="cancelled",
            iterations_used=2,
            budget_limit=8,
            cancel_to_exit_ms=5000.0,
        )
        alerts = record_back_metrics(mc, outcome)

        latency = mc.get_histogram("back.tier.cancel_to_exit_latency_ms", {"tier": "MEDIUM"})
        assert latency == [5000.0]

    def test_cancel_without_latency_not_emitted(self) -> None:
        mc = self._mc()
        outcome = BackOutcome(
            tier="LOW",
            status="cancelled",
            cancel_to_exit_ms=0.0,
        )
        record_back_metrics(mc, outcome)

        assert mc.get_histogram("back.tier.cancel_to_exit_latency_ms", {"tier": "LOW"}) == []

    def test_budget_limit_defaults_to_tier(self) -> None:
        mc = self._mc()
        outcome = BackOutcome(
            tier="HIGH",
            status="complete",
            iterations_used=6,
            budget_limit=0,  # Will default to TIER_BUDGET_LIMITS["HIGH"] = 400 (P3.2)
        )
        alerts = record_back_metrics(mc, outcome)

        util = mc.get_histogram("back.tier.budget_utilization", {"tier": "HIGH"})
        assert abs(util[0] - 6 / 400) < 1e-9

    def test_multiple_tiers_tracked_separately(self) -> None:
        mc = self._mc()

        record_back_metrics(
            mc, BackOutcome(tier="LOW", status="complete", iterations_used=2, budget_limit=4)
        )
        record_back_metrics(
            mc, BackOutcome(tier="HIGH", status="complete", iterations_used=6, budget_limit=12)
        )

        assert mc.get_counter("back.tier.invocation_count", {"tier": "LOW"}) == 1.0
        assert mc.get_counter("back.tier.invocation_count", {"tier": "HIGH"}) == 1.0

    def test_disabled_collector_noop(self) -> None:
        mc = MetricsCollector(session_id="s1", enabled=False)
        outcome = BackOutcome(tier="LOW", status="complete")
        alerts = record_back_metrics(mc, outcome)
        assert alerts == []
        assert mc.pending_count() == 0

    def test_none_collector_noop(self) -> None:
        outcome = BackOutcome(tier="LOW", status="complete")
        alerts = record_back_metrics(None, outcome)  # type: ignore[arg-type]
        assert alerts == []

    def test_non_suspended_no_suspension_count(self) -> None:
        mc = self._mc()
        outcome = BackOutcome(tier="LOW", status="complete", iterations_used=2, budget_limit=4)
        record_back_metrics(mc, outcome)
        assert mc.get_counter("back.tier.suspension_count", {"tier": "LOW"}) == 0.0

    def test_near_exhaustion_no_alert(self) -> None:
        """Budget utilization 0.875 (near exhaustion) but < 1.0: no alert."""
        mc = self._mc()
        outcome = BackOutcome(
            tier="MEDIUM",
            status="complete",
            iterations_used=7,
            budget_limit=8,
        )
        alerts = record_back_metrics(mc, outcome)
        assert alerts == []
        util = mc.get_histogram("back.tier.budget_utilization", {"tier": "MEDIUM"})
        assert util == [0.875]


# =====================================================================
# 11.2.3 -- classify_budget_utilization
# =====================================================================


class TestClassifyBudgetUtilization:
    """Budget utilization classification."""

    def test_under(self) -> None:
        assert classify_budget_utilization(0.1) == "under"
        assert classify_budget_utilization(0.0) == "under"
        assert classify_budget_utilization(0.29) == "under"

    def test_healthy(self) -> None:
        assert classify_budget_utilization(0.3) == "healthy"
        assert classify_budget_utilization(0.5) == "healthy"
        assert classify_budget_utilization(0.79) == "healthy"

    def test_near_exhaustion(self) -> None:
        assert classify_budget_utilization(0.8) == "near_exhaustion"
        assert classify_budget_utilization(0.9) == "near_exhaustion"
        assert classify_budget_utilization(0.99) == "near_exhaustion"

    def test_exhausted(self) -> None:
        assert classify_budget_utilization(1.0) == "exhausted"
        assert classify_budget_utilization(1.1) == "exhausted"

    def test_tier_budget_limits_defined(self) -> None:
        assert TIER_BUDGET_LIMITS["simple"] == 400
        assert TIER_BUDGET_LIMITS["plan"] == 400
        assert TIER_BUDGET_LIMITS["crisis"] == 400
        # Legacy aliases kept until P3.3
        assert TIER_BUDGET_LIMITS["LOW"] == 400
        assert TIER_BUDGET_LIMITS["MEDIUM"] == 400
        assert TIER_BUDGET_LIMITS["HIGH"] == 400


# =====================================================================
# Package import test
# =====================================================================


class TestE112PackageImport:
    """Verify obs package exports E11.2 symbols."""

    def test_import_react_metrics(self) -> None:
        from poc.k1_poc.obs import (
            ReactLoopOutcome,
            classify_exit_path,
            record_react_loop_metrics,
        )

        assert ReactLoopOutcome is not None
        assert classify_exit_path is not None
        assert record_react_loop_metrics is not None

    def test_import_actor_metrics(self) -> None:
        from poc.k1_poc.obs import (
            BackOutcome,
            FrontOutcome,
            classify_budget_utilization,
            record_back_metrics,
            record_front_metrics,
        )

        assert FrontOutcome is not None
        assert BackOutcome is not None
        assert record_front_metrics is not None
        assert record_back_metrics is not None
        assert classify_budget_utilization is not None


# =====================================================================
# E2E: React loop -> Front -> Back metric chain
# =====================================================================


class TestE2EMetricChain:
    """End-to-end metric chain: react_loop + front + back in one session."""

    def test_full_turn_metrics(self) -> None:
        mc = MetricsCollector(session_id="s1")
        mc.turn_number = 1

        # Simulate front react_loop completion
        front_react = ReactLoopOutcome(
            actor="front",
            status="complete",
            iterations_used=3,
            iterations_budget=6,
            tool_calls_total=4,
            parallel_tool_calls=2,
            sequential_tool_calls=2,
            mode="STANDARD",
            duration_ms=2000.0,
            dispatched_tasks=1,
        )
        record_react_loop_metrics(mc, front_react)

        # Simulate front per-mode metrics
        front_out = FrontOutcome(
            mode="STANDARD",
            status="complete",
            iterations_used=3,
            iterations_budget=6,
            tool_call_count=4,
            dispatched_tasks=1,
            duration_ms=2000.0,
        )
        record_front_metrics(mc, front_out)

        # Simulate back react_loop completion
        back_react = ReactLoopOutcome(
            actor="back",
            status="complete",
            iterations_used=5,
            iterations_budget=8,
            tool_calls_total=6,
            tier="MEDIUM",
            duration_ms=8000.0,
        )
        record_react_loop_metrics(mc, back_react)

        # Simulate back per-tier metrics
        back_out = BackOutcome(
            tier="MEDIUM",
            status="complete",
            iterations_used=5,
            budget_limit=8,
            tool_call_count=6,
            duration_ms=8000.0,
        )
        record_back_metrics(mc, back_out)

        # Verify session snapshot has all metric families
        snap = mc.snapshot()

        # Should have counters for both actors
        assert any("react_loop.front" in k for k in snap["counters"])
        assert any("react_loop.back" in k for k in snap["counters"])
        assert any("front.mode" in k for k in snap["counters"])
        assert any("back.tier" in k for k in snap["counters"])

        # Should have histograms for both actors
        assert any("react_loop.front" in k for k in snap["histograms"])
        assert any("react_loop.back" in k for k in snap["histograms"])
        assert any("front.mode" in k for k in snap["histograms"])
        assert any("back.tier" in k for k in snap["histograms"])

        # Pending envelopes accumulated
        assert mc.pending_count() > 0

    def test_multiple_turns(self) -> None:
        mc = MetricsCollector(session_id="s1")

        for turn in range(3):
            mc.turn_number = turn + 1
            record_react_loop_metrics(
                mc,
                ReactLoopOutcome(
                    actor="front",
                    status="complete",
                    iterations_used=2,
                    iterations_budget=6,
                    mode="STANDARD",
                ),
            )
            record_front_metrics(
                mc,
                FrontOutcome(
                    mode="STANDARD",
                    status="complete",
                    iterations_used=2,
                    iterations_budget=6,
                ),
            )

        # 3 turns -> 3 invocations
        assert mc.get_counter("front.mode.invocation_count", {"mode": "STANDARD"}) == 3.0
        assert (
            mc.get_counter(
                "react_loop.front.completion_count",
                {"actor": "front", "mode": "STANDARD", "exit_path": "normal"},
            )
            == 3.0
        )
