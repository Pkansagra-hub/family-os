# R1 Weight Research Plan

> **Status**: PLANNED
> **Date**: 2026-03-02
> **Depends on**: Epic 5A.1 + 5A.2 (complete), 565K event dataset
> **Output**: Chosen weight configuration, lambda, reliability floor -- fed into Epic 5.2-REDESIGN
> **Reference**: P03_R1_IMPORTANCE_SCORING_DISCOVERY.md Section 16

---

## 1. Objective

Find the optimal weight distribution for the R1 importance scoring formula using 565K real family events.

**We are NOT building a model.** We are running the proposed formula (Section 16.6.2) with 4 pre-defined weight configurations across real data, measuring which configuration best separates high-importance events from low-importance events using proxy ground truth labels derived from safety + hub routing signals.

---

## 2. Dataset

| Property | Value |
| - | - |
| Location | `D:\Modeling_studio\data\familyos\unified\output_healed_merged\` |
| Format | JSONL, 1 event per line |
| Shards | 113 files (shard_0000.jsonl to shard_0112.jsonl) |
| Events per shard | ~5,000 |
| Total events | ~565,000 |
| Total size | ~305 MB |
| Fields per event | id, text, tasks (8 sub-fields), hub_routing (4 booleans) |

---

## 3. Research Phases

### Phase 1: Signal Derivation Layer

Build a Python module that converts raw event JSON into R1-compatible signal vectors.

**Deliverable**: `poc/r1_weight_research/signal_derive.py`

| Derivation | Input | Output | Method |
| - | - | - | - |
| sentiment_score | tasks.sentiment | float [-1, 1] | Categorical map (5 levels) |
| affect_valence | tasks.emotions | float [-1, 1] | NRC-VAD lexicon average |
| affect_arousal | tasks.emotions | float [0, 1] | NRC-VAD lexicon average |
| affect_dominance | tasks.emotions | float [0, 1] | NRC-VAD lexicon average |
| num_participants | tasks.ner_family | int >= 1 | count(KINSHIP + PERSON) + 1 |
| social_intimacy | tasks.relations | LOW/MED/HIGH | Predicate hierarchy map |
| activity_type | tasks.ingress | enum (12) | Ingress-to-activity map |
| intent | tasks.intent | enum (8) | Direct 1:1 |
| surprise_level | tasks.emotions | float [0, 1] | 1.0 if "surprise" in list, else 0.0 |
| novelty | tasks.ingress + NER | enum (4) | Heuristic rules (see 16.9.3) |
| identity_relevance | tasks.ner_family | float [0, 1] | Identity-NER density |
| elaboration_depth | text | enum (4) | Word count heuristic |
| temporal_orientation | tasks.temporal + intent | enum (3) | Heuristic rules |

**NRC-VAD lexicon**: Build a 44-entry lookup table mapping each FamilyOS emotion label to [valence, arousal, dominance]. Labels not directly in NRC-VAD (parental_guilt, togetherness, bittersweet, etc.) will be mapped by closest semantic match or compound average.

### Phase 2: Proxy Ground Truth Labeling

Build a labeling function that assigns proxy importance tiers from safety + routing.

**Deliverable**: `poc/r1_weight_research/proxy_labels.py`

| Proxy Tier | Rule | Expected % |
| - | - | - |
| CRITICAL | safety = CRISIS | ~0.4% |
| HIGH | safety = RED OR (AMBER + EMO + very_negative) | ~5% |
| MEDIUM-HIGH | EMO + REL + MEM all true | ~15% |
| MEDIUM | EMO + (REL or MEM) | ~25% |
| LOW-MEDIUM | EMO only, non-neutral sentiment | ~20% |
| LOW | no routing or neutral-only | ~35% |

### Phase 3: Formula Implementation

Implement the proposed R1 formula (Section 16.6.2) as a standalone scoring function.

**Deliverable**: `poc/r1_weight_research/scorer.py`

The formula takes a signal vector + weight configuration and returns importance_score [0, 1].

Constants set for this research (no variance in dataset):
- source_type = "user_stated" for all (reliability = 0.95)
- narrative_is_goal_event = False for all (goal_boost = 1.0)
- narrative_arc_position = "EXPOSITION" for all (arc_boost = 1.0)
- memory_tier = "routine" for all (tier_mult = 1.0)
- recency: all events scored as "just happened" (recency = 1.0) -- recency tested separately in Phase 5

### Phase 4: Weight Configuration Scoring

Run all 565K events through the formula with 4 weight configurations.

**Deliverable**: `poc/r1_weight_research/run_matrix.py` + results CSV

**Weight Configs** (from Section 16.6.3):

| Config | Emotional | Surprise | Novelty | Social | Identity | Recency |
| - | - | - | - | - | - | - |
| A (Balanced) | 0.20 | 0.15 | 0.20 | 0.15 | 0.15 | 0.15 |
| B (Emotion-heavy) | 0.30 | 0.15 | 0.15 | 0.15 | 0.10 | 0.15 |
| C (Social-Identity) | 0.20 | 0.10 | 0.15 | 0.20 | 0.20 | 0.15 |
| D (Novelty-Surprise) | 0.15 | 0.20 | 0.25 | 0.10 | 0.15 | 0.15 |

**Metrics per configuration**:
- Tier separation: mean score per proxy tier (want CRITICAL >> HIGH >> MEDIUM >> LOW)
- Cohen's d between adjacent tiers (want d > 0.5 for each pair)
- Score distribution histogram (want spread, not clustering)
- Misclassification rate: events scored > 0.8 but proxy = LOW (false positives)
- Misclassification rate: events scored < 0.3 but proxy = HIGH/CRITICAL (false negatives)

### Phase 5: Lambda + Floor Calibration

Using the winning weight config from Phase 4, test recency lambda and reliability floor.

**Deliverable**: Results appended to the same CSV + analysis notebook

**Lambda test**: Score the same events at simulated ages (1h, 6h, 24h, 72h, 168h) with lambda values [0.005, 0.01, 0.02, 0.05]. Find the lambda where tier boundaries remain stable across reasonable age ranges.

**Reliability floor test**: Cannot test with this dataset (all events are user_stated). Use the 15 hand-crafted scenarios from Section 16.6.4 instead. Score scenarios 6 + 15 with floor values [0.3, 0.5, 0.7, no floor].

### Phase 6: Validation Against Hand-Crafted Scenarios

Run the 15 scenarios from Section 16.6.4 through the winning configuration.

**Deliverable**: Comparison table -- expected tier vs computed tier for all 15 scenarios

**Pass criteria**: <= 2 mismatches out of 15 scenarios. Any mismatch on scenario 1 (Sharvi's first word) or scenario 2 (breakfast alone) is an automatic fail.

---

## 4. File Structure

```
poc/r1_weight_research/
    __init__.py
    signal_derive.py      -- Phase 1: raw JSON -> R1 signal vector
    nrc_vad_lexicon.py    -- NRC-VAD mappings for 44 FamilyOS emotion labels
    proxy_labels.py       -- Phase 2: safety + routing -> proxy tier
    scorer.py             -- Phase 3: signal vector + weights -> importance
    run_matrix.py         -- Phase 4: batch scoring + metrics
    scenarios.py          -- Phase 6: 15 hand-crafted validation scenarios
    config.py             -- Weight configs A/B/C/D, lambda values, floor values
    results/
        scores_config_A.csv
        scores_config_B.csv
        scores_config_C.csv
        scores_config_D.csv
        summary.md         -- Final results + chosen configuration
```

---

## 5. Acceptance Criteria

| # | Criterion | How Verified |
| - | - | - |
| 1 | Signal derivation runs on 565K events without errors | run_matrix.py completes on all 113 shards |
| 2 | All 4 configs produce score distributions with visible tier separation | Histogram plots show multi-modal distribution |
| 3 | Winning config has Cohen's d > 0.5 between all adjacent proxy tiers | Computed in run_matrix.py |
| 4 | Winning config passes 13/15 hand-crafted scenarios | scenarios.py comparison table |
| 5 | Scenario 1 (milestone) scores > 0.85 | scenarios.py |
| 6 | Scenario 2 (routine breakfast) scores < 0.25 | scenarios.py |
| 7 | Results are documented in results/summary.md with chosen weights + lambda + floor | File exists and is complete |

---

## 6. What This Research Does NOT Do

- Does NOT train a model or learn weights from data
- Does NOT modify any production code in k0/
- Does NOT require database access or running P03 pipeline
- Does NOT test weight learner / Hebbian / Thompson Sampling
- Does NOT test narrative or salience signals (not in dataset)

This is a **static formula evaluation** across 4 pre-defined weight sets on real data with proxy labels.

---

## 7. Next Steps After Research

1. Document chosen config (weights, lambda, floor) in an ADR appendix
2. Update Section 16.6 of discovery doc with actual results
3. Proceed to Epic 5.2-REDESIGN with validated weights
4. Build R1 with the winning formula -- no guessing
