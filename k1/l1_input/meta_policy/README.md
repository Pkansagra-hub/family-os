# Meta Policy Engine

**Module:** `k1/l1_input/meta_policy/` (Module #56)
**Architecture:** ADR-0004 Amendment #2
**Capabilities:** Social norm modeling, contextual privacy, proactive confirmations
**Status:** 🔴 NEEDS_IMPLEMENTATION (P0 - MVP CRITICAL)

---

## Purpose

Provide social context constraints to LLM behavior, preventing inappropriate responses and adapting privacy dynamically based on environmental awareness.

## Problem

LLMs can generate inappropriate responses without social context:

- ❌ Suggest loud music at midnight
- ❌ Book $500 concert tickets without confirmation
- ❌ Read personal emails aloud when visitors present
- ❌ Execute high-cost actions without user approval

Meta Policy provides social norms and contextual rules to constrain LLM behavior.

## Components

### 1. Norm Modeler (`norm_modeler.py`)

**Responsibilities:**

- Model family norms (time-based, cost-based, privacy-based, safety-based)
- Learn norms from user corrections
- Enforce norm constraints on LLM outputs
- <1ms norm check latency

**Norm Categories:**

**Time-Based:**

- Quiet hours (22:00-07:00): No loud music, reduce TTS volume 50%
- Naptime detection: Ambient sensors (dark room, no motion) → audio-only mode

**Cost-Based:**

- High-cost threshold ($100+): Require confirmation
- Daily spend limit ($500): Block transaction, notify user

**Privacy-Based:**

- Visitors present (unknown voices/faces): Upgrade GREEN → AMBER band
- No personal information in responses when others present

**Safety-Based:**

- Emergency override: Fire alarm, medical emergency → bypass all norms

### 2. Dynamic Privacy Adjuster (`dynamic_privacy_adjuster.py`)

**Responsibilities:**

- Adjust privacy band based on ambient context
- GREEN → AMBER: Visitors detected
- AMBER → RED: Sensitive context (others present + sensitive topic)
- RED → AMBER: Visitors leave, return to baseline

**Triggers:**
- Ambient sensors (unknown voices, faces)
- Time-based rules (visitors expected at dinner time)
- User explicit override ("Privacy mode on")

### 3. Proactive Confirmation (`proactive_confirmation.py`)

**Responsibilities:**
- Detect actions requiring confirmation
- Agent-initiated prompts (not user-initiated)
- Track user acceptance rate
- Adapt confirmation frequency

**Confirmation Triggers:**
- High-cost actions ($100+)
- Privacy-sensitive actions (share personal data)
- Time-inappropriate actions (loud music at midnight)
- Irreversible actions (delete all emails)

**HITL Workflow:**
```
LLM: "Book $500 concert tickets"
Meta Policy: HIGH_COST_THRESHOLD → Trigger confirmation
System: "This costs $500. Confirm?"
User: "Yes" or "No"
```

## Integration

**Upstream (Layer 1 Inputs):**

- `k1/l1_input/streams/operators/ambient_sensor_fusion.py` ← room occupancy
- `k1/l1_input/streams/operators/speaker_diarization.py` ← visitor detection
- `k1/l2_orchestration/planner/` ← receives LLM action proposals

**Downstream (Layer 2 Orchestration):**

- `k1/l2_orchestration/planner/` ← validation gate for action plans
- `SessionState` ← stores active norms, privacy band adjustments

**Cross-Layer:**

- Event Bus (L5) ← publishes `NormViolation`, `PrivacyAdjustment` events
- Observability (L5) ← metrics + tracing

## Performance Budgets

| Component | Budget | Measurement |
|-----------|--------|-------------|
| Norm check | <1ms | `norm_modeler.check()` |
| Privacy adjustment | <5ms | `privacy_adjuster.adjust_band()` |
| Confirmation trigger | <1ms | `confirmation.check_trigger()` |
| **Total P95** | **<5ms** | End-to-end policy check |

## Observability

**Metrics:**

- `meta_policy_norm_violations_total{norm_type}`
- `meta_policy_confirmations_required_total{trigger}`
- `meta_policy_privacy_adjustments_total{from_band, to_band}`
- `meta_policy_user_acceptance_rate{confirmation_type}`

**Tracing:**

- Span: `meta_policy.check_norms`
- Attributes: `norm_type`, `violation`, `action`

## Research Foundation

- **Context-Aware Computing:** Dey (2001) - Contextual adaptation
- **Social Robotics:** Fong et al. (2003) - Norm learning from human feedback
- **Privacy-Preserving AI:** Abadi et al. (2016) - Differential privacy
- **Human-in-the-Loop AI:** Holzinger (2016) - HITL confirmation patterns

## Related ADRs

- **ADR-0004:** 56-Module Architecture (Amendment #2 - Module #56)
- **ADR-0001f:** SessionState Management (stores active norms)
- **ADR-0004a:** Event Bus Communication (`NormViolation`, `PrivacyAdjustment` events)

## Implementation Plan

**Phase 1: Norm Modeling (Week 1)**
- Implement `NormModeler` (4 norm categories)
- Norm database (YAML config)
- Unit tests for norm checks

**Phase 2: Privacy Adjustment (Week 1-2)**
- Implement `DynamicPrivacyAdjuster` (band transitions)
- Ambient sensor integration
- Privacy transition logic

**Phase 3: Proactive Confirmation (Week 2)**
- Implement `ProactiveConfirmation` (triggers)
- HITL workflow
- User acceptance tracking

**Phase 4: Integration & Learning (Week 2-3)**
- Integrate with Planner (action validation)
- Norm learning from corrections
- End-to-end integration tests

## Examples

**Example 1: Time-Based Norm**
```python
# 23:00 - User asks "Play loud music"
action = Action(type="PLAY_MUSIC", volume=0.9, time="23:00")
violation = norm_modeler.check(action)
# violation.norm = QUIET_HOURS
# violation.message = "It's 11pm (quiet hours). Play at 50% volume?"
```

**Example 2: Cost-Based Confirmation**
```python
# User: "Book concert tickets"
action = Action(type="PURCHASE", amount_usd=500)
trigger = confirmation.check_trigger(action)
# trigger.type = HIGH_COST_THRESHOLD
# trigger.message = "This costs $500. Confirm?"
```

**Example 3: Privacy Adjustment**
```python
# Ambient sensors detect unknown voice
context = AmbientContext(room_occupancy=3, known_speakers=2, unknown_speakers=1)
adjustment = privacy_adjuster.adjust(context)
# adjustment.from_band = GREEN
# adjustment.to_band = AMBER
# adjustment.reason = "VISITOR_DETECTED"
```

## Status

🔴 **NEEDS_IMPLEMENTATION** (P0 - MVP CRITICAL)

**Timeline:** 2-3 weeks implementation + 1 week testing

**Blockers:**

- Ambient sensor fusion (Module #54) - prerequisite
- Speaker diarization (Module #55) - prerequisite

**Next Steps:**

1. Implement `norm_modeler.py` (4 norm categories)
2. Implement `dynamic_privacy_adjuster.py` (band transitions)
3. Implement `proactive_confirmation.py` (HITL workflow)
4. Write WARD integration tests
5. Integrate with Planner (action validation gate)
