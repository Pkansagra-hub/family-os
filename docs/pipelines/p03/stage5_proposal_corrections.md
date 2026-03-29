## CRITICAL: Algorithm Name & Identity Confusion Between Section 4 and Section 13

This is the single most damaging issue in the document. **Two algorithms are silently renamed to completely different things between the design sections (4.x) and the implementation sections (13.x):**

| Acronym | Section 4 Definition | Section 13 Definition | Target Layer (Sec 4) | Target Layer (Sec 13) |
|---|---|---|---|---|
| **ASU** | **Anchor Seeding & Update** (fills `st_anchors` + `st_anchor_observations`) | **Adaptive Schema Updater** (updates `st_sem` confidence) | `st_anchors` | `st_sem` |
| **SPR** | **Semantic Pattern Reinforcement** (updates `st_sem` confidence) | **Stale Prediction Reaper** (expires/archives `st_prospective`) | `st_sem` | `st_prospective` |

This means **Section 13 has effectively deleted the anchor seeding algorithm and the semantic pattern reinforcement algorithm**, replacing them with entirely different algorithms that share the same acronyms. The `st_anchors` table (0 rows, identified as a key gap in Section 2.4) is never populated in the Section 13 implementation plan. The semantic pattern flat-confidence problem (all 545 at 0.80) also has no solution in Section 13.

**Impact**: Success criteria #1 ("10+ active anchors") and #5 ("confidence range 0.30-0.95") are unachievable under the Section 13 implementation plan.

---

## CRITICAL: Output Dataclass Conflicts Between Section 4 and Section 13.14

Every algorithm has **two different output dataclass definitions** with conflicting field names:

| Algorithm | Section 4 Dataclass | Section 13.14 Dataclass | Conflicts |
|---|---|---|---|
| EST | `EpisodeStrengthUpdate` (fields: `reinforcement_source`, no `decay_factor`) | `EpisodicStrengthUpdate` (fields: `decay_factor`, `reinforcement_rate`) | Different name, different fields. Section 4 explicitly says "NO STALENESS DECAY" yet 13.14 adds `decay_factor`. |
| ASU | `AnchorSeed` / `AnchorUpdate` (alpha/beta Bayesian) | `SchemaConfidenceUpdate` (confidence/contradiction_count) | Completely different algorithm |
| EWR | `EdgeWeightUpdate` (fields: `old_weight`, `reinforcement_reason`) | `EdgeWeightUpdate` (fields: `evidence_quality`, `current_version`) | Same name, different field sets |
| SRE | `SocialRelationshipUpdate` (fields: `health_score`, `sentiment_trajectory`, `emotional_diversity`) | `SocialRecalibration` (fields: `new_trust`, `emotional_variance`, `observation_window_days`) | Different name and fields |
| SPR | `SemanticPatternUpdate` + `PatternMerge` | `PredictionReaperAction` | Completely different algorithm |

**Impact**: Anyone implementing from this doc will not know which dataclass definition is authoritative.

---

## CRITICAL: Phase Execution Order Contradictions

Section 5 and Section 13.8 define **incompatible** phase groupings:

| Phase | Section 5 | Section 13.8 | Conflict |
|---|---|---|---|
| Phase 1 | EST, ASU, SRE, SPR, SPC-UQ | EST, ASU, EWR, SRE, SPC-UQ, SPR, **MTP** | MTP moved from Phase 5 to Phase 1 |
| Phase 2 | **EWR**, BGT-SM (sequential, depends on Phase 1) | BGT-SM, **SPG**, CLV, CTD (parallel) | EWR moved from Phase 2 to Phase 1; SPG moved from Phase 4 to Phase 2 |
| Phase 5 | **MTP**, EPC (sequential) | *(doesn't exist)* | Phase 5 collapsed |

Section 5 states EWR "benefits from EWR running first" and "reads observation_evidence + EST salience updates", implying EWR depends on EST (Phase 1). But Section 13.8 runs EWR in Phase 1 alongside EST, breaking that dependency.

MTP in Section 4.9 says it "reads observation_evidence + final salience/coherence state", requiring Phase 1-4 outputs. Section 13.8 runs it in Phase 1 with no dependencies.

---

## Missing Data Loaders (No Code Path to Feed Algorithms)

The proposal documents 5 `_load_accumulated_*()` loaders (entities, edges, episodes, schemas, routines) plus the new observation evidence loader. But several algorithms need data that **no loader provides**:

| Algorithm | Required Input | Loader | Status |
|---|---|---|---|
| SRE (4.4) | `existing_relationships: List[SocialRelationshipRow]` from `st_social` | `_load_accumulated_social()` | **MISSING** |
| SPC-UQ (4.5) | `existing_prospective: List[ProspectiveRow]` from `st_prospective` | `_load_accumulated_prospective()` | **MISSING** |
| ASU (4.2) | `existing_anchors: Dict[Tuple, AnchorRow]` from `st_anchors` | `_load_accumulated_anchors()` | **MISSING** |
| CLV (4.10) | `social: List[SocialRow]` from `st_social` | `_load_accumulated_social()` | **MISSING** |
| CTD (4.11) | `social: List[SocialRow]` from `st_social` | `_load_accumulated_social()` | **MISSING** |

---

## Missing Layer Infrastructure for `st_anchors`

Confirmed from codebase: `P03StagedWrites` has **no `st_anchors_writes` bucket**. The `add_write()` routing dict doesn't handle `layer="st_anchors"`. There is no `AnchorLayerWriter` in the R7 writer registry. The dependency order doesn't include `st_anchors`.

Section 6's R6/R7 Integration table claims `AnchorSeed` produces `StagedWrite(INSERT, st_anchors)`, but the staging infrastructure has nowhere to put it.

---

## Missing Database Migrations for Algorithm Outputs

| Column Needed | Algorithm | Table | Migration Provided? |
|---|---|---|---|
| `reinforcement_count` | EST | `st_epi` | **NO** |
| `last_reinforced_at` | EST | `st_epi` | **NO** |
| `sentiment_trajectory` | SRE | `st_social` | **NO** |
| `emotional_diversity` | SRE | `st_social` | **NO** |
| `health_score` | SRE | `st_social` | **NO** |
| `last_interaction_at` | SRE | `st_social` | **NO** |
| `episode_chain` (JSONB) | NTD | `st_sem` | **NO** (0073 adds `thread_entities` but not `episode_chain` per Section 4.14) |
| `propagated_salience` | SPG | `st_kg_edges` | **NO** (0071 only adds it to `st_kg_dom`, but Section 4.13 outputs `EdgeSalienceUpdate`) |
| `memory_tier` | MTP | `st_social`, `st_procedural` | **NO** (0070 covers st_epi, st_sem, st_kg_dom but MTP config includes `st_social` and `st_procedural` in `tier_eligible_layers`) |

---

## st_observations Schema Discrepancies

- Section 2.7 lists 32 columns including `observation_weight`, but Section 13.17 DDL omits `observation_weight` and instead has `confidence`. The actual `ObservationRecorder` INSERT SQL (confirmed in codebase) includes `observation_weight` at parameter $8, consistent with Section 2.7 but not with 13.17's DDL.
- `day_of_week` appears in `ObservationContext` but is absent from Section 13.17 DDL, while present in the actual recorder's INSERT SQL.
- Section 2.7 mentions 12 partial indexes; Section 13.17 shows only 8 indexes with different names (e.g., `idx_obs_salience` vs `idx_obs_salience_high`).

---

## R3 Integration for MTP Is Unspecified

Section 4.9 states R3's decay becomes `effective_lambda = base_lambda * record.memory_tier.decay_multiplier`. This is a **cross-phase change to R3** (an entirely different phase of P03). No modification to R3 code is described, no R3 file is listed in "Files Changed", and no migration ensures R3 can read the `memory_tier` column. Without R3 changes, MTP sets tiers that nothing reads.

---

## Stubbed Methods with "No LLM Calls" Constraint

Section 7 states all algorithms have "No LLM calls: Pure algorithmic computation." But:

- EPC's `_synthesize_description()` (Section 4.12) is `...` (stubbed). Generating "Regular family dinners" from 5 episode fragments without an LLM is non-trivial. No rule-based algorithm is described.
- NTD's `_synthesize_narrative()` (Section 4.14) is `...` (stubbed). Generating "How we fixed Panda's sleep" is a creative text generation task.
- EPC's `_cluster_by_similarity()` is `...` (stubbed). "Uses pre-computed embeddings from st_vec where available, falls back to token overlap" — no similarity algorithm is specified.

---

## Cold-Start / Empty Evidence Behavior Undocumented

If `st_observations` is empty (fresh deployment or new tenant), `ObservationEvidenceLoader` returns empty aggregates. All 14 algorithms would produce zero outputs since they all depend on observation evidence as their primary signal. The proposal references `ObservationEvidence.empty()` in 13.1.2 but never defines it or documents expected cold-start behavior across algorithms. EST's Tier 2 (heuristic signature matching) would still work, but ASU, SRE, SPR, MTP, CLV, CTD all go completely silent.

---

## Self-Reinforcing Loop Convergence Not Proven

The feedback loop (R5 reads observations -> R5 boosts records -> R7 writes REINFORCEMENT observation -> next R5 reads more reinforcements) uses `log2(1 + count)` scaling. But the proposal doesn't mathematically prove convergence. With `observation_boost=0.03` and unbounded reinforcement cycles, salience can theoretically ratchet up to 1.0 for any episode that keeps appearing. The logarithmic bound helps but the interaction between multiple algorithms (EST boost + SPG propagation + MTP tier promotion) compounding on the same record is not analyzed.

---

## Missing Governance Artifacts

Per the project's own GATE 1 and GATE 5 rules:

- **No ADR references**: The proposal supersedes dossier sections but creates no ADR in decisions-K0.
- **No pipeline dossier update**: GATE 1 requires reading and updating the P03 pipeline dossier. No update plan for `docs/pipelines/P03_*` is mentioned.
- **No contract YAML files**: GATE 2 requires contract validation. The 14 new algorithms have no `k0/contracts/modules/*.yaml` entries.
- **No `k0_architecture_master.md` updates**: GATE 5 requires sync with the architecture master document.
- **No sync validation command**: GATE 0/5 require `python -m governance.k0.scripts.sync --report`.

---

## Performance Estimate Concerns

- **Phase 0 at 150ms**: Loading ALL observation records for a tenant via `GROUP BY layer, record_id` with no LIMIT clause. For a user with 10K+ observations, this is likely >150ms. No EXPLAIN ANALYZE, no pagination, no max-records safeguard.
- **EPC at 200ms**: Pairwise embedding similarity over 339 episodes = ~57K comparisons. Even with optimized vector ops, 200ms is aggressive without a spatial index or approximate NN.
- **NTD at 150ms**: BFS from every episode forward through all subsequent episodes = O(n^2) in worst case for 339 episodes.

---

## Missing P01 Recall Path Changes

The proposal improves memory quality but describes **zero changes to P01 Recall** to actually use the new data:

- `propagated_salience` on entities (SPG) — no recall ranking change
- `memory_tier` — no recall filtering or prioritization
- `is_composite` episodes — no recall awareness of composites
- `NARRATIVE_THREAD` patterns — no recall selector for threads
- `ObservationContextFetcher` (Section 2.7) is called "planned — not yet implemented" with no implementation plan

Without P01 changes, the memory improvements are invisible to K1.

---

## Minor Issues

1. **`assemble_all()` missing `mcts_scenarios` parameter**: The current codebase's `assemble_all()` (confirmed at line 1850) doesn't have `mcts_scenarios` as a parameter — only `counterfactuals`. Section 13.3.2 claims it does.
2. **`EpisodeCluster` missing fields**: EST uses `activity_type` field on EpisodeCluster (Section 4.1). The actual `EpisodeCluster` dataclass (confirmed) has no `activity_type` field.
3. **No rollback plan for data mutations**: EPC archives source episodes. If EPC has a bug, how are archived episodes recovered? No reversibility mechanism described.
4. **Duplicate `_find_duplicates()` stubs**: SPC-UQ's cleanup references `self._find_duplicates(active_items, config)` and SPR's reinforcement references `self._find_duplicates(patterns, config)` — neither is implemented.
5. **Feature flags default to `true`**: Section 8 sets all per-algorithm flags to `default: true` while `P03_FF_R5_MODE` defaults to `disabled`. This means individual toggles are ON but the master switch is OFF. The interaction isn't documented — does `MODE=disabled` override individual flags?

## End-to-End Data Flow Trace: K1 → Bridge → K0 P02 → st_hipp_events

### LAYER 1: K1 Cognitive Kernel (Signal Production)

**Phase 1 — UltraBERT (22ms, pre-LLM, deterministic)**
Every user input passes through UltraBERT's multi-head model FIRST, writing 5 session-state sections:

| Section | UltraBERT Head | Output | Session Key |
|---------|---------------|--------|-------------|
| Intents | Intent Head | 8-type classification | `control.intents` |
| Domains | Ingress Head | 12-type activity | `control.domains` |
| Safety | Safety Head | GREEN/AMBER/RED/CRISIS | `control.safety_band` |
| Entities | NER Head (family+general) | KINSHIP, PER, ORG, LOC | `beliefs_active.entities` |
| Affect | Emotions+Sentiment | valence, emotions | `affective_now.raw` |

**Phase 2 — LLM Tools (Back LLM, 2-30s)**
The Back LLM sees conversation + Phase 1 state, calls tools:

- `update_scoreboard()`, `update_beliefs()`, `refine_affect()`, etc.
- Manages task lifecycle: PENDING→DISPATCHED→ACTIVE→COMPLETED

**Memory Writers (L4 agents)**
After LLM turn completes, Memory Writers observe the conversation and emit:

- `MW_EPISODIC` → topic: `memory.delta` → K0 Command Port
- `MW_PLAN` → topic: `plan.committed` → K0 Command Port
- `MW_GAP_ANSWER` → topic: `memory.delta + gap_id` → K0 Command Port

The Delta Bus aggregates session deltas with 250ms batching, and Memory Writer Agents prepare **CommandEnvelopes**.

### LAYER 2: Bridge (Security Gateway)

**CommandEnvelope structure** (K1 → K0, one-way fire-and-forget):

```
{
  cognitive_trace_id, tenant_id, space_id,
  topic: "memory.delta",        // Routes to P02
  schema_uri,
  body: { text, participants, location_name, activity_type, event_time, ... },
  actor, device_id, band,       // K1's policy_band assessment
  sig_alg, sig_kid, sig,        // Crypto signature
  envelope_sha256, idem_key     // Integrity + idempotency
}
```

Bridge responsibilities:

- Validates crypto signatures (ed25519/hmac-sha256)
- Applies offline-first queue (LocalOutbox) when K0 unreachable
- Routes by topic: `memory.delta` → P02, `learning.feedback` → P06, etc.

### LAYER 3: K0 P02 Pipeline (12-Stage DAG)

Entry topic: `cognitive.memory.write.committed.v1`

| Stage | Module | What It Does | Signal Produced |
|-------|--------|-------------|-----------------|
| 10 | `pattern_separate` | SimHash (64-bit) + MinHash (32 perms) from body.text+participants+location+activity+hour_bucket | `simhash_hex`, `minhash32` |
| 20 | `semantic_project` | UltraBERT NER (ner_family+ner_general), entity resolution, KG triple generation, raw NER storage for P03 | `entities_json`, `kg_triples_json`, `ner_entities_json`, `temporal_json`, `extracted_relations_json`, `safety_familyos_band`, `nli_label` |
| 22 | `embedding.extract` | Extract 768-dim embedding from UltraBERT cache (ADR-K003, inline) | `embedding` (768 floats), `embedding_id` |
| 30 | `affect.analyze` | Primary: UltraBERT (sentiment+emotions+safety), Fallback: GoEmotions→VADER | `affect_valence`, `affect_arousal`, `affect_band`, `dominant_emotions`, `clinical_safety_*` |
| 31 | `space.resolve` | Household/personal/shared scope resolution | `owner_id`, `visible_to_json`, `visibility_scope` |
| 32 | `social.family_graph` | Participant role resolution, relationship types | `social_context`, `social_intimacy`, `participant_roles_json` |
| 33 | `temporal_profile` | Time-of-day, day-of-week, circadian slot, backdating detection | 11 temporal columns |
| 40-43 | device/ingress/geo/spatial | Device type, activity classification, geohash, privacy masking | Device/geo/activity columns |
| 50 | `retention_lookup` | Retention policy (STANDARD/SENSITIVE/EPHEMERAL) | `retention_policy_id`, `retention_bucket` |
| 55 | `salience.score` | Formula: 0.50×social + 0.40×affect + 0.10×recency | `salience_score`, `salience_band` |
| 60 | `hipp_events_row` | Assembles 80+ columns from all enrichments into one row | `hipp_events_row` dict |
| 70 | `hipp_events_writer` | 3-table atomic write: st_hipp_events + st_vec + st_pipeline_processed | DB commit |
| 80 | `event_emitter` | Publishes `memory.formed.v1` SSE back to K1 | SSE event |

### LAYER 4: st_hipp_events (Final Storage)

Live table: **121 columns** across 12 groups, **1348 rows** in the database. 100% column fill rate for all UltraBERT fields.

---

## Signal Quality Analysis — Critical Findings from Live Data

### GOOD SIGNALS

| Signal | Quality | Evidence |
|--------|---------|----------|
| `activity_type_ultrabert` | **Excellent** | All 12 categories populated, well-distributed (DIARY 18%, HEALTH 18%, WORK 12%, CELEBRATION 8%, etc.) |
| `intent_ultrabert` | **Good** | 8-type intent working (`reflect`, `share_news`, etc.) |
| `affect_valence/arousal` | **Good** | Real floating-point values (0.64-0.81 range), not defaults |
| `ner_entities_json` | **Good** | UltraBERT NER populating ner_family (TRADITION, KINSHIP) and ner_general (PER with scores) |
| `extracted_relations_json` | **Present** | Relations like `["child_of", "colleague_of"]` being extracted |
| `embedding_status` | **100% READY** | ADR-K003 inline embedding working, all 1348 rows have vectors |
| `safety_familyos_band` | **All GREEN** | Expected for non-clinical family content |
| `simhash_hex` | **Good** | Unique fingerprints per event |

### BAD SIGNALS (Critical Problems)

**1. `social_context` is BROKEN — only "friends" (68%) or "solo" (32%)**

This is a FamilyOS app. The content is clearly about family ("Maya scared of thunderstorm", "Panda is asleep", "Christmas Eve dinner with both families"). Yet social_context never returns "family", "extended_family", or any kin-specific value. It's always "friends" or "solo".

**Root cause**: M32 (`social.family_graph_resolve`) doesn't have access to a real family graph. Without a household membership/kin registry, it can't distinguish "Panda" (partner) or "Maya" (child) from "friends". The participants JSON has names ("Panda", "Maya", "Mom", "Dad") but no role mapping.

**Impact**: Salience scoring is crippled. `WEIGHT_SOCIAL = 0.50` is the dominant factor, but `SOCIAL_IMPORTANCE_SCORES["friends"] = 0.5` vs `["family"] = 1.0` means every family event gets HALF the social score it should.

**2. `salience_score` is effectively FLAT — 60% stuck at 0.41, all 1348 rows MED**

| Score | Count | % |
|-------|-------|---|
| 0.41 | 812 | 60% |
| 0.5 | 67 | 5% |
| 0.42-0.43 | ~460 | 34% |

ALL 1348 rows are salience_band = MED. Zero HIGH. Zero LOW. The salience system is non-discriminating.

**Root cause**: Chain reaction from bad social_context:

- `social_context = "friends"` → `social_score = 0.5`
- `affect_valence ~0.7` → `affect_score ~0.8` (after amplification)
- `recency = 0.1` (batch loaded, all old)
- Formula: `0.50 × 0.5 + 0.40 × 0.8 + 0.10 × 0.1 = 0.25 + 0.32 + 0.01 = 0.58`
- But most rows show 0.41, suggesting the affect input to salience is often lower than expected (affect_intensity might be None, defaulting to 0.5)

**3. `has_partner_present` and `has_parent_present` are ALWAYS FALSE**

Even for "Christmas Eve dinner with both families" with `participants_json = ["Panda","Maya","Mom","Dad"]`, both flags are false. The family graph resolver cannot determine that "Panda" is a partner or "Mom" is a parent without a kin registry.

**4. `nli_label` is questionable**

"Maya scared of thunderstorm. Held her until she fell asleep" → `nli_label = "contradiction"`. This is not a contradiction in any NLI sense. The NLI head may not be well-calibrated for single-sentence inputs (NLI requires premise-hypothesis pairs).

### THE UltraBERT DUPLICATION YOU MENTIONED

UltraBERT runs in **three places**:

1. **K1 Phase 1** (22ms): Intent, Domain, Safety, NER, Emotions, Sentiment — used to populate session state for LLM tools
2. **P02 Stage 20** (`semantic_project`): Calls `extract_ner_for_storage()` and `extract_entities()` from `ultrabert_adapter` — re-runs NER + relations + safety + NLI
3. **P02 Stage 30** (`affect.analyze`): Calls `analyze_affect()` from `ultrabert_adapter` — re-runs sentiment + emotions + safety

The bridge CommandEnvelope carries K1's Phase 1 UltraBERT output in the `body.band` field (safety) and implicitly through the Memory Writer's text construction, but the **raw UltraBERT head outputs from K1 are NOT forwarded** to K0. So P02 re-runs UltraBERT independently.

**The fix path**: Forward K1's UltraBERT cache through the CommandEnvelope (add a `ultrabert_cache` field), let P02 Stage 22 extract from that cache, and skip re-running UltraBERT in stages 20 and 30. This would save ~60ms per event.

### SUMMARY: Where Good Signals Come From

| Signal Source | Status | Notes |
|--------------|--------|-------|
| UltraBERT NER (ner_entities_json) | Working | Raw 3-head output stored correctly |
| UltraBERT INGRESS (activity_type_ultrabert) | Working | 12-type classification, good distribution |
| UltraBERT INTENT (intent_ultrabert) | Working | 8-type, reasonable quality |
| UltraBERT Safety (safety_familyos_band) | Working | All GREEN (expected for this data) |
| UltraBERT Relations (extracted_relations_json) | Working | `["child_of", "colleague_of"]` etc. |
| SimHash/MinHash fingerprints | Working | Unique per event |
| Inline embeddings (768-dim) | Working | 100% READY via ADR-K003 |
| Affect valence/arousal | Working | Real values, reasonable range |
| **Social context** | **BROKEN** | Never "family", only "friends"/"solo" |
| **Salience scoring** | **BROKEN** | Flat at 0.41, all MED, zero discrimination |
| **Family relationship flags** | **BROKEN** | has_partner/parent always false |
| **NLI labeling** | **Questionable** | "contradiction" on non-contradictory text |

Completed: *Synthesize end-to-end data flow* (8/8)

The three biggest problems that need fixing before P03 consolidation can produce meaningful results:

1. **Family graph is blind** — Without a kin registry mapping "Panda"→partner, "Maya"→child, "Mom"→parent, social_context will never be "family" and relationship flags will always be false. This single gap degrades salience by 50%.

2. **Salience is non-discriminating** — All 1348 rows are MED band. P03 consolidation that relies on salience_band to prioritize (HIGH events consolidated first) will treat everything equally.

3. **UltraBERT runs 3x** — K1 Phase 1 output is discarded at the bridge boundary. P02 re-runs the same model in stages 20 and 30, wasting ~60ms per event.

Yes, I understand exactly. The LLM in K1 is already doing deep cognitive work — understanding relationships, emotions, intent, context. The Memory Writer observes that rich conversation and prepares the envelope. If that envelope carries the LLM's high-quality signals directly, P02 mostly just validates/stores them rather than re-computing with UltraBERT. Strong P02 input → strong P03 consolidation.

Here's the complete research synthesis:

---

## SessionState → Memory Writer → P02 → P03: Signal Chain Analysis

### 1. What SessionState Already Has (K1's Rich Signals)

K1's SessionState holds **100KB of structured cognitive state** across 15 sections. The Memory Writer reads 5 of them:

| Section (MW Reads) | Key Signals Available | Currently Forwarded to Envelope? |
|---|---|---|
| **history_active** (8KB) | Last 10 turns with full fidelity, per-turn emotion/entities/intent | Only `user_message` + `assistant_response` (via `turn.complete.v1` payload) |
| **beliefs_active** (8KB) | SVO Facts (subject/predicate/object + confidence), EntityRef with aliases/person_id, MentionedTime, MentionedLocation | Entity names → PersonResolver → `participants[]` (person_ids). **Location and time NOT forwarded** |
| **affective_now** (4KB) | EmotionDimensions (valence/arousal/dominance), EmotionTrajectory (INCREASING/STABLE/DECREASING), per-turn EmotionSnapshot[], empathy_needed, celebration_appropriate | Only `current_emotion` as prompt context → LLM re-derives `sentiment_label` + `emotion_tags` |
| **scoreboard** (6KB) | Per-entity **salience scores** with decay_rate, QUD stack, Topics with is_primary flag | Only `active_topics` as prompt context → LLM re-derives `topics[]` |
| **meta** (2KB) | session_id, user_id, device_id, privacy_band | `session_id`, `privacy_band` forwarded |

**Key insight**: K1 has **machine-computed valence/arousal/dominance** (from UltraBERT Phase 1 in the Concierge pipeline), **entity-level salience scores**, **resolved person_ids with aliases**, and **narrative arcs** — but the MW envelope body carries only the LLM's re-derived text labels (`sentiment_label`, `emotion_tags`, `topics`), not the underlying dimensional scores.

### 2. What the MW Envelope Body Looks Like Today

From memory_writer_architecture.md:

```json
{
  "text": "Had dinner with Mom at Olive Garden",        // LLM-extracted (<=50 words)
  "participants": ["person_mom"],                        // PersonResolver from beliefs_active
  "location_name": "Olive Garden",                       // LLM-extracted
  "activity_type": "MEAL",                               // LLM-extracted
  "topics": ["family", "dining"],                        // LLM-extracted
  "sentiment_label": "positive",                         // LLM-extracted (5-class)
  "emotion_tags": ["contentment"],                       // LLM-extracted (44-class)
  "categories": ["social", "meal"],                      // LLM-extracted
  "confidence": 0.95,                                    // LLM's self-assessed confidence
  "session_id": "...",                                   // From meta
  "conversation_turn": 5,                                // From turn event
  "language": "en"                                       // From meta
}
```

### 3. What P02 Does With Each Signal (Recompute vs. Pass-Through)

| P02 Stage | MW Field Consumed | What P02 Does | Recomputation? |
|---|---|---|---|
| **M01** pattern_separate | `text` | SimHash + MinHash fingerprint | **YES** - raw text needed for dedup hashing |
| **M02** semantic_project | `text`, `participants`, `location_name`, `activity_type` | UltraBERT NER (3-head: ner_family, ner_general, ner_temporal), entity resolution, KG triples | **YES** - runs UltraBERT on `text` (15-30 tokens). Uses participants for entity resolution matching |
| **M22** embedding_extract | `text` (via UltraBERT cache) | 768-dim embedding from UltraBERT cache | Cache hit from M02's UltraBERT call |
| **M04** affect.analyze | `text` **only** | UltraBERT sentiment + emotions + safety. **IGNORES** MW's `sentiment_label` and `emotion_tags` | **FULL RECOMPUTE** - runs UltraBERT on raw text, discards MW signals |
| **M07** social.family_graph | `participants` (from body) | Queries `st_kg_edges` for relationships, classifies social_context | **FULL RECOMPUTE** from DB - ignores MW context. **THIS IS BROKEN** because st_kg_edges has no family data |
| **M08** temporal_profile | `event_time_utc` (from headers) | Extracts time-of-day, day-of-week | Minimal (deterministic from timestamp) |
| **M06** salience.score | All M04+M07+M08 outputs | 0.50×social + 0.40×affect + 0.10×recency | Computed from recomputed signals → **GARBAGE IN, GARBAGE OUT** |

### 4. The Core Problem: P02 Recomputes What K1 Already Knows (Worse)

The architecture doc ([Section 14](k1/memory_writer/memory_writer_architecture.md#L700)) explicitly states:

> *"UltraBERT is a safety net, not the primary source. MW LLM sees full conversation context; UltraBERT sees only 15-30 token text body."*

But P02's actual implementation **ignores MW signals completely**:

- **M04 affect.analyze**: Extracts `text = envelope.get("body", {}).get("text", "")` and runs UltraBERT fresh. Never reads `sentiment_label` or `emotion_tags` from the envelope body. The MW's LLM had **full conversation history** + scoreboard topics + affective_now emotion trajectory. UltraBERT sees "Had dinner with Mom at Olive Garden" — 8 tokens, no context.

- **M07 social.family_graph_resolve**: Reads `participants` from body, queries `st_kg_edges` for relationships. **st_kg_edges has no family relationship data** → every participant maps to "OTHER" → social_context falls back to "friends". Meanwhile, K1's beliefs_active **already knew** "Mom" = person_mom with relationship PARENT, "Panda" = partner. The PersonResolver resolved the names but the **relationship metadata was NOT forwarded**.

- **M06 salience.score**: Formula is `0.50×social + 0.40×affect + 0.10×recency`. With social_context stuck at "friends" (score 0.5) and affect_intensity often defaulting, salience = 0.50×0.5 + 0.40×0.4 + 0.10×0.8 = 0.25 + 0.16 + 0.08 = 0.49 → always MED. Should be: social="family" (1.0) → 0.50×1.0 + 0.40×0.4 + 0.10×0.8 = 0.74 → HIGH.

### 5. The Solution: Enrich the MW Envelope with K1's Pre-Computed Signals

**The LLM does the hard work. The envelope should carry its conclusions. P02 validates, not recomputes.**

#### A. New Envelope Fields (k1_signals extension)

```json
{
  // ... existing fields ...

  "k1_signals": {
    // From affective_now (machine-computed, not LLM-derived)
    "valence": 0.72,                    // -1.0 to 1.0 (float, not text label)
    "arousal": 0.35,                    // 0.0 to 1.0
    "dominance": 0.60,                  // 0.0 to 1.0
    "emotion_trajectory": "STABLE",     // INCREASING/STABLE/DECREASING
    "empathy_needed": false,
    "celebration_appropriate": true,

    // From scoreboard (entity salience)
    "entity_salience": {
      "person_mom": 0.85,              // Salience score from scoreboard
      "Olive_Garden": 0.40
    },
    "primary_topic": "family",          // is_primary=true from scoreboard

    // From beliefs_active (relationship context)
    "participant_relationships": {
      "person_mom": "PARENT_OF",        // K1 KNOWS this relationship
      "person_panda": "SPOUSE_OF"       // K1 KNOWS this too
    },

    // From narrative_active
    "narrative_position": "RISING_ACTION",
    "thread_id": "thread_dinner_plans",

    // Confidence metadata
    "signal_source": "k1_cognitive",    // vs "p02_ultrabert"
    "ultrabert_phase1_cached": true     // UltraBERT already ran in K1 Phase 1
  }
}
```

#### B. P02 Module Changes

| Module | Current | With k1_signals |
|---|---|---|
| **M04** affect.analyze | Runs UltraBERT on text (recompute) | **Trust** `k1_signals.valence/arousal/dominance`. Run UltraBERT only if `k1_signals` absent or `confidence < 0.5`. Use UltraBERT for safety classification only (clinical, self-harm detection — can't trust LLM for safety) |
| **M07** social.family_graph | Queries empty st_kg_edges → "friends" | **Trust** `k1_signals.participant_relationships`. Map PARENT_OF → PARENT role directly. Only query st_kg_edges if `k1_signals` absent. **This immediately fixes social_context = "family"** |
| **M06** salience.score | Garbage-in (from broken M04+M07) | Correct inputs from trusted k1_signals → correct salience. Also **forward** `k1_signals.entity_salience` as cross-validation |
| **M02** semantic_project | Runs UltraBERT NER on text | Keep NER (UltraBERT is good at entity extraction from short text). Use `k1_signals.participant_relationships` to improve entity resolution |
| **M22** embedding_extract | UltraBERT cache from M02 | No change needed — embedding still comes from UltraBERT |

#### C. UltraBERT Reduction: 3x → 1x

Currently UltraBERT runs:

1. **K1 Phase 1** (Concierge pipeline) — populates affective_now
2. **P02 M02** (semantic_project) — NER + embedding
3. **P02 M04** (affect.analyze) — sentiment + emotion + safety

With k1_signals:

- **K1 Phase 1**: Still runs (feeds SessionState for conversation quality)
- **P02 M02**: Still runs NER + embedding (UltraBERT is good for short-text NER)
- **P02 M04**: **SKIP UltraBERT for sentiment/emotion** (trust k1_signals). **KEEP UltraBERT for safety only** (clinical/self-harm detection is a safety-critical validation — never trust LLM alone for this)

Net: 3 full UltraBERT passes → 1 full (M02) + 1 partial (M04 safety-only) = ~40% reduction.

### 6. How This Flows to P03

Once P02 stores **correct** signals in st_hipp_events:

| st_hipp_events Column | Broken (Today) | Fixed (With k1_signals) |
|---|---|---|
| `social_context` | "friends" (68%) / "solo" (32%) | "nuclear_family" / "extended_family" / "friends" / "solo" — **correct distribution** |
| `salience_score` | 0.41 (60% stuck) | 0.25-0.95 **full range**, HIGH for family events |
| `salience_band` | ALL MED | HIGH/MED/LOW proper distribution |
| `has_partner_present` | ALWAYS FALSE | TRUE when Panda is participant |
| `has_parent_present` | ALWAYS FALSE | TRUE when Mom/Dad is participant |
| `affect_valence` | UltraBERT on 8 tokens | K1's context-aware valence (better) |

**P03 consolidation** reads st_hipp_events. With correct social_context, salience, and affect:

- **Anchor detection** can identify truly important memories (HIGH salience family events)
- **Pattern consolidation** can cluster by social context correctly
- **Decay/strengthening** curves work properly (family memories strengthen, not flatten)
- **Semantic similarity** for dedup has richer context (narrative position, entity salience)

### 7. Open Design Questions from MW Architecture Doc

From memory_writer_architecture.md:

- **Q2: Person Resolver accuracy** — ambiguous names ("Alex" = multiple people). K1's beliefs_active has aliases, but conflicts need resolution strategy.
- **Q6: Event time vs turn time** — "Had dinner yesterday" = yesterday 7pm or now()? K1's beliefs_active has MentionedTime with `resolved_ms` and `is_relative`. Forward this.
- **Q10: AMBER location generalization** — could use UltraBERT's ner_general LOC type. With k1_signals, could also forward beliefs_active MentionedLocation with `location_type`.

### Summary

The MW architecture doc itself says UltraBERT is a safety net, not primary. But P02's implementation treats UltraBERT as primary and **completely ignores** MW's LLM-derived signals. Adding `k1_signals` to the envelope body lets P02 trust K1's rich context (valence/arousal/dominance from affective_now, relationships from beliefs_active, entity salience from scoreboard) and only use UltraBERT for what it's actually good at: NER on short text and safety classification. This immediately fixes the broken social_context/salience/family-flags chain and gives P03 high-quality input for consolidation.

Let me re-read the current MW context assembly and prompt design to understand what needs to change for the 15-section reader:

Read [](file:///d%3A/familyos/k1/memory_writer/memory_writer_architecture.md#450-450), lines 450 to 700

Now let me check the current ExtractionContext structure to understand what gets compressed from the 5 sections:

Read [](file:///d%3A/familyos/k1/memory_writer/memory_writer_architecture.md#340-340), lines 340 to 460

Created 4 todos

Let me check the remaining SessionState sections I haven't read — particularly `clarifications`, `task_state`, and `artifacts_warm` — to understand all 15 sections MW would now consume:

Read [](file:///d%3A/familyos/poc/k1_poc/sessionstate/sections/clarifications.py#1-1), lines 1 to 100

Read [](file:///d%3A/familyos/poc/k1_poc/sessionstate/sections/beliefs_history.py#1-1), lines 1 to 100

Read [](file:///d%3A/familyos/poc/k1_poc/sessionstate/sections/history_recent.py#1-1), lines 1 to 100

Read [](file:///d%3A/familyos/poc/k1_poc/sessionstate/sections/telemetry.py#1-1), lines 1 to 80

Read [](file:///d%3A/familyos/poc/k1_poc/sessionstate/sections/artifacts_warm.py#1-1), lines 1 to 80

Starting: *Design tagged one-liner schema* (2/4)

Now I have the complete picture of all 15 sections, the current MW architecture, the P02 pipeline, and the broken signals. Let me think through the redesign and present it clearly.

---

Here's the thinking on the redesigned Memory Writer direction:

## The Core Shift: MW Becomes the Primary Intelligence

**Current**: MW reads 5 sections → 150 tokens context → LLM produces minimally-tagged text → P02 recomputes everything with UltraBERT on 8-token text fragments → garbage social/salience

**New**: MW reads ALL 15 sections → full cognitive state → LLM produces **richly-tagged one-liner atoms** with every field pre-computed → P02 validates with one UltraBERT pass and stores

### What MW Gets From All 15 Sections

| Section | What MW Extracts For Context | Memory-Relevant Signal |
|---|---|---|
| **HOT CORE** | | |
| `control` (8KB) | FlowPhase, PrivacyBand, SafetyContext, DomainContext | Which domain this memory belongs to, safety band |
| `beliefs_active` (8KB) | SVO Facts, EntityRef **with aliases + person_id**, MentionedTime (resolved_ms), MentionedLocation (location_type) | **Relationship knowledge** (Mom=PARENT, Panda=SPOUSE), resolved times ("yesterday" → epoch), location types |
| `scoreboard` (6KB) | Per-entity salience scores with decay_rate, QUD Topics with is_primary, Referent mention counts | **Entity importance ranking**, what the conversation is ABOUT |
| `history_active` (8KB) | Last 10 turns with full fidelity, per-turn emotion/entities/intent | Conversation arc, what was said, what matters |
| `clarifications` (4KB) | Pending/resolved questions, blocking state | Whether memory is about a clarification exchange (skip or tag) |
| `affective_now` (4KB) | valence/arousal/dominance (float), EmotionTrajectory, EmotionSnapshot[], empathy_needed, celebration_appropriate | **Machine-precise affect** — not text labels, actual dimensional scores |
| `narrative_active` (4KB) | ConversationThread (goal, state, related_entities), NarrativeArc (EXPOSITION→CLIMAX→RESOLUTION) | **Where in the story** this memory sits, thread linkage |
| `meta` (2KB) | session_id, user_id, device_id, privacy_band, turn_count, locale | Envelope headers, language detection |
| `task_state` (4KB) | TaskStateEntry lifecycle (PENDING→ACTIVE→COMPLETED), task_type | Whether memory is task-related, task completion status |
| `task_artifacts` (4KB) | ArtifactType, artifact content | Whether there's a concrete output (code, list, plan) associated |
| **WARM TIER** | | |
| `beliefs_history` (12KB) | Demoted facts (LRU, max 100), entity index | Older knowledge that might resolve ambiguous references |
| `history_recent` (16KB) | Turns 11-30 (compressed: entities+intents+key phrases), Turns 31-40 (summarized: single sentence) | Broader narrative context, what happened earlier in session |
| `persona` (8KB) | PersonalityProfile (warmth/formality/humor), VoicePreferences, InteractionStyle | Tone awareness (important for sentiment accuracy) |
| `telemetry` (4KB) | LatencyMetrics, ErrorMetrics, CostMetrics | NOT memory-relevant (skip in context) |
| `artifacts_warm` (8KB) | Demoted artifacts from older tasks | Historical task outputs (rarely memory-relevant) |

**Practical filter**: MW reads 15 sections but compresses intelligently. `telemetry` and `artifacts_warm` contribute zero memory signal — they get a 0-token allocation. `persona` contributes tone context (5 tokens). The real expansion comes from `narrative_active`, `task_state`, `beliefs_history`, and `history_recent`.

### The New Token Budget

```
+------------------------------------+--------+
| Component                          | Tokens |
+------------------------------------+--------+
| System prompt (enriched persona)   | ~120   |
| HOT CORE context (10 sections)     | ~250   |
|   beliefs_active (entities+facts)  |   60   |
|   scoreboard (salience+topics)     |   40   |
|   affective_now (dimensions)       |   20   |
|   narrative_active (arc+threads)   |   30   |
|   history_active (last 3 turns)    |   60   |
|   control (domain+safety)          |   10   |
|   clarifications (if active)       |   10   |
|   meta (ids+band)                  |   10   |
|   task_state (if task active)      |   10   |
| WARM context (compressed)          | ~80    |
|   beliefs_history (top 5 by LRU)   |   30   |
|   history_recent (session summary) |   30   |
|   persona (tone profile)           |   20   |
| Turn payload (user + assistant)    | ~100   |
| Output (1-3 tagged one-liners)     | ~250   |
| Headroom                           | ~50    |
+------------------------------------+--------+
| TOTAL                              | ~850   |
+------------------------------------+--------+
```

Cost increase: 500 → 850 tokens. At GPT-4o-mini rates that's $0.0017/turn vs $0.001/turn. Negligible.

### The Tagged One-Liner: What MW Produces

Each extraction is no longer just text + basic tags. It's a **fully pre-computed memory atom**:

```json
{
  "text": "Had dinner with Mom at Olive Garden to celebrate Emma's birthday",

  "participants": ["person_mom", "person_emma"],
  "participant_relationships": {
    "person_mom": "PARENT_OF",
    "person_emma": "CHILD_OF"
  },

  "location_name": "Olive Garden",
  "location_type": "restaurant",

  "activity_type": "MEAL",
  "topics": ["family", "dining", "celebration"],
  "categories": ["social", "meal"],

  "sentiment_label": "very_positive",
  "emotion_tags": ["joy", "contentment", "love"],
  "affect": {
    "valence": 0.82,
    "arousal": 0.45,
    "dominance": 0.70,
    "trajectory": "INCREASING"
  },

  "social_context": "nuclear_family",
  "social_intimacy": "HIGH",

  "entity_salience": {
    "person_mom": 0.85,
    "person_emma": 0.90,
    "Olive_Garden": 0.40
  },

  "narrative": {
    "thread_id": "thread_emmas_birthday",
    "arc_position": "CLIMAX",
    "is_goal_event": true
  },

  "temporal": {
    "mentioned_time": "yesterday evening",
    "resolved_epoch_ms": 1740600000000,
    "is_backdated": true
  },

  "task_context": null,

  "confidence": 0.95,
  "privacy_band": "GREEN"
}
```

**One-liner sentence. Every tag attached. Every field P02 needs is already here.**

The LLM knows:

- "Mom" is PARENT_OF because `beliefs_active` has that entity with alias
- valence is 0.82 because `affective_now` has the dimensional scores
- "nuclear_family" because it sees the participant relationships
- "CLIMAX" because `narrative_active` says we're at the high point of the birthday thread
- "yesterday evening" resolved to epoch because `beliefs_active.MentionedTime` has `resolved_ms`
- Entity salience from `scoreboard` Referent scores

### What P02 Becomes: Validate-Store-Dedup

| P02 Stage | Current Role | New Role |
|---|---|---|
| **M01** pattern_separate | SimHash + MinHash from text | **SAME** — dedup MUST compute fresh fingerprints from text. No change. |
| **M02** semantic_project | UltraBERT NER + entity resolution + KG triples | **Reduced**: Run UltraBERT **once** for NER + embedding. Use MW's `participant_relationships` to validate entity resolution. KG triples built from MW's pre-tagged relationships (richer context). Store raw UltraBERT NER for P03 cross-validation. |
| **M22** embedding_extract | Extract 768-dim from UltraBERT cache | **SAME** — embedding comes from M02's single UltraBERT call |
| **M04** affect.analyze | Full UltraBERT sentiment+emotion+safety recompute | **VALIDATE ONLY**: Trust MW's `affect.valence/arousal/dominance`. Run UltraBERT for **safety heads only** (clinical/self-harm — never trust LLM alone for safety). Compare MW sentiment vs UltraBERT sentiment → log divergence, use MW if delta < 0.3 |
| **M07** social.family_graph | Query empty st_kg_edges → always "friends" | **TRUST MW**: Use `participant_relationships` and `social_context` directly from envelope. Write relationships to st_kg_edges for future reference. Only query DB if `k1_signals` absent. **Immediately fixes the broken chain.** |
| **M06** salience.score | 0.50×social + 0.40×affect + 0.10×recency | **CROSS-VALIDATE**: Compute salience from MW's pre-tagged social_context and affect. Compare with `entity_salience` from MW. Use MW's entity_salience as per-entity granularity (P02 formula gives per-event score, MW gives per-entity). |
| **M08** temporal_profile | Extract time patterns from timestamp | **ENRICHED**: Use MW's `temporal.resolved_epoch_ms` for backdated events instead of envelope timestamp. Detect "yesterday" → correct event_time. |
| **M60** hipp_events_row | Assemble 80+ columns from module outputs | Assemble from validated MW signals + UltraBERT safety validation + fresh dedup fingerprints |

### UltraBERT: From 3 Passes to 1.5

| Pass | Current | New |
|---|---|---|
| K1 Phase 1 | Full UltraBERT (intent, domain, safety, NER, emotion, sentiment) → SessionState | **SAME** — feeds conversation quality |
| P02 M02 | Full UltraBERT (NER + relations + safety + NLI + embedding) | **KEEP** — NER is valuable, embedding is needed. Single pass. |
| P02 M04 | Full UltraBERT (sentiment + emotions + safety) | **SAFETY ONLY** — skip sentiment/emotion heads (trust MW). Run safety heads for clinical detection. ~60% cheaper. |

Net: 3 full passes → 1 full (M02) + 1 partial safety-only (M04) = **~50% UltraBERT reduction**.

### Why This Creates Gorgeous Memory Formations

**Before** (broken chain):

```
User says: "Had dinner with Mom at Olive Garden for Emma's birthday"
MW produces: text + sentiment:"positive" + topics:["family","dining"]
P02 recomputes: UltraBERT on 8 tokens → social_context:"friends" → salience:0.41 MED
st_hipp_events: flat, undiscriminating, family-blind
P03 consolidation: everything looks the same → no anchors, no patterns
```

**After** (rich chain):

```
User says: "Had dinner with Mom at Olive Garden for Emma's birthday"
MW produces: text + valence:0.82 + social:"nuclear_family" + relationships:{mom:PARENT,emma:CHILD}
           + salience:{person_emma:0.90} + arc:"CLIMAX" + thread:"emmas_birthday"
P02 validates: UltraBERT confirms sentiment positive (match) + safety:GREEN
             + SimHash fingerprint (fresh) + embedding (768-dim)
st_hipp_events: rich, discriminating, family-aware
  social_context: "nuclear_family"
  salience_score: 0.78 HIGH
  has_parent_present: TRUE
  affect_valence: 0.82
  narrative_thread_id: "emmas_birthday"
P03 consolidation: HIGH salience family events cluster → anchors form
                   Birthday thread episodes link → narrative pattern emerges
                   PARENT relationship strengthens → social graph grows
```

### The Session → Envelopes Flow

```
Session starts (Turn 1)
  MW reads 15 sections (snapshot, <1ms)
  Turn is "Hi, I'm planning Emma's birthday dinner"
  MW produces 1 envelope:
    "Planning birthday dinner for Emma"
    + activity:TASK + social:nuclear_family + arc:EXPOSITION + task_state:PENDING

Turn 3: "Mom suggested Olive Garden, sounds perfect"
  MW produces 1 envelope:
    "Mom suggested Olive Garden for Emma's birthday dinner"
    + location_type:restaurant + social:nuclear_family + arc:RISING_ACTION
    + participant_relationships:{person_mom:PARENT}

Turn 5: "We went last night, Emma loved it, blew out candles"
  MW produces 2 envelopes:
    [1] "Had birthday dinner with Mom and Emma at Olive Garden"
        + activity:MEAL + social:nuclear_family + arc:CLIMAX + valence:0.82
        + entity_salience:{person_emma:0.95}
    [2] "Emma blew out birthday candles at Olive Garden"
        + activity:CELEBRATION + emotion_tags:[joy,excitement] + valence:0.90
        + is_goal_event:true

Turn 7: "She was so happy, best birthday ever"
  MW produces 1 envelope:
    "Emma had the best birthday celebration"
    + arc:RESOLUTION + emotion_tags:[love,contentment] + trajectory:STABLE
    + thread_complete:true
```

Each envelope is a **self-contained memory atom**: one-liner, all tags, no essays. P02 validates each, stores each. P03 later sees 4 HIGH-salience nuclear_family events in thread "emmas_birthday" spanning EXPOSITION→RESOLUTION. That's a gorgeous memory formation.

### Open Questions for This Direction

| # | Question | Impact |
|---|---|---|
| 1 | **LLM budget 850 vs 500 tokens**: Is the ~$0.0007/turn increase acceptable? | Cost |
| 2 | **affect.valence/arousal/dominance**: Should MW forward the raw `affective_now` floats, or should the LLM re-interpret them for the specific extraction? (e.g., session valence is 0.82 but this specific memory about a parking ticket might be 0.30) | Signal accuracy |
| 3 | **participant_relationships from beliefs_active**: What if beliefs_active doesn't have the relationship? (First mention of a new person) → fallback to LLM inference + P02 UltraBERT ner_family validation | Coverage |
| 4 | **narrative.thread_id**: Generated by LLM or taken from `narrative_active.ConversationThread.id`? If LLM generates, P02 can't validate. If taken from SessionState, it's deterministic. | Consistency |
| 5 | **Envelope schema versioning**: ~~RESOLVED -- not in production, no dual-mode needed. MW v2 is THE implementation. P02 always expects v2 fields.~~ | N/A |
| 6 | **WARM sections read latency**: Reading 15 sections vs 5. Still <1ms (in-memory FlatBuffers, lock-free). But more data to compress into context. | Performance |
| 7 | **Per-extraction vs per-turn affect**: Session affect is one snapshot. But a turn might produce 2 memories with different emotional valence ("Happy about birthday but worried about Mom's cough"). Should MW produce per-extraction affect? | Granularity |

Question 2 and 7 are the same design tension: **session-level signals vs extraction-level signals**. The answer is likely: MW's LLM uses the session-level dimensional scores as context but produces **per-extraction** affect tags. The `affective_now` valence of 0.82 becomes context, but the LLM can output valence 0.30 for a specific worried-about-health extraction from the same turn.

Good. All research complete. Here are the confirmed findings:

**`narrative_thread_id`**: System-generated. `ConversationThread.id` is created via `str(uuid.uuid4())` at narrative_active.py inside `create_thread()`. The system (Concierge/Orchestrator) creates threads, not the LLM. So MW reads `narrative_active.primary_thread.id` — a deterministic UUID — and forwards it in the envelope. P02 can store it as-is. No LLM involvement.

**`cognitive_trace_id`**: Present everywhere. MW invariant MW-10 explicitly requires it ([memory_writer_architecture.md line 170](k1/memory_writer/memory_writer_architecture.md#L170)). The trace ID flows from:

- `turn.complete.v1` event payload → MW pipeline → Envelope Builder injects into headers → Bridge preserves → K0 Gate → P02 all modules → st_hipp_events → P03.
- All P02 modules receive it via `message.trace_id` (confirmed in test files for pattern_separate, semantic_project, family_graph_resolve).
- Full causality chain documented in memory_writer_architecture.md.

**Bridge versioning**: Confirmed from the diagram. Bridge's `CommandBuilder` owns envelope structure. `IKernelCommandPort.submit(topic, schema_uri, body)` — K1 passes an arbitrary `body` dict. Bridge wraps it with crypto headers (sig, sig_kid, envelope_sha256, idem_key). K0's `MinimalGate` validates the envelope integrity but the `body` is opaque — K0 reads whatever fields are there. So K1 can add `k1_signals`, `participant_relationships`, `affect` etc. to the body independently. K0 P02 modules just need to check for those fields and use them if present, falling back to recomputation if absent. No Bridge changes needed.

Now let me synthesize the final design:

Starting: *Write final design synthesis* (7/7)

Here's the final synthesis based on all research + your decisions:

---

## Final Design: Powerful Memory Writer, Standard P02

### Design Decisions (Locked)

| # | Decision | Rationale |
|---|---|---|
| 1 | **2000 token budget** | Envelope quality > cost. ~$0.003/turn at GPT-4o-mini. |
| 2 | **Per-extraction affect** | Session affect dilutes. "Loved friend's engagement" (valence: 0.85) and "Sad seeing Jessica" (valence: -0.40) come from same turn — LLM detects per-atom. Session `affective_now` is context, not the output. |
| 3 | **`narrative_thread_id` = system UUID** | Created by `create_thread()` at narrative_active.py via `uuid.uuid4()`. MW reads `narrative_active.primary_thread.id` and forwards. No LLM generation. Deterministic, traceable. |
| 4 | **`cognitive_trace_id` everywhere** | Confirmed. MW-10 invariant. Flows: turn.complete.v1 → MW → Bridge → K0 Gate → P02 all modules → st_hipp_events. Full causality chain. |
| 5 | **K1 adds fields independently, K0 accepts any body** | Bridge's `IKernelCommandPort.submit(topic, schema_uri, body)` passes opaque body. Bridge adds crypto headers. K0 P02 checks for new fields, falls back to recomputation if absent. Zero Bridge changes. |
| 6 | **One LLM call, one snapshot, up to ~50 atomic envelopes** | Single SessionState snapshot (<1ms), single LLM call with 2000 token budget, LLM produces N memory atoms, each becomes one envelope. 250ms batch window, single Bridge POST. |
| 7 | **Per-turn affect, LLM detects** | Each atom carries its own valence/arousal/dominance. LLM uses session-level `affective_now` as context but outputs per-atom dimensions based on the actual content of that specific memory. |

### The Memory Atom Schema (What Each Envelope Body Looks Like)

```json
{
  "text": "Sad to see Jessica my school friend struggling",

  "participants": ["person_jessica"],
  "participant_relationships": {
    "person_jessica": { "type": "FRIEND_OF", "source": "beliefs_active" }
  },

  "location_name": null,
  "location_type": null,

  "activity_type": "SOCIAL",
  "topics": ["friendship", "concern"],
  "categories": ["social"],

  "sentiment_label": "negative",
  "emotion_tags": ["sadness", "concern", "empathy"],
  "affect": {
    "valence": -0.40,
    "arousal": 0.55,
    "dominance": 0.30
  },

  "social_context": "friends",
  "social_intimacy": "MED",

  "entity_salience": {
    "person_jessica": 0.70
  },

  "narrative": {
    "thread_id": "a1b2c3d4-e5f6-...",
    "arc_position": "RISING_ACTION",
    "is_goal_event": false
  },

  "temporal": {
    "mentioned_time": null,
    "resolved_epoch_ms": null,
    "is_backdated": false
  },

  "task_context": null,

  "confidence": 0.88,
  "privacy_band": "GREEN",

  "session_id": "sess-xyz",
  "conversation_turn": 12,
  "language": "en"
}
```

**Same turn, second atom** — different affect entirely:

```json
{
  "text": "Loved being at Rohan's engagement party with college friends",

  "participants": ["person_rohan"],
  "participant_relationships": {
    "person_rohan": { "type": "FRIEND_OF", "source": "beliefs_active" }
  },

  "location_name": null,
  "location_type": null,

  "activity_type": "CELEBRATION",
  "topics": ["friendship", "celebration"],
  "categories": ["social", "event"],

  "sentiment_label": "very_positive",
  "emotion_tags": ["joy", "excitement", "love"],
  "affect": {
    "valence": 0.85,
    "arousal": 0.70,
    "dominance": 0.65
  },

  "social_context": "friends",
  "social_intimacy": "MED",

  "entity_salience": {
    "person_rohan": 0.80
  },

  "narrative": {
    "thread_id": "a1b2c3d4-e5f6-...",
    "arc_position": "RISING_ACTION",
    "is_goal_event": false
  },

  "temporal": null,
  "task_context": null,

  "confidence": 0.92,
  "privacy_band": "GREEN",

  "session_id": "sess-xyz",
  "conversation_turn": 12,
  "language": "en"
}
```

One turn. Two atoms. Two completely different emotional signatures. If we'd used session-level affect (avg valence ~0.25), both would be wrong. Per-extraction catches the real human messiness.

### MW 15-Section Reader — What Goes Into the 2000 Token Budget

```
+----------------------------------------------+--------+
| Component                                    | Tokens |
+----------------------------------------------+--------+
| System prompt (persona + output schema)      | ~200   |
|                                              |        |
| HOT CORE snapshot (10 sections)              | ~350   |
|   history_active: last 3-5 turns (fidelity)  |  100   |
|   beliefs_active: entities + SVO facts       |   80   |
|   scoreboard: salience + topics + QUD        |   50   |
|   affective_now: valence/arousal/trajectory   |   25   |
|   narrative_active: thread + arc + goal      |   35   |
|   control: domain + safety_band + phase      |   15   |
|   task_state: active tasks (if any)          |   20   |
|   task_artifacts: recent outputs (if any)    |   15   |
|   meta: session/user/band/locale             |   10   |
|   clarifications: pending (if blocking)      |    0   |
|                                              |        |
| WARM context (compressed)                    | ~100   |
|   beliefs_history: top 10 by LRU             |   40   |
|   history_recent: session_summary            |   40   |
|   persona: tone profile (5 traits)           |   20   |
|   telemetry: SKIP (0 tokens)                 |    0   |
|   artifacts_warm: SKIP (0 tokens)            |    0   |
|                                              |        |
| Turn payload (user + assistant full text)    | ~150   |
|                                              |        |
| Output (1-N atoms, each ~80 tokens)          | ~500   |
|   (up to 6 atoms per turn at 80 tokens each) |        |
|                                              |        |
| Headroom                                     | ~200   |
+----------------------------------------------+--------+
| TOTAL                                        | ~1500  |
| BUDGET                                       |  2000  |
+----------------------------------------------+--------+
```

**Key change from old design**: Old MW read 5 sections (150 tokens), gave LLM minimal context, produced text + 4 basic tags. New MW reads all 15, gives LLM the full cognitive picture, LLM produces fully-tagged atoms with per-extraction affect, relationships, salience, narrative position.

### What P02 Becomes: Validate + Dedup + Embed + Store

| P02 Stage | Role | Details |
|---|---|---|
| **M01 pattern_separate** | **SAME** | SimHash + MinHash from `text`. Dedup requires fresh fingerprints. No change. |
| **M02 semantic_project** | **NER + Embed + Validate** | Single UltraBERT pass: NER (3-head), embedding (768-dim). Cross-validate MW's `participants` against UltraBERT ner_family. Store raw NER for P03. Use MW `participant_relationships` for entity resolution (instead of empty st_kg_edges). KG triples enriched by MW relationships. |
| **M22 embedding_extract** | **SAME** | Cache hit from M02's UltraBERT. |
| **M04 affect.analyze** | **VALIDATE + SAFETY** | Trust MW `affect.valence/arousal/dominance` as primary. Run UltraBERT **safety heads only** (clinical/self-harm — never trust LLM for safety). Compare MW sentiment vs UltraBERT: if divergence > 0.3, log warning, use UltraBERT override. If MW `affect` is absent (old envelope), full recompute as today. |
| **M07 social.family_graph** | **TRUST MW** | Use `participant_relationships` and `social_context` from envelope directly. Write to st_kg_edges for future P03 reference. Only query DB if `participant_relationships` absent. **Immediately fixes broken social_context.** |
| **M06 salience.score** | **CROSS-VALIDATE** | Compute using MW's correct `social_context` + MW's `affect.valence`. Cross-validate against `entity_salience` from MW. Per-entity salience stored alongside per-event salience. |
| **M08 temporal_profile** | **ENRICHED** | Use MW `temporal.resolved_epoch_ms` for backdated events ("yesterday evening" → correct epoch). If absent, use envelope timestamp as today. |
| **M60 hipp_events_row** | **ENRICHED** | New columns: `narrative_thread_id`, `narrative_arc_position`, `is_goal_event`, `k1_signal_source` (for provenance). Assemble from validated MW signals + UltraBERT safety + fresh fingerprints. |
| **M70 atomic_writer** | **SAME** | 3-table atomic write. |

### UltraBERT: 3x → 1.5x

| Pass | What | Cost |
|---|---|---|
| K1 Phase 1 | Full (feeds SessionState for conversation) | **Keep** |
| P02 M02 | NER + embedding (one pass) | **Keep** |
| P02 M04 | ~~Full sentiment+emotion+safety~~ → **Safety heads only** | **~60% cheaper** |

### The Flow: Session → Atoms → st_hipp_events

```
Session Turn 12:
  User: "Went to Rohan's engagement. Was amazing! But ran into Jessica
         from school... she's not doing well, felt really sad for her."

  MW reads 15 sections (snapshot <1ms):
    beliefs_active: {person_rohan: FRIEND, person_jessica: FRIEND (school)}
    scoreboard: {person_rohan: salience 0.80, person_jessica: salience 0.70}
    affective_now: {valence: 0.25, arousal: 0.60}  // mixed session
    narrative_active: {thread: "weekend_events", arc: RISING_ACTION}
    persona: {warmth: 0.8, humor: 0.6}

  MW LLM (single call, ~1200 tokens used):
    Produces 2 memory atoms:

    Atom 1: "Loved being at Rohan's engagement party"
      affect: {valence: 0.85, arousal: 0.70}
      social_context: "friends", activity_type: "CELEBRATION"
      entity_salience: {person_rohan: 0.80}

    Atom 2: "Sad to see Jessica struggling, felt empathy for her"
      affect: {valence: -0.40, arousal: 0.55}
      social_context: "friends", activity_type: "SOCIAL"
      entity_salience: {person_jessica: 0.70}

  250ms batch → 2 envelopes → Bridge → K0

  P02 processes each atom:
    M01: SimHash fingerprint (fresh) ✓
    M02: UltraBERT NER confirms "Rohan"=PER, "Jessica"=PER ✓
         MW participants match NER ✓
    M04: Safety heads → GREEN ✓
         MW sentiment "very_positive"/"negative" matches UltraBERT ✓
    M07: MW says FRIEND_OF → social_context "friends" ✓ (no DB needed)
    M06: Atom 1 salience: 0.50×0.5 + 0.40×0.85 + 0.10×1.0 = 0.69 (HIGH!)
         Atom 2 salience: 0.50×0.5 + 0.40×0.55 + 0.10×1.0 = 0.57 (MED)

  st_hipp_events gets 2 DISCRIMINATING rows:
    Row 1: valence=0.85, social="friends", salience=0.69 HIGH,
            thread="weekend_events", emotion=[joy,excitement]
    Row 2: valence=-0.40, social="friends", salience=0.57 MED,
            thread="weekend_events", emotion=[sadness,empathy]
```

Compare to today: both rows would get social_context="friends" (OK here, but by accident), salience=0.41 MED (both flat), no thread_id, no per-atom affect. The system couldn't tell "celebration" from "sadness" at the storage level.

### What P03 Gets: Gorgeous Memory Formations

With correctly tagged atoms in st_hipp_events, P03 consolidation sees:

- **Salience discrimination**: HIGH for family dinner, MED for friend meetup, LOW for routine task. Anchor detection actually works.
- **Social context accuracy**: "nuclear_family" when Mom+Emma, "friends" when Rohan, "solo" when journaling. Social graph grows from MW's `participant_relationships` written to st_kg_edges by M07.
- **Narrative threads**: Episodes linked by `thread_id`. P03 can trace "Emma's birthday" from EXPOSITION → RESOLUTION. Episode chains form naturally.
- **Per-atom affect**: Emotional diversity preserved. P03's SRE algorithm (Social Relationship Recalibration) gets real emotional_diversity scores instead of flat 0.41 everywhere.
- **Entity salience**: Per-entity importance from K1's scoreboard. P03 knows Emma was the most salient entity in the birthday thread (0.95), not equally weighted with the restaurant (0.40).

**The bottom line**: MW does the thinking. P02 validates and stores. P03 consolidates rich, discriminating, context-aware memory atoms. No more flat salience. No more family-blind social context. No more lost narrative threads.

### What Needs Building

| Component | Where | What |
|---|---|---|
| **MW 15-section reader** | `k1/memory_writer/context/session_reader.py` | Expand from 5 → 15 sections. Compress intelligently (skip telemetry/artifacts_warm). |
| **MW enriched prompt** | `k1/memory_writer/extraction/prompts/memory_writer_persona.md` | New system prompt with output schema for fully-tagged atoms. 2000 token budget. |
| **MW Envelope Builder v2** | `k1/memory_writer/envelope/envelope_builder.py` | Map all new fields (affect, participant_relationships, entity_salience, narrative, temporal) into body. |
| **P02 M04 safety-only mode** | analyze.py | Check for `body.affect`, trust MW values, run UltraBERT safety heads only. |
| **P02 M07 MW-trust mode** | family_graph_resolve.py | Check for `body.participant_relationships`, use directly, write to st_kg_edges. |
| **P02 M06 enriched salience** | score.py | Use MW social_context + MW affect for correct formula inputs. |
| **P02 M08 backdating** | temporal_profile.py | Use `body.temporal.resolved_epoch_ms` if present. |
| **P02 M60 new columns** | hipp_events_row.py | Map `narrative_thread_id`, `narrative_arc_position`, `is_goal_event`, `k1_signal_source`. |
| **Migration** | migrations | Add narrative_thread_id, narrative_arc_position, is_goal_event, k1_signal_source to st_hipp_events. |

Completed: *Write final design synthesis* (7/7)

## LAYER 1: What Memory Writer Reads from SessionState

MW takes a <1ms snapshot of ALL 15 sections. Here's what it actually USES per atom:

### HOT CORE (8 sections, 52KB) -- ALL READ

| Section | Data Structures | What MW Extracts | Dimension Fed |
|---|---|---|---|
| **control** (8KB) | `safety_band`, `intents[]`, `domains[]`, `FlowPhase` | `privacy_band`, `intent_type` (primary from intents[0]), `domains` | POLICY, WHY |
| **beliefs_active** (8KB) | `Fact{subject,predicate,object,confidence}`, `EntityRef{id,type,display_name}`, `MentionedTime{raw_text,resolved_ms,is_relative}`, `MentionedLocation{raw_text,location_type,entity_id}` | `participants`, `participant_relationships`, `location_name`, `location_type`, `temporal.mentioned_time`, `temporal.resolved_epoch_ms`, `temporal.is_backdated` | WHO, WHERE, WHEN, WHAT |
| **scoreboard** (6KB) | `Referent{entity_id,salience,mention_count}`, `Topic{name,salience,is_primary}`, `Question{status}`, `SalienceEntry{score,decay_rate}` | `entity_salience{}`, `topics[]`, novelty detection (compare new fact vs known referents) | SALIENCE, WHAT, SURPRISE |
| **history_active** (8KB) | `Turn{user_message,assistant_response,emotion,entities,intents}`, last 10 turns | `elaboration_depth` (how many turns on this topic), `source_type` (user stated vs system inferred from conversation pattern) | DEPTH, SOURCE |
| **affective_now** (4KB) | `EmotionDimensions{valence,arousal,dominance}`, `current_emotion`, `trajectory`, `EmotionSnapshot[]`, `empathy_needed`, `celebration_appropriate`, `source` | `affect{valence,arousal,dominance}`, `emotion_tags[]`, `sentiment_label` | EMOTION |
| **narrative_active** (4KB) | `ConversationThread{id,title,state,goal,is_goal_met,related_entities}`, `NarrativeArc{position}`, `paused_threads[]` | `narrative.thread_id`, `narrative.arc_position`, `narrative.is_goal_event`, `goal_context` | NARRATIVE, WHY |
| **clarifications** (4KB) | `Clarification{question,status,related_entity}` | If pending = skip extraction (conversation incomplete) | SKIP SIGNAL |
| **task_state** (4KB) | `TaskStateEntry{task_id,action,status}` | `task_context` (if extraction relates to an active task) | WHY |
| **task_artifacts** (4KB) | `ArtifactType`, `TaskArtifactEntry` | (rarely used, only if task produced artifact relevant to memory) | -- |
| **meta** (2KB) | `SessionIdentity{session_id,user_id,device_id,privacy_band}`, `SessionLifecycle{turn_count}` | `session_id`, `conversation_turn`, `privacy_band`, `user_id` | IDENTITY |

### WARM (4 sections, 48KB) -- SELECTIVELY READ

| Section | What MW Extracts | Dimension Fed |
|---|---|---|
| **beliefs_history** (12KB) | Demoted facts for NOVELTY detection: does this new fact contradict or repeat an old one? | SURPRISE |
| **history_recent** (16KB) | Compressed turns 11-30 for elaboration depth (was this topic discussed earlier in session?) | DEPTH |
| **persona** (8KB) | `PersonalityProfile{warmth,formality}`, `InteractionStyle` -- MW uses to determine `identity_domains` (which self is engaged: parent, professional, etc.) | SELF |
| **telemetry** (4KB) | **SKIP** -- 0 memory relevance | -- |
| **artifacts_warm** (4KB) | **SKIP** -- demoted artifacts, 0 memory relevance | -- |

### Key Derived Signals (MW computes from cross-section analysis)

| Signal | How Computed | Output Field |
|---|---|---|
| `source_type` | If user explicitly stated fact in `history_active.turns[].user_message` = `"user_stated"`. If inferred from context/belief = `"user_implied"`. If from device sensor = `"device_observed"`. If MW deduced from patterns = `"system_inferred"`. | `source_type` |
| `novelty` | Compare extraction against `beliefs_active.current_turn_facts` + `beliefs_history` + `scoreboard.referents`. New entity = NOVEL. Repeated pattern = ROUTINE. Contradicts known fact = SURPRISING. | `novelty` |
| `elaboration_depth` | Count turns in `history_active` + `history_recent` that discuss same entities/topics. 1 turn = MENTION. 2-3 = DISCUSSED. 4-6 = ELABORATED. 7+ = DEEPLY_PROCESSED. | `elaboration_depth` |
| `identity_domains` | Map `scoreboard.topics[].name` + `control.domains[]` to identity categories. HEALTH domain = `["health_self"]`. RELATIONSHIP + family entities = `["parent"]`. FINANCE = `["financial_self"]`. | `identity_domains[]` |
| `temporal_orientation` | If `MentionedTime.resolved_ms` < now = `"PAST"`. If fact describes ongoing condition (no time bound) = `"ONGOING"`. If `MentionedTime.resolved_ms` > now = `"FUTURE_COMMITMENT"`. | `temporal_orientation` |
| `goal_context` | If `narrative_active.primary_thread.goal` is non-empty AND extraction is related to thread's `related_entities` = forward the goal string. Else null. | `goal_context` |

---

## LAYER 2: What Memory Writer Produces (Envelope Body v2)

### Full Memory Atom Schema

This is the EXACT JSON body that MW v2 sends per envelope. Every field documented.

```json
{
  "schema_version": "2.0",
  "operation": "UPSERT",

  "text": "Had dinner with Mom at Olive Garden for Emma's birthday",

  "participants": ["person_mom", "person_emma"],
  "participant_relationships": {
    "person_mom": {"type": "PARENT_OF", "target": "person_user", "confidence": 0.95},
    "person_emma": {"type": "CHILD_OF", "target": "person_user", "confidence": 0.90}
  },

  "location_name": "Olive Garden",
  "location_type": "restaurant",

  "activity_type": "CELEBRATION",

  "topics": ["family", "dining", "celebration"],
  "categories": ["social", "meal"],

  "sentiment_label": "positive",
  "emotion_tags": ["joy", "contentment"],
  "affect": {
    "valence": 0.82,
    "arousal": 0.45,
    "dominance": 0.70
  },

  "social_context": "nuclear_family",
  "social_intimacy": "HIGH",
  "entity_salience": {
    "person_mom": 0.85,
    "person_emma": 0.72
  },

  "narrative": {
    "thread_id": "a3f8c2d1-...",
    "arc_position": "RISING_ACTION",
    "is_goal_event": false
  },

  "temporal": {
    "mentioned_time": "yesterday evening",
    "resolved_epoch_ms": 1740600000000,
    "is_backdated": true
  },

  "intent_type": "log_memory",
  "goal_context": null,
  "source_type": "user_stated",
  "novelty": "EXPECTED",
  "elaboration_depth": "DISCUSSED",
  "identity_domains": ["parent"],
  "temporal_orientation": "PAST",

  "task_context": null,
  "confidence": 0.95,

  "session_id": "session-abc123",
  "conversation_turn": 5,
  "language": "en"
}
```

### Field Reference (v2 Complete)

| # | Field | Type | Req | Enum / Constraints | Source | Dimension |
|---|---|---|---|---|---|---|
| 1 | `schema_version` | string | Y | `"2.0"` | Constant | -- |
| 2 | `operation` | string | Y | `"UPSERT"` | Constant | -- |
| 3 | `text` | string | Y | 1-50 words, past/present tense, self-contained | LLM extraction | WHAT |
| 4 | `participants` | string[] | N | `person_*` format, resolved by Person Resolver | LLM + beliefs_active EntityRef | WHO |
| 5 | `participant_relationships` | object | N | `{person_id: {type, target, confidence}}`. type enum: `PARENT_OF, CHILD_OF, SPOUSE_OF, SIBLING_OF, FRIEND_OF, COLLEAGUE_OF, CARETAKER_OF, OTHER` | beliefs_active Fact SVO where predicate is relationship | WHO |
| 6 | `location_name` | string | N | Place name (stripped in RED band) | LLM + beliefs_active MentionedLocation | WHERE |
| 7 | `location_type` | string | N | `home, restaurant, hospital, school, office, gym, store, park, church, airport, hotel, other` | LLM inference from location_name | WHERE |
| 8 | `activity_type` | string | N | `MEAL, TASK, TRAVEL, HEALTH, SOCIAL, WORK, EDUCATION, EXERCISE, SHOPPING, ENTERTAINMENT, CELEBRATION, APPOINTMENT, DIARY, FINANCE, RELATIONSHIP, PLANNING, CONCERN, GRATITUDE, META, MEMORY` (merged K1 12-type + legacy 12-type) | LLM + control.domains[0] | WHAT |
| 9 | `topics` | string[] | Y | 1-3 tags | LLM | WHAT |
| 10 | `categories` | string[] | N | Activity categories | LLM | WHAT |
| 11 | `sentiment_label` | string | Y | `very_negative, negative, neutral, positive, very_positive` | LLM from affective_now | EMOTION |
| 12 | `emotion_tags` | string[] | N | From 44-class emotion set | LLM from affective_now.current_emotion | EMOTION |
| 13 | `affect` | object | Y | `{valence: -1..+1, arousal: 0..1, dominance: 0..1}` | affective_now.dimensions (direct copy) | EMOTION |
| 14 | `social_context` | string | N | `solo, friends, colleagues, nuclear_family, extended_family, community` | MW derives from participant_relationships (if any has PARENT/CHILD/SPOUSE = nuclear_family) | WHO |
| 15 | `social_intimacy` | string | N | `LOW, MEDIUM, HIGH` | MW derives from relationship types (family=HIGH, friends=MEDIUM, unknown=LOW) | WHO |
| 16 | `entity_salience` | object | N | `{person_id: float 0..1}` | scoreboard.salience_map entries for participants | SALIENCE |
| 17 | `narrative.thread_id` | string | N | UUID from narrative_active.primary_thread.id | System-generated UUID | NARRATIVE |
| 18 | `narrative.arc_position` | string | N | `EXPOSITION, RISING_ACTION, CLIMAX, RESOLUTION` | narrative_active.arc.position | NARRATIVE |
| 19 | `narrative.is_goal_event` | bool | N | true if extraction matches thread.goal | MW checks thread.goal vs extraction text | NARRATIVE |
| 20 | `temporal.mentioned_time` | string | N | Raw text ("yesterday evening") | beliefs_active.MentionedTime.raw_text | WHEN |
| 21 | `temporal.resolved_epoch_ms` | int64 | N | Unix ms (resolved absolute) | beliefs_active.MentionedTime.resolved_ms | WHEN |
| 22 | `temporal.is_backdated` | bool | N | true if mentioned_time != now | MW compares resolved_ms vs current time | WHEN |
| 23 | `intent_type` | string | Y | `log_memory, query_memory, set_reminder, express_feeling, seek_advice, share_news, reflect, other` | control.intents[0] (UltraBERT primary) | WHY |
| 24 | `goal_context` | string | N | Active thread goal (if relevant) | narrative_active.primary_thread.goal | WHY |
| 25 | `source_type` | string | Y | `user_stated, user_implied, device_observed, system_inferred` | MW cross-ref: history_active turns vs extraction origin | SOURCE |
| 26 | `novelty` | string | Y | `ROUTINE, EXPECTED, NOVEL, SURPRISING` | MW compares against beliefs + scoreboard | SURPRISE |
| 27 | `elaboration_depth` | string | Y | `MENTION, DISCUSSED, ELABORATED, DEEPLY_PROCESSED` | MW counts turns on topic from history_active + history_recent | DEPTH |
| 28 | `identity_domains` | string[] | N | `parent, child, spouse, professional, health_self, financial_self, social_self, academic_self, spiritual_self` | MW maps domains + topics + relationships to identity categories | SELF |
| 29 | `temporal_orientation` | string | Y | `PAST, ONGOING, FUTURE_COMMITMENT` | MW temporal analysis of resolved_epoch_ms vs now | FUTURE |
| 30 | `task_context` | string | N | Active task action (if extraction relates to task) | task_state active entry | WHY |
| 31 | `confidence` | float | Y | 0.0-1.0, <0.3 dropped | LLM self-score | META |
| 32 | `session_id` | string | Y | Session UUID | meta.identity.session_id | IDENTITY |
| 33 | `conversation_turn` | int | Y | Turn ordinal | meta.lifecycle.turn_count | IDENTITY |
| 34 | `language` | string | Y | ISO 639-1 | Default "en" | META |

**Token cost for new fields:** ~10-15 extra tokens per atom for the 6 new cognitive dimension fields. Negligible in 2000 token budget.

**All 34 fields are the canonical schema.** No v1/v2 distinction -- this is the only version.

---

## LAYER 3: st_hipp_events Final Schema (What K0 Stores)

### Current Columns (121 total across 5 migrations)

| Group | Migration | Columns | Count |
|---|---|---|---|
| Identity & Trace | 0022 | event_id, wal_pos, cognitive_trace_id, tenant_id, space_id, effective_space_id, topic, uow_id, schema_version | 9 |
| Integrity & Audit | 0022 | envelope_sha256, sig_alg, sig_kid, idem_key, ingested_at, clock_skew_ms | 6 |
| Policy & Visibility | 0022 | policy_decision, policy_band, policy_version, obligations_json, visible_to_json, visibility_scope, owner_id, co_owners_json, retention_policy_id, retention_bucket | 10 |
| Actor & Device | 0022 | actor_id, actor_role, device_id, device_kind, device_os, ingress_channel | 6 |
| Temporal | 0022 | event_time_utc, write_time_utc, write_lag_ms, local_date, local_time, day_of_week, is_weekend, time_of_day_bucket, circadian_slot, is_backdated, created_at | 11 |
| Spatial & Place | 0022 | location_name, location_type, geohash_6, geo_precision_external, geo_masking_reason | 5 |
| Social & Relationships | 0022 | participants_json, num_participants, has_partner_present, has_parent_present, is_solo_event, participant_roles_json, social_context, social_intimacy | 8 |
| Semantic & Activity | 0022 | text, text_normalized, char_count, token_count, language, activity_type, activity_category, is_meal, is_outing, ingress_source | 10 |
| Hippocampus (Pattern Sep.) | 0022 | simhash_hex, minhash32, novelty_score, near_duplicates_json, is_near_duplicate, episode_cluster_id, cluster_confidence, clustering_version | 8 |
| Embeddings & KG | 0022 | embedding_id, embedding_status, entities_json, kg_triples_json | 4 |
| Affect & Salience | 0022 | sentiment_score, sentiment_label, dominant_emotions_json, affect_valence, affect_arousal, affect_band, salience_score, salience_reasons_json, salience_band | 9 |
| Metadata & Versioning | 0022 | hippocampus_api_version, space_resolver_version, schema_uri, updated_at | 4 |
| P02 NER | 0046 | ner_entities_json, temporal_json, intent_category, ingress_category, ultrabert_version | 5 |
| P03 Reconciliation | 0052 | reconciliation_action, best_match_id, best_match_layer, similarity_score, confidence, reconciliation_reason, consolidated_at_ms | 7 |
| UltraBERT Full | 0053 | extracted_relations_json, safety_familyos_band, safety_familyos_subcategory, effective_safety_band, nli_label | 5 |
| UltraBERT Activity | 0060 | activity_type_ultrabert, activity_type_confidence, intent_ultrabert, intent_confidence | 4 |
| **TOTAL** | | | **111** |

### NEW Columns Needed (Migration 0065)

These columns store the 6 new cognitive dimensions from MW v2 that have NO existing home:

| # | Column | Type | Nullable | Constraint | Source | Why New |
|---|---|---|---|---|---|---|
| 1 | `participant_relationships_json` | TEXT | YES | Valid JSON | MW v2 body.participant_relationships | No existing column for typed relationships with confidence. `participant_roles_json` only has roles, not family graph types. |
| 2 | `affect_dominance` | FLOAT | YES | 0.0-1.0 | MW v2 body.affect.dominance | Current schema has valence + arousal but NOT dominance (3rd VAD dimension). |
| 3 | `entity_salience_json` | TEXT | YES | Valid JSON | MW v2 body.entity_salience | Per-entity salience map. Current `salience_score` is a single aggregate number. |
| 4 | `narrative_thread_id` | TEXT | YES | -- | MW v2 body.narrative.thread_id | No column for conversation thread tracking. |
| 5 | `narrative_arc_position` | TEXT | YES | `EXPOSITION, RISING_ACTION, CLIMAX, RESOLUTION` | MW v2 body.narrative.arc_position | No column for story arc position. |
| 6 | `narrative_is_goal_event` | BOOLEAN | YES | -- | MW v2 body.narrative.is_goal_event | No column for goal completion tracking. |
| 7 | `temporal_mentioned_time` | TEXT | YES | -- | MW v2 body.temporal.mentioned_time | Raw text like "yesterday evening". Current temporal columns are all resolved/computed. |
| 8 | `temporal_resolved_epoch_ms` | BIGINT | YES | -- | MW v2 body.temporal.resolved_epoch_ms | Resolved absolute time from K1 temporal engine. `event_time_utc` is write time, not mentioned time. |
| 9 | `intent_type` | TEXT | YES | `log_memory, query_memory, set_reminder, express_feeling, seek_advice, share_news, reflect, other` | MW v2 body.intent_type | `intent_category` (0046) is P02 UltraBERT. This is K1's primary classification. |
| 10 | `goal_context` | TEXT | YES | -- | MW v2 body.goal_context | No column for active thread goal. |
| 11 | `source_type` | TEXT | YES | `user_stated, user_implied, device_observed, system_inferred` | MW v2 body.source_type | No column for memory provenance (source monitoring). |
| 12 | `novelty` | TEXT | YES | `ROUTINE, EXPECTED, NOVEL, SURPRISING` | MW v2 body.novelty | Current `novelty_score` is P02 DG float. This is MW cognitive classification (categorical). |
| 13 | `elaboration_depth` | TEXT | YES | `MENTION, DISCUSSED, ELABORATED, DEEPLY_PROCESSED` | MW v2 body.elaboration_depth | No column. P03 decay model needs this. |
| 14 | `identity_domains_json` | TEXT | YES | Valid JSON array | MW v2 body.identity_domains | No column for self-reference domains. |
| 15 | `temporal_orientation` | TEXT | YES | `PAST, ONGOING, FUTURE_COMMITMENT` | MW v2 body.temporal_orientation | No column. Proactive Agent and Workflow Scheduler need this. |
| 16 | `k1_signal_version` | TEXT | YES | -- | `"2.0"` from schema_version | Tracks MW version for observability and debugging. Always "2.0" pre-production. |

**Total after migration 0065: 111 + 16 = 127 columns**

### Column Mapping: MW v2 Body Field -> st_hipp_events Column

| MW v2 Body Field | st_hipp_events Column | Action in P02 |
|---|---|---|
| `text` | `text` | PASS-THROUGH |
| `participants` | `participants_json` | M02 validates + writes |
| `participant_relationships` | `participant_relationships_json` **NEW** | M07 trusts + writes to st_kg_edges |
| `location_name` | `location_name` | M40 geo enrichment if coords available |
| `location_type` | `location_type` | PASS-THROUGH |
| `activity_type` | `activity_type` + `activity_type_ultrabert` (P02 runs UltraBERT too) | MW value -> activity_type, UltraBERT -> activity_type_ultrabert |
| `topics` | stored in `entities_json` (topics sub-key) | M02 merges |
| `categories` | `activity_category` | PASS-THROUGH |
| `sentiment_label` | `sentiment_label` | M04 validates (UltraBERT safety-only) |
| `emotion_tags` | `dominant_emotions_json` | M04 validates, union merge |
| `affect.valence` | `affect_valence` | M04 trusts MW (UltraBERT safety-only) |
| `affect.arousal` | `affect_arousal` | M04 trusts MW |
| `affect.dominance` | `affect_dominance` **NEW** | PASS-THROUGH |
| `social_context` | `social_context` | M07 trusts MW (was BROKEN, now fixed) |
| `social_intimacy` | `social_intimacy` | M07 trusts MW |
| `entity_salience` | `entity_salience_json` **NEW** | M06 uses for enriched salience formula |
| `narrative.thread_id` | `narrative_thread_id` **NEW** | PASS-THROUGH |
| `narrative.arc_position` | `narrative_arc_position` **NEW** | PASS-THROUGH |
| `narrative.is_goal_event` | `narrative_is_goal_event` **NEW** | PASS-THROUGH |
| `temporal.mentioned_time` | `temporal_mentioned_time` **NEW** | PASS-THROUGH |
| `temporal.resolved_epoch_ms` | `temporal_resolved_epoch_ms` **NEW** | M08 uses for backdating |
| `temporal.is_backdated` | `is_backdated` (exists) | M08 validates |
| `intent_type` | `intent_type` **NEW** | PASS-THROUGH (K1 signal, not P02 UltraBERT) |
| `goal_context` | `goal_context` **NEW** | PASS-THROUGH |
| `source_type` | `source_type` **NEW** | PASS-THROUGH |
| `novelty` | `novelty` **NEW** (categorical) | PASS-THROUGH (distinct from `novelty_score` float) |
| `elaboration_depth` | `elaboration_depth` **NEW** | PASS-THROUGH |
| `identity_domains` | `identity_domains_json` **NEW** | PASS-THROUGH |
| `temporal_orientation` | `temporal_orientation` **NEW** | PASS-THROUGH |
| `confidence` | `confidence` (exists in 0052) | PASS-THROUGH |
| `session_id` | derived to `cognitive_trace_id` + `space_id` | Existing mapping |
| `conversation_turn` | stored in envelope headers | Existing mapping |
| `language` | `language` (exists) | PASS-THROUGH |
| -- | `k1_signal_version` **NEW** | Set from body.schema_version |

### P02 Module Behavior Changes (v2 Mode)

| Module | Behavior (MW v2 only -- no legacy mode) |
|---|---|
| **M01** pattern_separate | Compute SimHash + MinHash fingerprints from text (dedup always fresh) |
| **M02** semantic_project | Single UltraBERT pass: NER + 768-dim embedding. Cross-validate MW participants against NER. KG triples from MW relationships. |
| **M04** affect.analyze | SAFETY HEADS ONLY. Trust MW affect (valence/arousal/dominance). UltraBERT validates safety_familyos_band only. |
| **M07** social.family_graph | TRUST MW participant_relationships directly. Write to st_kg_edges. Derive has_partner/has_parent from relationship types. No DB lookup fallback needed. |
| **M06** salience.score | Use MW social_context + MW affect + MW entity_salience for correct salience formula. |
| **M08** temporal_profile | Use MW temporal.resolved_epoch_ms for backdating. Use MW temporal_orientation for FUTURE_COMMITMENT flagging. |
| **M60** hipp_events_row | Assemble 127 columns. Write all 16 new columns from MW body. |
| **M70** atomic_writer | 3-table atomic write (st_hipp_events + st_vec + st_pipeline_processed). |

### No Backward Compatibility Needed -- Pre-Production

We are NOT in production. There is no legacy data to preserve. All existing st_hipp_events rows (1348), st_observations, truth tables (st_epi, st_sem, st_kg_edges, st_social, st_prospective, st_anchors) can be wiped and rebuilt end-to-end with every iteration.

This means:

- **No v1/v2 dual-mode in P02.** P02 implements MW v2 behavior ONLY. No `schema_version` detection, no fallback to UltraBERT recompute. If the envelope has MW v2 fields, use them. Period.
- **No nullable new columns for compat.** The 16 new st_hipp_events columns can be NOT NULL with sensible defaults where appropriate. No need to handle old rows with NULLs.
- **No gradual migration.** Drop tables, re-run migrations, re-ingest from scratch. Iterate until the pipeline produces correct output.
- **No cold-start transition handling.** Every run starts clean. st_observations will contain ONLY v2 data. R5 algorithms never see mixed v1/v2 evidence.
- **Delete and rebuild freely.** If a schema change breaks things, truncate and re-process. This is the advantage of pre-production: zero data preservation cost.

The existing 1348 rows with broken social_context, flat salience, and false family flags are test data. They will be replaced by correct MW v2 data on the next ingestion run.

---

That's the complete three-layer contract:

**Layer 1** — MW reads 13 of 15 SessionState sections (skips telemetry + artifacts_warm). The 6 new cognitive dimensions are derived by cross-referencing sections: `novelty` from beliefs vs scoreboard, `elaboration_depth` from history turn counts, `source_type` from history user messages, `identity_domains` from persona + domains, `temporal_orientation` from MentionedTime vs now, `goal_context` from narrative_active.

**Layer 2** — Envelope body v2 has 34 fields. All fields present on every atom. No versioning needed.

**Layer 3** — st_hipp_events gets 16 new columns in migration 0065 (111 -> 127 total). P02 always trusts MW signals, UltraBERT validates safety only. This fixes the three broken signals (social_context, salience, family flags).

---

## How MW v2 + P02 v2 Improvements Affect P03 Stage 5 (R5 Dream Explorer)

### The Signal Chain: MW v2 -> P02 -> st_hipp_events -> R7 st_observations -> R5

The R5 Dream Explorer's 14 algorithms do NOT read st_hipp_events directly. They read **st_observations** -- the append-only observation log created by R7 truth writers during P03 R1-R4 consolidation. Every time R7 writes a FIRST_SEEN or REINFORCEMENT row to a truth table (st_epi, st_sem, st_kg_edges, st_social, etc.), it simultaneously records an observation row in st_observations that snapshots key context columns from the original st_hipp_events row.

The chain is:

```
MW v2 (34-field atoms)
  -> P02 v2 (trust MW, validate safety)
    -> st_hipp_events (127 columns, 16 new)
      -> P03 R1-R4 (reconcile, cluster, enrich, extract)
        -> R7 TruthWriter writes to truth tables
          -> R7 ObservationRecorder snapshots context into st_observations (32 columns)
            -> R5 algorithms read st_observations via ObservationEvidenceLoader
```

The critical implication: **every new MW v2 signal that flows into st_hipp_events and is captured in the st_observations snapshot becomes available to ALL 14 R5 algorithms.** The three broken signals being fixed (social_context, salience, family flags) directly improve the observation evidence pool. The 12 new cognitive dimension fields create entirely new evidence dimensions for algorithms that were previously data-starved.

### st_observations Context Columns: What Changes

The `ObservationRecorder.record_for_merge()` snapshots these context columns from the source st_hipp_events row when creating an observation:

| st_observations Column | Current State (v1) | After MW v2 | Impact |
|---|---|---|---|
| `social_context` | BROKEN: only "friends" (68%) or "solo" (32%) | CORRECT: "nuclear_family", "extended_family", "friends", "solo", "colleagues", "community" | ALL algorithms using social distribution get real data |
| `salience_score` | FLAT: 60% at 0.41, 100% MED band | DISCRIMINATING: 0.25-0.95 range, proper HIGH/MED/LOW distribution | EST, SPG, EPC threshold-based logic actually works |
| `sentiment_score` | From UltraBERT on 8-token text (context-poor) | From MW per-extraction affect (full conversation context) | SRE sentiment aggregation uses accurate per-atom values |
| `affect_valence` | UltraBERT recomputed (context-poor) | MW dimensional valence from affective_now (context-rich) | SRE emotional diversity computed from real affect, not UltraBERT guesses |
| `dominant_emotion` | UltraBERT on short text | MW 44-class emotion from session context | SRE diversity + ASU emotion distribution + SPR emotional_diversity all improve |
| `location_type` | From P02 M40 geo resolution | From MW + beliefs_active MentionedLocation.location_type | ASU location distribution anchors derive from correct types |

### Per-Algorithm Impact Analysis: How Each R5 Algorithm Benefits

#### Phase 1 Algorithms (Parallel, Read Observation Evidence)

**EST -- Episodic Strength Tracker**

| Aspect | Before MW v2 | After MW v2 |
|---|---|---|
| Primary signal (observation reinforcement count) | Unaffected -- counts are counts | Same |
| Tier 2 heuristic matching (location + activity + participants) | `activity_type` from UltraBERT (good), but `dominant_location` often null or generic | MW provides `location_type` (restaurant, park, home, etc.) and `activity_type` from domain context. Heuristic matching accuracy improves for new episodes without observation history |
| Emotional diversity bonus (McGaugh 2004) | `stats.distinct_emotions` counted from UltraBERT emotions on 8-token text -- low diversity because short text produces limited emotion detection | `distinct_emotions` now counted from MW's per-extraction 44-class emotions with full conversation context. A dinner discussion where user expressed joy, gratitude, and nostalgia actually registers 3 emotions instead of just "positive" |
| `aggregated_salience` base value for boost calculation | All episodes start at ~0.41 (flat). EST boost of 0.03*log2(count) adds to 0.41. Even 10 reinforcements: 0.41 + 0.03*3.46 = 0.51. Still MED. | Episodes start at 0.25-0.95 range. Family dinner at 0.78 + 0.03*3.46 = 0.88 (HIGH). Routine task at 0.30 stays low. EST amplifies real importance differences instead of adding noise to a flat baseline |

**NET**: EST goes from "slight nudges on a flat landscape" to "meaningful amplification of correctly-graded episodes." The difference between a family birthday reinforced 10x (0.78 -> 0.88 HIGH) and a solo lunch reinforced 2x (0.35 -> 0.38 LOW) becomes visible.

---

**ASU -- Anchor Seeding & Update**

ASU is the algorithm MOST affected by MW v2 because it derives Bayesian anchors entirely from st_observations distribution aggregates.

| Distribution | Before MW v2 | After MW v2 |
|---|---|---|
| `social_distribution` (social_context counts) | Only "friends" and "solo" exist. `family_oriented` anchor spec looks for "family" support value -- finds ZERO. `is_social` anchor counts "friends" but can't distinguish family-social from friend-social. | Full distribution: nuclear_family=45%, extended_family=8%, friends=20%, solo=22%, colleagues=5%. The `family_oriented` anchor: Beta(1 + 71, 1 + 29) = mean 0.71 -- MEANINGFUL. The `is_social` anchor includes family as support evidence. |
| `emotion_distribution` (dominant_emotion counts) | UltraBERT on 8-token text produces limited diversity. "positive" overwhelms. `generally_positive` anchor has lopsided evidence. `stress_reactive` anchor barely populated. | MW 44-class emotions with per-extraction granularity. Same user turn produces "joy" for birthday atom and "concern" for health atom. Emotion distribution reflects true emotional diversity. `stress_reactive` gets real "anxiety", "frustration" entries. |
| `location_distribution` (location_type counts) | P02 geo resolution provides some data but misses implied locations ("had dinner" = restaurant, "at the office" = office). | MW extracts `location_type` from beliefs_active MentionedLocation which K1's LLM resolved. "We went to Olive Garden" -> location_type=restaurant via K1 understanding. Distribution is richer and more accurate. |
| `circadian_distribution` | Already good (from timestamp) | No change -- timestamps are accurate regardless of MW version |
| `channel_distribution` | Already good (from device metadata) | No change |

**KEY IMPACT**: The `family_oriented` anchor (the single most important personalization signal for a FamilyOS app) was **impossible to derive** before MW v2 because `social_context` never contained "family". After MW v2, ASU can seed `family_oriented` with real evidence on the very first run. This anchor drives personalization: K1 uses it to prioritize family-relevant responses.

**Success criteria #1 ("10+ active anchors")**: Previously unachievable for social/emotional anchors due to broken distributions. Now achievable because distributions contain real signal.

---

**SRE -- Social Relationship Enrichment**

SRE directly benefits from three MW v2 fixes:

| Input | Before MW v2 | After MW v2 |
|---|---|---|
| Per-observation `sentiment_score` | UltraBERT on "Had dinner with Mom" -> sentiment ~0.55 (generic mild positive) | MW per-extraction affect: dinner with Mom -> valence 0.82 (context-aware, knows Mom is parent, knows celebration context) |
| Per-observation `affect_valence` | Same issue -- UltraBERT context-poor | MW dimensional valence from affective_now. Per-atom: birthday celebration = 0.85, worried about Mom's cough = -0.30. Same person (Mom), wildly different valences per atom. |
| Per-observation `dominant_emotion` | Limited to 1-2 emotions from short text | MW 44-class with session context: "joy", "contentment", "love" for birthday, "concern", "sadness" for health worry |
| `social_context` on observations mentioning person | Always "friends" for family members | Correct: "nuclear_family" when Mom + daughter, "extended_family" when grandparents |

**CONCRETE FIX**: The Panda at 0.00 sentiment problem. SRE aggregates `sentiment_score` from entity_observations. With v1, UltraBERT's context-poor scores for Panda-related events average to ~0.50 (generic positive). But the actual observation records have `sentiment_score` populated by P02 M04 which runs UltraBERT on 8-token text, missing the emotional richness. With MW v2, the observations for Panda carry MW's per-extraction valence: bedtime story = 0.75, family game = 0.80, sick child = -0.20. SRE computes: `avg_sentiment = mean([0.75, 0.80, -0.20, ...]) = 0.62`. Real signal, not 0.00.

**Emotional diversity**: SRE computes Shannon entropy of `dominant_emotion` per person. With v1, most observations for Panda have "positive" (UltraBERT lacks nuance). Diversity = low. With MW v2: "joy", "love", "concern", "gratitude", "pride" -- real emotional range. Diversity = high. This feeds into `health_score` which measures relationship health as `frequency * sentiment * recency`. Higher diversity = richer relationship model.

**Sentiment trajectory**: SRE splits observations into recent vs older halves. With flat UltraBERT scores, trajectory is always STABLE. With MW v2 per-extraction affect, if recent Panda observations trend happier (new bedtime routine working), trajectory = IMPROVING. This is the kind of signal K1 needs: "Your relationship with Panda has been more positive lately."

---

**SPR -- Semantic Pattern Reinforcement**

| Aspect | Before MW v2 | After MW v2 |
|---|---|---|
| Primary signal (reinforcement count) | Unaffected -- counts are counts | Same |
| Specificity scoring (causal/action language) | Unaffected -- analyzes pattern text | Same |
| Observation recency factor | Unaffected -- uses timestamps | Same |
| Indirect benefit: pattern CREATION quality | st_sem patterns created by R2/R4 from st_hipp_events text. With v1, patterns like "annoyance emotional pattern" created from flat UltraBERT labels. | With MW v2, richer st_hipp_events (per-extraction affect, social_context, narrative arc) means R2 creates more specific patterns: "family dinner celebration pattern" instead of generic "positive social event." SPR then reinforces these more specific patterns to higher confidence, matching the specificity scoring bonus. |

**NET**: SPR itself doesn't change behavior. But the QUALITY of patterns it operates on improves because R2 creates better patterns from richer st_hipp_events data. Specificity scoring rewards detailed patterns -- and MW v2 produces the kind of detail that creates them.

**Success criteria #5 ("confidence range 0.30-0.95")**: SPR differentiates by reinforcement count + specificity. With v1, both dimensions are weak (low reinforcement counts because flat salience means R7 writes generic observations; low specificity because patterns are generic). With MW v2, both improve.

---

**SPC-UQ -- Prospective Memory Cleanup**

| Aspect | Before MW v2 | After MW v2 |
|---|---|---|
| Counterfactual purge | Unaffected -- unconditional archive | Same |
| Observation-based completion detection | Works on reinforcement count per st_prospective record | Same mechanism, but NEW: `intent_type` field in st_hipp_events. When MW v2 tags an atom with `intent_type: "set_reminder"`, P03 R1-R4 can create a st_prospective record with provenance. SPC-UQ's subsequent reinforcement detection traces back to a real user intent, not a heuristic keyword match. |
| New intention detection from current events | `intent_ultrabert` field available but basic. `intent_type` from MW v2 is richer (K1 sees full conversation, understands "I should probably..." as set_reminder where UltraBERT sees neutral text). | More accurate prospective memory creation. Fewer false positives (UltraBERT misclassifies reflections as intentions) and fewer false negatives (subtle "I should..." captured by MW LLM) |
| `temporal_orientation` on source events | Not available | MW v2 provides `temporal_orientation: "FUTURE_COMMITMENT"` for forward-looking atoms. SPC-UQ can directly identify future-oriented memories as prospective candidates without keyword matching. |

**NET**: SPC-UQ gets better INPUT (more accurately tagged prospective items from R1-R4 that used MW v2's intent_type and temporal_orientation), and better EVIDENCE (observation trail with correct social/affect context).

---

#### Phase 2 Algorithms (Sequential, Depend on Phase 1)

**EWR -- Edge Weight Refinement**

| Aspect | Before MW v2 | After MW v2 |
|---|---|---|
| Multi-enricher analysis | Unaffected -- analyzes R4 enricher metadata | Same |
| Episode co-occurrence reinforcement | Depends on episode salience: `boost = config.cooccurrence_boost * episode.aggregated_salience`. With v1, all episodes at ~0.41. Boost = 0.02 * 0.41 = 0.008. Minimal. | With MW v2, HIGH salience family episodes at 0.78. Boost = 0.02 * 0.78 = 0.016. Double the signal. Family entity edges get proportionally stronger boosts. |
| Sentiment multiplier for emotional episodes | `if abs(episode.dominant_sentiment) > 0.7: boost *= 1.5`. With v1 UltraBERT context-poor sentiment, few episodes exceed 0.7. | MW v2 per-extraction affect: birthday celebration at valence 0.85 > 0.7 threshold. Sentiment multiplier triggers. Family birthday edges get 1.5x boost. |
| Noise demotion of WeightNormalization-only edges | Unaffected -- analyzes enricher metadata | Same |
| NEW: `participant_relationships` flowing to st_kg_edges via M07 | st_kg_edges was essentially empty for family relationships (broken M07) | M07 now writes MW's `participant_relationships` to st_kg_edges: Mom->PARENT_OF, Panda->SPOUSE_OF. EWR's enricher analysis sees these edges have `relationship_type` enricher source (from MW). Edges with MW relationship source + R4 enricher = multi-enricher = boost. |

**CRITICAL FIX**: The 1330 near-zero weight edges problem. Many of these are for family entities that SHOULD be strong edges but only have WeightNormalization as their enricher source (because the family graph was empty). With MW v2, M07 seeds real family relationships into st_kg_edges. On the next P03 cycle, EWR sees these edges now have 2 enricher sources (MW relationship + WeightNormalization) and boosts them. Over cycles, family edges climb to meaningful weights while genuinely noise edges continue to decay.

**Success criteria #3 ("average weight > 0.10") and #4 ("WeightNormalization-only demoted")**: MW v2 accelerates both because it creates multi-enricher edges for family members that EWR can boost, while noise edges still only have single-enricher sources and continue to be demoted.

---

**BGT-SM -- Bisociative Graph Traversal**

BGT-SM runs random-walk-with-restart over the KG. Edge weights determine walk probabilities. With EWR producing better weights (family edges strong, noise edges weak), BGT-SM's random walks naturally gravitate toward meaningful connections.

| Before MW v2 | After MW v2 |
|---|---|
| 82% of edges near-zero. Random walk is essentially random -- noise edges as likely to be traversed as meaningful ones. | Family edges boosted by EWR, noise edges demoted. Random walk concentrates on meaningful subgraph. |
| Insights discovered are random/low-quality because graph is homogeneous noise | Insights connect actual important entities because graph topology reflects real relationship strength |

---

#### Phase 4 Algorithms (Parallel, Graph-Level)

**SPG -- Salience Propagation through Graph**

SPG propagates salience from high-salience episodes to connected entities and edges. This is where the MW v2 salience fix has its most dramatic amplification effect.

| Before MW v2 | After MW v2 |
|---|---|
| All episodes at ~0.41. Phase 1 EST boosts a few to ~0.50. SPG's `min_episode_salience = 0.50` threshold: barely any episodes qualify for propagation. | EST-boosted family episodes at 0.78 -> 0.88. Many episodes above 0.50 threshold. SPG propagates to family entities. |
| Panda entity: no high-salience episodes -> `propagated_salience` = ~0.0 | Panda entity: appears in 25 episodes averaging 0.70 salience -> `propagated_salience` = 0.87 |
| Entity-to-edge propagation: no entities have salience -> no edge gets salience | Mom->User edge: both endpoints have propagated salience -> `edge_propagated = sqrt(0.85 * 0.90) = 0.87` |

**Success criteria #15 ("entity salience std_dev > 0.15")**: With v1, all entities would have ~0.0 propagated salience (nothing above threshold). With MW v2, key family entities get 0.70-0.90 while minor mentioned entities stay at 0.10-0.30. Clear variance.

---

**NTD -- Narrative Thread Detection**

NTD finds causal/temporal chains across episodes that form coherent narratives. MW v2 introduces `narrative_thread_id` and `narrative_arc_position` which directly feed this algorithm.

| Before MW v2 | After MW v2 |
|---|---|
| NTD must discover threads from scratch: entity overlap + temporal ordering + causal language heuristics in episode text. Expensive BFS, many false positives. | MW v2 atoms arrive with `narrative.thread_id` (system UUID from narrative_active). P02 stores this in st_hipp_events. R2 clustering can GROUP by thread_id. R4 creates temporal edges within same thread. By the time NTD runs, episodes are already pre-labeled with thread membership. NTD validates and enriches rather than discovers from scratch. |
| Emotional arc detection: looks at episode-level sentiment trend. With v1 flat sentiment, arc is always STABLE. | MW v2 per-extraction affect: episode sentiments actually vary. Birthday thread: EXPOSITION (0.50) -> RISING_ACTION (0.65) -> CLIMAX (0.85) -> RESOLUTION (0.75). NTD detects NEGATIVE_TO_POSITIVE arc. Panda's sleep issue thread: ESCALATION (negative trend). |
| `causal_strength` scoring: checks for causal/temporal R4 edges between episodes. R4 edges are mostly noise. | EWR Phase 2 has already cleaned edges. Temporal/causal edges between episodes within same thread_id are real. `causal_strength` scores higher. |
| `thread_confidence`: chain_length *causal_strength* entity_overlap. With noise edges and flat sentiment, confidence is low. | All three factors improve: chains pre-labeled by thread_id (longer), edges cleaned by EWR (stronger causal), shared entities confirmed by MW participant_relationships (more accurate). |

**Success criteria #16 ("at least 1 NARRATIVE_THREAD per 30 days")**: With v1, NTD struggles to find threads because episodes lack narrative metadata and sentiment is flat. With MW v2's pre-labeled thread_ids and real emotional arcs, NTD can reliably detect and validate threads.

**NEW CAPABILITY**: `narrative.is_goal_event` from MW v2. When an atom is tagged as a goal event (thread's goal is met), NTD can identify RESOLUTION points in the narrative. "Panda sleeping through the night" tagged as `is_goal_event: true` for the sleep-issue thread creates a natural narrative boundary that NTD can use to close threads.

---

**CTD -- Contradiction Detection**

| Check Type | Before MW v2 | After MW v2 |
|---|---|---|
| FACT_CONFLICT (same entity, same attribute, different values) | Unaffected -- compares st_kg_dom attributes | Same, but: MW v2's `participant_relationships` seeded into st_kg_edges by M07 provide typed relationship facts. If MW says Mom=PARENT_OF and an old record says Mom=FRIEND_OF, CTD catches it. Before MW v2, no relationship facts existed to conflict. |
| SENTIMENT_MISMATCH (st_social vs observation trail) | st_social sentiment = 0.00. Observation sentiment from UltraBERT on short text = ~0.50. Delta = 0.50 >= 0.30 threshold. CTD detects mismatch. But the "correct" value is the observation trail -- which itself is inaccurate (UltraBERT context-poor). Resolution: FORCE_RECALC to ~0.50 (still wrong, just less wrong). | st_social sentiment (after SRE fix) = 0.62 (from MW per-extraction affect). Observation trail = accurate per-extraction sentiment. Delta is small or zero. CTD finds FEWER false-positive mismatches. When it DOES find a mismatch, the observation trail is trustworthy and FORCE_RECALC produces the correct value. |
| TEMPORAL_IMPOSSIBLE (events at different locations overlapping) | Relies on episode temporal bounds and location_name. Location data sometimes missing. | MW v2's `temporal.resolved_epoch_ms` provides more accurate event times (K1 resolves "yesterday evening" to correct epoch). `location_type` from MW is more reliable than P02 geo-only resolution. Temporal impossibility detection is more accurate: fewer missed conflicts and fewer false positives. |

**NET**: CTD becomes more precise -- fewer false positives (because observation data is now accurate) and catches new contradiction types (relationship type conflicts via MW participant_relationships).

---

**CLV -- Cross-Layer Coherence Verification**

| Check | Before MW v2 | After MW v2 |
|---|---|---|
| ORPHAN_ENTITY (0 edges) | Many person entities have 0 edges because M07 couldn't create family edges from empty st_kg_edges. | M07 writes MW's `participant_relationships` to st_kg_edges. Family entities now have edges. Fewer orphan entity detections. CLV can focus on genuinely orphaned entities instead of flagging the entire family. |
| SOCIAL_WITHOUT_ENTITY and ENTITY_WITHOUT_SOCIAL | Person entities in st_kg_dom might not have st_social entries and vice versa. | MW v2's `participant_relationships` with typed relationships (PARENT_OF, SPOUSE_OF) give CLV richer context for SEED recommendations. When CLV finds a person entity without a social entry, it can recommend seeding with relationship type from st_kg_edges (which now has MW-sourced types). |
| UNGROUNDED_SOCIAL (0 observations) | Social entries created by R4 without observation trail. | Observations now carry correct `social_context`. Social entries seeded from MW relationships have observation backing from the start. Fewer ungrounded social entries. |

**Success criteria #12 ("0 orphan edges, 0 person entities without st_social")**: MW v2 directly reduces orphan entities by populating family edges. CLV's job shifts from "flag everything as broken" to "maintain integrity of a well-populated graph."

---

#### Phase 5 Algorithms (Sequential, Depend on Phase 1-4)

**MTP -- Memory Tier Promotion**

MTP assigns memory tiers (TRANSIENT -> ACTIVE -> STABLE -> CORE) based on reinforcement count and record age. It reads observation evidence, not st_hipp_events columns directly. However, MW v2 improves MTP indirectly:

| Before MW v2 | After MW v2 |
|---|---|
| Reinforcement counts are influenced by salience. R7 writes REINFORCEMENT observations for records being updated by R5 algorithms. With flat salience, R5 algorithms produce few updates -> few REINFORCEMENT observations -> slow tier progression. | Correct salience means R5 algorithms (EST, EWR, SRE, SPR) produce MORE updates (more records cross their activation thresholds). More R7 REINFORCEMENT writes. Faster tier progression for genuinely important memories. |
| "My daughter's name is Panda" might have the same reinforcement_count as "had pizza on Tuesday" because both had flat salience and neither got preferential R5 treatment. | "Panda" entity facts get reinforced by multiple algorithms (EST boosts Panda episodes, SRE updates Panda sentiment, EWR strengthens Panda edges, SPG propagates Panda salience). Each R5 update generates a REINFORCEMENT observation. Panda facts accumulate reinforcements faster -> promote to ACTIVE (3+) -> STABLE (10+) -> CORE (20+) sooner. Pizza-on-Tuesday gets minimal R5 attention -> stays TRANSIENT -> R3 decays it naturally. |

**Success criteria #11 ("CORE tier records exist")**: MW v2's correct salience creates a virtuous cycle: important memories get more R5 attention -> more reinforcement observations -> faster tier promotion -> R3 decay protection. The fundamental memories of a family ("daughter's name", "partner's birthday", "Mom's health condition") reach CORE status while ephemeral details decay. This is exactly how biological memory works.

---

**EPC -- Episode Compression**

| Aspect | Before MW v2 | After MW v2 |
|---|---|---|
| `max_salience_for_compression = 0.60` filter | ALL episodes at ~0.41 < 0.60. EVERY episode is compressible. EPC would try to compress everything including unique important events. | High-salience family events at 0.70-0.95 are ABOVE threshold. Only routine/low-importance episodes get compressed. Birthday celebrations, health scares, milestones stay as individual episodes. "Had dinner" at 0.35 gets compressed into a composite. |
| Entity overlap grouping (`min_shared_entities = 2`) | Participant data is flat (no relationship types). Grouping is by name only. | MW v2's `participant_relationships` in st_hipp_events mean entities have typed connections. "Family dinner" episodes reliably group because Mom + Emma + User share `nuclear_family` social_context. |
| `avg_sentiment` on composites | UltraBERT context-poor sentiment -> composites carry inaccurate sentiment averages. | MW per-extraction sentiment -> composites carry accurate emotional characterization. "Regular family dinners: avg_sentiment 0.78" reflects real family joy. |
| `frequency_per_month` calculation | Unaffected -- counts episodes over time | Same |

**Success criteria #14 ("composites carry frequency_per_month metadata")**: EPC works correctly regardless of MW version. But MW v2's correct salience prevents EPC from accidentally compressing important unique events (which would destroy important memories).

---

### How Better Memory Formation Emerges

The 14 R5 algorithms form an interconnected system. MW v2's improvements don't just help individual algorithms -- they create emergent quality improvements through the self-reinforcing cycle:

**Cycle 1 (First run after MW v2 deployment):**

1. st_hipp_events rows arrive with correct social_context, per-extraction affect, entity_salience, narrative metadata
2. R1-R4 creates better truth table entries (correct social in st_social, typed relationships in st_kg_edges, varied salience in st_epi)
3. R7 writes FIRST_SEEN observations with rich context
4. R5 reads these observations and produces:
   - EST: Real salience differentiation (family HIGH, routine LOW)
   - ASU: Family_oriented anchor seeded (finally possible)
   - SRE: Panda sentiment jumps from 0.00 to ~0.62
   - EWR: Family edges get multi-enricher boost
   - SPR: Patterns begin differentiating by observation count

**Cycle 2-5 (Feedback loop activates):**

1. R5 updates from Cycle 1 get recorded as REINFORCEMENT observations by R7
2. Next R5 sees more evidence -> more aggressive updates -> more observations -> cycle accelerates
3. EST boosted episodes trigger SPG propagation -> entity salience emerges
4. EWR cleaned edges improve BGT-SM insight quality
5. MTP begins promoting frequently-reinforced records (Panda facts -> ACTIVE tier)
6. NTD detects pre-labeled narrative threads from MW v2's thread_id metadata
7. CTD catches sentiment mismatches and resolves from observation evidence -> FORCE_RECALC

**Cycle 10+ (Steady state):**

1. CORE tier memories established (family names, key relationships, health conditions)
2. Composite episodes created for recurring routines (weekly family dinners, daily school runs)
3. Narrative threads track ongoing family stories (Panda's development, Mom's health journey)
4. Anchor system has 10+ active Bayesian priors (family_oriented: 0.85, is_morning_person: 0.72, etc.)
5. st_social has accurate sentiment for all family members
6. st_kg_edges: family edges at 0.40-0.80 weight, noise edges at <0.01
7. st_sem: LESSON patterns at 0.70-0.95, generic EMOTIONAL_TREND at 0.30-0.50

**The bottom line for recall quality**: When K1 asks "tell me about Panda," the memory system returns:

- CORE-tier facts that never decay (name, relationship, birthday)
- HIGH-salience episodes properly ordered by emotional intensity
- Composite episodes summarizing routines ("bedtime stories ~4x/week, positive mood")
- Narrative threads ("Panda's sleep improvement journey: 5 episodes, NEGATIVE_TO_POSITIVE arc")
- Accurate social sentiment (0.72, trajectory: IMPROVING)
- Entity salience from graph propagation (0.87 -- a central family figure)

Instead of what it returns today: 339 equally-weighted episodes, 39 relationships with 0.00 sentiment, 1330 near-zero edges, 545 patterns all at 0.80, 0 anchors, 0 narrative threads.

### Success Criteria Achievability: v1 vs v2

| # | Criterion | Achievable With v1 Signals? | Achievable With MW v2? | Why |
|---|---|---|---|---|
| 1 | 10+ active anchors with meaningful distributions | NO -- social_context broken, emotion distribution limited | YES -- all 6 distribution types have real data | ASU's `family_oriented` anchor depends entirely on correct social_context in observations |
| 2 | No relationships with 0.00 sentiment where obs > 5 | PARTIAL -- SRE fixes aggregation, but observation sentiment values are context-poor | YES -- per-extraction affect gives SRE accurate sentiment per observation | SRE's accuracy is bounded by observation quality |
| 3 | Average edge weight > 0.10 | SLOW -- EWR works but co-occurrence boost is minimal (flat salience dampens) | FASTER -- co-occurrence boost amplified by correct salience, MW relationship edges add multi-enricher source | EWR boost formula: `cooccurrence_boost * episode.aggregated_salience`. Higher salience = higher boost |
| 5 | Confidence range 0.30-0.95 | PARTIAL -- SPR differentiates by observation count, but pattern quality is low | YES -- better patterns from richer st_hipp_events + observation-based reinforcement | Specificity scoring rewards detailed patterns that MW v2 creates |
| 7 | Episode salience variance | NO -- EST boosts from 0.41 flat baseline, variance remains minimal | YES -- EST amplifies a baseline with real variance (0.25-0.95) | Variance in output requires variance in input |
| 11 | CORE tier records exist | SLOW -- flat salience = slow reinforcement accumulation | YES -- correct salience creates preferential reinforcement for important memories | MTP's tier thresholds (3/10/20 reinforcements) reached faster when R5 algorithms are more active |
| 13 | 0 unresolved SENTIMENT_MISMATCH where obs > 5 | MISLEADING -- CTD detects mismatches but "correct" value from observations is itself inaccurate | YES -- observation trail has accurate MW-sourced sentiment. CTD resolutions are trustworthy | The quality of contradiction resolution depends on observation data quality |
| 15 | Entity salience std_dev > 0.15 | NO -- SPG threshold (0.50) almost never triggered because episodes are at ~0.41 | YES -- EST-boosted episodes at 0.70+ trigger SPG propagation to entities | SPG is a multiplier on EST's output. No EST differentiation = no SPG output |
| 16 | 1+ NARRATIVE_THREAD per 30 days | UNLIKELY -- NTD relies on entity overlap + temporal ordering with no pre-labeling | YES -- MW v2 thread_id pre-labels episode threads. NTD validates rather than discovers | Qualitative shift from "discover from noise" to "validate from signal" |

### Recommendations for the R5 Proposal

Given the MW v2 improvements, the R5 proposal should:

1. **Add `narrative_thread_id` to ObservationEvidenceLoader**: The current loader queries 3 tables but doesn't group by thread_id. NTD would benefit from observation evidence pre-grouped by narrative thread. Add a 4th SQL query: `GROUP BY narrative_thread_id WHERE narrative_thread_id IS NOT NULL`.

2. **Add `temporal_orientation` to ASU distribution specs**: MW v2 provides `temporal_orientation` (PAST/ONGOING/FUTURE_COMMITMENT). ASU should have a `future_oriented` anchor spec using FUTURE_COMMITMENT as support evidence. This would enable personalization like "you tend to plan ahead" vs "you reflect on the past."

3. **Add `identity_domains` to SRE context**: MW v2's `identity_domains` (parent, professional, health_self, etc.) on observations would let SRE compute per-identity-domain relationship quality. "Your relationship with Panda is strongest in the parent domain (sentiment 0.85) but weaker in the social domain (sentiment 0.55)."

4. **Add `elaboration_depth` to MTP tier thresholds**: MW v2's `elaboration_depth` (MENTION -> DISCUSSED -> ELABORATED -> DEEPLY_PROCESSED) could modify MTP thresholds. A DEEPLY_PROCESSED memory reaching ACTIVE tier with only 2 reinforcements (instead of 3) because the user invested significant cognitive effort in that topic.

5. **Add `novelty` to EST's emotional diversity bonus**: MW v2's `novelty` (ROUTINE/EXPECTED/NOVEL/SURPRISING) on observations. EST's emotional diversity bonus (McGaugh 2004 reference) should consider novelty: SURPRISING events with high emotional diversity get a stronger memory trace (flashbulb memory effect).

6. **Add `source_type` to SPR specificity scoring**: MW v2's `source_type` (user_stated, user_implied, system_inferred). Patterns derived from `user_stated` observations should have higher specificity than patterns from `system_inferred` observations. The user explicitly saying "I've learned that delegation works" is stronger evidence than the system inferring a delegation pattern.

7. **Document the st_observations schema update**: When R7 writes observations for MW v2 rows, the observation context snapshot should include the new st_hipp_events columns (narrative_thread_id, intent_type, novelty, elaboration_depth, temporal_orientation, source_type, identity_domains_json). This requires adding these context columns to st_observations in migration 0067. Since we are pre-production, this is a clean schema addition with no data migration concern -- just add the columns and re-ingest.

8. **No cold-start or transition handling needed**: We are pre-production. Every test run starts from a clean database. There is no mixed v1/v2 observation data to worry about. All st_observations rows will contain MW v2 signals from the start. If the schema changes, truncate tables and re-process. This eliminates an entire class of complexity from the R5 implementation.
