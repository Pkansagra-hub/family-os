## Gap Analysis Summary

**Generated:** 2025-01-29
**Updated:** 2025-11-03 (Added Tool & API Integration gaps from System 41)
**Source:** whiteboard_chatexp.md (4826 lines) vs adr_family_map.md (300+ ADRs)
**Purpose:** Identify architectural topics from whiteboard requiring new ADRs

---

## Gap Analysis Summary

**Total Topics Analyzed:** 64 (was 62, +2 proactive behavior gaps)
**Covered by Existing ADRs:** 18 (partial or complete)
**New ADRs Required:** 49 (was 47, +2 proactive behavior gaps)
**Priority Breakdown:**

- **CRITICAL (Production-blocking):** 13 ADRs (was 11, +2 proactive gaps)
- **HIGH (Essential features):** 17 ADRs
- **MEDIUM (Important enhancements):** 12 ADRs
- **LOW (Documentation completeness):** 6 ADRs

---

## Comprehensive Topic Comparison Table

| # | Topic Name | Category | Description | Whiteboard Section | Existing ADR | Coverage | New ADR Needed | Priority |
|---|------------|----------|-------------|-------------------|--------------|----------|----------------|----------|
| **TIER ARCHITECTURE & COORDINATION** |
| 1 | ConciergeAgent Pattern | Architectural Pattern | Master coordinator, single entry point for all user messages, 11 meta-intents, comprehensive LLM system prompt | Three-Tier Hierarchy | None | 0% | **YES** | **CRITICAL** |
| 2 | Three-Tier Agent Hierarchy | Architectural Pattern | Tier 1: ConciergeAgent (coordinator), Tier 2: Specialists (domain experts), Tier 3: Writers (background bookkeepers) | Three-Tier Hierarchy | Partial (ADR-0086 covers dynamic creation) | 30% | **YES** | **CRITICAL** |
| 3 | Specialist Agents | Component | HealthcareAgent, FinanceAgent, SocialCoordinator, PlannerAgent, RoutineAgent, EmergencyAgent | Three-Tier Hierarchy | ADR-0086 (Dynamic Creation) | 40% | **YES** (Extensions) | **HIGH** |
| 4 | Writer Agents Pattern | Architectural Pattern | MemoryWriterAgent, LearningExtractor, SemanticEnricher - Background bookkeeping tier, always active, non-blocking | Three-Tier Hierarchy | None | 0% | **YES** | **CRITICAL** |
| 5 | Two-Phase Memory Formation | Protocol | Phase 1: Immediate raw capture (T0+1ms), Phase 2: Post-response enrichment (T0+500ms), non-blocking | Writer Agents | Partial (P02 pipeline exists) | 50% | **YES** (Protocol) | **HIGH** |
| **META-INTENTS & CONVERSATIONAL HANDLING** |
| 6 | Meta-Intent Classification | System | 11 types: ACKNOWLEDGMENT, STATUS_CHECK, CANCELLATION, RETRY, CORRECTION, RAPID_BATCH, AMENDMENT, REFINEMENT, TOPIC_CHANGE, AMBIGUOUS_QUERY, SMALL_TALK | ConciergeAgent System Prompt | None | 0% | **YES** | **CRITICAL** |
| 7 | Acknowledgment Handling | Protocol | Detect "ok", "thanks", "got it" - Update SessionState, brief response, no orchestration | Meta-Intents | None | 0% | **YES** (Part of Meta-Intent ADR) | **HIGH** |
| 8 | Status Check Handling | Protocol | Detect "are you there?", "still working?" - Return progress from active_tasks, don't cancel | Meta-Intents | None | 0% | **YES** (Part of Meta-Intent ADR) | **HIGH** |
| 9 | Cancellation Protocol | Protocol | Detect "never mind", "stop", "cancel" - Send CANCEL_TASK with save_partial=True | Meta-Intents | None | 0% | **YES** (Part of Meta-Intent ADR) | **HIGH** |
| 10 | Retry Protocol | Protocol | Detect "try again", "retry" - Send RETRY_TASK with fallback_strategy, reference last_failed_task | Meta-Intents | None | 0% | **YES** (Part of Meta-Intent ADR) | **HIGH** |
| 11 | Correction Detection | Protocol | Rapid follow-up (<2s), high text similarity (>80%), correction markers ("*", "I meant"), supersede first message | Scenario 1.1 | None | 0% | **YES** | **HIGH** |
| 12 | Rapid-Fire Message Batching | Protocol | Multiple messages <500ms apart, wait for pause, merge into single multi-part query | Scenario 1.2 | None | 0% | **YES** | **HIGH** |
| 13 | Amendment Protocol | Protocol | Modifying completed action (<30s), "actually", "change to" - COMPENSATE_AND_AMEND (Saga), use last_action_id | Scenario 1.3 | Partial (Saga pattern ADR-0006e) | 40% | **YES** (Extension) | **HIGH** |
| 14 | Refinement Protocol | Protocol | Adding constraint to ongoing query, "only Italian" - REFINE_TASK, filter results, don't restart | Scenario 2.3 | None | 0% | **YES** | **MEDIUM** |
| 15 | Topic Change Handling | Protocol | Switching domains mid-conversation, push old QUD to history, cancel old task if streaming | Scenario 2.2 | None | 0% | **YES** | **MEDIUM** |
| 16 | Ambiguous Query Resolution | Protocol | Low confidence (<0.6), underspecified, ask clarification before routing | Scenario 5.3 | None | 0% | **YES** | **MEDIUM** |
| 17 | Small Talk Handler | Component | Social greetings ("How are you?"), handle directly, no orchestration, maintain conversation flow | Meta-Intents | None | 0% | **YES** (Part of Meta-Intent ADR) | **MEDIUM** |
| **REAL-WORLD CHAT SCENARIOS** |
| 18 | Real-World Chat Handling | Protocol Suite | 23 scenarios across 7 categories, comprehensive handling protocols, all resolved implementations | Categories 1-7 | None | 0% | **YES** | **CRITICAL** |
| 19 | Streaming Interruption Protocol | Protocol | DialogueAgent.handle_interruption() - 5-step process (stop, save partial, yield control, clear queue, acknowledge) | Scenario 2.1 | None | 0% | **YES** | **HIGH** |
| 20 | Partial Response Preservation | Feature | SessionState.scoreboard.partial_responses, track interrupted streaming, save incomplete work | Scenario 2.1 | None | 0% | **YES** | **MEDIUM** |
| **WORKFLOW & STATE MANAGEMENT** |
| 21 | Workflow State Machine | Component | Multi-step dependent actions, WorkflowState dataclass, WorkflowStep with dependencies | Scenario 4.3 | None | 0% | **YES** | **CRITICAL** |
| 22 | Referent Tracking | System | Track "it", "that", "which one" across turns, SessionState.scoreboard.referents | Workflow State Machine | None | 0% | **YES** (Part of Workflow ADR) | **HIGH** |
| 23 | Dependency Graph Builder | System | Link multi-turn actions (find → book → send), track dependencies between workflow steps | Workflow State Machine | None | 0% | **YES** (Part of Workflow ADR) | **MEDIUM** |
| 24 | Context Switch Manager | System | Save/restore state when topic changes abruptly, push old QUD to history | Topic Change | None | 0% | **YES** | **MEDIUM** |
| 25 | Task Timeline Recorder | Observability | Full timeline of corrections/amendments for debugging and learning | Observability | None | 0% | **YES** | **LOW** |
| 26 | User Intent History | Observability | Track intent evolution across rapid messages | Observability | None | 0% | **YES** | **LOW** |
| **ERROR RECOVERY & RESILIENCE** |
| 27 | API Fallback Strategy | Protocol | execute_with_fallback() - 4-tier cascade (primary → backups → alternative agents → partial with alternatives) | Scenario 6.1 | None | 0% | **YES** | **HIGH** |
| 28 | Circuit Breaker Pattern | System | SessionState.control.api_health, track failure rates, stop trying if too many failures | Scenario 6.1 | None | 0% | **YES** | **HIGH** |
| 29 | Agent Crash Recovery | Protocol | AgentSupervisor - heartbeat monitoring, automatic restart with rate limiting, blacklist crashed agents | Scenario 6.2 | Partial (ADR-0002 supervision) | 60% | **YES** (Extension) | **HIGH** |
| 30 | Agent Blacklist Management | System | Track crashed agents, blacklist temporarily (5min), select backup agents | Scenario 6.2 | None | 0% | **YES** (Part of Crash Recovery ADR) | **MEDIUM** |
| 31 | Multi-Device Conflict Resolution | Protocol | LLM-based conflict detection, 3 strategies (ask_user, last_write_wins, merge), conflict_log tracking | Scenario 6.3 | Partial (ADR-P07 sync) | 30% | **YES** (Extension) | **MEDIUM** |
| 32 | Saga Compensation Engine | System | Rollback/compensate for amended tasks, compensation_actions generation | Amendment Protocol | ADR-0006e (Saga pattern) | 70% | No (Covered) | N/A |
| 33 | External API Retry Logic | System | Exponential backoff, circuit breaker integration | API Fallback | None | 0% | **YES** (Part of API Fallback ADR) | **MEDIUM** |
| 34 | Fallback Response Generator | System | "I'm working on it" when stuck, graceful degradation | Error Recovery | None | 0% | **YES** | **LOW** |
| 35 | Failure Analysis Logger | Observability | Track why tasks failed, what was retried, learn from failures | Observability | None | 0% | **YES** | **LOW** |
| **PRIVACY & SAFETY** |
| 36 | Emergency Deletion Protocol | Protocol | 3-tier cascade: Abort in-flight → Scrub SessionState → Trigger K0 P11 GDPR | Scenario 7.1 | Partial (K0 P11 exists) | 50% | **YES** | **CRITICAL** |
| 37 | Memory Redaction Engine | System | Remove specific memories on user request, abort signal checking in MemoryWriterAgent | Scenario 7.1 | None | 0% | **YES** (Part of Emergency Deletion ADR) | **HIGH** |
| 38 | Safety Re-Evaluation Protocol | Protocol | SafetyArbiter.evaluate_rephrased_query() - Clarification-aware safety, benefit of doubt | Scenario 7.2 | Partial (ADR-0007 safety) | 40% | **YES** (Extension) | **HIGH** |
| 39 | Safety Block Tracking | System | SessionState.meta.last_safety_block, track safety events for re-evaluation | Safety Re-Evaluation | None | 0% | **YES** (Part of Safety Re-Eval ADR) | **MEDIUM** |
| 40 | Audit Trail Logger | System | Track deletions/cancellations, NOT content itself, GDPR compliance | Privacy | None | 0% | **YES** | **MEDIUM** |
| **CONVERSATIONAL INTELLIGENCE** |
| 41 | Slot Filling State Machine | System | Track required vs optional slots per intent, calculate completion %, determine when to ask vs proceed | Conversational Intelligence | None | 0% | **YES** | **HIGH** |
| 42 | Context-Aware Pre-Fill Engine | System | Query SessionState.beliefs for profile data, check calendar, analyze past behavior | Slot Filling | None | 0% | **YES** (Part of Slot Filling ADR) | **HIGH** |
| 43 | Progressive Disclosure Question Generator | System | Priority tiers (Critical → Conditional → Optional), ask one at a time, skip high-confidence pre-fills | Slot Filling | None | 0% | **YES** (Part of Slot Filling ADR) | **MEDIUM** |
| 44 | Slot Validation & Refinement | System | Handle vague inputs ("next month" → specific dates), confirm high-risk slots | Slot Filling | None | 0% | **YES** (Part of Slot Filling ADR) | **MEDIUM** |
| 45 | Multi-Turn Clarification Protocol | Protocol | DialogueAgent modes: STREAMING_RESPONSE, SLOT_FILLING, SLOT_CONFIRMATION, HANDOFF | Conversational Intelligence | None | 0% | **YES** | **MEDIUM** |
| 46 | Conversational Memory | System | SessionState.workflow.active_slot_filling, track filled slots with confidence/source | Slot Filling | None | 0% | **YES** (Part of Slot Filling ADR) | **MEDIUM** |
| **EMOTIONAL INTELLIGENCE** |
| 47 | AgentContext | Data Structure | Rich context envelope: affect, self_model, conversation_context, recent_history, beliefs → formatted as LLM system prompts | Emotional Intelligence | None | 0% | **YES** | **CRITICAL** |
| 48 | LLM-Based Emotional Intelligence | System | Generate empathetic responses from rich system prompts, no hardcoded rules, natural incorporation of context | Emotional Intelligence | None | 0% | **YES** | **CRITICAL** |
| 49 | Context Propagation | Protocol | K1 Orchestrator builds AgentContext from SessionState, passes to specialist agents, formatted as system prompts | Orchestrator Phase 3 | Partial (ADR-0006f) | 30% | **YES** (Extension) | **HIGH** |
| 50 | LLM-Based Affect Tracking | System | Emotion detection via LLM (not keyword matching), nuanced understanding, integrates with P04 pipeline | Emotional Intelligence | Partial (P04 exists) | 40% | **YES** (Extension) | **HIGH** |
| 51 | LLM-Based Self-Model Extraction | System | Extract user self-perception beliefs ("I'm bad with money"), update SessionState.self_model | Emotional Intelligence | None | 0% | **YES** (Part of Emotional Intelligence ADR) | **MEDIUM** |
| **HISTORY MANAGEMENT** |
| 52 | Tiered Chat History Management | System | 3-tier architecture (Recent, Summary, Deep) with progressive summarization, 80-85% token cost reduction | System 40 | None | 0% | **YES** | **CRITICAL** |
| 53 | Progressive Summarization Pipeline | System | SessionSummarizer background agent, auto-compress every 10 turns, max 500 tokens | System 40 | None | 0% | **YES** (Part of History Management ADR) | **HIGH** |
| 54 | Smart Context Selection | System | Per-agent context tuning, topic filtering, conditional K0 retrieval | System 40 | None | 0% | **YES** (Part of History Management ADR) | **HIGH** |
| **K0 PIPELINE EXTENSIONS** |
| 55 | P03 Consolidation Detail | Pipeline Spec | 5-phase process: Hippocampal Replay → Episodic→Semantic → KG Evolution → Synaptic Pruning → Dream Exploration | P03 Pipeline | Partial (ADR-0001) | 30% | **YES** | **LOW** |
| 56 | P06 Learning Loop Detail | Pipeline Spec | Advisory-only K1 → Authoritative K0 validation, drift detection with rollback capability | P06 Pipeline | Partial (ADR-0001) | 30% | **YES** | **LOW** |
| **TOOL & API INTEGRATION** |
| 57 | Tool Chaining & Orchestration Protocol | Tool Execution | Automatic tool-centric orchestration (dependency graphs, sequential/parallel execution, result passing, failure handling) - PARTIAL via ADR-0052a step-by-step (user-driven only) | System 41 | Partial (ADR-0052a user-driven) | 40% | **YES** | **CRITICAL** |
| 58 | Tool Result Parsing & Validation | Tool Execution | Schema validation, error handling strategies (retry/fallback/escalate), partial success handling, type coercion | System 41 | None | 0% | **YES** | **CRITICAL** |
| 59 | Agent-Tool Integration Patterns | Tool Execution | How agents discover tools, capability→tool mapping, tool access control per agent, agent-specific tool prompts | System 41 | Partial (ADR-0004 registry) | 20% | **YES** | **HIGH** |
| 60 | Dynamic Tool Discovery & Hot-Reload | Tool Execution | Runtime tool discovery (MCP servers), hot-reload schemas, tool versioning, deprecation warnings | System 41 | None | 0% | **YES** | **HIGH** |
| 61 | Tool Performance Budgets & SLO Enforcement | Tool Execution | SLO enforcement, performance monitoring per tool, cost tracking, adaptive timeout adjustment | System 41 | Partial (latency_hint exists) | 10% | **YES** | **HIGH** |
| 62 | Tool Context Injection Protocol | Tool Execution | Privacy-aware context passing (user_id, session_id, cognitive_trace_id, SessionState filtering) | System 41 | None | 0% | **YES** | **MEDIUM** |
| **PROACTIVE BEHAVIOR & ANTICIPATORY ACTIONS** |
| 63 | Proactive Behavior Core Architecture | Intelligence | ProactiveAgent (Tier 2), Trigger System (4 types), Confidence Scoring Engine (rule-based), SessionState.proactive | System 42 | None | 0% | **YES** | **CRITICAL** |
| 64 | Proactive Feedback Loop & Learning | Intelligence | Explicit/implicit feedback handling, confidence threshold adaptation, success rate tracking, graceful degradation | System 42 | None | 0% | **YES** | **CRITICAL** |

---

## SessionState Extensions Required (Beyond ADR-0017)

| Extension | Section | Description | Priority |
|-----------|---------|-------------|----------|
| `workflow_state` | control | Multi-step workflow tracking (WorkflowState, WorkflowStep, dependencies) | **CRITICAL** |
| `conflict_log` | control | Multi-device conflict tracking (ConflictingRequest dataclass) | **MEDIUM** |
| `api_health` | control | Circuit breaker tracking (APIHealthStatus, consecutive failures) | **HIGH** |
| `partial_responses` | scoreboard | Interrupted streaming preservation | **MEDIUM** |
| `last_safety_block` | meta | Safety re-evaluation tracking (SafetyBlock dataclass) | **HIGH** |
| `active_slot_filling` | workflow (new) | Conversational intelligence slot tracking | **HIGH** |
| `interruption_state` | workflow (new) | Save/restore state for interruptions | **MEDIUM** |

---

## Orchestrator Extensions Required (Beyond ADR-0006)

| Extension | Phase | Description | Priority |
|-----------|-------|-------------|----------|
| `execute_with_fallback()` | Phase 3 | 4-tier API cascade (primary → backups → alternatives → partial) | **HIGH** |
| `blacklist_agent()` | Phase 2 | Crash recovery management, temporary blacklist | **HIGH** |
| `compensate_and_amend()` | Phase 3 | Saga pattern for amendments (ADR-0006e, **already covered**) | N/A |
| `refine_task()` | Phase 3 | Mid-execution constraint addition, filter results | **MEDIUM** |
| `build_agent_context()` | Phase 3 | Extract rich context from SessionState for LLM system prompts | **CRITICAL** |

---

## PlannerAgent Extensions Required (Beyond ADR-0007)

| Extension | Stage | Description | Priority |
|-----------|-------|-------------|----------|
| `SafetyArbiter.evaluate_rephrased_query()` | Validate | Clarification-aware safety re-evaluation, benefit of doubt | **HIGH** |
| `SafetyBlock` tracking | Validate | SessionState.meta integration for re-evaluation | **MEDIUM** |

---

## Priority-Based ADR Roadmap

### CRITICAL (Production-Blocking) - 8 ADRs

**Must be created FIRST - blocks production deployment**

1. **ADR-XXXX: ConciergeAgent Pattern (Master Coordinator with 11 Meta-Intents)**
   - Description: Master coordinator pattern, single entry point, comprehensive LLM system prompt handling all meta-intent classification
   - Components: ConciergeAgent class, meta-intent classification, SessionState updates, routing decisions
   - Related: Three-Tier Hierarchy, Real-World Chat Handling
   - Implementation: ~500 lines Python, LLM system prompt design

2. **ADR-XXXX: Real-World Chat Handling Protocol Suite (23 Scenarios, 7 Categories)**
   - Description: Comprehensive protocol suite for production-ready conversational handling
   - Categories: User Corrections (3), Mid-Response Interruptions (3), System Delays (3), Multi-Turn Dependencies (3), Conversational Noise (3), Error Recovery (3), Privacy/Safety (2)
   - Components: All 23 scenario implementations with protocols
   - Related: ConciergeAgent, Workflow State Machine, Emergency Deletion

3. **ADR-XXXX: Three-Tier Agent Hierarchy (Concierge + Specialists + Writers)**
   - Description: Architectural pattern for agent organization and coordination
   - Tiers: Tier 1 (ConciergeAgent coordinator), Tier 2 (Specialist agents), Tier 3 (Writer agents background bookkeeping)
   - Integration: ADR-0086 (Dynamic Creation), ADR-0006f (Orchestration), ADR-0017 (SessionState)
   - Related: ConciergeAgent, Writer Agents, Emotional Intelligence

4. **ADR-XXXX: Writer Agents Pattern (Background Bookkeeping Tier)**
   - Description: Background agent tier for memory formation, learning extraction, semantic enrichment
   - Agents: MemoryWriterAgent, LearningExtractor, SemanticEnricher
   - Protocol: Two-phase memory formation (T0+1ms raw, T0+500ms enrichment)
   - Integration: K0 P02 pipeline, non-blocking, always active

5. **ADR-XXXX: Workflow State Machine (Multi-Step Dependent Actions)**
   - Description: State machine for tracking multi-turn workflows with dependencies
   - Components: WorkflowState, WorkflowStep, dependency graph, referent tracking
   - SessionState Extension: control.workflow_state
   - Related: Multi-Turn Dependencies scenarios, Referent Tracking

6. **ADR-XXXX: Emergency Deletion Protocol (3-Tier Cascade)**
   - Description: GDPR-compliant emergency deletion with 3-tier cascade
   - Tiers: Abort in-flight → Scrub SessionState → Trigger K0 P11 GDPR
   - Components: detect_deletion_intent(), execute_emergency_deletion(), MemoryWriterAgent abort checking
   - Related: Privacy/Safety scenarios, K0 P11 pipeline

7. **ADR-XXXX: AgentContext (Rich Context Envelope for LLM System Prompts)**
   - Description: Data structure for passing rich context to specialist agents via LLM system prompts
   - Components: AffectState, SelfModel, ConversationState, recent_history, beliefs
   - Method: to_system_prompt() formatting for LLM inference
   - Related: Emotional Intelligence, Context Propagation

8. **ADR-XXXX: LLM-Based Emotional Intelligence System**
   - Description: LLM-powered empathetic response generation, no hardcoded rules
   - Components: LLMEmotionalIntelligence, LLMAffectTracker, LLMSelfModelTracker
   - Integration: P04 (Affective Tagging), SessionState.affect, SessionState.self_model
   - Related: AgentContext, Specialist Agents extensions

9. **ADR-XXXX: Tiered Chat History Management (Progressive Summarization)**
   - Description: 3-tier architecture (Recent/Summary/Deep) with 80-85% token cost reduction
   - Components: SessionSummarizer (background), ContextSelector (per-agent tuning), K0 retrieval integration
   - Tiers: Tier 1 (Recent 10 turns, ~1000 tokens), Tier 2 (Session summary, ~500 tokens), Tier 3 (K0 retrieval, ~500 tokens conditional)
   - SessionState Extension: scoreboard.session_summary, last_summary_turn, emotional_arc
   - Benefits: Scales to unlimited conversation length, bounded token cost 1500-2000 per call vs 10K+ naive
   - Integration: AgentContext, K1 Orchestrator, MemoryWriterAgent, K0 P01 (Recall)
   - Related: Emotional Intelligence, Context Propagation, Conversational Intelligence

---

### HIGH (Essential Features) - 14 ADRs

**Required for core functionality, implement after CRITICAL**

9. **ADR-XXXX: Specialist Agent Extensions (Emotional Intelligence Integration)**
   - Description: Extensions to specialist agents for emotional intelligence via AgentContext
   - Agents: HealthcareAgent, FinanceAgent, SocialCoordinator, PlannerAgent, RoutineAgent, EmergencyAgent
   - Integration: ADR-0086 (base), AgentContext (system prompts), LLM-based EI
   - Related: AgentContext, Context Propagation

10. **ADR-XXXX: Two-Phase Memory Formation Protocol**
    - Description: Non-blocking memory write protocol with immediate and enriched phases
    - Phases: Phase 1 (T0+1ms raw capture), Phase 2 (T0+500ms enrichment)
    - Components: MemoryWriterAgent phases, background processing
    - Related: Writer Agents, K0 P02 pipeline

11. **ADR-XXXX: Streaming Interruption Protocol**
    - Description: Graceful interruption handling for DialogueAgent mid-response
    - Protocol: 5-step process (stop streaming, save partial, yield control, clear queue, acknowledge)
    - SessionState Extension: scoreboard.partial_responses
    - Related: Real-World Chat Handling, Partial Response Preservation

12. **ADR-XXXX: API Fallback Strategy (4-Tier Cascade)**
    - Description: Automatic API failure recovery with fallback strategy
    - Tiers: Primary API → Backup APIs → Alternative agents → Partial with alternatives
    - Components: execute_with_fallback(), APIHealthStatus, circuit breaker
    - Related: Error Recovery scenarios, Circuit Breaker Pattern

13. **ADR-XXXX: Agent Crash Recovery Protocol (AgentSupervisor Extensions)**
    - Description: Extensions to ADR-0002 supervision for crash recovery
    - Components: AgentSupervisor.monitor_agent_health(), heartbeat protocol, automatic restart with rate limiting
    - Integration: ADR-0002 (base supervision), blacklist_agent()
    - Related: Error Recovery, Agent Blacklist Management

14. **ADR-XXXX: Slot Filling State Machine (Conversational Intelligence)**
    - Description: Multi-turn clarification with context-aware slot pre-filling
    - Components: Slot tracking, completion %, context-aware pre-fill, progressive disclosure
    - SessionState Extension: workflow.active_slot_filling
    - Related: Conversational Intelligence, Ambiguous Query Resolution

15. **ADR-XXXX: Context Propagation Protocol (Orchestrator → LLM System Prompts)**
    - Description: Extensions to ADR-0006f Phase 3 for AgentContext propagation
    - Components: build_agent_context(), agent.execute_with_llm_context()
    - Integration: ADR-0006f (base), AgentContext, LLM-Based EI
    - Related: Emotional Intelligence, Specialist Agent Extensions

16. **ADR-XXXX: LLM-Based Affect & Self-Model Tracking**
    - Description: Extensions to P04 for LLM-based emotion and self-belief extraction
    - Components: LLMAffectTracker, LLMSelfModelTracker
    - Integration: P04 (Affective Tagging), SessionState updates
    - Related: Emotional Intelligence, AgentContext

17. **ADR-XXXX: Safety Re-Evaluation Protocol (Clarification-Aware)**
    - Description: Extensions to ADR-0007 for safety re-evaluation after user clarification
    - Components: SafetyArbiter.evaluate_rephrased_query(), benefit of doubt logic
    - SessionState Extension: meta.last_safety_block
    - Related: Privacy/Safety scenarios, PlannerAgent extensions

18. **ADR-XXXX: Memory Redaction Engine (Abort Signal System)**
    - Description: MemoryWriterAgent extensions for abortion checking and emergency deletion
    - Components: check_abort_signal(), abort before/after write, race condition handling
    - Integration: Emergency Deletion Protocol, K0 P11 GDPR
    - Related: Privacy/Safety, Emergency Deletion

19. **ADR-XXXX: Correction Detection Protocol (Rapid Follow-Up)**
    - Description: Typo/correction handling with superseding messages
    - Detection: Rapid follow-up (<2s), high similarity (>80%), correction markers
    - SessionState: recent_turns superseded_by tracking
    - Related: Real-World Chat Handling, User Corrections

20. **ADR-XXXX: Rapid-Fire Message Batching Protocol (500ms Window)**
    - Description: Message queue with batching window for rapid-fire input
    - Components: 500ms buffer, message merging, single turn grouping
    - SessionState: scoreboard.turn_id for batching
    - Related: Real-World Chat Handling, User Corrections

21. **ADR-XXXX: Progressive Summarization Pipeline (SessionSummarizer)**
    - Description: Background agent for automatic conversation compression every 10 turns
    - Components: SessionSummarizer agent (Tier 3 Writer), LLM-based summarization, compression logic
    - SessionState: scoreboard.session_summary, last_summary_turn
    - Performance: <2s background task, max 500 tokens output
    - Related: Tiered History Management, MemoryWriterAgent

22. **ADR-XXXX: Smart Context Selection (Per-Agent Tuning)**
    - Description: Intelligent context selection based on agent type and task needs
    - Components: ContextSelector, topic filtering, conditional K0 retrieval, per-agent token budgets
    - Agent Types: ConciergeAgent (1500 tokens), Specialist (1000-1500), MemoryWriter (2500), SafetyArbiter (500)
    - Related: Tiered History Management, AgentContext, K1 Orchestrator Phase 3

23. **ADR-XXXX: Tool Chaining & Orchestration Protocol (Automatic, Tool-Centric)**
    - Description: Automatic tool orchestration with dependency graphs, sequential/parallel execution, result passing
    - Components: Tool dependency graph builder, orchestration engine, failure handling (retry/fallback/partial)
    - Current State: ADR-0052a provides USER-DRIVEN orchestration (step-by-step approval)
    - Missing: TOOL-DRIVEN orchestration (automatic chaining for low-risk queries)
    - Examples: "Find restaurant nearby and book" → auto-chain: location → search → filter → book
    - Integration: ADR-0052a (user-driven), tool registry, MCP/WASM sandboxes
    - SessionState: workflow.active_tool_chain (tracking state)
    - Related: System 41 (Tool Integration), ADR-0001e (sandboxes), ADR-0052a (user approval)

24. **ADR-XXXX: Tool Result Parsing & Validation (Schema Enforcement)**
    - Description: Schema validation, error handling strategies, type coercion, partial success handling
    - Components: Tool result schema definitions (JSON Schema/FlatBuffers), validation engine, error recovery
    - Error Strategies: Retry (malformed result), Fallback (tool failed), Partial (5/10 OK?), Escalate (ask user)
    - Integration: Tool registry (schema refs), circuit breaker (failure handling), tool.pdl.yml protocol
    - Performance: <100ms validation overhead P95
    - Related: System 41 (Tool Integration), ADR-0001e (tool execution), ADR-0003 (protocol)

25. **ADR-XXXX: Proactive Behavior Core Architecture**
    - Description: Trigger-based proactive actions & suggestions without explicit user request
    - Components: ProactiveAgent (Tier 2 specialist), Trigger System (Time/Location/Pattern/Anomaly), Confidence Scoring Engine (rule-based), Suggestion Delivery System
    - SessionState Extensions: proactive (ProactiveSuggestion, FeedbackHistory, user_preferences, disabled_triggers)
    - Confidence Thresholds: >0.9 auto-execute safe actions, 0.7-0.9 suggest with approval, <0.7 learn only
    - Integration: K0 P01 (pattern detection), P21-P30 tools (execution), ADR-0052 (confirmation protocols), Three-Tier hierarchy
    - Performance: <500ms P95 (trigger → suggestion), <1% CPU background monitoring
    - Examples: Medication reminders (time+pattern), grocery restocking (pattern), calendar conflicts (event), commute prep (time+location+weather)
    - Research Foundation: Tennenhouse 2000 (Proactive Computing), Horvitz 2003 (Attention-Sensitive Alerting), Ryan & Deci 2000 (Self-Determination Theory), Lee & See 2004 (Trust Calibration)
    - Privacy: GREEN band by default, RED band requires explicit consent, all suggestions logged (90-day retention)
    - Related: System 42 (Proactive Behavior), ADR-0052 (confirmation), ADR-0001e (tool execution)

26. **ADR-XXXX: Proactive Feedback Loop & Learning**
    - Description: Adaptive learning from user acceptance/rejection, confidence threshold adjustment, graceful degradation
    - Components: Explicit feedback handler (accept/dismiss/never-again), implicit feedback detector (missed opportunities), confidence adaptation engine, category disablement
    - Feedback Strategies: Accept → confidence +0.05, Dismiss → confidence -0.03, Never-again → confidence=0.0 (disable trigger)
    - Adaptation: Success rate >0.85 → lower threshold (suggest more), <0.60 → raise threshold (suggest less)
    - Temporal Adjustment: User accepts 10min late → shift suggestion time +10min
    - Notification Fatigue: Max 3/hour, 15/day, min 10min gap between suggestions
    - Cold Start: Generic templates, explicit onboarding, or passive learning (30 days)
    - Multi-User: Per-user + shared categories (family grocery restocking)
    - Integration: SessionState.proactive.feedback_history, success rate tracking per category
    - Observability: Prometheus metrics (suggestions generated, accepted, dismissed, success rate, missed opportunities, rate limited)
    - Related: System 42 (Proactive Behavior), Phase 2 Implementation

---

### HIGH PRIORITY (17 ADRs)

**Required for core functionality, implement after CRITICAL**

9. **ADR-XXXX: Specialist Agent Extensions (Emotional Intelligence Integration)**
    - Description: Add constraints to ongoing tasks without restart
    - Components: refine_task(), filter current results
    - Related: Real-World Chat Handling, Orchestrator Extensions

22. **ADR-XXXX: Topic Change Handling Protocol**
    - Description: Context switching with QUD history preservation
    - Components: push old QUD, cancel old task, context switch manager
    - Related: Real-World Chat Handling, Context Switch Manager

23. **ADR-XXXX: Ambiguous Query Resolution Protocol**
    - Description: Clarification prompts for underspecified queries
    - Detection: Low confidence (<0.6), missing key details
    - Related: Conversational Intelligence, Slot Filling

24. **ADR-XXXX: Multi-Device Conflict Resolution Protocol**
    - Description: Extensions to ADR-P07 for conflict detection and resolution
    - Components: LLM-based conflict detection, 3 strategies (ask_user, last_write_wins, merge)
    - SessionState Extension: control.conflict_log
    - Related: Error Recovery, ADR-P07 (Sync/CRDT)

25. **ADR-XXXX: Circuit Breaker Pattern (API Health Tracking)**
    - Description: Track API failure rates, stop trying if too many failures
    - Components: APIHealthStatus, consecutive_failures, circuit_open flag
    - SessionState Extension: control.api_health
    - Related: API Fallback Strategy, Error Recovery

26. **ADR-XXXX: Partial Response Preservation**
    - Description: Save incomplete work before interruption
    - SessionState Extension: scoreboard.partial_responses
    - Related: Streaming Interruption, Real-World Chat Handling

27. **ADR-XXXX: Context Switch Manager**
    - Description: Save/restore state when topic changes abruptly
    - Components: push old QUD, SessionState snapshot
    - Related: Topic Change Handling, Workflow State Machine

28. **ADR-XXXX: Progressive Disclosure Question Generator**
    - Description: Smart clarification question ordering (Critical → Conditional → Optional)
    - Components: Priority tiers, ask one at a time, skip high-confidence pre-fills
    - Related: Slot Filling, Conversational Intelligence

29. **ADR-XXXX: Slot Validation & Refinement**
    - Description: Handle vague inputs, confirm high-risk slots
    - Components: Vague input resolution ("next month" → dates), confirmation prompts
    - Related: Slot Filling, Conversational Intelligence

30. **ADR-XXXX: Multi-Turn Clarification Protocol (DialogueAgent Modes)**
    - Description: DialogueAgent state machine for conversational flow
    - Modes: STREAMING_RESPONSE, SLOT_FILLING, SLOT_CONFIRMATION, HANDOFF
    - Related: Slot Filling, Conversational Intelligence

31. **ADR-XXXX: Audit Trail Logger (Privacy Compliance)**
    - Description: Track deletions/cancellations without logging content
    - Components: audit_log, GDPR compliance, timestamp tracking
    - Related: Emergency Deletion, Privacy/Safety

32. **ADR-XXXX: Agent-Tool Integration Patterns (Discovery & Access Control)**
    - Description: How agents discover and invoke tools, capability-based access control
    - Components: Tool discovery (registry lookup + LLM), agent capability → tool mapping, per-agent access control
    - Examples: FinanceAgent can use bank_api/payment_api, ConciergeAgent can use all tools
    - Integration: Tool registry (ADR-0004), capability system (ADR-0010), agent architecture
    - SessionState: agent.available_tools (per-agent tool list)
    - Related: System 41 (Tool Integration), ADR-0004 (registry), ADR-0010 (capabilities)

33. **ADR-XXXX: Dynamic Tool Discovery & Hot-Reload (Zero-Downtime Updates)**
    - Description: Runtime tool discovery, hot-reload schemas, tool versioning, deprecation warnings
    - Components: MCP server discovery, schema hot-reload, version management, deprecation system
    - Examples: New MCP server starts → K1 discovers automatically (no restart)
    - Integration: Tool registry (ADR-0004), MCP protocol (ADR-0033a), lifecycle management
    - Performance: <500ms discovery latency P95
    - Related: System 41 (Tool Integration), ADR-0001e (MCP), deployment flexibility

34. **ADR-XXXX: Tool Performance Budgets & SLO Enforcement (Observability)**
    - Description: SLO enforcement, performance monitoring per tool, cost tracking, adaptive timeouts
    - Components: SLO definitions (P50/P95/P99 latency, error rate, cost budgets), circuit breaker integration, monitoring dashboard
    - Examples: calendar_api P95 > 500ms → alert, bank_api daily cost > $10 → alert
    - Integration: Circuit breaker (ADR-0001e), tool registry (latency_hint), observability layer
    - Performance: <50ms SLO check overhead P95
    - Related: System 41 (Tool Integration), ADR-0001e (lifecycle), observability

---

### MEDIUM (Important Enhancements) - 12 ADRs

**Nice-to-have features, enhance UX but not blocking**

21. **ADR-XXXX: Refinement Protocol (Mid-Execution Constraint Addition)**
    - Description: Full timeline of corrections/amendments for debugging
    - Components: timeline_log, event tracking
    - Related: Observability, Real-World Chat Handling

33. **ADR-XXXX: User Intent History (Observability)**
    - Description: Track intent evolution across rapid messages
    - Related: Observability, Rapid-Fire Batching

34. **ADR-XXXX: Fallback Response Generator**
    - Description: Graceful degradation responses when stuck
    - Components: "I'm working on it" templates
    - Related: Error Recovery, Resilience

35. **ADR-XXXX: Failure Analysis Logger (Observability)**
    - Description: Track why tasks failed, what was retried
    - Related: Observability, Error Recovery

36. **ADR-XXXX: P03 Consolidation 5-Phase Detail**
    - Description: Detailed specification for P03 5-phase consolidation
    - Phases: Hippocampal Replay → Episodic→Semantic → KG Evolution → Synaptic Pruning → Dream Exploration
    - Integration: K0 P03 pipeline, ADR-0001 extensions
    - Related: K0 Pipelines

37. **ADR-XXXX: P06 Learning Loop Detail (Drift Detection)**
    - Description: Detailed specification for P06 learning loop with drift detection
    - Components: Advisory K1 → Authoritative K0, drift detection, rollback capability
    - Integration: K0 P06 pipeline, ADR-0001 extensions
    - Related: K0 Pipelines

38. **ADR-XXXX: Tool Context Injection Protocol (Privacy-Aware Context Passing)**
    - Description: Pass user context to tools with privacy boundaries, filtered SessionState views
    - Components: ToolContext dataclass (user_id, session_id, cognitive_trace_id, filtered SessionState), privacy band filtering
    - Examples: Tool resolves "current location" from context.session_state.current_location
    - Integration: Tool execution (ADR-0001e), privacy bands (ADR-0032-0038), SessionState (ADR-0017)
    - Privacy: GREEN band data only by default, explicit capability for AMBER/RED access
    - Related: System 41 (Tool Integration), tool personalization, privacy boundaries

---

### LOW (Documentation Completeness) - 6 ADRs

**Nice-to-have for completeness, not blocking or high priority**

32. **ADR-XXXX: Task Timeline Recorder (Observability)**

**Extensions to ADR-0017 required for new features:**

### New Sections Required

| Section | Extensions | ADRs Required |
|---------|-----------|---------------|
| **control** | workflow_state, conflict_log, api_health, last_action_id extensions, active_tasks extensions | Workflow State Machine, Multi-Device Conflicts, Circuit Breaker, Amendment Protocol |
| **scoreboard** | partial_responses, turn_id batching, referents tracking | Streaming Interruption, Rapid-Fire Batching, Workflow State Machine |
| **meta** | last_safety_block, safety_flag_resolved, safety_violations | Safety Re-Evaluation Protocol |
| **workflow** (NEW) | active_slot_filling, interruption_state | Slot Filling State Machine, Context Switch Manager |

---

## Orchestrator Extension Roadmap

**Extensions to ADR-0006 required for new features:**

### Phase 3 (Execution) Extensions

| Method | Description | ADR Required |
|--------|-------------|--------------|
| `execute_with_fallback()` | 4-tier API cascade | API Fallback Strategy |
| `blacklist_agent()` | Crash recovery management | Agent Crash Recovery Protocol |
| `refine_task()` | Mid-execution constraint addition | Refinement Protocol |
| `build_agent_context()` | Extract rich context for LLM system prompts | Context Propagation Protocol |

### Phase 2 (Selection) Extensions

| Method | Description | ADR Required |
|--------|-------------|--------------|
| `replace_agent()` | Replace crashed agent with backup | Agent Crash Recovery Protocol |

---

## PlannerAgent Extension Roadmap

**Extensions to ADR-0007 required for new features:**

### Stage 3 (Validate) Extensions

| Component | Description | ADR Required |
|-----------|-------------|--------------|
| `SafetyArbiter.evaluate_rephrased_query()` | Clarification-aware safety | Safety Re-Evaluation Protocol |
| `SafetyBlock` tracking | SessionState.meta integration | Safety Re-Evaluation Protocol |

---

## Implementation Dependencies

**ADR dependencies (create parent ADRs first):**

```
CRITICAL Tier (8 ADRs):
  1. ConciergeAgent Pattern
     ├─ Depends on: ADR-0006f (Orchestrator), ADR-0017 (SessionState)
     └─ Enables: Real-World Chat Handling, Three-Tier Hierarchy

  2. Real-World Chat Handling
     ├─ Depends on: ConciergeAgent, Workflow State Machine, Emergency Deletion
     └─ Enables: All scenario implementations

  3. Three-Tier Hierarchy
     ├─ Depends on: ConciergeAgent, Writer Agents, ADR-0086 (Dynamic Creation)
     └─ Enables: Complete architecture organization

  4. Writer Agents Pattern
     ├─ Depends on: ADR-0017 (SessionState), K0 P02
     └─ Enables: Two-Phase Memory Formation

  5. Workflow State Machine
     ├─ Depends on: ADR-0017 (SessionState)
     └─ Enables: Multi-Turn Dependencies, Referent Tracking

  6. Emergency Deletion Protocol
     ├─ Depends on: K0 P11 (GDPR), Writer Agents
     └─ Enables: Memory Redaction Engine

  7. AgentContext
     ├─ Depends on: ADR-0017 (SessionState)
     └─ Enables: LLM-Based EI, Context Propagation

  8. LLM-Based Emotional Intelligence
     ├─ Depends on: AgentContext, K0 P04 (Affective Tagging)
     └─ Enables: Specialist Agent Extensions

HIGH Tier (12 ADRs):
  - Specialist Agent Extensions (depends on: AgentContext, LLM-Based EI)
  - Two-Phase Memory Formation (depends on: Writer Agents)
  - Streaming Interruption (depends on: Real-World Chat Handling)
  - API Fallback Strategy (depends on: ADR-0006f Orchestrator)
  - Agent Crash Recovery (depends on: ADR-0002 Supervision)
  - Slot Filling State Machine (depends on: ADR-0017 SessionState)
  - Context Propagation (depends on: AgentContext, ADR-0006f)
  - Affect/Self-Model Tracking (depends on: LLM-Based EI, K0 P04)
  - Safety Re-Evaluation (depends on: ADR-0007 Safety)
  - Memory Redaction (depends on: Emergency Deletion)
  - Correction Detection (depends on: ConciergeAgent)
  - Rapid-Fire Batching (depends on: ConciergeAgent)

MEDIUM & LOW Tiers:
  - All depend on CRITICAL and HIGH tier ADRs
```

---

## Next Steps

### Phase 1: CRITICAL ADRs (Weeks 1-4)

**Week 1-2:**

1. Create ADR-XXXX: ConciergeAgent Pattern (foundation)
2. Create ADR-XXXX: Three-Tier Agent Hierarchy (architecture)
3. Create ADR-XXXX: AgentContext (context envelope)

**Week 3-4:**
4. Create ADR-XXXX: LLM-Based Emotional Intelligence System
5. Create ADR-XXXX: Writer Agents Pattern
6. Create ADR-XXXX: Workflow State Machine

**Week 4-5:**
7. Create ADR-XXXX: Real-World Chat Handling (comprehensive)
8. Create ADR-XXXX: Emergency Deletion Protocol

### Phase 2: HIGH ADRs (Weeks 5-8)

**Weeks 5-6:** Specialist extensions, memory formation, streaming
**Weeks 7-8:** API fallback, crash recovery, slot filling, context propagation, safety

### Phase 3: MEDIUM ADRs (Weeks 9-11)

**Weeks 9-10:** Refinement, topic change, conflicts, circuit breaker
**Week 11:** Partial responses, context switch, clarification protocols

### Phase 4: LOW ADRs (Week 12)

**Week 12:** Observability ADRs, P03/P06 detail specs

---

## Validation Checklist

Before creating each ADR, validate:

- [ ] **Problem statement clear**: What issue does this solve?
- [ ] **Integration points identified**: Which existing ADRs does this extend?
- [ ] **SessionState impact documented**: What extensions required?
- [ ] **Performance budget defined**: Latency/memory/throughput targets
- [ ] **Testing strategy outlined**: How to verify implementation?
- [ ] **Observability plan**: What metrics/traces/logs needed?
- [ ] **Security/privacy review**: Any sensitive data or capabilities?
- [ ] **Alternatives considered**: Why this approach vs others?
- [ ] **Dependencies mapped**: What must exist before this?
- [ ] **Success criteria defined**: How to measure if working?

---

## Summary Statistics

**Whiteboard Analysis:**

- Total lines: 5800+ (was 5176, +System 42 Proactive Behavior)
- Major sections: 15+
- Scenarios covered: 23/23 (100%)
- Systems identified: 42 (was 41, +System 42 Proactive Behavior)
- Components: 60+ (was 56+, +ProactiveAgent, Trigger System, Confidence Scoring, Delivery System, Feedback Loop, Settings)

**ADR Coverage:**

- Existing ADRs: 300+
- Topics requiring new ADRs: 49 (was 47, +2 proactive behavior gaps)
- Topics fully covered: 5 (ADR-0052 HITL, ADR-0033b WASM, ADR-0001e sandbox, ADR-0006e Saga, ADR-0086 agent creation)
- Topics partially covered: 13

**Priority Distribution:**

- CRITICAL: 13 ADRs (was 11, +2 proactive gaps) - 22-28 weeks estimated
- HIGH: 17 ADRs - 34-51 weeks estimated
- MEDIUM: 12 ADRs - 24-36 weeks estimated
- LOW: 6 ADRs - 12-18 weeks estimated
- **Total Estimated Effort:** 92-133 weeks (18-26 months) for all 49 ADRs
- Topics with no coverage: 44 (was 41, +6 tool gaps - 3 covered)

**Priority Distribution:**

- **CRITICAL**: 11 ADRs (23.4%, was 22.0%) - Production-blocking
  - New: Tool Chaining & Orchestration, Tool Result Validation
- **HIGH**: 17 ADRs (36.2%, was 34.1%) - Essential features
  - New: Agent-Tool Integration, Dynamic Tool Discovery, Tool Performance SLOs
- **MEDIUM**: 12 ADRs (25.5%, was 26.8%) - Important enhancements
  - New: Tool Context Injection
- **LOW**: 6 ADRs (12.8%, was 14.6%) - Documentation completeness

**Estimated Effort:**

- CRITICAL: 5-6 weeks (11 ADRs × 2-3 days each)
- HIGH: 5-6 weeks (17 ADRs × 1-2 days each)
- MEDIUM: 2-3 weeks (12 ADRs × 1-2 days each)
- LOW: 1 week (6 ADRs × 1 day each)
- **Total: 13-16 weeks for complete documentation** (was 11-14 weeks)

---

**Conclusion:** The whiteboard contains 47 major architectural topics/patterns/components that require formal ADR documentation (was 41, +6 tool integration gaps from System 41). 11 are CRITICAL (production-blocking), including the new **Tiered Chat History Management** system (80-85% token cost reduction) and **Tool Chaining & Orchestration** + **Tool Result Validation** for production-ready tool execution. 17 are HIGH priority (essential features), 12 are MEDIUM (important enhancements), and 6 are LOW priority (documentation completeness).

**Key Finding:** Tool/API integration is 45% covered (ADR-0001e sandbox, ADR-0052 HITL, ADR-0033b WASM) but critical orchestration gaps remain (automatic chaining, validation, discovery).

Recommended approach: Create ADRs in priority order over 13-16 weeks, starting with CRITICAL tier in weeks 1-6.
