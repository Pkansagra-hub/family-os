# Chat Experience PoC Mailbox Rewire Plan

Plan organized into three execution batches to mitigate context bottlenecks and keep dependencies manageable. Each milestone lists epics and issues with target files and ordered steps. No coding should begin until preceding issues in the same batch close.

## Milestone 1 (Batch 1): Infrastructure Foundations

### Epic 1.1: Coordinator & Core Singletons

#### Issue 1.1.1: Consolidate shared infrastructure in `poc/chat_experience_poc/system_coordinator.py`

- Steps:
  1. Map current coordinator responsibilities and identify direct Concierge usage, ad-hoc singletons, and undefined health coverage.
  2. Refactor initialization sequence to construct and retain instances for `MailboxManager`, `SessionStateManager`, `AgentFabric`, `PlannerAgent`, `Orchestrator`, `DAGExecutor`, `BackgroundServicesManager`, and MCP/K0 mock clients.
  3. Expose accessor methods or properties for consumers to retrieve these instances instead of reconstructing them.
  4. Update coordinator bootstrap to pass the same `MailboxManager` into all downstream components (Intent Router, agents, runners).
  5. Extend health check routine to query each singleton for readiness and aggregate into a single status payload.

#### Issue 1.1.2: Share MCP/K0 mocks via coordinator

- Files: `poc/chat_experience_poc/system_coordinator.py`, `mock_services/mock_mcp_server.py`, `mock_services/mock_k0_http.py`
- Steps:
  1. Ensure coordinator spins up mock services once and stores client handles (HTTP session, ports, listener tasks).
  2. Provide getters so planner, DAG executor, tool handler, and writers reuse these handles.
  3. Add teardown logic to stop mocks and close sessions during shutdown.

### Epic 1.2: Agent Fabric & Mailboxes

#### Issue 1.2.1: Implement lifecycle orchestration in `l4_runtime/agent_fabric/fabric.py`

- Steps:
  1. Define `AgentFabric` API for agent registration, mailbox allocation, and lifecycle transitions (PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED) aligned with ADR-0005.
  2. Integrate `MailboxManager` to create per-agent mailboxes and surface mailbox handles to callers.
  3. Track agent metadata (type, tools, prompt source, last activity) for reuse pool decisions.
  4. Publish lifecycle events onto DeltaBus for observability.

#### Issue 1.2.2: Align `AgentBase` and concrete agents with mailbox usage

- Files: `l3_execution/agents/agent_base.py`, `l3_execution/agents/concierge_agent.py`, `l3_execution/agents/specialists/*`, `l2_orchestration/planner/planner_agent.py`, `l5_infrastructure/background_services/memory_writer_agent.py`
- Steps:
  1. Update constructors to accept mailbox references from `AgentFabric` instead of private queues.
  2. Replace direct send/receive logic with mailbox `put`/`get` calls, ensuring cognitive trace IDs propagate.
  3. Modify lifecycle hooks to notify `AgentFabric` when transitioning states.
  4. Ensure DeltaBus subscriptions publish agent task events instead of internal callbacks.

### Epic 1.3: Awaiter Utility Layer

#### Issue 1.3.1: Create awaiter helpers for event synchronization

- Files: `poc/chat_experience_poc/utils/awaiters.py` (new), `l4_runtime/deltabus/deltabus.py`
- Steps:
  1. Design helper coroutines (`await_response`, `await_phase`, `await_writer_receipts`, etc.) built on DeltaBus subscriptions and asyncio Futures.
  2. Implement cancellation, timeout handling, and logging with cognitive trace IDs.
  3. Expose awaiters for reuse across Intent Router, runner scripts, and tests.
  4. Update DeltaBus API if necessary to support scoped subscriptions and once-only listeners.

## Milestone 2 (Batch 2): Interaction Pipeline Rewire

### Epic 2.1: Intent Router Mailbox Path

#### Issue 2.1.1: Rebuild `l1_input/intent_router.py` around mailbox flow

- Steps:
  1. Require a `MailboxManager` and DeltaBus when instantiating the Intent Router.
  2. Generate `cognitive_trace_id`, assemble ingress envelopes, and deliver them through the Concierge mailbox.
  3. Use Batch 1 awaiters to wait on `response.env_*` events for replies; remove direct method invocation and `asyncio.sleep` loops.
  4. Keep CLI commands working by routing them through the same mailbox path and handling administrative responses via DeltaBus.

### Epic 2.2: Concierge & Specialist Delegation

#### Issue 2.2.1: Retrofit `l3_execution/agents/concierge_agent.py`

- Steps:
  1. Consume messages exclusively from the Concierge mailbox supplied by `AgentFabric`.
  2. Publish `agent.task_received`, `agent.task_completed`, and `session.delta` events in response to processing outcomes.
  3. Delegate query intents by requesting specialists through `AgentFactory` and passing mailboxes rather than direct calls.
  4. Remove simulated specialist logic; rely on actual specialist agents and tool calls.

#### Issue 2.2.2: Update specialist agents and factory

- Files: `l3_execution/agents/agent_factory.py`, `l3_execution/agents/specialists/*`
- Steps:
  1. Ensure agent factory requests mailboxes from `AgentFabric` when spawning or reusing agents.
  2. Cache prompts and tool loadouts per agent type; reuse existing agents when within idle TTL.
  3. When executing, rely on mailboxes to deliver tasks and gather results, publishing lifecycle events along the way.

### Epic 2.3: Orchestrator Pipeline Events

#### Issue 2.3.1: Enable mailbox-driven orchestration in `l2_orchestration/orchestrator/orchestrator.py`

- Steps:
  1. Read task requests from the orchestrator mailbox assigned by `AgentFabric`.
  2. Emit `orchestration.negotiation`, `orchestration.selection`, and `orchestration.execution` events to DeltaBus with phase metadata and trace IDs.
  3. Coordinate planner and DAG executor interactions by sending envelopes to their mailboxes and awaiting phase completions.
  4. Build `TaskResult` objects that trigger writer updates and K0 notifications via DeltaBus.

### Epic 2.4: Planner & DAG Executor Integration

#### Issue 2.4.1: Inject mocks and emit plan events in `l2_orchestration/planner/planner_agent.py`

- Steps:
  1. Accept BatchClient/MockCommandPort dependencies from the coordinator during agent initialization.
  2. Commit plans through the mock K0 WAL interface and capture receipts.
  3. Publish `orchestration.plan.committed` with plan metadata and receipt references.
  4. Return responses via the planner mailbox for orchestrator consumption.

#### Issue 2.4.2: Drive execution via `l2_orchestration/executor/dag_executor.py`

- Steps:
  1. Consume committed plans from its mailbox or orchestrator dispatch.
  2. Spawn or reuse agents for each step by leveraging `AgentFabric`.
  3. Publish `agent.task_started`, `tool.called`, `agent.task_completed`, and failure events per step.
  4. Aggregate step outputs and receipts into a final DAG result envelope.

### Epic 2.5: Tool Router Instrumentation

#### Issue 2.5.1: Instrument `l5_infrastructure/tool_call_handler.py`

- Steps:
  1. Guarantee every tool invocation emits a `tool.called` DeltaBus event containing trace ID, tool metadata, and receipt ID.
  2. Validate outgoing payloads against MCP mock schema before dispatching.
  3. Route deterministic responses from the mock to requesting mailboxes, ensuring receipts reach writers.

#### Issue 2.5.2: Harden mock services for deterministic validation

- Files: `mock_services/mock_mcp_server.py`, `mock_services/mock_k0_http.py`
- Steps:
  1. Implement schema validation for incoming tool calls and batches, returning explicit errors on mismatch.
  2. Ensure mock responses include consistent identifiers for downstream assertions.
  3. Add lightweight logging hooks to trace requests without flooding output.

## Milestone 3 (Batch 3): State Propagation, Runner, Health, and Tests

### Epic 3.1: Session State & Writer Pipeline

#### Issue 3.1.1: Normalize session state interactions

- Files: `k1/l2_orchestration/session_state/session_state_manager.py` (or current path), `l3_execution/agents/concierge_agent.py`, `l2_orchestration/orchestrator/orchestrator.py`, `l2_orchestration/planner/planner_agent.py`, `l2_orchestration/executor/dag_executor.py`
- Steps:
  1. Replace manual session mutations with `SessionStateManager` APIs that generate deltas.
  2. Ensure every delta triggers DeltaBus events consumed by writer agents.
  3. Remove any direct scoreboard/control editing, instead publishing changes via designated delta messages.

#### Issue 3.1.2: Verify writer agents consume deltas end-to-end

- Files: `l5_infrastructure/background_services/background_services_manager.py`, `l5_infrastructure/background_services/memory_writer_agent.py`, `l5_infrastructure/background_services/semantic_writer_agent.py`
- Steps:
  1. Confirm background services subscribe to the appropriate DeltaBus topics for episodic and semantic updates.
  2. Batch deltas according to DoD thresholds before sending to the K0 mock.
  3. Record statistics (counts, latency) for later health and test assertions.

### Epic 3.2: Runner & Health Coverage

#### Issue 3.2.1: Overhaul `scripts/run_e2e_paths.py`

- Steps:
  1. Initialize the system through `SystemCoordinator`, retrieving shared singletons.
  2. Drive PATH 1 and PATH 2 inputs through the Intent Router mailbox flow.
  3. Use awaiter utilities to synchronize on responses, orchestration phases, tool calls, and writer receipts.
  4. Assert K0 mock counters and recorded receipts match acceptance criteria without mutating session state directly.

#### Issue 3.2.2: Expand health reporting

- Files: `poc/chat_experience_poc/system_coordinator.py`, `poc/chat_experience_poc/monitoring/health_checks.py`
- Steps:
  1. Extend health checks to interrogate Intent Router, Concierge, Orchestrator, Planner, AgentFabric, SessionStateManager, Writer agents, and mocks.
  2. Surface aggregated health data via coordinator logging and API responses.
  3. Fail startup or mark degraded state when any component reports unhealthy.

### Epic 3.3: Test Reinforcement

#### Issue 3.3.1: Build pytest coverage for rewired flows

- Files: `tests/poc/chat_experience_poc/test_mailbox_routing.py`, `tests/poc/chat_experience_poc/test_orchestration_phases.py`, `tests/poc/chat_experience_poc/test_planner_commit.py`, `tests/poc/chat_experience_poc/test_tool_invocations.py`
- Steps:
  1. Craft integration-focused tests that bootstrap the coordinator, send envelopes through mailboxes, and assert emitted DeltaBus events.
  2. Verify orchestration milestone events, planner commit notifications, and tool-called receipts.
  3. Use awaiter utilities to avoid sleeps and ensure deterministic timing.
  4. Run `python -m pytest tests/poc/chat_experience_poc -k e2e` plus target suites, documenting required fixtures and teardown.

#### Issue 3.3.2: Validate runner output post-refactor

- Files: `scripts/run_e2e_paths.py`, `tests/poc/chat_experience_poc/test_runner_paths.py`
- Steps:
  1. Execute the updated runner as part of tests to confirm PATH 1 and PATH 2 meet latency and event criteria.
  2. Assert K0 mock stats, tool receipts, and response envelopes align with plan expectations.
  3. Capture logs or metrics snapshots for regression detection in future runs.
