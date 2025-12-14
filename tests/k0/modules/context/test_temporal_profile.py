"""
Test Suite for M08: Temporal & Circadian Profiler Module

Coverage:
- End-to-end temporal profiling with real envelopes
- 11-dimensional schema alignment with st_hipp_events
- Timestamp normalization (ISO 8601, Unix, edge cases)
- Timezone conversion and caching
- Circadian slot and time-of-day bucketing
- Write lag computation and QoS bands
- Backdate detection
- Invariant validation (ingested_at ≤ write_time_utc)
- Performance validation (<4ms P95)
- Contract compliance (schema 1:1 mapping)
"""

import json
import time
from datetime import datetime, timezone
from typing import Any
from unittest.mock import Mock

import pytest

import k0.modules.context.temporal_profile as tp

# ==================== Mock Classes for Phase 2 ====================


class MockMessage:
    """Mock BusMessage for testing Phase 2 signature."""

    def __init__(self, payload: dict[str, Any], trace_id: str = "test_trace"):
        self.payload = json.dumps(payload)
        self.trace_id = trace_id
        self.offset = 0
        self.topic = "cognitive.memory.write.committed.v1"
        self.space_id = "test_space"


class MockContext:
    """Mock PipelineContext for testing Phase 2 signature."""

    def __init__(self):
        self.logger = Mock()
        self.logger.debug = Mock()
        self.logger.info = Mock()
        self.logger.warning = Mock()
        self.logger.error = Mock()
        self.syscalls = Mock()
        self.config = {}


def make_test_call(envelope: dict[str, Any], **config) -> tuple[MockMessage, MockContext, dict]:
    """Helper to create message, context, and config for test calls."""
    message = MockMessage(payload=envelope, trace_id="test_trace")
    context = MockContext()
    return message, context, config


# ==================== Fixtures ====================


@pytest.fixture(autouse=True)
def reset_module_state():
    """Reset module metrics before each test."""
    tp.reset_metrics()
    yield
    tp.reset_metrics()


@pytest.fixture
def sample_envelope():
    """Standard test envelope with event_time."""
    return {
        "body": {"event_time": "2025-11-10T18:00:00Z"},
        "tenant_id": "family-smith",
    }


@pytest.fixture
def now_timestamp():
    """Current timestamp for deterministic testing."""
    return int(datetime.now(timezone.utc).timestamp())


# ==================== End-to-End Tests ====================


class TestEndToEnd:
    """Test complete temporal profiling flow."""

    @pytest.mark.asyncio
    async def test_complete_temporal_profile(self, sample_envelope):
        """Generate complete 11-dimensional temporal profile."""
        message, context, config = make_test_call(sample_envelope)
        result = await tp.run(message, context, **config)

        # Validate all 11 dimensions present
        assert "event_time_utc" in result
        assert "write_time_utc" in result
        assert "write_lag_ms" in result
        assert "local_date" in result
        assert "local_time" in result
        assert "day_of_week" in result
        assert "is_weekend" in result
        assert "time_of_day_bucket" in result
        assert "circadian_slot" in result or result["circadian_slot"] is None
        assert "is_backdated" in result
        assert "created_at" in result
        assert "timezone_used" in result

        # Validate types match st_hipp_events schema
        assert isinstance(result["event_time_utc"], int)
        assert isinstance(result["write_time_utc"], int)
        assert isinstance(result["write_lag_ms"], int)
        assert isinstance(result["local_date"], str)
        assert isinstance(result["local_time"], str)
        assert isinstance(result["day_of_week"], str)
        assert isinstance(result["is_weekend"], bool)
        assert isinstance(result["time_of_day_bucket"], str)
        assert result["circadian_slot"] is None or isinstance(result["circadian_slot"], str)
        assert isinstance(result["is_backdated"], bool)
        assert isinstance(result["created_at"], int)
        assert isinstance(result["timezone_used"], str)

        # Validate created_at = write_time_utc
        assert result["created_at"] == result["write_time_utc"]

        # Validate write_lag_ms = write_time_utc - event_time_utc
        expected_lag = (result["write_time_utc"] - result["event_time_utc"]) * 1000
        assert abs(result["write_lag_ms"] - expected_lag) < 100  # Allow 100ms tolerance

    @pytest.mark.asyncio
    async def test_realtime_event_classification(self, now_timestamp):
        """Test realtime event (<5s write lag) classification."""
        envelope = {
            "body": {"event_time": now_timestamp - 2},  # 2 seconds ago
            "tenant_id": "test",
        }

        message, context, config = make_test_call(envelope, write_time_utc=now_timestamp)
        result = await tp.run(message, context, **config)

        assert result["write_lag_ms"] < 5000  # <5 seconds
        assert result["is_backdated"] is False

        # Check metrics
        metrics = tp.get_metrics()
        assert metrics["write_lag_realtime_count"] == 1
        assert metrics["realtime_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_delayed_event_classification(self, now_timestamp):
        """Test delayed event (5s-24h write lag) classification."""
        envelope = {
            "body": {"event_time": now_timestamp - 3600},  # 1 hour ago
            "tenant_id": "test",
        }

        message, context, config = make_test_call(envelope, write_time_utc=now_timestamp)
        result = await tp.run(message, context, **config)

        assert 5000 <= result["write_lag_ms"] < 86_400_000  # 5s to 24h
        assert result["is_backdated"] is False

        # Check metrics
        metrics = tp.get_metrics()
        assert metrics["write_lag_delayed_count"] == 1
        assert metrics["delayed_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_backdated_event_classification(self, now_timestamp):
        """Test backdated event (>24h write lag) classification."""
        # Event 48 hours ago
        event_time = now_timestamp - (48 * 3600)
        envelope = {
            "body": {"event_time": event_time},
            "tenant_id": "test",
        }

        message, context, config = make_test_call(envelope, write_time_utc=now_timestamp)
        result = await tp.run(message, context, **config)

        assert result["write_lag_ms"] > 86_400_000  # >24 hours
        assert result["is_backdated"] is True

        # Check metrics
        metrics = tp.get_metrics()
        assert metrics["write_lag_backdated_count"] == 1
        assert metrics["backdate_count"] == 1
        assert metrics["backdate_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_invariant_validation_ingested_at(self, now_timestamp):
        """Test invariant: ingested_at ≤ write_time_utc."""
        envelope = {
            "body": {"event_time": now_timestamp - 10},
            "tenant_id": "test",
        }

        # Valid: ingested_at < write_time_utc
        message, context, config = make_test_call(
            envelope,
            write_time_utc=now_timestamp,
            ingested_at=now_timestamp - 5,
        )
        result = await tp.run(message, context, **config)
        metrics = tp.get_metrics()
        assert metrics["invariant_violations"] == 0

        # Invalid: ingested_at > write_time_utc (should log warning)
        tp.reset_metrics()
        message, context, config = make_test_call(
            envelope,
            write_time_utc=now_timestamp,
            ingested_at=now_timestamp + 10,  # Future ingested_at (invalid)
        )
        result = await tp.run(message, context, **config)
        metrics = tp.get_metrics()
        assert metrics["invariant_violations"] == 1

    @pytest.mark.asyncio
    async def test_idempotency(self, sample_envelope):
        """Same envelope → same output (deterministic)."""
        # Use fixed write_time_utc for determinism
        write_time = int(datetime.now(timezone.utc).timestamp())

        message, context, config = make_test_call(sample_envelope, write_time_utc=write_time)
        result1 = await tp.run(message, context, **config)
        message, context, config = make_test_call(sample_envelope, write_time_utc=write_time)
        result2 = await tp.run(message, context, **config)

        # Core temporal fields should match
        assert result1["event_time_utc"] == result2["event_time_utc"]
        assert result1["local_date"] == result2["local_date"]
        assert result1["day_of_week"] == result2["day_of_week"]
        assert result1["is_weekend"] == result2["is_weekend"]
        assert result1["time_of_day_bucket"] == result2["time_of_day_bucket"]
        assert result1["circadian_slot"] == result2["circadian_slot"]


# ==================== Timestamp Normalization Tests ====================


class TestTimestampNormalization:
    """Test timestamp parsing and normalization."""

    def test_iso8601_with_z(self, now_timestamp):
        """ISO 8601 with Z suffix → Unix timestamp."""
        envelope = {
            "body": {"event_time": "2025-11-10T18:00:00Z"},
            "tenant_id": "test",
        }
        result = tp.normalize_timestamp(envelope, now_ts=now_timestamp)

        expected = int(datetime(2025, 11, 10, 18, 0, 0, tzinfo=timezone.utc).timestamp())
        assert result == expected

    def test_iso8601_with_timezone(self, now_timestamp):
        """ISO 8601 with +00:00 timezone → Unix timestamp."""
        envelope = {
            "body": {"event_time": "2025-11-10T18:00:00+00:00"},
            "tenant_id": "test",
        }
        result = tp.normalize_timestamp(envelope, now_ts=now_timestamp)

        expected = int(datetime(2025, 11, 10, 18, 0, 0, tzinfo=timezone.utc).timestamp())
        assert result == expected

    def test_iso8601_naive_assumes_utc(self, now_timestamp):
        """ISO 8601 naive (no timezone) → Assume UTC."""
        envelope = {
            "body": {"event_time": "2025-11-10T18:00:00"},
            "tenant_id": "test",
        }
        result = tp.normalize_timestamp(envelope, now_ts=now_timestamp)

        expected = int(datetime(2025, 11, 10, 18, 0, 0, tzinfo=timezone.utc).timestamp())
        assert result == expected

    def test_unix_timestamp_seconds(self, now_timestamp):
        """Unix timestamp in seconds → Pass through."""
        timestamp = int(datetime(2025, 11, 10, 18, 0, 0, tzinfo=timezone.utc).timestamp())
        envelope = {
            "body": {"event_time": timestamp},
            "tenant_id": "test",
        }
        result = tp.normalize_timestamp(envelope, now_ts=now_timestamp)

        assert result == timestamp

    def test_unix_timestamp_milliseconds(self, now_timestamp):
        """Unix timestamp in milliseconds → Convert to seconds."""
        timestamp_ms = int(datetime(2025, 11, 10, 18, 0, 0, tzinfo=timezone.utc).timestamp()) * 1000
        envelope = {
            "body": {"event_time": timestamp_ms},
            "tenant_id": "test",
        }
        result = tp.normalize_timestamp(envelope, now_ts=now_timestamp)

        expected = timestamp_ms // 1000
        assert result == expected

    def test_unix_timestamp_microseconds(self, now_timestamp):
        """Unix timestamp in microseconds → Convert to seconds."""
        timestamp_us = (
            int(datetime(2025, 11, 10, 18, 0, 0, tzinfo=timezone.utc).timestamp()) * 1_000_000
        )
        envelope = {
            "body": {"event_time": timestamp_us},
            "tenant_id": "test",
        }
        result = tp.normalize_timestamp(envelope, now_ts=now_timestamp)

        expected = timestamp_us // 1_000_000
        assert result == expected

    def test_fallback_to_envelope_ts(self, now_timestamp):
        """Missing body.event_time → Use envelope.ts."""
        envelope = {
            "ts": "2025-11-10T18:00:00Z",
            "tenant_id": "test",
        }
        result = tp.normalize_timestamp(envelope, now_ts=now_timestamp)

        expected = int(datetime(2025, 11, 10, 18, 0, 0, tzinfo=timezone.utc).timestamp())
        assert result == expected

    def test_future_timestamp_clamped(self, now_timestamp):
        """Future timestamp → Clamp to now."""
        future_ts = now_timestamp + 3600  # 1 hour in future
        envelope = {
            "body": {"event_time": future_ts},
            "tenant_id": "test",
        }
        result = tp.normalize_timestamp(envelope, now_ts=now_timestamp)

        assert result == now_timestamp
        metrics = tp.get_metrics()
        assert metrics["future_event_time_clamped"] == 1

    def test_year_2100_clamped(self, now_timestamp):
        """Timestamp > year 2100 → Clamp to now."""
        year_2150 = 5_000_000_000  # Unix timestamp for year 2128
        envelope = {
            "body": {"event_time": year_2150},
            "tenant_id": "test",
        }
        result = tp.normalize_timestamp(envelope, now_ts=now_timestamp)

        assert result == now_timestamp
        metrics = tp.get_metrics()
        assert metrics["future_event_time_clamped"] == 1

    def test_missing_all_timestamps(self, now_timestamp):
        """No timestamps → Use current time."""
        envelope = {"tenant_id": "test"}
        result = tp.normalize_timestamp(envelope, now_ts=now_timestamp)

        assert result == now_timestamp


# ==================== Timezone Conversion Tests ====================


class TestTimezoneConversion:
    """Test UTC to local timezone conversion."""

    def test_conversion_los_angeles(self):
        """Convert UTC to America/Los_Angeles."""
        timestamp = int(datetime(2025, 11, 10, 18, 0, 0, tzinfo=timezone.utc).timestamp())
        dt_local, tz_name = tp.convert_to_local_timezone(timestamp, "test-tenant")

        # Should convert to PST (UTC-8) or PDT (UTC-7)
        assert tz_name == "America/Los_Angeles"
        assert dt_local.hour in (10, 11)  # 18:00 UTC → 10:00 or 11:00 PST/PDT

    def test_timezone_cache_hits(self):
        """Timezone cache should hit on repeated lookups."""
        timestamp = int(datetime.now(timezone.utc).timestamp())

        # First call: cache miss
        tp.reset_metrics()
        tp.convert_to_local_timezone(timestamp, "tenant-1")
        metrics = tp.get_metrics()
        assert metrics["timezone_cache_misses"] == 1
        assert metrics["timezone_cache_hits"] == 1

        # Second call: cache hit (no new miss)
        tp.convert_to_local_timezone(timestamp, "tenant-1")
        metrics = tp.get_metrics()
        assert metrics["timezone_cache_misses"] == 1  # Still 1 (no new miss)
        assert metrics["timezone_cache_hits"] == 2  # Incremented


# ==================== Temporal Bucket Tests ====================


class TestTemporalBuckets:
    """Test day-of-week, weekend, time-of-day, and circadian slot classification."""

    def test_day_of_week_monday(self):
        """2025-11-10 is Monday."""
        dt = datetime(2025, 11, 10, 12, 0, 0, tzinfo=timezone.utc)
        assert tp.get_day_of_week(dt) == "Monday"

    def test_day_of_week_sunday(self):
        """2025-11-16 is Sunday."""
        dt = datetime(2025, 11, 16, 12, 0, 0, tzinfo=timezone.utc)
        assert tp.get_day_of_week(dt) == "Sunday"

    def test_weekend_saturday(self):
        """Saturday is weekend."""
        dt = datetime(2025, 11, 15, 12, 0, 0, tzinfo=timezone.utc)  # Saturday
        assert tp.is_weekend(dt) is True

    def test_weekend_sunday(self):
        """Sunday is weekend."""
        dt = datetime(2025, 11, 16, 12, 0, 0, tzinfo=timezone.utc)  # Sunday
        assert tp.is_weekend(dt) is True

    def test_not_weekend_monday(self):
        """Monday is not weekend."""
        dt = datetime(2025, 11, 10, 12, 0, 0, tzinfo=timezone.utc)  # Monday
        assert tp.is_weekend(dt) is False

    def test_time_of_day_morning(self):
        """06:00-12:00 → morning."""
        dt = datetime(2025, 11, 10, 8, 0, 0, tzinfo=timezone.utc)
        assert tp.get_time_of_day_bucket(dt) == "morning"

    def test_time_of_day_afternoon(self):
        """12:00-17:00 → afternoon."""
        dt = datetime(2025, 11, 10, 14, 0, 0, tzinfo=timezone.utc)
        assert tp.get_time_of_day_bucket(dt) == "afternoon"

    def test_time_of_day_evening(self):
        """17:00-22:00 → evening."""
        dt = datetime(2025, 11, 10, 19, 0, 0, tzinfo=timezone.utc)
        assert tp.get_time_of_day_bucket(dt) == "evening"

    def test_time_of_day_night(self):
        """22:00-06:00 → night (wraps around midnight)."""
        dt = datetime(2025, 11, 10, 23, 0, 0, tzinfo=timezone.utc)
        assert tp.get_time_of_day_bucket(dt) == "night"

    def test_time_of_day_night_early_morning(self):
        """02:00 → night (wraps around midnight)."""
        dt = datetime(2025, 11, 10, 2, 0, 0, tzinfo=timezone.utc)
        assert tp.get_time_of_day_bucket(dt) == "night"

    def test_circadian_breakfast_window(self):
        """06:00-09:00 → breakfast_window."""
        dt = datetime(2025, 11, 10, 7, 30, 0, tzinfo=timezone.utc)
        assert tp.get_circadian_slot(dt) == "breakfast_window"

    def test_circadian_lunch_window(self):
        """11:30-13:30 → lunch_window."""
        dt = datetime(2025, 11, 10, 12, 0, 0, tzinfo=timezone.utc)
        assert tp.get_circadian_slot(dt) == "lunch_window"

    def test_circadian_dinner_window(self):
        """17:30-20:30 → dinner_window."""
        dt = datetime(2025, 11, 10, 18, 30, 0, tzinfo=timezone.utc)
        assert tp.get_circadian_slot(dt) == "dinner_window"

    def test_circadian_sleep_window(self):
        """22:00-06:00 → sleep_window (wraps around midnight)."""
        dt = datetime(2025, 11, 10, 23, 30, 0, tzinfo=timezone.utc)
        assert tp.get_circadian_slot(dt) == "sleep_window"

    def test_circadian_sleep_window_early_morning(self):
        """03:00 → sleep_window (wraps around midnight)."""
        dt = datetime(2025, 11, 10, 3, 0, 0, tzinfo=timezone.utc)
        assert tp.get_circadian_slot(dt) == "sleep_window"

    def test_circadian_no_match(self):
        """10:00 → None (unstructured time)."""
        dt = datetime(2025, 11, 10, 10, 0, 0, tzinfo=timezone.utc)
        assert tp.get_circadian_slot(dt) is None


# ==================== Write Lag Tests ====================


class TestWriteLag:
    """Test write lag computation and classification."""

    def test_compute_write_lag_10_seconds(self):
        """10 seconds lag → 10000 milliseconds."""
        event_time = 1000000000
        write_time = 1000000010
        lag_ms = tp.compute_write_lag(event_time, write_time)

        assert lag_ms == 10000

    def test_compute_write_lag_1_hour(self):
        """1 hour lag → 3600000 milliseconds."""
        event_time = 1000000000
        write_time = 1000003600
        lag_ms = tp.compute_write_lag(event_time, write_time)

        assert lag_ms == 3600000

    def test_is_backdated_25_hours(self):
        """25 hours lag → backdated (threshold 24h)."""
        lag_ms = 25 * 3600 * 1000
        assert tp.is_backdated(lag_ms, threshold_hours=24) is True

    def test_not_backdated_23_hours(self):
        """23 hours lag → not backdated (threshold 24h)."""
        lag_ms = 23 * 3600 * 1000
        assert tp.is_backdated(lag_ms, threshold_hours=24) is False

    def test_classify_write_lag_band_realtime(self):
        """<5 seconds → realtime band."""
        assert tp.classify_write_lag_band(3000) == "realtime"

    def test_classify_write_lag_band_delayed(self):
        """5 seconds to 24 hours → delayed band."""
        assert tp.classify_write_lag_band(10000) == "delayed"
        assert tp.classify_write_lag_band(3600000) == "delayed"

    def test_classify_write_lag_band_backdated(self):
        """>24 hours → backdated band."""
        assert tp.classify_write_lag_band(100_000_000) == "backdated"


# ==================== Performance Tests ====================


class TestPerformance:
    """Test performance requirements (<4ms P95)."""

    @pytest.mark.asyncio
    async def test_run_latency_under_4ms_p95(self):
        """P95 latency < 4ms (timezone lookup + date math)."""
        envelope = {
            "body": {"event_time": "2025-11-10T18:00:00Z"},
            "tenant_id": "test-perf",
        }

        # Warm up (prime cache)
        message, context, config = make_test_call(envelope)
        for _ in range(10):
            await tp.run(message, context, **config)

        # Measure 100 iterations
        latencies = []
        for _ in range(100):
            message, context, config = make_test_call(envelope)
            start = time.perf_counter()
            await tp.run(message, context, **config)
            end = time.perf_counter()
            latencies.append((end - start) * 1000)  # Convert to ms

        # Compute P95
        latencies.sort()
        p95_index = int(len(latencies) * 0.95)
        p95_latency = latencies[p95_index]
        p50_latency = latencies[int(len(latencies) * 0.50)]

        print("\n📊 Performance Results:")
        print(f"   P50: {p50_latency:.4f}ms")
        print(f"   P95: {p95_latency:.4f}ms (budget: 4ms)")
        print(f"   P99: {latencies[int(len(latencies) * 0.99)]:.4f}ms")
        print(f"   Mean: {sum(latencies)/len(latencies):.4f}ms")
        print(f"   Min: {min(latencies):.4f}ms, Max: {max(latencies):.4f}ms")

        assert p95_latency < 4.0, f"P95 latency {p95_latency:.4f}ms exceeds 4ms budget"

    @pytest.mark.asyncio
    async def test_throughput_at_least_250_ops_per_sec(self):
        """Throughput > 250 ops/sec (4ms budget = 250 ops/sec theoretical max)."""
        envelope = {
            "body": {"event_time": "2025-11-10T18:00:00Z"},
            "tenant_id": "test-throughput",
        }

        # Warm up
        message, context, config = make_test_call(envelope)
        for _ in range(10):
            await tp.run(message, context, **config)

        # Measure throughput over 1 second
        iterations = 0
        start = time.perf_counter()

        while time.perf_counter() - start < 1.0:
            message, context, config = make_test_call(envelope)
            await tp.run(message, context, **config)
            iterations += 1

        elapsed = time.perf_counter() - start
        throughput = iterations / elapsed

        print(f"\n⚡ Throughput: {throughput:.0f} ops/sec (target: >250 ops/sec)")

        assert throughput > 250, f"Throughput {throughput:.0f} ops/sec below 250 target"

    @pytest.mark.asyncio
    async def test_batch_processing_performance(self):
        """Test batch processing of 1000 events."""
        envelopes = [
            {
                "body": {"event_time": f"2025-11-10T{i % 24:02d}:00:00Z"},
                "tenant_id": f"tenant-{i % 10}",
            }
            for i in range(1000)
        ]

        start = time.perf_counter()
        for envelope in envelopes:
            message, context, config = make_test_call(envelope)
            await tp.run(message, context, **config)
        elapsed = time.perf_counter() - start

        throughput = len(envelopes) / elapsed
        avg_latency = (elapsed / len(envelopes)) * 1000  # ms

        print("\n📦 Batch Processing Results (1000 events):")
        print(f"   Total time: {elapsed:.3f}s")
        print(f"   Throughput: {throughput:.0f} events/sec")
        print(f"   Avg latency: {avg_latency:.4f}ms")

        assert avg_latency < 4.0, f"Average latency {avg_latency:.4f}ms exceeds 4ms budget"


# ==================== Metrics Tests ====================


class TestMetrics:
    """Test module observability metrics."""

    @pytest.mark.asyncio
    async def test_metrics_tracking(self):
        """Metrics track profiles, cache hits, write lag bands."""
        # Reset to clear any previous state
        tp.reset_metrics()
        # Clear LRU cache to ensure fresh cache misses
        tp.get_tenant_timezone.cache_clear()

        # Run 5 different events (should trigger cache misses for new tenants)
        for i in range(5):
            envelope = {
                "body": {"event_time": "2025-11-10T18:00:00Z"},
                "tenant_id": f"tenant-metrics-{i}",
            }
            message, context, config = make_test_call(envelope)
            await tp.run(message, context, **config)

        metrics = tp.get_metrics()

        assert metrics["total_profiles"] == 5
        assert metrics["timezone_cache_misses"] >= 5  # Each tenant is a new cache miss
        assert (
            metrics["timezone_cache_hits"] >= 5
        )  # Each profile does a conversion (hit after load)
        assert metrics["avg_write_lag_ms"] >= 0
        assert 0 <= metrics["backdate_rate"] <= 1
        assert 0 <= metrics["realtime_rate"] <= 1
        assert 0 <= metrics["delayed_rate"] <= 1

    def test_reset_metrics(self):
        """reset_metrics() clears all counters."""
        tp.reset_metrics()
        metrics = tp.get_metrics()

        assert metrics["total_profiles"] == 0
        assert metrics["timezone_cache_hits"] == 0
        assert metrics["timezone_cache_misses"] == 0
        assert metrics["backdate_count"] == 0
        assert metrics["write_lag_realtime_count"] == 0
        assert metrics["write_lag_delayed_count"] == 0
        assert metrics["write_lag_backdated_count"] == 0
        assert metrics["invariant_violations"] == 0


# ==================== Edge Cases ====================


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_invalid_iso8601_format(self, now_timestamp):
        """Invalid ISO 8601 → Use current time."""
        envelope = {
            "body": {"event_time": "invalid-timestamp"},
            "tenant_id": "test",
        }

        message, context, config = make_test_call(envelope)
        result = await tp.run(message, context, **config)

        # Should fall back to current time
        assert abs(result["event_time_utc"] - now_timestamp) < 10  # Within 10 seconds

    @pytest.mark.asyncio
    async def test_empty_envelope(self, now_timestamp):
        """Empty envelope → Use current time."""
        envelope = {}

        message, context, config = make_test_call(envelope)
        result = await tp.run(message, context, **config)

        # Should use current time
        assert abs(result["event_time_utc"] - now_timestamp) < 10

    @pytest.mark.asyncio
    async def test_dst_transition(self):
        """Test DST transition handling (March/November)."""
        # March DST transition (spring forward)
        envelope = {
            "body": {"event_time": "2025-03-09T10:00:00Z"},  # During DST transition
            "tenant_id": "test",
        }

        message, context, config = make_test_call(envelope)
        result = await tp.run(message, context, **config)

        # Should handle DST correctly (no crashes)
        assert result["local_date"] == "2025-03-09"
        assert result["timezone_used"] == "America/Los_Angeles"

    @pytest.mark.asyncio
    async def test_concurrent_different_tenants(self):
        """Test concurrent requests for different tenants (cache isolation)."""
        envelopes = [
            {
                "body": {"event_time": "2025-11-10T18:00:00Z"},
                "tenant_id": f"tenant-{i}",
            }
            for i in range(10)
        ]

        # Process concurrently
        import asyncio

        async def run_test(env):
            message, context, config = make_test_call(env)
            return await tp.run(message, context, **config)

        results = await asyncio.gather(*[run_test(env) for env in envelopes])

        # All should succeed
        assert len(results) == 10
        for result in results:
            assert "event_time_utc" in result
            assert result["timezone_used"] == "America/Los_Angeles"


# ==================== Contract Compliance Tests ====================


class TestContractCompliance:
    """Test contract compliance and schema alignment."""

    @pytest.mark.asyncio
    async def test_schema_alignment_with_st_hipp_events(self, sample_envelope):
        """Output fields match st_hipp_events temporal columns exactly."""
        message, context, config = make_test_call(sample_envelope)
        result = await tp.run(message, context, **config)

        # Expected 11 temporal columns from migration 0024
        expected_columns = {
            "event_time_utc",  # INTEGER NOT NULL
            "write_time_utc",  # INTEGER NOT NULL
            "write_lag_ms",  # INTEGER
            "local_date",  # TEXT
            "local_time",  # TEXT
            "day_of_week",  # TEXT
            "is_weekend",  # BOOLEAN
            "time_of_day_bucket",  # TEXT
            "circadian_slot",  # TEXT (nullable)
            "is_backdated",  # BOOLEAN
            "created_at",  # INTEGER NOT NULL
        }

        # Validate all expected columns present
        for col in expected_columns:
            assert col in result, f"Missing column: {col}"

        # Validate timezone_used (additional metadata, not in st_hipp_events)
        assert "timezone_used" in result

    @pytest.mark.asyncio
    async def test_contract_latency_budget(self):
        """Verify <4ms P95 latency budget from contract."""
        envelope = {
            "body": {"event_time": "2025-11-10T18:00:00Z"},
            "tenant_id": "contract-test",
        }

        # Warm up
        message, context, config = make_test_call(envelope)
        for _ in range(10):
            await tp.run(message, context, **config)

        # Measure
        latencies = []
        for _ in range(100):
            message, context, config = make_test_call(envelope)
            start = time.perf_counter()
            await tp.run(message, context, **config)
            latencies.append((time.perf_counter() - start) * 1000)

        p95 = sorted(latencies)[95]
        assert p95 < 4.0, f"Contract violation: P95 {p95:.4f}ms exceeds 4ms budget"

    @pytest.mark.asyncio
    async def test_contract_idempotency(self, sample_envelope):
        """Contract requirement: idempotent (same input → same output)."""
        write_time = int(datetime.now(timezone.utc).timestamp())

        message, context, config = make_test_call(sample_envelope, write_time_utc=write_time)
        result1 = await tp.run(message, context, **config)
        message, context, config = make_test_call(sample_envelope, write_time_utc=write_time)
        result2 = await tp.run(message, context, **config)

        # Temporal dimensions should be identical
        assert result1["event_time_utc"] == result2["event_time_utc"]
        assert result1["local_date"] == result2["local_date"]
        assert result1["day_of_week"] == result2["day_of_week"]
