"""
Protocol Negotiator - Format Switching between JSON and FlatBuffers

Layer: L5 Infrastructure
Component: K0 Bridge (K1 ↔ K0 Communication)
Priority: P0 (Critical Path)
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

Architecture Decision Records:
    - ADR-0001: K0/K1 Kernel Split (K1 Intelligence Module, K0 Memory Module)
    - ADR-0001a: K0 Bridge Dual Protocol Support (JSON PRIMARY + FlatBuffers SECONDARY)
    - ADR-0011: FlatBuffers Serialization (zero-copy, 150× faster than JSON)
    - ADR-0013: Schema Evolution and Versioning (forward/backward compatibility)

Dependencies:
    Internal:
        - k1.l5_infrastructure.serialization.Serializer (JSON serialization)
        - k1.l5_infrastructure.serialization.Deserializer (JSON deserialization)
    External:
        - json (JSON encoding/decoding)
        - flatbuffers (FlatBuffers library)

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

# =============================================================================
# SECTION 1: IMPORTS
# =============================================================================
# Standard library imports
from typing import Any, Dict, Optional

# flatbuffers - FlatBuffers library (zero-copy serialization)
# import flatbuffers

# Internal imports
# from k1.l5_infrastructure.serialization import Serializer, Deserializer

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
        # TODO(@infrastructure-team): Implement initialization (ADR-0001a)
        # 1. Validate config (check default_format in json/flatbuffers)
        # 2. Initialize state machine (INIT → NEGOTIATING → READY)
        # 3. Initialize format cache (negotiation results per host)
        # 4. Initialize capabilities tracker (K0 format support)
        self.config = config
        self.state = "INIT"  # State: INIT | NEGOTIATING | READY | DEGRADED | TERMINATED
        self._logger = logger
        self._capabilities_cache: Dict[str, FormatCapabilities] = (
            {}
        )  # host → capabilities
        self._negotiation_time: Dict[str, float] = {}  # host → last negotiation time
        pass

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
        # TODO(@infrastructure-team): Implement async initialization (ADR-0001a)
        # 1. Send OPTIONS request to K0 (detect FlatBuffers capability)
        # 2. Parse response headers (Accept: application/json, application/x-flatbuffers)
        # 3. Check schema version (X-FlatBuffers-Schema-Version: 1.2.0)
        # 4. Cache capabilities (host → FormatCapabilities)
        # 5. Transition state: INIT → NEGOTIATING → READY
        self.state = "READY"
        self._logger.info(
            "protocol_negotiator_initialized",
            k0_host=k0_host,
            k0_port=k0_port,
            supports_flatbuffers=self.config.enable_flatbuffers,
        )
        pass

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
        # TODO(@infrastructure-team): Implement format negotiation (ADR-0001a)
        # 1. Check cache for capabilities (host → FormatCapabilities)
        # 2. If cache miss or expired (TTL=3600s), re-detect capabilities
        # 3. Apply format decision logic:
        #    - payload_size < 1KB → JSON
        #    - K0 supports FlatBuffers → FlatBuffers
        #    - Otherwise → JSON (fallback)
        # 4. Record metrics (format selected, negotiation latency)
        # 5. Return SerializationFormat
        # Performance target: <50ms P95 (first call), <1ms (cache hit)
        self._logger.info(
            "negotiate_format",
            k0_host=k0_host,
            payload_size_bytes=payload_size_bytes,
            trace_id=cognitive_trace_id,
        )

        # Placeholder return (MUST be replaced with actual implementation)
        if payload_size_bytes < self.config.payload_size_threshold_bytes:
            return SerializationFormat.JSON
        elif self.config.enable_flatbuffers:
            return SerializationFormat.FLATBUFFERS
        else:
            return SerializationFormat.JSON

    async def serialize(
        self,
        obj: Dict[str, Any],
        format: Optional[SerializationFormat] = None,
        payload_size_bytes: Optional[int] = None,
    ) -> tuple[SerializationFormat, bytes]:
        """
        Serialize object to JSON or FlatBuffers.

        Args:
            obj: Python dict to serialize
            format: Target format (if None, auto-negotiate)
            payload_size_bytes: Payload size estimate (for format selection)

        Returns:
            Tuple: (format_used, serialized_bytes)

        Raises:
            ValueError: If obj is invalid
            TypeError: If obj type is not serializable

        Performance:
            - JSON: <10ms P95 (1KB payload)
            - FlatBuffers: <1ms P95 (1KB payload, 10× faster)

        Observability:
            - Metrics: k1_k0_bridge_serialization_latency_ms{format}

        ADR: ADR-0011 (FlatBuffers Serialization)
        Assigned to: Issue #L5-1.1.3
        """
        # TODO(@infrastructure-team): Implement serialization (ADR-0011)
        # 1. If format is None, auto-negotiate (negotiate_format)
        # 2. If format == JSON:
        #    - Serialize to JSON: json.dumps(obj).encode('utf-8')
        # 3. If format == FLATBUFFERS:
        #    - Create FlatBuffers builder
        #    - Serialize object to FlatBuffers schema
        #    - Return binary buffer
        # 4. Record metrics (serialization latency, format)
        # 5. Return (format_used, serialized_bytes)
        # Performance target: JSON <10ms, FlatBuffers <1ms

        if format is None:
            format = SerializationFormat.JSON  # Default fallback

        if format == SerializationFormat.JSON:
            serialized = json.dumps(obj).encode("utf-8")
        else:
            # TODO: Implement FlatBuffers serialization
            serialized = b"flatbuffers_placeholder"

        return (format, serialized)

    async def deserialize(
        self,
        data: bytes,
        format: SerializationFormat,
    ) -> Dict[str, Any]:
        """
        Deserialize bytes from JSON or FlatBuffers.

        Args:
            data: Serialized bytes
            format: Source format (JSON or FLATBUFFERS)

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
        # TODO(@infrastructure-team): Implement deserialization (ADR-0011)
        # 1. If format == JSON:
        #    - Decode bytes: json.loads(data.decode('utf-8'))
        # 2. If format == FLATBUFFERS:
        #    - Parse FlatBuffers binary buffer (zero-copy)
        #    - Convert to Python dict (FlatBuffers → dict)
        # 3. Return Python dict
        # Performance target: JSON <5ms, FlatBuffers <0.3ms (zero-copy)

        if format == SerializationFormat.JSON:
            return json.loads(data.decode("utf-8"))
        else:
            # TODO: Implement FlatBuffers deserialization
            return {"placeholder": "flatbuffers_data"}

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

    async def _detect_capabilities(
        self, k0_host: str, k0_port: int
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
        # TODO(@infrastructure-team): Implement capability detection (ADR-0001a)
        # 1. Send OPTIONS request to K0 (http://k0_host:k0_port/)
        # 2. Parse Accept header: application/json, application/x-flatbuffers
        # 3. Parse X-FlatBuffers-Schema-Version header
        # 4. Return FormatCapabilities
        pass


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
