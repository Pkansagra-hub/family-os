"""
poc.k1_poc.experience.affective_mirror -- AffectiveMirror.

Computes fulfillment-based tone adjustment from emotional trajectory
and persona baseline.

V2 Design Ref: Section 12.3.2
Whiteboard: docs/whiteboard/whiteboard_experience_layer.md

Fire cadence: immediately after EmotionalProcessor completes (chained).
Budget: 1 ms (arithmetic on EP output + persona config).
Reads: EmotionalTrajectory (from EP), persona config (SS).
Writes: ToneAdjustment emitted on bus, consumed by DynamicPromptBuilder.

Fulfillment philosophy (NOT mirroring):
  - Sad/frustrated user: warm + action-oriented. Help, don't narrate feelings.
  - Excited/happy user: amplify, celebrate, energy matching IS correct here.
  - Crisis/panic user: calm, competent, structured. Ground them.
  - Neutral user: efficient, friendly, persona baseline as-is.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ToneAdjustment:
    """Output of AffectiveMirror. Consumed by DynamicPromptBuilder identity section."""

    warmth: float = 0.5  # 0.0 (clinical) to 1.0 (warm)
    formality: float = 0.5  # 0.0 (casual) to 1.0 (formal)
    pace: str = "normal"  # "slow" | "normal" | "fast"
    mirror_intensity: float = 0.0  # 0.0 = no mirroring, 1.0 = full match


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


class AffectiveMirror:
    """Computes fulfillment-based tone adjustment.

    EP computes *what the user feels* (trajectory).
    AM computes *how the system should respond* (fulfillment strategy).
    Persona baseline modulates: high-formality persona stays professional
    even during positive energy; high-warmth persona runs warmer even
    during neutral band.

    Fire cadence: immediately after EmotionalProcessor completes.
    Budget: 1 ms.
    """

    async def mirror(
        self,
        emotional_state: dict,
        persona: dict,
    ) -> ToneAdjustment:
        """Compute fulfillment-based ToneAdjustment.

        Args:
            emotional_state: EmotionalTrajectory.__dict__ with keys:
                valence (-1.0 to +1.0), arousal (0.0 to 1.0),
                dominance (0.0 to 1.0), trend, confidence.
            persona: PersonaSection.to_dict() with personality sub-dict
                containing warmth, formality baselines.

        Returns:
            ToneAdjustment with fulfillment-modulated values.
        """
        if not emotional_state:
            return ToneAdjustment()

        valence = float(emotional_state.get("valence", 0.0))
        arousal = float(emotional_state.get("arousal", 0.5))
        confidence = float(emotional_state.get("confidence", 0.0))

        # If EP has no confidence, return persona baseline
        if confidence <= 0.0:
            return ToneAdjustment()

        # Extract persona baseline (default 0.5 for both)
        personality = persona.get("personality", {}) if persona else {}
        base_warmth = float(personality.get("warmth", 0.5))
        base_formality = float(personality.get("formality", 0.5))

        warmth = base_warmth
        formality = base_formality
        pace = "normal"
        mirror_intensity = 0.0

        # --- Crisis: high arousal + very negative valence ---
        # Calm, competent, structured. Ground them.
        if arousal > 0.7 and valence < -0.5:
            warmth = _clamp(base_warmth + 0.1)
            formality = _clamp(base_formality + 0.1)  # structured = grounding
            pace = "slow"
            mirror_intensity = 0.0  # absolutely do not mirror panic

        # --- Sad / frustrated: negative valence ---
        # Warm + action-oriented. Help them, don't narrate feelings.
        elif valence < -0.3:
            warmth = _clamp(base_warmth + 0.15)
            formality = _clamp(base_formality - 0.1)  # slightly more casual
            pace = "slow"
            mirror_intensity = 0.0  # do NOT mirror negativity

        # --- Excited / happy: positive valence ---
        # Amplify, celebrate. Energy matching IS appropriate here.
        elif valence > 0.5:
            warmth = _clamp(base_warmth + 0.1)
            formality = _clamp(base_formality - 0.05)
            pace = "fast"
            mirror_intensity = 0.7  # energy matching is correct

        # --- Mildly positive ---
        elif valence > 0.2:
            warmth = _clamp(base_warmth + 0.05)
            pace = "normal"
            mirror_intensity = 0.3

        # --- Neutral: use persona baseline ---
        # Efficient, friendly, don't overthink it.
        else:
            pass  # warmth/formality stay at persona baseline

        return ToneAdjustment(
            warmth=round(warmth, 3),
            formality=round(formality, 3),
            pace=pace,
            mirror_intensity=round(mirror_intensity, 3),
        )
