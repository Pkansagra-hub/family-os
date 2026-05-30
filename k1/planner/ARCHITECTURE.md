# K1 Planner — Architecture Document

> **Epic**: E-0.6 · **Generated**: 2025-07-02 · **Source**: Full code scan of 34 .py files (~10,500 lines) + 2 diagrams + 39 test files
> **Component**: K1 L3 LLM-Powered Planning Engine
> **Layer**: Hexagonal / Ports-and-Adapters

---

## §1 Port Surface (7 Ports)

All 7 ports are `Protocol` classes with `@runtime_checkable`. No ABC used.
Import path: `k1.planner.ports`.

### §1.1 Port Inventory

| # | Port | File | Methods | Cross-Component Imports |
|---|------|------|---------|------------------------|
| 1 | `IMailboxPort` | `mailbox_port.py` (90 lines) | `enqueue`, `dequeue`, `send_cancel`, `drain`, `micro_replan` | `PlanRequest`, `MicroReplanRequest`, `CommittedPlan` ← `k1.orchestrator.types` |
| 2 | `ILLMPort` | `llm_port.py` (60 lines) | `execute` | `HubRequest`, `HubResponse` ← `k1.planner.types` (local) |
| 3 | `IFabricRetrievalPort` | `fabric_retrieval_port.py` (83 lines) | `discover_capabilities`, `find_relevant_prompts` | `RetrievalResult` ← `k1.fabric.types` |
| 4 | `IStateReadPort` | `state_read_port.py` (64 lines) | `read_sections` | `SessionSnapshot` ← `k1.fabric.ports.state_reader` |
| 5 | `IBridgePort` | `bridge_port.py` (81 lines) | `recall`, `persist_plan` | `CommittedPlan` ← `k1.orchestrator.types`; `RecallResponse` ← `k1.planner.types` |
| 6 | `IDeltaEmitPort` | `delta_emit_port.py` (58 lines) | `emit` | `DeltaPayload` ← `k1.planner.types` |
| 7 | `IEventPort` | `event_port.py` (101 lines) | `emit`, `subscribe`, `unsubscribe` | `SubscriptionHandle` ← `k1.fabric.ports.event_port` |

### §1.2 Full Method Signatures

#### IMailboxPort

```python
async def enqueue(self, request: PlanRequest) -> None           # raises MailboxFullError
async def dequeue(self) -> PlanRequest                           # blocking FIFO
async def send_cancel(self, request_id: str) -> None             # best-effort signal
def drain(self) -> List[PlanRequest]                             # sync, non-blocking
async def micro_replan(self, request: MicroReplanRequest) -> CommittedPlan
```

#### ILLMPort

```python
async def execute(self, request: HubRequest) -> HubResponse
```

#### IFabricRetrievalPort

```python
async def discover_capabilities(self, domain=None, intent="", safety_band="GREEN",
    session_context=None, top_k=10) -> RetrievalResult
async def find_relevant_prompts(self, intent="", domain=None,
    safety_band="GREEN", top_k=10) -> RetrievalResult
```

#### IStateReadPort

```python
async def read_sections(self, sections: List[str], trace_id: str = "") -> SessionSnapshot
```

#### IBridgePort

```python
async def recall(self, query: str, selectors: Optional[List[str]] = None,
    *, trace_id: str = "") -> RecallResponse
async def persist_plan(self, plan: CommittedPlan, *, trace_id: str = "") -> None
```

#### IDeltaEmitPort

```python
def emit(self, delta: DeltaPayload) -> None                     # sync, fire-and-forget
```

#### IEventPort

```python
def emit(self, topic: str, payload: Any) -> None                # sync
def subscribe(self, topic: str, handler: Callable) -> SubscriptionHandle
def unsubscribe(self, handle: SubscriptionHandle) -> bool
```

### §1.3 Design Rules

- **PLAN-01**: `IStateReadPort` has NO write methods — read-only by construction.
- **PLAN-03**: `CommitService` has NO `ILLMPort` — zero LLM in Stage 4 by construction.
- **PLAN-06**: `IFabricRetrievalPort` has NO execute methods — discovery only.
- All ports use `Protocol` (structural typing), enabling test doubles without inheritance.
- `IEventPort` re-uses `SubscriptionHandle` from `k1.fabric.ports.event_port` (interface identity).

---

## §2 Internal Architecture

### §2.1 Component Topology (6 Layers)

```
Layer 6  PlannerAgent            (planner_agent.py — 733 lines)
Layer 5  PipelineController      (pipeline_controller.py — 1301 lines)
Layer 4  Stage Services          (stages/ — 4006 lines total)
Layer 3  Cross-Cutting Services  (services/ — 834 lines total)
Layer 2  Adapters                (adapters/ — 848 lines total)
Layer 1  Ports                   (ports/ — 537 lines total)
Layer 0  Types + Config          (types.py, events.py, config.py — 1151 lines total)
```

Import rule: Each layer imports ONLY from lower layers. Stages never import each other.

### §2.2 PlanStateMachine (plan_fsm.py — 273 lines)

**11 states** (PlanState enum):

| State | Category | Description |
|-------|----------|-------------|
| `IDLE` | Rest | No plan in progress |
| `SKETCHING` | Full pipeline | Stage 1 — discovery + LLM sketch |
| `EXPANDING` | Full pipeline | Stage 2 — tool mapping + LLM expand |
| `VALIDATING` | Full pipeline | Stage 3 — deterministic + LLM arbiter + HIL |
| `COMMITTING` | Shared | Stage 4 — plan assembly + WAL + event (shared with micro) |
| `MICRO_SKETCH` | Micro-replan | µStage 1 — re-sketch remaining steps |
| `MICRO_EXPAND` | Micro-replan | µStage 2 — re-map tools |
| `MICRO_VALIDATE` | Micro-replan | µStage 3 — validate replacements |
| `COMPLETED` | Terminal | Plan delivered |
| `FAILED` | Terminal | Unrecoverable failure |
| `CANCELLED` | Terminal | Cancelled by Orchestrator |

**Properties**: `is_terminal`, `is_micro`, `is_active`.

**23 transition edges** (TRANSITION_TABLE):

| From | Legal Targets |
|------|---------------|
| IDLE | SKETCHING, MICRO_SKETCH |
| SKETCHING | EXPANDING, FAILED, CANCELLED |
| EXPANDING | VALIDATING, FAILED, CANCELLED |
| VALIDATING | COMMITTING, EXPANDING (revise ×1), FAILED, CANCELLED |
| COMMITTING | COMPLETED, CANCELLED |
| COMPLETED | IDLE |
| FAILED | IDLE |
| CANCELLED | IDLE |
| MICRO_SKETCH | MICRO_EXPAND, FAILED |
| MICRO_EXPAND | MICRO_VALIDATE, FAILED |
| MICRO_VALIDATE | COMMITTING, FAILED |

**Bypass methods**: `force_failed()` and `force_cancelled()` skip TRANSITION_TABLE, work from any active state, no-op if already terminal. `reset()` only from terminal → IDLE.

### §2.3 PipelineController (pipeline_controller.py — 1301 lines)

Central stage sequencer. Owns FSM, budget tracking, cancel checking, delta emission. Does NOT perform LLM calls, tool discovery, or HIL interaction.

**Constructor** (7 injected dependencies):

```python
PipelineController(sketch, expand, validate, commit,
    delta_port: IDeltaEmitPort, event_port: IEventPort, config: PlannerConfig)
```

#### Full Pipeline Flow (execute)

```
IDLE → SKETCHING → EXPANDING → VALIDATING → COMMITTING → COMPLETED
         ↑                         │
         └── revise loop (max 1) ──┘
```

| Step | FSM | Action | Cancel | Timeout |
|------|-----|--------|--------|---------|
| 1 | — | `reset()`, set request/start_time | — | — |
| 2 | IDLE→SKETCHING | — | — | — |
| 3 | — | `await sketch.execute(request, ctx)` | — | — |
| 4 | — | cancel + timeout check | **CP-2** | PLAN-04 |
| 5 | SKETCHING→EXPANDING | — | — | — |
| 6 | — | `await expand.execute(sketch_result, ctx)` | — | — |
| 7 | — | cancel + timeout check | **CP-3** | PLAN-04 |
| 8 | EXPANDING→VALIDATING | — | — | — |
| 9 | — | `await validate.execute(expanded, ctx)` | — | — |
| 10 | — | verdict routing (see below) | — | — |
| 11 | VALIDATING→COMMITTING | cancel + timeout check | **CP-4** | PLAN-04 |
| 12 | — | `await commit.execute(expanded, verdict, ctx)` | — | — |
| 13 | COMMITTING→COMPLETED | emit plan_end delta | — | — |

**Verdict routing** (step 10):

| Verdict | Revise Count | Action |
|---------|-------------|--------|
| APPROVED | any | → COMMIT |
| REVISE/REJECT | 0 | increment revise_count, FSM→EXPANDING, loop back |
| REVISE | 1 | treat as approved → COMMIT |
| REJECT | 1 | `force_failed()` + raise `ValidateRejectedError` |

#### Micro-Replan Pipeline (micro_replan)

```
IDLE → MICRO_SKETCH → MICRO_EXPAND → MICRO_VALIDATE → COMMITTING → COMPLETED
```

Key differences from full pipeline:

- **10s timeout** (vs 45s), ~2K tokens (vs ~3.5K)
- Max 3 tool calls (vs 6)
- **No HIL**, no revise loop
- REVISE verdict → treated as APPROVED (best-effort)
- REJECT verdict → `force_failed()` + return `None`
- ALL failures → return `None` (no `plan.failed.v1` event)
- Delivery: synchronous return, not event bus
- `_enforce_plan12()` strips completed-step overlaps + dangling deps

#### Per-Plan State Tracking

| Slot | Type | Purpose |
|------|------|---------|
| `_stage_token_usage` | `Dict[str, int]` | Per-stage token counts |
| `_stage_cost` | `Dict[str, float]` | Per-stage cost |
| `_stage_latency` | `Dict[str, int]` | Per-stage latency (ms) |
| `_total_plan_tokens` | `int` | Cumulative tokens |
| `_tool_call_count` | `int` | Tool calls consumed |
| `_hil_round_count` | `int` | HIL rounds consumed |
| `_revise_count` | `int` | EXPAND revise loops consumed |

#### Cancel Handling (_check_cancel)

At each checkpoint: `force_cancelled()` → emit `plan.cancelled.v1` → emit delta → raise `PlanCancelledError`.

#### Timeout (_check_timeout)

`elapsed_ms > config.pipeline_timeout_ms` → `force_failed("pipeline_timeout")` → emit `plan.failed.v1{PIPELINE_TIMEOUT}` → raise `PlannerError`.

#### Delta Emission Points

| Method | Delta Type | Trigger |
|--------|-----------|---------|
| `_on_fsm_transition()` | `stage_transition` | Every FSM transition |
| `_check_cancel()` | `plan_cancelled` | Between-stage cancel |
| `_emit_plan_end_delta()` | `plan_end` | Pipeline completion |
| `_emit_micro_replan_started_delta()` | `micro_replan` | Start of micro-replan |

### §2.4 PlannerAgent (planner_agent.py — 733 lines)

Single-threaded async coordinator. Entry point of the module.

**Constructor** (4 dependencies):

```python
PlannerAgent(mailbox: IMailboxPort, pipeline: PipelineController,
    event_port: IEventPort, config: PlannerConfig)
```

**Concurrency**: `asyncio.Lock` — V1 single-plan-at-a-time. Micro-replan also acquires this lock.

#### Mailbox Loop (_run_loop)

```python
while self._running:
    request = await mailbox.dequeue()           # blocks FIFO
    if request_id in _cancel_set: skip          # CP-1 pre-check
    async with _plan_lock:
        cancel_check = lambda: request_id in _cancel_set
        await pipeline.execute(request, cancel_check)
    finally:
        pipeline.reset(), _cancel_set.discard()
```

Error handling: `PlanCancelledError` → already handled; `PlannerError` → already handled; unexpected `Exception` → emit `plan.failed.v1{INTERNAL_ERROR}`.

#### Cancel Checkpoints (5 total)

| # | Location | Mechanism |
|---|----------|-----------|
| 1 | _run_loop pre-check | request_id in cancel_set before lock |
| 2 | Between SKETCH→EXPAND | PipelineController._check_cancel() |
| 3 | Between EXPAND→VALIDATE | PipelineController._check_cancel() |
| 4 | Between VALIDATE→COMMIT | PipelineController._check_cancel() |
| 5 | Before WAL persist | CommitService responsibility |

#### Event Subscriptions (4 topics at start())

| Topic | Handler | Behavior |
|-------|---------|----------|
| `plan.request.v1` | `_on_plan_request()` | Parse + schedule enqueue |
| `plan.cancel.v1` | `_on_plan_cancel()` | Add to cancel set |
| `hil.clarification_response.v1` | `_on_hil_clarification()` | **V1 stub** — logs, discards |
| `hil.approval_response.v1` | `_on_hil_approval()` | **V1 stub** — logs, discards |

#### Lifecycle

| Phase | Actions |
|-------|---------|
| **INIT** | Validate wiring, subscribe 4 topics |
| **START** | Reset pipeline + cancel set, crash recovery (V1 no-op) |
| **RUN** | Enter dequeue loop |
| **SHUTDOWN** (8 steps) | _running=False → drain mailbox (cancel each) → cancel in-flight → inject sentinel → safety-release lock → unsubscribe all |

### §2.5 Stage Services

All stages are Layer 4. They import Layer 0 types + Layer 1 ports only. Stages NEVER import each other.

#### §2.5.1 SketchService (sketch_service.py — 1132 lines)

**Injected**: `ILLMPort`, `ToolCallRouterLike`, `HILCoordinatorLike`

**Full execute**: Agentic loop (up to 6 rounds). Error recovery: retry simplified (no tools) → raise `SketchFailedError`.

**Micro execute**: Single attempt, no HIL, no retry.

**4 Discovery Tools** (via ToolCallRouter):

| LLM Tool Name | Router Method | Port |
|----------------|--------------|------|
| `discover_capabilities` | `tool_router.discover()` | IFabricRetrievalPort |
| `query_session_context` | `tool_router.read_context()` | IStateReadPort |
| `recall_long_term_memory` | `tool_router.recall_memory()` | IBridgePort |
| `find_prompts` | `tool_router.find_prompts()` | IFabricRetrievalPort |

**LLM Call**: capability=`CHAT`, temperature=0.7, max_tokens=2048, timeout=8s.

**Output Schema** (SKETCH_OUTPUT_SCHEMA):

```json
{
  "rough_steps": [{"intent": "str", "suggested_capability?": "str", "depends_on?": ["int"]}],
  "rationale": "str",
  "needs_clarification": "bool",
  "clarification_question?": "str"
}
```

**HIL Integration**: If `needs_clarification=True` AND `clarification_question` non-empty → HILCoordinator.request_clarification() → re-run with addendum (max 1 round).

**Cancel**: At start of each agentic loop round.

#### §2.5.2 ExpandService (expand_service.py — 1357 lines)

**Injected**: `ILLMPort`, `ExpandToolRouterLike` (NO HILCoordinator)

**Full execute**: Agentic loop (up to 6 rounds). Error recovery: retry simplified → fallback to degraded plan.

**Micro execute**: Single attempt, no retry, no fallback.

**4 Discovery Tools** (different from SKETCH):

| LLM Tool Name | Router Method | Port |
|----------------|--------------|------|
| `discover_capabilities` | `tool_router.discover()` (top_k=5) | IFabricRetrievalPort |
| `get_capability_schema` | `tool_router.get_schema()` | IFabricRetrievalPort |
| `find_prompts` | `tool_router.find_prompts()` | IFabricRetrievalPort |
| `query_session_context` | `tool_router.read_context()` | IStateReadPort |

**Note**: No `recall_long_term_memory`. Adds `get_capability_schema`.

**LLM Call**: capability=`CHAT`, temperature=0.3, max_tokens=1024, timeout=5s.

**Output Schema** (EXPAND_OUTPUT_SCHEMA):

```json
{
  "steps": [{
    "id": "s<digits>", "capability": "str", "params": {}, "deps?": ["str"],
    "prompt_template?": "str", "tools_granted?": ["str"],
    "output_schema?": {}, "is_optional?": "bool"
  }],
  "dependencies": {"step_id": ["predecessor_ids"]},
  "rationale": "str"
}
```

**Post-LLM Enrichment** (_enrich_steps): Fills infrastructure fields from CapabilityContract metadata: `has_side_effects`, `compensation`, `timeout_ms`, `required_context`, `safety_band_min`, `output_schema`, and contract-backed `activity_profile`.

**Prompt binding validation**: `prompt_template` is preserved only when it exactly matches a name returned by `find_prompts` or an injected prompt inventory. Invalid names are cleared and logged. EXPAND does not select replacements from domain text, prompt scores, compatible metadata, or capability-name tokens.

**Degraded plan fallback**: PlanStep with `capability=UNRESOLVED`, `params={}`, `timeout_ms=10000`.

**Cycle removal**: DFS finds back edges in dependency graph, removes them (logs warning).

#### §2.5.3 ValidateService (validate_service.py — 1063 lines)

**Injected**: `ILLMPort`, `IFabricRetrievalPort` (direct, NOT via ToolCallRouter), `HILCoordinatorLike`

**Full execute**: Phase 1 (deterministic) → Phase 2 (LLM arbiter) → Phase 3 (optional HIL approval).

**Micro execute**: Phase 1 + Phase 2 only. No HIL, no revise. "revise" → "approved" (best-effort).

**Zero tool calls** — does not use ToolCallRouter. Does not count against PLAN-05.

**Phase 1 — Deterministic Checks** (<5ms target):

| Check | Severity | Description |
|-------|----------|-------------|
| `step_id_duplicate` | ERROR | Step ID uniqueness |
| `self_reference` | ERROR | Self-dependency |
| `dangling_dependency` | ERROR/WARN | Missing dep (WARN if in completed_step_ids for micro) |
| `inter_step_ref` | ERROR | `$<step_id>.result.*` without matching dep |
| `dag_cycle` | ERROR | Kahn's topological sort |
| `capability_missing` | ERROR/WARN | Not found in cache (WARN if `UNRESOLVED`) |
| `param_type_mismatch` | ERROR | Required params per CapabilityContract |
| `unsafe_capability` | WARNING | Non-GREEN safety_band_min |

**Phase 2 — LLM Arbiter**: capability=`STRUCTURED` (not CHAT), temperature=0.1, max_tokens=512/256(micro), timeout=3s/2s(micro).

**Verdict Schema** (VALIDATE_VERDICT_SCHEMA):

```json
{
  "status": "approved|revise|reject",
  "reasons": ["str"],
  "suggested_fixes?": ["str"],
  "coherence_score": 0.0-1.0,
  "safety_assessment": "safe|caution|unsafe",
  "completeness": "bool"
}
```

**Phase 3 — HIL Approval** (conditional):

- Triggered when: any step has `has_side_effects=True` AND (`safety_band_min != GREEN` OR arbiter says `caution`).
- Auto-approve if all GREEN + safe.
- HIL options: approve/modify/reject. V1: "modify" treated as approve.
- HIL timeout: auto-approve if all GREEN, else REJECT.

#### §2.5.4 CommitService (commit_service.py — 454 lines)

**Injected**: `IBridgePort`, `IDeltaEmitPort`, `IEventPort` — **NO ILLMPort** (PLAN-03 enforced)

**Execute** (11-step sequence):

1. Cancel check
2. Build `CommittedPlan` (uuid4, timestamp, frozen steps+deps)
3. `_compute_critical_path_duration()` — Kahn's algorithm + DP longest path
4. Validate via `__post_init__`
5. WAL persist (fire-and-forget, 2 attempts)
6. Publish `plan.ready.v1` event (2 attempts)
7. Emit stage + plan_end deltas

**Zero LLM calls, zero tool calls, zero HIL**.

### §2.6 Cross-Cutting Services

#### §2.6.1 ToolCallRouter (tool_call_router.py — 352 lines)

Routes discovery tool calls to correct ports. Enforces PLAN-02 (read-only) and PLAN-05 (budget).

**Routing Table**:

| Tool | Port | Timeout | Retries |
|------|------|---------|---------|
| `discover_capabilities` | IFabricRetrievalPort | 50ms | 1 |
| `find_relevant_prompts` | IFabricRetrievalPort | 50ms | 1 |
| `query_planning_context` | IStateReadPort | 10ms | 0 |
| `recall_for_planning` | IBridgePort | 100ms | 0 |

**Budget**: `tool_call_count < max_tool_calls_per_plan` (default 6). Retries do NOT double-count.

**Bypass**: `get_schema()` bypasses routing table and budget counter — used by ExpandService for schema lookups.

#### §2.6.2 HILCoordinator (hil_coordinator.py — 482 lines)

Human-in-the-loop coordination for clarification (Stage 1) and approval (Stage 3).

**Clarification Flow** (SKETCH):

1. Check round budget (PLAN-10: max 2 rounds)
2. Generate question via LLM (CHAT, 300 tokens, 0.7 temp, 3s)
3. Emit `k1.hil.clarification.v1` event
4. Wait for response on `k1.hil.clarification_response.v1` (60s timeout)
5. On timeout: return None. On success: return user text.

**Approval Flow** (VALIDATE):

1. Generate summary via LLM (CHAT, 400 tokens, 0.7 temp, 3s)
2. Emit `k1.hil.approval_request.v1` event (options: approve/modify/reject)
3. Wait for response on `k1.hil.approval_response.v1` (120s timeout)
4. On timeout: auto-approve if safe/no-side-effects, else raise `HILTimeoutError`.

**Response correlation**: subscribe + `asyncio.Event` bridge, filtered by request_id.

### §2.7 LLM Call Matrix

| ID | Stage | Capability | Temp | Max Tokens | Timeout | Purpose |
|----|-------|-----------|------|------------|---------|---------|
| LLM-1 | SKETCH | CHAT | 0.7 | 2048 | 8s | Plan sketching with tool use |
| LLM-2 | EXPAND | CHAT | 0.3 | 1024 | 5s | Step expansion with tool use |
| LLM-3 | VALIDATE | STRUCTURED | 0.1 | 512 | 3s | Arbiter verdict |
| LLM-4 | COMMIT | — | — | — | — | **No LLM** (PLAN-03) |
| LLM-5a | HIL Clarification | CHAT | 0.7 | 300 | 3s | Generate clarification question |
| LLM-5b | HIL Approval | CHAT | 0.7 | 400 | 3s | Generate approval summary |
| LLM-M1 | µSKETCH | CHAT | 0.7 | 1024 | 5s | Micro-replan sketch |
| LLM-M2 | µEXPAND | CHAT | 0.3 | 512 | 3s | Micro-replan expand |
| LLM-M3 | µVALIDATE | STRUCTURED | 0.1 | 256 | 2s | Micro-replan arbiter |

### §2.8 Discovery Tool Matrix

| Tool | Stages Used | Port | Read-Only | Budget-Counted |
|------|-------------|------|-----------|----------------|
| `discover_capabilities` | SKETCH, EXPAND | IFabricRetrievalPort | ✅ | ✅ |
| `find_relevant_prompts` | SKETCH, EXPAND | IFabricRetrievalPort | ✅ | ✅ |
| `query_session_context` | SKETCH, EXPAND | IStateReadPort | ✅ | ✅ |
| `recall_long_term_memory` | SKETCH only | IBridgePort | ✅ | ✅ |
| `get_capability_schema` | EXPAND only | IFabricRetrievalPort | ✅ | **❌ bypass** |

---

## §3 Factory, Config & Types

### §3.1 PlannerFactory (factory.py — 573 lines)

Pure static factory with 4 creation modes:

| Method | Use Case | Returns |
|--------|----------|---------|
| `create_standalone(config?)` | Quick start with all test adapters | `PlannerAgent` |
| `create_for_testing(config?, **overrides)` | Test with selective overrides | `(PlannerAgent, Dict)` |
| `create_with_ports(*, ports..., config?)` | Full custom wiring | `PlannerAgent` |
| `create_production(*, ports..., config?)` | Production-only | `PlannerAgent` |

**10-Step Wiring Sequence** (_wire):

1. `ToolCallRouter(fabric, state, bridge, config)` — leaf
2. `HILCoordinator(llm, event, config)` — leaf
3. `SketchService(llm, tool_router, hil)` — Stage 1
4. `ExpandService(llm, tool_router)` — Stage 2
5. `ValidateService(llm, fabric, hil)` — Stage 3
6. `CommitService(bridge, delta, event)` — Stage 4 (**NO llm**)
7. `PipelineController(sketch, expand, validate, commit, delta, event, config)`
8. `PlannerAgent(mailbox, pipeline, event, config)`

**Validation** (3 passes):

1. None check for all 7 ports
2. `isinstance` against `@runtime_checkable` Protocol
3. Uniqueness: `id()` comparison across all port pairs (DuplicatePortError)

### §3.2 PlannerConfig (config.py — 203 lines)

Frozen dataclass with comprehensive `__post_init__` validation:

| Field | Default | Constraint |
|-------|---------|------------|
| `mailbox_max_depth` | 5 | [1, 20] |
| `pipeline_timeout_ms` | 45,000 | > 0 |
| `sketch_timeout_ms` | 8,000 | > 0 |
| `expand_timeout_ms` | 5,000 | > 0 |
| `validate_timeout_ms` | 3,000 | > 0 |
| `commit_timeout_ms` | 1,000 | > 0 |
| `sketch_max_tokens` | 2,000 | > 0 |
| `expand_max_tokens` | 1,000 | > 0 |
| `validate_max_tokens` | 500 | > 0 |
| `total_token_budget` | 3,500 | ≥ sum(sketch+expand+validate) |
| `sketch_temperature` | 0.7 | [0.0, 2.0] |
| `expand_temperature` | 0.3 | [0.0, 2.0] |
| `validate_temperature` | 0.2 | [0.0, 2.0] |
| `max_tool_calls_per_plan` | 6 | [1, 20] |
| `max_hil_rounds` | 2 | [0, 5] |
| `hil_clarification_timeout_ms` | 60,000 | > 0 |
| `hil_approval_timeout_ms` | 120,000 | > 0 |
| `micro_replan_timeout_ms` | 10,000 | > 0 |
| `micro_replan_max_tokens` | 2,000 | ≥ sum(micro per-stage) |
| `micro_sketch_max_tokens` | 1,024 | > 0 |
| `micro_sketch_timeout_ms` | 5,000 | > 0 |
| `micro_expand_max_tokens` | 512 | > 0 |
| `micro_expand_timeout_ms` | 3,000 | > 0 |
| `micro_validate_max_tokens` | 256 | > 0 |
| `micro_validate_timeout_ms` | 2,000 | > 0 |
| `shutdown_grace_period_ms` | 5,000 | > 0 |

### §3.3 Type Inventory (types.py — 807 lines)

#### Dataclasses (all frozen=True unless noted)

| Type | Fields | Purpose |
|------|--------|---------|
| `RoughStep` | intent, suggested_capability?, depends_on, confidence | SKETCH output unit |
| `SketchResult` | rough_steps, capability_candidates, rationale | SKETCH→EXPAND handoff |
| `ExpandedPlan` | steps: List[PlanStep], dependencies, tool_mappings, rationale | EXPAND→VALIDATE→COMMIT handoff |
| `ValidationIssue` | check_name, severity, step_id?, detail | Deterministic/arbiter finding |
| `ValidationVerdict` | status, issues, confidence, rationale, deterministic_pass, safety_assessment, suggested_fixes | VALIDATE output |
| `StageContext` | request_id, trace_id, timeout_remaining_ms, token_budget_remaining, cancel_check, stage_budget? | Per-stage envelope (shrinking budgets) |
| `DeltaPayload` | agent_id, delta_type, section, data, trace_id | Observability envelope |
| `RequestConstraints` | max_tokens, timeout_ms, priority, temperature, consumer_id | Per-LLM-call constraints |
| `HubRequest` | capability, payload, constraints, trace_id | **LOCAL** — migration stale (see §4) |
| `HubResponse` | result, metadata | **LOCAL** — migration stale (see §4) |
| `RecallResponse` | facts, scores, trace_id | Bridge recall result |
| `TokenUsageRecord` | stage, prompt_tokens, completion_tokens, total_tokens | **Mutable** accumulator |
| `HealthStatus` | status, details | Agent health snapshot |

#### Protocols

| Protocol | Methods |
|----------|---------|
| `HILCoordinatorLike` | round_count, reset(), request_clarification(), request_approval() |

#### Enums

| Enum | Members |
|------|---------|
| `StagePhase` | SKETCH, EXPAND, VALIDATE, COMMIT |
| `ToolCallStatus` | SUCCESS, TIMEOUT, ERROR, BUDGET_EXHAUSTED |

#### Error Hierarchy (extends PlannerError)

| Error | Use |
|-------|-----|
| `PlannerError` | Base (stage, request_id, trace_id) |
| `SketchFailedError` | SKETCH failed |
| `ExpandFailedError` | EXPAND failed |
| `ValidateRejectedError` | VALIDATE rejected |
| `CommitFailedError` | COMMIT failed |
| `BudgetExhaustedError` | Total token budget |
| `MailboxFullError` | Queue at max depth |
| `ShutdownError` | Planner shutting down |
| `PlanCancelledError` | Cancelled by orchestrator |
| `HILTimeoutError` | HIL timed out |
| `HILBudgetExceededError` | PLAN-10 rounds exhausted |
| `LLMTimeoutError` | Model Hub timeout |
| `BudgetExceededError` | Model Hub rejected (MH-04) |
| `AdapterException` | Adapter infra failure (degraded: bool) |
| `UnknownToolError` | Unknown tool name |
| `InvalidPortError` | Factory: protocol mismatch |
| `MissingPortError` | Factory: None port |
| `DuplicatePortError` | Factory: same id() |
| `InvalidConfigError` | Factory: config bounds |
| `PlannerInitError` | Factory: wiring failed |

#### Constants (selected)

| Category | Constants |
|----------|-----------|
| Verdicts | VERDICT_APPROVED, VERDICT_REVISE, VERDICT_REJECT |
| Severities | SEVERITY_ERROR, SEVERITY_WARNING |
| Safety | SAFETY_SAFE, SAFETY_CAUTION, SAFETY_UNSAFE, SAFETY_UNKNOWN |
| Delta types (8) | stage_transition, tool_result, hil_event, plan_update, plan_end, plan_cancelled, micro_replan, crash_recovery |
| Sections | pipeline, plan, tools |
| Check names (9) | dag_cycle, dangling_dependency, inter_step_ref, self_reference, step_id_duplicate, capability_missing, param_type_mismatch, unsafe_capability, llm_arbiter_reject |

### §3.4 Events (events.py — 141 lines)

**Published topics**:

| Constant | Topic |
|----------|-------|
| `TOPIC_PLAN_READY` | `k1.planner.plan.ready.v1` |
| `TOPIC_PLAN_FAILED` | `k1.planner.plan.failed.v1` |
| `TOPIC_PLAN_CANCELLED` | `k1.planner.plan.cancelled.v1` |
| `TOPIC_MICRO_REPLAN_READY` | `k1.planner.micro_replan.ready.v1` |
| `TOPIC_DELTA` | `k1.planner.delta.v1` |
| `TOPIC_HIL_CLARIFICATION` | `k1.hil.clarification.v1` |
| `TOPIC_HIL_APPROVAL_REQ` | `k1.hil.approval_request.v1` |

**Subscribed topics**:

| Constant | Topic |
|----------|-------|
| `TOPIC_PLAN_REQUEST` | `k1.planner.plan.request.v1` |
| `TOPIC_PLAN_CANCEL` | `k1.planner.plan.cancel.v1` |
| `TOPIC_HIL_CLARIFICATION_RESP` | `k1.hil.clarification_response.v1` |
| `TOPIC_HIL_APPROVAL_RESP` | `k1.hil.approval_response.v1` |

**Event Payload Dataclasses** (all frozen):

| Payload | Fields |
|---------|--------|
| `PlanFailedPayload` | request_id, stage, error_code, error_message, tokens_used, duration_ms, trace_id, partial_state? |
| `PlanCancelledPayload` | request_id, reason, stage, trace_id |
| `HILClarificationPayload` | request_id, question, context, trace_id |
| `HILApprovalRequestPayload` | request_id, summary, options, side_effects, safety_assessment |

### §3.5 Public API Surface (**init**.py — 199 lines)

~57 symbols exported via `__all__`. Re-exports from `k1.orchestrator.types`: `CommittedPlan`, `MicroReplanRequest`, `PlanAck`, `PlanRequest`, `PlanStep`.

### §3.6 Tracing (tracing.py — 48 lines)

Single helper `create_stage_context()` — computes shrinking timeout/token envelopes. No OpenTelemetry or span instrumentation.

---

## §4 Cross-Component Wiring (7 Connections)

### §4.1 Compatibility Matrix

| # | Connection | Port | Adapter | Compatible? | Issues |
|---|-----------|------|---------|-------------|--------|
| 1 | ModelHub → Planner | `ILLMPort` | `LLMGatewayAdapter` | **🔴 NO** | Dual HubRequest/HubResponse/RequestConstraints (see §4.2) |
| 2 | Fabric → Planner | `IFabricRetrievalPort` | `FabricRetrievalAdapter` | ✅ Yes | None — `RetrievalResult` shared from `k1.fabric.types` |
| 3 | SessionState → Planner | `IStateReadPort` | `SessionStateReadAdapter` | ✅ Yes | Minor: sync reader call inside async method |
| 4 | Bridge → Planner | `IBridgePort` | `BridgeAdapter` | ✅ Yes | None — `RecallResponse` planner-owned, `CommittedPlan` orchestrator-owned |
| 5 | Planner → Orchestrator | Events | `IEventPort` | ✅ Yes | Shared types correctly owned by orchestrator |
| 6a | Bus → Planner | `IMailboxPort` | `MailboxAdapter` | ✅ Yes | asyncio.Queue[PlanRequest], bounded at 5 |
| 6b | Bus → Planner | `IEventPort` | `EventBusAdapter` | ✅ Yes | Interface identity passthrough (SS15.9) |
| 6c | Bus → Planner | `IDeltaEmitPort` | `DeltaBusAdapter` | ✅ Yes | DeltaPayload planner-owned, decomposed to positional args |

### §4.2 🔴 Critical: HubRequest/HubResponse Type Duplication

**Root cause**: Planner's `types.py` contains a migration note: *"These types should migrate to k1/model_hub/types.py when that module is created."* But `k1/model_hub/types.py` **already exists** with its own definitions. The planner still uses local copies.

**5 type mismatches**:

| Field | Planner (local) | ModelHub (canonical) | Impact |
|-------|-----------------|---------------------|--------|
| `HubRequest.capability` | `str` | `CapabilityType` (str, Enum — 15 members) | MEDIUM — works at runtime via str comparison, but statically incompatible |
| `HubRequest.payload` | `Dict[str, Any]` | `Any` (typed payloads) | LOW |
| `HubRequest.constraints` | Planner's `RequestConstraints` (5 fields) | ModelHub's `RequestConstraints` (8 fields, `Priority` enum) | **HIGH** — different classes, different priority types, different temp ranges, missing fields |
| `HubResponse.result` | `Dict[str, Any]` | `Any` (typed `CapabilityResult`) | MEDIUM |
| `HubResponse.metadata` | `Dict[str, Any]` | `ResponseMetadata` (frozen, 11 fields) | **HIGH** |

**Runtime mitigation**: `LLMGatewayAdapter` uses `ILLMRequestBus(Protocol)` with `Any` typing and `getattr()` coercion for response fields. This works but is fragile.

**Fix**: Complete the migration — import `HubRequest`, `HubResponse`, `RequestConstraints` from `k1.model_hub.types` and remove local definitions. Planner's `RequestConstraints` would need 3 additional fields (`model_preference`, `provider_preference`, `cost_limit`).

### §4.3 Adapter Patterns

| Pattern | Adapters |
|---------|----------|
| Fire-and-forget (never raise) | BridgeAdapter.persist_plan, DeltaBusAdapter.emit, EventBusAdapter.emit |
| Degraded fallback (empty return) | BridgeAdapter.recall, FabricRetrievalAdapter.*, SessionStateReadAdapter.* |
| Retry + timeout | FabricRetrievalAdapter (50ms, 1 retry) |
| Exception re-mapping | LLMGatewayAdapter (Timeout→LLMTimeoutError, budget→BudgetExceededError) |
| Explicit error types | MailboxAdapter (MailboxFullError, ShutdownError) |
| Offline guard | BridgeAdapter (is_available pre-check) |

### §4.4 Cross-Component Import Map

| Module | Imports From |
|--------|-------------|
| Ports | `k1.orchestrator.types` (3 types), `k1.fabric.types` (1), `k1.fabric.ports` (2) |
| Adapters | `k1.orchestrator.types` (3 via MailboxAdapter), `k1.fabric.ports` (1), `k1.fabric.types` (1) |
| Stages | `k1.orchestrator.types` (PlanRequest, PlanStep, MicroReplanRequest, StepResult), `k1.fabric.types` (ScoredCapability) |
| Services | None external (planner-internal only) |
| Types | `k1.orchestrator.types.PlanStep` (imported), `k1.fabric.types.ScoredCapability` (imported) |

**Type ownership**: `PlanRequest`, `CommittedPlan`, `PlanStep`, `MicroReplanRequest`, `PlanAck` are ALL owned by `k1.orchestrator.types`. Planner re-exports them via `__init__.py` but does NOT redefine them.

---

## §5 Test Inventory

### §5.1 Summary

| Metric | Count |
|--------|-------|
| Test functions (`def test_*`) | **1,923** |
| Test classes (`class Test*`) | **324** |
| Test files (excluding adapters/conftest) | **30** |
| Test adapter files (test doubles) | **7** |
| Conftest fixtures | **7** (+ 1 commented-out composite) |
| Estimated test LOC | ~22,000 |

### §5.2 Test File Map

| File | Tests | Classes | Component |
|------|-------|---------|-----------|
| test_planner_types_1_2_6_10 | 28 | 0 | types (StageContext, DeltaPayload, PlanState, enums) |
| test_planner_types_1_2_11_14 | 53 | 11 | types (events, RequestConstraints, TokenUsageRecord, Config, errors) |
| test_planner_ports_1_4 | 57 | 14 | ports (all 7 Protocols, @runtime_checkable, AST layer) |
| test_planner_events_1_5_1_4 | 57 | 18 | events (plan.ready, plan.failed, plan.cancelled, micro_replan.ready) |
| test_planner_events_1_5_5_9 | 105 | 17 | events (HIL topics, Config.from_dict, namespace validation) |
| test_planner_fsm_2_1_1 | 47 | 10 | plan_fsm (PlanState enum, 11 members) |
| test_planner_fsm_2_1_2_5 | 118 | 19 | plan_fsm (TRANSITION_TABLE, PlanStateMachine, force methods) |
| test_planner_pipeline_ctrl_2_2_1 | 96 | 14 | pipeline_controller (skeleton, constructor, reset, FSM) |
| test_planner_pipeline_ctrl_2_2_2 | 107 | 16 | pipeline_controller (execute stage loop, verdict routing) |
| test_planner_pipeline_ctrl_2_2_3 | 83 | 13 | pipeline_controller (budget injection, PLAN-11) |
| test_planner_pipeline_ctrl_2_2_4 | 71 | 16 | pipeline_controller (cancel, PLAN-12) |
| test_planner_pipeline_ctrl_2_2_5 | 24 | 7 | pipeline_controller (micro_replan routing) |
| test_planner_pipeline_ctrl_2_2_6 | 8 | 3 | pipeline_controller (timeout, PLAN-04) |
| test_planner_pipeline_ctrl_2_2_7 | 7 | 3 | pipeline_controller (StageContext propagation) |
| test_planner_agent_2_3_1 | 44 | 10 | planner_agent (skeleton, slots) |
| test_planner_agent_2_3_2_3_4 | 47 | 13 | planner_agent (dequeue loop, plan lock, cancel) |
| test_planner_agent_2_3_5_6_7 | 42 | 13 | planner_agent (INIT/SHUTDOWN/CRASH_RECOVERY) |
| test_planner_sketch_3_1_1 | 50 | 12 | sketch_service (skeleton, Protocols) |
| test_planner_sketch_3_1_2 | 97 | 15 | sketch_service (agentic loop, tools, HIL, parsing) |
| test_planner_expand_3_2 | 125 | 16 | expand_service (agentic loop, tools, DAG, enrichment) |
| test_planner_validate_3_3 | 66 | 11 | validate_service (deterministic, arbiter, HIL approval) |
| test_planner_commit_3_4 | 52 | 8 | commit_service (assembly, WAL, event/delta) |
| test_planner_tool_call_router_4_1 | 49 | 10 | tool_call_router (routing, PLAN-05, PLAN-02) |
| test_planner_hil_coordinator_4_2 | 45 | 7 | hil_coordinator (clarification/approval, timeout, PLAN-10) |
| test_planner_micro_replan_5_1 | 45 | 10 | pipeline_controller (micro trigger, micro FSM states) |
| test_planner_micro_prompt_5_1_2_3 | 53 | 11 | sketch+expand (micro prompts) |
| test_planner_micro_validate_5_1_4 | 24 | 5 | validate (micro, cross-boundary deps) |
| test_planner_adapters_6_1 | 212 | 56 | adapters (all 7 test adapters, Protocol compliance) |
| test_planner_adapters_6_2 | 68 | 18 | adapters (all 7 production adapters, happy/error) |
| test_factory | 43 | 9 | factory (4 modes, port/config validation) |

### §5.3 Coverage

| Component | Test Coverage |
|-----------|--------------|
| All 7 ports | ✅ Full (ports_1_4 + adapters_6_1) |
| All 7 production adapters | ✅ Full (adapters_6_2) |
| All 7 test adapters | ✅ Full (adapters_6_1) |
| PlanStateMachine | ✅ Full (fsm_2_1_1 + fsm_2_1_2_5: 165 tests) |
| PipelineController | ✅ Full (2_2_1 through 2_2_7 + micro_5_1: 441 tests) |
| PlannerAgent | ✅ Full (2_3_1 + 2_3_2_3_4 + 2_3_5_6_7: 133 tests) |
| SketchService | ✅ Full (3_1_1 + 3_1_2 + micro_prompt: 200 tests) |
| ExpandService | ✅ Full (3_2 + micro_prompt: 178 tests) |
| ValidateService | ✅ Full (3_3 + micro_validate: 90 tests) |
| CommitService | ✅ Full (3_4: 52 tests) |
| ToolCallRouter | ✅ Full (4_1: 49 tests) |
| HILCoordinator | ✅ Full (4_2: 45 tests) |
| Factory | ✅ Full (test_factory: 43 tests) |
| Types/Events/Config | ✅ Full (1_2_*+ 1_5_*: 243 tests) |

### §5.4 Test Patterns

- **Primary**: Hand-written Fake/Stub classes per file (FakeLLMPort, FakeSketchService, etc.)
- **Reusable**: 7 test adapter classes in `tests/k1/planner/adapters/` with capture + assertion helpers
- **Conftest**: 7 adapter fixtures + `all_adapters` dict
- **mock.patch**: Used sparingly (sketch: 22, expand: 14, adapters: 26, tool_router: 9)
- **@pytest.mark.parametrize**: 39 decorators across 7 files
- **@pytest.mark.asyncio**: Heavy use in agent/pipeline/stage tests

### §5.5 Gaps

| Gap | Severity | Detail |
|-----|----------|--------|
| No end-to-end wired test | 🟡 | `wired_planner` fixture commented out, pending Issue 6.3.3 |
| Thin timeout tests | 🟡 | test_planner_pipeline_ctrl_2_2_6 has only 8 tests |
| Thin StageContext tests | 🟡 | test_planner_pipeline_ctrl_2_2_7 has only 7 tests |
| No performance tests | 🟡 | No benchmark or timing validation in planner test tree |

---

## §6 Spec vs Code Delta

### §6.1 Invariant Verification

| Invariant | Description | Enforced? | Mechanism |
|-----------|------------|-----------|-----------|
| PLAN-01 | Planner NEVER writes SessionState | ✅ | `IStateReadPort` has no write methods |
| PLAN-02 | All discovery tools read-only | ✅ | Routing table has no execute routes |
| PLAN-03 | CommitService has NO LLM port | ✅ | Constructor: IBridgePort, IDeltaEmitPort, IEventPort only |
| PLAN-04 | Pipeline timeout enforcement | ✅ | `_check_timeout()` at 3 checkpoints |
| PLAN-05 | Max 6 tool calls per plan | ✅ | ToolCallRouter._check_budget() |
| PLAN-06 | No capability execution | ✅ | IFabricRetrievalPort has no execute methods |
| PLAN-07 | Token budget tracking | ✅ | StageContext.token_budget_remaining, PipelineController tracking |
| PLAN-08 | DAG acyclicity | ✅ | Kahn's algorithm in ValidateService Phase 1 |
| PLAN-09 | Capability existence | ✅ | ValidateService Phase 1 capability check |
| PLAN-10 | Max 2 HIL rounds | ✅ | HILCoordinator._check_round_budget() |
| PLAN-11 | Per-call LLM constraints | ✅ | RequestConstraints on every HubRequest |
| PLAN-12 | Micro-replan: completed steps frozen | ✅ | PipelineController._enforce_plan12() |

### §6.2 Diagram vs Code Discrepancies

| Aspect | Diagram Says | Code Says | Status |
|--------|-------------|-----------|--------|
| FSM states | 10 states | **11 states** (CANCELLED separate from FAILED) | Code is source of truth |
| Validate temperature | 0.1 | 0.1 (default), config has 0.2 | Config default differs; runtime uses 0.1 constant |
| HIL response routing | Event bus → HILCoordinator → resume stage | **V1 stub** in PlannerAgent — discards responses | ⚠️ V1 limitation documented |
| Crash recovery | "check WAL + resume" | **V1 no-op** (always discard, log) | ⚠️ V1 limitation documented |
| get_capability_schema | Listed as discovery tool | **Bypasses** routing table and budget counter | By design (schema lookup ≠ discovery call) |

### §6.3 Critical Findings

| # | Severity | Finding | Fix Required |
|---|----------|---------|-------------|
| 1 | 🔴 | **HubRequest/HubResponse/RequestConstraints type duplication** — Planner defines locally despite `k1.model_hub.types` already existing. 5 field mismatches: str vs CapabilityType, Dict vs ResponseMetadata, 5-field vs 8-field RequestConstraints. Runtime works via Any/getattr coercion but is fragile. | Complete migration: import from `k1.model_hub.types` |
| 2 | ⚠️ | **HIL response routing is V1 stub** — PlannerAgent subscribes to response topics but handlers log and discard. HILCoordinator uses asyncio.Event for response correlation but agent never forwards responses to it. | Wire response forwarding from agent to HILCoordinator |
| 3 | ⚠️ | **Crash recovery is V1 no-op** — Always discards queued plans on restart. | Implement WAL-based recovery |
| 4 | 🟡 | **BridgeAdapter.persist_plan types as Any** — Port declares `CommittedPlan` but adapter accepts `Any`. Works via duck typing but loses static safety. | Type the adapter parameter to `CommittedPlan` |
| 5 | 🟡 | **wired_planner fixture commented out** — No end-to-end integration test. Pending Issue 6.3.3. | Implement PlannerFactory.create_for_testing() integration |
| 6 | 🟡 | **Validate temperature discrepancy** — types.py `RequestConstraints.temperature` defaults to 0.7, config defaults to 0.2, but ValidateService uses hardcoded 0.1 constant. | Align or document which source wins |

---

## §7 File Inventory

### §7.1 Source Files (34 files, ~10,500 lines)

| Directory | File | Lines | Purpose |
|-----------|------|-------|---------|
| root | `__init__.py` | 199 | Public API (~57 exports) |
| root | `pipeline_controller.py` | 1,301 | 4-stage pipeline + micro-replan |
| root | `planner_agent.py` | 733 | Async coordinator + mailbox loop |
| root | `plan_fsm.py` | 273 | 11-state machine, 23 transitions |
| root | `types.py` | 807 | 13 dataclasses, 2 enums, 20 errors, 30+ constants |
| root | `factory.py` | 573 | 4-mode static factory, 10-step wiring |
| root | `config.py` | 203 | 26-field frozen config with validation |
| root | `events.py` | 141 | 11 topic constants, 4 payload dataclasses |
| root | `tracing.py` | 48 | StageContext builder |
| ports/ | 8 files | 537 | 7 Protocol ports |
| adapters/ | 8 files | 848 | 7 production adapters |
| stages/ | 5 files | 4,006 | 4 stage services |
| services/ | 3 files | 855 | ToolCallRouter + HILCoordinator |

### §7.2 Test Files (39 files, ~22,000 lines)

| Category | Files | Tests |
|----------|-------|-------|
| Type/Event/Port tests | 5 | 300 |
| FSM tests | 2 | 165 |
| PipelineController tests | 7 | 396 |
| PlannerAgent tests | 3 | 133 |
| Stage service tests | 6 | 415 |
| Cross-cutting service tests | 2 | 94 |
| Micro-replan tests | 3 | 122 |
| Adapter tests | 2 | 280 |
| Factory tests | 1 | 43 |
| **Total** | **30 + 7 adapters + conftest** | **1,923** |

### §7.3 Diagrams

| File | Lines | Content |
|------|-------|---------|
| `planner.mmd` | 719 | V1 architecture: type ownership, LLM call matrix, invariants, lifecycle, flow edges |
| `planner_v2.mmd` | 813 | V2 architecture: enhanced call matrix, metrics, resource budgets, error recovery, wiring |
