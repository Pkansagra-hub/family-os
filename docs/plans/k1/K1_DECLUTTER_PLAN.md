# K1 Declutter Plan — Redundant Control Planes

Date: 2026-05-20

Status: Read-only audit synthesis. No production code changes are implied by this file. Output of 8 parallel folder-by-folder subagent audits over `k1/concierge/{prompt,fsm,actors,react,tools}`, `k1/fabric/`, `k1/planner/` + `k1/orchestrator/`, and `k1/{kernel,bus,sessionstate,selfmodel}` + `k1/concierge/{session,factory,config}`.

## Target Architecture (One Sentence Per Owner)

- **Concierge** is one thing: Front LLM + Back LLM acting as a single conversational mind that writes natural sentences.
- **Fabric** owns the tool surface, capability registry, capability discovery, safety bands (GREEN/AMBER/RED/CRISIS), provider eligibility, and output validation.
- **Planner** is one LLM call that plans.
- **Orchestrator** is one LLM that follows the plan and works with the user to complete it.
- **FSM** tracks user-visible lifecycle only (listening → dispatching → companioning → clarifying → delivering). Nothing else.
- **Bus** is pub/sub. No hot-path middleware. No always-on dead-letter accumulator.

Everything else is creep. The job of this plan is to name every creep, name who currently owns it, name who should own it, and name what to strip.

## The Core Problem

Right now the LLM has to reason across roughly **8 simultaneous control planes** that disagree with each other:

1. **Prompt sections** (REACT_RHYTHM, DISPATCH_RULES, SAFETY_HITL, DOMAIN_RULES, ANTI_PATTERNS × 7, COGNITIVE_DISCIPLINE, PROACTIVE_INTELLIGENCE, INTERRUPT_RULES, EMOTIONAL_CALIB, …).
2. **Prompt mode allowlists** (`TOOL_ALLOWLIST` per `PromptMode`, 10 modes).
3. **Tool schema actor field** (front / back / both, on every schema).
4. **Dispatcher tier allowlists** (`FRONT_TIER_ALLOWLISTS`, `BACK_TIER_ALLOWLISTS`).
5. **ReAct preflight guards** (`front_dispatch_should_stay_conversational`, `context_read_gap_requires_dispatch`, capability binding, spin nudges, BackExecutionPlan).
6. **FSM arbiter + transition tables** (intent classification, domain/entity overlap scoring, cancel/defer/modify-inflight branches that fire on signals that are never populated).
7. **Fabric policy** (`SecurityContext`, `HardFilter`, `AffectiveRouting`, `CognitiveLoadRouting`, `QoSIntegration`, `ToolScope`).
8. **Planner + Orchestrator guards** (`MicroReplanCheckpoint`, `FailureReplanCheckpoint`, `OutputSchemaGuard`, validate-service LLM arbiter, plan FSM micro-replan states, workflow scheduler/supervisor/cross-workflow recursion).

Each plane evaluates the same decision (dispatch? safety? tool allowed? complete?) with different inputs and different rules. The LLM is asked to write a natural sentence inside that storm.

The fix is one owner per decision, and that owner is named below.

## Decision Domains: Current vs Target Ownership

| Decision | Currently Owned By (creep) | Should Be Owned By |
|---|---|---|
| What `dispatch_task` means / when to call it | prompt `REACT_RHYTHM` + prompt `DISPATCH_RULES` + `react/capability_routing.py` keyword classifier + `react/loop.py` preflight reject + actor cancel/normal split + Back STEP 5 | Front prompt (1 paragraph). LLM decides. No preflight veto. |
| Which tools Front can call | prompt `TOOL_ALLOWLIST[mode]` + `dispatcher._FRONT_SIMPLE` + schema `actor` field + ReAct preflight | Fabric `tools_granted` for the session/turn. One set, derived from Fabric. |
| Which tools Back can call | prompt `back_prompt.available_tools_note` + `schemas_back.BACK_TIER_ALLOWLISTS` + `back.py:_filter_back_tools` + `back.py:_maybe_rebind_back_dispatcher` | Fabric `tools_granted` for the Back agent. |
| Safety band (GREEN/AMBER/RED/CRISIS) | prompt `SAFETY_HITL` + prompt `DOMAIN_SAFETY_FLOORS` + Back prompt STEP 5 + `dispatcher` Step 4 + FSM `_check_crisis_keywords` + `back.py:_effective_task_safety_band` + Fabric `SecurityContext` + Fabric `HardFilter` | Fabric `SecurityContext` only. One hard gate. |
| Capability discovery / matching | Back prompt CAPABILITY NAMING + `react/capability_routing.bind_capability` (multi-stage pipeline) + `react/loop._execute_collection_read_plan` + Fabric `RetrievalEngine` | Fabric `RetrievalEngine.discover_capabilities`. LLM calls it. |
| Capability schema definitions | `schemas_fabric.DISCOVER_CAPABILITIES_SCHEMA.returns` (15-field hand-transcription) + Fabric `CapabilityContract` | Fabric `CapabilityContract`. Schema derived from it. |
| Dispatch coverage / "is task complete" | `react/back_execution_plan.BackExecutionPlan` (intent ledger blocking `submit_result`) + Back LLM `final_answer` | Back LLM. No second-opinion ledger. |
| HITL approve / reject | prompt `SAFETY_HITL` (Front says AMBER = confirm) vs Back `back_prompt` STEP 5 (explicit request = no confirm) + `front.py:_hitl_answer_rejects_background_task` + FSM `CLARIFYING_WORKER` + `HumanInTheLoopService` + `protocols/hitl_flow` | FSM lifecycle + HILService. Front LLM phrases the question/response. |
| HITL protocol version (legacy vs unified) | `front.py` adjudicates per-envelope | `HumanInTheLoopService` / `front_hil_envelope.py` |
| Intent classification (cancel / defer / modify / new) | `fsm/arbiter.ConversationArbiter` (with dead overlap-scoring branches) + `fsm/interrupt_handler.InterruptClassifier` (vestigial, never called) + prompt `INTERRUPT_RULES` | Front LLM. FSM only acts on the LLM's cognitive-tool writes. |
| Confirmation routing ("yes please" attaches to active task) | FSM arbiter (currently misroutes) + prompt `INTERRUPT_RULES` + actor logic | FSM (deterministic short-circuit: if active task/HIL exists and input is a confirmation/correction, route to active task). |
| Tool start/complete state transitions | FSM `TOPIC_TOOL_STARTED → PROGRESSING → TOPIC_TOOL_COMPLETED → COMPANIONING` | Observability only. FSM ignores tool events. |
| Output stripping (reasoning prefix / system blocks / Back frame leak) | `front.py:_strip_leaked_reasoning` + `_strip_leaked_system_blocks` + `_strip_leaked_back_frame` | LLM gateway / `LLMOutputValidator`. |
| Family/persona context rendering | `front.py:_extract_family_context` + `prompt/builder` `SECTION_RENDERERS["persona"]` + selfmodel `GroundingCapsule.family_block` | Prompt builder. One renderer. Conditional on relevance. |
| Identity grounding | OPP-7 `DynamicIdentityContext.to_prompt_block` + selfmodel `GroundingCapsule.self_block` (both injected when both wired) | One path. Pick OPP-7 or selfmodel; delete the other. |
| Execution profile selection | `back.py:_execution_profile_selection_for_task` + prompt `back_profiles` + Fabric back_profiles registry | Fabric. Back actor sees the result, not the selection logic. |
| Affect / cognitive-load provider boosts | `fabric/policy/affective_routing.py` (+0.1 for empathetic-tagged providers that don't exist) + `fabric/policy/cognitive_load_routing.py` (boosts that match no flags) | Delete. Boosts apply to nothing. |
| Cost/latency provider ranking | `fabric/retrieval/soft_ranker.W_COST_LATENCY` + `fabric/policy/qos_integration.QoSIntegration` | `SoftRanker` only. Drop QoSIntegration. |
| FAISS / embedding retrieval | `fabric/retrieval/embedding_index.py` (required `IEmbeddingPort`) | Feature-flagged off. Name+domain `HardFilter` + `SoftRanker` is enough. |
| Agent runtime build | `fabric/core/agent_builder.BuildAgentHandler` (8-step runtime DAG step) | Orchestrator / `agent_factory`. Fabric keeps only `AgentSpecValidator` + `AgentComposer`. |
| Native tool contract validation | `manifest_translator.register_definition(skip_validation=True)` default + `module_loader` hot-reload `skip_validation=True` (6 callsites) | `ContractValidator` mandatory. Add `LOCAL` to `_VALID_PROVIDER_TYPES`. |
| Plan re-planning mid-execution | `planner/plan_fsm.MICRO_SKETCH/MICRO_EXPAND/MICRO_VALIDATE` + `sketch_service.micro_execute` + `expand_service.micro_execute` + `validate_service.micro_execute` + `orchestration/guards/micro_replan.MicroReplanCheckpoint` + `orchestration/guards/failure_replan.FailureReplanCheckpoint` (output ignored — plan-swap not implemented) | Delete the entire shadow pipeline. If re-plan is needed, call sketch again. |
| Plan validation | `validate_service` Phase 1 (deterministic) + Phase 2 LLM arbiter + HIL approval | Phase 1 only. Drop the LLM arbiter and HIL approval (Concierge owns user mediation). |
| Output schema validation | `orchestration/guards/output_schema_guard.OutputSchemaGuard` + Fabric `output_validation/pipeline` + capability `CapabilityContract.output` | Fabric `output_validation`. |
| Workflow scheduling / supervision / recursion | `planner/workflows/{workflow_scheduler,workflow_supervisor,cross_workflow_resolver,gap_detector,workflow_compiler,workflow_registry,persistence}` | Feature flag `ENABLE_WORKFLOW_ENGINE=false` for V1. Entire subsystem is V2. |
| Bus topic validation | `bus/factory.create_local_ordered` auto-wires `TopicValidationMiddleware` | Opt-in `debug_topic_validation=True`. Off in production hot path. |
| Dead-letter accumulation | `enable_dead_letter_consumer: bool = True` (default) + `fsm/dead_letter_consumer.py` | Off by default. Logs are enough. |
| Config flag ownership | `KernelConfig` + `ConciergeConfig` (full copy-constructor with silent default drift between `delta_batch_window_ms`, `enable_ledger_recovery`) | `KernelConfig` only. `ConciergeFactory` accepts it directly. |
| Per-session vs shared Fabric | per-session Fabric P3 in `KernelService` | Shared Fabric. Per-session is a view if needed. |
| HIL lifecycle ownership | `HumanInTheLoopService` Tier-1 + `ConciergeFactory` builds bus callbacks + per-session destroy paths that can shut down the shared service | Shared service. Sessions hold handles, not lifetimes. |
| Selfmodel capsule rendering | `GroundingCapsuleBuilder.build()` always emits all 13 blocks (actor, family, rules, capabilities, footer, self, preferences, hobbies, goals, routines, space_graph, context, conscience) | Per-turn `CapsuleRenderFlags`. Identity + rules + footer minimum. Conscience / space_graph / hobbies / routines only when relevant. |
| Signature chain validation | `Ed25519SignatureChainValidator` walks full ancestor chain on every `SituationFrameComposer.compose()` call | Boot-time + per-session cache. |
| Family context injection | `front.py:_extract_family_context` unconditionally in STANDARD / INTERRUPT | Conditional on persona/domain relevance. Skip for "what's 2+2" and similar. |
| BackPool concurrency | `concierge/actors/back_pool.BackPool` (worker leasing, session limits, overflow queue) | Coordinator holds `dict[task_id, asyncio.Task]`. Delete BackPool. |
| Back topic routing | `concierge/actors/back_router.BackTopicRouter` (second dispatch table over coordinator's topic handling) | Coordinator inline. Delete BackTopicRouter. |
| Cancel keyword detection | `fsm/arbiter._DEFAULT_CANCEL_KEYWORDS` + `fsm/arbiter._CANCEL_ALL_KEYWORDS` + `fsm/interrupt_handler.InterruptClassifier.CANCEL_KEYWORDS` (dead) | Front LLM cognitive write. |
| Recall vs no-recall on greetings | prompt `PROACTIVE_INTELLIGENCE` (MUST recall on broad questions) + prompt `COGNITIVE_DISCIPLINE` (NOT for greetings) — both in STANDARD | One rule. Or remove both and let LLM decide. |

## Explicit Contradictions In The Live System

Every row below is a place where the LLM gets two contradictory instructions in the same turn.

1. **AMBER approval.** Front prompt `SAFETY_HITL`: "AMBER (confirm before acting): Book, purchase, send message… Dispatch with the expectation that the system will ask for approval." Back prompt STEP 5: "PRACTICAL RULE: If the user said 'send notification to Nana Liz', 'start the washing machine', 'add to grocery list', or any explicit action verb — that IS the approval. Execute it. Do NOT ask again." Front promises a confirmation Back will not deliver.
2. **Dispatch verbs.** `REACT_RHYTHM` and `DISPATCH_RULES` give two different but authoritative lists of "what to dispatch."
3. **Front anti-pattern vs dispatcher allowlist.** `ANTI_PATTERNS_FULL` tells the LLM "Front does not call discover_capabilities or invoke_capability directly." `dispatcher.FRONT_TIER_ALLOWLISTS` already makes the calls impossible. The prompt wastes tokens forbidding what the runtime already blocks.
4. **Mandatory recall vs forbidden recall.** `PROACTIVE_INTELLIGENCE`: "On broad questions ('what's today look like?'), you MUST call `recall_memory` BEFORE generating your response." `COGNITIVE_DISCIPLINE`: "Do NOT call `recall_memory` for pure greetings, acknowledgements, lightweight banter, or emotional check-ins." "How's the morning?" is both.
5. **Belief vs live record.** Back STEP 1: "If reference_context contradicts a high-confidence belief (>= 0.8), prefer the belief." Back STEP 3: "Live records are owned by capabilities… do NOT answer from `recall_memory`." Stale high-confidence beliefs about live records have no tiebreaker.
6. **AFFECT_TONE_BLOCKS vs EMOTIONAL_CALIB.** Both injected in STANDARD. Same instruction restated in different words.
7. **OPP-7 identity_block vs selfmodel self_block.** Both injected when both wired. Same identity stated twice.
8. **Front dispatch preflight vs FSM mode.** ReAct `front_dispatch_should_stay_conversational` vetoes dispatch based on raw keywords ("recipe", "lunch", "cook"). FSM mode and prompt already routed the turn to STANDARD with `dispatch_task` declared. The veto fires after the LLM made a legal choice.
9. **BackExecutionPlan vs Back LLM.** `BackExecutionPlan.can_submit_complete()` blocks `submit_result(complete)` when the original dispatch's `intents[]` ledger is not covered, even when Back has actually completed the work and explained it in `final_answer`. No repair path.
10. **FSM TOOL_STARTED guard mismatch.** `FULL_GUARD_TABLE` marks `TOPIC_TOOL_STARTED` as `_O` (OBSERVE) in DISPATCHING but `_T` (TRANSITION) in COMPANIONING. The same event is observation in one state and a state mutation in another.
11. **MODIFY_INFLIGHT structurally dead.** `_build_arbiter_input()` fills only `safety_band`; `domain_context` defaults to `"general"` and `entities` defaults to `[]`. `domain_overlap()` and `entity_overlap()` therefore always return `0.0`. The MODIFY_INFLIGHT branch in `ConversationArbiter.classify()` cannot fire on a normal-turn path.
12. **Three replan-timeout values.** `OrchestratorConfig.max_micro_replans = 1`, `_MICRO_REPLAN_TIMEOUT_S = 10.0` hardcoded in both `micro_replan.py` and `failure_replan.py`, and `PlannerConfig.micro_replan_timeout_ms = 10_000`. Same timeout, three places.
13. **Two config defaults silently diverge.** `KernelConfig.delta_batch_window_ms = 500`, `ConciergeConfig.delta_batch_window_ms = 100`, and `from_kernel_config()` does not copy this field. `KernelConfig.enable_ledger_recovery = False`, `ConciergeConfig.enable_ledger_recovery = True`, and the constructor `getattr` default flips it back to False.
14. **FailureReplanCheckpoint writes a key the executor ignores.** Guard fires, sets `metadata["new_plan"]`. `DAGExecutor` consumption "is a separate (downstream) milestone." Live code, dead output.

## Dead Branches Currently Loaded

These exist, run, and have zero effect on behavior.

- `fsm/interrupt_handler.InterruptClassifier` — built, exposed, reset on session close, never `.classify()` called after M5.
- `fsm/interrupt_handler.ProactiveWakeHandler` — `record_wake()` called for logging only, `should_wake()` never consulted.
- `fsm/controller._try_chain_into_current_response()` — second statement is unconditional `return False`.
- `fsm/arbiter.InflightContext.pool_*` fields — populated, ignored by `classify()`.
- `fsm/arbiter` `MODIFY_INFLIGHT` priority-4 branch (see contradiction 11).
- `fsm/arbiter.DEFER` on clean-turn path — `has_inflight=False` so the branch never fires.
- `fabric/policy/affective_routing` `+0.1` empathetic boost — no provider has the tag.
- `fabric/policy/cognitive_load_routing` `+0.1/+0.05` fast/comprehensive boost — no provider has the flag.
- `BUDGET_LIMITS` static dict in `dispatcher.py` — overridden by `get_config().tools.budget_limits`.
- `parallelism.py` — admitted compatibility shim that just delegates to `task/parallel_safety`.
- `enable_grounding` / `enable_spatial` flags — partial wiring, no production path.
- `system_bus_enabled`, `otel_enabled`, `allow_planner_passthrough`, `allow_dispatch_passthrough` — declared, never branched on (or test-only).

## Concierge: What To Strip So Front + Back Become Voices

### Front prompt (`k1/concierge/prompt/`)

Strip:
- `REACT_RHYTHM` full + `REACT_RHYTHM_REDUCED` (LLM does not drive the loop).
- `DISPATCH_RULES` full (duplicates REACT_RHYTHM + capability_routing markers).
- `STATE_INTERP` + `STATE_INTERP_CLARIFY` + `STATE_INTERP_TASK` + `STATE_INTERP_PRESENT` (LLM gets typed SS data; decoding tables are noise).
- `COGNITIVE_DISCIPLINE` + `COGNITIVE_DISCIPLINE_REDUCED` (tool guidance lives in tool descriptions).
- `PROACTIVE_INTELLIGENCE` (collapse to 3 sentences in IDENTITY).
- `EMOTIONAL_CALIB` (redundant with runtime-injected `AFFECT_TONE_BLOCKS`).
- `SAFETY_HITL` Front (Fabric enforces; keep one sentence on HITL phrasing).
- `DOMAIN_RULES` + `DOMAIN_SAFETY_FLOORS` + `DOMAIN_APPLICABLE_MODES` (Fabric policy).
- `INTERRUPT_RULES` (FSM already handed the LLM the right mode).
- 6 mode-specific anti-pattern subsets (`_CLARIFY`, `_HITL`, `_PRESENT`, `_WEAVE`, `_CANCEL`, `_ERROR`) — keep only `ANTI_PATTERNS_FULL`.
- `MAX_ITERATIONS_TABLE` + `CRISIS_ITERATIONS_TABLE` as separate tables — collapse to one.
- `AffectModifiers.examples_count_override` / `.vocabulary_tier` / `.history_window_delta` micro-knobs.
- `TOOL_ALLOWLIST` in `mode.py` — replaced by Fabric `tools_granted`.
- 11-mode `SS_READ_CONFIGS` — collapse to `full` / `task` / `slim`.
- `back_profiles.py` profile-scoring micro-router — pure passthrough for contract-loaded data.

Keep:
- `IDENTITY` + `PERSONALITY` + `NATIVE_INTELLIGENCE`.
- `AFFECT_TONE_BLOCKS` runtime-injected.
- One 3-sentence dispatch trigger.
- `COMMITMENT_TRACKING` collapsed to 1 paragraph.
- `WEAVE_PROTOCOL`.
- `SCENARIO_DATA_TEMPLATES` for PRESENT / WEAVE / HITL_RELAY / HITL_RESOLVE / ERROR.
- `CLARIFY_DEPTH_BLOCKS` depths 1 and 2 only.
- One consolidated 10-15 bullet ANTI-PATTERNS list.

### Back prompt

Keep: IDENTITY (executor), 3-line ReAct pattern, one `discover_capabilities` paragraph, RESULT FORMAT, BUDGET, TASK DISPATCH context block.

Strip: STEP 1…STEP 8 8-step protocol; CAPABILITY NAMING long-form; mandatory-discover language when Fabric returned candidates; STEP 5 safety check (Fabric owns); STEP 1 vs STEP 3 belief-vs-live conflict.

### Actors (`k1/concierge/actors/`)

Strip from `front.py`:
- `_hitl_answer_rejects_background_task` and its call site (FSM owns).
- `_build_resolution_frame` / `_build_resolution` / `_approval_decision_from_text` / `_match_hil_option` (move into `front_hil_envelope` / `protocols/hitl_flow`).
- `_strip_leaked_reasoning` / `_REASONING_PREFIXES` / `_strip_leaked_system_blocks` / `_SYSTEM_BLOCK_RE` / `_strip_leaked_back_frame` (LLM gateway / validator).
- `_extract_family_context` (prompt builder `SECTION_RENDERERS["persona"]`).
- `_OBSERVABILITY_TOPICS` frozenset (bus filter).
- Cancel/normal dispatch split loop (dispatcher).
- WEAVE / HITL_RELAY degenerate text fallback (prompt or react loop).
- Per-envelope HIL protocol-version adjudication (`HumanInTheLoopService`).

Strip from `back.py`:
- `_filter_back_tools` + `BACK_TIER_ALLOWLISTS` reference (Fabric `tools_granted`).
- `_maybe_rebind_back_dispatcher` (dispatcher pre-configured at coordinator).
- `_effective_task_safety_band` + `_normalize_safety_band` (Fabric).
- `_execution_profile_selection_for_task` + `_persist_*` + `_record_*` (Fabric).
- Multiple `_bind_tool_context()` calls — one at coordinator handoff.

Delete:
- `back_pool.py` (use `dict[task_id, asyncio.Task]`).
- `back_router.py` (coordinator inlines 4-topic match).

### ReAct (`k1/concierge/react/`)

Strip:
- `capability_routing.front_dispatch_should_stay_conversational` + `_CONVERSATIONAL_WORK_MARKERS` + `_EXTERNAL_WORK_MARKERS` + `_VAGUE_ADVISORY_ACTION_STARTS` + the preflight intercept in `loop.py` (~L1748-1775).
- `capability_routing.context_read_gap_requires_dispatch` + `synthesize_dispatch_task` + `_front_policy_dispatch`.
- `back_execution_plan.py` (entire file: `BackExecutionPlan`, `BackExecutionWorkItem`, `record_*`, `submit_rejection_payload`, `merge_submit_args`) and the gate in `loop.py` (~L1584-1613).
- Back capability spin nudge (`loop.py` ~L1975-2001).
- Front `recall_memory` spin nudge (`loop.py` ~L1944-1966).
- `_back_progress_nudge` 7-branch state-aware nudge.
- `_execute_collection_read_plan` / `_execute_collection_mutation_plan` / `_build_collection_*_plans` / `_ContractPlanExecution` / `_CollectionReadPlan` / `_CollectionMutationPlan` and all helpers (~300 lines mini-orchestrator).
- `capability_routing.bind_capability` multi-stage discovery / ambiguity / recovery pipeline.
- `_back_discovery_payloads` + `_back_capability_candidates_seen` (existed only for the deleted spin nudges).
- `_seed_back_*` scanning loops at init.
- Force-submit nudge injection before last Back iteration.
- Safety short-circuit `_SAFETY_REASONS` scan (Fabric already blocked; let the LLM respond to the error).

Keep:
- LLM call, dispatch tools, observe, repeat.
- Budget exhaustion guard.
- Repeated same tool+args ≥ 3 → `loop_degenerate` (real loop primitive).
- Empty response ≥ 3 → `loop_degenerate`.
- Parallel tool classification + `asyncio.gather` (when > 1 non-terminal tool call).
- Tool timeout `asyncio.wait_for`.
- `completed_tool_call_ids` dedup for checkpoint resume.
- `_drain_control_events` Back cancellation control queue.
- Streaming path.
- `checkpoint.py` (correct and minimal already).
- `control.py` typed markers.

Net: ReAct shrinks from ~2400 to ~200 lines and stops fighting the LLM.

### FSM (`k1/concierge/fsm/`)

Strip:
- `InterruptClassifier` (vestigial after M5).
- `ProactiveWakeHandler` (only `record_wake` is used, inline a log line).
- `PROGRESSING` state; remove `TOPIC_TOOL_STARTED → PROGRESSING` and `TOPIC_TOOL_COMPLETED → COMPANIONING` transitions; `tool.started` / `tool.completed` become observability no-ops.
- `MODIFY_INFLIGHT` scoring (`domain_overlap`, `entity_overlap`, `_apply_recency_decay`, `is_short_input`, `_RELATED_DOMAINS`) — dead on normal paths.
- `_try_chain_into_current_response` (unconditional False).
- `InflightContext.pool_*` fields (Arbiter ignores them; move to `WeaveSignal`).
- `response_final_table.py` 13 branches — collapse to 4 core transitions + CLARIFYING_WORKER single STAY.
- Second `route_task_sync()` call + inline `PassthroughPlannerStub` fallback (move to orchestrator module).
- Arbiter call on LISTENING clean-turn (always returns `PARALLEL_NEW` with zero scores; replace with: if `safety_band == RED` → crisis response, else → Front).
- Cancel keyword tables (Front LLM cognitive write).
- Dead-letter accumulator default-on.

Keep: 8 states only — `LISTENING`, `DISPATCHING`, `COMPANIONING`, `CLARIFYING_USER`, `CLARIFYING_WORKER`, `DELIVERING`, `CANCELLING`, `WEAVING` (+ `PROACTIVE_WAKE` if needed). `FrontLock`, dead-letter publishing (logs only), history writes, turn id tracking, `_active_task_ids`, idempotency ledger, crisis short-circuit.

Net: ~400 lines of scoring code gone, conceptual confusion gone.

### Tools (`k1/concierge/tools/`)

Strip:
- `dispatcher.py` Step 4 safety-band check (Fabric `SecurityContext`).
- `dispatcher.py` `BUDGET_LIMITS` static dict (overridden by config).
- `dispatcher.py` `FRONT_TIER_ALLOWLISTS` (Fabric `tools_granted`).
- `schemas_back.py` `BACK_TIER_ALLOWLISTS` (same).
- `schemas_fabric.py` `returns` block of `DISCOVER_CAPABILITIES_SCHEMA` and `INVOKE_CAPABILITY_SCHEMA` (derive from `CapabilityContract`).
- `recovery_contract.CapabilityParamContract` (read directly from `CapabilityContract.required_inputs`).
- `parallelism.py` (delete; callers import from `task.parallel_safety`).

Keep:
- `FRONT_TOOL_SCHEMAS` cognitive 6 + read 2 + control 1 (Concierge-native, write SS).
- `DISPATCH_TASK_SCHEMA`, `UPDATE_SESSION_BUNDLE_SCHEMA`.
- `ToolDispatcher` Steps 0-3 (policy gate, allowlist check from Fabric `tools_granted`, budget, schema validation).
- `ToolResult` / `result_protocol`.
- `ToolContext` (session dep injection).
- `TOOL_REGISTRY` for cognitive + read tools (they write SS, not Fabric concern).
- `ToolRecoveryContract.to_dict` + `ask_human_recovery_from_tool_data` (kernel HIL escalation), gut the param contract.

## Fabric: What It Should Own (And What To Strip)

### Keep (the minimum Fabric surface)

- `core/registry.CapabilityRegistry` — sole source of truth.
- `core/contract_validator.ContractValidator` — hard gate on every `register()`.
- `core/module_loader.ModuleLoader` — lifecycle + hot-reload.
- `manifest_translator.build_contract` + `register_definition`.
- `retrieval/hard_filter` + `retrieval/soft_ranker` + `retrieval/top_k_selector` + `retrieval/retrieval_engine`.
- `core/discovery_tools` MCP wrappers.
- `policy/security_context.SecurityContext` — `user_band >= contract.safety_band_min`, `tools_granted` scoping, rate limits.
- `policy/security_context.MetaOperationValidator` — agent-creation gates.
- `policy/tool_scope.ToolScope` — per-sub-agent invocation scoping.
- `output_validation/pipeline.OutputValidationPipeline`.
- `contracts/` — four contract parsers + JSON schemas.
- `core/agent_builder.AgentSpecValidator` + `AgentComposer` (pure validators / builders).

### Strip

- `policy/affective_routing.py` — empathetic-tag boost matches no providers. Delete file; remove from `PolicyEngine` compose.
- `policy/cognitive_load_routing.py` — fast/simple boost matches no flags. Delete.
- `policy/qos_integration.py` — fold into `SoftRanker.W_COST_LATENCY` (already exists).
- `core/agent_builder.BuildAgentHandler` (8-step runtime DAG step) — move to `k1/orchestrator/` or a dedicated `agent_factory/`.
- `retrieval/embedding_index.py` FAISS — feature-flag behind `FABRIC_EMBEDDING_ENABLED=true`; default path is name+domain.

### Fix (mandatory, blocks declutter)

- `manifest_translator.register_definition(skip_validation=True)` default → change to `False`. Add `"LOCAL"` to `_VALID_PROVIDER_TYPES` in `core/contract_validator.py` first. Without this fix, every native family tool bypasses validation and the schemas-vs-validator-vs-dispatcher drift cannot be detected.
- `core/module_loader.py` hot-reload 6 callsites of `skip_validation=True` → remove or add lightweight name + safety_band re-check.

## Planner + Orchestrator: One LLM Plans, One LLM Executes

### Strip

- `stages/validate_service.py` Phase 2 LLM arbiter + HIL approval (3rd LLM call per plan; second HIL path).
- `plan_fsm.py` micro-replan states (`MICRO_SKETCH`, `MICRO_EXPAND`, `MICRO_VALIDATE`).
- `sketch_service.micro_execute` + `expand_service.micro_execute` + `validate_service.micro_execute`.
- `orchestration/guards/micro_replan.MicroReplanCheckpoint` — feature-flag off.
- `orchestration/guards/failure_replan.FailureReplanCheckpoint` — delete entirely (output ignored; plan-swap not implemented).
- `orchestration/guards/output_schema_guard.OutputSchemaGuard` — Fabric owns schema.
- `workflows/` entire subsystem behind `ENABLE_WORKFLOW_ENGINE=false`: `workflow_scheduler`, `workflow_supervisor`, `cross_workflow_resolver`, `gap_detector`, `workflow_compiler`, `workflow_registry`, `persistence/`.
- `PlannerConfig` micro-replan budget fields (5 fields).
- `OrchestratorConfig` workflow section (8 fields), gap scan section, plan cache.
- `_MAX_TOOL_ROUNDS = 6` hardcoded in both `SketchService` and `ExpandService` — collapse to one config field.

### Keep

- `sketch_service.execute` — one LLM call with tool use to discover + sketch.
- `expand_service.execute` — one LLM call to parameterize the sketch.
- `validate_service` Phase 1 (deterministic structural: DAG cycle, capability existence, param type).
- `commit_service` — plan assembly + WAL persist.
- `orchestration/dag_executor` — wave-parallel execution, `MAX_WAVES`, `MAX_STEPS`, semaphore, `cancel_dependents`, compensation.
- `orchestration/guards/{concurrency_guard, conditional_eval, execution_monitor}`.
- `plan_fsm.py` — 5 main states + terminal states. Drop micro-replan states.
- `orchestrator_service` mailbox + `dispatch_high` (plan request/receive). Remove `dispatch_medium` if it duplicates Concierge direct-execution; otherwise clarify ownership boundary.

Net: from ~25 knobs across two configs to ~6.

## Kernel + Bus + Session-State + Selfmodel

### Strip

- Delete `ConciergeConfig` as a separate class. `ConciergeFactory` accepts `KernelConfig` directly. Eliminates the silent default drift on `delta_batch_window_ms` and `enable_ledger_recovery`.
- Remove `TopicValidationMiddleware` from `bus/factory.create_local_ordered()` default. Opt-in `debug_topic_validation=True`.
- Flip `enable_dead_letter_consumer: bool = False` default. Logs are sufficient.
- Cache `Ed25519SignatureChainValidator` result per session — deterministic for `(constitution_id, version)`.
- Add `CapsuleRenderFlags` to `GroundingCapsuleBuilder.build()`. Gate `conscience`, `space_graph`, `hobbies`, `routines` on relevance. Split `build_minimal()` (identity + rules + footer) from `build_full()`.
- Collapse dual identity: pick OPP-7 `identity_block` OR selfmodel `self_block`. Delete the other path.
- Make `_extract_family_context` conditional on `persona.is_personalized` flag + domain relevance. Skip on math/time/factual Q&A.
- Remove flags: `system_bus_enabled`, `allow_planner_passthrough`, `allow_dispatch_passthrough`. Make `otel_enabled` env-var-only.
- Collapse `enable_grounding` + `enable_spatial` into `enable_self_model`.

### Keep

- `KernelService` 8-phase startup (Tier-1 shared, Tier-2 per-session).
- `LocalBus` + `TopicTrie` + WFQ.
- `BusFactory.create_local_ordered()` (without auto-middleware).
- `SessionStateManager` + HOT sections (`control`, `history_active`, `task_state`).
- `TemporalSection` HOT, refresh per turn but only render projection when turn contains temporal language.
- `ConciergeRuntime` + FSM controller (slimmed to 8 states).
- `GroundingCapsuleBuilder` with flags.
- `SituationFrameComposer` on-demand.
- Boot-time `Ed25519SignatureChainValidator`.
- `HumanInTheLoopService` Tier-1 shared, sessions hold handles.
- `ConciergeFactory.create_with_ports`.

### Session-state sections (`k1/sessionstate/sections/`)

Strip / defer:
- `NarrativeArc` story-structure fields in hot state.
- `ScoreboardSection.salience_map` if referents already carry salience.
- Full `AffectiveNowSection` circumplex if no consumer reads it.
- `TemporalSection` duplicate `turn_id` and `last_turn_id` fields.
- Single-turn provenance lists — telemetry, not state.

Fix: Production `k1/sessionstate/sections/*` should not import generated FlatBuffers from `poc.k1_poc`. Move or regenerate generated bindings under `k1/sessionstate/generated/`.

## Execution Order

### Phase 0 — Unblock validation (mandatory first)

- Add `"LOCAL"` to `_VALID_PROVIDER_TYPES` in `fabric/core/contract_validator.py`.
- Flip `manifest_translator.register_definition` default to `skip_validation=False`.
- Remove `skip_validation=True` from `module_loader` hot-reload callsites.

Without Phase 0, no other declutter can be measured: schemas, dispatcher, validator, and prompt allowlists can silently disagree forever.

### Phase 1 — One source of truth for the Front tool surface

- Build validator from `prompt_context.tools`, not the catalog.
- Introduce Fabric `tools_granted` issued per session/turn.
- Delete `mode.py:TOOL_ALLOWLIST`, `dispatcher.py:FRONT_TIER_ALLOWLISTS`, `schemas_back.py:BACK_TIER_ALLOWLISTS`. Prompt builder, dispatcher, and validator all read the same `tools_granted` set.
- Done when: live log shows `tools=N` and `schema_count=N` identical, and the model cannot call any tool not in `tools_granted`.

### Phase 2 — Stop ReAct from fighting the LLM

- Delete `front_dispatch_should_stay_conversational` + preflight reject.
- Delete `context_read_gap_requires_dispatch` + `_front_policy_dispatch`.
- Delete entire `back_execution_plan.py` + its gate in `loop.py`.
  - **RETAINED (2026-06-18):** `BackExecutionPlan` is the shared coverage ledger for
    Option B per-intent parallel workers (BackPool wiring). The deletion
    recommendation applied to single-worker mode only. See
    `docs/plans/back_pool_wiring_plan.md` Decision 7.
- Delete spin nudges (Front recall, Back capability, Back progress).
- Delete collection execution plans (~300 lines).
- Delete safety short-circuit scan (Fabric already blocked).
- Done when: no `dispatch START actor=front tool=dispatch_task` before any rejection, recipe/ideas turns answer directly, shopping adds invoke immediately.

### Phase 3 — FSM lifecycle only

- Delete `InterruptClassifier`, `ProactiveWakeHandler`, `_try_chain_into_current_response`, `PROGRESSING` state and tool-event transitions, `MODIFY_INFLIGHT` scoring, `InflightContext.pool_*` fields, second `route_task_sync` call.
- Collapse `response_final_table` 13 branches → 4 + 1 STAY.
- Add deterministic active-task/HIL confirmation resolver before generic interrupt arbitration.
- Done when: `yes please` / `go ahead` / `that one` / `no stop` / `not that` route to active task while `COMPANIONING` or `CLARIFYING_WORKER`; no FSM state ping-pong from tool events.

### Phase 4 — Thin actors

- Delete `back_pool.py` and `back_router.py`.
- Move HIL resolution to `front_hil_envelope` / `protocols/hitl_flow`.
- Move output stripping to LLM gateway / validator.
- Move family-context rendering to `prompt/builder` `SECTION_RENDERERS["persona"]`.
- Move safety-band / tool-filter / execution-profile logic into Fabric boundary.

### Phase 5 — Strip Fabric creep

- Delete `policy/affective_routing.py`, `policy/cognitive_load_routing.py`, `policy/qos_integration.py`.
- Move `core/agent_builder.BuildAgentHandler` to orchestrator.
- Feature-flag `retrieval/embedding_index.py` FAISS off.
- Derive `schemas_fabric` `returns` blocks from `CapabilityContract`.

### Phase 6 — Slim prompts

- Delete `REACT_RHYTHM`, `DISPATCH_RULES`, `STATE_INTERP*`, `COGNITIVE_DISCIPLINE*`, `EMOTIONAL_CALIB`, `SAFETY_HITL` Front body, `DOMAIN_RULES`, `INTERRUPT_RULES`, 6 mode-specific anti-pattern subsets.
- Collapse `MAX_ITERATIONS_TABLE` + `CRISIS_ITERATIONS_TABLE` to one.
- Collapse 11-mode `SS_READ_CONFIGS` to `full` / `task` / `slim`.
- Reduce Back prompt STEP 1-8 to a 5-line ReAct pattern.

### Phase 7 — Planner + orchestrator V1

- Delete `MICRO_*` plan states + `micro_execute` methods.
- Delete `MicroReplanCheckpoint` and `FailureReplanCheckpoint`.
- Delete `OutputSchemaGuard`.
- Feature-flag entire `workflows/` subsystem off.
- Drop Phase 2 LLM arbiter + HIL approval in `validate_service`.

### Phase 8 — Kernel + bus + selfmodel

- Delete `ConciergeConfig`; collapse to `KernelConfig`.
- Remove `TopicValidationMiddleware` default.
- Flip `enable_dead_letter_consumer = False`.
- Add `CapsuleRenderFlags`; render conscience/space/hobbies/routines only on relevance.
- Pick one identity path.
- Cache signature chain per session.
- Delete `system_bus_enabled`, `allow_*_passthrough`; collapse `enable_grounding`/`enable_spatial` into `enable_self_model`.

## Definition Of Done

Behavior:
- Live log shows Front `tools=N` equals validator `schema_count=N` for the same turn.
- No `dispatch START actor=front tool=dispatch_task` followed by `react_loop: rejected conversational front dispatch`.
- Recipe / ideas / lunch brainstorming turns answer with `dispatched=0` and a natural sentence.
- Explicit shopping / calendar / task turns dispatch once and Back invokes the capability by iteration 1 or 2.
- `yes please` while a task is active does not start a new topic.
- No BackPool unknown-topic warnings.
- No FSM state ping-pong driven only by `tool.started` / `tool.completed`.
- Front LLM and Back LLM produce natural sentences without policy contradictions in the prompt.

Tests:
- Behavior tests for active-tool / schema alignment, conversational-dispatch preflight removal, explicit side-effect dispatch, active-task confirmation routing, Back native-family direct binding, single-discovery rule for known capabilities.

Tests removed:
- Hardcoded total tool counts.
- Hardcoded prompt section counts.
- POC anniversary-demo tests living under `tests/k1/concierge`.
- Assertions that known-incomplete wiring is the desired behavior.

## Explicit Keep List (Do Not Delete While Decluttering)

- Native family adapters under `k1/tools/family/`.
- Hard safety / offline filters in Fabric.
- HIL core concept (one path, owned by `HumanInTheLoopService`).
- Session state manager core lifecycle.
- Back worker concept.
- Task artifacts / result presentation.
- ReAct loop concept (just thinner).
- Model hub provider abstraction.
- SQLite family store.
- Fabric registry, contract validator, retrieval pipeline, security context, tool scope, output validation.
- DAG executor with wave-parallel + saga compensation.

## One-Line Summary

The Concierge has grown three control planes (prompt + ReAct + FSM) that re-decide what the LLM already decided; Fabric has grown two control planes (affective / cognitive / QoS routing + agent builder runtime) that re-decide what its own retrieval already decided; Planner/Orchestrator has grown a shadow pipeline (micro-replan + workflow engine) that re-decides what one sketch + one dag executor already did. Strip every "re-decide" surface, keep one owner per decision, and the LLMs go back to writing natural sentences.
