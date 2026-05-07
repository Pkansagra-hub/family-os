# K1_FLOWS.md — Enumerated Flow Inventory

Source: [architecture_diagrams/k1/K1_FLOWS.md](../../architecture_diagrams/k1/K1_FLOWS.md) (11,480 lines, 154 named flows)
Compiled: gap-analysis prep. **Pre-Concierge-impl doc** — names of components are aspirational; verify against current bootstrap in next pass.

## Document Structure (18 sections)

| § | Title | Flow IDs | Lines |
|---|---|---|---|
| 1 | Core Conversation Flows | F01–F10 | 9–433 |
| 2 | UltraBERT Classification | F11–F32 | 434–1402 |
| 3 | Tool Execution | F33–F42 | 1403–1881 |
| 4 | Orchestrator | F43–F52 | 1882–2422 |
| 5 | Planner (4-Stage) | F53–F59 | 2423–2831 |
| 6 | Sub-Agent Lifecycle | F60–F65 | 2832–3232 |
| 7 | SessionState (Single Writer / Tiering) | F66–F77 | 3233–3994 |
| 8 | K0 Bridge | F78–F87 | 3995–4621 |
| 9 | Proactive Agent | F88–F94 | 4622–5099 |
| 10 | Capability Fabric | F95–F103 | 5100–5711 |
| 11 | Model Gateway / LLM Consumers | F104–F111 | 5712–6536 |
| 12 | Experience Layer (periodic 20–30 turn) | F112–F119 | 6537–7328 |
| 13 | Rhythm & Empathy / ToM | F120–F127 | 7329–8154 |
| 14 | Module Loader | F128–F131 | 8155–8640 |
| 15 | Event Bus & Coordination / WFQ | F132–F137 | 8641–9257 |
| 16 | HIL Bidirectional Loops | F138–F141 | 9258–9772 |
| 17 | Observability (trace/metric/health) | F142–F144 | 9773–10198 |
| 18 | LLM Control Plane (prompts + validation) | F145–F154 | 10225–11477 |

Legend for **Trigger** column: `t.<x>` = topic, `evt:` = bus event, `tick:` = periodic, `call:` = synchronous in-proc, `state:` = FSM state entry.

---

## §1 — Core Conversation Flows (F01–F10)

| F# | Name | Trigger | Key Components | Lines |
|---|---|---|---|---|
| F01 | User Input → ACKING | t.k1.concierge.user_input | LISTENING→ACKING FSM, UltraBERT (22ms) | 13 |
| F02 | Uncertainty Check & Clarification | ACKING uncertainty ≥ 0.2 | UNCERTAINTY_ESTIMATOR, ENTROPY_MIN_QUESTION_PLANNER, PENDING_CLARIFICATIONS | 40 |
| F03 | Interrupt Handling | t.k1.concierge.user_input mid-turn / sub-agent intr | INTERRUPT_HANDLING state, DELTA_BUS, AGGREGATION_WINDOW | 83 |
| F04 | LOW Tier Fast Path | DISPATCHING + tier=LOW | DISPATCHING→Fabric direct, Model Gateway shortcut | 121 |
| F05 | MEDIUM Tier Reasoning | DISPATCHING + tier=MED | Orchestrator mailbox, StepRunner, Fabric | 159 |
| F06 | HIGH Tier Planning | DISPATCHING + tier=HIGH | Orchestrator → Planner 4-stage → DAGExecutor → Fabric | 197 |
| F07 | CRISIS Tier Safety Protocol | UltraBERT crisis flag | CrisisHandler, MODEL_GATEWAY canned, escalation | 241 |
| F08 | LOW Tier Response Delivery | tool result returned (LOW) | DELIVERING state, response.final, response.stream | 290 |
| F09 | MEDIUM/HIGH Response Delivery | orchestrator/planner result | DELIVERING, multi-step result aggregation | 336 |
| F10 | Preliminary Ack Generation | DISPATCHING start (MED/HIGH) | PrelimAckGen, conversational continuity prompt | 390 |

## §2 — UltraBERT Classification Flows (F11–F32)

| F# | Name | Trigger | Key Components | Lines |
|---|---|---|---|---|
| F11 | UltraBERT Core Forward Pass (22ms) | ACKING entry | UltraBERT 12-head shared encoder | 438 |
| F12 | Intent Classification (Multi-Label) | F11 done | IntentHead, multi-label scoring | 488 |
| F13 | Ingress/Domain Classification | F11 done | IngressHead, DomainHead | 536 |
| F14 | Safety Band Classification | F11 done | SafetyHead → GREEN/AMBER/RED | 578 |
| F15 | Emotion Detection | F11 done | EmotionHead → AFFECTIVE_NOW | 621 |
| F16 | NER Entity Extraction | F11 done | NERHead → BELIEFS_ACTIVE | 661 |
| F17 | Relations Extraction | F11 done | RelationsHead | 698 |
| F18 | Sentiment Analysis | F11 done | SentimentHead | 736 |
| F19 | Crisis Detection & Safety Override | safety_band=RED + crisis intent | CrisisDetector → CRISIS tier override | 773 |
| F20 | Multi-Intent Scoring | multi-label intent scores | MultiIntentArbiter | 830 |
| F21 | Cross-Domain Detection | multiple domain heads fire | CrossDomainResolver | 870 |
| F22 | Complexity Classification | F11 done | ComplexityHead → LOW/MED/HIGH/CRISIS | 910 |
| F23 | Hypothesis Generation | gap detected | HypothesisGenerator | 964 |
| F24 | Contract & Signal Gap Detection | intent vs contract delta | ContractGapDetector | 1005 |
| F25 | Context Inference | gap fillable from session | ContextInferrer (uses SessionState) | 1058 |
| F26 | Tiny Sanity Arbiter Validation | hypothesis chosen | TinySanityArbiter | 1104 |
| F27 | Uncertainty Estimation | head outputs ready | UncertaintyEstimator (entropy-based) | 1146 |
| F28 | Entropy-Minimizing Question Planning | uncertainty ≥ 0.2 | EntropyMinQuestionPlanner → 1–2 questions | 1187 |
| F29 | Emotion → AFFECTIVE_NOW Update | F15 done | SingleWriter → AFFECTIVE_NOW | 1242 |
| F30 | NER → BELIEFS_ACTIVE Update | F16 done | SingleWriter → BELIEFS_ACTIVE | 1282 |
| F31 | Safety → CONTROL Update | F14 done | SingleWriter → CONTROL.safety_band | 1322 |
| F32 | Intent/Ingress → CONTROL Update | F12/F13 done | SingleWriter → CONTROL.intent/ingress | 1360 |

## §3 — Tool Execution Flows (F33–F42)

| F# | Name | Trigger | Key Components | Lines |
|---|---|---|---|---|
| F33 | Capability Fabric Tool Invocation | DISPATCHING tool call | CapabilityFabric.execute, IDispatchPort | 1407 |
| F34 | MCP Tool Execution | provider_type=MCP | MCPTransport (stdio), MCPServer | 1454 |
| F35 | K0 Memory Operation | provider_type=Bridge | K0BridgePort (recall/write/ack) | 1498 |
| F36 | WASM Sandbox Execution | provider_type=WASM | WASMRuntime, sandbox isolation | 1547 |
| F37 | Tool Result Return | execution complete | ToolResult envelope, dispatch_envelope path | 1589 |
| F38 | Tool Result → LLM Context Staging | result returned | ContextStager, prompt injection | 1639 |
| F39 | K0 Query Port Recall | recall request | K0QueryPort, vector + WAL fan-out | 1698 |
| F40 | WAL Driver Query | episodic recall | WAL Driver, P02 episodic store | 1749 |
| F41 | Vector Semantic Search | semantic recall | VectorIndex (FAISS), embedding port | 1787 |
| F42 | Context Budget Application | recall results returned | ContextBudgeter (token-aware truncation) | 1831 |

## §4 — Orchestrator Flows (F43–F52)

| F# | Name | Trigger | Key Components | Lines |
|---|---|---|---|---|
| F43 | Task Announcement & Bidding | dispatch_envelope MED | TaskAnnouncer, BidCollector (multi-agent) | 1886 |
| F44 | Multi-Criteria Scoring & Selection | bids collected | MCScorer (cost/latency/skill), AgentSelector | 1945 |
| F45 | Parallel DAG Execution | committed plan or steps | DAGExecutor, parallel branches | 1993 |
| F46 | Saga Pattern Recovery | step failure | SagaCoordinator, compensating actions | 2054 |
| F47 | Constraint Manager Iteration | constrained problem | ConstraintManager (iter loop) | 2106 |
| F48 | Solution Validation (LLM + Rule) | constraint candidate | SolutionValidator, Rule+LLM hybrid | 2161 |
| F49 | Constraint HIL Fallback | validation failed N times | ConstraintHIL → user prompt | 2209 |
| F50 | Workflow Scheduling & Trigger | schedule tick / event | WorkflowScheduler | 2262 |
| F51 | Workflow Run Supervisor | workflow run started | WorkflowRunSupervisor | 2314 |
| F52 | Workflow Compiler → DAG | workflow definition | WorkflowCompiler → ExecutionDAG | 2365 |

## §5 — Planner (4-Stage) Flows (F53–F59)

| F# | Name | Trigger | Key Components | Lines |
|---|---|---|---|---|
| F53 | Stage 1 Sketch Plan | HIGH dispatch | PlannerAgent.sketch (LLM via ModelGateway) | 2427 |
| F54 | Stage 2 Expand with Tools | sketch ok | PlannerAgent.expand (capability lookup + LLM) | 2490 |
| F55 | Stage 3 Validation | expanded plan | PlanValidator (LLM + rule) | 2546 |
| F56 | Stage 4 Commit to K0 | validation pass | CommittedPlan → K0 P05 (or analog) | 2608 |
| F57 | Requirement Clarification HIL | sketch missing reqs | PlannerHIL → user clarification | 2671 |
| F58 | Plan Approval HIL | plan AMBER/RED band | PlannerHIL → user approval gate | 2726 |
| F59 | Execution Monitoring HIL | DAG step needs decision | HILCoordinator during DAG run | 2778 |

## §6 — Sub-Agent Lifecycle (F60–F65)

| F# | Name | Trigger | Key Components | Lines |
|---|---|---|---|---|
| F60 | Agent Spawn via Fabric | spawn request | AgentFactory, Fabric provider | 2836 |
| F61 | PENDING → WARMING → ACTIVE | spawn entry | AgentLifecycleFSM (warm-up) | 2899 |
| F62 | ACTIVE → IDLE → ACTIVE | inactivity / new task | AgentLifecycleFSM (idle gate) | 2963 |
| F63 | Agent Draining & Termination | shutdown / TTL | DrainController, terminate hook | 3025 |
| F64 | Sub-Agent Clarification (via DeltaBus) | agent needs input | DeltaBus emit, AggregationWindow | 3090 |
| F65 | Concierge Pending Clarifications Write | aggregated delta | SingleWriter → PENDING_CLARIFICATIONS | 3154 |

## §7 — SessionState Flows (F66–F77)

| F# | Name | Trigger | Key Components | Lines |
|---|---|---|---|---|
| F66 | Concierge → Single Writer → SessionState | any state mutation | ConciergeFSM → SingleWriter → SessionState | 3237 |
| F67 | Multi-Reader Access | any reader | RWLock, snapshot reads | 3307 |
| F68 | Agent Deltas → DeltaBus | sub-agent emit | DeltaBus producer | 3365 |
| F69 | DeltaBus → Aggregation Window → Concierge | aggregation tick | AggregationWindow, batched apply | 3413 |
| F70 | HOT → WARM Eviction | section size threshold | TieringManager (HOT→WARM) | 3476 |
| F71 | WARM → COLD Archive | age + size threshold | TieringManager (WARM→COLD) | 3540 |
| F72 | COLD → HOT Reconstruction | read miss in HOT | ColdStore retrieval, rehydrate | 3609 |
| F73 | Emergency Summarization (≥95KB) | size ≥ 95KB | EmergencySummarizer (LLM compress) | 3680 |
| F74 | Emergency Read-Only Mode | size critical | ReadOnlyGuard, write rejection | 3741 |
| F75 | Emergency Priority Shedding | overload | PriorityShedder (drop low-prio writes) | 3796 |
| F76 | Write Request → Mutation Guard | any write | MutationGuard (allowlist + schema) | 3858 |
| F77 | Eviction Engine Trigger | watermark | EvictionEngine | 3918 |

## §8 — K0 Bridge Flows (F78–F87)

| F# | Name | Trigger | Key Components | Lines |
|---|---|---|---|---|
| F78 | Memory Writer Agents → K0 | writer batch ready | MemoryWriterAgent (LLM-extracted atoms) → K0 | 3999 |
| F79 | Delta Aggregator → K0 Command | delta batch | DeltaAggregator → K0 command | 4063 |
| F80 | K0 P02 Episodic Write | write cmd | K0 P02 Episodic store | 4128 |
| F81 | K0 P03 Consolidation | bg consolidation | K0 P03 Consolidator | 4183 |
| F82 | K0 SSE → K1 EventBus | K0 SSE event | SSE Adapter → K1 EventBus topic | 4242 |
| F83 | SSE Trigger → Proactive Decision | SSE event | ProactiveDecisionEngine | 4304 |
| F84 | Session Checkpoint | checkpoint tick / boundary | CheckpointWriter → K0 | 4365 |
| F85 | Retention Expiry → Auto Deletion | retention scheduler tick | RetentionPolicy, AutoDeleter | 4425 |
| F86 | User Deletion → Soft Delete | user delete request | SoftDeleter (tombstone + grace) | 4491 |
| F87 | Grace Period Recovery | undo request in grace | RecoveryService | 4555 |

## §9 — Proactive Agent Flows (F88–F94)

| F# | Name | Trigger | Key Components | Lines |
|---|---|---|---|---|
| F88 | SSE Event → Proactive Decision | K0 SSE event | ProactiveDecisionEngine | 4626 |
| F89 | Proactive Budget Gate Check | spawn proposal | ProactiveBudgetGate (cost cap) | 4692 |
| F90 | Proactive Agent Spawn via Fabric | budget pass | Fabric.spawn (AGENT capability) | 4753 |
| F91 | Feedback Signal Collection | post-action signals | FeedbackCollector | 4828 |
| F92 | Drift Detection | metric window | DriftDetector | 4889 |
| F93 | Advisory Emission → K0 P06 | drift detected | AdvisoryEmitter → K0 P06 | 4947 |
| F94 | K0 SSE → Proactive Agent Spawner | SSE advisory | ProactiveSpawner | 5020 |

## §10 — Capability Fabric Flows (F95–F103)

| F# | Name | Trigger | Key Components | Lines |
|---|---|---|---|---|
| F95 | Capability Resolver Selection | execute() called | CapabilityResolver (domain+intent) | 5104 |
| F96 | Provider Matcher → DAG | matched providers | ProviderMatcher → ProviderDAG | 5166 |
| F97 | Affective Routing (Emotion-Aware) | affect signal in ctx | AffectiveRouter | 5247 |
| F98 | Cognitive Load Routing | cog-load estimate | CogLoadRouter | 5302 |
| F99 | QoS Integration (Token Budget) | per-call | QoSGate, TokenBudgeter | 5360 |
| F100 | Security Context (Band-Based Access) | per-call | SecurityContext, BandGuard | 5417 |
| F101 | Local MCP Server Discovery | startup / hot-reload | AutoDiscoveryMCPTransport | 5480 |
| F102 | Remote MCP Server → K0 Proxy | remote MCP call | RemoteMCPProxy via K0 | 5551 |
| F103 | MCP Capability Registration | server announces tools | CapabilityRegistry.register | 5622 |

## §11 — Model Gateway / LLM Consumer Flows (F104–F111)

| F# | Name | Trigger | Key Components | Lines |
|---|---|---|---|---|
| F104 | Model Router Load Balancing | inference request | MODEL_ROUTER (LB + fallback) | 5730 |
| F105 | Model Cache Hit/Miss | router has request | MODEL_CACHE → HUB_ROUTER on miss | 5825 |
| F106 | LLM Provider Routing | cache miss | HUB_ROUTER → OpenAI/Anthropic/Gemini | 5937 |
| F107 | Concierge LLM Inference | CONCIERGE_FSM needs LLM | ConciergePromptStack → ModelGateway | 6031 |
| F108 | Planner LLM Inference | Planner Stage 1/2 | PlannerPromptStack → ModelGateway | 6122 |
| F109 | Memory Writer LLM Inference | MW writer batch | MemoryWriterPromptStack → ModelGateway | 6219 |
| F110 | Solution Validator LLM | Stage 3 Validate | ValidatorPromptStack → ModelGateway | 6320 |
| F111 | Proactive Decision LLM | SSE-triggered analysis | ProactivePromptStack → ModelGateway | 6426 |

## §12 — Experience Layer Flows (F112–F119)

| F# | Name | Trigger | Key Components | Lines |
|---|---|---|---|---|
| F112 | Emotional Trajectory Analysis | tick: turn%25==0 | EMOTIONAL_PROCESSING | 6558 |
| F113 | Emotional Mirroring → Style Adjust | F112 output | EMOTIONAL_MIRRORING → CONCIERGE_STYLE | 6658 |
| F114 | Persona Hints Update | mirroring done | PersonaHintsUpdater → CONCIERGE_PERSONA | 6751 |
| F115 | Narrative Thread Analysis | tick: turn%20==0 | NARRATIVE_WEAVING | 6849 |
| F116 | Thread → Narrative Engine | F115 output | CONVERSATIONAL_NARRATIVE_ENGINE | 6946 |
| F117 | Narrative Arc Update | engine processed | NARRATIVE_ARC store | 7034 |
| F118 | User Needs Prediction | tick: turn%30==0 | ANTICIPATORY_RESPONSE | 7120 |
| F119 | Context Prefetch | predictions ready | ContextPrefetcher → CapabilityFabric | 7227 |

## §13 — Rhythm & Empathy / ToM Flows (F120–F127)

| F# | Name | Trigger | Key Components | Lines |
|---|---|---|---|---|
| F120 | Rhythm Patterns → Conversation Beat | every turn | ConversationBeatEstimator | 7350 |
| F121 | Dynamic Timing Adjustment | observed user behavior | RhythmPatternsTuner | 7451 |
| F122 | Pacing → Concierge FSM | beat output | PacingApplier → ConciergeFSM | 7552 |
| F123 | ToM Engine → Mental Model Update | new interaction data | TheoryOfMindEngine | 7646 |
| F124 | Mental Model Mgmt → Cognitive Load | cog-load signals | MentalModelManager | 7743 |
| F125 | Capacity Estimate → Concierge | capacity available | CapacityApplier → ConciergeFSM | 7844 |
| F126 | Predictions → Anticipation Engine | PredictiveCompletion output | ConversationalAnticipationEngine | 7940 |
| F127 | Anticipation → Speculative Execution | action queue | SpeculativeExecutor (high-conf only) | 8043 |

## §14 — Module Loader Flows (F128–F131)

| F# | Name | Trigger | Key Components | Lines |
|---|---|---|---|---|
| F128 | Module Scanner Discovery | startup / hot-reload | ModuleScanner (k1/modules/*) | 8166 |
| F129 | Tool Registry Registration | tools/contract.yaml found | ToolRegistry → CapabilityRegistry | 8281 |
| F130 | Prompt Registry Registration | prompts/*.md found | PromptRegistry | 8393 |
| F131 | Agent Registry → Factory | agents/*.yaml found | AgentRegistry, AgentFactory | 8503 |

## §15 — Event Bus & Coordination Flows (F132–F137)

| F# | Name | Trigger | Key Components | Lines |
|---|---|---|---|---|
| F132 | Capability Invoked Event | Fabric invokes capability | EventBus topic k1.capability.invoked.v1 | 8657 |
| F133 | Capability Completed Event | Fabric completes | k1.capability.completed.v1 | 8743 |
| F134 | Affect Analyzed Event | UltraBERT emotions done | k1.affect.analyzed.v1 → AFFECTIVE_CONTEXT | 8839 |
| F135 | Constraint Progress Event | ConstraintManager step | k1.constraint.progress.v1 → UI | 8935 |
| F136 | Priority-Based EventBus Delivery | any event | EventBus + WFQScheduler | 9036 |
| F137 | Priority-Based Mailbox Router | per-actor delivery | MailboxRouter (priority queues) | 9145 |

## §16 — HIL Bidirectional Flows (F138–F141)

| F# | Name | Trigger | Key Components | Lines |
|---|---|---|---|---|
| F138 | Concierge ↔ User Bidirectional | clarification round-trip | ConciergeFSM, k1.hil.clarification.v1 | 9269 |
| F139 | Planner ↔ User Bidirectional | requirement / approval | PlannerHIL, k1.hil.* topics | 9392 |
| F140 | Sub-Agents ↔ User Bidirectional | domain clarification | Sub-agent HIL via DeltaBus | 9530 |
| F141 | Orchestrator ↔ User Bidirectional | resource allocation | OrchestratorHIL | 9646 |

## §17 — Observability Flows (F142–F144)

| F# | Name | Trigger | Key Components | Lines |
|---|---|---|---|---|
| F142 | Distributed Tracing → Cognitive Trace ID | any action | TracingMiddleware (cognitive_trace_id) | 9783 |
| F143 | Metrics Aggregator → SessionState | metrics emitted | MetricsAggregator → SessionState.TELEMETRY | 9910 |
| F144 | Health Check Orchestrator | periodic / degradation | HealthCheckOrchestrator (provider health) | 10043 |

## §18 — LLM Control Plane Flows (F145–F154)

| F# | Name | Trigger | Key Components | Lines |
|---|---|---|---|---|
| F145 | Prompt Resolution → Template Lookup | consumer requests prompt by ID | PromptRegistry, file-based store | 10245 |
| F146 | Prompt Variable Injection | template loaded | VariableInjector (uses SessionState) | 10392 |
| F147 | Prompt Compilation → Model Gateway | template + vars ready | PromptCompiler → MODEL_ROUTER | 10491 |
| F148 | Dynamic Agent Prompt Registration | AgentFactory spawn | PromptTemplateStore.register | 10600 |
| F149 | LLM Output → 3-Tier Validation Pipeline | provider returns raw | OutputValidator (Tier1 syntax / Tier2 schema / Tier3 semantic) | 10697 |
| F150 | Schema Registry → Agent Schema Lookup | validator needs schema | SchemaRegistry (FlatBuffer per agent) | 10897 |
| F151 | Hallucination Detection → SessionState X-Ref | Tier3 semantic | HallucinationDetector vs SessionState | 11009 |
| F152 | Validation Fallback → Retry/Repair/Reject | any tier fails | FallbackController (retry/repair/reject) | 11117 |
| F153 | Dynamic Agent Schema Registration | spawn with custom schema | SchemaCompiler.register | 11243 |
| F154 | Core vs Generic Payload Schema Selection | validator selecting schema | SchemaSelector (core/generic) | 11359 |

---

## Subsystem Cross-Reference (for gap analysis next pass)

- **Concierge FSM**: F01–F03, F08–F10, F107, F122, F125, F138 (+ writes to F29–F32, F65, F66)
- **UltraBERT**: F11–F32, F134
- **Capability Fabric**: F33–F38, F95–F103, F132–F133
- **Orchestrator**: F05, F09, F43–F52, F141
- **Planner**: F06, F53–F59, F108, F139
- **Memory Writer (MW)**: F78–F81, F109
- **K0 Bridge**: F35, F39–F42, F78–F87, F94
- **Model Hub / Gateway**: F104–F111, F147
- **SessionState (Single Writer + Tiering)**: F29–F32, F66–F77, F143
- **Bus / EventBus / Mailbox**: F132–F137, F142
- **HIL**: F02, F49, F57–F59, F64–F65, F138–F141
- **Proactive / Learning**: F83, F88–F94, F111
- **Experience Layer (periodic)**: F112–F119
- **Rhythm/Empathy/ToM**: F120–F127
- **Module Loader**: F128–F131
- **LLM Control Plane (prompts/validation)**: F145–F154
- **Observability**: F142–F144
- **CRISIS / Safety**: F07, F19, F31, F100

## Notes for Gap-Analysis Pass

1. Doc precedes the current Concierge implementation — class names like `CONCIERGE_FSM`, `MODEL_ROUTER`, `HUB_ROUTER` are aspirational. Map to today's `ConciergeController`, `ModelHubService`, `ModelGatewayAdapter`, `BudgetEnforcer`, etc.
2. Several flows describe components NOT yet built: `EntropyMinQuestionPlanner`, `TinySanityArbiter`, `ConstraintManager`, `WorkflowScheduler`, `AgentLifecycleFSM`, `EmergencySummarizer`, `RetentionPolicy`, `DriftDetector`, `AffectiveRouter`, `CogLoadRouter`, `RhythmPatternsTuner`, `TheoryOfMindEngine`, `ToM/Anticipation`, full `OutputValidator` 3-tier pipeline.
3. Flows already proven in the current kernel smoke (test mode + Gemini hub mode): F01, F04 (LOW path), F08, F33, F66 (single-writer), F107 (Concierge LLM), F132/F133 (capability events), F142 (cognitive_trace_id), partial F78 (MW SessionBatchDispatcher → atoms=0 indicates F109 wiring incomplete).
4. Tier degradation cascade (HIGH→MED→LOW→canned) and the 4 circuit breakers (CB_MODEL/PLANNER/ORCHESTRATOR/FABRIC) referenced in M10 plan are NOT explicit F-numbered flows here but underpin F04/F05/F06/F07.
5. Doc has 18 sections with a final FLOW SUMMARY table at L10199 that confirms total = 154. No flows discovered outside the F01–F154 range.
