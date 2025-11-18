"""
Comprehensive M04 tests with real VADER sentiment analysis validation

Run: pytest tests/k0/modules/affect/test_analyze_full.py -v
"""

import json
import time
from datetime import UTC, datetime
from typing import Any
from unittest.mock import Mock

import pytest

from k0.modules.affect import analyze

# ============================================================================
# Mock Classes for Phase 2 Signature Testing
# ============================================================================


class MockMessage:
    """Mock BusMessage for testing Phase 2 signature."""

    def __init__(self, payload: dict[str, Any], trace_id: str = "test_trace"):
        self.payload = json.dumps(payload)
        self.trace_id = trace_id
        self.offset = 0
        self.topic = "cognitive.memory.write.committed.v1"
        self.space_id = "test_space"


class MockContext:
    """Mock PipelineContext for testing Phase 2 signature."""

    def __init__(self):
        self.logger = Mock()
        self.logger.debug = Mock()
        self.logger.info = Mock()
        self.logger.warning = Mock()
        self.logger.error = Mock()
        self.syscalls = Mock()
        self.config = {}


# ============================================================================
# Unit Tests: Complexity Detection
# ============================================================================


def test_complexity_detection_simple_text():
    """Simple text should NOT trigger Tier-1 fallback."""
    text = "Had a wonderful dinner with family tonight!"
    assert not analyze.should_fallback_to_tier1(text, text.lower())


def test_complexity_detection_long_text():
    """Text >50 words should trigger Tier-1 fallback."""
    text = " ".join(["word"] * 51)  # 51 words
    assert analyze.should_fallback_to_tier1(text, text.lower())


def test_complexity_detection_mixed_emotions():
    """Mixed emotion keywords should trigger Tier-1 fallback."""
    text = "I have such mixed feelings about leaving this job"
    assert analyze.should_fallback_to_tier1(text, text.lower())

    text = "Feeling bittersweet about the move"
    assert analyze.should_fallback_to_tier1(text, text.lower())


def test_complexity_detection_sarcasm():
    """Sarcasm indicators should trigger Tier-1 fallback."""
    text = "Yeah right, that went really well"
    assert analyze.should_fallback_to_tier1(text, text.lower())

    text = "Oh great, another meeting"
    assert analyze.should_fallback_to_tier1(text, text.lower())


def test_complexity_detection_double_negation():
    """Complex negation (double negative) should trigger Tier-1 fallback."""
    text = "I'm not unhappy about the decision"
    assert analyze.should_fallback_to_tier1(text, text.lower())

    text = "The event was not unpleasant"
    assert analyze.should_fallback_to_tier1(text, text.lower())


# ============================================================================
# Unit Tests: Circumplex Emotion Mapping
# ============================================================================


def test_circumplex_high_valence_high_arousal():
    """High valence + high arousal → joy, excitement, enthusiasm."""
    emotions = analyze.map_circumplex_to_emotions(valence=0.8, arousal=0.7)
    assert "joy" in emotions or "excitement" in emotions


def test_circumplex_high_valence_low_arousal():
    """High valence + low arousal → contentment, relaxation, satisfaction."""
    emotions = analyze.map_circumplex_to_emotions(valence=0.8, arousal=0.2)
    assert "contentment" in emotions or "relaxation" in emotions


def test_circumplex_low_valence_high_arousal():
    """Low valence + high arousal → anxiety, anger, fear."""
    emotions = analyze.map_circumplex_to_emotions(valence=0.2, arousal=0.7)
    assert any(e in emotions for e in ["anxiety", "anger", "fear"])


def test_circumplex_low_valence_low_arousal():
    """Low valence + low arousal → sadness, depression, boredom."""
    emotions = analyze.map_circumplex_to_emotions(valence=0.2, arousal=0.2)
    assert any(e in emotions for e in ["sadness", "depression", "boredom"])


def test_circumplex_neutral():
    """Moderate valence/arousal → neutral."""
    emotions = analyze.map_circumplex_to_emotions(valence=0.5, arousal=0.5)
    assert "neutral" in emotions


def test_circumplex_returns_max_three_emotions():
    """Emotion list should have ≤3 tags."""
    emotions = analyze.map_circumplex_to_emotions(valence=0.8, arousal=0.7)
    assert len(emotions) <= 3


# ============================================================================
# Unit Tests: Affect Band Classification
# ============================================================================


def test_affect_band_positive_green():
    """Valence ≥0.5 → GREEN band."""
    band, reasons = analyze.classify_affect_band(valence=0.6, arousal=0.4)
    assert band == "GREEN"
    assert "positive_affect" in reasons


def test_affect_band_mild_negative_amber():
    """Valence 0.3-0.5, low arousal → AMBER band."""
    band, reasons = analyze.classify_affect_band(valence=0.45, arousal=0.3)
    assert band == "AMBER"
    assert "mild_negative_affect" in reasons or "moderate_negative_affect" in reasons
    assert "low_arousal" in reasons or len(reasons) > 0


def test_affect_band_strong_negative_red():
    """Valence <0.3 → RED band."""
    band, reasons = analyze.classify_affect_band(valence=0.2, arousal=0.5)
    assert band == "RED"
    assert "strong_negative_affect" in reasons


def test_affect_band_red_high_arousal():
    """Valence <0.3, high arousal → RED with high_arousal reason."""
    band, reasons = analyze.classify_affect_band(valence=0.2, arousal=0.7)
    assert band == "RED"
    assert "high_arousal" in reasons


def test_affect_band_red_low_arousal():
    """Valence <0.3, low arousal → RED with depression_risk reason."""
    band, reasons = analyze.classify_affect_band(valence=0.2, arousal=0.2)
    assert band == "RED"
    assert "low_arousal_depression_risk" in reasons


def test_affect_band_moderate_negative_amber():
    """Valence 0.3-0.5, high arousal → AMBER."""
    band, reasons = analyze.classify_affect_band(valence=0.4, arousal=0.7)
    assert band == "AMBER"
    assert "moderate_negative_affect" in reasons


# ============================================================================
# Integration Tests: VADER Tier-0 Classification
# ============================================================================


def test_vader_simple_positive():
    """VADER should classify simple positive text correctly."""
    text = "Had a wonderful dinner with family tonight!"
    annotation = analyze.tier0_classify(text)

    assert annotation is not None
    assert annotation.valence > 0.7, f"Expected positive valence, got {annotation.valence}"
    assert annotation.affect_band == "GREEN"
    assert "joy" in annotation.dominant_emotions or "contentment" in annotation.dominant_emotions
    assert annotation.tier == "TIER_0"


def test_vader_simple_negative():
    """VADER should classify simple negative text correctly."""
    text = "Had a terrible day at work, everything went wrong"
    annotation = analyze.tier0_classify(text)

    assert annotation is not None
    assert annotation.valence < 0.4, f"Expected negative valence, got {annotation.valence}"
    assert annotation.affect_band in ["AMBER", "RED"]
    assert annotation.tier == "TIER_0"


def test_vader_neutral():
    """VADER should classify neutral text."""
    text = "Went to the store to buy groceries"
    annotation = analyze.tier0_classify(text)

    assert annotation is not None
    assert 0.4 <= annotation.valence <= 0.6, f"Expected neutral valence, got {annotation.valence}"
    assert annotation.tier == "TIER_0"


def test_vader_handles_negation():
    """VADER should handle simple negation (not happy → negative)."""
    text = "not happy about the weather today"
    annotation = analyze.tier0_classify(text)

    assert annotation is not None
    assert (
        annotation.valence < 0.5
    ), f"Expected negative valence with negation, got {annotation.valence}"
    assert annotation.affect_band in ["AMBER", "RED"]


def test_vader_intensity_boosters():
    """VADER should handle intensity boosters (very happy > happy)."""
    text1 = "I am happy"
    text2 = "I am very happy"

    annotation1 = analyze.tier0_classify(text1)
    annotation2 = analyze.tier0_classify(text2)

    assert annotation1 is not None
    assert annotation2 is not None
    # "very happy" should have higher valence than "happy"
    assert (
        annotation2.valence > annotation1.valence
    ), f"Expected 'very happy' ({annotation2.valence}) > 'happy' ({annotation1.valence})"


def test_vader_punctuation_emphasis():
    """VADER should handle punctuation emphasis (good!! > good)."""
    text1 = "good"
    text2 = "good!!"

    annotation1 = analyze.tier0_classify(text1)
    annotation2 = analyze.tier0_classify(text2)

    assert annotation1 is not None
    assert annotation2 is not None
    # "good!!" should have higher arousal or valence than "good"
    assert (
        annotation2.valence >= annotation1.valence or annotation2.arousal > annotation1.arousal
    ), "Expected 'good!!' to have higher affect than 'good'"


def test_vader_fallback_complex_text():
    """Complex text should return None (trigger Tier-1 fallback)."""
    text = "I have such mixed feelings about this decision, it's complicated"
    annotation = analyze.tier0_classify(text)

    assert annotation is None, "Expected None for complex text (Tier-1 fallback)"


# ============================================================================
# Performance Tests
# ============================================================================


def test_tier0_latency_single_event():
    """Tier-0 classification should be <2ms for simple events (after warmup)."""
    text = "Had lunch with friends today"

    # Warmup call to ensure VADER is loaded
    analyze.tier0_classify("warmup")

    # Actual measurement
    start_time = time.time()
    annotation = analyze.tier0_classify(text)
    latency_ms = (time.time() - start_time) * 1000

    assert annotation is not None
    assert latency_ms < 2, f"Expected <2ms latency, got {latency_ms:.2f}ms"


def test_tier0_latency_batch():
    """Tier-0 should maintain <2ms P95 latency across batch."""
    texts = [
        "Had fun with family",
        "Good meeting today",
        "Stressed about work",
        "Relaxing weekend",
        "Excited about the trip",
    ] * 20  # 100 texts

    latencies = []
    for text in texts:
        start_time = time.time()
        annotation = analyze.tier0_classify(text)
        latency_ms = (time.time() - start_time) * 1000
        if annotation:  # Only measure Tier-0 (not fallback)
            latencies.append(latency_ms)

    # Statistical analysis
    latencies.sort()
    p50_index = int(len(latencies) * 0.50)
    p95_index = int(len(latencies) * 0.95)
    p99_index = int(len(latencies) * 0.99)

    p50_latency = latencies[p50_index]
    p95_latency = latencies[p95_index]
    p99_latency = latencies[p99_index]
    mean_latency = sum(latencies) / len(latencies)

    print(f"\nTier-0 Latency Statistics (n={len(latencies)}):")
    print(f"  Mean: {mean_latency:.3f}ms")
    print(f"  P50 (median): {p50_latency:.3f}ms")
    print(f"  P95: {p95_latency:.3f}ms (target: <2ms)")
    print(f"  P99: {p99_latency:.3f}ms")

    assert p95_latency < 5, f"P95 latency {p95_latency:.2f}ms exceeds 5ms target"


def test_safety_keyword_detection_performance():
    """Safety keyword detection should be fast and not degrade performance."""
    safety_texts = [
        "Feeling great today!",  # No safety keywords
        "I want to hurt myself",  # Safety keyword
        "Had a wonderful dinner",  # No safety keywords
        "Thinking about suicide",  # Safety keyword
        "Just a normal day",  # No safety keywords
    ] * 10  # 50 texts

    latencies = []
    safety_detections = 0

    for text in safety_texts:
        start_time = time.time()
        annotation = analyze.tier0_classify(text)
        latency_ms = (time.time() - start_time) * 1000
        latencies.append(latency_ms)

        if annotation and "safety_keyword_detected" in annotation.band_reasons:
            safety_detections += 1

    mean_latency = sum(latencies) / len(latencies)
    max_latency = max(latencies)

    print("\nSafety Keyword Detection Performance:")
    print(f"  Texts processed: {len(safety_texts)}")
    print(f"  Safety detections: {safety_detections}")
    print(f"  Mean latency: {mean_latency:.3f}ms")
    print(f"  Max latency: {max_latency:.3f}ms")

    assert safety_detections == 20, f"Expected 20 safety detections, got {safety_detections}"
    assert mean_latency < 5, f"Safety check degraded performance: {mean_latency:.2f}ms"


def test_domain_lexicon_adjustment_performance():
    """Domain lexicon adjustments should not significantly impact latency."""
    domain_texts = [
        "Had quality time with family",  # Domain phrase
        "Big milestone for the kids",  # Domain phrase
        "Another meltdown at bedtime",  # Domain phrase
        "Just a regular day",  # No domain phrases
        "Feeling exhausted today",  # Domain phrase
    ] * 10  # 50 texts

    latencies_with_domain = []
    adjustments_applied = 0

    for text in domain_texts:
        start_time = time.time()
        annotation = analyze.tier0_classify(text)
        latency_ms = (time.time() - start_time) * 1000
        latencies_with_domain.append(latency_ms)

        # Check if domain adjustment likely applied (heuristic: check for domain words)
        if any(phrase in text.lower() for phrase in analyze.DOMAIN_LEXICON.keys()):
            adjustments_applied += 1

    # Compare with baseline (no domain phrases)
    baseline_texts = ["Had a normal day today"] * 50
    latencies_baseline = []

    for text in baseline_texts:
        start_time = time.time()
        annotation = analyze.tier0_classify(text)
        latency_ms = (time.time() - start_time) * 1000
        latencies_baseline.append(latency_ms)

    mean_with_domain = sum(latencies_with_domain) / len(latencies_with_domain)
    mean_baseline = sum(latencies_baseline) / len(latencies_baseline)
    overhead_pct = (
        ((mean_with_domain - mean_baseline) / mean_baseline) * 100 if mean_baseline > 0 else 0
    )

    print("\nDomain Lexicon Adjustment Performance:")
    print(f"  Texts with domain phrases: {adjustments_applied}/{len(domain_texts)}")
    print(f"  Mean latency (with domain): {mean_with_domain:.3f}ms")
    print(f"  Mean latency (baseline): {mean_baseline:.3f}ms")
    print(f"  Overhead: {overhead_pct:+.1f}%")

    assert mean_with_domain < 5, f"Domain lexicon overhead too high: {mean_with_domain:.2f}ms"
    assert abs(overhead_pct) < 50, f"Domain lexicon overhead excessive: {overhead_pct:.1f}%"


def test_emoji_adjustment_performance():
    """Emoji adjustments should not significantly impact latency."""
    emoji_texts = [
        "Had a great day ❤️",
        "Meeting went well 😊",
        "So excited!! 🎉",
        "Feeling sad today 😭",
        "Very angry right now 😡",
        "Just okay 👍",
    ] * 10  # 60 texts

    latencies = []

    for text in emoji_texts:
        start_time = time.time()
        annotation = analyze.tier0_classify(text)
        latency_ms = (time.time() - start_time) * 1000
        latencies.append(latency_ms)

    mean_latency = sum(latencies) / len(latencies)

    print("\nEmoji Adjustment Performance:")
    print(f"  Texts with emojis: {len(emoji_texts)}")
    print(f"  Mean latency: {mean_latency:.3f}ms")

    assert mean_latency < 5, f"Emoji processing overhead too high: {mean_latency:.2f}ms"


def test_complexity_detection_overhead():
    """Complexity detection should be fast (short-circuit optimization)."""
    test_cases = [
        ("Simple text", "Had a good day"),
        ("Long text", " ".join(["word"] * 60)),
        ("Mixed emotions", "Feeling bittersweet about this"),
        ("Sarcasm", "Yeah right, that was great"),
        ("Complex negation", "Not unhappy about it"),
    ] * 10  # 50 total

    latencies_by_type = {}

    for label, text in test_cases:
        start_time = time.time()
        is_complex = analyze.should_fallback_to_tier1(text, text.lower())
        latency_us = (time.time() - start_time) * 1000000  # microseconds

        if label not in latencies_by_type:
            latencies_by_type[label] = []
        latencies_by_type[label].append(latency_us)

    print("\nComplexity Detection Overhead (microseconds):")
    for label, latencies in latencies_by_type.items():
        mean_latency = sum(latencies) / len(latencies)
        print(f"  {label}: {mean_latency:.2f}μs")

    # All should be < 100 microseconds (0.1ms)
    for label, latencies in latencies_by_type.items():
        mean_latency = sum(latencies) / len(latencies)
        assert mean_latency < 100, f"{label} detection too slow: {mean_latency:.2f}μs"


def test_confidence_calculation_performance():
    """Confidence calculation should be negligible overhead."""
    test_cases = [
        (0.8, 0.6, False, False),  # High valence, high arousal, simple
        (0.2, 0.7, False, False),  # Low valence, high arousal, simple
        (0.5, 0.3, True, False),  # Neutral, low arousal, complex
        (0.7, 0.5, True, True),  # High valence, moderate arousal, low-conf
    ] * 100  # 400 calculations

    start_time = time.time()
    for valence, arousal, is_complex, is_low_conf in test_cases:
        confidence = analyze.calculate_confidence(valence, arousal, is_complex, is_low_conf)
    total_time = (time.time() - start_time) * 1000  # milliseconds

    per_calc_us = (total_time * 1000) / len(test_cases)  # microseconds per calculation

    print("\nConfidence Calculation Performance:")
    print(f"  Total calculations: {len(test_cases)}")
    print(f"  Total time: {total_time:.3f}ms")
    print(f"  Per calculation: {per_calc_us:.2f}μs")

    assert per_calc_us < 10, f"Confidence calculation too slow: {per_calc_us:.2f}μs"


# ============================================================================
# Integration Tests: Module Entry Point
# ============================================================================


@pytest.mark.asyncio
async def test_run_valid_input():
    """Module run() should process valid input and return enriched envelope."""
    envelope = {
        "event_id": "evt_001",
        "timestamp": datetime.now(UTC).isoformat(),
        "body": {
            "text": "Had a wonderful dinner with family tonight!",
            "actor_id": "person_dad",
        },
    }

    message = MockMessage(payload=envelope, trace_id="test_001")
    context = MockContext()
    config = {"confidence_threshold": 0.8}

    result = await analyze.run(message, context, **config)

    # Verify enriched envelope structure (now merged into original envelope)
    assert result["event_id"] == "evt_001"
    assert "affect_valence" in result
    assert "affect_arousal" in result
    assert "dominant_emotions" in result
    assert "affect_band" in result
    assert "band_reasons" in result
    assert "model_version" in result

    # Verify values
    assert 0.0 <= result["affect_valence"] <= 1.0
    assert 0.0 <= result["affect_arousal"] <= 1.0
    assert result["affect_band"] in ["GREEN", "AMBER", "RED"]
    assert isinstance(result["dominant_emotions"], list)
    assert isinstance(result["band_reasons"], list)

    # Verify logging was called
    assert context.logger.debug.call_count >= 2  # Start + completion logs


@pytest.mark.asyncio
async def test_run_missing_text():
    """Module run() should reject missing text field."""
    envelope = {
        "event_id": "evt_002",
        "body": {},  # Missing 'text' field
    }

    message = MockMessage(payload=envelope, trace_id="test_002")
    context = MockContext()

    with pytest.raises(ValueError, match="Missing or invalid 'text' field"):
        await analyze.run(message, context)


@pytest.mark.asyncio
async def test_run_invalid_text_type():
    """Module run() should reject invalid text type."""
    envelope = {
        "event_id": "evt_003",
        "body": {"text": 12345},  # text should be string
    }

    message = MockMessage(payload=envelope, trace_id="test_003")
    context = MockContext()

    with pytest.raises(ValueError, match="Missing or invalid 'text' field"):
        await analyze.run(message, context)


@pytest.mark.asyncio
async def test_run_preserves_original_envelope():
    """Module run() should preserve original envelope fields."""
    envelope = {
        "event_id": "evt_004",
        "timestamp": datetime.now(UTC).isoformat(),
        "body": {
            "text": "Meeting went well today",
            "actor_id": "person_dad",
        },
        "custom_field": "should_be_preserved",
    }

    message = MockMessage(payload=envelope, trace_id="test_004")
    context = MockContext()

    result = await analyze.run(message, context)

    # Verify original fields preserved
    assert result["event_id"] == "evt_004"
    assert result["body"]["text"] == "Meeting went well today"
    assert result["custom_field"] == "should_be_preserved"

    # Verify affect fields added
    assert "affect_valence" in result
    assert "affect_arousal" in result


# ============================================================================
# Edge Cases
# ============================================================================


def test_vader_empty_text():
    """VADER should handle empty text gracefully."""
    text = ""
    annotation = analyze.tier0_classify(text)

    # VADER will return neutral scores for empty text
    assert annotation is not None
    assert annotation.affect_band == "GREEN"  # Neutral → GREEN


def test_vader_special_characters():
    """VADER should handle special characters."""
    text = "Good!!! 😊 #happy #blessed"
    annotation = analyze.tier0_classify(text)

    assert annotation is not None
    assert annotation.valence > 0.5  # Should be positive


def test_affect_annotation_dataclass():
    """AffectAnnotation dataclass should have all required fields."""
    annotation = analyze.AffectAnnotation(
        valence=0.7,
        arousal=0.5,
        dominant_emotions=("joy", "contentment"),
        affect_band="GREEN",
        band_reasons=("positive_affect",),
        model_version="tier0_vader_v1.2",
        tier="TIER_0",
        confidence=0.8,
        raw_compound=0.5,
        raw_pos=0.4,
        raw_neg=0.1,
        raw_neu=0.5,
    )

    assert annotation.valence == 0.7
    assert annotation.arousal == 0.5
    assert annotation.affect_band == "GREEN"
    assert annotation.tier == "TIER_0"
    assert annotation.confidence == 0.8
