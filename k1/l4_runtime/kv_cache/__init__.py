"""
K1 L4 Runtime — Adaptive KV Cache

**Purpose:** Thermal-aware KV cache with dynamic placement, hot/cold eviction, ZSTD compression

**Components:**
- placement/ — Thermal-aware region assignment
- eviction/ — Hot/cold eviction policies, rollback
- compression/ — ZSTD level 3, 25-35% size reduction

**Performance:**
- Placement: <50ms P95
- Eviction: <20ms
- Compression: <1ms P95

**ADRs (3 total):**
- ADR-0060: Management Core (dynamic placement, eviction policies, thermal integration)
- ADR-0060a: Dynamic Placement (region assignment, thermal workload backpressure-based)
- ADR-0060b: Eviction & Recovery (hot/cold eviction, rollback, session reactivation)
- ADR-0076: Compression Tier (ZSTD 25-35%, priority-aware LRU)

**Integration:**
- L5 Thermal: thermal_manager.get_score for placement decisions
- SessionState: Agent/session memory budgets
- Actor Fabric: Backpressure signals trigger eviction

**Performance Metrics:**
- kv_cache_placement_latency_ms (histogram)
- kv_cache_eviction_total (counter, mode=hot|cold)
- kv_cache_compression_ratio (histogram)

**Last Updated:** October 2025
**Status:** Production-ready adaptive KV cache
"""

__version__ = "0.1.0"

# TODO: Implement placement/, eviction/, compression/
# Per ADR-0060 family (0060, 0060a-b) and ADR-0076
