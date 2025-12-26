# P03 Consolidation Pipeline — Research Whiteboard

> **Purpose**: Living document for P03 formula research, enhancement proposals, and closed-loop feedback design
> **Status**: 🔬 Active Research
> **Created**: 2025-12-24
> **Last Updated**: 2025-12-24
> **Related Dossier**: [P03_consolidation_dossier_v2.md](P03_consolidation_dossier_v2.md) (Appendix I)

---

## Table of Contents

1. [Current Formula Inventory](#1-current-formula-inventory)
2. [Static vs Learnable Analysis](#2-static-vs-learnable-analysis)
3. [Closed-Loop Enhancement Proposals](#3-closed-loop-enhancement-proposals)
4. [Implementation Priority Matrix](#4-implementation-priority-matrix)
5. [Research Notes](#5-research-notes)
6. [Open Questions (Partitioned by Formula)](#6-open-questions-partitioned-by-formulaenhancement)
7. [Question Resolution Log](#7-question-resolution-log)

---

## 1. Current Formula Inventory

### 1.1 R1 — Hippocampal Replay (NREM1)

#### Importance Score

```python
importance_score = (
    0.35 × |sentiment_score| × |affect_valence| × (1 + affect_arousal)   # Emotional
  + 0.25 × exp(-0.05 × days_since_event)                                 # Recency
  + 0.20 × log(1 + access_count) / log(10)                               # Access freq
  + 0.20 × participant_count × avg_relationship_strength                 # Social
)
```

| Parameter | Current Value | Learnable? | Notes |
|-----------|---------------|------------|-------|
| Emotional weight | 0.35 | ✅ Yes | Should vary by user preference |
| Recency weight | 0.25 | ✅ Yes | Some users value history more |
| Access weight | 0.20 | ✅ Yes | Power users vs casual |
| Social weight | 0.20 | ✅ Yes | Introverts vs extroverts |
| Recency λ | 0.05 | ✅ Yes | 14-day half-life assumption |

**Scientific Basis**: McGaugh (2004) — Emotional tagging theory

---

#### Social Factor

```python
social_factor = min(1.0, log₂(participant_count) / 3.32)
```

| Participants | Score |
|--------------|-------|
| 1 (solo) | 0.00 |
| 2 | 0.30 |
| 5 | 0.70 |
| 10+ | 1.00 |

**Status**: ✅ Reasonable, low priority for change

---

#### Hebbian Weight Update

```python
new_weight = current_weight + learning_rate × (max_weight - current_weight) × event_importance
```

| Parameter | Current Value | Learnable? |
|-----------|---------------|------------|
| learning_rate | 0.1 | ⚠️ Maybe |
| max_weight | 1.0 | ❌ No (normalization) |

**Scientific Basis**: Hebb (1949) — "Cells that fire together, wire together"

---

#### Association Strength

```python
association_strength = (
    co_occurrence_count
  × exp(-0.01 × avg_time_gap_hours)
  × (unique_contexts / total_contexts)
  × (1 + avg_sentiment_score)
)
```

| Parameter | Current Value | Learnable? |
|-----------|---------------|------------|
| Temporal decay λ | 0.01 | ✅ Yes |

---

### 1.2 R2 — Neocortical Integration (NREM2)

#### DBSCAN Composite Distance

```python
composite_distance = (1 - temporal_weight) × semantic_distance + temporal_weight × temporal_distance

semantic_distance = 1 - cosine_similarity(embedding_a, embedding_b)
temporal_distance = time_diff_hours / max_temporal_gap_hours
```

| Parameter | Current Value | Learnable? | Notes |
|-----------|---------------|------------|-------|
| eps | 0.25 | ✅ Yes | Per-space clustering tightness |
| min_samples | 2 | ⚠️ Maybe | Min events per episode |
| temporal_weight | 0.3 | ✅ Yes | Semantic vs temporal balance |
| max_temporal_gap | 4 hours | ✅ Yes | Episode boundary definition |

---

#### Confidence Score

```python
confidence = √(frequency_score × consistency_score × significance_score)

frequency_score = min(1.0, log(observation_count + 1) / log(10))
consistency_score = 1 - coefficient_of_variation(features)
significance_score = (temporal_regularity + spatial_tightness) / 2
```

**Status**: ✅ Well-designed, geometric mean is robust

---

#### Centroid Calculation

```python
centroid = Σ(weight_i × embedding_i)
centroid = centroid / ||centroid||  # L2 normalize

# Hybrid weighting (default)
weight_i = 0.7 × importance_i + 0.3 × recency_i
```

| Parameter | Current Value | Learnable? |
|-----------|---------------|------------|
| Importance weight | 0.7 | ⚠️ Maybe |
| Recency weight | 0.3 | ⚠️ Maybe |

---

### 1.3 R3 — Synaptic Homeostasis / Forgetting (SWS)

#### Decay Function ⚠️ HIGH PRIORITY FOR LEARNING

```python
decay_factor = exp(-λ × days_since_last_observed)
```

| Layer | λ (Current) | Half-life | Learnable? |
|-------|-------------|-----------|------------|
| st_epi | 0.005 | 139 days | ✅ Yes — per entity |
| st_sem | 0.003 | 231 days | ✅ Yes — per pattern type |
| st_procedural | 0.010 | 69 days | ✅ Yes — per habit |
| st_social | 0.002 | 347 days | ✅ Yes — per relationship |

**Scientific Basis**: Tononi & Cirelli (2006), Ebbinghaus forgetting curve

**Problem**: Why does everyone forget at the same rate?

---

#### Effective Lambda (Adjusted Decay)

```python
effective_λ = base_λ × importance_factor × confidence_factor × reinforcement_factor

importance_factor = 1.0 - (importance_score × 0.5)
confidence_factor = 1.0 - (confidence_score × 0.3)
reinforcement_factor = 1.0 / (1.0 + 0.1 × observation_count)
```

| Parameter | Current Value | Learnable? |
|-----------|---------------|------------|
| importance_modifier | 0.5 | ✅ Yes |
| confidence_modifier | 0.3 | ✅ Yes |
| reinforcement_rate | 0.1 | ✅ Yes |

---

#### Novelty Score

```python
novelty_score = 1.0 - (duplicate_count / time_window_event_count)

# Modifiers
+ 0.15  # first-time activity
+ 0.20  # milestone events
+ 0.10  # temporal anomaly
- 0.30  # exact duplicate
```

| Parameter | Current Value | Learnable? |
|-----------|---------------|------------|
| First-time bonus | 0.15 | ⚠️ Maybe |
| Milestone bonus | 0.20 | ❌ No (semantic) |
| Anomaly bonus | 0.10 | ⚠️ Maybe |
| Duplicate penalty | 0.30 | ⚠️ Maybe |

---

#### SimHash Hamming Distance

```python
hamming_distance = popcount(hash1 XOR hash2)
is_near_duplicate = (hamming_distance ≤ 3)
```

| Parameter | Current Value | Learnable? |
|-----------|---------------|------------|
| Threshold | 3 bits | ⚠️ Maybe — per content type |

---

### 1.4 R4 — Knowledge Graph Consolidation

#### Entity Disambiguation Score

```python
disambiguation_score = 0.7 × embedding_similarity + 0.3 × fuzzy_string_match
```

| Parameter | Current Value | Learnable? |
|-----------|---------------|------------|
| Embedding weight | 0.7 | ✅ Yes |
| String weight | 0.3 | ✅ Yes |
| Match threshold | 0.8 | ✅ Yes |

---

#### Granger Causality

```python
precedence_ratio = a_before_b_count / (a_before_b + b_before_a + simultaneous)

# Decision rules
If ratio ≥ 0.75 → A CAUSES B
If ratio ≤ 0.25 → B CAUSES A
```

| Parameter | Current Value | Learnable? |
|-----------|---------------|------------|
| Causality threshold | 0.75 | ⚠️ Maybe |

---

### 1.5 R5 — Dream-Like Exploration (REM)

#### UCT Selection (MCTS)

```python
UCT = Q/N + c × √(ln(N_parent) / N)
```

| Parameter | Current Value | Learnable? |
|-----------|---------------|------------|
| Exploration constant c | 1.414 (√2) | ❌ No (theoretical) |

---

#### Rollout Reward

```python
total_reward = Σ(reward_day × 0.9^day) + goal_bonus
```

| Parameter | Current Value | Learnable? |
|-----------|---------------|------------|
| Discount factor | 0.9 | ⚠️ Maybe |
| Goal bonus | 10.0 | ⚠️ Maybe |

---

#### PMI Score (Insight Generation)

```python
PMI = log₂(P(A,B) / (P(A) × P(B)))
```

| Parameter | Current Value | Learnable? |
|-----------|---------------|------------|
| PMI threshold | 3.0 | ⚠️ Maybe |

---

### 1.6 R7 — Memory Layer Writes (Truth Update)

#### Multi-Factor Similarity ⚠️ HIGH PRIORITY

```python
similarity = (
    0.40 × cosine_similarity(embedding)     # Semantic
  + 0.25 × (1 - hamming_distance / 64)      # Text structure
  + 0.15 × jaccard_similarity(entities)      # Entity overlap
  + 0.10 × temporal_proximity_score          # Time closeness
  + 0.10 × spatial_proximity_score           # Location closeness
)
```

| Parameter | Current Value | Learnable? | Notes |
|-----------|---------------|------------|-------|
| Semantic weight | 0.40 | ✅ Yes | May need more for some domains |
| SimHash weight | 0.25 | ✅ Yes | |
| Entity weight | 0.15 | ✅ Yes | |
| Temporal weight | 0.10 | ✅ Yes | |
| Spatial weight | 0.10 | ✅ Yes | |

---

#### Reconciliation Thresholds ⚠️ CRITICAL FOR ADAPTIVE LEARNING

| Similarity | Decision | Current Threshold |
|------------|----------|-------------------|
| High | **REINFORCE** | > 0.85 |
| Medium | **EXTEND/EVOLVE** | 0.60 – 0.85 |
| Low | **CREATE/CONTRADICT** | < 0.60 |

**Problem**: Why 0.85? Why 0.60? These are arbitrary and should adapt.

---

### 1.7 P06 Integration (Active Learning)

#### Gap Priority

```python
priority = 0.5 × entropy + 0.3 × recency_factor + 0.2 × impact_factor
```

| Parameter | Current Value | Learnable? |
|-----------|---------------|------------|
| Entropy weight | 0.5 | ⚠️ Maybe |
| Recency weight | 0.3 | ⚠️ Maybe |
| Impact weight | 0.2 | ⚠️ Maybe |

---

#### Shannon Entropy

```python
entropy = -Σ(p_i × log₂(p_i)) / log₂(n)
```

**Status**: ✅ Information-theoretic, no parameters

---

#### Bayesian Anchor Update

```python
new_α = α + evidence_weight    # if supports
new_β = β + evidence_weight    # if contradicts
confidence = α / (α + β)
```

**Status**: ✅ Well-designed Bayesian update

---

#### Token Bucket (Rate Limiting)

```python
tokens_available = min(max_tokens, current + refill_rate × hours_elapsed)
```

| Parameter | Current Value | Learnable? |
|-----------|---------------|------------|
| Max tokens | 5/day | ⚠️ Maybe — per user engagement |
| Refill rate | 0.5-1.0/hour | ⚠️ Maybe |

---

## 2. Static vs Learnable Analysis

### 2.1 Parameters That SHOULD Be Learned

| Parameter | Why Learnable | Learning Method |
|-----------|---------------|-----------------|
| Importance weights (0.35/0.25/0.20/0.20) | User preferences vary | Gradient descent |
| Decay λ per entity | Users forget differently | Fit to re-query patterns |
| REINFORCE threshold (0.85) | Domain-specific | Thompson Sampling |
| EXTEND threshold (0.60) | Domain-specific | Thompson Sampling |
| DBSCAN eps | Per-space clustering needs | Cross-validation |
| Disambiguation weights (0.7/0.3) | Content type varies | Online learning |

### 2.2 Parameters That Should Stay Static

| Parameter | Why Static |
|-----------|------------|
| UCT exploration constant (√2) | Theoretical optimum |
| L2 normalization | Mathematical requirement |
| Shannon entropy formula | Information theory definition |
| Bayesian update rule | Mathematical definition |

### 2.3 Parameters Needing Research

| Parameter | Research Needed |
|-----------|-----------------|
| SimHash threshold (3 bits) | Corpus analysis for optimal value |
| Causality threshold (0.75) | Domain validation needed |
| PMI threshold (3.0) | Calibration study |
| Token bucket rates | User study |

---

## 3. Closed-Loop Enhancement Proposals

### 3.1 Proposal: Adaptive Thresholds via Thompson Sampling

**Problem**: REINFORCE threshold (0.85) is arbitrary.

**Solution**: Use Thompson Sampling (Bayesian bandit) to learn optimal threshold per entity/space.

```python
class AdaptiveThreshold:
    def __init__(self, prior_alpha=85, prior_beta=15):
        self.alpha = prior_alpha  # Prior: 85% success expectation
        self.beta = prior_beta

    def sample(self) -> float:
        """Sample threshold from Beta posterior."""
        return np.random.beta(self.alpha, self.beta)

    def update(self, success: bool):
        """Update posterior with feedback signal."""
        if success:
            self.alpha += 1
        else:
            self.beta += 1

    @property
    def expected_value(self) -> float:
        return self.alpha / (self.alpha + self.beta)
```

**Feedback Signal**:

- Success = Memory was queried and used correctly
- Failure = Memory miss or user correction

**Status**: 📋 Design Phase

---

### 3.2 Proposal: Per-Entity Decay Calibration

**Problem**: Same λ = 0.005 for all entities. Some entities (birthdays) should never decay. Some (casual mentions) should decay fast.

**Solution**: Learn λ per entity based on re-query patterns.

```python
class PersonalizedDecay:
    def learn_decay_rate(self, entity_id: str) -> float:
        # Query: how often is this entity re-accessed?
        # Frequent re-access = important = slow decay
        # Rare re-access = can decay faster

        access_pattern = self.db.query(
            "SELECT accessed_at FROM st_access_log WHERE entity_id = :id",
            {"id": entity_id}
        )

        # Fit exponential model to inter-access intervals
        intervals = compute_intervals(access_pattern)
        learned_lambda = fit_exponential(intervals)

        return learned_lambda
```

**Status**: 📋 Design Phase

---

### 3.3 Proposal: Query Regret Tracking

**Problem**: R3 prunes aggressively without knowing if pruned memories were needed later.

**Solution**: Track "regret" when P04 queries fail to find recently-pruned entities.

```python
class RegretTracker:
    async def on_query_miss(self, query: str, session_id: str):
        # Check if any recently-pruned entity would have matched
        pruned_matches = await self.db.query(
            """
            SELECT * FROM st_prune_log
            WHERE pruned_at > :recent
            AND embedding_similarity(:query_embedding, embedding) > 0.7
            """,
            {"recent": time.time() - 7*86400, "query_embedding": embed(query)}
        )

        if pruned_matches:
            # REGRET: We pruned too aggressively!
            for match in pruned_matches:
                await self.emit_feedback(
                    signal_type="PRUNE_REGRET",
                    entity_id=match.entity_id,
                    confidence=0.85
                )

                # Reduce decay lambda for this entity type
                await self.adjust_decay_lambda(
                    entity_type=match.entity_type,
                    adjustment=-0.001  # Slower decay
                )
```

**Status**: 📋 Design Phase

---

### 3.4 Proposal: Learnable Importance Weights

**Problem**: Fixed weights (0.35/0.25/0.20/0.20) don't adapt to user preferences.

**Solution**: Use gradient descent to learn weights from access patterns.

```python
class LearnableImportance(nn.Module):
    def __init__(self):
        super().__init__()
        self.weights = nn.Parameter(torch.tensor([0.35, 0.25, 0.20, 0.20]))

    def forward(self, emotional, recency, access, social):
        w = F.softmax(self.weights, dim=0)  # Ensure sum to 1
        return w[0]*emotional + w[1]*recency + w[2]*access + w[3]*social

    def train_step(self, events, future_accesses):
        """Train on: Did high-importance events get accessed later?"""
        optimizer = torch.optim.Adam(self.parameters(), lr=0.01)

        pred_importance = self(events.features)
        loss = F.mse_loss(pred_importance, future_accesses)

        loss.backward()
        optimizer.step()
```

**Ground Truth**: Correlation between predicted importance and actual future access count.

**Status**: 📋 Research Phase

---

### 3.5 Proposal: Implicit Feedback Collection

**Problem**: Users don't give explicit feedback. We need to infer from behavior.

**Solution**: Detect implicit signals from P04/K1 behavior.

| Behavior | Signal Type | Confidence | P03 Action |
|----------|-------------|------------|------------|
| User asked, got nothing | MEMORY_MISS | 0.8 | Lower threshold for topic |
| User rephrased query | REFORMULATION | 0.6 | Lower similarity threshold |
| User corrected response | CORRECTION | 0.9 | Split/merge entities |
| User confirmed memory | VALIDATION | 0.95 | Boost confidence |
| Session < 60s after query | ABANDONMENT | 0.5 | Flag for audit |
| LLM response was hedging | HEDGING | 0.4 | Lower confidence on source |

**New Table**: `st_implicit_feedback`

```sql
CREATE TABLE st_implicit_feedback (
    feedback_id TEXT PRIMARY KEY,
    signal_type TEXT NOT NULL,
    source_event_ids JSONB,
    target_entity_id TEXT,
    session_id TEXT,
    confidence REAL,
    processed BOOLEAN DEFAULT FALSE,
    created_at INTEGER NOT NULL
);
```

**Status**: 📋 Design Phase

---

## 4. Implementation Priority Matrix

| Enhancement | Impact | Effort | Risk | Priority |
|-------------|--------|--------|------|----------|
| **Feedback signal integration** | High | Medium | Low | **P0** |
| **Query miss regret tracking** | High | Low | Low | **P0** |
| **st_implicit_feedback table** | Medium | Low | Low | **P0** |
| **Thompson Sampling thresholds** | Medium | Medium | Medium | **P1** |
| **Per-entity decay calibration** | Medium | High | Medium | **P1** |
| **Learnable importance weights** | Medium | High | High | **P2** |
| **Online gradient learning** | Low | High | High | **P2** |

---

## 5. Research Notes

### 2025-12-24: Initial Analysis

**Observation**: P03 has 40+ tunable parameters across R1-R7. Approximately:

- 15 are definitely learnable (weights, thresholds)
- 10 are maybe learnable (bonuses, modifiers)
- 15 should stay static (mathematical constants)

**Key Insight from temp.md**:
> "Users give feedback constantly — just not explicitly. Every rephrase is feedback. Every short session is feedback. Every time the LLM hedges is feedback."

**Key Insight from FEEDBACK.md**:
> The K1→K0 feedback architecture already exists. P03 needs to consume `feedback.signal.P03` topic.

### Next Steps

1. [ ] Enumerate all feedback signals P03 should consume
2. [ ] Design `st_implicit_feedback` schema
3. [ ] Create P03 feedback handler
4. [ ] Implement Thompson Sampling prototype for REINFORCE threshold
5. [ ] Design per-entity decay learning experiment

---

## 6. Open Questions (Partitioned by Formula/Enhancement)

> **Format**: Each subsection contains open questions specific to that formula or enhancement.
> Mark questions as ✅ Resolved, 🔄 In Progress, or ❓ Open.

---

### 6.1 Importance Score Formula (R1)

```python
importance_score = 0.35×emotional + 0.25×recency + 0.20×access + 0.20×social
```

#### 6.1.1 Available Data Sources (Pre-P03)

| Source Table | Relevant Columns | Usage for Importance |
|--------------|------------------|----------------------|
| `st_hipp_events` | `sentiment_score`, `affect_valence`, `affect_arousal` | Emotional component |
| `st_hipp_events` | `event_time_utc`, `created_at` | Recency component |
| `st_hipp_events` | `salience_score`, `salience_band` | Current static importance (P02 output) |
| `st_hipp_events` | `num_participants`, `has_partner_present` | Social component |
| `st_vec` | `vector` (embedding) | Semantic similarity for access prediction |
| `st_feedback_signals` | `payload.grounded_event_ids` | Which events were actually used |
| `st_feedback_signals` | `signal_class=CORRECTION` | User disagreed with recall |
| `st_feedback_signals` | `signal_class=IMPLICIT` | Reformulation, abandonment |

#### 6.1.2 Feedback Loop Design

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                    IMPORTANCE SCORE FEEDBACK LOOP                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐     ┌──────────────────┐     ┌──────────────────────────┐ │
│  │ st_hipp_     │     │ P03 R1:          │     │ P04 Query               │ │
│  │ events       │────▶│ importance_score │────▶│ + K1 Response           │ │
│  │              │     │ (static weights) │     │                         │ │
│  └──────────────┘     └──────────────────┘     └───────────┬─────────────┘ │
│        ▲                                                   │               │
│        │                                                   ▼               │
│        │              ┌──────────────────┐     ┌──────────────────────────┐ │
│        │              │ P03 R1+:         │     │ K1 Feedback Detection   │ │
│        │              │ Learn weights    │◀────│ • MEMORY_GROUNDED       │ │
│        │              │ via gradient     │     │ • MEMORY_MISS           │ │
│        │              │ descent          │     │ • CORRECTION            │ │
│        └──────────────┴──────────────────┘     └──────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 6.1.3 Ground Truth Definition

**Primary Ground Truth**: Was this event recalled and *used* in a response?

```sql
-- Events that were grounded in K1 responses (SUCCESS)
SELECT
    e.event_id,
    e.sentiment_score,
    e.affect_valence,
    e.affect_arousal,
    e.num_participants,
    e.event_time_utc,
    1.0 AS ground_truth_important  -- WAS used
FROM st_hipp_events e
JOIN st_feedback_signals f
    ON e.event_id = ANY(f.correlation_ids->'grounded_event_ids')
WHERE f.signal_class = 'OUTCOME'
  AND f.payload->>'outcome_type' = 'MEMORY_GROUNDED';

-- Events that were recalled but NOT used (FAILURE)
SELECT
    e.event_id,
    0.0 AS ground_truth_important  -- Was recalled but NOT used
FROM st_hipp_events e
JOIN st_feedback_signals f
    ON e.event_id = ANY(f.correlation_ids->'event_ids')
WHERE f.signal_class = 'OUTCOME'
  AND e.event_id NOT IN (
      SELECT jsonb_array_elements_text(f.correlation_ids->'grounded_event_ids')
  );
```

#### 6.1.4 Feedback Signals for Importance

| Signal | Source | Interpretation | Weight Adjustment |
|--------|--------|----------------|-------------------|
| `MEMORY_GROUNDED` | K1 response | Event was useful | +1 to access component |
| `MEMORY_RECALLED_NOT_USED` | K1 response | Event was noise | -0.5 to importance |
| `MEMORY_MISS` | P04 query | Similar events should rank higher | Boost emotional/social |
| `USER_CORRECTION` | K1 explicit | Wrong event surfaced | -1 to this event, +1 to corrected |
| `REFORMULATION` | K1 implicit | First recall was poor | Lower threshold for topic |

#### 6.1.5 New Table: `st_importance_feedback`

```sql
-- Specialized feedback table for importance learning
CREATE TABLE st_importance_feedback (
    feedback_id       TEXT PRIMARY KEY,
    event_id          TEXT NOT NULL REFERENCES st_hipp_events(event_id),
    space_id          TEXT NOT NULL,

    -- Feature snapshot at recall time
    emotional_score   REAL NOT NULL,
    recency_score     REAL NOT NULL,
    access_score      REAL NOT NULL,
    social_score      REAL NOT NULL,
    predicted_importance REAL NOT NULL,

    -- Outcome (ground truth)
    was_grounded      BOOLEAN NOT NULL,  -- Did K1 use this event?
    user_validated    BOOLEAN,           -- Did user confirm? (NULL = no signal)

    -- Learning metadata
    session_id        TEXT NOT NULL,
    feedback_source   TEXT NOT NULL,     -- 'OUTCOME', 'CORRECTION', 'IMPLICIT'
    created_at        BIGINT NOT NULL,

    -- Indexes for batch learning
    INDEX idx_importance_fb_space (space_id, created_at),
    INDEX idx_importance_fb_grounded (was_grounded)
);
```

#### 6.1.6 Learning Algorithm

```python
class ImportanceWeightLearner:
    """Learn importance weights from feedback signals."""

    def __init__(self, space_id: str):
        self.space_id = space_id
        # Start with static prior
        self.weights = torch.tensor([0.35, 0.25, 0.20, 0.20], requires_grad=True)
        self.optimizer = torch.optim.Adam([self.weights], lr=0.01)
        self.min_samples = 500  # Don't learn until we have enough data

    async def collect_training_data(self, db) -> tuple[Tensor, Tensor]:
        """Collect (features, labels) from st_importance_feedback."""
        rows = await db.fetch_all("""
            SELECT
                emotional_score, recency_score, access_score, social_score,
                CASE WHEN was_grounded THEN 1.0 ELSE 0.0 END AS label
            FROM st_importance_feedback
            WHERE space_id = :space_id
              AND created_at > :cutoff
        """, {"space_id": self.space_id, "cutoff": time.time() - 30*86400})

        if len(rows) < self.min_samples:
            return None, None  # Not enough data, use static weights

        features = torch.tensor([[r.emotional_score, r.recency_score,
                                  r.access_score, r.social_score] for r in rows])
        labels = torch.tensor([r.label for r in rows])
        return features, labels

    def train_step(self, features: Tensor, labels: Tensor) -> float:
        """One gradient descent step."""
        self.optimizer.zero_grad()

        # Softmax to ensure weights sum to 1
        w = F.softmax(self.weights, dim=0)
        predictions = (features * w).sum(dim=1)

        # Binary cross-entropy: predict "will this be grounded?"
        loss = F.binary_cross_entropy_with_logits(predictions, labels)

        loss.backward()
        self.optimizer.step()

        return loss.item()

    def get_current_weights(self) -> dict[str, float]:
        """Return current learned weights."""
        w = F.softmax(self.weights, dim=0).detach().numpy()
        return {
            "emotional": float(w[0]),
            "recency": float(w[1]),
            "access": float(w[2]),
            "social": float(w[3]),
        }
```

#### 6.1.7 Integration with P03 R1

```python
# In P03 R1 phase: Use learned weights if available
async def compute_importance(event: HippEvent, space_id: str) -> float:
    """Compute importance with learned or static weights."""

    # Check if we have learned weights for this space
    learned = await weight_store.get_weights(space_id)

    if learned and learned.sample_count >= 500:
        weights = learned.weights
    else:
        # Fall back to static prior
        weights = {"emotional": 0.35, "recency": 0.25, "access": 0.20, "social": 0.20}

    # Compute components
    emotional = compute_emotional(event)  # Uses sentiment_score, affect_*
    recency = compute_recency(event)      # Uses event_time_utc
    access = compute_access(event)        # Uses access_count (needs st_access_log)
    social = compute_social(event)        # Uses num_participants, relationships

    return (
        weights["emotional"] * emotional +
        weights["recency"] * recency +
        weights["access"] * access +
        weights["social"] * social
    )
```

#### 6.1.8 Open Questions

| # | Question | Status | Proposed Answer | Notes |
|---|----------|--------|-----------------|-------|
| 1 | How do we get ground truth for importance scoring? | 🔄 In Progress | Correlation with `was_grounded` from K1 | See 6.1.3 above |
| 2 | Should weights be per-user or global? | 🔄 In Progress | Per-space with global fallback | Cold start: use static until 500 samples |
| 3 | What's the minimum training data before learning weights? | ✅ Resolved | 500 events with grounding feedback | Configurable via `P03_IMPORTANCE_MIN_SAMPLES` |
| 4 | How do we handle events with missing affect/sentiment? | ✅ Resolved | P02 already provides defaults: `valence=0.5`, `arousal=0.3` | See `k0/modules/affect/analyze.py` lines 66-67 |
| 5 | Should recency λ (0.05) be learned per-user? | ❓ Open | Yes, based on re-query patterns | Some users value history more |
| 6 | What's the access_count source (st_access_log missing)? | ❓ Open | Use `st_feedback_signals` grounding events as proxy | Count `MEMORY_GROUNDED` signals per event |
| 7 | How often do we retrain weights? | ✅ Resolved | Nightly P03 run (batch) | Loaded at kernel bootup, persisted to `st_learned_weights` |
| 8 | How do we handle weight drift over time? | ✅ Resolved | Sliding window + momentum (see 6.1.10) | 30-day window, momentum=0.9 |

#### 6.1.9 Hybrid Kernel Architecture (Weight Sync)

> **Context**: K0 is a hybrid kernel — can run on user device OR cloud. Per ADR-0050c, family devices sync via CRDT.

```text
┌────────────────────────────────────────────────────────────────────────────┐
│              IMPORTANCE WEIGHT LIFECYCLE (Hybrid Kernel)                   │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌─────────────────────┐                    ┌────────────────────────────┐ │
│  │ KERNEL BOOTUP       │                    │ NIGHTLY P03 RUN            │ │
│  │                     │                    │                            │ │
│  │ 1. Load weights     │                    │ 1. Collect feedback        │ │
│  │    from st_learned_ │                    │    from st_importance_     │ │
│  │    weights          │                    │    feedback (30-day)       │ │
│  │                     │                    │                            │ │
│  │ 2. If missing:      │                    │ 2. Train gradient step     │ │
│  │    use static prior │◀───────────────────│    with momentum           │ │
│  │    (0.35/0.25/...)  │     PERSIST        │                            │ │
│  │                     │                    │ 3. Write to st_learned_    │ │
│  │ 3. Cache in memory  │                    │    weights                 │ │
│  │    for R1 scoring   │                    │                            │ │
│  └─────────────────────┘                    └────────────────────────────┘ │
│          │                                             │                   │
│          │ DEVICE-TO-DEVICE SYNC (ADR-0050c)           │                   │
│          ▼                                             ▼                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ CRDT MERGE (Last-Write-Wins)                                        │   │
│  │                                                                     │   │
│  │ • st_learned_weights is CRDT-synced across family devices          │   │
│  │ • LAN sync: <50ms latency (mDNS discovery)                         │   │
│  │ • Internet sync: <500ms (P2P E2EE, Phase 2)                        │   │
│  │ • Conflict resolution: Most recent training timestamp wins         │   │
│  │ • Each device can learn locally, sync merges best weights          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

**Key Design Points**:

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| **Learning location** | Per-device, nightly | Each device has local feedback |
| **Weight storage** | `st_learned_weights` table | Persists across kernel restarts |
| **Sync mechanism** | CRDT (LWW by timestamp) | ADR-0050c compliant |
| **Bootup behavior** | Load cached weights | No cold-start latency |
| **Fallback** | Static prior if no learned weights | Graceful degradation |
| **Sync scope** | Per-space weights | Different spaces can have different weights |

#### 6.1.10 Weight Drift Handling Strategy

> **Problem**: User preferences change over time. Old feedback may not reflect current behavior.

**Solution: Sliding Window + Exponential Decay + Momentum**

```python
class WeightDriftHandler:
    """Handle weight drift with sliding window and momentum."""

    def __init__(
        self,
        window_days: int = 30,           # Only use last 30 days of feedback
        sample_decay_lambda: float = 0.1, # Exponential decay on older samples
        momentum: float = 0.9,            # Smooth weight updates
    ):
        self.window_days = window_days
        self.sample_decay_lambda = sample_decay_lambda
        self.momentum = momentum
        self.velocity = torch.zeros(4)    # Momentum velocity for weights

    def compute_sample_weight(self, days_ago: float) -> float:
        """Weight older samples less in training."""
        return math.exp(-self.sample_decay_lambda * days_ago)

    async def collect_weighted_samples(self, db, space_id: str):
        """Collect samples with recency-based weights."""
        cutoff = time.time() - (self.window_days * 86400)

        rows = await db.fetch_all("""
            SELECT
                emotional_score, recency_score, access_score, social_score,
                was_grounded,
                (EXTRACT(EPOCH FROM NOW()) - created_at) / 86400.0 AS days_ago
            FROM st_importance_feedback
            WHERE space_id = :space_id
              AND created_at > :cutoff
            ORDER BY created_at DESC
        """, {"space_id": space_id, "cutoff": cutoff})

        # Apply exponential decay to sample weights
        features, labels, weights = [], [], []
        for r in rows:
            features.append([r.emotional_score, r.recency_score,
                            r.access_score, r.social_score])
            labels.append(1.0 if r.was_grounded else 0.0)
            weights.append(self.compute_sample_weight(r.days_ago))

        return (
            torch.tensor(features),
            torch.tensor(labels),
            torch.tensor(weights),  # Per-sample weights
        )

    def train_with_momentum(
        self,
        current_weights: Tensor,
        gradients: Tensor,
        learning_rate: float = 0.01,
    ) -> Tensor:
        """Update weights with momentum to smooth drift."""
        # Momentum update: v = momentum * v + gradient
        self.velocity = self.momentum * self.velocity + gradients

        # Weight update: w = w - lr * v
        new_weights = current_weights - learning_rate * self.velocity

        # Ensure weights sum to 1 via softmax
        return F.softmax(new_weights, dim=0)
```

**Drift Detection Metrics**:

```python
# Emit metrics for weight drift monitoring
metrics = {
    "p03_importance_weight_emotional": weights["emotional"],
    "p03_importance_weight_recency": weights["recency"],
    "p03_importance_weight_access": weights["access"],
    "p03_importance_weight_social": weights["social"],
    "p03_importance_weight_drift_30d": euclidean_distance(weights, prior_weights),
    "p03_importance_training_samples": len(samples),
    "p03_importance_training_loss": loss,
}
```

**Drift Alerting**:

| Metric | Threshold | Action |
|--------|-----------|--------|
| `weight_drift_30d > 0.3` | Large drift | Log warning, notify admin |
| `training_samples < 100` | Low data | Skip training, use prior |
| `training_loss > 0.5` | Poor fit | Investigate feature quality |

#### 6.1.11 Implementation Checklist

- [ ] Create `st_importance_feedback` table (Alembic migration)
- [ ] Create `st_learned_weights` table for weight persistence
- [ ] Implement `ImportanceWeightLearner` class with momentum
- [ ] Implement `WeightDriftHandler` with sliding window
- [ ] Subscribe P03 to `feedback.signal.p03` topic
- [ ] Implement feedback handler: `on_memory_grounded()`, `on_memory_miss()`
- [ ] Add feature flag: `P03_FF_IMPORTANCE_LEARNING=enabled`
- [ ] Add metrics: `p03_importance_weights_*`, `p03_importance_drift_*`
- [ ] Add CRDT sync for `st_learned_weights` (ADR-0050c)
- [ ] Write integration test with golden dataset
- [ ] Add bootup weight loading in kernel startup

---

### 6.2 Hebbian Weight Update (R1)

```python
new_weight = current_weight + learning_rate × (max_weight - current_weight) × event_importance
```

#### 6.2.1 Scientific Foundation

> **Hebb's Rule (1949)**: "Neurons that fire together, wire together."
>
> In P03 context: Entities that co-occur in events should have stronger associations.
> The inverse (anti-Hebbian) also applies: Entities that appear separately should weaken.

**Current Implementation** (from `st_kg_edges`):

```sql
-- Existing columns in st_kg_edges
edge_weight REAL DEFAULT 1.0,          -- Relationship strength
co_occurrence_count INTEGER DEFAULT 1, -- How often seen together
decay_factor REAL DEFAULT 1.0,         -- Forgetting over time
```

**Full Association Strength Formula** (Section 2.4 of dossier):

```python
association_strength = (
    co_occurrence_count                           # How often entities appear together
  × exp(-λ_temporal × avg_time_gap_hours)         # Temporal proximity bonus (λ=0.01)
  × (unique_contexts / total_contexts)            # Context diversity bonus
  × (1 + avg_sentiment_score)                     # Emotional significance
)
```

#### 6.2.2 Problems with Current Static Approach

| Problem | Impact | Proposed Solution |
|---------|--------|-------------------|
| Fixed `learning_rate=0.1` | Over-reinforces new, under-reinforces old | Adaptive rate based on edge maturity |
| No negative learning | Conflicting entities stay associated | Anti-Hebbian decay for non-co-occurrence |
| Unbounded co-occurrence | Frequent pairs dominate | Log-scale capping |
| No user feedback | Wrong associations persist | Feedback-driven correction |

#### 6.2.3 Adaptive Learning Rate Design

**Principle**: New relationships should learn fast, established ones should be stable.

```python
class AdaptiveHebbianLearner:
    """Hebbian learning with adaptive rate based on relationship maturity."""

    def __init__(self):
        # Learning rate bounds
        self.lr_new = 0.3        # Fast learning for new edges (< 5 co-occurrences)
        self.lr_mature = 0.05    # Slow learning for mature edges (> 50 co-occurrences)
        self.lr_decay = 0.1      # Rate at which learning rate decreases

        # Weight bounds
        self.max_weight = 1.0
        self.min_weight = 0.0
        self.prune_threshold = 0.05  # Below this, edge is candidate for deletion

    def compute_learning_rate(self, co_occurrence_count: int) -> float:
        """
        Adaptive learning rate: fast for new, slow for established.

        Formula: lr = lr_mature + (lr_new - lr_mature) × exp(-decay × count)

        Co-occurrences | Learning Rate
        --------------|---------------
        1             | 0.28 (fast)
        5             | 0.19
        10            | 0.12
        25            | 0.06
        50+           | 0.05 (slow, stable)
        """
        return self.lr_mature + (self.lr_new - self.lr_mature) * math.exp(
            -self.lr_decay * co_occurrence_count
        )

    def hebbian_update(
        self,
        current_weight: float,
        co_occurrence_count: int,
        event_importance: float,
    ) -> float:
        """
        Update edge weight using adaptive Hebbian rule.

        Hebbian: Δw = lr × (max - current) × importance
        - Saturates as weight approaches max (prevents runaway)
        - Faster learning for new edges
        - Importance-weighted (high-importance events matter more)
        """
        lr = self.compute_learning_rate(co_occurrence_count)
        delta = lr * (self.max_weight - current_weight) * event_importance
        return min(self.max_weight, current_weight + delta)
```

#### 6.2.4 Anti-Hebbian Learning (Conflict Handling)

**Principle**: "Cells that fire apart, unwire" — entities that appear in conflicting contexts should weaken.

**Conflict Signals**:

| Signal | Source | Interpretation |
|--------|--------|----------------|
| `ENTITY_MERGE_REJECTED` | P06/User | User said these are NOT the same entity |
| `ASSOCIATION_WRONG` | K1 Correction | User corrected an inferred relationship |
| `MUTUAL_EXCLUSION` | P04 Query | Entities never co-occur despite many opportunities |
| `CONTRADICTION` | P03 R7 | New fact contradicts existing association |

```python
class AntiHebbianDecay:
    """Weaken associations for conflicting entities."""

    def __init__(self):
        self.anti_lr = 0.15           # Faster than positive learning (mistakes hurt)
        self.conflict_penalty = 0.3   # Additional penalty for explicit conflicts
        self.min_weight = 0.0
        self.prune_threshold = 0.05

    def anti_hebbian_update(
        self,
        current_weight: float,
        conflict_type: str,
        confidence: float,
    ) -> float:
        """
        Decrease edge weight for conflicting entities.

        Anti-Hebbian: Δw = -lr × current × confidence × penalty_multiplier
        """
        penalty = self.conflict_penalty if conflict_type == 'EXPLICIT_CORRECTION' else 1.0
        delta = -self.anti_lr * current_weight * confidence * penalty
        new_weight = max(self.min_weight, current_weight + delta)

        if new_weight < self.prune_threshold:
            return None  # Signal edge should be pruned
        return new_weight

    def detect_mutual_exclusion(
        self,
        entity_a: str,
        entity_b: str,
        window_days: int = 30,
    ) -> float | None:
        """
        Detect entities that should co-occur but don't.

        Mutual exclusion score = 1 - (actual_co_occurrences / expected_co_occurrences)

        Expected = min(appearances_a, appearances_b) × baseline_rate
        If entities appear often but never together → likely mutually exclusive.
        """
        # This would query st_hipp_events for co-occurrence patterns
        # Return None if not enough data, else return exclusion score [0, 1]
        pass
```

#### 6.2.5 Log-Scale Co-occurrence Capping

**Problem**: Entities that appear together 1000 times shouldn't be 1000× stronger than those appearing 10 times.

**Solution**: Log-scale normalization after threshold.

```python
def normalize_co_occurrence(count: int, cap_threshold: int = 50) -> float:
    """
    Normalize co-occurrence count to prevent dominant pairs.

    count ≤ threshold: linear (1:1 mapping)
    count > threshold: log-scale

    Examples:
    count=10  → 10.0
    count=50  → 50.0
    count=100 → 50 + ln(100/50) × 50 = 50 + 34.7 = 84.7
    count=500 → 50 + ln(500/50) × 50 = 50 + 115.1 = 165.1
    count=1000 → 50 + ln(1000/50) × 50 = 50 + 149.8 = 199.8
    """
    if count <= cap_threshold:
        return float(count)
    return cap_threshold + math.log(count / cap_threshold) * cap_threshold
```

#### 6.2.6 Feedback Loop Design

```text
┌────────────────────────────────────────────────────────────────────────────┐
│                    HEBBIAN FEEDBACK LOOP                                   │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌──────────────┐     ┌──────────────────┐     ┌─────────────────────────┐ │
│  │ st_kg_edges  │     │ P03 R1:          │     │ P04 Query               │ │
│  │              │────▶│ Hebbian update   │────▶│ + K1 Inference          │ │
│  │ edge_weight  │     │ co_occurrence++  │     │ "X is related to Y"     │ │
│  └──────────────┘     └──────────────────┘     └───────────┬─────────────┘ │
│        ▲                                                   │               │
│        │                                                   ▼               │
│  ┌─────┴────────────────────────────────────────────────────────────────┐  │
│  │                      FEEDBACK SIGNALS                                │  │
│  │                                                                      │  │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐   │  │
│  │  │ CO_OCCURRENCE   │  │ ASSOCIATION_    │  │ ENTITY_MERGE_       │   │  │
│  │  │ (Implicit)      │  │ CONFIRMED       │  │ REJECTED            │   │  │
│  │  │                 │  │ (Explicit)      │  │ (Anti-Hebbian)      │   │  │
│  │  │ +Hebbian update │  │ +Strong boost   │  │ -Decay + flag       │   │  │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────────┘   │  │
│  │                                                                      │  │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐   │  │
│  │  │ RELATIONSHIP_   │  │ MUTUAL_         │  │ EDGE_USED_IN_       │   │  │
│  │  │ USED            │  │ EXCLUSION       │  │ RESPONSE            │   │  │
│  │  │ (P04 grounded)  │  │ (Never co-occur)│  │ (K1 grounded)       │   │  │
│  │  │                 │  │                 │  │                     │   │  │
│  │  │ +Reinforcement  │  │ -Prune          │  │ +Strong boost       │   │  │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────────┘   │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

#### 6.2.7 Feedback Signals for Hebbian Learning

| Signal | Source | Confidence | Hebbian Action |
|--------|--------|------------|----------------|
| `CO_OCCURRENCE` | P02 event ingestion | 1.0 | `hebbian_update(+)` with importance |
| `EDGE_USED_IN_RESPONSE` | K1 grounding | 0.9 | `boost_weight(+0.1)` |
| `ASSOCIATION_CONFIRMED` | User explicit "Yes" | 0.95 | `boost_weight(+0.15)` |
| `ASSOCIATION_WRONG` | User correction | 0.9 | `anti_hebbian_update(-0.3)` |
| `ENTITY_MERGE_REJECTED` | P06 / User | 0.85 | `flag_as_distinct()`, `anti_hebbian_update(-0.2)` |
| `MUTUAL_EXCLUSION` | P03 pattern detection | 0.7 | `candidate_for_prune()` |
| `TEMPORAL_DECAY` | P03 R3 nightly | 1.0 | `decay_factor × 0.99` per day |

#### 6.2.8 New Table: `st_hebbian_feedback`

```sql
-- Specialized feedback table for Hebbian learning
CREATE TABLE st_hebbian_feedback (
    feedback_id       TEXT PRIMARY KEY,

    -- Edge identification
    source_entity_id  TEXT NOT NULL,
    target_entity_id  TEXT NOT NULL,
    space_id          TEXT NOT NULL,

    -- Signal details
    signal_type       TEXT NOT NULL,     -- 'CO_OCCURRENCE', 'EDGE_USED', 'CORRECTION', etc.
    signal_source     TEXT NOT NULL,     -- 'P02', 'P03', 'P04', 'K1', 'USER'
    confidence        REAL NOT NULL,

    -- Context snapshot
    event_importance  REAL,              -- Importance of triggering event
    co_occurrence_at_signal INTEGER,     -- co_occurrence_count when signal received
    weight_before     REAL NOT NULL,     -- Edge weight before update
    weight_after      REAL NOT NULL,     -- Edge weight after update
    learning_rate_used REAL,             -- Adaptive LR that was applied

    -- Processing
    processed         BOOLEAN DEFAULT FALSE,
    processed_at      BIGINT,

    -- Audit
    session_id        TEXT,
    created_at        BIGINT NOT NULL,

    FOREIGN KEY (source_entity_id) REFERENCES st_kg_dom(entity_id),
    FOREIGN KEY (target_entity_id) REFERENCES st_kg_dom(entity_id)
);

CREATE INDEX idx_hebbian_fb_edge ON st_hebbian_feedback(source_entity_id, target_entity_id);
CREATE INDEX idx_hebbian_fb_unprocessed ON st_hebbian_feedback(processed, created_at)
    WHERE processed = FALSE;
CREATE INDEX idx_hebbian_fb_signal ON st_hebbian_feedback(signal_type, created_at);
```

#### 6.2.9 Integration with `st_learned_weights`

> **Reuse**: The `st_learned_weights` table from 6.1 also stores Hebbian hyperparameters.

```sql
-- Add Hebbian parameters to st_learned_weights
-- weight_type = 'HEBBIAN_PARAMS'

INSERT INTO st_learned_weights (
    weight_id,
    space_id,
    weight_type,
    weight_key,
    weight_value,
    sample_count,
    last_trained_at,
    created_at,
    updated_at
) VALUES
    (uuid(), :space_id, 'HEBBIAN_PARAMS', 'lr_new', 0.30, 0, now(), now(), now()),
    (uuid(), :space_id, 'HEBBIAN_PARAMS', 'lr_mature', 0.05, 0, now(), now(), now()),
    (uuid(), :space_id, 'HEBBIAN_PARAMS', 'lr_decay', 0.10, 0, now(), now(), now()),
    (uuid(), :space_id, 'HEBBIAN_PARAMS', 'anti_lr', 0.15, 0, now(), now(), now()),
    (uuid(), :space_id, 'HEBBIAN_PARAMS', 'cap_threshold', 50.0, 0, now(), now(), now()),
    (uuid(), :space_id, 'HEBBIAN_PARAMS', 'prune_threshold', 0.05, 0, now(), now(), now());
```

#### 6.2.10 Learning Hebbian Hyperparameters

**Ground Truth**: Was the edge used correctly in K1 response?

```python
class HebbianHyperparamLearner:
    """Learn optimal Hebbian hyperparameters from feedback."""

    def __init__(self, space_id: str):
        self.space_id = space_id
        self.min_samples = 200  # Need sufficient feedback history

    async def evaluate_hyperparams(self, db) -> dict:
        """
        Evaluate current hyperparameters based on feedback outcomes.

        Metrics:
        - Precision: Edges used in response / Edges surfaced
        - Recall: Relevant edges surfaced / Relevant edges available
        - False positive rate: Wrong associations used
        - Prune accuracy: Pruned edges that should have been kept
        """
        rows = await db.fetch_all("""
            SELECT
                signal_type,
                weight_before,
                weight_after,
                -- Was this edge later used successfully?
                EXISTS(
                    SELECT 1 FROM st_hebbian_feedback f2
                    WHERE f2.source_entity_id = f.source_entity_id
                      AND f2.target_entity_id = f.target_entity_id
                      AND f2.signal_type = 'EDGE_USED_IN_RESPONSE'
                      AND f2.created_at > f.created_at
                ) AS was_useful
            FROM st_hebbian_feedback f
            WHERE space_id = :space_id
              AND created_at > :cutoff
        """, {"space_id": self.space_id, "cutoff": time.time() - 30*86400})

        # Compute metrics and suggest hyperparameter adjustments
        return self._analyze_outcomes(rows)

    def _suggest_adjustments(self, metrics: dict) -> dict:
        """
        Suggest hyperparameter changes based on metrics.

        High false positive → Lower lr_new, increase anti_lr
        High false negative → Raise lr_new, lower prune_threshold
        Too many prunes → Raise prune_threshold
        """
        suggestions = {}

        if metrics['false_positive_rate'] > 0.15:
            suggestions['lr_new'] = 'decrease by 0.05'
            suggestions['anti_lr'] = 'increase by 0.02'

        if metrics['false_negative_rate'] > 0.20:
            suggestions['lr_new'] = 'increase by 0.03'
            suggestions['prune_threshold'] = 'decrease by 0.01'

        return suggestions
```

#### 6.2.11 Open Questions

| # | Question | Status | Proposed Answer | Notes |
|---|----------|--------|-----------------|-------|
| 1 | Should learning_rate (0.1) be adaptive? | ✅ Resolved | Yes, adaptive: 0.3 (new) → 0.05 (mature) | Exponential decay based on co-occurrence count |
| 2 | How do we handle negative associations (conflicts)? | ✅ Resolved | Anti-Hebbian learning with separate decay | `anti_lr=0.15`, faster than positive learning |
| 3 | Should we cap co-occurrence count? | ✅ Resolved | Yes, log-scale after 50 co-occurrences | Prevents dominant pairs |
| 4 | How do we detect mutual exclusion? | ✅ Resolved | SQL query on `st_hipp_events.entities_json` | See 6.2.13 below |
| 5 | Should we prune very weak edges? | ✅ Resolved | Yes, use existing `archival_status` lifecycle | ACTIVE → ARCHIVED → TOMBSTONE (see 6.2.14) |
| 6 | How do we handle edge resurrection? | ✅ Resolved | Check `archival_status` before insert, restore if ARCHIVED | See 6.2.15 below |

#### 6.2.12 Implementation Checklist

- [ ] Create `st_hebbian_feedback` table (Alembic migration)
- [ ] Add Hebbian parameters to `st_learned_weights`
- [ ] Implement `AdaptiveHebbianLearner` class
- [ ] Implement `AntiHebbianDecay` class
- [ ] Implement `normalize_co_occurrence()` function
- [ ] Subscribe to `feedback.signal.p03` for edge-related signals
- [ ] Implement edge pruning in P03 R3 (SWS phase)
- [ ] Add mutual exclusion detection (P03 R4)
- [ ] Add feature flag: `P03_FF_ADAPTIVE_HEBBIAN=enabled`
- [ ] Add metrics: `p03_hebbian_updates`, `p03_anti_hebbian_updates`, `p03_edges_pruned`
- [ ] Add CRDT sync for `st_kg_edges` weight updates (ADR-0050c)
- [ ] Write integration test with entity co-occurrence patterns

#### 6.2.13 Mutual Exclusion Detection (Q4 Resolution)

> **Feasibility**: ✅ Fully supported by existing schema

**Data Sources**:

- `st_hipp_events.entities_json` — Contains extracted entities per event
- `st_kg_edges` — Existing edges with `co_occurrence_count`

**Algorithm**:

```python
async def detect_mutual_exclusion(
    db,
    entity_a: str,
    entity_b: str,
    space_id: str,
    window_days: int = 30,
) -> tuple[float, bool]:
    """
    Detect if two entities should co-occur but don't.

    Returns: (exclusion_score, is_mutually_exclusive)

    Exclusion score = 1 - (actual / expected)
    - Score > 0.8 with sufficient data → mutually exclusive
    """
    cutoff = int((time.time() - window_days * 86400) * 1000)  # ms epoch

    # Count individual appearances
    result = await db.fetch_one("""
        WITH entity_appearances AS (
            SELECT
                event_id,
                entities_json::jsonb AS entities
            FROM st_hipp_events
            WHERE space_id = :space_id
              AND event_time_utc > :cutoff
        ),
        counts AS (
            SELECT
                COUNT(*) FILTER (WHERE entities @> :entity_a_json) AS count_a,
                COUNT(*) FILTER (WHERE entities @> :entity_b_json) AS count_b,
                COUNT(*) FILTER (
                    WHERE entities @> :entity_a_json
                      AND entities @> :entity_b_json
                ) AS count_both,
                COUNT(*) AS total_events
            FROM entity_appearances
        )
        SELECT
            count_a, count_b, count_both, total_events,
            -- Expected co-occurrence under independence assumption
            CASE WHEN total_events > 0
                THEN (count_a::float / total_events) * (count_b::float / total_events) * total_events
                ELSE 0
            END AS expected_co_occurrence
        FROM counts
    """, {
        "space_id": space_id,
        "cutoff": cutoff,
        "entity_a_json": json.dumps([{"entity_id": entity_a}]),
        "entity_b_json": json.dumps([{"entity_id": entity_b}]),
    })

    if not result or result.total_events < 50:
        return (0.0, False)  # Not enough data

    expected = max(result.expected_co_occurrence, 1.0)  # Avoid div by zero
    actual = result.count_both

    exclusion_score = 1.0 - (actual / expected)

    # Mutual exclusion if:
    # - High exclusion score (> 0.8)
    # - Both entities appear frequently (> 5 times each)
    # - They never or rarely co-occur
    is_exclusive = (
        exclusion_score > 0.8
        and result.count_a >= 5
        and result.count_b >= 5
        and result.count_both <= 1
    )

    return (exclusion_score, is_exclusive)
```

**Integration with P03 R4**:

```python
# In P03 R4 (KG Consolidation), detect mutual exclusion for existing edges
async def audit_edges_for_mutual_exclusion(db, space_id: str):
    """Flag edges that show mutual exclusion pattern."""

    edges = await db.fetch_all("""
        SELECT edge_id, source_entity_id, target_entity_id
        FROM st_kg_edges
        WHERE space_id = :space_id
          AND archival_status = 'ACTIVE'
          AND edge_weight > 0.1  -- Only check non-trivial edges
    """, {"space_id": space_id})

    for edge in edges:
        score, is_exclusive = await detect_mutual_exclusion(
            db, edge.source_entity_id, edge.target_entity_id, space_id
        )

        if is_exclusive:
            # Emit feedback signal for anti-Hebbian decay
            await emit_feedback(
                signal_type="MUTUAL_EXCLUSION",
                source_entity_id=edge.source_entity_id,
                target_entity_id=edge.target_entity_id,
                confidence=score,
            )
```

#### 6.2.14 Edge Pruning via Existing Lifecycle (Q5 Resolution)

> **Feasibility**: ✅ Already implemented in `st_kg_edges.archival_status`

**Existing Lifecycle** (from P03 dossier Section 2.4):

```text
ACTIVE → ARCHIVED → TOMBSTONE

Transitions:
- edge_weight < 0.1 AND decay_factor < 0.1 → ARCHIVED
- decay_factor < 0.01 → TOMBSTONE
- TOMBSTONE + 90 days → DELETE (hard delete)
```

**Integration with Hebbian Pruning**:

```python
class EdgeLifecycleManager:
    """Manage edge lifecycle with Hebbian-aware thresholds."""

    # Thresholds (learnable via st_learned_weights)
    ARCHIVE_WEIGHT_THRESHOLD = 0.1     # edge_weight below this
    ARCHIVE_DECAY_THRESHOLD = 0.1      # decay_factor below this
    TOMBSTONE_DECAY_THRESHOLD = 0.01   # decay_factor for tombstone
    PRUNE_WEIGHT_THRESHOLD = 0.05      # Hebbian prune threshold

    async def apply_lifecycle_transitions(self, db, space_id: str):
        """Run in P03 R3 (SWS phase) nightly."""

        # 1. Apply Hebbian prune threshold → mark as candidate
        await db.execute("""
            UPDATE st_kg_edges
            SET archival_status = 'ARCHIVED',
                updated_at = :now
            WHERE space_id = :space_id
              AND archival_status = 'ACTIVE'
              AND edge_weight < :prune_threshold
              AND decay_factor < :archive_decay
        """, {
            "space_id": space_id,
            "now": int(time.time() * 1000),
            "prune_threshold": self.PRUNE_WEIGHT_THRESHOLD,
            "archive_decay": self.ARCHIVE_DECAY_THRESHOLD,
        })

        # 2. ARCHIVED → TOMBSTONE if decay continues
        await db.execute("""
            UPDATE st_kg_edges
            SET archival_status = 'TOMBSTONE',
                updated_at = :now
            WHERE space_id = :space_id
              AND archival_status = 'ARCHIVED'
              AND decay_factor < :tombstone_decay
        """, {
            "space_id": space_id,
            "now": int(time.time() * 1000),
            "tombstone_decay": self.TOMBSTONE_DECAY_THRESHOLD,
        })

        # 3. Log to st_hebbian_feedback for audit
        # (pruned edges are logged before transition)
```

**Safety Net**: Edges are ARCHIVED first, not deleted. This allows resurrection.

#### 6.2.15 Edge Resurrection (Q6 Resolution)

> **Feasibility**: ✅ Check before insert, restore ARCHIVED edges

**Scenario**: Entity A and B were pruned (ARCHIVED) but appear together in a new event.

**Solution**: P02 event ingestion → P03 R1 co-occurrence detection checks for archived edges.

```python
class EdgeResurrectionHandler:
    """Handle resurrection of archived edges on new co-occurrence."""

    RESURRECTION_WEIGHT = 0.3  # Boosted initial weight (not 0.0, not 1.0)

    async def on_co_occurrence(
        self,
        db,
        source_entity_id: str,
        target_entity_id: str,
        space_id: str,
        event_importance: float,
    ):
        """Called when two entities co-occur in a new event."""

        # Check if edge exists (any status)
        existing = await db.fetch_one("""
            SELECT edge_id, archival_status, edge_weight, co_occurrence_count
            FROM st_kg_edges
            WHERE source_entity_id = :source
              AND target_entity_id = :target
              AND space_id = :space_id
            ORDER BY
                CASE archival_status
                    WHEN 'ACTIVE' THEN 1
                    WHEN 'ARCHIVED' THEN 2
                    WHEN 'TOMBSTONE' THEN 3
                END
            LIMIT 1
        """, {
            "source": source_entity_id,
            "target": target_entity_id,
            "space_id": space_id,
        })

        now = int(time.time() * 1000)

        if existing is None:
            # No edge exists → CREATE new edge
            await self._create_edge(db, source_entity_id, target_entity_id,
                                   space_id, event_importance, now)
            return "CREATED"

        elif existing.archival_status == 'ACTIVE':
            # Active edge → normal Hebbian update
            await self._hebbian_update(db, existing.edge_id, event_importance)
            return "UPDATED"

        elif existing.archival_status == 'ARCHIVED':
            # RESURRECT: Restore with boosted weight
            await db.execute("""
                UPDATE st_kg_edges
                SET archival_status = 'ACTIVE',
                    edge_weight = :resurrection_weight,
                    decay_factor = 1.0,
                    co_occurrence_count = co_occurrence_count + 1,
                    last_observed_at = :now,
                    updated_at = :now
                WHERE edge_id = :edge_id
            """, {
                "edge_id": existing.edge_id,
                "resurrection_weight": self.RESURRECTION_WEIGHT,
                "now": now,
            })

            # Log resurrection event
            await self._log_resurrection(db, existing.edge_id, space_id)
            return "RESURRECTED"

        elif existing.archival_status == 'TOMBSTONE':
            # Tombstone → Create NEW edge (old one is dead)
            # But inherit some history? Or fresh start?
            await self._create_edge(db, source_entity_id, target_entity_id,
                                   space_id, event_importance, now,
                                   inherited_count=existing.co_occurrence_count)
            return "RECREATED_FROM_TOMBSTONE"

    async def _log_resurrection(self, db, edge_id: str, space_id: str):
        """Log resurrection to st_hebbian_feedback for analysis."""
        await db.execute("""
            INSERT INTO st_hebbian_feedback (
                feedback_id, source_entity_id, target_entity_id, space_id,
                signal_type, signal_source, confidence,
                weight_before, weight_after, processed, created_at
            )
            SELECT
                :feedback_id,
                source_entity_id, target_entity_id, space_id,
                'RESURRECTION', 'P03', 1.0,
                0.0, :resurrection_weight, FALSE, :now
            FROM st_kg_edges WHERE edge_id = :edge_id
        """, {
            "feedback_id": str(uuid.uuid4()),
            "edge_id": edge_id,
            "resurrection_weight": self.RESURRECTION_WEIGHT,
            "now": int(time.time() * 1000),
        })
```

**Resurrection Metrics**:

```python
metrics = {
    "p03_edges_resurrected": count_resurrected,
    "p03_edges_resurrected_from_tombstone": count_from_tombstone,
    "p03_resurrection_rate": resurrected / total_new_co_occurrences,
}
```

**If resurrection rate is high** (> 10%):

- `prune_threshold` is too aggressive → lower it
- `decay_factor` is decaying too fast → reduce λ
- Emit alert for hyperparameter tuning

---

### 6.3 DBSCAN Clustering (R2)

```python
composite_distance = (1 - temporal_weight) × semantic_dist + temporal_weight × temporal_dist
```

| # | Question | Status | Proposed Answer | Notes |
|---|----------|--------|-----------------|-------|
| 1 | Should eps (0.25) vary by space or content type? | ✅ Resolved | Yes, per-space via `st_learned_weights` | See 6.3.1 below |
| 2 | How do we handle very long episodes (>4 hours)? | ✅ Resolved | Split at location/activity breaks | Use `location_geohash` + `activity_type` changes |
| 3 | Should min_samples (2) be configurable? | ✅ Resolved | Yes, per-space with noise-based adjustment | See 6.3.3 below |
| 4 | How do we evaluate cluster quality without labels? | ✅ Resolved | Silhouette + downstream grounding + user corrections | See 6.3.4 below |

#### 6.3.1 Per-Space `eps` Learning (Q1 Resolution)

> **Feasibility**: ✅ Supported via `st_learned_weights` + silhouette monitoring

**Current System Support**:

- `st_learned_weights` table (designed in 6.1) already supports per-space hyperparameters
- ADR k003.3 (CA3 Clustering Service) defines silhouette score monitoring with target > 0.5
- Per-space isolation already enforced in P03 processing

**Storage in `st_learned_weights`**:

```sql
-- Add DBSCAN parameters to st_learned_weights
-- weight_type = 'DBSCAN_PARAMS'

INSERT INTO st_learned_weights (
    weight_id, space_id, weight_type, weight_key, weight_value,
    sample_count, last_trained_at, created_at, updated_at
) VALUES
    (uuid(), :space_id, 'DBSCAN_PARAMS', 'eps', 0.25, 0, now(), now(), now()),
    (uuid(), :space_id, 'DBSCAN_PARAMS', 'min_samples', 2.0, 0, now(), now(), now()),
    (uuid(), :space_id, 'DBSCAN_PARAMS', 'temporal_weight', 0.3, 0, now(), now(), now());
```

**Adaptive Learning Algorithm**:

```python
class AdaptiveDBSCANLearner:
    """Learn optimal DBSCAN hyperparameters per-space from silhouette feedback."""

    # Learning bounds
    EPS_MIN = 0.15
    EPS_MAX = 0.40
    EPS_STEP = 0.02

    async def evaluate_and_adjust(self, db, space_id: str):
        """Run after each P03 cycle to tune eps."""

        # 1. Compute current silhouette score
        silhouette = await self._compute_silhouette(db, space_id)

        # 2. Get current eps
        current_eps = await self._get_param(db, space_id, 'eps')

        # 3. Decision based on silhouette (per ADR k003.3)
        if silhouette >= 0.7:
            # Excellent - no change
            adjustment = 0.0
        elif silhouette >= 0.5:
            # Good - small exploration
            adjustment = random.choice([-self.EPS_STEP, 0, self.EPS_STEP])
        elif silhouette >= 0.3:
            # Weak clustering - try tighter eps
            adjustment = -self.EPS_STEP
        else:
            # Poor clustering - try looser eps
            adjustment = self.EPS_STEP

        new_eps = max(self.EPS_MIN, min(self.EPS_MAX, current_eps + adjustment))

        # 4. Update with momentum (0.9)
        momentum = 0.9
        smoothed_eps = momentum * current_eps + (1 - momentum) * new_eps

        await self._update_param(db, space_id, 'eps', smoothed_eps, silhouette)

        return {
            "space_id": space_id,
            "old_eps": current_eps,
            "new_eps": smoothed_eps,
            "silhouette": silhouette,
        }

    async def _compute_silhouette(self, db, space_id: str) -> float:
        """Compute silhouette score for clustered events in space."""
        # Use st_hipp_events with episode_cluster_id + embedding similarity
        # Formula from ADR k003.3: s(i) = (b(i) - a(i)) / max(a(i), b(i))

        result = await db.fetch_one("""
            WITH clustered AS (
                SELECT event_id, episode_cluster_id, embedding_id
                FROM st_hipp_events
                WHERE space_id = :space_id
                  AND episode_cluster_id IS NOT NULL
                  AND event_time_utc > :cutoff
            ),
            cluster_stats AS (
                SELECT
                    episode_cluster_id,
                    COUNT(*) as cluster_size
                FROM clustered
                GROUP BY episode_cluster_id
                HAVING COUNT(*) >= 2  -- Skip singletons
            )
            SELECT
                COUNT(DISTINCT c.episode_cluster_id) as num_clusters,
                AVG(cs.cluster_size) as avg_cluster_size,
                COUNT(*) as total_events
            FROM clustered c
            JOIN cluster_stats cs ON c.episode_cluster_id = cs.episode_cluster_id
        """, {
            "space_id": space_id,
            "cutoff": int((time.time() - 30 * 86400) * 1000),  # Last 30 days
        })

        if not result or result.num_clusters < 2:
            return 0.5  # Default for insufficient data

        # Actual silhouette computation would use embeddings from st_vec
        # Simplified: use cluster_confidence average as proxy
        silhouette_proxy = await db.fetch_val("""
            SELECT AVG(cluster_confidence)
            FROM st_hipp_events
            WHERE space_id = :space_id
              AND cluster_confidence IS NOT NULL
        """, {"space_id": space_id})

        return silhouette_proxy or 0.5
```

**Metrics**:

```python
metrics = {
    "p03_dbscan_eps_current": current_eps,
    "p03_dbscan_silhouette": silhouette,
    "p03_dbscan_num_clusters": num_clusters,
    "p03_dbscan_avg_cluster_size": avg_cluster_size,
}
```

#### 6.3.2 Long Episode Splitting (Q2 Resolution)

> **Feasibility**: ✅ Use existing `location_geohash` + `activity_type` columns

**Current System Support**:

- `st_hipp_events.location_geohash` — Tracks location per event
- `st_hipp_events.activity_type` — Activity classification (MEAL, OUTING, etc.)
- ADR k003.3 notes: "No Hierarchical Clustering (Flat Clusters Only)" → Future work
- But: We can pre-split before clustering

**Algorithm: Pre-Clustering Episode Split**:

```python
class EpisodeSplitter:
    """Split long event sequences at natural breaks before DBSCAN."""

    MAX_EPISODE_DURATION_MS = 4 * 60 * 60 * 1000  # 4 hours
    MIN_LOCATION_CHANGE_DISTANCE = 4  # geohash prefix length for "same place"

    async def split_long_sequences(
        self,
        db,
        space_id: str,
        events: list[dict],
    ) -> list[list[dict]]:
        """
        Split event sequence into sub-episodes at natural breaks.

        Break signals (in priority order):
        1. Location change (geohash prefix differs by > 4 chars)
        2. Activity type change (MEAL → OUTING)
        3. Time gap > 30 minutes
        4. Hard limit: 4 hours
        """
        if not events:
            return []

        # Sort by time
        sorted_events = sorted(events, key=lambda e: e['event_time_utc'])

        episodes = []
        current_episode = [sorted_events[0]]

        for i in range(1, len(sorted_events)):
            prev = sorted_events[i - 1]
            curr = sorted_events[i]

            should_split = self._detect_break(prev, curr, current_episode)

            if should_split:
                episodes.append(current_episode)
                current_episode = [curr]
            else:
                current_episode.append(curr)

        if current_episode:
            episodes.append(current_episode)

        return episodes

    def _detect_break(
        self,
        prev: dict,
        curr: dict,
        current_episode: list[dict],
    ) -> bool:
        """Detect if we should split between prev and curr."""

        # 1. Location change (geohash prefix)
        prev_geo = (prev.get('location_geohash') or '')[:self.MIN_LOCATION_CHANGE_DISTANCE]
        curr_geo = (curr.get('location_geohash') or '')[:self.MIN_LOCATION_CHANGE_DISTANCE]
        if prev_geo and curr_geo and prev_geo != curr_geo:
            return True

        # 2. Activity type change
        if prev.get('activity_type') and curr.get('activity_type'):
            if prev['activity_type'] != curr['activity_type']:
                return True

        # 3. Time gap > 30 minutes
        time_gap_ms = curr['event_time_utc'] - prev['event_time_utc']
        if time_gap_ms > 30 * 60 * 1000:  # 30 minutes
            return True

        # 4. Hard limit: episode duration > 4 hours
        episode_start = current_episode[0]['event_time_utc']
        episode_duration = curr['event_time_utc'] - episode_start
        if episode_duration > self.MAX_EPISODE_DURATION_MS:
            return True

        return False
```

**Integration with P03 R2**:

```python
async def r2_episodic_clustering(db, space_id: str):
    """P03 R2: Cluster events into episodes."""

    # 1. Load unclustered events
    events = await db.fetch_all("""
        SELECT * FROM st_hipp_events
        WHERE space_id = :space_id
          AND episode_cluster_id IS NULL
          AND consolidation_status = 'IN_PROGRESS'
        ORDER BY event_time_utc
    """, {"space_id": space_id})

    # 2. Pre-split long sequences
    splitter = EpisodeSplitter()
    sub_episodes = await splitter.split_long_sequences(db, space_id, events)

    # 3. Run DBSCAN on each sub-episode
    for sub_episode in sub_episodes:
        await run_dbscan_clustering(db, space_id, sub_episode)
```

**Why Not Hierarchical Clustering?**

Per ADR k003.3:
> "No Hierarchical Clustering (Flat Clusters Only) — Mitigation: Future work"

Pre-splitting is simpler, deterministic, and uses existing columns without new algorithm complexity.

#### 6.3.3 Per-Space `min_samples` Configuration (Q3 Resolution)

> **Feasibility**: ✅ Store in `st_learned_weights`, adjust based on noise rate

**Problem**: `min_samples=2` is too low for noisy spaces (lots of singletons), too high for sparse spaces (misses valid clusters).

**Noise Detection**: Count singleton clusters (cluster_size = 1) as noise proxy.

```python
class MinSamplesAdjuster:
    """Adjust min_samples based on singleton (noise) rate."""

    MIN_SAMPLES_MIN = 2
    MIN_SAMPLES_MAX = 5
    NOISE_THRESHOLD_HIGH = 0.20  # > 20% singletons = too noisy
    NOISE_THRESHOLD_LOW = 0.05   # < 5% singletons = too strict

    async def adjust_min_samples(self, db, space_id: str):
        """Adjust min_samples based on singleton rate."""

        # Count singleton clusters
        result = await db.fetch_one("""
            WITH cluster_sizes AS (
                SELECT episode_cluster_id, COUNT(*) as cluster_size
                FROM st_hipp_events
                WHERE space_id = :space_id
                  AND episode_cluster_id IS NOT NULL
                GROUP BY episode_cluster_id
            )
            SELECT
                COUNT(*) FILTER (WHERE cluster_size = 1) as singletons,
                COUNT(*) as total_clusters
            FROM cluster_sizes
        """, {"space_id": space_id})

        if not result or result.total_clusters < 10:
            return  # Not enough data

        singleton_rate = result.singletons / result.total_clusters
        current_min_samples = await self._get_param(db, space_id, 'min_samples')

        if singleton_rate > self.NOISE_THRESHOLD_HIGH:
            # Too noisy → increase min_samples (stricter clustering)
            new_min_samples = min(current_min_samples + 1, self.MIN_SAMPLES_MAX)
        elif singleton_rate < self.NOISE_THRESHOLD_LOW:
            # Too strict → decrease min_samples (more lenient)
            new_min_samples = max(current_min_samples - 1, self.MIN_SAMPLES_MIN)
        else:
            new_min_samples = current_min_samples

        if new_min_samples != current_min_samples:
            await self._update_param(db, space_id, 'min_samples', new_min_samples)
```

#### 6.3.4 Cluster Quality Evaluation Without Labels (Q4 Resolution)

> **Feasibility**: ✅ Multi-signal approach using existing infrastructure

**Challenge**: No ground truth labels for "correct" clusters.

**Solution**: Combine automated metrics + downstream signals + user feedback.

**Signal 1: Silhouette Score (Automated)**

Per ADR k003.3:

- Target: > 0.5 (good clustering)
- Alert if < 0.5 (cluster quality degraded)
- Prometheus metric: `cluster_silhouette_score`

```python
# Already in k003.3
cluster_silhouette_score = Gauge(
    "cluster_silhouette_score",
    "Silhouette score for cluster quality",
    ["space_id"]
)
```

**Signal 2: Downstream Grounding (Implicit Feedback)**

If K1 retrieves an episode and uses it successfully → cluster is coherent.

```python
async def evaluate_cluster_grounding(db, space_id: str) -> float:
    """
    Measure: What fraction of clustered events were grounded in K1 responses?
    Higher = clusters are useful for retrieval.
    """
    result = await db.fetch_one("""
        WITH grounded_events AS (
            SELECT DISTINCT target_entity_id as event_id
            FROM st_feedback_signals
            WHERE space_id = :space_id
              AND signal_class = 'GROUNDING'
              AND target_entity_type = 'EVENT'
        ),
        clustered_grounded AS (
            SELECT h.episode_cluster_id
            FROM st_hipp_events h
            JOIN grounded_events g ON h.event_id = g.event_id
            WHERE h.space_id = :space_id
              AND h.episode_cluster_id IS NOT NULL
        )
        SELECT
            COUNT(DISTINCT episode_cluster_id) as grounded_clusters,
            (SELECT COUNT(DISTINCT episode_cluster_id)
             FROM st_hipp_events
             WHERE space_id = :space_id AND episode_cluster_id IS NOT NULL
            ) as total_clusters
        FROM clustered_grounded
    """, {"space_id": space_id})

    if not result or result.total_clusters == 0:
        return 0.5  # Default

    return result.grounded_clusters / result.total_clusters
```

**Signal 3: User Corrections via `st_feedback_signals`**

If user says "these events don't belong together" → cluster is incoherent.

```python
async def count_cluster_corrections(db, space_id: str) -> int:
    """Count user corrections for cluster assignments."""
    return await db.fetch_val("""
        SELECT COUNT(*)
        FROM st_feedback_signals
        WHERE space_id = :space_id
          AND signal_class = 'CORRECTION'
          AND payload_json::jsonb->>'correction_type' = 'CLUSTER_WRONG'
    """, {"space_id": space_id})
```

**Composite Cluster Quality Score**:

```python
@dataclass
class ClusterQualityMetrics:
    silhouette_score: float       # Target: > 0.5
    grounding_rate: float         # Fraction of clusters used by K1
    correction_rate: float        # User corrections / total clusters
    singleton_rate: float         # Noise proxy

    @property
    def composite_quality(self) -> float:
        """Weighted composite score [0-1]."""
        return (
            0.40 * self.silhouette_score +
            0.30 * self.grounding_rate +
            0.20 * (1 - self.correction_rate) +
            0.10 * (1 - self.singleton_rate)
        )

    @property
    def needs_tuning(self) -> bool:
        """True if parameters should be adjusted."""
        return self.composite_quality < 0.5
```

**Feedback-Driven Learning Loop**:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DBSCAN FEEDBACK LOOP                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────┐     ┌─────────────────┐     ┌─────────────────────┐  │
│  │ P03 R2:          │     │ st_hipp_events  │     │ P04 Query           │  │
│  │ DBSCAN clustering│────▶│ episode_cluster │────▶│ Episode retrieval   │  │
│  │ (eps, min_samples)    │ cluster_confidence    │ for K1              │  │
│  └──────────────────┘     └─────────────────┘     └──────────┬──────────┘  │
│        ▲                                                     │             │
│        │                                                     ▼             │
│  ┌─────┴─────────────────────────────────────────────────────────────────┐ │
│  │                      QUALITY SIGNALS                                   │ │
│  │                                                                        │ │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────┐   │ │
│  │  │ Silhouette     │  │ Grounding      │  │ User Corrections       │   │ │
│  │  │ (automated)    │  │ (st_feedback)  │  │ (CLUSTER_WRONG)        │   │ │
│  │  │                │  │                │  │                        │   │ │
│  │  │ < 0.5 → adjust │  │ low → eps ↓    │  │ high → min_samples ↑   │   │ │
│  │  └────────────────┘  └────────────────┘  └────────────────────────┘   │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                               │                                             │
│                               ▼                                             │
│                    ┌─────────────────────┐                                  │
│                    │ st_learned_weights  │                                  │
│                    │ DBSCAN_PARAMS       │                                  │
│                    └─────────────────────┘                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 6.3.5 Implementation Checklist

- [ ] Add DBSCAN params to `st_learned_weights` (eps, min_samples, temporal_weight)
- [ ] Implement `AdaptiveDBSCANLearner` class
- [ ] Implement `EpisodeSplitter` for long episode handling
- [ ] Implement `MinSamplesAdjuster` based on singleton rate
- [ ] Implement `ClusterQualityMetrics` dataclass
- [ ] Add Prometheus metrics: `p03_dbscan_eps`, `p03_dbscan_silhouette`, `p03_cluster_grounding_rate`
- [ ] Add feature flag: `P03_FF_ADAPTIVE_DBSCAN=enabled`
- [ ] Subscribe to `st_feedback_signals` for CLUSTER_WRONG corrections
- [ ] Add alert: `ClusterQualityCritical` when silhouette < 0.3

---

### 6.4 Decay Function (R3) ⚠️ High Priority

```python
decay_factor = exp(-λ × days_since_last_observed)
```

| # | Question | Status | Proposed Answer | Notes |
|---|----------|--------|-----------------|-------|
| 1 | Should λ be per-entity, per-entity-type, or per-user? | ✅ Resolved | Hybrid: per-space base λ + per-actor modifier | See 6.4.1 below |
| 2 | How do we learn λ from re-query patterns? | ✅ Resolved | Bayesian after 1000 memories, use defaults before | See 6.4.2 below |
| 3 | What's the floor for decay_factor before archival? | ✅ Resolved | 0.1 → ARCHIVED, 0.01 → TOMBSTONE | Validated thresholds |
| 4 | Should some entities never decay (birthdays, names)? | ✅ Resolved | Yes, both entity-level flag AND attribute-level ontology | See 6.4.3 below |
| 5 | How do we handle resurrection of archived entities? | ✅ Resolved | Boost: `max(0.7, 0.5 + current × 0.5)` + track count | See 6.4.4 below |

#### 6.4.1 Unified Decay System Architecture

> **Design Decision**: Single `DecayEngine` serves all 8 memory tables with table-specific λ values.

**Tables with Decay**:

| Table | Brain Analog | Default λ | Half-Life | Rationale |
|-------|--------------|-----------|-----------|-----------|
| `st_epi` | Episodic Memory | 0.005 | 139 days | Personal experiences fade slowly |
| `st_sem` | Semantic Memory | 0.003 | 231 days | Facts are very stable |
| `st_procedural` | Procedural Memory | 0.010 | 69 days | Habits need reinforcement |
| `st_social` | Social Memory | 0.002 | 347 days | Relationships persist long |
| `st_kg_dom` | Concept Nodes | 0.001 | 693 days | Core entities very stable |
| `st_kg_edges` | Associations | 0.008 | 87 days | Weak associations fade |
| `st_prospective` | Future Plans | 0.020 | 35 days | Plans become stale quickly |
| `st_hipp_events` | Short-term Buffer | 0.100 | 7 days | Hippocampus clears fast |

**Schema Addition** (all memory tables):

```sql
-- Add to each memory table via Alembic migration
ALTER TABLE st_epi ADD COLUMN access_count INTEGER DEFAULT 0;
ALTER TABLE st_epi ADD COLUMN last_accessed_at BIGINT;
ALTER TABLE st_epi ADD COLUMN resurrection_count INTEGER DEFAULT 0;

-- Repeat for: st_sem, st_procedural, st_social, st_kg_dom, st_kg_edges, st_prospective
```

**Unified Decay Engine**:

```python
from dataclasses import dataclass
from typing import Literal
import math

# Memory layer type
MemoryLayer = Literal[
    'st_epi', 'st_sem', 'st_procedural', 'st_social',
    'st_kg_dom', 'st_kg_edges', 'st_prospective', 'st_hipp_events'
]

@dataclass
class DecayConfig:
    """Configuration for a single memory layer's decay behavior."""
    layer: MemoryLayer
    base_lambda: float           # Default λ from dossier
    archive_threshold: float     # decay_factor below this → ARCHIVED
    tombstone_threshold: float   # decay_factor below this → TOMBSTONE
    supports_immunity: bool      # Whether entities can be decay-immune


# Default decay configurations (from dossier Section 2.4)
DECAY_CONFIGS: dict[MemoryLayer, DecayConfig] = {
    'st_epi': DecayConfig(
        layer='st_epi',
        base_lambda=0.005,
        archive_threshold=0.1,
        tombstone_threshold=0.01,
        supports_immunity=False,  # Episodes always decay
    ),
    'st_sem': DecayConfig(
        layer='st_sem',
        base_lambda=0.003,
        archive_threshold=0.1,
        tombstone_threshold=0.01,
        supports_immunity=True,  # Core patterns can be immune
    ),
    'st_procedural': DecayConfig(
        layer='st_procedural',
        base_lambda=0.010,
        archive_threshold=0.1,
        tombstone_threshold=0.01,
        supports_immunity=False,  # Habits need reinforcement
    ),
    'st_social': DecayConfig(
        layer='st_social',
        base_lambda=0.002,
        archive_threshold=0.1,
        tombstone_threshold=0.01,
        supports_immunity=True,  # Core relationships can be immune
    ),
    'st_kg_dom': DecayConfig(
        layer='st_kg_dom',
        base_lambda=0.001,
        archive_threshold=0.1,
        tombstone_threshold=0.01,
        supports_immunity=True,  # Core entities immune
    ),
    'st_kg_edges': DecayConfig(
        layer='st_kg_edges',
        base_lambda=0.008,
        archive_threshold=0.1,
        tombstone_threshold=0.01,
        supports_immunity=False,  # Edges always subject to decay
    ),
    'st_prospective': DecayConfig(
        layer='st_prospective',
        base_lambda=0.020,
        archive_threshold=0.1,
        tombstone_threshold=0.01,
        supports_immunity=False,  # Plans get stale
    ),
    'st_hipp_events': DecayConfig(
        layer='st_hipp_events',
        base_lambda=0.100,
        archive_threshold=0.1,
        tombstone_threshold=0.01,
        supports_immunity=False,  # Short-term buffer always clears
    ),
}


class UnifiedDecayEngine:
    """
    Unified decay engine for all memory layers.

    Implements:
    - Per-layer base λ (from dossier)
    - Per-space learned λ modifiers (after 1000 memories)
    - Per-actor modifiers for personal patterns
    - Decay immunity (entity-level + attribute-level)
    - Resurrection with partial memory
    """

    def __init__(self, db, space_id: str):
        self.db = db
        self.space_id = space_id
        self._lambda_cache: dict[str, float] = {}

    async def compute_decay_factor(
        self,
        layer: MemoryLayer,
        last_observed_at: int,
        actor_id: str | None = None,
        entity_type: str | None = None,
        is_immune: bool = False,
    ) -> float:
        """
        Compute decay factor for a memory record.

        decay_factor = exp(-λ_effective × days_since_last_observed)

        where λ_effective = λ_base × λ_space_modifier × λ_actor_modifier
        """
        if is_immune:
            return 1.0  # No decay

        config = DECAY_CONFIGS[layer]
        now_ms = int(time.time() * 1000)
        days_since = (now_ms - last_observed_at) / (1000 * 86400)

        if days_since <= 0:
            return 1.0

        # Get effective λ
        lambda_effective = await self._get_effective_lambda(
            layer, actor_id, entity_type
        )

        # Ebbinghaus decay curve
        decay_factor = math.exp(-lambda_effective * days_since)

        return max(0.0, min(1.0, decay_factor))

    async def _get_effective_lambda(
        self,
        layer: MemoryLayer,
        actor_id: str | None,
        entity_type: str | None,
    ) -> float:
        """
        Get effective λ = base × space_modifier × actor_modifier × entity_type_modifier
        """
        config = DECAY_CONFIGS[layer]
        base_lambda = config.base_lambda

        # 1. Space-level modifier (learned after 1000 memories)
        space_modifier = await self._get_space_modifier(layer)

        # 2. Actor-level modifier (for personal patterns)
        actor_modifier = 1.0
        if actor_id:
            actor_modifier = await self._get_actor_modifier(layer, actor_id)

        # 3. Entity-type modifier (e.g., PERSON decays slower than THING)
        entity_modifier = 1.0
        if entity_type:
            entity_modifier = await self._get_entity_type_modifier(layer, entity_type)

        return base_lambda * space_modifier * actor_modifier * entity_modifier

    async def _get_space_modifier(self, layer: MemoryLayer) -> float:
        """Get learned space-level λ modifier from st_learned_weights."""
        cache_key = f"space:{self.space_id}:{layer}"
        if cache_key in self._lambda_cache:
            return self._lambda_cache[cache_key]

        result = await self.db.fetch_val("""
            SELECT weight_value
            FROM st_learned_weights
            WHERE space_id = :space_id
              AND weight_type = 'DECAY_PARAMS'
              AND weight_key = :key
        """, {
            "space_id": self.space_id,
            "key": f"lambda_modifier_{layer}",
        })

        modifier = result if result else 1.0
        self._lambda_cache[cache_key] = modifier
        return modifier

    async def _get_actor_modifier(self, layer: MemoryLayer, actor_id: str) -> float:
        """Get per-actor λ modifier for personal patterns."""
        cache_key = f"actor:{actor_id}:{layer}"
        if cache_key in self._lambda_cache:
            return self._lambda_cache[cache_key]

        result = await self.db.fetch_val("""
            SELECT weight_value
            FROM st_learned_weights
            WHERE space_id = :space_id
              AND weight_type = 'DECAY_PARAMS'
              AND weight_key = :key
        """, {
            "space_id": self.space_id,
            "key": f"lambda_actor_{actor_id}_{layer}",
        })

        modifier = result if result else 1.0
        self._lambda_cache[cache_key] = modifier
        return modifier

    async def _get_entity_type_modifier(
        self,
        layer: MemoryLayer,
        entity_type: str,
    ) -> float:
        """
        Get entity-type specific λ modifier.

        Examples:
        - PERSON: 0.5 (decays slower - people are important)
        - THING: 1.5 (decays faster - objects less memorable)
        - EVENT: 1.0 (baseline)
        """
        # Entity-type modifiers (could be learned later)
        ENTITY_TYPE_MODIFIERS = {
            'PERSON': 0.5,       # People decay slower
            'FAMILY_MEMBER': 0.2,  # Family never forgotten
            'PLACE': 0.8,        # Places fairly stable
            'ORGANIZATION': 1.0,
            'THING': 1.5,        # Objects fade faster
            'EVENT': 1.0,
            'CONCEPT': 0.7,      # Concepts stable
        }

        return ENTITY_TYPE_MODIFIERS.get(entity_type, 1.0)
```

#### 6.4.2 Learning λ from Access Patterns (Bayesian)

> **Strategy**: Global defaults until 1000 memories, then Bayesian learning per-space

**Cold Start Phase** (< 1000 memories):

```python
class DecayLearner:
    """Learn λ from access patterns using Bayesian estimation."""

    COLD_START_THRESHOLD = 1000  # Memories before learning activates
    MIN_ACCESSES_PER_ENTITY = 5  # Minimum accesses to learn λ
    MIN_TIME_SPREAD_DAYS = 7     # Minimum spread for reliable fit

    async def should_start_learning(self, db, space_id: str) -> bool:
        """Check if space has enough data for learning."""
        total = await db.fetch_val("""
            SELECT SUM(cnt) FROM (
                SELECT COUNT(*) as cnt FROM st_epi WHERE space_id = :space_id
                UNION ALL
                SELECT COUNT(*) FROM st_sem WHERE space_id = :space_id
                UNION ALL
                SELECT COUNT(*) FROM st_kg_dom WHERE space_id = :space_id
            ) counts
        """, {"space_id": space_id})

        return (total or 0) >= self.COLD_START_THRESHOLD
```

**Bayesian λ Estimation**:

```python
from scipy import stats
import numpy as np

class BayesianLambdaEstimator:
    """
    Bayesian estimation of λ from inter-access intervals.

    Model: Access intervals follow Exponential(λ) distribution
    Prior: λ ~ Gamma(α_prior, β_prior) where α/β = dossier default
    Posterior: λ | data ~ Gamma(α_posterior, β_posterior)
    """

    def __init__(self, prior_lambda: float):
        # Set prior: E[λ] = prior_lambda, with moderate uncertainty
        # Gamma(α, β) has E[X] = α/β, Var[X] = α/β²
        # Set α=2 for moderate uncertainty, β = α/prior_lambda
        self.alpha_prior = 2.0
        self.beta_prior = self.alpha_prior / prior_lambda

    def fit(self, inter_access_days: list[float]) -> tuple[float, float, float]:
        """
        Fit Bayesian posterior for λ given observed inter-access intervals.

        Returns: (lambda_mean, lambda_lower_95, lambda_upper_95)
        """
        if not inter_access_days:
            # No data: return prior
            return (
                self.alpha_prior / self.beta_prior,
                0.0,
                self.alpha_prior / self.beta_prior * 2,
            )

        n = len(inter_access_days)
        sum_intervals = sum(inter_access_days)

        # Posterior parameters (conjugate update)
        alpha_post = self.alpha_prior + n
        beta_post = self.beta_prior + sum_intervals

        # Posterior mean
        lambda_mean = alpha_post / beta_post

        # 95% credible interval
        lambda_lower = stats.gamma.ppf(0.025, alpha_post, scale=1/beta_post)
        lambda_upper = stats.gamma.ppf(0.975, alpha_post, scale=1/beta_post)

        return (lambda_mean, lambda_lower, lambda_upper)

    def should_update_lambda(
        self,
        current_lambda: float,
        new_lambda: float,
        uncertainty: float,
    ) -> bool:
        """
        Decide if we should update stored λ.

        Only update if:
        1. New estimate differs significantly (> 20%)
        2. Uncertainty is low enough (CI width < 50% of estimate)
        """
        diff_ratio = abs(new_lambda - current_lambda) / current_lambda
        ci_ratio = uncertainty / new_lambda

        return diff_ratio > 0.2 and ci_ratio < 0.5


async def learn_lambda_for_layer(
    db,
    space_id: str,
    layer: MemoryLayer,
) -> dict:
    """
    Learn λ for a specific layer from access patterns.

    Uses grounding events from st_feedback_signals as access proxy.
    """
    config = DECAY_CONFIGS[layer]
    estimator = BayesianLambdaEstimator(config.base_lambda)

    # Get entities with sufficient access history
    entities_with_access = await db.fetch_all(f"""
        SELECT
            entity_id,
            ARRAY_AGG(accessed_at ORDER BY accessed_at) as access_times
        FROM (
            SELECT
                target_entity_id as entity_id,
                created_at as accessed_at
            FROM st_feedback_signals
            WHERE space_id = :space_id
              AND target_entity_type = :layer
              AND signal_class = 'GROUNDING'
        ) accesses
        GROUP BY entity_id
        HAVING COUNT(*) >= 5
    """, {"space_id": space_id, "layer": layer})

    all_intervals = []
    for entity in entities_with_access:
        times = entity.access_times
        # Compute inter-access intervals in days
        intervals = [
            (times[i+1] - times[i]) / (1000 * 86400)
            for i in range(len(times) - 1)
        ]
        all_intervals.extend(intervals)

    if len(all_intervals) < 10:
        return {"status": "insufficient_data", "lambda": config.base_lambda}

    # Fit Bayesian posterior
    lambda_mean, lambda_lower, lambda_upper = estimator.fit(all_intervals)
    uncertainty = lambda_upper - lambda_lower

    # Decide if update is warranted
    current = await db.fetch_val("""
        SELECT weight_value FROM st_learned_weights
        WHERE space_id = :space_id
          AND weight_type = 'DECAY_PARAMS'
          AND weight_key = :key
    """, {"space_id": space_id, "key": f"lambda_{layer}"})

    current_lambda = current if current else config.base_lambda

    should_update = estimator.should_update_lambda(
        current_lambda, lambda_mean, uncertainty
    )

    if should_update:
        # Store new λ (as modifier relative to base)
        modifier = lambda_mean / config.base_lambda
        await db.execute("""
            INSERT INTO st_learned_weights (
                weight_id, space_id, weight_type, weight_key, weight_value,
                sample_count, confidence_lower, confidence_upper,
                last_trained_at, created_at, updated_at
            ) VALUES (
                :id, :space_id, 'DECAY_PARAMS', :key, :value,
                :sample_count, :lower, :upper, :now, :now, :now
            )
            ON CONFLICT (space_id, weight_type, weight_key)
            DO UPDATE SET
                weight_value = :value,
                sample_count = :sample_count,
                confidence_lower = :lower,
                confidence_upper = :upper,
                last_trained_at = :now,
                updated_at = :now
        """, {
            "id": str(uuid.uuid4()),
            "space_id": space_id,
            "key": f"lambda_modifier_{layer}",
            "value": modifier,
            "sample_count": len(all_intervals),
            "lower": lambda_lower,
            "upper": lambda_upper,
            "now": int(time.time() * 1000),
        })

    return {
        "status": "updated" if should_update else "unchanged",
        "lambda_learned": lambda_mean,
        "lambda_current": current_lambda,
        "sample_count": len(all_intervals),
        "confidence_interval": (lambda_lower, lambda_upper),
    }
```

#### 6.4.3 Decay Immunity System

> **Design**: Both entity-level flag AND attribute-level via ontology

**Entity-Level Immunity** (column on memory tables):

```sql
-- Add to st_kg_dom, st_sem, st_social
ALTER TABLE st_kg_dom ADD COLUMN decay_immune BOOLEAN DEFAULT FALSE;
ALTER TABLE st_sem ADD COLUMN decay_immune BOOLEAN DEFAULT FALSE;
ALTER TABLE st_social ADD COLUMN decay_immune BOOLEAN DEFAULT FALSE;

-- Index for fast filtering
CREATE INDEX idx_kg_dom_immune ON st_kg_dom(decay_immune) WHERE decay_immune = TRUE;
```

**Attribute-Level Immunity** (ontology-driven):

```python
# Ontology defines which entity_type + attribute combinations are immune
IMMUNITY_ONTOLOGY = {
    'PERSON': {
        'attributes': ['birthday', 'name', 'relationship_to_user'],
        'entity_immune': False,  # Entity can decay, but these attributes don't
    },
    'FAMILY_MEMBER': {
        'attributes': ['*'],  # All attributes immune
        'entity_immune': True,  # Entity itself is immune
    },
    'PLACE': {
        'attributes': ['home_address', 'work_address'],
        'entity_immune': False,
    },
    'EVENT': {
        'attributes': ['wedding_date', 'birth_date', 'death_date'],
        'entity_immune': False,
    },
}


class ImmunityChecker:
    """Check if an entity or attribute is decay-immune."""

    def __init__(self, ontology: dict = None):
        self.ontology = ontology or IMMUNITY_ONTOLOGY

    def is_entity_immune(
        self,
        entity_type: str,
        attributes_json: dict | None = None,
        explicit_immune_flag: bool = False,
    ) -> bool:
        """
        Check if entity is decay-immune.

        Immune if:
        1. Explicit decay_immune = TRUE flag, OR
        2. Entity type is marked immune in ontology, OR
        3. Entity has any immune attribute
        """
        # 1. Explicit flag
        if explicit_immune_flag:
            return True

        # 2. Entity type immune
        type_config = self.ontology.get(entity_type, {})
        if type_config.get('entity_immune', False):
            return True

        # 3. Has immune attribute
        if attributes_json and type_config.get('attributes'):
            immune_attrs = type_config['attributes']
            if '*' in immune_attrs:
                return True
            for attr in immune_attrs:
                if attr in attributes_json and attributes_json[attr]:
                    return True

        return False

    def get_immune_attributes(
        self,
        entity_type: str,
        attributes_json: dict,
    ) -> set[str]:
        """Get list of attributes that should not decay."""
        type_config = self.ontology.get(entity_type, {})
        immune_attrs = set(type_config.get('attributes', []))

        if '*' in immune_attrs:
            return set(attributes_json.keys())

        return immune_attrs & set(attributes_json.keys())
```

**Auto-Marking Family Members as Immune**:

```python
async def mark_family_immune(db, space_id: str):
    """
    Auto-mark family members as decay-immune.

    Called during space setup and when new family members are added.
    """
    await db.execute("""
        UPDATE st_kg_dom
        SET decay_immune = TRUE,
            updated_at = :now
        WHERE space_id = :space_id
          AND entity_type IN ('FAMILY_MEMBER', 'PERSON')
          AND (
              -- Has family role in attributes
              attributes_json::jsonb->>'family_role' IS NOT NULL
              OR
              -- Explicitly marked as family
              attributes_json::jsonb->>'is_family_member' = 'true'
          )
          AND decay_immune = FALSE
    """, {"space_id": space_id, "now": int(time.time() * 1000)})
```

#### 6.4.4 Resurrection with Memory (Q5 Resolution)

> **Design**: Boost `max(0.7, 0.5 + current × 0.5)` + track `resurrection_count`

**Rationale** (Human Memory Model):

- When we suddenly remember something forgotten, it feels both **fresh** (re-activated) and **familiar** (we knew it before)
- Pure reset (1.0) loses the "it was forgotten" history
- Partial boost preserves familiarity while giving a strong recovery
- Tracking resurrection_count helps identify "weak spots" in memory

**Algorithm**:

```python
class ResurrectionHandler:
    """
    Handle resurrection of archived/tombstoned memories.

    Human analogy: "Oh yes, I remember this now!" - feels fresh but familiar.
    """

    MIN_RESURRECTION_DECAY = 0.7  # Resurrected memories start at least here

    async def resurrect(
        self,
        db,
        layer: MemoryLayer,
        entity_id: str,
        trigger: str,  # 'QUERY', 'CO_OCCURRENCE', 'USER_MENTION'
    ) -> dict:
        """
        Resurrect an archived entity.

        Formula: new_decay = max(0.7, 0.5 + current_decay × 0.5)

        This ensures:
        - Completely forgotten (decay=0.01) → revives to 0.7
        - Partially forgotten (decay=0.3) → revives to 0.65 → 0.7 (min)
        - Recently archived (decay=0.08) → revives to 0.54 → 0.7 (min)
        """
        table = layer  # e.g., 'st_kg_dom'

        # Get current state
        current = await db.fetch_one(f"""
            SELECT
                decay_factor,
                archival_status,
                resurrection_count,
                access_count
            FROM {table}
            WHERE entity_id = :entity_id
              AND space_id = :space_id
        """, {"entity_id": entity_id, "space_id": self.space_id})

        if not current:
            return {"status": "NOT_FOUND"}

        if current.archival_status == 'ACTIVE':
            # Not archived, just update access
            await self._update_access(db, table, entity_id)
            return {"status": "ALREADY_ACTIVE"}

        # Calculate new decay factor (human memory model)
        old_decay = current.decay_factor
        new_decay = max(
            self.MIN_RESURRECTION_DECAY,
            0.5 + old_decay * 0.5
        )

        new_resurrection_count = (current.resurrection_count or 0) + 1
        now = int(time.time() * 1000)

        # Perform resurrection
        await db.execute(f"""
            UPDATE {table}
            SET archival_status = 'ACTIVE',
                decay_factor = :new_decay,
                resurrection_count = :resurrection_count,
                access_count = access_count + 1,
                last_accessed_at = :now,
                last_observed_at = :now,
                updated_at = :now
            WHERE entity_id = :entity_id
        """, {
            "entity_id": entity_id,
            "new_decay": new_decay,
            "resurrection_count": new_resurrection_count,
            "now": now,
        })

        # Log resurrection for analysis
        await self._log_resurrection(
            db, layer, entity_id, old_decay, new_decay,
            new_resurrection_count, trigger
        )

        # Alert if resurrection count is high (memory instability)
        if new_resurrection_count >= 3:
            await self._emit_instability_alert(
                entity_id, layer, new_resurrection_count
            )

        return {
            "status": "RESURRECTED",
            "old_decay": old_decay,
            "new_decay": new_decay,
            "resurrection_count": new_resurrection_count,
            "trigger": trigger,
        }

    async def _log_resurrection(
        self,
        db,
        layer: MemoryLayer,
        entity_id: str,
        old_decay: float,
        new_decay: float,
        count: int,
        trigger: str,
    ):
        """Log resurrection to st_decay_feedback for analysis."""
        await db.execute("""
            INSERT INTO st_decay_feedback (
                feedback_id, entity_id, layer, space_id,
                signal_type, decay_before, decay_after,
                resurrection_count, trigger_source,
                created_at
            ) VALUES (
                :id, :entity_id, :layer, :space_id,
                'RESURRECTION', :old, :new, :count, :trigger, :now
            )
        """, {
            "id": str(uuid.uuid4()),
            "entity_id": entity_id,
            "layer": layer,
            "space_id": self.space_id,
            "old": old_decay,
            "new": new_decay,
            "count": count,
            "trigger": trigger,
            "now": int(time.time() * 1000),
        })

    async def _emit_instability_alert(
        self,
        entity_id: str,
        layer: MemoryLayer,
        count: int,
    ):
        """
        Alert if entity keeps being forgotten and resurrected.

        This suggests λ is too high for this entity type,
        or it's borderline important.
        """
        await emit_event(
            topic="p03.decay.instability.v1",
            payload={
                "entity_id": entity_id,
                "layer": layer,
                "resurrection_count": count,
                "recommendation": "Consider marking decay_immune=TRUE or lowering λ",
            }
        )
```

#### 6.4.5 P03 R3 Integration (Decay Application)

```python
async def r3_apply_decay(db, space_id: str, cycle_id: str):
    """
    P03 R3: Apply decay to all memory layers.

    Called nightly during consolidation cycle.
    """
    engine = UnifiedDecayEngine(db, space_id)
    immunity_checker = ImmunityChecker()

    stats = {layer: {"decayed": 0, "archived": 0, "tombstoned": 0, "immune": 0}
             for layer in DECAY_CONFIGS}

    for layer, config in DECAY_CONFIGS.items():
        # Skip layers without decay support
        if layer == 'st_hipp_events':
            continue  # Handled separately by P02

        # Get all active records
        records = await db.fetch_all(f"""
            SELECT
                entity_id,
                last_observed_at,
                actor_id,
                entity_type,
                attributes_json,
                decay_immune,
                decay_factor
            FROM {layer}
            WHERE space_id = :space_id
              AND archival_status = 'ACTIVE'
        """, {"space_id": space_id})

        for record in records:
            # Check immunity
            is_immune = immunity_checker.is_entity_immune(
                entity_type=record.entity_type,
                attributes_json=json.loads(record.attributes_json or '{}'),
                explicit_immune_flag=record.decay_immune,
            )

            if is_immune:
                stats[layer]["immune"] += 1
                continue

            # Compute new decay factor
            new_decay = await engine.compute_decay_factor(
                layer=layer,
                last_observed_at=record.last_observed_at,
                actor_id=record.actor_id,
                entity_type=record.entity_type,
            )

            # Determine new status
            if new_decay < config.tombstone_threshold:
                new_status = 'TOMBSTONE'
                stats[layer]["tombstoned"] += 1
            elif new_decay < config.archive_threshold:
                new_status = 'ARCHIVED'
                stats[layer]["archived"] += 1
            else:
                new_status = 'ACTIVE'
                stats[layer]["decayed"] += 1

            # Update record
            await db.execute(f"""
                UPDATE {layer}
                SET decay_factor = :decay,
                    archival_status = :status,
                    updated_at = :now
                WHERE entity_id = :entity_id
            """, {
                "entity_id": record.entity_id,
                "decay": new_decay,
                "status": new_status,
                "now": int(time.time() * 1000),
            })

    # Emit cycle completion metrics
    for layer, layer_stats in stats.items():
        emit_metric(f"p03_decay_{layer}_decayed", layer_stats["decayed"])
        emit_metric(f"p03_decay_{layer}_archived", layer_stats["archived"])
        emit_metric(f"p03_decay_{layer}_tombstoned", layer_stats["tombstoned"])
        emit_metric(f"p03_decay_{layer}_immune", layer_stats["immune"])

    return stats
```

#### 6.4.6 Access Tracking Integration

> **Trigger**: P04 query pipeline updates `access_count` + `last_accessed_at`

```python
async def on_memory_accessed(
    db,
    layer: MemoryLayer,
    entity_ids: list[str],
    space_id: str,
    query_id: str,
):
    """
    Called by P04 when memories are accessed (grounded in response).

    Updates:
    - access_count += 1
    - last_accessed_at = now
    - decay_factor = 1.0 (reset on access)
    """
    now = int(time.time() * 1000)

    await db.execute(f"""
        UPDATE {layer}
        SET access_count = access_count + 1,
            last_accessed_at = :now,
            last_observed_at = :now,
            decay_factor = 1.0,
            updated_at = :now
        WHERE entity_id = ANY(:ids)
          AND space_id = :space_id
    """, {
        "ids": entity_ids,
        "space_id": space_id,
        "now": now,
    })

    # Check for resurrections
    resurrection_handler = ResurrectionHandler(db, space_id)
    for entity_id in entity_ids:
        result = await resurrection_handler.resurrect(
            db, layer, entity_id, trigger='QUERY'
        )
        if result["status"] == "RESURRECTED":
            logger.info(f"Resurrected {entity_id} from {layer} via query")
```

#### 6.4.7 Feedback Table for Decay Learning

```sql
-- New table for decay feedback signals
CREATE TABLE st_decay_feedback (
    feedback_id       TEXT PRIMARY KEY,
    entity_id         TEXT NOT NULL,
    layer             TEXT NOT NULL,
    space_id          TEXT NOT NULL,

    -- Signal
    signal_type       TEXT NOT NULL,  -- 'DECAY', 'RESURRECTION', 'PRUNE_REGRET'
    trigger_source    TEXT,           -- 'QUERY', 'CO_OCCURRENCE', 'USER_MENTION', 'NIGHTLY'

    -- Decay state
    decay_before      REAL,
    decay_after       REAL,
    resurrection_count INTEGER,

    -- Processing
    processed         BOOLEAN DEFAULT FALSE,
    processed_at      BIGINT,

    -- Audit
    created_at        BIGINT NOT NULL
);

CREATE INDEX idx_decay_fb_layer ON st_decay_feedback(layer, space_id);
CREATE INDEX idx_decay_fb_unprocessed ON st_decay_feedback(processed, created_at)
    WHERE processed = FALSE;
CREATE INDEX idx_decay_fb_resurrections ON st_decay_feedback(signal_type, resurrection_count)
    WHERE signal_type = 'RESURRECTION';
```

#### 6.4.8 Metrics & Monitoring

```python
# Prometheus metrics for decay system
decay_metrics = {
    # Per-layer decay stats
    "p03_decay_applied": Counter(
        "p03_decay_applied_total",
        "Total decay applications",
        ["layer", "space_id"]
    ),
    "p03_decay_archived": Counter(
        "p03_decay_archived_total",
        "Entities archived due to decay",
        ["layer", "space_id"]
    ),
    "p03_decay_tombstoned": Counter(
        "p03_decay_tombstoned_total",
        "Entities tombstoned due to decay",
        ["layer", "space_id"]
    ),
    "p03_decay_immune_skipped": Counter(
        "p03_decay_immune_skipped_total",
        "Immune entities skipped",
        ["layer", "space_id"]
    ),

    # Resurrection tracking
    "p03_resurrections": Counter(
        "p03_resurrections_total",
        "Entity resurrections",
        ["layer", "trigger"]
    ),
    "p03_resurrection_instability": Counter(
        "p03_resurrection_instability_total",
        "Entities with resurrection_count >= 3",
        ["layer"]
    ),

    # Learning metrics
    "p03_lambda_learned": Gauge(
        "p03_lambda_learned",
        "Learned λ value per layer",
        ["layer", "space_id"]
    ),
    "p03_lambda_confidence": Gauge(
        "p03_lambda_confidence",
        "95% CI width for learned λ",
        ["layer", "space_id"]
    ),
}
```

#### 6.4.9 Implementation Checklist

- [ ] Add columns to all memory tables: `access_count`, `last_accessed_at`, `resurrection_count`
- [ ] Add `decay_immune` column to st_kg_dom, st_sem, st_social
- [ ] Create `st_decay_feedback` table (Alembic migration)
- [ ] Add DECAY_PARAMS to `st_learned_weights`
- [ ] Implement `UnifiedDecayEngine` class
- [ ] Implement `BayesianLambdaEstimator` class
- [ ] Implement `ImmunityChecker` with ontology
- [ ] Implement `ResurrectionHandler` class
- [ ] Integrate with P04 query pipeline (`on_memory_accessed`)
- [ ] Add feature flag: `P03_FF_BAYESIAN_DECAY=enabled` (activates after 1000 memories)
- [ ] Add metrics and Grafana dashboard
- [ ] Write integration test: decay → archive → resurrect cycle
- [ ] Document ontology immunity rules

#### 6.4.10 Feedback Loop Diagram

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                    UNIFIED DECAY FEEDBACK LOOP                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐     ┌──────────────────┐     ┌──────────────────────────┐ │
│  │ All Memory   │     │ P03 R3:          │     │ P04 Query               │ │
│  │ Tables       │────▶│ UnifiedDecayEngine│────▶│ Memory retrieval        │ │
│  │ (8 layers)   │     │ Apply nightly    │     │ + grounding             │ │
│  └──────────────┘     └──────────────────┘     └───────────┬─────────────┘ │
│        ▲                                                   │               │
│        │                                                   ▼               │
│  ┌─────┴────────────────────────────────────────────────────────────────┐  │
│  │                      FEEDBACK SIGNALS                                 │  │
│  │                                                                       │  │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐   │  │
│  │  │ ACCESS          │  │ RESURRECTION    │  │ PRUNE_REGRET        │   │  │
│  │  │ (P04 grounding) │  │ (archived →     │  │ (pruned but         │   │  │
│  │  │                 │  │  queried)       │  │  needed later)      │   │  │
│  │  │ Reset decay=1.0 │  │ Boost + track   │  │ Lower λ             │   │  │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────────┘   │  │
│  │                                                                       │  │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐   │  │
│  │  │ IMMUNITY        │  │ INSTABILITY     │  │ BAYESIAN UPDATE     │   │  │
│  │  │ (ontology +     │  │ (resurrection   │  │ (after 1000         │   │  │
│  │  │  explicit flag) │  │  count ≥ 3)     │  │  memories)          │   │  │
│  │  │ Skip decay      │  │ Alert + lower λ │  │ Learn per-space λ   │   │  │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                               │                                             │
│                               ▼                                             │
│                    ┌─────────────────────┐                                  │
│                    │ st_learned_weights  │                                  │
│                    │ DECAY_PARAMS        │                                  │
│                    │ + st_decay_feedback │                                  │
│                    └─────────────────────┘                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### 6.5 Novelty Score (R3)

```python
novelty_score = 1.0 - (duplicate_count / time_window_event_count)
```

| # | Question | Status | Proposed Answer | Notes |
|---|----------|--------|-----------------|-------|
| 1 | Should novelty bonuses (+0.15, +0.20, +0.10) be learned? | ✅ Resolved | Yes, learn from engagement signals | See 6.5.1 |
| 2 | How do we detect "milestone events" reliably? | ✅ Resolved | Ontology + temporal recurrence + NER | See 6.5.2 |
| 3 | What's the optimal time window for novelty calculation? | ✅ Resolved | Per-space adaptive: 12-48h based on activity | See 6.5.3 |

#### 6.5.1 Adaptive Novelty Bonuses (Q1 Resolution)

**Current Static Bonuses** (from dossier):

| Event Type | Bonus | Triggers |
|------------|-------|----------|
| First occurrence | +0.15 | Entity never seen before |
| Milestone event | +0.20 | Birthday, anniversary, graduation |
| Rare pattern | +0.10 | Activity < 5 times in 90 days |

**Learning Strategy**: Adjust bonuses based on downstream engagement.

**Feedback Signals**:

| Signal | Meaning | Adjustment |
|--------|---------|------------|
| Novel event grounded in K1 response | User found it useful | Increase bonus by 0.01 |
| Novel event never queried (30 days) | Over-prioritized | Decrease bonus by 0.02 |
| User explicitly references "first time" | Milestone detected correctly | Validate bonus |
| User corrects "this wasn't new" | False positive | Decrease bonus by 0.03 |

**Learning Process**:

1. Track novelty-tagged events in `st_hipp_events.novelty_bonus`
2. After 30 days, check if event was ever grounded (via `st_feedback_signals`)
3. If grounded: bonus was correct → reinforce
4. If never used: bonus inflated importance → reduce
5. Store learned bonuses in `st_learned_weights` (weight_type = 'NOVELTY_PARAMS')

**Bounds**: Bonuses clamped to [0.05, 0.30] to prevent runaway learning.

#### 6.5.2 Milestone Detection (Q2 Resolution)

**Three-Layer Detection**:

| Layer | Method | Examples |
|-------|--------|----------|
| **NER** | Extract temporal entities from text | "birthday", "anniversary", "first day" |
| **Ontology** | Match entity_type + date attributes | PERSON.birthday, EVENT.wedding_date |
| **Temporal Recurrence** | Detect annual patterns in history | Same date ± 3 days, same entities |

**Detection Flow**:

```
Event arrives → NER extraction → Check ontology dates → Check historical recurrence
                    ↓                    ↓                        ↓
              "birthday" found?    Date matches?           Same day last year?
                    ↓                    ↓                        ↓
                 YES → milestone_type = 'NER_DETECTED'
                            YES → milestone_type = 'ONTOLOGY_MATCH'
                                        YES → milestone_type = 'RECURRENCE'
```

**Confidence by Source**:

| Source | Confidence | Rationale |
|--------|------------|-----------|
| NER + Ontology match | 0.95 | Both agree = high confidence |
| Ontology only | 0.85 | Structured data reliable |
| NER only | 0.70 | Text extraction can be wrong |
| Recurrence only | 0.60 | Pattern may be coincidental |

**Storage**: Add `milestone_type` and `milestone_confidence` to `st_hipp_events`.

#### 6.5.3 Adaptive Time Window (Q3 Resolution)

**Problem**: 24h window is arbitrary. High-activity users need shorter windows; low-activity users need longer.

**Adaptive Strategy**:

| Daily Event Count | Time Window | Rationale |
|-------------------|-------------|-----------|
| < 5 events/day | 48 hours | Low activity, need more context |
| 5-20 events/day | 24 hours | Default (current) |
| 20-50 events/day | 12 hours | High activity, faster novelty decay |
| > 50 events/day | 6 hours | Very high activity (power user) |

**Learning Process**:

1. Track `events_per_day` rolling average (7-day window)
2. Store in `st_learned_weights` as `novelty_time_window_hours`
3. Adjust weekly based on activity pattern changes
4. Per-space isolation (family members may have different activity levels)

**Formula Update**:

```
novelty_score = 1.0 - (duplicate_count / time_window_event_count)

where time_window = adaptive_hours (6-48h based on activity)
```

#### 6.5.4 Implementation Checklist

- [ ] Add `milestone_type`, `milestone_confidence` columns to `st_hipp_events`
- [ ] Add NOVELTY_PARAMS to `st_learned_weights`
- [ ] Implement NER milestone detection (use existing NER pipeline)
- [ ] Implement ontology date matching
- [ ] Implement temporal recurrence detector
- [ ] Track novelty event grounding in `st_feedback_signals`
- [ ] Add 30-day novelty validation job
- [ ] Add metrics: `p03_novelty_bonus_applied`, `p03_milestones_detected`

---

### 6.6 SimHash Deduplication (R3)

```python
is_near_duplicate = (hamming_distance ≤ 3)
```

| # | Question | Status | Proposed Answer | Notes |
|---|----------|--------|-----------------|-------|
| 1 | Should threshold (3 bits) vary by content type? | ✅ Resolved | Yes, per-content-type thresholds | See 6.6.1 |
| 2 | How do we handle semantic duplicates with different wording? | ✅ Resolved | Two-stage: SimHash first, then embedding | See 6.6.2 |
| 3 | Should we use MinHash LSH for scale (>100K events)? | ✅ Resolved | Yes, auto-switch at 50K events | See 6.6.3 |

#### 6.6.1 Per-Content-Type Thresholds (Q1 Resolution)

**Rationale**: Structured data (calendar, contacts) needs stricter matching than free-form text (journal, notes).

**Threshold Matrix**:

| Content Type | Hamming Threshold | Rationale |
|--------------|-------------------|-----------|
| CALENDAR_EVENT | 2 bits | Structured, small variations matter |
| CONTACT_UPDATE | 2 bits | Names/phones must match closely |
| TRANSACTION | 1 bit | Financial data needs exact match |
| PHOTO_CAPTION | 4 bits | Free-form, allow more variation |
| JOURNAL_ENTRY | 4 bits | Personal text, paraphrasing common |
| CHAT_MESSAGE | 3 bits | Default, mixed content |
| VOICE_MEMO | 5 bits | Transcription has noise |

**Learning Process**:

1. Track false positives (user says "these aren't duplicates")
2. Track false negatives (user manually merges "duplicate" events)
3. If FP rate > 5%: increase threshold (more lenient)
4. If FN rate > 10%: decrease threshold (stricter)
5. Store in `st_learned_weights` (weight_type = 'SIMHASH_PARAMS')

**Feedback Sources**:

| Signal | Meaning |
|--------|---------|
| User unmerges deduped events | False positive → increase threshold |
| User manually marks duplicates | False negative → decrease threshold |
| Same content, different importance scores | Possible duplicate missed |

#### 6.6.2 Two-Stage Deduplication (Q2 Resolution)

**Problem**: SimHash catches syntactic duplicates but misses semantic ones ("I ate pizza" vs "Had pizza for dinner").

**Solution**: Two-stage pipeline.

**Stage 1: SimHash (Fast Filter)**

```
All events → Compute SimHash → Group by hamming distance ≤ threshold
                                        ↓
                              Candidate duplicate pairs
```

**Stage 2: Embedding Similarity (Semantic Check)**

```
Candidate pairs → Compute cosine similarity → If > 0.85: confirm duplicate
                                                        ↓
                                              Mark as NEAR_DUPLICATE
```

**Decision Matrix**:

| SimHash Match | Embedding Similarity | Decision |
|---------------|----------------------|----------|
| ≤ threshold | ≥ 0.85 | DUPLICATE (merge) |
| ≤ threshold | 0.70-0.85 | LIKELY_DUPLICATE (flag for review) |
| ≤ threshold | < 0.70 | NOT_DUPLICATE (false positive) |
| > threshold | ≥ 0.90 | SEMANTIC_DUPLICATE (different words, same meaning) |

**Performance**: Stage 1 filters 99%+ of pairs, Stage 2 only runs on candidates.

#### 6.6.3 Scale Strategy: MinHash LSH (Q3 Resolution)

**Current**: SimHash with O(n²) pairwise comparison.

**Problem**: At 50K+ events, O(n²) becomes expensive (2.5B comparisons).

**Solution**: Auto-switch to MinHash LSH at scale.

**Transition Logic**:

| Event Count | Algorithm | Complexity |
|-------------|-----------|------------|
| < 10K | SimHash pairwise | O(n²) fast enough |
| 10K-50K | SimHash with bucketing | O(n × bucket_size) |
| > 50K | MinHash LSH | O(n × num_bands) |

**MinHash LSH Parameters**:

| Parameter | Value | Tuning |
|-----------|-------|--------|
| num_hashes | 128 | More = higher accuracy, slower |
| num_bands | 32 | More = fewer FN, more FP |
| rows_per_band | 4 | = num_hashes / num_bands |

**Implementation Notes**:

- Store MinHash signatures in `st_hipp_events.minhash_signature` (BYTEA)
- Use Redis for LSH index (fast lookups)
- Rebuild index during P03 R0 (nightly)
- Feature flag: `P03_FF_MINHASH_LSH=enabled`

#### 6.6.4 Implementation Checklist

- [ ] Add `content_type` to SimHash threshold lookup
- [ ] Store thresholds in `st_learned_weights` (SIMHASH_PARAMS)
- [ ] Implement two-stage pipeline (SimHash → Embedding)
- [ ] Add `duplicate_check_method` column to `st_hipp_events`
- [ ] Implement MinHash signature computation
- [ ] Add Redis LSH index for scale
- [ ] Track FP/FN rates via `st_feedback_signals`
- [ ] Add metrics: `p03_duplicates_detected`, `p03_semantic_duplicates`

---

### 6.7 Entity Disambiguation (R4)

```python
disambiguation_score = 0.7 × embedding_similarity + 0.3 × fuzzy_string_match
```

| # | Question | Status | Proposed Answer | Notes |
|---|----------|--------|-----------------|-------|
| 1 | Should weights (0.7/0.3) be learned per entity type? | ✅ Resolved | Yes, per-entity-type weight vectors | See 6.7.1 |
| 2 | How do we handle ambiguous entities (e.g., "John")? | ✅ Resolved | Context-based + P06 gap emission | See 6.7.2 |
| 3 | What's the match threshold (0.8) based on? | ✅ Resolved | Per-entity-type, learned from corrections | See 6.7.3 |
| 4 | How do we merge incorrectly split entities? | ✅ Resolved | User correction → merge + cascade update | See 6.7.4 |

#### 6.7.1 Per-Entity-Type Weights (Q1 Resolution)

**Rationale**: Names need strong string matching (typos matter); concepts need semantic matching.

**Default Weight Matrix**:

| Entity Type | Embedding Weight | String Weight | Rationale |
|-------------|------------------|---------------|-----------|
| PERSON | 0.50 | 0.50 | Names matter, but context helps |
| FAMILY_MEMBER | 0.30 | 0.70 | Names highly specific |
| PLACE | 0.60 | 0.40 | "Home" vs "123 Main St" |
| ORGANIZATION | 0.55 | 0.45 | "Google" vs "Alphabet" |
| THING | 0.80 | 0.20 | "Car" vs "vehicle" |
| CONCEPT | 0.85 | 0.15 | Semantic meaning primary |
| EVENT | 0.70 | 0.30 | "Birthday party" vs "celebration" |

**Learning Process**:

1. Track disambiguation decisions in `st_disambiguation_log`
2. When user corrects (merges or splits): record as feedback
3. If corrections cluster around entity_type: adjust weights
4. Store in `st_learned_weights` (weight_type = 'DISAMBIGUATION_PARAMS')

**Feedback Loop**:

```
Disambiguation → Decision → User Correction?
        ↓                          ↓
   Log decision            If YES: adjust weights
        ↓                          ↓
   st_disambiguation_log    st_learned_weights
```

#### 6.7.2 Ambiguous Entity Handling (Q2 Resolution)

**Problem**: "John" could be John Smith, John Doe, or new John.

**Resolution Strategy** (Priority Order):

| Priority | Method | Example |
|----------|--------|---------|
| 1 | Recent context | "John" in conversation about work → John (coworker) |
| 2 | Co-occurring entities | "John and Mary" → if Mary=sister, John likely brother-in-law |
| 3 | Location context | Event at "Home" → family member John |
| 4 | Frequency | Most mentioned John in space |
| 5 | Emit to P06 | AMBIGUOUS_ENTITY gap for user resolution |

**Confidence Thresholds**:

| Confidence | Action |
|------------|--------|
| ≥ 0.85 | Auto-resolve to best match |
| 0.60-0.85 | Resolve but flag for validation |
| < 0.60 | Emit to P06 as AMBIGUOUS_ENTITY |

**P06 Gap Emission**:

```
Gap Type: AMBIGUOUS_ENTITY
Entity: "John"
Candidates: [John Smith (0.55), John Doe (0.52), NEW (0.40)]
Context: "Meeting with John tomorrow"
User Prompt: "Which John did you mean?"
```

**Storage**: Track ambiguity resolutions in `st_entity_resolutions`:

| Column | Purpose |
|--------|---------|
| resolution_id | Primary key |
| surface_form | "John" |
| resolved_entity_id | Which entity was chosen |
| resolution_method | 'CONTEXT', 'CO_OCCURRENCE', 'USER', 'FREQUENCY' |
| confidence | Resolution confidence |
| was_corrected | Did user override? |

#### 6.7.3 Per-Entity-Type Thresholds (Q3 Resolution)

**Problem**: 0.8 threshold is arbitrary; some types need stricter matching.

**Learned Thresholds**:

| Entity Type | Initial Threshold | Learning Range |
|-------------|-------------------|----------------|
| PERSON | 0.85 | [0.80, 0.95] |
| FAMILY_MEMBER | 0.90 | [0.85, 0.98] |
| PLACE | 0.75 | [0.65, 0.85] |
| ORGANIZATION | 0.80 | [0.70, 0.90] |
| THING | 0.70 | [0.60, 0.80] |
| CONCEPT | 0.65 | [0.55, 0.75] |

**Learning Signals**:

| Signal | Meaning | Adjustment |
|--------|---------|------------|
| User merges two entities | Threshold too strict | Lower by 0.02 |
| User splits merged entity | Threshold too lenient | Raise by 0.03 |
| Disambiguation never corrected (30 days) | Threshold correct | No change |

**Bounds**: Thresholds clamped to learning range to prevent drift.

#### 6.7.4 Entity Merge Process (Q4 Resolution)

**Trigger**: User says "John Smith and J. Smith are the same person."

**Merge Process**:

1. **Validate**: Confirm user intent (are you sure?)
2. **Select Primary**: Choose entity with more history as primary
3. **Merge Attributes**: Combine attributes (primary wins on conflict)
4. **Cascade References**: Update all references across tables:
   - `st_kg_edges`: Redirect edges to primary
   - `st_hipp_events.entities_json`: Replace secondary with primary
   - `st_epi/st_sem`: Update entity references
5. **Archive Secondary**: Set `archival_status = 'MERGED'` (not deleted)
6. **Log Merge**: Record in `st_entity_merges` for audit/undo

**Cascade Tables**:

| Table | Update Method |
|-------|---------------|
| st_kg_edges | Redirect source/target_entity_id |
| st_hipp_events | JSON replace in entities_json |
| st_epi | Update entity references |
| st_sem | Update pattern entity links |
| st_social | Update actor references |

**Undo Support**: Store merge history in `st_entity_merges`:

| Column | Purpose |
|--------|---------|
| merge_id | Primary key |
| primary_entity_id | Surviving entity |
| secondary_entity_id | Merged-into entity |
| merged_at | Timestamp |
| merged_by | User who triggered |
| attributes_before | JSON snapshot for undo |
| is_undone | Was merge reversed? |

**Feedback Signal**: Log to `st_feedback_signals` with signal_class = 'ENTITY_MERGE'.

#### 6.7.5 Implementation Checklist

- [ ] Add per-entity-type weights to `st_learned_weights` (DISAMBIGUATION_PARAMS)
- [ ] Create `st_disambiguation_log` table
- [ ] Create `st_entity_resolutions` table
- [ ] Create `st_entity_merges` table (for undo support)
- [ ] Implement context-based disambiguation
- [ ] Implement co-occurrence disambiguation
- [ ] Emit AMBIGUOUS_ENTITY to P06 when confidence < 0.60
- [ ] Implement entity merge with cascade updates
- [ ] Add metrics: `p03_disambiguations`, `p03_ambiguous_emitted`, `p03_entities_merged`

---

### 6.8 Granger Causality (R4)

```python
precedence_ratio = a_before_b / (a_before_b + b_before_a + simultaneous)
```

| # | Question | Status | Proposed Answer | Notes |
|---|----------|--------|-----------------|-------|
| 1 | Is 0.75 threshold too strict or too lenient? | ✅ Resolved | Per-relationship-type, learned | See 6.8.1 |
| 2 | How many observations needed before inferring causality? | ✅ Resolved | Minimum 5, scale with relationship importance | See 6.8.2 |
| 3 | How do we distinguish causation from confounding? | ✅ Resolved | Context conditioning + confound detection | See 6.8.3 |

#### 6.8.1 Adaptive Causality Threshold (Q1 Resolution)

**Problem**: 0.75 is arbitrary. Some relationships need stricter thresholds (medical), others more lenient (social).

**Per-Relationship-Type Thresholds**:

| Relationship Category | Initial Threshold | Rationale |
|-----------------------|-------------------|-----------|
| Health/Medical | 0.85 | High stakes, need strong evidence |
| Financial | 0.80 | Important decisions |
| Social/Routine | 0.70 | Lower stakes, allow weaker patterns |
| Preference/Habit | 0.65 | Personal patterns, more flexible |

**Learning Process**:

1. Track inferred causal edges in `st_kg_edges` with `edge_type = 'CAUSAL'`
2. Monitor downstream usage: was causal edge used in K1 reasoning?
3. If causal edge led to correct prediction → threshold was appropriate
4. If causal edge led to wrong prediction → threshold too lenient
5. Adjust per-category thresholds in `st_learned_weights`

**Feedback Signals**:

| Signal | Meaning | Adjustment |
|--------|---------|------------|
| Causal prediction confirmed | Threshold appropriate | No change |
| Causal prediction wrong | Threshold too lenient | Raise by 0.02 |
| User says "X doesn't cause Y" | False positive | Raise by 0.05 |
| Missed obvious causation | Threshold too strict | Lower by 0.03 |

#### 6.8.2 Observation Count Requirements (Q2 Resolution)

**Problem**: 5 observations may be too few for noisy patterns, too many for rare events.

**Adaptive Observation Requirements**:

| Pattern Frequency | Min Observations | Rationale |
|-------------------|------------------|-----------|
| Daily (> 0.8/day) | 10 | High frequency needs more samples |
| Weekly (0.1-0.8/day) | 5 | Default (current) |
| Monthly (< 0.1/day) | 3 | Rare events, lower bar |
| Annual (< 0.01/day) | 2 | Very rare, accept weak evidence |

**Confidence Scaling**:

```
causal_confidence = base_confidence × sqrt(observations / min_required)

where:
- base_confidence = precedence_ratio
- observations = actual count
- min_required = from table above
- Capped at 1.0
```

**Example**:

- Pattern seen 15 times, min_required = 5
- Confidence multiplier = sqrt(15/5) = 1.73, capped to 1.0
- Extra observations increase confidence

#### 6.8.3 Confound Detection (Q3 Resolution)

**Problem**: A→B may actually be C→A and C→B (confounding).

**Detection Strategy**:

1. **Context Variables**: Track co-occurring context for each A→B observation
   - Time of day (morning/afternoon/evening/night)
   - Day of week (weekday/weekend)
   - Location (home/work/other)
   - Actor (who was involved)

2. **Simpson's Paradox Check**:
   - If A→B holds globally but reverses in subgroups → confounded
   - Example: "Coffee → Productive" may be confounded by "Morning"

3. **Common Cause Detection**:
   - If C precedes both A and B in > 50% of cases → C may be confounder
   - Emit as POTENTIAL_CONFOUNDER for review

**Confound Handling**:

| Detection | Action |
|-----------|--------|
| Strong confounder found | Demote edge to `edge_type = 'CORRELATED'` |
| Weak confounder signal | Add `confounder_candidates` to edge metadata |
| No confounders | Confirm as `edge_type = 'CAUSAL'` |

**Storage**: Add to `st_kg_edges`:

| Column | Purpose |
|--------|---------|
| causal_confidence | Confidence in causal relationship |
| observation_count | Number of A→B observations |
| confounder_candidates | JSON array of potential confounders |
| context_breakdown | JSON: {morning: 0.8, evening: 0.3} |

#### 6.8.4 Implementation Checklist

- [ ] Add relationship categories to causality threshold lookup
- [ ] Store thresholds in `st_learned_weights` (CAUSALITY_PARAMS)
- [ ] Implement adaptive observation requirements
- [ ] Add context tracking (time, location, actor) to observations
- [ ] Implement Simpson's paradox detection
- [ ] Add `causal_confidence`, `confounder_candidates` to `st_kg_edges`
- [ ] Track causal prediction accuracy via `st_feedback_signals`
- [ ] Add metrics: `p03_causal_edges_created`, `p03_confounders_detected`

---

### 6.9 UCT / MCTS (R5)

```python
UCT = Q/N + c × √(ln(N_parent) / N)
```

| # | Question | Status | Proposed Answer | Notes |
|---|----------|--------|-----------------|-------|
| 1 | Should exploration constant c (√2) be tuned? | ✅ Resolved | No, keep static (theoretical optimum) | See 6.9.1 |
| 2 | How many rollouts are sufficient for stable estimates? | ✅ Resolved | Adaptive: 10-100 based on decision importance | See 6.9.2 |
| 3 | Should we skip R5 entirely for MVP? | ✅ Resolved | Yes, feature flag disabled for MVP | See 6.9.3 |

#### 6.9.1 Exploration Constant Decision (Q1 Resolution)

**Decision**: Keep c = √2 (≈ 1.414) static.

**Rationale**:

- √2 is theoretically optimal for UCT (Kocsis & Szepesvári, 2006)
- Tuning c adds complexity with minimal benefit
- Our use case (memory consolidation) is well-suited to default

**Alternative Considered**: Adaptive c based on search depth

- Rejected: adds complexity, theoretical gains unclear
- If needed later: feature flag `P03_FF_ADAPTIVE_UCT_C`

#### 6.9.2 Adaptive Rollout Count (Q2 Resolution)

**Problem**: 100 rollouts is expensive; 10 may be insufficient for important decisions.

**Decision Importance Classification**:

| Decision Type | Rollouts | Rationale |
|---------------|----------|-----------|
| Entity merge/split | 100 | High impact, irreversible |
| Causal edge creation | 50 | Important for reasoning |
| Memory reinforcement | 20 | Lower stakes |
| Decay parameter tuning | 10 | Reversible, low impact |

**Adaptive Strategy**:

1. Classify consolidation decision by type
2. Look up rollout count from table
3. Run MCTS with allocated budget
4. Track decision quality over time

**Early Termination**: Stop rollouts early if:

- Best action has > 90% of visits (clear winner)
- Confidence interval is narrow enough (< 5% uncertainty)

**Compute Budget**: Total rollouts per P03 cycle capped at 1000 to stay within <5% compute budget.

#### 6.9.3 MVP Feature Flag Strategy (Q3 Resolution)

**Decision**: R5 disabled for MVP via `P03_FF_R5_MODE=disabled`

**MVP Behavior** (R5 skipped):

- Use heuristic scoring instead of MCTS
- Decisions based on direct formula outputs
- No exploration/exploitation tradeoff

**Post-MVP Rollout Plan**:

| Phase | Mode | When |
|-------|------|------|
| MVP | disabled | Initial launch |
| Alpha | shadow | Run MCTS but don't use results (compare to heuristic) |
| Beta | enabled_low | 10 rollouts only, monitor performance |
| GA | enabled | Full adaptive rollouts |

**Shadow Mode Validation**:

- Track: "Would MCTS have made different decision?"
- If MCTS differs > 20% of time AND user corrections favor MCTS → enable
- If MCTS matches heuristic > 95% → keep disabled (not worth compute)

#### 6.9.4 Implementation Checklist

- [ ] Add feature flag: `P03_FF_R5_MODE=disabled|shadow|enabled_low|enabled`
- [ ] Implement decision importance classifier
- [ ] Implement early termination conditions
- [ ] Add shadow mode comparison logging
- [ ] Add compute budget tracking (< 1000 rollouts/cycle)
- [ ] Add metrics: `p03_mcts_rollouts`, `p03_mcts_decisions`, `p03_mcts_vs_heuristic_diff`

---

### 6.10 Multi-Factor Similarity (R7) ⚠️ High Priority

```python
similarity = 0.40×semantic + 0.25×simhash + 0.15×entity + 0.10×temporal + 0.10×spatial
```

| # | Question | Status | Proposed Answer | Notes |
|---|----------|--------|-----------------|-------|
| 1 | Should weights be learned per memory layer? | ✅ Resolved | Yes, per-layer weight vectors | See 6.10.1 |
| 2 | How do we validate similarity thresholds (0.85, 0.60)? | ✅ Resolved | Implicit feedback + golden dataset | See 6.10.2 |
| 3 | Should thresholds be per-entity-type? | ✅ Resolved | Yes, ontology-driven | See 6.10.3 |

#### 6.10.1 Per-Layer Weight Vectors (Q1 Resolution)

**Rationale**: Different memory layers value different similarity factors.

**Layer-Specific Default Weights**:

| Layer | Semantic | SimHash | Entity | Temporal | Spatial |
|-------|----------|---------|--------|----------|---------|
| st_epi | 0.30 | 0.15 | 0.15 | **0.25** | **0.15** |
| st_sem | **0.50** | 0.20 | 0.15 | 0.10 | 0.05 |
| st_procedural | 0.25 | 0.15 | 0.20 | **0.30** | 0.10 |
| st_social | 0.35 | 0.10 | **0.35** | 0.10 | 0.10 |
| st_kg_dom | **0.45** | 0.25 | 0.15 | 0.10 | 0.05 |

**Rationale by Layer**:

- **st_epi** (Episodic): When/where matters more than what
- **st_sem** (Semantic): Meaning is primary
- **st_procedural** (Habits): Timing patterns critical
- **st_social** (Relationships): Who is involved matters most
- **st_kg_dom** (Entities): Semantic identity primary

**Learning Process**:

1. Track which similarity factor "mattered" for correct matches
2. When user confirms match: boost factors that contributed
3. When user rejects match: reduce dominant factor
4. Weights normalized to sum = 1.0

**Storage**: `st_learned_weights` with weight_type = 'SIMILARITY_WEIGHTS_{layer}'

#### 6.10.2 Threshold Validation Strategy (Q2 Resolution)

**Two Validation Approaches**:

**Approach 1: Implicit Feedback (Online)**

| Signal | Meaning | Threshold Implication |
|--------|---------|----------------------|
| Match used in K1 response | Similarity was correct | Threshold appropriate |
| Match rejected by user | False positive | Threshold too low |
| User manually links items | Missed match | Threshold too high |
| Reformulation after response | Possible bad match | Review decision |

**Approach 2: Golden Dataset (Offline)**

| Dataset Component | Purpose |
|-------------------|---------|
| Known duplicates | True positives - should match |
| Known distinct | True negatives - should not match |
| Edge cases | Boundary testing |

**Validation Metrics**:

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Precision | > 0.90 | < 0.85 |
| Recall | > 0.85 | < 0.80 |
| F1 Score | > 0.87 | < 0.82 |

**Validation Schedule**:

- Online: Continuous via `st_feedback_signals`
- Offline: Weekly against golden dataset
- A/B test: Shadow mode for new thresholds

#### 6.10.3 Per-Entity-Type Thresholds (Q3 Resolution)

**Rationale**: Matching "John Smith" requires higher precision than matching "meeting".

**Entity-Type Threshold Matrix**:

| Entity Type | REINFORCE (>) | EXTEND (range) | CREATE (<) |
|-------------|---------------|----------------|------------|
| PERSON | 0.90 | 0.70-0.90 | 0.70 |
| FAMILY_MEMBER | 0.95 | 0.80-0.95 | 0.80 |
| PLACE | 0.80 | 0.55-0.80 | 0.55 |
| ORGANIZATION | 0.85 | 0.65-0.85 | 0.65 |
| EVENT | 0.80 | 0.55-0.80 | 0.55 |
| THING | 0.75 | 0.50-0.75 | 0.50 |
| CONCEPT | 0.70 | 0.45-0.70 | 0.45 |

**Learning Process**:

1. Start with ontology defaults above
2. Track match outcomes per entity_type
3. If FP rate high for type → raise thresholds
4. If recall low for type → lower thresholds
5. Per-space isolation (different families have different naming patterns)

#### 6.10.4 Implementation Checklist

- [ ] Store per-layer weight vectors in `st_learned_weights`
- [ ] Implement weight normalization (sum = 1.0)
- [ ] Track which factor contributed to matches
- [ ] Create golden dataset for offline validation
- [ ] Implement per-entity-type threshold lookup
- [ ] Add weekly validation job against golden dataset
- [ ] Add metrics: `p03_similarity_precision`, `p03_similarity_recall`

---

### 6.11 Reconciliation Thresholds (R7) ⚠️ Critical

| Similarity | Decision |
|------------|----------|
| > 0.85 | REINFORCE |
| 0.60–0.85 | EXTEND/EVOLVE |
| < 0.60 | CREATE/CONTRADICT |

| # | Question | Status | Proposed Answer | Notes |
|---|----------|--------|-----------------|-------|
| 1 | Why 0.85? Why 0.60? | ✅ Resolved | Learned via Thompson Sampling | See 6.11.1 |
| 2 | How fast should thresholds adapt? | ✅ Resolved | Momentum 0.9, per-cycle updates | See 6.11.2 |
| 3 | What's the minimum feedback before adapting? | ✅ Resolved | 100 signals per-space | See 6.11.3 |
| 4 | Should adaptation be per-user, per-space, or global? | ✅ Resolved | Per-space with global fallback | See 6.11.4 |

#### 6.11.1 Threshold Learning Strategy (Q1 Resolution)

**Problem**: 0.85 and 0.60 are arbitrary magic numbers.

**Solution**: Use Thompson Sampling to learn optimal thresholds.

**Threshold Model**:

| Threshold | Prior | Interpretation |
|-----------|-------|----------------|
| REINFORCE_THRESHOLD | Beta(85, 15) | E[x] = 0.85 |
| EXTEND_LOWER | Beta(60, 40) | E[x] = 0.60 |

**Learning Loop**:

1. Sample threshold from Beta posterior
2. Make reconciliation decision using sampled threshold
3. Observe outcome (was decision correct?)
4. Update Beta parameters based on outcome

**Success Definition**:

| Decision | Success Criteria |
|----------|------------------|
| REINFORCE | Memory used without correction in next 7 days |
| EXTEND | Extended memory useful (grounded or queried) |
| CREATE | New memory was distinct (not later merged) |
| CONTRADICT | Contradiction resolved correctly |

#### 6.11.2 Adaptation Speed (Q2 Resolution)

**Problem**: Too fast = unstable; too slow = no learning.

**Solution**: Momentum-based updates.

**Update Rule**:

```
new_alpha = momentum × old_alpha + (1 - momentum) × success_count
new_beta = momentum × old_beta + (1 - momentum) × failure_count

where momentum = 0.9
```

**Effective Learning Rate**:

- With momentum 0.9: ~10% of new data influences each update
- Requires ~50-100 signals to shift threshold by 0.05

**Stability Bounds**:

- REINFORCE_THRESHOLD: [0.75, 0.95]
- EXTEND_LOWER: [0.45, 0.75]
- Alert if threshold hits bound (may indicate data issue)

#### 6.11.3 Cold Start Strategy (Q3 Resolution)

**Problem**: No feedback = can't learn.

**Solution**: Use static priors until 100 signals.

**Cold Start Phases**:

| Phase | Signal Count | Behavior |
|-------|--------------|----------|
| Cold | < 100 | Use static defaults (0.85, 0.60) |
| Warm | 100-500 | Begin Thompson Sampling, wide exploration |
| Hot | > 500 | Full Thompson Sampling, exploitation focus |

**Transition Logic**:

```
if signal_count < 100:
    threshold = static_default
elif signal_count < 500:
    # Wide exploration: sample from prior
    threshold = sample_beta(alpha_prior + successes, beta_prior + failures)
else:
    # Narrow exploitation: sample from posterior
    threshold = sample_beta(alpha_posterior, beta_posterior)
```

#### 6.11.4 Per-Space with Global Fallback (Q4 Resolution)

**Decision**: Per-space thresholds with global fallback for new spaces.

**Hierarchy**:

```
Space threshold (if 100+ signals)
    ↓ fallback
Global threshold (aggregated from all spaces)
    ↓ fallback
Static defaults (0.85, 0.60)
```

**Global Aggregation**:

- Pool signals from all spaces (privacy-safe: only counts, not content)
- Update global Beta parameters nightly
- New spaces inherit global until they have 100 local signals

**Per-Space Isolation**:

- Each space has its own Beta parameters in `st_learned_weights`
- No cross-space signal leakage
- Family patterns differ from work patterns

**Storage Structure**:

| Weight Key | Scope | Purpose |
|------------|-------|---------|
| `reconcile_reinforce_alpha_{space_id}` | Per-space | Alpha for REINFORCE threshold |
| `reconcile_reinforce_beta_{space_id}` | Per-space | Beta for REINFORCE threshold |
| `reconcile_reinforce_alpha_global` | Global | Aggregated alpha |
| `reconcile_extend_lower_alpha_{space_id}` | Per-space | Alpha for EXTEND lower bound |

#### 6.11.5 Implementation Checklist

- [ ] Implement Thompson Sampling for threshold selection
- [ ] Store Beta parameters in `st_learned_weights` (per-space + global)
- [ ] Track reconciliation outcomes in `st_feedback_signals`
- [ ] Implement momentum-based parameter updates
- [ ] Add cold start phase detection (< 100, 100-500, > 500)
- [ ] Implement global aggregation (nightly job)
- [ ] Add stability bounds with alerts
- [ ] Add metrics: `p03_threshold_reinforce`, `p03_threshold_extend_lower`

---

### 6.12 Thompson Sampling (Proposal 3.1)

```python
threshold = np.random.beta(alpha, beta)
```

| # | Question | Status | Proposed Answer | Notes |
|---|----------|--------|-----------------|-------|
| 1 | What prior should we use? | ✅ Resolved | Beta(α, β) encoding current static threshold | See 6.12.1 |
| 2 | How do we define "success" for threshold update? | ✅ Resolved | Memory grounded without correction | See 6.12.2 |
| 3 | Should we use UCB instead of Thompson Sampling? | ✅ Resolved | Thompson Sampling (non-stationary) | See 6.12.3 |
| 4 | How do we handle exploration vs exploitation tradeoff? | ✅ Resolved | Natural via posterior sampling | See 6.12.4 |

#### 6.12.1 Prior Selection (Q1 Resolution)

**Goal**: Encode current static thresholds as informative priors.

**Prior Construction**:

| Threshold | Target Value | Prior | Effective Sample Size |
|-----------|--------------|-------|----------------------|
| REINFORCE | 0.85 | Beta(17, 3) | 20 |
| EXTEND_LOWER | 0.60 | Beta(12, 8) | 20 |

**Why These Values?**:

- Beta(α, β) has E[x] = α/(α+β)
- Beta(17, 3): E[x] = 17/20 = 0.85
- Beta(12, 8): E[x] = 12/20 = 0.60
- Effective sample size = α + β = 20 (moderate confidence)

**Prior Strength Tradeoff**:

- Stronger prior (higher α+β): slower to adapt, more stable
- Weaker prior (lower α+β): faster to adapt, less stable
- We chose α+β=20 as balance (50 signals to shift by ~0.05)

#### 6.12.2 Success Definition (Q2 Resolution)

**Challenge**: What makes a reconciliation decision "successful"?

**Success Criteria by Decision Type**:

| Decision | Success | Failure | Observation Window |
|----------|---------|---------|-------------------|
| REINFORCE | Memory grounded in K1 response | User corrects memory | 7 days |
| EXTEND | Extended version used | User reverts extension | 7 days |
| CREATE | New memory stays distinct | User merges with existing | 30 days |
| CONTRADICT | Contradiction accepted | User rejects resolution | 7 days |

**Signal Collection**:

1. Log reconciliation decision with threshold used
2. Track memory for observation window
3. Check for success/failure signals from `st_feedback_signals`
4. Update Beta parameters accordingly

**Delayed Feedback Handling**:

- Some outcomes take days to observe
- Use nightly batch to process delayed signals
- Associate feedback with original decision via `decision_id`

#### 6.12.3 Thompson Sampling vs UCB (Q3 Resolution)

**Decision**: Use Thompson Sampling.

**Comparison**:

| Criterion | Thompson Sampling | UCB |
|-----------|-------------------|-----|
| Non-stationary data | Good (forgets old data) | Poor (assumes stationarity) |
| Exploration | Probabilistic | Deterministic |
| Implementation | Simple | Moderate |
| Theoretical guarantees | Strong | Strong |
| Multi-armed bandits | Excellent | Good |

**Why Thompson Sampling for Memory**:

- User preferences change over time (non-stationary)
- Probabilistic exploration naturally handles uncertainty
- Simpler to implement with Beta-Bernoulli model
- Well-suited for batched feedback

**When UCB Might Be Better**:

- If we need deterministic reproducibility
- If feedback is immediate (not delayed)
- If data is truly stationary

#### 6.12.4 Exploration vs Exploitation (Q4 Resolution)

**How Thompson Sampling Handles This Naturally**:

**Early Stage** (high uncertainty):

- Posterior is wide (low α+β)
- Samples vary significantly
- High exploration automatically

**Late Stage** (low uncertainty):

- Posterior is narrow (high α+β)
- Samples cluster around mean
- High exploitation automatically

**Visual Intuition**:

```
Early: Beta(17, 3)  →  Samples: 0.65, 0.89, 0.78, 0.92, 0.71
       (wide spread, lots of exploration)

Late:  Beta(170, 30) → Samples: 0.84, 0.86, 0.85, 0.84, 0.85
       (narrow spread, exploitation)
```

**No Manual Epsilon Needed**:

- Unlike ε-greedy, no hyperparameter for exploration rate
- Uncertainty drives exploration automatically
- As confidence grows, exploration naturally decreases

**Forced Exploration** (optional):

- If posterior becomes too narrow too fast
- Periodically inject prior (reduce α, β proportionally)
- Feature flag: `P03_FF_THOMPSON_PRIOR_INJECTION=false`

#### 6.12.5 Implementation Checklist

- [ ] Implement Beta-Bernoulli Thompson Sampling
- [ ] Store (alpha, beta) pairs in `st_learned_weights`
- [ ] Define success criteria per decision type
- [ ] Implement delayed feedback processing (nightly job)
- [ ] Track `decision_id` for feedback association
- [ ] Add prior injection option (feature flag)
- [ ] Add metrics: `p03_thompson_samples`, `p03_thompson_successes`, `p03_thompson_failures`

---

### 6.13 Per-Entity Decay Calibration (Proposal 3.2)

```python
learned_lambda = fit_exponential(inter_access_intervals)
```

| # | Question | Status | Proposed Answer | Notes |
|---|----------|--------|-----------------|-------|
| 1 | How many access events needed to fit λ reliably? | ✅ Resolved | 5 accesses with >24h spread | See 6.13.1 |
| 2 | Should we use Bayesian estimation for λ? | ✅ Resolved | Yes, Gamma-Exponential conjugate | See 6.13.2 |
| 3 | How do we handle entities with no access history? | ✅ Resolved | Hierarchical fallback | See 6.13.3 |

#### 6.13.1 Minimum Access Requirements (Q1 Resolution)

**Problem**: Too few observations = unreliable λ estimate.

**Requirements Matrix**:

| Criterion | Requirement | Rationale |
|-----------|-------------|-----------|
| Minimum accesses | 5 | Statistical significance |
| Time spread | > 24h between first and last | Avoid same-day clustering |
| Interval variance | CV > 0.3 | Need variability to fit curve |

**Why These Values?**:

- 5 accesses: Minimum for exponential MLE to converge
- 24h spread: Captures day-over-day pattern, not session bursts
- CV > 0.3: Coefficient of variation ensures intervals aren't identical

**Insufficient Data Handling**:

| Data State | Action |
|------------|--------|
| 0 accesses | Use entity-type default λ |
| 1-4 accesses | Use entity-type default, but track |
| 5+ accesses, low spread | Use entity-type default, flag for review |
| 5+ accesses, good spread | Fit per-entity λ |

**Tracking for Future Learning**:

- Even with insufficient data, track access patterns
- When threshold reached, recalculate λ
- Store `access_count` and `first_access_at` on entity

#### 6.13.2 Bayesian Estimation (Q2 Resolution)

**Why Bayesian?**:

- Provides uncertainty quantification (confidence intervals)
- Handles small sample sizes gracefully
- Prior encodes domain knowledge (entity-type defaults)

**Conjugate Model**: Gamma-Exponential

| Component | Distribution | Parameters |
|-----------|--------------|------------|
| Prior on λ | Gamma(α₀, β₀) | α₀ = entity-type shape, β₀ = entity-type rate |
| Likelihood | Exponential(λ) | Inter-access intervals |
| Posterior | Gamma(α₀ + n, β₀ + Σxᵢ) | Closed-form update |

**Prior Construction from Entity-Type Defaults**:

| Entity Type | Default λ | Prior α₀ | Prior β₀ |
|-------------|-----------|----------|----------|
| PERSON | 0.002 | 2 | 1000 |
| FAMILY_MEMBER | 0.001 | 2 | 2000 |
| PLACE | 0.003 | 2 | 667 |
| THING | 0.005 | 2 | 400 |
| CONCEPT | 0.004 | 2 | 500 |

**Update Process**:

1. Collect inter-access intervals: [x₁, x₂, ..., xₙ] (in days)
2. Update posterior: α_post = α₀ + n, β_post = β₀ + Σxᵢ
3. Point estimate: λ_mean = α_post / β_post
4. 95% CI: [Gamma.ppf(0.025), Gamma.ppf(0.975)]

**Confidence-Based Application**:

| CI Width | Action |
|----------|--------|
| Narrow (< 20% of mean) | Use learned λ directly |
| Moderate (20-50%) | Blend learned λ with default |
| Wide (> 50%) | Use default, continue collecting |

#### 6.13.3 Hierarchical Fallback (Q3 Resolution)

**Problem**: New entities have no access history.

**Fallback Hierarchy**:

```
Per-entity λ (if 5+ accesses with good spread)
    ↓ fallback
Per-entity-type λ (space-specific, learned)
    ↓ fallback
Global entity-type λ (from dossier defaults)
    ↓ fallback
Layer default λ (from DECAY_CONFIGS)
```

**Examples**:

| Entity | Data Available | λ Used |
|--------|----------------|--------|
| "Mom" (FAMILY_MEMBER) | 20 accesses | Per-entity: 0.0008 |
| "Dr. Smith" (PERSON) | 3 accesses | Per-entity-type: 0.002 |
| "New Restaurant" (PLACE) | 0 accesses | Global PLACE: 0.003 |

**Warm-Up Period**:

- New entities inherit from entity-type for 30 days
- After 30 days, if still < 5 accesses, entity is likely unimportant
- Apply aggressive decay (higher λ) to low-access entities

#### 6.13.4 Implementation Checklist

- [ ] Add `access_count`, `first_access_at` tracking to entities
- [ ] Implement Gamma-Exponential Bayesian updater
- [ ] Store per-entity λ estimates in `st_learned_weights`
- [ ] Implement hierarchical fallback logic
- [ ] Add CI-based confidence checking
- [ ] Add metrics: `p03_per_entity_lambda_fitted`, `p03_lambda_ci_width`

---

### 6.14 Query Regret Tracking (Proposal 3.3)

```python
regret_signal = pruned_entity was later queried
```

| # | Question | Status | Proposed Answer | Notes |
|---|----------|--------|-----------------|-------|
| 1 | How long after pruning do we track regret? | ✅ Resolved | 14 days (extended from 7) | See 6.14.1 |
| 2 | How do we match queries to pruned entities? | ✅ Resolved | Embedding + name similarity | See 6.14.2 |
| 3 | What's the feedback weight for regret signals? | ✅ Resolved | 0.90 confidence (very high) | See 6.14.3 |

#### 6.14.1 Regret Tracking Window (Q1 Resolution)

**Decision**: 14-day window (extended from 7).

**Rationale**:

| Window | Pros | Cons |
|--------|------|------|
| 7 days | Lower storage | Miss delayed needs (e.g., weekly patterns) |
| 14 days | Catch weekly + biweekly patterns | Moderate storage |
| 30 days | Very comprehensive | High storage, stale signals |

**Why 14 Days**:

- Captures weekly patterns (people ask about things on same weekday)
- Captures biweekly patterns (payday, meetings)
- Storage is manageable (pruned entity data is small)
- After 14 days, if not queried, pruning was likely correct

**Storage Strategy**:

| Data | Retention | Storage Location |
|------|-----------|------------------|
| Pruned entity embedding | 14 days | `st_pruned_entities` |
| Pruned entity name | 14 days | `st_pruned_entities` |
| Pruning timestamp | 14 days | `st_pruned_entities` |
| Query match events | 30 days | `st_feedback_signals` |

**Cleanup Job**: Nightly job deletes entries older than 14 days from `st_pruned_entities`.

#### 6.14.2 Query-to-Pruned Matching (Q2 Resolution)

**Challenge**: User query "Mom's birthday" should match pruned entity "Mother's birthday reminder".

**Two-Stage Matching**:

| Stage | Method | Threshold |
|-------|--------|-----------|
| 1. Name match | Fuzzy string (Levenshtein + token overlap) | > 0.70 |
| 2. Semantic match | Embedding cosine similarity | > 0.75 |

**Match Decision**:

| Name Match | Embedding Match | Decision |
|------------|-----------------|----------|
| > 0.70 | > 0.75 | STRONG_MATCH → regret signal |
| > 0.70 | 0.60-0.75 | LIKELY_MATCH → weak regret |
| < 0.70 | > 0.85 | SEMANTIC_MATCH → regret signal |
| < 0.70 | < 0.85 | NO_MATCH |

**Context Boost**:

- Same space as pruned entity → boost match score by 0.1
- Same actor mentioned → boost by 0.05
- Same time window (e.g., morning) → boost by 0.03

**Efficient Matching**:

- Index pruned embeddings in vector store (pgvector)
- On query, search top-5 nearest pruned entities
- Run name match on candidates only

#### 6.14.3 Regret Signal Weight (Q3 Resolution)

**Decision**: 0.90 confidence (very high).

**Rationale**:

- Pruning an entity that user later queries is a clear mistake
- Strong signal to lower decay rate (λ) or raise importance
- User explicitly needed the information we removed

**Signal Processing**:

| Regret Type | Confidence | Action |
|-------------|------------|--------|
| STRONG_MATCH | 0.90 | Lower λ for entity type by 10% |
| LIKELY_MATCH | 0.70 | Lower λ by 5%, flag for review |
| Multiple regrets (same type) | 0.95 | Alert: pruning threshold too aggressive |

**Feedback Loop**:

```
Pruning → Store in st_pruned_entities → Query arrives
                                              ↓
                                    Match against pruned?
                                              ↓
                                    YES → REGRET signal
                                              ↓
                                    Lower λ or raise threshold
```

**Anti-Gaming**:

- Rate limit: max 10 regret signals per entity-type per day
- If regret rate > 20% of pruning rate → alert (threshold issue)

#### 6.14.4 st_pruned_entities Table

| Column | Type | Purpose |
|--------|------|---------|
| prune_id | TEXT | Primary key |
| entity_id | TEXT | Original entity ID |
| entity_type | TEXT | PERSON, PLACE, etc. |
| canonical_name | TEXT | For name matching |
| embedding | VECTOR(1024) | For semantic matching |
| space_id | TEXT | Isolation |
| decay_factor_at_prune | REAL | What was decay when pruned |
| pruned_at | BIGINT | Timestamp |
| matched_query_id | TEXT | If regret detected |
| matched_at | BIGINT | When regret detected |

#### 6.14.5 Implementation Checklist

- [ ] Create `st_pruned_entities` table with embeddings
- [ ] Implement pruning hook to store entity before archive
- [ ] Implement query-time matching against pruned entities
- [ ] Integrate with pgvector for efficient embedding search
- [ ] Add 14-day cleanup job
- [ ] Emit REGRET signals to `st_feedback_signals`
- [ ] Add λ adjustment based on regret rate
- [ ] Add metrics: `p03_prune_regrets`, `p03_prune_regret_rate`

---

### 6.15 Implicit Feedback Collection (Proposal 3.5)

| Signal | Source | Confidence |
|--------|--------|------------|
| MEMORY_MISS | P04 | 0.8 |
| REFORMULATION | K1 | 0.6 |
| CORRECTION | User | 0.9 |
| ABANDONMENT | Session | 0.5 |

| # | Question | Status | Proposed Answer | Notes |
|---|----------|--------|-----------------|-------|
| 1 | How do we detect reformulation reliably? | ✅ Resolved | Two-stage detection | See 6.15.1 |
| 2 | How do we distinguish abandonment from natural session end? | ✅ Resolved | Multi-factor detection | See 6.15.2 |
| 3 | How do we handle adversarial feedback? | ✅ Resolved | Rate + statistical anomaly | See 6.15.3 |
| 4 | Should we weight feedback by user engagement level? | ✅ Resolved | No — equal weighting | See 6.15.4 |

#### 6.15.1 Reformulation Detection (Q1 Resolution)

**Challenge**: User says "Tell me about Mom" → no good answer → user says "What about my mother?" → this is reformulation.

**Two-Stage Detection**:

| Stage | Check | Threshold |
|-------|-------|-----------|
| 1. Semantic similarity | Embedding cosine between Q1 and Q2 | > 0.70 |
| 2. Lexical difference | Token overlap ratio | < 0.50 |

**Decision Logic**:

- HIGH semantic similarity (same intent) + LOW lexical overlap (different words) = REFORMULATION
- If both conditions met within 120 seconds → emit reformulation signal

**Edge Cases**:

| Case | Detection | Action |
|------|-----------|--------|
| Follow-up question (related but different) | Semantic > 0.5, Lexical < 0.3 | NOT reformulation |
| Clarification ("I meant...") | Explicit marker | REFORMULATION (explicit) |
| Spelling correction ("Jhon" → "John") | Semantic ≈ 1.0, Lexical > 0.8 | NOT reformulation (typo fix) |

**Reformulation Signal**:

| Field | Value |
|-------|-------|
| signal_type | REFORMULATION |
| confidence | 0.60 |
| original_query_id | Q1 ID |
| reformulated_query_id | Q2 ID |
| time_gap_seconds | Time between Q1 and Q2 |
| affected_entities | Entities Q1 tried to retrieve |

**Feedback Action**: Entities that Q1 failed to retrieve → lower decay_factor slightly (user wanted them).

#### 6.15.2 Abandonment Detection (Q2 Resolution)

**Challenge**: Distinguish "user left because answer was bad" from "user got answer and left satisfied".

**Multi-Factor Detection**:

| Factor | Weight | Interpretation |
|--------|--------|----------------|
| Session duration after query | 0.40 | < 30s = likely abandonment |
| Query-to-last-interaction | 0.30 | Query is last action = abandonment |
| Response engagement | 0.20 | No scrolling/clicks = abandonment |
| Explicit satisfaction signal | 0.10 | Thumbs up/down if present |

**Decision Thresholds**:

| Scenario | Time After Query | Other Factors | Classification |
|----------|------------------|---------------|----------------|
| Quick exit | < 30s | Query is last action | ABANDONMENT |
| No engagement | 30-60s | No scroll, no click | LIKELY_ABANDONMENT |
| Some engagement | 60-120s | Some interaction | NEUTRAL |
| Good engagement | > 120s | Multiple interactions | SATISFIED |

**Time-of-Day Adjustment**:

- Late night (11pm-6am): Extend thresholds by 50% (user may be tired, slower)
- Peak hours (9am-6pm): Use standard thresholds

**Abandonment Signal**:

| Field | Value |
|-------|-------|
| signal_type | ABANDONMENT |
| confidence | 0.50 (low — inherently uncertain) |
| query_id | Query that led to abandonment |
| session_duration | Total session time |
| affected_entities | Entities returned (or not returned) |

**Feedback Action**: Low-confidence signal — use only in aggregate (10+ abandonments for same entity type → investigate).

#### 6.15.3 Adversarial Handling (Q3 Resolution)

**Threat Model**:

- Malicious actor tries to poison learning by generating fake feedback
- Compromised device sending automated corrections
- Bug causing feedback loops

**Defense Layers**:

| Layer | Mechanism | Threshold |
|-------|-----------|-----------|
| 1. Rate limiting | Per-user, per-device | 100 signals/min |
| 2. Velocity check | Sudden spike in signals | > 10× baseline |
| 3. Statistical anomaly | Signals that disagree with history | > 3σ deviation |
| 4. Entropy check | Too uniform feedback | Entropy < 0.3 |

**Response Actions**:

| Detection | Severity | Action |
|-----------|----------|--------|
| Rate limit exceeded | Low | Queue signals, process at normal rate |
| Velocity spike | Medium | Pause learning, alert, manual review |
| Statistical anomaly | Medium | Quarantine signals, investigate |
| Entropy anomaly | High | Disable learning for tenant, investigate |

**Quarantine Process**:

- Suspicious signals stored in `st_feedback_quarantine`
- Not applied to learning until reviewed
- Auto-release after 48h if no escalation
- Metrics: `p03_feedback_quarantine_count`, `p03_feedback_anomaly_rate`

#### 6.15.4 Engagement-Based Weighting (Q4 Resolution)

**Decision**: No engagement weighting — all users equal.

**Rationale**:

| Approach | Pros | Cons |
|----------|------|------|
| Power user weighting | Frequent users understand system | Creates feedback bias, new users ignored |
| Equal weighting | Fair, inclusive | Power users may be more accurate |
| Confidence-based | Weight by signal quality | Complex, requires meta-learning |

**Why Equal**:

- Simplicity: no need to track engagement levels
- Fairness: new users and casual users have equal voice
- Diversity: different usage patterns provide diverse signals
- Privacy: no need to profile users

**Exception**: Bot/automated accounts excluded from feedback entirely (detected via user-agent or rate patterns).

#### 6.15.5 Signal Confidence Summary

| Signal | Base Confidence | Adjustment Factors |
|--------|-----------------|-------------------|
| CORRECTION | 0.90 | +0.05 if explicit, -0.10 if via UI |
| MEMORY_MISS | 0.80 | +0.10 if user said "I told you" |
| REFORMULATION | 0.60 | +0.10 if explicit "I meant..." |
| ABANDONMENT | 0.50 | -0.20 if late night, +0.10 if repeat |

#### 6.15.6 Implementation Checklist

- [ ] Implement reformulation detector (embedding + lexical)
- [ ] Implement abandonment detector (multi-factor)
- [ ] Add rate limiting to feedback ingestion
- [ ] Add velocity and anomaly detection
- [ ] Create `st_feedback_quarantine` table
- [ ] Add metrics for all implicit feedback types
- [ ] Create feedback dashboard for monitoring
- [ ] Document signal interpretation for ops team

---

### 6.16 General / Cross-Cutting Questions

| # | Question | Status | Proposed Answer | Notes |
|---|----------|--------|-----------------|-------|
| 1 | How do we A/B test formula changes safely? | ✅ Resolved | Feature flags + shadow mode | See 6.16.1 |
| 2 | How do we rollback if learning goes wrong? | ✅ Resolved | Automated + manual rollback | See 6.16.2 |
| 3 | How do we explain formula decisions to users? | ✅ Resolved | Audit trail + natural language | See 6.16.3 |
| 4 | How do we handle multi-tenant parameter isolation? | ✅ Resolved | Strict per-space isolation | See 6.16.4 |
| 5 | What's the compute budget for online learning? | ✅ Resolved | < 5% of cycle time | See 6.16.5 |

#### 6.16.1 A/B Testing Formula Changes (Q1 Resolution)

**Strategy**: Feature flags + shadow mode + gradual rollout.

**Testing Phases**:

| Phase | Description | Duration | Risk |
|-------|-------------|----------|------|
| 0. Shadow | Both old + new run, new results discarded | 7 days | Zero |
| 1. Canary | 5% of spaces use new formula | 7 days | Very low |
| 2. Gradual | 25% → 50% → 75% rollout | 14 days | Low |
| 3. Full | 100% on new formula | Permanent | Normal |

**Shadow Mode Details**:

- Old formula applies changes to database
- New formula computes but does NOT apply
- Log both outcomes for comparison
- Metrics: accuracy, performance, edge cases

**Comparison Metrics**:

| Metric | Success Criteria |
|--------|------------------|
| Memory retrieval accuracy | New ≥ Old |
| Decay calibration error | New < Old by > 5% |
| Processing time | New ≤ Old × 1.1 |
| Edge case handling | No regressions |

**Rollout Decision**:

- Automatic promotion if all metrics pass
- Human review if any metric is borderline
- Automatic halt if any metric regresses > 10%

#### 6.16.2 Rollback Mechanism (Q2 Resolution)

**Two-Level Rollback**:

| Level | Scope | Trigger | Speed |
|-------|-------|---------|-------|
| Parameter rollback | Learned weights only | Quality drop | Instant |
| Formula rollback | Algorithm version | Bug or regression | Minutes |

**Parameter Rollback**:

- `st_learned_weights` stores history (last 10 versions per parameter)
- Rollback = restore previous version
- Automatic trigger: quality metric drops > 15% in 24h

**Parameter History Schema**:

| Column | Type | Purpose |
|--------|------|---------|
| param_key | TEXT | e.g., "decay_lambda_PERSON" |
| version | INT | 1, 2, 3, ... |
| value | JSONB | Parameter value |
| applied_at | BIGINT | When applied |
| quality_at_time | REAL | Quality metric when applied |
| space_id | TEXT | Isolation |

**Formula Rollback**:

- Feature flag controls which algorithm version runs
- Rollback = flip feature flag to previous version
- All spaces affected simultaneously

**Automatic Rollback Triggers**:

| Signal | Threshold | Action |
|--------|-----------|--------|
| Memory retrieval accuracy drop | > 15% | Rollback parameters |
| User corrections spike | > 3× baseline | Alert + manual review |
| Processing time spike | > 2× baseline | Rollback formula |
| Error rate | > 5% | Immediate halt |

#### 6.16.3 Explainability (Q3 Resolution)

**Requirement**: Users should understand why memory decisions were made.

**Three Levels**:

| Level | Audience | Detail |
|-------|----------|--------|
| User-facing | End users | Natural language explanation |
| Ops-facing | Support team | Structured audit trail |
| Debug-facing | Developers | Full computation trace |

**User-Facing Explanations**:

| Decision | Template |
|----------|----------|
| Memory reinforced | "This memory was reinforced because you mentioned {entity} frequently this week." |
| Memory decayed | "This memory faded because it hasn't been accessed in {N} days." |
| Memory archived | "This memory was archived to make room for more recent information." |
| Memory merged | "These two memories were combined because they refer to the same {entity_type}." |

**st_consolidation_audit Table**:

| Column | Type | Purpose |
|--------|------|---------|
| audit_id | TEXT | Primary key |
| memory_id | TEXT | Affected memory |
| action | TEXT | REINFORCE, DECAY, ARCHIVE, MERGE |
| formula_used | TEXT | e.g., "hebbian_v2" |
| inputs | JSONB | Input parameters |
| outputs | JSONB | Output values |
| explanation | TEXT | User-friendly explanation |
| timestamp | BIGINT | When decision was made |
| space_id | TEXT | Isolation |

**Retention**: Audit records kept for 90 days, then aggregated.

#### 6.16.4 Multi-Tenant Isolation (Q4 Resolution)

**Principle**: Absolute isolation — no cross-space learning leakage.

**Isolation Boundaries**:

| Data Type | Isolation Level | Mechanism |
|-----------|-----------------|-----------|
| Learned weights | Per-space | space_id column in st_learned_weights |
| Feedback signals | Per-space | space_id column in st_feedback_signals |
| Audit records | Per-space | space_id column in st_consolidation_audit |
| Feature flags | Per-space | space_id column in st_feature_flags |

**Isolation Enforcement**:

- Every query includes `WHERE space_id = ?`
- Row-level security (RLS) enabled on all learning tables
- No global learning aggregation (each space learns independently)

**Cross-Space Exceptions** (NONE currently):

- No shared priors across spaces
- No global defaults learned from other spaces
- Static defaults only come from code configuration

**Audit**:

- Quarterly review of queries for space_id leakage
- Metrics: `p03_cross_space_query_attempts` (should be 0)

#### 6.16.5 Compute Budget (Q5 Resolution)

**Budget**: Online learning uses < 5% of P03 consolidation cycle time.

**Breakdown**:

| Component | % of Learning Budget | Absolute Target |
|-----------|---------------------|-----------------|
| Feedback ingestion | 20% | < 10ms per signal |
| Parameter update | 30% | < 50ms per update |
| Quality monitoring | 30% | < 100ms per cycle |
| Audit logging | 20% | < 20ms per record |

**Performance Guardrails**:

| Operation | Max Time | Action if Exceeded |
|-----------|----------|-------------------|
| Single feedback processing | 50ms | Queue for batch |
| Parameter update | 100ms | Skip, retry next cycle |
| Quality check | 200ms | Sample (10%) instead |
| Audit write | 50ms | Async write |

**Optimization Strategies**:

- Batch feedback processing (every 1 minute, not per-signal)
- Incremental parameter updates (momentum, not full recompute)
- Quality sampling (10% of decisions audited in detail)
- Async audit writes (non-blocking)

**Metrics**:

- `p03_learning_time_pct`: % of cycle time spent on learning
- `p03_learning_latency_p99`: 99th percentile learning operation time
- `p03_learning_queue_depth`: Pending feedback signals

#### 6.16.6 Cross-Cutting Implementation Checklist

- [ ] Implement feature flag system for A/B testing
- [ ] Add shadow mode capability to all formulas
- [ ] Create parameter history table with rollback
- [ ] Implement automatic rollback triggers
- [ ] Create user-facing explanation templates
- [ ] Add `st_consolidation_audit` table
- [ ] Enforce RLS on all learning tables
- [ ] Add space_id to all queries (audit)
- [ ] Implement compute budget monitoring
- [ ] Add batch processing for feedback
- [ ] Create learning ops dashboard

---

## 7. Summary: Resolved vs Open

### All Questions Resolved

| Section | Questions | Resolved | Open |
|---------|-----------|----------|------|
| 6.1 Importance Score | 3 | 3 | 0 |
| 6.2 Hebbian | 5 | 5 | 0 |
| 6.3 DBSCAN | 3 | 3 | 0 |
| 6.4 Decay Function | 6 | 6 | 0 |
| 6.5 Novelty Score | 3 | 3 | 0 |
| 6.6 SimHash | 3 | 3 | 0 |
| 6.7 Entity Disambiguation | 4 | 4 | 0 |
| 6.8 Granger Causality | 4 | 4 | 0 |
| 6.9 UCT/MCTS | 4 | 4 | 0 |
| 6.10 Multi-Factor Similarity | 4 | 4 | 0 |
| 6.11 Reconciliation Thresholds | 3 | 3 | 0 |
| 6.12 Thompson Sampling | 4 | 4 | 0 |
| 6.13 Per-Entity Decay | 3 | 3 | 0 |
| 6.14 Query Regret | 3 | 3 | 0 |
| 6.15 Implicit Feedback | 4 | 4 | 0 |
| 6.16 Cross-Cutting | 5 | 5 | 0 |
| **TOTAL** | **61** | **61** | **0** |

### Key Design Decisions Summary

| Area | Decision | Rationale |
|------|----------|-----------|
| Learning storage | `st_learned_weights` unified | Single source of truth |
| Feedback collection | `st_feedback_signals` unified | Consistent ingestion |
| Parameter hierarchy | Per-entity → type → space → global | Granular + fallback |
| Cold start | Static defaults until 100-1000 signals | Conservative |
| Threshold learning | Thompson Sampling (Beta-Bernoulli) | Well-understood, robust |
| Continuous learning | Bayesian (Gamma-Exponential) | Conjugate, efficient |
| Stability | Momentum 0.9, clamping, gradual rollout | Prevent oscillation |
| Rollback | Automatic + manual, parameter history | Safety net |
| Isolation | Strict per-space, RLS enforced | Privacy, correctness |
| Compute budget | < 5% of cycle time | Lightweight |

---

*End of Whiteboard — All Open Questions Resolved*
