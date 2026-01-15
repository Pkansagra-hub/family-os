"""
Tests for P03 QoS Integration (Issue 1.3.6).

Validates:
1. P03QoSIntegration token lifecycle (acquire/release)
2. Budget enforcement (fanout_budget, top_k_budget)
3. Error handling for capacity/budget exhaustion
4. Context manager protocol
5. P03QoSSnapshot capture
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from k0.pipelines.p03.context import (
    BackpressureAction,
    P03BudgetExhaustedError,
    P03CapacityError,
    P03QoSError,
    P03QoSIntegration,
    P03QoSSnapshot,
)

# ============================================================
# Fixtures
# ============================================================


@dataclass
class MockSchedulerToken:
    """Mock scheduler token for testing."""

    released: bool = False

    def release(self) -> None:
        self.released = True


class MockScheduler:
    """Mock scheduler for testing."""

    def __init__(self, should_fail: bool = False, limit: int = 100):
        self.should_fail = should_fail
        self.limit = limit
        self.acquire_calls: list[dict] = []
        self.last_token: MockSchedulerToken | None = None

    def acquire(self, *, band: str, port: str, cost: int) -> MockSchedulerToken:
        self.acquire_calls.append({"band": band, "port": port, "cost": cost})

        if self.should_fail:
            from k0.qos import SchedulerCapacityError

            raise SchedulerCapacityError(band=band, port=port, cost=cost, limit=self.limit)

        self.last_token = MockSchedulerToken()
        return self.last_token


@pytest.fixture
def mock_scheduler() -> MockScheduler:
    """Create a mock scheduler."""
    return MockScheduler()


@pytest.fixture
def failing_scheduler() -> MockScheduler:
    """Create a scheduler that always fails capacity check."""
    return MockScheduler(should_fail=True, limit=10)


@pytest.fixture
def qos_integration(mock_scheduler: MockScheduler) -> P03QoSIntegration:
    """Create a P03QoSIntegration with mock scheduler."""
    return P03QoSIntegration(scheduler=mock_scheduler)


@pytest.fixture
def qos_no_scheduler() -> P03QoSIntegration:
    """Create a P03QoSIntegration without scheduler (unbounded mode)."""
    return P03QoSIntegration(scheduler=None)


# ============================================================
# P03QoSIntegration Initialization Tests
# ============================================================


class TestP03QoSIntegrationInit:
    """Test P03QoSIntegration initialization."""

    def test_default_values(self):
        """Default values are set correctly."""
        qos = P03QoSIntegration()

        assert qos.scheduler is None
        assert qos.port == "command"
        assert qos.default_band == "GREEN"
        assert qos.default_fanout_budget == 1000
        assert qos.default_top_k_budget == 500
        assert qos.fanout_budget == 1000
        assert qos.top_k_budget == 500
        assert not qos.has_active_token

    def test_custom_values(self, mock_scheduler: MockScheduler):
        """Custom values override defaults."""
        qos = P03QoSIntegration(
            scheduler=mock_scheduler,
            port="query",
            default_band="AMBER",
            default_fanout_budget=500,
            default_top_k_budget=200,
        )

        assert qos.scheduler is mock_scheduler
        assert qos.port == "query"
        assert qos.default_band == "AMBER"
        assert qos.fanout_budget == 500
        assert qos.top_k_budget == 200


# ============================================================
# Token Lifecycle Tests
# ============================================================


class TestTokenLifecycle:
    """Test scheduler token acquire/release lifecycle."""

    def test_acquire_token_success(self, qos_integration: P03QoSIntegration):
        """Token acquisition succeeds with valid parameters."""
        token = qos_integration.acquire_batch_token(batch_size=50, band="GREEN")

        assert token is not None
        assert qos_integration.has_active_token
        assert not token.released

        # Verify scheduler was called correctly
        scheduler = qos_integration.scheduler
        assert len(scheduler.acquire_calls) == 1
        call = scheduler.acquire_calls[0]
        assert call["band"] == "GREEN"
        assert call["port"] == "command"
        assert call["cost"] == 5  # 50 * 0.1 = 5

    def test_acquire_uses_default_band(self, qos_integration: P03QoSIntegration):
        """Token acquisition uses default band when not specified."""
        qos_integration.acquire_batch_token(batch_size=100)

        call = qos_integration.scheduler.acquire_calls[0]
        assert call["band"] == "GREEN"

    def test_acquire_custom_cost_multiplier(self, qos_integration: P03QoSIntegration):
        """Custom cost multiplier affects calculated cost."""
        qos_integration.acquire_batch_token(batch_size=100, cost_multiplier=0.5)

        call = qos_integration.scheduler.acquire_calls[0]
        assert call["cost"] == 50  # 100 * 0.5 = 50

    def test_acquire_minimum_cost_is_one(self, qos_integration: P03QoSIntegration):
        """Minimum cost is 1 even for small batches."""
        qos_integration.acquire_batch_token(batch_size=1, cost_multiplier=0.01)

        call = qos_integration.scheduler.acquire_calls[0]
        assert call["cost"] == 1

    def test_acquire_without_scheduler(self, qos_no_scheduler: P03QoSIntegration):
        """Token acquisition returns None when no scheduler configured."""
        token = qos_no_scheduler.acquire_batch_token(batch_size=50)

        assert token is None
        assert qos_no_scheduler.has_active_token

    def test_acquire_fails_when_token_held(self, qos_integration: P03QoSIntegration):
        """Cannot acquire new token while one is held."""
        qos_integration.acquire_batch_token(batch_size=50)

        with pytest.raises(ValueError, match="Token already held"):
            qos_integration.acquire_batch_token(batch_size=50)

    def test_acquire_raises_capacity_error(self, failing_scheduler: MockScheduler):
        """P03CapacityError raised when scheduler fails."""
        qos = P03QoSIntegration(scheduler=failing_scheduler)

        with pytest.raises(P03CapacityError) as exc_info:
            qos.acquire_batch_token(batch_size=100, band="RED")

        err = exc_info.value
        assert err.band == "RED"
        assert err.port == "command"
        assert err.cost == 10  # 100 * 0.1

    def test_release_token(self, qos_integration: P03QoSIntegration):
        """Token release clears state."""
        token = qos_integration.acquire_batch_token(batch_size=50)
        assert qos_integration.has_active_token

        qos_integration.release_token()

        assert not qos_integration.has_active_token
        assert token.released

    def test_release_explicit_token(self, qos_integration: P03QoSIntegration):
        """Can release an explicitly provided token."""
        token = qos_integration.acquire_batch_token(batch_size=50)

        qos_integration.release_token(token)

        assert not qos_integration.has_active_token
        assert token.released

    def test_release_no_token_is_noop(self, qos_integration: P03QoSIntegration):
        """Releasing when no token held is safe."""
        # Should not raise
        qos_integration.release_token()
        assert not qos_integration.has_active_token

    def test_release_already_released_token(self, qos_integration: P03QoSIntegration):
        """Releasing already-released token is safe."""
        token = qos_integration.acquire_batch_token(batch_size=50)
        token.release()

        # Should not raise even if token already released
        qos_integration.release_token()


# ============================================================
# Budget Enforcement Tests
# ============================================================


class TestBudgetEnforcement:
    """Test fanout and top_k budget enforcement."""

    def test_check_fanout_budget_allows(self, qos_integration: P03QoSIntegration):
        """check_fanout_budget returns True when budget allows."""
        assert qos_integration.check_fanout_budget(500)
        assert qos_integration.check_fanout_budget(1000)

    def test_check_fanout_budget_denies(self, qos_integration: P03QoSIntegration):
        """check_fanout_budget returns False when budget insufficient."""
        assert not qos_integration.check_fanout_budget(1001)

    def test_check_top_k_budget_allows(self, qos_integration: P03QoSIntegration):
        """check_top_k_budget returns True when budget allows."""
        assert qos_integration.check_top_k_budget(250)
        assert qos_integration.check_top_k_budget(500)

    def test_check_top_k_budget_denies(self, qos_integration: P03QoSIntegration):
        """check_top_k_budget returns False when budget insufficient."""
        assert not qos_integration.check_top_k_budget(501)

    def test_consume_fanout_success(self, qos_integration: P03QoSIntegration):
        """consume_fanout decrements budget."""
        qos_integration.consume_fanout(100)
        assert qos_integration.fanout_budget == 900

        qos_integration.consume_fanout(50)
        assert qos_integration.fanout_budget == 850

    def test_consume_fanout_exhausted(self, qos_integration: P03QoSIntegration):
        """consume_fanout raises when budget exhausted."""
        qos_integration.consume_fanout(900)

        with pytest.raises(P03BudgetExhaustedError) as exc_info:
            qos_integration.consume_fanout(200)

        err = exc_info.value
        assert err.budget_type == "fanout"
        assert err.requested == 200
        assert err.remaining == 100

    def test_consume_fanout_negative_rejected(self, qos_integration: P03QoSIntegration):
        """consume_fanout rejects negative amounts."""
        with pytest.raises(ValueError, match="non-negative"):
            qos_integration.consume_fanout(-10)

    def test_consume_top_k_success(self, qos_integration: P03QoSIntegration):
        """consume_top_k decrements budget."""
        qos_integration.consume_top_k(100)
        assert qos_integration.top_k_budget == 400

    def test_consume_top_k_exhausted(self, qos_integration: P03QoSIntegration):
        """consume_top_k raises when budget exhausted."""
        qos_integration.consume_top_k(500)

        with pytest.raises(P03BudgetExhaustedError) as exc_info:
            qos_integration.consume_top_k(1)

        err = exc_info.value
        assert err.budget_type == "top_k"
        assert err.requested == 1
        assert err.remaining == 0

    def test_consume_top_k_negative_rejected(self, qos_integration: P03QoSIntegration):
        """consume_top_k rejects negative amounts."""
        with pytest.raises(ValueError, match="non-negative"):
            qos_integration.consume_top_k(-5)


# ============================================================
# Budget Tightening Tests
# ============================================================


class TestBudgetTightening:
    """Test budget tightening behavior."""

    def test_tighten_fanout_reduces(self, qos_integration: P03QoSIntegration):
        """tighten_budgets reduces fanout when new value is lower."""
        qos_integration.tighten_budgets(fanout=500)
        assert qos_integration.fanout_budget == 500

    def test_tighten_fanout_ignores_increase(self, qos_integration: P03QoSIntegration):
        """tighten_budgets ignores increases to fanout."""
        qos_integration.tighten_budgets(fanout=2000)
        assert qos_integration.fanout_budget == 1000

    def test_tighten_top_k_reduces(self, qos_integration: P03QoSIntegration):
        """tighten_budgets reduces top_k when new value is lower."""
        qos_integration.tighten_budgets(top_k=200)
        assert qos_integration.top_k_budget == 200

    def test_tighten_top_k_ignores_increase(self, qos_integration: P03QoSIntegration):
        """tighten_budgets ignores increases to top_k."""
        qos_integration.tighten_budgets(top_k=1000)
        assert qos_integration.top_k_budget == 500

    def test_tighten_both_budgets(self, qos_integration: P03QoSIntegration):
        """tighten_budgets can reduce both simultaneously."""
        qos_integration.tighten_budgets(fanout=300, top_k=100)
        assert qos_integration.fanout_budget == 300
        assert qos_integration.top_k_budget == 100

    def test_tighten_ignores_negative(self, qos_integration: P03QoSIntegration):
        """tighten_budgets ignores negative values."""
        qos_integration.tighten_budgets(fanout=-100, top_k=-50)
        assert qos_integration.fanout_budget == 1000
        assert qos_integration.top_k_budget == 500

    def test_reset_budgets(self, qos_integration: P03QoSIntegration):
        """reset_budgets restores defaults."""
        qos_integration.consume_fanout(800)
        qos_integration.consume_top_k(400)

        qos_integration.reset_budgets()

        assert qos_integration.fanout_budget == 1000
        assert qos_integration.top_k_budget == 500


# ============================================================
# Capacity Action Evaluation Tests
# ============================================================


class TestCapacityActionEvaluation:
    """Test backpressure action evaluation based on QoS state."""

    def test_select_full_when_budget_sufficient(self, qos_integration: P03QoSIntegration):
        """SELECT_FULL when pending count <= fanout budget."""
        action = qos_integration.evaluate_capacity_action(pending_count=500)
        assert action == BackpressureAction.SELECT_FULL

    def test_select_reduced_when_budget_partial(self, qos_integration: P03QoSIntegration):
        """SELECT_REDUCED when budget covers half."""
        action = qos_integration.evaluate_capacity_action(pending_count=1500)
        assert action == BackpressureAction.SELECT_REDUCED

    def test_defer_when_budget_exhausted(self, qos_integration: P03QoSIntegration):
        """DEFER when fanout budget is zero."""
        qos_integration.consume_fanout(1000)
        action = qos_integration.evaluate_capacity_action(pending_count=100)
        assert action == BackpressureAction.DEFER

    def test_defer_when_budget_very_low(self, qos_integration: P03QoSIntegration):
        """DEFER when budget is too low relative to pending."""
        qos_integration.consume_fanout(900)  # 100 remaining
        action = qos_integration.evaluate_capacity_action(pending_count=500)
        assert action == BackpressureAction.DEFER


# ============================================================
# Context Manager Tests
# ============================================================


class TestContextManager:
    """Test context manager protocol."""

    def test_context_manager_releases_on_exit(self, qos_integration: P03QoSIntegration):
        """Context manager releases token on normal exit."""
        with qos_integration:
            token = qos_integration.acquire_batch_token(batch_size=50)
            assert qos_integration.has_active_token

        assert not qos_integration.has_active_token
        assert token.released

    def test_context_manager_releases_on_exception(self, qos_integration: P03QoSIntegration):
        """Context manager releases token on exception."""
        with pytest.raises(RuntimeError):
            with qos_integration:
                token = qos_integration.acquire_batch_token(batch_size=50)
                raise RuntimeError("Test error")

        assert not qos_integration.has_active_token
        assert token.released


# ============================================================
# Serialization Tests
# ============================================================


class TestSerialization:
    """Test to_dict serialization."""

    def test_to_dict_default_state(self, qos_integration: P03QoSIntegration):
        """to_dict captures default state."""
        result = qos_integration.to_dict()

        assert result["port"] == "command"
        assert result["default_band"] == "GREEN"
        assert result["has_scheduler"] is True
        assert result["has_active_token"] is False
        assert result["fanout_budget"] == 1000
        assert result["top_k_budget"] == 500

    def test_to_dict_with_consumption(self, qos_integration: P03QoSIntegration):
        """to_dict reflects consumed budgets."""
        qos_integration.consume_fanout(300)
        qos_integration.consume_top_k(100)
        qos_integration.acquire_batch_token(batch_size=50)

        result = qos_integration.to_dict()

        assert result["fanout_budget"] == 700
        assert result["top_k_budget"] == 400
        assert result["has_active_token"] is True


# ============================================================
# P03QoSSnapshot Tests
# ============================================================


class TestP03QoSSnapshot:
    """Test P03QoSSnapshot immutable capture."""

    def test_snapshot_capture(self, qos_integration: P03QoSIntegration):
        """Snapshot captures current state."""
        qos_integration.consume_fanout(200)
        qos_integration.acquire_batch_token(batch_size=50)

        snapshot = P03QoSSnapshot.capture(qos_integration, band="AMBER")

        assert snapshot.fanout_budget == 800
        assert snapshot.top_k_budget == 500
        assert snapshot.has_active_token is True
        assert snapshot.port == "command"
        assert snapshot.band == "AMBER"
        assert snapshot.captured_at_ms > 0

    def test_snapshot_is_frozen(self, qos_integration: P03QoSIntegration):
        """Snapshot is immutable."""
        snapshot = P03QoSSnapshot.capture(qos_integration)

        with pytest.raises(AttributeError):
            snapshot.fanout_budget = 999

    def test_snapshot_independent_of_source(self, qos_integration: P03QoSIntegration):
        """Snapshot does not change when source changes."""
        snapshot = P03QoSSnapshot.capture(qos_integration)
        original_fanout = snapshot.fanout_budget

        qos_integration.consume_fanout(500)

        assert snapshot.fanout_budget == original_fanout


# ============================================================
# Exception Hierarchy Tests
# ============================================================


class TestExceptionHierarchy:
    """Test exception class hierarchy."""

    def test_capacity_error_is_qos_error(self):
        """P03CapacityError inherits from P03QoSError."""
        err = P03CapacityError(band="RED", port="command", cost=10, limit=5)
        assert isinstance(err, P03QoSError)
        assert isinstance(err, Exception)

    def test_budget_error_is_qos_error(self):
        """P03BudgetExhaustedError inherits from P03QoSError."""
        err = P03BudgetExhaustedError(budget_type="fanout", requested=100, remaining=10)
        assert isinstance(err, P03QoSError)
        assert isinstance(err, Exception)

    def test_capacity_error_message(self):
        """P03CapacityError has informative message."""
        err = P03CapacityError(band="RED", port="command", cost=10, limit=5)
        msg = str(err)
        assert "RED" in msg
        assert "command" in msg
        assert "10" in msg
        assert "5" in msg

    def test_budget_error_message(self):
        """P03BudgetExhaustedError has informative message."""
        err = P03BudgetExhaustedError(budget_type="fanout", requested=100, remaining=10)
        msg = str(err)
        assert "fanout" in msg
        assert "100" in msg
        assert "10" in msg
