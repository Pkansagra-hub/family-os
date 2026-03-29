---
adr_id: FAB-006
title: "Agent Lifecycle in Fabric (Specializes ADR-0005)"
status: Accepted
date: 2026-02-06
module: fabric
layer: "L2"
authors: []
related_adrs:
  - "FAB-005"
  - "FAB-003"
  - "FAB-009"
related_events:
  - "k1.fabric.agent.spawned.v1"
  - "k1.fabric.agent.state_changed.v1"
  - "k1.fabric.agent.terminated.v1"
  - "k1.fabric.agent.pooled.v1"
related_contracts:
  - "k1/contracts/schemas/agent_contract.schema.json"
related_ports:
  - "IModelGatewayPort"
  - "ISessionStateReader"
implements_issue: "1.1.3"
superseded_by: ""
tags:
  - agent-lifecycle
  - agent-factory
  - fsm
  - pool
  - supervisor
---

# FAB-006: Agent Lifecycle in Fabric (Specializes ADR-0005)

## Context

### Problem Statement

ADR-0005 defines a 6-state FSM for ALL K1 agents (PENDING -> WARMING -> ACTIVE -> IDLE -> DRAINING -> TERMINATED). Fabric's Agent Factory (Role 3) creates agents dynamically from YAML templates. This ADR specifies how the legacy lifecycle model applies within the Fabric context and what Fabric-specific constraints exist.

### Legacy ADR-0005 Review Summary

ADR-0005 (2407 lines, ACCEPTED, 70% implemented) establishes:

- **6 states**: PENDING (roster registration), WARMING (model load, config, KV cache), ACTIVE (processing), IDLE (pooled for reuse), DRAINING (graceful shutdown), TERMINATED (cleanup)
- **Authority model**: Supervisor owns all transitions via monotonic clock. Agents publish intents, Supervisor decides.
- **Performance targets**: Cold start <=250ms laptop / <=500ms phone. Warm activation <50ms. Graceful shutdown <10s. Transition overhead <5ms.
- **Resource limits**: Max 3 agents per session. 60s idle TTL. 500MB total K1 memory. ~150MB per AI agent.
- **Crash recovery**: Max 3 crashes in 10 min -> blacklist 1 hour.
- **ADR-0005b (Idle Pooling)**: IDLE agents recycled for same-type requests.
- **ADR-0005c (Draining)**: Finish current task, flush state, release capabilities, terminate.
- **ADR-0005d (Supervisor Blacklist)**: Agents that crash repeatedly are excluded.

### What Fabric Changes

- **ADR-0005 assumed static 58-agent pool**. Fabric dynamically creates agents from YAML templates.
- **ADR-0005 assumed Orchestrator hires agents via Contract-Net**. Fabric's Agent Factory instantiates directly.
- **ADR-0005 assumed agents have persistent state**. Fabric agents are scoped to a plan step and stateless between invocations.
- **ADR-0005's Supervisor pattern remains valid** for health monitoring, crash recovery, and transition authority.

---

## Decision

### Chosen Approach

Fabric Agent Factory follows ADR-0005's 6-state FSM with these specializations:

### Fabric Agent Lifecycle

```
AgentFactory.spawn(contract, plan_step)
  -> PENDING (allocate ID, create lease, scope tools)
  -> WARMING (load prompt template, connect Model Gateway, acquire SessionState reader)
  -> ACTIVE (execute task with scoped LLM + tools)
  -> IDLE (available for pool reuse if same contract type)
  -> DRAINING (finish task, emit CapabilityResult, release resources)
  -> TERMINATED (cleanup, remove from roster)
```

### Fabric-Specific Specializations

| ADR-0005 Concept | Fabric Specialization |
|---|---|
| Agent ID | `{plan_id}/{step_id}/{agent_template_name}` |
| Agent Lease | tools_granted[] from CommittedPlan step, NOT full capability set |
| WARMING content | Load prompt template + compile variables + connect ModelGateway |
| ACTIVE behavior | Execute single task, emit deltas via DeltaBus (NOT write SessionState) |
| IDLE pool key | `{agent_template_name}:{tools_granted_hash}` |
| DRAINING trigger | Task complete OR timeout (max_execution_time_ms from contract) |
| Crash recovery | Fabric returns CapabilityResult.failure(), Orchestrator handles retry |

### Tool Scoping (FAB-07 Enforcement)

```python
class ScopedToolAccess:
    """Fabric Agent Factory enforces FAB-07."""

    def __init__(self, tools_granted: list[str], fabric: CapabilityFabric):
        self._allowed = frozenset(tools_granted)
        self._fabric = fabric

    async def invoke(self, capability_name: str, params: dict) -> CapabilityResult:
        if capability_name not in self._allowed:
            return CapabilityResult.failure(
                error=f"Tool '{capability_name}' not in tools_granted. "
                      f"Allowed: {sorted(self._allowed)}"
            )
        return await self._fabric.execute(CapabilityRequest(name=capability_name, params=params))
```

### Rationale

ADR-0005's FSM is sound and does not need replacement. Fabric only specializes:
1. **Dynamic creation** (from YAML templates vs static agent pool)
2. **Scoped tools** (per-step grant vs global capability set)
3. **Stateless result** (CapabilityResult vs persistent agent state)

The Supervisor pattern, crash recovery, idle pooling, and blacklisting all apply unchanged.

---

## Alternatives Considered

### Alternative 1: Simplified 3-state model (PENDING -> ACTIVE -> TERMINATED)

**Rejected because:**
- No WARMING state means cold-start latency spikes are invisible
- No IDLE state means no agent pool reuse (repeat cold starts)
- No DRAINING state means abrupt termination risks data loss

### Alternative 2: Fully custom Fabric lifecycle (ignore ADR-0005)

**Rejected because:**
- ADR-0005 is ACCEPTED and 70% implemented. Duplicating lifecycle logic creates divergence.
- Supervisor pattern is proven and handles crash recovery correctly.
- No functional gap in ADR-0005 that requires a new FSM.

---

## Consequences

### Positive

- Reuses proven 6-state FSM (no new lifecycle code needed)
- Pool reuse via IDLE state saves 200ms+ per repeated agent type
- Tool scoping enforces FAB-07 at the Agent Factory level
- Crash recovery handled by existing Supervisor pattern

### Negative

- Fabric agents have different scoping semantics than legacy static agents
- Pool key includes tools_granted hash, making pool hits less frequent

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Pool thrashing (too many unique tool combos) | Medium | Low | Monitor pool hit rate; consider relaxed matching |
| WARMING latency exceeds budget | Low | Medium | Pre-warm popular templates at startup |
| Max 3 agents limit too restrictive for complex plans | Medium | Medium | Configurable per-session; serialized step execution as fallback |

---

## Implementation

### Affected Code Paths

| Component | File | Change Type |
|-----------|------|-------------|
| AgentFactory | `k1/fabric/providers/agent_factory.py` | New |
| AgentPool | `k1/fabric/providers/agent_pool.py` | New |
| ScopedToolAccess | `k1/fabric/providers/scoped_tools.py` | New |
| AgentProvider | `k1/fabric/providers/agent_provider.py` | New |

### Events Emitted/Consumed

| Event Topic | Direction | Description |
|-------------|-----------|-------------|
| `k1.fabric.agent.spawned.v1` | Emitted | Agent entered PENDING |
| `k1.fabric.agent.state_changed.v1` | Emitted | Any FSM transition |
| `k1.fabric.agent.pooled.v1` | Emitted | Agent entered IDLE pool |
| `k1.fabric.agent.terminated.v1` | Emitted | Agent cleanup complete |

### Testing Strategy

- [ ] 6-state FSM transition tests (all valid/invalid transitions)
- [ ] Tool scoping tests (FAB-07: reject tools not in tools_granted)
- [ ] Pool reuse tests (same template + tools -> reuse IDLE agent)
- [ ] Crash recovery tests (3 crashes -> blacklist -> CapabilityResult.failure)
- [ ] Cold start latency tests (PENDING->ACTIVE <250ms)

---

## Amendment History

| Date | Author | Change |
|------|--------|--------|
| 2026-02-06 | - | Accepted: Fabric specialization of ADR-0005 lifecycle. |
