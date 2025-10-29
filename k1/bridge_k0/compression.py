"""
Zstd Compression - Payload Size Optimization

Layer: L5 Infrastructure
Component: K0 Bridge → Compression Utility
Priority: P1 (Performance Optimization)
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

Architecture Decision Records:
    - ADR-0025d: Zstd Compression (Level 3, >4KB payloads, 70% reduction)
    - ADR-0001a: K0 Bridge Communication Protocol (payload optimization)

Dependencies:
    Internal:
        - None (standalone utility)
    External:
        - zstandard (Zstd compression library)

Connects To:
    Upstream:
        - k1.bridge_k0.command_client (compress command payloads)
        - k1.bridge_k0.batch_client (compress batches)
        - k1.bridge_k0.protocol (compress before serialization)
    Downstream:
        - K0 ports (all payloads >4KB)

Performance Budgets:
    - Compression: <10ms P95 (input 128KB)
    - Decompression: <5ms P95 (input 38KB compressed)
    - Size reduction: ≥70% (128KB → 38KB)
    - Compression level: 3 (balanced speed/ratio)
    - Threshold: 4KB (skip compression below)

Observability:
    Metrics:
        - k1_k0_bridge_compression_compressed_bytes_total{counter}
        - k1_k0_bridge_compression_uncompressed_bytes_total{counter}
        - k1_k0_bridge_compression_duration_seconds{histogram}
        - k1_k0_bridge_decompression_duration_seconds{histogram}
    Traces:
        - Span: k0_bridge.compression.compress
        - Span: k0_bridge.compression.decompress
    Logs:
        - DEBUG: compression skipped (size < threshold)
        - DEBUG: compression applied (size, compressed_size, ratio)

References:
    - ADR-0025d: Zstd Compression Strategy
    - Research: Facebook Zstandard RFC 8478 (2018)
    - Diagram: architecture_diagrams/k1/k1_complete_with_flows.mmd
    - Test: tests/k1/bridge_k0/test_compression.py
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum

# =============================================================================
# SECTION 1: IMPORTS
# =============================================================================
# Standard library imports
from typing import Optional

# Third-party imports
try:
    import zstandard as zstd  # Zstd compression library
except ModuleNotFoundError as exc:  # pragma: no cover - dependency enforcement
    raise ImportError(
        "zstandard library is required for compression utilities"
    ) from exc

# Internal imports
# Observability (best-effort; fall back to no-ops if module missing)
try:  # pragma: no cover - observability package optional during early integration
    from k1.l5_infrastructure.observability import (  # type: ignore
        create_span,
        emit_counter,
        emit_histogram,
    )
except (ModuleNotFoundError, ImportError):  # pragma: no cover
    def create_span(name: str, **_: object):  # type: ignore
        class _NullSpan:
            def __enter__(self) -> "_NullSpan":
                return self

            def __exit__(self, exc_type, exc_value, traceback) -> None:
                return None

            def set_attribute(self, *_args: object, **_kwargs: object) -> None:
                return None

        return _NullSpan()

    def emit_counter(_name: str, **_labels: object) -> None:
        return None

    def emit_histogram(_name: str, value: float, **_labels: object) -> None:
        return None

# Configure module logger
logger = logging.getLogger(__name__)

# =============================================================================
# SECTION 2: CONSTANTS & CONFIGURATION
# =============================================================================

# TODO(@infrastructure-team): Load from k1/config/k0_bridge.yml (ADR-0025d)
# Assigned to: Issue #L5-1.3.3
DEFAULT_CONFIG = {
    "compression_level": 3,  # Zstd level 3 (balanced speed/ratio)
    "threshold_bytes": 4096,  # 4KB threshold (skip below)
    "compression_timeout_ms": 20,  # 20ms max compression time
    "decompression_timeout_ms": 10,  # 10ms max decompression time
}

# =============================================================================
# SECTION 3: TYPE DEFINITIONS & ENUMS
# =============================================================================


class CompressionStatus(Enum):
    """Compression decision status"""

    COMPRESSED = "COMPRESSED"  # Payload compressed (>4KB)
    SKIPPED = "SKIPPED"  # Compression skipped (<4KB)
    FAILED = "FAILED"  # Compression error


@dataclass
class CompressionConfig:
    """
    Zstd compression configuration.

    Fields:
        compression_level: Zstd level 1-22 (default: 3, balanced speed/ratio)
        threshold_bytes: Minimum payload size for compression (default: 4KB)
        compression_timeout_ms: Max compression time (default: 20ms)
        decompression_timeout_ms: Max decompression time (default: 10ms)
    """

    compression_level: int = DEFAULT_CONFIG["compression_level"]
    threshold_bytes: int = DEFAULT_CONFIG["threshold_bytes"]
    compression_timeout_ms: int = DEFAULT_CONFIG["compression_timeout_ms"]
    decompression_timeout_ms: int = DEFAULT_CONFIG["decompression_timeout_ms"]


@dataclass
class CompressionResult:
    """
    Compression result metadata.

    Fields:
        status: Compression status (COMPRESSED | SKIPPED | FAILED)
        original_size: Original payload size (bytes)
        compressed_size: Compressed payload size (bytes, if compressed)
        compression_ratio: Ratio original/compressed (if compressed)
        compression_time_ms: Time spent compressing (if compressed)
    """

    status: CompressionStatus
    original_size: int
    compressed_size: Optional[int] = None
    compression_ratio: Optional[float] = None
    compression_time_ms: Optional[float] = None


# =============================================================================
# SECTION 4: CORE CLASSES
# =============================================================================


class CompressionUtility:
    """
    Zstd compression utility for K0 Bridge payloads.

    Purpose:
        Compress payloads >4KB with Zstd level 3 (70% size reduction,
        <10ms compression, <5ms decompression), skip compression for <4KB
        payloads (overhead exceeds benefit), used by command_client, batch_client,
        protocol to reduce K0 Bridge bandwidth.

    Compression Strategy (ADR-0025d):
        - Input >4KB: Compress with Zstd level 3
        - Input ≤4KB: Skip compression (overhead too high)
        - Level 3: Balanced speed/ratio (Facebook Zstandard benchmark)
        - Target: 70% reduction (128KB → 38KB)

    Responsibilities:
        1. Compress payloads with Zstd level 3
        2. Decompress payloads
        3. Skip compression for <4KB payloads
        4. Track compression metrics (size, ratio, duration)

    Lifecycle:
        INIT → READY → [compress/decompress] → TERMINATED

    Thread Safety: Yes (stateless, thread-safe)
    Async Safe: No (synchronous API, use asyncio.to_thread if needed)

    Performance Budget (P95):
        - Compression: <10ms (input 128KB)
        - Decompression: <5ms (input 38KB compressed)
        - Size reduction: ≥70%

    Examples:
        >>> config = CompressionConfig(compression_level=3, threshold_bytes=4096)
        >>> compressor = CompressionUtility(config)
        >>>
        >>> # Compress large payload
        >>> payload = b'...' * 30000  # 128KB
        >>> compressed, result = compressor.compress(payload)
        >>> print(result.compression_ratio)  # ~3.4 (70% reduction)
        >>>
        >>> # Skip small payload
        >>> small_payload = b'...' * 1000  # 2KB
        >>> compressed, result = compressor.compress(small_payload)
        >>> print(result.status)  # SKIPPED

    References:
        - ADR-0025d: Zstd Compression Strategy
        - Research: Facebook Zstandard RFC 8478 (2018)
        - Benchmark: Zstd level 3 (70% ratio, 10ms @ 128KB)
    """

    def __init__(self, config: CompressionConfig) -> None:
        """
        Initialize CompressionUtility.

        Args:
            config: CompressionConfig with level, threshold, timeouts

        Raises:
            ValueError: If configuration is invalid

        ADR: ADR-0025d (Zstd Compression Strategy)
        Assigned to: Issue #L5-1.3.3
        """
        # TODO(@infrastructure-team): Implement initialization (ADR-0025d)
        # 1. Validate config (check compression_level 1-22, threshold_bytes >0)
        # 2. Initialize Zstd compressor (level 3)
        # 3. Initialize Zstd decompressor
        if not 1 <= config.compression_level <= 22:
            raise ValueError(
                "compression_level must be between 1 and 22 (ADR-0025d requirement)"
            )
        if config.threshold_bytes <= 0:
            raise ValueError("threshold_bytes must be positive (ADR-0025d requirement)")
        self.config = config
        self._logger = logger
        self._compressor = zstd.ZstdCompressor(level=config.compression_level)
        self._decompressor = zstd.ZstdDecompressor()

    def compress(self, payload: bytes) -> tuple[bytes, CompressionResult]:
        """
        Compress payload with Zstd (if >4KB).

        This method compresses payloads >4KB with Zstd level 3, or skips
        compression for ≤4KB payloads (overhead exceeds benefit).

        Args:
            payload: Raw payload bytes

        Returns:
            Tuple of (compressed_bytes, CompressionResult)
            - If compressed: (compressed_bytes, result with COMPRESSED status)
            - If skipped: (original_bytes, result with SKIPPED status)

        Raises:
            CompressionError: If compression fails

        Performance:
            - Target: <10ms P95 (input 128KB)

        ADR: ADR-0025d (Zstd Compression Strategy)
        Assigned to: Issue #L5-1.3.3
        """
        # TODO(@infrastructure-team): Implement compress (ADR-0025d)
        # 1. Check payload size vs threshold (4KB)
        # 2. If size <= threshold:
        #    - Log DEBUG: compression skipped
        #    - Return (payload, CompressionResult(SKIPPED))
        # 3. If size > threshold:
        #    - Start timer
        #    - Compress with Zstd level 3
        #    - Calculate compression ratio
        #    - Log DEBUG: compression applied
        #    - Emit metrics (compressed_bytes, duration)
        #    - Return (compressed, CompressionResult(COMPRESSED))
        original_size = len(payload)

        if original_size <= self.config.threshold_bytes:
            self._logger.debug(
                "compression_skipped size_bytes=%d threshold_bytes=%d",
                original_size,
                self.config.threshold_bytes,
            )
            emit_counter(
                "k1_k0_bridge_compression_skipped_total",
                reason="below_threshold",
            )
            return payload, CompressionResult(
                status=CompressionStatus.SKIPPED,
                original_size=original_size,
            )

        with create_span(
            "k0_bridge.compression.compress",
            compression_level=self.config.compression_level,
            original_size=original_size,
        ) as span:
            start_time = time.perf_counter()
            try:
                compressed = self._compressor.compress(payload)
            except zstd.ZstdError as exc:  # pragma: no cover - exceptional path
                emit_counter(
                    "k1_k0_bridge_compression_failures_total",
                    reason="compression_error",
                )
                self._logger.exception("compression_failed error=%s", exc)
                raise CompressionError("zstd compression failed") from exc

            compression_time_ms = (time.perf_counter() - start_time) * 1000
            compressed_size = len(compressed)
            ratio = compressed_size / original_size if original_size else 1.0
            span.set_attribute("compression.duration_ms", compression_time_ms)
            span.set_attribute("compression.compressed_size", compressed_size)
            span.set_attribute("compression.ratio", ratio)

        emit_counter(
            "k1_k0_bridge_compression_compressed_bytes_total",
            port="k0_bridge",
            codec="zstd",
            value=compressed_size,
        )
        emit_counter(
            "k1_k0_bridge_compression_uncompressed_bytes_total",
            port="k0_bridge",
            value=original_size,
        )
        emit_histogram(
            "k1_k0_bridge_compression_duration_ms",
            value=compression_time_ms,
            port="k0_bridge",
        )
        emit_histogram(
            "k1_k0_bridge_compression_ratio",
            value=ratio,
            port="k0_bridge",
        )

        self._logger.debug(
            "compression_applied original_size=%d compressed_size=%d ratio=%.4f duration_ms=%.3f",
            original_size,
            compressed_size,
            ratio,
            compression_time_ms,
        )

        return compressed, CompressionResult(
            status=CompressionStatus.COMPRESSED,
            original_size=original_size,
            compressed_size=compressed_size,
            compression_ratio=ratio,
            compression_time_ms=compression_time_ms,
        )

    def decompress(self, compressed: bytes) -> bytes:
        """
        Decompress Zstd-compressed payload.

        Args:
            compressed: Zstd-compressed bytes

        Returns:
            Decompressed payload bytes

        Raises:
            DecompressionError: If decompression fails

        Performance:
            - Target: <5ms P95 (input 38KB compressed)

        ADR: ADR-0025d (Zstd Compression Strategy)
        Assigned to: Issue #L5-1.3.3
        """
        # TODO(@infrastructure-team): Implement decompress (ADR-0025d)
        # 1. Start timer
        # 2. Decompress with Zstd
        # 3. Emit metrics (decompression_duration)
        # 4. Return decompressed bytes
        #
        # import time
        # start_time = time.perf_counter()
        # decompressed = self._decompressor.decompress(compressed)
        # decompression_time_ms = (time.perf_counter() - start_time) * 1000

        with create_span(
            "k0_bridge.compression.decompress",
            compressed_size=len(compressed),
        ) as span:
            start_time = time.perf_counter()
            try:
                decompressed = self._decompressor.decompress(compressed)
            except zstd.ZstdError as exc:  # pragma: no cover - exceptional path
                emit_counter(
                    "k1_k0_bridge_decompression_failures_total",
                    reason="decompression_error",
                )
                self._logger.exception("decompression_failed error=%s", exc)
                raise DecompressionError("zstd decompression failed") from exc
            decompression_time_ms = (time.perf_counter() - start_time) * 1000
            span.set_attribute("decompression.duration_ms", decompression_time_ms)
            span.set_attribute("decompression.output_size", len(decompressed))

        emit_histogram(
            "k1_k0_bridge_decompression_duration_ms",
            value=decompression_time_ms,
            port="k0_bridge",
        )

        self._logger.debug(
            "decompression_completed compressed_size=%d decompressed_size=%d duration_ms=%.3f",
            len(compressed),
            len(decompressed),
            decompression_time_ms,
        )

        return decompressed

    def should_compress(self, payload_size: int) -> bool:
        """
        Check if payload should be compressed.

        Args:
            payload_size: Payload size in bytes

        Returns:
            True if payload >4KB, False otherwise

        ADR: ADR-0025d (Zstd Compression Strategy)
        Assigned to: Issue #L5-1.3.3
        """
        return payload_size > self.config.threshold_bytes


# =============================================================================
# SECTION 5: HELPER FUNCTIONS & EXCEPTIONS
# =============================================================================


class CompressionError(Exception):
    """Raised when compression fails"""

    pass


class DecompressionError(Exception):
    """Raised when decompression fails"""

    pass


def create_compression_utility(
    config: Optional[CompressionConfig] = None,
) -> CompressionUtility:
    """
    Create CompressionUtility with default or provided configuration.

    Args:
        config: CompressionConfig (default: level 3, 4KB threshold)

    Returns:
        CompressionUtility instance

    ADR: ADR-0025d (Zstd Compression Strategy)
    Assigned to: Issue #L5-1.3.3
    """
    if config is None:
        config = CompressionConfig()

    return CompressionUtility(config)


# =============================================================================
# SECTION 6: MODULE EXPORTS & INITIALIZATION
# =============================================================================

__all__ = [
    "CompressionUtility",
    "CompressionConfig",
    "CompressionResult",
    "CompressionStatus",
    "CompressionError",
    "DecompressionError",
    "create_compression_utility",
]


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================
# Metrics to export (Prometheus):
#   - k1_k0_bridge_compression_compressed_bytes_total{counter}
#   - k1_k0_bridge_compression_uncompressed_bytes_total{counter}
#   - k1_k0_bridge_compression_duration_seconds{histogram}
#   - k1_k0_bridge_decompression_duration_seconds{histogram}
#
# Traces to generate (OpenTelemetry):
#   - Span name: k0_bridge.compression.compress
#   - Span name: k0_bridge.compression.decompress
#   - Attributes: original_size, compressed_size, compression_ratio
#
# Logs to emit (structured logging):
#   - Level: DEBUG (compression applied/skipped)
#   - Fields: component='compression', size, compressed_size, ratio
#
# =============================================================================

# =============================================================================
# TESTING REQUIREMENTS (WARD Framework)
# =============================================================================
# Integration tests required:
#   - tests/k1/bridge_k0/test_compression.py
#   - Test compression (>4KB payload → 70% reduction)
#   - Test skip compression (<4KB payload → SKIPPED)
#   - Test decompression (round-trip verification)
#   - Test performance (compression <10ms, decompression <5ms)
#
# No simulation code allowed:
#   - Use real Zstd compression library
#   - Test with real payloads (128KB, 4KB, 2KB)
#   - Integration tests > unit tests
#
# Performance budget tests:
#   - Assert compression <10ms P95 (128KB input)
#   - Assert decompression <5ms P95 (38KB compressed input)
#   - Assert 70% size reduction (128KB → 38KB)
#
# =============================================================================
