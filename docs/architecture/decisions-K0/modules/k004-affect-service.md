---
adr_number: 'k004'
title: Affect Service Architecture - Emotional Classification System
status: ACCEPTED
date_created: '2025-11-16'
date_updated: '2025-11-16'
implementation_status: DESIGN
affected_layers:
  - k0_modules
  - k0_pipelines
  - k0_storage
affected_modules:
  - affect.analyze (M04)
authors:
  - K0 Architecture Team
concerns:
  - emotional_classification
  - valence_arousal_scoring
  - affect_band_classification
  - sentiment_analysis
  - two_tier_latency_strategy
  - neuroscience_inspired_design
propagation:
  affected_adrs:
    - k004.1-tier0-fast-affect
    - k004.2-multimodal-affect
    - k004.3-affect-learning-loop
  affected_contracts:
    - k0/contracts/modules/affect.analyze.v1.yaml
  affected_pipelines:
    - P02 (Write Pipeline)
    - P06 (Therapy/Journaling - future)
  affected_storage:
    - st_hipp_events.affect_valence
    - st_hipp_events.affect_arousal
    - st_hipp_events.dominant_emotions
    - st_hipp_events.affect_band
    - st_hipp_events.band_reasons
related_adrs:
  - k003 (Hippocampus Architecture)
  - ADR-P02 (Write Pipeline Architecture)
related_contracts:
  - k0/contracts/modules/affect.analyze.v1.yaml
  - k0/contracts/asyncapi.events.yaml
related_diagrams:
  - architecture_diagrams/k0/p02_write_driver_architecture.mmd
research_citations:
  - "Russell, J. A. (1980). A circumplex model of affect. Journal of Personality and Social Psychology, 39(6), 1161-1178"
  - "Ekman, P. (1992). An argument for basic emotions. Cognition & Emotion, 6(3-4), 169-200"
  - "LeDoux, J. E. (2000). Emotion circuits in the brain. Annual Review of Neuroscience, 23, 155-184"
  - "Barrett, L. F. (2017). How Emotions Are Made: The Secret Life of the Brain. Houghton Mifflin Harcourt"
  - "Hutto, C. J., & Gilbert, E. (2014). VADER: A Parsimonious Rule-Based Model for Sentiment Analysis. ICWSM"
---

# k004 - Affect Service Architecture (Emotional Classification System)

**Status**: ACCEPTED | **Module**: M04

---

## Executive Summary

**AffectService (M04)** classifies emotional content of episodic memories using a **two-tier latency strategy** inspired by the brain's dual-process emotion system (amygdala fast path + prefrontal slow path). This module enriches P02 write pipeline events with affect dimensions for salience scoring and memory consolidation.

**Key Design Points**:

1. **Two-Tier Latency Strategy**: Tier-0 (<2ms lexicon-based) handles 90% of events; Tier-1 (<60ms ML-based) for complex emotions
2. **Russell's Circumplex Model**: Valence (negative→positive) × Arousal (calm→excited) dimensional representation
3. **Affect Band Classification**: GREEN (safe) / AMBER (monitor) / RED (alert) risk-based classification
4. **Dominant Emotion Tags**: Discrete emotion labels (joy, sadness, anger, fear, surprise, disgust) derived from continuous dimensions
5. **Write-Path Optimized**: P95 ≤70ms to support P02's <100ms total latency budget

**Performance Budget**: P95 ≤70ms, P99 ≤100ms, Memory <20MB per tenant.

---

## Context

### The Emotion Classification Problem

Episodic memories have **emotional significance** that affects:

1. **Salience Scoring**: High-arousal emotions boost memory importance (e.g., "birthday party" more salient than "daily commute")
2. **Risk Assessment**: Negative affect may indicate distress requiring attention (e.g., therapy escalation)
3. **Memory Consolidation**: Emotional events are preferentially retained in long-term memory (P03 consolidation)
4. **User Experience**: Emotional context improves memory recall and journaling insights

Traditional sentiment analysis (positive/negative polarity) is **insufficient** because:

- **Lacks arousal dimension**: "contentment" (low arousal) vs. "excitement" (high arousal) both positive but different salience
- **Binary classification**: Cannot capture mixed emotions (e.g., "bittersweet farewell")
- **No risk assessment**: Cannot distinguish "mild disappointment" (AMBER) from "severe distress" (RED)

### Biological Inspiration: Dual-Process Emotion System

The brain processes emotions through **two parallel pathways**:

1. **Fast Path (Amygdala → Direct Response)**:
   - **Latency**: 20-50ms (subcortical, automatic)
   - **Function**: Rapid threat detection, emotional tagging
   - **Characteristics**: Low-resolution, pattern-matching (e.g., "snake-like shape")
   - **Analogous to**: Tier-0 lexicon-based classification (<2ms)

2. **Slow Path (Cortex → Deliberative Response)**:
   - **Latency**: 200-500ms (cortical, controlled)
   - **Function**: Contextual appraisal, nuanced emotion recognition
   - **Characteristics**: High-resolution, semantic understanding
   - **Analogous to**: Tier-1 transformer-based classification (<60ms)

Our **two-tier strategy** mimics this dual-process architecture:

- **Tier-0**: Fast lexicon lookup for common patterns (90% of events)
- **Tier-1**: ML-based deep analysis for complex emotional content (10% of events)

### Russell's Circumplex Model of Affect

Instead of discrete emotion categories, we use **dimensional representation**:

```
Arousal (Excited)
       |
   Angry | Excited
       |
-------+------- Valence
       |
    Sad | Calm
       |
Arousal (Calm)
```

**Dimensions**:

- **Valence** (x-axis): 0.0 (negative) → 1.0 (positive)
- **Arousal** (y-axis): 0.0 (calm) → 1.0 (excited)

**Advantages of Circumplex Model**:

- **Continuous representation**: Captures gradations (e.g., "mildly positive" = valence 0.6)
- **Mixed emotions**: Points between quadrants (e.g., "bittersweet" = valence 0.5, arousal 0.4)
- **Cultural generalizability**: Dimensions are universal; discrete categories vary by culture

**Mapping to Discrete Emotions** (for user-facing tags):

| Quadrant | Valence | Arousal | Emotions |
|----------|---------|---------|----------|
| High Valence, High Arousal | >0.6 | >0.6 | Joy, excitement, enthusiasm |
| High Valence, Low Arousal | >0.6 | <0.4 | Contentment, relaxation, satisfaction |
| Low Valence, High Arousal | <0.4 | >0.6 | Anger, anxiety, fear, frustration |
| Low Valence, Low Arousal | <0.4 | <0.4 | Sadness, boredom, depression |

### Performance Requirements

**Write-Path Latency Constraints** (from P02 dossier):

- **P02 total budget**: <100ms P95 (all modules combined)
- **Affect module allocation**: ≤70ms P95 (leaves headroom for other modules)
- **Tier-0 target**: <2ms (fast path for simple emotions)
- **Tier-1 target**: <60ms (ML fallback for complex emotions)

**Why 70ms Budget?**

| Component | Latency | Percentage |
|-----------|---------|------------|
| DG fingerprinting (k003.1) | 15ms | 15% |
| CA1 semantic projection (k003.2) | 20ms | 20% |
| Affect classification (k004) | 70ms | 70% |
| Space resolution | 3ms | 3% |
| Salience scoring | 5ms | 5% |
| **Total** | **113ms** | - |

Affect is the **slowest module** in P02 because ML inference is more expensive than hash computation or NER. Budget must be tight to keep P02 under 100ms P95.

### Why Not Full Transformer (e.g., BERT) for All Events?

Full transformer models (BERT, RoBERTa) provide **high accuracy** but:

- **Latency**: 200-500ms per event (blocks write path)
- **GPU dependency**: Requires GPU for acceptable latency (adds infrastructure cost)
- **Overkill for simple text**: "Had lunch with family" doesn't need deep contextual analysis

**Two-tier strategy** balances accuracy and latency:

- **90% of events** are routine ("meal", "work", "conversation") → Tier-0 lexicon sufficient
- **10% of events** have complex emotions ("mixed feelings about job offer") → Tier-1 ML needed

---

## Decision

### Component Architecture

**Module Path**: `k0/modules/affect/analyze.py`
**Contract**: `k0/contracts/modules/affect.analyze.v1.yaml`
**Pipeline Stage**: P02 Write Path (stage_20_affect_analyze)
**Latency Budget**: P95 ≤70ms, P99 ≤100ms

### Two-Tier Classification Strategy

#### Tier-0: Fast Lexicon-Based Path (<2ms)

**Trigger**: Text length <50 words AND no complex emotional keywords

**Algorithm**: VADER (Valence Aware Dictionary and sEntiment Reasoner)

```python
def tier0_classify(text: str) -> Optional[AffectAnnotation]:
    """
    Fast lexicon-based classification using VADER.
    Returns None if text too complex (fallback to Tier-1).
    """
    # Check complexity
    if len(text.split()) > 50:
        return None  # Too long, use Tier-1

    if contains_complex_emotions(text):  # e.g., "bittersweet", "ambivalent"
        return None  # Mixed emotions, use Tier-1

    # VADER sentiment scores
    vader_scores = vader_analyzer.polarity_scores(text)
    # vader_scores = {'neg': 0.2, 'neu': 0.5, 'pos': 0.3, 'compound': 0.5}

    # Map compound score to valence (0.0-1.0)
    valence = (vader_scores['compound'] + 1.0) / 2.0  # [-1,1] → [0,1]

    # Estimate arousal from emotional intensity
    arousal = vader_scores['pos'] + vader_scores['neg']  # Sum of emotional magnitude
    arousal = min(arousal, 1.0)  # Cap at 1.0

    # Derive dominant emotions from valence/arousal
    dominant_emotions = map_to_discrete_emotions(valence, arousal)

    # Affect band classification
    affect_band, band_reasons = classify_affect_band(valence, arousal)

    return AffectAnnotation(
        valence=valence,
        arousal=arousal,
        dominant_emotions=dominant_emotions,
        affect_band=affect_band,
        band_reasons=band_reasons,
        model_version="tier0_vader_v1.2",
        tier="TIER_0"
    )
```

**Advantages**:
- ✅ <2ms latency (pure lexicon lookup)
- ✅ No GPU required (CPU-only)
- ✅ Deterministic (same input → same output)

**Limitations**:
- ⚠️ Lower accuracy (~70-75% vs. 85-90% for transformers)
- ⚠️ Cannot handle negation well ("not happy" may score as positive)
- ⚠️ No contextual understanding ("sick trick" misclassified as negative)

#### Tier-1: ML-Based Path (<60ms)

**Trigger**: Tier-0 returns None (complex text or mixed emotions)

**Algorithm**: Distilled transformer (e.g., DistilBERT fine-tuned on emotion datasets)

```python
def tier1_classify(text: str) -> AffectAnnotation:
    """
    ML-based classification using distilled transformer.
    Slower but more accurate than Tier-0.
    """
    # Tokenize and truncate to 128 tokens (balance latency and context)
    inputs = tokenizer(text, truncation=True, max_length=128, return_tensors="pt")

    # Model inference (GPU-accelerated if available)
    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits

    # Predict valence and arousal (multi-output regression)
    valence = torch.sigmoid(logits[0, 0]).item()  # [0,1]
    arousal = torch.sigmoid(logits[0, 1]).item()  # [0,1]

    # Derive dominant emotions
    dominant_emotions = map_to_discrete_emotions(valence, arousal)

    # Affect band classification
    affect_band, band_reasons = classify_affect_band(valence, arousal)

    return AffectAnnotation(
        valence=valence,
        arousal=arousal,
        dominant_emotions=dominant_emotions,
        affect_band=affect_band,
        band_reasons=band_reasons,
        model_version="tier1_distilbert_v2.3",
        tier="TIER_1"
    )
```

**Advantages**:
- ✅ Higher accuracy (85-90% on complex emotions)
- ✅ Contextual understanding (handles negation, sarcasm better)
- ✅ Handles mixed emotions ("bittersweet")

**Limitations**:
- ⚠️ Slower (<60ms with GPU, 200-500ms without)
- ⚠️ GPU dependency for production latency
- ⚠️ Model drift over time (requires retraining)

### Affect Band Classification

**Purpose**: Risk-based triage for events requiring attention (e.g., therapy escalation)

**Bands**:

| Band | Definition | Valence Range | Arousal Range | Examples |
|------|------------|---------------|---------------|----------|
| **GREEN** | Positive or neutral affect, no risk | >0.5 | Any | "Enjoyed dinner with family", "Productive work meeting" |
| **AMBER** | Mild negative affect, worth monitoring | 0.3-0.5 | <0.6 | "Felt a bit stressed today", "Disappointed about cancellation" |
| **RED** | Strong negative affect, requires attention | <0.3 | >0.6 | "Very anxious about upcoming presentation", "Angry after argument" |

**Classification Logic**:

```python
def classify_affect_band(valence: float, arousal: float) -> Tuple[str, List[str]]:
    """
    Classify affect band based on valence and arousal thresholds.
    Returns (band, reasons).
    """
    reasons = []

    if valence >= 0.5:
        # Positive or neutral valence → GREEN
        return ("GREEN", ["positive_affect"])

    elif valence >= 0.3 and arousal < 0.6:
        # Mild negative affect, low arousal → AMBER
        reasons.append("mild_negative_affect")
        reasons.append("low_arousal")
        return ("AMBER", reasons)

    elif valence < 0.3 and arousal >= 0.6:
        # Strong negative affect, high arousal → RED
        reasons.append("strong_negative_affect")
        reasons.append("high_arousal")
        return ("RED", reasons)

    elif valence < 0.3 and arousal < 0.6:
        # Strong negative affect, low arousal (depression risk) → RED
        reasons.append("strong_negative_affect")
        reasons.append("low_arousal_depression_risk")
        return ("RED", reasons)

    else:
        # Moderate negative affect, moderate arousal → AMBER
        reasons.append("moderate_negative_affect")
        return ("AMBER", reasons)
```

**Use Cases**:

- **Salience scoring (P02)**: RED/AMBER events boost salience (emotionally significant)
- **Therapy escalation (P06)**: RED events trigger notifications to therapists
- **Retention policy (P03)**: RED events prioritized for long-term retention

### Performance Budget Breakdown

**Tier-0 Path** (90% of events):

| Step | Latency | Cumulative |
|------|---------|------------|
| Text preprocessing | 0.2ms | 0.2ms |
| VADER lexicon lookup | 1.0ms | 1.2ms |
| Valence/arousal mapping | 0.3ms | 1.5ms |
| Band classification | 0.2ms | 1.7ms |
| **Total** | **<2ms** | - |

**Tier-1 Path** (10% of events):

| Step | Latency | Cumulative |
|------|---------|------------|
| Text preprocessing | 0.5ms | 0.5ms |
| Tokenization | 2.0ms | 2.5ms |
| Model inference (GPU) | 50ms | 52.5ms |
| Valence/arousal extraction | 0.5ms | 53ms |
| Band classification | 0.2ms | 53.2ms |
| **Total** | **<60ms** | - |

**Weighted Average** (90% Tier-0, 10% Tier-1):

- (0.9 × 2ms) + (0.1 × 60ms) = **7.8ms P50**
- Worst case (Tier-1): **60ms P99**
- Target: **<70ms P95** ✅

### Output Schema

Columns added to `st_hipp_events`:

```sql
-- Affect classification columns (populated by M04 in P02)
affect_valence REAL NOT NULL,              -- 0.0 (negative) to 1.0 (positive)
affect_arousal REAL NOT NULL,              -- 0.0 (calm) to 1.0 (excited)
dominant_emotions JSONB NOT NULL,          -- Array of emotion tags, e.g., ["joy", "contentment"]
affect_band TEXT NOT NULL,                 -- GREEN / AMBER / RED
band_reasons JSONB NOT NULL,               -- Explanation array, e.g., ["positive_affect"]
affect_model_version TEXT NOT NULL         -- e.g., "tier0_vader_v1.2" or "tier1_distilbert_v2.3"

-- Example row:
-- affect_valence: 0.82 (positive)
-- affect_arousal: 0.35 (calm)
-- dominant_emotions: ["contentment", "gratitude"]
-- affect_band: "GREEN"
-- band_reasons: ["positive_affect"]
-- affect_model_version: "tier0_vader_v1.2"
```

---

## Alternatives Considered

### Alternative 1: Full Transformer for All Events (Rejected)

**Approach**: Use BERT/RoBERTa for all emotion classification (no two-tier strategy).

**Pros**:
- Highest accuracy (88-92% on complex emotions)
- Consistent quality (no tier switching logic)
- Handles all edge cases (negation, sarcasm, context)

**Cons**:
- ❌ **Latency**: 200-500ms per event blocks P02 write path (<100ms budget)
- ❌ **GPU dependency**: Requires GPU infrastructure (cost + complexity)
- ❌ **Overkill**: 90% of events are simple ("Had lunch") and don't need deep analysis
- ❌ **Scalability**: GPU inference limits throughput (100-200 events/sec per GPU)

**Rejection Rationale**: Cannot meet P02's <100ms latency budget without massive GPU infrastructure investment. Two-tier strategy provides 95% of accuracy at 10% of latency cost.

### Alternative 2: Lexicon-Only (No ML Tier) (Rejected)

**Approach**: Use VADER for all events (no Tier-1 fallback).

**Pros**:
- Simplest approach (no ML model management)
- <2ms latency for all events
- No GPU dependency (CPU-only)
- Deterministic (no model drift)

**Cons**:
- ❌ **Low accuracy**: 70-75% on complex emotions (vs. 85-90% with Tier-1)
- ❌ **Poor mixed emotion handling**: Cannot classify "bittersweet" or "conflicted"
- ❌ **Negation failures**: "not happy" may score as positive
- ❌ **Contextual misses**: "sick trick" (slang) misclassified as negative

**Rejection Rationale**: Accuracy too low for therapy/journaling use cases (P06). Two-tier strategy achieves 85%+ accuracy with acceptable latency.

### Alternative 3: No Affect Classification (Defer to P06) (Rejected)

**Approach**: Skip affect classification in P02; add it later in P06 (therapy pipeline).

**Pros**:
- Simplifies P02 (one fewer module)
- Defers complexity to domain-specific pipeline

**Cons**:
- ❌ **Salience scoring breaks**: P02 salience formula requires affect (40% weight)
- ❌ **No early risk detection**: Cannot flag RED events for immediate attention
- ❌ **Double processing**: P06 would need to re-read events and recompute affect (inefficient)
- ❌ **Loss of context**: Affect is time-sensitive (emotional state at event time)

**Rejection Rationale**: Affect is **required** for P02 salience scoring. Cannot defer without breaking memory prioritization.

### Alternative 4: Emoji-Based Heuristic (Rejected)

**Approach**: Classify emotions based on emoji presence (e.g., 😊 → positive, 😢 → sad).

**Pros**:
- <1ms latency (simple pattern matching)
- Works well for emoji-heavy input (e.g., texts from teens)

**Cons**:
- ❌ **Low coverage**: Most text has no emojis (70-80% of events)
- ❌ **Ambiguous emojis**: 😅 can be nervous or amused
- ❌ **Missing context**: "Great 😑" (sarcasm) misclassified as positive
- ❌ **Not generalizable**: Different cultures use emojis differently

**Rejection Rationale**: Too narrow (only works for emoji-rich text). Cannot serve as primary classification method.

---

## Consequences

### Positive Consequences

✅ **Two-Tier Strategy Balances Accuracy and Latency**
- Tier-0 handles 90% of events in <2ms
- Tier-1 provides 85-90% accuracy for complex emotions in <60ms
- Overall P95 latency <70ms meets P02 budget

✅ **Circumplex Model Captures Emotional Nuance**
- Continuous dimensions (valence/arousal) handle mixed emotions
- Culturally generalizable (dimensions universal across cultures)
- Supports therapy use cases (tracks mood over time)

✅ **Affect Band Classification Enables Risk Triage**
- GREEN/AMBER/RED bands support therapy escalation (P06)
- RED events prioritized for long-term retention (P03)
- Salience scoring uses affect intensity (40% weight)

✅ **Write-Path Optimized (No Blocking)**
- Tier-0 (<2ms) keeps write path fast for routine events
- Tier-1 (<60ms) acceptable for 10% of events
- No GPU required for 90% of traffic (cost savings)

### Negative Consequences (with Mitigations)

⚠️ **Lower Accuracy Than Full Transformer (75-85% vs. 90%)**
- **Issue**: Tier-0 lexicon-based approach less accurate than BERT
- **Mitigation**: Tier-1 ML fallback for complex emotions; accuracy sufficient for salience scoring (not mission-critical)

⚠️ **Tier-1 Requires GPU for Production Latency (<60ms)**
- **Issue**: CPU inference takes 200-500ms (too slow for write path)
- **Mitigation**: Deploy Tier-1 model on GPU nodes; fall back to Tier-0 defaults if GPU unavailable

⚠️ **Model Drift Over Time (Language Evolution)**
- **Issue**: Slang and emoji usage change (e.g., "sus", "💀" meaning)
- **Mitigation**: Quarterly model retraining on recent data; A/B testing for model updates

⚠️ **Cannot Handle Multimodal Affect (Images, Audio, Video)**
- **Issue**: Text-only classification misses visual cues (facial expressions) and audio cues (tone of voice)
- **Mitigation**: Defer multimodal affect to k004.2 (future work); text-only sufficient for Phase 1

### Performance Impact Analysis

**Latency Comparison**:

| Approach | P50 | P95 | P99 | GPU Required |
|----------|-----|-----|-----|--------------|
| Full Transformer | 300ms | 450ms | 600ms | Yes |
| Lexicon-Only | 1.5ms | 2ms | 3ms | No |
| **Two-Tier (Chosen)** | **8ms** | **65ms** | **95ms** | Yes (Tier-1) |

**Cost Analysis** (per 1M events):

| Approach | Compute Cost | Accuracy | Cost per % Accuracy |
|----------|--------------|----------|---------------------|
| Full Transformer | $50 (GPU) | 90% | $0.56 |
| Lexicon-Only | $2 (CPU) | 75% | $0.027 |
| **Two-Tier (Chosen)** | **$7** (10% GPU) | **85%** | **$0.082** |

Two-tier strategy provides **best cost-effectiveness** (85% accuracy at 14% of full transformer cost).

---

## Testing Strategy

### Unit Tests

```python
def test_tier0_simple_positive():
    """Verify Tier-0 classifies simple positive text correctly."""
    text = "Had a wonderful dinner with family tonight!"
    annotation = tier0_classify(text)

    assert annotation is not None  # Should not fall back to Tier-1
    assert annotation.valence > 0.7  # Positive
    assert annotation.affect_band == "GREEN"
    assert "joy" in annotation.dominant_emotions or "contentment" in annotation.dominant_emotions

def test_tier0_fallback_to_tier1():
    """Verify Tier-0 falls back to Tier-1 for complex emotions."""
    text = "I have such mixed feelings about this job offer..."
    annotation = tier0_classify(text)

    assert annotation is None  # Should trigger Tier-1 fallback

def test_affect_band_classification():
    """Verify affect band thresholds are correct."""
    # GREEN (positive)
    band, reasons = classify_affect_band(valence=0.8, arousal=0.5)
    assert band == "GREEN"
    assert "positive_affect" in reasons

    # AMBER (mild negative)
    band, reasons = classify_affect_band(valence=0.4, arousal=0.3)
    assert band == "AMBER"
    assert "mild_negative_affect" in reasons

    # RED (strong negative + high arousal)
    band, reasons = classify_affect_band(valence=0.2, arousal=0.8)
    assert band == "RED"
    assert "strong_negative_affect" in reasons
    assert "high_arousal" in reasons
```

### Integration Tests

```python
def test_p02_affect_integration():
    """End-to-end test: P02 writes event → affect classification → verify columns."""
    # Step 1: Write event with emotional content
    event = write_event(
        text="Felt really anxious before the big presentation today.",
        pipeline="P02"
    )

    # Step 2: Verify affect classification (should be Tier-1 due to "anxious")
    assert event.affect_valence < 0.4  # Negative
    assert event.affect_arousal > 0.6  # High arousal (anxiety)
    assert event.affect_band == "RED"  # High negative arousal → RED
    assert "anxiety" in event.dominant_emotions or "fear" in event.dominant_emotions
    assert "strong_negative_affect" in event.band_reasons

    # Step 3: Verify Tier-1 model used (complex emotion)
    assert event.affect_model_version.startswith("tier1_")

def test_latency_slo():
    """Verify P95 latency ≤70ms for affect classification."""
    texts = [generate_test_text() for _ in range(1000)]
    latencies = []

    for text in texts:
        start_time = time.time()
        annotation = classify_affect(text)  # Tier-0 or Tier-1
        latency = (time.time() - start_time) * 1000  # ms
        latencies.append(latency)

    p95_latency = np.percentile(latencies, 95)
    assert p95_latency <= 70  # P95 ≤70ms SLO
```

---

## Implementation Roadmap

### Phase 1: Tier-0 Lexicon-Based (Week 1-2)

**Deliverables**:
- VADER integration for sentiment analysis
- Valence/arousal mapping from VADER compound score
- Affect band classification logic (GREEN/AMBER/RED)
- Dominant emotion derivation from circumplex model

**Acceptance Criteria**:
- Unit tests pass for valence/arousal mapping
- Affect band thresholds match specification (valence <0.3 + arousal >0.6 = RED)
- <2ms P99 latency for Tier-0 path

### Phase 2: Tier-1 ML-Based (Week 3-4)

**Deliverables**:
- Distilled transformer model (DistilBERT fine-tuned on GoEmotions dataset)
- GPU inference pipeline (fallback to CPU if GPU unavailable)
- Tier-0 → Tier-1 fallback logic (complexity detection)
- Model versioning and A/B testing framework

**Acceptance Criteria**:
- Integration test: Complex emotions classified correctly (85%+ accuracy on test set)
- <60ms P95 latency for Tier-1 path (with GPU)
- Tier-0 fallback triggers for 90%+ of simple events

### Phase 3: P02 Integration + Monitoring (Week 5)

**Deliverables**:
- P02 pipeline integration (stage_20_affect_analyze)
- Observability: metrics for tier distribution, latency, band distribution
- Error handling: fallback to neutral affect (0.5, 0.3) if classification fails

**Acceptance Criteria**:
- P02 processes 10K events/day per tenant with affect classification
- Tier distribution: 90% Tier-0, 10% Tier-1 (measured via telemetry)
- Affect band distribution logged (GREEN/AMBER/RED percentages)

---

## Sub-ADRs

This parent ADR defines the overall affect service architecture. Implementation details are in sub-ADRs:

- **[k004.1: Tier-0 Fast Affect Classification](k004.1-tier0-fast-affect.md)** — VADER lexicon-based approach (<2ms)
- **[k004.2: Multi-Modal Affect Classification](k004.2-multimodal-affect.md)** — Future: Images, audio, video, biometrics
- **[k004.3: Affect Learning Loop](k004.3-affect-learning-loop.md)** — Future: Personalized affect models, user feedback

---

## References

### Research Papers

1. **Russell, J. A. (1980)**. "A circumplex model of affect." *Journal of Personality and Social Psychology*, 39(6), 1161-1178.
   - Foundational paper on valence/arousal dimensional model

2. **Ekman, P. (1992)**. "An argument for basic emotions." *Cognition & Emotion*, 6(3-4), 169-200.
   - Discrete emotion categories (joy, sadness, anger, fear, surprise, disgust)

3. **LeDoux, J. E. (2000)**. "Emotion circuits in the brain." *Annual Review of Neuroscience*, 23, 155-184.
   - Dual-process emotion system (amygdala fast path + cortical slow path)

4. **Barrett, L. F. (2017)**. *How Emotions Are Made: The Secret Life of the Brain*. Houghton Mifflin Harcourt.
   - Constructivist theory of emotions (emotions as brain predictions, not hardwired)

5. **Hutto, C. J., & Gilbert, E. (2014)**. "VADER: A Parsimonious Rule-Based Model for Sentiment Analysis of Social Media Text." *ICWSM*.
   - VADER lexicon algorithm (used in Tier-0)

### Tools and Libraries

- **VADER Sentiment Analyzer**: https://github.com/cjhutto/vaderSentiment
- **Hugging Face Transformers**: https://github.com/huggingface/transformers (DistilBERT)
- **GoEmotions Dataset**: https://github.com/google-research/google-research/tree/master/goemotions (27 emotion categories)

---

**Last Updated**: 2025-11-16
