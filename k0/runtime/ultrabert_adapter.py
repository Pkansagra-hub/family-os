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
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

logger = logging.getLogger(__name__)

# Module-level singleton
_ultrabert_client: Any = None
_ultrabert_lock = threading.Lock()
_initialization_attempted = False


def _maybe_full_warmup(client: Any) -> None:
    """Optionally run a full `analyze()` pass to avoid first-request latency spikes.

    Why this exists:
    - The UltraBERT client supports warmup on init, but that warmup may not exercise
      the exact code-path used by K0 (especially when we call full `analyze()` to
      reuse one forward pass for multiple module needs).
    - On GPU/PyTorch backends, the first real `analyze()` can still pay compilation/
      kernel initialization costs. This warmup makes that cost happen at startup.

    Controlled by env:
      - K0_ULTRABERT_FULL_WARMUP: "1" (default) / "0" disables
      - K0_ULTRABERT_FULL_WARMUP_ROUNDS: int, default 1
      - K0_ULTRABERT_FULL_WARMUP_TEXT: sample text, default "warmup"
    """
    if client is None:
        return

    if os.getenv("K0_ULTRABERT_FULL_WARMUP", "1") in {"0", "false", "False"}:
        return

    try:
        rounds = int(os.getenv("K0_ULTRABERT_FULL_WARMUP_ROUNDS", "1"))
    except ValueError:
        rounds = 1

    if rounds <= 0:
        return

    text = os.getenv("K0_ULTRABERT_FULL_WARMUP_TEXT", "warmup")
    for i in range(rounds):
        try:
            t0 = time.perf_counter()
            _ = client.analyze(text)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            logger.info(
                "UltraBERT full-analysis warmup complete",
                extra={
                    "warmup_round": i + 1,
                    "warmup_rounds": rounds,
                    "backend": getattr(client, "backend", "unknown"),
                    "latency_ms": round(elapsed_ms, 2),
                },
            )
        except Exception as e:
            logger.warning(f"UltraBERT full-analysis warmup failed: {e}")
            return


# ============================================================================
# Single-pass analysis cache
#
# Motivation:
# - Multiple K0 modules call UltraBERT for different slices (affect, entities,
#   ingress/intent). UltraBERT can return all fields in one forward pass.
# - Enabling single-pass caching collapses repeated per-event inference.
#
# Behavior:
# - When enabled, adapter performs ONE client.analyze(text) per unique text (TTL/LRU)
#   and all helper functions read from the cached full result.
# - When disabled, adapter keeps per-capability calls (legacy behavior).
#
# NOTE: This is an in-process cache (per kernel process), not cross-process.
# ============================================================================


def _is_single_pass_enabled() -> bool:
    """Return True when adapter should reuse one full forward pass per text.

    Reads env dynamically so tests and live configuration can toggle behavior
    without requiring a process restart.
    """
    return os.getenv("K0_ULTRABERT_SINGLE_PASS", "1") not in {"0", "false", "False"}


_ANALYSIS_CACHE_TTL_SEC = float(os.getenv("K0_ULTRABERT_ANALYSIS_CACHE_TTL_SEC", "30"))
_ANALYSIS_CACHE_MAX_ENTRIES = int(os.getenv("K0_ULTRABERT_ANALYSIS_CACHE_MAX_ENTRIES", "64"))

_analysis_cache_lock = threading.Lock()
_analysis_cache: "OrderedDict[str, tuple[float, Any]]" = OrderedDict()

_analysis_cache_metrics: dict[str, int] = {
    "analysis_cache_hits": 0,
    "analysis_cache_misses": 0,
    "analysis_cache_evictions": 0,
    "analysis_single_pass_calls": 0,
}


def _analysis_cache_key(text: str) -> str:
    normalized = (text or "").strip()
    return sha256(normalized.encode("utf-8")).hexdigest()


def _analysis_cache_get(key: str) -> Any | None:
    now = time.time()
    with _analysis_cache_lock:
        item = _analysis_cache.get(key)
        if item is None:
            _analysis_cache_metrics["analysis_cache_misses"] += 1
            return None

        created_at, result = item
        if _ANALYSIS_CACHE_TTL_SEC > 0 and (now - created_at) > _ANALYSIS_CACHE_TTL_SEC:
            # Expired
            try:
                del _analysis_cache[key]
            except KeyError:
                pass
            _analysis_cache_metrics["analysis_cache_misses"] += 1
            return None

        # LRU refresh
        _analysis_cache.move_to_end(key)
        _analysis_cache_metrics["analysis_cache_hits"] += 1
        return result


def _analysis_cache_put(key: str, result: Any) -> None:
    now = time.time()
    with _analysis_cache_lock:
        _analysis_cache[key] = (now, result)
        _analysis_cache.move_to_end(key)

        # Enforce max size
        while (
            _ANALYSIS_CACHE_MAX_ENTRIES > 0 and len(_analysis_cache) > _ANALYSIS_CACHE_MAX_ENTRIES
        ):
            _analysis_cache.popitem(last=False)
            _analysis_cache_metrics["analysis_cache_evictions"] += 1


def reset_analysis_cache() -> None:
    """Clear the in-process UltraBERT analysis cache.

    Intended for tests and diagnostics.
    """
    with _analysis_cache_lock:
        _analysis_cache.clear()
    for k in list(_analysis_cache_metrics.keys()):
        _analysis_cache_metrics[k] = 0


def get_analysis_cache_metrics() -> dict[str, int]:
    """Return cache metrics counters (best-effort)."""
    return dict(_analysis_cache_metrics)


def _get_full_analysis_result(text: str) -> Any | None:
    """Get a full UltraBERT analysis result, optionally via single-pass cache."""
    client = get_ultrabert_client()
    if client is None:
        return None

    if not _is_single_pass_enabled():
        # Legacy: callers will invoke client.analyze with specific capabilities.
        return None

    key = _analysis_cache_key(text)
    cached = _analysis_cache_get(key)
    if cached is not None:
        return cached

    # Cache miss: run ONE full forward pass
    try:
        _analysis_cache_metrics["analysis_single_pass_calls"] += 1
        result = client.analyze(text)  # all capabilities
        _analysis_cache_put(key, result)
        return result
    except Exception as e:
        logger.error(f"UltraBERT full analysis failed: {e}")
        return None


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
# Entity Filtering Configuration
# ============================================================================

# Minimum entity text length after stripping punctuation/whitespace
ENTITY_MIN_LENGTH = int(os.getenv("K0_ENTITY_MIN_LENGTH", "3"))

# Minimum confidence threshold for extracted entities (0.0-1.0)
ENTITY_MIN_CONFIDENCE = float(os.getenv("K0_ENTITY_MIN_CONFIDENCE", "0.65"))

# Stop words to filter out - common words that are not meaningful entities
ENTITY_STOP_WORDS: frozenset[str] = frozenset(
    {
        # Articles and determiners
        "a",
        "an",
        "the",
        "this",
        "that",
        "these",
        "those",
        # Prepositions
        "at",
        "by",
        "for",
        "from",
        "in",
        "of",
        "on",
        "to",
        "with",
        "about",
        "after",
        "before",
        "between",
        "into",
        "through",
        "during",
        "under",
        "over",
        "above",
        "below",
        "up",
        "down",
        "out",
        "off",
        "away",
        # Conjunctions
        "and",
        "or",
        "but",
        "nor",
        "so",
        "yet",
        "both",
        "either",
        "neither",
        # Pronouns
        "i",
        "me",
        "my",
        "mine",
        "we",
        "us",
        "our",
        "ours",
        "you",
        "your",
        "yours",
        "he",
        "him",
        "his",
        "she",
        "her",
        "hers",
        "it",
        "its",
        "they",
        "them",
        "their",
        "theirs",
        "who",
        "whom",
        "whose",
        # Common verbs
        "is",
        "am",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "can",
        "shall",
        # Adverbs
        "very",
        "really",
        "just",
        "also",
        "too",
        "only",
        "even",
        "still",
        # Misc fragments
        "day",
        "day of",
        "time",
        "place",
        "way",
        "thing",
        "things",
        "some",
        "any",
        "all",
        "each",
        "every",
        "no",
        "not",
        "none",
        # Punctuation-only (should be caught by length filter too)
        ".",
        ",",
        "!",
        "?",
        ";",
        ":",
        "-",
        "'",
        '"',
        "(",
        ")",
        "[",
        "]",
    }
)


def _clean_entity_text(text: str) -> str:
    """Strip leading/trailing punctuation and whitespace from entity text."""
    import string

    # Strip whitespace first
    text = text.strip()
    # Strip common punctuation from both ends
    punct_chars = string.punctuation + "''" "—–"
    return text.strip(punct_chars).strip()


def _is_complete_word(entity_text: str, source_text: str) -> bool:
    """Check if entity appears as a complete word in source text.

    This robustly filters sub-word tokenization artifacts like:
    - "Chipot" from "Chipotle"
    - "Fur" from "Für Elise"
    - "San" from "San Francisco" (when extracted alone)

    Returns True if entity appears with word boundaries (whitespace/punctuation/start/end).
    """
    import re

    if not entity_text or not source_text:
        return True  # Can't validate, assume ok

    # Escape special regex chars and match as whole word
    # \b matches word boundaries (between \w and \W)
    pattern = r"\b" + re.escape(entity_text) + r"\b"
    return bool(re.search(pattern, source_text, re.IGNORECASE))


def _is_valid_entity(text: str, confidence: float, source_text: str | None = None) -> bool:
    """Check if entity passes quality filters.

    Filters:
    1. Minimum length (default 3 chars after cleaning)
    2. Not a common stop word
    3. Minimum confidence threshold
    4. Not pure punctuation/numbers
    5. Must be a complete word in source (not a sub-word fragment)
    """
    cleaned = _clean_entity_text(text)

    # Length check
    if len(cleaned) < ENTITY_MIN_LENGTH:
        return False

    # Stop word check (case-insensitive) - keep minimal set
    if cleaned.lower() in ENTITY_STOP_WORDS:
        return False

    # Confidence check
    if confidence < ENTITY_MIN_CONFIDENCE:
        return False

    # Must contain at least one letter
    if not any(c.isalpha() for c in cleaned):
        return False

    # Word boundary check - reject sub-word fragments
    if source_text and not _is_complete_word(cleaned, source_text):
        return False

    return True


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
        import torch
        from familyos_ultrabert import Client

        # Use the Client class from v2.1.0 - it handles warmup and provides
        # clean attribute access (result.sentiment, result.safety, etc.)
        # PyTorch nightly cu128 supports Blackwell (sm_100, sm_120)
        backend = "auto"  # Let it auto-detect: PyTorch+CUDA if available, else ONNX
        if torch.cuda.is_available():
            arch_list = torch.cuda.get_arch_list()
            logger.info(f"CUDA available, arch_list: {arch_list}")
            if "sm_120" in arch_list or "sm_100" in arch_list:
                backend = "pytorch"  # Force PyTorch for Blackwell GPUs
                logger.info("Blackwell GPU detected, using PyTorch backend")

        logger.info(f"Loading FamilyOS UltraBERT Client with backend={backend}...")
        client = Client(
            backend=backend,
            warmup=True,
            warmup_rounds=2,
            verbose=False,
        )
        _maybe_full_warmup(client)

        logger.info(
            "UltraBERT loaded successfully",
            extra={
                "version": client.VERSION,
                "backend": client.backend,
                "capabilities": len(client.capabilities),
            },
        )
        return client

    except ImportError as e:
        logger.warning(f"familyos_ultrabert not installed: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to load UltraBERT: {e}")
        return None


# NOTE: _UltraBERTClientWrapper and _AnalysisResultWrapper classes removed
# The familyos_ultrabert.Client class (v2.1.0) provides all the attribute-style
# access we need (result.sentiment, result.safety, result.emotions, etc.)
# See client.py in the wheel for the full API.


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
            import torch
            from familyos_ultrabert import Client

            backend = "auto"
            if torch.cuda.is_available():
                try:
                    arch_list = torch.cuda.get_arch_list()
                except Exception:
                    arch_list = []
                if "sm_120" in arch_list or "sm_100" in arch_list:
                    backend = "pytorch"

            logger.info("Initializing FamilyOS UltraBERT client...")
            _ultrabert_client = Client(
                backend=backend,
                warmup=warmup,
                warmup_rounds=warmup_rounds,
                verbose=False,
            )

            _maybe_full_warmup(_ultrabert_client)
            logger.info(
                "UltraBERT client initialized",
                extra={
                    "version": getattr(_ultrabert_client, "VERSION", "unknown"),
                    "backend": getattr(_ultrabert_client, "backend", "unknown"),
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
        # Prefer a single full-pass result (cached) to avoid repeated inference.
        result = _get_full_analysis_result(text)
        if result is None:
            # Legacy fallback: capability-scoped call
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
        # Prefer cached full-pass result.
        result = _get_full_analysis_result(text)
        if result is None:
            result = client.analyze(
                text,
                capabilities=["ner_family", "ner_general"],
            )

        entities = []

        # Process family entities with filtering
        for ent in result.entities:
            raw_text = ent.get("text", "")
            confidence = ent.get("confidence", 0.8)

            if not _is_valid_entity(raw_text, confidence, source_text=text):
                continue

            cleaned_text = _clean_entity_text(raw_text)
            entities.append(
                EntityResult(
                    text=cleaned_text,
                    label=ent.get("label", "UNKNOWN"),
                    start=ent.get("start", ent.get("start_token", 0)),
                    end=ent.get("end", ent.get("end_token", 0)),
                    confidence=confidence,
                    source="ultrabert_family",
                )
            )

        # Process general entities with filtering
        for ent in result.general_entities:
            raw_text = ent.get("text", "")
            confidence = ent.get("confidence", 0.8)

            if not _is_valid_entity(raw_text, confidence, source_text=text):
                continue

            cleaned_text = _clean_entity_text(raw_text)
            entities.append(
                EntityResult(
                    text=cleaned_text,
                    label=ent.get("label", "UNKNOWN"),
                    start=ent.get("start", ent.get("start_token", 0)),
                    end=ent.get("end", ent.get("end_token", 0)),
                    confidence=confidence,
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
        # Prefer cached full-pass result.
        result = _get_full_analysis_result(text)
        if result is None:
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
        # Prefer cached full-pass result.
        result = _get_full_analysis_result(text)
        if result is None:
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
        # Prefer cached full-pass result.
        result = _get_full_analysis_result(text)
        if result is None:
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
        result = _get_full_analysis_result(text)
        if result is None:
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


def extract_ner_for_storage(text: str) -> dict[str, Any]:
    """
    Extract UltraBERT outputs in format suitable for st_hipp_events storage.

    Returns the raw UltraBERT output from all heads in a format
    that can be stored in st_hipp_events columns.

    Issue: 4.4.1 - P02 stores raw output, P03 R4 processes it.
    Issue: 0053 - Full UltraBERT capability storage (relations, safety, nli)

    Args:
        text: Input text to analyze.

    Returns:
        Dict with:
            - ner_entities_json: Merged ner_family + ner_general entities
            - temporal_json: Temporal expressions from temporal head
            - intent_category: User intent classification
            - ingress_category: Routing category
            - ultrabert_version: Model version used
            - extracted_relations_json: Relationship types (parent_of, spouse_of, etc.)
            - safety_familyos_band: Safety band (GREEN/AMBER/RED/CRISIS)
            - safety_familyos_subcategory: Detailed safety subcategory
            - nli_label: NLI result (entailment/neutral/contradiction)
            - nli_confidence: NLI confidence score
            - sentiment_confidence: Sentiment confidence score
    """
    import json

    client = get_ultrabert_client()
    if client is None:
        return {
            "ner_entities_json": "[]",
            "temporal_json": "[]",
            "intent_category": None,
            "ingress_category": None,
            "ultrabert_version": None,
            "extracted_relations_json": "[]",
            "safety_familyos_band": None,
            "safety_familyos_subcategory": None,
            "nli_label": None,
            "nli_confidence": None,
            "sentiment_confidence": None,
        }

    try:
        result = _get_full_analysis_result(text)
        if result is None:
            result = client.analyze(text)

        # Build NER entities JSON (ner_family + ner_general merged)
        # Apply the same quality filtering as extract_entities()
        # This format matches what UltraBERTEntityExtractor expects
        filtered_family = []
        for ent in result.entities or []:
            raw_text = ent.get("text", "")
            confidence = ent.get("confidence", 0.8)
            if _is_valid_entity(raw_text, confidence, source_text=text):
                ent_copy = dict(ent)
                ent_copy["text"] = _clean_entity_text(raw_text)
                filtered_family.append(ent_copy)

        filtered_general = []
        for ent in result.general_entities or []:
            raw_text = ent.get("text", "")
            confidence = ent.get("confidence", 0.8)
            if _is_valid_entity(raw_text, confidence, source_text=text):
                ent_copy = dict(ent)
                ent_copy["text"] = _clean_entity_text(raw_text)
                filtered_general.append(ent_copy)

        ner_entities = {
            "ner_family": {"entities": filtered_family},
            "ner_general": {"entities": filtered_general},
        }

        # Build temporal JSON
        temporal = {"entities": result.temporal or []}

        # Extract relations (new in migration 0053)
        # UltraBERT returns list like ["parent_of"] or ["spouse_of", "caretaker_of"]
        relations = getattr(result, "relations", []) or []

        # Extract safety band and subcategory (new in migration 0053)
        # safety_familyos returns GREEN/AMBER/RED/CRISIS
        safety_band = getattr(result, "safety", None)
        safety_subcategory = getattr(result, "safety_subcategory", None)

        # Extract NLI (new in migration 0053)
        nli_label = getattr(result, "nli", None)
        nli_confidence = getattr(result, "nli_confidence", None)

        # Sentiment confidence
        sentiment_confidence = getattr(result, "sentiment_confidence", None)

        return {
            "ner_entities_json": json.dumps(ner_entities),
            "temporal_json": json.dumps(temporal),
            "intent_category": result.intent,
            "ingress_category": result.ingress,
            "ultrabert_version": getattr(client, "VERSION", "2.1.0"),
            # New fields from migration 0053
            "extracted_relations_json": json.dumps(relations),
            "safety_familyos_band": safety_band,
            "safety_familyos_subcategory": safety_subcategory,
            "nli_label": nli_label,
            "nli_confidence": nli_confidence,
            "sentiment_confidence": sentiment_confidence,
        }

    except Exception as e:
        logger.error(f"UltraBERT NER extraction for storage failed: {e}")
        return {
            "ner_entities_json": "[]",
            "temporal_json": "[]",
            "intent_category": None,
            "ingress_category": None,
            "ultrabert_version": None,
            "extracted_relations_json": "[]",
            "safety_familyos_band": None,
            "safety_familyos_subcategory": None,
            "nli_label": None,
            "nli_confidence": None,
            "sentiment_confidence": None,
        }
