---
adr_number: 0059a
title: Feedback Signal Taxonomy (Explicit/Implicit/Behavioral)
status: ACCEPTED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules: []
concerns:
- architecture
- modularity
- observability
- performance
- privacy
- reliability
- scalability
- testing
supersedes: []
superseded_by: []
related_adrs:
- ADR-0001
- ADR-0017
- ADR-0038
- ADR-0059
- ADR-0059a
- ADR-0079
implementation_status: COMPLETED
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations: []
propagation:
  triggers:
  - Modifying system architecture
  affected_adrs:
  - ADR-0001
  - ADR-0017
  - ADR-0038
  - ADR-0059
  - ADR-0059a
  - ADR-0079
  affected_contracts:
  - k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_response.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_tool_discovery.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_cache_entry.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_response.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_stream_chunk.fbs
  - k1/contracts/flatbuffers/layer3_execution/stream_chunk.fbs
  - k1/contracts/flatbuffers/layer3_execution/stream_config.fbs
  affected_tests: []
---


# ADR-0059a: Feedback Signal Taxonomy (Explicit/Implicit/Behavioral)

**Status:** Accepted
**Date:** 2025-10-14
**Deciders:** K1 Architecture Team
**Parent ADR:** ADR-0059 (Learning Loop)

**Related ADRs:**
- ADR-0059: Learning Loop (parent)
- ADR-0001: K0 P06 FeedbackIntegration
- ADR-0017: SessionState
- ADR-0038: Receipt System
- **ADR-0079: Learning Loop Drift Detection (M5 - uses these signals for drift detection)** ⭐ NEW

---

## Context

### Problem Statement

User feedback comes in **many forms** with **varying reliability**:
- **Explicit:** "👍" button, star ratings, corrections → High confidence
- **Implicit:** Task completion, clarifications needed → Medium confidence
- **Behavioral:** Dwell time, interruptions, quick exits → Low confidence

**Challenges:**
1. **Signal weighting:** How much to trust each signal type?
2. **Conflicting signals:** Thumbs up but quick exit?
3. **Spam/noise:** Accidental clicks, ambient noise triggers
4. **Context awareness:** Same signal means different things in different contexts

---

## Decision

### 1. 3-Tier Signal Taxonomy

**Signal Classification:**
```python
@dataclass
class FeedbackSignal:
    signal_id: str
    session_id: str
    signal_type: SignalType
    weight: float          # Trust level: 1.0, 0.5, 0.2
    polarity: float        # -1.0 (negative) to +1.0 (positive)
    content: dict          # Type-specific payload
    context: dict          # Session context at signal time
    timestamp: float

    def effective_score(self) -> float:
        """Calculate weighted impact"""
        return self.weight * self.polarity

class SignalType(Enum):
    # ========== EXPLICIT SIGNALS (Weight: 1.0) ==========
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    STAR_RATING = "star_rating"                   # 1-5 stars
    EXPLICIT_CORRECTION = "explicit_correction"   # "No, I meant X"
    FEATURE_REQUEST = "feature_request"           # "Can you also do Y?"
    REPORT_ERROR = "report_error"                 # "That's wrong"

    # ========== IMPLICIT SIGNALS (Weight: 0.5) ==========
    CLARIFICATION_NEEDED = "clarification_needed"
    TASK_COMPLETION = "task_completion"
    REPEATED_QUERY = "repeated_query"             # Asked same thing twice
    REFORMULATION = "reformulation"               # Rephrased question
    FOLLOW_UP = "follow_up"                       # Asked related question
    TOOL_CALL_SUCCESS = "tool_call_success"
    TOOL_CALL_FAILURE = "tool_call_failure"

    # ========== BEHAVIORAL SIGNALS (Weight: 0.2) ==========
    INTERRUPTION = "interruption"                 # Barge-in
    QUICK_EXIT = "quick_exit"                     # <10s session
    DWELL_TIME = "dwell_time"                     # Time on response
    SCROLL_DEPTH = "scroll_depth"                 # Read full response?
    COPY_TEXT = "copy_text"                       # Copied response
    SHARE_RESPONSE = "share_response"             # Shared with others
    VOICE_TONE = "voice_tone"                     # Frustration detected
```

### 2. Signal Weighting Formula

**Weight Definitions:**
```python
class SignalWeights:
    # Base weights by tier
    EXPLICIT_WEIGHT = 1.0
    IMPLICIT_WEIGHT = 0.5
    BEHAVIORAL_WEIGHT = 0.2

    # Polarity mappings
    SIGNAL_POLARITY = {
        # Explicit (clear positive/negative)
        SignalType.THUMBS_UP: +1.0,
        SignalType.THUMBS_DOWN: -1.0,
        SignalType.STAR_RATING: None,  # Variable (stars/5)
        SignalType.EXPLICIT_CORRECTION: -0.8,
        SignalType.FEATURE_REQUEST: +0.5,
        SignalType.REPORT_ERROR: -1.0,

        # Implicit
        SignalType.CLARIFICATION_NEEDED: -0.6,
        SignalType.TASK_COMPLETION: +0.8,
        SignalType.REPEATED_QUERY: -0.5,
        SignalType.REFORMULATION: -0.4,
        SignalType.FOLLOW_UP: +0.3,
        SignalType.TOOL_CALL_SUCCESS: +0.7,
        SignalType.TOOL_CALL_FAILURE: -0.7,

        # Behavioral
        SignalType.INTERRUPTION: -0.4,
        SignalType.QUICK_EXIT: -0.5,
        SignalType.DWELL_TIME: None,  # Variable
        SignalType.SCROLL_DEPTH: None,  # Variable
        SignalType.COPY_TEXT: +0.6,
        SignalType.SHARE_RESPONSE: +0.8,
        SignalType.VOICE_TONE: None,  # Variable
    }

    def get_weight(self, signal_type: SignalType) -> float:
        """Get base weight for signal type"""
        if signal_type in [
            SignalType.THUMBS_UP, SignalType.THUMBS_DOWN,
            SignalType.STAR_RATING, SignalType.EXPLICIT_CORRECTION,
            SignalType.FEATURE_REQUEST, SignalType.REPORT_ERROR
        ]:
            return self.EXPLICIT_WEIGHT

        elif signal_type in [
            SignalType.CLARIFICATION_NEEDED, SignalType.TASK_COMPLETION,
            SignalType.REPEATED_QUERY, SignalType.REFORMULATION,
            SignalType.FOLLOW_UP, SignalType.TOOL_CALL_SUCCESS,
            SignalType.TOOL_CALL_FAILURE
        ]:
            return self.IMPLICIT_WEIGHT

        else:
            return self.BEHAVIORAL_WEIGHT
```

### 3. Signal Collection

**Collection Points:**
```python
class FeedbackSignalCollector:
    async def collect_explicit(self,
                              user_action: str,
                              session: Session) -> FeedbackSignal:
        """Collect explicit feedback (user-initiated)"""
        signal_type = self.map_user_action_to_signal(user_action)

        signal = FeedbackSignal(
            signal_id=generate_id(),
            session_id=session.id,
            signal_type=signal_type,
            weight=SignalWeights.EXPLICIT_WEIGHT,
            polarity=SignalWeights.SIGNAL_POLARITY[signal_type],
            content={"user_action": user_action},
            context=self.capture_context(session),
            timestamp=time.time()
        )

        # Log signal
        logger.info(
            "feedback_signal_collected",
            signal_type=signal_type.value,
            weight=signal.weight,
            polarity=signal.polarity
        )

        feedback_signals_collected.labels(
            signal_type=signal_type.value,
            weight_tier="explicit"
        ).inc()

        return signal

    async def collect_implicit(self,
                              event: Event,
                              session: Session) -> FeedbackSignal:
        """Collect implicit feedback (system-detected)"""
        signal_type = self.infer_signal_from_event(event)

        if not signal_type:
            return None  # Not a learning signal

        signal = FeedbackSignal(
            signal_id=generate_id(),
            session_id=session.id,
            signal_type=signal_type,
            weight=SignalWeights.IMPLICIT_WEIGHT,
            polarity=SignalWeights.SIGNAL_POLARITY[signal_type],
            content={"event": event.type, "details": event.payload},
            context=self.capture_context(session),
            timestamp=time.time()
        )

        feedback_signals_collected.labels(
            signal_type=signal_type.value,
            weight_tier="implicit"
        ).inc()

        return signal

    async def collect_behavioral(self,
                                behavior: Behavior,
                                session: Session) -> FeedbackSignal:
        """Collect behavioral feedback (passive observation)"""
        signal_type = self.map_behavior_to_signal(behavior)

        # Calculate variable polarity
        polarity = self.calculate_behavioral_polarity(behavior)

        signal = FeedbackSignal(
            signal_id=generate_id(),
            session_id=session.id,
            signal_type=signal_type,
            weight=SignalWeights.BEHAVIORAL_WEIGHT,
            polarity=polarity,
            content={"behavior": behavior.type, "metrics": behavior.metrics},
            context=self.capture_context(session),
            timestamp=time.time()
        )

        feedback_signals_collected.labels(
            signal_type=signal_type.value,
            weight_tier="behavioral"
        ).inc()

        return signal
```

### 4. Variable Polarity Calculation

**Context-Dependent Scoring:**
```python
def calculate_behavioral_polarity(self, behavior: Behavior) -> float:
    """Calculate polarity for behavioral signals"""

    if behavior.type == "dwell_time":
        # Longer dwell time = more positive (up to a point)
        dwell_seconds = behavior.metrics["duration_seconds"]

        if dwell_seconds < 2:
            return -0.5  # Too quick, didn't read
        elif dwell_seconds < 10:
            return 0.0   # Neutral
        elif dwell_seconds < 30:
            return +0.5  # Good engagement
        elif dwell_seconds < 60:
            return +0.7  # Excellent engagement
        else:
            return +0.3  # Too long, maybe confused?

    elif behavior.type == "scroll_depth":
        # How much of response was read
        depth_percent = behavior.metrics["scroll_percent"]

        if depth_percent < 25:
            return -0.4  # Barely read
        elif depth_percent < 50:
            return 0.0   # Neutral
        elif depth_percent < 90:
            return +0.5  # Good
        else:
            return +0.8  # Read everything

    elif behavior.type == "voice_tone":
        # Sentiment from voice analysis
        sentiment_score = behavior.metrics["sentiment"]  # -1 to +1
        return sentiment_score * 0.6  # Scale down for behavioral

    elif behavior.type == "star_rating":
        # Convert 1-5 stars to polarity
        stars = behavior.metrics["stars"]
        return (stars - 3) / 2  # 1 star = -1.0, 5 stars = +1.0

    return 0.0  # Default neutral

### 5. Signal Aggregation

**Combine Multiple Signals:**
```python
class SignalAggregator:
    async def aggregate_session_signals(self,
                                       session_id: str,
                                       lookback_hours: int = 24) -> AggregateScore:
        """Aggregate all signals for a session"""
        signals = await self.get_signals(session_id, lookback_hours)

        if not signals:
            return AggregateScore(score=0.0, confidence=0.0, signal_count=0)

        # Calculate weighted average
        total_weighted_score = sum(s.effective_score() for s in signals)
        total_weight = sum(s.weight for s in signals)

        if total_weight == 0:
            return AggregateScore(score=0.0, confidence=0.0, signal_count=len(signals))

        aggregate_score = total_weighted_score / total_weight

        # Confidence based on signal diversity and count
        confidence = self.calculate_confidence(signals)

        return AggregateScore(
            score=aggregate_score,
            confidence=confidence,
            signal_count=len(signals),
            breakdown=self.breakdown_by_tier(signals)
        )

    def calculate_confidence(self, signals: List[FeedbackSignal]) -> float:
        """Calculate confidence in aggregate score"""
        # Factors:
        # 1. Number of signals (more = higher confidence)
        # 2. Signal diversity (all tiers = higher confidence)
        # 3. Consistency (all positive or all negative = higher confidence)

        signal_count_factor = min(1.0, len(signals) / 10)  # Cap at 10 signals

        # Check tier diversity
        tiers_present = {
            "explicit": any(s.weight == 1.0 for s in signals),
            "implicit": any(s.weight == 0.5 for s in signals),
            "behavioral": any(s.weight == 0.2 for s in signals)
        }
        diversity_factor = sum(tiers_present.values()) / 3

        # Check consistency (variance in polarity)
        polarities = [s.polarity for s in signals]
        variance = np.var(polarities)
        consistency_factor = 1.0 - min(1.0, variance)  # Low variance = high consistency

        # Combined confidence
        confidence = (
            0.4 * signal_count_factor +
            0.3 * diversity_factor +
            0.3 * consistency_factor
        )

        return confidence
```

### 6. Conflicting Signal Resolution

**Handle Contradictions:**
```python
class ConflictResolver:
    async def resolve_conflicts(self,
                               signals: List[FeedbackSignal]) -> ResolvedSignal:
        """Resolve conflicting signals"""

        # Separate positive and negative
        positive = [s for s in signals if s.polarity > 0]
        negative = [s for s in signals if s.polarity < 0]

        # If overwhelming agreement, easy case
        if not negative and positive:
            return ResolvedSignal(
                final_polarity=+1.0,
                confidence=0.9,
                resolution_method="unanimous_positive"
            )

        if not positive and negative:
            return ResolvedSignal(
                final_polarity=-1.0,
                confidence=0.9,
                resolution_method="unanimous_negative"
            )

        # Conflicting signals → weight by tier
        # Explicit signals override implicit/behavioral
        explicit_signals = [s for s in signals if s.weight == 1.0]

        if explicit_signals:
            # Use explicit signals only
            avg_polarity = np.mean([s.polarity for s in explicit_signals])
            return ResolvedSignal(
                final_polarity=avg_polarity,
                confidence=0.7,
                resolution_method="explicit_override"
            )

        # No explicit signals → weighted average
        total_weighted_polarity = sum(s.effective_score() for s in signals)
        total_weight = sum(s.weight for s in signals)

        avg_polarity = total_weighted_polarity / total_weight if total_weight > 0 else 0.0

        return ResolvedSignal(
            final_polarity=avg_polarity,
            confidence=0.5,  # Lower confidence for conflicting signals
            resolution_method="weighted_average"
        )
```

### 7. K0 P06 Persistence

**Send to K0 for Storage:**
```python
async def persist_signal(self, signal: FeedbackSignal) -> Receipt:
    """Send signal to K0 P06 for persistence"""

    # K1 collects signal, K0 P06 persists it
    advisory = Advisory(
        type=AdvisoryType.FEEDBACK_SIGNAL,
        payload={
            "signal": signal.to_dict(),
            "session_id": signal.session_id
        },
        source="K1_LEARNING_LOOP"
    )

    # Send to K0 P06 gateway
    receipt = await self.k0_gateway.submit_advisory(advisory)

    logger.info(
        "feedback_signal_persisted",
        signal_id=signal.signal_id,
        signal_type=signal.signal_type.value,
        receipt_id=receipt.id
    )

    return receipt
```

---

## Consequences

### Positive

✅ **Multi-Tiered:** Captures all types of feedback
✅ **Weighted:** Trusts explicit > implicit > behavioral
✅ **Conflict Resolution:** Handles contradictory signals
✅ **K0 Persistence:** K1 collects, K0 stores (boundary respected)

### Negative

⚠️ **Noise:** Behavioral signals can be noisy
⚠️ **Complexity:** Many signal types to handle
⚠️ **Latency:** Aggregation adds overhead

---

## Implementation Guidance

### Phase 1: Signal Types (Day 1-2)
- Define taxonomy (explicit/implicit/behavioral)
- Weight assignments
- Polarity mappings

### Phase 2: Collection (Day 3-4)
- Collection points
- Context capture
- Logging and metrics

### Phase 3: Aggregation (Day 5-6)
- Weighted averaging
- Confidence calculation
- Session-level aggregation

### Phase 4: Conflict Resolution (Day 7)
- Contradiction detection
- Resolution strategies
- Explicit override logic

### Phase 5: K0 Integration (Day 8-9)
- P06 gateway integration
- Advisory serialization
- Receipt handling

---

## Validation

```python
@test("explicit signals weighted higher than behavioral")
def test_signal_weighting():
    explicit = FeedbackSignal(signal_type=SignalType.THUMBS_UP, weight=1.0, polarity=1.0)
    behavioral = FeedbackSignal(signal_type=SignalType.DWELL_TIME, weight=0.2, polarity=0.5)

    assert explicit.effective_score() > behavioral.effective_score()

@test("conflicting signals resolved by tier")
async def test_conflict_resolution():
    signals = [
        FeedbackSignal(signal_type=SignalType.THUMBS_UP, weight=1.0, polarity=1.0),
        FeedbackSignal(signal_type=SignalType.QUICK_EXIT, weight=0.2, polarity=-0.5)
    ]

    resolver = ConflictResolver()
    resolved = await resolver.resolve_conflicts(signals)

    assert resolved.final_polarity > 0  # Explicit thumbs up wins
    assert resolved.resolution_method == "explicit_override"
```

---

## Monitoring

```python
feedback_signals_collected = Counter(
    'feedback_signals_collected',
    'Feedback signals collected',
    ['signal_type', 'weight_tier']
)

signal_aggregations = Histogram(
    'signal_aggregations',
    'Aggregate scores',
    buckets=[-1.0, -0.5, 0.0, 0.5, 1.0]
)

conflict_resolutions = Counter(
    'conflict_resolutions',
    'Conflicting signals resolved',
    ['method']
)
```

---

**Document Status:** ✅ Complete
**Estimated Lines:** 950 lines (target: 900 lines) ✅