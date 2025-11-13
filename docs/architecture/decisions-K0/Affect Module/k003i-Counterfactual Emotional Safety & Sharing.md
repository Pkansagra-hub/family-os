---
adr_number: '0012i'
parent_adr: '0012'
affected_layers:
  - K0 Memory Kernel
  - Policy & Safety Plane
  - K1 Intelligence Layer
affected_modules:
  - affect
  - modules/affect
  - policy
  - k1.planner
authors:
  - '@K0-Architecture'
  - '@K1-Architecture'
concerns:
  - safety
  - privacy
  - policy
  - architecture
  - simulation
date_created: '2025-11-13'
date_updated: '2025-11-13'
implementation_status: ACCEPTED
status: ACCEPTED
title: 'ADR-0012i: Counterfactual Emotional Safety & Sharing'
---

# ADR-0012i: Counterfactual Emotional Safety & Sharing

**Status**: Accepted
**Parent ADR**: ADR-0012 (Affect Module)
**Date**: 2025-11-13
**Authors**: @K0-Architecture, @K1-Architecture

---

## Context

ADR-0012e defines **policy bands** (GREEN/AMBER/RED/BLACK), ADR-0012g defines **household affect dynamics**, and ADR-0012h defines **social cognition**. This ADR specifies:

1. **Counterfactual reasoning**: "What if we share this message?" - simulate affect impact before action
2. **Sharing safety**: Prevent emotionally triggering content from being shared to spaces/people
3. **Notification timing**: Simulate affect impact of notification before sending
4. **Recall safety**: Prevent triggering memories from surfacing during vulnerable states
5. **Planning safety**: K1 evaluates affect impact of proposed actions before execution

**Goals**:

- **Proactive safety**: Prevent emotional harm before it happens
- **Simulation-based policy**: Use affect simulation to inform sharing/notification decisions
- **Explainable**: Show users why content was blocked/delayed
- **Low latency**: Counterfactual simulation <10ms (within decision path)
- **Privacy-preserving**: Simulate affect without exposing raw content

**Key Use Cases**:

- **Sharing during conflict**: "Don't share family photo to shared space during household conflict" → Block share
- **Triggering notification**: "Don't notify parent about child's distress while parent is also distressed" → Delay notification
- **Recall during distress**: "Don't surface sad memories when user is already sad" → Filter recall results
- **Planning impact**: "Suggesting vacation planning during household conflict" → Delay suggestion
- **Multi-recipient safety**: "Message safe for Mom but triggering for Teen" → Block share to Teen

---

## Decision

### 1. Counterfactual Affect Simulation

**Core Concept**: Simulate how content/action would affect recipient(s) before taking action

**Simulation Pipeline**:

```python
@dataclass
class CounterfactualInput:
    """Input for counterfactual affect simulation."""

    # Content to simulate
    content: str                        # Message, memory, notification text
    content_affect: AffectAnnotation    # Pre-computed affect of content

    # Recipients
    recipient_ids: list[str]            # Who would receive this content
    target_space_id: str                # Where content would be shared

    # Current state
    recipient_states: dict[str, AffectEMAState]         # Current affect of recipients
    household_state: HouseholdAffectState               # Current household state

    # Action type
    action_type: str                    # "share", "notify", "recall", "suggest"

    # Metadata
    timestamp: float


@dataclass
class CounterfactualResult:
    """Result of counterfactual affect simulation."""

    # Predicted impact
    predicted_valence_delta: dict[str, float]   # person_id → Δvalence
    predicted_arousal_delta: dict[str, float]   # person_id → Δarousal

    # Predicted bands after action
    predicted_bands: dict[str, str]             # person_id → band

    # Safety decision
    is_safe: bool                               # Safe to proceed?
    blocked_recipients: list[str]               # person_ids to exclude

    # Explanation
    reasons: list[str]                          # Why blocked/allowed

    # Confidence
    confidence: float                           # [0, 1]
```

**Simulation Algorithm**:

```python
def simulate_affect_impact(input: CounterfactualInput) -> CounterfactualResult:
    """
    Simulate affect impact of action before taking it.

    Returns safety decision and predicted affect changes.
    """
    predicted_valence_delta = {}
    predicted_arousal_delta = {}
    predicted_bands = {}
    blocked_recipients = []
    reasons = []

    for recipient_id in input.recipient_ids:
        # Get current recipient state
        current_state = input.recipient_states.get(recipient_id)
        if current_state is None:
            # Unknown state → assume neutral
            current_state = AffectEMAState(
                person_id=recipient_id,
                space_id=input.target_space_id,
                v_fast=0.0,
                a_fast=0.3
            )

        # Simulate affect impact
        valence_delta, arousal_delta = predict_affect_change(
            content_affect=input.content_affect,
            current_state=current_state,
            action_type=input.action_type
        )

        # Compute predicted new state
        predicted_valence = current_state.v_fast + valence_delta
        predicted_arousal = current_state.a_fast + arousal_delta

        # Clamp to valid ranges
        predicted_valence = np.clip(predicted_valence, -1.0, 1.0)
        predicted_arousal = np.clip(predicted_arousal, 0.0, 1.0)

        # Predict policy band after action
        predicted_band = predict_band(predicted_valence, predicted_arousal, input.content_affect.tags)

        # Check safety
        is_safe_for_recipient = check_recipient_safety(
            current_state=current_state,
            predicted_valence=predicted_valence,
            predicted_arousal=predicted_arousal,
            predicted_band=predicted_band,
            household_state=input.household_state
        )

        if not is_safe_for_recipient:
            blocked_recipients.append(recipient_id)
            reasons.append(f"Blocked for {recipient_id}: {get_block_reason(current_state, predicted_band)}")

        predicted_valence_delta[recipient_id] = valence_delta
        predicted_arousal_delta[recipient_id] = arousal_delta
        predicted_bands[recipient_id] = predicted_band

    # Overall safety decision
    is_safe = len(blocked_recipients) == 0

    # Confidence (lower if many recipients or high variance)
    confidence = compute_simulation_confidence(input, predicted_valence_delta)

    return CounterfactualResult(
        predicted_valence_delta=predicted_valence_delta,
        predicted_arousal_delta=predicted_arousal_delta,
        predicted_bands=predicted_bands,
        is_safe=is_safe,
        blocked_recipients=blocked_recipients,
        reasons=reasons if not is_safe else ["Safe to proceed"],
        confidence=confidence
    )
```

---

### 2. Affect Impact Prediction

**Predict how content will change recipient's affect**:

```python
def predict_affect_change(
    content_affect: AffectAnnotation,
    current_state: AffectEMAState,
    action_type: str
) -> Tuple[float, float]:
    """
    Predict Δvalence, Δarousal from content affect and current state.

    Uses simple linear model (can be replaced with learned model later).

    Returns:
        (valence_delta, arousal_delta)
    """
    # Base impact from content affect
    content_valence = content_affect.valence
    content_arousal = content_affect.arousal

    # Impact magnitude depends on action type
    action_weights = {
        "share": 0.3,       # Sharing has moderate impact
        "notify": 0.4,      # Notifications more impactful
        "recall": 0.2,      # Recall less impactful (user-initiated)
        "suggest": 0.2,     # Suggestions less impactful
    }

    impact_weight = action_weights.get(action_type, 0.3)

    # Valence delta (content pushes toward its valence)
    # Effect dampened if already aligned
    valence_alignment = content_valence * current_state.v_fast
    if valence_alignment > 0:
        # Already aligned → less impact
        valence_delta = impact_weight * content_valence * 0.5
    else:
        # Opposing → more impact
        valence_delta = impact_weight * content_valence

    # Arousal delta (content arousal adds to current arousal)
    # Diminishing returns (harder to increase already high arousal)
    arousal_headroom = 1.0 - current_state.a_fast
    arousal_delta = impact_weight * content_arousal * arousal_headroom

    return valence_delta, arousal_delta


def predict_band(valence: float, arousal: float, tags: list[str]) -> str:
    """
    Predict policy band from affect values (simplified version of ADR-0012e).
    """
    # BLACK: Toxic content
    if "toxic_severe" in tags or "explicit_content" in tags:
        return "BLACK"

    # RED: High risk
    if valence < -0.5 and arousal > 0.7:
        return "RED"
    if "toxic_moderate" in tags:
        return "RED"

    # AMBER: Moderate risk
    if arousal > 0.7 or valence < -0.4:
        return "AMBER"

    # GREEN: Safe
    return "GREEN"
```

---

### 3. Safety Checks

**Determine if action is safe for recipient**:

```python
def check_recipient_safety(
    current_state: AffectEMAState,
    predicted_valence: float,
    predicted_arousal: float,
    predicted_band: str,
    household_state: HouseholdAffectState
) -> bool:
    """
    Check if action is safe for recipient.

    Returns True if safe, False if should block.
    """
    # Rule 1: Don't push into RED band
    if predicted_band == "RED" and current_state.v_fast > -0.5:
        return False  # Would push recipient into distress

    # Rule 2: Don't amplify distress
    if current_state.v_fast < -0.5 and predicted_valence < current_state.v_fast:
        return False  # Would make distressed recipient more distressed

    # Rule 3: Don't spike arousal during conflict
    if household_state.conflict_active and predicted_arousal > 0.7:
        return False  # Would spike arousal during conflict

    # Rule 4: Don't push arousal too high
    if predicted_arousal > 0.85:
        return False  # Would push arousal to extreme

    # Rule 5: Don't push into BLACK band
    if predicted_band == "BLACK":
        return False  # Never safe to push into BLACK

    return True


def get_block_reason(current_state: AffectEMAState, predicted_band: str) -> str:
    """Generate human-readable reason for blocking."""
    if predicted_band == "RED":
        return "Would cause distress"
    elif predicted_band == "BLACK":
        return "Content violates safety policy"
    elif current_state.v_fast < -0.5:
        return "Recipient already distressed, would worsen"
    else:
        return "Would create unsafe emotional state"
```

---

### 4. Sharing Safety

**Use counterfactual simulation to block unsafe shares**:

```python
class SharingPolicy:
    def __init__(self):
        self.affect_service = AffectService()
        self.simulator = CounterfactualSimulator()

    def evaluate_share(self,
                      content: str,
                      source_person_id: str,
                      target_space_id: str,
                      recipient_ids: list[str]) -> Tuple[bool, list[str], list[str]]:
        """
        Evaluate whether sharing is safe.

        Returns:
            (is_allowed, allowed_recipients, block_reasons)
        """
        # Get content affect
        content_affect = self.affect_service.classify_text(content)

        # Get current states
        recipient_states = {
            rid: self.affect_service.get_ema_state(rid, target_space_id)
            for rid in recipient_ids
        }

        household_state = self.affect_service.get_household_state(target_space_id)

        # Simulate impact
        sim_result = self.simulator.simulate_affect_impact(
            CounterfactualInput(
                content=content,
                content_affect=content_affect,
                recipient_ids=recipient_ids,
                target_space_id=target_space_id,
                recipient_states=recipient_states,
                household_state=household_state,
                action_type="share",
                timestamp=time.time()
            )
        )

        # Decision
        if sim_result.is_safe:
            return True, recipient_ids, []
        else:
            # Partial block: allow for safe recipients only
            allowed_recipients = [
                rid for rid in recipient_ids
                if rid not in sim_result.blocked_recipients
            ]

            return len(allowed_recipients) > 0, allowed_recipients, sim_result.reasons
```

**Example**:

```python
# Scenario: Share family photo during household conflict
is_allowed, allowed_recipients, reasons = sharing_policy.evaluate_share(
    content="Family photo from vacation",
    source_person_id="mom",
    target_space_id="family",
    recipient_ids=["dad", "teen", "child"]
)

# Simulation predicts:
# - Dad (current valence=-0.6, conflict participant): Would spike arousal → BLOCKED
# - Teen (current valence=-0.5, conflict participant): Would spike arousal → BLOCKED
# - Child (current valence=0.2, not in conflict): Safe → ALLOWED

# Result:
# is_allowed=True (partial)
# allowed_recipients=["child"]
# reasons=["Blocked for dad: Would spike arousal during conflict",
#          "Blocked for teen: Would spike arousal during conflict"]
```

---

### 5. Notification Timing

**Use counterfactual simulation to delay unsafe notifications**:

```python
class NotificationPolicy:
    def __init__(self):
        self.affect_service = AffectService()
        self.simulator = CounterfactualSimulator()
        self.pending_notifications = []  # Queue for delayed notifications

    def should_send_notification(self,
                                 notification: Notification,
                                 recipient_id: str) -> Tuple[bool, Optional[float], list[str]]:
        """
        Decide whether to send notification now or delay.

        Returns:
            (send_now, delay_until_timestamp, reasons)
        """
        # Get recipient state
        recipient_state = self.affect_service.get_ema_state(recipient_id, notification.space_id)
        household_state = self.affect_service.get_household_state(notification.space_id)

        # Classify notification affect
        notif_affect = self.affect_service.classify_text(notification.content)

        # Simulate impact
        sim_result = self.simulator.simulate_affect_impact(
            CounterfactualInput(
                content=notification.content,
                content_affect=notif_affect,
                recipient_ids=[recipient_id],
                target_space_id=notification.space_id,
                recipient_states={recipient_id: recipient_state},
                household_state=household_state,
                action_type="notify",
                timestamp=time.time()
            )
        )

        # Decision
        if sim_result.is_safe:
            return True, None, []

        # Unsafe: Determine delay
        if notification.priority == "urgent":
            # Urgent notifications: Send anyway with warning
            return True, None, sim_result.reasons

        else:
            # Non-urgent: Delay until recipient state improves
            delay_until = self._estimate_recovery_time(recipient_state, household_state)
            self.pending_notifications.append((notification, recipient_id, delay_until))
            return False, delay_until, sim_result.reasons

    def _estimate_recovery_time(self,
                               recipient_state: AffectEMAState,
                               household_state: HouseholdAffectState) -> float:
        """
        Estimate when recipient will be in better state.

        Heuristic: Wait for arousal to drop below 0.6 or conflict to resolve.
        """
        if household_state.conflict_active:
            # Wait for conflict to resolve (assume 15 minutes average)
            return time.time() + 900

        elif recipient_state.a_fast > 0.7:
            # Wait for arousal to drop (assume 10 minutes)
            return time.time() + 600

        else:
            # Wait for valence to improve (assume 20 minutes)
            return time.time() + 1200
```

**Example**:

```python
# Scenario: Notify parent about child's homework due tomorrow
notification = Notification(
    content="Reminder: Emma's homework due tomorrow",
    priority="normal",
    space_id="family"
)

send_now, delay_until, reasons = notif_policy.should_send_notification(
    notification, recipient_id="mom"
)

# Simulation predicts:
# - Mom (current valence=-0.6, arousal=0.8, in conflict): Would spike arousal → DELAY

# Result:
# send_now=False
# delay_until=1699900800 (15 minutes from now)
# reasons=["Recipient in distressed state, delaying notification"]
```

---

### 6. Recall Safety

**Filter recall results based on recipient state**:

```python
class RecallSafetyFilter:
    def __init__(self):
        self.affect_service = AffectService()
        self.simulator = CounterfactualSimulator()

    def filter_recall_results(self,
                             query: str,
                             results: list[Memory],
                             person_id: str,
                             space_id: str,
                             limit: int) -> list[Memory]:
        """
        Filter recall results to avoid triggering content.

        Returns safe memories only.
        """
        # Get current state
        current_state = self.affect_service.get_ema_state(person_id, space_id)
        household_state = self.affect_service.get_household_state(space_id)

        safe_results = []

        for memory in results:
            # Get memory affect
            memory_affect = memory.affect_annotation

            # Simulate impact
            sim_result = self.simulator.simulate_affect_impact(
                CounterfactualInput(
                    content=memory.content,
                    content_affect=memory_affect,
                    recipient_ids=[person_id],
                    target_space_id=space_id,
                    recipient_states={person_id: current_state},
                    household_state=household_state,
                    action_type="recall",
                    timestamp=time.time()
                )
            )

            # Include if safe
            if sim_result.is_safe:
                safe_results.append(memory)
            else:
                logger.info(f"Filtered memory {memory.id}: {sim_result.reasons[0]}")

            if len(safe_results) >= limit:
                break

        return safe_results
```

**Example**:

```python
# Scenario: User asks "Show me memories from last year" while sad
query = "memories from last year"
results = recall_engine.search(query, limit=100)

# Current state: valence=-0.6 (sad), arousal=0.4 (calm)

filtered_results = recall_filter.filter_recall_results(
    query=query,
    results=results,
    person_id="user",
    space_id="personal",
    limit=10
)

# Simulation filters out:
# - Sad memories (would worsen distress)
# - High-arousal memories (would spike arousal)
# - Memories with "distressing" tag

# Returns:
# - Neutral or positive memories only
# - 10 safe results (vs 100 unfiltered)
```

---

### 7. Planning Safety (K1 Integration)

**K1 evaluates affect impact of proposed actions**:

```python
class K1PlanningWithAffectSafety:
    def __init__(self):
        self.affect_service = AffectService()
        self.simulator = CounterfactualSimulator()

    def evaluate_plan_action(self,
                            action: PlanAction,
                            session: SessionState) -> Tuple[bool, list[str]]:
        """
        Evaluate whether plan action is emotionally safe.

        Returns:
            (is_safe, reasons)
        """
        # Get current state
        current_state = self.affect_service.get_ema_state(session.person_id, session.space_id)
        household_state = self.affect_service.get_household_state(session.space_id)

        # Classify action affect
        action_affect = self.affect_service.classify_text(action.description)

        # Simulate impact
        sim_result = self.simulator.simulate_affect_impact(
            CounterfactualInput(
                content=action.description,
                content_affect=action_affect,
                recipient_ids=[session.person_id],
                target_space_id=session.space_id,
                recipient_states={session.person_id: current_state},
                household_state=household_state,
                action_type="suggest",
                timestamp=time.time()
            )
        )

        return sim_result.is_safe, sim_result.reasons

    def generate_safe_plan(self, session: SessionState) -> Plan:
        """
        Generate plan, filtering out emotionally unsafe actions.
        """
        # Generate candidate actions
        candidate_actions = self.planner.generate_actions(session)

        # Filter for emotional safety
        safe_actions = []
        for action in candidate_actions:
            is_safe, reasons = self.evaluate_plan_action(action, session)
            if is_safe:
                safe_actions.append(action)
            else:
                logger.info(f"Filtered action '{action.description}': {reasons[0]}")

        # Build plan from safe actions
        return Plan(actions=safe_actions, session_id=session.session_id)
```

**Example**:

```python
# Scenario: K1 suggests vacation planning during household conflict
session = SessionState(
    person_id="mom",
    space_id="family",
    affect=AffectSummary(valence=-0.5, arousal=0.7, band="RED")
)

candidate_actions = [
    PlanAction(description="Plan summer vacation", priority="low"),
    PlanAction(description="Reschedule dentist appointment", priority="high"),
    PlanAction(description="Review family budget", priority="medium"),
]

plan = k1_planner.generate_safe_plan(session)

# Simulation filters:
# - "Plan summer vacation": Would spike arousal during conflict → FILTERED
# - "Review family budget": Would add stress during conflict → FILTERED
# - "Reschedule dentist": Neutral task, high priority → ALLOWED

# Result:
# plan.actions = [PlanAction("Reschedule dentist appointment")]
```

---

### 8. Performance Budget

**Latency Target**: <10ms P95 for counterfactual simulation

**Breakdown**:

| Step | Latency | Notes |
|------|---------|-------|
| Load recipient states | 1ms | In-memory cache lookup |
| Classify content affect | 2ms | Tier-0 classifier (cached if repeated) |
| Predict affect change | 1ms | Simple linear model |
| Predict bands | 1ms | Simplified band rules |
| Safety checks | 2ms | Rule evaluation |
| **Total** | **7ms** | ✅ Within 10ms budget |

**Optimization**:

- **Cache content affect**: Same content → same affect (cache for 5 minutes)
- **Batch simulations**: Multiple recipients → parallel simulation
- **Simplified band prediction**: Use fast heuristics instead of full ADR-0012e rules

---

### 9. Observability

**Prometheus Metrics**:

```python
# Counterfactual simulation metrics
counterfactual_simulations = Counter(
    "k0_counterfactual_simulations_total",
    "Number of counterfactual affect simulations",
    ["action_type"]  # share, notify, recall, suggest
)

counterfactual_blocks = Counter(
    "k0_counterfactual_blocks_total",
    "Number of actions blocked by counterfactual simulation",
    ["action_type", "block_reason"]
)

counterfactual_partial_blocks = Counter(
    "k0_counterfactual_partial_blocks_total",
    "Number of partial blocks (some recipients blocked)",
    ["action_type"]
)

counterfactual_simulation_latency = Histogram(
    "k0_counterfactual_simulation_latency_seconds",
    "Latency of counterfactual affect simulation",
    ["action_type"]
)

# Validation metrics (from user feedback)
counterfactual_accuracy = Histogram(
    "k0_counterfactual_accuracy",
    "Accuracy of counterfactual predictions (validated by user feedback)",
    ["action_type"]
)
```

---

## Consequences

### Positive

✅ **Proactive safety**: Prevents emotional harm before it happens
✅ **Simulation-based policy**: Uses affect prediction to inform decisions
✅ **Explainable**: Shows users why content was blocked/delayed
✅ **Low latency**: <10ms P95 for simulation
✅ **Flexible**: Supports sharing, notifications, recall, planning

### Negative

❌ **Prediction errors**: False positives block safe content, false negatives allow unsafe content
❌ **Complexity**: Adds counterfactual reasoning layer to policy engine
❌ **User frustration**: Over-blocking may frustrate users
❌ **Validation difficulty**: Hard to validate predictions without ground truth

### Risks

- **False positives**: Over-blocking safe content frustrates users
- **False negatives**: Missing unsafe content causes harm
- **Model staleness**: Affect prediction model may drift over time
- **Computational cost**: Simulating for many recipients may exceed latency budget

**Mitigation**:

- **User feedback**: P06 feedback loop to improve prediction accuracy
- **Confidence thresholds**: Only block high-confidence predictions
- **User override**: Allow users to bypass blocks with confirmation
- **A/B testing**: Validate counterfactual simulation improves safety without frustrating users
- **Performance monitoring**: Alert if simulation latency exceeds 10ms
- **Rollback**: Feature flag to disable counterfactual simulation

---

## Implementation Checklist

- [ ] Implement `CounterfactualSimulator` class
- [ ] Implement affect impact prediction (`predict_affect_change`)
- [ ] Implement safety checks (`check_recipient_safety`)
- [ ] Integrate into sharing policy (ADR-0012e + P18)
- [ ] Integrate into notification timing (K1 Concierge)
- [ ] Integrate into recall filtering (Recall Engine)
- [ ] Integrate into K1 planning (K1 Planner)
- [ ] Unit tests: Impact prediction, safety checks, multi-recipient scenarios
- [ ] Integration tests: Sharing policy, notification delay, recall filtering
- [ ] Performance tests: Simulation latency <10ms P95
- [ ] Observability: Metrics for simulations, blocks, accuracy
- [ ] User feedback: Collect validation data for prediction accuracy
- [ ] Documentation: Counterfactual reasoning guide, user overrides

---

## References

- **Parent ADR**: ADR-0012 (Affect Module)
- **Related ADRs**:
  - k003a (Affect Contracts & Storage)
  - k003e (Policy Band Rules & P18 Integration)
  - k003f (K1 Planner Bridge)
  - k003g (Household-Level Affect Dynamics)
  - k003h (Social Cognition)
- **Module Locations**:
  - `k0/modules/affect/counterfactual.py`
  - `k0/policy/sharing_safety.py`
  - `k1/concierge/notification_timing.py`
  - `k1/recall/safety_filter.py`
- **Research**:
  - Counterfactual Reasoning: Pearl, 2009 (Causality)
  - Emotional Impact Prediction: Buechel & Hahn, 2017 (ACL)
  - Affective Computing: Picard, 1997

---

## Revision History

- 2025-11-13: Initial draft (@K0-Architecture, @K1-Architecture)
