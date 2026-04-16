# Scan 07: Fabric, Bus, and Orchestrator Integration Subsystems

> **Scope**: 20 Python files across `k1/concierge/fabric/`, `k1/concierge/bus/`, `k1/concierge/orchestrator/`
> **Purpose**: Research-only — map all classes, ports, types, cross-component imports, and integration patterns for ARCHITECTURE.md

---

## PART A: FABRIC SUBSYSTEM (8 files)

### A1. fabric/\_\_init\_\_.py

**Purpose**: Package façade — re-exports CapabilityRegistry, factory, and capability definitions.

**Exports**:

- `CapabilityRegistry` — from `capability_registry`
- `create_demo_registry` — from `capability_registry`
- `DEMO_CAPABILITIES` — from `demo_capabilities`
- `FAMILY_CAPABILITIES` — from `family_capabilities`
- `register_family_capabilities` — from `family_capabilities`

**Cross-component imports**: None (only intra-package).

**Note**: Does NOT export `IFabricPort`, `POCMockBridgeAdapter`, `contract_converter`, `web_capabilities`, or `WEB_CAPABILITIES`. Consumers of those must import the submodule directly.

---

### A2. fabric/capability_registry.py

**Purpose**: In-memory Fabric capability registry for POC. Maps capability names to definitions and async handler callables. Provides fuzzy intent matching (word overlap) for discovery and exact-name dispatch for invocation. Production equivalent: K0 Fabric's 9-step execution pipeline.

**Module-level constructs**:

- `DOMAIN_ALIASES: dict[str, str]` — 40+ domain alias mappings (e.g. `"communication" -> "messaging"`, `"smart_home" -> "iot"`, `"restaurants" -> "search"`)
- `resolve_domain(domain: str) -> str` — normalise domain through aliases

**Classes**:

#### `CapabilityRegistry`

- Base: none
- State:
  - `_capabilities: dict[str, dict[str, Any]]` — name → capability definition dict
  - `_handlers: dict[str, Callable[..., Coroutine[Any, Any, dict[str, Any]]]]` — name → async handler
- Key methods:
  - `register(capability: dict[str, Any], handler: Callable) -> None`
  - `unregister(name: str) -> bool`
  - `count -> int` (property)
  - `list_all() -> list[dict[str, Any]]`
  - `has(name: str) -> bool`
  - `get_definition(name: str) -> dict[str, Any] | None`
  - `async discover(intent: str, domain: str | None = None, constraints: dict | None = None) -> dict[str, Any]` — fuzzy match + domain filter with fallback to intent-only if domain yields 0 results. Returns `{"capabilities": [...], "count": N}` or includes `"hint"` when empty.
  - `_fuzzy_match(intent: str, domain: str | None) -> list[dict]` — core matching; splits intent on whitespace/underscores, checks word overlap in description/name
  - `async invoke(capability_name: str, params: dict, session_id: str | None = None) -> dict` — exact-name dispatch, returns error dict on KeyError
- Class attribute: `UNIVERSAL_CAPABILITIES: set[str]` = `{"tool.execute.web_search", "tool.execute.web_fetch"}` — bypass domain filtering

**Factory function**:

- `create_demo_registry() -> CapabilityRegistry` — loads 7 demo + 31 family + 2 web = 40 total capabilities

**Cross-component imports**: None — self-contained.

**Error handling**: `invoke()` catches all exceptions and returns structured error dict `{"success": False, "error": str(e), ...}`. Never raises.

---

### A3. fabric/contract_converter.py

**Purpose**: Convert POC capability dicts into K1 `CapabilityContract` objects for registration with the real K1 Fabric `CapabilityRegistry`. M6 E6.1.1.

**Cross-component imports**:

- `from k1.fabric.types import CapabilityContract, InputSpec` ← **K1 Fabric types**
- `from k1.concierge.fabric.demo_capabilities import DEMO_CAPABILITIES` (lazy)
- `from k1.concierge.fabric.family_capabilities import FAMILY_CAPABILITIES` (lazy)
- `from k1.concierge.fabric.web_capabilities import WEB_CAPABILITIES` (lazy)

**Functions**:

#### `poc_dict_to_contract(cap_dict: dict[str, Any]) -> CapabilityContract`

- Maps POC dict fields to K1 CapabilityContract constructor:
  - `name` → `name`
  - `description` → `description`
  - `domain` → `domain` as `[domain_str]` list
  - `required_inputs` / `optional_inputs` → `InputSpec(name=n, type="STRING", description=...)` lists
  - `has_side_effects` → `limitations: ["has_side_effects"]`
  - `estimated_cost` → `cost_per_call: float` (parsed from "$X.XX" string)
  - Hardcoded: `version="1.0.0"`, `capabilities=["tool_execution"]`, `provider_type="BRIDGE"`, `provider_id="poc-mock-bridge"`, `provider_endpoint="local://poc-mock-bridge"`, `safety_band_min="GREEN"`, `avg_latency_ms=50`, `max_latency_ms=200`, `availability="ONLINE"`, `ephemeral=True`, `session_scoped=True`

#### `convert_all_poc_capabilities() -> list[CapabilityContract]`

- Converts all 40 POC capabilities (7 demo + 31 family + 2 web) to K1 contracts

**Type compatibility**: Direct dependency on `k1.fabric.types.CapabilityContract` and `k1.fabric.types.InputSpec`. This is the bridge layer between POC dict-based capabilities and K1's typed contract system.

---

### A4. fabric/demo_capabilities.py

**Purpose**: 7 demo capability definitions + 7 async mock handlers across 3 domains: Travel (4), Productivity (2), Shopping (1).

**Module-level constructs**:

- `DEMO_CAPABILITIES: list[dict[str, Any]]` — 7 capability definition dicts
- `DEMO_HANDLERS: dict[str, Any]` — maps capability name → handler function
- `_deterministic_id(prefix: str, seed: str) -> str` — MD5-based deterministic ID (usedforsecurity=False)

**Capability definitions** (each dict has keys: name, description, required_inputs, optional_inputs, has_side_effects, estimated_cost, domain):

| Name | Domain | Side Effects | Artifact Type |
|------|--------|-------------|---------------|
| `tool.execute.hotel_search` | travel | No | None |
| `tool.execute.hotel_booking` | travel | Yes | "booking" |
| `tool.execute.restaurant_search` | travel | No | None |
| `tool.execute.restaurant_booking` | travel | Yes | "booking" |
| `tool.execute.weather_forecast` | productivity | No | None |
| `tool.execute.calendar_create` | productivity | Yes | "appointment" |
| `tool.execute.product_search` | shopping | No | None |

**Mock handlers** (all `async (params: dict) -> dict` with keys: success, data, artifact_type, duration_ms):

- `mock_hotel_search` — 3 results, filters by max_price
- `mock_hotel_booking` — returns confirmation with deterministic ID
- `mock_restaurant_search` — 3 results, filters by cuisine
- `mock_restaurant_booking` — returns reservation confirmation
- `mock_weather_forecast` — returns N-day forecast (max 5)
- `mock_calendar_create` — returns event with deterministic ID
- `mock_product_search` — 3 results, filters by max_price

**Cross-component imports**: None — self-contained.

**Error handling**: No try/except in handlers; exceptions propagate to CapabilityRegistry.invoke() which catches them.

---

### A5. fabric/family_capabilities.py

**Purpose**: 31 family-domain capability definitions + 31 async mock handlers covering: messaging (4), todo/lists (6), chores (3), school (3), health (4), transport (3), IoT (4), family coordination (3), activity prep (1).

**Module-level constructs**:

- `FAMILY_CAPABILITIES: list[dict[str, Any]]` — 31 capability definition dicts
- `FAMILY_HANDLERS: dict[str, Any]` — maps capability name → handler function
- `_deterministic_id(prefix: str, seed: str) -> str` — same pattern as demo_capabilities

**Capability domains breakdown**:

| Domain | Count | Capabilities |
|--------|-------|-------------|
| messaging | 4 | send_message, send_group_message, send_reminder, send_notification |
| productivity | 3 | get_todo_list, add_todo_item, complete_todo_item |
| shopping | 3 | get_grocery_list, add_grocery_item, grocery_order |
| household | 3 | get_chore_schedule, assign_chore, log_chore_complete |
| school | 3 | get_school_schedule, check_homework, school_pickup_status |
| health | 4 | medication_reminder, schedule_appointment, pharmacy_refill, vet_appointment |
| transport | 2 | ride_request, carpool_coordinate |
| logistics | 1 | package_tracking |
| iot | 4 | smart_home_control, set_timer, nap_timer, home_security_status |
| family | 3 | family_calendar, meal_planner, swim_bag_check |
| finance | 1 | family_budget |

**Registration helper**:

- `register_family_capabilities(registry: Any) -> int` — idempotent registration, returns count of newly registered capabilities

**Mock data**: All handlers return realistic, deterministic family scenario data (the "Anderson family" — Alex, Jordan, Riley, Nana Liz, Luna the dog). Very detailed for demo/storyline fidelity.

**Cross-component imports**: None — self-contained.

---

### A6. fabric/poc_bridge_adapter.py

**Purpose**: `POCMockBridgeAdapter` — implements `IBridgePort` protocol so the K1 `BridgeProvider` can dispatch capability requests to POC mock handlers through the standard Fabric execution pipeline. M6 E6.2.1.

**Cross-component imports**:

- `from k1.concierge.fabric.capability_registry import CapabilityRegistry` ← intra-concierge
- `from k1.fabric.ports.bridge_port import BridgeCommandResult, BridgeHealth, IFLRoute` ← **K1 Fabric bridge port types**

**Classes**:

#### `POCMockBridgeAdapter`

- Base: none (structural subtyping — satisfies `IBridgePort` Protocol without explicit inheritance)
- Constructor: `__init__(self, registry: CapabilityRegistry)`
- State: `_registry: CapabilityRegistry`
- Methods (all satisfy `IBridgePort` interface):
  - `async send_command(operation: str, payload: Dict[str, Any], *, trace_id: str = "", timeout_ms: int = 0) -> BridgeCommandResult` — dispatches to POC handler by operation name. Returns `BridgeCommandResult.ok()` or `.fail()`.
  - `async query(operation: str, selectors: Dict[str, Any], *, trace_id: str = "", timeout_ms: int = 0) -> BridgeCommandResult` — delegates to `send_command` (POC has no read-only distinction)
  - `async route_ifl(route: IFLRoute, payload: Dict[str, Any], *, trace_id: str = "") -> BridgeCommandResult` — IFL-addressed routing → `send_command(route.address, ...)`
  - `is_available() -> bool` — always returns True
  - `get_health() -> BridgeHealth` — returns `BridgeHealth(available=True, mode="K0_FULL")`

**Port/adapter pattern**: This is the **critical adapter** that bridges POC capabilities into the K1 Fabric's `BridgeProvider` system. It:

1. Receives commands via IBridgePort protocol (K1 types)
2. Translates to POC handler calls via CapabilityRegistry._handlers
3. Returns K1-typed BridgeCommandResult

**Error handling**: Catches all exceptions in handler dispatch, returns `BridgeCommandResult.fail("handler_error", str(exc), ...)`. Also handles missing handlers with `"not_found"` error. Uses `inspect.isawaitable()` for sync/async handler compatibility.

**Type compatibility**: Uses K1 types `BridgeCommandResult`, `BridgeHealth`, `IFLRoute` directly. Accesses private `_registry._handlers` dict (tight coupling to CapabilityRegistry internals).

---

### A7. fabric/ports.py

**Purpose**: `IFabricPort` — typed Protocol that matches K1 Fabric's public API surface. Enables POC tools to call the Fabric through a typed interface that the real K1 Fabric can satisfy natively after M5 (zero-change swap).

**Cross-component imports**:

- `from k1.fabric.types import CapabilityRequest, CapabilityResult, RetrievalResult` ← **K1 Fabric types**

**Protocols**:

#### `IFabricPort(Protocol)` — `@runtime_checkable`

- Methods:
  - `async execute(request: CapabilityRequest) -> CapabilityResult`
  - `async execute_batch(requests: List[CapabilityRequest], strategy: str = "PARALLEL") -> List[CapabilityResult]`
  - `async discover_capabilities(domain: Optional[List[str]] = None, intent: str = "", safety_band: str = "GREEN", session_context: Optional[Dict[str, Any]] = None, top_k: int = 10) -> RetrievalResult`
  - `async find_relevant_prompts(intent: str = "", domain: Optional[List[str]] = None, safety_band: str = "GREEN", top_k: int = 10) -> RetrievalResult`

**Design**: This is the hexagonal port that all POC tool functions call. During M2-M5, `FabricPOCBridge` satisfies it. After M5, the real K1 `Fabric` instance satisfies it natively.

**Type compatibility**: Uses K1's own `CapabilityRequest`, `CapabilityResult`, `RetrievalResult` directly. The protocol signature matches `k1/fabric/fabric.py Fabric` class public API (L1257-1340).

---

### A8. fabric/web_capabilities.py

**Purpose**: Real web capabilities — DuckDuckGo search and HTTP page fetch. 2 capability definitions + 2 async handlers.

**Module-level constructs**:

- `WEB_CAPABILITIES: list[dict[str, Any]]` — 2 capability definition dicts
- `WEB_HANDLERS: dict[str, Any]` — maps capability name → handler
- HTML extraction helpers: `_STRIP_TAGS`, `_HTML_TAG`, `_MULTI_SPACE`, `_MULTI_NEWLINE` regex patterns
- Safety constants: `_ALLOWED_SCHEMES = {"http", "https"}`, `_FETCH_TIMEOUT = 10`, `_DEFAULT_MAX_CHARS = 6000`, `_ABSOLUTE_MAX_CHARS = 12000`

**Capabilities**:

| Name | Domain | Handler | External dependency |
|------|--------|---------|-------------------|
| `tool.execute.web_search` | search | `web_search_handler` | `ddgs.DDGS` (DuckDuckGo) |
| `tool.execute.web_fetch` | search | `web_fetch_handler` | `httpx.AsyncClient` |

**Functions**:

- `async web_search_handler(params)` — max 10 results, region support. Returns `{title, url, snippet}` list.
- `async web_fetch_handler(params)` — SSRF protection (blocks localhost, private IPs, non-http/https schemes). Extracts readable text from HTML. Truncates to max_chars.
- `_extract_text_from_html(html: str) -> tuple[str, str]` — strips script/style/nav/header/footer/aside tags, decodes entities, normalises whitespace. Returns (title, body_text).
- `register_web_capabilities(registry: Any) -> int` — registers both capabilities into a CapabilityRegistry

**Cross-component imports**: None (standard library + third-party only).

**Security**: SSRF protection validates URL scheme (http/https only) and blocks private IP ranges (localhost, 127.0.0.1, 192.168.x, 10.x, 172.x, ::1). Uses `html.unescape()` for entity decoding.

---

## PART B: BUS SUBSYSTEM (5 files)

### B1. bus/\_\_init\_\_.py

**Purpose**: Package façade — re-exports the entire bus public API from submodules + K1 bus protocol types.

**Cross-component imports**:

- `from k1.bus.ports.bus import BusHandler, IBus, SubscriptionHandle` ← **K1 bus protocols**
- `from k1.bus.ports.mailbox import IMailbox, IMailboxRouter, MailboxConfig` ← **K1 mailbox protocols**
- All builder functions from `builders`
- All setup functions from `setup`
- All topic constants from `topics`

**Re-exported K1 types**: `IBus`, `BusHandler`, `SubscriptionHandle`, `IMailbox`, `IMailboxRouter`, `MailboxConfig`

**Re-exported concierge types**: All 28+ `TOPIC_*` constants, all `build_*` builder functions, setup functions (`create_poc_bus`, `create_poc_router`, etc.), classification sets (`ALL_TOPICS`, `STRICT_TOPICS`, etc.)

---

### B2. bus/builders.py

**Purpose**: Envelope builder functions for 45+ POC bus topics. Each builder produces a ready-to-publish `Envelope` with correct topic string, priority per V2 Section 3, JSON-serialized payload, and parent_id for causal chaining.

**Cross-component imports**:

- `from k1.bus.envelope import Envelope, PayloadFormat, Priority` ← **K1 bus envelope types**
- `from k1.concierge.bus.topics import TOPIC_*` — all 45+ topic constants
- `from k1.concierge.events.base import CanonicalEventMeta` — V3 canonical event base
- `from k1.concierge.config.loader import get_config` — config for validation flag
- `from k1.concierge.events.validator import validate_event` — canonical event validation
- `from k1.concierge.events.conversation import IntentArbitrated, UserInputReceived` (lazy)
- `from k1.concierge.events.hitl import HILRequested, HILResolved, HITLBlockedRedEvent, HITLRequestedEvent, HITLResolvedEvent, HITLTimedOutEvent, TaskResumed, TaskSuspended` (lazy)
- `from k1.concierge.events.task import TaskCancelled, TaskCompleted, TaskCreated, TaskFailed` (lazy)

**Module-level constructs**:

- `SYNTHETIC_ID_START = 1_000_000_000` — counter start for synthetic envelope IDs
- `_synthetic_id_counter = itertools.count(start=SYNTHETIC_ID_START)` — thread-safe counter
- `next_synthetic_envelope_id() -> int` — unique IDs for envelopes bypassing the bus

**Internal helpers**:

- `_serialize(payload) -> bytes` — JSON serialization. Handles both `CanonicalEventMeta` subclasses (calls `to_payload()`) and legacy dicts (auto-enriches with `event_id`, `ts_utc`, `payload_schema_version`).
- `_build(topic, priority, payload, parent_id=0) -> Envelope` — core builder. Optional canonical event validation when `bus.validate_canonical_events` config flag is enabled. Soft validation (logs warnings, never blocks).

**Builder functions** (each: `(payload: dict | CanonicalEventMeta, parent_id: int = 0) -> Envelope`):

| Category | Builders | Priority |
|----------|---------|----------|
| Session (STRICT) | `build_user_input`, `build_artifact_created`, `build_turn_started`, `build_turn_completed`, `build_state_updated` | URGENT / INTERACTIVE / BACKGROUND |
| Response (STRICT) | `build_response_stream`, `build_final_response`, `build_clarification_out` | URGENT |
| Orchestration (STRICT) | `build_task_dispatch`, `build_task_complete`, `build_task_failed`, `build_task_cancel`, `build_task_suspended`, `build_task_resume`, `build_task_accepted`, `build_task_modify`, `build_findings_ready`, `build_clarification_request`, `build_clarification_response`, `build_orchestration_delta`, `build_dag_completed` | INTERACTIVE / URGENT (cancel) |
| Tool (STRICT) | `build_tool_started`, `build_tool_completed` | INTERACTIVE |
| HITL (STRICT) | `build_hil_request`, `build_hil_response` | INTERACTIVE / URGENT |
| HITL lifecycle (M6) | `build_hitl_requested`, `build_hitl_resolved`, `build_hitl_timed_out`, `build_hitl_blocked_red` | INTERACTIVE |
| Planner (STRICT) | `build_plan_ready` | INTERACTIVE |
| Internal (STRICT) | `build_weave_batch`, `build_dead_letter` | INTERACTIVE / BACKGROUND |
| Relaxed | `build_affect_update`, `build_proactive_fill`, `build_ui_typing`, `build_weave_decided`, `build_weave_metrics` | BACKGROUND |
| Phase1/Routing (M10) | `build_phase1_classified`, `build_task_routed` | BACKGROUND |
| Observability (M11) | `build_metric_emitted`, `build_metric_alert`, `build_metric_session_summary` | BACKGROUND |
| Arbiter (M5) | `build_intent_arbitrated` | INTERACTIVE |
| BackPool (M7) | `build_backpool_worker_acquired`, `build_backpool_worker_released`, `build_task_leased` | BACKGROUND |

**Registry constructs**:

- `BuilderEntry(NamedTuple)` — `builder_fn`, `canonical_type` (V3 event class or None), `priority`
- `BUILDERS: dict[str, Any]` — flat dict: topic → builder function (legacy compat)
- `get_builder_registry() -> dict[str, BuilderEntry]` — enriched registry with canonical types. Lazy-loads canonical event classes to avoid circular imports.

**Canonical type mappings** (topics that have V3 schemas):

- `TOPIC_USER_INPUT` → `UserInputReceived`
- `TOPIC_TASK_DISPATCH` → `TaskCreated`
- `TOPIC_TASK_COMPLETE` → `TaskCompleted`
- `TOPIC_TASK_FAILED` → `TaskFailed`
- `TOPIC_TASK_CANCEL` → `TaskCancelled`
- `TOPIC_TASK_SUSPENDED` → `TaskSuspendedEvt`
- `TOPIC_TASK_RESUME` → `TaskResumedEvt`
- `TOPIC_HIL_REQUEST` → `HILRequested`
- `TOPIC_HIL_RESPONSE` → `HILResolved`
- `TOPIC_INTENT_ARBITRATED` → `IntentArbitrated`
- `TOPIC_HITL_REQUESTED` → `HITLRequestedEvent`
- `TOPIC_HITL_RESOLVED` → `HITLResolvedEvent`
- `TOPIC_HITL_TIMED_OUT` → `HITLTimedOutEvent`
- `TOPIC_HITL_BLOCKED_RED` → `HITLBlockedRedEvent`

**Causal chain rules**:

- User input: always root (`parent_id=0`)
- Task dispatch: `parent_id` = user input `envelope_id`
- Task complete/failed: `parent_id` = task dispatch `envelope_id`
- Final response: `parent_id` = task complete / dag completed `envelope_id`
- Tool events chain: started → completed (parent_id = started)

---

### B3. bus/deserialize.py

**Purpose**: Inverse of builder serialization — deserialize `Envelope` payload bytes into typed canonical events.

**Cross-component imports**:

- `from k1.concierge.events.base import CanonicalEventMeta` ← canonical event base
- `from k1.concierge.events.registry import deserialize_event` ← event type registry

**Functions**:

#### `deserialize_envelope(envelope: Any) -> CanonicalEventMeta | None`

- Extracts `envelope.payload` bytes → JSON parse → checks for `event_type` field → delegates to `deserialize_event()` from event registry
- Returns `None` for: empty payload, invalid JSON, non-dict, missing `event_type` (legacy payload), unregistered `event_type`

#### `parse_payload(envelope: Any) -> dict[str, Any]`

- Backward-compatible helper — always returns a dict regardless of canonical/legacy
- Adds `_canonical: True` marker for canonical payloads (has both `event_type` and `event_id`)

**Error handling**: All JSON parse failures return `None` or `{}`. No exceptions propagated.

---

### B4. bus/setup.py

**Purpose**: Bus infrastructure factory — thin wrappers around `BusFactory` that apply POC-specific defaults. Called once at boot time. Returns real K1 objects (no mocks).

**Cross-component imports**:

- `from k1.bus.adapters.session_adapter import SessionBusAdapter` ← **K1 bus adapter**
- `from k1.bus.factory import BusFactory` ← **K1 bus factory**
- `from k1.bus.middleware import MiddlewareChain` ← **K1 middleware**
- `from k1.bus.middleware.metrics import MetricsMiddleware` ← **K1 middleware**
- `from k1.bus.middleware.topic_validation import TopicRegistry, TopicValidationMiddleware` ← **K1 middleware**
- `from k1.bus.middleware.tracing import TracingMiddleware` ← **K1 middleware**
- `from k1.bus.ports.bus import IBus` ← **K1 bus port**
- `from k1.bus.ports.mailbox import IMailbox, IMailboxRouter, MailboxConfig` ← **K1 mailbox ports**
- `from k1.concierge.config import get_config` ← Concierge config

**Module-level constants**:

- `ACTOR_FRONT = "front_half"` — backward-compat alias
- `ACTOR_BACK = "back_half"` — backward-compat alias

**Functions**:

#### `_build_middleware_chain(cfg) -> MiddlewareChain | None`

- Order: TopicValidation → Tracing → Metrics (matches K1 design doc)
- TopicValidation: registers all `ALL_TOPICS` + dynamic prefixes `"k1.agent."` and `"k1.session."`
- Each middleware toggled by config flags: `cfg.topic_validation_enabled`, `cfg.tracing_enabled`, `cfg.metrics_enabled`

#### `create_poc_bus(*, capture: bool = False) -> IBus`

- Creates `BusFactory.create_local_ordered()` with middleware chain
- Params from config: `timeout_ms=cfg.gap_timeout_ms`

#### `create_poc_router() -> IMailboxRouter`

- Creates `BusFactory.create_mailbox_router(backend="python")`

#### `create_poc_session_adapter(bus: IBus) -> SessionBusAdapter`

- Wraps bus with `SessionBusAdapter` — maps SessionState events to `k1.session.{event_type}` topics

#### `register_poc_actors(router: IMailboxRouter) -> tuple[IMailbox, IMailbox]`

- Registers "front_half" and "back_half" actors with config-driven `MailboxConfig(capacity=cfg.mailbox_capacity, priority_wfq=cfg.priority_wfq)`
- Returns (front_mailbox, back_mailbox)

**Port/adapter pattern**: This module is the **boot-time wiring** layer. It composes K1 bus infrastructure (LocalBus, MailboxRouter, SessionBusAdapter, MiddlewareChain) with POC-specific configuration. All values come from `get_config().bus.*`.

---

### B5. bus/topics.py

**Purpose**: SINGLE SOURCE OF TRUTH for all POC bus topic constants. Authoritative definition site — no other module may define topic strings.

**Cross-component imports**: None — purely constants.

**Topic constants** (45 total, organized by prefix):

| Prefix | Topics | Delivery | Count |
|--------|--------|----------|-------|
| `k1.session.*` | user.input, artifact.created, turn.started, turn.completed, state.updated | STRICT | 5 |
| `k1.response.*` | stream, final, clarification | STRICT | 3 |
| `k1.orchestration.*` | task.dispatch/complete/failed/cancel/suspended/resume/accepted/modify, findings.ready, clarification.request/response, delta, dag.completed | STRICT | 13 |
| `k1.tool.*` | started, completed | STRICT | 2 |
| `k1.hil.*` | request, response | STRICT | 2 |
| `k1.hitl.*` | requested, resolved, timed_out, blocked_red | STRICT | 4 |
| `k1.planner.*` | plan.ready | STRICT | 1 |
| `k1.internal.*` | weave.batch, dead_letter | STRICT | 2 |
| `k1.backpool.*` | worker.acquired, worker.released, task.leased | STRICT | 3 |
| `k1.arbiter.*` | intent | STRICT | 1 |
| `k1.phase1.*` / `k1.task.*` | classified, routed | RELAXED | 2 |
| `k1.affect.*` | update | RELAXED | 1 |
| `k1.proactive.*` | fill | RELAXED | 1 |
| `k1.ui.*` | typing | RELAXED | 1 |
| `k1.conversation.*` | weave.decided | RELAXED | 1 |
| `k1.metrics.*` | weave, emitted, alert, session_summary | RELAXED | 4 |

**Classification sets**:

- `ALL_TOPICS: frozenset[str]` — all 45 topic strings
- `STRICT_TOPICS: frozenset[str]` — ALL_TOPICS minus 10 RELAXED = 35 topics
- `RELAXED_TOPICS: frozenset[str]` — 10 topics
- `URGENT_TOPICS: frozenset[str]` — 6 topics: user_input, response_stream, final_response, clarification_out, task_cancel, hil_response

**Subscription groups**:

- `FSM_ROUTED_TOPICS: frozenset[str]` — 8 topics routed by FSM directly (task_complete, task_failed, task_suspended, findings_ready, clarification_request, dag_completed, weave_batch, proactive_fill). **Must NOT appear in FRONT_SUBSCRIPTIONS** (enforced with assert at import time).
- `FRONT_SUBSCRIPTIONS: frozenset[str]` — 4 topics: task_accepted, orchestration_delta, hil_request, plan_ready
- `BACK_SUBSCRIPTIONS: frozenset[str]` — 7 topics: user_input, task_dispatch, task_cancel, task_resume, clarification_response, hil_response, affect_update

**Priority mapping**:

- `_TOPIC_PRIORITY: dict[str, int]` — topic → Priority int value
- `get_priority(topic: str) -> int` — defaults to INTERACTIVE (2)

**Routing invariant enforcement**: Assert at import time verifies `FSM_ROUTED_TOPICS.isdisjoint(FRONT_SUBSCRIPTIONS)`. Prevents duplicate delivery (FSM + direct subscription).

**HITL routing clarification** (documented in comments):

- `task.suspended` / `task.resume` = FSM lifecycle events (state transitions)
- `hil.request` / `hil.response` = protocol-level detail (carry HITL question/answer payload)
- Flow: Back → `task.suspended` → FSM → Front → `hil.request` → User → Front → `hil.response` → Back → Front → `task.resume`

---

## PART C: ORCHESTRATOR SUBSYSTEM (7 files)

### C1. orchestrator/\_\_init\_\_.py

**Purpose**: Package façade — re-exports all types, ports, stub, routing, degradation, and interfaces.

**Exports**:

- **Types**: `TaskEnvelope`, `Budget`, `AggregatedResult`, `CapabilityRequest`, `CapabilityResult`, `StepResult`, `CannedResponse`, `PlanRequest`, `CommittedPlan`, `PlanStep`
- **Ports**: `IFabricGatewayPort`, `IStateReadPort`, `IDeltaEmitPort`, `IDispatchPort`, `IPlannerPort`, `IWorkflowPort`, `IConnectorPort`, `IConstraintPort`, `ISagaPort`
- **Routing**: `route_task`, `DispatchRecord`
- **Degradation**: `route_task_with_degradation`, `CircuitBreaker`, `cb_planner`, `cb_orchestrator`, `cb_fabric`, `get_effective_tier`
- **Stub**: `OrchestratorStub`, `BudgetExceededError`
- **Interfaces**: `IDAGExecutor`, `IPlannerService`, `IWorkflowEngine`, `IConnectorManager`, `IConstraintResolver`, `ISagaRecovery`, `HIGH_TIER_EVENTS`

---

### C2. orchestrator/types.py

**Purpose**: All orchestrator types for tier routing and execution. Self-contained within concierge package — does NOT import from `k1.fabric` or `k1.orchestrator`.

**Cross-component imports**:

- `from k1.concierge.config import get_config` ← config for budget defaults
- `from k1.concierge.task.complexity import ComplexityTier` ← tier enum

**Classes** (all frozen dataclasses):

#### `Budget(frozen=True)`

- Fields: `max_fabric_calls: int = 2`, `max_planner_tokens: int = 0`, `timeout_ms: int = 0`
- `__post_init__`: resolves `timeout_ms=0` sentinel from config (`orchestrator.default_budget_timeout_ms`), validates non-negative values

#### `TaskEnvelope(frozen=True)`

- Fields: `intent: str`, `task_id: str` (auto-generated "task-XXXX"), `context: dict`, `tier: ComplexityTier = MEDIUM`, `budget: Budget`, `session_id: str`, `trace_id: str` (auto-generated)
- `__post_init__`: validates intent non-empty, tier must be MEDIUM or HIGH (LOW bypasses Orchestrator)

#### `CapabilityRequest(frozen=True)`

- Fields: `name: str`, `params: dict`, `session_id: str`, `trace_id: str`
- `__post_init__`: validates name non-empty
- **NOTE**: POC-local, NOT imported from `k1.fabric.types`

#### `CapabilityResult(frozen=True)`

- Fields: `success: bool`, `data: dict`, `error: str`, `capability_name: str`, `duration_ms: int`
- **NOTE**: POC-local, NOT imported from `k1.fabric.types`

#### `StepResult(frozen=True)`

- Fields: `step_id: str`, `capability_name: str`, `status: str` (COMPLETED/FAILED/CANCELLED/SKIPPED), `duration_ms: int`, `result: dict`, `error_detail: str`
- `to_dict() -> dict`

#### `AggregatedResult(frozen=True)`

- Fields: `total_steps: int`, `completed: int`, `failed: int`, `results: list`, `success: bool`, `cancelled: int`, `skipped: int`, `step_results: list`, `duration_ms: int`, `trace_id: str`, `result_id: str` (auto-generated), `plan_id: Optional[str]`
- Factory classmethods:
  - `from_medium(capability_result, trace_id, duration_ms) -> AggregatedResult` — single Fabric call
  - `from_multi_step(capability_results, trace_id, duration_ms) -> AggregatedResult` — multiple Fabric calls
- `to_dict() -> dict` — serializes for event payload

#### `CannedResponse(frozen=True)`

- Fields: `text: str` (default fallback message), `reason: str`
- Last-resort fallback when all circuit breakers are open

#### `PlanRequest(frozen=True)` — HIGH tier only, interface

- Fields: `intent: str`, `request_id: str`, `context: dict`, `constraints: dict`, `budget: Budget`, `trace_id: str`
- `__post_init__`: validates intent

#### `PlanStep(frozen=True)` — HIGH tier only, interface

- Fields: `step_id: str`, `capability: str`, `params: dict`, `has_side_effects: bool`, `compensation: Optional[str]`, `timeout_ms: int`, `required_context: list`, `safety_band_min: str`
- `__post_init__`: validates step_id and capability
- `to_dict() -> dict`

#### `CommittedPlan(frozen=True)` — HIGH tier only, interface

- Fields: `plan_id: str`, `request_id: str`, `steps: list[PlanStep]`, `dependencies: dict` (step_id → [dep_step_ids]), `created_at: str`
- `__post_init__`: validates plan_id, request_id, runs cycle detection
- `_detect_cycles()` — DFS-based dependency cycle detection

**Type compatibility analysis**:

- `CapabilityRequest` / `CapabilityResult` are POC-local, deliberately NOT imported from `k1.fabric.types`. This keeps the Orchestrator self-contained within the concierge package.
- `fabric/ports.py` uses K1's `CapabilityRequest`/`CapabilityResult` from `k1.fabric.types` — these are DIFFERENT types with DIFFERENT fields than the orchestrator's local versions.
- This dual-type situation is intentional: `IFabricPort` (fabric/ports.py) uses K1 types for Fabric-level operations, while `OrchestratorStub` (orchestrator/stub.py) uses local types for Orchestrator-level operations.

---

### C3. orchestrator/ports.py

**Purpose**: 9 Protocol classes for hexagonal architecture. All runtime_checkable, all async, no concrete implementations.

**Cross-component imports**:

- `from k1.concierge.orchestrator.types import CapabilityRequest, CapabilityResult, PlanRequest, PlanStep, TaskEnvelope` ← intra-orchestrator types (POC-local)

**Protocols**:

#### Core ports (used by OrchestratorStub — MEDIUM tier)

| Port | Methods | Design ref |
|------|---------|-----------|
| `IFabricGatewayPort` | `execute(request) -> CapabilityResult`, `execute_batch(requests) -> List[CapabilityResult]` | ORCH-04, ORCH-10 |
| `IStateReadPort` | `snapshot(sections) -> Dict`, `read_section(session_id, section) -> Optional[Dict]` | ORCH-01 (read-only, NO write methods) |
| `IDeltaEmitPort` | `emit(event_topic, payload, trace_id) -> None` | Fire-and-forget |
| `IDispatchPort` | `dispatch_envelope(envelope: TaskEnvelope) -> None` | Route to Orchestrator |

#### HIGH tier deferred ports (interface only)

| Port | Methods | Status |
|------|---------|--------|
| `IPlannerPort` | `request_plan(request) -> str`, `cancel_plan(request_id) -> None` | NOT implemented |
| `IWorkflowPort` | `run(request) -> Any` | NOT implemented |
| `IConnectorPort` | `register(mcp_server: dict) -> None` | NOT implemented |
| `IConstraintPort` | `resolve(step, context) -> dict` | NOT implemented |
| `ISagaPort` | `compensate(failed_step, completed_steps) -> None` | NOT implemented |

**Key invariant**: `IStateReadPort` has NO write methods — ORCH-01 enforced structurally. The Orchestrator physically cannot write to Session State.

---

### C4. orchestrator/routing.py

**Purpose**: Single dispatch point for all task routing. `route_task()` is invariant 8 — no alternate dispatch paths.

**Cross-component imports**:

- `from k1.concierge.orchestrator.types import Budget, TaskEnvelope` ← intra-orchestrator
- `from k1.concierge.task.complexity import ComplexityTier` ← task subsystem
- `from k1.concierge.task.dispatch import TaskDispatch` ← task subsystem
- `from k1.concierge.config import get_config` ← config (lazy, inside functions)

**Module-level constants**:

- `TIER_FABRIC_BUDGET: dict[ComplexityTier, int]` — LOW:1, MEDIUM:2, HIGH:10 (backward-compat)
- `TIER_PLANNER_TOKEN_BUDGET: dict[ComplexityTier, int]` — LOW:0, MEDIUM:0, HIGH:3500

**Types**:

- `EmitFn = Callable[..., Any]` — `async emit(topic, payload, priority) -> None`

#### `DispatchRecord` (dataclass)

- Fields: `tier: ComplexityTier`, `topic: str = ""`, `envelope: Optional[TaskEnvelope] = None`, `payload: Any = None`, `priority: str = "INTERACTIVE"`

**Functions**:

#### `async route_task(task: TaskDispatch, tier: ComplexityTier, *, emit_fn=None, dispatch_fn=None) -> DispatchRecord`

- Calls `route_task_sync()` then invokes `emit_fn` (LOW) or `dispatch_fn` (MEDIUM/HIGH) as appropriate.

#### `route_task_sync(task: TaskDispatch, tier: ComplexityTier) -> DispatchRecord`

- Synchronous routing decision for FSM event handlers
- LOW → `_route_low_sync` → `DispatchRecord(tier=LOW, topic="k1.orchestration.task.dispatch.v1")`
- MEDIUM → `_route_medium_sync` → creates `TaskEnvelope` with `Budget(max_fabric_calls=cfg.MEDIUM)`
- HIGH → `_route_high_sync` → creates `TaskEnvelope` with `Budget(max_fabric_calls=cfg.HIGH, max_planner_tokens=cfg.HIGH)`

#### Config-aware budget helpers

- `_get_fabric_budget(tier) -> int` — reads from `get_config().orchestrator.tier_fabric_budget`
- `_get_planner_token_budget(tier) -> int` — reads from `get_config().orchestrator.tier_planner_token_budget`

**Routing paths**:

- **LOW**: Emit envelope to `k1.orchestration.task.dispatch.v1` → Back handles directly via Fabric
- **MEDIUM**: Create `TaskEnvelope` → dispatch to `OrchestratorStub`
- **HIGH**: Create `TaskEnvelope` → dispatch to Orchestrator (future, interface ready)

---

### C5. orchestrator/degradation.py

**Purpose**: Tier degradation cascade — HIGH → MEDIUM → LOW → canned response when circuit breakers trip.

**Cross-component imports**:

- `from k1.concierge.orchestrator.routing import DispatchRecord, EmitFn, route_task` ← routing
- `from k1.concierge.orchestrator.types import CannedResponse` ← types
- `from k1.concierge.task.complexity import ComplexityTier` ← task subsystem
- `from k1.concierge.task.dispatch import TaskDispatch` ← task subsystem
- `from k1.concierge.config import get_config` ← config (lazy)

**Classes**:

#### `CircuitBreaker`

- Fields: `name: str`, `_open: bool = False`
- Methods: `is_open() -> bool`, `force_open()`, `force_closed()`, `reset()`
- Simplified POC version — production has CLOSED/OPEN/HALF_OPEN with failure counting, recovery timeout, half-open probes

**Named circuit breakers** (module-level singletons):

- `cb_planner = CircuitBreaker("CB_PLANNER")` — guards HIGH tier
- `cb_orchestrator = CircuitBreaker("CB_ORCHESTRATOR")` — guards MEDIUM tier
- `cb_fabric = CircuitBreaker("CB_FABRIC")` — guards LOW tier

**Functions**:

#### `async route_task_with_degradation(task, tier, *, emit_fn=None, dispatch_fn=None) -> DispatchRecord | CannedResponse`

- Degradation cascade:
  - HIGH + CB_PLANNER open → MEDIUM
  - MEDIUM + CB_ORCHESTRATOR open → LOW
  - LOW + CB_FABRIC open → `CannedResponse(text=config.orchestrator.canned_response_text, reason="CB_FABRIC_OPEN")`
- Delegates to `route_task()` with effective tier after degradation

#### `get_effective_tier(tier: ComplexityTier) -> ComplexityTier | None`

- Returns effective tier after degradation checks. Returns `None` if all tiers exhausted.

---

### C6. orchestrator/stub.py

**Purpose**: `OrchestratorStub` — minimal Orchestrator for MEDIUM tier tasks. Receives `TaskEnvelope`, makes 1-2 Fabric calls, returns `AggregatedResult`.

**Cross-component imports**:

- `from k1.concierge.orchestrator.ports import IDeltaEmitPort, IFabricGatewayPort, IStateReadPort` ← orchestrator ports
- `from k1.concierge.orchestrator.types import AggregatedResult, CapabilityRequest, CapabilityResult, TaskEnvelope` ← orchestrator types

**Classes**:

#### `BudgetExceededError(Exception)`

- Fields: `max_calls: int`, `attempted: int`
- Message: "ORCH-10 violation: attempted N Fabric calls, budget allows M"

#### `OrchestratorStub`

- Constructor: `__init__(self, fabric_gateway: IFabricGatewayPort, state_read: IStateReadPort, delta_emit: IDeltaEmitPort)` — **exactly 3 ports** (structural enforcement of ORCH-01 through ORCH-03)
- State: `self.fabric`, `self.state`, `self.delta`, `self._fabric_call_count: int`

**Key methods**:

#### `async handle_task(envelope: TaskEnvelope) -> AggregatedResult`

6-step flow:

1. Emit `k1.orchestration.task.accepted` via `delta.emit()`
2. Read context snapshot via `state.snapshot(["beliefs_active", "task_artifacts"])` (ORCH-01: read-only)
3. Resolve capability (known at MEDIUM tier, no discovery)
4. Execute via `fabric.execute(CapabilityRequest(...))` (ORCH-04, ORCH-10)
5. Aggregate result via `AggregatedResult.from_medium()`
6. Emit `k1.orchestration.dag.completed` via `delta.emit()`

#### `async handle_multi_step(envelope: TaskEnvelope, capability_names: list[str]) -> AggregatedResult`

- Handles tasks needing 2 coordinated Fabric calls (max per MEDIUM budget)
- Raises `BudgetExceededError` if `len(capability_names) > budget.max_fabric_calls`
- Uses `AggregatedResult.from_multi_step()`

#### `_check_budget(envelope: TaskEnvelope) -> None`

- Enforces ORCH-10: raises `BudgetExceededError` if exceeding budget

**Hard invariants** (structurally enforced):

- **ORCH-01**: No SS writes — only `IStateReadPort` injected (no write port)
- **ORCH-02**: No LLM calls — no `IConciergeModelPort` dependency
- **ORCH-03**: No tool execution — no `ToolDispatcher` dependency
- **ORCH-04**: Every step through Fabric — only `IFabricGatewayPort` for execution
- **ORCH-10**: Max Fabric calls per budget — `_check_budget()` enforcement

---

### C7. orchestrator/interfaces.py

**Purpose**: HIGH tier deferred interface contracts — NOT IMPLEMENTED in POC. Exist so HIGH tier can plug in without refactoring.

**Cross-component imports**:

- `from k1.concierge.orchestrator.types import AggregatedResult, CommittedPlan, PlanRequest, PlanStep` ← orchestrator types

**Abstract classes** (all ABC):

| Interface | Methods | Production Reference |
|-----------|---------|---------------------|
| `IDAGExecutor` | `execute(plan: CommittedPlan) -> AggregatedResult` | `k1/orchestrator/orchestration/dag_executor.py` |
| `IPlannerService` | `request_plan(request: PlanRequest) -> str`, `cancel_plan(request_id) -> None` | `k1/planner/` |
| `IWorkflowEngine` | `run(request) -> Any` | Production workflow engine |
| `IConnectorManager` | `register(mcp_server: dict) -> None` | MCP server registration |
| `IConstraintResolver` | `resolve(step: PlanStep, context: dict) -> dict` | Runtime parameter resolution |
| `ISagaRecovery` | `compensate(failed_step: PlanStep, completed_steps: List[PlanStep]) -> None` | Saga compensation |

**Constants**:

- `HIGH_TIER_EVENTS: dict[str, str]` — 7 event topic strings for HIGH tier flow:
  - `plan_request`, `plan_ready`, `dag_started`, `dag_wave_completed`, `dag_completed`, `hil_required`, `hil_response`

---

## PART D: CROSS-CUTTING ANALYSIS

### D1. Cross-Component Import Map

| Concierge Module | Imports from K1 Component | Specific types |
|-----------------|---------------------------|----------------|
| `fabric/ports.py` | `k1.fabric.types` | `CapabilityRequest`, `CapabilityResult`, `RetrievalResult` |
| `fabric/contract_converter.py` | `k1.fabric.types` | `CapabilityContract`, `InputSpec` |
| `fabric/poc_bridge_adapter.py` | `k1.fabric.ports.bridge_port` | `BridgeCommandResult`, `BridgeHealth`, `IFLRoute` |
| `bus/__init__.py` | `k1.bus.ports.bus` | `IBus`, `BusHandler`, `SubscriptionHandle` |
| `bus/__init__.py` | `k1.bus.ports.mailbox` | `IMailbox`, `IMailboxRouter`, `MailboxConfig` |
| `bus/builders.py` | `k1.bus.envelope` | `Envelope`, `PayloadFormat`, `Priority` |
| `bus/setup.py` | `k1.bus.adapters.session_adapter` | `SessionBusAdapter` |
| `bus/setup.py` | `k1.bus.factory` | `BusFactory` |
| `bus/setup.py` | `k1.bus.middleware` | `MiddlewareChain` |
| `bus/setup.py` | `k1.bus.middleware.metrics` | `MetricsMiddleware` |
| `bus/setup.py` | `k1.bus.middleware.topic_validation` | `TopicRegistry`, `TopicValidationMiddleware` |
| `bus/setup.py` | `k1.bus.middleware.tracing` | `TracingMiddleware` |
| `bus/setup.py` | `k1.bus.ports.bus` | `IBus` |
| `bus/setup.py` | `k1.bus.ports.mailbox` | `IMailbox`, `IMailboxRouter`, `MailboxConfig` |
| `bus/deserialize.py` | `k1.concierge.events.*` | `CanonicalEventMeta`, `deserialize_event` |
| `bus/builders.py` | `k1.concierge.events.*` | `CanonicalEventMeta`, canonical event classes (lazy) |
| `orchestrator/types.py` | `k1.concierge.config` | `get_config` |
| `orchestrator/types.py` | `k1.concierge.task.complexity` | `ComplexityTier` |
| `orchestrator/routing.py` | `k1.concierge.task.dispatch` | `TaskDispatch` |
| `orchestrator/degradation.py` | `k1.concierge.task.complexity` | `ComplexityTier` |
| `orchestrator/degradation.py` | `k1.concierge.task.dispatch` | `TaskDispatch` |

### D2. Intra-Concierge Dependencies

| Source | Depends on |
|--------|-----------|
| `fabric/__init__` | `fabric/capability_registry`, `fabric/demo_capabilities`, `fabric/family_capabilities` |
| `fabric/capability_registry` | `fabric/demo_capabilities`, `fabric/family_capabilities`, `fabric/web_capabilities` (lazy in factory) |
| `fabric/contract_converter` | `fabric/demo_capabilities`, `fabric/family_capabilities`, `fabric/web_capabilities` (lazy) |
| `fabric/poc_bridge_adapter` | `fabric/capability_registry` |
| `bus/__init__` | `bus/builders`, `bus/setup`, `bus/topics` |
| `bus/builders` | `bus/topics`, `events/base`, `events/registry`, `config/loader`, `events/validator` (lazy) |
| `bus/setup` | `bus/topics`, `config` |
| `bus/deserialize` | `events/base`, `events/registry` |
| `orchestrator/__init__` | all orchestrator submodules |
| `orchestrator/routing` | `orchestrator/types`, `task/complexity`, `task/dispatch`, `config` |
| `orchestrator/degradation` | `orchestrator/routing`, `orchestrator/types`, `task/complexity`, `task/dispatch`, `config` |
| `orchestrator/stub` | `orchestrator/ports`, `orchestrator/types` |
| `orchestrator/interfaces` | `orchestrator/types` |
| `orchestrator/ports` | `orchestrator/types` |

### D3. Port/Adapter Pattern Summary

The Concierge defines two levels of hexagonal ports:

**Fabric ports** (bridge to K1 Fabric):

1. `IFabricPort` (fabric/ports.py) — uses K1 `CapabilityRequest`/`CapabilityResult`/`RetrievalResult` directly. Production-ready swap target.
2. `POCMockBridgeAdapter` (fabric/poc_bridge_adapter.py) — implements K1 `IBridgePort` protocol. Adapts POC handler functions to K1 Fabric's BridgeProvider dispatch.

**Orchestrator ports** (internal hexagonal):

1. `IFabricGatewayPort` — uses POC-local `CapabilityRequest`/`CapabilityResult` (NOT K1 types)
2. `IStateReadPort` — read-only SS access (ORCH-01 structural enforcement)
3. `IDeltaEmitPort` — fire-and-forget bus events
4. `IDispatchPort` — route TaskEnvelope
5. 5 HIGH-tier deferred ports (IPlannerPort, IWorkflowPort, IConnectorPort, IConstraintPort, ISagaPort)

**Key dual-type observation**: The Fabric ports use K1 types (`k1.fabric.types.CapabilityRequest`) while the Orchestrator ports use concierge-local types (`k1.concierge.orchestrator.types.CapabilityRequest`). These are deliberately separate type systems — the Fabric layer bridges between them.

### D4. Capability Registration and Discovery

**Registration path**:

1. `create_demo_registry()` creates empty `CapabilityRegistry`
2. Registers 7 demo capabilities + handlers from `DEMO_HANDLERS`
3. Registers 31 family capabilities via `register_family_capabilities(registry)`
4. Registers 2 web capabilities via `register_web_capabilities(registry)`
5. Total: 40 capabilities across 12 domains

**Discovery path**:

1. Caller invokes `registry.discover(intent, domain)` or `IFabricPort.discover_capabilities()`
2. Domain aliases resolved: e.g. "communication" → "messaging"
3. Fuzzy matching: intent words overlapped with capability descriptions
4. Universal capabilities (`web_search`, `web_fetch`) bypass domain filter
5. Fallback: if domain filter yields 0 results, retries intent-only

**Contract conversion path** (for K1 integration):

1. `contract_converter.convert_all_poc_capabilities()` converts all 40 dicts to `CapabilityContract`
2. Each contract has `provider_type="BRIDGE"`, `provider_id="poc-mock-bridge"`
3. `POCMockBridgeAdapter` receives dispatches from K1's BridgeProvider

### D5. Bus Topic and Message Flow Architecture

**Builder pattern**: One builder function per topic. Each builder:

1. Accepts `payload: dict | CanonicalEventMeta` + `parent_id: int`
2. Calls `_serialize(payload)` → JSON bytes (auto-enriches legacy dicts with canonical metadata)
3. Creates `Envelope(topic, priority, payload_bytes, parent_id, payload_format=JSON)`
4. Optional canonical validation when config flag enabled

**Deserialization**: `deserialize_envelope()` reverses the path:

1. Extract `envelope.payload` bytes
2. JSON parse → check `event_type` field
3. Delegate to `EVENT_TYPE_REGISTRY` via `deserialize_event()`
4. Returns typed `CanonicalEventMeta` subclass or `None`

**Subscription routing**:

- Front subscribes to 4 topics (task_accepted, orchestration_delta, hil_request, plan_ready)
- Back subscribes to 7 topics (user_input, task_dispatch, task_cancel, task_resume, clarification_response, hil_response, affect_update)
- FSM directly routes 8 topics to Front (bypassing subscription)
- Routing invariant enforced at import time with assert

### D6. Orchestrator Routing and Degradation

**Routing flow**:

1. FSM determines `ComplexityTier` via cognitive analysis
2. Calls `route_task(task, tier)` — single dispatch point (invariant 8)
3. LOW: emit `k1.orchestration.task.dispatch.v1` → Back handles via Fabric
4. MEDIUM: create `TaskEnvelope(budget=2)` → `OrchestratorStub.handle_task()`
5. HIGH: create `TaskEnvelope(budget=10, tokens=3500)` → Orchestrator (future)

**Degradation cascade**:

1. `route_task_with_degradation()` checks circuit breakers before routing
2. HIGH + CB_PLANNER open → MEDIUM
3. MEDIUM + CB_ORCHESTRATOR open → LOW
4. LOW + CB_FABRIC open → `CannedResponse`
5. Transparent to user — FSM receives same result events regardless of tier

### D7. Error Handling Patterns

| Module | Pattern | Details |
|--------|---------|---------|
| `CapabilityRegistry.invoke()` | Catch-all → error dict | Returns `{"success": False, "error": str(e)}`, never raises |
| `POCMockBridgeAdapter.send_command()` | Catch-all → BridgeCommandResult.fail | Logs error, returns typed failure result |
| `web_fetch_handler` | Catch-all → error dict | SSRF protection before fetch attempt |
| `_build()` (builders) | Catch-suppress | Canonical validation errors logged as warnings, never block publishing |
| `deserialize_envelope()` | Safe return None | All JSON/type failures return None silently |
| `OrchestratorStub._check_budget()` | Raise BudgetExceededError | Hard enforcement of ORCH-10 |
| `Budget.__post_init__` | Raise ValueError | Validates non-negative values |
| `TaskEnvelope.__post_init__` | Raise ValueError | Validates intent non-empty, tier MEDIUM/HIGH |
| `CommittedPlan.__post_init__` | Raise ValueError | Cycle detection via DFS |

### D8. Configuration Dependencies

All runtime-tunable values read from `get_config()`:

- **Bus**: `bus.gap_timeout_ms`, `bus.mailbox_capacity`, `bus.priority_wfq`, `bus.actor_front_id`, `bus.actor_back_id`, `bus.topic_validation_enabled`, `bus.tracing_enabled`, `bus.metrics_enabled`, `bus.validate_canonical_events`
- **Orchestrator**: `orchestrator.default_budget_timeout_ms`, `orchestrator.tier_fabric_budget` (per-tier dict), `orchestrator.tier_planner_token_budget` (per-tier dict), `orchestrator.canned_response_text`

### D9. Production Readiness Assessment

| Component | Status | Gap to Production |
|-----------|--------|------------------|
| CapabilityRegistry | POC — fuzzy match | Production needs semantic search via K0 Fabric pipeline |
| POCMockBridgeAdapter | Production-ready adapter pattern | Correctly implements IBridgePort; 40 handlers are mocks |
| IFabricPort | Production-ready interface | Matches K1 Fabric.execute/discover API exactly |
| Contract converter | Production bridge | Converts 40 POC dicts → K1 CapabilityContract |
| Bus topics | Production | 45 topics, correct prefixes, subscription groups, priority mapping |
| Bus builders | Production | Envelope builders with canonical event support, causal chaining |
| Bus setup | Production | Real K1 BusFactory, middleware chain, SessionBusAdapter |
| Bus deserialization | Production | Typed canonical event deserialization |
| OrchestratorStub | POC — MEDIUM only | Handles 1-2 Fabric calls; HIGH tier needs DAGExecutor + Planner |
| Routing | Production-ready | Single dispatch point, config-driven budgets |
| Degradation | POC CBs | Simplified open/closed; production needs HALF_OPEN + failure counting |
| HIGH interfaces | Interface only | 6 abstract classes defined, not implemented |

---

*End of scan 07 — Fabric, Bus, and Orchestrator Integration Subsystems*
