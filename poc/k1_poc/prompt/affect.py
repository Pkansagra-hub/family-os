"""
poc.k1_poc.prompt.affect -- Affect band computation for prompt modulation.

Computes an AffectBand from the affective_now SS section to modulate
prompt parameters (iteration budget, tone, history window, etc.).

V2 Section 16.3 Affect Modulation. Five affect bands:
    crisis   -- valence < -0.5 AND arousal > 0.7  (panic, anger, distress)
    low      -- valence < -0.3 AND arousal < 0.4  (sad, tired, defeated)
    positive -- valence > 0.5  AND arousal > 0.6  (excited, happy)
    elevated -- |valence| > 0.3                    (noticeable but not extreme)
    neutral  -- default                            (calm, efficient)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AffectBand:
    """Computed affect band from affective_now at prompt assembly time.

    Attributes:
        band: One of "crisis", "elevated", "neutral", "positive", "low".
    """

    band: Literal["crisis", "elevated", "neutral", "positive", "low"]


# =========================================================================
# Affect tone blocks -- injected into assembled prompt by the builder
# =========================================================================

AFFECT_TONE_BLOCKS: dict[str, str] = {
    "crisis": (
        "== TONE: CRISIS MODE ==\n"
        "User is in distress. Respond with:\n"
        "- Calm, structured language. No fluff.\n"
        "- Lead with ACTION, not empathy monologue. "
        "One sentence of acknowledgment, then options.\n"
        "- Numbered options (max 3). Let user pick.\n"
        "- Shorter response. Every word must earn its place.\n"
        '- Do NOT say "I understand how you feel" -- act, don\'t narrate.'
    ),
    "low": (
        "== TONE: LOW ENERGY ==\n"
        "User seems tired, sad, or deflated. Respond with:\n"
        "- Gentle, brief language. Don't force cheerfulness.\n"
        "- Offer practical help without pressure.\n"
        "- Shorter sentences. Less cognitive load.\n"
        '- "No rush" energy. Don\'t overwhelm with options.'
    ),
    "neutral": "",  # No modifier needed
    "positive": (
        "== TONE: POSITIVE ENERGY ==\n"
        "User is excited or happy. Match their energy:\n"
        "- Enthusiastic language. Celebrate wins together.\n"
        "- Can be slightly longer and more expressive.\n"
        '- Share their excitement: "That\'s awesome!" not "Acknowledged."'
    ),
    "elevated": (
        "== TONE: ELEVATED EMOTION ==\n"
        "User has noticeable emotion (not crisis, not positive). Respond with:\n"
        "- Acknowledge the feeling in ONE sentence before proceeding.\n"
        "- Then move to action or information.\n"
        "- Match register: if frustrated, be direct. If anxious, be reassuring."
    ),
}


def compute_affect_band(affect: dict[str, Any] | None = None) -> AffectBand:
    """Compute affect band from affective_now dict.

    Args:
        affect: Dict with "valence" (float, -1..1) and "arousal" (float, 0..1).
            If None, returns neutral band.

    Returns:
        AffectBand with the resolved band string.
    """
    if affect is None:
        return AffectBand(band="neutral")

    valence: float = affect.get("valence", 0.0)
    arousal: float = affect.get("arousal", 0.5)

    if valence < -0.5 and arousal > 0.7:
        band = AffectBand(band="crisis")
    elif valence < -0.3 and arousal < 0.4:
        band = AffectBand(band="low")
    elif valence > 0.5 and arousal > 0.6:
        band = AffectBand(band="positive")
    elif abs(valence) > 0.3:
        band = AffectBand(band="elevated")
    else:
        band = AffectBand(band="neutral")

    logger.info(
        "compute_affect_band  valence=%.2f arousal=%.2f -> %s",
        valence,
        arousal,
        band.band,
    )
    return band


# =========================================================================
# AffectModifiers -- per-band overrides applied to mode defaults
# =========================================================================
# V2 Design Doc Section 6.1 -- Affect Modifier Matrix


@dataclass(frozen=True)
class AffectModifiers:
    """Affect-band-specific overrides applied on top of mode defaults.

    Applied by DynamicPromptBuilder after mode selection. These modify
    the assembled prompt and iteration budget:

    Attributes:
        max_iterations_delta: Added to the mode's max_iterations.
        examples_count_override: Overrides mode's default examples count.
            None means use the mode default.
        history_window_delta: Added to the mode's history_window.
        tone_prefix: Injected near the top of the assembled prompt
            (from AFFECT_TONE_BLOCKS).
        response_length_hint: Advisory hint injected into prompt text.
        skip_refine_affect: If True, remove refine_affect from tool
            allowlist (already in crisis/low, don't re-assess).
    """

    max_iterations_delta: int = 0
    examples_count_override: int | None = None
    history_window_delta: int = 0
    tone_prefix: str = ""
    response_length_hint: str = ""
    skip_refine_affect: bool = False


# Pre-computed modifier sets per band (V2 Design Doc Section 6.1 table)
AFFECT_MODIFIERS: dict[str, AffectModifiers] = {
    "crisis": AffectModifiers(
        max_iterations_delta=-1,
        examples_count_override=1,
        history_window_delta=-5,
        tone_prefix=AFFECT_TONE_BLOCKS["crisis"],
        response_length_hint="Short, numbered options",
        skip_refine_affect=True,
    ),
    "low": AffectModifiers(
        max_iterations_delta=0,
        examples_count_override=1,
        history_window_delta=0,
        tone_prefix=AFFECT_TONE_BLOCKS["low"],
        response_length_hint="Brief, practical",
        skip_refine_affect=True,
    ),
    "neutral": AffectModifiers(
        tone_prefix=AFFECT_TONE_BLOCKS["neutral"],
    ),
    "positive": AffectModifiers(
        max_iterations_delta=0,
        tone_prefix=AFFECT_TONE_BLOCKS["positive"],
        response_length_hint="Enthusiastic, can be longer",
    ),
    "elevated": AffectModifiers(
        max_iterations_delta=0,
        tone_prefix=AFFECT_TONE_BLOCKS["elevated"],
        response_length_hint="Empathetic, then action",
    ),
}


def compute_affect_modifiers(band: AffectBand) -> AffectModifiers:
    """Return pre-computed affect modifiers for the given band.

    Called by DynamicPromptBuilder.build() after compute_affect_band().

    Args:
        band: Computed AffectBand from compute_affect_band().

    Returns:
        AffectModifiers for the band. Falls back to neutral if unknown.
    """
    return AFFECT_MODIFIERS.get(band.band, AFFECT_MODIFIERS["neutral"])


# =========================================================================
# Affect x Mode Interaction Table
# =========================================================================
# V2 Design Doc Section 6.1 -- some (mode, band) pairs inject additional
# prompt blocks beyond the general AffectModifiers.

AFFECT_MODE_INTERACTIONS: dict[tuple[str, str], str] = {
    ("CLARIFY_ASK", "crisis"): (
        "== CRISIS + CLARIFICATION ==\n"
        "Ask a YES/NO question instead of open-ended.\n"
        "Reduce cognitive load: binary choice only.\n"
        "Example: 'Should I go with June 15?' not 'When are you thinking?'"
    ),
    ("CLARIFY_ASK", "low"): (
        "== LOW + CLARIFICATION ==\n"
        "Frame gently: 'Just checking one quick thing...'\n"
        "Keep it to a single, simple question."
    ),
    ("HITL_RELAY", "crisis"): (
        "== CRISIS + HITL RELAY ==\n"
        "Lead with reassurance: 'Don't worry, I can cancel after if needed.'\n"
        "State consequences but emphasize reversibility where possible.\n"
        "Keep options to 2 maximum."
    ),
    ("HITL_RELAY", "low"): (
        "== LOW + HITL RELAY ==\n"
        "Shorter option list. Skip non-essential details.\n"
        "Frame as: 'Just need a quick yes or no.'"
    ),
    ("HITL_RELAY", "positive"): (
        "== POSITIVE + HITL RELAY ==\n"
        "'Great news! Everything's ready to go!'\n"
        "Match excitement. Make approval feel like a celebration."
    ),
    ("PRESENT", "crisis"): (
        "== CRISIS + PRESENT ==\n"
        "'Crisis averted! Here's what came through.'\n"
        "Lead with the resolved situation. Relief framing."
    ),
    ("PRESENT", "low"): (
        "== LOW + PRESENT ==\n"
        "Present gently, no fanfare. Just the facts.\n"
        "Skip celebration language."
    ),
    ("PRESENT", "positive"): (
        "== POSITIVE + PRESENT ==\n"
        "Full celebration mode. Match user's excitement.\n"
        "'Amazing news!' / 'You're going to love this!'"
    ),
    ("WEAVE", "crisis"): (
        "== CRISIS + WEAVE ==\n"
        "Address the user's current topic briefly first (one sentence).\n"
        "Then present the async result directly -- no 'by the way' bridges.\n"
        "Skip conversational fluff, keep both parts short and factual."
    ),
    ("WEAVE", "low"): (
        "== LOW + WEAVE ==\n" "Direct, no transition fluff.\n" "Keep it short and factual."
    ),
    ("WEAVE", "positive"): (
        "== POSITIVE + WEAVE ==\n"
        "Excited bridging: 'Oh! Also -- great news!'\n"
        "Match the energy with the async result."
    ),
    ("ERROR", "crisis"): (
        "== CRISIS + ERROR ==\n"
        "Structured recovery: 3 numbered options. No narrative.\n"
        "1. Try again  2. Different approach  3. Cancel\n"
        "Let user pick. Do NOT explain what went wrong in detail."
    ),
    ("ERROR", "low"): (
        "== LOW + ERROR ==\n"
        "Extra gentle. 'No worries, happens to everyone.'\n"
        "Offer to handle it differently without pressure."
    ),
    ("ERROR", "positive"): (
        "== POSITIVE + ERROR ==\n"
        "Temper excitement, stay factual.\n"
        "'Small hiccup -- let me try another way.'"
    ),
}


def get_affect_mode_interaction(mode_name: str, band: str) -> str:
    """Return additional prompt block for specific (mode, band) pairs.

    Some mode + affect combinations require specialized prompt blocks
    beyond the general AFFECT_TONE_BLOCKS modifier. This function returns
    the extra block for known (mode, band) pairs, or empty string for
    combinations with no special interaction.

    Args:
        mode_name: PromptMode name in UPPER_CASE (e.g. "CLARIFY_ASK").
        band: AffectBand.band value (e.g. "crisis").

    Returns:
        Additional prompt block string or "" if no special interaction.
    """
    return AFFECT_MODE_INTERACTIONS.get((mode_name, band), "")
