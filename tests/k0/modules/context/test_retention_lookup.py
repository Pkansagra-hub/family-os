"""
Comprehensive test suite for M11 Retention Lookup module.

Test Categories:
1. Exact Match Lookup (8 tests)
2. Fallback Chain (6 tests)
3. Topic Normalization (4 tests)
4. Retention Buckets (3 tests)
5. End-to-End Resolution (6 tests)
6. Performance Tests (3 tests)
7. Metrics Tests (2 tests)
8. Edge Cases (6 tests)

Total: 38 tests
"""

import time

import pytest

# Direct import to avoid __init__.py conflicts
from k0.modules.context.retention_lookup import (
    DEFAULT_RETENTION_BUCKET,
    DEFAULT_RETENTION_DAYS,
    clear_cache,
    get_metrics,
    lookup_retention_policy,
    reset_metrics,
    run,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture(autouse=True)
def reset_module_state():
    """Reset module metrics and cache before each test."""
    reset_metrics()
    clear_cache()
    yield
    reset_metrics()
    clear_cache()


@pytest.fixture
def sample_envelope_red_phone():
    """Sample envelope for RED band, write, phone."""
    return {
        "topic": "cognitive.memory.write.v1",
        "policy_stamp": {"band": "RED"},
        "metadata": {"device_kind": "phone"},
        "device_id": "device-dad-phone",
    }


@pytest.fixture
def sample_envelope_amber_photo():
    """Sample envelope for AMBER band, photo, tablet."""
    return {
        "topic": "cognitive.memory.photo.v1",
        "policy_stamp": {"band": "AMBER"},
        "metadata": {"device_kind": "tablet"},
        "device_id": "device-mom-tablet",
    }


@pytest.fixture
def sample_envelope_green_write():
    """Sample envelope for GREEN band, write, web."""
    return {
        "topic": "cognitive.memory.write.v1",
        "policy_stamp": {"band": "GREEN"},
        "metadata": {"device_kind": "web"},
        "device_id": "web-browser-123",
    }


# =============================================================================
# TEST GROUP 1: Exact Match Lookup (8 tests)
# =============================================================================


class TestExactMatchLookup:
    """Test exact match policy resolution."""

    def test_red_write_phone_exact(self):
        """Test RED band + write + phone (exact match in DB)."""
        policy = lookup_retention_policy("RED", "cognitive.memory.write", "phone")

        assert policy.retention_policy_id == "pol-red-write-phone"
        assert policy.retention_bucket == "STANDARD"
        assert policy.retention_days == 30
        assert policy.resolved_at_utc  # Timestamp present

    def test_red_write_watch_exact(self):
        """Test RED band + write + watch (exact match, EPHEMERAL bucket)."""
        policy = lookup_retention_policy("RED", "cognitive.memory.write", "watch")

        assert policy.retention_policy_id == "pol-red-write-watch"
        assert policy.retention_bucket == "EPHEMERAL"
        assert policy.retention_days == 7

    def test_amber_write_wildcard_device(self):
        """Test AMBER band + write + any device (wildcard match)."""
        policy = lookup_retention_policy("AMBER", "cognitive.memory.write", "phone")

        # Should match (AMBER, cognitive.memory.write, *)
        assert policy.retention_policy_id == "pol-amber-write-all"
        assert policy.retention_bucket == "STANDARD"
        assert policy.retention_days == 90

    def test_green_write_long_retention(self):
        """Test GREEN band + write (long retention: 7 years)."""
        policy = lookup_retention_policy("GREEN", "cognitive.memory.write", "phone")

        assert policy.retention_policy_id == "pol-green-write-all"
        assert policy.retention_bucket == "STANDARD"
        assert policy.retention_days == 2555  # 7 years

    def test_red_voice_sensitive_bucket(self):
        """Test RED band + voice (SENSITIVE bucket)."""
        policy = lookup_retention_policy("RED", "cognitive.memory.voice", "phone")

        # Should match (RED, cognitive.memory.voice, *)
        assert policy.retention_policy_id == "pol-red-voice-all"
        assert policy.retention_bucket == "SENSITIVE"
        assert policy.retention_days == 7

    def test_amber_photo_long_retention(self):
        """Test AMBER band + photo (365 days retention)."""
        policy = lookup_retention_policy("AMBER", "cognitive.memory.photo", "tablet")

        assert policy.retention_policy_id == "pol-amber-photo-all"
        assert policy.retention_bucket == "STANDARD"
        assert policy.retention_days == 365

    def test_green_photo_long_retention(self):
        """Test GREEN band + photo (7 years retention)."""
        policy = lookup_retention_policy("GREEN", "cognitive.memory.photo", "phone")

        assert policy.retention_policy_id == "pol-green-photo-all"
        assert policy.retention_bucket == "STANDARD"
        assert policy.retention_days == 2555

    def test_amber_voice_sensitive(self):
        """Test AMBER band + voice (SENSITIVE bucket, 30 days)."""
        policy = lookup_retention_policy("AMBER", "cognitive.memory.voice", "phone")

        assert policy.retention_policy_id == "pol-amber-voice-all"
        assert policy.retention_bucket == "SENSITIVE"
        assert policy.retention_days == 30


# =============================================================================
# TEST GROUP 2: Fallback Chain (6 tests)
# =============================================================================


class TestFallbackChain:
    """Test fallback chain when exact match not found."""

    def test_fallback_to_topic_wildcard(self):
        """Test fallback from (band,topic,device) to (band,topic,*)."""
        # RED + write + tablet: no exact match, fallback to (RED, write, *)
        # But (RED, write, *) doesn't exist, so fallback to (RED, *, *)
        policy = lookup_retention_policy("RED", "cognitive.memory.write", "tablet")

        # Should fallback to (RED, *, *)
        assert policy.retention_policy_id == "pol-red-default"
        assert policy.retention_days == 30

    def test_fallback_to_all_wildcards(self):
        """Test fallback from (band,topic,*) to (band,*,*)."""
        # RED + import + phone: no exact or topic wildcard, use (RED, *, *)
        policy = lookup_retention_policy("RED", "cognitive.memory.import", "phone")

        assert policy.retention_policy_id == "pol-red-default"
        assert policy.retention_bucket == "STANDARD"
        assert policy.retention_days == 30

    def test_fallback_amber_default(self):
        """Test AMBER band fallback to (AMBER, *, *)."""
        policy = lookup_retention_policy("AMBER", "cognitive.memory.import", "api")

        assert policy.retention_policy_id == "pol-amber-default"
        assert policy.retention_days == 90

    def test_fallback_green_default(self):
        """Test GREEN band fallback to (GREEN, *, *)."""
        policy = lookup_retention_policy("GREEN", "cognitive.memory.import", "watch")

        assert policy.retention_policy_id == "pol-green-default"
        assert policy.retention_days == 2555

    def test_fallback_unknown_band(self):
        """Test unknown band falls back to system default."""
        policy = lookup_retention_policy("UNKNOWN", "cognitive.memory.write", "phone")

        # Should use system default (no policy for UNKNOWN band)
        assert policy.retention_policy_id == "pol-default-standard"
        assert policy.retention_bucket == DEFAULT_RETENTION_BUCKET
        assert policy.retention_days == DEFAULT_RETENTION_DAYS

    def test_fallback_metrics_tracking(self):
        """Test metrics track fallback chain usage."""
        reset_metrics()

        # Exact match
        lookup_retention_policy("RED", "cognitive.memory.write", "phone")
        metrics1 = get_metrics()
        assert metrics1["exact_match"] == 1

        # Topic wildcard fallback
        lookup_retention_policy("AMBER", "cognitive.memory.write", "tablet")
        metrics2 = get_metrics()
        assert metrics2["fallback_topic_wildcard"] == 1

        # All wildcards fallback
        lookup_retention_policy("RED", "cognitive.memory.import", "phone")
        metrics3 = get_metrics()
        assert metrics3["fallback_all_wildcards"] == 1

        # System default fallback
        lookup_retention_policy("UNKNOWN", "unknown.topic", "unknown")
        metrics4 = get_metrics()
        assert metrics4["fallback_default"] == 1


# =============================================================================
# TEST GROUP 3: Topic Normalization (4 tests)
# =============================================================================


class TestTopicNormalization:
    """Test topic version stripping (v1, v2 suffixes)."""

    def test_strip_v1_suffix(self):
        """Test .v1 suffix is stripped from topic."""
        policy1 = lookup_retention_policy("RED", "cognitive.memory.write.v1", "phone")
        policy2 = lookup_retention_policy("RED", "cognitive.memory.write", "phone")

        # Both should resolve to same policy
        assert policy1.retention_policy_id == policy2.retention_policy_id
        assert policy1.retention_policy_id == "pol-red-write-phone"

    def test_strip_v2_suffix(self):
        """Test .v2 suffix is stripped from topic."""
        policy = lookup_retention_policy("AMBER", "cognitive.memory.photo.v2", "phone")

        # Should match (AMBER, cognitive.memory.photo, *)
        assert policy.retention_policy_id == "pol-amber-photo-all"

    def test_strip_committed_v1_suffix(self):
        """Test .committed.v1 suffix is stripped."""
        policy = lookup_retention_policy("GREEN", "cognitive.memory.write.committed.v1", "web")

        # Should match (GREEN, cognitive.memory.write, *)
        assert policy.retention_policy_id == "pol-green-write-all"

    def test_no_version_suffix(self):
        """Test topics without version suffix work correctly."""
        policy = lookup_retention_policy("RED", "cognitive.memory.voice", "phone")

        assert policy.retention_policy_id == "pol-red-voice-all"
        assert policy.retention_bucket == "SENSITIVE"


# =============================================================================
# TEST GROUP 4: Retention Buckets (3 tests)
# =============================================================================


class TestRetentionBuckets:
    """Test retention bucket classification."""

    def test_standard_bucket(self):
        """Test STANDARD bucket assignment."""
        policy = lookup_retention_policy("GREEN", "cognitive.memory.write", "phone")

        assert policy.retention_bucket == "STANDARD"

    def test_sensitive_bucket(self):
        """Test SENSITIVE bucket assignment."""
        policy = lookup_retention_policy("RED", "cognitive.memory.voice", "phone")

        assert policy.retention_bucket == "SENSITIVE"

    def test_ephemeral_bucket(self):
        """Test EPHEMERAL bucket assignment."""
        policy = lookup_retention_policy("RED", "cognitive.memory.write", "watch")

        assert policy.retention_bucket == "EPHEMERAL"
        assert policy.retention_days == 7  # Short retention


# =============================================================================
# TEST GROUP 5: End-to-End Resolution (6 tests)
# =============================================================================


class TestEndToEndResolution:
    """Test complete retention resolution with async run()."""

    @pytest.mark.asyncio
    async def test_run_red_phone_envelope(self, sample_envelope_red_phone):
        """Test complete resolution with RED band phone envelope."""
        result = await run(sample_envelope_red_phone)

        assert result["retention_policy_id"] == "pol-red-write-phone"
        assert result["retention_bucket"] == "STANDARD"
        assert "retention_resolved_at_utc" in result

    @pytest.mark.asyncio
    async def test_run_amber_photo_envelope(self, sample_envelope_amber_photo):
        """Test complete resolution with AMBER band photo envelope."""
        result = await run(sample_envelope_amber_photo)

        assert result["retention_policy_id"] == "pol-amber-photo-all"
        assert result["retention_bucket"] == "STANDARD"

    @pytest.mark.asyncio
    async def test_run_green_write_envelope(self, sample_envelope_green_write):
        """Test complete resolution with GREEN band write envelope."""
        result = await run(sample_envelope_green_write)

        assert result["retention_policy_id"] == "pol-green-write-all"
        assert result["retention_bucket"] == "STANDARD"

    @pytest.mark.asyncio
    async def test_run_missing_band_defaults_green(self):
        """Test missing band defaults to GREEN."""
        envelope = {
            "topic": "cognitive.memory.write.v1",
            "policy_stamp": {},  # No band
            "metadata": {"device_kind": "phone"},
        }
        result = await run(envelope)

        # Should use GREEN default
        assert result["retention_policy_id"] == "pol-green-write-all"

    @pytest.mark.asyncio
    async def test_run_missing_device_kind_defaults_phone(self):
        """Test missing device_kind defaults to phone."""
        envelope = {
            "topic": "cognitive.memory.write.v1",
            "policy_stamp": {"band": "RED"},
            "metadata": {},  # No device_kind
        }
        result = await run(envelope)

        # Should use phone default
        assert result["retention_policy_id"] == "pol-red-write-phone"

    @pytest.mark.asyncio
    async def test_run_idempotency(self, sample_envelope_red_phone):
        """Test idempotency: same envelope → same result."""
        result1 = await run(sample_envelope_red_phone)
        result2 = await run(sample_envelope_red_phone)

        # Policy ID should be identical
        assert result1["retention_policy_id"] == result2["retention_policy_id"]
        assert result1["retention_bucket"] == result2["retention_bucket"]


# =============================================================================
# TEST GROUP 6: Performance Tests (3 tests)
# =============================================================================


class TestPerformance:
    """Test performance against <3ms P95 budget."""

    @pytest.mark.asyncio
    async def test_run_latency_batch(self, sample_envelope_red_phone):
        """Test async run() latency for batch of 1000 lookups (P95 < 3ms)."""
        latencies = []

        for _ in range(1000):
            start = time.perf_counter()
            await run(sample_envelope_red_phone)
            end = time.perf_counter()
            latencies.append((end - start) * 1000)  # Convert to milliseconds

        latencies.sort()
        p50 = latencies[int(len(latencies) * 0.50)]
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[int(len(latencies) * 0.99)]

        print("\n📊 Latency Results (n=1000):")
        print(f"   P50: {p50:.4f}ms")
        print(f"   P95: {p95:.4f}ms (budget: <3ms)")
        print(f"   P99: {p99:.4f}ms")

        # Performance assertion
        assert p95 < 3.0, f"P95 latency {p95:.4f}ms exceeds 3ms budget"

    @pytest.mark.asyncio
    async def test_throughput_single_thread(self, sample_envelope_red_phone):
        """Test throughput (target: >300 ops/sec single-threaded)."""
        num_ops = 1000
        start = time.perf_counter()

        for _ in range(num_ops):
            await run(sample_envelope_red_phone)

        elapsed = time.perf_counter() - start
        throughput = num_ops / elapsed

        print(f"\n🚀 Throughput: {throughput:,.0f} ops/sec")

        # Throughput assertion (expect >300 ops/sec)
        assert throughput > 300, f"Throughput {throughput:.0f} ops/sec below 300 target"

    def test_lookup_latency(self):
        """Test lookup_retention_policy() latency (<2ms for cached lookups)."""
        latencies = []

        for _ in range(1000):
            start = time.perf_counter()
            lookup_retention_policy("RED", "cognitive.memory.write", "phone")
            end = time.perf_counter()
            latencies.append((end - start) * 1000)

        latencies.sort()
        p95 = latencies[int(len(latencies) * 0.95)]

        print(f"\n⚡ lookup_retention_policy() P95: {p95:.4f}ms")

        # Should be < 2ms for cached lookups
        assert p95 < 2.0, f"P95 latency {p95:.4f}ms exceeds 2ms"


# =============================================================================
# TEST GROUP 7: Metrics Tests (2 tests)
# =============================================================================


class TestMetrics:
    """Test metrics tracking for observability."""

    @pytest.mark.asyncio
    async def test_metrics_tracking(self, sample_envelope_red_phone, sample_envelope_amber_photo):
        """Test metrics increment correctly for different lookups."""
        reset_metrics()
        clear_cache()  # Ensure clean cache state

        # Perform 3 RED lookups, 2 AMBER lookups
        for _ in range(3):
            await run(sample_envelope_red_phone)
        for _ in range(2):
            await run(sample_envelope_amber_photo)

        metrics = get_metrics()

        assert metrics["total_lookups"] == 5
        assert metrics["bucket_standard"] == 5  # All STANDARD bucket
        # Cache will hit after first lookup of each type, so expect 2 unique lookups
        assert metrics["exact_match"] >= 1  # At least one exact match
        assert metrics["fallback_topic_wildcard"] >= 1  # At least one fallback

    def test_reset_metrics(self):
        """Test metrics reset works correctly."""
        # Perform some lookups
        lookup_retention_policy("RED", "cognitive.memory.write", "phone")
        lookup_retention_policy("AMBER", "cognitive.memory.photo", "tablet")

        # Reset
        reset_metrics()

        metrics = get_metrics()
        assert metrics["total_lookups"] == 0
        assert metrics["cache_hits"] == 0
        assert metrics["exact_match"] == 0


# =============================================================================
# TEST GROUP 8: Edge Cases (6 tests)
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_run_with_empty_envelope(self):
        """Test handling of empty envelope (should use defaults)."""
        envelope = {}
        result = await run(envelope)

        # Should use GREEN + empty topic + phone defaults
        assert result["retention_policy_id"] == "pol-green-default"
        assert result["retention_bucket"] == DEFAULT_RETENTION_BUCKET

    @pytest.mark.asyncio
    async def test_run_with_missing_policy_stamp(self):
        """Test handling of missing policy_stamp (defaults to GREEN)."""
        envelope = {
            "topic": "cognitive.memory.write.v1",
            "metadata": {"device_kind": "phone"},
        }
        result = await run(envelope)

        # Should default to GREEN band
        assert result["retention_policy_id"] == "pol-green-write-all"

    @pytest.mark.asyncio
    async def test_run_with_missing_metadata(self):
        """Test handling of missing metadata (defaults to phone)."""
        envelope = {
            "topic": "cognitive.memory.write.v1",
            "policy_stamp": {"band": "RED"},
        }
        result = await run(envelope)

        # Should default to phone device
        assert result["retention_policy_id"] == "pol-red-write-phone"

    def test_cache_clear_resets_lru(self):
        """Test cache clear resets LRU cache."""
        # Perform lookup (populates cache)
        lookup_retention_policy("RED", "cognitive.memory.write", "phone")

        # Clear cache
        clear_cache()

        # Cache should be empty (metrics would show cache miss on next lookup)
        reset_metrics()
        lookup_retention_policy("RED", "cognitive.memory.write", "phone")
        metrics = get_metrics()

        # After cache clear, lookup should still work (rebuilds cache)
        assert metrics["total_lookups"] == 1

    @pytest.mark.asyncio
    async def test_concurrent_lookups(self, sample_envelope_red_phone, sample_envelope_amber_photo):
        """Test concurrent lookups (thread-safety check)."""
        import asyncio

        tasks = []
        for _ in range(50):
            tasks.append(run(sample_envelope_red_phone))
            tasks.append(run(sample_envelope_amber_photo))

        results = await asyncio.gather(*tasks)

        # Verify all 100 results returned
        assert len(results) == 100

        # Verify metrics are correct (100 lookups)
        metrics = get_metrics()
        assert metrics["total_lookups"] == 100

    def test_retention_policy_immutable(self):
        """Test RetentionPolicy is immutable (frozen dataclass)."""
        policy = lookup_retention_policy("RED", "cognitive.memory.write", "phone")

        # Should not be able to modify fields
        with pytest.raises(AttributeError):
            policy.retention_days = 999  # type: ignore


# =============================================================================
# RUN ALL TESTS
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
