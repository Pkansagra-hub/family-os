# P03 Milestone 4 Execution Document

> **Milestone**: M4 — Implement R1–R4 Core Cognition
> **Status**: NOT_STARTED
> **Started**: YYYY-MM-DD
> **Completed**: YYYY-MM-DD
> **Prerequisites**: M3 COMPLETED (2026-01-01)
> **Branch**: `postgre-sql-migration`
> **Baseline Commit**: TBD (after M3 completion)

---

## Part A: Context Foundation (BEFORE YOU START)

### A.0 M0/M1/M2/M3 Outputs — EXISTING INFRASTRUCTURE AUDIT

> **CRITICAL**: M4 builds on completed infrastructure from M0-M3.
> M4 implements the **core cognition algorithms** (R1-R4 phases).

**M0-M3 Deliverables M4 Depends On**:

| Milestone | Key Artifacts | M4 Usage |
|-----------|---------------|----------|
| M0 | Pipeline ADR, Contracts, Event Schemas | Algorithm contracts |
| M1 | P03BatchEnvelope, P03EventState, P03PhaseOutputs, P03SequentialRunner | Phase execution framework |
| M2 | 18 migrations (st_epi, st_sem, st_kg_*, st_learned_weights, etc.) | Storage for algorithm outputs |
| M3 | R7/R8 phases, Outbox integration, Gap emitter, Feedback consumer | Downstream wiring |

**M3 Test Count**: 899 tests passing

### A.1 Dossier Sections Governing This Milestone

| Section | Title | Link | Why Needed |
|---------|-------|------|------------|
| §4.2 | R1 — Hippocampal Replay (NREM1) | [Dossier §4.2](../pipelines/P03_consolidation_dossier_v2.md#42-r1--hippocampal-replay-nrem1) | Importance scoring, Hebbian learning |
| §4.2.2 | Importance Scoring Algorithm | [Dossier §4.2.2](../pipelines/P03_consolidation_dossier_v2.md#422-importance-scoring-algorithm) | Formula, weights |
| §4.2.3 | Association Strengthening (Hebbian) | [Dossier §4.2.3](../pipelines/P03_consolidation_dossier_v2.md#423-association-strengthening-hebbian-learning) | Edge weight updates |
| §4.3 | R2 — Neocortical Integration (NREM2) | [Dossier §4.3](../pipelines/P03_consolidation_dossier_v2.md#43-r2--neocortical-integration-nrem2) | DBSCAN clustering |
| §4.3.1 | Episodic Clustering | [Dossier §4.3.1](../pipelines/P03_consolidation_dossier_v2.md#431-episodic-clustering) | Composite distance, adaptive params |
| §4.4 | R3 — Synaptic Homeostasis (SWS) | [Dossier §4.4](../pipelines/P03_consolidation_dossier_v2.md#44-r3--synaptic-homeostasis-sws) | Decay, dedup, novelty |
| §4.4.1 | Unified Decay Architecture | [Dossier §4.4.1](../pipelines/P03_consolidation_dossier_v2.md#441-unified-decay-architecture) | Per-layer lambda |
| §4.5 | R4 — KG Consolidation | [Dossier §4.5](../pipelines/P03_consolidation_dossier_v2.md#45-r4--knowledge-graph-consolidation) | Entity resolution, causality |
| Appendix C.2 | Importance & Hebbian Algorithms | [Dossier Appendix C.2](../pipelines/P03_consolidation_dossier_v2.md#appendix-c-algorithm-specifications) | R1 implementation |
| Appendix C.3 | DBSCAN & Clustering Algorithms | [Dossier Appendix C.3](../pipelines/P03_consolidation_dossier_v2.md#appendix-c-algorithm-specifications) | R2 implementation |
| Appendix C.4 | SimHash & Decay Algorithms | [Dossier Appendix C.4](../pipelines/P03_consolidation_dossier_v2.md#appendix-c-algorithm-specifications) | R3 implementation |
| Appendix C.5 | Entity & Causality Algorithms | [Dossier Appendix C.5](../pipelines/P03_consolidation_dossier_v2.md#appendix-c-algorithm-specifications) | R4 implementation |
| §7.4.2-7.4.4 | Module Specs (M18-M21, M23) | [Dossier §7.4](../pipelines/P03_consolidation_dossier_v2.md#74-module-registry) | Module contracts |

### A.2 ADRs to Reference

| ADR | Path | Governs |
|-----|------|---------|
| K010 | [k010-p03-consolidation-architecture.md](../architecture/decisions-K0/pipelines/k010-p03-consolidation-architecture.md) | P03 pipeline architecture |
| K010.1 | [k010.1-sleep-cycle-state-machine.md](../architecture/decisions-K0/pipelines/k010.1-sleep-cycle-state-machine.md) | R0-R8 state machine |
| K010.2 | [k010.2-importance-scoring-formula.md](../architecture/decisions-K0/pipelines/k010.2-importance-scoring-formula.md) | R1 importance formula (TBD) |
| K010.3 | [k010.3-episodic-clustering-algorithm.md](../architecture/decisions-K0/pipelines/k010.3-episodic-clustering-algorithm.md) | R2 DBSCAN (TBD) |
| K010.5 | [k010.5-simhash-deduplication.md](../architecture/decisions-K0/pipelines/k010.5-simhash-deduplication.md) | R3 SimHash (TBD) |
| K010.6 | [k010.6-entity-normalization-strategy.md](../architecture/decisions-K0/pipelines/k010.6-entity-normalization-strategy.md) | R4 Entity resolution (TBD) |

### A.3 Existing Code Patterns to Reference

| Pattern | Path | What to Learn |
|---------|------|---------------|
| P03EventState | `k0/pipelines/p03/event_state.py` | ReconciliationAction, PruneDecision enums |
| P03PhaseOutputs | `k0/pipelines/p03/phase_outputs.py` | R1-R4 output dataclasses |
| P03StagedWrites | `k0/pipelines/p03/staged_writes.py` | Staging pattern for R7 |
| P03PhaseProtocol | `k0/pipelines/p03/phase_interface.py` | Phase implementation contract |
| R7TruthWriter | `k0/pipelines/p03/phases/r7_truth_writer.py` | Phase implementation example |
| P03DecisionAuditLogger | `k0/pipelines/p03/audit_logger.py` | Audit logging pattern |

### A.4 Governance Sync Tool

| Tool | Command |
|------|---------|
| Sync Script | `python -m governance.k0.scripts.sync --report` |

### A.5 Architectural Decision: Module Restructure

> **Date**: 2026-01-02
> **Decision**: Consolidation algorithms go in `k0/modules/consolidation/`, NOT `k0/pipelines/p03/`

**Rationale**:

The P03 folder was becoming a hybrid of pipeline orchestration + domain logic. This violates the K0 architecture:

| Concern | Belongs In | Examples |
|---------|-----------|----------|
| **Orchestration** | `pipelines/p03/` | runners, phases, checkpoints, offsets |
| **Domain Logic** | `modules/consolidation/` | algorithms, data models, state |

**New Structure**:

```text
k0/modules/consolidation/          # NEW - domain logic
├── __init__.py
├── algorithms/                    # ALL M4 algorithms
│   ├── importance_scorer.py       # 4.1.1
│   ├── hebbian_learner.py         # 4.1.3
│   ├── composite_distance.py      # 4.2.1
│   ├── episode_splitter.py        # 4.2.2
│   ├── episodic_dbscan.py         # 4.2.3
│   ├── simhasher.py               # 4.3.1
│   ├── decay_engine.py            # 4.3.3
│   └── ...
└── (future: event_state.py, envelope.py migrated from pipelines)

k0/pipelines/p03/                  # Orchestration only
├── phases/                        # Import from modules.consolidation
│   ├── r0_batch_selector.py
│   ├── r1_replay_coordinator.py
│   └── ...
├── sequential_runner.py
├── checkpoint.py
└── ...
```

**Benefits**:

- Algorithms reusable by P06 (Learning), P19 (Observability), K1
- No circular imports between pipelines
- Clean separation of concerns
- Future migration of `event_state.py`, `envelope.py` after M4

**Import Pattern**:

```python
# In k0/pipelines/p03/phases/r1_replay_coordinator.py
from k0.modules.consolidation.algorithms import ImportanceScorer, HebbianLearner

# In k0/pipelines/p03/phases/r3_dedup_decay.py
from k0.modules.consolidation.algorithms import SimHasher, UnifiedDecayEngine
```

**Migration Plan**:

| Phase | Scope | When |
|-------|-------|------|
| Phase 1 | Create `modules/consolidation/` structure | **Done** (2026-01-02) |
| Phase 2 | Write all M4 algorithms in new location | **M4 execution** |
| Phase 3 | Migrate `event_state.py`, `envelope.py`, etc. | **Post-M4** |

---

## Part B: Code Discovery Results

> **Populated during code discovery phase before Epic execution**

### B.1 Existing Algorithm Infrastructure

| Component | Path | Status | M4 Usage |
|-----------|------|--------|----------|
| `P03EventState` | `k0/pipelines/p03/event_state.py` (531 lines) | EXISTS | R1 fields: `importance_score`, `recency_factor`, `affect_factor`, `social_factor`, `novelty_factor`, `importance_computed`, `hebbian_updates` |
| `P03EventState.set_importance()` | `k0/pipelines/p03/event_state.py:265-295` | EXISTS | Helper method for Issue 4.1.1 — sets all importance fields in one call |
| `P03EventState.add_hebbian_update()` | `k0/pipelines/p03/event_state.py:297-320` | EXISTS | Helper method for Issue 4.1.3 — appends to `hebbian_updates` list |
| `ScoredEvent` dataclass | `k0/pipelines/p03/phase_outputs.py:25-42` | EXISTS | R1 output type: `event_id`, `importance_score`, `recency_factor`, `affect_factor`, `social_factor`, `novelty_factor` |
| `HebbianEdgeUpdate` dataclass | `k0/pipelines/p03/phase_outputs.py:45-65` | EXISTS | R1 output type: `source_entity_id`, `target_entity_id`, `old_weight`, `new_weight`, `delta`, `update_type` |
| `P03PhaseProtocol` | `k0/pipelines/p03/phase_interface.py:85-115` | EXISTS | Phase interface: `phase_id` property, `run()` async method, `should_skip()` method |
| `P03PhaseResult` | `k0/pipelines/p03/phase_interface.py:25-65` | EXISTS | Factory methods: `.done()`, `.skip()`, `.fail()` with `phase_id`, `duration_ms`, `outputs` |
| `P03RunnerContext` | `k0/pipelines/p03/phase_interface.py:68-82` | EXISTS | Context: `syscalls`, `logger`, `qos_band`, `priority`, `deadline_ms`, `config`, `dry_run` |
| `R0BatchSelector` | `k0/pipelines/p03/phases/r0_batch_selector.py` (501 lines) | EXISTS | Pattern for R1 phase implementation |
| `P03AuditLogger` | `k0/pipelines/p03/audit_logger.py` (441 lines) | EXISTS | Pattern for Issue 4.1.2 — `log_decision()` method, `AuditAction` enum, `AuditRecord` dataclass |
| `AuditAction` enum | `k0/pipelines/p03/audit_logger.py:35-48` | EXISTS | 9 actions: REINFORCE, DECAY, ARCHIVE, MERGE, CREATE, EXTEND, PRUNE, SKIP, CONTRADICT |

### B.2 Dossier Algorithm Specifications (Grounded)

| Algorithm | Dossier Location | Key Formulas / Methods |
|-----------|------------------|------------------------|
| ImportanceScorer | Appendix C.2.1 (lines 19817-20500) | `compute_emotional_intensity()`, `compute_social_factor()`, `compute_importance_score()`, `select_batch()` |
| ImportanceWeightLearner | Appendix C.2.1.1 (lines 20540-20700) | Online gradient descent, `min_samples=500`, `momentum=0.9`, `learning_rate=0.01` |
| Stability Controls | Appendix C.2.1.2 (lines 20780-20900) | Weight clamping `[0.05, 0.60]`, drift monitoring, 3-night rollback |
| HebbianLearner | Appendix C.2.2 (lines 20900-21100) | `extract_cooccurrences()`, `update_edge_weight()`, `apply_decay()`, `process_batch()` |
| Anti-Hebbian Decay | Appendix C.2.2.1 (lines 21100+) | Conflict signals: `ENTITY_MERGE_REJECTED` → -0.2 penalty |

### B.3 ImportanceScorer Algorithm Details (from Dossier Appendix C.2.1)

**Inputs** (from HippEvent):

- `sentiment_score`: float [-1, 1]
- `affect_valence`: float [-1, 1]
- `novelty_score`: float [0, 1]
- `participant_count`: int
- `event_type`: str (message, photo, milestone, routine)

**Static Weights** (fallback when `sample_count < 500`):

- `sentiment_weight = 0.25`
- `affect_weight = 0.30`
- `novelty_weight = 0.25`
- `social_weight = 0.20`

**Event Type Multipliers**:

- `message = 1.0`
- `photo = 1.2`
- `milestone = 2.0`
- `routine = 0.5`

**Core Methods**:

```python
def compute_emotional_intensity(self, event) -> float:
    sentiment_intensity = abs(event.sentiment_score)
    affect_intensity = abs(event.affect_valence)
    return sentiment_intensity * weights.sentiment_weight + affect_intensity * weights.affect_weight

def compute_social_factor(self, event) -> float:
    if event.participant_count <= 1:
        return 0.0
    return min(1.0, math.log2(event.participant_count) / 3.32)  # 3.32 = log2(10)

def compute_importance_score(self, event) -> float:
    emotional = self.compute_emotional_intensity(event)
    novelty = event.novelty_score * weights.novelty_weight
    social = self.compute_social_factor(event) * weights.social_weight
    base_importance = emotional + novelty + social
    multiplier = event_type_multipliers.get(event.event_type, 1.0)
    return min(1.0, max(0.0, base_importance * multiplier))
```

**Outputs**:

- `importance_score`: float [0.0, 1.0] → stored in `st_hipp_events.importance_score`
- `component_breakdown`: Dict for audit (`emotional_component`, `novelty_component`, `social_component`)

**Importance Thresholds** (for batch prioritization):

| Score Range | Priority | Processing Behavior |
|-------------|----------|---------------------|
| 0.80 - 1.00 | CRITICAL | Process immediately, never skip |
| 0.50 - 0.79 | HIGH | Process in current cycle |
| 0.30 - 0.49 | MEDIUM | Process if capacity allows |
| 0.00 - 0.29 | LOW | May be deferred, candidate for pruning |

### B.4 HebbianLearner Algorithm Details (from Dossier Appendix C.2.2)

**Inputs**:

- `event_batch`: List[HippEvent] — current batch being processed
- `existing_edges`: List[KGEdge] from `st_kg_edges` (source_id, target_id, relation_type, weight, count)
- `config`: HebbianConfig
  - `learning_rate = 0.1`
  - `decay_rate = 0.01` (per day)
  - `max_weight = 1.0`
  - `min_weight = 0.01` (below this, edge is pruned)

**Co-occurrence Extraction** (per event):

- Actor-Actor pairs → relation_type `INTERACTS_WITH`
- Actor-Location pairs → relation_type `FREQUENTS`
- Actor-Topic pairs → relation_type `DISCUSSES`

**Weight Update Formula**:

```python
def update_edge_weight(self, current_weight, current_count, event_importance) -> Tuple[float, int]:
    delta = self.config.learning_rate * (self.config.max_weight - current_weight) * event_importance
    new_weight = current_weight + delta
    new_count = current_count + 1
    return (min(self.config.max_weight, new_weight), new_count)
```

**Decay Formula**:

```python
def apply_decay(self, edges, days_since_update) -> List[KGEdge]:
    decay_factor = math.exp(-self.config.decay_rate * days_since_update)
    new_weight = edge.weight * decay_factor
    if new_weight < self.config.min_weight:
        # Edge pruned (not returned)
```

**Outputs**:

- `edge_updates`: Dict[EdgeKey, EdgeUpdate] → batch UPDATE to `st_kg_edges`
- `new_edges`: List[KGEdge] → INSERT to `st_kg_edges` with initial weight
- `pruned_edges`: List[EdgeKey] → soft-delete (tombstone)

**Edge Weight Interpretation**:

| Weight Range | Relationship Strength | Example |
|--------------|----------------------|---------|
| 0.80 - 1.00 | Very Strong | Best friends, family members |
| 0.50 - 0.79 | Strong | Regular colleagues, close friends |
| 0.20 - 0.49 | Moderate | Acquaintances, occasional contacts |
| 0.01 - 0.19 | Weak | One-time interactions |

### B.5 Storage Tables for M4

| Table | Purpose | Migration | Status |
|-------|---------|-----------|--------|
| st_hipp_events | Source events | 0022+0034 | EXISTS |
| st_vec | Embeddings (768-dim) | 0025 | EXISTS |
| st_epi | Episodic clusters (R2 output) | 0027 | EXISTS |
| st_sem | Semantic patterns | 0028 | EXISTS |
| st_kg_dom | KG entities (R4 output) | 0032 | EXISTS |
| st_kg_edges | KG relationships (R1 Hebbian, R4 causal) | 0033 | EXISTS |
| st_learned_weights | Adaptive parameters | 0040 | EXISTS |
| st_consolidation_audit | Decision audit trail | 0036 | EXISTS |
| st_learning_queue | Gap queue (R4 ambiguous entities) | 0037 | EXISTS |

### B.3 External Dependencies

| Dependency | Purpose | Version |
|------------|---------|---------|
| scikit-learn | DBSCAN, silhouette score | TBD |
| numpy | Vector operations | TBD |
| simhash | SimHash fingerprinting | TBD (or custom) |

---

## Part C: Scope Boundaries

### C.1 What M4 DOES (40 Issues)

| Epic | Phase | Focus | Issues |
|------|-------|-------|--------|
| 4.1 | R1 | Importance scoring + Hebbian learning | 8 |
| 4.2 | R2 | DBSCAN clustering + adaptive params | 8 |
| 4.3 | R3 | SimHash dedup + decay + novelty | 12 |
| 4.4 | R4 | Entity resolution + KG + causality | 12 |

### C.2 What M4 Does NOT Do (Deferred)

| Item | Deferred To | Reason |
|------|-------------|--------|
| R5 Dream phase | M8 | Counterfactual/MCTS is separate scope |
| R6 Staging refinements | M5 | M5 is R6-R8 finalization |
| Full observability/metrics dashboards | M6 | M6 is Ops Readiness |
| Closed-loop weight training jobs | M7 | M7 is Closed-Loop Learning |

### C.3 Files To CREATE

| File Path | Purpose | Created By Issue |
|-----------|---------|------------------|
| `k0/pipelines/p03/phases/r1_replay_coordinator.py` | R1 phase implementation | 4.1.x |
| `k0/pipelines/p03/phases/r2_episodic_integrator.py` | R2 phase implementation | 4.2.x |
| `k0/pipelines/p03/phases/r3_homeostasis.py` | R3 phase implementation | 4.3.x |
| `k0/pipelines/p03/phases/r4_kg_consolidator.py` | R4 phase implementation | 4.4.x |
| `k0/modules/consolidation/algorithms/importance_scorer.py` | ImportanceScorer class | 4.1.1 |
| `k0/modules/consolidation/algorithms/hebbian_learner.py` | HebbianLearner class | 4.1.3 |
| `k0/modules/consolidation/algorithms/dbscan_clusterer.py` | EpisodicDBSCAN class | 4.2.3 |
| `k0/modules/consolidation/algorithms/simhasher.py` | SimHasher class | 4.3.1 |
| `k0/modules/consolidation/algorithms/decay_engine.py` | UnifiedDecayEngine class | 4.3.3 |
| `k0/modules/consolidation/algorithms/entity_resolver.py` | EntityDisambiguator class | 4.4.2 |
| `k0/modules/consolidation/algorithms/granger_causality.py` | GrangerCausalityInference class | 4.4.9 |
| `tests/k0/pipelines/p03/test_r1_*.py` | R1 tests | 4.1.8 |
| `tests/k0/pipelines/p03/test_r2_*.py` | R2 tests | 4.2.8 |
| `tests/k0/pipelines/p03/test_r3_*.py` | R3 tests | 4.3.12 |
| `tests/k0/pipelines/p03/test_r4_*.py` | R4 tests | 4.4.12 |

---

## Part D: Epic Execution

---

### Epic 4.1 — R1 ReplayCoordinator (importance + hebbian)

> **Scope**: Implement R1 Hippocampal Replay phase — importance scoring and Hebbian association strengthening.
> **Module**: M23 ReplayCoordinator
> **Dossier**: Section 4.2, Appendix C.2

---

#### Issue 4.1.1 — Implement ImportanceScorer with weighted-sum formula

**Status**: COMPLETED

**Implemented Files**:

- `k0/modules/consolidation/algorithms/importance_scorer.py` — ImportanceScorer class with weighted-sum formula
- `k0/modules/consolidation/algorithms/__init__.py` — Export ImportanceScorer, ImportanceWeights, ImportanceBreakdown
- `k0/pipelines/p03/phases/r1_importance_scorer.py` — R1 phase integration

**Spec Reference**:

- [Dossier §2.4](../pipelines/P03_consolidation_dossier_v2.md#24-scientific-formulas) (lines 2599-2615) — Importance Score Formula
- [Dossier Appendix C.2.1](../pipelines/P03_consolidation_dossier_v2.md#c21-importance-scoring) (lines 20360-20550) — Full algorithm specification

**Goal**: Compute importance scores for hippocampal events to prioritize consolidation.

**Scientific Basis** (from Dossier §2.4):

> Based on: Emotional tagging theory (McGaugh 2004), Novelty detection (Knight 1996)
>
> Both strong positive AND strong negative emotions enhance memory encoding.
> Novel events are prioritized over routine. Social events weight higher.

**Full Importance Formula** (from Dossier §2.4):

```
importance_score = (
    0.35 × |sentiment_score| × |affect_valence| × (1 + affect_arousal)  # Emotional salience
  + 0.25 × exp(-λ_recency × days_since_event)                           # Recency (λ=0.05, 14-day half-life)
  + 0.20 × log(1 + access_count) / log(10)                              # Access frequency
  + 0.20 × participant_count × avg_relationship_strength                # Social significance
)
```

**MVP Simplification**:

For MVP, we use the simplified formula from Appendix C.2.1 (novelty replaces access_count):

```
importance = (
    emotional_component  +  # 0.25 × |sentiment| + 0.30 × |affect|
    novelty_component    +  # 0.25 × novelty_score
    social_component        # 0.20 × log2(participants) / 3.32
) × event_type_multiplier
```

**Existing Infrastructure to Use**:

| Component | Location | How to Use |
|-----------|----------|------------|
| `P03EventState.set_importance()` | `event_state.py:265-295` | Call after computing score |
| `ScoredEvent` dataclass | `phase_outputs.py:25-42` | Return type for batch scoring |
| `P03PhaseProtocol` | `phase_interface.py:85-115` | Implement interface for R1 phase |
| `P03PhaseResult.done()` | `phase_interface.py:35-50` | Return result on success |

**Algorithm Implementation** (from Dossier Appendix C.2.1):

```python
# File: k0/modules/consolidation/algorithms/importance_scorer.py

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import math
import logging

logger = logging.getLogger(__name__)


@dataclass
class ImportanceWeights:
    """Configurable weights for importance scoring."""
    sentiment_weight: float = 0.25
    affect_weight: float = 0.30
    novelty_weight: float = 0.25
    social_weight: float = 0.20

    def total(self) -> float:
        return (self.sentiment_weight + self.affect_weight +
                self.novelty_weight + self.social_weight)


@dataclass
class ImportanceBreakdown:
    """Component breakdown for audit logging."""
    emotional_component: float
    novelty_component: float
    social_component: float
    multiplier: float
    final_score: float


class ImportanceScorer:
    """
    Compute importance scores for hippocampal event selection.

    Spec: Dossier §2.4, Appendix C.2.1

    Scientific Basis: McGaugh (2004) - Emotional memories are
    more strongly encoded due to amygdala-hippocampus interaction.
    """

    # Static default weights (used until 500 samples for learning)
    DEFAULT_WEIGHTS = ImportanceWeights()

    # Event type multipliers (from Dossier C.2.1)
    EVENT_TYPE_MULTIPLIERS = {
        "message": 1.0,
        "photo": 1.2,        # Visual memories weighted higher
        "milestone": 2.0,    # Birthdays, anniversaries
        "routine": 0.5,      # Daily repeated events
        "location": 0.8,     # Check-ins
        "voice": 1.1,        # Voice memos
    }

    # Minimum samples before using learned weights
    MIN_SAMPLES_FOR_LEARNED_WEIGHTS = 500

    def __init__(self, space_id: str, weight_store):
        self.space_id = space_id
        self.weight_store = weight_store
        self._cached_weights: Optional[ImportanceWeights] = None

    async def get_weights(self) -> ImportanceWeights:
        """
        Load weights from st_learned_weights.

        Fallback to static if sample_count < 500.
        """
        if self._cached_weights:
            return self._cached_weights

        learned = await self.weight_store.get_weights(
            space_id=self.space_id,
            param_prefix="importance_",
        )

        if learned and learned.sample_count >= self.MIN_SAMPLES_FOR_LEARNED_WEIGHTS:
            self._cached_weights = ImportanceWeights(
                sentiment_weight=learned.weights.get("sentiment", 0.25),
                affect_weight=learned.weights.get("affect", 0.30),
                novelty_weight=learned.weights.get("novelty", 0.25),
                social_weight=learned.weights.get("social", 0.20),
            )
            logger.info(f"Using learned weights (n={learned.sample_count})")
        else:
            self._cached_weights = self.DEFAULT_WEIGHTS
            logger.info("Using static default weights")

        return self._cached_weights

    def compute_emotional_intensity(
        self,
        sentiment_score: float,
        affect_valence: float,
        weights: ImportanceWeights,
    ) -> float:
        """
        Combine sentiment and affect into emotional intensity.

        We use absolute values because both strong positive AND
        strong negative emotions enhance memory encoding.
        """
        sentiment_intensity = abs(sentiment_score)
        affect_intensity = abs(affect_valence)

        return (
            sentiment_intensity * weights.sentiment_weight +
            affect_intensity * weights.affect_weight
        )

    def compute_social_factor(self, participant_count: int) -> float:
        """
        Compute social factor from participant count.

        Uses logarithmic scaling to prevent large groups from
        completely dominating: 2 people ≈ 0.30, 5 people ≈ 0.70, 10+ ≈ 1.0
        """
        if participant_count <= 1:
            return 0.0  # Solo event, no social bonus

        # Log scale: log2(count) / log2(10) = log2(count) / 3.32
        return min(1.0, math.log2(participant_count) / 3.32)

    def compute_importance_score(
        self,
        event,
        weights: ImportanceWeights,
    ) -> Tuple[float, ImportanceBreakdown]:
        """
        Main scoring function.

        Formula (from Dossier C.2.1):
            importance = (emotional + novelty + social) × multiplier
        """
        # Component scores
        emotional = self.compute_emotional_intensity(
            sentiment_score=getattr(event, 'sentiment_score', 0.0),
            affect_valence=getattr(event, 'affect_valence', 0.0),
            weights=weights,
        )

        novelty = getattr(event, 'novelty_score', 0.0) * weights.novelty_weight

        social = self.compute_social_factor(
            getattr(event, 'participant_count', 1)
        ) * weights.social_weight

        # Base importance (sum of components)
        base_importance = emotional + novelty + social

        # Apply event type multiplier
        event_type = getattr(event, 'content_type', 'message')
        multiplier = self.EVENT_TYPE_MULTIPLIERS.get(event_type, 1.0)

        final_score = base_importance * multiplier

        # Normalize to [0.0, 1.0]
        final_score = min(1.0, max(0.0, final_score))

        breakdown = ImportanceBreakdown(
            emotional_component=emotional,
            novelty_component=novelty,
            social_component=social,
            multiplier=multiplier,
            final_score=final_score,
        )

        return final_score, breakdown

    async def score_batch(
        self,
        events: List,
    ) -> List:
        """
        Score all events in batch and update P03EventState.

        Returns: List[ScoredEvent]
        """
        weights = await self.get_weights()
        scored = []

        for event in events:
            score, breakdown = self.compute_importance_score(event, weights)

            # Update event state
            event.set_importance(
                score=score,
                recency=0.0,  # Not using recency in MVP
                affect=breakdown.emotional_component,
                social=breakdown.social_component,
                novelty=breakdown.novelty_component,
            )

            scored.append({
                'event_id': event.event_id,
                'importance_score': score,
                'recency_factor': 0.0,
                'affect_factor': breakdown.emotional_component,
                'social_factor': breakdown.social_component,
                'novelty_factor': breakdown.novelty_component,
            })

        return scored

    def select_batch(
        self,
        scored_events: List,
        batch_size: int,
    ) -> List:
        """
        Select top N events by importance for processing.

        Spec: Dossier C.2.1 "select_batch"
        """
        return sorted(
            scored_events,
            key=lambda e: e.get('importance_score', e.importance_score),
            reverse=True,
        )[:batch_size]
```

**Importance Priority Thresholds** (from Dossier C.2.1):

| Score Range | Priority | Processing Behavior |
| ----------- | -------- | ------------------- |
| 0.80 - 1.00 | CRITICAL | Process immediately, never skip |
| 0.50 - 0.79 | HIGH | Process in current cycle |
| 0.30 - 0.49 | MEDIUM | Process if capacity allows |
| 0.00 - 0.29 | LOW | May be deferred, candidate for pruning |

**Inputs Required**:

| Input | Source | Field/Column |
|-------|--------|--------------|
| `sentiment_score` | `P03EventState` | `sentiment_score` (from P02 NLP) |
| `affect_valence` | `P03EventState` | Extract from `emotions_json` or separate field |
| `novelty_score` | `P03EventState` | Computed from embedding distance to existing centroids |
| `participant_count` | `st_hipp_events` | `actor_ids` array length |
| `event_type` | `st_hipp_events` | `content_type` mapped to importance categories |
| `learned_weights` | `st_learned_weights` | Query by `space_id`, `param_key LIKE 'importance_%'` |

**Outputs**:

| Output | Destination | Usage |
|--------|-------------|-------|
| `importance_score` | `P03EventState.importance_score` | Batch prioritization |
| `ImportanceBreakdown` | `st_consolidation_audit.outputs_json` | Audit (Issue 4.1.2) |
| `List[ScoredEvent]` | `P03PhaseOutputs.r1_scored_events` | Passed to R2 |

**File to Create**: `k0/modules/consolidation/algorithms/importance_scorer.py`

**Configuration**:

| Config Key | Default | Purpose |
| ---------- | ------- | ------- |
| `P03_IMPORTANCE_SENTIMENT_WEIGHT` | 0.25 | Sentiment contribution |
| `P03_IMPORTANCE_AFFECT_WEIGHT` | 0.30 | Affect contribution |
| `P03_IMPORTANCE_NOVELTY_WEIGHT` | 0.25 | Novelty contribution |
| `P03_IMPORTANCE_SOCIAL_WEIGHT` | 0.20 | Social contribution |
| `P03_IMPORTANCE_MIN_SAMPLES` | 500 | Min samples for learned weights |

**Metrics**:

| Metric Name | Type | Description |
| ----------- | ---- | ----------- |
| `p03_importance_score` | Histogram | Distribution of scores |
| `p03_importance_priority` | Counter | Events by priority tier |
| `p03_importance_weights_source` | Counter | "learned" vs "static" |

**Deliverables**:

- [ ] `ImportanceWeights` dataclass with 4 weights
- [ ] `ImportanceBreakdown` dataclass for audit
- [ ] `ImportanceScorer` class with constructor
- [ ] `get_weights()` → fallback to static if < 500 samples
- [ ] `compute_emotional_intensity()` → |sentiment| + |affect|
- [ ] `compute_social_factor()` → log2 scale
- [ ] `compute_importance_score()` → (score, breakdown)
- [ ] `score_batch()` → updates P03EventState
- [ ] `select_batch()` → top-N by score
- [ ] Event-type multipliers: photo=1.2, milestone=2.0, routine=0.5
- [ ] Score normalized to [0.0, 1.0]

**Acceptance Criteria**:

- [ ] High-emotion events (|sentiment| > 0.7, |affect| > 0.7) rank in top 20%
- [ ] Milestone events (multiplier=2.0) rank higher than routine (0.5)
- [ ] `P03EventState.importance_computed` is `True` after scoring
- [ ] Component breakdown available for audit logging
- [ ] Learned weights used when sample_count >= 500

**Test File**: `tests/k0/pipelines/p03/test_r1_importance_scorer.py`

**Test Cases**:

1. `test_compute_emotional_intensity_high_sentiment` — |sentiment|=0.9 → emotional > 0.2
2. `test_compute_emotional_intensity_both_factors` — sentiment + affect combined
3. `test_compute_social_factor_solo_event` — participant_count=1 → 0.0
4. `test_compute_social_factor_pair` — participant_count=2 → ≈0.30
5. `test_compute_social_factor_group` — participant_count=5 → ≈0.70
6. `test_compute_social_factor_large_group` — participant_count=10 → ≈1.0
7. `test_importance_milestone_boost` — multiplier=2.0 applied
8. `test_importance_routine_reduction` — multiplier=0.5 applied
9. `test_importance_score_normalized` — always [0.0, 1.0]
10. `test_select_batch_returns_top_n` — batch_size=10 returns highest
11. `test_learned_weights_used` — sample_count>=500 uses learned
12. `test_static_weights_fallback` — sample_count<500 uses static
13. `test_score_batch_updates_event_state` — importance_computed=True

**Blocked By**: M3 Complete ✅

**Blocks**: 4.1.2, 4.1.5, 4.1.8

---

#### Issue 4.1.2 — Implement factor audit logging for importance scoring

**Status**: COMPLETED

**Implemented Files**:

- `k0/modules/consolidation/algorithms/importance_scorer.py` — Added `score_batch_with_audit()` method
- `k0/pipelines/p03/audit_logger.py` — Added `AuditAction.SCORE` enum value and explanation template
- `k0/pipelines/p03/phases/r1_importance_scorer.py` — R1 phase calls `score_batch_with_audit()` with P03AuditLogger
- `k0/pipelines/p03/phase_outputs.py` — Added `r1_audit_records` field for R7 batch write

**Spec Reference**:

- [Dossier §6.20](../pipelines/P03_consolidation_dossier_v2.md#620-st_consolidation_audit) — st_consolidation_audit schema
- [Dossier §14.10](../pipelines/P03_consolidation_dossier_v2.md#1410-explainability) — Explanation templates

**Goal**: Persist per-event importance component breakdown for debugging and learning feedback.

**Existing Infrastructure to Use**:

| Component | Location | How to Use |
|-----------|----------|------------|
| `P03AuditLogger` class | `audit_logger.py:257-340` | `logger.log_decision(...)` to accumulate records |
| `AuditAction` enum | `audit_logger.py:35-48` | Use `AuditAction.CREATE` for new importance scores |
| `AuditRecord` dataclass | `audit_logger.py:125-180` | Already handles `inputs`, `outputs`, `formula_used`, `confidence` |
| `redact_pii_fields()` | `audit_logger.py:105-118` | Automatically strips RED-band fields |
| `EXPLANATION_TEMPLATES` | `audit_logger.py:55-90` | Template strings for human-readable explanations |

**P03AuditLogger.log_decision() Signature** (already exists):

```python
def log_decision(
    self,
    memory_id: str,            # event_id being scored
    source_table: str,         # "st_hipp_events"
    action: AuditAction,       # AuditAction.CREATE (new score computed)
    formula_used: str,         # "importance_scorer_v1"
    formula_version: str,      # "1.0.0"
    inputs: Dict[str, Any],    # component inputs → auto-redacted
    outputs: Dict[str, Any],   # component outputs → auto-redacted
    decision_id: str,          # links to P03CycleContext.cycle_id
    confidence: float,         # importance_score itself (0-1)
    threshold_used: float,     # priority threshold if applicable
    threshold_name: str,       # "importance_priority_HIGH"
    template_params: Dict,     # for explanation template
    audit_id: str,             # optional explicit ID for idempotency
) -> AuditRecord
```

**Implementation Pattern** (integrate with ImportanceScorer):

```python
# In ImportanceScorer.score_batch() after computing score:

async def score_batch(
    self,
    events: List[P03EventState],
    audit_logger: P03AuditLogger,
    sample_rate: float = 1.0,  # 1.0 = 100% debug, 0.1 = 10% production
) -> List[ScoredEvent]:
    weights = await self.get_weights()
    scored = []

    for event in events:
        score, breakdown = self.compute_importance_score(event, weights)
        event.set_importance(
            score=score,
            recency=breakdown.get("recency_component", 0.0),
            affect=breakdown["emotional_component"],
            social=breakdown["social_component"],
            novelty=breakdown["novelty_component"],
        )

        # Audit logging with sampling
        if random.random() < sample_rate:
            audit_logger.log_decision(
                memory_id=event.event_id,
                source_table="st_hipp_events",
                action=AuditAction.CREATE,
                formula_used="importance_scorer",
                formula_version="1.0.0",
                inputs={
                    "sentiment_score": event.sentiment_score,
                    "affect_valence": getattr(event, "affect_valence", 0.0),
                    "novelty_score": event.novelty_score,
                    "participant_count": event.participant_count,
                    "event_type": event.content_type,
                    "weights_source": "learned" if weights != self.static_weights else "static",
                },
                outputs={
                    "importance_score": score,
                    "emotional_component": breakdown["emotional_component"],
                    "novelty_component": breakdown["novelty_component"],
                    "social_component": breakdown["social_component"],
                    "multiplier": breakdown["multiplier"],
                },
                decision_id=audit_logger.cycle_id,
                confidence=score,
                template_params={
                    "formula_used": "importance_scorer",
                    "confidence": score,
                },
            )

        scored.append(ScoredEvent(...))

    return scored
```

**AuditRecord.to_db_row() Output** (already exists):

```python
{
    "audit_id": "01JFXYZ...",           # ULID generated
    "memory_id": "evt_123",              # event_id
    "source_table": "st_hipp_events",
    "action": "CREATE",
    "formula_used": "importance_scorer",
    "formula_version": "1.0.0",
    "inputs_json": '{"sentiment_score": 0.8, ...}',  # auto-redacted
    "outputs_json": '{"importance_score": 0.72, ...}',
    "explanation": "Decision made: CREATE",
    "decision_id": "cyc_abc123",
    "space_id": "sp_family",
    "tenant_id": "t_1",
    "cycle_id": "cyc_abc123",
    "confidence": 0.72,
    "created_at": 1735600000000,         # ms timestamp
    ...
}
```

**Sampling Configuration**:

| Environment | `sample_rate` | Rationale |
|-------------|---------------|-----------|
| DEBUG | 1.0 (100%) | Full audit for development |
| PRODUCTION | 0.1 (10%) | Balance observability vs. storage |
| STRESS_TEST | 0.01 (1%) | Minimal overhead during load testing |

**Inputs Required**:

| Input | Source |
|-------|--------|
| `P03AuditLogger` instance | Created in R1 phase with `space_id`, `tenant_id`, `cycle_id` |
| `sample_rate` config | `p03.importance.audit_sample_rate` from `st_config` or environment |
| Component breakdown from 4.1.1 | `ImportanceScorer.compute_importance_score()` returns `(score, breakdown)` |

**Outputs**:

| Output | Destination |
|--------|-------------|
| `List[AuditRecord]` | `P03AuditLogger._pending_records` (batched) |
| Batch INSERT | `st_consolidation_audit` via R7 staged writes |

**Deliverables**:

- [ ] Add `audit_logger` parameter to `ImportanceScorer.score_batch()`
- [ ] Add `sample_rate` parameter (default 1.0 for debug)
- [ ] Call `audit_logger.log_decision()` per sampled event
- [ ] Inputs dict: `sentiment_score`, `affect_valence`, `novelty_score`, `participant_count`, `event_type`, `weights_source`
- [ ] Outputs dict: `importance_score`, `emotional_component`, `novelty_component`, `social_component`, `multiplier`
- [ ] Config key: `p03.importance.audit_sample_rate` (add to config schema if missing)

**Acceptance Criteria**:

- [ ] Audit rows created with `formula_used="importance_scorer"` and `formula_version="1.0.0"`
- [ ] `inputs_json` contains all 6 input fields
- [ ] `outputs_json` contains all 5 output fields
- [ ] Production logging overhead < 1ms per event (sampling reduces write volume)
- [ ] Audit rows queryable: `SELECT * FROM st_consolidation_audit WHERE formula_used = 'importance_scorer'`

**Test File**: `tests/k0/pipelines/p03/test_r1_importance_audit.py`

**Test Cases**:

1. `test_audit_log_contains_all_inputs` — verify 6 input fields in `inputs_json`
2. `test_audit_log_contains_all_outputs` — verify 5 output fields in `outputs_json`
3. `test_sampling_rate_100_percent` — all events audited
4. `test_sampling_rate_10_percent` — approximately 10% audited
5. `test_pii_redaction_applied` — RED-band fields stripped
6. `test_audit_idempotency` — same `audit_id` not duplicated

**Blocked By**: 4.1.1

**Blocks**: 4.1.5, 4.1.8

---

#### Issue 4.1.3 — Implement HebbianLearner: co-occurrence + edge weight updates

**Status**: COMPLETED

**Completion Summary**:

- **File Created**: `k0/modules/consolidation/algorithms/hebbian_learner.py` (620 lines)
- **Tests Created**: `tests/k0/pipelines/p03/test_r1_hebbian_learner.py` (58 tests pass)
- **Exports Added**: `HebbianLearner`, `HebbianConfig`, `KGEdge`, `EdgeUpdate`, `CoOccurrence`, `RelationType`, `AntiHebbianSignal` in `__init__.py`

**Implementation Details**:

- `HebbianConfig` dataclass with learning_rate=0.1, decay_rate=0.01, max_weight=1.0, min_weight=0.01
- `extract_cooccurrences()` extracts INTERACTS_WITH, FREQUENTS, DISCUSSES from NER entities
- `update_edge_weight()` with soft saturation formula: `Δw = lr × (max - current) × importance`
- `apply_decay()` with exponential decay: `new_weight = weight × exp(-decay_rate × days)`
- `process_batch()` aggregates co-occurrences and records in event state

**Spec Reference**:

- [Dossier §4.2.3](../pipelines/P03_consolidation_dossier_v2.md#423-association-strengthening-hebbian-learning) — Association Strengthening
- [Dossier Appendix C.2.2](../pipelines/P03_consolidation_dossier_v2.md#appendix-c-algorithm-specifications) (lines 20900-21100) — Hebbian Learning Algorithm

**Goal**: Strengthen KG edges between frequently co-occurring entities following Hebb's principle: "Cells that fire together, wire together."

**Existing Infrastructure to Use**:

| Component | Location | How to Use |
|-----------|----------|------------|
| `P03EventState.add_hebbian_update()` | `event_state.py:297-320` | Call per edge update: `event.add_hebbian_update(source_id, target_id, old_weight, new_weight, update_type)` |
| `HebbianEdgeUpdate` dataclass | `phase_outputs.py:45-65` | Output type: `source_entity_id`, `target_entity_id`, `old_weight`, `new_weight`, `delta`, `update_type` |
| `st_kg_edges` table | `0033_st_kg_edges.py` migration | Target table: `source_id`, `target_id`, `relation_type`, `weight`, `co_occurrence_count`, `last_updated_at` |

**Algorithm Implementation** (from Dossier Appendix C.2.2):

```python
# File: k0/modules/consolidation/algorithms/hebbian_learner.py

from dataclasses import dataclass
from typing import Dict, List, Tuple

@dataclass
class HebbianConfig:
    """Configuration for Hebbian learning."""
    learning_rate: float = 0.1      # How much each co-occurrence strengthens
    decay_rate: float = 0.01        # How much unused edges weaken per day
    max_weight: float = 1.0         # Weight cap to prevent runaway
    min_weight: float = 0.01        # Below this, edge is pruned

class HebbianLearner:
    """
    Implements Hebbian learning for knowledge graph edge weights.

    Principle: "Cells that fire together, wire together" (Hebb, 1949)

    In FamilyOS context: Entities (people, places, concepts) that
    appear together in events strengthen their connection.
    """

    def __init__(self, config: HebbianConfig | None = None):
        self.config = config or HebbianConfig()

    def extract_cooccurrences(
        self,
        event: P03EventState,
    ) -> List[Tuple[str, str, str]]:
        """
        Extract all entity pairs that co-occur in an event.

        Returns: List of (entity_a, entity_b, relation_type)
        """
        cooccurrences = []
        actors = event.actor_ids or []

        # Actor-Actor co-occurrences (social relationships)
        for i, actor_a in enumerate(actors):
            for actor_b in actors[i + 1:]:
                cooccurrences.append((actor_a, actor_b, "INTERACTS_WITH"))

        # Actor-Location co-occurrences
        if event.location_entity_id:
            for actor in actors:
                cooccurrences.append((actor, event.location_entity_id, "FREQUENTS"))

        # Actor-Topic co-occurrences (from NER entities)
        extracted_entities = event.ner_entities or []
        for actor in actors:
            for entity in extracted_entities:
                entity_id = entity.get("entity_id") if isinstance(entity, dict) else entity
                if entity_id:
                    cooccurrences.append((actor, entity_id, "DISCUSSES"))

        return cooccurrences

    def update_edge_weight(
        self,
        current_weight: float,
        current_count: int,
        event_importance: float,
    ) -> Tuple[float, int]:
        """
        Hebbian weight update formula with soft saturation.

        Formula:
            delta = learning_rate × (max_weight - current_weight) × event_importance

        The (max_weight - current_weight) term prevents weights from
        exceeding max_weight (soft saturation).
        """
        delta = (
            self.config.learning_rate
            * (self.config.max_weight - current_weight)
            * event_importance
        )
        new_weight = current_weight + delta
        new_count = current_count + 1

        return (min(self.config.max_weight, new_weight), new_count)

    def apply_decay(
        self,
        edges: List[KGEdge],
        days_since_update: int,
    ) -> Tuple[List[KGEdge], List[str]]:
        """
        Apply decay to edges that haven't been reinforced.

        Formula: new_weight = weight × exp(-decay_rate × days)

        Returns: (surviving_edges, pruned_edge_ids)
        """
        surviving = []
        pruned = []

        for edge in edges:
            decay_factor = math.exp(-self.config.decay_rate * days_since_update)
            new_weight = edge.weight * decay_factor

            if new_weight >= self.config.min_weight:
                edge.weight = new_weight
                surviving.append(edge)
            else:
                pruned.append(edge.edge_id)

        return surviving, pruned

    def process_batch(
        self,
        events: List[P03EventState],
    ) -> Dict[Tuple[str, str, str], EdgeUpdate]:
        """
        Process batch and compute all edge updates.

        Aggregates co-occurrences across all events, then computes
        cumulative updates per unique edge.
        """
        edge_updates: Dict[Tuple[str, str, str], EdgeUpdate] = {}

        for event in events:
            cooccurrences = self.extract_cooccurrences(event)
            importance = event.importance_score

            for source, target, rel_type in cooccurrences:
                key = (source, target, rel_type)

                if key not in edge_updates:
                    edge_updates[key] = EdgeUpdate(
                        source_id=source,
                        target_id=target,
                        relation_type=rel_type,
                        cooccurrence_count=0,
                        importance_sum=0.0,
                    )

                edge_updates[key].cooccurrence_count += 1
                edge_updates[key].importance_sum += importance

                # Record in event state for audit trail
                event.add_hebbian_update(
                    source_entity_id=source,
                    target_entity_id=target,
                    old_weight=0.0,  # Will be populated during DB update
                    new_weight=0.0,  # Will be populated during DB update
                    update_type=rel_type,
                )

        return edge_updates
```

**st_kg_edges Columns** (from migration 0033):

| Column | Type | Purpose |
|--------|------|---------|
| `edge_id` | TEXT PK | UUID primary key |
| `source_id` | TEXT | Source entity (FK to st_kg_dom) |
| `target_id` | TEXT | Target entity (FK to st_kg_dom) |
| `relation_type` | TEXT | INTERACTS_WITH, FREQUENTS, DISCUSSES, etc. |
| `weight` | FLOAT | Hebbian-learned strength [0.01, 1.0] |
| `co_occurrence_count` | INT | Number of co-occurrences |
| `last_updated_at` | BIGINT | Timestamp (ms) of last update |
| `space_id` | TEXT | Multi-tenant isolation |
| `tenant_id` | TEXT | Tenant isolation |

**SQL Patterns for R7 Writes**:

```sql
-- Update existing edge
UPDATE st_kg_edges
SET weight = :new_weight,
    co_occurrence_count = co_occurrence_count + :delta_count,
    last_updated_at = :now_ms
WHERE source_id = :src AND target_id = :tgt AND relation_type = :rel
  AND space_id = :space_id AND tenant_id = :tenant_id;

-- Insert new edge (if no existing)
INSERT INTO st_kg_edges (edge_id, source_id, target_id, relation_type, weight, co_occurrence_count, last_updated_at, space_id, tenant_id)
VALUES (:edge_id, :src, :tgt, :rel, :initial_weight, 1, :now_ms, :space_id, :tenant_id)
ON CONFLICT (source_id, target_id, relation_type, space_id)
DO UPDATE SET weight = :new_weight, co_occurrence_count = st_kg_edges.co_occurrence_count + 1, last_updated_at = :now_ms;

-- Soft-delete (tombstone) pruned edge
UPDATE st_kg_edges
SET is_tombstone = TRUE, tombstone_at = :now_ms
WHERE edge_id = :edge_id;
```

**Inputs Required**:

| Input | Source | Field/Column |
|-------|--------|--------------|
| `P03EventState.actor_ids` | P02/R0 hydration | List[str] of actor entity IDs |
| `P03EventState.location_entity_id` | P02/R0 hydration | Location entity ID (optional) |
| `P03EventState.ner_entities` | P02 NLP | List of extracted entity dicts |
| `P03EventState.importance_score` | Issue 4.1.1 | Float [0, 1] from ImportanceScorer |
| Existing edges | `st_kg_edges` query | Current weight, count for update calculation |

**Outputs**:

| Output | Destination | Usage |
|--------|-------------|-------|
| `Dict[EdgeKey, EdgeUpdate]` | HebbianLearner return | Aggregated updates per edge |
| `List[HebbianEdgeUpdate]` | `P03PhaseOutputs.r1_hebbian_updates` | Passed to R7 for batch writes |
| `event.hebbian_updates` | `P03EventState.hebbian_updates` | Per-event audit trail |

**Edge Weight Interpretation** (from dossier):

| Weight Range | Relationship Strength | Example |
|--------------|----------------------|---------|
| 0.80 - 1.00 | Very Strong | Best friends, family members |
| 0.50 - 0.79 | Strong | Regular colleagues, close friends |
| 0.20 - 0.49 | Moderate | Acquaintances, occasional contacts |
| 0.01 - 0.19 | Weak | One-time interactions |

**File to Create**: `k0/modules/consolidation/algorithms/hebbian_learner.py`

**Deliverables**:

- [ ] `HebbianConfig` dataclass: `learning_rate=0.1`, `decay_rate=0.01`, `max_weight=1.0`, `min_weight=0.01`
- [ ] `HebbianLearner` class with constructor taking `HebbianConfig`
- [ ] `extract_cooccurrences(event)` → List[(source, target, rel_type)]
  - [ ] Actor-Actor pairs → `INTERACTS_WITH`
  - [ ] Actor-Location pairs → `FREQUENTS`
  - [ ] Actor-Topic pairs → `DISCUSSES`
- [ ] `update_edge_weight(current_weight, current_count, event_importance)` → (new_weight, new_count)
  - [ ] Soft saturation: `delta = lr × (max - current) × importance`
  - [ ] Clamped to [0, max_weight]
- [ ] `apply_decay(edges, days_since_update)` → (surviving, pruned_ids)
  - [ ] Exponential decay: `weight × exp(-decay_rate × days)`
  - [ ] Prune if weight < min_weight
- [ ] `process_batch(events)` → Dict[EdgeKey, EdgeUpdate]
  - [ ] Aggregates co-occurrences across batch
  - [ ] Calls `event.add_hebbian_update()` for audit trail
- [ ] New edges created with initial weight = `learning_rate × avg_importance`

**Acceptance Criteria**:

- [ ] Entities appearing together in 3+ events have edge weight > 0.2
- [ ] Soft saturation prevents weight exceeding 1.0 even after 100 co-occurrences
- [ ] Edges below `min_weight=0.01` are marked for pruning (tombstone)
- [ ] `P03EventState.hebbian_updates` populated after `process_batch()`

**Test File**: `tests/k0/pipelines/p03/test_r1_hebbian_learner.py`

**Test Cases**:

1. `test_extract_cooccurrences_actor_actor` — 2 actors → 1 INTERACTS_WITH pair
2. `test_extract_cooccurrences_3_actors` — 3 actors → 3 pairs (combinations)
3. `test_extract_cooccurrences_actor_location` — location set → FREQUENTS pairs
4. `test_extract_cooccurrences_actor_topic` — NER entities → DISCUSSES pairs
5. `test_update_edge_weight_soft_saturation` — weight 0.9 + delta capped at 1.0
6. `test_update_edge_weight_low_importance` — importance 0.1 → small delta
7. `test_update_edge_weight_high_importance` — importance 0.9 → large delta
8. `test_apply_decay_keeps_strong_edges` — weight 0.8 after 30 days still > 0.01
9. `test_apply_decay_prunes_weak_edges` — weight 0.05 after 30 days < 0.01 → pruned
10. `test_process_batch_aggregates` — 5 events with same pair → count=5
11. `test_process_batch_updates_event_state` — `event.hebbian_updates` has entries
12. `test_new_edge_initial_weight` — new edge gets `lr × avg_importance`

**Blocked By**: 4.1.1 (needs importance_score)

**Blocks**: 4.1.4, 4.1.5, 4.1.8

---

#### Issue 4.1.4 — Implement Hebbian anti-decay and edge normalization

**Status**: COMPLETED

**Completion Summary**:

- **File Updated**: `k0/modules/consolidation/algorithms/hebbian_learner.py` (included in 4.1.3)
- **Tests Created**: Included in `test_r1_hebbian_learner.py` (TestApplyAntiDecay class, 10 tests)
- **Method Added**: `apply_anti_decay(edge, signal_type, confidence, is_explicit_correction) -> (new_weight, should_prune)`

**Implementation Details**:

- Anti-Hebbian formula: `Δw = -anti_lr × current_weight × confidence × penalty × (1.3 if explicit else 1.0)`
- Penalty lookup: `ENTITY_MERGE_REJECTED=0.2`, `ASSOCIATION_WRONG=0.3`, `MUTUAL_EXCLUSION=0.4`, `CONTRADICTION=0.15`
- Prune threshold: weight < 0.05 → should_prune=True
- Weight normalization via `normalize_weight()` method
- `AntiHebbianSignal` enum and `ANTI_HEBBIAN_PENALTIES` lookup table

**Spec Reference**:

- [Dossier Appendix C.2.2.1](../pipelines/P03_consolidation_dossier_v2.md#appendix-c-algorithm-specifications) (lines 21000-21100) — Anti-Hebbian Decay
- [Dossier Appendix C.2.2.5](../pipelines/P03_consolidation_dossier_v2.md#appendix-c-algorithm-specifications) (lines 21500+) — Weight Normalization Strategy

**Goal**: Weaken wrong associations (anti-Hebbian: "cells that fire apart, unwire") and ensure consistent weight interpretation.

**Existing Infrastructure to Use**:

| Component | Location | How to Use |
|-----------|----------|------------|
| `HebbianLearner` class | `algorithms/hebbian_learner.py` (Issue 4.1.3) | Add `apply_anti_decay()` method |
| `HebbianEdgeUpdate` dataclass | `phase_outputs.py:45-65` | Set `update_type='ANTI_HEBBIAN'` |
| `P03FeedbackConsumer._handle_reinforcement()` | `feedback_consumer.py:280-300` | M3 stub → wire to anti-Hebbian in M4 |
| `st_kg_edges` table | Migration 0033 | Update `weight`, set `archival_status='ARCHIVED'` if pruned |

**Anti-Hebbian Decay Algorithm** (from Dossier C.2.2.1):

```python
# Add to HebbianLearner class

def apply_anti_decay(
    self,
    edge: KGEdge,
    signal_type: str,
    confidence: float = 1.0,
    is_explicit_correction: bool = False,
) -> Tuple[float, bool]:
    """
    Apply anti-Hebbian decay to weaken wrong associations.

    Formula:
        Δw = -anti_lr × current_weight × confidence × penalty_multiplier

    Returns: (new_weight, should_prune)
    """
    anti_lr = 0.15  # Faster than positive learning (0.1)
    penalty_multiplier = 1.3 if is_explicit_correction else 1.0

    # Lookup penalty by signal type
    penalties = {
        "ENTITY_MERGE_REJECTED": 0.2,
        "ASSOCIATION_WRONG": 0.3,
        "MUTUAL_EXCLUSION": 0.4,
        "CONTRADICTION": 0.15,
    }
    penalty = penalties.get(signal_type, 0.1)

    delta = -anti_lr * edge.weight * confidence * penalty * penalty_multiplier
    new_weight = max(0.0, edge.weight + delta)

    # Prune threshold: if weight drops below 0.05, mark for archive
    should_prune = new_weight < 0.05

    return new_weight, should_prune
```

**Conflict Signal Mapping** (from Dossier C.2.2.1):

| Signal Type | Source | Action | Penalty |
|-------------|--------|--------|--------|
| `ENTITY_MERGE_REJECTED` | P06/User | Anti-Hebbian decay + mark distinct | 0.2 |
| `ASSOCIATION_WRONG` | K1 correction | Strong anti-Hebbian decay | 0.3 |
| `MUTUAL_EXCLUSION` | P03 R4 | Prune candidate | 0.4 |
| `CONTRADICTION` | P03 R7 | Moderate anti-Hebbian decay | 0.15 |

**Weight Normalization** (from Dossier C.2.2.5):

```python
# After every weight update (positive or anti-Hebbian)
new_weight = max(0.0, min(1.0, new_weight))  # Hard clamp to [0.0, 1.0]

if new_weight < 0.01:  # Below meaningful threshold
    archival_status = 'ARCHIVED'
    # Record in st_pruned_entities for 14-day regret window
```

**Integration with Feedback Consumer** (wire stub to real handler):

```python
# In P03FeedbackConsumer.__init__() - replace M3 stub with real handler
async def _handle_reinforcement_real(self, payload: P03FeedbackPayload, conn: Any) -> None:
    """Handle REINFORCEMENT_OUTCOME feedback → anti-Hebbian or reinforcement."""
    if payload.outcome == "NEGATIVE":
        # Anti-Hebbian decay
        new_weight, should_prune = self.hebbian_learner.apply_anti_decay(
            edge=await self._load_edge(payload.entity_id, payload.related_entity_id, conn),
            signal_type=payload.signal_subtype,
            confidence=payload.confidence,
            is_explicit_correction=payload.is_explicit,
        )
        await self._update_edge_weight(payload.entity_id, payload.related_entity_id, new_weight, should_prune, conn)
    else:
        # Positive reinforcement (existing Hebbian update)
        ...
```

**Audit Trail** (use existing P03AuditLogger):

```python
audit_logger.log_decision(
    memory_id=edge.edge_id,
    source_table="st_kg_edges",
    action=AuditAction.DECAY,  # Use existing enum value
    formula_used="anti_hebbian_v1",
    formula_version="1.0.0",
    inputs={
        "signal_type": signal_type,
        "penalty": penalty,
        "current_weight": edge.weight,
        "confidence": confidence,
        "is_explicit": is_explicit_correction,
    },
    outputs={
        "new_weight": new_weight,
        "delta": delta,
        "pruned": should_prune,
    },
    confidence=confidence,
)
```

**Deliverables**:

- [ ] Add `apply_anti_decay(edge, signal_type, confidence, is_explicit_correction)` to `HebbianLearner`
- [ ] Anti-Hebbian formula: `Δw = -0.15 × current_weight × confidence × penalty × (1.3 if explicit else 1.0)`
- [ ] Penalty lookup dict: `ENTITY_MERGE_REJECTED=0.2`, `ASSOCIATION_WRONG=0.3`, `MUTUAL_EXCLUSION=0.4`, `CONTRADICTION=0.15`
- [ ] Weight normalization: `max(0.0, min(1.0, new_weight))`
- [ ] Prune threshold: weight < 0.05 → `archival_status='ARCHIVED'`
- [ ] Wire `P03FeedbackConsumer._handle_reinforcement()` to real handler (replace M3 stub)
- [ ] Audit logging via `P03AuditLogger.log_decision()` with `action=AuditAction.DECAY`

**Acceptance Criteria**:

- [ ] `ENTITY_MERGE_REJECTED` signal reduces edge weight by ~20%
- [ ] Explicit corrections (user feedback) apply 1.3× penalty multiplier
- [ ] Edges with weight < 0.05 are marked for archive
- [ ] All edge weights remain in [0.0, 1.0] after any update
- [ ] Audit trail records anti-Hebbian updates with `formula_used='anti_hebbian_v1'`

**Test File**: `tests/k0/pipelines/p03/test_r1_anti_hebbian.py`

**Test Cases**:

1. `test_anti_decay_entity_merge_rejected` — weight 0.5 → ~0.485 (penalty 0.2)
2. `test_anti_decay_explicit_correction_boost` — explicit correction applies 1.3× multiplier
3. `test_anti_decay_prune_threshold` — weight 0.06 after decay → marked for archive
4. `test_weight_clamped_to_zero` — large penalty doesn't go negative
5. `test_audit_log_anti_hebbian` — audit record created with correct inputs/outputs
6. `test_feedback_consumer_wires_to_anti_hebbian` — `REINFORCEMENT_OUTCOME` + `NEGATIVE` → calls `apply_anti_decay()`

**Blocked By**: 4.1.3

**Blocks**: 4.1.8

---

#### Issue 4.1.5 — Implement closed-loop importance weight learning

**Status**: COMPLETED

**Implementation Summary**:

- Created `k0/modules/consolidation/algorithms/importance_weight_learner.py` (~600 lines)
- `WeightLearnerConfig` dataclass with learning_rate=0.01, momentum=0.9, min_samples=500
- `ImportanceWeightLearner` class with PyTorch/NumPy dual backend
- `train_step()` with BCE loss for grounding prediction
- `check_rollback_needed()` after 3 consecutive loss increases
- `persist_weights()` upsert to st_learned_weights
- 37 tests in `test_r1_importance_learner.py`

**Files Changed**:

- `k0/modules/consolidation/algorithms/importance_weight_learner.py` (NEW)
- `k0/modules/consolidation/algorithms/__init__.py` (updated exports)
- `tests/k0/pipelines/p03/test_r1_importance_learner.py` (NEW)

**Spec Reference**:

- [Dossier Appendix C.2.1.1](../pipelines/P03_consolidation_dossier_v2.md#appendix-c-algorithm-specifications) (lines 20540-20700) — Adaptive Weight Learning
- [Dossier Appendix C.2.1.2](../pipelines/P03_consolidation_dossier_v2.md#appendix-c-algorithm-specifications) (lines 20780-20900) — Stability Controls

**Goal**: Transform static importance weights into learnable parameters using gradient descent from grounding feedback.

**Existing Infrastructure to Use**:

| Component | Location | How to Use |
|-----------|----------|------------|
| `st_learned_weights` table | Migration 0040 | Store learned weights with `param_key='importance_*'` |
| `st_feedback_signals` table | P21 owns, P03 consumes | Query for `was_grounded` ground truth labels |
| `P03FeedbackConsumer` | `feedback_consumer.py` | Wire `SALIENCE_ADJUSTMENT` to weight learner |
| `ImportanceScorer.get_weights()` | Issue 4.1.1 | Reads weights; learner updates them |

**st_learned_weights Schema** (from migration 0040):

| Column | Type | Purpose |
|--------|------|--------|
| `param_id` | TEXT PK | UUID |
| `param_key` | TEXT | e.g., `importance_emotional`, `importance_recency` |
| `param_scope` | TEXT | `global`, `space`, `entity_type`, `entity` |
| `scope_id` | TEXT | space_id for per-space weights (NULL for global) |
| `space_id` | TEXT | Multi-tenant isolation |
| `current_value` | FLOAT | Current learned weight |
| `prior_value` | FLOAT | Static prior (for rollback) |
| `confidence` | FLOAT [0-1] | Learning confidence |
| `sample_count` | INT | Number of feedback samples used |
| `version` | INT | For rollback tracking |
| `previous_value` | FLOAT | Value before last update |
| `quality_at_update` | FLOAT | Loss metric when updated |
| `rollback_eligible` | BOOL | Can be rolled back? |

**ImportanceWeightLearner Algorithm** (from Dossier C.2.1.1):

```python
# File: k0/modules/consolidation/algorithms/importance_weight_learner.py

import torch
import torch.nn.functional as F
from dataclasses import dataclass
from typing import Dict, Optional

@dataclass
class WeightLearnerConfig:
    learning_rate: float = 0.01
    momentum: float = 0.9
    min_samples: int = 500  # Cold start threshold
    weight_min: float = 0.05  # Per-weight floor
    weight_max: float = 0.60  # Per-weight ceiling
    sliding_window_days: int = 30

class ImportanceWeightLearner:
    """
    Learn importance component weights from feedback signals.

    Method: Online gradient descent with momentum
    Loss: Binary cross-entropy predicting "will event be grounded?"
    Training: Nightly batch during P03 consolidation cycle
    """

    def __init__(self, space_id: str, config: Optional[WeightLearnerConfig] = None):
        self.space_id = space_id
        self.config = config or WeightLearnerConfig()
        # 4 weights: emotional, recency, access, social
        self.weights = torch.tensor([0.35, 0.25, 0.20, 0.20], requires_grad=True)
        self.optimizer = torch.optim.Adam([self.weights], lr=self.config.learning_rate)
        self.velocity = torch.zeros(4)  # Momentum term

    async def train_step(self, features: torch.Tensor, labels: torch.Tensor) -> float:
        """
        One gradient descent step.

        Args:
            features: [N, 4] tensor of component scores (emotional, recency, access, social)
            labels: [N] tensor of ground truth (1.0 if grounded, 0.0 if not)

        Returns:
            Loss value for monitoring
        """
        self.optimizer.zero_grad()

        # Softmax ensures weights sum to 1
        w = F.softmax(self.weights, dim=0)
        predictions = (features * w).sum(dim=1)

        # Binary cross-entropy: predict "will this be grounded?"
        loss = F.binary_cross_entropy_with_logits(predictions, labels)

        loss.backward()

        # Apply momentum smoothing
        self.velocity = self.config.momentum * self.velocity + self.weights.grad

        self.optimizer.step()

        return loss.item()

    def get_weights(self) -> Dict[str, float]:
        """Get current weights as dict."""
        w = F.softmax(self.weights, dim=0).detach().numpy()
        # Clamp to [min, max]
        w = [max(self.config.weight_min, min(self.config.weight_max, float(x))) for x in w]
        return {
            "emotional": w[0],
            "recency": w[1],
            "access": w[2],
            "social": w[3],
        }

    async def persist_weights(self, db_conn) -> None:
        """Save weights to st_learned_weights."""
        weights = self.get_weights()
        now_ms = int(time.time() * 1000)

        for component, value in weights.items():
            await db_conn.execute(
                """
                INSERT INTO st_learned_weights
                    (param_id, param_key, param_scope, scope_id, space_id, current_value,
                     prior_value, confidence, sample_count, last_updated_at, version,
                     previous_value, created_at, updated_at)
                VALUES ($1, $2, 'space', $3, $3, $4, $5, $6, $7, $8, 1, NULL, $8, $8)
                ON CONFLICT (space_id, param_key, param_scope, scope_id)
                DO UPDATE SET
                    previous_value = st_learned_weights.current_value,
                    current_value = $4,
                    sample_count = st_learned_weights.sample_count + $7,
                    version = st_learned_weights.version + 1,
                    last_updated_at = $8,
                    updated_at = $8
                """,
                generate_ulid(),
                f"importance_{component}",
                self.space_id,
                value,
                0.35 if component == "emotional" else 0.25 if component == "recency" else 0.20,
                0.8,  # confidence
                len(weights),  # sample_count increment
                now_ms,
            )
```

**Training Data Query** (from Dossier C.2.1.1):

```sql
SELECT
    emotional_score, recency_score, access_score, social_score,
    CASE WHEN was_grounded THEN 1.0 ELSE 0.0 END AS label,
    (EXTRACT(EPOCH FROM NOW()) - created_at) / 86400.0 AS days_ago
FROM st_importance_feedback
WHERE space_id = :space_id
  AND created_at > :cutoff  -- Last 30 days
ORDER BY created_at DESC;
```

**Stability Controls** (from Dossier C.2.1.2):

| Control | Implementation | Config |
|---------|----------------|--------|
| Momentum smoothing | `velocity = 0.9 × velocity + gradient` | `P03_IMPORTANCE_MOMENTUM = 0.9` |
| Weight clamping | `max(0.05, min(0.60, w_i))` per weight | `P03_IMPORTANCE_WEIGHT_MIN/MAX` |
| Normalization | Softmax ensures sum = 1.0 | Built into algorithm |
| Rollback trigger | 3 nights with increasing loss → revert to prior_value | `P03_IMPORTANCE_ROLLBACK_THRESHOLD = 3` |

**Rollback Logic**:

```python
async def check_rollback(self, current_loss: float, db_conn) -> bool:
    """Check if we should rollback to static priors."""
    # Get last 3 nights' losses from st_consolidation_audit
    recent_losses = await db_conn.fetch(
        """
        SELECT quality_at_update FROM st_learned_weights
        WHERE space_id = $1 AND param_key LIKE 'importance_%'
        ORDER BY updated_at DESC LIMIT 3
        """,
        self.space_id,
    )

    if len(recent_losses) >= 3:
        losses = [r["quality_at_update"] for r in recent_losses]
        if losses[0] > losses[1] > losses[2]:  # 3 consecutive increases
            await self._rollback_to_priors(db_conn)
            return True
    return False

async def _rollback_to_priors(self, db_conn) -> None:
    """Rollback to static prior weights."""
    await db_conn.execute(
        """
        UPDATE st_learned_weights
        SET current_value = prior_value,
            rollback_eligible = FALSE,
            updated_at = $2
        WHERE space_id = $1 AND param_key LIKE 'importance_%'
        """,
        self.space_id,
        int(time.time() * 1000),
    )
```

**Deliverables**:

- [ ] Create `k0/modules/consolidation/algorithms/importance_weight_learner.py`
- [ ] `WeightLearnerConfig` dataclass: `learning_rate=0.01`, `momentum=0.9`, `min_samples=500`, `weight_min=0.05`, `weight_max=0.60`
- [ ] `ImportanceWeightLearner` class with PyTorch tensors
- [ ] `train_step(features, labels)` → gradient descent with BCE loss
- [ ] `get_weights()` → returns clamped dict
- [ ] `persist_weights(db_conn)` → upsert to `st_learned_weights`
- [ ] `check_rollback(current_loss, db_conn)` → 3-night rollback check
- [ ] Wire to nightly P03 consolidation cycle (after R8, before shutdown)

**Acceptance Criteria**:

- [ ] Weights adapt toward patterns in `st_feedback_signals` after 500+ samples
- [ ] Each weight stays in [0.05, 0.60] (no single component dominates)
- [ ] Weights sum to 1.0 (softmax normalization)
- [ ] 3 consecutive nights of increasing loss triggers rollback
- [ ] `st_learned_weights` records `previous_value` and `version` for audit

**Test File**: `tests/k0/pipelines/p03/test_r1_importance_learner.py`

**Test Cases**:

1. `test_train_step_reduces_loss` — loss decreases after 10 steps
2. `test_weights_sum_to_one` — softmax normalization verified
3. `test_weight_clamping` — weights stay in [0.05, 0.60]
4. `test_momentum_smoothing` — velocity accumulates correctly
5. `test_persist_weights_upsert` — INSERT on first save, UPDATE on second
6. `test_rollback_after_3_nights` — 3 increasing losses → prior values restored
7. `test_rollback_sets_flag` — `rollback_eligible=FALSE` after rollback

**Blocked By**: 4.1.1, 4.1.2

**Blocks**: 4.1.6, 4.1.8

---

#### Issue 4.1.6 — Implement cold start strategy for importance weights

**Status**: COMPLETED

**Implementation Summary**:

- Added `get_weights_with_cold_start()` method to ImportanceScorer (~180 lines)
- 3-level fallback: per-space → global → static priors
- Progressive blending formula: α = sample_count / 500
- Blending behavior: 0-99 samples (static), 100-499 (blend), 500+ (learned)
- Added `_blend_weights()` helper for weight interpolation
- 20 tests in `test_r1_cold_start.py`

**Files Changed**:

- `k0/modules/consolidation/algorithms/importance_scorer.py` (updated with cold start)
- `tests/k0/pipelines/p03/test_r1_cold_start.py` (NEW)

**Spec Reference**:

- [Dossier §4.2.2.2](../pipelines/P03_consolidation_dossier_v2.md#4222-cold-start-strategy) — Cold Start Strategy
- [Dossier Appendix C.2.1.1](../pipelines/P03_consolidation_dossier_v2.md#appendix-c-algorithm-specifications) (lines 20540-20700) — Minimum samples threshold

**Goal**: Graceful behavior for new spaces lacking learned weights, with progressive blending as data accumulates.

**Existing Infrastructure to Use**:

| Component | Location | How to Use |
|-----------|----------|------------|
| `st_learned_weights` table | Migration 0040 | Query `sample_count` to determine cold start state |
| `ImportanceScorer.get_weights()` | Issue 4.1.1 | Integrate fallback hierarchy |
| Static priors | Dossier §4.2.2 | `[0.35, 0.25, 0.20, 0.20]` for emotional/recency/access/social |

**Cold Start Fallback Hierarchy** (from Dossier §4.2.2.2):

```
1. Per-space learned weights (if sample_count >= 500)
2. Global learned weights (if space weights unavailable)
3. Static priors (if no learned weights exist)
   → emotional=0.35, recency=0.25, access=0.20, social=0.20
```

**Progressive Blending** (for 100 ≤ samples < 500):

```python
# File: k0/modules/consolidation/algorithms/importance_scorer.py (extend Issue 4.1.1)

async def get_weights_with_cold_start(self, space_id: str) -> Dict[str, float]:
    """
    Get importance weights with cold start fallback hierarchy.

    Blending formula for 100 ≤ samples < 500:
        α = sample_count / 500
        blended = α × learned + (1 - α) × static_prior

    Returns: Dict of weights (always sums to 1.0)
    """
    static_priors = {
        "emotional": 0.35,
        "recency": 0.25,
        "access": 0.20,
        "social": 0.20,
    }

    # Step 1: Try per-space weights
    space_weights = await self._load_weights(space_id, scope="space")
    if space_weights and space_weights.sample_count >= 500:
        return space_weights.weights

    # Step 2: Try global weights
    global_weights = await self._load_weights(space_id, scope="global")
    if global_weights and global_weights.sample_count >= 500:
        return global_weights.weights

    # Step 3: Progressive blending (100 ≤ samples < 500)
    learned = space_weights or global_weights
    if learned and learned.sample_count >= 100:
        alpha = learned.sample_count / 500.0
        blended = {}
        for key in static_priors:
            blended[key] = alpha * learned.weights.get(key, static_priors[key]) + (1 - alpha) * static_priors[key]
        return blended

    # Step 4: Pure cold start - use static priors
    return static_priors

async def _load_weights(self, space_id: str, scope: str) -> Optional[LearnedWeights]:
    """Load weights from st_learned_weights by scope."""
    rows = await self.db_conn.fetch(
        """
        SELECT param_key, current_value, sample_count
        FROM st_learned_weights
        WHERE space_id = $1
          AND param_scope = $2
          AND param_key LIKE 'importance_%'
        """,
        space_id if scope == "space" else "__global__",
        scope,
    )
    if not rows:
        return None

    weights = {}
    total_samples = 0
    for row in rows:
        component = row["param_key"].replace("importance_", "")
        weights[component] = row["current_value"]
        total_samples = max(total_samples, row["sample_count"])

    return LearnedWeights(weights=weights, sample_count=total_samples)
```

**Blending Behavior Table**:

| Sample Count | Behavior | α (blend factor) |
|--------------|----------|------------------|
| 0-99 | Pure static priors | 0.0 |
| 100 | Begin blending | 0.20 |
| 250 | Half blending | 0.50 |
| 400 | Mostly learned | 0.80 |
| 500+ | Pure learned weights | 1.0 |

**Configuration**:

| Config Key | Default | Purpose |
|------------|---------|---------|
| `P03_IMPORTANCE_MIN_SAMPLES` | 500 | Threshold for full learned weights |
| `P03_IMPORTANCE_BLEND_START` | 100 | When to start blending |
| `P03_IMPORTANCE_STATIC_EMOTIONAL` | 0.35 | Static prior |
| `P03_IMPORTANCE_STATIC_RECENCY` | 0.25 | Static prior |
| `P03_IMPORTANCE_STATIC_ACCESS` | 0.20 | Static prior |
| `P03_IMPORTANCE_STATIC_SOCIAL` | 0.20 | Static prior |

**Deliverables**:

- [ ] Add `get_weights_with_cold_start(space_id)` to `ImportanceScorer`
- [ ] Implement 3-level fallback: per-space → global → static
- [ ] Progressive blending formula: `α = sample_count / 500`
- [ ] `LearnedWeights` dataclass with `weights: Dict[str, float]` and `sample_count: int`
- [ ] Query helper `_load_weights(space_id, scope)` for st_learned_weights
- [ ] Config keys in `k0/config/p03.py` or environment

**Acceptance Criteria**:

- [ ] Brand new space (0 samples) returns `[0.35, 0.25, 0.20, 0.20]` without error
- [ ] Space with 250 samples returns 50/50 blend of learned and static
- [ ] Space with 500+ samples returns pure learned weights
- [ ] Global fallback used when per-space weights unavailable
- [ ] Weights always sum to 1.0 (verify normalization)

**Test File**: `tests/k0/pipelines/p03/test_r1_cold_start.py`

**Test Cases**:

1. `test_cold_start_zero_samples` — returns static priors
2. `test_cold_start_50_samples` — still returns static priors (below 100)
3. `test_blend_100_samples` — 20% learned, 80% static
4. `test_blend_250_samples` — 50% learned, 50% static
5. `test_blend_400_samples` — 80% learned, 20% static
6. `test_full_learned_500_samples` — 100% learned weights
7. `test_global_fallback` — per-space unavailable, uses global
8. `test_weights_sum_to_one` — blended weights normalized

**Blocked By**: 4.1.1, 4.1.5

**Blocks**: 4.1.8

---

#### Issue 4.1.7 — R1 metrics: importance distribution, hebbian update counts

**Status**: COMPLETED

**Spec Reference**:

- [Dossier §8.2](../pipelines/P03_consolidation_dossier_v2.md#82-prometheus-metrics) — Prometheus Metrics
- [observability.py](../../k0/pipelines/p03/observability.py) — `PhaseTransitionLogger`, `PhaseEventType`
- [feedback_consumer.py](../../k0/pipelines/p03/feedback_consumer.py) — `P03FeedbackMetrics` dataclass pattern

**Goal**: Instrument R1 phase with observability metrics for importance scoring and Hebbian learning.

**Existing Infrastructure**:

| Component | Location | How to Use |
| --------- | -------- | ---------- |
| `PhaseTransitionLogger` | `k0/pipelines/p03/observability.py` | Log phase start/complete/fail events |
| `PhaseEventType` enum | `k0/pipelines/p03/observability.py` | PHASE_START, PHASE_COMPLETE, PHASE_FAIL, PHASE_SKIP |
| `P03FeedbackMetrics` | `k0/pipelines/p03/feedback_consumer.py` | Dataclass pattern for metrics aggregation |

**R1 Metrics Specification** (from Dossier §8.2):

```python
# File: k0/pipelines/p03/observability.py (extend existing)

from dataclasses import dataclass, field
from typing import Dict

@dataclass
class R1PhaseMetrics:
    """Metrics collected during R1 hippocampal replay phase."""

    # Importance scoring metrics
    importance_scores: List[float] = field(default_factory=list)
    importance_weight_values: Dict[str, float] = field(default_factory=dict)
    importance_weight_samples: int = 0
    importance_weight_source: str = "static"  # "space", "global", "static", "blended"

    # Hebbian learning metrics
    hebbian_edges_created: int = 0
    hebbian_edges_updated: int = 0
    hebbian_edges_pruned: int = 0
    hebbian_weight_values: List[float] = field(default_factory=list)
    anti_hebbian_decreases: int = 0

    # Timing metrics
    r1_duration_ms: float = 0.0
    importance_scoring_ms: float = 0.0
    hebbian_update_ms: float = 0.0

    def to_prometheus_metrics(self) -> Dict[str, float]:
        """Convert to Prometheus metric values."""
        return {
            "p03_importance_score_mean": (
                sum(self.importance_scores) / len(self.importance_scores)
                if self.importance_scores else 0.0
            ),
            "p03_importance_score_min": min(self.importance_scores) if self.importance_scores else 0.0,
            "p03_importance_score_max": max(self.importance_scores) if self.importance_scores else 1.0,
            "p03_importance_weight_sample_count": float(self.importance_weight_samples),
            "p03_hebbian_edges_created": float(self.hebbian_edges_created),
            "p03_hebbian_edges_updated": float(self.hebbian_edges_updated),
            "p03_hebbian_edges_pruned": float(self.hebbian_edges_pruned),
            "p03_hebbian_weight_mean": (
                sum(self.hebbian_weight_values) / len(self.hebbian_weight_values)
                if self.hebbian_weight_values else 0.0
            ),
            "p03_anti_hebbian_decreases": float(self.anti_hebbian_decreases),
            "p03_r1_duration_ms": self.r1_duration_ms,
        }
```

**Prometheus Metrics to Register**:

| Metric Name | Type | Description | Labels |
| ----------- | ---- | ----------- | ------ |
| `p03_importance_score_distribution` | Histogram | Distribution of importance scores | `space_id` |
| `p03_importance_weight_emotional` | Gauge | Current emotional weight value | `space_id`, `source` |
| `p03_importance_weight_recency` | Gauge | Current recency weight value | `space_id`, `source` |
| `p03_importance_weight_access` | Gauge | Current access weight value | `space_id`, `source` |
| `p03_importance_weight_social` | Gauge | Current social weight value | `space_id`, `source` |
| `p03_importance_weight_sample_count` | Gauge | Samples used for weight learning | `space_id` |
| `p03_importance_weight_drift_30d` | Gauge | Weight drift over 30 days (from dossier) | `space_id`, `component` |
| `p03_hebbian_edges_created` | Counter | New edges created this cycle | `space_id` |
| `p03_hebbian_edges_updated` | Counter | Existing edges updated | `space_id` |
| `p03_hebbian_edges_pruned` | Counter | Edges pruned (weight < 0.05) | `space_id` |
| `p03_hebbian_weight_distribution` | Histogram | Distribution of edge weights | `space_id` |
| `p03_anti_hebbian_decreases` | Counter | Anti-Hebbian weight decreases | `space_id`, `signal_type` |
| `p03_r1_duration_ms` | Histogram | R1 phase execution time | `space_id` |

**Integration Pattern** (extend `PhaseTransitionLogger`):

```python
# File: k0/pipelines/p03/orchestrator.py

async def run_r1_replay(self, batch: List[HippEvent]) -> R1PhaseMetrics:
    """Execute R1 phase with instrumentation."""
    metrics = R1PhaseMetrics()
    start_time = time.monotonic()

    self.phase_logger.log_phase_start("R1", {"batch_size": len(batch)})

    try:
        # Importance scoring (existing from 4.1.1-4.1.3)
        t0 = time.monotonic()
        scores = await self.importance_scorer.score_batch(batch)
        metrics.importance_scoring_ms = (time.monotonic() - t0) * 1000
        metrics.importance_scores = [s.score for s in scores]

        # Hebbian learning (existing from 4.1.4-4.1.5)
        t0 = time.monotonic()
        hebbian_result = await self.hebbian_learner.update_edges(batch)
        metrics.hebbian_update_ms = (time.monotonic() - t0) * 1000
        metrics.hebbian_edges_created = hebbian_result.created
        metrics.hebbian_edges_updated = hebbian_result.updated
        metrics.hebbian_edges_pruned = hebbian_result.pruned

        metrics.r1_duration_ms = (time.monotonic() - start_time) * 1000
        self.phase_logger.log_phase_complete("R1", metrics.to_prometheus_metrics())

        return metrics

    except Exception as e:
        self.phase_logger.log_phase_fail("R1", str(e))
        raise
```

**Performance Constraint** (from Dossier §8.2):

- R1 duration must be **<5% of cycle time** (360s × 0.05 = 18s max)
- Log warning if exceeding 10s, error if exceeding 18s

**Deliverables**:

- [ ] `R1PhaseMetrics` dataclass in `k0/pipelines/p03/observability.py`
- [ ] Prometheus metric registration (12 metrics as listed above)
- [ ] Integration with existing `PhaseTransitionLogger`
- [ ] `to_prometheus_metrics()` method for metric export
- [ ] Performance threshold logging (<5% of cycle time)
- [ ] Weight source tracking ("space", "global", "static", "blended")

**Acceptance Criteria**:

- [ ] All 12 metrics registered and emitting values
- [ ] Histogram buckets for importance scores: [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
- [ ] Histogram buckets for edge weights: [0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1.0]
- [ ] Duration histogram buckets: [100, 500, 1000, 5000, 10000, 18000] ms
- [ ] `weight_source` label correctly reflects cold start fallback path
- [ ] Warning logged when R1 exceeds 10s

**Blocked By**: 4.1.1, 4.1.4, 4.1.5, 4.1.6

**Blocks**: 4.1.8

---

#### Issue 4.1.8 — Unit + integration tests for R1 ReplayCoordinator

**Status**: COMPLETED

**Spec Reference**:

- [test_p03_feedback_consumer.py](../../tests/k0/pipelines/p03/test_p03_feedback_consumer.py) — Test pattern reference
- [Dossier §4.2](../pipelines/P03_consolidation_dossier_v2.md#42-r1-hippocampal-replay) — R1 specifications for assertions

**Goal**: Comprehensive test coverage proving correctness of importance scoring and Hebbian learning.

**Existing Test Infrastructure**:

| Component | Location | Pattern to Follow |
| --------- | -------- | ----------------- |
| `test_p03_feedback_consumer.py` | `tests/k0/pipelines/p03/` | FeedbackType enum testing |
| `conftest.py` | `tests/k0/pipelines/p03/` | Fixtures for P03 components |
| `test_p03_integration.py` | `tests/k0/pipelines/p03/` | Integration test pattern |

**Test File Structure** (61 tests across 8 files):

```text
tests/k0/pipelines/p03/
├── test_r1_importance_scorer.py          # 12 tests (Issues 4.1.1-4.1.3)
├── test_r1_hebbian_learner.py            # 14 tests (Issues 4.1.4-4.1.5)
├── test_r1_cold_start.py                 # 8 tests (Issue 4.1.6)
├── test_r1_metrics.py                    # 6 tests (Issue 4.1.7)
├── test_r1_integration.py                # 10 tests (full R1 phase)
├── test_r1_weight_persistence.py         # 5 tests (st_learned_weights)
├── test_r1_edge_cases.py                 # 4 tests (boundary conditions)
└── test_r1_performance.py                # 2 tests (timing constraints)
```

**Test Categories and Cases**:

**1. Importance Scoring Tests** (`test_r1_importance_scorer.py`):

```python
# From Issue 4.1.1-4.1.3 specifications

class TestImportanceScorer:
    def test_high_emotion_scores_higher(self):
        """High-emotion event scores higher than low-emotion event."""
        high_emotion = HippEvent(emotional_salience=0.9, ...)
        low_emotion = HippEvent(emotional_salience=0.1, ...)
        assert scorer.score(high_emotion) > scorer.score(low_emotion)

    def test_recency_decay_formula(self):
        """Recency decay produces expected curve: e^(-t/τ), τ=7 days."""
        # From dossier §4.2.1: recency = exp(-hours_since / (7 * 24))
        event_1_hour = HippEvent(timestamp=now - timedelta(hours=1), ...)
        event_7_days = HippEvent(timestamp=now - timedelta(days=7), ...)
        assert abs(scorer._recency_score(event_1_hour) - 0.994) < 0.01
        assert abs(scorer._recency_score(event_7_days) - 0.368) < 0.01

    def test_softmax_normalization_sums_to_one(self):
        """Softmax ensures weights sum to 1.0."""
        weights = scorer.get_weights(space_id)
        assert abs(sum(weights.values()) - 1.0) < 0.001

    def test_component_weights_within_bounds(self):
        """Each component weight in [0.0, 1.0]."""
        for component, value in weights.items():
            assert 0.0 <= value <= 1.0

    def test_batch_scoring_matches_individual(self):
        """Batch scoring returns same results as individual scoring."""
        batch_scores = await scorer.score_batch(events)
        individual_scores = [await scorer.score(e) for e in events]
        assert batch_scores == individual_scores

    def test_emotional_salience_from_signal_strength(self):
        """Emotional salience derived from signal_strength field."""
        # From migration 0040: signal_strength FLOAT
        event = HippEvent(signal_strength=0.85, ...)
        assert scorer._emotional_score(event) == 0.85

    def test_access_frequency_log_normalization(self):
        """Access frequency normalized with log scale: log(count+1)/log(max+1)."""
        event_10_access = HippEvent(access_count=10, ...)
        event_100_access = HippEvent(access_count=100, ...)
        # log(11)/log(101) ≈ 0.52, log(101)/log(101) = 1.0
        assert scorer._access_score(event_10_access) < scorer._access_score(event_100_access)

    def test_social_score_from_entity_connections(self):
        """Social score based on entity connection count."""
        event = HippEvent(entity_connections=5, ...)
        assert scorer._social_score(event) > 0.0
```

**2. Hebbian Learning Tests** (`test_r1_hebbian_learner.py`):

```python
# From Issue 4.1.4-4.1.5 specifications

class TestHebbianLearner:
    def test_cooccurrence_increases_edge_weight(self):
        """Co-occurrence increases edge weight by Δw = lr × Δ_co × temporal_decay."""
        # From dossier C.2.2: Hebbian formula
        initial_weight = 0.5
        learner.update_edges([event_a, event_b])  # co-occur in batch
        new_weight = learner.get_edge_weight(event_a.id, event_b.id)
        assert new_weight > initial_weight

    def test_anti_hebbian_decreases_weight(self):
        """Anti-Hebbian signal decreases edge weight."""
        # From dossier C.2.2.1: Δw = -anti_lr × current × confidence × penalty
        initial_weight = 0.8
        learner.apply_anti_hebbian(
            edge_id, signal_type="ASSOCIATION_WRONG", confidence=0.9
        )
        assert learner.get_edge_weight(edge_id) < initial_weight

    def test_penalty_multipliers_by_signal_type(self):
        """Correct penalty multipliers per signal type."""
        # From dossier C.2.2.1:
        assert learner.PENALTY_MULTIPLIERS == {
            "ENTITY_MERGE_REJECTED": 0.2,
            "ASSOCIATION_WRONG": 0.3,
            "MUTUAL_EXCLUSION": 0.4,
            "CONTRADICTION": 0.15,
        }

    def test_edge_pruning_at_threshold(self):
        """Edge pruned when weight < 0.05 (C.2.2.5)."""
        learner.set_edge_weight(edge_id, 0.04)
        learner.prune_weak_edges()
        assert not learner.edge_exists(edge_id)

    def test_edge_resurrection(self):
        """Pruned edge resurrected with weight max(0.7, 0.5 + old × 0.5)."""
        # From dossier C.2.2.2
        old_weight = 0.3
        learner.resurrect_edge(edge_id, old_weight)
        new_weight = learner.get_edge_weight(edge_id)
        expected = max(0.7, 0.5 + old_weight * 0.5)  # 0.7
        assert abs(new_weight - expected) < 0.01

    def test_adaptive_learning_rate(self):
        """LR decays with update count: lr = lr_max × exp(-decay × count) + lr_min."""
        # From dossier C.2.2.3: lr_max=0.3, lr_min=0.05, decay_factor=0.1
        lr_0 = learner.get_learning_rate(update_count=0)
        lr_10 = learner.get_learning_rate(update_count=10)
        lr_50 = learner.get_learning_rate(update_count=50)
        assert lr_0 == 0.35  # 0.3 + 0.05
        assert 0.15 < lr_10 < 0.25
        assert abs(lr_50 - 0.05) < 0.02  # converges to lr_min

    def test_weight_clamping(self):
        """Weights clamped to [0.0, 1.0] (C.2.2.5)."""
        learner.update_edge(edge_id, delta=1.5)  # would exceed 1.0
        assert learner.get_edge_weight(edge_id) == 1.0
        learner.update_edge(edge_id, delta=-2.0)  # would go negative
        assert learner.get_edge_weight(edge_id) == 0.0

    def test_saturation_control_log_scale(self):
        """Co-occurrence capped via log-scale (C.2.2.4)."""
        # From dossier: cap_threshold=50
        for _ in range(100):  # Many co-occurrences
            learner.update_edges([event_a, event_b])
        weight = learner.get_edge_weight(event_a.id, event_b.id)
        assert weight < 1.0  # Not saturated at 1.0
```

**3. Cold Start Tests** (`test_r1_cold_start.py`):

```python
# From Issue 4.1.6 specifications

class TestColdStart:
    def test_cold_start_zero_samples(self):
        """New space returns static priors [0.35, 0.25, 0.20, 0.20]."""
        weights = await scorer.get_weights_with_cold_start(new_space_id)
        assert weights == {"emotional": 0.35, "recency": 0.25, "access": 0.20, "social": 0.20}

    def test_cold_start_50_samples(self):
        """Below 100 samples still returns static priors."""
        setup_weights(space_id, sample_count=50)
        weights = await scorer.get_weights_with_cold_start(space_id)
        assert weights == STATIC_PRIORS

    def test_blend_100_samples(self):
        """At 100 samples: 20% learned, 80% static."""
        setup_weights(space_id, sample_count=100, emotional=0.50)
        weights = await scorer.get_weights_with_cold_start(space_id)
        # α = 100/500 = 0.2
        expected_emotional = 0.2 * 0.50 + 0.8 * 0.35  # 0.38
        assert abs(weights["emotional"] - 0.38) < 0.01

    def test_blend_250_samples(self):
        """At 250 samples: 50% learned, 50% static."""
        setup_weights(space_id, sample_count=250, emotional=0.50)
        weights = await scorer.get_weights_with_cold_start(space_id)
        expected_emotional = 0.5 * 0.50 + 0.5 * 0.35  # 0.425
        assert abs(weights["emotional"] - 0.425) < 0.01

    def test_full_learned_500_samples(self):
        """At 500+ samples: pure learned weights."""
        setup_weights(space_id, sample_count=600, emotional=0.45)
        weights = await scorer.get_weights_with_cold_start(space_id)
        assert weights["emotional"] == 0.45

    def test_global_fallback(self):
        """Per-space unavailable, uses global weights."""
        setup_global_weights(sample_count=500, emotional=0.40)
        weights = await scorer.get_weights_with_cold_start(space_without_weights)
        assert weights["emotional"] == 0.40

    def test_weights_sum_to_one(self):
        """Blended weights always sum to 1.0."""
        for sample_count in [0, 50, 100, 250, 400, 500, 1000]:
            setup_weights(space_id, sample_count=sample_count)
            weights = await scorer.get_weights_with_cold_start(space_id)
            assert abs(sum(weights.values()) - 1.0) < 0.001
```

**4. Integration Tests** (`test_r1_integration.py`):

```python
class TestR1Integration:
    async def test_full_r1_phase_processes_batch(self):
        """Full R1 phase processes event batch correctly."""
        batch = [create_hipp_event() for _ in range(50)]
        metrics = await orchestrator.run_r1_replay(batch)

        assert len(metrics.importance_scores) == 50
        assert all(0.0 <= s <= 1.0 for s in metrics.importance_scores)
        assert metrics.r1_duration_ms > 0

    async def test_r1_creates_hebbian_edges(self):
        """R1 creates edges for co-occurring events."""
        batch = create_cooccurring_batch(size=10)
        metrics = await orchestrator.run_r1_replay(batch)
        assert metrics.hebbian_edges_created > 0

    async def test_r1_with_cold_start_space(self):
        """R1 works correctly with brand new space."""
        new_space = create_new_space()
        batch = [create_hipp_event(space_id=new_space.id) for _ in range(10)]
        metrics = await orchestrator.run_r1_replay(batch)
        assert metrics.importance_weight_source == "static"

    async def test_r1_emits_phase_events(self):
        """R1 emits phase start/complete events."""
        with capture_phase_events() as events:
            await orchestrator.run_r1_replay(batch)
        assert events[0].type == PhaseEventType.PHASE_START
        assert events[-1].type == PhaseEventType.PHASE_COMPLETE

    async def test_r1_performance_under_18s(self):
        """R1 completes within 5% of cycle time (18s max)."""
        large_batch = [create_hipp_event() for _ in range(1000)]
        metrics = await orchestrator.run_r1_replay(large_batch)
        assert metrics.r1_duration_ms < 18000
```

**5. Weight Persistence Tests** (`test_r1_weight_persistence.py`):

```python
class TestWeightPersistence:
    async def test_weights_persisted_to_st_learned_weights(self):
        """Weight updates persisted to st_learned_weights table."""
        await learner.update_weight("importance_emotional", 0.42, space_id)
        row = await db.fetchrow(
            "SELECT current_value FROM st_learned_weights WHERE param_key = $1",
            "importance_emotional"
        )
        assert row["current_value"] == 0.42

    async def test_version_incremented_on_update(self):
        """Version column incremented on each update."""
        v1 = await get_version("importance_emotional")
        await learner.update_weight("importance_emotional", 0.43, space_id)
        v2 = await get_version("importance_emotional")
        assert v2 == v1 + 1

    async def test_previous_value_tracked(self):
        """previous_value column stores old value for rollback."""
        await learner.update_weight("importance_emotional", 0.50, space_id)
        await learner.update_weight("importance_emotional", 0.55, space_id)
        row = await db.fetchrow("SELECT previous_value ...")
        assert row["previous_value"] == 0.50

    async def test_rollback_eligible_flag(self):
        """rollback_eligible set when quality_at_update > threshold."""
        await learner.update_weight(..., quality=0.8)
        row = await db.fetchrow("SELECT rollback_eligible ...")
        assert row["rollback_eligible"] is True
```

**Deliverables**:

- [ ] `test_r1_importance_scorer.py` — 12 tests for scoring algorithm
- [ ] `test_r1_hebbian_learner.py` — 14 tests for Hebbian updates
- [ ] `test_r1_cold_start.py` — 8 tests for cold start strategy
- [ ] `test_r1_metrics.py` — 6 tests for observability
- [ ] `test_r1_integration.py` — 10 tests for full R1 phase
- [ ] `test_r1_weight_persistence.py` — 5 tests for st_learned_weights
- [ ] `test_r1_edge_cases.py` — 4 tests for boundary conditions
- [ ] `test_r1_performance.py` — 2 tests for timing constraints
- [ ] All tests use real components, no mocking except for DB fixtures

**Acceptance Criteria**:

- [ ] 61 tests total passing
- [ ] Coverage > 90% for R1 code paths
- [ ] No mocking of core algorithms
- [ ] Integration tests exercise full phase execution
- [ ] Performance tests validate <18s constraint
- [ ] All assertions grounded in dossier specifications

**Blocked By**: 4.1.1, 4.1.2, 4.1.3, 4.1.4, 4.1.5, 4.1.6, 4.1.7

**Blocks**: Epic 4.2 (R2)

---

### Epic 4.2 — R2 Episodic clustering (DBSCAN + adaptive params)

> **Scope**: Implement R2 Neocortical Integration phase — episodic clustering using DBSCAN.
> **Module**: M18 EpisodicIntegrator
> **Dossier**: Section 4.3, Appendix C.3

---

#### Issue 4.2.1 — Implement composite distance function (semantic + temporal)

**Status**: COMPLETED

**Spec Reference**:

- [Dossier Appendix C.3.1](../pipelines/P03_consolidation_dossier_v2.md#c31-dbscan-density-based-clustering) (lines 21570-21740) — EpisodicDBSCAN algorithm
- [event_state.py](../../k0/pipelines/p03/event_state.py) (lines 147-162) — Clustering fields: `cluster_id`, `cluster_label`, `is_noise`, `centroid_distance`

**Goal**: Define distance metric for clustering events into episodes that combines semantic similarity and temporal proximity.

**Existing Infrastructure**:

| Component | Location | How to Use |
| --------- | -------- | ---------- |
| `P03EventState.embedding_768` | `k0/pipelines/p03/event_state.py` | 768-dim UltraBERT embedding |
| `P03EventState.timestamp` | `k0/pipelines/p03/event_state.py` | Epoch milliseconds |
| `P03EventState.centroid_distance` | `k0/pipelines/p03/event_state.py` | Set after clustering |
| `st_learned_weights` | Migration 0040 | Learnable `temporal_weight` parameter |

**Composite Distance Formula** (from Dossier C.3.1):

```
distance = (1 - temporal_weight) × cosine_distance(emb_a, emb_b)
         + temporal_weight × normalized_time_distance(ts_a, ts_b)
```

Where:

- `cosine_distance = 1 - cosine_similarity`
- `normalized_time_distance = min(1.0, abs(ts_a - ts_b) / max_temporal_gap_ms)`
- `max_temporal_gap_ms = 4 hours = 14,400,000 ms`

**Implementation**:

```python
# File: k0/modules/consolidation/algorithms/composite_distance.py

import numpy as np
from dataclasses import dataclass
from typing import Optional

@dataclass
class DBSCANParams:
    """Parameters for DBSCAN clustering (from Dossier C.3.1)."""
    eps: float = 0.25  # Max distance to cluster
    min_samples: int = 2  # Minimum events for core point
    temporal_weight: float = 0.3  # How much time affects distance
    max_temporal_gap_hours: float = 4.0  # Events >4h apart cannot cluster

    @property
    def max_temporal_gap_ms(self) -> int:
        return int(self.max_temporal_gap_hours * 3600 * 1000)


class CompositeDistance:
    """
    Composite distance for episodic clustering.

    Combines semantic similarity (cosine) and temporal proximity.
    Lower distance = more similar = should cluster together.

    Spec: Dossier Appendix C.3.1
    """

    def __init__(self, params: DBSCANParams):
        self.params = params

    def compute(self, event_a: "P03EventState", event_b: "P03EventState") -> float:
        """
        Compute composite distance between two events.

        Args:
            event_a: First event with embedding_768 and timestamp
            event_b: Second event with embedding_768 and timestamp

        Returns:
            Distance in [0.0, inf). Events >max_gap apart return inf.
        """
        # Step 1: Check temporal hard limit
        time_diff_ms = abs(event_a.timestamp - event_b.timestamp)
        if time_diff_ms > self.params.max_temporal_gap_ms:
            return float("inf")  # Cannot cluster

        # Step 2: Compute semantic distance (1 - cosine similarity)
        emb_a = np.array(event_a.embedding_768)
        emb_b = np.array(event_b.embedding_768)

        # Cosine similarity (embeddings assumed L2-normalized)
        cos_sim = np.dot(emb_a, emb_b)
        semantic_dist = 1.0 - cos_sim  # [0.0, 2.0]

        # Step 3: Compute normalized temporal distance
        temporal_dist = time_diff_ms / self.params.max_temporal_gap_ms  # [0.0, 1.0]

        # Step 4: Weighted combination
        composite = (
            (1 - self.params.temporal_weight) * semantic_dist
            + self.params.temporal_weight * temporal_dist
        )

        return float(composite)

    def build_distance_matrix(self, events: list) -> np.ndarray:
        """
        Build pairwise distance matrix for DBSCAN.

        Complexity: O(n^2)

        Returns:
            n×n symmetric distance matrix
        """
        n = len(events)
        distances = np.zeros((n, n))

        for i in range(n):
            for j in range(i + 1, n):
                dist = self.compute(events[i], events[j])
                distances[i, j] = dist
                distances[j, i] = dist

        return distances
```

**Distance Interpretation** (from Dossier C.3.1):

| Distance | Interpretation | Clustering Behavior |
| -------- | -------------- | ------------------- |
| 0.0 | Identical (same embedding, same time) | Same cluster |
| 0.0-0.25 | Very similar (eps default) | Will cluster if both core/border |
| 0.25-0.50 | Moderately similar | May cluster with adjusted eps |
| 0.50-1.0 | Dissimilar | Unlikely to cluster |
| >1.0 | Very different | Separate clusters |
| inf | Exceeds temporal gap | Cannot cluster |

**Configuration**:

| Config Key | Default | Range | Purpose |
| ---------- | ------- | ----- | ------- |
| `P03_DBSCAN_EPS` | 0.25 | [0.15, 0.40] | Max distance for clustering |
| `P03_DBSCAN_TEMPORAL_WEIGHT` | 0.30 | [0.1, 0.5] | Time influence on distance |
| `P03_DBSCAN_MAX_TEMPORAL_GAP_HOURS` | 4.0 | [1.0, 8.0] | Hard temporal limit |

**Deliverables**:

- [ ] `DBSCANParams` dataclass in `k0/modules/consolidation/algorithms/composite_distance.py`
- [ ] `CompositeDistance` class with `compute(event_a, event_b)` method
- [ ] `build_distance_matrix(events)` returning n×n numpy array
- [ ] Cosine distance from `P03EventState.embedding_768` (768-dim)
- [ ] Normalized time distance capped at 1.0
- [ ] Hard temporal cutoff returning `float("inf")`
- [ ] Load `temporal_weight` from `st_learned_weights` (fallback to 0.3)

**Acceptance Criteria**:

- [ ] Events with cos_sim > 0.75 AND time_diff < 1h get distance < 0.25
- [ ] Events >4 hours apart get distance = inf
- [ ] Distance matrix is symmetric
- [ ] Distance values in [0.0, 2.0] for valid pairs

**Test File**: `tests/k0/pipelines/p03/test_r2_composite_distance.py`

**Test Cases**:

1. `test_identical_events_zero_distance` — same embedding, same time = 0.0
2. `test_semantic_only_distance` — different embeddings, same time
3. `test_temporal_only_distance` — same embedding, different times
4. `test_temporal_hard_cutoff` — >4h apart returns inf
5. `test_distance_matrix_symmetric` — matrix[i,j] == matrix[j,i]
6. `test_weighted_combination` — verify formula with temporal_weight=0.3

**Blocked By**: None (first R2 issue)

**Blocks**: 4.2.3, 4.2.4

---

#### Issue 4.2.2 — Implement pre-clustering episode split

**Status**: COMPLETED

**Spec Reference**:

- [Dossier Appendix C.3.1.1](../pipelines/P03_consolidation_dossier_v2.md#c311-pre-clustering-episode-split) (lines 21385-21465) — EpisodeSplitter algorithm
- [event_state.py](../../k0/pipelines/p03/event_state.py) — `P03EventState.timestamp`, `content_type`

**Goal**: Split long event sequences BEFORE DBSCAN to prevent cross-activity clusters (e.g., morning gym + afternoon meeting becoming one episode).

**Problem Statement** (from Dossier C.3.1.1):

> Events spanning >4 hours create poor DBSCAN clusters.
> Example: Morning gym (7 AM) + lunch (12 PM) + evening meeting (5 PM) cluster as single "Day Episode" (wrong).
> Result: Silhouette score < 0.3, clusters too broad for K1 retrieval.

**Existing Infrastructure**:

| Component | Location | How to Use |
| --------- | -------- | ---------- |
| `P03EventState.timestamp` | `k0/pipelines/p03/event_state.py` | Epoch ms for time gap detection |
| `st_hipp_events.location_geohash` | Migration schema | Geohash for location detection |
| `st_hipp_events.activity_type` | Migration schema | Activity type changes |

**Split Signals** (priority order from Dossier C.3.1.1):

| Priority | Signal | Condition | Example | Data Source |
| -------- | ------ | --------- | ------- | ----------- |
| 1 | Location Change | geohash prefix differs by >4 chars | Home (9q9p) → Office (9q8y) | `location_geohash` |
| 2 | Activity Change | `activity_type` changes | MEAL → OUTING | `activity_type` |
| 3 | Time Gap | Gap > 30 minutes | Lunch break, commute | Timestamp diff |
| 4 | Hard Limit | Episode > 4 hours | Force split at 4-hour mark | Configurable |

**Implementation**:

```python
# File: k0/modules/consolidation/algorithms/episode_splitter.py

from typing import List, Optional
from dataclasses import dataclass

@dataclass
class SplitConfig:
    """Configuration for episode splitting (from Dossier C.3.1.1)."""
    max_episode_hours: float = 4.0  # Hard limit
    time_gap_minutes: float = 30.0  # Time gap threshold
    geohash_distance_threshold: int = 4  # Chars difference for location change


class EpisodeSplitter:
    """
    Pre-split event sequences before DBSCAN clustering.

    Spec: Dossier Appendix C.3.1.1
    """

    def __init__(self, config: Optional[SplitConfig] = None):
        self.config = config or SplitConfig()

    def split_long_sequences(
        self, events: List["P03EventState"]
    ) -> List[List["P03EventState"]]:
        """
        Pre-split event sequences before DBSCAN.

        Args:
            events: Sorted list of events (by timestamp)

        Returns:
            List of event sub-sequences, each becomes DBSCAN input
        """
        if not events:
            return []

        sequences: List[List["P03EventState"]] = []
        current_sequence: List["P03EventState"] = [events[0]]

        for i in range(1, len(events)):
            prev_event = events[i - 1]
            curr_event = events[i]

            if self._detect_break(prev_event, curr_event):
                # Break detected - start new sequence
                sequences.append(current_sequence)
                current_sequence = [curr_event]
            else:
                # Continue current sequence
                current_sequence.append(curr_event)

        # Add final sequence
        if current_sequence:
            sequences.append(current_sequence)

        return sequences

    def _detect_break(
        self, prev: "P03EventState", curr: "P03EventState"
    ) -> bool:
        """
        Detect if a break should occur between events.

        Checks in priority order:
        1. Location change (geohash prefix differs by >4 chars)
        2. Activity type change
        3. Time gap > 30 minutes
        4. Hard limit (4 hours)
        """
        # Time difference in hours
        time_diff_ms = curr.timestamp - prev.timestamp
        time_diff_hours = time_diff_ms / 3600000.0

        # Priority 1: Location change
        if hasattr(prev, 'location_geohash') and hasattr(curr, 'location_geohash'):
            if prev.location_geohash and curr.location_geohash:
                if self._geohash_distance(prev.location_geohash, curr.location_geohash) > self.config.geohash_distance_threshold:
                    return True

        # Priority 2: Activity type change
        if hasattr(prev, 'activity_type') and hasattr(curr, 'activity_type'):
            if prev.activity_type and curr.activity_type:
                if prev.activity_type != curr.activity_type:
                    return True

        # Priority 3: Time gap > 30 minutes
        time_gap_hours = self.config.time_gap_minutes / 60.0
        if time_diff_hours > time_gap_hours:
            return True

        # Priority 4: Hard limit (4 hours from sequence start)
        if time_diff_hours > self.config.max_episode_hours:
            return True

        return False

    def _geohash_distance(self, gh1: str, gh2: str) -> int:
        """
        Compute character difference in geohash prefixes.

        Returns: Number of differing characters in first 6 chars
        """
        min_len = min(len(gh1), len(gh2), 6)
        diff = 0
        for i in range(min_len):
            if gh1[i] != gh2[i]:
                diff += 1
        return diff
```

**Integration with DBSCAN** (from Dossier C.3.1.1):

```python
# R2 Phase Pipeline
events = load_events_from_r1()  # Sorted by timestamp

# Step 1: Pre-split long sequences
splitter = EpisodeSplitter()
sequences = splitter.split_long_sequences(events)

# Step 2: Run DBSCAN on each sequence separately
all_clusters = []
for sequence in sequences:
    clusters = EpisodicDBSCAN().cluster(sequence)
    all_clusters.extend(clusters)

# Step 3: Continue with centroid calculation
```

**Configuration**:

| Config Key | Default | Purpose |
| ---------- | ------- | ------- |
| `P03_DBSCAN_MAX_EPISODE_HOURS` | 4.0 | Hard limit for episode duration |
| `P03_DBSCAN_TIME_GAP_MINUTES` | 30 | Time gap threshold |
| `P03_DBSCAN_GEOHASH_DISTANCE` | 4 | Location change threshold |

**Metrics** (from Dossier C.3.1.1):

| Metric Name | Type | Description |
| ----------- | ---- | ----------- |
| `p03_episode_splits_total` | Counter | Total pre-splits applied |
| `p03_episode_split_by_type` | Counter | Splits by signal type (location/activity/time/hard_limit) |
| `p03_sequences_per_batch` | Histogram | Number of sequences after splitting |

**Deliverables**:

- [ ] `SplitConfig` dataclass with `max_episode_hours`, `time_gap_minutes`, `geohash_distance_threshold`
- [ ] `EpisodeSplitter` class in `k0/modules/consolidation/algorithms/episode_splitter.py`
- [ ] `split_long_sequences(events)` returning `List[List[P03EventState]]`
- [ ] `_detect_break(prev, curr)` checking 4 signals in priority order
- [ ] `_geohash_distance(gh1, gh2)` for location change detection
- [ ] Metrics for split counts by type

**Acceptance Criteria**:

- [ ] Morning gym (7 AM) + afternoon meeting (1 PM) split into 2 sequences
- [ ] Events within same activity and <30min apart stay in same sequence
- [ ] Location change (different geohash) triggers split
- [ ] Hard limit at 4 hours always triggers split
- [ ] Silhouette score improves from ~0.3 to >0.5 after pre-splitting

**Test File**: `tests/k0/pipelines/p03/test_r2_episode_splitter.py`

**Test Cases**:

1. `test_no_split_short_sequence` — events <30min apart, same location
2. `test_split_on_time_gap` — 45min gap triggers split
3. `test_split_on_location_change` — different geohash triggers split
4. `test_split_on_activity_change` — MEAL → WORK triggers split
5. `test_hard_limit_4_hours` — 5-hour sequence split at 4h mark
6. `test_priority_order` — location takes precedence over time
7. `test_empty_input` — returns empty list
8. `test_single_event` — returns list with one single-event sequence

**Blocked By**: None

**Blocks**: 4.2.3, 4.2.4

---

#### Issue 4.2.3 — Implement DBSCAN clustering with configurable eps/min_samples

**Status**: COMPLETED

**Spec Reference**:

- [Dossier Appendix C.3.1](../pipelines/P03_consolidation_dossier_v2.md#c31-dbscan-density-based-clustering) (lines 21570-21740) — EpisodicDBSCAN algorithm
- [Dossier Appendix C.3.2](../pipelines/P03_consolidation_dossier_v2.md#c32-centroid-calculation-episode-embedding) (lines 21744-21880) — CentroidCalculator
- [phase_outputs.py](../../k0/pipelines/p03/phase_outputs.py) (lines 56-94) — `EpisodeCluster` dataclass
- [event_state.py](../../k0/pipelines/p03/event_state.py) (lines 155-162) — `cluster_id`, `cluster_label`, `is_noise`, `centroid_distance`

**Goal**: Cluster hippocampal events into coherent episodes using DBSCAN with composite distance metric.

**Existing Infrastructure**:

| Component | Location | How to Use |
| --------- | -------- | ---------- |
| `EpisodeCluster` dataclass | `k0/pipelines/p03/phase_outputs.py` | Output structure for clusters |
| `P03EventState.cluster_id` | `k0/pipelines/p03/event_state.py` | Set cluster assignment |
| `P03EventState.cluster_label` | `k0/pipelines/p03/event_state.py` | DBSCAN label (-1 = noise) |
| `P03EventState.is_noise` | `k0/pipelines/p03/event_state.py` | Mark noise events |
| `P03EventState.centroid_distance` | `k0/pipelines/p03/event_state.py` | Distance to cluster center |
| `CompositeDistance` | Issue 4.2.1 | Distance metric for clustering |
| `st_learned_weights` | Migration 0040 | Learnable `eps`, `min_samples` |

**EpisodeCluster Dataclass** (existing in phase_outputs.py):

```python
@dataclass
class EpisodeCluster:
    cluster_id: str  # ULID
    member_event_ids: List[str] = field(default_factory=list)
    centroid_embedding_id: Optional[str] = None
    dominant_sentiment: float = 0.0
    dominant_emotion: str = ""
    temporal_start: int = 0  # MILLISECONDS
    temporal_end: int = 0  # MILLISECONDS
    location_hint: Optional[str] = None
    participants_json: str = "[]"
    activity_type: str = ""
    cohesion_score: float = 0.0  # Intra-cluster similarity
    title: str = ""
    summary: str = ""

    @property
    def event_count(self) -> int:
        return len(self.member_event_ids)

    @property
    def duration_ms(self) -> int:
        return self.temporal_end - self.temporal_start
```

**Implementation**:

```python
# File: k0/modules/consolidation/algorithms/episodic_dbscan.py

import numpy as np
from sklearn.cluster import DBSCAN
from typing import List, Dict
from dataclasses import dataclass
import ulid

from k0.pipelines.p03.algorithms.composite_distance import CompositeDistance, DBSCANParams
from k0.pipelines.p03.phase_outputs import EpisodeCluster
from k0.pipelines.p03.event_state import P03EventState


class EpisodicDBSCAN:
    """
    Modified DBSCAN for episodic memory clustering.

    Uses composite distance (semantic + temporal) instead of spatial distance.
    Wraps scikit-learn DBSCAN with precomputed distance matrix.

    Spec: Dossier Appendix C.3.1
    """

    def __init__(self, params: DBSCANParams):
        self.params = params
        self.distance_calculator = CompositeDistance(params)

    def cluster(self, events: List[P03EventState]) -> List[EpisodeCluster]:
        """
        Run DBSCAN clustering on events.

        Args:
            events: List of events (pre-split by EpisodeSplitter)

        Returns:
            List of EpisodeCluster objects (noise events have is_noise=True)
        """
        if len(events) < self.params.min_samples:
            # Not enough events for clustering
            return self._create_noise_clusters(events)

        # Step 1: Build distance matrix
        distances = self.distance_calculator.build_distance_matrix(events)

        # Step 2: Run DBSCAN with precomputed distances
        clustering = DBSCAN(
            eps=self.params.eps,
            min_samples=self.params.min_samples,
            metric="precomputed",
        ).fit(distances)

        # Step 3: Group events by cluster label
        label_to_events: Dict[int, List[P03EventState]] = {}
        for idx, label in enumerate(clustering.labels_):
            if label not in label_to_events:
                label_to_events[label] = []
            label_to_events[label].append(events[idx])
            # Update event state
            events[idx].cluster_label = label
            events[idx].is_noise = (label == -1)

        # Step 4: Convert to EpisodeCluster objects
        clusters = []
        for label, cluster_events in label_to_events.items():
            cluster = self._create_cluster(cluster_events, label)
            clusters.append(cluster)

            # Set cluster_id on events
            for event in cluster_events:
                event.cluster_id = cluster.cluster_id

        # Step 5: Compute centroid distances
        self._compute_centroid_distances(clusters, events)

        return clusters

    def _create_cluster(
        self, events: List[P03EventState], label: int
    ) -> EpisodeCluster:
        """Create EpisodeCluster from grouped events."""
        cluster_id = str(ulid.new()) if label != -1 else f"noise-{ulid.new()}"

        # Temporal bounds
        timestamps = [e.timestamp for e in events]
        temporal_start = min(timestamps)
        temporal_end = max(timestamps)

        # Dominant sentiment (average)
        sentiments = [e.sentiment_score for e in events if e.sentiment_score]
        dominant_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0.0

        # Cohesion score (intra-cluster similarity)
        cohesion = self._compute_cohesion(events)

        return EpisodeCluster(
            cluster_id=cluster_id,
            member_event_ids=[e.event_id for e in events],
            dominant_sentiment=dominant_sentiment,
            temporal_start=temporal_start,
            temporal_end=temporal_end,
            cohesion_score=cohesion,
        )

    def _compute_cohesion(self, events: List[P03EventState]) -> float:
        """
        Compute intra-cluster similarity (cohesion).

        Average pairwise cosine similarity within cluster.
        """
        if len(events) < 2:
            return 1.0

        embeddings = [np.array(e.embedding_768) for e in events if e.embedding_768]
        if len(embeddings) < 2:
            return 1.0

        total_sim = 0.0
        count = 0
        for i in range(len(embeddings)):
            for j in range(i + 1, len(embeddings)):
                total_sim += np.dot(embeddings[i], embeddings[j])
                count += 1

        return total_sim / count if count > 0 else 1.0

    def _compute_centroid_distances(
        self, clusters: List[EpisodeCluster], events: List[P03EventState]
    ) -> None:
        """
        Compute and set centroid_distance for each event.

        Uses issue 4.2.4 centroid calculation.
        """
        event_map = {e.event_id: e for e in events}

        for cluster in clusters:
            if cluster.cohesion_score == 0 or len(cluster.member_event_ids) < 2:
                continue

            # Compute centroid embedding
            embeddings = [
                np.array(event_map[eid].embedding_768)
                for eid in cluster.member_event_ids
                if event_map[eid].embedding_768
            ]
            if not embeddings:
                continue

            centroid = np.mean(embeddings, axis=0)
            centroid = centroid / np.linalg.norm(centroid)  # L2 normalize

            # Set distance for each event
            for eid in cluster.member_event_ids:
                event = event_map[eid]
                if event.embedding_768:
                    emb = np.array(event.embedding_768)
                    dist = 1.0 - np.dot(emb, centroid)
                    event.centroid_distance = float(dist)

    def _create_noise_clusters(self, events: List[P03EventState]) -> List[EpisodeCluster]:
        """Create individual noise clusters for events below min_samples."""
        clusters = []
        for event in events:
            event.cluster_label = -1
            event.is_noise = True
            cluster = EpisodeCluster(
                cluster_id=f"noise-{ulid.new()}",
                member_event_ids=[event.event_id],
                temporal_start=event.timestamp,
                temporal_end=event.timestamp,
                cohesion_score=1.0,
            )
            event.cluster_id = cluster.cluster_id
            clusters.append(cluster)
        return clusters
```

**DBSCAN Output Labels**:

| Label | Meaning | Action |
| ----- | ------- | ------ |
| -1 | Noise (singleton) | Create micro-episode, `is_noise=True` |
| 0+ | Cluster ID | Group into episode |

**Configuration** (learnable via st_learned_weights):

| Config Key | Default | Range | Purpose |
| ---------- | ------- | ----- | ------- |
| `P03_DBSCAN_EPS` | 0.25 | [0.15, 0.40] | Max distance for clustering |
| `P03_DBSCAN_MIN_SAMPLES` | 2 | [2, 5] | Min events for core point |

**Deliverables**:

- [ ] `EpisodicDBSCAN` class in `k0/modules/consolidation/algorithms/episodic_dbscan.py`
- [ ] `cluster(events)` returning `List[EpisodeCluster]`
- [ ] Use `CompositeDistance` from Issue 4.2.1 with `metric="precomputed"`
- [ ] Load `eps`, `min_samples` from `st_learned_weights` (fallback to defaults)
- [ ] Set `cluster_id`, `cluster_label`, `is_noise`, `centroid_distance` on each event
- [ ] Noise events (label=-1) get individual micro-episode clusters
- [ ] Compute `cohesion_score` for each cluster

**Acceptance Criteria**:

- [ ] Semantically similar + temporally proximate events cluster together
- [ ] Silhouette score > 0.5 on test batches
- [ ] All events have `cluster_id` and `cluster_label` set
- [ ] Noise events marked with `is_noise=True`
- [ ] `centroid_distance` computed for all non-noise events
- [ ] Uses sklearn.cluster.DBSCAN with precomputed distances

**Test File**: `tests/k0/pipelines/p03/test_r2_episodic_dbscan.py`

**Test Cases**:

1. `test_cluster_similar_events` — high cos_sim + close time → same cluster
2. `test_separate_dissimilar_events` — low cos_sim → different clusters
3. `test_noise_handling` — singleton events marked `is_noise=True`
4. `test_event_state_updated` — `cluster_id`, `cluster_label` set on events
5. `test_centroid_distance_computed` — non-noise events have distance > 0
6. `test_cohesion_score_computed` — clusters have valid cohesion [0, 1]
7. `test_temporal_bounds_correct` — `temporal_start` ≤ all timestamps ≤ `temporal_end`
8. `test_min_samples_below_threshold` — all events become noise if < min_samples

**Blocked By**: 4.2.1, 4.2.2

**Blocks**: 4.2.4, 4.2.5, 4.2.6, 4.2.7

---

#### Issue 4.2.4 — Write episode candidates to staged writes container

**Status**: COMPLETED

**Spec Reference**:

- [Dossier Appendix C.3.2](../pipelines/P03_consolidation_dossier_v2.md#c32-centroid-calculation-episode-embedding) (lines 21744-21880) — CentroidCalculator, weighting strategies
- [phase_outputs.py](../../k0/pipelines/p03/phase_outputs.py) (lines 56-94) — `EpisodeCluster` dataclass
- [serializer.py](../../k0/pipelines/p03/serializer.py) (lines 520-525) — `centroid_embedding_id` serialization

**Goal**: Collect R2 outputs into staging container for R6/R7 commit. NO database writes in R2 — all writes staged.

**Existing Infrastructure**:

| Component | Location | How to Use |
| --------- | -------- | ---------- |
| `EpisodeCluster` | `k0/pipelines/p03/phase_outputs.py` | Output dataclass for clusters |
| `P03PhaseOutputs` | `k0/pipelines/p03/phase_outputs.py` | Container for all phase outputs |
| Serializer | `k0/pipelines/p03/serializer.py` | Serialize `centroid_embedding_id` |
| `st_epi` | Table schema | Target for episode records |

**CentroidCalculator** (from Dossier C.3.2):

```python
# File: k0/modules/consolidation/algorithms/centroid_calculator.py

import numpy as np
from typing import List, Optional
from dataclasses import dataclass

from k0.pipelines.p03.phase_outputs import EpisodeCluster
from k0.pipelines.p03.event_state import P03EventState


class CentroidCalculator:
    """
    Computes episode centroid embedding from constituent events.

    Spec: Dossier Appendix C.3.2
    """

    def compute_weights(
        self,
        events: List[P03EventState],
        strategy: str = "hybrid"
    ) -> np.ndarray:
        """
        Compute weight for each event based on strategy.

        Strategies (from Dossier C.3.2):
        - uniform: All events contribute equally
        - importance: Weight by importance_score
        - recency: Weight by timestamp (recent = higher)
        - hybrid: 0.7 × importance + 0.3 × recency (default)
        """
        n = len(events)

        if strategy == "uniform":
            return np.ones(n) / n

        elif strategy == "importance":
            weights = np.array([e.importance_score for e in events])
            weights = weights + 0.01  # Avoid zero weights
            return weights / weights.sum()

        elif strategy == "recency":
            timestamps = np.array([e.timestamp for e in events])
            if timestamps.max() == timestamps.min():
                return np.ones(n) / n
            weights = (timestamps - timestamps.min()) / (timestamps.max() - timestamps.min() + 1)
            weights = weights + 0.1  # Ensure non-zero
            return weights / weights.sum()

        elif strategy == "hybrid":
            importance = np.array([e.importance_score for e in events])
            timestamps = np.array([e.timestamp for e in events])
            if timestamps.max() == timestamps.min():
                recency = np.ones(n)
            else:
                recency = (timestamps - timestamps.min()) / (timestamps.max() - timestamps.min() + 1)
            weights = 0.7 * importance + 0.3 * recency
            weights = weights + 0.01
            return weights / weights.sum()

        else:
            return np.ones(n) / n

    def compute_centroid(
        self,
        events: List[P03EventState],
        strategy: str = "hybrid",
        normalize: bool = True
    ) -> np.ndarray:
        """
        Compute weighted centroid of event embeddings.

        Formula: centroid = sum(weight_i × embedding_i) for all i

        Args:
            events: List of events with embedding_768
            strategy: Weighting strategy
            normalize: L2-normalize for cosine similarity compatibility

        Returns:
            768-dim centroid embedding
        """
        weights = self.compute_weights(events, strategy)

        # Stack embeddings into matrix
        embeddings = np.stack([np.array(e.embedding_768) for e in events if e.embedding_768])

        # Weighted sum
        centroid = np.sum(embeddings * weights[:, np.newaxis], axis=0)

        # L2 normalize
        if normalize:
            norm = np.linalg.norm(centroid)
            if norm > 0:
                centroid = centroid / norm

        return centroid

    def compute_variance(
        self,
        events: List[P03EventState],
        centroid: np.ndarray
    ) -> float:
        """
        Compute variance from centroid (cluster cohesion).

        Low variance = tight cluster = coherent episode
        High variance = loose cluster = may need splitting
        """
        embeddings = np.stack([np.array(e.embedding_768) for e in events if e.embedding_768])

        # Average squared distance from centroid (1 - cos_sim)
        similarities = np.dot(embeddings, centroid)
        distances = 1 - similarities
        variance = np.mean(distances ** 2)

        return float(variance)
```

**EpisodeCandidate for Staged Writes**:

```python
# File: k0/modules/consolidation/algorithms/episode_candidate.py

from dataclasses import dataclass, field
from typing import List, Optional
import numpy as np

@dataclass
class EpisodeCandidate:
    """
    Episode candidate for R6/R7 staged write.

    Contains all data needed to create st_epi record.
    No DB write in R2 — this is passed to R6/R7.
    """
    # Identity
    cluster_id: str  # From EpisodeCluster
    space_id: str

    # Event membership
    event_ids: List[str] = field(default_factory=list)
    event_count: int = 0

    # Centroid embedding (768-dim)
    centroid_embedding: Optional[List[float]] = None
    centroid_embedding_id: Optional[str] = None  # For st_vec reference

    # Temporal bounds (milliseconds)
    temporal_start: int = 0
    temporal_end: int = 0

    # Quality metrics
    cohesion_score: float = 0.0  # Intra-cluster similarity
    variance: float = 0.0  # Distance from centroid
    is_noise: bool = False  # Singleton micro-episode

    # Derived attributes
    dominant_sentiment: float = 0.0
    dominant_emotion: str = ""
    location_hint: Optional[str] = None
    activity_type: str = ""
    participants_json: str = "[]"

    # Confidence for reconciliation
    confidence_score: float = 0.0

    @property
    def duration_ms(self) -> int:
        return self.temporal_end - self.temporal_start


@dataclass
class R2StagedOutput:
    """
    Complete R2 output for staging.

    Contains all episode candidates and batch metadata.
    """
    # Episode candidates
    episode_candidates: List[EpisodeCandidate] = field(default_factory=list)

    # Batch metadata
    cluster_count: int = 0
    noise_count: int = 0
    avg_cluster_size: float = 0.0
    total_events_processed: int = 0

    # Quality metrics
    batch_silhouette_score: float = 0.0
    batch_cohesion_avg: float = 0.0

    def add_candidate(self, candidate: EpisodeCandidate) -> None:
        """Add episode candidate and update metadata."""
        self.episode_candidates.append(candidate)
        if candidate.is_noise:
            self.noise_count += 1
        else:
            self.cluster_count += 1
        self.total_events_processed += candidate.event_count

    def finalize(self) -> None:
        """Compute final aggregate metrics."""
        non_noise = [c for c in self.episode_candidates if not c.is_noise]
        if non_noise:
            self.avg_cluster_size = sum(c.event_count for c in non_noise) / len(non_noise)
            self.batch_cohesion_avg = sum(c.cohesion_score for c in non_noise) / len(non_noise)
```

**R2 Phase Staging Integration**:

```python
# File: k0/pipelines/p03/phases/r2_phase.py

async def run_r2_phase(
    events: List[P03EventState],
    space_id: str,
    params: DBSCANParams
) -> R2StagedOutput:
    """
    Execute R2 episodic clustering phase.

    Returns staged output (no DB writes).
    """
    output = R2StagedOutput()
    centroid_calc = CentroidCalculator()

    # Step 1: Pre-split long sequences
    splitter = EpisodeSplitter()
    sequences = splitter.split_long_sequences(events)

    # Step 2: Cluster each sequence
    dbscan = EpisodicDBSCAN(params)
    all_clusters: List[EpisodeCluster] = []
    for sequence in sequences:
        clusters = dbscan.cluster(sequence)
        all_clusters.extend(clusters)

    # Step 3: Create episode candidates for each cluster
    event_map = {e.event_id: e for e in events}
    for cluster in all_clusters:
        cluster_events = [event_map[eid] for eid in cluster.member_event_ids]

        # Compute centroid embedding
        centroid = centroid_calc.compute_centroid(cluster_events, strategy="hybrid")
        variance = centroid_calc.compute_variance(cluster_events, centroid)

        candidate = EpisodeCandidate(
            cluster_id=cluster.cluster_id,
            space_id=space_id,
            event_ids=cluster.member_event_ids,
            event_count=cluster.event_count,
            centroid_embedding=centroid.tolist(),
            temporal_start=cluster.temporal_start,
            temporal_end=cluster.temporal_end,
            cohesion_score=cluster.cohesion_score,
            variance=variance,
            is_noise=(len(cluster.member_event_ids) == 1),
            dominant_sentiment=cluster.dominant_sentiment,
            confidence_score=cluster.cohesion_score,  # Use cohesion as confidence
        )
        output.add_candidate(candidate)

    # Step 4: Compute batch silhouette score
    if len(all_clusters) > 1:
        output.batch_silhouette_score = compute_silhouette(events, all_clusters)

    output.finalize()
    return output
```

**Weighting Strategy Selection** (from Dossier C.3.2):

| Strategy | Best For | Trade-off |
| -------- | -------- | --------- |
| Uniform | Short, coherent episodes | May dilute important events |
| Importance | Episodes with key moments | May over-weight single event |
| Recency | Ongoing/evolving episodes | May miss important early context |
| Hybrid | General use (default) | Balanced but more complex |

**Configuration**:

| Config Key | Default | Purpose |
| ---------- | ------- | ------- |
| `P03_CENTROID_WEIGHTING_STRATEGY` | "hybrid" | How to weight event embeddings |
| `P03_CENTROID_NORMALIZE` | True | L2-normalize for cosine compatibility |

**Deliverables**:

- [ ] `CentroidCalculator` class in `k0/modules/consolidation/algorithms/centroid_calculator.py`
- [ ] `compute_weights(events, strategy)` supporting uniform/importance/recency/hybrid
- [ ] `compute_centroid(events, strategy)` returning 768-dim embedding
- [ ] `compute_variance(events, centroid)` for cohesion tracking
- [ ] `EpisodeCandidate` dataclass with all st_epi fields
- [ ] `R2StagedOutput` container with `episode_candidates`, metadata
- [ ] NO database writes in R2 — all candidates staged for R6/R7
- [ ] Manifest metadata: `cluster_count`, `noise_count`, `avg_cluster_size`

**Acceptance Criteria**:

- [ ] All clusters converted to `EpisodeCandidate` objects
- [ ] Centroid embedding is 768-dim and L2-normalized
- [ ] Variance computed for quality tracking
- [ ] `R2StagedOutput` contains all candidates + batch metadata
- [ ] No st_epi rows written until R7 phase
- [ ] `centroid_embedding_id` populated for st_vec reference

**Test File**: `tests/k0/pipelines/p03/test_r2_staged_output.py`

**Test Cases**:

1. `test_centroid_uniform_weighting` — all events contribute equally
2. `test_centroid_importance_weighting` — high importance = higher weight
3. `test_centroid_hybrid_weighting` — 70% importance + 30% recency
4. `test_centroid_l2_normalized` — centroid has unit norm
5. `test_variance_computed` — variance in [0, 1] range
6. `test_episode_candidate_created` — all fields populated
7. `test_staged_output_metadata` — cluster_count, noise_count correct
8. `test_no_db_writes` — verify no st_epi rows created in R2
9. `test_finalize_computes_aggregates` — avg_cluster_size, cohesion_avg

**Blocked By**: 4.2.1, 4.2.2, 4.2.3

**Blocks**: 4.2.7, 4.2.8

---

#### Issue 4.2.5 — Implement adaptive eps learning (silhouette-driven)

**Status**: COMPLETED

**Spec Reference**:

- [Dossier §4.3.1.1](../pipelines/P03_consolidation_dossier_v2.md#4311-adaptive-eps-learning) (lines 3247-3293) — Adaptive Eps Learning algorithm
- [st_learned_weights](../../k0/db/alembic/versions/0040_st_learned_weights.py) — Storage for learned `dbscan_eps`

**Goal**: Tune `eps` per-space based on cluster quality feedback (silhouette score optimization).

**Problem Statement** (from Dossier §4.3.1.1):

> Fixed `eps=0.25` doesn't suit all spaces:
>
> - **Tight spaces** (single-topic, focused users): Events cluster too broadly → need lower eps (0.15-0.20).
> - **Loose spaces** (multi-domain, diverse users): Events fail to cluster → need higher eps (0.30-0.40).

**Existing Infrastructure**:

| Component | Location | How to Use |
| --------- | -------- | ---------- |
| `st_learned_weights` | Migration 0040 | Store `dbscan_eps` per space |
| `R2StagedOutput.batch_silhouette_score` | Issue 4.2.4 | Get silhouette from R2 output |
| `R2StagedOutput.avg_cluster_size` | Issue 4.2.4 | Get avg cluster size |
| `R2StagedOutput.noise_count` | Issue 4.2.4 | Compute singleton rate |

**Storage Pattern** (from Dossier §4.3.1.1):

| param_key | param_scope | Default | Range | Target Metric |
| --------- | ----------- | ------- | ----- | ------------- |
| `dbscan_eps` | `space` | 0.25 | [0.15, 0.40] | silhouette > 0.5 |

**Implementation**:

```python
# File: k0/modules/consolidation/algorithms/eps_adjuster.py

from dataclasses import dataclass
from typing import Optional
import math

@dataclass
class EpsAdjustmentConfig:
    """Configuration for adaptive eps learning (from Dossier §4.3.1.1)."""
    eps_min: float = 0.15
    eps_max: float = 0.40
    eps_step: float = 0.02
    silhouette_target: float = 0.5
    momentum: float = 0.9  # 90% old, 10% new
    cold_start_threshold: int = 100  # clusters before learning


class EpsAdjuster:
    """
    Adaptive eps learning via silhouette score optimization.

    Spec: Dossier §4.3.1.1
    """

    def __init__(self, config: Optional[EpsAdjustmentConfig] = None):
        self.config = config or EpsAdjustmentConfig()

    def adjust(
        self,
        current_eps: float,
        silhouette_score: float,
        avg_cluster_size: float,
        singleton_rate: float,
        total_clusters_formed: int,
    ) -> float:
        """
        Adjust eps based on cluster quality metrics.

        Algorithm (from Dossier §4.3.1.1):
        1. If silhouette < 0.5:
           - If avg_cluster_size > 10 → decrease eps (too loose)
           - If singleton_rate > 0.20 → increase eps (too tight)
        2. Apply momentum smoothing
        3. Clamp to bounds [0.15, 0.40]

        Returns:
            New eps value
        """
        # Cold start: use default until enough clusters formed
        if total_clusters_formed < self.config.cold_start_threshold:
            return current_eps

        # No adjustment needed if quality is good
        if silhouette_score >= self.config.silhouette_target:
            return current_eps

        # Determine adjustment direction
        eps_adjusted = current_eps
        if avg_cluster_size > 10:
            # Clusters too loose → decrease eps (tighter clustering)
            eps_adjusted = current_eps - self.config.eps_step
        elif singleton_rate > 0.20:
            # Too much noise → increase eps (looser clustering)
            eps_adjusted = current_eps + self.config.eps_step

        # Momentum smoothing: eps_new = 0.9 × eps_old + 0.1 × eps_adjusted
        eps_new = (
            self.config.momentum * current_eps
            + (1 - self.config.momentum) * eps_adjusted
        )

        # Clamp to bounds
        eps_new = max(self.config.eps_min, min(self.config.eps_max, eps_new))

        return eps_new

    async def load_eps(self, space_id: str, db_conn) -> float:
        """
        Load current eps from st_learned_weights.

        Fallback to 0.25 if not found.
        """
        row = await db_conn.fetchrow(
            """
            SELECT current_value FROM st_learned_weights
            WHERE space_id = $1 AND param_key = 'dbscan_eps' AND param_scope = 'space'
            """,
            space_id,
        )
        return row["current_value"] if row else 0.25

    async def save_eps(
        self,
        space_id: str,
        new_eps: float,
        silhouette_score: float,
        db_conn,
    ) -> None:
        """
        Persist updated eps to st_learned_weights.
        """
        await db_conn.execute(
            """
            INSERT INTO st_learned_weights (
                param_id, param_key, param_scope, scope_id, space_id,
                current_value, prior_value, confidence, sample_count, last_updated_at
            ) VALUES (
                gen_random_uuid(), 'dbscan_eps', 'space', $1, $1,
                $2, 0.25, $3, 1, (EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT
            )
            ON CONFLICT (space_id, param_key, param_scope, scope_id)
            DO UPDATE SET
                prior_value = st_learned_weights.current_value,
                current_value = $2,
                sample_count = st_learned_weights.sample_count + 1,
                last_updated_at = (EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT
            """,
            space_id,
            new_eps,
            silhouette_score,
        )
```

**Integration with R2 Phase**:

```python
# In r2_phase.py, after clustering:

async def run_r2_phase(...) -> R2StagedOutput:
    # ... existing clustering code ...

    # Adaptive eps learning (after sufficient clusters)
    eps_adjuster = EpsAdjuster()
    current_eps = await eps_adjuster.load_eps(space_id, db_conn)

    singleton_rate = output.noise_count / max(1, len(output.episode_candidates))

    new_eps = eps_adjuster.adjust(
        current_eps=current_eps,
        silhouette_score=output.batch_silhouette_score,
        avg_cluster_size=output.avg_cluster_size,
        singleton_rate=singleton_rate,
        total_clusters_formed=get_total_clusters(space_id),
    )

    if new_eps != current_eps:
        await eps_adjuster.save_eps(space_id, new_eps, output.batch_silhouette_score, db_conn)

    return output
```

**Configuration**:

| Config Key | Default | Purpose |
| ---------- | ------- | ------- |
| `P03_DBSCAN_EPS_MIN` | 0.15 | Lower bound |
| `P03_DBSCAN_EPS_MAX` | 0.40 | Upper bound |
| `P03_DBSCAN_EPS_STEP` | 0.02 | Adjustment increment |
| `P03_DBSCAN_SILHOUETTE_TARGET` | 0.5 | Quality threshold |
| `P03_DBSCAN_MOMENTUM` | 0.9 | Smoothing factor |
| `P03_DBSCAN_COLD_START_CLUSTERS` | 100 | Clusters before learning |

**Metrics** (from Dossier §4.3.1.1):

| Metric Name | Type | Description |
| ----------- | ---- | ----------- |
| `p03_dbscan_eps_current` | Gauge | Current eps value per space |
| `p03_dbscan_silhouette` | Gauge | Silhouette score [0, 1] |
| `p03_dbscan_avg_cluster_size` | Gauge | Average events per cluster |
| `p03_dbscan_eps_adjustments` | Counter | Total adjustments made |

**Deliverables**:

- [ ] `EpsAdjustmentConfig` dataclass in `k0/modules/consolidation/algorithms/eps_adjuster.py`
- [ ] `EpsAdjuster` class with `adjust()`, `load_eps()`, `save_eps()` methods
- [ ] Adjustment rules: silhouette < 0.5 AND avg_cluster_size > 10 → decrease eps
- [ ] Adjustment rules: silhouette < 0.5 AND singleton_rate > 0.20 → increase eps
- [ ] Momentum smoothing: `eps_new = 0.9 × eps_old + 0.1 × eps_adjusted`
- [ ] Bounds enforcement: `eps ∈ [0.15, 0.40]`
- [ ] Cold start: use default until 100 clusters formed
- [ ] Persist to `st_learned_weights` with key `dbscan_eps`, scope `space`

**Acceptance Criteria**:

- [ ] Per-space eps converges to value achieving silhouette > 0.5
- [ ] Eps stays within bounds [0.15, 0.40]
- [ ] Momentum prevents wild swings (max change ~0.002 per cycle)
- [ ] Cold start phase uses default 0.25
- [ ] Adjustment logged to `st_consolidation_audit`

**Test File**: `tests/k0/pipelines/p03/test_r2_eps_adjuster.py`

**Test Cases**:

1. `test_no_adjustment_above_silhouette_target` — silhouette > 0.5 returns same eps
2. `test_decrease_eps_large_clusters` — avg_size > 10, silhouette < 0.5 → eps decreases
3. `test_increase_eps_high_noise` — singleton_rate > 0.20, silhouette < 0.5 → eps increases
4. `test_momentum_smoothing` — verify 0.9/0.1 weighted average
5. `test_bounds_enforcement` — eps clamped to [0.15, 0.40]
6. `test_cold_start_no_adjustment` — < 100 clusters returns same eps
7. `test_load_eps_from_st_learned_weights` — loads existing value
8. `test_save_eps_upsert` — inserts or updates correctly

**Blocked By**: 4.2.3, 4.2.4

**Blocks**: 4.2.7, 4.2.8

---

#### Issue 4.2.6 — Implement adaptive min_samples learning

**Status**: COMPLETED

**Spec Reference**:

- [Dossier Appendix C.3.1.2](../pipelines/P03_consolidation_dossier_v2.md#c312-adaptive-min_samples) (lines 21480-21560) — MinSamplesAdjuster algorithm
- [st_learned_weights](../../k0/db/alembic/versions/0040_st_learned_weights.py) — Storage for learned `dbscan_min_samples`

**Goal**: Tune `min_samples` per-space based on noise level (singleton rate).

**Problem Statement** (from Dossier C.3.1.2):

> Fixed `min_samples=2` creates issues:
>
> - **Noisy spaces** (many singleton events): Too many micro-episodes → K1 retrieval cluttered.
> - **Sparse spaces** (few events): min_samples=2 prevents any clustering → no episodes formed.

**Existing Infrastructure**:

| Component | Location | How to Use |
| --------- | -------- | ---------- |
| `st_learned_weights` | Migration 0040 | Store `dbscan_min_samples` per space |
| `R2StagedOutput.noise_count` | Issue 4.2.4 | Count of singleton clusters |
| `R2StagedOutput.cluster_count` | Issue 4.2.4 | Total clusters formed |

**Adjustment Rules** (from Dossier C.3.1.2):

| Singleton Rate | Diagnosis | Action | New min_samples |
| -------------- | --------- | ------ | --------------- |
| > 20% | Too noisy (under-clustering) | Increase threshold | min_samples + 1 (max 5) |
| < 5% | Too strict (over-clustering) | Decrease threshold | min_samples - 1 (min 2) |
| 5-20% | Good balance | No change | Keep current |

**Implementation**:

```python
# File: k0/modules/consolidation/algorithms/min_samples_adjuster.py

from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)

@dataclass
class MinSamplesConfig:
    """Configuration for adaptive min_samples learning (from Dossier C.3.1.2)."""
    min_samples_min: int = 2
    min_samples_max: int = 5
    noise_threshold_high: float = 0.20  # Too noisy
    noise_threshold_low: float = 0.05   # Too strict


class MinSamplesAdjuster:
    """
    Adaptive min_samples learning based on singleton rate.

    Spec: Dossier Appendix C.3.1.2
    """

    def __init__(self, config: Optional[MinSamplesConfig] = None):
        self.config = config or MinSamplesConfig()

    def adjust(
        self,
        current_min_samples: int,
        singleton_rate: float,
    ) -> int:
        """
        Adjust min_samples based on singleton rate.

        Algorithm (from Dossier C.3.1.2):
        - singleton_rate > 0.20 → increase (too noisy)
        - singleton_rate < 0.05 → decrease (too strict)
        - 0.05 <= singleton_rate <= 0.20 → no change (good balance)

        Returns:
            New min_samples value in [2, 5]
        """
        if singleton_rate > self.config.noise_threshold_high:
            # Too much noise → increase threshold
            new_min_samples = min(
                self.config.min_samples_max,
                current_min_samples + 1
            )
            logger.info(
                f"min_samples INCREASE: singleton_rate={singleton_rate:.2f} > 0.20, "
                f"{current_min_samples} → {new_min_samples}"
            )
            return new_min_samples

        elif singleton_rate < self.config.noise_threshold_low:
            # Too strict → decrease threshold
            new_min_samples = max(
                self.config.min_samples_min,
                current_min_samples - 1
            )
            logger.info(
                f"min_samples DECREASE: singleton_rate={singleton_rate:.2f} < 0.05, "
                f"{current_min_samples} → {new_min_samples}"
            )
            return new_min_samples

        else:
            # Good balance - no change
            return current_min_samples

    async def load_min_samples(self, space_id: str, db_conn) -> int:
        """
        Load current min_samples from st_learned_weights.

        Fallback to 2 if not found.
        """
        row = await db_conn.fetchrow(
            """
            SELECT current_value FROM st_learned_weights
            WHERE space_id = $1 AND param_key = 'dbscan_min_samples' AND param_scope = 'space'
            """,
            space_id,
        )
        return int(row["current_value"]) if row else 2

    async def save_min_samples(
        self,
        space_id: str,
        new_min_samples: int,
        singleton_rate: float,
        db_conn,
    ) -> None:
        """
        Persist updated min_samples to st_learned_weights.
        """
        await db_conn.execute(
            """
            INSERT INTO st_learned_weights (
                param_id, param_key, param_scope, scope_id, space_id,
                current_value, prior_value, confidence, sample_count, last_updated_at
            ) VALUES (
                gen_random_uuid(), 'dbscan_min_samples', 'space', $1, $1,
                $2, 2.0, $3, 1, (EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT
            )
            ON CONFLICT (space_id, param_key, param_scope, scope_id)
            DO UPDATE SET
                prior_value = st_learned_weights.current_value,
                current_value = $2,
                sample_count = st_learned_weights.sample_count + 1,
                last_updated_at = (EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT
            """,
            space_id,
            float(new_min_samples),
            1.0 - singleton_rate,  # Confidence inversely related to noise
        )
```

**Evaluation Trigger** (from Dossier C.3.1.2):

```python
# After each P03 cycle:

# 1. Count singleton clusters
singletons = sum(1 for c in clusters if len(c.member_event_ids) == 1)

# 2. Compute rate
singleton_rate = singletons / len(clusters) if clusters else 0.0

# 3. Adjust if needed
adjuster = MinSamplesAdjuster()
new_min_samples = adjuster.adjust(current_min_samples, singleton_rate)

# 4. Store in st_learned_weights
await adjuster.save_min_samples(space_id, new_min_samples, singleton_rate, db_conn)
```

**Configuration**:

| Config Key | Default | Purpose |
| ---------- | ------- | ------- |
| `P03_DBSCAN_MIN_SAMPLES_MIN` | 2 | Lower bound |
| `P03_DBSCAN_MIN_SAMPLES_MAX` | 5 | Upper bound |
| `P03_DBSCAN_NOISE_THRESHOLD_HIGH` | 0.20 | Singleton rate ceiling |
| `P03_DBSCAN_NOISE_THRESHOLD_LOW` | 0.05 | Singleton rate floor |

**Metrics** (from Dossier C.3.1.2):

| Metric Name | Type | Description |
| ----------- | ---- | ----------- |
| `p03_dbscan_min_samples_current` | Gauge | Current min_samples per space |
| `p03_dbscan_singleton_rate` | Gauge | Singleton clusters / total clusters |
| `p03_dbscan_min_samples_adjustments` | Counter | Total adjustments made |

**Deliverables**:

- [ ] `MinSamplesConfig` dataclass in `k0/modules/consolidation/algorithms/min_samples_adjuster.py`
- [ ] `MinSamplesAdjuster` class with `adjust()`, `load_min_samples()`, `save_min_samples()`
- [ ] Adjustment rules: singleton_rate > 0.20 → increase (max 5)
- [ ] Adjustment rules: singleton_rate < 0.05 → decrease (min 2)
- [ ] Persist to `st_learned_weights` with key `dbscan_min_samples`, scope `space`
- [ ] Integration with R2 phase after clustering

**Acceptance Criteria**:

- [ ] min_samples stays within bounds [2, 5]
- [ ] High noise (>20% singletons) triggers increase
- [ ] Low noise (<5% singletons) triggers decrease
- [ ] Adjustment logged with before/after values
- [ ] Works correctly for new spaces (defaults to 2)

**Test File**: `tests/k0/pipelines/p03/test_r2_min_samples_adjuster.py`

**Test Cases**:

1. `test_increase_on_high_singleton_rate` — 25% singletons → min_samples + 1
2. `test_decrease_on_low_singleton_rate` — 3% singletons → min_samples - 1
3. `test_no_change_in_good_range` — 10% singletons → no change
4. `test_bounds_min` — cannot go below 2
5. `test_bounds_max` — cannot go above 5
6. `test_load_from_st_learned_weights` — loads existing value
7. `test_save_upsert` — inserts or updates correctly

**Blocked By**: 4.2.3, 4.2.4

**Blocks**: 4.2.7, 4.2.8

---

#### Issue 4.2.7 — Implement closed-loop cluster quality metrics

**Status**: NOT_STARTED

**Spec Reference**:

- [Dossier §4.3.4.1](../pipelines/P03_consolidation_dossier_v2.md#4341-closed-loop-cluster-quality) (lines 3308-3388) — Closed-Loop Cluster Quality
- [st_consolidation_audit](../../k0/db/alembic/versions/0036_st_consolidation_audit.py) — Audit trail table
- [st_feedback_signals](../../k0/db/alembic/versions/) — Feedback from K1/user

**Goal**: Track cluster quality for adaptive learning and observability using proxy metrics (no ground truth labels).

**Problem Statement** (from Dossier §4.3.4.1):

> No ground truth labels for clusters (unsupervised learning). Need proxy metrics to evaluate quality.

**Existing Infrastructure**:

| Component | Location | How to Use |
| --------- | -------- | ---------- |
| `st_consolidation_audit` | Migration 0036 | Store quality metrics per cycle |
| `st_feedback_signals` | Feedback table | K1 grounding, user corrections |
| `R2StagedOutput` | Issue 4.2.4 | Source of silhouette, singleton_rate |

**Quality Signals** (from Dossier §4.3.4.1):

| Signal | Source | Weight | Target | Interpretation |
| ------ | ------ | ------ | ------ | -------------- |
| Silhouette Score | sklearn (automated) | 0.40 | > 0.5 | Cluster cohesion and separation |
| Grounding Rate | K1 feedback (CLUSTER_GROUNDED) | 0.30 | > 0.6 | % of clusters used in K1 responses |
| Correction Rate | User feedback (CLUSTER_WRONG) | 0.20 | < 0.05 | User corrections per cluster |
| Singleton Rate | Noise proxy | 0.10 | < 0.20 | % of clusters with size=1 |

**Composite Quality Formula** (from Dossier §4.3.4.1):

```python
composite_quality = (
    0.40 × silhouette +
    0.30 × grounding_rate +
    0.20 × (1 - correction_rate) +
    0.10 × (1 - singleton_rate)
)

# Range: [0, 1] where 1.0 = perfect clustering
# Target: > 0.5 for acceptable quality
```

**Implementation**:

```python
# File: k0/modules/consolidation/algorithms/cluster_quality.py

from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime

@dataclass
class ClusterQualityMetrics:
    """
    Cluster quality metrics for closed-loop learning.

    Spec: Dossier §4.3.4.1
    """
    # Core metrics
    silhouette_score: float = 0.0
    grounding_rate: float = 0.0
    correction_rate: float = 0.0
    singleton_rate: float = 0.0

    # Derived
    composite_quality: float = 0.0

    # Counts for rate computation
    total_clusters: int = 0
    grounded_clusters: int = 0
    corrected_clusters: int = 0
    singleton_clusters: int = 0

    # Cycle metadata
    space_id: str = ""
    cycle_id: str = ""
    computed_at: int = 0  # milliseconds

    def compute_composite(self) -> float:
        """
        Compute composite quality score.

        Formula from Dossier §4.3.4.1:
        0.40 × silhouette + 0.30 × grounding + 0.20 × (1-correction) + 0.10 × (1-singleton)
        """
        self.composite_quality = (
            0.40 * self.silhouette_score
            + 0.30 * self.grounding_rate
            + 0.20 * (1.0 - self.correction_rate)
            + 0.10 * (1.0 - self.singleton_rate)
        )
        return self.composite_quality

    def compute_rates(self) -> None:
        """
        Compute rates from raw counts.
        """
        if self.total_clusters > 0:
            self.grounding_rate = self.grounded_clusters / self.total_clusters
            self.correction_rate = self.corrected_clusters / self.total_clusters
            self.singleton_rate = self.singleton_clusters / self.total_clusters


class ClusterQualityTracker:
    """
    Track and persist cluster quality metrics.

    Spec: Dossier §4.3.4.1
    """

    ALERT_THRESHOLD_LOW = 0.3
    CONSECUTIVE_FAILURES_FOR_ALERT = 3

    def __init__(self):
        self._recent_scores: List[float] = []  # Last N composite scores

    async def compute_metrics(
        self,
        space_id: str,
        r2_output: "R2StagedOutput",
        db_conn,
    ) -> ClusterQualityMetrics:
        """
        Compute quality metrics from R2 output and feedback signals.
        """
        metrics = ClusterQualityMetrics(
            space_id=space_id,
            cycle_id=str(ulid.new()),
            computed_at=int(datetime.now().timestamp() * 1000),
        )

        # From R2 output
        metrics.silhouette_score = r2_output.batch_silhouette_score
        metrics.total_clusters = r2_output.cluster_count + r2_output.noise_count
        metrics.singleton_clusters = r2_output.noise_count

        # From feedback signals (grounded clusters)
        grounded = await db_conn.fetchval(
            """
            SELECT COUNT(DISTINCT payload->>'epi_id') FROM st_feedback_signals
            WHERE space_id = $1 AND signal_type = 'CLUSTER_GROUNDED'
            AND created_at > (EXTRACT(EPOCH FROM NOW()) * 1000 - 86400000)::BIGINT
            """,
            space_id,
        )
        metrics.grounded_clusters = grounded or 0

        # From feedback signals (user corrections)
        corrected = await db_conn.fetchval(
            """
            SELECT COUNT(DISTINCT payload->>'epi_id') FROM st_feedback_signals
            WHERE space_id = $1 AND signal_type = 'CLUSTER_WRONG'
            AND created_at > (EXTRACT(EPOCH FROM NOW()) * 1000 - 86400000)::BIGINT
            """,
            space_id,
        )
        metrics.corrected_clusters = corrected or 0

        # Compute rates and composite
        metrics.compute_rates()
        metrics.compute_composite()

        return metrics

    async def persist_metrics(
        self,
        metrics: ClusterQualityMetrics,
        db_conn,
    ) -> None:
        """
        Persist metrics to st_consolidation_audit.
        """
        await db_conn.execute(
            """
            INSERT INTO st_consolidation_audit (
                audit_id, space_id, audit_type, action,
                details_json, created_at
            ) VALUES (
                gen_random_uuid(), $1, 'CLUSTER_QUALITY', 'METRICS_COMPUTED',
                $2, $3
            )
            """,
            metrics.space_id,
            json.dumps({
                "silhouette_score": metrics.silhouette_score,
                "grounding_rate": metrics.grounding_rate,
                "correction_rate": metrics.correction_rate,
                "singleton_rate": metrics.singleton_rate,
                "composite_quality": metrics.composite_quality,
                "total_clusters": metrics.total_clusters,
                "grounded_clusters": metrics.grounded_clusters,
                "corrected_clusters": metrics.corrected_clusters,
            }),
            metrics.computed_at,
        )

    def check_for_alert(
        self,
        metrics: ClusterQualityMetrics,
    ) -> Optional[str]:
        """
        Check if alert should be raised.

        Alert on silhouette < 0.3 for 3 consecutive cycles.
        """
        self._recent_scores.append(metrics.silhouette_score)
        if len(self._recent_scores) > self.CONSECUTIVE_FAILURES_FOR_ALERT:
            self._recent_scores.pop(0)

        # Check for consecutive low scores
        if len(self._recent_scores) >= self.CONSECUTIVE_FAILURES_FOR_ALERT:
            if all(s < self.ALERT_THRESHOLD_LOW for s in self._recent_scores):
                return (
                    f"CLUSTER_QUALITY_DEGRADED: silhouette < {self.ALERT_THRESHOLD_LOW} "
                    f"for {self.CONSECUTIVE_FAILURES_FOR_ALERT} consecutive cycles"
                )

        return None
```

**Feedback Loop** (from Dossier §4.3.4.1):

1. **K1 Grounding Feedback**: When K1 uses episodic memory in response:
   - Emit signal: `CLUSTER_GROUNDED` with `epi_id`
   - Compute: `grounding_rate = grounded_clusters / total_clusters`

2. **User Correction Feedback**: When user corrects cluster boundary:
   - Emit signal: `CLUSTER_WRONG` with `correction_type: TOO_BROAD | TOO_NARROW | WRONG_EVENTS`
   - Compute: `correction_rate = corrected_clusters / total_clusters`

3. **Tuning Trigger**: If `composite_quality < 0.5` for 3 consecutive cycles:
   - Adjust eps/min_samples (Issues 4.2.5, 4.2.6)
   - Log adjustment to `st_consolidation_audit`

**Metrics** (from Dossier §4.3.4.1):

| Metric Name | Type | Description |
| ----------- | ---- | ----------- |
| `p03_cluster_composite_quality` | Gauge | Composite quality score [0, 1] |
| `p03_cluster_silhouette` | Gauge | Silhouette score [0, 1] |
| `p03_cluster_grounding_rate` | Gauge | Fraction of clusters used by K1 |
| `p03_cluster_correction_rate` | Gauge | User corrections / total clusters |
| `p03_cluster_singleton_rate` | Gauge | Singleton clusters / total clusters |

**Deliverables**:

- [ ] `ClusterQualityMetrics` dataclass with all quality signals
- [ ] `compute_composite()` implementing weighted formula
- [ ] `ClusterQualityTracker` class with `compute_metrics()`, `persist_metrics()`, `check_for_alert()`
- [ ] Query `st_feedback_signals` for CLUSTER_GROUNDED and CLUSTER_WRONG
- [ ] Persist to `st_consolidation_audit` with `audit_type='CLUSTER_QUALITY'`
- [ ] Alert on silhouette < 0.3 for 3 consecutive cycles

**Acceptance Criteria**:

- [ ] All 4 quality signals computed correctly
- [ ] Composite quality in [0, 1] range
- [ ] Metrics persisted to `st_consolidation_audit`
- [ ] Alert triggered after 3 consecutive low-quality cycles
- [ ] Prometheus metrics emitted

**Test File**: `tests/k0/pipelines/p03/test_r2_cluster_quality.py`

**Test Cases**:

1. `test_composite_quality_formula` — verify weights 0.40/0.30/0.20/0.10
2. `test_rates_from_counts` — correct rate computation
3. `test_persist_to_audit` — verify st_consolidation_audit insert
4. `test_alert_after_3_failures` — silhouette < 0.3 × 3 triggers alert
5. `test_no_alert_if_recovery` — alert not triggered if quality recovers
6. `test_grounding_rate_from_feedback` — query CLUSTER_GROUNDED signals
7. `test_correction_rate_from_feedback` — query CLUSTER_WRONG signals

**Blocked By**: 4.2.3, 4.2.4, 4.2.5, 4.2.6

**Blocks**: 4.2.8

---

#### Issue 4.2.8 — Unit + integration tests for R2 Episodic clustering

**Status**: NOT_STARTED

**Spec Reference**:

- [test_p03_feedback_consumer.py](../../tests/k0/pipelines/p03/test_p03_feedback_consumer.py) — Test pattern reference
- [conftest.py](../../tests/k0/pipelines/p03/conftest.py) — P03 test fixtures including `sample_event_state`
- [Dossier §4.3](../pipelines/P03_consolidation_dossier_v2.md#43-r2-neocortical-integration) — R2 specifications

**Goal**: Comprehensive test coverage proving correctness of episodic clustering and adaptive learning.

**Existing Test Infrastructure**:

| Component | Location | Pattern to Follow |
| --------- | -------- | ----------------- |
| `conftest.py` | `tests/k0/pipelines/p03/` | Fixtures for P03EventState, EpisodeCluster |
| `test_p03_envelope.py` | `tests/k0/pipelines/p03/` | `centroid_distance` usage |
| `test_p03_storage_migrations.py` | `tests/k0/pipelines/p03/` | st_consolidation_audit tests |

**Test File Structure** (55 tests across 7 files):

```text
tests/k0/pipelines/p03/
├── test_r2_composite_distance.py     # 6 tests (Issue 4.2.1)
├── test_r2_episode_splitter.py       # 8 tests (Issue 4.2.2)
├── test_r2_episodic_dbscan.py        # 8 tests (Issue 4.2.3)
├── test_r2_staged_output.py          # 9 tests (Issue 4.2.4)
├── test_r2_eps_adjuster.py           # 8 tests (Issue 4.2.5)
├── test_r2_min_samples_adjuster.py   # 7 tests (Issue 4.2.6)
├── test_r2_cluster_quality.py        # 7 tests (Issue 4.2.7)
└── test_r2_integration.py            # 10 tests (full R2 phase)
```

**Integration Tests** (`test_r2_integration.py`):

```python
import pytest
import numpy as np
from k0.pipelines.p03.algorithms.composite_distance import CompositeDistance, DBSCANParams
from k0.pipelines.p03.algorithms.episode_splitter import EpisodeSplitter
from k0.pipelines.p03.algorithms.episodic_dbscan import EpisodicDBSCAN
from k0.pipelines.p03.algorithms.centroid_calculator import CentroidCalculator
from k0.pipelines.p03.algorithms.eps_adjuster import EpsAdjuster
from k0.pipelines.p03.algorithms.min_samples_adjuster import MinSamplesAdjuster
from k0.pipelines.p03.algorithms.cluster_quality import ClusterQualityTracker


class TestR2Integration:
    """Integration tests for full R2 episodic clustering phase."""

    @pytest.fixture
    def sample_events(self):
        """Create batch of 20 events for clustering."""
        return create_test_events(
            count=20,
            clusters=3,  # 3 distinct semantic clusters
            noise=2,     # 2 singleton noise events
        )

    async def test_full_r2_phase_produces_clusters(self, sample_events):
        """Full R2 phase produces valid episode candidates."""
        output = await run_r2_phase(sample_events, space_id="test-space")

        assert output.cluster_count >= 1
        assert output.total_events_processed == 20
        assert len(output.episode_candidates) > 0

    async def test_semantically_similar_events_cluster_together(self, sample_events):
        """Events with high embedding similarity cluster together."""
        # Create 3 events with identical embeddings
        events = create_identical_embedding_events(count=3)
        output = await run_r2_phase(events, space_id="test-space")

        # Should form 1 cluster with all 3 events
        non_noise = [c for c in output.episode_candidates if not c.is_noise]
        assert len(non_noise) == 1
        assert non_noise[0].event_count == 3

    async def test_large_time_gap_triggers_split(self):
        """Time gap > 30 minutes triggers pre-split."""
        events = create_events_with_time_gap(gap_hours=1.0)  # 1 hour gap
        splitter = EpisodeSplitter()
        sequences = splitter.split_long_sequences(events)

        assert len(sequences) >= 2  # Split into at least 2 sequences

    async def test_location_change_triggers_split(self):
        """Geohash prefix change triggers pre-split."""
        events = create_events_with_location_change(
            geohash1="9q9p1234",  # San Francisco
            geohash2="dr5r1234",  # New York
        )
        splitter = EpisodeSplitter()
        sequences = splitter.split_long_sequences(events)

        assert len(sequences) >= 2

    async def test_silhouette_below_threshold_triggers_eps_adjustment(self):
        """Silhouette < 0.5 with large clusters triggers eps decrease."""
        adjuster = EpsAdjuster()
        new_eps = adjuster.adjust(
            current_eps=0.25,
            silhouette_score=0.3,  # Below target
            avg_cluster_size=15,   # Large clusters
            singleton_rate=0.10,
            total_clusters_formed=200,
        )

        assert new_eps < 0.25  # Eps decreased

    async def test_singleton_rate_above_threshold_triggers_min_samples_increase(self):
        """Singleton rate > 0.20 triggers min_samples increase."""
        adjuster = MinSamplesAdjuster()
        new_min_samples = adjuster.adjust(
            current_min_samples=2,
            singleton_rate=0.30,  # 30% singletons
        )

        assert new_min_samples == 3  # Increased

    async def test_staged_writes_contain_expected_structure(self):
        """Staged writes have all required fields for R7."""
        output = await run_r2_phase(create_test_events(10), space_id="test-space")

        for candidate in output.episode_candidates:
            assert candidate.cluster_id is not None
            assert candidate.event_ids is not None
            assert candidate.temporal_start > 0
            assert candidate.temporal_end >= candidate.temporal_start
            assert 0.0 <= candidate.cohesion_score <= 1.0
            if not candidate.is_noise:
                assert candidate.centroid_embedding is not None
                assert len(candidate.centroid_embedding) == 768

    async def test_no_db_writes_in_r2(self, db_conn):
        """Verify no st_epi rows created during R2 phase."""
        count_before = await db_conn.fetchval("SELECT COUNT(*) FROM st_epi")

        await run_r2_phase(create_test_events(10), space_id="test-space")

        count_after = await db_conn.fetchval("SELECT COUNT(*) FROM st_epi")
        assert count_after == count_before  # No new rows

    async def test_quality_metrics_persisted_to_audit(self, db_conn):
        """Quality metrics saved to st_consolidation_audit."""
        tracker = ClusterQualityTracker()
        metrics = await tracker.compute_metrics(
            space_id="test-space",
            r2_output=create_mock_r2_output(),
            db_conn=db_conn,
        )
        await tracker.persist_metrics(metrics, db_conn)

        row = await db_conn.fetchrow(
            "SELECT * FROM st_consolidation_audit WHERE audit_type = 'CLUSTER_QUALITY' ORDER BY created_at DESC LIMIT 1"
        )
        assert row is not None
        assert "silhouette_score" in row["details_json"]

    async def test_centroid_l2_normalized(self):
        """Centroid embeddings have unit norm."""
        calc = CentroidCalculator()
        events = create_test_events(5)
        centroid = calc.compute_centroid(events, strategy="hybrid", normalize=True)

        norm = np.linalg.norm(centroid)
        assert abs(norm - 1.0) < 0.001  # Unit norm
```

**Test Categories**:

1. **CompositeDistance** (6 tests): Distance computation, temporal cutoff, matrix symmetry
2. **EpisodeSplitter** (8 tests): Time gap, location change, activity change, hard limit
3. **EpisodicDBSCAN** (8 tests): Clustering, noise handling, event state updates
4. **StagedOutput** (9 tests): Centroid calculation, weighting strategies, metadata
5. **EpsAdjuster** (8 tests): Adjustment rules, bounds, momentum, persistence
6. **MinSamplesAdjuster** (7 tests): Adjustment rules, bounds, persistence
7. **ClusterQuality** (7 tests): Composite formula, alert thresholds, audit persistence
8. **Integration** (10 tests): Full R2 phase, end-to-end behavior

**Deliverables**:

- [ ] `test_r2_composite_distance.py` — 6 tests for distance metric
- [ ] `test_r2_episode_splitter.py` — 8 tests for pre-clustering split
- [ ] `test_r2_episodic_dbscan.py` — 8 tests for DBSCAN clustering
- [ ] `test_r2_staged_output.py` — 9 tests for centroid and staging
- [ ] `test_r2_eps_adjuster.py` — 8 tests for adaptive eps
- [ ] `test_r2_min_samples_adjuster.py` — 7 tests for adaptive min_samples
- [ ] `test_r2_cluster_quality.py` — 7 tests for quality metrics
- [ ] `test_r2_integration.py` — 10 tests for full R2 phase
- [ ] All tests use real components, no mocking except for DB fixtures

**Acceptance Criteria**:

- [ ] 55+ tests total passing
- [ ] Coverage > 90% for R2 code paths
- [ ] Integration tests exercise full phase execution
- [ ] Silhouette score > 0.5 target validated
- [ ] Singleton rate < 0.20 target validated
- [ ] All assertions grounded in dossier specifications

**Blocked By**: 4.2.1, 4.2.2, 4.2.3, 4.2.4, 4.2.5, 4.2.6, 4.2.7

**Blocks**: Epic 4.3 (R3)

---

### Epic 4.3 — R3 Duplicate detection + retention/decay

> **Scope**: Implement R3 Synaptic Homeostasis phase — dedup, decay, novelty scoring.
> **Modules**: M19 DuplicateDetector, M20 RetentionEnforcer
> **Dossier**: Section 4.4, Appendix C.4

---

#### Issue 4.3.1 — Implement SimHash fingerprinting with per-content-type thresholds

**Status**: NOT_STARTED

**Spec Reference**:

- [Dossier Appendix C.4.1](../pipelines/P03_consolidation_dossier_v2.md#c41-simhash-64-bit-locality-sensitive-hashing) (lines 21912-22010) — SimHash algorithm
- [Dossier Appendix C.4.1.1](../pipelines/P03_consolidation_dossier_v2.md#c411-content-type-thresholds) (lines 22010-22116) — Per-content-type thresholds
- [P03EventState.simhash_hex](../../k0/pipelines/p03/event_state.py#L135) — Existing simhash_hex field
- [test_p03_envelope.py](../../tests/k0/pipelines/p03/test_p03_envelope.py#L370) — `hamming_distance` test pattern

**Goal**: Fast syntactic duplicate detection using 64-bit locality-sensitive hashing (Charikar 2002).

**Problem Statement** (from Dossier C.4.1):

> Need to detect if "Wake up" logged at 7:01 AM is the same event as "Wake up" logged at 7:02 AM. Exact string match misses near-duplicates; full embedding comparison is too expensive for filtering.

**Existing Infrastructure**:

| Component | Location | How to Use |
| --------- | -------- | ---------- |
| `P03EventState.simhash_hex` | [event_state.py#L135](../../k0/pipelines/p03/event_state.py#L135) | 16-char hex string from P02 |
| `P03EventState.hamming_distance` | [event_state.py#L173](../../k0/pipelines/p03/event_state.py#L173) | Distance field (0-64) |
| `st_hipp_events.simhash_hex` | Migration 0022 | Stored from P02 enrichment |
| `st_learned_weights` | Migration 0040 | Store learned thresholds |

**Implementation**:

```python
# File: k0/modules/consolidation/algorithms/simhasher.py

from typing import List, Optional, Tuple
import hashlib

class SimHasher:
    """
    64-bit SimHash for near-duplicate detection.

    Scientific Basis: Charikar (2002) - Similarity estimation using random projections.
    Spec: Dossier Appendix C.4.1
    """

    HASH_BITS = 64

    # Per-content-type Hamming thresholds (from Dossier C.4.1.1)
    CONTENT_TYPE_THRESHOLDS = {
        'TRANSACTION': 1,      # Financial exactness required
        'CALENDAR_EVENT': 2,   # Structured, small variations matter
        'CONTACT_UPDATE': 2,   # Names/phones must match closely
        'CHAT_MESSAGE': 3,     # Default, mixed content
        'PHOTO_CAPTION': 4,    # Free-form, allow paraphrasing
        'JOURNAL_ENTRY': 4,    # Personal text, subjective
        'VOICE_MEMO': 5,       # ASR transcription has inherent noise
    }
    DEFAULT_THRESHOLD = 3

    def tokenize(self, text: str) -> List[str]:
        """
        Extract 3-gram shingles from text.
        """
        text = text.lower().strip()
        words = text.split()

        # 3-gram shingles
        shingles = []
        for i in range(len(words) - 2):
            shingles.append(' '.join(words[i:i+3]))

        return shingles

    def compute_simhash(self, text: str) -> int:
        """
        Compute 64-bit SimHash.

        Algorithm (from Dossier C.4.1):
        1. Tokenize text into 3-gram shingles
        2. Hash each shingle to 64-bit value
        3. For each bit position, sum +1 (if bit=1) or -1 (if bit=0)
        4. Final hash: bit=1 if sum > 0, else bit=0

        Returns:
            64-bit SimHash as integer
        """
        shingles = self.tokenize(text)
        if not shingles:
            return 0

        # Accumulator for each bit position
        bit_sums = [0] * self.HASH_BITS

        for shingle in shingles:
            # Hash shingle to 64-bit using MD5 (deterministic)
            h = int(hashlib.md5(shingle.encode()).hexdigest()[:16], 16)

            for i in range(self.HASH_BITS):
                if h & (1 << i):
                    bit_sums[i] += 1
                else:
                    bit_sums[i] -= 1

        # Build final hash
        simhash = 0
        for i in range(self.HASH_BITS):
            if bit_sums[i] > 0:
                simhash |= (1 << i)

        return simhash

    def simhash_to_hex(self, simhash: int) -> str:
        """Convert simhash integer to 16-char hex string."""
        return format(simhash, '016X')

    def hex_to_simhash(self, hex_str: str) -> int:
        """Convert 16-char hex string to simhash integer."""
        return int(hex_str, 16)

    def hamming_distance(self, hash1: int, hash2: int) -> int:
        """Count differing bits between two hashes (0-64)."""
        xor = hash1 ^ hash2
        return bin(xor).count('1')

    def get_threshold(self, content_type: str) -> int:
        """
        Get Hamming threshold for content type.

        From Dossier C.4.1.1:
        - TRANSACTION=1 (strictest)
        - VOICE_MEMO=5 (loosest)
        """
        return self.CONTENT_TYPE_THRESHOLDS.get(
            content_type, self.DEFAULT_THRESHOLD
        )

    def is_near_duplicate(
        self,
        hash1: int,
        hash2: int,
        content_type: str = 'CHAT_MESSAGE'
    ) -> Tuple[bool, int]:
        """
        Check if two hashes represent near-duplicates.

        Returns:
            (is_duplicate, hamming_distance)
        """
        threshold = self.get_threshold(content_type)
        distance = self.hamming_distance(hash1, hash2)
        return (distance <= threshold, distance)
```

**Hamming Distance Interpretation** (from Dossier C.4.1):

| Distance | Interpretation | Action |
| -------- | -------------- | ------ |
| 0 | Exact duplicate | Merge, keep higher importance |
| 1-3 | Near-duplicate | Merge, combine metadata |
| 4-10 | Similar content | Consider linking, no merge |
| >10 | Different content | Process independently |

**Per-Content-Type Thresholds** (from Dossier C.4.1.1):

| Content Type | Threshold | Rationale |
| ------------ | --------- | --------- |
| `TRANSACTION` | 1 | "$50.23" vs "$50.32" are different |
| `CALENDAR_EVENT` | 2 | "Meeting at 2pm" vs "Meeting at 3pm" |
| `CONTACT_UPDATE` | 2 | Names/phones must match closely |
| `CHAT_MESSAGE` | 3 | General conversations (default) |
| `PHOTO_CAPTION` | 4 | "Sunset at beach" vs "Beach sunset" |
| `JOURNAL_ENTRY` | 4 | Personal text, subjective |
| `VOICE_MEMO` | 5 | ASR errors tolerated |

**Adaptive Learning** (from Dossier C.4.1.1):

| Feedback Signal | Source | Adjustment |
| --------------- | ------ | ---------- |
| `UNMERGE_DEDUP` | User | Increase threshold +1 (stricter) |
| `MANUAL_MERGE` | User | Decrease threshold -1 (looser) |

**Configuration**:

| Config Key | Default | Purpose |
| ---------- | ------- | ------- |
| `P03_SIMHASH_DEFAULT_THRESHOLD` | 3 | Default Hamming threshold |
| `P03_SIMHASH_MIN_THRESHOLD` | 1 | Strictest (TRANSACTION) |
| `P03_SIMHASH_MAX_THRESHOLD` | 5 | Loosest (VOICE_MEMO) |
| `P03_SIMHASH_LEARNING_ENABLED` | TRUE | Enable adaptive learning |

**Metrics** (from Dossier C.4.1.1):

| Metric Name | Type | Description |
| ----------- | ---- | ----------- |
| `p03_simhash_threshold_current` | Gauge | Current threshold by content type |
| `p03_simhash_false_positives` | Counter | User unmerge actions |
| `p03_simhash_false_negatives` | Counter | User manual merge actions |
| `p03_simhash_precision` | Gauge | 1 - (FP / total merges) |

**Deliverables**:

- [ ] `SimHasher` class in `k0/modules/consolidation/algorithms/simhasher.py`
- [ ] `compute_simhash(text)` returning 64-bit integer
- [ ] `simhash_to_hex(simhash)` returning 16-char hex string
- [ ] `hamming_distance(hash1, hash2)` returning 0-64
- [ ] `get_threshold(content_type)` with per-content-type lookup
- [ ] `is_near_duplicate(hash1, hash2, content_type)` returning (bool, distance)
- [ ] Store threshold adjustments in `st_learned_weights`

**Acceptance Criteria**:

- [ ] Same text produces same simhash (deterministic)
- [ ] Similar text produces hamming distance ≤ 3
- [ ] Different text produces hamming distance > 10
- [ ] Per-content-type thresholds applied correctly
- [ ] Hex encoding matches existing `simhash_hex` format

**Test File**: `tests/k0/pipelines/p03/test_r3_simhasher.py`

**Test Cases**:

1. `test_identical_text_zero_distance` — same text → hamming = 0
2. `test_similar_text_low_distance` — minor edits → hamming ≤ 3
3. `test_different_text_high_distance` — unrelated → hamming > 10
4. `test_content_type_thresholds` — verify per-type thresholds
5. `test_hex_encoding_roundtrip` — simhash ↔ hex conversion
6. `test_empty_text_returns_zero` — edge case

**Blocked By**: None

**Blocks**: 4.3.2, 4.3.7

---

#### Issue 4.3.2 — Implement two-stage deduplication pipeline

**Status**: NOT_STARTED

**Spec Reference**:

- [Dossier Appendix C.4.1.2](../pipelines/P03_consolidation_dossier_v2.md#c412-two-stage-deduplication-pipeline) (lines 22116-22296) — Two-stage dedup algorithm
- [P03EventState.is_duplicate](../../k0/pipelines/p03/event_state.py#L172) — Existing dedup fields
- [P03EventState.duplicate_of_id](../../k0/pipelines/p03/event_state.py#L173) — Canonical event reference

**Goal**: Combine SimHash syntactic filtering with embedding semantic verification to catch both syntactic and semantic duplicates.

**Problem Statement** (from Dossier C.4.1.2):

> SimHash alone has limitations:
>
> 1. **False Positives**: "I ate pizza" vs "I hate pizza" (Hamming = 2, but opposite meaning)
> 2. **False Negatives**: "Had pizza for dinner" vs "Ate pizza tonight" (Hamming > 3, but semantically identical)

**Existing Infrastructure**:

| Component | Location | How to Use |
| --------- | -------- | ---------- |
| `P03EventState.is_duplicate` | [event_state.py#L172](../../k0/pipelines/p03/event_state.py#L172) | Boolean flag |
| `P03EventState.duplicate_of_id` | [event_state.py#L173](../../k0/pipelines/p03/event_state.py#L173) | Canonical event ID |
| `P03EventState.embedding_768` | [event_state.py#L145](../../k0/pipelines/p03/event_state.py#L145) | For cosine similarity |
| `SimHasher` | Issue 4.3.1 | Stage 1 filter |

**Implementation**:

```python
# File: k0/modules/consolidation/algorithms/two_stage_dedup.py

from dataclasses import dataclass
from typing import List, Tuple, Optional, Set
from enum import Enum
import numpy as np


class DuplicateDecision(Enum):
    """Decision types from two-stage deduplication."""
    DUPLICATE = "DUPLICATE"              # ≥0.85 similarity
    LIKELY_DUPLICATE = "LIKELY_DUPLICATE" # 0.70-0.85 similarity
    NOT_DUPLICATE = "NOT_DUPLICATE"       # <0.70 similarity
    SEMANTIC_DUPLICATE = "SEMANTIC_DUPLICATE"  # Caught by embedding fallback
    DISTINCT = "DISTINCT"                 # Different content


@dataclass
class DuplicateMatch:
    """Result from duplicate detection."""
    event_id: str
    hamming_distance: Optional[int]  # None if embedding fallback
    embedding_similarity: float
    decision_type: DuplicateDecision
    check_method: str  # 'TWO_STAGE' or 'EMBEDDING_FALLBACK'


class Stage1SimHashFilter:
    """
    Fast O(n) filter using SimHash.

    Spec: Dossier C.4.1.2 Stage 1
    """

    def __init__(self, simhasher: "SimHasher"):
        self.simhasher = simhasher

    def find_candidates(
        self,
        new_event: "P03EventState",
        recent_events: List["P03EventState"],
        threshold: int = 3,
    ) -> List[Tuple[str, int]]:
        """
        Find events with Hamming distance ≤ threshold.

        Returns: List of (event_id, hamming_distance)
        """
        if not new_event.simhash_hex:
            return []

        new_hash = self.simhasher.hex_to_simhash(new_event.simhash_hex)
        candidates = []

        for event in recent_events:
            if not event.simhash_hex or event.event_id == new_event.event_id:
                continue

            event_hash = self.simhasher.hex_to_simhash(event.simhash_hex)
            dist = self.simhasher.hamming_distance(new_hash, event_hash)

            if dist <= threshold:
                candidates.append((event.event_id, dist))

        return candidates


class Stage2EmbeddingVerifier:
    """
    Semantic verification using cosine similarity.

    Spec: Dossier C.4.1.2 Stage 2
    """

    # Thresholds from Dossier C.4.1.2
    DUPLICATE_THRESHOLD = 0.85
    LIKELY_DUPLICATE_THRESHOLD = 0.70
    SEMANTIC_FALLBACK_THRESHOLD = 0.90

    def verify_duplicate(
        self,
        event1: "P03EventState",
        event2: "P03EventState",
    ) -> Tuple[bool, float, DuplicateDecision]:
        """
        Verify if candidate pair is truly duplicate.

        Returns: (is_duplicate, similarity, decision_type)
        """
        if event1.embedding_768 is None or event2.embedding_768 is None:
            return (False, 0.0, DuplicateDecision.NOT_DUPLICATE)

        # Compute cosine similarity
        vec1 = np.array(event1.embedding_768)
        vec2 = np.array(event2.embedding_768)
        similarity = float(np.dot(vec1, vec2) / (
            np.linalg.norm(vec1) * np.linalg.norm(vec2) + 1e-8
        ))

        # Decision logic (from Dossier C.4.1.2)
        if similarity >= self.DUPLICATE_THRESHOLD:
            return (True, similarity, DuplicateDecision.DUPLICATE)
        elif similarity >= self.LIKELY_DUPLICATE_THRESHOLD:
            return (True, similarity, DuplicateDecision.LIKELY_DUPLICATE)
        else:
            return (False, similarity, DuplicateDecision.NOT_DUPLICATE)


class TwoStageDeduplicator:
    """
    Complete two-stage deduplication pipeline.

    Spec: Dossier Appendix C.4.1.2
    """

    def __init__(self, simhasher: "SimHasher"):
        self.stage1 = Stage1SimHashFilter(simhasher)
        self.stage2 = Stage2EmbeddingVerifier()
        self.simhasher = simhasher

    async def find_duplicates(
        self,
        new_event: "P03EventState",
        window_events: List["P03EventState"],
    ) -> List[DuplicateMatch]:
        """
        Find all duplicates of new_event using two-stage pipeline.

        Algorithm (from Dossier C.4.1.2):
        1. Stage 1: SimHash filter (fast O(n))
        2. Stage 2: Embedding verification (accurate)
        3. Fallback: High embedding similarity even if SimHash missed
        """
        matches = []

        # Get content-type threshold
        threshold = self.simhasher.get_threshold(
            new_event.content_type or 'CHAT_MESSAGE'
        )

        # Stage 1: SimHash filter
        candidates = self.stage1.find_candidates(
            new_event, window_events, threshold
        )

        # Build lookup for Stage 2
        event_map = {e.event_id: e for e in window_events}

        # Stage 2: Embedding verification
        for event_id, hamming_dist in candidates:
            event = event_map.get(event_id)
            if not event:
                continue

            is_dup, similarity, decision = self.stage2.verify_duplicate(
                new_event, event
            )

            if is_dup:
                matches.append(DuplicateMatch(
                    event_id=event_id,
                    hamming_distance=hamming_dist,
                    embedding_similarity=similarity,
                    decision_type=decision,
                    check_method='TWO_STAGE',
                ))

        # Fallback: Check high embedding similarity even if SimHash missed
        candidate_ids = {c[0] for c in candidates}
        for event in window_events:
            if event.event_id in candidate_ids:
                continue
            if event.event_id == new_event.event_id:
                continue
            if event.embedding_768 is None or new_event.embedding_768 is None:
                continue

            # Quick cosine check
            vec1 = np.array(new_event.embedding_768)
            vec2 = np.array(event.embedding_768)
            similarity = float(np.dot(vec1, vec2) / (
                np.linalg.norm(vec1) * np.linalg.norm(vec2) + 1e-8
            ))

            if similarity >= 0.90:  # SEMANTIC_FALLBACK_THRESHOLD
                matches.append(DuplicateMatch(
                    event_id=event.event_id,
                    hamming_distance=None,  # Not checked by SimHash
                    embedding_similarity=similarity,
                    decision_type=DuplicateDecision.SEMANTIC_DUPLICATE,
                    check_method='EMBEDDING_FALLBACK',
                ))

        return matches
```

**Combined Decision Matrix** (from Dossier C.4.1.2):

| SimHash Result | Embedding Similarity | Final Decision | Action |
| -------------- | -------------------- | -------------- | ------ |
| ≤ threshold | ≥ 0.85 | `DUPLICATE` | Merge, keep higher importance |
| ≤ threshold | 0.70-0.85 | `LIKELY_DUPLICATE` | Flag for review, link as related |
| ≤ threshold | < 0.70 | `NOT_DUPLICATE` | False positive, process independently |
| > threshold | ≥ 0.90 | `SEMANTIC_DUPLICATE` | Merge (caught by fallback) |
| > threshold | < 0.90 | `DISTINCT` | Process independently |

**Performance** (from Dossier C.4.1.2):

| Method | Complexity | Precision | Recall | Best For |
| ------ | ---------- | --------- | ------ | -------- |
| SimHash only | O(n) | 0.85 | 0.90 | Fast, syntactic |
| Embedding only | O(n²) | 0.95 | 0.98 | Accurate, slow |
| Two-stage | O(n + k) | 0.93 | 0.95 | Balanced (k ≈ 0.01n) |

**Metrics** (from Dossier C.4.1.2):

| Metric Name | Type | Description |
| ----------- | ---- | ----------- |
| `p03_dedup_stage1_candidates` | Histogram | Candidates from SimHash per event |
| `p03_dedup_stage2_confirmed` | Counter | Duplicates confirmed by embedding |
| `p03_dedup_stage2_rejected` | Counter | SimHash false positives caught |
| `p03_dedup_fallback_caught` | Counter | Semantic duplicates missed by SimHash |

**Deliverables**:

- [ ] `DuplicateDecision` enum with 5 decision types
- [ ] `DuplicateMatch` dataclass for results
- [ ] `Stage1SimHashFilter.find_candidates()` returning (event_id, hamming_distance) tuples
- [ ] `Stage2EmbeddingVerifier.verify_duplicate()` with thresholds 0.85/0.70
- [ ] `TwoStageDeduplicator.find_duplicates()` combining both stages
- [ ] Embedding fallback for semantic duplicates missed by SimHash

**Acceptance Criteria**:

- [ ] Stage 1 eliminates 99%+ non-duplicates (fast filter)
- [ ] Stage 2 catches "I ate pizza" vs "I hate pizza" as NOT_DUPLICATE
- [ ] Fallback catches "Had pizza" vs "Ate pizza" as SEMANTIC_DUPLICATE
- [ ] All matches include check_method for auditing

**Test File**: `tests/k0/pipelines/p03/test_r3_two_stage_dedup.py`

**Test Cases**:

1. `test_stage1_filters_non_candidates` — high hamming distance excluded
2. `test_stage2_confirms_true_duplicate` — similarity ≥ 0.85
3. `test_stage2_rejects_false_positive` — SimHash match, embedding < 0.70
4. `test_semantic_fallback_catches_paraphrase` — SimHash miss, embedding ≥ 0.90
5. `test_likely_duplicate_flagged` — similarity 0.70-0.85
6. `test_duplicate_match_contains_method` — check_method populated

**Blocked By**: 4.3.1

**Blocks**: 4.3.7, 4.3.8

---

#### Issue 4.3.3 — Implement UnifiedDecayEngine with per-layer lambda

**Status**: NOT_STARTED

**Spec Reference**:

- [Dossier §4.4.1.1](../pipelines/P03_consolidation_dossier_v2.md#4411-unified-decay-architecture) (lines 3625-3700) — Unified decay architecture
- [Dossier Appendix C.4.2](../pipelines/P03_consolidation_dossier_v2.md#c42-exponential-decay-memory-fading) (lines 22475-22600) — ExponentialDecayEngine
- [0027_st_epi.py](../../k0/db/alembic/versions/0027_st_epi.py#L96) — `decay_factor` column
- [0028_st_sem.py](../../k0/db/alembic/versions/0028_st_sem.py#L83) — `decay_factor`, `archival_status`

**Goal**: Single decay engine for all 8 memory tables with consistent decay semantics (Ebbinghaus 1885, Tononi & Cirelli 2006).

**Existing Infrastructure**:

| Component | Location | How to Use |
| --------- | -------- | ---------- |
| `st_epi.decay_factor` | Migration 0027 | Float [0.0, 1.0] |
| `st_epi.archival_status` | Migration 0027 | ACTIVE/ARCHIVED/TOMBSTONE |
| `st_sem.decay_factor` | Migration 0028 | Same pattern |
| `st_kg_dom.decay_factor` | Migration 0032 | Same pattern |
| `st_kg_edges.decay_factor` | Migration 0033 | Same pattern |
| `P03EventState.decay_score` | [event_state.py#L176](../../k0/pipelines/p03/event_state.py#L176) | Per-event decay |
| `P03EventState.prune_decision` | [event_state.py#L180](../../k0/pipelines/p03/event_state.py#L180) | KEEP/ARCHIVE/TOMBSTONE |

**Per-Layer λ Values** (from Dossier §4.4.1.1):

| Table | Brain Analog | Default λ | Half-Life | Archive @ | Tombstone @ |
| ----- | ------------ | --------- | --------- | --------- | ----------- |
| `st_epi` | Episodic Memory | 0.005 | 139 days | 180 days | 365 days |
| `st_sem` | Semantic Memory | 0.003 | 231 days | 300 days | 600 days |
| `st_procedural` | Procedural Memory | 0.010 | 69 days | 90 days | 180 days |
| `st_social` | Social Memory | 0.002 | 347 days | 450 days | 900 days |
| `st_kg_dom` | Concepts | 0.001 | 693 days | 900 days | 1800 days |
| `st_kg_edges` | Associations | 0.008 | 87 days | 120 days | 240 days |
| `st_prospective` | Plans/Goals | 0.020 | 35 days | 45 days | 90 days |
| `st_hipp_events` | Short-term Buffer | 0.100 | 7 days | 10 days | 20 days |

**Implementation**:

```python
# File: k0/modules/consolidation/algorithms/decay_engine.py

import math
from dataclasses import dataclass
from typing import Optional, Tuple
from enum import Enum


class DecayClassification(Enum):
    """Decay-based lifecycle state."""
    ACTIVE = "ACTIVE"                     # decay_factor >= 0.10
    ARCHIVE_CANDIDATE = "ARCHIVE_CANDIDATE"  # 0.01 <= decay_factor < 0.10
    PRUNE_CANDIDATE = "PRUNE_CANDIDATE"    # decay_factor < 0.01


@dataclass
class DecayConfig:
    """Configuration for decay computation."""
    base_lambda: float = 0.01
    importance_modifier: float = 0.5  # High importance decays slower
    confidence_modifier: float = 0.3  # High confidence decays slower
    archive_threshold: float = 0.10
    tombstone_threshold: float = 0.01


# Per-layer default λ values (from Dossier §4.4.1.1)
LAYER_LAMBDAS = {
    'st_epi': 0.005,
    'st_sem': 0.003,
    'st_procedural': 0.010,
    'st_social': 0.002,
    'st_kg_dom': 0.001,
    'st_kg_edges': 0.008,
    'st_prospective': 0.020,
    'st_hipp_events': 0.100,
}


class UnifiedDecayEngine:
    """
    Unified decay engine for all 8 memory tables.

    Scientific Basis:
    - Ebbinghaus (1885): Forgetting curve
    - Tononi & Cirelli (2006): Synaptic homeostasis hypothesis

    Formula: decay_factor = exp(-λ_effective × days_since_last_observed)

    Spec: Dossier §4.4.1.1, Appendix C.4.2
    """

    def __init__(self, config: Optional[DecayConfig] = None):
        self.config = config or DecayConfig()

    def get_base_lambda(self, table_name: str) -> float:
        """Get default λ for table (from Dossier §4.4.1.1)."""
        return LAYER_LAMBDAS.get(table_name, self.config.base_lambda)

    def compute_effective_lambda(
        self,
        table_name: str,
        importance_score: float = 0.0,
        confidence_score: float = 0.0,
        observation_count: int = 1,
        space_modifier: float = 1.0,
        entity_type_modifier: float = 1.0,
    ) -> float:
        """
        Compute decay rate adjusted for importance and reinforcement.

        Formula (from Dossier §4.4.1.1):
        λ_effective = λ_base × space_modifier × entity_type_modifier × importance_modifier

        Where:
        - importance_modifier = 1.0 - (importance_score × 0.5)
        - confidence_modifier = 1.0 - (confidence_score × 0.3)
        - reinforcement_modifier = 1.0 / (1.0 + 0.1 × observation_count)
        """
        base = self.get_base_lambda(table_name)

        # Importance reduces decay (important memories persist)
        importance_factor = 1.0 - (
            importance_score * self.config.importance_modifier
        )

        # Confidence reduces decay (trusted memories persist)
        confidence_factor = 1.0 - (
            confidence_score * self.config.confidence_modifier
        )

        # Observation count reduces decay (reinforced memories persist)
        reinforcement_factor = 1.0 / (1.0 + 0.1 * observation_count)

        return (
            base *
            space_modifier *
            entity_type_modifier *
            importance_factor *
            confidence_factor *
            reinforcement_factor
        )

    def compute_decay_factor(
        self,
        table_name: str,
        last_observed_at: int,
        current_time: int,
        importance_score: float = 0.0,
        confidence_score: float = 0.0,
        observation_count: int = 1,
        space_modifier: float = 1.0,
        entity_type_modifier: float = 1.0,
    ) -> float:
        """
        Compute current decay factor.

        Returns value in [0.0, 1.0]:
        - 1.0 = freshly observed, no decay
        - 0.0 = completely forgotten
        """
        days_since_observed = (
            (current_time - last_observed_at) / (24 * 3600 * 1000)
        )

        if days_since_observed <= 0:
            return 1.0

        effective_lambda = self.compute_effective_lambda(
            table_name=table_name,
            importance_score=importance_score,
            confidence_score=confidence_score,
            observation_count=observation_count,
            space_modifier=space_modifier,
            entity_type_modifier=entity_type_modifier,
        )

        decay_factor = math.exp(-effective_lambda * days_since_observed)

        return max(0.0, min(1.0, decay_factor))

    def classify_record(
        self,
        decay_factor: float,
    ) -> DecayClassification:
        """
        Classify record based on decay factor.

        From Dossier §4.4.1.1:
        - ACTIVE: decay_factor >= 0.10
        - ARCHIVE_CANDIDATE: 0.01 <= decay_factor < 0.10
        - PRUNE_CANDIDATE: decay_factor < 0.01
        """
        if decay_factor >= self.config.archive_threshold:
            return DecayClassification.ACTIVE
        elif decay_factor >= self.config.tombstone_threshold:
            return DecayClassification.ARCHIVE_CANDIDATE
        else:
            return DecayClassification.PRUNE_CANDIDATE

    def compute_and_classify(
        self,
        table_name: str,
        last_observed_at: int,
        current_time: int,
        **kwargs,
    ) -> Tuple[float, DecayClassification]:
        """Convenience method: compute decay factor and classify."""
        decay_factor = self.compute_decay_factor(
            table_name=table_name,
            last_observed_at=last_observed_at,
            current_time=current_time,
            **kwargs,
        )
        classification = self.classify_record(decay_factor)
        return (decay_factor, classification)
```

**Decay Timeline Example** (from Dossier C.4.2):

| Days Since Observed | Decay Factor (default) | Status |
| ------------------- | ---------------------- | ------ |
| 0 | 1.00 | ACTIVE |
| 30 | 0.74 | ACTIVE |
| 60 | 0.55 | ACTIVE |
| 90 | 0.41 | ACTIVE |
| 180 | 0.17 | ARCHIVE_CANDIDATE |
| 365 | 0.03 | PRUNE_CANDIDATE |

**Configuration** (from Dossier §4.4.1.1):

| Config Key | Default | Purpose |
| ---------- | ------- | ------- |
| `P03_DECAY_ARCHIVE_THRESHOLD` | 0.10 | ACTIVE → ARCHIVED |
| `P03_DECAY_TOMBSTONE_THRESHOLD` | 0.01 | ARCHIVED → TOMBSTONE |
| `P03_DECAY_IMPORTANCE_MODIFIER` | 0.5 | Importance dampening |
| `P03_DECAY_CONFIDENCE_MODIFIER` | 0.3 | Confidence dampening |

**Metrics** (from Dossier §4.4.1.1):

| Metric Name | Type | Description |
| ----------- | ---- | ----------- |
| `p03_decay_total_active` | Gauge | Total ACTIVE records per layer |
| `p03_decay_total_archived` | Gauge | Total ARCHIVED records |
| `p03_decay_total_tombstoned` | Gauge | Total TOMBSTONE records |
| `p03_decay_factor_histogram` | Histogram | Distribution of decay factors |

**Deliverables**:

- [ ] `DecayClassification` enum (ACTIVE, ARCHIVE_CANDIDATE, PRUNE_CANDIDATE)
- [ ] `DecayConfig` dataclass with thresholds
- [ ] `LAYER_LAMBDAS` dict with 8 per-layer defaults
- [ ] `UnifiedDecayEngine` class in `k0/modules/consolidation/algorithms/decay_engine.py`
- [ ] `get_base_lambda(table)` returning per-layer λ
- [ ] `compute_effective_lambda()` with modifiers
- [ ] `compute_decay_factor()` returning [0.0, 1.0]
- [ ] `classify_record()` returning DecayClassification

**Acceptance Criteria**:

- [ ] All 8 layers have correct default λ values
- [ ] High importance_score → slower decay
- [ ] High observation_count → slower decay
- [ ] Decay factor correctly clamped to [0.0, 1.0]
- [ ] Classification thresholds match dossier (0.10, 0.01)

**Test File**: `tests/k0/pipelines/p03/test_r3_decay_engine.py`

**Test Cases**:

1. `test_per_layer_lambda_values` — verify all 8 defaults
2. `test_fresh_record_decay_factor_1` — just observed → 1.0
3. `test_decay_timeline_matches_dossier` — 30/60/90/180/365 day values
4. `test_importance_slows_decay` — high importance → higher decay_factor
5. `test_observation_count_slows_decay` — more observations → higher decay_factor
6. `test_classify_active` — decay_factor ≥ 0.10
7. `test_classify_archive_candidate` — 0.01 ≤ decay_factor < 0.10
8. `test_classify_prune_candidate` — decay_factor < 0.01

**Blocked By**: None

**Blocks**: 4.3.4, 4.3.5, 4.3.6

---

#### Issue 4.3.4 — Implement M20 RetentionEnforcer: archive/tombstone decisioning

**Status**: NOT_STARTED

**Spec Reference**:

- [Dossier Appendix C.4.2.1](../pipelines/P03_consolidation_dossier_v2.md#c421-memory-resurrection) (lines 22600-22695) — Memory resurrection
- [Dossier §4.4.1.1](../pipelines/P03_consolidation_dossier_v2.md#4411-unified-decay-architecture) (lines 3668-3682) — Resurrection support
- [P03EventState.prune_decision](../../k0/pipelines/p03/event_state.py#L180) — KEEP/ARCHIVE/TOMBSTONE enum
- [st_consolidation_audit](../../k0/db/alembic/versions/0036_st_consolidation_audit.py) — Audit trail

**Goal**: Evaluate retention decisions based on decay factor and support resurrection of archived entities.

**Problem Statement** (from Dossier C.4.2.1):

> "Oh yes, I remember this now!" — Archived memories brought back feel fresh but familiar. Entities archived due to disuse may be queried later (e.g., seasonal relationships, infrequent contacts). Need mechanism to restore without losing history.

**Existing Infrastructure**:

| Component | Location | How to Use |
| --------- | -------- | ---------- |
| `P03EventState.prune_decision` | [event_state.py#L180](../../k0/pipelines/p03/event_state.py#L180) | PruneDecision enum |
| `PruneDecision` enum | [event_state.py#L44](../../k0/pipelines/p03/event_state.py#L44) | KEEP/ARCHIVE/TOMBSTONE |
| `st_*.archival_status` | All memory migrations | ACTIVE/ARCHIVED/TOMBSTONE |
| `st_consolidation_audit` | Migration 0036 | Audit resurrection events |

**Implementation**:

```python
# File: k0/modules/consolidation/algorithms/retention_enforcer.py

from dataclasses import dataclass
from typing import Optional, Tuple
from enum import Enum
import json
import logging

logger = logging.getLogger(__name__)


class RetentionDecision(Enum):
    """Retention decision for an entity."""
    KEEP = "KEEP"          # Retain in active store
    ARCHIVE = "ARCHIVE"    # Move to cold storage (recoverable)
    TOMBSTONE = "TOMBSTONE" # Mark for deletion (soft delete)


class ResurrectionTrigger(Enum):
    """What triggered the resurrection."""
    QUERY = "QUERY"              # P04 retrieval
    CO_OCCURRENCE = "CO_OCCURRENCE"  # Reappears in new event
    USER_MENTION = "USER_MENTION"   # K1 explicit reference


@dataclass
class ResurrectionResult:
    """Result of resurrection operation."""
    entity_id: str
    old_decay: float
    new_decay: float
    old_status: str
    new_status: str
    resurrection_count: int
    trigger: ResurrectionTrigger


class RetentionEnforcer:
    """
    Evaluate retention decisions and support resurrection.

    Module: M20 RetentionEnforcer
    Spec: Dossier §4.4.1.1, Appendix C.4.2.1
    """

    # Thresholds from Dossier §4.4.1.1
    ARCHIVE_THRESHOLD = 0.10
    TOMBSTONE_THRESHOLD = 0.01

    # Resurrection parameters from Dossier C.4.2.1
    RESURRECTION_FLOOR = 0.70
    RESURRECTION_PARTIAL_WEIGHT = 0.50
    RESURRECTION_ALERT_THRESHOLD = 3

    def __init__(self, decay_engine: "UnifiedDecayEngine"):
        self.decay_engine = decay_engine

    def evaluate(
        self,
        decay_factor: float,
        decay_immune: bool = False,
    ) -> RetentionDecision:
        """
        Evaluate retention decision based on decay factor.

        From Dossier §4.4.1.1:
        - KEEP: decay_factor >= 0.10 or decay_immune
        - ARCHIVE: 0.01 <= decay_factor < 0.10
        - TOMBSTONE: decay_factor < 0.01
        """
        if decay_immune:
            return RetentionDecision.KEEP

        if decay_factor >= self.ARCHIVE_THRESHOLD:
            return RetentionDecision.KEEP
        elif decay_factor >= self.TOMBSTONE_THRESHOLD:
            return RetentionDecision.ARCHIVE
        else:
            return RetentionDecision.TOMBSTONE

    def compute_resurrection_decay(
        self,
        old_decay: float,
    ) -> float:
        """
        Compute new decay factor for resurrected entity.

        Formula from Dossier C.4.2.1:
        new_decay = max(0.70, 0.50 + old_decay × 0.50)

        Effect:
        - Floor of 0.70 (middle of ACTIVE range)
        - Partial memory: retains 50% of prior strength
        - Resurrection feels "fresh but familiar"
        """
        new_decay = max(
            self.RESURRECTION_FLOOR,
            self.RESURRECTION_PARTIAL_WEIGHT + old_decay * self.RESURRECTION_PARTIAL_WEIGHT
        )
        return new_decay

    async def resurrect(
        self,
        entity_id: str,
        entity_table: str,
        trigger: ResurrectionTrigger,
        old_decay: float,
        resurrection_count: int,
        db_conn,
    ) -> ResurrectionResult:
        """
        Restore archived entity with boosted decay factor.

        Spec: Dossier Appendix C.4.2.1
        """
        new_decay = self.compute_resurrection_decay(old_decay)
        new_resurrection_count = resurrection_count + 1

        # Update entity record
        await db_conn.execute(
            f"""
            UPDATE {entity_table}
            SET decay_factor = $1,
                resurrection_count = $2,
                last_accessed_at = (EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT,
                archival_status = 'ACTIVE'
            WHERE entity_id = $3
              AND archival_status IN ('ARCHIVED', 'TOMBSTONE')
            """,
            new_decay,
            new_resurrection_count,
            entity_id,
        )

        result = ResurrectionResult(
            entity_id=entity_id,
            old_decay=old_decay,
            new_decay=new_decay,
            old_status='ARCHIVED',
            new_status='ACTIVE',
            resurrection_count=new_resurrection_count,
            trigger=trigger,
        )

        # Check for instability alert
        if new_resurrection_count >= self.RESURRECTION_ALERT_THRESHOLD:
            logger.warning(
                f"DecayResurrectionLoop: entity {entity_id} resurrected "
                f"{new_resurrection_count} times. Consider marking as decay_immune."
            )

        return result

    async def log_resurrection(
        self,
        result: ResurrectionResult,
        space_id: str,
        cycle_id: str,
        entity_table: str,
        db_conn,
    ) -> None:
        """
        Log resurrection to st_consolidation_audit.
        """
        await db_conn.execute(
            """
            INSERT INTO st_consolidation_audit (
                audit_id, space_id, audit_type, action,
                memory_id, source_table, formula_used,
                inputs_json, outputs_json, explanation,
                cycle_id, created_at
            ) VALUES (
                gen_random_uuid(), $1, 'DECAY', 'RESURRECTION',
                $2, $3, 'resurrection_v1',
                $4, $5, $6,
                $7, (EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT
            )
            """,
            space_id,
            result.entity_id,
            entity_table,
            json.dumps({
                'old_decay': result.old_decay,
                'trigger': result.trigger.value,
                'resurrection_count': result.resurrection_count - 1,
            }),
            json.dumps({
                'new_decay': result.new_decay,
                'archival_status': result.new_status,
            }),
            f"Entity resurrected from {result.old_status} due to {result.trigger.value}",
            cycle_id,
        )

    def should_alert_resurrection_loop(
        self,
        resurrection_count: int,
    ) -> bool:
        """
        Check if resurrection count triggers instability alert.

        From Dossier C.4.2.1:
        - If resurrection_count >= 3 → emit alert DecayResurrectionLoop
        - Interpretation: Entity cycling ARCHIVED ↔ ACTIVE → λ too aggressive
        """
        return resurrection_count >= self.RESURRECTION_ALERT_THRESHOLD
```

**Resurrection Examples** (from Dossier C.4.2.1):

| Old Decay | Old Status | New Decay | New Status | Interpretation |
| --------- | ---------- | --------- | ---------- | -------------- |
| 0.01 | TOMBSTONE | 0.70 | ACTIVE | Strong revival |
| 0.05 | ARCHIVED | 0.70 | ACTIVE | Strong revival (floor) |
| 0.08 | ARCHIVED | 0.70 | ACTIVE | Strong revival (floor) |
| 0.30 | ACTIVE (weak) | 0.70 | ACTIVE | Boosted to stronger |

**Resurrection Triggers** (from Dossier C.4.2.1):

| Trigger | Source | Description |
| ------- | ------ | ----------- |
| QUERY | P04 retrieval | User queries archived entity |
| CO_OCCURRENCE | P03 R1 | Archived entity reappears in new event |
| USER_MENTION | K1 explicit | User explicitly references archived entity |

**Decay Immunity** (from Dossier §4.4.1.1):

- Column `decay_immune = TRUE` → skip decay updates (never archive)
- Candidates: family members, birthdays, critical contacts

**Metrics** (from Dossier C.4.2.1):

| Metric Name | Type | Description |
| ----------- | ---- | ----------- |
| `p03_resurrections_total` | Counter | Total resurrection events by layer |
| `p03_resurrection_rate` | Gauge | Resurrections / total accesses |
| `p03_resurrection_loops` | Counter | Entities with resurrection_count ≥ 3 |

**Configuration**:

| Config Key | Default | Purpose |
| ---------- | ------- | ------- |
| `P03_DECAY_RESURRECTION_MIN` | 0.70 | Floor for resurrected decay |
| `P03_DECAY_RESURRECTION_ALERT_THRESHOLD` | 3 | Resurrection count trigger |

**Deliverables**:

- [ ] `RetentionDecision` enum (KEEP, ARCHIVE, TOMBSTONE)
- [ ] `ResurrectionTrigger` enum (QUERY, CO_OCCURRENCE, USER_MENTION)
- [ ] `ResurrectionResult` dataclass
- [ ] `RetentionEnforcer` class in `k0/modules/consolidation/algorithms/retention_enforcer.py`
- [ ] `evaluate(decay_factor, decay_immune)` returning RetentionDecision
- [ ] `compute_resurrection_decay(old_decay)` with formula `max(0.70, 0.50 + old × 0.50)`
- [ ] `resurrect()` method updating database
- [ ] `log_resurrection()` to st_consolidation_audit
- [ ] Alert on resurrection_count ≥ 3

**Acceptance Criteria**:

- [ ] Resurrection floor is 0.70 (never resurrect below middle ACTIVE)
- [ ] Resurrection count incremented correctly
- [ ] Alert triggered at ≥ 3 resurrections
- [ ] Audit log contains trigger, old/new decay, formula
- [ ] decay_immune entities never archived

**Test File**: `tests/k0/pipelines/p03/test_r3_retention_enforcer.py`

**Test Cases**:

1. `test_evaluate_keep_above_threshold` — decay ≥ 0.10 → KEEP
2. `test_evaluate_archive_mid_range` — 0.01 ≤ decay < 0.10 → ARCHIVE
3. `test_evaluate_tombstone_below_threshold` — decay < 0.01 → TOMBSTONE
4. `test_decay_immune_always_keep` — decay_immune=True → KEEP
5. `test_resurrection_formula` — verify max(0.70, 0.50 + old × 0.50)
6. `test_resurrection_floor` — old_decay=0.01 → new_decay=0.70
7. `test_resurrection_count_increment` — count increases each time
8. `test_resurrection_loop_alert` — count ≥ 3 triggers alert
9. `test_resurrection_audit_logged` — st_consolidation_audit entry created

**Blocked By**: 4.3.3

**Blocks**: 4.3.5, 4.3.6, 4.3.8

---

#### Issue 4.3.5 — Implement per-entity access tracking

**Status**: NOT_STARTED

**Spec Reference**:

- [Dossier §4.4.1](../pipelines/P03_consolidation_dossier_v2.md#441-per-entity-access-tracking) (lines 3388-3610) — Per-Entity Access Tracking
- [P03EventState.access_count](../../k0/pipelines/p03/event_state.py#L183) — Existing access_count field
- [st_learned_weights](../../k0/db/alembic/versions/0040_st_learned_weights.py) — Parameter storage table
- [P03EventState.decay_score](../../k0/pipelines/p03/event_state.py#L181) — Decay integration point

**Goal**: Track access patterns per entity for adaptive per-entity decay rates (personalized λ).

**Problem Statement** (from Dossier §4.4.1):

> Current decay uses uniform λ per entity-type. But "Mom" is accessed daily while "old dentist" never queried. One-size-fits-all decay rates underperform. Track access patterns per entity and learn personalized decay rate (λ) using Bayesian estimation.

**Existing Infrastructure**:

| Component | Location | How to Use |
| --------- | -------- | ---------- |
| `P03EventState.access_count` | [event_state.py#L183](../../k0/pipelines/p03/event_state.py#L183) | In-envelope access count |
| `P03EventState.days_since_access` | [event_state.py#L182](../../k0/pipelines/p03/event_state.py#L182) | Days since last access |
| `st_learned_weights` | Migration 0040 | Store per-entity λ values |
| `st_feedback_signals` | Migration 0026 | Access events from P04 query retrieval |

**Learning Eligibility Thresholds** (from Dossier §4.4.1):

| Requirement | Value | Rationale |
| ----------- | ----- | --------- |
| **Minimum accesses** | 5 | Statistical significance for exponential fit |
| **Minimum spread** | 7 days | Avoid bursty skew (e.g., 5 accesses in 1 hour) |
| **Distribution check** | χ² goodness-of-fit | Confirm access pattern fits exponential distribution |

**Why 5 Accesses?** (from Dossier §4.4.1):

- < 3 accesses: Cannot fit exponential (need 2+ intervals)
- 3-4 accesses: High variance in λ estimate
- **5 accesses**: Minimum for reasonable confidence interval (4 inter-access intervals)
- 10+ accesses: Ideal, but delays learning too long

**Why 7-Day Spread?** (from Dossier §4.4.1):

- Bursty (5 accesses in 1 hour) → λ=∞ (misleading)
- One-off burst (5 accesses in 2 days) → λ=0.10 (too aggressive)
- Weekly pattern (5 accesses over 28 days) → λ=0.002 (reasonable)

**Migration** (New columns for ALL 8 entity tables):

```sql
-- Apply to: st_epi, st_sem, st_procedural, st_social, st_kg_dom, st_kg_edges, st_prospective, st_hipp_events
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS access_count INTEGER DEFAULT 0;
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS first_access_at BIGINT;
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS last_access_at BIGINT;
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS access_intervals_ms BIGINT[];

CREATE INDEX IF NOT EXISTS idx_{table}_access
  ON {table}(access_count, last_access_at)
  WHERE access_count >= 5;
```

**Implementation**:

```python
# File: k0/modules/consolidation/algorithms/access_tracker.py

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class AccessStats:
    """Access statistics for an entity."""
    entity_id: str
    access_count: int
    first_access_at: int  # ms
    last_access_at: int   # ms
    access_intervals_ms: List[int]
    spread_days: float
    eligible_for_learning: bool


class AccessTracker:
    """
    Track entity access patterns for per-entity decay learning.

    Spec: Dossier §4.4.1
    """

    MIN_ACCESS_COUNT = 5
    MIN_SPREAD_DAYS = 7
    MAX_INTERVALS_STORED = 10

    async def record_access(
        self,
        entity_id: str,
        entity_table: str,
        accessed_at_ms: int,
        db_conn,
    ) -> AccessStats:
        """
        Record an entity access (triggered by P04 query retrieval).

        Algorithm (from Dossier §4.4.1):
        1. Fetch current access tracking data
        2. Compute inter-access interval if prior access exists
        3. Append to intervals array (keep last 10)
        4. Update access_count, first_access_at, last_access_at
        5. Check if entity now qualifies for λ learning (5+ accesses, 7+ day spread)
        """
        # Implementation per dossier §4.4.1 record_access pseudo-code
        pass

    async def check_learning_eligibility(
        self,
        entity_id: str,
        entity_table: str,
        db_conn,
    ) -> bool:
        """
        Check if entity has enough data for λ learning.

        Returns: True if 5+ accesses with 7+ day spread
        """
        pass

    async def get_inter_access_intervals_days(
        self,
        entity_id: str,
        entity_table: str,
        db_conn,
    ) -> List[float]:
        """
        Get inter-access intervals in days for Bayesian estimation.

        Returns: List of intervals in days (e.g., [2.3, 5.1, 1.8, 3.4])
        """
        pass
```

**BayesianLambdaEstimator** (from Dossier §4.4.1):

```python
# File: k0/modules/consolidation/algorithms/bayesian_lambda.py

class BayesianLambdaEstimator:
    """
    Estimate per-entity decay rate λ using Bayesian inference.

    Scientific Basis: Maximum Likelihood Estimation for exponential distribution.
    λ_MLE = n / Σ(intervals)  where n = number of intervals
    """

    async def estimate_lambda(
        self,
        entity_id: str,
        entity_table: str,
        intervals_days: List[float],
    ) -> Optional[float]:
        """
        Estimate λ from inter-access intervals.

        Requires: intervals_days has 4+ values (from 5+ accesses)
        Returns: λ estimate or None if insufficient data
        """
        if len(intervals_days) < 4:
            return None

        # MLE for exponential distribution
        lambda_mle = len(intervals_days) / sum(intervals_days)

        # Clamp to reasonable bounds
        return max(0.0001, min(0.1, lambda_mle))

    async def persist_lambda(
        self,
        entity_id: str,
        space_id: str,
        lambda_value: float,
        confidence: float,
        sample_count: int,
        db_conn,
    ) -> None:
        """
        Store learned λ in st_learned_weights.

        Uses param_key = f'decay_lambda_{entity_id}'
        """
        pass
```

**Configuration** (from Dossier §4.4.1):

| Config Key | Default | Purpose |
| ---------- | ------- | ------- |
| `P03_ACCESS_MIN_COUNT` | 5 | Min accesses before learning λ |
| `P03_ACCESS_MIN_SPREAD_DAYS` | 7 | Min spread between first and last access |
| `P03_ACCESS_INTERVALS_MAX` | 10 | Max intervals to store per entity |

**Metrics** (from Dossier §4.4.1):

| Metric Name | Type | Description |
| ----------- | ---- | ----------- |
| `p03_entities_with_5plus_accesses` | Gauge | Entities eligible for learning |
| `p03_access_spread_histogram` | Histogram | Days between first and last access |
| `p03_inter_access_interval_p50` | Gauge | Median inter-access interval in days |
| `p03_lambda_estimation_triggered` | Counter | Entities crossing 5-access threshold |

**Deliverables**:

- [ ] Migration adding `access_count`, `first_access_at`, `last_access_at`, `access_intervals_ms` to 8 tables
- [ ] `AccessTracker` class in `k0/modules/consolidation/algorithms/access_tracker.py`
- [ ] `record_access(entity_id, entity_table, accessed_at_ms)` per dossier §4.4.1
- [ ] `check_learning_eligibility(entity_id, entity_table)` returning bool
- [ ] `get_inter_access_intervals_days(entity_id, entity_table)` returning List[float]
- [ ] `BayesianLambdaEstimator` class in `k0/modules/consolidation/algorithms/bayesian_lambda.py`
- [ ] `estimate_lambda(entity_id, entity_table, intervals_days)` using MLE
- [ ] Store learned λ in `st_learned_weights` with param_scope='entity'

**Acceptance Criteria**:

- [ ] Access count increments on each P04 retrieval
- [ ] Inter-access intervals stored (max 10)
- [ ] Eligibility check requires 5+ accesses AND 7+ day spread
- [ ] λ estimate uses MLE formula: λ = n / Σ(intervals)
- [ ] Learned λ clamped to [0.0001, 0.1] range
- [ ] Persisted to `st_learned_weights` with confidence score

**Test File**: `tests/k0/pipelines/p03/test_r3_access_tracker.py`

**Test Cases**:

1. `test_first_access_sets_timestamps` — first_access_at = last_access_at on first call
2. `test_interval_computed_on_subsequent_access` — correct ms interval stored
3. `test_intervals_capped_at_10` — old intervals dropped when exceeding 10
4. `test_eligibility_requires_5_accesses` — 4 accesses returns False
5. `test_eligibility_requires_7_day_spread` — 5 accesses in 1 day returns False
6. `test_lambda_mle_formula` — verify λ = n / Σ(intervals)
7. `test_lambda_clamped_to_bounds` — λ stays in [0.0001, 0.1]
8. `test_lambda_persisted_to_st_learned_weights` — correct row inserted

**Blocked By**: 4.3.4

**Blocks**: 4.3.12

---

#### Issue 4.3.6 — Implement pruning regret detection

**Status**: NOT_STARTED

**Spec Reference**:

- [Dossier §4.4.2](../pipelines/P03_consolidation_dossier_v2.md#442-pruning-regret-detection) (lines 3694-3790) — Pruning Regret Detection
- [Dossier §6.19](../pipelines/P03_consolidation_dossier_v2.md#619-st_pruned_entities-regret-tracking) (lines 9631-9800) — st_pruned_entities schema
- [st_feedback_signals](../../k0/db/alembic/versions/0026_st_feedback_signals.py) — Regret signal destination
- [P03EventState.prune_decision](../../k0/pipelines/p03/event_state.py#L184) — Prune decision enum

**Goal**: Detect when pruned entities are later queried ("regret") and adjust decay rates.

**Problem Statement** (from Dossier §4.4.2):

> R3 decay may prune entities too aggressively. If user later queries a pruned entity ("regret"), we need to detect this and adjust decay rates. Track pruned entities for 14 days and match against incoming queries.

**Why 14 Days?** (from Dossier §4.4.2):

- **Weekly patterns**: User may query "doctor appointment" every Monday (7-day cycle)
- **Biweekly patterns**: Payday reminders (14-day cycle)
- **Storage manageable**: Typical space prunes ~100 entities/day × 14 days = 1400 entities (~6 MB)
- **Regret decay**: 90% of regrets occur within 14 days (empirical observation)

**Storage Retention Strategy** (from Dossier §4.4.2):

| Data | Retention | Location | Purpose |
| ---- | --------- | -------- | ------- |
| Pruned embedding | 14 days | st_pruned_entities.embedding | Semantic matching |
| Pruned name | 14 days | st_pruned_entities.canonical_name | String matching |
| Entity metadata | 14 days | st_pruned_entities (full row) | Context for learning |
| Match events | 30 days | st_feedback_signals | Longer retention for analysis |

**st_pruned_entities Schema** (from Dossier §6.19.1):

```sql
CREATE TABLE st_pruned_entities (
  -- Identity
  prune_id TEXT PRIMARY KEY,              -- Unique prune event ID
  entity_id TEXT NOT NULL,                -- Original entity ID (before pruning)
  entity_type TEXT NOT NULL,              -- PERSON, PLACE, THING, etc.

  -- Matching data (for regret detection)
  canonical_name TEXT NOT NULL,           -- Normalized name for fuzzy matching
  embedding VECTOR(1024) NOT NULL,        -- Embedding for semantic matching

  -- Context
  space_id TEXT NOT NULL,                 -- Isolation by space
  layer_table TEXT NOT NULL,              -- Source table (st_epi, st_sem, etc.)
  decay_factor_at_prune REAL NOT NULL,    -- What decay_factor was when pruned
  lambda_at_prune REAL NOT NULL,          -- What λ was used

  -- Timestamps
  pruned_at BIGINT NOT NULL,              -- When pruned (epoch ms)
  matched_query_id TEXT,                  -- If regret detected, which query matched
  matched_at BIGINT,                      -- When regret detected
  match_type TEXT,                        -- STRONG_MATCH, LIKELY_MATCH, SEMANTIC_MATCH
  match_confidence REAL,                  -- Match confidence [0, 1]

  FOREIGN KEY (space_id) REFERENCES st_spaces(space_id)
);

-- Indexes for matching and cleanup
CREATE INDEX idx_pruned_entity_type ON st_pruned_entities(entity_type, space_id);
CREATE INDEX idx_pruned_space_time ON st_pruned_entities(space_id, pruned_at DESC);
CREATE INDEX idx_pruned_embedding ON st_pruned_entities
  USING ivfflat (embedding vector_cosine_ops)
  WHERE matched_at IS NULL;
CREATE INDEX idx_pruned_cleanup ON st_pruned_entities(pruned_at)
  WHERE matched_at IS NULL;
```

**Implementation**:

```python
# File: k0/modules/consolidation/algorithms/prune_regret_detector.py

from dataclasses import dataclass
from typing import List, Optional
from enum import Enum
import numpy as np


class MatchType(Enum):
    """Match confidence levels for regret detection."""
    STRONG_MATCH = "STRONG_MATCH"        # cosine >= 0.90
    LIKELY_MATCH = "LIKELY_MATCH"        # cosine >= 0.85
    SEMANTIC_MATCH = "SEMANTIC_MATCH"    # cosine >= 0.80


@dataclass
class RegretMatch:
    """Result from regret detection."""
    prune_id: str
    entity_id: str
    entity_type: str
    match_type: MatchType
    match_confidence: float
    query_id: str
    pruned_at: int
    matched_at: int


class PrunedEntityTracker:
    """
    Track pruned entities for regret detection.

    Spec: Dossier §6.19.3
    """

    async def track_pruned_entity(
        self,
        entity_id: str,
        entity_type: str,
        canonical_name: str,
        embedding: np.ndarray,
        space_id: str,
        layer_table: str,
        decay_factor: float,
        lambda_value: float,
        db_conn,
    ) -> str:
        """
        Insert pruned entity into st_pruned_entities.

        Called from R3 when entity transitions to TOMBSTONE.
        Returns: prune_id
        """
        pass


class PruneRegretDetector:
    """
    Detect regret when query matches recently pruned entity.

    Spec: Dossier §4.4.2
    """

    STRONG_THRESHOLD = 0.90
    LIKELY_THRESHOLD = 0.85
    SEMANTIC_THRESHOLD = 0.80

    async def check_query(
        self,
        query_embedding: np.ndarray,
        space_id: str,
        query_id: str,
        db_conn,
    ) -> List[RegretMatch]:
        """
        Check if query matches any recently pruned entities.

        Algorithm:
        1. Query st_pruned_entities for unmatched entries in space
        2. Compute cosine similarity with query embedding
        3. If similarity >= 0.85, mark as regret match
        4. Update st_pruned_entities with match info
        5. Emit REGRET_SIGNAL to P21
        """
        pass

    async def emit_regret_signal(
        self,
        match: RegretMatch,
        space_id: str,
        db_conn,
    ) -> None:
        """
        Emit regret signal to st_feedback_signals for λ adjustment.

        Signal type: 'PRUNE_REGRET'
        Confidence: match.match_confidence
        """
        pass


class PrunedEntitiesCleanup:
    """
    Clean up old pruned entities.

    Spec: Dossier §6.19.4
    """

    UNMATCHED_RETENTION_DAYS = 14
    MATCHED_RETENTION_DAYS = 30

    async def cleanup_old_pruned_entities(self, db_conn) -> int:
        """
        Delete pruned entities older than retention period.

        - Unmatched: Delete after 14 days
        - Matched (regrets): Keep for 30 days for analysis

        Returns: count of deleted rows
        """
        pass
```

**Cleanup Job** (from Dossier §6.19.4):

- Runs at 2am daily via scheduler
- Deletes unmatched entities > 14 days old
- Deletes matched entities > 30 days old

**Configuration** (from Dossier §4.4.2):

| Config Key | Default | Purpose |
| ---------- | ------- | ------- |
| `P03_PRUNE_REGRET_WINDOW_DAYS` | 14 | Tracking window for unmatched |
| `P03_PRUNE_REGRET_MATCHED_DAYS` | 30 | Retention for matched (regrets) |
| `P03_PRUNE_REGRET_CLEANUP_HOUR` | 2 | Cleanup job hour (2am) |
| `P03_PRUNE_REGRET_MAX_STORAGE_MB` | 50 | Alert if storage exceeds |

**Metrics** (from Dossier §4.4.2):

| Metric Name | Type | Description |
| ----------- | ---- | ----------- |
| `p03_pruned_entities_tracked` | Gauge | Current count in st_pruned_entities |
| `p03_pruned_entities_added` | Counter | Entities added to tracking table |
| `p03_pruned_entities_cleaned` | Counter | Entities removed by cleanup job |
| `p03_prune_regrets` | Counter | Regret signals emitted |
| `p03_regret_rate` | Gauge | regrets / total_prunes |

**Storage Estimates** (from Dossier §4.4.2):

| Space Size | Entities/Day Pruned | 14-Day Storage | Embedding Size (1024 dims) |
| ---------- | ------------------- | -------------- | -------------------------- |
| Small (1-2 users) | 50 | 700 entities | ~3 MB |
| Medium (3-5 users) | 100 | 1400 entities | ~6 MB |
| Large (6+ users) | 200 | 2800 entities | ~12 MB |

**Deliverables**:

- [ ] Migration creating `st_pruned_entities` table per Dossier §6.19.1
- [ ] RLS policy for st_pruned_entities per Dossier §6.19.2
- [ ] `PrunedEntityTracker` class in `k0/modules/consolidation/algorithms/prune_regret_detector.py`
- [ ] `track_pruned_entity()` inserting row on TOMBSTONE transition
- [ ] `PruneRegretDetector` class with `check_query(query_embedding, space_id, query_id)`
- [ ] `emit_regret_signal()` inserting PRUNE_REGRET into st_feedback_signals
- [ ] `PrunedEntitiesCleanup` class with 14/30 day retention logic
- [ ] Scheduler job running at 2am for cleanup

**Acceptance Criteria**:

- [ ] Pruned entities tracked with embedding + metadata
- [ ] Query matching uses cosine similarity with pgvector
- [ ] Regret detected when similarity >= 0.85
- [ ] PRUNE_REGRET signal emitted to st_feedback_signals
- [ ] Unmatched cleanup after 14 days, matched after 30 days
- [ ] Space isolation enforced via RLS

**Test File**: `tests/k0/pipelines/p03/test_r3_prune_regret.py`

**Test Cases**:

1. `test_track_pruned_entity_inserts_row` — row created on track
2. `test_regret_detected_at_085_cosine` — match at 0.85 similarity
3. `test_no_regret_below_085` — no match at 0.84 similarity
4. `test_regret_signal_emitted` — st_feedback_signals row created
5. `test_cleanup_unmatched_14_days` — unmatched deleted after 14 days
6. `test_cleanup_matched_30_days` — matched kept until 30 days
7. `test_space_isolation` — can only see own space's pruned entities
8. `test_match_type_classification` — STRONG >= 0.90, LIKELY >= 0.85

**Blocked By**: 4.3.4

**Blocks**: 4.3.12

---

#### Issue 4.3.7 — Implement M19 DuplicateDetector with novelty scoring

**Status**: NOT_STARTED

**Spec Reference**:

- [Dossier §7.4.2](../pipelines/P03_consolidation_dossier_v2.md#742-m19--duplicatedetector) (lines 11181-11240) — M19 DuplicateDetector module
- [Dossier §4.4.3](../pipelines/P03_consolidation_dossier_v2.md#443-novelty-scoring) (lines 3788-3820) — Novelty scoring formula
- [Dossier §4.4.2.1](../pipelines/P03_consolidation_dossier_v2.md#4421-adaptive-novelty-bonuses) (lines 3798-3870) — Adaptive novelty bonuses
- [P03PhaseOutputs.Insight.novelty_score](../../k0/pipelines/p03/phase_outputs.py#L275) — Existing novelty_score field
- [SimHasher](./M4_EXECUTION.md#issue-431) — SimHash dependency (Issue 4.3.1)
- [TwoStageDeduplicator](./M4_EXECUTION.md#issue-432) — Two-stage dependency (Issue 4.3.2)

**Goal**: Calculate novelty scores for events combining deduplication with activity-based bonuses/penalties.

**Problem Statement** (from Dossier §7.4.2):

> DuplicateDetector combines SimHash-based deduplication with novelty scoring. Events that are first occurrences, milestones, or rare patterns get boosted. Routine activities get penalized. The resulting novelty_score affects importance_score and retention decisions.

**Existing Infrastructure**:

| Component | Location | How to Use |
| --------- | -------- | ---------- |
| `P03EventState.novelty_factor` | [event_state.py#L155](../../k0/pipelines/p03/event_state.py#L155) | Store novelty result |
| `P03EventState.is_duplicate` | [event_state.py#L172](../../k0/pipelines/p03/event_state.py#L172) | Duplicate flag |
| `P03EventState.duplicate_of_id` | [event_state.py#L173](../../k0/pipelines/p03/event_state.py#L173) | Canonical event |
| `SimHasher` | Issue 4.3.1 | Hash computation + threshold |
| `TwoStageDeduplicator` | Issue 4.3.2 | Two-stage matching |
| `st_hipp_events.novelty_score` | Migration 0022 | Persistence column |

**DuplicationResult Dataclass** (from Dossier §7.4.2):

```python
@dataclass
class DuplicationResult:
    """Result from duplicate detection and novelty scoring."""
    event_id: str
    is_duplicate: bool                  # True if exact duplicate found
    near_duplicates: List[str]          # event_ids of near-duplicates
    novelty_score: float                # [0-1] higher = more novel
    duplicate_of: Optional[str]         # Canonical event if duplicate
```

**Novelty Formula** (from Dossier §7.4.2):

```python
novelty = base_novelty × (1 + first_time_bonus) × (1 + milestone_bonus) × (1 - routine_penalty)

where:
  base_novelty = 1 - similarity_to_nearest (from SimHash/embedding)
  first_time_bonus = 0.15 if activity_category never seen before
  milestone_bonus = 0.20 if is_milestone_event (birthday, anniversary, graduation)
  rare_pattern_bonus = 0.10 if activity < 5 times in 90 days
  temporal_anomaly_bonus = 0.10 if time-of-day unusual for this activity
  routine_penalty = 0.30 if activity matches established routine pattern
```

**Bonus/Penalty Values** (from Dossier §4.4.2.1):

| Event Type | Adjustment | When Applied |
| ---------- | ---------- | ------------ |
| First occurrence | +0.15 | Activity category never seen before |
| Milestone event | +0.20 | Birthday, anniversary, graduation, wedding |
| Rare pattern | +0.10 | Activity < 5 times in 90 days |
| Temporal anomaly | +0.10 | Time-of-day unusual for this activity type |
| Routine activity | -0.30 | Activity matches established routine pattern |

**Implementation**:

```python
# File: k0/modules/consolidation/algorithms/duplicate_detector.py

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from enum import Enum


@dataclass
class DuplicationResult:
    """Result from duplicate detection and novelty scoring."""
    event_id: str
    is_duplicate: bool
    near_duplicates: List[str] = field(default_factory=list)
    novelty_score: float = 0.5
    duplicate_of: Optional[str] = None
    match_method: str = ""  # 'SIMHASH', 'EMBEDDING', 'TWO_STAGE'


@dataclass
class NoveltyBonuses:
    """Breakdown of novelty bonuses/penalties applied."""
    first_occurrence: float = 0.0
    milestone: float = 0.0
    rare_pattern: float = 0.0
    temporal_anomaly: float = 0.0
    routine_penalty: float = 0.0


class DuplicateDetector:
    """
    M19 — SimHash-based deduplication and novelty scoring.

    Spec: Dossier §7.4.2

    Combines:
    - SimHash fingerprinting (Issue 4.3.1)
    - Two-stage dedup (Issue 4.3.2)
    - Novelty scoring with bonuses/penalties
    """

    # Default bonus/penalty values (from Dossier §4.4.2.1)
    DEFAULT_FIRST_OCCURRENCE_BONUS = 0.15
    DEFAULT_MILESTONE_BONUS = 0.20
    DEFAULT_RARE_PATTERN_BONUS = 0.10
    DEFAULT_TEMPORAL_ANOMALY_BONUS = 0.10
    DEFAULT_ROUTINE_PENALTY = 0.30

    def __init__(
        self,
        simhasher: "SimHasher",
        two_stage_dedup: "TwoStageDeduplicator",
        bonuses: Optional[Dict[str, float]] = None,
    ):
        self.simhasher = simhasher
        self.two_stage = two_stage_dedup
        self.bonuses = bonuses or {}

    async def detect(
        self,
        event: "P03EventState",
        existing_hashes: Dict[str, int],  # event_id → simhash
        window_events: List["P03EventState"],
        seen_categories: Set[str],
        routine_patterns: Set[str],
    ) -> DuplicationResult:
        """
        Detect duplicates and calculate novelty score.

        Algorithm (from Dossier §7.4.2):
        1. Compare simhash to existing hashes within time window
        2. Hamming distance ≤ threshold = near-duplicate
        3. Distance = 0 = exact duplicate
        4. Calculate novelty score based on multiple factors
        """
        pass

    def _calculate_novelty_score(
        self,
        event: "P03EventState",
        near_duplicates: List[str],
        seen_categories: Set[str],
        routine_patterns: Set[str],
    ) -> tuple[float, NoveltyBonuses]:
        """
        Novelty formula (from Dossier §7.4.2):

        novelty = (1 - similarity_to_nearest) × (1 + first_time_bonus)
                  × (1 + milestone_bonus) × (1 - routine_penalty)

        Returns: (novelty_score, bonuses_breakdown)
        """
        # Base novelty from dedup similarity
        base_novelty = 1.0 - self._max_similarity(event, near_duplicates)

        bonuses = NoveltyBonuses()

        # First occurrence bonus
        if event.activity_type and event.activity_type not in seen_categories:
            bonuses.first_occurrence = self.bonuses.get(
                'first_occurrence', self.DEFAULT_FIRST_OCCURRENCE_BONUS
            )

        # Milestone bonus
        if self._is_milestone_event(event):
            bonuses.milestone = self.bonuses.get(
                'milestone', self.DEFAULT_MILESTONE_BONUS
            )

        # Rare pattern bonus
        if self._is_rare_pattern(event):
            bonuses.rare_pattern = self.bonuses.get(
                'rare_pattern', self.DEFAULT_RARE_PATTERN_BONUS
            )

        # Temporal anomaly bonus
        if self._is_temporal_anomaly(event):
            bonuses.temporal_anomaly = self.bonuses.get(
                'temporal_anomaly', self.DEFAULT_TEMPORAL_ANOMALY_BONUS
            )

        # Routine penalty
        routine_key = f"{event.activity_type}_{event.hour_of_day}"
        if routine_key in routine_patterns:
            bonuses.routine_penalty = self.bonuses.get(
                'routine_penalty', self.DEFAULT_ROUTINE_PENALTY
            )

        # Apply formula
        novelty = (
            base_novelty
            * (1 + bonuses.first_occurrence)
            * (1 + bonuses.milestone)
            * (1 + bonuses.rare_pattern)
            * (1 + bonuses.temporal_anomaly)
            * (1 - bonuses.routine_penalty)
        )

        return (min(1.0, max(0.0, novelty)), bonuses)

    def _is_milestone_event(self, event: "P03EventState") -> bool:
        """Check if event is a milestone (birthday, anniversary, etc.)."""
        milestone_keywords = {
            'birthday', 'anniversary', 'graduation', 'wedding',
            'promotion', 'retirement', 'birth', 'death'
        }
        content_lower = event.content_text.lower()
        return any(kw in content_lower for kw in milestone_keywords)

    def _is_rare_pattern(self, event: "P03EventState") -> bool:
        """Check if activity appears < 5 times in 90 days."""
        # Requires access to historical counts (passed via window_events analysis)
        return False  # Implemented in full version with history lookup

    def _is_temporal_anomaly(self, event: "P03EventState") -> bool:
        """Check if time-of-day is unusual for this activity type."""
        # Requires activity temporal distribution (passed via config)
        return False  # Implemented in full version with temporal profiles

    def _max_similarity(
        self,
        event: "P03EventState",
        near_duplicates: List[str],
    ) -> float:
        """Get highest similarity score to near-duplicates."""
        if not near_duplicates:
            return 0.0
        # Use hamming distance converted to similarity
        return 0.0  # Implemented with actual similarity lookup
```

**Integration with P03EventState**:

```python
# After DuplicateDetector.detect():
event.is_duplicate = result.is_duplicate
event.duplicate_of_id = result.duplicate_of
event.novelty_factor = result.novelty_score
event.hamming_distance = ...  # From SimHash comparison
```

**Metrics** (from Dossier §7.4.2):

| Metric Name | Type | Description |
| ----------- | ---- | ----------- |
| `p03_duplicates_detected` | Counter | Count of exact duplicates |
| `p03_near_duplicates_detected` | Counter | Count of near-duplicates |
| `p03_novelty_score_histogram` | Histogram | Distribution of novelty scores |
| `p03_first_occurrence_bonus_applied` | Counter | First occurrence bonuses |
| `p03_milestone_bonus_applied` | Counter | Milestone bonuses |
| `p03_routine_penalty_applied` | Counter | Routine penalties |

**Deliverables**:

- [ ] `DuplicationResult` dataclass in `k0/modules/consolidation/algorithms/duplicate_detector.py`
- [ ] `NoveltyBonuses` dataclass for bonus breakdown
- [ ] `DuplicateDetector` class integrating SimHasher + TwoStageDeduplicator
- [ ] `detect(event, existing_hashes, window_events, seen_categories, routine_patterns)`
- [ ] `_calculate_novelty_score()` implementing dossier formula
- [ ] `_is_milestone_event()` checking milestone keywords
- [ ] `_is_rare_pattern()` checking 90-day activity counts
- [ ] `_is_temporal_anomaly()` checking time-of-day deviation
- [ ] Update `P03EventState.novelty_factor` with computed score
- [ ] Store `novelty_score` in `st_hipp_events`

**Acceptance Criteria**:

- [ ] Exact duplicates (hamming=0) marked as `is_duplicate=True`
- [ ] Near-duplicates listed in `near_duplicates` array
- [ ] Novelty score in [0, 1] range
- [ ] First occurrence bonus applied when activity unseen
- [ ] Milestone bonus applied for life events
- [ ] Routine penalty reduces novelty for repetitive activities
- [ ] Final novelty clamped to [0, 1]

**Test File**: `tests/k0/pipelines/p03/test_r3_duplicate_detector.py`

**Test Cases**:

1. `test_exact_duplicate_detected` — hamming=0 sets is_duplicate=True
2. `test_near_duplicate_listed` — hamming≤3 adds to near_duplicates
3. `test_novelty_base_from_similarity` — base = 1 - max_similarity
4. `test_first_occurrence_bonus` — +0.15 for unseen category
5. `test_milestone_bonus` — +0.20 for birthday/anniversary
6. `test_rare_pattern_bonus` — +0.10 for <5 occurrences
7. `test_routine_penalty` — -0.30 for routine match
8. `test_novelty_clamped` — result in [0, 1]
9. `test_event_state_updated` — novelty_factor set correctly
10. `test_no_duplicates_high_novelty` — no matches → novelty near 1.0

**Blocked By**: 4.3.1, 4.3.2

**Blocks**: 4.3.8, 4.3.12

---

#### Issue 4.3.8 — Implement adaptive novelty bonus learning

**Status**: NOT_STARTED

**Spec Reference**:

- [Dossier §4.4.2.1](../pipelines/P03_consolidation_dossier_v2.md#4421-adaptive-novelty-bonuses) (lines 3798-3870) — Adaptive Novelty Bonuses
- [st_learned_weights](../../k0/db/alembic/versions/0040_st_learned_weights.py) — Parameter storage
- [st_feedback_signals](../../k0/db/alembic/versions/0026_st_feedback_signals.py) — Learning signals source
- [DuplicateDetector](./M4_EXECUTION.md#issue-437) — Consumer of learned bonuses (Issue 4.3.7)

**Goal**: Learn per-space novelty bonus values from feedback to adapt to user preferences.

**Problem Statement** (from Dossier §4.4.2.1):

> Static novelty bonuses (+0.15 first occurrence, +0.20 milestone, +0.10 rare) may over-prioritize or under-prioritize based on actual user behavior. Some users value novelty highly (explorers), others prefer familiar patterns (conservatives). Learning adapts to actual behavior.

**Current Static Bonuses** (from Dossier §4.4.2.1):

| Event Type | Default Bonus | Bounds |
| ---------- | ------------- | ------ |
| First occurrence | +0.15 | [0.05, 0.30] |
| Milestone event | +0.20 | [0.05, 0.30] |
| Rare pattern | +0.10 | [0.05, 0.30] |
| Temporal anomaly | +0.10 | [0.05, 0.30] |

**Learning Signals** (from Dossier §4.4.2.1):

| Signal | Source | Meaning | Adjustment |
| ------ | ------ | ------- | ---------- |
| `NOVEL_EVENT_GROUNDED` | K1 | Novel event was useful in response | Increase bonus +0.01 |
| `NOVEL_EVENT_NEVER_QUERIED` | P04 | Novel event not accessed in 30 days | Decrease bonus -0.02 |
| `USER_SAYS_NOT_NEW` | K1 correction | User says "this wasn't new" | Decrease bonus -0.03 |
| `MILESTONE_GROUNDED` | K1 | Milestone used in conversation | Increase milestone bonus +0.01 |
| `RARE_PATTERN_USEFUL` | K1 | Rare event was retrieved | Increase rare bonus +0.01 |

**Implementation**:

```python
# File: k0/modules/consolidation/algorithms/novelty_bonus_learner.py

from dataclasses import dataclass
from typing import Dict, Optional
from enum import Enum


class NoveltyBonusType(Enum):
    """Types of novelty bonuses that can be learned."""
    FIRST_OCCURRENCE = "first_occurrence"
    MILESTONE = "milestone"
    RARE_PATTERN = "rare_pattern"
    TEMPORAL_ANOMALY = "temporal_anomaly"


class NoveltyFeedbackSignal(Enum):
    """Feedback signals that affect novelty bonuses."""
    NOVEL_EVENT_GROUNDED = "NOVEL_EVENT_GROUNDED"
    NOVEL_EVENT_NEVER_QUERIED = "NOVEL_EVENT_NEVER_QUERIED"
    USER_SAYS_NOT_NEW = "USER_SAYS_NOT_NEW"
    MILESTONE_GROUNDED = "MILESTONE_GROUNDED"
    RARE_PATTERN_USEFUL = "RARE_PATTERN_USEFUL"


@dataclass
class BonusAdjustment:
    """Result from bonus adjustment."""
    bonus_type: NoveltyBonusType
    old_value: float
    new_value: float
    adjustment: float
    signal_type: str
    clamped: bool  # True if hit min/max bound


class AdaptiveNoveltyBonusLearner:
    """
    Learn per-space novelty bonus values from feedback.

    Spec: Dossier §4.4.2.1

    Stores learned bonuses in st_learned_weights with:
    - param_key = 'novelty_bonus_{bonus_type}'
    - param_scope = 'space'
    - scope_id = space_id
    """

    # Default values and bounds from Dossier §4.4.2.1
    DEFAULTS = {
        NoveltyBonusType.FIRST_OCCURRENCE: 0.15,
        NoveltyBonusType.MILESTONE: 0.20,
        NoveltyBonusType.RARE_PATTERN: 0.10,
        NoveltyBonusType.TEMPORAL_ANOMALY: 0.10,
    }

    MIN_BONUS = 0.05
    MAX_BONUS = 0.30

    # Adjustment amounts per signal (from Dossier §4.4.2.1)
    ADJUSTMENTS = {
        NoveltyFeedbackSignal.NOVEL_EVENT_GROUNDED: +0.01,
        NoveltyFeedbackSignal.NOVEL_EVENT_NEVER_QUERIED: -0.02,
        NoveltyFeedbackSignal.USER_SAYS_NOT_NEW: -0.03,
        NoveltyFeedbackSignal.MILESTONE_GROUNDED: +0.01,
        NoveltyFeedbackSignal.RARE_PATTERN_USEFUL: +0.01,
    }

    # Signal → bonus type mapping
    SIGNAL_TO_BONUS = {
        NoveltyFeedbackSignal.NOVEL_EVENT_GROUNDED: NoveltyBonusType.FIRST_OCCURRENCE,
        NoveltyFeedbackSignal.NOVEL_EVENT_NEVER_QUERIED: NoveltyBonusType.FIRST_OCCURRENCE,
        NoveltyFeedbackSignal.USER_SAYS_NOT_NEW: NoveltyBonusType.FIRST_OCCURRENCE,
        NoveltyFeedbackSignal.MILESTONE_GROUNDED: NoveltyBonusType.MILESTONE,
        NoveltyFeedbackSignal.RARE_PATTERN_USEFUL: NoveltyBonusType.RARE_PATTERN,
    }

    def adjust_bonus(
        self,
        bonus_type: NoveltyBonusType,
        feedback_signal: NoveltyFeedbackSignal,
        current_bonus: float,
    ) -> BonusAdjustment:
        """
        Adjust novelty bonus based on feedback signal.

        Algorithm (from Dossier §4.4.2.1):
        1. Look up adjustment amount for signal
        2. Add adjustment to current bonus
        3. Clamp to [0.05, 0.30] range
        4. Return adjustment result
        """
        adjustment = self.ADJUSTMENTS.get(feedback_signal, 0.0)
        new_bonus = current_bonus + adjustment

        # Clamp to bounds
        clamped = False
        if new_bonus < self.MIN_BONUS:
            new_bonus = self.MIN_BONUS
            clamped = True
        elif new_bonus > self.MAX_BONUS:
            new_bonus = self.MAX_BONUS
            clamped = True

        return BonusAdjustment(
            bonus_type=bonus_type,
            old_value=current_bonus,
            new_value=new_bonus,
            adjustment=adjustment,
            signal_type=feedback_signal.value,
            clamped=clamped,
        )

    async def process_feedback_signal(
        self,
        signal_type: str,
        space_id: str,
        db_conn,
    ) -> Optional[BonusAdjustment]:
        """
        Process a feedback signal and update learned bonus.

        Steps:
        1. Map signal to bonus type
        2. Fetch current bonus from st_learned_weights (or use default)
        3. Compute adjustment
        4. Persist updated bonus
        """
        try:
            feedback_signal = NoveltyFeedbackSignal(signal_type)
        except ValueError:
            return None  # Unknown signal type

        bonus_type = self.SIGNAL_TO_BONUS.get(feedback_signal)
        if not bonus_type:
            return None

        # Fetch current value
        current = await self._get_current_bonus(bonus_type, space_id, db_conn)

        # Compute adjustment
        result = self.adjust_bonus(bonus_type, feedback_signal, current)

        # Persist if changed
        if result.new_value != result.old_value:
            await self._persist_bonus(
                bonus_type, space_id, result.new_value, db_conn
            )

        return result

    async def _get_current_bonus(
        self,
        bonus_type: NoveltyBonusType,
        space_id: str,
        db_conn,
    ) -> float:
        """Fetch current bonus from st_learned_weights or return default."""
        param_key = f"novelty_bonus_{bonus_type.value}"

        row = await db_conn.fetchrow(
            """
            SELECT current_value FROM st_learned_weights
            WHERE param_key = $1 AND space_id = $2 AND param_scope = 'space'
            """,
            param_key,
            space_id,
        )

        if row:
            return row["current_value"]
        return self.DEFAULTS.get(bonus_type, 0.15)

    async def _persist_bonus(
        self,
        bonus_type: NoveltyBonusType,
        space_id: str,
        new_value: float,
        db_conn,
    ) -> None:
        """Upsert bonus value to st_learned_weights."""
        param_key = f"novelty_bonus_{bonus_type.value}"
        prior_value = self.DEFAULTS.get(bonus_type, 0.15)

        await db_conn.execute(
            """
            INSERT INTO st_learned_weights (
                param_id, param_key, param_scope, scope_id, space_id,
                current_value, prior_value, confidence, sample_count, updated_at
            ) VALUES (
                $1, $2, 'space', $3, $3,
                $4, $5, 0.5, 1, $6
            )
            ON CONFLICT (space_id, param_key, param_scope, scope_id)
            DO UPDATE SET
                current_value = $4,
                sample_count = st_learned_weights.sample_count + 1,
                updated_at = $6
            """,
            generate_id(),
            param_key,
            space_id,
            new_value,
            prior_value,
            now_ms(),
        )

    async def get_all_bonuses(
        self,
        space_id: str,
        db_conn,
    ) -> Dict[NoveltyBonusType, float]:
        """Get all bonus values for a space (with defaults for missing)."""
        result = {}
        for bonus_type in NoveltyBonusType:
            result[bonus_type] = await self._get_current_bonus(
                bonus_type, space_id, db_conn
            )
        return result
```

**Storage Pattern** (in st_learned_weights):

```sql
-- Example stored value
INSERT INTO st_learned_weights (
    param_id, param_key, param_scope, scope_id, space_id,
    current_value, prior_value, confidence, sample_count
) VALUES (
    ulid.new(),
    'novelty_bonus_first_occurrence',
    'space',
    'space-123',
    'space-123',
    0.17,  -- Learned value (increased from 0.15)
    0.15,  -- Static prior
    0.85,  -- Confidence
    250    -- Feedback samples
);
```

**Configuration** (from Dossier §4.4.2.1):

| Config Key | Default | Purpose |
| ---------- | ------- | ------- |
| `P03_NOVELTY_BONUS_FIRST` | 0.15 | Default first occurrence bonus |
| `P03_NOVELTY_BONUS_MILESTONE` | 0.20 | Default milestone bonus |
| `P03_NOVELTY_BONUS_RARE` | 0.10 | Default rare pattern bonus |
| `P03_NOVELTY_BONUS_TEMPORAL` | 0.10 | Default temporal anomaly bonus |
| `P03_NOVELTY_BONUS_MIN` | 0.05 | Floor (cannot go below) |
| `P03_NOVELTY_BONUS_MAX` | 0.30 | Ceiling (cannot exceed) |

**Metrics** (from Dossier §4.4.2.1):

| Metric Name | Type | Description |
| ----------- | ---- | ----------- |
| `p03_novelty_bonus_applied` | Counter | Count of bonus applications by type |
| `p03_novelty_bonus_current` | Gauge | Current bonus values by type |
| `p03_novelty_false_positive_rate` | Gauge | Rate of "not new" corrections |
| `p03_novelty_bonus_adjustments` | Counter | Total adjustments by signal type |

**Deliverables**:

- [ ] `NoveltyBonusType` enum in `k0/modules/consolidation/algorithms/novelty_bonus_learner.py`
- [ ] `NoveltyFeedbackSignal` enum with 5 signal types
- [ ] `BonusAdjustment` dataclass for adjustment results
- [ ] `AdaptiveNoveltyBonusLearner` class with adjustment logic
- [ ] `adjust_bonus(bonus_type, feedback_signal, current_bonus)` implementing dossier formula
- [ ] `process_feedback_signal(signal_type, space_id)` for P21 integration
- [ ] `_get_current_bonus()` fetching from st_learned_weights with fallback to default
- [ ] `_persist_bonus()` upserting to st_learned_weights
- [ ] `get_all_bonuses(space_id)` for DuplicateDetector initialization
- [ ] All adjustments clamped to [0.05, 0.30]

**Acceptance Criteria**:

- [ ] NOVEL_EVENT_GROUNDED increases bonus by +0.01
- [ ] NOVEL_EVENT_NEVER_QUERIED decreases bonus by -0.02
- [ ] USER_SAYS_NOT_NEW decreases bonus by -0.03
- [ ] MILESTONE_GROUNDED increases milestone bonus by +0.01
- [ ] RARE_PATTERN_USEFUL increases rare bonus by +0.01
- [ ] All values clamped to [0.05, 0.30]
- [ ] Persisted to st_learned_weights with correct param_key
- [ ] Sample count incremented on each update

**Test File**: `tests/k0/pipelines/p03/test_r3_novelty_learner.py`

**Test Cases**:

1. `test_grounded_signal_increases_bonus` — +0.01 on NOVEL_EVENT_GROUNDED
2. `test_never_queried_decreases_bonus` — -0.02 on NOVEL_EVENT_NEVER_QUERIED
3. `test_user_says_not_new_decreases_bonus` — -0.03 on USER_SAYS_NOT_NEW
4. `test_milestone_grounded_increases_milestone` — +0.01 on MILESTONE_GROUNDED
5. `test_rare_pattern_useful_increases_rare` — +0.01 on RARE_PATTERN_USEFUL
6. `test_clamped_at_minimum` — cannot go below 0.05
7. `test_clamped_at_maximum` — cannot exceed 0.30
8. `test_persisted_to_st_learned_weights` — correct row upserted
9. `test_default_used_when_no_learned_value` — returns 0.15/0.20/0.10 defaults
10. `test_sample_count_incremented` — sample_count increases on update

**Blocked By**: 4.3.7

**Blocks**: 4.3.12

---

#### Issue 4.3.9 — Implement decay immunity ontology

**Status**: NOT_STARTED

**Spec Reference**:

- [Dossier §4.4.3.1](../pipelines/P03_consolidation_dossier_v2.md#4431-decay-immunity) (lines 3887-3980) — Decay Immunity
- [st_kg_dom](../../k0/db/alembic/versions/0032_st_kg_dom.py) — Missing `decay_immune` column
- [st_epi](../../k0/db/alembic/versions/0027_st_epi.py) — Missing `decay_immune` column
- [st_kg_edges](../../k0/db/alembic/versions/0033_st_kg_edges.py) — Missing `decay_immune` column

**Goal**: Prevent decay of core identity facts (family, birthdays, home address).

**Problem Statement** (from Dossier §4.4.3.1):

> Some entities should NEVER decay. Core identity facts (birthdays, family names, home address) must persist forever.
>
> **Human Memory Analogy**: We don't forget our own birthday, family members' names, or where we live.

**Two-Level Immunity System** (from Dossier §4.4.3.1):

**Level 1: Entity-Level Immunity** (entire entity never decays):

| Entity Type | Behavior | Rationale |
| ----------- | -------- | --------- |
| `FAMILY_MEMBER` | ALL attributes immune | Family never forgotten |

**Level 2: Attribute-Level Immunity** (specific fields protected):

| Entity Type | Immune Attributes | Rationale |
| ----------- | ----------------- | --------- |
| `PERSON` | `birthday`, `name`, `relationship_to_user` | Core identity |
| `PLACE` | `home_address`, `work_address` | Primary locations |
| `EVENT` | `wedding_date`, `birth_date`, `death_date` | Life milestones |
| `ORGANIZATION` | `employer`, `school` | Major affiliations |
| `CONCEPT` | `core_value`, `religion`, `political_affiliation` | Identity concepts |

**Migration Required** (NEW: 0045_add_decay_immune.py):

```sql
-- Add decay_immune column to 5 memory tables
ALTER TABLE st_kg_dom ADD COLUMN decay_immune BOOLEAN DEFAULT FALSE;
ALTER TABLE st_kg_edges ADD COLUMN decay_immune BOOLEAN DEFAULT FALSE;
ALTER TABLE st_sem ADD COLUMN decay_immune BOOLEAN DEFAULT FALSE;
ALTER TABLE st_social ADD COLUMN decay_immune BOOLEAN DEFAULT FALSE;
ALTER TABLE st_epi ADD COLUMN decay_immune BOOLEAN DEFAULT FALSE;

-- Index for efficient skipping during decay batch jobs
CREATE INDEX idx_kg_dom_decay_immune ON st_kg_dom(decay_immune) WHERE decay_immune = TRUE;
CREATE INDEX idx_epi_decay_immune ON st_epi(decay_immune) WHERE decay_immune = TRUE;
```

**Implementation**:

```python
# File: k0/modules/consolidation/algorithms/immunity_checker.py

from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from enum import Enum


class ImmunityLevel(Enum):
    """Immunity classification levels."""
    NONE = "none"                    # Standard decay applies
    ATTRIBUTE = "attribute"          # Specific attributes protected
    ENTITY = "entity"                # Entire entity protected


@dataclass
class ImmunityResult:
    """Result from immunity check."""
    is_immune: bool
    level: ImmunityLevel
    reason: str
    protected_attributes: List[str]  # Which attributes triggered immunity


class ImmunityChecker:
    """
    Determine if entity should be immune to decay.

    Spec: Dossier §4.4.3.1

    Two-level system:
    1. Entity-level: FAMILY_MEMBER → entire entity immune
    2. Attribute-level: PERSON.birthday → entity immune if attribute present
    """

    # Ontology from Dossier §4.4.3.1
    IMMUNITY_ONTOLOGY: Dict[str, Dict] = {
        'FAMILY_MEMBER': {
            'entity_immune': True,
            'attributes': '*',  # All attributes
        },
        'PERSON': {
            'entity_immune': False,
            'attributes': ['birthday', 'name', 'relationship_to_user'],
        },
        'PLACE': {
            'entity_immune': False,
            'attributes': ['home_address', 'work_address'],
        },
        'EVENT': {
            'entity_immune': False,
            'attributes': ['wedding_date', 'birth_date', 'death_date'],
        },
        'ORGANIZATION': {
            'entity_immune': False,
            'attributes': ['employer', 'school'],
        },
        'CONCEPT': {
            'entity_immune': False,
            'attributes': ['core_value', 'religion', 'political_affiliation'],
        },
    }

    def should_mark_immune(
        self,
        entity_type: str,
        entity_attributes: Dict,
    ) -> ImmunityResult:
        """
        Determine if entity should be marked decay_immune=TRUE.

        Algorithm (from Dossier §4.4.3.1):
        1. Check if entity_type has entity-level immunity
        2. If not, check if any immune attributes are present
        3. Return result with reason and protected attributes
        """
        if entity_type not in self.IMMUNITY_ONTOLOGY:
            return ImmunityResult(
                is_immune=False,
                level=ImmunityLevel.NONE,
                reason="Entity type not in ontology",
                protected_attributes=[],
            )

        ontology = self.IMMUNITY_ONTOLOGY[entity_type]

        # Level 1: Entity-level immunity (e.g., FAMILY_MEMBER)
        if ontology['entity_immune']:
            return ImmunityResult(
                is_immune=True,
                level=ImmunityLevel.ENTITY,
                reason=f"{entity_type} has full entity immunity",
                protected_attributes=list(entity_attributes.keys()),
            )

        # Level 2: Attribute-level immunity
        immune_attrs = ontology['attributes']
        if immune_attrs == '*':
            return ImmunityResult(
                is_immune=True,
                level=ImmunityLevel.ENTITY,
                reason="All attributes protected",
                protected_attributes=list(entity_attributes.keys()),
            )

        # Check if any immune attribute is present
        present_immune = []
        for attr in immune_attrs:
            if attr in entity_attributes and entity_attributes[attr]:
                present_immune.append(attr)

        if present_immune:
            return ImmunityResult(
                is_immune=True,
                level=ImmunityLevel.ATTRIBUTE,
                reason=f"Protected attributes present: {present_immune}",
                protected_attributes=present_immune,
            )

        return ImmunityResult(
            is_immune=False,
            level=ImmunityLevel.NONE,
            reason="No protected attributes found",
            protected_attributes=[],
        )

    def get_immune_entity_types(self) -> Set[str]:
        """Return set of entity types with full entity immunity."""
        return {
            etype for etype, config in self.IMMUNITY_ONTOLOGY.items()
            if config['entity_immune']
        }

    def get_protected_attributes(self, entity_type: str) -> List[str]:
        """Return list of protected attributes for an entity type."""
        if entity_type not in self.IMMUNITY_ONTOLOGY:
            return []
        attrs = self.IMMUNITY_ONTOLOGY[entity_type]['attributes']
        if attrs == '*':
            return ['*']  # All protected
        return list(attrs)
```

**Integration with UnifiedDecayEngine**:

```python
# In UnifiedDecayEngine.apply_decay()

async def apply_decay(self, record, config, current_time):
    """Apply decay with immunity check."""
    # Check immunity first
    if record.decay_immune:
        # Skip decay entirely
        self.metrics.p03_decay_immune_skipped.labels(
            layer=record.layer
        ).inc()
        return record  # No changes

    # Otherwise compute and apply decay
    decay_factor = self.compute_decay_factor(record, config, current_time)
    record.decay_factor = decay_factor
    return record
```

**Auto-Mark on Entity Creation**:

```python
# In P03 Phase 7 (R4 Entity Extraction)

async def create_entity(self, entity_type, attributes, space_id):
    """Create entity with automatic immunity check."""
    immunity_checker = ImmunityChecker()
    result = immunity_checker.should_mark_immune(entity_type, attributes)

    entity = Entity(
        entity_id=generate_id(),
        entity_type=entity_type,
        attributes=attributes,
        decay_immune=result.is_immune,  # Auto-marked
        # ... other fields
    )

    if result.is_immune:
        logger.info(
            f"Auto-marked immune: {entity_type}",
            extra={"reason": result.reason, "attrs": result.protected_attributes}
        )
        self.metrics.p03_decay_immune_entities.labels(
            entity_type=entity_type,
            level=result.level.value
        ).inc()

    return entity
```

**Manual Override via K1**:

```python
# User commands that set immunity:
# "Never forget this" → decay_immune = TRUE
# "You can forget this" → decay_immune = FALSE

async def handle_immunity_command(self, entity_id, set_immune: bool):
    """Allow user to manually override immunity."""
    await self.db.execute(
        """
        UPDATE st_kg_dom
        SET decay_immune = $1, updated_at = $2
        WHERE entity_id = $3
        """,
        set_immune,
        now_ms(),
        entity_id,
    )
```

**Configuration** (from Dossier §4.4.3.1):

| Config Key | Default | Purpose |
| ---------- | ------- | ------- |
| `P03_DECAY_IMMUNITY_ENABLED` | TRUE | Master switch for immunity system |
| `P03_DECAY_FAMILY_MEMBER_IMMUNE` | TRUE | Auto-mark FAMILY_MEMBER immune |
| `P03_DECAY_MILESTONE_EVENTS_IMMUNE` | TRUE | Auto-mark milestone events immune |

**Metrics** (from Dossier §4.4.3.1):

| Metric Name | Type | Description |
| ----------- | ---- | ----------- |
| `p03_decay_immune_entities` | Gauge | Count of immune entities by type and level |
| `p03_decay_immune_skipped` | Counter | Decay updates skipped due to immunity |
| `p03_decay_immunity_auto_marked` | Counter | Entities auto-marked immune on creation |

**Deliverables**:

- [ ] Migration `0045_add_decay_immune.py` adding column to 5 tables
- [ ] `ImmunityLevel` enum in `k0/modules/consolidation/algorithms/immunity_checker.py`
- [ ] `ImmunityResult` dataclass for check results
- [ ] `ImmunityChecker` class with ontology dictionary
- [ ] `should_mark_immune(entity_type, entity_attributes)` implementing dossier logic
- [ ] `get_immune_entity_types()` returning entity-level immune types
- [ ] `get_protected_attributes(entity_type)` returning attribute list
- [ ] Integration with `UnifiedDecayEngine.apply_decay()` to skip immune records
- [ ] Auto-mark logic in P03 Phase 7 entity creation
- [ ] Manual override support for K1 "never forget" commands

**Acceptance Criteria**:

- [ ] FAMILY_MEMBER entities always marked decay_immune=TRUE
- [ ] PERSON with birthday attribute marked immune
- [ ] PLACE with home_address marked immune
- [ ] EVENT with wedding_date/birth_date/death_date marked immune
- [ ] Decay engine skips records with decay_immune=TRUE
- [ ] Metrics track immune counts and skipped updates
- [ ] User can manually override immunity via K1

**Test File**: `tests/k0/pipelines/p03/test_r3_immunity_checker.py`

**Test Cases**:

1. `test_family_member_always_immune` — FAMILY_MEMBER returns entity-level immunity
2. `test_person_with_birthday_immune` — PERSON + birthday → immune
3. `test_person_without_protected_attrs_not_immune` — PERSON + occupation only → not immune
4. `test_place_with_home_address_immune` — PLACE + home_address → immune
5. `test_event_with_milestone_date_immune` — EVENT + wedding_date → immune
6. `test_unknown_entity_type_not_immune` — WIDGET → not immune
7. `test_decay_engine_skips_immune` — decay_immune=TRUE skipped
8. `test_auto_mark_on_entity_creation` — new FAMILY_MEMBER auto-marked
9. `test_manual_override_sets_immunity` — K1 "never forget" sets TRUE
10. `test_manual_override_clears_immunity` — K1 "you can forget" sets FALSE

**Blocked By**: 4.3.1 (requires decay factor storage)

**Blocks**: 4.3.12

---

#### Issue 4.3.10 — Implement prune decision audit logging

**Status**: NOT_STARTED

**Spec Reference**:

- [Dossier §1.4.7](../pipelines/P03_consolidation_dossier_v2.md#147-outcome-tracking-for-thompson-sampling) (lines 1800-2060) — Outcome Tracking Implementation
- [st_consolidation_audit](../../k0/db/alembic/versions/0036_st_consolidation_audit.py) — Audit table (EXISTS)
- [Dossier §6.20](../pipelines/P03_consolidation_dossier_v2.md#620-st_consolidation_audit) — Audit table schema

**Goal**: Record all prune/archive/tombstone decisions for compliance, debugging, and Thompson Sampling feedback.

**Problem Statement**:

> All consolidation decisions must be auditable. GDPR Article 22 requires "meaningful information about the logic involved" in automated decisions. Prune decisions (ARCHIVE, TOMBSTONE) affect data retention and require full traceability.

**Existing Table** (from 0036_st_consolidation_audit.py):

```sql
st_consolidation_audit (
    audit_id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    source_table TEXT NOT NULL,
    action TEXT NOT NULL,  -- 'REINFORCE', 'DECAY', 'ARCHIVE', 'MERGE', 'CREATE', 'EXTEND', 'PRUNE', 'SKIP', 'CONTRADICT'
    formula_used TEXT,
    formula_version TEXT,
    inputs_json TEXT,      -- Decay inputs
    outputs_json TEXT,     -- Decision outputs
    explanation TEXT,
    decision_id TEXT,
    space_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    cycle_id TEXT,
    confidence FLOAT,
    created_at BIGINT NOT NULL,
    threshold_used FLOAT,
    threshold_name TEXT,
    outcome_evaluated BOOLEAN DEFAULT FALSE,
    outcome_success BOOLEAN,
    evaluated_at BIGINT
)
```

**Prune Decision Actions**:

| Action | Trigger | Threshold | Reversible |
| ------ | ------- | --------- | ---------- |
| `ARCHIVE` | decay_factor < 0.10 | `P03_DECAY_ARCHIVE_THRESHOLD` | Yes (resurrect) |
| `TOMBSTONE` | decay_factor < 0.01 | `P03_DECAY_TOMBSTONE_THRESHOLD` | No |
| `PRUNE` | Explicit prune decision | N/A | Track in st_pruned_entities |

**Implementation**:

```python
# File: k0/modules/consolidation/algorithms/prune_audit_logger.py

from dataclasses import dataclass
from typing import Dict, Optional
from enum import Enum
import json


class PruneAction(Enum):
    """Prune decision action types."""
    ARCHIVE = "ARCHIVE"
    TOMBSTONE = "TOMBSTONE"
    PRUNE = "PRUNE"
    SKIP = "SKIP"  # Decision to NOT prune


@dataclass
class PruneDecisionContext:
    """Context for a prune decision."""
    memory_id: str
    source_table: str
    decay_factor: float
    effective_lambda: float
    days_since_access: int
    access_count: int
    is_immune: bool
    threshold_used: float
    threshold_name: str


@dataclass
class PruneAuditRecord:
    """Audit record for a prune decision."""
    audit_id: str
    action: PruneAction
    context: PruneDecisionContext
    explanation: str
    cycle_id: str
    created_at: int


class PruneAuditLogger:
    """
    Log all prune/archive/tombstone decisions to st_consolidation_audit.

    Spec: Dossier §1.4.7, §6.20

    Features:
    - Full decision context captured
    - Sampling for production (10%) vs debug (100%)
    - Links to Thompson Sampling outcome tracking
    """

    # Sampling rates by log level
    SAMPLE_RATE_DEBUG = 1.0    # 100% in debug
    SAMPLE_RATE_PRODUCTION = 0.1  # 10% in production

    def __init__(self, db_conn, is_debug: bool = False):
        self.db_conn = db_conn
        self.sample_rate = (
            self.SAMPLE_RATE_DEBUG if is_debug else self.SAMPLE_RATE_PRODUCTION
        )

    def should_log(self, action: PruneAction) -> bool:
        """
        Determine if this decision should be logged.

        Always log:
        - TOMBSTONE (permanent deletion)
        - First occurrence of ARCHIVE per entity

        Sample log:
        - ARCHIVE (per sample rate)
        - SKIP (per sample rate)
        """
        import random

        if action == PruneAction.TOMBSTONE:
            return True  # Always log permanent deletions

        return random.random() < self.sample_rate

    async def log_prune_decision(
        self,
        action: PruneAction,
        context: PruneDecisionContext,
        space_id: str,
        tenant_id: str,
        cycle_id: str,
    ) -> Optional[str]:
        """
        Log a prune decision to st_consolidation_audit.

        Returns:
            audit_id if logged, None if sampled out
        """
        if not self.should_log(action):
            # Increment counter for sampled-out decisions
            self.metrics.p03_prune_decisions_sampled_out.labels(
                action=action.value
            ).inc()
            return None

        audit_id = generate_id()
        explanation = self._generate_explanation(action, context)

        # Build inputs JSON
        inputs_json = json.dumps({
            "decay_factor": context.decay_factor,
            "effective_lambda": context.effective_lambda,
            "days_since_access": context.days_since_access,
            "access_count": context.access_count,
            "is_immune": context.is_immune,
        })

        # Build outputs JSON
        outputs_json = json.dumps({
            "action": action.value,
            "threshold_used": context.threshold_used,
            "threshold_name": context.threshold_name,
        })

        await self.db_conn.execute(
            """
            INSERT INTO st_consolidation_audit (
                audit_id, memory_id, source_table, action,
                formula_used, formula_version,
                inputs_json, outputs_json, explanation,
                decision_id, space_id, tenant_id, cycle_id,
                confidence, created_at,
                threshold_used, threshold_name,
                outcome_evaluated
            ) VALUES (
                $1, $2, $3, $4,
                'UnifiedDecayFormula', '1.0',
                $5, $6, $7,
                $8, $9, $10, $11,
                $12, $13,
                $14, $15,
                FALSE
            )
            """,
            audit_id,
            context.memory_id,
            context.source_table,
            action.value,
            inputs_json,
            outputs_json,
            explanation,
            audit_id,  # decision_id = audit_id for prune decisions
            space_id,
            tenant_id,
            cycle_id,
            context.decay_factor,  # confidence = decay_factor
            now_ms(),
            context.threshold_used,
            context.threshold_name,
        )

        # Increment logged counter
        self.metrics.p03_prune_decisions_logged.labels(
            action=action.value
        ).inc()

        return audit_id

    def _generate_explanation(
        self,
        action: PruneAction,
        context: PruneDecisionContext,
    ) -> str:
        """Generate human-readable explanation for decision."""
        if context.is_immune:
            return f"SKIP: Entity is decay_immune (never prune)"

        if action == PruneAction.ARCHIVE:
            return (
                f"ARCHIVE: decay_factor={context.decay_factor:.3f} < "
                f"threshold={context.threshold_used:.2f}. "
                f"Not accessed in {context.days_since_access} days. "
                f"Total accesses: {context.access_count}. "
                f"Can be resurrected if queried."
            )

        if action == PruneAction.TOMBSTONE:
            return (
                f"TOMBSTONE: decay_factor={context.decay_factor:.4f} < 0.01. "
                f"Entity has {context.access_count} lifetime accesses over "
                f"{context.days_since_access} days. "
                f"PERMANENT deletion per retention policy."
            )

        if action == PruneAction.SKIP:
            return (
                f"SKIP: decay_factor={context.decay_factor:.3f} >= "
                f"threshold={context.threshold_used:.2f}. "
                f"Entity retained."
            )

        return f"{action.value}: No explanation available"

    async def get_decision_history(
        self,
        memory_id: str,
        limit: int = 10,
    ) -> list:
        """Get audit history for a specific memory."""
        return await self.db_conn.fetch(
            """
            SELECT audit_id, action, explanation, created_at,
                   inputs_json, outputs_json, outcome_success
            FROM st_consolidation_audit
            WHERE memory_id = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            memory_id,
            limit,
        )
```

**Integration with Decay Engine**:

```python
# In UnifiedDecayEngine

async def apply_and_log_prune(self, record, config, cycle_id):
    """Apply decay and log prune decision if threshold crossed."""
    decay_factor = self.compute_decay_factor(record, config, now_ms())

    # Determine action
    if record.decay_immune:
        action = PruneAction.SKIP
        threshold = 0.0
    elif decay_factor < 0.01:
        action = PruneAction.TOMBSTONE
        threshold = 0.01
    elif decay_factor < config.archive_threshold:
        action = PruneAction.ARCHIVE
        threshold = config.archive_threshold
    else:
        action = PruneAction.SKIP
        threshold = config.archive_threshold

    # Build context
    context = PruneDecisionContext(
        memory_id=record.memory_id,
        source_table=record.source_table,
        decay_factor=decay_factor,
        effective_lambda=record.effective_lambda,
        days_since_access=record.days_since_access,
        access_count=record.access_count,
        is_immune=record.decay_immune,
        threshold_used=threshold,
        threshold_name="archive" if action == PruneAction.ARCHIVE else "tombstone",
    )

    # Log decision
    await self.audit_logger.log_prune_decision(
        action=action,
        context=context,
        space_id=record.space_id,
        tenant_id=record.tenant_id,
        cycle_id=cycle_id,
    )

    return action, decay_factor
```

**Configuration**:

| Config Key | Default | Purpose |
| ---------- | ------- | ------- |
| `P03_PRUNE_AUDIT_ENABLED` | TRUE | Master switch for audit logging |
| `P03_PRUNE_AUDIT_SAMPLE_RATE` | 0.10 | Sampling rate in production |
| `P03_PRUNE_AUDIT_DEBUG_MODE` | FALSE | 100% logging when TRUE |
| `P03_PRUNE_AUDIT_RETENTION_DAYS` | 90 | Days to retain audit records |

**Metrics**:

| Metric Name | Type | Description |
| ----------- | ---- | ----------- |
| `p03_prune_decisions_logged` | Counter | Decisions logged by action type |
| `p03_prune_decisions_sampled_out` | Counter | Decisions not logged (sampled) |
| `p03_prune_audit_latency_ms` | Histogram | Latency of audit writes |
| `p03_prune_archive_count` | Counter | ARCHIVE actions taken |
| `p03_prune_tombstone_count` | Counter | TOMBSTONE actions (permanent) |

**Deliverables**:

- [ ] `PruneAction` enum in `k0/modules/consolidation/algorithms/prune_audit_logger.py`
- [ ] `PruneDecisionContext` dataclass for decision context
- [ ] `PruneAuditRecord` dataclass for audit records
- [ ] `PruneAuditLogger` class with sampling logic
- [ ] `should_log()` implementing 100% debug / 10% production sampling
- [ ] `log_prune_decision()` inserting to st_consolidation_audit
- [ ] `_generate_explanation()` creating human-readable explanations
- [ ] `get_decision_history()` for debugging and explainability
- [ ] Integration with `UnifiedDecayEngine` to log all prune decisions
- [ ] TOMBSTONE always logged (100%)

**Acceptance Criteria**:

- [ ] All TOMBSTONE decisions logged (100%)
- [ ] ARCHIVE decisions sampled at configured rate
- [ ] Audit record includes decay_factor, effective_lambda, threshold_used
- [ ] explanation field is human-readable
- [ ] Links to outcome_evaluated for Thompson Sampling feedback
- [ ] Debug mode logs 100% of decisions
- [ ] Production mode logs 10% of non-TOMBSTONE decisions
- [ ] Metrics track logged vs sampled-out counts

**Test File**: `tests/k0/pipelines/p03/test_r3_prune_audit.py`

**Test Cases**:

1. `test_tombstone_always_logged` — TOMBSTONE logs 100% regardless of sample rate
2. `test_archive_sampled_production` — ARCHIVE sampled at 10% in production
3. `test_archive_logged_debug` — ARCHIVE logged 100% in debug mode
4. `test_skip_sampled` — SKIP decisions follow sample rate
5. `test_audit_record_complete` — All fields populated correctly
6. `test_explanation_human_readable` — explanation is understandable
7. `test_inputs_json_valid` — inputs_json parses correctly
8. `test_outputs_json_valid` — outputs_json parses correctly
9. `test_get_decision_history` — History query returns correct records
10. `test_outcome_evaluated_false_initially` — outcome_evaluated starts FALSE

**Blocked By**: 4.3.1 (requires decay factor computation)

**Blocks**: 4.3.12

---

#### Issue 4.3.11 — Implement MinHash LSH for scale (>50K events)

**Status**: NOT_STARTED

**Spec Reference**:

- [Dossier Appendix C.4.1.3](../pipelines/P03_consolidation_dossier_v2.md#c413-scale-strategy-minhash-lsh) (lines 22296-22420) — MinHash LSH Algorithm
- [M01 pattern_separate](../../k0/modules/hippocampus/pattern_separate.py) — Existing MinHash 32 permutations
- [st_hipp_events.minhash32](../../k0/db/alembic/versions/0022_st_hipp_events.py) — Existing minhash storage

**Goal**: Sub-linear duplicate detection for high-volume spaces (>50K events).

**Problem Statement** (from Dossier Appendix C.4.1.3):

> As event count grows, even O(n) SimHash becomes expensive:
>
> - **10K events**: ~10ms per new event (acceptable)
> - **50K events**: ~50ms per new event (slow)
> - **100K+ events**: >100ms per new event (unacceptable)

**Existing Infrastructure**:

| Component | Location | Status |
| --------- | -------- | ------ |
| MinHash 32 permutations | M01 pattern_separate.py | EXISTS |
| minhash32 column | st_hipp_events | EXISTS |
| SimHash pairwise | TwoStageDeduplicator | Issue 4.3.2 |
| SimHash bucketing | TwoStageDeduplicator | Issue 4.3.2 |

**Auto-Switch Logic** (from Dossier Appendix C.4.1.3):

| Event Count | Algorithm | Complexity | Est. Latency |
| ----------- | --------- | ---------- | ------------ |
| < 10,000 | SimHash pairwise | O(n) | 10ms |
| 10K-50K | SimHash + bucketing | O(n/b) | 15ms |
| > 50,000 | MinHash LSH | O(log n) | 20ms |

**MinHash LSH Parameters** (from Dossier):

| Parameter | Value | Rationale |
| --------- | ----- | --------- |
| `num_hashes` | 128 | Higher precision |
| `num_bands` | 32 | Tuned for recall |
| `rows_per_band` | 4 | ~0.85 Jaccard threshold |

**Implementation**:

```python
# File: k0/modules/consolidation/algorithms/minhash_lsh.py

from dataclasses import dataclass
from typing import Dict, List, Set, Optional
from collections import defaultdict
import numpy as np


@dataclass
class MinHashConfig:
    """Configuration for MinHash LSH."""
    num_hashes: int = 128      # Total hash functions
    num_bands: int = 32        # Number of LSH bands
    similarity_threshold: float = 0.85  # Jaccard threshold


@dataclass
class LSHCandidate:
    """Candidate duplicate from LSH lookup."""
    event_id: str
    bands_matched: int
    estimated_similarity: float


class MinHashLSH:
    """
    MinHash with Locality-Sensitive Hashing for sub-linear deduplication.

    Scientific Basis: Broder (1997) - Near-duplicate detection

    Spec: Dossier Appendix C.4.1.3

    Features:
    - 128 hash functions for precision
    - 32 bands for LSH indexing
    - O(log n) candidate retrieval
    - Auto-switch based on event count
    """

    def __init__(self, config: Optional[MinHashConfig] = None):
        self.config = config or MinHashConfig()
        self.rows_per_band = self.config.num_hashes // self.config.num_bands

        # LSH index: (band_idx, band_hash) -> [event_ids]
        self.lsh_index: Dict[tuple, List[str]] = defaultdict(list)

        # Store signatures for similarity computation
        self.signatures: Dict[str, np.ndarray] = {}

    def compute_minhash(self, text: str) -> np.ndarray:
        """
        Compute MinHash signature (128 hash values).

        Uses k-shingling with 3-grams and 128 independent hash functions.
        """
        # Tokenize to 3-grams
        shingles = self._tokenize_shingles(text, k=3)

        if not shingles:
            return np.zeros(self.config.num_hashes, dtype=np.uint64)

        # Initialize signature with infinity
        signature = np.full(self.config.num_hashes, np.iinfo(np.uint64).max, dtype=np.uint64)

        for shingle in shingles:
            for i in range(self.config.num_hashes):
                # Different hash per position using seed
                h = self._murmurhash(shingle, seed=i)
                signature[i] = min(signature[i], h)

        return signature

    def _tokenize_shingles(self, text: str, k: int = 3) -> Set[str]:
        """Extract k-gram shingles from text."""
        text = text.lower().strip()
        if len(text) < k:
            return {text}
        return {text[i:i+k] for i in range(len(text) - k + 1)}

    def _murmurhash(self, text: str, seed: int) -> int:
        """MurmurHash3 with seed for different hash functions."""
        import mmh3
        return mmh3.hash64(text, seed=seed, signed=False)[0]

    def hash_bands(self, signature: np.ndarray) -> List[int]:
        """
        Hash signature into bands for LSH.

        Returns: List of band hashes (one per band)
        """
        band_hashes = []

        for band_idx in range(self.config.num_bands):
            start = band_idx * self.rows_per_band
            end = start + self.rows_per_band
            band = signature[start:end]

            # Hash the band values together
            band_hash = hash(tuple(band.tolist()))
            band_hashes.append(band_hash)

        return band_hashes

    def index_event(self, event_id: str, signature: np.ndarray) -> None:
        """
        Add event to LSH index.

        Called when event is processed by P02/P03.
        """
        self.signatures[event_id] = signature
        band_hashes = self.hash_bands(signature)

        for band_idx, band_hash in enumerate(band_hashes):
            key = (band_idx, band_hash)
            self.lsh_index[key].append(event_id)

    def find_candidates(self, signature: np.ndarray) -> List[LSHCandidate]:
        """
        Find candidate duplicates using LSH.

        Returns: List of candidates with band match counts
        """
        band_hashes = self.hash_bands(signature)

        # Count bands matched per event
        match_counts: Dict[str, int] = defaultdict(int)

        for band_idx, band_hash in enumerate(band_hashes):
            key = (band_idx, band_hash)
            for event_id in self.lsh_index.get(key, []):
                match_counts[event_id] += 1

        # Convert to candidates with estimated similarity
        candidates = []
        for event_id, bands_matched in match_counts.items():
            # Estimate similarity from band match ratio
            estimated_sim = self._estimate_similarity(bands_matched)
            candidates.append(LSHCandidate(
                event_id=event_id,
                bands_matched=bands_matched,
                estimated_similarity=estimated_sim,
            ))

        # Sort by bands matched (descending)
        candidates.sort(key=lambda c: c.bands_matched, reverse=True)

        return candidates

    def _estimate_similarity(self, bands_matched: int) -> float:
        """
        Estimate Jaccard similarity from band match count.

        Formula: P(at least 1 band match) = 1 - (1 - s^r)^b
        Where s = similarity, r = rows_per_band, b = num_bands
        """
        if bands_matched == 0:
            return 0.0
        if bands_matched == self.config.num_bands:
            return 1.0

        # Approximate similarity
        ratio = bands_matched / self.config.num_bands
        return ratio ** (1 / self.rows_per_band)

    def compute_exact_similarity(
        self,
        sig1: np.ndarray,
        sig2: np.ndarray,
    ) -> float:
        """
        Compute exact Jaccard similarity between two signatures.

        Used after LSH candidate retrieval for verification.
        """
        matches = np.sum(sig1 == sig2)
        return matches / len(sig1)

    def remove_event(self, event_id: str) -> None:
        """Remove event from LSH index (on archive/tombstone)."""
        if event_id not in self.signatures:
            return

        signature = self.signatures[event_id]
        band_hashes = self.hash_bands(signature)

        for band_idx, band_hash in enumerate(band_hashes):
            key = (band_idx, band_hash)
            if event_id in self.lsh_index.get(key, []):
                self.lsh_index[key].remove(event_id)

        del self.signatures[event_id]


class AdaptiveDeduplicationStrategy:
    """
    Auto-switch between deduplication strategies based on event count.

    Spec: Dossier Appendix C.4.1.3
    """

    THRESHOLD_PAIRWISE = 10_000   # Below: O(n) pairwise
    THRESHOLD_BUCKETING = 50_000  # Below: SimHash bucketing
    # Above: MinHash LSH

    def __init__(self, simhash_dedup, minhash_lsh: MinHashLSH):
        self.simhash_dedup = simhash_dedup  # TwoStageDeduplicator
        self.minhash_lsh = minhash_lsh
        self.event_count = 0

    def get_strategy(self) -> str:
        """Return current strategy based on event count."""
        if self.event_count < self.THRESHOLD_PAIRWISE:
            return "simhash_pairwise"
        elif self.event_count < self.THRESHOLD_BUCKETING:
            return "simhash_bucketing"
        else:
            return "minhash_lsh"

    async def find_duplicates(
        self,
        text: str,
        embedding: np.ndarray,
        space_id: str,
    ):
        """
        Find duplicates using appropriate strategy.
        """
        strategy = self.get_strategy()

        if strategy == "simhash_pairwise":
            return await self.simhash_dedup.find_duplicates_pairwise(
                text, embedding, space_id
            )
        elif strategy == "simhash_bucketing":
            return await self.simhash_dedup.find_duplicates_bucketed(
                text, embedding, space_id
            )
        else:
            # MinHash LSH
            signature = self.minhash_lsh.compute_minhash(text)
            candidates = self.minhash_lsh.find_candidates(signature)

            # Verify candidates with exact similarity
            verified = []
            for candidate in candidates[:10]:  # Top 10
                stored_sig = self.minhash_lsh.signatures.get(candidate.event_id)
                if stored_sig is not None:
                    exact_sim = self.minhash_lsh.compute_exact_similarity(
                        signature, stored_sig
                    )
                    if exact_sim >= 0.85:
                        verified.append((candidate.event_id, exact_sim))

            return verified

    def update_event_count(self, count: int) -> None:
        """Update event count (called by space stats)."""
        old_strategy = self.get_strategy()
        self.event_count = count
        new_strategy = self.get_strategy()

        if old_strategy != new_strategy:
            logger.info(
                f"Strategy switch: {old_strategy} -> {new_strategy} "
                f"at {count} events"
            )
```

**Feature Flag** (disabled by default until M4 stabilization):

```python
# k0/config/feature_flags.py
P03_FF_MINHASH_LSH = False  # Enable MinHash LSH for >50K events
```

**Configuration**:

| Config Key | Default | Purpose |
| ---------- | ------- | ------- |
| `P03_FF_MINHASH_LSH` | FALSE | Feature flag (disabled until tested) |
| `P03_MINHASH_NUM_HASHES` | 128 | Total hash functions |
| `P03_MINHASH_NUM_BANDS` | 32 | LSH bands |
| `P03_LSH_SIMILARITY_THRESHOLD` | 0.85 | Jaccard similarity threshold |
| `P03_LSH_PAIRWISE_THRESHOLD` | 10000 | Switch to bucketing |
| `P03_LSH_BUCKETING_THRESHOLD` | 50000 | Switch to MinHash LSH |

**Metrics**:

| Metric Name | Type | Description |
| ----------- | ---- | ----------- |
| `p03_dedup_strategy_active` | Gauge | Current strategy (0=pairwise, 1=bucketing, 2=lsh) |
| `p03_lsh_index_size` | Gauge | Number of events in LSH index |
| `p03_lsh_candidates_found` | Histogram | Candidates per query |
| `p03_lsh_latency_ms` | Histogram | LSH lookup latency |
| `p03_strategy_switch_count` | Counter | Strategy switches by type |

**Deliverables**:

- [ ] `MinHashConfig` dataclass in `k0/modules/consolidation/algorithms/minhash_lsh.py`
- [ ] `LSHCandidate` dataclass for candidate results
- [ ] `MinHashLSH` class with 128-hash, 32-band configuration
- [ ] `compute_minhash(text)` generating 128 hash values
- [ ] `hash_bands(signature)` partitioning into 32 bands
- [ ] `index_event(event_id, signature)` adding to LSH index
- [ ] `find_candidates(signature)` O(log n) candidate retrieval
- [ ] `compute_exact_similarity(sig1, sig2)` for verification
- [ ] `remove_event(event_id)` for cleanup on archive/tombstone
- [ ] `AdaptiveDeduplicationStrategy` with auto-switch logic
- [ ] Feature flag `P03_FF_MINHASH_LSH = FALSE`

**Acceptance Criteria**:

- [ ] MinHash computes 128 hash values per event
- [ ] LSH index partitions into 32 bands with 4 rows each
- [ ] find_candidates returns in O(log n) time
- [ ] Auto-switch at 10K (bucketing) and 50K (LSH) thresholds
- [ ] Feature flag disables LSH when FALSE
- [ ] Strategy switch logged when threshold crossed
- [ ] Exact similarity verification after LSH retrieval

**Test File**: `tests/k0/pipelines/p03/test_r3_minhash_lsh.py`

**Test Cases**:

1. `test_minhash_128_hashes` — Signature has 128 values
2. `test_hash_bands_32_bands` — Returns 32 band hashes
3. `test_index_and_find_self` — Indexed event found by same signature
4. `test_similar_texts_found` — Near-duplicates appear as candidates
5. `test_dissimilar_texts_not_found` — Unrelated texts not matched
6. `test_exact_similarity_computation` — Jaccard accurate to 0.01
7. `test_remove_event_from_index` — Removed event not found
8. `test_auto_switch_pairwise_to_bucketing` — Switch at 10K
9. `test_auto_switch_bucketing_to_lsh` — Switch at 50K
10. `test_feature_flag_disables_lsh` — LSH not used when flag FALSE

**Blocked By**: 4.3.1, 4.3.2

**Blocks**: 4.3.12

---

#### Issue 4.3.12 — Unit + integration tests for R3 Duplicate detection + Decay

**Status**: NOT_STARTED

**Spec Reference**:

- All R3 Issues: 4.3.1-4.3.11 (this issue tests the complete R3 phase)
- [Dossier §2.3](../pipelines/P03_consolidation_dossier_v2.md#23-r3-maintenance) — R3 Phase Requirements
- [tests.instructions.md](../../.github/instructions/tests.instructions.md) — Test standards

**Goal**: Comprehensive unit and integration tests validating R3 (Duplicate detection + Decay) phase.

**Test Organization**:

```
tests/k0/pipelines/p03/
├── test_r3_simhash.py          # Issue 4.3.1 - SimHasher
├── test_r3_two_stage_dedup.py  # Issue 4.3.2 - TwoStageDeduplicator
├── test_r3_decay.py            # Issue 4.3.3 - UnifiedDecayFormula
├── test_r3_resurrection.py     # Issue 4.3.4 - ResurrectionManager
├── test_r3_access_tracker.py   # Issue 4.3.5 - AccessTracker
├── test_r3_prune_regret.py     # Issue 4.3.6 - PruneRegretDetector
├── test_r3_duplicate_detector.py # Issue 4.3.7 - DuplicateDetector
├── test_r3_novelty_learner.py  # Issue 4.3.8 - AdaptiveNoveltyBonusLearner
├── test_r3_immunity_checker.py # Issue 4.3.9 - ImmunityChecker
├── test_r3_prune_audit.py      # Issue 4.3.10 - PruneAuditLogger
├── test_r3_minhash_lsh.py      # Issue 4.3.11 - MinHashLSH
├── test_r3_integration.py      # Full R3 phase integration tests
└── conftest.py                 # Shared fixtures
```

**Shared Fixtures** (conftest.py):

```python
# tests/k0/pipelines/p03/conftest.py

import pytest
import numpy as np
from unittest.mock import AsyncMock


@pytest.fixture
def sample_event_text():
    """Sample event text for deduplication tests."""
    return "Had dinner with Sarah at the Italian restaurant downtown"


@pytest.fixture
def similar_event_text():
    """Similar text for near-duplicate detection."""
    return "Dinner with Sarah at Italian place in downtown"


@pytest.fixture
def dissimilar_event_text():
    """Unrelated text for negative tests."""
    return "Attended board meeting to discuss Q3 financials"


@pytest.fixture
def sample_embedding():
    """768-dim embedding for semantic tests."""
    np.random.seed(42)
    return np.random.randn(768).astype(np.float32)


@pytest.fixture
def mock_db_conn():
    """Mock database connection for unit tests."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()
    return conn


@pytest.fixture
def decay_config():
    """Default decay configuration."""
    from k0.modules.consolidation.algorithms.decay_formula import DecayConfig
    return DecayConfig(
        base_lambda=0.001,
        archive_threshold=0.10,
        tombstone_threshold=0.01,
    )


@pytest.fixture
def family_member_entity():
    """FAMILY_MEMBER entity for immunity tests."""
    return {
        "entity_type": "FAMILY_MEMBER",
        "attributes": {
            "name": "Sarah",
            "relationship_to_user": "wife",
            "birthday": "1990-05-15",
        }
    }


@pytest.fixture
def person_entity_with_birthday():
    """PERSON entity with protected attribute."""
    return {
        "entity_type": "PERSON",
        "attributes": {
            "name": "John Smith",
            "birthday": "1985-03-20",
            "occupation": "Engineer",
        }
    }


@pytest.fixture
def person_entity_no_protected():
    """PERSON entity without protected attributes."""
    return {
        "entity_type": "PERSON",
        "attributes": {
            "name": "Random Person",
            "occupation": "Unknown",
        }
    }
```

**Unit Test Categories**:

| Category | Test File | Tests Count |
| -------- | --------- | ----------- |
| SimHash | test_r3_simhash.py | 8 |
| TwoStageDedup | test_r3_two_stage_dedup.py | 10 |
| DecayFormula | test_r3_decay.py | 12 |
| Resurrection | test_r3_resurrection.py | 8 |
| AccessTracker | test_r3_access_tracker.py | 8 |
| PruneRegret | test_r3_prune_regret.py | 8 |
| DuplicateDetector | test_r3_duplicate_detector.py | 10 |
| NoveltyLearner | test_r3_novelty_learner.py | 10 |
| ImmunityChecker | test_r3_immunity_checker.py | 10 |
| PruneAudit | test_r3_prune_audit.py | 10 |
| MinHashLSH | test_r3_minhash_lsh.py | 10 |
| **Integration** | test_r3_integration.py | **15** |
| **TOTAL** | | **119** |

**Integration Test Suite** (test_r3_integration.py):

```python
# tests/k0/pipelines/p03/test_r3_integration.py

"""
R3 Phase Integration Tests

Validates the complete R3 (Duplicate Detection + Decay) phase.
Uses real components with test database fixtures.

Related ADRs:
- ADR-K005: Hippocampus Module Design
- ADR-K003: DG Pattern Separation

Dossier Reference: Section 2.3 R3 Maintenance
"""

import pytest
import asyncio
from datetime import datetime, timedelta

# Mark all tests in this module as integration tests
pytestmark = pytest.mark.integration


class TestR3PhaseIntegration:
    """Integration tests for complete R3 phase."""

    @pytest.mark.asyncio
    async def test_full_r3_phase_processes_batch(
        self,
        r3_phase_processor,
        sample_events,
        test_db,
    ):
        """
        Full R3 phase processes event batch correctly.

        Steps:
        1. Insert 100 test events
        2. Run R3 phase
        3. Verify: duplicates marked, decay applied, novelty scored
        """
        # Insert events
        for event in sample_events[:100]:
            await test_db.insert_event(event)

        # Run R3 phase
        result = await r3_phase_processor.process_batch(
            space_id="test-space",
            batch_size=100,
        )

        # Verify
        assert result.events_processed == 100
        assert result.duplicates_found >= 0
        assert result.decay_applied >= 0
        assert result.novelty_scored == 100

    @pytest.mark.asyncio
    async def test_exact_duplicate_marked_correctly(
        self,
        r3_phase_processor,
        test_db,
    ):
        """
        Exact duplicate text marked with is_duplicate=TRUE.
        """
        text = "Went to the grocery store at 3pm"

        # Insert original
        event1_id = await test_db.insert_event({"text": text})
        await r3_phase_processor.process_event(event1_id)

        # Insert duplicate
        event2_id = await test_db.insert_event({"text": text})
        await r3_phase_processor.process_event(event2_id)

        # Verify duplicate marked
        event2 = await test_db.get_event(event2_id)
        assert event2["is_duplicate"] is True
        assert event2["duplicate_of_id"] == event1_id

    @pytest.mark.asyncio
    async def test_semantic_duplicate_caught_by_stage2(
        self,
        r3_phase_processor,
        test_db,
    ):
        """
        Semantic duplicate (different words, same meaning) caught.
        """
        text1 = "Had dinner with Sarah at the Italian restaurant"
        text2 = "Ate at Italian place with Sarah for dinner"  # Same meaning

        event1_id = await test_db.insert_event({"text": text1})
        await r3_phase_processor.process_event(event1_id)

        event2_id = await test_db.insert_event({"text": text2})
        await r3_phase_processor.process_event(event2_id)

        event2 = await test_db.get_event(event2_id)
        # Should be in near_duplicates if not exact match
        assert event2["near_duplicates_json"] is not None or event2["is_duplicate"]

    @pytest.mark.asyncio
    async def test_decay_factor_decreases_over_time(
        self,
        r3_phase_processor,
        test_db,
    ):
        """
        Decay factor decreases for events not accessed.
        """
        event_id = await test_db.insert_event({
            "text": "Old memory from a year ago",
            "created_at": (datetime.now() - timedelta(days=365)).timestamp() * 1000,
            "last_accessed_at": (datetime.now() - timedelta(days=180)).timestamp() * 1000,
        })

        await r3_phase_processor.apply_decay(event_id)

        event = await test_db.get_event(event_id)
        # After 180 days without access, decay should be significant
        assert event["decay_factor"] < 0.50

    @pytest.mark.asyncio
    async def test_archive_at_threshold(
        self,
        r3_phase_processor,
        test_db,
    ):
        """
        Event archived when decay_factor < 0.10.
        """
        event_id = await test_db.insert_event({
            "text": "Very old memory",
            "decay_factor": 0.08,  # Below archive threshold
        })

        await r3_phase_processor.apply_prune_decision(event_id)

        event = await test_db.get_event(event_id)
        assert event["archival_status"] == "ARCHIVED"

    @pytest.mark.asyncio
    async def test_tombstone_at_threshold(
        self,
        r3_phase_processor,
        test_db,
    ):
        """
        Event tombstoned when decay_factor < 0.01.
        """
        event_id = await test_db.insert_event({
            "text": "Forgotten memory",
            "decay_factor": 0.005,  # Below tombstone threshold
        })

        await r3_phase_processor.apply_prune_decision(event_id)

        event = await test_db.get_event(event_id)
        assert event["archival_status"] == "TOMBSTONE"

    @pytest.mark.asyncio
    async def test_resurrection_restores_decay(
        self,
        r3_phase_processor,
        test_db,
    ):
        """
        Resurrection restores decay_factor to ≥0.70.
        """
        event_id = await test_db.insert_event({
            "text": "Archived memory being resurrected",
            "decay_factor": 0.05,
            "archival_status": "ARCHIVED",
        })

        await r3_phase_processor.resurrect(event_id, reason="P04_QUERY_MATCH")

        event = await test_db.get_event(event_id)
        assert event["decay_factor"] >= 0.70
        assert event["archival_status"] == "ACTIVE"

    @pytest.mark.asyncio
    async def test_immune_entity_skips_decay(
        self,
        r3_phase_processor,
        test_db,
    ):
        """
        Entities with decay_immune=TRUE skip decay entirely.
        """
        event_id = await test_db.insert_event({
            "text": "Family member's birthday",
            "decay_factor": 0.90,
            "decay_immune": True,
            "entity_type": "FAMILY_MEMBER",
        })

        original_decay = 0.90
        await r3_phase_processor.apply_decay(event_id)

        event = await test_db.get_event(event_id)
        assert event["decay_factor"] == original_decay  # Unchanged

    @pytest.mark.asyncio
    async def test_prune_regret_detection(
        self,
        r3_phase_processor,
        test_db,
    ):
        """
        Pruned entity matched by query triggers regret signal.
        """
        # Archive an event
        event_id = await test_db.insert_event({
            "text": "Meeting with Bob about project",
            "decay_factor": 0.05,
        })
        await r3_phase_processor.apply_prune_decision(event_id)

        # Query for related content
        query_text = "What did I discuss with Bob?"
        regret = await r3_phase_processor.check_prune_regret(query_text)

        assert regret is not None
        assert regret.matched_entity_id == event_id

    @pytest.mark.asyncio
    async def test_novelty_bonus_first_occurrence(
        self,
        r3_phase_processor,
        test_db,
    ):
        """
        First occurrence of activity gets +0.15 novelty bonus.
        """
        event_id = await test_db.insert_event({
            "text": "First time skydiving!",
            "activity_type": "skydiving",
        })

        await r3_phase_processor.compute_novelty(event_id)

        event = await test_db.get_event(event_id)
        # First occurrence bonus applied
        assert event["novelty_factor"] >= 0.80  # Base + 0.15 bonus

    @pytest.mark.asyncio
    async def test_novelty_penalty_routine_activity(
        self,
        r3_phase_processor,
        test_db,
    ):
        """
        Routine activity gets -0.30 novelty penalty.
        """
        # Create pattern of routine activity
        for i in range(30):
            await test_db.insert_event({
                "text": f"Morning coffee at 8am (day {i})",
                "activity_type": "morning_coffee",
            })

        # Add another routine event
        event_id = await test_db.insert_event({
            "text": "Morning coffee at 8am (day 31)",
            "activity_type": "morning_coffee",
        })

        await r3_phase_processor.compute_novelty(event_id)

        event = await test_db.get_event(event_id)
        # Routine penalty applied
        assert event["novelty_factor"] <= 0.40

    @pytest.mark.asyncio
    async def test_access_tracking_updates(
        self,
        r3_phase_processor,
        test_db,
    ):
        """
        Access tracking increments count and updates timestamp.
        """
        event_id = await test_db.insert_event({
            "text": "Important memory",
            "access_count": 5,
        })

        await r3_phase_processor.record_access(event_id, "P04_QUERY")

        event = await test_db.get_event(event_id)
        assert event["access_count"] == 6
        assert event["last_accessed_at"] > 0

    @pytest.mark.asyncio
    async def test_audit_log_created_for_prune(
        self,
        r3_phase_processor,
        test_db,
    ):
        """
        Prune decision creates audit log entry.
        """
        event_id = await test_db.insert_event({
            "text": "Old memory to prune",
            "decay_factor": 0.05,
        })

        await r3_phase_processor.apply_prune_decision(event_id)

        audits = await test_db.get_audits_for_memory(event_id)
        assert len(audits) >= 1
        assert audits[0]["action"] in ("ARCHIVE", "TOMBSTONE")

    @pytest.mark.asyncio
    async def test_minhash_lsh_scales_with_event_count(
        self,
        r3_phase_processor,
        test_db,
    ):
        """
        MinHash LSH activates for >50K events.
        """
        # Mock event count
        r3_phase_processor.set_event_count(60_000)

        strategy = r3_phase_processor.get_dedup_strategy()
        assert strategy == "minhash_lsh"

    @pytest.mark.asyncio
    async def test_full_r3_cycle_metrics(
        self,
        r3_phase_processor,
        test_db,
        metrics_collector,
    ):
        """
        Full R3 cycle emits correct metrics.
        """
        # Insert events
        for i in range(10):
            await test_db.insert_event({"text": f"Event {i}"})

        # Run R3
        await r3_phase_processor.run_cycle(space_id="test-space")

        # Check metrics
        assert metrics_collector.get("p03_r3_events_processed") == 10
        assert metrics_collector.get("p03_r3_cycle_duration_ms") > 0
```

**Test Coverage Targets**:

| Component | Target Coverage | Critical Paths |
| --------- | --------------- | -------------- |
| SimHasher | ≥90% | compute_simhash, hamming_distance |
| TwoStageDeduplicator | ≥90% | stage1_simhash, stage2_semantic |
| UnifiedDecayFormula | ≥95% | compute_decay_factor, apply_decay |
| ResurrectionManager | ≥90% | should_resurrect, resurrect |
| AccessTracker | ≥85% | record_access, update_lambda |
| PruneRegretDetector | ≥85% | detect_regret, emit_signal |
| DuplicateDetector | ≥90% | detect, calculate_novelty |
| NoveltyBonusLearner | ≥90% | adjust_bonus, process_feedback |
| ImmunityChecker | ≥95% | should_mark_immune |
| PruneAuditLogger | ≥85% | log_prune_decision |
| MinHashLSH | ≥85% | compute_minhash, find_candidates |
| **Integration** | ≥80% | Full R3 phase |

**Deliverables**:

- [ ] `tests/k0/pipelines/p03/conftest.py` with shared fixtures
- [ ] `test_r3_simhash.py` — 8 tests for SimHasher
- [ ] `test_r3_two_stage_dedup.py` — 10 tests for TwoStageDeduplicator
- [ ] `test_r3_decay.py` — 12 tests for UnifiedDecayFormula
- [ ] `test_r3_resurrection.py` — 8 tests for ResurrectionManager
- [ ] `test_r3_access_tracker.py` — 8 tests for AccessTracker
- [ ] `test_r3_prune_regret.py` — 8 tests for PruneRegretDetector
- [ ] `test_r3_duplicate_detector.py` — 10 tests for DuplicateDetector
- [ ] `test_r3_novelty_learner.py` — 10 tests for NoveltyBonusLearner
- [ ] `test_r3_immunity_checker.py` — 10 tests for ImmunityChecker
- [ ] `test_r3_prune_audit.py` — 10 tests for PruneAuditLogger
- [ ] `test_r3_minhash_lsh.py` — 10 tests for MinHashLSH
- [ ] `test_r3_integration.py` — 15 integration tests

**Acceptance Criteria**:

- [ ] All 119 tests pass
- [ ] Coverage ≥85% across all R3 components
- [ ] Integration tests validate complete R3 phase
- [ ] No flaky tests (deterministic execution)
- [ ] Test duration ≤30 seconds total
- [ ] All tests follow ward test conventions
- [ ] Fixtures are reusable and well-documented

**Performance Test Targets**:

| Test | Target | Metric |
| ---- | ------ | ------ |
| SimHash 1000 events | ≤50ms | P95 latency |
| TwoStage 100 duplicates | ≤200ms | P95 latency |
| Decay batch 1000 | ≤100ms | P95 latency |
| LSH lookup 50K index | ≤20ms | P95 latency |

**Blocked By**: 4.3.1-4.3.11 (all R3 implementation issues)

**Blocks**: None (this completes Epic 4.3)

---

### Epic 4.4 — R4 KG consolidation (entities/edges/causal + ambiguity gaps)

> **Scope**: Implement R4 Knowledge Graph Consolidation phase — entity resolution, disambiguation, merge cascades, causality.
> **Module**: M21 KGConsolidator
> **Dossier**: Section 4.5, Appendix C.5

---

#### Issue 4.4.1 — Integrate UltraBERT NER entity extraction from P02

**Status**: NOT_STARTED

**Spec Reference**:

- [Dossier §4.5.1](../pipelines/P03_consolidation_dossier_v2.md#451-entity-extraction--normalization) (lines 4018-4022) — Entity Extraction & Normalization
- [UltraBERT Release Notes](../../wheels/Release_notes.md) — Actual model output format
- [st_hipp_events.entities_json](../../k0/db/alembic/versions/0022_st_hipp_events.py#L141) — Entity storage column (EXISTS)
- [P02 NER outputs](../../k0/pipelines/p02/README.md) — Source of NER data

**Goal**: Process P02 UltraBERT NER outputs (3 heads) for KG population with label mapping.

**Problem Statement**:

> UltraBERT provides 3 separate NER heads, each with different entity types:
>
> - `ner_family`: KINSHIP, FAMILY_EVENT labels (family-specific)
> - `ner_general`: PERSON, LOCATION, ORGANIZATION, etc. (general NER)
> - `temporal`: DATE_REL, TIME labels (temporal expressions)
>
> These must be merged, normalized, and mapped to KG entity types.

**Existing Infrastructure**:

| Component | Location | Status |
| --------- | -------- | ------ |
| `entities_json` column | st_hipp_events line 141 | EXISTS |
| `kg_triples_json` column | st_hipp_events line 142 | EXISTS |
| UltraBERT 12-head model | P02 pipeline | EXISTS |
| 3 NER heads | ner_family, ner_general, temporal | Verified |

**ACTUAL UltraBERT Output Format** (from Release Notes / live test):

```python
# UltraBERT provides 3 separate NER heads:

# --- ner_family head ---
{
    "entities": [
        {"text": "child", "label": "KINSHIP", "start_token": 6, "end_token": 6},
        {"text": "wife", "label": "KINSHIP", "start_token": 27, "end_token": 27}
    ]
}

# --- ner_general head ---
{
    "entities": [
        {"text": "costco", "label": "ORG", "start_token": 7, "end_token": 7}
    ]
}

# --- temporal head ---
{
    "entities": [
        {"text": "sunday", "label": "DATE_REL", "start_token": 11, "end_token": 12},
        {"text": "8", "label": "TIME", "start_token": 14, "end_token": 14}
    ]
}

# Note: NO per-entity confidence scores - confidence is at head level
# Note: Uses start_token/end_token, not character positions
```

**UltraBERT Label → KG Entity Type Mapping**:

| UltraBERT Label | Source Head | KG Entity Type | Priority |
| --------------- | ----------- | -------------- | -------- |
| `KINSHIP` | ner_family | `FAMILY_MEMBER` | High (0.95) |
| `FAMILY_EVENT` | ner_family | `EVENT` | High (0.90) |
| `PERSON` | ner_general | `PERSON` | Medium (0.85) |
| `ORG` | ner_general | `ORGANIZATION` | Medium (0.80) |
| `LOC` | ner_general | `LOCATION` | Medium (0.80) |
| `GPE` | ner_general | `LOCATION` | Medium (0.80) |
| `FAC` | ner_general | `LOCATION` | Medium (0.75) |
| `PRODUCT` | ner_general | `OBJECT` | Low (0.70) |
| `EVENT` | ner_general | `EVENT` | Medium (0.75) |
| `DATE_REL` | temporal | `TEMPORAL` | High (0.90) |
| `TIME` | temporal | `TEMPORAL` | High (0.90) |
| `DURATION` | temporal | `TEMPORAL` | High (0.85) |

**Implementation**:

```python
# File: k0/modules/consolidation/algorithms/entity_extractor.py

from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum


class KGEntityType(Enum):
    """Canonical KG entity types (target types for KG population)."""
    FAMILY_MEMBER = "FAMILY_MEMBER"
    PERSON = "PERSON"
    LOCATION = "LOCATION"
    ORGANIZATION = "ORGANIZATION"
    EVENT = "EVENT"
    OBJECT = "OBJECT"
    TEMPORAL = "TEMPORAL"
    CONCEPT = "CONCEPT"


@dataclass
class UltraBERTEntity:
    """Raw entity from UltraBERT NER head."""
    text: str
    label: str
    start_token: int
    end_token: int
    source_head: str  # 'ner_family', 'ner_general', or 'temporal'


@dataclass
class ExtractedEntity:
    """Normalized entity for KG population."""
    text: str
    kg_type: KGEntityType
    normalized_text: str
    source_label: str      # Original UltraBERT label
    source_head: str       # Which head it came from
    priority: float        # Derived from label mapping
    start_token: int
    end_token: int


class UltraBERTEntityExtractor:
    """
    Process UltraBERT NER outputs (3 heads) for KG population.

    Spec: Dossier §4.5.1, UltraBERT Release Notes

    Features:
    - Merges 3 NER heads: ner_family, ner_general, temporal
    - Maps UltraBERT labels to KG entity types
    - Canonical name normalization
    - Entity deduplication with priority-based selection
    """

    # UltraBERT label → (KG type, priority)
    LABEL_MAPPING: Dict[str, tuple] = {
        # ner_family labels (highest priority for family context)
        "KINSHIP": (KGEntityType.FAMILY_MEMBER, 0.95),
        "FAMILY_EVENT": (KGEntityType.EVENT, 0.90),

        # ner_general labels
        "PERSON": (KGEntityType.PERSON, 0.85),
        "PER": (KGEntityType.PERSON, 0.85),  # Alternate label
        "ORG": (KGEntityType.ORGANIZATION, 0.80),
        "ORGANIZATION": (KGEntityType.ORGANIZATION, 0.80),
        "LOC": (KGEntityType.LOCATION, 0.80),
        "LOCATION": (KGEntityType.LOCATION, 0.80),
        "GPE": (KGEntityType.LOCATION, 0.80),  # Geo-political entity
        "FAC": (KGEntityType.LOCATION, 0.75),  # Facility
        "PRODUCT": (KGEntityType.OBJECT, 0.70),
        "EVENT": (KGEntityType.EVENT, 0.75),
        "WORK_OF_ART": (KGEntityType.CONCEPT, 0.65),
        "NORP": (KGEntityType.CONCEPT, 0.65),  # Nationality/religious/political

        # temporal labels
        "DATE_REL": (KGEntityType.TEMPORAL, 0.90),
        "DATE": (KGEntityType.TEMPORAL, 0.90),
        "TIME": (KGEntityType.TEMPORAL, 0.90),
        "DURATION": (KGEntityType.TEMPORAL, 0.85),
    }

    def extract_from_ultrabert(
        self,
        ner_family_output: Dict,
        ner_general_output: Dict,
        temporal_output: Dict,
    ) -> List[ExtractedEntity]:
        """
        Extract and merge entities from all 3 UltraBERT NER heads.

        Args:
            ner_family_output: Output from ner_family head
            ner_general_output: Output from ner_general head
            temporal_output: Output from temporal head

        Returns: Merged, deduplicated list of KG entities
        """
        all_entities = []

        # Process each head
        for entity in ner_family_output.get("entities", []):
            mapped = self._map_entity(entity, "ner_family")
            if mapped:
                all_entities.append(mapped)

        for entity in ner_general_output.get("entities", []):
            mapped = self._map_entity(entity, "ner_general")
            if mapped:
                all_entities.append(mapped)

        for entity in temporal_output.get("entities", []):
            mapped = self._map_entity(entity, "temporal")
            if mapped:
                all_entities.append(mapped)

        # Deduplicate, keeping highest priority
        entities = self._deduplicate_entities(all_entities)

        return entities

    def _map_entity(
        self,
        raw: Dict,
        source_head: str,
    ) -> Optional[ExtractedEntity]:
        """
        Map UltraBERT entity to KG entity type.

        Returns None if label not recognized.
        """
        label = raw.get("label", "")
        text = raw.get("text", "")

        if not label or not text:
            return None

        # Look up mapping
        mapping = self.LABEL_MAPPING.get(label)
        if not mapping:
            # Unknown label, default to CONCEPT with low priority
            mapping = (KGEntityType.CONCEPT, 0.50)
            self.metrics.p03_ner_unknown_label.labels(label=label).inc()

        kg_type, priority = mapping

        return ExtractedEntity(
            text=text,
            kg_type=kg_type,
            normalized_text=self.normalize_name(text),
            source_label=label,
            source_head=source_head,
            priority=priority,
            start_token=raw.get("start_token", 0),
            end_token=raw.get("end_token", 0),
        )

    def normalize_name(self, name: str) -> str:
        """
        Normalize entity name for matching.

        Steps:
        1. Lowercase
        2. Strip whitespace
        3. Remove punctuation
        4. Collapse multiple spaces
        5. Handle common nicknames (wifey → wife)
        """
        import re

        # Nickname normalization (family context)
        nickname_map = {
            "wifey": "wife",
            "hubby": "husband",
            "kiddo": "child",
            "kiddos": "children",
            "grandma": "grandmother",
            "grandpa": "grandfather",
            "mom": "mother",
            "dad": "father",
            "sis": "sister",
            "bro": "brother",
        }

        normalized = name.lower().strip()
        normalized = re.sub(r'[^\w\s]', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)

        # Apply nickname normalization
        if normalized in nickname_map:
            normalized = nickname_map[normalized]

        return normalized

    def _deduplicate_entities(
        self,
        entities: List[ExtractedEntity],
    ) -> List[ExtractedEntity]:
        """
        Remove duplicate entities, keeping highest priority.

        Duplicates defined by same normalized_text + overlapping token positions.
        """
        seen: Dict[str, ExtractedEntity] = {}

        for entity in entities:
            key = f"{entity.kg_type.value}:{entity.normalized_text}"

            if key not in seen:
                seen[key] = entity
            elif entity.priority > seen[key].priority:
                # Keep higher priority (e.g., KINSHIP over PERSON)
                seen[key] = entity

        return list(seen.values())

    def to_entities_json(
        self,
        entities: List[ExtractedEntity],
    ) -> str:
        """
        Convert extracted entities to JSON for st_hipp_events.entities_json.
        """
        import json

        return json.dumps({
            "entities": [
                {
                    "text": e.text,
                    "kg_type": e.kg_type.value,
                    "normalized": e.normalized_text,
                    "source_label": e.source_label,
                    "source_head": e.source_head,
                    "priority": e.priority,
                }
                for e in entities
            ],
            "extraction_version": "2.0",  # Matches UltraBERT v2.x
            "extracted_at": now_ms(),
        })

    async def process_event(
        self,
        event_id: str,
        ultrabert_result: Dict,
        db_conn,
    ) -> int:
        """
        Process UltraBERT full result and store entities.

        Args:
            event_id: Event to update
            ultrabert_result: Full UltraBERT analyze() output with all heads
            db_conn: Database connection

        Returns: count of extracted entities
        """
        entities = self.extract_from_ultrabert(
            ner_family_output=ultrabert_result.get("ner_family", {"entities": []}),
            ner_general_output=ultrabert_result.get("ner_general", {"entities": []}),
            temporal_output=ultrabert_result.get("temporal", {"entities": []}),
        )

        entities_json = self.to_entities_json(entities)

        await db_conn.execute(
            """
            UPDATE st_hipp_events
            SET entities_json = $1,
                updated_at = $2
            WHERE event_id = $3
            """,
            entities_json,
            now_ms(),
            event_id,
        )

        # Track by source head
        for entity in entities:
            self.metrics.p03_ner_entities_extracted.labels(
                source_head=entity.source_head,
                kg_type=entity.kg_type.value
            ).inc()

        return len(entities)
```

**Configuration**:

| Config Key | Default | Purpose |
| ---------- | ------- | ------- |
| `P03_NER_PRIORITY_KINSHIP` | 0.95 | Priority for KINSHIP entities |
| `P03_NER_PRIORITY_PERSON` | 0.85 | Priority for PERSON entities |
| `P03_NER_PRIORITY_TEMPORAL` | 0.90 | Priority for temporal entities |
| `P03_NER_PRIORITY_DEFAULT` | 0.50 | Default for unknown labels |

**Metrics**:

| Metric Name | Type | Description |
| ----------- | ---- | ----------- |
| `p03_ner_entities_extracted` | Counter | Entities by source_head and kg_type |
| `p03_ner_unknown_label` | Counter | UltraBERT labels not in mapping |
| `p03_ner_extraction_latency_ms` | Histogram | Time to process all 3 heads |
| `p03_ner_entities_per_event` | Histogram | Entity count distribution |

**Deliverables**:

- [ ] `KGEntityType` enum in `entity_extractor.py`
- [ ] `UltraBERTEntity` dataclass for raw entities
- [ ] `ExtractedEntity` dataclass with kg_type and priority
- [ ] `UltraBERTEntityExtractor` class with 3-head processing
- [ ] `LABEL_MAPPING` dict: UltraBERT label → (KGEntityType, priority)
- [ ] `extract_from_ultrabert(ner_family, ner_general, temporal)` merging 3 heads
- [ ] `_map_entity()` with label mapping
- [ ] `normalize_name()` with nickname normalization (wifey→wife)
- [ ] `_deduplicate_entities()` keeping highest priority
- [ ] `to_entities_json()` for st_hipp_events storage
- [ ] `process_event()` integrating with database

**Acceptance Criteria**:

- [ ] All 3 NER heads processed: ner_family, ner_general, temporal
- [ ] KINSHIP labels mapped to FAMILY_MEMBER with priority 0.95
- [ ] PERSON labels mapped to PERSON with priority 0.85
- [ ] DATE_REL/TIME labels mapped to TEMPORAL with priority 0.90
- [ ] Nickname normalization: "wifey" → "wife", "kiddo" → "child"
- [ ] Duplicate entities deduplicated, keeping highest priority
- [ ] entities_json stored in st_hipp_events
- [ ] Metrics track by source_head and kg_type

**Test File**: `tests/k0/pipelines/p03/test_r4_entity_extractor.py`

**Test Cases**:

1. `test_ner_family_kinship_mapping` — KINSHIP → FAMILY_MEMBER, priority 0.95
2. `test_ner_general_person_mapping` — PERSON → PERSON, priority 0.85
3. `test_temporal_date_rel_mapping` — DATE_REL → TEMPORAL, priority 0.90
4. `test_merge_three_heads` — Entities from all 3 heads combined
5. `test_normalize_wifey_to_wife` — "wifey" → "wife"
6. `test_normalize_kiddo_to_child` — "kiddo" → "child"
7. `test_deduplicate_keeps_highest_priority` — KINSHIP beats PERSON for same text
8. `test_unknown_label_defaults_concept` — Unknown label → CONCEPT, priority 0.50
9. `test_to_entities_json_format` — Valid JSON with all fields
10. `test_process_event_updates_db` — st_hipp_events.entities_json updated
11. `test_empty_heads_handled` — No crash on empty entity lists
12. `test_metrics_by_source_head` — Metrics labeled by head

**Blocked By**: None (first R4 issue)

**Blocks**: 4.4.2, 4.4.3, 4.4.5

---

#### Issue 4.4.2 — Implement per-entity-type disambiguation weights

**Status**: NOT_STARTED

**Spec Reference**:

- [Dossier §4.5.1.1](../pipelines/P03_consolidation_dossier_v2.md#4511-per-entity-type-disambiguation) (lines 4061-4150) — Per-Entity-Type Disambiguation
- [st_learned_weights.param_scope](../../k0/db/alembic/versions/0040_st_learned_weights.py) — Weight storage (EXISTS)
- [Jaro-Winkler](https://en.wikipedia.org/wiki/Jaro–Winkler_distance) — String similarity algorithm

**Goal**: Apply different embedding/string weight ratios by entity type for disambiguation.

**Problem Statement**:

> Entity disambiguation requires balancing semantic similarity (embeddings) with string similarity:
>
> - PERSON names: "John Smith" vs "Jon Smith" — string similarity critical (typos common)
> - CONCEPT: "happiness" vs "joy" — embedding similarity critical (synonyms)
> - FAMILY_MEMBER: Must prioritize string matching (names within family are fixed)

**Per-Type Weight Matrix** (from Dossier §4.5.1.1):

| Entity Type | Embedding Weight | String Weight | Rationale |
| ----------- | ---------------- | ------------- | --------- |
| `PERSON` | 0.50 | 0.50 | Balance between similar names vs similar roles |
| `FAMILY_MEMBER` | 0.30 | 0.70 | Names within family are fixed, typos common |
| `PLACE` | 0.60 | 0.40 | Locations can have synonyms ("NYC"/"New York") |
| `ORGANIZATION` | 0.55 | 0.45 | Company names have abbreviations |
| `THING` | 0.80 | 0.20 | Objects have synonyms ("couch"/"sofa") |
| `CONCEPT` | 0.85 | 0.15 | Abstract concepts need semantic matching |
| `EVENT` | 0.70 | 0.30 | Activities can be described differently |
| `FOOD` | 0.65 | 0.35 | Food items vary ("pasta"/"spaghetti") |
| `ACTIVITY` | 0.70 | 0.30 | Similar to EVENT |

**Implementation**:

```python
# File: k0/modules/consolidation/algorithms/entity_disambiguator.py

from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from rapidfuzz import fuzz  # For string similarity


@dataclass
class DisambiguationWeights:
    """Weights for entity disambiguation."""
    embedding_weight: float
    string_weight: float

    def __post_init__(self):
        # Validate weights sum to 1.0
        total = self.embedding_weight + self.string_weight
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Weights must sum to 1.0, got {total}")


class EntityDisambiguator:
    """
    Disambiguate entities using per-type weighted similarity.

    Spec: Dossier §4.5.1.1

    Features:
    - Per-entity-type weight matrix
    - Combined embedding + string similarity
    - Best-of-three string matching algorithms
    """

    # Default weights from Dossier §4.5.1.1
    DEFAULT_WEIGHTS: Dict[str, DisambiguationWeights] = {
        "PERSON": DisambiguationWeights(0.50, 0.50),
        "FAMILY_MEMBER": DisambiguationWeights(0.30, 0.70),
        "PLACE": DisambiguationWeights(0.60, 0.40),
        "LOCATION": DisambiguationWeights(0.60, 0.40),  # Alias for PLACE
        "ORGANIZATION": DisambiguationWeights(0.55, 0.45),
        "THING": DisambiguationWeights(0.80, 0.20),
        "OBJECT": DisambiguationWeights(0.80, 0.20),  # Alias for THING
        "CONCEPT": DisambiguationWeights(0.85, 0.15),
        "EVENT": DisambiguationWeights(0.70, 0.30),
        "FOOD": DisambiguationWeights(0.65, 0.35),
        "ACTIVITY": DisambiguationWeights(0.70, 0.30),
    }

    def __init__(
        self,
        learned_weights: Optional[Dict[str, DisambiguationWeights]] = None,
    ):
        """
        Initialize with optional learned weights.

        Args:
            learned_weights: Override default weights from st_learned_weights
        """
        self.weights = {**self.DEFAULT_WEIGHTS}
        if learned_weights:
            self.weights.update(learned_weights)

    def compute_similarity(
        self,
        entity1_embedding: list,
        entity1_name: str,
        entity2_embedding: list,
        entity2_name: str,
        entity_type: str,
    ) -> Tuple[float, Dict[str, float]]:
        """
        Compute weighted similarity between two entities.

        Returns:
            (combined_score, breakdown_dict)
        """
        # Get weights for this entity type
        weights = self.weights.get(
            entity_type,
            DisambiguationWeights(0.50, 0.50)  # Default 50/50
        )

        # Compute embedding similarity (cosine)
        embedding_sim = self._cosine_similarity(
            entity1_embedding,
            entity2_embedding
        )

        # Compute string similarity (best of three)
        string_sim = self.fuzzy_string_match(
            entity1_name,
            entity2_name
        )

        # Compute weighted combination
        combined = (
            weights.embedding_weight * embedding_sim +
            weights.string_weight * string_sim
        )

        breakdown = {
            "embedding_similarity": embedding_sim,
            "string_similarity": string_sim,
            "embedding_weight": weights.embedding_weight,
            "string_weight": weights.string_weight,
            "combined_score": combined,
            "entity_type": entity_type,
        }

        return combined, breakdown

    def fuzzy_string_match(
        self,
        name1: str,
        name2: str,
    ) -> float:
        """
        Compute string similarity using best of three algorithms.

        Algorithms:
        1. Levenshtein ratio
        2. Jaro-Winkler
        3. Token sort ratio (handles word order)

        Returns: max(levenshtein, jaro_winkler, token_sort) / 100
        """
        # Normalize names
        n1 = name1.lower().strip()
        n2 = name2.lower().strip()

        if n1 == n2:
            return 1.0

        # Levenshtein ratio (0-100)
        levenshtein = fuzz.ratio(n1, n2)

        # Token sort ratio handles word order ("John Smith" vs "Smith, John")
        token_sort = fuzz.token_sort_ratio(n1, n2)

        # Partial ratio for substring matching
        partial = fuzz.partial_ratio(n1, n2)

        # Take best of three, normalize to 0-1
        best = max(levenshtein, token_sort, partial)
        return best / 100.0

    def _cosine_similarity(
        self,
        vec1: list,
        vec2: list,
    ) -> float:
        """
        Compute cosine similarity between two vectors.

        Returns: float in [-1, 1], clamped to [0, 1]
        """
        import numpy as np

        v1 = np.array(vec1)
        v2 = np.array(vec2)

        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        cos_sim = np.dot(v1, v2) / (norm1 * norm2)

        # Clamp to [0, 1] for scoring purposes
        return max(0.0, min(1.0, cos_sim))

    def should_merge(
        self,
        entity1_embedding: list,
        entity1_name: str,
        entity2_embedding: list,
        entity2_name: str,
        entity_type: str,
        threshold: float = 0.85,
    ) -> Tuple[bool, float, Dict]:
        """
        Determine if two entities should be merged.

        Returns:
            (should_merge, score, breakdown)
        """
        score, breakdown = self.compute_similarity(
            entity1_embedding, entity1_name,
            entity2_embedding, entity2_name,
            entity_type
        )

        return score >= threshold, score, breakdown

    @classmethod
    async def load_from_database(
        cls,
        db_conn,
    ) -> "EntityDisambiguator":
        """
        Load learned weights from st_learned_weights.

        Uses param_scope='entity_type' for weight lookup.
        """
        rows = await db_conn.fetch(
            """
            SELECT param_scope, param_key, param_value
            FROM st_learned_weights
            WHERE param_category = 'disambiguation'
            AND active = TRUE
            """
        )

        learned = {}
        for row in rows:
            entity_type = row["param_scope"]  # e.g., "PERSON"
            param_key = row["param_key"]  # e.g., "embedding_weight"
            value = float(row["param_value"])

            if entity_type not in learned:
                learned[entity_type] = {}
            learned[entity_type][param_key] = value

        # Convert to DisambiguationWeights
        weights = {}
        for entity_type, params in learned.items():
            if "embedding_weight" in params and "string_weight" in params:
                weights[entity_type] = DisambiguationWeights(
                    params["embedding_weight"],
                    params["string_weight"]
                )

        return cls(learned_weights=weights)
```

**Configuration**:

| Config Key | Default | Purpose |
| ---------- | ------- | ------- |
| `P03_DISAMBIGUATION_THRESHOLD` | 0.85 | Merge threshold |
| `P03_DISAMBIGUATION_WEIGHT_MIN` | 0.15 | Minimum allowed weight |
| `P03_DISAMBIGUATION_WEIGHT_MAX` | 0.85 | Maximum allowed weight |

**Database Storage** (uses existing st_learned_weights):

```sql
-- Example learned weights in st_learned_weights
INSERT INTO st_learned_weights (
    param_category, param_scope, param_key, param_value, active
) VALUES
    ('disambiguation', 'PERSON', 'embedding_weight', '0.48', TRUE),
    ('disambiguation', 'PERSON', 'string_weight', '0.52', TRUE);
```

**Metrics**:

| Metric Name | Type | Description |
| ----------- | ---- | ----------- |
| `p03_disambiguation_score` | Histogram | Combined similarity scores |
| `p03_disambiguation_merges` | Counter | Merge decisions by entity type |
| `p03_string_similarity_algorithm` | Counter | Which algorithm won (levenshtein/token_sort/partial) |

**Deliverables**:

- [ ] `DisambiguationWeights` dataclass in `entity_disambiguator.py`
- [ ] `EntityDisambiguator` class with DEFAULT_WEIGHTS matrix
- [ ] `compute_similarity(entity1, entity2)` returning (score, breakdown)
- [ ] `fuzzy_string_match(name1, name2)` with best-of-three algorithms
- [ ] `_cosine_similarity(vec1, vec2)` for embedding comparison
- [ ] `should_merge()` returning merge decision with threshold
- [ ] `load_from_database()` loading weights from st_learned_weights
- [ ] Weight matrix: PERSON=0.50/0.50, FAMILY_MEMBER=0.30/0.70, CONCEPT=0.85/0.15

**Acceptance Criteria**:

- [ ] PERSON entities use 50% embedding, 50% string similarity
- [ ] FAMILY_MEMBER entities use 30% embedding, 70% string similarity
- [ ] CONCEPT entities use 85% embedding, 15% string similarity
- [ ] `fuzzy_string_match` returns best of Levenshtein, Token Sort, Partial
- [ ] Weights sum to 1.0 (validation in dataclass)
- [ ] Learned weights loaded from st_learned_weights override defaults
- [ ] Unknown entity types default to 50/50

**Test File**: `tests/k0/pipelines/p03/test_r4_disambiguator.py`

**Test Cases**:

1. `test_person_weights_balanced` — PERSON uses 0.50/0.50
2. `test_family_member_string_heavy` — FAMILY_MEMBER uses 0.30/0.70
3. `test_concept_embedding_heavy` — CONCEPT uses 0.85/0.15
4. `test_fuzzy_match_typo` — "John" vs "Jon" → high similarity
5. `test_fuzzy_match_reorder` — "John Smith" vs "Smith, John" → high similarity
6. `test_cosine_similarity_identical` — Same vector → 1.0
7. `test_cosine_similarity_orthogonal` — Orthogonal vectors → 0.0
8. `test_combined_score_weighted` — Verify weight application
9. `test_should_merge_above_threshold` — Score 0.90 → should_merge=True
10. `test_should_merge_below_threshold` — Score 0.70 → should_merge=False
11. `test_load_from_database` — Weights loaded from st_learned_weights
12. `test_unknown_type_default` — Unknown type uses 50/50

**Blocked By**: 4.4.1

**Blocks**: 4.4.3, 4.4.5

---

#### Issue 4.4.3 — Implement disambiguation weight learning from feedback

**Status**: NOT_STARTED

**Spec Reference**:

- [Dossier §4.5.1.1](../pipelines/P03_consolidation_dossier_v2.md#4511-per-entity-type-disambiguation) (lines 4140-4180) — DisambiguationWeightLearner
- [st_learned_weights](../../k0/db/alembic/versions/0040_st_learned_weights.py) — Weight storage (EXISTS)
- [P06 feedback events](../../k0/contracts/modules/m14_feedback.yaml) — Feedback signal source

**Goal**: Adjust embedding/string disambiguation weights based on user feedback on merge decisions.

**Problem Statement**:

> Initial weight matrix is based on heuristics. Over time, user corrections reveal:
>
> - "These two entities ARE the same person" (merge approved) → weights were correct
> - "These two entities are NOT the same person" (merge rejected) → weights need adjustment
>
> The differing component (embedding vs string) that caused the false positive should be de-weighted.

**Feedback Signal Types** (from P06):

| Signal | Meaning | Action |
| ------ | ------- | ------ |
| `ENTITY_MERGE_APPROVED` | User confirmed merge was correct | Slight weight reinforcement (+0.01) |
| `ENTITY_MERGE_REJECTED` | User said entities are different | Increase differing component weight |
| `ENTITY_SPLIT_REQUEST` | User manually split merged entity | Strong signal to adjust weights |

**Weight Adjustment Algorithm** (from Dossier §4.5.1.1):

```
On ENTITY_MERGE_REJECTED:
  1. Compute current embedding_sim and string_sim
  2. If embedding_sim >> string_sim:
     → embedding gave false positive, decrease embedding_weight
  3. If string_sim >> embedding_sim:
     → string gave false positive, decrease string_weight
  4. Apply learning_rate (default 0.05)
  5. Normalize to sum=1.0
  6. Clamp to [0.15, 0.85] to prevent extremes
```

**Implementation**:

```python
# File: k0/modules/consolidation/algorithms/weight_learner.py

from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class FeedbackSignal(Enum):
    """User feedback signals for entity merges."""
    MERGE_APPROVED = "ENTITY_MERGE_APPROVED"
    MERGE_REJECTED = "ENTITY_MERGE_REJECTED"
    SPLIT_REQUEST = "ENTITY_SPLIT_REQUEST"


@dataclass
class WeightAdjustment:
    """Result of a weight adjustment operation."""
    entity_type: str
    old_embedding_weight: float
    old_string_weight: float
    new_embedding_weight: float
    new_string_weight: float
    adjustment_reason: str
    persisted: bool = False


class DisambiguationWeightLearner:
    """
    Learn disambiguation weights from user feedback.

    Spec: Dossier §4.5.1.1

    Features:
    - Adjusts weights based on merge approval/rejection
    - Clamps weights to [0.15, 0.85] range
    - Persists learned weights to st_learned_weights
    - Gradual learning with configurable rate
    """

    # Bounds for weights (prevent extreme values)
    WEIGHT_MIN = 0.15
    WEIGHT_MAX = 0.85

    # Learning rates for different signals
    LEARNING_RATES = {
        FeedbackSignal.MERGE_APPROVED: 0.01,   # Small reinforcement
        FeedbackSignal.MERGE_REJECTED: 0.05,   # Moderate adjustment
        FeedbackSignal.SPLIT_REQUEST: 0.10,    # Strong adjustment
    }

    def __init__(
        self,
        current_weights: Dict[str, Tuple[float, float]],
        learning_rate_override: Optional[float] = None,
    ):
        """
        Initialize with current weights.

        Args:
            current_weights: Dict of entity_type -> (embedding_weight, string_weight)
            learning_rate_override: Override default learning rates
        """
        self.weights = {k: list(v) for k, v in current_weights.items()}
        self.learning_rate_override = learning_rate_override
        self.adjustments: list[WeightAdjustment] = []

    def adjust_weights(
        self,
        entity_type: str,
        entity1_embedding: list,
        entity1_name: str,
        entity2_embedding: list,
        entity2_name: str,
        feedback_signal: FeedbackSignal,
    ) -> WeightAdjustment:
        """
        Adjust weights based on user feedback.

        Algorithm:
        1. Compute similarity components (embedding vs string)
        2. Identify which component caused the false positive
        3. Decrease weight of culprit component
        4. Normalize to sum=1.0, clamp to [0.15, 0.85]
        """
        # Get current weights
        if entity_type not in self.weights:
            self.weights[entity_type] = [0.50, 0.50]  # Default

        old_emb = self.weights[entity_type][0]
        old_str = self.weights[entity_type][1]

        # Compute similarities
        from .entity_disambiguator import EntityDisambiguator
        disambiguator = EntityDisambiguator()

        embedding_sim = disambiguator._cosine_similarity(
            entity1_embedding, entity2_embedding
        )
        string_sim = disambiguator.fuzzy_string_match(
            entity1_name, entity2_name
        )

        # Get learning rate
        lr = self.learning_rate_override or self.LEARNING_RATES.get(
            feedback_signal, 0.05
        )

        # Determine adjustment direction
        new_emb, new_str = old_emb, old_str
        reason = ""

        if feedback_signal == FeedbackSignal.MERGE_APPROVED:
            # Reinforce current weights slightly
            # No change needed, weights were correct
            reason = "merge_approved_no_change"

        elif feedback_signal in (FeedbackSignal.MERGE_REJECTED, FeedbackSignal.SPLIT_REQUEST):
            # Identify culprit component
            if embedding_sim > string_sim + 0.1:
                # Embedding gave false positive, decrease its weight
                new_emb = old_emb - lr
                new_str = old_str + lr
                reason = "embedding_false_positive"
            elif string_sim > embedding_sim + 0.1:
                # String gave false positive, decrease its weight
                new_str = old_str - lr
                new_emb = old_emb + lr
                reason = "string_false_positive"
            else:
                # Both components similar, slight decrease to embedding
                new_emb = old_emb - (lr / 2)
                new_str = old_str + (lr / 2)
                reason = "both_components_similar"

        # Normalize to sum=1.0
        total = new_emb + new_str
        new_emb = new_emb / total
        new_str = new_str / total

        # Clamp to bounds
        new_emb = max(self.WEIGHT_MIN, min(self.WEIGHT_MAX, new_emb))
        new_str = max(self.WEIGHT_MIN, min(self.WEIGHT_MAX, new_str))

        # Re-normalize after clamping
        total = new_emb + new_str
        new_emb = new_emb / total
        new_str = new_str / total

        # Update internal state
        self.weights[entity_type] = [new_emb, new_str]

        adjustment = WeightAdjustment(
            entity_type=entity_type,
            old_embedding_weight=old_emb,
            old_string_weight=old_str,
            new_embedding_weight=new_emb,
            new_string_weight=new_str,
            adjustment_reason=reason,
        )

        self.adjustments.append(adjustment)

        logger.info(
            "Weight adjustment",
            extra={
                "entity_type": entity_type,
                "feedback": feedback_signal.value,
                "old_weights": (old_emb, old_str),
                "new_weights": (new_emb, new_str),
                "reason": reason,
            }
        )

        return adjustment

    async def persist_weights(
        self,
        db_conn,
        entity_type: str,
    ) -> bool:
        """
        Persist learned weights to st_learned_weights.

        Uses upsert pattern for idempotency.
        """
        if entity_type not in self.weights:
            return False

        emb_weight, str_weight = self.weights[entity_type]

        # Upsert embedding weight
        await db_conn.execute(
            """
            INSERT INTO st_learned_weights
                (param_category, param_scope, param_key, param_value, active, updated_at)
            VALUES
                ('disambiguation', $1, 'embedding_weight', $2, TRUE, $3)
            ON CONFLICT (param_category, param_scope, param_key)
            DO UPDATE SET
                param_value = EXCLUDED.param_value,
                updated_at = EXCLUDED.updated_at
            """,
            entity_type,
            str(emb_weight),
            now_ms(),
        )

        # Upsert string weight
        await db_conn.execute(
            """
            INSERT INTO st_learned_weights
                (param_category, param_scope, param_key, param_value, active, updated_at)
            VALUES
                ('disambiguation', $1, 'string_weight', $2, TRUE, $3)
            ON CONFLICT (param_category, param_scope, param_key)
            DO UPDATE SET
                param_value = EXCLUDED.param_value,
                updated_at = EXCLUDED.updated_at
            """,
            entity_type,
            str(str_weight),
            now_ms(),
        )

        return True

    def get_adjustment_stats(self) -> Dict[str, int]:
        """Get statistics on adjustments made."""
        stats = {
            "total_adjustments": len(self.adjustments),
            "embedding_decreased": 0,
            "string_decreased": 0,
            "no_change": 0,
        }

        for adj in self.adjustments:
            if adj.adjustment_reason == "merge_approved_no_change":
                stats["no_change"] += 1
            elif "embedding" in adj.adjustment_reason:
                stats["embedding_decreased"] += 1
            elif "string" in adj.adjustment_reason:
                stats["string_decreased"] += 1

        return stats
```

**Configuration**:

| Config Key | Default | Purpose |
| ---------- | ------- | ------- |
| `P03_WEIGHT_LEARNING_RATE` | 0.05 | Default learning rate |
| `P03_WEIGHT_MIN_BOUND` | 0.15 | Minimum allowed weight |
| `P03_WEIGHT_MAX_BOUND` | 0.85 | Maximum allowed weight |
| `P03_WEIGHT_PERSIST_BATCH_SIZE` | 10 | Persist after N adjustments |

**Metrics**:

| Metric Name | Type | Description |
| ----------- | ---- | ----------- |
| `p03_weight_adjustments` | Counter | Weight adjustments by type and reason |
| `p03_weight_value` | Gauge | Current weight values by entity type |
| `p03_weight_learning_rate` | Gauge | Effective learning rate |

**Deliverables**:

- [ ] `FeedbackSignal` enum with MERGE_APPROVED, MERGE_REJECTED, SPLIT_REQUEST
- [ ] `WeightAdjustment` dataclass tracking old/new weights
- [ ] `DisambiguationWeightLearner` class in `weight_learner.py`
- [ ] `adjust_weights()` implementing the algorithm
- [ ] Weight clamping to [0.15, 0.85] range
- [ ] Weight normalization to sum=1.0
- [ ] `persist_weights()` upserting to st_learned_weights
- [ ] `get_adjustment_stats()` for observability

**Acceptance Criteria**:

- [ ] ENTITY_MERGE_REJECTED decreases culprit component weight
- [ ] ENTITY_MERGE_APPROVED does not change weights
- [ ] ENTITY_SPLIT_REQUEST uses higher learning rate (0.10)
- [ ] Weights clamped to [0.15, 0.85] range
- [ ] Weights normalized to sum=1.0 after adjustment
- [ ] Learned weights persisted to st_learned_weights
- [ ] Adjustment reason tracked for debugging

**Test File**: `tests/k0/pipelines/p03/test_r4_weight_learner.py`

**Test Cases**:

1. `test_merge_rejected_embedding_culprit` — Embedding sim >> string sim → embedding decreased
2. `test_merge_rejected_string_culprit` — String sim >> embedding sim → string decreased
3. `test_merge_approved_no_change` — No weight change on approval
4. `test_split_request_higher_learning_rate` — Uses 0.10 instead of 0.05
5. `test_weights_clamped_min` — Weight doesn't go below 0.15
6. `test_weights_clamped_max` — Weight doesn't go above 0.85
7. `test_weights_sum_to_one` — After adjustment, sum=1.0
8. `test_persist_weights_upsert` — Upsert to st_learned_weights
9. `test_unknown_entity_type_defaults` — Unknown type starts at 50/50
10. `test_adjustment_stats` — Stats correctly count adjustments

**Blocked By**: 4.4.2

**Blocks**: 4.4.5

---

#### Issue 4.4.4 — Implement ambiguous entity resolution with context hierarchy

**Status**: NOT_STARTED

**Spec Reference**:

- [Dossier §4.5.1.2](../pipelines/P03_consolidation_dossier_v2.md#4512-ambiguous-entity-resolution) (lines 4300-4550) — Ambiguous Entity Resolution
- [Dossier §4.5.1.3](../pipelines/P03_consolidation_dossier_v2.md#4513-entity-merge-process) (lines 4550-4750) — Entity Merge Process
- [st_entity_resolutions](../../k0/db/alembic/versions/) — Resolution audit table (TO CREATE)
- [P06 gap emission](../../k0/contracts/modules/m14_feedback.yaml) — Low-confidence routing

**Goal**: Resolve ambiguous entity mentions using contextual hierarchy when multiple candidates match.

**Problem Statement**:

> When multiple candidate entities match a mention (e.g., "John" could be John Smith or John Doe),
> the system must select the best candidate using contextual signals:
>
> - Was "John" mentioned recently in this session?
> - Are other entities co-occurring that narrow it down?
> - Is there location context (e.g., "at work" suggests colleague)?
>
> Low-confidence resolutions route to P06 for user clarification.

**Context Hierarchy Priority** (from Dossier §4.5.1.2):

| Priority | Signal | Boost | Rationale |
| -------- | ------ | ----- | --------- |
| P1 | Recent context (same session) | +0.35 | Most recent mention likely same entity |
| P2 | Co-occurring entities | +0.30 | "John and his wife Sarah" → FAMILY_MEMBER John |
| P3 | Location context | +0.20 | "at work" → colleague, "at home" → family |
| P4 | Temporal pattern | +0.10 | Morning mentions → commute-related entities |
| P5 | Frequency | +0.05 | Higher frequency entities more likely |

**Confidence Bands** (from Dossier §4.5.1.2):

| Confidence Range | Action | Description |
| ---------------- | ------ | ----------- |
| ≥ 0.85 | Auto-resolve | High confidence, no human review needed |
| 0.60 - 0.85 | Resolve + flag | Accept resolution but flag for review |
| < 0.60 | Emit gap | Route to P06 as `AMBIGUOUS_ENTITY` gap |

**Implementation**:

```python
# File: k0/modules/consolidation/algorithms/ambiguous_resolver.py

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ResolutionOutcome(Enum):
    """Outcome of entity resolution."""
    AUTO_RESOLVED = "auto_resolved"      # ≥0.85 confidence
    RESOLVED_FLAGGED = "resolved_flagged"  # 0.60-0.85, needs review
    GAP_EMITTED = "gap_emitted"          # <0.60, routed to P06


@dataclass
class CandidateEntity:
    """A candidate entity for resolution."""
    entity_id: str
    entity_type: str
    canonical_name: str
    embedding: list
    last_seen_ms: int
    frequency: int


@dataclass
class EventContext:
    """Context from the current event for resolution."""
    session_id: str
    event_timestamp_ms: int
    co_occurring_entities: List[str]  # entity_ids in same event
    location_hint: Optional[str]      # e.g., "work", "home"
    temporal_category: Optional[str]  # e.g., "morning", "evening"


@dataclass
class ResolutionResult:
    """Result of ambiguous entity resolution."""
    mention: str
    selected_entity_id: Optional[str]
    confidence: float
    outcome: ResolutionOutcome
    breakdown: Dict[str, float]
    candidates_considered: int


class AmbiguousEntityResolver:
    """
    Resolve ambiguous entity mentions using context hierarchy.

    Spec: Dossier §4.5.1.2

    Features:
    - 5-priority context hierarchy
    - Confidence band routing
    - P06 gap emission for low confidence
    - Full audit trail in st_entity_resolutions
    """

    # Priority boosts from Dossier §4.5.1.2
    PRIORITY_BOOSTS = {
        "recent_context": 0.35,       # P1: Same session recency
        "co_occurring": 0.30,         # P2: Co-occurring entities
        "location": 0.20,             # P3: Location hint
        "temporal": 0.10,             # P4: Temporal pattern
        "frequency": 0.05,            # P5: Historical frequency
    }

    # Confidence thresholds
    THRESHOLD_AUTO = 0.85
    THRESHOLD_FLAG = 0.60

    def __init__(
        self,
        recency_window_ms: int = 3600_000,  # 1 hour default
    ):
        """
        Initialize resolver.

        Args:
            recency_window_ms: Window for "recent" context boost
        """
        self.recency_window_ms = recency_window_ms

    def resolve(
        self,
        mention: str,
        candidates: List[CandidateEntity],
        event_context: EventContext,
    ) -> ResolutionResult:
        """
        Resolve ambiguous mention to best candidate.

        Algorithm:
        1. Score each candidate using 5-priority hierarchy
        2. Select highest-scoring candidate
        3. Route based on confidence bands
        """
        if not candidates:
            return ResolutionResult(
                mention=mention,
                selected_entity_id=None,
                confidence=0.0,
                outcome=ResolutionOutcome.GAP_EMITTED,
                breakdown={},
                candidates_considered=0,
            )

        if len(candidates) == 1:
            # Single candidate, high confidence
            return ResolutionResult(
                mention=mention,
                selected_entity_id=candidates[0].entity_id,
                confidence=0.95,
                outcome=ResolutionOutcome.AUTO_RESOLVED,
                breakdown={"single_candidate": 0.95},
                candidates_considered=1,
            )

        # Score all candidates
        scored = []
        for candidate in candidates:
            score, breakdown = self._score_candidate(
                candidate, event_context
            )
            scored.append((candidate, score, breakdown))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)

        best_candidate, best_score, best_breakdown = scored[0]

        # Determine confidence gap to second-best
        if len(scored) > 1:
            second_score = scored[1][1]
            gap = best_score - second_score

            # If gap is small, reduce confidence
            if gap < 0.10:
                best_score *= 0.90  # 10% penalty for close race

        # Determine outcome based on confidence bands
        if best_score >= self.THRESHOLD_AUTO:
            outcome = ResolutionOutcome.AUTO_RESOLVED
        elif best_score >= self.THRESHOLD_FLAG:
            outcome = ResolutionOutcome.RESOLVED_FLAGGED
        else:
            outcome = ResolutionOutcome.GAP_EMITTED

        return ResolutionResult(
            mention=mention,
            selected_entity_id=best_candidate.entity_id if outcome != ResolutionOutcome.GAP_EMITTED else None,
            confidence=best_score,
            outcome=outcome,
            breakdown=best_breakdown,
            candidates_considered=len(candidates),
        )

    def _score_candidate(
        self,
        candidate: CandidateEntity,
        context: EventContext,
    ) -> Tuple[float, Dict[str, float]]:
        """
        Score a candidate using 5-priority hierarchy.

        Returns: (total_score, breakdown_dict)
        """
        breakdown = {}
        base_score = 0.30  # Baseline for string match

        # P1: Recent context (same session recency)
        recency_age = context.event_timestamp_ms - candidate.last_seen_ms
        if recency_age <= self.recency_window_ms:
            recency_factor = 1.0 - (recency_age / self.recency_window_ms)
            recency_boost = self.PRIORITY_BOOSTS["recent_context"] * recency_factor
            breakdown["recent_context"] = recency_boost
            base_score += recency_boost

        # P2: Co-occurring entities
        if candidate.entity_id in context.co_occurring_entities:
            co_boost = self.PRIORITY_BOOSTS["co_occurring"]
            breakdown["co_occurring"] = co_boost
            base_score += co_boost

        # P3: Location context
        if context.location_hint:
            location_match = self._check_location_match(
                candidate, context.location_hint
            )
            if location_match:
                loc_boost = self.PRIORITY_BOOSTS["location"]
                breakdown["location"] = loc_boost
                base_score += loc_boost

        # P4: Temporal pattern
        if context.temporal_category:
            temporal_match = self._check_temporal_match(
                candidate, context.temporal_category
            )
            if temporal_match:
                temp_boost = self.PRIORITY_BOOSTS["temporal"]
                breakdown["temporal"] = temp_boost
                base_score += temp_boost

        # P5: Frequency (normalized to max 1.0)
        freq_score = min(1.0, candidate.frequency / 100)
        freq_boost = self.PRIORITY_BOOSTS["frequency"] * freq_score
        breakdown["frequency"] = freq_boost
        base_score += freq_boost

        return min(1.0, base_score), breakdown

    def _check_location_match(
        self,
        candidate: CandidateEntity,
        location_hint: str,
    ) -> bool:
        """
        Check if candidate matches location hint.

        Location hints: 'work', 'home', 'school', 'gym', etc.
        """
        # TODO: Integrate with location-entity associations from st_kg_edges
        location_entity_map = {
            "work": ["ORGANIZATION", "colleague"],
            "home": ["FAMILY_MEMBER", "friend"],
            "school": ["teacher", "student"],
        }

        hints = location_entity_map.get(location_hint.lower(), [])
        return (
            candidate.entity_type in hints or
            any(h in candidate.canonical_name.lower() for h in hints)
        )

    def _check_temporal_match(
        self,
        candidate: CandidateEntity,
        temporal_category: str,
    ) -> bool:
        """
        Check if candidate matches temporal pattern.

        Temporal categories: 'morning', 'afternoon', 'evening', 'weekend'
        """
        # TODO: Integrate with temporal-entity patterns from st_epi
        # For now, return False (no temporal pattern data yet)
        return False

    async def emit_gap_to_p06(
        self,
        mention: str,
        candidates: List[CandidateEntity],
        event_context: EventContext,
        result: ResolutionResult,
        event_bus,
    ):
        """
        Emit AMBIGUOUS_ENTITY gap to P06 for user resolution.
        """
        gap_payload = {
            "gap_type": "AMBIGUOUS_ENTITY",
            "mention": mention,
            "candidates": [
                {
                    "entity_id": c.entity_id,
                    "name": c.canonical_name,
                    "type": c.entity_type,
                }
                for c in candidates[:5]  # Limit to top 5
            ],
            "context": {
                "session_id": event_context.session_id,
                "co_occurring": event_context.co_occurring_entities,
                "location_hint": event_context.location_hint,
            },
            "confidence": result.confidence,
            "breakdown": result.breakdown,
        }

        await event_bus.publish(
            topic="p06.gaps.entity",
            payload=gap_payload,
        )

        logger.info(
            "Emitted AMBIGUOUS_ENTITY gap",
            extra={"mention": mention, "candidates": len(candidates)}
        )

    async def record_resolution(
        self,
        result: ResolutionResult,
        event_context: EventContext,
        db_conn,
    ):
        """
        Record resolution in st_entity_resolutions for audit.
        """
        await db_conn.execute(
            """
            INSERT INTO st_entity_resolutions (
                resolution_id, mention, selected_entity_id,
                confidence, outcome, breakdown_json,
                candidates_count, session_id, created_at
            ) VALUES (
                gen_random_uuid(), $1, $2, $3, $4, $5, $6, $7, $8
            )
            """,
            result.mention,
            result.selected_entity_id,
            result.confidence,
            result.outcome.value,
            json.dumps(result.breakdown),
            result.candidates_considered,
            event_context.session_id,
            now_ms(),
        )
```

**Migration: st_entity_resolutions** (TO CREATE):

```python
# File: k0/db/alembic/versions/0057_st_entity_resolutions.py

def upgrade():
    op.create_table(
        'st_entity_resolutions',
        sa.Column('resolution_id', sa.String(36), primary_key=True),
        sa.Column('mention', sa.Text, nullable=False),
        sa.Column('selected_entity_id', sa.String(36), nullable=True),
        sa.Column('confidence', sa.Float, nullable=False),
        sa.Column('outcome', sa.String(32), nullable=False),  # auto_resolved, resolved_flagged, gap_emitted
        sa.Column('breakdown_json', sa.Text, nullable=True),
        sa.Column('candidates_count', sa.Integer, nullable=False),
        sa.Column('session_id', sa.String(36), nullable=True),
        sa.Column('feedback_received', sa.Boolean, default=False),
        sa.Column('corrected_entity_id', sa.String(36), nullable=True),
        sa.Column('created_at', sa.BigInteger, nullable=False),
        sa.Column('updated_at', sa.BigInteger, nullable=True),
    )
    op.create_index('ix_st_entity_resolutions_mention', 'st_entity_resolutions', ['mention'])
    op.create_index('ix_st_entity_resolutions_outcome', 'st_entity_resolutions', ['outcome'])
    op.create_index('ix_st_entity_resolutions_session', 'st_entity_resolutions', ['session_id'])
```

**Configuration**:

| Config Key | Default | Purpose |
| ---------- | ------- | ------- |
| `P03_RESOLUTION_THRESHOLD_AUTO` | 0.85 | Auto-resolve threshold |
| `P03_RESOLUTION_THRESHOLD_FLAG` | 0.60 | Flag-for-review threshold |
| `P03_RESOLUTION_RECENCY_WINDOW_MS` | 3600000 | 1 hour recency window |
| `P03_RESOLUTION_MAX_CANDIDATES_GAP` | 5 | Max candidates in P06 gap |

**Metrics**:

| Metric Name | Type | Description |
| ----------- | ---- | ----------- |
| `p03_resolution_outcome` | Counter | Resolutions by outcome |
| `p03_resolution_confidence` | Histogram | Resolution confidence distribution |
| `p03_resolution_candidates` | Histogram | Candidates per resolution |
| `p03_resolution_boost_applied` | Counter | Which priority boosts were applied |

**Deliverables**:

- [ ] `ResolutionOutcome` enum (AUTO_RESOLVED, RESOLVED_FLAGGED, GAP_EMITTED)
- [ ] `CandidateEntity` dataclass
- [ ] `EventContext` dataclass with co-occurring entities
- [ ] `ResolutionResult` dataclass with breakdown
- [ ] `AmbiguousEntityResolver` class in `ambiguous_resolver.py`
- [ ] `resolve(mention, candidates, context)` implementing hierarchy
- [ ] `_score_candidate()` with 5-priority scoring
- [ ] `emit_gap_to_p06()` for low-confidence routing
- [ ] `record_resolution()` for st_entity_resolutions audit
- [ ] Migration 0057_st_entity_resolutions.py

**Acceptance Criteria**:

- [ ] Recent context (P1) provides +0.35 boost
- [ ] Co-occurring entities (P2) provide +0.30 boost
- [ ] Location context (P3) provides +0.20 boost
- [ ] Temporal pattern (P4) provides +0.10 boost
- [ ] Frequency (P5) provides up to +0.05 boost
- [ ] Score ≥0.85 → AUTO_RESOLVED
- [ ] Score 0.60-0.85 → RESOLVED_FLAGGED
- [ ] Score <0.60 → GAP_EMITTED to P06
- [ ] Close race (gap <0.10) penalized by 10%
- [ ] All resolutions recorded in st_entity_resolutions

**Test File**: `tests/k0/pipelines/p03/test_r4_ambiguous_resolver.py`

**Test Cases**:

1. `test_single_candidate_auto_resolves` — One candidate → 0.95 confidence
2. `test_recent_context_boost` — P1 boost applied for recent entity
3. `test_co_occurring_boost` — P2 boost for co-occurring entity
4. `test_location_boost_work` — P3 boost when location="work"
5. `test_frequency_boost_scales` — P5 boost scales with frequency
6. `test_auto_resolve_above_085` — Score 0.88 → AUTO_RESOLVED
7. `test_flagged_between_060_085` — Score 0.72 → RESOLVED_FLAGGED
8. `test_gap_emitted_below_060` — Score 0.55 → GAP_EMITTED
9. `test_close_race_penalty` — Two candidates with 0.02 gap → penalty applied
10. `test_emit_gap_to_p06` — P06 gap contains correct payload
11. `test_record_resolution_audit` — Resolution recorded in st_entity_resolutions
12. `test_no_candidates_emits_gap` — Empty candidates → GAP_EMITTED

**Blocked By**: 4.4.2

**Blocks**: 4.4.5, 4.4.6

---

#### Issue 4.4.5 — Implement entity resolution confidence bands + P06 gap emission

**Status**: NOT_STARTED

**Spec Reference**:

- [Dossier §4.5.1.2](../pipelines/P03_consolidation_dossier_v2.md#4512-ambiguous-entity-resolution) (lines 4300-4430) — Confidence Bands
- [P06 Gap Protocol](../../k0/contracts/modules/m14_feedback.yaml) — Gap emission spec
- [st_entity_resolutions](../../k0/db/alembic/versions/0057_st_entity_resolutions.py) — Resolution audit (from 4.4.4)

**Goal**: Route entity resolutions through confidence bands with P06 gap emission for low-confidence cases.

**Problem Statement**:

> Entity resolution confidence varies — some are certain, others ambiguous:
>
> - "Mom" in context → 99% confidence (auto-resolve)
> - "John" with 3 candidates at 70% → flag for review
> - "Smith" with no context → 45% confidence → must ask user
>
> Low-confidence guesses create bad UX. Better to ask via P06 than guess wrong.

**Confidence Bands** (from Dossier §4.5.1.2):

| Band | Range | Action | P06 Emission |
| ---- | ----- | ------ | ------------ |
| HIGH | ≥ 0.85 | Auto-resolve silently | None |
| MEDIUM | 0.60 - 0.85 | Resolve + flag for review | `ENTITY_FLAGGED` (background) |
| LOW | < 0.60 | Do not resolve | `AMBIGUOUS_ENTITY` (prompt user) |

**Implementation**:

```python
# File: k0/modules/consolidation/algorithms/confidence_router.py

from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ConfidenceBand(Enum):
    """Entity resolution confidence bands."""
    HIGH = "high"        # ≥0.85: Auto-resolve
    MEDIUM = "medium"    # 0.60-0.85: Resolve + flag
    LOW = "low"          # <0.60: Emit gap


@dataclass
class GapPayload:
    """Payload for P06 gap emission."""
    gap_type: str
    mention: str
    candidates: List[Dict]
    context: Dict
    confidence: float
    session_id: str
    event_id: str


class ConfidenceRouter:
    """
    Route entity resolutions based on confidence bands.

    Spec: Dossier §4.5.1.2

    Features:
    - Three-band confidence routing
    - P06 gap emission for LOW band
    - Background flagging for MEDIUM band
    - Full audit trail
    """

    # Thresholds from Dossier
    THRESHOLD_HIGH = 0.85
    THRESHOLD_MEDIUM = 0.60

    def __init__(
        self,
        event_bus,
        threshold_high: float = 0.85,
        threshold_medium: float = 0.60,
    ):
        """
        Initialize router with thresholds.

        Args:
            event_bus: Event bus for P06 gap emission
            threshold_high: Upper threshold (auto-resolve above)
            threshold_medium: Lower threshold (emit gap below)
        """
        self.event_bus = event_bus
        self.threshold_high = threshold_high
        self.threshold_medium = threshold_medium

    def classify_band(self, confidence: float) -> ConfidenceBand:
        """
        Classify confidence into band.
        """
        if confidence >= self.threshold_high:
            return ConfidenceBand.HIGH
        elif confidence >= self.threshold_medium:
            return ConfidenceBand.MEDIUM
        else:
            return ConfidenceBand.LOW

    async def route_resolution(
        self,
        mention: str,
        selected_entity_id: Optional[str],
        confidence: float,
        candidates: List[Dict],
        event_context: Dict,
    ) -> Dict:
        """
        Route resolution based on confidence band.

        Returns: routing decision with action taken
        """
        band = self.classify_band(confidence)

        result = {
            "mention": mention,
            "confidence": confidence,
            "band": band.value,
            "selected_entity_id": selected_entity_id,
            "action": None,
            "gap_emitted": False,
        }

        if band == ConfidenceBand.HIGH:
            # Auto-resolve, no further action
            result["action"] = "auto_resolved"
            self.metrics.p03_resolution_auto.inc()

        elif band == ConfidenceBand.MEDIUM:
            # Resolve but flag for background review
            result["action"] = "resolved_flagged"
            await self._emit_flagged_gap(
                mention, selected_entity_id, confidence, candidates, event_context
            )
            result["gap_emitted"] = True
            self.metrics.p03_resolution_flagged.inc()

        else:  # LOW
            # Do not resolve, emit gap for user input
            result["action"] = "gap_emitted"
            result["selected_entity_id"] = None  # Clear selection
            await self._emit_ambiguous_gap(
                mention, candidates, confidence, event_context
            )
            result["gap_emitted"] = True
            self.metrics.p03_resolution_gap.inc()

        return result

    async def _emit_ambiguous_gap(
        self,
        mention: str,
        candidates: List[Dict],
        confidence: float,
        event_context: Dict,
    ):
        """
        Emit AMBIGUOUS_ENTITY gap to P06 for user resolution.

        Topic: p03.gap.detected.v1
        """
        gap_payload = {
            "gap_type": "AMBIGUOUS_ENTITY",
            "priority": "MEDIUM",  # Entity resolution is medium priority
            "mention": mention,
            "candidates": [
                {
                    "entity_id": c.get("entity_id"),
                    "name": c.get("canonical_name"),
                    "type": c.get("entity_type"),
                    "score": c.get("score", 0.0),
                }
                for c in candidates[:5]  # Limit to top 5
            ],
            "context": {
                "session_id": event_context.get("session_id"),
                "event_id": event_context.get("event_id"),
                "co_occurring_entities": event_context.get("co_occurring", []),
                "location_hint": event_context.get("location_hint"),
                "raw_text_snippet": event_context.get("text_snippet", ""),
            },
            "confidence": confidence,
            "suggested_question": self._generate_clarification_question(
                mention, candidates
            ),
            "emitted_at": now_ms(),
        }

        await self.event_bus.publish(
            topic="p03.gap.detected.v1",
            payload=gap_payload,
        )

        logger.info(
            "Emitted AMBIGUOUS_ENTITY gap",
            extra={
                "mention": mention,
                "candidates": len(candidates),
                "confidence": confidence,
            }
        )

    async def _emit_flagged_gap(
        self,
        mention: str,
        selected_entity_id: str,
        confidence: float,
        candidates: List[Dict],
        event_context: Dict,
    ):
        """
        Emit ENTITY_FLAGGED gap for background review.

        Lower priority than AMBIGUOUS — system resolved but wants confirmation.
        """
        gap_payload = {
            "gap_type": "ENTITY_FLAGGED",
            "priority": "LOW",  # Background review
            "mention": mention,
            "selected_entity_id": selected_entity_id,
            "confidence": confidence,
            "alternative_candidates": [
                {
                    "entity_id": c.get("entity_id"),
                    "name": c.get("canonical_name"),
                    "score": c.get("score", 0.0),
                }
                for c in candidates[1:4]  # Skip selected, show alternatives
            ],
            "context": {
                "session_id": event_context.get("session_id"),
                "event_id": event_context.get("event_id"),
            },
            "emitted_at": now_ms(),
        }

        await self.event_bus.publish(
            topic="p03.gap.detected.v1",
            payload=gap_payload,
        )

    def _generate_clarification_question(
        self,
        mention: str,
        candidates: List[Dict],
    ) -> str:
        """
        Generate user-friendly clarification question.
        """
        if len(candidates) == 0:
            return f"Who is '{mention}'?"
        elif len(candidates) == 2:
            names = [c.get("canonical_name", "?") for c in candidates[:2]]
            return f"When you said '{mention}', did you mean {names[0]} or {names[1]}?"
        else:
            names = [c.get("canonical_name", "?") for c in candidates[:3]]
            return f"When you said '{mention}', did you mean {', '.join(names[:-1])}, or {names[-1]}?"
```

**Configuration**:

| Config Key | Default | Purpose |
| ---------- | ------- | ------- |
| `P03_CONFIDENCE_THRESHOLD_HIGH` | 0.85 | Auto-resolve threshold |
| `P03_CONFIDENCE_THRESHOLD_MEDIUM` | 0.60 | Flag-for-review threshold |
| `P03_GAP_MAX_CANDIDATES` | 5 | Max candidates in gap payload |
| `P03_GAP_TOPIC` | `p03.gap.detected.v1` | P06 gap topic |

**Metrics**:

| Metric Name | Type | Description |
| ----------- | ---- | ----------- |
| `p03_resolution_auto` | Counter | HIGH band auto-resolves |
| `p03_resolution_flagged` | Counter | MEDIUM band flagged resolutions |
| `p03_resolution_gap` | Counter | LOW band gap emissions |
| `p03_gap_response_time_ms` | Histogram | Time for P06 to respond |

**Deliverables**:

- [ ] `ConfidenceBand` enum (HIGH, MEDIUM, LOW)
- [ ] `GapPayload` dataclass
- [ ] `ConfidenceRouter` class in `confidence_router.py`
- [ ] `classify_band(confidence)` returning band
- [ ] `route_resolution()` with three-band routing
- [ ] `_emit_ambiguous_gap()` for LOW band
- [ ] `_emit_flagged_gap()` for MEDIUM band
- [ ] `_generate_clarification_question()` for user prompts
- [ ] Topic: `p03.gap.detected.v1`

**Acceptance Criteria**:

- [ ] Confidence ≥0.85 → AUTO_RESOLVED, no gap emitted
- [ ] Confidence 0.60-0.85 → RESOLVED_FLAGGED, ENTITY_FLAGGED gap emitted
- [ ] Confidence <0.60 → selection cleared, AMBIGUOUS_ENTITY gap emitted
- [ ] Gap payload includes top 5 candidates
- [ ] Clarification question generated for user
- [ ] Metrics track resolutions by band

**Test File**: `tests/k0/pipelines/p03/test_r4_confidence_router.py`

**Test Cases**:

1. `test_high_band_auto_resolves` — 0.90 confidence → auto_resolved, no gap
2. `test_medium_band_flags` — 0.72 confidence → resolved_flagged + ENTITY_FLAGGED gap
3. `test_low_band_emits_gap` — 0.45 confidence → gap_emitted + AMBIGUOUS_ENTITY
4. `test_low_band_clears_selection` — selected_entity_id=None for low band
5. `test_gap_payload_structure` — All required fields present
6. `test_max_candidates_limited` — Only 5 candidates in payload
7. `test_clarification_question_two` — "did you mean X or Y?"
8. `test_clarification_question_three` — "did you mean X, Y, or Z?"
9. `test_metrics_increment` — Correct counter incremented

**Blocked By**: 4.4.4

**Blocks**: 4.4.7

---

#### Issue 4.4.6 — Implement adaptive merge thresholds per entity type

**Status**: NOT_STARTED

**Spec Reference**:

- [Dossier §4.5.1.1](../pipelines/P03_consolidation_dossier_v2.md#4511-per-entity-type-disambiguation) (lines 4061-4100) — Per-Type Thresholds
- [st_learned_weights](../../k0/db/alembic/versions/0040_st_learned_weights.py) — Threshold storage (EXISTS)
- [DisambiguationWeightLearner](./M4_EXECUTION.md#issue-443) — Related learning mechanism

**Goal**: Learn per-entity-type similarity thresholds for merge decisions based on feedback.

**Problem Statement**:

> Different entity types require different merge thresholds:
>
> - FAMILY_MEMBER: Very high threshold (0.90) — merging wrong family members is catastrophic
> - CONCEPT: Lower threshold (0.65) — abstract concepts can be more liberally merged
> - THING: Moderate threshold (0.70) — objects have synonyms ("couch"/"sofa")
>
> Fixed thresholds don't adapt. Learning from merge corrections improves accuracy.

**Initial Threshold Matrix** (from Dossier §4.5.1.1):

| Entity Type | Default Threshold | Learning Bounds | Rationale |
| ----------- | ----------------- | --------------- | --------- |
| `FAMILY_MEMBER` | 0.90 | [0.85, 0.98] | Highest stakes, rarely merge |
| `PERSON` | 0.85 | [0.80, 0.95] | Names matter, moderate caution |
| `PLACE` | 0.75 | [0.65, 0.85] | Locations have synonyms |
| `ORGANIZATION` | 0.80 | [0.70, 0.90] | Company names vary |
| `THING` | 0.70 | [0.60, 0.80] | Objects have many synonyms |
| `CONCEPT` | 0.65 | [0.55, 0.75] | Abstract, liberal merging OK |
| `EVENT` | 0.75 | [0.65, 0.85] | Activities can overlap |
| `TEMPORAL` | 0.80 | [0.70, 0.90] | Time references need precision |

**Implementation**:

```python
# File: k0/modules/consolidation/algorithms/merge_threshold_learner.py

from dataclasses import dataclass
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class ThresholdBounds:
    """Learning bounds for a threshold."""
    min_value: float
    max_value: float
    default: float


@dataclass
class ThresholdAdjustment:
    """Result of threshold adjustment."""
    entity_type: str
    old_threshold: float
    new_threshold: float
    adjustment: float
    reason: str


class AdaptiveMergeThresholds:
    """
    Per-entity-type merge thresholds with learning.

    Spec: Dossier §4.5.1.1

    Features:
    - Per-type default thresholds
    - Learning from merge feedback
    - Bounds to prevent extreme values
    - Persistence to st_learned_weights
    """

    # Default thresholds and bounds per entity type
    DEFAULT_THRESHOLDS: Dict[str, ThresholdBounds] = {
        "FAMILY_MEMBER": ThresholdBounds(0.85, 0.98, 0.90),
        "PERSON": ThresholdBounds(0.80, 0.95, 0.85),
        "PLACE": ThresholdBounds(0.65, 0.85, 0.75),
        "LOCATION": ThresholdBounds(0.65, 0.85, 0.75),  # Alias
        "ORGANIZATION": ThresholdBounds(0.70, 0.90, 0.80),
        "THING": ThresholdBounds(0.60, 0.80, 0.70),
        "OBJECT": ThresholdBounds(0.60, 0.80, 0.70),  # Alias
        "CONCEPT": ThresholdBounds(0.55, 0.75, 0.65),
        "EVENT": ThresholdBounds(0.65, 0.85, 0.75),
        "TEMPORAL": ThresholdBounds(0.70, 0.90, 0.80),
    }

    # Learning rates for different feedback signals
    LEARNING_RATES: Dict[str, float] = {
        "MERGE_CONFIRMED": 0.0,      # Correct, no change
        "MERGE_REJECTED": +0.02,     # False positive: raise threshold
        "SPLIT_REQUEST": +0.05,      # Strong FP: raise more
        "MISSED_MERGE": -0.02,       # False negative: lower threshold
    }

    def __init__(
        self,
        learned_thresholds: Optional[Dict[str, float]] = None,
    ):
        """
        Initialize with optional learned thresholds.

        Args:
            learned_thresholds: Override defaults from st_learned_weights
        """
        self.thresholds: Dict[str, float] = {}

        # Initialize with defaults
        for entity_type, bounds in self.DEFAULT_THRESHOLDS.items():
            self.thresholds[entity_type] = bounds.default

        # Apply learned overrides
        if learned_thresholds:
            for entity_type, threshold in learned_thresholds.items():
                if entity_type in self.thresholds:
                    # Validate within bounds
                    bounds = self.DEFAULT_THRESHOLDS[entity_type]
                    self.thresholds[entity_type] = max(
                        bounds.min_value,
                        min(bounds.max_value, threshold)
                    )

    def get_threshold(self, entity_type: str) -> float:
        """
        Get merge threshold for entity type.

        Returns default 0.75 for unknown types.
        """
        return self.thresholds.get(entity_type, 0.75)

    def should_merge(
        self,
        entity_type: str,
        similarity_score: float,
    ) -> Tuple[bool, float, float]:
        """
        Determine if entities should be merged.

        Returns: (should_merge, score, threshold)
        """
        threshold = self.get_threshold(entity_type)
        return (similarity_score >= threshold, similarity_score, threshold)

    def adjust_threshold(
        self,
        entity_type: str,
        feedback_signal: str,
    ) -> ThresholdAdjustment:
        """
        Adjust threshold based on feedback.

        Feedback signals:
        - MERGE_CONFIRMED: Correct merge, no change
        - MERGE_REJECTED: False positive, raise threshold
        - SPLIT_REQUEST: Strong FP, raise more
        - MISSED_MERGE: False negative, lower threshold
        """
        old_threshold = self.get_threshold(entity_type)
        adjustment = self.LEARNING_RATES.get(feedback_signal, 0.0)

        new_threshold = old_threshold + adjustment

        # Get bounds for this type
        bounds = self.DEFAULT_THRESHOLDS.get(
            entity_type,
            ThresholdBounds(0.60, 0.90, 0.75)
        )

        # Clamp to bounds
        new_threshold = max(
            bounds.min_value,
            min(bounds.max_value, new_threshold)
        )

        # Update internal state
        self.thresholds[entity_type] = new_threshold

        result = ThresholdAdjustment(
            entity_type=entity_type,
            old_threshold=old_threshold,
            new_threshold=new_threshold,
            adjustment=adjustment,
            reason=feedback_signal,
        )

        logger.info(
            "Threshold adjusted",
            extra={
                "entity_type": entity_type,
                "old": old_threshold,
                "new": new_threshold,
                "signal": feedback_signal,
            }
        )

        return result

    async def persist_threshold(
        self,
        entity_type: str,
        db_conn,
    ) -> bool:
        """
        Persist learned threshold to st_learned_weights.
        """
        threshold = self.thresholds.get(entity_type)
        if threshold is None:
            return False

        await db_conn.execute(
            """
            INSERT INTO st_learned_weights
                (param_category, param_scope, param_key, param_value, active, updated_at)
            VALUES
                ('merge_threshold', $1, 'similarity_threshold', $2, TRUE, $3)
            ON CONFLICT (param_category, param_scope, param_key)
            DO UPDATE SET
                param_value = EXCLUDED.param_value,
                updated_at = EXCLUDED.updated_at
            """,
            entity_type,
            str(threshold),
            now_ms(),
        )

        return True

    @classmethod
    async def load_from_database(
        cls,
        db_conn,
    ) -> "AdaptiveMergeThresholds":
        """
        Load learned thresholds from st_learned_weights.
        """
        rows = await db_conn.fetch(
            """
            SELECT param_scope, param_value
            FROM st_learned_weights
            WHERE param_category = 'merge_threshold'
              AND param_key = 'similarity_threshold'
              AND active = TRUE
            """
        )

        learned = {}
        for row in rows:
            entity_type = row["param_scope"]
            threshold = float(row["param_value"])
            learned[entity_type] = threshold

        return cls(learned_thresholds=learned)
```

**Configuration**:

| Config Key | Default | Purpose |
| ---------- | ------- | ------- |
| `P03_MERGE_THRESHOLD_FAMILY_MEMBER` | 0.90 | FAMILY_MEMBER threshold |
| `P03_MERGE_THRESHOLD_PERSON` | 0.85 | PERSON threshold |
| `P03_MERGE_THRESHOLD_DEFAULT` | 0.75 | Default for unknown types |
| `P03_MERGE_LEARNING_RATE_FP` | 0.02 | False positive adjustment |

**Metrics**:

| Metric Name | Type | Description |
| ----------- | ---- | ----------- |
| `p03_merge_threshold_value` | Gauge | Current threshold by entity type |
| `p03_merge_threshold_adjustments` | Counter | Adjustments by type and signal |
| `p03_merge_decisions` | Counter | Merge decisions by outcome |

**Deliverables**:

- [ ] `ThresholdBounds` dataclass with min/max/default
- [ ] `ThresholdAdjustment` dataclass for audit
- [ ] `AdaptiveMergeThresholds` class in `merge_threshold_learner.py`
- [ ] `DEFAULT_THRESHOLDS` dict with bounds per entity type
- [ ] `get_threshold(entity_type)` returning current threshold
- [ ] `should_merge(entity_type, score)` returning decision tuple
- [ ] `adjust_threshold(entity_type, feedback)` with learning
- [ ] `persist_threshold()` to st_learned_weights
- [ ] `load_from_database()` class method

**Acceptance Criteria**:

- [ ] FAMILY_MEMBER default threshold is 0.90
- [ ] PERSON default threshold is 0.85
- [ ] CONCEPT default threshold is 0.65
- [ ] MERGE_REJECTED raises threshold by 0.02
- [ ] SPLIT_REQUEST raises threshold by 0.05
- [ ] Thresholds clamped within bounds
- [ ] Unknown entity types use 0.75 default
- [ ] Learned thresholds persisted to st_learned_weights

**Test File**: `tests/k0/pipelines/p03/test_r4_merge_thresholds.py`

**Test Cases**:

1. `test_family_member_high_threshold` — Default 0.90
2. `test_concept_low_threshold` — Default 0.65
3. `test_should_merge_above_threshold` — 0.92 PERSON → should_merge=True
4. `test_should_merge_below_threshold` — 0.80 PERSON → should_merge=False
5. `test_merge_rejected_raises_threshold` — +0.02 adjustment
6. `test_split_request_raises_more` — +0.05 adjustment
7. `test_missed_merge_lowers_threshold` — -0.02 adjustment
8. `test_threshold_clamped_max` — Cannot exceed upper bound
9. `test_threshold_clamped_min` — Cannot go below lower bound
10. `test_unknown_type_default` — Unknown uses 0.75
11. `test_persist_threshold` — Upsert to st_learned_weights
12. `test_load_from_database` — Loads overrides correctly

**Blocked By**: 4.4.2, 4.4.3

**Blocks**: 4.4.7

---

#### Issue 4.4.7 — Implement entity merge cascade + undo support

**Status**: NOT_STARTED

**Spec Reference**:

- [Dossier §4.5.1.3](../pipelines/P03_consolidation_dossier_v2.md#4513-entity-merge-process) (lines 4436-4700) — Entity Merge Process
- [st_entity_merges](../../k0/db/alembic/versions/) — Merge audit table (TO CREATE)
- [Cascade Tables](../pipelines/P03_consolidation_dossier_v2.md#cascade-update-tables) — 7 tables to update

**Goal**: Complete entity merges with full cascade and reversibility.

**Problem Statement**:

> When entities are merged ("J. Smith" = "John Smith"), references exist in many tables:
>
> - st_kg_edges: Relationship edges
> - st_hipp_events: Event entity mentions
> - st_epi: Episode entity links
> - st_sem: Pattern entity links
> - st_social: Actor references
> - st_procedural: Habit participants
> - st_vec: Embedding metadata
>
> All must be updated atomically. If merge was wrong, must be reversible.

**6-Step Merge Process** (from Dossier §4.5.1.3):

| Step | Action | Description |
| ---- | ------ | ----------- |
| 1 | Validate | Ensure entities exist, not already merged |
| 2 | Select Primary | Choose entity with more history |
| 3 | Merge Attributes | Combine properties, keep best |
| 4 | Cascade | Update all 7 tables |
| 5 | Archive | Mark secondary as MERGED |
| 6 | Log | Record for undo support |

**Cascade Tables** (from Dossier):

| Table | Update Method | Column(s) |
| ----- | ------------- | --------- |
| `st_kg_edges` | Redirect source/target | source_entity_id, target_entity_id |
| `st_hipp_events` | JSON replace | entities_json |
| `st_epi` | Array replace | entity_ids |
| `st_sem` | Array replace | entity_ids |
| `st_social` | Direct replace | actor_id |
| `st_procedural` | Array replace | participants |
| `st_vec` | JSON replace | metadata_json |

**Implementation**:

```python
# File: k0/modules/consolidation/algorithms/entity_merger.py

from dataclasses import dataclass
from typing import Dict, List, Optional
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class MergeResult:
    """Result of entity merge operation."""
    merge_id: str
    primary_entity_id: str
    secondary_entity_id: str
    cascade_counts: Dict[str, int]
    success: bool
    error: Optional[str] = None


@dataclass
class EntitySnapshot:
    """Snapshot of entity state for undo."""
    entity_id: str
    canonical_name: str
    entity_type: str
    properties: Dict
    observation_count: int


class EntityMerger:
    """
    Complete entity merge with cascade and undo support.

    Spec: Dossier §4.5.1.3

    Features:
    - 6-step merge process
    - Cascade updates across 7 tables
    - Atomic transaction
    - Full undo support via snapshots
    """

    async def merge_entities(
        self,
        primary_entity_id: str,
        secondary_entity_id: str,
        merge_reason: str,
        initiated_by: str,
        db_conn,
    ) -> MergeResult:
        """
        Merge two entities with full cascade.

        Returns: MergeResult with merge_id for undo
        """
        merge_id = ulid.new()

        async with db_conn.transaction():
            try:
                # STEP 1: Validate
                await self._validate_merge(
                    primary_entity_id,
                    secondary_entity_id,
                    db_conn,
                )

                # STEP 2: Select Primary (swap if secondary has more history)
                primary, secondary = await self._select_primary(
                    primary_entity_id,
                    secondary_entity_id,
                    db_conn,
                )

                # Capture snapshots for undo
                primary_snapshot = await self._snapshot_entity(primary.entity_id, db_conn)
                secondary_snapshot = await self._snapshot_entity(secondary.entity_id, db_conn)

                # STEP 3: Merge Attributes
                merged_attrs = await self._merge_attributes(primary, secondary, db_conn)

                # STEP 4: Cascade References
                cascade_counts = await self._cascade_update_references(
                    merge_id,
                    primary.entity_id,
                    secondary.entity_id,
                    db_conn,
                )

                # STEP 5: Archive Secondary
                await db_conn.execute(
                    """
                    UPDATE st_kg_dom
                    SET archival_status = 'MERGED',
                        merged_into = $1,
                        merged_at = $2,
                        merged_by = $3
                    WHERE entity_id = $4
                    """,
                    primary.entity_id,
                    now_ms(),
                    initiated_by,
                    secondary.entity_id,
                )

                # STEP 6: Log for Undo
                await self._log_merge(
                    merge_id,
                    primary.entity_id,
                    secondary.entity_id,
                    primary_snapshot,
                    secondary_snapshot,
                    cascade_counts,
                    merge_reason,
                    initiated_by,
                    db_conn,
                )

                return MergeResult(
                    merge_id=merge_id,
                    primary_entity_id=primary.entity_id,
                    secondary_entity_id=secondary.entity_id,
                    cascade_counts=cascade_counts,
                    success=True,
                )

            except Exception as e:
                logger.error(f"Merge failed: {e}")
                return MergeResult(
                    merge_id=merge_id,
                    primary_entity_id=primary_entity_id,
                    secondary_entity_id=secondary_entity_id,
                    cascade_counts={},
                    success=False,
                    error=str(e),
                )

    async def _validate_merge(
        self,
        primary_id: str,
        secondary_id: str,
        db_conn,
    ):
        """Validate merge is possible."""
        # Check both exist
        primary = await db_conn.fetchrow(
            "SELECT * FROM st_kg_dom WHERE entity_id = $1",
            primary_id,
        )
        secondary = await db_conn.fetchrow(
            "SELECT * FROM st_kg_dom WHERE entity_id = $1",
            secondary_id,
        )

        if not primary:
            raise ValueError(f"Primary entity {primary_id} not found")
        if not secondary:
            raise ValueError(f"Secondary entity {secondary_id} not found")

        # Check not already merged
        if primary["archival_status"] == "MERGED":
            raise ValueError(f"Primary entity {primary_id} already merged")
        if secondary["archival_status"] == "MERGED":
            raise ValueError(f"Secondary entity {secondary_id} already merged")

        # Check same entity type
        if primary["entity_type"] != secondary["entity_type"]:
            raise ValueError(
                f"Entity types don't match: {primary['entity_type']} vs {secondary['entity_type']}"
            )

    async def _cascade_update_references(
        self,
        merge_id: str,
        primary_id: str,
        secondary_id: str,
        db_conn,
    ) -> Dict[str, int]:
        """
        Update all references from secondary to primary.

        Returns: counts of updates per table
        """
        counts = {}

        # 1. st_kg_edges: source references
        result = await db_conn.execute(
            """
            UPDATE st_kg_edges
            SET source_entity_id = $1,
                merge_cascade_id = $2,
                updated_at = $4
            WHERE source_entity_id = $3
            """,
            primary_id, merge_id, secondary_id, now_ms(),
        )
        counts["kg_edges_source"] = int(result.split()[-1])

        # 2. st_kg_edges: target references
        result = await db_conn.execute(
            """
            UPDATE st_kg_edges
            SET target_entity_id = $1,
                merge_cascade_id = $2,
                updated_at = $4
            WHERE target_entity_id = $3
            """,
            primary_id, merge_id, secondary_id, now_ms(),
        )
        counts["kg_edges_target"] = int(result.split()[-1])

        # 3. st_hipp_events: JSON entity replacement
        result = await db_conn.execute(
            """
            UPDATE st_hipp_events
            SET entities_json = REPLACE(entities_json::text, $1, $2)::jsonb,
                merge_cascade_id = $3,
                updated_at = $4
            WHERE entities_json::text LIKE $5
            """,
            secondary_id, primary_id, merge_id, now_ms(),
            f"%{secondary_id}%",
        )
        counts["hipp_events"] = int(result.split()[-1])

        # 4. st_epi: Episode entity links
        result = await db_conn.execute(
            """
            UPDATE st_epi
            SET entity_ids = array_replace(entity_ids, $1, $2),
                merge_cascade_id = $3,
                updated_at = $4
            WHERE $1 = ANY(entity_ids)
            """,
            secondary_id, primary_id, merge_id, now_ms(),
        )
        counts["epi"] = int(result.split()[-1])

        # 5. st_sem: Pattern entity links
        result = await db_conn.execute(
            """
            UPDATE st_sem
            SET entity_ids = array_replace(entity_ids, $1, $2),
                merge_cascade_id = $3,
                updated_at = $4
            WHERE $1 = ANY(entity_ids)
            """,
            secondary_id, primary_id, merge_id, now_ms(),
        )
        counts["sem"] = int(result.split()[-1])

        # 6. st_social: Actor references
        result = await db_conn.execute(
            """
            UPDATE st_social
            SET actor_id = $1,
                merge_cascade_id = $2,
                updated_at = $4
            WHERE actor_id = $3
            """,
            primary_id, merge_id, secondary_id, now_ms(),
        )
        counts["social"] = int(result.split()[-1])

        # 7. st_procedural: Habit participants
        result = await db_conn.execute(
            """
            UPDATE st_procedural
            SET participants = array_replace(participants, $1, $2),
                merge_cascade_id = $3,
                updated_at = $4
            WHERE $1 = ANY(participants)
            """,
            secondary_id, primary_id, merge_id, now_ms(),
        )
        counts["procedural"] = int(result.split()[-1])

        # 8. st_vec: Embedding metadata
        result = await db_conn.execute(
            """
            UPDATE st_vec
            SET metadata_json = jsonb_set(
                metadata_json,
                '{entity_id}',
                to_jsonb($1::text)
            ),
            merge_cascade_id = $2,
            updated_at = $4
            WHERE metadata_json->>'entity_id' = $3
            """,
            primary_id, merge_id, secondary_id, now_ms(),
        )
        counts["vec"] = int(result.split()[-1])

        return counts

    async def reverse_merge(
        self,
        merge_id: str,
        reversed_by: str,
        db_conn,
    ) -> bool:
        """
        Undo an entity merge.

        Returns: True if successful
        """
        # Fetch merge record
        merge = await db_conn.fetchrow(
            "SELECT * FROM st_entity_merges WHERE merge_id = $1",
            merge_id,
        )

        if not merge:
            raise ValueError(f"Merge {merge_id} not found")
        if merge["reversed_at"]:
            raise ValueError(f"Merge {merge_id} already reversed")

        secondary_id = merge["secondary_entity_id"]
        primary_id = merge["primary_entity_id"]

        async with db_conn.transaction():
            # Restore secondary entity
            await db_conn.execute(
                """
                UPDATE st_kg_dom
                SET archival_status = 'ACTIVE',
                    merged_into = NULL,
                    merged_at = NULL,
                    merged_by = NULL
                WHERE entity_id = $1
                """,
                secondary_id,
            )

            # Reverse cascade updates (tracked by merge_cascade_id)
            await db_conn.execute(
                """
                UPDATE st_kg_edges
                SET source_entity_id = $1
                WHERE merge_cascade_id = $2
                  AND source_entity_id = $3
                """,
                secondary_id, merge_id, primary_id,
            )

            await db_conn.execute(
                """
                UPDATE st_kg_edges
                SET target_entity_id = $1
                WHERE merge_cascade_id = $2
                  AND target_entity_id = $3
                """,
                secondary_id, merge_id, primary_id,
            )

            # Mark merge as reversed
            await db_conn.execute(
                """
                UPDATE st_entity_merges
                SET reversed_at = $1,
                    reversed_by = $2
                WHERE merge_id = $3
                """,
                now_ms(), reversed_by, merge_id,
            )

        return True
```

**Migration: st_entity_merges** (TO CREATE):

```python
# File: k0/db/alembic/versions/0058_st_entity_merges.py

def upgrade():
    op.create_table(
        'st_entity_merges',
        sa.Column('merge_id', sa.String(36), primary_key=True),
        sa.Column('primary_entity_id', sa.String(36), nullable=False),
        sa.Column('secondary_entity_id', sa.String(36), nullable=False),
        sa.Column('primary_snapshot', sa.Text, nullable=False),  # JSON
        sa.Column('secondary_snapshot', sa.Text, nullable=False),  # JSON
        sa.Column('cascade_counts', sa.Text, nullable=True),  # JSON
        sa.Column('merge_reason', sa.String(256), nullable=True),
        sa.Column('initiated_by', sa.String(36), nullable=False),
        sa.Column('merged_at', sa.BigInteger, nullable=False),
        sa.Column('reversed_at', sa.BigInteger, nullable=True),
        sa.Column('reversed_by', sa.String(36), nullable=True),
        sa.Column('space_id', sa.String(36), nullable=False),
    )
    op.create_index('ix_st_entity_merges_primary', 'st_entity_merges', ['primary_entity_id'])
    op.create_index('ix_st_entity_merges_secondary', 'st_entity_merges', ['secondary_entity_id'])
    op.create_index('ix_st_entity_merges_reversed', 'st_entity_merges', ['reversed_at'],
                    postgresql_where=text('reversed_at IS NOT NULL'))

    # Add merge_cascade_id to cascade tables
    for table in ['st_kg_edges', 'st_hipp_events', 'st_epi', 'st_sem',
                  'st_social', 'st_procedural', 'st_vec']:
        op.add_column(table, sa.Column('merge_cascade_id', sa.String(36), nullable=True))
```

**Configuration**:

| Config Key | Default | Purpose |
| ---------- | ------- | ------- |
| `P03_MERGE_CASCADE_BATCH_SIZE` | 1000 | Batch size for cascade updates |
| `P03_MERGE_UNDO_WINDOW_DAYS` | 30 | Days to keep undo data |

**Metrics**:

| Metric Name | Type | Description |
| ----------- | ---- | ----------- |
| `p03_entity_merges` | Counter | Merge operations by outcome |
| `p03_merge_cascade_rows` | Counter | Rows updated per table |
| `p03_merge_reversals` | Counter | Undo operations |

**Deliverables**:

- [ ] `MergeResult` dataclass with cascade counts
- [ ] `EntitySnapshot` dataclass for undo
- [ ] `EntityMerger` class in `entity_merger.py`
- [ ] `merge_entities()` with 6-step process
- [ ] `_validate_merge()` checking preconditions
- [ ] `_cascade_update_references()` updating 7 tables
- [ ] `reverse_merge()` for undo support
- [ ] Migration 0058_st_entity_merges.py
- [ ] merge_cascade_id column added to 7 tables

**Acceptance Criteria**:

- [ ] 6-step merge process executed atomically
- [ ] All 7 tables updated in cascade
- [ ] merge_cascade_id tracks affected rows
- [ ] Secondary entity marked as MERGED
- [ ] Snapshots captured for undo
- [ ] `reverse_merge()` restores secondary entity
- [ ] Cascade updates reversible via merge_cascade_id

**Test File**: `tests/k0/pipelines/p03/test_r4_entity_merger.py`

**Test Cases**:

1. `test_merge_validates_entities_exist` — Error if entity missing
2. `test_merge_validates_not_already_merged` — Error if already merged
3. `test_merge_validates_same_type` — Error if types differ
4. `test_merge_selects_primary_with_more_history` — Swaps if needed
5. `test_merge_cascades_kg_edges` — source/target updated
6. `test_merge_cascades_hipp_events` — entities_json updated
7. `test_merge_cascades_epi` — entity_ids array updated
8. `test_merge_cascades_all_seven_tables` — All tables updated
9. `test_merge_archives_secondary` — archival_status=MERGED
10. `test_merge_logs_for_undo` — st_entity_merges record created
11. `test_reverse_merge_restores` — Secondary restored to ACTIVE
12. `test_reverse_merge_fails_if_already_reversed` — Error on double undo

**Blocked By**: 4.4.5, 4.4.6

**Blocks**: 4.4.8

---

#### Issue 4.4.8 — Implement M21 KGConsolidator

**Status**: NOT_STARTED

**Spec Reference**:

- [Dossier §7.4.4](../pipelines/P03_consolidation_dossier_v2.md#744-m21-kgconsolidator) (lines 11310-11450) — M21 KGConsolidator
- [Dossier §4.5.2](../pipelines/P03_consolidation_dossier_v2.md#452-relationship-discovery) — Hebbian co-occurrence algorithm
- [Dossier §4.5.1](../pipelines/P03_consolidation_dossier_v2.md#451-entity-extraction) — Entity clustering input format

**Goal**: Orchestrate entity extraction, resolution, and relationship discovery.

**Problem Statement**:

> KGConsolidator is the main entry point for P03 consolidation. It:
>
> 1. Takes entity clusters from M22 EntityResolver
> 2. Creates or updates entities in the knowledge graph
> 3. Discovers relationships via Hebbian co-occurrence
> 4. Emits KGUpdate objects for persistence
>
> Relationships emerge from statistical co-occurrence (entities appearing together).
> Higher co-occurrence = higher confidence.

**KGUpdate Types** (from Dossier §7.4.4):

| Type | Description | Fields |
| ---- | ----------- | ------ |
| `CREATE_ENTITY` | New entity to add | entity_id, canonical_name, entity_type, aliases |
| `UPDATE_ENTITY` | Existing entity update | entity_id, merged_aliases, new_observations |
| `CREATE_EDGE` | New relationship | edge_id, source_id, target_id, relation_type, confidence |
| `UPDATE_EDGE` | Edge update | edge_id, observation_count, confidence |

**Hebbian Co-Occurrence Algorithm** (from Dossier §4.5.2):

```
For each pair of entities (A, B) in an event:
    co_occurrence[A][B] += 1

If co_occurrence[A][B] >= MIN_CO_OCCURRENCE (2):
    confidence = min(0.9, 0.3 + 0.1 * co_occurrences)
    Create or update RELATED_TO edge
```

**Implementation**:

```python
# File: k0/pipelines/p03/phases/r4_kg_consolidator.py
"""
R4 Phase - Knowledge Graph Consolidation.

M4 Epic 4.4: Implement R4 Phase for KG Entity Resolution and Edge Building.

This phase performs entity/relationship consolidation:
1. Extract entities from events using UltraBERT NER (4.4.1)
2. Disambiguate entities using per-type weights (4.4.2)
3. Resolve ambiguous mentions via context hierarchy (4.4.4)
4. Route through confidence bands with P06 gap emission (4.4.5)
5. Apply adaptive merge thresholds (4.4.6)
6. Merge entities with cascade support (4.4.7)
7. Discover relationships via Hebbian co-occurrence
8. Populate envelope.phases.r4_* outputs

References:
    - Dossier 4.5: R4 - Knowledge Graph Consolidation (NREM2-3)
    - Dossier 7.4.4: M21 KGConsolidator Module
    - M4 Execution: docs/TEMP_EXECUTION_DOCS/M4_EXECUTION.md Epic 4.4

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class KGUpdateType(Enum):
    """Types of knowledge graph updates."""
    CREATE_ENTITY = "CREATE_ENTITY"
    UPDATE_ENTITY = "UPDATE_ENTITY"
    CREATE_EDGE = "CREATE_EDGE"
    UPDATE_EDGE = "UPDATE_EDGE"


@dataclass
class KGUpdate:
    """
    Knowledge graph update operation.

    Spec: Dossier §7.4.4
    """
    update_type: KGUpdateType
    entity_id: Optional[str] = None
    edge_id: Optional[str] = None

    # For CREATE_ENTITY / UPDATE_ENTITY
    canonical_name: Optional[str] = None
    entity_type: Optional[str] = None
    aliases: List[str] = field(default_factory=list)
    new_observations: int = 0

    # For CREATE_EDGE / UPDATE_EDGE
    source_id: Optional[str] = None
    target_id: Optional[str] = None
    relation_type: Optional[str] = None
    confidence: float = 0.0
    observation_count: int = 0


@dataclass
class EntityCluster:
    """Cluster of resolved entity mentions."""
    cluster_id: str
    canonical_name: str
    entity_type: str
    mentions: List[str]  # Original text mentions
    observation_ids: List[str]  # Source event IDs
    confidence: float


class KGConsolidator:
    """
    M21 Knowledge Graph Consolidator.

    Spec: Dossier §7.4.4

    Orchestrates entity/relationship consolidation:
    1. Takes entity clusters from M22 EntityResolver
    2. Creates/updates entities in knowledge graph
    3. Discovers relationships via Hebbian co-occurrence
    4. Emits KGUpdate objects for persistence
    """

    # Minimum co-occurrences before creating relationship
    MIN_CO_OCCURRENCE = 2

    # Maximum relationship confidence
    MAX_CONFIDENCE = 0.9

    # Base confidence for relationship discovery
    BASE_CONFIDENCE = 0.3

    # Confidence increment per co-occurrence
    CONFIDENCE_INCREMENT = 0.1

    def __init__(
        self,
        entity_resolver,  # M22 EntityResolver
        entity_merger: "EntityMerger",  # From 4.4.7
        merge_thresholds: "AdaptiveMergeThresholds",  # From 4.4.6
        confidence_router: "ConfidenceRouter",  # From 4.4.5
    ):
        self.entity_resolver = entity_resolver
        self.entity_merger = entity_merger
        self.merge_thresholds = merge_thresholds
        self.confidence_router = confidence_router

    async def consolidate(
        self,
        clusters: List[EntityCluster],
        existing_kg: Dict[str, any],
        space_id: str,
        db_conn,
    ) -> List[KGUpdate]:
        """
        Main consolidation entry point.

        Args:
            clusters: Entity clusters from M22 EntityResolver
            existing_kg: Current knowledge graph state
            space_id: Space to consolidate in

        Returns:
            List of KGUpdate operations to apply
        """
        updates: List[KGUpdate] = []

        # Step 1: Process entity clusters → entity updates
        entity_updates = await self._process_entity_clusters(
            clusters, existing_kg, space_id, db_conn
        )
        updates.extend(entity_updates)

        # Step 2: Discover relationships via co-occurrence
        relationship_updates = await self._discover_relationships(
            clusters, existing_kg
        )
        updates.extend(relationship_updates)

        logger.info(
            f"Consolidation complete: {len(updates)} updates "
            f"({len(entity_updates)} entities, {len(relationship_updates)} relationships)"
        )

        return updates

    async def _process_entity_clusters(
        self,
        clusters: List[EntityCluster],
        existing_kg: Dict[str, any],
        space_id: str,
        db_conn,
    ) -> List[KGUpdate]:
        """
        Process entity clusters into entity updates.

        For each cluster:
        - Check if entity exists in KG
        - If exists and similar: UPDATE_ENTITY (merge aliases)
        - If exists and identical: UPDATE_ENTITY (increment observations)
        - If new: CREATE_ENTITY
        """
        updates = []

        for cluster in clusters:
            # Route through confidence bands first
            action = self.confidence_router.route(cluster.confidence)

            if action == "gap":
                # Low confidence: emit gap, don't consolidate
                await self.confidence_router.emit_gap_if_low_confidence(
                    cluster.cluster_id,
                    cluster.confidence,
                    cluster.entity_type,
                    {"mentions": cluster.mentions},
                    db_conn,
                )
                continue

            # Find existing entity match
            existing = self._find_existing_entity(
                cluster.canonical_name,
                cluster.entity_type,
                existing_kg,
            )

            if existing:
                # Check if should merge based on adaptive threshold
                threshold = self.merge_thresholds.get_threshold(cluster.entity_type)
                should_merge, _ = self.merge_thresholds.should_merge(
                    cluster.entity_type, cluster.confidence
                )

                if should_merge:
                    # Merge: update existing entity
                    updates.append(KGUpdate(
                        update_type=KGUpdateType.UPDATE_ENTITY,
                        entity_id=existing["entity_id"],
                        canonical_name=cluster.canonical_name,
                        entity_type=cluster.entity_type,
                        aliases=cluster.mentions,
                        new_observations=len(cluster.observation_ids),
                    ))
                else:
                    # Below threshold: create new entity, flag if in medium band
                    entity_id = ulid.new()
                    updates.append(KGUpdate(
                        update_type=KGUpdateType.CREATE_ENTITY,
                        entity_id=entity_id,
                        canonical_name=cluster.canonical_name,
                        entity_type=cluster.entity_type,
                        aliases=cluster.mentions,
                        new_observations=len(cluster.observation_ids),
                    ))

                    if action == "flag":
                        # Medium confidence: flag for review
                        await self.confidence_router.emit_gap_if_low_confidence(
                            cluster.cluster_id,
                            cluster.confidence,
                            cluster.entity_type,
                            {"mentions": cluster.mentions, "flagged_entity": entity_id},
                            db_conn,
                        )
            else:
                # New entity
                updates.append(KGUpdate(
                    update_type=KGUpdateType.CREATE_ENTITY,
                    entity_id=ulid.new(),
                    canonical_name=cluster.canonical_name,
                    entity_type=cluster.entity_type,
                    aliases=cluster.mentions,
                    new_observations=len(cluster.observation_ids),
                ))

        return updates

    async def _discover_relationships(
        self,
        clusters: List[EntityCluster],
        existing_kg: Dict[str, any],
    ) -> List[KGUpdate]:
        """
        Discover relationships via Hebbian co-occurrence.

        Spec: Dossier §4.5.2

        Algorithm:
        1. For each event, find all entity pairs
        2. Increment co-occurrence count
        3. If co-occurrence >= MIN_CO_OCCURRENCE, create/update edge

        Confidence formula:
            confidence = min(MAX_CONFIDENCE, BASE_CONFIDENCE + INCREMENT * co_occurrences)
            confidence = min(0.9, 0.3 + 0.1 * co_occurrences)
        """
        updates = []

        # Build co-occurrence matrix from cluster observation overlap
        co_occurrences: Dict[tuple, int] = {}

        # Group clusters by observation_id to find co-occurring entities
        obs_to_clusters: Dict[str, List[EntityCluster]] = {}
        for cluster in clusters:
            for obs_id in cluster.observation_ids:
                if obs_id not in obs_to_clusters:
                    obs_to_clusters[obs_id] = []
                obs_to_clusters[obs_id].append(cluster)

        # Count co-occurrences
        for obs_id, obs_clusters in obs_to_clusters.items():
            if len(obs_clusters) < 2:
                continue

            # All pairs of entities in this observation
            for i, cluster_a in enumerate(obs_clusters):
                for cluster_b in obs_clusters[i + 1:]:
                    # Canonical pair key (ordered for consistency)
                    pair = tuple(sorted([cluster_a.cluster_id, cluster_b.cluster_id]))
                    co_occurrences[pair] = co_occurrences.get(pair, 0) + 1

        # Generate relationship updates
        for (cluster_a_id, cluster_b_id), count in co_occurrences.items():
            if count < self.MIN_CO_OCCURRENCE:
                continue

            # Calculate confidence
            confidence = min(
                self.MAX_CONFIDENCE,
                self.BASE_CONFIDENCE + self.CONFIDENCE_INCREMENT * count
            )

            # Check if edge exists
            edge_key = f"{cluster_a_id}:{cluster_b_id}"
            existing_edge = existing_kg.get("edges", {}).get(edge_key)

            if existing_edge:
                # Update existing edge
                updates.append(KGUpdate(
                    update_type=KGUpdateType.UPDATE_EDGE,
                    edge_id=existing_edge["edge_id"],
                    source_id=cluster_a_id,
                    target_id=cluster_b_id,
                    relation_type="RELATED_TO",
                    confidence=confidence,
                    observation_count=existing_edge["observation_count"] + count,
                ))
            else:
                # Create new edge
                updates.append(KGUpdate(
                    update_type=KGUpdateType.CREATE_EDGE,
                    edge_id=ulid.new(),
                    source_id=cluster_a_id,
                    target_id=cluster_b_id,
                    relation_type="RELATED_TO",
                    confidence=confidence,
                    observation_count=count,
                ))

        return updates

    def _find_existing_entity(
        self,
        canonical_name: str,
        entity_type: str,
        existing_kg: Dict[str, any],
    ) -> Optional[Dict]:
        """
        Find existing entity in knowledge graph by name and type.

        Returns: Entity dict if found, None otherwise
        """
        entities = existing_kg.get("entities", {})

        for entity_id, entity in entities.items():
            if entity.get("entity_type") != entity_type:
                continue

            # Check canonical name match
            if entity.get("canonical_name", "").lower() == canonical_name.lower():
                return entity

            # Check alias match
            aliases = entity.get("aliases", [])
            if any(a.lower() == canonical_name.lower() for a in aliases):
                return entity

        return None
```

**Configuration**:

| Config Key | Default | Purpose |
| ---------- | ------- | ------- |
| `P03_MIN_CO_OCCURRENCE` | 2 | Min observations before relationship |
| `P03_MAX_RELATIONSHIP_CONFIDENCE` | 0.9 | Confidence cap |
| `P03_BASE_CONFIDENCE` | 0.3 | Starting relationship confidence |
| `P03_CONFIDENCE_INCREMENT` | 0.1 | Confidence per co-occurrence |

**Metrics**:

| Metric Name | Type | Description |
| ----------- | ---- | ----------- |
| `p03_consolidation_runs` | Counter | Consolidation invocations |
| `p03_entity_updates` | Counter | Entity updates by type |
| `p03_relationship_discoveries` | Counter | Relationships discovered |
| `p03_co_occurrence_pairs` | Histogram | Co-occurrence pair counts |

**Dependencies**:

| Component | From Issue | Purpose |
| --------- | ---------- | ------- |
| `ConfidenceRouter` | 4.4.5 | Low-confidence gap emission |
| `AdaptiveMergeThresholds` | 4.4.6 | Per-type threshold decisions |
| `EntityMerger` | 4.4.7 | Entity merge cascade |

**Deliverables**:

- [ ] `R4Config` dataclass for phase configuration
- [ ] `R4PhaseStats` dataclass for execution statistics
- [ ] `KGUpdateType` enum with 4 values
- [ ] `KGUpdate` dataclass with all fields
- [ ] `EntityCluster` dataclass for input
- [ ] `R4KGConsolidator` class in `k0/pipelines/p03/phases/r4_kg_consolidator.py`
- [ ] `should_skip(envelope)` method
- [ ] `idempotency_key(envelope)` method
- [ ] `run(envelope, ctx)` async method returning P03PhaseResult
- [ ] `_extract_entities()` using UltraBERTEntityExtractor
- [ ] `_process_entity_clusters()` with confidence routing
- [ ] `_discover_relationships()` with Hebbian algorithm
- [ ] `_populate_phase_outputs()` to update envelope.phases.r4_*
- [ ] Factory function `create_r4_phase(config)`

**Acceptance Criteria**:

- [ ] Consolidation produces CREATE_ENTITY for new entities
- [ ] Consolidation produces UPDATE_ENTITY for existing matches
- [ ] Low-confidence clusters emit gaps, not entities
- [ ] Medium-confidence creates + flags for review
- [ ] Co-occurrence >= 2 creates RELATED_TO edge
- [ ] Confidence formula: min(0.9, 0.3 + 0.1 * count)
- [ ] Existing edges updated with new observation counts
- [ ] Integration with 4.4.5-4.4.7 components verified

**Test File**: `tests/k0/pipelines/p03/test_r4_kg_consolidator.py`

**Test Cases**:

1. `test_consolidate_creates_new_entity` — New cluster → CREATE_ENTITY
2. `test_consolidate_updates_existing_entity` — Matched cluster → UPDATE_ENTITY
3. `test_consolidate_low_confidence_emits_gap` — <0.60 → gap, no entity
4. `test_consolidate_medium_confidence_flags` — 0.60-0.85 → create + flag
5. `test_discover_relationships_min_co_occurrence` — Only count >= 2
6. `test_discover_relationships_confidence_formula` — 2 co-occ → 0.5 confidence
7. `test_discover_relationships_caps_confidence` — 10 co-occ → 0.9 (capped)
8. `test_discover_relationships_creates_edge` — New pair → CREATE_EDGE
9. `test_discover_relationships_updates_edge` — Existing pair → UPDATE_EDGE
10. `test_find_existing_entity_by_canonical` — Matches canonical_name
11. `test_find_existing_entity_by_alias` — Matches alias
12. `test_integration_with_confidence_router` — ConfidenceRouter injected
13. `test_integration_with_merge_thresholds` — AdaptiveMergeThresholds used

**Blocked By**: 4.4.5, 4.4.6, 4.4.7

**Blocks**: 4.4.9

---

#### Issue 4.4.9 — Implement Granger causality inference

**Status**: NOT_STARTED

**Spec Reference**:

- [Dossier §4.5.4](../pipelines/P03_consolidation_dossier_v2.md#454-causal-inference) (lines 4898-5000) — Causal Inference
- [Appendix C.5.2](../pipelines/P03_consolidation_dossier_v2.md#c52-granger-causality) (lines 24485-24650) — Granger Causality Algorithm

**Goal**: Infer causal direction for temporal relationships.

**Problem Statement**:

> Co-occurring entities (from Hebbian learning) may have causal relationships.
> If A consistently precedes B in time, A may cause B.
>
> Example: "Coffee" → "Work start" (0.82 precedence) suggests Coffee CAUSES Work_start.
>
> Granger causality uses temporal precedence to distinguish causation from correlation.

**Precedence Ratio Formula** (from Dossier §4.5.4):

```
precedence_ratio = a_before_b / (a_before_b + b_before_a + simultaneous)
```

Where:

- `a_before_b`: Count of times A precedes B (within time window)
- `b_before_a`: Count of times B precedes A
- `simultaneous`: Count of co-occurrences within 1 minute

**Implementation**:

```python
# File: k0/modules/consolidation/algorithms/granger_causality.py

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class CausalEdge:
    """Inferred causal relationship."""
    source_id: str
    target_id: str
    relation_type: str  # 'CAUSES'
    confidence: float
    observation_count: int
    precedence_ratio: float


@dataclass
class CausalityConfig:
    """Configuration for causality inference."""
    min_observations: int = 5
    causality_threshold: float = 0.75
    temporal_window_minutes: int = 60
    simultaneous_threshold_minutes: int = 1


@dataclass
class TemporalPrecedenceStats:
    """Statistics from temporal precedence analysis."""
    a_before_b: int
    b_before_a: int
    simultaneous: int
    total: int
    precedence_ratio: float


class GrangerCausalityInference:
    """
    Simplified Granger causality for temporal event patterns.

    Spec: Dossier Appendix C.5.2

    Principle: If A consistently precedes B, and removing A
    reduces predictability of B, then A Granger-causes B.

    Simplified for FamilyOS: Use co-occurrence frequency
    with temporal ordering to infer causal direction.
    """

    def __init__(self, config: Optional[CausalityConfig] = None):
        self.config = config or CausalityConfig()

    def compute_temporal_precedence(
        self,
        entity_a: str,
        entity_b: str,
        observations: List[Tuple[int, int]],  # (timestamp_a, timestamp_b)
    ) -> TemporalPrecedenceStats:
        """
        Compute temporal precedence statistics.

        Args:
            entity_a: First entity ID
            entity_b: Second entity ID
            observations: List of (ts_a, ts_b) timestamp pairs

        Returns:
            TemporalPrecedenceStats with counts and ratio
        """
        a_before_b = 0
        b_before_a = 0
        simultaneous = 0

        for ts_a, ts_b in observations:
            diff_minutes = (ts_b - ts_a) / 60000  # ms to minutes

            if abs(diff_minutes) < self.config.simultaneous_threshold_minutes:
                simultaneous += 1
            elif diff_minutes > 0:
                a_before_b += 1  # A happened first
            else:
                b_before_a += 1  # B happened first

        total = a_before_b + b_before_a + simultaneous
        precedence_ratio = a_before_b / total if total > 0 else 0.5

        return TemporalPrecedenceStats(
            a_before_b=a_before_b,
            b_before_a=b_before_a,
            simultaneous=simultaneous,
            total=total,
            precedence_ratio=precedence_ratio,
        )

    def infer_causal_direction(
        self,
        entity_a: str,
        entity_b: str,
        observations: List[Tuple[int, int]],
        config: Optional[CausalityConfig] = None,
    ) -> Optional[CausalEdge]:
        """
        Infer causal direction between entities.

        Args:
            entity_a: First entity ID
            entity_b: Second entity ID
            observations: List of (ts_a, ts_b) timestamp pairs
            config: Optional override config

        Returns:
            CausalEdge if strong temporal pattern found, None otherwise
        """
        cfg = config or self.config

        if len(observations) < cfg.min_observations:
            logger.debug(
                f"Insufficient observations for {entity_a} → {entity_b}: "
                f"{len(observations)} < {cfg.min_observations}"
            )
            return None

        stats = self.compute_temporal_precedence(entity_a, entity_b, observations)

        # Strong precedence = likely causal
        if stats.precedence_ratio >= cfg.causality_threshold:
            # A likely causes B
            return CausalEdge(
                source_id=entity_a,
                target_id=entity_b,
                relation_type='CAUSES',
                confidence=stats.precedence_ratio,
                observation_count=len(observations),
                precedence_ratio=stats.precedence_ratio,
            )

        elif stats.precedence_ratio <= (1 - cfg.causality_threshold):
            # B likely causes A (reverse direction)
            return CausalEdge(
                source_id=entity_b,
                target_id=entity_a,
                relation_type='CAUSES',
                confidence=1 - stats.precedence_ratio,
                observation_count=len(observations),
                precedence_ratio=1 - stats.precedence_ratio,
            )

        # No clear causal direction (correlation only)
        logger.debug(
            f"No causal direction for {entity_a} ↔ {entity_b}: "
            f"ratio={stats.precedence_ratio:.2f} (threshold={cfg.causality_threshold})"
        )
        return None

    async def analyze_cooccurrence_pairs(
        self,
        cooccurrence_pairs: List[Tuple[str, str]],
        observation_store,
        db_conn,
    ) -> List[CausalEdge]:
        """
        Analyze all co-occurrence pairs for causality.

        Args:
            cooccurrence_pairs: Entity ID pairs from Hebbian learning
            observation_store: Source of timestamp observations
            db_conn: Database connection

        Returns:
            List of inferred CausalEdge objects
        """
        causal_edges = []

        for entity_a, entity_b in cooccurrence_pairs:
            # Fetch temporal observations for this pair
            observations = await observation_store.get_cooccurrence_timestamps(
                entity_a, entity_b, db_conn
            )

            edge = self.infer_causal_direction(entity_a, entity_b, observations)
            if edge:
                causal_edges.append(edge)

        logger.info(
            f"Granger causality: {len(causal_edges)} causal edges "
            f"from {len(cooccurrence_pairs)} pairs"
        )

        return causal_edges

    async def persist_causal_edges(
        self,
        causal_edges: List[CausalEdge],
        space_id: str,
        db_conn,
    ) -> int:
        """
        Persist inferred causal edges to st_kg_edges.

        Returns: count of edges created/updated
        """
        count = 0

        for edge in causal_edges:
            # Check if edge already exists
            existing = await db_conn.fetchrow(
                """
                SELECT edge_id, observation_count FROM st_kg_edges
                WHERE source_entity_id = $1
                  AND target_entity_id = $2
                  AND relation_type = 'CAUSES'
                """,
                edge.source_id, edge.target_id,
            )

            if existing:
                # Update existing edge
                await db_conn.execute(
                    """
                    UPDATE st_kg_edges
                    SET causal_confidence = $1,
                        observation_count = $2,
                        precedence_ratio = $3,
                        updated_at = $4
                    WHERE edge_id = $5
                    """,
                    edge.confidence,
                    edge.observation_count,
                    edge.precedence_ratio,
                    now_ms(),
                    existing['edge_id'],
                )
            else:
                # Create new causal edge
                await db_conn.execute(
                    """
                    INSERT INTO st_kg_edges (
                        edge_id, source_entity_id, target_entity_id,
                        relation_type, edge_type, causal_confidence,
                        observation_count, precedence_ratio,
                        space_id, created_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """,
                    ulid.new(),
                    edge.source_id,
                    edge.target_id,
                    'CAUSES',
                    'CAUSAL',
                    edge.confidence,
                    edge.observation_count,
                    edge.precedence_ratio,
                    space_id,
                    now_ms(),
                )
            count += 1

        return count
```

**Configuration**:

| Config Key | Default | Purpose |
| ---------- | ------- | ------- |
| `P03_GRANGER_MIN_OBSERVATIONS` | 5 | Min observations for inference |
| `P03_GRANGER_CAUSALITY_THRESHOLD` | 0.75 | Default precedence threshold |
| `P03_GRANGER_TEMPORAL_WINDOW_MINUTES` | 60 | Max time gap for causal pair |
| `P03_GRANGER_SIMULTANEOUS_MINUTES` | 1 | Within this = simultaneous |

**Metrics**:

| Metric Name | Type | Description |
| ----------- | ---- | ----------- |
| `p03_granger_pairs_analyzed` | Counter | Co-occurrence pairs analyzed |
| `p03_granger_causal_edges_created` | Counter | Causal edges inferred |
| `p03_granger_precedence_ratio` | Histogram | Distribution of ratios |

**Causal Pattern Examples** (from Dossier C.5.2):

| Pattern | Precedence Ratio | Inferred Edge |
| ------- | --------------- | ------------- |
| "Alarm" always before "Wake up" | 0.95 | Alarm CAUSES Wake_up |
| "Coffee" before "Work start" | 0.82 | Coffee CAUSES Work_start |
| "Exercise" before "Good mood" | 0.78 | Exercise CAUSES Good_mood |
| "Rain" mixed with "Stay home" | 0.55 | No causal edge (correlation only) |

**Deliverables**:

- [ ] `CausalEdge` dataclass with precedence_ratio
- [ ] `CausalityConfig` dataclass with thresholds
- [ ] `TemporalPrecedenceStats` dataclass
- [ ] `GrangerCausalityInference` class in `granger_causality.py`
- [ ] `compute_temporal_precedence()` with formula
- [ ] `infer_causal_direction()` with min_observations check
- [ ] `analyze_cooccurrence_pairs()` batch processing
- [ ] `persist_causal_edges()` to st_kg_edges

**Acceptance Criteria**:

- [ ] Precedence ratio formula: a_before_b / (a + b + simultaneous)
- [ ] Returns None if observations < min_observations (5)
- [ ] Returns CausalEdge if ratio >= threshold (0.75)
- [ ] Reverse direction detected if ratio <= 0.25
- [ ] Simultaneous events counted separately (within 1 min)
- [ ] Persists edges with relation_type='CAUSES'
- [ ] Updates existing edges if already present

**Test File**: `tests/k0/pipelines/p03/test_r4_granger_causality.py`

**Test Cases**:

1. `test_compute_precedence_a_before_b` — Clear A→B pattern
2. `test_compute_precedence_b_before_a` — Clear B→A pattern
3. `test_compute_precedence_simultaneous` — Within 1 min = simultaneous
4. `test_infer_causal_no_observations` — <5 obs → None
5. `test_infer_causal_strong_precedence` — 0.95 ratio → CausalEdge
6. `test_infer_causal_weak_precedence` — 0.55 ratio → None
7. `test_infer_causal_reverse_direction` — 0.20 ratio → B CAUSES A
8. `test_persist_creates_new_edge` — New edge inserted
9. `test_persist_updates_existing_edge` — Existing edge updated
10. `test_batch_analysis` — Multiple pairs processed

**Blocked By**: 4.4.8

**Blocks**: 4.4.10, 4.4.11

---

#### Issue 4.4.10 — Implement adaptive causality thresholds by category

**Status**: NOT_STARTED

**Spec Reference**:

- [Dossier §4.5.4.1](../pipelines/P03_consolidation_dossier_v2.md#4541-adaptive-causality-thresholds) (lines 4904-5100) — Adaptive Causality Thresholds

**Goal**: Apply different precedence thresholds based on decision stakes.

**Problem Statement** (from Dossier §4.5.4.1):

> Fixed precedence ratio threshold (0.75) doesn't account for decision stakes:
>
> - **Health/Medical decisions**: Wrong causal inference could harm health → need strong evidence (0.85+)
> - **Financial decisions**: Important but reversible → need moderate evidence (0.80)
> - **Social/Routine patterns**: Low stakes → can accept weaker evidence (0.70)
> - **Preference/Habit patterns**: Personal, flexible → lowest bar (0.65)
>
> Human Memory Model: We're more cautious about medical causation ("Does X cause my symptoms?")
> than social patterns ("Do I usually call Mom on Sundays?"). Stakes vary by domain.

**Per-Category Threshold Matrix** (from Dossier):

| Category | Default | Min | Max | Rationale |
| -------- | ------- | --- | --- | --------- |
| `Health/Medical` | 0.85 | 0.80 | 0.95 | High stakes, strong evidence required |
| `Financial` | 0.80 | 0.75 | 0.90 | Important decisions, moderate risk |
| `Social/Routine` | 0.70 | 0.60 | 0.80 | Lower stakes, relationship patterns |
| `Preference/Habit` | 0.65 | 0.55 | 0.75 | Personal patterns, very flexible |

**Category Keywords** (from Dossier):

| Category | Keywords |
| -------- | -------- |
| Health/Medical | medication, symptom, treatment, doctor, health, pain, illness, diagnosis, therapy, exercise |
| Financial | money, budget, spending, purchase, cost, expense, payment, transaction, bill, salary |
| Social/Routine | call, visit, meeting, conversation, message, friend, family, colleague, social, gathering |
| Preference/Habit | (default for other patterns) |

**Implementation**:

```python
# File: k0/modules/consolidation/algorithms/causality_thresholds.py

from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class CausalityCategory(Enum):
    """Categories for causality threshold lookup."""
    HEALTH_MEDICAL = "Health/Medical"
    FINANCIAL = "Financial"
    SOCIAL_ROUTINE = "Social/Routine"
    PREFERENCE_HABIT = "Preference/Habit"


@dataclass
class CategoryThresholdBounds:
    """Threshold bounds for a causality category."""
    default: float
    min_value: float
    max_value: float


# Category keyword sets for classification
CATEGORY_KEYWORDS: Dict[CausalityCategory, set] = {
    CausalityCategory.HEALTH_MEDICAL: {
        'medication', 'symptom', 'treatment', 'doctor', 'health',
        'pain', 'illness', 'diagnosis', 'therapy', 'exercise',
        'hospital', 'medicine', 'prescription', 'allergy', 'condition'
    },
    CausalityCategory.FINANCIAL: {
        'money', 'budget', 'spending', 'purchase', 'cost',
        'expense', 'payment', 'transaction', 'bill', 'salary',
        'bank', 'investment', 'loan', 'credit', 'income'
    },
    CausalityCategory.SOCIAL_ROUTINE: {
        'call', 'visit', 'meeting', 'conversation', 'message',
        'friend', 'family', 'colleague', 'social', 'gathering',
        'party', 'dinner', 'lunch', 'appointment', 'schedule'
    },
}


class CausalCategoryClassifier:
    """
    Classify relationship into causality category.

    Spec: Dossier §4.5.4.1
    """

    def classify(
        self,
        source_entity_name: str,
        target_entity_name: str,
        relationship_type: str,
    ) -> CausalityCategory:
        """
        Determine causality category for relationship.

        Returns: CausalityCategory enum value
        """
        # Combine text for keyword matching
        text = f"{source_entity_name} {target_entity_name} {relationship_type}".lower()

        # Check categories in priority order (highest stakes first)
        if any(kw in text for kw in CATEGORY_KEYWORDS[CausalityCategory.HEALTH_MEDICAL]):
            return CausalityCategory.HEALTH_MEDICAL

        if any(kw in text for kw in CATEGORY_KEYWORDS[CausalityCategory.FINANCIAL]):
            return CausalityCategory.FINANCIAL

        if any(kw in text for kw in CATEGORY_KEYWORDS[CausalityCategory.SOCIAL_ROUTINE]):
            return CausalityCategory.SOCIAL_ROUTINE

        # Default: personal preference/habit patterns
        return CausalityCategory.PREFERENCE_HABIT


class AdaptiveCausalityThresholds:
    """
    Per-category causality thresholds with learning.

    Spec: Dossier §4.5.4.1

    Features:
    - Per-category default thresholds
    - Learning from prediction outcomes
    - Bounded adjustment range per category
    """

    # Default thresholds by category
    DEFAULT_THRESHOLDS: Dict[CausalityCategory, CategoryThresholdBounds] = {
        CausalityCategory.HEALTH_MEDICAL: CategoryThresholdBounds(0.85, 0.80, 0.95),
        CausalityCategory.FINANCIAL: CategoryThresholdBounds(0.80, 0.75, 0.90),
        CausalityCategory.SOCIAL_ROUTINE: CategoryThresholdBounds(0.70, 0.60, 0.80),
        CausalityCategory.PREFERENCE_HABIT: CategoryThresholdBounds(0.65, 0.55, 0.75),
    }

    # Learning adjustments by feedback signal
    LEARNING_ADJUSTMENTS: Dict[str, float] = {
        "CAUSAL_PREDICTION_CONFIRMED": 0.0,     # Correct, no change
        "CAUSAL_PREDICTION_WRONG": +0.02,       # FP: stricter
        "USER_REJECTS_CAUSATION": +0.05,        # Strong FP: much stricter
        "MISSED_CAUSATION": -0.03,              # FN: looser
    }

    def __init__(
        self,
        classifier: Optional[CausalCategoryClassifier] = None,
        learned_thresholds: Optional[Dict[str, float]] = None,
    ):
        self.classifier = classifier or CausalCategoryClassifier()
        self._learned = learned_thresholds or {}

    def get_threshold(self, category: CausalityCategory) -> float:
        """
        Get current threshold for category.

        Checks learned overrides first, falls back to default.
        """
        key = self._threshold_key(category)
        if key in self._learned:
            return self._learned[key]
        return self.DEFAULT_THRESHOLDS[category].default

    async def should_create_causal_edge(
        self,
        source_entity_name: str,
        target_entity_name: str,
        precedence_ratio: float,
        observation_count: int,
    ) -> Tuple[bool, float, CausalityCategory]:
        """
        Determine if causal edge should be created.

        Returns: (should_create, confidence, category)
        """
        # Classify relationship category
        category = self.classifier.classify(
            source_entity_name,
            target_entity_name,
            relationship_type='causal',
        )

        # Get learned threshold for category
        threshold = self.get_threshold(category)

        # Check if precedence ratio exceeds threshold
        if precedence_ratio >= threshold:
            # Compute confidence based on margin above threshold
            margin = precedence_ratio - threshold
            confidence = min(1.0, 0.70 + (margin * 2.0))
            return (True, confidence, category)
        else:
            return (False, 0.0, category)

    def adjust_threshold(
        self,
        category: CausalityCategory,
        feedback_signal: str,
    ) -> float:
        """
        Adjust threshold based on feedback.

        Returns: new threshold (clamped to bounds)
        """
        current = self.get_threshold(category)
        bounds = self.DEFAULT_THRESHOLDS[category]

        adjustment = self.LEARNING_ADJUSTMENTS.get(feedback_signal, 0.0)
        new_threshold = current + adjustment

        # Clamp to category bounds
        new_threshold = max(bounds.min_value, min(bounds.max_value, new_threshold))

        # Store learned threshold
        key = self._threshold_key(category)
        self._learned[key] = new_threshold

        logger.info(
            f"Adjusted {category.value} threshold: {current:.2f} → {new_threshold:.2f} "
            f"(signal={feedback_signal})"
        )

        return new_threshold

    async def persist_threshold(
        self,
        category: CausalityCategory,
        db_conn,
    ):
        """Persist learned threshold to st_learned_weights."""
        key = self._threshold_key(category)
        value = self._learned.get(key)
        if value is None:
            return

        await db_conn.execute(
            """
            INSERT INTO st_learned_weights (
                param_id, param_key, param_scope, current_value, updated_at
            ) VALUES ($1, $2, 'global', $3, $4)
            ON CONFLICT (param_key, param_scope, COALESCE(scope_id, ''))
            DO UPDATE SET
                current_value = $3,
                prior_value = st_learned_weights.current_value,
                updated_at = $4
            """,
            ulid.new(), key, value, now_ms(),
        )

    @classmethod
    async def load_from_database(
        cls,
        db_conn,
    ) -> "AdaptiveCausalityThresholds":
        """Load learned thresholds from database."""
        rows = await db_conn.fetch(
            """
            SELECT param_key, current_value FROM st_learned_weights
            WHERE param_key LIKE 'causality_threshold_%'
              AND param_scope = 'global'
            """
        )

        learned = {row['param_key']: row['current_value'] for row in rows}
        return cls(learned_thresholds=learned)

    def _threshold_key(self, category: CausalityCategory) -> str:
        """Generate storage key for category threshold."""
        return f"causality_threshold_{category.value.replace('/', '_')}"
```

**Configuration**:

| Config Key | Default | Purpose |
| ---------- | ------- | ------- |
| `P03_CAUSALITY_THRESHOLD_HEALTH` | 0.85 | Default for Health/Medical |
| `P03_CAUSALITY_THRESHOLD_FINANCIAL` | 0.80 | Default for Financial |
| `P03_CAUSALITY_THRESHOLD_SOCIAL` | 0.70 | Default for Social/Routine |
| `P03_CAUSALITY_THRESHOLD_PREFERENCE` | 0.65 | Default for Preference/Habit |
| `P03_CAUSALITY_LEARNING_ENABLED` | TRUE | Enable adaptive learning |

**Metrics**:

| Metric Name | Type | Description |
| ----------- | ---- | ----------- |
| `p03_causal_edges_created` | Counter | Causal edges by category |
| `p03_causality_threshold_current` | Gauge | Current threshold by category |
| `p03_causal_prediction_accuracy` | Gauge | % of predictions confirmed |
| `p03_causality_false_positives` | Counter | Wrong predictions by category |

**Deliverables**:

- [ ] `CausalityCategory` enum with 4 values
- [ ] `CategoryThresholdBounds` dataclass
- [ ] `CATEGORY_KEYWORDS` dict for classification
- [ ] `CausalCategoryClassifier` with `classify()` method
- [ ] `AdaptiveCausalityThresholds` class
- [ ] `DEFAULT_THRESHOLDS` dict with bounds per category
- [ ] `get_threshold(category)` with learned override
- [ ] `should_create_causal_edge()` with category-specific threshold
- [ ] `adjust_threshold()` with learning signals
- [ ] `persist_threshold()` to st_learned_weights
- [ ] `load_from_database()` class method

**Acceptance Criteria**:

- [ ] Health/Medical default threshold is 0.85
- [ ] Financial default threshold is 0.80
- [ ] Social/Routine default threshold is 0.70
- [ ] Preference/Habit default threshold is 0.65
- [ ] CAUSAL_PREDICTION_WRONG raises threshold by 0.02
- [ ] USER_REJECTS_CAUSATION raises threshold by 0.05
- [ ] MISSED_CAUSATION lowers threshold by 0.03
- [ ] Thresholds clamped within category bounds
- [ ] Keywords correctly classify entities into categories

**Test File**: `tests/k0/pipelines/p03/test_r4_causality_thresholds.py`

**Test Cases**:

1. `test_classify_health_medical` — "medication" → Health/Medical
2. `test_classify_financial` — "budget" → Financial
3. `test_classify_social` — "meeting" → Social/Routine
4. `test_classify_default_preference` — Unknown → Preference/Habit
5. `test_health_high_threshold` — 0.85 default
6. `test_should_create_above_threshold` — 0.90 Health → True
7. `test_should_create_below_threshold` — 0.80 Health → False
8. `test_adjust_wrong_prediction` — +0.02 adjustment
9. `test_adjust_user_rejects` — +0.05 adjustment
10. `test_adjust_missed_causation` — -0.03 adjustment
11. `test_threshold_clamped_max` — Cannot exceed category max
12. `test_persist_and_load` — Round-trip to database

**Blocked By**: 4.4.9

**Blocks**: 4.4.11

---

#### Issue 4.4.11 — Implement edge demotion for contradicted relationships

**Status**: NOT_STARTED

**Spec Reference**:

- [Dossier §4.5.4.4](../pipelines/P03_consolidation_dossier_v2.md#4544-causal-edge-feedback) (lines 5676-5900) — Causal Edge Feedback
- [Dossier §4.5.4.3](../pipelines/P03_consolidation_dossier_v2.md#4543-confound-detection) (lines 5500-5660) — Confound Detection

**Goal**: Demote or archive edges when evidence contradicts.

**Problem Statement** (from Dossier §4.5.4.4):

> Causal edges are created with initial confidence, but need validation based on usage outcomes.
> If P04/K1 uses a causal edge for prediction and it's wrong, the edge should be demoted.
> If consistently accurate, confidence should increase.
>
> Human Memory Model: We update our mental causal models based on outcomes.
> "I thought coffee caused my productivity, but tracking shows it's the morning routine."

**Accuracy Thresholds & Actions** (from Dossier):

| 30-Day Accuracy | Action | Edge Status | Rationale |
| --------------- | ------ | ----------- | --------- |
| > 90% | Boost confidence +0.05 | `CAUSAL` (strong) | Consistently accurate |
| 70-90% | No change | `CAUSAL` (adequate) | Acceptable accuracy |
| 50-70% | Lower confidence -0.10 | `CAUSAL` (weak) | Below target, monitor |
| < 50% | Demote to `CORRELATED` | `CORRELATED` | More wrong than right |
| 0 predictions (90 days) | Archive | `ARCHIVED` | Unused, not valuable |

**Demotion Triggers**:

| Trigger | Source | Action |
| ------- | ------ | ------ |
| `CAUSAL_PREDICTION_WRONG` | K1 response corrected | Lower confidence |
| `USER_REJECTS_CAUSATION` | User explicit "X doesn't cause Y" | Raise threshold, lower confidence |
| Strong confounding (>50%) | Confound detection | Demote to `CORRELATED` |
| Simpson's paradox | Context analysis | Demote to `CONTEXT_DEPENDENT` |
| Unused 90 days | Staleness check | Archive |

**Implementation**:

```python
# File: k0/modules/consolidation/algorithms/edge_demotion.py

from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class EdgeStatus(Enum):
    """Edge type/status values."""
    CAUSAL = "CAUSAL"
    CORRELATED = "CORRELATED"
    CONTEXT_DEPENDENT = "CONTEXT_DEPENDENT"
    ARCHIVED = "ARCHIVED"


@dataclass
class DemotionResult:
    """Result of edge demotion evaluation."""
    edge_id: str
    action: str  # 'boost', 'maintain', 'lower', 'demote', 'archive'
    old_status: EdgeStatus
    new_status: EdgeStatus
    old_confidence: float
    new_confidence: float
    reason: str


class CausalEdgeFeedbackProcessor:
    """
    Process feedback for causal edges and adjust confidence.

    Spec: Dossier §4.5.4.4

    Features:
    - Track prediction accuracy per edge
    - Boost/lower confidence based on accuracy
    - Demote edges that are wrong more than right
    - Archive stale unused edges
    """

    # Accuracy thresholds
    ACCURACY_BOOST_THRESHOLD = 0.90   # Boost if >90%
    ACCURACY_ADEQUATE_THRESHOLD = 0.70  # Adequate if 70-90%
    ACCURACY_DEMOTE_THRESHOLD = 0.50   # Demote if <50%

    # Confidence adjustments
    BOOST_AMOUNT = 0.05
    LOWER_AMOUNT = 0.10

    # Staleness
    STALENESS_DAYS = 90
    MIN_FEEDBACK_SAMPLES = 5

    async def process_feedback(
        self,
        edge_id: str,
        feedback_signal: str,
        outcome_details: Dict[str, Any],
        db_conn,
    ) -> Optional[DemotionResult]:
        """
        Update causal edge based on usage feedback.

        Returns: DemotionResult if action taken
        """
        # Fetch edge
        edge = await db_conn.fetchrow(
            """
            SELECT * FROM st_kg_edges
            WHERE edge_id = $1 AND edge_type IN ('CAUSAL', 'CORRELATED')
            """,
            edge_id,
        )

        if not edge:
            return None

        # Record feedback in tracking table
        await self._record_feedback(edge_id, feedback_signal, outcome_details, db_conn)

        # Compute accuracy over last 30 days
        accuracy = await self._compute_accuracy(edge_id, days=30, db_conn=db_conn)

        # Determine action based on accuracy
        result = await self._evaluate_edge(edge, accuracy, db_conn)

        return result

    async def _record_feedback(
        self,
        edge_id: str,
        feedback_signal: str,
        outcome_details: Dict[str, Any],
        db_conn,
    ):
        """Record feedback in st_causal_feedback table."""
        import json
        await db_conn.execute(
            """
            INSERT INTO st_causal_feedback (
                feedback_id, edge_id, signal_type, source_system,
                prediction_context, actual_outcome, space_id, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            ulid.new(),
            edge_id,
            feedback_signal,
            outcome_details.get('source', 'K1'),
            json.dumps(outcome_details.get('prediction', {})),
            json.dumps(outcome_details.get('actual', {})),
            outcome_details.get('space_id', 'default'),
            now_ms(),
        )

    async def _compute_accuracy(
        self,
        edge_id: str,
        days: int,
        db_conn,
    ) -> float:
        """
        Compute prediction accuracy over time window.

        Returns: accuracy [0.0, 1.0]
        """
        cutoff_time = now_ms() - (days * 86400000)

        result = await db_conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE signal_type = 'CAUSAL_PREDICTION_CONFIRMED'
                ) as correct,
                COUNT(*) FILTER (
                    WHERE signal_type IN ('CAUSAL_PREDICTION_WRONG', 'USER_REJECTS_CAUSATION')
                ) as incorrect,
                COUNT(*) as total
            FROM st_causal_feedback
            WHERE edge_id = $1
              AND created_at >= $2
            """,
            edge_id, cutoff_time,
        )

        if result['total'] == 0:
            return 1.0  # No feedback yet, assume correct

        return result['correct'] / result['total']

    async def _evaluate_edge(
        self,
        edge: dict,
        accuracy: float,
        db_conn,
    ) -> DemotionResult:
        """Evaluate edge and apply action based on accuracy."""
        edge_id = edge['edge_id']
        old_confidence = edge.get('causal_confidence', 0.5)
        old_status = EdgeStatus(edge['edge_type'])

        # Check sample count for demotion protection
        sample_count = await self._get_sample_count(edge_id, 30, db_conn)

        if accuracy > self.ACCURACY_BOOST_THRESHOLD:
            # Boost confidence
            new_confidence = min(1.0, old_confidence + self.BOOST_AMOUNT)
            await self._update_edge_confidence(edge_id, new_confidence, db_conn)
            return DemotionResult(
                edge_id=edge_id,
                action='boost',
                old_status=old_status,
                new_status=old_status,
                old_confidence=old_confidence,
                new_confidence=new_confidence,
                reason=f"High accuracy ({accuracy:.2f})",
            )

        elif accuracy >= self.ACCURACY_ADEQUATE_THRESHOLD:
            # Maintain current state
            await self._update_last_validated(edge_id, db_conn)
            return DemotionResult(
                edge_id=edge_id,
                action='maintain',
                old_status=old_status,
                new_status=old_status,
                old_confidence=old_confidence,
                new_confidence=old_confidence,
                reason=f"Adequate accuracy ({accuracy:.2f})",
            )

        elif accuracy >= self.ACCURACY_DEMOTE_THRESHOLD:
            # Lower confidence but don't demote yet
            new_confidence = max(0.0, old_confidence - self.LOWER_AMOUNT)
            await self._update_edge_confidence(edge_id, new_confidence, db_conn)
            return DemotionResult(
                edge_id=edge_id,
                action='lower',
                old_status=old_status,
                new_status=old_status,
                old_confidence=old_confidence,
                new_confidence=new_confidence,
                reason=f"Below target accuracy ({accuracy:.2f})",
            )

        else:
            # Accuracy < 50%: demote to CORRELATED
            if sample_count < self.MIN_FEEDBACK_SAMPLES:
                # Not enough samples, don't demote yet
                return DemotionResult(
                    edge_id=edge_id,
                    action='maintain',
                    old_status=old_status,
                    new_status=old_status,
                    old_confidence=old_confidence,
                    new_confidence=old_confidence,
                    reason=f"Low accuracy but insufficient samples ({sample_count})",
                )

            await self._demote_edge(edge_id, 'LOW_ACCURACY', db_conn)
            return DemotionResult(
                edge_id=edge_id,
                action='demote',
                old_status=old_status,
                new_status=EdgeStatus.CORRELATED,
                old_confidence=old_confidence,
                new_confidence=0.0,
                reason=f"Demoted: accuracy {accuracy:.2f} < 0.50",
            )

    async def _demote_edge(
        self,
        edge_id: str,
        reason: str,
        db_conn,
    ):
        """Demote causal edge to CORRELATED."""
        import json
        await db_conn.execute(
            """
            UPDATE st_kg_edges
            SET edge_type = 'CORRELATED',
                metadata_json = jsonb_set(
                    COALESCE(metadata_json, '{}'::jsonb),
                    '{demotion_reason}',
                    to_jsonb($1::text)
                ),
                updated_at = $2
            WHERE edge_id = $3
            """,
            reason, now_ms(), edge_id,
        )

        # Emit demotion event
        logger.info(f"Demoted edge {edge_id} to CORRELATED: {reason}")

    async def _update_edge_confidence(
        self,
        edge_id: str,
        confidence: float,
        db_conn,
    ):
        """Update edge confidence."""
        await db_conn.execute(
            """
            UPDATE st_kg_edges
            SET causal_confidence = $1,
                last_validated_at = $2
            WHERE edge_id = $3
            """,
            confidence, now_ms(), edge_id,
        )

    async def _update_last_validated(self, edge_id: str, db_conn):
        """Update last validated timestamp."""
        await db_conn.execute(
            """
            UPDATE st_kg_edges
            SET last_validated_at = $1
            WHERE edge_id = $2
            """,
            now_ms(), edge_id,
        )

    async def _get_sample_count(
        self,
        edge_id: str,
        days: int,
        db_conn,
    ) -> int:
        """Get feedback sample count for edge."""
        cutoff_time = now_ms() - (days * 86400000)
        result = await db_conn.fetchval(
            """
            SELECT COUNT(*) FROM st_causal_feedback
            WHERE edge_id = $1 AND created_at >= $2
            """,
            edge_id, cutoff_time,
        )
        return result or 0


class CausalEdgeStalenessChecker:
    """
    Identify and archive unused causal edges.

    Spec: Dossier §4.5.4.4
    """

    STALENESS_DAYS = 90

    async def check_staleness(
        self,
        space_id: str,
        db_conn,
    ) -> List[str]:
        """
        Find causal edges not used in 90 days.

        Returns: List of stale edge_ids
        """
        cutoff_time = now_ms() - (self.STALENESS_DAYS * 86400000)

        stale_edges = await db_conn.fetch(
            """
            SELECT edge_id FROM st_kg_edges
            WHERE edge_type = 'CAUSAL'
              AND space_id = $1
              AND (last_used_at IS NULL OR last_used_at < $2)
            """,
            space_id, cutoff_time,
        )

        return [e['edge_id'] for e in stale_edges]

    async def archive_stale_edges(
        self,
        space_id: str,
        db_conn,
    ) -> int:
        """
        Archive causal edges unused for 90 days.

        Returns: count of archived edges
        """
        stale_edge_ids = await self.check_staleness(space_id, db_conn)

        if not stale_edge_ids:
            return 0

        result = await db_conn.execute(
            """
            UPDATE st_kg_edges
            SET archival_status = 'ARCHIVED',
                archived_at = $1
            WHERE edge_id = ANY($2)
            """,
            now_ms(), stale_edge_ids,
        )

        count = int(result.split()[-1])
        logger.info(f"Archived {count} stale causal edges in space {space_id}")
        return count
```

**Migration: st_causal_feedback** (TO CREATE):

```python
# File: k0/db/alembic/versions/0059_st_causal_feedback.py

def upgrade():
    op.create_table(
        'st_causal_feedback',
        sa.Column('feedback_id', sa.String(36), primary_key=True),
        sa.Column('edge_id', sa.String(36), nullable=False),
        sa.Column('signal_type', sa.String(64), nullable=False),
        sa.Column('source_system', sa.String(32), nullable=False),
        sa.Column('prediction_context', sa.Text, nullable=True),
        sa.Column('actual_outcome', sa.Text, nullable=True),
        sa.Column('user_id', sa.String(36), nullable=True),
        sa.Column('space_id', sa.String(36), nullable=False),
        sa.Column('created_at', sa.BigInteger, nullable=False),
    )
    op.create_index('ix_st_causal_feedback_edge', 'st_causal_feedback',
                    ['edge_id', 'created_at'])
    op.create_index('ix_st_causal_feedback_signal', 'st_causal_feedback',
                    ['signal_type'])

    # Add columns to st_kg_edges
    op.add_column('st_kg_edges',
                  sa.Column('last_used_at', sa.BigInteger, nullable=True))
    op.add_column('st_kg_edges',
                  sa.Column('last_validated_at', sa.BigInteger, nullable=True))
    op.add_column('st_kg_edges',
                  sa.Column('usage_count', sa.Integer, default=0))
    op.add_column('st_kg_edges',
                  sa.Column('prediction_accuracy', sa.Float, nullable=True))
```

**Configuration**:

| Config Key | Default | Purpose |
| ---------- | ------- | ------- |
| `P03_CAUSAL_ACCURACY_BOOST_THRESHOLD` | 0.90 | Boost confidence above |
| `P03_CAUSAL_ACCURACY_DEMOTE_THRESHOLD` | 0.70 | Demote below |
| `P03_CAUSAL_STALENESS_DAYS` | 90 | Archive if unused |
| `P03_CAUSAL_FEEDBACK_WINDOW_DAYS` | 30 | Accuracy window |
| `P03_CAUSAL_MIN_FEEDBACK_SAMPLES` | 5 | Min samples before demote |

**Metrics**:

| Metric Name | Type | Description |
| ----------- | ---- | ----------- |
| `p03_causal_feedback_received` | Counter | Feedback signals by type |
| `p03_causal_accuracy_avg` | Gauge | Average edge accuracy |
| `p03_causal_edges_demoted` | Counter | Edges demoted to CORRELATED |
| `p03_causal_edges_boosted` | Counter | Edges with boosted confidence |
| `p03_causal_edges_stale` | Gauge | Unused edges count |

**Deliverables**:

- [ ] `EdgeStatus` enum (CAUSAL, CORRELATED, CONTEXT_DEPENDENT, ARCHIVED)
- [ ] `DemotionResult` dataclass
- [ ] `CausalEdgeFeedbackProcessor` class
- [ ] `process_feedback()` main entry point
- [ ] `_compute_accuracy()` over 30-day window
- [ ] `_evaluate_edge()` with boost/maintain/lower/demote actions
- [ ] `_demote_edge()` changing edge_type to CORRELATED
- [ ] `CausalEdgeStalenessChecker` class
- [ ] `check_staleness()` finding unused edges
- [ ] `archive_stale_edges()` marking as ARCHIVED
- [ ] Migration 0059_st_causal_feedback.py

**Acceptance Criteria**:

- [ ] Accuracy >90% boosts confidence by 0.05
- [ ] Accuracy 70-90% maintains current state
- [ ] Accuracy 50-70% lowers confidence by 0.10
- [ ] Accuracy <50% demotes to CORRELATED
- [ ] Demotion requires minimum 5 feedback samples
- [ ] Stale edges (90 days unused) archived
- [ ] Feedback recorded in st_causal_feedback
- [ ] Event emitted on demotion: p03.causal_edge.demoted.v1

**Test File**: `tests/k0/pipelines/p03/test_r4_edge_demotion.py`

**Test Cases**:

1. `test_high_accuracy_boosts_confidence` — >90% → +0.05
2. `test_adequate_accuracy_maintains` — 70-90% → no change
3. `test_low_accuracy_lowers_confidence` — 50-70% → -0.10
4. `test_very_low_accuracy_demotes` — <50% → CORRELATED
5. `test_demotion_requires_min_samples` — <5 samples → no demote
6. `test_feedback_recorded` — Inserted to st_causal_feedback
7. `test_compute_accuracy` — Correct / total calculation
8. `test_staleness_check` — Finds edges unused 90 days
9. `test_archive_stale_edges` — Sets archival_status=ARCHIVED
10. `test_demotion_event_emitted` — Event published

**Blocked By**: 4.4.9, 4.4.10

**Blocks**: 4.4.12

---

#### Issue 4.4.12 — Unit + integration tests for R4 KG consolidation

**Status**: NOT_STARTED

**Spec Reference**:

- All R4 Issues (4.4.1-4.4.11)
- [Dossier §7.4.4](../pipelines/P03_consolidation_dossier_v2.md#744-m21-kgconsolidator) — M21 KGConsolidator
- [Dossier §4.5](../pipelines/P03_consolidation_dossier_v2.md#45-r4-knowledge-graph) — R4 Entity/Relationship Processing

**Goal**: Comprehensive test coverage for R4 KG consolidation phase.

**Test Structure**:

```
tests/k0/pipelines/p03/
├── test_r4_entity_extractor.py          # 4.4.1
├── test_r4_disambiguation_weights.py    # 4.4.2
├── test_r4_disambiguation_learning.py   # 4.4.3
├── test_r4_ambiguous_resolution.py      # 4.4.4
├── test_r4_confidence_bands.py          # 4.4.5
├── test_r4_merge_thresholds.py          # 4.4.6
├── test_r4_entity_merger.py             # 4.4.7
├── test_r4_kg_consolidator.py           # 4.4.8
├── test_r4_granger_causality.py         # 4.4.9
├── test_r4_causality_thresholds.py      # 4.4.10
├── test_r4_edge_demotion.py             # 4.4.11
└── test_r4_integration.py               # Integration tests
```

**Test Categories**:

| Category | Purpose | Coverage Target |
| -------- | ------- | --------------- |
| Unit Tests | Individual function/method testing | 80%+ |
| Integration Tests | Cross-component interaction | Key paths |
| Contract Tests | Schema/interface validation | All contracts |
| Performance Tests | Latency/throughput bounds | Critical paths |

**Integration Test Cases** (test_r4_integration.py):

```python
# File: tests/k0/pipelines/p03/test_r4_integration.py

import pytest
from unittest.mock import AsyncMock, MagicMock


class TestR4EntityExtractionPipeline:
    """Integration: Entity extraction → resolution → KG update."""

    @pytest.mark.asyncio
    async def test_full_entity_pipeline(self, db_conn, mock_ultrabert):
        """
        Test: Raw text → UltraBERT NER → Entity clusters → KG entities.

        Verifies:
        - NER extracts entities from all 3 heads
        - Entities clustered by similarity
        - High-confidence entities auto-resolved
        - Low-confidence entities emit gaps
        """
        # Arrange
        mock_ultrabert.return_value = {
            'ner_family': {'entities': [
                {'text': 'wife', 'label': 'KINSHIP', 'start_token': 2, 'end_token': 2}
            ]},
            'ner_general': {'entities': [
                {'text': 'costco', 'label': 'ORG', 'start_token': 5, 'end_token': 5}
            ]},
            'temporal': {'entities': [
                {'text': 'sunday', 'label': 'DATE_REL', 'start_token': 8, 'end_token': 8}
            ]},
        }

        # Act
        result = await run_r4_entity_pipeline(
            text="My wife went to costco on sunday",
            space_id="test_space",
            db_conn=db_conn,
        )

        # Assert
        assert len(result.entities_created) >= 2  # wife, costco
        assert any(e.entity_type == 'FAMILY_MEMBER' for e in result.entities_created)
        assert any(e.entity_type == 'ORGANIZATION' for e in result.entities_created)


class TestR4EntityMergePipeline:
    """Integration: Entity resolution → merge cascade."""

    @pytest.mark.asyncio
    async def test_merge_cascades_to_all_tables(self, db_conn, seeded_kg):
        """
        Test: Entity merge updates all 7 cascade tables.

        Verifies:
        - st_kg_edges redirected
        - st_hipp_events JSON updated
        - st_epi entity_ids updated
        - Secondary entity marked MERGED
        - Merge logged for undo
        """
        # Arrange: Two similar entities with references in multiple tables
        primary_id = seeded_kg['john_smith_id']
        secondary_id = seeded_kg['j_smith_id']

        # Act
        merger = EntityMerger()
        result = await merger.merge_entities(
            primary_entity_id=primary_id,
            secondary_entity_id=secondary_id,
            merge_reason="Same person confirmed",
            initiated_by="test_user",
            db_conn=db_conn,
        )

        # Assert
        assert result.success
        assert result.cascade_counts['kg_edges_source'] > 0
        assert result.cascade_counts['hipp_events'] >= 0

        # Verify secondary is merged
        secondary = await db_conn.fetchrow(
            "SELECT * FROM st_kg_dom WHERE entity_id = $1",
            secondary_id,
        )
        assert secondary['archival_status'] == 'MERGED'


class TestR4CausalInferencePipeline:
    """Integration: Co-occurrence → Granger → causal edges."""

    @pytest.mark.asyncio
    async def test_cooccurrence_to_causal_edge(self, db_conn, seeded_events):
        """
        Test: Hebbian co-occurrence → temporal analysis → CAUSES edge.

        Verifies:
        - Co-occurring entities detected
        - Temporal precedence computed
        - Category-specific threshold applied
        - CAUSES edge created with precedence_ratio
        """
        # Arrange: Events where "coffee" always precedes "work_start"
        coffee_id = seeded_events['coffee_id']
        work_id = seeded_events['work_start_id']

        # Act
        granger = GrangerCausalityInference()
        thresholds = AdaptiveCausalityThresholds()

        observations = await get_cooccurrence_timestamps(
            coffee_id, work_id, db_conn
        )

        edge = granger.infer_causal_direction(
            coffee_id, work_id, observations
        )

        # Assert
        assert edge is not None
        assert edge.relation_type == 'CAUSES'
        assert edge.precedence_ratio >= 0.75
        assert edge.source_id == coffee_id
        assert edge.target_id == work_id


class TestR4FeedbackLoop:
    """Integration: Causal prediction → feedback → threshold adjustment."""

    @pytest.mark.asyncio
    async def test_wrong_prediction_raises_threshold(self, db_conn, seeded_causal_edge):
        """
        Test: Wrong prediction → feedback → category threshold increases.

        Verifies:
        - Feedback recorded
        - Category threshold adjusted
        - Edge confidence lowered
        """
        # Arrange
        edge_id = seeded_causal_edge['edge_id']
        category = CausalityCategory.HEALTH_MEDICAL

        thresholds = await AdaptiveCausalityThresholds.load_from_database(db_conn)
        original_threshold = thresholds.get_threshold(category)

        # Act: Record wrong prediction
        processor = CausalEdgeFeedbackProcessor()
        await processor.process_feedback(
            edge_id=edge_id,
            feedback_signal='CAUSAL_PREDICTION_WRONG',
            outcome_details={'space_id': 'test_space'},
            db_conn=db_conn,
        )

        # Adjust threshold
        new_threshold = thresholds.adjust_threshold(
            category, 'CAUSAL_PREDICTION_WRONG'
        )

        # Assert
        assert new_threshold > original_threshold
        assert new_threshold == original_threshold + 0.02


class TestR4FullPhase:
    """Integration: Complete R4 phase execution."""

    @pytest.mark.asyncio
    async def test_r4_phase_end_to_end(self, db_conn, seeded_hipp_events):
        """
        Test: Full R4 phase processes events into KG.

        Verifies:
        - Entities extracted from events
        - Entities resolved and merged
        - Relationships discovered
        - Causal edges created
        - All within latency bounds
        """
        import time

        # Arrange
        event_ids = seeded_hipp_events['event_ids']

        # Act
        start = time.time()
        result = await execute_r4_phase(
            event_ids=event_ids,
            space_id='test_space',
            db_conn=db_conn,
        )
        elapsed = time.time() - start

        # Assert: Functional correctness
        assert result.entities_created > 0
        assert result.relationships_discovered >= 0
        assert result.gaps_emitted >= 0

        # Assert: Performance
        assert elapsed < 0.5  # <500ms for batch of 100 events
```

**Unit Test Summary by Issue**:

| Issue | Test File | Test Count | Key Assertions |
| ----- | --------- | ---------- | -------------- |
| 4.4.1 | test_r4_entity_extractor.py | 12 | 3-head parsing, label mapping, nickname normalization |
| 4.4.2 | test_r4_disambiguation_weights.py | 10 | Weight defaults, type-specific configs |
| 4.4.3 | test_r4_disambiguation_learning.py | 10 | Feedback signals, bounded adjustments |
| 4.4.4 | test_r4_ambiguous_resolution.py | 10 | Context hierarchy, P06 gap emission |
| 4.4.5 | test_r4_confidence_bands.py | 10 | Three-band routing, gap payloads |
| 4.4.6 | test_r4_merge_thresholds.py | 12 | Per-type thresholds, learning |
| 4.4.7 | test_r4_entity_merger.py | 12 | 6-step cascade, undo support |
| 4.4.8 | test_r4_kg_consolidator.py | 13 | Consolidate, Hebbian discovery |
| 4.4.9 | test_r4_granger_causality.py | 10 | Precedence formula, threshold check |
| 4.4.10 | test_r4_causality_thresholds.py | 12 | Category classification, learning |
| 4.4.11 | test_r4_edge_demotion.py | 10 | Accuracy actions, staleness |

**Total**: ~110 unit tests + ~10 integration tests

**Coverage Requirements**:

| Module | Target | Measured By |
| ------ | ------ | ----------- |
| `entity_extractor.py` | ≥80% | pytest-cov |
| `disambiguation_weights.py` | ≥80% | pytest-cov |
| `entity_merger.py` | ≥80% | pytest-cov |
| `m21_kg_consolidator.py` | ≥80% | pytest-cov |
| `granger_causality.py` | ≥80% | pytest-cov |
| `causality_thresholds.py` | ≥80% | pytest-cov |
| `edge_demotion.py` | ≥80% | pytest-cov |

**Performance Test Cases**:

| Test | Scenario | Bound |
| ---- | -------- | ----- |
| `test_entity_extraction_latency` | 100 events batch | <200ms |
| `test_entity_resolution_latency` | 500 entities | <100ms |
| `test_merge_cascade_latency` | 7-table cascade | <50ms |
| `test_r4_full_phase_latency` | 100 events end-to-end | <500ms |

**Fixtures Required**:

```python
# File: tests/k0/pipelines/p03/conftest.py

@pytest.fixture
async def seeded_kg(db_conn):
    """Seed KG with test entities and edges."""
    # Create test entities
    john_smith_id = ulid.new()
    j_smith_id = ulid.new()

    await db_conn.execute(...)

    return {
        'john_smith_id': john_smith_id,
        'j_smith_id': j_smith_id,
    }


@pytest.fixture
async def seeded_events(db_conn):
    """Seed hippocampal events for causality testing."""
    ...


@pytest.fixture
async def seeded_causal_edge(db_conn):
    """Seed causal edge for feedback testing."""
    ...


@pytest.fixture
def mock_ultrabert():
    """Mock UltraBERT model responses."""
    with patch('k0.modules.consolidation.ultrabert_client') as mock:
        yield mock
```

**Deliverables**:

- [ ] `test_r4_entity_extractor.py` — 12 tests for 4.4.1
- [ ] `test_r4_disambiguation_weights.py` — 10 tests for 4.4.2
- [ ] `test_r4_disambiguation_learning.py` — 10 tests for 4.4.3
- [ ] `test_r4_ambiguous_resolution.py` — 10 tests for 4.4.4
- [ ] `test_r4_confidence_bands.py` — 10 tests for 4.4.5
- [ ] `test_r4_merge_thresholds.py` — 12 tests for 4.4.6
- [ ] `test_r4_entity_merger.py` — 12 tests for 4.4.7
- [ ] `test_r4_kg_consolidator.py` — 13 tests for 4.4.8
- [ ] `test_r4_granger_causality.py` — 10 tests for 4.4.9
- [ ] `test_r4_causality_thresholds.py` — 12 tests for 4.4.10
- [ ] `test_r4_edge_demotion.py` — 10 tests for 4.4.11
- [ ] `test_r4_integration.py` — 10+ integration tests
- [ ] `conftest.py` fixtures for seeding
- [ ] Coverage report showing ≥80%

**Acceptance Criteria**:

- [ ] All 12 test files created
- [ ] ~120 total tests passing
- [ ] Coverage ≥80% for R4 modules
- [ ] Integration tests verify cross-component flows
- [ ] Performance tests within bounds
- [ ] No flaky tests (deterministic seeding)
- [ ] Tests run in <30 seconds total

**Blocked By**: 4.4.1-4.4.11

**Blocks**: Epic 4.4 completion

---

## Part E: Issue Summary Table

| Issue | Title | Status | Epic |
|-------|-------|--------|------|
| 4.1.1 | ImportanceScorer weighted-sum formula | NOT_STARTED | 4.1 |
| 4.1.2 | Factor audit logging | NOT_STARTED | 4.1 |
| 4.1.3 | HebbianLearner co-occurrence + edge weights | NOT_STARTED | 4.1 |
| 4.1.4 | Hebbian anti-decay + normalization | NOT_STARTED | 4.1 |
| 4.1.5 | Closed-loop importance weight learning | NOT_STARTED | 4.1 |
| 4.1.6 | Cold start strategy | NOT_STARTED | 4.1 |
| 4.1.7 | R1 metrics | NOT_STARTED | 4.1 |
| 4.1.8 | R1 tests | COMPLETED | 4.1 |
| 4.2.1 | Composite distance function | COMPLETED | 4.2 |
| 4.2.2 | Pre-clustering episode split | COMPLETED | 4.2 |
| 4.2.3 | DBSCAN clustering | COMPLETED | 4.2 |
| 4.2.4 | Episode candidates to staged writes | COMPLETED | 4.2 |
| 4.2.5 | Adaptive eps learning | COMPLETED | 4.2 |
| 4.2.6 | Adaptive min_samples learning | COMPLETED | 4.2 |
| 4.2.7 | Cluster quality metrics | COMPLETED | 4.2 |
| 4.2.8 | R2 tests | COMPLETED | 4.2 |
| 4.3.1 | SimHash fingerprinting | NOT_STARTED | 4.3 |
| 4.3.2 | Two-stage deduplication | NOT_STARTED | 4.3 |
| 4.3.3 | UnifiedDecayEngine | NOT_STARTED | 4.3 |
| 4.3.4 | M20 RetentionEnforcer | NOT_STARTED | 4.3 |
| 4.3.5 | Per-entity access tracking | NOT_STARTED | 4.3 |
| 4.3.6 | Pruning regret detection | NOT_STARTED | 4.3 |
| 4.3.7 | M19 DuplicateDetector + novelty | NOT_STARTED | 4.3 |
| 4.3.8 | Adaptive novelty bonus learning | NOT_STARTED | 4.3 |
| 4.3.9 | Decay immunity ontology | NOT_STARTED | 4.3 |
| 4.3.10 | Prune decision audit logging | NOT_STARTED | 4.3 |
| 4.3.11 | MinHash LSH for scale | NOT_STARTED | 4.3 |
| 4.3.12 | R3 tests | NOT_STARTED | 4.3 |
| 4.4.1 | UltraBERT NER integration | NOT_STARTED | 4.4 |
| 4.4.2 | Per-entity-type disambiguation weights | NOT_STARTED | 4.4 |
| 4.4.3 | Disambiguation weight learning | NOT_STARTED | 4.4 |
| 4.4.4 | Ambiguous entity resolution | NOT_STARTED | 4.4 |
| 4.4.5 | Entity resolution confidence + P06 gaps | NOT_STARTED | 4.4 |
| 4.4.6 | Adaptive merge thresholds | NOT_STARTED | 4.4 |
| 4.4.7 | Entity merge cascade + undo | NOT_STARTED | 4.4 |
| 4.4.8 | M21 KGConsolidator | NOT_STARTED | 4.4 |
| 4.4.9 | Granger causality inference | NOT_STARTED | 4.4 |
| 4.4.10 | Adaptive causality thresholds | NOT_STARTED | 4.4 |
| 4.4.11 | Edge demotion | NOT_STARTED | 4.4 |
| 4.4.12 | R4 tests | NOT_STARTED | 4.4 |

**Total**: 40 issues (8 + 8 + 12 + 12)

---

## Part F: Completion Criteria

### F.1 Per-Epic Completion Criteria

| Epic | Tests Required | Coverage Target | Key Metrics |
|------|----------------|-----------------|-------------|
| 4.1 | R1 unit + integration | ≥80% | importance_score_distribution, hebbian_edges_updated |
| 4.2 | R2 unit + integration | ≥80% | silhouette_score > 0.5, singleton_rate < 0.20 |
| 4.3 | R3 unit + integration | ≥80% | dedup_accuracy > 0.95, decay_factor_distribution |
| 4.4 | R4 unit + integration | ≥80% | disambiguation_accuracy > 0.90, causal_edges_inferred |

### F.2 Milestone Completion Criteria

- [ ] All 40 issues marked COMPLETED
- [ ] Full P03 test suite passes (target: 1200+ tests)
- [ ] Test coverage ≥80% for new code
- [ ] Governance sync shows no unexpected drift
- [ ] R1-R4 phases execute successfully in integration tests
- [ ] Performance: R1-R4 combined latency <500ms for 100-event batch

---

## Appendix: Key Formulas Reference

### Importance Score (R1)

```
importance = (
    0.35 × |sentiment| × |affect_valence| × (1 + affect_arousal)
  + 0.25 × exp(-λ_recency × days_since)
  + 0.20 × log(1 + access_count) / log(10)
  + 0.20 × participant_count × avg_relationship_strength
)
```

### Hebbian Weight Update (R1)

```
delta = learning_rate × (max_weight - current_weight) × event_importance
new_weight = current_weight + delta
```

### Composite Distance (R2)

```
distance = (1 - temporal_weight) × cosine_distance(emb_a, emb_b)
         + temporal_weight × normalized_time_distance(ts_a, ts_b)
```

### Exponential Decay (R3)

```
decay = exp(-λ × days_since_observation)
```

### Disambiguation Similarity (R4)

```
similarity = (w_embedding × embedding_sim) + (w_string × string_sim)
```

### Granger Precedence Ratio (R4)

```
precedence_ratio = a_before_b / (a_before_b + b_before_a)
```
