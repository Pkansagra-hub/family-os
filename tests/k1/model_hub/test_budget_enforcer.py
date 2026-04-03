"""M4 Resilience & Cost -- Test BudgetEnforcer [F46].

Tests 3-tier budget enforcement (ALLOW / ALLOW_DEGRADED / REJECT),
spending tracking from HubResponse metadata, and daily reset.

Covers:
  - BudgetCheckResult & SpendingRecord: construction, frozen
  - check(): ALLOW, ALLOW_DEGRADED (>=80%), REJECT (>=100%), cost_limit
  - track(): spending from HubResponse metadata
  - reset_daily(): clears spending
  - Properties: daily_spent_usd, daily_budget_usd, usage_pct, spending_records
  - Re-exports from services/__init__.py
"""

from __future__ import annotations

import pytest

from k1.model_hub.config import ModelHubConfig
from k1.model_hub.services.budget_enforcer import BudgetCheckResult, BudgetEnforcer, SpendingRecord
from k1.model_hub.types import (
    BudgetDecision,
    CapabilityType,
    ChatPayload,
    HubRequest,
    HubResponse,
    Message,
    RequestConstraints,
    ResponseMetadata,
    TokenUsage,
)

# ===========================================================================
# Helpers
# ===========================================================================


def _make_request(
    *,
    cost_limit: float | None = None,
    temperature: float = 0.7,
) -> HubRequest:
    return HubRequest(
        capability=CapabilityType.CHAT,
        payload=ChatPayload(messages=[Message(role="user", content="hi")]),
        trace_id="t-1",
        constraints=RequestConstraints(cost_limit=cost_limit, temperature=temperature),
    )


def _make_response(
    *,
    cost_usd: float = 0.01,
    request_id: str = "r-1",
    provider_id: str = "openai",
    model_id: str = "gpt-4o",
) -> HubResponse:
    return HubResponse(
        result="ok",
        metadata=ResponseMetadata(
            request_id=request_id,
            model_id=model_id,
            provider_id=provider_id,
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            cost_usd=cost_usd,
            latency_ms=100,
            cache_hit=False,
            capability=CapabilityType.CHAT,
            trace_id="t-1",
        ),
    )


def _make_config(daily_budget_usd: float = 5.0) -> ModelHubConfig:
    return ModelHubConfig(daily_budget_usd=daily_budget_usd)


@pytest.fixture
def enforcer() -> BudgetEnforcer:
    return BudgetEnforcer(_make_config(daily_budget_usd=5.0))


# ===========================================================================
# BudgetCheckResult Tests
# ===========================================================================


class TestBudgetCheckResult:
    def test_construction(self) -> None:
        r = BudgetCheckResult(
            decision=BudgetDecision.ALLOW,
            daily_spent_usd=1.0,
            daily_budget_usd=5.0,
            daily_remaining_usd=4.0,
            usage_pct=20.0,
        )
        assert r.decision == BudgetDecision.ALLOW
        assert r.daily_remaining_usd == 4.0
        assert r.reason == ""

    def test_frozen(self) -> None:
        r = BudgetCheckResult(
            decision=BudgetDecision.ALLOW,
            daily_spent_usd=0,
            daily_budget_usd=5,
            daily_remaining_usd=5,
            usage_pct=0,
        )
        with pytest.raises(AttributeError):
            r.decision = BudgetDecision.REJECT  # type: ignore[misc]


# ===========================================================================
# SpendingRecord Tests
# ===========================================================================


class TestSpendingRecord:
    def test_construction(self) -> None:
        sr = SpendingRecord(request_id="r-1", cost_usd=0.05)
        assert sr.request_id == "r-1"
        assert sr.cost_usd == 0.05
        assert sr.consumer_id == ""

    def test_frozen(self) -> None:
        sr = SpendingRecord(request_id="r-1", cost_usd=0.05)
        with pytest.raises(AttributeError):
            sr.cost_usd = 1.0  # type: ignore[misc]


# ===========================================================================
# check() -- ALLOW
# ===========================================================================


class TestCheckAllow:
    def test_healthy_budget_allows(self, enforcer: BudgetEnforcer) -> None:
        result = enforcer.check(_make_request())
        assert result.decision == BudgetDecision.ALLOW
        assert result.daily_budget_usd == 5.0
        assert result.usage_pct == 0.0

    def test_usage_below_80_allows(self, enforcer: BudgetEnforcer) -> None:
        # Spend $3.99 (79.8%)
        enforcer.track(_make_response(cost_usd=3.99))
        result = enforcer.check(_make_request())
        assert result.decision == BudgetDecision.ALLOW

    def test_allow_has_remaining(self, enforcer: BudgetEnforcer) -> None:
        enforcer.track(_make_response(cost_usd=1.0))
        result = enforcer.check(_make_request())
        assert result.daily_remaining_usd == pytest.approx(4.0)


# ===========================================================================
# check() -- ALLOW_DEGRADED (>= 80%)
# ===========================================================================


class TestCheckAllowDegraded:
    def test_at_80_percent(self, enforcer: BudgetEnforcer) -> None:
        enforcer.track(_make_response(cost_usd=4.0))  # 80%
        result = enforcer.check(_make_request())
        assert result.decision == BudgetDecision.ALLOW_DEGRADED
        assert result.usage_pct == pytest.approx(80.0)

    def test_at_95_percent(self, enforcer: BudgetEnforcer) -> None:
        enforcer.track(_make_response(cost_usd=4.75))  # 95%
        result = enforcer.check(_make_request())
        assert result.decision == BudgetDecision.ALLOW_DEGRADED

    def test_degraded_reason_mentions_percent(self, enforcer: BudgetEnforcer) -> None:
        enforcer.track(_make_response(cost_usd=4.5))  # 90%
        result = enforcer.check(_make_request())
        assert "90.0%" in result.reason


# ===========================================================================
# check() -- REJECT (>= 100%, MH-04)
# ===========================================================================


class TestCheckReject:
    def test_at_100_percent(self, enforcer: BudgetEnforcer) -> None:
        enforcer.track(_make_response(cost_usd=5.0))  # 100%
        result = enforcer.check(_make_request())
        assert result.decision == BudgetDecision.REJECT

    def test_over_budget(self, enforcer: BudgetEnforcer) -> None:
        enforcer.track(_make_response(cost_usd=6.0))  # 120%
        result = enforcer.check(_make_request())
        assert result.decision == BudgetDecision.REJECT
        assert result.daily_remaining_usd == 0.0

    def test_reject_reason_mentions_mh04(self, enforcer: BudgetEnforcer) -> None:
        enforcer.track(_make_response(cost_usd=5.0))
        result = enforcer.check(_make_request())
        assert "MH-04" in result.reason


# ===========================================================================
# check() -- Per-request cost_limit
# ===========================================================================


class TestCheckCostLimit:
    def test_cost_limit_rejects_when_remaining_insufficient(self, enforcer: BudgetEnforcer) -> None:
        enforcer.track(_make_response(cost_usd=4.5))  # remaining $0.50
        result = enforcer.check(_make_request(cost_limit=1.0))
        assert result.decision == BudgetDecision.REJECT
        assert "cost_limit" in result.reason

    def test_cost_limit_allows_when_sufficient(self, enforcer: BudgetEnforcer) -> None:
        enforcer.track(_make_response(cost_usd=1.0))  # remaining $4.00
        result = enforcer.check(_make_request(cost_limit=2.0))
        assert result.decision == BudgetDecision.ALLOW

    def test_no_cost_limit_no_check(self, enforcer: BudgetEnforcer) -> None:
        result = enforcer.check(_make_request(cost_limit=None))
        assert result.decision == BudgetDecision.ALLOW


# ===========================================================================
# track()
# ===========================================================================


class TestTrack:
    def test_track_adds_to_daily_total(self, enforcer: BudgetEnforcer) -> None:
        enforcer.track(_make_response(cost_usd=1.0))
        assert enforcer.daily_spent_usd == pytest.approx(1.0)

    def test_track_cumulative(self, enforcer: BudgetEnforcer) -> None:
        enforcer.track(_make_response(cost_usd=1.0, request_id="r-1"))
        enforcer.track(_make_response(cost_usd=2.0, request_id="r-2"))
        assert enforcer.daily_spent_usd == pytest.approx(3.0)

    def test_track_records_spending(self, enforcer: BudgetEnforcer) -> None:
        enforcer.track(_make_response(cost_usd=0.05, request_id="r-1"))
        records = enforcer.spending_records
        assert len(records) == 1
        assert records[0].request_id == "r-1"
        assert records[0].cost_usd == 0.05

    def test_track_records_provider_info(self, enforcer: BudgetEnforcer) -> None:
        enforcer.track(_make_response(cost_usd=0.01, provider_id="azure", model_id="gpt-35"))
        rec = enforcer.spending_records[0]
        assert rec.provider_id == "azure"
        assert rec.model_id == "gpt-35"


# ===========================================================================
# reset_daily()
# ===========================================================================


class TestResetDaily:
    def test_reset_clears_spending(self, enforcer: BudgetEnforcer) -> None:
        enforcer.track(_make_response(cost_usd=4.0))
        enforcer.reset_daily()
        assert enforcer.daily_spent_usd == 0.0

    def test_reset_clears_records(self, enforcer: BudgetEnforcer) -> None:
        enforcer.track(_make_response(cost_usd=1.0))
        enforcer.reset_daily()
        assert len(enforcer.spending_records) == 0

    def test_reset_allows_after_reject(self, enforcer: BudgetEnforcer) -> None:
        enforcer.track(_make_response(cost_usd=5.0))
        assert enforcer.check(_make_request()).decision == BudgetDecision.REJECT
        enforcer.reset_daily()
        assert enforcer.check(_make_request()).decision == BudgetDecision.ALLOW


# ===========================================================================
# Properties
# ===========================================================================


class TestProperties:
    def test_daily_budget_usd(self, enforcer: BudgetEnforcer) -> None:
        assert enforcer.daily_budget_usd == 5.0

    def test_usage_pct_zero(self, enforcer: BudgetEnforcer) -> None:
        assert enforcer.usage_pct == 0.0

    def test_usage_pct_after_spending(self, enforcer: BudgetEnforcer) -> None:
        enforcer.track(_make_response(cost_usd=2.5))
        assert enforcer.usage_pct == pytest.approx(50.0)

    def test_spending_records_returns_copy(self, enforcer: BudgetEnforcer) -> None:
        enforcer.track(_make_response(cost_usd=1.0))
        records = enforcer.spending_records
        records.clear()
        assert len(enforcer.spending_records) == 1

    def test_tiny_budget(self) -> None:
        """Edge case: very small budget works correctly."""
        e = BudgetEnforcer(_make_config(daily_budget_usd=0.01))
        assert e.usage_pct == 0.0
        assert e.daily_budget_usd == 0.01


# ===========================================================================
# Re-exports
# ===========================================================================


class TestBudgetEnforcerReExports:
    def test_budget_enforcer_reexport(self) -> None:
        from k1.model_hub.services import BudgetEnforcer as Reexported

        assert Reexported is BudgetEnforcer

    def test_budget_check_result_reexport(self) -> None:
        from k1.model_hub.services import BudgetCheckResult as Reexported

        assert Reexported is BudgetCheckResult

    def test_spending_record_reexport(self) -> None:
        from k1.model_hub.services import SpendingRecord as Reexported

        assert Reexported is SpendingRecord
