# ADR-K026: KG Relationship Boost for R1 Importance Scoring

**Status**: ACCEPTED
**Date**: 2026-03-03
**Deciders**: K0 Team
**Issue**: 5.F.1.1

## Context

R1 importance scoring (CONFIG_B) currently computes scores using 6 additive
components and 7 multiplicative modulators. The formula treats every event
identically regardless of whether the mentioned entities have a strong or
weak relationship in the knowledge graph.

This means an event mentioning Mom and Dad (who have edge_weight 0.9 in
st_kg_edges) scores identically to an event mentioning two strangers -- the
KG's accumulated relationship knowledge is invisible to importance scoring.

The plan (M6.F) calls for closing this loop: strong KG edges should boost
importance, creating a virtuous cycle where frequently co-occurring entities
in important events gradually become more important themselves.

## Decision

**Option A (CHOSEN): Multiplicative relationship_boost modulator**

Add `relationship_boost` as the 8th multiplicative modulator in CONFIG_B,
applied after `intent_boost` and before `tier_multiplier`:

```
importance = clamp(base * elab * goal * arc * temporal
                   * type * intent * relationship * tier * reliability, 0, 1)
```

### Boost Formula

```
relationship_boost = 1.0 + boost_scale * max_edge_weight
```

Where:
- `boost_scale` = 0.15 (configurable, default conservative)
- `max_edge_weight` = maximum edge_weight among all entity pairs in the event
- Edge weights are in [0, 1] from st_kg_edges (Hebbian maintained)
- Result range: [1.0, 1.15] -- boost only, never penalize

### Entity Extraction

R1 extracts entity IDs from `event.ner_entities_json` (JSON array populated
by P02/UltraBERT NER). Each entity has a `canonical_name` and `entity_type`.
Entity pairs are formed from all combinations within the event.

### Edge Weight Lookup

R1 uses the existing `kg_edges_query` syscall to batch-load ALL active edges
for the space once per cycle. This creates an in-memory lookup dict keyed by
`sorted(source_id, target_id)` pairs. Per-event lookups are O(1) dict lookups.

Performance budget: The batch query adds ~10-50ms once per cycle (amortized
across all events). Per-event lookup is <0.01ms. Total R1 phase stays within
the 30ms/event contract budget.

### Feature Flag

`R1Config.enable_kg_boost: bool = False` -- disabled by default until KG has
meaningful Hebbian-maintained edges. When disabled, `relationship_boost = 1.0`
(multiplicative identity, zero impact).

### Boost Cap

Maximum boost is capped at `1.0 + max_boost_cap` where `max_boost_cap = 0.20`.
Even if boost_scale is misconfigured, the boost never exceeds 1.20x.

## Alternatives Considered

**Option B: Additive KG component (rejected)**
Add a 7th additive component `kg_relationship` with its own weight.
Rejected because:
- Changes the weight sum from 1.0 (would need rebalancing all 8 weights)
- Less intuitive: relationship context is a contextual modifier, not a signal dimension
- Would require retraining the weight learner

**Option C: Per-entity boost (rejected)**
Instead of max edge weight per event, compute per-entity importance.
Rejected because:
- More complex with unclear benefit over max-edge approach
- Requires entity-level scoring, not event-level
- Harder to explain in audit breakdown

## Consequences

### Positive
- Events about strongly-connected entities score higher (personalization)
- KG knowledge feeds back into importance (closes the learning loop)
- Multiplicative modulator preserves existing base score distribution
- Feature flag enables gradual rollout and safe testing
- Audit breakdown includes relationship_boost for explainability

### Negative
- R1 now requires `st_kg_edges.read` capability (new dependency)
- One additional DB query per P03 cycle (mitigated by batch loading)
- Potential reinforcement runaway (mitigated by boost cap + Hebbian soft saturation)

### Convergence Safety
- Hebbian apply_decay prevents edge weights from growing unboundedly
- Boost cap (1.20x max) limits per-cycle inflation
- Soft saturation in HebbianLearner.update_edge_weight() caps at 1.0
- Combined: even with maximum reinforcement, importance scores converge

## Performance Impact

| Metric | Before | After (flag ON) | Budget |
|--------|--------|-----------------|--------|
| R1 per-event | <1ms | <1.01ms | 30ms |
| R1 batch (once/cycle) | 0ms | +10-50ms | N/A |
| Memory | 0 | ~100KB edge cache | N/A |

## References

- Plan: `docs/plans/PLAN_HEBBIAN_WEIGHT_LEARNER_INTEGRATION.md` Epic 5.F.1
- ADR-K024: Weight learner component alignment (8 CONFIG_B components)
- ADR-K025: Grounding signal sources
- CONFIG_B: `k0/modules/consolidation/algorithms/importance_scorer.py`
- KG edges: `k0/kernel/syscalls.py` kg_edges_query()
