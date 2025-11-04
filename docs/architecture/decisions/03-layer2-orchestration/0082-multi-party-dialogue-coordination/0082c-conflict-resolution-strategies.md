---
adr_number: 0082c
affected_layers:
- layer1_input
- layer3_execution
- layer4_runtime
affected_modules:
- k1.l2_orchestration.conflict_resolver
- k1.l3_execution.planner.conflict_detection
- k0.kernel.knowledge_graph.meta_policy
- k1.l4_runtime.session_state
authors:
- K1 Architecture Team
concerns:
- architecture
- cost
- observability
- performance
- privacy
- reliability
- security
- testing
- usability
date_created: '2025-11-03'
date_updated: '2025-11-03'
implementation_date: '2025-11-03'
implementation_phase: Phase 5 (Multi-Party Extensions)
implementation_status: IN_PROGRESS
propagation:
  affected_adrs:
  - ADR-0036
  - ADR-0050e
  - ADR-0052d
  - ADR-0069
  - ADR-0081
  - ADR-0082
  - ADR-0082a
  - ADR-0082b
  - ADR-0082c
  affected_contracts:
  - k0/contracts/api/dialogue/conflict_resolution.yml
  - k0/contracts/api/policy/meta_policy.yml
  - k1/contracts/flatbuffers/layer2_orchestration/conflict_state.fbs
  - k1/contracts/flatbuffers/layer3_execution/planner_state.fbs
  affected_tests:
  - tests/k1/l2_orchestration/test_conflict_resolver.py
  - tests/k1/l3_execution/test_conflict_detection.py
  - tests/k0/kernel/test_meta_policy.py
  triggers:
  - Performance requirement changes
related_adrs:
- ADR-0036
- ADR-0050e
- ADR-0052d
- ADR-0054
- ADR-0069
- ADR-0081
- ADR-0082
- ADR-0082a
- ADR-0082b
- ADR-0082c
related_contracts: []
related_diagrams: []
research_citations:
- Conflict Resolution in Dialogue (Walker, 1996)
- Multi-Agent Negotiation (Jennings et al., 2001)
- Privacy-Aware Mediation (Cranor et al., 2002)
status: ACCEPTED
title: Conflict Resolution Strategies
---

# ADR-0082c: Conflict Resolution Strategies

**Status:** Proposed
**Date:** 2025-10-22
**Parent ADR:** ADR-0082 (Multi-Party Dialogue Coordination)
**Related ADRs:** ADR-0069 (Affect Modulation), ADR-0081 (K0 Knowledge Graph - Meta Policy), ADR-0052d (Proactive Risk Confirmation)

---

## Context

### **Problem Statement**

Multi-party conversations inevitably produce **conflicting requests** when family members have:
- **Opposing goals:** Dad wants steakhouse, Mom wants vegetarian restaurant
- **Resource conflicts:** Same device, different commands (Dad: "play rock music", Mom: "play classical")
- **Timing conflicts:** Competing urgent actions (Dad: "turn up heat", Mom: "open windows for fresh air")

**Traditional chatbot approach:** Process requests sequentially, ignore conflicts → **leads to frustration**

```
WITHOUT Conflict Resolution:
Dad: "Book dinner at steakhouse tonight"
System: "Booking steakhouse for 7pm..."
Mom (immediately after): "Actually, let's do vegetarian restaurant"
System: "Booking vegetarian restaurant for 7pm..." [Cancels Dad's booking without asking]
Dad: "Wait, I didn't agree to that!" [FRUSTRATED]
```

**FamilyOS LLM-Powered Approach:** Detect conflicts, apply mediation strategies, reach consensus

```
WITH Conflict Resolution:
Dad: "Book dinner at steakhouse tonight"
Mom: "Actually, let's do vegetarian restaurant"
System (Conflict Detector): [steakhouse vs vegetarian] → GOAL CONFLICT
System (Mediation): "I heard conflicting preferences - Dad suggested steakhouse, Mom suggested vegetarian. Which would you both prefer?"
[Users negotiate offline]
Mom: "Vegetarian is fine - I have dietary restrictions"
Dad: "Okay, vegetarian works"
System: "Great, booking vegetarian restaurant for 7pm"
```

---

## Decision

### **Conflict Taxonomy**

**Type 1: Goal Conflicts** (Opposing Actions)

Examples:
- Dad: "Book steakhouse" vs Mom: "Book vegetarian restaurant"
- Dad: "Play loud music" vs Mom: "Keep quiet, baby sleeping"
- Dad: "Turn up heat" vs Mom: "Open windows"

**Detection Method:** Compare action verbs + target entities

```python
def detect_goal_conflict(action_a: dict, action_b: dict) -> bool:
    """Detect if two actions are mutually exclusive"""
    # Example: "book steakhouse" vs "book vegetarian"
    if (action_a["verb"] == action_b["verb"] and
        action_a["target"] != action_b["target"]):
        return True

    # Example: "turn_up heat" vs "open_windows" (thermal conflict)
    opposing_pairs = [
        ("turn_up_heat", "open_windows"),
        ("play_loud_music", "enable_quiet_mode"),
        ("lights_on", "lights_off")
    ]

    action_pair = (action_a["verb"], action_b["verb"])
    return action_pair in opposing_pairs or action_pair[::-1] in opposing_pairs
```

**Type 2: Timing Conflicts** (Same Resource, Different Times)

Examples:
- Dad: "Schedule meeting 3pm" vs Mom: "Schedule dentist 3pm"
- Dad: "Play music now" vs Mom: "Play podcast now"

**Detection Method:** Resource overlap + temporal collision

```python
def detect_timing_conflict(action_a: dict, action_b: dict) -> bool:
    """Detect if two actions compete for same resource at same time"""
    # Same resource?
    if action_a["resource"] != action_b["resource"]:
        return False

    # Temporal overlap?
    overlap_start = max(action_a["start_time"], action_b["start_time"])
    overlap_end = min(action_a["end_time"], action_b["end_time"])

    return overlap_start < overlap_end  # Conflict if overlap exists
```

**Type 3: Priority Conflicts** (Both Want Urgency)

Examples:
- Dad (urgent): "I need weather forecast NOW for flight"
- Mom (urgent): "I need grocery list NOW for shopping"

**Detection Method:** Dual high-urgency flags (both >0.7)

```python
def detect_priority_conflict(action_a: dict, action_b: dict) -> bool:
    """Detect if both actions claim high priority"""
    URGENCY_THRESHOLD = 0.7
    return (action_a["urgency"] >= URGENCY_THRESHOLD and
            action_b["urgency"] >= URGENCY_THRESHOLD)
```

### **Mediation Strategies**

**Strategy 1: Explicit Confirmation (Default - Conservative)**

```
Goal: Get explicit consensus from users before proceeding

Flow:
Dad: "Book steakhouse"
Mom: "Book vegetarian restaurant"
  ↓
System: "I heard conflicting preferences:
  - Dad suggested steakhouse
  - Mom suggested vegetarian restaurant
Which would you both prefer?"
  ↓
[Users negotiate offline - system waits]
  ↓
Mom: "Vegetarian please"
Dad: "Fine with me"
  ↓
System: "Great, booking vegetarian restaurant for 7pm"
```

**When to Use:**
- **Default strategy** for most conflicts
- **Low confidence** in automated resolution (<0.7)
- **First-time conflict** (system learning family preferences)

**Pros:** Safe, respects user autonomy, builds trust
**Cons:** Adds latency (+2-5 seconds for negotiation), requires manual intervention

**Strategy 2: Sentiment-Based Priority (Adaptive)**

```
Goal: Prioritize speaker with higher emotional urgency

Flow:
Dad: "Book steakhouse" [Sentiment: neutral, urgency=0.3]
Mom: "Actually, vegetarian restaurant" [Sentiment: assertive, urgency=0.7]
  ↓
Sentiment Analysis (ADR-0069):
  - Dad: neutral (0.3 urgency)
  - Mom: assertive (0.7 urgency) → HIGHER URGENCY
  ↓
System: "Prioritizing Mom's preference (vegetarian) based on urgency. Dad, is that okay?"
  ↓
Dad: "Sure" OR Dad: "No, I really want steakhouse"
  ↓
System: [Proceed with vegetarian OR escalate to explicit confirmation]
```

**When to Use:**
- **Clear sentiment divergence** (one speaker >0.7 urgency, other <0.5)
- **Learned family pattern** (system observed Mom's dietary needs usually prioritized)

**Pros:** Faster resolution (+1-2 seconds vs +2-5 for explicit), adapts to family dynamics
**Cons:** Risk of wrong priority if sentiment misread

**Strategy 3: Meta Policy Learned Norms (Intelligent)**

```
Goal: Apply learned family rules to resolve conflicts automatically

Flow:
Dad: "Book steakhouse"
Mom: "Book vegetarian restaurant"
  ↓
Meta Policy Query (via K0 Knowledge Graph ADR-0081):
  GET_NORM(context="dietary_restrictions")
  ↓
  Returns: {
    "rule": "dietary_restrictions_always_prioritize",
    "confidence": 0.87,
    "learned_from": 20  # 20 past conflicts
  }
  ↓
System: "Following family dietary rules, I'll book a vegetarian restaurant. Dad, this aligns with Mom's restrictions - okay?"
  ↓
Dad: "Yes" OR Dad: "No, let's discuss"
  ↓
System: [Proceed with vegetarian OR escalate to explicit confirmation]
```

**When to Use:**
- **High-confidence norms** (learned from >15 interactions, confidence >0.8)
- **Consistent family patterns** (dietary, cost, privacy rules)

**Pros:** Fastest resolution (+500ms confirmation vs +2-5s explicit), feels intelligent
**Cons:** Requires training data (15+ interactions), risk of over-generalizing

**Meta Policy Norm Examples:**

```yaml
# Family norm database (stored in K0 via ADR-0081 Knowledge Graph)
norms:
  - rule_id: "dietary_restrictions_prioritize"
    description: "Mom's dietary restrictions (vegetarian, gluten-free) always take precedence"
    confidence: 0.87
    learned_from: 20  # 20 conflicts where Mom's diet won
    contexts: ["restaurant_booking", "grocery_shopping", "meal_planning"]

  - rule_id: "quiet_hours_after_9pm"
    description: "No loud activities after 9pm (baby bedtime)"
    confidence: 0.92
    learned_from: 30  # 30 rejections of loud requests after 9pm
    contexts: ["music_playback", "smart_home_control", "tv_volume"]

  - rule_id: "cost_threshold_$100"
    description: "Ask before booking anything >$100"
    confidence: 0.78
    learned_from: 12  # 12 proactive confirmations on expensive items
    contexts: ["restaurant_booking", "shopping", "travel"]
```

**Strategy 4: Time-Based Deferral (Contextual)**

```
Goal: Defer to context-aware rules (time, location, occupancy)

Flow:
Dad: "Play loud music" [Time: 11pm]
Mom: "Please don't, baby is sleeping" [Baby_sleeping: true]
  ↓
Context Check:
  - Current time: 23:00 (11pm)
  - Meta Policy: "No loud activities after 21:00 (9pm)"
  - Ambient Context: baby_sleeping=true
  ↓
System: "It's 11pm and the baby is sleeping. I'll defer to Mom's preference for quiet. Dad, how about headphones instead?"
```

**When to Use:**
- **Time-based rules** (quiet hours, work hours, family time)
- **Contextual overrides** (baby sleeping, guests present, meeting in progress)

**Pros:** Respects context, feels intelligent
**Cons:** Requires ambient sensors (ADR-0050e Device Presence, baby monitors)

### **Mediation Loop with Max Attempts**

**Problem:** Endless back-and-forth if users can't decide

```
System: "Steakhouse or vegetarian?"
Dad: "Steakhouse"
Mom: "Vegetarian"
System: "Still conflicting. Final decision?"
Dad: "Steakhouse!"
Mom: "Vegetarian!"
System: [Stuck in loop - frustration increases]
```

**Solution: Max 3 Mediation Attempts → Escalate**

```python
MAX_MEDIATION_ATTEMPTS = 3

mediation_count = 0
consensus_reached = False

while not consensus_reached and mediation_count < MAX_MEDIATION_ATTEMPTS:
    mediation_count += 1

    # Attempt mediation
    system_prompt = generate_mediation_prompt(conflict, strategy)
    user_response = await get_user_response(system_prompt)

    # Check if consensus reached
    consensus_reached = detect_consensus(user_response)

if not consensus_reached:
    # Escalation: Defer to offline decision
    system_response = (
        "I've tried to help resolve this {mediation_count} times, "
        "but you still have conflicting preferences. "
        "Please decide offline and let me know what you'd like."
    )
    # Clear conflict state, wait for explicit command
```

### **Conflict Resolution Decision Tree**

```
┌─────────────────────────────────────────────────────────────────────────┐
│ CONFLICT DETECTOR: Opposing Requests Detected                           │
├─────────────────────────────────────────────────────────────────────────┤
│ Input: [Dad: "Book steakhouse", Mom: "Book vegetarian"]                 │
│   ↓                                                                      │
│ Step 1: Classify Conflict Type                                          │
│   - Goal conflict? YES (steakhouse vs vegetarian)                       │
│   - Timing conflict? NO                                                  │
│   - Priority conflict? NO (both low urgency)                             │
│   ↓                                                                      │
│ Step 2: Query Meta Policy (K0 Knowledge Graph)                          │
│   - GET_NORM(context="dietary_restrictions")                            │
│   - Returns: {rule: "dietary_restrictions_prioritize", confidence: 0.87} │
│   ↓                                                                      │
│ Step 3: Check Norm Confidence                                           │
│   - Confidence: 0.87 (>0.8 threshold) → HIGH CONFIDENCE                 │
│   ↓                                                                      │
│ Step 4: Select Mediation Strategy                                       │
│   ├─ IF norm confidence >= 0.8:                                         │
│   │     → Strategy 3: Meta Policy Learned Norms                         │
│   ├─ ELSE IF sentiment divergence >= 0.3:                               │
│   │     → Strategy 2: Sentiment-Based Priority                          │
│   └─ ELSE:                                                               │
│         → Strategy 1: Explicit Confirmation                              │
│   ↓                                                                      │
│ Step 5: Apply Mediation (with max 3 attempts)                           │
│   - Attempt 1: "Following family dietary rules, vegetarian okay Dad?"   │
│   - Dad: "Yes" → CONSENSUS REACHED                                      │
│   ↓                                                                      │
│ Step 6: Execute Consensus Action                                        │
│   - Book vegetarian restaurant                                          │
│   - Update Meta Policy: Increment "dietary_restrictions_prioritize" confidence │
└─────────────────────────────────────────────────────────────────────────┘
```

### **Integration with ADR-0069 (Affect Modulation)**

**Sentiment Divergence Detection:**

```python
# Detect emotional tone differences between speakers
from k1.l3_execution.affect.sentiment_analyzer import analyze_sentiment

dad_sentiment = analyze_sentiment(dad_utterance)
# Returns: {"valence": 0.5, "arousal": 0.3, "emotion": "neutral"}

mom_sentiment = analyze_sentiment(mom_utterance)
# Returns: {"valence": 0.4, "arousal": 0.7, "emotion": "assertive"}

sentiment_divergence = abs(mom_sentiment["arousal"] - dad_sentiment["arousal"])
# 0.7 - 0.3 = 0.4 (significant divergence)

if sentiment_divergence >= 0.3:
    # Apply Strategy 2: Sentiment-Based Priority
    prioritize_speaker = "Mom" if mom_sentiment["arousal"] > dad_sentiment["arousal"] else "Dad"
```

**Emotional De-Escalation:**

```python
# If conflict detected + high emotional arousal → use calming language
if conflict_detected and max(dad_arousal, mom_arousal) >= 0.7:
    mediation_tone = "calm_empathetic"
    system_prompt = (
        "I sense some tension here. Let's take a moment - "
        "Dad wants steakhouse, Mom wants vegetarian. "
        "Both are valid choices. What works best for both of you?"
    )
else:
    mediation_tone = "neutral"
    system_prompt = (
        "I heard conflicting preferences - "
        "steakhouse vs vegetarian. "
        "Which would you prefer?"
    )
```

### **Performance Budget**

| **Operation** | **Target (P95)** | **Implementation** |
|---------------|------------------|-------------------|
| Conflict Detection | <50ms | Goal/timing/priority comparison (lightweight) |
| Meta Policy Query | <30ms | K0 Knowledge Graph norm lookup (indexed) |
| Sentiment Analysis | <70ms | ADR-0069 affect modulation (cached embeddings) |
| Mediation Prompt Generation | <50ms | Template-based with speaker names |
| **Total Conflict Resolution** | **<100ms** | Sum of above (excludes user response wait time) |

**Note:** User response wait time (1-5 seconds) not included in budget (external dependency)

---

## Consequences

### **Positive**

1. **Graceful Conflict Handling:** System doesn't blindly execute conflicting actions (prevents frustration)
2. **Intelligent Mediation:** Learns family norms over time (feels adaptive, not rigid)
3. **Emotional Awareness:** Detects sentiment divergence, adapts tone (de-escalation)
4. **User Autonomy:** Explicit confirmation strategy respects user control (builds trust)
5. **Escalation Safety:** Max 3 attempts prevents endless loops (graceful degradation)

### **Negative**

1. **Latency Overhead:** Explicit confirmation adds +2-5 seconds (acceptable for conflict resolution)
2. **Learning Curve:** Meta Policy requires 15+ interactions to reach confidence (slow start)
3. **Misclassification Risk:** 5-10% conflict detection errors (mitigated by explicit confirmation fallback)
4. **Complexity:** 4 mediation strategies increase testing surface (more edge cases)
5. **Privacy Sensitivity:** Family norms stored in K0 (must encrypt, restrict access)

### **Risks & Mitigations**

| **Risk** | **Impact** | **Mitigation** |
|----------|------------|----------------|
| Wrong priority (system picks wrong speaker) | HIGH | Default to explicit confirmation (Strategy 1) if confidence <0.8 |
| Norm overgeneralization (rule applied incorrectly) | MEDIUM | Max 3 mediation attempts → escalate if conflict persists |
| Sentiment misread (neutral detected as urgent) | MEDIUM | Combine keyword + sentiment analysis, confidence thresholds |
| Endless mediation loop (users can't decide) | LOW | Max 3 attempts → defer to offline decision |
| Privacy leak (family norms exposed) | HIGH | Encrypt norms in K0 (AES-256-GCM per ADR-0036), restrict access |

---

## Implementation Guidance

### **Conflict Detector State Machine**

```python
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional

class ConflictType(Enum):
    GOAL_CONFLICT = "goal_conflict"
    TIMING_CONFLICT = "timing_conflict"
    PRIORITY_CONFLICT = "priority_conflict"

class MediationStrategy(Enum):
    EXPLICIT_CONFIRMATION = "explicit_confirmation"
    SENTIMENT_PRIORITY = "sentiment_priority"
    META_POLICY_NORMS = "meta_policy_norms"
    TIME_BASED_DEFERRAL = "time_based_deferral"

@dataclass
class ConflictEvent:
    conflict_id: str
    conflict_type: ConflictType
    speakers: List[str]
    actions: List[dict]
    mediation_strategy: MediationStrategy
    mediation_attempts: int
    consensus_reached: bool

class ConflictResolver:
    def __init__(self, kg_client, affect_analyzer, meta_policy):
        self.kg_client = kg_client  # K0 Knowledge Graph
        self.affect_analyzer = affect_analyzer  # ADR-0069
        self.meta_policy = meta_policy  # Norm engine
        self.MAX_ATTEMPTS = 3

    def detect_conflict(self, actions: List[dict]) -> Optional[ConflictEvent]:
        """Detect if multiple actions are conflicting"""
        if len(actions) < 2:
            return None

        # Check all pairs
        for i in range(len(actions)):
            for j in range(i+1, len(actions)):
                action_a, action_b = actions[i], actions[j]

                # Goal conflict?
                if self._is_goal_conflict(action_a, action_b):
                    return ConflictEvent(
                        conflict_id=generate_id(),
                        conflict_type=ConflictType.GOAL_CONFLICT,
                        speakers=[action_a["speaker_id"], action_b["speaker_id"]],
                        actions=[action_a, action_b],
                        mediation_strategy=None,  # To be determined
                        mediation_attempts=0,
                        consensus_reached=False
                    )

                # Timing conflict?
                if self._is_timing_conflict(action_a, action_b):
                    return ConflictEvent(
                        conflict_type=ConflictType.TIMING_CONFLICT,
                        # ... similar structure
                    )

                # Priority conflict?
                if self._is_priority_conflict(action_a, action_b):
                    return ConflictEvent(
                        conflict_type=ConflictType.PRIORITY_CONFLICT,
                        # ... similar structure
                    )

        return None

    def select_mediation_strategy(self, conflict: ConflictEvent) -> MediationStrategy:
        """Select best mediation strategy for conflict"""
        # Query Meta Policy for learned norms
        norm = self.meta_policy.get_norm(context=conflict.actions[0]["context"])

        if norm and norm["confidence"] >= 0.8:
            return MediationStrategy.META_POLICY_NORMS

        # Check sentiment divergence
        sentiments = [
            self.affect_analyzer.analyze(action["utterance"])
            for action in conflict.actions
        ]
        sentiment_divergence = abs(sentiments[0]["arousal"] - sentiments[1]["arousal"])

        if sentiment_divergence >= 0.3:
            return MediationStrategy.SENTIMENT_PRIORITY

        # Default to explicit confirmation
        return MediationStrategy.EXPLICIT_CONFIRMATION

    async def mediate(self, conflict: ConflictEvent) -> dict:
        """Apply mediation strategy to resolve conflict"""
        strategy = self.select_mediation_strategy(conflict)

        for attempt in range(self.MAX_ATTEMPTS):
            conflict.mediation_attempts += 1

            # Generate mediation prompt
            prompt = self._generate_mediation_prompt(conflict, strategy)

            # Get user response
            response = await self._get_user_response(prompt)

            # Check for consensus
            if self._detect_consensus(response):
                conflict.consensus_reached = True
                return {"status": "resolved", "action": response["agreed_action"]}

        # Max attempts reached → escalate
        return {
            "status": "escalated",
            "message": "Please decide offline and let me know"
        }
```

### **Metrics & Observability**

```python
from prometheus_client import Histogram, Counter, Gauge

conflict_detections_total = Counter(
    'conflict_detections_total',
    'Total conflict detections',
    ['conflict_type']  # goal, timing, priority
)

mediation_strategy_used = Counter(
    'mediation_strategy_used',
    'Mediation strategy applied',
    ['strategy']  # explicit_confirmation, sentiment_priority, meta_policy, time_deferral
)

mediation_success_rate = Gauge(
    'mediation_success_rate',
    'Percentage of conflicts resolved (not escalated)'
)

mediation_attempts_histogram = Histogram(
    'mediation_attempts',
    'Number of attempts before resolution or escalation',
    buckets=[1, 2, 3, 4]
)

conflict_resolution_latency_ms = Histogram(
    'conflict_resolution_latency_ms',
    'Time to resolve conflict (excludes user response time)',
    buckets=[50, 100, 200, 500, 1000]
)
```

---

## References

### **Research Papers**

1. **De Dreu & Gelfand (2008):** "Conflict in the Workplace: Sources, Functions, and Dynamics Across Multiple Levels of Analysis" - Stanford University
2. **Pruitt & Rubin (1986):** "Social Conflict: Escalation, Stalemate, and Settlement" - NYU
3. **Fisher & Ury (1981):** "Getting to Yes: Negotiating Agreement Without Giving In" - Harvard Negotiation Project
4. **Deutsch (1973):** "The Resolution of Conflict: Constructive and Destructive Processes" - Columbia University

### **Related ADRs**

- **ADR-0069:** Affect Modulation (sentiment analysis for urgency/divergence detection)
- **ADR-0081:** K0 Knowledge Graph (Meta Policy norm storage and learning)
- **ADR-0052d:** Proactive Risk Confirmation (HITL integration for explicit confirmation)
- **ADR-0082a:** Speaker Diarization (speaker_id attribution for conflict detection)
- **ADR-0082b:** Multi-Party Turn-Taking (overlap detection feeds into conflict detection)

---

## Changelog

- **2025-10-22:** Initial proposal for Conflict Resolution Strategies (Sub-ADR of ADR-0082)

---

**Next Steps:**

1. **Conflict Taxonomy Validation:** Test goal/timing/priority detection on 100 sample conflicts (2 weeks)
2. **Meta Policy Integration:** Build norm learning loop with K0 Knowledge Graph (3 weeks)
3. **Sentiment Analysis Integration:** Connect ADR-0069 affect modulation for urgency detection (1 week)
4. **Mediation Prompt Templates:** Create 4 strategy-specific prompt templates (1 week)
5. **WARD Testing:** Multi-speaker conflict scenarios (escalation, consensus, max attempts) (2 weeks)