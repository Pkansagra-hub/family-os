# R1 Importance Scorer Phase - Wiki Documentation

> **Pipeline**: P03 Consolidation
> **Phase**: R1 (Importance Scoring & Hebbian Learning)
> **Version**: 1.0.0
> **Last Updated**: 2026-01-28
> **Source File**: `k0/pipelines/p03/phases/r1_importance_scorer.py`

---

## Table of Contents

1. [Overview](#overview)
2. [Scientific Basis](#scientific-basis)
3. [File Dependencies](#file-dependencies)
4. [Class Reference](#class-reference)
5. [Algorithms](#algorithms)
6. [API Reference](#api-reference)
7. [Data Structures](#data-structures)
8. [End-to-End Process Flow](#end-to-end-process-flow)
9. [Configuration](#configuration)
10. [Metrics & Observability](#metrics--observability)
11. [Error Handling](#error-handling)
12. [Usage Examples](#usage-examples)

---

## Overview

The **R1 Importance Scorer Phase** is the second phase (after R0 Batch Selection) in the P03 Consolidation Pipeline. It determines which hippocampal events should be prioritized for memory consolidation based on cognitive neuroscience principles.

### Responsibilities

1. **Load importance weights** - Learned (if 500+ samples) or static defaults
2. **Compute importance score** for each event using multi-factor formula
3. **Log scoring factors** to `st_consolidation_audit` for explainability
4. **Update event state** with importance fields
5. **(Future)** Extract co-occurrences for Hebbian edge updates

### Position in Pipeline

```
R0 (Batch Selection) → R1 (Importance Scoring) → R2 (Episode Clustering) → R3 → R4 → R5 → R6 → R7 → R8
```

---

## Scientific Basis

### McGaugh (2004) - Emotional Memory Enhancement

The R1 algorithm is based on cognitive neuroscience research showing that emotional memories are more strongly encoded due to **amygdala-hippocampus interaction**. Events with high emotional salience, novelty, or social significance are prioritized for consolidation.

**Key Principles:**

- Both strong positive AND strong negative emotions enhance memory encoding
- Social interactions increase memory salience
- Novel information is prioritized over routine events
- Intentional actions (planning, reminders) indicate future relevance

### Roediger & Karpicke (2006) - Retrieval Practice

Intent-based boost multipliers are derived from research showing that retrieval practice strengthens memory traces. Querying memories and planning activities indicate intentional cognitive engagement.

---

## File Dependencies

### Primary Files

| File Path | Purpose | Key Exports |
|-----------|---------|-------------|
| `k0/pipelines/p03/phases/r1_importance_scorer.py` | Phase implementation | `R1ImportanceScorer`, `R1Config`, `create_r1_phase()` |
| `k0/modules/consolidation/algorithms/importance_scorer.py` | Core algorithm | `ImportanceScorer`, `ImportanceWeights`, `ImportanceBreakdown` |
| `k0/pipelines/p03/audit_logger.py` | Audit trail | `P03AuditLogger`, `AuditAction`, `AuditRecord` |
| `k0/pipelines/p03/phase_outputs.py` | Output containers | `ScoredEvent`, `P03PhaseOutputs` |
| `k0/pipelines/p03/phase_interface.py` | Phase contract | `P03PhaseResult`, `P03RunnerContext` |
| `k0/pipelines/p03/runner_contract.py` | Pipeline contract | `P03PhaseId`, `P03PhaseStatus` |
| `k0/pipelines/p03/envelope.py` | Batch container | `P03BatchEnvelope` |
| `k0/pipelines/p03/observability.py` | Metrics/errors | `P03Error`, `R1PhaseMetrics` |
| `k0/pipelines/p03/context.py` | Utilities | `generate_ulid()`, `P03CycleContext` |

### Import Graph

```
r1_importance_scorer.py
├── k0.modules.consolidation.algorithms.importance_scorer
│   ├── ImportanceScorer (class)
│   └── ImportanceWeights (dataclass)
├── k0.pipelines.p03.audit_logger
│   └── P03AuditLogger (class)
├── k0.pipelines.p03.observability
│   └── P03Error (dataclass)
├── k0.pipelines.p03.phase_interface
│   └── P03PhaseResult (dataclass)
├── k0.pipelines.p03.phase_outputs
│   └── ScoredEvent (dataclass)
├── k0.pipelines.p03.runner_contract
│   └── P03PhaseId (enum)
└── k0.pipelines.p03.envelope (TYPE_CHECKING)
    └── P03BatchEnvelope (dataclass)
```

---

## Class Reference

### R1ImportanceScorer

**Location:** `k0/pipelines/p03/phases/r1_importance_scorer.py`

```python
class R1ImportanceScorer:
    """
    R1 Phase: Importance Scoring and Hebbian Learning.
    """

    PHASE_ID = P03PhaseId.R1_SCORE

    def __init__(self, config: Optional[R1Config] = None) -> None: ...

    @property
    def phase_id(self) -> P03PhaseId: ...

    def should_skip(self, envelope: P03BatchEnvelope) -> bool: ...

    def idempotency_key(self, envelope: P03BatchEnvelope) -> str: ...

    async def run(
        self,
        envelope: P03BatchEnvelope,
        ctx: P03RunnerContext,
    ) -> P03PhaseResult: ...
```

### R1Config

**Location:** `k0/pipelines/p03/phases/r1_importance_scorer.py`

```python
@dataclass
class R1Config:
    """R1 phase configuration."""

    audit_sample_rate: float = 1.0        # 100% for debug; 0.1 for production
    enable_hebbian: bool = False          # Not yet implemented (Issue 4.1.3)
    min_samples_for_learned_weights: int = 500
    importance_weights: Optional[ImportanceWeights] = None
```

### ImportanceScorer

**Location:** `k0/modules/consolidation/algorithms/importance_scorer.py`

```python
class ImportanceScorer:
    """
    Compute importance scores for hippocampal event selection.
    """

    DEFAULT_WEIGHTS = ImportanceWeights()
    EVENT_TYPE_MULTIPLIERS: Dict[str, float] = {...}
    INTENT_BOOST_MULTIPLIERS: Dict[str, float] = {...}
    MIN_SAMPLES_FOR_LEARNED_WEIGHTS = 500
    LOG2_10 = 3.321928

    def __init__(
        self,
        space_id: str,
        weight_store: Optional[WeightStoreProtocol] = None,
    ) -> None: ...

    async def get_weights(self) -> ImportanceWeights: ...

    async def get_weights_with_cold_start(
        self,
        global_store: Optional[WeightStoreProtocol] = None,
    ) -> Tuple[ImportanceWeights, str, int]: ...

    def compute_emotional_intensity(
        self,
        sentiment_score: float,
        affect_valence: float,
        weights: ImportanceWeights,
    ) -> float: ...

    def compute_social_factor(
        self,
        participant_count: int,
        weights: ImportanceWeights,
    ) -> float: ...

    def compute_novelty_factor(
        self,
        novelty_score: float,
        weights: ImportanceWeights,
    ) -> float: ...

    def get_event_type_multiplier(self, content_type: str) -> float: ...

    def compute_importance_score(
        self,
        event: Any,
        weights: ImportanceWeights,
    ) -> Tuple[float, ImportanceBreakdown]: ...

    async def score_batch(self, events: List[Any]) -> List[Dict[str, Any]]: ...

    async def score_batch_with_audit(
        self,
        events: List[Any],
        audit_logger: Any,
        sample_rate: float = 1.0,
    ) -> List[Dict[str, Any]]: ...

    def select_batch(
        self,
        scored_events: List[Any],
        batch_size: int,
    ) -> List[Any]: ...

    def get_priority_tier(self, score: float) -> str: ...
```

---

## Algorithms

### 1. Master Importance Formula

```
importance = (emotional + novelty + social) × event_type_multiplier × intent_boost
```

**Final score is clamped to [0.0, 1.0]**

### 2. Emotional Intensity Algorithm

Uses absolute values because both strong positive AND strong negative emotions enhance memory encoding.

```python
def compute_emotional_intensity(sentiment_score, affect_valence, weights):
    sentiment_intensity = abs(sentiment_score)  # [-1, 1] → [0, 1]
    affect_intensity = abs(affect_valence)      # [-1, 1] → [0, 1]

    return (
        sentiment_intensity * weights.sentiment_weight +  # 0.25
        affect_intensity * weights.affect_weight          # 0.30
    )
    # Returns: [0.0, ~0.55]
```

### 3. Novelty Factor Algorithm

Novelty score represents how different this event is from existing memory clusters.

```python
def compute_novelty_factor(novelty_score, weights):
    clamped_novelty = max(0.0, min(1.0, novelty_score))
    return clamped_novelty * weights.novelty_weight  # 0.25
    # Returns: [0.0, 0.25]
```

**Note:** R1 uses `salience_score` as novelty proxy since actual novelty is computed by R3 (which runs after R1).

### 4. Social Factor Algorithm (Logarithmic Scaling)

Prevents large groups from completely dominating importance scores using logarithmic scaling.

```python
LOG2_10 = 3.321928  # log₂(10)

def compute_social_factor(participant_count, weights):
    if participant_count <= 1:
        return 0.0  # Solo event, no social bonus

    # Log scale: log₂(count) / log₂(10)
    log_factor = min(1.0, math.log2(participant_count) / LOG2_10)
    return log_factor * weights.social_weight  # 0.20
    # Returns: [0.0, 0.20]
```

**Social Factor Scale:**

| Participants | log₂(n)/3.32 | Factor (×0.20) |
|--------------|--------------|----------------|
| 1 | 0.00 | 0.00 |
| 2 | 0.30 | 0.06 |
| 3 | 0.48 | 0.10 |
| 5 | 0.70 | 0.14 |
| 10 | 1.00 | 0.20 (capped) |

### 5. Event Type Multipliers

Higher multipliers boost importance for significant event types:

| Event Type | Multiplier | Rationale |
|------------|------------|-----------|
| `milestone` | 2.0 | Birthdays, anniversaries, achievements |
| `celebration` | 2.0 | Special occasions |
| `video` | 1.3 | Rich visual memories |
| `photo` / `image` | 1.2 | Visual memories |
| `voice` / `audio` | 1.1 | Voice memos |
| `message` / `chat` | 1.0 | Default text messages |
| `calendar` | 0.9 | Calendar events |
| `location` | 0.8 | Check-ins and location updates |
| `transaction` | 0.6 | Financial transactions |
| `routine` | 0.5 | Daily repeated events (lower priority) |

### 6. Intent-Based Boost Multipliers (UltraBERT)

Based on cognitive significance of intentional actions:

| Intent Label | Boost | Rationale |
|--------------|-------|-----------|
| `query_memory` | 1.20 | Retrieval strengthens memory traces |
| `share_news` | 1.20 | News-sharing events are typically significant |
| `set_reminder` | 1.15 | Reminders indicate future importance |
| `make_plan` | 1.15 | Planning content has intentional significance |
| `seek_advice` | 1.10 | Decision-making context matters |
| `reflect` | 1.10 | Reflective content often leads to semantic patterns |
| `express_feeling` | 1.00 | Already captured by emotional component |
| `casual_chat` | 0.90 | Routine conversation, slightly lower salience |

### 7. Cold Start Strategy & Progressive Blending

3-level fallback with progressive weight blending for new users/spaces.

**Blending Formula:**

```python
α = min(1.0, sample_count / 500)
blended_weight = α × learned_weight + (1 - α) × static_prior
```

**Behavior:**

| Sample Count | α | Behavior |
|--------------|---|----------|
| 0-99 | 0.0 | Pure static priors |
| 100-499 | 0.2-0.99 | Progressive blending |
| 500+ | 1.0 | Pure learned weights |

**Fallback Priority:**

1. Per-space learned weights (if sample_count ≥ 100)
2. Global learned weights (if per-space insufficient)
3. Static priors (final fallback)

### 8. Priority Tier Classification

```python
def get_priority_tier(score: float) -> str:
    if score >= 0.80:
        return "CRITICAL"   # Process immediately
    elif score >= 0.50:
        return "HIGH"       # Process in current cycle
    elif score >= 0.30:
        return "MEDIUM"     # Process if capacity allows
    else:
        return "LOW"        # May be deferred
```

---

## API Reference

### Input: P03BatchEnvelope

```python
@dataclass
class P03BatchEnvelope:
    context: P03CycleContext    # Immutable cycle metadata
    events: List[P03EventState]  # Events to score
    phases: P03PhaseOutputs      # Phase outputs container
    staged: P03StagedWrites      # Staged writes
    observability: P03ObservabilityContext
    current_phase: P03PhaseId
    phase_statuses: Dict[P03PhaseId, P03PhaseStatus]
```

#### Event Input Fields (P03EventState)

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| `event_id` | `str` | ULID | Unique event identifier |
| `sentiment_score` | `float` | [-1.0, 1.0] | Sentiment analysis score |
| `affect_valence` | `float` | [-1.0, 1.0] | Emotional valence |
| `salience_score` | `float` | [0.0, 1.0] | P02's salience (used as novelty proxy) |
| `participant_count` | `int` | ≥1 | Number of participants |
| `content_type` | `str` | enum | Event type (message, photo, etc.) |
| `intent_label` | `str` | enum | UltraBERT intent classification |

### Output: P03PhaseResult

```python
@dataclass
class P03PhaseResult:
    phase_id: P03PhaseId          # R1_SCORE
    status: P03PhaseStatus        # DONE, SKIP, or FAIL
    duration_ms: int              # Execution time
    outputs_summary: Dict[str, Any]  # Summary metrics
    error_info: Optional[P03Error]   # Error details (if FAIL)
    skip_reason: Optional[str]       # Skip reason (if SKIP)
    idempotency_key: Optional[str]   # For exactly-once semantics
```

#### outputs_summary Structure

```python
{
    "events_scored": int,          # Number of events scored
    "audit_records": int,          # Audit records created
    "avg_importance": float,       # Average importance score
    "critical_count": int,         # Events with score ≥ 0.80
    "high_count": int,             # Events with 0.50 ≤ score < 0.80
    "weights_source": str,         # "static", "learned", "blended"
}
```

### Envelope Mutations

After R1 execution, the envelope is enriched:

```python
# Phase outputs populated:
envelope.phases.r1_scored_events: List[ScoredEvent]
envelope.phases.r1_audit_records: List[AuditRecord]

# Each event state updated:
event.importance_score: float      # [0.0, 1.0]
event.recency_factor: float        # Reserved for future use
event.affect_factor: float         # Emotional component
event.social_factor: float         # Social component
event.novelty_factor: float        # Novelty component
event.importance_computed: bool    # Set to True
```

---

## Data Structures

### ImportanceWeights

```python
@dataclass(frozen=True)
class ImportanceWeights:
    """Configurable weights for importance scoring components."""

    sentiment_weight: float = 0.25   # Sentiment analysis contribution
    affect_weight: float = 0.30      # Emotional valence/arousal contribution
    novelty_weight: float = 0.25     # Information novelty contribution
    social_weight: float = 0.20      # Social context contribution

    def total(self) -> float:
        """Sum of all weights (should be 1.0 for normalization)."""
        return (self.sentiment_weight + self.affect_weight +
                self.novelty_weight + self.social_weight)
```

### ImportanceBreakdown

```python
@dataclass
class ImportanceBreakdown:
    """Component breakdown of importance score for audit logging."""

    emotional_component: float   # Combined sentiment + affect contribution
    novelty_component: float     # Novelty contribution
    social_component: float      # Social relevance contribution
    multiplier: float            # Event type × intent multiplier applied
    final_score: float           # Final normalized score [0, 1]
    weights_source: str = "static"  # "static" or "learned"
```

### ScoredEvent

```python
@dataclass
class ScoredEvent:
    """Event with computed importance score (R1 output)."""

    event_id: str
    importance_score: float
    recency_factor: float
    affect_factor: float
    social_factor: float
    novelty_factor: float
```

### AuditRecord

```python
@dataclass
class AuditRecord:
    """A single audit record for a consolidation decision."""

    audit_id: str                     # ULID primary key
    memory_id: str                    # Event ID
    source_table: str                 # "st_hipp_events"
    action: AuditAction               # SCORE
    formula_used: Optional[str]       # "importance_scorer"
    formula_version: Optional[str]    # "1.0.0"
    inputs: Optional[Dict[str, Any]]  # Input parameters
    outputs: Optional[Dict[str, Any]] # Output values
    explanation: Optional[str]        # Human-readable explanation
    space_id: str
    tenant_id: str
    cycle_id: Optional[str]
    confidence: Optional[float]       # importance_score value
    created_at: int                   # Milliseconds since epoch
```

### AuditAction Enum

```python
class AuditAction(Enum):
    REINFORCE = "REINFORCE"
    DECAY = "DECAY"
    ARCHIVE = "ARCHIVE"
    MERGE = "MERGE"
    CREATE = "CREATE"
    EXTEND = "EXTEND"
    PRUNE = "PRUNE"
    SKIP = "SKIP"
    CONTRADICT = "CONTRADICT"
    SCORE = "SCORE"  # Used by R1
```

---

## End-to-End Process Flow

### Sequence Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        R1 IMPORTANCE SCORING PHASE                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 1: Initialize                                                          │
│   • Create R1ImportanceScorer(config)                                       │
│   • Load weight_store from ctx.syscalls                                     │
│   • Create P03AuditLogger(space_id, tenant_id, cycle_id)                    │
│   • Get sample_rate from config (default: 1.0)                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 2: Skip Check                                                          │
│   • If envelope.events is empty → SKIP                                      │
│   • If all events have importance_computed=True → SKIP                      │
│   • Return P03PhaseResult.skip() with reason                                │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 3: Load Weights                                                        │
│   • Check weight cache → if cached, use cached weights                      │
│   • Try weight_store.get_weights(space_id, "importance_")                   │
│   • If learned.sample_count >= 500 → use learned weights                    │
│   • Else → use static defaults:                                             │
│       sentiment=0.25, affect=0.30, novelty=0.25, social=0.20                │
│   • Set _weights_source to "static" or "learned"                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 4: Score Each Event (score_batch_with_audit)                           │
│                                                                             │
│   FOR each event in envelope.events:                                        │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ 4a. Extract Event Attributes (with safe defaults)                   │   │
│   │     sentiment_score = event.sentiment_score or 0.0                  │   │
│   │     affect_valence = event.affect_valence or 0.0                    │   │
│   │     novelty_score = event.salience_score or 0.0  # Proxy            │   │
│   │     participant_count = event.participant_count or 1                │   │
│   │     content_type = event.content_type or "message"                  │   │
│   │     intent_label = event.intent_label or ""                         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                      │                                      │
│                                      ▼                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ 4b. Compute Emotional Intensity                                     │   │
│   │     emotional = sentiment_weight × |sentiment_score|                │   │
│   │               + affect_weight × |affect_valence|                    │   │
│   │     # Result: [0.0, ~0.55]                                          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                      │                                      │
│                                      ▼                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ 4c. Compute Novelty Factor                                          │   │
│   │     novelty = novelty_weight × clamp(novelty_score, 0.0, 1.0)       │   │
│   │     # Result: [0.0, 0.25]                                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                      │                                      │
│                                      ▼                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ 4d. Compute Social Factor                                           │   │
│   │     if participant_count <= 1: social = 0.0                         │   │
│   │     else:                                                           │   │
│   │       log_factor = min(1.0, log₂(participant_count) / 3.32)         │   │
│   │       social = social_weight × log_factor                           │   │
│   │     # Result: [0.0, 0.20]                                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                      │                                      │
│                                      ▼                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ 4e. Sum Base Components                                             │   │
│   │     base_importance = emotional + novelty + social                  │   │
│   │     # Result: [0.0, ~1.0]                                           │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                      │                                      │
│                                      ▼                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ 4f. Apply Event Type Multiplier                                     │   │
│   │     multiplier = EVENT_TYPE_MULTIPLIERS.get(content_type, 1.0)      │   │
│   │     raw_score = base_importance × multiplier                        │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                      │                                      │
│                                      ▼                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ 4g. Apply Intent Boost                                              │   │
│   │     intent_boost = INTENT_BOOST_MULTIPLIERS.get(intent_label, 1.0)  │   │
│   │     if intent_boost != 1.0:                                         │   │
│   │       raw_score *= intent_boost                                     │   │
│   │       multiplier *= intent_boost  # Track combined multiplier       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                      │                                      │
│                                      ▼                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ 4h. Clamp Final Score                                               │   │
│   │     final_score = max(0.0, min(1.0, raw_score))                     │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                      │                                      │
│                                      ▼                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ 4i. Create ImportanceBreakdown                                      │   │
│   │     breakdown = ImportanceBreakdown(                                │   │
│   │       emotional_component=emotional,                                │   │
│   │       novelty_component=novelty,                                    │   │
│   │       social_component=social,                                      │   │
│   │       multiplier=multiplier,                                        │   │
│   │       final_score=final_score,                                      │   │
│   │       weights_source=_weights_source,                               │   │
│   │     )                                                               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                      │                                      │
│                                      ▼                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ 4j. Update Event State                                              │   │
│   │     event.set_importance(                                           │   │
│   │       score=final_score,                                            │   │
│   │       recency=0.0,                                                  │   │
│   │       affect=breakdown.emotional_component,                         │   │
│   │       social=breakdown.social_component,                            │   │
│   │       novelty=breakdown.novelty_component,                          │   │
│   │     )                                                               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                      │                                      │
│                                      ▼                                      │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │ 4k. Audit Logging (with sampling)                                   │   │
│   │     if random() < sample_rate:                                      │   │
│   │       priority_tier = get_priority_tier(final_score)                │   │
│   │       audit_logger.log_decision(                                    │   │
│   │         memory_id=event_id,                                         │   │
│   │         source_table="st_hipp_events",                              │   │
│   │         action=AuditAction.SCORE,                                   │   │
│   │         formula_used="importance_scorer",                           │   │
│   │         formula_version="1.0.0",                                    │   │
│   │         inputs={sentiment, affect, novelty, participants, ...},     │   │
│   │         outputs={score, emotional, novelty, social, tier, ...},     │   │
│   │         confidence=final_score,                                     │   │
│   │       )                                                             │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│   END FOR                                                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 5: Collect Results                                                     │
│   • Create ScoredEvent for each scored event                                │
│   • Store in envelope.phases.r1_scored_events                               │
│   • Store audit records in envelope.phases.r1_audit_records                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 6: Calculate Statistics                                                │
│   • avg_score = sum(scores) / len(scores)                                   │
│   • max_score = max(scores)                                                 │
│   • min_score = min(scores)                                                 │
│   • critical_count = count where score >= 0.80                              │
│   • high_count = count where 0.50 <= score < 0.80                           │
│   • medium_count = count where 0.30 <= score < 0.50                         │
│   • low_count = count where score < 0.30                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STEP 7: Return P03PhaseResult                                               │
│   return P03PhaseResult.done(                                               │
│     phase_id=P03PhaseId.R1_SCORE,                                           │
│     duration_ms=execution_time,                                             │
│     outputs_summary={                                                       │
│       "events_scored": len(scored_events),                                  │
│       "audit_records": audit_logger.record_count(),                         │
│       "avg_importance": avg_score,                                          │
│       "critical_count": critical_count,                                     │
│       "high_count": high_count,                                             │
│       "weights_source": scorer._weights_source,                             │
│     },                                                                      │
│     idempotency_key="p03:r1:{cycle_id}",                                    │
│   )                                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
                    ┌─────────────────────────────────────┐
                    │  Proceed to R2 (Episode Clustering)  │
                    └─────────────────────────────────────┘
```

### Data Flow Diagram

```
┌────────────────────────────────────────────────────────────────────────────┐
│                                  INPUT                                      │
├────────────────────────────────────────────────────────────────────────────┤
│  P03BatchEnvelope                                                          │
│  ├── context                                                               │
│  │   ├── cycle_id: str (ULID)                                              │
│  │   ├── batch_id: str                                                     │
│  │   ├── space_id: str                                                     │
│  │   └── tenant_id: str                                                    │
│  │                                                                         │
│  ├── events: List[P03EventState]                                           │
│  │   ├── event_id: str                                                     │
│  │   ├── sentiment_score: float [-1, 1]                                    │
│  │   ├── affect_valence: float [-1, 1]                                     │
│  │   ├── salience_score: float [0, 1]                                      │
│  │   ├── participant_count: int                                            │
│  │   ├── content_type: str                                                 │
│  │   └── intent_label: str                                                 │
│  │                                                                         │
│  └── phases: P03PhaseOutputs (empty R1 section)                            │
└────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      │  R1ImportanceScorer.run()
                                      │
                                      ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                                 OUTPUT                                      │
├────────────────────────────────────────────────────────────────────────────┤
│  P03BatchEnvelope (enriched)                                               │
│  ├── context (unchanged)                                                   │
│  │                                                                         │
│  ├── events: List[P03EventState] (importance fields populated)             │
│  │   ├── importance_score: float [0, 1]                                    │
│  │   ├── recency_factor: float (0.0)                                       │
│  │   ├── affect_factor: float                                              │
│  │   ├── social_factor: float                                              │
│  │   ├── novelty_factor: float                                             │
│  │   └── importance_computed: bool (True)                                  │
│  │                                                                         │
│  ├── phases: P03PhaseOutputs                                               │
│  │   ├── r1_scored_events: List[ScoredEvent]                               │
│  │   │   ├── event_id                                                      │
│  │   │   ├── importance_score                                              │
│  │   │   ├── recency_factor                                                │
│  │   │   ├── affect_factor                                                 │
│  │   │   ├── social_factor                                                 │
│  │   │   └── novelty_factor                                                │
│  │   │                                                                     │
│  │   └── r1_audit_records: List[AuditRecord]                               │
│  │       ├── audit_id                                                      │
│  │       ├── memory_id                                                     │
│  │       ├── action: SCORE                                                 │
│  │       ├── inputs_json                                                   │
│  │       ├── outputs_json                                                  │
│  │       └── explanation                                                   │
│  │                                                                         │
│  └── observability: P03ObservabilityContext (metrics updated)              │
│                                                                            │
│  + P03PhaseResult                                                          │
│    ├── phase_id: R1_SCORE                                                  │
│    ├── status: DONE                                                        │
│    ├── duration_ms: int                                                    │
│    ├── outputs_summary: Dict                                               │
│    └── idempotency_key: "p03:r1:{cycle_id}"                                │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## Configuration

### R1Config Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `audit_sample_rate` | `float` | `1.0` | Fraction of events to audit [0.0, 1.0]. Use 1.0 for debug, 0.1 for production. |
| `enable_hebbian` | `bool` | `False` | Enable Hebbian learning (not yet implemented) |
| `min_samples_for_learned_weights` | `int` | `500` | Minimum samples before using learned weights |
| `importance_weights` | `ImportanceWeights` | `None` | Custom weights (uses defaults if None) |

### Pipeline Config Keys

```python
ctx.get_config("p03.importance.audit_sample_rate", default=1.0)
```

---

## Metrics & Observability

### Prometheus Metrics

| Metric Name | Type | Description |
|-------------|------|-------------|
| `p03_importance_score_distribution` | Histogram | Distribution of importance scores |
| `p03_importance_weight_emotional` | Gauge | Emotional weight value |
| `p03_importance_weight_recency` | Gauge | Recency weight value |
| `p03_importance_weight_access` | Gauge | Access weight value |
| `p03_importance_weight_social` | Gauge | Social weight value |
| `p03_importance_weight_sample_count` | Gauge | Number of training samples |
| `p03_r1_duration_ms` | Histogram | R1 phase duration |

### Performance Thresholds

| Threshold | Value | Action |
|-----------|-------|--------|
| Warning | 10,000 ms | Log warning |
| Error | 18,000 ms | R1 must complete in <5% of cycle time |

### Log Fields

```json
{
  "cycle_id": "01HXYZ...",
  "tenant_id": "t_123",
  "space_id": "sp_456",
  "event_count": 50,
  "events_scored": 50,
  "audit_records": 50,
  "avg_score": 0.456,
  "max_score": 0.892,
  "min_score": 0.123,
  "critical_count": 5,
  "high_count": 12,
  "medium_count": 18,
  "low_count": 15,
  "weights_source": "static",
  "duration_ms": 234
}
```

---

## Error Handling

### Skip Conditions

| Condition | Result |
|-----------|--------|
| Empty event list | `P03PhaseResult.skip("No unscored events in batch")` |
| All events already scored | `P03PhaseResult.skip("No unscored events in batch")` |

### Error Recovery

| Error Type | Strategy | Max Retries |
|------------|----------|-------------|
| `P08_UNAVAILABLE` | Use cached embeddings | 1 |
| `EMBEDDING_TIMEOUT` | Skip event, log | 0 |
| General exceptions | Create `P03Error`, return `P03PhaseResult.fail()` | 3 |

### P03Error Structure

```python
P03Error.create(
    phase="R1",
    stage_id="importance_scorer",
    error_type="R1_SCORING_ERROR",
    error_message=str(e),
    recoverable=True,  # R1 failures are retriable
)
```

---

## Usage Examples

### Basic Usage

```python
from k0.pipelines.p03.phases.r1_importance_scorer import (
    R1ImportanceScorer,
    R1Config,
    create_r1_phase,
)

# Create phase with default config
r1_phase = create_r1_phase()

# Or with custom config
config = R1Config(
    audit_sample_rate=0.1,  # 10% sampling for production
    enable_hebbian=False,
)
r1_phase = R1ImportanceScorer(config=config)

# Run phase
result = await r1_phase.run(envelope, ctx)

if result.is_success:
    print(f"Scored {result.outputs_summary['events_scored']} events")
    print(f"Average importance: {result.outputs_summary['avg_importance']}")
elif result.is_skipped:
    print(f"Skipped: {result.skip_reason}")
else:
    print(f"Failed: {result.error_info.error_message}")
```

### Direct Scorer Usage

```python
from k0.modules.consolidation.algorithms.importance_scorer import (
    ImportanceScorer,
    ImportanceWeights,
)

# Create scorer
scorer = ImportanceScorer(
    space_id="sp_123",
    weight_store=my_weight_store,  # Optional
)

# Score a batch
results = await scorer.score_batch(events)

for result in results:
    print(f"Event {result['event_id']}: {result['importance_score']:.3f}")

# With audit logging
from k0.pipelines.p03.audit_logger import P03AuditLogger

audit_logger = P03AuditLogger(
    space_id="sp_123",
    tenant_id="t_1",
    cycle_id="cyc_abc",
)

results = await scorer.score_batch_with_audit(
    events=events,
    audit_logger=audit_logger,
    sample_rate=1.0,
)

# Get audit records for database write
audit_rows = audit_logger.get_pending_db_rows()
```

### Custom Weights

```python
from k0.modules.consolidation.algorithms.importance_scorer import ImportanceWeights

# Create custom weights (must sum to 1.0)
custom_weights = ImportanceWeights(
    sentiment_weight=0.20,
    affect_weight=0.35,
    novelty_weight=0.30,
    social_weight=0.15,
)

config = R1Config(importance_weights=custom_weights)
r1_phase = R1ImportanceScorer(config=config)
```

---

## Related Documentation

- **Spec**: `docs/pipelines/P03_consolidation_dossier_v2.md` Appendix C.2.1
- **Issue**: `docs/TEMP_EXECUTION_DOCS/M4_EXECUTION.md` Issues 4.1.1-4.1.2
- **Phase Interface**: `k0/pipelines/p03/phase_interface.py`
- **Runner Contract**: `k0/pipelines/p03/runner_contract.py`
- **R0 Batch Selector**: `docs/pipelines/R0_BATCH_SELECTOR_DEEP_DIVE.md`

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-01-28 | Initial documentation |
