"""Apply enrichment blocks for all Milestone 5 issues (19 issues across 3 prerequisites + 3 epics)."""

import pathlib

f = pathlib.Path(r"D:\familyos\docs\plans\R2_EPISODIC_INTEGRATION_EPIC_PLAN.md")
content = f.read_text(encoding="utf-8")
APOS = "\u2019"  # Unicode right single quotation mark

replacements = 0


def do_replace(old, new, label):
    global content, replacements
    if old not in content:
        print(f"ERROR: {label} old text not found!")
        # Print surrounding context to help debug
        return
    content = content.replace(old, new, 1)
    replacements += 1
    print(f"{label} enrichment applied.")


# =============================================================================
# MILESTONE 5 PREREQUISITE ISSUES (3 issues)
# =============================================================================

# --- Issue 5.0.1 ---
do_replace(
    "| Success criteria | All five fields are accessible through `EventAdapter` with the same fallback defaults as `P03EventState`. |\n\n##### Issue 5.0.2",
    """| Success criteria | All five fields are accessible through `EventAdapter` with the same fallback defaults as `P03EventState`. |

**Codebase Reality** (verified 2026-03-07):

`P03EventState` carries all five fields:
- `source_reliability` (L230, float, default=1.0)
- `activity_type_confidence` (L191, float, default=0.0)
- `intent_confidence` (L195, float, default=0.0)
- `k1_signal_version` (L215, str, default="2.0")
- `temporal_source` (L220, str, default="")

`EventAdapter` (r2_episodic_integrator.py L123-L320) exposes 22 signal properties but NONE of the five reliability/provenance fields. The adapter delegates to `self.event` (P03EventState) for all other fields via `@property` accessors.

`temporal_source` is accessed once in R2 outside the adapter: `getattr(_evt, "temporal_source", "")` at r2_episodic_integrator.py L525, directly on the raw P03EventState object -- violating the adapter abstraction pattern used everywhere else.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 12.6: `source_reliability` 0/1360 coverage, `k1_signal_version` 0/1360, `temporal_source` 0/1360. Only `confidence` has coverage (1360/1360, homogeneous mean=0.90). M5-RSCH-05/06/07 are BLOCKED because these signals are not yet populated by K1. Adding adapter properties is safe (pure exposure, no behavior change) and prepares the surface for when K1 populates them.

**Implementation Detail**:

1. Add five `@property` accessors to EventAdapter following the existing pattern (e.g., `salience_score` at L272):
   - `source_reliability -> float`: `return self.event.source_reliability` (default 1.0)
   - `activity_type_confidence -> float`: `return self.event.activity_type_confidence` (default 0.0)
   - `intent_confidence -> float`: `return self.event.intent_confidence` (default 0.0)
   - `k1_signal_version -> str`: `return self.event.k1_signal_version` (default "2.0")
   - `temporal_source -> str`: `return self.event.temporal_source` (default "")
2. Replace the raw `getattr(_evt, "temporal_source", "")` at L525 with adapter property access.
3. Tests: each property returns P03EventState value when present, default when absent. No clustering behavior change from adding properties alone.
4. No CentroidableEvent extension needed -- these fields serve gating, not centroid weighting.

##### Issue 5.0.2""",
    "Issue 5.0.1",
)

# --- Issue 5.0.2 ---
do_replace(
    "| Success criteria | Adaptive distance weight key schema is documented, collision-free, and compatible with the existing `SyscallLearnedWeightsStore` or its replacement. |\n\n##### Issue 5.0.3",
    """| Success criteria | Adaptive distance weight key schema is documented, collision-free, and compatible with the existing `SyscallLearnedWeightsStore` or its replacement. |

**Codebase Reality** (verified 2026-03-07):

`stores.py` (124 lines, 2 store classes):
- `SyscallWeightStore` (L23-L83): serves R1 ImportanceScorer. Uses prefix-key pattern: caller provides `param_prefix` (e.g. `"importance_"`), syscall `learned_weights_query(space_id, param_prefix)` returns matching rows.
- `SyscallLearnedWeightsStore` (L86-L124): serves R3 NoveltyBonusLearner. Uses exact-key pattern: `learned_weights_get(space_id, param_key)`, `learned_weights_upsert(space_id, param_key, value, prior_value)`.

R2 uses NEITHER store. It calls `ctx.syscalls.set_learned_param()` directly at L1659 (`"dbscan_eps"`) and L1687 (`"dbscan_min_samples"`). This is a third key pattern (direct syscall, no store wrapper).

Four control planes exist/planned, all sharing `st_learned_weights`:
1. R1 importance weights: prefix-key `"importance_*"` via SyscallWeightStore
2. R2 clustering params: exact-key `"dbscan_eps"`, `"dbscan_min_samples"` via direct syscall
3. R3 novelty weights: exact-key via SyscallLearnedWeightsStore
4. R2 adaptive distance weights: NOT YET DEFINED

**Research Evidence**:

M5-RSCH-03/04: Context-adaptive weights NEUTRAL -- no adaptive policy beats static 0.45/0.25/0.30 (post-M3 weights). Stability: score_std=0.0 across 5 cycles. This means adaptive distance weights may never be persisted (if static wins), but the key schema must be designed in case they are needed.

**Implementation Detail**:

1. Recommended key schema: `"dist_weight_<dimension>"` prefix (e.g., `"dist_weight_semantic"`, `"dist_weight_temporal"`, `"dist_weight_narrative"`). Clearly namespaced, collision-free with R1 `"importance_"`, R2 `"dbscan_"`, R3 novelty keys.
2. Decision: reuse `SyscallLearnedWeightsStore` with the `"dist_weight_"` prefix. No new store class needed -- the exact-key get/upsert pattern is sufficient.
3. Add key-collision regression test: assert `"dist_weight_"` keys never collide with `"importance_"`, `"dbscan_"`, or R3 patterns.
4. Since M5-RSCH-03 says static weights win, this store path may remain unpopulated. Design it as a ready-but-dormant surface.

##### Issue 5.0.3""",
    "Issue 5.0.2",
)

# --- Issue 5.0.3 ---
do_replace(
    "| Success criteria | Test inventory exists, R4 regression surface is protected, and R2-specific gap list is ready for Issues 5.1.1-5.1.5. |\n\n#### Epic 5.1 Issue Execution Checklist",
    """| Success criteria | Test inventory exists, R4 regression surface is protected, and R2-specific gap list is ready for Issues 5.1.1-5.1.5. |

**Codebase Reality** (verified 2026-03-07):

`hebbian_learner.py` (L256, HebbianLearner class): pure computation, no storage. Methods: extract_cooccurrences (L344), update_edge_weight (L432), compute_initial_weight (L468), apply_decay (L483), apply_anti_decay (L525), process_batch (L642), normalize_weight (L722), weight_interpretation (L733).

`HebbianConfig` (L39-L81): learning_rate=0.1, decay_rate=0.01, max_weight=1.0, min_weight=0.01, anti_learning_rate=0.15, explicit_correction_multiplier=1.3, prune_threshold=0.05.

Existing test surface (test_r1_hebbian_learner.py): 10 test classes, ~50+ test methods covering:
- Config validation (5 tests)
- NER entity parsing (8 tests)
- Co-occurrence extraction (9 tests: actor-actor, actor-location, actor-topic, overrides)
- Edge weight update (7 tests: basic, soft saturation, cap, importance variations)
- Time decay (5 tests: exponential formula, prune threshold)
- Anti-Hebbian decay (8 tests: all 4 signal types, explicit correction, prune, confidence scaling)
- Batch processing (5 tests: empty, single pair, aggregation, event state updates)
- Utility methods (2 tests)
- Full workflow (1 test: update then anti-Hebbian until prune)

Additional hebbian references: test_reinforcement_cycle.py (HebbianLearner used in R1+R4 cycle), test_r1_metrics.py (hebbian edge counters, weight distribution), test_r4_integration.py (merge threshold check).

**R2-specific gaps identified**:
1. No test for bounded boost caps (how Hebbian weight translates to distance modifier)
2. No test for stale-edge handling in an R2 context (old co-occurrence applied to new batch)
3. No test for empty st_cooccurrence / cold start behavior
4. No test for R2-specific contamination scenarios (historically co-occurring but currently distinct contexts)
5. No test for Hebbian boost + rescue interaction
6. No test for Hebbian boost + 6D (or 3D) distance integration

**Research Evidence**:

M5-RSCH-01+02: Hebbian boost formula: `d_hebbian = d_ensemble * (1 - min(affinity * scale, cap))`. Production params: scale=0.10, cap=0.05, min_count=1. The existing HebbianLearner tests cover edge weight computation but NOT the distance-modifier formula. The boost function is a new layer between HebbianLearner output and CompositeDistance input.

**Implementation Detail**:

1. Catalog all 50+ existing tests as the R4 regression baseline (already done above).
2. Add R2-gap tests:
   - Bounded boost cap: `d * (1 - min(w * 0.10, 0.05))` for various weights
   - Stale edge: weight after decay < threshold, boost should be zero
   - Cold start: no co-occurrence data, boost_factor = 1.0 (neutral)
   - Contamination: same-participant-different-context pairs should not have co-occurrence edges
3. Do NOT modify HebbianLearner itself until Issue 5.1.1. This issue is baseline + gap analysis only.

#### Epic 5.1 Issue Execution Checklist""",
    "Issue 5.0.3",
)

# =============================================================================
# EPIC 5.1: Hebbian Distance Boost (5 issues)
# =============================================================================

# --- Issue 5.1.1 ---
do_replace(
    "| Success criteria | The boost function is mathematically explicit, bounded, and compatible with the 6D distance semantics. |\n\n##### Issue 5.1.2",
    """| Success criteria | The boost function is mathematically explicit, bounded, and compatible with the 6D distance semantics. |

**Codebase Reality** (verified 2026-03-07):

`CompositeDistance` (composite_distance.py L152): purely static 2-component formula: `semantic_weight * cosine + temporal_weight * time_dist`. No modifier hook, no post-sum multiplier, no Hebbian reference. The distance is returned as a scalar float from `compute()` (L186) and `compute_from_arrays()` (L226).

Contract (consolidation.episodic_clusterer.v1.yaml L38): declares `boost_factor = 1 - (cooccurrence_weight * edge_weight)` with `cooccurrence_weight: 0.2`. This was a design-time formula that was never implemented.

HebbianLearner (hebbian_learner.py L432): computes edge weights in [0, 1] via soft saturation: `delta = lr * (max_weight - current_weight) * importance`. The edge weight itself is NOT a distance modifier -- it needs a translation layer.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 12.3: Research validated a multiplicative modifier: `d_hebbian = d_ensemble * (1 - min(affinity * boost_scale, boost_cap))`. Production params: scale=0.10, cap=0.05, min_count=1. This means max distance reduction is 5% (cap=0.05), applied multiplicatively AFTER the base distance is computed.

Key findings: 8/8 scenarios (from 5/8 baseline), zero contamination. All scale values >= 0.10 achieve 8/8. All cap values achieve 8/8. Conservative params minimize risk.

The contract formula (`1 - (0.2 * weight)`) would allow up to 20% reduction -- research proves 5% cap is sufficient and safer.

**Implementation Detail**:

1. The boost is a multiplicative post-modifier on CompositeDistance output: `d_final = d_base * (1 - min(affinity * 0.10, 0.05))`.
2. Add a `hebbian_boost` parameter to `compute()` and `compute_from_arrays()`: `Optional[float] = None`. When provided, multiply the final distance by `(1 - boost_value)`. When None, return unmodified distance (backward compatible).
3. OR: add a separate `apply_hebbian_boost(distance, edge_weight)` function that wraps the formula.
4. Update contract formula from `1 - (0.2 * weight)` to `1 - min(0.10 * weight, 0.05)` to match research.
5. Tests: no-history (factor=1.0), weak history (small reduction), strong history (capped at 5%), zero-weight edge (no effect).

##### Issue 5.1.2""",
    "Issue 5.1.1",
)

# --- Issue 5.1.2 ---
do_replace(
    "| Success criteria | Hebbian influence is gated by evidence and recency rather than treated as timeless truth. |\n\n##### Issue 5.1.3",
    """| Success criteria | Hebbian influence is gated by evidence and recency rather than treated as timeless truth. |

**Codebase Reality** (verified 2026-03-07):

`HebbianConfig` (L39-L81): `decay_rate=0.01` (per-day exponential), `min_weight=0.01` (prune threshold), `prune_threshold=0.05` (archive threshold). `apply_decay()` (L483): `new_weight = weight * exp(-decay_rate * days)`. Edges below `min_weight` after decay are pruned.

`KGEdge` (L124): stores `weight`, `count`, `last_updated`, `source_algorithm="co_occurrence"`, `relation_type`. The `count` field tracks how many times the co-occurrence has been observed.

The learner already has evidence gating (count) and recency gating (decay + last_updated) built into its edge model. But these operate at the edge-update level, not at the boost-application level. When R2 reads an edge weight, it gets the current weight (already decayed) but has no minimum-evidence threshold before applying the boost.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 12.3: min_count=1 is the research winner -- ALL thresholds (1-20) achieve 8/8 scenarios. This means a single co-occurrence is sufficient evidence. Recency decay: raw vs decay are equivalent (both 8/8). The conservative choice is still to apply decay, but the evidence threshold is effectively 1.

Research co-occurrence graph: 27 edges, top edges saturated at weight=1.0 (e.g., person_maya + loc:place_home = 548 co-occurrences). The corpus is dense enough that evidence thresholds don't discriminate.

**Implementation Detail**:

1. Production evidence policy: min_count=1 (research-validated), but apply time-based decay.
2. At boost-application time: check `edge.count >= min_count AND edge.weight >= min_weight`. If either fails, boost_factor = 1.0 (neutral).
3. Stale-edge handling: if `edge.last_updated` is older than a configurable window (e.g., 90 days), attenuate boost by staleness factor OR skip entirely.
4. Archive handling: edges at prune_threshold (0.05) should not contribute boost -- they are candidates for removal.
5. Tests: fresh strong edge (full boost), stale strong edge (attenuated), fresh weak edge (minimal boost), below-threshold edge (no boost), archived edge (no boost).
6. Future: if corpus diversity increases, re-evaluate whether min_count=1 is still safe.

##### Issue 5.1.3""",
    "Issue 5.1.2",
)

# --- Issue 5.1.3 ---
do_replace(
    "| Success criteria | R2 can actually retrieve co-occurrence evidence safely and deterministically. |\n\n##### Issue 5.1.4",
    """| Success criteria | R2 can actually retrieve co-occurrence evidence safely and deterministically. |

**Codebase Reality** (verified 2026-03-07):

Contract declares `read:st_cooccurrence` (consolidation.episodic_clusterer.v1.yaml L17-18, p03_consolidation.v1.yaml L96) but R2 has ZERO references to st_cooccurrence, hebbian, or co-occurrence in r2_episodic_integrator.py.

HebbianLearner (L256) is pure computation -- it does NOT read from or write to any store. `process_batch()` (L642) returns `Dict[(src, tgt, rel), EdgeUpdate]` that callers must persist. The actual persistence happens in R1/R4, not R2.

`st_kg_edges` table (migrations 0033, 0069, 0070): stores `KGEdge` records with source_node, target_node, relation_type, weight, count, last_updated, source_algorithm. This is the backing store for co-occurrence data.

R2 would need to: (a) query st_kg_edges for entity pairs relevant to the current batch events, (b) extract the edge weights, (c) pass them into the distance computation as boost factors. None of this wiring exists.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 12.3: research used participant co-occurrence (person-person, person-location edges). The boost reads co-occurrence affinity between entity pairs that appear in the same batch. M5 exit gate G5: "research outputs sufficient to justify making st_cooccurrence real or removing the stale contract promise" -- partially met, as Hebbian boost works via participant co-occurrence without needing a separate st_cooccurrence table.

**Implementation Detail**:

1. R2 needs a batch-level co-occurrence preload: before distance matrix computation, query st_kg_edges for all entity pairs represented in the current batch.
2. Build an affinity lookup: `Dict[(entity_a, entity_b), float]` where value is the edge weight.
3. For each event pair (i, j) in the distance matrix: find all shared entities between events i and j, look up their co-occurrence weights, compute the aggregate affinity (e.g., max or mean of shared entity pair weights).
4. Apply boost: `d_final = d_base * (1 - min(affinity * 0.10, 0.05))`.
5. Fallback: if st_kg_edges is empty or query fails, affinity = 0 for all pairs, boost_factor = 1.0 (neutral). Log the fallback.
6. Capability enforcement: R2 must declare `read:st_kg_edges` in its capability set.
7. Query bound: limit preload to entities present in the current batch to avoid unbounded queries.
8. Tests: empty table (neutral), single pair with co-occurrence (boosted), capability enforcement, query error fallback.

##### Issue 5.1.4""",
    "Issue 5.1.3",
)

# --- Issue 5.1.4 ---
do_replace(
    "| Success criteria | Hebbian influence has a single documented operational role with bounded side effects. |\n\n##### Issue 5.1.5",
    """| Success criteria | Hebbian influence has a single documented operational role with bounded side effects. |

**Codebase Reality** (verified 2026-03-07):

R2 has three distinct decision surfaces where Hebbian could influence outcomes:

1. **Pairwise distance** (composite_distance.py `compute()`): determines cluster membership. Current: no Hebbian input. This is the primary research-validated integration point.

2. **Rescue** (episodic_hdbscan.py `_rescue_noise()` L359-L436): assigns noise events to nearest cluster if distance < rescue_threshold (0.3). Hebbian boost could lower the effective distance for co-occurring entities, making rescue more likely. This was NOT tested in research.

3. **Episode matching** (r2_episodic_integrator.py `_match_events_to_existing_episodes()` L1823): matches new events to existing episodes via embedding similarity. This is a different code path from clustering.

Contract (p03_consolidation.v1.yaml L171-172): `use_cooccurrence_boost: true, cooccurrence_weight: 0.2` -- declared for R2 clustering config, not rescue or matching.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 12.3: Hebbian boost was tested on pairwise distance only (d_hebbian = d_ensemble * modifier). Rescue and matching were not part of the M5 research surface. The +3 scenario improvement (5/8 -> 8/8) comes from distance modification alone.

**Implementation Detail**:

1. Primary role: PAIRWISE DISTANCE ONLY. Hebbian boost modifies the distance matrix before HDBSCAN clustering.
2. Rescue: do NOT apply Hebbian boost to rescue distance thresholds. Rescue already operates on the modified distance matrix (if distances shrink, rescue happens naturally). Applying boost twice would be double-counting.
3. Episode matching: do NOT apply Hebbian boost. Episode matching uses embedding similarity (cosine), not composite distance. Co-occurrence is irrelevant for vector-space matching.
4. Document the scope restriction: "Hebbian co-occurrence boost applies ONLY to build_distance_matrix() in CompositeDistance. It does NOT apply to rescue thresholds, episode matching, or centroid weighting."
5. Tests: verify boost affects clustering distance, verify rescue uses boosted distance matrix (indirect effect), verify episode matching is unaffected.

##### Issue 5.1.5""",
    "Issue 5.1.4",
)

# --- Issue 5.1.5 ---
do_replace(
    "| Success criteria | Hebbian distance boost is only approved if its contamination cost is explicitly acceptable in research and test results. |\n\n### Epic 5.2:",
    """| Success criteria | Hebbian distance boost is only approved if its contamination cost is explicitly acceptable in research and test results. |

**Codebase Reality** (verified 2026-03-07):

No contamination testing infrastructure exists in the production test suite. test_r2_integration.py (16 tests) covers clustering mechanics but no contamination scenarios. The research pipeline (poc/r2_phase_research/) has the replay harness and scenario evaluation framework.

R2 processes batches from P03EventState records hydrated from st_hipp_events. A contamination scenario requires: two events from the same participant that belong to DIFFERENT episodes (e.g., "Maya fears" vs "Maya preschool") -- Hebbian boost on person_maya edges could incorrectly merge these.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 12.3: Contamination analysis on 3 scenarios:
- `clean_maya_fears_arc`: 0.33 -> 1.00 (improved, not contaminated)
- `rescue_edge_family_overlap`: 0.83 -> 1.00 (improved)
- `within_entity_maya_fears_vs_preschool`: 0.75 -> 1.00 (improved -- the key contamination risk scenario showed IMPROVEMENT, not contamination)

Zero degraded scenarios out of 8 total. The conservative parameters (scale=0.10, cap=0.05) limit distance reduction to max 5%, which is not enough to force merging of genuinely separate contexts.

**Implementation Detail**:

1. Research APPROVES Hebbian boost with zero contamination.
2. Add production regression tests derived from research scenarios:
   - Same-participant, same-context events (should cluster together, boost helps)
   - Same-participant, different-context events (should remain separate, boost must not merge)
   - Cross-participant with location co-occurrence (shared places, different episodes)
3. Add a contamination metric: count of cross-episode event pairs that were incorrectly merged due to Hebbian boost.
4. Gate: if contamination metric exceeds threshold in production, disable Hebbian boost (fallback to boost_factor=1.0).
5. Replay regression: periodically replay the research corpus with production parameters to detect drift.

### Epic 5.2:""",
    "Issue 5.1.5",
)

# =============================================================================
# EPIC 5.2: Context-Adaptive Weights (5 issues)
# =============================================================================

# --- Issue 5.2.1 ---
do_replace(
    "| Success criteria | The adaptive policy is explicit enough that a reviewer can predict how weights move and why. |\n\n##### Issue 5.2.2",
    """| Success criteria | The adaptive policy is explicit enough that a reviewer can predict how weights move and why. |

**Codebase Reality** (verified 2026-03-07):

`CompositeDistance` (composite_distance.py L152): weights are fixed at construction via `DBSCANParams`. `semantic_weight = 1.0 - temporal_weight` (L85-L87), `temporal_weight = 0.3` default. The weight vector is [0.7, 0.3] for semantic/temporal. After M3, this becomes [0.45, 0.25, 0.30] for semantic/temporal/narrative (3D model).

No mechanism exists to change weights per-batch or per-context. The only adaptation surface is eps/min_samples via EpsAdjuster and MinSamplesAdjuster.

The discovery document (temp_r2_design.md) describes "global modifiers" that shift weights based on context (novelty, social density, narrative continuity), but none of this is implemented.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 12.4: No adaptive policy outperforms static weights. Tested policies:
- static (M3 baseline 0.45/0.25/0.30): 5/8 scenarios
- uniform (1/3 each): 7/8 -- better than static!
- novelty_boost: 5/8 (no improvement)
- social_boost: 5/8 (no improvement)
- narrative_boost: 5/8 (no improvement)
- temporal_spread: 5/8 (no improvement)
- composite: 5/8 (no improvement)

Uniform is the only policy that improves, and it is not adaptive -- it is a different static assignment. No context-sensitive rule provides benefit.

**Implementation Detail**:

1. RESEARCH VERDICT: Keep static weights. No adaptive policy justified.
2. However, the uniform result (7/8 > 5/8) suggests the M3 static weights may not be globally optimal. Consider a follow-up experiment to find the best static weight vector.
3. Do NOT implement adaptive weight policy infrastructure -- research proves it adds complexity without benefit.
4. If future corpus diversity changes this conclusion, re-run M5-RSCH-03.
5. Document the decision: "Context-adaptive distance weights rejected per M5-RSCH-03. Static weights retained. Uniform weights noted as potentially superior but not adopted pending further investigation."

##### Issue 5.2.2""",
    "Issue 5.2.1",
)

# --- Issue 5.2.2 ---
do_replace(
    "| Success criteria | Adaptive weights have a clear persistence model that does not reuse or confuse any existing key namespace across R1, R2, or R3. |\n\n##### Issue 5.2.3",
    """| Success criteria | Adaptive weights have a clear persistence model that does not reuse or confuse any existing key namespace across R1, R2, or R3. |

**Codebase Reality** (verified 2026-03-07):

`stores.py` (124 lines): Two stores in st_learned_weights:
- `SyscallWeightStore` (L23): R1, prefix-key `"importance_*"`. `get_weights(space_id, param_prefix)`.
- `SyscallLearnedWeightsStore` (L86): R3, exact-key. `get_weight(param_key, space_id)`, `upsert_weight(param_key, space_id, value, prior_value)`.
- R2 uses `ctx.syscalls.set_learned_param()` directly for `"dbscan_eps"` and `"dbscan_min_samples"`.

Four key namespaces in st_learned_weights: `importance_*` (R1), `dbscan_*` (R2 clustering), R3 novelty keys (various), and the proposed `dist_weight_*` (R2 adaptive).

**Research Evidence**:

M5-RSCH-03: Adaptive weights rejected. No persistence needed for a dormant feature. The store schema from Issue 5.0.2 remains ready-but-unpopulated.

**Implementation Detail**:

1. REDUCED SCOPE: Since adaptive weights are not being implemented (M5-RSCH-03 rejects them), the persistence model is a design-only deliverable.
2. Document the key schema: `"dist_weight_semantic"`, `"dist_weight_temporal"`, `"dist_weight_narrative"` using SyscallLearnedWeightsStore pattern.
3. Add key-collision test (from Issue 5.0.2) even though the keys will not be populated yet.
4. No migration needed -- st_learned_weights already supports arbitrary key strings.
5. If future research validates adaptive weights, the schema is ready for immediate use.

##### Issue 5.2.3""",
    "Issue 5.2.2",
)

# --- Issue 5.2.3 ---
do_replace(
    "| Success criteria | Adaptive weights influence the real 6D distance model and no legacy-only code path remains. |\n\n##### Issue 5.2.4",
    """| Success criteria | Adaptive weights influence the real 6D distance model and no legacy-only code path remains. |

**Codebase Reality** (verified 2026-03-07):

`CompositeDistance` (composite_distance.py L152) is currently 2D (semantic + temporal). After M3, it becomes 3D (semantic + temporal + narrative). The weight vector is hardcoded at construction via `DBSCANParams` and cannot be changed per-batch.

No weight injection hook exists. `compute()` (L186) reads `self._semantic_weight` and `self._temporal_weight` as instance attributes. To support adaptive weights, either: (a) pass weights per-call, or (b) rebuild the distance object per-batch with new weights.

**Research Evidence**:

M5-RSCH-03: No adaptive policy beats static weights. M5-RSCH-04: Both static and adaptive weights produce score_std=0.0 across 5 cycles -- zero variance. The research says adaptive weights are stable but unhelpful.

M3 proves 3D optimal (semantic 0.45 + temporal 0.25 + narrative 0.30), not 6D. The "6D model" assumption in this issue is stale -- M3 research reduced dimensionality.

**Implementation Detail**:

1. DEFERRED: Adaptive weight integration is deferred because M5-RSCH-03 rejects adaptive policies.
2. However, a weight-injection hook is still useful for future experimentation. Recommended: add optional `weights_override: Optional[Dict[str, float]]` parameter to `build_distance_matrix()` that overrides instance-level weights for that batch.
3. Update issue title from "6D" to "3D" to reflect M3 research outcome.
4. When M3 lands the 3D model, verify the weight-injection hook works for all three dimensions.
5. No production adaptive weight path until new research justifies it.

##### Issue 5.2.4""",
    "Issue 5.2.3",
)

# --- Issue 5.2.4 ---
do_replace(
    "| Success criteria | Adaptive weights and eps/min_samples learning are independent, observable, and separately testable. |\n\n##### Issue 5.2.5",
    """| Success criteria | Adaptive weights and eps/min_samples learning are independent, observable, and separately testable. |

**Codebase Reality** (verified 2026-03-07):

`_track_quality_and_adapt()` (r2_episodic_integrator.py L1597): sequentially calls:
1. `self._quality_tracker.compute_from_r2_output()` (quality metrics)
2. `self._eps_adjuster.adjust()` (eps adaptation, persisted at L1659)
3. `self._min_samples_adjuster.adjust()` (min_samples adaptation, persisted at L1687)

Both adjusters operate on quality metrics (silhouette, singleton_rate) and persist to `st_learned_weights` via `ctx.syscalls.set_learned_param()`. They are already independent from each other (different inputs, different outputs, different keys).

If adaptive distance weights were added, they would be a THIRD adaptation surface that must not interfere with eps/min_samples. The composition question: do you adapt weights first, then eps, or eps first, then weights?

**Research Evidence**:

M5-RSCH-03: Adaptive weights rejected, making this separation concern moot for production. M5-RSCH-04: stability is confirmed (score_std=0.0), so even if adaptive weights were added, they would not oscillate.

**Implementation Detail**:

1. REDUCED SCOPE: Adaptive weights not being implemented, so separation from eps/min_samples is a design note only.
2. Document the intended architecture: if adaptive weights are ever added, they must be a separate coordinator class (e.g., `DistanceWeightAdjuster`) invoked in `_track_quality_and_adapt()` BEFORE eps/min_samples adjustment (weights change distance distribution, which changes optimal eps).
3. Execution order: weights -> distance recomputation -> eps adjustment -> min_samples adjustment.
4. Observability: each adaptation surface logs independently with separate trace identifiers.
5. No code changes until research justifies adaptive weights.

##### Issue 5.2.5""",
    "Issue 5.2.4",
)

# --- Issue 5.2.5 ---
do_replace(
    "| Success criteria | Adaptive weighting can be frozen, rolled back, or bounded before it causes prolonged clustering drift. |\n\n### Epic 5.3:",
    """| Success criteria | Adaptive weighting can be frozen, rolled back, or bounded before it causes prolonged clustering drift. |

**Codebase Reality** (verified 2026-03-07):

Existing safety rails for eps/min_samples:
- EpsAdjuster: bounds [0.15, 0.40], momentum=0.9, cold_start skip at <100 clusters
- MinSamplesAdjuster: bounds [2, 5], singleton_rate thresholds

No rollback mechanism exists for either adjuster. Once a parameter is persisted via `set_learned_param()`, the old value is overwritten. `SyscallLearnedWeightsStore.upsert_weight()` (L110) takes `prior_value` for optimistic concurrency but does not maintain history.

**Research Evidence**:

M5-RSCH-04: stability confirmed -- score_std=0.0 across 5 cycles, weight variance negligible (sem_std=0.009, temp_std=0.005, narr_std=0.012). No oscillation detected. However, this was tested on a single corpus; production conditions may differ.

**Implementation Detail**:

1. REDUCED SCOPE: Adaptive weights not being implemented, so rollback design is hypothetical.
2. Design principles for when/if implemented:
   - Bounds: per-dimension weight must stay in [0.1, 0.6] (no dimension can dominate or disappear).
   - Change-rate limit: max delta per cycle (e.g., 0.05 per dimension per batch).
   - Rollback trigger: if composite quality drops by > 10% over 3 consecutive batches, freeze adaptive weights and revert to M3 static defaults.
   - History: maintain last N weight snapshots in st_learned_weights for rollback (e.g., `dist_weight_semantic_t-1`, `dist_weight_semantic_t-2`).
   - Freeze: config flag `enable_adaptive_distance_weights: bool = False` (default off).
3. For eps/min_samples (existing): consider adding a similar rollback mechanism as a separate improvement.

### Epic 5.3:""",
    "Issue 5.2.5",
)

# =============================================================================
# EPIC 5.3: Reliability And Provenance Gating (6 issues)
# =============================================================================

# --- Issue 5.3.1 ---
do_replace(
    "| Success criteria | Low-reliability events become less authoritative without disappearing from clustering entirely. |\n\n##### Issue 5.3.2",
    """| Success criteria | Low-reliability events become less authoritative without disappearing from clustering entirely. |

**Codebase Reality** (verified 2026-03-07):

`source_reliability` (P03EventState L230, float, default=1.0): NOT on EventAdapter. Not consumed by any R2 algorithm. CompositeDistance.compute() has no reliability parameter. Rescue (_rescue_noise) has no reliability check.

R1 importance_scorer.py uses reliability as a scoring factor, establishing precedent. The R1 pattern: `reliability_factor = max(0.3, source_reliability)` -- floor prevents total suppression.

The distance formula has no neutralization hook. "Neutralization toward uncertainty" means: when one or both events have low reliability, pull pairwise distance toward a neutral value (e.g., the mean distance for that batch) rather than trusting the computed distance.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 12.6: `source_reliability` has 0/1360 coverage in the corpus. M5-RSCH-05 is BLOCKED. Cannot validate reliability gating without K1-populated data. Deferral is the only research-backed option.

**Implementation Detail**:

1. BLOCKED: Cannot implement without K1-populated source_reliability data.
2. When K1 provides data, the implementation plan:
   - Add `source_reliability` property to EventAdapter (Issue 5.0.1).
   - In CompositeDistance: when `min(event_i.source_reliability, event_j.source_reliability) < threshold`, attenuate distance toward batch mean.
   - Attenuation formula: `d_final = reliability_factor * d_computed + (1 - reliability_factor) * d_neutral`, where `reliability_factor = min(r_i, r_j)` and `d_neutral = batch_mean_distance`.
   - Floor: reliability_factor >= 0.3 (R1 precedent), preventing total suppression.
3. Tests: stub with synthetic reliability values until K1 data is available.
4. Gate: M5-RSCH-05 must be run and passed before production deployment.

##### Issue 5.3.2""",
    "Issue 5.3.1",
)

# --- Issue 5.3.2 ---
do_replace(
    "| Success criteria | Activity-based clustering behavior is confidence-aware instead of label-literal. |\n\n##### Issue 5.3.3",
    """| Success criteria | Activity-based clustering behavior is confidence-aware instead of label-literal. |

**Codebase Reality** (verified 2026-03-07):

`activity_type_confidence` (P03EventState L191, float, default=0.0): NOT on EventAdapter. The field exists but is not consumed by any R2 clustering algorithm.

`activity_type` (P03EventState L185, str): on EventAdapter (L240). Used in R2 for logging and observation context but NOT as a distance modifier. After M3, activity_type may contribute to narrative or semantic distance.

`ingress_classify.py` (P02): produces activity_type and activity_type_confidence from UltraBERT classification. The confidence value reflects classifier certainty.

No distance modifier currently uses activity_type, so activity_type_confidence gating has nothing to gate yet. This issue depends on M3 or later epics adding activity-type-aware distance logic.

**Research Evidence**:

M5-RSCH-05/06/07 all BLOCKED (signals not in corpus or homogeneous). `activity_type_confidence` has coverage in the corpus (mapped from UltraBERT confidence) but is homogeneous (mean=0.90, all GREEN band). Cannot test confidence-gating behavior when confidence never varies.

**Implementation Detail**:

1. BLOCKED: No activity-type distance modifier exists to gate. And confidence data is homogeneous.
2. When M3 adds activity-type distance contribution:
   - Add `activity_type_confidence` to EventAdapter (Issue 5.0.1).
   - Scale the activity-type distance contribution by confidence: `activity_dist *= activity_type_confidence`.
   - When confidence is low (< 0.5), attenuate to zero (remove activity contribution, redistribute weight to other dimensions).
3. Tests: high-confidence activity match (full contribution), low-confidence (attenuated), zero-confidence (removed).
4. Depends on Issue 5.0.1 and M3 activity-type integration.

##### Issue 5.3.3""",
    "Issue 5.3.2",
)

# --- Issue 5.3.3 ---
do_replace(
    "| Success criteria | Intent confidence changes influence only the intent-driven parts of the model and do so predictably. |\n\n##### Issue 5.3.4",
    """| Success criteria | Intent confidence changes influence only the intent-driven parts of the model and do so predictably. |

**Codebase Reality** (verified 2026-03-07):

`intent_confidence` (P03EventState L195, float, default=0.0): NOT on EventAdapter. Not consumed by R2 clustering.

`intent_ultrabert` (P03EventState L194, str, default=""): NOT on EventAdapter. Available on ObservationContext (L83) for coherence and metadata.

No intent-driven distance modifier exists in CompositeDistance. After M3, intent may contribute to narrative distance via intent similarity. Until then, intent_confidence gating has nothing to gate.

**Research Evidence**:

M5-RSCH-05/06/07 BLOCKED. M4-RSCH-07 found intent signals are SUMMARY-ONLY for encoding. Intent confidence matters only if intent contributes to distance or coherence, which it currently does not.

**Implementation Detail**:

1. BLOCKED: No intent-driven distance modifier exists to gate.
2. When M3 or later adds intent to distance:
   - Add `intent_confidence` to EventAdapter (Issue 5.0.1).
   - Scale intent distance contribution by confidence: `intent_dist *= intent_confidence`.
   - Low-confidence fallback: remove intent contribution, redistribute weight.
3. For coherence (M4 Epic 4.4): if intent coherence dimension is added, gate it by intent_confidence.
4. Tests: high-confidence intent match, low-confidence attenuation, zero-confidence removal.
5. Depends on Issue 5.0.1 and a future intent-distance integration.

##### Issue 5.3.4""",
    "Issue 5.3.3",
)

# --- Issue 5.3.4 ---
do_replace(
    "| Success criteria | Version handling is deterministic, documented, and test-covered rather than implicit. |\n\n##### Issue 5.3.5",
    """| Success criteria | Version handling is deterministic, documented, and test-covered rather than implicit. |

**Codebase Reality** (verified 2026-03-07):

`k1_signal_version` (P03EventState L215, str, default="2.0"): NOT on EventAdapter. Not consumed by R2.

Current default "2.0" means all events appear to be the same version. No version-aware logic exists anywhere in R2. No version comparison, compatibility check, or segmentation.

The field is populated by K1 during MW (Memory Writer) processing. When K1 upgrades its signal pipeline, new events get a new version string while old events retain the old version. Mixed-version batches occur during K1 rollouts.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 12.6: `k1_signal_version` 0/1360 coverage (K1 versioned signal emission not implemented). M5-RSCH-06 BLOCKED. Cannot test mixed-version behavior when only one version exists.

**Implementation Detail**:

1. BLOCKED: K1 signal versioning not yet implemented.
2. When K1 provides versioned signals:
   - Add `k1_signal_version` to EventAdapter (Issue 5.0.1).
   - Define compatibility matrix: which version pairs can be clustered together?
   - Options: (a) neutralize version-specific signals for cross-version pairs, (b) segment batches by version before clustering, (c) treat all as compatible with degraded-confidence annotation.
   - Recommended: option (c) -- compatible with degraded annotation -- until research proves segmentation is needed.
3. Run M5-RSCH-06 when multiple versions exist in production data.
4. Tests: same-version batch (no effect), mixed-version batch (degraded annotation), incompatible versions (if defined).

##### Issue 5.3.5""",
    "Issue 5.3.4",
)

# --- Issue 5.3.5 ---
do_replace(
    "| Success criteria | Temporal provenance affects the authority of time-based clustering logic in a documented, bounded way. |\n\n##### Issue 5.3.6",
    """| Success criteria | Temporal provenance affects the authority of time-based clustering logic in a documented, bounded way. |

**Codebase Reality** (verified 2026-03-07):

`temporal_source` (P03EventState L220, str, default=""): NOT on EventAdapter as a property, but accessed raw via `getattr(_evt, "temporal_source", "")` at r2_episodic_integrator.py L525 for observability logging only.

P03EventState carries `temporal_source` values from the timestamp chain (R0 batch selector). Values: "mw_resolved" (highest quality), "ner_temporal", "event_time", "envelope_ts", "now" (lowest quality). R0 already uses temporal_source for timestamp quality stats logging.

Current R2 usage: temporal_source is logged but does NOT influence temporal distance computation. All events contribute equally to temporal distance regardless of timestamp provenance quality.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 12.6: `temporal_source` 0/1360 coverage (not yet propagated to st_hipp_events). M5-RSCH-07 BLOCKED. However, the field IS on P03EventState with values populated during P03 processing -- the research limitation is that the replay corpus does not contain the field.

The M2 timestamp chain work (R2_RESEARCH_FINAL.md Section 6) established provenance ordering: conversation_anchor_ms > event_time_utc > created_at. Temporal_source captures this ordering.

**Implementation Detail**:

1. PARTIALLY BLOCKED: field exists on P03EventState but M5-RSCH-07 not validated.
2. When research is unblocked:
   - Add `temporal_source` to EventAdapter (Issue 5.0.1, replacing raw getattr access).
   - Define provenance confidence mapping: `{"mw_resolved": 1.0, "ner_temporal": 0.8, "event_time": 0.6, "envelope_ts": 0.4, "now": 0.2, "": 0.5}`.
   - Attenuate temporal distance by provenance confidence: `temporal_conf = min(conf_i, conf_j)`. When temporal_conf is low, reduce temporal distance weight contribution (pull toward neutral).
   - Formula: `temporal_contribution = temporal_weight * temporal_conf * normalized_time_distance + temporal_weight * (1 - temporal_conf) * 0.5`.
3. Tests: mw_resolved pair (full temporal authority), now+now pair (attenuated), mixed provenance pair.
4. Gate: M5-RSCH-07 must run before production deployment.

##### Issue 5.3.6""",
    "Issue 5.3.5",
)

# --- Issue 5.3.6 ---
do_replace(
    "| Success criteria | Quality and observability outputs show when reliability/provenance issues materially shaped clustering. |\n\n#### Milestone 5 Research Exit Gate",
    """| Success criteria | Quality and observability outputs show when reliability/provenance issues materially shaped clustering. |

**Codebase Reality** (verified 2026-03-07):

`ClusterQualityMetrics` (cluster_quality.py L58-L155): 12 fields, no reliability or provenance awareness. The composite formula gives no weight to signal confidence or reliability. Quality output cannot distinguish "bad cluster" from "cluster degraded by low-confidence inputs."

`ClusterQualityTracker.compute_from_r2_output()` (L242-L276): inputs are batch_silhouette_score, cluster_count, noise_count. No reliability input.

R2 observability: r2_episodic_integrator.py logs temporal_source stats at L525 (raw getattr, not adapter), but this is informational logging, not integrated into quality metrics.

EpisodeCluster (phase_outputs.py L77-L161): no reliability or provenance fields. Member events carry reliability on P03EventState but this is not surfaced on the cluster.

**Research Evidence**:

M5-RSCH-05/06/07 all BLOCKED (signals not populated). Reliability propagation into quality outputs depends on Issues 5.3.1-5.3.5 implementing the gating logic first.

**Implementation Detail**:

1. BLOCKED: depends on Issues 5.3.1-5.3.5 landing first.
2. When gating logic is implemented:
   - Add `reliability_summary` to ClusterQualityMetrics: `{mean_reliability, min_reliability, low_confidence_event_count, degraded_cluster_count}`.
   - Per-cluster annotation: tag clusters where > 30% of events have low reliability.
   - Quality alert differentiation: "low coherence (genuine)" vs "low coherence (reliability-degraded)".
   - Observability: log per-batch reliability distribution alongside existing quality metrics.
3. Extend batch_coherence_summary (M4 Issue 4.4.2) with reliability overlay.
4. Tests: high-reliability batch (no degradation annotation), mixed-reliability batch (annotation present), all-low-reliability batch (strong annotation).

#### Milestone 5 Research Exit Gate""",
    "Issue 5.3.6",
)

# --- Write ---
f.write_text(content, encoding="utf-8")
print(f"\nAll {replacements} enrichments applied and saved.")
