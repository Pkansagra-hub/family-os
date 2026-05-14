# K1 Fabric — WIRING

Describes how K1 Fabric connects to every external port, adapter, and system at
construction time, and what flows over each connection at runtime.

---

## 1. Four construction modes (`FabricFactory`)

| Mode | Method | Typical caller | Notes |
|---|---|---|---|
| Standalone | `create_standalone(...)` | Scripts, isolated test | Test adapters, capture_mode=False |
| Testing | `create_for_testing(...)` | Unit/integration tests | Test adapters + `LocalEventAdapter(capture=True)` |
| Full ports | `create_with_ports(state_reader, event_port, bridge, model_gateway, prompt_system, delta_bus, ...)` | K1 system bootstrap (session-aware) | All ports injected |
| Shared | `create_shared(event_port, bridge, model_gateway, prompt_system, delta_bus, *, state_reader=None, ...)` | K1 system bootstrap (system-global) | `NullSessionStateReaderAdapter` when state_reader=None |

All modes call `_construct_fabric()` (20-step internal), which wires every internal component.

---

## 2. Port map

Every external dependency is accessed through a Protocol. All ports are injected at
construction; no `import` of concrete classes happens inside Fabric logic.

| Port (Protocol) | Production Adapter | Test Adapter | Notes |
|---|---|---|---|
| `ISessionStateReader` | `SessionStateReaderAdapter(SessionStateManager)` | `TestSessionStateReaderAdapter` | Read-only. SIM-GAP-47: `NullSessionStateReaderAdapter` for shared Fabric. |
| `IEventPort` | `EventPortProdAdapter(IBus)` | `LocalEventAdapter(capture=True)` | Fire-and-forget. Must not raise. |
| `IFabricK0Port` (Bridge) | `BridgeConnectionAdapter` | `TestBridgeAdapter` | Starts disconnected (LOCAL COLD). |
| `IModelGatewayPort` | `ModelGatewayBridgeAdapter(IModelHubPort)` | `TestModelGatewayAdapter` | E-0.5.2 bridge adapter. |
| `IPromptSystemPort` | `PromptSystemProdAdapter(prompts_dir)` | `TestPromptSystemAdapter` | Reads YAML. Supports template_file refs. |
| `IDeltaBusPort` | `DeltaBusProdAdapter(IBus)` | `TestDeltaBusAdapter` | Fire-and-forget. Non-blocking. |
| `IHILPort` | (injected at construction) | none | HIL gate for `requires_human_confirmation`. |
| `IConsciencePort` | (injected at construction) | none | Conscience gate for `social_act`. |

---

## 3. Internal component wiring (20-step `_construct_fabric`)

Below is the construction order. Each step is numbered as in the factory code.

```
(1)  ContractValidator()
(2)  CapabilityRegistry(validator, event_port=event_emitter_shim)
(3)  EmbeddingIndex()            — FAISS, dimension 384 (MiniLM-L6)
(4)  RetrievalEngine(registry, embedding_index)
(5)  FabricRetrieval(retrieval_engine)
(6)  HardFilter(), SoftRanker(), TopKSelector() → wired into RetrievalEngine
(7)  ContextBuilder(state_reader, prompt_system)
(8)  ContextBudget(ContextBudgetConfig)
(9)  EventEmitter(event_port)
(10) ProviderRegistry(event_port=event_emitter_shim)
(11) ProviderFactory(**port_deps)
        Registers 7 handler constructors by ProviderType:
        - MCP    → MCPProvider(config, transport=mcp_transport)
        - WASM   → WASMProvider(config, runtime=wasm_runtime)
        - BRIDGE → BridgeProvider(config, bridge=bridge_port)
        - AGENT  → AgentFactory(...) → AgentProvider(config, agent_factory=factory)
        - WORKFLOW → WorkflowProvider(config, workflow_registry, capability_lookup, orchestrator)
        - CONCIERGE → ConciergeProvider(config, router=concierge_router)
        - LOCAL_STUB → LocalStubProvider(config)
(12) ProviderMatcher(provider_registry)
(13) ProviderSelector()
(14) PolicyEngine(SecurityContext, AffectiveRouting, CognitiveLoadRouting, QoSIntegration)
(15) Resolver(capability_registry, provider_matcher, provider_selector, provider_factory, policy_engine)
(16) OutputValidationPipeline(state_reader, event_port, schema_compiler)
(17) CircuitBreakerMap: Dict[provider_id, CircuitBreaker]
        CB state-change callback → AvailabilityTracker.on_state_change()
(18) AvailabilityTracker(event_port, registry_updater=capability_registry.update_availability)
(19) CapabilityFabric(resolver, context_builder, validation_pipeline, event_emitter,
                      capability_registry, provider_factory, circuit_breakers,
                      dispatcher, config, hil_port, conscience_port)
(15-prod only) FabricDispatcher(event_callback=event_emitter._emit)
(19b-F4)  BuildAgentHandler registered on mcp_transport.register_handler()
          Capability: "tool.write.build_agent"
(20) ModuleLoader(registry, contracts_dir, event_port, validator, poll_interval_s=2.0)
     → scan_directory() → start_watching()
(20b) ProactiveGapDetector(event_port, event_emitter, module_loader)
     → wire_subscriptions() subscribes four Fabric/MCP discovery topics
(21) HealthChecker(provider_registry, availability_tracker, provider_instances,
                   circuit_breakers, event_port, config)
     → start() (async, called by Fabric.start_health_checker())
(22) Fabric(facade, retrieval, registry_api, registry, module_loader, health_checker,
            event_port, event_emitter, gap_detector)
```

`Fabric.shutdown()` stops the health checker and module loader, then calls
`gap_detector.stop()` so every subscription created by `wire_subscriptions()` is
unsubscribed from the injected `IEventPort` before the owning session bus closes.

---

## 4. MCP transport wiring

```
FabricFactory._construct_fabric()
    │
    ├── production_mode=True + no explicit mcp_transport supplied:
    │     AutoDiscoveryMCPTransport(mcp_servers_dir="k1/tools/mcp_servers/")
    │     Dispatch order per request method:
    │       1. Registered handlers (BuildAgentHandler on "tools/call")
    │       2. JSON-RPC handlers
    │       3. FastMCP adapters
    │       4. Error response
    │
    └── testing / standalone:
          TestMCPTransport (captured calls via CapturedMCPCall)
```

Remote vs local CB selection (in `get_breaker_config()`):
- transport = `sse` or `streamable-http` → `MCP_REMOTE_CONFIG` (15s timeout)
- transport = `stdio` → `MCP_LOCAL_CONFIG` (10s timeout)

---

## 5. WASM runtime wiring

```
FabricFactory._construct_fabric()
    │
    ├── production_mode=True:
    │     AutoDiscoveryWASMRuntime(wasm_modules_dir="k1/tools/wasm_modules/")
    │     Convention: each module directory must have executor.py
    │
    └── testing:
          TestWASMRuntime (captured calls via CapturedWASMCall)
```

WASM sandbox per-call config: `WASMSandboxConfig(memory_limit_mb=64, timeout_ms=5000, allow_network=False, allow_filesystem=False)`.

---

## 6. Bridge (K0) wiring

```
FabricFactory.create_with_ports(bridge=bridge_port) or create_shared(bridge=bridge_port)
    │
    └── BridgeConnectionAdapter(bridge_client=None)
          _connected = False at construction (LOCAL COLD mode)
          Bridge client protocol: not yet built (see OPEN_ISSUES.md)

          At runtime:
          BridgeProvider._execute(request, context, trace_id)
              if bridge.is_available():
                  classify operation:
                      read ops (memory.recall, query.*) → bridge.query()
                      write ops (memory.store, memory.delta, checkpoint, feedback.signal) → bridge.send_command()
                  IFL ops (tool.execute.home.*, tool.execute.device.*) → bridge.route_ifl()
              else:
                  K0_OFFLINE fallback (returns partial result with k0_mode="K0_OFFLINE")
```

---

## 7. Model Gateway wiring

```
FabricFactory.create_with_ports(model_gateway=model_gateway_port)
    │
    └── ModelGatewayBridgeAdapter(hub_port: IModelHubPort)
          Maps FabricModelInfo ↔ HubModelInfo

          At runtime (agent spawn, step 3 of AgentFactory._spawn()):
          model_gateway.create_handle(
              budget_tokens=contract.llm_budget_tokens or 4000,
              model_preference=None,
              capabilities=None,
              trace_id=trace_id
          ) → ILLMHandle

          Agent.execute(params):
              llm_handle.generate(compiled_prompt, params) → str
              Tokens approximated: len(text) // 4
```

`LLMHandleBridge.generate()` is NOT thread-safe by design. Each spawned `Agent` holds its own handle.

---

## 8. Delta bus wiring

```
FabricFactory.create_with_ports(delta_bus=delta_bus_port)
    │
    └── DeltaBusProdAdapter(bus: IBus)

          At runtime (DeltaEmitter.flush()):
          delta_bus.emit_delta(
              agent_id=..., delta_type=..., section=..., data=...
          )
          → IBus.publish(topic="k1.agent.{agent_id}.delta.v1", payload=delta.to_dict())
          Fire-and-forget. Non-blocking. Must not raise.
```

DeltaEmitter batches AgentDelta objects with 500ms window (`DELTA_BATCH_WINDOW_MS=500`).
LWW merge on `(section, key)` within the window.

---

## 9. Prompt system wiring

```
FabricFactory.create_with_ports(prompt_system=prompt_system_port)
    │
    └── PromptSystemProdAdapter(prompts_dir=...)
          Threading: RLock per instance
          Supports {{template_file:<path>}} references in templates

          At runtime (ContextBuilder.build(), step 4):
          prompt_system.resolve(template_name) → PromptTemplate
          prompt_system.compile(template, variables) → str

          Missing template → context.prompt_resolved=False, continue gracefully
```

---

## 10. SessionState wiring

```
FabricFactory.create_with_ports(state_reader=state_reader_port)
    │
    ├── Production (session-aware):
    │     SessionStateReaderAdapter(SessionStateManager)
    │     Supports dotted paths: "control.safety_band" normalised for DAGExecutor compat.
    │     read_section(session_id, section) → Optional[Dict]
    │     read_sections(session_id, names) → Dict
    │     get_snapshot(session_id) → SessionSnapshot
    │
    └── Shared/startup (no session context):
          NullSessionStateReaderAdapter() [SIM-GAP-47]
          All methods return empty Dict or None.
          Logs a single warning at construction.

          Also used as fallback in create_standalone / create_for_testing.
```

Used by:
- `ContextBuilder.build()` — reads required and optional context sections
- `SemanticValidator.validate()` — reads `beliefs_active` section for hallucination detection
- `AffectiveRouting.score()` — reads `affective_now` section
- `CognitiveLoadRouting.score()` — reads `cognitive` section

---

## 11. Event port wiring

```
Production:
    EventPortProdAdapter(bus: IBus)
        emit(topic, payload):
            extracts cognitive_trace_id from payload (FAB-09)
            bus.publish(topic, payload)  — async, fire-and-forget
        subscribe(topic, handler) → SubscriptionHandle
        unsubscribe(handle) → bool

Test / standalone:
    LocalEventAdapter(capture_mode=True)
        emit(topic, payload):
            dispatches synchronously to registered handlers (outside lock)
            if capture_mode: appends to captured_events[]
        drain() → List[Dict]
        assert_emitted(topic, *, count=1)
```

`EventEmitter` wraps `IEventPort`. If `event_port is None`, all emissions are silently dropped.

---

## 12. Health checker wiring

```
HealthChecker(
    provider_registry=ProviderRegistry,
    availability_tracker=AvailabilityTracker,
    provider_instances={provider_id: ICapabilityProvider, ...},
    circuit_breakers={provider_id: CircuitBreaker, ...},
    event_port=IEventPort,
    config=HealthCheckerConfig(
        default_interval_s=30,
        failure_threshold=3,
        check_timeout_s=10,
        max_consecutive_failures=10
    )
)

Async polling loop (_run_loop):
    For each registered provider:
        asyncio.wait_for(provider.health_check(), timeout=10s)
        On timeout → DEGRADED
        On exception → UNHEALTHY, increment consecutive_failures
        If consecutive_failures >= threshold → force UNHEALTHY
        On status change:
            1. provider_registry.update_health(...)
            2. availability_tracker.update_state(...)
            3. _sync_circuit_breaker(...):
                HEALTHY → breaker.allow_probe()
                UNHEALTHY → breaker.trip()
            4. emit k1.fabric.provider.health.changed.v1

CB state-change callback (on_cb_state_change):
    OPEN → schedule _immediate_check (asyncio.create_task)
    CLOSED/HALF_OPEN → no action (health_checker schedules regular cycle)
```

---

## 13. Availability tracker wiring

```
AvailabilityTracker(
    event_port=IEventPort,
    registry_updater=capability_registry.update_availability,
    enforce_progressive_recovery=True
)

Connected to:
    - HealthChecker: calls update_state() after each health probe
    - CircuitBreaker: on_state_change() callback registered at CB construction
        CLOSED  → ONLINE
        HALF_OPEN → DEGRADED
        OPEN    → OFFLINE
        Note: OFFLINE → ONLINE is blocked; auto-inserts DEGRADED intermediate step.
    - CapabilityRegistry: registry_updater called after every valid state change
```

---

## 14. Circuit breaker wiring

```
For each ProviderConfig in ProviderRegistry:
    cb_config = get_breaker_config(provider_type, provider_config, override=None)
    breaker = CircuitBreaker(
        provider_id=config.provider_id,
        config=cb_config,
        on_state_change=availability_tracker.on_state_change
    )
    circuit_breakers[provider_id] = breaker

CapabilityFabric._execute_with_breaker(provider, provider_id, request, context, trace_id):
    breaker = circuit_breakers.get(provider_id)
    if breaker is None:
        # Newly registered provider (hot-loaded)
        breaker = CircuitBreaker(provider_id, DEFAULT_CONFIG)
    result = await breaker.call(provider._execute, request, context, trace_id)
```

---

## 15. Dispatcher wiring

Production mode only (`production_mode=True` in factory):

```
FabricDispatcher(
    config=FabricDispatcherConfig(max_concurrent=10, warning_threshold=0.80, shedding_threshold=0.95),
    event_callback=event_emitter._emit
)

CapabilityFabric.execute(request):
    if dispatcher is not None:
        dispatch_result = await dispatcher.dispatch(request, _execute_impl)
    else:
        result = await _execute_impl(request)
```

Semaphore created in `FabricDispatcher.__init__()`. See OPEN_ISSUES.md §1 for the asyncio
event-loop creation concern.

---

## 16. Registry hot-reload wiring

```
ModuleLoader.start_watching()
    → daemon thread "fabric-module-watcher" polls at 2.0s

On YAML file created/modified:
    ContractValidator.validate_or_raise(data, contract_type)
    If valid:
        capability_registry.unregister(old_name)  [if modify]
        capability_registry.register(new_contract)
        emit k1.fabric.contract.hot_reloaded.v1
    If invalid:
        mtime_cache[path] = current_mtime  (suppress retry spam)
        emit k1.fabric.contract.validation.failed.v1

On YAML file deleted:
    capability_registry.unregister(name)
    emit k1.fabric.contract.removed.v1
```

---

## 17. Dynamic agent creation wiring (F4 / Epic 4.5.5)

```
_construct_fabric() step 19b:
    mcp_transport.register_handler(
        "tool.write.build_agent",
        BuildAgentHandler(
            validator=AgentSpecValidator(registry, prompt_system),
            composer=AgentComposer(registry, prompt_system),
            registry=capability_registry,
            security=MetaOperationValidator(),
            emitter=event_emitter
        )
    )

BuildAgentHandler.execute(request):
    1. MetaOperationValidator: 5 gates (caller band, agent band, domain, no tool.write.* in tools_granted, no AGENT providers)
    2. AgentSpecValidator.validate_or_raise(request.params)
    3. AgentComposer.build() → AgentContract (frozen)
    4. capability_registry.register(contract)
    5. capability_registry.register_created_agent(contract, ephemeral=True, ...)
    6. event_emitter.emit_agent_created(...)
```

---

## 18. Concierge provider wiring

```
ConciergeProvider(config, router=IConciergeRouter)

Known states: interrupt_check, greeting, farewell, clarify, handoff

_execute(request, context, trace_id):
    state_name = request.capability_name.removeprefix("concierge.state.")
    req = ConciergeStateRequest(state_name, params, session_id, trace_id)
    resp = await router.route(req)
    if resp.success:
        return CapabilityResult.success_result(data={...resp.data, "next_state": resp.next_state})
    else:
        return CapabilityResult.failure_result(...)
```

No circuit breaker for Concierge (in-process, no network hop).

---

## 19. Workflow provider wiring

```
WorkflowProvider(config,
    workflow_registry=IWorkflowRegistry,
    capability_lookup=ICapabilityLookup,
    orchestrator=IOrchestrator,
    max_depth=3
)

_execute():
    1. Guard: _current_depth >= max_depth → WorkflowDepthExceededError
    2. await workflow_registry.load(workflow_name) → WorkflowSpec
    3. Validate each step's capability via capability_lookup.exists()
    4. Detect schema drift per step:
        NONE   → continue
        MINOR  → auto-fill defaults
        MAJOR  → store gap in K0, abort
    5. RunManifest(SHA-256 content_hash)
    6. await orchestrator.execute_workflow(manifest, context)
```

`WorkflowRegistry` and `IOrchestrator` are external ports (not yet live — see OPEN_ISSUES.md §8).

---

## 20. Output validation wiring

```
OutputValidationPipeline(
    state_reader=ISessionStateReader,
    event_port=IEventPort,
    config=OutputValidationConfig(
        skip_semantic=False,
        enable_coercion=True
    ),
    schema_compiler=SchemaCompiler()
)

SchemaCompiler:
    Cache: Dict[(contract_name, version), Dict] — module-scoped

ValidationFallback:
    _event_port = event_port
    _schema_validator = SchemaValidator

Tier 3 (semantic):
    SemanticValidator → HallucinationDetector
    state_reader used to read beliefs_active for belief consistency check
```

---

## 21. Context builder wiring

```
ContextBuilder(
    state_reader=ISessionStateReader,
    prompt_system=IPromptSystemPort,
    config=ContextBuilderConfig(
        default_session_id="",
        budget_config=ContextBudgetConfig(
            ceiling=128_000,
            response_headroom=4_000,
            allocation=BudgetAllocation(...)
        )
    )
)

build(contract, params, session_id, trace_id, ...):
    1. Identify required_context + optional_context from contract
    2. state_reader.read_sections(session_id, required_names) → Dict
    3. state_reader.read_sections(session_id, optional_names) → Dict
    4. Compile prompt: prompt_system.resolve(template) + compile(template, variables)
    5. ContextBudget.apply(session_sections, prompt, params, optional_sections) → BudgetResult
    6. Return ContextBuildResult(context=ExecutionContext(...), budget=BudgetResult(...), ...)
```

Token counting: `tiktoken.get_encoding("cl100k_base")` lazy-loaded; fallback `len(text)//4` on failure.

---

## 22. Discovery tools wiring

Three built-in meta-capability handlers registered at startup (not via YAML — registered directly in registry by the factory):

| Capability | Handler | Provider ID |
|---|---|---|
| `tool.read.discover_capabilities` | `DiscoverCapabilitiesHandler(retrieval_engine)` | `discover_capabilities_handler` |
| `tool.read.find_prompts` | `FindPromptsHandler(retrieval_engine)` | `find_prompts_handler` |
| `tool.read.get_capability_schema` | `GetCapabilitySchemaHandler(capability_registry)` | `get_capability_schema_handler` |

Note: These use `RetrievalEngine` directly (synchronous). `FabricRetrieval` (async wrapper) does NOT satisfy `RetrievalLike` protocol (mismatch on async/sync signatures).
