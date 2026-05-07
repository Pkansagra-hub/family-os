"""k1.memory_writer.filter -- Relevance filter package (Stage 1)."""

from k1.memory_writer.filter.relevance_filter import RelevanceFilter
from k1.memory_writer.filter.rules import (
    CONTINUATION_PHRASES,
    TRIVIAL_PATTERNS,
    DedupRingBuffer,
    check_r1_clarification,
    check_r2_system_meta,
    check_r3_duplicate,
    check_r4_empty,
    check_r5_continuation,
    check_r6_tool_call_boost,
)

__all__ = [
    "RelevanceFilter",
    "DedupRingBuffer",
    "TRIVIAL_PATTERNS",
    "CONTINUATION_PHRASES",
    "check_r1_clarification",
    "check_r2_system_meta",
    "check_r3_duplicate",
    "check_r4_empty",
    "check_r5_continuation",
    "check_r6_tool_call_boost",
]
