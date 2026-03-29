"""
k1.fabric.policy.cognitive_load_routing -- CognitiveLoadRouting soft score (3.2.3).

Reads cognitive state (complexity tier + cognitive load) from SessionState
and adjusts provider selection to match the user's current capacity.
This is a **soft score** -- it never rejects, only adjusts the composite
policy score.

Rules (from fabric_discussion.md Section 10 Dimension 3):
  - High cognitive load (user overwhelmed):
      Prefer faster/simpler providers.
      Score boost: +0.1 for fast, simple providers.
  - Low cognitive load (user is fresh):
      No penalty for complex providers.
      Score boost: +0.05 for comprehensive providers.

Score range: 0.0 to 0.15.

Design:
  - ``ISessionStateReader`` is an Optional port.  When ``None``,
    returns neutral (0.0) -- graceful degradation.
  - Stateless.  All state comes from SessionState read.
  - Thread-safe (no mutable internal state).

References:
  - fabric_discussion.md Section 10 (Dimension 3: Cognitive Load Routing)
  - Epic 3.2.3 in fabric-implementation-plan.md

Exports:
  CognitiveLoadRouting -- Soft-score cognitive load evaluator
  CognitiveScore       -- Frozen result dataclass
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from k1.fabric.policy.ports import ISessionStateReader
from k1.fabric.types import CapabilityRequest

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Score result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CognitiveScore:
    """
    Output of CognitiveLoadRouting evaluation.

    Attributes:
        score: Additive soft score (0.0 to 0.15).
        reason: Human-readable explanation.
    """

    score: float = 0.0
    reason: str = "neutral"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Cognitive load level thresholds
_HIGH_LOAD_THRESHOLD = 0.7
_LOW_LOAD_THRESHOLD = 0.3

# Score boost values
_HIGH_LOAD_BOOST = 0.10  # prefer faster/simpler when overwhelmed
_LOW_LOAD_BOOST = 0.05  # slight boost for comprehensive when fresh

# Complexity tier values
_TIER_HIGH = "HIGH"
_TIER_MEDIUM = "MEDIUM"
_TIER_LOW = "LOW"


# ---------------------------------------------------------------------------
# CognitiveLoadRouting
# ---------------------------------------------------------------------------


class CognitiveLoadRouting:
    """
    Soft-score policy dimension for cognitive-load-aware selection (3.2.3).

    Reads ``cognitive`` section from SessionState and computes an
    additive score that adjusts provider ranking based on the user's
    current cognitive capacity.

    Usage::

        clr = CognitiveLoadRouting(state_reader=my_reader)
        score = clr.score(request)
        # score.score in [0.0 .. 0.15]
    """

    __slots__ = ("_state_reader",)

    def __init__(
        self,
        *,
        state_reader: Optional[ISessionStateReader] = None,
    ) -> None:
        """
        Args:
            state_reader: Optional SessionState reader port.
                If None, all evaluations return neutral (0.0).
        """
        self._state_reader = state_reader

    # ======================================================================
    # Public API
    # ======================================================================

    def score(self, request: CapabilityRequest) -> CognitiveScore:
        """
        Compute cognitive load routing score for the given request.

        Reads ``cognitive`` section from SessionState via the injected
        reader.  If the reader is None or the section is unavailable,
        returns neutral (0.0).

        Expected ``cognitive`` schema::

            {
                "load": 0.8,            # 0.0 (fresh) to 1.0 (overwhelmed)
                "complexity_tier": "HIGH" # LOW, MEDIUM, HIGH
            }

        Both fields are used: ``load`` is the primary signal, while
        ``complexity_tier`` provides a discrete fallback when ``load``
        is not available.

        Args:
            request: The capability request (needs session_id for state read).

        Returns:
            CognitiveScore with score (0.0-0.15) and human-readable reason.
        """
        if self._state_reader is None:
            return CognitiveScore(score=0.0, reason="no_state_reader")

        section = self._state_reader.read_section(request.session_id, "cognitive")
        if section is None:
            return CognitiveScore(score=0.0, reason="cognitive_unavailable")

        # --- Primary signal: continuous load value ---
        raw_load = section.get("load")
        if raw_load is not None:
            try:
                load = float(raw_load)
            except (TypeError, ValueError):
                load = None
        else:
            load = None

        if load is not None:
            return self._score_from_load(load)

        # --- Fallback: discrete complexity tier ---
        tier = str(section.get("complexity_tier", "")).upper().strip()
        return self._score_from_tier(tier)

    # ======================================================================
    # Internal scoring helpers
    # ======================================================================

    @staticmethod
    def _score_from_load(load: float) -> CognitiveScore:
        """
        Score based on continuous cognitive load value.

        Args:
            load: 0.0 (fresh) to 1.0 (overwhelmed).
        """
        load = max(0.0, min(1.0, load))  # clamp

        if load >= _HIGH_LOAD_THRESHOLD:
            return CognitiveScore(
                score=_HIGH_LOAD_BOOST,
                reason=f"high_load_boost: load={load:.2f}",
            )
        if load <= _LOW_LOAD_THRESHOLD:
            return CognitiveScore(
                score=_LOW_LOAD_BOOST,
                reason=f"low_load_boost: load={load:.2f}",
            )
        # Medium load -> no adjustment
        return CognitiveScore(
            score=0.0,
            reason=f"medium_load: load={load:.2f}",
        )

    @staticmethod
    def _score_from_tier(tier: str) -> CognitiveScore:
        """
        Score based on discrete complexity tier.

        Args:
            tier: "LOW", "MEDIUM", or "HIGH".
        """
        if tier == _TIER_HIGH:
            return CognitiveScore(
                score=_HIGH_LOAD_BOOST,
                reason=f"high_tier_boost: tier={tier}",
            )
        if tier == _TIER_LOW:
            return CognitiveScore(
                score=_LOW_LOAD_BOOST,
                reason=f"low_tier_boost: tier={tier}",
            )
        # MEDIUM or unrecognized tier -> no adjustment
        return CognitiveScore(
            score=0.0,
            reason=f"neutral_tier: tier={tier or '(empty)'}",
        )
