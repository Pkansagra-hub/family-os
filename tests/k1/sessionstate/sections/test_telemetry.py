"""
Tests for TelemetrySection.

Issue: 2.3.4 (WARM tier - telemetry)
Budget: 8KB (8192 bytes)
Eviction Priority: 1 (FIRST to evict)

Tests cover:
- Data classes (TokenData, CostData, LatencyData, etc.)
- ISection protocol compliance
- IEvictable protocol compliance
- Token API
- Cost API
- Latency API
- Turn timing API
- Error API
- Summary API
- FlatBuffer serialization
- Apply operations
- Edge cases
"""

import pytest

from k1.sessionstate.sections.telemetry import (
    CostData,
    ErrorData,
    ErrorType,
    EvictedData,
    LatencyData,
    SummaryData,
    TelemetrySection,
    TokenData,
    TurnTimingData,
    create_telemetry_section,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def section() -> TelemetrySection:
    """Create fresh TelemetrySection."""
    return TelemetrySection()


@pytest.fixture
def populated_section(section: TelemetrySection) -> TelemetrySection:
    """Create section with recorded turns."""
    # Record 5 turns
    for i in range(5):
        section.record_turn(
            turn_number=i + 1,
            duration_ms=100 + i * 20,
            token_count=50 + i * 10,
            had_tool_call=(i % 2 == 0),
        )
        section.record_tokens(input_tokens=30, output_tokens=50 + i * 10)
        section.record_cost(cost_microdollars=1000 + i * 100)

    return section


# =============================================================================
# TokenData Tests
# =============================================================================


class TestTokenData:
    """Tests for TokenData dataclass."""

    def test_default_values(self) -> None:
        """Test default values."""
        data = TokenData()

        assert data.input_tokens == 0
        assert data.output_tokens == 0
        assert data.total_tokens == 0
        assert data.reasoning_tokens == 0
        assert data.avg_input_per_turn == 0

    def test_to_dict(self) -> None:
        """Test converting to dictionary."""
        data = TokenData(input_tokens=100, output_tokens=200)
        d = data.to_dict()

        assert d["input_tokens"] == 100
        assert d["output_tokens"] == 200
        assert d["total_tokens"] == 0  # Not auto-calculated in dataclass


# =============================================================================
# CostData Tests
# =============================================================================


class TestCostData:
    """Tests for CostData dataclass."""

    def test_default_values(self) -> None:
        """Test default values."""
        data = CostData()

        assert data.total_cost_microdollars == 0
        assert data.reasoning_cost == 0
        assert data.avg_cost_per_turn == 0

    def test_to_dict(self) -> None:
        """Test converting to dictionary."""
        data = CostData(total_cost_microdollars=1_000_000)
        d = data.to_dict()

        assert d["total_cost_microdollars"] == 1_000_000
        assert d["total_cost_usd"] == 1.0


# =============================================================================
# LatencyData Tests
# =============================================================================


class TestLatencyData:
    """Tests for LatencyData dataclass."""

    def test_default_values(self) -> None:
        """Test default values."""
        data = LatencyData()

        assert data.p50_ms == 0
        assert data.p95_ms == 0
        assert data.min_ms == 0
        assert data.max_ms == 0

    def test_to_dict(self) -> None:
        """Test converting to dictionary."""
        data = LatencyData(p50_ms=100, p95_ms=200)
        d = data.to_dict()

        assert d["p50_ms"] == 100
        assert d["p95_ms"] == 200


# =============================================================================
# TurnTimingData Tests
# =============================================================================


class TestTurnTimingData:
    """Tests for TurnTimingData dataclass."""

    def test_default_values(self) -> None:
        """Test default values."""
        data = TurnTimingData()

        assert data.turn_number == 0
        assert data.duration_ms == 0
        assert data.had_error is False
        assert data.had_tool_call is False

    def test_to_dict(self) -> None:
        """Test converting to dictionary."""
        data = TurnTimingData(turn_number=5, duration_ms=150, had_tool_call=True)
        d = data.to_dict()

        assert d["turn_number"] == 5
        assert d["duration_ms"] == 150
        assert d["had_tool_call"] is True


# =============================================================================
# ErrorData Tests
# =============================================================================


class TestErrorData:
    """Tests for ErrorData dataclass."""

    def test_default_values(self) -> None:
        """Test default values."""
        data = ErrorData()

        assert data.total_errors == 0
        assert data.error_rate == 0.0
        assert data.last_error_message == ""

    def test_to_dict(self) -> None:
        """Test converting to dictionary."""
        data = ErrorData(total_errors=5, error_rate=0.1)
        d = data.to_dict()

        assert d["total_errors"] == 5
        assert d["error_rate"] == 0.1


# =============================================================================
# SummaryData Tests
# =============================================================================


class TestSummaryData:
    """Tests for SummaryData dataclass."""

    def test_default_values(self) -> None:
        """Test default values."""
        data = SummaryData()

        assert data.avg_latency_ms == 0
        assert data.error_rate == 0.0
        assert data.latency_sla_met is True
        assert data.budget_sla_met is True

    def test_to_dict(self) -> None:
        """Test converting to dictionary."""
        data = SummaryData(avg_latency_ms=100, latency_sla_met=False)
        d = data.to_dict()

        assert d["avg_latency_ms"] == 100
        assert d["latency_sla_met"] is False


# =============================================================================
# ErrorType Tests
# =============================================================================


class TestErrorType:
    """Tests for ErrorType enum."""

    def test_values(self) -> None:
        """Test enum values."""
        assert ErrorType.TIMEOUT == 0
        assert ErrorType.RATE_LIMIT == 1
        assert ErrorType.MODEL == 2
        assert ErrorType.TOOL == 3
        assert ErrorType.VALIDATION == 4
        assert ErrorType.OTHER == 5


# =============================================================================
# ISection Protocol Tests
# =============================================================================


class TestISection:
    """Tests for ISection protocol compliance."""

    def test_name(self, section: TelemetrySection) -> None:
        """Test section name."""
        assert section.name == "telemetry"

    def test_tier(self, section: TelemetrySection) -> None:
        """Test section tier."""
        assert section.tier == "warm"

    def test_budget_bytes(self, section: TelemetrySection) -> None:
        """Test budget bytes."""
        assert section.budget_bytes == 8192  # 8KB

    def test_get_size_bytes_empty(self, section: TelemetrySection) -> None:
        """Test size of empty section."""
        size = section.get_size_bytes()
        # Base size ~400 bytes
        assert 350 <= size <= 500

    def test_get_size_bytes_with_data(self, populated_section: TelemetrySection) -> None:
        """Test size with data."""
        size = populated_section.get_size_bytes()
        # Base + turn timings + latency samples
        assert size > 400
        assert size < 2000

    def test_clear(self, populated_section: TelemetrySection) -> None:
        """Test clearing section."""
        populated_section.clear()

        assert populated_section.get_turn_count() == 0
        assert populated_section.get_tokens().total_tokens == 0
        assert populated_section.get_cost().total_cost_microdollars == 0

    def test_to_dict(self, populated_section: TelemetrySection) -> None:
        """Test to_dict conversion."""
        d = populated_section.to_dict()

        assert d["name"] == "telemetry"
        assert d["tier"] == "warm"
        assert d["turn_count"] == 5
        assert "tokens" in d
        assert "cost" in d
        assert "latency" in d


# =============================================================================
# IEvictable Protocol Tests
# =============================================================================


class TestIEvictable:
    """Tests for IEvictable protocol compliance."""

    def test_get_eviction_priority(self, section: TelemetrySection) -> None:
        """Test eviction priority."""
        assert section.get_eviction_priority() == 1  # First to evict

    def test_can_evict_empty(self, section: TelemetrySection) -> None:
        """Test empty section cannot evict."""
        assert section.can_evict() is False

    def test_can_evict_with_data(self, populated_section: TelemetrySection) -> None:
        """Test section with data can evict."""
        assert populated_section.can_evict() is True

    def test_evict_partial_turn_timings(self, populated_section: TelemetrySection) -> None:
        """Test eviction evicts turn timings first."""
        initial_timings = len(populated_section.get_turn_timings())

        evicted = populated_section.evict_partial(target_kb=0.2)

        assert len(evicted.turn_timings) > 0
        assert len(populated_section.get_turn_timings()) < initial_timings

    def test_evicted_data_structure(self, populated_section: TelemetrySection) -> None:
        """Test EvictedData structure."""
        evicted = populated_section.evict_partial(target_kb=0.2)

        assert isinstance(evicted, EvictedData)
        assert isinstance(evicted.turn_timings, list)
        assert evicted.bytes_freed > 0
        assert evicted.eviction_reason == "pressure"


# =============================================================================
# Token API Tests
# =============================================================================


class TestTokenAPI:
    """Tests for token API."""

    def test_record_tokens(self, section: TelemetrySection) -> None:
        """Test recording tokens."""
        section.record_tokens(input_tokens=100, output_tokens=200)

        tokens = section.get_tokens()
        assert tokens.input_tokens == 100
        assert tokens.output_tokens == 200
        assert tokens.total_tokens == 300

    def test_record_tokens_cumulative(self, section: TelemetrySection) -> None:
        """Test tokens accumulate."""
        section.record_tokens(input_tokens=100, output_tokens=200)
        section.record_tokens(input_tokens=50, output_tokens=100)

        tokens = section.get_tokens()
        assert tokens.input_tokens == 150
        assert tokens.output_tokens == 300
        assert tokens.total_tokens == 450

    def test_record_tokens_with_breakdown(self, section: TelemetrySection) -> None:
        """Test recording token breakdown."""
        section.record_tokens(
            input_tokens=100,
            output_tokens=200,
            reasoning_tokens=50,
            generation_tokens=150,
        )

        tokens = section.get_tokens()
        assert tokens.reasoning_tokens == 50
        assert tokens.generation_tokens == 150

    def test_avg_tokens_per_turn(self, section: TelemetrySection) -> None:
        """Test average tokens per turn."""
        section.record_turn(turn_number=1, duration_ms=100)
        section.record_tokens(input_tokens=100, output_tokens=200)
        section.record_turn(turn_number=2, duration_ms=100)
        section.record_tokens(input_tokens=100, output_tokens=200)

        tokens = section.get_tokens()
        assert tokens.avg_input_per_turn == 100  # 200/2
        assert tokens.avg_output_per_turn == 200  # 400/2


# =============================================================================
# Cost API Tests
# =============================================================================


class TestCostAPI:
    """Tests for cost API."""

    def test_record_cost(self, section: TelemetrySection) -> None:
        """Test recording cost."""
        section.record_cost(cost_microdollars=1_000_000)

        cost = section.get_cost()
        assert cost.total_cost_microdollars == 1_000_000

    def test_get_total_cost_usd(self, section: TelemetrySection) -> None:
        """Test getting cost in USD."""
        section.record_cost(cost_microdollars=2_500_000)

        assert section.get_total_cost_usd() == 2.5

    def test_record_cost_with_breakdown(self, section: TelemetrySection) -> None:
        """Test recording cost breakdown."""
        section.record_cost(
            cost_microdollars=1_000_000,
            reasoning_cost=300_000,
            generation_cost=500_000,
            tool_cost=200_000,
        )

        cost = section.get_cost()
        assert cost.reasoning_cost == 300_000
        assert cost.generation_cost == 500_000
        assert cost.tool_cost == 200_000

    def test_avg_cost_per_turn(self, section: TelemetrySection) -> None:
        """Test average cost per turn."""
        section.record_turn(turn_number=1, duration_ms=100)
        section.record_cost(cost_microdollars=1_000_000)
        section.record_turn(turn_number=2, duration_ms=100)
        section.record_cost(cost_microdollars=1_000_000)

        cost = section.get_cost()
        assert cost.avg_cost_per_turn == 1_000_000  # 2M/2


# =============================================================================
# Latency API Tests
# =============================================================================


class TestLatencyAPI:
    """Tests for latency API."""

    def test_record_latency(self, section: TelemetrySection) -> None:
        """Test recording latency."""
        section.record_latency(duration_ms=150)

        latency = section.get_latency()
        assert latency.p50_ms == 150
        assert latency.min_ms == 150
        assert latency.max_ms == 150

    def test_percentile_calculation(self, section: TelemetrySection) -> None:
        """Test percentile calculation."""
        # Add 100 samples
        for i in range(100):
            section.record_latency(duration_ms=100 + i)

        latency = section.get_latency()
        assert latency.min_ms == 100
        assert latency.max_ms == 199
        assert 145 <= latency.p50_ms <= 155
        assert 185 <= latency.p95_ms <= 195

    def test_component_latency(self, section: TelemetrySection) -> None:
        """Test component latency tracking."""
        section.record_latency(
            duration_ms=200,
            model_latency_ms=100,
            retrieval_latency_ms=50,
            tool_latency_ms=30,
        )

        latency = section.get_latency()
        assert latency.model_latency_p50_ms > 0
        assert latency.retrieval_latency_p50_ms > 0
        assert latency.tool_latency_p50_ms > 0

    def test_latency_sla_check(self, section: TelemetrySection) -> None:
        """Test latency SLA checking."""
        # Record low latency
        for _ in range(10):
            section.record_latency(duration_ms=100)

        assert section.get_summary().latency_sla_met is True

        # Record high latency
        for _ in range(100):
            section.record_latency(duration_ms=600)

        assert section.get_summary().latency_sla_met is False


# =============================================================================
# Turn Timing API Tests
# =============================================================================


class TestTurnTimingAPI:
    """Tests for turn timing API."""

    def test_record_turn(self, section: TelemetrySection) -> None:
        """Test recording a turn."""
        section.record_turn(
            turn_number=1,
            duration_ms=150,
            token_count=100,
            had_tool_call=True,
        )

        timings = section.get_turn_timings()
        assert len(timings) == 1
        assert timings[0].turn_number == 1
        assert timings[0].duration_ms == 150
        assert timings[0].had_tool_call is True

    def test_get_turn_count(self, section: TelemetrySection) -> None:
        """Test turn count."""
        section.record_turn(turn_number=1, duration_ms=100)
        section.record_turn(turn_number=2, duration_ms=100)

        assert section.get_turn_count() == 2

    def test_turn_timings_limit(self, section: TelemetrySection) -> None:
        """Test turn timings limited to MAX_TURN_TIMINGS."""
        for i in range(30):
            section.record_turn(turn_number=i, duration_ms=100)

        timings = section.get_turn_timings()
        assert len(timings) == section.MAX_TURN_TIMINGS

    def test_tool_call_rate(self, section: TelemetrySection) -> None:
        """Test tool call rate calculation."""
        section.record_turn(turn_number=1, duration_ms=100, had_tool_call=True)
        section.record_turn(turn_number=2, duration_ms=100, had_tool_call=False)
        section.record_turn(turn_number=3, duration_ms=100, had_tool_call=True)
        section.record_turn(turn_number=4, duration_ms=100, had_tool_call=False)

        summary = section.get_summary()
        assert summary.tool_call_rate == 0.5


# =============================================================================
# Error API Tests
# =============================================================================


class TestErrorAPI:
    """Tests for error API."""

    def test_record_error(self, section: TelemetrySection) -> None:
        """Test recording an error."""
        section.record_error(ErrorType.TIMEOUT, turn_number=5, message="Request timed out")

        errors = section.get_errors()
        assert errors.total_errors == 1
        assert errors.timeout_errors == 1
        assert errors.last_error_turn == 5
        assert errors.last_error_message == "Request timed out"

    def test_error_types(self, section: TelemetrySection) -> None:
        """Test different error types."""
        section.record_error(ErrorType.TIMEOUT, turn_number=1)
        section.record_error(ErrorType.RATE_LIMIT, turn_number=2)
        section.record_error(ErrorType.MODEL, turn_number=3)
        section.record_error(ErrorType.TOOL, turn_number=4)
        section.record_error(ErrorType.VALIDATION, turn_number=5)

        errors = section.get_errors()
        assert errors.total_errors == 5
        assert errors.timeout_errors == 1
        assert errors.rate_limit_errors == 1
        assert errors.model_errors == 1
        assert errors.tool_errors == 1
        assert errors.validation_errors == 1

    def test_error_rate(self, section: TelemetrySection) -> None:
        """Test error rate calculation."""
        section.record_turn(turn_number=1, duration_ms=100)
        section.record_turn(turn_number=2, duration_ms=100, had_error=True)
        section.record_error(ErrorType.MODEL, turn_number=2)

        errors = section.get_errors()
        assert errors.error_rate == 0.5

    def test_error_message_truncation(self, section: TelemetrySection) -> None:
        """Test error message truncation."""
        long_message = "x" * 300
        section.record_error(ErrorType.OTHER, turn_number=1, message=long_message)

        errors = section.get_errors()
        assert len(errors.last_error_message) == 200


# =============================================================================
# Summary API Tests
# =============================================================================


class TestSummaryAPI:
    """Tests for summary API."""

    def test_get_summary(self, populated_section: TelemetrySection) -> None:
        """Test getting summary."""
        summary = populated_section.get_summary()

        assert summary.avg_latency_ms > 0
        assert summary.tool_call_rate > 0
        assert summary.latency_sla_met is True

    def test_set_budget_sla_met(self, section: TelemetrySection) -> None:
        """Test setting budget SLA."""
        section.set_budget_sla_met(False)

        assert section.get_summary().budget_sla_met is False


# =============================================================================
# Statistics Tests
# =============================================================================


class TestStatistics:
    """Tests for statistics API."""

    def test_get_statistics(self, populated_section: TelemetrySection) -> None:
        """Test getting statistics."""
        stats = populated_section.get_statistics()

        assert stats["turn_count"] == 5
        assert stats["total_tokens"] > 0
        assert stats["total_cost_usd"] > 0
        assert stats["turn_timings_count"] == 5

    def test_statistics_empty(self, section: TelemetrySection) -> None:
        """Test statistics for empty section."""
        stats = section.get_statistics()

        assert stats["turn_count"] == 0
        assert stats["total_tokens"] == 0
        assert stats["latency_sla_met"] is True


# =============================================================================
# Integrity Tests
# =============================================================================


class TestIntegrity:
    """Tests for integrity verification."""

    def test_compute_integrity(self, populated_section: TelemetrySection) -> None:
        """Test computing integrity hash."""
        hash1 = populated_section.compute_integrity()

        assert len(hash1) == 64  # SHA256 hex
        assert hash1 == populated_section.compute_integrity()  # Deterministic

    def test_verify_integrity(self, populated_section: TelemetrySection) -> None:
        """Test verifying integrity."""
        populated_section.update_integrity()

        assert populated_section.verify_integrity() is True

    def test_verify_integrity_after_modification(self, populated_section: TelemetrySection) -> None:
        """Test integrity fails after modification."""
        populated_section.update_integrity()

        # Modify
        populated_section.record_turn(turn_number=99, duration_ms=100)

        assert populated_section.verify_integrity() is False


# =============================================================================
# FlatBuffer Serialization Tests
# =============================================================================


class TestFlatBufferSerialization:
    """Tests for FlatBuffer serialization."""

    def test_to_flatbuffer(self, populated_section: TelemetrySection) -> None:
        """Test serializing to FlatBuffer."""
        data = populated_section.to_flatbuffer()

        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_from_flatbuffer(self, populated_section: TelemetrySection) -> None:
        """Test deserializing from FlatBuffer."""
        data = populated_section.to_flatbuffer()

        restored = TelemetrySection()
        restored.from_flatbuffer(data)

        assert restored.get_turn_count() == 0  # Not stored
        assert restored.get_tokens().total_tokens == populated_section.get_tokens().total_tokens

    def test_roundtrip_tokens(self, section: TelemetrySection) -> None:
        """Test roundtrip preserves tokens."""
        section.record_tokens(
            input_tokens=500,
            output_tokens=1000,
            reasoning_tokens=200,
        )

        data = section.to_flatbuffer()
        restored = TelemetrySection()
        restored.from_flatbuffer(data)

        assert restored.get_tokens().input_tokens == 500
        assert restored.get_tokens().output_tokens == 1000
        assert restored.get_tokens().reasoning_tokens == 200

    def test_roundtrip_cost(self, section: TelemetrySection) -> None:
        """Test roundtrip preserves cost."""
        section.record_cost(
            cost_microdollars=5_000_000,
            reasoning_cost=2_000_000,
        )

        data = section.to_flatbuffer()
        restored = TelemetrySection()
        restored.from_flatbuffer(data)

        assert restored.get_cost().total_cost_microdollars == 5_000_000
        assert restored.get_cost().reasoning_cost == 2_000_000

    def test_roundtrip_latency(self, section: TelemetrySection) -> None:
        """Test roundtrip preserves latency."""
        for i in range(10):
            section.record_latency(duration_ms=100 + i * 10)

        data = section.to_flatbuffer()
        restored = TelemetrySection()
        restored.from_flatbuffer(data)

        assert restored.get_latency().min_ms == section.get_latency().min_ms
        assert restored.get_latency().max_ms == section.get_latency().max_ms
        assert restored.get_latency().p95_ms == section.get_latency().p95_ms

    def test_roundtrip_errors(self, section: TelemetrySection) -> None:
        """Test roundtrip preserves errors."""
        section.record_turn(turn_number=1, duration_ms=100)
        section.record_error(ErrorType.MODEL, turn_number=1, message="Test error")

        data = section.to_flatbuffer()
        restored = TelemetrySection()
        restored.from_flatbuffer(data)

        assert restored.get_errors().total_errors == 1
        assert restored.get_errors().model_errors == 1
        assert restored.get_errors().last_error_message == "Test error"

    def test_roundtrip_turn_timings(self, section: TelemetrySection) -> None:
        """Test roundtrip preserves turn timings."""
        section.record_turn(turn_number=1, duration_ms=100, had_tool_call=True)
        section.record_turn(turn_number=2, duration_ms=200, had_error=True)

        data = section.to_flatbuffer()
        restored = TelemetrySection()
        restored.from_flatbuffer(data)

        timings = restored.get_turn_timings()
        assert len(timings) == 2
        assert timings[0].turn_number == 1
        assert timings[0].had_tool_call is True
        assert timings[1].had_error is True

    def test_roundtrip_summary(self, section: TelemetrySection) -> None:
        """Test roundtrip preserves summary."""
        section.set_budget_sla_met(False)
        # Add enough latency to fail SLA
        for _ in range(100):
            section.record_latency(duration_ms=600)

        data = section.to_flatbuffer()
        restored = TelemetrySection()
        restored.from_flatbuffer(data)

        assert restored.get_summary().budget_sla_met is False
        assert restored.get_summary().latency_sla_met is False

    def test_caching(self, populated_section: TelemetrySection) -> None:
        """Test FlatBuffer caching."""
        data1 = populated_section.to_flatbuffer()
        data2 = populated_section.to_flatbuffer()

        # Same reference (cached)
        assert data1 is data2

    def test_cache_invalidation(self, section: TelemetrySection) -> None:
        """Test cache invalidated on modification."""
        section.record_turn(turn_number=1, duration_ms=100)
        data1 = section.to_flatbuffer()

        section.record_turn(turn_number=2, duration_ms=200)
        data2 = section.to_flatbuffer()

        assert data1 is not data2


# =============================================================================
# Apply Operations Tests
# =============================================================================


class TestApplyOperations:
    """Tests for apply operations (MutationGuard pattern)."""

    def test_apply_record_tokens(self, section: TelemetrySection) -> None:
        """Test apply record_tokens."""
        section.apply("record_tokens", {"input_tokens": 100, "output_tokens": 200})
        assert section.get_tokens().total_tokens == 300

    def test_apply_record_cost(self, section: TelemetrySection) -> None:
        """Test apply record_cost."""
        section.apply("record_cost", {"cost_microdollars": 1_000_000})
        assert section.get_cost().total_cost_microdollars == 1_000_000

    def test_apply_record_latency(self, section: TelemetrySection) -> None:
        """Test apply record_latency."""
        section.apply("record_latency", {"duration_ms": 150})
        assert section.get_latency().p50_ms == 150

    def test_apply_record_turn(self, section: TelemetrySection) -> None:
        """Test apply record_turn."""
        section.apply(
            "record_turn",
            {"turn_number": 1, "duration_ms": 100, "had_tool_call": True},
        )
        assert section.get_turn_count() == 1

    def test_apply_record_error(self, section: TelemetrySection) -> None:
        """Test apply record_error."""
        section.record_turn(turn_number=1, duration_ms=100)
        section.apply(
            "record_error",
            {"error_type": ErrorType.TIMEOUT, "turn_number": 1},
        )
        assert section.get_errors().timeout_errors == 1

    def test_apply_record_error_int(self, section: TelemetrySection) -> None:
        """Test apply record_error with int error type."""
        section.record_turn(turn_number=1, duration_ms=100)
        section.apply("record_error", {"error_type": 2, "turn_number": 1})  # MODEL
        assert section.get_errors().model_errors == 1

    def test_apply_set_budget_sla_met(self, section: TelemetrySection) -> None:
        """Test apply set_budget_sla_met."""
        section.apply("set_budget_sla_met", {"met": False})
        assert section.get_summary().budget_sla_met is False

    def test_apply_evict_partial(self, populated_section: TelemetrySection) -> None:
        """Test apply evict_partial."""
        result = populated_section.apply("evict_partial", {"target_kb": 0.2})

        assert isinstance(result, EvictedData)
        assert result.bytes_freed > 0

    def test_apply_clear(self, populated_section: TelemetrySection) -> None:
        """Test apply clear."""
        populated_section.apply("clear", {})

        assert populated_section.get_turn_count() == 0

    def test_apply_unknown_operation(self, section: TelemetrySection) -> None:
        """Test apply with unknown operation."""
        with pytest.raises(ValueError, match="Unknown operation"):
            section.apply("unknown", {})


# =============================================================================
# Factory Function Tests
# =============================================================================


class TestFactory:
    """Tests for factory function."""

    def test_create_telemetry_section(self) -> None:
        """Test factory creates empty section."""
        section = create_telemetry_section()

        assert isinstance(section, TelemetrySection)
        assert section.get_turn_count() == 0


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_len(self, populated_section: TelemetrySection) -> None:
        """Test __len__ returns turn timings count."""
        assert len(populated_section) == 5

    def test_repr(self, populated_section: TelemetrySection) -> None:
        """Test __repr__."""
        r = repr(populated_section)

        assert "TelemetrySection" in r
        assert "turns=5" in r
        assert "tokens=" in r
        assert "cost=$" in r

    def test_constants(self) -> None:
        """Test class constants."""
        assert TelemetrySection.BUDGET_BYTES == 8192
        assert TelemetrySection.TIER == "warm"
        assert TelemetrySection.SECTION_NAME == "telemetry"
        assert TelemetrySection.CAN_EVICT is True
        assert TelemetrySection.EVICTION_PRIORITY == 1
        assert TelemetrySection.MAX_TURN_TIMINGS == 20
        assert TelemetrySection.MAX_LATENCY_SAMPLES == 100

    def test_latency_samples_limit(self, section: TelemetrySection) -> None:
        """Test latency samples limited to MAX_LATENCY_SAMPLES."""
        for i in range(150):
            section.record_latency(duration_ms=100 + i)

        # Should only keep last 100
        stats = section.get_statistics()
        assert stats["latency_samples_count"] == section.MAX_LATENCY_SAMPLES
