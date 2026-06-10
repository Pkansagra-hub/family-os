# Fabric — Architecture Document

> **Epic**: E-0.3 · Fabric Full Code Scan · **Phase 1 complete (GATE-P1 passed 2026-06-05)**
> **Generated**: 2025-07-15 · **Updated**: 2026-06-05 (Phase 1 Epics 0–8)
> **Milestone**: GATE-P1 — Fabric standalone proven · 280 tests pass, 0 regressions
> **Source files**: ~100+ Python modules · 111 test files · ~280 Phase-1 tests
> **Diagrams**: `k1/fabric/fabric.mmd` (~700 lines), `k1/fabric/fabric_new.mmd` (~500 lines)
> **Phase 1 spec**: `k1/fabric/docs/phase1_implementation_plan.md` (39 issues, 8 epics, 50-connector catalog)

---

## Table of Contents

1. [Port Surface](#1-port-surface)
2. [Internal Architecture](#2-internal-architecture)
3. [Factory & Configuration](#3-factory--configuration)
4. [Cross-Component Connections](#4-cross-component-connections)
5. [Test Surface](#5-test-surface)
6. [Spec vs Code Delta](#6-spec-vs-code-delta)

---

## §0 Phase 1 — Situsted Resolution Subsystem (NEW, Epics 1–8)

Phase 1 adds a **situated resolution pipeline** parallel to the existing execution-discover-register API. It is the answer to "what capability can fulfill this intent, on this resource, for this actor, under these policies?"

### 0.1 Phase 1 Component Map

```
RequestFrame (Back's LLM extraction)
  │
  ▼
ResolveSituationService (13-step verdict cascade)
  ├─ ResolveResourcesService  → ResourceUniverse        (Epic 3.4)
  ├─ CapabilityTypeResolver   → list[ResolvedIntentType] (Epic 3.5)
  ├─ PolicySelectorService    → PolicyBundle             (Epic 4.1)
  ├─ CapabilityBinderService  → BindingBundle            (Epic 6.1)
  │    └─ 3-pass: typed graph → exact match → BM25 FTS5
  ├─ ConstitutionLoader       → ConstitutionArtifact     (Epic 5.2)
  └─ PromptPackBuilder        → PromptPack               (Epic 6.3)
       └─ 5 disclosure phases, triple redaction check
  │
  ▼
ResolutionEnvelope {verdict, sub_reason, binding_bundle, prompt_pack}
```

### 0.2 New Stores (Epic 1)

| Store | Scope | Tables | Key Feature |
|---|---|---|---|
| `GlobalProjectionStore` | Shared (SQLite WAL) | 11 tables + FTS5 | 50-connector catalog, graph ontology, typed resolution |
| `LocalProjectionStore` | Per-session (`:memory:`) | 4 tables | Connected resources, household members, alias index |
| `IdempotencyStore` | Shared (SQLite WAL) | 1 table | State machine: not_seen→in_flight→succeeded/failed; succeeded is immutable |

### 0.3 13-Step Verdict Cascade (Epic 6.2)

| Step | Check | Verdict | Sub-Reason |
|---|---|---|---|
| 1 | Budget exhausted | `cannot_execute` | `budget_exhausted:{field}` |
| 2 | Idempotency duplicate | `cannot_execute` | `idempotency_duplicate:{key}` |
| 3 | Ambiguous person ref | `needs_disambiguation` | `ambiguous_person:{raw}` |
| 4 | Stale resource on write | `stale_projection` | `stale_resource:{id}` |
| 5 | Unresolved ambiguous ref | `needs_disambiguation` | `ambiguous_resource:{raw}` |
| 6 | Unresolved not_found ref | `missing_required_params` | `resource_not_found:{raw}` |
| 7 | Intent too vague | `missing_required_params` | `intent_too_vague` |
| 8 | Promote to Tier 3 | `promote_to_tier3` | `connectors:{n}_depth:{d}` |
| 9 | Policy denied | `blocked_by_policy` | `{deny_reason}` |
| 10 | Stale binding | `stale_projection` | `stale_binding:{detail}` |
| 11 | Missing capability | `missing_capability` | `{reason}:{resource_kind}` |
| 12 | Incomplete prerequisites | `can_execute_with_gate` | `prerequisite_read_incomplete:{name}` |
| 13 | HIL gate (write-only) | `needs_hil` | `hil_gate:{trigger}` |
| — | All pass | `can_execute` | `None` |

### 0.4 New Fabric Fields (Epic 7.1)

| Field | Type | Scope |
|---|---|---|
| `global_projection_store` | `GlobalProjectionStore \| None` | Shared |
| `local_projection_store` | `LocalProjectionStore \| None` | Per-session |
| `idempotency_store` | `IdempotencyStore \| None` | Shared |
| `situated_resolver` | `ResolveSituationService \| None` | Per-session |
| `policy_selector` | `PolicySelectorService \| None` | Per-session |
| `verification_runner` | `VerificationPlanRunner \| None` | Shared (kernel-wired) |
| `constitution_loader` | `ConstitutionLoader \| None` | Shared |
| `prompt_pack_builder` | `PromptPackBuilder \| None` | Per-session |

All default to `None` — zero backward-compat impact. Factory STEP 21 wires them when `global_projection_store is not None`.

### 0.5 New Public API on Fabric

- `resolve_situation(request: ResolveSituationRequest) -> ResolutionEnvelope` — typed sync entry (raises `FabricError` if unwired)
- `async _handle_resolve_situation(payload: dict) -> dict` — Back-facing meta-tool (never raises)

### 0.6 Domain Catalog (Epic 2)

50 connectors across 5 domains (family, enterprise, government, agriculture, healthcare), 182 capabilities. Admitted into `GlobalProjectionStore` via `ManifestAdmissionService.admit_all()`. Capability naming: `tool.{invocation_mode}.{domain}.{svc.id}.{action_name}`.

### 0.7 Kernel Integration (Epic 7.3)

| Point | When | What |
|---|---|---|
| S2.10 | Before S3 Fabric | Opens `GlobalProjectionStore` + `IdempotencyStore` (gated: `enable_fabric_stores=True`) |
| S3 | Shared Fabric | Passes stores to `FabricFactory.create_shared()` → STEP 21 wires everything |
| Post-S8 | After family tools | `_load_phase1_catalog_and_verifier()` admits 50-connector catalog |
| P3 | Per-session | `LocalProjectionStore(":memory:")` passed to `create_with_ports()` |
| Shutdown | After fabric.close() | Closes `global_projection_store` + `idempotency_store` |

### 0.8 GATE-P1 Status

- 280/280 Phase 1 tests pass (1 skipped = Bridge Phase 2)
- Real Vertex `gemini-2.5-flash` benchmark: verdict PASS 49/50 (98%), extraction 46/50 (92%), resolve ~25 ms
- `scripts/probe_back_fabric_resolver_benchmark.py` — full pipeline on real `k1.fabric`

---

## §1 Port Surface

### 1.1 Port Inventory

Fabric exposes **6 hexagonal ports**, all implemented as `typing.Protocol` with `@runtime_checkable` — structural subtyping throughout, no ABC inheritance anywhere. A 7th policy-only subset port exists in `policy/ports.py`.

| # | Port | File | Methods | Async | Co-defined Types |
|---|------|------|---------|-------|-----------------|
| 1 | `ISessionStateReader` | `ports/state_reader.py` | `read_section`, `read_sections`, `get_snapshot` | No | `SessionSnapshot` |
| 2 | `IEventPort` | `ports/event_port.py` | `emit`, `subscribe`, `unsubscribe` | No | `SubscriptionHandle` |
| 3 | `IBridgePort` | `ports/bridge_port.py` | `send_command`, `query`, `route_ifl`, `is_available`, `get_health` | Yes (3 async) | `BridgeHealth`, `BridgeCommandResult`, `IFLRoute` |
| 4 | `IModelGatewayPort` | `ports/model_gateway.py` | `create_handle`, `is_model_loaded`, `list_models`, `find_model` | No | `ModelCapability`, `ModelInfo`, `ILLMHandle` |
| 5 | `IPromptSystemPort` | `ports/prompt_system.py` | `resolve`, `compile` | No | `PromptTemplate` |
| 6 | `IDeltaBusPort` | `ports/delta_bus.py` | `emit_delta` | No | `DeltaPayload` |
| 7 | `ISessionStateReader` (policy) | `policy/ports.py` | `read_section` (1 method only) | No | — |

**Policy port note**: `policy/ports.py` defines a separate `ISessionStateReader` with only `read_section` — a strict subset of the canonical 3-method port. NOT `@runtime_checkable`. Any canonical adapter satisfies it automatically via structural subtyping.

### 1.2 Port Details

#### 1.2.1 ISessionStateReader

| Method | Params | Return |
|--------|--------|--------|
| `read_section` | `session_id: str, section: str` | `Optional[Dict[str, Any]]` |
| `read_sections` | `session_id: str, names: List[str]` | `Dict[str, Any]` |
| `get_snapshot` | `session_id: str` | `SessionSnapshot` |

**SessionSnapshot** (frozen): `session_id`, `sections: Dict[str, Dict[str, Any]]`, `timestamp_ms`, `section_names: List[str]`. Auto-populates `section_names` from `sections.keys()`.

#### 1.2.2 IEventPort

| Method | Params | Return |
|--------|--------|--------|
| `emit` | `topic: str, payload: Any` | `None` |
| `subscribe` | `topic: str, handler: Callable[[str, Any], None]` | `SubscriptionHandle` |
| `unsubscribe` | `handle: SubscriptionHandle` | `bool` |

#### 1.2.3 IBridgePort

| Method | Params | Return | Async |
|--------|--------|--------|-------|
| `send_command` | `operation: str, payload: Dict, *, trace_id: str, timeout_ms: int` | `BridgeCommandResult` | Yes |
| `query` | `operation: str, selectors: Dict, *, trace_id: str, timeout_ms: int` | `BridgeCommandResult` | Yes |
| `route_ifl` | `route: IFLRoute, payload: Dict, *, trace_id: str` | `BridgeCommandResult` | Yes |
| `is_available` | — | `bool` | No |
| `get_health` | — | `BridgeHealth` | No |

**BridgeHealth** (frozen): `available`, `mode` (K0_OFFLINE/K0_DEGRADED/K0_FULL), `last_heartbeat_ms`, `latency_ms`, `error_message`.
**BridgeCommandResult** (frozen): `success`, `data`, `error_code`, `error_message`, `k0_mode`, `latency_ms`, `trace_id`. Static: `ok()`, `fail()`.
**IFLRoute** (frozen): `address`, `namespace`, `function_name`, `timeout_ms`. Static: `parse(address)` — parses `tool.execute.<namespace>.<function>`.

#### 1.2.4 IModelGatewayPort

| Method | Params | Return |
|--------|--------|--------|
| `create_handle` | `budget_tokens: int, model_preference?: str, capabilities?: List[str], trace_id?: str` | `ILLMHandle` |
| `is_model_loaded` | `model_id: str` | `bool` |
| `list_models` | — | `List[ModelInfo]` |
| `find_model` | `required_capabilities: List[str]` | `Optional[str]` |

**ILLMHandle** (Protocol): `async generate(prompt, params) -> str`, `model_id` property, `budget_tokens` property.
**ModelCapability** (str Enum): CHAT, TOOL_CALL, STRUCTURED, EMBED, VISION, BATCH.
**ModelInfo** (frozen): `model_id`, `capabilities`, `loaded`, `max_tokens`, `provider`.

#### 1.2.5 IPromptSystemPort

| Method | Params | Return |
|--------|--------|--------|
| `resolve` | `template_name: str` | `Optional[PromptTemplate]` |
| `compile` | `template: str, variables: Dict[str, Any]` | `str` |

**PromptTemplate** (frozen): `name`, `template`, `version`, `variables: List[str]`, `metadata: Dict`.

#### 1.2.6 IDeltaBusPort

| Method | Params | Return |
|--------|--------|--------|
| `emit_delta` | `agent_id: str, delta_type: str, section: str, data: Dict[str, Any]` | `None` |

**DeltaPayload** (frozen): `agent_id`, `delta_type`, `section`, `data`, `trace_id`.

### 1.3 Adapter Inventory

#### Production Adapters (4)

| # | Adapter | Port | File | Threading | Notes |
|---|---------|------|------|-----------|-------|
| 1 | `SessionStateReaderAdapter` | `ISessionStateReader` | `adapters/sessionstate_reader.py` | No lock (manager handles) | Session-bound. Dotted path support (`control.safety_band`). Delegates to `manager.get_section()` |
| 2 | `BridgeConnectionAdapter` | `IBridgePort` | `adapters/bridge_connection.py` | `RLock` | Config-driven: endpoint, timeout, reconnect. Starts LOCAL COLD (bridge client not yet built) |
| 3 | `AutoDiscoveryMCPTransport` | `IMCPTransport` (provider-layer) | `adapters/auto_mcp_transport.py` | No lock (GIL/asyncio) | Auto-discovers MCP servers in `k1/tools/mcp_servers` |
| 4 | `AutoDiscoveryWASMRuntime` | `IWASMRuntime` (provider-layer) | `adapters/auto_wasm_runtime.py` | No lock (GIL/asyncio) | Auto-discovers WASM modules in `k1/tools/wasm_modules` |
| 5 | `PromptSystemProdAdapter` | `IPromptSystemPort` | `adapters/prompt_system_prod.py` | `RLock` | Loads `k1/contracts/prompts/*.yaml` and reads external `template_file` markdown from `k1/prompts/**` |

**NOTE**: `AutoDiscoveryMCPTransport` and `AutoDiscoveryWASMRuntime` implement provider-layer protocols, NOT hexagonal Fabric ports.

#### Test Adapters (8)

| # | Adapter | Port | File | Threading |
|---|---------|------|------|-----------|
| 1 | `TestSessionStateReaderAdapter` | `ISessionStateReader` | `adapters/test_state_reader.py` | `RLock` |
| 2 | `LocalEventAdapter` | `IEventPort` | `adapters/local_event.py` | `RLock` |
| 3 | `TestBridgeAdapter` | `IBridgePort` | `adapters/test_bridge.py` | `RLock` |
| 4 | `TestModelGatewayAdapter` | `IModelGatewayPort` | `adapters/test_model_gateway.py` | `RLock` |
| 5 | `TestPromptSystemAdapter` | `IPromptSystemPort` | `adapters/test_prompt_system.py` | `RLock` |
| 6 | `TestDeltaBusAdapter` | `IDeltaBusPort` | `adapters/test_delta_bus.py` | `RLock` |
| 7 | `TestMCPTransport` | `IMCPTransport` (provider-layer) | `adapters/test_mcp_transport.py` | `RLock` |
| 8 | `TestWASMRuntime` | `IWASMRuntime` (provider-layer) | `adapters/test_wasm_runtime.py` | `RLock` |

**NOTE**: `LocalEventAdapter` serves as BOTH production and test adapter (no separate production IEventPort adapter exists).

### 1.4 Port Conformance Matrix

| Port | Production Adapter | Test Adapter | Conformance |
|------|-------------------|--------------|-------------|
| `ISessionStateReader` | ✅ `SessionStateReaderAdapter` | ✅ `TestSessionStateReaderAdapter` | All 3 methods exact match |
| `IEventPort` | ⚠️ `LocalEventAdapter` (dual-role) | ✅ `LocalEventAdapter` | Payload typed `Dict[str,Any]` (narrower than port's `Any`) — compatible |
| `IBridgePort` | ✅ `BridgeConnectionAdapter` | ✅ `TestBridgeAdapter` | All 5 methods exact match |
| `IModelGatewayPort` | ❌ **MISSING** | ✅ `TestModelGatewayAdapter` | Test adapter satisfies; no production path |
| `IPromptSystemPort` | ✅ `PromptSystemProdAdapter` | ✅ `TestPromptSystemAdapter` | `compile()` accepts `Any` for raw strings, dicts, or `PromptTemplate`; external `template_file` markdown loads at adapter construction/reload |
| `IDeltaBusPort` | ❌ **MISSING** (Bus side provides `FabricBusAdapter`) | ✅ `TestDeltaBusAdapter` | Exact match |

**2 ports lack production adapters in this directory**: `IModelGatewayPort` and `IDeltaBusPort`. Production adapters live outside Fabric where applicable: Bus `FabricBusAdapter` satisfies both `IEventPort` and `IDeltaBusPort`; ModelHub production wiring is external to this adapter inventory.

---

## §2 Internal Architecture

### 2.1 Component Overview

Fabric is K1's **Layer 2.5** — the central resolution, retrieval, and execution engine serving three roles:

| Role | Consumer | API Surface |
|------|----------|-------------|
| **Intelligent Retrieval** | Planner | `discover_capabilities()`, `find_relevant_prompts()` |
| **Resolution + Execution** | Orchestrator, Concierge | `execute()`, `execute_batch()` |
| **Agent Factory** | Orchestrator (via AgentProvider) | `spawn_and_execute()` |

### 2.1.1 Prompt/Profile Metadata Surface

M1 adds an advisory prompt/profile surface to tool capability contracts. `CapabilityContract` carries `prompt_template`, `activity_profile`, `tool_instructions`, and `prompt_variables_schema` for YAML MCP/WASM/Bridge contracts and for K1-native family tools translated through `manifest_translator.py`.

The metadata is contract-plane state and M3 runtime input: it is loaded, validated, round-tripped, registered, discoverable, loadable through `PromptSystemProdAdapter`, and forwarded through `ContextBuilder`. It does not change exact-name lookup, provider selection, tool grants, HIL, conscience gates, or business `params`. Providers receive it only through reserved metadata surfaces: MCP/WASM `__metadata__`, native `WriteContext.extras`, or the agent compiled prompt.

### 2.2 Shared Type System (`types.py`, ~1600 lines)

#### Enums (10)

| Enum | Values |
|------|--------|
| `SafetyBand` | GREEN, AMBER, RED, CRISIS (custom comparison operators) |
| `ProviderType` | MCP, WASM, BRIDGE, AGENT, WORKFLOW, CONCIERGE |
| `ProviderStatus` | HEALTHY, DEGRADED, UNHEALTHY, UNKNOWN |
| `Availability` | ONLINE, DEGRADED, OFFLINE |
| `WFQPriority` | URGENT, REALTIME, INTERACTIVE, BACKGROUND |
| `RequestStatus` | PENDING, IN_PROGRESS, COMPLETED, FAILED, CANCELLED, TIMED_OUT |
| `Tier` | LOW, MEDIUM, HIGH |
| `OutputFormat` | TEXT, JSON, STRUCTURED |
| `TriggerType` | cron, event, manual |
| `TransportType` | stdio, sse, streamable-http |

#### Core Request/Response Types

**`CapabilityRequest`** (frozen, 16 fields): `request_id`, `capability_name`, `params`, `prompt_template`, `context_override`, `tier`, `wfq_priority`, `safety_band`, `timeout_ms` (30s), `retry_count`, `caller`, `caller_id`, `trace_id`, `session_id`, `plan_id`, `step_id`. Has `validate()` (8 checks) and `validate_or_raise()`.

**`CapabilityResult`** (frozen, 10 fields): `request_id`, `trace_id`, `success`, `data`, `error: ErrorInfo`, `provider_id`, `duration_ms`, `retrieval_time_ms`, `resolution_time_ms`, `execution_time_ms`. Factory methods: `success_result()`, `failure_result()`, `timeout_result()`. Invariant: success → data set, error None; failure → error set, data None.

**`ExecutionContext`** (frozen, 5 fields): `session_sections`, `params`, `prompt`, `token_count`, `trace_id`.

#### Contract Types (4 frozen dataclasses)

| Contract | Fields | Extends |
|----------|--------|---------|
| `CapabilityContract` | Identity, capabilities, inputs, context, output, provider, prompt/profile metadata, policy, audit, lifecycle | — |
| `AgentContract` | +6 fields (prompt_template, tools_granted, llm_budget_tokens, max_tool_calls, max_execution_time_ms, template_file) | `CapabilityContract` |
| `PromptContract` | 13 fields (identity, intent_match, variables, template, compatibility, audit) | — |
| `WorkflowContract` | 17 fields (identity, plan, trigger, DAG steps, recursion limits, policy, audit) | — |

**`ContractUnion`** = `Union[CapabilityContract, AgentContract, PromptContract, WorkflowContract]`

### 2.3 Subsystem 1: Contract System

#### ContractValidator (`core/contract_validator.py`, ~700 lines)

Two-phase validation: (1) JSON Schema via `Draft7Validator`, (2) 12 semantic rules.

| # | Rule | Applies To | Key Check |
|---|------|-----------|-----------|
| 1 | Name convention (FAB-11) | All | Regex per type (`^tool.(execute|read|write|delete)…`,`^agent.(execute|spawn)…`, etc.) |
| 2 | Semver version | All | `^M.m.p$` format |
| 3 | Domain non-empty | All | ≥1 tag |
| 4 | Description | All | Non-empty, ≤512 chars |
| 5 | Required inputs | Tool/Agent | Each has name, type, description |
| 6 | Output schema | Tool/Agent | Must be object with `type` prop |
| 7 | Provider type | Tool/Agent | Tool must be MCP/WASM/BRIDGE; agent must be AGENT |
| 8 | Safety band | All | Valid enum (GREEN/AMBER/RED/CRISIS) |
| 9 | Availability | All | Valid enum (ONLINE/DEGRADED/OFFLINE) |
| 10 | Agent tools_granted | Agent | Each follows tool naming regex |
| 11 | Prompt variables | Prompt | name/type/required present; type ∈ {STRING,NUMBER,BOOLEAN,DATE,OBJECT,ARRAY} |
| 12 | Workflow DAG acyclicity | Workflow | Kahn's algorithm cycle detection |

#### Contract Parsers (`contracts/`, 5 files)

`parse_contract()` auto-detects type from root key (`tool_contract`, `agent_contract`, `prompt_contract`, `workflow_contract`), routes to type-specific parser. Each parser: load YAML → extract body → validate → build frozen dataclass.

#### ModuleLoader (`core/module_loader.py`, ~700 lines)

**Lifecycle**: `start(watch=True)` → `scan_directory()` → optionally `start_watching()` (polling daemon thread).
**Hot-reload**: Polling-based (no watchdog dependency). Detects new/modified/deleted YAML files by mtime comparison.
**Change handling**: Created → parse + register. Modified → parse + unregister old + register new (keeps old on validation failure). Deleted → unregister.
**Events**: `contract.validation.failed.v1`, `contract.hot_reloaded.v1`, `contract.removed.v1`.

### 2.4 Subsystem 2: CapabilityRegistry (`core/registry.py`, ~1550 lines)

**5 index structures** (all under `RLock`):

| Index | Type | Purpose |
|-------|------|---------|
| `_by_name` | `Dict[str, ContractUnion]` | O(1) name lookup |
| `_by_domain` | `Dict[str, List[ContractUnion]]` | Inverted domain index |
| `_by_type` | `Dict[str, List[ContractUnion]]` | Grouped by type prefix |
| `_by_provider` | `Dict[str, List[ContractUnion]]` | Grouped by provider_id |
| `_by_version` | `Dict[str, Dict[str, ContractUnion]]` | name → {version_str → contract} |

Plus: `_metadata_cache` (ContractMetadata hot cache), `_created_agents` (runtime agent lifecycle).

**Version conflict resolution** (4-branch):

1. Same version → reject (`VersionConflictError`)
2. Newer compatible (same major) → in-place upgrade
3. Different major → multi-version (`name@major`)
4. Older compatible → reject (`VersionRegressionError`)

**Metrics EMA**: α=0.3 for latency, running average for success rate.
**Thread safety**: `RLock` for all mutations. Lock-free reads (dict atomic + frozen contracts). Events emitted outside lock.

### 2.5 Subsystem 3: Retrieval Engine

4-step pipeline: **Embed → HardFilter → SoftRank → TopK**.

#### EmbeddingIndex (`retrieval/embedding_index.py`)

| Condition | Index Type | Search |
|-----------|-----------|--------|
| n ≤ 10,000 | `faiss.IndexFlatL2(384)` | Exact L2 |
| n > 10,000 | `faiss.IndexIVFFlat(quantizer, 384, nlist=100)` | Approximate, nprobe=10 |

Score: `1/(1+distance)` ∈ (0, 1]. Full rebuild on every add/remove (O(N) per mutation).

#### HardFilter (`retrieval/hard_filter.py`)

3 rules (short-circuit on first failure):

| Rule | Check | Configurable |
|------|-------|-------------|
| Safety Band (FAB-06) | `user_level >= contract_level` (GREEN<AMBER<RED<CRISIS) | `check_safety` |
| Availability | `!= OFFLINE` (DEGRADED kept, penalized later) | `check_availability` |
| Input Satisfiability | `ratio >= 0.5` of required inputs satisfiable from params ∪ session_keys | `check_inputs` |

**Note**: With `planner_can_ask=True` (default), Rule 3 is effectively a no-op.

#### SoftRanker (`retrieval/soft_ranker.py`)

```
Score = (0.40 × semantic_similarity)    // cosine similarity
      + (0.30 × domain_match)           // Jaccard index
      + (0.15 × success_rate)           // 30d rolling, default 0.50
      + (0.15 × cost_latency_score)     // 1 - normalized(cost+latency)
```

If `availability == DEGRADED`: `Score *= 0.70` penalty. Clamped to [0.0, 1.0].

#### TopKSelector (`retrieval/top_k_selector.py`)

Config: `default_k=10, max_k=25, min_k=1`. Slices pre-sorted ranked list.

### 2.6 Subsystem 4: Provider Resolution Chain

5-step pipeline: **Lookup → Match → Policy → Select → Instantiate**.

#### ProviderRegistry (`provider_resolution/provider_registry.py`)

Primary: `provider_id → ProviderConfig`. Secondary: `provider_type → [provider_ids]`. Health cache: `provider_id → ProviderHealth`.
Thread safety: `RLock` on mutations.

#### ProviderMatcher (`provider_resolution/provider_matcher.py`)

1:1 exact `provider_id` lookup (not semantic search). Health filter: skips UNHEALTHY unless `include_unhealthy=True`. Fail-open on health check exception.

#### ProviderSelector (`provider_resolution/provider_selector.py`)

**Deterministic sort key (FAB-10)**: `(-score, avg_latency_ms, provider_id)`. Filters `allowed=True` only. Raises `AllProvidersRejectedError` if all blocked.

#### ProviderFactory (`provider_resolution/provider_factory.py`)

Handler registry: `provider_type → constructor`. Deps injected as `**port_deps` keyword args.
**Design**: Factory never imports concrete providers — they are registered externally by FabricFactory during bootstrap.

#### Resolver (`provider_resolution/resolver.py`)

Orchestrates steps 1-4. Step 5 (instantiation) deferred to caller (`CapabilityFabric._execute_impl`).
If no `_policy_engine`: default pass-all (`allowed=True, score=1.0`).

### 2.7 Subsystem 5: Policy Engine (4 Dimensions)

| # | Dimension | Class | Type | Score Range | SessionState Section |
|---|-----------|-------|------|-------------|---------------------|
| 1 | **Security** | `SecurityContext` | **HARD GATE** | 0 (reject) or pass | None |
| 2 | **Affective** | `AffectiveRouting` | Soft boost | 0.0 – 0.10 | `affective_now` |
| 3 | **Cognitive** | `CognitiveLoadRouting` | Soft boost | 0.0 – 0.10 | `cognitive` |
| 4 | **QoS** | `QoSIntegration` | Soft boost | 0.0 – 0.20 | None (uses request params) |

**Composite formula**: `final_score = 1.0 + affective + cognitive + qos` (base relevance = 1.0, max theoretical = 1.40).

#### SecurityContext — 3 checks (short-circuit)

1. **Safety band (FAB-06)**: `user_level >= cap_level` (GREEN(0) < AMBER(1) < RED(2) < CRISIS(3))
2. **Tool scope**: `capability_name in tools_granted` (only if tools_granted provided)
3. **Rate limiting**: 60-second sliding window per capability_name

#### MetaOperationValidator — 5 hard gates (all evaluated, violations collected)

1. Caller band must be ≥ AMBER
2. No privilege escalation (agent band ≤ caller band)
3. Restricted domain gate (`META`, `SECURITY`, `ADMIN` blocked)
4. Tool grant recursion gate (no `^tool\.write\.` patterns)
5. Agent depth gate (depth=1, leaf nodes only)

#### ToolScope (`policy/tool_scope.py`)

Immutable `FrozenSet[str]` wrapper. Used at invocation time (separate from SecurityContext's policy-time check).

### 2.8 Subsystem 6: Provider Implementations

```
CapabilityProvider (Protocol)
  └─ BaseProvider (ABC) — template method: execute() → _execute()
       ├─ MCPProvider       (IMCPTransport)
       ├─ WASMProvider      (IWASMRuntime)
       ├─ BridgeProvider    (IBridgePort)
       ├─ AgentProvider     (IAgentFactory → Agent, AgentPool, DeltaEmitter)
       ├─ WorkflowProvider  (IWorkflowRegistry, ICapabilityLookup, IOrchestrator)
       └─ ConciergeProvider (IConciergeRouter)
```

**BaseProvider** template method: `execute()` catches ALL exceptions → `CapabilityResult`. Never raises to caller. Subclasses implement `_execute()`.

| Provider | Key Port | CB Timeout | CB Threshold | Max Retries | Unique Feature |
|----------|----------|-----------|-------------|-------------|----------------|
| MCP (local) | `IMCPTransport` | 10s | 3/min | 2 | JSON-RPC over stdio, tool_name_map |
| MCP (remote) | `IMCPTransport` | 15s | 3/min | 2 | SSE/HTTP transport |
| WASM | `IWASMRuntime` | 5s | 5/min | 2 | 64MB memory sandbox, no network/filesystem |
| Bridge | `IBridgePort` | 10s | 3/min | 2 | K0 health modes, IFL routing, LOCAL COLD fallback |
| Agent | `IAgentFactory` | 30s | 2/min | 2 | 6-state lifecycle FSM, AgentPool (5/contract, 60s TTL), DeltaEmitter (500ms batch) |
| Workflow | `IWorkflowRegistry` | 60s | 1/min | **1** | max_depth=3, SHA-256 manifest hash, schema drift detection |
| Concierge | `IConciergeRouter` | 5s | 5/min | 2 | In-process, no external I/O, state routing |

#### Agent Lifecycle FSM (6 states)

```
PENDING → WARMING → ACTIVE → IDLE (pool, 60s TTL)
                             → DRAINING → TERMINATED
```

#### Agent Factory — 8-step spawn

1. Load AgentContract
2. Create Mailbox (stub: `None`, Epic 4.4)
3. Grant LLM via `IModelGatewayPort.create_handle(budget)`
4. Grant SessionState reader
5. Scope tools via `ToolScope(tools_granted)`
6. Build context via `ContextBuilder.build()`
7. Create `DeltaEmitter` if `IDeltaBusPort` present
8. Instantiate `Agent(...)`

#### DeltaEmitter — LWW merge on `(section, key)` by timestamp, 500ms batch window, thread-safe flush

### 2.9 Subsystem 7: Context Builder

6-step assembly pipeline:

| Step | Action |
|------|--------|
| 1 | Read contract context requirements (`required_context`, `optional_context`) |
| 2 | Fetch sections from SessionState via `ISessionStateReader` |
| 3 | Inject request params (pass-through) and preserve `context_override` as a non-SessionState section |
| 4 | Resolve + compile prompt with priority request template -> contract template -> `tool_instructions` fallback |
| 5 | Apply token budget via `ContextBudget` |
| 6 | Package frozen `ExecutionContext` |

Prompt variables are assembled from `prompt_variables_schema` defaults, request params, and `context_override["prompt_variables"]`. The assembled map is used only for prompt compilation and never mutates `CapabilityRequest.params`.

#### Token Budget (`core/context_budget.py`)

**Ceiling**: 128,000 tokens. **Response headroom**: 4,000. **Counting**: tiktoken cl100k_base (fallback: `len(text)//4`).

5-level compression strategy (sequential, stops when under budget):

| Level | Action |
|-------|--------|
| L1 | Drop optional_context sections |
| L2 | Truncate `history_recent` to 3 turns |
| L3 | Filter `beliefs_active` by confidence ≥ 0.5 |
| L4 | Summarize `scoreboard` to `{current_qud}` only |
| L5 | Emergency — HOT sections only (drop all WARM) |

**HOT sections** (8): control, beliefs_active, scoreboard, history_active, clarifications, affective_now, narrative_active, meta.
**WARM sections** (4): beliefs_history, history_recent, persona, telemetry.

### 2.10 Output Validation (3-tier)

| Tier | Validator | Severity | On Failure |
|------|-----------|----------|-----------|
| T1 Structural | Required fields, data well-formedness, truncation markers, size limits (1 MiB) | HARD | **REJECT immediately** |
| T2 Schema | JSON Schema validation (built-in lightweight validator, no `jsonschema` dep) | HARD | **COERCE → re-validate → REJECT** |
| T3 Semantic | Hallucination detection (rule-based, no LLM): uncertainty/fabrication/belief-contradiction | SOFT | **ANNOTATE only (never reject)** |

T3 only runs for `provider_type ∈ {AGENT, WORKFLOW}`.

### 2.11 Circuit Breaker

**Per-provider-id** (one CB per `provider_id`, not per type).

| State | Behavior |
|-------|---------|
| CLOSED | Normal operation |
| OPEN | All requests rejected (`retriable=True`) |
| HALF_OPEN | One probe request allowed; additional rejected |

**Transitions**: CLOSED→OPEN (failures ≥ threshold in window), OPEN→HALF_OPEN (after `half_open_after_ms` elapsed), HALF_OPEN→CLOSED (probe succeeds), HALF_OPEN→OPEN (probe fails).

**Retry strategy**: Up to `max_retries + 1` total attempts. Non-retriable failures break immediately.

**Per-type defaults**:

| Type | Timeout | Threshold | Window | Half-Open After | Retries | Fallback Code |
|------|---------|-----------|--------|-----------------|---------|---------------|
| MCP (local) | 10s | 3/min | 60s | 30s | 2 | `tool_offline` |
| MCP (remote) | 15s | 3/min | 60s | 30s | 2 | `tool_offline` |
| WASM | 5s | 5/min | 60s | 15s | 2 | `computation_failed` |
| Bridge | 10s | 3/min | 60s | 30s | 2 | `bridge_offline` |
| Agent | 30s | 2/min | 60s | 30s | 2 | `agent_execution_failed` |
| Workflow | 60s | 1/min | 60s | 60s | **1** | `workflow_failed` |
| Concierge | 5s | 5/min | 60s | 10s | 2 | `concierge_state_failed` |

### 2.12 Health Monitoring

#### HealthChecker — per-provider periodic health probing

1. Call `provider.health_check()` with 10s timeout
2. Map result: HEALTHY→0 failures, DEGRADED/UNHEALTHY→increment failures
3. If consecutive failures ≥ threshold → force UNHEALTHY
4. Update `ProviderRegistry.update_health()`
5. Sync `AvailabilityTracker` (HEALTHY→ONLINE, DEGRADED→DEGRADED, UNHEALTHY→OFFLINE)
6. Sync circuit breaker (HEALTHY + CB OPEN → `allow_probe()`, UNHEALTHY + CB !OPEN → `trip()`)

**Bidirectional CB↔Health wire**: CB state change notifies HealthChecker → immediate check → may `allow_probe()`. HealthChecker can `trip()` a CB on UNHEALTHY.

#### AvailabilityTracker — progressive recovery enforcement

- ONLINE → DEGRADED, OFFLINE (free)
- DEGRADED → ONLINE, OFFLINE (free)
- OFFLINE → **DEGRADED only** (must recover through DEGRADED first)

### 2.13 Concurrency (ADR-1.1.9)

**Semaphore(10)** hybrid async/await — NO actor mailbox.

#### FabricDispatcher (`concurrency/dispatcher.py`)

| Level | Trigger | Action |
|-------|---------|--------|
| NORMAL | < 80% utilization | All accepted |
| WARNING | ≥ 80% | All accepted + pressure event |
| SHEDDING | ≥ 95% | BACKGROUND priority rejected + shedding event |
| SATURATED | = 100% | All rejected |

**Production-only**: Created when `production_mode=True` in factory. Standalone/testing modes skip dispatcher.

#### TimeoutGuard (`concurrency/timeout.py`)

Available but NOT wired into `_execute_impl()`. Timeout enforcement is via CB per-provider timeout.

### 2.14 Events

#### Emitted Events (16)

| # | Topic | Trigger |
|---|-------|---------|
| 1 | `k1.capability.invoked.v1` | Every `execute()` call start |
| 2 | `k1.capability.completed.v1` | Successful execution |
| 3 | `k1.capability.failed.v1` | Failed execution |
| 4 | `k1.fabric.learning.signal.v1` | Every execution (K0 P09 feedback) |
| 5 | `k1.fabric.capability.registered.v1` | Contract registered |
| 6 | `k1.fabric.capability.unregistered.v1` | Contract unregistered |
| 7 | `k1.fabric.capability.version.conflict.v1` | Version conflict on register |
| 8 | `k1.fabric.capability.contract_updated.v1` | Contract changed (via ProactiveGapDetector) |
| 9 | `k1.fabric.contract.validation.failed.v1` | Contract validation failure |
| 10 | `k1.fabric.output.validation.failed.v1` | Output validation rejection |
| 11 | `k1.fabric.provider.health.changed.v1` | Provider health state change |
| 12 | `k1.fabric.pressure.warning.v1` | Dispatcher at ≥80% |
| 13 | `k1.fabric.pressure.shedding.v1` | Dispatcher shedding requests |
| 14 | `k1.fabric.agent.created.v1` | Runtime agent created |
| 15 | `k1.fabric.agent.expired.v1` | Runtime agent expired |
| 16 | `k1.fabric.meta.operation.blocked.v1` | Meta-operation security violation |

#### Consumed Events (4)

| # | Topic | Handler |
|---|-------|---------|
| 1 | `k1.orchestration.step.execute.v1` | Step execution dispatch |
| 2 | `k1.planner.discovery.request.v1` | Discovery request handling |
| 3 | `k1.fabric.provider.health.check.v1` | Health check trigger |
| 4 | `k1.mcp.tool.discovered.v1` | Auto-registration of MCP tools |

**FAB-09 enforcement**: All emitted events include `cognitive_trace_id` field.

#### ProactiveGapDetector

Subscribes to registry change events, re-emits `contract_updated` for Orchestrator workflow invalidation. Handles MCP tool auto-registration (`mcp.tool.discovered` → contract → register).

### 2.15 Observability

#### Prometheus Metrics (15)

- **Histograms** (5): execution duration, retrieval duration, registry lookup duration, context build duration, policy evaluation duration
- **Counters** (6): executions_total, retrievals_total, registrations_total, circuit_breaker_trips_total, agent_spawns_total, retries_total
- **Gauges** (4): registry_size, circuit_breaker_state, agent_pool_size, active_executions

#### Structured Logging

JSON-formatted, 5 log phases: resolve, policy_check, context_build, execute, result_return. Standard fields: timestamp_iso, level, event, component, trace_id, request_id, capability_name, provider_id, duration_ms, success.

#### Alert Rules (5)

- `FabricHighLatency`: P95 > 200ms for 5m (warning)
- `FabricCircuitBreakerOpen`: Any CB OPEN for 2m (critical)
- `FabricRetrievalSlow`: P95 > 100ms for 5m (warning)
- `FabricAgentPoolExhausted`: Pool size = 0 for 5m (warning)
- `FabricRegistryEmpty`: Any type registry = 0 for 5m (critical)

### 2.16 Invariants (FAB-01 to FAB-13)

| ID | Invariant | Enforcement |
|----|-----------|-------------|
| FAB-01 | NEVER writes SessionState | `ISessionStateReader` = read-only port |
| FAB-02 | NEVER calls LLM directly | All LLM access via `IModelGatewayPort` → `ILLMHandle` |
| FAB-03 | Stateless per-request | Per-call execution, no request-to-request state leaks |
| FAB-04 | CB timeout 30s default | Per-provider `CircuitBreakerConfig` |
| FAB-05 | Hard filters before soft ranking | Retrieval pipeline order enforced |
| FAB-06 | Safety band before execution | SecurityContext HARD GATE in PolicyEngine |
| FAB-07 | Sub-agent tool scoping | `ToolScope` at invocation + SecurityContext at policy |
| FAB-08 | 128K token budget | `TOKEN_CEILING = 128_000` in ContextBudget |
| FAB-09 | All events with trace_id | `EventEmitter._emit()` injects `cognitive_trace_id` |
| FAB-10 | Deterministic selection | Sort key: `(-score, avg_latency_ms, provider_id)` |
| FAB-11 | Name conventions | ContractValidator regex per type |
| FAB-12 | Contracts validated before registration | `ContractValidator.validate()` in register path |
| FAB-13 | quality_score deterministic | SoftRanker formula is pure function of inputs |
| FAB-18 | Phase 1 stores gated behind `enable_fabric_stores` | `KernelConfig.enable_fabric_stores` default `False` — zero behavioral change |
| FAB-19 | `resolve_situation` typed entry | `Fabric.resolve_situation()` delegates to `ResolveSituationService` (13-step cascade) |
| FAB-20 | Constitution loaded via single `ConstitutionLoader` | Shared instance — validated once, read by resolver + verifier + prompt builder |
| FAB-21 | Redaction triple-check before LLM exposure | Source envelope → pack dict → rendered string → any leak raises `PromptPackLeakError` |
| FAB-22 | NEVER global-as-local | Factory creates `LocalProjectionStore(":memory:")` when none provided; never reuses global store |

---

## §3 Factory & Configuration

### 3.1 FabricFactory — 3 Entry Points

| Method | Purpose | Adapters Used |
|--------|---------|---------------|
| `create_standalone()` | Dev/unit tests. No external deps. | All test adapters |
| `create_for_testing()` | Integration tests with event capture. | Test adapters + `LocalEventAdapter(capture_mode=True)` |
| `create_with_ports()` | Production. Custom adapter injection. | All injected externally |

### 3.2 The 22-Step Construction Order (Phase 1 adds STEP 21)

| Step | Component | Key Dependencies |
|------|-----------|-----------------|
| 1 | Adapters | Provided as parameters |
| 2 | `ContractValidator()` | — |
| 3 | `CapabilityRegistry(validator, event_port)` | Step 2 |
| 4 | `ModuleLoader(registry, contracts_dir, event_port, validator)` | Steps 2, 3 |
| 5 | `PolicyEngine`: `SecurityContext()` + `AffectiveRouting(state_reader)` + `CognitiveLoadRouting(state_reader)` + `QoSIntegration()` | state_reader |
| 6 | `ProviderRegistry(event_port)` | event_port |
| 7 | `circuit_breakers: Dict[str, CircuitBreaker] = {}` | Shared mutable dict |
| 8 | `ContextBuilder(state_reader, prompt_system)` | state_reader, prompt_system |
| 9 | `ProviderFactory(**port_deps)` + `_register_provider_handlers()` | Steps 3, 8, all adapters |
| 10 | Resolution chain: `ProviderMatcher(provider_registry)` + `ProviderSelector()` + `Resolver(...)` | Steps 3, 5, 6, 9 |
| 11 | Retrieval: `EmbeddingIndex()` + `HardFilter()` + `SoftRanker()` + `TopKSelector()` + `RetrievalEngine(...)` | Step 3, embedding_port |
| 12 | `OutputValidationPipeline(state_reader, event_port)` | state_reader, event_port |
| 13 | `AvailabilityTracker(event_port)` + `HealthChecker(provider_registry, availability_tracker, circuit_breakers, event_port)` | Steps 6, 7, event_port |
| 14 | Wire bidirectional CB ↔ HealthChecker callbacks | Steps 7, 13 |
| 15 | `FabricDispatcher()` — **production mode only** | event_port |
| 16 | `EventEmitter(event_port)` | event_port |
| 17 | `CapabilityFabric(resolver, context_builder, validation_pipeline, event_emitter, registry, provider_factory, circuit_breakers, dispatcher, config)` | Everything |
| 18 | `FabricRetrieval(retrieval_engine)` | Step 11 |
| 19 | `CapabilityRegistryAPI(registry)` | Step 3 |
| 20 | Bootstrap: `module_loader.start()` + `_auto_register_providers()` + `ProactiveGapDetector.wire_subscriptions()` + assemble `Fabric(...)` container | All |

### 3.3 Provider Handler Registration

6 handlers registered on `ProviderFactory` at Step 9:

| Type | Handler | Key Dependencies |
|------|---------|-----------------|
| MCP | `_create_mcp` | `mcp_transport` |
| WASM | `_create_wasm` | `wasm_runtime` |
| BRIDGE | `_create_bridge` | `bridge_port` |
| AGENT | `_create_agent` | `model_gateway`, `state_reader`, `delta_bus`, `context_builder` |
| WORKFLOW | `_create_workflow` | `workflow_registry`, `capability_lookup`, `orchestrator` |
| CONCIERGE | `_create_concierge` | `concierge_router` |

### 3.4 Auto-Registration

`_auto_register_providers()` scans all contracts in CapabilityRegistry, extracts `provider_id`, auto-creates `ProviderConfig` entries in ProviderRegistry. Derives transport from naming conventions, sets timeouts (30s default, 5s for WASM).

### 3.5 SIM-GAP-48: Is CapabilityRegistry externally injectable?

**NO.** CapabilityRegistry is always constructed internally at Step 3. There is no parameter on any factory method to inject a pre-built registry. External control limited to `contracts_dir` and `event_port`. This is a **closed composition root**.

### 3.6 Two-Phase Construction

1. **Construction** (Steps 1–19): All components built and wired
2. **Bootstrap** (Step 20): `module_loader.start()` + `_auto_register_providers()` + `ProactiveGapDetector.wire_subscriptions()`

Additionally, `Fabric.start_health_checker()` is a **separate async call** post-construction.

### 3.7 The Main Execution Pipeline (`CapabilityFabric.execute()`)

**9-step pipeline** (never raises — all errors wrapped in `CapabilityResult`):

| Step | Action |
|------|--------|
| 1 | Emit `invoked` event |
| 2 | Resolve provider (5-step resolution chain) |
| 3 | Build context (6-step assembly) |
| 4 | Instantiate provider via ProviderFactory |
| 5 | Execute via circuit breaker (or direct if no CB) |
| 6 | Validate output (3-tier pipeline, validation errors don't block) |
| 7 | Emit success/fail event |
| 8 | Update registry metrics (fault-isolated) |
| 9 | Emit learning signal (K0 P09 feedback) |

**Batch execution** (`execute_batch`): 3 strategies — PARALLEL (`asyncio.gather`), SEQUENTIAL (loop), DAG (topological waves with cycle detection).

---

## §4 Cross-Component Connections

### 4.1 Connection Summary

| # | Connection | Fabric Port | Verdict |
|---|-----------|-------------|---------|
| 1 | SessionState → Fabric | `ISessionStateReader` | ✅ **SAFE** |
| 2 | Bus → Fabric (Events) | `IEventPort` | ✅ **SAFE** |
| 3 | Bus → Fabric (Delta) | `IDeltaBusPort` | ✅ **SAFE** |
| 4 | ModelHub → Fabric | `IModelGatewayPort` | ⚠️ **CAUTION** |
| 5 | Bridge → Fabric | `IBridgePort` | ⚠️ **CAUTION** |
| 6 | Fabric → Orchestrator | Orch `IFabricGatewayPort` | ✅ **SAFE** |
| 7 | Fabric → Planner | Planner `IFabricRetrievalPort` | ✅ **SAFE** |
| 8 | Fabric → Concierge | Concierge `IFabricPort` + `IDispatchPort` | ✅ **SAFE** |

### 4.2 Connection Details

#### Connection 1: SessionState → Fabric ✅

| Side | Component | Signature Match |
|------|-----------|----------------|
| Fabric port | `ISessionStateReader` (3 methods) | — |
| Fabric adapter | `SessionStateReaderAdapter` → `manager.get_section()` | ✅ All 3 exact |
| SS side | `SessionStateManager.get_section()` (duck-typed via `Any`) | ✅ Compatible |

Session-bound at construction. FAB-01 (read-only) enforced. Dotted path support.

#### Connection 2: Bus → Fabric (Events) ✅

| Side | Component | Signature Match |
|------|-----------|----------------|
| Fabric port | `IEventPort` (3 methods) | — |
| In-process | `LocalEventAdapter` (dual-role production + test) | ✅ All 3 exact |
| Bus side | `FabricBusAdapter` → `LocalBus.publish()` | ✅ All 3 exact |

Bus adapter serializes Dict → JSON bytes → `Envelope`. Maps between Fabric's `SubscriptionHandle(subscription_id, topic)` and Bus's `SubscriptionHandle(subscription_id, pattern)`.

#### Connection 3: Bus → Fabric (Delta) ✅

| Side | Component | Signature Match |
|------|-----------|----------------|
| Fabric port | `IDeltaBusPort` (1 method) | — |
| Bus side | `FabricBusAdapter.emit_delta()` → `Envelope(priority=REALTIME)` | ✅ Exact |
| Test | `TestDeltaBusAdapter` | ✅ Exact |
| Startup | `NullDeltaBusAdapter` (silent drop) | ✅ Exact |

#### Connection 4: ModelHub → Fabric ⚠️

| Side | Component | Status |
|------|-----------|--------|
| Fabric port | `IModelGatewayPort` (4 methods + `ILLMHandle` sub-protocol) | Defined |
| Fabric adapter | `TestModelGatewayAdapter` (**TEST ONLY**) | No production adapter |
| ModelHub port | `IModelHubPort` (5 methods: `execute`, `stream_execute`, `discover_*`, `health`) | **DIFFERENT INTERFACE** |

**Issue**: `IModelGatewayPort` ≠ `IModelHubPort`. Different types (`Fabric.ModelInfo` ≠ `ModelHub.ModelInfo`), different abstraction levels (token-budget handles vs request/response). No production adapter bridges these. Concierge bypasses Fabric's model port entirely using `IModelHubPort` directly.

**Impact**: Agent Factory's LLM path (`IModelGatewayPort` → `ILLMHandle` → `generate()`) has no production wiring.

#### Connection 5: Bridge → Fabric ⚠️

| Side | Component | Status |
|------|-----------|--------|
| Fabric port | `IBridgePort` (5 methods) | Defined |
| Fabric adapter | `BridgeConnectionAdapter` (expects `client: Any`) | Skeleton — bridge client not yet built |
| Bridge side | **Zero imports from `k1.fabric`** | Not yet aware of K1 Fabric |
| POC | `POCMockBridgeAdapter` (routes via registry handlers) | Working workaround |

**Impact**: `BridgeConnectionAdapter` starts in LOCAL COLD mode. Real K0 bridge communication not yet functional.

#### Connection 6: Fabric → Orchestrator ✅

| Side | Component | Signature Match |
|------|-----------|----------------|
| Orch port | `IFabricGatewayPort` (4 methods) | — |
| Orch adapter | `FabricGatewayAdapter` → wraps `Fabric` facade directly | ✅ All 4 exact |

Imports `Fabric`, `BatchStrategy`, `FabricError` from `k1.fabric.fabric` (adapter layer — architecturally correct).

#### Connection 7: Fabric → Planner ✅

| Side | Component | Signature Match |
|------|-----------|----------------|
| Planner port | `IFabricRetrievalPort` (2 methods) | — |
| Planner adapter | `FabricRetrievalAdapter` → wraps `FabricRetrieval` | ✅ Both exact |

Discovery ONLY (PLAN-06). Timeout: 50ms/attempt, 1 retry. All imports are types only.

#### Connection 8: Fabric → Concierge ✅

| Side | Component | Signature Match |
|------|-----------|----------------|
| Concierge ports | `IFabricPort` (4 methods) + `IDispatchPort` (2 methods) | — |
| Concierge adapter | `FabricDispatchAdapter` | ✅ All 6 exact |

Dual dispatch: LOW tier → `IFabricPort.execute()`, MED/HIGH tier → `orchestrator.handle_task()`.

### 4.3 Cross-Boundary Import Analysis

**Fabric has ZERO outward imports** to any other K1 component. Pure dependency sink. ✅

Other components import from Fabric:

| Import Category | Examples | Assessment |
|----------------|---------|------------|
| Shared types (`k1.fabric.types`) | `CapabilityRequest`, `CapabilityResult`, `RetrievalResult`, `ScoredCapability` | ✅ Legitimate — Fabric owns canonical types |
| Port types (`k1.fabric.ports.*`) | `SessionSnapshot`, `SubscriptionHandle`, `ISessionStateReader` | ✅ Legitimate — shared port vocabulary |
| Facade class (`k1.fabric.fabric`) | `Fabric`, `BatchStrategy` | ✅ Adapter layer only |
| CB impl (`k1.fabric.circuit_breaker`) | `CircuitBreaker` | ✅ Shared infrastructure |

---

## §5 Test Surface

### 5.1 Aggregate Statistics

| Metric | Value |
|--------|-------|
| Test files | **92** (83 root + 9 tools/) |
| Total test functions | **3,958** (3,482 sync + 476 async) |
| Total test lines | **68,893** |
| Infrastructure | conftest.py (365 lines) + helpers.py (311 lines) |

### 5.2 Coverage by Area

| Area | Files | Tests | % | Lines |
|------|:-----:|:-----:|:---:|:-----:|
| Agents | 12 | 550 | 13.9% | 10,444 |
| Providers | 7 | 296 | 7.5% | 5,903 |
| Policy | 5 | 288 | 7.3% | 4,539 |
| Integration | 9 | 284 | 7.2% | 9,052 |
| Tools (e2e) | 9 | 247 | 6.2% | 4,525 |
| Adapters | 4 | 233 | 5.9% | 3,060 |
| Retrieval | 3 | 220 | 5.6% | 2,241 |
| Registry | 4 | 214 | 5.4% | 2,537 |
| Ports | 2 | 191 | 4.8% | 1,739 |
| Output Validation | 3 | 191 | 4.8% | 3,171 |
| Context | 3 | 141 | 3.6% | 2,088 |
| Contracts | 2 | 103 | 2.6% | 1,253 |
| Health | 2 | 100 | 2.5% | 2,157 |
| Types | 1 | 84 | 2.1% | 922 |
| Safety | 3 | 90 | 2.3% | 1,590 |
| Invariants | 3 | 75 | 1.9% | 2,041 |
| Benchmarks | 4 | 71 | 1.8% | 3,786 |
| Circuit Breaker | 3 | 72 | 1.8% | 2,233 |
| Concurrency | 1 | 59 | 1.5% | 1,208 |
| Module Loader | 2 | 56 | 1.4% | 1,267 |
| Wiring Contract | 1 | 53 | 1.3% | 570 |
| Module Contract | 1 | 33 | 0.8% | 437 |
| Lifecycle | 1 | 42 | 1.1% | 680 |
| Events | 1 | 41 | 1.0% | 484 |
| Metrics/Logging | 2 | 38 | 1.0% | 394 |
| Load Testing | 2 | 24 | 0.6% | 1,618 |

### 5.3 Notable Test Files

| File | Tests | Lines | Why Notable |
|------|:-----:|:-----:|-------------|
| `test_ports_514_516.py` | **108** | 897 | Most test functions — IModelGatewayPort, IPromptSystemPort, IDeltaBusPort |
| `test_output_validation_351_355.py` | **106** | 1,443 | All 5 output validation sub-issues |
| `test_context_421_423.py` | **88** | 937 | Context builder + SessionState integration |
| `test_agent_spec_validator_451.py` | **85** | 800 | All 7 agent spec validation rules |
| `test_policy_context_agent.py` | 42 | **2,093** | Largest file — full cross-subsystem chain |
| `test_loader_registry_retrieval.py` | 49 | **1,950** | Cross-subsystem: Loader → Registry → Retrieval |

### 5.4 Testing Strategy

- **No mocks anywhere** — entire suite uses real adapters per "No-Mock Testing Strategy"
- Shared fixtures in conftest.py: `fabric_standalone`, `fabric_for_testing`, `registry`, `event_adapter`, sample contracts
- Helper utilities in helpers.py: `load_fixture_contract()`, `create_n_contracts()`, `register_contract_with_provider()`, `assert_capability_result_*()`, `wait_for_event()`
- Cross-component isolation excellent: only 1 peer import (`k1.sessionstate` in wiring contract compliance test)

---

## §6 Spec vs Code Delta

### 6.1 Diagram vs Code Discrepancies

| # | Area | Diagram Says | Code Says | Severity |
|---|------|-------------|-----------|----------|
| 1 | Agent Factory steps | fabric.mmd: 8 steps | fabric_new.mmd + code: Step 2 (Mailbox) is stub `None` (Epic 4.4 deferred) | 🟡 Expected — ADR-1.1.9 bypassed mailbox |
| 2 | Concurrency model | fabric.mmd: Semaphore(10) | Code: `FabricDispatcher` with Semaphore(10) + 4-level backpressure + priority shedding | 🟢 Code exceeds spec |
| 3 | Output validation T3 | fabric.mmd: "semantic with hallucination detection" | Code: Rule-based only (no LLM), 3 check categories, ANNOTATE-only (never reject) | 🟢 Conservative implementation |
| 4 | TimeoutGuard | fabric_new.mmd lists it | NOT wired into `_execute_impl()` — CB provides timeout | 🟡 Available but unused in main path |

### 6.2 Missing Production Adapters

| Port | Impact | Path Forward |
|------|--------|-------------|
| `IModelGatewayPort` | 🔴 Agent Factory has no production LLM path | Build adapter bridging to `IModelHubPort` or ModelHub's concrete API |
| `IPromptSystemPort` | 🟡 Context builder prompt resolution limited to test mode | Build adapter wrapping production prompt store |
| `IDeltaBusPort` | 🟢 Bus-side `FabricBusAdapter` serves as production adapter | Already resolved via Bus component |

### 6.3 Unwired Components

| Component | Status | Impact |
|-----------|--------|--------|
| Bridge client | Not yet built | `BridgeConnectionAdapter` starts in LOCAL COLD; K0 communication offline |
| `IModelGatewayPort` → `IModelHubPort` bridge | Not yet built | Two parallel LLM paths exist (Fabric vs Concierge direct) |
| QoS `cost_per_call` | Always `None` in `PolicyEngine._eval_qos()` | Only latency scoring active; cost dimension fully implemented but unwired |
| TimeoutGuard | Available in `concurrency/timeout.py` | Not wired into main execution pipeline (CB handles timeout) |
| `capability_types/` | Empty `__init__.py` | Placeholder package |
| `module_registry/` | Empty `__init__.py` | Placeholder package |

### 6.4 Architectural Observations

1. **Fabric is a pure dependency sink** — zero outward imports to other K1 components
2. **All contracts are frozen dataclasses** — mutations use `dataclasses.replace()`, atomic swap under lock
3. **Thread safety model is consistent**: RLock for mutations, lock-free reads, events emitted outside locks
4. **Protocol-based DI throughout** — ~15+ Protocol definitions for substitution without hard imports
5. **Two parallel LLM paths**: Fabric path (`IModelGatewayPort` → `ILLMHandle`) for Agent Factory, Concierge path (`IModelHubPort` → `HubRequest/HubResponse`) for direct LLM — intentionally different abstraction levels
6. **EmbeddingIndex full rebuild** on every single add/remove — O(N) per mutation, fine for registration-time but potential bottleneck under frequent hot-reload
7. **HardFilter Rule 3 relaxation**: With `planner_can_ask=True` (default), input satisfiability check is effectively a no-op
8. **Workflow CB uniquely conservative**: 60s timeout, 1 failure threshold, 1 retry — reflects multi-step expense
