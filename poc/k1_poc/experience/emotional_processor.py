"""
poc.k1_poc.experience.emotional_processor -- EmotionalProcessor.

Computes emotional trajectory from UltraBERT affect history.

V2 Design Ref: Section 12.3.1
Whiteboard: docs/whiteboard/whiteboard_experience_layer.md

Fire cadence: every 25th turn_end (enforced by ExperienceLayer.tick()).
Budget: 1 ms (pure math on existing SS data).
Reads: turn transcript, affect history (from SS affective_now snapshots).
Writes: affective_now SS section (EmotionalTrajectory).

EP skip rule (Section 5): if Front's refine_affect() was called
this turn with confidence > 0.8, tick() skips this component's
write to avoid overwriting a high-confidence Front correction.

Algorithm:
  - Weighted moving average over affect_history snapshots.
  - Recent turns weighted exponentially heavier (decay factor 0.7).
  - Trend = sign of valence slope over window (rising/falling/stable).
  - Confidence = inverse of valence variance (stable = high confidence).
  - Dominance inferred from turn_transcript patterns (commands vs questions).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class EmotionalTrajectory:
    """Output of EmotionalProcessor. Written to affective_now SS section."""

    valence: float = 0.0  # -1.0 (negative) to +1.0 (positive)
    arousal: float = 0.5  # 0.0 (calm) to 1.0 (excited)
    dominance: float = 0.5  # 0.0 (submissive) to 1.0 (dominant)
    trend: str = "stable"  # "rising" | "falling" | "stable"
    confidence: float = 0.0  # 0.0 = no data, 1.0 = high certainty


# Threshold for trend detection: absolute valence slope must exceed this
# to classify as "rising" or "falling". Prevents noise from triggering trends.
_TREND_THRESHOLD = 0.08

# Exponential decay factor for weighting recent turns.
# 0.7 means each older turn is weighted 70% of the next newer one.
_DECAY_FACTOR = 0.7


def _weighted_average(values: list[float], decay: float) -> float:
    """Compute exponentially weighted average (newest = highest weight)."""
    if not values:
        return 0.0
    n = len(values)
    total = 0.0
    weight_sum = 0.0
    for i, v in enumerate(values):
        w = decay ** (n - 1 - i)  # newest gets weight 1.0
        total += v * w
        weight_sum += w
    return total / weight_sum if weight_sum > 0 else 0.0


def _valence_slope(values: list[float]) -> float:
    """Compute simple linear slope of valence over the window.

    Uses least-squares regression: slope = sum((x-xm)(y-ym)) / sum((x-xm)^2)
    where x is the index (0..n-1) and y is the valence value.
    """
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    numerator = 0.0
    denominator = 0.0
    for i, v in enumerate(values):
        dx = i - x_mean
        numerator += dx * (v - y_mean)
        denominator += dx * dx
    return numerator / denominator if denominator > 0 else 0.0


def _variance(values: list[float]) -> float:
    """Compute variance of values."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / len(values)


def _infer_dominance(transcript: str) -> float:
    """Infer dominance from turn transcript patterns.

    Commands and directives suggest high dominance.
    Questions and hedging suggest low dominance.
    Returns 0.0 to 1.0. Default 0.5 for ambiguous input.
    """
    if not transcript:
        return 0.5
    text = transcript.strip().lower()
    # Command patterns: imperative verbs, short direct statements
    command_signals = 0
    question_signals = 0
    if text.endswith("?"):
        question_signals += 1
    if text.endswith("!"):
        command_signals += 1
    # Imperative starters
    _imperatives = (
        "do ",
        "make ",
        "set ",
        "get ",
        "find ",
        "show ",
        "tell ",
        "send ",
        "order ",
        "book ",
        "buy ",
        "call ",
        "stop ",
        "start ",
        "turn ",
        "open ",
        "close ",
        "add ",
        "remove ",
        "delete ",
        "cancel ",
        "schedule ",
        "remind ",
    )
    for imp in _imperatives:
        if text.startswith(imp):
            command_signals += 1
            break
    # Hedging / uncertainty
    _hedges = ("maybe", "i think", "not sure", "could you", "would you", "please")
    for h in _hedges:
        if h in text:
            question_signals += 1
            break
    if command_signals > question_signals:
        return min(0.75, 0.5 + command_signals * 0.15)
    if question_signals > command_signals:
        return max(0.25, 0.5 - question_signals * 0.15)
    return 0.5


class EmotionalProcessor:
    """Computes emotional trajectory from UltraBERT affect history.

    Fire cadence: every 25th turn_end.
    Budget: 1 ms (pure math on existing SS data).
    Reads: turn transcript, affect history (from SS affective_now).
    Writes: affective_now SS section (EmotionalTrajectory).

    EP does NOT re-classify the user's message. UltraBERT already did
    that. EP reads UltraBERT's output from affective_now and computes
    the cross-turn trajectory over time.

    Algorithm:
      1. Extract valence and arousal sequences from affect_history.
      2. Compute exponentially weighted averages (recent turns heavier).
      3. Compute valence slope to determine trend direction.
      4. Compute confidence from inverse of valence variance.
      5. Infer dominance from turn_transcript patterns.
    """

    async def process(
        self,
        turn_transcript: str,
        affect_history: list[dict],
    ) -> EmotionalTrajectory:
        """Compute emotional trajectory from affect history snapshots.

        Args:
            turn_transcript: Current turn's user text (for dominance inference).
            affect_history: List of dicts with keys: emotion, valence, arousal,
                intensity, turn_number, timestamp_ms. From affective_now.recent_emotions.

        Returns:
            EmotionalTrajectory with smoothed values and trend.
        """
        if not affect_history:
            return EmotionalTrajectory()

        # Extract valence and arousal sequences
        valences: list[float] = []
        arousals: list[float] = []
        for snap in affect_history:
            v = snap.get("valence")
            a = snap.get("arousal")
            if v is not None:
                valences.append(float(v))
            if a is not None:
                arousals.append(float(a))

        if not valences:
            return EmotionalTrajectory()

        # Weighted moving averages (recent turns heavier)
        smoothed_valence = _weighted_average(valences, _DECAY_FACTOR)
        smoothed_arousal = _weighted_average(arousals, _DECAY_FACTOR) if arousals else 0.5

        # Clamp to valid ranges
        smoothed_valence = max(-1.0, min(1.0, smoothed_valence))
        smoothed_arousal = max(0.0, min(1.0, smoothed_arousal))

        # Trend from valence slope
        slope = _valence_slope(valences)
        if slope > _TREND_THRESHOLD:
            trend = "rising"
        elif slope < -_TREND_THRESHOLD:
            trend = "falling"
        else:
            trend = "stable"

        # Confidence from inverse of variance
        # Low variance = high confidence (stable signal)
        # variance of 0 -> confidence 1.0
        # variance of 1 -> confidence ~0.27
        var = _variance(valences)
        confidence = math.exp(-2.0 * var)
        # Scale by sample count: fewer samples = lower confidence
        sample_factor = min(1.0, len(valences) / 5.0)
        confidence *= sample_factor
        confidence = max(0.0, min(1.0, confidence))

        # Dominance from turn transcript patterns
        dominance = _infer_dominance(turn_transcript)

        return EmotionalTrajectory(
            valence=round(smoothed_valence, 3),
            arousal=round(smoothed_arousal, 3),
            dominance=round(dominance, 3),
            trend=trend,
            confidence=round(confidence, 3),
        )
