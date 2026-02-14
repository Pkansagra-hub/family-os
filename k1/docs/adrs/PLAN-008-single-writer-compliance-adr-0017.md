---
adr_id: PLAN-008
title: "Single Writer Compliance Review -- ADR-0017 for Planner"
status: Accepted
date: 2026-02-14
module: planner
layer: "L3"
authors:
  - "K1 Architecture Team"
related_adrs:
  - "PLAN-001"
  - "PLAN-005"
  - "PLAN-006"
related_events:
  - "k1.planner.plan.ready.v1"
  - "k1.planner.delta.v1"
related_contracts:
  - "k1/contracts/modules/planner/wiring.contract.yaml"
  - "k1/contracts/modules/planner/module.contract.yaml"
related_ports:
  - "IStateReadPort"
  - "IFabricRetrievalPort"
  - "IBridgePort"
  - "IDeltaEmitPort"
implements_issue: "1.1.2"
superseded_by: ""
tags:
  - planner
  - review
  - adr-0017
  - single-writer
  - compliance
  - read-only
---

# PLAN-008: Single Writer Compliance Review -- ADR-0017 for Planner

## Context

### Problem Statement

ADR-0017 (SessionState 6-Section Tiered Design) establishes the Single Writer principle for session state: only the designated owner module may write to each SessionState section. The Planner module must demonstrably comply with this principle -- it must never write to SessionState, only read. This review documents the compliance matrix mapping ADR-0017 requirements to Planner port and invariant enforcement points.

### Scope

This review covers Planner compliance with ADR-0017's Single Writer principle:

- Port interface analysis (read-only enforced at Protocol level)
- Discovery tool analysis (all tools read-only)
- Output channel analysis (event bus and delta, not direct state writes)
- Invariant enforcement mechanisms (PLAN-01, PLAN-02, PLAN-06)

### Review Source Documents

- **ADR-0017**: `docs/architecture/decisions-K1/03-layer2-orchestration/0017-sessionstate-6-section-design/0017.md` (1571 lines, Nov 2025)
- **planner.md**: Authoritative Planner specification (Feb 2026), specifically SS15.5 (IStateReadPort), SS11.5.1 (routing table), SS15.4 (IFabricRetrievalPort)

---

## Compliance Matrix

### PLAN-01: IStateReadPort Is Read-Only

**ADR-0017 Requirement:** Only the designated writer module may mutate SessionState sections.

**Planner Compliance:**

| Aspect | Evidence | Reference |
| ------ | -------- | --------- |
| Port name | `IStateReadPort` -- "Read" is in the name | SS15.5 |
| Port Protocol methods | `read_planning_context(request_id) -> SessionSnapshot` | SS15.5 |
| Write methods | **NONE** -- Protocol has no `write_*`, `update_*`, or `set_*` methods | SS15.5 |
| Enforcement level | Structural -- Protocol class defines only read methods | Interface-level |
| Runtime bypass possible? | No -- adapter implements Protocol; no write method exists to call | Protocol enforcement |

**Verdict: COMPLIANT**

The Planner's state access port is structurally read-only. There is no method signature through which the Planner could write to SessionState, even accidentally. This is enforced at the Protocol (interface) level, not by convention.

### PLAN-02: All Discovery Tools Are Read-Only

**ADR-0017 Requirement:** Modules that are not the designated writer must not produce side effects on state.

**Planner Compliance:**

| Tool Name | Backend Port | Operation | Side Effects | Reference |
| --------- | ------------ | --------- | ------------ | --------- |
| `discover_capabilities` | `IFabricRetrievalPort` | Semantic search over registered capabilities | None -- read-only query | SS11.5.1 |
| `find_relevant_prompts` | `IFabricRetrievalPort` | Semantic search over prompt templates | None -- read-only query | SS11.5.1 |
| `query_planning_context` | `IStateReadPort` | Read planning-relevant fields from session state | None -- read via PLAN-01 compliant port | SS11.5.1 |
| `recall_for_planning` | `IBridgePort` | Recall prior plan results and memory entries | None -- read-only recall | SS11.5.1 |

**Routing Table Analysis:**

The ToolCallRouter routing table (SS11.5.1) contains exactly 4 entries. All 4 map to read-only methods on read-only ports. There are zero write/execute/action routes in the table.

**Verdict: COMPLIANT**

All discovery tools are read-only with zero side effects. The routing table structure makes this auditable: any new tool added to the routing table would be visible in code review and contract tests.

### PLAN-06: IFabricRetrievalPort Has No invoke_capability

**ADR-0017 Requirement:** State-reading modules must not have the ability to trigger execution through their ports.

**Planner Compliance:**

| Aspect | Evidence | Reference |
| ------ | -------- | --------- |
| Port name | `IFabricRetrievalPort` -- "Retrieval" signals read-only intent | SS15.4 |
| Methods available | `discover_capabilities()`, `find_relevant_prompts()` | SS15.4 |
| Methods NOT available | `invoke_capability()` -- deliberately excluded | SS15.4 |
| Write methods | **NONE** -- no mutation methods in Protocol | SS15.4 |
| Execution methods | **NONE** -- no invoke/execute/call methods | SS15.4 |

**Distinction from Orchestrator's Fabric port:**

| Port | Owner | Has invoke_capability | Purpose |
| ---- | ----- | --------------------- | ------- |
| `IFabricRetrievalPort` | Planner | No | Discovery only |
| `IFabricGatewayPort` | Orchestrator | Yes | Discovery + Execution |

The Planner has a deliberately narrower port than the Orchestrator. The Orchestrator needs `invoke_capability` to execute plan steps; the Planner only needs discovery to inform plan creation.

**Verdict: COMPLIANT**

IFabricRetrievalPort is a proper subset of IFabricGatewayPort, containing only discovery methods. The Planner cannot invoke capabilities, even if it discovers them.

### Output Channel Compliance

**ADR-0017 Requirement:** Modules produce output through designated channels, not by writing directly to other modules' state.

**Planner Output Channels:**

| Channel | Mechanism | Target | State Mutation? |
| ------- | --------- | ------ | --------------- |
| CommittedPlan delivery | Event: `k1.planner.plan.ready.v1` | Orchestrator (via event bus) | No -- event published, Orchestrator chooses to consume |
| Plan failure | Event: `k1.planner.plan.failed.v1` | Orchestrator (via event bus) | No -- event published |
| Plan cancellation | Event: `k1.planner.plan.cancelled.v1` | Orchestrator (via event bus) | No -- event published |
| Delta emission | Event: `k1.planner.delta.v1` | Telemetry / Observability | No -- observability channel |
| WAL persistence | `IBridgePort.persist_plan()` | K0 WAL (via Bridge) | Write to WAL only -- NOT to SessionState |
| HIL events | Events: `k1.hil.clarification.v1`, `k1.hil.approval_request.v1` | Concierge (via event bus) | No -- event published |

**Verdict: COMPLIANT**

All Planner output flows through the event bus or WAL persistence. The Planner never writes to SessionState directly. WAL persistence (IBridgePort) writes to a separate storage layer, not to SessionState sections.

---

## Summary Compliance Table

| Invariant | ADR-0017 Principle | Enforcement Mechanism | Verdict |
| --------- | ------------------ | --------------------- | ------- |
| PLAN-01 | Single Writer (no state writes) | IStateReadPort Protocol has no write methods | COMPLIANT |
| PLAN-02 | No side effects from discovery | All 4 tools map to read-only port methods | COMPLIANT |
| PLAN-06 | No execution capability | IFabricRetrievalPort has no invoke_capability | COMPLIANT |
| Output channels | Designated channels only | Event bus + WAL persist (no direct state write) | COMPLIANT |

**Overall Assessment: FULLY COMPLIANT**

The Planner module complies with ADR-0017's Single Writer principle through structural enforcement at the port Protocol level. Compliance is not dependent on developer discipline or runtime checks -- the interfaces physically lack write methods.

---

## Decision

### Compliance Confirmed

The Planner module is fully compliant with ADR-0017 Single Writer principle. Compliance is enforced at three levels:

1. **Port Protocol level** -- IStateReadPort and IFabricRetrievalPort define only read methods
2. **Routing table level** -- ToolCallRouter contains only read-only tool mappings
3. **Output channel level** -- all output flows through events or WAL, never through SessionState writes

### Monitoring Recommendations

To maintain compliance as the Planner evolves:

1. **Contract test**: Verify IStateReadPort Protocol has no write methods (inspect Protocol members)
2. **Contract test**: Verify IFabricRetrievalPort Protocol has no invoke_capability method
3. **Contract test**: Verify ToolCallRouter routing table contains only read-only entries
4. **Code review gate**: Any new port added to Planner must be assessed for Single Writer compliance

---

## Consequences

### Positive

- Planner cannot cause state corruption in SessionState
- Single Writer violations are structurally impossible (not just unlikely)
- Clean separation: Planner reads state and produces plans; state writes happen elsewhere
- Compliance is auditable through port Protocol inspection

### Negative

- Planner cannot cache planning results in SessionState (must use WAL or event bus)
- Any future need for Planner state writes requires architectural change (new port, new ADR)

### Risks

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| New port added without compliance review | Low | High | Contract tests verify all Planner ports are read-only where expected |
| IBridgePort gains state-writing methods | Low | Med | IBridgePort writes to WAL, not SessionState; distinct storage domains |
| ToolCallRouter gets write-capable tool | Low | High | Contract test verifies routing table entries are read-only |

---

## Implementation

### Affected Code Paths

No code changes. This is a compliance review document.

### Contract Tests Required

| Test | Description | Enforcement |
| ---- | ----------- | ----------- |
| `test_state_read_port_no_write_methods` | Inspect IStateReadPort Protocol members; assert no write_*/update_*/set_* | Gate 4 |
| `test_fabric_retrieval_port_no_invoke` | Inspect IFabricRetrievalPort Protocol members; assert no invoke_capability | Gate 4 |
| `test_tool_router_read_only_routing` | Inspect ToolCallRouter._routing values; assert all are read methods | Gate 4 |
| `test_planner_no_state_write_port` | Inspect PlannerAgent constructor; assert no IStateWritePort injection | Gate 4 |

### Success Metrics

- All 4 contract tests pass in CI
- Zero SingleWriterViolation events in observability for Planner module

### Testing Strategy

- [ ] Contract tests as described above (added in Epic 1.4 or 1.5)
- [ ] Observability check: no Planner-originated state write events in production

---

## Amendment History

| Date | Author | Change |
| ---- | ------ | ------ |
| 2026-02-14 | K1 Architecture Team | Initial compliance review -- Planner fully compliant with ADR-0017 |
