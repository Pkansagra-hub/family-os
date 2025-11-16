# Affect Module

**Version**: 0.1.0
**Status**: Planning (Step 3 - Module List Frozen)
**ADR**: [K004](../../../docs/architecture/decisions-K0/modules/k004-affect-service.md)

## Purpose

Emotional classification system for episodic memories using fast tier-0 affect models.

## Configuration

**`config.yml`** - All tunable parameters externalized:

```yaml
tier0:
  model_path: "${AFFECT_MODEL_PATH}"
  valence:
    range: [-1.0, 1.0]
    neutral_threshold: 0.1
  arousal:
    range: [0.0, 1.0]
    high_threshold: 0.7
  performance:
    target_p95_ms: 70
    batch_size: 16

emotions:
  tags:
    - joy, contentment, sadness, anger, fear, surprise, disgust, anticipation
  confidence_threshold: 0.3

bands:
  GREEN:  # Low emotional intensity
    valence_range: [-0.3, 0.3]
    arousal_range: [0.0, 0.4]
  AMBER:  # Moderate
    valence_range: [-0.7, 0.7]
  RED:    # High emotional intensity
    arousal_range: [0.7, 1.0]
```

## Usage

```python
from k0.modules.affect import AffectService, AffectConfig

affect = AffectService()
annotation = await affect.classify_text(
    text="We had dinner at Olive Garden with Mom and it was great",
    context={"person_id": "person_dad", "space_id": "personal:dad"},
)

print(f"Valence: {annotation.valence}")  # 0.8 (positive)
print(f"Arousal: {annotation.arousal}")  # 0.4 (moderate)
print(f"Tags: {annotation.tags}")        # ["joy", "contentment"]
print(f"Band: {annotation.band}")        # AffectBand.GREEN
```

## Extensibility

### Multi-Modal Affect (Future)

```yaml
features:
  multimodal_affect: true

multimodal:
  image_affect:
    enabled: true
    model: "clip-affect-v1"
  audio_affect:
    enabled: true
    model: "wav2vec-emotion"
```

```python
# Future API
annotation = await affect.classify_multimodal(
    text="Dinner was amazing!",
    image_data=image_bytes,
    audio_data=audio_bytes,
)
```

### Personalized Models (Future)

```yaml
features:
  personalized_models: true

personalization:
  baseline_window_days: 30
  min_samples: 100
```

```python
# Future API
baseline = await affect.get_personalized_baseline(person_id="person_dad")
annotation = await affect.classify_text(text, baseline=baseline)
```

## Performance Budget

| Metric | Target | Notes |
|--------|--------|-------|
| P95 Latency | ≤70ms | Tier-0 fast path |
| P99 Latency | ≤100ms | |
| Memory | <20MB | Per inference |
| Batch Size | 16 events | Optimized for throughput |

## Testing

```bash
pytest tests/k0/modules/affect/ -v --benchmark
```

## Dependencies

- Optional: HuggingFace Transformers
- Optional: ONNX Runtime (for optimized inference)

## Version History

- **0.1.0** (2025-11-16): Initial module structure

## Related

- **Pipeline**: P02 (Episodic Write), P06 (Learning)
- **ADR**: [K004 Series](../../../docs/architecture/decisions-K0/modules/README.md#affect-module-emotional-classification)
