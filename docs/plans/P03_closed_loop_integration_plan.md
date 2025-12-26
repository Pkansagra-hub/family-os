# P03 Closed-Loop Learning Integration Plan

> **Purpose**: Maps whiteboard research (p03_whiteboard.md) to specific edits in P03_consolidation_dossier_v2.md
> **Status**: 📋 Planning
> **Created**: 2025-12-24
> **Whiteboard Reference**: [p03_whiteboard.md](../pipelines/p03_whiteboard.md)
> **Target Dossier**: [P03_consolidation_dossier_v2.md](../pipelines/P03_consolidation_dossier_v2.md)

---

## Milestone 1: Learning Infrastructure

**Goal**: Add foundational tables and unified learning engine to P03 dossier before implementation

---

### Epic 1.1: Storage Schema Additions

**Dossier Location**: Section 6 (Storage Schema Design), Lines 2467-3800
**Insert After**: Section 6.16 (st_retention_policy), Line ~3800

---

#### Issue 1.1.1: st_learned_weights table

**Read From Whiteboard**:

- Section 6.1.5 (st_importance_feedback) — pattern for feedback tables
- Section 6.4.1 (Unified Decay Engine) — per-layer parameter storage
- Section 6.10.1 (Per-Layer Weight Vectors) — weight vector structure

**Read From Dossier**:

- Section 6.1 (Schema Design Principles), Lines 2471-2810 — naming conventions, column patterns
- Section 6.12 (st_anchors), Lines 3609-3660 — similar Bayesian parameter storage pattern

**Edit Description**:
Add new section `### 6.17 st_learned_weights (Adaptive Parameters)` with:

| Column | Type | Purpose |
|--------|------|---------|
| param_id | TEXT | Primary key |
| param_key | TEXT | e.g., "importance_emotional", "decay_lambda_PERSON" |
| param_scope | TEXT | 'global', 'space', 'entity_type', 'entity' |
| scope_id | TEXT | space_id or entity_id (NULL for global) |
| space_id | TEXT | Isolation (always set) |
| current_value | REAL | Current learned value |
| prior_value | REAL | Initial/default value |
| confidence | REAL | Learning confidence (0-1) |
| sample_count | INTEGER | Number of feedback samples |
| last_updated_at | BIGINT | Timestamp |
| version | INTEGER | For parameter history |

**Rationale**: Central storage for all learned hyperparameters — single source of truth for importance weights, decay λ, similarity factors, etc.

---

#### Issue 1.1.2: P03 Feedback Handler Subscription

**Read From Whiteboard**:

- Section 3.5 (Implicit Feedback Collection) — "P03 needs to consume `feedback.signal.P03` topic"
- Section 6.15 (Implicit Feedback Collection) — signal types P03 should handle

**Read From External Plan**:

- [PLAN-feedback-pipeline-system.md](./PLAN-feedback-pipeline-system.md) — P21 Feedback architecture
- `st_feedback_signals` table is owned by P21 (FEEDBACK-006)
- K1 emits feedback via observe port → P21 dispatches to `feedback.signal.p03`

**Edit Description**:
Add to Section 9 (Integration Contracts) new subsection `### 9.X P21 Feedback Integration`:

**Content to Add**:

1. **P03 subscribes to**: `feedback.signal.p03` bus topic
2. **P03 consumes P03FeedbackPayload** (defined in PLAN-feedback-pipeline-system.md):
   - `SALIENCE_ADJUSTMENT` — adjust importance scores
   - `DECAY_REVERSAL` — memory was needed but decayed
   - `CLUSTER_CORRECTION` — clustering feedback
   - `REINFORCEMENT_OUTCOME` — did reinforcement help?
   - `NOVELTY_SIGNAL` — gap detected (hedging)

3. **P03 reads from shared table**: `st_feedback_signals WHERE target_pipeline = 'P03'`
4. **P03 marks consumed**: Update `consumed_at`, `consumed_by = 'P03'`

**Rationale**: P03 is a CONSUMER of the P21 feedback system, not the owner. Feedback ingestion, schema validation, and storage are handled by P21.

---

#### Issue 1.1.3: st_pruned_entities table

**Read From Whiteboard**:

- Section 6.14.4 (st_pruned_entities Table) — full schema definition
- Section 6.14.1 (Regret Tracking Window) — 14-day retention
- Section 6.14.2 (Query-to-Pruned Matching) — embedding storage for matching

**Read From Dossier**:

- Section 6.10 (st_vec), Lines 3472-3522 — embedding storage pattern with pgvector
- Section 4.4 (R3 Synaptic Homeostasis), Lines ~1800 — pruning/archival logic

**Edit Description**:
Add new section `### 6.19 st_pruned_entities (Regret Tracking)` with:

| Column | Type | Purpose |
|--------|------|---------|
| prune_id | TEXT | Primary key |
| entity_id | TEXT | Original entity ID |
| entity_type | TEXT | PERSON, PLACE, EVENT, etc. |
| source_table | TEXT | st_epi, st_kg_dom, etc. |
| canonical_name | TEXT | For fuzzy name matching |
| embedding | VECTOR(1024) | For semantic matching (pgvector) |
| space_id | TEXT | Isolation |
| decay_factor_at_prune | REAL | What was decay when pruned |
| pruned_at | BIGINT | Timestamp |
| matched_query_id | TEXT | If regret detected (nullable) |
| matched_at | BIGINT | When regret detected (nullable) |

**Indexes**: `idx_pruned_embedding` using ivfflat for vector search, TTL 14 days via st_retention_policy.

**Rationale**: Enables "regret tracking" — if user queries an entity within 14 days of pruning, we know λ was too aggressive and can adjust.

---

#### Issue 1.1.4: st_consolidation_audit table

**Read From Whiteboard**:

- Section 6.16.3 (Explainability) — audit trail design, user-facing explanations
- Section 6.16.3 st_consolidation_audit Table — full schema

**Read From Dossier**:

- Section 14.5 (Audit Trail), Lines ~7800 — K0 observability integration
- Section 8.4 (Structured Logging), Lines ~4500 — logging patterns

**Edit Description**:
Add new section `### 6.20 st_consolidation_audit (Decision Audit)` with:

| Column | Type | Purpose |
|--------|------|---------|
| audit_id | TEXT | Primary key |
| memory_id | TEXT | Affected memory entity |
| source_table | TEXT | st_epi, st_kg_dom, etc. |
| action | TEXT | 'REINFORCE', 'DECAY', 'ARCHIVE', 'MERGE', 'CREATE' |
| formula_used | TEXT | e.g., "hebbian_v2", "decay_unified" |
| inputs_json | JSONB | Input parameters to formula |
| outputs_json | JSONB | Output values from formula |
| explanation | TEXT | User-friendly explanation template |
| space_id | TEXT | Isolation |
| cycle_id | TEXT | Consolidation cycle ID |
| created_at | BIGINT | Timestamp |

**Retention**: 90 days detailed, then aggregated. RLS enforced.

**Rationale**: Enables explainability ("This memory was reinforced because...") and debugging. Links decisions to formulas for post-hoc analysis.

---

#### Issue 1.1.5: st_feedback_quarantine table

**Read From Whiteboard**:

- Section 6.15.3 (Adversarial Handling) — quarantine process
- Section 6.15.3 Defense Layers — rate limiting, anomaly detection

**Read From Dossier**:

- Section 14.2 (Privacy Band Enforcement), Lines ~7700 — security patterns
- Section 13.4 (st_dlq), Lines ~7500 — dead letter queue pattern

**Edit Description**:
Add new section `### 6.21 st_feedback_quarantine (Suspicious Signals)` with:

| Column | Type | Purpose |
|--------|------|---------|
| quarantine_id | TEXT | Primary key |
| signal_id | TEXT | Reference to st_feedback_signals |
| space_id | TEXT | Isolation |
| reason | TEXT | 'RATE_LIMIT', 'VELOCITY_SPIKE', 'ANOMALY', 'ENTROPY' |
| severity | TEXT | 'LOW', 'MEDIUM', 'HIGH' |
| detected_at | BIGINT | When quarantined |
| reviewed_at | BIGINT | When reviewed (nullable) |
| reviewed_by | TEXT | Reviewer ID (nullable) |
| decision | TEXT | 'RELEASE', 'DISCARD', NULL |
| auto_release_at | BIGINT | 48h after detected_at |

**Rationale**: Protects learning from adversarial or buggy feedback. Suspicious signals are held for review before affecting parameters.

---

#### Issue 1.1.6: Parameter History Columns

**Read From Whiteboard**:

- Section 6.16.2 (Rollback Mechanism) — parameter history schema
- Section 6.16.2 Parameter History Schema — version, quality tracking

**Read From Dossier**:

- Section 6.17 (proposed st_learned_weights) — add history support
- Section 11.5 (Backward Compatibility), Lines ~6900 — versioning patterns

**Edit Description**:
Extend `st_learned_weights` (Issue 1.1.1) with history support:

| Additional Column | Type | Purpose |
|-------------------|------|---------|
| version | INTEGER | Increment on each update |
| previous_value | REAL | Value before this update |
| quality_at_update | REAL | Quality metric when updated |
| rollback_eligible | BOOLEAN | Can be rolled back? |

Add history table `st_learned_weights_history`:

| Column | Type | Purpose |
|--------|------|---------|
| history_id | TEXT | Primary key |
| param_id | TEXT | FK to st_learned_weights |
| version | INTEGER | Version number |
| value | REAL | Value at this version |
| quality_at_time | REAL | Quality metric |
| applied_at | BIGINT | When applied |
| space_id | TEXT | Isolation |

**Retention**: Last 10 versions per parameter.

**Rationale**: Enables automatic and manual rollback when learning degrades quality. "Undo" capability for parameter changes.

---

### Epic 1.2: Feature Flag System

**Dossier Location**: Section 12 (Policy Decisions & Feature Flags), Lines 7080-7500
**Extend**: Section 12.4 (Feature Flag Master List), Line ~7354

---

#### Issue 1.2.1: Feature Flag Schema for Learning

**Read From Whiteboard**:

- Section 6.9 (UCT/MCTS) — feature flag for disabled MVP
- Section 6.16.1 (A/B Testing) — phased rollout with flags

**Read From Dossier**:

- Section 12.4 (Feature Flag Master List), Lines 7354-7400 — existing flag table
- Section 12.4.1 (Feature Flag Operational Guide) — flag change procedures

**Edit Description**:
Add to Section 12.4 table:

| Flag Name | Type | Default | Description |
|-----------|------|---------|-------------|
| `P03_FF_LEARNING_ENABLED` | bool | `false` | Master switch for all learning |
| `P03_FF_IMPORTANCE_LEARNING` | enum | `disabled` | disabled/shadow/enabled |
| `P03_FF_HEBBIAN_LEARNING` | enum | `disabled` | disabled/shadow/enabled |
| `P03_FF_DECAY_LEARNING` | enum | `disabled` | disabled/shadow/enabled |
| `P03_FF_SIMILARITY_LEARNING` | enum | `disabled` | disabled/shadow/enabled |
| `P03_FF_THRESHOLD_LEARNING` | enum | `disabled` | disabled/shadow/enabled |

**Rationale**: Granular control over learning subsystems. Can enable/disable individual formula learning independently.

---

#### Issue 1.2.2: Shadow Mode Capability

**Read From Whiteboard**:

- Section 6.16.1 (A/B Testing) — shadow mode details
- Section 6.16.1 Testing Phases — Phase 0: Shadow

**Read From Dossier**:

- Section 12.4.2 (Environment-Specific Defaults), Lines ~7420 — per-env settings
- Section 8.2 (Metric Definitions), Lines ~4400 — comparison metrics

**Edit Description**:
Add new subsection `#### 12.4.3 Shadow Mode Specification`:

**Shadow Mode Behavior**:

- When flag = `shadow`: both old and new formula run
- Old formula applies changes to database
- New formula computes but does NOT apply
- Both outcomes logged for comparison

**Shadow Metrics** (add to Section 8.2):

- `p03_shadow_agreement_rate`: % where old and new agree
- `p03_shadow_improvement_rate`: % where new is better
- `p03_shadow_regression_rate`: % where new is worse

**Promotion Criteria**:

- Agreement rate > 80%
- Improvement rate > regression rate
- 7 days of shadow data

**Rationale**: Safe testing of new formulas without risking production data. Validate before enabling.

---

#### Issue 1.2.3: Phased Rollout Strategy

**Read From Whiteboard**:

- Section 6.3.3 (Feedback-Driven Adjustment) — gradual rollout
- Section 6.16.1 Testing Phases — Canary → Gradual → Full

**Read From Dossier**:

- Section 11.2 (v1 → v2 Migration), Lines ~6800 — migration phases
- Section 12.4.1 (Operational Guide) — flag change commands

**Edit Description**:
Add new subsection `#### 12.4.4 Learning Rollout Strategy`:

| Phase | % Spaces | Duration | Flag Value | Rollback Trigger |
|-------|----------|----------|------------|------------------|
| 0. Shadow | 100% (read-only) | 7 days | `shadow` | N/A |
| 1. Canary | 5% | 7 days | `enabled_low` | Regression > 5% |
| 2. Gradual | 25% → 50% → 75% | 14 days | `enabled_medium` | Regression > 3% |
| 3. Full | 100% | Permanent | `enabled` | Regression > 2% |

**Canary Selection**:

- Internal test spaces (priority)
- High-activity spaces (more feedback)
- Diverse usage patterns

**Rationale**: Conservative rollout protects users. Automatic rollback on quality regression.

---

#### Issue 1.2.4: Per-Space Flag Isolation

**Read From Whiteboard**:

- Section 6.16.4 (Multi-Tenant Isolation) — per-space isolation
- Section 6.16.4 Isolation Enforcement — space_id in all queries

**Read From Dossier**:

- Section 14.2 (Privacy Band Enforcement), Lines ~7700 — RLS patterns
- Section 6.1 (Schema Design Principles) — space_id column requirement

**Edit Description**:
Add to Section 12.4 a new table for per-space overrides:

**st_feature_flag_overrides**:

| Column | Type | Purpose |
|--------|------|---------|
| override_id | TEXT | Primary key |
| flag_name | TEXT | e.g., "P03_FF_LEARNING_ENABLED" |
| space_id | TEXT | Space this override applies to |
| value | TEXT | Override value |
| reason | TEXT | Why override exists |
| created_at | BIGINT | Timestamp |
| expires_at | BIGINT | Auto-expire (nullable) |

**Resolution Order**:

1. Per-space override (if exists and not expired)
2. Environment default (Section 12.4.2)
3. Global default (Section 12.4)

**Rationale**: Enables canary rollout to specific spaces. Also allows disabling learning for specific problematic spaces without affecting others.

---

### Epic 1.1/1.2 Summary: Dossier Locations

| Issue | Insert Location | Section Number |
|-------|-----------------|----------------|
| 1.1.1 | After 6.16 | New 6.17 |
| 1.1.2 | After 6.17 | New 6.18 |
| 1.1.3 | After 6.18 | New 6.19 |
| 1.1.4 | After 6.19 | New 6.20 |
| 1.1.5 | After 6.20 | New 6.21 |
| 1.1.6 | Extend 6.17 + new 6.22 | 6.17, 6.22 |
| 1.2.1 | Extend 12.4 table | 12.4 |
| 1.2.2 | After 12.4.2 | New 12.4.3 |
| 1.2.3 | After 12.4.3 | New 12.4.4 |
| 1.2.4 | After 12.4.4 | New 12.4.5 |

---

## Milestone 2: Formula Learning — R1 Phase

**Goal**: Make R1 (Hippocampal Replay) formulas learnable with closed-loop feedback

---

### Epic 2.1: Importance Score Learning

**Dossier Location**: Section 4.2 (R1), Lines 1112-1140; Appendix C.2, Lines 10942-11120
**Primary Formula**: `importance = emotional + novelty + social (weighted sum)`

---

#### Issue 2.1.1: Feedback Loop Design for Importance

**Read From Whiteboard**:

- Section 6.1.2 (Feedback Loop Design) — full feedback loop diagram
- Section 6.1.4 (Feedback Signals for Importance) — signal types and interpretations
- Section 6.1.7 (Integration with P03 R1) — how to use learned weights

**Read From Dossier**:

- Section 4.2.2 (Importance Scoring Algorithm), Lines 1118-1120 — current static description
- Appendix C.2.1 (Importance Scoring), Lines 10960-11090 — detailed algorithm with static weights

**Edit Description**:
Extend Section 4.2.2 with new subsection `#### 4.2.2.1 Closed-Loop Importance Learning`:

**Content to Add**:

1. **Feedback Loop Diagram**: Copy from whiteboard 6.1.2
2. **Feedback Signals Table**:
   - `MEMORY_GROUNDED` (K1) → event was useful → boost importance
   - `MEMORY_RECALLED_NOT_USED` (K1) → event was noise → penalize
   - `MEMORY_MISS` (P04) → needed event not found → boost similar
   - `USER_CORRECTION` (K1) → explicit feedback → strong signal
3. **Ground Truth Definition**: From whiteboard 6.1.3 SQL queries

**Also Extend**: Appendix C.2.1 with `ImportanceWeightLearner` class reference (algorithm lives in whiteboard 6.1.6, link to it)

**Rationale**: Currently dossier describes static weights (0.25/0.30/0.25/0.20). Need to document how weights become learnable.

---

#### Issue 2.1.2: Weight Learning Mechanism

**Read From Whiteboard**:

- Section 6.1.6 (Learning Algorithm) — `ImportanceWeightLearner` class with gradient descent
- Section 6.1.10 (Weight Drift Handling) — sliding window, momentum, decay

**Read From Dossier**:

- Appendix C.2.1 lines 10990-11010 — current static weight table:
  - `sentiment_weight: 0.25`
  - `affect_weight: 0.30`
  - `novelty_weight: 0.25`
  - `social_weight: 0.20`

**Edit Description**:
Add to Appendix C.2.1 a new subsection `#### C.2.1.1 Adaptive Weight Learning`:

**Content to Add**:

1. **Learning Algorithm**:
   - Method: Online gradient descent with momentum=0.9
   - Loss: Binary cross-entropy predicting "will event be grounded?"
   - Training: Nightly batch during P03 cycle

2. **Weight Persistence**:
   - Table: `st_learned_weights` (from M1 Issue 1.1.1)
   - Key pattern: `importance_<component>` e.g., `importance_emotional`
   - Per-space isolation

3. **Drift Handling**:
   - 30-day sliding window for training data
   - Exponential decay on older samples (λ=0.1)
   - Momentum update: `v = 0.9×v + gradient`

4. **Metrics** (add to Section 8.2):
   - `p03_importance_weight_emotional`: Current emotional weight
   - `p03_importance_weight_drift_30d`: Euclidean drift from prior
   - `p03_importance_training_loss`: Learning convergence

**Rationale**: Establishes the learning mechanism that replaces static weights.

---

#### Issue 2.1.3: Cold Start Handling

**Read From Whiteboard**:

- Section 6.1.3 (Ground Truth Definition) — needs sufficient signals
- Section 6.1.6 line "min_samples = 500" — threshold before learning
- Section 6.1.8 Q2 — "Per-space with global fallback"

**Read From Dossier**:

- Section 4.2.2 (Importance Scoring) — no cold start handling currently
- Section 6.1 (Schema Design Principles) — default value patterns

**Edit Description**:
Add to Section 4.2.2 a new subsection `#### 4.2.2.2 Cold Start Strategy`:

**Content to Add**:

1. **Minimum Samples**: 500 events with grounding feedback before learning
2. **Fallback Hierarchy**:
   - Level 1: Per-space learned weights (if sample_count ≥ 500)
   - Level 2: Global learned weights (aggregated across spaces)
   - Level 3: Static prior (0.25/0.30/0.25/0.20)
3. **New Space Behavior**:
   - Uses static prior until 500 grounding events accumulated
   - Progressive blend: `weight = α×learned + (1-α)×static` where α = min(1, samples/500)

**Also Add**: Configuration key `P03_IMPORTANCE_MIN_SAMPLES` to Section 16 (Configuration)

**Rationale**: New spaces and new users need sensible defaults until feedback accumulates.

---

#### Issue 2.1.4: Momentum-Based Stability

**Read From Whiteboard**:

- Section 6.1.10 (Weight Drift Handling) — `WeightDriftHandler` class
- Section 6.1.10 `train_with_momentum()` — momentum=0.9, velocity tracking
- Section 6.1.10 Drift Alerting table — thresholds for alerts

**Read From Dossier**:

- Section 17.3 (Alerting Rules) — alert patterns
- Section 8.2 (Metric Definitions) — metric naming

**Edit Description**:
Add to Appendix C.2.1 subsection `#### C.2.1.2 Stability Controls`:

**Content to Add**:

1. **Momentum Update**:
   - Formula: `velocity = 0.9 × velocity + gradient`
   - Weight update: `w_new = w_old - lr × velocity`
   - Prevents oscillation from noisy feedback

2. **Clamping**:
   - Weights clamped to [0.05, 0.60] range
   - No single component can dominate (>60%)
   - No component can be ignored (<5%)

3. **Drift Alerts** (add to Section 17.3):

   | Metric | Threshold | Severity | Action |
   |--------|-----------|----------|--------|
   | `weight_drift_30d > 0.3` | Large drift | Warning | Admin notification |
   | `training_samples < 100` | Low data | Info | Skip training |
   | `training_loss > 0.5` | Poor fit | Warning | Investigate features |

4. **Rollback Trigger**: If loss increases 3 consecutive nights → revert to prior weights

**Rationale**: Learning must be stable — wild swings hurt user experience.

---

### Epic 2.2: Hebbian Weight Update

**Dossier Location**: Section 4.2.3 (Association Strengthening), Lines 1122-1126; Appendix C.2.2, Lines 11130-11320
**Primary Formula**: `new_weight = current + lr × (max - current) × importance`

---

#### Issue 2.2.1: Anti-Hebbian Decay

**Read From Whiteboard**:

- Section 6.2.4 (Anti-Hebbian Learning) — `AntiHebbianDecay` class
- Section 6.2.4 Conflict Signals table — signals that trigger anti-Hebbian
- Section 6.2.7 row "ASSOCIATION_WRONG" — user correction triggers decay

**Read From Dossier**:

- Appendix C.2.2 lines 11250-11270 — `apply_decay()` method (only temporal decay)
- Section 4.2.3 — no mention of conflict-driven decay

**Edit Description**:
Extend Appendix C.2.2 with new subsection `#### C.2.2.1 Anti-Hebbian Decay`:

**Content to Add**:

1. **Principle**: "Cells that fire apart, unwire"
2. **Conflict Signals**:

   | Signal | Source | Action |
   |--------|--------|--------|
   | `ENTITY_MERGE_REJECTED` | P06/User | `anti_hebbian(-0.2)` + flag distinct |
   | `ASSOCIATION_WRONG` | K1 correction | `anti_hebbian(-0.3)` |
   | `MUTUAL_EXCLUSION` | P03 R4 | Candidate for prune |
   | `CONTRADICTION` | P03 R7 | `anti_hebbian(-0.15)` |

3. **Anti-Hebbian Formula**:

   ```
   Δw = -anti_lr × current_weight × confidence × penalty_multiplier
   anti_lr = 0.15 (faster than positive learning)
   penalty_multiplier = 1.3 if explicit correction, else 1.0
   ```

4. **Prune Threshold**: If weight < 0.05 after anti-Hebbian → candidate for soft delete

**Also Add**: Metric `p03_hebbian_anti_updates` to Section 8.2

**Rationale**: Currently no negative learning — wrong associations persist forever.

---

#### Issue 2.2.2: Resurrection Mechanism

**Read From Whiteboard**:

- Section 6.2.11 Q6 — "Check archival_status before insert, restore if ARCHIVED"
- Section 6.4.4 (Resurrection Formula from Decay section) — `max(0.7, 0.5 + current × 0.5)`

**Read From Dossier**:

- Appendix C.2.2 lines 11310-11320 — pruned_edges output, but no resurrection
- Section 4.4.3 (Retention Policy) — ACTIVE → ARCHIVED → TOMBSTONE lifecycle

**Edit Description**:
Add to Appendix C.2.2 subsection `#### C.2.2.2 Edge Resurrection`:

**Content to Add**:

1. **When to Resurrect**:
   - New co-occurrence for ARCHIVED edge
   - K1 uses relationship that was archived
   - User explicitly confirms relationship

2. **Resurrection Formula**:

   ```
   new_weight = max(0.7, 0.5 + old_weight × 0.5)
   resurrection_count += 1
   archival_status = 'ACTIVE'
   ```

3. **Instability Alert**: If `resurrection_count >= 3` → emit alert
   - Suggests edge is borderline important
   - Consider lowering decay rate for this relationship type

4. **Audit**: Log resurrection to `st_hebbian_feedback` with signal_type='RESURRECTION'

**Rationale**: Edges wrongly pruned should be recoverable when re-observed.

---

#### Issue 2.2.3: Per-Context Learning Rate

**Read From Whiteboard**:

- Section 6.2.3 (Adaptive Learning Rate Design) — `AdaptiveHebbianLearner` class
- Section 6.2.3 `compute_learning_rate()` — exponential decay from 0.3 to 0.05

**Read From Dossier**:

- Appendix C.2.2 lines 11135 — fixed `learning_rate: 0.1`
- Section 4.2.3 — mentions "Co-occurrence counting algorithm" but no rate adaptation

**Edit Description**:
Extend Appendix C.2.2 `HebbianConfig` section with `#### C.2.2.3 Adaptive Learning Rate`:

**Content to Add**:

1. **Problem**: Fixed LR=0.1 over-reinforces new edges, under-reinforces established ones
2. **Solution**: Adaptive rate based on relationship maturity

3. **Formula**:

   ```
   lr = lr_mature + (lr_new - lr_mature) × exp(-decay × co_occurrence_count)
   lr_new = 0.30 (fast for new edges)
   lr_mature = 0.05 (slow for established)
   decay = 0.10
   ```

4. **Rate Table**:

   | Co-occurrences | Learning Rate |
   |----------------|---------------|
   | 1 | 0.28 |
   | 5 | 0.19 |
   | 10 | 0.12 |
   | 25 | 0.06 |
   | 50+ | 0.05 |

5. **Storage**: LR parameters stored in `st_learned_weights` with key `hebbian_lr_*`

**Rationale**: Mature relationships should be stable; new ones should learn quickly.

---

#### Issue 2.2.4: Saturation Prevention

**Read From Whiteboard**:

- Section 6.2.5 (Log-Scale Co-occurrence Capping) — `normalize_co_occurrence()` function
- Section 6.2.3 lines on soft saturation — `(max_weight - current_weight)` term

**Read From Dossier**:

- Appendix C.2.2 lines 11230-11245 — `update_edge_weight()` has soft saturation
- No co-occurrence capping mentioned

**Edit Description**:
Add to Appendix C.2.2 subsection `#### C.2.2.4 Saturation Controls`:

**Content to Add**:

1. **Soft Saturation** (already in dossier, document explicitly):
   - Formula includes `(max_weight - current_weight)` term
   - As weight → 1.0, delta → 0
   - Prevents weights from exceeding max_weight

2. **Co-occurrence Capping** (new):
   - Problem: Entities appearing 1000× shouldn't be 1000× stronger than 10×
   - Solution: Log-scale normalization after threshold

   ```
   if count ≤ 50: normalized = count
   if count > 50: normalized = 50 + ln(count/50) × 50
   ```

   - Examples: 100→85, 500→165, 1000→200

3. **Weight Cap**: max_weight = 1.0 (enforced via MIN in update)

4. **Configuration**: Add `P03_HEBBIAN_CAP_THRESHOLD` to Section 16 (default: 50)

**Rationale**: Prevents dominant pairs from drowning out other relationships.

---

#### Issue 2.2.5: Normalization Strategy

**Read From Whiteboard**:

- Section 6.2.9 (Integration with st_learned_weights) — parameter storage
- Section 6.2.10 (Learning Hebbian Hyperparameters) — `HebbianHyperparamLearner`
- Section 6.2.11 Q5 — "Use existing archival_status lifecycle"

**Read From Dossier**:

- Appendix C.2.2 Edge Weight Interpretation table — 0.80-1.00 = Very Strong, etc.
- Section 6.9 (st_kg_edges) — `edge_weight REAL` column

**Edit Description**:
Add to Appendix C.2.2 subsection `#### C.2.2.5 Weight Normalization`:

**Content to Add**:

1. **Weight Range**: [0.0, 1.0] enforced
   - 0.0: No relationship (edge pruned)
   - 1.0: Maximum strength

2. **Interpretation Table** (already in dossier, reference it):

   | Range | Strength | Example |
   |-------|----------|---------|
   | 0.80-1.00 | Very Strong | Family, best friends |
   | 0.50-0.79 | Strong | Close colleagues |
   | 0.20-0.49 | Moderate | Acquaintances |
   | 0.01-0.19 | Weak | One-time interactions |

3. **Per-Relation-Type Normalization**:
   - Different relation types may have different weight distributions
   - E.g., INTERACTS_WITH saturates faster than DISCUSSES
   - Future: Learn per-relation normalization curves

4. **Global Normalization**: Not applied (weights are per-edge, not relative)

**Rationale**: Consistent interpretation of edge weights across the system.

---

### Epic 2.1/2.2 Summary: Dossier Locations

| Issue | Insert Location | Section Number |
|-------|-----------------|----------------|
| 2.1.1 | Extend Section 4.2.2 | New 4.2.2.1 |
| 2.1.2 | Extend Appendix C.2.1 | New C.2.1.1 |
| 2.1.3 | Extend Section 4.2.2 | New 4.2.2.2 |
| 2.1.4 | Extend Appendix C.2.1 | New C.2.1.2 |
| 2.2.1 | Extend Appendix C.2.2 | New C.2.2.1 |
| 2.2.2 | Extend Appendix C.2.2 | New C.2.2.2 |
| 2.2.3 | Extend Appendix C.2.2 | New C.2.2.3 |
| 2.2.4 | Extend Appendix C.2.2 | New C.2.2.4 |
| 2.2.5 | Extend Appendix C.2.2 | New C.2.2.5 |

### Dependencies from Milestone 1

| M2 Issue | Depends On | Reason |
|----------|------------|--------|
| 2.1.1 | 1.1.2 (st_feedback_signals) | Feedback signals flow through this table |
| 2.1.2 | 1.1.1 (st_learned_weights) | Learned weights stored here |
| 2.1.3 | 1.1.1 (st_learned_weights) | Fallback reads from weight table |
| 2.1.4 | 1.2.1 (Feature flags) | `P03_FF_IMPORTANCE_LEARNING` controls this |
| 2.2.1 | 1.1.2 (st_feedback_signals) | Anti-Hebbian signals from feedback |
| 2.2.2 | 1.1.4 (st_consolidation_audit) | Resurrection logged in audit |
| 2.2.3 | 1.1.1 (st_learned_weights) | LR parameters stored here |
| 2.2.4 | 1.2.1 (Feature flags) | `P03_FF_HEBBIAN_LEARNING` controls this |

---

## Milestone 3: Formula Learning — R2/R3 Phases

**Goal**: Make R2 (Integration) and R3 (Forgetting) formulas learnable with closed-loop feedback

---

### Epic 3.1: DBSCAN Clustering

**Dossier Location**: Section 4.3 (R2), Lines 1138-1168; Appendix C.3, Lines 11338-11500
**Primary Formula**: `composite_distance = (1 - temporal_weight) × semantic_dist + temporal_weight × temporal_dist`

---

#### Issue 3.1.1: Per-Space Eps Learning

**Read From Whiteboard**:

- Section 6.3.1 (Per-Space `eps` Learning) — `AdaptiveDBSCANLearner` class
- Section 6.3.1 eps bounds — EPS_MIN=0.15, EPS_MAX=0.40, EPS_STEP=0.02
- Section 6.3.4 (Cluster Quality Evaluation) — silhouette target > 0.5

**Read From Dossier**:

- Section 4.3.1 (Episodic Clustering), Lines 1140-1145 — mentions eps=0.25 as fixed
- Appendix C.3.1 (DBSCAN), Lines 11380-11420 — `eps: 0.25` hardcoded in DBSCANParams

**Edit Description**:
Add to Section 4.3.1 new subsection `#### 4.3.1.1 Adaptive Eps Learning`:

**Content to Add**:

1. **Problem**: Fixed eps=0.25 doesn't suit all spaces — some need tighter (0.15), others looser (0.40)
2. **Solution**: Per-space eps stored in `st_learned_weights`

3. **Storage Pattern**:

   | weight_type | weight_key | Default | Range |
   |-------------|------------|---------|-------|
   | DBSCAN_PARAMS | eps | 0.25 | [0.15, 0.40] |
   | DBSCAN_PARAMS | min_samples | 2.0 | [2, 5] |
   | DBSCAN_PARAMS | temporal_weight | 0.3 | [0.1, 0.5] |

4. **Learning Algorithm**:
   - Compute silhouette score after each P03 cycle
   - If silhouette < 0.5: adjust eps by ±0.02
   - Use momentum=0.9 for stability

5. **Metrics** (add to Section 8.2):
   - `p03_dbscan_eps_current`: Current eps value
   - `p03_dbscan_silhouette`: Clustering quality [0-1]

**Also Extend**: Appendix C.3.1 DBSCANParams to reference `st_learned_weights` for eps lookup

**Rationale**: ADR k003.3 sets silhouette target > 0.5 — learning eps helps achieve this per-space.

---

#### Issue 3.1.2: Episode Split Detection

**Read From Whiteboard**:

- Section 6.3.2 (Long Episode Splitting) — `EpisodeSplitter` class
- Section 6.3.2 break signals — location, activity, time gap, 4-hour hard limit
- Section 6.3.2 `_detect_break()` — priority order for split signals

**Read From Dossier**:

- Appendix C.3.1 lines 11400-11420 — `max_temporal_gap_hours: 4.0` mentioned but no pre-split
- Section 4.3.2 (Pattern Extraction) — no episode split handling

**Edit Description**:
Add to Appendix C.3.1 new subsection `#### C.3.1.1 Pre-Clustering Episode Split`:

**Content to Add**:

1. **Problem**: Events spanning >4 hours create poor clusters
2. **Solution**: Pre-split long sequences BEFORE DBSCAN runs

3. **Split Signals** (priority order):

   | Signal | Condition | Example |
   |--------|-----------|---------|
   | Location Change | geohash prefix differs by >4 chars | Home → Office |
   | Activity Change | activity_type changes | MEAL → OUTING |
   | Time Gap | gap > 30 minutes | Lunch break |
   | Hard Limit | episode > 4 hours | Force split |

4. **Algorithm**: `EpisodeSplitter.split_long_sequences()` runs before DBSCAN
5. **Data Source**: Uses `st_hipp_events.location_geohash` + `st_hipp_events.activity_type`

**Also Add**: Configuration key `P03_DBSCAN_MAX_EPISODE_HOURS` to Section 16 (default: 4)

**Rationale**: Simpler than hierarchical clustering; uses existing columns without algorithm complexity.

---

#### Issue 3.1.3: Min_samples Adaptation

**Read From Whiteboard**:

- Section 6.3.3 (Per-Space min_samples Configuration) — `MinSamplesAdjuster` class
- Section 6.3.3 noise thresholds — NOISE_THRESHOLD_HIGH=0.20, NOISE_THRESHOLD_LOW=0.05

**Read From Dossier**:

- Appendix C.3.1 lines 11385 — `min_samples: 2` hardcoded
- Section 4.3.4 (Consolidation Quality Gates) — mentions "minimum cluster size thresholds"

**Edit Description**:
Add to Appendix C.3.1 new subsection `#### C.3.1.2 Adaptive Min_samples`:

**Content to Add**:

1. **Problem**: `min_samples=2` too low for noisy spaces, too high for sparse spaces
2. **Noise Proxy**: Singleton clusters (cluster_size = 1) indicate noise

3. **Adjustment Rules**:

   | Singleton Rate | Action | New min_samples |
   |----------------|--------|-----------------|
   | > 20% | Too noisy | +1 (max 5) |
   | < 5% | Too strict | -1 (min 2) |
   | 5-20% | Good balance | No change |

4. **Storage**: `st_learned_weights` with key `min_samples`
5. **Evaluation**: Count singletons after each P03 cycle

**Rationale**: Balances cluster quality vs coverage based on actual noise levels.

---

#### Issue 3.1.4: Feedback-Driven Cluster Quality

**Read From Whiteboard**:

- Section 6.3.4 (Cluster Quality Evaluation Without Labels) — multi-signal approach
- Section 6.3.4 `ClusterQualityMetrics` — composite score formula
- Section 6.3.4 Feedback Loop Diagram — DBSCAN → Quality Signals → st_learned_weights

**Read From Dossier**:

- Section 4.3.4 (Consolidation Quality Gates), Lines 1160-1168 — mentions quality gates
- Section 8.2 (Metric Definitions) — metric patterns

**Edit Description**:
Extend Section 4.3.4 with new subsection `#### 4.3.4.1 Closed-Loop Cluster Quality`:

**Content to Add**:

1. **Quality Signals**:

   | Signal | Source | Weight | Target |
   |--------|--------|--------|--------|
   | Silhouette Score | Automated | 0.40 | > 0.5 |
   | Grounding Rate | K1 feedback | 0.30 | > 0.6 |
   | Correction Rate | User feedback | 0.20 | < 0.05 |
   | Singleton Rate | Noise proxy | 0.10 | < 0.20 |

2. **Composite Quality**: `quality = 0.40×silhouette + 0.30×grounding + 0.20×(1-corrections) + 0.10×(1-singletons)`
3. **Tuning Trigger**: If `composite_quality < 0.5` → adjust eps/min_samples
4. **User Correction Signal**: `CLUSTER_WRONG` in `st_feedback_signals.payload_json`

**Also Add**: Metrics to Section 8.2:

- `p03_cluster_grounding_rate`: Fraction of clusters used by K1
- `p03_cluster_correction_rate`: User corrections / total clusters

**Rationale**: No ground truth labels, so use downstream usage + user feedback as proxy.

---

### Epic 3.2: Unified Decay Engine

**Dossier Location**: Section 4.4 (R3), Lines 1168-1220; Appendix C.4, Lines 11699-11900
**Primary Formula**: `decay_factor = exp(-λ × days_since_last_observed)`

---

#### Issue 3.2.1: Unified Decay Engine Architecture

**Read From Whiteboard**:

- Section 6.4.1 (Unified Decay System Architecture) — `UnifiedDecayEngine` class
- Section 6.4.1 `DECAY_CONFIGS` — per-layer λ values and thresholds
- Section 6.4.1 tables list — 8 tables with decay support

**Read From Dossier**:

- Section 4.4.3 (Retention Policy Enforcement), Lines 1190-1195 — mentions λ but not unified
- Appendix C.4.2 (Exponential Decay), Lines 11800-11850 — `ExponentialDecayEngine` class

**Edit Description**:
Add to Section 4.4 new subsection `#### 4.4.1.1 Unified Decay Architecture`:

**Content to Add**:

1. **Design**: Single `UnifiedDecayEngine` serves ALL 8 memory tables
2. **Tables with Decay**:

   | Table | Brain Analog | Default λ | Half-Life |
   |-------|--------------|-----------|-----------|
   | st_epi | Episodic | 0.005 | 139 days |
   | st_sem | Semantic | 0.003 | 231 days |
   | st_procedural | Procedural | 0.010 | 69 days |
   | st_social | Social | 0.002 | 347 days |
   | st_kg_dom | Concepts | 0.001 | 693 days |
   | st_kg_edges | Associations | 0.008 | 87 days |
   | st_prospective | Plans | 0.020 | 35 days |
   | st_hipp_events | Short-term | 0.100 | 7 days |

3. **Schema Additions** (add to each table):
   - `access_count INTEGER DEFAULT 0`
   - `last_accessed_at BIGINT`
   - `resurrection_count INTEGER DEFAULT 0`

4. **Effective λ**: `λ_effective = λ_base × space_modifier × actor_modifier × entity_type_modifier`

**Also Extend**: Appendix C.4.2 to reference `UnifiedDecayEngine` as wrapper around `ExponentialDecayEngine`

**Rationale**: Centralizes decay logic; enables consistent learning across all memory types.

---

#### Issue 3.2.2: Per-Layer Lambda Configuration

**Read From Whiteboard**:

- Section 6.4.1 `DECAY_CONFIGS` — per-layer settings including archive/tombstone thresholds
- Section 6.4.1 `_get_entity_type_modifier()` — PERSON=0.5, THING=1.5

**Read From Dossier**:

- Appendix F (Threshold Calibration Matrix), Lines ~15000 — threshold tables
- Section 4.4.3 — mentions "Layer-specific decay constants"

**Edit Description**:
Add to Appendix F new section `#### F.X Decay Lambda Calibration`:

**Content to Add**:

1. **Per-Layer λ Table** (copy from whiteboard 6.4.1)
2. **Entity Type Modifiers**:

   | Entity Type | Modifier | Effect |
   |-------------|----------|--------|
   | FAMILY_MEMBER | 0.2 | Decays 5× slower |
   | PERSON | 0.5 | Decays 2× slower |
   | CONCEPT | 0.7 | Slightly slower |
   | ORGANIZATION | 1.0 | Baseline |
   | PLACE | 0.8 | Slightly slower |
   | THING | 1.5 | Decays 1.5× faster |

3. **Thresholds**:
   - `archive_threshold: 0.1` → ACTIVE → ARCHIVED
   - `tombstone_threshold: 0.01` → ARCHIVED → TOMBSTONE

4. **Storage**: Entity type modifiers stored in `st_learned_weights` with `DECAY_PARAMS` type

**Rationale**: People and family members should persist longer than objects.

---

#### Issue 3.2.3: Resurrection Formula

**Read From Whiteboard**:

- Section 6.4.4 (Resurrection with Memory) — `ResurrectionHandler` class
- Section 6.4.4 formula — `new_decay = max(0.7, 0.5 + old_decay × 0.5)`
- Section 6.4.4 resurrection triggers — QUERY, CO_OCCURRENCE, USER_MENTION

**Read From Dossier**:

- Section 4.4.3 — mentions ACTIVE → ARCHIVED → TOMBSTONE but no resurrection
- Appendix C.4.2 — no resurrection handling

**Edit Description**:
Add to Appendix C.4.2 new subsection `#### C.4.2.1 Memory Resurrection`:

**Content to Add**:

1. **Human Memory Model**: "Oh yes, I remember this now!" — feels fresh but familiar
2. **Formula**: `new_decay = max(0.7, 0.5 + old_decay × 0.5)`

   | Old Decay | New Decay | Interpretation |
   |-----------|-----------|----------------|
   | 0.01 (forgotten) | 0.70 | Strong revival |
   | 0.08 (recently archived) | 0.70 | Strong revival (min) |
   | 0.30 (partial) | 0.70 | Strong revival (min) |

3. **Triggers**:
   - `QUERY`: P04 retrieves archived entity
   - `CO_OCCURRENCE`: Archived edge reappears in new event
   - `USER_MENTION`: User explicitly references archived entity

4. **Resurrection Count Tracking**: `resurrection_count += 1` on each revival
5. **Instability Alert**: If `resurrection_count >= 3` → emit alert, suggests λ too aggressive

**Also Add**: Metric `p03_resurrection_rate` to Section 8.2 (alert if > 10%)

**Rationale**: Wrongly pruned memories should be recoverable; high resurrection rate signals tuning needed.

---

#### Issue 3.2.4: Decay Immunity Rules

**Read From Whiteboard**:

- Section 6.4.3 (Decay Immunity System) — `ImmunityChecker` class
- Section 6.4.3 `IMMUNITY_ONTOLOGY` — entity-level and attribute-level immunity
- Section 6.4.3 SQL — `decay_immune BOOLEAN DEFAULT FALSE`

**Read From Dossier**:

- Section 4.4.3 mentions retention but no immunity concept
- Schema sections — no `decay_immune` column

**Edit Description**:
Add to Section 4.4 new subsection `#### 4.4.3.1 Decay Immunity`:

**Content to Add**:

1. **Problem**: Some entities should NEVER decay (birthdays, family names)
2. **Solution**: Two-level immunity system

3. **Entity-Level Immunity** (column on tables):

   ```sql
   ALTER TABLE st_kg_dom ADD COLUMN decay_immune BOOLEAN DEFAULT FALSE;
   ALTER TABLE st_sem ADD COLUMN decay_immune BOOLEAN DEFAULT FALSE;
   ALTER TABLE st_social ADD COLUMN decay_immune BOOLEAN DEFAULT FALSE;
   ```

4. **Attribute-Level Immunity** (ontology-driven):

   | Entity Type | Immune Attributes |
   |-------------|-------------------|
   | PERSON | birthday, name, relationship_to_user |
   | FAMILY_MEMBER | ALL (entity + attributes) |
   | PLACE | home_address, work_address |
   | EVENT | wedding_date, birth_date, death_date |

5. **Auto-Marking**: Family members auto-marked as `decay_immune=TRUE` on creation

**Also Update**: Section 6 (Storage Schema) to add `decay_immune` column to relevant tables

**Rationale**: Core identity facts must persist forever; aligns with human memory.

---

#### Issue 3.2.5: Bayesian Lambda Learning

**Read From Whiteboard**:

- Section 6.4.2 (Learning λ from Access Patterns) — `BayesianLambdaEstimator` class
- Section 6.4.2 cold start — 1000 memories before learning activates
- Section 6.4.2 Bayesian formula — Gamma prior, posterior update

**Read From Dossier**:

- Appendix C.4.2 lines 11810-11830 — `compute_effective_lambda()` but static modifiers
- No Bayesian learning mentioned

**Edit Description**:
Add to Appendix C.4.2 new subsection `#### C.4.2.2 Adaptive Lambda Learning`:

**Content to Add**:

1. **Cold Start**: Use dossier defaults until 1000 memories accumulated
2. **Learning Trigger**: 1000 memories + 5 accesses per entity + 7-day spread

3. **Bayesian Model**:
   - Prior: `λ ~ Gamma(α=2, β=2/λ_base)` — moderate uncertainty
   - Data: Inter-access intervals follow `Exponential(λ)`
   - Posterior: `λ | data ~ Gamma(α + n, β + Σ intervals)`

4. **Update Criteria** (only update if):
   - New estimate differs > 20% from current
   - Credible interval width < 50% of estimate

5. **Storage**: Store as modifier in `st_learned_weights`:
   - Key: `lambda_modifier_{layer}`
   - Value: `learned_λ / base_λ` (ratio)

6. **Per-Space Isolation**: Each space learns its own λ modifiers

**Also Add**: Configuration `P03_DECAY_COLD_START_THRESHOLD` to Section 16 (default: 1000)

**Rationale**: Access patterns reveal how quickly memories should fade for each space.

---

#### Issue 3.2.6: Cross-Layer Decay Audit

**Read From Whiteboard**:

- Section 6.4.5 (P03 R3 Integration) — `r3_apply_decay()` function
- Section 6.4.6 (Access Tracking Integration) — P04 updates access counts
- Section 6.4.7 (Feedback Table for Decay Learning) — `st_decay_feedback`

**Read From Dossier**:

- Section 8.2 (Metric Definitions) — metric patterns
- Section 14.5 (Audit Trail) — audit logging patterns

**Edit Description**:
Extend Section 8.2 with new decay metrics:

**Content to Add**:

1. **Per-Layer Decay Metrics** (for each of 8 tables):
   - `p03_decay_{layer}_decayed`: Count of records with decay_factor updated
   - `p03_decay_{layer}_archived`: Count transitioned to ARCHIVED
   - `p03_decay_{layer}_tombstoned`: Count transitioned to TOMBSTONE
   - `p03_decay_{layer}_immune`: Count skipped due to immunity

2. **Aggregate Decay Metrics**:
   - `p03_decay_total_archived`: Sum across all layers
   - `p03_decay_resurrection_rate`: Resurrections / total accesses
   - `p03_decay_lambda_drift_30d`: Max λ change over 30 days

3. **Decay Feedback Table** (add to Section 6):

   | Column | Type | Purpose |
   |--------|------|---------|
   | feedback_id | TEXT | Primary key |
   | entity_id | TEXT | Affected entity |
   | layer | TEXT | Memory table |
   | signal_type | TEXT | 'DECAY', 'RESURRECTION', 'IMMUNITY' |
   | decay_before | REAL | Value before action |
   | decay_after | REAL | Value after action |
   | trigger_source | TEXT | 'P03', 'P04', 'USER' |
   | created_at | BIGINT | Timestamp |

**Also Add**: Alert `DecayRateAnomaly` to Section 17.3 (trigger if > 30% archived in single cycle)

**Rationale**: Cross-layer visibility ensures decay behavior is consistent and debuggable.

---

### Epic 3.1/3.2 Summary: Dossier Locations

| Issue | Insert Location | Section Number |
|-------|-----------------|----------------|
| 3.1.1 | Extend Section 4.3.1 | New 4.3.1.1 |
| 3.1.2 | Extend Appendix C.3.1 | New C.3.1.1 |
| 3.1.3 | Extend Appendix C.3.1 | New C.3.1.2 |
| 3.1.4 | Extend Section 4.3.4 | New 4.3.4.1 |
| 3.2.1 | Extend Section 4.4 | New 4.4.1.1 |
| 3.2.2 | Extend Appendix F | New F.X |
| 3.2.3 | Extend Appendix C.4.2 | New C.4.2.1 |
| 3.2.4 | Extend Section 4.4.3 | New 4.4.3.1 |
| 3.2.5 | Extend Appendix C.4.2 | New C.4.2.2 |
| 3.2.6 | Extend Section 8.2 + Section 6 | 8.2, 6.X |

### Dependencies from Milestones 1-2

| M3 Issue | Depends On | Reason |
|----------|------------|--------|
| 3.1.1 | 1.1.1 (st_learned_weights) | eps/min_samples stored here |
| 3.1.4 | 1.1.2 (st_feedback_signals) | CLUSTER_WRONG signals |
| 3.2.1 | 1.1.1 (st_learned_weights) | λ modifiers stored here |
| 3.2.3 | 1.1.4 (st_consolidation_audit) | Resurrection logged in audit |
| 3.2.5 | 1.1.2 (st_feedback_signals) | Grounding signals for access patterns |
| 3.2.6 | 1.2.1 (Feature flags) | `P03_FF_DECAY_LEARNING` controls this |

---

## Milestone 4: Formula Learning — R4/R5 Phases

**Goal**: Make R4 (Knowledge Graph) and R5 (Exploration) formulas learnable with closed-loop feedback

---

### Epic 4.1: Novelty Score

**Dossier Location**: Section 4.4.2 (Novelty Scoring), Lines 1176-1186; Appendix C.4
**Primary Formula**: `novelty_score = 1.0 - (duplicate_count / time_window_event_count)`

---

#### Issue 4.1.1: Adaptive Novelty Bonuses

**Read From Whiteboard**:

- Section 6.5.1 (Adaptive Novelty Bonuses) — learning from engagement signals
- Section 6.5.1 Feedback Signals table — grounding, never queried, user references
- Section 6.5.1 bounds — bonuses clamped to [0.05, 0.30]

**Read From Dossier**:

- Section 4.4.2 (Novelty Scoring), Lines 1176-1186 — mentions first-time bonus, milestones
- Section 2.4 (Core Formulas) — novelty bonuses: +0.15 first occurrence, +0.20 milestone, +0.10 rare

**Edit Description**:
Add to Section 4.4.2 new subsection `#### 4.4.2.1 Adaptive Novelty Bonuses`:

**Content to Add**:

1. **Current Static Bonuses**:

   | Event Type | Bonus | When |
   |------------|-------|------|
   | First occurrence | +0.15 | Entity never seen before |
   | Milestone event | +0.20 | Birthday, anniversary, graduation |
   | Rare pattern | +0.10 | Activity < 5 times in 90 days |

2. **Learning Signals**:

   | Signal | Meaning | Adjustment |
   |--------|---------|------------|
   | Novel event grounded in K1 | Useful | Increase +0.01 |
   | Novel event never queried (30d) | Over-prioritized | Decrease -0.02 |
   | User says "this wasn't new" | False positive | Decrease -0.03 |

3. **Bounds**: Bonuses clamped to [0.05, 0.30]
4. **Storage**: `st_learned_weights` with `NOVELTY_PARAMS` type

**Also Add**: Metric `p03_novelty_bonus_applied` to Section 8.2

**Rationale**: Static bonuses may over/under-weight novelty; learn from actual usage.

---

#### Issue 4.1.2: Milestone Detection

**Read From Whiteboard**:

- Section 6.5.2 (Milestone Detection) — three-layer detection: NER, Ontology, Recurrence
- Section 6.5.2 Detection Flow — priority order
- Section 6.5.2 Confidence by Source table — 0.95 for NER+Ontology match

**Read From Dossier**:

- Section 4.4.2 mentions "Milestone event detection" but no details
- No milestone detection algorithm in Appendix C

**Edit Description**:
Add to Appendix C.4 new subsection `#### C.4.X Milestone Event Detection`:

**Content to Add**:

1. **Three-Layer Detection**:

   | Layer | Method | Examples |
   |-------|--------|----------|
   | NER | Extract temporal entities | "birthday", "anniversary" |
   | Ontology | Match entity + date | PERSON.birthday |
   | Recurrence | Detect annual patterns | Same date ±3 days |

2. **Confidence Levels**:

   | Source | Confidence |
   |--------|------------|
   | NER + Ontology | 0.95 |
   | Ontology only | 0.85 |
   | NER only | 0.70 |
   | Recurrence only | 0.60 |

3. **Schema**: Add `milestone_type`, `milestone_confidence` to `st_hipp_events`

**Rationale**: Milestones get +0.20 bonus; need reliable detection to avoid false positives.

---

#### Issue 4.1.3: Adaptive Time Window

**Read From Whiteboard**:

- Section 6.5.3 (Adaptive Time Window) — 12-48h based on activity level
- Section 6.5.3 Daily Event Count table — thresholds for window adjustment

**Read From Dossier**:

- Section 2.4 formula uses fixed 24h window implicitly
- No adaptive window mentioned

**Edit Description**:
Add to Section 4.4.2 new subsection `#### 4.4.2.2 Adaptive Novelty Window`:

**Content to Add**:

1. **Problem**: 24h window arbitrary; high-activity users need shorter, low-activity need longer

2. **Adaptive Rules**:

   | Daily Events | Window | Rationale |
   |--------------|--------|-----------|
   | < 5/day | 48 hours | Low activity, more context |
   | 5-20/day | 24 hours | Default |
   | 20-50/day | 12 hours | High activity |
   | > 50/day | 6 hours | Power user |

3. **Learning**: Track 7-day rolling `events_per_day`, adjust weekly
4. **Storage**: `st_learned_weights` key `novelty_time_window_hours`
5. **Per-Space**: Family members may have different activity levels

**Also Add**: Configuration `P03_NOVELTY_DEFAULT_WINDOW_HOURS` to Section 16 (default: 24)

**Rationale**: Activity-based window prevents novelty score inflation for busy users.

---

### Epic 4.2: SimHash Deduplication

**Dossier Location**: Section 4.4.1 (Deduplication Algorithm), Lines 1170-1175; Appendix C.4.1
**Primary Formula**: `is_near_duplicate = (hamming_distance ≤ 3)`

---

#### Issue 4.2.1: Per-Content-Type Thresholds

**Read From Whiteboard**:

- Section 6.6.1 (Per-Content-Type Thresholds) — threshold matrix by content type
- Section 6.6.1 Learning Process — FP/FN rate based adjustment

**Read From Dossier**:

- Section 4.4.1 — fixed "Hamming distance threshold (≤3)"
- Appendix C.4.1 (SimHash) — `HAMMING_THRESHOLD = 3` hardcoded

**Edit Description**:
Extend Appendix C.4.1 with new subsection `#### C.4.1.1 Content-Type Thresholds`:

**Content to Add**:

1. **Problem**: Structured data needs stricter matching than free-form text

2. **Threshold Matrix**:

   | Content Type | Threshold | Rationale |
   |--------------|-----------|-----------|
   | TRANSACTION | 1 bit | Financial needs exact match |
   | CALENDAR_EVENT | 2 bits | Structured, variations matter |
   | CONTACT_UPDATE | 2 bits | Names/phones match closely |
   | CHAT_MESSAGE | 3 bits | Default, mixed content |
   | PHOTO_CAPTION | 4 bits | Free-form, allow variation |
   | JOURNAL_ENTRY | 4 bits | Personal text, paraphrasing |
   | VOICE_MEMO | 5 bits | Transcription has noise |

3. **Learning Signals**:
   - User unmerges deduped events → FP → increase threshold
   - User manually merges events → FN → decrease threshold

4. **Storage**: `st_learned_weights` with `SIMHASH_PARAMS` type

**Rationale**: One threshold doesn't fit all content types.

---

#### Issue 4.2.2: Two-Stage Deduplication Pipeline

**Read From Whiteboard**:

- Section 6.6.2 (Two-Stage Deduplication) — SimHash first, then embedding
- Section 6.6.2 Decision Matrix — combining SimHash + embedding scores

**Read From Dossier**:

- Appendix C.4.1 — SimHash only, no semantic stage
- Section 2.4 multi-factor similarity mentions embedding but not for dedup

**Edit Description**:
Extend Appendix C.4.1 with new subsection `#### C.4.1.2 Two-Stage Pipeline`:

**Content to Add**:

1. **Problem**: SimHash misses semantic duplicates ("I ate pizza" vs "Had pizza for dinner")

2. **Stage 1 — SimHash (Fast Filter)**:
   - Compute SimHash for all events
   - Group by hamming distance ≤ threshold
   - Output: candidate duplicate pairs (99%+ filtered out)

3. **Stage 2 — Embedding Similarity (Semantic Check)**:
   - For candidate pairs: compute cosine similarity
   - Confirm if similarity ≥ 0.85

4. **Decision Matrix**:

   | SimHash | Embedding | Decision |
   |---------|-----------|----------|
   | ≤ thresh | ≥ 0.85 | DUPLICATE (merge) |
   | ≤ thresh | 0.70-0.85 | LIKELY_DUPLICATE (flag) |
   | ≤ thresh | < 0.70 | NOT_DUPLICATE (false positive) |
   | > thresh | ≥ 0.90 | SEMANTIC_DUPLICATE |

**Also Add**: Column `duplicate_check_method` to `st_hipp_events`

**Rationale**: Two-stage catches both syntactic and semantic duplicates efficiently.

---

#### Issue 4.2.3: MinHash LSH for Scale

**Read From Whiteboard**:

- Section 6.6.3 (Scale Strategy: MinHash LSH) — auto-switch at 50K events
- Section 6.6.3 MinHash parameters — num_hashes=128, num_bands=32

**Read From Dossier**:

- Section 4.4.1 — mentions "MinHash LSH for scale (100K+ events)"
- No implementation details

**Edit Description**:
Extend Appendix C.4.1 with new subsection `#### C.4.1.3 Scale Strategy`:

**Content to Add**:

1. **Transition Logic**:

   | Event Count | Algorithm | Complexity |
   |-------------|-----------|------------|
   | < 10K | SimHash pairwise | O(n²) fast enough |
   | 10K-50K | SimHash + bucketing | O(n × bucket) |
   | > 50K | MinHash LSH | O(n × bands) |

2. **MinHash Parameters**:
   - `num_hashes: 128`
   - `num_bands: 32`
   - `rows_per_band: 4`

3. **Storage**: `st_hipp_events.minhash_signature BYTEA`
4. **Index**: Redis for LSH index, rebuild nightly in R0
5. **Feature Flag**: `P03_FF_MINHASH_LSH`

**Also Add**: Metric `p03_duplicates_detected` to Section 8.2

**Rationale**: O(n²) becomes expensive at scale; MinHash enables large-space dedup.

---

### Epic 4.3: Entity Disambiguation

**Dossier Location**: Section 4.5.1 (Entity Extraction), Lines 1203-1215
**Primary Formula**: `disambiguation_score = 0.7 × embedding_similarity + 0.3 × fuzzy_string_match`

---

#### Issue 4.3.1: Per-Entity-Type Weights

**Read From Whiteboard**:

- Section 6.7.1 (Per-Entity-Type Weights) — weight matrix by entity type
- Section 6.7.1 Learning Process — track corrections, adjust weights

**Read From Dossier**:

- Section 4.5.1 — mentions "Entity deduplication" but fixed formula
- No per-type weights mentioned

**Edit Description**:
Add to Section 4.5.1 new subsection `#### 4.5.1.1 Per-Entity-Type Disambiguation`:

**Content to Add**:

1. **Rationale**: Names need string matching; concepts need semantic matching

2. **Weight Matrix**:

   | Entity Type | Embedding | String | Rationale |
   |-------------|-----------|--------|-----------|
   | PERSON | 0.50 | 0.50 | Names + context |
   | FAMILY_MEMBER | 0.30 | 0.70 | Names specific |
   | PLACE | 0.60 | 0.40 | "Home" vs address |
   | ORGANIZATION | 0.55 | 0.45 | "Google" vs "Alphabet" |
   | THING | 0.80 | 0.20 | "Car" = "vehicle" |
   | CONCEPT | 0.85 | 0.15 | Semantic primary |

3. **Learning**: User corrections → adjust weights for that entity_type
4. **Storage**: `st_learned_weights` with `DISAMBIGUATION_PARAMS` type

**Rationale**: One-size-fits-all weights underperform for specific entity types.

---

#### Issue 4.3.2: Ambiguous Entity Resolution

**Read From Whiteboard**:

- Section 6.7.2 (Ambiguous Entity Handling) — resolution strategy with priority order
- Section 6.7.2 Confidence Thresholds — ≥0.85 auto, 0.60-0.85 flag, <0.60 emit P06
- Section 6.7.2 `st_entity_resolutions` table

**Read From Dossier**:

- Section 4.5.1 — no ambiguity handling
- Section 4.5.5 mentions "Emit to P06" but not for ambiguity

**Edit Description**:
Add to Section 4.5.1 new subsection `#### 4.5.1.2 Ambiguous Entity Resolution`:

**Content to Add**:

1. **Problem**: "John" could be multiple Johns

2. **Resolution Priority**:

   | Priority | Method | Example |
   |----------|--------|---------|
   | 1 | Recent context | Work conversation → coworker John |
   | 2 | Co-occurring entities | With Mary (sister) → brother-in-law |
   | 3 | Location | At "Home" → family member |
   | 4 | Frequency | Most mentioned John |
   | 5 | Emit P06 | AMBIGUOUS_ENTITY gap |

3. **Confidence Actions**:

   | Confidence | Action |
   |------------|--------|
   | ≥ 0.85 | Auto-resolve |
   | 0.60-0.85 | Resolve + flag |
   | < 0.60 | Emit to P06 |

4. **Schema**: Create `st_entity_resolutions` table

**Also Add**: Metric `p03_ambiguous_emitted` to Section 8.2

**Rationale**: Avoid guessing when confidence is low; ask user via P06.

---

#### Issue 4.3.3: Entity Merge with Cascade

**Read From Whiteboard**:

- Section 6.7.4 (Entity Merge Process) — 6-step process
- Section 6.7.4 Cascade Tables — st_kg_edges, st_hipp_events, st_epi, etc.
- Section 6.7.4 `st_entity_merges` table for undo

**Read From Dossier**:

- Section 4.5.1 mentions "Entity deduplication" but no merge details
- No cascade update mechanism documented

**Edit Description**:
Add to Section 4.5.1 new subsection `#### 4.5.1.3 Entity Merge Process`:

**Content to Add**:

1. **Merge Steps**:
   1. Validate: Confirm user intent
   2. Select Primary: Entity with more history
   3. Merge Attributes: Primary wins on conflict
   4. Cascade References: Update all tables
   5. Archive Secondary: Set `archival_status = 'MERGED'`
   6. Log: Record in `st_entity_merges`

2. **Cascade Tables**:

   | Table | Update Method |
   |-------|---------------|
   | st_kg_edges | Redirect source/target_entity_id |
   | st_hipp_events | JSON replace in entities_json |
   | st_epi | Update entity references |
   | st_sem | Update pattern entity links |
   | st_social | Update actor references |

3. **Undo Support**: `st_entity_merges` stores snapshot for reversal

**Also Add**: Metric `p03_entities_merged` to Section 8.2

**Rationale**: Merge is common; must be complete (cascade) and reversible (undo).

---

#### Issue 4.3.4: Disambiguation Confidence Thresholds

**Read From Whiteboard**:

- Section 6.7.3 (Per-Entity-Type Thresholds) — learned thresholds by type
- Section 6.7.3 Learning Signals — merge/split corrections
- Section 6.7.3 Bounds — clamped to learning range

**Read From Dossier**:

- Section 4.5.1 — uses fixed 0.8 threshold implicitly
- No per-type thresholds

**Edit Description**:
Add to Section 4.5.1 new subsection `#### 4.5.1.4 Adaptive Thresholds`:

**Content to Add**:

1. **Per-Type Thresholds**:

   | Entity Type | Initial | Range |
   |-------------|---------|-------|
   | PERSON | 0.85 | [0.80, 0.95] |
   | FAMILY_MEMBER | 0.90 | [0.85, 0.98] |
   | PLACE | 0.75 | [0.65, 0.85] |
   | ORGANIZATION | 0.80 | [0.70, 0.90] |
   | THING | 0.70 | [0.60, 0.80] |
   | CONCEPT | 0.65 | [0.55, 0.75] |

2. **Learning Signals**:
   - User merges entities → threshold too strict → lower by 0.02
   - User splits merged entity → threshold too lenient → raise by 0.03

3. **Bounds**: Thresholds clamped to range to prevent drift

**Rationale**: Family members need stricter matching than concepts.

---

### Epic 4.1/4.2/4.3 Summary: Dossier Locations

| Issue | Insert Location | Section Number |
|-------|-----------------|----------------|
| 4.1.1 | Extend Section 4.4.2 | New 4.4.2.1 |
| 4.1.2 | Extend Appendix C.4 | New C.4.X |
| 4.1.3 | Extend Section 4.4.2 | New 4.4.2.2 |
| 4.2.1 | Extend Appendix C.4.1 | New C.4.1.1 |
| 4.2.2 | Extend Appendix C.4.1 | New C.4.1.2 |
| 4.2.3 | Extend Appendix C.4.1 | New C.4.1.3 |
| 4.3.1 | Extend Section 4.5.1 | New 4.5.1.1 |
| 4.3.2 | Extend Section 4.5.1 | New 4.5.1.2 |
| 4.3.3 | Extend Section 4.5.1 | New 4.5.1.3 |
| 4.3.4 | Extend Section 4.5.1 | New 4.5.1.4 |

### Dependencies from Milestones 1-3

| M4 Issue | Depends On | Reason |
|----------|------------|--------|
| 4.1.1 | 1.1.1 (st_learned_weights) | Novelty bonuses stored here |
| 4.1.1 | 1.1.2 (st_feedback_signals) | Grounding signals for learning |
| 4.2.1 | 1.1.1 (st_learned_weights) | SimHash thresholds stored here |
| 4.2.2 | 3.2.1 (st_vec integration) | Embeddings for Stage 2 |
| 4.3.1 | 1.1.1 (st_learned_weights) | Disambiguation weights stored here |
| 4.3.2 | 1.1.2 (st_feedback_signals) | Resolution feedback |
| 4.3.3 | 1.1.4 (st_consolidation_audit) | Merge logged in audit |

---

### Epic 4.4: Granger Causality

**Dossier Location**: Section 4.5.4 (Causal Inference), Lines 1228-1234
**Primary Formula**: `precedence_ratio = a_before_b / (a_before_b + b_before_a + simultaneous)`

---

#### Issue 4.4.1: Per-Category Causality Thresholds

**Read From Whiteboard**:

- Section 6.8.1 (Adaptive Causality Threshold) — per-relationship-type thresholds
- Section 6.8.1 threshold table — Health=0.85, Financial=0.80, Social=0.70
- Section 6.8.1 Learning Process — track prediction accuracy

**Read From Dossier**:

- Section 4.5.4 (Causal Inference), Lines 1228-1234 — mentions Granger causality
- No threshold mentioned (implicit 0.75 in formulas)

**Edit Description**:
Add to Section 4.5.4 new subsection `#### 4.5.4.1 Adaptive Causality Thresholds`:

**Content to Add**:

1. **Problem**: 0.75 is arbitrary; health decisions need stricter evidence than social patterns

2. **Per-Category Thresholds**:

   | Category | Threshold | Rationale |
   |----------|-----------|-----------|
   | Health/Medical | 0.85 | High stakes, strong evidence |
   | Financial | 0.80 | Important decisions |
   | Social/Routine | 0.70 | Lower stakes |
   | Preference/Habit | 0.65 | Personal patterns, flexible |

3. **Learning Signals**:
   - Causal prediction confirmed → threshold appropriate
   - Causal prediction wrong → raise by 0.02
   - User says "X doesn't cause Y" → raise by 0.05

4. **Storage**: `st_learned_weights` with `CAUSALITY_PARAMS` type

**Also Add**: Metric `p03_causal_edges_created` to Section 8.2

**Rationale**: Medical/financial relationships need higher confidence than social patterns.

---

#### Issue 4.4.2: Observation Count Requirements

**Read From Whiteboard**:

- Section 6.8.2 (Observation Count Requirements) — adaptive by pattern frequency
- Section 6.8.2 Confidence Scaling formula — `sqrt(observations / min_required)`

**Read From Dossier**:

- Section 4.5.4 — no minimum observation count specified
- Implicit assumption of sufficient data

**Edit Description**:
Add to Section 4.5.4 new subsection `#### 4.5.4.2 Observation Requirements`:

**Content to Add**:

1. **Adaptive Requirements by Frequency**:

   | Pattern Frequency | Min Observations | Rationale |
   |-------------------|------------------|-----------|
   | Daily (>0.8/day) | 10 | High frequency needs more |
   | Weekly (0.1-0.8/day) | 5 | Default |
   | Monthly (<0.1/day) | 3 | Rare events, lower bar |
   | Annual (<0.01/day) | 2 | Very rare, weak evidence ok |

2. **Confidence Scaling**:

   ```
   confidence = base_confidence × sqrt(observations / min_required)
   ```

   - Capped at 1.0
   - Extra observations increase confidence

3. **Cold Start**: No causal edges until min observations met

**Rationale**: Rare events shouldn't require same evidence as daily patterns.

---

#### Issue 4.4.3: Confound Detection

**Read From Whiteboard**:

- Section 6.8.3 (Confound Detection) — context conditioning, Simpson's paradox
- Section 6.8.3 Common Cause Detection — C precedes both A and B
- Section 6.8.3 Confound Handling table

**Read From Dossier**:

- Section 4.5.4 mentions "Confidence intervals" but no confound handling
- No Simpson's paradox detection

**Edit Description**:
Add to Section 4.5.4 new subsection `#### 4.5.4.3 Confound Detection`:

**Content to Add**:

1. **Problem**: A→B may actually be C→A and C→B (confounding)

2. **Context Variables** (track co-occurring):
   - Time of day (morning/afternoon/evening/night)
   - Day of week (weekday/weekend)
   - Location (home/work/other)
   - Actor (who was involved)

3. **Simpson's Paradox Check**:
   - If A→B holds globally but reverses in subgroups → confounded
   - Example: "Coffee → Productive" confounded by "Morning"

4. **Common Cause Detection**:
   - If C precedes both A and B in >50% cases → C is confounder candidate

5. **Handling**:

   | Detection | Action |
   |-----------|--------|
   | Strong confounder | Demote to `edge_type = 'CORRELATED'` |
   | Weak signal | Add `confounder_candidates` metadata |
   | No confounders | Confirm as `edge_type = 'CAUSAL'` |

6. **Schema**: Add `causal_confidence`, `confounder_candidates` to `st_kg_edges`

**Also Add**: Metric `p03_confounders_detected` to Section 8.2

**Rationale**: Distinguish correlation from causation for reliable reasoning.

---

#### Issue 4.4.4: Feedback-Based Threshold Adjustment

**Read From Whiteboard**:

- Section 6.8.1 Learning Process — track causal edge usage
- Section 6.8.1 Feedback Signals table — prediction correct/wrong signals

**Read From Dossier**:

- Section 4.5.4 — no feedback mechanism for causal edges
- Section 9 (Integration Contracts) — P04 event patterns

**Edit Description**:
Add to Section 4.5.4 new subsection `#### 4.5.4.4 Causal Edge Feedback`:

**Content to Add**:

1. **Feedback Loop**:
   - P03 creates causal edge with confidence
   - P04/K1 uses edge for prediction/reasoning
   - Outcome recorded in `st_feedback_signals`

2. **Learning Signals**:

   | Signal | Source | Adjustment |
   |--------|--------|------------|
   | Prediction confirmed | K1 response validated | No change |
   | Prediction wrong | K1 response corrected | Raise threshold +0.02 |
   | User rejects causation | Explicit feedback | Raise threshold +0.05 |
   | Missed causation | User reports pattern | Lower threshold -0.03 |

3. **Edge Updates**:
   - If prediction accuracy < 70% over 30 days → demote to CORRELATED
   - If accuracy > 90% → boost `causal_confidence`

4. **Storage**: Track edge usage in `st_causal_feedback` (new table)

**Rationale**: Causal edges should improve over time based on prediction accuracy.

---

### Epic 4.5: UCT/MCTS (Dream Exploration)

**Dossier Location**: Section 4.6 (R5 Dream-Like Exploration), Lines 1240-1268
**Primary Formula**: `UCT = Q/N + c × √(ln(N_parent) / N)`

---

#### Issue 4.5.1: Feature Flag (Disabled MVP)

**Read From Whiteboard**:

- Section 6.9.3 (MVP Feature Flag Strategy) — disabled for MVP
- Section 6.9.3 Post-MVP Rollout Plan — shadow → enabled_low → enabled
- Section 6.9.3 Shadow Mode Validation — compare MCTS vs heuristic

**Read From Dossier**:

- Section 4.6 (R5) — full MCTS spec documented
- Section 12 (Feature Flags) — flag patterns
- No MVP disable mention

**Edit Description**:
Add to Section 4.6 new subsection `#### 4.6.0 MVP Strategy`:

**Content to Add**:

1. **Decision**: R5 disabled for MVP via `P03_FF_R5_MODE=disabled`

2. **MVP Behavior** (R5 skipped):
   - Use heuristic scoring instead of MCTS
   - Decisions based on direct formula outputs
   - No exploration/exploitation tradeoff

3. **Rollout Plan**:

   | Phase | Mode | Duration |
   |-------|------|----------|
   | MVP | `disabled` | Initial launch |
   | Alpha | `shadow` | Run but don't apply |
   | Beta | `enabled_low` | 10 rollouts only |
   | GA | `enabled` | Full adaptive |

4. **Shadow Validation**:
   - Track "Would MCTS differ from heuristic?"
   - If differs >20% AND user corrections favor MCTS → enable
   - If matches >95% → keep disabled (not worth compute)

**Also Add**: Feature flag `P03_FF_R5_MODE` to Section 12.4

**Rationale**: MCTS is compute-intensive; validate benefit before enabling.

---

#### Issue 4.5.2: Adaptive Rollout Count

**Read From Whiteboard**:

- Section 6.9.2 (Adaptive Rollout Count) — decision importance classification
- Section 6.9.2 rollout table — merge=100, causal=50, reinforce=20, decay=10
- Section 6.9.2 Early Termination — stop if clear winner

**Read From Dossier**:

- Section 4.6.2 (Forward Simulation) — mentions MCTS but fixed rollouts
- No adaptive rollout specification

**Edit Description**:
Add to Section 4.6.2 new subsection `#### 4.6.2.1 Adaptive Rollouts`:

**Content to Add**:

1. **Decision Importance → Rollouts**:

   | Decision Type | Rollouts | Rationale |
   |---------------|----------|-----------|
   | Entity merge/split | 100 | High impact, irreversible |
   | Causal edge creation | 50 | Important for reasoning |
   | Memory reinforcement | 20 | Lower stakes |
   | Decay parameter tuning | 10 | Reversible |

2. **Early Termination**:
   - Stop if best action has >90% of visits
   - Stop if CI width <5% uncertainty

3. **Compute Budget**: 1000 total rollouts per P03 cycle (<5% compute)

4. **Storage**: Track rollout allocation in `st_mcts_decisions`

**Also Add**: Metric `p03_mcts_rollouts` to Section 8.2

**Rationale**: Allocate compute to high-impact decisions; save on reversible ones.

---

#### Issue 4.5.3: Exploration Constant Decision

**Read From Whiteboard**:

- Section 6.9.1 (Exploration Constant Decision) — keep c=√2 static
- Section 6.9.1 Rationale — theoretically optimal, tuning adds complexity

**Read From Dossier**:

- Section 4.6.2 — no exploration constant specified
- Appendix C.6 (if exists) — UCT formula

**Edit Description**:
Add to Section 4.6.2 new subsection `#### 4.6.2.2 Exploration Constant`:

**Content to Add**:

1. **Decision**: Keep `c = √2 ≈ 1.414` static

2. **Rationale**:
   - √2 is theoretically optimal (Kocsis & Szepesvári, 2006)
   - Tuning adds complexity with minimal benefit
   - Memory consolidation use case suits default

3. **Alternative Rejected**: Adaptive c based on search depth
   - Would add complexity
   - Theoretical gains unclear
   - Reserved for future: `P03_FF_ADAPTIVE_UCT_C`

4. **Formula**: `UCT = Q/N + 1.414 × √(ln(N_parent) / N)`

**Rationale**: Use proven theoretical optimum; don't over-engineer.

---

#### Issue 4.5.4: Shadow Mode Comparison

**Read From Whiteboard**:

- Section 6.9.3 Shadow Mode Validation — compare MCTS to heuristic
- Section 6.9.3 enabling criteria — differs >20% AND better outcomes

**Read From Dossier**:

- Section 12.4.3 (Shadow Mode Specification) — general shadow pattern
- No MCTS-specific shadow comparison

**Edit Description**:
Add to Section 4.6 new subsection `#### 4.6.5 Shadow Mode Validation`:

**Content to Add**:

1. **When `P03_FF_R5_MODE=shadow`**:
   - Run both heuristic AND MCTS for each decision
   - Apply heuristic result (MCTS is read-only)
   - Log comparison to `st_mcts_shadow_log`

2. **Comparison Metrics**:

   | Metric | Threshold | Action |
   |--------|-----------|--------|
   | Decision agreement | >95% | Keep disabled (MCTS not useful) |
   | MCTS better (30d) | >55% | Promote to `enabled_low` |
   | MCTS worse (30d) | >55% | Keep disabled |

3. **"Better" Definition**:
   - Memory grounded more often
   - Fewer user corrections
   - Higher downstream satisfaction

4. **Schema**: `st_mcts_shadow_log` with:
   - `decision_id`, `heuristic_choice`, `mcts_choice`, `outcome`, `created_at`

**Also Add**: Metric `p03_mcts_vs_heuristic_diff` to Section 8.2

**Rationale**: Validate MCTS benefit with real data before enabling compute cost.

---

### Epic 4.4/4.5 Summary: Dossier Locations

| Issue | Insert Location | Section Number |
|-------|-----------------|----------------|
| 4.4.1 | Extend Section 4.5.4 | New 4.5.4.1 |
| 4.4.2 | Extend Section 4.5.4 | New 4.5.4.2 |
| 4.4.3 | Extend Section 4.5.4 | New 4.5.4.3 |
| 4.4.4 | Extend Section 4.5.4 | New 4.5.4.4 |
| 4.5.1 | Extend Section 4.6 | New 4.6.0 |
| 4.5.2 | Extend Section 4.6.2 | New 4.6.2.1 |
| 4.5.3 | Extend Section 4.6.2 | New 4.6.2.2 |
| 4.5.4 | Extend Section 4.6 | New 4.6.5 |

### Epic 4.4/4.5 Dependencies

| M4 Issue | Depends On | Reason |
|----------|------------|--------|
| 4.4.1 | 1.1.1 (st_learned_weights) | Causality thresholds stored here |
| 4.4.3 | 1.1.2 (st_feedback_signals) | Causal prediction feedback |
| 4.4.4 | 1.1.4 (st_consolidation_audit) | Edge decisions logged |
| 4.5.1 | 1.2.1 (Feature flags) | `P03_FF_R5_MODE` flag |
| 4.5.4 | 1.2.2 (Shadow mode) | Shadow comparison infrastructure |

---

## Milestone 5: Formula Learning — Reconciliation

**Goal**: Make reconciliation thresholds and similarity formulas learnable with closed-loop feedback

---

### Epic 5.1: Multi-Factor Similarity

**Dossier Location**: Section 1.4 (Reconciliation Algorithm), Lines 393-530; Section 2.4 (Core Formulas)
**Primary Formula**: `similarity = 0.40×semantic + 0.25×simhash + 0.15×entity + 0.10×temporal + 0.10×spatial`

---

#### Issue 5.1.1: Per-Layer Weight Vectors

**Read From Whiteboard**:

- Section 6.10.1 (Per-Layer Weight Vectors) — different layers value different factors
- Section 6.10.1 Default Weight Matrix — st_epi emphasizes temporal, st_sem emphasizes semantic
- Section 6.10.1 Learning Process — track which factor contributed to matches

**Read From Dossier**:

- Section 2.4 (Core Formulas), Lines 700-710 — single static weight vector
- Section 1.4 `compute_similarity()` — no per-layer differentiation

**Edit Description**:
Add to Section 1.4 new subsection `#### 1.4.1 Per-Layer Similarity Weights`:

**Content to Add**:

1. **Rationale**: Different memory types value different factors

2. **Layer-Specific Weights**:

   | Layer | Semantic | SimHash | Entity | Temporal | Spatial |
   |-------|----------|---------|--------|----------|---------|
   | st_epi | 0.30 | 0.15 | 0.15 | **0.25** | **0.15** |
   | st_sem | **0.50** | 0.20 | 0.15 | 0.10 | 0.05 |
   | st_procedural | 0.25 | 0.15 | 0.20 | **0.30** | 0.10 |
   | st_social | 0.35 | 0.10 | **0.35** | 0.10 | 0.10 |
   | st_kg_dom | **0.45** | 0.25 | 0.15 | 0.10 | 0.05 |

3. **Learning**: Track which factor "mattered" for correct matches
4. **Normalization**: Weights sum to 1.0, enforced on update
5. **Storage**: `st_learned_weights` with `SIMILARITY_WEIGHTS_{layer}` type

**Also Add**: Metric `p03_similarity_factor_contribution` to Section 8.2

**Rationale**: Episodic memory cares about when/where; semantic cares about meaning.

---

#### Issue 5.1.2: Golden Dataset Validation

**Read From Whiteboard**:

- Section 6.10.2 (Threshold Validation Strategy) — Approach 2: Golden Dataset
- Section 6.10.2 Validation Metrics table — Precision >0.90, Recall >0.85, F1 >0.87
- Section 6.10.2 Validation Schedule — weekly against golden dataset

**Read From Dossier**:

- Section 10 (Testing) — test patterns but no golden dataset for similarity
- No offline validation for reconciliation mentioned

**Edit Description**:
Add to Section 10 new subsection `#### 10.X Reconciliation Golden Dataset`:

**Content to Add**:

1. **Dataset Components**:

   | Component | Purpose | Size |
   |-----------|---------|------|
   | Known duplicates | True positives — should match | 500+ pairs |
   | Known distinct | True negatives — should not match | 500+ pairs |
   | Edge cases | Boundary testing | 200+ pairs |

2. **Validation Metrics**:

   | Metric | Target | Alert Threshold |
   |--------|--------|-----------------|
   | Precision | > 0.90 | < 0.85 |
   | Recall | > 0.85 | < 0.80 |
   | F1 Score | > 0.87 | < 0.82 |

3. **Schedule**: Weekly validation job, results to `st_validation_results`
4. **Drift Detection**: Alert if F1 drops >5% week-over-week

**Also Add**: Configuration `P03_GOLDEN_DATASET_PATH` to Section 16

**Rationale**: Offline validation catches drift before it affects users.

---

#### Issue 5.1.3: Online Weight Adjustment

**Read From Whiteboard**:

- Section 6.10.2 (Threshold Validation Strategy) — Approach 1: Implicit Feedback
- Section 6.10.2 Signal table — match used, match rejected, user manually links

**Read From Dossier**:

- Section 1.4 — no online learning for similarity weights
- Section 9 (Integration Contracts) — feedback event patterns

**Edit Description**:
Add to Section 1.4 new subsection `#### 1.4.2 Online Weight Learning`:

**Content to Add**:

1. **Feedback Signals**:

   | Signal | Meaning | Adjustment |
   |--------|---------|------------|
   | Match used in K1 | Similarity correct | Boost contributing factors |
   | Match rejected by user | False positive | Reduce dominant factor |
   | User manually links | Missed match | Boost weak factors |
   | Reformulation after response | Possible bad match | Review decision |

2. **Update Rule**:
   - Identify which factor(s) contributed most to decision
   - On success: boost those factors by 0.02
   - On failure: reduce those factors by 0.03
   - Re-normalize to sum=1.0

3. **Momentum**: 0.9 for stability (same as other learning)
4. **Bounds**: Each factor clamped to [0.05, 0.60]

**Rationale**: Continuous learning from actual usage patterns.

---

#### Issue 5.1.4: Per-Entity-Type Similarity

**Read From Whiteboard**:

- Section 6.10.3 (Per-Entity-Type Thresholds) — PERSON needs 0.90, CONCEPT needs 0.70
- Section 6.10.3 Entity-Type Threshold Matrix — per-type REINFORCE/EXTEND/CREATE thresholds

**Read From Dossier**:

- Section 1.4 — fixed thresholds (0.85, 0.60) for all types
- No entity-type differentiation

**Edit Description**:
Add to Section 1.4 new subsection `#### 1.4.3 Entity-Type Similarity Thresholds`:

**Content to Add**:

1. **Problem**: Matching "John Smith" requires higher precision than "meeting"

2. **Per-Type Thresholds**:

   | Entity Type | REINFORCE (>) | EXTEND (range) | CREATE (<) |
   |-------------|---------------|----------------|------------|
   | PERSON | 0.90 | 0.70-0.90 | 0.70 |
   | FAMILY_MEMBER | 0.95 | 0.80-0.95 | 0.80 |
   | PLACE | 0.80 | 0.55-0.80 | 0.55 |
   | ORGANIZATION | 0.85 | 0.65-0.85 | 0.65 |
   | EVENT | 0.80 | 0.55-0.80 | 0.55 |
   | THING | 0.75 | 0.50-0.75 | 0.50 |
   | CONCEPT | 0.70 | 0.45-0.70 | 0.45 |

3. **Learning**: Track FP/FN rates per entity_type, adjust thresholds
4. **Per-Space**: Different families have different naming patterns

**Rationale**: Family members need stricter matching; concepts can be looser.

---

### Epic 5.2: Reconciliation Thresholds

**Dossier Location**: Section 1.4, Lines 425-470; Appendix F.1 (Thresholds)
**Primary Thresholds**: `REINFORCE > 0.85`, `EXTEND 0.60-0.85`, `CREATE < 0.60`

---

#### Issue 5.2.1: Thompson Sampling Integration

**Read From Whiteboard**:

- Section 6.11.1 (Threshold Learning Strategy) — use Thompson Sampling
- Section 6.12 (Thompson Sampling) — Beta-Bernoulli model
- Section 6.12.4 (Exploration vs Exploitation) — natural via posterior sampling

**Read From Dossier**:

- Section 1.4 lines 425-430 — hardcoded `if best_similarity > 0.85`
- No learning mechanism for thresholds

**Edit Description**:
Add to Section 1.4 new subsection `#### 1.4.4 Thompson Sampling for Thresholds`:

**Content to Add**:

1. **Problem**: 0.85 and 0.60 are arbitrary magic numbers

2. **Solution**: Learn optimal thresholds via Thompson Sampling

3. **Threshold Model**:

   | Threshold | Prior | E[x] |
   |-----------|-------|------|
   | REINFORCE | Beta(17, 3) | 0.85 |
   | EXTEND_LOWER | Beta(12, 8) | 0.60 |

4. **Learning Loop**:
   - Sample threshold from Beta posterior
   - Make reconciliation decision
   - Observe outcome (was decision correct?)
   - Update Beta parameters

5. **Why Thompson Sampling**:
   - Natural exploration/exploitation balance
   - Handles non-stationary user preferences
   - Simple Beta-Bernoulli conjugate model

**Also Add**: Metric `p03_threshold_reinforce` to Section 8.2

**Rationale**: Replace magic numbers with data-driven thresholds.

---

#### Issue 5.2.2: Per-Space Threshold Isolation

**Read From Whiteboard**:

- Section 6.11.4 (Per-Space with Global Fallback) — hierarchy
- Section 6.11.4 Storage Structure — per-space Beta parameters

**Read From Dossier**:

- Section 1.4 — global thresholds, no per-space
- Section 14.2 (Privacy) — per-space isolation patterns

**Edit Description**:
Add to Section 1.4 new subsection `#### 1.4.5 Per-Space Threshold Isolation`:

**Content to Add**:

1. **Hierarchy**:

   ```
   Space threshold (if 100+ signals)
       ↓ fallback
   Global threshold (aggregated)
       ↓ fallback
   Static defaults (0.85, 0.60)
   ```

2. **Per-Space Storage**:
   - `reconcile_reinforce_alpha_{space_id}`
   - `reconcile_reinforce_beta_{space_id}`
   - `reconcile_extend_lower_alpha_{space_id}`

3. **Global Aggregation**: Pool counts nightly (privacy-safe: only counts)
4. **No Cross-Space Leakage**: Family patterns differ from work patterns

**Rationale**: Each space learns its own thresholds; new spaces use global.

---

#### Issue 5.2.3: Beta Prior Initialization

**Read From Whiteboard**:

- Section 6.12.1 (Prior Selection) — encode static thresholds as priors
- Section 6.12.1 Prior Construction table — Beta(17,3) for 0.85

**Read From Dossier**:

- No Bayesian priors mentioned
- Appendix F.1 — static thresholds only

**Edit Description**:
Add to Appendix F.1 new subsection `#### F.1.1 Bayesian Prior Configuration`:

**Content to Add**:

1. **Prior Construction**:

   | Threshold | Target | Prior | Effective Samples |
   |-----------|--------|-------|-------------------|
   | REINFORCE | 0.85 | Beta(17, 3) | 20 |
   | EXTEND_LOWER | 0.60 | Beta(12, 8) | 20 |

2. **Why α+β=20**:
   - Moderate confidence in prior
   - ~50 signals to shift threshold by 0.05
   - Balances stability vs adaptability

3. **Prior Strength Tradeoff**:
   - Stronger (higher α+β): slower to adapt, more stable
   - Weaker (lower α+β): faster to adapt, less stable

**Rationale**: Informative priors encode current best practice.

---

#### Issue 5.2.4: Success/Failure Criteria

**Read From Whiteboard**:

- Section 6.12.2 (Success Definition) — criteria per decision type
- Section 6.12.2 table — REINFORCE success = memory grounded without correction

**Read From Dossier**:

- Section 1.4 — no success tracking for decisions
- Section 9 — feedback signal patterns

**Edit Description**:
Add to Section 1.4 new subsection `#### 1.4.6 Decision Outcome Tracking`:

**Content to Add**:

1. **Success Criteria**:

   | Decision | Success | Failure | Window |
   |----------|---------|---------|--------|
   | REINFORCE | Memory grounded in K1 | User corrects | 7 days |
   | EXTEND | Extended version used | User reverts | 7 days |
   | CREATE | Stays distinct | User merges | 30 days |
   | CONTRADICT | Resolution accepted | User rejects | 7 days |

2. **Signal Collection**:
   - Log decision with `decision_id` and threshold used
   - Track memory over observation window
   - Check `st_feedback_signals` for outcomes
   - Update Beta parameters accordingly

3. **Delayed Feedback**: Nightly batch processes delayed signals

**Also Add**: Column `decision_id` to `st_consolidation_audit`

**Rationale**: Clear success criteria enable Thompson Sampling to learn.

---

#### Issue 5.2.5: Cold Start Strategy

**Read From Whiteboard**:

- Section 6.11.3 (Cold Start Strategy) — phases based on signal count
- Section 6.11.3 table — Cold (<100), Warm (100-500), Hot (>500)

**Read From Dossier**:

- No cold start handling for thresholds
- Section 1.4 uses static values always

**Edit Description**:
Add to Section 1.4 new subsection `#### 1.4.7 Threshold Cold Start`:

**Content to Add**:

1. **Cold Start Phases**:

   | Phase | Signals | Behavior |
   |-------|---------|----------|
   | Cold | < 100 | Use static defaults (0.85, 0.60) |
   | Warm | 100-500 | Thompson Sampling, wide exploration |
   | Hot | > 500 | Thompson Sampling, exploitation focus |

2. **Transition Logic**:
   - Cold: `threshold = static_default`
   - Warm: `threshold = sample_beta(α_prior + successes, β_prior + failures)`
   - Hot: Full posterior sampling

3. **Per-Space Tracking**: `signal_count` per space in `st_learned_weights`

**Rationale**: Use proven defaults until sufficient feedback accumulates.

---

#### Issue 5.2.6: Stability Bounds and Alerts

**Read From Whiteboard**:

- Section 6.11.2 (Adaptation Speed) — momentum=0.9, stability bounds
- Section 6.11.2 Stability Bounds — [0.75, 0.95] for REINFORCE

**Read From Dossier**:

- No threshold bounds mentioned
- Section 17.3 (Alerting) — alert patterns

**Edit Description**:
Add to Section 1.4 new subsection `#### 1.4.8 Threshold Stability`:

**Content to Add**:

1. **Momentum Update**:

   ```
   new_α = 0.9 × old_α + 0.1 × success_count
   new_β = 0.9 × old_β + 0.1 × failure_count
   ```

2. **Stability Bounds**:

   | Threshold | Lower | Upper |
   |-----------|-------|-------|
   | REINFORCE | 0.75 | 0.95 |
   | EXTEND_LOWER | 0.45 | 0.75 |

3. **Bound Alerts**:
   - If threshold hits bound → emit alert
   - May indicate data quality issue or concept drift

4. **Rollback**: If quality degrades 3 consecutive days → revert to prior

**Also Add**: Alert `ThresholdBoundHit` to Section 17.3

**Rationale**: Prevent runaway learning; maintain operational stability.

---

### Epic 5.1/5.2 Summary: Dossier Locations

| Issue | Insert Location | Section Number |
|-------|-----------------|----------------|
| 5.1.1 | Extend Section 1.4 | New 1.4.1 |
| 5.1.2 | Extend Section 10 | New 10.X |
| 5.1.3 | Extend Section 1.4 | New 1.4.2 |
| 5.1.4 | Extend Section 1.4 | New 1.4.3 |
| 5.2.1 | Extend Section 1.4 | New 1.4.4 |
| 5.2.2 | Extend Section 1.4 | New 1.4.5 |
| 5.2.3 | Extend Appendix F.1 | New F.1.1 |
| 5.2.4 | Extend Section 1.4 | New 1.4.6 |
| 5.2.5 | Extend Section 1.4 | New 1.4.7 |
| 5.2.6 | Extend Section 1.4 | New 1.4.8 |

### Dependencies from Milestones 1-4

| M5 Issue | Depends On | Reason |
|----------|------------|--------|
| 5.1.1 | 1.1.1 (st_learned_weights) | Similarity weights stored here |
| 5.1.3 | 1.1.2 (st_feedback_signals) | Online feedback source |
| 5.2.1 | 1.1.1 (st_learned_weights) | Beta parameters stored here |
| 5.2.2 | 1.2.4 (Per-space flags) | Isolation infrastructure |
| 5.2.4 | 1.1.4 (st_consolidation_audit) | Decision tracking |
| 5.2.6 | 1.2.1 (Feature flags) | `P03_FF_SIMILARITY_LEARNING` |

---

## Milestone 6: Feedback Collection & Learning

**Goal**: Implement feedback collection, implicit signals, and regret tracking

---

### Epic 6.1: Per-Entity Decay Calibration

**Dossier Location**: Section 4.4 (R3 Decay), Appendix C.4 (R3 Algorithms)
**Primary Goal**: Learn individual decay rates (λ) per entity based on access patterns

---

#### Issue 6.1.1: Minimum Access Requirements

**Read From Whiteboard**:

- Section 6.13.1 (Minimum Data) — 5+ accesses with >7 day spread
- Section 6.13.1 Access Tracking table — access_count, first_access_at columns

**Read From Dossier**:

- Section 4.4 (R3 Decay) — applies uniform decay_factor per entity-type
- No per-entity access tracking exists

**Edit Description**:
Add to Section 4.4 new subsection `#### 4.4.1 Per-Entity Access Tracking`:

**Content to Add**:

1. **Access Requirements**:

   | Requirement | Value | Rationale |
   |-------------|-------|-----------|
   | Minimum accesses | 5 | Statistical significance |
   | Minimum spread | 7 days | Avoid bursty skew |
   | Distribution check | χ² goodness-of-fit | Ensure exponential fit |

2. **Access Tracking Columns** (on entity tables):
   - `access_count INTEGER DEFAULT 0`
   - `first_access_at BIGINT`
   - `last_access_at BIGINT`

3. **Increment Logic**: On every P04 (Query) that retrieves entity
4. **Spread Calculation**: `(last_access_at - first_access_at) >= 7 days`

**Also Add**: Migration for access tracking columns

**Rationale**: Need sufficient data before learning per-entity λ.

---

#### Issue 6.1.2: Bayesian Lambda Estimation

**Read From Whiteboard**:

- Section 6.13.2 (Bayesian Estimation) — Gamma-Exponential conjugate model
- Section 6.13.2 Prior Construction table — entity-type priors
- Section 6.13.2 Confidence-Based Application — CI width thresholds

**Read From Dossier**:

- Section 4.4 — static λ values from entity-type defaults
- No Bayesian updating mechanism

**Edit Description**:
Add to Appendix C.4 new subsection `#### C.4.1 Bayesian Lambda Estimation`:

**Content to Add**:

1. **Conjugate Model**: Gamma-Exponential

   | Component | Distribution | Parameters |
   |-----------|--------------|------------|
   | Prior on λ | Gamma(α₀, β₀) | Entity-type defaults |
   | Likelihood | Exponential(λ) | Inter-access intervals |
   | Posterior | Gamma(α₀+n, β₀+Σxᵢ) | Closed-form update |

2. **Entity-Type Priors**:

   | Entity Type | Default λ | α₀ | β₀ |
   |-------------|-----------|-----|-----|
   | PERSON | 0.002 | 2 | 1000 |
   | FAMILY_MEMBER | 0.001 | 2 | 2000 |
   | PLACE | 0.003 | 2 | 667 |
   | THING | 0.005 | 2 | 400 |
   | CONCEPT | 0.004 | 2 | 500 |

3. **Update Process**:
   - Collect inter-access intervals [x₁, x₂, ..., xₙ] in days
   - Update: α_post = α₀ + n, β_post = β₀ + Σxᵢ
   - Point estimate: λ_mean = α_post / β_post

4. **Confidence-Based Application**:

   | CI Width | Action |
   |----------|--------|
   | Narrow (< 20% of mean) | Use learned λ directly |
   | Moderate (20-50%) | Blend with default |
   | Wide (> 50%) | Use default, continue collecting |

**Also Add**: Metric `p03_per_entity_lambda_fitted` to Section 8.2

**Rationale**: Bayesian estimation provides uncertainty quantification and graceful degradation.

---

#### Issue 6.1.3: Hierarchical Fallback

**Read From Whiteboard**:

- Section 6.13.3 (Hierarchical Fallback) — 4-level hierarchy
- Section 6.13.3 Examples table — when each level applies
- Section 6.13.3 Warm-Up Period — 30 days before aggressive decay

**Read From Dossier**:

- Section 4.4 — flat entity-type defaults, no hierarchy
- DECAY_CONFIGS static structure

**Edit Description**:
Add to Appendix C.4 new subsection `#### C.4.2 Lambda Fallback Hierarchy`:

**Content to Add**:

1. **Fallback Chain**:

   ```
   Per-entity λ (if 5+ accesses, good spread)
       ↓ fallback
   Per-entity-type λ (space-specific, learned)
       ↓ fallback
   Global entity-type λ (from DECAY_CONFIGS)
       ↓ fallback
   Layer default λ (from layer configuration)
   ```

2. **Selection Logic**:

   | Entity Situation | λ Used |
   |------------------|--------|
   | "Mom" with 20 accesses | Per-entity: 0.0008 |
   | "Dr. Smith" with 3 accesses | Per-entity-type: 0.002 |
   | "New Restaurant" with 0 accesses | Global PLACE: 0.003 |

3. **Warm-Up Period**:
   - New entities inherit from entity-type for 30 days
   - After 30 days, if < 5 accesses → entity is unimportant
   - Apply aggressive decay (1.5× default λ) to low-access entities

**Rationale**: Graceful degradation from personalized to global defaults.

---

### Epic 6.2: Query Regret Tracking

**Dossier Location**: Section 4.4 (R3), Appendix C.4 (R3 Algorithms), Section 6 (Storage)
**Primary Goal**: Detect when pruned entities are later queried (regret signal)

---

#### Issue 6.2.1: 14-Day Tracking Window

**Read From Whiteboard**:

- Section 6.14.1 (Regret Tracking Window) — 14 days chosen
- Section 6.14.1 Storage Strategy table — what to retain
- Section 6.14.1 Cleanup Job — nightly deletion

**Read From Dossier**:

- Section 4.4 (R3 Decay) — no regret tracking mentioned
- Section 6 (Storage) — no st_pruned_entities table

**Edit Description**:
Add to Section 4.4 new subsection `#### 4.4.2 Pruning Regret Detection`:

**Content to Add**:

1. **Window Duration**: 14 days

   | Window | Pros | Cons |
   |--------|------|------|
   | 7 days | Lower storage | Miss weekly patterns |
   | 14 days | Catches weekly + biweekly | Moderate storage |
   | 30 days | Very comprehensive | High storage, stale |

2. **Rationale for 14 Days**:
   - Captures weekly patterns (same-day queries)
   - Captures biweekly patterns (payday, meetings)
   - Manageable storage overhead
   - After 14 days, if not queried → pruning was correct

3. **Storage Retention**:

   | Data | Retention | Location |
   |------|-----------|----------|
   | Pruned embedding | 14 days | st_pruned_entities |
   | Pruned name | 14 days | st_pruned_entities |
   | Match events | 30 days | st_feedback_signals |

4. **Cleanup**: Nightly job deletes entries > 14 days

**Also Add**: Metric `p03_prune_regrets` to Section 8.2

**Rationale**: Track regret without infinite storage growth.

---

#### Issue 6.2.2: Query-to-Pruned Matching

**Read From Whiteboard**:

- Section 6.14.2 (Query-to-Pruned Matching) — two-stage matching
- Section 6.14.2 Match Decision table — thresholds
- Section 6.14.2 Context Boost — same-space boost

**Read From Dossier**:

- No query-to-pruned matching exists
- Section 6 — pgvector capabilities available

**Edit Description**:
Add to Appendix C.4 new subsection `#### C.4.3 Query-Pruned Matching Algorithm`:

**Content to Add**:

1. **Two-Stage Matching**:

   | Stage | Method | Threshold |
   |-------|--------|-----------|
   | Name match | Fuzzy (Levenshtein + token) | > 0.70 |
   | Semantic match | Embedding cosine | > 0.75 |

2. **Match Decision**:

   | Name Match | Embedding Match | Decision |
   |------------|-----------------|----------|
   | > 0.70 | > 0.75 | STRONG_MATCH → regret signal |
   | > 0.70 | 0.60-0.75 | LIKELY_MATCH → weak regret |
   | < 0.70 | > 0.85 | SEMANTIC_MATCH → regret signal |
   | < 0.70 | < 0.85 | NO_MATCH |

3. **Context Boost**:
   - Same space as pruned → +0.10
   - Same actor mentioned → +0.05
   - Same time window → +0.03

4. **Efficient Matching**:
   - Index pruned embeddings in pgvector
   - On query, search top-5 nearest pruned
   - Run name match on candidates only

**Rationale**: "Mom's birthday" should match pruned "Mother's birthday reminder".

---

#### Issue 6.2.3: Regret Signal Weighting

**Read From Whiteboard**:

- Section 6.14.3 (Regret Signal Weight) — 0.90 confidence
- Section 6.14.3 Signal Processing table — actions per regret type
- Section 6.14.3 Anti-Gaming — rate limits

**Read From Dossier**:

- No regret signals defined
- st_feedback_signals can accept new signal types

**Edit Description**:
Add to Appendix C.4 new subsection `#### C.4.4 Regret Signal Processing`:

**Content to Add**:

1. **Base Confidence**: 0.90 (very high — clear mistake)

2. **Signal Processing**:

   | Regret Type | Confidence | Action |
   |-------------|------------|--------|
   | STRONG_MATCH | 0.90 | Lower λ for entity type by 10% |
   | LIKELY_MATCH | 0.70 | Lower λ by 5%, flag for review |
   | Multiple (same type) | 0.95 | Alert: threshold too aggressive |

3. **Feedback Loop**:

   ```
   Pruning → st_pruned_entities → Query arrives
                                       ↓
                              Match against pruned?
                                       ↓
                              YES → REGRET signal
                                       ↓
                              Lower λ or raise threshold
   ```

4. **Anti-Gaming**:
   - Max 10 regret signals per entity-type per day
   - If regret rate > 20% of pruning rate → alert

**Rationale**: Pruning entity user later needs is a clear signal to lower decay.

---

#### Issue 6.2.4: st_pruned_entities Table

**Read From Whiteboard**:

- Section 6.14.4 (st_pruned_entities Table) — schema
- Section 6.14.5 Implementation Checklist — pgvector integration

**Read From Dossier**:

- Section 6 (Storage Schema) — no pruned tracking table
- pgvector enabled for embeddings

**Edit Description**:
Add to Section 6 new subsection `#### 6.X.X st_pruned_entities`:

**Content to Add**:

1. **Table Schema**:

   | Column | Type | Purpose |
   |--------|------|---------|
   | prune_id | TEXT PK | Primary key |
   | entity_id | TEXT | Original entity ID |
   | entity_type | TEXT | PERSON, PLACE, etc. |
   | canonical_name | TEXT | For name matching |
   | embedding | VECTOR(1024) | For semantic matching |
   | space_id | TEXT | Isolation |
   | decay_factor_at_prune | REAL | Decay when pruned |
   | pruned_at | BIGINT | Timestamp |
   | matched_query_id | TEXT | If regret detected |
   | matched_at | BIGINT | When regret detected |

2. **Indexes**:
   - `idx_pruned_space_time` on (space_id, pruned_at)
   - `idx_pruned_embedding` using ivfflat on embedding

3. **RLS**: Row-level security by space_id
4. **Cleanup**: Nightly job deletes rows > 14 days

**Also Add**: Hook in R3 pruning to insert into st_pruned_entities

**Rationale**: Enable efficient query-time matching against recently pruned entities.

---

### Epic 6.3: P03 Feedback Handler Implementation

**Dossier Location**: Section 9 (Integration Contracts), Appendix C
**Primary Goal**: P03 subscribes to P21 feedback system and processes signals

> **IMPORTANT**: Reformulation detection, abandonment detection, and adversarial handling
> are implemented by **K1 + P21 Feedback Pipeline** (see PLAN-feedback-pipeline-system.md).
> P03 is a **CONSUMER** of these signals, not the producer.

---

#### Issue 6.3.1: P03FeedbackHandler Subscription

**Read From Whiteboard**:

- Section 3.5: "P03 needs to consume `feedback.signal.P03` topic"
- Section 6.15 — signal types P03 should handle

**Read From External Plan**:

- [PLAN-feedback-pipeline-system.md](./PLAN-feedback-pipeline-system.md) M3 Epic 3.1 (FEEDBACK-012)
- P03FeedbackHandler subscribes to `feedback.signal.p03`
- K1 detects reformulation/abandonment (FEEDBACK-008, FEEDBACK-009)

**Edit Description**:
Add to Section 9 new subsection `#### 9.X P03 Feedback Handler`:

**Content to Add**:

1. **Bus Subscription**: `feedback.signal.p03`

2. **Signal Types Handled**:

   | Signal Type | P21 Producer | P03 Action |
   |-------------|--------------|------------|
   | SALIENCE_ADJUSTMENT | K1 CorrectionParser | Adjust importance scores |
   | DECAY_REVERSAL | K1 HedgingDetector | Restore decayed memory |
   | CLUSTER_CORRECTION | K1 CorrectionParser | Fix clustering |
   | REINFORCEMENT_OUTCOME | P21 GapResolution | Track if reinforcement helped |
   | NOVELTY_SIGNAL | K1 HedgingDetector | Log memory gap for learning |

3. **Processing Flow**:
   - Receive FeedbackEnvelope from bus topic
   - Validate P03FeedbackPayload
   - Apply learning action (update st_learned_weights)
   - Mark feedback consumed in st_feedback_signals

**Rationale**: P03 consumes from P21's shared infrastructure; detection logic lives in K1.

---

#### Issue 6.3.2: Feedback-to-Learning Mapping

**Read From Whiteboard**:

- Section 6.15.5 (Signal Confidence Summary) — confidence levels
- Section 6.1 through 6.12 — which formulas should react to which signals

**Read From External Plan**:

- PLAN-feedback-pipeline-system.md Story 3.1.1 — P03FeedbackHandler actions

**Edit Description**:
Add to Appendix C new subsection `#### C.X Feedback-to-Formula Mapping`:

**Content to Add**:

1. **Signal → Formula Impact**:

   | Feedback Type | Affected Formula | Parameter Updated |
   |---------------|------------------|-------------------|
   | SALIENCE_ADJUSTMENT | Importance (R1) | importance weights |
   | DECAY_REVERSAL | Unified Decay (R3) | decay λ |
   | CLUSTER_CORRECTION | DBSCAN (R2) | eps, min_samples |
   | NOVELTY_SIGNAL | Novelty Score (R4) | novelty thresholds |
   | REFORMULATION (via payload) | Similarity (R6) | similarity thresholds |

2. **Confidence Weighting**:
   - < 0.50: Use only in aggregate (10+ signals)
   - 0.50-0.75: Apply with 50% weight
   - > 0.75: Apply full weight

3. **Batch Processing**: Signals processed in nightly batch, not real-time

**Rationale**: Map P21-delivered signals to P03 learning formulas.

---

#### Issue 6.3.3: P03 Adversarial Signal Filtering

**Read From Whiteboard**:

- Section 6.15.3 (Adversarial Handling) — defense layers

**Read From External Plan**:

- PLAN-feedback-pipeline-system.md — primary adversarial detection in P21
- P03 adds pipeline-specific anomaly detection

**Edit Description**:
Add to Section 14 new subsection `#### 14.X P03 Learning Anomaly Detection`:

**Content to Add**:

1. **P03-Specific Checks** (in addition to P21 quarantine):

   | Check | Threshold | Action |
   |-------|-----------|--------|
   | Parameter drift | > 20% change in 24h | Pause learning, alert |
   | Contradictory signals | Same entity, opposite signals | Flag for review |
   | Formula regression | Quality metric drops > 10% | Auto-rollback |

2. **Learning Pause**: If anomaly detected, stop applying signals until reviewed

**Rationale**: P21 handles ingestion-level protection; P03 adds formula-level protection.

---

#### Issue 6.3.4: Signal Confidence Standards

**Read From Whiteboard**:

- Section 6.15.5 (Signal Confidence Summary) — base confidences
- Section 6.15.5 Adjustment Factors — context modifiers

**Read From Dossier**:

- st_feedback_signals has confidence column
- No documented confidence standards

**Edit Description**:
Add to Appendix C new subsection `#### C.X Implicit Signal Confidence Standards`:

**Content to Add**:

1. **Base Confidence by Signal Type**:

   | Signal | Base Confidence | Reliability |
   |--------|-----------------|-------------|
   | CORRECTION | 0.90 | High (explicit) |
   | MEMORY_MISS | 0.80 | High (clear gap) |
   | REFORMULATION | 0.60 | Medium (inferred) |
   | ABANDONMENT | 0.50 | Low (uncertain) |
   | REGRET | 0.90 | High (clear mistake) |

2. **Adjustment Factors**:

   | Condition | Adjustment |
   |-----------|------------|
   | Explicit user action ("I meant...") | +0.10 |
   | Via UI control (not direct) | -0.10 |
   | Late night session | -0.20 |
   | Repeat pattern (3+ similar) | +0.10 |

3. **Confidence Usage**:
   - < 0.50: Use only in aggregate (10+ signals)
   - 0.50-0.75: Apply with 50% weight
   - > 0.75: Apply full weight

**Rationale**: Different signals have different reliability; weight accordingly.

---

### Epic 6.1/6.2/6.3 Summary: Dossier Locations

| Issue | Insert Location | Section Number |
|-------|-----------------|----------------|
| 6.1.1 | Extend Section 4.4 | New 4.4.1 |
| 6.1.2 | Extend Appendix C.4 | New C.4.1 |
| 6.1.3 | Extend Appendix C.4 | New C.4.2 |
| 6.2.1 | Extend Section 4.4 | New 4.4.2 |
| 6.2.2 | Extend Appendix C.4 | New C.4.3 |
| 6.2.3 | Extend Appendix C.4 | New C.4.4 |
| 6.2.4 | Extend Section 6 | New 6.X.X |
| 6.3.1 | Extend Section 9 | New 9.X |
| 6.3.2 | Extend Section 9 | New 9.X |
| 6.3.3 | Extend Section 14 | New 14.X |
| 6.3.4 | Extend Appendix C | New C.X |

### Dependencies from Previous Milestones

| M6 Issue | Depends On | Reason |
|----------|------------|--------|
| 6.1.2 | 1.1.1 (st_learned_weights) | Per-entity λ stored here |
| 6.1.3 | 3.2.1 (DECAY_CONFIGS learning) | Fallback to learned type defaults |
| 6.2.4 | st_pruned_entities (P03 owned) | Regret tracking for pruned entities |
| 6.3.1-4 | P21 st_feedback_signals (shared) | P03 consumes from P21 table |
| 6.3.3 | 1.2.1 (Feature flags) | `P03_FF_ADVERSARIAL_DETECTION` |

> **External Dependency**: P21 Feedback Pipeline (PLAN-feedback-pipeline-system.md)
> Must be implemented before M6 can consume feedback signals.

---

## Milestone 7: Cross-Cutting Concerns

**Goal**: A/B testing, rollback, explainability, isolation, compute budget

---

### Epic 7.1: A/B Testing & Rollout

**Dossier Location**: Section 12 (Feature Flags), Section 11 (Migration), Section 8 (Observability)
**Primary Goal**: Safe rollout of formula changes via shadow mode and gradual canary

---

#### Issue 7.1.1: Shadow Mode for Formulas

**Read From Whiteboard**:

- Section 6.16.1 (A/B Testing) — shadow mode details
- Section 6.16.1 Testing Phases table — Phase 0 Shadow

**Read From Dossier**:

- Section 12 (Feature Flags) — flag patterns
- No shadow mode capability exists

**Edit Description**:
Add to Section 12 new subsection `#### 12.X Shadow Mode Infrastructure`:

**Content to Add**:

1. **Shadow Mode Concept**:
   - Old formula applies changes to database
   - New formula computes but does NOT apply
   - Log both outcomes for comparison
   - Zero production risk

2. **Implementation Pattern**:

   ```
   if shadow_mode_enabled(formula_name):
       old_result = run_old_formula(inputs)
       new_result = run_new_formula(inputs)
       log_comparison(old_result, new_result)
       return old_result  # Only old applies
   ```

3. **Feature Flag**: `P03_FF_SHADOW_{formula_name}`
4. **Duration**: Minimum 7 days in shadow before canary

**Also Add**: Metric `p03_shadow_comparison_divergence` to Section 8.2

**Rationale**: Validate new formulas with zero risk before any production impact.

---

#### Issue 7.1.2: Canary Rollout Process

**Read From Whiteboard**:

- Section 6.16.1 Testing Phases table — 4-phase rollout
- Section 6.16.1 Rollout Decision — automatic promotion criteria

**Read From Dossier**:

- Section 11 (Migration) — migration patterns
- No gradual rollout process

**Edit Description**:
Add to Section 11 new subsection `#### 11.X Formula Canary Rollout`:

**Content to Add**:

1. **Rollout Phases**:

   | Phase | Description | Duration | % of Spaces |
   |-------|-------------|----------|-------------|
   | 0. Shadow | New runs, discarded | 7 days | 0% |
   | 1. Canary | Small test group | 7 days | 5% |
   | 2. Gradual | Progressive expansion | 14 days | 25→50→75% |
   | 3. Full | Complete rollout | Permanent | 100% |

2. **Promotion Criteria**:
   - All comparison metrics pass (see 7.1.3)
   - No regression > 5% on any metric
   - Human review if borderline

3. **Halt Criteria**:
   - Any metric regresses > 10% → automatic halt
   - User corrections spike > 3× → halt + alert
   - Error rate > 5% → immediate rollback

4. **Space Selection**: Random selection, stratified by space size

**Rationale**: Gradual exposure limits blast radius of any formula bugs.

---

#### Issue 7.1.3: Comparison Metrics

**Read From Whiteboard**:

- Section 6.16.1 Comparison Metrics table — success criteria
- Section 6.16.1 Shadow Mode Details — what to measure

**Read From Dossier**:

- Section 8 (Observability) — metrics patterns
- No formula comparison metrics

**Edit Description**:
Add to Section 8 new subsection `#### 8.X Formula Comparison Metrics`:

**Content to Add**:

1. **Comparison Metrics**:

   | Metric | Success Criteria | Measurement |
   |--------|------------------|-------------|
   | Memory retrieval accuracy | New ≥ Old | P04 grounding rate |
   | Decay calibration error | New < Old by > 5% | Regret signal rate |
   | Processing time | New ≤ Old × 1.1 | p99 latency |
   | Edge case handling | No regressions | Error rate delta |

2. **Comparison Dashboard**:
   - Side-by-side metrics: old vs new
   - Time series: divergence over rollout period
   - Anomaly highlighting

3. **Statistical Significance**: Require p < 0.05 before declaring winner

**Also Add**: Prometheus queries for all comparison metrics

**Rationale**: Data-driven rollout decisions based on measured outcomes.

---

### Epic 7.2: Rollback Mechanism

**Dossier Location**: Section 13 (Error Handling), Section 17 (Ops Readiness)
**Primary Goal**: Fast rollback of parameters or formulas when quality degrades

---

#### Issue 7.2.1: Parameter Rollback

**Read From Whiteboard**:

- Section 6.16.2 Parameter Rollback — version history
- Section 6.16.2 Parameter History Schema — storage design

**Read From Dossier**:

- Section 13 (Error Handling) — error recovery patterns
- st_learned_weights has no versioning

**Edit Description**:
Add to Section 13 new subsection `#### 13.X Parameter Rollback`:

**Content to Add**:

1. **Version History**: st_learned_weights stores last 10 versions per parameter

2. **History Schema Extension**:

   | Column | Type | Purpose |
   |--------|------|---------|
   | version | INTEGER | 1, 2, 3, ... |
   | applied_at | BIGINT | When this version applied |
   | quality_at_time | REAL | Quality metric when applied |
   | rolled_back | BOOLEAN | Was this version rolled back? |

3. **Rollback Process**:
   - Identify parameter to rollback
   - Find previous version where quality_at_time was acceptable
   - Restore that version's value
   - Mark current version as `rolled_back = true`

4. **Rollback Speed**: Instant (single UPDATE statement)

**Also Add**: Runbook for parameter rollback to Section 17

**Rationale**: Learned parameters can drift; need fast recovery path.

---

#### Issue 7.2.2: Formula Rollback

**Read From Whiteboard**:

- Section 6.16.2 Formula Rollback — feature flag approach
- Section 6.16.2 Two-Level Rollback table

**Read From Dossier**:

- Section 12 (Feature Flags) — flag patterns
- No formula version control

**Edit Description**:
Add to Section 13 new subsection `#### 13.X Formula Rollback`:

**Content to Add**:

1. **Formula Version Control**:
   - Each formula has version identifier (e.g., `hebbian_v1`, `hebbian_v2`)
   - Feature flag controls which version runs
   - Flag: `P03_FF_FORMULA_VERSION_{formula_name}`

2. **Rollback Process**:
   - Flip feature flag to previous version
   - Takes effect on next consolidation cycle
   - All spaces affected simultaneously

3. **Rollback Speed**: Minutes (flag propagation time)

4. **Version Registry**:

   | Formula | Current | Previous | Fallback |
   |---------|---------|----------|----------|
   | importance | v2 | v1 | static |
   | hebbian | v2 | v1 | disabled |
   | decay | v3 | v2 | v1 |
   | similarity | v2 | v1 | static |

**Rationale**: Algorithm bugs may require reverting entire formula, not just parameters.

---

#### Issue 7.2.3: Automatic Rollback Triggers

**Read From Whiteboard**:

- Section 6.16.2 Automatic Rollback Triggers table — signals and thresholds

**Read From Dossier**:

- Section 17 (Ops Readiness) — alerting patterns
- No automatic rollback

**Edit Description**:
Add to Section 17 new subsection `#### 17.X Automatic Rollback`:

**Content to Add**:

1. **Automatic Triggers**:

   | Signal | Threshold | Action |
   |--------|-----------|--------|
   | Memory retrieval accuracy drop | > 15% in 24h | Rollback parameters |
   | User corrections spike | > 3× baseline | Alert + manual review |
   | Processing time spike | > 2× baseline | Rollback formula |
   | Error rate | > 5% | Immediate halt |
   | Regret signal spike | > 5× baseline | Rollback decay parameters |

2. **Trigger Evaluation**: Every 15 minutes
3. **Cooldown**: 24h after rollback before re-enabling learning
4. **Notification**: PagerDuty alert on any automatic rollback

**Also Add**: Alert `P03LearningRollbackTriggered` to Section 17.3

**Rationale**: Automated safety net catches degradation before users notice.

---

### Epic 7.3: Explainability

**Dossier Location**: Section 14 (Security/Audit), Section 6 (Storage), Section 8 (Observability)
**Primary Goal**: Users and operators can understand why memory decisions were made

---

#### Issue 7.3.1: User-Facing Explanations

**Read From Whiteboard**:

- Section 6.16.3 User-Facing Explanations table — templates
- Section 6.16.3 Three Levels — audience differentiation

**Read From Dossier**:

- Section 14 (Security/Audit) — audit patterns
- No user-facing explanations

**Edit Description**:
Add to Section 14 new subsection `#### 14.X Memory Decision Explanations`:

**Content to Add**:

1. **Explanation Templates**:

   | Decision | Template |
   |----------|----------|
   | REINFORCE | "This memory was reinforced because you mentioned {entity} frequently this week." |
   | DECAY | "This memory faded because it hasn't been accessed in {N} days." |
   | ARCHIVE | "This memory was archived to make room for more recent information." |
   | MERGE | "These two memories were combined because they refer to the same {entity_type}." |
   | CREATE | "A new memory was created for {entity} based on your conversation." |

2. **Template Variables**:
   - `{entity}`: Entity canonical name
   - `{entity_type}`: PERSON, PLACE, etc.
   - `{N}`: Numeric value (days, count)
   - `{date}`: Human-readable date

3. **API Endpoint**: `GET /k0/memory/{id}/explanation`

**Rationale**: Users deserve to understand why their memories change.

---

#### Issue 7.3.2: Audit Trail Design

**Read From Whiteboard**:

- Section 6.16.3 st_consolidation_audit Table — full schema
- Section 6.16.3 Retention — 90 days then aggregate

**Read From Dossier**:

- Section 6 (Storage) — table patterns
- st_consolidation_audit partially defined in 1.1.4

**Edit Description**:
Extend Section 6 st_consolidation_audit with additional columns:

**Content to Add**:

1. **Extended Schema**:

   | Column | Type | Purpose |
   |--------|------|---------|
   | formula_used | TEXT | e.g., "hebbian_v2", "decay_unified" |
   | formula_version | TEXT | Version identifier |
   | inputs_json | JSONB | All input parameters |
   | outputs_json | JSONB | All output values |
   | explanation | TEXT | User-friendly explanation |
   | confidence | REAL | Decision confidence (0-1) |

2. **Retention Policy**:
   - Raw records: 90 days
   - After 90 days: Aggregate to daily summaries
   - Summaries kept: 2 years

3. **Indexes**:
   - `idx_audit_memory_time` on (memory_id, timestamp)
   - `idx_audit_action` on (action, timestamp)

**Rationale**: Complete audit trail for debugging and compliance.

---

#### Issue 7.3.3: Debug-Level Tracing

**Read From Whiteboard**:

- Section 6.16.3 Three Levels — Debug-facing details
- Section 6.16.3 Ops-facing — structured audit trail

**Read From Dossier**:

- Section 8 (Observability) — tracing patterns
- No formula-level tracing

**Edit Description**:
Add to Section 8 new subsection `#### 8.X Formula Debug Tracing`:

**Content to Add**:

1. **Trace Levels**:

   | Level | Audience | Content |
   |-------|----------|---------|
   | User | End users | Natural language explanation |
   | Ops | Support team | Structured audit + decision path |
   | Debug | Developers | Full computation trace + intermediates |

2. **Debug Trace Content**:
   - All input values with types
   - Each formula step with intermediate results
   - Threshold comparisons with actual values
   - Feature flag states at decision time
   - Timing for each step

3. **Trace Sampling**: 1% of decisions get full debug trace (configurable)
4. **Trace Storage**: 7 days for debug traces (large)

**Also Add**: `P03_FF_DEBUG_TRACE_RATE` to Section 12

**Rationale**: Detailed traces essential for debugging formula issues.

---

### Epic 7.4: Multi-Tenant Isolation

**Dossier Location**: Section 14 (Security), Section 6 (Storage), Section 8 (Observability)
**Primary Goal**: Absolute isolation — no cross-space learning leakage

---

#### Issue 7.4.1: Per-Space Learning Isolation

**Read From Whiteboard**:

- Section 6.16.4 Isolation Boundaries table — per-space for all data
- Section 6.16.4 Cross-Space Exceptions — NONE currently

**Read From Dossier**:

- Section 14 (Security) — multi-tenant patterns
- Learning tables need explicit isolation

**Edit Description**:
Add to Section 14 new subsection `#### 14.X Learning Data Isolation`:

**Content to Add**:

1. **Isolation Boundaries**:

   | Data Type | Isolation Level | Mechanism |
   |-----------|-----------------|-----------|
   | Learned weights | Per-space | space_id column |
   | Feedback signals | Per-space | space_id column |
   | Audit records | Per-space | space_id column |
   | Pruned entities | Per-space | space_id column |
   | Feature flags | Per-space | space_id column |

2. **Isolation Principle**: Each space learns independently
   - No shared priors across spaces
   - No global defaults learned from other spaces
   - Static defaults only from code configuration

3. **Query Pattern**: Every query MUST include `WHERE space_id = ?`

**Rationale**: Family data must never influence another family's learning.

---

#### Issue 7.4.2: RLS Enforcement

**Read From Whiteboard**:

- Section 6.16.4 Isolation Enforcement — RLS enabled
- Section 6.16.4 Audit — quarterly review

**Read From Dossier**:

- Section 6 (Storage) — RLS patterns on other tables
- Learning tables need RLS

**Edit Description**:
Add to Section 6 new subsection `#### 6.X Row-Level Security for Learning Tables`:

**Content to Add**:

1. **RLS Policies**:

   ```sql
   -- st_learned_weights
   CREATE POLICY learned_weights_isolation ON st_learned_weights
       USING (space_id = current_setting('app.current_space_id'));

   -- st_consolidation_audit
   CREATE POLICY audit_isolation ON st_consolidation_audit
       USING (space_id = current_setting('app.current_space_id'));

   -- st_pruned_entities
   CREATE POLICY pruned_isolation ON st_pruned_entities
       USING (space_id = current_setting('app.current_space_id'));
   ```

2. **Application Context**: Set `app.current_space_id` at connection start
3. **Superuser Bypass**: Only for migrations and ops tooling

**Rationale**: RLS provides database-level enforcement of isolation.

---

#### Issue 7.4.3: Cross-Space Leakage Audit

**Read From Whiteboard**:

- Section 6.16.4 Audit — quarterly review, metrics

**Read From Dossier**:

- Section 8 (Observability) — audit patterns
- No cross-space monitoring

**Edit Description**:
Add to Section 8 new subsection `#### 8.X Cross-Space Leakage Detection`:

**Content to Add**:

1. **Monitoring**:
   - Metric: `p03_cross_space_query_attempts` (should always be 0)
   - Alert if metric > 0

2. **Query Audit**:
   - Log all queries to learning tables
   - Weekly automated scan for missing `WHERE space_id`
   - Quarterly manual review

3. **Testing**:
   - Integration tests verify isolation
   - Attempt cross-space access in test suite → must fail

**Also Add**: Alert `P03CrossSpaceLeakageDetected` to Section 17.3

**Rationale**: Detect and prevent any cross-space data access.

---

### Epic 7.5: Compute Budget

**Dossier Location**: Section 15 (Performance), Section 8 (Observability)
**Primary Goal**: Learning uses < 5% of P03 consolidation cycle time

---

#### Issue 7.5.1: 5% Budget Enforcement

**Read From Whiteboard**:

- Section 6.16.5 Budget breakdown table — component allocations
- Section 6.16.5 Performance Guardrails table — max times

**Read From Dossier**:

- Section 15 (Performance) — performance targets
- No learning budget defined

**Edit Description**:
Add to Section 15 new subsection `#### 15.X Learning Compute Budget`:

**Content to Add**:

1. **Total Budget**: < 5% of P03 consolidation cycle time

2. **Component Breakdown**:

   | Component | % of Budget | Absolute Target |
   |-----------|-------------|-----------------|
   | Feedback ingestion | 20% | < 10ms per signal |
   | Parameter update | 30% | < 50ms per update |
   | Quality monitoring | 30% | < 100ms per cycle |
   | Audit logging | 20% | < 20ms per record |

3. **Enforcement**:
   - If learning exceeds budget → skip non-critical operations
   - Priority: quality monitoring > parameter update > audit > feedback

4. **Measurement**: Track `p03_learning_time_pct` per cycle

**Rationale**: Learning must not slow down memory consolidation.

---

#### Issue 7.5.2: Batch Processing

**Read From Whiteboard**:

- Section 6.16.5 Optimization Strategies — batch processing
- Section 6.16.5 Performance Guardrails — queue overflow handling

**Read From Dossier**:

- Section 15 (Performance) — batch patterns
- No learning batch processing

**Edit Description**:
Add to Section 15 new subsection `#### 15.X Learning Batch Processing`:

**Content to Add**:

1. **Batch Strategy**:

   | Operation | Batch Size | Interval |
   |-----------|------------|----------|
   | Feedback processing | 100 signals | Every 1 minute |
   | Parameter updates | 10 params | Every 5 minutes |
   | Audit writes | 50 records | Every 30 seconds |
   | Quality checks | 1 | Every cycle |

2. **Queue Management**:
   - Max queue depth: 1000 signals
   - If queue > 1000 → sample (process 10%, discard rest)
   - Alert if queue consistently > 500

3. **Async Writes**: Audit writes non-blocking (fire-and-forget)

**Rationale**: Batching amortizes overhead and smooths load.

---

#### Issue 7.5.3: Learning Metrics

**Read From Whiteboard**:

- Section 6.16.5 Metrics — specific metric names

**Read From Dossier**:

- Section 8 (Observability) — metrics patterns
- No learning-specific metrics

**Edit Description**:
Add to Section 8 new subsection `#### 8.X Learning Performance Metrics`:

**Content to Add**:

1. **Core Metrics**:

   | Metric | Type | Description |
   |--------|------|-------------|
   | `p03_learning_time_pct` | Gauge | % of cycle time spent on learning |
   | `p03_learning_latency_p99` | Histogram | 99th percentile latency |
   | `p03_learning_queue_depth` | Gauge | Pending feedback signals |
   | `p03_learning_batch_size` | Histogram | Signals per batch |
   | `p03_learning_skip_rate` | Counter | Operations skipped due to budget |

2. **Alerting Thresholds**:

   | Metric | Warning | Critical |
   |--------|---------|----------|
   | learning_time_pct | > 4% | > 5% |
   | queue_depth | > 500 | > 1000 |
   | skip_rate | > 1/hour | > 10/hour |

3. **Dashboard**: Learning ops dashboard with all metrics

**Rationale**: Visibility into learning performance for proactive optimization.

---

### Epic 7.1-7.5 Summary: Dossier Locations

| Issue | Insert Location | Section Number |
|-------|-----------------|----------------|
| 7.1.1 | Extend Section 12 | New 12.X |
| 7.1.2 | Extend Section 11 | New 11.X |
| 7.1.3 | Extend Section 8 | New 8.X |
| 7.2.1 | Extend Section 13 | New 13.X |
| 7.2.2 | Extend Section 13 | New 13.X |
| 7.2.3 | Extend Section 17 | New 17.X |
| 7.3.1 | Extend Section 14 | New 14.X |
| 7.3.2 | Extend Section 6 | Extend 6.20 |
| 7.3.3 | Extend Section 8 | New 8.X |
| 7.4.1 | Extend Section 14 | New 14.X |
| 7.4.2 | Extend Section 6 | New 6.X |
| 7.4.3 | Extend Section 8 | New 8.X |
| 7.5.1 | Extend Section 15 | New 15.X |
| 7.5.2 | Extend Section 15 | New 15.X |
| 7.5.3 | Extend Section 8 | New 8.X |

### Dependencies from Previous Milestones

| M7 Issue | Depends On | Reason |
|----------|------------|--------|
| 7.1.1 | 1.2.1 (Feature flags) | Shadow mode flags |
| 7.1.3 | All M2-M5 formulas | Metrics for each formula |
| 7.2.1 | 1.1.1 (st_learned_weights) | Version history stored here |
| 7.2.3 | 7.1.3 (Comparison metrics) | Triggers based on metrics |
| 7.3.2 | 1.1.4 (st_consolidation_audit) | Extends audit table |
| 7.4.2 | All storage tables | RLS on all learning tables |
| 7.5.1 | All learning operations | Budget covers all components |

---

## Milestone 8: P21 Feedback System Integration

**Goal**: Ensure P03 correctly integrates with P21 Feedback Pipeline infrastructure

> **Reference**: [PLAN-feedback-pipeline-system.md](./PLAN-feedback-pipeline-system.md)
> P03 is a CONSUMER of P21. K1 emits feedback via observe port → P21 routes to `feedback.signal.p03`.

---

### Epic 8.1: P03FeedbackPayload Schema

**Dossier Location**: Section 9 (Integration Contracts), k0/feedback/schemas/
**Primary Goal**: Register P03-specific feedback payload schema with P21 infrastructure

> **Coordination Required**: These issues define the P03 side of the P21 contract.
> P21's FeedbackSchemaRegistry must recognize and validate P03 payloads.

---

#### Issue 8.1.1: Register P03 Schema with FeedbackSchemaRegistry

**Read From Whiteboard**:

- Section 6.10-6.15 — All signal types P03 needs
- Section 6.15.5 (Signal Confidence Summary) — signal categorization

**Read From P21 Plan**:

- PLAN-feedback-pipeline-system.md M0 Epic 0.1 — FeedbackSchemaRegistry pattern
- P21 maintains registry of all pipeline payload schemas

**Edit Description**:
Add to Section 9 new subsection `#### 9.X P03 Schema Registration`:

**Content to Add**:

1. **Registration Entry**:

   | Field | Value |
   |-------|-------|
   | Pipeline ID | `P03` |
   | Schema Name | `P03FeedbackPayload` |
   | Schema Version | `1.0` |
   | Location | `k0/feedback/schemas/p03_consolidation.py` |

2. **Registration Code**:

   ```python
   # k0/feedback/registry.py (P21 owns this file)
   from k0.feedback.schemas.p03_consolidation import P03FeedbackPayload

   SCHEMA_REGISTRY = {
       "P03": P03FeedbackPayload,
       # ... other pipelines
   }
   ```

3. **Validation Flow**:
   - P21 receives FeedbackEnvelope with `target_pipeline: "P03"`
   - P21 looks up `P03` in registry → gets `P03FeedbackPayload`
   - P21 validates `envelope.payload` against `P03FeedbackPayload`
   - If valid → store in `st_feedback_signals` and dispatch

**Rationale**: P21 must know P03's schema to validate incoming feedback.

---

#### Issue 8.1.2: Define P03FeedbackPayload Model

**Read From Whiteboard**:

- Section 6.1-6.5 — Importance formula signals
- Section 6.6-6.8 — Decay formula signals
- Section 6.9-6.11 — Hebbian signals
- Section 6.14 — Regret signals

**Read From P21 Plan**:

- PLAN-feedback-pipeline-system.md lines 347-380 — P03FeedbackPayload skeleton

**Edit Description**:
Add to Section 9 new subsection `#### 9.X P03FeedbackPayload Schema`:

**Content to Add**:

1. **Feedback Types** (from whiteboard research):

   | feedback_type | Source | Description |
   |---------------|--------|-------------|
   | SALIENCE_ADJUSTMENT | K1 grounding | Adjust importance score |
   | DECAY_REVERSAL | Query regret | Memory was needed but decayed |
   | CLUSTER_CORRECTION | User edit | Memories should/shouldn't be grouped |
   | REINFORCEMENT_OUTCOME | Hebbian | Reinforcement decision feedback |
   | NOVELTY_SIGNAL | K1 hedging | New pattern detected (memory gap) |
   | REGRET_SIGNAL | Query match | Pruned entity was later queried |

2. **Schema Fields**:

   ```python
   class P03FeedbackPayload(BaseModel):
       feedback_type: Literal[
           "SALIENCE_ADJUSTMENT",
           "DECAY_REVERSAL",
           "CLUSTER_CORRECTION",
           "REINFORCEMENT_OUTCOME",
           "NOVELTY_SIGNAL",
           "REGRET_SIGNAL",
       ]

       # Target identification
       wal_positions: list[int] = Field(default_factory=list)
       entity_id: str | None = None
       cluster_id: str | None = None

       # Adjustments
       salience_delta: float | None = None  # -1.0 to +1.0
       importance_override: float | None = None  # 0.0 to 1.0
       decay_lambda_delta: float | None = None  # Learning rate adjustment

       # Outcomes
       was_retrieved: bool | None = None
       was_helpful: bool | None = None
       user_confirmed: bool | None = None

       # Context (from K1)
       retrieval_query: str | None = None
       session_context: dict | None = None
       confidence: float = 0.5  # Signal confidence
   ```

3. **Field Mapping to Formulas**:

   | Field | Used By | Purpose |
   |-------|---------|---------|
   | salience_delta | Importance formula (R1) | α_imp adjustment |
   | decay_lambda_delta | Decay formula (R2/R3) | λ adjustment |
   | was_retrieved | Hebbian formula (R4) | Co-activation signal |
   | was_helpful | Hebbian formula (R4) | Success/failure signal |
   | confidence | All formulas | Weighting factor |

**Rationale**: Schema must capture all signal types P03 learning formulas need.

---

#### Issue 8.1.3: Validate Payload Coverage

**Read From Whiteboard**:

- Section 6.15.5 (Signal Confidence Summary) — complete signal list
- Section 6.1 through 6.14 — all formula input signals

**Read From P21 Plan**:

- PLAN-feedback-pipeline-system.md M3 — Pipeline integration

**Edit Description**:
Add to Section 9 new subsection `#### 9.X P03 Signal Coverage Matrix`:

**Content to Add**:

1. **Signal Coverage Validation**:

   | Whiteboard Signal | P03FeedbackPayload Field | Covered? |
   |-------------------|--------------------------|----------|
   | Grounding signal | salience_delta + was_helpful | ✅ |
   | Correction signal | salience_delta | ✅ |
   | Entity co-access | wal_positions (multiple) | ✅ |
   | Regret signal | feedback_type: REGRET_SIGNAL | ✅ |
   | Novelty signal | feedback_type: NOVELTY_SIGNAL | ✅ |
   | Decay reversal | feedback_type: DECAY_REVERSAL | ✅ |
   | Cluster correction | feedback_type: CLUSTER_CORRECTION | ✅ |

2. **Confidence Mapping**:

   | Signal Type | Base Confidence | Field |
   |-------------|-----------------|-------|
   | GROUNDING | 0.70 | confidence |
   | CORRECTION | 0.85 | confidence |
   | CO_ACCESS | 0.60 | confidence |
   | REGRET | 0.90 | confidence |
   | NOVELTY | 0.40 | confidence |

3. **Validation Test**: Integration test that every whiteboard signal can be represented

**Rationale**: Ensure no learning signals are lost at the P21 integration boundary.

---

### Epic 8.2: P03FeedbackHandler Implementation

**Dossier Location**: Section 5 (Pipeline Logic), Section 9 (Integration)
**Primary Goal**: Implement handler that subscribes to `feedback.signal.p03` and routes signals to learning formulas

---

#### Issue 8.2.1: Implement P03FeedbackHandler

**Read From Whiteboard**:

- Section 6.1-6.12 — Formula input mappings
- Section 6.15.5 — Confidence-based weighting

**Read From P21 Plan**:

- PLAN-feedback-pipeline-system.md lines 1027-1115 — P03FeedbackHandler skeleton

**Edit Description**:
Add to Section 5 new subsection `#### 5.X P03FeedbackHandler`:

**Content to Add**:

1. **Handler Structure**:

   ```python
   # k0/pipelines/p03_consolidation/feedback_handler.py

   class P03FeedbackHandler:
       """
       Consumes feedback for P03 (Consolidation/Salience).
       Subscribed topics: feedback.signal.p03
       """

       topics = ["feedback.signal.p03"]

       async def handle(self, msg: BusMessage, ctx: PipelineContext) -> None:
           envelope = FeedbackEnvelope.model_validate(msg.payload)
           payload = P03FeedbackPayload.model_validate(envelope.payload)

           match payload.feedback_type:
               case "SALIENCE_ADJUSTMENT":
                   await self._route_to_importance_learner(payload, ctx)
               case "DECAY_REVERSAL":
                   await self._route_to_decay_learner(payload, ctx)
               case "CLUSTER_CORRECTION":
                   await self._route_to_similarity_learner(payload, ctx)
               case "REINFORCEMENT_OUTCOME":
                   await self._route_to_hebbian_learner(payload, ctx)
               case "NOVELTY_SIGNAL":
                   await self._log_memory_gap(payload, ctx)
               case "REGRET_SIGNAL":
                   await self._route_to_regret_learner(payload, ctx)

           await self._mark_consumed(envelope.envelope_id, ctx)
   ```

2. **Signal Routing Table**:

   | feedback_type | Routes To | Learner Module |
   |---------------|-----------|----------------|
   | SALIENCE_ADJUSTMENT | ImportanceLearner | M2 (2.1.x) |
   | DECAY_REVERSAL | DecayLearner | M3 (3.1.x, 3.2.x) |
   | CLUSTER_CORRECTION | SimilarityLearner | M4 (4.2.x) |
   | REINFORCEMENT_OUTCOME | HebbianLearner | M4 (4.1.x) |
   | NOVELTY_SIGNAL | AuditLogger | M1 (1.1.4) |
   | REGRET_SIGNAL | RegretLearner | M6 (6.2.x) |

3. **Error Handling**: On error, log but don't retry (dead-letter after 3 failures)

**Rationale**: Central handler routes P21 signals to appropriate learning modules.

---

#### Issue 8.2.2: Wire Bus Subscription

**Read From Whiteboard**:

- Section 3.5 — Bus subscription pattern

**Read From P21 Plan**:

- PLAN-feedback-pipeline-system.md line 728 — `feedback.signal.p03` topic

**Edit Description**:
Add to Section 9 new subsection `#### 9.X P03 Bus Subscription`:

**Content to Add**:

1. **Topic Subscription**:

   | Topic | Handler | Priority |
   |-------|---------|----------|
   | `feedback.signal.p03` | P03FeedbackHandler | NORMAL |

2. **Subscription Registration**:

   ```python
   # k0/pipelines/p03_consolidation/__init__.py

   def register_handlers(bus: EventBus) -> None:
       bus.subscribe(
           topic="feedback.signal.p03",
           handler=P03FeedbackHandler(),
           priority=Priority.NORMAL,
       )
   ```

3. **Startup Order**:
   - P21 FeedbackSubsystem must start before P03
   - P03 subscribes during pipeline initialization
   - Subscription confirmed via `p03_feedback_subscribed` metric

4. **Health Check**: P03 reports unhealthy if subscription fails

**Also Add**: Metric `p03_feedback_messages_received` to Section 8

**Rationale**: P03 must actively subscribe to receive P21-dispatched signals.

---

#### Issue 8.2.3: Mark Consumed Flow

**Read From Whiteboard**:

- Section 6.16.4 (Isolation) — per-space tracking

**Read From P21 Plan**:

- PLAN-feedback-pipeline-system.md — `consumed_at`, `consumed_by` columns

**Edit Description**:
Add to Section 9 new subsection `#### 9.X Feedback Consumption Tracking`:

**Content to Add**:

1. **Consumption Fields** (in P21's st_feedback_signals):

   | Column | Type | Set By |
   |--------|------|--------|
   | consumed_at | BIGINT | P03FeedbackHandler |
   | consumed_by | TEXT | "P03" |
   | consumption_status | TEXT | "PROCESSED", "SKIPPED", "FAILED" |

2. **Mark Consumed Code**:

   ```python
   async def _mark_consumed(
       self,
       envelope_id: UUID,
       ctx: PipelineContext,
       status: str = "PROCESSED"
   ) -> None:
       await ctx.execute("""
           UPDATE st_feedback_signals
           SET
               consumed_at = $1,
               consumed_by = 'P03',
               consumption_status = $2
           WHERE envelope_id = $3
       """, int(time.time() * 1000), status, str(envelope_id))
   ```

3. **Consumption Statuses**:

   | Status | Meaning | Retry? |
   |--------|---------|--------|
   | PROCESSED | Successfully applied to learning | No |
   | SKIPPED | Filtered (low confidence, duplicate) | No |
   | FAILED | Error during processing | Yes (3x) |

4. **Audit Trail**: Link consumed feedback to st_consolidation_audit entries

**Also Add**: Metric `p03_feedback_consumption_status` with status label

**Rationale**: Track which signals were consumed to prevent reprocessing and enable debugging.

---

### Epic 8.1/8.2 Summary: Dossier Locations

| Issue | Insert Location | Section Number |
|-------|-----------------|----------------|
| 8.1.1 | Extend Section 9 | New 9.X |
| 8.1.2 | Extend Section 9 | New 9.X |
| 8.1.3 | Extend Section 9 | New 9.X |
| 8.2.1 | Extend Section 5 | New 5.X |
| 8.2.2 | Extend Section 9 | New 9.X |
| 8.2.3 | Extend Section 9 | New 9.X |

### Dependencies from Previous Milestones

| M8 Issue | Depends On | Reason |
|----------|------------|--------|
| 8.1.1 | P21 M0 (FeedbackSchemaRegistry) | Registry must exist |
| 8.1.2 | All M2-M6 formulas | Payload covers all signals |
| 8.2.1 | 8.1.2 (P03FeedbackPayload) | Handler validates payload |
| 8.2.1 | M2-M6 learner modules | Handler routes to learners |
| 8.2.2 | P21 M1 (BusDispatcher) | Topic must be available |
| 8.2.3 | P21 st_feedback_signals | Consumption columns exist |

### External Dependencies

| External Component | P03 Requirement | Status |
|--------------------|-----------------|--------|
| P21 FeedbackSchemaRegistry | Must accept P03 registration | 📋 Draft |
| P21 st_feedback_signals | Must have consumed_at/by columns | 📋 Draft |
| P21 BusDispatcher | Must route to feedback.signal.p03 | 📋 Draft |
| K1 observe port | Must emit FeedbackEnvelope | 📋 Draft |

---

## Summary: Issue Count

| Milestone | Epics | Issues |
|-----------|-------|--------|
| M1: Learning Infrastructure | 2 | 10 |
| M2: R1 Phase Learning | 2 | 9 |
| M3: R2/R3 Phase Learning | 2 | 10 |
| M4: R4/R5 Phase Learning | 5 | 18 |
| M5: Reconciliation Learning | 2 | 10 |
| M6: Feedback & Regret | 3 | 11 |
| M7: Cross-Cutting | 5 | 15 |
| M8: P21 Feedback Integration | 2 | 6 |
| **TOTAL** | **23** | **89** |

### External Dependencies

| External Plan | P03 Dependency | Status |
|---------------|----------------|--------|
| PLAN-feedback-pipeline-system.md | P21 must be implemented for M6/M8 | 📋 Draft |
| k0/ports/FEEDBACK.md | P03 wiring guide for feedback consumption | ✅ Available |

---

## Next Steps

1. **Line-level mapping**: For each issue, identify exact line numbers in P03 dossier
2. **Dependency graph**: Map which issues depend on which
3. **Sprint assignment**: Group issues into 2-week sprints
4. **ADR creation**: Create ADRs for major architectural changes

---

*Plan Document — Created from p03_whiteboard.md research*
