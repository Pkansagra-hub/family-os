# K1 Intelligence Kernel - Code Repository Structure

This document outlines the proposed directory structure for the `k1/` module, based on the K1 Cognitive Architecture diagram. It maps the 7-layer architecture (L0-L6) plus coordination mechanisms into a modular Python codebase.

## Overview

- **Layers**: Hierarchical separation (L0 External Interfaces → L1 Concierge → L2 Orchestrator → L2.5 Fabric → L3 Planner → L4 Agents/Tools → L5 SessionState → L6 K0 Bridge).
- **Coordination**: Event Bus, Delta Bus, Mailbox Router for pub/sub and direct routing. SSE integration with K0 for proactive notifications.
- **Principles**: Actor-based concurrency, single-writer/multi-reader SessionState, WFQ scheduling, HITL feedback, learning loops with proactive agent spawning.
- **ADRs**: All components link to formal architectural decisions (e.g., ADR-0005 for agent lifecycle).

## Directory Structure

```text
k1/
├── __init__.py                          # Exports: ConciergeAgent, OrchestratorActor, CapabilityFabric, EventBus, SessionState, DeltaBus, MailboxRouter, ProactiveDecisionEngine
├── main.py                              # Wiring only: Load config (pydantic), instantiate actors/buses/bridges, connect Event Bus/Delta Bus, start supervisors, handle shutdown (signal handlers)
├── README.md                            # Full spec: Layers (L0-L6), flows (e.g., 3-phase orchestration, Delta aggregation), ADRs (e.g., ADR-0005, ADR-0006), setup (deps, env vars), usage (API endpoints), troubleshooting (common errors, logs)
├── pyproject.toml                       # Deps: flatbuffers, pydantic, aiohttp, pykka (actors), aiokafka (Event Bus), opentelemetry (tracing), pytest (tests), uvicorn (if web APIs needed)
├── contracts/                           # Existing: Schemas & interfaces (expanded per diagram)
│   ├── schemas/                         # FlatBuffers .fbs (SessionState.fbs, Event.fbs, Agent.fbs, Delta.fbs)
│   ├── modules/                         # YAML contracts (concierge.yaml, orchestrator.yaml, etc.) - define interfaces, events, syscalls
│   ├── events/                          # JSON schemas for topics (e.g., k1.orchestration.task.announced.v1, k1.agent.lifecycle.spawn)
│   └── sse/                             # SSE-specific schemas and configurations
│       ├── event_schema.json            # SSE event format schema (k0.learning.advisory.validated.v1, etc.)
│       ├── retry_config.yaml            # Retry logic configuration (timeouts, jitter, dead letter)
│       └── security_config.yaml         # SSE security settings (CORS, CSRF, rate limiting)
├── kernel/                             # L0.5: Module Loader System
│   ├── __init__.py                      # Exports: ModuleLoader, registries
│   ├── README.md                        # Module discovery, hot reload, registry management
│   ├── loader.py                        # class ModuleLoader: Scans k1/modules/*/module.yaml, installs components
│   ├── hot_reload.py                    # class HotReloadEngine: File watcher for dev mode
│   └── registries/                      # Module Registries
│       ├── __init__.py                  # Exports: ToolRegistry, PromptRegistry, AgentRegistry
│       ├── tool_registry.py             # class ToolRegistry: Install + lookup + versions
│       ├── prompt_registry.py           # class PromptRegistry: Markdown prompt assets
│       └── agent_registry.py            # class AgentRegistry: YAML agent templates
├── modules/                            # Plugin Modules (User-Installable)
│   ├── <domain>/                        # e.g., health/, finance/, stress_table/
│   │   ├── module.yaml                  # Module metadata, tools, agents
│   │   ├── tools/                       # Domain-specific tools
│   │   │   └── <tool_name>/             # e.g., k0_health_query/
│   │   │       ├── tool.yaml            # Contract: inputs/outputs/scopes
│   │   │       ├── impl.py              # Implementation: calls generic K0 bridge
│   │   │       └── prompts/             # Tool-specific prompts
│   │   │           └── *.md
│   │   └── agents/                      # Optional agent templates
│   │       └── *.yaml
├── concierge/                           # L1: The Chatty Brain (Concierge as single writer to SessionState)
│   ├── __init__.py                      # Exports: ConciergeAgent, ConciergeMailbox
│   ├── README.md                        # Purpose: User interface, state writer. Interfaces: Tool adapters, mailbox. ADRs: ADR-0093 (ConciergeAgent pattern), ADR-0005 (agent lifecycle FSM), ADR-0017 (SessionState 6-section design), ADR-0052 (HITL protocols), ADR-0059 (learning loop), ADR-0086 (dynamic agent creation), ADR-0002 (actor model), ADR-0010 (capability security), ADR-0032 (band-based egress), ADR-0035 (PII detection), ADR-0036 (E2EE), ADR-0037 (JWT), ADR-0053 (message queue coalescing), ADR-0054 (turn boundary), ADR-0055 (context switch), ADR-0065 (UX micro-interactions), ADR-0066 (developer testing), ADR-0067 (conversational delight), ADR-0085 (embodied awareness), ADR-0094 (query_k0_finance tool), ADR-0014 (JSON REST), ADR-0015 (WebSocket), ADR-0016 (SSE), ADR-0040 (WebSocket chat), ADR-0041 (REST session), ADR-0046 (SSE WebSocket bridge)
│   ├── agent.py                         # class ConciergeAgent(Actor): async def handle_message(msg). LLM calls via mailbox. Single writer to SessionState. Handles 11 meta-intents.
│   ├── mailbox.py                       # class ConciergeMailbox: WFQ queue (REALTIME priority). async def send/receive. Integrates with MailboxRouter.
│   ├── tools/                           # Thin adapters only (delegate to Event Bus/tools - no implementation)
│   │   ├── list_resources.py             # def list_available_resources() -> emit k1.tool.query to EventBus
│   │   ├── spawn_planner.py              # def spawn_planner() -> emit k1.agent.lifecycle.spawn to EventBus
│   │   ├── delegate_task.py              # def delegate_task(intent) -> emit k1.orchestration.task.announced to EventBus
│   │   ├── check_safety.py               # def check_safety(input) -> emit k1.agent.safety.check to EventBus
│   │   ├── execute_workflow.py           # def execute_workflow() -> emit k1.workflow.execute to EventBus
│   │   └── update_state.py               # def update_session_state(delta) -> emit to DeltaBus (via DeltaAggregationWindow)
│   ├── persona.py                        # class PersonaEngine: Manage traits (static, rarely changes)
│   ├── style.py                          # class ConversationalStyle: Tone/length control
│   ├── aggregation.py                    # class DeltaAggregationWindow: 500ms batching, conflict resolution (timestamp + confidence scoring)
│   ├── rhythm/                           # L1.5: Conversational Rhythm Controller (NEW)
│   │   ├── __init__.py                   # Exports: RhythmController
│   │   ├── rhythm_patterns.py            # class RhythmPatterns: Q&A, Teaching, Emotional pacing
│   │   ├── dynamic_adjustment.py         # class DynamicAdjustment: User typing speed, cadence mirroring
│   │   └── conversation_beat.py          # class ConversationBeat: Temporal intelligence layer
│   ├── affective/                        # Affective Mirroring Engine (NEW)
│   │   ├── __init__.py                   # Exports: AffectiveMirroringEngine
│   │   ├── affective_mirroring.py        # class AffectiveMirroring: Real-time emotion detection & resonance
│   │   ├── emotion_detector.py           # class EmotionDetector: Sentiment analysis
│   │   └── tone_adjuster.py              # class ToneAdjuster: Dynamic tone adjustment
│   └── empathy/                          # L3.5: Cognitive Empathy Core (NEW)
│       ├── __init__.py                   # Exports: CognitiveEmpathyCore
│       ├── theory_of_mind_engine.py      # class TheoryOfMindEngine: User mental model estimation
│       ├── mental_model_manager.py       # class MentalModelManager: Knowledge, attention tracking
│       └── predictive_completion.py      # class PredictiveCompletion: Anticipatory response system
├── orchestrator/                        # L2: The Coordinator (Pure Actor - no LLM)
│   ├── __init__.py                      # Exports: OrchestratorActor, OrchestratorMailbox
│   ├── README.md                        # Purpose: Execution logic. Interfaces: 3-phase orchestration, agent spawning. ADRs: ADR-0006 (3-phase orchestration), ADR-0086 (dynamic agent creation subsystem), ADR-0005 (agent lifecycle FSM), ADR-0045 (K1 event bus coordination), ADR-0048 (K1 internal event bus), ADR-0028 (weighted fair queuing scheduler), ADR-0007 (4-stage planning), ADR-0008 (saga pattern), ADR-0017 (SessionState), ADR-0049 (fast/smart lane router), ADR-0073 (agent lifecycle enhancements), ADR-0082 (multi-party dialogue), ADR-0093 (concierge pattern), ADR-0002 (actor model), ADR-0009 (circuit breaker)
│   ├── actor.py                         # class OrchestratorActor(Actor): Pure logic. async def negotiate/select/execute. Tool call translation to DAG/agent factories.
│   ├── mailbox.py                       # class OrchestratorMailbox: WFQ REALTIME
│   ├── orchestration/                   # 3-Phase (ADR-0006, ADR-0006a-d)
│   │   ├── negotiation.py               # class ContractNet: Announce tasks (k1.orchestration.task.announced), collect proposals (k1.orchestration.proposal.submitted)
│   │   ├── selection.py                 # class MultiCriteriaScorer: Score proposals (capability + latency + cost + specialization) (k1.orchestration.proposals.scored)
│   │   ├── execution.py                 # class DAGExecutor: Parallel tasks with dependencies, Saga recovery (k1.orchestration.execution.dag.started, k1.orchestration.saga.rollback)
│   │   └── constraint_resolution_engine/ # Constraint Resolution Engine (NEW)
│   │       ├── __init__.py              # Exports: ConstraintResolutionEngine
│   │       ├── constraint_manager.py    # class ConstraintManager: Oversees iterative flow
│   │       ├── iteration_controller.py  # class IterationController: Max 3 cycles
│   │       ├── constraint_graph.py      # class ConstraintGraph: Priority & dependencies
│   │       ├── solution_validator.py    # class SolutionValidator: LLM + rule-based
│   │       ├── fallback_trigger.py      # class FallbackTrigger: → HIL when stuck
│   │       └── capability_constraint_resolver.py # class CapabilityConstraintResolver: Fabric-aware validation
│   ├── spawning/                        # ADR-0086
│   │   ├── registry.py                  # class AgentRegistry (58+ types, O(1) lookups), PromptRegistry (Jinja2 templates), ToolRegistry (MCP + direct)
│   │   ├── factory.py                   # class AgentFactory: Singleton, resource reservation, ID generation (k1.agent.factory.create)
│   │   └── composition.py               # class CompositionEngine: Inject prompts/tools/persona, injection protection (k1.agent.composition.build)
│   ├── workflows/                       # User Workflow System (NEW)
│   │   ├── __init__.py                  # Exports: WorkflowSystem
│   │   ├── workflow_registry.py         # class WorkflowRegistry: Text-defined automation, version pointers
│   │   ├── workflow_compiler.py         # class WorkflowCompiler: Compile to DAG
│   │   ├── workflow_scheduler.py        # class WorkflowScheduler: Time/event triggers
│   │   └── run_supervisor.py            # class RunSupervisor: Leases, lifecycle, interrupt handling
│   └── connectors/                      # Connector Ecosystem (NEW)
│       ├── __init__.py                  # Exports: ConnectorEcosystem
│       ├── local_mcp_servers.py         # class LocalMCPServers: Device-hosted tools
│       ├── remote_mcp_servers.py        # class RemoteMCPServers: Company-hosted via K0
│       ├── k0_proxy.py                  # class K0ConnectorProxy: Auth, routing, caching
│       └── sandbox_executor.py          # class SandboxExecutor: Isolation, rate limiting
├── fabric/                              # L2.5: Capability Fabric (ADR-K004 Adaptation) (NEW)
│   ├── __init__.py                      # Exports: CapabilityFabric
│   ├── README.md                        # Purpose: Dynamic invocation & resolution. ADRs: ADR-K004
│   ├── core/                            # Capability Fabric Core
│   │   ├── capability_fabric.py         # class CapabilityFabric: Dynamic invocation
│   │   ├── fabric_mailbox.py            # class FabricMailbox: WFQ REALTIME
│   │   ├── capability_registry.py       # class CapabilityRegistry: Agent/Tool index
│   │   ├── capability_loader.py         # class CapabilityLoader: Contract-based discovery
│   │   ├── capability_resolver.py       # class CapabilityResolver: Provider selection + QoS
│   │   ├── capability_context_builder.py # class ContextBuilder: SessionState → Fabric context
│   │   └── context_budget.py            # class ContextBudget: Token budget manager
│   ├── providers/                       # Capability Providers
│   │   ├── agent_providers.py           # class AgentProviders: 58+ agent types
│   │   ├── tool_providers.py            # class ToolProviders: MCP tools
│   │   ├── workflow_providers.py        # class WorkflowProviders: Pre-compiled workflows
│   │   └── concierge_providers.py       # class ConciergeProviders: FSM state handlers
│   ├── contracts/                       # Capability Contracts
│   │   ├── agent_contracts.py           # YAML definitions in k1/contracts/agents/
│   │   ├── tool_contracts.py            # YAML definitions in k1/contracts/tools/
│   │   ├── workflow_contracts.py        # Compiled from WorkflowRegistry
│   │   └── capability_versioning.py     # Versioning & compatibility
│   ├── policy/                          # Fabric Policy Engine
│   │   ├── affective_routing.py         # class AffectiveRouting: Emotion-aware selection
│   │   ├── cognitive_load_routing.py    # class CognitiveLoadRouting: Complexity-aware
│   │   ├── qos_integration.py           # class QoSIntegration: Budget-aware
│   │   └── security_context.py          # class SecurityContext: Band-based access
│   ├── module_registry/                 # Module Registry (K0 Pattern)
│   │   ├── module_loader.py             # class ModuleLoader: Loads contracts
│   │   ├── module_validator.py          # class ContractValidator: Schema validation
│   │   └── module_cache.py              # class ModuleCache: Hot-loaded contracts
│   ├── provider_resolution/             # Provider Resolution Engine
│   │   ├── provider_matcher.py          # class ProviderMatcher: Capability → implementation
│   │   ├── provider_selector.py         # class ProviderSelector: QoS + affective + context-aware
│   │   └── provider_factory.py          # class ProviderFactory: Instantiate handlers
│   └── capability_types/                # Capability Type Registry
│       ├── agent_capabilities.py        # agent.spawn.*, agent.execute.*
│       ├── tool_capabilities.py         # tool.execute.*, tool.read.*
│       ├── workflow_capabilities.py     # workflow.run.*
│       └── concierge_capabilities.py    # concierge.state.*
├── planner/                             # L3: The Strategist (Conditional - LLM-powered)
│   ├── __init__.py                      # Exports: PlannerAgent, PlannerMailbox
│   ├── README.md                        # Purpose: Conditional planning. Interfaces: 4-stage pipeline, HITL. ADRs: ADR-0007 (4-stage), ADR-0005 (agent lifecycle), ADR-0052 (HITL), ADR-0002 (actor model), ADR-0008 (saga), ADR-0017 (SessionState), ADR-0027 (model placement), ADR-0033 (tool execution), ADR-0058 (intent classification), ADR-0059 (learning loop), ADR-0078 (tool batching), ADR-0079 (learning drift)
│   ├── agent.py                         # class PlannerAgent(Actor): LLM-powered planning
│   ├── mailbox.py                       # class PlannerMailbox: WFQ INTERACTIVE
│   ├── pipeline/                        # ADR-0007
│   │   ├── sketch.py                    # class SketchStage: LLM plan sketch, high-level intent analysis
│   │   ├── expand.py                    # class ExpandStage: Lookup prompts/tools from registries
│   │   ├── validate.py                  # class ValidateStage: Rule-based + arbiter validation, safety/feasibility checks
│   │   └── commit.py                    # class CommitStage: Persist to K0 WAL (k1.planning.commit)
│   └── hil/                             # HITL (ADR-0052)
│       ├── clarification.py             # class RequirementClarifier: User clarification (k1.user.feedback.planning)
│       ├── approval.py                  # class PlanApprover: Plan approval
│       └── monitoring.py                # class ExecutionMonitor: Progress monitoring
├── agents/                              # L4: The Workers (Dynamic Sub-Agents & Tools)
│   ├── __init__.py                      # Exports: BaseAgent, AgentLifecycleFSM
│   ├── README.md                        # Purpose: Dynamic execution. Interfaces: FSM, tools. ADRs: ADR-0005 (lifecycle FSM), ADR-0002 (actor model), ADR-0086 (dynamic creation), ADR-0006 (orchestration), ADR-0008 (saga), ADR-0027 (model placement), ADR-0033 (tool execution), ADR-0058 (intent classification), ADR-0059 (learning loop), ADR-0078 (tool batching), ADR-0079 (learning drift)
│   ├── lifecycle.py                     # class AgentLifecycleFSM: States (PENDING→WARMING→ACTIVE→IDLE→DRAINING→TERMINATED)
│   ├── base.py                          # class BaseAgent(Actor): Mailbox, hooks, tool execution
│   ├── dynamic/                        # Instances
│   │   ├── planner_instance.py          # class PlannerAgentInstance: Spawned planner
│   │   ├── researcher.py                # class ResearcherAgent: Background priority
│   │   ├── safety.py                    # class SafetyWatchAgent: URGENT priority
│   │   ├── custom.py                    # class CustomAgent: Prompt + tools + persona
│   │   ├── context_updater.py           # class ContextUpdaterAgent: SSE-triggered context updates
│   │   ├── learning_enactor.py          # class LearningEnactorAgent: Implements learning opportunities
│   │   ├── memory_consolidator.py       # class MemoryConsolidatorAgent: Processes episodic memory
│   │   ├── behavior_analyzer.py         # class BehaviorAnalyzerAgent: Analyzes user patterns
│   │   ├── opportunity_spotter.py       # class OpportunitySpotterAgent: Spots upcoming needs
│   │   └── agent_capability_bindings.py # class AgentCapabilityBindings: Agent ↔ Capability mappings
│   └── mailboxes/                       # Dynamic allocation
│       ├── pool.py                      # class MailboxPool: MPSC queues, WFQ integration
│       ├── planner_mailbox_instance.py  # class PlannerMailboxInstance: WFQ INTERACTIVE
│       ├── researcher_mailbox.py        # class ResearcherMailbox: WFQ BACKGROUND
│       ├── safety_mailbox.py            # class SafetyMailbox: WFQ URGENT
│       └── custom_mailboxes.py          # class CustomMailboxes: Dynamic allocation
├── tools/                               # Shared Tool Infrastructure (Centralized - L4)
│   ├── __init__.py                      # Exports: MCPToolRunner, WASMSandbox, ModelInferenceCascade
│   ├── README.md                        # Purpose: Execution infra. Interfaces: Run tools. ADRs: ADR-0078 (batching), ADR-0033 (tool execution), ADR-0034 (MCP protocol), ADR-0027 (model placement), ADR-0058 (intent classification), ADR-0059 (learning loop), ADR-0079 (learning drift)
│   ├── mcp_runners.py                   # class MCPToolRunner: Sandbox MCP tools
│   ├── wasm_sandbox.py                  # class WASMSandbox: Execute WASM
│   └── model_inference.py               # class ModelInferenceCascade: NPU→GPU→CPU→Remote with thermal hysteresis
├── sessionstate/                        # L5: The Memory (Multi-Tier Storage)
│   ├── __init__.py                      # Exports: SessionState
│   ├── README.md                        # Purpose: Shared state. Interfaces: Read/write, tiers. ADRs: ADR-0017 (concurrency), ADR-0020 (tiers), ADR-0021 (retention), ADR-0018 (eviction), ADR-0019 (serialization), ADR-0025 (KV cache), ADR-0031 (cost tracking), ADR-0039 (backpressure), ADR-0060 (adaptive cache), ADR-0076 (optimization)
│   ├── store.py                         # class SessionState: Single-writer (Concierge), multi-reader, 6 sections, LRU eviction
│   ├── sections/                        # 6 Sections + Emotional/Narrative (NEW)
│   │   ├── beliefs.py                   # class BeliefsSection: Facts/preferences (LRU Medium)
│   │   ├── scoreboard.py                # class ScoreboardSection: QUD/commitments (LRU High)
│   │   ├── control.py                   # class ControlSection: Flow/agent leases (LRU Critical, ephemeral)
│   │   ├── flow_leases.py               # class FlowLeases: active_flows[], user_attention, interrupt_policy (NEW)
│   │   ├── persona.py                   # class PersonaSection: Static traits
│   │   ├── multimodal.py                # class MultimodalSection: Context (LRU Medium)
│   │   ├── history.py                   # class HistorySection: Conversation continuity
│   │   ├── telemetry.py                 # class TelemetrySection: Costs/meta (LRU Low)
│   │   ├── affective_section.py         # class AffectiveSection: Emotional trajectory, baseline (NEW)
│   │   ├── mental_model_section.py      # class MentalModelSection: User knowledge, attention (NEW)
│   │   ├── threads_section.py           # class ThreadsSection: Conversation threads, suspension (NEW)
│   │   └── narrative_section.py         # class NarrativeSection: Storytelling, longitudinal coherence (NEW)
│   └── tiers/                           # ADR-0020
│       ├── hot.py                       # class HotTier: RAM <1ms, capacity >56MB → evict to Warm
│       ├── warm.py                      # class WarmTier: SSD <50ms, 30d retention (GREEN/AMBER), 7d (RED)
│       └── cold.py                      # class ColdTier: Object storage <500ms, 365d (GREEN/AMBER), 90d (RED)
├── k0_bridge/                          # L6: The Archive (Durable Kernel Bridge)
│   ├── __init__.py                      # Exports: K0Bridge
│   ├── README.md                        # Purpose: Durable ops. Interfaces: P01-P20 ports. ADRs: ADR-0018 (memory writer), ADR-0020 (multi-tier storage), ADR-0022 (bridge batching), ADR-0044 (HTTP2 FlatBuffers), ADR-0011 (FlatBuffers), ADR-0019 (SessionState serialization), ADR-0014 (JSON REST), ADR-0015 (WebSocket), ADR-0016 (SSE), ADR-0040 (WebSocket chat), ADR-0041 (REST session), ADR-0042 (SSE streaming), ADR-0043 (SSE topic), ADR-0046 (SSE WebSocket bridge)
│   ├── bridge.py                        # class K0Bridge: aiohttp client, FlatBuffers/JSON, 3-retry failover
│   ├── protocol.py                      # class BridgeProtocol: Serialization
│   ├── services/                        # K0 Services
│   │   ├── memory.py                    # class K0MemoryOps: Query/write
│   │   ├── persistence.py               # class K0Persistence: WAL
│   │   ├── receipts.py                  # class K0Receipts: Audit trail
│   │   ├── affect_analysis.py           # class K0AffectAnalysis: UltraBERT inference, real-time emotional analysis (NEW)
│   │   └── learning_bridge.py           # class K0K1LearningBridge: SSE events, proactive spawns (k1.k0.bridge.learning)
│   └── backends/                        # K0 Backends
│       ├── wal.py                       # class K0WALBackend: SQLite WAL
│       └── object.py                    # class K0ObjectBackend: MinIO/S3
├── bus/                                 # Coordination: The Nervous System
│   ├── __init__.py                      # Exports: EventBus, DeltaBus, MailboxRouter
│   ├── README.md                        # Purpose: Routing. Interfaces: Pub/sub, direct. ADRs: ADR-0048 (routing), ADR-0017 (Delta Bus), ADR-0045 (event bus coordination), ADR-0049 (fast/smart lane router), ADR-0014 (JSON REST), ADR-0015 (WebSocket), ADR-0016 (SSE), ADR-0022 (bridge batching), ADR-0023 (cursor pagination), ADR-0034 (MCP protocol), ADR-0040 (WebSocket chat), ADR-0041 (REST session), ADR-0042 (SSE streaming), ADR-0043 (SSE topic), ADR-0044 (HTTP2 FlatBuffers), ADR-0046 (SSE WebSocket bridge)
│   ├── event_bus.py                     # class EventBus: aiokafka pub/sub (topics: k1.orchestration.*, k1.agent.*, etc.)
│   ├── delta_bus.py                     # class DeltaBus: Dumb transport for state deltas (no aggregation - delegates to DeltaAggregationWindow)
│   └── mailbox_router.py                # class MailboxRouter: UUID → mailbox, location transparent
├── scheduler/                           # Top-Level: Performance Scheduling
│   ├── __init__.py                      # Exports: WFQScheduler
│   ├── README.md                        # Purpose: Priority/latency. Interfaces: Queue tasks. ADRs: ADR-0028 (WFQ), ADR-0024 (performance budgets), ADR-0026 (thermal hysteresis), ADR-0027 (model placement), ADR-0029 (Prometheus metrics), ADR-0030 (trace sampling), ADR-0031 (cost tracking), ADR-0039 (backpressure cascade), ADR-0060 (adaptive cache), ADR-0061 (backpressure cascade), ADR-0076 (KV cache optimization), ADR-0077 (thermal placement)
│   ├── wfq.py                           # class WFQScheduler: Priority queues (URGENT=4, REALTIME=3, INTERACTIVE=2, BACKGROUND=1)
│   ├── latency.py                       # class LatencyBalancer: AI <500ms, pure actors <5ms
│   └── placement.py                     # class ModelPlacement: Cascade with hysteresis
├── supervision/                         # Top-Level: Failure Recovery
│   ├── __init__.py                      # Exports: Supervisor
│   ├── README.md                        # Purpose: Monitoring/recovery. Interfaces: Health checks. ADRs: ADR-0002b (recovery), ADR-0005d (FSM), ADR-0002 (actor model), ADR-0005 (agent lifecycle), ADR-0009 (circuit breaker), ADR-0024 (performance budgets), ADR-0026 (thermal hysteresis), ADR-0029 (Prometheus metrics), ADR-0030 (trace sampling), ADR-0038 (audit trail), ADR-0050 (multi-device sync), ADR-0061 (backpressure cascade), ADR-0070 (observability evaluation), ADR-0074 (pluggable modules), ADR-0075 (layer5 extensibility), ADR-0077 (thermal placement), ADR-0080 (continuous config hot-reload), ADR-0081 (K0 knowledge graph), ADR-0084 (memory consolidation), ADR-0087 (KG MCP semantic enhancement), ADR-0088 (local paths migration), ADR-0090 (deployment strategy), ADR-0091 (K0 observability), ADR-0092 (remediation service)
│   ├── supervisor.py                    # class Supervisor: <2s detection, 1Hz ping, exponential backoff
│   ├── cleanup.py                       # class SessionStateCleanup: Remove leases, mark flows interrupted
│   └── blacklist.py                     # class BlacklistManager: 3 crashes/10min → 1hr ban
├── learning/                            # Top-Level: Learning Loop
│   ├── __init__.py                      # Exports: FeedbackSignalCollector, ProactiveDecisionEngine, etc.
│   ├── README.md                        # Purpose: Adaptation. Interfaces: Signals, updates. ADRs: ADR-0059 (learning), ADR-0059a-e, ADR-0058 (intent classification), ADR-0079 (learning drift detection), ADR-0081 (K0 knowledge graph), ADR-0084 (memory consolidation), ADR-0087 (KG MCP semantic enhancement)
│   ├── signal_collector.py              # class FeedbackSignalCollector: 3-tier signals (explicit/implicit/behavioral)
│   ├── drift_detector.py                # class DriftDetector: Statistical divergence
│   ├── advisory_emitter.py              # class AdvisoryEmitter: Parameter recommendations (k1.learning.advisory.emitted)
│   ├── parameter_updater.py             # class ParameterUpdater: Adjust thresholds/temperature
│   ├── proactive_decision.py            # class ProactiveDecisionEngine: LLM-based analysis for proactive actions (k1.proactive.decision.made.v1)
│   ├── proactive_spawner.py             # class ProactiveAgentSpawner: LLM questions, feedback, SSE-triggered spawns (k1.agent.proactive.spawned)
│   ├── rollback_handler.py              # class AuditRollbackHandler: Safety, rollback
│   └── synthetic_pipeline.py            # class SyntheticDataPipeline: Bootstrapping examples
├── memory_writer/                       # Top-Level: Memory Writer System
│   ├── __init__.py                      # Exports: MemoryWriterAgent
│   ├── README.md                        # Purpose: Durable memory. Interfaces: Summarize, emit. ADRs: ADR-0018 (writer), ADR-0018a-b, ADR-0020 (multi-tier storage), ADR-0022 (bridge batching), ADR-0044 (HTTP2 FlatBuffers), ADR-0011 (FlatBuffers), ADR-0019 (SessionState serialization), ADR-0014 (JSON REST), ADR-0015 (WebSocket), ADR-0016 (SSE), ADR-0040 (WebSocket chat), ADR-0041 (REST session), ADR-0042 (SSE streaming), ADR-0043 (SSE topic), ADR-0046 (SSE WebSocket bridge), ADR-0081 (K0 knowledge graph), ADR-0084 (memory consolidation), ADR-0087 (KG MCP semantic enhancement)
│   ├── agents.py                        # class MemoryWriterAgent: LLM summarizers (Episodic/Semantic/KG/Procedural/Prospective/Social/Vector)
│   ├── delta_emitter.py                 # class StateDeltaEmitter: 250ms batch to K0 (P02, P05, P06)
│   └── aggregator.py                    # class DeltaAggregator: Dedupe, compress, priority queuing
├── cache/                               # Top-Level: Adaptive KV Cache
│   ├── __init__.py                      # Exports: CacheSizeAllocator
│   ├── README.md                        # Purpose: Cache management. Interfaces: Size, eviction. ADRs: ADR-0060 (cache), ADR-0060a-b, ADR-0025 (KV cache management), ADR-0076 (KV cache optimization), ADR-0024 (performance budgets), ADR-0026 (thermal hysteresis), ADR-0027 (model placement), ADR-0077 (thermal placement)
│   ├── size_allocator.py                # class CacheSizeAllocator: Dynamic allocation
│   ├── evictor.py                       # class HotColdEvictor: LRU with thermal data
│   ├── rewarmer.py                      # class RapidRewarmer: <50ms reactivation
│   └── thermal_integrator.py            # class ThermalCacheIntegrator: Temperature adjustments
├── hitl/                                # Top-Level: HITL Feedback Loops
│   ├── __init__.py                      # Exports: ConciergeUserLoop
│   ├── README.md                        # Purpose: User feedback. Interfaces: Bidirectional. ADRs: ADR-0052 (HITL), ADR-0053 (message queue coalescing), ADR-0054 (turn boundary management), ADR-0055 (context switch detection), ADR-0065 (UX micro-interactions), ADR-0066 (developer testing), ADR-0067 (conversational delight), ADR-0085 (embodied awareness), ADR-0094 (query_k0_finance tool)
│   ├── concierge_loop.py                # class ConciergeUserLoop: Conversational feedback (k1.user.feedback.conversational)
│   ├── planner_loop.py                  # class PlannerUserLoop: Planning feedback
│   ├── subagents_loop.py                # class SubAgentsUserLoop: Execution feedback
│   └── orchestrator_loop.py             # class OrchestratorUserLoop: Resource feedback
├── connectors/                          # Top-Level: Connector Ecosystem (NEW)
│   ├── __init__.py                      # Exports: ConnectorEcosystem
│   ├── README.md                        # Purpose: Local/Remote MCP servers, K0 proxy, sandboxing. ADRs: ADR-0034 (MCP protocol), ADR-0044 (HTTP2 FlatBuffers)
│   ├── local_mcp_servers.py             # class LocalMCPServers: Device-hosted tools/sensors
│   ├── remote_mcp_servers.py            # class RemoteMCPServers: Company-hosted via K0
│   ├── k0_proxy.py                      # class K0ConnectorProxy: Auth, routing, caching
│   └── sandbox_executor.py              # class SandboxExecutor: Isolation, rate limiting, security
├── sse/                                 # Top-Level: SSE Notification System (Runtime) (NEW)
│   ├── __init__.py                      # Exports: SSEClient
│   ├── README.md                        # Purpose: Proactive notifications from K0. Interfaces: SSE streams. ADRs: ADR-0016 (SSE), ADR-0042 (SSE streaming), ADR-0043 (SSE topic), ADR-0046 (SSE WebSocket bridge)
│   ├── sse_client.py                    # class SSEClient: Connection management, auth, compression
│   ├── sse_event_handler.py             # class SSEEventHandler: Event processing, proactive triggers
│   └── proactive_trigger_manager.py     # class ProactiveTriggerManager: Decision gating, cooldowns
├── retention/                           # Top-Level: Retention & Lifecycle Management (NEW)
│   ├── __init__.py                      # Exports: RetentionManager
│   ├── README.md                        # Purpose: Automated deletion, grace periods, compliance. ADRs: ADR-0021 (retention), ADR-0020 (multi-tier storage)
│   ├── retention_policies.py            # class RetentionPolicies: GREEN/AMBER/RED/BLACK bands
│   ├── deletion_manager.py              # class DeletionManager: Automated/user deletion, grace recovery
│   └── audit_compliance.py              # class AuditCompliance: Hard deletes, compliance metrics
├── tracing/                             # Top-Level: Cognitive Trace ID System (NEW)
│   ├── __init__.py                      # Exports: CognitiveTrace
│   ├── README.md                        # Purpose: Causality tracking across fabrics. ADRs: ADR-0030 (trace sampling), ADR-0038 (audit trail)
│   └── cognitive_trace.py               # class CognitiveTrace: Monotonic sequence IDs, fork prevention
├── coordination/                        # Coordination Mechanisms (NEW)
│   ├── __init__.py                      # Exports: CoordinationMechanisms
│   ├── sessionstate_concurrency/        # SessionState Concurrency (ADR-0017)
│   │   ├── single_writer.py             # class SingleWriter: Concierge only updates
│   │   ├── multi_reader.py              # class MultiReader: <1ms read latency
│   │   └── six_sections.py              # class SixSections: beliefs/control/scoreboard/persona/multimodal/meta
│   ├── observability/                   # Observability Layer (NEW)
│   │   ├── metrics_aggregator.py        # class MetricsAggregator: Performance & usage
│   │   └── health_check_orchestrator.py # class HealthCheckOrchestrator: Fabric provider health
│   └── llm_model_hub/                   # LLM Model Hub (NEW)
│       ├── hub_router.py                # class HubRouter: Load balancing & fallback
│       ├── hub_openai.py                # class HubOpenAI: OpenAI API access
│       ├── hub_anthropic.py             # class HubAnthropic: Anthropic API access
│       └── hub_others.py                # class HubOthers: Other providers
├── config/                              # The Settings
│   ├── __init__.py                      # Exports: settings
│   ├── settings.py                      # pydantic BaseSettings: Env vars, config files
├── scripts/                             # Utilities
│   ├── sync_architecture.py             # Run governance sync (GATE 0/5)
│   ├── migrate_sessionstate.py          # Tier migrations (ADR-0020)
│   └── benchmark_inference.py           # Latency tests (ADR-0028)
└── docs/                                # Knowledge
    ├── diagrams/                        # Mermaid (e.g., k1_cognitive_architecture_skeleton.mmd)
    ├── adrs/                            # Links to docs/architecture/decisions-K0/
    └── runbooks/                        # Guides: Setup, troubleshooting, performance tuning
```

## Folder Descriptions

### Root Level

- **`__init__.py`**: Package initialization, exports key classes for external use.
- **`main.py`**: Entry point for running K1. Handles config loading, actor instantiation, bus connections, supervisor startup, and graceful shutdown.
- **`README.md`**: Comprehensive documentation including architecture layers, event flows, ADR references, dependency setup, API usage, and troubleshooting.
- **`pyproject.toml`**: Project metadata, dependencies (e.g., async libraries, serialization), build config, and optional test/dev tools.

### contracts/

- **`schemas/`**: FlatBuffers schema files (.fbs) for structured data like SessionState, Events, Agents, and Deltas. ADRs: ADR-0011 (FlatBuffers), ADR-0012 (76 FlatBuffers schemas), ADR-0013 (pipeline versioning), ADR-0019 (SessionState serialization)
- **`modules/`**: YAML files defining module contracts, interfaces, and syscalls for each component (e.g., concierge.yaml specifies tool adapters).
- **`events/`**: JSON schemas for Event Bus topics, ensuring message validation (e.g., k1.orchestration.task.announced.v1). ADRs: ADR-0047 (OpenAPI 3.1 REST specs)
- **`sse/`**: SSE-specific configurations and schemas for K0-K1 communication (event formats, retry logic, security settings).

### concierge/ (L1)

- **`__init__.py`**: Exports ConciergeAgent and ConciergeMailbox.
- **`README.md`**: Details purpose (user interface, state writer), interfaces (tool calls, mailbox), and ADRs.
- **`agent.py`**: Core LLM-powered agent handling 11 meta-intents, single writer to SessionState.
- **`mailbox.py`**: WFQ priority queue for REALTIME messages, integrated with MailboxRouter.
- **`tools/`**: Thin wrapper functions emitting events to EventBus (no direct implementation).
- **`persona.py`**: Manages static personality traits.
- **`style.py`**: Controls conversational tone and length.
- **`aggregation.py`**: Batches state deltas with conflict resolution.
- **`rhythm/`**: Conversational pacing and cadence management (L1.5).
  - **`rhythm_patterns.py`**: Q&A, teaching, emotional pacing patterns.
  - **`dynamic_adjustment.py`**: User typing speed and cadence mirroring.
  - **`conversation_beat.py`**: Temporal intelligence layer.
- **`affective/`**: Real-time emotional analysis and resonance.
  - **`affective_mirroring.py`**: Emotion detection and tone adjustment.
  - **`emotion_detector.py`**: Sentiment and affect analysis.
  - **`tone_adjuster.py`**: Dynamic emotional tone control.
- **`empathy/`**: Cognitive empathy and mental modeling (L3.5).
  - **`theory_of_mind_engine.py`**: User mental model estimation.
  - **`mental_model_manager.py`**: Knowledge and attention tracking.
  - **`predictive_completion.py`**: Anticipatory response system.

### orchestrator/ (L2)

- **`__init__.py`**: Exports OrchestratorActor and OrchestratorMailbox.
- **`README.md`**: Covers execution logic, 3-phase orchestration, and spawning ADRs.
- **`actor.py`**: Pure logic actor for negotiation, selection, execution; translates tool calls to DAGs/agents.
- **`mailbox.py`**: WFQ REALTIME queue.
- **`orchestration/`**: Submodules for Contract Net negotiation, multi-criteria scoring, and DAG execution with Saga recovery.
- **`spawning/`**: Registries (Agent, Prompt, Tool), Factory (singleton for creation), Composition Engine (injects configs safely).
- **`workflows/`**: Text-defined automation and scheduling.
  - **`workflow_registry.py`**: Manages workflow definitions and version pointers.
  - **`workflow_compiler.py`**: Compiles workflows to executable DAGs.
  - **`workflow_scheduler.py`**: Handles time and event-based triggers.
  - **`run_supervisor.py`**: Manages workflow execution with leases and interrupts.
- **`connectors/`**: Local and remote MCP server integration.
  - **`local_mcp_servers.py`**: Device-hosted tools and sensors.
  - **`remote_mcp_servers.py`**: Company-hosted systems via K0 proxy.
  - **`k0_proxy.py`**: Authentication, routing, and caching for remotes.
  - **`sandbox_executor.py`**: Secure execution with isolation.

### planner/ (L3)

- **`__init__.py`**: Exports PlannerAgent and PlannerMailbox.
- **`README.md`**: Conditional planning, 4-stage pipeline, HITL interfaces.
- **`agent.py`**: LLM-driven planning actor.
- **`mailbox.py`**: WFQ INTERACTIVE queue.
- **`pipeline/`**: Stages for sketching, expanding, validating, and committing plans.
- **`hil/`**: Human-in-the-loop components for clarification, approval, and monitoring.

### agents/ (L4)

- **`__init__.py`**: Exports BaseAgent and AgentLifecycleFSM.
- **`README.md`**: Dynamic execution, FSM states, tool interfaces.
- **`lifecycle.py`**: FSM managing agent states (PENDING to TERMINATED).
- **`base.py`**: Base class for agents with mailbox hooks and tool execution.
- **`dynamic/`**: Specific agent instances (PlannerAgentInstance, ResearcherAgent, SafetyWatchAgent, CustomAgent, and proactive agents).
- **`mailboxes/`**: Pool for dynamic MPSC queues with WFQ integration.

### tools/ (L4)

- **`__init__.py`**: Exports tool runners and inference cascade.
- **`README.md`**: Execution infrastructure, batching ADRs.
- **`mcp_runners.py`**: Sandbox for MCP tools.
- **`wasm_sandbox.py`**: WASM execution environment.
- **`model_inference.py`**: Cascade for model placement (NPU→GPU→CPU→Remote).

### sessionstate/ (L5)

- **`__init__.py`**: Exports SessionState.
- **`README.md`**: Shared memory, concurrency, tiers, retention ADRs.
- **`store.py`**: Core store with single-writer/multi-reader, 6 sections, LRU eviction.
- **`sections/`**: Individual sections (beliefs, scoreboard, etc.) with specific eviction policies.
  - **Existing**: beliefs, scoreboard, control, persona, multimodal, history, telemetry.
  - **New Emotional/Narrative**: affective_section (emotional trajectory), mental_model_section (knowledge/attention), threads_section (conversation threads), narrative_section (storytelling coherence).
- **`control/flow_leases.py`**: Manages active_flows[], user_attention, interrupt_policy for workflow arbitration.
- **`tiers/`**: Hot (RAM), Warm (SSD), Cold (Object Storage) with retention rules.

### k0_bridge/ (L6)

- **`__init__.py`**: Exports K0GenericClient, EnvelopeBuilder.
- **`README.md`**: Generic transport bridge, schema-driven envelopes, no domain logic.
- **`client.py`**: K0GenericClient - transport, auth, retries only.
- **`envelope_builder.py`**: EnvelopeBuilder - schema-driven envelope construction.
- **`codecs/`**: Encoding/decoding for JSON, FlatBuffers.
- **`backends/`**: Transport backends (HTTP, Unix socket, gRPC, etc.).

### bus/ (Coordination)

- **`__init__.py`**: Exports EventBus, DeltaBus, MailboxRouter.
- **`README.md`**: Pub/sub routing, Delta Bus patterns.
- **`event_bus.py`**: aiokafka for topic-based messaging.
- **`delta_bus.py`**: Transport for state deltas (no aggregation).
- **`mailbox_router.py`**: UUID-to-mailbox mapping.

### scheduler/ (Top-Level)

- **`__init__.py`**: Exports WFQScheduler.
- **`README.md`**: Priority scheduling, latency balancing.
- **`wfq.py`**: Weighted Fair Queuing with priority levels.
- **`latency.py`**: Balancing for AI vs. pure actors.
- **`placement.py`**: Model placement cascade.

### supervision/ (Top-Level)

- **`__init__.py`**: Exports Supervisor.
- **`README.md`**: Failure recovery, health checks.
- **`supervisor.py`**: Monitoring with heartbeat and backoff.
- **`cleanup.py`**: SessionState cleanup on failures.
- **`blacklist.py`**: Crash-based blacklisting.

### learning/ (Top-Level)

- **`__init__.py`**: Exports learning components.
- **`README.md`**: Adaptation via signals, drift detection, advisories.
- **`signal_collector.py`**: Collects 3-tier feedback signals.
- **`drift_detector.py`**: Detects performance divergence.
- **`advisory_emitter.py`**: Emits parameter recommendations.
- **`parameter_updater.py`**: Adjusts model/planner params.
- **`proactive_decision.py`**: LLM-based analysis for proactive actions.
- **`proactive_spawner.py`**: Spawns agents for user questions and SSE triggers.
- **`rollback_handler.py`**: Safety rollback mechanisms.
- **`synthetic_pipeline.py`**: Generates bootstrapping data.

### memory_writer/ (Top-Level)

- **`__init__.py`**: Exports MemoryWriterAgent.
- **`README.md`**: Durable memory summarization and emission.
- **`agents.py`**: LLM-based summarizers for memory types.
- **`delta_emitter.py`**: Batches deltas to K0.
- **`aggregator.py`**: Dedupes and compresses deltas.

### cache/ (Top-Level)

- **`__init__.py`**: Exports CacheSizeAllocator.
- **`README.md`**: Adaptive KV cache management.
- **`size_allocator.py`**: Dynamic cache sizing.
- **`evictor.py`**: LRU eviction with thermal data.
- **`rewarmer.py`**: Fast reactivation.
- **`thermal_integrator.py`**: Temperature-based adjustments.

### hitl/ (Top-Level)

- **`__init__.py`**: Exports HITL loops.
- **`README.md`**: Bidirectional user feedback.
- **`concierge_loop.py`**: Conversational feedback.
- **`planner_loop.py`**: Planning feedback.
- **`subagents_loop.py`**: Execution feedback.
- **`orchestrator_loop.py`**: Resource feedback.

### connectors/ (Top-Level) (NEW)

- **`__init__.py`**: Exports ConnectorEcosystem.
- **`README.md`**: Local/remote MCP servers, K0 proxy, sandboxing.
- **`local_mcp_servers.py`**: Device-hosted tools and sensors.
- **`remote_mcp_servers.py`**: Company-hosted systems via K0.
- **`k0_proxy.py`**: Authentication, routing, and caching for remote connectors.
- **`sandbox_executor.py`**: Secure execution with isolation and rate limiting.

### sse/ (Top-Level) (NEW)

- **`__init__.py`**: Exports SSEClient.
- **`README.md`**: Proactive K0 notifications and event handling.
- **`sse_client.py`**: SSE connection management with auth and compression.
- **`sse_event_handler.py`**: Processing SSE events and triggering proactive actions.
- **`proactive_trigger_manager.py`**: Decision gating, cooldowns, and relevance checks.

### retention/ (Top-Level) (NEW)

- **`__init__.py`**: Exports RetentionManager.
- **`README.md`**: Automated deletion, grace periods, and compliance auditing.
- **`retention_policies.py`**: Privacy band-based retention rules (GREEN/AMBER/RED/BLACK).
- **`deletion_manager.py`**: Handles automated and user-requested deletions with recovery.
- **`audit_compliance.py`**: Hard deletes and compliance metrics tracking.

### tracing/ (Top-Level) (NEW)

- **`__init__.py`**: Exports CognitiveTrace.
- **`README.md`**: Causality tracking across K1 fabrics.
- **`cognitive_trace.py`**: Monotonic sequence IDs to prevent forking and ensure traceability.

### coordination/ (Coordination Mechanisms) (NEW)

- **`__init__.py`**: Exports CoordinationMechanisms.
- **`sessionstate_concurrency/`**: SessionState concurrency patterns (single-writer/multi-reader, 6 sections).
- **`observability/`**: Metrics aggregation and health checks.
- **`llm_model_hub/`**: Centralized LLM API access with load balancing.

### fabric/ (L2.5) (NEW)

- **`__init__.py`**: Exports CapabilityFabric.
- **`README.md`**: Dynamic capability invocation and resolution.
- **`core/`**: Core fabric components (registry, resolver, context builder).
- **`providers/`**: Provider implementations for agents, tools, workflows.
- **`contracts/`**: Contract definitions and versioning.
- **`policy/`**: Policy engines for routing and security.
- **`module_registry/`**: Contract loading and caching.
- **`provider_resolution/`**: Matching and instantiation logic.
- **`capability_types/`**: Registry of capability types.

### config/

- **`__init__.py`**: Exports settings.
- **`settings.py`**: Pydantic config with env vars and files. ADRs: ADR-0080 (continuous config hot-reload)

### scripts/

- **`sync_architecture.py`**: Tool to run governance sync (GATE 0/5).
- **`migrate_sessionstate.py`**: Scripts for tier migrations.
- **`benchmark_inference.py`**: Latency benchmarking.

### docs/

- **`diagrams/`**: Mermaid diagrams (e.g., architecture skeleton).
- **`adrs/`**: Links to ADR documents.
- **`runbooks/`**: Operational guides for setup, troubleshooting, and tuning.

## Implementation Notes

- **Governance**: Follow 5-Gate workflow; run sync before/after changes.
- **Testing**: Integration tests in repo-level `tests/` (not here).
- **Dependencies**: Use pinned versions; update `pyproject.toml`.
- **Security**: Enforce capability boundaries, redact logs.
- **Performance**: WFQ scheduling, bounded latency, thermal hysteresis.
