# Runbook: Fabric - Capability Execution

**Module**: `k1/fabric`
**Owner**: K1 Kernel Team
**Priority**: P0 (CRITICAL) - Core capability execution fabric
**Alert Configuration**: `k1/fabric/alerts.yaml`
**Policy Contract**: `k1/contracts/modules/fabric/policies.contract.yaml`

---

## Overview

Capability Fabric is the execution backbone for tool, agent, workflow, and concierge capabilities. It performs provider resolution, policy checks, context building, execution with circuit breakers, output validation, and event emission.

### Architecture Summary

| Phase | Component | Key Metric |
|-------|-----------|------------|
| Resolve | Resolver + PolicyEngine | `fabric_policy_evaluation_duration_seconds` |
| Context | ContextBuilder | `fabric_context_build_duration_seconds` |
| Execute | Providers + CircuitBreaker | `fabric_execution_duration_seconds` |
| Retrieve | RetrievalEngine | `fabric_retrieval_duration_seconds` |

---

## Quick Reference

### Key Metrics

```promql
# Execution latency P95
histogram_quantile(0.95, rate(fabric_execution_duration_seconds_bucket[5m]))

# Retrieval latency P95
histogram_quantile(0.95, rate(fabric_retrieval_duration_seconds_bucket[5m]))

# Circuit breaker OPEN count
sum(fabric_circuit_breaker_state{state="OPEN"})

# Registry size by capability type
fabric_registry_size

# Agent pool sizes
fabric_agent_pool_size
```

### Common Investigation Commands

```bash
# Check Fabric metrics
curl http://localhost:9090/metrics | grep "fabric_"

# View recent Fabric logs
kubectl logs -l app=k1-kernel --since=10m | grep -E "fabric\."
```

---

## 2. Alert Response Procedures

### 2.1 FabricHighLatency

**Alert**: `FabricHighLatency`
**Severity**: Warning
**Threshold**: Execution latency P95 > 200ms for 5 minutes

#### Symptoms

- Increased request latency for capability execution
- Spike in `fabric_execution_duration_seconds` P95
- Possible queueing or slow provider execution

#### Investigation Steps

```bash
# Check execution P95
curl http://localhost:9090/metrics | grep fabric_execution_duration_seconds_bucket

# Check active executions
curl http://localhost:9090/metrics | grep fabric_active_executions

# Inspect recent Fabric logs
kubectl logs -l app=k1-kernel --since=10m | grep "fabric.execute"
```

#### Mitigation Steps

1. Identify slow providers and check their health.
2. Check for elevated circuit breaker activity.
3. Reduce concurrent load or temporarily disable degraded providers.
4. Verify context build and policy evaluation latency are within targets.

#### Verification

- P95 execution latency returns below 200ms
- `fabric_active_executions` returns to expected baseline

---

### 2.2 FabricCircuitBreakerOpen

**Alert**: `FabricCircuitBreakerOpen`
**Severity**: Critical
**Threshold**: Any circuit breaker OPEN for >2 minutes

#### Symptoms

- Requests to one or more providers are rejected
- `fabric_circuit_breaker_state{state="OPEN"}` is 1

#### Investigation Steps

```bash
# Identify open breakers
curl http://localhost:9090/metrics | grep fabric_circuit_breaker_state | grep OPEN

# Check provider health logs
kubectl logs -l app=k1-kernel --since=10m | grep "CB:"
```

#### Mitigation Steps

1. Determine which provider is failing and why.
2. If provider is external, validate connectivity and timeouts.
3. If provider is internal, check recent deployments or config changes.
4. Consider temporarily removing the provider from registry if unstable.

#### Verification

- Circuit breaker returns to CLOSED state
- Provider health checks succeed

---

### 2.3 FabricRetrievalSlow

**Alert**: `FabricRetrievalSlow`
**Severity**: Warning
**Threshold**: Retrieval latency P95 > 100ms for 5 minutes

#### Symptoms

- Planner discovery requests are slow
- `fabric_retrieval_duration_seconds` P95 elevated

#### Investigation Steps

```bash
# Check retrieval P95
curl http://localhost:9090/metrics | grep fabric_retrieval_duration_seconds_bucket

# Check registry size (large registries can impact retrieval)
curl http://localhost:9090/metrics | grep fabric_registry_size
```

#### Mitigation Steps

1. Verify embedding index health and capacity.
2. Check for large spikes in registry size.
3. Inspect retrieval logs for slow queries or errors.
4. Consider reducing top_k or filtering domains to narrow search.

#### Verification

- Retrieval P95 returns below 100ms

---

### 2.4 FabricAgentPoolExhausted

**Alert**: `FabricAgentPoolExhausted`
**Severity**: Warning
**Threshold**: Agent pool size 0 for any contract for 5 minutes

#### Symptoms

- Increased agent spawn latency
- `fabric_agent_pool_size` shows 0 for one or more contracts

#### Investigation Steps

```bash
# Check pool sizes
curl http://localhost:9090/metrics | grep fabric_agent_pool_size

# Check agent spawn rate
curl http://localhost:9090/metrics | grep fabric_agent_spawns_total
```

#### Mitigation Steps

1. Validate agent pool configuration (max_pool_size, idle_ttl).
2. Check if agent contracts are being evicted unexpectedly.
3. Increase pool size for high-traffic agents if needed.
4. Check model gateway capacity for agent warmups.

#### Verification

- Agent pool size returns above 0 for affected contracts

---

### 2.5 FabricRegistryEmpty

**Alert**: `FabricRegistryEmpty`
**Severity**: Critical
**Threshold**: Any capability type has zero registrations for 5 minutes

#### Symptoms

- Capability lookups fail for an entire capability type
- `fabric_registry_size` shows 0 for at least one type

#### Investigation Steps

```bash
# Check registry size by type
curl http://localhost:9090/metrics | grep fabric_registry_size

# Review ModuleLoader logs
kubectl logs -l app=k1-kernel --since=10m | grep "module_loader"
```

#### Mitigation Steps

1. Verify contract directories and YAML files are present.
2. Trigger registry reload if necessary.
3. Check for validation failures in ModuleLoader logs.
4. Restore contracts from version control if missing.

#### Verification

- Registry size returns above 0 for all capability types
- Capability lookups succeed for each type

---

## 3. Preventive Measures

### 3.1 Capacity and Performance

- Monitor execution P95 against 200ms alert threshold.
- Keep registry size growth in check via pruning or archiving unused contracts.
- Regularly review provider timeout and circuit breaker settings.

### 3.2 Reliability

- Validate provider health check cadence is appropriate.
- Ensure ModuleLoader hot-reload is enabled in production.
- Review agent pool utilization weekly to size pools appropriately.

---

## 4. Related Documentation

### ADRs

- `k1/docs/adrs/FAB-005-fabric-architecture-supersedes-contract-net.md`
- `k1/docs/adrs/FAB-009-performance-scheduling-in-fabric.md`

### Contracts

- `k1/contracts/modules/fabric/policies.contract.yaml`
- `k1/contracts/modules/fabric/module.contract.yaml`

### Implementation

- `docs/plans/k1/fabric-implementation-plan.md`
- `k1/fabric/`
- `k1/fabric/alerts.yaml`

### Dashboards

- `fabric-overview`
- `fabric-retrieval`
- `fabric-circuit-breakers`
- `fabric-registry`
- `fabric-agents`

---

## 5. Contact

- **On-Call Team**: k1-kernel-oncall@familyos.dev
- **Slack Channel**: #k1-fabric-alerts
- **Escalation**: See K1 Kernel escalation policy
