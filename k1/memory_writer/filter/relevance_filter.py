"""
RelevanceFilter -- Stage 1 of the Memory Writer pipeline.

Evaluates rules R1-R6 against incoming turns. MW-07: zero LLM dependencies.
Constructor dependencies: MWConfig only (no ports).
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from k1.memory_writer.config import MWConfig
from k1.memory_writer.invariants import assert_mw07_filter_no_llm
from k1.memory_writer.types import FilterDecision

from .rules import (
    DedupRingBuffer,
    check_r1_clarification,
    check_r2_system_meta,
    check_r3_duplicate,
    check_r4_empty,
    check_r5_continuation,
    check_r6_tool_call_boost,
)


class RelevanceFilter:
    """Evaluates all rules against incoming turns. MW-07: zero LLM dependencies.

    Rule evaluation order (cheapest-first):
      R4 EMPTY → R5 TRIVIAL → R6 TOOL_BOOST → R1 CLARIFY → R2 SYSTEM → R3 DEDUP
    """

    __slots__ = ("_config", "_dedup_ring")

    def __init__(self, config: MWConfig) -> None:
        assert_mw07_filter_no_llm({"config": config})
        self._config = config
        self._dedup_ring = DedupRingBuffer(capacity=100)

    def evaluate(
        self,
        user_message: str,
        assistant_response: str,
        entities: List[str],
        topics: List[str],
        turn_id: str,
        timestamp_ms: int,
        turn_metadata: Optional[Dict[str, Any]] = None,
    ) -> FilterDecision:
        """Evaluate all rules against a turn. Returns FilterDecision."""
        start = time.perf_counter_ns()
        meta = turn_metadata or {}

        # R6: tool call boost — auto-PASS if tool_calls present
        if check_r6_tool_call_boost(meta):
            elapsed = (time.perf_counter_ns() - start) / 1_000_000
            return FilterDecision(passed=True, turn_id=turn_id, latency_ms=elapsed)

        # R4: empty/trivial
        reason = check_r4_empty(user_message, entities, self._config.filter_trivial_word_threshold)
        if reason:
            elapsed = (time.perf_counter_ns() - start) / 1_000_000
            return FilterDecision(
                passed=False, skip_reason=reason, turn_id=turn_id, latency_ms=elapsed
            )

        # R5: continuation
        reason = check_r5_continuation(user_message, entities)
        if reason:
            elapsed = (time.perf_counter_ns() - start) / 1_000_000
            return FilterDecision(
                passed=False, skip_reason=reason, turn_id=turn_id, latency_ms=elapsed
            )

        # R1: clarification
        reason = check_r1_clarification(user_message, assistant_response, entities)
        if reason:
            elapsed = (time.perf_counter_ns() - start) / 1_000_000
            return FilterDecision(
                passed=False, skip_reason=reason, turn_id=turn_id, latency_ms=elapsed
            )

        # R2: system/meta
        reason = check_r2_system_meta(user_message, entities)
        if reason:
            elapsed = (time.perf_counter_ns() - start) / 1_000_000
            return FilterDecision(
                passed=False, skip_reason=reason, turn_id=turn_id, latency_ms=elapsed
            )

        # R3: duplicate (most expensive — hash computation)
        reason = check_r3_duplicate(
            participants=entities,
            topics=topics,
            now_ms=timestamp_ms,
            ring=self._dedup_ring,
            window_ms=self._config.filter_dedup_window_seconds * 1000,
        )
        if reason:
            elapsed = (time.perf_counter_ns() - start) / 1_000_000
            return FilterDecision(
                passed=False, skip_reason=reason, turn_id=turn_id, latency_ms=elapsed
            )

        # All rules passed
        elapsed = (time.perf_counter_ns() - start) / 1_000_000
        return FilterDecision(passed=True, turn_id=turn_id, latency_ms=elapsed)

    def reset(self) -> None:
        """Clear session-scoped state (dedup ring). Called on session end."""
        self._dedup_ring.clear()
