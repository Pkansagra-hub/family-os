"""
k1.fabric.policy.affective_routing -- AffectiveRouting soft score (3.2.2).

Reads ``affective_now`` from SessionState to adjust provider selection
based on the user's emotional state.  This is a **soft score** -- it
never rejects, only adjusts the composite policy score.

Rules (from fabric_discussion.md Section 10 Dimension 2):
  - High sadness/anxiety (intensity > 0.7):
      Score boost: +0.1 for empathetic-tagged / simpler providers.
  - High joy/excitement:
      Score boost: +0.05 for detail-rich providers.
  - Neutral/low intensity:
      No adjustment (score = 0.0).

Score range: 0.0 to 0.2.

Design:
  - ``ISessionStateReader`` is an Optional port.  When ``None``,
    the dimension returns neutral (0.0) -- graceful degradation.
  - Stateless.  All state comes from SessionState read.
  - Thread-safe (no mutable internal state).

References:
  - fabric_discussion.md Section 10 (Dimension 2: Affective Routing)
  - Epic 3.2.2 in fabric-implementation-plan.md

Exports:
  AffectiveRouting -- Soft-score affective evaluator
  AffectiveScore   -- Frozen result dataclass
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
class AffectiveScore:
    """
    Output of AffectiveRouting evaluation.

    Attributes:
        score: Additive soft score (0.0 to 0.2).
        reason: Human-readable explanation.
    """

    score: float = 0.0
    reason: str = "neutral"


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Emotions that trigger a gentler/simpler preference
_SAD_ANXIOUS_EMOTIONS = frozenset({"sadness", "anxiety", "fear", "grief", "distress"})

# Emotions that trigger a richer/more-detailed preference
_JOY_EXCITED_EMOTIONS = frozenset({"joy", "excitement", "happiness", "elation"})

# Intensity threshold above which affective routing kicks in
_HIGH_INTENSITY_THRESHOLD = 0.7

# Score boost values
_SAD_ANXIOUS_BOOST = 0.10
_JOY_EXCITED_BOOST = 0.05


# ---------------------------------------------------------------------------
# AffectiveRouting
# ---------------------------------------------------------------------------


class AffectiveRouting:
    """
    Soft-score policy dimension for emotion-aware provider selection (3.2.2).

    Reads ``affective_now`` section from SessionState and computes an
    additive score that adjusts provider ranking based on the user's
    current emotional state.

    Usage::

        ar = AffectiveRouting(state_reader=my_reader)
        score = ar.score(request)
        # score.score in [0.0 .. 0.2]
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

    def score(self, request: CapabilityRequest) -> AffectiveScore:
        """
        Compute affective routing score for the given request.

        Reads ``affective_now`` from SessionState via the injected
        reader.  If the reader is None or the section is unavailable,
        returns neutral (0.0).

        Expected ``affective_now`` schema::

            {
                "raw": "sadness",       # detected emotion label
                "intensity": 0.85       # 0.0 to 1.0
            }

        Args:
            request: The capability request (needs session_id for state read).

        Returns:
            AffectiveScore with score (0.0-0.2) and human-readable reason.
        """
        if self._state_reader is None:
            return AffectiveScore(score=0.0, reason="no_state_reader")

        section = self._state_reader.read_section(request.session_id, "affective_now")
        if section is None:
            return AffectiveScore(score=0.0, reason="affective_now_unavailable")

        raw_emotion = str(section.get("raw", "")).lower().strip()
        try:
            intensity = float(section.get("intensity", 0.0))
        except (TypeError, ValueError):
            intensity = 0.0

        # Only adjust when intensity exceeds the threshold
        if intensity <= _HIGH_INTENSITY_THRESHOLD:
            return AffectiveScore(
                score=0.0,
                reason=f"low_intensity: {raw_emotion} @ {intensity:.2f}",
            )

        # High sadness/anxiety -> prefer gentler/simpler providers
        if raw_emotion in _SAD_ANXIOUS_EMOTIONS:
            return AffectiveScore(
                score=_SAD_ANXIOUS_BOOST,
                reason=f"sad_anxious_boost: {raw_emotion} @ {intensity:.2f}",
            )

        # High joy/excitement -> prefer richer providers
        if raw_emotion in _JOY_EXCITED_EMOTIONS:
            return AffectiveScore(
                score=_JOY_EXCITED_BOOST,
                reason=f"joy_excited_boost: {raw_emotion} @ {intensity:.2f}",
            )

        # High intensity but emotion not in known buckets -> no adjustment
        return AffectiveScore(
            score=0.0,
            reason=f"unrecognized_emotion: {raw_emotion} @ {intensity:.2f}",
        )
