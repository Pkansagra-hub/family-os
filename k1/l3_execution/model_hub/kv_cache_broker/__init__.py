"""
K1 Layer 3 Execution — model_hub/kv_cache_broker/

PURPOSE:
========
Global KV cache management (512MB budget) with <2ms allocation.
Implements hybrid eviction (60% LRU + 40% LFU) with cache warming and compression.

RESPONSIBILITIES:
=================
1. Global Allocator: 512MB device-wide budget, per-session min 32MB, max 256MB
2. Hybrid Eviction: 60% recency weight + 40% frequency weight, >75% hit rate target
3. Cache Warming: Resume detection, prefetch last 3 turns (<50ms), async background
4. Compression: zstd level 3 (70% reduction), compress inactive >10 min, decompress <20ms
5. Protection: Never evict active turn, low priority (recently used), normal (inactive 5-30 min), high priority (inactive >30 min)

PRIMARY ADRs:
=============
- ADR-0025: KV Cache Management (global allocator, hybrid eviction)
- ADR-0025a: Global Allocator (512MB device-wide budget)
- ADR-0025b: Hybrid Eviction (60% LRU + 40% LFU)
- ADR-0025c: Cache Warming (prefetch last 3 turns)
- ADR-0025d: Compression (zstd level 3, 70% reduction)
- ADR-0025e: Protection (never evict active turn)

RELATED ADRs:
=============
- ADR-0024: Performance Budgets (cache <2ms allocation)
- ADR-0029: Prometheus Metrics (hit rate >75%, eviction rate)

PERFORMANCE METRICS:
====================
- Allocation: <2ms P95
- Eviction decision: <5ms
- Hit rate: >75% target
- Miss penalty: 100-200ms (80-90% slower)
- Compression: <15ms (70% size reduction)
- Decompression: <20ms

AUTHOR: K1 Intelligence Module
VERSION: 1.0.0
LAST UPDATED: October 2025
"""
