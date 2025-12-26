# P21 Feedback Pipeline — Issue Tracker

**Epic**: Pipeline-Agnostic Feedback System
**Plan**: [PLAN-feedback-pipeline-system.md](PLAN-feedback-pipeline-system.md)
**Wiring Guide**: [k0/ports/FEEDBACK.md](../../k0/ports/FEEDBACK.md)
**Status**: PLANNING
**Created**: 2025-12-24

---

## Reality Check

**Current Pipelines**: Only P02 (Write) and P08 (Embeddings) exist.
**Future Pipelines**: When new pipelines are created, refer to [FEEDBACK.md](../../k0/ports/FEEDBACK.md) wiring guide.

---

## Milestone Summary

| Milestone | Title | Issues | Status |
|-----------|-------|--------|--------|
| **M0** | Foundation & Provenance | 5 | 🔵 Not Started |
| **M1** | Core Feedback Infrastructure | 4 | 🔵 Not Started |
| **M2** | Implicit Feedback Signals | 5 | 🔵 Not Started |
| **M3** | Pipeline Integration (P02, P08) | 3 | 🔵 Not Started |
| **M4** | Adaptive Learning Engine | 2 | 🔵 Not Started |
| **M5** | Active Learning Loop Integration | 2 | 🔵 Not Started |

---

## Milestone 0: Foundation & Provenance

### Epic 0.1: Feedback Provenance (NEW - P0)

| Issue | Title | Priority | Assignee | Status |
|-------|-------|----------|----------|--------|
| FEEDBACK-000 | Design FeedbackProvenance model with cryptographic hashing | P0 | — | 🔵 Open |

**Rationale**: Immutable provenance on every feedback signal (source message_id, recall_context, timestamp, user_intent). Prevents feedback loops from contaminating themselves.

**Fields**:
- `source_message_id`: Original message that triggered feedback
- `recall_context_hash`: SHA-256 of memory context at recall time
- `feedback_timestamp`: When feedback was captured (not received)
- `user_intent_snapshot`: Frozen intent at feedback time
- `provenance_chain`: List of prior feedback IDs if correction-of-correction

### Epic 0.2: Feedback Envelope Design

| Issue | Title | Priority | Assignee | Status |
|-------|-------|----------|----------|--------|
| FEEDBACK-001 | Create FeedbackEnvelope Pydantic model | P0 | — | 🔵 Open |
| FEEDBACK-002 | Define signal class taxonomy (OUTCOME, CORRECTION, IMPLICIT, EXPLICIT, VALIDATION) | P0 | — | 🔵 Open |

### Epic 0.3: Feedback Schema Registry

| Issue | Title | Priority | Assignee | Status |
|-------|-------|----------|----------|--------|
| FEEDBACK-003 | Implement FeedbackSchemaRegistry (Pydantic + JSON Schema, permissive mode) | P0 | — | 🔵 Open |
| FEEDBACK-004 | Define feedback schemas for P02 and P08 only | P0 | — | 🔵 Open |

---

## Milestone 1: Core Feedback Infrastructure

### Epic 1.1: Extend Observe Port

| Issue | Title | Priority | Assignee | Status |
|-------|-------|----------|----------|--------|
| FEEDBACK-005 | Add `kind: "feedback"` to ObservabilityPayload in observe.py | P0 | — | 🔵 Open |
| FEEDBACK-006 | Create Alembic migration for st_feedback_signals table | P0 | — | 🔵 Open |

### Epic 1.2: Feedback Bus Topics

| Issue | Title | Priority | Assignee | Status |
|-------|-------|----------|----------|--------|
| FEEDBACK-007 | Register feedback.signal.{pipeline_id} bus topics (P02, P08 only) | P1 | — | 🔵 Open |

### Epic 1.3: Safety Guardrails (NEW)

| Issue | Title | Priority | Assignee | Status |
|-------|-------|----------|----------|--------|
| FEEDBACK-008 | Implement feedback rate limiting and anomaly detection | P1 | — | 🔵 Open |

**Rationale**: Feedback can be noisy or malicious. Basic filtering:
- Rate limits per tenant/user (e.g., 100 signals/min)
- Anomaly detection (sudden spike in negative feedback)
- Duplicate signal suppression (same feedback within 5s)

---

## Milestone 2: Implicit Feedback Signals

### Epic 2.1: Session Pattern Detection

| Issue | Title | Priority | Assignee | Status |
|-------|-------|----------|----------|--------|
| FEEDBACK-009 | Implement ReformulationDetector (query rephrasing detection) | P1 | — | 🔵 Open |
| FEEDBACK-010 | Implement AbandonmentDetector (session abandonment detection) | P1 | — | 🔵 Open |
| FEEDBACK-011 | Implement HedgingDetector (LLM uncertainty detection) | P2 | — | 🔵 Open |

### Epic 2.2: User Correction & Validation Detection

| Issue | Title | Priority | Assignee | Status |
|-------|-------|----------|----------|--------|
| FEEDBACK-012 | Implement CorrectionParser (explicit user correction parsing) | P1 | — | 🔵 Open |
| FEEDBACK-013 | Implement MemoryValidationDetector (recall confirm/correct signals) | P1 | — | 🔵 Open |

**Rationale for FEEDBACK-013**: When user recalls a memory and confirms/corrects it (e.g., "Yes, I do yoga on Tuesdays" or "No, I stopped that"), this is gold for truth reconciliation tuning.

---

## Milestone 3: Pipeline Integration (P02, P08 Only)

### Epic 3.1: P02 Write Pipeline Feedback

| Issue | Title | Priority | Assignee | Status |
|-------|-------|----------|----------|--------|
| FEEDBACK-014 | Implement P02FeedbackHandler (ingestion quality signals) | P1 | — | 🔵 Open |

**P02 Feedback Schema** (Draft):
```json
{
  "ingested_envelope_id": "uuid",
  "extraction_quality": "good|partial|poor",
  "user_correction": { "field": "...", "expected": "...", "actual": "..." }
}
```

### Epic 3.2: P08 Embeddings Pipeline Feedback

| Issue | Title | Priority | Assignee | Status |
|-------|-------|----------|----------|--------|
| FEEDBACK-015 | Implement P08FeedbackHandler (embedding quality signals) | P1 | — | 🔵 Open |

**P08 Feedback Schema** (Draft):
```json
{
  "embedding_id": "uuid",
  "retrieval_hit": true,
  "retrieval_rank": 3,
  "user_relevance": "relevant|irrelevant|partial"
}
```

### Epic 3.3: Adaptive Parameter Learning

| Issue | Title | Priority | Assignee | Status |
|-------|-------|----------|----------|--------|
| FEEDBACK-016 | Implement AdaptiveParameter with Thompson Sampling (per-parameter bandits) | P1 | — | 🔵 Open |

**Enhancement**: Separate bandits for each tunable parameter:
- `importance_weight_bandit`
- `emotional_weight_bandit`
- `decay_lambda_bandit`
- `similarity_threshold_bandit`

---

## Milestone 4: Adaptive Learning Engine

### Epic 4.1: Learning Coordinator

| Issue | Title | Priority | Assignee | Status |
|-------|-------|----------|----------|--------|
| FEEDBACK-017 | Enhance LearningCoordinator for cross-pipeline learning | P1 | — | 🔵 Open |
| FEEDBACK-018 | Implement per-parameter Thompson Sampling state persistence | P1 | — | 🔵 Open |

---

## Milestone 5: Active Learning Loop Integration

### Epic 5.1: Curiosity-Feedback Loop

| Issue | Title | Priority | Assignee | Status |
|-------|-------|----------|----------|--------|
| FEEDBACK-019 | Implement CuriosityTracker (question outcome tracking) | P1 | — | 🔵 Open |
| FEEDBACK-020 | Implement gap resolution feedback (closes Active Learning loop) | P1 | — | 🔵 Open |

---

## Status Legend

| Symbol | Meaning |
|--------|---------|
| 🔵 | Open / Not Started |
| 🟡 | In Progress |
| 🟢 | Complete |
| 🔴 | Blocked |
| ⚪ | Cancelled |

---

## Quick Stats

- **Total Issues**: 21
- **P0 (Critical)**: 6
- **P1 (High)**: 12
- **P2 (Medium)**: 3

---

## Dependencies Graph

```
M0 Foundation & Provenance
 │
 ├── FEEDBACK-000 (Provenance) ─────────────┐
 │                                          │
 └── FEEDBACK-001/002/003/004 (Envelope)    │
              │                             │
              ▼                             ▼
M1 Core Infrastructure ◄────────────────────┘
 │
 ├── FEEDBACK-005/006 (Observe Port)
 │
 ├── FEEDBACK-007 (Bus Topics)
 │
 └── FEEDBACK-008 (Safety Guardrails)
              │
              ├──────────────────┐
              ▼                  ▼
M2 Implicit Signals        M3 Pipeline Integration
 │                          │
 ├── FEEDBACK-009-013       ├── FEEDBACK-014 (P02)
 │                          ├── FEEDBACK-015 (P08)
 │                          └── FEEDBACK-016 (Adaptive)
 │                               │
 └───────────┬───────────────────┘
             │
             ▼
        M4 Adaptive Learning Engine
             │
             ├── FEEDBACK-017 (Cross-pipeline)
             └── FEEDBACK-018 (Thompson Sampling persistence)
                  │
                  ▼
        M5 Active Learning Loop Integration
             │
             ├── FEEDBACK-019 (CuriosityTracker)
             └── FEEDBACK-020 (Gap Resolution)
                  │
                  ▼
         Idea-0001 (Active Learning Loop)
```

---

## Future Pipeline Expansion

When new pipelines (P03, P04, ..., P20+) are created:

1. **Read the wiring guide**: [k0/ports/FEEDBACK.md](../../k0/ports/FEEDBACK.md)
2. **Register schema**: Add pipeline-specific schema to FeedbackSchemaRegistry
3. **Subscribe to bus**: Add `feedback.signal.{pipeline_id}` topic
4. **Implement handler**: Create `P{XX}FeedbackHandler`

**Do NOT pre-define schemas for non-existent pipelines.**

---

## Related Documents

- [PLAN-feedback-pipeline-system.md](PLAN-feedback-pipeline-system.md) — Full plan
- [Idea-0001: Active Learning Loop](../architecture/ideas/0001-active-learning-loop.md) — Related idea
- [Feedback Wiring Guide](../../k0/ports/FEEDBACK.md) — How to wire feedback for new pipelines
- [K0 Source of Truth](../../architecture_diagrams/k0/k0_source_of_truth_postgresql.mmd) — Architecture reference
