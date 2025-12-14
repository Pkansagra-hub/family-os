"""
Tests for M15: Spatial Minimal Enrichment Module

Test Coverage:
- Band-based geohash truncation (GREEN/AMBER/RED)
- Missing geohash handling
- Missing band defaults (GREEN)
- Location name/type copying
- End-to-end minimization
- Performance (<3ms P95)
- Metrics tracking
- Edge cases (empty envelope, concurrent)
"""

import asyncio
import json
import time
from datetime import datetime
from unittest.mock import Mock

import pytest

from k0.modules.context.spatial_minimal import (
    BAND_PRECISION_MAP,
    get_metrics,
    minimize_spatial_fields,
    reset_metrics,
    run,
    truncate_geohash,
)

# ===========================
# Mock Classes for Phase 2
# ===========================


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


# ===========================
# Fixtures
# ===========================


@pytest.fixture(autouse=True)
def reset_module_metrics():
    """Reset metrics before each test."""
    reset_metrics()
    yield
    reset_metrics()


def create_envelope(
    band: str = "GREEN",
    location_geohash: str = "9q8yywkg62",
    location_name: str = "Olive Garden, Market St",
    location_type: str = "restaurant",
) -> dict:
    """Helper to create test envelope."""
    return {
        "body": {
            "location_geohash": location_geohash,
            "location_name": location_name,
            "location_type": location_type,
        },
        "policy_stamp": {
            "band": band,
        },
    }


# ===========================
# Band Precision Mapping Tests
# ===========================


def test_band_precision_map():
    """Verify band precision configuration."""
    assert BAND_PRECISION_MAP["GREEN"] == 6
    assert BAND_PRECISION_MAP["AMBER"] == 4
    assert BAND_PRECISION_MAP["RED"] == 0


# ===========================
# Geohash Truncation Tests
# ===========================


def test_truncate_green_band_full():
    """GREEN band keeps full geohash-6."""
    result = truncate_geohash("9q8yywkg62", "GREEN")
    assert result == "9q8yyw"  # Truncated to 6 chars

    metrics = get_metrics()
    assert metrics["green_band_full"] == 1
    assert metrics["geohash_present"] == 1


def test_truncate_amber_band_to_4():
    """AMBER band truncates to geohash-4."""
    result = truncate_geohash("9q8yywkg62", "AMBER")
    assert result == "9q8y"  # Truncated to 4 chars

    metrics = get_metrics()
    assert metrics["amber_band_truncated"] == 1
    assert metrics["geohash_present"] == 1


def test_truncate_red_band_null():
    """RED band returns NULL (maximum privacy)."""
    result = truncate_geohash("9q8yywkg62", "RED")
    assert result is None

    metrics = get_metrics()
    assert metrics["red_band_null"] == 1
    assert metrics["geohash_missing"] == 0  # Geohash was present but returned None


def test_truncate_missing_geohash():
    """Missing geohash returns None."""
    result = truncate_geohash(None, "GREEN")
    assert result is None

    metrics = get_metrics()
    assert metrics["geohash_missing"] == 1


def test_truncate_missing_band_defaults_green():
    """Missing band defaults to GREEN (6 chars)."""
    result = truncate_geohash("9q8yywkg62", None)
    assert result == "9q8yyw"  # GREEN default

    metrics = get_metrics()
    assert metrics["band_unknown"] == 1
    assert metrics["green_band_full"] == 1


def test_truncate_case_insensitive():
    """Band matching is case-insensitive."""
    assert truncate_geohash("9q8yywkg62", "green") == "9q8yyw"
    assert truncate_geohash("9q8yywkg62", "AmBeR") == "9q8y"
    assert truncate_geohash("9q8yywkg62", "red") is None


def test_truncate_short_geohash():
    """Geohash shorter than precision is kept as-is."""
    # Geohash-3 with GREEN (precision 6)
    result = truncate_geohash("9q8", "GREEN")
    assert result == "9q8"  # Too short to truncate

    # Geohash-3 with AMBER (precision 4)
    result = truncate_geohash("9q8", "AMBER")
    assert result == "9q8"  # Too short to truncate


def test_truncate_exact_precision():
    """Geohash matching exact precision is kept as-is."""
    result = truncate_geohash("9q8yyw", "GREEN")
    assert result == "9q8yyw"  # Already 6 chars

    result = truncate_geohash("9q8y", "AMBER")
    assert result == "9q8y"  # Already 4 chars


# ===========================
# Minimize Spatial Fields Tests
# ===========================


def test_minimize_green_band_full():
    """GREEN band: Full geohash-6 with location metadata."""
    envelope = create_envelope(
        band="GREEN",
        location_geohash="9q8yywkg62",
        location_name="Olive Garden, Market St",
        location_type="restaurant",
    )

    spatial = minimize_spatial_fields(envelope)

    assert spatial.geohash_6 == "9q8yyw"
    assert spatial.location_name == "Olive Garden, Market St"
    assert spatial.location_type == "restaurant"
    assert spatial.spatial_minimized_at_utc  # Timestamp present


def test_minimize_amber_band_truncated():
    """AMBER band: Truncated geohash-4."""
    envelope = create_envelope(
        band="AMBER",
        location_geohash="9q8yywkg62",
        location_name="Downtown SF",
        location_type="neighborhood",
    )

    spatial = minimize_spatial_fields(envelope)

    assert spatial.geohash_6 == "9q8y"  # Truncated to 4
    assert spatial.location_name == "Downtown SF"
    assert spatial.location_type == "neighborhood"


def test_minimize_red_band_null():
    """RED band: No geohash (NULL for privacy)."""
    envelope = create_envelope(
        band="RED",
        location_geohash="9q8yywkg62",
        location_name="San Francisco",
        location_type="city",
    )

    spatial = minimize_spatial_fields(envelope)

    assert spatial.geohash_6 is None  # RED band omits geohash
    assert spatial.location_name == "San Francisco"
    assert spatial.location_type == "city"


def test_minimize_missing_geohash():
    """Missing geohash returns None."""
    envelope = {
        "body": {
            "location_name": "Unknown Location",
            "location_type": "unknown",
        },
        "policy_stamp": {"band": "GREEN"},
    }

    spatial = minimize_spatial_fields(envelope)

    assert spatial.geohash_6 is None
    assert spatial.location_name == "Unknown Location"
    assert spatial.location_type == "unknown"


def test_minimize_missing_location_name():
    """Missing location_name returns None."""
    envelope = create_envelope(location_name=None)
    envelope["body"].pop("location_name", None)

    spatial = minimize_spatial_fields(envelope)

    assert spatial.location_name is None
    metrics = get_metrics()
    assert metrics["location_name_missing"] == 1


def test_minimize_missing_location_type():
    """Missing location_type returns None."""
    envelope = create_envelope(location_type=None)
    envelope["body"].pop("location_type", None)

    spatial = minimize_spatial_fields(envelope)

    assert spatial.location_type is None
    metrics = get_metrics()
    assert metrics["location_type_missing"] == 1


def test_minimize_missing_all_fields():
    """Missing all fields returns None for all."""
    envelope = {"body": {}, "policy_stamp": {"band": "GREEN"}}

    spatial = minimize_spatial_fields(envelope)

    assert spatial.geohash_6 is None
    assert spatial.location_name is None
    assert spatial.location_type is None


# ===========================
# End-to-End Tests
# ===========================


@pytest.mark.asyncio
async def test_run_green_band_full_envelope():
    """End-to-end: GREEN band full envelope."""
    envelope = create_envelope(
        band="GREEN",
        location_geohash="9q8yywkg62",
        location_name="Olive Garden, Market St",
        location_type="restaurant",
    )

    message, context, config = make_test_call(envelope)
    result = await run(message, context, **config)

    assert result["geohash_6"] == "9q8yyw"
    assert result["location_name"] == "Olive Garden, Market St"
    assert result["location_type"] == "restaurant"
    assert "spatial_minimized_at_utc" in result


@pytest.mark.asyncio
async def test_run_amber_band_truncated():
    """End-to-end: AMBER band with geohash-4."""
    envelope = create_envelope(
        band="AMBER",
        location_geohash="9q8yywkg62",
        location_name="Downtown",
        location_type="neighborhood",
    )

    message, context, config = make_test_call(envelope)
    result = await run(message, context, **config)

    assert result["geohash_6"] == "9q8y"  # Truncated to 4
    assert result["location_name"] == "Downtown"
    assert result["location_type"] == "neighborhood"


@pytest.mark.asyncio
async def test_run_red_band_null_geohash():
    """End-to-end: RED band with NULL geohash."""
    envelope = create_envelope(
        band="RED",
        location_geohash="9q8yywkg62",
        location_name="City",
        location_type="city",
    )

    message, context, config = make_test_call(envelope)
    result = await run(message, context, **config)

    assert result["geohash_6"] is None  # RED band omits
    assert result["location_name"] == "City"
    assert result["location_type"] == "city"


@pytest.mark.asyncio
async def test_run_empty_envelope():
    """End-to-end: Empty envelope returns None for all fields."""
    envelope = {"body": {}, "policy_stamp": {}}

    message, context, config = make_test_call(envelope)
    result = await run(message, context, **config)

    assert result["geohash_6"] is None
    assert result["location_name"] is None
    assert result["location_type"] is None


@pytest.mark.asyncio
async def test_idempotency():
    """Multiple runs return same results."""
    envelope = create_envelope()

    message1, context1, config1 = make_test_call(envelope)
    result1 = await run(message1, context1, **config1)
    message2, context2, config2 = make_test_call(envelope)
    result2 = await run(message2, context2, **config2)

    # Timestamps may differ, so compare other fields
    assert result1["geohash_6"] == result2["geohash_6"]
    assert result1["location_name"] == result2["location_name"]
    assert result1["location_type"] == result2["location_type"]


# ===========================
# Performance Tests
# ===========================


@pytest.mark.asyncio
async def test_performance_under_3ms():
    """Minimization completes in <3ms P95."""
    envelope = create_envelope()

    latencies = []
    for _ in range(1000):
        message, context, config = make_test_call(envelope)
        start = time.perf_counter()
        await run(message, context, **config)
        latency_ms = (time.perf_counter() - start) * 1000
        latencies.append(latency_ms)

    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95)]

    print("\nM15 Performance:")
    print(f"  P50: {latencies[500]:.4f}ms")
    print(f"  P95: {p95:.4f}ms")
    print(f"  P99: {latencies[990]:.4f}ms")

    assert p95 < 3.0, f"P95 latency {p95:.4f}ms exceeds 3ms budget"


def test_minimize_spatial_fields_performance():
    """Synchronous minimization is fast."""
    envelope = create_envelope()

    latencies = []
    for _ in range(1000):
        start = time.perf_counter()
        minimize_spatial_fields(envelope)
        latency_ms = (time.perf_counter() - start) * 1000
        latencies.append(latency_ms)

    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95)]

    print("\nMinimize Performance:")
    print(f"  P95: {p95:.4f}ms")

    assert p95 < 1.0, f"Minimize P95 {p95:.4f}ms exceeds 1ms budget"


def test_throughput():
    """Measure ops/sec throughput."""
    envelope = create_envelope()

    start = time.perf_counter()
    count = 10000
    for _ in range(count):
        minimize_spatial_fields(envelope)
    duration = time.perf_counter() - start

    ops_per_sec = count / duration
    print(f"\nThroughput: {ops_per_sec:,.0f} ops/sec")

    assert ops_per_sec > 100_000, f"Throughput {ops_per_sec:,.0f} ops/sec too low"


# ===========================
# Metrics Tests
# ===========================


def test_metrics_tracking():
    """Metrics track all operations."""
    reset_metrics()

    # Minimize 3 envelopes
    minimize_spatial_fields(create_envelope(band="GREEN"))
    minimize_spatial_fields(create_envelope(band="AMBER"))
    minimize_spatial_fields(create_envelope(band="RED"))

    metrics = get_metrics()

    assert metrics["total_minimizations"] == 3
    assert metrics["green_band_full"] == 1
    assert metrics["amber_band_truncated"] == 1
    assert metrics["red_band_null"] == 1


def test_metrics_reset():
    """Metrics reset clears all counters."""
    minimize_spatial_fields(create_envelope())

    metrics_before = get_metrics()
    assert metrics_before["total_minimizations"] > 0

    reset_metrics()

    metrics_after = get_metrics()
    assert metrics_after["total_minimizations"] == 0
    assert all(v == 0 for v in metrics_after.values())


# ===========================
# Edge Cases
# ===========================


def test_missing_body():
    """Missing body returns None for all fields."""
    envelope = {"policy_stamp": {"band": "GREEN"}}
    spatial = minimize_spatial_fields(envelope)

    assert spatial.geohash_6 is None
    assert spatial.location_name is None
    assert spatial.location_type is None


def test_missing_policy_stamp():
    """Missing policy_stamp defaults to GREEN."""
    envelope = {
        "body": {
            "location_geohash": "9q8yywkg62",
            "location_name": "Place",
            "location_type": "location",
        }
    }

    spatial = minimize_spatial_fields(envelope)

    assert spatial.geohash_6 == "9q8yyw"  # GREEN default (6 chars)
    metrics = get_metrics()
    assert metrics["band_unknown"] == 1


@pytest.mark.asyncio
async def test_concurrent_minimization():
    """Concurrent minimizations work correctly."""
    envelope = create_envelope()

    tasks = []
    for _ in range(10):
        message, context, config = make_test_call(envelope)
        tasks.append(run(message, context, **config))

    results = await asyncio.gather(*tasks)

    # All should succeed
    assert len(results) == 10
    assert all(r["geohash_6"] == "9q8yyw" for r in results)


def test_timestamp_format():
    """Timestamp is ISO 8601 with timezone."""
    envelope = create_envelope()
    spatial = minimize_spatial_fields(envelope)

    # Parse timestamp to verify format
    ts = datetime.fromisoformat(spatial.spatial_minimized_at_utc)
    assert ts.tzinfo is not None  # Has timezone
    assert ts.year >= 2025


def test_geohash_longer_than_precision():
    """Geohash longer than precision is properly truncated."""
    # Geohash-9 truncated to 6 (GREEN)
    result = truncate_geohash("9q8yywkg6", "GREEN")
    assert result == "9q8yyw"
    assert len(result) == 6

    # Geohash-9 truncated to 4 (AMBER)
    result = truncate_geohash("9q8yywkg6", "AMBER")
    assert result == "9q8y"
    assert len(result) == 4


def test_unknown_band_defaults_to_green():
    """Unknown band defaults to GREEN (6 chars)."""
    result = truncate_geohash("9q8yywkg62", "BLUE")
    assert result == "9q8yyw"  # GREEN default


def test_immutability():
    """SpatialMinimal dataclass is immutable."""
    spatial = minimize_spatial_fields(create_envelope())

    with pytest.raises(AttributeError):
        spatial.geohash_6 = "new_value"


def test_band_specific_metrics():
    """Each band increments correct metrics."""
    reset_metrics()

    truncate_geohash("9q8yyw", "GREEN")
    truncate_geohash("9q8yyw", "AMBER")
    truncate_geohash("9q8yyw", "RED")

    metrics = get_metrics()
    assert metrics["green_band_full"] == 1
    assert metrics["amber_band_truncated"] == 1
    assert metrics["red_band_null"] == 1
    assert metrics["red_band_null"] == 1
