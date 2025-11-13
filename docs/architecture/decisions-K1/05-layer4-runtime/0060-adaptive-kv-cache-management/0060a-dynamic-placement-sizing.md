---
adr_number: '0060a'
title: Dynamic Placement & Sizing (KV-Cache)
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer2_orchestration
- layer3_execution
- layer4_runtime
affected_modules:
- k1.l4_runtime.cache_placer
- k1.l2_orchestration.resource_allocator
- k1.l4_runtime.thermal_manager
concerns:
- architecture
- observability
- performance
- privacy
- scalability
- testing
implementation_status: PLANNED
implementation_phase: Phase 4 (Performance Optimization)
related_adrs:
- ADR-0059
- ADR-0060
related_contracts:
- k1/contracts/flatbuffers/layer3_execution/model_cache_entry.fbs
- k1/contracts/flatbuffers/layer3_execution/model_request.fbs
- k1/contracts/flatbuffers/layer3_execution/model_response.fbs
research_citations:
- 'Dynamic Memory Allocation (Wilson et al., 1995)'
- 'Cache Partitioning Strategies (Qureshi & Patt, 2006)'
- 'Thermal-Aware Resource Management (Zanini et al., 2009)'
---


# ADR-0060a: Dynamic Placement & Sizing (KV-Cache)

**Date:** 2025-10-15
**Status:** Proposed
**Tier:** 1
**Sub-ADR to ADR-0060**

## Context

Static cache allocation leads to resource contention, thermal overload, and suboptimal agent performance. The K1 kernel must dynamically assign cache regions and size them based on session state, agent count, thermal signals, and backpressure. This enables real-time adaptation to workload spikes, agent migration, and session handoff.

## Decision

Implement dynamic placement and sizing for KV-cache:
- Cache regions assigned per agent/session based on thermal, workload, and backpressure signals
- Sizing adapts to session state, agent count, and performance metrics
- Placement integrates with thermal manager and backpressure cascade
- Configuration via `k1/config/agent_fabric.yml` and `k1/config/sessionstate.yml`

## Consequences

- Reduces risk of cache thrashing and thermal overload
- Enables agent migration and session handoff
- Improves cache hit rate and performance
- Supports real-time backpressure mitigation

## Implementation Details

- Reference: [k1_kv_cache_thermal.mmd](../../../../architecture_diagrams/k1_kv_cache_thermal.mmd)
- Placement algorithm: Assign cache region based on agent thermal score, session workload, and backpressure signals
- Sizing algorithm: Adjust cache size per session/agent using Prometheus metrics and session state boundaries
- Integration: Thermal manager emits signals to orchestrator, which triggers cache resizing and migration
- Observability: Prometheus metrics for cache region usage, hit/miss rate, thermal events
- Tracing: OpenTelemetry spans for cache migration, resizing, and agent handoff

### Pseudocode Example
```python
# Dynamic placement and sizing
for agent in active_agents:
    thermal_score = thermal_manager.get_score(agent)
    workload = session_state.get_workload(agent.session)
    backpressure = backpressure_cascade.get_signal(agent)
    cache_region = assign_cache_region(thermal_score, workload, backpressure)
    cache_size = adjust_cache_size(agent.session, workload, thermal_score)
    kv_cache.set_region(agent.id, cache_region, cache_size)
```

## References
- ADR-0060: Adaptive KV-Cache Management
- ADR-0059: Learning Loop, K1 advisory/K0 persistence
- [k1_kv_cache_thermal.mmd](../../../../architecture_diagrams/k1_kv_cache_thermal.mmd)
- [k1_backpressure_cascade.mmd](../../../../architecture_diagrams/k1_backpressure_cascade.mmd)

---

**Checklist:**
- [ ] Placement algorithm defined
- [ ] Sizing algorithm defined
- [ ] Integration with thermal manager
- [ ] Observability and tracing added
- [ ] Validated
