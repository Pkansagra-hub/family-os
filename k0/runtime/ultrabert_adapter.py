"""
UltraBERT Adapter - Unified NLP Interface for K0 Kernel.

This module provides a singleton wrapper around FamilyOS UltraBERT v2.0.3,
replacing 9 separate models with a single unified model.

Capabilities Provided (12 total):
- sentiment: 5-class sentiment (very_negative to very_positive)
- emotions: 44-class multi-label emotion detection
- safety_familyos: GREEN/AMBER/RED/CRISIS safety classification
- safety_generic: Toxicity detection
- ner_family: Family entity extraction (KINSHIP, FAMILY_EVENT)
- ner_general: General NER (PERSON, ORG, LOC, DATE)
- temporal: Temporal expression extraction (DATE_REL, TIME_REL)
- intent: User intent classification
- ingress: Message routing category
- relation: Relationship type detection
- nli: Natural language inference
- embedding: 768-dimensional embeddings

Performance:
- Load time: ~5 seconds (vs ~62 seconds for 9 models)
- Memory: ~500MB (vs ~4350MB for 9 models)
- Latency: ~30ms all capabilities (vs ~150ms for 9 models)
- Accuracy: 89.6% weighted average

Usage:
    from k0.runtime.ultrabert_adapter import get_ultrabert_client, analyze_text

    # Get singleton client
    client = get_ultrabert_client()

    # Full analysis
    result = client.analyze("Mom picked up the kids!")
    print(result.sentiment)   # "very_positive"
    print(result.safety)      # "GREEN"
    print(result.emotions)    # ["joy", "love"]

    # Quick convenience methods
    sentiment = client.get_sentiment("I love this!")
    is_safe = client.is_safe("Having a great day!")
    entities = client.get_entities("Mom and Dad went to dinner")

Issue: UltraBERT Integration - Replace 9 models with unified model
Author: K0 Architecture Team
Date: 2025-12-09
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Module-level singleton
_ultrabert_client: Any = None
_ultrabert_lock = threading.Lock()
_initialization_attempted = False


# ============================================================================
# Result Adapters - Map UltraBERT outputs to K0 module interfaces
# ============================================================================


@dataclass
class AffectResult:
    """Affect analysis result compatible with M04 affect.analyze interface."""

    valence: float  # 0-1 scale (mapped from sentiment)
    arousal: float  # 0-1 scale (estimated from emotion intensity)
    dominant_emotions: tuple[str, ...]  # Top emotions
    affect_band: str  # GREEN/AMBER/RED (mapped from safety)
    band_reasons: tuple[str, ...]  # Explanation
    sentiment: str  # very_negative/negative/neutral/positive/very_positive
    sentiment_confidence: float  # 0-1
    model_version: str  # "ultrabert_v2.0.3"
    tier: str  # "ULTRABERT"
    confidence: float  # Overall confidence
    # Safety fields
    safety_severity: str | None = None  # NONE/LOW/MEDIUM/HIGH/CRITICAL
    safety_risk_detected: bool = False
    # Raw scores for downstream use
    emotion_scores: dict[str, float] | None = None
    safety_scores: dict[str, float] | None = None


@dataclass
class EntityResult:
    """Entity extraction result compatible with M02 semantic_project interface."""

    text: str  # Entity text span
    label: str  # Entity type (PERSON, KINSHIP, ORG, etc.)
    start: int  # Start character position
    end: int  # End character position
    confidence: float  # 0-1 confidence score
    source: str = "ultrabert"  # Model source


@dataclass
class TemporalResult:
    """Temporal expression result."""

    text: str  # Temporal text span
    label: str  # DATE_REL, TIME_REL, etc.
    start: int  # Start token position
    end: int  # End token position


@dataclass
class ActivityResult:
    """Activity classification result compatible with M10 ingress_classify interface."""

    activity_type: str  # Primary activity (meal, celebration, etc.)
    confidence: float  # 0-1 confidence
    ingress_category: str  # Routing category (CELEBRATION, ROUTINE, etc.)
    intent: str  # User intent (log_memory, share_news, etc.)
    intent_confidence: float  # 0-1


# ============================================================================
# Sentiment to Valence Mapping
# ============================================================================

SENTIMENT_TO_VALENCE = {
    "very_negative": 0.1,
    "negative": 0.3,
    "neutral": 0.5,
    "positive": 0.7,
    "very_positive": 0.9,
}

# Safety band mapping from UltraBERT safety to K0 affect bands
SAFETY_TO_BAND = {
    "GREEN": "GREEN",
    "AMBER": "AMBER",
    "RED": "RED",
    "CRISIS": "RED",  # Map CRISIS to RED for K0 compatibility
}

# Ingress to activity type mapping
INGRESS_TO_ACTIVITY = {
    "CELEBRATION": "celebration",
    "MEAL": "meal",
    "ROUTINE": "routine",
    "SOCIAL": "social",
    "WORK": "work",
    "TRAVEL": "travel",
    "HEALTH": "medical_appointment",
    "EDUCATION": "learning",
    "EXERCISE": "exercise",
    "ENTERTAINMENT": "entertainment",
    "FAMILY": "social",
    "MEMORY": "routine",  # Memory logging is typically routine activity
    "OTHER": "routine",
}


# ============================================================================
# Singleton Client Management
# ============================================================================


def _load_ultrabert_client() -> Any:
    """
    Load and initialize UltraBERT client.

    Returns:
        Initialized Client instance or None if unavailable.
    """
    global _ultrabert_client, _initialization_attempted

    if _initialization_attempted:
        return _ultrabert_client

    _initialization_attempted = True

    try:
        from familyos_ultrabert import Client

        logger.info("Loading FamilyOS UltraBERT client...")
        client = Client(warmup=True, warmup_rounds=2, verbose=False)
        logger.info(
            "UltraBERT client loaded successfully",
            extra={
                "version": getattr(client, "VERSION", "unknown"),
                "backend": "auto",
            },
        )
        return client

    except ImportError as e:
        logger.warning(f"familyos_ultrabert not installed: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to load UltraBERT client: {e}")
        return None


def get_ultrabert_client() -> Any:
    """
    Get singleton UltraBERT client instance.

    Thread-safe lazy initialization.

    Returns:
        UltraBERT Client instance or None if unavailable.
    """
    global _ultrabert_client

    if _ultrabert_client is not None:
        return _ultrabert_client

    with _ultrabert_lock:
        if _ultrabert_client is None:
            _ultrabert_client = _load_ultrabert_client()

    return _ultrabert_client


def is_ultrabert_available() -> bool:
    """Check if UltraBERT is available and loaded."""
    return get_ultrabert_client() is not None


def init_ultrabert_client(warmup: bool = True, warmup_rounds: int = 2) -> Any:
    """
    Initialize UltraBERT client with custom settings.

    Called during kernel startup for explicit initialization.

    Args:
        warmup: Whether to warm up the model.
        warmup_rounds: Number of warmup inference rounds.

    Returns:
        Initialized Client instance.
    """
    global _ultrabert_client, _initialization_attempted

    with _ultrabert_lock:
        if _ultrabert_client is not None:
            return _ultrabert_client

        _initialization_attempted = True

        try:
            from familyos_ultrabert import Client

            logger.info("Initializing FamilyOS UltraBERT client...")
            _ultrabert_client = Client(
                warmup=warmup,
                warmup_rounds=warmup_rounds,
                verbose=False,
            )
            logger.info(
                "UltraBERT client initialized",
                extra={
                    "version": getattr(_ultrabert_client, "VERSION", "unknown"),
                    "warmup": warmup,
                    "warmup_rounds": warmup_rounds,
                },
            )
            return _ultrabert_client

        except ImportError as e:
            logger.error(f"familyos_ultrabert not installed: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize UltraBERT: {e}")
            raise


# ============================================================================
# High-Level Analysis Functions (Module Interface Adapters)
# ============================================================================


def analyze_affect(text: str) -> AffectResult | None:
    """
    Analyze affect/sentiment/emotions using UltraBERT.

    Replaces:
    - VADER sentiment analyzer
    - GoEmotions transformer
    - ClinicalSafetyDetector

    Args:
        text: Input text to analyze.

    Returns:
        AffectResult with sentiment, emotions, safety, or None if unavailable.
    """
    client = get_ultrabert_client()
    if client is None:
        logger.warning("UltraBERT not available for affect analysis")
        return None

    try:
        result = client.analyze(
            text,
            capabilities=["sentiment", "emotions", "safety_familyos"],
        )

        # Map sentiment to valence
        valence = SENTIMENT_TO_VALENCE.get(result.sentiment, 0.5)

        # Estimate arousal from emotion intensity
        emotion_scores = getattr(result, "emotion_scores", {}) or {}
        if emotion_scores:
            arousal = min(1.0, sum(emotion_scores.values()) / len(emotion_scores) * 2)
        else:
            arousal = 0.3  # Default calm

        # Map safety to affect band
        affect_band = SAFETY_TO_BAND.get(result.safety, "GREEN")

        # Determine band reasons
        band_reasons = []
        if result.safety == "CRISIS":
            band_reasons.append("crisis_detected")
        elif result.safety == "RED":
            band_reasons.append("high_risk_detected")
        elif result.safety == "AMBER":
            band_reasons.append("moderate_concern")
        else:
            band_reasons.append("positive_affect" if valence > 0.5 else "neutral_affect")

        # Map safety to severity for clinical safety compatibility
        safety_severity_map = {
            "GREEN": "NONE",
            "AMBER": "LOW",
            "RED": "MEDIUM",
            "CRISIS": "CRITICAL",
        }

        return AffectResult(
            valence=valence,
            arousal=arousal,
            dominant_emotions=tuple(result.emotions[:3]) if result.emotions else ("neutral",),
            affect_band=affect_band,
            band_reasons=tuple(band_reasons),
            sentiment=result.sentiment,
            sentiment_confidence=getattr(result, "sentiment_confidence", 0.8),
            model_version="ultrabert_v2.0.3",
            tier="ULTRABERT",
            confidence=getattr(result, "sentiment_confidence", 0.8),
            safety_severity=safety_severity_map.get(result.safety, "NONE"),
            safety_risk_detected=result.safety in ("AMBER", "RED", "CRISIS"),
            emotion_scores=emotion_scores,
            safety_scores=getattr(result, "safety_scores", None),
        )

    except Exception as e:
        logger.error(f"UltraBERT affect analysis failed: {e}")
        return None


def extract_entities(text: str) -> list[EntityResult]:
    """
    Extract named entities using UltraBERT.

    Replaces:
    - TransformerNER (dslim/bert-base-NER)
    - spaCy NER

    Args:
        text: Input text to analyze.

    Returns:
        List of EntityResult objects.
    """
    client = get_ultrabert_client()
    if client is None:
        logger.warning("UltraBERT not available for entity extraction")
        return []

    try:
        result = client.analyze(
            text,
            capabilities=["ner_family", "ner_general"],
        )

        entities = []

        # Process family entities
        for ent in result.entities:
            entities.append(
                EntityResult(
                    text=ent.get("text", ""),
                    label=ent.get("label", "UNKNOWN"),
                    start=ent.get("start", ent.get("start_token", 0)),
                    end=ent.get("end", ent.get("end_token", 0)),
                    confidence=ent.get("confidence", 0.8),
                    source="ultrabert_family",
                )
            )

        # Process general entities
        for ent in result.general_entities:
            entities.append(
                EntityResult(
                    text=ent.get("text", ""),
                    label=ent.get("label", "UNKNOWN"),
                    start=ent.get("start", ent.get("start_token", 0)),
                    end=ent.get("end", ent.get("end_token", 0)),
                    confidence=ent.get("confidence", 0.8),
                    source="ultrabert_general",
                )
            )

        return entities

    except Exception as e:
        logger.error(f"UltraBERT entity extraction failed: {e}")
        return []


def extract_temporal(text: str) -> list[TemporalResult]:
    """
    Extract temporal expressions using UltraBERT.

    Replaces spaCy DATE/TIME extraction.

    Args:
        text: Input text to analyze.

    Returns:
        List of TemporalResult objects.
    """
    client = get_ultrabert_client()
    if client is None:
        logger.warning("UltraBERT not available for temporal extraction")
        return []

    try:
        result = client.analyze(text, capabilities=["temporal"])

        temporals = []
        for temp in result.temporal:
            temporals.append(
                TemporalResult(
                    text=temp.get("text", ""),
                    label=temp.get("label", "DATE_REL"),
                    start=temp.get("start", temp.get("start_token", 0)),
                    end=temp.get("end", temp.get("end_token", 0)),
                )
            )

        return temporals

    except Exception as e:
        logger.error(f"UltraBERT temporal extraction failed: {e}")
        return []


def classify_activity(text: str) -> ActivityResult | None:
    """
    Classify activity type and intent using UltraBERT.

    Replaces:
    - ZeroShotActivityClassifier (bart-large-mnli)
    - Rule-based ingress classification

    Args:
        text: Input text to analyze.

    Returns:
        ActivityResult with activity type and intent, or None if unavailable.
    """
    client = get_ultrabert_client()
    if client is None:
        logger.warning("UltraBERT not available for activity classification")
        return None

    try:
        result = client.analyze(text, capabilities=["ingress", "intent"])

        ingress = result.ingress
        activity_type = INGRESS_TO_ACTIVITY.get(ingress, "routine")

        return ActivityResult(
            activity_type=activity_type,
            confidence=getattr(result, "ingress_confidence", 0.8),
            ingress_category=ingress,
            intent=result.intent,
            intent_confidence=getattr(result, "intent_confidence", 0.8),
        )

    except Exception as e:
        logger.error(f"UltraBERT activity classification failed: {e}")
        return None


def get_embedding(text: str) -> list[float] | None:
    """
    Get text embedding using UltraBERT.

    Replaces SentenceTransformer (all-MiniLM-L6-v2).

    Note: UltraBERT produces 768-dim embeddings (vs 384-dim for MiniLM).

    Args:
        text: Input text to embed.

    Returns:
        768-dimensional embedding vector, or None if unavailable.
    """
    client = get_ultrabert_client()
    if client is None:
        logger.warning("UltraBERT not available for embedding")
        return None

    try:
        return client.get_embedding(text)
    except Exception as e:
        logger.error(f"UltraBERT embedding failed: {e}")
        return None


def check_safety(text: str) -> tuple[bool, str, str | None]:
    """
    Check text safety using UltraBERT.

    Replaces ClinicalSafetyDetector.

    Args:
        text: Input text to check.

    Returns:
        Tuple of (is_concern, safety_level, summary).
        - is_concern: True if not GREEN
        - safety_level: GREEN/AMBER/RED/CRISIS
        - summary: Human-readable summary
    """
    client = get_ultrabert_client()
    if client is None:
        return False, "GREEN", None

    try:
        result = client.analyze(text, capabilities=["safety_familyos"])
        is_concern = result.safety in ("AMBER", "RED", "CRISIS")
        summary = f"Safety: {result.safety}"
        if hasattr(result, "needs_attention") and result.needs_attention:
            summary += " (needs attention)"
        return is_concern, result.safety, summary

    except Exception as e:
        logger.error(f"UltraBERT safety check failed: {e}")
        return False, "GREEN", None


# ============================================================================
# Convenience Functions (Quick Single-Purpose Calls)
# ============================================================================


def quick_sentiment(text: str) -> str:
    """Get quick sentiment label."""
    client = get_ultrabert_client()
    if client is None:
        return "neutral"
    try:
        return client.get_sentiment(text)
    except Exception:
        return "neutral"


def quick_emotions(text: str) -> list[str]:
    """Get quick emotion list."""
    client = get_ultrabert_client()
    if client is None:
        return []
    try:
        return client.get_emotions(text)
    except Exception:
        return []


def quick_is_safe(text: str) -> bool:
    """Quick safety check (True if GREEN)."""
    client = get_ultrabert_client()
    if client is None:
        return True
    try:
        return client.is_safe(text)
    except Exception:
        return True


def quick_is_crisis(text: str) -> bool:
    """Quick crisis check."""
    client = get_ultrabert_client()
    if client is None:
        return False
    try:
        return client.is_crisis(text)
    except Exception:
        return False


# ============================================================================
# Full Analysis (All Capabilities)
# ============================================================================


def full_analysis(text: str) -> dict[str, Any] | None:
    """
    Run full analysis with all capabilities.

    Returns dict with all UltraBERT outputs for maximum flexibility.

    Args:
        text: Input text to analyze.

    Returns:
        Dict with all capability outputs, or None if unavailable.
    """
    client = get_ultrabert_client()
    if client is None:
        return None

    try:
        result = client.analyze(text)  # All capabilities

        return {
            "text": text,
            "sentiment": result.sentiment,
            "sentiment_confidence": getattr(result, "sentiment_confidence", 0.0),
            "emotions": result.emotions,
            "emotion_scores": getattr(result, "emotion_scores", {}),
            "safety": result.safety,
            "safety_confidence": getattr(result, "safety_confidence", 0.0),
            "entities": result.entities,
            "general_entities": result.general_entities,
            "temporal": result.temporal,
            "intent": result.intent,
            "ingress": result.ingress,
            "relations": getattr(result, "relations", []),
            "embedding": result.embedding,
            "latency_ms": result.latency_ms,
        }

    except Exception as e:
        logger.error(f"UltraBERT full analysis failed: {e}")
        return None
