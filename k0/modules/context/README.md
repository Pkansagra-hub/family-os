# Context Module | Version: 0.1.0 | ADR: K007
## Purpose: Metadata enrichment (temporal, device, ingress, retention, geo)

## Modules (M08-M12)
- **TemporalProfiler** (M08): Time-of-day, circadian, backdating
- **DeviceProfiler** (M09): Device context & primary detection
- **IngressClassifier** (M10): Channel & source classification
- **RetentionLookup** (M11): Lifecycle policy resolution
- **GeoMetadataLookup** (M12): Location metadata & masking

## Configuration (`config.yml`)
```yaml
temporal:
  timezone_source: "tenant_config"
  backdating_threshold_hours: 24
  buckets:
    morning: [6, 12]
device:
  cache_ttl_seconds: 600
retention:
  cache_ttl_seconds: 3600
```

## Usage
```python
from k0.modules.context import TemporalProfiler, DeviceProfiler

temporal = TemporalProfiler()
profile = await temporal.profile(event_time, ingested_at, tenant_tz)

device = DeviceProfiler()
device_info = await device.profile(device_id, actor_id)
```

## Performance: All modules P95 ≤5ms
## Related: P02, ADR K007 Series
