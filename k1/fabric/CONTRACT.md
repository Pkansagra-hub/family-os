# K1 Fabric — CONTRACT

---

## 1. Purpose

`k1/fabric/` is the **capability execution layer** of the K1 system. It is the single
gateway through which all capability invocations flow — tools (MCP, WASM, Bridge), agents,
workflows, and Concierge state transitions. It owns:

- A registry of `CapabilityContract` objects loaded from YAML files
- A retrieval pipeline (embedding + hard filter + soft rank) to discover capabilities
- A resolution pipeline (registry lookup → policy evaluation → provider selection)
- A provider factory that instantiates the correct transport per provider type
- An output validation pipeline (structural → schema → semantic)
- A circuit breaker per provider
- A dispatcher with backpressure (WFQ-priority semaphore)
- A health checker + availability tracker
- A hot-reload module loader (file-watching daemon)

Fabric does **not**:
- Write SessionState (FAB-01: read-only via `ISessionStateReader`)
- Call LLMs directly (routes through `IModelGatewayPort` → Model Hub)
- Schedule or plan (Orchestrator + Planner do that)
- Own conversation state

---

## 2. Core invariants

| ID | Invariant |
|---|---|
| FAB-01 | Fabric NEVER writes SessionState. `ISessionStateReader` is read-only. `NullSessionStateReaderAdapter` satisfies the port for shared/startup tiers. |
| FAB-02 | Every capability name must match one of four patterns: `tool.(execute|read|write|delete).<namespace>.<name>`, `agent.(execute|spawn).<name>`, `workflow.run.<name>`, `concierge.state.<name>`. |
| FAB-03 | `CapabilityRequest.capability_name` must start with `tool.`, `agent.`, `workflow.`, or `concierge.`. Validated in `CapabilityRequest.validate()`. |
| FAB-04 | The `SafetyBand` enum is ordered: GREEN < AMBER < RED < CRISIS. A user's band must be ≥ the capability's `safety_band_min` to invoke it (`HardFilter`). |
| FAB-05 | Circuit breaker state transitions: CLOSED → OPEN (failure threshold) → HALF_OPEN (after cooldown) → CLOSED (probe success). Failure window is sliding (60s). |
| FAB-06 | Eviction order in retrieval soft-ranking: DEGRADED candidates get ×0.70 penalty. |
| FAB-07 | `AgentContract.tools_granted` defines the tool scope for a spawned agent. An agent can only invoke capabilities in its `tools_granted` set. |
| FAB-08 | Maximum workflow nesting depth: 3. `WorkflowProvider.MAX_WORKFLOW_DEPTH = 3`. |
| FAB-09 | Every event payload emitted via `IEventPort` MUST carry `cognitive_trace_id`. Injected by `EventEmitter._emit()`. |
| FAB-10 | Provider selection is deterministic for equal scores: tie-break by `(avg_latency_ms, provider_id)` ascending. `ProviderSelector._sort_key()`. |
| FAB-11 | Contract version strings must be semantic-version (`X.Y.Z`). Version compatibility: same major AND major > 0; major=0 requires exact match. |
| FAB-12 | All contract types are validated with both JSON Schema (jsonschema Draft7) and 12 semantic rules (including DAG cycle detection for workflows). |
| FAB-13 | Output validation is 3-tier: Structural (hard, always) → Schema (hard, for `success=True`) → Semantic (soft, only for AGENT/WORKFLOW). Structural failure immediately short-circuits. |
| FAB-14 | Agents NEVER write SessionState directly. They emit `AgentDelta` objects via `DeltaEmitter` → K1 DeltaBus → K1 bus. |
| FAB-15 | `CapabilityContract.social_act` is evaluated by the conscience gate before execution. If `IConsciencePort.get_digest().is_forbidden(social_act)` → abort with failure result. |

---

## 3. Public API surface

### `Fabric` (primary handle — mutable dataclass)

```python
# Execution
async def execute(request: CapabilityRequest) -> CapabilityResult
async def execute_batch(requests: List[CapabilityRequest], strategy: BatchStrategy) -> List[CapabilityResult]

# Retrieval
async def discover_capabilities(domain, intent, safety_band, session_context, top_k=10) -> RetrievalResult
async def find_relevant_prompts(intent, domain, safety_band, top_k=10) -> RetrievalResult

# Registry
def register(contract: ContractUnion) -> None
def unregister(name: str) -> None
def lookup(name: str, *, version: Optional[str] = None) -> Optional[ContractUnion]

# Health
def health() -> RegistryHealth

# Lifecycle
async def start_health_checker() -> None
async def shutdown() -> None
```

### `CapabilityFabric` (execution engine — `__slots__`-based)

9-step internal `_execute_impl()` pipeline (see §5).

### `FabricRetrieval` (retrieval API — `__slots__`-based)

Async wrappers delegating to synchronous `RetrievalEngine`.

### `CapabilityRegistryAPI` (registry API — `__slots__`-based)

Thin façade over `CapabilityRegistry` with additional `reload()`, `health()`, `list_by_*()`.

---

## 4. `CapabilityRequest` contract

```python
@dataclass(frozen=True)
class CapabilityRequest:
    request_id: str         # UUID4 if not provided
    capability_name: str    # must start with tool. / agent. / workflow. / concierge.
    params: Dict[str, Any]
    prompt_template: Optional[str]
    context_override: Optional[Dict[str, Any]]
    tier: str               # Tier.MEDIUM default
    wfq_priority: str       # WFQPriority.INTERACTIVE default
    safety_band: str        # SafetyBand.GREEN default
    timeout_ms: int         # default 30000
    retry_count: int        # default 0
    caller: str             # non-empty required
    caller_id: str
    trace_id: str           # UUID4 if not provided
    session_id: str
    plan_id: Optional[str]
    step_id: Optional[str]
```

`validate()` checks 8 invariants; `validate_or_raise()` raises `CapabilityRequestValidationError`.

---

## 5. Execution pipeline (`_execute_impl`)

```
CapabilityRequest
    │
    ▼ (1) Emit INVOKED event
    │
    ▼ (2) _resolve(request)
    │     registry.lookup → provider_matcher.match → policy_engine.evaluate → selector.select
    │     Returns ResolvedProvider (contract + provider_config)
    │     On failure: return CapabilityResult.failure_result(error_code)
    │
    ▼ (3) Conscience gate (_run_conscience_gate)
    │     If contract.social_act AND conscience_port.get_digest().is_forbidden(social_act):
    │       return CapabilityResult.failure_result("conscience_gate_blocked")
    │
    ▼ (4) HIL gate (async _run_hil_gate)
    │     If contract.requires_human_confirmation:
    │       await hil_port.gate_capability(...) with hil_gate_timeout_ms=120s
    │       If denied: return CapabilityResult.failure_result("hil_denied")
    │
    ▼ (5) _build_context(request, contract)
    │     context_builder.build(contract, params, session_id, trace_id)
    │     → ExecutionContext(session_sections, params, prompt, token_count, trace_id)
    │
    ▼ (6) Instantiate provider
    │     provider_factory.create(provider_config)
    │
    ▼ (7) _execute_with_breaker(provider, provider_id, request, context, trace_id)
    │     circuit_breakers[provider_id].call(provider._execute, request, context, trace_id)
    │     Up to max_retries+1 attempts (retries only for retriable errors)
    │
    ▼ (8) _validate_output(result, contract, provider_type, request, execution_context)
    │     OutputValidationPipeline.validate(...)
    │     On REJECT: coercion or hard failure
    │
    ▼ (9) Emit COMPLETED/FAILED + LEARNING_SIGNAL, update metrics
    │
    └──→ CapabilityResult
```

---

## 6. Retrieval pipeline

```
discover_capabilities(domain, intent, safety_band, session_context, top_k)
    │
    ▼ (1) registry.list_by_domain(domain) or list_all()
    │
    ▼ (2) embedding_port.embed(intent) → query_vector
    │
    ▼ (3) HardFilter
    │     - user_band >= capability.safety_band_min
    │     - availability != OFFLINE  (DEGRADED kept, penalized)
    │     - satisfied_inputs / total_inputs >= 0.5 threshold
    │
    ▼ (4) SoftRanker  (descending)
    │     score = 0.40 * cosine_similarity
    │           + 0.30 * jaccard_domain_match
    │           + 0.15 * success_rate_30d
    │           + 0.15 * (1 - avg(norm_cost, norm_latency))
    │     DEGRADED: × 0.70 penalty
    │
    ▼ (5) TopKSelector  (clamp k to [1, 25])
    │
    └──→ RetrievalResult
```

---

## 7. Policy evaluation pipeline

Called by `Resolver._evaluate_policy()` per resolution request.

```
PolicyEngine.evaluate(candidates, contract, request):
    1. AffectiveRouting.score(request)   — reads affective_now section; returns [0.0, 0.2]
    2. CognitiveLoadRouting.score(request) — reads cognitive section; returns [0.0, 0.15]
    3. SecurityContext.evaluate(request, contract) — 3 checks:
         a. check_band(user_band, capability_band_min)
         b. check_tool_scope(capability_name, tools_granted)
         c. check_rate_limit(capability_name) — 60s sliding window
    4. Per candidate: QoSIntegration.score(request, cost_per_call, avg_latency_ms) — [0.0, 0.20]

    Final score = 1.0 + affective_score + cognitive_score + qos_score
    Candidates that fail security check → rejected (not included in output)

    Returns List[ScoredCandidate], ordered descending by score
```

---

## 8. Output validation pipeline

```
OutputValidationPipeline.validate(result, contract, provider_type, ...):
    Tier 1 — StructuralValidator (always run, hard):
        - Required fields present (success, data, error)
        - success=True → data is dict, error is None
        - success=False → error is not None
        - Data ≤ 1 MiB
        - No truncation markers
        HARD failure → immediate REJECT, emit OUTPUT_VALIDATION_FAILED event

    Tier 2 — SchemaValidator (success=True only, hard):
        - Validates result.data against contract.output (JSON Schema Draft-7 subset)
        - Coercion on failure (fill defaults, cast string→numeric)
        - Re-validate after coercion; REJECT if still failing
                - REJECT returns CapabilityResult(success=False, error_code="output_validation_failed")
                    and emits OUTPUT_VALIDATION_FAILED with request/capability/provider/trace context

    Tier 3 — SemanticValidator (AGENT/WORKFLOW only, soft):
        - HallucinationDetector: uncertainty markers, fabrication markers, belief consistency
        - Penalties: −0.30 for uncertainty, −0.40 for fabrication, −0.40 for belief conflict
        - Always ANNOTATE, never REJECT
```

---

## 9. `CapabilityContract` structure

26 fields. Key policy fields:

| Field | Type | Default | Notes |
|---|---|---|---|
| `name` | `str` | `""` | Matches naming pattern for type |
| `version` | `str` | `""` | semver X.Y.Z |
| `provider_type` | `str` | `""` | MCP/WASM/BRIDGE/AGENT/WORKFLOW/CONCIERGE/LOCAL_STUB |
| `provider_id` | `str` | `""` | Key into ProviderRegistry |
| `safety_band_min` | `str` | `GREEN` | Minimum caller band required |
| `availability` | `str` | `ONLINE` | ONLINE/DEGRADED/OFFLINE |
| `requires_human_confirmation` | `Optional[bool]` | `None` | HIL gate trigger |
| `social_act` | `Optional[str]` | `None` | Conscience gate trigger |
| `risk_class` | `str` | `"safety_sensitive"` | Self-model integration |
| `side_effects` | `List[Dict]` | `[]` | Side-effect declaration |
| `ephemeral` | `bool` | `True` | Session-scoped lifecycle |
| `required_context` | `List[str]` | `[]` | SessionState sections needed |

`AgentContract` extends with: `prompt_template`, `tools_granted`, `llm_budget_tokens`, `max_tool_calls`, `max_execution_time_ms`, `template_file`.

---

## 10. Provider types and transport

| `ProviderType` | Concrete provider | Transport | Status |
|---|---|---|---|
| `MCP` | `MCPProvider` | `IMCPTransport` (stdio/sse/streamable-http) | LIVE |
| `WASM` | `WASMProvider` | `IWASMRuntime` | LIVE |
| `BRIDGE` | `BridgeProvider` | `IFabricK0Port` (Bridge/K0) | LIVE (LOCAL COLD mode) |
| `AGENT` | `AgentProvider` + `AgentFactory` | `IModelGatewayPort` + `IDeltaBusPort` | LIVE |
| `WORKFLOW` | `WorkflowProvider` | `IWorkflowRegistry` + `IOrchestrator` | LIVE |
| `CONCIERGE` | `ConciergeProvider` | `IConciergeRouter` | LIVE |
| `LOCAL_STUB` | `LocalStubProvider` | In-process | LIVE (deterministic stub) |

Auto-discovery at startup: `AutoDiscoveryMCPTransport` scans `k1/tools/mcp_servers/`. `AutoDiscoveryWASMRuntime` scans `k1/tools/wasm_modules/`.

---

## 11. Circuit breaker config per provider type

| Type | `timeout_ms` | `failure_threshold` | `half_open_after_ms` | `max_retries` | `fallback_error_code` |
|---|---|---|---|---|---|
| MCP local (stdio) | 10,000 | 3 | 30,000 | 2 | `tool_offline` |
| MCP remote (sse/http) | 15,000 | 3 | 30,000 | 2 | `tool_offline` |
| WASM | 5,000 | 5 | 15,000 | 2 | `computation_failed` |
| BRIDGE | 10,000 | 3 | 30,000 | 2 | `bridge_offline` |
| AGENT | 30,000 | 2 | 30,000 | 2 | `agent_execution_failed` |
| WORKFLOW | 60,000 | 1 | 60,000 | **1** | `workflow_failed` |
| CONCIERGE | 5,000 | 5 | 10,000 | 2 | `concierge_state_failed` |
| Default | 30,000 | 5 | 30,000 | 2 | `capability_unavailable` |

Sliding failure window: 60,000ms for all types.

---

## 12. Dispatcher (WFQ backpressure)

`FabricDispatcher` controls concurrency of `CapabilityFabric._execute_impl()` calls.

| `WFQPriority` | Budget SLA | Shed at |
|---|---|---|
| `URGENT` | ≤ 50ms | SHEDDING level |
| `REALTIME` | ≤ 150ms | SHEDDING level |
| `INTERACTIVE` | ≤ 300ms | SHEDDING level |
| `BACKGROUND` | ≤ 5s | WARNING level |

Backpressure levels (computed from `in_flight / max_concurrent`):
- NORMAL: < 80%
- WARNING: 80–94%
- SHEDDING: ≥ 95%
- SATURATED: 100% (semaphore blocking)

Emits `k1.fabric.pressure.warning.v1` and `k1.fabric.pressure.shedding.v1` on level transitions.

---

## 13. Bus events emitted

All emitted via `EventEmitter` → `IEventPort`.

| Topic | When |
|---|---|
| `k1.capability.invoked.v1` | Before resolution |
| `k1.capability.completed.v1` | After successful execution |
| `k1.capability.failed.v1` | On any failure |
| `k1.fabric.learning.signal.v1` | After every execution (success or failure) |
| `k1.fabric.capability.registered.v1` | On contract registration |
| `k1.fabric.capability.unregistered.v1` | On contract removal |
| `k1.fabric.capability.version.conflict.v1` | On semver conflict during registration |
| `k1.fabric.contract.validation.failed.v1` | On hot-reload YAML parse failure |
| `k1.fabric.output.validation.failed.v1` | On output validation REJECT; enriched Fabric payload includes capability, request, provider, tier, rejection reason, and `cognitive_trace_id` |
| `k1.fabric.provider.health.changed.v1` | On health status change |
| `k1.fabric.pressure.warning.v1` | On dispatcher WARNING level entry |
| `k1.fabric.pressure.shedding.v1` | On dispatcher SHEDDING level entry |
| `k1.fabric.agent.created.v1` | After `BuildAgentHandler` creates dynamic agent |
| `k1.fabric.agent.expired.v1` | On agent expiration |
| `k1.fabric.meta.operation.blocked.v1` | On `MetaOperationValidator` rejection |

Bus events **consumed** by Fabric:
- `k1.orchestration.step.execute.v1`
- `k1.planner.discovery.request.v1`
- `k1.fabric.provider.health.check.v1`
- `k1.mcp.tool.discovered.v1`

---

## 14. `BatchStrategy` — batch execution modes

| Strategy | Behaviour |
|---|---|
| `PARALLEL` | `asyncio.gather()` — all requests concurrently |
| `SEQUENTIAL` | Each request awaited in order |
| `DAG` | Topological wave execution; `request.params["_depends_on"]` = list of `request_id`s |

Max batch size: `FabricConfig.max_batch_size = 50`. Raises `BatchSizeExceededError` if exceeded.

---

## 15. Dynamic agent creation (meta-tools)

`tool.write.build_agent` is a built-in meta-tool registered automatically at startup (F4 wiring). It allows runtime creation of new `AgentContract` entries in the registry.

Security gates (enforced by `MetaOperationValidator`, Epic 4.5.5):
1. Caller band ≥ AMBER
2. Agent's `safety_band_min` ≤ caller band
3. Domain not in `{META, SECURITY, ADMIN}`
4. `tools_granted` may not contain `tool.write.*` patterns
5. `tools_granted` may not include AGENT-type providers

---

## 16. Hot-reload (module loader)

`ModuleLoader` watches `k1/contracts/` (4 subdirs: tools/, agents/, prompts/, workflows/) for YAML changes.
- Polls every 2.0s (configurable, min 0.1s) via daemon thread `fabric-module-watcher`
- On file modify: unregisters old, registers new (if validation passes)
- On validate fail: keeps old contract, emits `contract.validation.failed.v1`
- Supported extensions: `.yaml`, `.yml`

---

## 17. `CapabilityVersion` compatibility rules

- `major > 0`: `v1.x.y` is compatible with `v1.a.b` (same major)
- `major == 0`: exact match required (pre-stable API)
- `CapabilityRegistry` stores all versions; `lookup_latest_compatible(name, major)` returns max within major

---

## 18. Error surface

| Exception | Location | When |
|---|---|---|
| `CapabilityRequestValidationError(errors)` | `types.py` | `validate_or_raise()` |
| `CapabilityVersionError(raw)` | `types.py` | `CapabilityVersion.parse()` on bad string |
| `FabricError` | `fabric.py` | Base |
| `BatchSizeExceededError(actual, maximum)` | `fabric.py` | batch > max_batch_size |
| `ResolutionFailedError(capability_name, error_code)` | `resolver.py` | capability not found, no provider, access denied |
| `DispatcherOverloadedError(level, in_flight, max_concurrent, rejected_priority)` | `dispatcher.py` | SHEDDING + non-URGENT request |
| `DispatcherShutdownError` | `dispatcher.py` | dispatch after shutdown |
| `CircuitBreakerOpen(provider_id, remaining_ms)` | `breaker.py` | request while CB OPEN |
| `ProviderExecutionError(provider_id, message, retriable, error_code)` | `base_provider.py` | transport-level error |
| `ProviderTimeoutError(provider_id, timeout_ms)` | `base_provider.py` | execution > timeout |
| `ContractValidationError(errors, contract_type, contract_name)` | `contract_validator.py` | validation fail |
| `CapabilityRegistryError` family | `registry.py` | duplicate, not found, version conflict |
