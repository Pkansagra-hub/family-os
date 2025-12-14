# Builders Module | Version: 0.1.0 | ADR: K009
## Purpose: Row assembly and queue management for P02 writes

## Modules (M13-M14)
- **HippEventsRowBuilder** (M13): Consolidates enrichments → st_hipp_events row (65+ columns)
- **EmbeddingQueueWriter** (M14): Creates st_embedding_queue entries for P08

## Configuration (`config.yml`)
```yaml
hipp_events_builder:
  schema_version: "0.1.0"
  null_handling: "explicit"
  target_p95_ms: 5

embedding_queue_writer:
  default_priority: "NORMAL"
  default_max_attempts: 5
  model_id: "embed-mini-001"
  target_p95_ms: 2
```

## Usage
```python
from k0.modules.builders import HippEventsRowBuilder, EmbeddingQueueWriter

# Build st_hipp_events row
builder = HippEventsRowBuilder()
row = await builder.build(
    envelope=envelope,
    dg_fingerprint=dg_result,
    ca1_projection=ca1_result,
    affect=affect_result,
    space=space_result,
    temporal=temporal_result,
    device=device_result,
    social=social_result,
    retention=retention_result,
    salience=salience_result,
)

# Enqueue embedding job
queue_writer = EmbeddingQueueWriter()
queue_row = await queue_writer.enqueue(
    wal_pos=12345,
    event_id="evt_abc123",
    embedding_id="emb_xyz789",
    tenant_id="family-smith",
    space_id="personal:dad",
)
```

## Performance
- HippEventsRowBuilder: P95 ≤5ms
- EmbeddingQueueWriter: P95 ≤2ms

## Related: P02, st_hipp_events, st_embedding_queue, ADR K009 Series
