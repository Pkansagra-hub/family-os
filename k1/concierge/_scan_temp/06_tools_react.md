# 06 — Tools & React Subsystems: Exhaustive Scan

> **Batch:** `k1/concierge/tools/` (7 Python files, ~1,600 lines) + `k1/concierge/react/` (3 Python files, ~970 lines)
> **Scan date:** 2026-04-04

---

## TABLE OF CONTENTS

1. [tools/\_\_init\_\_.py — Package Re-exports](#1-toolsinit)
2. [tools/schemas_front.py — Front Tool Schemas (10 tools)](#2-schemas_front)
3. [tools/schemas_back.py — Back Tool Schemas (7 tools)](#3-schemas_back)
4. [tools/result_protocol.py — ToolResult Envelope](#4-result_protocol)
5. [tools/parallelism.py — Parallel Execution Rules](#5-parallelism)
6. [tools/dispatcher.py — 7-Step Dispatch Pipeline](#6-dispatcher)
7. [tools/implementations.py — Real Tool Implementations](#7-implementations)
8. [react/\_\_init\_\_.py — Package Re-exports](#8-reactinit)
9. [react/history.py — Chat History Helpers](#9-history)
10. [react/loop.py — Shared ReAct Loop](#10-loop)
11. [Cross-Component Dependency Map](#11-dependencies)
12. [Tool Registry Summary Table](#12-tool-registry)
13. [Error Handling Summary](#13-error-handling)

---

## 1. tools/\_\_init\_\_.py {#1-toolsinit}

**Purpose:** Central re-export hub for the entire tools subsystem.

### Re-exports (all public API)

| Symbol | Source Module |
|--------|-------------|
| `ToolDispatcher`, `create_front_dispatcher`, `create_back_dispatcher` | `dispatcher` |
| `TOOL_REGISTRY`, `ToolContext`, `execute_tool` | `implementations` |
| `PARALLEL_SAFE_GROUPS`, `ALWAYS_SEQUENTIAL`, `can_parallelize`, `partition_calls` | `parallelism` |
| `ToolResult`, `tool_result_to_message` | `result_protocol` |
| `BACK_TIER_ALLOWLISTS`, `BACK_TOOL_SCHEMAS`, `DISCOVER_CAPABILITIES_SCHEMA`, `EXECUTE_WORKFLOW_SCHEMA`, `INVOKE_CAPABILITY_SCHEMA`, `SPAWN_VIA_FABRIC_SCHEMA`, `SUBMIT_RESULT_SCHEMA` | `schemas_back` |
| `FRONT_TOOL_SCHEMAS`, `DISPATCH_TASK_SCHEMA`, `PROMOTE_BELIEF_SCHEMA`, `RECALL_MEMORY_SCHEMA`, `REFINE_AFFECT_SCHEMA`, `SUMMARIZE_CONTEXT_SCHEMA`, `UPDATE_BELIEFS_SCHEMA`, `UPDATE_CLARIFICATIONS_SCHEMA`, `UPDATE_NARRATIVE_SCHEMA`, `UPDATE_SCOREBOARD_SCHEMA` | `schemas_front` |

### Cross-Component Imports
- None (pure re-export)

---

## 2. tools/schemas_front.py — Front Tool Schemas {#2-schemas_front}

**Purpose:** Defines all 10 Front LLM tool schemas using the provider-agnostic `ToolSchema` from `k1.concierge.llm.types`.

### Cross-Component Imports
```python
from k1.concierge.llm.types import ToolSchema
```

### Tool Schema Definitions

#### 2.1 COGNITIVE (6 tools)

##### `UPDATE_BELIEFS_SCHEMA`
- **name:** `"update_beliefs"`
- **actor:** `"front"`, **category:** `"cognitive"`, **side_effects:** `True`
- **description:** Create or correct factual beliefs. Each belief is a subject-predicate-object triple with confidence.
- **parameters:**
  ```
  beliefs: array of {
    subject: string (required)
    predicate: string (required)
    object: string (required)
    confidence: number [0.0, 1.0] (required)
  } (minItems: 1)
  ```
- **returns:** `{ stored: integer, updated: integer }`

##### `UPDATE_SCOREBOARD_SCHEMA`
- **name:** `"update_scoreboard"`
- **actor:** `"front"`, **category:** `"cognitive"`, **side_effects:** `True`
- **description:** Update conversational scoreboard: QUD, referent resolution, salience, topic shifts, commitments.
- **parameters:**
  ```
  qud_push: string (optional) — New Question Under Discussion
  qud_pop: boolean (default false) — Pop current QUD
  referent_updates: object (additionalProperties: string) — pronoun -> entity map
  topic_shift: string (optional) — New topic name
  commitment_add: object {
    description: string (required)
    trigger_condition: string (required)
    linked_entities: array of string (optional)
    linked_content_summary: string (optional)
  }
  commitment_fulfill: string — Commitment ID to mark fulfilled
  ```
- **returns:** `{ qud_depth: integer, active_referents: integer, open_commitments: integer }`

##### `UPDATE_CLARIFICATIONS_SCHEMA`
- **name:** `"update_clarifications"`
- **actor:** `"front"`, **category:** `"cognitive"`, **side_effects:** `True`
- **description:** Record semantic gaps detected in user intent.
- **parameters:**
  ```
  gaps: array of {
    field: string (required) — What info is missing
    question: string (required) — Question to resolve it
    severity: enum ["blocking", "helpful", "minor"] (required)
  }
  resolved_gaps: array of string — Field names now resolved
  ```
- **returns:** `{ open_gaps: integer, blocking_gaps: integer }`

##### `UPDATE_NARRATIVE_SCHEMA`
- **name:** `"update_narrative"`
- **actor:** `"front"`, **category:** `"cognitive"`, **side_effects:** `True`
- **description:** Track conversation thread switches, resumptions, closures.
- **parameters:**
  ```
  action: enum ["switch", "resume", "close"] (required)
  thread_id: string (required)
  summary: string (optional)
  ```
- **returns:** `{ active_thread: string, total_threads: integer }`

##### `REFINE_AFFECT_SCHEMA`
- **name:** `"refine_affect"`
- **actor:** `"front"`, **category:** `"cognitive"`, **side_effects:** `True`
- **description:** Override Phase 1 (UltraBERT) emotion classification with LLM assessment.
- **parameters:**
  ```
  emotion: string (required) — Primary emotion label
  valence: number [-1.0, 1.0] (required)
  arousal: number [0.0, 1.0] (required)
  confidence: number [0.0, 1.0] (required)
  reason: string (optional)
  ```
- **returns:** `{ previous_emotion: string, updated: boolean }`

##### `PROMOTE_BELIEF_SCHEMA`
- **name:** `"promote_belief"`
- **actor:** `"front"`, **category:** `"cognitive"`, **side_effects:** `True`
- **description:** Promote low-confidence belief to HOT/high-confidence. MEDIUM and HIGH tier only.
- **parameters:**
  ```
  belief_id: string (required)
  new_confidence: number [0.0, 1.0] (required)
  reason: string (optional)
  ```
- **returns:** `{ promoted: boolean, from_tier: string }`

#### 2.2 BUNDLE (1 tool)

##### `UPDATE_SESSION_BUNDLE_SCHEMA`
- **name:** `"update_session_bundle"`
- **actor:** `"front"`, **category:** `"cognitive"`, **side_effects:** `True`
- **description:** Write to multiple SS sections in a single tool call with idempotency.
- **parameters:**
  ```
  mutations: array of {
    section: string (required) — Target SS section
    operation: string (required) — Operation name
    data: object (required) — Operation payload
  } (minItems: 1)
  idempotency_key: string (required) — Dedup key
  stop_on_rejection: boolean (default true) — Cancel on first rejection
  ```
- **returns:** `{ applied: integer, rejected: integer, cancelled: integer, stopped_early: boolean, details: array }`

#### 2.3 READ (2 tools)

##### `RECALL_MEMORY_SCHEMA`
- **name:** `"recall_memory"`
- **actor:** `"both"`, **category:** `"read"`, **side_effects:** `False`
- **description:** Query K0 long-term memory. Primary information source for agendas, calendars, preferences, past events, routines.
- **parameters:**
  ```
  query: string (required) — Natural language query
  memory_types: array of enum ["episodic", "semantic", "procedural"] (default: all)
  max_results: integer [1, 20] (default 5)
  ```
- **returns:** `{ memories: array of { content, type, relevance, timestamp }, count: integer }`

##### `SUMMARIZE_CONTEXT_SCHEMA`
- **name:** `"summarize_context"`
- **actor:** `"front"`, **category:** `"read"`, **side_effects:** `False`
- **description:** Compress Session State sections to fit within token budget.
- **parameters:**
  ```
  sections: array of string (required) — SS section names
  target_tokens: integer (required)
  ```
- **returns:** `{ compressed: string, original_tokens: integer, compressed_tokens: integer }`

#### 2.4 CONTROL (1 tool)

##### `DISPATCH_TASK_SCHEMA`
- **name:** `"dispatch_task"`
- **actor:** `"front"`, **category:** `"control"`, **side_effects:** `False`
- **description:** Dispatch task to background worker. FSM intercepts and emits `k1.orchestration.task.dispatch.v1`. Supports multi-intent with `depends_on`.
- **parameters:**
  ```
  intents: array of {
    action: string (required) — What to do
    params: object (optional)
    domain: string (optional) — travel, health, etc.
  } (minItems: 1)
  urgency: enum ["normal", "urgent", "background"] (default "normal")
  reference_context: object (optional) — Resolved references for Back
  depends_on: string (optional) — Task ID from previous dispatch_task
  ```
- **returns:** `{ queued: boolean, task_id: string }`

### Aggregated List

```python
FRONT_TOOL_SCHEMAS: list[ToolSchema] = [
    UPDATE_BELIEFS_SCHEMA,        # cognitive
    UPDATE_SCOREBOARD_SCHEMA,     # cognitive
    UPDATE_CLARIFICATIONS_SCHEMA, # cognitive
    UPDATE_NARRATIVE_SCHEMA,      # cognitive
    REFINE_AFFECT_SCHEMA,         # cognitive
    PROMOTE_BELIEF_SCHEMA,        # cognitive
    UPDATE_SESSION_BUNDLE_SCHEMA, # bundle
    RECALL_MEMORY_SCHEMA,         # read
    SUMMARIZE_CONTEXT_SCHEMA,     # read
    DISPATCH_TASK_SCHEMA,         # control
]
```

---

## 3. tools/schemas_back.py — Back Tool Schemas {#3-schemas_back}

**Purpose:** Defines all 7 Back LLM tool schemas.

### Cross-Component Imports
```python
from k1.concierge.llm.types import ToolSchema
from k1.concierge.tools.schemas_front import RECALL_MEMORY_SCHEMA  # shared
```

### Tool Schema Definitions

#### 3.1 READ (2 tools)

- **RECALL_MEMORY_SCHEMA** — imported from `schemas_front` (actor=`"both"`)

##### `DISCOVER_CAPABILITIES_SCHEMA`
- **name:** `"discover_capabilities"`
- **actor:** `"back"`, **category:** `"read"`, **side_effects:** `False`
- **description:** Query K0 capability registry. Returns ranked matches. Call BEFORE invoke/spawn.
- **parameters:**
  ```
  intent: string (required) — What to accomplish
  domain: string (optional) — Domain hint
  constraints: object (optional)
  ```
- **returns:** `{ capabilities: array of { name, description, confidence, provider }, count: integer }`

#### 3.2 ACTION (3 tools)

##### `INVOKE_CAPABILITY_SCHEMA`
- **name:** `"invoke_capability"`
- **actor:** `"back"`, **category:** `"action"`, **side_effects:** `True`
- **description:** Invoke a known K0 capability by name with parameters.
- **parameters:**
  ```
  capability_name: string (required)
  params: object (required)
  session_id: string (optional)
  ```
- **returns:** `{ result: object, duration_ms: integer, status: enum ["success", "partial", "error"] }`

##### `BATCH_INVOKE_CAPABILITIES_SCHEMA`
- **name:** `"batch_invoke_capabilities"`
- **actor:** `"back"`, **category:** `"action"`, **side_effects:** `True`
- **description:** Invoke multiple capabilities in a single tool call (saves tool budget). 1-8 invocations.
- **parameters:**
  ```
  invocations: array of {
    capability_name: string (required)
    params: object (required)
  } (minItems: 1, maxItems: 8)
  ```
- **returns:** `{ results: array of { capability_name, result, status }, total, succeeded, failed }`

##### `SPAWN_VIA_FABRIC_SCHEMA`
- **name:** `"spawn_via_fabric"`
- **actor:** `"back"`, **category:** `"action"`, **side_effects:** `True`
- **description:** Spawn a specialized agent via K0 Agent Fabric. MEDIUM/HIGH tier only.
- **parameters:**
  ```
  agent_type: string (required)
  task: string (required)
  constraints: object (optional)
  capabilities_needed: array of string (optional)
  ```
- **returns:** `{ agent_id: string, status: enum ["spawned", "queued", "rejected"], estimated_duration_ms: integer }`

##### `EXECUTE_WORKFLOW_SCHEMA`
- **name:** `"execute_workflow"`
- **actor:** `"back"`, **category:** `"action"`, **side_effects:** `True`
- **description:** Execute a predefined workflow by ID. MEDIUM/HIGH tier only.
- **parameters:**
  ```
  workflow_id: string (required)
  params: object (required)
  timeout_ms: integer (default 30000)
  ```
- **returns:** `{ execution_id: string, status: enum ["completed", "running", "failed"], result: object }`

#### 3.3 CONTROL (1 tool)

##### `SUBMIT_RESULT_SCHEMA`
- **name:** `"submit_result"`
- **actor:** `"back"`, **category:** `"control"`, **side_effects:** `False`
- **description:** Submit task result back to Front. Must be called EXACTLY ONCE as final tool call. `result_type="complete"` for done, `"needs_human"` for HITL.
- **parameters:**
  ```
  result_type: enum ["complete", "needs_human"] (required)
  # For "complete":
  final_answer: string
  results: array of object
  artifacts_created: array of string
  # For "needs_human":
  hil_type: enum ["confirm", "choose", "provide_info", "clarification", "escalate"]
  question: string
  options: array of object
  side_effects: string
  ```
- **returns:** `{ delivered: boolean, weave_event_id: string }`

### Aggregated List

```python
BACK_TOOL_SCHEMAS: list[ToolSchema] = [
    RECALL_MEMORY_SCHEMA,
    DISCOVER_CAPABILITIES_SCHEMA,
    INVOKE_CAPABILITY_SCHEMA,
    BATCH_INVOKE_CAPABILITIES_SCHEMA,
    SPAWN_VIA_FABRIC_SCHEMA,
    EXECUTE_WORKFLOW_SCHEMA,
    SUBMIT_RESULT_SCHEMA,
]
```

### Tier-Based Allowlists (schemas_back)

| Tier | Allowed Tools |
|------|--------------|
| **LOW** | recall_memory, discover_capabilities, invoke_capability, batch_invoke_capabilities, submit_result |
| **MEDIUM** | ALL 7 tools |
| **HIGH** | ALL 7 tools |

---

## 4. tools/result_protocol.py — ToolResult Envelope {#4-result_protocol}

**Purpose:** Every tool implementation returns a `ToolResult` envelope. `tool_result_to_message()` converts it to LLM-appendable format.

### Cross-Component Imports
```python
from k1.concierge.llm.types import ToolResultMessage
```

### Class: `ToolResult`

```python
@dataclass(frozen=True)
class ToolResult:
    tool_name: str
    status: str           # "ok" | "error" | "partial"
    data: dict[str, Any]  # default_factory=dict
    error: str | None     # default None

    def is_ok(self) -> bool
    def is_error(self) -> bool
```

### Function: `tool_result_to_message`

```python
def tool_result_to_message(
    call_id: str,
    result: ToolResult,
) -> ToolResultMessage
```
- Converts `ToolResult` into `ToolResultMessage` for LLM history
- Error results: `{"error": ..., "tool": ...}`
- Success results: `json.dumps(result.data)`

---

## 5. tools/parallelism.py — Parallel Execution Rules {#5-parallelism}

**Purpose:** Defines which tools can execute concurrently and partitioning logic.

### Cross-Component Imports
- None

### Constants

```python
PARALLEL_SAFE_GROUPS: dict[str, frozenset[str]] = {
    "cognitive": frozenset({
        "update_beliefs", "update_scoreboard", "update_clarifications",
        "update_narrative", "refine_affect", "promote_belief",
    }),
    "read": frozenset({
        "recall_memory", "summarize_context", "discover_capabilities",
    }),
    "action": frozenset({
        "invoke_capability", "spawn_via_fabric", "execute_workflow",
    }),
}

ALWAYS_SEQUENTIAL: frozenset[str] = frozenset({
    "dispatch_task",   # Must be last (Front)
    "submit_result",   # Must be last (Back)
})
```

### Functions

#### `can_parallelize(tool_a: str, tool_b: str) -> bool`
- Both in same group → `True`
- Cross-group: `read + cognitive` → `True`
- Cross-group: `read + action` → `True`
- Either in `ALWAYS_SEQUENTIAL` → `False`
- All other combos → `False`

#### `partition_calls(tool_names: list[str]) -> list[list[str]]`
- Splits tools into batches: parallelizable first (one batch), then sequential tools each in own batch
- Sequential tools (`dispatch_task`, `submit_result`) always go **last**

---

## 6. tools/dispatcher.py — 7-Step Dispatch Pipeline {#6-dispatcher}

**Purpose:** Validates and dispatches tool calls through a multi-step pipeline with allowlists, budget enforcement, schema validation, and safety band checks.

### Cross-Component Imports
```python
from k1.bus.ports.bus import IBus
from k1.concierge.config import get_config
from k1.concierge.llm.types import ToolCallResult, ToolSchema
from k1.concierge.tools.implementations import ToolContext, execute_tool
from k1.concierge.tools.result_protocol import ToolResult

# Optional (try/except):
from k1.concierge.bus.builders import build_tool_completed, build_tool_started
```

### Module-Level Constants

```python
BUDGET_LIMITS: dict[str, int] = {"LOW": 5, "MEDIUM": 10, "HIGH": 20, "CRISIS": 3}
```

### Front Tier Allowlists (defined in dispatcher.py)

| Tier | Allowed Tools |
|------|--------------|
| **LOW** | update_beliefs, update_scoreboard, update_clarifications, update_narrative, refine_affect, recall_memory, summarize_context, dispatch_task |
| **MEDIUM** | LOW + promote_belief |
| **HIGH** | Same as MEDIUM |
| **CRISIS** | ∅ (empty — Front doesn't run ReAct in CRISIS) |

### Back Tier Allowlists (duplicated in dispatcher.py)

| Tier | Allowed Tools |
|------|--------------|
| **LOW** | recall_memory, discover_capabilities, invoke_capability, submit_result |
| **MEDIUM** | LOW + spawn_via_fabric, execute_workflow |
| **HIGH** | Same as MEDIUM |

### Function: `validate_arguments`

```python
def validate_arguments(
    tool_name: str,
    arguments: dict,
    schema: dict,
) -> list[str]
```
- Draft-7 JSON Schema validation via `jsonschema`
- Returns empty list on valid, list of error strings on invalid
- Gracefully skips if `jsonschema` not installed

### Class: `DispatchRecord`

```python
@dataclass
class DispatchRecord:
    tool_name: str
    arguments: dict[str, Any]
    result: ToolResult
    timestamp_ms: int
    iteration: int
```

### Class: `ToolDispatcher`

```python
class ToolDispatcher:
    def __init__(
        self,
        actor: str,                       # "front" or "back"
        allowlist: set[str],
        tool_schemas: dict[str, ToolSchema],
        ctx: ToolContext,
        tier: str = "LOW",
        bus: IBus | None = None,
    )
```

**Attributes:**
- `actor: str`
- `allowlist: frozenset[str]`
- `tool_schemas: dict[str, ToolSchema]`
- `ctx: ToolContext`
- `tier: str`
- `call_count: int`
- `call_history: list[DispatchRecord]`
- `_budget_limit: int` (from config)
- `_bus: IBus | None`

**Methods:**

#### `async dispatch(self, tool_call: ToolCallResult) -> ToolResult`
The 7-step pipeline:
1. **Allowlist check** — tool must be in actor's allowlist
2. **Budget check** — `call_count < budget_limit` (`submit_result` exempt)
3. **Schema validation** — JSON Schema validation of arguments
4. **Safety band check** — CRISIS tier blocks side-effect tools
5. **Dispatch** — calls `execute_tool(name, args, ctx)` (async-aware)
6. **Bus events** — emits `tool.started` and `tool.completed` events
7. **Record** — increments `call_count`, appends `DispatchRecord`

#### `budget_remaining -> int` (property)
#### `is_budget_exhausted -> bool` (property)
#### `get_call_history(self) -> list[DispatchRecord]`
#### `reset(self) -> None` — reset for new turn

### Factory Functions

#### `create_front_dispatcher`
```python
def create_front_dispatcher(
    tier: str,
    ctx: ToolContext,
    schemas: list[ToolSchema] | None = None,
    bus: IBus | None = None,
) -> ToolDispatcher
```

#### `create_back_dispatcher`
```python
def create_back_dispatcher(
    tier: str,
    ctx: ToolContext,
    schemas: list[ToolSchema] | None = None,
    bus: IBus | None = None,
) -> ToolDispatcher
```

Both factories:
- Default schemas from `FRONT_TOOL_SCHEMAS` / `BACK_TOOL_SCHEMAS` if None
- Set `ctx.actor` to `"front"` / `"back"`
- Build `name -> ToolSchema` map via `_build_schema_map()`

---

## 7. tools/implementations.py — Real Tool Implementations {#7-implementations}

**Purpose:** Real SS-integrated tool execution functions. NOT stubs. Interacts with SessionState sections via `ToolContext`.

### Cross-Component Imports
```python
from k1.concierge.fabric.ports import IFabricPort
from k1.concierge.task.complexity import ComplexityTier
from k1.concierge.task.dispatch import TaskDispatch
from k1.concierge.task.intent import TaskIntent
from k1.concierge.tools.result_protocol import ToolResult
from k1.fabric.types import CapabilityRequest
from k1.sessionstate.ports.writer import BatchRequest, MutationRequest
```

### Class: `ToolContext`

```python
@dataclass
class ToolContext:
    session_manager: Any            # SessionStateManager (M02)
    cognitive_trace_id: str = ""
    actor: str = "front"
    writer_port: Any = None         # IWriterPort (M4 E4.2.1)
    bundle_idempotency_cache: dict = None  # M4 E4.3.1 per-session dedup
    active_device_id: str | None = None    # M5 E5.5.6
    hil_coordinator: Any = None            # M6 E6.1.3 HILCoordinator
    active_task_id: str | None = None      # M6 E6.1.3
    fabric_port: IFabricPort | None = None # M2 typed K1 Fabric port
    recall_fn: Callable | None = None      # K0 long-term memory callback
    capability_cache: dict | None = None   # Per-session discover_capabilities cache
```

### Tool Registry

```python
TOOL_REGISTRY: dict[str, Callable[[dict, ToolContext], ToolResult]] = {}

def _register(name: str):  # Decorator to populate TOOL_REGISTRY
```

### Registered Tool Implementations (16 total)

#### FRONT — Cognitive (6)

##### `execute_update_beliefs(args: dict, ctx: ToolContext) -> ToolResult`
- Reads `beliefs_active` section for existing SPO triples
- Routes through `ctx.writer_port.request_mutation()` for adds/updates
- Returns `{ stored: int, updated: int }`

##### `execute_update_scoreboard(args: dict, ctx: ToolContext) -> ToolResult`
- Handles: qud_push, qud_pop, referent_updates, topic_shift, commitment_add, commitment_fulfill
- Each sub-action routed through `ctx.writer_port.request_mutation()` with `MutationRequest.create()`
- Returns `{ qud_depth, active_referents, open_commitments }`

##### `execute_update_clarifications(args: dict, ctx: ToolContext) -> ToolResult`
- Maps severity to priority: blocking→2, helpful→1, minor→0
- Adds new gaps, resolves existing by `related_entity` match
- Returns `{ open_gaps, blocking_gaps }`

##### `execute_update_narrative(args: dict, ctx: ToolContext) -> ToolResult`
- Actions: `switch` (create or switch_to), `resume` (same logic), `close` (resolve_thread)
- Idempotent: closing non-existent thread succeeds
- Returns `{ active_thread, total_threads }`

##### `execute_refine_affect(args: dict, ctx: ToolContext) -> ToolResult`
- Reads `affective_now` section for previous emotion
- Writes via writer_port: emotion, intensity, valence, arousal, confidence, source
- Returns `{ previous_emotion, updated }`

##### `execute_promote_belief(args: dict, ctx: ToolContext) -> ToolResult`
- Reads `beliefs_active` for fact lookup
- Tier calculation: confidence ≥0.8→HOT, ≥0.5→WARM, else→COLD
- Returns `{ promoted, from_tier }`

#### FRONT — Bundle (1)

##### `execute_update_session_bundle(args: dict, ctx: ToolContext) -> ToolResult`
- Accepts ordered list of mutations with idempotency_key
- Uses `ctx.writer_port.batch_mutations(BatchRequest)` for batch processing
- Idempotency: caches results in `ctx.bundle_idempotency_cache`
- Status: `"ok"` if all applied, `"error"` if none, `"partial"` if mixed
- Returns `{ applied, rejected, cancelled, stopped_early, details }`

#### SHARED — Read (2)

##### `async execute_recall_memory(args: dict, ctx: ToolContext) -> ToolResult`
- Delegates to `ctx.recall_fn(query, memory_types, max_results)` if wired
- Supports both sync and async `recall_fn` (checks `isawaitable`)
- Returns `{ memories: list, count }`
- POC: returns empty results when no recall_fn

##### `execute_summarize_context(args: dict, ctx: ToolContext) -> ToolResult`
- Reads SS sections, uses `get_metadata()` if available
- Rough token estimate: 4 chars per token
- Truncates to `target_tokens` if needed
- Returns `{ compressed, original_tokens, compressed_tokens }`

#### FRONT — Control (1)

##### `execute_dispatch_task(args: dict, ctx: ToolContext) -> ToolResult`
- Validates `depends_on` must start with `"task-"` (strips non-ID values)
- Auto-detects tier from SS `control.get_complexity_tier()` when tier=`"AUTO"`
- Normalizes urgency aliases: `"high"→"urgent"`, `"low"→"background"`
- Builds `TaskDispatch` with `TaskIntent.from_dict()` for each intent
- Returns `{ queued: true, task_id, _dispatch: <full payload> }`
- `_dispatch` stashed for FSM handler to emit as bus event

#### BACK — Read (1 exclusive)

##### `async execute_discover_capabilities(args: dict, ctx: ToolContext) -> ToolResult`
- Per-session cache: `ctx.capability_cache` keyed by `(intent.lower(), domain.lower())`
- Delegates to `ctx.fabric_port.discover_capabilities(intent, domain, top_k=10)`
- Returns `{ capabilities: list of { name, description, domain, score }, count }`

#### BACK — Action (3)

##### `async execute_invoke_capability(args: dict, ctx: ToolContext) -> ToolResult`
- **M6 E6.1.3 HITL safety:** Checks `ctx.hil_coordinator.get_pending_request()` before execution
  - Blocks if HITL pending → `status="blocked"`, error `"HITL pending"`
  - Checks `validate_before_invoke()` → may return `"block_red"` or `"block_needs_approval"`
- Creates `CapabilityRequest(capability_name, params, session_id, trace_id, caller, caller_id)`
- Delegates to `ctx.fabric_port.execute(request)`
- Returns `{ result, duration_ms, status }`
- POC fallback: returns `{ _poc: true, capability, params }`

##### `async execute_batch_invoke_capabilities(args: dict, ctx: ToolContext) -> ToolResult`
- Iterates invocations sequentially, each through `ctx.fabric_port.execute()`
- Returns `{ results: array, total, succeeded, failed }`

##### `async execute_spawn_via_fabric(args: dict, ctx: ToolContext) -> ToolResult`
- Creates `CapabilityRequest` with `capability_name=f"agent.{agent_type}"`
- Delegates to `ctx.fabric_port.execute()`
- POC fallback: generates `agent-{hex12}` ID, returns `{ agent_id, status="spawned", estimated_duration_ms=5000 }`

##### `async execute_execute_workflow(args: dict, ctx: ToolContext) -> ToolResult`
- Creates `CapabilityRequest` with `capability_name=f"workflow.{workflow_id}"`
- Delegates to `ctx.fabric_port.execute()`
- POC fallback: generates `exec-{hex12}` ID, returns `{ execution_id, status="completed", result }`

#### BACK — Control (1)

##### `execute_submit_result(args: dict, ctx: ToolContext) -> ToolResult`
- Validates `result_type` ∈ `{"complete", "needs_human"}`
- For `"complete"`: stashes `final_answer`, `results`, `artifacts_created`
- For `"needs_human"`: stashes `hil_type`, `question`, `options`, `side_effects`
- Generates `weave-{hex12}` event ID
- Returns `{ delivered: true, weave_event_id, _submission: <full payload> }`

### Top-Level Function

#### `async execute_tool(tool_name: str, args: dict, ctx: ToolContext) -> ToolResult`
- Looks up `TOOL_REGISTRY[tool_name]`
- Calls function; awaits if coroutine (transparent async support)
- On unknown tool: returns error `"Unknown tool: {name}"`
- On exception: returns error `"Tool execution failed: {e}"`, logs full traceback

---

## 8. react/\_\_init\_\_.py {#8-reactinit}

**Purpose:** Re-export hub for the react subsystem.

### Re-exports

| Symbol | Source |
|--------|--------|
| `build_chat_history`, `build_chat_history_for_back` | `history` |
| `react_loop`, `ReactResult`, `_resolve_tool_choice` | `loop` |
| `DEFAULT_FRONT_MAX_ITERATIONS` (6), `DEFAULT_BACK_MAX_ITERATIONS` (10) | `loop` |
| `MODE_MAX_ITERATIONS`, `CRISIS_MAX_ITERATIONS` | `loop` |
| `FRONT_DEGENERATE_FALLBACK`, `FRONT_BUDGET_FALLBACK` | `loop` |
| `get_mode_max_iterations`, `get_crisis_max_iterations` | `loop` |

---

## 9. react/history.py — Chat History Helpers {#9-history}

**Purpose:** Build chat message lists from `history_active` for LLM context windows.

### Cross-Component Imports
```python
from k1.concierge.llm.types import ModelMessage
```

### Functions

#### `build_chat_history(history_active: list[Any], window: int = 3) -> list[ModelMessage]`
- Filters for `entry_type ∈ {"user", "final", "proactive"}`
- Takes last `window * 2` entries
- Maps: `"user"` → role `"user"`, `"final"/"proactive"` → role `"assistant"`
- Used by **Front** actor

#### `build_chat_history_for_back(history_active: list[Any], window: int = 3) -> list[ModelMessage]`
- Filters for `entry_type ∈ {"user", "final", "hitl_response"}`
- Takes last `window` entries (NOT pairs)
- Truncates text to **500 chars**
- Maps: `"user"/"hitl_response"` → `"user"`, `"final"` → `"assistant"`
- Used by **Back** actor

---

## 10. react/loop.py — Shared ReAct Loop {#10-loop}

**Purpose:** Single async ReAct loop implementation for both Front and Back actors. Handles LLM calls, tool dispatch, termination detection, cancellation, budget enforcement, streaming, validation, and degenerate response recovery.

### Cross-Component Imports
```python
from k1.model_hub.ports import IModelHubPort
from k1.model_hub.types import (
    CapabilityType, ChatPayload, ChatResult, FinishReason as K1FinishReason,
    HubChunk, HubRequest, HubResponse, Message as K1Message,
    ReasonResult, RequestConstraints, StructuredResult,
    ToolCallPayload, ToolCallResult as K1ToolCallResult,
    ToolCallResultSet, ToolDefinition as K1ToolDefinition,
)
from k1.concierge.config import get_config
from k1.concierge.llm.types import (
    ConciergeModelResponse, FinishReason, ModelMessage, StreamChunk,
    ToolCallResult, ToolSchema, tool_result_to_message as _tool_result_to_msg,
)
from k1.concierge.llm.validator import LLMOutputValidator, ValidationResult
from k1.concierge.task.parallel_safety import classify_tool_batch
from k1.concierge.tools.dispatcher import ToolDispatcher
from k1.concierge.tools.result_protocol import ToolResult
```

### Type Conversion Helpers (K1 ↔ POC Bridge)

#### `_to_k1_messages(msgs: list[ModelMessage]) -> list[K1Message]`
- Converts POC ModelMessages to K1 Messages for HubRequest

#### `_to_k1_tools(tools: list[ToolSchema]) -> list[K1ToolDefinition]`
- Converts POC ToolSchemas to K1 ToolDefinitions

#### `_unwrap_response(hub_resp: HubResponse) -> ConciergeModelResponse`
- Converts K1 HubResponse back to POC ConciergeModelResponse
- Handles `ToolCallResultSet`, `StructuredResult`, `ReasonResult` subtypes

#### `_unwrap_chunk(hub_chunk: HubChunk) -> StreamChunk`
- Converts K1 HubChunk to POC StreamChunk for streaming

### Constants

```python
DEFAULT_FRONT_MAX_ITERATIONS: int = 6
DEFAULT_BACK_MAX_ITERATIONS: int = 10

MODE_MAX_ITERATIONS: dict[str, int] = {
    "STANDARD": 6, "CLARIFY_ASK": 3, "CLARIFY_RESOLVE": 5,
    "HITL_RELAY": 1, "HITL_RESOLVE": 3, "PRESENT": 3,
    "WEAVE": 3, "CANCEL": 3, "INTERRUPT": 6, "ERROR": 2,
}

CRISIS_MAX_ITERATIONS: dict[str, int] = {
    "STANDARD": 4, "CLARIFY_ASK": 2, "CLARIFY_RESOLVE": 4,
    "HITL_RELAY": 1, "HITL_RESOLVE": 2, "PRESENT": 2,
    "WEAVE": 2, "CANCEL": 2, "INTERRUPT": 4, "ERROR": 2,
}

FRONT_DEGENERATE_FALLBACK: str = "Let me think about that for a moment."
FRONT_BUDGET_FALLBACK: str = "Let me get back to you on that."
```

### Config Accessor Functions

#### `get_mode_max_iterations() -> dict[str, int]`
- Delegates to `get_config().prompt.max_iterations`

#### `get_crisis_max_iterations() -> dict[str, int]`
- Delegates to `get_config().prompt.crisis_iterations`

### Class: `ReactResult`

```python
@dataclass
class ReactResult:
    status: str                          # "complete" | "suspended" | "cancelled" | "budget_exhausted"
    text: str | None = None              # Front: final response. Back: None.
    data: dict | None = None             # Back: submit_result() args. Front: None.
    dispatched_tasks: list[dict]         # L3: dispatch_task calls
    parallel_tool_calls: int = 0         # M3 E3.7.4 observability
    sequential_tool_calls: int = 0
    iteration_durations_ms: list[int]    # Per-iteration wall-clock ms
```

### Function: `_resolve_tool_choice`

```python
def _resolve_tool_choice(iteration: int, actor: str, tools: list[ToolSchema]) -> str
```
- Front, iteration 0, tools available → `"required"` (forces first tool call)
- All other cases → `"auto"`

### Function: `_result_to_dict`

```python
def _result_to_dict(result: ToolResult) -> dict[str, Any]
```
- Error → `{"error": ..., "tool": ...}`
- Success → `result.data`

### Function: `_streaming_generate` (async)

```python
async def _streaming_generate(
    model: IModelHubPort,
    request: HubRequest,
    on_stream: Callable[[StreamChunk], Awaitable[None]],
) -> ConciergeModelResponse
```
- Consumes `model.stream_execute()` async iterator
- Converts K1 HubChunks to POC StreamChunks
- Falls back to `model.execute()` on `NotImplementedError`/`AttributeError`/exception

### Function: `react_loop` (async) — CORE

```python
async def react_loop(
    actor: str,                                          # "front" or "back"
    system_prompt: str,                                  # From DynamicPromptBuilder
    messages: list[ModelMessage],                        # MUTATED in-place
    tools: list[ToolSchema],                             # Actor-specific
    max_iterations: int,                                 # Mode+affect or tier driven
    model: IModelHubPort,                                # LLM adapter (K1 ModelHub)
    tool_dispatcher: ToolDispatcher,                     # Validates + executes
    on_text_response: Callable[[str], Awaitable[None]],  # Unused internally (compat)
    cancellation_check: Callable[[], Awaitable[bool]],   # Check turn cancellation
    trace_id: str = "",
    scenario: str = "",
    validator: LLMOutputValidator | None = None,
    on_stream: Callable[[StreamChunk], Awaitable[None]] | None = None,
) -> ReactResult
```

#### ReAct Loop Execution Flow

1. **Per-iteration structure:**
   - Restore tools after degenerate retry
   - Cancellation check (returns `ReactResult(status="cancelled")`)
   - Build HubRequest (ChatPayload or ToolCallPayload)
   - LLM call with timeout (`asyncio.wait_for`, from `config.llm.default_timeout_ms`)
   - Streaming for Front via `_streaming_generate()` when `on_stream` provided

2. **Termination conditions:**
   - **Front (L1):** Text response with NO tool calls → final response
   - **Back (L2):** `submit_result()` tool call → structured result
   - **Cancellation:** `cancellation_check()` returns True
   - **Budget exhausted:** `max_iterations` reached

3. **Special iteration behaviors:**
   - **Last iteration (Front):** Strips tools to force text-only output
   - **Last iteration (Back):** Injects nudge message to call `submit_result`
   - **Iteration 0 (Front):** `tool_choice="required"` forces a tool call

4. **Error/edge case handling:**
   - **LLM ERROR finish_reason:** Bail immediately with fallback
   - **LLM timeout:** Return fallback (Front) or budget_exhausted (Back)
   - **Malformed tool call:** Nudge LLM to simplify, continue
   - **Degenerate (no text, no tools):**
     - Front: Retry once with nudge + strip tools; then use saved mixed-response text or fallback
     - Back: Gentle nudge (early iter) or urgent nudge (late iter)
   - **Validation failure:** Use fixed response if available; else degenerate fallback (Front) or continue (Back)

5. **Tool execution within iteration:**
   - Check for `submit_result` in tool calls (Back termination, processed first)
   - `submit_result` alongside other tools: warning logged, submit processed, others skipped
   - Non-terminal tools classified via `classify_tool_batch()` → parallel vs sequential
   - Parallel tools: `asyncio.gather(*[_run_tool(tc) for tc in parallel_tcs])`
   - Sequential tools: dispatched one-by-one
   - Results re-sorted to match LLM's original call order
   - `dispatch_task` results collected in `dispatched_tasks` list with merged `task_id` and `_dispatch`
   - Tool results appended as observations via `_tool_result_to_msg()`

6. **Budget exhaustion (post-loop):**
   - Front: Use `last_text_with_tools` if captured from mixed response, else `FRONT_BUDGET_FALLBACK`
   - Back: Return `budget_exhausted` status

7. **Observability tracking:**
   - `_parallel_count`, `_sequential_count` (M3 E3.7.4)
   - `_iteration_durations` (per-iteration wall-clock ms)

---

## 11. Cross-Component Dependency Map {#11-dependencies}

### From tools/

| Module | External Import | Component |
|--------|----------------|-----------|
| `dispatcher.py` | `k1.bus.ports.bus.IBus` | k1.bus |
| `dispatcher.py` | `k1.concierge.config.get_config` | concierge.config |
| `dispatcher.py` | `k1.concierge.llm.types.ToolCallResult, ToolSchema` | concierge.llm |
| `dispatcher.py` | `k1.concierge.bus.builders.build_tool_completed, build_tool_started` | concierge.bus (optional) |
| `implementations.py` | `k1.concierge.fabric.ports.IFabricPort` | concierge.fabric |
| `implementations.py` | `k1.concierge.task.complexity.ComplexityTier` | concierge.task |
| `implementations.py` | `k1.concierge.task.dispatch.TaskDispatch` | concierge.task |
| `implementations.py` | `k1.concierge.task.intent.TaskIntent` | concierge.task |
| `implementations.py` | `k1.fabric.types.CapabilityRequest` | k1.fabric |
| `implementations.py` | `k1.sessionstate.ports.writer.BatchRequest, MutationRequest` | k1.sessionstate |
| `schemas_front.py` | `k1.concierge.llm.types.ToolSchema` | concierge.llm |
| `schemas_back.py` | `k1.concierge.llm.types.ToolSchema` | concierge.llm |
| `schemas_back.py` | `k1.concierge.tools.schemas_front.RECALL_MEMORY_SCHEMA` | tools.schemas_front |
| `result_protocol.py` | `k1.concierge.llm.types.ToolResultMessage` | concierge.llm |

### From react/

| Module | External Import | Component |
|--------|----------------|-----------|
| `loop.py` | `k1.model_hub.ports.IModelHubPort` | k1.model_hub |
| `loop.py` | `k1.model_hub.types.*` (12+ types) | k1.model_hub |
| `loop.py` | `k1.concierge.config.get_config` | concierge.config |
| `loop.py` | `k1.concierge.llm.types.*` (8 types) | concierge.llm |
| `loop.py` | `k1.concierge.llm.validator.LLMOutputValidator, ValidationResult` | concierge.llm |
| `loop.py` | `k1.concierge.task.parallel_safety.classify_tool_batch` | concierge.task |
| `loop.py` | `k1.concierge.tools.dispatcher.ToolDispatcher` | concierge.tools |
| `loop.py` | `k1.concierge.tools.result_protocol.ToolResult` | concierge.tools |
| `history.py` | `k1.concierge.llm.types.ModelMessage` | concierge.llm |

### External K1 Components Depended On

| Component | Used By | Purpose |
|-----------|---------|---------|
| `k1.bus` | dispatcher | Emit tool lifecycle events |
| `k1.model_hub` | react/loop | LLM execution (chat, tool_call, streaming) |
| `k1.fabric` | implementations | `CapabilityRequest` type for Fabric port |
| `k1.sessionstate` | implementations | `MutationRequest`, `BatchRequest` for write-path |

---

## 12. Tool Registry Summary Table {#12-tool-registry}

| # | Tool Name | Actor | Category | Side Effects | Async | HITL Guard |
|---|-----------|-------|----------|-------------|-------|------------|
| 1 | `update_beliefs` | front | cognitive | Yes | No | No |
| 2 | `update_scoreboard` | front | cognitive | Yes | No | No |
| 3 | `update_clarifications` | front | cognitive | Yes | No | No |
| 4 | `update_narrative` | front | cognitive | Yes | No | No |
| 5 | `refine_affect` | front | cognitive | Yes | No | No |
| 6 | `promote_belief` | front | cognitive | Yes | No | No |
| 7 | `update_session_bundle` | front | cognitive | Yes | No | No |
| 8 | `recall_memory` | both | read | No | **Yes** | No |
| 9 | `summarize_context` | front | read | No | No | No |
| 10 | `dispatch_task` | front | control | No | No | No |
| 11 | `discover_capabilities` | back | read | No | **Yes** | No |
| 12 | `invoke_capability` | back | action | Yes | **Yes** | **Yes** |
| 13 | `batch_invoke_capabilities` | back | action | Yes | **Yes** | No |
| 14 | `spawn_via_fabric` | back | action | Yes | **Yes** | No |
| 15 | `execute_workflow` | back | action | Yes | **Yes** | No |
| 16 | `submit_result` | back | control | No | No | No |

**Total:** 16 registered implementations (10 Front, 7 Back — `recall_memory` shared)

---

## 13. Error Handling Summary {#13-error-handling}

### Tool Dispatcher (7-step pipeline)
1. **Allowlist violation** → `ToolResult(status="error", error="Tool '{name}' not allowed for actor '{actor}'")`
2. **Budget exhaustion** → `ToolResult(status="error", error="Tool budget exhausted")` — `submit_result` exempt
3. **Schema validation failure** → `ToolResult(status="error", error="Invalid arguments: ...")`
4. **CRISIS safety block** → `ToolResult(status="error", error="Side-effect tools blocked in CRISIS tier")`
5. **Bus event emission failures** → silently caught, never break execution

### Tool Implementations
- **Missing required args** → `ToolResult(status="error", error="<field> is required")`
- **writer_port rejection** → `ToolResult(status="error", error=resp.reason)` — early return on any mutation rejection
- **Unknown tool** → `ToolResult(status="error", error="Unknown tool: {name}")`
- **Exception in tool function** → `ToolResult(status="error", error="Tool execution failed: {e}")`, full traceback logged
- **HITL blocking (invoke_capability)** → `ToolResult(status="blocked", error="HITL pending...")`
- **RED safety band** → `ToolResult(status="blocked", error="RED safety band -- execution blocked entirely")`
- **recall_fn exception** → `ToolResult(status="error", error=str(e))`
- **fabric_port exception** → `ToolResult(status="error", error=str(e))`

### ReAct Loop
- **LLM timeout** → `asyncio.TimeoutError` caught → fallback text (Front) or budget_exhausted (Back)
- **LLM ERROR finish_reason** → Immediate bail with fallback
- **Malformed tool call** → Nudge message injected, continue to next iteration
- **Degenerate response** → Retry with nudge + tool stripping (Front), gentle/urgent nudge (Back)
- **Validation failure** → Use fixed response or degenerate fallback
- **submit_result dispatch error** → Error fed back as tool result, LLM retries on next iteration
- **submit_result alongside other tools** → Warning logged, submit processed first, others skipped

---

*End of exhaustive scan for tools/ and react/ subsystems.*
