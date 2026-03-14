"""Apply enrichment blocks for all Milestone 4 issues (31 issues across 6 epics)."""

import pathlib

f = pathlib.Path(r"D:\familyos\docs\plans\R2_EPISODIC_INTEGRATION_EPIC_PLAN.md")
content = f.read_text(encoding="utf-8")
APOS = "\u2019"  # Unicode right single quotation mark

replacements = 0


def do_replace(old, new, label):
    global content, replacements
    assert old in content, f"{label} old text not found!"
    content = content.replace(old, new, 1)
    replacements += 1
    print(f"{label} enrichment applied.")


# =============================================================================
# EPIC 4.1: Salience-Composite Centroid Weighting (7 issues)
# =============================================================================

# --- Issue 4.1.0 ---
do_replace(
    "| Success criteria | All encoding-strength terms use typed protocol access. No `getattr` fallback for fields that belong in the centroid contract. Protocol is coordinated with `EventLike` and `SplittableEvent`. |\n\n##### Issue 4.0.1",
    """| Success criteria | All encoding-strength terms use typed protocol access. No `getattr` fallback for fields that belong in the centroid contract. Protocol is coordinated with `EventLike` and `SplittableEvent`. |

**Codebase Reality** (verified 2026-03-07):

`CentroidableEvent` protocol (centroid_calculator.py L62-L83) has exactly 4 fields:
- `event_id`: str (L68)
- `timestamp`: int (L73)
- `embedding_768`: Optional[List[float]] (L78)
- `importance_score`: float (L83)

`compute_weights()` (L275-L326) reads only `importance_score` and `timestamp` from events. No other signal field is accessed. The 4-strategy enum (`WeightingStrategy` L49-L55): UNIFORM, IMPORTANCE, RECENCY, HYBRID.

`EventLike` protocol (composite_distance.py L120-L137) has 3 fields: event_id, timestamp, embedding_768. `SplittableEvent` (episode_splitter.py L112-L126) has 2 fields: event_id, timestamp. All three protocols are minimal and uncoordinated.

`EventAdapter` (r2_episodic_integrator.py L109-L309) already exposes salience_score (L272), affect_valence (L257), affect_arousal (L262), affect_dominance (L267), sentiment_score (L250), novelty_score is NOT exposed, memory_tier is NOT on P03EventState, source_type is NOT exposed. The adapter has the signals; the protocols do not declare them.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 11.3 (M4-RSCH-01): recency_exp wins with MRR=0.9006 (+6.6% vs hybrid). But Section 11.9 (M4-RSCH-07): ALL 9 cognitive/support signals are SUMMARY-ONLY -- baseline MRR=0.9975 is near-perfect with unweighted mean. The encoding-strength formula needs recency but not salience/elaboration/identity weighting on centroids. Protocol extension for those signals serves coherence (Epic 4.4) and metadata, not centroid weighting.

**Implementation Detail**:

1. Extend `CentroidableEvent` with Optional fields: salience_score, affect_valence, affect_arousal, affect_dominance, novelty_score, sentiment_score. All default None.
2. Do NOT add elaboration_depth, identity_relevance, memory_tier, source_type to CentroidableEvent -- M4-RSCH-07 proves they do not help encoding. Keep them on ObservationContext for coherence.
3. Coordinate with M3 `EventLike` extension: shared fields should use identical names and types.
4. Protocol compliance tests: EventAdapter satisfies enriched CentroidableEvent.
5. Missing-field tests: None defaults do not crash compute_weights().

##### Issue 4.0.1""",
    "Issue 4.1.0",
)

# --- Issue 4.0.1 ---
do_replace(
    "| Success criteria | `R2StagedOutput` has a single documented role (live, dead, or bridge) and M4 code implements that role consistently. |\n\n##### Issue 4.0.2",
    """| Success criteria | `R2StagedOutput` has a single documented role (live, dead, or bridge) and M4 code implements that role consistently. |

**Codebase Reality** (verified 2026-03-07):

`R2StagedOutput` (centroid_calculator.py L203-L270): dataclass with 7 fields (episode_candidates, cluster_count, noise_count, avg_cluster_size, total_events_processed, batch_silhouette_score, batch_cohesion_avg) plus methods add_candidate(), finalize(), singleton_rate, to_dict().

It is exported from `__init__.py` and referenced by `cluster_quality.py` `R2OutputProtocol` (L161-L167: batch_silhouette_score, cluster_count, noise_count). However, the live R2 path in r2_episodic_integrator.py builds `EpisodeCluster` objects directly via `_build_episode_cluster()` and returns them via `P03PhaseResult`. The live path calls `ClusterQualityTracker.compute_from_r2_output()` but passes a dict-like object, not an R2StagedOutput instance.

`R2StagedOutput` is effectively dead code -- defined, exported, protocol-referenced, but never instantiated by the live pipeline.

**Research Evidence**:

R2_RESEARCH_FINAL.md does not reference R2StagedOutput. The research pipeline builds its own output containers. M4-RSCH-05 (storage rehearsal) recommends json_blob for multi-centroid persistence -- this affects EpisodeCluster, not R2StagedOutput. The decision is architectural, not research-driven.

**Implementation Detail**:

1. Recommended option: DELETE. R2StagedOutput duplicates fields already on EpisodeCluster and P03PhaseResult.
2. Update R2OutputProtocol in cluster_quality.py to reference EpisodeCluster fields directly (cluster_count, noise_count from P03PhaseResult; silhouette from ClusterQualityMetrics).
3. Remove R2StagedOutput from __init__.py exports and centroid_calculator.py.
4. Verify no external consumer imports R2StagedOutput (grep across codebase).
5. Preserve R2StagedOutput test coverage (TestR2StagedOutput in test_r2_centroid_calculator.py) only if the equivalent behavior is tested elsewhere.

##### Issue 4.0.2""",
    "Issue 4.0.1",
)

# --- Issue 4.0.2 ---
do_replace(
    "| Success criteria | A decision exists about whether legacy strategy tests survive, get archived, or get replaced \u2014 before any strategy code changes. |\n\n##### Issue 4.1.1",
    """| Success criteria | A decision exists about whether legacy strategy tests survive, get archived, or get replaced \u2014 before any strategy code changes. |

**Codebase Reality** (verified 2026-03-07):

test_r2_centroid_calculator.py has 17 tests across 6 test classes:
- `TestWeightingStrategies` (5 tests): pin uniform (1/n), importance (higher score = higher weight), recency (most recent = highest), hybrid (0.7*importance + 0.3*recency), same-timestamps fallback.
- `TestCentroidComputation` (3 tests): L2 normalization, single-event centroid, no-embeddings error.
- `TestVarianceComputation` (3 tests): variance in [0,1], identical embeddings = 0, single event = 0.
- `TestCentroidResult` (3 tests): all fields populated, centroid_list property, empty returns zero.
- `TestEpisodeCandidate` (2 tests): field population, duration_ms property.
- `TestR2StagedOutput` (3 tests) + `TestEventUpdate` (1 test).

test_r2_integration.py has 16 tests covering end-to-end cluster production, semantic grouping, splitting, adaptive eps/min_samples adjustment, write structure, quality metrics, and distance matrix properties.

**Research Evidence**:

M4-RSCH-01 shows recency_exp (MRR=0.9006) replaces hybrid (MRR=0.8344). The 5 TestWeightingStrategies tests will need updating: uniform may remain as a baseline, importance stays, recency changes to exponential, hybrid gets replaced. M4-RSCH-03 REJECTS probability weighting, so no probability-related test additions needed.

**Implementation Detail**:

1. Snapshot current test assertions in a brief test-surface document before any changes.
2. Decision: REPLACE legacy strategy tests with encoding-strength equivalents. Archive old assertions as comments for regression reference.
3. Keep TestCentroidComputation, TestVarianceComputation, TestCentroidResult, TestEpisodeCandidate unchanged -- these are strategy-independent.
4. TestR2StagedOutput tests: if Issue 4.0.1 deletes R2StagedOutput, these tests are removed with it.
5. test_r2_integration.py tests remain as end-to-end regression baselines.

##### Issue 4.1.1""",
    "Issue 4.0.2",
)

# --- Issue 4.1.1 ---
do_replace(
    "| Success criteria | The new strategy is explicit, bounded, fallback-safe, and supported by offline research artifacts rather than intuition. |\n\n##### Issue 4.1.2",
    """| Success criteria | The new strategy is explicit, bounded, fallback-safe, and supported by offline research artifacts rather than intuition. |

**Codebase Reality** (verified 2026-03-07):

`compute_weights()` (L275-L326) implements 4 strategies via a match/case on `WeightingStrategy`:
- UNIFORM (L289): `np.ones(n) / n`
- IMPORTANCE (L292-L297): `importance_score + 0.01`, normalized
- RECENCY (L299-L306): linear `(ts - min) / (max - min + 1)` + 0.1 floor, normalized; uniform fallback for equal timestamps
- HYBRID (L308-L322): `0.7 * importance + 0.3 * recency + 0.01`, normalized

The recency implementation is linear normalization, which is the WORST performer in research (linear_recency MRR=0.5990 -- collapses). The hybrid implementation uses fixed 0.7/0.3 weights with no fallback chain.

No signal-availability mask tracking. No per-event sparse-data handling. No weight redistribution for missing signals.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 11.3 (M4-RSCH-01): recency_exp wins (MRR=0.9006). The exponential decay formula emphasizes recent events without the extreme bias of linear normalization. Section 11.9 (M4-RSCH-07): ALL cognitive/support signals are SUMMARY-ONLY (baseline MRR=0.9975) -- the encoding-strength formula should NOT include salience, novelty, identity, or affect weighting. M4-RSCH-03 REJECTS probability weighting.

The approved formula is effectively: `weight_i = exp(-decay * (t_max - t_i) / t_range)`, normalized to sum=1. This is a 1-factor model (recency only), not a multi-factor encoding-strength formula.

**Implementation Detail**:

1. Add RECENCY_EXP strategy to WeightingStrategy enum.
2. Implement exponential decay: `w_i = exp(-lambda * (t_max - t_i) / (t_max - t_min + 1))` with configurable decay lambda.
3. Preserve UNIFORM as a baseline. IMPORTANCE and HYBRID can remain for backward compatibility but are not the production path.
4. No multi-factor encoding-strength formula needed -- research proves recency is the only weighting factor that helps.
5. Fallback: if all timestamps equal, return uniform weights (same as current RECENCY fallback).
6. Tests: recency_exp produces higher weights for recent events, exponential vs linear comparison, equal-timestamp fallback, configurable decay parameter.

##### Issue 4.1.2""",
    "Issue 4.1.1",
)

# --- Issue 4.1.2 ---
do_replace(
    "| Success criteria | Encoding inputs are explicit, typed, and future Milestone 4.6 fields have a clear path into centroid weighting via the protocol. |\n\n##### Issue 4.1.3",
    """| Success criteria | Encoding inputs are explicit, typed, and future Milestone 4.6 fields have a clear path into centroid weighting via the protocol. |

**Codebase Reality** (verified 2026-03-07):

EventAdapter (r2_episodic_integrator.py L109-L309) exposes 22 properties. For centroid weighting, the only input needed is `timestamp` (already on CentroidableEvent via L166). `importance_score` is also already on the protocol (L200 via P03EventState.importance_score).

The research result (M4-RSCH-07: all signals SUMMARY-ONLY) means the centroid formula only needs timestamp access, which is already on the protocol. The "expose weighting inputs cleanly" issue is largely resolved by M4-RSCH-07 proving those inputs are not needed.

However, for Epic 4.4 (coherence), ObservationContext already carries the richer signal surface: salience_score (L90), novelty_score (L92), affect_valence (L74), affect_arousal (L75), sentiment_score (L72), intent_ultrabert (L83), social_context (L115), location_name (L107). ObservationContext is built post-clustering by `_build_episode_cluster()` at L1363-L1369 via `ObservationContext.from_event(e.event)`.

**Research Evidence**:

M4-RSCH-01: recency_exp only needs timestamp. M4-RSCH-07: no signal improves encoding beyond MRR=0.9975 baseline. The "weighting inputs" issue scope shrinks to: ensure CentroidableEvent has timestamp (already done) and prepare a clear path for coherence inputs via ObservationContext (already done by the existing from_event() factory).

**Implementation Detail**:

1. This issue has reduced scope post-research: CentroidableEvent already has timestamp for recency_exp.
2. Verify EventAdapter satisfies CentroidableEvent protocol (add protocol compliance test).
3. Ensure M3 EventLike and CentroidableEvent share consistent field names for overlapping fields.
4. For coherence inputs: document that ObservationContext.from_event() is the input path for Epic 4.4, not CentroidableEvent.
5. No new EventAdapter properties needed specifically for centroid weighting.

##### Issue 4.1.3""",
    "Issue 4.1.2",
)

# --- Issue 4.1.3 ---
do_replace(
    "| Success criteria | Recency helps representation without collapsing the centroid onto the last event in the cluster. |\n\n##### Issue 4.1.4",
    """| Success criteria | Recency helps representation without collapsing the centroid onto the last event in the cluster. |

**Codebase Reality** (verified 2026-03-07):

Current recency weighting (compute_weights RECENCY, L299-L306): `weight = (ts - min_ts) / (max_ts - min_ts + 1) + 0.1`, normalized. This is linear normalization to [0.1, ~1.1] range. For clusters spanning hours, the most recent event gets ~1.1 weight while the earliest gets ~0.1 -- a 10:1 ratio that can dominate the centroid.

The HYBRID strategy (L308-L322) mitigates this with `0.7 * importance + 0.3 * recency`, but importance_score is coarse (often uniform) so recency still dominates.

The floor of 0.1 prevents total erasure of early events but does not prevent disproportionate influence of the last event.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 11.3: linear_recency MRR=0.5990 (WORST strategy -- extreme recency bias collapses centroid onto last event). recency_exp MRR=0.9006 (BEST -- exponential decay naturally bounds recency influence). The exponential decay curve gives recent events higher weight while keeping early events meaningfully represented.

The research directly validates this issue: linear recency is harmful, exponential recency is beneficial.

**Implementation Detail**:

1. Replace RECENCY strategy logic with exponential decay: `w_i = exp(-lambda * (t_max - t_i) / (t_max - t_min + eps))`.
2. Configurable lambda parameter (research used specific decay rate -- extract from r2_final_pipeline.py).
3. Floor: exp(-lambda * 1.0) for the oldest event ensures minimum contribution (never zero).
4. The exp decay naturally bounds the ratio between newest and oldest events, unlike linear.
5. Preserve uniform fallback for equal timestamps.
6. Test: verify newest/oldest weight ratio is bounded (e.g., <= 5:1 for typical lambda).

##### Issue 4.1.4""",
    "Issue 4.1.3",
)

# --- Issue 4.1.4 ---
do_replace(
    "| Success criteria | The approved weighting strategy outperforms or clearly matches the current baseline on replay metrics and edge cases. |\n\n### Epic 4.2:",
    """| Success criteria | The approved weighting strategy outperforms or clearly matches the current baseline on replay metrics and edge cases. |

**Codebase Reality** (verified 2026-03-07):

The current production centroid uses HYBRID strategy (0.7*importance + 0.3*recency). No retrieval benchmarks exist in the production test suite -- test_r2_centroid_calculator.py tests weight computation mechanics (sums to 1.0, relative ordering) but not retrieval quality or representative quality.

test_r2_integration.py has `test_centroid_l2_normalized` and `test_centroid_variance_low_for_similar_events` but these test centroid properties, not retrieval effectiveness.

The research pipeline (r2_final_pipeline.py) contains the MRR benchmarking infrastructure that can be adapted for production validation.

**Research Evidence**:

M4-RSCH-01: recency_exp MRR=0.9006 vs hybrid MRR=0.8344 -- a +6.6% improvement on 246 clusters from the replay corpus. This is the validation result. The replay dataset uses the same life_events.jsonl corpus (1360 events, 32 sequences) that established the M2/M3 baseline.

M4-RSCH-07: unweighted mean MRR=0.9975 -- near-perfect with the corrected clustering pipeline. This suggests that clustering quality (from M2/M3) matters more than centroid weighting. recency_exp still helps for edge cases where event ordering matters.

**Implementation Detail**:

1. Research validation is already complete (M4-RSCH-01). The production implementation task is: integrate recency_exp into CentroidCalculator and verify it reproduces the research MRR on the replay corpus.
2. Add a focused production test: create a cluster with known temporal ordering, verify the centroid is pulled toward recent events but not collapsed onto them.
3. Preserve HYBRID as a fallback strategy during rollout. If recency_exp regresses on production data, HYBRID is the fallback.
4. Add retrieval-oriented regression fixtures from the research corpus as permanent test cases.

### Epic 4.2:""",
    "Issue 4.1.4",
)

# =============================================================================
# EPIC 4.2: Multi-Centroid Episode Representation (5 issues)
# =============================================================================

# --- Issue 4.2.1 ---
do_replace(
    "| Success criteria | There is one clear schema plan that production code, writes, and queries can all implement consistently. |\n\n##### Issue 4.2.2",
    """| Success criteria | There is one clear schema plan that production code, writes, and queries can all implement consistently. |

**Codebase Reality** (verified 2026-03-07):

`EpisodeCluster` (phase_outputs.py L77-L161): single `centroid_embedding_id: Optional[str]` at L93. No field for secondary centroids, centroid metadata, or centroid set.

`EpisodeCandidate` (centroid_calculator.py L121-L196): single `centroid_embedding: Optional[List[float]]` at L147 and `centroid_embedding_id: Optional[str]` at L150.

`st_epi` schema (0027_st_epi.py): single `embedding_id` column (L94, Text, nullable). 33 total columns, 4 indexes. No centroid_metadata or secondary embedding columns.

`truth_write_assembler.py` (L517-L530): resolves single `embedding_id` from `cluster.centroid_embedding_id`, falls back to first event's embedding_id.

All four surfaces assume exactly one embedding per episode.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 11.7 (M4-RSCH-05): json_blob wins. Recommended schema: add `centroid_metadata` JSON column to st_epi containing secondary centroid references (emotional_peak, narrative_anchor, start, end). MRR gap: +0.2147 vs single centroid (exceeds 0.05 threshold). json_blob is simpler than side_table, same MRR, backward compatible.

Section 11.4 (M4-RSCH-02): best_of_all (5-way) MRR=0.9627. Emotional_peak found in 246/246 clusters (100%), narrative_anchor in 113/246 (45.9%). Primary + emotional_peak + narrative_anchor captures the most retrieval-relevant perspectives.

**Implementation Detail**:

1. Add `centroid_metadata: Optional[Dict[str, Any]]` to EpisodeCluster with structure: `{"emotional_peak": {"embedding_id": str, "event_id": str}, "narrative_anchor": {"embedding_id": str, "event_id": str}, ...}`.
2. Add `centroid_metadata` JSON column to st_epi via new Alembic migration.
3. Preserve `centroid_embedding_id` as the canonical primary centroid FK (backward compatible).
4. Secondary centroids reference existing st_vec entries (event embeddings) -- no new vector generation needed.
5. EpisodeCandidate gets optional `secondary_centroids` dict alongside existing centroid fields.

##### Issue 4.2.2""",
    "Issue 4.2.1",
)

# --- Issue 4.2.2 ---
do_replace(
    "| Success criteria | Secondary centroids are deterministic, interpretable, and limited to the researched set that actually helps. |\n\n##### Issue 4.2.3",
    """| Success criteria | Secondary centroids are deterministic, interpretable, and limited to the researched set that actually helps. |

**Codebase Reality** (verified 2026-03-07):

CentroidCalculator.compute() (L436-L535) produces a single centroid via weighted mean of member embeddings. No secondary centroid computation exists.

`_build_episode_cluster()` (r2_episodic_integrator.py, ~176 lines) already iterates all cluster events and has access to: timestamps (for start/end), sentiment_score (for emotional peak), narrative_thread_id (for narrative anchor). The selection logic for secondary centroids can reuse this iteration.

ObservationContext.from_event() (observation_context.py) carries sentiment_score, affect_valence, affect_arousal for emotional peak selection.

**Research Evidence**:

M4-RSCH-02: best_of_all (5-way: primary + start + end + emotional_peak + narrative_anchor) MRR=0.9627. But primary+emotional_peak+narrative_anchor MRR=0.9003, while primary_only MRR=0.9140 -- adding emo+nar without start+end actually hurts slightly. Start+end alone MRR~0.35 (terrible as standalone, but useful in combination).

Emotional_peak: select event with max |affect_valence| or max affect_arousal. 100% coverage (every cluster has at least one event with affect data).
Narrative_anchor: select event with the dominant narrative_thread_id. 45.9% coverage.
Start/end: select events with min/max timestamp. 100% coverage.

**Implementation Detail**:

1. Add secondary centroid selectors to CentroidCalculator or a new `SecondaryCentroidSelector` class.
2. Selection rules (deterministic):
   - `emotional_peak`: event with max `abs(affect_valence) + affect_arousal`
   - `narrative_anchor`: event with the most common narrative_thread_id in the cluster
   - `start`: event with min timestamp
   - `end`: event with max timestamp
3. Each selector returns the event's existing embedding_768 reference -- no new embedding computation.
4. Missing signal fallback: if narrative_thread_id is absent for all events, narrative_anchor is null.
5. Tests: short episodes (1-2 events where all selectors return the same event), competing emotional peaks, no-thread episodes.

##### Issue 4.2.3""",
    "Issue 4.2.2",
)

# --- Issue 4.2.3 ---
do_replace(
    "| Success criteria | R6/R7 can persist the approved centroid-set shape without breaking existing episodic writes. All three write surfaces handle multi-centroid or explicitly preserve single-centroid compatibility. |\n\n##### Issue 4.2.4",
    """| Success criteria | R6/R7 can persist the approved centroid-set shape without breaking existing episodic writes. All three write surfaces handle multi-centroid or explicitly preserve single-centroid compatibility. |

**Codebase Reality** (verified 2026-03-07):

Three write surfaces assume single-embedding semantics:

1. **truth_write_assembler.py** (L517-L530): Writes `embedding_id` from `cluster.centroid_embedding_id`. Falls back to first event embedding_id if centroid is None. Single field.

2. **EpisodicLayerWriter._insert()** (episodic.py L194-L303): INSERT SQL includes `embedding_text`, `embedding_vector`, `embedding_model`, `embedding_id`. All four are single-valued. The TextVectorCoordinator generates one text+vector pair per episode.

3. **truth_query_service._query_layer()** (L279-L367): `JOIN st_vec v ON t.embedding_id = v.embedding_id`. Single JOIN, single vector per episode.

st_epi schema has no centroid_metadata column (would need migration).

**Research Evidence**:

M4-RSCH-05: json_blob recommended. One new column (`centroid_metadata` JSONB) on st_epi. Backward compatible: old episodes have NULL centroid_metadata, query path falls back to primary embedding_id. MRR gap: +0.2147 justifies the schema change.

Write surface impact from research:
- TruthWriteAssembler: add centroid_metadata JSON field to the staged record
- EpisodicLayerWriter: write centroid_metadata JSON alongside primary embedding fields
- TruthQueryService: add optional secondary vector lookup for re-ranking (retrieval-time only)

**Implementation Detail**:

1. New Alembic migration: `ALTER TABLE st_epi ADD COLUMN centroid_metadata JSONB DEFAULT NULL`.
2. TruthWriteAssembler: write `centroid_metadata` JSON from EpisodeCluster.centroid_metadata. Null-safe (old code path produces NULL).
3. EpisodicLayerWriter._insert(): add `centroid_metadata` to INSERT SQL. The JSON contains references to existing st_vec entries, not new vectors.
4. TruthQueryService: Phase 1 -- no query change (primary embedding_id JOIN unchanged). Phase 2 -- add optional secondary centroid re-ranking at retrieval time.
5. Backward compatibility: episodes with NULL centroid_metadata behave exactly as today.
6. Tests: write with/without centroid_metadata, read old episodes (NULL metadata), mixed population.

##### Issue 4.2.4""",
    "Issue 4.2.3",
)

# --- Issue 4.2.4 ---
do_replace(
    "| Success criteria | Default consumers keep working, and richer consumers have a documented access pattern for additional centroids. |\n\n##### Issue 4.2.5",
    """| Success criteria | Default consumers keep working, and richer consumers have a documented access pattern for additional centroids. |

**Codebase Reality** (verified 2026-03-07):

`truth_query_service.py` find_candidates() (L216-L277) iterates all layers (st_hipp, st_sem, st_epi), queries each via _query_layer(), computes cosine similarity against query vector, returns top-k. For st_epi, this always uses the primary embedding_id.

`_query_layer()` (L279-L367) returns `(record_id, vector, vector_dim, confidence)` tuples. The vector is always the single primary embedding.

`r2_episodic_integrator.py` `_query_existing_episodes()` (L1717) and `_match_events_to_existing_episodes()` (L1823) also query st_epi by primary embedding_id for episode matching/reinforcement.

No consumer currently expects multiple vectors per episode.

**Research Evidence**:

M4-RSCH-02: best_of_all MRR=0.9627 vs primary_only MRR=0.9140. The +4.9% improvement comes from using the best-matching secondary centroid at retrieval time. Storage rehearsal (M4-RSCH-05): secondary centroids are only needed at retrieval time, not for reconciliation matching.

**Implementation Detail**:

1. Phase 1 (M4): Add an optional `use_secondary_centroids: bool` parameter to find_candidates(). When True, also load centroid_metadata JSON and compute similarity against secondary centroids for st_epi results. Return the best similarity across all centroids per episode.
2. Phase 1 default: False (existing behavior unchanged).
3. Episode matching (_query_existing_episodes) stays on primary centroid only -- secondary centroids do not change reconciliation behavior.
4. Tests: retrieval with/without secondary centroids, episodes with no centroid_metadata, mixed population.

##### Issue 4.2.5""",
    "Issue 4.2.4",
)

# --- Issue 4.2.5 ---
do_replace(
    "| Success criteria | No existing episodic read/write path fails when the repository contains both legacy and upgraded episode representations. |\n\n### Epic 4.3:",
    """| Success criteria | No existing episodic read/write path fails when the repository contains both legacy and upgraded episode representations. |

**Codebase Reality** (verified 2026-03-07):

The current st_epi table has 33 columns and ~78 rows (per stored memory). All existing episodes have a single embedding_id and no centroid_metadata. The migration path adds a NULLABLE JSONB column, so all existing rows get NULL centroid_metadata automatically.

TruthWriteAssembler, EpisodicLayerWriter, and TruthQueryService all use hardcoded column lists in their SQL. Any new column must be added to all three surfaces.

EpisodeCluster serialization happens via P03PhaseResult (phase_outputs.py) which passes through the R6/R7 truth writing pipeline. Adding centroid_metadata requires it to survive serialization.

**Research Evidence**:

M4-RSCH-05 explicitly tested backward compatibility: json_blob strategy preserves single-centroid semantics for existing episodes (NULL centroid_metadata = primary-only retrieval). No migration risk for existing data.

**Implementation Detail**:

1. Migration: NULLABLE JSONB column, no DEFAULT value (existing rows get NULL).
2. All SQL paths must handle NULL centroid_metadata gracefully (COALESCE or IS NOT NULL checks).
3. Mixed-population integration test: create legacy episodes (no metadata), create new episodes (with metadata), verify read/write/retrieval works for both.
4. Rollback plan: column can be dropped without data loss if multi-centroid is reverted.
5. Version the centroid_metadata JSON schema: `{"version": 1, "centroids": {...}}` for future extensibility.

### Epic 4.3:""",
    "Issue 4.2.5",
)

# =============================================================================
# EPIC 4.3: HDBSCAN Probability-Augmented Centroids (4 issues)
# =============================================================================

# --- Issue 4.3.1 ---
do_replace(
    "| Success criteria | Per-event probability is available at the centroid layer without inference hacks or index-order ambiguity. |\n\n##### Issue 4.3.2",
    """| Success criteria | Per-event probability is available at the centroid layer without inference hacks or index-order ambiguity. |

**Codebase Reality** (verified 2026-03-07):

`HDBSCANClusteringResult` (episodic_hdbscan.py L170-L199) stores `probabilities: List[float]` (L195) and `outlier_scores: List[float]` (L198). These are populated from HDBSCAN fit output at L282-L300 (_run_hdbscan) or simulated as 1.0/0.0 by DBSCAN fallback at L302-L323.

However, probabilities are NOT threaded into EpisodeCluster or CentroidCalculator inputs. The path breaks at `_build_episode_cluster()` in r2_episodic_integrator.py -- it receives cluster_events (List[EventAdapter]) but not per-event probabilities. The probability array is indexed by global event position, not by cluster membership, creating an index-alignment challenge.

CentroidableEvent protocol has no probability field. CentroidCalculator.compute_weights() has no probability input.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 11.5 (M4-RSCH-03): REJECTED. Uniform MRR=0.8943 beats all probability strategies. Best prob strategy: prob_floor_x_imp MRR=0.8813. 1217/1360 events (89.5%) had prob > 0.01 -- probabilities are nearly uniform for most events, providing minimal discrimination.

**Implementation Detail**:

1. RESEARCH REJECTS THIS ISSUE. M4-RSCH-03 proves probability weighting does not improve centroids.
2. However, threading probabilities through the pipeline still has value for: observability (log probability distribution per cluster), rescue quality tracking (low-prob rescued events), coherence diagnostics (Epic 4.4).
3. Minimal implementation: add `probability` field to EpisodeCluster or ObservationContext per member event. Do NOT use it for centroid weighting.
4. The index-alignment problem remains: probabilities array is global, cluster membership is per-cluster. Must map global indices to cluster-local events during _build_episode_cluster.
5. Defer full implementation unless Epic 4.4 coherence requires probability as a diagnostic input.

##### Issue 4.3.2""",
    "Issue 4.3.1",
)

# --- Issue 4.3.2 ---
do_replace(
    "| Success criteria | Probability interaction is explicit, bounded, and does not erase non-density reasons an event should represent the episode. |\n\n##### Issue 4.3.3",
    """| Success criteria | Probability interaction is explicit, bounded, and does not erase non-density reasons an event should represent the episode. |

**Codebase Reality** (verified 2026-03-07):

CentroidCalculator.compute_weights() (L275-L326) returns a weight array that is normalized to sum=1.0. The 4 current strategies (uniform, importance, recency, hybrid) all produce final weights via division by sum. Any probability multiplier would need to be applied before normalization.

The hybrid formula is: `0.7 * importance_weights + 0.3 * recency_weights + 0.01`, normalized. A probability combination rule would add a third factor: `w_final = encoding_strength * probability^alpha`, where alpha controls probability influence.

**Research Evidence**:

M4-RSCH-03: REJECTED. All probability strategies tested (prob_weighted, prob_thresholded, prob_x_importance, prob_floor_x_imp, prob_softmax) underperform uniform. The combination rule question is moot -- no combination helps. The research tested the exact interaction patterns this issue proposes.

**Implementation Detail**:

1. DO NOT IMPLEMENT. M4-RSCH-03 explicitly rejects probability-based centroid weighting.
2. Document the rejection: "HDBSCAN probabilities do not improve centroid quality because the probability distribution is nearly uniform (89.5% of events have prob > 0.01) and provides minimal discrimination between event contributions."
3. If future corpus data shows more varied probability distributions, re-run M4-RSCH-03.
4. The combination rule remains documented in the research memo for future reference.

##### Issue 4.3.3""",
    "Issue 4.3.2",
)

# --- Issue 4.3.3 ---
do_replace(
    "| Success criteria | Rescued or weakly attached events can contribute without hijacking the episode vector. |\n\n##### Issue 4.3.4",
    """| Success criteria | Rescued or weakly attached events can contribute without hijacking the episode vector. |

**Codebase Reality** (verified 2026-03-07):

`_rescue_noise()` (episodic_hdbscan.py L359-L436): rescued events get probability = their pre-rescue probability (from HDBSCAN output, typically low). Weak cluster events (from nearby noise grouping) get probability based on DBSCAN fallback (1.0 if clustered).

The rescue path assigns events to clusters with hardcoded thresholds: rescue distance 0.3 (L475-equiv), weak cluster 0.2 (L489-equiv). Rescued events are full cluster members -- their embeddings contribute equally to the centroid regardless of their rescue status or probability.

EpisodeCluster has no mechanism to distinguish rescued vs core members. CentroidCalculator treats all member events identically.

**Research Evidence**:

M4-RSCH-03: probability weighting rejected, which also covers rescue/fringe behavior. Uniform weighting means rescued events contribute equally to centroids, which is the same as the current behavior. The research found this is fine -- rescued events don't distort centroids because they were rescued based on proximity (distance < 0.3), meaning they're semantically similar to core members.

Section 7: production baseline had 71.5% noise; research pipeline reduced to 0.15% noise (2 events). Rescue is rare in the improved pipeline, limiting its centroid impact.

**Implementation Detail**:

1. NO CHANGE NEEDED for centroid weighting (M4-RSCH-03 validates uniform is best).
2. For observability: tag rescued events in EpisodeCluster.member_contexts or a rescue_status field so quality tracking can distinguish core vs rescued member quality.
3. If rescue frequency increases (more noise), revisit with rescue-specific centroid dampening.
4. Weak cluster events (prefix "weak-") already have separate cluster IDs, so their centroids are separate from main clusters.

##### Issue 4.3.4""",
    "Issue 4.3.3",
)

# --- Issue 4.3.4 ---
do_replace(
    "| Success criteria | Probability weighting is either validated and approved or explicitly rejected with documented rationale. |\n\n### Epic 4.4:",
    """| Success criteria | Probability weighting is either validated and approved or explicitly rejected with documented rationale. |

**Codebase Reality** (verified 2026-03-07):

No probability weighting exists in CentroidCalculator. The current system uses uniform/importance/recency/hybrid strategies that ignore HDBSCAN probabilities entirely.

**Research Evidence**:

M4-RSCH-03: EXPLICITLY REJECTED. Uniform MRR=0.8943 > best probability strategy (prob_floor_x_imp MRR=0.8813). All 6 probability strategies tested underperform uniform. Zero contamination risk from rejection -- the current non-probability path is already the better path.

Research POC-02 obligation met: "Probabilities add variance without retrieval benefit."

**Implementation Detail**:

1. REJECTED -- no production implementation.
2. Document rejection in the M4 decision memo: "HDBSCAN probability weighting rejected per M4-RSCH-03. Uniform centroid contribution is optimal. Probability data remains available on HDBSCANClusteringResult for observability and diagnostics but is not used for centroid computation."
3. Remove placeholder in CentroidableEvent for `hdbscan_probability` (from Issue 4.1.0) if it was added.
4. This closes Epic 4.3 with a documented null result. The epic produced knowledge (probability doesn't help) which is valuable for preventing future re-investigation.

### Epic 4.4:""",
    "Issue 4.3.4",
)

# =============================================================================
# EPIC 4.4: EpisodicCoherenceScore (5 issues)
# =============================================================================

# --- Issue 4.4.1 ---
do_replace(
    "| Success criteria | Every coherence dimension has documented math, bounded outputs, and explicit sparse-data behavior. |\n\n##### Issue 4.4.2",
    """| Success criteria | Every coherence dimension has documented math, bounded outputs, and explicit sparse-data behavior. |

**Codebase Reality** (verified 2026-03-07):

`ClusterQualityMetrics` (cluster_quality.py L58-L155) has no coherence fields. The composite formula (L108-L130) is: `0.40 * silhouette + 0.30 * grounding + 0.20 * (1-correction) + 0.10 * (1-singleton)`. Grounding is always 0.0, correction is always 0.0, so the formula gives a permanent +0.20 bonus from (1-correction) and 0.0 from grounding -- effectively `0.40 * silhouette + 0.20 + 0.10 * (1-singleton)`.

No coherence metrics exist anywhere in the codebase. No narrative, social, spatial, temporal, affective, or identity coherence computation.

`ObservationContext` (observation_context.py L30-L150) carries the raw signals needed for coherence: narrative_thread_id (via source event), social_context (L115), location_name (L107), sentiment_score (L72), affect_valence (L74), affect_arousal (L75). These are per-member-event contexts stored on `EpisodeCluster.member_contexts`.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 11.6 (M4-RSCH-04): equal_weight coherence (mean of 5 sub-dimensions) achieves rho=0.4556 post-correction vs silhouette mean=-0.0329 (broken). Coherence is stable across correction; silhouette breaks because thread-purity correction invalidates per-sequence distance matrices.

Key dimensions post-correction: social (0.3920), narrative (0.3386), spatial (0.1732). Temporal and affective contribute less.

**Implementation Detail**:

1. Create `k0/modules/consolidation/algorithms/episodic_coherence.py` with `EpisodicCoherenceScore` class.
2. Five coherence dimensions (each outputs [0, 1]):
   - Narrative: fraction of events sharing the dominant narrative_thread_id
   - Social: fraction sharing dominant social_context
   - Spatial: fraction sharing dominant location (geohash_6 or location_name)
   - Temporal: 1 - normalized_temporal_spread (tighter = more coherent)
   - Affective: 1 - stddev(affect_valence) / max_range (similar affect = more coherent)
3. Composite: equal-weight mean of populated dimensions.
4. Missing-signal fallback: if a dimension has no data (e.g., no narrative_thread_id for any member), contribute 0.5 (uncertain) and redistribute weight.
5. Input: List[ObservationContext] from EpisodeCluster.member_contexts.
6. Tests: single-thread cluster (narrative=1.0), mixed-thread (narrative < 1.0), no-thread (narrative=0.5 fallback).

##### Issue 4.4.2""",
    "Issue 4.4.1",
)

# --- Issue 4.4.2 ---
do_replace(
    "| Success criteria | The system exposes both per-cluster coherence and batch summaries clearly enough for tuning and audit. |\n\n##### Issue 4.4.3",
    """| Success criteria | The system exposes both per-cluster coherence and batch summaries clearly enough for tuning and audit. |

**Codebase Reality** (verified 2026-03-07):

Current quality is batch-level only. `ClusterQualityTracker.compute_from_r2_output()` (L242-L276) takes batch-level inputs (batch_silhouette_score, cluster_count, noise_count) and produces one ClusterQualityMetrics per batch. No per-cluster quality metrics exist.

`_track_quality_and_adapt()` in r2_episodic_integrator.py (L1597, ~120 lines) calls compute_from_r2_output() once per batch, gets one composite score, and feeds it to adjusters.

EpisodeCluster has `cohesion_score` (L110) which is per-cluster variance-based (from CentroidCalculator.compute_variance()), but this is a geometric metric, not a semantic coherence measure.

**Research Evidence**:

M4-RSCH-04: equal_weight coherence computed per-cluster, then aggregated. Post-correction rho=0.4556 for the aggregate. Per-cluster coherence reveals that mixed-quality batches exist -- some clusters are highly coherent while others are contaminated. Batch-level silhouette hides this variance.

**Implementation Detail**:

1. Compute EpisodicCoherenceScore per EpisodeCluster (from member_contexts).
2. Store per-cluster coherence on EpisodeCluster as `coherence_score: float` and `coherence_dimensions: Dict[str, float]`.
3. Aggregate to batch level: mean, min, max, stddev of per-cluster coherence scores.
4. BatchCoherenceSummary: `{mean_coherence, min_coherence, max_coherence, std_coherence, worst_cluster_id, per_dimension_means}`.
5. Feed batch coherence into quality tracker alongside existing silhouette.
6. Observability: log per-cluster coherence dimensions for audit and debugging.

##### Issue 4.4.3""",
    "Issue 4.4.2",
)

# --- Issue 4.4.3 ---
do_replace(
    "| Success criteria | Quality tracking and downstream consumers use coherence intentionally and do not keep the old silhouette-centric semantics by accident. |\n\n##### Issue 4.4.4",
    """| Success criteria | Quality tracking and downstream consumers use coherence intentionally and do not keep the old silhouette-centric semantics by accident. |

**Codebase Reality** (verified 2026-03-07):

`ClusterQualityTracker.compute_from_r2_output()` (L242-L276): creates ClusterQualityMetrics, calls compute_composite() which applies the fixed formula (0.40*silhouette + 0.30*grounding + 0.20*(1-correction) + 0.10*(1-singleton)).

`_track_quality_and_adapt()` (r2_episodic_integrator.py L1597): passes metrics.silhouette_score to EpsAdjuster and metrics.singleton_rate to both adjusters. The composite_quality score is computed but only used for quality tracking and alerts, not directly by adjusters.

Weight constants are module-level in cluster_quality.py (L44-L47): WEIGHT_SILHOUETTE=0.40, WEIGHT_GROUNDING=0.30, WEIGHT_CORRECTION=0.20, WEIGHT_SINGLETON=0.10.

**Research Evidence**:

M4-RSCH-04: silhouette breaks post-correction (mean=-0.0329). Coherence is stable (rho=0.4556). The recommendation is to use coherence AS the primary quality metric, with silhouette as a secondary geometric diagnostic. The 50% phantom weight (grounding=0 + correction=0) should be replaced with real signal.

**Implementation Detail**:

1. Replace composite formula: `0.50 * coherence + 0.30 * normalized_silhouette + 0.10 * (1-singleton) + 0.10 * reserved_for_future`.
2. OR: Drop silhouette from composite entirely and use `0.60 * coherence + 0.20 * (1-singleton) + 0.20 * reserved`.
3. Remove phantom grounding and correction weights (they are always 0.0/1.0).
4. Keep ClusterQualityMetrics fields for grounding/correction but mark them as dormant (explicit is_active flag or documentation).
5. Adjusters: see Issue 4.4.5 -- must be re-validated with new metric distribution in the SAME cycle.

##### Issue 4.4.4""",
    "Issue 4.4.3",
)

# --- Issue 4.4.4 ---
do_replace(
    "| Success criteria | Quality outputs clearly distinguish cluster-internal coherence from unavailable external feedback. |\n\n##### Issue 4.4.5",
    """| Success criteria | Quality outputs clearly distinguish cluster-internal coherence from unavailable external feedback. |

**Codebase Reality** (verified 2026-03-07):

ClusterQualityMetrics (L58-L155) has fields that mix intrinsic and extrinsic signals without distinction:
- Intrinsic (cluster-internal): `silhouette_score`, `singleton_rate`, `total_clusters`, `singleton_clusters`
- Extrinsic (external feedback, currently dormant): `grounding_rate`, `correction_rate`, `grounded_clusters`, `corrected_clusters`
- Meta: `space_id`, `cycle_id`, `computed_at`, `composite_quality`

The `is_acceptable` property (L155) checks `composite_quality >= 0.50`, but composite_quality gets a permanent +0.20 boost from `(1 - correction_rate)` where correction_rate is always 0.0. This means "acceptable" quality is easier to reach than it should be.

**Research Evidence**:

M4-RSCH-04: coherence is intrinsic (computed from cluster member signals). Silhouette is intrinsic (computed from distance matrix). Grounding and correction are extrinsic (require human or downstream feedback loops that do not exist). The research validates that intrinsic metrics alone (coherence + silhouette) provide meaningful quality assessment without phantom extrinsic signals.

**Implementation Detail**:

1. Add an `is_dormant` flag or separate intrinsic vs extrinsic metric groups in ClusterQualityMetrics.
2. Mark grounding_rate and correction_rate as dormant with explicit documentation: "These fields require external feedback loops (human review, downstream correction) that are not yet operational."
3. Composite formula must NOT give credit for absent extrinsic signals (no more +0.20 from 1-correction).
4. Add a `signal_availability` dict to metrics: `{"coherence": True, "silhouette": True, "grounding": False, "correction": False}`.
5. Quality alerts must distinguish "low quality because cluster is bad" from "low quality because signals are missing."

##### Issue 4.4.5""",
    "Issue 4.4.4",
)

# --- Issue 4.4.5 ---
do_replace(
    "| Success criteria | Quality alerts and adaptation logic behave predictably with the new coherence-aware metric surface. Adjusters are re-validated, not assumed stable. |\n\n### Epic 4.5:",
    """| Success criteria | Quality alerts and adaptation logic behave predictably with the new coherence-aware metric surface. Adjusters are re-validated, not assumed stable. |

**Codebase Reality** (verified 2026-03-07):

`EpsAdjuster.adjust()` (eps_adjuster.py L170-L308) reads: `silhouette_score`, `avg_cluster_size`, `singleton_rate`, `total_clusters_formed`. Decision logic:
- Cold start skip: total_clusters_formed < 100
- Quality acceptable: silhouette >= 0.5 AND avg_cluster_size <= 10
- Decrease eps: avg_cluster_size > 10.0
- Increase eps: singleton_rate > 0.20
- Bounds: [0.15, 0.40], momentum=0.9

`MinSamplesAdjuster.adjust()` (min_samples_adjuster.py L150-L233) reads: `singleton_rate`.
- Increase min_samples: singleton_rate > 0.20
- Decrease min_samples: singleton_rate < 0.05
- Bounds: [2, 5]

Both adjusters consume `silhouette_score` and `singleton_rate` from ClusterQualityMetrics. If coherence replaces silhouette in the composite formula, EpsAdjuster's `silhouette >= 0.5` threshold needs recalibration because the input distribution changes.

Current composite gives +0.20 phantom bonus from (1-correction). Removing this drops composite scores by ~0.20, potentially triggering more frequent eps adjustments.

**Research Evidence**:

M4-RSCH-04: coherence rho=0.4556 post-correction, silhouette mean=-0.0329. The numerical distribution of coherence scores will differ from silhouette scores. Adjuster thresholds calibrated for silhouette distribution may not be appropriate for coherence distribution. POC-08 (M2 research): adaptive loop is stable with 0 oscillation in 10 batches -- but this was tested under the old quality formula.

**Implementation Detail**:

1. Replace EpsAdjuster's `silhouette_score >= silhouette_target(0.5)` with either `coherence_score >= coherence_target` or `composite_quality >= composite_target` (using the new formula without phantom weights).
2. Calibrate new thresholds by computing coherence distribution on the replay corpus (246 clusters).
3. MinSamplesAdjuster uses only singleton_rate -- unaffected by coherence change.
4. Run adjuster stability test: simulate 10+ batch cycles with new quality formula, verify no oscillation.
5. Update cold_start_threshold if coherence requires more batches to stabilize.
6. Tests: adjuster behavior under new quality distribution, phantom-free composite, edge cases at threshold boundaries.

### Epic 4.5:""",
    "Issue 4.4.5",
)

# =============================================================================
# EPIC 4.5: Vectorized Distance Matrix (5 issues)
# =============================================================================

# --- Issue 4.5.1 ---
do_replace(
    "| Success criteria | Semantic pairwise distances match the scalar implementation within tight tolerance and materially reduce runtime on representative batch sizes. |\n\n##### Issue 4.5.2",
    """| Success criteria | Semantic pairwise distances match the scalar implementation within tight tolerance and materially reduce runtime on representative batch sizes. |

**Codebase Reality** (verified 2026-03-07):

`build_distance_matrix()` (composite_distance.py L270-L311): Pre-extracts embeddings and timestamps into Python lists (L282-L292), then nested loop:
```
for i in range(n):
    for j in range(i + 1, n):
        dist = self.compute_from_arrays(embeddings[i], embeddings[j], ...)
```

`compute_from_arrays()` (L230-L255): calls `_cosine_distance_arrays()` which normalizes both vectors and computes `1 - dot(a, b)`. Each call creates 2 numpy arrays from Python lists, normalizes, dots. The per-pair overhead is dominated by list-to-array conversion.

No scipy import. No cdist call. NumPy is used only for single-pair operations within the scalar loop.

Semantic cosine distance vectorization: stack all embeddings into an (N, 768) matrix, L2-normalize rows, compute `1 - (M @ M.T)` for the full NxN distance matrix in one operation.

**Research Evidence**:

R2_RESEARCH_FINAL.md Section 11.8 (M4-RSCH-06): 70.61x speedup for full vectorization. Semantic distance is the easiest dimension to vectorize (matrix multiply). 4/6 M3 dimensions are vectorizable (semantic, temporal, affective, spatial). Parity FAILS on narrative (fuzzy UltraBERT matching) and social (set overlap).

Current corpus: max sequence N=100, total runtime 2.5 seconds scalar. Vectorization benefit is marginal for N<=100 but significant for N>200.

**Implementation Detail**:

1. M4-RSCH-06 DEFERS vectorization (scalar adequate for N<=100).
2. If implemented anyway: stack embeddings into (N, 768) ndarray, L2-normalize via `embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)`, compute `cosine_matrix = 1 - (normalized @ normalized.T)`.
3. Handle zero vectors: pre-mask rows with zero norm, assign 1.0 (orthogonal) for those pairs.
4. Parity test: compare vectorized NxN cosine matrix against scalar pairwise computation, tolerance 1e-6.
5. No scipy dependency needed for semantic-only vectorization (pure NumPy).

##### Issue 4.5.2""",
    "Issue 4.5.1",
)

# --- Issue 4.5.2 ---
do_replace(
    "| Success criteria | Vectorized temporal distance reproduces the scalar path exactly for supported cases, including hard gates and degraded paths. |\n\n##### Issue 4.5.3",
    """| Success criteria | Vectorized temporal distance reproduces the scalar path exactly for supported cases, including hard gates and degraded paths. |

**Codebase Reality** (verified 2026-03-07):

`_normalized_time_distance()` (composite_distance.py L349-L361): `min(1.0, abs(t1-t2) / max_gap_ms)` (linear). After M3 Epic 3.2, this becomes logarithmic. The hard cutoff is in `compute()` (L199): `if time_diff_ms > max_temporal_gap_ms: return float("inf")`.

Temporal vectorization: extract timestamps into (N,) array, compute `abs(ts[:, None] - ts[None, :])` for NxN time-diff matrix, apply log or linear transform, apply inf mask where diff > max_gap.

This is straightforward broadcasting -- no complex per-pair logic. The hard cutoff becomes `np.where(time_diff > max_gap, np.inf, normalized_dist)`.

**Research Evidence**:

M4-RSCH-06: temporal broadcasting is one of the 4 easily vectorizable dimensions. Parity passes for temporal (failures are in narrative dimension only). The 70.61x speedup includes temporal vectorization.

**Implementation Detail**:

1. DEFERRED per M4-RSCH-06 (scalar adequate for N<=100).
2. If implemented: `time_diffs = np.abs(ts[:, None] - ts[None, :])`, apply transform (linear or log), apply inf mask.
3. Handle M3 logarithmic transform: `np.log1p(time_diffs / scale)` broadcast.
4. Parity test: compare against scalar pairwise for near-threshold, over-threshold, and equal-timestamp cases.
5. The inf mask is the only tricky part -- must match scalar hard-cutoff exactly.

##### Issue 4.5.3""",
    "Issue 4.5.2",
)

# --- Issue 4.5.3 ---
do_replace(
    "| Success criteria | All scalar edge semantics survive the vectorized implementation. |\n\n##### Issue 4.5.4",
    """| Success criteria | All scalar edge semantics survive the vectorized implementation. |

**Codebase Reality** (verified 2026-03-07):

Scalar edge cases that must survive vectorization:
1. Hard cutoff: `time_diff > max_gap -> inf` (composite_distance.py L199)
2. Zero-vector fallback: `_cosine_distance_arrays` returns 1.0 for zero-norm vectors (L336)
3. Missing embedding: `build_distance_matrix` raises ValueError for missing embeddings (L286)
4. After M3: per-dimension missing-signal masks, weight redistribution, neutral fallbacks, categorical comparisons

The 6D M3 formula is significantly harder to vectorize than 2D because:
- Narrative distance uses UltraBERT fuzzy thread matching (string comparison, not numeric)
- Social distance uses Jaccard set overlap (set operations, not matrix operations)
- Missing-signal masks create per-pair-specific weight vectors

**Research Evidence**:

M4-RSCH-06: parity FAILS (max_err=0.329) due to narrative fuzzy matching. The scalar path uses UltraBERT fuzzy thread matching; the vectorized path used exact-match only, producing different distances. 4/6 dimensions vectorizable; narrative and social require scalar loops.

**Implementation Detail**:

1. DEFERRED per M4-RSCH-06.
2. If partially vectorized: vectorize semantic + temporal + affective + spatial (4 dimensions), keep narrative + social as scalar loops.
3. The mixed approach creates a "partially vectorized" matrix that is harder to maintain than pure scalar.
4. Recommendation: keep scalar until sequence sizes grow significantly (N > 200) or a new narrative distance function allows vectorization.
5. Parity harness: mandatory before any vectorization ships. Compare full NxN matrix, scalar vs vectorized, tolerance 1e-6 per element.

##### Issue 4.5.4""",
    "Issue 4.5.3",
)

# --- Issue 4.5.4 ---
do_replace(
    "| Success criteria | The plan and code clearly state which vectorization dependency model the repo supports and why. |\n\n##### Issue 4.5.5",
    """| Success criteria | The plan and code clearly state which vectorization dependency model the repo supports and why. |

**Codebase Reality** (verified 2026-03-07):

Current dependencies (from pyproject.toml and requirements.txt): numpy is used throughout K0. scipy is NOT in the dependency surface. No `from scipy.spatial.distance import cdist` or similar import exists in any K0 production code.

NumPy broadcasting is sufficient for: cosine distance (matrix multiply), temporal distance (broadcasting), affective distance (element-wise ops), spatial distance (categorical match).

scipy.spatial.distance.cdist would add: optimized C-level pairwise distance for common metrics, but adds a ~30MB dependency and requires binary compatibility.

**Research Evidence**:

M4-RSCH-06: vectorization benchmark used pure NumPy broadcasting. No scipy required. 70.61x speedup achieved without scipy. The research validates that NumPy-only is sufficient.

**Implementation Detail**:

1. Decision: NumPy-only. Do NOT add scipy dependency.
2. Rationale: NumPy broadcasting achieves sufficient speedup for vectorizable dimensions. scipy adds dependency weight without proportional benefit for the 4 vectorizable dimensions. The 2 non-vectorizable dimensions (narrative, social) cannot use cdist anyway.
3. Document in pyproject.toml or architecture docs: "K0 vectorization uses NumPy broadcasting only. scipy is explicitly excluded."
4. If future profiling shows NumPy bottleneck at N > 500: revisit scipy decision with measured evidence.

##### Issue 4.5.5""",
    "Issue 4.5.4",
)

# --- Issue 4.5.5 ---
do_replace(
    "| Success criteria | The approved vectorized path is demonstrably faster and semantically equivalent on representative workloads. |\n\n### Epic 4.6:",
    """| Success criteria | The approved vectorized path is demonstrably faster and semantically equivalent on representative workloads. |

**Codebase Reality** (verified 2026-03-07):

Current scalar performance: 2.5 seconds for full corpus (1360 events, 32 sequences, max N=100). This is measured in the research pipeline, not production. Production batch sizes are typically smaller (P03 processes recent events, not the full corpus).

No existing benchmark or parity test infrastructure in the production test suite. test_r2_integration.py has `test_distance_matrix_for_clustering` which checks matrix properties (symmetric, non-negative, diagonal=0) but not performance.

**Research Evidence**:

M4-RSCH-06: 70.61x speedup (vectorized). Memory: 7x overhead (7 NxN matrices vs 1), 547 KB vs 78 KB for N=100 -- acceptable. Parity: FAILS (narrative fuzzy matching). Verdict: scalar_adequate for current workloads.

Small sequences: 8x speedup. Medium: 27x. Large: 70x. The speedup scales with N^2, so benefit increases with batch size.

**Implementation Detail**:

1. DEFERRED per M4-RSCH-06 research verdict.
2. When implementing: add parity harness that runs vectorized and scalar on identical inputs, asserts max_err < 1e-6 per element.
3. Add performance benchmark: measure scalar vs vectorized on N=10, 50, 100, 200, 500 event batches.
4. Add memory regression test: verify matrix memory stays within bounds for expected batch sizes.
5. Gate: vectorization only ships when parity passes (narrative dimension must be resolved).
6. Current action: document the deferral decision and the conditions under which vectorization becomes necessary (N > 200 regularly, or latency SLA requires sub-second matrix generation).

### Epic 4.6:""",
    "Issue 4.5.5",
)

# =============================================================================
# EPIC 4.6: Narrative, Cognitive, And Support-Signal Encoding (5 issues)
# =============================================================================

# --- Issue 4.6.1 ---
do_replace(
    "| Success criteria | Narrative arc signals have a documented and test-covered role in Milestone 4 outputs. |\n\n##### Issue 4.6.2",
    """| Success criteria | Narrative arc signals have a documented and test-covered role in Milestone 4 outputs. |

**Codebase Reality** (verified 2026-03-07):

`narrative_arc_position` is on EventAdapter (L209): returns `self.event.narrative_arc_position or None`. P03EventState (L209): str = "". Values: BEGINNING/MIDDLE/END/CLIMAX.

`narrative_is_goal_event` does NOT exist on P03EventState or EventAdapter. No field by this name in event_state.py. The closest field is `goal_context` (P03EventState L209, str = "").

ObservationContext does NOT carry narrative_arc_position. It has no narrative-specific fields beyond what the source event provides.

Current usage: narrative_arc_position is exposed on EventAdapter but NOT consumed by any algorithm. It is available for M3 narrative distance (Epic 3.1.4) but the algorithm does not read it yet.

**Research Evidence**:

M4-RSCH-07: ALL 9 cognitive/narrative signals tested (including narrative_arc_position) are SUMMARY-ONLY. They do not improve centroid encoding quality (baseline MRR=0.9975). The research recommends keeping these signals in episode metadata and summaries, not in encoding or distance math.

M4-RSCH-04: narrative coherence is one of the 5 coherence dimensions (rho post-correction: narrative=0.3386). Narrative arc position could contribute to narrative coherence assessment (clusters with consistent arc progression are more coherent).

**Implementation Detail**:

1. Primary role: SUMMARY and COHERENCE, not encoding.
2. Add narrative_arc_position to ObservationContext so it flows into episode metadata.
3. For coherence (Issue 4.4.1): compute arc consistency -- clusters where events progress BEGINNING -> MIDDLE -> END/CLIMAX are more narratively coherent.
4. For summary: include dominant arc position in episode summary metadata.
5. `narrative_is_goal_event`: derive from `goal_context != ""` rather than adding a new field.
6. Tests: clusters with consistent vs mixed arc positions, clusters with goal events.

##### Issue 4.6.2""",
    "Issue 4.6.1",
)

# --- Issue 4.6.2 ---
do_replace(
    "| Success criteria | Goal and intent are represented coherently in both encoding and episode metadata surfaces. |\n\n##### Issue 4.6.3",
    """| Success criteria | Goal and intent are represented coherently in both encoding and episode metadata surfaces. |

**Codebase Reality** (verified 2026-03-07):

`goal_context` (P03EventState L209, str = ""): NOT on EventAdapter. Contains free-text goal description from MW v2.

`intent_type` (P03EventState L208, str = ""): NOT on EventAdapter. Listed among 7 zombie/deprecated columns. `intent_ultrabert` (P03EventState L194, str = "") is the replacement from P02 UltraBERT. `intent_ultrabert` is NOT on EventAdapter either.

ObservationContext carries `intent_ultrabert` (L83) and `intent_confidence` (L84) but NOT `goal_context` or `intent_type`.

Current usage: none of these fields are consumed by any clustering, distance, or quality algorithm. They are passive P03EventState fields.

**Research Evidence**:

M4-RSCH-07: goal_context and intent signals are SUMMARY-ONLY -- they do not improve centroid encoding. M4-RSCH-04: coherence includes no intent or goal dimension explicitly, but intent consistency within a cluster could contribute to narrative coherence.

**Implementation Detail**:

1. Primary role: SUMMARY metadata and episode characterization.
2. Add goal_context to ObservationContext so it flows into episode-level metadata.
3. For episode summary: aggregate goal contexts across cluster events (dominant goal, goal diversity).
4. Intent: use intent_ultrabert from ObservationContext for intent consistency metric (could augment narrative coherence).
5. Do NOT add intent_type (zombie column) to any new surface.
6. Tests: clusters with consistent vs mixed goals, clusters with intent shifts.

##### Issue 4.6.3""",
    "Issue 4.6.2",
)

# --- Issue 4.6.3 ---
do_replace(
    "| Success criteria | `memory_tier` has exactly two bounded jobs: encoding weight and distance anchoring. `novelty` and `source_type` each have one or two bounded jobs in the representation layer. Anchoring is a configurable post-sum modifier, not an ad-hoc hack inside a single dimension. |\n\n##### Issue 4.6.4",
    """| Success criteria | `memory_tier` has exactly two bounded jobs: encoding weight and distance anchoring. `novelty` and `source_type` each have one or two bounded jobs in the representation layer. Anchoring is a configurable post-sum modifier, not an ad-hoc hack inside a single dimension. |

**Codebase Reality** (verified 2026-03-07):

`novelty_score` (P03EventState L154, float = 0.0): NOT on EventAdapter. ObservationContext carries it (L92). Computed by P02 processing.

`memory_tier`: does NOT exist on P03EventState. Not in event_state.py. Not on EventAdapter. Not on ObservationContext. This field is a design-time concept from the temp_r2_design document, not yet materialized in the codebase.

`source_type`: does NOT exist on P03EventState. Not on EventAdapter. ObservationContext has related fields: `ingress_channel` (L98), `ingress_category` (L99), `ingress_source` (L100), but no `source_type` field.

For distance anchoring: composite_distance.py compute() returns a weighted sum. A post-sum anchoring modifier would multiply the final distance: `d_final = d_sum * anchoring_factor(event_i, event_j)`. This hook does not exist yet.

**Research Evidence**:

M4-RSCH-07: novelty tested as encoding weight modifier -- SUMMARY-ONLY (delta < 0.01 vs baseline MRR=0.9975). The research does not test memory_tier or source_type because they do not exist in the corpus.

Memory tier anchoring (landmark attraction/repulsion) is a design-time proposal from the discovery doc. No empirical validation exists. The mechanism (d *= 0.5 for related landmarks, d *= 1.3 for unrelated) is untested.

**Implementation Detail**:

1. `novelty_score`: SUMMARY-ONLY per M4-RSCH-07. Keep on ObservationContext for episode metadata. Surface on EventAdapter for coherence diagnostics.
2. `memory_tier`: DEFER. Does not exist on P03EventState. Requires K1 memory classification pipeline to populate. Cannot implement until the field exists and has non-trivial population. Create a placeholder architecture note for when K1 provides memory_tier.
3. `source_type`: DEFER. Map to ObservationContext's ingress fields (ingress_channel, ingress_source) which already exist. Define the mapping: ingress_channel -> source_type normalization rule.
4. Distance anchoring: DEFER until memory_tier exists and has empirical validation. The post-sum modifier hook can be designed now but not implemented without data.
5. Tests: novelty in summary, deferred placeholder tests for memory_tier and source_type.

##### Issue 4.6.4""",
    "Issue 4.6.3",
)

# --- Issue 4.6.4 ---
do_replace(
    "| Success criteria | Identity-domain information influences coherence or summary output in a deterministic and documented way. |\n\n##### Issue 4.6.5",
    """| Success criteria | Identity-domain information influences coherence or summary output in a deterministic and documented way. |

**Codebase Reality** (verified 2026-03-07):

`identity_domains_json` does NOT exist on P03EventState. Not in event_state.py. Not on EventAdapter. Not on ObservationContext. This is a design-time concept from the discovery document.

The closest existing field is `ner_entities_json` (P03EventState L172, str = "[]"): JSON array of NER-extracted entities with text and labels. EventAdapter wraps this (L183-L192) by parsing the JSON and extracting text fields.

`identity_relevance` also does not exist -- another design-time concept. No identity scoring or domain classification pipeline exists in K0/K1.

**Research Evidence**:

M4-RSCH-07: identity_domains tested as encoding weight modifier -- SUMMARY-ONLY (delta < 0.01). Even if the field existed, it would not improve centroid quality.

M4-RSCH-04: no identity coherence dimension was computed in the research (only narrative, social, spatial, temporal, affective). Identity coherence (do cluster events share identity domains?) would be a new dimension.

**Implementation Detail**:

1. DEFER. The field does not exist in the codebase. Cannot implement until K1 provides identity domain classification.
2. When available: add identity_domains_json to P03EventState and EventAdapter.
3. Identity coherence: fraction of cluster events sharing a dominant identity domain (similar pattern to social coherence).
4. Summary contribution: aggregate identity domains across cluster events for episode characterization.
5. No encoding role per M4-RSCH-07.
6. Placeholder: document the intended integration point for when K1 identity classification ships.

##### Issue 4.6.5""",
    "Issue 4.6.4",
)

# --- Issue 4.6.5 ---
do_replace(
    "| Success criteria | Affective support signals are represented in encoding and summary outputs with clear scope and no opportunistic leakage. |\n\n#### Milestone 4 Research Exit Gate",
    """| Success criteria | Affective support signals are represented in encoding and summary outputs with clear scope and no opportunistic leakage. |

**Codebase Reality** (verified 2026-03-07):

`emotions_json` / `dominant_emotions_json`: ObservationContext has `dominant_emotions_json` (L77, Optional[str]). P03EventState has `emotions_json` (L135, str = "[]"). EventAdapter does NOT expose emotions_json.

`entity_salience_json`: does NOT exist on P03EventState or EventAdapter. The closest field is `salience_score` (P03EventState L140, float = 0.0) which is a scalar, not per-entity salience.

`salience_band`: P03EventState has it (L142, str = ""). ObservationContext carries it (L91). EventAdapter does NOT expose it.

Current usage in R2:
- `_build_episode_cluster()` (r2_episodic_integrator.py) aggregates `dominant_emotion` via majority vote from cluster events (L1260-L1280). This uses parsed `emotions_json` to find the most common emotion across events.
- EpisodeCluster has `dominant_emotion` (L95) and `dominant_sentiment` (L94) -- both are scalar aggregates.
- Emotional-peak centroid selection (Issue 4.2.2) would use affect_valence and affect_arousal, which are already on EventAdapter.

**Research Evidence**:

M4-RSCH-07: emotion_tags tested as encoding weight modifier -- SUMMARY-ONLY. entity_salience tested -- SUMMARY-ONLY. All signals: delta < 0.01 vs baseline MRR=0.9975.

M4-RSCH-02: emotional_peak centroid selection uses max |affect_valence| + affect_arousal. Found in 246/246 clusters (100%). This is the primary affective signal role: selecting the emotional-peak secondary centroid.

M4-RSCH-04: affective coherence is one of 5 dimensions. Post-correction contribution is lower than narrative and social.

**Implementation Detail**:

1. `emotions_json`: SUMMARY-ONLY. Keep in ObservationContext (dominant_emotions_json). Used by _build_episode_cluster() for dominant_emotion aggregation. No change needed.
2. `entity_salience_json`: DEFER. Does not exist on P03EventState. Requires MW v2 entity-level salience extraction.
3. `salience_band`: SUMMARY-ONLY. Already on ObservationContext. Surface on EventAdapter for coherence diagnostics if needed.
4. Emotional-peak centroid: use affect_valence + affect_arousal from EventAdapter (already available). This is the primary M4 role for affective signals.
5. Affective coherence (Issue 4.4.1): use stddev of affect_valence across cluster members from ObservationContext.
6. Tests: emotional-peak selection from cluster events, affective coherence computation, dominant emotion aggregation.

#### Milestone 4 Research Exit Gate""",
    "Issue 4.6.5",
)

# --- Write ---
f.write_text(content, encoding="utf-8")
print(f"\nAll {replacements} enrichments applied and saved.")
