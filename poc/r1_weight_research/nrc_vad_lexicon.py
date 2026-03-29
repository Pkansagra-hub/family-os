"""NRC-VAD lexicon mappings for the 44 FamilyOS emotion labels.

Values are on [0, 1] scale (NRC standard):
  - valence: 0 = most negative, 1 = most positive
  - arousal: 0 = calm/passive, 1 = excited/active
  - dominance: 0 = submissive/weak, 1 = dominant/in-control

Standard emotion values sourced from the NRC Valence-Arousal-Dominance Lexicon
(Mohammad, 2018). FamilyOS-specific labels (parental_pride, togetherness, etc.)
are estimated from closest semantic matches or compound averages.

For R1 formula usage:
  - affect_valence [-1, 1] = 2 * nrc_valence - 1
  - affect_arousal [0, 1]  = nrc_arousal  (no conversion)
  - affect_dominance [0, 1] = nrc_dominance (no conversion)
"""

from __future__ import annotations

from typing import Dict, NamedTuple


class VADTriple(NamedTuple):
    """Valence-Arousal-Dominance triple on [0, 1] NRC scale."""

    valence: float
    arousal: float
    dominance: float


# --- 44 FamilyOS emotion labels ---
# Sorted alphabetically for maintainability.

NRC_VAD: Dict[str, VADTriple] = {
    # ---- Standard psychological emotions (NRC-VAD direct) ----
    "admiration": VADTriple(0.85, 0.50, 0.45),
    "amusement": VADTriple(0.88, 0.62, 0.60),
    "anger": VADTriple(0.17, 0.83, 0.74),
    "annoyance": VADTriple(0.20, 0.58, 0.45),
    "approval": VADTriple(0.80, 0.35, 0.65),
    "caring": VADTriple(0.85, 0.35, 0.55),
    "contentment": VADTriple(0.88, 0.18, 0.60),
    "disappointment": VADTriple(0.22, 0.42, 0.28),
    "disapproval": VADTriple(0.22, 0.48, 0.55),
    "disgust": VADTriple(0.08, 0.64, 0.52),
    "embarrassment": VADTriple(0.18, 0.60, 0.15),
    "emptiness": VADTriple(0.12, 0.20, 0.15),
    "excitement": VADTriple(0.90, 0.85, 0.65),
    "fear": VADTriple(0.07, 0.85, 0.18),
    "frustration": VADTriple(0.18, 0.72, 0.30),
    "gratitude": VADTriple(0.90, 0.40, 0.55),
    "grief": VADTriple(0.10, 0.55, 0.15),
    "hope": VADTriple(0.86, 0.50, 0.56),
    "joy": VADTriple(0.98, 0.66, 0.72),
    "longing": VADTriple(0.45, 0.50, 0.25),
    "love": VADTriple(0.96, 0.54, 0.57),
    "nervousness": VADTriple(0.20, 0.75, 0.18),
    "neutral": VADTriple(0.50, 0.10, 0.50),
    "nostalgia": VADTriple(0.65, 0.40, 0.35),
    "optimism": VADTriple(0.85, 0.55, 0.60),
    "pride": VADTriple(0.89, 0.58, 0.78),
    "relief": VADTriple(0.83, 0.28, 0.56),
    "remorse": VADTriple(0.20, 0.45, 0.22),
    "sadness": VADTriple(0.19, 0.35, 0.22),
    "surprise": VADTriple(0.54, 0.77, 0.40),
    "warmth": VADTriple(0.87, 0.35, 0.55),
    "worry": VADTriple(0.15, 0.70, 0.20),
    # ---- FamilyOS-specific labels (estimated from semantic components) ----
    "belonging": VADTriple(0.88, 0.32, 0.55),  # contentment + social bond
    "bittersweet": VADTriple(0.50, 0.45, 0.35),  # joy-sadness midpoint
    "celebration": VADTriple(0.95, 0.80, 0.70),  # joy + excitement
    "homesickness": VADTriple(0.25, 0.50, 0.20),  # longing + sadness
    "overwhelmed": VADTriple(0.25, 0.80, 0.12),  # high arousal, very low dominance
    "parental_guilt": VADTriple(0.15, 0.55, 0.20),  # guilt + parental concern
    "parental_pride": VADTriple(0.92, 0.60, 0.75),  # pride + parental bond
    "patience": VADTriple(0.70, 0.15, 0.62),  # calm, moderate positive
    "playfulness": VADTriple(0.88, 0.70, 0.62),  # amusement + energy
    "protectiveness": VADTriple(0.70, 0.55, 0.75),  # caring + high dominance
    "tenderness": VADTriple(0.88, 0.25, 0.45),  # warmth + gentleness
    "togetherness": VADTriple(0.90, 0.40, 0.55),  # warmth + belonging
}

# Verify completeness at import time
assert len(NRC_VAD) == 44, f"Expected 44 emotion labels, got {len(NRC_VAD)}"


def emotions_to_vad(emotion_labels: list[str]) -> VADTriple:
    """Average NRC-VAD across a list of emotion labels.

    Returns VADTriple(0.50, 0.10, 0.50) (neutral) if no labels match.
    """
    if not emotion_labels:
        return NRC_VAD["neutral"]

    val_sum = aro_sum = dom_sum = 0.0
    matched = 0
    for label in emotion_labels:
        vad = NRC_VAD.get(label)
        if vad is not None:
            val_sum += vad.valence
            aro_sum += vad.arousal
            dom_sum += vad.dominance
            matched += 1

    if matched == 0:
        return NRC_VAD["neutral"]

    return VADTriple(
        valence=val_sum / matched,
        arousal=aro_sum / matched,
        dominance=dom_sum / matched,
    )
