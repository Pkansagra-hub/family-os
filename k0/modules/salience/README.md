# Salience Module | Version: 0.1.0 | ADR: K006
## Purpose: Attention prioritization for episodic memories

## Configuration (`config.yml`)
```yaml
write_path:
  formula:
    social_weight: 0.50
    affect_weight: 0.40
    recency_weight: 0.10
social_importance:
  SPOUSE: 1.0
  PARENT: 0.9
```

## Usage
```python
from k0.modules.salience import SalienceScorer
scorer = SalienceScorer()
score = await scorer.compute_salience(
    participant_roles={"person_mom": "SPOUSE"},
    affect_valence=0.8,
    affect_arousal=0.4,
    event_time_utc="2025-11-10T18:00:00Z",
)
print(score.score, score.band)  # 0.72, SalienceBand.HIGH
```

## Performance: P95 ≤5ms | P99 ≤10ms
## Related: P02, P03, ADR K006 Series
