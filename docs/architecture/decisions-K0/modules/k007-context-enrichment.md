---
adr_number: 'K007'
affected_modules: ['M08', 'M09', 'M10', 'M11', 'M12']
title: Context Enrichment Architecture - Metadata Profiling Subsystem
status: PROPOSED
date_created: '2025-11-16'
---

# K007: Context Enrichment Architecture

**Status**: PROPOSED | **Modules**: M08-M12

## Context

Context enrichment adds temporal, device, ingress, retention, and geo metadata to events.

## Current Modules

### M08: TemporalProfiler
- Time-of-day bucketing (morning/afternoon/evening/night)
- Circadian slot classification (wake/active/wind-down/sleep)
- Backdating detection (event_time vs write_time)
- Local timezone conversion

### M09: DeviceProfiler
- Device context (kind, OS, primary device flag)
- Multi-device correlation

### M10: IngressClassifier
- Channel classification (k1.conversation, k1.command, external)
- Source attribution

### M11: RetentionLookup
- Policy matrix lookup (band × topic × device_kind)
- Lifecycle bucket assignment

### M12: GeoMetadataLookup
- Geohash precision metadata
- Masking reason tracking (no re-masking)

## Future Capabilities

- Multi-modal context (image EXIF, audio metadata, video duration)
- Behavioral context (typing speed, interaction patterns)
- Environmental context (weather, ambient noise, lighting)

## Sub-ADRs

- [K007.1: Temporal Profiler](k007.1-temporal-profiler.md)
- [K007.2: Device Profiler](k007.2-device-profiler.md)
- [K007.3: Ingress Classifier](k007.3-ingress-classifier.md)
- [K007.4: Retention Lookup](k007.4-retention-lookup.md)
- [K007.5: Geo Metadata Lookup](k007.5-geo-metadata.md)
- [K007.6: Multi-Modal Context](k007.6-multimodal-context.md)

## Performance Budget

- All modules: P95 ≤5ms | Total context: <25MB

---
**Last Updated**: 2025-11-16
