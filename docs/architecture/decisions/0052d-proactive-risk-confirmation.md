---
adr_number: 0052d
title: Proactive Risk Confirmation
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer1_input
- layer2_orchestration
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules: []
concerns:
- architecture
- compliance
- cost
- observability
- performance
- privacy
- reliability
- scalability
- testing
- ux
supersedes: []
superseded_by: []
related_adrs:
- ADR-0003b
- ADR-0007
- ADR-0052a
- ADR-0052b
- ADR-0052c
implementation_status: COMPLETED
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations:
- Amershi et al. (2019)
- Floridi (2018)
- Ribeiro et al. (2016)
- Taddeo & Floridi (2018)
propagation:
  triggers:
  - Modifying system architecture
  - Performance requirement changes
  - Updating API contracts or schemas
  affected_adrs:
  - ADR-0003b
  - ADR-0007
  - ADR-0052a
  - ADR-0052b
  - ADR-0052c
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


# ADR-0052d: Proactive Risk Confirmation

**Status:** ✅ **ACCEPTED** (2025-10-16)
**Date:** 2025-10-16
**Decision Date:** 2025-10-16
**Parent ADR:** [ADR-0052: Enhanced HITL Protocols](0052-enhanced-hitl-protocols.md)
**Authors:** K1 Architecture Team
**Category:** Human-in-the-Loop & Safety
**Technical Story:** [Agent-Initiated Safety Checks for Uncertain Actions]

**Related ADRs:**
- [ADR-0052: Enhanced HITL Protocols](0052-enhanced-hitl-protocols.md) - Parent umbrella ADR
- [ADR-0003b: 6 Core Protocol Implementations](0003b-6-core-protocol-implementations.md) - Protocol 3 (Clarification) foundation
- [ADR-0007: 4-Stage Planning Pipeline](0007-4stage-planning-pipeline.md) - Validation stage integration
- [ADR-0029: Prometheus Metrics](0029-prometheus-metrics-red-method.md) - Confidence metric tracking
- [ADR-0038: Audit Trail to K0 Receipts](0038-audit-trail-to-k0-receipts.md) - Audit logging

---

## Executive Summary

**Purpose:** Enable agents to proactively request user confirmation when action confidence falls below safety thresholds, preventing silent execution of uncertain decisions.

**Core Functionality:**
- **Confidence-Triggered Confirmation:** When agent confidence < threshold, request user confirmation
- **Risk Context Display:** Show agent's reasoning, confidence score, and alternative approaches
- **Explicit Proceed/Retry Options:** User chooses "Proceed" (accept risk) or "Retry" (try alternate approach)
- **Confidence Thresholds:** Configurable per action type (DEFAULT: 0.65 for general, 0.85 for financial)
- **Audit Trail:** Log when agent requested confirmation, user response, confidence scores
- **No Forced Confirmation:** "Proceed" is always available (user can override agent caution)

**Key Design Decisions:**
1. **Agent-initiated, not auto-triggered** — Only fire when agent explicitly requests confirmation
2. **Three confidence tiers:**
   - HIGH (≥0.85): Execute without confirmation
   - MEDIUM (0.65-0.85): Optional warning badge, user can dismiss
   - LOW (<0.65): Mandatory confirmation, show reasoning
3. **Retry option is always available** — User not trapped by agent's cautious decision
4. **Confidence scores tracked as metrics** — Enable drift detection (ADR-0059b)
5. **Timeout: 3 minutes** — Balance between user wait time and stale decision

**Performance Targets:**
- Confidence calculation: <50ms (model inference already done)
- Confirmation display: <100ms (UI render)
- Total HITL overhead: <150ms (P95)

---

## Context

### The Problem

**Current State:** K1 executes actions based on agent confidence, but lacks:
- Explicit user approval when agent is uncertain
- Transparency into agent reasoning and confidence scores
- Recovery path when agent's high-confidence decision was wrong
- Metrics on when agent caution prevented failures

**Risk Scenario 1: Incorrect Recipe Ingredient Substitution**
```
User: "I'm making pasta but we're out of basil. What can I use instead?"

Agent (current behavior - BAD):
  [Confidence: 0.62 - LOW, due to family allergies not checked]
  Agent: "Use oregano instead - same flavor profile!"

  [Later, user's nut-allergic child tries dish]
  User: "WAIT - this has oregano! Is there cross-contamination risk?"
  Agent should have asked: "I'm 62% confident about oregano substitution.
                          Should I double-check for allergy interactions first?"
```

**Risk Scenario 2: Uncertain Financial Category Classification**
```
User: "Categorize my $500 charge from 'ACME Retail' for household budgeting"

Agent (current behavior - BAD):
  [Confidence: 0.58 - LOW, merchant name is ambiguous]
  Agent: "This looks like 'Entertainment & Recreation' based on merchant name"

  [User's budget report shows $500 miscategorized]
  User: "That should be 'Groceries' - ACME is our local supermarket!"

  Agent should have asked: "I'm only 58% confident about this category.
                          Please confirm: Is this 'Groceries' or 'Entertainment'?"
```

**Risk Scenario 3: Unreliable Appointment Scheduling**
```
User: "Schedule Emma's parent-teacher conference"

Agent (current behavior - BAD):
  [Confidence: 0.69 - MEDIUM, missing confirmation about time preference]
  Agent: "I've scheduled the meeting for Thursday 3 PM"

  [Later, user realizes they have another meeting at 3 PM]
  User: "That conflicts with my dentist appointment!"

  Agent should have asked: "I'm 69% confident about this time slot.
                          Should I check your calendar first? Y/N"
```

### Production Requirements

From **Requirement #9 (Safety & Ethics):**
> "Structured clarification during execution with context preservation. Agent-initiated safety checks for uncertain decisions."

From **Requirement #2 (Turn-Taking & Flow):**
> "Graceful handling of agent uncertainty without silent failures. Clear recovery paths."

### Why This Matters

**User Trust:** Transparent agent caution builds confidence
- Users see: "Agent is 72% confident, asking to confirm" → Trust maintained
- Users don't see: "Agent silently made wrong decision" → Trust broken

**Failure Prevention:** Early user involvement prevents downstream errors
- Recipe domain: Allergy interactions caught before eating
- Finance domain: Miscategorization corrected immediately
- Scheduling domain: Double-booking avoided

**Learning Signal:** User confirmations are high-quality feedback
- Confirmed decision → Agent was right → Reward signal
- Rejected decision → Agent was wrong → Penalty signal
- "Retry" → Agent should try alternate approach → Learn alternatives

---

## Decision

### Architecture

**Confidence-Triggered HITL Flow**

```
Agent Planning → Confidence Scoring → Threshold Check
                                          ↓
                                    ┌─────┴─────┐
                                    ↓           ↓
                             Confidence ≥ 0.85  Confidence < 0.85
                             (HIGH)             (LOW/MEDIUM)
                                    ↓           ↓
                                  Execute    [HITL: Proactive Confirmation]
                                            ↓
                                    ┌──────────┴──────────┐
                                    ↓                     ↓
                            User: "Proceed"        User: "Retry"
                                    ↓                     ↓
                                Execute           Try Alternate Approach
                                                  (e.g., ask for more info)
```

**Confidence Scoring Integration**

```
Agent Planner (ADR-0007)
    ├─ Sketch Stage: Generate candidate plans
    ├─ Expand Stage: Add tools and details
    ├─ Validate Stage:
    │    ├─ [NEW] Calculate confidence score
    │    ├─ Check safety thresholds
    │    └─ Trigger confirmation if low
    └─ Commit Stage: Execute approved plan
```

**Confidence Tiers**

| Tier | Score | User Experience | Action |
|------|-------|-----------------|--------|
| **HIGH** | ≥0.85 | Execute silently | Proceed immediately |
| **MEDIUM** | 0.65-0.85 | Warning badge (⚠️ Low confidence) | User can dismiss/proceed/retry |
| **LOW** | <0.65 | Mandatory confirmation dialog | Must choose: Proceed/Retry |

**Confirmation Prompt Design**

```
┌─────────────────────────────────────────────────────┐
│ ⚠️ I'm uncertain about this decision                 │
│                                                     │
│ Agent confidence: 62% (LOW)                         │
│                                                     │
│ What I'm planning:                                  │
│ "Use oregano as basil substitute in pasta sauce"   │
│                                                     │
│ Why I'm uncertain:                                  │
│ - Family allergy list not checked (need verification) │
│ - Oregano flavor profile differs from basil         │
│ - Substitution not in recipe database               │
│                                                     │
│ Alternative approaches I could try:                 │
│ 1. Check your allergy list first                    │
│ 2. Search for FDA-approved substitutes              │
│ 3. Ask: "What herbs do you have available?"        │
│                                                     │
│ What would you like to do?                          │
│ ┌─────────────┐  ┌──────┐  ┌──────┐              │
│ │  Proceed ↓  │  │Retry ↓│  │ Exit │              │
│ └─────────────┘  └──────┘  └──────┘              │
│                                                     │
│ (Proceeds with agent's original plan)              │
│ (Try #1: Check allergies. Confidence will improve) │
│ (Cancel this action)                               │
└─────────────────────────────────────────────────────┘
```

### Confidence Score Calculation

**Base Factors** (0.0 - 1.0 scale):

```python
def calculate_confidence(action: Action, context: SessionState) -> float:
    """Calculate confidence score for proposed action"""

    # Base factors (each 0.0-1.0)
    factors = {
        "domain_match": compute_domain_match(action, context),     # 0.9 if domain known
        "context_completeness": compute_context_completeness(action, context),  # 0.8 if full context
        "plan_similarity": compute_plan_similarity(action, context),  # 0.85 if similar past plans worked
        "prerequisite_check": compute_prerequisite_check(action, context),  # 1.0 if all prereqs met
        "user_preference_alignment": compute_alignment(action, context),  # 0.75 if in user preferences
        "side_effect_assessment": compute_side_effects(action, context),  # 0.9 if no side effects
    }

    # Weights (sum to 1.0)
    weights = {
        "domain_match": 0.20,
        "context_completeness": 0.25,
        "plan_similarity": 0.15,
        "prerequisite_check": 0.20,
        "user_preference_alignment": 0.10,
        "side_effect_assessment": 0.10,
    }

    # Weighted average
    confidence = sum(factors[k] * weights[k] for k in factors.keys())

    # Apply penalties
    if action.has_irreversible_side_effects():
        confidence *= 0.9  # 10% penalty for irreversible actions

    if action.involves_privacy_band_AMBER():
        confidence *= 0.85  # 15% penalty for sensitive data

    if action.involves_privacy_band_RED():
        confidence *= 0.75  # 25% penalty for high-risk operations

    return max(0.0, min(1.0, confidence))  # Clamp to [0.0, 1.0]
```

**Example Calculations**

```
Scenario 1: Recipe Substitution (oregano for basil)
  domain_match: 0.90 (cooking well-known)
  context_completeness: 0.55 (missing allergy check)
  plan_similarity: 0.75 (herb substitution done before)
  prerequisite_check: 0.60 (missing allergy prerequisites)
  user_preference_alignment: 0.70 (user cooking style known)
  side_effect_assessment: 0.65 (allergy risk not assessed)

  confidence = 0.90*0.20 + 0.55*0.25 + 0.75*0.15 + 0.60*0.20 + 0.70*0.10 + 0.65*0.10
            = 0.18 + 0.138 + 0.113 + 0.12 + 0.07 + 0.065
            = 0.666 (MEDIUM)

  → Display warning badge but allow proceed

Scenario 2: Financial Transfer $8,000
  domain_match: 0.95 (finance routine)
  context_completeness: 0.98 (full transaction details)
  plan_similarity: 0.92 (similar transfer done before)
  prerequisite_check: 1.0 (balance verified, account valid)
  user_preference_alignment: 0.95 (within monthly budget)
  side_effect_assessment: 0.95 (no side effects)

  confidence = 0.95*0.20 + 0.98*0.25 + 0.92*0.15 + 1.0*0.20 + 0.95*0.10 + 0.95*0.10
            = 0.19 + 0.245 + 0.138 + 0.20 + 0.095 + 0.095
            = 0.963 (HIGH)

  Apply RED band penalty: 0.963 * 0.75 = 0.722 (MEDIUM)

  → With RED band, still show optional confirmation (covered by ADR-0052b)
```

### FlatBuffers Contract

**Proactive Confirmation Record (stored in K0 receipts):**

```flatbuffers
namespace FamilyOS.HITL;

table ProactiveConfirmationRecord {
  decision_id: string;              // Unique record ID
  trace_id: string;                 // cognitive_trace_id for tracing
  timestamp: int64;                 // Unix timestamp
  user_id: string;

  action_description: string;       // What agent proposed
  confidence_score: float;          // 0.0-1.0
  confidence_tier: string;          // "HIGH", "MEDIUM", "LOW"

  confidence_factors: [ConfidenceFactor];  // Breakdown of confidence calculation

  reasoning_text: string;           // Why agent was uncertain
  alternative_approaches: [string]; // Approaches agent could try instead

  user_response: string;            // "proceeded", "retried", "cancelled"
  response_timestamp: int64;        // When user responded

  outcome: string;                  // "success", "failed", "rolled_back"
  outcome_description: string;      // What actually happened

  feedback_signal: float;           // 1.0 (correct), 0.5 (partial), 0.0 (wrong)
}

table ConfidenceFactor {
  factor_name: string;              // e.g., "domain_match", "context_completeness"
  score: float;                     // 0.0-1.0
  weight: float;                    // How much this factor matters
  explanation: string;              // Why this score
}
```

### Metrics & Monitoring

**Prometheus Metrics (NEW)**

```python
# Count confirmations by outcome
proactive_confirmations_total = Counter(
    'proactive_confirmations_total',
    'Total proactive confirmations requested',
    ['outcome', 'action_type', 'confidence_tier']
)

# Track user decisions
confirmation_user_decisions = Counter(
    'confirmation_user_decisions_total',
    'User decisions on proactive confirmations',
    ['decision', 'confidence_tier']  # decision: "proceeded", "retried", "cancelled"
)

# Distribution of confidence scores
confirmation_confidence_histogram = Histogram(
    'confirmation_confidence_score',
    'Distribution of confidence scores for proactive confirmations',
    buckets=[0.0, 0.25, 0.50, 0.65, 0.75, 0.85, 1.0]
)

# Outcome feedback: Was agent right?
confirmation_outcome_feedback = Counter(
    'confirmation_outcome_feedback_total',
    'Feedback on whether agent\'s caution was justified',
    ['feedback']  # feedback: "was_right", "was_wrong"
)
```

**Example Monitoring**

```
Weekly Report: Proactive Confirmations

Total confirmations: 1,247
├─ HIGH confidence (0.85+): 342 (27%)
│  ├─ User proceeded: 340 (99%)  ← Agent was right
│  └─ User retried: 2 (1%)       ← Agent was overly cautious
│
├─ MEDIUM confidence (0.65-0.85): 654 (52%)
│  ├─ User proceeded: 580 (89%)
│  ├─ User retried: 60 (9%)
│  └─ User cancelled: 14 (2%)
│
└─ LOW confidence (<0.65): 251 (20%)
   ├─ User proceeded: 140 (56%)  ← User overrode agent caution
   ├─ User retried: 100 (40%)    ← Agent caution was justified
   └─ User cancelled: 11 (4%)

Action Type Breakdown:
├─ Recipe/Cooking: 420 confirmations (33.7%)
├─ Financial: 205 confirmations (16.4%)
├─ Scheduling: 378 confirmations (30.3%)
├─ Photos/Media: 156 confirmations (12.5%)
└─ Other: 88 confirmations (7.1%)

Agent Accuracy (Feedback Signal):
├─ Was Right: 1,086/1,247 (87.1%) ✅
├─ Was Wrong: 89/1,247 (7.1%)
├─ Partial: 72/1,247 (5.8%)

Trend (Last 4 weeks):
Week 1: 87.3% accuracy
Week 2: 87.1% accuracy ← This week
Week 3: 86.8% accuracy
Week 4: 86.5% accuracy (trending down - alert)
```

---

## Consequences

### Positive

✅ **Transparent Uncertainty**
- Users see when agent is uncertain, not blindsided by failures
- Builds trust through honest admission of limitations
- Creates dialogue about risky decisions

✅ **Failure Prevention**
- Catches low-confidence decisions before they cause harm
- User knowledge fills gaps agent missed (allergies, scheduling conflicts)
- Proactive approach beats reactive error correction

✅ **High-Quality Feedback Signals**
- User confirmations/rejections provide ground truth
- Enables learning loop (ADR-0059) to improve confidence scoring
- "Retry" signals help agent learn alternative approaches

✅ **Flexible User Control**
- Users can override agent caution ("Proceed anyway")
- Users always have "Retry" option (not trapped by cautious agent)
- Confidence tiers allow tuning (HIGH-confidence actions still silent)

### Negative

❌ **Potential User Fatigue**
- Excessive confirmations for low-risk actions (e.g., "I'm 50% confident you like pasta" 💀)
- Users may habitual-click "Proceed" without reading
- Undermines safety benefit if overused

**Mitigation:**
- Tune confidence thresholds carefully (start HIGH at 0.85, lower gradually)
- Only show confirmations for actions with meaningful impact
- Monitor confirmation click-through rates (alert if >95% - sign of fatigue)

❌ **Latency Impact**
- Confirmation adds 3-5 second wait for user response
- Users might leave conversation while waiting
- 3-minute timeout causes hanging conversations

**Mitigation:**
- Make confirmation optional per user preference
- Show "Proceed Anyway" button for impatient users
- Log timeout occurrences for analysis

❌ **Confidence Scoring Complexity**
- Must maintain 6+ factors for accurate confidence calculation
- Factors need fine-tuning per domain (cooking ≠ finance)
- Drift in confidence scoring leads to false positives/negatives

**Mitigation:**
- Start with conservative thresholds (avoid false positives)
- Use feedback signals to auto-tune weights over time (ADR-0059b)
- Monitor agent accuracy vs. confidence for drift

---

## Implementation Strategy

### Phase 1: Foundation (Week 1)

**Goals:**
- Integrate confidence calculation with Planner Validate stage
- Display confirmation prompt when confidence < 0.65
- Basic audit logging to K0 receipts

**Deliverables:**
1. `confidence_calculator.py` - Implement confidence scoring (6 factors)
2. Update Planner Validate stage: After safety checks, calculate confidence
3. `confirmation_prompt.py` - Render confirmation UI with alternatives
4. Update HITL Protocol 3 to support PROACTIVE_CONFIRM type
5. K0 receipt schema for confirmations
6. Unit tests: Confidence calculation, threshold logic

**Testing:**
- Confidence calculation: Unit tests for each factor
- Threshold logic: Integration tests for 3 tiers
- UI: Manual testing of confirmation prompt display
- Scenario: Recipe substitution with low confidence

### Phase 2: Monitoring & Tuning (Week 2)

**Goals:**
- Export confirmations as Prometheus metrics
- Analyze user decisions (proceed vs. retry vs. cancel)
- Fine-tune confidence thresholds based on real usage

**Deliverables:**
1. Prometheus metrics export (7 new metrics)
2. Weekly report: Confirmation accuracy, user decisions by tier
3. Threshold tuning guide (start HIGH at 0.85, adjust down based on false positives)
4. Grafana dashboard: Confirmation rate, user decisions, agent accuracy trends

**Testing:**
- Metrics: Validate counter increments
- Reporting: Manual review of weekly report
- Tuning: A/B test different thresholds (0.65 vs. 0.70)

### Phase 3: Learning Integration (Week 3-4)

**Goals:**
- Wire confirmation feedback to Learning Loop (ADR-0059)
- Auto-tune confidence weights based on user outcomes
- Enable drift detection (when agent accuracy degrades)

**Deliverables:**
1. Feedback signal generation: Map confirmation outcomes to reward/penalty
2. Learning Loop integration: Send feedback to K0 P06 (FeedbackIntegration)
3. Drift detector: Alert when agent accuracy trending down
4. Auto-tuning: Gradually adjust confidence factor weights

**Testing:**
- Feedback signals: Verify mapping from confirmation outcome to reward
- Learning integration: Trace feedback → K0 P06 → weight update
- Drift detection: Simulate accuracy trend, verify alert
- Auto-tuning: Verify weights adjust in right direction

---

## Acceptance Criteria

- ✅ Confidence scoring implemented with 6 factors (domain_match, context_completeness, etc.)
- ✅ Confidence thresholds: HIGH (≥0.85), MEDIUM (0.65-0.85), LOW (<0.65)
- ✅ Proactive confirmations triggered when confidence < 0.65
- ✅ Confirmation prompt displays reasoning, confidence score, alternatives
- ✅ User can choose: "Proceed" (override caution), "Retry" (try alternate), "Exit" (cancel)
- ✅ All confirmations logged to K0 receipts with audit trail
- ✅ Prometheus metrics exported: counts, outcomes, feedback signals
- ✅ Weekly report shows confirmation accuracy and user decision patterns
- ✅ WARD integration tests pass for: 3 confidence tiers, user decisions, audit logging
- ✅ Performance: Confidence calculation <50ms, confirmation display <150ms total
- ✅ Zero user fatigue: <5% false positive rate on confirmations (tuned empirically)

---

## Related ADRs

**Depends On:**
- [ADR-0007](0007-4stage-planning-pipeline.md): 4-Stage Planning Pipeline (confidence thresholds)
- [ADR-0003b](0003b-6-core-protocol-implementations.md): Protocol 3 (Clarification) - base protocol

**Referenced By:**
- (Future) Learning Loop for feedback signal integration

**Related (No dependency):**
- [ADR-0052a](0052a-step-by-step-approval-protocol.md): Step-by-Step Approval (complementary HITL)
- [ADR-0052b](0052b-red-band-approval-two-person-rule.md): RED Band Approval (complementary HITL)
- [ADR-0052c](0052c-nested-clarification-chains-history.md): Nested Clarifications (complementary HITL)

---

## Questions for Review

1. **Confidence Threshold Defaults:** Start with 0.65 (LOW) or 0.75 (stricter)? User feedback welcome.
2. **Alternative Approaches:** Should we always show 3 alternatives, or vary based on action type?
3. **Timeout Behavior:** 3 minutes or configurable per user? Should we auto-proceed on timeout (risky)?
4. **Confidence Factors:** Are 6 factors sufficient, or missing key factors (e.g., "temporal relevance")?
5. **RED Band Interaction:** Proactive confirmation + RED band approval = stacking HITL gates. Too much?

---

## References

- **Whiteboard Section:** L11800-11900+ (Proactive confirmation, confidence thresholds)
- **ADR Creation Plan:** Gap Analysis #2 (Turn-Taking & Flow), #6 (Emotion & Confidence)
- **Research:**
  - Amershi et al. (2019) - "Guidelines for Human-AI Interaction"
  - Ribeiro et al. (2016) - "LIME: Low-Fidelity Interpretable Model Explanations"
  - Taddeo & Floridi (2018) - "How AI can be a force for good"

---

**Next Steps:**
1. ✅ ADR-0052d created and ready for review
2. → Review with safety team & product
3. → Implement Phase 1 (confidence calculation + prompt)
4. → A/B test confidence thresholds with real users
5. → Wire to Learning Loop (ADR-0059) for feedback integration