# ADR-0060: Adaptive KV-Cache Management

**Date:** 2025-10-15
**Status:** Proposed
**Tier:** 1
**Umbrella ADR**

## Context

The K1 Intelligence Module requires a highly adaptive key-value (KV) cache to support agentic orchestration, rapid context switching, and strict performance budgets. Static cache sizing and placement strategies are insufficient for dynamic workloads, thermal constraints, and multi-agent collaboration. The cache must respond to real-time signals, backpressure, and thermal placement, while supporting hot/cold eviction and rapid recovery.

## Decision

Implement an adaptive KV-cache management system with:
- Dynamic placement and sizing (see ADR-0060a)
- Hot/cold eviction and recovery (see ADR-0060b)
- Integration with thermal manager, backpressure cascade, and session state boundaries
- Real-time metrics, observability, and tracing
- Strict adherence to performance budgets (see Section 3, Copilot Rules)

## Consequences

- Enables real-time cache resizing and placement for optimal performance
- Supports agent migration, session handoff, and backpressure mitigation
- Reduces risk of cache thrashing and thermal overload
- Improves recovery from eviction events and supports rollback
- Increases system resilience and observability

## Implementation Details

- Reference: [k1_kv_cache_thermal.mmd](../../../../architecture_diagrams/k1_kv_cache_thermal.mmd)
- Dynamic placement: Agents and sessions are assigned cache regions based on thermal, workload, and backpressure signals
- Sizing: Cache size adapts to session state, agent count, and performance metrics
- Eviction: Hot/cold eviction policies, with recovery and rollback support
- Observability: Prometheus metrics, OpenTelemetry tracing, cognitive_trace_id propagation
- Configuration: All parameters in `k1/config/agent_fabric.yml` and `k1/config/sessionstate.yml`
- Security: Capability-based access, privacy band enforcement

## References
- ADR-0059: Learning Loop, K1 advisory/K0 persistence
- ADR-0057: Voice-Specific Backpressure
- ADR-0060a: Dynamic Placement & Sizing
- ADR-0060b: Hot/Cold Eviction & Recovery
- [k1_kv_cache_thermal.mmd](../../../../architecture_diagrams/k1_kv_cache_thermal.mmd)
- [k1_backpressure_cascade.mmd](../../../../architecture_diagrams/k1_backpressure_cascade.mmd)
- [k1_session_state_structure.mmd](../../../../architecture_diagrams/k1_session_state_structure.mmd)

---

**Sub-ADRs:**
- 0060a: Dynamic Placement & Sizing
- 0060b: Hot/Cold Eviction & Recovery

**Checklist:**
- [ ] 0060 umbrella ADR created
- [ ] 0060a sub-ADR created
- [ ] 0060b sub-ADR created
- [ ] Checklist updated
- [ ] Validated
