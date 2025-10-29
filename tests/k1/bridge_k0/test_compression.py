"""Integration tests for K0 Bridge compression utilities."""

import time

import pytest

from k1.bridge_k0.compression import (
    CompressionConfig,
    CompressionStatus,
    CompressionUtility,
)


@pytest.fixture()
def compression_utility() -> CompressionUtility:
    """Return a compression utility configured with defaults (ADR-0025d)."""

    return CompressionUtility(CompressionConfig())


def _make_payload(size: int) -> bytes:
    """Create highly compressible payload of the given size."""

    pattern = b"FamilyOS-Compression-Rocks-"
    repeats = (size // len(pattern)) + 1
    return (pattern * repeats)[:size]


def test_should_compress_threshold(compression_utility: CompressionUtility) -> None:
    """Compression should only trigger when payload exceeds 4KB threshold (ADR-0025d)."""

    assert compression_utility.should_compress(CompressionConfig().threshold_bytes) is False
    assert compression_utility.should_compress(CompressionConfig().threshold_bytes + 1) is True


def test_compress_skips_small_payload(compression_utility: CompressionUtility) -> None:
    """Payloads below threshold should be returned untouched with SKIPPED status."""

    payload = _make_payload(2048)  # 2KB < 4KB threshold

    compressed, result = compression_utility.compress(payload)

    assert compressed == payload
    assert result.status is CompressionStatus.SKIPPED
    assert result.original_size == len(payload)
    assert result.compressed_size is None
    assert result.compression_ratio is None


def test_compress_and_decompress_roundtrip(compression_utility: CompressionUtility) -> None:
    """Large payloads should compress to ≤40% size and round-trip losslessly."""

    payload = _make_payload(131_072)  # 128KB payload for performance budget check

    compressed, result = compression_utility.compress(payload)

    assert result.status is CompressionStatus.COMPRESSED
    assert result.compressed_size is not None
    assert result.compression_ratio is not None
    assert result.compressed_size < len(payload)
    assert result.compression_ratio <= 0.40  # ADR-0025d minimum ratio target
    assert result.compression_time_ms is not None
    assert result.compression_time_ms <= compression_utility.config.compression_timeout_ms

    decompressed = compression_utility.decompress(compressed)
    assert decompressed == payload

    start = time.perf_counter()
    _ = compression_utility.decompress(compressed)
    decompression_time_ms = (time.perf_counter() - start) * 1000
    assert decompression_time_ms <= compression_utility.config.decompression_timeout_ms


def test_compress_handles_exact_threshold_plus_one(compression_utility: CompressionUtility) -> None:
    """Payload size equal to threshold should skip; threshold+1 should compress."""

    threshold = compression_utility.config.threshold_bytes
    payload_threshold = _make_payload(threshold)
    payload_threshold_plus_one = _make_payload(threshold + 1)

    small_compressed, small_result = compression_utility.compress(payload_threshold)
    assert small_compressed == payload_threshold
    assert small_result.status is CompressionStatus.SKIPPED

    large_compressed, large_result = compression_utility.compress(payload_threshold_plus_one)
    assert large_result.status is CompressionStatus.COMPRESSED
    assert len(large_compressed) < len(payload_threshold_plus_one)
