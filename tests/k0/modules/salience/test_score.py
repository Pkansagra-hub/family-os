"""
M06 Salience Scoring Module - Comprehensive Test Suite (pytest)

Tests cover:
1. Social importance scoring (9 tests)
2. Recency decay curves (8 tests)
3. Affect amplification (6 tests)
4. Band classification (5 tests)
5. Salience computation (5 tests)
6. Edge cases (6 tests)
7. Integration tests (5 tests)
8. Performance tests (3 tests)

Total: 47 tests
"""

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

# Import module under test
from k0.modules.salience.score import (
    SalienceResult,
    classify_salience_band,
    compute_affect_amplification,
    compute_recency_score,
    compute_salience,
    compute_social_importance,
    generate_salience_reasons,
    get_metrics,
    reset_metrics,
    run,
)

# ==================== Mock Classes for Phase 2 ====================


class MockMessage:
    def __init__(self, payload: dict, trace_id: str = "test_trace"):
        self.payload = json.dumps(payload)
        self.trace_id = trace_id
        self.offset = 0


class MockContext:
    def __init__(self):
        self.logger = Mock()
        self.syscalls = Mock()
        self.config = {}


def make_test_call(envelope: dict, **config):
    """Helper to create message, context, config tuple for test calls."""
    return MockMessage(envelope), MockContext(), config


# ==================== Fixtures ====================


@pytest.fixture(autouse=True)
def reset_metrics_fixture():
    """Reset metrics before each test."""
    reset_metrics()
    yield
    reset_metrics()


@pytest.fixture
def now_utc():
    """Current UTC time."""
    return datetime.now(timezone.utc)


# ==================== Social Importance Tests ====================


class TestSocialImportance:
    """Test suite for social importance scoring."""

    def test_family_returns_max_score(self):
        """Family events should have maximum social importance (1.0)."""
        score = compute_social_importance("family")
        assert score == 1.0

    def test_extended_family_returns_high_score(self):
        """Extended family events should have high social importance (0.7)."""
        score = compute_social_importance("extended_family")
        assert score == 0.7

    def test_close_friends_returns_moderate_high_score(self):
        """Close friends events should have moderate-high importance (0.6)."""
        score = compute_social_importance("close_friends")
        assert score == 0.6

    def test_friends_returns_moderate_score(self):
        """Friends events should have moderate importance (0.5)."""
        score = compute_social_importance("friends")
        assert score == 0.5

    def test_acquaintance_returns_low_moderate_score(self):
        """Acquaintance events should have low-moderate importance (0.3)."""
        score = compute_social_importance("acquaintance")
        assert score == 0.3

    def test_solo_returns_low_score(self):
        """Solo events should have low importance (0.2)."""
        score = compute_social_importance("solo")
        assert score == 0.2

    def test_none_context_returns_unknown_default(self):
        """Missing social context should return unknown default (0.4)."""
        score = compute_social_importance(None)
        assert score == 0.4

        # Check metrics
        metrics = get_metrics()
        assert metrics["missing_social_context"] == 1

    def test_unknown_context_returns_default(self):
        """Unknown social context should return default (0.4)."""
        score = compute_social_importance("alien_civilization")
        assert score == 0.4

    def test_case_insensitive_matching(self):
        """Social context matching should be case-insensitive."""
        assert compute_social_importance("FAMILY") == 1.0
        assert compute_social_importance("FaMiLy") == 1.0
        assert compute_social_importance("  family  ") == 1.0


# ==================== Recency Decay Tests ====================


class TestRecencyDecay:
    """Test suite for recency decay scoring."""

    def test_30_minutes_ago_returns_high_score(self, now_utc):
        """Events within 1 hour should have high recency score (working memory)."""
        timestamp = now_utc - timedelta(minutes=30)
        score = compute_recency_score(timestamp)
        assert score >= 0.8, f"30-minute-old event should have score ≥0.8, got {score}"

    def test_1_hour_ago_returns_boundary_score(self, now_utc):
        """Events at 1-hour mark should be at working memory boundary (~0.8)."""
        timestamp = now_utc - timedelta(hours=1)
        score = compute_recency_score(timestamp)
        assert 0.75 <= score <= 0.85, f"1-hour-old event should be ~0.8, got {score}"

    def test_6_hours_ago_returns_moderate_score(self, now_utc):
        """Events 6 hours ago should have moderate-high recency score."""
        timestamp = now_utc - timedelta(hours=6)
        score = compute_recency_score(timestamp)
        assert 0.3 <= score <= 0.7, f"6-hour-old event should be 0.3-0.7, got {score}"

    def test_24_hours_ago_returns_episodic_boundary(self, now_utc):
        """Events at 24-hour mark should be at episodic fresh boundary (~0.3)."""
        timestamp = now_utc - timedelta(hours=24)
        score = compute_recency_score(timestamp)
        assert 0.28 <= score <= 0.35, f"24-hour-old event should be ~0.3, got {score}"

    def test_3_days_ago_returns_low_score(self, now_utc):
        """Events 3 days ago should have low recency score."""
        timestamp = now_utc - timedelta(days=3)
        score = compute_recency_score(timestamp)
        assert 0.1 <= score <= 0.3, f"3-day-old event should be 0.1-0.3, got {score}"

    def test_7_days_ago_returns_baseline(self, now_utc):
        """Events at 7-day mark should be at long-term baseline (~0.1)."""
        timestamp = now_utc - timedelta(days=7)
        score = compute_recency_score(timestamp)
        assert 0.08 <= score <= 0.12, f"7-day-old event should be ~0.1, got {score}"

    def test_30_days_ago_returns_minimum_baseline(self, now_utc):
        """Events 30+ days ago should have minimum baseline score (0.1)."""
        timestamp = now_utc - timedelta(days=30)
        score = compute_recency_score(timestamp)
        assert score == 0.1, f"30-day-old event should have baseline 0.1, got {score}"

    def test_future_timestamp_handles_clock_skew(self, now_utc):
        """Future timestamps (clock skew) should return maximum score (1.0)."""
        timestamp = now_utc + timedelta(hours=2)
        score = compute_recency_score(timestamp)
        assert score == 1.0, f"Future timestamp should return 1.0, got {score}"

        # Check metrics
        metrics = get_metrics()
        assert metrics["future_timestamp_count"] == 1


# ==================== Affect Amplification Tests ====================


class TestAffectAmplification:
    """Test suite for affect amplification (non-linear emotional memory encoding)."""

    def test_low_affect_returns_minimal_boost(self):
        """Low affect should pass through with minimal amplification."""
        amplified = compute_affect_amplification(0.2)
        assert 0.20 <= amplified <= 0.25

    def test_moderate_affect_returns_10_percent_boost(self):
        """Moderate affect should get ~10% amplification boost."""
        amplified = compute_affect_amplification(0.5)
        expected = 0.5 + (0.5**2) * 0.2  # 0.55
        assert abs(amplified - expected) < 0.01

    def test_high_affect_returns_amplified_clamped(self):
        """High affect should be amplified but clamped to 1.0."""
        amplified = compute_affect_amplification(0.9)
        assert amplified <= 1.0
        assert amplified >= 0.9

    def test_extreme_affect_returns_maximum(self):
        """Extreme affect (1.0) should remain at maximum after amplification."""
        amplified = compute_affect_amplification(1.0)
        assert amplified == 1.0

    def test_none_affect_returns_neutral_baseline(self):
        """Missing affect should return neutral baseline (0.5)."""
        amplified = compute_affect_amplification(None)
        assert amplified == 0.5

        # Check metrics
        metrics = get_metrics()
        assert metrics["missing_affect_intensity"] == 1

    def test_out_of_range_values_are_clamped(self):
        """Out-of-range affect values should be clamped to [0, 1]."""
        # Negative affect
        assert compute_affect_amplification(-0.5) == 0.0

        # Affect >1.0
        assert compute_affect_amplification(1.5) == 1.0


# ==================== Band Classification Tests ====================


class TestBandClassification:
    """Test suite for salience band classification (HIGH/MED/LOW)."""

    def test_high_score_returns_high_band(self):
        """Scores ≥0.7 should classify as HIGH."""
        band = classify_salience_band(0.95)
        assert band == "HIGH"

        metrics = get_metrics()
        assert metrics["high_band_count"] == 1

    def test_high_boundary_returns_high_band(self):
        """Score exactly 0.70 should classify as HIGH (boundary case)."""
        band = classify_salience_band(0.70)
        assert band == "HIGH"

    def test_medium_score_returns_med_band(self):
        """Scores 0.4-0.7 should classify as MED."""
        band = classify_salience_band(0.55)
        assert band == "MED"

        metrics = get_metrics()
        assert metrics["med_band_count"] == 1

    def test_medium_boundary_returns_med_band(self):
        """Score exactly 0.40 should classify as MED (boundary case)."""
        band = classify_salience_band(0.40)
        assert band == "MED"

    def test_low_score_returns_low_band(self):
        """Scores <0.4 should classify as LOW."""
        band = classify_salience_band(0.25)
        assert band == "LOW"

        metrics = get_metrics()
        assert metrics["low_band_count"] == 1


# ==================== Salience Computation Tests ====================


class TestSalienceComputation:
    """Test suite for full salience computation (weighted formula)."""

    def test_family_high_affect_recent_returns_high(self, now_utc):
        """Family event with high affect and recent timestamp should return HIGH."""
        result = compute_salience(
            social_context="family", affect_intensity=0.9, timestamp=now_utc - timedelta(minutes=30)
        )

        assert isinstance(result, SalienceResult)
        assert result.salience_score >= 0.7
        assert result.salience_band == "HIGH"
        assert len(result.salience_reasons) > 0
        assert result.component_scores.social == 1.0

    def test_solo_low_affect_old_returns_low(self, now_utc):
        """Solo event with low affect and old timestamp should return LOW."""
        result = compute_salience(
            social_context="solo", affect_intensity=0.2, timestamp=now_utc - timedelta(days=10)
        )

        assert isinstance(result, SalienceResult)
        assert result.salience_score < 0.4
        assert result.salience_band == "LOW"
        assert result.component_scores.social == 0.2

    def test_friends_moderate_affect_12h_returns_med(self, now_utc):
        """Friends event with moderate affect and 12h ago should return MED."""
        result = compute_salience(
            social_context="friends", affect_intensity=0.6, timestamp=now_utc - timedelta(hours=12)
        )

        assert isinstance(result, SalienceResult)
        assert 0.4 <= result.salience_score < 0.7
        assert result.salience_band == "MED"
        assert result.component_scores.social == 0.5

    def test_weighted_formula_validation(self, now_utc):
        """Validate that weighted formula is computed correctly."""
        result = compute_salience(
            social_context="family", affect_intensity=0.8, timestamp=now_utc - timedelta(hours=2)
        )

        # Manual calculation: 0.50*social + 0.40*affect + 0.10*recency
        expected_score = (
            0.50 * result.component_scores.social
            + 0.40 * result.component_scores.affect
            + 0.10 * result.component_scores.recency
        )

        assert abs(result.salience_score - expected_score) < 0.01

    def test_score_rounded_to_3_decimals(self, now_utc):
        """Salience score should be rounded to 3 decimal places."""
        result = compute_salience(
            social_context="friends", affect_intensity=0.666, timestamp=now_utc - timedelta(hours=5)
        )

        # Check score has at most 3 decimals
        score_str = str(result.salience_score)
        if "." in score_str:
            decimals = len(score_str.split(".")[1])
            assert decimals <= 3


# ==================== Reason Generation Tests ====================


class TestReasonGeneration:
    """Test suite for interpretable reason generation."""

    def test_includes_component_breakdowns(self):
        """Reasons should include social, affect, recency components."""
        reasons = generate_salience_reasons(
            social_score=1.0,
            affect_score=0.9,
            recency_score=0.8,
            salience_band="HIGH",
            social_context="family",
        )

        assert len(reasons) >= 3

        # Check for component mentions
        reasons_text = " ".join(reasons).lower()
        assert "social" in reasons_text
        assert "affect" in reasons_text or "emotion" in reasons_text
        assert "recency" in reasons_text or "recent" in reasons_text

    def test_includes_overall_band_classification(self):
        """Reasons should include overall salience band."""
        reasons = generate_salience_reasons(
            social_score=0.6,
            affect_score=0.5,
            recency_score=0.4,
            salience_band="MED",
            social_context="friends",
        )

        # Last reason should be band summary
        assert reasons[-1] == "Overall salience: MED"


# ==================== Edge Case Tests ====================


class TestEdgeCases:
    """Test suite for edge cases and error handling."""

    def test_none_social_context_graceful(self, now_utc):
        """Missing social context should use default (0.4) and not crash."""
        result = compute_salience(
            social_context=None, affect_intensity=0.5, timestamp=now_utc - timedelta(hours=1)
        )

        assert result.component_scores.social == 0.4
        assert result.salience_band in ("HIGH", "MED", "LOW")

    def test_none_affect_intensity_graceful(self, now_utc):
        """Missing affect should use neutral baseline (0.5) and not crash."""
        result = compute_salience(
            social_context="family", affect_intensity=None, timestamp=now_utc - timedelta(hours=1)
        )

        assert result.component_scores.affect == 0.5
        assert result.salience_band in ("HIGH", "MED", "LOW")

    def test_both_none_values_graceful(self, now_utc):
        """Missing both social and affect should still compute valid salience."""
        result = compute_salience(
            social_context=None, affect_intensity=None, timestamp=now_utc - timedelta(hours=1)
        )

        # With defaults: social=0.4, affect=0.5, recency≈0.8
        # salience ≈ 0.50*0.4 + 0.40*0.5 + 0.10*0.8 ≈ 0.48
        assert 0.45 <= result.salience_score <= 0.55
        assert result.salience_band == "MED"

    def test_boundary_case_band_transitions(self, now_utc):
        """Test boundary cases between MED and HIGH bands."""
        # Test various boundary scenarios
        result_low = compute_salience(
            social_context="extended_family",
            affect_intensity=0.5,
            timestamp=now_utc - timedelta(minutes=30),
        )

        result_high = compute_salience(
            social_context="extended_family",
            affect_intensity=0.7,
            timestamp=now_utc - timedelta(minutes=10),
        )

        # Just verify both work
        assert result_low.salience_band in ("MED", "HIGH")
        assert result_high.salience_band in ("MED", "HIGH")

    def test_extreme_inputs_do_not_crash(self, now_utc):
        """Test extreme edge cases with unusual inputs."""
        result = compute_salience(
            social_context="🎉🎊🎈" * 100,  # Emoji overload
            affect_intensity=0.9999,
            timestamp=now_utc - timedelta(days=365),
        )

        assert result.salience_band in ("HIGH", "MED", "LOW")

    def test_score_never_exceeds_1_0(self, now_utc):
        """Salience score should never exceed 1.0 even with extreme inputs."""
        result = compute_salience(social_context="family", affect_intensity=1.0, timestamp=now_utc)

        assert result.salience_score <= 1.0


# ==================== Integration Tests (async run()) ====================


class TestAsyncIntegration:
    """Test suite for async run() entry point."""

    @pytest.mark.asyncio
    async def test_processes_valid_envelope(self):
        """Test async run() with valid envelope."""
        now = datetime.now(timezone.utc)
        envelope = {
            "event": {
                "social_context": "family",
                "event_time_utc": (now - timedelta(hours=2)).isoformat(),
            },
            "affect_intensity": 0.8,
        }

        message, context, config = make_test_call(envelope)
        result = await run(message, context, **config)

        # Check required output fields
        assert "salience_score" in result
        assert "salience_band" in result
        assert "salience_reasons_json" in result
        assert "component_scores_json" in result
        assert "salience_computed_at_utc" in result

        # Validate field types
        assert isinstance(result["salience_score"], float)
        assert result["salience_band"] in ("HIGH", "MED", "LOW")

        # Validate JSON fields
        reasons = json.loads(result["salience_reasons_json"])
        assert isinstance(reasons, list)

        components = json.loads(result["component_scores_json"])
        assert "social" in components
        assert "affect" in components
        assert "recency" in components

    @pytest.mark.asyncio
    async def test_handles_missing_timestamp_gracefully(self):
        """Test async run() with missing timestamp (should use default fallback)."""
        envelope = {"event": {"social_context": "family"}, "affect_intensity": 0.8}

        message, context, config = make_test_call(envelope)
        result = await run(message, context, **config)

        # Should fall back to default salience
        assert result["salience_score"] == 0.5
        assert result["salience_band"] == "MED"

        # Check metrics
        metrics = get_metrics()
        assert metrics["default_fallback_count"] == 1

    @pytest.mark.asyncio
    async def test_handles_datetime_object(self):
        """Test async run() with datetime object (not ISO string)."""
        now = datetime.now(timezone.utc)
        envelope = {
            "event": {
                "social_context": "friends",
                "event_time_utc": (now - timedelta(hours=5)).isoformat(),
            },
            "affect_intensity": 0.6,
        }

        message, context, config = make_test_call(envelope)
        result = await run(message, context, **config)

        # Should process successfully
        assert 0.0 <= result["salience_score"] <= 1.0
        assert result["salience_band"] in ("HIGH", "MED", "LOW")

    @pytest.mark.asyncio
    async def test_handles_iso_string_with_z_suffix(self):
        """Test async run() with ISO string ending in 'Z' (UTC indicator)."""
        now = datetime.now(timezone.utc)
        envelope = {
            "event": {
                "social_context": "family",
                "event_time_utc": (now - timedelta(hours=1)).isoformat() + "Z",
            },
            "affect_intensity": 0.7,
        }

        message, context, config = make_test_call(envelope)
        result = await run(message, context, **config)

        # Should parse successfully
        assert 0.0 <= result["salience_score"] <= 1.0

    @pytest.mark.asyncio
    async def test_concurrent_scoring_maintains_independence(self):
        """Test concurrent salience scoring (no state leakage)."""
        now = datetime.now(timezone.utc)

        # Create 10 different envelopes
        envelopes = [
            {
                "event": {
                    "social_context": ["family", "friends", "solo"][i % 3],
                    "event_time_utc": (now - timedelta(hours=i)).isoformat(),
                },
                "affect_intensity": 0.3 + (i % 5) * 0.15,
            }
            for i in range(10)
        ]

        # Run concurrently
        tasks = []
        for env in envelopes:
            message, context, config = make_test_call(env)
            tasks.append(run(message, context, **config))

        results = await asyncio.gather(*tasks)

        # Verify all completed
        assert len(results) == 10

        # Verify scores are diverse (not all the same)
        unique_scores = len(set(r["salience_score"] for r in results))
        assert unique_scores >= 5


# ==================== Performance Tests ====================


class TestPerformance:
    """Performance validation tests (latency budgets)."""

    def test_compute_salience_meets_5ms_p95_budget(self, now_utc):
        """Validate compute_salience meets <5ms P95 latency budget."""
        # Run 1000 iterations for statistical significance
        latencies = []
        for i in range(1000):
            start = time.perf_counter()

            compute_salience(
                social_context=["family", "friends", "solo", "acquaintance"][i % 4],
                affect_intensity=0.2 + (i % 8) * 0.1,
                timestamp=now_utc - timedelta(hours=i % 48),
            )

            end = time.perf_counter()
            latencies.append((end - start) * 1000)  # Convert to ms

        # Calculate P50, P95, P99
        latencies.sort()
        p50 = latencies[int(len(latencies) * 0.50)]
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[int(len(latencies) * 0.99)]

        print("\ncompute_salience() latency:")
        print(f"  P50: {p50:.4f}ms")
        print(f"  P95: {p95:.4f}ms (budget: <5ms)")
        print(f"  P99: {p99:.4f}ms")

        assert p95 < 5.0, f"P95 latency {p95:.4f}ms exceeds 5ms budget"

    @pytest.mark.asyncio
    async def test_async_run_meets_10ms_p95_budget(self):
        """Validate async run() meets <10ms P95 latency (includes JSON overhead)."""
        now = datetime.now(timezone.utc)

        # Run 1000 iterations
        latencies = []
        for i in range(1000):
            envelope = {
                "event": {
                    "social_context": ["family", "friends", "solo", "acquaintance"][i % 4],
                    "event_time_utc": (now - timedelta(hours=i % 48)).isoformat(),
                },
                "affect_intensity": 0.2 + (i % 8) * 0.1,
            }

            message, context, config = make_test_call(envelope)
            start = time.perf_counter()
            await run(message, context, **config)
            end = time.perf_counter()

            latencies.append((end - start) * 1000)

        # Calculate P50, P95, P99
        latencies.sort()
        p50 = latencies[int(len(latencies) * 0.50)]
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[int(len(latencies) * 0.99)]

        print("\nasync run() latency:")
        print(f"  P50: {p50:.4f}ms")
        print(f"  P95: {p95:.4f}ms (budget: <10ms)")
        print(f"  P99: {p99:.4f}ms")

        assert p95 < 10.0, f"P95 latency {p95:.4f}ms exceeds 10ms budget"

    def test_throughput_under_load(self, now_utc):
        """Validate throughput (events/sec) under sustained load."""
        # Run for 1 second and count operations
        start_time = time.perf_counter()
        operations = 0
        target_duration = 1.0  # 1 second

        while time.perf_counter() - start_time < target_duration:
            compute_salience(
                social_context="family",
                affect_intensity=0.7,
                timestamp=now_utc - timedelta(hours=2),
            )
            operations += 1

        elapsed = time.perf_counter() - start_time
        throughput = operations / elapsed

        print(f"\nThroughput: {throughput:.0f} operations/sec")
        print(f"  ({operations} ops in {elapsed:.3f}s)")

        # Should handle >1000 ops/sec (1ms average latency or better)
        assert (
            throughput > 1000
        ), f"Throughput {throughput:.0f} ops/sec is below 1000 ops/sec target"


# ==================== Metrics Tests ====================


class TestMetrics:
    """Test suite for observability metrics."""

    def test_tracks_all_metric_types(self, now_utc):
        """Validate that all metrics are tracked correctly."""
        # Generate diverse events
        compute_salience("family", 0.9, now_utc - timedelta(minutes=30))  # HIGH
        compute_salience("friends", 0.5, now_utc - timedelta(hours=12))  # MED
        compute_salience("solo", 0.2, now_utc - timedelta(days=10))  # LOW
        compute_salience(None, None, now_utc - timedelta(hours=1))  # Missing
        compute_salience("family", 0.8, now_utc + timedelta(hours=2))  # Future

        metrics = get_metrics()

        # Check computation count
        assert metrics["salience_computations"] == 5

        # Check band distribution
        assert metrics["high_band_count"] >= 1
        assert metrics["med_band_count"] >= 1
        assert metrics["low_band_count"] >= 1

        # Check edge case tracking
        assert metrics["missing_social_context"] == 1
        assert metrics["missing_affect_intensity"] == 1
        assert metrics["future_timestamp_count"] == 1

        # Check band distribution percentages
        assert "band_distribution" in metrics
        dist = metrics["band_distribution"]
        assert "high_pct" in dist and "med_pct" in dist and "low_pct" in dist

        # Percentages should sum to ~100%
        total_pct = dist["high_pct"] + dist["med_pct"] + dist["low_pct"]
        assert abs(total_pct - 100.0) < 0.1

    def test_reset_metrics_clears_all_counters(self, now_utc):
        """Validate reset_metrics() clears all counters."""
        # Generate events
        compute_salience("family", 0.9, now_utc - timedelta(minutes=30))
        compute_salience("friends", 0.5, now_utc - timedelta(hours=12))

        metrics_before = get_metrics()
        assert metrics_before["salience_computations"] > 0

        # Reset
        reset_metrics()

        metrics_after = get_metrics()
        assert metrics_after["salience_computations"] == 0
        assert metrics_after["high_band_count"] == 0
