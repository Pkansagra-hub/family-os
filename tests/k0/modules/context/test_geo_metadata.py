"""
Tests for M12: Geo Metadata Extraction Module

Test Coverage:
- Exact extraction (GREEN/AMBER/RED bands)
- Missing location fields (geohash/name/type)
- Geohash validation (valid/invalid formats)
- Precision extraction from band
- Masking reason from obligations
- End-to-end extraction
- Performance (<2ms P95)
- Metrics tracking
- Edge cases (empty envelope, concurrent extraction)
"""

import asyncio
import time
from datetime import datetime

import pytest

from k0.modules.context.geo_metadata import (
    extract_geo_metadata,
    get_geo_masking_reason,
    get_geo_precision_from_band,
    get_metrics,
    is_valid_geohash,
    reset_metrics,
    run,
)

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
    obligations: list = None,
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
            "obligations": obligations or [],
        },
    }


# ===========================
# Geohash Validation Tests
# ===========================


def test_valid_geohash_format():
    """Valid geohash passes validation."""
    assert is_valid_geohash("9q8yywkg62") is True
    assert is_valid_geohash("u4pruydqqvj") is True
    assert is_valid_geohash("dr5regw") is True


def test_invalid_geohash_characters():
    """Invalid characters (a,i,l,o) fail validation."""
    assert is_valid_geohash("9q8ailorg2") is False  # Contains a,i,l,o
    assert is_valid_geohash("invalidhash") is False


def test_empty_geohash():
    """Empty or None geohash fails validation."""
    assert is_valid_geohash(None) is False
    assert is_valid_geohash("") is False


def test_numeric_only_geohash():
    """Numeric-only geohash is valid."""
    assert is_valid_geohash("123456789") is True


# ===========================
# Geo Precision Extraction Tests
# ===========================


def test_precision_green_band():
    """GREEN band returns 'full' precision."""
    assert get_geo_precision_from_band("GREEN") == "full"
    metrics = get_metrics()
    assert metrics["precision_green"] == 1


def test_precision_amber_band():
    """AMBER band returns 'geohash-6' precision."""
    assert get_geo_precision_from_band("AMBER") == "geohash-6"
    metrics = get_metrics()
    assert metrics["precision_amber"] == 1


def test_precision_red_band():
    """RED band returns 'geohash-4' precision."""
    assert get_geo_precision_from_band("RED") == "geohash-4"
    metrics = get_metrics()
    assert metrics["precision_red"] == 1


def test_precision_unknown_band():
    """Unknown band returns 'unknown' precision."""
    assert get_geo_precision_from_band("BLUE") == "unknown"
    assert get_geo_precision_from_band(None) == "unknown"
    metrics = get_metrics()
    assert metrics["precision_unknown"] == 2


def test_precision_case_insensitive():
    """Band matching is case-insensitive."""
    assert get_geo_precision_from_band("green") == "full"
    assert get_geo_precision_from_band("AmBeR") == "geohash-6"
    assert get_geo_precision_from_band("red") == "geohash-4"


# ===========================
# Geo Masking Reason Extraction Tests
# ===========================


def test_masking_reason_band_policy():
    """Band policy obligation returns 'band_policy'."""
    obligations = ["mask.location.precision"]
    assert get_geo_masking_reason(obligations) == "band_policy"
    metrics = get_metrics()
    assert metrics["masking_band_policy"] == 1


def test_masking_reason_user_preference():
    """User preference obligation returns 'user_preference'."""
    obligations = ["user.privacy.location"]
    assert get_geo_masking_reason(obligations) == "user_preference"
    metrics = get_metrics()
    assert metrics["masking_user_preference"] == 1


def test_masking_reason_none():
    """No location obligations returns 'none'."""
    obligations = ["mask.text.redact"]
    assert get_geo_masking_reason(obligations) == "none"
    assert get_geo_masking_reason([]) == "none"
    assert get_geo_masking_reason(None) == "none"
    metrics = get_metrics()
    assert metrics["masking_none"] == 3


def test_masking_reason_priority():
    """Band policy takes priority over other obligations."""
    obligations = ["mask.location.precision", "user.privacy.location"]
    assert get_geo_masking_reason(obligations) == "band_policy"


# ===========================
# Exact Extraction Tests
# ===========================


def test_extract_geo_metadata_green_band():
    """GREEN band extraction with full geohash."""
    envelope = create_envelope(
        band="GREEN",
        location_geohash="9q8yywkg62",
        location_name="Olive Garden, Market St",
        location_type="restaurant",
        obligations=["mask.location.precision"],
    )

    geo = extract_geo_metadata(envelope)

    assert geo.geohash_6 == "9q8yyw"  # Truncated to 6 chars
    assert geo.location_name == "Olive Garden, Market St"
    assert geo.location_type == "restaurant"
    assert geo.geo_precision_external == "full"
    assert geo.geo_masking_reason == "band_policy"
    assert geo.geo_metadata_extracted_at_utc  # Timestamp present


def test_extract_geo_metadata_amber_band():
    """AMBER band extraction with geohash-6 precision."""
    envelope = create_envelope(
        band="AMBER",
        location_geohash="9q8yyw",
        location_name="Downtown SF",
        location_type="neighborhood",
        obligations=["mask.location.precision"],
    )

    geo = extract_geo_metadata(envelope)

    assert geo.geohash_6 == "9q8yyw"
    assert geo.location_name == "Downtown SF"
    assert geo.location_type == "neighborhood"
    assert geo.geo_precision_external == "geohash-6"
    assert geo.geo_masking_reason == "band_policy"


def test_extract_geo_metadata_red_band():
    """RED band extraction with geohash-4 precision."""
    envelope = create_envelope(
        band="RED",
        location_geohash="9q8y",
        location_name="San Francisco",
        location_type="city",
        obligations=["mask.location.precision"],
    )

    geo = extract_geo_metadata(envelope)

    assert geo.geohash_6 == "9q8y"  # Less than 6 chars, kept as-is
    assert geo.location_name == "San Francisco"
    assert geo.location_type == "city"
    assert geo.geo_precision_external == "geohash-4"
    assert geo.geo_masking_reason == "band_policy"


# ===========================
# Missing Fields Tests
# ===========================


def test_missing_geohash():
    """Missing geohash returns None."""
    envelope = create_envelope(location_geohash=None)
    geo = extract_geo_metadata(envelope)

    assert geo.geohash_6 is None
    metrics = get_metrics()
    assert metrics["geohash_missing"] == 1


def test_missing_location_name():
    """Missing location_name returns None."""
    envelope = create_envelope(location_name=None)
    geo = extract_geo_metadata(envelope)

    assert geo.location_name is None
    metrics = get_metrics()
    assert metrics["location_name_missing"] == 1


def test_missing_location_type():
    """Missing location_type returns None."""
    envelope = create_envelope(location_type=None)
    geo = extract_geo_metadata(envelope)

    assert geo.location_type is None
    metrics = get_metrics()
    assert metrics["location_type_missing"] == 1


def test_missing_all_location_fields():
    """Missing all location fields returns None for all."""
    envelope = {
        "body": {},
        "policy_stamp": {"band": "GREEN", "obligations": []},
    }

    geo = extract_geo_metadata(envelope)

    assert geo.geohash_6 is None
    assert geo.location_name is None
    assert geo.location_type is None
    assert geo.geo_precision_external == "full"
    assert geo.geo_masking_reason == "none"


def test_invalid_geohash_format():
    """Invalid geohash format returns None."""
    envelope = create_envelope(location_geohash="invalid-hash-with-dashes")
    geo = extract_geo_metadata(envelope)

    assert geo.geohash_6 is None
    metrics = get_metrics()
    assert metrics["invalid_geohash_format"] == 1


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
        obligations=["mask.location.precision"],
    )

    result = await run(envelope)

    assert result["geohash_6"] == "9q8yyw"
    assert result["location_name"] == "Olive Garden, Market St"
    assert result["location_type"] == "restaurant"
    assert result["geo_precision_external"] == "full"
    assert result["geo_masking_reason"] == "band_policy"
    assert "geo_metadata_extracted_at_utc" in result


@pytest.mark.asyncio
async def test_run_red_band_minimal():
    """End-to-end: RED band minimal fields."""
    envelope = create_envelope(
        band="RED",
        location_geohash="9q8y",
        location_name=None,
        location_type=None,
        obligations=["mask.location.precision"],
    )

    result = await run(envelope)

    assert result["geohash_6"] == "9q8y"
    assert result["location_name"] is None
    assert result["location_type"] is None
    assert result["geo_precision_external"] == "geohash-4"
    assert result["geo_masking_reason"] == "band_policy"


@pytest.mark.asyncio
async def test_run_empty_envelope():
    """End-to-end: Empty envelope returns defaults."""
    envelope = {"body": {}, "policy_stamp": {}}

    result = await run(envelope)

    assert result["geohash_6"] is None
    assert result["location_name"] is None
    assert result["location_type"] is None
    assert result["geo_precision_external"] == "unknown"
    assert result["geo_masking_reason"] == "none"


@pytest.mark.asyncio
async def test_idempotency():
    """Multiple runs return same results."""
    envelope = create_envelope()

    result1 = await run(envelope)
    result2 = await run(envelope)

    # Timestamps may differ, so compare other fields
    assert result1["geohash_6"] == result2["geohash_6"]
    assert result1["location_name"] == result2["location_name"]
    assert result1["geo_precision_external"] == result2["geo_precision_external"]


# ===========================
# Performance Tests
# ===========================


@pytest.mark.asyncio
async def test_performance_under_2ms():
    """Extraction completes in <2ms P95."""
    envelope = create_envelope()

    latencies = []
    for _ in range(1000):
        start = time.perf_counter()
        await run(envelope)
        latency_ms = (time.perf_counter() - start) * 1000
        latencies.append(latency_ms)

    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95)]

    print("\nM12 Performance:")
    print(f"  P50: {latencies[500]:.4f}ms")
    print(f"  P95: {p95:.4f}ms")
    print(f"  P99: {latencies[990]:.4f}ms")

    assert p95 < 2.0, f"P95 latency {p95:.4f}ms exceeds 2ms budget"


def test_extract_geo_metadata_performance():
    """Synchronous extraction is fast."""
    envelope = create_envelope()

    latencies = []
    for _ in range(1000):
        start = time.perf_counter()
        extract_geo_metadata(envelope)
        latency_ms = (time.perf_counter() - start) * 1000
        latencies.append(latency_ms)

    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95)]

    print("\nExtract Performance:")
    print(f"  P95: {p95:.4f}ms")

    assert p95 < 1.0, f"Extract P95 {p95:.4f}ms exceeds 1ms budget"


def test_throughput():
    """Measure ops/sec throughput."""
    envelope = create_envelope()

    start = time.perf_counter()
    count = 10000
    for _ in range(count):
        extract_geo_metadata(envelope)
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

    # Extract 3 envelopes
    extract_geo_metadata(create_envelope(band="GREEN"))
    extract_geo_metadata(create_envelope(band="AMBER"))
    extract_geo_metadata(create_envelope(band="RED", location_name=None))

    metrics = get_metrics()

    assert metrics["total_extractions"] == 3
    assert metrics["geohash_present"] == 3
    assert metrics["location_name_present"] == 2
    assert metrics["location_name_missing"] == 1
    assert metrics["precision_green"] == 1
    assert metrics["precision_amber"] == 1
    assert metrics["precision_red"] == 1


def test_metrics_reset():
    """Metrics reset clears all counters."""
    extract_geo_metadata(create_envelope())

    metrics_before = get_metrics()
    assert metrics_before["total_extractions"] > 0

    reset_metrics()

    metrics_after = get_metrics()
    assert metrics_after["total_extractions"] == 0
    assert all(v == 0 for v in metrics_after.values())


# ===========================
# Edge Cases
# ===========================


def test_geohash_less_than_6_chars():
    """Geohash shorter than 6 chars is kept as-is."""
    envelope = create_envelope(location_geohash="9q8")
    geo = extract_geo_metadata(envelope)

    assert geo.geohash_6 == "9q8"  # Not truncated


def test_geohash_exactly_6_chars():
    """Geohash with exactly 6 chars is kept as-is."""
    envelope = create_envelope(location_geohash="9q8yyw")
    geo = extract_geo_metadata(envelope)

    assert geo.geohash_6 == "9q8yyw"


def test_missing_body():
    """Missing body returns None for all fields."""
    envelope = {"policy_stamp": {"band": "GREEN"}}
    geo = extract_geo_metadata(envelope)

    assert geo.geohash_6 is None
    assert geo.location_name is None
    assert geo.location_type is None


def test_missing_policy_stamp():
    """Missing policy_stamp uses defaults."""
    envelope = {
        "body": {
            "location_geohash": "9q8yyw",
            "location_name": "SF",
            "location_type": "city",
        }
    }

    geo = extract_geo_metadata(envelope)

    assert geo.geohash_6 == "9q8yyw"
    assert geo.geo_precision_external == "unknown"
    assert geo.geo_masking_reason == "none"


@pytest.mark.asyncio
async def test_concurrent_extraction():
    """Concurrent extractions work correctly."""
    envelope = create_envelope()

    tasks = [run(envelope) for _ in range(10)]
    results = await asyncio.gather(*tasks)

    # All should succeed
    assert len(results) == 10
    assert all(r["geohash_6"] == "9q8yyw" for r in results)


def test_timestamp_format():
    """Timestamp is ISO 8601 with timezone."""
    envelope = create_envelope()
    geo = extract_geo_metadata(envelope)

    # Parse timestamp to verify format
    ts = datetime.fromisoformat(geo.geo_metadata_extracted_at_utc)
    assert ts.tzinfo is not None  # Has timezone
    assert ts.year >= 2025
    assert ts.year >= 2025
