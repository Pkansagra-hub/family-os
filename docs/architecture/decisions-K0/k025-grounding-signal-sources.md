# ADR-K025: Grounding Signal Sources and Reliability Weighting

| Field     | Value                         |
|-----------|-------------------------------|
| Status    | ACCEPTED                      |
| Date      | 2025-07-22                    |
| Deciders  | K0 Team                       |
| Issue     | 5.W.2.1                       |
| Milestone | M5.W (Weight Learner Alignment)|

## Context

ImportanceWeightLearner trains on `(features, was_grounded)` pairs using binary
cross-entropy loss. A "grounded" event is one confirmed as important through
downstream signals. The learner needs a source for these grounding labels.

Multiple potential sources exist with varying reliability and availability:

| Source                | Reliability | Available Now? |
|-----------------------|-------------|----------------|
| K1 recall queries     | HIGH        | Future         |
| Explicit star/save    | HIGH        | Future         |
| R3 reconciliation     | MEDIUM-HIGH | YES            |
| R5 dream selection    | MEDIUM      | Partially      |
| P08 retrieval hits    | MEDIUM      | Future         |
| Time-based survival   | LOW         | Computable     |

## Decision

**Option A: R3 Reconciliation-Based Grounding (same-cycle, extensible)**

Use the R3 reconciliation action as the primary grounding signal:

| R3 Action     | Grounded? | Confidence | Rationale                                   |
|---------------|-----------|------------|---------------------------------------------|
| REINFORCE     | YES       | 0.8        | Matches existing truth, user-relevant pattern|
| EXTEND        | YES       | 0.7        | Adds detail to existing truth               |
| CREATE        | YES       | 0.5        | Novel enough to warrant new truth record     |
| EVOLVE        | YES       | 0.6        | Significant enough to version existing truth |
| CONTRADICT    | YES       | 0.4        | Important enough to conflict with truth      |
| SKIP          | NO        | 0.9        | Duplicate or filtered                        |
| PRUNE         | NO        | 0.8        | Below decay threshold                        |
| PENDING       | EXCLUDED  | --         | Not yet decided, skip                        |

### Feature Extraction

8 CONFIG_B features extracted from P03EventState (ADR-K024):

| Feature   | Source Field                  | Transform              |
|-----------|-------------------------------|------------------------|
| sentiment | sentiment_score               | abs(value)             |
| affect    | affect_valence                | abs(value)             |
| arousal   | affect_arousal                | direct [0,1]           |
| surprise  | surprise_level                | direct [0,1]           |
| novelty   | novelty (categorical)         | NOVELTY_MAP lookup     |
| social    | num_participants, social_intimacy | log2/3.32 * intimacy |
| identity  | identity_relevance            | direct [0,1]           |
| recency   | timestamp + now_ms            | exp(-0.005 * hours)    |

### Training Flow

```
P03 Cycle:
  R0 -> R1 (score events, extract features)
     -> R2 (cluster)
     -> R3 (reconcile -- grounding labels available)
     -> [TRAINING POINT: build TrainingSamples from R1 features + R3 labels]
     -> R4 (Hebbian)
     -> R5-R8 ...
```

Training is gated:
- Minimum 50 events in batch (min_batch_size)
- Total sample_count tracked across cycles
- Cold-start blending until 500+ samples (existing mechanism)

### Extensibility

The GroundingSignalCollector accepts pluggable signal sources:

```python
class GroundingSignalSource(Protocol):
    async def collect(self, event_ids: List[str]) -> Dict[str, GroundingSignal]: ...
```

Future sources (K1 recall, explicit save, P08 retrieval) register as additional
sources with higher reliability weights that override R3-only labels.

## Alternatives Considered

### Option B: Multi-source with reliability weighting from day one

Implement all available sources (R3 + time-based survival + R5 selection) with
weighted confidence aggregation. Rejected: over-engineered for current state.
R3 is sufficient and available in the same cycle. Other sources can be added
incrementally without changing the core training flow.

### Option C: Deferred training with time-based survival only

Wait for events to survive 30+ days, then use survival as grounding signal.
Rejected: requires historical query infrastructure, delays training by 30 days,
and LOW reliability means slow convergence.

## Consequences

### Positive
- Same-cycle grounding: no historical queries needed
- Simple implementation: R3 reconciliation is already in P03EventState
- Extensible: future sources plug in without changing training flow
- Immediate feedback: weight learning begins from first P03 cycle with R3 data

### Negative
- R3 reconciliation is a MEDIUM-HIGH signal, not ground truth from user actions
- Events in first P03 cycle have no prior truth records, so CREATE dominates
- Convergence may be slower than with HIGH-reliability signals

### Risks
- R3 may label events as grounded that users don't actually find important
- Mitigation: cold-start blending (alpha = sample_count/500) limits impact of
  early noisy labels; drift detection catches weight divergence

## Related

- ADR-K024: Weight learner component alignment (8 CONFIG_B components)
- Issue 5.W.2.2-5.W.2.6: Implementation issues for this ADR
- P03 Dossier Appendix C.2.1.2: Cold start strategy
