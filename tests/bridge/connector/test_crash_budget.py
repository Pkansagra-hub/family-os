"""Tests for :mod:`bridge.connector.crash_budget`."""

from __future__ import annotations

from bridge.connector.crash_budget import (
    DEFAULT_CRASH_BUDGET_COUNT,
    DEFAULT_CRASH_BUDGET_WINDOW_S,
    CrashBudget,
)


class TestCrashBudgetSlidingWindow:
    def test_defaults_match_architecture_doc(self) -> None:
        budget = CrashBudget()
        assert budget.count == DEFAULT_CRASH_BUDGET_COUNT
        assert budget.window_s == DEFAULT_CRASH_BUDGET_WINDOW_S

    def test_zero_crashes_is_under_budget(self) -> None:
        budget = CrashBudget(count=3, window_s=60.0)
        assert budget.recent_count(now=100.0) == 0
        assert not budget.is_over_budget(now=100.0)

    def test_below_threshold_stays_under_budget(self) -> None:
        budget = CrashBudget(count=3, window_s=60.0)
        budget.record(now=100.0)
        budget.record(now=110.0)
        assert budget.recent_count(now=120.0) == 2
        assert not budget.is_over_budget(now=120.0)

    def test_at_threshold_triggers_quarantine(self) -> None:
        budget = CrashBudget(count=3, window_s=60.0)
        budget.record(now=100.0)
        budget.record(now=110.0)
        budget.record(now=120.0)
        assert budget.recent_count(now=125.0) == 3
        assert budget.is_over_budget(now=125.0)

    def test_old_crashes_drop_out_of_window(self) -> None:
        budget = CrashBudget(count=3, window_s=60.0)
        budget.record(now=100.0)
        budget.record(now=105.0)
        budget.record(now=110.0)
        # 200s later, all three crashes are outside the 60s window.
        assert budget.recent_count(now=200.0) == 0
        assert not budget.is_over_budget(now=200.0)

    def test_partial_eviction_recovers_from_quarantine(self) -> None:
        budget = CrashBudget(count=3, window_s=60.0)
        budget.record(now=100.0)
        budget.record(now=110.0)
        budget.record(now=120.0)
        assert budget.is_over_budget(now=125.0)
        # By t=170 the first crash (t=100) is outside the 60s window.
        assert budget.recent_count(now=170.0) == 2
        assert not budget.is_over_budget(now=170.0)

    def test_reset_clears_all_crashes(self) -> None:
        budget = CrashBudget(count=3, window_s=60.0)
        budget.record(now=100.0)
        budget.record(now=110.0)
        budget.record(now=120.0)
        assert budget.is_over_budget(now=125.0)
        budget.reset()
        assert budget.recent_count(now=125.0) == 0
        assert not budget.is_over_budget(now=125.0)


class TestCrashBudgetCustomThresholds:
    def test_count_one_quarantines_on_first_crash(self) -> None:
        budget = CrashBudget(count=1, window_s=60.0)
        assert not budget.is_over_budget(now=0.0)
        budget.record(now=0.0)
        assert budget.is_over_budget(now=0.0)

    def test_short_window_evicts_quickly(self) -> None:
        budget = CrashBudget(count=2, window_s=1.0)
        budget.record(now=0.0)
        budget.record(now=0.5)
        assert budget.is_over_budget(now=0.6)
        assert budget.recent_count(now=2.0) == 0
