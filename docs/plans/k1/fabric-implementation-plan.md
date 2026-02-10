# Capability Fabric -- Implementation Plan

> **Module**: Capability Fabric (Layer 2.5 in K1 Cognitive Architecture)
> **Location**: `k1/fabric/`
> **Plan Created**: 2026-02-07
> **Last Updated**: 2026-02-07
> **Status**: Planning
> **Governing Documents**:
>
> - `k1/fabric/fabric.mmd` (911 lines -- architecture diagram)
> - `k1/fabric/fabric_discussion.md` (2195 lines -- design document)
> - `architecture_diagrams/k1/k1_cognitive_architecture_skeleton.mmd` (1888 lines)
> - `architecture_diagrams/bridge/bridge_architecture.mmd` (882 lines)
> **Reference Plan**: `docs/plans/sessionstate-implementation-plan.md` (SessionState -- 455+ tests, fully implemented)
> **Related ADRs**: ADR-K004 (Capability Fabric Adaptation), ADR-0005 (Agent Lifecycle), ADR-0017 (Single Writer), ADR-0028 (Performance Scheduling), ADR-0011 (FlatBuffers Serialization)
> **Branch Target**: `k1-kernel`

---

## Executive Summary

Capability Fabric is K1's central resolution, retrieval, and execution engine. It is the single runtime through which every tool invocation, agent spawn, and workflow execution flows. Fabric is **deterministic, stateless per-request, NO LLM, NEVER writes SessionState**.

### Three Roles

| Role | Serves | What It Does |
|------|--------|-------------|
| **Role 1: Intelligent Retrieval** | Planner (HIGH tier) | Semantic Top-K search across registry. Returns relevant capabilities + schemas. |
| **Role 2: Resolution + Execution** | Orchestrator + Concierge (ALL tiers) | Name -> provider lookup, policy check, context build, execute, return result. |
| **Role 3: Agent Factory** | Plan steps with `agent.execute.*` | Instantiate agents from YAML templates with scoped tools, LLM, SessionState reader. |

### Seven Subsystems

| # | Subsystem | Dir | Purpose |
|---|-----------|-----|---------|
| 1 | Contract System | `contracts/` | Standard shape for tools, agents, prompts, workflows. Validation + parsing. |
| 2 | Capability Registry | `core/` | In-memory indexed catalog. Exact lookup + semantic search index. |
| 3 | Semantic Retrieval Engine | `retrieval/` | Embedding + hard filter + soft rank + Top-K. Serves Planner. |
| 4 | Provider Resolution Engine | `provider_resolution/` | Name -> provider. Exact match. Serves Orchestrator + Concierge. |
| 5 | Policy Engine | `policy/` | 4 dimensions: Security (hard gate), Affective, Cognitive Load, QoS. |
| 6 | Execution Runtime | `providers/` | 6 provider types: MCP, WASM, Bridge, Agent, Workflow, Concierge. |
| 7 | Context Builder | `core/` | Reads SessionState, applies 128K token budget, compiles prompts. |
| 8 | Output Validation | `output_validation/` | 3-Tier validation pipeline: Structural -> Schema -> Semantic. HallucinationDetector, SchemaCompiler, ValidationFallback. |
| 9 | Health Checker | `health/` | Provider health monitoring, availability tracking, proactive capability gap detection. |

### 13 Hard Invariants

| ID | Invariant |
|----|-----------|
| FAB-01 | Fabric NEVER writes to SessionState |
| FAB-02 | Fabric NEVER calls an LLM |
| FAB-03 | Fabric is stateless per-request |
| FAB-04 | Every execution returns CapabilityResult within circuit breaker timeout (30s) |
| FAB-05 | Hard filters run BEFORE soft ranking (safety first) |
| FAB-06 | Safety band access is ALWAYS checked before provider execution |
| FAB-07 | Sub-Agent tool access is scoped to plan-specified `tools_granted[]` only |
| FAB-08 | Context Builder respects 128K token budget for agent context |
| FAB-09 | All Fabric events emitted on K1 Event Bus with cognitive_trace_id |
| FAB-10 | Provider selection is deterministic given same inputs + same registry state |
| FAB-11 | Capability names follow type conventions |
| FAB-12 | All contracts validated against schema before registration |
| FAB-13 | (From mmd) Registry lookup < 1ms, Retrieval < 50ms, Full overhead < 100ms P95 |

### Independence Confirmation

Fabric can be developed independently because:

1. **Hexagonal Architecture**: All interactions through ports (ISessionStateReader, IEventPort, IBridgePort, IModelGatewayPort)
2. **FAB-01/02/03**: Never writes SessionState, never calls LLM, stateless -- no mutating dependencies
3. **SessionState Implemented**: Use `SessionStateFactory.create_for_testing()` for read-only context
4. **Test Adapter Pattern**: Established by SessionState (InMemory, Local, Direct adapters)
5. **Self-Contained Subsystems**: Each subsystem has clear interfaces and can be tested in isolation

### Dependency Map (External)

| Dependency | Component | How Fabric Uses | Test Strategy |
|------------|-----------|-----------------|---------------|
| SessionState (READ-ONLY) | K1 L5 | Context Builder reads declared sections | `SessionStateFactory.create_for_testing()` -- IMPLEMENTED |
| K1 Event Bus | K1 Coordination | Event emission + consumption | `LocalEventAdapter` (capture mode) -- IMPLEMENTED |
| Model Gateway | K1 L2.5 | Agent Factory grants LLM access | `TestModelGatewayAdapter` (canned responses) |
| Prompt System | K1 L2.5 | Prompt resolution + compilation | `TestPromptAdapter` (static templates) |
| Bridge (BridgeConnectionAdapter) | K1 L6 | Bridge Provider + IFL tool routing | `BridgeConnectionAdapter` (connects when Bridge available, graceful fallback when not). Bridge DESIGN is ready (`bridge_architecture.mmd`), CODE not yet built. Adapter pattern enables Fabric development to proceed independently. Test: `TestBridgeAdapter` (local in-memory fallback). |
| Delta Bus | K1 Coordination | Agents emit deltas | `TestDeltaBusAdapter` (capture mode) |

---

## Milestone Overview

| Milestone | Name | Epics | Focus |
|-----------|------|-------|-------|
| M1 | Foundation | 3 | ADRs, contract schemas, core types |
| M2 | Contract System + Registry | 4 | Contract parsing/validation, in-memory registry, module loader, capability versioning |
| M3 | Resolution + Policy + Execution | 6 | Provider resolution, policy engine, 6 provider runtimes, circuit breaker, output validation pipeline, health checker |
| M4 | Retrieval + Context + Agent Factory + Meta-Agent Creation | 5 | Semantic search, context builder, agent factory, fabric mailbox/concurrency, meta-agent creation |
| M5 | Ports, Adapters & Standalone Mode | 4 | Port interfaces, production + test adapters (incl. BridgeConnectionAdapter), factory, event integration |
| M6 | Testing | 7 | Unit, integration, contract, cross-subsystem, lifecycle tests |
| M7 | SLO/SLI + Observability | 4 | SLI definition, metrics, tracing, alerts |
| M8 | Production Readiness | 4 | Load testing, chaos testing, documentation, final validation |

**Estimated effort**: 8-12 weeks (assuming SessionState-level rigor)

---

## Milestone 1: Foundation

> **Goal**: Establish architectural decisions, define contract schemas, and create core Fabric types before any implementation code.
>
> **Prerequisite**: All ADRs reviewed and accepted. Contract schemas registered.
>
> **Pattern**: Mirrors SessionState M1 (ADR review + Contract registration + FlatBuffers).

### Epic 1.1: ADR Review & Creation

**Goal**: Review existing ADRs relevant to Fabric. Create/update ADRs where gaps exist.

> **Reference**: `fabric_discussion.md` Section 26 -- 10 Open Design Questions
> **Note**: ADR-K004 needs revision (currently references Contract-Net Protocol, must be updated for Fabric Resolution + Retrieval + Agent Factory).

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 1.1.1 | Review ADR-K004 (Capability Fabric Adaptation) | DONE | ADR reviewed | ADR-K004 file not found in repo. Superseded by FAB-005. See `k1/docs/adrs/FAB-005-fabric-architecture-supersedes-contract-net.md`. |
| 1.1.2 | Update ADR-K004 for Fabric architecture | DONE | ADR updated | FAB-005 created as full replacement. Documents Contract-Net -> Fabric transition, 3 roles, 7 subsystems, 13 invariants, 5 ports. Status: Accepted. |
| 1.1.3 | Review ADR-0005 (Agent Lifecycle) | DONE | ADR reviewed | FAB-006 created. Specializes ADR-0005 6-state FSM for Fabric Agent Factory: scoped tool access, pool key by template+tools hash, stateless result pattern. Status: Accepted. See `k1/docs/adrs/FAB-006-agent-lifecycle-in-fabric.md`. |
| 1.1.4 | Review ADR-0011 (FlatBuffers Serialization) | DONE | ADR reviewed | FAB-007 created. Dual-layer serialization: Pydantic internal + FlatBuffers at boundaries. 5 new schemas (capability_request, capability_result, task_envelope, committed_plan, retrieval_result) + 4 existing reused. Status: Accepted. See `k1/docs/adrs/FAB-007-flatbuffers-serialization-in-fabric.md`. |
| 1.1.5 | Review ADR-0017 (Single Writer) | DONE | ADR reviewed | FAB-008 created. Confirms Fabric is strictly read-only (ISessionStateReader only). No ISessionStateWriter in any Fabric component. Delta Bus for agent fact discovery. Status: Accepted. See `k1/docs/adrs/FAB-008-single-writer-alignment.md`. |
| 1.1.6 | Review ADR-0028 (Performance Scheduling) | DONE | ADR reviewed | FAB-009 created. Maps Fabric operations to WFQ priority classes. Priority propagation from caller. Agent spawn always INTERACTIVE. Retrieval + Resolution not scheduled (fast path). Status: Accepted. See `k1/docs/adrs/FAB-009-performance-scheduling-in-fabric.md`. |
| 1.1.7 | Create ADR: Core Envelope Schemas | DONE | New ADR | FAB-001 fleshed out. Frozen Pydantic dataclasses: CapabilityRequest, CapabilityResult, TaskEnvelope, CommittedPlan, RetrievalResult, RetrievalCandidate, PlanStep. WFQ priority embedded. Status: Accepted. See `k1/docs/adrs/FAB-001-core-envelope-schemas.md`. |
| 1.1.8 | Create ADR: Embedding Model Selection | DONE | New ADR | FAB-002 accepted. UltraBERT v4.0.0, 768-dim, S5 text format, FAISS IndexFlatIP. PoC validated: 88.9% Recall@5. See `k1/docs/adrs/FAB-002-embedding-model-selection.md`. |
| 1.1.9 | Create ADR: Fabric Concurrency Model | DONE | New ADR | FAB-003 fleshed out. Hybrid: async facade + WFQ-scheduled agent execution. No FABRIC_MAILBOX needed. Epic 4.4 bypassed. Semaphore(10) for backpressure. Status: Accepted. See `k1/docs/adrs/FAB-003-fabric-concurrency-model.md`. |
| 1.1.10 | Create ADR: Multi-Provider Selection | DONE | New ADR | FAB-004 fleshed out. Two-stage pipeline: Retrieval SoftRanker (semantic) + Resolution ProviderSelector (operational). Weighted composite score (0.50 semantic, 0.20 success, 0.15 latency, 0.15 type). Fallback chain top-3. Status: Accepted. See `k1/docs/adrs/FAB-004-multi-provider-selection.md`. |

> **Wiring**: ADRs are governance artifacts, not code. No runtime wiring. However:
>
> - ADR-1.1.7 (Envelope Schemas) **decides** the type system used by EVERY subsystem in M2-M5.
> - ADR-1.1.9 (Concurrency Model) **decides** whether Epic 4.4 (FabricMailbox) is needed or bypassed.
> - ADR-1.1.8 (Embedding Model) **decides** dimensionality for EmbeddingIndex (4.1.1) and must match K1 default.
> - ADR-1.1.10 (Multi-Provider) **decides** scoring logic in ProviderSelector (3.1.3) vs SoftRanker (4.1.3).
> - **Outputs consumed by**: All subsequent milestones. No ADR = no implementation clearance (GATE 1).

### Epic 1.2: Contract Schema Registration

**Goal**: Register Fabric contract schemas in the K1 contracts system.

> **Reference**: `k1/contracts/` directory structure. SessionState pattern for contract registration.
> **Deliverables**: YAML contract schemas in `k1/contracts/schemas/modules/fabric/`

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 1.2.1 | Create module.contract.yaml for Fabric | DONE | k1/contracts/modules/fabric/module.contract.yaml | 21 exports (facade, retrieval, contracts, registry, resolution, policy, context, agent factory, output validation, health, 9 types). Entrypoints: fabric:initialize, fabric:cleanup. Dependencies: kernel, bus, sessionstate. |
| 1.2.2 | Create wiring.contract.yaml for Fabric | DONE | k1/contracts/modules/fabric/wiring.contract.yaml | Code root k1/fabric, 44 required_files across 12 submodules. 5 provided capabilities (execute, retrieve, register, resolve, health). 8 consumed capabilities (session:read, bus:publish, bridge, model-gateway, prompt-system, delta-bus, scheduler). 12 emitted events (capability lifecycle + agent lifecycle). 3 subscribed events. No mailboxes (FAB-003). Read-only state (FAB-008). 13 validation rules. |
| 1.2.3 | Create policies.contract.yaml for Fabric | DONE | k1/contracts/modules/fabric/policies.contract.yaml | 12 granted capabilities. Full Section 22 performance budgets (registry <1ms, retrieval <20ms/50ms, resolution <5ms, context <10ms/50ms, overhead <100ms). Per-provider timeouts (MCP 10/15s, WASM 5s, Bridge 10s, Agent 30s, Workflow 60s). Circuit breaker config (global + 6 per-provider). Egress rules. Safety band enforcement. Audit with cognitive_trace_id. |
| 1.2.4 | Create tool_contract.schema.json | DONE | k1/contracts/schemas/tool_contract.schema.json | Draft-07 JSON Schema. Root key `tool_contract`, 22 properties. Name pattern enforces `tool.<verb>.<name>` convention. Semver version, domain[] min 1, description max 512, capabilities[], limitations[], required/optional inputs and context, output JSON Schema, provider_type (MCP, WASM, BRIDGE), safety_band (GREEN thru CRISIS), cost + latency fields, availability enum, audit timestamps + 30d metrics. Shared defs: input_spec, input_spec_optional. Validated against Section 6 restaurant_booking example. |
| 1.2.5 | Create agent_contract.schema.json | DONE | k1/contracts/schemas/agent_contract.schema.json | Draft-07 JSON Schema. Root key `agent_contract`, extends tool fields with 6 agent-specific: prompt_template (required), tools_granted[] (pattern-validated per FAB-07), llm_budget_tokens (min 1), max_tool_calls (min 0), max_execution_time_ms (min 1), template_file. provider_type locked to AGENT. Name pattern enforces `agent.<verb>.<name>` convention. Validated against Section 6 invitation_sender example. |
| 1.2.6 | Create prompt_contract.schema.json | DONE | k1/contracts/schemas/prompt_contract.schema.json | Draft-07 JSON Schema. Root key `prompt_contract`, 12 properties. Name pattern `^[a-z][a-z0-9_]+(_v[0-9]+)?$`. Variables as variable_spec (name, type enum STRING/NUMBER/BOOLEAN/DATE/OBJECT/ARRAY, required bool, optional default, description). output_format enum TEXT/JSON/STRUCTURED. compatible_agents/tools pattern-validated. Validated against Section 6 invitation_drafter_v1 example. |
| 1.2.7 | Create workflow_contract.schema.json | DONE | k1/contracts/schemas/workflow_contract.schema.json | Draft-07 JSON Schema. Root key `workflow_contract`. Name pattern `^workflow\.run\.<name>$`. trigger_spec (type cron/event/manual, schedule, timezone, event_topic). plan_step (id, capability, prompt_template, params with $ref support, tools_granted, deps). Dependencies as DAG map (step_id -> [dep_ids]). max_depth 1-10 default 3. allows_sub_workflows default true. Audit: created_at, last_run, run_count, success_rate. Validated against Section 6 weekly_health_check example. |
| 1.2.8 | Validate all schemas via CLI | DONE | CLI validation passing | All 7 artifacts validated: (1) 4 JSON schemas pass Draft-07 self-validation via jsonschema.Draft7Validator.check_schema(). (2) 4 JSON schemas accept Section 6 example contracts (restaurant_booking, invitation_sender, invitation_drafter_v1, weekly_health_check). (3) 3 YAML module contracts parse cleanly with correct top-level keys. CLI stub at k1/contracts/cli.py not yet implemented -- validation ran via inline Python. |

> **Wiring**:
>
> - **module.contract.yaml** (1.2.1) **defines** all public exports that FabricFactory (5.3.1) must wire and test_module_contract.py (6.4.1) must verify.
> - **wiring.contract.yaml** (1.2.2) **defines** ports, adapters, capabilities that test_wiring_contract.py (6.4.2) validates.
> - **policies.contract.yaml** (1.2.3) **defines** SLI targets that PolicyEngine (3.2.5), performance tests (6.7.x), and SLO validation (7.1.x) enforce.
> - **tool/agent/prompt/workflow schemas** (1.2.4-1.2.7) **consumed by** ContractValidator (2.1.1), all 4 parsers (2.1.2-2.1.5), and schema validation tests (6.4.4-6.4.5).
> - **Depends on**: K1 contracts CLI infrastructure (`k1/contracts/cli`).
> - **Consumed by**: Every M2 issue (validation + parsing reads these schemas).

### Epic 1.3: Core Types

**Goal**: Create all Fabric domain types as Python dataclasses. These are the message envelopes and data structures used across all subsystems.

> **Reference**: `fabric_discussion.md` Section 14 (Message Envelopes and Schemas)
> **Pattern**: Pure Python dataclasses with `to_dict()` and `from_dict()` class methods.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 1.3.1 | CapabilityRequest dataclass | DONE | k1/fabric/types.py | Fields: request_id (UUID), capability_name (str), params (dict), prompt_template (str or None), context_override (dict or None), tier (str: LOW/MEDIUM/HIGH), caller (str), caller_id (str), trace_id (str), timeout_ms (int), retry_count (int, default 0). Include to_dict(), from_dict(), validate(). |
| 1.3.2 | CapabilityResult dataclass | DONE | k1/fabric/types.py | Fields: request_id (str), success (bool), data (dict or None), error (ErrorInfo or None), duration_ms (int), provider_id (str), trace_id (str). ErrorInfo: code (str), message (str), retriable (bool). Include factory methods: success(), failure(), timeout(). |
| 1.3.3 | CapabilityContract dataclass | DONE | k1/fabric/types.py | Fields: name (str), version (str), domain (list[str]), description (str), capabilities (list[str]), limitations (list[str]), required_inputs (list[InputSpec]), optional_inputs (list[InputSpec]), required_context (list[str]), optional_context (list[str]), output (dict -- JSON Schema), provider_type (str), provider_id (str), provider_endpoint (str), safety_band_min (str), cost_per_call (float), avg_latency_ms (int), max_latency_ms (int), availability (str), registered_at (str), last_updated (str), success_rate_30d (float), total_invocations_30d (int). |
| 1.3.4 | AgentContract dataclass | DONE | k1/fabric/types.py | Extends CapabilityContract with agent-specific fields: prompt_template (str), tools_granted (list[str]), llm_budget_tokens (int), max_tool_calls (int), max_execution_time_ms (int), template_file (str). |
| 1.3.5 | PromptContract dataclass | DONE | k1/fabric/types.py | Fields: name, version, domain, description, intent_match (list[str]), variables (list[VariableSpec]), template_file (str), max_tokens (int), output_format (str), compatible_agents (list[str]), compatible_tools (list[str]). VariableSpec: name, type, required (bool), default (str or None), description. |
| 1.3.6 | WorkflowContract dataclass | DONE | k1/fabric/types.py | Fields: name, version, domain, description, source_plan_id (str), trigger (TriggerSpec), steps (list[PlanStep]), dependencies (dict), max_depth (int, default 3), allows_sub_workflows (bool), policy metadata, audit fields. TriggerSpec: type (cron/event/manual), schedule (str or None), timezone (str or None). PlanStep: id, capability, prompt_template, params, tools_granted, deps. |
| 1.3.7 | RetrievalResult dataclass | DONE | k1/fabric/types.py | Fields: capabilities (list[ScoredCapability]), total_matched (int), query_latency_ms (int). ScoredCapability: contract (CapabilityContract), score (float). |
| 1.3.8 | ExecutionContext dataclass | DONE | k1/fabric/types.py | Fields: session_sections (dict[str, Any]), params (dict[str, Any]), prompt (str or None), token_count (int), trace_id (str). |
| 1.3.9 | ProviderConfig dataclass | DONE | k1/fabric/types.py | Fields: provider_id (str), provider_type (str: MCP/WASM/BRIDGE/AGENT/WORKFLOW/CONCIERGE), endpoint (str or None), transport (str or None: stdio/sse/http), module_path (str or None), sandbox_memory_mb (int or None), max_concurrent (int), health_check_interval_s (int), max_execution_ms (int). |
| 1.3.10 | Enums: ProviderType, SafetyBand, Availability, Tier, AgentLifecycleState | DONE | k1/fabric/types.py | **ProviderType**: MCP, WASM, BRIDGE, AGENT, WORKFLOW, CONCIERGE. **SafetyBand**: GREEN, AMBER, RED, CRISIS (ordered). **Availability**: ONLINE, DEGRADED, OFFLINE. **Tier**: LOW, MEDIUM, HIGH. **AgentLifecycleState**: PENDING, WARMING, ACTIVE, IDLE, DRAINING, TERMINATED. **CapabilityType prefixes**: agent.spawn, agent.execute, tool.execute, tool.read, workflow.run, concierge.state. |

> **Wiring**:
>
> - **CapabilityRequest** (1.3.1) is the **input envelope** for FabricFacade.execute() (5.3.2), Resolver (3.1.5), PolicyEngine (3.2.5), all Providers (3.3.x), and EventEmitter (5.4.2). Created by Orchestrator/Concierge callers.
> - **CapabilityResult** (1.3.2) is the **output envelope** returned by every Provider.execute(), validated by OutputValidationPipeline (3.5.5), emitted in events (5.4.1). Consumed by Orchestrator.
> - **CapabilityContract** (1.3.3) is the **registry record** stored in CapabilityRegistry (2.2.1), queried by RetrievalEngine (4.1.5), Resolver (3.1.5), ContextBuilder (4.2.1).
> - **AgentContract** (1.3.4) is consumed by AgentFactory (4.3.1) for agent instantiation and ToolScope (3.2.6) for scoping.
> - **ProviderConfig** (1.3.9) is consumed by ProviderRegistry (3.1.1) and ProviderFactory (3.1.4).
> - **ExecutionContext** (1.3.8) is built by ContextBuilder (4.2.1), consumed by all Providers via execute(request, context, trace_id).
> - **Enums** (1.3.10): SafetyBand used by SecurityContext (3.2.1) and HardFilter (4.1.2). Availability used by AvailabilityTracker (3.6.2) and Registry (2.2.5). ProviderType used by ProviderFactory (3.1.4) and CircuitBreaker configs (3.4.2).
> - **Depends on**: ADR-1.1.7 decision (Pydantic vs FlatBuffers vs both).
> - **All types are pure dataclasses**: No port dependencies, no I/O. Importable by any subsystem.

---

## Milestone 2: Contract System + Registry

> **Goal**: Implement the Contract System (Subsystem 1) and Capability Registry (Subsystem 2). These are the foundation that all other subsystems read from.
>
> **Build Order Reference**: `fabric_discussion.md` Section 24 -- Phase 1 (Contract schemas + validation) and Phase 2 (Capability Registry).
>
> **Prerequisite**: M1 complete (types and contract schemas exist).

### Epic 2.1: Contract Validation & Parsing

**Goal**: Implement contract loading from YAML files and validation against JSON Schemas.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 2.1.1 | Implement ContractValidator | DONE | k1/fabric/core/contract_validator.py | Two-phase validation: (1) JSON Schema Draft-07 structural via jsonschema.Draft7Validator, (2) 12 semantic rules. ContractValidator class with validate(), validate_or_raise(), validate_body(). ContractValidationError with errors list, contract_type, contract_name. detect_contract_type() auto-detection. Schema caching. All 4 contract types supported. |
| 2.1.2 | Implement ToolContractParser | DONE | k1/fabric/contracts/tool_contract.py | ToolContractParser with parse(source: str/Path/dict), parse_body(body). Loads YAML, extracts tool_contract root key, validates via ContractValidator, builds CapabilityContract with all 22 fields. InputSpec nested parsing. Dependency injection for validator. ToolContractParseError for I/O and parse failures. |
| 2.1.3 | Implement AgentContractParser | DONE | k1/fabric/contracts/agent_contract.py | AgentContractParser with parse(source: str/Path/dict), parse_body(body). Loads YAML, extracts agent_contract root key, validates via ContractValidator, builds AgentContract with all base CapabilityContract fields + 6 agent-specific (prompt_template, tools_granted, llm_budget_tokens, max_tool_calls, max_execution_time_ms, template_file). InputSpec nested parsing. Dependency injection for validator. AgentContractParseError for I/O and parse failures. 18 errors caught on maximally-bad input. |
| 2.1.4 | Implement PromptContractParser | DONE | k1/fabric/contracts/prompt_contract.py | PromptContractParser with parse(source: str/Path/dict), parse_body(body). Loads YAML, extracts prompt_contract root key, validates via ContractValidator, builds PromptContract with all 14 fields (identity, intent_match, variables via VariableSpec.from_dict, template config, compatibility, audit). Dependency injection for validator. PromptContractParseError for I/O and parse failures. Rule-11 validates variable names, types, required/default consistency, duplicates. 20 errors caught on maximally-bad input. |
| 2.1.5 | Implement WorkflowContractParser | DONE | k1/fabric/contracts/workflow_contract.py | WorkflowContractParser with parse(source: str/Path/dict), parse_body(body). Loads YAML, extracts workflow_contract root key, validates via ContractValidator, builds WorkflowContract with all 17 fields (identity, source_plan_id, trigger via TriggerSpec.from_dict, steps via PlanStep.from_dict, dependencies DAG, recursion controls, policy, audit). DAG acyclicity validated by rule-12 (Kahn's algorithm). Dependency injection for validator. WorkflowContractParseError for I/O and parse failures. |
| 2.1.6 | Contract type detection | DONE | k1/fabric/contracts/init.py | parse_contract(source, validator, skip_validation) auto-detects contract type via detect_contract_type() root key inspection, routes to correct parser (Tool/Agent/Prompt/Workflow), returns typed Union. parse_contract_body() for pre-extracted bodies with explicit type. ContractParseError for unknown types, YAML errors, non-YAML extensions. Shared validator support for schema caching. 16 integration tests: all 4 types round-trip, error routing, skip_validation passthrough. |

> **Wiring**:
>
> - **ContractValidator** (2.1.1) is a **dependency of** Registry.register() (2.2.2) and ModuleLoader (2.3.1). Every contract passes through validation before entering the system.
> - **Parsers** (2.1.2-2.1.5) **consume** schemas from Epic 1.2 (tool_contract.schema.json, agent_contract.schema.json, prompt_contract.schema.json, workflow_contract.schema.json).
> - **Parsers** **produce** typed dataclasses from Epic 1.3 (CapabilityContract, AgentContract, PromptContract, WorkflowContract).
> - **parse_contract()** (2.1.6) is the **single entry point** called by ModuleLoader.scan_directory() (2.3.3) and programmatic registration (2.3.4).
> - **Depends on**: M1 types (1.3.x) + M1 schemas (1.2.x). No port dependencies. Pure computation.
> - **Consumed by**: Registry (2.2.2), ModuleLoader (2.3.1), ContractTests (6.4.x).

### Epic 2.2: Capability Registry

**Goal**: Implement the in-memory indexed catalog. This is the core data structure that both Retrieval (Role 1) and Resolution (Role 2) query.

> **Reference**: `fabric_discussion.md` Section 7 -- complete data structures and API.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 2.2.1 | Implement registry data structures | DONE | k1/fabric/core/registry.py | CapabilityRegistry class with 5 core indexes: by_name (dict O(1) name lookup), by_domain (inverted domain index), by_type (grouped by CapabilityType prefix, with generic 'prompt'/'workflow' keys for non-typed), by_provider (grouped by provider_id), metadata_cache (ContractMetadata hot cache with 11 fields). Thread-safe with RLock. ContractUnion type alias for all 4 contract types. EventPort Protocol (duck-typed, avoids hard SessionState dependency). ContractMetadata dataclass (mutable, to_dict). RegistryHealth frozen dataclass (2.2.8 type pre-created). 3 exception classes: CapabilityRegistryError, DuplicateCapabilityError, CapabilityNotFoundError. Event topic constants. Constructor injection: validator + event_port (Optional). |
| 2.2.2 | Implement register() and unregister() | DONE | k1/fabric/core/registry.py | register(contract, skip_validation): 5-phase atomic registration -- (1) validate via ContractValidator (wraps contract back to root-keyed dict), (2) duplicate check (DuplicateCapabilityError), (3) insert all 4 indexes under RLock, (4) build metadata cache entry with monotonic timestamp, (5) emit k1.fabric.capability.registered.v1 outside lock. unregister(name) returns bool: remove from all indexes under RLock, emit k1.fabric.capability.unregistered.v1, return False if not found. Private helpers for insert/remove on domain, type, and provider indexes. Polymorphic contract-to-validation-dict handles all 4 contract types. 50-thread concurrent registration stress test passed. |
| 2.2.3 | Implement lookup() | DONE | k1/fabric/core/registry.py | O(1) exact-match by canonical name via by_name dict. Returns ContractUnion or None. contains(name) -> bool convenience. get_metadata(name) -> ContractMetadata or None for hot-cache access. |
| 2.2.4 | Implement list_by_domain() and list_by_type() | DONE | k1/fabric/core/registry.py | O(1) via inverted indexes, all return defensive copies (list()). list_by_domain(domain) returns all capabilities with given domain tag. list_by_type(type_prefix) returns all capabilities matching type prefix (tool.execute, agent.execute, agent.spawn, workflow.run, prompt). list_by_provider(provider_id) bonus. list_all(), list_names() (sorted), size property. 25 integration tests: empty registry, constructor injection, register all 4 types, duplicate error, unregister cleans all indexes, lookup/contains, multi-domain, multi-cap-per-domain, mixed types, empty queries, provider grouping, bulk accessors, defensive copies, metadata cache, optional event port, 50-thread concurrency, multi-domain cleanup, RegistryHealth type. |
| 2.2.5 | Implement update_availability() | DONE | k1/fabric/core/registry.py | Copy-on-write via dataclasses.replace() on frozen contract. Validates Availability enum value. Swaps contract reference in all 4 indexes + updates mutable metadata cache. No-ops when already at target state. Emits k1.fabric.capability.availability.changed.v1 with old/new values. CapabilityNotFoundError for unknown name. ValueError for invalid availability string. 10 integration tests (transitions, no-op, not_found, invalid, event, index consistency, frozen immutability, no-event-port). |
| 2.2.6 | Implement update_metrics() | DONE | k1/fabric/core/registry.py | Copy-on-write update of success_rate_30d (running average), avg_latency_ms (EMA alpha=0.3), total_invocations_30d (counter). First invocation uses exact latency. Swaps frozen contract in all indexes. Updates mutable metadata cache. Emits k1.fabric.capability.metrics.updated.v1. ValueError for negative latency. 11 integration tests (first success, first failure, running average, EMA, metadata sync, not_found, negative latency, event, index consistency, frozen replacement, zero latency). |
| 2.2.7 | Implement reload() | DONE | k1/fabric/core/registry.py | Full reload from contracts directory. Scans tools/, agents/, prompts/, workflows/ for .yaml/.yml files. Uses parse_contract() facade (2.1.6) with shared validator. Clears all 5 indexes under RLock, re-registers each valid contract. Skips duplicates (first wins, logged as error). Sets last_reload_at ISO timestamp. Emits k1.fabric.registry.reloaded.v1 with loaded/failed counts. Returns summary dict {loaded, failed, errors[{file, error}]}. 8 integration tests (yaml loading, clear old, failures, timestamp, event, multi-subdir, missing subdirs, duplicate handling). |
| 2.2.8 | Implement health() | DONE | k1/fabric/core/registry.py | Returns frozen RegistryHealth snapshot under short lock. Computes by_type_counts from by_type index, by_availability_counts from metadata_cache, index_size_bytes via sys.getsizeof on all 5 indexes. Includes last_reload_at from reload(). 7 integration tests (empty, after registration, after availability change, frozen, to_dict, after unregister, positive size). Plus 2 concurrency tests: 50-thread availability toggle + 50-thread metrics update (500 total invocations). |

> **Wiring**:
>
> - **CapabilityRegistry** is the **central hub** of the Fabric. Nearly every subsystem depends on it.
> - **register()/unregister()** (2.2.2) **calls** ContractValidator (2.1.1) before insertion. **Emits** events via IEventPort (5.1.2): `k1.fabric.capability.registered.v1`, `k1.fabric.capability.unregistered.v1`.
> - **lookup()** (2.2.3) is **called by** Resolver (3.1.5) for exact-match resolution (Role 2).
> - **list_by_domain()/list_by_type()** (2.2.4) is **called by** RetrievalEngine (4.1.5) for filtered discovery (Role 1).
> - **update_availability()** (2.2.5) is **called by** AvailabilityTracker (3.6.2), CircuitBreaker (3.4.1), HealthChecker (3.6.1).
> - **update_metrics()** (2.2.6) is **called by** FabricFacade.execute() (5.3.2) after every CapabilityResult.
> - **reload()** (2.2.7) is **called by** ModuleLoader (2.3.1) at startup.
> - **Thread-safety**: RLock guards all mutations. Reads are concurrent-safe.
> - **Depends on**: ContractValidator (2.1.1), IEventPort (5.1.2).
> - **Consumed by**: Resolver (3.1.5), RetrievalEngine (4.1.5), ModuleLoader (2.3.x), AvailabilityTracker (3.6.2), HealthChecker (3.6.1), FabricFacade (5.3.2), CapabilityRegistryAPI (5.3.4).
> - **Injection**: Constructor injection via FabricFactory (5.3.1). Receives `event_port` and `validator` as constructor args.

### Epic 2.3: Module Loader

**Goal**: Implement the file watcher that loads contracts from disk and enables hot-reload.

> **Reference**: `fabric_discussion.md` Section 7 -- Hot-Reload Mechanism.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 2.3.1 | Implement ModuleLoader | DONE | k1/fabric/core/module_loader.py | Watches `k1/contracts/` directory (tools/, agents/, prompts/, workflows/). On startup: scan all YAMLs, validate, register. Thread-safe incremental loading. |
| 2.3.2 | Implement hot-reload watcher | DONE | k1/fabric/core/module_loader.py | File system watcher (watchdog or polling). On file create/modify: parse YAML, validate, if valid: unregister(old) + register(new). On delete: unregister(name). If validation fails: log error, keep old contract, emit `k1.fabric.contract.validation.failed.v1`. Atomic per-contract, no downtime. |
| 2.3.3 | Implement contract directory scanner | DONE | k1/fabric/core/module_loader.py | `scan_directory(path) -> list[CapabilityContract]`: recursively find all .yaml/.yml files, auto-detect contract type, parse, validate, return valid contracts. Report invalid files as warnings. |
| 2.3.4 | Implement programmatic registration API | DONE | k1/fabric/core/module_loader.py | `register_from_dict(contract_dict) -> CapabilityContract`: allow runtime registration from in-memory contract dicts (not only YAML files). Used by Orchestrator's MCP Capability Registrar (MCP Tool Discovery -> MCP Provider Factory -> programmatic register). Enables MCP servers discovered at runtime to be registered without writing YAML to disk. Emits same `k1.fabric.capability.registered.v1` event. |

> **Wiring**:
>
> - **ModuleLoader** (2.3.1) **depends on** ContractValidator (2.1.1) via parse_contract() (2.1.6) and Registry.register() (2.2.2).
> - **Hot-reload watcher** (2.3.2) **calls** Registry.unregister() + Registry.register() atomically on file change. **Emits** `k1.fabric.contract.validation.failed.v1` via IEventPort on invalid YAML.
> - **scan_directory()** (2.3.3) is **called at startup** by FabricFactory (5.3.1) to bootstrap the registry from `k1/contracts/` disk files.
> - **register_from_dict()** (2.3.4) is **called by** event handler for `k1.mcp.tool.discovered.v1` (5.4.4) to register MCP tools discovered at runtime without YAML.
> - **Depends on**: parse_contract() (2.1.6), Registry (2.2.1), IEventPort (5.1.2), file system (watchdog or polling).
> - **Consumed by**: FabricFactory startup sequence (5.3.1), MCP tool discovery event handler (5.4.4).
> - **Pattern**: Singleton per Fabric instance. Constructed by FabricFactory with registry + event_port injected.

### Epic 2.4: Capability Versioning

**Goal**: Implement version management for capabilities -- conflict resolution, backward compatibility, and version negotiation during resolution.

> **Reference**: `k1_cognitive_architecture_skeleton.mmd` -- Capability Versioning, Workflow Invalidation.
> **Gap Coverage**: Architecture shows capability versioning as critical for workflow invalidation and schema drift detection.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 2.4.1 | Implement CapabilityVersion type | DONE | k1/fabric/types.py | Extend types with `CapabilityVersion{major, minor, patch}`. Implement `parse(semver_str) -> CapabilityVersion`, `is_compatible(v1, v2) -> bool` (same major = compatible), `compare(v1, v2) -> int`. Used by Registry and Resolver. |
| 2.4.2 | Implement version conflict resolution | DONE | k1/fabric/core/registry.py | When registering a capability with same name as existing: (1) If same version: REJECT (duplicate). (2) If newer compatible version (same major): UPGRADE (replace old). (3) If newer breaking version (different major): REGISTER BOTH (multi-version). (4) If older version: REJECT (regression). Emit `k1.fabric.capability.version.conflict.v1` on any conflict. |
| 2.4.3 | Implement backward compatibility rules | DONE | k1/fabric/core/registry.py | Registry maintains version index: `by_version: dict[str, dict[str, CapabilityContract]]` (name -> version -> contract). `lookup(name, version?)` supports: exact version match, latest compatible (same major, highest minor.patch), latest (no version constraint). Used by WorkflowProvider to verify referenced capabilities still compatible after schema drift. |

> **Wiring**:
>
> - **CapabilityVersion** (2.4.1) is a **pure type** added to types.py. Used by Registry version index and Resolver.
> - **Version conflict resolution** (2.4.2) is **invoked within** Registry.register() (2.2.2). **Emits** `k1.fabric.capability.version.conflict.v1` via IEventPort on any conflict.
> - **Backward compatibility rules** (2.4.3) **extend** Registry.lookup() to support version-aware queries. **Called by** WorkflowProvider (3.3.5) for schema drift detection and Resolver (3.1.5) for version-pinned resolution.
> - **Depends on**: Registry (2.2.1), IEventPort (5.1.2), CapabilityVersion type (2.4.1).
> - **Consumed by**: WorkflowProvider (3.3.5), Resolver (3.1.5), proactive gap detection (5.4.4).
> - **Pattern**: Version logic is embedded in Registry (not a separate subsystem). Same RLock protects version index mutations.

---

## Milestone 3: Resolution + Policy + Execution

> **Goal**: Implement Provider Resolution (Subsystem 4), Policy Engine (Subsystem 5), and Execution Runtime (Subsystem 6). This enables Role 2 (Resolution + Execution).
>
> **Build Order Reference**: Phase 3 (Resolution + basic Policy), Phase 4 (Execution Runtime), Phase 7 (Full Policy).
>
> **Prerequisite**: M2 complete (Registry operational with lookup()).

### Epic 3.1: Provider Resolution Engine

**Goal**: Map `CapabilityRequest.name` to a concrete provider. Exact-match lookup, not semantic.

> **Reference**: `fabric_discussion.md` Section 9 -- Resolution Pipeline.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 3.1.1 | Implement ProviderRegistry | DONE | k1/fabric/provider_resolution/provider_registry.py | Maps provider_id to ProviderConfig. Methods: `register_provider(provider_id, config)`, `lookup_provider(provider_id) -> ProviderConfig | None`,`health_check(provider_id) -> ProviderHealth`. Thread-safe dict. |
| 3.1.2 | Implement ProviderMatcher | DONE | k1/fabric/provider_resolution/provider_matcher.py | Given a CapabilityContract, find all registered providers that can fulfill it. Usually 1:1 (contract.provider_id -> provider). For multi-provider: contract.provider_id + aliases. Returns `list[ProviderConfig]`. |
| 3.1.3 | Implement ProviderSelector | DONE | k1/fabric/provider_resolution/provider_selector.py | Given candidate providers + policy scores, select the highest-scoring provider. Ties broken by: lower avg_latency_ms, then alphabetical name (deterministic per FAB-10). Returns `ResolvedProvider{provider_instance, contract, policy_context}`. |
| 3.1.4 | Implement ProviderFactory | DONE | k1/fabric/provider_resolution/provider_factory.py | Given ProviderConfig, instantiate the appropriate provider handler: MCPProvider, WASMProvider, BridgeProvider, AgentProvider, WorkflowProvider, ConciergeProvider. Factory pattern. |
| 3.1.5 | Implement Resolver (full pipeline) | DONE | k1/fabric/provider_resolution/resolver.py | Full resolution pipeline: (1) Registry lookup by name, (2) Provider matching, (3) Policy evaluation, (4) Provider selection, (5) Provider instantiation. Returns `ResolvedProvider`. Handles errors: capability_not_found, access_denied. |

> **Wiring**:
>
> - **ProviderRegistry** (3.1.1) is a **separate registry** from CapabilityRegistry (2.2.1). Maps provider_id to ProviderConfig. **Populated by** FabricFactory (5.3.1) at startup.
> - **ProviderMatcher** (3.1.2) **reads** CapabilityRegistry (2.2.1) to find which providers can fulfill a contract.
> - **ProviderSelector** (3.1.3) **receives** PolicyResult from PolicyEngine (3.2.5). ADR 1.1.10 decides if scoring uses ProviderSelector or SoftRanker (4.1.3).
> - **ProviderFactory** (3.1.4) **instantiates** provider handlers: MCPProvider (3.3.2), WASMProvider (3.3.3), BridgeProvider (3.3.4), AgentProvider (3.3.7/4.3.5), WorkflowProvider (3.3.5), ConciergeProvider (3.3.6). Factory pattern.
> - **Resolver** (3.1.5) is the **composite pipeline** called by FabricFacade.execute() (5.3.2). It chains: Registry.lookup() -> ProviderMatcher -> PolicyEngine.evaluate() -> ProviderSelector -> ProviderFactory.
> - **Depends on**: CapabilityRegistry (2.2.1), ProviderRegistry (3.1.1), PolicyEngine (3.2.5), all Providers (3.3.x).
> - **Consumed by**: FabricFacade.execute() (5.3.2).
> - **Injection**: FabricFactory constructs Resolver with registry, provider_registry, policy_engine injected.

### Epic 3.2: Policy Engine

**Goal**: Implement the 4-dimension policy evaluation. Security is a hard gate; the other three are soft scores.

> **Reference**: `fabric_discussion.md` Section 10 -- Four Policy Dimensions.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 3.2.1 | Implement SecurityContext (hard gate) | DONE | k1/fabric/policy/security_context.py | **Hard gate**: Check `user_band >= capability_band_min`. Band ordering: GREEN < AMBER < RED < CRISIS. If fail: immediate REJECT. Additional checks: sub-agent tool scoping (verify capability in tools_granted[]), rate limiting (per-capability invocation limits). This is the FIRST check in every policy evaluation. |
| 3.2.2 | Implement AffectiveRouting (soft score) | DONE | k1/fabric/policy/affective_routing.py | Read `affective_now` from SessionState. Rules: High sadness/anxiety (intensity > 0.7): prefer gentler/simpler providers (+0.1). High joy/excitement: prefer richer providers (+0.05). Neutral: no adjustment. Output: `affective_score (0.0 to 0.2)`. |
| 3.2.3 | Implement CognitiveLoadRouting (soft score) | DONE | k1/fabric/policy/cognitive_load_routing.py | Read complexity tier + cognitive state. Rules: High cognitive load: prefer faster/simpler providers (+0.1). Low cognitive load: no penalty for complex (+0.05). Output: `cognitive_score (0.0 to 0.15)`. |
| 3.2.4 | Implement QoSIntegration (soft score) | DONE | k1/fabric/policy/qos_integration.py | Budget-aware + latency-aware. Rules: Tight budget (<20% remaining): heavily prefer lower cost (weight 0.8). Tight latency (<30% remaining): heavily prefer faster (weight 0.8). Ample: balanced (weight 0.3 each). Output: `qos_score (0.0 to 0.2)`. |
| 3.2.5 | Implement PolicyEngine (composite) | DONE | k1/fabric/policy/policy_engine.py | Compose all 4 dimensions: `final_score = base_relevance + affective + cognitive + qos`. Security is hard gate (PASS/REJECT). Others are additive soft scores. Returns `PolicyResult{allowed: bool, score: float, reasons: list[str]}`. Deterministic per FAB-10. |
| 3.2.6 | Implement ToolScope (sub-agent tool scoping) | DONE | k1/fabric/policy/tool_scope.py | Enforces that sub-agents can only invoke capabilities from `tools_granted[]`. `validate(capability_name) -> bool`. Raises `AccessDeniedError` if not in allowed set. Used by Agent Factory when creating scoped invoke_capability for agents. |

> **Wiring**:
>
> - **SecurityContext** (3.2.1) is the **hard gate** -- FIRST check in every execute(). **Reads** user_band from CapabilityRequest and capability.safety_band_min from CapabilityContract (1.3.3). **Enforces** FAB-06.
> - **AffectiveRouting** (3.2.2) **reads** `affective_now` from SessionState via ISessionStateReader (5.1.1). Soft dependency: if SessionState unavailable, returns neutral score (0.0).
> - **CognitiveLoadRouting** (3.2.3) **reads** cognitive state from SessionState via ISessionStateReader (5.1.1). Same soft dependency.
> - **QoSIntegration** (3.2.4) **reads** budget/latency from CapabilityRequest or ExecutionContext (1.3.8). No port dependency.
> - **PolicyEngine** (3.2.5) **composes** all 4 dimensions. **Called by** Resolver (3.1.5) during resolution pipeline. Returns PolicyResult{allowed, score, reasons}.
> - **ToolScope** (3.2.6) **reads** tools_granted from AgentContract (1.3.4). **Used by** AgentFactory (4.3.1) step 5 to create scoped invoke_capability. **Enforces** FAB-07.
> - **Depends on**: ISessionStateReader (5.1.1) for affective + cognitive reads, types from M1.
> - **Consumed by**: Resolver (3.1.5), AgentFactory (4.3.1).
> - **Injection**: FabricFactory constructs PolicyEngine with state_reader port injected. ToolScope is standalone (no port deps).

### Epic 3.3: Execution Runtime (6 Provider Types)

**Goal**: Implement all 6 provider types with the common CapabilityProvider interface.

> **Reference**: `fabric_discussion.md` Section 11 -- Execution Runtime.
> **Build Order**: MCP first (most common), then WASM, Bridge, Agent (deferred to M4), Workflow, Concierge.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 3.3.1 | Implement CapabilityProvider protocol | DONE | k1/fabric/providers/base_provider.py | Protocol interface: `async execute(request, context, trace_id) -> CapabilityResult`, `async health_check() -> ProviderHealth`, `capabilities() -> list[str]`. All providers implement this. |
| 3.3.2 | Implement MCPProvider | DONE | k1/fabric/providers/mcp_provider.py | MCP tool execution via Model Context Protocol. Supports: local stdio transport, remote SSE transport, streamable-http transport. Flow: (1) lookup MCP server connection, (2) build MCP tools/call message, (3) send via transport, (4) await response within circuit breaker, (5) parse result, (6) return CapabilityResult. Handle MCP-specific errors: server not found, tool not found on server, timeout. |
| 3.3.3 | Implement WASMProvider | DONE | k1/fabric/providers/wasm_provider.py | WASM sandboxed execution. Flow: (1) load WASM module (cached), (2) create sandbox with memory limit, (3) marshal params, (4) execute function, (5) unmarshal result. Sandbox constraints: configurable memory (default 64MB), configurable timeout (default 5s), no network. |
| 3.3.4 | Implement BridgeProvider | DONE | k1/fabric/providers/bridge_provider.py | Route operations to K0 through Cross-Kernel Bridge via BridgeConnectionAdapter. Flow: (1) check `is_available()` via IBridgePort, (2) map to Bridge operation, (3) send via IBridgePort, (4) handle K0 offline fallback (LOCAL COLD), (5) return CapabilityResult. **Memory operations**: memory.store, memory.recall, memory.delta, checkpoint, feedback.signal. **IFL-routed tool execution**: `tool.execute.home.*`, `tool.execute.device.*` -- route via IFL (Inter-Function-Language) addressing from `bridge_architecture.mmd`. Bridge DESIGN is ready but CODE is not built. BridgeConnectionAdapter connects when Bridge is available and gracefully degrades when not. |
| 3.3.5 | Implement WorkflowProvider | DONE | k1/fabric/providers/workflow_provider.py | Rehydrate frozen WorkflowSpec + execute via Orchestrator. Flow: (1) load WorkflowSpec, (2) validate all referenced capabilities still exist (use version-aware lookup from Epic 2.4), (3) detect schema drift (small: auto-fill defaults; large: store gap in K0), (4) create Run Manifest, (5) send to Orchestrator for DAG execution, (6) guard max_depth=3. |
| 3.3.6 | Implement ConciergeProvider | DONE | k1/fabric/providers/concierge_provider.py | Handle `concierge.state.*` capabilities. Route to corresponding FSM state handler. Return CapabilityResult. |
| 3.3.7 | Implement AgentProvider (stub) | DONE | k1/fabric/providers/agent_provider.py | Stub implementation that delegates to Agent Factory (M4). Interface only at this stage. Full implementation in Epic 4.3. |

> **Wiring**:
>
> - **CapabilityProvider protocol** (3.3.1) is the **interface** ALL providers implement. Defines execute(), health_check(), capabilities(). **Consumed by** ProviderFactory (3.1.4) and CircuitBreaker (3.4.1) which wraps each provider.
> - **MCPProvider** (3.3.2) **uses** MCP transport layer (stdio/SSE/streamable-http). External dependency. **Wrapped by** CircuitBreaker (3.4.1) with per-provider config (3.4.2: 10s local / 15s remote).
> - **WASMProvider** (3.3.3) sandboxed execution. No port dependencies. **Wrapped by** CircuitBreaker (5s timeout).
> - **BridgeProvider** (3.3.4) **uses** IBridgePort (5.1.3) for K0 access. Routes memory.*and tool.execute.home.* via BridgeConnectionAdapter (5.2.8). **Wrapped by** CircuitBreaker (10s timeout). Gracefully degrades when Bridge unavailable.
> - **WorkflowProvider** (3.3.5) **uses** Registry (2.2.1) for version-aware capability lookup (2.4.3). Sends to Orchestrator for DAG execution. max_depth=3 guard.
> - **ConciergeProvider** (3.3.6) routes to FSM state handlers. Lightweight.
> - **AgentProvider** (3.3.7) is a **STUB** in M3 -- full implementation in Epic 4.3 (AgentFactory). Delegates to AgentFactory.spawn_and_execute().
> - **All providers** are **wrapped by** CircuitBreaker (3.4.1) in the execution path. Results pass through OutputValidationPipeline (3.5.5) before return.
> - **Depends on**: IBridgePort (5.1.3) for BridgeProvider, external transports for MCP, types from M1.
> - **Consumed by**: ProviderFactory (3.1.4), Resolver (3.1.5), FabricFacade.execute() (5.3.2).
> - **Injection**: ProviderFactory receives port references from FabricFactory. BridgeProvider gets IBridgePort. AgentProvider gets IModelGatewayPort + IDeltaBusPort (in M4).

### Epic 3.4: Circuit Breaker

**Goal**: Implement per-provider circuit breakers for fault isolation.

> **Reference**: `fabric_discussion.md` Section 19 -- Error Handling and Circuit Breakers.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 3.4.1 | Implement CircuitBreaker | DONE | k1/fabric/circuit_breaker/breaker.py | **Completed**: States: CLOSED (normal), OPEN (failing, reject all), HALF_OPEN (trying one request). Config: timeout_ms, failure_threshold, failure_window_ms, half_open_after_ms, fallback. Sliding window failure tracking. Thread-safe. 646 lines. 86 tests in test_circuit_breaker_341_343.py. |
| 3.4.2 | Implement per-provider circuit breaker config | DONE | k1/fabric/circuit_breaker/breaker_config.py | **Completed**: Per-provider type configs from `fabric_discussion.md` Section 19: MCP local (10s, 3/min), MCP remote (15s, 3/min), WASM (5s, 5/min), Bridge (10s, 3/min), Agent (30s, 2/min), Workflow (60s, 1/min). Default: 30s, 5 failures/min. get_breaker_config() with override support. |
| 3.4.3 | Implement retry strategy | DONE | k1/fabric/circuit_breaker/breaker.py | **Completed**: Integrated into CircuitBreaker.call(). Attempt 1: execute normally. Attempt 2: same provider, same params. Attempt 3: NOT automatic -- return CapabilityResult{success=false, retriable=false}. Max 2 retries for transient failures. |

> **Wiring**:
>
> - **CircuitBreaker** (3.4.1) **wraps** every provider's execute() call. Sits between Resolver output (3.1.5) and Provider.execute() (3.3.x) in the execution path.
> - **Per-provider config** (3.4.2) is loaded from hardcoded defaults per ProviderType enum (1.3.10). Override via policies.contract.yaml (1.2.3).
> - **On CB state change**: CB **calls** AvailabilityTracker.update_state() (3.6.2) and Registry.update_availability() (2.2.5). CB OPEN -> provider marked DEGRADED/OFFLINE.
> - **HealthChecker integration** (3.6.3): HealthChecker consumes CB state changes. CB OPEN triggers immediate health check. Health success signals CB to try HALF_OPEN.
> - **Retry strategy** (3.4.3) is internal to CB. Max 2 retries before returning failure. Does NOT escalate to a different provider.
> - **Depends on**: Provider interface (3.3.1), ProviderConfig (1.3.9), AvailabilityTracker (3.6.2).
> - **Consumed by**: FabricFacade.execute() execution path (5.3.2) -- CB wraps provider call.
> - **Injection**: FabricFactory creates one CircuitBreaker per registered provider. Stored in Resolver's provider registry.

### Epic 3.5: Output Validation Pipeline

**Goal**: Implement the 3-Tier Output Validation Pipeline from the K1 architecture skeleton. Validates all provider execution results before returning to callers.

> **Reference**: `k1_cognitive_architecture_skeleton.mmd` -- Fabric L2.5 Output Validation: Structural -> Schema -> Semantic.
> **Gap Coverage**: Architecture defines a full validation pipeline with HallucinationDetector and SchemaCompiler. No prior plan coverage.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 3.5.1 | Implement StructuralValidator | DONE | k1/fabric/output_validation/structural_validator.py | Tier 1 -- structural validation of CapabilityResult. Checks: (1) result has required fields (success, data or error), (2) data is well-formed (parseable JSON/dict), (3) no truncation markers, (4) response within size limits. Fast-fail: reject malformed results immediately. |
| 3.5.2 | Implement SchemaValidator (SchemaCompiler) | DONE | k1/fabric/output_validation/schema_validator.py | Tier 2 -- validate result.data against the output JSON Schema declared in the CapabilityContract. Uses `contract.output` schema. SchemaCompiler compiles JSON Schema once per contract (cached) for fast repeated validation. Reports specific field violations. |
| 3.5.3 | Implement SemanticValidator (HallucinationDetector) | DONE | k1/fabric/output_validation/semantic_validator.py | Tier 3 -- semantic validation for agent/LLM-generated outputs. HallucinationDetector checks: (1) factual grounding against provided context, (2) consistency with SessionState beliefs (via ISessionStateReader, read-only), (3) confidence scoring. Returns `ValidationResult{valid: bool, confidence: float, issues: list[str]}`. Optional tier -- only runs for agent/prompt provider types. |
| 3.5.4 | Implement ValidationFallback | DONE | k1/fabric/output_validation/validation_fallback.py | When validation fails: (1) Structural fail: REJECT, return CapabilityResult.failure(). (2) Schema fail: attempt coercion (fill defaults, cast types), retry validation, if still fails REJECT. (3) Semantic fail: annotate result with low-confidence warning, do NOT reject (soft signal). Emit `k1.fabric.output.validation.failed.v1` on any rejection. |
| 3.5.5 | Implement OutputValidationPipeline | DONE | k1/fabric/output_validation/pipeline.py | Composite pipeline: run Structural -> Schema -> Semantic in sequence. Short-circuit on hard failure (Structural, Schema). Pass-through on soft failure (Semantic warning). Wire into execution path AFTER provider returns result, BEFORE returning to caller. Configurable: skip_semantic=True for tool-only results. |

> **Wiring**:
>
> - **OutputValidationPipeline** (3.5.5) is **wired into** FabricFacade.execute() (5.3.2) AFTER provider.execute() returns and BEFORE returning CapabilityResult to caller.
> - **StructuralValidator** (3.5.1) has NO dependencies. Pure structural checks on CapabilityResult (1.3.2).
> - **SchemaValidator** (3.5.2) **reads** output JSON Schema from CapabilityContract (1.3.3). SchemaCompiler cache is per-contract.
> - **SemanticValidator** (3.5.3) **reads** SessionState beliefs via ISessionStateReader (5.1.1) for grounding checks. Only runs for agent/prompt providers (skip_semantic=True for tools).
> - **ValidationFallback** (3.5.4) **emits** `k1.fabric.output.validation.failed.v1` via IEventPort (5.1.2) on rejection.
> - **Pipeline flow**: Provider result -> StructuralValidator -> SchemaValidator -> SemanticValidator -> return (or reject via fallback).
> - **Depends on**: Types (1.3.x), ISessionStateReader (5.1.1) for semantic tier, IEventPort (5.1.2) for failure events.
> - **Consumed by**: FabricFacade.execute() (5.3.2).
> - **Injection**: FabricFactory constructs pipeline with state_reader + event_port. Semantic tier optional (disabled for standalone mode).

### Epic 3.6: Health Checker Service

**Goal**: Implement provider health monitoring and availability tracking. Directory structure lists `health/health_checker.py` and `availability_tracker.py` but no implementation issues existed.

> **Reference**: `k1_cognitive_architecture_skeleton.mmd` -- Provider health monitoring, proactive gap detection.
> **Gap Coverage**: Directory structure listed health/ files with zero implementation issues.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 3.6.1 | Implement HealthChecker | DONE | k1/fabric/health/health_checker.py | Periodic health checks for all registered providers. Config: check_interval_s (default 30s per provider type, configurable). Flow: (1) iterate registered providers, (2) call `provider.health_check()`, (3) update ProviderHealth status, (4) emit `k1.fabric.provider.health.changed.v1` on state change. Handle: timeout (mark DEGRADED), failure (mark OFFLINE after consecutive failures threshold), recovery (OFFLINE -> DEGRADED -> ONLINE progression). |
| 3.6.2 | Implement AvailabilityTracker | DONE | k1/fabric/health/availability_tracker.py | Tracks ONLINE/DEGRADED/OFFLINE state per provider with transition history. Methods: `update_state(provider_id, new_state)`, `get_state(provider_id) -> Availability`, `get_transitions(provider_id) -> list[StateTransition]`. Integrates with Registry's `update_availability()`. Provides data for proactive gap detection. |
| 3.6.3 | Wire health checks into Circuit Breaker | DONE | k1/fabric/health/health_checker.py | HealthChecker consumes circuit breaker state changes. When CB opens: trigger immediate health check. When health check succeeds: signal CB to try HALF_OPEN. Bidirectional: CB informs health, health informs CB. Prevents unnecessary CB timeout waiting when provider recovers quickly. |

> **Wiring**:
>
> - **HealthChecker** (3.6.1) **iterates** all providers from ProviderRegistry (3.1.1). Calls provider.health_check() (3.3.1 interface).
> - **HealthChecker** **calls** AvailabilityTracker.update_state() (3.6.2) on state change. **Emits** `k1.fabric.provider.health.changed.v1` via IEventPort (5.1.2).
> - **AvailabilityTracker** (3.6.2) **calls** Registry.update_availability() (2.2.5) to update capability availability in CapabilityRegistry.
> - **Bidirectional CB wiring** (3.6.3): HealthChecker subscribes to CB state changes. CB OPEN -> immediate health check. Health success -> signal CB HALF_OPEN. This creates a **circular dependency** resolved by: HealthChecker holds reference to CB map, CB holds reference to HealthChecker callback. Both injected by FabricFactory.
> - **Depends on**: ProviderRegistry (3.1.1), CircuitBreaker (3.4.1), IEventPort (5.1.2), AvailabilityTracker (3.6.2), CapabilityRegistry (2.2.5).
> - **Consumed by**: FabricFactory startup (5.3.1) starts the health check loop. AvailabilityTracker data consumed by HardFilter (4.1.2).
> - **Injection**: FabricFactory constructs HealthChecker with provider_registry, circuit_breakers, event_port. Starts periodic loop. AvailabilityTracker receives registry reference.
> - **Circular dependency resolution**: FabricFactory creates both CB and HealthChecker, then wires callbacks bidirectionally after construction.

---

## Milestone 4: Retrieval + Context + Agent Factory + Meta-Agent Creation

> **Goal**: Implement Semantic Retrieval Engine (Subsystem 3), Context Builder (Subsystem 7), Agent Factory, and Meta-Agent Creation. This completes all three Fabric Roles and enables dynamic agent composition.
>
> **Build Order Reference**: Phase 5 (Context Builder), Phase 6 (Retrieval), Phase 8 (Agent Factory), Phase 9 (Meta-Agent Creation).
>
> **Prerequisite**: M3 complete (Resolution and basic execution working).
> **Reference (Epic 4.5)**: `docs/plans/meta-agent-creation-integration-proposal.md` -- Meta-Agent Creation Integration Proposal.

### Epic 4.1: Semantic Retrieval Engine

**Goal**: Implement Role 1 -- Intelligent Retrieval for the Planner.

> **Reference**: `fabric_discussion.md` Section 8 -- Retrieval Pipeline (4 steps).

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 4.1.1 | Implement EmbeddingIndex | DONE | k1/fabric/retrieval/embedding_index.py | FAISS vector index for semantic search. Text to embed: `f"{contract.description} \| {' '.join(contract.capabilities)}"`. Operations: add_vector(contract_id, text), remove_vector(contract_id), search(query_vector, k) -> list[(contract_id, score)]. Support: flat L2 for <10K contracts, IVF for >10K. Incremental add/remove on register/unregister. Dimensionality matches embedding model output. |
| 4.1.2 | Implement HardFilter | DONE | k1/fabric/retrieval/hard_filter.py | Three hard rules (ANY fail = ELIMINATED): (1) Safety band: `capability.safety_band_min <= user_band`, (2) Availability: not OFFLINE (DEGRADED kept but penalized), (3) Input satisfiability: required_inputs satisfiable from params + SessionState + Planner can ask (relaxed: if MOST are satisfiable, keep it). Returns: `filtered_set (subset of registry)`. |
| 4.1.3 | Implement SoftRanker | DONE | k1/fabric/retrieval/soft_ranker.py | Composite scoring: `Score = (0.4 * semantic_similarity) + (0.3 * domain_match) + (0.15 * success_rate) + (0.15 * cost_latency_score)`. **semantic_similarity**: cosine(query_vector, capability_vector). **domain_match**: Jaccard(query_domains, capability_domains). **success_rate**: capability.success_rate_30d (default 0.5 if new). **cost_latency_score**: `1.0 - normalize(cost + latency/10000)`. DEGRADED penalty: multiply by 0.7. |
| 4.1.4 | Implement TopKSelector | DONE | k1/fabric/retrieval/top_k_selector.py | Select top K results from scored set (default K=10, max K=25). Each result includes full contract, input/output schemas, score, provider_type. Returns `list[ScoredCapability]`. |
| 4.1.5 | Implement RetrievalEngine | DONE | k1/fabric/retrieval/retrieval_engine.py | Full pipeline: (1) Embed query, (2) Hard filter, (3) Soft rank, (4) Top-K select. API: `discover_capabilities(domain, intent, safety_band, session_context, top_k)` -> RetrievalResult. `find_relevant_prompts(intent, domain, safety_band, top_k)` -> RetrievalResult. Performance target: <20ms for 10K caps, <50ms for 100K caps. |

> **Wiring**:
>
> - **EmbeddingIndex** (4.1.1) **receives** contract text from Registry.register() events. Index updated incrementally on register/unregister. Dimensionality decided by ADR 1.1.8. FAISS library dependency.
> - **HardFilter** (4.1.2) **reads** safety_band from CapabilityRequest, availability from AvailabilityTracker (3.6.2) / Registry (2.2.5). **Enforces** FAB-05 (filter before rank).
> - **SoftRanker** (4.1.3) **reads** EmbeddingIndex for semantic similarity, Registry for domain tags, Rolling metrics (2.2.6) for success_rate_30d. Composite scoring formula: 0.4 semantic + 0.3 domain + 0.15 success + 0.15 cost_latency.
> - **TopKSelector** (4.1.4) is stateless. Receives scored list, returns top K.
> - **RetrievalEngine** (4.1.5) is the **composite pipeline** called by FabricRetrieval (5.3.3). Chains: Embed -> HardFilter -> SoftRanker -> TopKSelector.
> - **Depends on**: CapabilityRegistry (2.2.1) for data, EmbeddingIndex (FAISS), AvailabilityTracker (3.6.2), ISessionStateReader (5.1.1) for context.
> - **Consumed by**: FabricRetrieval.discover_capabilities() (5.3.3), FabricRetrieval.find_relevant_prompts() (5.3.3), Planner (Role 1 consumer).
> - **Injection**: FabricFactory constructs RetrievalEngine with registry, embedding_index, availability_tracker.

### Epic 4.2: Context Builder

**Goal**: Assemble execution context for agents and tool calls from SessionState, within token budget.

> **Reference**: `fabric_discussion.md` Section 12 -- Context Assembly Flow.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 4.2.1 | Implement ContextBuilder | DONE | k1/fabric/core/context_builder.py | 6-step flow: (1) Read contract required_context + optional_context, (2) Fetch from SessionState via ISessionStateReader (multi-reader, lock-free), (3) Inject request params, (4) Resolve prompt template (if applicable), (5) Apply token budget (128K), (6) Package ExecutionContext. Handle: optional section missing (skip), required section missing (log warning, continue with partial). |
| 4.2.2 | Implement ContextBudget | DONE | k1/fabric/core/context_budget.py | Token budget manager. Budget allocation: system prompt (2K-5K), compiled prompt (500-2K), SessionState sections (10K-40K), request params (1K-5K), tool results (5K-20K), response headroom (2K-8K). Compression strategy when over budget: (1) drop optional_context first, (2) truncate history_recent to last 3 turns, (3) summarize beliefs_active (drop low-confidence), (4) summarize scoreboard (keep only current QUD), (5) emergency: drop all WARM, keep HOT only. Ceiling: 128K tokens. |
| 4.2.3 | Implement token counting | DONE | k1/fabric/core/context_budget.py | Token counting utility. `count_tokens(text) -> int`. Support: tiktoken (if available) or approximate (chars/4 heuristic). Used by ContextBudget to enforce ceiling. Must be fast (<1ms for typical context). |

> **Wiring**:
>
> - **ContextBuilder** (4.2.1) **reads** SessionState via ISessionStateReader (5.1.1) -- multi-reader, lock-free. **Reads** CapabilityContract.required_context and optional_context (1.3.3). **Resolves** prompt templates via IPromptSystemPort (5.1.5).
> - **ContextBudget** (4.2.2) is **internal to** ContextBuilder. Applies 5-level compression strategy when over 128K ceiling. **Enforces** FAB-08.
> - **Token counting** (4.2.3) uses tiktoken or chars/4 heuristic. No external port. Fast (<1ms).
> - **ContextBuilder output**: ExecutionContext (1.3.8) is **consumed by** ALL providers via execute(request, context, trace_id) method (3.3.1 protocol).
> - **Depends on**: ISessionStateReader (5.1.1), IPromptSystemPort (5.1.5), types from M1.
> - **Consumed by**: FabricFacade.execute() (5.3.2) -- context built before provider execution. AgentFactory (4.3.1) step 6 -- initial context for agent.
> - **Injection**: FabricFactory constructs ContextBuilder with state_reader + prompt_system ports injected.

### Epic 4.3: Agent Factory

**Goal**: Implement the agent instantiation and lifecycle management system.

> **Reference**: `fabric_discussion.md` Section 13 -- Agent Factory (8-step flow).
> **Reference**: ADR-0005 (Agent Lifecycle states).

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 4.3.1 | Implement AgentFactory | DONE | k1/fabric/providers/agent_provider.py | 8-step instantiation: (1) Load YAML template, (2) Create MPSC Mailbox (WFQ INTERACTIVE priority), (3) Grant LLM access via IModelGatewayPort, (4) Grant SessionState read access (declared sections only, lock-free), (5) Scope tool access (tools_granted from contract, override from plan step, strict enforcement), (6) Build initial context via ContextBuilder, (7) Instantiate Agent object, (8) Start lifecycle: PENDING -> WARMING -> ACTIVE -> execute -> IDLE/DRAINING -> TERMINATED. |
| 4.3.2 | Implement Agent class | DONE | k1/fabric/providers/agent_provider.py | Agent object: id (UUID), contract (AgentContract), mailbox, llm_handle, state_reader, tool_scope, context, lifecycle_state. Methods: `warm_up()`, `execute(params) -> CapabilityResult`, `drain()`, `terminate()`. Lifecycle: PENDING -> WARMING (model preload) -> ACTIVE (executing) -> IDLE (pool, 60s TTL) -> DRAINING -> TERMINATED. |
| 4.3.3 | Implement Agent Pool (reuse) | DONE | k1/fabric/providers/agent_provider.py | IDLE pool for agent reuse. AgentPool keyed by contract name, FIFO reuse, configurable max_pool_size (default 5), idle_ttl_s (60s), sweep_interval_s (15s). AgentPoolConfig frozen dataclass. put() transitions ACTIVE/IDLE agents, evicts oldest at capacity. get() pops+reactivates, skips expired. sweep() TTL eviction. drain_all() shutdown. AgentFactory checks pool before spawning (pool hit = reuse without warm_up), pools agent after success. Thread-safe via RLock. 76 tests. |
| 4.3.4 | Implement Delta emission pattern | DONE | k1/fabric/providers/agent_provider.py | AgentDelta frozen dataclass (agent_id, delta_type, section, key, value, op=set/append/delete, timestamp_ms, trace_id) with to_dict/from_dict. DeltaEmitter batched emission with 500ms window (DELTA_BATCH_WINDOW_MS), LWW merge on (section,key), thread-safe Lock. emit/flush/flush_if_ready. DELTA_TOPIC_PATTERN="k1.agent.{agent_id}.delta.v1". Agent.execute() prefers DeltaEmitter over raw IDeltaBusPort. AgentFactory creates DeltaEmitter per agent when delta_bus configured. 76 tests. |
| 4.3.5 | Complete AgentProvider (full) | DONE | k1/fabric/providers/agent_provider.py | Replaced M3 stub with full implementation. AgentTemplateNotFoundError + AgentTimeoutError exceptions. DEFAULT_AGENT_TIMEOUT_MS=30000._execute() uses asyncio.wait_for for timeout enforcement, pattern-matches factory errors (template not found, model loading, tool scope violation). health_check() probes factory+gateway (HEALTHY/DEGRADED/UNKNOWN). shutdown() drains+terminates tracked agents + factory pool. track_agent/untrack_agent thread-safe lifecycle tracking. _resolve_timeout() priority: request params > default. 78 exports. 60 tests. |

> **Wiring**:
>
> - **AgentFactory** (4.3.1) is the **most heavily wired** component in Fabric. 8-step instantiation uses:
>   - Step 1: YAML template from AgentContract (1.3.4) loaded by parse_contract (2.1.6).
>   - Step 2: FabricMailbox (4.4.1) for MPSC communication (WFQ INTERACTIVE priority).
>   - Step 3: IModelGatewayPort (5.1.4) to grant LLM access. Capability-driven model selection.
>   - Step 4: ISessionStateReader (5.1.1) for declared read-only sections.
>   - Step 5: ToolScope (3.2.6) from PolicyEngine to enforce tools_granted[] (FAB-07).
>   - Step 6: ContextBuilder (4.2.1) for initial ExecutionContext.
>   - Step 7-8: Agent object instantiation + lifecycle PENDING -> WARMING -> ACTIVE.
> - **Agent** (4.3.2) lifecycle: PENDING -> WARMING (model preload via IModelGatewayPort) -> ACTIVE -> IDLE (pool, 60s TTL) -> DRAINING -> TERMINATED.
> - **Agent Pool** (4.3.3) reuses IDLE agents for same contract type. Keyed by contract name.
> - **Delta emission** (4.3.4): Agents NEVER write SessionState (FAB-01). Emit deltas via IDeltaBusPort (5.1.6) -> Delta Bus -> Concierge -> MutationGuard -> SessionState. **Enforces** FAB-01.
> - **AgentProvider** (4.3.5) replaces M3 stub. Called by ProviderFactory (3.1.4) for agent.* capability types.
> - **Depends on**: IModelGatewayPort (5.1.4), ISessionStateReader (5.1.1), IDeltaBusPort (5.1.6), ContextBuilder (4.2.1), ToolScope (3.2.6), FabricMailbox (4.4.1), AgentContract (1.3.4).
> - **Consumed by**: ProviderFactory (3.1.4) via AgentProvider.
> - **Injection**: FabricFactory constructs AgentFactory with all 4 ports + context_builder + tool_scope injected.

### Epic 4.4: Fabric Mailbox & Concurrency Model

**Goal**: Implement the FABRIC_MAILBOX with WFQ REALTIME priority scheduling from the K1 actor model.

> **Reference**: `k1_cognitive_architecture_skeleton.mmd` -- FABRIC_MAILBOX, WFQ scheduling, ADR 1.1.9.
> **Gap Coverage**: Architecture defines FABRIC_MAILBOX with WFQ REALTIME priority. ADR 1.1.9 decides mailbox model. No implementation issues existed.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 4.4.1 | Implement FabricDispatcher | DONE | k1/fabric/concurrency/dispatcher.py | Per FAB-003 (Accepted): No FABRIC_MAILBOX. FabricDispatcher with asyncio.Semaphore(max_concurrent=10) for bounded parallelism. FabricDispatcherConfig frozen dataclass. BackpressureLevel enum: NORMAL/WARNING/SHEDDING/SATURATED. DispatchResult wraps CapabilityResult + wait_ms + backpressure_at_entry. DispatcherHealth snapshot with to_dict(). DispatcherOverloadedError/DispatcherShutdownError. dispatch() flow: shutdown check -> backpressure reject -> semaphore acquire -> execute -> release. Per-priority in-flight tracking. Event emission on level transitions. Graceful shutdown drains all permits. Thread-safe via RLock. 91 tests. |
| 4.4.2 | Implement TimeoutGuard and backpressure | DONE | k1/fabric/concurrency/timeout.py | TimeoutGuard for deadline enforcement. TimeoutGuardConfig (default_timeout_ms, max_timeout_ms). DeadlineExceededError (agent_id, timeout_ms, retriable=True). resolve_timeout() priority: request params > default > max cap. execute_with_guard() raises DeadlineExceededError on timeout. execute_safe() returns CapabilityResult.failure on timeout. Stats tracking (total_guarded, total_exceeded, total_succeeded). Backpressure signals: WARNING at 80% -> emit k1.fabric.pressure.warning.v1, SHEDDING at 95% -> reject BACKGROUND, SATURATED at 100% -> reject all. 91 tests. |

> **Wiring**:
>
> - **FabricMailbox** (4.4.1) is the **entry point** for production-mode request ingestion. CapabilityRequest enters via mailbox -> dequeued by priority -> handed to FabricFacade.execute().
> - **Backpressure** (4.4.2) **emits** `k1.fabric.pressure.warning.v1` via IEventPort (5.1.2) at 80% depth. Rejects BACKGROUND at 95%, rejects ALL at 100%.
> - **Standalone mode bypass**: FabricFactory.create_standalone() does NOT create a mailbox. Requests go directly to FabricFacade.execute(). Production mode uses mailbox.
> - **Agent mailboxes** are separate: Each spawned Agent (4.3.2) gets its own MPSC mailbox from FabricMailbox system with INTERACTIVE priority.
> - **ADR dependency**: ADR 1.1.9 decides concurrency model. If mailbox-based actor model is selected, this epic is critical path. If simple async/await model, mailbox becomes optional.
> - **Depends on**: IEventPort (5.1.2) for backpressure events, types from M1.
> - **Consumed by**: FabricFactory.create_with_ports() production mode (5.3.1). AgentFactory step 2 (4.3.1).
> - **Injection**: FabricFactory creates FabricMailbox and wires it as request ingestion layer before FabricFacade.

### Epic 4.5: Meta-Agent Creation

**Goal**: Enable dynamic agent creation where Planner discovers tools/prompts (read-only) and plans agent specs, then Orchestrator executes build_agent DAG steps to compose and register new agents via Fabric.

> **Reference**: `docs/plans/meta-agent-creation-integration-proposal.md` -- PART 1 (Option A).
> **Related ADRs**: ADR-0005 (Agent Lifecycle), ADR-K004 (Capability Fabric Adaptation).
> **Gap Coverage**: Architecture defines Agent Factory (Role 3) but lacks runtime agent composition and dynamic creation from discovered capabilities.
> **PLAN-06 compliance**: Planner NEVER executes write operations. Planner discovers (read-only), commits a DAG. Orchestrator executes all steps including `tool.write.build_agent` and `tool.execute.{created_agent}`.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 4.5.1 | Implement AgentSpecValidator | NEW | k1/fabric/core/agent_builder.py | `AgentSpecValidator` class. Methods: `validate(spec: dict) -> AgentSpecValidationResult` (frozen dataclass: valid: bool, errors: list[str], warnings: list[str]), `validate_or_raise(spec: dict) -> None` (raises `AgentSpecValidationError(errors: list[str])`). 7 validation rules: (1) name regex `^agent\\.execute\\.[a-z][a-z0-9_]+$`, (2) tools_granted[] verified via Registry.contains() (2.2.3) -- rejects unknown tools, (3) required_context from allowed set {beliefs_active, interaction_history, task_context, rhythm_state, active_plans, pending_clarifications}, (4) prompt_template resolves via IPromptSystemPort.resolve() (5.1.5) when specified -- rejects unknown templates, (5) domain tags non-empty and no duplicates (restricted domain check deferred to 4.5.5 SecurityContext), (6) safety_band valid SafetyBand enum value from types.py (1.3.3), (7) budget ranges: llm_budget_tokens [512..32768], max_tool_calls [1..50], max_execution_time_ms [1000..60000]. Constructor injection: `registry: CapabilityRegistry` (2.2.1), `prompt_system: IPromptSystemPort` (5.1.5). Thread-safe: stateless validator, no mutable state, all methods are pure functions over inputs. ~150 lines. ~40 tests. |
| 4.5.2 | Implement tool.write.build_agent (MCP Tool) | NEW | k1/contracts/tools/build_agent.yaml + k1/fabric/core/agent_builder.py | **Contract YAML** (`k1/contracts/tools/build_agent.yaml`): name=`tool.write.build_agent`, version=1.0.0, domain=[META, AGENT_CREATION], safety_band_min=AMBER, provider_type=MCP. Required inputs: agent_name(str), description(str), tools_granted(list[str]), prompt_template(str), domain(list[str]). Optional inputs: required_context(list[str], default=all 6 sections), llm_budget_tokens(int, default=8192), safety_band_min(str, default=GREEN), max_tool_calls(int, default=10), max_execution_time_ms(int, default=30000), ephemeral(bool, default=true), session_scoped(bool, default=true). Output schema: {agent_name: str, status: str, errors: list[str]}. **Implementation** `BuildAgentHandler` class with 8-step execute(): (1) Parse+validate inputs against contract schema (ContractValidator 2.1.1), (2) AgentSpecValidator.validate_or_raise(spec) (4.5.1), (3) SecurityContext.validate_meta_operation(request, spec) (4.5.5), (4) AgentComposer.compose_agent(name, desc, domain).add_tool(each)...build() (4.5.4) returns CapabilityContract, (5) Registry.register(contract, skip_validation=False) (2.2.2), (6) Registry.register_created_agent(contract, ephemeral, created_by="orchestrator", session_scoped) (4.5.6), (7) EventEmitter.emit_agent_created(agent_name, created_by, tools_granted, domain, prompt_template, ephemeral, session_id, trace_id) (4.5.7), (8) Return CapabilityResult.success(data={agent_name, status:"registered"}) or CapabilityResult.failure(error="validation_failed", details={errors:[...]}). `BuildAgentError` exception for unrecoverable build failures. Constructor injection: validator(AgentSpecValidator 4.5.1), composer(AgentComposer 4.5.4), registry(CapabilityRegistry 2.2.1), security(SecurityContext 3.2.1), emitter(EventEmitter 5.4.2). Registered in MCPProvider (3.3.1) handler_registry as local handler for `tool.write.build_agent`. Resolved via standard Resolver pipeline (3.1.5) -- appears as normal AMBER-band MCP capability. **NOTE**: Orchestrator-executed DAG step, NOT a Planner tool (PLAN-06). ~200 lines. ~50 tests. |
| 4.5.3 | Discovery tool wrappers (MCP-callable) | NEW | k1/fabric/core/discovery_tools.py + k1/contracts/tools/ | Two MCP tool contracts + thin handler classes. (1) `k1/contracts/tools/discover_capabilities.yaml`: name=`tool.read.discover_capabilities`, version=1.0.0, domain=[META, DISCOVERY], safety_band_min=GREEN, provider_type=MCP. Inputs: domain(list[str]), intent(str). Optional: top_k(int, default=10), safety_band(str, default=GREEN). Output: list[{name: str, version: str, domain: list[str], description: str, required_inputs: list, output: dict, provider_type: str, safety_band_min: str}]. `DiscoverCapabilitiesHandler.execute()`: delegates to FabricRetrieval.discover_capabilities(domain, intent, top_k, safety_band) (5.3.3), maps each ScoredCapability to full contract JSON via ContractValidator.to_dict() (2.1.1). (2) `k1/contracts/tools/find_prompts.yaml`: name=`tool.read.find_prompts`, version=1.0.0, domain=[META, DISCOVERY], safety_band_min=GREEN. Inputs: intent(str). Optional: domain(list[str]), top_k(int, default=5). Output: list[{name: str, variables: list[str], output_format: str, compatible_agents: list[str]}]. `FindPromptsHandler.execute()`: delegates to FabricRetrieval.find_relevant_prompts(intent, domain, top_k) (5.3.3). Both registered in MCPProvider (3.3.1) handler_registry as local handlers. Contracts auto-registered by ModuleLoader (2.3.1) on startup scan of `k1/contracts/tools/` directory. GREEN-band read-only tools, safe for Planner to invoke via Orchestrator DAG. ~100 lines. ~30 tests. |
| 4.5.4 | Implement AgentComposer | NEW | k1/fabric/core/agent_builder.py | `AgentComposer` class with builder pattern. Static factory: `compose_agent(name: str, description: str, domain: list[str]) -> AgentComposer` returns new builder instance. Builder methods (all return self for chaining): `add_tool(tool_name: str)` validates tool exists via Registry.contains() (2.2.3) raises ValueError if missing, `set_prompt(template_name: str)` validates via IPromptSystemPort.resolve() (5.1.5) raises ValueError if unknown, `set_context(required: list[str], optional: Optional[list[str]] = None)`, `set_budget(llm_tokens: int = 8192, max_tool_calls: int = 10, max_execution_ms: int = 30000)`, `set_safety_band(band: str = "GREEN")`, `set_lifecycle(ephemeral: bool = True, session_scoped: bool = True)`, `build() -> CapabilityContract` terminal method -- runs cross-field validation, returns frozen CapabilityContract (1.3.3) with provider_type=AGENT. `AgentCompositionError` exception for build-time validation failures (missing required fields, incompatible tool+band combinations). Factory method: `from_discovery_result(capabilities: list[ScoredCapability], intent: str, prompt_template: str) -> AgentComposer` auto-selects tools from capabilities list, auto-unions domains, auto-computes safety_band as max() of individual tool bands. Constructor injection: `registry: CapabilityRegistry` (2.2.1), `prompt_system: IPromptSystemPort` (5.1.5). Thread-safe: builder instances are per-call, no shared mutable state. ~180 lines. ~45 tests. |
| 4.5.5 | Safety: Meta-operation policy rules | NEW | k1/fabric/policy/security_context.py | Extend SecurityContext (3.2.1) with `validate_meta_operation(request: CapabilityRequest, agent_spec: dict) -> PolicyResult`. 5 hard gates (ANY fail returns PolicyResult(allowed=False, score=0.0, reasons=[...])): (1) Capability band gate: `tool.write.build_agent` requires caller SafetyBand >= AMBER via request.security_context.get_safety_band() (3.2.1), (2) Safety band inheritance: agent_spec["safety_band_min"] cannot exceed caller safety band (no escalation -- GREEN caller cannot create AMBER agent), (3) Restricted domain gate: agent_spec["domain"] cannot contain "META", "SECURITY", or "ADMIN" (prevents recursive meta-agents), (4) Tool grant recursion gate: agent_spec["tools_granted"] cannot contain "tool.write.build_agent" or any "tool.write.*" meta-tool (no recursive tool-grant), (5) Agent depth gate: if any tool in tools_granted has provider_type=AGENT (checked via Registry.lookup() 2.2.3), reject (depth=1, leaf nodes only -- no agent chains). On ANY violation: emit `k1.fabric.meta.operation.blocked.v1` via EventEmitter (4.5.7) with violation_type and request details. Integrated into PolicyEngine.evaluate() (3.2.5) as additional hard gate triggered ONLY for capabilities matching `tool.write.*` pattern. Constructor inherits existing SecurityContext deps (state_reader: ISessionStateReader 5.1.1) + adds emitter: EventEmitter (5.4.2). Thread-safe: validate_meta_operation is pure function over inputs + registry lookups (registry has RLock). ~120 lines. ~35 tests. |
| 4.5.6 | Lifecycle: Ephemeral vs Persistent agents | NEW | k1/fabric/core/registry.py | Extend CapabilityContract (1.3.3) with 4 optional frozen fields: `ephemeral: bool = True`, `created_by: str = ""` (empty for YAML-loaded, "orchestrator" for build_agent created), `created_at_iso: str = ""`, `session_scoped: bool = True`. Extend CapabilityRegistry (2.2.1) with: (1) `_created_agents: dict[str, CapabilityContract]` index, (2) `register_created_agent(contract: CapabilityContract, ephemeral: bool, created_by: str, session_scoped: bool) -> None` sets lifecycle metadata + inserts_created_agents + calls register() (2.2.2), (3) `list_created_agents() -> list[CapabilityContract]` returns defensive copy, (4) `remove_expired_agents(session_id: str) -> int` bulk-removes session-scoped ephemeral agents, emits k1.fabric.agent.expired.v1 per agent via EventEmitter (4.5.7), returns count removed, (5) `is_created_agent(name: str) -> bool`. Auto-YAML serialization: if ephemeral=False, `AgentContractSerializer.to_yaml(contract: CapabilityContract) -> str` writes to `k1/contracts/agents/generated/{name}.yaml`. ModuleLoader (2.3.1) auto-discovers generated YAMLs on next scan/reload. Thread-safe:_created_agents protected by existing Registry._lock (RLock from 2.2.1). ~100 lines added to registry.py. ~30 tests. |
| 4.5.7 | Event: Agent creation lifecycle events | NEW | k1/fabric/events/fabric_events.py | 3 frozen dataclass event payloads + 3 topic constants + 3 EventEmitter methods. (1) `AgentCreatedEvent(agent_name: str, created_by: str, tools_granted: tuple[str, ...], domain: tuple[str, ...], prompt_template: str, ephemeral: bool, session_id: str, trace_id: str, timestamp_iso: str)` with `to_dict() -> dict`. (2) `AgentExpiredEvent(agent_name: str, created_at_iso: str, expired_at_iso: str, invocations: int, trace_id: str)` with `to_dict() -> dict`. (3) `MetaOperationBlockedEvent(operation: str, violation_type: str, requested_by: str, details: dict[str, str], trace_id: str)` with `to_dict() -> dict`. Topic constants: `AGENT_CREATED = "k1.fabric.agent.created.v1"`, `AGENT_EXPIRED = "k1.fabric.agent.expired.v1"`, `META_OP_BLOCKED = "k1.fabric.meta.operation.blocked.v1"`. EventEmitter (5.4.2) methods: `emit_agent_created(agent_name, created_by, tools_granted, domain, prompt_template, ephemeral, session_id, trace_id)`, `emit_agent_expired(agent_name, created_at, invocations, trace_id)`, `emit_meta_blocked(operation, violation, requested_by, details, trace_id)`. All enforce cognitive_trace_id per FAB-09. ~60 lines. ~20 tests. |
| 4.5.8 | Define AgentResponsePayload type | NEW | k1/fabric/types.py | Frozen dataclass `AgentResponsePayload`: `answer: str`, `confidence: float`, `domain: tuple[str, ...]`, `sources: tuple[dict, ...]`, `domain_data: dict[str, Any]` (freeform per domain -- e.g., health: {vitals, medications}, finance: {accounts, transactions}), `follow_up_needed: bool`, `follow_up_suggestion: str`, `reasoning_trace: tuple[str, ...]`, `tools_used: tuple[str, ...]`, `k0_queries_made: int`. Methods: `to_dict() -> dict` (JSON-safe serialization), `from_dict(cls, data: dict) -> AgentResponsePayload` (classmethod factory with type validation), `validate() -> bool` (confidence in [0.0, 1.0], domain non-empty, answer non-empty). **Integration**: CapabilityResult.data["payload"] contains `payload.to_dict()`. AgentFactory.execute() (4.3.2) wraps agent output in AgentResponsePayload before returning CapabilityResult.success(data={"payload": payload.to_dict()}). **Concierge consumption** (DELIVERING state): reads result.data["payload"]["answer"], result.data["payload"]["domain_data"], result.data["payload"]["sources"]. Multi-agent merging: Concierge aggregates multiple AgentResponsePayload instances via existing result aggregation logic. ~50 lines. ~25 tests. |
| 4.5.9 | Orchestrator ParamResolver: dynamic capability resolution | NEW | k1/orchestrator/ (Orchestrator scope) | Enhance Orchestrator ParamResolver `resolve_step(step: dict, completed_results: dict[str, CapabilityResult]) -> dict`. Current behavior: resolves `$step_id.result.path` references in `params` dict values only. **Enhancement**: ALSO resolve `$step_id.result.path` in step `capability` field. Logic: (1) existing param resolution unchanged, (2) NEW: if `step["capability"].startswith("$")`, split on ".", lookup completed_results[step_id], traverse .result.path to extract string value, replace capability field with resolved string, (3) if resolved capability not in Registry: raise `UnresolvedCapabilityError(step_id: str, capability_ref: str, resolved_value: str)`. **Pattern**: build_agent step returns CapabilityResult.success(data={agent_name: "agent.execute.diabetes_companion"}), next DAG step has `capability: "$step_1a.result.agent_name"`, ParamResolver resolves to `"agent.execute.diabetes_companion"`, Fabric resolves+executes via standard pipeline. **NOTE**: Orchestrator scope, NOT Fabric scope. Fabric receives the already-resolved capability name as a standard CapabilityRequest. ~30 lines added to resolver. ~20 tests. |

> **Wiring (production-grade integration)**:
>
> - **AgentSpecValidator** (4.5.1): Constructor injection: `registry: CapabilityRegistry` (2.2.1), `prompt_system: IPromptSystemPort` (5.1.5). **Depends on**: Registry.contains() (2.2.3) for tools_granted validation, IPromptSystemPort.resolve() (5.1.5) for prompt_template validation. **Consumed by**: BuildAgentHandler (4.5.2) step 2. No new ports required. Stateless validator -- no thread-safety concerns, all methods are pure functions.
> - **BuildAgentHandler** (4.5.2): Constructor injection: `validator: AgentSpecValidator` (4.5.1), `composer: AgentComposer` (4.5.4), `registry: CapabilityRegistry` (2.2.1), `security: SecurityContext` (3.2.1), `emitter: EventEmitter` (5.4.2). Registered in MCPProvider (3.3.1) handler_registry for name `tool.write.build_agent`. Contract YAML auto-loaded by ModuleLoader (2.3.1) from `k1/contracts/tools/`. Resolved via standard Resolver pipeline (3.1.5) -- appears as normal AMBER-band MCP tool to Orchestrator. **Executed by Orchestrator** DAG Executor (not Planner) per PLAN-06. Execution path: Orchestrator -> Fabric.execute(CapabilityRequest("tool.write.build_agent", params)) -> Resolver -> MCPProvider -> BuildAgentHandler.execute() -> CapabilityResult.
> - **Discovery tool wrappers** (4.5.3): `DiscoverCapabilitiesHandler` and `FindPromptsHandler` delegate to FabricRetrieval (5.3.3). Constructor injection: `fabric_retrieval: FabricRetrieval` (5.3.3). Contract YAMLs in `k1/contracts/tools/` auto-loaded by ModuleLoader (2.3.1). Registered in MCPProvider (3.3.1) as local handlers. GREEN-band read-only tools, safe for Planner to invoke via Orchestrator DAG steps. No state mutation.
> - **AgentComposer** (4.5.4): Constructor injection: `registry: CapabilityRegistry` (2.2.1), `prompt_system: IPromptSystemPort` (5.1.5). Builder instances are per-call (no shared state). Validated incrementally: each add_tool() checks Registry.contains(), set_prompt() checks IPromptSystemPort.resolve(). **Consumed by**: BuildAgentHandler (4.5.2) step 4. from_discovery_result() factory enables Planner-planned agent specs to auto-compose.
> - **Meta-operation policy** (4.5.5): Extends SecurityContext (3.2.1) with validate_meta_operation() method. Called within PolicyEngine.evaluate() (3.2.5) as additional hard gate triggered ONLY for capabilities matching `tool.write.*` pattern. **Depends on**: Registry.lookup() (2.2.3) for provider_type check (depth=1 gate), EventEmitter (5.4.2) for blocked event emission. No new port consumption. Thread-safe: SecurityContext is frozen dataclass, validate_meta_operation is pure function over inputs + registry lookups.
> - **Lifecycle** (4.5.6): Extends CapabilityContract (1.3.3) with 4 optional fields (backward-compatible: defaults ephemeral=True, created_by="", session_scoped=True). Extends CapabilityRegistry (2.2.1) with _created_agents dict. Thread-safe: protected by existing Registry._lock (RLock). Writes to `k1/contracts/agents/generated/` for persistent agents. ModuleLoader (2.3.1) auto-discovers generated YAMLs on scan. **Consumed by**: BuildAgentHandler (4.5.2) step 6 (register_created_agent), session cleanup (remove_expired_agents).
> - **Events** (4.5.7): 3 new frozen dataclass payloads + 3 topic constants + 3 EventEmitter (5.4.2) wrapper methods. All enforce cognitive_trace_id per FAB-09. **Emitted by**: BuildAgentHandler (4.5.2) step 7 (agent.created), SecurityContext.validate_meta_operation (4.5.5) on violation (meta.operation.blocked), Registry.remove_expired_agents (4.5.6) on cleanup (agent.expired). **Consumed by**: K1 Event Bus subscribers, Learning Loop, audit log.
> - **AgentResponsePayload** (4.5.8): Added to types.py (1.3.3) alongside existing types. No port consumption. **Integration point**: AgentFactory.execute() (4.3.2) wraps agent output in AgentResponsePayload before constructing CapabilityResult.success(data={"payload": payload.to_dict()}). **Consumed by**: Concierge DELIVERING state reads payload.answer + payload.domain_data + payload.sources. Multi-agent merging: Concierge aggregates multiple AgentResponsePayload instances.
> - **ParamResolver** (4.5.9): Orchestrator scope -- extends existing resolve_step() method. No new Fabric port dependencies. Pattern: `capability: "$step_id.result.path"` resolved from completed_results dict. UnresolvedCapabilityError on missing resolution. **Consumed by**: Orchestrator DAG Executor step resolution loop. Fabric receives already-resolved capability name.
> - **FabricFactory construction order update**: After existing step 19 (FabricFacade), add: **Step 20**: Create AgentSpecValidator(registry, prompt_system) + AgentComposer(registry, prompt_system) + BuildAgentHandler(validator, composer, registry, security_context, event_emitter); register build_agent handler in MCPProvider handler_registry. **Step 21**: Create DiscoverCapabilitiesHandler(fabric_retrieval) + FindPromptsHandler(fabric_retrieval); register both in MCPProvider handler_registry. No circular dependencies (all deps already created in steps 1-19).
> - **Test adapter integration**: TestBridge (5.2.1) supports build_agent tool execution in isolation. TestPromptSystem (5.2.5) provides mock prompt resolution for AgentSpecValidator (4.5.1) and AgentComposer (4.5.4). TestModelGateway (5.2.4) supports spawned agent LLM calls. No new test adapters required -- existing 8 adapters cover all ports consumed by Epic 4.5 components.
> - **Depends on (complete)**: CapabilityRegistry (2.2.1), Registry.contains/lookup (2.2.3), ContractValidator (2.1.1), ModuleLoader (2.3.1), SecurityContext (3.2.1), PolicyEngine (3.2.5), MCPProvider (3.3.1), Resolver (3.1.5), AgentFactory (4.3.1-4.3.5), EventEmitter (5.4.2), IEventPort (5.1.2), IPromptSystemPort (5.1.5), ISessionStateReader (5.1.1), FabricRetrieval (5.3.3), FabricFacade (5.3.2), types.py (1.3.3).
> - **Consumed by (complete)**: Orchestrator DAG Executor (build_agent as DAG step + dynamic capability resolution via 4.5.9), Planner (read-only discovery tools 4.5.3 for agent composition planning), Concierge DELIVERING (AgentResponsePayload 4.5.8 consumption and multi-agent result merging), Learning Loop (creation events 4.5.7 for adaptive recommendations), session cleanup (lifecycle 4.5.6 ephemeral removal).
> - **Phase 2 deferred to M9**: Runtime prompt template creation (killed in M4), ORCH-13 micro-replan for mid-DAG agent discovery, K0 direct integration (currently via Bridge through Fabric per BridgeProvider 3.3.4), workflow creation tools (tool.write.build_workflow), template recommendation engine, agent-to-agent delegation (depth > 1).

---

## Milestone 5: Ports, Adapters & Standalone Mode

> **Goal**: Define hexagonal port interfaces, implement production and test adapters, create factory methods, and wire event bus integration.
>
> **Pattern**: Same approach as SessionState M3 (5 ports + adapters + factory + standalone).

### Epic 5.1: Port Interfaces

**Goal**: Define all port interfaces that Fabric uses for external communication.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 5.1.1 | Define ISessionStateReader port | DONE | k1/fabric/ports/state_reader.py | Canonical @runtime_checkable Protocol. read_section(session_id, section) -> dict or None, read_sections(session_id, names) -> dict, get_snapshot(session_id) -> SessionSnapshot. SessionSnapshot frozen dataclass with has_section/get_section helpers, auto-populated section_names. Structurally compatible with all inline declarations (policy/ports.py, context_builder.py, semantic_validator.py, agent_provider.py). FAB-01 enforced (read-only, no write methods). 90 tests. |
| 5.1.2 | Define IEventPort port | DONE | k1/fabric/ports/event_port.py | Canonical @runtime_checkable Protocol. emit(topic, payload) fire-and-forget, subscribe(topic, handler) -> SubscriptionHandle, unsubscribe(handle) -> bool. SubscriptionHandle frozen dataclass (subscription_id, topic). Handler semantics: sync during emit, exceptions caught+logged, FAB-09 (cognitive_trace_id). Thread-safe emit, exception-safe handler dispatch. 90 tests. |
| 5.1.3 | Define IBridgePort port | DONE | k1/fabric/ports/bridge_port.py | Canonical @runtime_checkable Protocol. async send_command(operation, payload, trace_id, timeout_ms) -> BridgeCommandResult, async query(operation, selectors, trace_id, timeout_ms) -> BridgeCommandResult, async route_ifl(route: IFLRoute, payload, trace_id) -> BridgeCommandResult, is_available() -> bool, get_health() -> BridgeHealth. BridgeHealth frozen dataclass with is_full/is_degraded/is_offline helpers + to_dict. BridgeCommandResult with ok/fail static factories. IFLRoute with parse() for IFL address format (tool.execute.namespace.function). 90 tests. |
| 5.1.4 | Define IModelGatewayPort port | DONE | k1/fabric/ports/model_gateway.py | Canonical @runtime_checkable Protocol. IModelGatewayPort: create_handle(budget_tokens, model_preference, capabilities, trace_id)->ILLMHandle, is_model_loaded(model_id)->bool, list_models()->list[ModelInfo], find_model(required_capabilities)->Optional[str]. ILLMHandle Protocol: async generate(prompt, params)->str, model_id property, budget_tokens property. ModelCapability str enum (CHAT, TOOL_CALL, STRUCTURED, EMBED, VISION, BATCH). ModelInfo frozen dataclass with has_capability/has_all_capabilities/to_dict. Structurally compatible with inline preview in agent_provider.py. 112 tests (shared with 5.1.5, 5.1.6). |
| 5.1.5 | Define IPromptSystemPort port | DONE | k1/fabric/ports/prompt_system.py | Canonical @runtime_checkable Protocol. resolve(template_name)->Optional[PromptTemplate], compile(template, variables)->str. PromptTemplate frozen dataclass with has_variable/to_dict. to_dict() provides Dict compatibility with inline preview in context_builder.py. PORT ONLY -- Prompt System implementation out of scope. 112 tests (shared with 5.1.4, 5.1.6). |
| 5.1.6 | Define IDeltaBusPort port | DONE | k1/fabric/ports/delta_bus.py | Canonical @runtime_checkable Protocol. emit_delta(agent_id, delta_type, section, data)->None. Fire-and-forget, synchronous, thread-safe. DeltaPayload frozen dataclass with to_dict/from_args. Structurally compatible with inline IDeltaBusPort in agent_provider.py and DeltaEmitter usage. 112 tests (shared with 5.1.4, 5.1.5). |

> **Wiring**:
>
> - **Port interfaces are the hexagonal boundary** of the Fabric. ALL external communication goes through these 6 ports. No subsystem bypasses a port to reach infrastructure directly.
> - **ISessionStateReader** (5.1.1) is **consumed by**: PolicyEngine (3.2.2, 3.2.3), ContextBuilder (4.2.1), SemanticValidator (3.5.3), AgentFactory (4.3.1 step 4). Read-only (FAB-01). Production: SessionStateReaderAdapter (5.2.1). Test: TestSessionStateReaderAdapter (5.2.2).
> - **IEventPort** (5.1.2) is **consumed by**: Registry (2.2.2), ModuleLoader (2.3.2), CircuitBreaker state changes (3.4.1), HealthChecker (3.6.1), OutputValidation fallback (3.5.4), EventEmitter (5.4.2), FabricMailbox backpressure (4.4.2). Production: K1 EventBus adapter. Test: LocalEventAdapter (5.2.3) with capture mode.
> - **IBridgePort** (5.1.3) is **consumed by**: BridgeProvider (3.3.4) exclusively. Production: BridgeConnectionAdapter (5.2.8). Test: TestBridgeAdapter (5.2.4).
> - **IModelGatewayPort** (5.1.4) is **consumed by**: AgentFactory (4.3.1 step 3). Production: Model Hub adapter. Test: TestModelGatewayAdapter (5.2.5).
> - **IPromptSystemPort** (5.1.5) is **consumed by**: ContextBuilder (4.2.1 step 4). Production: Prompt System adapter (external module). Test: TestPromptSystemAdapter (5.2.6).
> - **IDeltaBusPort** (5.1.6) is **consumed by**: Agent.execute() (4.3.2) for delta emission. Production: Delta Bus adapter. Test: TestDeltaBusAdapter (5.2.7).
> - **Pattern**: All ports are Protocol classes (Python typing.Protocol). No ABC inheritance. Enforced by type checker.

### Epic 5.2: Adapters (Production + Test)

**Goal**: Implement adapters for each port -- production adapters for real infrastructure, test adapters for standalone/testing.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 5.2.1 | SessionStateReaderAdapter (production) | DONE | k1/fabric/adapters/sessionstate_reader.py | Wraps real SessionStateManager. Bound per-session at construction. Converts sections via to_dict() with raw-dict fallback. Discovers section names via get_all_section_sizes or static fallback list. Returns None/empty on KeyError/RuntimeError. Manager typed as Any (no import dependency). 78 tests in test_adapters_521_523.py. |
| 5.2.2 | TestSessionStateReaderAdapter (test) | DONE | k1/fabric/adapters/test_state_reader.py | In-memory Dict[session_id:section, data]. load/load_many/remove/clear helpers. section_count introspection. Thread-safe via RLock. Returns Fabric SessionSnapshot. No real SessionState dependency. Structural subtyping (no ABC inheritance). |
| 5.2.3 | LocalEventAdapter (reuse from SessionState) | DONE | k1/fabric/adapters/local_event.py | Fabric-specific LocalEventAdapter (not a wrapper — different handler signature). Synchronous dispatch for deterministic testing. Returns SubscriptionHandle from subscribe. capture_mode with enable/disable/drain/assert_emitted/clear_captured. Thread-safe via RLock (handlers called outside lock). subscription_count/handler_count/captured_count introspection. |
| 5.2.4 | TestBridgeAdapter | DONE | k1/fabric/adapters/test_bridge.py | In-memory K0 stub. Canned responses keyed by operation string. IFL responses keyed by address. Dynamic handlers (priority over canned). is_available/set_available/set_health. Capture mode with CapturedBridgeCall records. drain/assert_called/get_captured(method filter). call_count/command_count/query_count/ifl_count introspection. Thread-safe via RLock. Async send_command/query/route_ifl return BridgeCommandResult.fail on unavailable. 111 tests in test_adapters_524_526.py. |
| 5.2.5 | TestModelGatewayAdapter | DONE | k1/fabric/adapters/test_model_gateway.py | TestLLMHandle: round-robin responses, budget decrement, error_after, call_count/prompts introspection. TestModelGatewayAdapter: model catalog (add/remove/list/find), capability-driven routing (loaded preferred), create_handle tracks all handles, set_default_responses/set_error_after/clear. Thread-safe via RLock. No real LLM dependency. |
| 5.2.6 | TestPromptSystemAdapter | DONE | k1/fabric/adapters/test_prompt_system.py | In-memory dict of PromptTemplate. add_template (by parts or obj)/remove_template/clear/has_template/list_names. resolve() looks up by name, returns None if missing. compile() does {variable} string replacement, unresolved left as-is. resolve_count/compile_count/template_count introspection. Thread-safe via RLock. |
| 5.2.7 | TestDeltaBusAdapter | DONE | k1/fabric/adapters/test_delta_bus.py | CapturedDelta frozen dataclass (agent_id, delta_type, section, data, timestamp_ms, to_dict). emit_delta captures as CapturedDelta with deep-copy and epoch timestamp. get_deltas with filter by agent_id/delta_type/section (combinable). drain returns+clears. clear discards. assert_emitted with optional count (None=at least 1, 0=zero). delta_count/agent_ids introspection. Thread-safe via RLock. 74 tests in test_adapters_527_528.py (shared with 5.2.8). |
| 5.2.8 | BridgeConnectionAdapter (production) | DONE | k1/fabric/adapters/bridge_connection.py | Production adapter for IBridgePort. BridgeConnectionConfig (frozen: endpoint, default_timeout_ms, reconnect_interval_ms, max_reconnect_attempts). Pluggable client (typed Any — future bridge client). _probe_connection on init checks client.is_connected(). LOCAL COLD fallback: all operations return BridgeCommandResult.fail("k0_offline") when unavailable. Async send_command/query/route_ifl route through client when connected, mark disconnected on error. is_available/get_health with BridgeHealth from client. reconnect with throttle (reconnect_interval_ms) + max_reconnect_attempts. disconnect lifecycle. _mark_connected/_mark_disconnected atomic state transitions. Thread-safe via RLock. 74 tests in test_adapters_527_528.py (shared with 5.2.7). |

> **Wiring**:
>
> - **Adapters implement ports**. Each production adapter connects to real infrastructure. Each test adapter is self-contained.
> - **SessionStateReaderAdapter** (5.2.1) **wraps** real SessionStateManager. Injected into PolicyEngine, ContextBuilder, SemanticValidator, AgentFactory.
> - **TestSessionStateReaderAdapter** (5.2.2) **pre-loaded** with dict sections. Used by FabricFactory.create_standalone() and create_for_testing().
> - **LocalEventAdapter** (5.2.3) **reused** from SessionState module. capture_mode=True stores events for test assertions. Injected into Registry, ModuleLoader, EventEmitter, HealthChecker.
> - **TestBridgeAdapter** (5.2.4) **canned** responses for memory/IFL operations. is_available() configurable. Injected into BridgeProvider.
> - **TestModelGatewayAdapter** (5.2.5) **canned** LLM responses. Injected into AgentFactory.
> - **TestPromptSystemAdapter** (5.2.6) **static** prompt templates. Injected into ContextBuilder.
> - **TestDeltaBusAdapter** (5.2.7) **capture** mode for delta assertions. Injected into AgentFactory/Agent.
> - **BridgeConnectionAdapter** (5.2.8) is the **only production adapter** in this plan that connects to K0. All others connect to K1 infrastructure. Graceful degradation when Bridge unavailable.
> - **Pattern**: Constructor injection. FabricFactory selects adapter set based on factory method (standalone/testing/production). No service locator.

### Epic 5.3: Factory & Standalone Mode

**Goal**: Create factory methods for wiring Fabric with appropriate adapters.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 5.3.1 | Implement FabricFactory | DONE | k1/fabric/factory.py | Factory methods: `create_standalone()` (all test adapters, no external deps), `create_for_testing()` (capture mode events + test adapters), `create_with_ports(state_reader, event_port, bridge, model_gateway, prompt_system, delta_bus)` (custom adapter injection). Wire all subsystems: Registry, Resolver, PolicyEngine, ContextBuilder, Providers, RetrievalEngine, CircuitBreakers. 20-step dependency-safe construction in _construct_fabric(). _register_provider_handlers() for all 6 provider types (MCP, WASM, Bridge, Agent, Workflow, Concierge)._StubEmbeddingPort for standalone mode. 585 lines. |
| 5.3.2 | Implement FabricFacade (main API) | DONE | k1/fabric/fabric.py | The CapabilityFabric class from `fabric_discussion.md` Section 15. Methods: `async execute(request) -> CapabilityResult`, `async execute_batch(requests, strategy: BatchStrategy) -> list[CapabilityResult]`. **execute_batch() semantics**: `BatchStrategy` enum: PARALLEL (all at once, default), SEQUENTIAL (ordered), DAG (dependency-aware). Partial failure handling: each request independent, failed requests return CapabilityResult.failure() without blocking others. Ordering guarantee: results list matches input order regardless of execution order. Backpressure: batch size capped at max_batch_size (default 50). Critical for Orchestrator DAG wave execution where multiple capabilities execute in a single wave. Enforces FAB-03 (stateless per-request), FAB-04 (circuit breaker timeout), FAB-09 (event emission). Wire OutputValidationPipeline (Epic 3.5) into execution path after provider returns. Full 9-step execute() pipeline. DAG strategy with topological wave execution + cycle detection. Coerced data handling from validation pipeline. 1175 lines total in fabric.py. |
| 5.3.3 | Implement FabricRetrieval (retrieval API) | DONE | k1/fabric/fabric.py | Separate class for Role 1 API. Methods: `async discover_capabilities(domain, intent, safety_band, session_context, top_k) -> RetrievalResult`, `async find_relevant_prompts(intent, domain, safety_band, top_k) -> RetrievalResult`. Thin async delegate over RetrievalEngine. |
| 5.3.4 | Implement CapabilityRegistryAPI | DONE | k1/fabric/fabric.py | Registry management API: register, unregister, lookup (with version support), contains, list_all, list_by_domain, list_by_type, update_availability, update_metrics, reload, health. Thin wrapper over core Registry. |

> **Wiring**:
>
> - **FabricFactory** (5.3.1) is the **master wiring point** for the entire Fabric. It constructs ALL subsystems and wires ALL dependencies.
> - **FabricFactory construction order** (dependency-safe):
>   1. Create adapters (ports first -- no dependencies)
>   2. Create ContractValidator (2.1.1 -- no dependencies)
>   3. Create CapabilityRegistry (2.2.1 -- depends on validator + event_port)
>   4. Create ModuleLoader (2.3.1 -- depends on registry + event_port)
>   5. Create PolicyEngine (3.2.5 -- depends on state_reader)
>   6. Create ProviderRegistry (3.1.1) + ProviderFactory (3.1.4 -- depends on ports)
>   7. Create CircuitBreakers per provider (3.4.1)
>   8. Create Resolver (3.1.5 -- depends on registries + policy + providers)
>   9. Create EmbeddingIndex (4.1.1) + RetrievalEngine (4.1.5)
>   10. Create ContextBuilder (4.2.1 -- depends on state_reader + prompt_system)
>   11. Create OutputValidationPipeline (3.5.5 -- depends on state_reader + event_port)
>   12. Create AgentFactory (4.3.1 -- depends on model_gateway + state_reader + delta_bus + context_builder + tool_scope)
>   13. Create HealthChecker (3.6.1 -- depends on provider_registry + circuit_breakers + event_port)
>   14. Wire HealthChecker <-> CircuitBreaker bidirectional callbacks
>   15. Create FabricMailbox (4.4.1 -- optional, production mode only)
>   16. Create FabricFacade (5.3.2 -- depends on resolver + context_builder + validation_pipeline + event_emitter)
>   17. Create FabricRetrieval (5.3.3 -- depends on retrieval_engine)
>   18. Start ModuleLoader scan (bootstrap registry from disk)
>   19. Start HealthChecker periodic loop
> - **FabricFacade** (5.3.2) is the **main API**. execute() pipeline: EventEmitter.emit_invoked -> Resolver.resolve -> ContextBuilder.build -> CircuitBreaker.execute(Provider.execute) -> OutputValidationPipeline.validate -> EventEmitter.emit_completed/failed -> Registry.update_metrics.
> - **FabricRetrieval** (5.3.3) is the **retrieval API**. discover_capabilities() -> RetrievalEngine.discover().
> - **Depends on**: ALL subsystems from M1-M4. Factory is the composition root.
> - **Consumed by**: Orchestrator, Planner, Concierge (external consumers of Fabric's public API).

### Epic 5.4: Event Bus Integration

**Goal**: Wire all Fabric event emission and consumption.

> **Reference**: `fabric_discussion.md` Section 20 -- Event Bus Integration.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 5.4.1 | Define Fabric event types | DONE | k1/fabric/events/fabric_events.py | **Emitted**: k1.capability.invoked.v1, k1.capability.completed.v1, k1.capability.failed.v1, k1.fabric.capability.registered.v1, k1.fabric.capability.unregistered.v1, k1.fabric.capability.version.conflict.v1, k1.fabric.contract.validation.failed.v1, k1.fabric.output.validation.failed.v1, k1.fabric.learning.signal.v1 (payload: capability_name, provider_id, success, duration_ms, error_code, context_quality_score -- consumed by Learning Loop / K0 feedback pipeline P09), k1.fabric.provider.health.changed.v1, k1.fabric.capability.contract_updated.v1 (proactive gap detection -- emitted when capability contracts change, consumed by Orchestrator Workflow Engine for workflow invalidation), k1.fabric.pressure.warning.v1 (backpressure signal from mailbox). **Consumed**: k1.orchestration.step.execute.v1, k1.planner.discovery.request.v1, k1.fabric.provider.health.check.v1, k1.mcp.tool.discovered.v1 (from Orchestrator MCP Tool Discovery -- triggers programmatic registration). Event payloads as dataclasses with to_dict(). |
| 5.4.2 | Implement EventEmitter wrapper | DONE | k1/fabric/events/event_emitter.py | Wraps IEventPort. Enforces cognitive_trace_id on every event (FAB-09). Methods: `emit_invoked(request)`, `emit_completed(request, result)`, `emit_failed(request, error)`, `emit_registered(contract)`, `emit_unregistered(name)`. All carry trace_id + timestamp. |
| 5.4.3 | Wire events into execution pipeline | DONE | k1/fabric/fabric.py | Modify execute() to emit: (1) k1.capability.invoked.v1 before execution, (2) k1.capability.completed.v1 after success, (3) k1.capability.failed.v1 after failure. Modify register()/unregister() to emit registry events. Wire learning.signal.v1 after every result with full payload (capability_name, provider_id, success, duration_ms, error_code, context_quality_score). |
| 5.4.4 | Wire proactive gap detection | DONE | k1/fabric/events/event_emitter.py | Subscribe to registry change events (register, unregister, version conflict). On any contract change: emit `k1.fabric.capability.contract_updated.v1` with old_version, new_version, breaking_change flag. Orchestrator's Workflow Engine consumes this to invalidate affected frozen workflows and trigger re-validation. Also subscribe to `k1.mcp.tool.discovered.v1` from Orchestrator MCP Tool Discovery: on receipt, convert MCP tool manifest to CapabilityContract dict and call `register_from_dict()` (Issue 2.3.4). |

> **Wiring**:
>
> - **Event types** (5.4.1) are **pure dataclasses**. No port dependency. Define ALL event schemas used by entire Fabric.
> - **EventEmitter** (5.4.2) **wraps** IEventPort (5.1.2). Adds cognitive_trace_id enforcement (FAB-09). ALL subsystems emit events through EventEmitter, never directly through IEventPort.
> - **Execution pipeline events** (5.4.3) wired into FabricFacade.execute() (5.3.2):
>   - BEFORE execution: emit `k1.capability.invoked.v1`
>   - AFTER success: emit `k1.capability.completed.v1` + `k1.fabric.learning.signal.v1`
>   - AFTER failure: emit `k1.capability.failed.v1` + `k1.fabric.learning.signal.v1`
>   - `learning.signal.v1` carries full payload for K0 feedback pipeline P09.
> - **Proactive gap detection** (5.4.4) **subscribes to** registry change events. **Emits** `k1.fabric.capability.contract_updated.v1` consumed by Orchestrator Workflow Engine. **Subscribes to** `k1.mcp.tool.discovered.v1` from Orchestrator and calls register_from_dict() (2.3.4).
> - **Event consumers** (external): Orchestrator consumes step.execute events. Planner consumes discovery.request events. Learning Loop consumes learning.signal events. K0 feedback pipeline P09 consumes learning.signal.
> - **Depends on**: IEventPort (5.1.2), ModuleLoader (2.3.4) for programmatic registration.
> - **Consumed by**: FabricFacade (5.3.2), Registry (2.2.2), external K1 subsystems.
> - **Pattern**: EventEmitter is singleton per Fabric instance. Created by FabricFactory. Passed to all subsystems that emit events.

---

## Milestone 6: Testing

> **Goal**: Comprehensive test suite following SessionState's no-mock testing philosophy.
>
> **Philosophy**: Real adapters, real execution paths, real concurrency. NO MOCKS except for error boundary testing.
>
> **Test Location**: `tests/k1/fabric/`

### Epic 6.1: Test Infrastructure

**Goal**: Set up test fixtures and helpers.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 6.1.1 | Create conftest.py with fixtures | TODO | tests/k1/fabric/conftest.py | Fixtures: `fabric_standalone()` (FabricFactory.create_standalone()), `fabric_for_testing()` (FabricFactory.create_for_testing() with capture events), `registry()` (empty CapabilityRegistry), `sample_tool_contract()`, `sample_agent_contract()`, `sample_prompt_contract()`, `sample_workflow_contract()`. All using real adapters, NO MOCKS. |
| 6.1.2 | Create sample contracts for testing | TODO | tests/k1/fabric/fixtures/ | Sample YAML contracts: restaurant_booking (tool), weather_api (tool), invitation_sender (agent), health_summarizer (agent), invitation_drafter_v1 (prompt), weekly_health_check (workflow). All valid against schemas. Provide variety of domains, safety bands, provider types. |
| 6.1.3 | Create test helpers | TODO | tests/k1/fabric/helpers.py | Helper functions: `load_fixture_contract(name)`, `create_n_contracts(n, domain?)` (generate N valid contracts), `assert_capability_result_success(result)`, `assert_capability_result_failure(result, error_code)`, `wait_for_event(adapter, event_type, timeout_ms)`. |

> **Wiring**:
>
> - **conftest.py** (6.1.1) wires test infrastructure using FabricFactory.create_for_testing() (5.3.1). ALL test fixtures flow through the factory -- no direct subsystem construction.
> - **Sample contracts** (6.1.2) are real YAML files validated against schemas (1.2.x). Used by ModuleLoader tests (6.2.4), integration tests (6.3.x), and cross-subsystem tests (6.5.x).
> - **Test helpers** (6.1.3) use LocalEventAdapter.captured_events (5.2.3) for event assertions. No mocks.
> - **Depends on**: FabricFactory (5.3.1), all test adapters (5.2.x), contract schemas (1.2.x).

### Epic 6.2: Unit Tests (Per Subsystem)

**Goal**: Test each subsystem in isolation with real adapters.

> **MANDATORY**: All tests use real adapters via FabricFactory.create_for_testing(). No direct internal component access.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 6.2.1 | Test ContractValidator | TODO | test_contract_validator.py | Test all 12 validation rules: (1) name pattern, (2) semver, (3) domain non-empty, (4) description non-empty, (5) required_inputs complete, (6) output schema valid, (7) provider_type enum, (8) safety_band enum, (9) availability enum, (10) agent tools_granted valid, (11) prompt variables satisfiable, (12) workflow DAG acyclic. Test valid contracts pass. Test each invalid case raises ContractValidationError with clear message. |
| 6.2.2 | Test ContractParsers (all 4 types) | TODO | test_contract_parsers.py | Test YAML loading for tool, agent, prompt, workflow contracts. Test parse -> validate -> dataclass roundtrip. Test malformed YAML handling. Test missing required fields. Test auto-detection of contract type from YAML content. |
| 6.2.3 | Test CapabilityRegistry | TODO | test_registry.py | Test register/unregister, lookup (O(1)), list_by_domain, list_by_type, update_availability, update_metrics, reload(), health(). Test thread-safety with concurrent register/lookup. Test event emission on register/unregister. Test with 100+ contracts. |
| 6.2.4 | Test ModuleLoader | TODO | test_module_loader.py | Test startup scan of contracts directory. Test hot-reload: file create triggers register, file modify triggers unregister + register, file delete triggers unregister. Test invalid file: logs error, keeps old contract. Test scan with mix of valid and invalid YAMLs. |
| 6.2.5 | Test ProviderResolution pipeline | TODO | test_provider_resolution.py | Test full pipeline: registry lookup -> provider matching -> policy -> selection -> instantiation. Test capability_not_found error. Test access_denied for safety band violation. Test deterministic selection (FAB-10). Test multi-provider selection. |
| 6.2.6 | Test PolicyEngine (all 4 dimensions) | TODO | test_policy_engine.py | Test SecurityContext: GREEN user + GREEN cap = PASS, GREEN user + AMBER cap = REJECT. Test AffectiveRouting: high sadness boosts gentle providers. Test CognitiveLoadRouting: high load prefers faster. Test QoSIntegration: tight budget prefers cheaper. Test composite score calculation. Test ToolScope enforcement. |
| 6.2.7 | Test RetrievalEngine | TODO | test_retrieval_engine.py | Test full pipeline: embed -> hard filter -> soft rank -> Top-K. Test with 100 contracts: verify top results are semantically relevant. Test hard filter: safety band exclusion, OFFLINE exclusion, input satisfiability. Test soft ranker weights (0.4/0.3/0.15/0.15). Test DEGRADED penalty (0.7x). Test top_k parameter (default 10, max 25). |
| 6.2.8 | Test ContextBuilder | TODO | test_context_builder.py | Test 6-step flow: (1) read required_context, (2) fetch from SessionState, (3) inject params, (4) resolve prompt, (5) apply token budget, (6) package. Test optional section missing (skip gracefully). Test required section missing (log warning, partial context). Test token budget compression strategies (5 levels). Test 128K ceiling enforcement (FAB-08). |
| 6.2.9 | Test CircuitBreaker | TODO | test_circuit_breaker.py | Test state transitions: CLOSED -> OPEN (after threshold failures) -> HALF_OPEN (after recovery period) -> CLOSED (on success) or OPEN (on failure). Test sliding window failure counting. Test per-provider configs. Test retry strategy (max 2 retries). |
| 6.2.10 | Test Core Types | TODO | test_types.py | Test all dataclasses: CapabilityRequest, CapabilityResult, CapabilityContract, AgentContract, PromptContract, WorkflowContract, RetrievalResult, ExecutionContext, ProviderConfig. Test to_dict(), from_dict() roundtrip. Test factory methods (CapabilityResult.success(), .failure(), .timeout()). Test all enums. |
| 6.2.11 | Test OutputValidationPipeline | TODO | test_output_validation.py | Test 3-tier pipeline: (1) StructuralValidator rejects malformed results, (2) SchemaValidator rejects schema-violating data, (3) SemanticValidator flags low-confidence outputs. Test ValidationFallback: structural fail -> rejection, schema fail -> coercion attempt, semantic fail -> warning annotation. Test pipeline short-circuit on hard failure. Test configurable skip_semantic for tool results. |
| 6.2.12 | Test HealthChecker | TODO | test_health_checker.py | Test periodic health checks: healthy provider returns ONLINE, unhealthy returns DEGRADED/OFFLINE. Test consecutive failure threshold for OFFLINE marking. Test recovery progression: OFFLINE -> DEGRADED -> ONLINE. Test health-checker + circuit-breaker bidirectional integration. Test AvailabilityTracker state transitions and history. |
| 6.2.13 | Test CapabilityVersioning | TODO | test_capability_versioning.py | Test CapabilityVersion parsing, comparison, compatibility. Test registry version conflict resolution: duplicate rejection, compatible upgrade, breaking multi-version, regression rejection. Test version-aware lookup: exact, latest compatible, latest. Test version conflict event emission. |

> **Wiring**:
>
> - All unit tests **access subsystems through** FabricFactory.create_for_testing() (5.3.1). Each test gets a fresh Fabric instance.
> - **ContractValidator tests** (6.2.1) verify validation rules consumed by Registry.register() (2.2.2).
> - **Registry tests** (6.2.3) verify event emission via captured_events on LocalEventAdapter (5.2.3).
> - **PolicyEngine tests** (6.2.6) verify ISessionStateReader reads via TestSessionStateReaderAdapter (5.2.2).
> - **RetrievalEngine tests** (6.2.7) verify EmbeddingIndex integration with FAISS. Require sample contracts (6.1.2).
> - **ContextBuilder tests** (6.2.8) verify ISessionStateReader + IPromptSystemPort reads via test adapters.
> - **OutputValidation tests** (6.2.11) verify 3-tier pipeline behavior.
> - **HealthChecker tests** (6.2.12) verify bidirectional CB <-> HealthChecker wiring (3.6.3).
> - **Versioning tests** (6.2.13) verify version conflict resolution and events.
> - **Pattern**: NO MOCKS. All test adapters are real implementations with in-memory state.

### Epic 6.3: Integration Tests

**Goal**: Test subsystems working together through Fabric's execution and retrieval APIs.

> **MANDATORY**: All tests use FabricFactory. All mutations/reads through fabric.execute() or fabric.discover_capabilities(). No direct subsystem access.
>
> **HARDCORE INTEGRATION TEST REQUIREMENTS**:
>
> 1. ALWAYS use FabricFactory.create_for_testing() or create_standalone()
> 2. All capability invocations through fabric.execute() -- NEVER direct provider access
> 3. All retrievals through fabric.discover_capabilities() -- NEVER direct retrieval engine access
> 4. Real adapters only (test adapters are real -- they are NOT mocks)
> 5. Verify events via event adapter capture mode
> 6. Verify all 13 invariants hold during execution

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 6.3.1 | Test LOW tier execution flow | DONE | test_low_tier_flow.py (33 tests) | Full LOW tier: MCP/WASM/Bridge providers. Events, metrics, error handling, timeout, batch. All 33 tests passing. |
| 6.3.2 | Test MEDIUM tier execution flow | DONE | test_medium_tier_flow.py (19 tests) | Multi-provider batch execution. Parallel/sequential strategies, cross-provider, error isolation. All 19 tests passing. |
| 6.3.3 | Test HIGH tier retrieval + execution flow | DONE | test_high_tier_flow.py (22 tests) | 50+ contracts, domain discovery, top-K relevance, full retrieve-then-execute pipeline. All 22 tests passing. |
| 6.3.4 | Test agent spawn and execution | DONE | test_agent_execution.py (32 tests) | Agent lifecycle FSM (7), AgentFactory spawn (6), Agent execute (3), ToolScope (4), DeltaEmission (5), AgentPool (3), Fabric stub verification (4). All 32 tests passing. |
| 6.3.5 | Test safety band enforcement end-to-end | DONE | test_safety_band_e2e.py (24 tests) | GREEN/AMBER/RED/CRISIS access control (16 band combinations), event emission (3), edge cases (5). All 24 tests passing. |
| 6.3.6 | Test circuit breaker integration | DONE | test_circuit_breaker_integration.py (18 tests) | State machine (5), fabric.execute CB flow (6), events (3), config (3), full recovery cycle (2). FAST_CB_CONFIG: threshold=3, half_open=100ms. All 18 tests passing. |
| 6.3.7 | Test context builder with real SessionState | TODO | test_context_with_sessionstate.py | Create SessionState via create_for_testing(), populate with beliefs, history, persona. Register agent capability requiring these sections. Execute via fabric. Verify ExecutionContext contains correct SessionState data. Verify token budget applied. Test FAB-08 (128K ceiling). |
| 6.3.8 | Test sub-agent tool scoping | TODO | test_tool_scoping.py | Spawn agent with tools_granted = ["tool.execute.send_message"]. Agent attempts to invoke "tool.execute.restaurant_booking" (not granted). Verify AccessDeniedError. Verify FAB-07. |
| 6.3.9 | Test statelessness (FAB-03) | TODO | test_statelessness.py | Execute capability A, then capability B. Verify no state carried between invocations. Verify Fabric instance has no request-specific state after execution. Execute same capability 100 times, verify each is independent. |
| 6.3.10 | Test deterministic selection (FAB-10) | TODO | test_deterministic_selection.py | Register 3 providers for same capability with different scores. Execute 100 times with same inputs + same registry state. Verify same provider selected every time. Verify tie-breaking: lower latency, then alphabetical. |
| 6.3.11 | Test BridgeConnectionAdapter integration | TODO | test_bridge_connection_adapter.py | Test with Bridge unavailable: verify is_available() == False, all operations return graceful fallback (LOCAL COLD), no crash, warning logged. Test with Bridge available: verify operations route through Bridge, IFL addresses resolved correctly. Test auto-reconnect: start unavailable, make available, verify adapter reconnects. Test IFL routing for tool.execute.home.* addresses. |
| 6.3.12 | Test execute_batch() semantics | TODO | test_execute_batch.py | Test PARALLEL strategy: 10 capabilities execute concurrently, results in input order. Test SEQUENTIAL strategy: ordered execution, results in input order. Test partial failure: 3 of 5 fail, 2 succeed, all results returned, failed ones have CapabilityResult.failure(). Test backpressure: batch > max_batch_size rejected. Test with Orchestrator DAG wave scenario (multiple capabilities from one wave). |
| 6.3.13 | Test output validation end-to-end | DONE (27 tests) | test_output_validation_e2e.py | Register capability, execute via fabric.execute(). Inject provider that returns schema-violating result. Verify OutputValidationPipeline catches violation. Verify `k1.fabric.output.validation.failed.v1` event emitted. Test with valid result: verify pipeline passes through. Test with agent provider + semantic validation. |
| 6.3.14 | Test proactive gap detection | DONE (25 tests) | test_proactive_gap_detection.py | Register capability v1. Update to v2 (breaking change). Verify `k1.fabric.capability.contract_updated.v1` emitted with breaking_change=True. Simulate MCP tool discovery event `k1.mcp.tool.discovered.v1`: verify tool auto-registered in registry via programmatic registration. Test learning signal payload completeness after execution. |
| 6.3.15 | Test meta-agent creation workflow | NEW | tests/k1/fabric/test_meta_agent_creation.py | End-to-end via FabricFactory.create_standalone(): (1) Register 3 tool contracts (send_message, check_vitals, log_entry) + 1 prompt template via TestPromptSystem (5.2.5), (2) Execute `tool.read.discover_capabilities` via Fabric -> verify returns full contract JSON with all fields, (3) Execute `tool.read.find_prompts` via Fabric -> verify returns matching templates, (4) Execute `tool.write.build_agent` via Fabric with valid spec -> verify CapabilityResult.success with status="registered", (5) Verify agent registered in Registry via Registry.lookup("agent.execute.test_agent"), (6) Verify `k1.fabric.agent.created.v1` event emitted with correct payload fields (4.5.7), (7) Execute created agent via Fabric.execute(CapabilityRequest("agent.execute.test_agent", params)) -> verify agent runs with TestModelGateway (5.2.4) and scoped tools only, (8) Verify AgentResponsePayload in result.data["payload"] (4.5.8). Additional scenarios: ephemeral cleanup via Registry.remove_expired_agents() -> verify agent unregistered + agent.expired event, duplicate name rejection (register same name twice -> error), tool validation failure (grant non-existent tool -> AgentSpecValidationError), prompt validation failure (unknown template -> error). **Fixtures**: FabricFactory.create_standalone() with TestPromptSystem, TestModelGateway, TestBridge. **Invariants verified**: FAB-02 (contract compliance), FAB-03 (statelessness between agent executions), FAB-07 (tool scoping), FAB-09 (trace_id propagation through build+execute). **Validates issues**: 4.5.1, 4.5.2, 4.5.3, 4.5.4, 4.5.6, 4.5.7, 4.5.8. ~25 tests. |
| 6.3.16 | Test recursive creation prevention | NEW | tests/k1/fabric/test_meta_safety.py | All tests via FabricFactory.create_standalone() with AMBER-band SecurityContext. 5 hard gate scenarios: (1) Tool grant recursion: build_agent with tools_granted=["tool.write.build_agent"] -> verify PolicyResult(allowed=False, reasons=["meta_operation:recursive_tool_grant"]) + MetaOperationBlockedEvent emitted, (2) Restricted domain: build_agent with domain=["META"] -> verify rejection + blocked event with violation_type="restricted_domain", (3) Safety escalation: GREEN-band caller executes build_agent with safety_band_min="AMBER" -> verify rejection + blocked event with violation_type="safety_escalation", same for RED band, (4) Tool grant validation: build_agent with tools_granted=["tool.execute.nonexistent"] -> verify AgentSpecValidationError from validator (4.5.1) before reaching SecurityContext, (5) Agent depth: register a capability with provider_type=AGENT, then build_agent with that capability in tools_granted -> verify rejection + blocked event with violation_type="agent_depth_exceeded". Each scenario: assert CapabilityResult.failure returned, assert exactly 1 MetaOperationBlockedEvent captured (4.5.7), assert no agent registered in Registry. Additional: test valid AMBER-band creation succeeds (positive control), test all 5 gates simultaneously (spec violating multiple gates -> all violations in reasons list). **Fixtures**: FabricFactory.create_standalone() with configurable SecurityContext bands. **Invariants verified**: FAB-02 (contracts enforced), custom meta-safety invariants (no recursion, no escalation, depth=1). **Validates issues**: 4.5.5 (all 5 gates), 4.5.7 (blocked events). ~15 tests. |
| 6.3.17 | Test AgentResponsePayload and result merging | NEW | tests/k1/fabric/test_agent_response_payload.py | Payload construction and validation: (1) Create AgentResponsePayload with all fields -> verify frozen, verify to_dict() produces JSON-safe dict, verify from_dict() roundtrip equality, (2) validate() passes for valid payload (confidence=0.85, domain=["health"], answer="..."), (3) validate() fails for confidence > 1.0, empty domain, empty answer, (4) domain_data freeform: store complex nested dict {vitals: {heart_rate: 72}, medications: [{name: "aspirin"}]} -> verify preserved through to_dict/from_dict roundtrip. Integration with CapabilityResult: (5) Wrap payload in CapabilityResult.success(data={"payload": payload.to_dict()}) -> verify extraction via result.data["payload"], verify from_dict reconstruction. Multi-agent aggregation: (6) Create 3 AgentResponsePayload instances (health, finance, scheduling domains) -> verify confidence averaging ((0.9+0.8+0.7)/3), verify domain union, verify all sources merged, verify follow_up_needed=True if any agent sets it, (7) Test single-agent passthrough (no aggregation needed). Concierge consumption pattern: (8) Simulate Concierge reading result.data["payload"]["answer"] + result.data["payload"]["domain_data"] + result.data["payload"]["sources"] -> verify all accessible. **Fixtures**: No Fabric factory needed -- mostly unit-level dataclass tests + CapabilityResult integration. **Validates issues**: 4.5.8 (all methods and integration). ~20 tests. |

> **Wiring**:
>
> - Integration tests verify **end-to-end wiring** through FabricFacade.execute() (5.3.2) and FabricRetrieval.discover_capabilities() (5.3.3). NEVER bypass the API.
> - **LOW/MEDIUM/HIGH tier tests** (6.3.1-6.3.3) verify the full execution pipeline: request -> mailbox (optional) -> resolve -> policy -> context -> provider -> output validation -> events -> result.
> - **Agent tests** (6.3.4) verify AgentFactory wiring: IModelGatewayPort, ISessionStateReader, IDeltaBusPort, ToolScope all connected.
> - **Safety band tests** (6.3.5) verify SecurityContext hard gate in PolicyEngine (3.2.1).
> - **CB integration** (6.3.6) verifies CircuitBreaker <-> HealthChecker <-> AvailabilityTracker <-> Registry chain.
> - **Bridge adapter** (6.3.11) verifies BridgeConnectionAdapter graceful degradation and IFL routing.
> - **Batch tests** (6.3.12) verify execute_batch() wiring for Orchestrator DAG wave execution.
> - **Output validation E2E** (6.3.13) verifies OutputValidationPipeline wired into execute() path.
> - **Gap detection** (6.3.14) verifies event subscription chain: Registry -> EventEmitter -> external consumers.
> - **Meta-agent creation** (6.3.15) verifies full Epic 4.5 workflow end-to-end: DiscoverCapabilitiesHandler (4.5.3) -> FindPromptsHandler (4.5.3) -> BuildAgentHandler (4.5.2) with AgentSpecValidator (4.5.1) + AgentComposer (4.5.4) + SecurityContext.validate_meta_operation (4.5.5) -> Registry.register_created_agent (4.5.6) -> EventEmitter.emit_agent_created (4.5.7) -> AgentFactory.execute (4.3.2) -> AgentResponsePayload (4.5.8). Also verifies ephemeral cleanup via remove_expired_agents (4.5.6) + agent.expired event. Fixture: FabricFactory.create_standalone() with TestPromptSystem (5.2.5), TestModelGateway (5.2.4).
> - **Recursive prevention** (6.3.16) verifies SecurityContext.validate_meta_operation() (4.5.5) all 5 hard gates through full Fabric execution path: Orchestrator -> Fabric.execute(CapabilityRequest("tool.write.build_agent")) -> Resolver -> MCPProvider -> BuildAgentHandler.execute() step 3 -> SecurityContext.validate_meta_operation() -> PolicyResult(allowed=False). Confirms MetaOperationBlockedEvent (4.5.7) emission per violation with correct violation_type. Confirms no agent registered after rejection.
> - **AgentResponsePayload** (6.3.17) verifies standard agent output envelope (4.5.8): frozen dataclass construction, to_dict()/from_dict() roundtrip, validate() boundary conditions, CapabilityResult.data integration, multi-agent confidence aggregation, Concierge consumption pattern (reads payload.answer + payload.domain_data + payload.sources). Mostly unit-level tests, no full Fabric factory needed.
> - **Pattern**: Each test creates a full Fabric via factory, executes through public API, asserts via captured events + results.

### Epic 6.4: Contract Tests

**Goal**: Validate compliance with all registered Fabric contracts.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 6.4.1 | Test module.contract.yaml compliance | TODO | test_module_contract.py | Verify all required exports exist: CapabilityFabric, FabricRetrieval, CapabilityRegistry, ContractValidator, ProviderResolver, PolicyEngine, ContextBuilder, AgentFactory. Verify all port interfaces: ISessionStateReader, IEventPort, IBridgePort, IModelGatewayPort, IPromptSystemPort. Verify factory methods work. |
| 6.4.2 | Test wiring.contract.yaml compliance | TODO | test_wiring_contract.py | Verify all required files exist. Verify port interfaces have declared methods. Verify all adapters implement their port. Verify factory wiring. |
| 6.4.3 | Test policies.contract.yaml compliance | DONE | test_policies_contract.py | 198 tests (198 passed). Verifies SLI budgets (registry lookup, retrieval, resolution, context build, overhead). Circuit breaker global + per-provider configs. SafetyBand ordering. Safety enforcement declarations. Audit requirements. Capability grants. Egress rules. SLI latency (9 targets + consistency), SLI throughput (4 targets), SLO availability (4 targets + consistency). |
| 6.4.4 | Test tool contract schema validation | DONE | test_tool_schema_validation.py | 77 tests (77 passed). Phase 1 JSON Schema validation (required fields, name pattern, provider_type enum, safety_band enum, availability enum). Phase 2 semantic rules 1-9 (name convention, semver, domain, description, inputs, output, provider_type, safety_band, availability). Edge cases and boundary tests. |
| 6.4.5 | Test agent contract schema validation | DONE | test_agent_schema_validation.py | 97 tests (97 passed). Phase 1 JSON Schema validation (all required fields incl. prompt_template, tools_granted, llm_budget_tokens, max_tool_calls, max_execution_time_ms). Phase 2 semantic rules 1-10 (includes agent-specific rule-07 provider_type=AGENT, rule-10 tools_granted pattern). Agent-specific field constraints and edge cases. |

> **Wiring**:
>
> - Contract tests verify the **3 contract files** (module.contract.yaml, wiring.contract.yaml, policies.contract.yaml) from Epic 1.2 match actual implementation.
> - **Module contract** (6.4.1) verifies all exports declared in module.contract.yaml (1.2.1) are importable from k1/fabric/.
> - **Wiring contract** (6.4.2) verifies all ports (5.1.x) have declared methods, all adapters (5.2.x) implement their port, FabricFactory (5.3.1) wires correctly.
> - **Policies contract** (6.4.3) verifies SLI targets from policies.contract.yaml (1.2.3) are met via benchmarks.
> - **Schema validation** (6.4.4-6.4.5) verifies ContractValidator (2.1.1) enforces all 12 rules from schemas.
> - **Pattern**: Contract tests are the **compliance gateway** -- they prove the implementation matches the declared contracts.

### Epic 6.5: Cross-Subsystem Integration Tests

**Goal**: Test subsystem interactions and data flow between them.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 6.5.1 | Test Registry -> Retrieval flow | DONE | test_registry_retrieval.py | 56 tests (56 passed). 18 test classes: bulk registration (100 contracts), 22 distinct queries, safety-band/availability/satisfiability hard filters, domain-match & DEGRADED soft ranking, top-K selection, hot-reload (availability + unregister), metrics-update ranking, registration events, edge cases (empty registry, single contract, empty intent, large top_k clamped), YAML fixture co-existence, concurrent registration, combined hard filters, registry size consistency, multi-domain contracts, RetrievalResult serialization. Regression: 4367 passed, 8 xfailed. |
| 6.5.2 | Test Registry -> Resolution -> Execution flow | DONE | test_registry_resolution_execution.py | 86 tests (86 passed). 19 test classes: registry lookup during resolution (5), provider matching for MCP/WASM/BRIDGE (5), policy evaluation security hard gate (6), full execution chain with timing/trace/events (7), event emission sequence invoked/completed/failed/learning (8), availability OFFLINE + provider UNHEALTHY blocking (6), metrics update via registry (4), hot-reload health lifecycle HEALTHY->UNHEALTHY->HEALTHY (3), multi-provider-type execution (4), concurrent execution parallel same/different capabilities (3), stateless execution FAB-03 (3), deterministic provider selection FAB-10 (1), registration events then execute (2), edge cases empty params/large params/unregister/re-register (6), resolution-to-execution data flow provider_id/trace_id/events (5), provider registry consistency auto-registration/health defaults (4), resolver direct access resolve/resolve_to_result/policy_score (6), YAML fixture full chain (3), provider factory handler registration (5). Documents FabricFacade._update_metrics() signature mismatch bug (silently caught). Regression: 4453 passed, 8 xfailed. |
| 6.5.3 | Test Policy -> ContextBuilder -> Agent flow | DONE | test_policy_context_agent.py | Register agent with required_context including beliefs_active, persona. Policy passes. ContextBuilder reads SessionState. Agent receives correct context. Delta emitted on fact discovery. Full pipeline. 67 tests. |
| 6.5.4 | Test ModuleLoader -> Registry -> Retrieval update | DONE (72 tests) | test_loader_registry_retrieval.py | Start with empty registry. ModuleLoader scans fixture directory. Register all found contracts. Verify retrieval works on loaded contracts. Hot-reload: modify a YAML file, verify registry + retrieval index updated. |

> **Wiring**:
>
> - Cross-subsystem tests verify **data flow chains** between subsystems that depend on each other.
> - **Registry -> Retrieval** (6.5.1): Verifies Registry data indexed by EmbeddingIndex, HardFilter reads availability, SoftRanker reads metrics.
> - **Registry -> Resolution -> Execution** (6.5.2): Verifies Resolver reads Registry, selects provider, executes through CB.
> - **Policy -> Context -> Agent** (6.5.3): Verifies PolicyEngine reads SessionState, ContextBuilder reads SessionState + prompts, Agent receives completed context.
> - **Loader -> Registry -> Retrieval** (6.5.4): Verifies ModuleLoader.scan_directory() -> Registry.register() -> EmbeddingIndex rebuild chain.
> - **Pattern**: Tests verify multi-hop dependency chains that are wired by FabricFactory (5.3.1).

### Epic 6.6: Invariant Tests

**Goal**: Explicitly test every one of the 13 hard invariants.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 6.6.1 | Test FAB-01 to FAB-04 | DONE | test_invariants_core.py | **FAB-01**: Fabric has no IStateWritePort dependency, no write methods available. **FAB-02**: Fabric has no ILLMPort dependency. **FAB-03**: Execute 100 requests, verify no instance state between calls. **FAB-04**: Register slow provider (sleep 35s), verify circuit breaker timeout at 30s. |
| 6.6.2 | Test FAB-05 to FAB-08 | DONE | test_invariants_safety.py | **FAB-05**: Register OFFLINE capability, verify hard filter eliminates before soft ranking. **FAB-06**: Execute without safety check, verify policy engine called first. **FAB-07**: Spawn agent, attempt unauthorized tool, verify rejection. **FAB-08**: Build context exceeding 128K, verify compression + ceiling. |
| 6.6.3 | Test FAB-09 to FAB-13 | DONE | test_invariants_behavior.py | **FAB-09**: Execute capability, verify all events have cognitive_trace_id. **FAB-10**: Same inputs, 100 executions, same provider selected. **FAB-11**: Register invalid capability name, verify rejection. **FAB-12**: Register contract without validation, verify blocked. **FAB-13**: Registry lookup <1ms (benchmark), retrieval <50ms (benchmark), overhead <100ms (benchmark). |

> **Wiring**:
>
> - Invariant tests verify the **13 hard invariants** (FAB-01 to FAB-13) that are enforced by wiring decisions:
> - **FAB-01** (no writes): Verified by checking Fabric has NO IStateWritePort in its port set (5.1.x). Pure wiring constraint.
> - **FAB-02** (no LLM): Verified by checking Fabric has NO ILLMPort. Agents get LLM through IModelGatewayPort (5.1.4).
> - **FAB-03** (stateless): Verified by multiple execute() calls with no leaking state.
> - **FAB-04** (timeout): Verified by CB wrapping (3.4.1) in execution path.
> - **FAB-05-08**: Filter ordering, safety checks, tool scoping, token ceiling -- all PolicyEngine/ContextBuilder wiring.
> - **FAB-09-13**: Trace IDs (EventEmitter), determinism (ProviderSelector), naming (ContractValidator), validation (Registry.register), performance (benchmarks).

### Epic 6.7: Performance Tests

**Goal**: Benchmark critical paths and validate performance targets.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 6.7.1 | Benchmark registry lookup | DONE | test_bench_registry.py (30 tests) | Registry with 1K, 10K, 100K contracts. Measure lookup latency: target <1ms P95. Measure list_by_domain, list_by_type latency. |
| 6.7.2 | Benchmark retrieval | TODO | test_bench_retrieval.py | Registry with 10K contracts. Measure discover_capabilities() latency: target <20ms P95. With 100K contracts: target <50ms P95. Measure embedding computation: target <5ms. Hard filter: target <2ms. Soft ranking: target <10ms. |
| 6.7.3 | Benchmark context build | TODO | test_bench_context.py | Measure context build latency: small context (2-3 sections): target <10ms P95. Large context (6+ sections): target <50ms P95. Token counting: target <1ms. |
| 6.7.4 | Benchmark full overhead | TODO | test_bench_overhead.py | Measure full Fabric overhead (resolve + policy + context + routing + result): target <100ms P95. Exclude provider execution time. Measure with real adapters. |

> **Wiring**:
>
> - Performance tests validate **SLI targets** declared in policies.contract.yaml (1.2.3) against real wired subsystems.
> - **Registry benchmark** (6.7.1): Measures CapabilityRegistry.lookup() (2.2.3) with increasing contract counts.
> - **Retrieval benchmark** (6.7.2): Measures RetrievalEngine.discover_capabilities() (4.1.5) including FAISS search + HardFilter + SoftRanker.
> - **Context benchmark** (6.7.3): Measures ContextBuilder.build() (4.2.1) including ISessionStateReader reads + token counting.
> - **Overhead benchmark** (6.7.4): Measures FabricFacade.execute() (5.3.2) end-to-end EXCLUDING provider execution. This is Fabric's own overhead: resolve + policy + context + output validation.
> - **All benchmarks** use FabricFactory.create_for_testing() with real adapters. Results feed into Epic 7.1 SLI compliance.

---

## Milestone 7: SLO/SLI + Observability

> **Goal**: Define SLIs/SLOs, implement metrics collection, tracing, and alerting.
>
> **Pattern**: Same approach as SessionState M5.

### Epic 7.1: SLI/SLO Definition

**Goal**: Define measurable service level indicators and objectives.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 7.1.1 | Define latency SLIs | DONE | SLI spec in policies.contract.yaml | **Registry lookup**: P95 <1ms. **Retrieval (10K)**: P95 <20ms. **Retrieval (100K)**: P95 <50ms. **Provider resolution**: P95 <5ms. **Context build (small)**: P95 <10ms. **Context build (large)**: P95 <50ms. **Full overhead**: P95 <100ms. **MCP local**: P95 <2s. **Agent execution**: P95 <10s. 9 latency SLIs in sli.latency section. 11 tests (TestSLILatency) + 7 consistency tests (TestSLILatencyConsistency). |
| 7.1.2 | Define throughput SLIs | DONE | SLI spec in policies.contract.yaml | **Concurrent executions**: 100 parallel. **Registry size**: 100K+ capabilities. **Retrieval QPS**: 1000 queries/sec. **Execution QPS**: 100 requests/sec. 4 throughput SLIs in sli.throughput section. 6 tests (TestSLIThroughput). |
| 7.1.3 | Define availability SLOs | DONE | SLO spec in policies.contract.yaml | **Availability**: 99.9%. **Latency compliance**: 99.5% within P95 targets. **Retrieval accuracy**: 95% relevant results in Top-10. **Circuit breaker recovery**: <60s. 4 SLOs in slo section. 8 tests (TestSLOAvailability) + 3 consistency tests (TestSLOConsistency). |

> **Wiring**:
>
> - SLI/SLO definitions are **written into** policies.contract.yaml (1.2.3). They are the source of truth for:
>   - Performance test targets (6.7.x)
>   - Alert thresholds (7.4.1)
>   - CB config defaults (3.4.2)
>   - Dashboard requirements (7.2.x)
> - **Consumed by**: PolicyEngine (3.2.5) for QoS scoring, performance benchmarks (6.7.x), alerting rules (7.4.1), SLO compliance validation (8.4.2).

### Epic 7.2: Metrics Implementation

**Goal**: Implement metrics collection for SLI measurement.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 7.2.1 | Implement latency histograms | DONE | k1/fabric/metrics.py | Histograms implemented in `FabricMetrics` with time_* context managers. Wired into `CapabilityFabric.execute`, `RetrievalEngine`, `CapabilityRegistry.lookup`, `ContextBuilder.build`, `PolicyEngine.evaluate`. |
| 7.2.2 | Implement counters | DONE | k1/fabric/metrics.py | Counters implemented in `FabricMetrics` and wired into execution, retrieval, registration, circuit breaker trips, agent spawns, and retries. |
| 7.2.3 | Implement gauges | DONE | k1/fabric/metrics.py | Gauges implemented in `FabricMetrics` and wired into registry size, circuit breaker state, agent pool size, and active executions. |

> **Wiring**:
>
> - **Histograms** (7.2.1) are **wired into** subsystem hot paths via context managers:
>   - `time_execution()` wraps FabricFacade.execute() (5.3.2)
>   - `time_retrieval()` wraps RetrievalEngine.discover() (4.1.5)
>   - `time_lookup()` wraps Registry.lookup() (2.2.3)
>   - `time_context_build()` wraps ContextBuilder.build() (4.2.1)
> - **Counters** (7.2.2) are **incremented by**: FabricFacade after execute(), Registry after register(), CB on trip, AgentFactory on spawn.
> - **Gauges** (7.2.3) are **updated by**: Registry on register/unregister (size), CB on state change, AgentPool on add/remove, FabricFacade on execute start/end.
> - **Depends on**: All subsystems (metrics wraps their hot paths).
> - **Pattern**: Metrics module is imported by subsystems. No circular dependency. Context managers are zero-overhead when metrics disabled.

### Epic 7.3: Tracing & Logging

**Goal**: Implement distributed tracing and structured logging.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 7.3.1 | Add cognitive_trace_id to all operations | TODO | All subsystems | Every operation logs trace_id. CapabilityRequest.trace_id propagated through: resolve, policy, context_build, execute, result_return. Events carry trace_id (FAB-09). Same pattern as SessionState 5.3.1. |
| 7.3.2 | Implement structured logging | TODO | k1/fabric/logging.py | JSON structured logs per phase: resolve, policy_check, context_build, execute, result_return. Fields: timestamp, level, component (fabric.{phase}), trace_id, request_id, capability_name, provider_id, duration_ms, success. |

> **Wiring**:
>
> - **cognitive_trace_id** (7.3.1) is generated at FabricFacade.execute() entry and **propagated through**: Resolver, PolicyEngine, ContextBuilder, Provider.execute(), OutputValidationPipeline, EventEmitter. **Enforces** FAB-09.
> - **Structured logging** (7.3.2) is added at each phase boundary in FabricFacade.execute() pipeline. Each log entry includes trace_id for correlation.
> - **Depends on**: All subsystems accept trace_id parameter. EventEmitter (5.4.2) enforces trace_id on events.
> - **Pattern**: Same as SessionState 5.3.1 tracing pattern. trace_id flows top-down through the entire execution pipeline.

### Epic 7.4: Alerting Rules

**Goal**: Define alerts for SLO violations.

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 7.4.1 | Define alert rules | TODO | k1/fabric/alerts.yaml | Alerts: `FabricHighLatency` (P95 > 200ms sustained 5min), `FabricCircuitBreakerOpen` (any CB open > 2min), `FabricRetrievalSlow` (P95 > 100ms sustained 5min), `FabricAgentPoolExhausted` (pool=0 for any contract), `FabricRegistryEmpty` (size=0 for any type). |
| 7.4.2 | Document runbook for alerts | TODO | docs/runbooks/fabric.md | Per alert: Cause, impact, investigation steps, remediation. |

> **Wiring**:
>
> - **Alert rules** (7.4.1) consume **metrics** from Epic 7.2 (histograms, counters, gauges). Thresholds derived from SLI/SLO definitions (7.1.x).
> - **FabricHighLatency** triggers when fabric_execution_duration_seconds P95 > 200ms (metric 7.2.1).
> - **FabricCircuitBreakerOpen** triggers when fabric_circuit_breaker_state gauge (7.2.3) shows OPEN > 2min.
> - **Runbook** (7.4.2) documents remediation that references specific subsystems: CircuitBreaker (3.4.1), Registry (2.2.1), AgentPool (4.3.3), RetrievalEngine (4.1.5).
> - **Depends on**: Metrics (7.2.x), SLIs (7.1.x).

---

## Milestone 8: Production Readiness

> **Goal**: Validate production-level quality through load testing, chaos testing, documentation, and final checklist.
>
> **Pattern**: Same approach as SessionState M6.

### Epic 8.1: Load Testing

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 8.1.1 | Test concurrent executions | TODO | test_load_testing.py | Test 10, 50, 100 concurrent fabric.execute() calls. Measure: throughput (ops/sec), latency (P50, P95, P99), error rate. Target: 100 concurrent, P95 <200ms overhead. |
| 8.1.2 | Test registry at scale | TODO | test_load_testing.py | Load 10K, 50K, 100K contracts. Measure: register throughput, lookup latency, retrieval latency. Verify lookup <1ms at 100K. Verify retrieval <50ms at 100K. |
| 8.1.3 | Test retrieval throughput | TODO | test_load_testing.py | With 10K contracts. 1000 concurrent discover_capabilities() calls. Measure QPS, P95 latency. Target: 1000 QPS, P95 <50ms. |
| 8.1.4 | Test agent pool under load | TODO | test_load_testing.py | Spawn 20 agents concurrently. Then 50. Measure: spawn latency, pool reuse rate, memory consumption. Verify pool reuse for same contract type within 60s TTL. |

> **Wiring**:
>
> - Load tests verify wiring **holds under concurrency pressure**. All tests use FabricFactory.create_for_testing().
> - **Concurrent executions** (8.1.1): Stress-tests FabricFacade.execute() (5.3.2) with 100 parallel requests. Validates thread-safety of Registry (RLock), CircuitBreaker, EventEmitter.
> - **Registry at scale** (8.1.2): Tests Registry.register() (2.2.2) and lookup() (2.2.3) with 100K contracts. Validates O(1) lookup wiring.
> - **Retrieval throughput** (8.1.3): Tests RetrievalEngine (4.1.5) under 1000 concurrent queries. Validates FAISS index + HardFilter + SoftRanker concurrency.
> - **Agent pool** (8.1.4): Tests AgentFactory (4.3.1) + AgentPool (4.3.3) under concurrent spawn load. Validates IModelGatewayPort throughput.

### Epic 8.2: Chaos Testing

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 8.2.1 | Test MCP server failure | TODO | test_chaos_testing.py | Simulate MCP server crash mid-execution. Verify: circuit breaker trips, CapabilityResult{success=false} returned, events emitted, provider marked OFFLINE. Recovery: restart server, verify half-open -> closed. |
| 8.2.2 | Test K0 Bridge unavailability | TODO | test_chaos_testing.py | Simulate K0 offline. Verify: Bridge Provider returns graceful fallback, circuit breaker prevents cascading, other provider types unaffected. |
| 8.2.3 | Test SessionState reader failure | TODO | test_chaos_testing.py | Simulate SessionState read timeout during context build. Verify: context built with partial data (graceful degradation), no crash, warning logged. |
| 8.2.4 | Test concurrent registry modifications | TODO | test_chaos_testing.py | Hot-reload contracts while 100 concurrent executions happening. Verify: no crashes, no data corruption, thread safety maintained. |

> **Wiring**:
>
> - Chaos tests verify **graceful degradation** when wired dependencies fail.
> - **MCP failure** (8.2.1): MCPProvider (3.3.2) -> CircuitBreaker (3.4.1) -> HealthChecker (3.6.1) -> AvailabilityTracker (3.6.2) -> Registry.update_availability (2.2.5). Full failure chain.
> - **Bridge unavailability** (8.2.2): BridgeConnectionAdapter (5.2.8) -> BridgeProvider (3.3.4) -> fallback (LOCAL COLD). Verifies IBridgePort.is_available() wiring.
> - **SessionState failure** (8.2.3): ISessionStateReader (5.1.1) timeout -> ContextBuilder (4.2.1) partial context -> Provider executes with degraded context. Graceful degradation.
> - **Concurrent modifications** (8.2.4): ModuleLoader (2.3.2) hot-reload concurrent with FabricFacade.execute() (5.3.2). Verifies RLock in Registry (2.2.1).

### Epic 8.3: Documentation Finalization

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 8.3.1 | Finalize README.md | TODO | k1/fabric/README.md | Full README with: overview (3 Roles), architecture (7 Subsystems), invariants (13), API surface, performance targets, usage examples (standalone, testing, wired), directory structure, test coverage summary. |
| 8.3.2 | Create runbook | TODO | docs/runbooks/fabric.md | Emergency procedures for: high latency, circuit breaker cascades, registry corruption, agent pool exhaustion, retrieval degradation. |
| 8.3.3 | Update architecture diagrams | TODO | fabric.mmd updated | Update fabric.mmd to reflect FINAL IMPLEMENTATION: add STATUS header, port/adapter subgraphs, test counts, performance baselines. |
| 8.3.4 | Create performance baseline | TODO | docs/benchmarks/fabric-benchmark-report.md | Comprehensive benchmark report: latency profiles (registry, retrieval, resolution, context, overhead), throughput limits, SLI/SLO compliance table, architecture insights. |

> **Wiring**:
>
> - **README** (8.3.1) documents the full wiring architecture: 9 subsystems, 6 ports, adapter selection, FabricFactory construction order (from 5.3.1 wiring notes).
> - **Runbook** (8.3.2) maps alert rules (7.4.1) to subsystem remediation procedures.
> - **Architecture diagrams** (8.3.3) show port/adapter subgraphs and subsystem dependency graph from this wiring documentation.
> - **Performance baseline** (8.3.4) captures benchmark results (6.7.x) as permanent baseline for SLI/SLO tracking.

### Epic 8.4: Final Validation

| Issue | Title | Status | Deliverable | Details |
|-------|-------|--------|-------------|---------|
| 8.4.1 | Run full test suite | TODO | Test results | All tests pass. Target: >95% pass rate. Capture total test count and coverage. |
| 8.4.2 | Validate SLO compliance | TODO | SLO report | All SLI/SLO tests pass. All performance targets met. Generate compliance report. |
| 8.4.3 | Security review | TODO | Security sign-off | Verify: FAB-01 (no SessionState writes), FAB-06 (safety band enforcement), FAB-07 (tool scoping), egress policies, audit trails, capability access control. |
| 8.4.4 | Performance baseline documentation | TODO | Perf baseline | Document baselines for all critical operations with measured P50/P95/P99 latencies. |

> **Wiring**:
>
> - **Full test suite** (8.4.1) runs ALL tests from M6 (6.1-6.7). Validates entire wiring is correct.
> - **SLO compliance** (8.4.2) validates all SLI targets from 7.1.x against benchmark results from 6.7.x.
> - **Security review** (8.4.3) verifies security-critical wiring: FAB-01 (no write port), FAB-06 (SecurityContext hard gate), FAB-07 (ToolScope enforcement), agent capability scoping.
> - **Performance baseline** (8.4.4) documents P50/P95/P99 for all subsystem paths: Registry, Retrieval, Resolution, Context, Overhead.
> - **Final gate**: No production deployment until all tests pass, SLOs met, security reviewed, baselines documented.

---

## Issue Dependencies Graph

```
                                    M1: FOUNDATION
                                         |
         +-------------------------------+-------------------------------+
         |                               |                               |
    Epic 1.1                        Epic 1.2                        Epic 1.3
    (ADRs)                        (Contracts)                    (Core Types)
         |                               |                               |
         +-------------------------------+-------------------------------+
                                         |
                                         v
                              M2: CONTRACT SYSTEM + REGISTRY
                                         |
         +-------------------------------+-------------------------------+
         |                               |                               |
    Epic 2.1                        Epic 2.2                        Epic 2.3
    (Validation)                   (Registry)                    (Loader)
         |                               |                               |
         +-------------------------------+-------------------------------+
                                         |
                                         v
                          M3: RESOLUTION + POLICY + EXECUTION
                                         |
    +----------------+-------------------+-------------------+----------------+
    |                |                   |                   |                |
Epic 3.1         Epic 3.2           Epic 3.3            Epic 3.4
(Resolution)     (Policy)           (Providers)         (Circuit Breaker)
    |                |                   |                   |
    +----------------+-------------------+-------------------+
                                         |
                                         v
                      M4: RETRIEVAL + CONTEXT + AGENT FACTORY
                                         |
         +-------------------------------+-------------------------------+
         |                               |                               |
    Epic 4.1                        Epic 4.2                        Epic 4.3
    (Retrieval)                  (Context Builder)              (Agent Factory)
         |                               |                               |
         +-------------------------------+-------------------------------+
                                         |
                                         v
                     M5: PORTS, ADAPTERS & STANDALONE MODE
                                         |
    +----------------+-------------------+-------------------+----------------+
    |                |                   |                   |                |
Epic 5.1         Epic 5.2           Epic 5.3            Epic 5.4
(Ports)          (Adapters)         (Factory)           (Events)
    |                |                   |                   |
    +----------------+-------------------+-------------------+
                                         |
                                         v
                                    M6: TESTING
                                         |
    +--------+--------+--------+--------+--------+--------+--------+
    |        |        |        |        |        |        |        |
  E6.1     E6.2     E6.3     E6.4     E6.5     E6.6     E6.7
 (Infra) (Unit)  (Integ)  (Contract)(Cross) (Invar) (Perf)
    |        |        |        |        |        |        |
    +--------+--------+--------+--------+--------+--------+
                                         |
                                         v
                                M7: SLO/SLI + OBS
                                         |
    +----------------+-------------------+-------------------+
    |                |                   |                   |
Epic 7.1         Epic 7.2           Epic 7.3            Epic 7.4
(SLI Def)        (Metrics)        (Tracing)           (Alerts)
    |                |                   |                   |
    +----------------+-------------------+-------------------+
                                         |
                                         v
                              M8: PRODUCTION READINESS
                                         |
    +----------------+-------------------+-------------------+
    |                |                   |                   |
Epic 8.1         Epic 8.2           Epic 8.3            Epic 8.4
(Load Test)      (Chaos)            (Docs)           (Validation)
```

---

## Critical Path

**Minimum viable path to testable Fabric (STANDALONE):**

```
1.3.1 (CapabilityRequest) -> 1.3.2 (CapabilityResult) -> 1.3.3 (CapabilityContract)
                                                                |
                                                                v
2.1.1 (ContractValidator) -> 2.1.2 (ToolContractParser) -> 2.2.1 (Registry data structures)
                                                                |
                                                                v
2.2.2 (register/unregister) -> 2.2.3 (lookup) -> 3.1.1 (ProviderRegistry)
                                                                |
                                                                v
3.1.5 (Resolver) -> 3.2.1 (SecurityContext) -> 3.3.1 (CapabilityProvider protocol)
                                                                |
                                                                v
3.3.2 (MCPProvider) -> 5.3.1 (FabricFactory) -> 5.3.2 (FabricFacade)
                                                                |
                                                                v
                                                 6.3.1 (LOW tier test)
```

**Estimated critical path duration**: 3-4 weeks to first executable fabric.execute() call

**Extended path to full Fabric (all 3 Roles):**

```
Critical path (3-4 weeks) -> Role 2 complete
  + 4.1.5 (RetrievalEngine) -> Role 1 complete (1-2 weeks)
  + 4.3.5 (AgentProvider) -> Role 3 complete (2-3 weeks)
```

**Note**: This path produces a FULLY TESTABLE standalone Fabric. No external dependencies required beyond SessionState read-only access.

---

## No-Mock Testing Strategy

### Principles

1. **Real Adapters**: Use TestSessionStateReaderAdapter, TestBridgeAdapter, TestModelGatewayAdapter (real implementations, NOT mock objects)
2. **Real Contract Parsing**: Parse real YAML contracts, validate against real schemas
3. **Real Registry**: In-memory CapabilityRegistry with real contracts loaded
4. **Real Timers**: Use real time for circuit breaker tests (short timeouts)
5. **Real Concurrency**: Use actual threads/async for parallel execution tests
6. **Standalone First**: All tests work with FabricFactory.create_standalone() -- no Orchestrator, no Concierge, no K0

### Fixture Strategy

```python
# tests/k1/fabric/conftest.py

from k1.fabric.factory import FabricFactory
from k1.fabric.adapters.test_state_reader import TestSessionStateReaderAdapter
from k1.fabric.adapters.local_event import LocalEventAdapter
from k1.fabric.adapters.test_bridge import TestBridgeAdapter
from k1.fabric.adapters.test_model_gateway import TestModelGatewayAdapter
from k1.fabric.adapters.test_prompt_system import TestPromptSystemAdapter
from k1.fabric.adapters.test_delta_bus import TestDeltaBusAdapter

@pytest.fixture
def state_reader():
    """Real in-memory SessionState reader (pre-loaded sections)"""
    adapter = TestSessionStateReaderAdapter()
    adapter.load_section("beliefs_active", {"entities": [...]})
    adapter.load_section("persona", {"name": "Mom", "tone": "warm"})
    return adapter

@pytest.fixture
def event_adapter():
    """Real local event bus with capture mode"""
    adapter = LocalEventAdapter(capture_mode=True)
    yield adapter
    adapter.drain()

@pytest.fixture
def bridge_adapter():
    """Real in-memory K0 bridge (canned responses)"""
    return TestBridgeAdapter(available=True)

@pytest.fixture
def model_gateway():
    """Real test model gateway (canned LLM responses)"""
    return TestModelGatewayAdapter()

@pytest.fixture
def fabric(state_reader, event_adapter, bridge_adapter, model_gateway):
    """Fully functional standalone Fabric"""
    return FabricFactory.create_with_ports(
        state_reader=state_reader,
        event_port=event_adapter,
        bridge=bridge_adapter,
        model_gateway=model_gateway,
        prompt_system=TestPromptSystemAdapter(),
        delta_bus=TestDeltaBusAdapter(),
    )

@pytest.fixture
def standalone_fabric():
    """Quick standalone Fabric (all default test adapters)"""
    return FabricFactory.create_standalone()
```

### Why No Mocks?

| Mock Pattern | Problem | Real Alternative |
|--------------|---------|------------------|
| Mock registry | Hides index bugs | Real CapabilityRegistry with test contracts |
| Mock policy | Hides safety band bugs | Real PolicyEngine with test safety configs |
| Mock providers | Hides protocol bugs | Real test providers (in-memory execution) |
| Mock events | Hides emission bugs | Real LocalEventAdapter with capture mode |
| Mock SessionState | Hides context build bugs | Real TestSessionStateReaderAdapter |
| Mock timers | Hides circuit breaker bugs | Real time (short durations) |

---

## SLO/SLI Targets

### SLIs (Measurable)

| SLI | Metric | Target | Measurement |
|-----|--------|--------|-------------|
| Registry Lookup Latency | `fabric_registry_lookup_duration_seconds` | P95 < 1ms | Histogram |
| Retrieval Latency (10K) | `fabric_retrieval_duration_seconds` | P95 < 20ms | Histogram |
| Retrieval Latency (100K) | `fabric_retrieval_duration_seconds` | P95 < 50ms | Histogram |
| Provider Resolution | `fabric_resolution_duration_seconds` | P95 < 5ms | Histogram |
| Context Build (small) | `fabric_context_build_duration_seconds` | P95 < 10ms | Histogram |
| Context Build (large) | `fabric_context_build_duration_seconds` | P95 < 50ms | Histogram |
| Full Fabric Overhead | `fabric_overhead_duration_seconds` | P95 < 100ms | Histogram |
| Execution Success Rate | `fabric_executions_total{result}` | > 99% | Counter ratio |
| Circuit Breaker Recovery | `fabric_circuit_breaker_recovery_seconds` | < 60s | Timer |

### SLOs (Commitments)

| SLO | Target | Error Budget |
|-----|--------|--------------|
| Availability | 99.9% | 43.2 min/month |
| Latency (overhead) | 99.5% within 100ms | 0.5% slow requests |
| Retrieval Accuracy | 95% relevant in Top-10 | 5% irrelevant first page |
| Execution Success | 99% | 1% execution failures |

---

## Directory Structure (Target)

```
k1/fabric/
  __init__.py                           # Public exports
  fabric.py                             # CapabilityFabric + FabricRetrieval + RegistryAPI facade
  factory.py                            # FabricFactory (create_standalone, create_for_testing, create_with_ports)
  types.py                              # All types: Request, Result, Contract, Enums, etc.
  metrics.py                            # Histograms, counters, gauges
  logging.py                            # Structured JSON logging
  fabric.mmd                            # Architecture diagram (existing)
  fabric_discussion.md                  # Design document (existing)

  core/
    __init__.py
    registry.py                         # CapabilityRegistry (indexed catalog)
    registry_types.py                   # SearchQuery, ScoredCapability, RegistryHealth
    context_builder.py                  # Context Builder (SessionState -> ExecutionContext)
    context_budget.py                   # Token budget manager (128K ceiling)
    module_loader.py                    # Contract directory scanner + hot-reload watcher
    module_validator.py                 # 12-rule contract validation
    fabric_mailbox.py                   # FABRIC_MAILBOX with WFQ REALTIME priority scheduling

  retrieval/
    __init__.py
    retrieval_engine.py                 # Semantic Top-K retrieval (Role 1)
    embedding_index.py                  # FAISS vector index
    hard_filter.py                      # Safety + availability + satisfiability filter
    soft_ranker.py                      # Weighted composite scoring
    top_k_selector.py                   # Top-K selection

  provider_resolution/
    __init__.py
    resolver.py                         # Full resolution pipeline
    provider_registry.py                # Provider configurations
    provider_matcher.py                 # Capability -> provider candidates
    provider_selector.py                # Policy-scored selection
    provider_factory.py                 # Provider instantiation

  policy/
    __init__.py
    policy_engine.py                    # Composite 4-dimension evaluation
    security_context.py                 # Safety band hard gate
    affective_routing.py                # Emotion-aware soft score
    cognitive_load_routing.py           # Complexity-aware soft score
    qos_integration.py                  # Budget-aware soft score
    tool_scope.py                       # Sub-agent tool scoping

  providers/
    __init__.py
    base_provider.py                    # CapabilityProvider protocol
    mcp_provider.py                     # MCP tool execution
    wasm_provider.py                    # WASM sandboxed execution
    bridge_provider.py                  # K0 via Bridge
    agent_provider.py                   # Agent Factory + execution
    workflow_provider.py                # Workflow rehydration + Orchestrator
    concierge_provider.py               # Concierge FSM state handlers

  contracts/
    __init__.py
    tool_contract.py                    # ToolContract parser
    agent_contract.py                   # AgentContract parser
    prompt_contract.py                  # PromptContract parser
    workflow_contract.py                # WorkflowContract parser

  capability_types/
    __init__.py
    type_registry.py                    # Capability type conventions

  module_registry/
    __init__.py                         # K0-pattern compatibility

  events/
    __init__.py
    fabric_events.py                    # All event topics + payloads
    event_emitter.py                    # Event emission wrapper (trace_id enforced)

  circuit_breaker/
    __init__.py
    breaker.py                          # CircuitBreaker implementation
    breaker_config.py                   # Per-provider configs

  output_validation/
    __init__.py
    structural_validator.py             # Tier 1: structural result validation
    schema_validator.py                 # Tier 2: JSON Schema validation (SchemaCompiler)
    semantic_validator.py               # Tier 3: semantic validation (HallucinationDetector)
    validation_fallback.py              # Fallback handling (coercion, rejection, warning)
    pipeline.py                         # OutputValidationPipeline (composite 3-tier)

  health/
    __init__.py
    health_checker.py                   # Provider health monitoring
    availability_tracker.py             # ONLINE/DEGRADED/OFFLINE tracking

  ports/
    __init__.py
    state_reader.py                     # ISessionStateReader
    event_port.py                       # IEventPort
    bridge_port.py                      # IBridgePort
    model_gateway.py                    # IModelGatewayPort
    prompt_system.py                    # IPromptSystemPort
    delta_bus.py                        # IDeltaBusPort

  adapters/
    __init__.py
    sessionstate_reader.py              # Production SessionState reader
    local_event.py                      # LocalEventAdapter (reuse from SessionState)
    test_state_reader.py                # In-memory SessionState stub
    test_bridge.py                      # In-memory K0 bridge
    test_model_gateway.py               # Canned LLM responses
    test_prompt_system.py               # Static prompt templates
    test_delta_bus.py                   # Capture mode delta bus
    bridge_connection.py                # BridgeConnectionAdapter (production, connects when Bridge available)
```

---

## Quick Start Checklist

For starting implementation today:

- [ ] Run `python -m governance.k0.scripts.sync --report` to verify baseline
- [ ] Review ADR-K004 (Capability Fabric Adaptation)
- [ ] Review ADR-0005 (Agent Lifecycle)
- [ ] Review ADR-0011 (FlatBuffers Serialization) for Fabric schemas
- [ ] Create `k1/contracts/schemas/modules/fabric/` directory
- [ ] Start with Issue 1.3.1 (CapabilityRequest dataclass -- simplest type)
- [ ] Then Issue 1.3.2 (CapabilityResult dataclass)
- [ ] Then Issue 2.1.1 (ContractValidator -- everything reads contracts)

---

## Tracking

| Metric | Value |
|--------|-------|
| Total Milestones | 8 |
| Total Epics | 40 |
| Total Issues | 188 |
| Completed (DONE) | 110 (M1-M5 minus Epic 4.5) |
| New (Epic 4.5 + 6.3.15-17) | 12 |
| TODO (M6-M8) | 66 |
| Blocked | 0 |

### Epic Summary

| Milestone | Epics | Issues |
|-----------|-------|--------|
| M1: Foundation | 3 (1.1, 1.2, 1.3) | 28 |
| M2: Contract System + Registry | 4 (2.1-2.4) | 21 |
| M3: Resolution + Policy + Execution | 6 (3.1-3.6) | 25 |
| M4: Retrieval + Context + Agent Factory + Meta-Agent Creation | 5 (4.1-4.5) | 24 |
| M5: Ports, Adapters & Standalone | 4 (5.1-5.4) | 21 |
| M6: Testing | 7 (6.1-6.7) | 48 |
| M7: SLO/SLI + Observability | 4 (7.1-7.4) | 9 |
| M8: Production Readiness | 4 (8.1-8.4) | 12 |

### Gap Coverage Summary (added 2026-02-07)

| Gap | Source Architecture Doc | Coverage Added |
|-----|------------------------|----------------|
| Output Validation Pipeline | k1_cognitive_architecture_skeleton.mmd | Epic 3.5 (5 issues), Issue 6.2.11, Issue 6.3.13 |
| Model Hub Capability Routing | k1_cognitive_architecture_skeleton.mmd | Expanded Issue 5.1.4 (IModelGatewayPort) |
| Prompt System Scope Note | k1_cognitive_architecture_skeleton.mmd | Expanded Issue 5.1.5 (explicit out-of-scope note) |
| Capability Versioning | k1_cognitive_architecture_skeleton.mmd | Epic 2.4 (3 issues), Issue 6.2.13 |
| MCP Auto-Registration | orchestrator.mmd | Issue 2.3.4, Issue 5.4.4 (consume k1.mcp.tool.discovered.v1) |
| execute_batch() Semantics | fabric_discussion.md + orchestrator.mmd | Expanded Issue 5.3.2 (BatchStrategy, partial failure, backpressure), Issue 6.3.12 |
| Proactive Gap Detection | k1_cognitive_architecture_skeleton.mmd | Issue 5.4.4, expanded 5.4.1 events, Issue 6.3.14 |
| Fabric Mailbox/Concurrency | k1_cognitive_architecture_skeleton.mmd | Epic 4.4 (2 issues) |
| Health Checker Service | Directory structure | Epic 3.6 (3 issues), Issue 6.2.12 |
| Learning Signal Detail | k1_cognitive_architecture_skeleton.mmd | Expanded Issue 5.4.1, expanded 5.4.3 |
| Bridge Architecture (IFL + BridgeConnectionAdapter) | bridge_architecture.mmd | Expanded 3.3.4, expanded 5.1.3, Issue 5.2.8, Issue 6.3.11 |
| Meta-Agent Creation | meta-agent-creation-integration-proposal.md | Epic 4.5 (9 issues: 4.5.1-4.5.9), Issues 6.3.15-6.3.17 |

---

*Plan created: 2026-02-07*
*Last updated: 2026-02-07*
*Format: Follows SessionState implementation plan structure (Milestones -> Epics -> Issues with Status/Deliverable/Details)*
