"""
FlatBuffers Deserializer - FlatBuffers Binary â†’ Python Objects (Zero-Copy)

Layer: L5 Infrastructure
Component: Serialization (Core)
Priority: P0 (Critical Path)
Status: ðŸš§ STUB - NEEDS_IMPLEMENTATION

Architecture Decision Records:
    - ADR-0011: FlatBuffers for All K1 Serialization
      * Zero-copy deserialization (0ms, direct buffer access)
      * 150-200Ã— faster than JSON deserialization (0.05ms vs 7.5ms)
      * No memory allocation overhead (field access via pointer arithmetic)
      * Section: "Performance Comparison" (FlatBuffers vs JSON/Protobuf)

    - ADR-0011c: Serialization Performance & Zero-Copy
      * Vtable-based field access (2-3 CPU cycles per field)
      * Memory layout optimization (alignment, padding, vtable compression)
      * Buffer lifetime management (keep buffer alive for object lifetime)
      * Section: "Zero-Copy Deserialization", "Memory Layout", "Vtable Compression"
      * Performance: <0.1ms P95 deserialization, 0ms memory copy

    - ADR-0011d: Schema Evolution & Versioning
      * Forward compatibility (ignore unknown fields)
      * Backward compatibility (default values for missing fields)
      * File identifier validation (4-character codes)
      * Section: "Forward Compatibility Rules", "Handling Unknown Enum Values"

Dependencies:
    Internal:
        - k1.l5_infrastructure.serialization.serializer.SchemaRegistry (schema metadata)

    External:
        - flatbuffers (FlatBuffers Python library)
        - typing (type hints)

Connects To:
    Used By:
        - k1.bridge_k0.command_client (K0 command deserialization)
        - k1.bridge_k0.sse_port (K0 event deserialization)
        - k1.l5_infrastructure.event_bus.event_bus (event deserialization)
        - k1.l2_orchestration.orchestrator (agent message deserialization)
        - k1.l4_runtime.session_state.manager (SessionState loading)

Performance Budgets:
    - Deserialization latency: <0.1ms P95 (zero-copy, no parsing)
    - Field access latency: <0.05ms P95 (pointer arithmetic + dereference)
    - Memory overhead: <1KB per buffer (vtable + metadata only)
    - Buffer lifetime: Keep buffer alive for object lifetime (no GC until object destroyed)

Observability:
    - Metrics:
        * k1_flatbuffers_deserialize_duration_ms{schema_type, p50, p95, p99} (histogram: deserialization latency)
        * k1_flatbuffers_deserialize_calls_total{schema_type, status} (counter: success/error)
        * k1_flatbuffers_field_access_duration_ms{schema_type, field_name} (histogram: field access latency)
        * k1_flatbuffers_buffer_kept_alive_count{gauge} (gauge: buffers kept alive for zero-copy)

    - Logs:
        * DEBUG: deserialize_started (schema_type, buffer_size, file_identifier)
        * DEBUG: deserialize_completed (schema_type, duration_ms, field_count, zero_copy)
        * WARNING: file_identifier_mismatch (expected, actual, buffer_size)
        * ERROR: deserialize_failed (schema_type, error, buffer_hex)

References:
    - ADR-0011: FlatBuffers Serialization Core
    - ADR-0011c: Serialization Performance & Zero-Copy
    - ADR-0011d: Schema Evolution & Versioning
    - Contracts: k1/contracts/flatbuffers/ (130 .fbs schema files)
    - Test: tests/k1/l5_infrastructure/serialization/test_deserializer.py
"""

import logging
import time

# =============================================================================
# SECTION 1: IMPORTS
# =============================================================================
# Standard library imports
from typing import Any, Dict

# Internal imports
from k1.l5_infrastructure.serialization.serializer import SchemaRegistry

# Third-party imports


# Configure module logger
logger = logging.getLogger(__name__)


# =============================================================================
# SECTION 2: CONSTANTS & CONFIGURATION
# =============================================================================

# Performance thresholds for warnings
SLOW_DESERIALIZATION_THRESHOLD_MS = {
    "session_state": 0.1,  # SessionState (64KB) budget
    "k0_event": 0.05,  # K0 Event (4KB) budget
    "agent_message": 0.05,  # Agent Message (2KB) budget
    "default": 0.1,  # Default threshold
}


# =============================================================================
# SECTION 3: BUFFER WRAPPER (KEEPS BUFFER ALIVE)
# =============================================================================


class BufferWrapper:
    """
    Wrapper to keep FlatBuffers buffer alive for zero-copy access

    Purpose:
        FlatBuffers zero-copy requires buffer to remain in memory
        while object is accessed. This wrapper ensures buffer lifetime
        matches object lifetime.

    Usage:
        wrapper = BufferWrapper(buffer_bytes)
        state = AgentState.AgentState.GetRootAs(wrapper.buffer, 0)
        # wrapper keeps buffer alive until state is garbage collected

    Lifecycle:
        1. Deserializer creates BufferWrapper
        2. BufferWrapper stores reference to buffer bytes
        3. FlatBuffers table object holds reference to wrapper
        4. When table object is destroyed, wrapper is destroyed
        5. Buffer bytes are garbage collected

    ADR-0011c: Buffer lifetime management for zero-copy (Section "Zero-Copy Architecture")
    """

    def __init__(self, buffer: bytes):
        """
        Initialize buffer wrapper

        Args:
            buffer: FlatBuffers binary buffer

        TODO(@infrastructure-team): Initialize wrapper
        Assigned to: Issue #L5-3.1.2
        """
        self.buffer = buffer
        self.size = len(buffer)
        self.kept_alive_at = time.time()

    def __len__(self) -> int:
        """Return buffer size"""
        return self.size

    def __repr__(self) -> str:
        """String representation"""
        return f"BufferWrapper(size={self.size}, kept_alive_at={self.kept_alive_at})"


# =============================================================================
# SECTION 4: CORE DESERIALIZER CLASS
# =============================================================================


class Deserializer:
    """
    FlatBuffers Deserializer: FlatBuffers binary â†’ Python objects (zero-copy)

    Responsibilities:
        1. Deserialize FlatBuffers binary to Python objects
        2. Support zero-copy field access (lazy evaluation)
        3. Keep buffer alive for lifetime of object
        4. Validate schema compatibility (file identifiers)
        5. Handle schema evolution (forward/backward compatibility)
        6. Track performance metrics

    Zero-Copy Design:
        - Field access does NOT copy data from buffer
        - Object.__dict__ contains references to buffer (via wrapper)
        - Buffer lifecycle: Keep buffer alive while object is used
        - Performance: <0.1ms deserialization, <0.05ms field access

    Key Property:
        Traditional JSON: JSON String (64KB) â†’ Parse (7.5ms) â†’ Allocate (3KB) â†’ Copy Fields â†’ Value
        FlatBuffers Zero-Copy: Binary Buffer (64KB) [KEEP IN MEMORY] â†’ Cast Pointer (0.05ms) â†’ Vtable Lookup â†’ Value [Read from buffer at offset, no copy]

    Supported Schema Types (76+ schemas):
        - Same as Serializer (all K1 schemas)

    Performance Targets (from ADR-0011c):
        - SessionState (64KB): <0.1ms P95 deserialization
        - K0 Event (4KB): <0.05ms P95 deserialization
        - Agent Message (2KB): <0.05ms P95 deserialization
        - Field access: <0.05ms P95 (pointer arithmetic)

    ADR-0011: FlatBuffers core deserialization design
    ADR-0011c: Zero-copy performance optimization
    ADR-0011d: Schema evolution (file identifier validation)
    """

    def __init__(self, schema_registry: SchemaRegistry):
        """
        Initialize deserializer with schema registry

        Args:
            schema_registry: Registry of all FlatBuffers schemas

        TODO(@infrastructure-team): Initialize deserializer
        Assigned to: Issue #L5-3.1.2
        """
        self.schema_registry = schema_registry

        # Stats
        self._total_deserializations = 0
        self._total_bytes_read = 0
        self._buffers_kept_alive = 0

        logger.info(
            "deserializer_initialized",
            total_schemas=len(schema_registry.list_schemas()),
        )

    def deserialize(
        self,
        buffer: bytes,
        schema_name: str,
        keep_buffer_alive: bool = True,
    ) -> Any:
        """
        Deserialize FlatBuffers binary to Python object (zero-copy)

        Args:
            buffer: FlatBuffers binary buffer
            schema_name: Schema type name (e.g., "SessionState")
            keep_buffer_alive: If True, keep buffer in memory for zero-copy access

        Returns:
            Deserialized object (FlatBuffers table instance)

        Raises:
            ValueError: If buffer too small or file identifier mismatch
            KeyError: If schema_name not registered

        Performance:
            - Deserialization: <0.1ms P95 (zero-copy, no parsing)
            - Field access: <0.05ms P95 (pointer arithmetic + dereference)
            - Memory: <1KB overhead (vtable + metadata)

        Zero-Copy Mechanism:
            1. Validate buffer size (minimum 8 bytes)
            2. Extract file identifier (bytes 4-8)
            3. Validate file identifier matches schema
            4. Cast buffer pointer to table type
            5. Read fields via vtable offsets (pointer arithmetic)
            6. Keep buffer alive if keep_buffer_alive=True

        Usage:
            # Deserialize SessionState
            buffer = receive_from_k0()  # 64KB FlatBuffers buffer

            state = deserializer.deserialize(
                buffer=buffer,
                schema_name='SessionState',
                keep_buffer_alive=True,  # Zero-copy
            )

            # Access fields (zero-copy, no memory allocation)
            session_id = state.SessionId()  # <0.05ms
            beliefs = state.Beliefs()        # <0.05ms

        ADR-0011c: Zero-copy deserialization (Section "Zero-Copy Architecture")
        ADR-0011d: File identifier validation (Section "File Identifier")

        TODO(@infrastructure-team): Implement zero-copy deserialization
        Assigned to: Issue #L5-3.1.2

        Steps:
            1. Get schema metadata from registry
            2. Validate buffer size (minimum 8 bytes)
            3. Extract file identifier (bytes 4-8 in buffer)
            4. Validate file identifier matches schema
            5. Create BufferWrapper if keep_buffer_alive=True
            6. Call schema's GetRootAs method (zero-copy cast)
            7. Record metrics (duration_ms, buffer_size)
            8. Return deserialized object
        """
        start_time = time.perf_counter()

        # TODO(@infrastructure-team): Get schema metadata
        metadata = self.schema_registry.get_schema(schema_name)

        # TODO(@infrastructure-team): Validate buffer size
        if len(buffer) < 8:
            raise ValueError(
                f"Buffer too small: {len(buffer)} bytes (minimum 8 bytes required)"
            )

        # TODO(@infrastructure-team): Extract file identifier
        file_id = buffer[4:8].decode("ascii")

        # TODO(@infrastructure-team): Validate file identifier
        if file_id != metadata.file_identifier:
            logger.warning(
                "file_identifier_mismatch",
                expected=metadata.file_identifier,
                actual=file_id,
                buffer_size=len(buffer),
            )
            raise ValueError(
                f"File identifier mismatch: expected {metadata.file_identifier}, got {file_id}"
            )

        # TODO(@infrastructure-team): Zero-copy deserialization
        # Create BufferWrapper to keep buffer alive
        if keep_buffer_alive:
            wrapper = BufferWrapper(buffer)
            self._buffers_kept_alive += 1
            # Use wrapper.buffer for deserialization (keeps buffer alive)
            # obj = metadata.root_type.GetRootAs(wrapper.buffer, 0)
            # obj._buffer_wrapper = wrapper  # Attach wrapper to object
        else:
            # Direct deserialization (buffer can be GC'd after)
            # obj = metadata.root_type.GetRootAs(buffer, 0)
            pass

        # TODO(@infrastructure-team): Record metrics
        end_time = time.perf_counter()
        duration_ms = (end_time - start_time) * 1000
        self._total_deserializations += 1
        self._total_bytes_read += len(buffer)

        # Check performance budget
        threshold = SLOW_DESERIALIZATION_THRESHOLD_MS.get(
            schema_name.lower(), SLOW_DESERIALIZATION_THRESHOLD_MS["default"]
        )
        if duration_ms > threshold:
            logger.warning(
                "deserialize_slow",
                schema_name=schema_name,
                duration_ms=duration_ms,
                threshold_ms=threshold,
                buffer_size=len(buffer),
            )

        # TODO(@infrastructure-team): Return deserialized object
        raise NotImplementedError(
            f"Deserialization for schema '{schema_name}' not yet implemented. "
            f"Schema-specific deserialization logic required (see ADR-0011b for codegen approach)."
        )

    def get_field(
        self,
        obj: Any,
        field_name: str,
    ) -> Any:
        """
        Get field value from deserialized object (zero-copy)

        Args:
            obj: Deserialized FlatBuffers table object
            field_name: Field name to access

        Returns:
            Field value (zero-copy access via vtable)

        Performance:
            - Field access: <0.05ms P95 (pointer arithmetic + dereference)
            - No memory allocation (read directly from buffer)

        Zero-Copy Mechanism:
            1. Get vtable pointer from table object
            2. Lookup field offset in vtable
            3. Add offset to table pointer
            4. Dereference pointer to get value
            5. Return value (no copy)

        Total: 4 pointer dereferences = ~20-30 CPU cycles = 0.01-0.02ms @ 2GHz

        Usage:
            # Deserialize SessionState
            state = deserializer.deserialize(buffer, 'SessionState')

            # Access fields (zero-copy)
            session_id = deserializer.get_field(state, 'session_id')
            # OR use direct method (generated by flatc)
            session_id = state.SessionId()

        ADR-0011c: Vtable-based field access (Section "Memory Layout")

        TODO(@infrastructure-team): Implement zero-copy field access
        Assigned to: Issue #L5-3.1.2

        Steps:
            1. Get method name (CamelCase field name)
            2. Call method on object (generated by flatc)
            3. Return value (zero-copy)
        """
        # TODO(@infrastructure-team): Convert field_name to method name
        # Example: "session_id" â†’ "SessionId"
        method_name = "".join(word.capitalize() for word in field_name.split("_"))

        # TODO(@infrastructure-team): Call method (generated by flatc)
        if hasattr(obj, method_name):
            return getattr(obj, method_name)()
        else:
            raise AttributeError(
                f"Field '{field_name}' not found in object (method: {method_name})"
            )

    def validate_file_identifier(
        self,
        buffer: bytes,
        expected_file_id: str,
    ) -> bool:
        """
        Validate buffer file identifier matches expected

        Args:
            buffer: FlatBuffers binary buffer
            expected_file_id: Expected 4-character file ID

        Returns:
            True if file identifier matches, False otherwise

        Usage:
            # Validate buffer before deserialization
            if deserializer.validate_file_identifier(buffer, "SEST"):
                state = deserializer.deserialize(buffer, "SessionState")
            else:
                logger.error("Invalid buffer file identifier")

        ADR-0011d: File identifier validation (Section "File Identifier")

        TODO(@infrastructure-team): Implement file identifier validation
        Assigned to: Issue #L5-3.1.2
        """
        if len(buffer) < 8:
            return False

        file_id = buffer[4:8].decode("ascii", errors="ignore")
        return file_id == expected_file_id

    def get_stats(self) -> Dict[str, Any]:
        """
        Get deserializer statistics

        Returns:
            Dict with:
                - total_deserializations: Lifetime deserialization count
                - total_bytes_read: Total bytes deserialized
                - buffers_kept_alive: Count of buffers kept alive for zero-copy

        TODO(@infrastructure-team): Implement stats collection
        Assigned to: Issue #L5-3.1.2
        """
        return {
            "total_deserializations": self._total_deserializations,
            "total_bytes_read": self._total_bytes_read,
            "buffers_kept_alive": self._buffers_kept_alive,
        }


# =============================================================================
# SECTION 5: MODULE EXPORTS
# =============================================================================

__all__ = [
    "Deserializer",
    "BufferWrapper",
]


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================
# Metrics to export:
#   - k1_flatbuffers_deserialize_duration_ms{schema_type} (histogram: P50/P95/P99 deserialization latency)
#   - k1_flatbuffers_deserialize_calls_total{schema_type, status} (counter: success/error)
#   - k1_flatbuffers_field_access_duration_ms{schema_type, field_name} (histogram: field access latency)
#   - k1_flatbuffers_buffer_kept_alive_count (gauge: buffers kept alive for zero-copy)
#   - k1_flatbuffers_file_identifier_mismatches_total (counter: file identifier validation failures)
#
# Logs to emit:
#   - Level: DEBUG (normal), WARNING (file ID mismatch, slow deserialization), ERROR (failures)
#   - Fields: component="serialization.deserializer", schema_name, duration_ms, buffer_size, file_identifier, error
#   - Events: deserialize_started, deserialize_completed, file_identifier_mismatch, deserialize_slow, deserialize_failed
#
# =============================================================================

# =============================================================================
# TESTING REQUIREMENTS (WARD Framework)
# =============================================================================
# Integration tests required:
#   - tests/k1/l5_infrastructure/serialization/test_deserializer.py
#   - Test: zero-copy deserialization (buffer kept alive, no memory allocation)
#   - Test: file identifier validation (valid/invalid/mismatch)
#   - Test: performance budgets (SessionState <0.1ms, K0 Event <0.05ms)
#   - Test: field access latency (<0.05ms via vtable lookup)
#   - Test: buffer lifetime (buffer stays alive until object destroyed)
#   - Test: schema evolution (forward compatibility, backward compatibility)
#   - Test: error handling (invalid buffer, too small, corrupt vtable)
#
# Benchmark tests required:
#   - ward-benchmark for performance validation
#   - Measure deserialization latency (P50/P95/P99)
#   - Measure field access latency (P50/P95/P99)
#   - Compare with JSON baseline (expected 150-200Ã— faster)
#   - Validate zero-copy (no memory allocation during field access)
#
# No simulation code allowed:
#   - Use real FlatBuffers schemas from k1/contracts/flatbuffers/
#   - Test with actual generated Python bindings
#   - Integration tests > unit tests
#
# =============================================================================

