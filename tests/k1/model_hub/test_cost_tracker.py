"""M5 Request Pipeline -- Test CostTracker [F50].

Tests cost computation from manifest model cost tables (MH-07),
per-consumer / per-model / per-capability aggregation, and reset.

Covers:
  - CostRecord: construction, frozen
  - compute_cost(): formula from manifest tables
  - track(): record creation + aggregation
  - Properties: total_cost_usd, by_consumer, by_model, by_capability
  - reset(): clears everything
  - Re-exports from services/__init__.py
"""

from __future__ import annotations

import pytest

from k1.model_hub.manifest import ModelSpec
from k1.model_hub.services.cost_tracker import CostRecord, CostTracker
from k1.model_hub.types import CapabilityType, TokenUsage

# ===========================================================================
# Helpers
# ===========================================================================


def _gpt4o_spec() -> ModelSpec:
    return ModelSpec(
        id="gpt-4o",
        capabilities=[CapabilityType.CHAT],
        cost_per_1m_input=2.50,
        cost_per_1m_output=10.00,
    )


def _cheap_spec() -> ModelSpec:
    return ModelSpec(
        id="gpt-4o-mini",
        capabilities=[CapabilityType.CHAT],
        cost_per_1m_input=0.15,
        cost_per_1m_output=0.60,
    )


def _embed_spec() -> ModelSpec:
    return ModelSpec(
        id="text-embedding-3-small",
        capabilities=[CapabilityType.EMBED],
        cost_per_1m_input=0.02,
        cost_per_1m_output=0.0,
    )


# ===========================================================================
# CostRecord Tests
# ===========================================================================


class TestCostRecord:
    def test_construction(self) -> None:
        r = CostRecord(
            cost_usd=0.005,
            input_cost_usd=0.0025,
            output_cost_usd=0.0025,
            model_id="gpt-4o",
            provider_id="openai",
            prompt_tokens=1000,
            completion_tokens=250,
            capability=CapabilityType.CHAT,
        )
        assert r.cost_usd == 0.005
        assert r.consumer_id == ""

    def test_frozen(self) -> None:
        r = CostRecord(
            cost_usd=0.0,
            input_cost_usd=0.0,
            output_cost_usd=0.0,
            model_id="m",
            provider_id="p",
            prompt_tokens=0,
            completion_tokens=0,
            capability=CapabilityType.CHAT,
        )
        with pytest.raises(AttributeError):
            r.cost_usd = 1.0  # type: ignore[misc]


# ===========================================================================
# compute_cost Tests (MH-07)
# ===========================================================================


class TestComputeCost:
    def test_formula(self) -> None:
        """cost = (prompt * input_rate + completion * output_rate) / 1M."""
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        spec = _gpt4o_spec()
        input_cost, output_cost = CostTracker.compute_cost(usage, spec)

        # 1000 * 2.50 / 1_000_000 = 0.0025
        assert input_cost == pytest.approx(0.0025)
        # 500 * 10.00 / 1_000_000 = 0.005
        assert output_cost == pytest.approx(0.005)

    def test_zero_tokens(self) -> None:
        usage = TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
        input_cost, output_cost = CostTracker.compute_cost(usage, _gpt4o_spec())
        assert input_cost == 0.0
        assert output_cost == 0.0

    def test_embedding_no_output_cost(self) -> None:
        """Embedding models have 0 output cost."""
        usage = TokenUsage(prompt_tokens=5000, completion_tokens=0, total_tokens=5000)
        input_cost, output_cost = CostTracker.compute_cost(usage, _embed_spec())
        # 5000 * 0.02 / 1_000_000 = 0.0001
        assert input_cost == pytest.approx(0.0001)
        assert output_cost == 0.0

    def test_cheap_model(self) -> None:
        usage = TokenUsage(prompt_tokens=10000, completion_tokens=1000, total_tokens=11000)
        input_cost, output_cost = CostTracker.compute_cost(usage, _cheap_spec())
        # 10000 * 0.15 / 1M = 0.0015
        assert input_cost == pytest.approx(0.0015)
        # 1000 * 0.60 / 1M = 0.0006
        assert output_cost == pytest.approx(0.0006)


# ===========================================================================
# track() Tests
# ===========================================================================


class TestTrack:
    def test_track_returns_record(self) -> None:
        tracker = CostTracker()
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        record = tracker.track(
            usage, _gpt4o_spec(), provider_id="openai", capability=CapabilityType.CHAT
        )
        assert record.model_id == "gpt-4o"
        assert record.provider_id == "openai"
        assert record.cost_usd == pytest.approx(0.0075)

    def test_track_cumulative(self) -> None:
        tracker = CostTracker()
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        tracker.track(usage, _gpt4o_spec(), provider_id="openai", capability=CapabilityType.CHAT)
        tracker.track(usage, _gpt4o_spec(), provider_id="openai", capability=CapabilityType.CHAT)
        assert tracker.total_cost_usd == pytest.approx(0.015)

    def test_track_with_consumer(self) -> None:
        tracker = CostTracker()
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        record = tracker.track(
            usage,
            _gpt4o_spec(),
            provider_id="openai",
            capability=CapabilityType.CHAT,
            consumer_id="concierge",
        )
        assert record.consumer_id == "concierge"

    def test_records_list(self) -> None:
        tracker = CostTracker()
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        tracker.track(usage, _gpt4o_spec(), provider_id="openai", capability=CapabilityType.CHAT)
        assert len(tracker.records) == 1

    def test_records_returns_copy(self) -> None:
        tracker = CostTracker()
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        tracker.track(usage, _gpt4o_spec(), provider_id="openai", capability=CapabilityType.CHAT)
        records = tracker.records
        records.clear()
        assert len(tracker.records) == 1


# ===========================================================================
# Aggregation Tests
# ===========================================================================


class TestAggregation:
    def test_by_consumer(self) -> None:
        tracker = CostTracker()
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        tracker.track(
            usage,
            _gpt4o_spec(),
            provider_id="openai",
            capability=CapabilityType.CHAT,
            consumer_id="concierge",
        )
        tracker.track(
            usage,
            _gpt4o_spec(),
            provider_id="openai",
            capability=CapabilityType.CHAT,
            consumer_id="planner",
        )
        by = tracker.by_consumer
        assert "concierge" in by
        assert "planner" in by

    def test_by_model(self) -> None:
        tracker = CostTracker()
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        tracker.track(usage, _gpt4o_spec(), provider_id="openai", capability=CapabilityType.CHAT)
        tracker.track(usage, _cheap_spec(), provider_id="openai", capability=CapabilityType.CHAT)
        by = tracker.by_model
        assert "gpt-4o" in by
        assert "gpt-4o-mini" in by

    def test_by_capability(self) -> None:
        tracker = CostTracker()
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        tracker.track(usage, _gpt4o_spec(), provider_id="openai", capability=CapabilityType.CHAT)
        embed_usage = TokenUsage(prompt_tokens=5000, completion_tokens=0, total_tokens=5000)
        tracker.track(
            embed_usage, _embed_spec(), provider_id="openai", capability=CapabilityType.EMBED
        )
        by = tracker.by_capability
        assert "CHAT" in by
        assert "EMBED" in by

    def test_by_consumer_cumulative(self) -> None:
        tracker = CostTracker()
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        tracker.track(
            usage,
            _gpt4o_spec(),
            provider_id="openai",
            capability=CapabilityType.CHAT,
            consumer_id="concierge",
        )
        tracker.track(
            usage,
            _gpt4o_spec(),
            provider_id="openai",
            capability=CapabilityType.CHAT,
            consumer_id="concierge",
        )
        assert tracker.by_consumer["concierge"] == pytest.approx(0.015)


# ===========================================================================
# Reset Tests
# ===========================================================================


class TestReset:
    def test_reset_clears_all(self) -> None:
        tracker = CostTracker()
        usage = TokenUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        tracker.track(usage, _gpt4o_spec(), provider_id="openai", capability=CapabilityType.CHAT)
        tracker.reset()
        assert tracker.total_cost_usd == 0.0
        assert len(tracker.records) == 0
        assert len(tracker.by_consumer) == 0
        assert len(tracker.by_model) == 0
        assert len(tracker.by_capability) == 0


# ===========================================================================
# Re-exports
# ===========================================================================


class TestCostTrackerReExports:
    def test_cost_tracker_reexport(self) -> None:
        from k1.model_hub.services import CostTracker as Reexported

        assert Reexported is CostTracker

    def test_cost_record_reexport(self) -> None:
        from k1.model_hub.services import CostRecord as Reexported

        assert Reexported is CostRecord
