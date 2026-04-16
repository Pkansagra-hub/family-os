# Epic 1.3: Fabric Audit — Complete Findings

**Date:** 2026-04-11
**Status:** COMPLETE — All 6 issues audited
**Verdict:** Fabric is the **most mature component** — all 9 production adapters are REAL, 20-step factory, async execution pipeline.

---

## Summary Verdict

| Aspect | Status | Notes |
| ------ | ------ | ----- |
| Port definitions (6 Protocols) | ✅ COMPLETE | ALL Protocol + @runtime_checkable (unlike SSM's ABCs) |
| FabricFactory | ✅ COMPLETE | 3 methods, 20-step _construct_fabric(), zero external imports |
| Production adapters (9) | ✅ ALL REAL | Zero stubs — every adapter has complete logic |
| Test adapters (7) | ✅ COMPLETE | In-memory stubs with capture/assertion APIs |
| EventPort vs DeltaBus dual-role | ✅ SEPARATE | Two distinct classes, can share same bus instance |
| SessionStateReader constructor | ✅ TWO ARGS | `__init__(self, manager: Any, session_id: str)` — per-session |
| NullSessionStateReaderAdapter | ⚠️ EXISTS but NOT WIRED | Lives in `k1/concierge/adapters/`, not in any factory method |
| Fabric core (CapabilityFabric) | ✅ ASYNC | ~1,400 LOC, 9-step async pipeline, 3 batch strategies |

**Total LOC:** ~5,500+ across fabric package (core + factory + adapters + ports)
**Stubs found:** ZERO in production set

---

## Issue 1.3.1: Port Definitions (6 Protocols) ✅

**Key finding: All 6 ports use Protocol (structural) + @runtime_checkable. Zero ABCs. Zero concrete defaults.**

This is the OPPOSITE pattern to SessionState (which uses ABC/nominal). Fabric uses structural subtyping throughout.

### FA-P1: ISessionStateReader (`k1/fabric/ports/state_reader.py`, ~160 LOC)

| Method | Signature | Kind |
| ------ | --------- | ---- |
| `read_section` | `(self, session_id: str, section: str) -> Optional[Dict[str, Any]]` | abstract |
| `read_sections` | `(self, session_id: str, names: List[str]) -> Dict[str, Any]` | abstract |
| `get_snapshot` | `(self, session_id: str) -> SessionSnapshot` | abstract |

Supporting types: `SessionSnapshot` — frozen dataclass with `session_id`, `sections`, `timestamp_ms`, `section_names`. Has `has_section()` and `get_section()` convenience methods.

**Note:** All methods take `session_id` as parameter (unlike SSM which has it as constructor arg). The adapter (FA-A1) binds session_id at construction time.

### FA-P2: IEventPort (`k1/fabric/ports/event_port.py`, ~150 LOC)

| Method | Signature | Kind |
| ------ | --------- | ---- |
| `emit` | `(self, topic: str, payload: Any) -> None` | abstract |
| `subscribe` | `(self, topic: str, handler: Callable[[str, Any], None]) -> SubscriptionHandle` | abstract |
| `unsubscribe` | `(self, handle: SubscriptionHandle) -> bool` | abstract |

Supporting types: `SubscriptionHandle` — frozen dataclass with `subscription_id`, `topic`.

**Note:** This is Fabric's OWN IEventPort, distinct from SessionState's IEventPort (SS-P2). Different method signatures — Fabric's subscribe handler takes `(topic, payload)` vs SS's `(payload)`.

### FA-P3: IDeltaBusPort (`k1/fabric/ports/delta_bus.py`, ~120 LOC)

| Method | Signature | Kind |
| ------ | --------- | ---- |
| `emit_delta` | `(self, agent_id: str, delta_type: str, section: str, data: Dict[str, Any]) -> None` | abstract |

Supporting types: `DeltaPayload` — frozen dataclass with `agent_id`, `delta_type`, `section`, `data`, `trace_id`. Has `to_dict()` and `from_args()` factory.

**Simplest port — single fire-and-forget method.**

### FA-P4: IBridgePort (`k1/fabric/ports/bridge_port.py`, ~340 LOC)

| Method | Signature | Kind |
| ------ | --------- | ---- |
| `send_command` | `async (self, operation: str, payload: Dict[str, Any], *, trace_id: str = "", timeout_ms: int = 0) -> BridgeCommandResult` | abstract async |
| `query` | `async (self, operation: str, selectors: Dict[str, Any], *, trace_id: str = "", timeout_ms: int = 0) -> BridgeCommandResult` | abstract async |
| `route_ifl` | `async (self, route: IFLRoute, payload: Dict[str, Any], *, trace_id: str = "") -> BridgeCommandResult` | abstract async |
| `is_available` | `(self) -> bool` | abstract sync |
| `get_health` | `(self) -> BridgeHealth` | abstract sync |

Supporting types:

- `BridgeHealth` — frozen dataclass with `available`, `mode`, `last_heartbeat_ms`, `latency_ms`, `error_message`. Has `is_full()`, `is_degraded()`, `is_offline()`.
- `BridgeCommandResult` — frozen dataclass with `success`, `data`, `error_code`, `error_message`, `k0_mode`, `latency_ms`, `trace_id`. Has `ok()` and `fail()` static factories.
- `IFLRoute` — frozen dataclass with `address`, `namespace`, `function_name`, `timeout_ms`. Has `parse()` static factory.

**Most complex port — mixed sync/async, 3 async + 2 sync methods.**

### FA-P5: IModelGatewayPort (`k1/fabric/ports/model_gateway.py`, ~260 LOC)

| Method | Signature | Kind |
| ------ | --------- | ---- |
| `create_handle` | `(self, budget_tokens: int, model_preference: Optional[str] = None, capabilities: Optional[List[str]] = None, trace_id: str = "") -> ILLMHandle` | abstract sync |
| `is_model_loaded` | `async (self, model_id: str) -> bool` | abstract async |
| `list_models` | `async (self) -> List[ModelInfo]` | abstract async |
| `find_model` | `async (self, required_capabilities: List[str]) -> Optional[str]` | abstract async |

**Nested Protocol — ILLMHandle** (also @runtime_checkable):

| Method | Signature | Kind |
| ------ | --------- | ---- |
| `generate` | `async (self, prompt: str, params: Dict[str, Any]) -> str` | abstract async |
| `model_id` | `@property -> str` | abstract |
| `budget_tokens` | `@property -> int` | abstract |

Supporting types: `ModelCapability(str, Enum)` — CHAT, TOOL_CALL, STRUCTURED, EMBED, VISION, BATCH. `ModelInfo` — frozen dataclass.

**Anomaly:** `create_handle` is sync, returns async handle. `ModelInfo.capabilities` uses `List[str]` not `List[ModelCapability]`.

### FA-P6: IPromptSystemPort (`k1/fabric/ports/prompt_system.py`, ~120 LOC)

| Method | Signature | Kind |
| ------ | --------- | ---- |
| `resolve` | `(self, template_name: str) -> Optional[PromptTemplate]` | abstract |
| `compile` | `(self, template: str, variables: Dict[str, Any]) -> str` | abstract |

Supporting types: `PromptTemplate` — frozen dataclass with `name`, `template`, `version`, `variables`, `metadata`. Has `has_variable()` and `to_dict()`.

### Ports **init**.py Exports

All 6 protocols + 10 supporting types exported in `__all__`:
`ISessionStateReader`, `SessionSnapshot`, `IEventPort`, `SubscriptionHandle`, `IBridgePort`, `BridgeHealth`, `BridgeCommandResult`, `IFLRoute`, `IModelGatewayPort`, `ILLMHandle`, `ModelCapability`, `ModelInfo`, `IPromptSystemPort`, `PromptTemplate`, `IDeltaBusPort`, `DeltaPayload`.

---

## Issue 1.3.2: FabricFactory ✅

### FabricFactory (`k1/fabric/factory.py`, ~720 LOC)

| Factory Method | Params | Returns | DI Pattern |
| -------------- | ------ | ------- | ---------- |
| `create_standalone` | `*, contracts_dir?, config?` | `Fabric` | Zero injection — all test adapters |
| `create_for_testing` | `*, capture_events?, contracts_dir?, config?, mcp_transport?, wasm_runtime?` | `Fabric` | Partial injection (2 optional overrides) |
| `create_with_ports` | `state_reader, event_port, bridge, model_gateway, prompt_system, delta_bus, *, production_mode?, contracts_dir?, config?, embedding_port?, capability_registry?` | `Fabric` | Full injection — production path |

**All 3 delegate to `_construct_fabric()` — 20-step construction pipeline:**

1. Accept 6 ports (passed in)
2. ContractValidator
3. CapabilityRegistry(validator, event_port)
4. ModuleLoader(registry, contracts_dir, event_port, validator)
5. Policy: SecurityContext + AffectiveRouting(state_reader) + CognitiveLoadRouting(state_reader) + QoSIntegration → PolicyEngine
6. ProviderRegistry(event_port)
7. CircuitBreakers dict (shared mutable reference)
8. ContextBuilder(state_reader, prompt_system)
9. ProviderFactory(bridge, model_gateway, state_reader, delta_bus, context_builder, registry, mcp_transport, wasm_runtime) + register handlers
10. ProviderMatcher → ProviderSelector → Resolver(registry, matcher, selector, factory, policy_engine)
11. Retrieval: EmbeddingIndex + HardFilter + SoftRanker + TopKSelector → RetrievalEngine
12. OutputValidationPipeline(state_reader, event_port)
13. AvailabilityTracker → HealthChecker(provider_registry, tracker, circuit_breakers, event_port)
14. Bidirectional CB wiring
15. FabricDispatcher (production_mode only)
16. EventEmitter(event_port)
17. CapabilityFabric(resolver, context_builder, validation, emitter, registry, provider_factory, CBs, dispatcher, config)
18. FabricRetrieval(retrieval_engine)
19. CapabilityRegistryAPI(registry)
20. module_loader.start() → auto_register_providers → ProactiveGapDetector → assemble Fabric container

**Cross-component imports: NONE.** Factory is entirely self-contained within `k1.fabric.*`.

**Provider handler registration** — 6 types: MCP, WASM, BRIDGE, AGENT, WORKFLOW, CONCIERGE.

---

## Issue 1.3.3: All 9 Production Adapters ✅ ALL REAL

| ID | Adapter | Port | LOC | External Deps | Key Detail |
| -- | ------- | ---- | --- | ------------- | ---------- |
| FA-A1 | SessionStateReaderAdapter | ISessionStateReader | ~300 | SSM (via Any) | Per-session, dotted path support, safety_band compat |
| FA-A2 | EventPortProdAdapter | IEventPort | ~270 | IBus, Envelope, Priority | JSON → Envelope → bus.publish(), INTERACTIVE priority |
| FA-A3 | DeltaBusProdAdapter | IDeltaBusPort | ~130 | IBus, Envelope, Priority | JSON → Envelope → bus.publish(), REALTIME priority |
| FA-A4 | BridgeConnectionAdapter | IBridgePort | ~350 | Bridge client (Any) | Graceful degradation, LOCAL COLD fallback, async |
| FA-A5 | ModelGatewayBridgeAdapter | IModelGatewayPort | ~250 | IModelHubPort, HubRequest | Full HubRequest construction, budget tracking |
| FA-A6 | PromptSystemProdAdapter | IPromptSystemPort | ~280 | yaml, filesystem | YAML scanning, template caching, {var} substitution |
| FA-A7 | LocalEventAdapter | IEventPort | ~280 | None | In-process pub/sub, capture mode for tests |
| FA-A8 | AutoDiscoveryWASMRuntime | IWASMRuntime | ~270 | importlib, filesystem | Convention-based dir scanning, dynamic loading |
| FA-A9 | AutoDiscoveryMCPTransport | IMCPTransport | ~440 | importlib, FastMCP | Dir scanning, JSON-RPC + FastMCP dual-pattern, 3-tier dispatch |

**ZERO stubs in production.** All 9 have complete, functioning logic. Every adapter uses `threading.RLock` for thread safety.

### Test Adapters (7)

| Class | Port | LOC | Pattern |
| ----- | ---- | --- | ------- |
| TestSessionStateReaderAdapter | ISessionStateReader | ~190 | In-memory dict |
| TestBridgeAdapter | IBridgePort | ~340 | Canned K0 responses, capture mode |
| TestModelGatewayAdapter + TestLLMHandle | IModelGatewayPort + ILLMHandle | ~260 | Round-robin canned responses |
| TestPromptSystemAdapter | IPromptSystemPort | ~180 | In-memory template dict |
| TestDeltaBusAdapter | IDeltaBusPort | ~190 | Delta capture for assertions |
| TestMCPTransport | IMCPTransport | ~180 | Canned MCP responses |
| TestWASMRuntime | IWASMRuntime | ~180 | Canned WASM results |

---

## Issue 1.3.4: EventPort vs DeltaBus Dual-Role ✅ SEPARATE

**They are TWO SEPARATE classes, NOT dual-role.**

| Aspect | EventPortProdAdapter (FA-A2) | DeltaBusProdAdapter (FA-A3) |
| ------ | ----------------------------- | --------------------------- |
| Protocol | IEventPort | IDeltaBusPort |
| Constructor | `__init__(self, bus: Any)` | `__init__(self, bus: Any)` |
| Methods | emit, subscribe, unsubscribe | emit_delta only |
| Direction | Bidirectional (pub+sub) | Unidirectional (emit only) |
| Topic scheme | Caller-provided | Auto: `k1.agent.{agent_id}.delta.v1` |
| Priority | INTERACTIVE | REALTIME |

**Can share the same bus instance** — both accept `IBus` via `Any`. In production wiring they MAY point at the same bus, but they are independent with no shared state.

FA-A2 docstring explicitly states: *"This adapter lives in Fabric's layer and is exclusively an IEventPort (not IDeltaBusPort)."*

---

## Issue 1.3.5: SessionStateReader Constructor ✅ TWO ARGS

```python
class SessionStateReaderAdapter:
    __slots__ = ("_manager", "_session_id")

    def __init__(self, manager: Any, session_id: str) -> None:
```

**YES, takes TWO separate positional args:**

1. `manager: Any` — SessionStateManager instance (duck-typed to avoid circular import)
2. `session_id: str` — Binds adapter to this specific session

**Per-session adapter** — if caller passes different session_id to `read_section()`, returns `None` gracefully.

Key behaviors:

- Supports dotted section paths (e.g., `"control.safety_band"`)
- Hardcoded safety_band compatibility normalization for DAGExecutor
- Manager typed as `Any` (not `SessionStateManager`) to avoid cross-package import dependency

---

## Issue 1.3.6: NullSessionStateReaderAdapter ⚠️ EXISTS but NOT WIRED

**Location:** `k1/concierge/adapters/null_state_reader.py` (~36 LOC)

**Implements:** ISessionStateReader (structurally)

| Method | Returns |
| ------ | ------- |
| `read_section(session_id, section)` | `None` |
| `read_sections(session_id, names)` | `{}` (empty dict) |
| `get_snapshot(session_id)` | `SessionSnapshot(session_id=session_id)` (empty sections) |

No method raises. All degrade gracefully to empty/None values.

**NOT WIRED into FabricFactory.** The factory's `create_standalone()` and `create_for_testing()` both use `TestSessionStateReaderAdapter`. The `create_with_ports()` accepts any `state_reader` — so the null adapter CAN be injected, but no factory convenience method does so.

**Implication for kernel bootstrap:** The "S3: Shared Fabric" scenario (Fabric for Orchestrator/Planner, no session) will need to manually pass `NullSessionStateReaderAdapter` to `create_with_ports()`. A `create_shared()` or `create_for_orchestrator()` factory convenience method would be helpful but does not exist yet.

---

## Fabric Core Architecture

### CapabilityFabric — Main Class (~1,400 LOC in `k1/fabric/fabric.py`)

**Constructor:**

```python
def __init__(self, *, resolver, context_builder, validation_pipeline,
             event_emitter, registry, provider_factory,
             circuit_breakers=None, dispatcher=None, config=None)
```

**Key methods:**

- `execute(request: CapabilityRequest) -> CapabilityResult` — 9-step async pipeline
- `execute_batch(requests, strategy=PARALLEL) -> List[CapabilityResult]` — 3 strategies: PARALLEL, SEQUENTIAL, DAG

**9-step execution pipeline:**

1. Validate request
2. Resolve capability → provider
3. Build context (state + prompts)
4. Apply policy (security, affective, cognitive, QoS)
5. Check circuit breaker
6. Execute via provider
7. Validate output
8. Emit completion events
9. Return result

**Fabric container dataclass:**

```python
@dataclass
class Fabric:
    facade: CapabilityFabric
    retrieval: FabricRetrieval
    registry_api: CapabilityRegistryAPI
    registry: Any = None
    module_loader: Any = None
    health_checker: Any = None
    event_port: Any = None
    event_emitter: Optional[EventEmitter] = None
```

### How 6 ports are consumed (indirectly via injected subsystems)

| Port | Used By |
| ---- | ------- |
| ISessionStateReader | ContextBuilder, PolicyEngine (affective + cognitive), OutputValidation, ProviderFactory (AgentProvider) |
| IEventPort | EventEmitter, CapabilityRegistry, ModuleLoader, OutputValidation, HealthChecker, AvailabilityTracker |
| IDeltaBusPort | ProviderFactory → AgentProvider (state delta emission) |
| IBridgePort | ProviderFactory → BridgeProvider (cross-system calls) |
| IModelGatewayPort | ProviderFactory → AgentProvider (LLM execution) |
| IPromptSystemPort | ContextBuilder (prompt template resolution) |

---

## Cross-Component Dependencies

| From | To | Nature |
| ---- | -- | ------ |
| FA-A1 (StateReader) | SessionStateManager | Duck-typed via `Any` |
| FA-A2 (EventPort) | IBus, Envelope, Priority | `k1.bus.envelope.envelope` (lazy import) |
| FA-A3 (DeltaBus) | IBus, Envelope, Priority | `k1.bus.envelope.envelope` (lazy import) |
| FA-A4 (Bridge) | Bridge client | `Any` (no direct import) |
| FA-A5 (ModelGateway) | IModelHubPort, HubRequest | `k1.model_hub.*` |
| FA-A6 (PromptSystem) | Filesystem, yaml | stdlib only |
| FA-A8, FA-A9 | Filesystem, importlib | Convention-based discovery |
| Factory | **NONE external** | Fully self-contained within k1.fabric |

---

## Anomalies & Concerns

1. **Port params typed as `Any` in factory.** `create_with_ports()` declares all 6 port args as `Any` instead of Protocol types. Defeats type-checker enforcement at the composition root.

2. **No IEmbeddingPort Protocol.** The embedding port is used in `_construct_fabric()` and `_StubEmbeddingPort` but has no formal Protocol in `k1/fabric/ports/`. Implicit structural contract.

3. **WORKFLOW and CONCIERGE provider deps not injected.** `_create_workflow` needs `workflow_registry`, `capability_lookup`, `orchestrator`; `_create_concierge` needs `concierge_router`. None in ProviderFactory constructor — would raise `ValueError` in standalone/testing modes.

4. **ABC vs Protocol split.** SessionState ports use ABC (nominal), Fabric ports use Protocol (structural). This is an architectural inconsistency across components. Both work but different contracts for isinstance() checks vs structural matching.

5. **NullStateReader location mismatch.** Lives in `k1/concierge/adapters/` but logically belongs in `k1/fabric/adapters/` (it implements Fabric's ISessionStateReader). Cross-package placement.

6. **Lazy bus imports in FA-A2 and FA-A3.** `Envelope` and `Priority` imported inside method body to avoid circular imports. Minor per-call overhead.

---

## Wiring Requirements for Kernel Bootstrap

### Tier-1 (Shared) — S3: Shared Fabric

```python
# For Orchestrator/Planner (no session)
null_reader = NullSessionStateReaderAdapter()
shared_fabric = FabricFactory.create_with_ports(
    state_reader=null_reader,
    event_port=EventPortProdAdapter(shared_bus),     # or LocalEventAdapter()
    bridge=BridgeConnectionAdapter(client=bridge),    # or TestBridgeAdapter()
    model_gateway=ModelGatewayBridgeAdapter(model_hub),
    prompt_system=PromptSystemProdAdapter(prompts_dir),
    delta_bus=DeltaBusProdAdapter(shared_bus),
    production_mode=True,
)
```

### Tier-2 (Per-Session) — P3: Per-Session Fabric

```python
# For Concierge (with session)
session_reader = SessionStateReaderAdapter(ssm, session_id)
session_fabric = FabricFactory.create_with_ports(
    state_reader=session_reader,
    event_port=EventPortProdAdapter(session_bus),
    bridge=BridgeConnectionAdapter(client=bridge),
    model_gateway=ModelGatewayBridgeAdapter(model_hub),
    prompt_system=PromptSystemProdAdapter(prompts_dir),
    delta_bus=DeltaBusProdAdapter(session_bus),
    production_mode=True,
)
```

### Open Questions for MS-2

| # | Question | Impact |
| - | -------- | ------ |
| Q1 | Should shared Fabric and per-session Fabric share ModelGateway/Bridge adapters? | Resource efficiency vs isolation |
| Q2 | EventPort + DeltaBus — shared bus vs per-session bus for Fabric? | Topic namespace isolation |
| Q3 | NullStateReader should move to `k1/fabric/adapters/` or stay in concierge? | Package ownership |
| Q4 | Missing `create_shared()` factory method — add it? | Bootstrap convenience |
| Q5 | WORKFLOW/CONCIERGE provider deps — how to inject at runtime? | Provider registration |

---

## 09_wiring_plan.md Status Updates

| Issue | Status | Verdict |
| ----- | ------ | ------- |
| 1.3.1 | ✅ | All 6 ports complete — Protocol + @runtime_checkable, ~1,150 LOC total |
| 1.3.2 | ✅ | Factory complete — 3 methods, 20-step pipeline, zero external imports |
| 1.3.3 | ✅ | ALL 9 production adapters are REAL — zero stubs |
| 1.3.4 | ✅ | SEPARATE classes — EventPortProd (IEventPort) ≠ DeltaBusProd (IDeltaBusPort), can share bus |
| 1.3.5 | ✅ | TWO ARGS confirmed — `__init__(self, manager: Any, session_id: str)` |
| 1.3.6 | ⚠️ | NullStateReader EXISTS (`k1/concierge/adapters/`) but NOT wired into any factory method |
