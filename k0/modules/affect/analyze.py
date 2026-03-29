"""
M04: affect.analyze (Amygdala/Affect System)

Phase 2 Declarative Module - Emotional content and risk level analysis

Architecture (v2 trust-then-fill):
- Tier 0: MW v2 per-extraction affect passthrough + safety heads only (~85%, <10ms)
- Tier 1: Full UltraBERT inference when MW absent/malformed (~10%, <70ms)
- Tier 2: VADER fallback when UltraBERT fails (~5%, <20ms)
- Tier 3: Safe defaults when all fail (<1%)
- Safety heads (clinical_safety_risk, safety_familyos_band) ALWAYS run on body.text

UltraBERT is DEMOTED from primary to fallback. MW v2 provides per-extraction
affect from full conversation context (~2000 tokens). UltraBERT sees only
body.text (~15-30 tokens). MW affect is higher quality when present.

Performance:
- MW fast path: <10ms P95 (safety heads only)
- UltraBERT fallback: <70ms P95 (full inference)
- VADER fallback: <20ms P95
- Safety accuracy: 96.2% (UltraBERT safety heads)

Contract: k0/contracts/modules/affect.analyze.v2.yaml
ADR: docs/architecture/decisions-K0/modules/k004.1-tier0-fast-affect.md
     docs/architecture/decisions-K0/modules/k004.2-transformer-affect.md

Related Modules:
- M02 (semantic_project): Parallel module, NER fallback source
- M06 (salience.score): Downstream consumer of affect data

Input: cognitive.memory.write.committed.v1 event
Output: p02.affect.analyzed.v2 event
Side Effects: None (pure computation)

Epic: 3.10 - M04 Trust-Then-Fill Mode Implementation
Author: K0 Architecture Team
Date: 2025-11-17 (v1), 2026-03-01 (v2 trust-then-fill)
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
    "ultrabert_calls": 0,
    "ultrabert_unavailable": 0,
    "tier0_calls": 0,
    "tier1_calls": 0,
    "tier1_fallback_requests": 0,
    "vader_unavailable": 0,
    "transformer_unavailable": 0,
    "clinical_safety_calls": 0,
    "clinical_safety_detections": 0,
    "band_green": 0,
    "band_amber": 0,
    "band_red": 0,
    "safety_keyword_detections": 0,
    "truncated_inputs": 0,
    "mw_v2_passthrough": 0,
    "mw_v2_malformed": 0,
    "safe_defaults_used": 0,
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
    # v2 trust-then-fill additions
    dominance: float | None = None  # 0-1 3rd VAD dimension (null from VADER)
    affect_source: str = "default"  # mw_v2 | ultrabert | vader | default


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


def check_clinical_safety(text: str) -> tuple[bool, str | None, str | None]:
    """
    Check for mental health risks using clinical NLP detector.

    This is an upgraded safety check that uses transformer-based detection
    combined with clinically validated risk indicators.

    Research: Coppersmith et al. (2018) - CLPsych shared task
              Zirikly et al. (2019) - Suicide risk assessment

    Args:
        text: Input text to assess

    Returns:
        Tuple of (is_concern, severity, summary)
        - is_concern: True if any risk detected
        - severity: NONE/LOW/MEDIUM/HIGH/CRITICAL or None if unavailable
        - summary: Human-readable summary or None

    Issue: 3.1.2 - Add Safety Detection with Clinical NLP
    """
    _metrics["clinical_safety_calls"] += 1

    try:
        from k0.modules.affect.clinical_safety import assess_safety
    except ImportError:
        logger.debug("clinical_safety module not available")
        return False, None, None

    try:
        assessment = assess_safety(text)

        if assessment.risk_detected:
            _metrics["clinical_safety_detections"] += 1

        return (
            assessment.risk_detected,
            assessment.severity.value if assessment.severity else None,
            assessment.indicator_summary,
        )

    except Exception as e:
        logger.warning(f"Clinical safety assessment failed: {e}")
        return False, None, None


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

    # Step 2: Safety detection (clinical NLP + keyword fallback)
    # First try clinical safety detector for better accuracy
    clinical_concern, clinical_severity, clinical_summary = check_clinical_safety(text)

    if clinical_concern and clinical_severity in ("HIGH", "CRITICAL"):
        # Clinical NLP detected high/critical risk - force RED band
        _metrics["band_red"] += 1
        return AffectAnnotation(
            valence=0.1,  # Very negative
            arousal=0.85,  # High intensity
            dominant_emotions=("anxiety", "fear", "distress"),
            affect_band="RED",
            band_reasons=(
                "clinical_safety_detected",
                (
                    f"severity_{clinical_severity.lower()}"
                    if clinical_severity
                    else "unknown_severity"
                ),
            ),
            model_version="tier0_clinical_safety_v1.0",
            tier="TIER_0",
            confidence=1.0,  # High confidence in clinical safety detection
            raw_compound=None,
            raw_pos=None,
            raw_neg=None,
            raw_neu=None,
        )
    elif clinical_concern and clinical_severity == "MEDIUM":
        # Medium severity - force AMBER band but continue processing
        # Will override final band to AMBER if not already RED
        pass  # Handled in band classification

    # Fallback to keyword detection for backwards compatibility
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
# Tier-1 Transformer Classification (GoEmotions)
# ============================================================================


def tier1_classify(
    text: str,
    preloaded_models: dict[str, Any] | None = None,
) -> AffectAnnotation | None:
    """
    Tier-1 transformer-based classification using GoEmotions model.

    Model: SamLowe/roberta-base-go_emotions (27 emotions + neutral)
    Research: Demszky et al. (2020) - GoEmotions dataset

    Algorithm:
    1. Import and initialize TransformerAffect (lazy loading)
    2. Run multi-label emotion classification
    3. Map emotions to valence/arousal via Russell's circumplex
    4. Classify affect band with safety detection
    5. Return AffectAnnotation compatible with Tier-0 output

    Performance: <30ms P95 (GPU), <100ms P95 (CPU)
    Accuracy: >85% on GoEmotions test set

    Issue: 3.1.1 - Upgrade to Transformer-Based Emotion Detection

    Args:
        text: Event description text
        preloaded_models: Optional dict with preloaded GoEmotions model

    Returns:
        AffectAnnotation if classified, None if transformer unavailable
    """
    _metrics["tier1_calls"] += 1

    try:
        from k0.modules.affect.transformer_affect import (
            analyze_affect_transformer,
            transformer_to_legacy_annotation,
        )
    except ImportError:
        logger.warning("transformer_affect module not available for Tier-1")
        _metrics["transformer_unavailable"] += 1
        return None

    # Run transformer-based analysis
    result = analyze_affect_transformer(text)

    if result is None:
        logger.warning("GoEmotions model not available, falling back to Tier-0")
        _metrics["transformer_unavailable"] += 1
        return None

    # Convert to AffectAnnotation for compatibility
    legacy = transformer_to_legacy_annotation(result)

    # Update metrics based on band
    if result.affect_band == "GREEN":
        _metrics["band_green"] += 1
    elif result.affect_band == "AMBER":
        _metrics["band_amber"] += 1
    else:
        _metrics["band_red"] += 1

    return AffectAnnotation(
        valence=legacy["valence"],
        arousal=legacy["arousal"],
        dominant_emotions=tuple(legacy["dominant_emotions"]),
        affect_band=legacy["affect_band"],
        band_reasons=tuple(legacy["band_reasons"]),
        model_version=legacy["model_version"],
        tier="TIER_1",
        confidence=legacy["confidence"],
        raw_compound=None,  # Not applicable for transformer
        raw_pos=None,
        raw_neg=None,
        raw_neu=None,
    )


# ============================================================================
# UltraBERT Classification (Primary Path)
# ============================================================================


def ultrabert_classify(text: str) -> AffectAnnotation | None:
    """
    Primary classification path using FamilyOS UltraBERT unified model.

    UltraBERT provides sentiment, emotions, and safety in a single model:
    - sentiment: very_positive/positive/neutral/negative/very_negative
    - emotions: top 3 from 28 emotion categories
    - safety_familyos: family-context safety classification
    - safety_generic: general safety flags

    Performance: <30ms P95 (single model vs 9 separate models)
    Accuracy: 89.6% weighted avg, 96.2% safety accuracy

    Issue: UltraBERT Migration - Single Unified Model

    Args:
        text: Event description text

    Returns:
        AffectAnnotation if classified, None if UltraBERT unavailable
    """
    _metrics["ultrabert_calls"] += 1

    try:
        from k0.runtime.ultrabert_adapter import analyze_affect, is_ultrabert_available
    except ImportError:
        logger.debug("ultrabert_adapter module not available")
        _metrics["ultrabert_unavailable"] += 1
        return None

    if not is_ultrabert_available():
        logger.debug("UltraBERT not available, falling back to legacy path")
        _metrics["ultrabert_unavailable"] += 1
        return None

    try:
        result = analyze_affect(text)

        if result is None:
            _metrics["ultrabert_unavailable"] += 1
            return None

        # Use UltraBERT's direct valence/arousal output (well-calibrated from the model)
        # instead of lossy recalculation from emotion labels.
        valence = max(0.0, min(1.0, result.valence))
        arousal = max(0.0, min(1.0, result.arousal))

        # Update band metrics
        if result.affect_band == "GREEN":
            _metrics["band_green"] += 1
        elif result.affect_band == "AMBER":
            _metrics["band_amber"] += 1
        else:
            _metrics["band_red"] += 1

        return AffectAnnotation(
            valence=valence,
            arousal=arousal,
            dominant_emotions=result.dominant_emotions,
            affect_band=result.affect_band,
            band_reasons=result.band_reasons,
            model_version=result.model_version,
            tier="ULTRABERT",
            confidence=result.confidence,
            raw_compound=None,
            raw_pos=None,
            raw_neg=None,
            raw_neu=None,
        )

    except Exception as e:
        logger.warning(f"UltraBERT classification failed: {e}")
        _metrics["ultrabert_unavailable"] += 1
        return None


# ============================================================================
# Module Entry Point (Phase 2 Signature)
# ============================================================================


# ============================================================================
# v2 Trust-Then-Fill: MW Affect Extraction
# ============================================================================


def _extract_mw_affect(body: dict[str, Any]) -> dict[str, Any] | None:
    """Extract and validate MW v2 affect values from envelope body.

    Validates that body.affect is present and body.affect.valence is a
    valid float in [0.0, 1.0]. If valid, returns a dict with MW affect
    values. If invalid or missing, returns None (triggers fallback).

    Args:
        body: Envelope body dict (may contain body.affect from MW v2).

    Returns:
        Dict with validated MW affect values, or None if absent/malformed.
    """
    affect = body.get("affect")
    if affect is None or not isinstance(affect, dict):
        return None

    # Validate valence (required for MW passthrough)
    valence = affect.get("valence")
    if valence is None:
        return None
    try:
        valence = float(valence)
    except (TypeError, ValueError):
        logger.warning(
            "MW affect.valence is not a valid float, falling back to UltraBERT",
            extra={"valence_raw": repr(affect.get("valence"))},
        )
        return None
    if not (0.0 <= valence <= 1.0):
        logger.warning(
            "MW affect.valence out of range [0.0, 1.0], falling back to UltraBERT",
            extra={"valence": valence},
        )
        return None

    # Extract arousal (optional, default 0.5)
    arousal = affect.get("arousal")
    if arousal is not None:
        try:
            arousal = float(arousal)
            arousal = max(0.0, min(1.0, arousal))
        except (TypeError, ValueError):
            arousal = 0.5
    else:
        arousal = 0.5

    # Extract dominance (optional, new in v2)
    dominance = affect.get("dominance")
    if dominance is not None:
        try:
            dominance = float(dominance)
            dominance = max(0.0, min(1.0, dominance))
        except (TypeError, ValueError):
            dominance = None

    # Extract dominant_emotions (optional)
    dominant_emotions = affect.get("dominant_emotions")
    if dominant_emotions and isinstance(dominant_emotions, list):
        dominant_emotions = tuple(str(e) for e in dominant_emotions[:5])
    else:
        dominant_emotions = map_circumplex_to_emotions(valence, arousal)

    return {
        "valence": valence,
        "arousal": arousal,
        "dominance": dominance,
        "dominant_emotions": dominant_emotions,
    }


def _run_safety_heads_only(text: str) -> tuple[bool, str | None, str | None, str, float]:
    """Run UltraBERT safety heads on text (without full sentiment/emotion inference).

    Safety classification is a safety-critical validation that must ALWAYS run
    on body.text regardless of whether MW affect is trusted. Never trust LLM
    alone for safety classification.

    Uses the UltraBERT check_safety() function which leverages the single-pass
    cache (if enabled) or runs safety_familyos capability only.

    Args:
        text: Input text to assess for safety.

    Returns:
        Tuple of (risk_detected, severity, summary, safety_band, confidence).
    """
    _metrics["clinical_safety_calls"] += 1

    # Try UltraBERT safety heads first
    try:
        from k0.runtime.ultrabert_adapter import check_safety as ultrabert_check_safety

        is_concern, safety_level, summary = ultrabert_check_safety(text)

        severity_map = {
            "GREEN": "NONE",
            "AMBER": "LOW",
            "RED": "MEDIUM",
            "CRISIS": "CRITICAL",
        }
        severity = severity_map.get(safety_level, "NONE")

        if is_concern:
            _metrics["clinical_safety_detections"] += 1

        return is_concern, severity, summary, safety_level, 0.9

    except ImportError:
        logger.debug("ultrabert_adapter not available for safety heads")

    except Exception as e:
        logger.warning(f"UltraBERT safety heads failed: {e}")

    # Fallback to clinical_safety module
    try:
        from k0.modules.affect.clinical_safety import assess_safety

        assessment = assess_safety(text)
        if assessment.risk_detected:
            _metrics["clinical_safety_detections"] += 1
        return (
            assessment.risk_detected,
            assessment.severity.value if assessment.severity else None,
            assessment.indicator_summary,
            "RED" if assessment.risk_detected else "GREEN",
            0.8,
        )
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"Clinical safety assessment failed: {e}")

    # Keyword-based safety as last resort
    text_lower = text.lower()
    if check_safety_keywords(text_lower):
        _metrics["safety_keyword_detections"] += 1
        return True, "HIGH", "Safety keyword detected", "RED", 1.0

    return False, "NONE", None, "GREEN", 0.5


# ============================================================================
# Module Entry Point (Phase 2 Signature -- v2 Trust-Then-Fill)
# ============================================================================


async def run(message: Any, context: Any, **config: Any) -> dict[str, Any]:
    """
    M04 affect.analyze module entry point (Phase 2, v2 trust-then-fill).

    Process:
    1. Extract text AND body.affect from envelope
    2. Tier 0 (MW present): Passthrough MW affect + safety heads only (~10ms)
    3. Tier 1 (MW absent): Full UltraBERT inference (~70ms)
    4. Tier 2 (UltraBERT fails): VADER fallback (~20ms)
    5. Tier 3 (all fail): Safe defaults
    6. Safety heads ALWAYS run on body.text
    7. Emit p02.affect.analyzed.v2 event with rich output

    Contract: k0/contracts/modules/affect.analyze.v2.yaml

    Args:
        message: BusMessage with .payload, .trace_id, .offset
        context: PipelineContext with .syscalls, .logger, .config
        **config: Stage-specific configuration:
            - confidence_threshold (float): Minimum confidence (default: 0.8)
            - affect_divergence_log_threshold (float): Log MW vs UltraBERT delta (default: 0.3)

    Returns:
        Enriched envelope dict with affect analysis fields:
            - affect_valence: float (0.0 to 1.0)
            - affect_arousal: float (0.0 to 1.0)
            - affect_dominance: float | null (0.0 to 1.0, 3rd VAD dimension)
            - dominant_emotions: list of emotion labels
            - affect_band: str (GREEN/AMBER/RED)
            - band_reasons: list of reasoning codes
            - model_version: str (model identifier)
            - confidence: float (0.0 to 1.0)
            - affect_source: str (mw_v2 | ultrabert | vader | default)

    Raises:
        ValueError: Invalid input format
    """
    # Use enriched envelope from pipeline_runner, with fallback to message.payload
    import json

    envelope = config.get("envelope")
    if envelope is None:
        envelope = (
            json.loads(message.payload)
            if isinstance(message.payload, (str, bytes))
            else message.payload
        )

    # Extract configuration
    confidence_threshold = config.get("confidence_threshold", 0.8)
    divergence_threshold = config.get("affect_divergence_log_threshold", 0.3)

    # Get preloaded models from context (if available from kernel startup)
    preloaded_models = getattr(context, "preloaded_models", None)

    # Log module start
    context.logger.debug(
        "M04 affect.analyze v2 starting",
        extra={
            "module_id": "affect.analyze",
            "trace_id": message.trace_id,
            "event_id": envelope.get("event_id"),
        },
    )

    # Extract body and text
    body = envelope.get("body", {})
    text = body.get("text", "")

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

    # ====================================================================
    # SAFETY HEADS -- ALWAYS RUN on body.text regardless of tier
    # Content-level safety classification is safety-critical validation.
    # Never trust LLM alone for safety.
    # ====================================================================
    safety_risk, safety_severity, safety_summary, safety_band, safety_conf = _run_safety_heads_only(
        text
    )

    # ====================================================================
    # ULTRABERT-FIRST WATERFALL
    # UltraBERT is the primary classifier. MW v2 affect is supplementary
    # (provides dominance, the 3rd VAD dimension UltraBERT lacks).
    # MW valence/arousal are NOT trusted because LLM-generated affect
    # has systematic negative bias (~0.30 mean on neutral/positive text).
    # ====================================================================
    annotation: AffectAnnotation | None = None
    mw_affect = _extract_mw_affect(body)

    # ------------------------------------------------------------------
    # TIER 0: Full UltraBERT inference (primary, <70ms)
    # ------------------------------------------------------------------
    _metrics["ultrabert_calls"] += 1
    ub_result = ultrabert_classify(text)
    if ub_result is not None:
        # Use MW dominance if available (UltraBERT does not produce it)
        mw_dominance = mw_affect["dominance"] if mw_affect else None

        annotation = AffectAnnotation(
            valence=ub_result.valence,
            arousal=ub_result.arousal,
            dominant_emotions=ub_result.dominant_emotions,
            affect_band=ub_result.affect_band,
            band_reasons=ub_result.band_reasons,
            model_version=ub_result.model_version,
            tier=ub_result.tier,
            confidence=ub_result.confidence,
            raw_compound=ub_result.raw_compound,
            raw_pos=ub_result.raw_pos,
            raw_neg=ub_result.raw_neg,
            raw_neu=ub_result.raw_neu,
            dominance=mw_dominance,
            affect_source="ultrabert",
        )
        context.logger.debug(
            "Tier 0: UltraBERT primary classification",
            extra={
                "module_id": "affect.analyze",
                "trace_id": message.trace_id,
                "ub_valence": ub_result.valence,
                "mw_valence": mw_affect["valence"] if mw_affect else None,
            },
        )

    # ------------------------------------------------------------------
    # TIER 1: MW v2 affect fallback (when UltraBERT unavailable)
    # ------------------------------------------------------------------
    if annotation is None and mw_affect is not None:
        _metrics["tier0_calls"] += 1
        context.logger.debug(
            "Tier 1: UltraBERT unavailable, MW v2 affect fallback",
            extra={
                "module_id": "affect.analyze",
                "trace_id": message.trace_id,
                "mw_valence": mw_affect["valence"],
            },
        )

        affect_band, band_reasons = classify_affect_band(mw_affect["valence"], mw_affect["arousal"])

        annotation = AffectAnnotation(
            valence=mw_affect["valence"],
            arousal=mw_affect["arousal"],
            dominant_emotions=mw_affect["dominant_emotions"],
            affect_band=affect_band,
            band_reasons=band_reasons,
            model_version="mw_v2_fallback",
            tier="MW_V2",
            confidence=0.5,  # Lower confidence: MW has known negative bias
            dominance=mw_affect["dominance"],
            affect_source="mw_v2",
        )

    # ------------------------------------------------------------------
    # TIER 2: VADER fallback (when both UltraBERT and MW unavailable)
    # ------------------------------------------------------------------
    if annotation is None:
        context.logger.debug(
            "Tier 2: UltraBERT unavailable, trying VADER",
            extra={
                "module_id": "affect.analyze",
                "trace_id": message.trace_id,
            },
        )

        vader_result = tier0_classify(
            text, allow_low_confidence=True, preloaded_models=preloaded_models
        )
        if vader_result is not None:
            annotation = AffectAnnotation(
                valence=vader_result.valence,
                arousal=vader_result.arousal,
                dominant_emotions=vader_result.dominant_emotions,
                affect_band=vader_result.affect_band,
                band_reasons=vader_result.band_reasons,
                model_version=vader_result.model_version,
                tier=vader_result.tier,
                confidence=vader_result.confidence,
                raw_compound=vader_result.raw_compound,
                raw_pos=vader_result.raw_pos,
                raw_neg=vader_result.raw_neg,
                raw_neu=vader_result.raw_neu,
                dominance=None,  # VADER does not produce dominance
                affect_source="vader",
            )

    # ------------------------------------------------------------------
    # TIER 3: Safe defaults (<1% of envelopes)
    # ------------------------------------------------------------------
    if annotation is None:
        context.logger.warning(
            "Tier 3: All classifiers failed, using safe defaults",
            extra={
                "module_id": "affect.analyze",
                "trace_id": message.trace_id,
            },
        )
        annotation = AffectAnnotation(
            valence=DEFAULT_VALENCE,
            arousal=DEFAULT_AROUSAL,
            dominant_emotions=("neutral",),
            affect_band="GREEN",
            band_reasons=("all_classifiers_unavailable_fallback",),
            model_version="safe_defaults_v2.0",
            tier="FALLBACK",
            confidence=0.2,
            dominance=None,
            affect_source="default",
        )

    # ====================================================================
    # SAFETY OVERRIDE -- apply safety band to affect band
    # ====================================================================
    final_affect_band = annotation.affect_band
    final_band_reasons = list(annotation.band_reasons)

    if safety_risk and safety_severity:
        if safety_severity in ("CRITICAL", "HIGH"):
            final_affect_band = "RED"
            final_band_reasons.append(f"clinical_safety_{safety_severity.lower()}")
        elif safety_severity == "MEDIUM":
            if final_affect_band == "GREEN":
                final_affect_band = "AMBER"
            final_band_reasons.append("clinical_safety_medium")

    # ====================================================================
    # BUILD ENRICHED ENVELOPE
    # ====================================================================
    enriched_envelope = {
        **envelope,
        # BACKWARD COMPAT: Keep flat fields during migration (Phase 2)
        "affect_valence": annotation.valence,
        "affect_arousal": annotation.arousal,
        "dominant_emotions": list(annotation.dominant_emotions),
        "affect_band": final_affect_band,
        "band_reasons": final_band_reasons,
        "model_version": annotation.model_version,
        "affect_tier": annotation.tier,
        "confidence": annotation.confidence,
        # Raw VADER scores for downstream learning/calibration
        "raw_vader_compound": annotation.raw_compound,
        "raw_vader_pos": annotation.raw_pos,
        "raw_vader_neg": annotation.raw_neg,
        "raw_vader_neu": annotation.raw_neu,
        # Clinical safety fields (for downstream salience boost)
        "clinical_safety_risk": safety_risk,
        "clinical_safety_severity": safety_severity,
        "clinical_safety_summary": safety_summary,
        # v2 additions
        "affect_dominance": annotation.dominance,
        "affect_source": annotation.affect_source,
        # Nested enrichments structure (Phase 2)
        "enrichments": {
            **envelope.get("enrichments", {}),
            "affect_analyzer": {
                "valence": annotation.valence,
                "arousal": annotation.arousal,
                "dominance": annotation.dominance,
                "dominant_emotions": list(annotation.dominant_emotions),
                "band": final_affect_band,
                "band_reasons": final_band_reasons,
                "model_version": annotation.model_version,
                "tier": annotation.tier,
                "confidence": annotation.confidence,
                "affect_source": annotation.affect_source,
                "raw_vader_compound": annotation.raw_compound,
                "raw_vader_pos": annotation.raw_pos,
                "raw_vader_neg": annotation.raw_neg,
                "raw_vader_neu": annotation.raw_neu,
                "clinical_safety_risk": safety_risk,
                "clinical_safety_severity": safety_severity,
                "clinical_safety_summary": safety_summary,
                "module_version": "v2",
                "execution_time_ms": 0.0,  # Set by PipelineRunner
            },
        },
    }

    # Log module completion
    context.logger.debug(
        "M04 affect.analyze v2 completed",
        extra={
            "module_id": "affect.analyze",
            "trace_id": message.trace_id,
            "valence": annotation.valence,
            "arousal": annotation.arousal,
            "dominance": annotation.dominance,
            "affect_band": final_affect_band,
            "affect_source": annotation.affect_source,
            "confidence": annotation.confidence,
            "clinical_safety_risk": safety_risk,
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
