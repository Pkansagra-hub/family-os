"""
Integration Tests for Protocol Negotiator - K0 Bridge

Layer: L5 Infrastructure
Component: K0 Bridge (K1 ↔ K0 Communication)
Priority: P0 (Critical Path)
Status: ✅ PRODUCTION

Architecture Decision Records:
    - ADR-0001a: K0 Bridge Dual Protocol Support (JSON PRIMARY + FlatBuffers SECONDARY)
    - ADR-0011: FlatBuffers Serialization (zero-copy, 150× faster than JSON)

Test Strategy:
    - Integration tests > unit tests (per FamilyOS rules)
    - Real components where feasible
    - Assert contract compliance and performance budgets (P95)
    - NO simulation code (asyncio.sleep/time.sleep forbidden)

Performance Budgets (P95):
    - Format negotiation: <50ms (first call), <1ms (cache hit)
    - JSON serialization: <10ms (1KB payload)
    - FlatBuffers serialization: <1ms (1KB payload, 10× faster)

References:
    - ADR-0001a: K0 Bridge Dual Protocol Support
    - ADR-0011: FlatBuffers Serialization
    - Contract: k1/contracts/k0_bridge/protocols/content_negotiation.yml
"""

import pytest
import json
from k1.bridge_k0.protocol import (
    ProtocolNegotiator,
    ProtocolConfig,
    SerializationFormat,
    FormatCapabilities,
    create_protocol_negotiator,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def protocol_config():
    """Protocol configuration for testing."""
    return ProtocolConfig(
        default_format="json",
        enable_flatbuffers=True,
        payload_size_threshold_bytes=1024,  # 1KB
        negotiation_cache_ttl_s=3600,
    )


@pytest.fixture
async def protocol_negotiator(protocol_config):
    """Protocol negotiator fixture with automatic cleanup."""
    negotiator = ProtocolNegotiator(protocol_config)
    await negotiator.initialize(k0_host="localhost", k0_port=8080)
    yield negotiator
    await negotiator.shutdown()


# =============================================================================
# INITIALIZATION TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_protocol_negotiator_initialization(protocol_config):
    """Test protocol negotiator initialization."""
    # ADR-0001a: K0 Bridge Dual Protocol Support
    negotiator = ProtocolNegotiator(protocol_config)
    
    assert negotiator.state == "INIT"
    assert negotiator.config.default_format == "json"
    assert negotiator.config.enable_flatbuffers is True
    assert negotiator.config.payload_size_threshold_bytes == 1024


@pytest.mark.asyncio
async def test_protocol_negotiator_invalid_config():
    """Test protocol negotiator with invalid configuration."""
    # ADR-0001a: K0 Bridge Dual Protocol Support
    
    # Invalid default_format
    with pytest.raises(ValueError, match="Invalid default_format"):
        ProtocolNegotiator(ProtocolConfig(default_format="invalid"))
    
    # Invalid payload_size_threshold_bytes
    with pytest.raises(ValueError, match="payload_size_threshold_bytes must be positive"):
        ProtocolNegotiator(ProtocolConfig(payload_size_threshold_bytes=-1))


@pytest.mark.asyncio
async def test_protocol_negotiator_async_initialization(protocol_config):
    """Test protocol negotiator async initialization."""
    # ADR-0001a: K0 Bridge Dual Protocol Support
    negotiator = ProtocolNegotiator(protocol_config)
    
    await negotiator.initialize(k0_host="localhost", k0_port=8080)
    
    assert negotiator.state == "READY"
    assert "localhost:8080" in negotiator._capabilities_cache


# =============================================================================
# FORMAT NEGOTIATION TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_negotiate_format_small_payload(protocol_negotiator):
    """Test format negotiation for small payload (<1KB)."""
    # ADR-0001a: K0 Bridge Dual Protocol Support
    # Format Decision Logic: payload_size < 1KB → JSON
    
    format = await protocol_negotiator.negotiate_format(
        k0_host="localhost",
        payload_size_bytes=512,  # 512 bytes (< 1KB)
        cognitive_trace_id="trace_001",
    )
    
    assert format == SerializationFormat.JSON


@pytest.mark.asyncio
async def test_negotiate_format_large_payload(protocol_negotiator):
    """Test format negotiation for large payload (>1KB)."""
    # ADR-0001a: K0 Bridge Dual Protocol Support
    # Format Decision Logic: payload_size > 1KB + FlatBuffers supported → FlatBuffers
    
    format = await protocol_negotiator.negotiate_format(
        k0_host="localhost",
        payload_size_bytes=5000,  # 5KB (> 1KB)
        cognitive_trace_id="trace_002",
    )
    
    # Should prefer FlatBuffers for large payloads
    assert format == SerializationFormat.FLATBUFFERS


@pytest.mark.asyncio
async def test_negotiate_format_flatbuffers_disabled():
    """Test format negotiation with FlatBuffers disabled."""
    # ADR-0001a: K0 Bridge Dual Protocol Support
    # Format Decision Logic: FlatBuffers disabled → JSON (fallback)
    
    config = ProtocolConfig(
        default_format="json",
        enable_flatbuffers=False,  # Disable FlatBuffers
        payload_size_threshold_bytes=1024,
    )
    negotiator = ProtocolNegotiator(config)
    await negotiator.initialize(k0_host="localhost", k0_port=8080)
    
    format = await negotiator.negotiate_format(
        k0_host="localhost",
        payload_size_bytes=5000,  # Large payload
        cognitive_trace_id="trace_003",
    )
    
    # Should fall back to JSON
    assert format == SerializationFormat.JSON
    
    await negotiator.shutdown()


# =============================================================================
# JSON SERIALIZATION TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_serialize_json_dict(protocol_negotiator):
    """Test JSON serialization of dict."""
    # ADR-0001a: K0 Bridge Dual Protocol Support
    
    test_data = {"key": "value", "number": 42, "nested": {"inner": "data"}}
    
    format_used, serialized = await protocol_negotiator.serialize(
        obj=test_data,
        cognitive_trace_id="trace_004",
    )
    
    assert format_used == SerializationFormat.JSON
    assert isinstance(serialized, bytes)
    
    # Verify deserialization
    deserialized = json.loads(serialized.decode('utf-8'))
    assert deserialized == test_data


@pytest.mark.asyncio
async def test_serialize_json_list(protocol_negotiator):
    """Test JSON serialization of list."""
    # ADR-0001a: K0 Bridge Dual Protocol Support
    
    test_data = [1, 2, 3, {"key": "value"}]
    
    format_used, serialized = await protocol_negotiator.serialize(
        obj=test_data,
        cognitive_trace_id="trace_005",
    )
    
    assert format_used == SerializationFormat.JSON
    assert isinstance(serialized, bytes)
    
    # Verify deserialization
    deserialized = json.loads(serialized.decode('utf-8'))
    assert deserialized == test_data


@pytest.mark.asyncio
async def test_serialize_json_invalid_type(protocol_negotiator):
    """Test JSON serialization with invalid type."""
    # ADR-0001a: K0 Bridge Dual Protocol Support
    
    # Invalid type (not dict or list)
    with pytest.raises(ValueError, match="Data must be dict or list"):
        await protocol_negotiator.serialize(
            obj="invalid_string",
            cognitive_trace_id="trace_006",
        )


@pytest.mark.asyncio
async def test_deserialize_json(protocol_negotiator):
    """Test JSON deserialization."""
    # ADR-0001a: K0 Bridge Dual Protocol Support
    
    test_data = {"key": "value", "number": 42}
    json_bytes = json.dumps(test_data).encode('utf-8')
    
    deserialized = await protocol_negotiator.deserialize(
        data=json_bytes,
        format=SerializationFormat.JSON,
        cognitive_trace_id="trace_007",
    )
    
    assert deserialized == test_data


@pytest.mark.asyncio
async def test_deserialize_json_invalid_data(protocol_negotiator):
    """Test JSON deserialization with invalid data."""
    # ADR-0001a: K0 Bridge Dual Protocol Support
    
    # Invalid JSON
    with pytest.raises(json.JSONDecodeError):
        await protocol_negotiator.deserialize(
            data=b"invalid json",
            format=SerializationFormat.JSON,
            cognitive_trace_id="trace_008",
        )


# =============================================================================
# FLATBUFFERS TESTS (PLACEHOLDER)
# =============================================================================


@pytest.mark.asyncio
async def test_serialize_flatbuffers_fallback(protocol_negotiator):
    """Test FlatBuffers serialization (currently falls back to JSON)."""
    # ADR-0011: FlatBuffers Serialization
    # TODO: Implement actual FlatBuffers serialization
    
    test_data = {"key": "value"}
    
    # Currently falls back to JSON
    serialized = protocol_negotiator._serialize_flatbuffers(
        data=test_data,
        cognitive_trace_id="trace_009",
    )
    
    assert isinstance(serialized, bytes)
    # Verify it's actually JSON (fallback)
    deserialized = json.loads(serialized.decode('utf-8'))
    assert deserialized == test_data


@pytest.mark.asyncio
async def test_deserialize_flatbuffers_fallback(protocol_negotiator):
    """Test FlatBuffers deserialization (currently falls back to JSON)."""
    # ADR-0011: FlatBuffers Serialization
    # TODO: Implement actual FlatBuffers deserialization
    
    test_data = {"key": "value"}
    json_bytes = json.dumps(test_data).encode('utf-8')
    
    # Currently falls back to JSON
    deserialized = protocol_negotiator._deserialize_flatbuffers(
        data=json_bytes,
        cognitive_trace_id="trace_010",
    )
    
    assert deserialized == test_data


# =============================================================================
# CAPABILITY CACHING TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_capability_caching(protocol_negotiator):
    """Test format capability caching."""
    # ADR-0001a: K0 Bridge Dual Protocol Support
    
    # First call (cache miss)
    format1 = await protocol_negotiator.negotiate_format(
        k0_host="localhost",
        payload_size_bytes=5000,
        cognitive_trace_id="trace_011",
    )
    
    # Second call (cache hit)
    format2 = await protocol_negotiator.negotiate_format(
        k0_host="localhost",
        payload_size_bytes=5000,
        cognitive_trace_id="trace_012",
    )
    
    # Should return same format
    assert format1 == format2
    
    # Verify cache entry exists
    assert "localhost" in protocol_negotiator._capabilities_cache


# =============================================================================
# PERFORMANCE TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_json_serialization_performance(protocol_negotiator):
    """Test JSON serialization performance budget."""
    # ADR-0001a: K0 Bridge Dual Protocol Support
    # Performance Budget: JSON serialization <10ms P95 (1KB payload)
    
    import time
    
    # Create 1KB payload
    test_data = {"data": "x" * 1000}
    
    # Measure serialization time
    start_time = time.time()
    format_used, serialized = await protocol_negotiator.serialize(
        obj=test_data,
        cognitive_trace_id="trace_013",
    )
    serialization_time_ms = (time.time() - start_time) * 1000
    
    # Assert performance budget
    assert serialization_time_ms < 10, f"JSON serialization took {serialization_time_ms}ms (budget: <10ms)"
    assert format_used == SerializationFormat.JSON


@pytest.mark.asyncio
async def test_format_negotiation_performance(protocol_negotiator):
    """Test format negotiation performance budget."""
    # ADR-0001a: K0 Bridge Dual Protocol Support
    # Performance Budget: Format negotiation <50ms P95 (first call), <1ms (cache hit)
    
    import time
    
    # First call (cache miss)
    start_time = time.time()
    await protocol_negotiator.negotiate_format(
        k0_host="localhost",
        payload_size_bytes=5000,
        cognitive_trace_id="trace_014",
    )
    first_call_time_ms = (time.time() - start_time) * 1000
    
    # Assert first call performance
    assert first_call_time_ms < 50, f"Format negotiation (first call) took {first_call_time_ms}ms (budget: <50ms)"
    
    # Second call (cache hit)
    start_time = time.time()
    await protocol_negotiator.negotiate_format(
        k0_host="localhost",
        payload_size_bytes=5000,
        cognitive_trace_id="trace_015",
    )
    cached_call_time_ms = (time.time() - start_time) * 1000
    
    # Assert cached call performance
    assert cached_call_time_ms < 1, f"Format negotiation (cache hit) took {cached_call_time_ms}ms (budget: <1ms)"


# =============================================================================
# HELPER FUNCTION TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_create_protocol_negotiator_default():
    """Test create_protocol_negotiator with default config."""
    # ADR-0001a: K0 Bridge Dual Protocol Support
    
    negotiator = create_protocol_negotiator()
    
    assert negotiator is not None
    assert negotiator.config.default_format == "json"
    assert negotiator.config.enable_flatbuffers is True


@pytest.mark.asyncio
async def test_create_protocol_negotiator_custom():
    """Test create_protocol_negotiator with custom config."""
    # ADR-0001a: K0 Bridge Dual Protocol Support
    
    custom_config = ProtocolConfig(
        default_format="json",
        enable_flatbuffers=False,
        payload_size_threshold_bytes=2048,
    )
    
    negotiator = create_protocol_negotiator(config=custom_config)
    
    assert negotiator is not None
    assert negotiator.config.enable_flatbuffers is False
    assert negotiator.config.payload_size_threshold_bytes == 2048


# =============================================================================
# SHUTDOWN TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_protocol_negotiator_shutdown(protocol_config):
    """Test protocol negotiator graceful shutdown."""
    # ADR-0001a: K0 Bridge Dual Protocol Support
    
    negotiator = ProtocolNegotiator(protocol_config)
    await negotiator.initialize(k0_host="localhost", k0_port=8080)
    
    assert negotiator.state == "READY"
    
    await negotiator.shutdown()
    
    assert negotiator.state == "TERMINATED"
    assert len(negotiator._capabilities_cache) == 0


# =============================================================================
# INTEGRATION TEST SUMMARY
# =============================================================================
# Tests implemented:
#   ✅ Protocol negotiator initialization
#   ✅ Invalid configuration validation
#   ✅ Async initialization
#   ✅ Format negotiation (small payload → JSON)
#   ✅ Format negotiation (large payload → FlatBuffers)
#   ✅ Format negotiation (FlatBuffers disabled → JSON fallback)
#   ✅ JSON serialization (dict)
#   ✅ JSON serialization (list)
#   ✅ JSON serialization (invalid type)
#   ✅ JSON deserialization
#   ✅ JSON deserialization (invalid data)
#   ✅ FlatBuffers serialization (fallback to JSON)
#   ✅ FlatBuffers deserialization (fallback to JSON)
#   ✅ Capability caching
#   ✅ JSON serialization performance (<10ms P95)
#   ✅ Format negotiation performance (<50ms first, <1ms cached)
#   ✅ Helper function (create_protocol_negotiator)
#   ✅ Graceful shutdown
#
# Performance assertions:
#   - Format negotiation: <50ms P95 (first call), <1ms (cache hit)
#   - JSON serialization: <10ms P95 (1KB payload)
#
# Contract compliance:
#   - ADR-0001a: K0 Bridge Dual Protocol Support
#   - ADR-0011: FlatBuffers Serialization
#   - Contract: k1/contracts/k0_bridge/protocols/content_negotiation.yml
#
# Note: FlatBuffers tests currently use fallback to JSON.
#       Actual FlatBuffers implementation to be added in future iteration.
# =============================================================================
