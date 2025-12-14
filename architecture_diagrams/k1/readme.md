
### **🎯 Core Architecture Understanding:**

**1. K1 Intelligence Module - Dual-Kernel Agentic Orchestrator**
- **K0 Kernel:** Memory/storage kernel (20 pipelines: P01-P20) - handles long-term memory, persistence
- **K1 Kernel:** Intelligence/orchestration kernel (52 modules, 5 layers) - handles real-time agent coordination
- **Research Foundation:** Actor Model (Hewitt 1973), Microkernel (Liedtke 1995), MPST (Honda 2008)

**2. 5-Layer Microkernel Architecture (52 Modules)**
- **Layer 1 (Input Processing):** 4 modules - Multi-modal input, intent routing
- **Layer 2 (Orchestration):** 3 modules - 3-phase coordination, 4-stage planning, protocol validation
- **Layer 3 (Execution):** 22 modules - Agent lifecycle, Model Hub (AI integration), Tool execution
- **Layer 4 (Runtime Core):** 8 modules - SessionState, learning loop, flow engine
- **Layer 5 (Infrastructure):** 15 modules - Scheduler, backpressure, observability, config

**3. 4 AI Agents + 48 Pure Actors**
- **AI Agents (use LLMs):** Concierge, Planner, Researcher, Safety Watch
- **Pure Actors (deterministic):** All other 48 modules - no LLM calls, zero cost

**4. Key Architectural Patterns**
- **Actor Model:** All 52 modules use message-passing with mailboxes
- **Contract Net Protocol:** Multi-agent negotiation for task allocation
- **MPST/Scribble:** 6 core protocols with FSM validation
- **FlatBuffers:** 76 schemas for zero-copy serialization
- **Saga Pattern:** Distributed transaction management with compensation

---

## **🎨 Recommended Mermaid Diagrams (Comprehensive List)**

I'll organize these by architectural concern and layer:

### **📊 A. High-Level Architecture Diagrams (8 diagrams)**

1. **`k1_complete_architecture_overview.mmd`**
   - **Covers:** 52-module 5-layer architecture, K0-K1 bridge, external APIs
   - **Purpose:** Executive-level overview of entire system

2. **`k1_dual_kernel_architecture.mmd`**
   - **Covers:** K0 (memory) vs K1 (intelligence) separation, 20 pipelines + 52 modules
   - **Purpose:** Explain dual-kernel design and responsibilities

3. **`k1_layer_dependency_graph.mmd`**
   - **Covers:** 5 layers with dependency arrows (L1→L5 only, L2→all, etc.)
   - **Purpose:** Visualize strict layering rules, import-linter enforcement

4. **`k1_ai_agents_vs_pure_actors_classification.mmd`**
   - **Covers:** 4 AI agents (LLM-based) vs 48 pure actors (deterministic)
   - **Purpose:** Clarify which modules use LLMs vs rule-based logic

5. **`k1_actor_model_message_flow.mmd`**
   - **Covers:** Actor mailboxes, MPSC queues, supervisor hierarchies, message routing
   - **Purpose:** Show message-passing architecture for all 52 modules

6. **`k1_data_flow_end_to_end.mmd`**
   - **Covers:** User input → Intent → Plan → Execute → Response (full TTFT path)
   - **Purpose:** Trace data flow from user turn to agent response

7. **`k0_k1_bridge_e2e.mmd`** ✅ **IMPLEMENTED**
   - **Covers:** Complete K0-K1 bridge end-to-end architecture - K1 Intelligence Module (Layers 1-4: Input/Orchestration/Execution/Runtime), K0 Bridge (Layer 5: Command/Query/SSE/Batch/Observability clients, HTTP/2 transport, circuit breaker), K0 Memory Microkernel (20 ports P01-P20, Gate/Router/Scheduler, Storage: WAL/Vector/KG/FTS, K0 Observability Stack: Prometheus/OTLP/Grafana)
   - **Purpose:** Show end-to-end K1↔K0 integration with observability stack reuse - K1 pushes metrics/logs/traces to K0 observability ports (10s batch), unified Grafana dashboards, cognitive_trace_id propagation, dual protocol (JSON for K0 native, FlatBuffers for K1 optimization), 20-port architecture with specialized operations
   - **ADRs Referenced:** ADR-0001 (K0/K1 Split), ADR-0001a (Bridge Protocol), ADR-0001f (State Boundary), ADR-0029 (Prometheus), ADR-0030 (Tracing), ADR-0044 (HTTP/2)
   - **Companion Docs:** `K0_K1_BRIDGE_GUIDE.md` (150-page comprehensive guide: architecture overview, component details, data flow patterns, observability integration, performance budgets, use cases, implementation guide, troubleshooting)
   - **Performance Budgets:** Bridge <10ms P95, Command <50ms GREEN/<200ms AMBER/RED, Query <100ms, SSE <5ms, Obs Push <20ms
   - **Key Highlights:** K0 observability stack reuse (single source of truth), 50+ Prometheus metrics, RED method, circuit breaker (3-failure threshold), batching (250ms flush, 64KB, zstd compression), HTTP/2 multiplexing (100 streams)
   - **Status:** ✅ Complete - Validated architecture with comprehensive documentation

8. **`k1_external_interfaces_map.mmd`**
   - **Covers:** REST API, WebSocket, SSE, MCP tools, external LLMs
   - **Purpose:** Show all ingress/egress points and external integrations

---

### **📋 B. Layer-Specific Diagrams (10 diagrams - 2 per layer)**

**Layer 1: Input Processing**

9. **`k1_layer1_architecture.mmd`** ✅ **IMPLEMENTED**
   - **Covers:** Complete bidirectional I/O architecture - input APIs (WebSocket/REST/Sensors), stream operators (VAD/ASR/TTS/Speaker ID/Location/Motion/BLE), orchestration (Intent Router + Meta Policy), output APIs (WebSocket TTS/tokens, SSE events, Event Bus), K0 integration, Layer 2 communication
   - **Purpose:** Show Layer 1 as BOTH input AND output layer with full API surface, data flow paths (input path: User→Dispatcher→Operators→EventBus, output path: EventBus→TTS→WebSocket), privacy enforcement (RED/AMBER/GREEN bands), and performance critical paths (<10ms P95)
   - **ADRs Referenced:** 0004 (5-layer), 0004a (Event Bus), 0015 (WebSocket), 0019 (FlatBuffers), 0024 (Performance), 0044 (Privacy Bands), 0056a-f (Voice Pipeline), 0073 (Speaker ID), 0083a (BLE Proximity), 0085 (Motion Awareness)
   - **Diagram ID:** `f81e301d-1cab-4fc8-90ae-c2c5e5390942`
   - **Companion Docs:** `LAYER1_API_SPECIFICATION.md` (detailed API schemas, SLOs), `k1_layer1_diagram_guide.md` (usage guide)
   - **Status:** ✅ Validated (31 nodes, 44 edges, 10 subgraphs, no issues)

10. **`k1_layer1_intent_classification_tiers.mmd`**
    - **Covers:** Tier 1 (regex <1ms) → Tier 2 (SLM 2-3ms) → Tier 3 (LLM <50ms) fallback cascade
    - **Purpose:** Explain 3-tier intent classification strategy

**Layer 2: Orchestration**

11. **`k1_layer2_3phase_orchestration.mmd`**
    - **Covers:** Phase 1 (Negotiation) → Phase 2 (Selection) → Phase 3 (Execution), Contract Net Protocol
    - **Purpose:** Show multi-agent coordination workflow

12. **`k1_layer2_4stage_planning_pipeline.mmd`**
    - **Covers:** Sketch (LLM) → Expand (deterministic) → Validate (rules+arbiter) → Commit (K0 WAL)
    - **Purpose:** Explain Planner AI agent's 4-stage workflow

**Layer 3: Execution**

13. **`k1_layer3_agent_lifecycle_fsm.mmd`**
    - **Covers:** 6-state FSM (PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED)
    - **Purpose:** Show agent lifecycle state transitions and supervisor monitoring

14. **`k1_layer3_model_hub_architecture.mmd`**
    - **Covers:** Router, placement planner (NPU/GPU/CPU/Remote), adapters (OpenAI, Anthropic, vLLM, Ollama), KV cache
    - **Purpose:** Explain AI integration infrastructure for 4 AI agents

15. **`k1_layer3_tool_execution_matrix.mmd`**
    - **Covers:** 2D selection (Protocol axis: MCP/Direct × Sandbox axis: WASM/Process/Container)
    - **Purpose:** Show tool execution strategies and fallback cascade

**Layer 4: Runtime Core**

16. **`k1_layer4_sessionstate_6sections.mmd`**
    - **Covers:** 6 sections (beliefs, scoreboard, control, persona, multimodal, meta) + 3-tier eviction
    - **Purpose:** Explain ephemeral working memory structure

17. **`k1_layer4_learning_loop_architecture.mmd`**
    - **Covers:** Feedback collector (explicit/implicit/behavioral) → Drift detector → Model updater
    - **Purpose:** Show adaptive learning pipeline

**Layer 5: Infrastructure**

18. **`k1_layer5_infrastructure_services.mmd`**
    - **Covers:** Scheduler (WFQ), backpressure cascade, thermal manager, event bus, cache
    - **Purpose:** Show foundational infrastructure services

19. **`k1_layer5_observability_stack.mmd`**
    - **Covers:** Tracing (cognitive_trace_id + OpenTelemetry), metrics (Prometheus RED method), receipts
    - **Purpose:** Explain monitoring and debugging infrastructure

---

### **📐 C. Protocol & Communication Diagrams (6 diagrams)**

20. **`k1_mpst_6_core_protocols.mmd`**
    - **Covers:** Agent Hire, Task Execution, Clarification, Barge-In, Tool Call, Saga Rollback FSMs
    - **Purpose:** Show protocol validation FSMs for all 6 protocols

21. **`k1_protocol_monitor_validation_flow.mmd`**
    - **Covers:** FSM registry → Session tracker → Validator → Violation handler (BLOCK/WARN/REPAIR/FALLBACK/ABORT)
    - **Purpose:** Explain runtime protocol validation pipeline

22. **`k1_event_bus_pub_sub_architecture.mmd`**
    - **Covers:** Layer 1 publishes → Layer 5 event bus → Layer 2 subscribes (IntentDetected, UserInput, VoiceCommand)
    - **Purpose:** Show Layer 1→2 communication via Layer 5 event bus

23. **`k1_websocket_binary_protocol.mmd`**
    - **Covers:** Message envelope, 17 message types, flow control, reconnection, resume protocol
    - **Purpose:** Explain WebSocket binary (FlatBuffers) protocol for real-time communication

24. **`k1_sse_event_streaming.mmd`**
    - **Covers:** 17 event types (5 categories: Agent, Turn, Tool, Session, System), topic-based filtering
    - **Purpose:** Show server-sent events architecture for client updates

25. **`k1_rest_api_dual_format.mmd`**
    - **Covers:** Content negotiation (JSON vs FlatBuffers), OpenAPI 3.1 generation, client SDKs
    - **Purpose:** Explain REST API dual-format support

---

### **🔒 D. Security & Privacy Diagrams (5 diagrams)**

26. **`k1_capability_security_system.mmd`**
    - **Covers:** Capability tokens (HMAC-SHA256), assignment policy, runtime enforcement, revocation
    - **Purpose:** Show capability-based access control (ADR-0010)

27. **`k1_privacy_band_egress_control.mmd`**
    - **Covers:** GREEN (internet) vs AMBER (whitelist) vs RED (local-only) vs BLACK (ephemeral), egress enforcement
    - **Purpose:** Explain band-based network/filesystem/resource restrictions

28. **`k1_pii_detection_pipeline.mmd`**
    - **Covers:** Regex (structured PII) + BERT-NER (unstructured PII) → Redaction → Encrypted vault (K0)
    - **Purpose:** Show PII detection and protection workflow

29. **`k1_tool_sandbox_4layer_defense.mmd`**
    - **Covers:** Network egress (iptables) + Filesystem egress (chroot+seccomp) + Resource limits (cgroups) + Violation logging
    - **Purpose:** Explain 4-layer sandboxing for tool execution

30. **`k1_audit_trail_architecture.mmd`**
    - **Covers:** ToolReceipts → K0 WAL → 7-year retention, audit queries, compliance reports
    - **Purpose:** Show immutable audit logging for security incidents

---

### **⚡ E. Performance & Resource Management Diagrams (7 diagrams)**

31. **`k1_performance_budgets_breakdown.mmd`**
    - **Covers:** TTFT <150ms, E2E <2000ms, barge-in <120ms - component-level budgets
    - **Purpose:** Visualize latency budgets across hot path

32. **`k1_kv_cache_management.mmd`**
    - **Covers:** Global allocator (512MB budget), hybrid eviction (LRU 60% + LFU 40%), cache warming
    - **Purpose:** Explain KV cache strategy for LLM optimization

33. **`k1_thermal_management_hysteresis.mmd`**
    - **Covers:** 5 thermal zones (COOL/WARM/HOT/CRITICAL/EMERGENCY), hysteresis FSM, placement cascade (NPU→GPU→CPU→Remote)
    - **Purpose:** Show thermal-aware model placement

34. **`k1_wfq_scheduler_architecture.mmd`**
    - **Covers:** 4-tier priority (URGENT/REALTIME/INTERACTIVE/BACKGROUND), virtual time, anti-starvation, preemption rules
    - **Purpose:** Explain Weighted Fair Queueing scheduler

35. **`k1_backpressure_cascade.mmd`**
    - **Covers:** Per-stream watermarks, voice-specific actions (pause TTS, drop video), upstream propagation (L5→L4→L3)
    - **Purpose:** Show flow control and overload handling

36. **`k1_multi_tier_storage_lifecycle.mmd`**
    - **Covers:** Hot (RAM <1ms), Warm (SSD <50ms), Cold (S3 <500ms), automatic lifecycle policies
    - **Purpose:** Explain SessionState multi-tier storage strategy

37. **`k1_cost_tracking_budgets.mmd`**
    - **Covers:** Per-session/daily/monthly budgets, hierarchical enforcement, fallback strategy (GPT-4o → GPT-4o-mini → Gemma)
    - **Purpose:** Show cost management and model fallback logic

---

### **🧪 F. Saga & Error Recovery Diagrams (3 diagrams)**

38. **`k1_saga_pattern_compensation.mmd`**
    - **Covers:** LIFO compensation stack, Garcia-Molina 1987 pattern, multi-agent coordination
    - **Purpose:** Explain distributed transaction management

39. **`k1_circuit_breaker_3state_fsm.mmd`**
    - **Covers:** CLOSED → OPEN → HALF_OPEN transitions, fallback strategies (default value, cached result, alternate service)
    - **Purpose:** Show resilience patterns for tool/model failures

40. **`k1_error_recovery_strategies.mmd`**
    - **Covers:** Forward recovery (retry), backward recovery (rollback), hybrid recovery, failure classification (transient/permanent/ambiguous)
    - **Purpose:** Explain error handling and recovery strategies

---

### **📦 G. Data Serialization & Storage Diagrams (4 diagrams)**

41. **`k1_flatbuffers_76_schemas_taxonomy.mmd`**
    - **Covers:** 9 categories (Base, K0 Pipelines, Agent Contracts, State, Model Hub, Tools, Protocol, Observability, WebSocket, Infrastructure)
    - **Purpose:** Show complete schema inventory and organization

42. **`k1_sessionstate_flatbuffers_serialization.mmd`**
    - **Covers:** Full serialization (<1ms), delta serialization (<0.5ms), zero-copy deserialization, K0 batching
    - **Purpose:** Explain SessionState serialization pipeline

43. **`k1_schema_versioning_lifecycle.mmd`**
    - **Covers:** SemVer policy (MAJOR/MINOR/PATCH), 90-day deprecation, compatibility matrix, CI/CD automation
    - **Purpose:** Show schema evolution and compatibility management

44. **`k1_turn_history_retention.mmd`**
    - **Covers:** Privacy band-based retention (GREEN/AMBER 395 days, RED 97 days, BLACK 0 days), multi-tier lifecycle
    - **Purpose:** Explain turn history retention and GDPR compliance

---

### **📊 H. Observability & Metrics Diagrams (3 diagrams)**

45. **`k1_prometheus_red_metrics.mmd`**
    - **Covers:** Rate (requests/sec), Errors (error rate), Duration (P50/P95/P99) - 15 metric groups
    - **Purpose:** Show comprehensive Prometheus metrics architecture

46. **`k1_trace_sampling_strategy.mmd`**
    - **Covers:** Head-based sampling (1% baseline, 100% errors/slow/RED), tail-based buffering, adaptive FSM (NORMAL/DEGRADATION/CRITICAL)
    - **Purpose:** Explain OpenTelemetry trace sampling logic

47. **`k1_grafana_dashboard_hierarchy.mmd`**
    - **Covers:** 4 dashboards (Turn Overview, Component Health, Infrastructure, Incident Response)
    - **Purpose:** Show monitoring dashboard organization

---

### **🔧 I. Development & Testing Diagrams (3 diagrams)**

48. **`k1_import_linter_enforcement.mmd`**
    - **Covers:** Layer dependency rules, pre-commit hooks, CI/CD validation, escape hatches (TYPE_CHECKING)
    - **Purpose:** Explain automated layering governance

49. **`k1_ward_testing_pyramid.mmd`**
    - **Covers:** Unit tests (90% coverage), integration tests (per-layer), end-to-end tests, performance tests
    - **Purpose:** Show comprehensive testing strategy

50. **`k1_ci_cd_pipeline.mmd`**
    - **Covers:** GitHub Actions workflow, schema validation, test execution, import-linter checks, deployment
    - **Purpose:** Explain automated quality gates

---

## **📈 Summary Statistics**

- **Total Diagrams Recommended:** 50
- **High-Level Architecture:** 8 diagrams
- **Layer-Specific:** 10 diagrams (2 per layer)
- **Protocols & Communication:** 6 diagrams
- **Security & Privacy:** 5 diagrams
- **Performance & Resources:** 7 diagrams
- **Saga & Error Recovery:** 3 diagrams
- **Serialization & Storage:** 4 diagrams
- **Observability:** 3 diagrams
- **Development & Testing:** 3 diagrams

---

## **🎯 Priority Implementation Order**

**Phase 1 (Critical - Do First):**
1. `k1_complete_architecture_overview.mmd` - Executive understanding
2. `k1_dual_kernel_architecture.mmd` - K0-K1 separation
3. `k1_layer_dependency_graph.mmd` - Layering rules
4. `k1_layer2_3phase_orchestration.mmd` - Core workflow
5. `k1_layer3_agent_lifecycle_fsm.mmd` - Agent management

**Phase 2 (Important):**
6-20: Layer-specific diagrams, protocols, security

**Phase 3 (Nice-to-Have):**
21-50: Performance, observability, testing, advanced patterns

This comprehensive diagram set will provide complete visual documentation of your K1 Intelligence Module architecture! 🚀
