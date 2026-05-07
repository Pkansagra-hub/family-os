# K1 Kernel Bootstrap - Complete Extraction from kernel.md

**Source:** `d:\familyos\k1\kernel\kernel.md` (~6120 lines, 378KB)
**Structure:** Part A (Kernel Wiring Spec §1-25), Part B (Fabric Deep Dive §26-39), Part C (SessionState Deep Dive §40-52), Part D (Bus Deep Dive §53-68)

---

## PART A: KERNEL WIRING SPECIFICATION

### 1. PURPOSE & COMPONENT INVENTORY (7 Managed Components)

The kernel manages 7 components through hexagonal port-adapter wiring:

| Component | Ports | Standalone Adapters | Bus Adapter | Factory |
|-----------|-------|---------------------|-------------|---------|
| Bus | 3 (IBus, IMailbox, IMailboxRouter) | n/a (IS the infrastructure) | n/a | BusFactory |
| Fabric | 6 | 6 test stubs | FabricBusAdapter | FabricFactory |
| SessionState | 5 (4 mandatory + 1 optional) | SQLite, LocalEvent, DirectWriter, StandaloneLifecycle | SessionBusAdapter | SessionStateFactory |
| Orchestrator | 9 (8 core + IAdminPort) | 17 (8 prod + 8 test + admin) | Reuses FabricBusAdapter | OrchestratorFactory |
| Planner | 7 | 7 test adapters | Reuses FabricBusAdapter | PlannerFactory |
| Model Hub | 7 | Test adapters for all 7 | n/a (consumers wrap it) | ModelHubFactory |
| Concierge | 8 | 8 test adapters | Reuses FabricBusAdapter | ConciergeFactory |

### 2. DEPENDENCY GRAPH (Complete Wiring Blueprint)

Critical Path Dependencies:
1. Bus created FIRST (infrastructure dependency for all)
2. SessionState created SECOND (needs Bus for events)
3. Fabric created THIRD (needs SessionState reader adapter)
4. Model Hub created FOURTH (stateless, no bus deps)
5. Orchestrator created FIFTH (needs Fabric + SessionState)
6. Planner created SIXTH (needs Fabric + SessionState + Model Hub)
7. Planner STARTED as background task (asyncio.create_task)
8. Orchestrator cross-wired with Planner (Phase 5b: _planner_port hot-swap)
9. Concierge created LAST (needs all others as port implementations)
10. Concierge STARTED as background task (asyncio.create_task)

### 3. PORT WIRING MATRIX

#### 3.1 Fabric Ports (6)
| Port | Methods | Production Adapter |
|------|---------|-------------------|
| ISessionStateReader | read_section(session_id, section)→Dict, read_sections(session_id, names)→Dict, get_snapshot(session_id)→SessionSnapshot | SessionStateReaderAdapter |
| IEventPort | emit(topic, payload)→None, subscribe(topic, handler)→SubscriptionHandle, unsubscribe(handle)→bool | FabricBusAdapter (shared instance) |
| IBridgePort | send_command(operation, payload)→BridgeCommandResult, query(operation, selectors)→BridgeCommandResult, route_ifl(route, payload)→BridgeCommandResult, is_available()→bool, get_health()→BridgeHealth | BridgeAdapter |
| IModelGatewayPort | create_handle(budget_tokens, model_preference, capabilities)→ILLMHandle, is_model_loaded(model_id)→bool, list_models()→List[ModelInfo], find_model(required_capabilities)→Optional[str] | ModelHubGatewayAdapter |
| IPromptSystemPort | resolve(template_name)→Optional[PromptTemplate], compile(template, variables)→str | PromptSystemAdapter |
| IDeltaBusPort | emit_delta(agent_id, delta_type, section, data)→None | FabricBusAdapter (shared instance) |

#### 3.2 Orchestrator Ports (9 = 8 core + IAdminPort)
| Port | Methods | Adapter |
|------|---------|---------|
| IMailboxPort | receive(timeout_ms)→Envelope, depth()→int | MailboxAdapter |
| IFabricGatewayPort | dispatch(request)→CapabilityResult, list_capabilities()→list | FabricGatewayAdapter |
| IPlannerPort | request_plan(context)→PlanResponse, micro_replan(context)→PlanResponse | PlannerAdapter (hot-swapped Phase 5b) |
| IStateReadPort | read_section(session_id, section)→Dict | StateReadAdapter |
| IDeltaEmitPort | emit(delta)→None | DeltaEmitAdapter(event_port, delta_bus) — takes TWO args |
| IBridgeWritePort | send_command(operation, payload)→BridgeCommandResult | BridgeWriteAdapter |
| IEventSubscriptionPort | subscribe(topic, handler)→handle, unsubscribe(handle)→bool | EventSubscriptionAdapter |
| IWorkflowStoragePort | save/load/list workflows | WorkflowStorageAdapter(SQLiteWorkflowAdapter) |
| IAdminPort (optional) | HTTP endpoints | AdminHttpAdapter (post-injected) |

#### 3.3 SessionState Ports (5 = 4 mandatory + 1 optional)
| Port | Type | Adapter |
|------|------|---------|
| IStoragePort | ABC | SQLiteStorageAdapter or InMemoryStorageAdapter |
| IEventPort | ABC | LocalEventAdapter or SessionBusAdapter |
| IWriterPort | ABC | DirectWriterAdapter |
| ILifecyclePort | ABC | StandaloneLifecycle |
| IK0SyncPort (optional) | ABC | NullSyncPort (default until Bridge live) |

#### 3.4 Planner Ports (7)
| Port | Adapter |
|------|---------|
| ILLMPort | LLMGatewayAdapter → LLMRequestBusAdapter |
| IFabricPort | FabricRetrievalAdapter |
| IStatePort | SessionStateReadAdapter(reader, session_id) — pre-bound |
| IBridgePort | BridgeAdapter |
| IDeltaPort | DeltaBusAdapter (pre-stamps agent_id="planner") |
| IEventPort | EventBusAdapter (≠ DeltaBusAdapter!) |
| IMailboxPort | MailboxAdapter |

#### 3.5 Concierge Ports (8)
| # | Port | Direction | Kernel Injects | Used For |
|---|------|-----------|---------------|----------|
| 1 | IInputPort | Inbound | WebSocketInputAdapter/TestInputAdapter | Receive user messages |
| 2 | IOutputPort | Outbound | SSEOutputAdapter/TestOutputAdapter | Send responses |
| 3 | IClassificationPort | Outbound | UltraBERTv4Adapter/MockClassificationAdapter | Phase 1 classification |
| 4 | ILLMPort | Outbound | ModelGatewayAdapter | LLM calls |
| 5 | IStatePort | Both | SessionKernelAdapter | Read/write SessionState |
| 6 | IDispatchPort | Outbound | FabricOrchestratorAdapter | Route tasks |
| 7 | IDeltaPort | Both | DeltaBusAdapter | Emit events + subscribe deltas |
| 8 | IMemoryPort | Outbound | BridgeRecallAdapter | K0 long-term memory recall |

#### 3.6 Bus Ports (3)
- IBus: publish, subscribe, unsubscribe, close
- IMailbox: receive(timeout_ms), depth()
- IMailboxRouter: deliver(mailbox_name, envelope), create_mailbox(name, config)

#### 3.7 Model Hub Ports (7)
- Test adapters for all 7 ports
- Consumers wrap ModelHub differently (4 consumers, 4 interfaces)

### 4. BUS ADAPTER CONTRACTS

- **FabricBusAdapter**: SINGLE instance for both IEventPort + IDeltaBusPort. Bridges Dict ↔ bytes.
- **SessionBusAdapter**: Extends IEventPort ABC (not Protocol)
- **PlannerEventBusAdapter**: For Planner's IEventPort
- **ConciergeDeltaBusAdapter**: For Concierge's IDeltaPort

### 5. TOPIC NAMESPACE REGISTRY (60+ topics)

| Prefix | Owner | Count |
|--------|-------|-------|
| k1.session.* | SessionState | ~5 |
| k1.agent.{id}.delta.v1 | Agents | per-agent |
| k1.fabric.* | Fabric | ~10 |
| k1.orchestration.* | Orchestrator | 17 |
| k1.planner.* | Planner | 11 |
| k1.hil.* | HIL | ~4 |
| k1.capability.* | Fabric | ~4 |
| k1.affect.* | Experience | ~3 |
| k1.constraint.* | Constraints | ~2 |
| k1.proactive.* | Proactive | ~2 |
| k1.workflow.* | Workflows | ~3 |
| k1.response.* | Concierge | ~3 |
| k1.k0.sse.* | Bridge | ~3 |

### 6. BOOTSTRAP SEQUENCE (8 Phases from kernel.md §7)

#### Phase 1: Infrastructure
- BusFactory.create_local(backend="auto")
- BusFactory.create_mailbox_router()

#### Phase 2: SessionState
- SQLiteStorageAdapter(db_path)
- SessionBusAdapter(bus)
- SessionStateFactory.create_with_ports(storage, events, writer, lifecycle, k0_sync)
- session_manager.start()

#### Phase 3: Fabric
- FabricBusAdapter(bus)
- SessionStateReaderAdapter(session_manager)
- FabricFactory.create_with_ports(state_reader, event_port, delta_bus, bridge, model_gateway, prompt_system)

#### Phase 3.5: Model Hub
- ModelHubFactory.create_standalone(config, plugins={openai, anthropic, google, vllm, ollama})

#### Phase 4: Orchestrator
- OrchestratorFactory.create_production(config, mailbox, fabric, planner, state, delta, bridge, event, storage)

#### Phase 5: Planner
- PlannerFactory.create_production(llm_port, fabric_port, state_port, bridge_port, delta_port, event_port, mailbox_port, config)
- asyncio.create_task(planner.start()) -- background task

#### Phase 5b: Cross-Wire Planner
- planner_mailbox = planner.get_mailbox()
- cb_planner = CircuitBreaker("CB_PLANNER", config)
- orchestrator._planner_port = PlannerAdapter(planner_mailbox, cb_planner)

#### Phase 5.5: Bridge Client
- BridgeClient.connect(config) -- Phase 1: None (stubs), Phase 2: real connection

#### Phase 6: Concierge
- ConciergeFactory.create_with_ports(input_port, output_port, classification_port, llm_port, state_port, dispatch_port, delta_port, memory_port, config)
- asyncio.create_task(concierge.start()) -- background task

#### Phase 6.5: Household Projection Hydration
- bridge_client.query("household.projection.v1") if available
- concierge.hydrate_household(snapshot) or concierge.hydrate_household_from_local_cold()

#### Phase 7: Start Lifecycle
- session_manager.start()

#### Phase 8: Expose Kernel API
- return KernelRuntime(bus, mailbox_router, session, fabric, orchestrator, planner, model_hub, concierge, bridge)

### 7. SHUTDOWN SEQUENCE (10 Steps in Reverse)
1. concierge.stop() → flush DeltaAggregator, unsubscribe, cancel FrontLock
2. concierge_task.cancel()
3. orchestrator.shutdown() → stop admin HTTP, drain DAG, stop scheduler, unsubscribe events
4. planner.stop() → drain mailbox, emit plan.cancelled per request
5. planner_task.cancel()
6. model_hub.close() → close plugins, flush metrics
7. fabric.shutdown() → stop health checker, module loader
8. session_manager.stop() → final checkpoint, flush events
9. bus.close() → drain subscribers, close ring buffer
10. mailbox_router.close() → drain all mailboxes

### 8. EVENT FLOW EXAMPLES (§9.1-9.12)
- 9.1: User input → Phase 1 → FSM dispatch → Front Actor → LLM → Tools → Response
- 9.2: HIGH tier task → Orchestrator → Planner → DAG execution → Back Actor → Results
- 9.3: MED tier task → Orchestrator direct (max 2 Fabric calls)
- 9.4: LOW tier → Fabric direct capability execution
- 9.5: HIL (Human-in-the-Loop) flow
- 9.6: Delta aggregation → 500ms flush → Bus event → DeltaApplicator
- 9.7: Session checkpoint flow
- 9.8: Bridge K0 recall flow
- 9.9: Experience tick flow
- 9.10: Crash recovery flow
- 9.11: Proactive wake flow
- 9.12: Weaving flow

### 9. 60-POINT VALIDATION CHECKLIST (W-01 to W-60)
Covers: Bus startup/events/topology, SessionState reader/events/checkpoint, Fabric reader/deltas/capabilities, Orchestrator port injection/health/shutdown, Planner factory/ports/health/lifecycle, Concierge FSM/IStatePort/dispatch/HITL, Model Hub factory/ports/budget/plugins, Zero circular imports, test pass rates, performance SLAs.

### 10. OPEN QUESTIONS (Q-01 to Q-10)
- Q-01: JSON vs FlatBuffers for serialization? (JSON for now)
- Q-02: Kernel own session_id or receive from outside? (TBD)
- Q-03: When replace test stubs with real adapters? (After bootstrap proven)
- Q-04: MailboxRouter wired to Fabric agents? (Yes but not yet in Phase 1)
- Q-05: How does K0 enter? (Via IBridgePort + IK0SyncPort, stubs until live)
- Q-06: Single bus or isolated bus domains? (Single with topic namespacing)
- Q-07: When does ConciergeFactory replace monolith? (After M10)
- Q-08: Split IStatePort to IStateReadPort + IStateWritePort? (No, Concierge is ONLY writer)
- Q-09: Concierge front/back mailbox wiring? (Via MailboxRouter, Concierge-internal)
- Q-10: Concierge need direct Planner port? (No, indirect via IDispatchPort)

---

## PART A CONTINUED: ORCHESTRATOR DEEP DIVE

### OrchestratorService Constructor (14 Keyword-Only Parameters)
1. mailbox: IMailboxPort
2. dag_executor: DAGExecutorLike
3. constraint_resolver: ConstraintResolverLike
4. workflow_engine: WorkflowEngineLike
5. connector_lifecycle: ConnectorLifecycleLike
6. error_router: ErrorRouterLike
7. concurrency_guard: ConcurrencyGuardLike
8. fabric_port: IFabricGatewayPort
9. planner_port: IPlannerPort
10. state_port: IStateReadPort
11. delta_port: IDeltaEmitPort
12. bridge_port: IBridgeWritePort
13. event_port: IEventSubscriptionPort
14. config: OrchestratorConfig

Post-construction injection: _admin (if config.admin_enabled)

### OrchestratorService init() Startup (10 Steps)
1. _validate_ports() — assert all 14 constructor params + internals non-None
2. (reserved)
3. await crash_recovery() — read WAL, re-enqueue incomplete DAGs
4. Assert concurrency guard not locked
5. await _discover_mcp_tools() — 500ms timeout
6. await _workflow_engine.registry.list_active()
7. await _workflow_engine.scheduler.start()
8. _subscribe_events() — 5 topics (plan.ready, plan.failed, plan.cancelled, hil_override, hil_fallback)
9. await _workflow_engine.gap_detector.start(); ConnectorLifecycleManager.start_lifecycle_monitoring()
10. _running = True; spawn _reaper_task + _mailbox_loop; if admin: await _admin.start()

### OrchestratorService shutdown() Teardown (9 Steps)
1. _running = False
2. ConnectorLifecycleManager.stop_lifecycle_monitoring()
3. Wait for active DAG completion (30s timeout)
4. (Force compensate — V1: DEFERRED)
5. await _workflow_engine.scheduler.stop()
6. await _workflow_engine.gap_detector.stop(); unsubscribe all 5 event subscriptions
7. (Trigger state persistence — V1: DEFERRED)
8. Final audit write + orphaned context warning
9. Cancel _reaper_task + _loop_task

### OrchestratorConfig Fields (32 Fields)
- **Concurrency (3):** max_concurrent_dags=1, max_wave_parallelism=5, mailbox_capacity=100
- **Timeouts in ms (7):** default_step_timeout_ms=30000, plan_request_timeout_ms=45000, hil_timeout_ms=120000, drain_timeout_ms=30000, shutdown_grace_period_ms=30000, context_reap_interval_ms=5000
- **Retry (3):** step_max_retries=2, step_retry_base_delay_ms=100, step_retry_max_delay_ms=5000
- **Guards (3):** guard_order: List[str], max_micro_replans=1, substep_rate_limit_ms=500
- **Workflow (3):** max_workflow_depth=3, workflow_db_path="data/orchestrator_workflows.db", scheduler_tick_interval_ms=1000
- **MCP Connectors (3):** mcp_config_path, mcp_discovery_interval_ms=300000, mcp_max_servers=10
- **Circuit Breaker CB_PLANNER (3):** cb_planner_failure_threshold=3, cb_planner_reset_timeout_ms=60000, cb_planner_half_open_probes=1
- **Telemetry (4):** metrics_enabled=True, metrics_interval_ms=10000, structured_log_level="INFO", trace_sample_rate=1.0
- **Admin (2):** admin_enabled=True, admin_port=8081
- **Pending Context Limits (2):** max_pending_plans=50, max_pending_hil=20

### Orchestrator Event Topics
- **EMITTED (19):** task.accepted, plan.requested, dag.started, dag.micro_replan, dag.completed, step.started, step.completed, step.failed, step.cancelled, step.skipped, step.retrying, step.schema_retry, saga.compensating, delta.v1, workflow.triggered, workflow.completed, workflow.saved, error.routed, mcp.tool_registered
- **CONSUMED (12):** plan.ready, plan.failed, plan.cancelled, micro_replan.ready, capability.completed, capability.failed, contract.updated, agent.tool_call, agent.llm_call, workflow.trigger_due, hil.override_response, hil.fallback_response

### 4 Active Guards (in order)
1. OutputSchemaGuard — validates output against step.output_schema
2. ConditionalEdgeEvaluator — evaluates step.condition against results
3. MicroReplanCheckpoint — detects discoveries, calls planner.micro_replan()
4. ExecutionMonitor — checks interrupt flag, emits progress delta, optional HIL

### 18 Admin HTTP Endpoints
- Health (3): GET /health/live, /health/ready, /health/status
- DAG (3): GET /admin/dags, /admin/dags/{dag_id}, POST /admin/dags/{dag_id}/cancel
- Circuit Breaker (2): GET /admin/circuit-breakers, POST /admin/circuit-breakers/{name}/state
- Workflow (2): GET /admin/scheduler/triggers, /admin/scheduler/triggers/{workflow_id}
- Mailbox (3): POST /admin/drain, GET /admin/mailbox/depth, /admin/mailbox/stats
- MCP (2): GET /admin/mcp/servers, POST /admin/mcp/rediscover
- Observability (3): GET /admin/config, /admin/metrics, /admin/version

---

## PART B: FABRIC DEEP DIVE (§26-39)

### Architecture
- 6 ports, 12 adapters (6 production + 6 test)
- 9-step execution pipeline
- 6 provider types: MCP, WASM, BRIDGE, AGENT, WORKFLOW, CONCIERGE

### Fabric Factory Internal Wiring (20 Steps)
Creates: ContractValidator, ModuleLoader, PolicyEngine, Resolver, ContextBuilder, OutputValidationPipeline, HealthChecker, AvailabilityTracker, FabricDispatcher, CapabilityFabric

### Fabric Execution Pipeline (9 Steps)
1. Validate request
2. Resolve capability
3. Check availability
4. Build context
5. Apply policies
6. Execute provider
7. Validate output
8. Emit events
9. Return result

### Internal Components
- Resolver: capability name → provider mapping
- PolicyEngine: 4-tier policy (rate limit, budget, safety, governance)
- ContextBuilder: assembles execution context from SS snapshot
- OutputValidationPipeline: validates provider output against contract
- ContractValidator: validates capability contracts at load time
- ModuleLoader: hot-loads capability modules, watches for changes

### Health Infrastructure
- HealthChecker: periodic health checks per provider
- AvailabilityTracker: progressive recovery (OFFLINE → DEGRADED → ONLINE)
- FabricDispatcher: routes to available providers

### Circuit Breaker System
- Per-provider configs, auto-selected by provider type
- State machine: CLOSED → OPEN → HALF_OPEN → CLOSED

### Event Reference
- **Emitted (16):** capability.started, capability.completed, capability.failed, capability.timeout, provider.registered, provider.removed, provider.health_changed, module.loaded, module.unloaded, contract.validated, contract.failed, batch.started, batch.completed, learning.feedback, learning.outcome, delta.v1
- **Consumed (4):** contract.updated, provider.config_changed, module.reload_requested, capability.cancel_requested

---

## PART C: SESSIONSTATE DEEP DIVE (§40-52)

### Architecture
- 96KB budget per session: 48KB HOT + 48KB WARM + unlimited LOCAL COLD (SQLite)

### 12 Session Sections
**HOT Tier (8 sections):**
1. control (NEVER EVICT, 8KB)
2. beliefs_active (8KB, priority 5, demotes to beliefs_history)
3. scoreboard (6KB, priority 6)
4. history_active (8KB, priority 4, demotes to history_recent)
5. clarifications (4KB, priority 7)
6. affective_now (4KB, priority 8)
7. narrative_active (8KB, priority 9)
8. meta (NEVER EVICT, 2KB)

**WARM Tier (4 sections):**
1. telemetry (8KB, priority 1 = first to evict)
2. beliefs_history (12KB, priority 2)
3. history_recent (20KB, priority 3)
4. persona (8KB, priority 10 = last to evict)

### SessionStateManager Constructor (18 Slots)
Internal wiring: 12 steps from store ports → SizeTracker → MutationGuard → HotTier → WarmTier → LocalColdTier → EvictionEngine → MigrationEngine

### 26 Valid Operations
set, append, add_turn, add_fact, create_thread, switch_to, pause_thread, resolve_thread, archive_thread, update_thread, update, register_agent, add_referent, request, add_compressed, add_summarized, set_session_summary, add_vocabulary, clear, delete, record_turn, record_error, accept_demoted, (+ 3 internal)

### MutationGuard 7-Tier Preflight
1. INVALID_SECTION → 2. INVALID_OPERATION → 3. SECTION_LOCKED → 4. EMERGENCY_MODE (>95%) → 5. SECTION_CAPACITY → 6. TIER_CAPACITY → 7. TOTAL_CAPACITY

### Pressure Levels
- NORMAL: < 80%
- ELEVATED: 80-90%
- CRITICAL: 90-95% (triggers eviction)
- EMERGENCY: > 95% (blocks non-CRITICAL mutations)

### Migration Pairs (HOT → WARM)
- history_active → history_recent (priority 1)
- beliefs_active → beliefs_history (priority 2)
- narrative_active → (archivable) (priority 3)

### Event Reference (8 event types)
Session created, started, checkpoint, restored, evicted, migrated, pressure_changed, stopped

---

## PART D: BUS DEEP DIVE (§53-68)

### Design Principles
1. Fire-and-forget, at-most-once
2. Topic-matched fan-out with wildcard (`*` = one segment, `>` = one or more trailing)
3. Handler error isolation (exceptions never propagate to publisher)
4. Zero-allocation hot path
5. Dual backend (Python LocalBus or Rust RustBusAdapter)
6. Causal + sequence ordering via optional TimingChain
7. Middleware pipeline (tracing, metrics, topic validation)

### Envelope (frozen dataclass, 12 fields)
topic, priority (0-3), envelope_id (global monotonic), sequence (per-topic), cognitive_trace_id, session_id, request_id, parent_id (causal parent, 0=root), created_ns, payload (opaque bytes), ttl_ms (V2), payload_format (OPAQUE/JSON/MSGPACK)

### DeliveryMode (3 modes)
- **STRICT:** buffer on gap, enforce causal parent ordering (capability, orchestration, planner, hil, response, session, agent)
- **RELAXED:** deliver as-is, log reorder (affect, constraint, proactive, workflow)
- **BEST_EFFORT:** deliver immediately, droppable (k0.sse, fabric.learning)

### LocalBus Hot Path (8 steps)
1. Guard → 2. STAMP → 3. Track → 4. MIDDLEWARE → 5. CAPTURE → 6. MATCH → 7. DISPATCH → 8. CALL

### 3 Builtin Middlewares
1. TracingMiddleware (OpenTelemetry spans)
2. MetricsMiddleware (Prometheus counters)
3. TopicValidationMiddleware (soft validation, warns but never drops)

### TimingChain Rules (14 topic prefixes)
- STRICT: k1.capability, k1.orchestration, k1.planner, k1.hil, k1.response, k1.session, k1.agent
- RELAXED: k1.affect, k1.constraint, k1.proactive, k1.workflow
- BEST_EFFORT: k1.k0.sse, k1.fabric.learning
- DEFAULT: RELAXED

### Bus Factory (4 methods)
- create_local(backend="auto") → LocalBus
- create_local_ordered() → LocalBus + TimingChain (forces Python backend)
- create_mailbox_router() → LocalMailboxRouter
- create_mailbox(name, config) → LocalMailbox

---

## KEY GOTCHAS (60 total)

### Orchestrator (G-01 to G-12)
- G-01: crash_recovery() before mailbox loop
- G-02: create_production() auto-calls init(), others don't
- G-03: Factory kwargs use short names (mailbox, fabric, planner, state, delta, bridge, event, storage)
- G-04: MockPlannerAdapter is Phase 1 stub only
- G-05: AdminHttpAdapter post-injected via _admin = ...
- G-06: ExecutionMonitor._service_ref post-constructed (circular dep)
- G-07: DeltaEmitAdapter(event_port, delta_bus) takes TWO args
- G-08: WorkflowStorageAdapter wraps SQLiteWorkflowAdapter, not raw db_path
- G-09: Shutdown order: Orch → Fabric → SS → Bus
- G-10: OrchestratorConfig.from_dict() ignores unknown keys
- G-11: Test factories set admin_enabled=False
- G-12: MailboxAdapter capacity must match config

### Planner (P-01 to P-10)
- P-01: create_production() doesn't call start(); kernel must spawn asyncio.create_task()
- P-02: planner.stop() before planner_task.cancel()
- P-03: EventBusAdapter ≠ DeltaBusAdapter (different Fabric interfaces)
- P-04: DeltaBusAdapter pre-stamps agent_id="planner"
- P-05: SessionStateReadAdapter takes session_id (pre-bound)
- P-06: All 7 port slots must be distinct id()
- P-07: TestLLMAdapter/TestBridgeAdapter are Phase 1 stubs only
- P-08: PlannerConfig validates bounds at factory creation
- P-09: MailboxAdapter depth must match planner_config.mailbox_max_depth
- P-10: Phase 5b cross-wire must happen before TaskEnvelope arrives

### Fabric (F-01 to F-12)
- F-01: FabricBusAdapter is SINGLE instance for both IEventPort + IDeltaBusPort
- F-02: SessionStateReaderAdapter(manager, session_id) takes TWO args
- F-03: production_mode=True required for FabricDispatcher
- F-04: module_loader.start(watch=False) at bootstrap; call start_watching() explicitly
- F-05: HealthChecker and CapabilityFabric share same circuit_breakers dict reference
- F-06: AvailabilityTracker enforces progressive recovery (OFFLINE → DEGRADED → ONLINE)
- F-07: Fabric shutdown AFTER Orchestrator, BEFORE SessionState
- F-08: FabricConfig only 2 fields (max_batch_size, default_timeout_ms)
- F-09: Contract files must be in contracts_dir at bootstrap time
- F-10: EventEmitter silently drops events if event_port=None
- F-11: CB per-provider configs auto-selected by provider type
- F-12: create_with_ports() requires ALL 6 port adapters

### SessionState (S-01 to S-12)
- S-01: create_standalone() uses POST-CONSTRUCTION injection for writer/lifecycle
- S-02: create_with_ports() requires all 4 mandatory ports pre-constructed
- S-03: SessionState IEventPort is ABC, not Protocol
- S-04: LocalColdArchive and SQLiteStorageAdapter share db_path
- S-05: SessionStateReaderAdapter(manager, session_id) takes TWO args
- S-06: session_manager.start() must be called before reads/mutations
- S-07: Checkpoint SLA is 50ms
- S-08: StandaloneLifecycle starts daemon timer thread
- S-09: Eviction archive to LOCAL COLD, not K0
- S-10: LifecycleConfig.testing() sets checkpoint_interval_ms=0, restore_on_start=False
- S-11: 96KB budget per-session (multiple sessions scale linearly)
- S-12: 26 valid operations; unknown ops rejected silently

### Bus (B-01 to B-13)
- B-01: Bus MUST be created FIRST
- B-02: Bus MUST be closed LAST
- B-03: SessionBusAdapter extends IEventPort ABC (not Protocol)
- B-04: FabricBusAdapter bridges Dict ↔ bytes
- B-05: TimingChain Python-only; create_local_ordered() forces backend="python"
- B-06: Middleware NEVER reads payload (opaque bytes)
- B-07: publish() silently drops after close()
- B-08: TopicValidationMiddleware is SOFT (warns, never drops)
- B-09: `*` = one segment, `>` = one or more trailing (must be last)
- B-10: capture=True stores all envelopes in memory (testing only)
- B-11: Envelope frozen=True; bus stamps via with_bus_fields()
- B-12: Per-topic sequence monotonic starting at 1
- B-13: ENVELOPE_FORMAT env var controls wire format

---

## DATA MODELS & TYPES (100+ defined)

Key types: Envelope (20 fields), OrchestratorConfig (32 fields), LifecycleConfig, MailboxConfig, CircuitBreakerConfig, SessionSnapshot, PendingPlanContext, PendingHILContext, CapabilityRequest, CapabilityResult, ProviderConfig, ExecutionContext

Key Enums: Priority, DeliveryMode, PayloadFormat, ProviderType, SafetyBand, Availability, Tier, RequestStatus, BatchStrategy, AgentLifecycleState, ManagerState, LifecycleState, CheckpointTrigger, PressureLevel, MutationPriority, MutationStatus, RejectionCategory, MutationResult

---

## FILE LOCATIONS (100+ paths)
- k1/bus/factory.py, k1/bus/local.py, k1/bus/trie.py, k1/bus/mailbox.py
- k1/fabric/fabric.py, k1/fabric/factory.py, k1/fabric/ports.py
- k1/sessionstate/manager.py, k1/sessionstate/factory.py
- k1/orchestrator/factory.py, k1/orchestrator/service.py
- k1/planner/factory.py, k1/planner/agent.py
- k1/concierge/factory.py (TO BE CREATED)
- k1/concierge/kernel/bootstrap.py (current monolith)
- k1/model_hub/factory.py

---

## TODO / DEFERRED ITEMS
1. ConciergeFactory replace monolith (after M10)
2. MailboxRouter wiring to Fabric agents
3. Saga compensation (V1: DEFERRED)
4. Force-compensate timed-out DAGs on shutdown (V1: DEFERRED)
5. State persistence on shutdown (V1: DEFERRED)
6. Circuit Breaker per-provider auto-detection
