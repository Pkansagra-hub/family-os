---
adr_number: '0012g'
parent_adr: '0012'
affected_layers:
  - K0 Memory Kernel
  - Cognitive Services
  - Policy & Safety Plane
affected_modules:
  - affect
  - modules/affect
  - workspace
authors:
  - '@K0-Architecture'
concerns:
  - architecture
  - family-dynamics
  - social-context
  - observability
date_created: '2025-11-13'
date_updated: '2025-11-13'
implementation_status: ACCEPTED
status: ACCEPTED
title: 'ADR-0012g: Household-Level Affect Dynamics'
---

# ADR-0012g: Household-Level Affect Dynamics

**Status**: Accepted  
**Parent ADR**: ADR-0012 (Affect Module)  
**Date**: 2025-11-13  
**Authors**: @K0-Architecture

---

## Context

ADR-0012d defines **per-person affect EMA** (valence/arousal smoothing), and ADR-0012e defines **policy bands**. This ADR specifies:

1. **Household-level aggregation**: How to compute collective affect state from individual EMAs
2. **Conflict detection**: Identify active household conflicts (multi-party high arousal + negative valence)
3. **Family moments**: Detect positive shared experiences (multi-party high valence)
4. **Emotional contagion**: Model how one person's affect influences others
5. **Household policy modifiers**: Adjust bands based on collective state

**Goals**:

- **Social awareness**: System understands household is a social unit, not just individuals
- **Conflict de-escalation**: Detect and respond to household conflicts early
- **Positive reinforcement**: Amplify and preserve family moments
- **Context-aware policy**: Policy bands consider household dynamics, not just individual affect
- **Privacy-preserving**: Aggregate household state without exposing individual details

**Key Use Cases**:

- **Conflict detection**: "Parent-teen argument" → Quiet mode for all agents, avoid triggering notifications
- **Family celebration**: "Birthday party with 4 positive members" → Green band boost, extended rollup
- **Emotional contagion**: "One member frustrated → others show rising arousal" → Preemptive downshift
- **Household stress**: "Multiple members with elevated arousal" → Suggest calming activities
- **Bedtime coordination**: "Kids aroused at night → parents notified" → Wind-down mode for household

---

## Decision

### 1. Household Affect State

**Data Structure**:

```python
@dataclass
class HouseholdAffectState:
    """
    Aggregated household-level affect state.
    
    Computed from individual AffectEMAState per person×space.
    """
    space_id: str
    household_id: str
    
    # Aggregated metrics (from active members in space)
    valence_avg: float          # Mean valence across active members
    arousal_avg: float          # Mean arousal across active members
    valence_min: float          # Most negative member
    valence_max: float          # Most positive member
    arousal_min: float          # Least aroused member
    arousal_max: float          # Most aroused member
    
    # Variance (spread of affect across members)
    valence_std: float          # Standard deviation of valence
    arousal_std: float          # Standard deviation of arousal
    
    # Conflict signals
    conflict_active: bool               # Multi-party negative + high arousal
    conflict_participants: list[str]    # person_ids involved in conflict
    conflict_severity: float            # [0, 1] intensity score
    conflict_duration: float            # Seconds since conflict started
    
    # Positive signals
    family_moment_active: bool          # Multi-party positive + moderate arousal
    family_moment_participants: list[str]
    celebration_active: bool            # Multi-party positive + high arousal
    
    # Emotional contagion signals
    contagion_source: Optional[str]     # person_id of affect source
    contagion_magnitude: float          # How much affect is spreading
    
    # Metadata
    n_active_members: int
    active_members: list[str]           # person_ids present in space
    last_updated: float
    
    # Historical trend
    valence_trend: str                  # "improving", "declining", "stable"
    arousal_trend: str                  # "rising", "falling", "stable"
```

**Computation** (from individual EMAs):

```python
def compute_household_state(
    person_states: list[AffectEMAState],
    space_id: str,
    household_id: str,
    time_window_seconds: float = 300  # 5 minutes
) -> HouseholdAffectState:
    """
    Aggregate individual affect states into household state.
    
    Only includes members active in the last `time_window_seconds`.
    """
    now = time.time()
    
    # Filter to active members (recent activity)
    active_states = [
        s for s in person_states
        if s.space_id == space_id and 
           (now - s.last_updated) < time_window_seconds
    ]
    
    if not active_states:
        return HouseholdAffectState(
            space_id=space_id,
            household_id=household_id,
            valence_avg=0.0,
            arousal_avg=0.3,
            n_active_members=0,
            active_members=[],
            last_updated=now
        )
    
    # Compute aggregates
    valences = [s.v_fast for s in active_states]
    arousals = [s.a_fast for s in active_states]
    
    state = HouseholdAffectState(
        space_id=space_id,
        household_id=household_id,
        valence_avg=np.mean(valences),
        arousal_avg=np.mean(arousals),
        valence_min=np.min(valences),
        valence_max=np.max(valences),
        arousal_min=np.min(arousals),
        arousal_max=np.max(arousals),
        valence_std=np.std(valences),
        arousal_std=np.std(arousals),
        n_active_members=len(active_states),
        active_members=[s.person_id for s in active_states],
        last_updated=now
    )
    
    # Detect patterns
    state.conflict_active = detect_conflict(active_states)
    state.conflict_participants = get_conflict_participants(active_states)
    state.conflict_severity = compute_conflict_severity(active_states)
    
    state.family_moment_active = detect_family_moment(active_states)
    state.family_moment_participants = get_family_moment_participants(active_states)
    state.celebration_active = detect_celebration(active_states)
    
    state.contagion_source, state.contagion_magnitude = detect_contagion(active_states)
    
    state.valence_trend, state.arousal_trend = compute_household_trends(active_states)
    
    return state
```

---

### 2. Conflict Detection

**Definition**: ≥2 members with **(valence < -0.3, arousal > 0.6)** within 5-minute window

**Algorithm**:

```python
def detect_conflict(person_states: list[AffectEMAState]) -> bool:
    """
    Detect active household conflict.
    
    Heuristic: ≥2 members with high arousal + negative valence.
    """
    high_arousal_negative = [
        s for s in person_states
        if s.v_fast < -0.3 and s.a_fast > 0.6
    ]
    
    return len(high_arousal_negative) >= 2


def get_conflict_participants(person_states: list[AffectEMAState]) -> list[str]:
    """
    Get person_ids of members involved in conflict.
    """
    return [
        s.person_id for s in person_states
        if s.v_fast < -0.3 and s.a_fast > 0.6
    ]


def compute_conflict_severity(person_states: list[AffectEMAState]) -> float:
    """
    Compute conflict intensity score [0, 1].
    
    Factors:
    - Number of participants (more = higher)
    - Arousal levels (higher = higher)
    - Valence negativity (lower = higher)
    - Arousal variance (high variance = escalating)
    """
    conflict_members = [
        s for s in person_states
        if s.v_fast < -0.3 and s.a_fast > 0.6
    ]
    
    if len(conflict_members) < 2:
        return 0.0
    
    # Number of participants (normalized by household size)
    n_participants = len(conflict_members)
    participant_score = min(n_participants / 4.0, 1.0)  # Cap at 4 people
    
    # Arousal intensity
    arousal_avg = np.mean([s.a_fast for s in conflict_members])
    arousal_score = (arousal_avg - 0.6) / 0.4  # Normalize [0.6, 1.0] → [0, 1]
    
    # Valence negativity
    valence_avg = np.mean([s.v_fast for s in conflict_members])
    valence_score = (-valence_avg - 0.3) / 0.7  # Normalize [-1.0, -0.3] → [0, 1]
    
    # Arousal variance (high variance = escalating)
    arousal_std = np.std([s.a_fast for s in conflict_members])
    variance_score = min(arousal_std / 0.2, 1.0)  # Cap at 0.2 std dev
    
    # Weighted combination
    severity = (
        0.3 * participant_score +
        0.3 * arousal_score +
        0.2 * valence_score +
        0.2 * variance_score
    )
    
    return np.clip(severity, 0.0, 1.0)
```

**Conflict Severity Levels**:

| Severity | Range | Description | Policy Impact |
|----------|-------|-------------|---------------|
| **None** | 0.0 | No conflict | Normal behavior |
| **Low** | 0.0-0.3 | Minor disagreement | Monitor, no action |
| **Moderate** | 0.3-0.6 | Active argument | Quiet mode, delay notifications |
| **High** | 0.6-0.8 | Escalated conflict | Quiet mode, suggest de-escalation |
| **Severe** | 0.8-1.0 | Crisis | Quiet mode, alert guardian (if minors) |

**Conflict Duration Tracking**:

```python
class HouseholdStateTracker:
    def __init__(self):
        self.conflict_start_time: Optional[float] = None
    
    def update_conflict_duration(self, state: HouseholdAffectState):
        """
        Track how long conflict has been active.
        """
        if state.conflict_active:
            if self.conflict_start_time is None:
                # Conflict just started
                self.conflict_start_time = time.time()
                logger.info(f"Household conflict started: severity={state.conflict_severity:.2f}")
            
            state.conflict_duration = time.time() - self.conflict_start_time
        
        else:
            if self.conflict_start_time is not None:
                # Conflict resolved
                duration = time.time() - self.conflict_start_time
                logger.info(f"Household conflict resolved after {duration:.1f}s")
                self.conflict_start_time = None
            
            state.conflict_duration = 0.0
```

---

### 3. Family Moments & Celebrations

**Family Moment**: ≥3 members with **(valence > 0.3)** within 10-minute window

**Celebration**: ≥3 members with **(valence > 0.5, arousal > 0.6)** within 10-minute window

**Algorithm**:

```python
def detect_family_moment(person_states: list[AffectEMAState]) -> bool:
    """
    Detect positive family moment.
    
    Heuristic: ≥3 members with positive valence.
    """
    positive_members = [
        s for s in person_states
        if s.v_fast > 0.3
    ]
    
    return len(positive_members) >= 3


def get_family_moment_participants(person_states: list[AffectEMAState]) -> list[str]:
    """
    Get person_ids of members in family moment.
    """
    return [
        s.person_id for s in person_states
        if s.v_fast > 0.3
    ]


def detect_celebration(person_states: list[AffectEMAState]) -> bool:
    """
    Detect celebration (high valence + high arousal).
    
    Heuristic: ≥3 members with excited/joyful state.
    """
    excited_members = [
        s for s in person_states
        if s.v_fast > 0.5 and s.a_fast > 0.6
    ]
    
    return len(excited_members) >= 3
```

**Policy Impact**:

- **Family Moment**: GREEN band boost (+0.1 valence), extended rollup (6 hours)
- **Celebration**: GREEN band guaranteed, tag as "celebratory", boost in recall (2x)

---

### 4. Emotional Contagion

**Definition**: One person's affect spreading to others in the household

**Detection**:

```python
def detect_contagion(person_states: list[AffectEMAState]) -> Tuple[Optional[str], float]:
    """
    Detect emotional contagion.
    
    Heuristic: One member with extreme affect + others showing similar trend.
    
    Returns:
        (contagion_source_person_id, magnitude)
    """
    if len(person_states) < 3:
        return None, 0.0
    
    # Find member with most extreme affect (potential source)
    extreme_valence_states = sorted(person_states, key=lambda s: abs(s.v_fast), reverse=True)
    extreme_arousal_states = sorted(person_states, key=lambda s: s.a_fast, reverse=True)
    
    # Check if most aroused member is influencing others
    potential_source = extreme_arousal_states[0]
    
    # Count how many others show rising arousal trend (fast > slow)
    rising_arousal_count = sum(
        1 for s in person_states
        if s.person_id != potential_source.person_id and
           (s.a_fast - s.a_slow) > 0.1  # Rising trend
    )
    
    if rising_arousal_count >= 2:
        # Contagion detected
        magnitude = min(rising_arousal_count / len(person_states), 1.0)
        return potential_source.person_id, magnitude
    
    return None, 0.0
```

**Example Scenario**:

```
Time T0:
- Mom: valence=-0.7, arousal=0.85 (frustrated)
- Dad: valence=0.2, arousal=0.4 (calm)
- Teen: valence=0.1, arousal=0.35 (calm)

Time T1 (5 minutes later):
- Mom: valence=-0.65, arousal=0.82 (still frustrated)
- Dad: valence=-0.1, arousal=0.55 (rising arousal, valence declining)
- Teen: valence=-0.05, arousal=0.48 (rising arousal)

→ Contagion detected: source=Mom, magnitude=0.67 (2/3 members affected)
```

**Policy Impact**:

- **Contagion magnitude > 0.5**: Downshift all members to AMBER band (preemptive)
- **Contagion source RED band**: Entire household enters quiet mode
- **Log contagion events** for P06 feedback (validate accuracy)

---

### 5. Household Trends

**Compute household valence/arousal trend** (improving/declining/stable):

```python
def compute_household_trends(person_states: list[AffectEMAState]) -> Tuple[str, str]:
    """
    Compute household-level trends from individual EMAs.
    
    Returns:
        (valence_trend, arousal_trend)
    """
    if not person_states:
        return "stable", "stable"
    
    # Compute household fast vs slow EMAs
    v_fast_avg = np.mean([s.v_fast for s in person_states])
    v_slow_avg = np.mean([s.v_slow for s in person_states])
    a_fast_avg = np.mean([s.a_fast for s in person_states])
    a_slow_avg = np.mean([s.a_slow for s in person_states])
    
    # Valence trend
    v_divergence = v_fast_avg - v_slow_avg
    if v_divergence > 0.15:
        valence_trend = "improving"
    elif v_divergence < -0.15:
        valence_trend = "declining"
    else:
        valence_trend = "stable"
    
    # Arousal trend
    a_divergence = a_fast_avg - a_slow_avg
    if a_divergence > 0.15:
        arousal_trend = "rising"
    elif a_divergence < -0.15:
        arousal_trend = "falling"
    else:
        arousal_trend = "stable"
    
    return valence_trend, arousal_trend
```

**Example**:

```python
# Household with 4 members
person_states = [
    AffectEMAState(v_fast=0.3, v_slow=0.1, a_fast=0.5, a_slow=0.4),  # Improving, rising
    AffectEMAState(v_fast=0.4, v_slow=0.2, a_fast=0.6, a_slow=0.5),  # Improving, rising
    AffectEMAState(v_fast=0.2, v_slow=0.1, a_fast=0.5, a_slow=0.45), # Improving, stable
    AffectEMAState(v_fast=0.5, v_slow=0.3, a_fast=0.7, a_slow=0.6),  # Improving, rising
]

valence_trend, arousal_trend = compute_household_trends(person_states)
# Returns: ("improving", "rising")
```

---

### 6. Household Policy Modifiers

**Policy Band Adjustments** based on household state:

| Household State | Individual Band | Modified Band | Reason |
|-----------------|-----------------|---------------|--------|
| Conflict active (severity > 0.6) | GREEN | AMBER | Conflict downshift |
| Conflict active (severity > 0.6) | AMBER | RED | Escalated conflict |
| Family moment active | AMBER | GREEN | Family moment boost |
| Celebration active | AMBER/GREEN | GREEN | Celebration boost |
| Contagion magnitude > 0.5 | GREEN | AMBER | Preemptive downshift |

**Implementation**:

```python
def apply_household_modifiers(
    individual_band: str,
    household_state: HouseholdAffectState,
    person_id: str
) -> Tuple[str, list[str]]:
    """
    Adjust individual policy band based on household state.
    
    Returns:
        (modified_band, modifier_reasons)
    """
    modified_band = individual_band
    reasons = []
    
    # Conflict downshift
    if household_state.conflict_active:
        if household_state.conflict_severity > 0.6:
            if individual_band == "GREEN":
                modified_band = "AMBER"
                reasons.append(f"Household conflict (severity {household_state.conflict_severity:.2f})")
            elif individual_band == "AMBER":
                modified_band = "RED"
                reasons.append(f"Escalated household conflict (severity {household_state.conflict_severity:.2f})")
    
    # Family moment boost
    if household_state.family_moment_active:
        if person_id in household_state.family_moment_participants:
            if individual_band == "AMBER":
                modified_band = "GREEN"
                reasons.append("Family moment detected - upgrading to GREEN")
    
    # Celebration boost
    if household_state.celebration_active:
        if person_id in household_state.family_moment_participants:
            if individual_band in ["AMBER", "GREEN"]:
                modified_band = "GREEN"
                reasons.append("Celebration detected - upgrading to GREEN")
    
    # Contagion preemptive downshift
    if household_state.contagion_magnitude > 0.5:
        if individual_band == "GREEN":
            modified_band = "AMBER"
            reasons.append(f"Emotional contagion detected (magnitude {household_state.contagion_magnitude:.2f})")
    
    return modified_band, reasons
```

---

### 7. Privacy-Preserving Aggregation

**Goal**: Compute household state without exposing individual details

**Approach**: Only share aggregates, not individual values

```python
@dataclass
class HouseholdAffectSummary:
    """
    Privacy-preserving household affect summary.
    
    Exposes aggregates but not individual person data.
    """
    space_id: str
    
    # Aggregates (OK to share)
    valence_avg: float
    arousal_avg: float
    conflict_active: bool
    family_moment_active: bool
    
    # NO individual person_ids or values exposed
    # (Use person_id hashes if needed for logging)
    
    n_active_members: int
    last_updated: float
```

**K1 Consumption** (from ADR-0012f):

```python
# K1 Planner reads household state (aggregates only)
household_summary = affect_service.get_household_summary(space_id="home")

if household_summary.conflict_active:
    logger.info("Household conflict detected - entering quiet mode")
    session.quiet_mode = True
```

---

### 8. Observability

**Prometheus Metrics**:

```python
# Conflict metrics
household_conflict_active = Gauge(
    "k0_household_conflict_active",
    "Whether household conflict is currently active",
    ["household_id"]
)

household_conflict_severity = Histogram(
    "k0_household_conflict_severity",
    "Household conflict severity score",
    ["household_id"]
)

household_conflict_duration = Histogram(
    "k0_household_conflict_duration_seconds",
    "Duration of household conflicts",
    ["household_id"]
)

# Family moment metrics
household_family_moments = Counter(
    "k0_household_family_moments_total",
    "Number of detected family moments",
    ["household_id"]
)

household_celebrations = Counter(
    "k0_household_celebrations_total",
    "Number of detected celebrations",
    ["household_id"]
)

# Contagion metrics
household_contagion_detections = Counter(
    "k0_household_contagion_detections_total",
    "Number of emotional contagion events detected",
    ["household_id"]
)

household_contagion_magnitude = Histogram(
    "k0_household_contagion_magnitude",
    "Magnitude of emotional contagion",
    ["household_id"]
)

# Aggregates
household_valence_avg = Gauge(
    "k0_household_valence_avg",
    "Average household valence",
    ["household_id"]
)

household_arousal_avg = Gauge(
    "k0_household_arousal_avg",
    "Average household arousal",
    ["household_id"]
)
```

**Dashboard Alerts**:

- **Conflict duration > 15 minutes**: Alert guardian
- **Conflict severity > 0.8**: Escalate to crisis protocol
- **Contagion magnitude > 0.7**: Log for review (validate detection accuracy)

---

### 9. Integration with Policy (P18)

**Household-Aware Policy Rules**:

```python
# In ADR-0012e (Policy Band Rules), add household modifiers:

def compute_band_with_household_context(
    affect_result: AffectAnnotation,
    household_state: HouseholdAffectState,
    person_id: str
) -> BandingResult:
    """
    Compute policy band with household context.
    """
    # Step 1: Compute individual band (ADR-0012e)
    individual_result = compute_band(affect_result)
    
    # Step 2: Apply household modifiers (ADR-0012g)
    modified_band, modifier_reasons = apply_household_modifiers(
        individual_result.band,
        household_state,
        person_id
    )
    
    # Step 3: Return modified result
    return BandingResult(
        band=modified_band,
        confidence=individual_result.confidence,
        reasons=individual_result.reasons + modifier_reasons,
        rule_ids=individual_result.rule_ids + ["HOUSEHOLD_MODIFIER"],
        downshift_from=individual_result.band if modified_band != individual_result.band else None
    )
```

---

## Consequences

### Positive

✅ **Social awareness**: System understands household as social unit  
✅ **Conflict detection**: Early detection enables de-escalation  
✅ **Family moments**: Positive experiences amplified and preserved  
✅ **Emotional contagion**: Preemptive downshift prevents household-wide escalation  
✅ **Privacy-preserving**: Aggregates shared, individual details protected  
✅ **Context-aware policy**: Bands consider household dynamics  

### Negative

❌ **Complexity**: Household state adds another layer of aggregation  
❌ **False positives**: May detect "conflict" in friendly debate  
❌ **Household size bias**: Thresholds (≥2, ≥3 members) may not work for small households  
❌ **Privacy concerns**: Even aggregates may reveal household patterns  

### Risks

- **Conflict detection errors**: False positives frustrate users, false negatives miss crises
- **Contagion misattribution**: Wrong source identified, ineffective intervention
- **Small household bias**: Single-parent households may never trigger "family moment"
- **Cultural variation**: Conflict norms differ across cultures (what's "normal" argument?)

**Mitigation**:

- **Tunable thresholds**: Allow per-household calibration of conflict/family moment thresholds
- **User feedback**: P06 feedback loop to correct false detections
- **Household size normalization**: Adjust thresholds based on household size (e.g., 2-member households need lower thresholds)
- **Cultural sensitivity**: Expose household affect patterns in dashboards, let users adjust
- **Rollback**: Feature flag to disable household-level features

---

## Implementation Checklist

- [ ] Implement `HouseholdAffectState` data structure
- [ ] Implement `compute_household_state()` aggregation
- [ ] Implement conflict detection (severity, duration tracking)
- [ ] Implement family moment detection
- [ ] Implement emotional contagion detection
- [ ] Implement household trend computation
- [ ] Implement household policy modifiers in P18
- [ ] Add privacy-preserving `HouseholdAffectSummary` for K1
- [ ] Unit tests: Conflict detection, family moments, contagion, modifiers
- [ ] Integration tests: Household state → policy band adjustment
- [ ] Performance tests: Aggregation <5ms for household of 6 members
- [ ] Observability: Metrics for conflicts, family moments, contagion
- [ ] Documentation: Household dynamics guide, threshold tuning

---

## References

- **Parent ADR**: ADR-0012 (Affect Module)
- **Related ADRs**:
  - k003a (Affect Contracts & Storage)
  - k003d (Multi-Modal Fusion & EMA)
  - k003e (Policy Band Rules & P18 Integration)
  - k003f (K1 Planner Bridge)
  - k003h (Social Cognition)
- **Module Locations**:
  - `k0/modules/affect/household_state.py`
  - `k0/modules/affect/conflict_detection.py`
  - `k0/policy/household_modifiers.py`
- **Research**:
  - Emotional Contagion: Hatfield et al., 1994
  - Family Systems Theory: Bowen, 1978
  - Household Affect Dynamics: Butler, 2011 (Emotion)

---

## Revision History

- 2025-11-13: Initial draft (@K0-Architecture)
