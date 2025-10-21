# ADR-0060b: Hot/Cold Eviction & Recovery (KV-Cache)

**Date:** 2025-10-15
**Status:** Proposed
**Tier:** 1
**Sub-ADR to ADR-0060**

## Context

Cache thrashing, thermal overload, and session migration require robust eviction and recovery mechanisms. Hot/cold eviction policies must balance performance, resilience, and recovery speed. Recovery must support rollback, agent migration, and session handoff, integrating with the backpressure cascade and session state boundaries.

## Decision

Implement hot/cold eviction and recovery for KV-cache:
- Hot eviction: Immediate removal of cache regions under thermal or backpressure stress
- Cold eviction: Gradual removal based on session inactivity, agent migration, or memory pressure
- Recovery: Rapid restoration of evicted cache regions, with rollback and migration support
- Integration with backpressure cascade and session state boundaries
- Observability and tracing for eviction/recovery events

## Consequences

- Reduces risk of cache thrashing and thermal overload
- Enables rapid recovery from eviction events
- Supports agent migration and session handoff
- Improves system resilience and performance

## Implementation Details

- Reference: [k1_kv_cache_thermal.mmd](../../../../architecture_diagrams/k1_kv_cache_thermal.mmd)
- Hot eviction: Triggered by thermal manager or backpressure cascade; cache region is immediately removed, agent is migrated or session is handed off
- Cold eviction: Triggered by inactivity, migration, or memory pressure; cache region is gradually removed, with state persisted to K0
- Recovery: On agent/session reactivation, cache region is restored from K0, with rollback if needed
- Observability: Prometheus metrics for eviction/recovery events, OpenTelemetry tracing
- Security: Capability-based access, privacy band enforcement

### Pseudocode Example
```python
# Hot/cold eviction and recovery
for region in kv_cache.regions:
    if thermal_manager.is_overloaded(region) or backpressure_cascade.is_stressed(region):
        kv_cache.evict(region, mode="hot")
        migrate_agent_or_session(region)
    elif kv_cache.is_inactive(region) or memory_manager.is_pressure(region):
        kv_cache.evict(region, mode="cold")
        persist_state_to_k0(region)

# Recovery
for region in evicted_regions:
    if agent_or_session_reactivated(region):
        kv_cache.restore(region)
        rollback_if_needed(region)
```

## References
- ADR-0060: Adaptive KV-Cache Management
- ADR-0059: Learning Loop, K1 advisory/K0 persistence
- [k1_kv_cache_thermal.mmd](../../../../architecture_diagrams/k1_kv_cache_thermal.mmd)
- [k1_backpressure_cascade.mmd](../../../../architecture_diagrams/k1_backpressure_cascade.mmd)
- [k1_session_state_structure.mmd](../../../../architecture_diagrams/k1_session_state_structure.mmd)

---

**Checklist:**
- [ ] Hot eviction policy defined
- [ ] Cold eviction policy defined
- [ ] Recovery mechanism defined
- [ ] Integration with backpressure/session state
- [ ] Observability and tracing added
- [ ] Validated
