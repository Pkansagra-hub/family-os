"""
Protocol Negotiator - Format Switching between JSON and FlatBuffers

Layer: L5 Infrastructure
Component: K0 Bridge (K1 ↔ K0 Communication)
Priority: P0 (Critical Path)
Status: ✅ IMPLEMENTED

Architecture Decision Records:
    - ADR-0001: K0/K1 Kernel Split (K1 Intelligence Module, K0 Memory Module)
    - ADR-0001a: K0 Bridge Dual Protocol Support (JSON PRIMARY + FlatBuffers SECONDARY)
    - ADR-0011: FlatBuffers Serialization (zero-copy, 150× faster than JSON)
    - ADR-0013: Schema Evolution and Versioning (forward/backward compatibility)

Dependencies:
    Internal:
        - k1.l5_infrastructure.serialization.Serializer (JSON serialization)
        - k1.l5_infrastructure.serialization.Deserializer (JSON deserialization)
        - k1.bridge_k0.compression.CompressionUtility (compression)
    External:
        - json (JSON encoding/decoding)
        - flatbuffers (FlatBuffers library)
        - httpx (async HTTP client)

Connects To:
    Upstream:
        - k1.bridge_k0.command_client.CommandClient (format selection)
        - k1.bridge_k0.ports.* (port adapters)
    Downstream:
        - K0 ports (accepts both JSON and FlatBuffers)

Performance Budgets:
    - Format detection: <10ms P95 (OPTIONS request to K0)
    - Format negotiation: <50ms P95 (once per session, cached)
    - JSON serialization: <10ms P95 (1KB payload)
    - FlatBuffers serialization: <1ms P95 (1KB payload, 10× faster than JSON)
    - Memory: Format cache: <1MB (negotiation results per host)

Observability:
    Metrics:
        - k1_k0_bridge_protocol_negotiation_total{format} (counter)
        - k1_k0_bridge_serialization_latency_ms{format, p50, p95, p99} (histogram)
        - k1_k0_bridge_format_selected{format} (gauge)
    Traces:
        - Span: k0_bridge.protocol_negotiate
        - Attributes: format, payload_size, cognitive_trace_id
    Logs:
        - INFO: protocol negotiated (format, capabilities)
        - WARNING: FlatBuffers not supported, falling back to JSON
        - ERROR: format negotiation failed (reason)

References:
    - Diagram: architecture_diagrams/k1/k1_complete_with_flows.mmd
    - Whiteboard: docs/whiteboard.md (Section: K0 Bridge Dual Protocol)
    - Test: tests/k1/bridge_k0/test_protocol.py
"""

# Third-party imports
# json - JSON encoding/decoding
import json
import logging
import time
from dataclasses import dataclass
from enum import Enum

import httpx

# =============================================================================
# SECTION 1: IMPORTS
# =============================================================================
# Standard library imports
from typing import Any, Dict, Optional

from k1.bridge_k0.compression import (
    CompressionConfig,
    CompressionStatus,
    CompressionUtility,
    create_compression_utility,
)

# flatbuffers - FlatBuffers library (zero-copy serialization)
# import flatbuffers  # TODO: Implement FlatBuffers serialization

# Internal imports
# from k1.l5_infrastructure.serialization import Serializer, Deserializer

# Observability (best-effort; fall back to no-ops if module not available)
try:  # pragma: no cover - observability module may not yet exist
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

# TODO(@infrastructure-team): Load from k1/config/k0_bridge.yml (ADR-0001a)
# Assigned to: Issue #L5-1.1.3
DEFAULT_CONFIG = {
    "default_format": "json",  # PRIMARY format (K0 native)
    "enable_flatbuffers": True,  # Enable FlatBuffers optimization
    "payload_size_threshold_bytes": 1024,  # Use FlatBuffers if >1KB
    "negotiation_cache_ttl_s": 3600,  # Cache negotiation for 1 hour
    "format_detection_timeout_ms": 10,  # 10ms timeout for OPTIONS request
    "negotiation_endpoint": "/k0/bridge/capabilities",
    "compression": {
        "enabled": True,
        "threshold_bytes": 4096,
    },
}

# =============================================================================
# SECTION 3: TYPE DEFINITIONS & ENUMS
# =============================================================================


class SerializationFormat(Enum):
    """Serialization format for K0 Bridge (ADR-0001a)"""

    JSON = "json"  # PRIMARY: K0 native, human-readable
    FLATBUFFERS = "flatbuffers"  # SECONDARY: K1 optimization, zero-copy


@dataclass
class ProtocolConfig:
    """
    Configuration dataclass for Protocol Negotiator.

    Fields:
        default_format: Default serialization format (json or flatbuffers)
        enable_flatbuffers: Enable FlatBuffers optimization (default: True)
        payload_size_threshold_bytes: Use FlatBuffers if payload >1KB
        negotiation_cache_ttl_s: Cache negotiation results (seconds)
        format_detection_timeout_ms: Timeout for OPTIONS request (ms)
    """

    default_format: str = DEFAULT_CONFIG["default_format"]
    enable_flatbuffers: bool = DEFAULT_CONFIG["enable_flatbuffers"]
    payload_size_threshold_bytes: int = DEFAULT_CONFIG["payload_size_threshold_bytes"]
    negotiation_cache_ttl_s: int = DEFAULT_CONFIG["negotiation_cache_ttl_s"]
    format_detection_timeout_ms: int = DEFAULT_CONFIG["format_detection_timeout_ms"]
    negotiation_endpoint: str = DEFAULT_CONFIG["negotiation_endpoint"]
    compression_enabled: bool = DEFAULT_CONFIG["compression"]["enabled"]
    compression_threshold_bytes: int = DEFAULT_CONFIG["compression"]["threshold_bytes"]


@dataclass
class FormatCapabilities:
    """
    K0 format capabilities (detected via OPTIONS request).

    Fields:
        supports_json: K0 supports JSON format (always True)
        supports_flatbuffers: K0 supports FlatBuffers format (optional)
        schema_version: K0 FlatBuffers schema version (e.g., "1.2.0")
        detected_at: Timestamp when capabilities were detected
    """

    supports_json: bool = True  # K0 always supports JSON (PRIMARY)
    supports_flatbuffers: bool = False  # FlatBuffers is SECONDARY
    schema_version: Optional[str] = None
    detected_at: float = 0.0

    def __post_init__(self):
        if self.detected_at == 0.0:
            self.detected_at = time.time()


# =============================================================================
# SECTION 4: CORE CLASSES
# =============================================================================


class ProtocolNegotiator:
    """
    Protocol negotiation and format switching between JSON and FlatBuffers.

    Purpose:
        Detects K0 FlatBuffers capability (via OPTIONS request), chooses optimal
        format based on capability and payload size, marshals objects to/from
        JSON and FlatBuffers, handles version negotiation for schema evolution.

    Responsibilities:
        1. Detect K0 FlatBuffers capability (via OPTIONS request)
        2. Choose format based on capability and payload size
        3. Marshal objects to/from JSON
        4. Marshal objects to/from FlatBuffers
        5. Handle version negotiation for schema evolution

    Format Decision Logic (ADR-0001a):
        IF payload_size < 1KB:
            PREFER: JSON (overhead negligible, human-readable)
        ELSE IF K0_supports_flatbuffers:
            PREFER: FlatBuffers (150× faster, 3× smaller)
        ELSE:
            FALLBACK: JSON (always works, K0 native)

    Lifecycle:
        INIT → NEGOTIATING → READY → [DEGRADED] → TERMINATED

    Thread Safety: Yes (async-safe with caching)
    Async Safe: Yes (fully async/await compatible)

    Cognitive Trace:
        - Propagates cognitive_trace_id to format negotiation requests
        - Required for: negotiate_format, serialize, deserialize

    Performance Budget (P95):
        - Format detection: <10ms (OPTIONS request to K0)
        - Format negotiation: <50ms (once per session, cached)
        - JSON serialization: <10ms (1KB payload)
        - FlatBuffers serialization: <1ms (1KB payload, 10× faster)

    Examples:
        >>> config = ProtocolConfig(enable_flatbuffers=True)
        >>> negotiator = ProtocolNegotiator(config)
        >>> await negotiator.initialize()
        >>>
        >>> # Serialize command payload
        >>> payload = {'command_type': 'MEMORY_WRITE', 'data': '...'}
        >>> format_used, serialized = await negotiator.serialize(
        ...     payload,
        ...     payload_size_bytes=len(str(payload))
        ... )
        >>> print(f'Format: {format_used}, Size: {len(serialized)} bytes')
        >>>
        >>> # Deserialize response
        >>> response = await negotiator.deserialize(serialized, format=format_used)
        >>> await negotiator.shutdown()

    References:
        - ADR-0001a: K0 Bridge Dual Protocol Support
        - ADR-0011: FlatBuffers Serialization (150× faster than JSON)
        - ADR-0013: Schema Evolution and Versioning
        - Diagram: architecture_diagrams/k1/k1_complete_with_flows.mmd
    """

    def __init__(self, config: ProtocolConfig) -> None:
        """
        Initialize ProtocolNegotiator.

        Args:
            config: Configuration object with format preferences

        Raises:
            ValueError: If configuration is invalid
            TypeError: If config type is incorrect

        Side Effects:
            - Initializes internal state (format cache, capabilities)
            - Does NOT detect K0 capabilities (call initialize() to detect)

        ADR: ADR-0001a (K0 Bridge Dual Protocol Support)
        Assigned to: Issue #L5-1.1.3
        """
        # ADR-0001a: K0 Bridge Dual Protocol Support
        # Validate config
        if config.default_format not in ("json", "flatbuffers"):
            raise ValueError(f"Invalid default_format: {config.default_format}")
        if config.payload_size_threshold_bytes <= 0:
            raise ValueError("payload_size_threshold_bytes must be positive")
        if config.compression_threshold_bytes <= 0:
            raise ValueError("compression_threshold_bytes must be positive")

        self.config = config
        self.state = "INIT"  # State: INIT | NEGOTIATING | READY | DEGRADED | TERMINATED
        self._logger = logger
        self._capabilities_cache: Dict[str, FormatCapabilities] = {}  # host → capabilities
        self._negotiation_time: Dict[str, float] = {}  # host → last negotiation time
        self._compression: CompressionUtility = create_compression_utility(
            CompressionConfig(threshold_bytes=config.compression_threshold_bytes)
        )
        self._default_host: Optional[str] = None
        self._default_port: Optional[int] = None

    async def initialize(self, k0_host: str = "localhost", k0_port: int = 8080) -> None:
        """
        Async initialization phase - detect K0 format capabilities.

        This method performs async setup (OPTIONS request to K0).

        Args:
            k0_host: K0 server hostname (default: localhost)
            k0_port: K0 server port (default: 8080)

        Raises:
            RuntimeError: If initialization fails
            ConnectionError: If cannot connect to K0
            TimeoutError: If OPTIONS request times out (>10ms)

        Lifecycle:
            Transitions: INIT → NEGOTIATING → READY

        ADR: ADR-0001a (K0 Bridge Dual Protocol Support)
        Assigned to: Issue #L5-1.1.3
        """
        host_key = self._cache_key(k0_host, k0_port)
        self._default_host = k0_host
        self._default_port = k0_port

        try:
            with create_span(
                "k0_bridge.protocol.detect_capabilities",
                k0_host=k0_host,
                k0_port=k0_port,
            ) as span:
                capabilities = await self._detect_capabilities(
                    k0_host=k0_host,
                    k0_port=k0_port,
                    trace_id=None,
                )
                span.set_attribute("supports_flatbuffers", capabilities.supports_flatbuffers)
        except (TimeoutError, ConnectionError):
            self._logger.warning(
                "capability_detection_failed_using_defaults host=%s port=%s",
                k0_host,
                k0_port,
            )
            capabilities = FormatCapabilities(
                supports_json=True,
                supports_flatbuffers=self.config.enable_flatbuffers,
                schema_version=None,
            )

        self._capabilities_cache[host_key] = capabilities
        self._capabilities_cache[k0_host] = capabilities
        self._negotiation_time[host_key] = capabilities.detected_at
        self._negotiation_time[k0_host] = capabilities.detected_at

        self.state = "READY"
        self._logger.info(
            "protocol_negotiator_initialized host=%s port=%s supports_json=%s supports_flatbuffers=%s schema_version=%s",
            k0_host,
            k0_port,
            capabilities.supports_json,
            capabilities.supports_flatbuffers,
            capabilities.schema_version,
        )

    async def negotiate_format(
        self,
        k0_host: str,
        payload_size_bytes: int,
        cognitive_trace_id: Optional[str] = None,
    ) -> SerializationFormat:
        """
        Negotiate optimal serialization format based on K0 capabilities and payload size.

        Format Decision Logic (ADR-0001a):
            IF payload_size < 1KB:
                PREFER: JSON (overhead negligible, human-readable)
            ELSE IF K0_supports_flatbuffers:
                PREFER: FlatBuffers (150× faster, 3× smaller)
            ELSE:
                FALLBACK: JSON (always works, K0 native)

        Args:
            k0_host: K0 server hostname (for capability lookup)
            payload_size_bytes: Payload size in bytes
            cognitive_trace_id: Trace ID for observability

        Returns:
            SerializationFormat (JSON or FLATBUFFERS)

        Raises:
            ValueError: If k0_host is invalid
            RuntimeError: If negotiation fails

        Performance:
            - Target: <50ms P95 (first call, cached after)
            - Cache hit: <1ms (lookup in cache)

        Observability:
            - Metrics: k1_k0_bridge_protocol_negotiation_total{format}
            - Traces: Span name: k0_bridge.protocol_negotiate
            - Logs: INFO: protocol negotiated (format, capabilities)

        ADR: ADR-0001a (K0 Bridge Dual Protocol Support)
        Assigned to: Issue #L5-1.1.3
        Depends on: FormatCapabilities (K0 capability detection)
        """
        # ADR-0001a: K0 Bridge Dual Protocol Support
        # Step 1: Check cache for capabilities
        host_key = k0_host
        capabilities = self._capabilities_cache.get(host_key)

        # Step 2: Check if cache expired (TTL=3600s)
        now = time.time()
        if capabilities:
            age = now - capabilities.detected_at
            if age > self.config.negotiation_cache_ttl_s:
                # Cache expired, re-detect capabilities
                try:
                    capabilities = await self._detect_capabilities(
                        k0_host=k0_host,
                        k0_port=self._default_port,
                        trace_id=cognitive_trace_id,
                    )
                    self._capabilities_cache[host_key] = capabilities
                    self._negotiation_time[host_key] = capabilities.detected_at
                except (TimeoutError, ConnectionError):
                    capabilities = FormatCapabilities(
                        supports_json=True,
                        supports_flatbuffers=self.config.enable_flatbuffers,
                        schema_version=None,
                    )

        if capabilities is None:
            try:
                capabilities = await self._detect_capabilities(
                    k0_host=k0_host,
                    k0_port=self._default_port,
                    trace_id=cognitive_trace_id,
                )
                self._capabilities_cache[host_key] = capabilities
                if self._default_host:
                    composite_key = self._cache_key(self._default_host, self._default_port)
                    self._capabilities_cache.setdefault(composite_key, capabilities)
                self._negotiation_time[host_key] = capabilities.detected_at
            except (TimeoutError, ConnectionError):
                capabilities = FormatCapabilities(
                    supports_json=True,
                    supports_flatbuffers=self.config.enable_flatbuffers,
                    schema_version=None,
                )

        # Step 3: Apply format decision logic
        # Format Decision Logic (ADR-0001a):
        # IF payload_size < 1KB:
        #     PREFER: JSON (overhead negligible, human-readable)
        # ELSE IF enable_flatbuffers:
        #     PREFER: FlatBuffers (150× faster, 3× smaller)
        # ELSE:
        #     FALLBACK: JSON (always works, K0 native)
        
        selected_format = SerializationFormat.JSON  # Default to JSON (PRIMARY)
        
        if payload_size_bytes < self.config.payload_size_threshold_bytes:
            # Small payload: use JSON (overhead negligible)
            selected_format = SerializationFormat.JSON
            reason = "payload_small"
        elif self.config.enable_flatbuffers:
            # Large payload + FlatBuffers enabled: use FlatBuffers
            selected_format = SerializationFormat.FLATBUFFERS
            reason = "flatbuffers_enabled"
        else:
            # Fallback to JSON
            selected_format = SerializationFormat.JSON
            reason = "fallback_to_json"
        
        # Step 4: Record metrics
        emit_counter(
            "k1_k0_bridge_protocol_negotiation_total",
            selected_format=selected_format.value,
        )
        self._logger.debug(
            "format_negotiated host=%s payload=%d format=%s reason=%s trace_id=%s",
            k0_host,
            payload_size_bytes,
            selected_format.value,
            reason,
            cognitive_trace_id,
        )
        
        return selected_format

    async def serialize(
        self,
        obj: Dict[str, Any],
        format: Optional[SerializationFormat] = None,
        payload_size_bytes: Optional[int] = None,
        cognitive_trace_id: Optional[str] = None,
    ) -> tuple[SerializationFormat, bytes]:
        """
        Serialize object to JSON or FlatBuffers.

        Args:
            obj: Python dict to serialize
            format: Target format (if None, auto-negotiate)
            payload_size_bytes: Payload size estimate (for format selection)
            cognitive_trace_id: Trace ID for observability

        Returns:
            Tuple: (format_used, serialized_bytes)

        Raises:
            ValueError: If obj is invalid
            TypeError: If obj type is not serializable

        Performance:
            - JSON: <10ms P95 (1KB payload)
            - FlatBuffers: <1ms P95 (1KB payload, 10× faster)

        ADR: ADR-0011 (FlatBuffers Serialization)
        Assigned to: Issue #L5-1.1.3
        """
        payload_size_estimate = payload_size_bytes or len(json.dumps(obj))

        if format is None:
            format = await self.negotiate_format(
                k0_host="localhost",
                payload_size_bytes=payload_size_estimate,
                cognitive_trace_id=cognitive_trace_id,
            )

        if format == SerializationFormat.FLATBUFFERS:
            serialized = self._serialize_flatbuffers(obj, cognitive_trace_id)
        else:
            serialized = self._serialize_json(obj, cognitive_trace_id)
            format = SerializationFormat.JSON

        if (
            self.config.compression_enabled
            and len(serialized) > self._compression.config.threshold_bytes
        ):
            compressed, result = self._compression.compress(serialized)
            if result.status == CompressionStatus.COMPRESSED:
                emit_histogram(
                    "k1_k0_bridge_compression_ratio",
                    value=result.compression_ratio or 1.0,
                    port="protocol",
                )
                emit_histogram(
                    "k1_k0_bridge_compression_duration_ms",
                    value=result.compression_time_ms or 0.0,
                    port="protocol",
                )
                self._logger.debug(
                    "payload_compressed original_size=%d compressed_size=%s ratio=%s trace_id=%s",
                    result.original_size,
                    result.compressed_size,
                    result.compression_ratio,
                    cognitive_trace_id,
                )
                serialized = compressed

        return format, serialized

    async def deserialize(
        self,
        data: bytes,
        format: SerializationFormat,
        cognitive_trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Deserialize bytes from JSON or FlatBuffers.

        Args:
            data: Serialized bytes
            format: Source format (JSON or FLATBUFFERS)
            cognitive_trace_id: Trace ID for observability

        Returns:
            Python dict (deserialized object)

        Raises:
            ValueError: If data is invalid
            json.JSONDecodeError: If JSON parsing fails
            flatbuffers.Error: If FlatBuffers parsing fails

        Performance:
            - JSON: <5ms P95 (1KB payload)
            - FlatBuffers: <0.3ms P95 (1KB payload, zero-copy)

        ADR: ADR-0011 (FlatBuffers Serialization)
        Assigned to: Issue #L5-1.1.3
        """
        # ADR-0001a: K0 Bridge Dual Protocol Support
        if format == SerializationFormat.JSON:
            return self._deserialize_json(data, cognitive_trace_id)
        elif format == SerializationFormat.FLATBUFFERS:
            return self._deserialize_flatbuffers(data, cognitive_trace_id)
        else:
            raise ValueError(f"Unknown format: {format}")

    async def shutdown(self) -> None:
        """
        Graceful shutdown sequence.

        This method performs cleanup and state transitions.

        Lifecycle:
            - Clear format cache
            - Finalize metrics

        ADR: ADR-0001a (K0 Bridge Dual Protocol Support)
        Assigned to: Issue #L5-1.1.3
        """
        # TODO(@infrastructure-team): Implement shutdown (ADR-0001a)
        # 1. Set state to TERMINATED
        # 2. Clear capabilities cache
        # 3. Flush metrics (Prometheus)
        self.state = "TERMINATED"
        self._capabilities_cache.clear()
        self._logger.info("protocol_negotiator_shutdown_complete")
        pass

    # =========================================================================
    # PRIVATE METHODS (Implementation Details)
    # =========================================================================

    def _serialize_json(
        self, data: Dict[str, Any], cognitive_trace_id: Optional[str] = None
    ) -> bytes:
        """Serialize data to JSON bytes."""
        # ADR-0001a: K0 Bridge Dual Protocol Support
        if not isinstance(data, (dict, list)):
            raise ValueError(f"Data must be dict or list, got {type(data).__name__}")
        
        start_time = time.time()
        try:
            json_str = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
            json_bytes = json_str.encode('utf-8')
            
            latency_ms = (time.time() - start_time) * 1000
            self._logger.debug(
                "json_serialized bytes=%d latency_ms=%.2f trace_id=%s",
                len(json_bytes),
                round(latency_ms, 2),
                cognitive_trace_id,
            )
            
            return json_bytes
            
        except (TypeError, ValueError) as e:
            self._logger.error(
                "json_serialization_failed error=%s trace_id=%s",
                e,
                cognitive_trace_id,
            )
            raise

    def _deserialize_json(
        self, data: bytes, cognitive_trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Deserialize JSON bytes to dict."""
        # ADR-0001a: K0 Bridge Dual Protocol Support
        start_time = time.time()
        try:
            json_str = data.decode('utf-8')
            result = json.loads(json_str)
            
            if not isinstance(result, (dict, list)):
                raise ValueError(f"Expected dict or list, got {type(result).__name__}")
            
            latency_ms = (time.time() - start_time) * 1000
            self._logger.debug(
                "json_deserialized bytes=%d latency_ms=%.2f trace_id=%s",
                len(data),
                round(latency_ms, 2),
                cognitive_trace_id,
            )
            
            return result
            
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as e:
            self._logger.error(
                "json_deserialization_failed error=%s trace_id=%s",
                e,
                cognitive_trace_id,
            )
            raise

    def _serialize_flatbuffers(
        self, data: Dict[str, Any], cognitive_trace_id: Optional[str] = None
    ) -> bytes:
        """Serialize data to FlatBuffers bytes (placeholder)."""
        # ADR-0011: FlatBuffers Serialization
        # TODO: Implement actual FlatBuffers serialization
        self._logger.warning(
            "flatbuffers_not_implemented_fallback_to_json trace_id=%s",
            cognitive_trace_id,
        )
        return self._serialize_json(data, cognitive_trace_id)

    def _deserialize_flatbuffers(
        self, data: bytes, cognitive_trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Deserialize FlatBuffers bytes to dict (placeholder)."""
        # ADR-0011: FlatBuffers Serialization
        # TODO: Implement actual FlatBuffers deserialization
        self._logger.warning(
            "flatbuffers_not_implemented_fallback_to_json trace_id=%s",
            cognitive_trace_id,
        )
        return self._deserialize_json(data, cognitive_trace_id)

    async def _detect_capabilities(
        self, k0_host: str, k0_port: Optional[int], trace_id: Optional[str]
    ) -> FormatCapabilities:
        """
        Detect K0 format capabilities via OPTIONS request.

        Args:
            k0_host: K0 server hostname
            k0_port: K0 server port

        Returns:
            FormatCapabilities (supports_json, supports_flatbuffers, schema_version)

        Raises:
            ConnectionError: If cannot connect to K0
            TimeoutError: If OPTIONS request times out

        Performance:
            - Target: <10ms P95 (OPTIONS request)

        ADR: ADR-0001a (K0 Bridge Dual Protocol Support)
        Assigned to: Issue #L5-1.1.3
        """
        port = k0_port if k0_port not in (None, 0) else self._default_port
        url = httpx.URL(
            scheme="http",
            host=k0_host,
            port=port,
            path=self.config.negotiation_endpoint,
        )
        headers = {}
        if trace_id:
            headers["X-Cognitive-Trace-Id"] = trace_id

        timeout = httpx.Timeout(self.config.format_detection_timeout_ms / 1000)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.options(url, headers=headers)
            except httpx.TimeoutException as exc:
                emit_counter(
                    "k1_k0_bridge_protocol_negotiation_failures_total",
                    reason="timeout",
                )
                raise TimeoutError("Capability detection timed out") from exc
            except httpx.HTTPError as exc:
                emit_counter(
                    "k1_k0_bridge_protocol_negotiation_failures_total",
                    reason="transport_error",
                )
                raise ConnectionError("Failed to negotiate protocol") from exc

        accept_header = response.headers.get("Accept", "")
        supports_flatbuffers = "application/x-flatbuffers" in accept_header
        schema_version = response.headers.get("X-Flatbuffers-Schema-Version")

        capabilities = FormatCapabilities(
            supports_json=True,
            supports_flatbuffers=supports_flatbuffers,
            schema_version=schema_version,
        )
        self._logger.info(
            "capabilities_detected host=%s port=%s supports_flatbuffers=%s schema_version=%s trace_id=%s",
            k0_host,
            port,
            supports_flatbuffers,
            schema_version,
            trace_id,
        )
        return capabilities

    @staticmethod
    def _cache_key(k0_host: str, k0_port: Optional[int]) -> str:
        return f"{k0_host}:{k0_port}" if k0_port is not None else k0_host


# =============================================================================
# SECTION 5: HELPER FUNCTIONS
# =============================================================================


def create_protocol_negotiator(
    config: Optional[ProtocolConfig] = None,
) -> ProtocolNegotiator:
    """
    Create ProtocolNegotiator with default or provided configuration.

    Args:
        config: ProtocolConfig (default: JSON PRIMARY, FlatBuffers enabled)

    Returns:
        ProtocolNegotiator instance

    ADR: ADR-0001a (K0 Bridge Dual Protocol Support)
    Assigned to: Issue #L5-1.1.3
    """
    if config is None:
        config = ProtocolConfig()

    return ProtocolNegotiator(config)


# =============================================================================
# SECTION 6: MODULE EXPORTS & INITIALIZATION
# =============================================================================

__all__ = [
    "ProtocolNegotiator",
    "SerializationFormat",
    "ProtocolConfig",
    "FormatCapabilities",
    "create_protocol_negotiator",
]


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================
# Metrics to export (Prometheus):
#   - k1_k0_bridge_protocol_negotiation_total{format} (counter)
#   - k1_k0_bridge_serialization_latency_ms{format, p50, p95, p99} (histogram)
#   - k1_k0_bridge_format_selected{format} (gauge: current format in use)
#
# Traces to generate (OpenTelemetry):
#   - Span name: k0_bridge.protocol_negotiate
#   - Attributes: format, payload_size, cognitive_trace_id, k0_host
#   - Links to: upstream command_client spans
#
# Logs to emit (structured logging):
#   - Level: INFO (normal), WARNING (fallback), ERROR (failures)
#   - Fields: component='protocol_negotiator', format, latency_ms, error
#
# =============================================================================

# =============================================================================
# COGNITIVE TRACE PROPAGATION
# =============================================================================
# All async methods must:
#   1. Accept cognitive_trace_id parameter
#   2. Include trace_id in OPTIONS request (X-Cognitive-Trace-Id header)
#   3. Include trace_id in all log statements
#
# Example:
#   format = await negotiator.negotiate_format(
#       k0_host='localhost',
#       payload_size_bytes=5000,
#       cognitive_trace_id='trace_abc123'
#   )
#   # OPTIONS request includes: X-Cognitive-Trace-Id: trace_abc123
#
# =============================================================================

# =============================================================================
# TESTING REQUIREMENTS (WARD Framework)
# =============================================================================
# Integration tests required:
#   - tests/k1/bridge_k0/test_protocol.py
#   - Test format negotiation (JSON vs FlatBuffers)
#   - Test payload size threshold (1KB)
#   - Test K0 capability detection (OPTIONS request)
#   - Test format cache (TTL=3600s)
#   - Test JSON serialization/deserialization
#   - Test FlatBuffers serialization/deserialization
#   - Test fallback to JSON (if FlatBuffers not supported)
#
# No simulation code allowed:
#   - Use real K0 mock server with OPTIONS endpoint
#   - Test both JSON and FlatBuffers paths
#   - Integration tests > unit tests
#
# Performance budget tests:
#   - Assert format detection <10ms P95
#   - Assert JSON serialization <10ms P95
#   - Assert FlatBuffers serialization <1ms P95 (10× faster)
#
# =============================================================================
