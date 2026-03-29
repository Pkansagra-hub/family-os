# Learning Loop Architecture -- Implementation Reference

> **Status**: ARCHITECTURE COMPLETE -- Implementation Deferred
> **Location**: `k1/learning/`
> **Diagram**: `k1/learning/learning.mmd`
> **Last Updated**: 2026-02-06
> **Author**: K1 Architecture Team

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Two-System Architecture](#2-two-system-architecture)
3. [System 1: Gap Resolution (Active Learning)](#3-system-1-gap-resolution)
4. [System 2: Model Refinement (Feedback Loop)](#4-system-2-model-refinement)
5. [Memory Writer Subsystem](#5-memory-writer-subsystem)
6. [Agent Inventory](#6-agent-inventory)
7. [Storage Tables](#7-storage-tables)
8. [Event Bus Topics](#8-event-bus-topics)
9. [Integration Points with Existing K1 Systems](#9-integration-points)
10. [Invariants](#10-invariants)
11. [Performance Budget](#11-performance-budget)
12. [Implementation Phasing](#12-implementation-phasing)
13. [Source Documents](#13-source-documents)

---

## 1. Executive Summary

The Learning Loop is K1's intelligence refinement layer. It is NOT a single monolithic system -- it is **two clearly separated systems** that share storage but have completely different data flows:

- **System 1 (Gap Resolution)**: K0 detects a knowledge gap, asks K1 to formulate a question, user answers, answer flows back to K0. CIRCULAR flow.
- **System 2 (Model Refinement)**: K1 detects behavioral signals during conversation, packages them as feedback, sends to K0 for pipeline parameter tuning. ONE-WAY flow.

Both systems are architecturally supported from day 1 -- SSE transport, Bridge ports, event bus topics, agent contracts -- so implementation can proceed incrementally without structural changes.

---

## 2. Two-System Architecture

```
+==============================================================================+
|                     LEARNING LOOP -- TWO-SYSTEM OVERVIEW                      |
+==============================================================================+
|                                                                              |
|  SYSTEM 1: GAP RESOLUTION (Active Learning)                                 |
|  Direction: K0 -> Bridge SSE -> K1 -> User -> K0 (circular)                |
|                                                                              |
|  +--------+    +--------+    +--------+    SSE     +------------------+     |
|  |  P03   |--->|  P06   |--->|  P05   |---------->| K1 SSE Listener  |     |
|  | Consol.|    | Learn  |    | Attend |   Bridge   | Event Router     |     |
|  | Gap Det|    | Entropy|    | Budget |            +--------+---------+     |
|  +--------+    +--------+    +--------+                     |               |
|       ^                                                     v               |
|       |                                          +------------------+       |
|       |                                          | Proactive Decide |       |
|       |                                          | Attention Budget |       |
|       |                                          | Context Monitor  |       |
|       |                                          +--------+---------+       |
|       |                                                   |                 |
|       |                                                   v                 |
|       |                                          +------------------+       |
|       |                                          | Curiosity Agent  |       |
|       |                                          | Constitution Flt |       |
|       |                                          | Question Format  |       |
|       |                                          +--------+---------+       |
|       |                                                   |                 |
|       |                                                   v                 |
|       |                                          +------------------+       |
|       |                                          | Concierge        |       |
|       |                                          | OUTPUT_CHANNEL   |       |
|       |                                          | Delivers to User |       |
|       |                                          +--------+---------+       |
|       |                                                   |                 |
|       |                                           User answers              |
|       |                                                   |                 |
|       |                                                   v                 |
|       |    +--------+    +------------------+    +------------------+       |
|       +<---|  P02   |<---|  Bridge Cmd Port |<---| Gap Answer Writer|       |
|            | Write  |    | /k0/command.submit|    | memory.delta     |       |
|            +--------+    +------------------+    | + gap_id         |       |
|                                                  +------------------+       |
|                                                                              |
+==============================================================================+
|                                                                              |
|  SYSTEM 2: MODEL REFINEMENT (Feedback Loop)                                 |
|  Direction: K1 -> Bridge Obs Port -> K0 (one-way)                          |
|                                                                              |
|  +------------------+    +------------------+    +------------------+       |
|  | K1 Conversation  |--->| Signal Detectors |    | Feedback Envelope|       |
|  | Context Tracker  |    | Correction  0.85 |--->| Builder          |       |
|  | session_id       |    | Validation  0.90 |    | feedback_id      |       |
|  | event_ids[]      |    | Reformulate 0.65 |    | pipeline_id      |       |
|  | recall_id        |    | Abandonment 0.70 |    | signal_class     |       |
|  | grounded_ids[]   |    | Hedging     0.50 |    | correlation{}    |       |
|  +------------------+    +------------------+    +--------+---------+       |
|                                                           |                 |
|                                                           v                 |
|                                                  +------------------+       |
|                                                  | Feedback Emitter |       |
|                                                  | POST /k0/obs.emit|       |
|                                                  | kind=feedback    |       |
|                                                  +--------+---------+       |
|                                                           |                 |
|                                            Bridge Obs Port|                 |
|                                                           v                 |
|  +--------+    +--------+    +--------+    +------------------+            |
|  |  P02   |    |  P03   |    |  P08   |<---| K0 observe.py    |            |
|  | Feedbk |    | Feedbk |    | Feedbk |    | FeedbackRegistry |            |
|  | Handler|    | Handler|    | Handler|    | st_feedback_sigs |            |
|  +--------+    +--------+    +--------+    | BusDispatcher    |            |
|                                            +------------------+            |
|                                                                              |
+==============================================================================+
```

### Side-by-Side Comparison

| Dimension              | System 1: Gap Resolution              | System 2: Model Refinement           |
|------------------------|---------------------------------------|--------------------------------------|
| **Direction**          | K0 -> SSE -> K1 -> User -> K0 (loop) | K1 -> Obs Port -> K0 (one-way)       |
| **Trigger**            | K0 detects knowledge gap              | K1 detects behavioral signal         |
| **Goal**               | Get missing info from user            | Tune pipeline parameters from usage  |
| **K0 Pipelines**       | P03, P06, P05, P02                    | P21, P02, P03, P08                   |
| **K1 Agents**          | CuriosityAgent, ReminderAgent, GapAnswerWriter | FeedbackCollector, DriftDetector |
| **User Involvement**   | YES (answers questions)               | NO (implicit/automatic)              |
| **Storage**            | st_learning_queue, st_anchors         | st_feedback_signals, st_learned_weights |
| **Rate Limit**         | 3 questions/day (Token Bucket)        | 100 signals/min per tenant           |
| **Latency (E2E)**      | < 5s (gap detection to question)      | < 200ms (signal to K0)               |

---

## 3. System 1: Gap Resolution

### 3.1 Full Data Flow

```
STEP 1: K0 Gap Detection (P03 Consolidation)
==============================================

  P03 processes events from st_hipp_events during consolidation cycle.
  During entity resolution (R2-R4) and truth write (R7):

  GapDetector checks for:
  +-----------------------------+-----------------------------------+----------+
  | Gap Type                    | Trigger Condition                 | Priority |
  +-----------------------------+-----------------------------------+----------+
  | AMBIGUOUS_ENTITY            | Multiple candidates, max conf<0.7 | HIGH     |
  | LOW_CONFIDENCE_EDGE         | Relationship confidence < 0.6     | MEDIUM   |
  | MISSING_ATTRIBUTE           | Ontology-required attribute NULL   | MEDIUM   |
  | CONTRADICTION               | Semantic conflict with truth      | HIGH     |
  | CONCEPT_DRIFT               | Anchor conf shifted >20% / 30d   | LOW      |
  | STRUCTURAL_HOLE             | Missing expected KG edge          | LOW      |
  | STALE_ANCHOR                | Anchor not updated 90+ days       | LOW      |
  +-----------------------------+-----------------------------------+----------+

  For each detected gap:
    1. Create GapRecord with entropy_score, confidence_score
    2. Calculate importance_score = entropy * (1 / (confidence + 0.1))
    3. Persist to st_learning_queue (status: PENDING)
    4. Emit p03.gap.detected.v1 to K0 event bus


STEP 2: Implicit Resolution Attempt (GapAutoResolver, P03 R0)
==============================================================

  BEFORE P06 asks a question, every new P02 event runs through GapAutoResolver:

    New NER entities --> Match against pending gaps
                         |
                    Jaccard similarity >= 0.6?
                         |
                +--------+--------+
                |                 |
          conf >= 0.75      conf < 0.75
                |                 |
          Auto-resolve        Gap stays PENDING
          (silent, no Q)      (proceed to P06)

  Grace period: 24 hours before P06 generates explicit question
  Rationale: Give implicit resolution a chance first


STEP 3: P06 Active Learning (Entropy Scanner)
===============================================

  P06 has two input paths:

  Path A: Reactive (from P03 gap emissions)
    p03.gap.detected.v1 --> P06 Priority Queue

  Path B: Proactive (background entropy scanner, daily 4AM cron)
    Scans:
      - Ontology violations (missing required attributes)
      - Stale anchors (not updated 90+ days)
      - Structural holes (co-occurring entities with no edge)
      - Concept drift (anchor confidence shift > 20% in 30 days)
    Results: Additional gap records into st_learning_queue

  P06 filters:
    - Skip gaps with status != PENDING
    - Skip gaps within grace period (< 24h old)
    - Skip implicitly resolved gaps (resolution_type = IMPLICIT)
    - Order by importance_score DESC
    - Top 10 per batch


STEP 4: P05 Attention Manager (Token Bucket)
==============================================

  P05 receives gap-ready signal from P06.

  Attention Budget Gate:
    +-------------------------------------------+
    | Token Bucket Algorithm                    |
    |                                           |
    | tokens: 3/day (max)                       |
    | refill: 1 token per 8 hours               |
    |                                           |
    | can_ask_question(): tokens >= 1.0         |
    | spend_token(): tokens -= 1.0              |
    +-------------------------------------------+

  Context Monitor (0.0 - 1.0 readiness score):
    0.0  User stressed / driving / safety-critical
    0.1  User at work / high cognitive load
    0.3  Default -- possible but not ideal
    0.6  User idle > 5 minutes
    0.9  User discussing related topic (cosine > 0.7)

  Decision matrix:
    tokens >= 1 AND readiness >= 0.6  -->  EMIT SSE curiosity.intent.v1
    tokens >= 1 AND readiness < 0.3   -->  DEFER (re-check later)
    tokens < 1                        -->  SUPPRESS (budget exhausted)


STEP 5: SSE Transport (K0 -> Bridge -> K1)
============================================

  K0 SSE Server emits:
    Topic: curiosity.intent.v1
    Endpoint: /v1/k0/events/stream
    Payload: {
      gap_id, gap_type, priority,
      entity_id, context_json,
      prompt_hints: { suggested_questions[], sensitivity },
      sse_topic: "curiosity.intent.v1"
    }

  Bridge SSE Port:
    IKernelSSEPort -> EventSource stream -> K1 SSE Listener
    Reconnect: exponential backoff on disconnect
    Ack protocol: per-event acknowledgment


STEP 6: K1 Proactive Decision Engine
======================================

  SSE event arrives at K1 SSE Listener.
  SSE Router sends to Proactive Decision Engine.

  Proactive Queue (priority sorted):
    importance = entropy * (1 / (confidence + 0.1)) * recency * type_weight

    Type weights:
      CONTRADICTION: 1.5      (urgent)
      AMBIGUOUS_ENTITY: 1.3   (important for interactions)
      MISSING_ATTRIBUTE: 1.0  (standard)
      LOW_CONFIDENCE_EDGE: 0.9
      CONCEPT_DRIFT: 0.7
      STRUCTURAL_HOLE: 0.6
      STALE_ANCHOR: 0.5       (low urgency)

  Max queue depth: 50
  Expiry: 7 days per gap record


STEP 7: Curiosity Agent (Question Generation)
===============================================

  Spawned by Fabric Agent Factory from curiosity_agent.yaml contract.

  Input: GapRecord { gap_type, entity_id, context_json, prompt_hints }
  Output: Natural language question (max 15 words, ~300 tokens)

  Strategy by gap_type:
    AMBIGUOUS_ENTITY   -> "Quick check: Is Sarah from work, or a friend?"
    MISSING_ATTRIBUTE  -> "What is Dad's birthday?"
    CONTRADICTION      -> "I thought you liked Thai food -- has that changed?"
    CONCEPT_DRIFT      -> "Still enjoying morning runs, or switched routine?"
    STRUCTURAL_HOLE    -> "How do you know Dr. Smith?"
    STALE_ANCHOR       -> "Still a fan of sci-fi movies?"

  Persona constraints:
    - Curious, humble, brief
    - No "As an AI" preambles
    - Max 15 words
    - Casual and natural tone

  Tools granted: recall_memory (read-only, for context enrichment)


STEP 8: Constitutional AI Filter
==================================

  Every generated question is checked against Family Constitution:

  Question Principles:
    1. Not during high-stress moments
    2. Respect "I don't want to answer" without penalty
    3. Avoid questions that could create family conflict
    4. Question count within budget
    5. Genuine curiosity framing, not judgment

  Privacy Band Enforcement:
    RED (medical, financial, highly personal):
      Requires explicit user consent for RED-band questions
    AMBER (moderate sensitivity):
      Requires general consent
    GREEN (routine):
      Always okay to ask

  Child Safety (age < 13):
    - Parental consent required
    - Age-appropriate language
    - Block: financial, medical, relationship conflicts, trauma

  If violation detected:
    Attempt 1: Revise question to comply
    Attempt 2: Revise again
    Attempt 3: SUPPRESS question entirely (do not ask)


STEP 9: Delivery via Concierge
================================

  Question Formatter wraps into CuriosityOutput envelope:
    { gap_id, gap_type, question_text, trace_id, session_id, priority }

  Emits: k1.learning.question_ready.v1 on K1 Event Bus

  Concierge receives and routes to OUTPUT_CHANNEL:
    - User sees a proactive message (NOT in response to their input)
    - Concierge tracks gap_id in active conversation context
    - Emits: k1.learning.question_delivered.v1


STEP 10: User Answer -> K0
============================

  User responds. Concierge detects answer correlates with active gap_id.
  Routes to Learning Loop via: k1.learning.gap_answer.v1

  Gap Answer Writer (deterministic, NO LLM):
    Builds K0 command envelope:
      op: memory.delta
      body: { user_answer_text }
      meta: { gap_id, gap_type, confidence: 1.0, source: "user_explicit" }

    POST /k0/command.submit via Bridge Command Port

  P02 Write Pipeline:
    Receives command, writes to st_hipp_events
    Tags event with gap_resolution_id

  P03 Next Consolidation Cycle:
    Finds event with gap_resolution_id
    Resolves matching gap in st_learning_queue
    Updates truth layer (KG, anchors)
    Status: PENDING -> RESOLVED


STEP 11: Reminder (if no answer)
==================================

  If gap status = ASKED and no answer after 24h:
    Reminder Agent generates gentle follow-up
    Max 1 reminder per gap
    Respects attention budget (costs 1 token)

  If still no answer after reminder:
    Gap status -> EXPIRED
    No further attempts
```

### 3.2 Bayesian Anchor Points

The Learning Loop maintains Bayesian beliefs about user attributes via Beta distributions:

```
  Anchor: "loves_spicy_food"
  +-----------+----------+------------+-------------------+
  | Day       | alpha    | beta       | Confidence        |
  +-----------+----------+------------+-------------------+
  | 1 (prior) | 1.0      | 1.0        | 0.50 (no data)    |
  | 7         | 4.0      | 1.0        | 0.80 (3 spicy)    |
  | 30        | 11.0     | 3.0        | 0.79 (peaked)     |
  | 90        | 21.0     | 11.0       | 0.66 (revised)    |
  +-----------+----------+------------+-------------------+

  Bayesian Update:
    evidence FOR  -> alpha += weight
    evidence AGAINST -> beta += weight

  Temporal Decay:
    factor = exp(-decay_rate * days_since_update)
    alpha_new = 1.0 + (alpha - 1.0) * factor
    beta_new  = 1.0 + (beta - 1.0) * factor
    Decay starts after 7 days of no observations

  Drift Detection:
    Compare recent_mean vs historical_mean over 30-day windows
    If |shift| > 0.20 -> CONCEPT_DRIFT gap created
    Example: "Stopped eating meat" -> drift detected -> ask user
```

---

## 4. System 2: Model Refinement

### 4.1 Full Data Flow

```
STEP 1: Conversation Context Tracking
=======================================

  Per-session state (cached in K1, NOT in SessionState):

    ConversationContext {
      session_id:          str
      message_id:          str (per turn, uuid)
      event_ids:           list[str]    (from K0 recall)
      recall_id:           str          (K0 query.recall correlation)
      response_id:         str          (LLM response ID)
      grounded_event_ids:  list[str]    (memories used in response)
      wal_positions:       list[int]    (WAL positions for events)
    }

  Updated after every:
    - K0 recall: record_recall(recall_id, event_ids)
    - LLM response: record_response(response_id, grounded_event_ids)
  Cached via set_context(session_id, context)


STEP 2: Signal Detection (inline, per user message)
=====================================================

  Before generating next LLM response, run 5 detectors:

  +------------------------+-------------------+------+----------+
  | Detector               | Patterns          | Conf | Priority |
  +------------------------+-------------------+------+----------+
  | CorrectionDetector     | "no, actually..."  | 0.85 | P0       |
  |                        | "that's wrong..."  |      |          |
  |                        | "I stopped..."     |      |          |
  |                        | "it's not X, Y"    |      |          |
  +------------------------+-------------------+------+----------+
  | ValidationDetector     | "yes", "exactly"   | 0.90 | P0       |
  |                        | "that's right"     | (pos)|          |
  |                        | "no", "I don't     | 0.85 |          |
  |                        |  think so" (neg)   | (neg)|          |
  +------------------------+-------------------+------+----------+
  | ReformulationDetector  | Semantic sim > 0.7 | 0.60 | P2       |
  |                        | + different wording | -    |          |
  |                        | = user retrying    | 0.75 |          |
  +------------------------+-------------------+------+----------+
  | AbandonmentDetector    | No activity 5+ min | 0.70 | P2       |
  |                        | after recall w/o   |      |          |
  |                        | positive signal    |      |          |
  +------------------------+-------------------+------+----------+
  | HedgingDetector        | LLM uncertainty    | 0.50 | P2       |
  |                        | markers in output  |      |          |
  +------------------------+-------------------+------+----------+

  Early exit: if CORRECTION detected, skip other detectors (no double-count)


STEP 3: Feedback Envelope Construction
========================================

  FeedbackEnvelope {
    feedback_id:    uuid
    pipeline_id:    "P02" | "P03" | "P08"
    tenant_id:      from space resolution
    space_id:       from space resolution
    signal_class:   "CORRECTION" | "VALIDATION" | "IMPLICIT" | "EXPLICIT" | "OUTCOME"
    signal_subtype: "user_explicit_correction" | "reformulation_detected" | ...

    correlation: {
      session_id:          from ConversationContext
      message_id:          from ConversationContext
      wal_positions:       from ConversationContext
      event_ids:           list (deduplicated)
      recall_id:           from ConversationContext
      response_id:         from ConversationContext
      target_entity_type:  "event"
      target_entity_id:    grounded_event_ids[0]
    }

    provenance: {
      source_message_id:     message_id
      recall_context_hash:   SHA-256 of {event_ids, grounded_event_ids}
      feedback_timestamp:    ISO-8601
    }

    payload: pipeline-specific (Pydantic schema per pipeline)
  }


STEP 4: Emit to K0 via Bridge Obs Port
========================================

  POST /k0/obs.emit
  Body: { kind: "feedback", body: <FeedbackEnvelope> }

  K0 observe.py:
    1. Validates via FeedbackSchemaRegistry (per-pipeline Pydantic)
    2. Dedup: payload_hash within 5s -> ignored
    3. Rate limit: 100 signals/min per tenant
    4. Persists to st_feedback_signals (JSONB)
    5. BusDispatcher publishes to feedback.signal.<pipeline>.v1

  Downstream handlers:
    feedback.signal.p02.v1 -> P02FeedbackHandler
      CORRECTION: update entity, mark corrected
      VALIDATION: boost/reduce salience
      IMPLICIT: reduce salience proportional to confidence

    feedback.signal.p08.v1 -> P08FeedbackHandler
      retrieval_hit/miss: adjust embedding weights
      user_relevance: relevant/irrelevant/partial

    feedback.signal.p03.v1 -> P03FeedbackHandler (future)
      AdaptiveParameter (Thompson Sampling) for:
        similarity_threshold, decay_lambda, salience_boost


STEP 5: Adaptive Parameters (Thompson Sampling)
=================================================

  Each tunable pipeline parameter modeled as Beta distribution:

    AdaptiveParameter {
      name: str
      alpha: float = 1.0    (successes)
      beta: float = 1.0     (failures)
      min_value, max_value: float
    }

    sample():  np.random.beta(alpha, beta) -> scale to [min, max]
    update(success: bool):  alpha += 1 or beta += 1

  Pipeline uses sampled values at runtime -> parameters self-tune
  over time based on feedback quality signals.
```

### 4.2 Drift Detection

```
  Drift Detector runs as background process:

  Checks (rolling 30-day window):
    1. Embedding retrieval relevance decay
       - retrieval_hit rate dropping across sessions
    2. User correction rate increase
       - > 2 corrections per 10 recalls = spike
    3. Abandonment rate spike
       - > 3 abandonments per session = anomaly

  On drift detected:
    -> Emit k1.learning.drift_alert.v1 (K1 internal)
    -> Advisory Emitter sends k0.learning.advisory.v1 via Bridge Obs Port

  Advisory types:
    EMBEDDING_DECAY:    P08 reindex needed
    CORRECTION_SPIKE:   P02 review needed
    CONFIDENCE_DRIFT:   P03 re-consolidate
```

---

## 5. Memory Writer Subsystem

```
  Spans both systems. Observes LLM conversations, extracts storable facts.

  +-------------------+     +-------------------+     +-----------------+
  | Concierge LLM     |---->| Memory Writer     |---->| Delta Aggregator|
  | conversation      |     | Agent             |     | 250ms batch     |
  | stream            |     | (LLM, 500 tok)    |     | dedup + merge   |
  +-------------------+     +-------------------+     +--------+--------+
                                                               |
                                                               v
  +-------------------+     +-------------------+     +-----------------+
  | K0 st_hipp_events |<----| Bridge Cmd Port   |<----| State Delta     |
  |                   |     | /k0/command.submit |     | Emitter         |
  +-------------------+     +-------------------+     +-----------------+

  Memory Writer Agent:
    - Spawned by Fabric Agent Factory per session
    - Template: k1/contracts/agents/memory_writer.yaml
    - Observes: LLM conversation stream from Concierge
    - Extracts: facts, entities, relationships, preferences
    - Outputs: memory.delta operations
    - Budget: 500 tokens per extraction

  Learning Extractor Agent:
    - Extracts meta-knowledge: question styles that work, user response
      length preferences, topic sensitivity patterns
    - Output: learning.signal payloads -> feeds System 2 advisory path
    - Budget: 400 tokens

  Delta Aggregator:
    - 250ms time-window batching
    - Deduplicates overlapping deltas
    - Merges compatible operations
    - Orders by event_id (causal ordering)

  State Delta Emitter:
    - Sends batched command to K0 via Bridge Command Port
    - Single POST per batch (reduces Bridge overhead)
```

---

## 6. Agent Inventory

All agents are spawned by Fabric Agent Factory and registered in the Agent Registry.

| Agent                 | System | LLM? | Tools Granted                      | Token Budget | Latency     |
|-----------------------|--------|------|------------------------------------|-------------|-------------|
| CuriosityAgent        | 1      | YES  | recall_memory                      | 300         | 1-3s        |
| ReminderAgent         | 1      | YES  | recall_memory, invoke_capability   | 200         | 1-2s        |
| GapAnswerWriter       | 1      | NO   | memory.delta (Bridge Cmd Port)     | 0           | < 200ms     |
| FeedbackCollector     | 2      | NO   | feedback.signal (Bridge Obs Port)  | 0           | < 50ms      |
| MemoryWriterAgent     | Both   | YES  | memory.delta (Bridge Cmd Port)     | 500         | 1-3s        |
| LearningExtractor     | Both   | YES  | recall_memory                      | 400         | 1-3s        |
| DriftDetector         | 2      | NO   | none (pure computation)            | 0           | < 30s/1K    |

All contracts stored at `k1/contracts/agents/`:
- `curiosity_agent.yaml`
- `reminder_agent.yaml`
- `memory_writer.yaml`
- `learning_extractor.yaml`
- `gap_answer_writer.yaml`

---

## 7. Storage Tables

All K0-side tables. K1 writes via Bridge ports, never directly.

### 7.1 st_learning_queue (Gap Queue)

Written by P03 R8 (gap detection) and P06 (entropy scanner).

| Column                | Type    | Description                                           |
|-----------------------|---------|-------------------------------------------------------|
| id                    | TEXT PK | ULID for gap record                                   |
| tenant_id, space_id   | TEXT    | Isolation keys                                        |
| gap_type              | TEXT    | AMBIGUOUS_ENTITY, CONTRADICTION, etc. (7 types)       |
| entity_id             | TEXT    | Related entity (if applicable)                        |
| related_event_id      | TEXT    | Source event FK                                       |
| confidence_score      | REAL    | [0-1] current confidence                              |
| entropy_score         | REAL    | [0-1] uncertainty level                               |
| importance_score      | REAL    | GENERATED: entropy * (1 / (confidence + 0.1))         |
| context_json          | TEXT    | Rich context for question generation                  |
| status                | TEXT    | PENDING, READY, ASKED, ANSWERED, RESOLVED, EXPIRED... |
| resolution_type       | TEXT    | USER_ANSWER, IMPLICIT, INFERRED, EXPIRED, DISMISSED   |
| resolution_data_json  | TEXT    | Answer or inference result                            |
| attempts              | INT     | How many times asked (max 3)                          |
| created_at, expires_at| INT     | Timing (7-day expiry default)                         |

### 7.2 st_anchors (Bayesian Beliefs)

Written by P03 during consolidation, P06 entropy scanner.

| Column              | Type    | Description                              |
|---------------------|---------|------------------------------------------|
| entity_id           | TEXT    | Person ID this anchor belongs to         |
| attribute           | TEXT    | e.g., "loves_spicy_food"                 |
| tenant_id           | TEXT    | Isolation key                            |
| alpha               | REAL    | Beta dist: evidence FOR (default 1.0)    |
| beta                | REAL    | Beta dist: evidence AGAINST (default 1.0)|
| confidence          | REAL    | GENERATED: alpha / (alpha + beta)        |
| uncertainty         | REAL    | GENERATED: 1 / (1 + alpha + beta)        |
| observation_count   | INT     | Total evidence observations              |
| decay_rate          | REAL    | Forgetting factor (default 0.05/month)   |
| drift_detected      | BOOL    | Concept drift flag                       |
| status              | TEXT    | ACTIVE, DRIFTING, STALE, ARCHIVED        |

PK: (entity_id, attribute, tenant_id)

### 7.3 st_anchor_observations (Evidence Log)

Audit trail for anchor updates.

| Column              | Type    | Description                              |
|---------------------|---------|------------------------------------------|
| id                  | TEXT PK | Observation ID                           |
| entity_id           | TEXT    | Anchor reference                         |
| attribute           | TEXT    | Anchor reference                         |
| observed_at         | INT     | Timestamp                                |
| event_id            | TEXT    | Source event FK                          |
| supports_anchor     | BOOL    | TRUE = evidence FOR, FALSE = AGAINST     |
| observation_weight  | REAL    | Weight (0-1)                             |

### 7.4 st_feedback_signals

Written by K0 observe.py from K1 feedback envelopes.

| Column              | Type        | Description                              |
|---------------------|-------------|------------------------------------------|
| id                  | UUID PK     | Auto-generated                           |
| feedback_id         | TEXT UNIQUE | From K1 envelope                         |
| pipeline_id         | TEXT        | P02, P03, P08                            |
| signal_class        | TEXT        | CORRECTION, VALIDATION, IMPLICIT, etc.   |
| signal_subtype      | TEXT        | Specific signal type                     |
| correlation         | JSONB       | session_id, event_ids, target, etc.      |
| provenance          | JSONB       | audit trail                              |
| payload             | JSONB       | Pipeline-specific                        |
| payload_hash        | TEXT        | SHA-256 for dedup                        |
| processing_status   | TEXT        | pending, processing, completed, failed   |

---

## 8. Event Bus Topics

### 8.1 SSE Events (K0 -> Bridge -> K1)

| Topic                              | Producer     | Consumer              |
|------------------------------------|--------------|-----------------------|
| curiosity.intent.v1                | P05/P06      | SSE Inbound Handler   |
| k0.learning.advisory.v1            | P06          | Drift Detector        |
| k0.proactive.signal.v1             | P05          | Proactive Decision    |
| curiosity.intent.visual.v1         | Multimodal   | Visual Handler (future)|
| curiosity.intent.counterfactual.v1 | Causal       | Socratic Coach (future)|
| curiosity.intent.values.v1         | CRDT Sync    | Family Mediator (future)|

### 8.2 K1 Internal Events

| Topic                              | Producer              | Consumer                |
|------------------------------------|-----------------------|-------------------------|
| k1.learning.gap_received.v1        | SSE Inbound Handler   | Proactive Decision      |
| k1.learning.question_ready.v1      | Question Formatter    | Concierge OUTPUT_CHANNEL|
| k1.learning.question_delivered.v1  | Concierge             | Reminder Agent          |
| k1.learning.gap_answer.v1          | Concierge (answer det)| Gap Answer Writer       |
| k1.learning.gap_resolved.v1        | Gap Answer Writer     | Metrics                 |
| k1.learning.feedback_detected.v1   | Signal Detectors      | Metrics                 |
| k1.learning.feedback_emitted.v1    | Feedback Emitter      | Metrics                 |
| k1.learning.drift_alert.v1         | Drift Detector        | Advisory Emitter        |
| k1.learning.memory_batch.v1        | State Delta Emitter   | Metrics                 |

### 8.3 K0 Feedback Bus Topics (downstream of K1 emission)

| Topic                    | Handler              | Action                      |
|--------------------------|----------------------|-----------------------------|
| feedback.signal.p02.v1   | P02FeedbackHandler   | Correct, validate, adjust   |
| feedback.signal.p03.v1   | P03FeedbackHandler   | Thompson Sampling tune      |
| feedback.signal.p08.v1   | P08FeedbackHandler   | Embedding weight adjustment |

---

## 9. Integration Points

### 9.1 Concierge (concierge.mmd)

```
  REQUIRED ADDITIONS when implementing Learning Loop:

  1. OUTPUT_CHANNEL: Accept k1.learning.question_ready.v1
     Route proactive question to user (not in response to user input)
     Track active gap_id in conversation context

  2. ANSWER_DETECTION: When user responds and active gap_id exists,
     route to k1.learning.gap_answer.v1 instead of normal processing

  3. ACKING_CORE: UltraBERT can detect reformulation patterns
     Feed to ReformulationDetector for System 2 feedback

  Integration is event-based: no structural changes to Concierge FSM
```

### 9.2 Fabric (fabric.mmd)

```
  REQUIRED ADDITIONS when implementing Learning Loop:

  1. Agent Registry: Register 5 new agent contracts
     (curiosity, reminder, memory_writer, learning_extractor, gap_answer_writer)

  2. Agent Factory: Spawn Learning Loop agents on demand
     CuriosityAgent: on SSE trigger
     MemoryWriterAgent: per session
     Others: on specific triggers

  3. Agent Lifecycle FSM: Standard PENDING->ACTIVE->TERMINATED
     No special states needed for Learning Loop agents

  Integration: standard Fabric contract registration, no structural changes
```

### 9.3 Orchestrator (orchestrator.mmd)

```
  NOT DIRECTLY INVOLVED in Learning Loop flows.

  Proactive questions bypass Orchestrator entirely:
    SSE -> Proactive Decision -> Curiosity Agent -> Concierge

  MINOR ADDITION: Execution Monitor can emit OUTCOME feedback signals
  for capability execution results (System 2 input)
```

### 9.4 Bridge (bridge_architecture.mmd)

```
  ALREADY SUPPORTS Learning Loop:

  1. SSE Port: curiosity.intent.v1, k0.learning.advisory.v1, k0.proactive.signal.v1
  2. Command Port: memory.delta (for gap answers + memory writer)
  3. Obs Port: kind=feedback (for FeedbackEnvelope)

  No changes needed to Bridge architecture
```

### 9.5 SessionState

```
  MULTI-READER ONLY from Learning Loop perspective.

  Reads:
    - conversation_context: for feedback correlation IDs
    - affective_now: for context readiness assessment
    - user_state signals: for attention budget decisions

  NEVER writes (LEARN-01, ADR-0017 Single Writer = Concierge only)
```

---

## 10. Invariants

| ID       | Rule                                                                    |
|----------|-------------------------------------------------------------------------|
| LEARN-01 | Learning Loop agents NEVER write SessionState (ADR-0017)                |
| LEARN-02 | All K0 writes via Bridge Command Port (memory.delta, feedback.signal)   |
| LEARN-03 | Attention Budget hard cap: 3 questions/day per user (Token Bucket)      |
| LEARN-04 | Curiosity Agent max 300 tokens per question (15 words target)           |
| LEARN-05 | Constitutional AI filter on EVERY question before delivery              |
| LEARN-06 | Privacy band: RED data questions need explicit user consent             |
| LEARN-07 | GapAutoResolver 24h grace period before explicit ask                    |
| LEARN-08 | Feedback correlation MUST include session_id + event_ids + recall_id    |
| LEARN-09 | Feedback payload_hash dedup (same hash within 5s = ignored)             |
| LEARN-10 | Rate limit: 100 feedback signals/min per tenant                        |
| LEARN-11 | DriftDetector threshold: 20% confidence shift in 30-day window         |
| LEARN-12 | Memory Writer batch window: 250ms                                       |
| LEARN-13 | All events carry cognitive_trace_id                                     |
| LEARN-14 | System 1 SSE requires Bridge SSE Port healthy (CB_SSE fallback)         |

---

## 11. Performance Budget

| Operation                     | Latency Target     | Tokens | Owner            |
|-------------------------------|-------------------|--------|------------------|
| SSE event receive             | < 50ms            | 0      | Bridge SSE Port  |
| Attention budget check        | < 5ms             | 0      | Budget Gate      |
| Context readiness assessment  | < 100ms           | 0      | Context Monitor  |
| Curiosity question generation | 1-3s              | ~300   | Curiosity Agent  |
| Constitutional filter         | 500ms-2s          | ~200   | Constitution     |
| Gap detection (P03-side)      | < 500ms P95       | 0      | K0 P03           |
| Entropy scan (P06-side)       | < 5min / 10K ent  | 0      | K0 P06           |
| Feedback emit to K0           | < 200ms           | 0      | Feedback Emitter |
| Feedback detection (per turn) | < 50ms            | 0      | Detectors        |
| Memory writer batch           | 250ms window      | ~500   | Memory Writer    |
| Drift detection               | < 30s / 1K anchors| 0      | Drift Detector   |
| End-to-end gap-to-question    | < 5s              | ~500   | Composite        |

---

## 12. Implementation Phasing

This system is designed last but needs architectural support from day 1. The integration points (SSE events, Bridge ports, Fabric agent contracts) are all already defined. Implementation can proceed in 4 independent phases:

### Phase 1: Reactive Gap Resolution (4 weeks)

P03 gap detection, st_learning_queue, P05 attention budget, K1 Curiosity Agent, gap answer flow.

**Dependencies**: P03 consolidation, P02 write, Bridge SSE Port, Fabric Agent Factory

### Phase 2: Proactive Entropy Scanning (3 weeks)

P06 background scanner, ontology violations, stale anchors, structural holes, concept drift.

**Dependencies**: Phase 1 complete, st_anchors table

### Phase 3: Feedback Loop (3 weeks)

Signal detectors, FeedbackEnvelope, emit to K0, P02/P08 feedback handlers, adaptive parameters.

**Dependencies**: Bridge Obs Port, K0 observe.py, st_feedback_signals table

### Phase 4: Memory Writers + Drift (2 weeks)

MemoryWriterAgent, LearningExtractorAgent, Delta batching, DriftDetector, Advisory Emitter.

**Dependencies**: Phase 3 complete, Concierge conversation stream

---

## 13. Source Documents

| Document | Path | Relevance |
|----------|------|-----------|
| Active Learning Loop Idea | `docs/architecture/ideas/0001-active-learning-loop.md` | Theory, roadmap, schemas, research citations |
| P03 Dossier v2 Section 5 | `docs/pipelines/P03_consolidation_dossier_v2.md` | Gap detection, entropy scanning, Bayesian anchors, canonical table schemas |
| Feedback Developer Guide | `k0/ports/FEEDBACK.md` | K1 feedback wiring, FeedbackEnvelope, detector code, K0 handler guide |
| Bridge Architecture | `architecture_diagrams/bridge/bridge_architecture.mmd` | SSE events, Obs Port, Command Port, Two-System flow |
| K1 Skeleton | `architecture_diagrams/k1/k1_cognitive_architecture_skeleton.mmd` | PROACTIVE_AGENT_FLOW, LEARNING_LOOP_FRAMEWORK, MEMORY_WRITER_SYSTEM |
| K0 Source of Truth | `architecture_diagrams/k0/k0_source_of_truth_v2.mmd` | K1 Feedback Connections, PORT_OBS, BUS_DISPATCHER routing |
| Learning Loop mmd | `k1/learning/learning.mmd` | Production architecture diagram (this system) |
