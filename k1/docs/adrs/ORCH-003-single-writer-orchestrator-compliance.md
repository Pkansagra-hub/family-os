---
adr_id: ORCH-003
title: "Single Writer Compliance -- Orchestrator Never Writes SessionState"
status: Accepted
date: 2026-02-11
module: orchestrator
layer: "L2"
authors:
  - "K1 Architecture Team"
related_adrs:
  - "ORCH-001"
  - "ORCH-002"
  - "ORCH-004"
  - "FAB-008"
related_events:
  - "k1.orchestration.delta.v1"
  - "k1.hil.progress.v1"
related_contracts:
  - "k1/contracts/schemas/modules/orchestrator/module.contract.yaml"
  - "k1/contracts/schemas/modules/sessionstate/module.contract.yaml"
related_ports:
  - "IStateReadPort"
  - "IDeltaEmitPort"
implements_issue: "1.1.3"
superseded_by: ""
tags:
  - architecture
  - orchestrator
  - single-writer
  - sessionstate
  - invariant
  - ORCH-01
---

# ORCH-003: Single Writer Compliance -- Orchestrator Never Writes SessionState

## Context

### Problem Statement

ADR-0017 establishes the SessionState 6-Section Tiered Design, and ADR-0017g establishes the Single-Writer Concurrency Pattern: **Concierge is the sole writer to SessionState**. All other components -- including Orchestrator, Sub-Agents, and Dynamic Agents -- have read-only access and must submit mutation requests via the Delta Bus for Concierge to apply.

This ADR formally confirms ORCH-01 (Orchestrator NEVER writes SessionState) and defines the exact mechanisms by which the Orchestrator interacts with SessionState: what it reads, when it reads, and how it communicates state-impacting information without writing.

The Orchestrator touches SessionState in two ways:
1. **Reading** context snapshots for plan requests and safety band checks
2. **Emitting** progress deltas and orchestration outcomes that Concierge may use to mutate SessionState

Both must be carefully bounded to prevent accidental writes, stale reads, and mutation backdoors.

### Current Situation

ADR-0017g defines the access control matrix:

| Agent Type | Read Access | Write Access | Mutation Request |
|------------|-------------|--------------|------------------|
| Concierge | Full | Full (via MutationGuard) | N/A (is writer) |
| Sub-Agent | Snapshot | None | Via Delta Bus |
| Dynamic Agent | Scoped | None | Via Delta Bus |
| Tool | None | None | None |
| External | None | None | None |

The Orchestrator is none of these categories -- it's a Layer 2 kernel component, not an agent. Its access level must be explicitly defined.

FAB-008 (Single Writer Alignment) established the same pattern for Fabric: Fabric reads SessionState through `ISessionStateReader` Protocol, never writes. The Orchestrator follows the same pattern.

### Constraints

- Concierge is the sole writer (ADR-0017g -- architecture invariant)
- Orchestrator has no `IStateWritePort` -- port does not exist in its hexagonal architecture
- Delta Bus is fire-and-forget (no ACK, no guarantee of application)
- SessionState snapshots may become stale during long DAG executions (10-45s for HIGH tier)
- Safety band can change mid-execution (user's context shifts)

### Requirements

- ORCH-01: Orchestrator NEVER writes SessionState directly, via any mechanism
- Orchestrator reads via `IStateReadPort` (multi-reader, lock-free, read-only Protocol)
- Orchestrator emits all state-impacting information via `IDeltaEmitPort` (fire-and-forget)
- Safety band re-read at wave boundaries during HIGH-tier execution (defense against stale safety context)
- No IStateWritePort in Orchestrator's port set (compile-time enforcement via Protocol type)

---

## Decision

### Chosen Approach

**Orchestrator has read-only SessionState access via `IStateReadPort` and communicates all outcomes via `IDeltaEmitPort`. No write port exists. ORCH-01 is enforced at three levels: protocol type, port boundary, and test invariant.**

### Key Design

**1. IStateReadPort Protocol (Read-Only)**

```python
class IStateReadPort(Protocol):
    """Read-only access to SessionState.

    Orchestrator uses this for:
    - Context snapshots when building PlanRequests (HIGH tier)
    - Safety band checks at wave boundaries
    - No write methods exist on this Protocol
    """

    def read(self, section: str) -> SectionData: ...
    def snapshot(self, sections: list[str]) -> ContextSnapshot: ...
```

No `write()`, `mutate()`, `update()`, or `apply_delta()` methods exist. The Protocol is structurally impossible to use for writes.

**2. When Orchestrator Reads SessionState**

| Read Point | What | Why | Staleness Risk |
|------------|------|-----|----------------|
| TaskEnvelope dequeue | Full snapshot (beliefs, control, persona) | Build PlanRequest context for Planner | Low (fresh read at task start) |
| Wave boundary (HIGH) | control.safety_band only | Check if safety band changed mid-execution | Medium (5-15s between wave boundaries) |
| ConstraintResolver cycle | control.safety_band | Validate capability access against current band | Low (read per validation cycle, max 3) |

Orchestrator does NOT read SessionState during:
- Step execution (Fabric reads its own context via ISessionStateReader)
- Result aggregation (uses in-memory StepResult objects)
- Workflow scheduling (uses user timezone from WorkflowSpec, not live SessionState)

**3. How Orchestrator Emits Outcomes (No Writes)**

All Orchestrator outcomes that could affect SessionState are emitted as fire-and-forget deltas:

| Delta Type | Event | Content | Concierge Action |
|------------|-------|---------|-------------------|
| Progress | `k1.hil.progress.v1` | step_id, summary, progress_pct | Stream to user, update control.flow_state |
| DAG Complete | `k1.orchestration.dag.completed.v1` | AggregatedResult | Stage in TOOL_RESULT_BUFFER, trigger DELIVERING |
| HIL Request | `k1.orchestration.hil.request.v1` | question, context, fallback_id | Route to user, update control.pending_hil |
| Plan Timeout | `k1.orchestration.plan.timeout.v1` | request_id, degradation_path | Update control.tier_degradation_log |
| Constraint Progress | `k1.constraint.progress.v1` | cycle_num, issues, resolved | Observability only |

Concierge decides whether and how to apply these deltas to SessionState via MutationGuard. Orchestrator never knows if its deltas were applied.

**4. Three-Level ORCH-01 Enforcement**

| Level | Mechanism | Enforcement |
|-------|-----------|-------------|
| Protocol Type | `IStateReadPort` has no write methods | Compile-time (Python Protocol structural typing) |
| Port Boundary | No `IStateWritePort` in Orchestrator's 8-port set | Design-time (hexagonal architecture) |
| Test Invariant | Integration tests assert zero write calls on SessionState mock | Runtime (CI gate) |

```python
# tests/k1/orchestrator/invariants/test_orch_01_no_writes.py

class TestORCH01NoSessionStateWrites:
    """ORCH-01 invariant: Orchestrator NEVER writes SessionState."""

    def test_medium_tier_no_writes(self, orchestrator, mock_state):
        """MEDIUM tier execution emits no SessionState writes."""
        orchestrator.process(medium_envelope)
        assert mock_state.write_count == 0
        assert mock_state.mutate_count == 0

    def test_high_tier_no_writes(self, orchestrator, mock_state):
        """HIGH tier DAG execution emits no SessionState writes."""
        orchestrator.process(high_envelope_with_plan)
        assert mock_state.write_count == 0

    def test_workflow_no_writes(self, orchestrator, mock_state):
        """Workflow execution emits no SessionState writes."""
        orchestrator.process(workflow_run_request)
        assert mock_state.write_count == 0

    def test_no_write_port_exists(self):
        """Orchestrator has no IStateWritePort in its port set."""
        assert not hasattr(OrchestratorFactory, 'state_write_port')
        assert 'IStateWritePort' not in dir(orchestrator_ports)
```

**5. Safety Band Re-Read Strategy**

During HIGH-tier DAG execution (10-45s), the user's safety band may change. The Orchestrator re-reads `control.safety_band` at wave boundaries:

```
At each wave boundary:
  1. Re-read safety_band via IStateReadPort.read("control")
  2. Compare with plan's assumed safety band
  3. If band ESCALATED (GREEN -> AMBER -> RED -> CRISIS):
       - Check remaining steps against new band
       - Cancel steps that violate new band
       - Continue steps that are still allowed
  4. If band DE-ESCALATED:
       - No action (conservative: planned steps already validated for stricter band)
```

This is a READ operation, not a write. The safety band is set by Concierge (or Safety Agent) and read by Orchestrator.

### Rationale

1. **Single-writer eliminates race conditions.** With 6+ services potentially running concurrently (Orchestrator, Fabric, Agents, Planner), a single writer (Concierge) prevents lost updates, corrupted beliefs, and stale referents. ADR-0017g provides the theoretical foundation from Martin Thompson's Single-Writer Principle (2011).

2. **Delta Bus preserves loose coupling.** Orchestrator doesn't need to know HOW its outcomes affect SessionState. It emits deltas; Concierge applies them. This keeps Orchestrator's implementation completely independent of SessionState's internal structure.

3. **Protocol-level enforcement prevents accidents.** Developers cannot accidentally write SessionState from Orchestrator because the port interface has no write methods. This is enforced at compile time, not just by convention.

4. **Safety band re-read is the minimal necessary read.** Reading the full SessionState at every wave boundary would add latency. Reading only `control.safety_band` (a single field) is O(1) and adds <0.1ms per wave.

---

## Alternatives Considered

### Alternative 1: Grant Orchestrator Limited Write Access

**Description:** Allow Orchestrator to write a small subset of SessionState (e.g., `control.orchestration_state`, `meta.last_orchestration_time`).

**Pros:**
- Faster state updates (no Delta Bus intermediary)
- Orchestrator can track its own state in SessionState

**Cons:**
- Breaks single-writer pattern (two writers = race conditions)
- MutationGuard must handle concurrent writers (complexity explosion)
- Sets precedent for other components to request write access

**Rejected because:** The Single-Writer Pattern (ADR-0017g) is a foundational invariant. Granting exceptions creates a slippery slope where every component argues for "just a small write." The Delta Bus is designed for exactly this pattern -- fire-and-forget state suggestions that the sole writer applies at its discretion.

### Alternative 2: Write-Through Cache (Orchestrator Writes, Concierge Validates)

**Description:** Orchestrator writes to a staging area; Concierge validates and promotes to SessionState.

**Pros:**
- Orchestrator can "write" without direct SessionState access
- Two-phase commit provides safety

**Cons:**
- Staging area is effectively a second SessionState (complexity)
- Two-phase commit within a single-threaded event loop is complex
- Concierge must poll staging area or be notified (same as Delta Bus)

**Rejected because:** This is the Delta Bus with extra steps. The staging area adds complexity without improving the protocol. Delta Bus already provides fire-and-forget delivery with Concierge as the final arbiter.

---

## Consequences

### Positive

- Zero race conditions between Orchestrator and SessionState
- Clear boundary: Orchestrator produces outcomes, Concierge applies them
- Protocol-level enforcement prevents accidental writes (compile-time safety)
- Testable invariant: CI gate catches any ORCH-01 violations immediately
- Safety band re-read provides defense against stale context without writes

### Negative

- Orchestrator cannot update SessionState directly, even for simple status updates
- Delta Bus delivery is fire-and-forget (no guarantee Concierge applied the delta)
- Stale reads possible during long DAG executions (mitigated by wave boundary re-reads)

### Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Stale safety band causes incorrect step execution | Low | High | Re-read at every wave boundary (max 5-15s staleness) |
| Delta Bus drops critical deltas | Low | Medium | Deltas are best-effort; AggregatedResult delivered via direct mailbox return |
| Future developer bypasses IStateReadPort | Low | High | CI test gate (test_orch_01_no_writes.py), code review enforcement |

---

## Implementation

### Affected Code Paths

| Component | File | Change Type |
|-----------|------|-------------|
| IStateReadPort | `k1/orchestrator/ports/state_read_port.py` | New |
| IDeltaEmitPort | `k1/orchestrator/ports/delta_emit_port.py` | New |
| StateReadAdapter | `k1/orchestrator/adapters/state_read_adapter.py` | New |
| DeltaEmitAdapter | `k1/orchestrator/adapters/delta_emit_adapter.py` | New |
| ORCH-01 invariant tests | `tests/k1/orchestrator/invariants/test_orch_01_no_writes.py` | New |

### Events Emitted/Consumed

| Event Topic | Direction | Description |
|-------------|-----------|-------------|
| `k1.orchestration.delta.v1` | Emitted | Progress, outcomes, status changes (fire-and-forget) |
| `k1.hil.progress.v1` | Emitted | Step progress narration to user |
| `k1.orchestration.dag.completed.v1` | Emitted | Final AggregatedResult |
| `k1.orchestration.hil.request.v1` | Emitted | HIL question from ConstraintResolver fallback |

### Contracts Affected

| Contract | Type | Change |
|----------|------|--------|
| SessionState read contract | Port interface | IStateReadPort -- read-only Protocol |
| ADR-0017g | Architectural alignment | Orchestrator classified as read-only kernel component |

### Port/Adapter Impact

| Port | Adapter | Change |
|------|---------|--------|
| `IStateReadPort` | `StateReadAdapter` / `MockStateReadAdapter` | New (read-only, no write methods) |
| `IDeltaEmitPort` | `DeltaEmitAdapter` / `TestDeltaAdapter` | New (fire-and-forget deltas) |

### Success Metrics

- ORCH-01 invariant: zero SessionState writes in all integration tests (CI gate)
- IStateReadPort Protocol: zero write methods (compile-time verification)
- Safety band re-read at every wave boundary (logged, auditable)
- All Orchestrator outcomes delivered via IDeltaEmitPort (traced with cognitive_trace_id)

### Testing Strategy

- [ ] Invariant tests: `test_orch_01_no_writes.py` (4 test cases, CI gate)
- [ ] Unit tests: IStateReadPort mock captures read-only operations
- [ ] Unit tests: IDeltaEmitPort captures all emitted deltas
- [ ] Integration tests: Safety band re-read at wave boundaries
- [ ] Negative tests: Verify IStateReadPort has no write methods via reflection

---

## Amendment History

| Date | Author | Change |
|------|--------|--------|
| 2026-02-11 | K1 Architecture Team | Initial decision -- ORCH-01 formalization for ADR-0017 compliance |
