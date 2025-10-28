"""
String Deduplication - Reduce Payload Size by Deduplicating Strings

Layer: L5 Infrastructure
Component: Serialization (Optimization & Advanced Features)
Priority: P1 (Important for Optimization)
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

Architecture Decision Records:
    - ADR-0011c: Serialization Performance & Zero-Copy
      * String deduplication: Store strings once, reference with offsets
      * Size savings: 30-50% for text-heavy data (typical)
      * Overhead: <10% serialization time (hash table + reference resolution)
      * Trade-off: Slower serialization, smaller payload, faster deserialization
      * Section: "Memory Layout Optimization" (String Deduplication)

Dependencies:
    Internal:
        - k1.l5_infrastructure.serialization.serializer (Serializer)

    External:
        - flatbuffers (Python bindings)
        - typing (type hints)
        - logging (structured logging)

Connects To:
    Used By:
        - k1.l5_infrastructure.serialization.serializer.Serializer (optional dedup)
        - k1.l4_runtime.session_state (SessionState serialization)
        - k1.l2_orchestration.plan (Plan serialization with repeated strings)

Performance Impact:
    - Serialization overhead: <10% (hash table operations)
    - Size savings: 30-50% for text-heavy data (repeated strings)
    - Deserialization speedup: Fewer allocations (strings stored once)
    - Memory overhead: Hash table (O(unique_strings))

Observability:
    - Metrics:
        * k1_string_dedup_operations_total{result} (counter: hit/miss)
        * k1_string_dedup_size_savings_bytes (counter: bytes saved)
        * k1_string_dedup_ratio (gauge: savings ratio 0.0-1.0)
        * k1_string_dedup_overhead_ms (histogram: overhead latency)

    - Logs:
        * DEBUG: string_dedup_hit (string_hash, offset)
        * DEBUG: string_dedup_miss (string_hash, new_offset)
        * INFO: string_dedup_stats (size_before, size_after, savings_percent)

References:
    - ADR-0011c: Serialization Performance & Zero-Copy (String Deduplication section)
    - Test: tests/k1/l5_infrastructure/serialization/test_string_dedup.py
"""

import hashlib
import logging
from collections import defaultdict

# =============================================================================
# SECTION 1: IMPORTS
# =============================================================================
# Standard library imports
from typing import Any, Dict, Optional

# Third-party imports (FlatBuffers)
try:
    import flatbuffers
except ImportError:
    flatbuffers = None  # Will raise error in __init__ if not installed

# Configure module logger
logger = logging.getLogger(__name__)


# =============================================================================
# SECTION 2: CONSTANTS & CONFIGURATION
# =============================================================================

# String deduplication thresholds
MIN_STRING_LENGTH_FOR_DEDUP = 8  # Strings < 8 bytes not worth deduplicating
MIN_OCCURRENCES_FOR_DEDUP = 2  # Must occur at least 2× to deduplicate

# Hash algorithm for string deduplication
STRING_HASH_ALGORITHM = "xxhash64"  # Fast non-cryptographic hash


# =============================================================================
# SECTION 3: STRING DEDUPLICATOR CLASS
# =============================================================================


class StringDeduplicator:
    """
    Deduplicate strings during FlatBuffers serialization

    Purpose:
        Reduce payload size by detecting duplicate strings and storing
        them only once in the FlatBuffers buffer. References use offsets.

    Strategy (from ADR-0011c):
        1. **First Pass:** Build frequency map (count string occurrences)
        2. **Second Pass:** Serialize frequent strings once, store offsets
        3. **References:** Use stored offsets for duplicate strings
        4. **Trade-off:** Slower serialization (2-pass), smaller payload, faster deserialization

    Example (from ADR-0011c):
        SessionState contains: ["intent", "reminder", "intent", "reminder"]

        Without deduplication:
            4 strings × 7 bytes average = 28 bytes total

        With deduplication:
            2 unique strings × 7 bytes = 14 bytes
            2 references × 4 bytes = 8 bytes
            Total: 22 bytes
            Savings: 21% (6 bytes saved)

        Real-world example (SessionState with 100 entities):
            Without dedup: 6,400 bytes (64 bytes per entity)
            With dedup: 4,200 bytes (42 bytes per entity, shared strings)
            Savings: 34% (2,200 bytes saved)

    Performance Targets (from ADR-0011c):
        - Overhead: <10% serialization time (hash table operations)
        - Size savings: 30-50% for text-heavy data (typical SessionState)
        - Deserialization speedup: Fewer allocations (strings stored once)

    Trade-offs:
        - ✅ Smaller payload: 30-50% reduction for text-heavy data
        - ✅ Faster deserialization: Fewer allocations (strings stored once)
        - ✅ Network savings: Reduced bandwidth for K0 bridge
        - ⚠️ Slower serialization: 2-pass (build frequency map + serialize)
        - ⚠️ Memory overhead: Hash table (O(unique_strings))

    ADR-0011c: "Memory Layout Optimization" (String Deduplication section)
    """

    def __init__(
        self,
        min_length: int = MIN_STRING_LENGTH_FOR_DEDUP,
        min_occurrences: int = MIN_OCCURRENCES_FOR_DEDUP,
    ):
        """
        Initialize string deduplicator

        Args:
            min_length: Minimum string length to deduplicate (default: 8 bytes)
            min_occurrences: Minimum occurrences to deduplicate (default: 2×)

        TODO(@infrastructure-team): Initialize string deduplicator
        Assigned to: Issue #L5-3.3.2

        Steps:
            1. Initialize frequency map (str → count)
            2. Initialize offset map (str → FlatBuffers offset)
            3. Initialize stats (size_before, size_after, savings)
        """
        self.min_length = min_length
        self.min_occurrences = min_occurrences

        # Frequency map: string → count
        self.frequency_map: Dict[str, int] = defaultdict(int)

        # Offset map: string → FlatBuffers offset (for deduplication)
        self.offset_map: Dict[str, int] = {}

        # Stats
        self.strings_total = 0
        self.strings_unique = 0
        self.size_before = 0
        self.size_after = 0

        logger.debug(
            "string_deduplicator_initialized",
            min_length=min_length,
            min_occurrences=min_occurrences,
        )

    def _should_deduplicate(self, string: str) -> bool:
        """
        Check if string should be deduplicated

        Args:
            string: String to check

        Returns:
            True if string should be deduplicated, False otherwise

        Criteria:
            1. String length >= min_length (8 bytes)
            2. String occurrences >= min_occurrences (2×)

        TODO(@infrastructure-team): Implement deduplication check
        Assigned to: Issue #L5-3.3.2
        """
        return (
            len(string) >= self.min_length
            and self.frequency_map[string] >= self.min_occurrences
        )

    def _hash_string(self, string: str) -> str:
        """
        Hash string for deduplication (fast non-cryptographic)

        Args:
            string: String to hash

        Returns:
            Hex digest of string hash

        Note: Using SHA256 for stub (replace with xxhash in production)

        TODO(@infrastructure-team): Replace with xxhash for performance
        Assigned to: Issue #L5-3.3.2
        """
        # STUB: Using SHA256 (replace with xxhash for production)
        return hashlib.sha256(string.encode("utf-8")).hexdigest()

    def build_frequency_map(self, obj: Any) -> None:
        """
        Build frequency map by traversing object (first pass)

        Args:
            obj: Object to traverse (dict, list, or primitive)

        Side Effects:
            - Populates frequency_map with string counts

        Traversal Strategy:
            - Recursively traverse dicts, lists, tuples
            - Count string occurrences
            - Track total strings and size

        Example:
            obj = {
                "entities": ["intent", "reminder", "intent", "reminder"],
                "tools": ["search", "calendar", "search"],
            }

            build_frequency_map(obj)
            # frequency_map = {"intent": 2, "reminder": 2, "search": 2, "calendar": 1}

        TODO(@infrastructure-team): Implement frequency map builder
        Assigned to: Issue #L5-3.3.2

        Steps:
            1. If obj is dict: Recurse on keys and values
            2. If obj is list/tuple: Recurse on elements
            3. If obj is str: Increment frequency_map[obj], track size
            4. Otherwise: Skip (primitive types)
        """
        if isinstance(obj, dict):
            for key, value in obj.items():
                self.build_frequency_map(key)
                self.build_frequency_map(value)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                self.build_frequency_map(item)
        elif isinstance(obj, str):
            self.strings_total += 1
            self.size_before += (
                len(obj) + 4 + 1
            )  # string length + 4-byte length prefix + null terminator
            self.frequency_map[obj] += 1

    def create_string_with_dedup(
        self,
        builder: "flatbuffers.Builder",
        string: str,
    ) -> int:
        """
        Create string in builder with deduplication

        Args:
            builder: FlatBuffers builder
            string: String to create

        Returns:
            FlatBuffers offset to string (deduplicated if possible)

        Strategy:
            1. Check if string should be deduplicated
            2. If yes and already created: Return stored offset (hit)
            3. If yes and not created: Create string, store offset (miss)
            4. If no: Create string without storing (not worth deduplicating)

        Example:
            # First occurrence of "intent"
            offset1 = dedup.create_string_with_dedup(builder, "intent")  # Miss, create new

            # Second occurrence of "intent"
            offset2 = dedup.create_string_with_dedup(builder, "intent")  # Hit, reuse offset1

            # offset1 == offset2 (same string stored once)

        TODO(@infrastructure-team): Implement string creation with deduplication
        Assigned to: Issue #L5-3.3.2

        Steps:
            1. Check if string should be deduplicated (_should_deduplicate)
            2. If yes:
                a. Check if offset already exists in offset_map (hit)
                b. If hit: Return existing offset, log hit
                c. If miss: Create string, store offset, log miss
            3. If no: Create string without storing
            4. Return offset
        """
        # Check if should deduplicate
        if self._should_deduplicate(string):
            # Check if already created (hit)
            if string in self.offset_map:
                offset = self.offset_map[string]
                logger.debug(
                    "string_dedup_hit",
                    string_hash=self._hash_string(string)[:16],
                    offset=offset,
                )
                return offset

            # Not created yet (miss)
            offset = builder.CreateString(string)
            self.offset_map[string] = offset
            self.strings_unique += 1
            self.size_after += (
                len(string) + 4 + 1
            )  # string + length prefix + null terminator

            logger.debug(
                "string_dedup_miss",
                string_hash=self._hash_string(string)[:16],
                new_offset=offset,
            )

            return offset

        # Not worth deduplicating
        offset = builder.CreateString(string)
        self.size_after += len(string) + 4 + 1
        return offset

    def get_dedup_stats(self) -> Dict[str, Any]:
        """
        Get deduplication statistics

        Returns:
            Dict with:
                - strings_total: Total string count
                - strings_unique: Unique strings
                - size_before: Original size (bytes)
                - size_after: After dedup (bytes)
                - size_saved: Bytes saved
                - savings_percent: (size_before - size_after) / size_before × 100
                - hit_rate: offset_map hits / strings_total

        Example:
            stats = dedup.get_dedup_stats()
            print(f"Size savings: {stats['savings_percent']:.1f}%")
            print(f"Hit rate: {stats['hit_rate']:.1%}")

        TODO(@infrastructure-team): Implement stats collection
        Assigned to: Issue #L5-3.3.2

        Steps:
            1. Calculate size_saved = size_before - size_after
            2. Calculate savings_percent = (size_saved / size_before) × 100
            3. Calculate hit_rate = (strings_total - strings_unique) / strings_total
            4. Return stats dict
        """
        size_saved = self.size_before - self.size_after
        savings_percent = (
            (size_saved / self.size_before * 100) if self.size_before > 0 else 0.0
        )
        hit_rate = (
            ((self.strings_total - self.strings_unique) / self.strings_total)
            if self.strings_total > 0
            else 0.0
        )

        stats = {
            "strings_total": self.strings_total,
            "strings_unique": self.strings_unique,
            "size_before": self.size_before,
            "size_after": self.size_after,
            "size_saved": size_saved,
            "savings_percent": savings_percent,
            "hit_rate": hit_rate,
        }

        logger.info(
            "string_dedup_stats",
            **stats,
        )

        return stats

    def reset(self) -> None:
        """
        Reset deduplicator state for next serialization

        Side Effects:
            - Clears frequency_map, offset_map, stats

        TODO(@infrastructure-team): Implement reset
        Assigned to: Issue #L5-3.3.2
        """
        self.frequency_map.clear()
        self.offset_map.clear()
        self.strings_total = 0
        self.strings_unique = 0
        self.size_before = 0
        self.size_after = 0

        logger.debug("string_deduplicator_reset")


# =============================================================================
# SECTION 4: CONVENIENCE FUNCTIONS
# =============================================================================


def create_string_with_dedup(
    builder: "flatbuffers.Builder",
    string: str,
    deduplicator: Optional[StringDeduplicator] = None,
) -> int:
    """
    Convenience function for creating strings with optional deduplication

    Args:
        builder: FlatBuffers builder
        string: String to create
        deduplicator: Optional StringDeduplicator instance

    Returns:
        FlatBuffers offset to string

    Usage:
        # Without deduplication
        offset = create_string_with_dedup(builder, "intent")

        # With deduplication
        dedup = StringDeduplicator()
        dedup.build_frequency_map(obj)  # First pass
        offset = create_string_with_dedup(builder, "intent", deduplicator=dedup)  # Second pass

    TODO(@infrastructure-team): Implement convenience function
    Assigned to: Issue #L5-3.3.2
    """
    if deduplicator:
        return deduplicator.create_string_with_dedup(builder, string)
    else:
        return builder.CreateString(string)


# =============================================================================
# SECTION 5: MODULE EXPORTS
# =============================================================================

__all__ = [
    "StringDeduplicator",
    "create_string_with_dedup",
]


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================
# Metrics to export:
#   - k1_string_dedup_operations_total{result} (counter: hit/miss)
#   - k1_string_dedup_size_savings_bytes (counter: bytes saved)
#   - k1_string_dedup_ratio (gauge: savings ratio 0.0-1.0)
#   - k1_string_dedup_overhead_ms (histogram: overhead latency)
#
# Logs to emit:
#   - Level: DEBUG (hit/miss), INFO (stats)
#   - Fields: component="serialization.string_dedup", string_hash, offset, size_before, size_after
#   - Events: string_dedup_hit, string_dedup_miss, string_dedup_stats
#
# =============================================================================

# =============================================================================
# TESTING REQUIREMENTS (WARD Framework)
# =============================================================================
# Integration tests required:
#   - tests/k1/l5_infrastructure/serialization/test_string_dedup.py
#   - Test: build_frequency_map (traverse dict/list, count strings)
#   - Test: create_string_with_dedup (hit/miss, offset reuse)
#   - Test: get_dedup_stats (size savings, hit rate)
#   - Test: reset (clear state)
#   - Test: performance overhead (<10% serialization time)
#   - Test: size savings (30-50% for text-heavy data)
#   - Test: min_length threshold (strings < 8 bytes not deduplicated)
#   - Test: min_occurrences threshold (strings occurring <2× not deduplicated)
#
# Benchmark tests required:
#   - pytest-benchmark for performance validation
#   - Measure overhead (<10% vs no deduplication)
#   - Measure size savings (30-50% for SessionState with 100 entities)
#   - Compare with no deduplication (baseline)
#
# No simulation code allowed:
#   - Use real FlatBuffers builders (flatbuffers.Builder)
#   - Test with actual schemas (SessionState, TaskAnnouncement)
#   - Integration tests > unit tests
#
# =============================================================================

# =============================================================================
# PERFORMANCE OPTIMIZATION NOTES
# =============================================================================
#
# Current implementation uses SHA256 for string hashing (STUB).
#
# Production optimization:
#   - Replace SHA256 with xxhash (10-100× faster)
#   - Use C extension for hash computation
#   - Consider inline caching for hot strings
#
# Expected performance:
#   - Overhead: <10% serialization time (hash table operations)
#   - Size savings: 30-50% for text-heavy data (typical SessionState)
#   - Deserialization speedup: Fewer allocations (strings stored once)
#
# Trade-offs:
#   - Memory overhead: Hash table (O(unique_strings))
#   - CPU overhead: 2-pass serialization (frequency map + serialize)
#   - Network savings: Reduced payload size (30-50%)
#
# =============================================================================
