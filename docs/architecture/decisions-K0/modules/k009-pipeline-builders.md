---
adr_number: 'K009'
affected_modules: ['M13', 'M14']
title: Pipeline Builders Architecture - Row Assembly and Queue Management
status: PROPOSED
date_created: '2025-11-16'
---

# K009: Pipeline Builders Architecture

**Status**: PROPOSED | **Modules**: M13-M14

## Context

Builder modules consolidate enrichment outputs into database rows.

## Current Modules

### M13: HippEventsRowBuilder
- Assembles st_hipp_events row from all enrichment modules
- Handles NULL for CA3 outputs (populated by P03)
- JSON serialization for flexible structures

### M14: EmbeddingQueueWriter
- Creates st_embedding_queue entries for P08
- Tracks attempt count and status
- Links to wal_pos and event_id

## Future Capabilities

- Batch optimization (vectorized row building)
- Streaming row assembly (reduce memory footprint)
- Schema evolution support (handle missing/new columns gracefully)
- Compression for large JSON fields

## Sub-ADRs

- [K009.1: HippEvents Row Builder](k009.1-hipp-events-builder.md)
- [K009.2: Embedding Queue Writer](k009.2-embedding-queue-writer.md)
- [K009.3: Batch Optimization](k009.3-batch-optimization.md)

## Performance Budget

- M13 P95: ≤5ms | M14 P95: ≤2ms | Memory: <20MB total

---
**Last Updated**: 2025-11-16
