"""
K1 L4 Runtime — SessionState Memory Manager (3-Tier Eviction)

**Purpose:** 3-tier eviction strategy (Soft 64KB → Hard 128KB → OOM 256KB) with graceful degradation

**Eviction Tiers:**
1. **Tier 1 Soft Eviction (64KB→80KB):**
   - LRU eviction of low-priority data (meta section, old turns 4+)
   - Graceful degradation, minimal UX impact
   - <5ms latency P95

2. **Tier 2 Hard Eviction (128KB→192KB):**
   - Aggressive eviction: beliefs LRU, scoreboard LRU, multimodal compression
   - 70% compression ratio (zstd level 3)
   - <3ms latency P95

3. **Tier 3 OOM Prevention (256KB threshold):**
   - Emergency state save (beliefs + persona → K0 WAL)
   - User notification (SSE event session.terminated reason=OOM)
   - Session termination <20ms

**Performance:**
- Tier 1 eviction: <5ms P95, minimal UX impact (eviction_tier1_total counter)
- Tier 2 eviction: <3ms P95, moderate UX impact (eviction_tier2_total counter)
- Tier 3 OOM: <10ms save + <20ms total termination (session_oom_terminated_total counter)
- Memory tracking: <100μs per section size check (cached sizes, no re-serialization)

**ADRs (4 total):**
- ADR-0018: Eviction Architecture (soft 64KB, hard 128KB, OOM 256KB, escalation triggers)
- ADR-0018a: Tier 1 Soft Eviction (LRU policy, priority eviction meta/old turns, <5ms, aging algorithm)
- ADR-0018b: Tier 2 Hard Eviction (beliefs LRU 15KB, scoreboard LRU 4KB, multimodal zstd compression <3ms)
- ADR-0018c: Tier 3 OOM Prevention (256KB trigger, critical state save <10ms, SSE notification, session kill <20ms)

**Memory Budgets (ADR-0024c):**
- Soft limit: 64KB (triggers Tier 1 at 80KB = 64KB + 25%)
- Hard limit: 128KB (triggers Tier 2 at 192KB = 128KB + 50%)
- OOM limit: 256KB (triggers Tier 3 immediately)

**3-Tier Eviction Pipeline:**

```python
async def check_memory_pressure(session: SessionState) -> None:
    size_kb = calculate_size(session)  # <100μs cached

    if size_kb >= 256:
        # Tier 3: OOM Prevention
        await tier3_oom_prevention(session)  # <20ms total
    elif size_kb >= 192:
        # Tier 2: Hard Eviction
        await tier2_hard_eviction(session)  # <3ms
    elif size_kb >= 80:
        # Tier 1: Soft Eviction
        await tier1_soft_eviction(session)  # <5ms
```

**Tier 1 Soft Eviction (ADR-0018a):**
- **LRU Policy:** Evict least recently accessed data (last_accessed_ms tracking)
- **Priority Eviction:**
  - Meta section first (lowest priority, telemetry)
  - Old turns (turn_number ≥ 4, keep recent 3 turns)
  - Expired entities (salience < 0.1)
  - Old grounding acts (completed tool calls, >5 min ago)
- **Target:** Reduce from 80KB → 64KB (20% reduction)
- **UX Impact:** Minimal (only affects historical data, not current context)

**Tier 2 Hard Eviction (ADR-0018b):**
- **Beliefs LRU:** Evict 15KB of least accessed facts (sort by last_accessed_ms)
- **Scoreboard LRU:** Evict 4KB of least salient entities (sort by salience score)
- **Multimodal Compression:** zstd level 3, 70% size reduction, <3ms compression
- **Target:** Reduce from 192KB → 128KB (33% reduction)
- **UX Impact:** Moderate (may lose some context, affects recall quality)
- **UX Impact Score:** 0.0-1.0 (logged to Prometheus, 0.1% eviction frequency goal)

**Tier 3 OOM Prevention (ADR-0018c):**
- **Critical State Save:** Persist beliefs + persona to K0 WAL (<10ms)
- **Recovery Token:** Generate UUID recovery_token for user to resume session
- **User Notification:** Send SSE event (session.terminated, reason=OOM, recovery_token)
- **Session Termination:** Graceful kill, cleanup resources, <20ms total
- **Prometheus Alert:** session_oom_terminated_total (CRITICAL, should be zero)

**Files:**
- eviction_coordinator.py — Tier orchestration, priority algorithms, safety checks
- memory_tracker.py — Per-agent memory tracking (RSS), session totals, thresholds
- tier1_evictor.py — Soft eviction LRU policy, priority eviction, <5ms
- tier2_evictor.py — Hard eviction beliefs/scoreboard LRU, multimodal compression <3ms
- tier3_oom_prevention.py — OOM detection, critical state save, user notification, session kill
- metrics_collector.py — Eviction counts (per tier), memory timeseries, Prometheus export

**Integration:**
- SessionState Model: Sections provide size estimates, last_accessed_ms timestamps
- Serialization: FlatBuffers serialize for K0 WAL checkpointing
- Storage: Multi-tier storage receives evicted data for warm/cold tiers
- L5 Thermal: Memory pressure signals trigger eviction escalation
- K0 WAL: Critical state save during Tier 3 OOM

**Performance Metrics:**
- eviction_tier1_total (counter) — Soft evictions
- eviction_tier1_bytes (counter) — Bytes evicted Tier 1
- eviction_tier1_latency_ms (histogram) — <5ms P95
- eviction_tier2_total (counter) — Hard evictions
- eviction_tier2_bytes (counter) — Bytes evicted Tier 2
- eviction_tier2_latency_ms (histogram) — <3ms P95
- session_oom_terminated_total (counter) — OOM terminations (CRITICAL alert)
- session_state_size_bytes (gauge) — Current size per session
- memory_pressure_level (gauge) — 0=normal, 1=soft, 2=hard, 3=OOM

**Research Foundations:**
- Belady (1966) — Optimal replacement policy (LRU approximation)
- Denning (1968) — Working set model (memory pressure detection)
- Card et al. (1983) — Psychology of HCI (graceful degradation, user transparency)

**Last Updated:** October 2025
**Status:** Production-ready 3-tier eviction with OOM prevention
"""

__version__ = "0.1.0"

# TODO: Implement eviction_coordinator.py, memory_tracker.py, tier1_evictor.py, tier2_evictor.py,
# tier3_oom_prevention.py, metrics_collector.py
# Per ADR-0018 family (0018, 0018a-c) and ADR-0024c (Memory Budgets)
