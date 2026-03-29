---
adr_number: 'K024'
affected_layers: [k0]
affected_modules:
- consolidation/algorithms/importance_weight_learner
- consolidation/algorithms/importance_scorer
- pipelines/p03/phases/r1_importance_scorer
- pipelines/p03/stores
authors:
- K0 Architecture Team
concerns:
- architecture
- learning-system
- importance-scoring
date_created: '2025-07-23'
date_updated: '2025-07-23'
implementation_date: '2025-07-23'
implementation_phase: M5.W
implementation_status: ACCEPTED
propagation:
  affected_adrs:
  - K023
  affected_contracts:
  - p03_consolidation.v1.yaml
  affected_tests:
  - tests/k0/modules/consolidation/algorithms/test_importance_weight_learner.py
  triggers:
  - Weight learner output must be consumable by ImportanceScorer
  - Learner trains on CONFIG_B component structure
related_adrs:
- k023-r4-hebbian-delegation-strategy
related_contracts:
- k0/contracts/pipelines/p03_consolidation.v1.yaml
related_diagrams: []
research_citations:
- McGaugh 2004 (emotional memory encoding)
- Ranganath & Rainer 2003 (surprise and prediction error)
status: ACCEPTED
superseded_by: []
supersedes: []
title: Weight Learner Component Alignment with CONFIG_B Scorer
---

# ADR-K024: Weight Learner Component Alignment with CONFIG_B Scorer

**Status**: Accepted

**Date**: 2025-07-23

**Authors**: K0 Architecture Team

## Context

ImportanceWeightLearner trains weights for 4 components:
- emotional (0.35), recency (0.25), access (0.20), social (0.20)

ImportanceScorer (CONFIG_B, POC validated 120/120) uses 8 components:
- sentiment (0.10), affect (0.12), arousal (0.08), surprise (0.15),
  novelty (0.15), social (0.15), identity (0.10), recency (0.15)

This creates 3 categories of mismatch:

1. **Missing components**: surprise, novelty, identity have no learner equivalent
2. **Naming mismatch**: learner has "access" (no scorer equivalent)
3. **Granularity mismatch**: learner "emotional" = one weight; scorer splits into
   sentiment_weight + affect_weight + arousal_weight

The learner's output `{emotional: X, recency: Y, access: Z, social: W}` cannot be
consumed by `ImportanceScorer._weights_from_dict()` which expects keys:
sentiment, affect, arousal, surprise, novelty, social, identity, recency.

Even if the learner ran today, learned weights would be invisible to the scorer.

## Decision

**Option A: Expand learner to 8 components matching CONFIG_B exactly.**

The ImportanceWeightLearner COMPONENTS list changes from:
```python
COMPONENTS = ["emotional", "recency", "access", "social"]
```
to:
```python
COMPONENTS = ["sentiment", "affect", "arousal", "surprise", "novelty", "social", "identity", "recency"]
```

WeightLearnerConfig priors change from 4 values to 8 values matching CONFIG_B defaults:
```python
prior_sentiment: float = 0.10
prior_affect: float = 0.12
prior_arousal: float = 0.08
prior_surprise: float = 0.15
prior_novelty: float = 0.15
prior_social: float = 0.15
prior_identity: float = 0.10
prior_recency: float = 0.15
```

TrainingSample changes from 4 features to 8 features matching scorer inputs:
```python
sentiment_score: float   # abs(sentiment_score) from P03EventState
affect_score: float      # abs(affect_valence) from P03EventState
arousal_score: float     # affect_arousal from P03EventState
surprise_score: float    # surprise_level from P03EventState
novelty_score: float     # NOVELTY_MAP[novelty] from P03EventState
social_score: float      # log2(participants)/3.32 * intimacy from P03EventState
identity_score: float    # identity_relevance from P03EventState
recency_score: float     # exp(-0.005 * hours) from P03EventState
```

### Key Mapping

| Learner Component | Scorer Weight Field | P03EventState Source |
|-------------------|--------------------|--------------------|
| sentiment | sentiment_weight | abs(sentiment_score) |
| affect | affect_weight | abs(affect_valence) |
| arousal | arousal_weight | affect_arousal |
| surprise | surprise_weight | surprise_level |
| novelty | novelty_weight | NOVELTY_MAP[novelty] |
| social | social_weight | log2(num_participants)/3.32 * INTIMACY_SCALE[social_intimacy] |
| identity | identity_weight | identity_relevance (fallback: len(identity_domains)/9.0) |
| recency | recency_weight | exp(-0.005 * hours_since_event) |

### Weight Flow

```
Learner.get_weights()
  -> {"sentiment": 0.11, "affect": 0.13, ...}
  -> persist_weights() writes to st_learned_weights
     keys: importance_sentiment, importance_affect, ...
  -> SyscallWeightStore.get_weights(prefix="importance_")
     strips prefix -> {"sentiment": 0.11, "affect": 0.13, ...}
  -> ImportanceScorer._weights_from_dict(d)
     -> ImportanceWeights(sentiment_weight=d["sentiment"], ...)
```

This flow works end-to-end because:
1. `persist_weights()` uses `f"importance_{component}"` as param_key
2. `SyscallWeightStore.get_weights()` strips the `importance_` prefix
3. `_weights_from_dict()` maps short keys to ImportanceWeights fields

## Consequences

### Positive

- Direct 1:1 mapping between learner output and scorer input
- No translation layer needed
- Learner priors match CONFIG_B defaults (POC validated 120/120)
- All 8 components independently learnable per family space
- TrainingSample features derive from the same P03EventState fields the scorer uses

### Negative

- Learner weight space increases from 4D to 8D (more parameters to learn)
- 8D softmax normalization may need slightly more samples to converge
- All existing learner tests must be updated for 8 components

### Risks

- **Higher sample requirement**: 8 weights may need > 500 samples to converge.
  Mitigation: CONFIG_B priors are strong (POC validated); learner starts from
  good defaults and only adjusts incrementally.
- **Correlated components**: sentiment, affect, arousal are correlated.
  Mitigation: Softmax + clamping prevents any one component from dominating.
  The learner can discover family-specific patterns (e.g., a family that values
  surprise over emotional intensity).

## Alternatives Considered

### Alternative B: Group weights with sub-distribution

Learner trains group weights (emotional_group, cognitive_group, social_group,
temporal_group). Scorer distributes within group using fixed ratios.

Rejected because:
- Adds a translation layer between learner and scorer
- Cannot learn that a family values surprise but not novelty (both cognitive)
- Harder to debug and audit weight flow

### Alternative C: Hierarchical learning

Learner trains 6 group weights; sub-weights within groups are fixed ratios
derived from CONFIG_B proportions.

Rejected because:
- Overly complex for current stage
- Cannot differentiate between sentiment and arousal within emotional group
- Reduces personalization granularity

## Implementation Notes

- **Phase 1**: Update WeightLearnerConfig, COMPONENTS, priors (5.W.1.2)
- **Phase 2**: Update TrainingSample and feature extraction (5.W.1.3)
- **Phase 3**: Verify persist/load works with new keys (5.W.1.4)
- **Phase 4**: Comprehensive tests (5.W.1.5)
- **Backward compatibility**: No existing learned weights in production (learner
  never activated). No migration needed for st_learned_weights rows.
- **Rollback**: Revert COMPONENTS to 4 elements; priors to original values.

## References

- **Plan**: docs/plans/PLAN_HEBBIAN_WEIGHT_LEARNER_INTEGRATION.md (M5.W section)
- **ImportanceScorer**: k0/modules/consolidation/algorithms/importance_scorer.py
- **ImportanceWeightLearner**: k0/modules/consolidation/algorithms/importance_weight_learner.py
- **Related ADR**: K023 (R4 Hebbian delegation strategy)
- **CONFIG_B validation**: POC 562K events, 120/120 scenarios

## Revision History

- 2025-07-23: Accepted (K0 Architecture Team)
