# Planner Implemented Spec -- Factory Wiring Guide

> **Purpose**: Single source of truth for building `k1/planner/factory.py`.
> Every constructor signature, port protocol, dependency, and layer assignment
> documented here is extracted from **actual code** on branch `k1-kernel` -- not
> from spec aspirations. Where code diverges from planner.md, code wins and
> the divergence is flagged.
>
> **Audience**: PlannerFactory implementer only.
>
> **Date**: 2026-02-15

---

## Table of Contents

1. [Dependency Layer Map](#1-dependency-layer-map)
2. [Port Protocol Registry](#2-port-protocol-registry)
3. [Type and Error Registry](#3-type-and-error-registry)
4. [Config Spec](#4-config-spec)
5. [Service Constructors](#5-service-constructors)
6. [Stage Constructors](#6-stage-constructors)
7. [Orchestrator Constructors](#7-orchestrator-constructors)
8. [Port-to-Service Wiring Matrix](#8-port-to-service-wiring-matrix)
9. [10-Step Wiring Sequence](#9-10-step-wiring-sequence)
10. [Adapter Registry](#10-adapter-registry)
11. [Event Topic Registry](#11-event-topic-registry)
12. [Hard Invariants Checklist](#12-hard-invariants-checklist)
13. [Agentic Tool-Use Architecture](#13-agentic-tool-use-architecture)
14. [Discrepancies Plan vs Code](#14-discrepancies-plan-vs-code)
15. [Factory Requirements Summary](#15-factory-requirements-summary)

---

## 1. Dependency Layer Map

Every file in `k1/planner/` belongs to exactly one layer. A file at layer N
may import from layers 0..N-1 only. `factory.py` (Layer 7) is the sole
exception -- it imports across ALL layers.

| Layer | Files | Import Rule |
|-------|-------|-------------|
| **L0** | `types.py` [F05], `events.py` [F06], `config.py` [F07], `plan_fsm.py` [F04] | stdlib only, no internal deps |
| **L1** | `ports/*.py` [F11-F18] (7 Protocol files + `__init__.py`) | L0 types only |
| **L2** | `adapters/*.py` [F27-F34] (7 production adapters + `__init__.py`) | L0 + L1 |
| **L3** | `services/*.py` [F25-F26] (`ToolCallRouter`, `HILCoordinator`) | L0 + L1 |
| **L4** | `stages/*.py` [F19-F23] (`SketchService`, `ExpandService`, `ValidateService`, `CommitService`) | L0 + L1 + L3 |
| **L5** | `pipeline_controller.py` [F03] | L0 + L1 + L4 |
| **L6** | `planner_agent.py` [F02] | L0 + L1 + L5 |
| **L7** | `factory.py` [F08] | **ALL layers** (only file allowed) |
| **L8** | `__init__.py` [F01] | re-exports only |

**Circular import guard**: No file at layer N imports from layer N+1 or above.
Factory is the single convergence point.

---

## 2. Port Protocol Registry

All 7 ports live in `k1/planner/ports/` and are `@runtime_checkable` Protocols.
Re-exported via `k1.planner.ports.__init__`.

### 2.1 IMailboxPort [F12]

**File**: `k1/planner/ports/mailbox_port.py`

```python
@runtime_checkable
class IMailboxPort(Protocol):
    async def dequeue(self) -> PlanRequest: ...
    async def enqueue(self, request: PlanRequest) -> None: ...
    async def send_cancel(self, request_id: str) -> None: ...
    async def drain(self) -> List[PlanRequest]: ...
    async def micro_replan(self, request: MicroReplanRequest) -> CommittedPlan: ...
```

- Direction: **Inbound** (Orchestrator -> Planner)
- Properties: MPSC + FIFO, bounded at `max_depth=5`
- Raises: `MailboxFullError` on overflow

### 2.2 ILLMPort [F13]

**File**: `k1/planner/ports/llm_port.py`

```python
@runtime_checkable
class ILLMPort(Protocol):
    async def execute(self, request: HubRequest) -> HubResponse: ...
```

- Direction: **Outbound** (Planner -> Model Hub)
- Callers: SketchService, ExpandService, ValidateService, HILCoordinator
- NOT called by: CommitService (PLAN-03)
- Every HubRequest carries `RequestConstraints` (PLAN-11)

### 2.3 IFabricRetrievalPort [F14]

**File**: `k1/planner/ports/fabric_retrieval_port.py`

```python
@runtime_checkable
class IFabricRetrievalPort(Protocol):
    async def discover_capabilities(
        self,
        domain: Optional[List[str]] = None,
        intent: str = "",
        safety_band: str = "GREEN",
        session_context: Optional[Dict[str, Any]] = None,
        top_k: int = 10,
    ) -> RetrievalResult: ...

    async def find_relevant_prompts(
        self,
        intent: str = "",
        domain: Optional[List[str]] = None,
        safety_band: str = "GREEN",
        top_k: int = 5,
    ) -> RetrievalResult: ...
```

- Direction: **Outbound read-only** (Planner -> Fabric)
- In-process call (NOT HTTP)
- PLAN-06: NO `invoke_capability` or `execute` method exists

### 2.4 IStateReadPort [F15]

**File**: `k1/planner/ports/state_read_port.py`

```python
@runtime_checkable
class IStateReadPort(Protocol):
    async def read_sections(
        self,
        sections: List[str],
        trace_id: str = "",
    ) -> SessionSnapshot: ...
```

- Direction: **Outbound read-only** (Planner -> SessionState)
- PLAN-01: NO write method exists
- Lock-free multi-reader

### 2.5 IBridgePort [F16]

**File**: `k1/planner/ports/bridge_port.py`

```python
@runtime_checkable
class IBridgePort(Protocol):
    async def recall(
        self,
        query: str,
        selectors: Optional[List[str]] = None,
        *,
        trace_id: str = "",
    ) -> RecallResponse: ...

    async def persist_plan(
        self,
        plan: CommittedPlan,
        *,
        trace_id: str = "",
    ) -> None: ...
```

- Direction: **Outbound** (Planner -> K0 Bridge)
- `persist_plan` is fire-and-forget (CommitService does NOT await confirmation)
- Offline: `recall` returns empty, `persist_plan` silently drops

### 2.6 IDeltaEmitPort [F17]

**File**: `k1/planner/ports/delta_emit_port.py`

```python
@runtime_checkable
class IDeltaEmitPort(Protocol):
    def emit(self, delta: DeltaPayload) -> None: ...
```

- Direction: **Outbound fire-and-forget**
- **Synchronous** (not async) -- MUST NOT block, MUST NOT raise
- Delta loss is acceptable (observability signal, not control plane)

### 2.7 IEventPort [F18]

**File**: `k1/planner/ports/event_port.py`

```python
@runtime_checkable
class IEventPort(Protocol):
    def emit(self, topic: str, payload: Any) -> None: ...
    def subscribe(self, topic: str, handler: Callable[..., Any]) -> SubscriptionHandle: ...
    def unsubscribe(self, handle: SubscriptionHandle) -> bool: ...
```

- Direction: **Bidirectional** (pub/sub)
- `emit` is synchronous, fire-and-forget
- Subscription lifecycle: INIT subscribes, SHUTDOWN unsubscribes

---

## 3. Type and Error Registry

**File**: `k1/planner/types.py` [F05]

### 3.1 Data Types (frozen dataclasses)

| Type | Key Fields |
|------|------------|
| `RoughStep` | `intent: str`, `suggested_capability: Optional[str]`, `depends_on: List[str]`, `confidence: float` |
| `SketchResult` | `rough_steps: List[RoughStep]`, `capability_candidates: List[ScoredCapability]`, `rationale: str` |
| `ExpandedPlan` | `steps: List[PlanStep]`, `dependencies: Dict[str, List[str]]`, `tool_mappings: Dict[str, str]`, `rationale: str` |
| `ValidationIssue` | `check_name: str`, `severity: str`, `step_id: Optional[str]`, `detail: str` |
| `ValidationVerdict` | `status: str`, `issues: List[ValidationIssue]`, `confidence: float`, `rationale: str`, `deterministic_pass: bool`, `safety_assessment: str`, `suggested_fixes: List[str]` |
| `StageContext` | `request_id: str`, `trace_id: str`, `timeout_remaining_ms: int`, `token_budget_remaining: int`, `cancel_check: Callable[[], bool]`, `stage_budget: Optional[RequestConstraints]` |
| `DeltaPayload` | `agent_id: str`, `delta_type: str`, `section: str`, `data: Dict[str, Any]`, `trace_id: str` |
| `RequestConstraints` | `max_tokens: int`, `timeout_ms: int`, `priority: str`, `temperature: float`, `consumer_id: str` |
| `HubRequest` | `capability: str`, `payload: Dict[str, Any]`, `constraints: RequestConstraints`, `trace_id: str` |
| `HubResponse` | `result: Dict[str, Any]`, `metadata: Dict[str, Any]` |
| `RecallResponse` | `facts: List[Dict[str, Any]]`, `scores: List[float]`, `trace_id: str` |
| `TokenUsageRecord` | `stage: str`, `prompt_tokens: int`, `completion_tokens: int`, `total_tokens: int` (**mutable**) |

### 3.2 Enums

| Enum | Members |
|------|---------|
| `StagePhase` | `SKETCH`, `EXPAND`, `VALIDATE`, `COMMIT` |
| `ToolCallStatus` | `SUCCESS`, `TIMEOUT`, `ERROR`, `BUDGET_EXHAUSTED` |

### 3.3 Protocol Aliases (structural)

| Protocol | Defined In | Methods |
|----------|-----------|---------|
| `HILCoordinatorLike` | `types.py` | `round_count`, `reset()`, `request_clarification()`, `request_approval()` |
| `ToolCallRouterLike` | `stages/sketch_service.py` (local) | `tool_call_count`, `reset()`, `discover()`, `read_context()`, `recall_memory()`, `find_prompts()` |
| `ExpandToolRouterLike` | `stages/expand_service.py` (local) | `tool_call_count`, `reset()`, `discover()`, `get_schema()`, `find_prompts()`, `read_context()` |

`ToolCallRouter` satisfies both `ToolCallRouterLike` and `ExpandToolRouterLike` structurally.

### 3.4 Error Hierarchy

All extend `PlannerError(Exception)` which carries `stage: str`, `request_id: str`, `trace_id: str`.

| Error | Error Code | Trigger |
|-------|-----------|---------|
| `PlannerError` | (base) | all planner errors |
| `SketchFailedError` | ERR_SKETCH_FAIL | sketch stage failure |
| `ExpandFailedError` | ERR_EXPAND_FAIL | expand stage failure |
| `ValidateRejectedError` | ERR_VALIDATE_FAIL | validate rejects plan |
| `CommitFailedError` | ERR_COMMIT_FAIL | commit stage failure |
| `BudgetExhaustedError` | PLAN-05/PLAN-11 | token or tool budget exceeded |
| `MailboxFullError` | — | mailbox depth >= 5 |
| `ShutdownError` | — | enqueue during shutdown |
| `PlanCancelledError` | — | cooperative cancel |
| `HILTimeoutError` | — | HIL response timeout |
| `HILBudgetExceededError` | — | max HIL rounds (PLAN-10) |
| `LLMTimeoutError` | — | LLM call timeout |
| `BudgetExceededError` | — | model hub budget |
| `AdapterException` | — | adapter-level failure |
| `UnknownToolError` | — | tool not in routing table |

### 3.5 Factory Error Types (to be added)

| Error | Context | Trigger |
|-------|---------|---------|
| `InvalidPortError` | `port_name, expected_protocol, actual_type` | port fails `isinstance` check |
| `MissingPortError` | `port_name` | port is `None` |
| `DuplicatePortError` | `port_a, port_b` | same `id()` for two port slots |
| `InvalidConfigError` | `field_name, value, constraint` | config field out of bounds |
| `PlannerInitError` | `detail` | `agent.start()` fails or agent not ready |

### 3.6 Constants

```python
VERDICT_APPROVED = "approved"
VERDICT_REVISE = "revise"
VERDICT_REJECT = "reject"

SAFETY_SAFE = "SAFE"
SAFETY_CAUTION = "CAUTION"
SAFETY_UNSAFE = "UNSAFE"
SAFETY_UNKNOWN = "UNKNOWN"

PLANNER_AGENT_ID = "planner"

# Delta types
DELTA_STAGE_TRANSITION = "stage_transition"
DELTA_TOOL_RESULT = "tool_result"
DELTA_HIL_EVENT = "hil_event"
DELTA_PLAN_UPDATE = "plan_update"
DELTA_PLAN_END = "plan_end"
DELTA_PLAN_CANCELLED = "plan_cancelled"
DELTA_MICRO_REPLAN = "micro_replan"
DELTA_CRASH_RECOVERY = "crash_recovery"
```

### 3.7 External Shared Types (imported, not owned)

Source of truth: `k1/orchestrator/types.py`

| Type | Key Fields |
|------|------------|
| `PlanRequest` | `request_id`, `intent`, `domain`, `context`, `session_id`, `trace_id`, `allow_hil`, `priority` |
| `CommittedPlan` | `plan_id`, `request_id`, `steps`, `dependencies`, `created_at`, `estimated_duration_ms`, `trace_id` |
| `PlanStep` | 14 fields: `step_id`, `capability`, `params`, `depends_on`, `timeout_ms`, `has_side_effects`, etc. |
| `PlanAck` | `request_id`, `status`, `message` |
| `MicroReplanRequest` | `request_id`, `original_plan`, `completed_results`, `remaining_step_ids`, `failure_context`, `trace_id` |

Source of truth: `k1/fabric/types.py`

| Type | Used By |
|------|---------|
| `ScoredCapability` | SketchResult.capability_candidates, FabricRetrievalPort |
| `RetrievalResult` | IFabricRetrievalPort return type |

Source of truth: `k1/fabric/ports/state_reader.py`

| Type | Used By |
|------|---------|
| `SessionSnapshot` | IStateReadPort return type |

Source of truth: `k1/fabric/ports/event_port.py`

| Type | Used By |
|------|---------|
| `SubscriptionHandle` | IEventPort.subscribe return type |

---

## 4. Config Spec

**File**: `k1/planner/config.py` [F07]

```python
@dataclass(frozen=True)
class PlannerConfig:
    # Mailbox
    mailbox_max_depth: int = 5

    # Pipeline
    pipeline_timeout_ms: int = 45_000

    # Stage timeouts
    sketch_timeout_ms: int = 8_000
    expand_timeout_ms: int = 5_000
    validate_timeout_ms: int = 3_000
    commit_timeout_ms: int = 1_000

    # Token budgets
    sketch_max_tokens: int = 2_000
    expand_max_tokens: int = 1_000
    validate_max_tokens: int = 500
    total_token_budget: int = 3_500

    # LLM temperatures
    sketch_temperature: float = 0.7
    expand_temperature: float = 0.3
    validate_temperature: float = 0.2

    # Tool budget
    max_tool_calls_per_plan: int = 6

    # HIL
    max_hil_rounds: int = 2
    hil_clarification_timeout_ms: int = 60_000
    hil_approval_timeout_ms: int = 120_000

    # Micro-replan
    micro_replan_timeout_ms: int = 10_000
    micro_replan_max_tokens: int = 2_000
    micro_sketch_max_tokens: int = 1_024
    micro_sketch_timeout_ms: int = 5_000
    micro_expand_max_tokens: int = 512
    micro_expand_timeout_ms: int = 3_000
    micro_validate_max_tokens: int = 256
    micro_validate_timeout_ms: int = 2_000

    # Shutdown
    shutdown_grace_period_ms: int = 5_000
```

**Validation bounds** (for factory `_validate_config`):

| Field | Constraint |
|-------|-----------|
| `mailbox_max_depth` | >= 1 |
| `pipeline_timeout_ms` | > 0 |
| `max_tool_calls_per_plan` | >= 1 |
| `max_hil_rounds` | >= 0 |
| `total_token_budget` | > 0 |
| `sketch_timeout_ms` | > 0 |
| `expand_timeout_ms` | > 0 |
| `validate_timeout_ms` | > 0 |
| `commit_timeout_ms` | > 0 |
| `shutdown_grace_period_ms` | > 0 |

**Class method**: `from_dict(overrides: Dict[str, Any]) -> PlannerConfig`

---

## 5. Service Constructors

### 5.1 ToolCallRouter [F25]

**File**: `k1/planner/services/tool_call_router.py` (Layer 3, ~500 lines)

```python
class ToolCallRouter:
    __slots__ = ("_fabric_retrieval", "_state_read", "_bridge_port",
                 "_tool_call_count", "_config")

    def __init__(
        self,
        fabric_retrieval: IFabricRetrievalPort,
        state_read: IStateReadPort,
        bridge_port: IBridgePort,
        *,
        config: Optional[PlannerConfig] = None,
    ) -> None
```

**Ports consumed**: `IFabricRetrievalPort`, `IStateReadPort`, `IBridgePort`

**Routing table** (frozen, 4 tools + 1 schema lookup):

| Tool Name | Routes To | Counts Against PLAN-05 |
|-----------|-----------|----------------------|
| `discover_capabilities` | `_fabric_retrieval.discover_capabilities()` | Yes |
| `find_relevant_prompts` | `_fabric_retrieval.find_relevant_prompts()` | Yes |
| `query_planning_context` | `_state_read.read_sections()` | Yes |
| `recall_for_planning` | `_bridge_port.recall()` | Yes |
| `get_schema` (convenience) | `_fabric_retrieval.discover_capabilities(intent=name, top_k=1)` | **No** |

**Public methods**: `call(tool_name, **params)`, `discover()`, `find_prompts()`, `read_context()`, `recall_memory()`, `get_schema()`, `reset()`, `tool_call_count` property

**Budget**: PLAN-05 max 6 calls per plan (configurable via `config.max_tool_calls_per_plan`)

### 5.2 HILCoordinator [F26]

**File**: `k1/planner/services/hil_coordinator.py` (Layer 3, 575 lines)

```python
class HILCoordinator:
    __slots__ = ("_llm_port", "_event_port", "_config", "_round_count",
                 "_pending_request_id", "_hil_type", "_waiting")

    def __init__(
        self,
        llm_port: ILLMPort,
        event_port: IEventPort,
        config: Optional[PlannerConfig] = None,
    ) -> None
```

**Ports consumed**: `ILLMPort`, `IEventPort`

**Public methods**:
- `request_clarification(request_id, question_context) -> Optional[str]`
- `request_approval(request_id, plan_summary, side_effects, safety_assessment, estimated_duration_ms) -> str`
- `reset()`, `round_count` property

**Budget**: PLAN-10 max 2 HIL rounds (configurable via `config.max_hil_rounds`)

**Satisfies**: `HILCoordinatorLike` Protocol structurally

---

## 6. Stage Constructors

### 6.1 SketchService [F19]

**File**: `k1/planner/stages/sketch_service.py` (Layer 4, 1307 lines)

```python
class SketchService:
    __slots__ = ("_llm_port", "_tool_router", "_hil_coord")

    def __init__(
        self,
        llm_port: ILLMPort,
        tool_router: ToolCallRouterLike,
        hil_coord: HILCoordinatorLike,
    ) -> None
```

**Dependencies**: `ILLMPort` (direct), `ToolCallRouter` (via Protocol), `HILCoordinator` (via Protocol)

**Public methods**:
- `execute(request: PlanRequest, ctx: StageContext) -> SketchResult`
- `micro_execute(request: MicroReplanRequest, ctx: StageContext) -> SketchResult`

**Architecture**: Agentic tool-use (see Section 13)

### 6.2 ExpandService [F20]

**File**: `k1/planner/stages/expand_service.py` (Layer 4, 1562 lines)

```python
class ExpandService:
    __slots__ = ("_llm_port", "_tool_router")

    def __init__(
        self,
        llm_port: ILLMPort,
        tool_router: ExpandToolRouterLike,
    ) -> None
```

**Dependencies**: `ILLMPort` (direct), `ToolCallRouter` (via ExpandToolRouterLike Protocol)

**Public methods**:
- `execute(sketch_result, request, ctx, arbiter_feedback=None) -> ExpandedPlan`
- `micro_execute(micro_sketch_result, completed_results, ctx) -> ExpandedPlan`

**Architecture**: Agentic tool-use (see Section 13). No HIL.

### 6.3 ValidateService [F21]

**File**: `k1/planner/stages/validate_service.py` (Layer 4, 1216 lines)

```python
class ValidateService:
    __slots__ = ("_llm_port", "_fabric_retrieval", "_hil_coord")

    def __init__(
        self,
        llm_port: ILLMPort,
        fabric_retrieval: IFabricRetrievalPort,
        hil_coord: HILCoordinatorLike,
    ) -> None
```

**Dependencies**: `ILLMPort` (direct), `IFabricRetrievalPort` (direct -- NOT via ToolCallRouter), `HILCoordinator` (via Protocol)

**Public methods**:
- `execute(expanded_plan, request, ctx, cached_capabilities=None) -> ValidationVerdict`
- `micro_execute(expanded_plan, ctx, cached_capabilities=None, *, completed_step_ids=None) -> ValidationVerdict`

**Architecture**: NOT agentic. Two-phase (deterministic + LLM arbiter) + HIL approval.
Direct `IFabricRetrievalPort` access does NOT count against PLAN-05 tool budget.

### 6.4 CommitService [F23]

**File**: `k1/planner/stages/commit_service.py` (Layer 4, 538 lines)

```python
class CommitService:
    __slots__ = ("_bridge_port", "_delta_port", "_event_port")

    def __init__(
        self,
        bridge_port: IBridgePort,
        delta_port: IDeltaEmitPort,
        event_port: IEventPort,
    ) -> None
```

**Dependencies**: `IBridgePort`, `IDeltaEmitPort`, `IEventPort` -- **NO `ILLMPort`** (PLAN-03)

**Public methods**:
- `execute(expanded_plan, request, verdict, ctx) -> CommittedPlan`

**Architecture**: Zero LLM. Deterministic 11-step assembly. WAL persist is fire-and-forget.

---

## 7. Orchestrator Constructors

### 7.1 PipelineController [F03]

**File**: `k1/planner/pipeline_controller.py` (Layer 5, 1491 lines)

```python
class PipelineController:
    __slots__ = ("_sketch", "_expand", "_validate", "_commit",
                 "_delta_port", "_event_port", "_config", "_fsm",
                 "_stage_token_usage", "_stage_cost", "_stage_latency",
                 "_total_plan_tokens", "_tool_call_count", "_hil_round_count",
                 "_current_request", "_plan_start_time", "_revise_count",
                 "_active_cancel_check")

    def __init__(
        self,
        sketch: Any,
        expand: Any,
        validate: Any,
        commit: Any,
        delta_port: IDeltaEmitPort,
        event_port: IEventPort,
        config: PlannerConfig,
    ) -> None
```

**All 7 parameters are positional and required (no defaults).**

**Dependencies**: 4 stage services + `IDeltaEmitPort` + `IEventPort` + `PlannerConfig`

**Note**: Stage services typed as `Any` -- concrete types deferred. Factory is responsible for
passing correctly-typed stage instances.

**Public methods**:
- `execute(request: PlanRequest, cancel_check: Callable) -> CommittedPlan`
- `micro_replan(request: MicroReplanRequest, cancel_check: Callable) -> Optional[CommittedPlan]`
- `reset()`

**Properties**: `current_state`, `config`, `stage_token_usage`, `total_plan_tokens`,
`tool_call_count`, `hil_round_count`, `revise_count`, `plan_start_time`, `current_request`

### 7.2 PlannerAgent [F02]

**File**: `k1/planner/planner_agent.py` (Layer 6, 781 lines)

```python
class PlannerAgent:
    __slots__ = ("_mailbox", "_pipeline", "_event_port", "_config",
                 "_plan_lock", "_cancel_set", "_running",
                 "_subscriptions", "_in_flight_request_id")

    def __init__(
        self,
        mailbox: IMailboxPort,
        pipeline: PipelineController,
        event_port: IEventPort,
        config: PlannerConfig,
    ) -> None
```

**All 4 parameters are positional and required (no defaults).**

**IMPORTANT**: Parameter order is `(mailbox, pipeline, event_port, config)`.
Spec says `(pipeline, mailbox, event_port, config)` -- code wins.

**Dependencies**: `IMailboxPort`, `PipelineController`, `IEventPort`, `PlannerConfig`

**Public methods**:

| Method | Signature | Status |
|--------|-----------|--------|
| `start()` | `async def start(self) -> None` | Implemented -- INIT + crash recovery + dequeue loop |
| `stop()` | `async def stop(self) -> None` | Implemented -- full SHUTDOWN sequence |
| `on_cancel(request_id)` | `async def on_cancel(self, request_id: str) -> None` | Implemented |
| `micro_replan(request)` | `async def micro_replan(self, request: MicroReplanRequest) -> Optional[CommittedPlan]` | Implemented |

**Missing methods** (needed by factory, to be added):

| Method | Signature | Purpose |
|--------|-----------|---------|
| `get_mailbox()` | `def get_mailbox(self) -> IMailboxPort` | Kernel Phase 5 needs mailbox reference |
| `ready()` | `def ready(self) -> bool` | Post-wiring validation |
| `health()` | `def health(self) -> HealthStatus` | Post-wiring + runtime health check |

**Lifecycle**: `start()` subscribes 4 events and enters dequeue loop.
`stop()` executes 8-step shutdown with configurable grace period (default 5s).

---

## 8. Port-to-Service Wiring Matrix

This matrix shows which port each service receives at construction time.

```
                    Mailbox  LLM  FabricRet  StateRead  Bridge  DeltaEmit  Event   Config
                    -------  ---  ---------  ---------  ------  ---------  -----   ------
PlannerAgent         [X]                                                    [X]     [X]
PipelineController                                              [X]        [X]     [X]
SketchService                [X]  via TCR    via TCR   via TCR
ExpandService                [X]  via TCR              via TCR
ValidateService              [X]    [X]
CommitService                                          [X]     [X]        [X]
ToolCallRouter                      [X]       [X]      [X]                         [X]*
HILCoordinator               [X]                                          [X]     [X]*
```

`[X]` = direct port injection at construction.
`via TCR` = accessed through ToolCallRouter (not directly injected).
`[X]*` = optional config param (defaults to `PlannerConfig()`).

**Port instance sharing**:
- `ILLMPort` -- shared by SketchService, ExpandService, ValidateService, HILCoordinator (4 consumers)
- `IFabricRetrievalPort` -- shared by ToolCallRouter (via discover/find_prompts) AND ValidateService (direct)
- `IEventPort` -- shared by PlannerAgent, PipelineController, CommitService, HILCoordinator (4 consumers)
- `IDeltaEmitPort` -- shared by PipelineController and CommitService (2 consumers)
- `IBridgePort` -- shared by ToolCallRouter and CommitService (2 consumers)
- `ToolCallRouter` -- shared by SketchService and ExpandService (2 consumers)
- `HILCoordinator` -- shared by SketchService and ValidateService (2 consumers)

---

## 9. 10-Step Wiring Sequence

This is the EXACT construction order for `factory._wire()`, using actual
constructor signatures from code. Each step references only objects
already created in prior steps.

```python
@staticmethod
async def _wire(
    llm_port: ILLMPort,
    fabric_port: IFabricRetrievalPort,
    state_port: IStateReadPort,
    bridge_port: IBridgePort,
    delta_port: IDeltaEmitPort,
    event_port: IEventPort,
    mailbox_port: IMailboxPort,
    config: PlannerConfig,
) -> PlannerAgent:

    # Step 1: Leaf service -- routes tool calls to 3 backend ports
    tool_router = ToolCallRouter(
        fabric_retrieval=fabric_port,
        state_read=state_port,
        bridge_port=bridge_port,
        config=config,
    )

    # Step 2: Leaf service -- manages HIL question/approval flow
    hil_coord = HILCoordinator(
        llm_port=llm_port,
        event_port=event_port,
        config=config,
    )

    # Step 3: Stage -- agentic sketch with tool-use
    sketch = SketchService(
        llm_port=llm_port,
        tool_router=tool_router,
        hil_coord=hil_coord,
    )

    # Step 4: Stage -- agentic expand with tool-use (no HIL)
    expand = ExpandService(
        llm_port=llm_port,
        tool_router=tool_router,
    )

    # Step 5: Stage -- deterministic + LLM arbiter validation
    validate = ValidateService(
        llm_port=llm_port,
        fabric_retrieval=fabric_port,
        hil_coord=hil_coord,
    )

    # Step 6: Stage -- zero LLM, deterministic assembly (PLAN-03)
    commit = CommitService(
        bridge_port=bridge_port,
        delta_port=delta_port,
        event_port=event_port,
    )

    # Step 7: Orchestrator -- 4-stage pipeline
    pipeline = PipelineController(
        sketch=sketch,
        expand=expand,
        validate=validate,
        commit=commit,
        delta_port=delta_port,
        event_port=event_port,
        config=config,
    )

    # Step 8: Top-level agent
    agent = PlannerAgent(
        mailbox=mailbox_port,
        pipeline=pipeline,
        event_port=event_port,
        config=config,
    )

    # Step 9: INIT phase -- subscribe events, FSM -> IDLE, enter dequeue loop
    await agent.start()

    # Step 10: Return initialized agent
    return agent
```

**Invariants enforced by step order**:
- Step 6 (CommitService) has no `ILLMPort` parameter -- PLAN-03 is structural
- Steps 1-2 (leaf services) are created before steps 3-5 (stages that depend on them)
- Step 7 (PipelineController) depends on all 4 stages
- Step 8 (PlannerAgent) depends on PipelineController
- Step 9 must complete before Step 10 returns

---

## 10. Adapter Registry

### 10.1 Production Adapters

**Directory**: `k1/planner/adapters/` [F27]

| Adapter | File | Port | Constructor | Wraps |
|---------|------|------|-------------|-------|
| `MailboxAdapter` | `mailbox_adapter.py` [F28] | `IMailboxPort` | `(max_depth=5, priority_class="INTERACTIVE")` | `asyncio.Queue` |
| `LLMGatewayAdapter` | `llm_gateway_adapter.py` [F29] | `ILLMPort` | `(llm_request_bus, consumer_id="planner")` | `ILLMRequestBus` (V2 only) |
| `FabricRetrievalAdapter` | `fabric_retrieval_adapter.py` [F30] | `IFabricRetrievalPort` | `(fabric_retrieval, timeout_ms=50, max_retries=1)` | `FabricRetrieval` API |
| `SessionStateReadAdapter` | `session_state_adapter.py` [F31] | `IStateReadPort` | `(reader, session_id: str)` | `ISessionStateReader` |
| `BridgeAdapter` | `bridge_adapter.py` [F32] | `IBridgePort` | `(bridge_port)` | Fabric `IBridgePort` |
| `DeltaBusAdapter` | `delta_bus_adapter.py` [F33] | `IDeltaEmitPort` | `(delta_bus, agent_id="planner")` | `IDeltaBusPort` |
| `EventBusAdapter` | `event_bus_adapter.py` [F34] | `IEventPort` | `(event_port)` | Fabric `IEventPort` |

**V1**: `LLMGatewayAdapter` is NOT used. V1 uses `TestLLMAdapter` in all environments.

### 10.2 Test Adapters

**Directory**: `tests/k1/planner/adapters/`

| Adapter | Port | Constructor |
|---------|------|-------------|
| `TestMailboxAdapter` | `IMailboxPort` | `(preset_requests: Optional[List[PlanRequest]] = None)` |
| `TestLLMAdapter` | `ILLMPort` | `(stage_responses=None, error_stages=None, latency_ms=0, default_response=None)` |
| `TestFabricRetrievalAdapter` | `IFabricRetrievalPort` | `(preset_capabilities=None, preset_prompts=None)` |
| `TestStateReadAdapter` | `IStateReadPort` | `(preset_snapshot=None, preset_sections=None)` |
| `TestBridgeAdapter` | `IBridgePort` | `(preset_recall=None, available=True)` |
| `TestDeltaAdapter` | `IDeltaEmitPort` | `()` (no args) |
| `TestEventAdapter` | `IEventPort` | `()` (no args) |

**Import path**: `from tests.k1.planner.adapters import TestMailboxAdapter, ...`

**Factory usage**: `create_for_testing()` and `create_with_ports()` use deferred imports
to prevent production code from depending on test code.

---

## 11. Event Topic Registry

**File**: `k1/planner/events.py` [F06]

### 11.1 Published by Planner (7 topics)

| Constant | Topic String | Payload | Emitter |
|----------|-------------|---------|---------|
| `TOPIC_PLAN_READY` | `k1.planner.plan.ready.v1` | `CommittedPlan.to_dict()` | CommitService |
| `TOPIC_PLAN_FAILED` | `k1.planner.plan.failed.v1` | `PlanFailedPayload` | PipelineController |
| `TOPIC_PLAN_CANCELLED` | `k1.planner.plan.cancelled.v1` | `PlanCancelledPayload` | PipelineController |
| `TOPIC_MICRO_REPLAN_READY` | `k1.planner.micro_replan.ready.v1` | `CommittedPlan.to_dict()` | PipelineController |
| `TOPIC_DELTA` | `k1.planner.delta.v1` | `DeltaPayload` | PipelineController |
| `TOPIC_HIL_CLARIFICATION` | `k1.hil.clarification.v1` | `HILClarificationPayload` | HILCoordinator |
| `TOPIC_HIL_APPROVAL_REQ` | `k1.hil.approval_request.v1` | `HILApprovalRequestPayload` | HILCoordinator |

### 11.2 Subscribed by Planner (4 topics)

| Constant | Topic String | Handler | Subscriber |
|----------|-------------|---------|------------|
| `TOPIC_PLAN_REQUEST` | `k1.planner.plan.request.v1` | `_on_plan_request` | PlannerAgent |
| `TOPIC_PLAN_CANCEL` | `k1.planner.plan.cancel.v1` | `_on_plan_cancel` | PlannerAgent |
| `TOPIC_HIL_CLARIFICATION_RESP` | `k1.hil.clarification_response.v1` | `_on_hil_clarification` | PlannerAgent (stub) |
| `TOPIC_HIL_APPROVAL_RESP` | `k1.hil.approval_response.v1` | `_on_hil_approval` | PlannerAgent (stub) |

### 11.3 Event Payload Dataclasses

| Payload | Fields |
|---------|--------|
| `PlanFailedPayload` | `request_id`, `stage`, `error_code`, `error_message`, `tokens_used`, `duration_ms`, `trace_id`, `partial_state` |
| `PlanCancelledPayload` | `request_id`, `reason`, `stage`, `trace_id` |
| `HILClarificationPayload` | `request_id`, `question`, `context`, `trace_id` |
| `HILApprovalRequestPayload` | `request_id`, `summary`, `options`, `side_effects`, `safety_assessment` |

---

## 12. Hard Invariants Checklist

| ID | Rule | Enforcement Point |
|----|------|-------------------|
| **PLAN-01** | Never writes SessionState | `IStateReadPort` has no write method. Port Protocol enforced at type level. |
| **PLAN-02** | Read-only tools only | `ToolCallRouter` routing table has read-only tools. No execute/invoke routes. |
| **PLAN-03** | COMMIT is zero LLM | `CommitService.__init__` has no `ILLMPort` parameter. Structural enforcement. |
| **PLAN-04** | 45s max pipeline timeout | `PipelineController._check_timeout()` against `config.pipeline_timeout_ms`. |
| **PLAN-05** | Max 6 tool calls per plan | `ToolCallRouter.tool_call_count` checked per call. `get_schema` exempt. |
| **PLAN-06** | Never executes capabilities | `IFabricRetrievalPort` has no `invoke_capability()`. Port level. |
| **PLAN-07** | Token/cost budget | V2 deferred. V1: per-stage token limits via `RequestConstraints`. |
| **PLAN-08** | All capabilities must exist | `ValidateService` Phase 1 checks via `IFabricRetrievalPort.discover_capabilities(intent=name, top_k=1)`. |
| **PLAN-09** | Plan must be DAG | `ValidateService` Phase 1: Kahn's algorithm cycle detection. `ExpandService._remove_cycles()` defensive cleanup. |
| **PLAN-10** | Max 2 HIL rounds | `HILCoordinator.round_count` checked against `config.max_hil_rounds`. |
| **PLAN-11** | All LLM calls carry budget | `RequestConstraints` mandatory field on every `HubRequest`. |
| **PLAN-12** | Micro-replan adjusts remaining only | `PipelineController._enforce_plan12()` validates scope. |

**Factory-level enforcement**: Step 6 of `_wire()` constructs `CommitService` without `ILLMPort`.
This is not a runtime check -- it is a structural guarantee. The factory is the ONLY
construction site, so PLAN-03 compliance is provable by inspection.

---

## 13. Agentic Tool-Use Architecture

The stages moved from prompt injection (slot-based context pre-fetching) to agentic tool-use.
This is the "huge change" -- the LLM now decides what context to gather through tool calls.

### 13.1 How It Works

1. **System prompt** teaches a universal planning methodology (no domain-specific slots)
2. **Tool definitions** provided in OpenAI function-calling format (`tools` param)
3. **Agentic loop** (`_run_agentic_loop`) runs up to 6 rounds:
   - Send messages + tools to LLM via `ILLMPort.execute()`
   - If LLM returns tool calls: dispatch each via `ToolCallRouter`, feed results back
   - If LLM returns final JSON content: parse, validate, return result
4. **Tool dispatch** (`_dispatch_tool_call`) routes each call through `ToolCallRouter`
5. **Final output** must conform to a JSON Schema (`*_OUTPUT_SCHEMA` constant)

### 13.2 Tool Definitions by Stage

**SKETCH** (4 tools in `SKETCH_TOOL_DEFINITIONS`):

| Tool | Routes To | Purpose |
|------|-----------|---------|
| `discover_capabilities` | `tool_router.discover()` | Find system capabilities matching intent |
| `query_session_context` | `tool_router.read_context()` | Read session state sections |
| `recall_long_term_memory` | `tool_router.recall_memory()` | Query K0 long-term memory |
| `find_prompts` | `tool_router.find_prompts()` | Find relevant prompt templates |

**EXPAND** (4 tools in `EXPAND_TOOL_DEFINITIONS`):

| Tool | Routes To | Purpose |
|------|-----------|---------|
| `discover_capabilities` | `tool_router.discover()` | Refined capability discovery |
| `get_capability_schema` | `tool_router.get_schema()` | Full capability contract lookup |
| `find_prompts` | `tool_router.find_prompts()` | Find prompt templates |
| `query_session_context` | `tool_router.read_context()` | Read session context |

**VALIDATE**: NOT agentic. Uses `IFabricRetrievalPort` directly (not tools).
**COMMIT**: NOT agentic. Zero LLM. Pure deterministic assembly.

### 13.3 Factory Implication

The factory does NOT need to know about tool definitions or agentic loops.
It wires ports and services; the stages handle their own tool-use internally.
The only factory concern is ensuring `ToolCallRouter` satisfies both
`ToolCallRouterLike` (SKETCH) and `ExpandToolRouterLike` (EXPAND) -- which it
does structurally.

---

## 14. Discrepancies Plan vs Code

These divergences were found between `planner.md` / `planner-implementation-plan.md`
and the actual code. **Code is authoritative for factory wiring.**

| # | Area | Plan Says | Code Actually Has | Resolution |
|---|------|-----------|-------------------|------------|
| 1 | PlannerAgent param order | `(pipeline, mailbox, event_port, config)` | `(mailbox, pipeline, event_port, config)` | Use code order |
| 2 | PipelineController params | 6 params (some plan references) | 7 params (includes `config: PlannerConfig`) | Use code: 7 params |
| 3 | ToolCallRouter config | Not mentioned in plan wiring | `*, config: Optional[PlannerConfig] = None` | Pass `config` from factory |
| 4 | HILCoordinator config | Not mentioned in plan wiring | `config: Optional[PlannerConfig] = None` | Pass `config` from factory |
| 5 | ExpandService tool_router type | `ToolCallRouter` | `ExpandToolRouterLike` (Protocol) | ToolCallRouter satisfies it |
| 6 | SketchService tool_router type | `ToolCallRouter` | `ToolCallRouterLike` (Protocol) | ToolCallRouter satisfies it |
| 7 | PlannerAgent.ready() | Required by factory | **Does not exist** | Must add before factory |
| 8 | PlannerAgent.health() | Required by factory | **Does not exist** | Must add before factory |
| 9 | PlannerAgent.get_mailbox() | Required by kernel Phase 5 | **Does not exist** | Must add before factory |
| 10 | PlannerAgent.shutdown() | Method name in plan | Method is `stop()` in code | Use `stop()` |
| 11 | ValidateService.fabric_retrieval | Plan: via ToolCallRouter | Code: direct `IFabricRetrievalPort` injection | Use direct injection |
| 12 | Stage typing | Plan: concrete types | Code: `__slots__` + Protocol-typed deps | Code prevents tight coupling |
| 13 | create_for_testing return | Plan: `(PlannerAgent, Dict[str, adapter])` | N/A (not built yet) | Follow plan: return tuple |

---

## 15. Factory Requirements Summary

### 15.1 File

`k1/planner/factory.py` [F08] -- Layer 7 (imports from ALL layers)

### 15.2 Class

```python
class PlannerFactory:
    """Pure static factory -- no instance state."""
```

### 15.3 Three Creation Modes

| Method | Signature | Returns | Purpose |
|--------|-----------|---------|---------|
| `create_standalone` | `(llm_port, fabric_port, state_port, bridge_port, delta_port, event_port, mailbox_port, config=PlannerConfig())` | `PlannerAgent` | Production (kernel Phase 5) |
| `create_for_testing` | `(config=PlannerConfig(), **overrides)` | `Tuple[PlannerAgent, Dict[str, Any]]` | Integration tests |
| `create_with_ports` | `(ports: Dict[str, Any], config=PlannerConfig())` | `PlannerAgent` | Unit tests (selective injection) |

### 15.4 Internal Methods

| Method | Purpose |
|--------|---------|
| `_wire(ports, config)` | 10-step object graph construction (Section 9) |
| `_validate_ports(ports)` | Protocol compliance + completeness + no duplicates |
| `_validate_config(config)` | Bounds checking on PlannerConfig fields |

### 15.5 Validation Rules

1. **Protocol compliance**: `isinstance(port, PortProtocol)` for all 7 using `@runtime_checkable`
2. **Completeness**: all 7 ports non-None -> `MissingPortError`
3. **No duplicates**: no two port slots share same `id()` -> `DuplicatePortError`
4. **Config bounds**: Section 4 constraints -> `InvalidConfigError`
5. **Post-wiring**: `agent.ready() == True` and `agent.health().status == "HEALTHY"` -> `PlannerInitError`

### 15.6 Prerequisites (must exist before factory can be built)

| Prerequisite | Status | Location |
|-------------|--------|----------|
| All 7 port Protocols | Done | `k1/planner/ports/` |
| All 7 production adapters | Done | `k1/planner/adapters/` |
| All 7 test adapters | Done | `tests/k1/planner/adapters/` |
| ToolCallRouter | Done | `k1/planner/services/tool_call_router.py` |
| HILCoordinator | Done | `k1/planner/services/hil_coordinator.py` |
| All 4 stage services | Done | `k1/planner/stages/` |
| PipelineController | Done | `k1/planner/pipeline_controller.py` |
| PlannerAgent | Done | `k1/planner/planner_agent.py` |
| PlannerConfig | Done | `k1/planner/config.py` |
| PlannerAgent.ready() | **TODO** | `k1/planner/planner_agent.py` |
| PlannerAgent.health() | **TODO** | `k1/planner/planner_agent.py` |
| PlannerAgent.get_mailbox() | **TODO** | `k1/planner/planner_agent.py` |
| Factory error types | **TODO** | `k1/planner/types.py` |

### 15.7 Import Map for factory.py

```python
# Layer 0
from k1.planner.config import PlannerConfig
from k1.planner.types import (
    PlannerError, InvalidPortError, MissingPortError,
    DuplicatePortError, InvalidConfigError, PlannerInitError,
)

# Layer 1
from k1.planner.ports import (
    IMailboxPort, ILLMPort, IFabricRetrievalPort,
    IStateReadPort, IBridgePort, IDeltaEmitPort, IEventPort,
)

# Layer 3
from k1.planner.services.tool_call_router import ToolCallRouter
from k1.planner.services.hil_coordinator import HILCoordinator

# Layer 4
from k1.planner.stages.sketch_service import SketchService
from k1.planner.stages.expand_service import ExpandService
from k1.planner.stages.validate_service import ValidateService
from k1.planner.stages.commit_service import CommitService

# Layer 5
from k1.planner.pipeline_controller import PipelineController

# Layer 6
from k1.planner.planner_agent import PlannerAgent

# Test adapters (deferred import inside create_for_testing / create_with_ports)
# from tests.k1.planner.adapters import (
#     TestMailboxAdapter, TestLLMAdapter, TestFabricRetrievalAdapter,
#     TestStateReadAdapter, TestBridgeAdapter, TestDeltaAdapter, TestEventAdapter,
# )
```

---

*End of Planner Implemented Spec*
