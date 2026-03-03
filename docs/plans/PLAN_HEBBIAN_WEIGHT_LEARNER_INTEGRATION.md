# Plan: Hebbian Learning & Importance Weight Learner Integration

> **Status**: DRAFT
> **Created**: 2026-03-03
> **Scope**: Complete the disconnected R1 learning systems (HebbianLearner, ImportanceWeightLearner) and wire
> them into P03 with proper DB layers, feedback loops, and KG integration.
> **Related Discovery Docs**:
>
> - `docs/pipelines/p03_enhancement_discovery/P03_R1_IMPORTANCE_SCORING_DISCOVERY.md`
> - `docs/pipelines/p03_enhancement_discovery/P03_R4_KG_CONSOLIDATION_DISCOVERY.md`
>
> **Core Thesis**: Close the loop — R1 importance affects Hebbian/KG strengthening; learned
> structures affect future consolidation; both are auditable and bounded.
> The plan is NOT inventing new primitives — it's wiring and alignment.

---

## Architecture Recap: Three Disconnected Systems

```
                    P03 Consolidation Pipeline
                    ==========================

  R1 (Importance Scoring)                      R4 (KG Consolidation)
  -----------------------                      ----------------------
  ImportanceScorer (ACTIVE)                    _discover_relationships()
  CONFIG_B: 8 weights, 6 additive +             |
  7 multiplicative modulators                    +-- HebbianLearner.compute_initial_weight()
  190 unit + 24 integration tests                +-- HebbianLearner.update_edge_weight()
       |                                         +-- kg_edges_lookup (READ st_kg_edges)
       |  scores events [0,1]                    +-- envelope -> R7 -> st_kg_edges (WRITE)
       v                                         |
  ScoredEvent                                    |  WHAT'S MISSING:
  (importance_score,                             |  - apply_decay() NOT called
   priority_tier)                                |  - apply_anti_decay() NOT called
       |                                         |  - process_batch() NOT called
       |  NOT CONNECTED                          |  - Uses cluster.confidence as importance
       v                                         |    proxy, NOT actual R1 importance_score
                                                 |  - No time-based edge decay
  ImportanceWeightLearner (EXISTS, DISCONNECTED) |  - No anti-Hebbian from P06 feedback
  4 components: emotional, recency,              |  - No KG edge weight -> importance feedback
    access, social                               |
  Scorer uses 8 components -> MISMATCH           |
  Needs 500+ grounded events -> NONE YET         |
                                                 |
                     NO FEEDBACK LOOP            |
          KG edge weights do NOT influence       |
          importance scoring today               |
```

### What R4 Already Does (Partial Hebbian)

R4's `_discover_relationships()` at line 1936 of `r4_kg_consolidator.py`:

1. **READS** existing edges from `st_kg_edges` via `kg_edges_lookup` syscall
2. Counts co-occurrences per event using its own pair enumeration (NOT `HebbianLearner.process_batch()`)
3. Calls `HebbianLearner.compute_initial_weight(avg_importance)` for new edges
4. Calls `HebbianLearner.update_edge_weight(current_weight, count, avg_importance)` for existing edges
5. **WRITES** edge updates via `envelope.phases.r4_new_edges` / `r4_updated_edges` -> R7 -> `st_kg_edges`

### What R4 Does NOT Do

- Does NOT call `HebbianLearner.apply_decay(weight, days_since_last)` -- edges never fade
- Does NOT call `HebbianLearner.apply_anti_decay(weight, signal)` -- wrong edges never weaken
- Does NOT use `HebbianLearner.process_batch()` at all (has its own co-occurrence loop)
- Uses `(cluster_a.confidence + cluster_b.confidence) / 2` as importance proxy instead of actual `event.importance_score` from R1
- Does NOT feed KG edge weights back to R1 importance scoring

### Answer: Does R4 Serve as the "Missing Layer"?

**Partially yes.** R4 is already the orchestration layer that reads edges from DB, calls HebbianLearner methods, and writes updates back through the envelope/R7 path. The DB read/write infrastructure EXISTS.

**But the integration is incomplete.** R4 cherry-picks 2 out of 5 HebbianLearner methods. The decay, anti-Hebbian, batch processing, and actual-importance-score paths are all missing. And the reverse feedback loop (KG -> R1) doesn't exist at all.

---

## Verified Disconnects (Code Evidence)

The following four disconnects were verified against live code. These are prerequisites
that must be resolved before the learning-system milestones can land cleanly.

### Disconnect 1: R1 weight_store is not production-wired

**File**: `k0/pipelines/p03/phases/r1_importance_scorer.py` line 209

```python
weight_store = getattr(ctx.syscalls, "weight_store", None)
scorer = ImportanceScorer(space_id=space_id, weight_store=weight_store)
```

Nothing in the runtime injects `weight_store` onto `ctx.syscalls`. The `getattr(..., None)`
fallback means R1 always gets `None` in production and uses static CONFIG_B. Tests pass because
they inject mock stores directly. The scorer's learned-weight path (cold-start blending, per-space
lookup, alpha blending) is logically supported but never exercised in a real runtime.

### Disconnect 2: Two incompatible weight-store protocols

**R1 protocol** (`k0/modules/consolidation/algorithms/importance_scorer.py` line 162):

```python
class WeightStoreProtocol(Protocol):
    async def get_weights(self, space_id: str, param_prefix: str) -> Optional[LearnedWeights]:
        ...
# LearnedWeights = {weights: Dict[str, float], sample_count: int, updated_at: int}
```

**R3 protocol** (`k0/modules/consolidation/algorithms/novelty_bonus_learner.py` line 146):

```python
class LearnedWeightsStoreProtocol(Protocol):
    async def get_weight(self, param_key: str, space_id: str) -> Optional[float]:
        ...
    async def upsert_weight(self, param_key: str, space_id: str, value: float, prior_value: float) -> None:
        ...
```

Both claim to read/write `st_learned_weights`, but:

- R1 does a **bulk fetch** (all weights for a space+prefix at once).
- R3 does **per-key get/upsert** (one param at a time).
- R3 uses `InMemoryLearnedWeightsStore` even in its production store container (`R3Stores`
  at `r3_dedup_decay.py` line 334 uses `InMemoryLearnedWeightsStore()` as default).

A single `st_learned_weights` adapter must implement both protocols, or they must be unified.

### Disconnect 3: Pipeline contract R1 section is stale vs CONFIG_B

**Contract** (`k0/contracts/pipelines/p03_consolidation.v1.yaml` line 127-141):

```yaml
description: |
  R1 - Importance scoring using weighted formula.
  importance = w_recency * recency + w_affect * affect + w_social * social +
               w_rehearsal * rehearsal + w_novelty * novelty
  Weights from st_learned_weights (Thompson Sampling adaptive).
config:
  default_weights:
    recency: 0.25
    affect: 0.30
    social: 0.20
    rehearsal: 0.15
    novelty: 0.10
```

**Reality** (CONFIG_B in `importance_scorer.py`):

- 8 weights: sentiment, affect, arousal, surprise, novelty, social, identity, recency
- 6 additive components + 7 multiplicative modulators + clamp + tier mapping
- NO Thompson Sampling -- uses static CONFIG_B or online gradient descent (ImportanceWeightLearner)
- The 5-weight "recency/affect/social/rehearsal/novelty" set no longer exists

The contract also declares `stage_11_hebbian_update` as a parallel R1 phase with its own
module `consolidation.hebbian_learner:v1`, config (`learning_rate: 0.01, decay_factor: 0.995`),
and `temporal_window_seconds: 3600`. In reality, Hebbian is called INSIDE R4's
`_discover_relationships()`, not as a separate P03 phase.

### Disconnect 4: R4 uses cluster confidence, not R1 importance_score

Already documented in original plan above (`r4_kg_consolidator.py` line ~1960):

```python
avg_importance = (cluster_a.confidence + cluster_b.confidence) / 2
```

This is NER extraction confidence, not R1's event-level importance score.

---

## Milestone 0: Production Wiring Alignment (M5.P)

> **Goal**: Resolve the four verified disconnects above. Without this milestone,
> none of the learning milestones (M5.H, M5.W, M6.F) can function in production.
> This is the "make it real" milestone -- everything else is "make it smart."
>
> **Principle**: These are wiring and schema alignment issues, not algorithm work.
> They should be fast to implement because the primitives (table, scorer, protocol,
> in-memory stores, tests) all exist. The gap is the glue.

### Epic 5.P.1 -- Unified Weight Store Adapter

**Problem**: `st_learned_weights` table exists (migration 0040 + 0041 history), but there is
no production implementation of either `WeightStoreProtocol` (R1 bulk) or
`LearnedWeightsStoreProtocol` (R3 per-key). Both protocols are satisfied only by in-memory
test doubles today.

**Decision**: Build ONE adapter class that implements BOTH protocols against `st_learned_weights`.
R1's bulk `get_weights()` issues `SELECT * FROM st_learned_weights WHERE scope_id = $1 AND param_key LIKE $2%`.
R3's per-key `get_weight()` issues `SELECT current_value FROM st_learned_weights WHERE param_key = $1 AND scope_id = $2`.
R3's `upsert_weight()` uses the existing UPSERT + history trigger (migration 0041).

| Issue | Title | Scope | Est. | Depends | AC |
|-------|-------|-------|------|---------|-----|
| 5.P.1.1 | Create PgLearnedWeightsStore adapter | Single class implementing both `WeightStoreProtocol` and `LearnedWeightsStoreProtocol` backed by `st_learned_weights` via syscalls | M | none | Both protocols satisfied; SELECT, UPSERT, and history work |
| 5.P.1.2 | Define authoritative param_key namespace for CONFIG_B | Document key convention: `importance.{component_name}` for all 8 CONFIG_B weights. e.g. `importance.sentiment_weight`, `importance.affect_weight`, ..., `importance.recency_weight`. R1 reads with prefix `importance.`, R3 reads individual keys. | S | none | Key namespace documented; no collision with R3 novelty keys (`novelty_bonus.*`) |
| 5.P.1.3 | Wire adapter into P03 runner context | Inject `PgLearnedWeightsStore` instance onto `ctx.syscalls.weight_store` during P03 phase runner initialization. R1 gets it via existing `getattr(ctx.syscalls, "weight_store", None)`. R3 gets it via `R3Stores.learned_weights_store`. | M | 5.P.1.1 | `weight_store is not None` in both R1 and R3 at runtime; fallback still works if injection fails |
| 5.P.1.4 | Add capability declaration | Add `st_learned_weights.read` + `st_learned_weights.write` to both R1 and R3 module contracts (R1 already has it in pipeline contract but not module contract) | S | 5.P.1.3 | Capability check passes for both phases |
| 5.P.1.5 | Integration tests with real store | Test: inject PgLearnedWeightsStore -> R1 scorer reads weights -> R3 novelty learner upserts weights -> R1 reads updated weights on next cycle. Verify round-trip. | M | 5.P.1.3 | End-to-end read/write/read cycle works against test DB |
| 5.P.1.6 | Verify history/rollback via migration 0041 | Confirm that upsert_weight triggers version history insert; verify rollback query works | S | 5.P.1.1 | History row created on each weight update; rollback to prior version tested |

---

### Epic 5.P.2 -- Pipeline Contract Alignment with CONFIG_B

**Problem**: The pipeline contract `p03_consolidation.v1.yaml` describes an R1 formula and
weight set that no longer exists. It also declares a separate `stage_11_hebbian_update` phase
that doesn't match how Hebbian actually runs (inside R4, not as a standalone R1 phase).

This is not just cosmetic -- the contract is the authoritative reference for what capabilities
a phase needs, what config keys are valid, and what the DAG structure is. Stale contracts
create risk when integrating learners because config keys won't match.

| Issue | Title | Scope | Est. | Depends | AC |
|-------|-------|-------|------|---------|-----|
| 5.P.2.1 | Update stage_10 description to CONFIG_B formula | Replace 5-weight linear formula with actual CONFIG_B: 8 weights, 6 additive + 7 multiplicative modulators. Reference module contract `consolidation.importance_scorer.v1.yaml`. | S | none | Description matches implementation; no stale weight names |
| 5.P.2.2 | Update stage_10 default_weights config | Replace `{recency: 0.25, affect: 0.30, social: 0.20, rehearsal: 0.15, novelty: 0.10}` with CONFIG_B 8-weight defaults from `importance_scorer.py` | S | none | Config keys match scorer's `ImportanceWeights` field names |
| 5.P.2.3 | Remove "Thompson Sampling" reference | Replace with accurate description: "Static CONFIG_B weights; learned weights from st_learned_weights when sample_count >= 500; cold-start blending for intermediate state" | S | none | No Thompson Sampling reference remains |
| 5.P.2.4 | Resolve stage_11_hebbian_update declaration | Either: (A) Remove it (Hebbian runs inside R4 _discover_relationships), or (B) Keep it as the intended future architecture and add a "status: not_implemented" marker. Document decision. | M | none | Pipeline DAG accurately reflects actual execution; R2 `after:` dependencies updated if stage removed |
| 5.P.2.5 | Align R4 stage descriptions with actual code | Verify stage_40 (entity_extractor), stage_41 (relationship_builder), stage_42 (causal_inference) descriptions match what `r4_kg_consolidator.py` actually does (it's a monolith, not 3 separate modules) | M | none | Contract DAG matches runtime phase execution; or note "monolith pending decomposition" |
| 5.P.2.6 | Bump contract version or add changelog | Record that CONFIG_B alignment was applied; note backward-incompatible config key changes | S | 5.P.2.1, 5.P.2.2, 5.P.2.3 | Version bumped or changelog section added |

---

### Epic 5.P.3 -- R3 Stores Production Wiring

**Problem**: `R3Stores.create_in_memory()` is the default at `r3_dedup_decay.py` line 334.
This means R3's novelty bonus learner writes to an in-memory store that is discarded after
each cycle. Learned novelty bonuses don't persist.

| Issue | Title | Scope | Est. | Depends | AC |
|-------|-------|-------|------|---------|-----|
| 5.P.3.1 | Wire PgLearnedWeightsStore into R3Stores | Replace `InMemoryLearnedWeightsStore()` default with injected `PgLearnedWeightsStore` from P03 runner context | M | 5.P.1.1, 5.P.1.3 | R3 novelty learner persists to st_learned_weights |
| 5.P.3.2 | Add fallback for missing store | If injection fails, fall back to `InMemoryLearnedWeightsStore` with warning log (current behavior preserved) | S | 5.P.3.1 | Graceful degradation; structured log emitted |
| 5.P.3.3 | Verify R3 novelty learner round-trip | Integration test: R3 upserts novelty bonus -> next cycle reads persisted value | M | 5.P.3.1 | Novelty bonus persists across cycles |

---

## Milestone 1: Hebbian Learning Completion (M5.H)

> **Goal**: Make HebbianLearner fully functional within R4 -- use real importance scores,
> enable time-based decay, wire anti-Hebbian signals, and replace the partial integration
> with a proper orchestration pattern.

### Epic 5.H.1 -- Wire R1 Importance Scores into R4 Hebbian

**Problem**: R4 uses `(cluster_a.confidence + cluster_b.confidence) / 2` as the importance signal
for Hebbian weight computation. The actual R1 `importance_score` is available on each event
in `envelope.phases.r1_scored_events` but R4 ignores it.

**Impact**: Hebbian weights are based on NER confidence, not on how important the event actually is.
A routine breakfast mention with high NER confidence strengthens edges equally to a milestone event.
This defeats the entire purpose -- Hebbian should strengthen edges MORE for important events.

| Issue | Title | Scope | Est. | Depends | AC |
|-------|-------|-------|------|---------|-----|
| 5.H.1.1 | Build R1-to-R4 importance score map | In `_discover_relationships`, build `event_id -> importance_score` from `envelope.phases.r1_scored_events` | S | none | Map populated from ScoredEvent list; fallback to 0.5 if R1 skipped |
| 5.H.1.2 | Replace cluster confidence proxy with R1 scores | Use actual R1 importance_score per event when computing `avg_importance` for each co-occurrence pair | S | 5.H.1.1 | `avg_importance = mean(importance_scores_for_pair_events)` not `mean(cluster confidences)` |
| 5.H.1.3 | Add importance_source field to edge metadata | Track whether Hebbian used R1 score or fallback in edge evidence | S | 5.H.1.2 | `source_algorithm` includes "hebbian_r1" vs "hebbian_fallback" |
| 5.H.1.4 | Update tests for importance-score-aware Hebbian | Test that high-importance events produce stronger edge weights than low-importance | M | 5.H.1.2 | 5+ tests covering score-dependent edge weight variation |

---

### Epic 5.H.2 -- Enable Edge Decay and Anti-Hebbian in R4

**Problem**: Once an edge is created, its weight NEVER decreases. There is no time-based decay
(edges between people you haven't mentioned in 6 months stay at full strength) and no correction
mechanism (if the system made a wrong association, there's no way to weaken it).

The HebbianLearner already has `apply_decay()` and `apply_anti_decay()` implemented and tested.
R4 just doesn't call them.

| Issue | Title | Scope | Est. | Depends | AC |
|-------|-------|-------|------|---------|-----|
| 5.H.2.1 | Add edge age computation to _discover_relationships | For each existing edge, compute `days_since_last_observed` from `last_observed_at` vs current cycle timestamp | S | none | `days_elapsed` calculated per edge; handles NULL last_observed_at |
| 5.H.2.2 | Call HebbianLearner.apply_decay() on stale edges | Apply exponential decay `w * exp(-0.01 * days)` to edges not re-observed in current batch. Edges below prune_threshold (0.05) get marked for archive. | M | 5.H.2.1 | Existing edges without current-cycle co-occurrence get decayed; pruned edges tracked in stats |
| 5.H.2.3 | Emit decay stats in R4PhaseStats | Add `hebbian_edges_decayed`, `hebbian_edges_pruned` counters | S | 5.H.2.2 | Stats visible in phase completion log |
| 5.H.2.4 | Add feature flag for decay | `R4Config.enable_hebbian_decay: bool = False` (safe default off until validated) | S | 5.H.2.2 | Flag controls whether decay runs; false = current behavior |
| 5.H.2.5 | Design anti-Hebbian signal ingestion from P06 | Read `st_learning_queue` entries with anti-Hebbian signal types (ENTITY_MERGE_REJECTED, ASSOCIATION_WRONG, CONTRADICTION) and map to edge pairs | M | none | ADR or design doc specifying P06 -> R4 anti-Hebbian signal protocol |
| 5.H.2.6 | Implement anti-Hebbian signal processing in R4 | Query resolved gaps with anti-Hebbian signals, call `apply_anti_decay()` per affected edge, emit weakened weight via envelope | M | 5.H.2.5 | Anti-Hebbian signals reduce edge weights; 1.5x faster than positive learning |
| 5.H.2.7 | Add anti-Hebbian stats | `hebbian_anti_signals_processed`, `hebbian_edges_weakened_by_feedback` counters | S | 5.H.2.6 | Stats visible in phase log |
| 5.H.2.8 | Tests for decay and anti-Hebbian in R4 | Unit: decay reduces old edges. Integration: anti-Hebbian signal weakens target edge. Edge case: prune below threshold. | M | 5.H.2.2, 5.H.2.6 | 10+ tests covering decay, prune, anti-Hebbian, combined |

---

### Epic 5.H.3 -- Refactor R4 Co-occurrence to Use HebbianLearner.process_batch()

**Problem**: R4's `_discover_relationships` has 150+ lines of its own co-occurrence counting
and pair enumeration logic. Meanwhile, `HebbianLearner.process_batch()` does exactly the same
thing and additionally handles batch-level aggregation with EdgeUpdate audit records. The R4
code duplicates logic and misses process_batch's aggregation benefits.

**Decision Required**: Should R4 delegate entirely to `process_batch()`, or keep its own
co-occurrence logic (which has R4-specific features like UltraBERT relation type inference)?

**Recommendation**: Keep R4's co-occurrence enumeration (it has UltraBERT relation inference,
cluster-level dedup, self-loop guards that process_batch lacks) but call HebbianLearner methods
more systematically. The refactor should:

1. Use `extract_cooccurrences()` for entity pair extraction
2. Use `process_batch()` for weight aggregation
3. Keep R4's relation type inference and DB read/write orchestration

| Issue | Title | Scope | Est. | Depends | AC |
|-------|-------|-------|------|---------|-----|
| 5.H.3.1 | ADR: R4 Hebbian delegation strategy | Decide: full delegation to process_batch vs. R4 wrapper + selective method calls. Document trade-offs. | S | none | ADR accepted |
| 5.H.3.2 | Align HebbianLearner.ParsedEntity with R4 EntityCluster | ParsedEntity has 4 fields; EntityCluster has 12. Create adapter or alignment layer. | S | 5.H.3.1 | HebbianLearner can accept R4 cluster data without data loss |
| 5.H.3.3 | Implement chosen delegation pattern | Refactor `_discover_relationships` per ADR decision | L | 5.H.3.1, 5.H.3.2, 5.H.1.2 | Co-occurrence logic uses HebbianLearner methods; no duplicate pair enumeration |
| 5.H.3.4 | Preserve UltraBERT relation type inference | Ensure relation_type/subtype inference (M10.3) still works after refactor | M | 5.H.3.3 | All existing R4 edge type inference tests pass |
| 5.H.3.5 | Regression test suite | Full R4 phase execution test with Hebbian refactor; edge counts match pre-refactor | M | 5.H.3.3 | All 441 existing R4 tests pass; new regression tests for edge weight accuracy |

---

## Milestone 2: Importance Weight Learner Alignment (M5.W)

> **Goal**: Fix the 4-vs-8 component mismatch between ImportanceWeightLearner and ImportanceScorer,
> enable the learner to actually train, and create the grounding signal path.

### Current State

| Property | ImportanceWeightLearner | ImportanceScorer (CONFIG_B) |
|----------|------------------------|----------------------------|
| Components | 4: emotional, recency, access, social | 8: sentiment, affect, arousal, surprise, novelty, social, identity, recency |
| Weights sum | 1.0 (softmax) | 1.0 (manually tuned) |
| Training signal | `was_grounded: bool` (event became permanent memory) | N/A (stateless) |
| Min samples | 500 | 500 (for reading learned weights) |
| Storage | `st_learned_weights` (UPSERT per component) | Reads from `st_learned_weights` |
| Activation | Never activated (no grounded events) | Always active |
| Backend | PyTorch (preferred) or NumPy | N/A |

### The Mismatch (FG-R1-002)

The learner trains weights for 4 components. The scorer uses 8 components. Even if the learner
ran today, its output (`{emotional: 0.35, recency: 0.25, access: 0.20, social: 0.20}`) cannot
be consumed by the scorer because:

1. **Missing components**: surprise, novelty, identity have no learner component
2. **Naming mismatch**: learner calls it "access", scorer has no "access" component
3. **Granularity mismatch**: learner's "emotional" = one weight; scorer splits emotional into
   sentiment_weight + affect_weight + arousal_weight

### Epic 5.W.1 -- Align Learner Components with Scorer

| Issue | Title | Scope | Est. | Depends | AC |
|-------|-------|-------|------|---------|-----|
| 5.W.1.1 | ADR: Weight learner component alignment strategy | Choose between: (A) Expand learner to 8 components matching scorer, (B) Learner trains group weights (emotional, social, etc.) and scorer distributes within group, (C) Hierarchical: learner trains 6 group weights, sub-weights are fixed ratios within groups | M | none | ADR accepted with clear mapping from learner output to scorer input |
| 5.W.1.2 | Implement component alignment | Update WeightLearnerConfig.COMPONENTS, TrainingSample.features, and get_weights() to match chosen strategy | L | 5.W.1.1 | Learner output can be directly consumed by ImportanceScorer.get_weights() |
| 5.W.1.3 | Update TrainingSample feature extraction | TrainingSample must extract the correct features from P03EventState fields to match new components | M | 5.W.1.2 | Each new component has a derivation path from available event fields |
| 5.W.1.4 | Update st_learned_weights schema/rows | Migrate existing rows (if any) to new component names; ensure scorer reads correctly | S | 5.W.1.2 | get_weights() returns ImportanceWeights-compatible dict |
| 5.W.1.5 | Comprehensive tests for aligned learner | Train step with new features, weight output compatible with scorer, rollback works | M | 5.W.1.2, 5.W.1.3 | 15+ tests pass; end-to-end: train -> get_weights -> scorer consumes |

---

### Epic 5.W.2 -- Build Grounding Signal Path

**Problem**: ImportanceWeightLearner trains on `(features, was_grounded)` pairs. A "grounded"
event is one that a user confirmed as important (e.g., recalled it, asked about it, explicitly
saved it). This signal does not exist in the current system.

**The grounding signal needs a source.** Options:

| Source | Description | Reliability | Available? |
|--------|-------------|-------------|------------|
| K1 recall queries | User asks "what happened with Mom last week?" -> events returned are grounded | HIGH | Future (K1 query pipeline) |
| Explicit star/save | User explicitly marks an event as important | HIGH | Future (UI) |
| R5 dream selection | Events selected for "dream consolidation" are implicitly grounded | MEDIUM | Exists but not wired |
| P08 retrieval hits | Events retrieved by any downstream system count as grounded | MEDIUM | Future (P08) |
| Time-based proxy | Events that survive 30 days without decay are implicitly grounded | LOW | Computable from st_hipp_events |

| Issue | Title | Scope | Est. | Depends | AC |
|-------|-------|-------|------|---------|-----|
| 5.W.2.1 | ADR: Grounding signal sources and reliability weighting | Define which signals count as "grounded", with what confidence, and how they flow to the weight learner | M | none | ADR accepted |
| 5.W.2.2 | Implement grounding signal collector | Service/module that aggregates grounding signals from defined sources into `st_grounding_signals` or equivalent storage | L | 5.W.2.1 | Grounding signals queryable per event_id |
| 5.W.2.3 | Wire grounding signals to TrainingBatch construction | Build TrainingBatch from scored events + grounding signals for weight learner training | M | 5.W.2.2, 5.W.1.3 | TrainingBatch populated with real features + grounding labels |
| 5.W.2.4 | Implement training trigger in P03 | After R1 scoring and grounding signals available, call `ImportanceWeightLearner.train_step()` with batch | M | 5.W.2.3 | Training runs when >= 500 samples + >= 50 batch size |
| 5.W.2.5 | Implement weight persistence flow | After training, persist learned weights to `st_learned_weights`; R1 reads on next cycle | S | 5.W.2.4 | Learned weights persisted and loaded on next cycle; cold-start blending works |
| 5.W.2.6 | Tests for grounding-to-training pipeline | Integration test: mock grounding signals -> training batch -> train step -> weights change -> scorer reads new weights | L | 5.W.2.4, 5.W.2.5 | End-to-end test passes; weights converge toward reasonable values |

---

## Milestone 3: KG Edge -> Importance Feedback Loop (M6.F)

> **Goal**: Close the loop. Currently KG edge weights and importance scores are independent.
> If Mom and Dad have a strong KG relationship (edge weight 0.9), events mentioning both
> of them SHOULD score higher. This is the missing feedback loop.
>
> **This is the user's core intuition**: "7 billion people, 7 billion memory preferences,
> one formula can't guide what is important." The feedback loop lets the KG personalize scoring.

### Design: How KG Edges Feed Back to R1

```
    R1 Scoring (current batch)
    ==========================
    event mentions [Mom, Dad]
           |
           v
    [1] Look up KG edge weight for (Mom, Dad) pair
        st_kg_edges WHERE source=Mom AND target=Dad
        -> edge_weight = 0.87 (strong relationship)
           |
           v
    [2] Compute "relationship_boost" factor
        relationship_boost = 1.0 + boost_scale * max_edge_weight_in_event
        e.g., 1.0 + 0.15 * 0.87 = 1.13
           |
           v
    [3] Apply as multiplicative modulator in CONFIG_B
        score = base * ... * relationship_boost * ... * reliability
           |
           v
    Events about strongly-connected entities score HIGHER
    Events about weakly-connected entities are not penalized (boost >= 1.0)
```

### Epic 5.F.1 -- KG Edge Lookup for R1 Scoring

| Issue | Title | Scope | Est. | Depends | AC |
|-------|-------|-------|------|---------|-----|
| 5.F.1.1 | ADR: KG relationship boost design | Define: boost formula, scale factor, max boost cap, which edge types contribute, performance budget (R1 currently < 30ms) | M | none | ADR accepted |
| 5.F.1.2 | Add kg_edges_lookup capability to R1 | R1 currently has read:st_learned_weights only. Add read:st_kg_edges to R1 contract side_effects. | S | 5.F.1.1 | Contract updated; capability declared |
| 5.F.1.3 | Implement entity extraction from events in R1 | R1 needs to know which entities are in each event. Either parse `ner_entities_json` or receive entity list from R0/envelope. | M | 5.F.1.1 | R1 can determine entity set per event |
| 5.F.1.4 | Implement KG edge weight lookup in R1 | Query st_kg_edges for entity pairs in current batch; cache per-cycle to avoid per-event DB calls | M | 5.F.1.2, 5.F.1.3 | Edge weights available per entity pair; single DB call per cycle |
| 5.F.1.5 | Implement relationship_boost computation | For each event, find max edge weight among entity pairs; compute boost = 1.0 + scale * max_weight | M | 5.F.1.4, 5.F.1.1 | relationship_boost computed per event; range [1.0, 1.0 + scale] |
| 5.F.1.6 | Integrate relationship_boost into CONFIG_B formula | Add relationship_boost as 8th multiplicative modulator (after intent_boost, before tier_multiplier) | M | 5.F.1.5 | CONFIG_B formula updated; existing tests updated for new modulator |
| 5.F.1.7 | Feature flag: enable_kg_boost | `R1Config.enable_kg_boost: bool = False` (disabled until KG has meaningful data) | S | 5.F.1.6 | Flag controls boost; false = boost is 1.0 (no effect) |
| 5.F.1.8 | Update R1 contract for relationship_boost | Add relationship_boost to formula description, add read:st_kg_edges side effect | S | 5.F.1.6 | Contract reflects new modulator and DB access |
| 5.F.1.9 | Tests for KG boost | Unit: boost computation correctness. Integration: events with strong KG edges score higher. Edge case: no KG data = no boost. Performance: < 30ms with edge lookup. | L | 5.F.1.6 | 15+ tests; all existing 190 R1 tests still pass with boost disabled |

---

### Epic 5.F.2 -- Hebbian -> Importance Reinforcement Cycle

**This is the full virtuous cycle.**

```
Cycle N:
  R1 scores events -> high-importance events get high scores
  R4 Hebbian strengthens edges for entity pairs in high-importance events
  Edge weight for (Mom, Dad) increases from 0.5 to 0.54

Cycle N+1:
  New event mentions Mom and Dad
  R1 looks up edge weight (0.54) -> relationship_boost = 1.08
  This event scores slightly higher than if Mom and Dad were strangers
  R4 Hebbian sees higher importance -> strengthens edge more

  Over time:
  - Frequently co-occurring entities in important events get VERY strong edges
  - Those strong edges make future events about those entities more important
  - Rare or low-importance co-occurrences decay toward zero
  - The system PERSONALIZES: your important people/places/topics emerge naturally
```

| Issue | Title | Scope | Est. | Depends | AC |
|-------|-------|-------|------|---------|-----|
| 5.F.2.1 | End-to-end cycle simulation test | Simulate 5 P03 cycles: events -> R1 scoring -> R4 Hebbian -> write edges -> next cycle R1 reads edges -> verify boost increases | L | 5.F.1.6, 5.H.1.2 | Test shows monotonic increase in edge weights AND importance scores for consistently co-occurring entity pairs |
| 5.F.2.2 | Convergence analysis | Verify the reinforcement cycle converges (soft saturation in Hebbian prevents runaway; boost cap in R1 prevents inflation). Mathematical proof or simulation. | M | 5.F.2.1 | Proof or simulation showing weights converge to stable equilibrium |
| 5.F.2.3 | Runaway detection | Add monitoring for edge weight velocity (rate of change). Alert if any edge weight increases > 0.1 per cycle. | S | 5.F.2.1 | Metric emitted; alert threshold configurable |
| 5.F.2.4 | Emergency brake: weight reset capability | Syscall or admin endpoint to reset all edge weights to initial values if runaway detected. | S | 5.F.2.3 | Reset mechanism works; tested |

---

## Milestone 4: R1 Observability & Test Completion (M5.O)

> **Goal**: Close the remaining R1 gaps from Epic 5A.4 that were deferred.
> These are independent of the learning system milestones above.

### Epic 5.O.1 -- R1 Observability (5.2-OBS)

From R1 Discovery Doc Section 7:

| Issue | Title | Scope | Est. | Depends | AC |
|-------|-------|-------|------|---------|-----|
| 5.O.1.1 | Add OTel span for R1 phase | Wrap R1ImportanceScorer.run() in OpenTelemetry span with cycle_id, event_count, duration_ms | S | none | Span visible in tracing; includes all R1 attributes |
| 5.O.1.2 | Score distribution histogram | Emit histogram of importance_score values per cycle (10 buckets: 0-0.1, 0.1-0.2, ..., 0.9-1.0) | S | none | Histogram metric emitted per cycle |
| 5.O.1.3 | Weight source counter | Counter tracking how many cycles use "static" vs "learned" vs "blended" weights | S | none | Counter incremented per cycle |
| 5.O.1.4 | Priority tier gauge | Gauge tracking count per priority tier per cycle (CRITICAL, HIGH, MEDIUM_HIGH, MEDIUM, LOW_MEDIUM, LOW) | S | none | Gauge updated per cycle; matches tier counts in structured log |
| 5.O.1.5 | Audit sampling rate control | Verify audit_sample_rate=0.10 works correctly; add metric for audit_records_generated vs events_scored | S | none | Metric shows ~10% sampling rate |
| 5.O.1.6 | Breakdown component distribution | Per-cycle histogram of each component (emotional, surprise, novelty, social, identity, recency) | M | none | 6 histograms emitted; enables cross-cycle component drift detection |

---

### Epic 5.O.2 -- R1 Test Gap Closure (5.2-TEST)

From R1 Discovery Doc Section 8.2:

| Issue | Title | Scope | Est. | Depends | AC |
|-------|-------|-------|------|---------|-----|
| 5.O.2.1 | Cold-start blending tests | Test 3-level weight fallback: per-space -> global-blend -> static. Alpha blending correctness. | M | none | 5+ tests covering all 3 fallback levels + edge cases |
| 5.O.2.2 | Port POC 120 scenarios as regression tests | Convert `poc/r1_weight_research/scenarios.py` (120 scenarios, 13 categories) to pytest parametrized tests | L | none | 120 parametrized tests pass; all tiers match POC expectations |
| 5.O.2.3 | Performance benchmark test | Score 100 events in < 30ms (contract latency). Score 1000 events in < 300ms. | S | none | Timing assertions pass on CI |
| 5.O.2.4 | Hebbian disabled path test | Verify R1 with enable_hebbian=False produces no HebbianEdgeUpdate outputs | S | none | Test confirms empty Hebbian output |
| 5.O.2.5 | Idempotency test | Score same batch twice with same now_ms -> identical results | S | none | Deterministic output verified |

---

## Milestone 5: Storage & Infrastructure (M5.S)

> **Goal**: Database schema, indexes, and housekeeping needed by the learning systems.

### Epic 5.S.1 -- Storage Housekeeping

| Issue | Title | Scope | Est. | Depends | AC |
|-------|-------|-------|------|---------|-----|
| 5.S.1.1 | Verify st_learned_weights table existence | Confirm table exists and has correct schema for both weight learner and scorer reads | S | none | Table confirmed; SELECT and UPSERT work |
| 5.S.1.2 | Add composite index on st_learning_queue (status, entity_id) | From R4 Discovery SG-003: resolved gap query needs composite index | S | none | Migration added; query plan uses index |
| 5.S.1.3 | Audit retention policy for st_consolidation_audit | Define retention period (30d? 90d?) and add TTL-based cleanup job | S | none | Policy documented; cleanup mechanism exists |
| 5.S.1.4 | Add st_grounding_signals table (if ADR 5.W.2.1 requires it) | Schema: event_id, signal_type, signal_source, confidence, created_at | M | 5.W.2.1 | Migration created; table queryable |
| 5.S.1.5 | Add merge_cascade_id index on st_entity_merges | From R4 Discovery SG-004: undo lookups need this index | S | none | Migration added |

---

## Dependency & Sequencing

```text
                                    Legend
                                    ------
                                    [x] = completed
                                    --> = depends on

  [x] Epic 5A.4 (CONFIG_B implementation)
   |
   +---> Epic 5.P.1 (Unified weight store adapter) -- GATE ZERO: blocks all learning
   |      |
   |      +---> Epic 5.P.2 (Contract alignment)   -- can start in parallel with 5.P.3
   |      +---> Epic 5.P.3 (R3 stores wiring)     -- R3 novelty learner persistence
   |      |
   |      +---> Epic 5.H.1 (Wire R1 scores to R4) -- first Hebbian priority
   |      |      |
   |      |      +---> Epic 5.H.2 (Decay + Anti-Hebbian)
   |      |      |      |
   |      |      |      +---> Epic 5.H.3 (Refactor co-occurrence)
   |      |      |
   |      |      +---> Epic 5.F.1 (KG boost in R1)
   |      |             |
   |      |             +---> Epic 5.F.2 (Full reinforcement cycle)
   |      |
   |      +---> Epic 5.W.1 (Align learner components) -- needs authoritative key namespace
   |             |
   |             +---> Epic 5.W.2 (Grounding signal path)
   |
   +---> Epic 5.O.1 (Observability)          -- independent, start anytime
   +---> Epic 5.O.2 (Test gaps)              -- independent, start anytime
   +---> Epic 5.S.1 (Storage)                -- independent, start anytime
```

### Recommended Execution Order

| Phase | Epics | Rationale |
|-------|-------|-----------|
| **Phase 0** (GATE ZERO) | 5.P.1 + 5.P.2 + 5.P.3 | Production wiring. Nothing works without a real weight store and aligned contracts. Unblocks every downstream epic. |
| **Phase A** (parallel) | 5.O.1 + 5.O.2 + 5.S.1 | Independent cleanup; reduces tech debt. Can run parallel with Phase 0. |
| **Phase B** | 5.H.1 | Quick win: use real R1 scores in Hebbian. Makes all future Hebbian work meaningful. |
| **Phase C** | 5.H.2 | Enable decay and anti-Hebbian. Edges can now weaken. Critical for graph health. |
| **Phase D** | 5.W.1 | Align weight learner. Prerequisite for personalized scoring. |
| **Phase E** (parallel) | 5.H.3 + 5.F.1 | Refactor co-occurrence + build KG boost. Both depend on earlier work. |
| **Phase F** | 5.W.2 | Grounding signal path. Depends on aligned learner. |
| **Phase G** | 5.F.2 | Full reinforcement cycle. The grand integration. Depends on everything. |

---

## Summary: Issue Counts by Epic

| Epic | Title | Issues | Estimated Size |
|------|-------|--------|----------------|
| **5.P.1** | **Unified Weight Store Adapter** | **6** | **M** |
| **5.P.2** | **Pipeline Contract Alignment** | **6** | **S-M** |
| **5.P.3** | **R3 Stores Production Wiring** | **3** | **S-M** |
| 5.H.1 | Wire R1 Scores into R4 Hebbian | 4 | S-M |
| 5.H.2 | Decay + Anti-Hebbian in R4 | 8 | M-L |
| 5.H.3 | Refactor Co-occurrence | 5 | L |
| 5.W.1 | Align Learner Components | 5 | L |
| 5.W.2 | Grounding Signal Path | 6 | XL |
| 5.F.1 | KG Edge Boost in R1 | 9 | L |
| 5.F.2 | Full Reinforcement Cycle | 4 | L |
| 5.O.1 | R1 Observability | 6 | M |
| 5.O.2 | R1 Test Gap Closure | 5 | M-L |
| 5.S.1 | Storage Housekeeping | 5 | S-M |
| **TOTAL** | | **72 issues** | |

### Critical Path

The fastest path to "the system learns what's important to THIS family" is:

```text
5.P.1 (3-4 days) -> 5.H.1 (2-3 days) -> 5.F.1 (5-7 days) -> 5.F.2 (3-5 days) = ~3-4 weeks
```

**5.P.1 is the new gate zero.** Without a production weight store adapter, learned weights
are invisible to R1 and R3. Nothing else in the plan functions without it.

The weight learner alignment (5.W.1 + 5.W.2) is a separate track that enables
per-family personalization of the CONFIG_B weights themselves.

---

## Risk Register

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|------------|--------|------------|
| R-H-001 | Reinforcement cycle creates runaway inflation (importance -> edge weight -> importance -> ...) | Medium | High | Soft saturation in Hebbian + boost cap in R1 + convergence proof (5.F.2.2) |
| R-H-002 | R1 latency exceeds 30ms budget with KG edge lookup | Medium | Medium | Per-cycle batch lookup (one DB call, not per-event); cache edges in memory |
| R-H-003 | Grounding signals unavailable for weight learner training for months | High | Medium | Weight learner stays on CONFIG_B static defaults (proven by POC); no regression |
| R-H-004 | Edge decay too aggressive, loses meaningful long-term relationships | Low | High | decay_rate=0.01 means 90 days to lose 60%; feature flag to disable; seasonal patterns get special handling |
| R-H-005 | 4-to-8 component alignment breaks existing weight learner tests | Medium | Low | Comprehensive regression; old learner tests updated in 5.W.1.5 |
| R-H-006 | Anti-Hebbian signals from P06 don't exist yet (P06 not implemented) | High | Medium | Anti-Hebbian feature flag off by default; R4 works without P06 feedback |
| R-P-001 | R3 production store still uses InMemoryLearnedWeightsStore | Confirmed | High | 5.P.3 replaces with PgLearnedWeightsStore; R3 novelty bonuses lost each cycle until fixed |
| R-P-002 | Two weight-store protocols cause adapter complexity | Confirmed | Medium | Single adapter class implements both protocols; param_key namespace prevents collision |
| R-P-003 | Pipeline contract describes non-existent formula + phase | Confirmed | Medium | 5.P.2 aligns contract with CONFIG_B reality; consumers reading contract get wrong info until fixed |
