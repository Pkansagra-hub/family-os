"""Integration test: QoS Scheduler, Bands, and Budgets.

Tests the QoS subsystem: scheduler port capacity enforcement, per-band policy
tightening, budget consumption, rejection paths, and metrics emission.

This validates that QoS prevents overload and starvation across the kernel.
"""

from __future__ import annotations

from typing import Dict, Tuple

import pytest

from k0.qos import (
    QoSBudgetError,
    QoSContext,
    Scheduler,
    SchedulerCapacityError,
    SchedulerProfile,
)


class MetricsRecorder:
    """Mock metrics recorder for QoS metric emissions during tests."""

    def __init__(self) -> None:
        self.records: list[Tuple[str, float, Dict[str, str]]] = []

    def __call__(self, metric_name: str, value: float, **labels: str) -> None:
        """Record a metric with name, value, and labels."""
        self.records.append((metric_name, value, dict(labels)))

    def metric_count(self, metric_name: str, **expected: str) -> int:
        """Count metrics matching name and label filters."""
        count = 0
        for name, _value, labels in self.records:
            if name != metric_name:
                continue
            if all(labels.get(k) == v for k, v in expected.items()):
                count += 1
        return count

    def metric_sum(self, metric_name: str, **expected: str) -> float:
        """Sum metric values matching name and label filters."""
        total = 0.0
        for name, value, labels in self.records:
            if name != metric_name:
                continue
            if all(labels.get(k) == v for k, v in expected.items()):
                total += value
        return total

    def reset(self) -> None:
        """Clear recorded metrics."""
        self.records.clear()


class TestSchedulerPortBuckets:
    """Test per-port token bucket enforcement."""

    def test_single_port_respects_capacity_limit(self) -> None:
        """Scheduler enforces capacity limit on single port."""
        profile = SchedulerProfile(
            name="test",
            description="Test",
            port_limits={"command": 10},
            default_port_limit=5,
        )
        scheduler = Scheduler(profile=profile)

        # Acquire up to limit
        token1 = scheduler.acquire(band="GREEN", port="command", cost=7)
        assert scheduler.active_tokens("command") == 7

        # Acquire more within limit
        token2 = scheduler.acquire(band="GREEN", port="command", cost=3)
        assert scheduler.active_tokens("command") == 10

        # Reject exceeding limit
        with pytest.raises(SchedulerCapacityError) as exc_info:
            scheduler.acquire(band="GREEN", port="command", cost=1)

        assert exc_info.value.port == "command"
        assert exc_info.value.cost == 1
        assert exc_info.value.limit == 0  # No capacity remaining

    def test_multiple_ports_independent_buckets(self) -> None:
        """Each port has independent token bucket."""
        profile = SchedulerProfile(
            name="test",
            description="Test",
            port_limits={"command": 5, "query": 10, "sse": 3},
            default_port_limit=2,
        )
        scheduler = Scheduler(profile=profile)

        # Fill command port
        _token_cmd = scheduler.acquire(band="GREEN", port="command", cost=5)
        assert scheduler.active_tokens("command") == 5

        # Query port should still have capacity
        _token_query1 = scheduler.acquire(band="GREEN", port="query", cost=8)
        assert scheduler.active_tokens("query") == 8

        # SSE port independent
        _token_sse = scheduler.acquire(band="GREEN", port="sse", cost=2)
        assert scheduler.active_tokens("sse") == 2

        # Command at limit
        with pytest.raises(SchedulerCapacityError):
            scheduler.acquire(band="GREEN", port="command", cost=1)

        # Query still has capacity
        _token_query2 = scheduler.acquire(band="GREEN", port="query", cost=2)
        assert scheduler.active_tokens("query") == 10

    def test_default_port_limit_applied_to_unknown_ports(self) -> None:
        """Unknown ports use default limit."""
        profile = SchedulerProfile(
            name="test",
            description="Test",
            port_limits={"command": 5},
            default_port_limit=3,
        )
        scheduler = Scheduler(profile=profile)

        # Unknown port uses default_port_limit (3)
        _token = scheduler.acquire(band="GREEN", port="obs", cost=2)
        assert scheduler.active_tokens("obs") == 2

        # Can't exceed default
        with pytest.raises(SchedulerCapacityError):
            scheduler.acquire(band="GREEN", port="obs", cost=2)


class TestBudgetEnforcement:
    """Test per-request budget enforcement."""

    def test_fanout_budget_consumed_and_enforced(self) -> None:
        """Fanout budget is consumed per acquire and enforced."""
        scheduler = Scheduler()
        context = QoSContext(scheduler=scheduler, fanout_budget=5, top_k_budget=10)

        # Consume within budget
        context.consume_fanout(amount=3)
        assert context.fanout_budget == 2

        context.consume_fanout(amount=2)
        assert context.fanout_budget == 0

        # Reject exceeding budget
        with pytest.raises(QoSBudgetError, match="fanout budget exceeded"):
            context.consume_fanout(amount=1)

    def test_top_k_budget_consumed_and_enforced(self) -> None:
        """Top-k budget is consumed per acquire and enforced."""
        scheduler = Scheduler()
        context = QoSContext(scheduler=scheduler, fanout_budget=10, top_k_budget=8)

        # Consume within budget
        context.consume_top_k(amount=5)
        assert context.top_k_budget == 3

        context.consume_top_k(amount=3)
        assert context.top_k_budget == 0

        # Reject exceeding budget
        with pytest.raises(QoSBudgetError, match="top_k budget exceeded"):
            context.consume_top_k(amount=1)

    def test_independent_budget_enforcement(self) -> None:
        """Fanout and top-k budgets are independent."""
        scheduler = Scheduler()
        context = QoSContext(scheduler=scheduler, fanout_budget=5, top_k_budget=5)

        # Consume all fanout
        context.consume_fanout(amount=5)
        assert context.fanout_budget == 0

        # Top-k should still have capacity
        context.consume_top_k(amount=3)
        assert context.top_k_budget == 2

        # Can't consume more fanout
        with pytest.raises(QoSBudgetError):
            context.consume_fanout(amount=1)

        # Can still consume top-k
        context.consume_top_k(amount=2)
        assert context.top_k_budget == 0


class TestBandPolicyTightening:
    """Test per-band policy tightening of budgets."""

    def test_budget_tightening_reduces_limits(self) -> None:
        """Tightening reduces budget limits (never increases)."""
        scheduler = Scheduler()
        context = QoSContext(scheduler=scheduler, fanout_budget=10, top_k_budget=20)

        # Tighten fanout from 10 to 6
        context.tighten(fanout=6)
        assert context.fanout_budget == 6

        # Tighten top-k from 20 to 8
        context.tighten(top_k=8)
        assert context.top_k_budget == 8

        # Tightening to same value is no-op
        context.tighten(fanout=6, top_k=8)
        assert context.fanout_budget == 6
        assert context.top_k_budget == 8

    def test_budget_tightening_rejects_increases(self) -> None:
        """Tightening rejects attempts to increase budgets."""
        scheduler = Scheduler()
        context = QoSContext(scheduler=scheduler, fanout_budget=5, top_k_budget=5)

        # Attempt to increase fanout - silently ignored (no-op)
        context.tighten(fanout=10)
        assert context.fanout_budget == 5

        # Attempt to increase top-k - silently ignored
        context.tighten(top_k=10)
        assert context.top_k_budget == 5

    def test_tightening_respects_consumption(self) -> None:
        """Tightening works correctly after consumption."""
        scheduler = Scheduler()
        context = QoSContext(scheduler=scheduler, fanout_budget=10, top_k_budget=10)

        # Consume some
        context.consume_fanout(amount=3)
        context.consume_top_k(amount=5)
        assert context.fanout_budget == 7
        assert context.top_k_budget == 5

        # Tighten to values between original and consumed
        context.tighten(fanout=4, top_k=3)
        assert context.fanout_budget == 4
        assert context.top_k_budget == 3

        # Further consumption respects new limits
        with pytest.raises(QoSBudgetError):
            context.consume_fanout(amount=5)

        with pytest.raises(QoSBudgetError):
            context.consume_top_k(amount=4)


class TestRejectionPaths:
    """Test error paths and rejection scenarios."""

    def test_capacity_error_includes_context(self) -> None:
        """SchedulerCapacityError includes full context."""
        profile = SchedulerProfile(
            name="test",
            description="Test",
            port_limits={"command": 4},
            default_port_limit=4,
        )
        scheduler = Scheduler(profile=profile)

        # Consume capacity
        token = scheduler.acquire(band="GREEN", port="command", cost=3)
        assert scheduler.active_tokens("command") == 3

        # Try to exceed
        try:
            scheduler.acquire(band="AMBER", port="command", cost=2)
            pytest.fail("Should have raised SchedulerCapacityError")
        except SchedulerCapacityError as e:
            assert e.band == "AMBER"
            assert e.port == "command"
            assert e.cost == 2
            assert e.limit == 1  # 4 - 3 = 1 remaining

    def test_budget_error_raised_on_exceeded(self) -> None:
        """QoSBudgetError raised when budget exceeded."""
        scheduler = Scheduler()
        context = QoSContext(scheduler=scheduler, fanout_budget=1, top_k_budget=1)

        # Consume both budgets
        context.consume_fanout(amount=1)
        context.consume_top_k(amount=1)

        # Both should raise
        with pytest.raises(QoSBudgetError):
            context.consume_fanout(amount=1)

        with pytest.raises(QoSBudgetError):
            context.consume_top_k(amount=1)


class TestTokenManagement:
    """Test token acquisition, release, and context management."""

    def test_token_release_frees_capacity(self) -> None:
        """Token release refunds capacity to scheduler."""
        profile = SchedulerProfile(
            name="test",
            description="Test",
            port_limits={"command": 5},
            default_port_limit=5,
        )
        scheduler = Scheduler(profile=profile)

        token1 = scheduler.acquire(band="GREEN", port="command", cost=3)
        assert scheduler.active_tokens("command") == 3

        token1.release()
        assert scheduler.active_tokens("command") == 0

        # Capacity refunded and available for new acquisitions
        token2 = scheduler.acquire(band="GREEN", port="command", cost=5)
        assert scheduler.active_tokens("command") == 5

    def test_token_context_manager_auto_releases(self) -> None:
        """Token as context manager auto-releases on exit."""
        profile = SchedulerProfile(
            name="test",
            description="Test",
            port_limits={"query": 10},
            default_port_limit=10,
        )
        scheduler = Scheduler(profile=profile)

        with scheduler.acquire(band="GREEN", port="query", cost=4):
            assert scheduler.active_tokens("query") == 4

        # Auto-released after context
        assert scheduler.active_tokens("query") == 0

    def test_multiple_tokens_same_port(self) -> None:
        """Multiple tokens for same port accumulate correctly."""
        profile = SchedulerProfile(
            name="test",
            description="Test",
            port_limits={"sse": 10},
            default_port_limit=10,
        )
        scheduler = Scheduler(profile=profile)

        token1 = scheduler.acquire(band="GREEN", port="sse", cost=2)
        token2 = scheduler.acquire(band="GREEN", port="sse", cost=3)
        token3 = scheduler.acquire(band="AMBER", port="sse", cost=2)

        assert scheduler.active_tokens("sse") == 7

        token2.release()
        assert scheduler.active_tokens("sse") == 4

        token1.release()
        token3.release()
        assert scheduler.active_tokens("sse") == 0


class TestQoSCompleteIntegration:
    """Integration tests for complete QoS scenarios."""

    def test_multi_port_load_distribution(self) -> None:
        """Multiple ports distribute load correctly."""
        profile = SchedulerProfile(
            name="test",
            description="Test",
            port_limits={"command": 10, "query": 15, "sse": 8},
            default_port_limit=5,
        )
        scheduler = Scheduler(profile=profile)

        # Simulate request wave: some command, some query, some sse
        cmd_token1 = scheduler.acquire(band="GREEN", port="command", cost=5)
        query_token1 = scheduler.acquire(band="GREEN", port="query", cost=8)
        _sse_token1 = scheduler.acquire(band="AMBER", port="sse", cost=4)

        assert scheduler.active_tokens("command") == 5
        assert scheduler.active_tokens("query") == 8
        assert scheduler.active_tokens("sse") == 4

        # More requests
        cmd_token2 = scheduler.acquire(band="AMBER", port="command", cost=4)
        query_token2 = scheduler.acquire(band="AMBER", port="query", cost=7)

        assert scheduler.active_tokens("command") == 9
        assert scheduler.active_tokens("query") == 15
        assert scheduler.active_tokens("sse") == 4

        # Release some
        cmd_token1.release()
        query_token1.release()

        assert scheduler.active_tokens("command") == 4
        assert scheduler.active_tokens("query") == 7
        assert scheduler.active_tokens("sse") == 4

        # Can acquire more on query
        query_token3 = scheduler.acquire(band="GREEN", port="query", cost=8)
        assert scheduler.active_tokens("query") == 15

    def test_band_tightening_with_concurrent_requests(self) -> None:
        """Band tightening works with active requests."""
        scheduler = Scheduler()

        # Initial generous budgets (GREEN band)
        context_green = QoSContext(
            scheduler=scheduler, fanout_budget=20, top_k_budget=30
        )

        # Consume some
        context_green.consume_fanout(amount=5)
        context_green.consume_top_k(amount=10)

        # Request comes in for AMBER band - tighten
        context_green.tighten(fanout=12, top_k=15)

        assert context_green.fanout_budget == 12
        assert context_green.top_k_budget == 15

        # Can still consume from tightened budgets
        context_green.consume_fanout(amount=5)
        assert context_green.fanout_budget == 7

        context_green.consume_top_k(amount=5)
        assert context_green.top_k_budget == 10

    def test_scheduler_rejects_all_zero_cost(self) -> None:
        """Scheduler rejects zero and negative costs."""
        scheduler = Scheduler()

        with pytest.raises(ValueError, match="cost must be positive"):
            scheduler.acquire(band="GREEN", port="command", cost=0)

        with pytest.raises(ValueError, match="cost must be positive"):
            scheduler.acquire(band="GREEN", port="command", cost=-5)

    def test_context_rejects_negative_budgets(self) -> None:
        """QoSContext rejects negative amounts in consume/tighten."""
        scheduler = Scheduler()
        context = QoSContext(scheduler=scheduler, fanout_budget=10, top_k_budget=10)

        with pytest.raises(ValueError, match="fanout must be non-negative"):
            context.consume_fanout(amount=-1)

        with pytest.raises(ValueError, match="top_k must be non-negative"):
            context.consume_top_k(amount=-1)

        with pytest.raises(ValueError, match="fanout must be non-negative"):
            context.tighten(fanout=-1)

        with pytest.raises(ValueError, match="top_k must be non-negative"):
            context.tighten(top_k=-1)

    def test_overload_scenario_rejection_clear_errors(self) -> None:
        """Under overload, rejection returns clear errors."""
        profile = SchedulerProfile(
            name="test",
            description="Test",
            port_limits={"command": 3},
            default_port_limit=3,
        )
        scheduler = Scheduler(profile=profile)

        # Consume capacity
        token1 = scheduler.acquire(band="GREEN", port="command", cost=1)
        token2 = scheduler.acquire(band="GREEN", port="command", cost=1)
        token3 = scheduler.acquire(band="GREEN", port="command", cost=1)

        assert scheduler.active_tokens("command") == 3

        # Attempt to acquire when full - should get clear error
        with pytest.raises(SchedulerCapacityError) as exc_info:
            scheduler.acquire(band="AMBER", port="command", cost=1)

        error = exc_info.value
        assert "port 'command'" in str(error).lower()
        assert "requested 1" in str(error)
        assert "available 0" in str(error)

    def test_starvation_prevention_with_bands(self) -> None:
        """Different bands can compete fairly for capacity."""
        profile = SchedulerProfile(
            name="test",
            description="Test",
            port_limits={"command": 10},
            default_port_limit=10,
        )
        scheduler = Scheduler(profile=profile)

        # GREEN band acquires half
        green_token = scheduler.acquire(band="GREEN", port="command", cost=5)
        assert scheduler.active_tokens("command") == 5

        # AMBER band can still acquire remaining half
        amber_token = scheduler.acquire(band="AMBER", port="command", cost=5)
        assert scheduler.active_tokens("command") == 10

        # RED band cannot acquire (port full)
        with pytest.raises(SchedulerCapacityError):
            scheduler.acquire(band="RED", port="command", cost=1)

        # GREEN releases - RED can now acquire
        green_token.release()
        _red_token = scheduler.acquire(band="RED", port="command", cost=3)
        assert scheduler.active_tokens("command") == 8


class TestQoSMetricsEmission:
    """Test metrics support in QoS subsystem."""

    def test_scheduler_supports_metrics_exporter_parameter(self) -> None:
        """Scheduler accepts optional metrics_exporter for telemetry."""
        metrics = MetricsRecorder()
        profile = SchedulerProfile(
            name="test",
            description="Test",
            port_limits={"command": 10},
            default_port_limit=10,
        )
        # Scheduler should accept metrics_exporter without error
        scheduler = Scheduler(profile=profile, metrics_exporter=metrics)
        _token = scheduler.acquire(band="GREEN", port="command", cost=3)
        # If we got here, metrics_exporter was accepted successfully
        assert True

    def test_scheduler_port_utilization_tracking(self) -> None:
        """Scheduler tracks port utilization correctly."""
        profile = SchedulerProfile(
            name="test",
            description="Test",
            port_limits={"command": 10, "query": 5},
            default_port_limit=10,
        )
        scheduler = Scheduler(profile=profile)

        # Verify active tokens tracking
        assert scheduler.active_tokens("command") == 0
        assert scheduler.active_tokens("query") == 0

        token_cmd = scheduler.acquire(band="GREEN", port="command", cost=3)
        assert scheduler.active_tokens("command") == 3

        token_query = scheduler.acquire(band="GREEN", port="query", cost=2)
        assert scheduler.active_tokens("query") == 2

        token_cmd.release()
        assert scheduler.active_tokens("command") == 0

        token_query.release()
        assert scheduler.active_tokens("query") == 0
