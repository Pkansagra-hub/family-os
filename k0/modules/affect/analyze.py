"""
M04: affect.analyze (Amygdala/Affect System)

Phase 2 Declarative Module - Emotional content and risk level analysis

Architecture:
- Two-tier latency strategy: Tier-0 (lexicon, <2ms) for 90% events, Tier-1 (ML, <60ms) for 10%
- VADER lexicon-based sentiment analysis (7,500 words)
- Valence/arousal mapping from compound scores
- Affect band classification (GREEN/AMBER/RED) for risk assessment
- Russell's circumplex model for emotion tag mapping

Performance:
- Tier-0: <2ms P99 (CPU-only, no GPU)
- Tier-1: <60ms P99 (ML inference - deferred to future implementation)
- Overall P95: ≤70ms
- 73% accuracy target for Tier-0 (sufficient for salience scoring)

Contract: k0/contracts/modules/affect.analyze.v1.yaml
ADR: docs/architecture/decisions-K0/modules/k004.1-tier0-fast-affect.md

Related Modules:
- M02 (semantic_project): Parallel module
- M06 (salience.score): Downstream consumer of affect data

Input: cognitive.memory.write.committed.v1 event
Output: p02.affect.analyzed.v1 event
Side Effects: None (pure computation)

Author: K0 Architecture Team
Date: 2025-11-17
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# ============================================================================
# Configuration (from affect.analyze.v1.yaml)
# ============================================================================

# Tier-0 complexity thresholds
MAX_WORD_COUNT_TIER0 = 50  # Words beyond this trigger Tier-1
MAX_TEXT_LENGTH = 10000  # Absolute character limit (prevent DoS)

# Affect band thresholds (from contract config_schema)
RED_BAND_VALENCE_THRESHOLD = 0.25  # Below this = RED
AMBER_BAND_VALENCE_THRESHOLD = 0.4  # Below this = AMBER
GREEN_BAND_VALENCE_THRESHOLD = 0.5  # Above this = GREEN

# Circumplex emotion mapping thresholds
HIGH_VALENCE_THRESHOLD = 0.6  # Positive emotions
LOW_VALENCE_THRESHOLD = 0.4  # Negative emotions
HIGH_AROUSAL_THRESHOLD = 0.6  # High intensity
LOW_AROUSAL_THRESHOLD = 0.4  # Low intensity

# Default fallback values (from contract)
DEFAULT_VALENCE = 0.5  # Neutral
DEFAULT_AROUSAL = 0.3  # Calm

# Confidence scoring parameters
MIN_CONFIDENCE_VALENCE_DISTANCE = 0.2  # Distance from neutral for high confidence

# ============================================================================
# Precompiled Patterns & Constants
# ============================================================================

# Complex negation pattern (double negatives)
COMPLEX_NEGATION_RE = re.compile(r"\b(not|no|never)\s+(un|in|im)\w+", re.IGNORECASE)

# Mixed emotion keywords (Tier-1 fallback triggers)
MIXED_EMOTION_KEYWORDS = (
    "bittersweet",
    "mixed feelings",
    "conflicted",
    "ambivalent",
    "complicated",
)

# Sarcasm indicators (Tier-1 fallback triggers)
SARCASM_INDICATORS = (
    "yeah right",
    "sure buddy",
    "oh great",
    "thanks a lot",
)

# High-risk safety keywords (force RED band regardless of VADER)
SAFETY_KEYWORDS = (
    "suicide",
    "kill myself",
    "self harm",
    "hurt myself",
    "end it all",
    "abuse",
    "hitting",
    "screaming at",
)

# FamilyOS domain-specific lexicon overrides (phrase → valence adjustment)
DOMAIN_LEXICON = {
    "quality time": 0.15,  # Boost positive
    "milestone": 0.15,
    "big day": 0.10,
    "meltdown": -0.20,  # Penalize negative
    "tantrum": -0.15,
    "exhausted": -0.10,
}

# Emoji valence overrides (emoji → valence score)
EMOJI_VALENCE = {
    "❤️": 0.9,
    "😊": 0.8,
    "😍": 0.9,
    "🎉": 0.8,
    "😭": 0.2,
    "😢": 0.3,
    "😡": 0.1,
    "😠": 0.2,
    "👍": 0.7,
    "👎": 0.3,
}

# ============================================================================
# VADER Lazy Loading
# ============================================================================

# VADER will be loaded lazily on first use (not at module import time)
_VADER_AVAILABLE = None  # Will be set on first call to _ensure_vader_loaded()
_vader_analyzer = None
_VADER_LOAD_ERROR = None

# Module-level metrics counters (for observability)
_metrics = {
    "tier0_calls": 0,
    "tier1_fallback_requests": 0,
    "vader_unavailable": 0,
    "band_green": 0,
    "band_amber": 0,
    "band_red": 0,
    "safety_keyword_detections": 0,
    "truncated_inputs": 0,
}


def _ensure_vader_loaded(preloaded_models: dict[str, Any] | None = None):
    """Lazy-load VADER sentiment analyzer on first use, or use preloaded model from app.state."""
    global _VADER_AVAILABLE, _vader_analyzer, _VADER_LOAD_ERROR

    if _VADER_AVAILABLE is not None:
        return _VADER_AVAILABLE  # Already tried loading

    # Check for preloaded model first (from kernel startup)
    if preloaded_models and "vader_analyzer" in preloaded_models:
        preloaded_vader = preloaded_models["vader_analyzer"]
        if preloaded_vader is not None:
            _vader_analyzer = preloaded_vader
            _VADER_AVAILABLE = True
            logger.debug("Using preloaded VADER analyzer from kernel startup")
            return _VADER_AVAILABLE

    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        _vader_analyzer = SentimentIntensityAnalyzer()
        _VADER_AVAILABLE = True
        logger.info("VADER sentiment analyzer loaded successfully")
    except ImportError as e:
        _VADER_LOAD_ERROR = f"ImportError: {e}"
        _VADER_AVAILABLE = False
        logger.warning(
            f"VADER initialization failed: {_VADER_LOAD_ERROR}. "
            "Affect classification will use default values."
        )
    except Exception as e:
        _VADER_LOAD_ERROR = f"Unexpected error: {type(e).__name__}: {e}"
        _VADER_AVAILABLE = False
        logger.error(f"VADER loading failed unexpectedly: {_VADER_LOAD_ERROR}")

    return _VADER_AVAILABLE


# ============================================================================
# Data Structures
# ============================================================================


@dataclass(slots=True, frozen=True)
class AffectAnnotation:
    """Affect classification result (immutable, memory-optimized)."""

    valence: float  # 0-1 scale (negative to positive sentiment)
    arousal: float  # 0-1 scale (calm to excited emotional intensity)
    dominant_emotions: tuple[str, ...]  # Top 3 emotion tags (e.g., ("joy", "excitement"))
    affect_band: str  # GREEN/AMBER/RED risk classification
    band_reasons: tuple[str, ...]  # Explanation for band (e.g., ("positive_affect",))
    model_version: str  # e.g., "tier0_vader_v1.2"
    tier: str  # "TIER_0" or "TIER_1" or "TIER_0_LOW_CONF"
    confidence: float  # 0-1 scale (confidence in classification)
    # Raw VADER scores for downstream calibration/learning
    raw_compound: float | None = None  # VADER compound score (-1 to +1)
    raw_pos: float | None = None  # VADER positive proportion
    raw_neg: float | None = None  # VADER negative proportion
    raw_neu: float | None = None  # VADER neutral proportion


# ============================================================================
# Complexity Detection (Tier-0 vs Tier-1 Fallback)
# ============================================================================


def should_fallback_to_tier1(text: str, text_lower: str) -> bool:
    """
    Check if text is too complex for Tier-0 lexicon-based classification.
    Returns True if should use Tier-1 ML model.

    Fallback triggers:
    - Text >50 words (long, nuanced content)
    - Mixed emotion keywords ("bittersweet", "conflicted")
    - Sarcasm indicators ("yeah right", "sure buddy")
    - Complex negation ("not unhappy" = double negative)

    Optimizations:
    - Reuse precompiled regex and tuple constants
    - Cheap checks first (length), expensive checks last (regex)
    - Takes pre-lowercased text_lower to avoid redundant lower() calls

    ADR: k004.1 Section "Step 1: Complexity Detection"

    Args:
        text: Original text (for word count)
        text_lower: Lowercased text (reused from caller)

    Returns:
        True if Tier-1 needed, False if Tier-0 sufficient
    """
    # Cheap check first: word count approximation (avoid allocating list)
    word_count = text.count(" ") + 1
    if word_count > MAX_WORD_COUNT_TIER0:
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                f"Fallback to Tier-1: Text too long ({word_count} words > {MAX_WORD_COUNT_TIER0})"
            )
        _metrics["tier1_fallback_requests"] += 1
        return True

    # Mixed emotion keywords (tuple lookup faster than list)
    if any(keyword in text_lower for keyword in MIXED_EMOTION_KEYWORDS):
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Fallback to Tier-1: Mixed emotion keywords detected")
        _metrics["tier1_fallback_requests"] += 1
        return True

    # Sarcasm indicators
    if any(indicator in text_lower for indicator in SARCASM_INDICATORS):
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Fallback to Tier-1: Sarcasm indicators detected")
        _metrics["tier1_fallback_requests"] += 1
        return True

    # Expensive check last: complex negation regex
    if COMPLEX_NEGATION_RE.search(text_lower):
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Fallback to Tier-1: Complex negation (double negative) detected")
        _metrics["tier1_fallback_requests"] += 1
        return True

    return False  # Simple enough for Tier-0


# ============================================================================
# Circumplex Model: Valence/Arousal → Emotion Tags
# ============================================================================


def map_circumplex_to_emotions(valence: float, arousal: float) -> tuple[str, ...]:
    """
    Map continuous valence/arousal to discrete emotion tags.
    Uses Russell's circumplex model quadrants.

    Russell (1980) divides affect space into 4 quadrants:
    - High Valence + High Arousal → Joy, Excitement, Enthusiasm
    - High Valence + Low Arousal → Contentment, Relaxation, Satisfaction
    - Low Valence + High Arousal → Anxiety, Anger, Fear
    - Low Valence + Low Arousal → Sadness, Depression, Boredom

    Optimizations:
    - Returns tuple (immutable, hashable, faster than list)
    - Uses config constants instead of magic numbers

    ADR: k004.1 Section "Step 3: Circumplex to Emotion Mapping"

    Args:
        valence: 0-1 scale (0=negative, 1=positive)
        arousal: 0-1 scale (0=calm, 1=excited)

    Returns:
        Tuple of 1-3 emotion tags (never empty, defaults to ("neutral",))
    """
    # High Valence (>0.6) → Positive emotions
    if valence > HIGH_VALENCE_THRESHOLD:
        if arousal > HIGH_AROUSAL_THRESHOLD:
            # High arousal → Joy, Excitement
            return ("joy", "excitement", "enthusiasm")
        else:
            # Low/moderate arousal → Contentment, Relaxation
            return ("contentment", "relaxation", "satisfaction")

    # Low Valence (<0.4) → Negative emotions
    elif valence < LOW_VALENCE_THRESHOLD:
        if arousal > HIGH_AROUSAL_THRESHOLD:
            # High arousal → Anxiety, Anger, Fear
            return ("anxiety", "anger", "fear")
        else:
            # Low arousal → Sadness, Depression
            return ("sadness", "depression", "boredom")

    # Moderate valence (0.4-0.6) → Neutral or mixed
    else:
        return ("neutral",)


# ============================================================================
# Affect Band Classification (GREEN/AMBER/RED)
# ============================================================================


def classify_affect_band(valence: float, arousal: float) -> tuple[str, tuple[str, ...]]:
    """
    Classify affect band (GREEN/AMBER/RED) based on valence and arousal.

    Band Definitions (from contract config_schema):
    - GREEN: Positive or neutral affect, no risk indicators
    - AMBER: Mild negative affect, worth monitoring
    - RED: Strong negative affect, requires attention/escalation

    Thresholds (from contract loaded as module constants):
    - RED_BAND_VALENCE_THRESHOLD: 0.25
    - AMBER_BAND_VALENCE_THRESHOLD: 0.4
    - GREEN_BAND_VALENCE_THRESHOLD: 0.5

    Optimizations:
    - Returns tuple (immutable, hashable)
    - Uses config constants instead of magic numbers
    - Updates metrics counters for observability

    ADR: k004.1 Section "Step 4: Affect Band Classification"

    Args:
        valence: 0-1 scale (0=negative, 1=positive)
        arousal: 0-1 scale (0=calm, 1=excited)

    Returns:
        Tuple of (band, reasons)
        - band: "GREEN" | "AMBER" | "RED"
        - reasons: Tuple of explanation strings
    """
    if valence >= GREEN_BAND_VALENCE_THRESHOLD:
        # Positive → GREEN
        _metrics["band_green"] += 1
        return ("GREEN", ("positive_affect",))

    elif valence >= AMBER_BAND_VALENCE_THRESHOLD and arousal < HIGH_AROUSAL_THRESHOLD:
        # Mild negative, low arousal → AMBER
        _metrics["band_amber"] += 1
        return ("AMBER", ("mild_negative_affect", "low_arousal"))

    elif valence < RED_BAND_VALENCE_THRESHOLD:
        # Strong negative → RED
        _metrics["band_red"] += 1
        if arousal >= HIGH_AROUSAL_THRESHOLD:
            return ("RED", ("strong_negative_affect", "high_arousal"))
        else:
            return ("RED", ("strong_negative_affect", "low_arousal_depression_risk"))

    else:
        # Moderate negative → AMBER
        _metrics["band_amber"] += 1
        return ("AMBER", ("moderate_negative_affect",))


# ============================================================================
# Safety & Domain Overrides
# ============================================================================


def check_safety_keywords(text_lower: str) -> bool:
    """Check for high-risk safety keywords that force RED band."""
    return any(keyword in text_lower for keyword in SAFETY_KEYWORDS)


def apply_domain_lexicon_adjustments(text_lower: str, valence: float) -> float:
    """Apply FamilyOS domain-specific lexicon adjustments to valence."""
    adjustment = 0.0
    for phrase, delta in DOMAIN_LEXICON.items():
        if phrase in text_lower:
            adjustment += delta
    return max(0.0, min(1.0, valence + adjustment))  # Clamp to [0,1]


def apply_emoji_adjustments(text: str, valence: float) -> float:
    """Apply emoji-based valence adjustments."""
    adjustment = 0.0
    emoji_count = 0
    for emoji, emoji_val in EMOJI_VALENCE.items():
        if emoji in text:
            adjustment += emoji_val
            emoji_count += 1
    if emoji_count > 0:
        # Weighted average with original valence
        weight = min(emoji_count * 0.1, 0.3)  # Max 30% influence
        return valence * (1 - weight) + (adjustment / emoji_count) * weight
    return valence


def calculate_confidence(
    valence: float, arousal: float, is_complex: bool, is_low_conf_tier0: bool
) -> float:
    """
    Calculate confidence score (0-1) based on multiple factors.

    High confidence when:
    - Valence far from neutral (0.5)
    - High arousal (strong emotion)
    - Not complex text (no fallback triggers)
    - Not low-confidence Tier-0 (forced VADER on complex text)

    Args:
        valence: Classified valence (0-1)
        arousal: Classified arousal (0-1)
        is_complex: True if text had Tier-1 fallback triggers
        is_low_conf_tier0: True if using Tier-0 despite complexity

    Returns:
        Confidence score (0-1)
    """
    # Distance from neutral valence (0.5)
    valence_distance = abs(valence - 0.5)

    # Base confidence from valence clarity
    confidence = min(valence_distance / 0.5, 1.0)  # Normalize to [0,1]

    # Boost from high arousal (strong emotion = more confident)
    confidence += arousal * 0.2

    # Penalize complex text
    if is_complex:
        confidence *= 0.6

    # Penalize low-conf Tier-0 (forced VADER on complex text)
    if is_low_conf_tier0:
        confidence *= 0.5

    return max(0.0, min(1.0, confidence))  # Clamp to [0,1]


# ============================================================================
# Tier-0 VADER Classification
# ============================================================================


def tier0_classify(
    text: str,
    allow_low_confidence: bool = False,
    preloaded_models: dict[str, Any] | None = None,
) -> AffectAnnotation | None:
    """
    Tier-0 fast path: VADER lexicon-based classification.
    Returns None if text too complex (triggers Tier-1 fallback), unless allow_low_confidence=True.

    Algorithm:
    1. Input validation & truncation
    2. Safety keyword detection (force RED if present)
    3. Complexity check → Fallback to Tier-1 if needed (or continue with low confidence)
    4. VADER sentiment scores (compound, pos, neg, neu)
    5. Domain lexicon & emoji adjustments
    6. Map to valence/arousal
    7. Circumplex → emotion tags
    8. Affect band classification
    9. Confidence scoring

    Optimizations:
    - Precompute text_lower once, reuse everywhere
    - Local binding of _vader_analyzer to avoid global lookups
    - Clamp valence/arousal to [0,1]
    - Return raw VADER scores for downstream learning
    - Metrics counters for observability

    Performance: <2ms P99 (CPU-only, no GPU)
    Accuracy: 73% on simple events (sufficient for salience scoring)

    ADR: k004.1 Section "Tier-0 Classification Algorithm"
    Contract: k0/contracts/modules/affect.analyze.v1.yaml

    Args:
        text: Event description text
        allow_low_confidence: If True, classify even complex text with low confidence tier
        preloaded_models: Optional dict with preloaded VADER analyzer

    Returns:
        AffectAnnotation if classified, None if Tier-1 fallback needed
    """
    _metrics["tier0_calls"] += 1

    # Step 1: Input validation & truncation
    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH]
        _metrics["truncated_inputs"] += 1

    # Precompute lowercased text (used for all keyword checks)
    text_lower = text.lower()

    # Step 2: Safety keyword detection (force RED regardless of VADER)
    if check_safety_keywords(text_lower):
        _metrics["safety_keyword_detections"] += 1
        _metrics["band_red"] += 1
        return AffectAnnotation(
            valence=0.1,  # Very negative
            arousal=0.8,  # High intensity
            dominant_emotions=("anxiety", "fear"),
            affect_band="RED",
            band_reasons=("safety_keyword_detected",),
            model_version="tier0_vader_v1.2_safety_override",
            tier="TIER_0",
            confidence=1.0,  # High confidence in safety detection
            raw_compound=None,
            raw_pos=None,
            raw_neg=None,
            raw_neu=None,
        )

    # Step 3: Complexity check
    is_complex = should_fallback_to_tier1(text, text_lower)
    if is_complex and not allow_low_confidence:
        return None  # Use Tier-1 ML model

    # Step 4: Ensure VADER loaded (with preloaded models)
    if not _ensure_vader_loaded(preloaded_models):
        logger.warning(
            "VADER not available, using default affect values "
            f"(valence={DEFAULT_VALENCE}, arousal={DEFAULT_AROUSAL}, band=GREEN)"
        )
        _metrics["vader_unavailable"] += 1
        _metrics["band_green"] += 1
        return AffectAnnotation(
            valence=DEFAULT_VALENCE,  # Neutral
            arousal=DEFAULT_AROUSAL,  # Low-moderate
            dominant_emotions=("neutral",),
            affect_band="GREEN",
            band_reasons=("default_fallback_vader_unavailable",),
            model_version="tier0_vader_v1.2_unavailable",
            tier="TIER_0",
            confidence=0.3,  # Low confidence for fallback
            raw_compound=None,
            raw_pos=None,
            raw_neg=None,
            raw_neu=None,
        )

    # Step 5: VADER sentiment analysis (local binding to avoid global lookups)
    analyzer = _vader_analyzer
    scores = analyzer.polarity_scores(text)  # type: ignore
    # scores = {
    #   'compound': 0.6369,   # Normalized total (-1.0 to +1.0)
    #   'pos': 0.4,           # Proportion positive
    #   'neu': 0.6,           # Proportion neutral
    #   'neg': 0.0            # Proportion negative
    # }

    # Step 6: Map to valence/arousal
    valence = (scores["compound"] + 1.0) / 2.0  # [-1,1] → [0,1]
    arousal = scores["pos"] + scores["neg"]  # Emotional intensity

    # Step 7: Apply domain lexicon & emoji adjustments
    valence = apply_domain_lexicon_adjustments(text_lower, valence)
    valence = apply_emoji_adjustments(text, valence)

    # Clamp to [0,1] range (guard against pathological inputs)
    valence = max(0.0, min(1.0, valence))
    arousal = max(0.0, min(1.0, arousal))

    # Step 8: Derive dominant emotions
    dominant_emotions = map_circumplex_to_emotions(valence, arousal)

    # Step 9: Affect band classification
    affect_band, band_reasons = classify_affect_band(valence, arousal)

    # Add complexity flag to band_reasons if using low-confidence Tier-0
    if is_complex and allow_low_confidence:
        band_reasons = band_reasons + ("tier1_desired_but_not_available",)

    # Step 10: Calculate confidence
    tier = "TIER_0_LOW_CONF" if is_complex else "TIER_0"
    confidence = calculate_confidence(valence, arousal, is_complex, is_complex)

    return AffectAnnotation(
        valence=valence,
        arousal=arousal,
        dominant_emotions=dominant_emotions,
        affect_band=affect_band,
        band_reasons=band_reasons,
        model_version="tier0_vader_v1.2",
        tier=tier,
        confidence=confidence,
        raw_compound=scores["compound"],
        raw_pos=scores["pos"],
        raw_neg=scores["neg"],
        raw_neu=scores["neu"],
    )


# ============================================================================
# Module Entry Point (Phase 2 Signature)
# ============================================================================


async def run(message: Any, context: Any, **config: Any) -> dict[str, Any]:
    """
    M04 affect.analyze module entry point (Phase 2).

    Process:
    1. Extract text from cognitive.memory.write.committed.v1 event
    2. Tier-0 classification (VADER)
    3. If Tier-0 returns None → Try low-confidence Tier-0 (future: Tier-1 ML)
    4. Emit p02.affect.analyzed.v1 event with rich output

    Optimizations:
    - Conditional logging to avoid string formatting overhead
    - Preserve raw VADER scores for downstream learning
    - Metrics counters for observability

    Contract: k0/contracts/modules/affect.analyze.v1.yaml

    Args:
        message: BusMessage with .payload, .trace_id, .offset
        context: PipelineContext with .syscalls, .logger, .config
        **config: Stage-specific configuration:
            - confidence_threshold (float): Minimum confidence for classification (default: 0.8)

    Returns:
        Enriched envelope dict with affect analysis fields:
            - affect_valence: float (-1.0 to 1.0)
            - affect_arousal: float (0.0 to 1.0)
            - dominant_emotions: list of emotion labels
            - affect_band: str (GREEN/AMBER/RED)
            - band_reasons: list of reasoning codes
            - model_version: str (model identifier)
            - confidence: float (0.0 to 1.0)

    Raises:
        ValueError: Invalid input format
        RuntimeError: Classification failed
    """
    # Parse envelope from message payload
    import json

    envelope = (
        json.loads(message.payload)
        if isinstance(message.payload, (str, bytes))
        else message.payload
    )

    # Extract configuration
    confidence_threshold = config.get("confidence_threshold", 0.8)

    # Get preloaded models from context (if available from kernel startup)
    preloaded_models = getattr(context, "preloaded_models", None)

    # Log module start
    context.logger.debug(
        "M04 affect.analyze starting",
        extra={
            "module_id": "affect.analyze",
            "trace_id": message.trace_id,
            "event_id": envelope.get("event_id"),
            "confidence_threshold": confidence_threshold,
        },
    )

    # Extract text from envelope body
    text = envelope.get("body", {}).get("text", "")

    if not text or not isinstance(text, str):
        context.logger.error(
            "Missing or invalid text field",
            extra={
                "module_id": "affect.analyze",
                "trace_id": message.trace_id,
                "text_type": type(text).__name__,
            },
        )
        raise ValueError(f"Missing or invalid 'text' field in payload (got: {type(text).__name__})")

    context.logger.debug(
        f"Analyzing affect for text (len={len(text)})",
        extra={
            "module_id": "affect.analyze",
            "trace_id": message.trace_id,
            "text_length": len(text),
        },
    )

    # Tier-0 classification (with preloaded models)
    annotation = tier0_classify(text, allow_low_confidence=False, preloaded_models=preloaded_models)

    if annotation is None:
        # Tier-1 fallback: For now, use low-confidence Tier-0
        # Future: Call Tier-1 ML model here (k004.2)
        context.logger.warning(
            "Tier-1 not implemented, using low-confidence Tier-0",
            extra={
                "module_id": "affect.analyze",
                "trace_id": message.trace_id,
            },
        )
        annotation = tier0_classify(
            text, allow_low_confidence=True, preloaded_models=preloaded_models
        )

        if annotation is None:
            # Ultimate fallback (should never happen unless VADER fails)
            annotation = AffectAnnotation(
                valence=DEFAULT_VALENCE,  # Neutral (default from contract)
                arousal=DEFAULT_AROUSAL,  # Low-moderate (default from contract)
                dominant_emotions=("neutral",),
                affect_band="GREEN",
                band_reasons=("tier1_not_implemented_ultimate_fallback",),
                model_version="tier0_vader_v1.2",
                tier="TIER_1_PLACEHOLDER",
                confidence=0.2,  # Very low confidence
                raw_compound=None,
                raw_pos=None,
                raw_neg=None,
                raw_neu=None,
            )

    # Return enriched envelope (merge affect fields into original envelope)
    enriched_envelope = {
        **envelope,
        "affect_valence": annotation.valence,
        "affect_arousal": annotation.arousal,
        "dominant_emotions": list(annotation.dominant_emotions),  # Convert tuple → list
        "affect_band": annotation.affect_band,
        "band_reasons": list(annotation.band_reasons),  # Convert tuple → list
        "model_version": annotation.model_version,
        "confidence": annotation.confidence,
        # Raw VADER scores for downstream learning/calibration
        "raw_vader_compound": annotation.raw_compound,
        "raw_vader_pos": annotation.raw_pos,
        "raw_vader_neg": annotation.raw_neg,
        "raw_vader_neu": annotation.raw_neu,
    }

    # Log module completion
    context.logger.debug(
        "M04 affect.analyze completed",
        extra={
            "module_id": "affect.analyze",
            "trace_id": message.trace_id,
            "valence": annotation.valence,
            "arousal": annotation.arousal,
            "affect_band": annotation.affect_band,
            "confidence": annotation.confidence,
        },
    )

    return enriched_envelope


# ============================================================================
# Observability
# ============================================================================


def get_metrics() -> dict[str, int]:
    """
    Get current metrics counters for observability/telemetry.

    Returns:
        Dictionary of metric names → counts
    """
    return _metrics.copy()


def reset_metrics() -> None:
    """Reset all metrics counters to zero (for testing)."""
    for key in _metrics:
        _metrics[key] = 0
