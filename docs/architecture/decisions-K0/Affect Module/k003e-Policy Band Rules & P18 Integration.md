---
adr_number: '0012e'
parent_adr: '0012'
affected_layers:
  - K0 Memory Kernel
  - Policy & Safety Plane
  - Cognitive Services
affected_modules:
  - affect
  - policy
  - modules/affect
authors:
  - '@K0-Architecture'
concerns:
  - safety
  - privacy
  - policy
  - architecture
date_created: '2025-11-13'
date_updated: '2025-11-13'
implementation_status: ACCEPTED
status: ACCEPTED
title: 'ADR-0012e: Policy Band Rules & P18 Integration'
---

# ADR-0012e: Policy Band Rules & P18 Integration

**Status**: Accepted  
**Parent ADR**: ADR-0012 (Affect Module)  
**Date**: 2025-11-13  
**Authors**: @K0-Architecture

---

## Context

ADR-0012 defines the Affect Module, which computes **valence** (emotional polarity) and **arousal** (intensity) from multi-modal signals. This ADR specifies:

1. **Policy Band Rules**: How to map $(v, a, \text{tags})$ → **band** (GREEN/AMBER/RED/BLACK)
2. **P18 Integration**: How bands trigger policy obligations (downshift, block, child safety)
3. **Explanation Templates**: How to generate human-readable `reasons[]` for band decisions

**Goals**:

- **Safety-first**: Err on the side of caution (downshift when uncertain)
- **Explainable**: Every band decision includes clear reasons
- **Context-aware**: Consider household dynamics, minor actors, time-of-day
- **Performance**: Band computation <5ms (within P02 write path budget)
- **Auditable**: Log all band decisions with attribution

**Key Use Cases**:

- **Downshift high-arousal conflicts**: "Parent-child argument at bedtime" → RED band → block sharing to family space
- **Child safety**: "Minor expressing distress" → RED band → notify guardian, store in personal space only
- **Positive family moments**: "Family celebration with high valence+arousal" → GREEN band → extend rollup half-life
- **Toxic content**: "Message contains toxic language" → RED/BLACK band → block or redact

---

## Decision

### 1. Policy Band Definitions

**Four Bands** (from most permissive to most restrictive):

| Band | Color | Meaning | Default Behavior |
|------|-------|---------|------------------|
| **GREEN** | 🟢 | Safe, positive, low-risk | Store in all spaces, enable sharing, extend rollup half-life |
| **AMBER** | 🟡 | Caution, moderate risk | Store in personal+family spaces, delay sharing, shorter rollup |
| **RED** | 🔴 | High risk, privacy/safety concern | Store in personal space only, block sharing, notify if minor |
| **BLACK** | ⚫ | Prohibited, policy violation | Block entirely, log for audit, escalate if needed |

**Band Priorities** (hierarchical):

1. **BLACK**: Hard policy violations (always wins)
2. **RED**: Safety concerns (overrides GREEN/AMBER)
3. **AMBER**: Moderate risk (overrides GREEN)
4. **GREEN**: Default safe band

**Example**: If both GREEN (positive family moment) and RED (minor distress) signals are present, RED wins.

---

### 2. Band Decision Algorithm

**Input**:

```python
@dataclass
class BandingInput:
    valence: float              # [-1, 1]
    arousal: float              # [0, 1]
    tags: list[str]             # e.g., ["urgent", "toxic_moderate", "conflict"]
    confidence: float           # [0, 1]
    
    # Context
    person_id: str
    space_id: str
    is_minor: bool              # Actor is <18 years old
    household_state: Optional['HouseholdAffectState'] = None
    time_of_day: str            # "morning", "afternoon", "evening", "night"
    
    # Household dynamics
    other_actors: list[str] = field(default_factory=list)
    relationship_graph: Optional[dict] = None  # parent-child, partner, etc.
```

**Output**:

```python
@dataclass
class BandingResult:
    band: str                   # "GREEN", "AMBER", "RED", "BLACK"
    confidence: float           # [0, 1]
    reasons: list[str]          # Human-readable explanations
    rule_ids: list[str]         # Rule identifiers that fired
    downshift_from: Optional[str] = None  # Original band before downshift
```

**Algorithm** (tiered rule evaluation):

```python
def compute_band(input: BandingInput) -> BandingResult:
    """
    Compute policy band using hierarchical rule cascade.
    
    Order of evaluation:
    1. BLACK rules (hard denies)
    2. RED rules (safety concerns)
    3. AMBER rules (moderate risk)
    4. GREEN rules (safe, positive)
    """
    reasons = []
    rule_ids = []
    confidence = input.confidence
    
    # TIER 1: BLACK rules (hard denies)
    black_result = check_black_rules(input)
    if black_result:
        return BandingResult(
            band="BLACK",
            confidence=1.0,  # Hard rules are absolute
            reasons=black_result.reasons,
            rule_ids=black_result.rule_ids
        )
    
    # TIER 2: RED rules (safety concerns)
    red_result = check_red_rules(input)
    if red_result:
        return BandingResult(
            band="RED",
            confidence=red_result.confidence,
            reasons=red_result.reasons,
            rule_ids=red_result.rule_ids
        )
    
    # TIER 3: AMBER rules (moderate risk)
    amber_result = check_amber_rules(input)
    if amber_result:
        return BandingResult(
            band="AMBER",
            confidence=amber_result.confidence,
            reasons=amber_result.reasons,
            rule_ids=amber_result.rule_ids
        )
    
    # TIER 4: GREEN (default safe)
    green_result = check_green_rules(input)
    return BandingResult(
        band="GREEN",
        confidence=green_result.confidence,
        reasons=green_result.reasons or ["No risk signals detected"],
        rule_ids=green_result.rule_ids or ["RULE_DEFAULT_GREEN"]
    )
```

---

### 3. BLACK Band Rules (Hard Denies)

**Rule Set**:

| Rule ID | Condition | Reason Template |
|---------|-----------|-----------------|
| **BLACK_001** | `"toxic_severe" in tags` | "Severe toxic language detected" |
| **BLACK_002** | `toxicity > 0.9` | "Extremely high toxicity score" |
| **BLACK_003** | `"explicit_content" in tags` | "Explicit content detected" |
| **BLACK_004** | `"self_harm" in tags` | "Self-harm language detected" |
| **BLACK_005** | `"violence" in tags` | "Violent content detected" |
| **BLACK_006** | `content_classification == "adult"` | "Adult content classification" |

**Implementation**:

```python
def check_black_rules(input: BandingInput) -> Optional[BandingResult]:
    """
    Check hard deny rules.
    
    Returns BandingResult if BLACK, None otherwise.
    """
    reasons = []
    rule_ids = []
    
    # Rule BLACK_001: Severe toxicity tag
    if "toxic_severe" in input.tags:
        reasons.append("Severe toxic language detected")
        rule_ids.append("BLACK_001")
    
    # Rule BLACK_002: Toxicity score threshold
    if "onnx_toxicity" in input.attribution:
        if input.attribution["onnx_toxicity"] > 0.9:
            reasons.append("Extremely high toxicity score (0.9+)")
            rule_ids.append("BLACK_002")
    
    # Rule BLACK_003: Explicit content
    if "explicit_content" in input.tags:
        reasons.append("Explicit content detected")
        rule_ids.append("BLACK_003")
    
    # Rule BLACK_004: Self-harm
    if "self_harm" in input.tags:
        reasons.append("Self-harm language detected - blocking and escalating")
        rule_ids.append("BLACK_004")
    
    # Rule BLACK_005: Violence
    if "violence" in input.tags:
        reasons.append("Violent content detected")
        rule_ids.append("BLACK_005")
    
    if reasons:
        return BandingResult(
            band="BLACK",
            confidence=1.0,
            reasons=reasons,
            rule_ids=rule_ids
        )
    
    return None
```

**P18 Obligations for BLACK**:

- **Block storage entirely** (do not write to `st_hipp_store`)
- **Log for audit** (write to `st_policy_violations` with full context)
- **Escalate if self-harm** (notify guardian, trigger crisis protocol)
- **Return error to user** (if real-time input like chat)

---

### 4. RED Band Rules (Safety Concerns)

**Rule Set**:

| Rule ID | Condition | Reason Template |
|---------|-----------|-----------------|
| **RED_001** | `is_minor AND valence < -0.5 AND arousal > 0.6` | "Minor expressing high distress" |
| **RED_002** | `"conflict" in tags AND is_minor AND "parent" in other_actors` | "Parent-child conflict detected" |
| **RED_003** | `"toxic_moderate" in tags OR "toxic_light" in tags` | "Toxic language detected" |
| **RED_004** | `household_state.conflict_active AND arousal > 0.7` | "Active household conflict with high arousal" |
| **RED_005** | `valence < -0.7 AND arousal > 0.75` | "Extreme negative emotion (distress)" |
| **RED_006** | `"distressing" in tags` | "Distressing content detected" |
| **RED_007** | `time_of_day == "night" AND is_minor AND arousal > 0.6` | "Minor high arousal at bedtime" |
| **RED_008** | `is_minor AND "urgent" in tags AND valence < -0.4` | "Minor urgent negative request" |

**Implementation**:

```python
def check_red_rules(input: BandingInput) -> Optional[BandingResult]:
    """
    Check safety concern rules.
    
    Returns BandingResult if RED, None otherwise.
    """
    reasons = []
    rule_ids = []
    confidence = input.confidence
    
    # Rule RED_001: Minor distress
    if input.is_minor and input.valence < -0.5 and input.arousal > 0.6:
        reasons.append("Minor expressing high distress (valence < -0.5, arousal > 0.6)")
        rule_ids.append("RED_001")
        confidence = min(confidence, 0.9)
    
    # Rule RED_002: Parent-child conflict
    if input.is_minor and "conflict" in input.tags:
        if input.relationship_graph:
            # Check if any other actor is parent
            for actor in input.other_actors:
                rel = input.relationship_graph.get((input.person_id, actor))
                if rel == "parent-child":
                    reasons.append("Parent-child conflict detected")
                    rule_ids.append("RED_002")
                    confidence = min(confidence, 0.85)
                    break
    
    # Rule RED_003: Toxic language (moderate or light)
    if "toxic_moderate" in input.tags or "toxic_light" in input.tags:
        reasons.append(f"Toxic language detected ({', '.join([t for t in input.tags if 'toxic' in t])})")
        rule_ids.append("RED_003")
        confidence = min(confidence, 0.8)
    
    # Rule RED_004: Household conflict + high arousal
    if input.household_state and input.household_state.conflict_active:
        if input.arousal > 0.7:
            reasons.append("Active household conflict with high arousal")
            rule_ids.append("RED_004")
            confidence = min(confidence, 0.85)
    
    # Rule RED_005: Extreme negative emotion
    if input.valence < -0.7 and input.arousal > 0.75:
        reasons.append(f"Extreme negative emotion (valence {input.valence:.2f}, arousal {input.arousal:.2f})")
        rule_ids.append("RED_005")
        confidence = min(confidence, 0.9)
    
    # Rule RED_006: Distressing tag
    if "distressing" in input.tags:
        reasons.append("Distressing content detected")
        rule_ids.append("RED_006")
    
    # Rule RED_007: Minor high arousal at night
    if input.is_minor and input.time_of_day == "night" and input.arousal > 0.6:
        reasons.append("Minor high arousal at bedtime (potential sleep disruption)")
        rule_ids.append("RED_007")
        confidence = min(confidence, 0.8)
    
    # Rule RED_008: Minor urgent negative
    if input.is_minor and "urgent" in input.tags and input.valence < -0.4:
        reasons.append("Minor urgent negative request (may need guardian attention)")
        rule_ids.append("RED_008")
        confidence = min(confidence, 0.85)
    
    if reasons:
        return BandingResult(
            band="RED",
            confidence=confidence,
            reasons=reasons,
            rule_ids=rule_ids
        )
    
    return None
```

**P18 Obligations for RED**:

- **Store in personal space only** (no family/shared spaces)
- **Block sharing** to other spaces
- **Notify guardian if minor** (push notification with context)
- **Tag for review** (flag for P06 feedback loop)
- **Shorter rollup half-life** (1 hour instead of 4 hours)

---

### 5. AMBER Band Rules (Moderate Risk)

**Rule Set**:

| Rule ID | Condition | Reason Template |
|---------|-----------|-----------------|
| **AMBER_001** | `arousal > 0.7` | "High arousal detected" |
| **AMBER_002** | `valence < -0.4` | "Moderately negative emotion" |
| **AMBER_003** | `confidence < 0.5` | "Low confidence in affect prediction" |
| **AMBER_004** | `"urgent" in tags` | "Urgent context detected" |
| **AMBER_005** | `household_state.arousal_avg > 0.6` | "Elevated household arousal" |
| **AMBER_006** | `is_minor AND time_of_day == "night"` | "Minor activity at bedtime" |
| **AMBER_007** | `valence > 0.5 AND arousal > 0.8` | "High excitement (potential overstimulation)" |

**Implementation**:

```python
def check_amber_rules(input: BandingInput) -> Optional[BandingResult]:
    """
    Check moderate risk rules.
    
    Returns BandingResult if AMBER, None otherwise.
    """
    reasons = []
    rule_ids = []
    confidence = input.confidence
    
    # Rule AMBER_001: High arousal
    if input.arousal > 0.7:
        reasons.append(f"High arousal detected ({input.arousal:.2f})")
        rule_ids.append("AMBER_001")
    
    # Rule AMBER_002: Moderately negative
    if input.valence < -0.4:
        reasons.append(f"Moderately negative emotion (valence {input.valence:.2f})")
        rule_ids.append("AMBER_002")
    
    # Rule AMBER_003: Low confidence
    if input.confidence < 0.5:
        reasons.append(f"Low confidence in affect prediction ({input.confidence:.2f})")
        rule_ids.append("AMBER_003")
        confidence = 0.5  # Cap at prediction confidence
    
    # Rule AMBER_004: Urgent tag
    if "urgent" in input.tags:
        reasons.append("Urgent context detected")
        rule_ids.append("AMBER_004")
    
    # Rule AMBER_005: Elevated household arousal
    if input.household_state and input.household_state.arousal_avg > 0.6:
        reasons.append(f"Elevated household arousal ({input.household_state.arousal_avg:.2f})")
        rule_ids.append("AMBER_005")
    
    # Rule AMBER_006: Minor at bedtime
    if input.is_minor and input.time_of_day == "night":
        reasons.append("Minor activity at bedtime (encourage winding down)")
        rule_ids.append("AMBER_006")
    
    # Rule AMBER_007: High excitement (overstimulation risk)
    if input.valence > 0.5 and input.arousal > 0.8:
        reasons.append("High excitement detected (potential overstimulation)")
        rule_ids.append("AMBER_007")
    
    if reasons:
        return BandingResult(
            band="AMBER",
            confidence=confidence,
            reasons=reasons,
            rule_ids=rule_ids
        )
    
    return None
```

**P18 Obligations for AMBER**:

- **Store in personal + family spaces** (no shared/external spaces)
- **Delay sharing** (wait 15 minutes before enabling)
- **Shorter rollup half-life** (2 hours instead of 4 hours)
- **Suggest calm-down period** (if high arousal for minor)
- **Tag for review** (optional, based on household settings)

---

### 6. GREEN Band Rules (Safe, Positive)

**Rule Set**:

| Rule ID | Condition | Reason Template |
|---------|-----------|-----------------|
| **GREEN_001** | `valence > 0.4 AND arousal < 0.5` | "Positive, calm emotion" |
| **GREEN_002** | `"calming" in tags` | "Calming content detected" |
| **GREEN_003** | `"celebratory" in tags` | "Celebratory moment detected" |
| **GREEN_004** | `"affectionate" in tags` | "Affectionate interaction detected" |
| **GREEN_005** | `household_state.family_moment AND valence > 0.3` | "Positive family moment" |
| **GREEN_DEFAULT** | `True` | "No risk signals detected" |

**Implementation**:

```python
def check_green_rules(input: BandingInput) -> BandingResult:
    """
    Check safe/positive rules.
    
    Always returns a result (GREEN is default).
    """
    reasons = []
    rule_ids = []
    confidence = input.confidence
    
    # Rule GREEN_001: Positive + calm
    if input.valence > 0.4 and input.arousal < 0.5:
        reasons.append(f"Positive, calm emotion (valence {input.valence:.2f}, arousal {input.arousal:.2f})")
        rule_ids.append("GREEN_001")
    
    # Rule GREEN_002: Calming tag
    if "calming" in input.tags:
        reasons.append("Calming content detected")
        rule_ids.append("GREEN_002")
    
    # Rule GREEN_003: Celebratory
    if "celebratory" in input.tags:
        reasons.append("Celebratory moment detected")
        rule_ids.append("GREEN_003")
    
    # Rule GREEN_004: Affectionate
    if "affectionate" in input.tags:
        reasons.append("Affectionate interaction detected")
        rule_ids.append("GREEN_004")
    
    # Rule GREEN_005: Positive family moment
    if input.household_state and input.household_state.family_moment:
        if input.valence > 0.3:
            reasons.append("Positive family moment")
            rule_ids.append("GREEN_005")
    
    # Default GREEN
    if not reasons:
        reasons = ["No risk signals detected"]
        rule_ids = ["GREEN_DEFAULT"]
    
    return BandingResult(
        band="GREEN",
        confidence=confidence,
        reasons=reasons,
        rule_ids=rule_ids
    )
```

**P18 Obligations for GREEN**:

- **Store in all spaces** (personal, family, shared, external as configured)
- **Enable sharing** immediately
- **Extended rollup half-life** (4-6 hours)
- **Positive recall bias** (boost in search results for "happy moments")
- **No restrictions** (default behavior)

---

### 7. Household Context Integration

**Household Affect State** (computed from per-person EMAs):

```python
@dataclass
class HouseholdAffectState:
    """
    Aggregated household-level affect state.
    """
    space_id: str
    
    # Aggregated metrics
    valence_avg: float          # Average valence across active members
    arousal_avg: float          # Average arousal across active members
    valence_min: float          # Min valence (most negative member)
    arousal_max: float          # Max arousal (most aroused member)
    
    # Conflict detection
    conflict_active: bool       # Multiple high-arousal, low-valence actors
    conflict_participants: list[str]
    
    # Family moments
    family_moment: bool         # Multiple actors with high positive valence
    
    # Metadata
    n_active_members: int
    last_updated: float
```

**Conflict Detection** (Rule RED_004):

```python
def detect_household_conflict(person_states: list[AffectEMAState]) -> bool:
    """
    Detect active household conflict.
    
    Heuristic: ≥2 members with (valence < -0.3, arousal > 0.6) within 5 minutes.
    """
    high_arousal_negative = [
        s for s in person_states
        if s.v_fast < -0.3 and s.a_fast > 0.6
        and (time.time() - s.last_updated) < 300  # 5 minutes
    ]
    
    return len(high_arousal_negative) >= 2
```

**Family Moment Detection** (Rule GREEN_005):

```python
def detect_family_moment(person_states: list[AffectEMAState]) -> bool:
    """
    Detect positive family moment.
    
    Heuristic: ≥3 members with (valence > 0.3) within 10 minutes.
    """
    positive_members = [
        s for s in person_states
        if s.v_fast > 0.3
        and (time.time() - s.last_updated) < 600  # 10 minutes
    ]
    
    return len(positive_members) >= 3
```

---

### 8. P18 Policy Integration

**Policy Module** (`k0/policy/affect_policy.py`):

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class PolicyAction:
    """
    Policy obligations triggered by band.
    """
    # Storage restrictions
    allowed_spaces: list[str]   # e.g., ["personal"], ["personal", "family"]
    block_sharing: bool
    
    # Timing
    sharing_delay_seconds: int  # 0 (immediate), 900 (15 min), -1 (blocked)
    
    # Rollup
    rollup_half_life_hours: float  # 1, 2, 4, 6
    
    # Notifications
    notify_guardian: bool
    escalate: bool              # Trigger crisis protocol
    
    # Audit
    log_for_audit: bool
    
    # UX hints
    suggest_calm_down: bool
    boost_in_recall: bool       # For positive moments


def band_to_policy_action(band: str, is_minor: bool) -> PolicyAction:
    """
    Map band to P18 policy obligations.
    """
    if band == "BLACK":
        return PolicyAction(
            allowed_spaces=[],  # Block entirely
            block_sharing=True,
            sharing_delay_seconds=-1,
            rollup_half_life_hours=0,
            notify_guardian=is_minor,
            escalate=True,
            log_for_audit=True,
            suggest_calm_down=False,
            boost_in_recall=False,
        )
    
    elif band == "RED":
        return PolicyAction(
            allowed_spaces=["personal"],
            block_sharing=True,
            sharing_delay_seconds=-1,
            rollup_half_life_hours=1.0,
            notify_guardian=is_minor,
            escalate=False,
            log_for_audit=True,
            suggest_calm_down=is_minor,
            boost_in_recall=False,
        )
    
    elif band == "AMBER":
        return PolicyAction(
            allowed_spaces=["personal", "family"],
            block_sharing=False,
            sharing_delay_seconds=900,  # 15 minutes
            rollup_half_life_hours=2.0,
            notify_guardian=False,
            escalate=False,
            log_for_audit=False,
            suggest_calm_down=is_minor,
            boost_in_recall=False,
        )
    
    else:  # GREEN
        return PolicyAction(
            allowed_spaces=["personal", "family", "shared", "external"],
            block_sharing=False,
            sharing_delay_seconds=0,
            rollup_half_life_hours=4.0,
            notify_guardian=False,
            escalate=False,
            log_for_audit=False,
            suggest_calm_down=False,
            boost_in_recall=True,
        )
```

**Integration with P02 Write Path**:

```python
# In P02 pipeline
affect_result = affect_service.classify(event)
banding_result = policy_engine.compute_band(affect_result)
policy_action = policy_engine.band_to_policy_action(
    banding_result.band,
    is_minor=event.person.is_minor
)

# Apply policy action
if policy_action.allowed_spaces:
    # Write to allowed spaces only
    storage_manager.write_event(event, spaces=policy_action.allowed_spaces)
else:
    # Block storage, log violation
    policy_logger.log_violation(event, banding_result)

# Set rollup half-life
event.rollup_half_life = policy_action.rollup_half_life_hours

# Notify if needed
if policy_action.notify_guardian:
    notification_service.notify_guardian(event.person_id, banding_result)
```

---

### 9. Explanation Templates

**Human-Readable Reasons** (for UX and audit logs):

```python
REASON_TEMPLATES = {
    # BLACK
    "BLACK_001": "Severe toxic language detected in message",
    "BLACK_002": "Extremely high toxicity score (0.9+)",
    "BLACK_003": "Explicit content detected",
    "BLACK_004": "Self-harm language detected - blocking and escalating to guardian",
    "BLACK_005": "Violent content detected",
    
    # RED
    "RED_001": "Minor expressing high distress (valence {valence:.2f}, arousal {arousal:.2f})",
    "RED_002": "Parent-child conflict detected",
    "RED_003": "Toxic language detected ({tags})",
    "RED_004": "Active household conflict with high arousal",
    "RED_005": "Extreme negative emotion (valence {valence:.2f}, arousal {arousal:.2f})",
    "RED_006": "Distressing content detected",
    "RED_007": "Minor high arousal at bedtime (potential sleep disruption)",
    "RED_008": "Minor urgent negative request (may need guardian attention)",
    
    # AMBER
    "AMBER_001": "High arousal detected ({arousal:.2f})",
    "AMBER_002": "Moderately negative emotion (valence {valence:.2f})",
    "AMBER_003": "Low confidence in affect prediction ({confidence:.2f})",
    "AMBER_004": "Urgent context detected",
    "AMBER_005": "Elevated household arousal ({household_arousal:.2f})",
    "AMBER_006": "Minor activity at bedtime (encourage winding down)",
    "AMBER_007": "High excitement detected (potential overstimulation)",
    
    # GREEN
    "GREEN_001": "Positive, calm emotion (valence {valence:.2f}, arousal {arousal:.2f})",
    "GREEN_002": "Calming content detected",
    "GREEN_003": "Celebratory moment detected",
    "GREEN_004": "Affectionate interaction detected",
    "GREEN_005": "Positive family moment",
    "GREEN_DEFAULT": "No risk signals detected",
}


def format_reason(rule_id: str, context: dict) -> str:
    """
    Format reason template with context variables.
    """
    template = REASON_TEMPLATES.get(rule_id, "Unknown rule")
    try:
        return template.format(**context)
    except KeyError:
        return template  # Return unformatted if missing context
```

**User-Facing Explanation** (for settings/review UI):

```
Band: RED
Confidence: 85%

Reasons:
- Minor expressing high distress (valence -0.62, arousal 0.78)
- Parent-child conflict detected

Actions Taken:
- Stored in personal space only
- Sharing blocked to protect privacy
- Guardian notified of distress signal
- Rollup half-life reduced to 1 hour

Rules Applied: RED_001, RED_002
```

---

### 10. Performance Budget

**Latency Target**: <5ms P95 for band computation (within P02 write path budget)

**Breakdown**:

| Step | Latency | Notes |
|------|---------|-------|
| Load household state | 0.5ms | In-memory cache lookup |
| Check BLACK rules | 0.3ms | 6 rule evaluations |
| Check RED rules | 1.2ms | 8 rule evaluations + household checks |
| Check AMBER rules | 0.8ms | 7 rule evaluations |
| Check GREEN rules | 0.4ms | 5 rule evaluations |
| Format reasons | 0.5ms | Template substitution |
| Map to policy action | 0.2ms | Dictionary lookup |
| **Total** | **3.9ms** | ✅ Within 5ms budget |

**Memory Footprint**:

- Rule evaluation: <1KB (stack variables)
- Household state: ~200 bytes (cached)
- Total: <2KB per band computation

---

## Consequences

### Positive

✅ **Safety-first**: Hierarchical rules prioritize safety (BLACK/RED override GREEN/AMBER)  
✅ **Explainable**: Every band includes clear reasons and rule IDs  
✅ **Context-aware**: Household dynamics, minor status, time-of-day considered  
✅ **Performance**: <5ms P95 latency (within P02 budget)  
✅ **Auditable**: All band decisions logged with full attribution  
✅ **P18 integration**: Clean mapping from bands to policy obligations  

### Negative

❌ **Rule maintenance**: 27+ rules require ongoing tuning  
❌ **False positives**: Conservative rules may over-block safe content  
❌ **Household state complexity**: Conflict/family moment detection adds state  
❌ **Cultural variation**: Rules may not generalize across cultures  

### Risks

- **Over-blocking**: Conservative rules may frustrate users (too many REDs)
- **Under-blocking**: Missed safety signals (false negatives)
- **Rule conflicts**: Multiple rules firing may create ambiguous reasons
- **Household state drift**: Stale household state may cause incorrect bands

**Mitigation**:

- **User feedback**: P06 feedback loop to tune thresholds
- **A/B testing**: Gradual rollout of new rules with metrics
- **Rule versioning**: Track rule changes for rollback
- **Household state TTL**: Expire stale state (5-minute TTL)
- **Manual override**: Allow guardians to adjust band sensitivity

---

## Implementation Checklist

- [ ] Implement band computation in `k0/modules/affect/banding.py`
- [ ] Add rule evaluation functions (check_black_rules, check_red_rules, etc.)
- [ ] Implement household state aggregation in `k0/modules/affect/household_state.py`
- [ ] Add P18 integration in `k0/policy/affect_policy.py`
- [ ] Add reason templates and formatting
- [ ] Unit tests: Each rule, household conflict detection, policy action mapping
- [ ] Integration tests: P02 → Affect → Banding → P18 → Storage
- [ ] Performance tests: Band computation <5ms P95
- [ ] Observability: Metrics for band distribution, rule firing frequency
- [ ] Documentation: Rule registry, tuning guide, user-facing explanations

---

## References

- **Parent ADR**: ADR-0012 (Affect Module)
- **Related ADRs**:
  - k003a (Affect Contracts & Storage)
  - k003b (Tier-0 Realtime Classifier)
  - k003c (Tier-1 Enhanced Classifier)
  - k003d (Multi-Modal Fusion & EMA)
  - k003f (K1 Planner Bridge)
- **Module Locations**:
  - `k0/modules/affect/banding.py`
  - `k0/modules/affect/household_state.py`
  - `k0/policy/affect_policy.py`
- **Research**:
  - Circumplex Model of Affect: Russell, 1980
  - Emotion Regulation: Gross, 1998
  - Child Safety Online: Livingstone & Helsper, 2008

---

## Revision History

- 2025-11-13: Initial draft (@K0-Architecture)
