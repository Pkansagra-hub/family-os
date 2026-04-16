# Fabric — Formal API Mapping

> Generated: 2026-04-12 · Scope: Inputs, Outputs, Processing for every Fabric boundary

---

## 1. Entry Points (What Goes IN)

### 1.1 Direct API — CapabilityFabric.execute()

Primary execution entry. Called by Orchestrator (via FabricGatewayAdapter) and Concierge (via IDispatchPort).

| Method | Input | Output | Caller |
| --- | --- | --- | --- |
| `execute(request)` | `CapabilityRequest` | `CapabilityResult` | Orchestrator StepRunner, Concierge dispatch |
| `execute_batch(requests, strategy)` | `List[CapabilityRequest]`, `BatchStrategy` (PARALLEL / SEQUENTIAL / DAG) | `List[CapabilityResult]` | Orchestrator DAGExecutor wave execution |

**CapabilityRequest** (frozen, 16 fields):

| Field | Type | Default | Set By |
| --- | --- | --- | --- |
| `request_id` | `str` | uuid4() | Auto |
| `capability_name` | `str` | `""` | Orchestrator / Concierge |
| `params` | `Dict[str, Any]` | `{}` | Caller |
| `prompt_template` | `Optional[str]` | `None` | Planner step / Caller |
| `context_override` | `Optional[Dict[str, Any]]` | `None` | Caller |
| `tier` | `str` | `"MEDIUM"` | Orchestrator tier routing |
| `wfq_priority` | `str` | `"INTERACTIVE"` | Caller |
| `safety_band` | `str` | `"GREEN"` | Concierge classification |
| `timeout_ms` | `int` | `30000` | Caller / PlanStep |
| `retry_count` | `int` | `0` | Internal retry tracking |
| `caller` | `str` | `""` | `"orchestrator"` / `"concierge"` |
| `caller_id` | `str` | `""` | Step ID / task ID |
| `trace_id` | `str` | uuid4() | Propagated from turn |
| `session_id` | `str` | `""` | From session |
| `plan_id` | `Optional[str]` | `None` | From CommittedPlan |
| `step_id` | `Optional[str]` | `None` | From PlanStep |

### 1.2 Retrieval API — FabricRetrieval

Called by Planner (via FabricRetrievalAdapter) for capability discovery.

| Method | Input | Output | Caller |
| --- | --- | --- | --- |
| `discover_capabilities(domain, intent, safety_band, session_context, top_k)` | `domain: Optional[List[str]]`, `intent: str`, `safety_band: str`, `session_context: Optional[Dict]`, `top_k: Optional[int]` | `RetrievalResult` | Planner ToolCallRouter (fabric_search tool) |
| `find_relevant_prompts(intent, domain, safety_band, top_k)` | `intent: str`, `domain: Optional[List[str]]`, `safety_band: str`, `top_k: Optional[int]` | `RetrievalResult` | Planner ToolCallRouter (fabric_search tool) |

### 1.3 Registry API — CapabilityRegistryAPI

Called by Orchestrator (via FabricGatewayAdapter.query_registry).

| Method | Input | Output | Caller |
| --- | --- | --- | --- |
| `lookup(name)` | `capability_name: str` | `Optional[ContractUnion]` | Orchestrator ConstraintResolver, Compensation lookup |
| `list_all()` | — | `List[ContractUnion]` | Orchestrator query_registry_by_category |
| `list_by_domain(domain)` | `domain: str` | `List[ContractUnion]` | RetrievalEngine |
| `register(contract)` | `ContractUnion` | — | ModuleLoader, Admin |
| `unregister(name)` | `capability_name: str` | `bool` | Admin |

### 1.4 Event Subscriptions (Async Inbound)

| Topic | Handler | Payload Shape | Effect |
| --- | --- | --- | --- |
| `k1.orchestration.step.execute.v1` | (wired at init) | `StepExecuteEvent` → `{capability_name, request_id, session_id, params, trace_id, priority, caller}` | Build CapabilityRequest → execute |
| `k1.planner.discovery.request.v1` | (wired at init) | `DiscoveryRequestEvent` → `{intent, domain, safety_band, top_k, request_id, trace_id}` | discover_capabilities() |
| `k1.fabric.provider.health.check.v1` | (wired at init) | `HealthCheckRequestEvent` → `{provider_id, trace_id}` | HealthChecker.check_provider() or check_all() |
| `k1.mcp.tool.discovered.v1` | ProactiveGapDetector | `MCPToolDiscoveredEvent` → `{tool_name, tool_description, input_schema, output_schema, server_id, server_name, trace_id}` | Auto-register MCP tool as CapabilityContract |

### 1.5 Module Loading (Contract Registration)

`ModuleLoader.start(watch=False)` scans 4 directories at bootstrap:
- `tools/` → `CapabilityContract` (via ToolContractParser)
- `agents/` → `AgentContract` (via AgentContractParser)
- `prompts/` → `PromptContract` (via PromptContractParser)
- `workflows/` → `WorkflowContract` (via WorkflowContractParser)

Hot-reload: polling daemon thread when `watch=True`.

---

## 2. Exit Points (What Goes OUT)

### 2.1 Port Calls — What Fabric Sends

#### ISessionStateReader (→ SessionState)

| Method | When Called | Input | Output |
| --- | --- | --- | --- |
| `read_section(session_id, section)` | ContextBuilder, PolicyEngine (Affective/Cognitive), SemanticValidator | `session_id: str`, `section: str` | `Optional[Dict[str, Any]]` |
| `read_sections(session_id, names)` | ContextBuilder bulk read | `session_id: str`, `names: List[str]` | `Dict[str, Any]` |
| `get_snapshot(session_id)` | ContextBuilder full context | `session_id: str` | `SessionSnapshot` |

**Adapters:** `SessionStateReaderAdapter` (prod, wraps SSM), `NullSessionStateReaderAdapter` (shared mode, returns empty), `TestSessionStateReaderAdapter` (tests).

#### IEventPort (→ Event Bus)

| Method | When Called | Input | Output |
| --- | --- | --- | --- |
| `emit(topic, payload)` | EventEmitter (16 topics), CapabilityRegistry, ProviderRegistry, AvailabilityTracker | `topic: str`, `payload: Any` | `None` |
| `subscribe(topic, handler)` | ProactiveGapDetector, HealthChecker | `topic: str`, `handler: Callable` | `SubscriptionHandle` |
| `unsubscribe(handle)` | Shutdown | `SubscriptionHandle` | `bool` |

**Adapters:** `EventPortProdAdapter` (prod, wraps IBus with JSON serialization), `LocalEventAdapter` (test, in-process with capture).

#### IBridgePort (→ K0 via Bridge)

| Method | When Called | Input | Output |
| --- | --- | --- | --- |
| `send_command(operation, payload, *, trace_id, timeout_ms)` | BridgeProvider (memory.store, memory.delta, checkpoint, feedback.signal) | `operation: str`, `payload: Dict`, kwargs | `BridgeCommandResult` |
| `query(operation, selectors, *, trace_id, timeout_ms)` | BridgeProvider (memory.recall) | `operation: str`, `selectors: Dict`, kwargs | `BridgeCommandResult` |
| `route_ifl(route, payload, *, trace_id)` | BridgeProvider (tool.execute.home.*, tool.execute.device.*) | `IFLRoute`, `payload: Dict`, kwargs | `BridgeCommandResult` |
| `is_available()` | BridgeProvider health check | — | `bool` |
| `get_health()` | HealthChecker | — | `BridgeHealth` |

**Adapters:** `BridgeConnectionAdapter` (prod, wraps Bridge client), `TestBridgeAdapter` (tests).

#### IModelGatewayPort (→ ModelHub)

| Method | When Called | Input | Output |
| --- | --- | --- | --- |
| `create_handle(budget_tokens, model_preference, capabilities, trace_id)` | AgentFactory._spawn() | `budget_tokens: int`, kwargs | `ILLMHandle` |
| `is_model_loaded(model_id)` | Health check | `model_id: str` | `bool` |
| `list_models()` | Discovery | — | `List[ModelInfo]` |
| `find_model(required_capabilities)` | AgentFactory model selection | `List[str]` | `Optional[str]` |

**ILLMHandle.generate(prompt, params) → str** — Called by Agent.execute(). Budget-tracked.

**Adapters:** `ModelGatewayBridgeAdapter` + `LLMHandleBridge` (prod, wraps IModelHubPort), `TestModelGatewayAdapter` + `TestLLMHandle` (tests).

#### IPromptSystemPort (→ Prompt Templates)

| Method | When Called | Input | Output |
| --- | --- | --- | --- |
| `resolve(template_name)` | ContextBuilder.build() | `template_name: str` | `Optional[PromptTemplate]` |
| `compile(template, variables)` | ContextBuilder.build() | `template: str`, `variables: Dict` | `str` |

**Adapters:** `PromptSystemProdAdapter` (prod, YAML loader), `TestPromptSystemAdapter` (tests).

#### IDeltaBusPort (→ Agent Delta Bus)

| Method | When Called | Input | Output |
| --- | --- | --- | --- |
| `emit_delta(agent_id, delta_type, section, data)` | DeltaEmitter.flush() (batched, 500ms window) | `agent_id: str`, `delta_type: str`, `section: str`, `data: Dict` | `None` |

Topic pattern: `k1.agent.{agent_id}.delta.v1` (REALTIME priority).

**Adapters:** `DeltaBusProdAdapter` (prod, wraps IBus), `TestDeltaBusAdapter` (tests, with capture).

#### IMCPTransport (→ MCP Tool Servers)

| Method | When Called | Input | Output |
| --- | --- | --- | --- |
| `send(request)` | MCPProvider._execute() | `MCPRequest(method, tool_name, arguments, timeout_ms, trace_id)` | `MCPResponse(success, content, error_message, latency_ms, raw)` |
| `ping()` | MCPProvider.health_check() | — | `bool` |
| `is_connected()` | MCPProvider._execute() pre-check | — | `bool` |

**Adapters:** `AutoDiscoveryMCPTransport` (prod, scans k1/tools/mcp_servers/), `TestMCPTransport` (tests).

#### IWASMRuntime (→ WASM Modules)

| Method | When Called | Input | Output |
| --- | --- | --- | --- |
| `load_module(module_path)` | WASMProvider._execute() | `module_path: str` | `WASMModuleHandle` |
| `execute(handle, function_name, params, sandbox_config)` | WASMProvider._execute() | handle, fn, params, `WASMSandboxConfig(memory_limit_mb=64, timeout_ms=5000, allow_network=False, allow_filesystem=False)` | `WASMExecutionResult` |
| `is_available()` | WASMProvider health check | — | `bool` |

**Adapters:** `AutoDiscoveryWASMRuntime` (prod, scans k1/tools/wasm_modules/), `TestWASMRuntime` (tests).

---

## 3. Processing Pipeline (What Gets Processed and How)

### 3.1 Execution Pipeline — CapabilityFabric._execute_impl() (9 Steps)

```
CapabilityRequest
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ STEP 1: EMIT INVOKED EVENT                          │
│  k1.capability.invoked.v1                            │
│  {capability_name, request_id, caller, session_id}   │
└─────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ STEP 2: RESOLVE PROVIDER (5-substep pipeline)       │
│  2a. Registry lookup → contract                      │
│  2b. Provider matching → List[ProviderConfig]        │
│  2c. Policy evaluation → List[ScoredCandidate]       │
│      Security (hard gate) + Affective + Cognitive    │
│      + QoS = composite score 1.0–1.55               │
│  2d. Provider selection → ResolvedProvider           │
│      Sort by (-score, +latency, +provider_id)        │
│  2e. Return (provider_config, contract, policy)      │
└─────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ STEP 3: BUILD EXECUTION CONTEXT (6-substep)         │
│  3a. Read contract context specs                     │
│  3b. Fetch sections from SessionState                │
│  3c. Inject params from request                      │
│  3d. Resolve prompt template                         │
│  3e. Apply 128K token budget (5-level compression)   │
│  3f. Package → ExecutionContext                       │
└─────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ STEP 4: INSTANTIATE PROVIDER                        │
│  ProviderFactory.create(config) → CapabilityProvider │
│  Provider types: MCP, WASM, BRIDGE, AGENT,           │
│                  WORKFLOW, CONCIERGE                  │
└─────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ STEP 5: EXECUTE (with CB + timeout)                 │
│  CircuitBreaker.call(provider.execute, request,      │
│                      context, trace_id)              │
│  ─ CB CLOSED: execute through                        │
│  ─ CB OPEN: reject with fallback_error_code          │
│  ─ CB HALF_OPEN: one probe allowed                   │
│  ─ Retry: up to max_retries+1 attempts              │
│  ─ Timeout: asyncio.wait_for(timeout_ms)             │
│  → CapabilityResult                                  │
└─────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ STEP 6: VALIDATE OUTPUT (3-tier pipeline)           │
│  Tier 1 — Structural: required fields, data type,   │
│           truncation markers, size ≤1 MiB (HARD)     │
│  Tier 2 — Schema: contract output schema validation  │
│           → coercion attempt on failure (HARD)       │
│  Tier 3 — Semantic: hallucination detection          │
│           (AGENT/WORKFLOW only, SOFT — annotate)      │
│                                                      │
│  Fallback: STRUCTURAL→REJECT, SCHEMA→COERCE/REJECT, │
│            SEMANTIC→ANNOTATE                         │
└─────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ STEP 7: EMIT COMPLETED/FAILED EVENT                 │
│  k1.capability.completed.v1 or .failed.v1            │
│  {capability_name, request_id, provider_id,          │
│   duration_ms, error_code}                           │
└─────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ STEP 8: UPDATE REGISTRY METRICS                     │
│  capability_name → latency, success count            │
└─────────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ STEP 9: EMIT LEARNING SIGNAL                        │
│  k1.fabric.learning.signal.v1                        │
│  {capability_name, provider_id, success, duration_ms,│
│   error_code, context_quality_score}                 │
└─────────────────────────────────────────────────────┘
  │
  ▼
Return CapabilityResult
```

### 3.2 Retrieval Pipeline — RetrievalEngine._run_pipeline() (5 Steps)

```
Query (intent + domain + safety_band)
  │
  ▼
Step 0: GATHER CONTRACTS
  list_by_domain() if domains given, else list_all()
  Optional: filter to prompt contracts only
  │
  ▼
Step 1: EMBED QUERY
  IEmbeddingPort.embed(query_text) → np.float32[384]
  │
  ▼
Step 2: HARD FILTER (3 rules, short-circuit)
  Rule 1: Safety band (GREEN < AMBER < RED < CRISIS)
  Rule 2: Availability (OFFLINE rejected, DEGRADED kept)
  Rule 3: Input satisfiability (≥50% params available)
  │
  ▼
Step 3: SOFT RANK (weighted scoring)
  Score = 0.40×cosine_sim + 0.30×jaccard_domain
        + 0.15×success_rate + 0.15×cost_latency
  DEGRADED penalty: ×0.70
  │
  ▼
Step 4: TOP-K SELECT (default 10, max 25)
  Sort descending by score → take top K
  │
  ▼
Return RetrievalResult(capabilities, total_matched, query_latency_ms)
```

### 3.3 Batch Strategies

| Strategy | Behavior | Use Case |
| --- | --- | --- |
| `PARALLEL` | `asyncio.gather(*tasks)`, order preserved, max 50 | Default — Orchestrator wave execution |
| `SEQUENTIAL` | One-by-one, failed don't block others | Ordered dependencies |
| `DAG` | Topological waves via `params["_depends_on"]`, per-wave parallel, circular dep detection | Complex multi-step |

### 3.4 Provider Execution by Type

| Provider | Port Used | Execute Flow | CB Config |
| --- | --- | --- | --- |
| **MCPProvider** | `IMCPTransport.send(MCPRequest)` | Check connected → resolve tool name → build MCPRequest → send → parse response | Local: 10s/3fail, Remote: 15s/3fail |
| **WASMProvider** | `IWASMRuntime.execute()` | Check available → load module → build sandbox → execute → parse result | 5s/5fail |
| **BridgeProvider** | `IBridgePort.send_command/query/route_ifl()` | Check available → classify op → route (direct/IFL/query) → parse response. Offline→fallback | 10s/3fail |
| **AgentProvider** | `AgentFactory.spawn_and_execute()` | Load contract → pool check → spawn (8-step) → warm_up → execute → pool on success | 30s/2fail |
| **WorkflowProvider** | `IOrchestrator.execute_workflow()` | Guard depth(3) → load spec → validate caps → detect schema drift → build manifest → execute | 60s/1fail |
| **ConciergeProvider** | `IConciergeRouter.route()` | Extract state_name → build request → route → parse response | 5s/5fail (lightweight) |

### 3.5 Agent Lifecycle (6-State FSM)

```
PENDING → WARMING → ACTIVE → IDLE (pool, 60s TTL) → DRAINING → TERMINATED
                      ↑          │
                      └──────────┘ (reactivate from pool)
```

- **AgentFactory** 8-step spawn: load contract → pool check → create mailbox → create LLM handle (budget) → pass state_reader → create ToolScope → build context → create DeltaEmitter → instantiate Agent
- **AgentPool**: max 5 per contract, 60s idle TTL, 15s sweep interval, FIFO reuse
- **DeltaEmitter**: 500ms batch window, LWW merge on (section, key), flush via IDeltaBusPort

---

## 4. Events Published (What Gets Emitted)

### 4.1 Execution Events (per-request)

| Topic | When | Payload Key Fields |
| --- | --- | --- |
| `k1.capability.invoked.v1` | Step 1 of pipeline | `capability_name, request_id, caller, session_id, priority, timestamp_ms` |
| `k1.capability.completed.v1` | Step 7 on success | `capability_name, request_id, provider_id, duration_ms, timestamp_ms` |
| `k1.capability.failed.v1` | Step 7 on failure | `capability_name, request_id, error_code, error_message, provider_id, duration_ms, timestamp_ms` |
| `k1.fabric.learning.signal.v1` | Step 9 always | `capability_name, provider_id, success, duration_ms, error_code, context_quality_score, timestamp_ms` |

### 4.2 Registry Events

| Topic | When | Payload Key Fields |
| --- | --- | --- |
| `k1.fabric.capability.registered.v1` | register() | `capability_name, version, domain, provider_type, timestamp_ms` |
| `k1.fabric.capability.unregistered.v1` | unregister() | `capability_name, version, reason, timestamp_ms` |
| `k1.fabric.capability.version.conflict.v1` | Version mismatch on register | `capability_name, existing_version, incoming_version, resolution, timestamp_ms` |
| `k1.fabric.capability.contract_updated.v1` | Contract updated | `capability_name, old_version, new_version, breaking_change, timestamp_ms` |
| `k1.fabric.contract.validation.failed.v1` | Contract parse failure | `file_path, capability_name, validation_errors, timestamp_ms` |

### 4.3 Infrastructure Events

| Topic | When | Payload Key Fields |
| --- | --- | --- |
| `k1.fabric.output.validation.failed.v1` | Output validation REJECT | `capability_name, request_id, provider_id, validation_tier, rejection_reason, timestamp_ms` |
| `k1.fabric.provider.health.changed.v1` | Health status change | `provider_id, old_state, new_state, reason, timestamp_ms` |
| `k1.fabric.pressure.warning.v1` | Dispatcher 80% capacity | `current_depth, max_depth, backpressure_level, in_flight, timestamp_ms` |
| `k1.fabric.pressure.shedding.v1` | Dispatcher 95%+ capacity | `current_depth, max_depth, backpressure_level, rejected_priority, in_flight, timestamp_ms` |
| `k1.fabric.agent.created.v1` | Agent build_agent tool | `agent_name, created_by, tools_granted, domain, prompt_template, ephemeral, session_id, timestamp_ms` |
| `k1.fabric.agent.expired.v1` | Agent TTL expired | `agent_name, created_at_iso, expired_at_iso, invocations, timestamp_ms` |
| `k1.fabric.meta.operation.blocked.v1` | Meta-op security gate | `operation, violation_type, requested_by, details, timestamp_ms` |

---

## 5. Type Transformations

### 5.1 Inbound: Caller → Fabric

| Source | Transformation | Fabric Internal Type |
| --- | --- | --- |
| Orchestrator `CapabilityRequest` (k1.orchestrator.types) | **Type collision** — Orch has its own `CapabilityRequest` type. FabricGatewayAdapter passes through because Orch imports from `k1.fabric.types` | `CapabilityRequest` (k1.fabric.types) — same type |
| Planner discovery call | Planner FabricRetrievalAdapter calls `discover_capabilities()` with kwargs | Direct — no type conversion needed |
| Event `StepExecuteEvent` | `from_dict()` → build `CapabilityRequest` | `CapabilityRequest` |

### 5.2 Internal: Pipeline Stages

| From | To | Transformation |
| --- | --- | --- |
| `CapabilityRequest` | `ResolvedProvider` | Resolver 5-step: lookup → match → score → select |
| `CapabilityRequest` + `ResolvedProvider` | `ExecutionContext` | ContextBuilder 6-step: read SS → inject params → resolve prompt → budget compress |
| `ExecutionContext` + `CapabilityRequest` | `CapabilityResult` | Provider.execute() — provider-specific logic |
| `CapabilityResult` | `PipelineOutcome` | OutputValidation 3-tier: structural → schema → semantic |

### 5.3 Outbound: Fabric → Caller

| Fabric Type | Transformation | Wire/Caller Type |
| --- | --- | --- |
| `CapabilityResult` | Direct return | Same `CapabilityResult` (k1.fabric.types) |
| `RetrievalResult` | Direct return | Same — Planner FabricRetrievalAdapter receives directly |
| Contract lookup | `_contract_to_entry()` in FabricGatewayAdapter | `RegistryEntry(name, provider_type, safety_band_min, availability, compensation_capability, estimated_duration_ms)` — Orchestrator type |

---

## 6. Adapter Translations (Port ↔ Infrastructure)

| Adapter | Port | Wraps | Key Translation |
| --- | --- | --- | --- |
| `SessionStateReaderAdapter` | `ISessionStateReader` | `SessionStateManager` | Per-session bound. `read_section()` → `manager.get_section()` → `to_dict()`. Supports dotted paths. |
| `NullSessionStateReaderAdapter` | `ISessionStateReader` | Nothing | All reads return None/empty. Used for shared Fabric (no session). |
| `EventPortProdAdapter` | `IEventPort` | `IBus` | `emit()` → JSON serialize → `Envelope(priority=INTERACTIVE)` → `bus.publish()`. `subscribe()` → wraps with JSON deserializer. |
| `BridgeConnectionAdapter` | `IBridgePort` | Bridge HTTP client | Routes commands/queries/IFL. Offline → `BridgeCommandResult.fail("k0_offline")`. Reconnect throttling. |
| `ModelGatewayBridgeAdapter` | `IModelGatewayPort` | `IModelHubPort` | `create_handle()` → `LLMHandleBridge`. Translates `HubModelInfo → FabricModelInfo`. |
| `LLMHandleBridge` | `ILLMHandle` | `IModelHubPort` | `generate(prompt, params)` → `ChatPayload` → `HubRequest(CHAT)` → `hub.execute()` → extract content. Budget tracking. |
| `PromptSystemProdAdapter` | `IPromptSystemPort` | YAML files in `prompts/` | `resolve()` → dict lookup. `compile()` → `{variable}` substitution. Eager load at construction. |
| `DeltaBusProdAdapter` | `IDeltaBusPort` | `IBus` | `emit_delta()` → topic `k1.agent.{agent_id}.delta.v1` → JSON → `Envelope(REALTIME)` → `bus.publish()`. |
| `AutoDiscoveryMCPTransport` | `IMCPTransport` | MCP server modules | Scans `k1/tools/mcp_servers/`. Routes: handler > JSON-RPC > FastMCP. Strips `tool.execute.` prefix. |
| `AutoDiscoveryWASMRuntime` | `IWASMRuntime` | WASM executor modules | Scans `k1/tools/wasm_modules/`. Substring match for module loading. Sandbox: 64MB, no network/fs. |

---

## 7. Error Handling & Circuit Breakers

### 7.1 Per-Provider CB Configuration

| Provider Type | Timeout | Failure Threshold | Window | Half-Open After | Max Retries | Fallback Code |
| --- | --- | --- | --- | --- | --- | --- |
| MCP (local) | 10s | 3 | 60s | 30s | 2 | `tool_offline` |
| MCP (remote) | 15s | 3 | 60s | 30s | 2 | `tool_offline` |
| WASM | 5s | 5 | 60s | 15s | 2 | `computation_failed` |
| Bridge | 10s | 3 | 60s | 30s | 2 | `bridge_offline` |
| Agent | 30s | 2 | 60s | 30s | 2 | `agent_execution_failed` |
| Workflow | 60s | 1 | 60s | 60s | 1 | `workflow_failed` |
| Concierge | 5s | 5 | 60s | 10s | 2 | `concierge_state_failed` |

### 7.2 CB State Machine

```
CLOSED ──(failures ≥ threshold)──► OPEN ──(half_open_after_ms)──► HALF_OPEN
  ▲                                  ▲                              │
  │                                  └──────(probe fails)───────────┘
  └──────────────(probe succeeds)───────────────────────────────────┘
```

### 7.3 Error Classification

| Error Source | Error Code | Retriable | CB Impact |
| --- | --- | --- | --- |
| Timeout | `deadline_exceeded` | Yes | Counted |
| Provider execution | `provider_error` | Depends on exc | Counted |
| CB Open | `circuit_breaker_open` / type-specific | No | N/A (already open) |
| Resolution failed | `capability_not_found` / `no_provider` / `access_denied` | No | Not counted |
| Output validation rejected | `output_validation_failed` | No | Not counted |
| Bridge offline | `k0_offline` | No | Counted → BRIDGE CB |

### 7.4 Concurrency & Backpressure (FabricDispatcher)

| Level | Threshold | Behavior |
| --- | --- | --- |
| NORMAL | < 80% of 10 slots | All requests pass |
| WARNING | 80% | Log warning |
| SHEDDING | 95% | Reject BACKGROUND priority |
| SATURATED | 100% | Reject all new requests |

---

## 8. Factory & Initialization

### 8.1 Factory Modes

| Mode | Method | Use | Key Difference |
| --- | --- | --- | --- |
| `create_standalone()` | Minimal, all test adapters | Local testing | `capture_mode=False` |
| `create_for_testing()` | Test adapters, injectable MCP/WASM | Unit tests | `capture_mode=True` |
| `create_with_ports()` | Full port injection, 6 positional + 5 kw | Integration/prod | Shared registry support |
| `create_shared()` | Like create_with_ports but NullStateReader | Shared singleton | No per-session state |

### 8.2 _construct_fabric() — 20-Step Wiring Sequence

```
Step 2:  ContractValidator()
Step 3:  CapabilityRegistry(validator, event_port)
Step 4:  ModuleLoader(registry, contracts_dir, event_port, validator)
Step 5:  PolicyEngine(SecurityContext(), AffectiveRouting(state_reader),
                      CognitiveLoadRouting(state_reader), QoSIntegration())
Step 6:  ProviderRegistry(event_port)
Step 7:  circuit_breakers: Dict[str, CircuitBreaker] = {}
Step 8:  ContextBuilder(state_reader, prompt_system)
Step 9:  ProviderFactory(ports) + register 6 handlers (MCP, WASM, BRIDGE,
                                                        AGENT, WORKFLOW, CONCIERGE)
Step 10: Resolver(capability_registry, provider_matcher, provider_selector,
                  provider_factory, policy_engine)
Step 11: RetrievalEngine(embedding_index, hard_filter, soft_ranker,
                         top_k_selector, embedding_port, registry_port)
Step 12: OutputValidationPipeline(state_reader, event_port)
Step 13: HealthChecker + AvailabilityTracker
Step 15: FabricDispatcher(event_callback) [prod mode only]
Step 16: EventEmitter(event_port)
Step 17: CapabilityFabric(resolver, context_builder, validation_pipeline,
                          event_emitter, registry, provider_factory,
                          circuit_breakers, dispatcher, config)
Step 18: FabricRetrieval(retrieval_engine)
Step 19: CapabilityRegistryAPI(registry)
Step 20: Bootstrap: module_loader.start() → auto_register_providers()
         → ProactiveGapDetector.wire_subscriptions() → assemble Fabric
```

### 8.3 Kernel S4 Wiring (from `k1/kernel/service.py`)

```python
shared_fabric = FabricFactory.create_shared(
    event_port=event_port,
    bridge=bridge_adapter,
    model_gateway=model_gateway,
    prompt_system=prompt_system,
    delta_bus=delta_bus,
)
```

### 8.4 Shutdown Sequence

```
Fabric.shutdown():
  1. HealthChecker.stop() (cancel polling task)
  2. ModuleLoader.stop() (cancel watcher thread)
  3. AgentPool.drain_all() (terminate all idle agents)
  4. FabricDispatcher.shutdown() (drain in-flight, return count)
  5. Close MCP transport if closeable
```

---

## 9. Configuration

| Field | Source | Default | Effect |
| --- | --- | --- | --- |
| `max_concurrent` | FabricDispatcher | `10` | Semaphore-bounded parallelism |
| `default_top_k` | RetrievalEngineConfig | `10` | Default retrieval results |
| `max_top_k` | RetrievalEngineConfig | `25` | Max retrieval results |
| `embedding_dimension` | EmbeddingIndexConfig | `384` | MiniLM-L6 vector size |
| `ivf_threshold` | EmbeddingIndexConfig | `10000` | Switch to IVF above this |
| `max_data_bytes` | StructuralValidatorConfig | `1048576` (1 MiB) | Max output size |
| `default_timeout_ms` | CapabilityRequest | `30000` | Per-request timeout |
| `idle_ttl_s` | AgentPoolConfig | `60` | Agent pool idle TTL |
| `max_pool_size` | AgentPoolConfig | `5` | Per-contract agent pool |
| `batch_window_ms` | DeltaEmitter | `500` | Agent delta batch window |
| `health_check_interval_s` | HealthCheckerConfig | `30` | Health polling interval |
| `failure_threshold` | HealthCheckerConfig | `3` | Consecutive failures → UNHEALTHY |

---

## 10. Policy Engine (Security & Routing)

### 10.1 Composite Score Formula

$$\text{FinalScore} = 1.0 + \text{Affective}_{[0, 0.2]} + \text{Cognitive}_{[0, 0.15]} + \text{QoS}_{[0, 0.2]}$$

Range: 1.0 (minimum) to 1.55 (maximum). Security is a hard gate — if rejected, score = 0.0.

### 10.2 Four Dimensions

| Dimension | Class | Type | Score Range | Signal Source |
| --- | --- | --- | --- | --- |
| Security | `SecurityContext` | Hard gate | pass/fail | Safety band, tool scope, rate limit |
| Affective | `AffectiveRouting` | Soft bonus | 0.0–0.2 | SessionState `affective_now` section |
| Cognitive | `CognitiveLoadRouting` | Soft bonus | 0.0–0.15 | SessionState `cognitive` section |
| QoS | `QoSIntegration` | Soft bonus | 0.0–0.2 | request.params budget/latency hints |

### 10.3 Security Hard Gates

1. **Safety band**: `request.safety_band >= contract.safety_band_min`
2. **Tool scope**: Per-sub-agent ToolScope enforcement (`tools_granted` allowlist)
3. **Rate limit**: Per-capability 60s sliding window
4. **Meta-operation validation**: 5 hard gates for agent creation (max agents, tools granted subset, budget cap, domain match, no nested meta-ops)

---

## 11. Flags & Known Gaps

| ID | Description | Severity | Impact |
| --- | --- | --- | --- |
| **FAB-GAP-01** | `NullSessionStateReaderAdapter` used in `create_shared()` — Fabric has no session context in shared mode | MEDIUM | PolicyEngine Affective/Cognitive scoring always 0. ContextBuilder has no session sections. |
| **FAB-GAP-02** | `EmbeddingIndex._rebuild_index()` is O(N) on every add/remove — rebuilds full FAISS index | LOW | Acceptable for <10K capabilities. Problematic if hot-registration is frequent. |
| **FAB-GAP-03** | `IEmbeddingPort` not wired in kernel S4 — no embedding_port passed to `create_shared()` | MEDIUM | RetrievalEngine cannot embed queries. Falls back to empty results if port is None. |
| **FAB-GAP-04** | `capability_types/` directory is empty — no type definitions exist | LOW | CapabilityType constants in types.py are sufficient. |
| **FAB-GAP-05** | `module_registry/` directory is empty — registry logic lives in core/ | LOW | No functional gap, just organizational. |
| **FAB-GAP-06** | No `IWorkflowRegistry` or `IOrchestrator` wired for WorkflowProvider in kernel S4 | MEDIUM | WorkflowProvider cannot execute workflows. Deferred to M3. |
| **FAB-GAP-07** | `IConciergeRouter` not wired for ConciergeProvider in kernel S4 | MEDIUM | ConciergeProvider cannot route state requests. Deferred to Concierge factory. |
| **FAB-GAP-08** | PlanStep in k1.fabric.types (6 fields) vs PlanStep in k1.orchestrator.types (14 fields) — different types, same name | MEDIUM | Type collision across modules. Orchestrator PlanStep is superset. Fabric PlanStep only used in WorkflowContract. |
