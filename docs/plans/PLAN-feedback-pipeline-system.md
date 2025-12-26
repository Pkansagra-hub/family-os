# PLAN: Pipeline-Agnostic Feedback System (P21 Feedback)

**Plan ID**: PLAN-FEEDBACK-001
**Status**: DRAFT
**Created**: 2025-12-24
**Authors**: K0 Architecture Team
**Related**: [Idea-0001: Active Learning Loop](../architecture/ideas/0001-active-learning-loop.md)

---

## Executive Summary

Design and implement a **pipeline-agnostic feedback system** for K0 that enables self-learning across all pipelines (P01-P20+). The system follows K0's standard interface pattern: single ingress via the observe port, flexible schema registry, and per-pipeline subscription model.

### Core Principles

1. **Schema Flexibility**: Each pipeline defines its own feedback payload schema — the core envelope is generic
2. **No Bottlenecks**: The system must accommodate unlimited future pipelines without schema changes
3. **Standard Interface**: Uses existing observe port (`/k0/obs.emit`) with new `kind: "feedback"`
4. **Implicit + Explicit**: Captures both explicit user corrections and implicit behavioral signals
5. **Pipeline Sovereignty**: Each pipeline owns its feedback consumption logic

---

## Problem Statement

### Current State

- K0 pipelines (P01-P20) operate with **static, hardcoded parameters**
- No mechanism for pipelines to receive outcome feedback
- System cannot learn from:
  - Query results that didn't help users
  - Memory retrievals that were irrelevant
  - Consolidation decisions that pruned important memories
  - Action recommendations that were rejected
  - Personalization predictions that were wrong

### Desired State

- Every pipeline can receive structured feedback signals
- Pipelines adapt their behavior based on outcomes
- K1 orchestration can send implicit feedback (session patterns, reformulations)
- Users can send explicit corrections
- System continuously improves without manual tuning

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           K1 ORCHESTRATION                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ Curiosity    │  │ Session      │  │ LLM Response │  │ User         │    │
│  │ Agent        │  │ Monitor      │  │ Analyzer     │  │ Corrections  │    │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘    │
│         │                 │                 │                 │             │
│         └────────────┬────┴────────────┬────┴────────────┬────┘             │
│                      │                 │                 │                  │
│                      ▼                 ▼                 ▼                  │
│              ┌───────────────────────────────────────────────┐             │
│              │         FeedbackEnvelope Builder              │             │
│              │  (schema-flexible, pipeline-specific payload) │             │
│              └───────────────────────┬───────────────────────┘             │
└──────────────────────────────────────┼──────────────────────────────────────┘
                                       │
                                       │ POST /k0/obs.emit
                                       │ kind: "feedback"
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           K0 MEMORY KERNEL                                   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    OBSERVE PORT (Layer 1)                            │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────────┐  │   │
│  │  │ kind:       │  │ kind:       │  │ kind: "feedback"            │  │   │
│  │  │ "metrics"   │  │ "logs"      │  │ (NEW)                       │  │   │
│  │  └─────────────┘  └─────────────┘  └──────────────┬──────────────┘  │   │
│  └───────────────────────────────────────────────────┼──────────────────┘   │
│                                                      │                       │
│  ┌───────────────────────────────────────────────────┼──────────────────┐   │
│  │                    FEEDBACK SUBSYSTEM (NEW)       │                  │   │
│  │                                                   ▼                  │   │
│  │  ┌─────────────────────────────────────────────────────────────┐    │   │
│  │  │              Feedback Schema Registry                        │    │   │
│  │  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌───────┐ │    │   │
│  │  │  │ P01     │ │ P02     │ │ P03     │ │ P04     │ │ P...  │ │    │   │
│  │  │  │ schema  │ │ schema  │ │ schema  │ │ schema  │ │ schema│ │    │   │
│  │  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └───────┘ │    │   │
│  │  └─────────────────────────────────────────────────────────────┘    │   │
│  │                                                                      │   │
│  │  ┌─────────────────────────────────────────────────────────────┐    │   │
│  │  │              st_feedback_signals (PostgreSQL)                │    │   │
│  │  │  - Generic envelope columns                                  │    │   │
│  │  │  - JSONB payload (pipeline-specific, schema-validated)       │    │   │
│  │  └─────────────────────────────────────────────────────────────┘    │   │
│  │                                                                      │   │
│  │  ┌─────────────────────────────────────────────────────────────┐    │   │
│  │  │              BusDispatcher → feedback.signal.*               │    │   │
│  │  └─────────────────────────────────────────────────────────────┘    │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                         PIPELINE CONSUMERS                            │  │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐  │  │
│  │  │  P01   │ │  P02   │ │  P03   │ │  P04   │ │  P06   │ │  P19   │  │  │
│  │  │ ───────│ │ ───────│ │ ───────│ │ ───────│ │ ───────│ │ ───────│  │  │
│  │  │feedback│ │feedback│ │feedback│ │feedback│ │feedback│ │feedback│  │  │
│  │  │.p01.*  │ │.p02.*  │ │.p03.*  │ │.p04.*  │ │.p06.*  │ │.p19.*  │  │  │
│  │  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘ └────────┘  │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Milestones

| Milestone | Title | Duration | Dependencies |
|-----------|-------|----------|--------------|
| **M0** | Foundation & Schema Registry | 1 week | None |
| **M1** | Core Feedback Infrastructure | 2 weeks | M0 |
| **M2** | Implicit Feedback Signals | 2 weeks | M1 |
| **M3** | Pipeline Integration (P01-P06) | 2 weeks | M1 |
| **M4** | Pipeline Integration (P07-P20) | 2 weeks | M3 |
| **M5** | Adaptive Learning Engine | 3 weeks | M3, M4 |
| **M6** | Active Learning Loop Integration | 2 weeks | M5, Idea-0001 |

**Total Duration**: ~14 weeks

---

# Milestone 0: Foundation & Schema Registry

**Goal**: Establish the foundational schema design and registry pattern that allows unlimited pipeline feedback schemas.

## Epic 0.1: Feedback Envelope Design

### Design Principles

The feedback envelope has two parts:

1. **Generic Header**: Common fields for all feedback (routing, tracing, timing)
2. **Pipeline Payload**: Flexible JSONB validated against pipeline-specific schema

```
┌─────────────────────────────────────────────────────────────────┐
│                     FeedbackEnvelope                             │
├─────────────────────────────────────────────────────────────────┤
│  HEADER (Generic - same for all pipelines)                       │
│  ├── envelope_id: UUID                                           │
│  ├── feedback_version: "1.0"                                     │
│  ├── target_pipeline: "P03"                                      │
│  ├── signal_class: "OUTCOME" | "CORRECTION" | "IMPLICIT"        │
│  ├── source: "K1" | "USER" | "SYSTEM"                           │
│  ├── session_id: string                                          │
│  ├── trace_id: string (cognitive_trace_id)                       │
│  ├── correlation_ids: { query_id?, wal_pos?, receipt_id? }       │
│  ├── timestamp: ISO8601                                          │
│  └── priority: 0.0-1.0                                           │
├─────────────────────────────────────────────────────────────────┤
│  PAYLOAD (Pipeline-specific - schema per pipeline)               │
│  └── payload: JSONB (validated against target_pipeline schema)   │
└─────────────────────────────────────────────────────────────────┘
```

### Story 0.1.1: Define FeedbackEnvelope Pydantic Model

**Issue**: `FEEDBACK-001` — Create FeedbackEnvelope base model

```python
# k0/feedback/envelope.py

from pydantic import BaseModel, Field
from typing import Literal, Any
from uuid import UUID
from datetime import datetime

class CorrelationIds(BaseModel):
    """Links feedback to originating K0 operations."""
    query_id: str | None = None
    wal_position: int | None = None
    receipt_id: str | None = None
    event_ids: list[str] = Field(default_factory=list)

class FeedbackEnvelope(BaseModel):
    """
    Pipeline-agnostic feedback envelope.

    The payload field is validated against the schema registered
    for target_pipeline in the FeedbackSchemaRegistry.
    """
    # === Envelope Identity ===
    envelope_id: UUID = Field(default_factory=uuid4)
    feedback_version: str = "1.0"

    # === Routing ===
    target_pipeline: str  # "P01", "P02", ..., "P99"
    signal_class: Literal["OUTCOME", "CORRECTION", "IMPLICIT", "EXPLICIT"]

    # === Source Attribution ===
    source: Literal["K1", "USER", "SYSTEM", "AGENT"]
    source_component: str | None = None  # e.g., "curiosity_agent", "session_monitor"

    # === Tracing ===
    session_id: str
    trace_id: str  # cognitive_trace_id for correlation
    correlation_ids: CorrelationIds = Field(default_factory=CorrelationIds)

    # === Timing ===
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_timestamp: datetime | None = None  # When the original event occurred

    # === Priority ===
    priority: float = Field(ge=0.0, le=1.0, default=0.5)

    # === Payload (Pipeline-Specific) ===
    payload: dict[str, Any]  # Validated against FeedbackSchemaRegistry

    # === Metadata ===
    metadata: dict[str, Any] = Field(default_factory=dict)
```

**Acceptance Criteria**:

- [ ] FeedbackEnvelope model defined with all header fields
- [ ] Correlation IDs support linking to queries, WAL positions, receipts
- [ ] Payload is generic dict, validated separately
- [ ] Model serializes to JSON for bus dispatch

---

### Story 0.1.2: Define Signal Classes

**Issue**: `FEEDBACK-002` — Define signal class taxonomy

| Signal Class | Description | Example |
|--------------|-------------|---------|
| `OUTCOME` | Result of a K0 operation | Query returned empty, consolidation completed |
| `CORRECTION` | User explicitly corrects system | "That's not my sister, that's my colleague" |
| `IMPLICIT` | Behavioral signal from session | Reformulation, abandonment, short dwell time |
| `EXPLICIT` | User provides unsolicited feedback | "This memory is wrong" |

**Acceptance Criteria**:

- [ ] Signal classes documented with examples
- [ ] Each class has defined priority ranges

---

## Epic 0.2: Feedback Schema Registry

### Story 0.2.1: Create FeedbackSchemaRegistry

**Issue**: `FEEDBACK-003` — Implement FeedbackSchemaRegistry

```python
# k0/feedback/schema_registry.py

from typing import Type
from pydantic import BaseModel
from pathlib import Path
import json

class FeedbackSchemaRegistry:
    """
    Registry for pipeline-specific feedback payload schemas.

    Each pipeline registers its own payload schema. When feedback
    arrives, the payload is validated against the registered schema.

    Schemas can be:
    1. Pydantic models (registered programmatically)
    2. JSON Schema files (loaded from k0/feedback/schemas/)
    3. Dynamic schemas (registered at runtime by pipelines)
    """

    _schemas: dict[str, Type[BaseModel] | dict] = {}
    _json_schemas: dict[str, dict] = {}

    @classmethod
    def register(cls, pipeline_id: str, schema: Type[BaseModel]) -> None:
        """Register a Pydantic model as the feedback schema for a pipeline."""
        cls._schemas[pipeline_id] = schema

    @classmethod
    def register_json_schema(cls, pipeline_id: str, schema: dict) -> None:
        """Register a JSON Schema for a pipeline (for dynamic schemas)."""
        cls._json_schemas[pipeline_id] = schema

    @classmethod
    def validate(cls, pipeline_id: str, payload: dict) -> tuple[bool, str | None]:
        """Validate payload against registered schema."""
        if pipeline_id in cls._schemas:
            try:
                cls._schemas[pipeline_id].model_validate(payload)
                return True, None
            except Exception as e:
                return False, str(e)
        elif pipeline_id in cls._json_schemas:
            # Use jsonschema for validation
            return cls._validate_json_schema(pipeline_id, payload)
        else:
            # No schema registered — accept any payload (permissive mode)
            return True, None

    @classmethod
    def load_schemas_from_directory(cls, directory: Path) -> None:
        """Load JSON schemas from k0/feedback/schemas/*.json"""
        for schema_file in directory.glob("*.json"):
            pipeline_id = schema_file.stem.upper()  # p03.json → P03
            with open(schema_file) as f:
                cls.register_json_schema(pipeline_id, json.load(f))

    @classmethod
    def get_schema(cls, pipeline_id: str) -> Type[BaseModel] | dict | None:
        """Get the registered schema for a pipeline."""
        return cls._schemas.get(pipeline_id) or cls._json_schemas.get(pipeline_id)

    @classmethod
    def list_registered(cls) -> list[str]:
        """List all pipelines with registered feedback schemas."""
        return list(set(cls._schemas.keys()) | set(cls._json_schemas.keys()))
```

**Acceptance Criteria**:

- [ ] Registry supports both Pydantic models and JSON Schema
- [ ] Validation returns success/failure with error message
- [ ] Unregistered pipelines accepted in permissive mode (no schema = accept all)
- [ ] Schemas loadable from directory at startup

---

### Story 0.2.2: Create Initial Pipeline Schemas

**Issue**: `FEEDBACK-004` — Define feedback schemas for P01-P06

Create schema files in `k0/feedback/schemas/`:

```python
# k0/feedback/schemas/p03_consolidation.py

from pydantic import BaseModel, Field
from typing import Literal

class P03FeedbackPayload(BaseModel):
    """
    Feedback schema for P03 (Consolidation/Salience).

    P03 needs feedback about:
    - Salience scoring accuracy
    - Decay decisions (was forgotten memory needed later?)
    - Cluster quality (were related memories grouped correctly?)
    - Reinforcement outcomes (did strengthened memories get retrieved?)
    """

    feedback_type: Literal[
        "SALIENCE_ADJUSTMENT",    # Adjust importance score
        "DECAY_REVERSAL",         # Memory was needed but decayed
        "CLUSTER_CORRECTION",     # Memories should/shouldn't be grouped
        "REINFORCEMENT_OUTCOME",  # Reinforcement decision feedback
        "NOVELTY_SIGNAL",         # New pattern detected
    ]

    # === Target Identification ===
    wal_positions: list[int] = Field(default_factory=list)
    cluster_id: str | None = None

    # === Adjustments ===
    salience_delta: float | None = None  # -1.0 to +1.0 adjustment
    importance_override: float | None = None  # 0.0 to 1.0 absolute

    # === Outcomes ===
    was_retrieved: bool | None = None
    was_helpful: bool | None = None
    user_confirmed: bool | None = None

    # === Context ===
    retrieval_query: str | None = None
    session_context: dict | None = None


class P01FeedbackPayload(BaseModel):
    """
    Feedback schema for P01 (Ingress/Discovery).

    P01 needs feedback about:
    - Query success/failure rates
    - Retrieval relevance
    - Missing results that should have been found
    """

    feedback_type: Literal[
        "QUERY_OUTCOME",         # Query result feedback
        "MISSING_RESULT",        # Expected result not found
        "IRRELEVANT_RESULT",     # Retrieved but not useful
        "RANKING_ADJUSTMENT",    # Result order feedback
    ]

    query_id: str
    query_text: str | None = None

    # Results feedback
    result_count: int | None = None
    relevant_count: int | None = None
    expected_wal_positions: list[int] = Field(default_factory=list)
    irrelevant_wal_positions: list[int] = Field(default_factory=list)

    # Ranking
    expected_top_k: list[int] = Field(default_factory=list)


class P02FeedbackPayload(BaseModel):
    """
    Feedback schema for P02 (Write/Ingest).

    P02 needs feedback about:
    - Memory formation quality
    - Entity extraction accuracy
    - Categorization correctness
    """

    feedback_type: Literal[
        "ENTITY_CORRECTION",     # Entity was misidentified
        "CATEGORY_CORRECTION",   # Wrong category assigned
        "DUPLICATE_DETECTION",   # Was/wasn't a duplicate
        "IMPORTANCE_OVERRIDE",   # User marks as important/unimportant
    ]

    wal_position: int

    # Entity corrections
    extracted_entities: list[str] | None = None
    correct_entities: list[str] | None = None

    # Category corrections
    assigned_category: str | None = None
    correct_category: str | None = None

    # Importance
    user_importance: Literal["HIGH", "MEDIUM", "LOW", "ARCHIVE"] | None = None


class P04FeedbackPayload(BaseModel):
    """
    Feedback schema for P04 (Action/Arbitration).

    P04 needs feedback about:
    - Action recommendation acceptance/rejection
    - Action outcome success/failure
    - User preference for action types
    """

    feedback_type: Literal[
        "ACTION_ACCEPTED",       # User accepted recommendation
        "ACTION_REJECTED",       # User rejected recommendation
        "ACTION_OUTCOME",        # Result of executed action
        "ACTION_PREFERENCE",     # User prefers different action style
    ]

    action_id: str
    action_type: str | None = None

    # Acceptance
    was_accepted: bool | None = None
    rejection_reason: str | None = None

    # Outcome
    outcome_success: bool | None = None
    outcome_description: str | None = None

    # Preference
    preferred_action_style: str | None = None


class P06FeedbackPayload(BaseModel):
    """
    Feedback schema for P06 (Learning/Neuromodulation).

    P06 is the meta-learning pipeline — it receives feedback about
    how well the learning system itself is performing.
    """

    feedback_type: Literal[
        "LEARNING_RATE_ADJUSTMENT",  # Learning too fast/slow
        "STRATEGY_EFFECTIVENESS",    # Learning strategy feedback
        "ANCHOR_DRIFT_SIGNAL",       # User preference changed
        "CURIOSITY_CALIBRATION",     # Question quality feedback
    ]

    # Learning parameters
    current_learning_rate: float | None = None
    suggested_learning_rate: float | None = None

    # Strategy
    strategy_id: str | None = None
    strategy_effectiveness: float | None = None  # 0.0 to 1.0

    # Anchors
    anchor_attribute: str | None = None
    anchor_confidence_delta: float | None = None

    # Curiosity (for Active Learning Loop)
    question_id: str | None = None
    question_was_helpful: bool | None = None
    question_was_answered: bool | None = None
    question_timing_appropriate: bool | None = None
```

**Acceptance Criteria**:

- [ ] P01-P06 feedback schemas defined
- [ ] Each schema has typed feedback_type discriminator
- [ ] Schemas allow optional fields for flexibility
- [ ] Schemas registered in FeedbackSchemaRegistry at boot

---

# Milestone 1: Core Feedback Infrastructure

**Goal**: Implement the feedback ingestion path through the observe port.

## Epic 1.1: Extend Observe Port

### Story 1.1.1: Add `kind: "feedback"` to ObservabilityPayload

**Issue**: `FEEDBACK-005` — Extend observe.py for feedback ingestion

```python
# k0/ports/observe.py (modification)

class ObservabilityPayload(BaseModel):
    """Extended to support feedback signals."""

    kind: Literal["metrics", "logs", "feedback"]  # ADD "feedback"

    # Existing fields
    envelope_id: str | None = None
    trace_id: str | None = None
    metrics: list[ForwardedMetricsBuffer] | None = None
    logs: list[dict] | None = None

    # NEW: Feedback
    feedback: FeedbackEnvelope | None = None


async def _ingest_feedback_signal(
    payload: ObservabilityPayload,
    ctx: PipelineContext,
) -> None:
    """
    Process incoming feedback signal.

    1. Validate payload against pipeline schema
    2. Persist to st_feedback_signals
    3. Dispatch to bus topic feedback.signal.{pipeline}
    """
    feedback = payload.feedback
    if not feedback:
        return

    # Validate against schema registry
    valid, error = FeedbackSchemaRegistry.validate(
        feedback.target_pipeline,
        feedback.payload
    )
    if not valid:
        logger.warning(
            "Feedback schema validation failed",
            pipeline=feedback.target_pipeline,
            error=error,
        )
        # Still accept but mark as unvalidated
        feedback.metadata["schema_valid"] = False
        feedback.metadata["schema_error"] = error
    else:
        feedback.metadata["schema_valid"] = True

    # Persist
    async with ctx.uow() as uow:
        await uow.execute(
            """
            INSERT INTO st_feedback_signals (
                envelope_id, target_pipeline, signal_class, source,
                session_id, trace_id, correlation_ids, priority,
                payload, metadata, received_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())
            """,
            feedback.envelope_id,
            feedback.target_pipeline,
            feedback.signal_class,
            feedback.source,
            feedback.session_id,
            feedback.trace_id,
            feedback.correlation_ids.model_dump_json(),
            feedback.priority,
            json.dumps(feedback.payload),
            json.dumps(feedback.metadata),
        )
        await uow.commit()

    # Dispatch to bus
    topic = f"feedback.signal.{feedback.target_pipeline.lower()}"
    await ctx.bus.dispatch(
        topic=topic,
        message=BusMessage(
            topic=topic,
            payload=feedback.model_dump(),
            trace_id=feedback.trace_id,
        )
    )

    # Emit telemetry
    ctx.metrics.counter(
        "k0_feedback_signals_received_total",
        labels={"pipeline": feedback.target_pipeline, "signal_class": feedback.signal_class}
    )
```

**Acceptance Criteria**:

- [ ] ObservabilityPayload accepts `kind: "feedback"`
- [ ] Feedback validated against schema registry
- [ ] Invalid schema feedback accepted but marked
- [ ] Feedback persisted to st_feedback_signals
- [ ] Feedback dispatched to pipeline-specific bus topic
- [ ] Metrics emitted for observability

---

### Story 1.1.2: Create st_feedback_signals Table

**Issue**: `FEEDBACK-006` — Create Alembic migration for feedback storage

```python
# k0/db/alembic/versions/xxx_create_st_feedback_signals.py

def upgrade():
    op.execute("""
    CREATE TABLE st_feedback_signals (
        -- Identity
        id              BIGSERIAL PRIMARY KEY,
        envelope_id     UUID NOT NULL UNIQUE,

        -- Routing
        target_pipeline VARCHAR(16) NOT NULL,
        signal_class    VARCHAR(32) NOT NULL,
        source          VARCHAR(32) NOT NULL,

        -- Tracing
        session_id      VARCHAR(64) NOT NULL,
        trace_id        VARCHAR(64) NOT NULL,
        correlation_ids JSONB DEFAULT '{}',

        -- Priority & Timing
        priority        FLOAT DEFAULT 0.5,
        received_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        event_timestamp TIMESTAMPTZ,

        -- Payload (pipeline-specific, schema-flexible)
        payload         JSONB NOT NULL,
        metadata        JSONB DEFAULT '{}',

        -- Processing State
        consumed_at     TIMESTAMPTZ,
        consumed_by     VARCHAR(64),
        processing_result JSONB,

        -- Constraints
        CONSTRAINT valid_priority CHECK (priority >= 0.0 AND priority <= 1.0),
        CONSTRAINT valid_signal_class CHECK (
            signal_class IN ('OUTCOME', 'CORRECTION', 'IMPLICIT', 'EXPLICIT')
        )
    );

    -- Indexes for efficient querying
    CREATE INDEX idx_feedback_pipeline_unconsumed
        ON st_feedback_signals (target_pipeline, received_at)
        WHERE consumed_at IS NULL;

    CREATE INDEX idx_feedback_session
        ON st_feedback_signals (session_id);

    CREATE INDEX idx_feedback_trace
        ON st_feedback_signals (trace_id);

    CREATE INDEX idx_feedback_correlation_wal
        ON st_feedback_signals USING GIN ((correlation_ids->'wal_positions'));

    -- Partitioning by month for scalability
    -- (Can be added in Phase 2)

    COMMENT ON TABLE st_feedback_signals IS
        'Pipeline-agnostic feedback signals with flexible JSONB payloads.
         Each pipeline defines its own payload schema in FeedbackSchemaRegistry.';
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS st_feedback_signals CASCADE;")
```

**Acceptance Criteria**:

- [ ] Table created with Alembic migration
- [ ] Indexes support efficient unconsumed query per pipeline
- [ ] Correlation IDs indexed for linking to WAL positions
- [ ] JSONB payload for flexibility

---

## Epic 1.2: Feedback Bus Topics

### Story 1.2.1: Register Feedback Topics

**Issue**: `FEEDBACK-007` — Register feedback bus topics

```python
# k0/feedback/topics.py

"""
Feedback topic hierarchy:

feedback.signal.*           - All feedback signals
feedback.signal.p01         - P01 (Ingress) feedback
feedback.signal.p02         - P02 (Write) feedback
feedback.signal.p03         - P03 (Consolidation) feedback
...
feedback.signal.p20         - P20 (Procedures) feedback

feedback.consumed.*         - Consumed feedback confirmations
feedback.consumed.p03       - P03 consumed feedback

feedback.aggregate.*        - Aggregated feedback metrics
feedback.aggregate.daily    - Daily feedback summary
"""

FEEDBACK_TOPICS = [
    # Signal topics (one per pipeline)
    *[f"feedback.signal.p{i:02d}" for i in range(1, 21)],

    # Meta topics
    "feedback.signal.*",          # Wildcard subscription
    "feedback.consumed.*",
    "feedback.aggregate.daily",
    "feedback.aggregate.weekly",
]

def get_pipeline_feedback_topic(pipeline_id: str) -> str:
    """Get the feedback topic for a pipeline."""
    return f"feedback.signal.{pipeline_id.lower()}"
```

**Acceptance Criteria**:

- [ ] Topics registered for P01-P20
- [ ] Wildcard topic for global feedback monitoring
- [ ] Topic helper function for pipelines

---

# Milestone 2: Implicit Feedback Signals

**Goal**: Enable K1 to detect and send implicit behavioral feedback.

## Epic 2.1: Session Pattern Detection

### Story 2.1.1: Reformulation Detector

**Issue**: `FEEDBACK-008` — Detect query reformulations as feedback

When a user rephrases a query within the same session, it signals the first query didn't get satisfactory results.

```python
# k1/feedback/reformulation_detector.py

class ReformulationDetector:
    """
    Detects when users rephrase queries within a session.

    Signal: IMPLICIT / P01 (query feedback)
    """

    def __init__(self, similarity_threshold: float = 0.75):
        self.similarity_threshold = similarity_threshold
        self.session_queries: dict[str, list[QueryRecord]] = {}

    async def on_query(self, session_id: str, query: str, results: list) -> FeedbackEnvelope | None:
        """Check if this query is a reformulation of a previous query."""

        if session_id not in self.session_queries:
            self.session_queries[session_id] = []

        history = self.session_queries[session_id]

        for prev in reversed(history[-5:]):  # Check last 5 queries
            similarity = self.compute_similarity(prev.query_text, query)

            if similarity > self.similarity_threshold:
                # This is a reformulation!
                feedback = FeedbackEnvelope(
                    target_pipeline="P01",
                    signal_class="IMPLICIT",
                    source="K1",
                    source_component="reformulation_detector",
                    session_id=session_id,
                    trace_id=current_trace_id(),
                    correlation_ids=CorrelationIds(
                        query_id=prev.query_id,
                    ),
                    payload={
                        "feedback_type": "QUERY_OUTCOME",
                        "query_id": prev.query_id,
                        "query_text": prev.query_text,
                        "result_count": prev.result_count,
                        "relevant_count": 0,  # Implicit: none were relevant
                        "reformulated_as": query,
                    },
                    priority=0.7,
                )

                return feedback

        # Record this query
        history.append(QueryRecord(query_text=query, ...))
        return None
```

**Acceptance Criteria**:

- [ ] Detector tracks queries per session
- [ ] Detects reformulations based on semantic similarity
- [ ] Generates P01 IMPLICIT feedback envelope
- [ ] Configurable similarity threshold

---

### Story 2.1.2: Session Abandonment Detector

**Issue**: `FEEDBACK-009` — Detect session abandonment as feedback

```python
# k1/feedback/abandonment_detector.py

class AbandonmentDetector:
    """
    Detects sessions that end abruptly without resolution.

    Signals:
    - Short session after query = query didn't help
    - Disconnect during response = response was unhelpful
    """

    async def on_session_end(
        self,
        session_id: str,
        duration_seconds: float,
        last_activity: str,  # "query", "response", "action"
        pending_queries: list[str],
    ) -> list[FeedbackEnvelope]:
        """Generate feedback for abandoned session."""

        feedbacks = []

        # Short session after query = query failure
        if duration_seconds < 30 and last_activity == "query" and pending_queries:
            for query_id in pending_queries:
                feedbacks.append(FeedbackEnvelope(
                    target_pipeline="P01",
                    signal_class="IMPLICIT",
                    source="K1",
                    source_component="abandonment_detector",
                    session_id=session_id,
                    trace_id=current_trace_id(),
                    correlation_ids=CorrelationIds(query_id=query_id),
                    payload={
                        "feedback_type": "QUERY_OUTCOME",
                        "query_id": query_id,
                        "relevant_count": 0,
                        "session_duration_seconds": duration_seconds,
                        "abandonment_signal": True,
                    },
                    priority=0.6,
                ))

        return feedbacks
```

---

### Story 2.1.3: LLM Hedging Detector

**Issue**: `FEEDBACK-010` — Detect LLM uncertainty as memory gap signal

```python
# k1/feedback/hedging_detector.py

HEDGING_PATTERNS = [
    r"I'm not sure",
    r"I don't have (enough )?information",
    r"I couldn't find",
    r"Based on what I know",
    r"It's possible that",
    r"I think|I believe",  # Without certainty
]

class HedgingDetector:
    """
    Detects when LLM responses contain uncertainty language.

    Signal: IMPLICIT / P03 (memory gap) or P01 (retrieval failure)
    """

    def analyze_response(
        self,
        response_text: str,
        query_context: QueryContext,
    ) -> FeedbackEnvelope | None:
        """Detect hedging in LLM response."""

        hedging_score = self.compute_hedging_score(response_text)

        if hedging_score > 0.6:
            # Strong hedging detected
            return FeedbackEnvelope(
                target_pipeline="P03",  # Memory consolidation
                signal_class="IMPLICIT",
                source="K1",
                source_component="hedging_detector",
                session_id=query_context.session_id,
                trace_id=query_context.trace_id,
                correlation_ids=CorrelationIds(
                    query_id=query_context.query_id,
                    wal_positions=query_context.retrieved_wal_positions,
                ),
                payload={
                    "feedback_type": "NOVELTY_SIGNAL",
                    "hedging_score": hedging_score,
                    "query_text": query_context.query_text,
                    "retrieved_count": len(query_context.retrieved_wal_positions),
                    "gap_signal": True,  # Memory gap detected
                },
                priority=0.5,
            )

        return None
```

---

## Epic 2.2: User Correction Detection

### Story 2.2.1: Explicit Correction Parser

**Issue**: `FEEDBACK-011` — Parse user corrections from messages

```python
# k1/feedback/correction_parser.py

CORRECTION_PATTERNS = [
    r"(?:that's|that is) (?:not|wrong)",
    r"(?:actually|no),? (?:it's|it is|she's|he's)",
    r"you (?:got|have) (?:it|that) wrong",
    r"let me correct",
    r"I meant",
]

class CorrectionParser:
    """
    Detects and parses explicit user corrections.

    Signal: CORRECTION / varies by content
    """

    async def parse_message(
        self,
        message: str,
        context: MessageContext,
    ) -> FeedbackEnvelope | None:
        """Parse user message for corrections."""

        if not self.is_correction(message):
            return None

        # Use LLM to extract the correction details
        correction = await self.extract_correction(message, context)

        if correction.corrects_entity:
            return FeedbackEnvelope(
                target_pipeline="P02",  # Write pipeline
                signal_class="CORRECTION",
                source="USER",
                session_id=context.session_id,
                trace_id=context.trace_id,
                correlation_ids=CorrelationIds(
                    wal_positions=correction.affected_wal_positions,
                ),
                payload={
                    "feedback_type": "ENTITY_CORRECTION",
                    "wal_position": correction.affected_wal_positions[0],
                    "extracted_entities": correction.wrong_entities,
                    "correct_entities": correction.correct_entities,
                    "user_message": message,
                },
                priority=0.9,  # High priority for explicit corrections
            )

        # ... handle other correction types
```

---

# Milestone 3: Pipeline Integration (P01-P06)

**Goal**: Wire core pipelines to consume feedback signals.

## Epic 3.1: P03 Consolidation Feedback Consumer

### Story 3.1.1: P03 Feedback Handler

**Issue**: `FEEDBACK-012` — Implement P03 feedback consumption

```python
# k0/pipelines/p03_consolidation/feedback_handler.py

class P03FeedbackHandler:
    """
    Consumes feedback for P03 (Consolidation/Salience).

    Subscribed topics: feedback.signal.p03

    Actions:
    - Adjust salience scores based on outcome feedback
    - Reverse decay for wrongly-forgotten memories
    - Update clustering parameters
    """

    topics = ["feedback.signal.p03"]

    async def handle(self, msg: BusMessage, ctx: PipelineContext) -> None:
        """Process P03 feedback signal."""

        envelope = FeedbackEnvelope.model_validate(msg.payload)
        payload = P03FeedbackPayload.model_validate(envelope.payload)

        match payload.feedback_type:
            case "SALIENCE_ADJUSTMENT":
                await self._handle_salience_adjustment(payload, ctx)
            case "DECAY_REVERSAL":
                await self._handle_decay_reversal(payload, ctx)
            case "CLUSTER_CORRECTION":
                await self._handle_cluster_correction(payload, ctx)
            case "REINFORCEMENT_OUTCOME":
                await self._handle_reinforcement_outcome(payload, ctx)
            case "NOVELTY_SIGNAL":
                await self._handle_novelty_signal(payload, ctx)

        # Mark feedback as consumed
        await self._mark_consumed(envelope.envelope_id, ctx)

    async def _handle_salience_adjustment(
        self,
        payload: P03FeedbackPayload,
        ctx: PipelineContext,
    ) -> None:
        """Adjust salience scores for memories."""

        for wal_pos in payload.wal_positions:
            if payload.salience_delta:
                # Relative adjustment
                await ctx.execute("""
                    UPDATE st_hipp_events
                    SET importance = LEAST(1.0, GREATEST(0.0, importance + $1))
                    WHERE wal_position = $2
                """, payload.salience_delta, wal_pos)

            elif payload.importance_override:
                # Absolute override
                await ctx.execute("""
                    UPDATE st_hipp_events
                    SET importance = $1
                    WHERE wal_position = $2
                """, payload.importance_override, wal_pos)

        ctx.metrics.counter(
            "p03_salience_adjustments_total",
            labels={"adjustment_type": "delta" if payload.salience_delta else "override"}
        )

    async def _handle_decay_reversal(
        self,
        payload: P03FeedbackPayload,
        ctx: PipelineContext,
    ) -> None:
        """
        Reverse decay for memories that were needed but had decayed.

        This is critical feedback — the system forgot something important!
        """
        for wal_pos in payload.wal_positions:
            # Restore importance and reset decay timer
            await ctx.execute("""
                UPDATE st_hipp_events
                SET
                    importance = GREATEST(importance, 0.7),  -- Restore to at least 0.7
                    last_accessed = NOW(),
                    access_count = access_count + 1,
                    reinforced_at = NOW()
                WHERE wal_position = $1
            """, wal_pos)

        # Log this as a learning opportunity
        await ctx.bus.dispatch(
            topic="learning.feedback.decay_reversal",
            message=BusMessage(
                topic="learning.feedback.decay_reversal",
                payload={
                    "wal_positions": payload.wal_positions,
                    "query_context": payload.retrieval_query,
                },
            )
        )

        ctx.metrics.counter(
            "p03_decay_reversals_total",
            labels={"count": str(len(payload.wal_positions))}
        )
```

**Acceptance Criteria**:

- [ ] P03 subscribes to feedback.signal.p03
- [ ] Salience adjustments applied to st_hipp_events
- [ ] Decay reversals restore importance and emit learning signal
- [ ] Feedback marked as consumed
- [ ] Metrics emitted

---

## Epic 3.2: Adaptive Parameter Learning

### Story 3.2.1: Thompson Sampling for Thresholds

**Issue**: `FEEDBACK-013` — Implement adaptive thresholds using feedback

```python
# k0/feedback/adaptive_parameters.py

import numpy as np
from scipy.stats import beta as beta_dist

class AdaptiveParameter:
    """
    A parameter that adapts based on feedback using Thompson Sampling.

    Used for thresholds like:
    - P03 reinforcement threshold (currently hardcoded 0.85)
    - P03 decay rate (currently hardcoded 0.005)
    - P01 retrieval limit
    """

    def __init__(
        self,
        name: str,
        min_value: float,
        max_value: float,
        initial_value: float,
        pipeline_id: str,
    ):
        self.name = name
        self.min_value = min_value
        self.max_value = max_value
        self.pipeline_id = pipeline_id

        # Thompson Sampling parameters (Beta distribution)
        # Discretize the range into K arms
        self.k_arms = 10
        self.arm_values = np.linspace(min_value, max_value, self.k_arms)

        # Prior: start uniform, concentrate around initial_value
        initial_arm = np.argmin(np.abs(self.arm_values - initial_value))
        self.alpha = np.ones(self.k_arms)
        self.beta = np.ones(self.k_arms)
        self.alpha[initial_arm] = 5  # Prior belief in initial value

    def sample(self) -> float:
        """Sample a value using Thompson Sampling."""
        samples = [beta_dist.rvs(a, b) for a, b in zip(self.alpha, self.beta)]
        best_arm = np.argmax(samples)
        return self.arm_values[best_arm]

    def update(self, value_used: float, reward: float) -> None:
        """
        Update beliefs based on feedback.

        Args:
            value_used: The parameter value that was used
            reward: 0.0 to 1.0 indicating success
        """
        arm = np.argmin(np.abs(self.arm_values - value_used))

        if reward > 0.5:
            self.alpha[arm] += reward
        else:
            self.beta[arm] += (1 - reward)

    def get_optimal(self) -> float:
        """Get the current optimal value based on beliefs."""
        expected = self.alpha / (self.alpha + self.beta)
        return self.arm_values[np.argmax(expected)]

    def get_uncertainty(self) -> float:
        """Get the uncertainty in current beliefs."""
        # Entropy of the posterior
        variances = (self.alpha * self.beta) / ((self.alpha + self.beta)**2 * (self.alpha + self.beta + 1))
        return np.mean(variances)


class AdaptiveParameterRegistry:
    """
    Registry of adaptive parameters across pipelines.

    Persisted to st_adaptive_parameters for durability.
    """

    _parameters: dict[str, AdaptiveParameter] = {}

    @classmethod
    def register(cls, param: AdaptiveParameter) -> None:
        key = f"{param.pipeline_id}:{param.name}"
        cls._parameters[key] = param

    @classmethod
    def get(cls, pipeline_id: str, name: str) -> AdaptiveParameter | None:
        return cls._parameters.get(f"{pipeline_id}:{name}")

    @classmethod
    async def persist(cls, ctx: PipelineContext) -> None:
        """Persist all parameters to database."""
        for key, param in cls._parameters.items():
            await ctx.execute("""
                INSERT INTO st_adaptive_parameters (
                    key, pipeline_id, name, alpha, beta, arm_values, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, NOW())
                ON CONFLICT (key) DO UPDATE SET
                    alpha = $4, beta = $5, updated_at = NOW()
            """,
                key, param.pipeline_id, param.name,
                param.alpha.tolist(), param.beta.tolist(),
                param.arm_values.tolist()
            )

    @classmethod
    async def load(cls, ctx: PipelineContext) -> None:
        """Load all parameters from database."""
        rows = await ctx.fetch("SELECT * FROM st_adaptive_parameters")
        for row in rows:
            param = AdaptiveParameter(
                name=row["name"],
                min_value=row["arm_values"][0],
                max_value=row["arm_values"][-1],
                initial_value=row["arm_values"][len(row["arm_values"])//2],
                pipeline_id=row["pipeline_id"],
            )
            param.alpha = np.array(row["alpha"])
            param.beta = np.array(row["beta"])
            cls._parameters[row["key"]] = param
```

---

# Milestone 4: Pipeline Integration (P07-P20)

**Goal**: Extend feedback consumption to remaining pipelines.

## Epic 4.1: Schema Definitions for P07-P20

*Issues FEEDBACK-014 through FEEDBACK-027 — Define feedback schemas for each remaining pipeline*

| Issue | Pipeline | Key Feedback Types |
|-------|----------|-------------------|
| FEEDBACK-014 | P07 Sync | CONFLICT_RESOLUTION_OUTCOME, MERGE_QUALITY |
| FEEDBACK-015 | P08 Embeddings | SIMILARITY_ACCURACY, EMBEDDING_QUALITY |
| FEEDBACK-016 | P09 Connectors | CONNECTION_SUCCESS, DATA_QUALITY |
| FEEDBACK-017 | P10 PII | FALSE_POSITIVE, FALSE_NEGATIVE |
| FEEDBACK-018 | P11 GDPR | COMPLIANCE_VERIFIED, USER_SATISFACTION |
| FEEDBACK-019 | P12 E2EE | ENCRYPTION_ISSUES, KEY_PROBLEMS |
| FEEDBACK-020 | P13 Index | SEARCH_QUALITY, INDEX_FRESHNESS |
| FEEDBACK-021 | P14 Dedup | DUPLICATE_MISSED, FALSE_DUPLICATE |
| FEEDBACK-022 | P15 Rollups | SUMMARY_ACCURACY, COMPRESSION_LOSS |
| FEEDBACK-023 | P16 Features | FLAG_EFFECTIVENESS, AB_OUTCOME |
| FEEDBACK-024 | P17 QoS | BUDGET_ACCURACY, THROTTLE_APPROPRIATE |
| FEEDBACK-025 | P18 Safety | FALSE_BLOCK, MISSED_THREAT |
| FEEDBACK-026 | P19 Personalization | PREFERENCE_ACCURACY, RECOMMENDATION_QUALITY |
| FEEDBACK-027 | P20 Procedures | HABIT_EFFECTIVENESS, SKILL_ACCURACY |

---

# Milestone 5: Adaptive Learning Engine

**Goal**: Build the meta-learning system that uses feedback to improve all pipelines.

## Epic 5.1: Learning Coordinator

### Story 5.1.1: P06 Learning Pipeline Enhancement

**Issue**: `FEEDBACK-028` — Enhance P06 to coordinate cross-pipeline learning

```python
# k0/pipelines/p06_learning/coordinator.py

class LearningCoordinator:
    """
    Central coordinator for feedback-driven learning.

    P06 acts as the "meta-learner" — it doesn't just receive feedback,
    it learns *how to learn* based on feedback patterns across pipelines.
    """

    topics = [
        "feedback.signal.*",  # Subscribe to ALL feedback
        "learning.feedback.*",  # Learning-specific signals
    ]

    async def handle(self, msg: BusMessage, ctx: PipelineContext) -> None:
        """Process feedback for learning coordination."""

        envelope = FeedbackEnvelope.model_validate(msg.payload)

        # Track feedback patterns across pipelines
        await self._record_feedback_pattern(envelope, ctx)

        # Update adaptive parameters based on feedback
        await self._update_adaptive_parameters(envelope, ctx)

        # Detect learning opportunities (gaps, corrections, patterns)
        opportunities = await self._detect_learning_opportunities(envelope, ctx)

        for opp in opportunities:
            await ctx.bus.dispatch(
                topic=f"learning.opportunity.{opp.type}",
                message=BusMessage(payload=opp.model_dump())
            )

    async def _update_adaptive_parameters(
        self,
        envelope: FeedbackEnvelope,
        ctx: PipelineContext,
    ) -> None:
        """Update parameters based on outcome feedback."""

        if envelope.signal_class == "OUTCOME":
            # Find adaptive parameters for this pipeline
            pipeline_params = [
                p for p in AdaptiveParameterRegistry._parameters.values()
                if p.pipeline_id == envelope.target_pipeline
            ]

            # Compute reward from feedback
            reward = self._compute_reward(envelope)

            for param in pipeline_params:
                current_value = param.get_optimal()
                param.update(current_value, reward)

            # Persist periodically
            if self._should_persist():
                await AdaptiveParameterRegistry.persist(ctx)
```

---

# Milestone 6: Active Learning Loop Integration

**Goal**: Connect the feedback system to the Active Learning Loop (Idea-0001).

## Epic 6.1: Curiosity-Feedback Loop

### Story 6.1.1: Question Outcome Tracking

**Issue**: `FEEDBACK-029` — Track outcomes of curiosity questions

```python
# k0/feedback/curiosity_tracker.py

class CuriosityTracker:
    """
    Tracks outcomes of questions asked by the Curiosity Agent.

    Feeds back to P06 for learning strategy adjustment.
    """

    async def track_question_outcome(
        self,
        question_id: str,
        was_answered: bool,
        was_helpful: bool,
        timing_appropriate: bool,
        answer_quality: float,  # 0.0 to 1.0
        gap_resolved: bool,
    ) -> FeedbackEnvelope:
        """Generate feedback for a curiosity question."""

        return FeedbackEnvelope(
            target_pipeline="P06",
            signal_class="OUTCOME",
            source="K1",
            source_component="curiosity_tracker",
            session_id=self.session_id,
            trace_id=current_trace_id(),
            payload={
                "feedback_type": "CURIOSITY_CALIBRATION",
                "question_id": question_id,
                "question_was_helpful": was_helpful,
                "question_was_answered": was_answered,
                "question_timing_appropriate": timing_appropriate,
                "answer_quality": answer_quality,
                "gap_resolved": gap_resolved,
            },
            priority=0.7,
        )
```

### Story 6.1.2: Gap Resolution Feedback

**Issue**: `FEEDBACK-030` — Feed gap resolution back to P03

When a gap from `st_learning_queue` is resolved via user answer:

```python
# k0/feedback/gap_resolution.py

async def on_gap_resolved(
    gap_id: str,
    resolution: GapResolution,
    ctx: PipelineContext,
) -> None:
    """
    Generate feedback when an Active Learning gap is resolved.

    This closes the loop:
    P03 detects gap → P05 triggers question → User answers → P02 ingests → Feedback to P03
    """

    feedback = FeedbackEnvelope(
        target_pipeline="P03",
        signal_class="OUTCOME",
        source="SYSTEM",
        source_component="gap_resolution",
        session_id=resolution.session_id,
        trace_id=resolution.trace_id,
        correlation_ids=CorrelationIds(
            wal_positions=resolution.new_wal_positions,
        ),
        payload={
            "feedback_type": "REINFORCEMENT_OUTCOME",
            "gap_id": gap_id,
            "gap_type": resolution.gap_type,
            "original_wal_positions": resolution.original_wal_positions,
            "new_wal_positions": resolution.new_wal_positions,
            "was_helpful": True,
            "user_confirmed": True,
        },
        priority=0.8,
    )

    await send_feedback(feedback, ctx)

    # Also update the question strategy in P06
    strategy_feedback = FeedbackEnvelope(
        target_pipeline="P06",
        signal_class="OUTCOME",
        source="SYSTEM",
        source_component="gap_resolution",
        session_id=resolution.session_id,
        trace_id=resolution.trace_id,
        payload={
            "feedback_type": "STRATEGY_EFFECTIVENESS",
            "strategy_id": resolution.question_strategy,
            "strategy_effectiveness": 1.0,  # Gap was resolved!
        },
        priority=0.7,
    )

    await send_feedback(strategy_feedback, ctx)
```

---

## Issue Checklist Summary

| Issue ID | Title | Milestone | Priority |
|----------|-------|-----------|----------|
| FEEDBACK-001 | Create FeedbackEnvelope base model | M0 | P0 |
| FEEDBACK-002 | Define signal class taxonomy | M0 | P0 |
| FEEDBACK-003 | Implement FeedbackSchemaRegistry | M0 | P0 |
| FEEDBACK-004 | Define feedback schemas for P01-P06 | M0 | P0 |
| FEEDBACK-005 | Extend observe.py for feedback ingestion | M1 | P0 |
| FEEDBACK-006 | Create st_feedback_signals migration | M1 | P0 |
| FEEDBACK-007 | Register feedback bus topics | M1 | P1 |
| FEEDBACK-008 | Detect query reformulations | M2 | P1 |
| FEEDBACK-009 | Detect session abandonment | M2 | P1 |
| FEEDBACK-010 | Detect LLM hedging | M2 | P2 |
| FEEDBACK-011 | Parse user corrections | M2 | P1 |
| FEEDBACK-012 | Implement P03 feedback handler | M3 | P0 |
| FEEDBACK-013 | Implement adaptive thresholds | M3 | P1 |
| FEEDBACK-014-027 | Schema definitions for P07-P20 | M4 | P2 |
| FEEDBACK-028 | Enhance P06 learning coordinator | M5 | P1 |
| FEEDBACK-029 | Track curiosity question outcomes | M6 | P1 |
| FEEDBACK-030 | Feed gap resolution back to P03 | M6 | P1 |

---

## Success Metrics

| Metric | Baseline | Target | Measurement |
|--------|----------|--------|-------------|
| Feedback signals/day | 0 | 1000+ | Prometheus counter |
| P03 salience accuracy | Unknown | +15% improvement | A/B test |
| Query success rate | Unknown | +10% improvement | Reformulation reduction |
| Adaptive parameter convergence | N/A | <7 days | Thompson Sampling entropy |
| Gap resolution rate | Unknown | +20% | st_learning_queue RESOLVED/PENDING |

---

## Dependencies

| Dependency | Status | Required By |
|------------|--------|-------------|
| PostgreSQL 16+ migration | ✅ Complete | M1 |
| observe.py exists | ✅ Complete | M1 |
| BusDispatcher | ✅ Complete | M1 |
| st_hipp_events table | ✅ Complete | M3 |
| P06 Learning pipeline | Partial | M5 |
| Active Learning Loop (Idea-0001) | Proposed | M6 |

---

## Open Questions

1. **Schema Evolution**: How do we handle schema changes for existing feedback types?
   - Proposed: Version in feedback_version field, validators handle backward compat

2. **Feedback Expiry**: Should old unconsumed feedback expire?
   - Proposed: Yes, 30-day TTL with archival to cold storage

3. **Cross-Pipeline Correlation**: Should feedback be able to target multiple pipelines?
   - Proposed: Single target_pipeline, but P06 can fan-out internally

4. **Privacy**: Should feedback be subject to PEP evaluation?
   - Proposed: Feedback inherits privacy band from correlated WAL entries

---

## Next Steps

1. **Review this plan** with K0/K1 architecture team
2. **Create ADR** for feedback system design decisions
3. **Begin M0** with FeedbackEnvelope and SchemaRegistry
4. **Parallel**: Define schemas for P01-P06 with pipeline owners
