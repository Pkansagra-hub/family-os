"""
Relevance filter rules -- R1 through R6.

Evaluated cheapest-first in RelevanceFilter.evaluate().
All rules are pure functions: no I/O, no LLM (MW-07).

Rule order (cheapest-first):
  R4 EMPTY       — O(1) word count + set lookup
  R5 TRIVIAL     — O(1) pattern match
  R6 TOOL_BOOST  — O(1) key check (auto-PASS, not a skip rule)
  R1 CLARIFY     — O(n) regex on user msg + assistant response
  R2 SYSTEM_META — O(n) regex on user msg
  R3 DUPLICATE   — O(1) SHA256 hash lookup in ring buffer
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional

from k1.memory_writer.types import SkipReason

# ---------------------------------------------------------------------------
# R4 constants
# ---------------------------------------------------------------------------

TRIVIAL_PATTERNS: frozenset = frozenset(
    {
        "ok",
        "sure",
        "thanks",
        "thank you",
        "got it",
        "yes",
        "no",
        "yeah",
        "alright",
        "cool",
        "nice",
        "fine",
        "good",
        "right",
        "okay",
        "yep",
        "nope",
        "uh huh",
        "mm",
        "hmm",
        "mhm",
    }
)

# ---------------------------------------------------------------------------
# R5 constants
# ---------------------------------------------------------------------------

CONTINUATION_PHRASES: frozenset = frozenset(
    {
        "go on",
        "continue",
        "what else",
        "tell me more",
        "and then",
        "anything else",
        "keep going",
        "next",
        "more",
        "what else?",
        "and?",
        "go ahead",
        "proceed",
    }
)

# ---------------------------------------------------------------------------
# R1 regex patterns
# ---------------------------------------------------------------------------

_CLARIFICATION_PATTERNS: tuple = (
    re.compile(r"\bwhat do you mean\b", re.I),
    re.compile(r"\bcan you (explain|repeat|clarify)\b", re.I),
    re.compile(r"\bi don'?t understand\b", re.I),
    re.compile(r"\bwhich one\b", re.I),
    re.compile(r"\bwhat'?s that\b", re.I),
    re.compile(r"\bhuh\?", re.I),
)

_REPAIR_MARKERS: tuple = (
    re.compile(r"\bI meant\b", re.I),
    re.compile(r"\bto clarify\b", re.I),
    re.compile(r"\bin other words\b", re.I),
    re.compile(r"\bwhat I (said|meant)\b", re.I),
)

# ---------------------------------------------------------------------------
# R2 regex patterns
# ---------------------------------------------------------------------------

_SYSTEM_META_PATTERNS: tuple = (
    re.compile(r"\b(change|set|use|switch)\s+(your\s+)?(tone|style|format)\b", re.I),
    re.compile(r"\bwhat (can you do|features|capabilities)\b", re.I),
    re.compile(r"\bstop (asking|using|doing)\b", re.I),
    re.compile(r"\bbe more (concise|brief|formal|casual)\b", re.I),
    re.compile(r"\b(how|what) (do|does) (you|this|the system)\b", re.I),
)


# ---------------------------------------------------------------------------
# Rule functions
# ---------------------------------------------------------------------------


def check_r4_empty(
    user_message: str,
    entities: List[str],
    threshold: int = 5,
) -> Optional[SkipReason]:
    """R4: Skip empty/trivial turns (<threshold words, no entities, trivial pattern)."""
    words = user_message.strip().split()
    if len(words) >= threshold:
        return None
    if entities:
        return None
    normalized = user_message.strip().lower().rstrip("!?.,")
    if normalized in TRIVIAL_PATTERNS:
        return SkipReason.EMPTY
    return None


def check_r5_continuation(
    user_message: str,
    entities: List[str],
    max_words: int = 10,
) -> Optional[SkipReason]:
    """R5: Skip pure continuation phrases ("go on", "what else")."""
    words = user_message.strip().split()
    if len(words) > max_words:
        return None
    if entities:
        return None
    normalized = user_message.strip().lower().rstrip("!?.,")
    if normalized in CONTINUATION_PHRASES:
        return SkipReason.TRIVIAL
    return None


def check_r6_tool_call_boost(turn_metadata: Dict[str, Any]) -> bool:
    """R6: Returns True if turn has tool_calls — auto-PASS (skip R4/R5)."""
    tool_calls = turn_metadata.get("tool_calls")
    return bool(tool_calls)


def check_r1_clarification(
    user_message: str,
    assistant_response: str,
    entities: List[str],
) -> Optional[SkipReason]:
    """R1: Skip clarification + repair turns."""
    if entities:
        return None
    user_is_clarification = any(p.search(user_message) for p in _CLARIFICATION_PATTERNS)
    assistant_has_repair = any(p.search(assistant_response) for p in _REPAIR_MARKERS)
    if user_is_clarification and assistant_has_repair:
        return SkipReason.CLARIFICATION
    return None


def check_r2_system_meta(
    user_message: str,
    entities: List[str],
) -> Optional[SkipReason]:
    """R2: Skip system/meta talk (not about life)."""
    if entities:
        return None
    if any(p.search(user_message) for p in _SYSTEM_META_PATTERNS):
        return SkipReason.SYSTEM_TURN
    return None


# ---------------------------------------------------------------------------
# R3: Dedup ring buffer + check
# ---------------------------------------------------------------------------


class DedupRingBuffer:
    """Bounded ring buffer for SHA256 hashes. Cleared on session end."""

    __slots__ = ("_buffer", "_capacity", "_index", "_lookup")

    def __init__(self, capacity: int = 100) -> None:
        self._buffer: List[tuple] = []
        self._capacity = capacity
        self._index = 0
        self._lookup: Dict[str, int] = {}

    def contains(self, hash_val: str, now_ms: int, window_ms: int) -> bool:
        ts = self._lookup.get(hash_val)
        if ts is None:
            return False
        return (now_ms - ts) < window_ms

    def add(self, hash_val: str, now_ms: int) -> None:
        if len(self._buffer) < self._capacity:
            self._buffer.append((hash_val, now_ms))
        else:
            old_hash, _ = self._buffer[self._index]
            self._lookup.pop(old_hash, None)
            self._buffer[self._index] = (hash_val, now_ms)
            self._index = (self._index + 1) % self._capacity
        self._lookup[hash_val] = now_ms

    def clear(self) -> None:
        self._buffer.clear()
        self._lookup.clear()
        self._index = 0


def check_r3_duplicate(
    participants: List[str],
    topics: List[str],
    now_ms: int,
    ring: DedupRingBuffer,
    window_ms: int = 300_000,
) -> Optional[SkipReason]:
    """R3: Skip duplicate entity+topic hash within dedup window."""
    key = ",".join(sorted(participants)) + "|" + ",".join(sorted(topics))
    hash_val = hashlib.sha256(key.encode()).hexdigest()
    if ring.contains(hash_val, now_ms, window_ms):
        return SkipReason.DUPLICATE
    ring.add(hash_val, now_ms)
    return None
