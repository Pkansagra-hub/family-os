---
adr_id: PLAN-006
title: "Discovery Tool Selection and Routing"
status: Accepted
date: 2026-02-14
module: planner
layer: "L3"
authors:
  - "K1 Architecture Team"
related_adrs:
  - "PLAN-001"
  - "PLAN-002"
  - "PLAN-003"
  - "PLAN-008"
  - "ORCH-002"
related_events:
  - "k1.planner.delta.v1"
related_contracts:
  - "k1/contracts/modules/planner/wiring.contract.yaml"
  - "k1/contracts/modules/planner/module.contract.yaml"
related_ports:
  - "IFabricRetrievalPort"
  - "IStateReadPort"
  - "IBridgePort"
implements_issue: "1.1.8"
superseded_by: ""
tags:
  - planner
  - discovery
  - tools
  - routing
  - read-only
  - plan-02
  - plan-05
  - plan-06
---

# PLAN-006: Discovery Tool Selection and Routing

## Context

### Problem Statement

The Planner's SKETCH and EXPAND stages need context from the system to produce informed plans: available capabilities, relevant prompts, planning context from session state, and prior plan history. These lookups must be strictly read-only (PLAN-02), bounded in number (PLAN-05), and routed to the correct backend port without the Planner having direct knowledge of backend implementations.

### Current Situation

planner.md SS11 defines 4 discovery tools with a routing table mapping each tool to a backend port. The ToolCallRouter component owns the routing table, budget enforcement (PLAN-05), and retry policy. All tools are read-only with zero side effects, enforcing PLAN-02 and PLAN-06 at the routing level.

### Constraints

- PLAN-02: All discovery tools are read-only, zero side effects (SS11.5.1)
- PLAN-05: Max 6 tool calls per plan -- ToolCallRouter enforces via atomic counter (SS11.5.2)
- PLAN-06: IFabricRetrievalPort has discovery methods only, no `invoke_capability` (SS15.4)
- Tools are used in SKETCH (3 calls) and EXPAND (2-3 calls); VALIDATE and COMMIT use 0
- Micro-replan resets tool budget to 0 (independent from full plan, PLAN-003)

### Requirements

- 4 discovery tools with well-defined routing to 3 backend ports
- Atomic budget counter enforcing max 6 calls per plan
- Per-tool retry policy with retries not counting against budget
- Concurrent dispatch within stages via asyncio.gather
- Graceful fallback when all tools fail

---

## Decision

### Chosen Approach

4 read-only discovery tools routed through ToolCallRouter to 3 backend ports with max 6 calls per plan (planner.md SS11).

### Key Design

**Routing Table (SS11.5.1):**

| Tool Name | Backend Port | Return Type | Description |
| --------- | ------------ | ----------- | ----------- |
| `discover_capabilities` | `IFabricRetrievalPort` | `List[ScoredCapability]` | Search Fabric for relevant capabilities by semantic query |
| `find_relevant_prompts` | `IFabricRetrievalPort` | `List[RetrievalResult]` | Find prompt templates relevant to the planning context |
| `query_planning_context` | `IStateReadPort` | `SessionSnapshot` | Read planning-relevant fields from session state |
| `recall_for_planning` | `IBridgePort` | `List[RetrievalResult]` | Recall prior plan results and memory entries |

**PLAN-02 Enforcement:**

All 4 tools are read-only. The routing table contains zero write/execute/action routes. This is verified by:

- Port interface analysis: `IFabricRetrievalPort` has no `invoke_capability` method (PLAN-06)
- Port interface analysis: `IStateReadPort` has no `write_*` methods (PLAN-01 compliance)
- Port interface analysis: `IBridgePort.recall_for_planning()` is a read method
- Contract test: routing table contains only methods that return data, no methods that mutate state

**PLAN-05 Budget Enforcement (SS11.5.2):**

```python
class ToolCallRouter:
    MAX_TOOL_CALLS = 6

    def __init__(self, fabric_port, state_port, bridge_port):
        self._counter = 0
        self._routing = {
            "discover_capabilities": fabric_port.discover_capabilities,
            "find_relevant_prompts": fabric_port.find_relevant_prompts,
            "query_planning_context": state_port.read_planning_context,
            "recall_for_planning": bridge_port.recall_for_planning,
        }

    async def call(self, tool_name: str, **kwargs) -> Any:
        if self._counter >= self.MAX_TOOL_CALLS:
            raise BudgetExhaustedError(f"Tool budget exhausted ({self.MAX_TOOL_CALLS})")
        self._counter += 1
        handler = self._routing[tool_name]
        return await self._retry(handler, tool_name, **kwargs)

    def reset(self) -> None:
        """Reset counter for micro-replan."""
        self._counter = 0
```

**Budget Allocation by Stage:**

| Stage | Expected Calls | Tools Used |
| ----- | -------------- | ---------- |
| SKETCH | 3 | discover_capabilities + query_planning_context + recall_for_planning |
| EXPAND | 2-3 | discover_capabilities (refined) + find_relevant_prompts + optional recall |
| VALIDATE | 0 | None |
| COMMIT | 0 | None |

**Retry Policy (SS11.5.3):**

| Tool | Retry Delay | Max Retries | Notes |
| ---- | ----------- | ----------- | ----- |
| `discover_capabilities` | 50ms | 1 | Fabric query may transiently fail |
| `find_relevant_prompts` | 50ms | 1 | Same backend as discover |
| `query_planning_context` | 10ms | 0 | Local state read, fast fail |
| `recall_for_planning` | 100ms | 0 | Bridge query, no retry |

Retries do NOT double-count against the budget (SS11.5.2). The counter increments once per logical call, regardless of retry attempts.

**Concurrent Dispatch (SS11.5.4):**

SKETCH dispatches 3 calls concurrently:

```python
results = await asyncio.gather(
    router.call("discover_capabilities", query=intent),
    router.call("query_planning_context", request_id=request_id),
    router.call("recall_for_planning", query=intent),
    return_exceptions=True,
)
```

EXPAND dispatches 2-3 calls concurrently.

**Fallback on All-Tools-Fail:**

If all discovery tools fail (or budget is exhausted before SKETCH completes), the LLM generates a plan from `PlanRequest.intent` alone. This produces a valid but minimal plan (no capability mappings, generic steps). Logged as a degraded plan in the delta payload.

### Rationale

Read-only tools with explicit routing and budget enforcement provide:

- Strong PLAN-02 guarantee (impossible to mutate state through discovery tools)
- Predictable resource usage (max 6 external calls per plan)
- Clear ownership (ToolCallRouter is the single point of control)
- Graceful degradation (LLM can still plan without discovery results)

---

## Alternatives Considered

### Alternative 1: Unrestricted Tool Calls

**Description:** No budget limit. LLM decides how many discovery calls to make.

**Pros:**

- LLM can gather optimal context

**Cons:**

- Unbounded external calls (Fabric, Bridge, State queries)
- Unpredictable latency
- Resource contention under load

**Rejected because:** PLAN-05's 6-call budget is sufficient for typical plans (3 SKETCH + 3 EXPAND). Unbounded calls add unpredictable latency to a time-budgeted pipeline.

### Alternative 2: Static Discovery (No Runtime Calls)

**Description:** Pre-load all discovery context before pipeline starts. No runtime tool calls.

**Pros:**

- Predictable latency (all data loaded upfront)
- No tool routing complexity

**Cons:**

- Cannot refine discovery based on SKETCH results (EXPAND needs refined queries)
- Pre-loading everything wastes resources when only a subset is needed
- Larger prompt context (more tokens) for each LLM call

**Rejected because:** Two-phase discovery (broad in SKETCH, refined in EXPAND) produces better plans. Stage-specific queries are more targeted than pre-loading everything.

### Alternative 3: Write-Capable Tools

**Description:** Include tools that can create capabilities, modify state, or trigger actions during planning.

**Pros:**

- Planner could provision resources during planning

**Cons:**

- Violates PLAN-02 (read-only discovery)
- Violates PLAN-06 (no invoke_capability in discovery ports)
- Side effects during planning create rollback complexity
- Breaks Single Writer compliance (ADR-0017)

**Rejected because:** Planning must be side-effect-free. Execution is the Orchestrator's responsibility.

---

## Consequences

### Positive

- Zero side effects from discovery (PLAN-02 enforced)
- Bounded external calls (PLAN-05 max 6)
- Clean port routing (3 ports, 4 tools, 1 router)
- Concurrent dispatch reduces discovery latency

### Negative

- 6 calls may be insufficient for complex multi-domain plans
- Fixed routing table cannot accommodate new tools without code change
- Retry policy is per-tool, not adaptive

### Risks

| Risk | Likelihood | Impact | Mitigation |
| ---- | ---------- | ------ | ---------- |
| Budget exhaustion before EXPAND | Low | Med | Budget allocation: 3 SKETCH + 3 EXPAND ensures both stages get calls |
| Fabric retrieval returns irrelevant results | Med | Med | LLM filters results during SKETCH/EXPAND; V2 may add relevance scoring |
| All tools fail simultaneously | Very Low | Med | Fallback to intent-only planning; degraded plan logged |

---

## Implementation

### Affected Code Paths

| Component | File | Change Type |
| --------- | ---- | ----------- |
| ToolCallRouter | `k1/planner/services/tool_call_router.py` [F25] | New -- routing table, budget counter, retry logic |
| SketchService | `k1/planner/services/sketch_service.py` [F20] | Modified -- calls router for 3 discovery tools |
| ExpandService | `k1/planner/services/expand_service.py` [F21] | Modified -- calls router for 2-3 discovery tools |
| BudgetExhaustedError | `k1/planner/errors.py` [F09] | New -- raised when PLAN-05 budget exceeded |
| PlannerConfig | `k1/planner/config.py` [F07] | New -- max_tool_calls=6, per-tool retry config |

### Events Emitted/Consumed

| Event Topic | Direction | Description |
| ----------- | --------- | ----------- |
| `k1.planner.delta.v1` | Emitted | Contains tool_call_count and discovery_results in delta |

### Contracts Affected

| Contract | Type | Change |
| -------- | ---- | ------ |
| `module.contract.yaml` | Module | Declares PLAN-02, PLAN-05, PLAN-06 invariants |
| `wiring.contract.yaml` | Module Wiring | ToolCallRouter requires 3 ports: IFabricRetrievalPort, IStateReadPort, IBridgePort |

### Port/Adapter Impact

| Port | Adapter | Change |
| ---- | ------- | ------ |
| `IFabricRetrievalPort` | `FabricRetrievalAdapter` | Existing -- discover_capabilities(), find_relevant_prompts() |
| `IStateReadPort` | `StateReadAdapter` | Existing -- read_planning_context() |
| `IBridgePort` | `BridgeAdapter` | Existing -- recall_for_planning() |

### Success Metrics

- Tool budget utilization: avg 5-6 calls per plan (near-full use of budget)
- Discovery success rate: > 95% of calls return usable results
- Concurrent dispatch speedup: 2-3x vs sequential for 3-call batches
- Fallback plan rate: < 2% of plans use intent-only fallback

### Testing Strategy

- [ ] Unit test: ToolCallRouter enforces max 6 calls (raises BudgetExhaustedError)
- [ ] Unit test: retry does not double-count against budget
- [ ] Unit test: routing table maps tool names to correct port methods
- [ ] Unit test: reset() clears counter for micro-replan
- [ ] Integration test: SKETCH concurrent dispatch via asyncio.gather
- [ ] Contract test: IFabricRetrievalPort has no invoke_capability method
- [ ] Contract test: IStateReadPort has no write_* methods

---

## Amendment History

| Date | Author | Change |
| ---- | ------ | ------ |
| 2026-02-14 | K1 Architecture Team | Initial decision -- 4 read-only tools, 3-port routing, 6-call budget |
