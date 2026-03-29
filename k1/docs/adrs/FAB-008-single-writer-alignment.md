---
adr_id: FAB-008
title: "Single-Writer Alignment (Enforces ADR-0017g)"
status: Accepted
date: 2026-02-06
module: fabric
layer: "L2"
authors: []
related_adrs:
  - "FAB-005"
  - "FAB-006"
related_events:
  - "k1.fabric.agent.fact_discovered.v1"
related_contracts:
  - "k1/contracts/schemas/events/sessionstate/mutation_requested.v1.json"
  - "k1/contracts/schemas/events/sessionstate/mutation_approved.v1.json"
related_ports:
  - "ISessionStateReader"
  - "IDeltaBusPublisher"
implements_issue: "1.1.5"
superseded_by: ""
tags:
  - single-writer
  - sessionstate
  - concurrency
  - delta-bus
  - invariant
---

# FAB-008: Single-Writer Alignment (Enforces ADR-0017g)

## Context

### Problem Statement

ADR-0017g establishes the Single-Writer Concurrency Pattern: Concierge is the SOLE writer to SessionState. All other components (sub-agents, dynamic agents, tools) are read-only or must request mutations via Delta Bus. Fabric is a major new subsystem that must be verified to have ZERO write paths to SessionState.

### Legacy ADR-0017g Review Summary

ADR-0017g (610 lines, ACCEPTED, PLANNING) establishes:

- **Concierge is sole writer**: All mutations go through Concierge
- **MutationGuard validates all writes**: Checks writer_id, section locks, size limits
- **Access control matrix**:
  - Concierge: Full read + Full write (via MutationGuard)
  - Sub-Agent: Snapshot read + No write + Mutation request via Delta Bus
  - Dynamic Agent: Scoped read + No write + Mutation request via Delta Bus
  - Tool: No read + No write
  - External: No read + No write
- **Delta Bus**: Channel for sub-agent mutation requests (`sessionstate.mutation.requested.v1`)
- **MutationGuard rejection reasons**: NOT_WRITER, SECTION_LOCKED, SIZE_EXCEEDED, NEVER_EVICT_VIOLATION, INVALID_OPERATION, PREFLIGHT_FAILED

### fabric_discussion.md Invariant FAB-01

> "Fabric NEVER writes SessionState. It reads beliefs/scoreboard for resolution context. Any fact discovered by a sub-agent flows through the Delta Bus to Concierge for approval."

This is Fabric Invariant #1 (FAB-01) from Section 5 of fabric_discussion.md.

---

## Decision

### Chosen Approach: Fabric is Strictly Read-Only + Delta Bus Publisher

Fabric enforces ADR-0017g by design:

1. **No SessionState write port exists in Fabric's port set** (FAB-005 defines 5 ports; none include `ISessionStateWriter`)
2. **Fabric receives `ISessionStateReader` only** — injected as a constructor dependency
3. **Agents spawned by Agent Factory inherit read-only access** (per ADR-0017g: Dynamic Agents get "Scoped read + No write")
4. **Facts discovered by Fabric-spawned agents are published to Delta Bus** — Concierge approves or rejects

### Enforcement Points

| Fabric Component | SessionState Access | Write Path? | Enforcement |
|---|---|---|---|
| FabricFacade (entry point) | `ISessionStateReader` | NO | Constructor accepts reader port only |
| SemanticIndex (Retrieval) | None | NO | No SessionState dependency |
| ProviderSelector (Resolution) | `ISessionStateReader` (reads beliefs for context) | NO | Reader port only |
| PolicyGuard (Resolution) | `ISessionStateReader` (reads control for policy) | NO | Reader port only |
| ExecutionEngine | None | NO | Delegates to Agent Factory |
| Agent Factory | `ISessionStateReader` (passes to spawned agents) | NO | Passes reader, not writer |
| Spawned Agents | `ISessionStateReader` (scoped snapshot) | NO | MutationGuard rejects if agent tries to write |

### Delta Bus Integration for Agent Fact Discovery

```python
class FabricAgentRuntime:
    """Runtime context for agents spawned by Fabric Agent Factory."""

    def __init__(
        self,
        session_reader: ISessionStateReader,
        delta_bus: IDeltaBusPublisher,
        scoped_tools: ScopedToolAccess,
    ):
        self._session_reader = session_reader
        self._delta_bus = delta_bus
        self._tools = scoped_tools

    async def discover_fact(self, section: str, fact: dict) -> None:
        """Agent discovered a fact. Publish to Delta Bus for Concierge approval."""
        await self._delta_bus.publish(
            topic="sessionstate.mutation.requested.v1",
            payload={
                "requester_id": self._agent_id,
                "section": section,
                "operation": "add_fact",
                "payload": fact,
                "estimated_size_bytes": len(str(fact).encode()),
                "source": "fabric_agent",
            }
        )
        # Agent does NOT wait for approval. Fire-and-forget.
        # Concierge processes mutation requests asynchronously.
```

### Compile-Time Guarantee

Fabric's module contract (`fabric.module.yaml`) will NOT list `ISessionStateWriter` in its `requires` section. This means:

- The dependency injection container will never inject a writer
- Any code attempting to import `ISessionStateWriter` inside `k1/fabric/` will fail contract validation
- The governance scanner will flag violations

### Rationale

ADR-0017g is clear: only Concierge writes. Fabric as a read-only subsystem is the simplest and safest alignment. Adding any write path would:
1. Violate FAB-01 invariant
2. Require MutationGuard integration (complexity for no benefit)
3. Create a second writer (breaking single-writer guarantee)
4. Need Concierge coordination for every write (same as Delta Bus, but harder)

---

## Alternatives Considered

### Alternative 1: Fabric writes directly via MutationGuard

**Rejected because:**
- Violates ADR-0017g's "Concierge is sole writer" principle
- MutationGuard checks `writer_id == concierge_id`; Fabric would be rejected
- Would require modifying MutationGuard to accept multiple writers (architectural regression)

### Alternative 2: Fabric proxies writes through Concierge API

**Rejected because:**
- Adds synchronous coupling between Fabric and Concierge
- Delta Bus already provides this pattern asynchronously
- No advantage over existing Delta Bus channel

---

## Consequences

### Positive

- Zero risk of SessionState corruption from Fabric
- No new concurrency issues introduced
- ADR-0017g remains intact without modifications
- Governance scanning can verify no `ISessionStateWriter` import in `k1/fabric/`

### Negative

- Fabric-spawned agents cannot persist facts synchronously (must wait for Concierge approval via Delta Bus)
- Slight delay between fact discovery and fact availability in SessionState

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Agent needs fact in SessionState before next step | Low | Medium | Agent uses local context; Concierge processes Delta Bus promptly |
| Delta Bus backlog delays fact persistence | Low | Low | Delta Bus is async; facts are eventually consistent |

---

## Implementation

### Affected Code Paths

| Component | File | Change Type |
|-----------|------|-------------|
| FabricFacade | `k1/fabric/facade.py` | Verify: accepts ISessionStateReader only |
| FabricAgentRuntime | `k1/fabric/providers/agent_runtime.py` | New: reader + Delta Bus publisher |
| Module contract | `k1/contracts/schemas/module/fabric.module.yaml` | Verify: no ISessionStateWriter in requires |

### Testing Strategy

- [ ] Negative test: Attempt to inject ISessionStateWriter into Fabric -> must fail
- [ ] Positive test: Fabric reads beliefs via ISessionStateReader -> succeeds
- [ ] Integration test: Spawned agent discovers fact -> Delta Bus publishes -> Concierge receives
- [ ] Governance scan: No ISessionStateWriter import in k1/fabric/**

---

## Amendment History

| Date | Author | Change |
|------|--------|--------|
| 2026-02-06 | - | Accepted: Fabric is read-only, Delta Bus for fact discovery. |
