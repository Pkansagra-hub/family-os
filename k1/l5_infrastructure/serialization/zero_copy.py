"""
Zero-Copy Access - Direct Buffer Access Helpers for FlatBuffers

Layer: L5 Infrastructure
Component: Serialization (Optimization & Advanced Features)
Priority: P0 (Critical Path)
Status: ðŸš§ STUB - NEEDS_IMPLEMENTATION

Architecture Decision Records:
    - ADR-0011: FlatBuffers Serialization Core
      * Zero-copy deserialization: Access data without copying/parsing
      * Field access via vtable offsets: 2-3 CPU cycles (0.01-0.02ms @ 2GHz)
      * Memory layout: Vtables point to field offsets for direct access
      * Section: "Zero-Copy Architecture" (Field Access Performance)

    - ADR-0011c: Serialization Performance & Zero-Copy
      * Vtable-based field access: Pointer arithmetic + dereference
      * No parsing overhead: 35-200Ã— faster than JSON/Protobuf
      * Buffer lifetime management: Keep buffer alive for object lifetime
      * Section: "Zero-Copy Deserialization" (Memory Layout, Vtable Compression)

Dependencies:
    Internal:
        - k1.l5_infrastructure.serialization.deserializer (BufferWrapper)

    External:
        - flatbuffers (Python bindings)
        - typing (type hints)
        - logging (structured logging)

Connects To:
    Used By:
        - k1.l5_infrastructure.serialization.deserializer.Deserializer (field access)
        - k1.l4_runtime.session_state (SessionState field access)
        - k1.l3_execution.agents (AgentState field access)

Performance Budgets:
    - Root table access: <0.01ms P95 (just offset calculation)
    - Field offset calculation: <0.01ms P95 (vtable lookup + pointer arithmetic)
    - String access: <1ms P95 (UTF-8 decode, minimal copy)
    - Nested object access: <0.05ms P95 (chain offset lookups)

Observability:
    - Metrics:
        * k1_zero_copy_access_total{type} (counter: root/field/string/nested)
        * k1_zero_copy_access_duration_seconds{type} (histogram: access latency)
        * k1_vtable_cache_hit_rate (gauge: vtable cache hit rate 0.0-1.0)

    - Logs:
        * DEBUG: zero_copy_access (type, offset, buffer_size)
        * DEBUG: vtable_lookup (field_index, offset)
        * WARNING: buffer_lifetime_warning (buffer deallocated, reference exists)

References:
    - ADR-0011: FlatBuffers Serialization Core (Zero-Copy Architecture)
    - ADR-0011c: Serialization Performance & Zero-Copy (Vtable Compression, Field Access)
    - Test: tests/k1/l5_infrastructure/serialization/test_zero_copy.py
"""

import logging
import struct

# =============================================================================
# SECTION 1: IMPORTS
# =============================================================================
# Standard library imports
from typing import Optional, Union

# Configure module logger
logger = logging.getLogger(__name__)


# =============================================================================
# SECTION 2: CONSTANTS & CONFIGURATION
# =============================================================================

# FlatBuffers file identifier size
FILE_IDENTIFIER_SIZE = 4

# Vtable header sizes
VTABLE_SIZE_BYTES = 2
TABLE_SIZE_BYTES = 2
FIELD_OFFSET_BYTES = 2

# Default alignment
DEFAULT_ALIGNMENT = 4


# =============================================================================
# SECTION 3: ZERO-COPY ACCESSOR CLASS
# =============================================================================


class ZeroCopyAccessor:
    """
    Utilities for zero-copy field access from FlatBuffers

    Purpose:
        Provide direct buffer access helpers for zero-copy deserialization.
        Enables accessing nested structures, repeated fields, and strings
        without copying data from the buffer.

    Zero-Copy Principles (from ADR-0011, ADR-0011c):
        - **No Parsing:** Read data directly via pointer arithmetic
        - **No Allocation:** Access buffer in-place, no memory copy
        - **Vtable-Based:** Field offsets stored in vtable (2-3 CPU cycles)
        - **Buffer Lifetime:** Keep buffer alive for object lifetime

    Performance Targets (from ADR-0011c):
        - Root table access: <0.01ms P95 (offset calculation)
        - Field offset calculation: <0.01ms P95 (vtable lookup)
        - String access: <1ms P95 (UTF-8 decode for 1KB string)
        - Nested object access: <0.05ms P95 (chain offsets)

    Memory Layout (from ADR-0011c):
        â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
        â”‚  File Identifier (4 bytes): "AGST"                          â”‚
        â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
        â”‚  Buffer Size (4 bytes): 256                                 â”‚
        â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
        â”‚  Root Table Offset (4 bytes): 12                            â”‚
        â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
        â”‚  AgentState Table:                                          â”‚
        â”‚    Vtable Offset (4 bytes): -8 (relative offset)           â”‚
        â”‚    agent_id Offset (4 bytes): 24 (relative offset)         â”‚
        â”‚    state (1 byte): 2                                        â”‚
        â”‚    padding (3 bytes): 0x00                                  â”‚
        â”‚    memory_mb (4 bytes): 512                                 â”‚
        â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
        â”‚  Vtable:                                                    â”‚
        â”‚    Vtable Size (2 bytes): 12                                â”‚
        â”‚    Table Size (2 bytes): 20                                 â”‚
        â”‚    Field 0 Offset (2 bytes): 4  (agent_id)                 â”‚
        â”‚    Field 1 Offset (2 bytes): 8  (state)                    â”‚
        â”‚    Field 2 Offset (2 bytes): 12 (memory_mb)                â”‚
        â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
        â”‚  String: "agent_xyz"                                        â”‚
        â”‚    Length (4 bytes): 9                                      â”‚
        â”‚    Data (9 bytes): "agent_xyz"                              â”‚
        â”‚    Null terminator (1 byte): 0x00                           â”‚
        â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜

    ADR-0011: Zero-copy deserialization architecture
    ADR-0011c: Vtable-based field access performance
    """

    @staticmethod
    def get_root_table(
        buffer: Union[bytes, bytearray, memoryview], offset: int = 0
    ) -> int:
        """
        Get root table offset from buffer (zero-copy)

        Args:
            buffer: Binary FlatBuffers data
            offset: Offset to root table reference (default: 0, after file identifier)

        Returns:
            Absolute offset to root table in buffer

        Performance:
            - Access: <0.01ms P95 (just offset calculation, no copy)
            - CPU: 2-3 cycles (read 4 bytes, add to offset)

        Memory Layout (from ADR-0011c):
            buffer[offset:offset+4] = relative offset to root table
            root_table_offset = offset + 4 + relative_offset

        Example:
            # Get root table for AgentState
            buf = serialize_agent_state("agent_xyz", 2, 512)
            root_offset = ZeroCopyAccessor.get_root_table(buf, 0)
            # root_offset = 12 (typically after 4-byte file ID + 4-byte buffer size)

        ADR-0011: "Zero-Copy Architecture" (Root table access)

        TODO(@infrastructure-team): Implement root table access
        Assigned to: Issue #L5-3.3.1

        Steps:
            1. Read 4 bytes at offset (relative offset to root table)
            2. Add offset + 4 + relative_offset to get absolute offset
            3. Return absolute offset
            4. Log access for observability
        """
        # Read relative offset to root table (4 bytes, little-endian)
        relative_offset = struct.unpack("<I", buffer[offset : offset + 4])[0]

        # Calculate absolute offset
        root_table_offset = offset + 4 + relative_offset

        logger.debug(
            "zero_copy_root_access",
            offset=offset,
            relative_offset=relative_offset,
            root_table_offset=root_table_offset,
            buffer_size=len(buffer),
        )

        return root_table_offset

    @staticmethod
    def get_vtable_offset(
        buffer: Union[bytes, bytearray, memoryview], table_offset: int
    ) -> int:
        """
        Get vtable offset from table (zero-copy)

        Args:
            buffer: Binary FlatBuffers data
            table_offset: Offset to table (from get_root_table)

        Returns:
            Absolute offset to vtable in buffer

        Performance:
            - Access: <0.01ms P95 (offset calculation)

        Memory Layout (from ADR-0011c):
            buffer[table_offset:table_offset+4] = relative offset to vtable (signed, negative)
            vtable_offset = table_offset - abs(relative_offset)

        ADR-0011c: "Zero-Copy Deserialization" (Vtable lookup)

        TODO(@infrastructure-team): Implement vtable offset calculation
        Assigned to: Issue #L5-3.3.1

        Steps:
            1. Read 4 bytes at table_offset (signed relative offset to vtable)
            2. Calculate vtable_offset = table_offset - abs(relative_offset)
            3. Return vtable_offset
        """
        # Read relative offset to vtable (4 bytes, little-endian, signed)
        relative_offset = struct.unpack("<i", buffer[table_offset : table_offset + 4])[
            0
        ]

        # Calculate absolute vtable offset (relative_offset is negative)
        vtable_offset = table_offset - abs(relative_offset)

        logger.debug(
            "vtable_offset_calc",
            table_offset=table_offset,
            relative_offset=relative_offset,
            vtable_offset=vtable_offset,
        )

        return vtable_offset

    @staticmethod
    def get_field_offset(
        buffer: Union[bytes, bytearray, memoryview],
        table_offset: int,
        field_index: int,
    ) -> Optional[int]:
        """
        Calculate field offset from vtable (zero-copy)

        Args:
            buffer: Binary FlatBuffers data
            table_offset: Offset to table (from get_root_table)
            field_index: Field index in schema (0-based)

        Returns:
            Absolute offset to field in buffer, or None if field not present

        Performance:
            - Calculation: <0.01ms P95 (vtable lookup + offset calculation)
            - CPU: 5-10 cycles (read vtable header, read field offset, add offsets)

        Memory Layout (from ADR-0011c):
            1. Get vtable offset from table
            2. Read vtable header (vtable_size, table_size)
            3. Read field offset from vtable (vtable[4 + field_index * 2])
            4. If field_offset == 0, field not present (return None)
            5. Calculate absolute field offset = table_offset + field_offset

        Field Access (from ADR-0011c):
            # 1. Get root table pointer
            root_offset = buffer[8:12]  # Read 4 bytes at offset 8
            table_ptr = root_offset      # Pointer to AgentState table

            # 2. Get vtable pointer
            vtable_offset = buffer[table_ptr:table_ptr+4]  # Relative offset
            vtable_ptr = table_ptr + vtable_offset         # Absolute vtable pointer

            # 3. Get field offset from vtable
            field_offset = buffer[vtable_ptr+4:vtable_ptr+6]  # Field 0 offset (agent_id)

            # 4. Get field value
            field_ptr = table_ptr + field_offset
            field_value = buffer[field_ptr:field_ptr+4]  # String offset

            # Total: 4 pointer dereferences, no memory copy, no parsing
            # Performance: ~20-30 CPU cycles = 0.01-0.02ms @ 2GHz

        ADR-0011c: "Zero-Copy Deserialization" (Field Access)

        TODO(@infrastructure-team): Implement field offset calculation
        Assigned to: Issue #L5-3.3.1

        Steps:
            1. Get vtable offset from table
            2. Read vtable header (vtable_size at vtable[0:2], table_size at vtable[2:4])
            3. Check if field_index valid (field_index < (vtable_size - 4) / 2)
            4. Read field offset from vtable (vtable[4 + field_index * 2 : 4 + field_index * 2 + 2])
            5. If field_offset == 0, return None (field not present)
            6. Calculate absolute field offset = table_offset + field_offset
            7. Return absolute field offset
        """
        # Get vtable offset
        vtable_offset = ZeroCopyAccessor.get_vtable_offset(buffer, table_offset)

        # Read vtable header
        vtable_size = struct.unpack("<H", buffer[vtable_offset : vtable_offset + 2])[0]
        table_size = struct.unpack("<H", buffer[vtable_offset + 2 : vtable_offset + 4])[
            0
        ]

        # Check field_index valid
        max_fields = (vtable_size - 4) // 2
        if field_index >= max_fields:
            logger.debug(
                "field_index_out_of_range",
                field_index=field_index,
                max_fields=max_fields,
                vtable_size=vtable_size,
            )
            return None

        # Read field offset from vtable
        field_offset_pos = vtable_offset + 4 + (field_index * 2)
        field_offset = struct.unpack(
            "<H", buffer[field_offset_pos : field_offset_pos + 2]
        )[0]

        # If field_offset == 0, field not present
        if field_offset == 0:
            logger.debug(
                "field_not_present",
                field_index=field_index,
                table_offset=table_offset,
            )
            return None

        # Calculate absolute field offset
        absolute_field_offset = table_offset + field_offset

        logger.debug(
            "field_offset_calc",
            field_index=field_index,
            table_offset=table_offset,
            vtable_offset=vtable_offset,
            field_offset=field_offset,
            absolute_field_offset=absolute_field_offset,
        )

        return absolute_field_offset

    @staticmethod
    def get_string(
        buffer: Union[bytes, bytearray, memoryview],
        offset: int,
    ) -> str:
        """
        Extract string from buffer (minimal copy for UTF-8 decode)

        Args:
            buffer: Binary FlatBuffers data
            offset: Offset to string (absolute offset from get_field_offset)

        Returns:
            Decoded UTF-8 string

        Performance:
            - Decode: <1ms P95 for 1KB string (UTF-8 decode overhead)
            - Memory: Minimal copy (only string bytes, not entire buffer)

        Memory Layout (from ADR-0011c):
            buffer[offset:offset+4] = string length (4 bytes, little-endian)
            buffer[offset+4:offset+4+length] = string data (UTF-8)
            buffer[offset+4+length] = null terminator (1 byte)

        Example:
            # Get agent_id string from AgentState
            field_offset = ZeroCopyAccessor.get_field_offset(buf, root_offset, 0)  # Field 0 = agent_id
            string_offset_rel = struct.unpack('<I', buf[field_offset:field_offset+4])[0]
            string_offset_abs = field_offset + 4 + string_offset_rel
            agent_id = ZeroCopyAccessor.get_string(buf, string_offset_abs)
            # agent_id = "agent_xyz"

        ADR-0011c: "Zero-Copy Deserialization" (String Access)

        TODO(@infrastructure-team): Implement string extraction
        Assigned to: Issue #L5-3.3.1

        Steps:
            1. Read string length (4 bytes at offset)
            2. Extract string data (offset+4 to offset+4+length)
            3. Decode UTF-8 (minimal copy required)
            4. Return decoded string
        """
        # Read string length
        string_length = struct.unpack("<I", buffer[offset : offset + 4])[0]

        # Extract string data (UTF-8)
        string_data = buffer[offset + 4 : offset + 4 + string_length]

        # Decode UTF-8
        string_value = string_data.decode("utf-8")

        logger.debug(
            "string_access",
            offset=offset,
            length=string_length,
            value_preview=string_value[:50] if len(string_value) > 50 else string_value,
        )

        return string_value

    @staticmethod
    def get_nested_table_offset(
        buffer: Union[bytes, bytearray, memoryview],
        field_offset: int,
    ) -> int:
        """
        Get nested table offset from field (zero-copy)

        Args:
            buffer: Binary FlatBuffers data
            field_offset: Offset to field containing nested table reference

        Returns:
            Absolute offset to nested table

        Performance:
            - Access: <0.05ms P95 (chain offset lookups)

        Memory Layout:
            buffer[field_offset:field_offset+4] = relative offset to nested table
            nested_table_offset = field_offset + 4 + relative_offset

        Example:
            # Get SessionState.beliefs nested table
            beliefs_field_offset = ZeroCopyAccessor.get_field_offset(buf, root_offset, 1)  # Field 1 = beliefs
            beliefs_table_offset = ZeroCopyAccessor.get_nested_table_offset(buf, beliefs_field_offset)
            # Now access beliefs table fields at beliefs_table_offset

        ADR-0011: "Zero-Copy Architecture" (Nested object access)

        TODO(@infrastructure-team): Implement nested table access
        Assigned to: Issue #L5-3.3.1

        Steps:
            1. Read 4 bytes at field_offset (relative offset to nested table)
            2. Calculate nested_table_offset = field_offset + 4 + relative_offset
            3. Return nested_table_offset
        """
        # Read relative offset to nested table
        relative_offset = struct.unpack("<I", buffer[field_offset : field_offset + 4])[
            0
        ]

        # Calculate absolute nested table offset
        nested_table_offset = field_offset + 4 + relative_offset

        logger.debug(
            "nested_table_access",
            field_offset=field_offset,
            relative_offset=relative_offset,
            nested_table_offset=nested_table_offset,
        )

        return nested_table_offset

    @staticmethod
    def get_vector_length(
        buffer: Union[bytes, bytearray, memoryview],
        field_offset: int,
    ) -> int:
        """
        Get vector (array) length from field (zero-copy)

        Args:
            buffer: Binary FlatBuffers data
            field_offset: Offset to field containing vector reference

        Returns:
            Vector length (number of elements)

        Performance:
            - Access: <0.01ms P95 (offset calculation + read length)

        Memory Layout:
            buffer[field_offset:field_offset+4] = relative offset to vector
            vector_offset = field_offset + 4 + relative_offset
            buffer[vector_offset:vector_offset+4] = vector length

        Example:
            # Get length of agents vector in SessionState.control
            agents_field_offset = ZeroCopyAccessor.get_field_offset(buf, control_offset, 0)  # Field 0 = agents
            agents_count = ZeroCopyAccessor.get_vector_length(buf, agents_field_offset)
            # agents_count = 5 (5 active agents)

        ADR-0011: "Zero-Copy Architecture" (Repeated field access)

        TODO(@infrastructure-team): Implement vector length access
        Assigned to: Issue #L5-3.3.1

        Steps:
            1. Read relative offset to vector (4 bytes at field_offset)
            2. Calculate vector_offset = field_offset + 4 + relative_offset
            3. Read vector length (4 bytes at vector_offset)
            4. Return vector length
        """
        # Read relative offset to vector
        relative_offset = struct.unpack("<I", buffer[field_offset : field_offset + 4])[
            0
        ]

        # Calculate vector offset
        vector_offset = field_offset + 4 + relative_offset

        # Read vector length
        vector_length = struct.unpack("<I", buffer[vector_offset : vector_offset + 4])[
            0
        ]

        logger.debug(
            "vector_length_access",
            field_offset=field_offset,
            vector_offset=vector_offset,
            length=vector_length,
        )

        return vector_length


# =============================================================================
# SECTION 4: MODULE EXPORTS
# =============================================================================

__all__ = [
    "ZeroCopyAccessor",
]


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================
# Metrics to export:
#   - k1_zero_copy_access_total{type} (counter: root/field/string/nested/vector)
#   - k1_zero_copy_access_duration_seconds{type} (histogram: access latency)
#   - k1_vtable_cache_hit_rate (gauge: vtable cache hit rate 0.0-1.0)
#
# Logs to emit:
#   - Level: DEBUG (access operations)
#   - Fields: component="serialization.zero_copy", offset, buffer_size, field_index
#   - Events: zero_copy_root_access, vtable_offset_calc, field_offset_calc, string_access, nested_table_access, vector_length_access
#
# =============================================================================

# =============================================================================
# TESTING REQUIREMENTS (WARD Framework)
# =============================================================================
# Integration tests required:
#   - tests/k1/l5_infrastructure/serialization/test_zero_copy.py
#   - Test: get_root_table (correct offset calculation)
#   - Test: get_vtable_offset (vtable lookup)
#   - Test: get_field_offset (field offset calculation, missing fields)
#   - Test: get_string (UTF-8 decode, minimal copy)
#   - Test: get_nested_table_offset (nested object access)
#   - Test: get_vector_length (array length access)
#   - Test: performance (access <0.01ms P95 for root/field, <1ms for string)
#   - Test: buffer lifetime (keep buffer alive during access)
#
# Benchmark tests required:
#   - ward-benchmark for performance validation
#   - Measure root table access (<0.01ms P95)
#   - Measure field offset calculation (<0.01ms P95)
#   - Measure string access (<1ms P95 for 1KB string)
#   - Compare with JSON deserialization (35-200Ã— faster)
#
# No simulation code allowed:
#   - Use real FlatBuffers buffers (serialized with flatbuffers.Builder)
#   - Test with actual schemas (AgentState, SessionState, TaskAnnouncement)
#   - Integration tests > unit tests
#
# =============================================================================

