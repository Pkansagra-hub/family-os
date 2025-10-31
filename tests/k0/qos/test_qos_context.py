"""QoS Context tests - migrated from ward to pytest."""

from __future__ import annotations

import pytest

from k0.qos import QoSBudgetError, QoSContext


class TestQoSContextTightening:
    """Test suite for QoSContext tightening semantics."""

    def test_tighten_fanout_clamps_budget_downward(self, qos_context: QoSContext) -> None:
        """Tightening fanout budget must clamp to smaller value."""
        assert qos_context.fanout_budget == 5
        qos_context.tighten(fanout=3)
        assert qos_context.fanout_budget == 3

    def test_tighten_fanout_ignores_upward_attempts(self, qos_context: QoSContext) -> None:
        """Tightening fanout budget ignores attempts to increase."""
        qos_context.tighten(fanout=3)
        assert qos_context.fanout_budget == 3
        qos_context.tighten(fanout=6)  # Try to increase
        assert qos_context.fanout_budget == 3  # Should be ignored

    def test_tighten_top_k_clamps_budget_downward(self, qos_context: QoSContext) -> None:
        """Tightening top_k budget must clamp to smaller value."""
        assert qos_context.top_k_budget == 8
        qos_context.tighten(top_k=4)
        assert qos_context.top_k_budget == 4

    def test_tighten_top_k_ignores_upward_attempts(self, qos_context: QoSContext) -> None:
        """Tightening top_k budget ignores attempts to increase."""
        qos_context.tighten(top_k=4)
        assert qos_context.top_k_budget == 4
        qos_context.tighten(top_k=10)  # Try to increase
        assert qos_context.top_k_budget == 4  # Should be ignored

    def test_tighten_both_simultaneously(self, qos_context: QoSContext) -> None:
        """Tightening both fanout and top_k in single call."""
        qos_context.tighten(fanout=2, top_k=5)
        assert qos_context.fanout_budget == 2
        assert qos_context.top_k_budget == 5

    def test_tighten_with_negative_fanout_raises_value_error(self, qos_context: QoSContext) -> None:
        """Negative fanout values must raise ValueError."""
        with pytest.raises(ValueError, match="fanout must be non-negative"):
            qos_context.tighten(fanout=-1)

    def test_tighten_with_negative_top_k_raises_value_error(self, qos_context: QoSContext) -> None:
        """Negative top_k values must raise ValueError."""
        with pytest.raises(ValueError, match="top_k must be non-negative"):
            qos_context.tighten(top_k=-1)

    def test_tighten_with_zero_values(self, qos_context: QoSContext) -> None:
        """Zero values are valid and effective (complete tightening)."""
        qos_context.tighten(fanout=0, top_k=0)
        assert qos_context.fanout_budget == 0
        assert qos_context.top_k_budget == 0

    def test_tighten_monotonic_sequence(self, qos_context: QoSContext) -> None:
        """Multiple tightening calls maintain monotonic (non-increasing) property."""
        assert qos_context.fanout_budget == 5
        qos_context.tighten(fanout=4)
        assert qos_context.fanout_budget == 4
        qos_context.tighten(fanout=2)
        assert qos_context.fanout_budget == 2
        qos_context.tighten(fanout=2)  # Same value OK
        assert qos_context.fanout_budget == 2


class TestQoSContextConsumption:
    """Test suite for QoS budget consumption."""

    def test_consume_fanout_single_unit(self, qos_context: QoSContext) -> None:
        """Consuming single fanout unit decrements budget."""
        assert qos_context.fanout_budget == 5
        qos_context.consume_fanout()
        assert qos_context.fanout_budget == 4

    def test_consume_fanout_multiple_units(self, qos_context: QoSContext) -> None:
        """Consuming multiple fanout units decrements budget correctly."""
        qos_context.consume_fanout(2)
        assert qos_context.fanout_budget == 3

    def test_consume_top_k_single_unit(self, qos_context: QoSContext) -> None:
        """Consuming single top_k unit decrements budget."""
        assert qos_context.top_k_budget == 8
        qos_context.consume_top_k()
        assert qos_context.top_k_budget == 7

    def test_consume_top_k_multiple_units(self, qos_context: QoSContext) -> None:
        """Consuming multiple top_k units decrements budget correctly."""
        qos_context.consume_top_k(3)
        assert qos_context.top_k_budget == 5

    def test_consume_fanout_exhaustion_raises_budget_error(self, qos_context: QoSContext) -> None:
        """Consuming more than available fanout raises QoSBudgetError."""
        qos_context.consume_fanout(2)
        assert qos_context.fanout_budget == 3
        with pytest.raises(QoSBudgetError, match="fanout budget exceeded"):
            qos_context.consume_fanout(5)
        # Budget should not change on failed consumption
        assert qos_context.fanout_budget == 3

    def test_consume_top_k_exhaustion_raises_budget_error(self, qos_context: QoSContext) -> None:
        """Consuming more than available top_k raises QoSBudgetError."""
        qos_context.consume_top_k(4)
        assert qos_context.top_k_budget == 4
        with pytest.raises(QoSBudgetError, match="top_k budget exceeded"):
            qos_context.consume_top_k(10)
        # Budget should not change on failed consumption
        assert qos_context.top_k_budget == 4

    def test_consume_negative_fanout_raises_value_error(self, qos_context: QoSContext) -> None:
        """Negative fanout consumption must raise ValueError."""
        with pytest.raises(ValueError, match="fanout must be non-negative"):
            qos_context.consume_fanout(-1)

    def test_consume_negative_top_k_raises_value_error(self, qos_context: QoSContext) -> None:
        """Negative top_k consumption must raise ValueError."""
        with pytest.raises(ValueError, match="top_k must be non-negative"):
            qos_context.consume_top_k(-1)

    def test_consume_exact_budget(self, qos_context: QoSContext) -> None:
        """Consuming exact remaining budget succeeds."""
        qos_context.consume_fanout(5)
        assert qos_context.fanout_budget == 0

    def test_consume_zero_amount(self, qos_context: QoSContext) -> None:
        """Consuming zero units is allowed (no-op)."""
        original = qos_context.fanout_budget
        qos_context.consume_fanout(0)
        assert qos_context.fanout_budget == original


class TestQoSContextSchedulerIntegration:
    """Test suite for QoSContext scheduler integration."""

    def test_acquire_token_from_context(self, qos_context: QoSContext) -> None:
        """QoSContext.acquire() delegates to scheduler."""
        token = qos_context.acquire(band="GREEN", port="command", cost=2)
        assert token is not None
        assert token.port == "command"
        assert token.cost == 2
        assert qos_context.scheduler.active_tokens("command") == 2

    def test_acquire_token_release_frees_capacity(self, qos_context: QoSContext) -> None:
        """Released token frees scheduler capacity."""
        token = qos_context.acquire(band="GREEN", port="query", cost=3)
        assert qos_context.scheduler.active_tokens("query") == 3
        token.release()
        assert qos_context.scheduler.active_tokens("query") == 0

    def test_acquire_multiple_tokens_accumulate(self, qos_context: QoSContext) -> None:
        """Multiple acquired tokens accumulate in scheduler."""
        token1 = qos_context.acquire(band="GREEN", port="command", cost=1)
        token2 = qos_context.acquire(band="GREEN", port="command", cost=2)
        assert qos_context.scheduler.active_tokens("command") == 3
        token1.release()
        assert qos_context.scheduler.active_tokens("command") == 2
        token2.release()
        assert qos_context.scheduler.active_tokens("command") == 0

    def test_acquire_respects_band(self, qos_context: QoSContext) -> None:
        """Acquire accepts band parameter (passed to scheduler)."""
        token = qos_context.acquire(band="AMBER", port="query", cost=1)
        assert token is not None
        token.release()


class TestQoSContextCompositeScenarios:
    """Test suite for composite QoS scenarios."""

    def test_tighten_then_consume_after_tightening(self, qos_context: QoSContext) -> None:
        """Consuming after tightening respects new budget."""
        qos_context.tighten(fanout=2)
        qos_context.consume_fanout(2)
        with pytest.raises(QoSBudgetError):
            qos_context.consume_fanout(1)

    def test_consume_then_tighten_does_not_restore_consumed(self, qos_context: QoSContext) -> None:
        """Tightening after consumption doesn't restore consumed budget."""
        qos_context.consume_fanout(3)
        assert qos_context.fanout_budget == 2
        qos_context.tighten(fanout=5)  # Try to increase
        assert qos_context.fanout_budget == 2  # Remains at 2

    def test_scheduler_capacity_error_during_acquire(self, qos_context_strict: QoSContext) -> None:
        """Scheduler capacity error propagates from acquire."""
        from k0.qos import SchedulerCapacityError

        # Strict scheduler has command port limit of 1, cost 2 exceeds that
        with pytest.raises(SchedulerCapacityError):
            qos_context_strict.acquire(band="GREEN", port="command", cost=2)

    def test_budget_state_after_exception(self, qos_context: QoSContext) -> None:
        """QoS budgets unchanged when exception raised."""
        original_fanout = qos_context.fanout_budget
        try:
            qos_context.consume_fanout(10)
        except QoSBudgetError:
            pass
        assert qos_context.fanout_budget == original_fanout

    def test_idempotent_release(self, qos_context: QoSContext) -> None:
        """Token release is idempotent (can call multiple times safely)."""
        token = qos_context.acquire(band="GREEN", port="command", cost=1)
        token.release()
        assert qos_context.scheduler.active_tokens("command") == 0
        token.release()  # Second release should be no-op
        assert qos_context.scheduler.active_tokens("command") == 0

    def test_context_manager_token_release(self, qos_context: QoSContext) -> None:
        """Token can be used as context manager for auto-release."""
        with qos_context.acquire(band="GREEN", port="command", cost=1) as token:
            assert qos_context.scheduler.active_tokens("command") == 1
        assert qos_context.scheduler.active_tokens("command") == 0

    def test_context_manager_release_on_exception(self, qos_context: QoSContext) -> None:
        """Token released even if exception in context manager."""
        try:
            with qos_context.acquire(band="GREEN", port="command", cost=2) as token:
                assert qos_context.scheduler.active_tokens("command") == 2
                raise ValueError("test exception")
        except ValueError:
            pass
        assert qos_context.scheduler.active_tokens("command") == 0
