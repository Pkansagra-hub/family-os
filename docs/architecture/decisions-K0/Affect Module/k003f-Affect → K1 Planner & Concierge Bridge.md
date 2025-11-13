---
adr_number: '0012f'
parent_adr: '0012'
affected_layers:
  - K0 Memory Kernel
  - K1 Intelligence Layer
  - Cognitive Services
affected_modules:
  - affect
  - k1.planner
  - k1.concierge
  - workspace
authors:
  - '@K0-Architecture'
  - '@K1-Architecture'
concerns:
  - architecture
  - integration
  - ux
  - safety
date_created: '2025-11-13'
date_updated: '2025-11-13'
implementation_status: ACCEPTED
status: ACCEPTED
title: 'ADR-0012f: Affect → K1 Planner & Concierge Bridge'
---

# ADR-0012f: Affect → K1 Planner & Concierge Bridge

**Status**: Accepted  
**Parent ADR**: ADR-0012 (Affect Module)  
**Date**: 2025-11-13  
**Authors**: @K0-Architecture, @K1-Architecture

---

## Context

ADR-0012 defines the **Affect Module** (valence/arousal sensing), and ADR-0012e defines **Policy Band Rules** (GREEN/AMBER/RED/BLACK). This ADR specifies:

1. **K1 Consumption**: How K1 Planner and Concierge read affect state from K0
2. **Behavior Adaptation**: How K1 adjusts planning, UX, and topic selection based on affect
3. **Contracts**: Data structures for affect summaries in SessionState and Workspace
4. **Integration Points**: Where affect state flows into K1 decision-making

**Goals**:

- **Emotion-aware UX**: K1 adapts behavior to user's emotional state
- **Safety-aware planning**: K1 respects policy bands (avoid triggering during distress)
- **Gentle interaction**: K1 enters "slow mode" during high arousal
- **Personalized timing**: K1 chooses optimal moments for reminders/suggestions
- **Explainable**: Users understand why K1 behaved differently

**Key Use Cases**:

- **High arousal → slow mode**: "User frustrated" → K1 slows down, confirms actions, avoids complex decisions
- **Distress → gentle behavior**: "User sad" → K1 offers calming content, postpones non-urgent tasks
- **Positive mood → opportunity**: "User happy" → K1 suggests memory recall, planning, creative tasks
- **Conflict detected → stay quiet**: "Household conflict" → K1 minimizes notifications, waits for calm
- **Bedtime arousal → wind down**: "Minor aroused at night" → K1 suggests calming activities, dims notifications

---

## Decision

### 1. Affect Summary Contract

**Data Structure** (in SessionState and Workspace):

```python
@dataclass
class AffectSummary:
    """
    Affect state summary for K1 consumption.
    
    Computed from K0 AffectEMAState and policy bands.
    """
    # Per-person affect
    person_id: str
    valence: float              # [-1, 1] from EMA
    arousal: float              # [0, 1] from EMA
    confidence: float           # [0, 1]
    
    # Policy band
    band: str                   # "GREEN", "AMBER", "RED", "BLACK"
    band_reasons: list[str]     # Human-readable reasons
    
    # Mood descriptors
    mood_label: str             # "calm", "happy", "excited", "stressed", "sad", "frustrated"
    trend: str                  # "improving", "declining", "stable"
    
    # Household context
    household_state: Optional['HouseholdAffectSummary'] = None
    
    # Metadata
    last_updated: float
    n_events_in_window: int     # Events used for EMA (data quality indicator)


@dataclass
class HouseholdAffectSummary:
    """
    Household-level affect summary.
    """
    space_id: str
    
    # Aggregated metrics
    valence_avg: float
    arousal_avg: float
    
    # Conflict detection
    conflict_active: bool
    conflict_participants: list[str]
    
    # Family moments
    family_moment_active: bool
    
    # Metadata
    n_active_members: int
    last_updated: float
```

**Mood Label Mapping** (from valence × arousal):

```python
def compute_mood_label(valence: float, arousal: float) -> str:
    """
    Map (valence, arousal) to mood descriptor.
    
    Uses Russell's Circumplex Model of Affect.
    """
    if arousal < 0.3:
        # Low arousal
        if valence > 0.3:
            return "calm"          # Positive + low arousal
        elif valence < -0.3:
            return "sad"           # Negative + low arousal
        else:
            return "neutral"       # Neutral + low arousal
    
    elif arousal < 0.6:
        # Moderate arousal
        if valence > 0.3:
            return "happy"         # Positive + moderate arousal
        elif valence < -0.3:
            return "worried"       # Negative + moderate arousal
        else:
            return "alert"         # Neutral + moderate arousal
    
    else:
        # High arousal
        if valence > 0.3:
            return "excited"       # Positive + high arousal
        elif valence < -0.3:
            return "frustrated"    # Negative + high arousal (or "angry", "stressed")
        else:
            return "stressed"      # Neutral + high arousal
```

**Circumplex Model Visualization**:

```
       High Arousal
            |
   Excited  |  Stressed
       \    |    /
        \   |   /
Positive ---|--- Negative
        /   |   \
       /    |    \
    Happy   |   Worried
            |
        Low Arousal
     (Calm/Sad)
```

---

### 2. K1 Access Patterns

**Reading Affect State**:

```python
# In K1 Planner
from k0.modules.affect import AffectService

affect_service = AffectService()

# Get current affect for active user
affect_summary = affect_service.get_affect_summary(
    person_id="person_abc",
    space_id="home"
)

# Access affect state
print(f"Valence: {affect_summary.valence:.2f}")
print(f"Arousal: {affect_summary.arousal:.2f}")
print(f"Band: {affect_summary.band}")
print(f"Mood: {affect_summary.mood_label}")
print(f"Trend: {affect_summary.trend}")

# Access household context
if affect_summary.household_state:
    if affect_summary.household_state.conflict_active:
        print("Household conflict detected - entering quiet mode")
```

**Integration into SessionState**:

```python
@dataclass
class SessionState:
    """
    K1 session state (per conversation/interaction).
    """
    session_id: str
    person_id: str
    space_id: str
    
    # Existing fields
    conversation_history: list[Message]
    active_plan: Optional[Plan]
    
    # NEW: Affect state
    affect: AffectSummary
    
    # Behavior modifiers derived from affect
    slow_mode: bool             # High arousal → slow down
    gentle_mode: bool           # Distress → gentle interaction
    quiet_mode: bool            # Conflict → minimize notifications
    
    # Metadata
    created_at: float
    last_updated: float
```

**Integration into Workspace (Global)**:

```python
@dataclass
class WorkspaceState:
    """
    Global workspace (shared cognitive state across agents).
    """
    # Existing fields
    active_agents: list[AgentContext]
    shared_memory: dict
    
    # NEW: Household affect state
    household_affect: HouseholdAffectSummary
    
    # Household-wide behavior modifiers
    household_quiet_mode: bool  # Conflict active → all agents stay quiet
    
    # Metadata
    last_updated: float
```

---

### 3. K1 Behavior Adaptation

#### 3.1 Slow Mode (High Arousal)

**Trigger**: `arousal > 0.7` OR `band == "RED"` OR `band == "AMBER"`

**Behavior Changes**:

| Component | Normal Mode | Slow Mode |
|-----------|-------------|-----------|
| **Response Time** | Immediate | +2 second delay before response |
| **Confirmation Prompts** | Skip for simple actions | Confirm all actions |
| **Plan Complexity** | Multi-step plans allowed | Single-step plans only |
| **UX Pacing** | Fast, efficient | Slow, deliberate |
| **Interruptions** | Allow | Minimize (only urgent) |
| **Options Presented** | 5-7 choices | 2-3 choices |

**Implementation**:

```python
class K1Planner:
    def __init__(self):
        self.affect_service = AffectService()
    
    def plan_next_action(self, session: SessionState) -> Plan:
        """
        Generate next action plan, adapting to affect state.
        """
        affect = session.affect
        
        # Check slow mode
        if affect.arousal > 0.7 or affect.band in ["RED", "AMBER"]:
            session.slow_mode = True
            logger.info(f"Entering slow mode: arousal={affect.arousal:.2f}, band={affect.band}")
        
        # Generate plan
        if session.slow_mode:
            plan = self._generate_simple_plan(session)
            plan.require_confirmation = True
            plan.response_delay_seconds = 2.0
        else:
            plan = self._generate_normal_plan(session)
        
        return plan
```

**User Experience**:

```
[High Arousal Detected]

Normal Mode:
User: "Book a flight to NYC"
K1: "Done! Flight booked for tomorrow at 6am."

Slow Mode:
User: "Book a flight to NYC"
K1: [2 second pause]
    "I found a flight to NYC tomorrow at 6am for $350.
     Would you like me to book this?"
User: "Yes"
K1: "Confirmed! Flight booked."
```

#### 3.2 Gentle Mode (Distress)

**Trigger**: `valence < -0.5` OR `band == "RED"` OR `mood_label in ["sad", "frustrated"]`

**Behavior Changes**:

| Component | Normal Mode | Gentle Mode |
|-----------|-------------|-------------|
| **Tone** | Neutral, efficient | Warm, empathetic |
| **Content Suggestions** | Task-oriented | Calming, comforting |
| **Recall Bias** | Balanced | Favor positive memories |
| **Task Postponement** | Prompt for all tasks | Defer non-urgent tasks |
| **Notification Volume** | Normal | Reduced (urgent only) |

**Implementation**:

```python
def generate_response(self, session: SessionState, user_input: str) -> str:
    """
    Generate K1 response, adapting tone to affect state.
    """
    affect = session.affect
    
    # Check gentle mode
    if affect.valence < -0.5 or affect.mood_label in ["sad", "frustrated"]:
        session.gentle_mode = True
        tone = "empathetic"
    else:
        session.gentle_mode = False
        tone = "neutral"
    
    # Generate response with appropriate tone
    response = self.llm.generate(
        prompt=user_input,
        tone=tone,
        context=session.conversation_history
    )
    
    # Add calming suggestions if in gentle mode
    if session.gentle_mode:
        response += self._add_calming_suggestions(affect)
    
    return response


def _add_calming_suggestions(self, affect: AffectSummary) -> str:
    """
    Suggest calming activities based on affect state.
    """
    suggestions = []
    
    if affect.arousal > 0.6:
        suggestions.append("Would you like to try a breathing exercise?")
    
    if affect.mood_label == "sad":
        suggestions.append("I can show you some happy memories if you'd like.")
    
    if affect.mood_label == "frustrated":
        suggestions.append("I'll defer non-urgent tasks for now. Take your time.")
    
    return "\n\n" + " ".join(suggestions) if suggestions else ""
```

**User Experience**:

```
[Distress Detected: valence=-0.65, mood=sad]

Normal Mode:
K1: "You have 5 tasks due today. Which would you like to start with?"

Gentle Mode:
K1: "I noticed you seem a bit down today. I'll defer non-urgent tasks for now.
     Would you like to see some happy memories, or should I just stay out of the way?"
```

#### 3.3 Quiet Mode (Household Conflict)

**Trigger**: `household_affect.conflict_active == True`

**Behavior Changes**:

| Component | Normal Mode | Quiet Mode |
|-----------|-------------|------------|
| **Proactive Suggestions** | Frequent | Disabled |
| **Notifications** | All types | Urgent only |
| **Agent Presence** | Visible, active | Invisible, passive |
| **Recall Prompts** | "Remember when..." | Disabled |
| **Planning Suggestions** | "Let's plan..." | Disabled |

**Implementation**:

```python
class K1Concierge:
    def should_notify(self, notification: Notification, workspace: WorkspaceState) -> bool:
        """
        Decide whether to send notification based on household affect.
        """
        household = workspace.household_affect
        
        # Check quiet mode
        if household.conflict_active:
            workspace.household_quiet_mode = True
            logger.info("Household conflict detected - entering quiet mode")
            
            # Only allow urgent notifications
            if notification.priority != "urgent":
                logger.info(f"Suppressing non-urgent notification: {notification.title}")
                return False
        
        return True
    
    def generate_proactive_suggestion(self, workspace: WorkspaceState) -> Optional[str]:
        """
        Generate proactive suggestion, respecting quiet mode.
        """
        if workspace.household_quiet_mode:
            logger.info("Quiet mode active - no proactive suggestions")
            return None
        
        # Normal proactive behavior
        return self._generate_suggestion(workspace)
```

**User Experience**:

```
[Household Conflict Detected: 2 members with high arousal + negative valence]

Normal Mode:
K1: [Proactive notification]
    "Hey! Want to plan this weekend's camping trip?"

Quiet Mode:
K1: [Silent - no proactive notifications]
    [Only urgent notifications allowed, e.g., "Fire alarm triggered"]
```

#### 3.4 Wind-Down Mode (Bedtime Arousal)

**Trigger**: `is_minor AND time_of_day == "night" AND arousal > 0.5`

**Behavior Changes**:

| Component | Normal Mode | Wind-Down Mode |
|-----------|-------------|----------------|
| **Content Suggestions** | Any content | Calming content only |
| **Notification Brightness** | Normal | Dimmed |
| **Task Suggestions** | All tasks | Bedtime routine only |
| **Recall Bias** | Balanced | Favor calming memories |
| **Screen Time Hints** | None | "Time to wind down" |

**Implementation**:

```python
def suggest_next_activity(self, session: SessionState) -> str:
    """
    Suggest next activity, adapting to time-of-day and affect.
    """
    affect = session.affect
    
    # Check wind-down mode
    if session.person.is_minor and session.time_of_day == "night":
        if affect.arousal > 0.5:
            logger.info("Minor high arousal at bedtime - wind-down mode")
            return self._suggest_wind_down_activity(affect)
    
    # Normal activity suggestions
    return self._suggest_normal_activity(session)


def _suggest_wind_down_activity(self, affect: AffectSummary) -> str:
    """
    Suggest calming bedtime activities.
    """
    activities = [
        "Would you like to read a calming story?",
        "How about some quiet music?",
        "Let's try a short breathing exercise.",
        "Time to get ready for bed - want help with your routine?",
    ]
    
    # Choose based on arousal level
    if affect.arousal > 0.7:
        return "I notice you're pretty energized! Let's do a breathing exercise to wind down."
    else:
        return random.choice(activities)
```

**User Experience**:

```
[Minor, 9pm, arousal=0.72]

Normal Mode:
K1: "Want to play a game or watch a video?"

Wind-Down Mode:
K1: "I notice you're pretty energized, but it's getting late!
     Let's try a breathing exercise to wind down, then get ready for bed."
```

#### 3.5 Opportunity Mode (Positive Mood)

**Trigger**: `valence > 0.5 AND arousal < 0.6 AND band == "GREEN"`

**Behavior Changes**:

| Component | Normal Mode | Opportunity Mode |
|-----------|-------------|------------------|
| **Proactive Suggestions** | Occasional | Frequent |
| **Task Suggestions** | Urgent tasks | Creative/planning tasks |
| **Recall Prompts** | Balanced | Favor happy memories |
| **Planning Horizon** | Short-term | Long-term (vacations, goals) |
| **Social Suggestions** | Reactive | Proactive ("Call mom?") |

**Implementation**:

```python
def check_opportunity_window(self, session: SessionState) -> bool:
    """
    Detect optimal moment for proactive suggestions.
    """
    affect = session.affect
    
    # Check opportunity mode
    if (affect.valence > 0.5 and 
        affect.arousal < 0.6 and 
        affect.band == "GREEN"):
        
        logger.info("Opportunity window detected - user in positive, calm state")
        return True
    
    return False


def generate_opportunity_suggestion(self, session: SessionState) -> str:
    """
    Generate proactive suggestion during opportunity window.
    """
    suggestions = [
        "You seem to be in a great mood! Want to plan something fun for this weekend?",
        "Great time to look back at some happy memories - interested?",
        "Feeling good today! How about we tackle that project you've been thinking about?",
        "Perfect moment to call someone you've been meaning to catch up with!",
    ]
    
    return random.choice(suggestions)
```

**User Experience**:

```
[Positive Mood: valence=0.68, arousal=0.42, mood=happy]

Normal Mode:
K1: [Waits for user to initiate]

Opportunity Mode:
K1: [Proactive suggestion]
    "You seem to be in a great mood! Want to plan something fun for this weekend?"
```

---

### 4. Topic Selection & Content Filtering

**Content Bias Based on Affect**:

```python
class RecallEngine:
    def search_memories(self, 
                       query: str,
                       affect: AffectSummary,
                       limit: int = 10) -> list[Memory]:
        """
        Search memories, biasing results based on affect state.
        """
        # Base search
        results = self._semantic_search(query, limit=limit * 3)
        
        # Apply affect-based bias
        if affect.mood_label in ["sad", "frustrated"]:
            # Boost positive memories during distress
            results = self._boost_positive_memories(results, boost_factor=2.0)
        
        elif affect.mood_label in ["calm", "happy"]:
            # Balanced retrieval during positive states
            results = self._balanced_retrieval(results)
        
        elif affect.band == "RED":
            # Avoid triggering content during RED band
            results = self._filter_triggering_content(results)
        
        # Re-rank and return top k
        return results[:limit]
    
    def _boost_positive_memories(self, memories: list[Memory], boost_factor: float) -> list[Memory]:
        """
        Boost positive memories in ranking.
        """
        for mem in memories:
            if mem.affect_valence > 0.3:
                mem.relevance_score *= boost_factor
        
        return sorted(memories, key=lambda m: m.relevance_score, reverse=True)
    
    def _filter_triggering_content(self, memories: list[Memory]) -> list[Memory]:
        """
        Filter out potentially triggering content.
        """
        return [
            m for m in memories
            if m.band != "RED" and 
               m.affect_valence > -0.3 and
               "distressing" not in m.tags
        ]
```

---

### 5. Integration Points

**K1 Components That Consume Affect**:

| Component | Consumes | Behavior Adaptation |
|-----------|----------|---------------------|
| **Planner** | AffectSummary | Slow mode, plan complexity, confirmation prompts |
| **Concierge** | AffectSummary + HouseholdAffectSummary | Quiet mode, notification volume, proactive suggestions |
| **Recall Engine** | AffectSummary | Content bias, triggering content filtering |
| **Dialogue Manager** | AffectSummary | Tone adaptation, response pacing |
| **Task Scheduler** | AffectSummary | Task postponement, optimal timing |
| **Notification Service** | HouseholdAffectSummary | Quiet mode, urgency filtering |

**Data Flow**:

```
K0 Affect Module (per-event classification)
    ↓
EMA Smoothing (per person×space)
    ↓
Policy Banding (GREEN/AMBER/RED/BLACK)
    ↓
AffectSummary (compact representation)
    ↓
SessionState / Workspace (K1 state)
    ↓
K1 Components (Planner, Concierge, Recall, etc.)
    ↓
Behavior Adaptation (slow mode, gentle mode, quiet mode, etc.)
```

---

### 6. Observability & Metrics

**Affect-Driven Metrics**:

```python
# Prometheus metrics
affect_slow_mode_activations = Counter(
    "k1_affect_slow_mode_activations_total",
    "Number of slow mode activations"
)

affect_gentle_mode_activations = Counter(
    "k1_affect_gentle_mode_activations_total",
    "Number of gentle mode activations"
)

affect_quiet_mode_activations = Counter(
    "k1_affect_quiet_mode_activations_total",
    "Number of quiet mode activations"
)

affect_notification_suppressions = Counter(
    "k1_affect_notification_suppressions_total",
    "Notifications suppressed due to affect state"
)

affect_content_bias_applications = Counter(
    "k1_affect_content_bias_applications_total",
    "Content bias applications in recall",
    ["bias_type"]  # "positive_boost", "trigger_filter"
)

affect_opportunity_suggestions = Counter(
    "k1_affect_opportunity_suggestions_total",
    "Proactive suggestions during opportunity windows"
)
```

**User Feedback Metrics**:

```python
# Track effectiveness of affect-driven behaviors
affect_behavior_feedback = Histogram(
    "k1_affect_behavior_feedback",
    "User satisfaction with affect-driven behaviors",
    ["behavior_mode", "feedback_type"]  # slow_mode/gentle_mode, positive/negative
)

# Example usage
affect_behavior_feedback.observe(
    0.8,  # Satisfaction score
    ["slow_mode", "positive"]
)
```

---

### 7. User Controls & Transparency

**Settings UI**:

```
Affect-Aware Behaviors
├─ Enable affect-aware UX [ON/OFF]
├─ Slow Mode Sensitivity [Low/Medium/High]
├─ Gentle Mode Sensitivity [Low/Medium/High]
├─ Quiet Mode (Household Conflict) [ON/OFF]
├─ Wind-Down Mode (Bedtime) [ON/OFF]
└─ Show affect state in UI [ON/OFF]
```

**Transparency Display** (in K1 UI):

```
Current Mood: Happy 😊
Arousal: Moderate
Band: GREEN

K1 Behavior:
- Normal mode (responsive and efficient)
- Proactive suggestions enabled
```

**Explanation on Demand**:

```
User: "Why did K1 slow down?"

K1: "I noticed you seemed a bit stressed (high arousal detected),
     so I switched to slow mode to give you more time to think.
     You can adjust this in Settings → Affect-Aware Behaviors."
```

---

## Consequences

### Positive

✅ **Emotion-aware UX**: K1 adapts to user's emotional state  
✅ **Safety-aware**: Respects policy bands, avoids triggering during distress  
✅ **Gentle interaction**: Slow mode, gentle mode, quiet mode improve UX  
✅ **Personalized timing**: Opportunity mode leverages positive moments  
✅ **Explainable**: Users understand why K1 behaved differently  
✅ **User control**: Settings allow customization of affect-driven behaviors  

### Negative

❌ **Complexity**: Multiple behavior modes increase K1 logic complexity  
❌ **False positives**: Incorrect affect state may cause unwanted behavior changes  
❌ **User confusion**: Unexpected behavior changes may confuse users  
❌ **Performance overhead**: Affect state lookups add latency  

### Risks

- **Over-adaptation**: K1 may become too passive (e.g., always in quiet mode)
- **Under-adaptation**: K1 may miss genuine distress signals
- **Privacy concerns**: Users may not want K1 "reading their emotions"
- **Cultural variation**: Affect-driven behaviors may not generalize across cultures

**Mitigation**:

- **User feedback**: P06 feedback loop to tune behavior thresholds
- **Transparent**: Show affect state and behavior mode in UI
- **User control**: Allow disabling affect-aware behaviors
- **A/B testing**: Validate behavior changes improve UX before wide rollout
- **Rollback**: Feature flag to disable affect-driven behaviors

---

## Implementation Checklist

- [ ] Add `AffectSummary` to SessionState contract
- [ ] Add `HouseholdAffectSummary` to WorkspaceState contract
- [ ] Implement `get_affect_summary()` in K0 Affect Module
- [ ] Implement slow mode in K1 Planner
- [ ] Implement gentle mode in K1 Dialogue Manager
- [ ] Implement quiet mode in K1 Concierge
- [ ] Implement wind-down mode for minors
- [ ] Implement opportunity mode for proactive suggestions
- [ ] Add content bias to Recall Engine
- [ ] Add observability metrics (slow_mode_activations, etc.)
- [ ] Add user settings UI for affect-aware behaviors
- [ ] Unit tests: Mood label mapping, behavior mode triggers
- [ ] Integration tests: K0 Affect → K1 SessionState → Behavior adaptation
- [ ] User testing: Validate affect-driven behaviors improve UX
- [ ] Documentation: User guide for affect-aware behaviors

---

## References

- **Parent ADR**: ADR-0012 (Affect Module)
- **Related ADRs**:
  - k003a (Affect Contracts & Storage)
  - k003b (Tier-0 Realtime Classifier)
  - k003c (Tier-1 Enhanced Classifier)
  - k003d (Multi-Modal Fusion & EMA)
  - k003e (Policy Band Rules)
- **Module Locations**:
  - `k0/modules/affect/affect_service.py` (AffectSummary generation)
  - `k1/planner/affect_adapter.py` (Behavior adaptation)
  - `k1/concierge/quiet_mode.py` (Quiet mode logic)
  - `k1/recall/affect_bias.py` (Content bias)
- **Research**:
  - Circumplex Model: Russell, 1980
  - Affective Computing: Picard, 1997
  - Emotion-Aware AI: Brave & Nass, 2008

---

## Revision History

- 2025-11-13: Initial draft (@K0-Architecture, @K1-Architecture)
