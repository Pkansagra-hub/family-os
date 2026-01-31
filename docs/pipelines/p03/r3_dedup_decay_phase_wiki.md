# R3 Dedup/Decay Phase Wiki

> **Phase ID:** `P03PhaseId.R3_PRUNE`
> **Issue Reference:** 4.3.12
> **Spec Reference:** Dossier §4.3, M4_EXECUTION.md
> **Primary File:** `k0/pipelines/p03/phases/r3_dedup_decay.py`

---

## Table of Contents

1. [Phase Overview](#1-phase-overview)
2. [Sub-Phase Architecture](#2-sub-phase-architecture)
3. [API Reference](#3-api-reference)
4. [Data Structures](#4-data-structures)
5. [Algorithms](#5-algorithms)
6. [Dependencies](#6-dependencies)
7. [Configuration](#7-configuration)
8. [End-to-End Process Flow](#8-end-to-end-process-flow)
9. [Metrics & Statistics](#9-metrics--statistics)
10. [Scientific References](#10-scientific-references)

---

## 1. Phase Overview

### Purpose

The R3 Dedup/Decay phase is the **third phase** in the P03 Consolidation Pipeline. It orchestrates:

1. **Duplicate Detection** — SimHash + embedding-based deduplication
2. **Novelty Scoring** — Adaptive bonuses for unique/milestone events
3. **Decay Computation** — Exponential decay per Ebbinghaus forgetting curve
4. **Retention Decisions** — KEEP/ARCHIVE/TOMBSTONE evaluation
5. **Immunity Checking** — Protect core identity facts from decay
6. **Audit Logging** — GDPR Article 22 compliance
7. **Access Tracking** — Per-entity λ learning
8. **Regret Detection** — Detect queries for pruned entities
9. **Scale Optimization** — Auto-switch strategies at high volume
10. **Reconciliation** — Truth layer reconciliation (Issue 4.3.13)

### Position in Pipeline

```
R0 (Selector) → R1 (Importance) → R2 (Episodic) → **R3 (Dedup/Decay)** → R4 (KG) → R5 (Granger) → R6 (Staging) → R7 (Truth Writer) → R8 (Event Emitter)
```

### Key Responsibilities

| Sub-Phase | Issue | Responsibility |
|-----------|-------|----------------|
| R3.1 | 4.3.1, 4.3.2 | Duplicate Detection (SimHash, Two-Stage) |
| R3.2 | 4.3.7, 4.3.8 | Novelty Scoring (DuplicateDetector, AdaptiveNoveltyBonusLearner) |
| R3.3 | 4.3.3 | Decay Computation (UnifiedDecayEngine) |
| R3.4 | 4.3.4, 4.3.9 | Retention Evaluation (RetentionEnforcer, ImmunityChecker) |
| R3.5 | 4.3.10 | Audit Logging (PruneAuditLogger) |
| R3.6 | 4.3.5 | Access Tracking (AccessTracker, BayesianLambdaEstimator) |
| R3.7 | 4.3.6 | Regret Detection (PruneRegretDetector, PrunedEntityTracker) |
| R3.8 | 4.3.11 | Scale Optimization (MinHashLSH, AdaptiveDeduplicationStrategy) |
| R3.9 | 4.3.13 | Reconciliation (ReconciliationEngine) |

---

## 2. Sub-Phase Architecture

### R3.1: Duplicate Detection

**Components:**

- `SimHasher` — 64-bit locality-sensitive hashing (Charikar 2002)
- `TwoStageDeduplicator` — SimHash + embedding verification pipeline

**Purpose:** Fast O(n) duplicate detection with semantic verification.

### R3.2: Novelty Scoring

**Components:**

- `DuplicateDetector` — M19 SimHash-based deduplication with novelty
- `AdaptiveNoveltyBonusLearner` — Per-space bonus learning from feedback

**Purpose:** Calculate novelty scores with bonuses/penalties.

### R3.3: Decay Computation

**Components:**

- `UnifiedDecayEngine` — Exponential decay for all 8 memory tables

**Purpose:** Compute decay_factor per Ebbinghaus forgetting curve.

### R3.4: Retention Evaluation

**Components:**

- `RetentionEnforcer` — KEEP/ARCHIVE/TOMBSTONE decisions
- `ImmunityChecker` — Two-level immunity (entity/attribute)

**Purpose:** Evaluate retention and protect core identity facts.

### R3.5: Audit Logging

**Components:**

- `PruneAuditLogger` — GDPR-compliant decision logging

**Purpose:** Record all prune/archive/tombstone decisions.

### R3.6: Access Tracking

**Components:**

- `AccessTracker` — Track access patterns
- `BayesianLambdaEstimator` — Per-entity λ learning

**Purpose:** Learn per-entity decay rates from access patterns.

### R3.7: Regret Detection

**Components:**

- `PrunedEntityTracker` — Track pruned entities for 14 days
- `PruneRegretDetector` — Match queries against pruned entities

**Purpose:** Detect when pruned data is later queried.

### R3.8: Scale Optimization

**Components:**

- `MinHashLSH` — Sub-linear O(log n) deduplication
- `AdaptiveDeduplicationStrategy` — Auto-switch based on volume

**Purpose:** Maintain performance at scale (>50K events).

### R3.9: Reconciliation

**Components:**

- `ReconciliationEngine` — Truth layer reconciliation decisions

**Purpose:** Determine REINFORCE/EXTEND/CREATE/EVOLVE/CONTRADICT actions.

---

## 3. API Reference

### Main Class: `R3DedupDecay`

**Location:** `k0/pipelines/p03/phases/r3_dedup_decay.py`

#### Constructor

```python
def __init__(
    self,
    config: Optional[R3Config] = None,
) -> None
```

**Parameters:**

- `config`: R3 phase configuration (uses defaults if None)

#### Phase Interface Methods

##### `phase_id()`

```python
def phase_id(self) -> P03PhaseId
```

**Returns:** `P03PhaseId.R3_PRUNE`

##### `should_skip(envelope)`

```python
def should_skip(self, envelope: "P03BatchEnvelope") -> bool
```

**Returns:** `True` if no events or no R2 clusters exist.

##### `run(envelope, ctx)`

```python
async def run(
    self,
    envelope: "P03BatchEnvelope",
    ctx: "P03RunnerContext",
) -> P03PhaseResult
```

**Input:**

- `envelope`: Batch envelope with events from R2
- `ctx`: Runner context with syscalls, logger, config

**Output:**

- `P03PhaseResult` with:
  - `status`: `DONE` or `SKIP`
  - `duration_ms`: Execution time
  - `outputs_summary`: Stats dict

#### R3.1: Duplicate Detection

##### `detect_duplicate(event, existing_events, ...)`

```python
async def detect_duplicate(
    self,
    event: Any,
    existing_events: List[Any],
    space_id: str = "",
    event_hour: Optional[int] = None,
    activity_type: Optional[str] = None,
) -> DuplicationResult
```

**Input:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `event` | EventStateProtocol | Event to check |
| `existing_events` | List[EventStateProtocol] | Events to compare against |
| `space_id` | str | Space ID for activity history |
| `event_hour` | Optional[int] | Hour of day (0-23) |
| `activity_type` | Optional[str] | Activity type string |

**Output:**

```python
@dataclass
class DuplicationResult:
    event_id: str
    is_duplicate: bool = False
    near_duplicates: List[str] = field(default_factory=list)
    novelty_score: float = 0.5
    duplicate_of: Optional[str] = None
    match_method: str = ""  # 'SIMHASH', 'EMBEDDING', 'TWO_STAGE'
    max_similarity: float = 0.0
    bonuses: NoveltyBonuses = field(default_factory=NoveltyBonuses)
```

##### `process_events(events, existing_events, space_id, stores)`

```python
async def process_events(
    self,
    events: List[Any],
    existing_events: List[Any],
    space_id: str,
    stores: R3Stores,
) -> List[DuplicationResult]
```

**Input:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `events` | List[Any] | New events to process |
| `existing_events` | List[Any] | Existing events in window |
| `space_id` | str | Space ID |
| `stores` | R3Stores | Storage backends |

**Output:** List of `DuplicationResult` for each event.

#### R3.2: Novelty Scoring

##### `process_novelty_feedback(signal_type, space_id, stores)`

```python
async def process_novelty_feedback(
    self,
    signal_type: str,
    space_id: str,
    stores: R3Stores,
) -> Optional[BonusAdjustment]
```

**Input:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `signal_type` | str | Feedback signal type |
| `space_id` | str | Space ID |
| `stores` | R3Stores | Storage backends |

**Output:**

```python
@dataclass
class BonusAdjustment:
    bonus_type: NoveltyBonusType
    old_value: float
    new_value: float
    adjustment: float
    signal_type: str
    clamped: bool
```

#### R3.3: Decay Computation

##### `compute_decay(table_name, last_observed_at, current_time, ...)`

```python
def compute_decay(
    self,
    table_name: str,
    last_observed_at: int,
    current_time: int,
    importance_score: float = 0.0,
    confidence_score: float = 0.0,
    observation_count: int = 1,
) -> tuple[float, DecayClassification]
```

**Input:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `table_name` | str | Source table (st_epi, st_sem, etc.) |
| `last_observed_at` | int | Last access timestamp (epoch ms) |
| `current_time` | int | Current timestamp (epoch ms) |
| `importance_score` | float | Importance [0, 1] |
| `confidence_score` | float | Confidence [0, 1] |
| `observation_count` | int | Number of observations |

**Output:**

- `decay_factor`: float in [0.0, 1.0]
- `classification`: `DecayClassification.ACTIVE | ARCHIVE_CANDIDATE | PRUNE_CANDIDATE`

#### R3.4: Retention Evaluation

##### `check_immunity(entity_type, entity_attributes)`

```python
def check_immunity(
    self,
    entity_type: str,
    entity_attributes: Dict[str, Any],
) -> ImmunityResult
```

**Input:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `entity_type` | str | Entity type (PERSON, FAMILY_MEMBER, etc.) |
| `entity_attributes` | Dict[str, Any] | Entity attributes |

**Output:**

```python
@dataclass(frozen=True)
class ImmunityResult:
    is_immune: bool
    level: ImmunityLevel  # NONE | ATTRIBUTE | ENTITY
    reason: str
    protected_attributes: tuple[str, ...]
```

##### `evaluate_retention(...)`

```python
def evaluate_retention(
    self,
    entity_id: str,
    table_name: str,
    last_observed_at: int,
    current_time: int,
    current_status: str = "ACTIVE",
    importance_score: float = 0.0,
    confidence_score: float = 0.0,
    observation_count: int = 1,
) -> RetentionResult
```

**Output:**

```python
@dataclass
class RetentionResult:
    entity_id: str
    table_name: str
    current_decay: float
    classification: DecayClassification
    decision: RetentionDecision  # KEEP | ARCHIVE | TOMBSTONE
    reason: str
    days_since_access: float = 0.0
    importance_score: float = 0.0
```

##### `resurrect_entity(...)`

```python
def resurrect_entity(
    self,
    entity_id: str,
    table_name: str,
    current_decay: float,
    current_status: str,
    trigger: ResurrectionTrigger,
    current_time: Optional[int] = None,
) -> ResurrectionResult
```

**Output:**

```python
@dataclass
class ResurrectionResult:
    entity_id: str
    table_name: str
    trigger: ResurrectionTrigger
    old_decay: float
    new_decay: float
    old_status: str
    new_status: str = "ACTIVE"
    resurrected_at: int = 0
    resurrection_count: int = 1
```

#### R3.5: Audit Logging

##### `log_prune_decision(...)`

```python
async def log_prune_decision(
    self,
    action: PruneAction,
    context: PruneDecisionContext,
    space_id: str,
    tenant_id: str,
    cycle_id: str,
    stores: R3Stores,
) -> Optional[str]
```

**Output:** `audit_id` if logged, `None` if sampled out.

#### R3.6: Access Tracking

##### `record_access(...)`

```python
async def record_access(
    self,
    entity_id: str,
    entity_table: str,
    accessed_at_ms: int,
    stores: R3Stores,
) -> AccessStats
```

**Output:**

```python
@dataclass
class AccessStats:
    entity_id: str
    entity_table: str = ""
    access_count: int = 0
    first_access_at: int = 0  # ms
    last_access_at: int = 0  # ms
    access_intervals_ms: List[int] = field(default_factory=list)
    spread_days: float = 0.0
    eligible_for_learning: bool = False
```

##### `estimate_and_persist_lambda(...)`

```python
async def estimate_and_persist_lambda(
    self,
    stats: AccessStats,
    space_id: str,
    stores: R3Stores,
) -> Optional[LambdaEstimate]
```

**Output:**

```python
@dataclass
class LambdaEstimate:
    entity_id: str
    entity_table: str
    lambda_value: float
    confidence: float
    sample_count: int
    half_life_days: float = 0.0
```

#### R3.7: Regret Detection

##### `track_pruned_entity(...)`

```python
async def track_pruned_entity(
    self,
    entity_id: str,
    entity_type: str,
    canonical_name: str,
    embedding: Any,  # np.ndarray
    space_id: str,
    layer_table: str,
    decay_factor: float,
    lambda_value: float,
    pruned_at: int,
    stores: R3Stores,
) -> str  # prune_id
```

##### `check_query_regret(...)`

```python
async def check_query_regret(
    self,
    query_embedding: Any,  # np.ndarray
    space_id: str,
    query_id: str,
    stores: R3Stores,
) -> List[RegretMatch]
```

**Output:**

```python
@dataclass
class RegretMatch:
    prune_id: str
    entity_id: str
    entity_type: str
    match_type: MatchType  # STRONG_MATCH | LIKELY_MATCH | SEMANTIC_MATCH | NO_MATCH
    match_confidence: float
    query_id: str
    pruned_at: int
    matched_at: int
    canonical_name: str = ""
    layer_table: str = ""
```

#### R3.9: Reconciliation

##### `reconcile_event(...)`

```python
async def reconcile_event(
    self,
    event: Any,  # P03EventState
    space_id: str,
    tenant_id: str,
) -> Optional[ReconciliationDecision]
```

**Output:**

```python
@dataclass
class ReconciliationDecision:
    action: ReconciliationAction  # REINFORCE | EXTEND | CREATE | EVOLVE | CONTRADICT | SKIP | PRUNE
    best_match_id: Optional[str]
    best_match_layer: Optional[str]
    similarity_score: float
    confidence: float
    reason: str
    candidates_evaluated: int
    decision_time_ms: float = 0.0
```

#### Full Phase Execution

##### `execute(...)`

```python
async def execute(
    self,
    events: List[Any],
    existing_events: List[Any],
    entities_for_decay: List[Dict[str, Any]],
    space_id: str,
    tenant_id: str,
    cycle_id: str,
    current_time: int,
    stores: R3Stores,
) -> R3PhaseStats
```

**Input:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `events` | List[Any] | New events to process |
| `existing_events` | List[Any] | Existing events in window |
| `entities_for_decay` | List[Dict] | Entities to evaluate for decay |
| `space_id` | str | Space ID |
| `tenant_id` | str | Tenant ID |
| `cycle_id` | str | Consolidation cycle ID |
| `current_time` | int | Current timestamp (epoch ms) |
| `stores` | R3Stores | R3 storage backends |

**Output:** `R3PhaseStats` (see Section 9).

---

## 4. Data Structures

### R3Config

```python
@dataclass
class R3Config:
    decay_config: Optional[DecayConfig] = None
    access_config: Optional[AccessTrackerConfig] = None
    novelty_config: Optional[NoveltyBonusConfig] = None
    regret_config: Optional[PruneRegretConfig] = None
    dedup_config: Optional[DuplicateDetectorConfig] = None
    immunity_config: Optional[ImmunityCheckerConfig] = None
    audit_config: Optional[PruneAuditLoggerConfig] = None
    minhash_config: Optional[MinHashConfig] = None
    adaptive_config: Optional[AdaptiveStrategyConfig] = None
    reconciliation_config: Optional[ReconciliationConfig] = None
    enable_reconciliation: bool = True
    is_debug: bool = False
```

### R3Stores

```python
@dataclass
class R3Stores:
    access_store: AccessStoreProtocol
    pruned_entity_store: PrunedEntityStoreProtocol
    learned_weights_store: LearnedWeightsStoreProtocol
    audit_store: AuditStoreProtocol

    @classmethod
    def create_in_memory(cls) -> "R3Stores":
        """Create in-memory stores for testing."""
```

### DecayClassification

```python
class DecayClassification(Enum):
    ACTIVE = "ACTIVE"                     # decay_factor >= 0.10
    ARCHIVE_CANDIDATE = "ARCHIVE_CANDIDATE"  # 0.01 <= decay_factor < 0.10
    PRUNE_CANDIDATE = "PRUNE_CANDIDATE"      # decay_factor < 0.01
```

### RetentionDecision

```python
class RetentionDecision(Enum):
    KEEP = "KEEP"           # Record is healthy
    ARCHIVE = "ARCHIVE"     # Move to archive tier
    TOMBSTONE = "TOMBSTONE" # Mark for deletion
```

### ResurrectionTrigger

```python
class ResurrectionTrigger(Enum):
    EXPLICIT_ACCESS = "EXPLICIT_ACCESS"
    ASSOCIATION_HIT = "ASSOCIATION_HIT"
    SEARCH_RESULT = "SEARCH_RESULT"
    CONSOLIDATION_RESCUE = "CONSOLIDATION_RESCUE"
```

### ImmunityLevel

```python
class ImmunityLevel(Enum):
    NONE = "none"           # Standard decay applies
    ATTRIBUTE = "attribute" # Specific attributes protected
    ENTITY = "entity"       # Entire entity protected
```

### PruneAction

```python
class PruneAction(Enum):
    ARCHIVE = "ARCHIVE"     # decay_factor < 0.10
    TOMBSTONE = "TOMBSTONE" # decay_factor < 0.01
    PRUNE = "PRUNE"         # Explicit prune
    SKIP = "SKIP"           # Retained
```

### DuplicateDecision

```python
class DuplicateDecision(Enum):
    DUPLICATE = "DUPLICATE"               # >= 0.85 similarity
    LIKELY_DUPLICATE = "LIKELY_DUPLICATE" # 0.70-0.85 similarity
    NOT_DUPLICATE = "NOT_DUPLICATE"       # < 0.70 similarity
    SEMANTIC_DUPLICATE = "SEMANTIC_DUPLICATE"  # Caught by embedding fallback
    DISTINCT = "DISTINCT"                 # Different content
```

### MatchType (Regret Detection)

```python
class MatchType(Enum):
    STRONG_MATCH = "STRONG_MATCH"     # cosine >= 0.90
    LIKELY_MATCH = "LIKELY_MATCH"     # cosine >= 0.85
    SEMANTIC_MATCH = "SEMANTIC_MATCH" # cosine >= 0.80
    NO_MATCH = "NO_MATCH"             # cosine < 0.80
```

### DeduplicationStrategy

```python
class DeduplicationStrategy(Enum):
    SIMHASH_PAIRWISE = "simhash_pairwise"   # < 10K events
    SIMHASH_BUCKETING = "simhash_bucketing" # 10K-50K events
    MINHASH_LSH = "minhash_lsh"             # > 50K events
```

### ReconciliationAction

```python
class ReconciliationAction(Enum):
    REINFORCE = "REINFORCE"   # >= 0.85: Strengthen existing truth
    EXTEND = "EXTEND"         # 0.60-0.84: Add detail to existing
    CREATE = "CREATE"         # No match found
    EVOLVE = "EVOLVE"         # 0.40-0.59: Related but distinct
    CONTRADICT = "CONTRADICT" # < 0.40: Potential contradiction
    SKIP = "SKIP"             # is_duplicate=True
    PRUNE = "PRUNE"           # prune_decision=TOMBSTONE
```

---

## 5. Algorithms

### Algorithm 1: SimHash (64-bit LSH)

**File:** `k0/modules/consolidation/algorithms/simhasher.py`
**Issue:** 4.3.1
**Scientific Basis:** Charikar (2002) — Similarity estimation using random projections

#### Formula

```
SimHash Algorithm:
1. Tokenize text into 3-gram shingles
2. For each shingle:
   hash = MD5(shingle)[:16]  → 64-bit value
   For each bit position i:
     if hash[i] = 1: bit_sums[i] += 1
     else:           bit_sums[i] -= 1
3. Final SimHash:
   For each bit position i:
     if bit_sums[i] > 0: simhash[i] = 1
     else:               simhash[i] = 0
```

#### Per-Content-Type Hamming Thresholds

| Content Type | Threshold | Rationale |
|--------------|-----------|-----------|
| `TRANSACTION` | 1 | Financial exactness required |
| `CALENDAR_EVENT` | 2 | Structured, small variations matter |
| `CONTACT_UPDATE` | 2 | Names/phones must match closely |
| `CHAT_MESSAGE` | 3 | Default, mixed content |
| `PHOTO_CAPTION` | 4 | Free-form, allow paraphrasing |
| `JOURNAL_ENTRY` | 4 | Personal text, subjective |
| `VOICE_MEMO` | 5 | ASR transcription has inherent noise |

### Algorithm 2: Two-Stage Deduplication

**File:** `k0/modules/consolidation/algorithms/two_stage_dedup.py`
**Issue:** 4.3.2
**Spec:** Dossier Appendix C.4.1.2

#### Problem Statement

SimHash alone has limitations:

- **False Positives:** "I ate pizza" vs "I hate pizza" (Hamming = 2, but opposite meaning)
- **False Negatives:** "Had pizza for dinner" vs "Ate pizza tonight" (Hamming > 3, but semantically identical)

#### Solution

```
Stage 1: SimHash Filter (Fast O(n))
  → Find candidates with Hamming distance <= threshold
  → Eliminates 99%+ non-candidates

Stage 2: Embedding Verification (Accurate)
  → Compute cosine similarity between embeddings
  → Confirm true duplicates

Thresholds:
  similarity >= 0.85: DUPLICATE
  similarity >= 0.70: LIKELY_DUPLICATE
  similarity <  0.70: NOT_DUPLICATE

Fallback: Embedding-only check (catches paraphrases SimHash missed)
  similarity >= 0.90: SEMANTIC_DUPLICATE
```

#### Performance Comparison

| Method | Complexity | Precision | Recall | Best For |
|--------|------------|-----------|--------|----------|
| SimHash only | O(n) | 0.85 | 0.90 | Fast, syntactic |
| Embedding | O(n²) | 0.95 | 0.98 | Accurate, slow |
| **Two-stage** | O(n + k) | 0.93 | 0.95 | **Balanced** |

Where k ~ 0.01n (candidates from Stage 1).

### Algorithm 3: Novelty Score Formula

**File:** `k0/modules/consolidation/algorithms/duplicate_detector.py`
**Issue:** 4.3.7
**Spec:** Dossier §7.4.2

#### Formula

```
novelty = base_novelty
          × (1 + first_occurrence_bonus)
          × (1 + milestone_bonus)
          × (1 + rare_pattern_bonus)
          × (1 + temporal_anomaly_bonus)
          × (1 - routine_penalty)

Where:
  base_novelty = 1.0 - max_similarity
```

#### Bonus/Penalty Values

| Bonus Type | Default Value | Trigger Condition |
|------------|---------------|-------------------|
| `first_occurrence` | 0.15 | Activity type not seen before |
| `milestone` | 0.20 | Keywords: birthday, wedding, graduation, etc. |
| `rare_pattern` | 0.10 | Activity appears < 5 times in 90 days |
| `temporal_anomaly` | 0.10 | Unusual time-of-day for activity |
| `routine_penalty` | 0.30 | Pattern key in routine_patterns set |

#### Milestone Keywords

```python
MILESTONE_KEYWORDS = frozenset({
    "birthday", "anniversary", "graduation", "wedding",
    "promotion", "retirement", "birth", "death",
    "engaged", "engagement", "married", "divorce",
    "funeral", "memorial"
})
```

### Algorithm 4: Adaptive Novelty Bonus Learning

**File:** `k0/modules/consolidation/algorithms/novelty_bonus_learner.py`
**Issue:** 4.3.8
**Spec:** Dossier §4.4.2.1

#### Adjustment Formula

```
new_bonus = old_bonus + adjustment
new_bonus = clamp(new_bonus, 0.05, 0.30)
```

#### Signal-to-Adjustment Mapping

| Signal Type | Adjustment | Affected Bonus |
|-------------|------------|----------------|
| `NOVEL_EVENT_GROUNDED` | +0.01 | first_occurrence |
| `NOVEL_EVENT_NEVER_QUERIED` | -0.02 | first_occurrence |
| `USER_SAYS_NOT_NEW` | -0.03 | first_occurrence |
| `MILESTONE_GROUNDED` | +0.01 | milestone |
| `RARE_PATTERN_USEFUL` | +0.01 | rare_pattern |

### Algorithm 5: Exponential Decay (Ebbinghaus)

**File:** `k0/modules/consolidation/algorithms/decay_engine.py`
**Issue:** 4.3.3
**Scientific Basis:** Ebbinghaus (1885), Tononi & Cirelli (2006)

#### Core Formula

```
decay_factor = exp(-λ_effective × days_since_last_observed)
```

#### Effective Lambda Calculation

```
λ_effective = λ_base
              × space_modifier
              × entity_type_modifier
              × importance_factor
              × confidence_factor
              × reinforcement_factor

Where:
  importance_factor = 1.0 - (importance_score × 0.5)
  confidence_factor = 1.0 - (confidence_score × 0.3)
  reinforcement_factor = 1.0 / (1.0 + 0.1 × observation_count)
```

#### Per-Layer Lambda Values

| Table | Base λ | Half-Life (days) | Rationale |
|-------|--------|------------------|-----------|
| `st_hipp_events` | 0.100 | ~7 | Short-term buffer |
| `st_prospective` | 0.020 | ~35 | Plans/Goals |
| `st_procedural` | 0.010 | ~69 | Habits/Routines |
| `st_kg_edges` | 0.008 | ~87 | Associations |
| `st_epi` | 0.005 | ~139 | Episodic Memory |
| `st_sem` | 0.003 | ~231 | Semantic Memory |
| `st_social` | 0.002 | ~347 | Social Memory |
| `st_kg_dom` | 0.001 | ~693 | Concepts |

**Half-life Formula:** `t_half = ln(2) / λ ≈ 0.693 / λ`

#### Decay Classification Thresholds

```
decay_factor >= 0.10: ACTIVE
0.01 <= decay_factor < 0.10: ARCHIVE_CANDIDATE
decay_factor < 0.01: PRUNE_CANDIDATE
```

### Algorithm 6: Resurrection Formula

**File:** `k0/modules/consolidation/algorithms/retention_enforcer.py`
**Issue:** 4.3.4
**Scientific Basis:** Bjork & Bjork (1992) — Retrieval strengthens memories

#### Formula

```
new_decay = max(0.70, 0.50 + old_decay × 0.50)
```

**Constants:**

- `RESURRECTION_FLOOR = 0.70` — Minimum decay after resurrection
- `RESURRECTION_BASE = 0.50` — Base decay boost
- `RESURRECTION_CARRY = 0.50` — Fraction of old decay preserved

**Alert Threshold:** Log warning after 3+ resurrections per entity.

### Algorithm 7: Immunity Ontology

**File:** `k0/modules/consolidation/algorithms/immunity_checker.py`
**Issue:** 4.3.9
**Spec:** Dossier §4.4.3.1

#### Two-Level Immunity System

**Level 1: Entity-Level Immunity**

- `FAMILY_MEMBER` → Entire entity is immune (all attributes)

**Level 2: Attribute-Level Immunity**

| Entity Type | Protected Attributes |
|-------------|---------------------|
| `PERSON` | birthday, name, relationship_to_user |
| `PLACE` | home_address, work_address |
| `EVENT` | wedding_date, birth_date, death_date |
| `ORGANIZATION` | employer, school |
| `CONCEPT` | core_value, religion, political_affiliation |

**Rationale:** We don't forget our own birthday, family members' names, or where we live.

### Algorithm 8: Bayesian Lambda Estimation

**File:** `k0/modules/consolidation/algorithms/access_tracker.py`
**Issue:** 4.3.5

#### MLE Formula for Exponential Distribution

```
λ_MLE = n / Σ(intervals)

Where:
  n = number of inter-access intervals
  intervals = time between successive accesses (in days)
```

#### Eligibility Requirements

- Minimum 5 accesses
- Minimum 7-day spread between first and last access
- Maximum 10 intervals stored per entity

#### Lambda Bounds

```
LAMBDA_MIN = 0.0001  # ~6931 day half-life
LAMBDA_MAX = 0.1     # ~7 day half-life
```

#### Confidence Calculation

| Sample Count | Confidence |
|--------------|------------|
| ≤ 4 | 0.50 |
| 5-6 | 0.50-0.65 |
| 7-8 | 0.65-0.75 |
| 9-10 | 0.75-0.85 |
| 11-15 | 0.85-0.95 |
| > 15 | 0.95 |

### Algorithm 9: Prune Regret Detection

**File:** `k0/modules/consolidation/algorithms/prune_regret_detector.py`
**Issue:** 4.3.6
**Spec:** Dossier §4.4.2

#### Match Classification

```
cosine_similarity >= 0.90: STRONG_MATCH (regret detected)
cosine_similarity >= 0.85: LIKELY_MATCH (regret detected)
cosine_similarity >= 0.80: SEMANTIC_MATCH (logged, not regret)
cosine_similarity <  0.80: NO_MATCH
```

#### Retention Periods

- **Unmatched entities:** 14 days (weekly + biweekly patterns)
- **Matched entities (regrets):** 30 days (for analysis)

#### Scientific Basis

- Weekly patterns: Users may query data on 7-day cycles
- Biweekly patterns: Payday reminders (14-day cycle)
- 90% of regrets occur within 14 days (empirical observation)

### Algorithm 10: MinHash LSH

**File:** `k0/modules/consolidation/algorithms/minhash_lsh.py`
**Issue:** 4.3.11
**Scientific Basis:** Broder (1997) — Near-duplicate detection using MinHash

#### Problem: O(n²) Scaling

| Event Count | Latency per Event |
|-------------|-------------------|
| 10K | ~10ms (acceptable) |
| 50K | ~50ms (slow) |
| 100K+ | >100ms (unacceptable) |

#### Solution: Sub-linear O(log n)

**Parameters:**

- `num_hashes = 128` — Total hash functions
- `num_bands = 32` — LSH bands
- `rows_per_band = 4` — Rows per band
- `similarity_threshold = 0.85` — Jaccard threshold

#### Auto-Switch Thresholds

| Event Count | Strategy |
|-------------|----------|
| < 10,000 | SimHash pairwise O(n) |
| 10K-50K | SimHash bucketing O(n/b) |
| > 50,000 | MinHash LSH O(log n) |

#### LSH Probability Formula

```
P(at least 1 band match) = 1 - (1 - s^r)^b

Where:
  s = Jaccard similarity
  r = rows_per_band
  b = num_bands
```

### Algorithm 11: Audit Sampling

**File:** `k0/modules/consolidation/algorithms/prune_audit_logger.py`
**Issue:** 4.3.10
**Spec:** Dossier §1.4.7

#### Sampling Rates

| Action | Production | Debug |
|--------|------------|-------|
| `TOMBSTONE` | **100%** (always logged) | 100% |
| `ARCHIVE` | 10% | 100% |
| `PRUNE` | 10% | 100% |
| `SKIP` | 10% | 100% |

**Rationale:** TOMBSTONE is permanent deletion and requires full audit trail for GDPR compliance.

### Algorithm 12: Reconciliation Thresholds

**File:** `k0/modules/consolidation/algorithms/reconciliation_engine.py`
**Issue:** 4.3.13
**Spec:** Dossier §4.3.2, Appendix C.1

#### Threshold Mapping

```
similarity >= 0.85: REINFORCE (strengthen existing truth)
0.60 <= similarity < 0.85: EXTEND (add detail to existing)
0.40 <= similarity < 0.60: EVOLVE (related but distinct)
similarity < 0.40 + has_match: CONTRADICT
similarity < 0.40 + no match: CREATE

Overrides:
  is_duplicate=True → SKIP
  prune_decision=TOMBSTONE → PRUNE
```

#### Confidence Computation (Bayesian)

```
confidence = prior + (evidence_weight × evidence_factor)

Where:
  prior = 0.5
  evidence_weight = 0.3
```

---

## 6. Dependencies

### Algorithm Files (12 Files)

| File | Issue | Primary Class |
|------|-------|---------------|
| `simhasher.py` | 4.3.1 | `SimHasher` |
| `two_stage_dedup.py` | 4.3.2 | `TwoStageDeduplicator` |
| `decay_engine.py` | 4.3.3 | `UnifiedDecayEngine` |
| `retention_enforcer.py` | 4.3.4 | `RetentionEnforcer` |
| `access_tracker.py` | 4.3.5 | `AccessTracker`, `BayesianLambdaEstimator` |
| `prune_regret_detector.py` | 4.3.6 | `PruneRegretDetector`, `PrunedEntityTracker` |
| `duplicate_detector.py` | 4.3.7 | `DuplicateDetector` |
| `novelty_bonus_learner.py` | 4.3.8 | `AdaptiveNoveltyBonusLearner` |
| `immunity_checker.py` | 4.3.9 | `ImmunityChecker` |
| `prune_audit_logger.py` | 4.3.10 | `PruneAuditLogger` |
| `minhash_lsh.py` | 4.3.11 | `MinHashLSH`, `AdaptiveDeduplicationStrategy` |
| `reconciliation_engine.py` | 4.3.13 | `ReconciliationEngine` |

### External Dependencies

| Module | Usage |
|--------|-------|
| `numpy` | Vector operations, cosine similarity |
| `hashlib` | MD5/SHA256 for hashing |
| `uuid` | Audit ID generation |
| `asyncio` | Async operations, timeout handling |

### Internal Dependencies

| Module | Usage |
|--------|-------|
| `k0.pipelines.p03.phase_interface` | `P03PhaseId`, `P03PhaseResult` |
| `k0.pipelines.p03.event_state` | `P03EventState`, `ReconciliationAction` |
| `k0.modules.consolidation.staging.truth_query_service` | `TruthQueryService` |
| `k0.db.pool` | Database pool for truth queries |

---

## 7. Configuration

### DecayConfig

```python
@dataclass(frozen=True)
class DecayConfig:
    base_lambda: float = 0.01
    importance_modifier: float = 0.5   # High importance → slower decay
    confidence_modifier: float = 0.3   # High confidence → slower decay
    archive_threshold: float = 0.10    # ACTIVE → ARCHIVE_CANDIDATE
    tombstone_threshold: float = 0.01  # ARCHIVE_CANDIDATE → PRUNE_CANDIDATE
```

### AccessTrackerConfig

```python
@dataclass(frozen=True)
class AccessTrackerConfig:
    min_access_count: int = 5        # Min accesses before learning λ
    min_spread_days: float = 7       # Min spread between first and last access
    max_intervals_stored: int = 10   # Max intervals to store per entity
    lambda_min: float = 0.0001       # Minimum λ
    lambda_max: float = 0.1          # Maximum λ
```

### DuplicateDetectorConfig

```python
@dataclass
class DuplicateDetectorConfig:
    first_occurrence_bonus: float = 0.15
    milestone_bonus: float = 0.20
    rare_pattern_bonus: float = 0.10
    temporal_anomaly_bonus: float = 0.10
    routine_penalty: float = 0.30
    hamming_threshold: int = 3
    exact_duplicate_similarity: float = 0.95
    near_duplicate_similarity: float = 0.85
```

### PruneRegretConfig

```python
@dataclass
class PruneRegretConfig:
    unmatched_retention_days: int = 14
    matched_retention_days: int = 30
    strong_threshold: float = 0.90
    likely_threshold: float = 0.85
    semantic_threshold: float = 0.80
    cleanup_hour: int = 2  # 2am
    max_storage_mb: int = 50
```

### ImmunityCheckerConfig

```python
@dataclass
class ImmunityCheckerConfig:
    enabled: bool = True
    family_member_immune: bool = True
    milestone_events_immune: bool = True
```

### PruneAuditLoggerConfig

```python
@dataclass
class PruneAuditLoggerConfig:
    enabled: bool = True
    sample_rate_production: float = 0.10  # 10%
    sample_rate_debug: float = 1.0        # 100%
    is_debug: bool = False
    retention_days: int = 90
    formula_name: str = "UnifiedDecayFormula"
    formula_version: str = "1.0"
```

### MinHashConfig

```python
@dataclass
class MinHashConfig:
    num_hashes: int = 128
    num_bands: int = 32
    similarity_threshold: float = 0.85
    hash_seed: int = 42
    enabled: bool = False  # Feature flag for safe rollout
```

### AdaptiveStrategyConfig

```python
@dataclass
class AdaptiveStrategyConfig:
    pairwise_threshold: int = 10_000   # Switch to bucketing above this
    bucketing_threshold: int = 50_000  # Switch to LSH above this
    lsh_enabled: bool = False          # Feature flag
```

### ReconciliationConfig

```python
@dataclass
class ReconciliationConfig:
    reinforce_threshold: float = 0.85
    extend_threshold: float = 0.60
    evolve_threshold: float = 0.40
    candidate_top_k: int = 10
    min_candidate_similarity: float = 0.35
    prior_confidence: float = 0.5
    evidence_weight: float = 0.3
    truth_layers: Tuple[str, ...] = ("st_epi", "st_sem", "st_procedural", "st_social", "st_prospective")
    enable_batch_mode: bool = True
    query_timeout_seconds: float = 5.0
```

---

## 8. End-to-End Process Flow

### Phase Execution Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    R3DedupDecay.run()                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
           ┌──────────────────────────────────────┐
           │   1. Skip Check                       │
           │   - No events? → SKIP                 │
           │   - No R2 clusters? → SKIP            │
           └──────────────────────────────────────┘
                              │
                              ▼
           ┌──────────────────────────────────────┐
           │   2. Create In-Memory Stores          │
           │   - R3Stores.create_in_memory()       │
           └──────────────────────────────────────┘
                              │
                              ▼
           ┌──────────────────────────────────────┐
           │   3. Initialize TruthQueryService     │
           │   (Lazy, if reconciliation enabled)   │
           └──────────────────────────────────────┘
                              │
                              ▼
           ┌──────────────────────────────────────┐
           │   4. Query Entities for Decay         │
           │   - TruthQueryService.query_entities  │
           │   - max_decay_factor=0.99             │
           │   - limit_per_layer=100               │
           └──────────────────────────────────────┘
                              │
                              ▼
           ┌──────────────────────────────────────┐
           │   5. Execute Full R3 Phase            │
           │   → R3DedupDecay.execute()            │
           └──────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ R3.1: Dedup  │     │ R3.3: Decay  │     │ R3.9: Recon  │
│ process_events│     │ evaluate_batch│    │ reconcile    │
│              │     │              │     │              │
│ For each:    │     │ For each:    │     │ For each:    │
│ - SimHash    │     │ - compute_   │     │ - query truth│
│ - Two-stage  │     │   decay      │     │ - find match │
│ - Novelty    │     │ - classify   │     │ - apply      │
│   score      │     │ - decide     │     │   thresholds │
└──────────────┘     └──────────────┘     └──────────────┘
        │                     │                     │
        ▼                     ▼                     ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ DuplicationResult │ │ RetentionResult │ │ ReconciliationDecision │
│ - is_duplicate│   │ - decision   │     │ - action     │
│ - novelty_score│  │ - decay      │     │ - match_id   │
│ - near_duplicates││ - classification│  │ - similarity │
└──────────────┘     └──────────────┘     └──────────────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              ▼
           ┌──────────────────────────────────────┐
           │   6. Update Envelope Events           │
           │   - event.novelty_score = ...         │
           │   - event.is_duplicate = ...          │
           │   - event.set_reconciliation(...)     │
           └──────────────────────────────────────┘
                              │
                              ▼
           ┌──────────────────────────────────────┐
           │   7. Store Dedup Results in Envelope  │
           │   envelope.phases.r3_dedup_results    │
           └──────────────────────────────────────┘
                              │
                              ▼
           ┌──────────────────────────────────────┐
           │   8. Return P03PhaseResult.done()     │
           │   - duration_ms                       │
           │   - outputs_summary                   │
           └──────────────────────────────────────┘
```

### Detailed Step-by-Step

1. **Skip Check**
   - If `envelope.events` is empty → Return `P03PhaseResult.skip()`
   - If `envelope.phases.r2_clusters` is empty → Return `P03PhaseResult.skip()`

2. **Create In-Memory Stores**
   - Create `R3Stores` with in-memory backends for:
     - `access_store` (AccessTracker)
     - `pruned_entity_store` (PruneRegretDetector)
     - `learned_weights_store` (NoveltyBonusLearner)
     - `audit_store` (PruneAuditLogger)

3. **Initialize TruthQueryService**
   - If `enable_reconciliation=True` and not initialized:
     - Get database pool via `k0.db.pool.get_pool()`
     - Create `TruthQueryService(pool=pool)`
     - Connect to `ReconciliationEngine`

4. **Query Entities for Decay**
   - Call `TruthQueryService.query_entities_for_decay()`
   - Filter: `decay_factor < 0.99` (any started decaying)
   - Limit: 100 per layer to avoid overload

5. **Execute Full R3 Phase** (`execute()`)

   **5.1 R3.1: Process Events for Deduplication**
   - Update adaptive strategy based on event count
   - For each event:
     - Get activity_type (prefer UltraBERT 12-type)
     - Call `detect_duplicate()` → `DuplicationResult`
     - Track seen categories
     - Index in LSH if using MINHASH_LSH strategy

   **5.2 R3.4: Evaluate Entities for Retention**
   - Call `evaluate_retention_batch()` → `BatchRetentionResult`
   - For each result:
     - Check immunity via `check_immunity()`
     - Count by classification (ACTIVE, ARCHIVE_CANDIDATE, PRUNE_CANDIDATE)
     - Log audit record via `log_retention_decision()`

   **5.3 R3.9: Reconciliation**
   - If `enable_reconciliation=True`:
     - Call `reconcile_batch()` → `Dict[event_id, ReconciliationDecision]`
     - Update stats by action type

6. **Update Envelope Events**
   - For each event, set:
     - `novelty_score`
     - `is_duplicate`
     - `duplicate_of_id`
     - `near_duplicates_json`
     - `hamming_distance`
     - Reconciliation fields via `set_reconciliation()`

7. **Store Results in Envelope**
   - `envelope.phases.r3_dedup_results = stats.dedup_results`

8. **Return Result**
   - Return `P03PhaseResult.done()` with:
     - `phase_id=P03PhaseId.R3_PRUNE`
     - `duration_ms`
     - `outputs_summary` dict

---

## 9. Metrics & Statistics

### R3PhaseStats

```python
@dataclass
class R3PhaseStats:
    # Duplicate detection
    events_processed: int = 0
    duplicates_found: int = 0
    near_duplicates_found: int = 0
    distinct_events: int = 0
    dedup_results: Dict[str, DuplicationResult] = field(default_factory=dict)

    # Novelty scoring
    avg_novelty_score: float = 0.0
    high_novelty_count: int = 0   # novelty >= 0.7
    low_novelty_count: int = 0    # novelty < 0.3

    # Decay
    entities_evaluated: int = 0
    active_count: int = 0
    archive_candidate_count: int = 0
    prune_candidate_count: int = 0

    # Retention
    keep_count: int = 0
    archive_count: int = 0
    tombstone_count: int = 0

    # Immunity
    immune_count: int = 0
    immune_by_entity: int = 0
    immune_by_attribute: int = 0

    # Audit
    decisions_logged: int = 0
    decisions_sampled_out: int = 0

    # Access tracking
    accesses_recorded: int = 0
    lambda_estimates_created: int = 0

    # Regret detection
    regrets_detected: int = 0
    strong_matches: int = 0
    likely_matches: int = 0

    # Scale optimization
    current_strategy: str = "simhash_pairwise"
    strategy_switches: int = 0
    lsh_queries: int = 0

    # Reconciliation (Issue 4.3.13)
    reconciliation_enabled: bool = False
    reconciliation_count: int = 0
    reinforce_count: int = 0
    extend_count: int = 0
    create_count: int = 0
    evolve_count: int = 0
    contradict_count: int = 0
    skip_count: int = 0
    prune_count: int = 0

    # Timing
    total_duration_ms: float = 0.0
```

### Prometheus Metrics (from Dossier)

| Metric | Type | Description |
|--------|------|-------------|
| `p03_r3_duplicates_found` | Counter | Total duplicates detected |
| `p03_r3_novelty_score` | Histogram | Novelty score distribution |
| `p03_r3_decay_factor` | Histogram | Decay factor distribution |
| `p03_r3_retention_decision` | Counter | Retention decisions by type |
| `p03_r3_immune_entities` | Gauge | Immune entities by level |
| `p03_r3_audit_logged` | Counter | Audit records logged |
| `p03_r3_regrets_detected` | Counter | Prune regrets detected |
| `p03_dedup_strategy_active` | Gauge | Current dedup strategy |
| `p03_lsh_index_size` | Gauge | Events in LSH index |
| `p03_reconciliation_action` | Counter | Reconciliation actions by type |

---

## 10. Scientific References

### Memory & Forgetting

1. **Ebbinghaus, H. (1885)**
   *Über das Gedächtnis: Untersuchungen zur experimentellen Psychologie*
   Foundation for exponential forgetting curve

2. **Tononi, G., & Cirelli, C. (2006)**
   *Sleep function and synaptic homeostasis*
   Sleep clears weak synapses, strengthens important ones

3. **Bjork, R. A., & Bjork, E. L. (1992)**
   *A new theory of disuse and an old theory of stimulus fluctuation*
   Retrieval strengthens memories (resurrection mechanism)

### Similarity & Hashing

1. **Charikar, M. S. (2002)**
   *Similarity estimation techniques from rounding algorithms*
   SimHash locality-sensitive hashing

2. **Broder, A. Z. (1997)**
   *On the resemblance and containment of documents*
   MinHash for near-duplicate detection

3. **Mikolov, T., et al. (2013)**
   *Distributed representations of words and phrases and their compositionality*
   Cosine similarity for semantic relatedness

### Memory Systems

1. **Tulving, E. (1983)**
   *Elements of Episodic Memory*
   Episodic vs semantic memory distinction

2. **McGaugh, J. L. (2004)**
   *The amygdala modulates the consolidation of memories of emotionally arousing experiences*
   Emotional enhancement of memory consolidation

---

## Appendix: Component Properties (for Testing)

The `R3DedupDecay` class exposes all internal components as properties:

```python
@property
def simhasher(self) -> SimHasher

@property
def two_stage_dedup(self) -> TwoStageDeduplicator

@property
def decay_engine(self) -> UnifiedDecayEngine

@property
def retention_enforcer(self) -> RetentionEnforcer

@property
def access_tracker(self) -> AccessTracker

@property
def regret_detector(self) -> PruneRegretDetector

@property
def duplicate_detector(self) -> DuplicateDetector

@property
def novelty_learner(self) -> AdaptiveNoveltyBonusLearner

@property
def immunity_checker(self) -> ImmunityChecker

@property
def audit_logger(self) -> PruneAuditLogger

@property
def minhash_lsh(self) -> MinHashLSH

@property
def adaptive_strategy(self) -> AdaptiveDeduplicationStrategy

@property
def reconciliation_engine(self) -> Optional[ReconciliationEngine]

@property
def truth_query_service(self) -> Optional[TruthQueryService]
```

---

## Appendix: Factory Function

```python
def create_r3_phase(config: Optional[R3Config] = None) -> R3DedupDecay:
    """
    Factory function to create R3 phase.

    By default, creates R3 with reconciliation enabled (Issue 4.3.13).

    Args:
        config: Optional configuration. If None, uses defaults with
                reconciliation enabled.

    Returns:
        Configured R3DedupDecay instance
    """
    return R3DedupDecay(config=config)
```

---

*Generated from source code analysis of `k0/pipelines/p03/phases/r3_dedup_decay.py` and 12 algorithm dependency files.*
