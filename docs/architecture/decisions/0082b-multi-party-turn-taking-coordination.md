# ADR-0082b: Multi-Party Turn-Taking Coordination

**Status:** Proposed
**Date:** 2025-10-22
**Parent ADR:** ADR-0082 (Multi-Party Dialogue Coordination)
**Related ADRs:** ADR-0054 (Turn Boundary Management), ADR-0017 (SessionState Section 2), ADR-0082a (Speaker Diarization)

---

## Context

### **Problem Statement**

Single-user dialogue systems (ADR-0054) assume **sequential turns**: User speaks → System responds → User speaks. Family conversations have:

- **Overlapping speech:** Dad and Mom speak simultaneously
- **Rapid switching:** Barge-in mid-response (ADR-0054c)
- **Multi-threading:** Dad asks about weather, Mom asks about calendar (2 parallel requests)
- **Context mixing:** Without speaker attribution, system confuses "my calendar" (whose calendar?)

**Current ADR-0054 Limitation:**

```python
# ADR-0054 Turn Boundary (single-user only)
turn_state = {
    "turn_id": "turn_00042",
    "user_speech_start": 1729620000000000,
    "user_speech_end": 1729620003000000,
    "system_response_start": 1729620003500000,
    # No multi-speaker support
}
```

**Multi-Party Requirement:**

```python
# Extended turn state for multi-party
turn_state = {
    "turn_id": "turn_00042",
    "mode": "multi_party",  # NEW
    "speakers": [  # NEW: Multiple concurrent speakers
        {
            "speaker_id": "Dad",
            "segment": (T0, T3),
            "utterance": "Book dinner reservation"
        },
        {
            "speaker_id": "Mom",
            "segment": (T1, T4),  # Overlaps with Dad (T1-T3)
            "utterance": "What's the weather tomorrow?"
        }
    ],
    "overlap_detected": True,
    "allocation_strategy": "parallel_processing"
}
```

---

## Decision

### **Architecture: 3-Strategy Turn Allocation**

**Strategy 1: First-Speaker Priority (Sequential Processing)**

```
Dad starts speaking at T0
Mom starts speaking at T1 (50ms after Dad)

Turn Manager:
  - Detect overlap: Dad (T0-T3), Mom (T1-T4) → 2-second overlap
  - Apply First-Speaker Priority: Dad started first (T0 < T1)
  - Queue Mom's request (latency +500ms)

Processing:
  T0-T3: Dad speaking [ACTIVE]
  T3: Dad finishes → ASR transcribes "Book dinner reservation"
  T3-T4: Mom still speaking [QUEUED]
  T4: Mom finishes → ASR transcribes "What's the weather tomorrow?"

  T4+: System responds to Dad first:
      "I'll book dinner at your usual steakhouse for 7pm"
  T5+: System responds to Mom second:
      "Tomorrow will be 68°F and rainy in Seattle"
```

**When to Use:**
- **Default strategy** for most families
- **Low compute cost:** Sequential agent execution (1× cost)
- **Acceptable latency:** +500ms queue delay tolerable for non-urgent requests

**Strategy 2: Parallel Processing (Concurrent Agents)**

```
Dad starts speaking at T0
Mom starts speaking at T1 (50ms after Dad)

Turn Manager:
  - Detect overlap: Dad (T0-T3), Mom (T1-T4) → 2-second overlap
  - Apply Parallel Processing: Assign 2 agents simultaneously

Processing (Parallel):
  T0-T3: Dad speaking [ACTIVE]
  T1-T4: Mom speaking [ACTIVE]

  Agent 1 (Dad's request):
    T3: ASR transcribes "Book dinner reservation"
    T3-T4: Planner generates plan (uses Dad's preferences from KG)
    T4: Execute tool call (book restaurant)

  Agent 2 (Mom's request):
    T4: ASR transcribes "What's the weather tomorrow?"
    T4-T5: Planner generates plan (uses Mom's location from SessionState)
    T5: Execute weather query

  T4+: System responds to both (spatially separated audio OR sequential TTS)
```

**When to Use:**
- **Urgent requests:** Both speakers have high-priority needs
- **Power users:** Families comfortable with higher compute cost
- **Latency-sensitive:** Minimize queue delay (<200ms for both speakers)

**Cost:** 2× compute (2 agents running in parallel)

**Strategy 3: Priority-Based Preemption**

```
Dad speaking (low urgency): "What's the weather?"
Mom interrupts (high urgency): "Emergency! Baby fell!"

Turn Manager:
  - Detect overlap + sentiment analysis (ADR-0069)
    - Dad: neutral sentiment, urgency=0.2
    - Mom: panic sentiment, urgency=0.9
  - Apply Priority Preemption: Mom's urgency (0.9) >> Dad's (0.2)
  - INTERRUPT Dad's processing, prioritize Mom

Processing:
  T0-T2: Dad speaking "What's the weather?"
  T2: Mom interrupts "Emergency! Baby fell!"
  T2: Turn Manager PAUSES Dad's request (save state)
  T2-T3: Mom speaking [ACTIVE, HIGH PRIORITY]
  T3: ASR transcribes Mom's request
  T3+: System responds to Mom IMMEDIATELY:
       "Calling 911. Stay calm, help is on the way."
  T5+: System returns to Dad's request (low priority):
       "Sorry for the interruption - you asked about weather. It's 72°F today."
```

**When to Use:**
- **Emergency scenarios:** Panic/urgent keywords detected (fire, emergency, help, 911)
- **Sentiment-based:** High emotional urgency (ADR-0069 affect >0.8)

**Urgency Detection:**
```python
# Keyword-based urgency
urgent_keywords = ["emergency", "help", "fire", "911", "stop", "danger"]

# Sentiment-based urgency (ADR-0069)
sentiment_urgency = {
    "panic": 0.9,
    "angry": 0.7,
    "frustrated": 0.5,
    "neutral": 0.2,
    "happy": 0.1
}

# Combined urgency score
urgency_score = max(
    keyword_match_score(utterance, urgent_keywords),
    sentiment_urgency[detected_sentiment]
)
```

### **Overlapping Speech Detection**

**Algorithm: Timestamp + Energy Analysis**

```python
def detect_overlap(segments: List[SpeechSegment]) -> bool:
    """
    Detect if multiple speakers have overlapping speech

    Args:
        segments: List of speech segments with (start_ts, end_ts, speaker_id)

    Returns:
        True if any segments overlap in time
    """
    for i in range(len(segments)):
        for j in range(i+1, len(segments)):
            seg_a = segments[i]
            seg_b = segments[j]

            # Check temporal overlap
            overlap_start = max(seg_a.start_ts, seg_b.start_ts)
            overlap_end = min(seg_a.end_ts, seg_b.end_ts)

            if overlap_start < overlap_end:
                overlap_duration_ms = (overlap_end - overlap_start) / 1000

                # Ignore very short overlaps (<100ms - natural turn-taking)
                if overlap_duration_ms >= 100:
                    return True, {
                        "speakers": [seg_a.speaker_id, seg_b.speaker_id],
                        "overlap_duration_ms": overlap_duration_ms,
                        "overlap_start": overlap_start,
                        "overlap_end": overlap_end
                    }

    return False, None
```

**Audio Energy Thresholding:**

```python
# Detect if both speakers have sufficient energy (not background noise)
def validate_dual_speech(audio_a: np.ndarray, audio_b: np.ndarray) -> bool:
    """Check if both audio streams have speech energy (RMS > threshold)"""
    rms_a = np.sqrt(np.mean(audio_a ** 2))
    rms_b = np.sqrt(np.mean(audio_b ** 2))

    SPEECH_ENERGY_THRESHOLD = 0.02  # Empirically determined

    return (rms_a > SPEECH_ENERGY_THRESHOLD and
            rms_b > SPEECH_ENERGY_THRESHOLD)
```

### **Speaker Context Retrieval**

**Integration with SessionState Section 2 (Scoreboard)**

ADR-0017 SessionState Section 2 stores **common ground** (shared conversation context). Extend for **per-speaker context**:

```python
# SessionState Section 2 Extension (from ADR-0082 parent)
scoreboard = {
    "speakers": {
        "Dad": {
            "speaker_id": "Dad",
            "preferences": {
                "restaurant": "steakhouse",
                "response_style": "concise"
            },
            "recent_queries": ["weather", "calendar"],
            "active": True,
            "last_interaction_ts": 1729620000000000
        },
        "Mom": {
            "speaker_id": "Mom",
            "preferences": {
                "restaurant": "vegetarian",
                "dietary_restrictions": ["vegetarian", "gluten-free"]
            },
            "recent_queries": ["calendar", "grocery list"],
            "active": True,
            "last_interaction_ts": 1729620050000000
        }
    },
    "active_speakers": ["Dad", "Mom"],
    "conversation_mode": "multi_party"
}

# API for speaker context retrieval
def get_speaker_context(speaker_id: str) -> Dict:
    """Retrieve per-speaker context from SessionState Section 2"""
    return scoreboard["speakers"].get(speaker_id, {
        "speaker_id": "Unknown",
        "preferences": {},
        "recent_queries": [],
        "active": False
    })
```

**Context Usage in LLM Planner:**

```python
# Planner uses speaker-specific context
speaker_context = get_speaker_context(speaker_id="Dad")

# Query Knowledge Graph with speaker preferences
if speaker_context["speaker_id"] == "Dad":
    restaurant_pref = kg.query(
        "GET_PREFERENCE",
        speaker_id="Dad",
        preference_type="restaurant"
    )
    # Returns: "steakhouse" (Dad's preference)
else:
    restaurant_pref = kg.query(
        "GET_PREFERENCE",
        speaker_id="Mom",
        preference_type="restaurant"
    )
    # Returns: "vegetarian" (Mom's preference)
```

### **Turn Allocation Decision Tree**

```
┌─────────────────────────────────────────────────────────────────────────┐
│ TURN MANAGER: Overlap Detected (2+ speakers)                            │
├─────────────────────────────────────────────────────────────────────────┤
│ Input: [Dad: T0-T3, Mom: T1-T4] → Overlap detected (T1-T3)             │
│   ↓                                                                      │
│ Step 1: Check Urgency Signals                                           │
│   - Dad urgency: 0.2 (neutral sentiment, no urgent keywords)            │
│   - Mom urgency: 0.3 (neutral sentiment, no urgent keywords)            │
│   - Max urgency: 0.3 (below 0.7 threshold for preemption)               │
│   ↓                                                                      │
│ Step 2: Check System Configuration                                      │
│   - parallel_processing_enabled: True/False (user preference)           │
│   - compute_budget_available: True/False (CPU load < 70%)               │
│   ↓                                                                      │
│ Step 3: Select Allocation Strategy                                      │
│   ├─ IF max_urgency >= 0.7:                                             │
│   │     → Strategy 3: Priority Preemption (interrupt low-urgency)       │
│   ├─ ELSE IF parallel_processing_enabled AND compute_budget_available:  │
│   │     → Strategy 2: Parallel Processing (2 agents)                    │
│   └─ ELSE:                                                               │
│         → Strategy 1: First-Speaker Priority (queue Mom, Dad first)     │
│   ↓                                                                      │
│ Step 4: Execute Allocation                                              │
│   - Assign agents to speakers                                           │
│   - Retrieve speaker context from SessionState Section 2                │
│   - Tag requests with speaker_id for downstream processing              │
└─────────────────────────────────────────────────────────────────────────┘
```

### **Barge-In Handling (ADR-0054c Integration)**

ADR-0054c (Barge-In Interruption) handles single-user interruptions. Extend for multi-party:

```python
# Multi-party barge-in scenario
system_speaking = True  # TTS in progress
new_speaker_detected = "Mom"  # Mom speaks while system responding to Dad

# Barge-in decision (from ADR-0054c)
if system_speaking and new_speaker_detected:
    # Check if new speaker is DIFFERENT from original requester
    if new_speaker_detected != original_requester:
        # Multi-party barge-in → new request from different speaker
        barge_in_action = "queue_new_request"  # Don't interrupt, queue
    else:
        # Same-user barge-in → apply ADR-0054c logic
        barge_in_action = "interrupt_response"  # User refining request

# Example:
# Dad: "What's the weather?" [SYSTEM STARTS RESPONDING]
# Mom (interrupts): "What's on my calendar?" [NEW SPEAKER]
# → Queue Mom's request, finish responding to Dad first
```

### **Performance Budget**

| **Operation** | **Target (P95)** | **Implementation** |
|---------------|------------------|-------------------|
| Overlap Detection | <20ms | Timestamp comparison (O(n²) for n speakers) |
| Urgency Analysis | <30ms | Keyword matching + sentiment lookup (ADR-0069) |
| Context Retrieval | <10ms | SessionState Section 2 in-memory lookup |
| Turn Allocation Decision | <10ms | Decision tree evaluation |
| **Total Turn Coordination** | **<50ms** | Sum of above stages |

---

## Consequences

### **Positive**

1. **Graceful Overlap Handling:** System doesn't fail when 2+ people speak simultaneously
2. **Flexible Strategies:** Families choose priority (latency), parallel (speed), or preemption (urgency)
3. **Speaker-Aware Context:** Each speaker gets personalized responses using their preferences
4. **Emergency Responsiveness:** Urgent requests interrupt non-urgent ones (safety-critical)
5. **Scalable:** Supports 3-5 concurrent speakers (most family sizes)

### **Negative**

1. **Compute Cost:** Parallel processing 2× cost (acceptable for power users)
2. **Queue Latency:** First-Speaker Priority adds +500ms for queued speakers (acceptable for non-urgent)
3. **Complex State:** Tracking multiple speakers increases SessionState size (~10KB per speaker)
4. **Edge Cases:** 3+ concurrent speakers may exceed compute budget (fallback to queueing)
5. **Testing Complexity:** Multi-speaker scenarios harder to reproduce/test

### **Risks & Mitigations**

| **Risk** | **Impact** | **Mitigation** |
|----------|------------|----------------|
| Compute overload (4+ parallel agents) | HIGH | Limit max concurrent speakers to 3, queue additional |
| Context mixing (wrong speaker context) | HIGH | Strict speaker_id tagging throughout pipeline |
| Queue starvation (low-urgency never processed) | MEDIUM | Max queue time 5 seconds → force processing |
| TTS collision (2 responses overlap) | MEDIUM | Spatial audio separation OR sequential TTS with speaker tags |

---

## Implementation Guidance

### **Turn Manager State Machine**

```python
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional

class AllocationStrategy(Enum):
    FIRST_SPEAKER_PRIORITY = "first_speaker_priority"
    PARALLEL_PROCESSING = "parallel_processing"
    PRIORITY_PREEMPTION = "priority_preemption"

@dataclass
class SpeechSegment:
    speaker_id: str
    start_ts: int  # Microseconds
    end_ts: int
    utterance: str
    confidence: float
    urgency: float  # 0.0-1.0

class TurnManager:
    def __init__(self, config):
        self.config = config
        self.active_segments: List[SpeechSegment] = []

    def detect_overlap(self) -> Optional[dict]:
        """Detect overlapping speech segments"""
        # Implementation from earlier
        pass

    def calculate_urgency(self, segment: SpeechSegment) -> float:
        """Calculate urgency score (keywords + sentiment)"""
        keyword_urgency = self._keyword_urgency(segment.utterance)
        sentiment_urgency = self._sentiment_urgency(segment.utterance)
        return max(keyword_urgency, sentiment_urgency)

    def select_strategy(self, segments: List[SpeechSegment]) -> AllocationStrategy:
        """Select turn allocation strategy"""
        max_urgency = max(seg.urgency for seg in segments)

        if max_urgency >= 0.7:
            return AllocationStrategy.PRIORITY_PREEMPTION
        elif (self.config.parallel_processing_enabled and
              self._compute_budget_available()):
            return AllocationStrategy.PARALLEL_PROCESSING
        else:
            return AllocationStrategy.FIRST_SPEAKER_PRIORITY

    def allocate_turns(self, segments: List[SpeechSegment]) -> dict:
        """Allocate processing resources to speakers"""
        strategy = self.select_strategy(segments)

        if strategy == AllocationStrategy.FIRST_SPEAKER_PRIORITY:
            # Sort by start time, process sequentially
            sorted_segments = sorted(segments, key=lambda s: s.start_ts)
            return {
                "strategy": "first_speaker_priority",
                "queue": [seg.speaker_id for seg in sorted_segments],
                "latency_estimate_ms": len(sorted_segments) * 500
            }

        elif strategy == AllocationStrategy.PARALLEL_PROCESSING:
            # Process all speakers in parallel
            return {
                "strategy": "parallel_processing",
                "concurrent_agents": [seg.speaker_id for seg in segments],
                "compute_multiplier": len(segments)
            }

        elif strategy == AllocationStrategy.PRIORITY_PREEMPTION:
            # Interrupt low-urgency, prioritize high-urgency
            sorted_by_urgency = sorted(segments, key=lambda s: s.urgency, reverse=True)
            return {
                "strategy": "priority_preemption",
                "priority_queue": [seg.speaker_id for seg in sorted_by_urgency],
                "interrupted_speakers": [s.speaker_id for s in sorted_by_urgency[1:]]
            }
```

### **Metrics & Observability**

```python
from prometheus_client import Histogram, Counter, Gauge

overlapping_speech_total = Counter(
    'overlapping_speech_detections_total',
    'Total overlapping speech events'
)

turn_allocation_latency_ms = Histogram(
    'turn_allocation_latency_ms',
    'Turn allocation decision latency',
    buckets=[5, 10, 25, 50, 75, 100]
)

turn_allocation_strategy_used = Counter(
    'turn_allocation_strategy',
    'Turn allocation strategy used',
    ['strategy']  # first_speaker, parallel, priority_preemption
)

speaker_queue_latency_ms = Histogram(
    'speaker_queue_latency_ms',
    'Time speaker waited in queue before processing',
    buckets=[100, 250, 500, 1000, 2000]
)

concurrent_speakers_active = Gauge(
    'concurrent_speakers_active',
    'Number of speakers currently being processed'
)
```

---

## References

### **Research Papers**

1. **Bohus & Horvitz (2011):** "Multiparty Turn Taking in Situated Dialog: Study, Lessons, and Directions" - Microsoft Research
2. **Skantze (2021):** "Turn-taking in Conversational Systems and Human-Robot Interaction: A Review" - KTH Royal Institute of Technology
3. **Traum & Rickel (2002):** "Embodied Agents for Multi-party Dialogue in Immersive Virtual Worlds" - USC Institute for Creative Technologies

### **Related ADRs**

- **ADR-0054:** Turn Boundary Management (extended for multi-party)
- **ADR-0054c:** Barge-In Interruption Handling (integrated with multi-speaker barge-in)
- **ADR-0017:** SessionState Section 2 (Scoreboard - per-speaker context storage)
- **ADR-0082a:** Speaker Diarization (provides speaker_id for turn allocation)
- **ADR-0069:** Affect Modulation (sentiment analysis for urgency detection)

---

## Changelog

- **2025-10-22:** Initial proposal for Multi-Party Turn-Taking Coordination (Sub-ADR of ADR-0082)

---

**Next Steps:**

1. **Strategy Evaluation:** Benchmark latency/compute for 3 strategies (2 weeks)
2. **SessionState Extension:** Add per-speaker context to Section 2 (1 week)
3. **Turn Manager Implementation:** Build state machine with 3 strategies (2 weeks)
4. **Urgency Detection:** Integrate keyword matching + ADR-0069 sentiment (1 week)
5. **WARD Testing:** Multi-speaker scenarios (overlap, urgency, queueing) (2 weeks)
