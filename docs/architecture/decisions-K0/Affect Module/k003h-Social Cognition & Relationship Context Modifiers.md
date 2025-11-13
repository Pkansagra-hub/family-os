---
adr_number: '0012h'
parent_adr: '0012'
affected_layers:
  - K0 Memory Kernel
  - Cognitive Services
  - Policy & Safety Plane
affected_modules:
  - affect
  - modules/affect
  - policy
authors:
  - '@K0-Architecture'
concerns:
  - architecture
  - social-context
  - relationships
  - safety
  - privacy
date_created: '2025-11-13'
date_updated: '2025-11-13'
implementation_status: ACCEPTED
status: ACCEPTED
title: 'ADR-0012h: Social Cognition & Relationship Context Modifiers'
---

# ADR-0012h: Social Cognition & Relationship Context Modifiers

**Status**: Accepted  
**Parent ADR**: ADR-0012 (Affect Module)  
**Date**: 2025-11-13  
**Authors**: @K0-Architecture

---

## Context

ADR-0012e defines **policy band rules**, and ADR-0012g defines **household affect dynamics**. This ADR specifies:

1. **Relationship graph integration**: How to use relationship types (parent-child, partner, sibling, friend) to modify affect interpretation
2. **Social context modifiers**: Adjust valence/arousal based on who is present (e.g., parent-child interaction vs sibling interaction)
3. **Developmental stage awareness**: Age-appropriate affect thresholds (minor vs adult)
4. **Lifecycle context**: Time-of-day, day-of-week, special events (bedtime, school hours, holidays)
5. **Safety rules for vulnerable actors**: Enhanced protection for minors, elderly, vulnerable adults

**Goals**:

- **Relationship-aware policy**: Same affect signal interpreted differently based on relationships
- **Developmental appropriateness**: Age-appropriate thresholds for minors vs adults
- **Context-aware interpretation**: Time-of-day and lifecycle events modify affect interpretation
- **Enhanced child safety**: Parent-child conflicts escalated more aggressively than adult-adult conflicts
- **Privacy-preserving**: Relationship graph stored securely, minimal exposure

**Key Use Cases**:

- **Parent-child conflict**: valence=-0.4 + minor + parent present → RED (vs AMBER for adult-adult)
- **Sibling argument**: valence=-0.5 + teens + no adults → AMBER (monitor, don't escalate)
- **Bedtime arousal**: arousal=0.6 + minor + time=night → RED (vs GREEN during day)
- **School hours**: arousal=0.8 + minor + time=school → RED (potential truancy/distress)
- **Partner affection**: valence=0.7 + arousal=0.5 + partner present → GREEN + "affectionate" tag

---

## Decision

### 1. Relationship Graph

**Data Structure**:

```python
@dataclass
class Relationship:
    """
    Relationship between two people in household.
    """
    person_a: str               # person_id
    person_b: str               # person_id
    relationship_type: str      # "parent-child", "partner", "sibling", "friend", "caregiver-dependent"
    
    # Directional metadata (if applicable)
    direction: Optional[str] = None  # e.g., "parent-child": A is parent, B is child
    
    # Relationship strength
    strength: float = 1.0       # [0, 1] - how close the relationship is
    
    # Metadata
    created_at: float = 0.0
    last_interaction: float = 0.0


@dataclass
class RelationshipGraph:
    """
    Complete relationship graph for household.
    """
    household_id: str
    relationships: dict[Tuple[str, str], Relationship]  # (person_a, person_b) → Relationship
    
    # Lookup helpers
    def get_relationship(self, person_a: str, person_b: str) -> Optional[Relationship]:
        """Get relationship between two people (bidirectional)."""
        key = tuple(sorted([person_a, person_b]))
        return self.relationships.get(key)
    
    def get_related_people(self, person_id: str, rel_type: Optional[str] = None) -> list[str]:
        """Get all people related to person_id, optionally filtered by type."""
        related = []
        for (a, b), rel in self.relationships.items():
            if a == person_id:
                if rel_type is None or rel.relationship_type == rel_type:
                    related.append(b)
            elif b == person_id:
                if rel_type is None or rel.relationship_type == rel_type:
                    related.append(a)
        return related
    
    def is_parent_child(self, person_a: str, person_b: str) -> bool:
        """Check if relationship is parent-child."""
        rel = self.get_relationship(person_a, person_b)
        return rel is not None and rel.relationship_type == "parent-child"
    
    def is_minor_with_parent(self, minor_id: str, other_id: str) -> bool:
        """Check if minor is interacting with their parent."""
        rel = self.get_relationship(minor_id, other_id)
        if rel and rel.relationship_type == "parent-child":
            # Check direction: other_id must be parent
            if rel.direction == "parent-child":
                return (rel.person_a == other_id) or (rel.person_b == other_id)
        return False
```

**Relationship Types**:

| Type | Description | Example |
|------|-------------|---------|
| **parent-child** | Parental relationship | Mom & child (directional) |
| **partner** | Romantic partnership | Husband & wife |
| **sibling** | Siblings | Brother & sister |
| **friend** | Friendship | Close friends in household |
| **caregiver-dependent** | Care relationship | Caregiver & elderly parent |
| **extended-family** | Extended relatives | Aunt & niece |

---

### 2. Social Context Modifiers

**Modify affect interpretation based on who is present**:

```python
def apply_social_context_modifiers(
    base_valence: float,
    base_arousal: float,
    person_id: str,
    other_actors: list[str],
    relationship_graph: RelationshipGraph,
    person_metadata: dict
) -> Tuple[float, float, list[str]]:
    """
    Apply social context modifiers to affect scores.
    
    Returns:
        (modified_valence, modified_arousal, modifier_tags)
    """
    valence = base_valence
    arousal = base_arousal
    modifier_tags = []
    
    is_minor = person_metadata.get("is_minor", False)
    age = person_metadata.get("age", 0)
    
    # MODIFIER 1: Parent-child interaction (if minor)
    if is_minor and other_actors:
        parents_present = [
            actor for actor in other_actors
            if relationship_graph.is_minor_with_parent(person_id, actor)
        ]
        
        if parents_present:
            # Parent-child conflict: Amplify negative valence
            if valence < -0.2:
                valence *= 1.3  # Amplify by 30%
                arousal = min(arousal + 0.1, 1.0)  # Boost arousal
                modifier_tags.append("parent_child_conflict")
            
            # Parent-child affection: Amplify positive valence
            elif valence > 0.4:
                valence = min(valence * 1.2, 1.0)  # Amplify by 20%
                modifier_tags.append("parent_child_affection")
    
    # MODIFIER 2: Sibling interaction
    if other_actors:
        siblings_present = [
            actor for actor in other_actors
            if relationship_graph.get_relationship(person_id, actor) and
               relationship_graph.get_relationship(person_id, actor).relationship_type == "sibling"
        ]
        
        if siblings_present:
            # Sibling conflict: Moderate amplification (less than parent-child)
            if valence < -0.3:
                valence *= 1.15  # Amplify by 15%
                modifier_tags.append("sibling_conflict")
            
            # Sibling play: Slightly amplify positive
            elif valence > 0.4 and arousal > 0.5:
                valence = min(valence * 1.1, 1.0)
                modifier_tags.append("sibling_play")
    
    # MODIFIER 3: Partner interaction
    if not is_minor and other_actors:
        partners_present = [
            actor for actor in other_actors
            if relationship_graph.get_relationship(person_id, actor) and
               relationship_graph.get_relationship(person_id, actor).relationship_type == "partner"
        ]
        
        if partners_present:
            # Partner conflict: Amplify negative valence
            if valence < -0.3:
                valence *= 1.25  # Amplify by 25%
                arousal = min(arousal + 0.15, 1.0)
                modifier_tags.append("partner_conflict")
            
            # Partner affection: Amplify positive
            elif valence > 0.5:
                valence = min(valence * 1.2, 1.0)
                modifier_tags.append("partner_affection")
    
    # MODIFIER 4: Alone vs social
    if not other_actors:
        # Alone: Reduce arousal slightly (less stimulation)
        arousal *= 0.9
        modifier_tags.append("alone")
    else:
        # Social: Slight arousal boost
        arousal = min(arousal * 1.05, 1.0)
        modifier_tags.append("social")
    
    # Clamp to valid ranges
    valence = np.clip(valence, -1.0, 1.0)
    arousal = np.clip(arousal, 0.0, 1.0)
    
    return valence, arousal, modifier_tags
```

---

### 3. Developmental Stage Awareness

**Age-appropriate thresholds** for minors:

```python
@dataclass
class DevelopmentalStage:
    """Age-based developmental stage with affect thresholds."""
    
    name: str
    age_range: Tuple[int, int]      # (min_age, max_age) in years
    
    # Affect thresholds
    distress_valence_threshold: float    # When to flag distress
    high_arousal_threshold: float        # When arousal is "high" for this age
    
    # Policy modifiers
    guardian_notify_threshold: float     # Valence threshold for guardian notification
    bedtime_arousal_threshold: float     # Arousal threshold for bedtime concerns
    
    # Baseline priors (typical affect for this age)
    baseline_valence: float
    baseline_arousal: float


# Age-based stages
DEVELOPMENTAL_STAGES = [
    DevelopmentalStage(
        name="toddler",
        age_range=(0, 5),
        distress_valence_threshold=-0.4,       # Lower threshold (more sensitive)
        high_arousal_threshold=0.5,
        guardian_notify_threshold=-0.3,
        bedtime_arousal_threshold=0.4,         # Lower threshold for bedtime
        baseline_valence=0.2,
        baseline_arousal=0.5                   # Toddlers often aroused
    ),
    DevelopmentalStage(
        name="child",
        age_range=(6, 12),
        distress_valence_threshold=-0.5,
        high_arousal_threshold=0.6,
        guardian_notify_threshold=-0.4,
        bedtime_arousal_threshold=0.5,
        baseline_valence=0.1,
        baseline_arousal=0.45
    ),
    DevelopmentalStage(
        name="teen",
        age_range=(13, 17),
        distress_valence_threshold=-0.6,
        high_arousal_threshold=0.7,
        guardian_notify_threshold=-0.5,
        bedtime_arousal_threshold=0.6,
        baseline_valence=0.0,                  # Teens more neutral baseline
        baseline_arousal=0.5
    ),
    DevelopmentalStage(
        name="adult",
        age_range=(18, 150),
        distress_valence_threshold=-0.7,
        high_arousal_threshold=0.75,
        guardian_notify_threshold=-1.0,        # No guardian notification for adults
        bedtime_arousal_threshold=0.7,
        baseline_valence=0.0,
        baseline_arousal=0.4
    ),
]


def get_developmental_stage(age: int) -> DevelopmentalStage:
    """Get developmental stage for given age."""
    for stage in DEVELOPMENTAL_STAGES:
        if stage.age_range[0] <= age <= stage.age_range[1]:
            return stage
    return DEVELOPMENTAL_STAGES[-1]  # Default to adult
```

**Usage in Policy Rules**:

```python
def check_red_rules_with_developmental_context(
    input: BandingInput,
    relationship_graph: RelationshipGraph
) -> Optional[BandingResult]:
    """
    Check RED rules with developmental stage awareness.
    """
    reasons = []
    rule_ids = []
    
    if not input.is_minor:
        # Use standard RED rules for adults (ADR-0012e)
        return check_red_rules(input)
    
    # Get developmental stage
    age = input.person_metadata.get("age", 10)
    stage = get_developmental_stage(age)
    
    # Rule RED_001_DEV: Minor distress (age-adjusted threshold)
    if input.valence < stage.distress_valence_threshold and input.arousal > stage.high_arousal_threshold:
        reasons.append(f"{stage.name.capitalize()} expressing high distress (valence {input.valence:.2f}, arousal {input.arousal:.2f})")
        rule_ids.append("RED_001_DEV")
    
    # Rule RED_002_DEV: Parent-child conflict (age-adjusted)
    if input.other_actors:
        parents_present = [
            actor for actor in input.other_actors
            if relationship_graph.is_minor_with_parent(input.person_id, actor)
        ]
        
        if parents_present and input.valence < stage.distress_valence_threshold:
            reasons.append(f"Parent-{stage.name} conflict detected")
            rule_ids.append("RED_002_DEV")
    
    # Rule RED_007_DEV: Bedtime arousal (age-adjusted threshold)
    if input.time_of_day == "night" and input.arousal > stage.bedtime_arousal_threshold:
        reasons.append(f"{stage.name.capitalize()} high arousal at bedtime (arousal {input.arousal:.2f})")
        rule_ids.append("RED_007_DEV")
    
    if reasons:
        return BandingResult(
            band="RED",
            confidence=input.confidence,
            reasons=reasons,
            rule_ids=rule_ids
        )
    
    return None
```

---

### 4. Lifecycle Context Modifiers

**Time-of-day and lifecycle events** modify affect interpretation:

```python
@dataclass
class LifecycleContext:
    """Lifecycle context for affect interpretation."""
    
    time_of_day: str            # "morning", "afternoon", "evening", "night"
    day_of_week: str            # "monday", ..., "sunday"
    is_weekend: bool
    is_holiday: bool
    special_event: Optional[str] = None  # "birthday", "vacation", "first_day_school"
    
    # School context (for minors)
    is_school_hours: bool = False       # 8am-3pm on weekdays
    is_bedtime: bool = False            # 8pm-11pm (age-dependent)


def get_lifecycle_context(timestamp: float, age: int, household_calendar: dict) -> LifecycleContext:
    """
    Compute lifecycle context from timestamp and household calendar.
    """
    dt = datetime.fromtimestamp(timestamp)
    
    # Time of day
    hour = dt.hour
    if 5 <= hour < 12:
        time_of_day = "morning"
    elif 12 <= hour < 17:
        time_of_day = "afternoon"
    elif 17 <= hour < 21:
        time_of_day = "evening"
    else:
        time_of_day = "night"
    
    # Day of week
    day_of_week = dt.strftime("%A").lower()
    is_weekend = day_of_week in ["saturday", "sunday"]
    
    # School hours (for minors)
    is_school_hours = (
        age < 18 and
        not is_weekend and
        8 <= hour < 15
    )
    
    # Bedtime (age-dependent)
    bedtime_hours = {
        (0, 5): (19, 21),      # Toddlers: 7pm-9pm
        (6, 12): (20, 22),     # Children: 8pm-10pm
        (13, 17): (21, 23),    # Teens: 9pm-11pm
        (18, 150): (22, 24),   # Adults: 10pm-12am
    }
    
    for (min_age, max_age), (start_hour, end_hour) in bedtime_hours.items():
        if min_age <= age <= max_age:
            is_bedtime = start_hour <= hour < end_hour
            break
    
    # Holidays (from household calendar)
    is_holiday = household_calendar.get(dt.date(), {}).get("is_holiday", False)
    special_event = household_calendar.get(dt.date(), {}).get("event")
    
    return LifecycleContext(
        time_of_day=time_of_day,
        day_of_week=day_of_week,
        is_weekend=is_weekend,
        is_holiday=is_holiday,
        special_event=special_event,
        is_school_hours=is_school_hours,
        is_bedtime=is_bedtime
    )


def apply_lifecycle_modifiers(
    base_valence: float,
    base_arousal: float,
    lifecycle: LifecycleContext,
    is_minor: bool
) -> Tuple[float, float, list[str]]:
    """
    Apply lifecycle context modifiers to affect scores.
    
    Returns:
        (modified_valence, modified_arousal, modifier_tags)
    """
    valence = base_valence
    arousal = base_arousal
    modifier_tags = []
    
    # MODIFIER 1: School hours (if minor)
    if is_minor and lifecycle.is_school_hours:
        # High arousal during school hours = potential issue
        if arousal > 0.7:
            arousal = min(arousal * 1.2, 1.0)  # Amplify arousal
            modifier_tags.append("school_hours_high_arousal")
        
        # Negative valence during school hours = potential truancy/distress
        if valence < -0.4:
            valence *= 1.2  # Amplify negative valence
            modifier_tags.append("school_hours_distress")
    
    # MODIFIER 2: Bedtime
    if lifecycle.is_bedtime:
        # High arousal at bedtime = concern (especially for minors)
        if arousal > 0.6:
            if is_minor:
                arousal = min(arousal * 1.3, 1.0)  # Amplify arousal for minors
                modifier_tags.append("bedtime_arousal_minor")
            else:
                arousal = min(arousal * 1.1, 1.0)  # Slight amplification for adults
                modifier_tags.append("bedtime_arousal_adult")
    
    # MODIFIER 3: Special events
    if lifecycle.special_event:
        if lifecycle.special_event in ["birthday", "holiday", "celebration"]:
            # Positive events: Amplify positive valence
            if valence > 0.3:
                valence = min(valence * 1.2, 1.0)
                modifier_tags.append(f"special_event_{lifecycle.special_event}")
        
        elif lifecycle.special_event in ["first_day_school", "test_day"]:
            # Stressful events: Amplify arousal
            arousal = min(arousal * 1.15, 1.0)
            modifier_tags.append(f"special_event_{lifecycle.special_event}")
    
    # MODIFIER 4: Weekend vs weekday
    if lifecycle.is_weekend:
        # Weekends: Slight relaxation (lower arousal baseline)
        arousal *= 0.95
        modifier_tags.append("weekend")
    
    # Clamp to valid ranges
    valence = np.clip(valence, -1.0, 1.0)
    arousal = np.clip(arousal, 0.0, 1.0)
    
    return valence, arousal, modifier_tags
```

---

### 5. Enhanced Child Safety Rules

**Stricter rules for minors** with relationship context:

```python
# Additional RED rules for minors (supplement ADR-0012e)

RED_RULES_MINORS = {
    "RED_101": {
        "condition": lambda input: (
            input.is_minor and
            input.valence < -0.4 and
            any(rel.is_minor_with_parent(input.person_id, actor) for actor in input.other_actors)
        ),
        "reason": "Minor distress in presence of parent",
        "notify_guardian": True
    },
    
    "RED_102": {
        "condition": lambda input: (
            input.is_minor and
            input.arousal > 0.7 and
            input.lifecycle.is_school_hours
        ),
        "reason": "Minor high arousal during school hours (potential truancy/distress)",
        "notify_guardian": True
    },
    
    "RED_103": {
        "condition": lambda input: (
            input.is_minor and
            input.valence < -0.5 and
            not any(rel.is_minor_with_parent(input.person_id, actor) for actor in input.other_actors)
        ),
        "reason": "Minor distress without parent present",
        "notify_guardian": True
    },
    
    "RED_104": {
        "condition": lambda input: (
            input.is_minor and
            input.age < 13 and  # Children under 13
            input.arousal > 0.6 and
            input.lifecycle.is_bedtime
        ),
        "reason": "Young child high arousal at bedtime",
        "notify_guardian": True
    },
    
    "RED_105": {
        "condition": lambda input: (
            input.is_minor and
            "conflict" in input.tags and
            len([actor for actor in input.other_actors if input.relationship_graph.is_minor_with_parent(input.person_id, actor)]) == 0
        ),
        "reason": "Minor in conflict without parent supervision",
        "notify_guardian": True
    },
}


def check_minor_safety_rules(input: BandingInput) -> Optional[BandingResult]:
    """
    Check enhanced child safety rules.
    
    Returns RED band result if any minor safety rule fires.
    """
    if not input.is_minor:
        return None
    
    reasons = []
    rule_ids = []
    
    for rule_id, rule_spec in RED_RULES_MINORS.items():
        if rule_spec["condition"](input):
            reasons.append(rule_spec["reason"])
            rule_ids.append(rule_id)
    
    if reasons:
        return BandingResult(
            band="RED",
            confidence=input.confidence,
            reasons=reasons,
            rule_ids=rule_ids,
            notify_guardian=True  # Always notify for minor safety rules
        )
    
    return None
```

---

### 6. Integration with Policy Pipeline

**Complete affect → policy pipeline** with social cognition:

```python
def compute_affect_with_social_context(
    event: Event,
    relationship_graph: RelationshipGraph,
    household_calendar: dict
) -> AffectAnnotation:
    """
    Full affect computation pipeline with social cognition.
    
    Steps:
    1. Base affect classification (Tier-0 or Tier-1)
    2. Social context modifiers (relationships)
    3. Lifecycle context modifiers (time-of-day, special events)
    4. Developmental stage adjustments (age-appropriate thresholds)
    5. Policy banding with enhanced minor safety rules
    """
    # Step 1: Base classification
    base_result = affect_classifier.classify(event.text, event.behavior)
    
    # Step 2: Social context modifiers
    valence, arousal, social_tags = apply_social_context_modifiers(
        base_result.valence,
        base_result.arousal,
        event.person_id,
        event.other_actors,
        relationship_graph,
        event.person_metadata
    )
    
    # Step 3: Lifecycle context modifiers
    lifecycle = get_lifecycle_context(event.timestamp, event.person_metadata["age"], household_calendar)
    valence, arousal, lifecycle_tags = apply_lifecycle_modifiers(
        valence,
        arousal,
        lifecycle,
        event.person_metadata["is_minor"]
    )
    
    # Step 4: EMA smoothing (ADR-0012d)
    valence_ema, arousal_ema, confidence, attribution = fusion.fuse_and_smooth(
        event.person_id,
        event.space_id,
        [ModalityScore(valence, arousal, base_result.confidence, "combined")]
    )
    
    # Step 5: Policy banding with social context
    banding_input = BandingInput(
        valence=valence_ema,
        arousal=arousal_ema,
        tags=base_result.tags + social_tags + lifecycle_tags,
        confidence=confidence,
        person_id=event.person_id,
        space_id=event.space_id,
        is_minor=event.person_metadata["is_minor"],
        other_actors=event.other_actors,
        relationship_graph=relationship_graph,
        lifecycle=lifecycle
    )
    
    # Check minor safety rules first
    banding_result = check_minor_safety_rules(banding_input)
    
    # Fall back to standard rules
    if banding_result is None:
        banding_result = compute_band_with_household_context(banding_input, household_state, event.person_id)
    
    return AffectAnnotation(
        event_id=event.event_id,
        space_id=event.space_id,
        valence=valence_ema,
        arousal=arousal_ema,
        tags=banding_input.tags,
        confidence=confidence,
        band=banding_result.band,
        band_reasons=banding_result.reasons,
        model_version="affect_v1.0",
        timestamp=time.time()
    )
```

---

### 7. Privacy & Security

**Relationship graph security**:

- **Encrypted storage**: Relationship graph encrypted with household-scoped MLS key
- **Access control**: Only K0 affect module and policy engine can read relationships
- **No external exposure**: Relationships never leave device, not in logs/metrics
- **Anonymized aggregates**: If logging needed, use person_id hashes

**Audit logging**:

```python
# Log policy decisions with minimal context
audit_logger.log({
    "event_id": event.event_id,
    "band": banding_result.band,
    "rule_ids": banding_result.rule_ids,
    "social_context": "parent_child" if any("parent_child" in tag for tag in social_tags) else "other",
    "is_minor": event.person_metadata["is_minor"],
    "timestamp": time.time()
})
# NO relationship details, NO person_ids in clear text
```

---

## Consequences

### Positive

✅ **Relationship-aware policy**: Same affect interpreted differently based on relationships  
✅ **Developmental appropriateness**: Age-appropriate thresholds for minors  
✅ **Context-aware**: Time-of-day and lifecycle events modify interpretation  
✅ **Enhanced child safety**: Stricter rules for minors, especially with parents  
✅ **Privacy-preserving**: Relationship graph encrypted, minimal exposure  

### Negative

❌ **Complexity**: Adds relationship graph, developmental stages, lifecycle context  
❌ **Maintenance**: Relationship graph must be kept up-to-date  
❌ **Cultural bias**: Relationship norms vary across cultures  
❌ **Privacy risk**: Even encrypted relationship graph reveals household structure  

### Risks

- **Relationship graph staleness**: Outdated relationships lead to incorrect modifiers
- **Cultural insensitivity**: "Parent-child conflict" rules may not generalize
- **False escalation**: Over-amplification for parent-child conflicts frustrates users
- **Privacy leakage**: Relationship graph could be inferred from policy decisions

**Mitigation**:

- **User-managed relationships**: Allow users to edit relationship graph in settings
- **Cultural sensitivity**: Expose social context modifiers in dashboards, allow adjustment
- **A/B testing**: Validate social modifiers improve safety without frustrating users
- **Privacy audit**: Regular review of what relationship data is logged/exposed
- **Rollback**: Feature flag to disable social cognition modifiers

---

## Implementation Checklist

- [ ] Implement `RelationshipGraph` data structure
- [ ] Implement social context modifiers (parent-child, sibling, partner)
- [ ] Implement developmental stage thresholds
- [ ] Implement lifecycle context modifiers (time-of-day, special events)
- [ ] Implement enhanced minor safety rules (RED_101 - RED_105)
- [ ] Integrate into affect → policy pipeline
- [ ] Add relationship graph storage (encrypted in `st_relationships`)
- [ ] Add household calendar integration
- [ ] Unit tests: Social modifiers, lifecycle modifiers, minor safety rules
- [ ] Integration tests: Full affect pipeline with social context
- [ ] Privacy audit: Verify relationship graph not exposed
- [ ] Documentation: Social cognition guide, relationship management UI

---

## References

- **Parent ADR**: ADR-0012 (Affect Module)
- **Related ADRs**:
  - k003a (Affect Contracts & Storage)
  - k003e (Policy Band Rules & P18 Integration)
  - k003g (Household-Level Affect Dynamics)
  - k003i (Counterfactual Safety)
- **Module Locations**:
  - `k0/modules/affect/social_context.py`
  - `k0/modules/affect/relationship_graph.py`
  - `k0/modules/affect/lifecycle_context.py`
- **Research**:
  - Social Cognition: Frith & Frith, 2012 (Nature Reviews Neuroscience)
  - Developmental Psychology: Steinberg, 2005 (Annual Review of Psychology)
  - Family Systems: Bowen, 1978

---

## Revision History

- 2025-11-13: Initial draft (@K0-Architecture)
