# K1 Kernel Sequential Development Plan

## 🎯 Development Philosophy

- **Bottom-Up Build:** Start with Layer 5 (infrastructure), build upward
- **Contract-First:** Define interfaces before implementation
- **Incremental Testing:** Test each module before proceeding
- **Zero Blockers:** Each phase unlocks the next layer

---

## 📋 Phase 1: Foundation Layer (Layer 5 Infrastructure)

**Duration:** Weeks 1-4 | **Why First:** All other layers depend on these services

### Week 1: Core K0 Bridge

**Layer 5 → bridge_k0/ (5 modules)** ✅ **E2E DATA FLOW PROVEN**

1. **bridge_k0/command_client.py** ✅ **COMPLETE**
   - K0 Command Port writes (GREEN/AMBER/RED lanes)
   - **Status**: 147 lines, production-ready
   - **Proven**: Real NaCl Ed25519 signatures, HTTP 200 responses
   - Unlocks: K1→K0 write operations for all layers

2. **bridge_k0/query_client.py** ✅ **COMPLETE**
   - K0 Query Port reads (FTS5, FAISS, KG retrieval)
   - **Status**: 124 lines, production-ready
   - **Proven**: Full memory recall, exact data retrieval
   - Unlocks: Memory recall for all agents

3. **bridge_k0/sse_client.py** 🚧 **IN PROGRESS**
   - K0 SSE Port event subscription
   - Unlocks: Real-time K0 event streaming
   - Dependency: command_client ✅

4. **bridge_k0/batch_client.py** 🚧 **NEXT**
   - SessionState delta batching (250ms intervals)
   - Unlocks: Efficient bulk writes
   - Dependency: command_client ✅

5. **bridge_k0/observability_client.py** 🚧 **NEXT**
   - Metrics/logs push to K0
   - Unlocks: K1 observability
   - Dependency: command_client ✅

**✅ MILESTONE: Full K1 → K0 → K1 data persistence cycle proven (Oct 26, 2025)**

- Test: `tests/k1/l5_infrastructure/bridge_k0/test_real_data_flow.py` (240 lines)
- Results: All 4 stages passing (sign → submit → persist → query)
- Documentation: Complete E2E section added to testing guide
- Performance: All latency budgets met (<150ms round-trip)

### Week 2: Event Bus & Resilience

**Layer 5 → event_bus/ + resilience/**

6. **event_bus/event_bus.py**
   - Layer 1→2 pub/sub messaging
   - Unlocks: Intent routing from L1 to L2
   - Dependency: None (in-memory queue)

7. **event_bus/schemas.py**
   - Event type definitions
   - Unlocks: Type-safe event handling
   - Dependency: event_bus

8. **resilience/circuit_breaker.py**
   - 3-state FSM (CLOSED→OPEN→HALF_OPEN)
   - Unlocks: Fault tolerance for all layers
   - Dependency: None (standalone logic)

9. **resilience/retry_policy.py**
   - Exponential backoff with jitter
   - Unlocks: Resilient K0 calls
   - Dependency: None

10. **resilience/hot_reload.py**
    - Config file watcher
    - Unlocks: Dynamic configuration updates
    - Dependency: None

### Week 3: Thermal & Observability

**Layer 5 → thermal/ + observability/**

11. **thermal/monitor.py**
    - Temperature sensor polling (NPU/GPU/CPU)
    - Unlocks: Thermal-aware placement
    - Dependency: None (system calls)

12. **thermal/placement_planner.py**
    - 4-tier compute placement (NPU→GPU→CPU→Remote)
    - Unlocks: Model Hub placement decisions
    - Dependency: thermal/monitor

13. **observability/metrics.py**
    - Prometheus metric emission
    - Unlocks: Performance monitoring
    - Dependency: None (Prometheus client)

14. **observability/tracing.py**
    - OpenTelemetry span creation
    - Unlocks: Distributed tracing
    - Dependency: None (OTLP client)

15. **observability/logging.py**
    - Structured JSON logging
    - Unlocks: Debugging across layers
    - Dependency: None (structlog)

16. **observability/dashboards.py**
    - Grafana dashboard definitions
    - Unlocks: Visual monitoring
    - Dependency: metrics, tracing

### Week 4: Config & Connectors

**Layer 5 → config/ + connectors/**

17. **config/loader.py**
    - YAML config file loading
    - Unlocks: Global configuration
    - Dependency: None

18. **config/schema_validator.py**
    - JSON schema validation
    - Unlocks: Safe config loading
    - Dependency: loader

19. **config/config_manager.py**
    - Hot reload orchestrator
    - Unlocks: Runtime config updates
    - Dependency: loader, hot_reload

20. **connectors/k0_connector.py**
    - K0 connection lifecycle management
    - Unlocks: HTTP/2 connection pooling
    - Dependency: bridge_k0/command_client

21. **connectors/model_hub_client.py**
    - Internal Model Hub interface (placeholder)
    - Unlocks: L3→L5 communication
    - Dependency: None

---

## 📋 Phase 2: Runtime Core (Layer 4)

**Duration:** Weeks 5-6 | **Why Second:** State management needed before execution layer

### Week 5: SessionState & Actor Fabric Mailbox

**Layer 4 → session_state/ + actor_fabric/mailbox/**

22. **session_state/model.py** ✅ CRITICAL - MUST BUILD FIRST IN L4
    - 6-section FlatBuffers schema (Beliefs, Scoreboard, Control, Persona, Multimodal, Meta)
    - Unlocks: All L3/L4 state operations
    - Dependency: None (FlatBuffers compiler)

23. **session_state/control.py**
    - Locking & delta batching
    - Unlocks: Concurrent state updates
    - Dependency: model

24. **session_state/memory_manager.py**
    - 3-tier eviction (beliefs→multimodal→scoreboard)
    - Unlocks: Memory-constrained devices
    - Dependency: model

25. **actor_fabric/mailbox/mailbox.py**
    - MPSC queue with 4-tier priority
    - Unlocks: Inter-agent messaging
    - Dependency: None (asyncio.Queue)

26. **actor_fabric/mailbox/dead_letter.py**
    - Dead Letter Queue for undeliverable messages
    - Unlocks: Message failure handling
    - Dependency: mailbox

### Week 6: Actor Fabric Router + Supervisor + Learning

**Layer 4 → actor_fabric/ + learning/**

27. **actor_fabric/router/admission.py**
    - 5-check admission control pipeline
    - Unlocks: Secure message routing
    - Dependency: mailbox

28. **actor_fabric/router/routing_table.py**
    - Agent ID → mailbox mapping
    - Unlocks: Message delivery
    - Dependency: admission

29. **actor_fabric/supervisor/health_monitor.py**
    - 1 Hz heartbeat, crash detection
    - Unlocks: Agent reliability
    - Dependency: None

30. **actor_fabric/supervisor/restart_policy.py**
    - Exponential backoff restart logic
    - Unlocks: Automatic recovery
    - Dependency: health_monitor

31. **actor_fabric/supervisor/blacklist.py**
    - 3 crashes/10 min → 1 hr ban
    - Unlocks: Crash loop prevention
    - Dependency: restart_policy

32. **learning/loop.py**
    - Feedback integration, self-model update
    - Unlocks: Adaptive behavior
    - Dependency: session_state/model, bridge_k0/command_client

---

## 📋 Phase 3: Execution Layer - Agents (Layer 3)

**Duration:** Weeks 7-8 | **Why Third:** Agent lifecycle must exist before orchestration

### Week 7: Agent Registry + Hire/Fire + Supervisor

**Layer 3 → agents/**

33. **agents/registry/loader.py** ✅ START HERE FOR L3
    - YAML agent spec loading (58 agent types)
    - Unlocks: Agent definitions
    - Dependency: L5 config/loader

34. **agents/registry/validator.py**
    - JSON schema validation for agent specs
    - Unlocks: Safe agent registration
    - Dependency: loader

35. **agents/hire_fire/state_machine.py**
    - 6-state FSM (PENDING→WARMING→ACTIVE→IDLE→DRAINING→TERMINATED)
    - Unlocks: Agent lifecycle management
    - Dependency: registry/loader, L4 mailbox

36. **agents/hire_fire/pool_manager.py**
    - IDLE pool management (warm starts)
    - Unlocks: 5× faster agent hiring
    - Dependency: state_machine

37. **agents/supervisor/crash_detector.py**
    - Agent crash detection & restart
    - Unlocks: Agent reliability
    - Dependency: L4 supervisor/health_monitor

38. **agents/supervisor/health_tracker.py**
    - Per-agent health metrics
    - Unlocks: Failure rate tracking
    - Dependency: crash_detector

### Week 8: Agent Mailbox + Personality + Active Roster

**Layer 3 → agents/**

39. **agents/mailbox/agent_mailbox.py**
    - Per-agent MPSC queue
    - Unlocks: Agent message delivery
    - Dependency: L4 mailbox

40. **agents/personality/loader.py**
    - Persona trait loading (OCEAN model)
    - Unlocks: Agent personality
    - Dependency: registry/loader

41. **agents/personality/formatter.py**
    - LLM system prompt formatting
    - Unlocks: AI agent behavior
    - Dependency: loader

42. **agents/active_roster/tracker.py**
    - Runtime agent tracking
    - Unlocks: Agent discovery
    - Dependency: hire_fire/state_machine

43. **agents/active_roster/index.py**
    - Fast agent ID → state lookup
    - Unlocks: O(1) agent queries
    - Dependency: tracker

---

## 📋 Phase 4: Execution Layer - Model Hub (Layer 3)

**Duration:** Weeks 9-10 | **Why Fourth:** AI agents need Model Hub for LLM reasoning

### Week 9: Model Hub Core

**Layer 3 → model_hub/**

44. **model_hub/router/router.py** ✅ START HERE FOR MODEL HUB
    - Model request routing (<5ms)
    - Unlocks: LLM call routing
    - Dependency: L5 thermal/placement_planner

45. **model_hub/router/load_balancer.py**
    - Model endpoint load balancing
    - Unlocks: Multi-instance routing
    - Dependency: router

46. **model_hub/placement_planner/planner.py**
    - Thermal-aware model placement
    - Unlocks: Device-appropriate inference
    - Dependency: L5 thermal/placement_planner, router

47. **model_hub/adapters/openai_adapter.py**
    - OpenAI API adapter
    - Unlocks: GPT-4o-mini calls
    - Dependency: router

48. **model_hub/adapters/anthropic_adapter.py**
    - Anthropic API adapter
    - Unlocks: Claude calls
    - Dependency: router

49. **model_hub/adapters/vllm_adapter.py**
    - vLLM local inference adapter
    - Unlocks: On-device LLM
    - Dependency: router

50. **model_hub/adapters/ollama_adapter.py**
    - Ollama local inference adapter
    - Unlocks: Llama/Phi models
    - Dependency: router

### Week 10: Model Hub Advanced Features

**Layer 3 → model_hub/**

51. **model_hub/kv_cache_broker/broker.py**
    - Global KV cache (512MB budget)
    - Unlocks: Cross-agent cache sharing
    - Dependency: router

52. **model_hub/kv_cache_broker/eviction.py**
    - Hybrid LRU+LFU eviction
    - Unlocks: >75% hit rate
    - Dependency: broker

53. **model_hub/prompt_library/loader.py**
    - Jinja2 template loading
    - Unlocks: Prompt templates
    - Dependency: None

54. **model_hub/prompt_library/renderer.py**
    - Template rendering (<5ms)
    - Unlocks: Dynamic prompts
    - Dependency: loader

55. **model_hub/fallback_cascade/cascade.py**
    - Model fallback routing
    - Unlocks: Fault tolerance
    - Dependency: router, L5 circuit_breaker

56. **model_hub/safety_filter/pre_filter.py**
    - Pre-LLM safety check (5ms)
    - Unlocks: Fast content filtering
    - Dependency: None (regex rules)

57. **model_hub/safety_filter/post_filter.py**
    - Post-LLM safety check (50ms)
    - Unlocks: Output validation
    - Dependency: router

---

## 📋 Phase 5: Execution Layer - Tools & Dialogue (Layer 3)

**Duration:** Weeks 11-12 | **Why Fifth:** Tools & dialogue can be built in parallel with agents

### Week 11: Tool Execution

**Layer 3 → tools/**

58. **tools/registry/loader.py** ✅ START HERE FOR TOOLS
    - Tool catalog loading (758 tools: 608 MCP + 150 API)
    - Unlocks: Tool discovery
    - Dependency: L5 config/loader

59. **tools/registry/validator.py**
    - JSON schema validation for tool specs
    - Unlocks: Safe tool registration
    - Dependency: loader

60. **tools/runner/executor.py**
    - Tool execution engine (<3000ms P95)
    - Unlocks: Tool invocation
    - Dependency: registry/loader

61. **tools/runner/timeout.py**
    - Execution timeout enforcement
    - Unlocks: Runaway tool prevention
    - Dependency: executor

62. **tools/sandbox/wasm_sandbox.py**
    - WASM sandbox (<10ms startup)
    - Unlocks: Safe WASM execution
    - Dependency: executor

63. **tools/sandbox/process_sandbox.py**
    - Process sandbox (<100ms startup)
    - Unlocks: Safe native execution
    - Dependency: executor

64. **tools/adapters/mcp_adapter.py**
    - MCP protocol adapter (80% of tools)
    - Unlocks: MCP tool calls
    - Dependency: runner/executor

65. **tools/adapters/rest_adapter.py**
    - REST API adapter (15% of tools)
    - Unlocks: REST tool calls
    - Dependency: runner/executor

66. **tools/control/manager.py**
    - Runtime tool lifecycle management
    - Unlocks: Tool enable/disable
    - Dependency: registry/loader

### Week 12: Dialogue Management

**Layer 3 → dialogue/**

67. **dialogue/scoreboard/qud_stack.py**
    - Question Under Discussion stack
    - Unlocks: Context tracking
    - Dependency: L4 session_state/model

68. **dialogue/scoreboard/entity_tracker.py**
    - Entity salience tracking
    - Unlocks: Reference resolution
    - Dependency: qud_stack

69. **dialogue/state_tracker/belief_tracker.py**
    - User belief tracking
    - Unlocks: Belief updates
    - Dependency: L4 session_state/model

70. **dialogue/state_tracker/slot_filler.py**
    - Slot filling logic
    - Unlocks: Structured dialogue
    - Dependency: belief_tracker

71. **dialogue/turn_manager/turn_taker.py**
    - Turn-taking logic
    - Unlocks: Dialogue flow
    - Dependency: None

72. **dialogue/turn_manager/barge_in.py**
    - Barge-in handling (<120ms cancel)
    - Unlocks: Interruption support
    - Dependency: turn_taker

73. **dialogue/repair/repair_detector.py**
    - Conversation repair detection
    - Unlocks: Error recovery
    - Dependency: state_tracker

74. **dialogue/repair/repair_strategy.py**
    - Repair strategy selection
    - Unlocks: Clarification generation
    - Dependency: repair_detector

---

## 📋 Phase 6: Execution Layer - AI Agents (Layer 3)

**Duration:** Week 13 | **Why Sixth:** AI agents need Model Hub + agents infrastructure

### Week 13: AI Agent Implementations

**Layer 3 → agents/**

75. **agents/concierge/nlu.py** ✅ FIRST AI AGENT
    - Intent classification (50ms budget)
    - Unlocks: Intent routing
    - Dependency: model_hub/router, agents/hire_fire

76. **agents/concierge/entity_extraction.py**
    - Named entity recognition
    - Unlocks: Slot filling
    - Dependency: nlu

77. **agents/researcher/retrieval.py**
    - Knowledge synthesis (3000ms budget)
    - Unlocks: Research tasks
    - Dependency: model_hub/router, bridge_k0/query_client

78. **agents/researcher/synthesis.py**
    - Multi-source information fusion
    - Unlocks: Complex research
    - Dependency: retrieval

---

## 📋 Phase 7: Orchestration Layer (Layer 2)

**Duration:** Weeks 14-16 | **Why Seventh:** Needs L3 agents + L4 state + L5 infrastructure

### Week 14: Planner (4-Stage Pipeline)

**Layer 2 → planner/**

79. **planner/sketch/llm_planner.py** ✅ START HERE FOR L2
    - LLM plan generation (500ms budget)
    - Unlocks: AI-driven planning
    - Dependency: L3 model_hub/router

80. **planner/sketch/json_validator.py**
    - Plan JSON schema validation
    - Unlocks: Safe plan parsing
    - Dependency: llm_planner

81. **planner/expand/metadata_enricher.py**
    - Tool registry lookup (1ms budget)
    - Unlocks: Plan enrichment
    - Dependency: L3 tools/registry

82. **planner/expand/dependency_resolver.py**
    - Tool dependency resolution
    - Unlocks: Valid DAGs
    - Dependency: metadata_enricher

83. **planner/validate/rule_validator.py**
    - 6-rule validation checks (1ms budget)
    - Unlocks: Plan correctness
    - Dependency: expand/dependency_resolver

84. **planner/validate/llm_arbiter.py**
    - LLM validation arbiter (<15% invocation)
    - Unlocks: Complex validation
    - Dependency: L3 model_hub/router, rule_validator

85. **planner/commit/wal_writer.py**
    - K0 WAL write (10ms budget)
    - Unlocks: Plan persistence
    - Dependency: L5 bridge_k0/command_client

86. **planner/commit/state_locker.py**
    - SessionState locking during commit
    - Unlocks: Concurrent plan prevention
    - Dependency: L4 session_state/control

### Week 15: Orchestrator (3-Phase Coordination)

**Layer 2 → orchestrator/**

87. **orchestrator/negotiation/contract_net.py** ✅ START HERE FOR ORCHESTRATOR
    - Contract Net Protocol (50ms budget)
    - Unlocks: Agent bidding
    - Dependency: L3 agents/active_roster

88. **orchestrator/negotiation/bidding.py**
    - Agent bid collection & evaluation
    - Unlocks: Multi-agent coordination
    - Dependency: contract_net

89. **orchestrator/selection/madm_scorer.py**
    - MADM 6-factor scoring (5ms budget)
    - Unlocks: Agent selection
    - Dependency: negotiation/bidding

90. **orchestrator/selection/ranker.py**
    - Agent ranking & selection
    - Unlocks: Best agent choice
    - Dependency: madm_scorer

91. **orchestrator/execution/dag_executor.py**
    - DAG parallel execution
    - Unlocks: Parallel task execution
    - Dependency: selection/ranker, L3 agents/mailbox

92. **orchestrator/execution/barrier_sync.py**
    - Barrier synchronization for parallel tasks
    - Unlocks: DAG completion detection
    - Dependency: dag_executor

93. **orchestrator/saga/saga_coordinator.py**
    - Saga Pattern (LIFO compensation)
    - Unlocks: Rollback on failure
    - Dependency: execution/dag_executor

94. **orchestrator/saga/compensation.py**
    - Compensation action execution
    - Unlocks: Transactional orchestration
    - Dependency: saga_coordinator

### Week 16: Protocol Monitor

**Layer 2 → protocol_monitor/**

95. **protocol_monitor/fsm_compiler.py**
    - PDL → FSM compilation
    - Unlocks: Protocol validation
    - Dependency: None

96. **protocol_monitor/validator.py**
    - MPST protocol validation (2ms budget)
    - Unlocks: Protocol safety
    - Dependency: fsm_compiler

97. **protocol_monitor/timeout_enforcer.py**
    - Timeout enforcement for protocols
    - Unlocks: Progress guarantees
    - Dependency: validator

98. **protocol_monitor/security.py**
    - 2-phase validation (role + protocol)
    - Unlocks: Security enforcement
    - Dependency: validator

---

## 📋 Phase 8: Input Processing Layer (Layer 1)

**Duration:** Weeks 17-18 | **Why Last:** Needs L2 orchestration + L5 event bus

### Week 17: Input Streams

**Layer 1 → streams/**

99. **streams/stream_switch/multi_modal.py** ✅ START HERE FOR L1
    - Multi-modal input bus (audio, text, vision)
    - Unlocks: Input normalization
    - Dependency: L5 event_bus

100. **streams/stream_switch/serializer.py**
     - FlatBuffers serialization (<1ms)
     - Unlocks: Zero-copy messaging
     - Dependency: multi_modal

101. **streams/operators/vad.py**
     - Voice Activity Detection (20ms budget)
     - Unlocks: Audio processing
     - Dependency: stream_switch

102. **streams/operators/asr.py**
     - Automatic Speech Recognition (80ms budget)
     - Unlocks: Speech-to-text
     - Dependency: vad

103. **streams/operators/tts.py**
     - Text-to-Speech (300ms TTFT)
     - Unlocks: Voice output
     - Dependency: None

### Week 18: Intent Routing & Meta Policy

**Layer 1 → orchestration/**

104. **orchestration/intent_router/t1_rules.py**
     - T1 Rule-Based routing (10ms budget, 70% coverage)
     - Unlocks: Fast intent classification
     - Dependency: streams/stream_switch

105. **orchestration/intent_router/t2_slm.py**
     - T2 SLM classification (3ms budget, 20% coverage)
     - Unlocks: On-device ML classification
     - Dependency: t1_rules, L3 model_hub/router

106. **orchestration/intent_router/t3_llm.py**
     - T3 LLM fallback (40ms budget, 10% coverage)
     - Unlocks: Complex intent handling
     - Dependency: t2_slm, L3 model_hub/router

107. **meta_policy/proactivity.py**
     - Proactive suggestion engine (5ms budget)
     - Unlocks: Context-aware suggestions
     - Dependency: L4 session_state/model

108. **meta_policy/clarification.py**
     - Clarification detection (5ms budget)
     - Unlocks: Ambiguity handling
     - Dependency: orchestration/intent_router

---

## 🎯 Critical Path Summary

### Must Build in This Order

1. **L5 bridge_k0/command_client** → All K0 writes depend on this
2. **L5 event_bus** → L1→L2 communication depends on this
3. **L4 session_state/model** → All state operations depend on this
4. **L4 mailbox** → All inter-agent messaging depends on this
5. **L3 agents/registry** → All agent operations depend on this
6. **L3 agents/hire_fire** → Agent lifecycle must exist before orchestration
7. **L3 model_hub/router** → All AI agents depend on this
8. **L2 planner** → Orchestrator needs plans
9. **L2 orchestrator** → Layer 1 needs coordination
10. **L1 stream_switch** → Entry point for all user input

### Parallel Opportunities

- **Week 2-3:** Event bus + resilience + thermal (no dependencies)
- **Week 9-10:** Model Hub adapters (all depend on router, can build in parallel)
- **Week 11-12:** Tools + dialogue (independent modules)

### Testing Strategy Per Phase

- **After Each Week:** Unit tests for that week's modules
- **After Each Phase:** Integration tests for that layer
- **After All Phases:** End-to-end hot path test (L1→L2→L3→L4→L5→K0)

---

## 📊 Module Count Summary

| Phase | Layer | Modules | Weeks | Dependencies |
|-------|-------|---------|-------|--------------|
| 1 | L5 Infrastructure | 21 modules | 1-4 | None (foundation) |
| 2 | L4 Runtime Core | 11 modules | 5-6 | L5 complete |
| 3 | L3 Agents | 11 modules | 7-8 | L4 complete |
| 4 | L3 Model Hub | 14 modules | 9-10 | L5 thermal, L3 agents |
| 5 | L3 Tools + Dialogue | 18 modules | 11-12 | L4 state, L3 agents |
| 6 | L3 AI Agents | 4 modules | 13 | L3 Model Hub |
| 7 | L2 Orchestration | 20 modules | 14-16 | L3 complete |
| 8 | L1 Input | 10 modules | 17-18 | L2 complete, L5 event bus |
| **TOTAL** | **5 layers** | **109 modules** | **18 weeks** | **Sequential build** |
