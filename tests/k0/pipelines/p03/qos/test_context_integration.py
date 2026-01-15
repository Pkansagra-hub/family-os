"""
Tests for P03QoSContext.

Issue 6.4.2: Fanout/top_k budget management for P03 operations.
"""

from __future__ import annotations

import pytest

from k0.pipelines.p03.qos.context_integration import (
    P03_QOS_DEFAULTS,
    P03BudgetSnapshot,
    P03QoSContext,
    create_p03_qos_context,
)
from k0.qos.context import QoSBudgetError, QoSContext
from k0.qos.policy import QoSTightening
from k0.qos.scheduler import Scheduler, SchedulerProfile


class TestP03QoSDefaults:
    """Tests for P03_QOS_DEFAULTS constant."""

    def test_default_fanout_budget(self) -> None:
        """Default fanout budget is 1000."""
        assert P03_QOS_DEFAULTS["fanout_budget"] == 1000

    def test_default_top_k_budget(self) -> None:
        """Default top_k budget is 500."""
        assert P03_QOS_DEFAULTS["top_k_budget"] == 500


class TestP03BudgetSnapshot:
    """Tests for P03BudgetSnapshot dataclass."""

    def test_snapshot_creation(self) -> None:
        """Snapshot is created correctly."""
        snapshot = P03BudgetSnapshot(
            fanout_remaining=800,
            top_k_remaining=400,
            fanout_consumed=200,
            top_k_consumed=100,
        )
        assert snapshot.fanout_remaining == 800
        assert snapshot.top_k_remaining == 400
        assert snapshot.fanout_consumed == 200
        assert snapshot.top_k_consumed == 100

    def test_fanout_utilization(self) -> None:
        """Fanout utilization is calculated correctly."""
        snapshot = P03BudgetSnapshot(
            fanout_remaining=800,
            top_k_remaining=400,
            fanout_consumed=200,
            top_k_consumed=100,
        )
        # 200 / (800 + 200) = 0.2
        assert snapshot.fanout_utilization == pytest.approx(0.2)

    def test_top_k_utilization(self) -> None:
        """Top-k utilization is calculated correctly."""
        snapshot = P03BudgetSnapshot(
            fanout_remaining=800,
            top_k_remaining=400,
            fanout_consumed=200,
            top_k_consumed=100,
        )
        # 100 / (400 + 100) = 0.2
        assert snapshot.top_k_utilization == pytest.approx(0.2)

    def test_utilization_zero_total(self) -> None:
        """Utilization is 0 when total is 0."""
        snapshot = P03BudgetSnapshot(
            fanout_remaining=0,
            top_k_remaining=0,
            fanout_consumed=0,
            top_k_consumed=0,
        )
        assert snapshot.fanout_utilization == 0.0
        assert snapshot.top_k_utilization == 0.0

    def test_snapshot_is_frozen(self) -> None:
        """Snapshot is immutable (frozen)."""
        snapshot = P03BudgetSnapshot(
            fanout_remaining=100,
            top_k_remaining=50,
            fanout_consumed=10,
            top_k_consumed=5,
        )
        with pytest.raises(AttributeError):
            snapshot.fanout_remaining = 0  # type: ignore[misc]


class TestP03QoSContext:
    """Tests for P03QoSContext class."""

    @pytest.fixture
    def scheduler(self) -> Scheduler:
        """Create K0 Scheduler."""
        profile = SchedulerProfile(
            name="test",
            description="Test scheduler",
            port_limits={"command": 100, "query": 100},
        )
        return Scheduler(profile=profile)

    @pytest.fixture
    def qos_ctx(self, scheduler: Scheduler) -> QoSContext:
        """Create K0 QoSContext."""
        return QoSContext(
            scheduler=scheduler,
            fanout_budget=1000,
            top_k_budget=500,
        )

    @pytest.fixture
    def p03_ctx(self, qos_ctx: QoSContext) -> P03QoSContext:
        """Create P03QoSContext."""
        return P03QoSContext(qos_ctx)

    def test_init(self, qos_ctx: QoSContext) -> None:
        """Context initializes correctly."""
        ctx = P03QoSContext(qos_ctx)
        assert ctx.qos_ctx is qos_ctx
        assert ctx.fanout_budget == 1000
        assert ctx.top_k_budget == 500

    def test_check_fanout_budget_sufficient(self, p03_ctx: P03QoSContext) -> None:
        """check_fanout_budget returns True when sufficient."""
        assert p03_ctx.check_fanout_budget(100) is True
        assert p03_ctx.check_fanout_budget(1000) is True

    def test_check_fanout_budget_insufficient(self, p03_ctx: P03QoSContext) -> None:
        """check_fanout_budget returns False when insufficient."""
        assert p03_ctx.check_fanout_budget(1001) is False

    def test_check_fanout_budget_negative_raises(self, p03_ctx: P03QoSContext) -> None:
        """check_fanout_budget raises on negative input."""
        with pytest.raises(ValueError, match="non-negative"):
            p03_ctx.check_fanout_budget(-1)

    def test_consume_fanout_success(self, p03_ctx: P03QoSContext) -> None:
        """consume_fanout reduces budget and returns True."""
        assert p03_ctx.consume_fanout(100) is True
        assert p03_ctx.fanout_budget == 900

    def test_consume_fanout_insufficient(self, p03_ctx: P03QoSContext) -> None:
        """consume_fanout returns False when insufficient."""
        assert p03_ctx.consume_fanout(1001) is False
        assert p03_ctx.fanout_budget == 1000  # Unchanged

    def test_consume_fanout_negative_raises(self, p03_ctx: P03QoSContext) -> None:
        """consume_fanout raises on negative amount."""
        with pytest.raises(ValueError, match="non-negative"):
            p03_ctx.consume_fanout(-1)

    def test_try_consume_fanout_success(self, p03_ctx: P03QoSContext) -> None:
        """try_consume_fanout reduces budget."""
        p03_ctx.try_consume_fanout(100)
        assert p03_ctx.fanout_budget == 900

    def test_try_consume_fanout_raises(self, p03_ctx: P03QoSContext) -> None:
        """try_consume_fanout raises when insufficient."""
        with pytest.raises(QoSBudgetError):
            p03_ctx.try_consume_fanout(1001)

    def test_check_top_k_budget_sufficient(self, p03_ctx: P03QoSContext) -> None:
        """check_top_k_budget returns True when sufficient."""
        assert p03_ctx.check_top_k_budget(50) is True
        assert p03_ctx.check_top_k_budget(500) is True

    def test_check_top_k_budget_insufficient(self, p03_ctx: P03QoSContext) -> None:
        """check_top_k_budget returns False when insufficient."""
        assert p03_ctx.check_top_k_budget(501) is False

    def test_check_top_k_budget_negative_raises(self, p03_ctx: P03QoSContext) -> None:
        """check_top_k_budget raises on negative input."""
        with pytest.raises(ValueError, match="non-negative"):
            p03_ctx.check_top_k_budget(-1)

    def test_consume_top_k_success(self, p03_ctx: P03QoSContext) -> None:
        """consume_top_k reduces budget and returns True."""
        assert p03_ctx.consume_top_k(50) is True
        assert p03_ctx.top_k_budget == 450

    def test_consume_top_k_insufficient(self, p03_ctx: P03QoSContext) -> None:
        """consume_top_k returns False when insufficient."""
        assert p03_ctx.consume_top_k(501) is False
        assert p03_ctx.top_k_budget == 500  # Unchanged

    def test_consume_top_k_negative_raises(self, p03_ctx: P03QoSContext) -> None:
        """consume_top_k raises on negative amount."""
        with pytest.raises(ValueError, match="non-negative"):
            p03_ctx.consume_top_k(-1)

    def test_try_consume_top_k_success(self, p03_ctx: P03QoSContext) -> None:
        """try_consume_top_k reduces budget."""
        p03_ctx.try_consume_top_k(50)
        assert p03_ctx.top_k_budget == 450

    def test_try_consume_top_k_raises(self, p03_ctx: P03QoSContext) -> None:
        """try_consume_top_k raises when insufficient."""
        with pytest.raises(QoSBudgetError):
            p03_ctx.try_consume_top_k(501)

    def test_tighten_fanout(self, p03_ctx: P03QoSContext) -> None:
        """tighten reduces fanout budget."""
        p03_ctx.tighten(fanout=500)
        assert p03_ctx.fanout_budget == 500

    def test_tighten_top_k(self, p03_ctx: P03QoSContext) -> None:
        """tighten reduces top_k budget."""
        p03_ctx.tighten(top_k=250)
        assert p03_ctx.top_k_budget == 250

    def test_tighten_both(self, p03_ctx: P03QoSContext) -> None:
        """tighten reduces both budgets."""
        p03_ctx.tighten(fanout=500, top_k=250)
        assert p03_ctx.fanout_budget == 500
        assert p03_ctx.top_k_budget == 250

    def test_tighten_cannot_increase(self, p03_ctx: P03QoSContext) -> None:
        """tighten cannot increase budgets."""
        p03_ctx.tighten(fanout=2000, top_k=1000)
        assert p03_ctx.fanout_budget == 1000  # Unchanged
        assert p03_ctx.top_k_budget == 500  # Unchanged

    def test_apply_tightening(self, p03_ctx: P03QoSContext) -> None:
        """apply_tightening applies QoSTightening."""
        tightening = QoSTightening(fanout=500, top_k=250)
        p03_ctx.apply_tightening(tightening)
        assert p03_ctx.fanout_budget == 500
        assert p03_ctx.top_k_budget == 250

    def test_apply_tightening_partial(self, p03_ctx: P03QoSContext) -> None:
        """apply_tightening handles partial tightening."""
        tightening = QoSTightening(fanout=500, top_k=None)
        p03_ctx.apply_tightening(tightening)
        assert p03_ctx.fanout_budget == 500
        assert p03_ctx.top_k_budget == 500  # Unchanged

    def test_acquire_scheduler_token(self, p03_ctx: P03QoSContext) -> None:
        """acquire_scheduler_token delegates to scheduler."""
        token = p03_ctx.acquire_scheduler_token(band="GREEN", port="command", cost=10)
        assert token is not None
        assert token.port == "command"
        assert token.cost == 10
        token.release()

    def test_get_budget_snapshot(self, p03_ctx: P03QoSContext) -> None:
        """get_budget_snapshot returns correct values."""
        p03_ctx.consume_fanout(200)
        p03_ctx.consume_top_k(100)

        snapshot = p03_ctx.get_budget_snapshot()
        assert snapshot.fanout_remaining == 800
        assert snapshot.top_k_remaining == 400
        assert snapshot.fanout_consumed == 200
        assert snapshot.top_k_consumed == 100

    def test_get_remaining_capacity(self, p03_ctx: P03QoSContext) -> None:
        """get_remaining_capacity returns correct dict."""
        p03_ctx.consume_fanout(100)
        p03_ctx.consume_top_k(50)

        capacity = p03_ctx.get_remaining_capacity()
        assert capacity["fanout_budget"] == 900
        assert capacity["top_k_budget"] == 450


class TestCreateP03QoSContext:
    """Tests for create_p03_qos_context factory."""

    @pytest.fixture
    def scheduler(self) -> Scheduler:
        """Create K0 Scheduler."""
        profile = SchedulerProfile(
            name="test",
            description="Test scheduler",
            port_limits={"command": 100},
        )
        return Scheduler(profile=profile)

    def test_creates_with_defaults(self, scheduler: Scheduler) -> None:
        """Factory creates context with default budgets."""
        ctx = create_p03_qos_context(scheduler)
        assert ctx.fanout_budget == 1000
        assert ctx.top_k_budget == 500

    def test_creates_with_custom_fanout(self, scheduler: Scheduler) -> None:
        """Factory accepts custom fanout budget."""
        ctx = create_p03_qos_context(scheduler, fanout_budget=2000)
        assert ctx.fanout_budget == 2000
        assert ctx.top_k_budget == 500

    def test_creates_with_custom_top_k(self, scheduler: Scheduler) -> None:
        """Factory accepts custom top_k budget."""
        ctx = create_p03_qos_context(scheduler, top_k_budget=1000)
        assert ctx.fanout_budget == 1000
        assert ctx.top_k_budget == 1000

    def test_creates_with_both_custom(self, scheduler: Scheduler) -> None:
        """Factory accepts both custom budgets."""
        ctx = create_p03_qos_context(scheduler, fanout_budget=2000, top_k_budget=1000)
        assert ctx.fanout_budget == 2000
        assert ctx.top_k_budget == 1000

    def test_snapshot_tracks_initial(self, scheduler: Scheduler) -> None:
        """Snapshot correctly tracks initial budgets."""
        ctx = create_p03_qos_context(scheduler)
        ctx.consume_fanout(100)
        ctx.consume_top_k(50)

        snapshot = ctx.get_budget_snapshot()
        assert snapshot.fanout_consumed == 100
        assert snapshot.top_k_consumed == 50


class TestApplyObligations:
    """Tests for apply_obligations method."""

    @pytest.fixture
    def scheduler(self) -> Scheduler:
        """Create K0 Scheduler."""
        return Scheduler()

    @pytest.fixture
    def p03_ctx(self, scheduler: Scheduler) -> P03QoSContext:
        """Create P03QoSContext."""
        return create_p03_qos_context(scheduler)

    def test_apply_empty_obligations(self, p03_ctx: P03QoSContext) -> None:
        """Empty obligations return empty tightening."""
        tightening = p03_ctx.apply_obligations([])
        assert tightening.fanout is None
        assert tightening.top_k is None

    def test_apply_non_qos_obligations(self, p03_ctx: P03QoSContext) -> None:
        """Non-QoS obligations are ignored."""

        class DummyObligation:
            name = "some.other.obligation"
            details = {"value": 100}

        tightening = p03_ctx.apply_obligations([DummyObligation()])
        assert tightening.fanout is None
        assert tightening.top_k is None

    def test_apply_qos_tighten_obligation(self, p03_ctx: P03QoSContext) -> None:
        """QoS tighten obligations are applied."""

        class QoSObligation:
            name = "kernel.qos.tighten"
            details = {"fanout": 500, "top_k": 250}

        tightening = p03_ctx.apply_obligations([QoSObligation()])
        assert tightening.fanout == 500
        assert tightening.top_k == 250
        assert p03_ctx.fanout_budget == 500
        assert p03_ctx.top_k_budget == 250
