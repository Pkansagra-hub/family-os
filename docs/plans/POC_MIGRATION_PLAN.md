# POC → K1 Production Migration Plan

**Branch**: `POC_Migration` (from `develop`)
**Strategy**: Port-First in POC, Copy Once
**Principle**: Add ports at POC boundaries → verify tests green → single copy to `k1/concierge/` → swap adapters
**Created**: 2026-03-29
**Status**: SKELETON — Milestones defined, Epics & Issues TBD

---

## Migration Philosophy

> The POC is the organ. K1 is the skeleton. We transplant organs into the skeleton, not rebuild organs from bone.

- **Do NOT rewrite** working POC internals (FSM, ReAct, Prompt Builder, OPP, HITL, Weave)
- **Do add** port interfaces at the 4 boundary points where POC makes direct calls
- **Do write** two adapters per port: POC adapter (keeps tests green) + K1 adapter (targets production layer)
- **Do copy** the entire POC into `k1/concierge/` in one go after all ports are wired
- **Do verify** each milestone with its own test gate before proceeding

---

## Milestone Overview

| # | Milestone | Theme | Gate |
|---|-----------|-------|------|
| M0 | Pre-Flight | Baseline audit, test inventory, dependency map | All POC tests pass on `POC_Migration` branch |
| M1 | Port: IModelPort | Extract LLM boundary | Tests pass with POC model adapter |
| M2 | Port: ICapabilityPort | Extract Fabric/tool boundary | Tests pass with POC capability adapter |
| M3 | Port: IBusPort | Normalize bus interface | Tests pass with POC bus adapter |
| M4 | Port: IStoragePort Audit | Verify SS ports already clean | SS port contract tests pass |
| M5 | The Big Copy | POC → `k1/concierge/` | All imports resolve, all tests pass from new location |
| M6 | K1 Fabric Wiring | Swap `ICapabilityPort` → real Fabric | Capabilities resolve through `k1/fabric/` |
| M7 | K1 Model Hub Wiring | Swap `IModelPort` → Model Hub | LLM calls route through `k1/model_hub/` |
| M8 | K1 Orchestrator Wiring | MEDIUM tier through Orchestrator | MEDIUM tasks route through `k1/orchestrator/` |
| M9 | K1 Planner Wiring | HIGH tier through Planner | HIGH tasks route through `k1/planner/` (future) |
| M10 | Integration & Hardening | E2E tests, perf benchmarks, cleanup | Full regression green, latency within budget |

---

## M0 — Pre-Flight

> Establish baseline: what do we have, what passes, what depends on what.
> **Gate**: All POC tests pass on `POC_Migration` branch. Dependency map validated. Test inventory documented.

### Baseline Numbers

| Metric | Count |
|--------|-------|
| External test files (`tests/poc/`) | 73 |
| External test functions | 3,054 |
| Internal harness test files (`poc/k1_poc/testing/harness/`) | 10 |
| Internal harness test functions | 207 |
| **Total test functions** | **3,261** |
| Production .py files (`poc/k1_poc/`, excl demo/testing) | ~138 |
| Demo-only .py files (`poc/k1_poc/demo/`) | ~9 |
| Test harness .py files | ~21 |
| Config files (`poc/k1_poc/config/`) | 3 (loader.py, **init**.py, defaults.yaml) |
| POC folders (top-level in `poc/k1_poc/`) | 22 |
| K1 concierge .py files (existing) | 5 (all empty `__init__.py`) |
| External PyPI dependencies | 1 (google.genai, lazy-loaded) |
| K1 framework dependencies | k1.bus.* only |

### Epic E0.1 — Run Full Test Suite on POC_Migration Branch

> Verify that the branch merge didn't break anything. Establish the exact green/red/skip baseline.

**Issue E0.1.1** — Run `tests/poc/` full suite, record pass/fail/skip counts

- Run: `python -m pytest tests/poc/ -v --tb=short`
- Record: total, passed, failed, skipped, errors
- File: capture output to `docs/test_results/m0_external_baseline.txt`
- Touch points: none (read-only audit)

**Issue E0.1.2** — Run `poc/k1_poc/testing/harness/` internal suite

- Run: `python -m pytest poc/k1_poc/testing/harness/ -v --tb=short`
- Record: total, passed, failed, skipped, errors
- File: capture output to `docs/test_results/m0_internal_baseline.txt`

**Issue E0.1.3** — Document any existing failures as known-issues

- If any tests fail, create a `docs/plans/M0_KNOWN_FAILURES.md` listing each failure with root cause
- Classify each as: `migration-blocker` (must fix before M1) or `pre-existing` (existed before merge)

### Epic E0.2 — Validate Dependency Map

> Confirm the auto-generated dependency map at `poc/k1_poc/docs/DEPENDENCY_MAP.md` (dated 2026-02-23) is still accurate after recent changes.

**Issue E0.2.1** — Regenerate import graph and diff against existing

- Script: walk all `.py` under `poc/k1_poc/`, extract `from poc.k1_poc.X import` lines
- Compare against `poc/k1_poc/docs/DEPENDENCY_MAP.md` Section 4 (folder-to-folder matrix)
- Touch points: every `.py` file under `poc/k1_poc/` (read-only scan)
- Output: updated `DEPENDENCY_MAP.md` if any new cross-folder imports found

**Issue E0.2.2** — Verify zero circular dependencies

- From the import graph, check that no folder cycle exists (A→B→C→A)
- Known safe pattern: `kernel/bootstrap.py` imports everything (hub), but nothing imports `kernel/`
- If circular dep found: document and flag as migration-blocker

**Issue E0.2.3** — Document k1.* framework imports

- List every `from k1.*` import across POC code
- Currently known: `k1.bus.envelope`, `k1.bus.factory`, `k1.bus.impl.local_bus`, `k1.bus.impl.local_mailbox`, `k1.bus.ports.bus`, `k1.bus.ports.mailbox`, `k1.bus.timing.defaults`, `k1.bus.timing.timing_chain`, `k1.bus.adapters`
- Touch points: `fsm/controller.py`, `actors/back.py`, `bus/setup.py`, `kernel/bootstrap.py`
- Purpose: these are the imports that WON'T change path during the Big Copy (M5) since k1.bus stays at k1.bus

### Epic E0.3 — Classify POC Files: Copy vs Stay vs Drop

> Every file in `poc/k1_poc/` must be tagged as one of: COPY (goes to k1/concierge), STAY (remains in poc/ for demo), DROP (dead code).

**Issue E0.3.1** — Tag all `poc/k1_poc/demo/` files as STAY

- Files: `coordinator.py`, `coordinator_old.py`, `interactive.py`, `display.py`, `output_channel.py`, `iot_stubs.py`, `smith_family.py`, `preloaded_memories.py`, `runner.py`, `web/` directory
- Rationale: demo harness, Smith family data, interactive UI — not production
- Touch points: none (classification only)

**Issue E0.3.2** — Tag all `poc/k1_poc/testing/` files as STAY

- Files: `harness/engine.py`, `harness/test_*.py`, `fixtures/*.py`
- Rationale: test utilities — reference tests/poc/ instead after migration

**Issue E0.3.3** — Tag production files as COPY

- Tag the following 22 directories as COPY targets:
  `actors/`, `bus/`, `compression/`, `config/`, `delta/`, `events/`, `experience/`, `fabric/`, `fsm/`, `identity/`, `kernel/`, `ledger/`, `llm/`, `obs/`, `orchestrator/`, `prompt/`, `protocols/`, `react/`, `scheduler/`, `sessionstate/`, `task/`, `tools/`
- Touch points: none (classification only)

**Issue E0.3.4** — Identify dead code candidates for DROP

- Scan for files not imported by anything (orphans)
- Check `coordinator_old.py` (superseded by `coordinator.py`)
- Check any `*.py.bak` or commented-out files
- Output: list of DROP candidates with justification

### Epic E0.4 — Audit K1 Concierge Target Structure

> Understand what already exists in `k1/concierge/` and what needs to be created/replaced.

**Issue E0.4.1** — Document existing k1/concierge/ contents

- Current state: 5 empty `__init__.py` files in `k1/concierge/`, `k1/concierge/affective/`, `k1/concierge/empathy/`, `k1/concierge/rhythm/`, `k1/concierge/tools/`
- Docs: `concierge.md`, `concierge.mmd`, `concierge_fsm_flows.md`, `README.md`
- Decision needed: do we keep/merge existing docs or replace entirely from POC?

**Issue E0.4.2** — Map POC directories → K1 concierge directories

- Create mapping table:

  | POC Source | K1 Target | Notes |
  |---|---|---|
  | `poc/k1_poc/actors/` | `k1/concierge/actors/` | New directory |
  | `poc/k1_poc/bus/` | `k1/concierge/bus/` | New; wraps k1/bus/ |
  | `poc/k1_poc/compression/` | `k1/concierge/compression/` | New |
  | `poc/k1_poc/config/` | `k1/concierge/config/` | Merge with k1/config/? |
  | `poc/k1_poc/delta/` | `k1/concierge/delta/` | New |
  | `poc/k1_poc/events/` | `k1/concierge/events/` | New |
  | `poc/k1_poc/experience/` | `k1/concierge/experience/` | Replaces empty `affective/`, `empathy/`, `rhythm/` |
  | `poc/k1_poc/fabric/` | `k1/concierge/fabric/` | New; bridge to k1/fabric/ |
  | `poc/k1_poc/fsm/` | `k1/concierge/fsm/` | New |
  | `poc/k1_poc/identity/` | `k1/concierge/identity/` | New |
  | `poc/k1_poc/kernel/` | `k1/concierge/kernel/` | New; bootstrap becomes concierge entry point |
  | `poc/k1_poc/ledger/` | `k1/concierge/ledger/` | New |
  | `poc/k1_poc/llm/` | `k1/concierge/llm/` | New; port+adapter for model hub |
  | `poc/k1_poc/obs/` | `k1/concierge/obs/` | New |
  | `poc/k1_poc/orchestrator/` | `k1/concierge/orchestrator/` | New; bridge to k1/orchestrator/ |
  | `poc/k1_poc/prompt/` | `k1/concierge/prompt/` | New |
  | `poc/k1_poc/protocols/` | `k1/concierge/protocols/` | New |
  | `poc/k1_poc/react/` | `k1/concierge/react/` | New |
  | `poc/k1_poc/scheduler/` | `k1/concierge/scheduler/` | New |
  | `poc/k1_poc/sessionstate/` | `k1/concierge/sessionstate/` | New; already has ports |
  | `poc/k1_poc/task/` | `k1/concierge/task/` | New |
  | `poc/k1_poc/tools/` | `k1/concierge/tools/` | Replaces empty `k1/concierge/tools/` |

**Issue E0.4.3** — Decide: config merge strategy

- POC has `poc/k1_poc/config/defaults.yaml` (59 tunable parameters)
- K1 has `k1/config/` (separate config structure)
- Decision: Does concierge carry its own config, or merge into k1/config/?
- This affects import paths in `config/loader.py` and every file that calls `get_config()`

### Epic E0.5 — Audit Smith Family Demo Isolation (Completed)

> Verify POC engine is not contaminated by demo-specific data.

**Issue E0.5.1** — ✅ Confirm engine layer has zero Smith family data

- Result: FSM, ReAct, Prompt Builder (builder.py), SessionState, Bus, Delta, OPP, HITL, Weave — all **CLEAN**
- `prompt/sections.py` has Smith names in **few-shot examples only** (teaches patterns, not data injection)
- `fabric/family_capabilities.py` has mock return values with Smith defaults — replaced entirely by M6 (Fabric Wiring)

**Issue E0.5.2** — ✅ Confirm data injection is parameter-driven

- `KernelConfig.seed_memories` — accepts any family's data, no hardcoding
- `build_persona_from_profile(family_profile)` — accepts any profile dict
- `recall_fn` — generic keyword-match engine, receives memories as parameter
- Demo data enters ONLY through `demo/coordinator.py` → `KernelConfig`

### Epic E0.6 — Integration Test: Branch Health Verification

> Final gate: confirm the POC_Migration branch is healthy and ready for M1.

**Issue E0.6.1** — Run full test suite (external + internal), require 100% pass

- Depends on: E0.1.1, E0.1.2, E0.1.3 (any migration-blockers must be fixed first)
- Command: `python -m pytest tests/poc/ poc/k1_poc/testing/harness/ --tb=short`
- Gate: 3,261 tests pass (or documented known-failures classified as pre-existing)

**Issue E0.6.2** — Run import smoke test

- Script: `python -c "from poc.k1_poc.kernel.bootstrap import start_kernel; print('OK')"`
- Verifies the full import chain resolves on this branch
- Touch points: validates `kernel/bootstrap.py` → all 12 cross-folder deps

**Issue E0.6.3** — Tag baseline

- Git tag: `m0-preflight-baseline`
- Ensures we can always diff back to the pre-migration state

---

## M1 — IModelPort (Build K1 Model Hub Contract + POC Bridge)

> K1 Model Hub has ZERO Python code — only `k1/model_hub/model_hub.mmd` (700+ line production spec).
> This milestone **first builds the K1 Model Hub public contract** (types, ports, plugin interface)
> per the `.mmd` diagram, then creates a POC bridge adapter so the Concierge speaks Model Hub's
> language from day one. After M5 (Big Copy), the bridge swaps for the real Model Hub service (M7).

**K1 Model Hub status**: Only `k1/model_hub/model_hub.mmd` exists. Zero `.py` files.
**POC LLM layer**: 6 files in `poc/k1_poc/llm/` — `ports.py`, `types.py`, `gemini_adapter.py`, `test_adapter.py`, `model_selection.py`, `validator.py`
**POC callers**: `react/loop.py` (sole `ConciergeModelRequest` constructor, line 340), `actors/front.py` (passes `model: IConciergeModelPort`), `actors/back.py` (passes `model: IConciergeModelPort`, 3 handler functions), `kernel/bootstrap.py` (`_create_model()` factory + `KernelRuntime.model`)
**Concierge diagram ref**: `k1/concierge/concierge.mmd` defines `ILLMPort` outbound port using `HubRequest`/`HubResponse` from `k1.model_hub.types`

### Mapping: POC types → K1 Model Hub types (from mmd)

| POC Type (poc.k1_poc.llm.types) | K1 Model Hub Type (k1.model_hub.types) | Notes |
|---|---|---|
| `Capability` enum (CHAT, TOOL_CALL, STRUCTURED, STREAM, REASON) | `CapabilityType` enum (CHAT, TOOL_CALL, STRUCTURED, REASON, EMBED, VISION, + 10 more) | K1 superset; STREAM becomes a flag on HubRequest, not a capability |
| `ConciergeModelRequest` | `HubRequest` (capability + payload + constraints + trace_id) | Flat → structured (capability-specific payloads) |
| `ConciergeModelRequest.system_prompt` + `.messages` + `.tools` | `ToolCallPayload.system_prompt` + `.messages` + `.tools` | Payload is polymorphic by capability |
| `ConciergeModelRequest.max_tokens` / `.timeout_ms` / `.temperature` | `RequestConstraints.max_tokens` / `.timeout_ms` / `.temperature` | Budget moves to constraints |
| `ConciergeModelRequest.actor` / `.scenario` | `RequestConstraints.consumer_id` (e.g. `"concierge.front"`) + `RequestConstraints.priority` | Actor/scenario collapse to consumer_id + priority enum |
| `ConciergeModelRequest.model_hint` | `RequestConstraints.model_preference` / `.provider_preference` | Hint string → typed preference |
| `ConciergeModelRequest.thinking` (ThinkingLevel) | `ReasonPayload.reasoning_effort` (low/medium/high) | Thinking moves into REASON payload |
| `ConciergeModelResponse` | `HubResponse` (result + metadata) | Flat → structured |
| `ConciergeModelResponse.text` / `.tool_calls` / `.json_output` | `HubResponse.result` (CapabilityResult, polymorphic) | Result type depends on capability |
| `ConciergeModelResponse.tokens_in` / `.tokens_out` / `.latency_ms` / `.model_id` | `ResponseMetadata.usage` / `.latency_ms` / `.model_id` | Usage is nested dataclass |
| `ConciergeModelResponse.finish_reason` (FinishReason) | `ResponseMetadata.finish_reason` | Moves to metadata |
| `StreamChunk` | `HubChunk` | Same concept, K1 naming |
| `ToolSchema` | `ToolDefinition` (in ToolCallPayload) | Rename, same schema shape |
| `ModelMessage` | `Message` (in payload) | Rename, same fields |
| `IConciergeModelPort` (generate/generate_stream) | `IModelHubPort` (execute/stream_execute) | Method rename + type changes |

### Epic E1.1 — Build K1 Model Hub Public Types

> Create `k1/model_hub/types.py` — the **source of truth** for all Model Hub consumers.
> Every type comes directly from the mmd diagram specification.

**Issue E1.1.1** — Create `k1/model_hub/types.py` with all public types

From mmd diagram, implement as frozen dataclasses / enums:

- `CapabilityType(str, Enum)` — CHAT, TOOL_CALL, STRUCTURED, REASON, EMBED, VISION, BATCH, MODERATE, TOKEN_COUNT, CACHE_PROMPT, AUDIO_IN, TTS, IMAGE_GEN, WEB_SEARCH, CODE_EXEC
- `Priority(str, Enum)` — REALTIME, INTERACTIVE, BACKGROUND
- `ModelPreference` dataclass — `model_id: str | None`, `provider_id: str | None`, `tier: str | None` (FAST/STANDARD/PREMIUM)
- `RequestConstraints` dataclass — `max_tokens`, `timeout_ms`, `priority`, `temperature`, `model_preference`, `provider_preference`, `cost_limit`, `consumer_id`
- `HubRequest` dataclass — `capability: CapabilityType`, `payload: CapabilityPayload`, `constraints: RequestConstraints`, `trace_id: str`, `idempotency_key: str | None`
- `Usage` dataclass — `prompt_tokens`, `completion_tokens`, `total_tokens`
- `ResponseMetadata` dataclass — `request_id`, `model_id`, `provider_id`, `usage: Usage`, `cost_usd`, `latency_ms`, `cache_hit`, `capability`, `trace_id`, `fallback_used`, `finish_reason`
- `HubResponse` dataclass — `result: CapabilityResult`, `metadata: ResponseMetadata`
- `HubChunk` dataclass — `chunk_type` (text_delta/tool_call_delta/thought_delta/done), `text`, `tool_call_partial`, `thought_text`, `response: HubResponse | None`
- Capability payloads (all frozen dataclasses):
  - `ChatPayload` — `messages: list[Message]`, `system_prompt: str`
  - `ToolCallPayload` — `messages`, `system_prompt`, `tools: list[ToolDefinition]`, `tool_choice`, `parallel_tool_calls`
  - `StructuredOutputPayload` — `messages`, `system_prompt`, `output_schema: dict`, `strict: bool`
  - `ReasonPayload` — `messages`, `system_prompt`, `reasoning_effort: str`, `include_thinking: bool`
  - `VisionPayload` — `messages`, `image_inputs: list[ImageInput]`, `detail: str`
- `Message` dataclass — `role`, `content`, `tool_call_id`, `name`, `tool_calls`
- `ToolDefinition` dataclass — `name`, `description`, `parameters: dict`
- `ToolCallResult` dataclass — `id`, `name`, `arguments: dict`
- `CapabilityPayload` — Union type of all payload classes
- `CapabilityResult` — Union type of all result classes (ChatResult with .text, ToolCallResult list, StructuredResult with .json_output, etc.)

Touch point: NEW file `k1/model_hub/types.py` (~250 lines)
Depends on: nothing (leaf module, zero imports from k1.*)

**Issue E1.1.2** — Update `k1/model_hub/__init__.py` with public exports

Touch point: EDIT `k1/model_hub/__init__.py` (currently empty)
Export all public types from `types.py`

### Epic E1.2 — Build IModelHubPort + All 7 Ports

> Create `k1/model_hub/ports.py` — the hexagonal boundary contracts per mmd.
> These are `typing.Protocol` classes, no implementation.

**Issue E1.2.1** — Create `k1/model_hub/ports.py` with all 7 ports

From mmd diagram PORTS section, implement as `@runtime_checkable Protocol`:

- `IModelHubPort` (Inbound — THE Single Gateway):
  - `execute(request: HubRequest) -> HubResponse`
  - `stream_execute(request: HubRequest) -> AsyncIterator[HubChunk]`
  - `discover_capabilities() -> dict[CapabilityType, list[str]]`
  - `discover_models(capability: CapabilityType | None = None) -> list[ModelInfo]`
  - `health() -> HubHealthReport`
- `IEventPort` (Both): `publish(topic, payload)`, `subscribe(topics, handler)`
- `IStateReadPort` (Inbound read-only): `read(sections: list[str]) -> StateSnapshot`
- `IMetricsPort` (Outbound): `emit(metric_name, value, labels)`
- `IConfigPort` (Inbound): `get(key)`, `watch(key, callback)`
- `ICredentialPort` (Inbound): `get_key(provider_id)`, `refresh_key(provider_id)`
- `IHealthPort` (Outbound): `report_health(component, status)`, `check_health()`
- Supporting types: `ModelInfo`, `HubHealthReport`, `StateSnapshot`, `ProviderHealthStatus`

Touch point: NEW file `k1/model_hub/ports.py` (~120 lines)
Depends on: E1.1.1 (imports from `k1.model_hub.types`)

### Epic E1.3 — Build IProviderPlugin Contract

> Create `k1/model_hub/plugins/` — the extensibility contract that ALL providers implement.
> Per mmd: "ADDING A NEW PROVIDER: 1. Create manifest YAML, 2. Implement IProviderPlugin (5 methods), 3. Place in plugins/, 4. Auto-discovered on startup, 5. DONE."

**Issue E1.3.1** — Create `k1/model_hub/plugins/base.py` with IProviderPlugin + internal types

From mmd diagram PLUGIN_INTERFACE section:

- `IProviderPlugin(Protocol)`:
  - `initialize(manifest: ProviderManifest) -> None`
  - `supports(capability: CapabilityType) -> bool`
  - `execute(request: NormalizedRequest) -> ProviderResponse`
  - `stream_execute(request: NormalizedRequest) -> AsyncIterator[ProviderChunk]`
  - `estimate_tokens(messages: list[Message]) -> int`
  - `health_check() -> ProviderHealth`
  - `close() -> None`
- `NormalizedRequest` dataclass — provider-agnostic intermediate form (between HubRequest and provider-native API)
- `ProviderResponse` dataclass — provider-agnostic response
- `ProviderChunk` dataclass — streaming chunk from provider
- `ProviderHealth` dataclass — `status: str` (HEALTHY/DEGRADED/UNHEALTHY), `latency_ms`, `error_rate`
- `ProviderManifest` dataclass — parsed YAML manifest structure (provider_id, display_name, plugin_class, capabilities, models, circuit_breaker config, etc.)

Touch point: NEW file `k1/model_hub/plugins/__init__.py` (empty) + NEW file `k1/model_hub/plugins/base.py` (~150 lines)
Depends on: E1.1.1 (imports CapabilityType, Message from types)

**Issue E1.3.2** — Create `k1/model_hub/plugins/test_plugin.py`

From mmd diagram ADAPTERS_TEST section (TestProviderPlugin):

- `TestProviderPlugin(IProviderPlugin)`:
  - Deterministic responses, configurable per test
  - Set response for (capability) → ProviderResponse
  - Set response sequence for multi-call tests
  - Configurable latency, errors, token counts, streaming chunks
  - Can be registered as any provider_id for test isolation
  - Records all calls for assertions

Touch point: NEW file `k1/model_hub/plugins/test_plugin.py` (~100 lines)
Depends on: E1.3.1 (imports IProviderPlugin, NormalizedRequest, etc.)

### Epic E1.4 — Build POC Bridge Adapter (IModelHubPort → GeminiConciergeAdapter)

> Creates a bridge that implements `IModelHubPort` but internally delegates to the existing
> `GeminiConciergeAdapter`. This lets POC callers switch to K1 types while the real Model Hub
> is built (M7). The bridge translates HubRequest ↔ ConciergeModelRequest and
> ConciergeModelResponse ↔ HubResponse using the mapping table above.

**Issue E1.4.1** — Create `poc/k1_poc/llm/model_hub_bridge.py` — ModelHubPOCBridge

Class: `ModelHubPOCBridge` implements `IModelHubPort`

Constructor: `__init__(self, inner: GeminiConciergeAdapter | TestConciergeAdapter)`

Translation methods (private):

- `_hub_to_poc_request(hub_req: HubRequest) -> ConciergeModelRequest`:
  - `hub_req.capability` (CapabilityType) → `Capability` enum mapping
  - `hub_req.payload.messages` → `ConciergeModelRequest.messages` (Message → ModelMessage)
  - `hub_req.payload.system_prompt` → `ConciergeModelRequest.system_prompt`
  - `hub_req.payload.tools` (if ToolCallPayload) → `ConciergeModelRequest.tools` (ToolDefinition → ToolSchema)
  - `hub_req.payload.tool_choice` → `ConciergeModelRequest.tool_choice`
  - `hub_req.constraints.max_tokens` → `ConciergeModelRequest.max_tokens`
  - `hub_req.constraints.timeout_ms` → `ConciergeModelRequest.timeout_ms`
  - `hub_req.constraints.temperature` → `ConciergeModelRequest.temperature`
  - `hub_req.constraints.consumer_id` → `ConciergeModelRequest.actor` (parse "concierge.front" → "front")
  - `hub_req.constraints.priority` → `ConciergeModelRequest.scenario` (derive from priority + capability)
  - `hub_req.constraints.model_preference` → `ConciergeModelRequest.model_hint`
  - `hub_req.trace_id` → `ConciergeModelRequest.trace_id`
  - If `ReasonPayload`: map `reasoning_effort` → `ThinkingLevel`

- `_poc_to_hub_response(poc_resp: ConciergeModelResponse, capability: CapabilityType, trace_id: str) -> HubResponse`:
  - `poc_resp.text` → `ChatResult.text` (or ToolCallResult)
  - `poc_resp.tool_calls` → `ToolCallResult` list in result
  - `poc_resp.json_output` → `StructuredResult.json_output`
  - `poc_resp.tokens_in`/`.tokens_out` → `ResponseMetadata.usage`
  - `poc_resp.latency_ms` → `ResponseMetadata.latency_ms`
  - `poc_resp.model_id` → `ResponseMetadata.model_id`
  - `poc_resp.finish_reason` → `ResponseMetadata.finish_reason`

Public methods (IModelHubPort):

- `execute(HubRequest) -> HubResponse` — translate, call `inner.generate()`, translate back
- `stream_execute(HubRequest) -> AsyncIterator[HubChunk]` — translate, call `inner.generate_stream()`, map `StreamChunk` → `HubChunk`
- `discover_capabilities()` — hardcoded: CHAT, TOOL_CALL, STRUCTURED, REASON (POC Day 1 set)
- `discover_models()` — delegates to `model_selection.py` tables
- `health()` — always HEALTHY (POC has no circuit breakers)

Touch point: NEW file `poc/k1_poc/llm/model_hub_bridge.py` (~200 lines)
Depends on: E1.1.1 (k1.model_hub.types), E1.2.1 (k1.model_hub.ports), existing `gemini_adapter.py`

**Issue E1.4.2** — Create `poc/k1_poc/llm/test_model_hub_bridge.py` — TestModelHubBridge

Same pattern as E1.4.1 but wraps `TestConciergeAdapter`:

- `TestModelHubBridge(inner: TestConciergeAdapter)` implements `IModelHubPort`
- Exposes `inner` for test configuration: `bridge.inner.set_response("front", "user_input", ...)`
- Alternatively: add `set_response()` / `set_response_sequence()` pass-through methods

Touch point: NEW file `poc/k1_poc/llm/test_model_hub_bridge.py` (~80 lines)
Depends on: E1.4.1, existing `test_adapter.py`

### Epic E1.5 — Migrate POC Callers to IModelHubPort + K1 Types

> Change all POC callers from `IConciergeModelPort` / `ConciergeModelRequest` / `ConciergeModelResponse`
> to `IModelHubPort` / `HubRequest` / `HubResponse`. The bridge adapter (E1.4) ensures existing
> Gemini/test behaviour is preserved. Tests must stay green after each file.

**Issue E1.5.1** — Migrate `poc/k1_poc/react/loop.py`

This is the **only** file that constructs `ConciergeModelRequest` (line 340).

Changes:

- Import: replace `from poc.k1_poc.llm.ports import IConciergeModelPort` → `from k1.model_hub.ports import IModelHubPort`
- Import: replace `from poc.k1_poc.llm.types import ConciergeModelRequest, ConciergeModelResponse, ...` → `from k1.model_hub.types import HubRequest, HubResponse, HubChunk, CapabilityType, RequestConstraints, ToolCallPayload, ChatPayload, ...`
- `_streaming_generate()` signature: `model: IConciergeModelPort` → `model: IModelHubPort`
- `_streaming_generate()` body: `model.generate_stream(request)` → `model.stream_execute(request)`, `model.generate(request)` → `model.execute(request)`, `StreamChunk` → `HubChunk`
- `react_loop()` signature: `model: IConciergeModelPort` → `model: IModelHubPort`
- `react_loop()` line 340: replace `ConciergeModelRequest(...)` constructor with `HubRequest(capability=..., payload=ToolCallPayload(...) or ChatPayload(...), constraints=RequestConstraints(...), trace_id=...)`
- `react_loop()` response handling: `response.text` → `response.result.text`, `response.tool_calls` → `response.result.tool_calls`, `response.finish_reason` → `response.metadata.finish_reason`, etc.
- Keep `from poc.k1_poc.llm.types import ModelMessage, ToolSchema` for internal message building (these stay POC types until E1.5.4 internal cleanup)
- ALTERNATIVE: If response field access is too pervasive, keep a thin `_unwrap(hub_response) -> ConciergeModelResponse` helper inside loop.py to minimise diff

Touch points: EDIT `poc/k1_poc/react/loop.py` — imports (lines 25-35), `_streaming_generate` (lines 168-201), `react_loop` request construction (lines 340-365), response access (~10 sites in react_loop body)

**Issue E1.5.2** — Migrate `poc/k1_poc/actors/front.py`

Changes:

- Import: replace `from poc.k1_poc.llm.ports import IConciergeModelPort` → `from k1.model_hub.ports import IModelHubPort`
- `front_handler()` signature (line 619): `model: IConciergeModelPort` → `model: IModelHubPort`
- All internal calls already pass `model` to `react_loop()` which handles the actual LLM call — no request construction in this file
- Docstrings: update "IConciergeModelPort" → "IModelHubPort"

Touch point: EDIT `poc/k1_poc/actors/front.py` — import (line 46), signature (line 619), docstring (line 635)

**Issue E1.5.3** — Migrate `poc/k1_poc/actors/back.py`

Changes:

- Import: replace `from poc.k1_poc.llm.ports import IConciergeModelPort` → `from k1.model_hub.ports import IModelHubPort`
- 3 handler function signatures:
  - `back_handler()` (line 409): `model: IConciergeModelPort` → `model: IModelHubPort`
  - `back_resume_handler()` (line 596): `model: IConciergeModelPort` → `model: IModelHubPort`
  - 3rd handler (line 891): `model: IConciergeModelPort` → `model: IModelHubPort`
- All internal calls pass `model` to `react_loop()` — no request construction in this file
- Docstrings: update references

Touch point: EDIT `poc/k1_poc/actors/back.py` — import (line 55), signatures (lines 409, 596, 891), docstrings

**Issue E1.5.4** — Migrate `poc/k1_poc/kernel/bootstrap.py`

Changes:

- `_create_model()` (line 643): return type is now `IModelHubPort`
  - Test mode: `TestConciergeAdapter()` → `TestModelHubBridge(TestConciergeAdapter())`
  - Live mode: `GeminiConciergeAdapter(api_key=...)` → `ModelHubPOCBridge(GeminiConciergeAdapter(api_key=...))`
  - Fallback: same wrapping pattern
- `KernelRuntime.model` (line 92): type annotation `Any` → `IModelHubPort` (or keep Any for now)
- Imports: add `from poc.k1_poc.llm.model_hub_bridge import ModelHubPOCBridge` and `from poc.k1_poc.llm.test_model_hub_bridge import TestModelHubBridge`

Touch point: EDIT `poc/k1_poc/kernel/bootstrap.py` — imports (top), `_create_model()` (lines 643-657), optionally `KernelRuntime` type (line 92)

### Epic E1.6 — Update LLM Validator for K1 Types

> `LLMOutputValidator` currently validates `ConciergeModelResponse`. After E1.5, the react loop
> receives `HubResponse`. The validator must accept the new type.

**Issue E1.6.1** — Update `poc/k1_poc/llm/validator.py` to accept HubResponse

Two options (decide during implementation):

- **Option A** (minimal diff): Add `_unwrap_hub_response(hr: HubResponse) -> ConciergeModelResponse` at the top of `validate()`. Internal validation logic stays unchanged. This is a thin shim.
- **Option B** (clean): Change `validate()` to accept `HubResponse` directly. Update all field access (`response.text` → `response.result.text`, etc.).

Recommended: **Option A** for M1 (minimal risk, tests stay green). Option B deferred to M10.

Touch point: EDIT `poc/k1_poc/llm/validator.py` — `validate()` method, `_attempt_fix()` method
Depends on: E1.1.1 (k1.model_hub.types), E1.5.1 (callers pass HubResponse)

### Epic E1.7 — Unit Tests for New K1 Model Hub Types + Ports

> Validate that all new K1 types serialize/deserialize correctly, ports are runtime-checkable,
> and the bridge adapter faithfully translates between POC and K1 types.

**Issue E1.7.1** — Create `tests/poc/test_model_hub_types.py`

Tests for `k1/model_hub/types.py`:

- All CapabilityType enum values match mmd table (15 capabilities)
- HubRequest construction with each payload type
- RequestConstraints defaults match mmd (timeout per priority tier)
- HubResponse + ResponseMetadata round-trip
- HubChunk for each chunk_type
- Message / ToolDefinition / ToolCallResult immutability (frozen)

Touch point: NEW file `tests/poc/test_model_hub_types.py` (~60 tests)

**Issue E1.7.2** — Create `tests/poc/test_model_hub_ports.py`

Tests for `k1/model_hub/ports.py`:

- IModelHubPort is runtime_checkable
- All 7 ports are Protocols with correct method signatures
- TestProviderPlugin satisfies IProviderPlugin

Touch point: NEW file `tests/poc/test_model_hub_ports.py` (~20 tests)

**Issue E1.7.3** — Create `tests/poc/test_model_hub_bridge.py`

Tests for `poc/k1_poc/llm/model_hub_bridge.py`:

- ModelHubPOCBridge satisfies IModelHubPort (isinstance check)
- CHAT capability: HubRequest → ConciergeModelRequest → ConciergeModelResponse → HubResponse round-trip
- TOOL_CALL capability: tools + tool_choice translate correctly
- STRUCTURED capability: response_schema → json_output mapping
- REASON capability: thinking level mapping
- Streaming: stream_execute() yields HubChunk from StreamChunk
- Token usage: prompt_tokens + completion_tokens in ResponseMetadata
- discover_capabilities() returns correct set
- TestModelHubBridge scripted response pass-through

Touch point: NEW file `tests/poc/test_model_hub_bridge.py` (~40 tests)

### Epic E1.8 — Integration Tests: Full Suite Green

> Final gate: all 3,261 existing tests + new tests pass. Zero regressions from the type migration.

**Issue E1.8.1** — Run full external test suite (3,054 tests)

- Command: `python -m pytest tests/poc/ --tb=short -q`
- Gate: ALL pass. Any failure means E1.5 translation broke something — fix before proceeding.
- Focus areas: test files that exercise the react loop (e.g. `test_m08_e85_wiring.py` with 99 tests, `test_m15_experience_layer.py` with 171 tests)

**Issue E1.8.2** — Run full internal harness (207 tests)

- Command: `python -m pytest poc/k1_poc/testing/harness/ --tb=short -q`
- Gate: ALL pass.

**Issue E1.8.3** — Git tag `m1-imodelport-complete`

- Tag commit after all tests green
- Ensures we can diff M1 changes vs M0 baseline

---

## M2 — ICapabilityPort (Bridge POC Tools → K1 Fabric)

> K1 Fabric is **FULLY IMPLEMENTED** — 183 Python files, all 6 ports, 9-step execution pipeline,
> 6 provider types (MCP, WASM, Bridge, Agent, Workflow, Concierge), retrieval engine, circuit
> breakers, output validation, policy engine, and test adapters. See `k1/fabric/fabric.mmd`.
>
> This milestone creates a bridge from the POC's 4 capability callbacks (`invoke_fn`,
> `capability_fn`, `fabric_fn`, `workflow_fn`) to K1 Fabric's public API surface
> (`CapabilityFabric.execute()`, `FabricRetrieval.discover_capabilities()`, Agent Factory,
> Workflow Provider). After M5 (Big Copy), the bridge becomes a direct injection of the
> real `Fabric` instance.

**K1 Fabric status**: Fully implemented. Key files: `k1/fabric/types.py` (~1600 lines, all types), `k1/fabric/fabric.py` (~1400 lines, CapabilityFabric + FabricRetrieval + Fabric container), `k1/fabric/factory.py` (20-step factory with 3 construction modes), `k1/fabric/ports/` (6 port Protocols), `k1/fabric/providers/` (7 providers), `k1/fabric/adapters/` (13 adapters)
**POC fabric layer**: 4 files in `poc/k1_poc/fabric/` — `capability_registry.py` (discovery + invocation), `demo_capabilities.py` (7 mock), `family_capabilities.py` (31 mock), `web_capabilities.py` (2 live)
**POC callers**: `ToolContext` in `tools/implementations.py` — 4 optional callbacks: `capability_fn`, `invoke_fn`, `fabric_fn`, `workflow_fn`
**POC wiring**: `kernel/bootstrap.py` lines 827-842 (`_capability_discover`, `_capability_invoke`) + line 847 (`_FabricGatewayAdapter` for Orchestrator)

### Mapping: POC Fabric → K1 Fabric (K1 is production, POC must match it)

| POC Pattern | POC Location | K1 Fabric Equivalent | K1 Location |
|---|---|---|---|
| `CapabilityRegistry.invoke(name, params, session_id)` → dict | `poc/k1_poc/fabric/capability_registry.py` | `CapabilityFabric.execute(CapabilityRequest) -> CapabilityResult` | `k1/fabric/fabric.py` L309 |
| `CapabilityRegistry.discover(intent, domain, constraints)` → dict | `poc/k1_poc/fabric/capability_registry.py` | `FabricRetrieval.discover_capabilities(domain, intent, safety_band, session_context, top_k) -> RetrievalResult` | `k1/fabric/fabric.py` L1110 |
| Handler result dict `{success, data, artifact_type, duration_ms}` | POC mock handlers | `CapabilityResult` (frozen dataclass, 13 fields, factory methods) | `k1/fabric/types.py` L306 |
| Capability definition dict `{name, description, required_inputs, ...}` | POC capability dicts | `CapabilityContract` (frozen dataclass, 24+ fields, lifecycle metadata) | `k1/fabric/types.py` |
| POC `CapabilityRequest(name, params, session_id, trace_id)` — 4 fields | `poc/k1_poc/orchestrator/types.py` L123 | K1 `CapabilityRequest` — 16 fields: `request_id, capability_name, params, tier, wfq_priority, safety_band, timeout_ms, trace_id, session_id, plan_id, step_id, caller, caller_id, prompt_template, context_override, retry_count` | `k1/fabric/types.py` L118 |
| POC `CapabilityResult(success, data, error, capability_name, duration_ms)` — 5 fields | `poc/k1_poc/orchestrator/types.py` L148 | K1 `CapabilityResult` — 13 fields: `request_id, trace_id, success, data, error: ErrorInfo, provider_id, duration_ms, retrieval_time_ms, resolution_time_ms, execution_time_ms` + factory methods | `k1/fabric/types.py` L306 |
| `ToolContext.invoke_fn(name, params, session_id)` — untyped callable | `tools/implementations.py` L94 | Typed: `CapabilityFabric.execute(CapabilityRequest) -> CapabilityResult` | `k1/fabric/fabric.py` |
| `ToolContext.capability_fn(intent, domain, constraints)` — untyped callable | `tools/implementations.py` L93 | Typed: `FabricRetrieval.discover_capabilities(...)  -> RetrievalResult` | `k1/fabric/fabric.py` |
| `ToolContext.fabric_fn(agent_type, task, ...)` — untyped callable | `tools/implementations.py` L95 | `AgentProvider` via `CapabilityFabric.execute()` with `agent.*` capability name | `k1/fabric/providers/agent_provider.py` |
| `ToolContext.workflow_fn(workflow_id, params, timeout)` — untyped callable | `tools/implementations.py` L96 | `WorkflowProvider` via `CapabilityFabric.execute()` with `workflow.*` capability name | `k1/fabric/providers/workflow_provider.py` |
| `IFabricGatewayPort.execute/execute_batch` (Orchestrator port) | `poc/k1_poc/orchestrator/ports.py` L48 | Direct injection of `CapabilityFabric` or `Fabric` container (K1 Fabric IS the production gateway) | `k1/fabric/fabric.py` |
| Fuzzy word-overlap discovery | POC `capability_registry.py` | FAISS semantic similarity (5-stage retrieval pipeline: EmbeddingIndex → HardFilter → SoftRanker → TopKSelector) | `k1/fabric/retrieval/` |

### Key Structural Gap

The POC conflates **discovery** and **execution** into one `CapabilityRegistry` class with `discover()` + `invoke()`. K1 separates them into two distinct APIs:

- `FabricRetrieval` (Role 1 — discovery, ranking, read-only)
- `CapabilityFabric` (Role 2 — 9-step execution pipeline with policy, circuit breaking, output validation)

The POC also uses 4 separate untyped callbacks (`invoke_fn`, `capability_fn`, `fabric_fn`, `workflow_fn`) on `ToolContext`. In K1, ALL of these route through a single `CapabilityFabric.execute()` call — the capability name prefix (`tool.*`, `agent.*`, `workflow.*`) determines which provider handles it.

### Epic E2.1 — Create IFabricPort Protocol for POC

> Define a typed port protocol that the POC tools will call instead of untyped callbacks.
> This port matches K1 Fabric's public API surface so the swap at M6 is trivial.

**Issue E2.1.1** — Create `poc/k1_poc/fabric/ports.py` with `IFabricPort` Protocol

Using K1 Fabric's actual `Fabric` class API (from `k1/fabric/fabric.py` L1257-1340) as the contract:

```python
@runtime_checkable
class IFabricPort(Protocol):
    async def execute(self, request: CapabilityRequest) -> CapabilityResult: ...
    async def execute_batch(self, requests: list[CapabilityRequest], strategy: str = "PARALLEL") -> list[CapabilityResult]: ...
    async def discover_capabilities(self, domain: list[str] | None = None, intent: str = "", safety_band: str = "GREEN", session_context: dict | None = None, top_k: int = 10) -> RetrievalResult: ...
    async def find_relevant_prompts(self, intent: str = "", domain: list[str] | None = None, safety_band: str = "GREEN", top_k: int = 10) -> RetrievalResult: ...
```

Types used: Import `CapabilityRequest`, `CapabilityResult`, `RetrievalResult` from `k1.fabric.types`
Note: This protocol intentionally uses K1 types — after M5 the real `Fabric` instance satisfies it natively.

Touch point: NEW file `poc/k1_poc/fabric/ports.py` (~40 lines)
Depends on: `k1/fabric/types.py` exists (it does — fully implemented)

### Epic E2.2 — Create POC Fabric Bridge Adapter

> Implements `IFabricPort` but internally delegates to the existing `CapabilityRegistry`.
> Translates between K1 types and POC dict-based patterns. All 40 existing POC capabilities
> remain accessible through the bridge.

**Issue E2.2.1** — Create `poc/k1_poc/fabric/fabric_bridge.py` — FabricPOCBridge

Class: `FabricPOCBridge` implements `IFabricPort`

Constructor: `__init__(self, registry: CapabilityRegistry)`

Translation methods (private):

- `_to_k1_request(name: str, params: dict, session_id: str, trace_id: str) -> CapabilityRequest`:
  - Maps POC flat args to K1 `CapabilityRequest` (16 fields)
  - Sets defaults: `tier="MEDIUM"`, `wfq_priority="INTERACTIVE"`, `safety_band="GREEN"`, `timeout_ms=30000`, `caller="concierge"`, `caller_id="concierge.back"`
  - Generates `request_id` via uuid4
  - Passes `name` → `capability_name`, `params` → `params`, `session_id` → `session_id`, `trace_id` → `trace_id`

- `_to_k1_result(poc_result: dict, request_id: str, trace_id: str, duration_ms: int) -> CapabilityResult`:
  - `poc_result["success"]` → `CapabilityResult.success`
  - `poc_result["data"]` or `poc_result` → `CapabilityResult.data`
  - `poc_result.get("error", "")` → `CapabilityResult.error` (as `ErrorInfo` if present)
  - `duration_ms` → `CapabilityResult.duration_ms` + `execution_time_ms`
  - Uses `CapabilityResult.success_result()` / `.failure_result()` factory methods

- `_to_k1_retrieval(poc_result: dict) -> RetrievalResult`:
  - `poc_result["capabilities"]` list of dicts → `RetrievalResult` with `ScoredCapability` items
  - POC capability dict `{name, description, domain, ...}` → `ScoredCapability` fields

Public methods (IFabricPort):

- `execute(CapabilityRequest) -> CapabilityResult`:
  - Extract `capability_name` + `params` + `session_id` from request
  - Call `registry.invoke(name, params, session_id)` (existing POC)
  - Wrap result with `_to_k1_result()`
- `execute_batch(requests, strategy) -> list[CapabilityResult]`:
  - Sequential: `[await self.execute(r) for r in requests]` (POC doesn't support true parallel)
- `discover_capabilities(domain, intent, safety_band, session_context, top_k) -> RetrievalResult`:
  - Call `registry.discover(intent, domain, constraints)` (existing POC)
  - Wrap result with `_to_k1_retrieval()`
- `find_relevant_prompts(...)`:
  - Returns empty `RetrievalResult` (POC has no prompt registry)

Touch point: NEW file `poc/k1_poc/fabric/fabric_bridge.py` (~180 lines)
Depends on: E2.1.1, existing `capability_registry.py`, `k1.fabric.types` (CapabilityRequest, CapabilityResult, RetrievalResult)

### Epic E2.3 — Migrate ToolContext from Untyped Callbacks to IFabricPort

> Replace the 4 untyped callbacks (`invoke_fn`, `capability_fn`, `fabric_fn`, `workflow_fn`)
> on `ToolContext` with a single typed `fabric_port: IFabricPort`. All 4 tool functions
> (`execute_invoke_capability`, `execute_discover_capabilities`, `execute_spawn_via_fabric`,
> `execute_execute_workflow`) call the port instead of raw callbacks.

**Issue E2.3.1** — Add `fabric_port: IFabricPort | None` to `ToolContext`

Changes to `poc/k1_poc/tools/implementations.py`:

- Import: add `from poc.k1_poc.fabric.ports import IFabricPort` and `from k1.fabric.types import CapabilityRequest, CapabilityResult`
- `ToolContext` dataclass (line 55): add field `fabric_port: IFabricPort | None = None`
- Keep `invoke_fn`, `capability_fn`, `fabric_fn`, `workflow_fn` for backward compatibility (deprecated, still checked as fallback)

Touch point: EDIT `poc/k1_poc/tools/implementations.py` — import (top), `ToolContext` class (line 55, add 1 field)

**Issue E2.3.2** — Migrate `execute_invoke_capability()` to use `fabric_port`

Changes to `poc/k1_poc/tools/implementations.py` line 1099:

- First check: `if ctx.fabric_port is not None:` → build `CapabilityRequest(capability_name=capability_name, params=params, session_id=session_id or "", trace_id=ctx.trace_id or "", caller="concierge", caller_id="concierge.back")` → `result = await ctx.fabric_port.execute(request)` → convert `CapabilityResult` to `ToolResult`
- Fallback: existing `ctx.invoke_fn` path (for backward compat during transition)
- HITL checks (L2 defense-in-depth) remain BEFORE the port call — no change to that block

Touch point: EDIT `poc/k1_poc/tools/implementations.py` — `execute_invoke_capability()` (lines 1099-1220), add K1-type path before existing invoke_fn fallback

**Issue E2.3.3** — Migrate `execute_discover_capabilities()` to use `fabric_port`

Changes to `poc/k1_poc/tools/implementations.py` line 999:

- First check: `if ctx.fabric_port is not None:` → `result = await ctx.fabric_port.discover_capabilities(intent=intent, domain=[domain] if domain else None, top_k=10)` → convert `RetrievalResult` to `ToolResult` dict with `{capabilities: [...], count: N}`
- Fallback: existing `ctx.capability_fn` path
- Cache logic stays — key remains `(intent, domain)`, value is `ToolResult`

Touch point: EDIT `poc/k1_poc/tools/implementations.py` — `execute_discover_capabilities()` (lines 999-1097), add K1-type path

**Issue E2.3.4** — Migrate `execute_spawn_via_fabric()` to use `fabric_port`

Changes to `poc/k1_poc/tools/implementations.py` line 1321:

- First check: `if ctx.fabric_port is not None:` → build `CapabilityRequest(capability_name=f"agent.{agent_type}", params={"task": task, "constraints": constraints, "capabilities_needed": capabilities_needed}, caller="concierge")` → `result = await ctx.fabric_port.execute(request)` → convert to `ToolResult`
- Fallback: existing `ctx.fabric_fn` path

Touch point: EDIT `poc/k1_poc/tools/implementations.py` — `execute_spawn_via_fabric()` (lines 1321-1365), add K1-type path

**Issue E2.3.5** — Migrate `execute_execute_workflow()` to use `fabric_port`

Changes to `poc/k1_poc/tools/implementations.py` line 1368:

- First check: `if ctx.fabric_port is not None:` → build `CapabilityRequest(capability_name=f"workflow.{workflow_id}", params=params, timeout_ms=timeout_ms, caller="concierge")` → `result = await ctx.fabric_port.execute(request)` → convert to `ToolResult`
- Fallback: existing `ctx.workflow_fn` path

Touch point: EDIT `poc/k1_poc/tools/implementations.py` — `execute_execute_workflow()` (lines 1368-1410), add K1-type path

### Epic E2.4 — Update Bootstrap Wiring

> Replace the 4 lambda callbacks with a single `FabricPOCBridge` instance wired to `ToolContext.fabric_port`.

**Issue E2.4.1** — Wire `FabricPOCBridge` into `kernel/bootstrap.py`

Changes to `poc/k1_poc/kernel/bootstrap.py`:

- Import: add `from poc.k1_poc.fabric.fabric_bridge import FabricPOCBridge`
- After `capability_registry = _create_capability_registry()` (line 128):
  - Add: `fabric_bridge = FabricPOCBridge(capability_registry)`
- `ToolContext` construction (lines ~190-191 where capability_fn/invoke_fn are set):
  - Add: `fabric_port=fabric_bridge`
  - Keep `capability_fn` and `invoke_fn` for backward compat (tests that don't use bridge yet)
- Remove: nothing yet (backward compat). Deprecation happens at M10.

Touch point: EDIT `poc/k1_poc/kernel/bootstrap.py` — imports, line 128, ToolContext construction (~3 sites)

**Issue E2.4.2** — Update `_FabricGatewayAdapter` (Orchestrator port) to use K1 types

Changes to `poc/k1_poc/kernel/bootstrap.py` line 847:

- `_FabricGatewayAdapter.__init__`: accept `FabricPOCBridge` instead of raw `CapabilityRegistry`
- `execute()`: build K1 `CapabilityRequest` from POC `orchestrator.types.CapabilityRequest`, call `bridge.execute()`, convert K1 `CapabilityResult` back to POC `orchestrator.types.CapabilityResult`
- `execute_batch()`: same pattern, sequential
- ALTERNATIVE: Change `IFabricGatewayPort` (in `orchestrator/ports.py`) to use K1 types directly. This is cleaner but touches more test files — decide during implementation.

Touch point: EDIT `poc/k1_poc/kernel/bootstrap.py` — `_FabricGatewayAdapter` class (lines 847-870)

### Epic E2.5 — Migrate POC Orchestrator Types to K1 Fabric Types

> The POC has its own `CapabilityRequest` and `CapabilityResult` in `orchestrator/types.py`.
> After M2, all callers should use K1 `k1.fabric.types.CapabilityRequest/CapabilityResult`.
> The POC-local types become thin aliases or are removed.

**Issue E2.5.1** — Assess POC `orchestrator/types.py` usage and decide strategy

Two options:

- **Option A** (keep POC types, add translation layer): `_FabricGatewayAdapter` translates between POC Orchestrator types and K1 Fabric types. Tests keep using POC types. Minimal diff.
- **Option B** (replace POC types with K1 types): Change `IFabricGatewayPort` and `OrchestratorStub` to import from `k1.fabric.types`. Larger diff but cleaner long-term.

Recommended: **Option A** for M2 (translation in adapter, tests stay green). Option B deferred to M8 (Orchestrator Wiring).

Touch point: DECISION doc only for M2; actual migration in M8
Depends on: E2.4.2

### Epic E2.6 — Unit Tests for Fabric Bridge + Port

> Validate that the bridge correctly translates between POC dict patterns and K1 typed patterns,
> and that all 40 existing capabilities are accessible through the new port.

**Issue E2.6.1** — Create `tests/poc/test_fabric_port.py`

Tests for `poc/k1_poc/fabric/ports.py`:

- `IFabricPort` is `runtime_checkable`
- `FabricPOCBridge` satisfies `IFabricPort` (isinstance check)
- K1 `Fabric` class (if imported) would satisfy `IFabricPort` — validate signature match

Touch point: NEW file `tests/poc/test_fabric_port.py` (~10 tests)

**Issue E2.6.2** — Create `tests/poc/test_fabric_bridge.py`

Tests for `poc/k1_poc/fabric/fabric_bridge.py`:

- `execute()` with each of the 40 POC capabilities:
  - Pass K1 `CapabilityRequest` → get K1 `CapabilityResult` back
  - Verify `success`, `data`, `duration_ms` fields translate correctly
  - Verify `error` → `ErrorInfo` mapping for failed capabilities
  - Verify `request_id` and `trace_id` propagation
- `discover_capabilities()`:
  - Intent "send a message" returns messaging capabilities
  - Domain filter works
  - Result is `RetrievalResult` with `ScoredCapability` items
  - Empty intent returns error
- `execute_batch()` sequential execution
- `find_relevant_prompts()` returns empty (POC has no prompt registry)
- Factory method coverage: `CapabilityResult.success_result()`, `.failure_result()`

Touch point: NEW file `tests/poc/test_fabric_bridge.py` (~50 tests)

**Issue E2.6.3** — Create `tests/poc/test_tool_fabric_port_wiring.py`

Tests for migrated tool implementations:

- `execute_invoke_capability` with `fabric_port` set: builds correct `CapabilityRequest`, returns correct `ToolResult`
- `execute_discover_capabilities` with `fabric_port` set: calls `discover_capabilities()`, returns correct `ToolResult`
- `execute_spawn_via_fabric` with `fabric_port` set: builds `agent.*` capability name
- `execute_execute_workflow` with `fabric_port` set: builds `workflow.*` capability name
- Backward compat: when `fabric_port=None`, falls through to old `invoke_fn`/`capability_fn`
- HITL blocking still works with `fabric_port` path

Touch point: NEW file `tests/poc/test_tool_fabric_port_wiring.py` (~35 tests)

### Epic E2.7 — Integration Tests: Full Suite Green

> Final gate: all existing tests + new tests pass. Zero regressions from the capability port migration.

**Issue E2.7.1** — Run full external test suite (3,054+ tests)

- Command: `python -m pytest tests/poc/ --tb=short -q`
- Gate: ALL pass. Focus areas: tool execution tests, orchestrator tests, capability tests
- Any failure means E2.3/E2.4 translation broke something — fix before proceeding.

**Issue E2.7.2** — Run full internal harness (207+ tests)

- Command: `python -m pytest poc/k1_poc/testing/harness/ --tb=short -q`
- Gate: ALL pass.

**Issue E2.7.3** — Git tag `m2-icapabilityport-complete`

- Tag commit after all tests green
- Ensures we can diff M2 changes vs M1 baseline

---

## M3 — Port: IBusPort

> Normalize bus type hints and factory usage to code against `k1/bus/ports/` protocols exclusively.

**Boundary**: `poc/k1_poc/bus/setup.py` → `BusFactory` + concrete `LocalBus` / `LocalMailboxRouter` type hints
**Callers**: `kernel/bootstrap.py`, `main.py`, `fsm/controller.py`, `actors/*.py`, `tools/dispatcher.py`, `demo/coordinator.py`, `testing/fixtures.py`, `testing/harness/engine.py`
**Port protocols (K1 — already exist)**: `k1/bus/ports/bus.py` → `IBus` (3 methods: publish, subscribe, unsubscribe), `k1/bus/ports/mailbox.py` → `IMailbox` (2 methods), `IMailboxRouter` (4 methods)
**Status**: K1 bus is FULLY IMPLEMENTED (28+ source files, 30+ tests). POC already imports `k1.bus.*` directly. Work is type-hint alignment + middleware wiring + contract tests.

### Key finding

The POC **already uses** the K1 bus as its event backbone — `create_poc_bus()` calls `BusFactory.create_local_ordered()`, all builders produce real `Envelope` instances, and the FSM + actors call `bus.publish()` / `bus.subscribe()` which match `IBus` exactly. The only gap is that **setup.py returns concrete types** (`LocalBus`, `LocalMailboxRouter`, `LocalMailbox`) instead of the protocol abstractions (`IBus`, `IMailboxRouter`, `IMailbox`), and the POC runs with **zero middleware** (no tracing, no topic validation, no metrics).

### K1 Bus Protocol Surface (from `k1/bus/ports/`)

| Protocol | Methods | File |
|---|---|---|
| `IBus` | `publish(Envelope) → None`, `subscribe(pattern, BusHandler) → SubscriptionHandle`, `unsubscribe(SubscriptionHandle) → bool` | `k1/bus/ports/bus.py` |
| `IMailbox` | `receive(timeout_ms=0) → Optional[Envelope]`, `pending() → int` | `k1/bus/ports/mailbox.py` |
| `IMailboxRouter` | `deliver(actor_id, Envelope) → None`, `register(actor_id, MailboxConfig?) → IMailbox`, `unregister(actor_id) → bool`, `registered_actors() → list[str]` | `k1/bus/ports/mailbox.py` |

### POC → K1 Bus Type Mapping

| POC concrete type | K1 protocol | Used in | Change needed |
|---|---|---|---|
| `LocalBus` (type hint) | `IBus` | `setup.py` return type, `main.py` | Change return type `→ IBus` |
| `LocalMailboxRouter` (type hint) | `IMailboxRouter` | `setup.py` return type, `main.py` | Change return type `→ IMailboxRouter` |
| `LocalMailbox` (type hint) | `IMailbox` | `setup.py` return type, `main.py` | Change return type `→ IMailbox` |
| `SessionBusAdapter(bus: LocalBus)` | Keep — adapter stays concrete | `setup.py` param type | Change param `bus: IBus` |
| `bus: Any` | `bus: IBus` | `bootstrap.py` L85, `dispatcher.py` L423/L468 | Replace `Any` with `IBus` |
| `router: Any` | `router: IMailboxRouter` | `bootstrap.py` L86 | Replace `Any` with `IMailboxRouter` |
| `bus: Any` in `_DeltaEmitAdapter` | `bus: IBus` | `bootstrap.py` L1001 | Replace `Any` with `IBus` |

### POC Files Importing `k1.bus.*` (complete inventory)

| File | Imports | Role |
|---|---|---|
| `bus/setup.py` | `SessionBusAdapter`, `BusFactory`, `LocalBus`, `LocalMailbox`, `LocalMailboxRouter`, `MailboxConfig` | Factory wrappers — **PRIMARY EDIT TARGET** |
| `bus/builders.py` | `Envelope`, `PayloadFormat`, `Priority` | 47 envelope builder functions — **NO CHANGE** (uses value types only) |
| `bus/topics.py` | None from k1.bus | 47 topic constants — **NO CHANGE** |
| `bus/deserialize.py` | None from k1.bus | Payload parser — **NO CHANGE** |
| `actors/front.py` | `Envelope`, `IBus` | Front actor — already uses `IBus` protocol ✅ |
| `actors/back.py` | `Envelope`, `IBus` | Back actor — already uses `IBus` protocol ✅ |
| `actors/shared.py` | `Envelope` | Shared utilities — **NO CHANGE** |
| `fsm/controller.py` | `Envelope`, `PayloadFormat`, `Priority`, `IBus`, `IMailboxRouter` | FSM — already uses protocols ✅ |
| `fsm/dead_letter_consumer.py` | `Envelope`, `IBus` | Dead letter consumer — already uses `IBus` ✅ |
| `fsm/front_lock.py` | `Envelope` | Front lock — **NO CHANGE** |
| `fsm/turn_state.py` | `Envelope` | Turn tracking — **NO CHANGE** |
| `kernel/bootstrap.py` | `Envelope`, `PayloadFormat`, `Priority` (lazy imports in closures) | Boot wiring — **EDIT: type hints from `Any` → protocols** |
| `main.py` | `BusFactory` (only for `--unordered` fallback) | POC entrypoint — **EDIT: type hints + return types** |
| `tools/dispatcher.py` | None directly (uses `bus: Any`) | Tool dispatch — **EDIT: `Any` → `IBus`** |
| `demo/iot_stubs.py` | `IBus` | IoT stubs — already uses `IBus` ✅ |
| `demo/output_channel.py` | `Envelope`, `IBus` | Output channel — already uses `IBus` ✅ |
| `demo/spinner.py` | `Envelope`, `IBus` | Spinner — already uses `IBus` ✅ |
| `demo/web/app.py` | `Envelope` (lazy) | Web app — **NO CHANGE** |
| `testing/harness/engine.py` | `Envelope` | Test engine — **NO CHANGE** (concrete types OK for test infra) |

### Epics

#### E3.1 — Widen `setup.py` Return Types to Protocols

Replace concrete type hints in `poc/k1_poc/bus/setup.py` with K1 protocol types so all downstream code receives protocol-typed objects.

**E3.1.1** — Change `create_poc_bus()` return type from `LocalBus` to `IBus`

- File: `poc/k1_poc/bus/setup.py` L54
- Current: `def create_poc_bus(*, capture: bool = False) -> LocalBus:`
- Target: `def create_poc_bus(*, capture: bool = False) -> IBus:`
- Add import: `from k1.bus.ports.bus import IBus`
- Internal implementation still calls `BusFactory.create_local_ordered()` — unchanged
- NOTE: `create_poc_session_adapter(bus: LocalBus)` param type also widens to `IBus` (L88)

**E3.1.2** — Change `create_poc_router()` return type from `LocalMailboxRouter` to `IMailboxRouter`

- File: `poc/k1_poc/bus/setup.py` L76
- Current: `def create_poc_router() -> LocalMailboxRouter:`
- Target: `def create_poc_router() -> IMailboxRouter:`
- Add import: `from k1.bus.ports.mailbox import IMailboxRouter`

**E3.1.3** — Change `register_poc_actors()` return type from `tuple[LocalMailbox, LocalMailbox]` to `tuple[IMailbox, IMailbox]`

- File: `poc/k1_poc/bus/setup.py` L107-108
- Current: `def register_poc_actors(router: LocalMailboxRouter, ...) -> tuple[LocalMailbox, LocalMailbox]:`
- Target: `def register_poc_actors(router: IMailboxRouter, ...) -> tuple[IMailbox, IMailbox]:`
- Add import: `from k1.bus.ports.mailbox import IMailbox`

**E3.1.4** — Remove unused concrete imports from `setup.py`

- After E3.1.1-3, `LocalBus`, `LocalMailbox`, `LocalMailboxRouter` are only needed inside function bodies (factory returns them)
- Move these imports inside function bodies or keep at module level with `# noqa: used by factory internals` comment
- `MailboxConfig` stays — it's a value type used in `register_poc_actors`

---

#### E3.2 — Update `__init__.py` Re-exports

Ensure `poc/k1_poc/bus/__init__.py` re-exports the K1 protocols alongside the POC setup functions.

**E3.2.1** — Add protocol re-exports to `poc/k1_poc/bus/__init__.py`

- Add: `from k1.bus.ports.bus import IBus, BusHandler, SubscriptionHandle`
- Add: `from k1.bus.ports.mailbox import IMailbox, IMailboxRouter, MailboxConfig`
- Add to `__all__`: `"IBus"`, `"IMailbox"`, `"IMailboxRouter"`, `"BusHandler"`, `"SubscriptionHandle"`, `"MailboxConfig"`
- This lets other POC modules import bus protocols from `poc.k1_poc.bus` instead of reaching into `k1.bus.ports.*` directly

---

#### E3.3 — Widen Type Hints in `kernel/bootstrap.py` and `main.py`

Replace `Any` type hints for bus/router/mailbox with protocol types.

**E3.3.1** — Update `KernelConfig` type hints in `bootstrap.py`

- File: `poc/k1_poc/kernel/bootstrap.py`
- `bus: Any` (L85) → `bus: IBus`
- `router: Any` (L86) → `router: IMailboxRouter`
- `front_mailbox: Any` (L88) → `front_mailbox: IMailbox`
- `back_mailbox: Any` (L89) → `back_mailbox: IMailbox`
- Add imports: `from k1.bus.ports.bus import IBus` and `from k1.bus.ports.mailbox import IMailbox, IMailboxRouter`
- NOTE: The `KernelRuntime` class also has `bus`, `router`, `front_mailbox`, `back_mailbox` fields — these are assigned from `KernelConfig` fields and should also be typed

**E3.3.2** — Update `_DeltaEmitAdapter` type hint in `bootstrap.py`

- File: `poc/k1_poc/kernel/bootstrap.py` L1001
- `bus: Any = None` → `bus: IBus | None = None`
- `self._bus` typed accordingly

**E3.3.3** — Update `_build_delta_applicator` type hint in `bootstrap.py`

- File: `poc/k1_poc/kernel/bootstrap.py` L899
- `def _build_delta_applicator(session_state: Any, bus: Any)` → `bus: IBus`

**E3.3.4** — Update `main.py` type hints

- File: `poc/k1_poc/main.py`
- Variables `bus`, `router`, `front_mailbox`, `back_mailbox` (L60-67) are currently untyped — add type annotations using protocols
- Return type of `boot()` currently returns `dict` — consider adding typed `BootResult` dataclass or keep dict

---

#### E3.4 — Widen Type Hints in `tools/dispatcher.py`

**E3.4.1** — Replace `bus: Any | None = None` with `bus: IBus | None = None`

- File: `poc/k1_poc/tools/dispatcher.py` L423, L468 (in `create_front_dispatcher`, `create_back_dispatcher`)
- Also check `ToolDispatcher.__init__` for `bus` param type
- Add import: `from k1.bus.ports.bus import IBus`

---

#### E3.5 — Wire K1 Middleware (Optional but Recommended)

The POC runs with zero middleware — no tracing, no topic validation, no metrics. K1 provides three ready-to-use middleware classes. Wiring them aligns POC with K1 production expectations.

**E3.5.1** — Wire `TopicValidationMiddleware` in `create_poc_bus()`

- File: `poc/k1_poc/bus/setup.py`
- Create `TopicRegistry`, register all 47 `ALL_TOPICS`, build `TopicValidationMiddleware(registry)`
- Pass as `middleware=MiddlewareChain([TopicValidationMiddleware(registry)])` to `BusFactory.create_local_ordered()`
- Import: `from k1.bus.middleware import MiddlewareChain` + `from k1.bus.middleware.topic_validation import TopicRegistry, TopicValidationMiddleware`
- NOTE: Topic validation is SOFT (warns but never drops) — safe to add without breaking tests

**E3.5.2** — Wire `TracingMiddleware` (behind config flag)

- Add `bus.tracing_enabled: bool = false` to `poc/k1_poc/config/defaults.yaml`
- Conditionally prepend `TracingMiddleware(enabled=config.bus.tracing_enabled)` to middleware chain
- Import: `from k1.bus.middleware.tracing import TracingMiddleware`

**E3.5.3** — Wire `MetricsMiddleware` (behind config flag)

- Add `bus.metrics_enabled: bool = false` to `poc/k1_poc/config/defaults.yaml`
- Conditionally append `MetricsMiddleware(enabled=config.bus.metrics_enabled)` to middleware chain
- Import: `from k1.bus.middleware.metrics import MetricsMiddleware`

---

#### E3.6 — Contract Tests

Verify protocol compliance and ensure factory-produced instances satisfy protocols at runtime.

**E3.6.1** — Protocol compliance test: `isinstance(bus, IBus)` ✅

- File: `tests/poc/bus/test_bus_port_compliance.py` (new, ~60 tests)
- Test `isinstance(create_poc_bus(), IBus)` — must pass (`IBus` is `@runtime_checkable`)
- Test `isinstance(create_poc_router(), IMailboxRouter)` — must pass
- Test `isinstance(mailbox, IMailbox)` for registered actor mailbox
- Test all 3 `IBus` methods work through protocol reference
- Test all 4 `IMailboxRouter` methods work through protocol reference
- Test all 2 `IMailbox` methods work through protocol reference

**E3.6.2** — Middleware integration test

- Test `create_poc_bus()` with topic validation middleware: publish known topic → no warning; publish unknown topic → warning logged
- Test middleware chain processes envelopes without dropping
- Test TracingMiddleware and MetricsMiddleware are no-ops when disabled

**E3.6.3** — Regression: existing bus tests still green

- Run full `tests/poc/bus/` test suite — must be 100% green
- Run full `tests/k1/bus/` test suite — must be 100% green (K1 bus unchanged)

---

#### E3.7 — Full Suite Green + Tag

**E3.7.1** — Run full test suite (3,261 tests)

- All POC tests must pass — type narrowing should be transparent
- Zero test changes expected for actors/FSM/react (they already use `IBus` / `IMailboxRouter`)

**E3.7.2** — Git tag `m3-ibusport-complete`

### Structural Gap Analysis

| Aspect | POC Current | K1 Bus Design | Gap | Resolution |
|---|---|---|---|---|
| Type hints | Mixed: actors use `IBus`/`IMailboxRouter`, but setup.py and bootstrap use concrete types or `Any` | All protocols: `IBus`, `IMailbox`, `IMailboxRouter` | **SMALL** — surface-level type annotations | E3.1 + E3.3 + E3.4 |
| Factory | `BusFactory.create_local_ordered()` | Same factory, same config | **NONE** — already aligned | — |
| Envelope | Real `Envelope` with `Priority`, `PayloadFormat.JSON` | Same `Envelope` | **NONE** — fully aligned | — |
| Topics | 47 topic constants, priority sets, subscription sets | TimingConfig has 18 prefix rules | **NONE** — topics map to timing rules | — |
| Middleware | Zero — no tracing, no validation, no metrics | 3 middleware: tracing, topic validation, metrics | **OPTIONAL** — K1 provides them, POC doesn't use | E3.5 (behind flags) |
| Builders | 47 builder functions producing typed Envelopes | K1 has no builder layer (consumers build envelopes directly) | **POC-SPECIFIC** — builders stay in concierge | — |
| TimingChain | Via factory (implicit `default_timing_config()`) | Same `TimingChain` + `TimingConfig` | **NONE** — fully aligned | — |
| Mailbox routing | `front_half` / `back_half` actors via `register_poc_actors()` | Same `IMailboxRouter.register()` API | **NONE** — fully aligned | — |
| Rust backend | `backend="python"` forced | `backend="auto"` prefers Rust | **DEFERRED** — Rust parity is separate | — |
| `SessionBusAdapter` | `SessionBusAdapter(bus: LocalBus)` wrapping concrete type | Same adapter class in `k1/bus/adapters/` | **SMALL** — widen param type | E3.1.1 |
| `FabricBusAdapter` | Not used in POC | Available in `k1/bus/adapters/` | **DEFERRED** — M6 Fabric wiring | — |

---

## M4 — Port: IStoragePort Audit

> Session State already has ports/adapters in POC. Verify contracts are clean, back-port POC improvements to K1 sessionstate, and resolve `poc.k1_poc.config` import coupling.

**Existing K1 ports**: `k1/sessionstate/ports/` — 5 ABCs + supporting types (IStoragePort, IEventPort, IWriterPort, ILifecyclePort, IK0SyncPort)
**Existing K1 adapters**: `k1/sessionstate/adapters/` — 5 adapters (DirectWriter, LocalEvents, MemoryStorage, SQLiteStorage, StandaloneLifecycle)
**Existing POC ports**: `poc/k1_poc/sessionstate/ports/` — **byte-for-byte identical** to K1 ports
**Existing POC adapters**: `poc/k1_poc/sessionstate/adapters/` — **DIVERGED** (POC is ahead by ~153 LoC across 4 files)
**Status**: Ports are perfectly aligned. Adapters need back-port. Config coupling needs resolution.

### Key Finding

Unlike M1-M3, SessionState has a **unique topology**: the code exists in BOTH `k1/sessionstate/` AND `poc/k1_poc/sessionstate/`, with the POC copy being the actively developed version. All 6 port files are byte-for-byte identical. The adapters have diverged — POC added per-turn mutation tracking, LLM section guards, config-backing, and logging upgrades. The POC currently imports its own copy (`from poc.k1_poc.sessionstate import ...`). After M5 (Big Copy), concierge will import from `k1.concierge.sessionstate` — but since K1 already has `k1.sessionstate`, we need to decide the canonical home.

### Divergence Inventory

| File | K1 Lines | POC Lines | Delta | Nature of Change |
|---|---|---|---|---|
| `ports/*` (all 6 files) | identical | identical | 0 | **NONE** — ports are clean ✅ |
| `adapters/direct_writer.py` | 487 | 628 | +141 | Per-turn mutation audit (`_turn_stats`, `_record_turn_mutation`, `snapshot_turn_stats`), LLM tool-writer section guard via `get_config().sessionstate.llm_writable_sections` |
| `adapters/local_events.py` | 303 | 307 | +4 | `logger.info()` at init |
| `adapters/sqlite_storage.py` | 520 | 524 | +4 | Config-backed: `get_config().sessionstate.storage.default_db_path` and `sla_storage_ms` replace hardcoded defaults |
| `adapters/standalone_lifecycle.py` | 602 | 602 | ~0 | `logger.debug` → `logger.info` with richer format strings |
| `adapters/memory_storage.py` | 227 | 227 | 0 | **IDENTICAL** ✅ |
| `factory.py` | 325 | 334 | +9 | Config-backed: `get_config()` for `default_db_path` and `checkpoint_interval_s` |
| `manager.py` | 1316 | 1327 | +11 | Logging only: `debug` → `info` with richer format strings |

### POC `poc.k1_poc.config` Import Sites in SessionState

These imports create a coupling to `poc.k1_poc.config` that will break at M5 (Big Copy) if not resolved:

| File | Line | Import |
|---|---|---|
| `adapters/direct_writer.py` | 243 | `from poc.k1_poc.config import get_config` |
| `adapters/sqlite_storage.py` | 55 | `from poc.k1_poc.config import get_config` |
| `factory.py` | 44 | `from poc.k1_poc.config import get_config` |
| `eviction.py` | 53 | `from poc.k1_poc.config import get_config` |
| `guard.py` | 61 | `from poc.k1_poc.config import get_config` |
| `local_cold.py` | 52 | `from poc.k1_poc.config import get_config` |
| `migration.py` | 60 | `from poc.k1_poc.config import get_config` |
| `reconstruction.py` | 47 | `from poc.k1_poc.config import get_config` |

**8 files** import `poc.k1_poc.config.get_config` — all in adapter/service-layer code, never in port definitions.

### 5-Port ABC Surface (from `k1/sessionstate/ports/` — identical in POC)

| Port ABC | Methods | Supporting Types |
|---|---|---|
| `IStoragePort` | `is_available` (prop), `storage_type` (prop), `archive(section, data, metadata) → ArchiveResult`, `restore(section, filters) → RestoreResult`, `list_archives(session_id) → List[ArchiveEntry]`, `delete(archive_id) → bool` | `ArchiveResult`, `RestoreResult`, `ArchiveEntry` |
| `IEventPort` | `is_connected` (prop), `emit(event_type, payload) → None`, `subscribe(event_type, handler) → str`, `unsubscribe(subscription_id) → bool`, `emit_batch(events) → None` (concrete default) | — |
| `IWriterPort` | `writer_id` (prop), `request_mutation(MutationRequest) → MutationResponse`, `request_batch(BatchRequest) → BatchResult`, `authorize(writer_id) → WriterAuthorization`, `get_stats() → Dict`, `reset_stats() → None` | `MutationRequest`, `MutationResponse`, `BatchRequest`, `BatchResult`, `MutationPriority` (enum), `MutationStatus` (enum), `RejectionCategory` (enum), `WriterAuthorization` |
| `ILifecyclePort` | `state` (prop), `config` (prop), `start(session_id) → StartResult`, `stop() → StopResult`, `checkpoint(trigger) → CheckpointResult`, `health_check() → HealthStatus`, `transition_to_error(error) → None` | `LifecycleState` (enum), `CheckpointTrigger` (enum), `RestoreSource` (enum), `PressureLevel` (enum), `LifecycleConfig`, `StartResult`, `StopResult`, `HealthStatus`, `CheckpointResult`, `InvalidStateError` |
| `IK0SyncPort` | `is_available` (prop), `sync_to_k0(session_id) → SyncResult`, `restore_from_k0(session_id) → RestoreFromK0Result`, `get_sync_status(session_id) → SyncStatus`, `cancel_sync(session_id) → bool` | `SyncStatus` (enum), `SyncResult`, `RestoreFromK0Result`, `NullSyncPort` (concrete no-op) |

### K1 External Consumers (Inversion — they do NOT import sessionstate)

| Module | Port Used | Pattern |
|---|---|---|
| `k1/fabric/adapters/sessionstate_reader.py` | `ISessionStateReader` (Fabric's own port) | Wraps `manager: Any` — never imports `k1.sessionstate` |
| `k1/planner/adapters/session_state_adapter.py` | `ISessionStateReader` (Fabric's port) | Same pattern — reads via Fabric's abstraction |
| `k1/memory_writer/ports/session_read_port.py` | `ISessionReadPort` (own Protocol) | Defines `snapshot(sections)`, `read_section(name)` — explicitly documents "NEVER imports from k1.sessionstate" |

**No K1 module imports `k1.sessionstate` directly.** All use their own adapter ports. This is correct hexagonal architecture.

### Canonical Home Decision

After M5, sessionstate lives at `k1/concierge/sessionstate/`. The existing `k1/sessionstate/` becomes a **re-export shim** (or is merged). K1 external consumers are unaffected because they never import from `k1.sessionstate` directly.

**Decision**: **Option A — K1 becomes re-export shim** (preferred)

- `k1/sessionstate/__init__.py` re-exports from `k1.concierge.sessionstate`
- Existing `tests/k1/sessionstate/` tests (70+ files) keep working
- Zero impact on K1 modules (they don't import k1.sessionstate anyway)
- The POC (richer) copy becomes the canonical implementation

### Existing Test Coverage

| Test Suite | File Count | Location | Status |
|---|---|---|---|
| K1 sessionstate tests | 70+ files | `tests/k1/sessionstate/` | Tests K1 copy — will need to run against POC copy after merge |
| POC session bundle test | 1 file | `tests/poc/test_m04_e43_session_bundle.py` | Tests POC-specific session bundling |
| POC internal harness | 10 files | `poc/k1_poc/testing/harness/` | Creates sessions via `SessionStateFactory.create_for_testing()` |

### Epics

#### E4.1 — Back-port POC Adapter Improvements to K1

Copy POC adapter improvements back to `k1/sessionstate/adapters/` so both copies are in sync before M5.

**E4.1.1** — Back-port `direct_writer.py` (+141 LoC)

- Source: `poc/k1_poc/sessionstate/adapters/direct_writer.py`
- Target: `k1/sessionstate/adapters/direct_writer.py`
- Changes: Per-turn mutation audit (`_turn_stats`, `_empty_turn_stats()`, `_record_turn_mutation()`, `snapshot_turn_stats()`, `mutation_stats` property), LLM tool-writer section guard
- NOTE: The `get_config()` import needs resolution (E4.3) — use `try/except` or parameter injection for now

**E4.1.2** — Back-port `local_events.py` (+4 LoC)

- Source: `poc/k1_poc/sessionstate/adapters/local_events.py`
- Target: `k1/sessionstate/adapters/local_events.py`
- Changes: `logger.info()` at init

**E4.1.3** — Back-port `sqlite_storage.py` (+4 LoC)

- Source: `poc/k1_poc/sessionstate/adapters/sqlite_storage.py`
- Target: `k1/sessionstate/adapters/sqlite_storage.py`
- Changes: Config-backed `default_db_path` and `sla_storage_ms`
- NOTE: Same `get_config()` coupling issue — resolve in E4.3

**E4.1.4** — Back-port `standalone_lifecycle.py` (logging upgrades)

- Source: `poc/k1_poc/sessionstate/adapters/standalone_lifecycle.py`
- Target: `k1/sessionstate/adapters/standalone_lifecycle.py`
- Changes: `logger.debug` → `logger.info` with richer format strings

**E4.1.5** — Back-port `factory.py` (+9 LoC)

- Source: `poc/k1_poc/sessionstate/factory.py`
- Target: `k1/sessionstate/factory.py`
- Changes: Config-backed `default_db_path` and `checkpoint_interval_s`

**E4.1.6** — Back-port `manager.py` (+11 LoC)

- Source: `poc/k1_poc/sessionstate/manager.py`
- Target: `k1/sessionstate/manager.py`
- Changes: Logging only — `debug` → `info` with richer format strings

---

#### E4.2 — Fix POC `sqlite_storage.py` Bug

**E4.2.1** — Fix duplicate `return` in `__repr__` (POC line ~598)

- File: `poc/k1_poc/sessionstate/adapters/sqlite_storage.py`
- Reported by audit: duplicate `return` statement in `__repr__` method
- Fix in POC, then back-port to K1 copy

---

#### E4.3 — Resolve `poc.k1_poc.config` Coupling

The 8 files that import `from poc.k1_poc.config import get_config` will break when moved to `k1/concierge/sessionstate/` in M5. Resolution strategy:

**E4.3.1** — Introduce config parameter injection pattern

- For `factory.py`, `sqlite_storage.py`, `direct_writer.py`: add optional config parameters to constructors/factory methods with fallback to `get_config()` when available
- Pattern: `def __init__(self, ..., config: Any | None = None): self._config = config or _try_get_config()`
- Helper: `def _try_get_config()` that wraps the import in `try/except ImportError: return _DEFAULT_CONFIG`
- This lets the code work from EITHER `poc.k1_poc` or `k1.concierge` path

**E4.3.2** — Apply same pattern to remaining 5 files

- `eviction.py`, `guard.py`, `local_cold.py`, `migration.py`, `reconstruction.py`
- All use `get_config()` for threshold values — inject via constructor or read from defaults

**E4.3.3** — Update `SessionStateFactory.create_standalone()` and `create_for_testing()` to pass config explicitly

- Factory already has `create_with_ports()` that takes injected ports — extend pattern to config
- `create_standalone(session_id, config=None)` → passes config to adapters that need it

---

#### E4.4 — Resolve FlatBuffers Import Paths

POC's generated FlatBuffers code uses `from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState import ...` — K1 uses `from k1.sessionstate.generated.flatbuffers.K1.SessionState import ...`. These section files will break at M5.

**E4.4.1** — Audit all section files for FlatBuffer import paths

- Files: `poc/k1_poc/sessionstate/sections/` — 12+ section files
- Each has 3-8 FlatBuffer imports with `poc.k1_poc.sessionstate.generated` prefix
- These become `k1.concierge.sessionstate.generated` after M5
- Decision: Let M5 handle mechanically (find-replace) OR add a re-export shim in `generated/__init__.py`

---

#### E4.5 — Verify Orchestrator-Level Abstractions

POC has TWO layers of state abstraction: sessionstate ports (5 ABCs) + orchestrator ports (`IStateReadPort`, `IDeltaEmitPort`). Verify alignment.

**E4.5.1** — Audit `IStateReadPort` → `SessionStateManager.get_section()` mapping

- File: `poc/k1_poc/orchestrator/ports.py` L76 — `IStateReadPort(Protocol)`
- This is the orchestrator's read-only view of session state
- `SessionStateManager.get_section(name)` (L621 in `manager.py`) satisfies this
- Verify structural compatibility — SessionStateManager must satisfy `IStateReadPort` without adapters

**E4.5.2** — Audit `IDeltaEmitPort` → bus/delta wiring

- File: `poc/k1_poc/orchestrator/ports.py` L110 — `IDeltaEmitPort(Protocol)`
- Used by `_DeltaEmitAdapter` in `bootstrap.py` (wraps delta_aggregator + bus)
- No direct sessionstate dependency — clean abstraction ✅

---

#### E4.6 — Contract Tests

**E4.6.1** — Verify K1 sessionstate tests pass against POC copy

- Run `tests/k1/sessionstate/test_all_ports.py` (35 tests covering all 5 port ABCs)
- Run `tests/k1/sessionstate/test_factory.py` — factory wiring tests
- Run `tests/k1/sessionstate/test_wiring_contract.py` — DI contract tests
- These currently import from `k1.sessionstate` — they test the K1 copy
- After E4.1 back-port, both copies should produce identical results

**E4.6.2** — Add port-protocol compliance tests for POC path

- File: `tests/poc/sessionstate/test_port_compliance.py` (new, ~40 tests)
- `isinstance(adapter, IStoragePort)` for all storage adapters
- `isinstance(adapter, IEventPort)` for LocalEventAdapter
- `isinstance(adapter, IWriterPort)` for DirectWriterAdapter
- `isinstance(adapter, ILifecyclePort)` for StandaloneLifecycle
- Verify `SessionStateFactory.create_with_ports()` accepts all injected ports

**E4.6.3** — Regression: POC session bundle test still green

- Run `tests/poc/test_m04_e43_session_bundle.py`

**E4.6.4** — Regression: full K1 sessionstate suite green (70+ files)

- Run full `tests/k1/sessionstate/` — all tests must pass after back-port

---

#### E4.7 — Full Suite Green + Tag

**E4.7.1** — Run full test suite (3,261 tests)

- Back-port and config-decoupling changes must not break anything
- POC tests import `poc.k1_poc.sessionstate` — must still work
- K1 tests import `k1.sessionstate` — must still work

**E4.7.2** — Git tag `m4-istorageport-audit-complete`

### Structural Gap Analysis

| Aspect | POC Current | K1 SessionState | Gap | Resolution |
|---|---|---|---|---|
| Port definitions | 5 ABCs, identical | 5 ABCs, identical | **NONE** ✅ | — |
| Adapter implementations | Ahead by ~153 LoC | Behind | **BACK-PORT** needed | E4.1 |
| Config coupling | `poc.k1_poc.config.get_config()` in 8 files | No config (hardcoded defaults) | **COUPLING** — will break at M5 | E4.3 |
| FlatBuffer imports | `poc.k1_poc.sessionstate.generated.*` | `k1.sessionstate.generated.*` | **PATH** — mechanical M5 fix | E4.4 |
| Factory DI | `create_with_ports()` accepts all 5 ABCs | Same | **NONE** ✅ | — |
| Canonical home | `poc/k1_poc/sessionstate/` (active) | `k1/sessionstate/` (stale) | **DECISION** — POC copy is canonical | Option A: K1 becomes re-export shim |
| External consumers | POC modules import POC path | K1 modules use own adapter ports | **NONE** — decoupled ✅ | — |
| Test coverage | 1 POC-specific test + 10 harness files | 70+ K1 test files | **GOOD** — K1 tests cover port contracts thoroughly | E4.6 |
| `sqlite_storage.py` bug | Duplicate `return` in `__repr__` | Not present | **BUG** — fix in POC + back-port | E4.2 |
| Orchestrator ports | `IStateReadPort`, `IDeltaEmitPort` | N/A (concierge-specific) | **CLEAN** — separate layer ✅ | E4.5 verify only |

---

## M5 — The Big Copy

> Single mechanical move: `poc/k1_poc/` → `k1/concierge/`. Rewrite all import paths. Verify all tests pass from new location.

**Source**: `poc/k1_poc/` — 277 .py files across 22 directories (+ 3 kernel/ files — decision below)
**Target**: `k1/concierge/` — currently 5 empty `__init__.py` stubs + 4 .md docs + 1 .mmd diagram
**Import rewrites**: 3,303 total (`poc.k1_poc` → `k1.concierge`) — 2,072 in source, 1,231 in tests
**External consumers**: 0 (POC is fully self-contained — no files outside `poc/` and `tests/poc/` import it)
**Test files**: 73 files in `tests/poc/` → move to `tests/k1/concierge/`

### What Copies (the organs) — 22 directories, 277 .py files

| Directory | .py Files | Description |
|---|--:|---|
| `sessionstate/` | 129 | Manager + tiers + sections + ports + adapters + 80 FlatBuffer generated files |
| `protocols/` | 20 | OPP (8 primitives), HITL, Weave, Suspension |
| `fsm/` | 19 | FSM controller + guard matrix + states + arbiter + task bridge |
| `task/` | 12 | Task model + lifecycle + topics |
| `events/` | 10 | Event type definitions + registry |
| `prompt/` | 9 | DynamicPromptBuilder + 10 prompt modes |
| `delta/` | 9 | Delta applicator + aggregation + bus adapter |
| `experience/` | 8 | 6 experience layer stubs |
| `actors/` | 7 | Front + Back handlers + shared utils |
| `llm/` | 7 | Model port (M1) + POC adapter + test adapter + validator |
| `tools/` | 7 | Dispatcher + schemas (front/back) + implementations |
| `orchestrator/` | 7 | POC simple orchestrator (becomes LOW-tier path) |
| `bus/` | 5 | Bus setup + builders + topics + deserialize (M3 port) |
| `fabric/` | 5 | Capability port (M2) + POC bridge adapter |
| `ledger/` | 5 | Idempotency ledger |
| `obs/` | 4 | Observability |
| `kernel/` | 3 | **COPIES** — bootstrap.py (wiring), runner.py (CLI), **init**.py |
| `react/` | 3 | ReAct loop engine + history |
| `config/` | 2 | defaults.yaml loader + **init**.py |
| `compression/` | 2 | Episodic compression |
| `identity/` | 2 | Persona engine |
| `scheduler/` | 2 | Proactive scheduler |

**Non-Python files that copy (24 files)**:

- `config/defaults.yaml` — 59 tunable parameters
- `sessionstate/alerts.yaml` — alert config
- `sessionstate/sessionstate.mmd` + `sessionstate_internal.mmd` — architecture diagrams
- `sessionstate/README.md` + `sessionstate/docs/` (8 .md files) — port documentation
- `docs/` (11 .md files) — design docs, milestones, wiring plans → `k1/concierge/docs/`

### What Stays Behind (not production) — 33 .py files

| Item | .py Files | Reason |
|---|--:|---|
| `demo/` | 16 | Test harness, coordinator, web app — not production |
| `testing/` | 16 | Test fixtures, harness engine — stays as POC test infra |
| `main.py` | 1 | POC entrypoint — replaced by `k1/concierge/kernel/runner.py` |

**Other files that stay**:

- `concierge_poc_architecture.mmd` → copy to `k1/concierge/docs/` as historical reference
- `demo/web/static/` (app.js, index.html, styles.css) — demo web UI

### What Moves to Tests — 73 .py files

All files in `tests/poc/` → `tests/k1/concierge/` with import path rewrite.

### Target Directory Conflicts

| Target path | Existing | Source | Resolution |
|---|---|---|---|
| `k1/concierge/__init__.py` | 0 bytes (empty) | No source file | Keep empty or add concierge package docstring |
| `k1/concierge/tools/` | Empty `__init__.py` + `README.md` | POC `tools/` (7 .py) | **Overwrite** — POC tools/ replaces empty stub |
| `k1/concierge/affective/` | Empty `__init__.py` | No POC counterpart | **Keep** — future K1 stub |
| `k1/concierge/empathy/` | Empty `__init__.py` | No POC counterpart | **Keep** — future K1 stub |
| `k1/concierge/rhythm/` | Empty `__init__.py` | No POC counterpart | **Keep** — future K1 stub |
| `k1/concierge/README.md` | 8.6 KB | No source file | **Keep** — existing K1 doc |
| `k1/concierge/concierge.md` | 605 KB | No source file | **Keep** — existing K1 design doc |
| `k1/concierge/concierge.mmd` | 93 KB | No source file | **Keep** — existing K1 diagram |
| `k1/concierge/concierge_fsm_flows.md` | 132 KB | No source file | **Keep** — existing K1 flows doc |

### Import Path Rewrite Rules

| Old pattern | New pattern | Scope |
|---|---|---|
| `from poc.k1_poc.` | `from k1.concierge.` | All source + test files |
| `import poc.k1_poc.` | `import k1.concierge.` | All source + test files |
| `poc.k1_poc.` (string refs in docstrings/comments) | `k1.concierge.` | Best-effort, non-blocking |

**Special cases**:

1. `from k1.bus.*` — **NO CHANGE** (already imports K1 bus directly)
2. `from poc.k1_poc.config import get_config` — rewrites to `from k1.concierge.config import get_config` (M4 E4.3 already decoupled these)
3. FlatBuffer paths: `from poc.k1_poc.sessionstate.generated.flatbuffers.K1.SessionState` → `from k1.concierge.sessionstate.generated.flatbuffers.K1.SessionState`
4. `pyproject.toml` — no change needed (`packages = ["k0", "k1", "services"]` — `k1.concierge` is already under `k1`)
5. Logger names: `poc.k1_poc.sessionstate` → `k1.concierge.sessionstate` (in `logging.py` defaults)
6. CLI module paths: `python -m poc.k1_poc.sessionstate.cli` → `python -m k1.concierge.sessionstate.cli`

### K1 SessionState Shim (from M4 decision)

After the copy, `k1/sessionstate/` becomes a re-export shim pointing to `k1/concierge/sessionstate/`:

- `k1/sessionstate/__init__.py` → `from k1.concierge.sessionstate import *`
- 70+ K1 sessionstate tests continue importing `from k1.sessionstate` → resolved by shim
- K1 external consumers (fabric, planner, memory_writer) are unaffected — they never import `k1.sessionstate`

### Epics

#### E5.1 — Create Target Directory Structure

Set up `k1/concierge/` subdirectories before the copy.

**E5.1.1** — Create all 22 target subdirectories under `k1/concierge/`

- Create: `actors/`, `bus/`, `compression/`, `config/`, `delta/`, `docs/`, `events/`, `experience/`, `fabric/`, `fsm/`, `identity/`, `kernel/`, `ledger/`, `llm/`, `obs/`, `orchestrator/`, `prompt/`, `protocols/`, `react/`, `scheduler/`, `sessionstate/`, `task/`
- Nested dirs: `sessionstate/ports/`, `sessionstate/adapters/`, `sessionstate/sections/`, `sessionstate/tiers/`, `sessionstate/generated/`, `sessionstate/docs/`, `sessionstate/scripts/`, `tools/`, `protocols/opp/`, `protocols/hitl/`, etc.
- Preserve existing stubs: `affective/`, `empathy/`, `rhythm/`
- Preserve existing docs: `README.md`, `concierge.md`, `concierge.mmd`, `concierge_fsm_flows.md`

**E5.1.2** — Create `tests/k1/concierge/` directory + `__init__.py` + `conftest.py`

- Mirror test structure from `tests/poc/`

---

#### E5.2 — Mechanical File Copy

Copy all 277+ .py files and 24 non-.py files from `poc/k1_poc/` → `k1/concierge/`.

**E5.2.1** — Copy all 22 production directories

- Use `git mv` or `cp` + `git add` for each directory
- DECISION: **Use `cp -r` (copy), not `git mv`** — POC stays behind as reference + demo/ and testing/ still need it
- Command per dir: `cp -r poc/k1_poc/<dir>/* k1/concierge/<dir>/`
- Skip: `demo/`, `testing/`, `main.py`, `concierge_poc_architecture.mmd`
- Special: `concierge_poc_architecture.mmd` → `k1/concierge/docs/concierge_poc_architecture.mmd`
- Total: 277 .py + 24 non-.py = **301 files**

**E5.2.2** — Copy test files

- `tests/poc/*.py` (73 files) → `tests/k1/concierge/`
- Copy `tests/poc/conftest.py` if exists

**E5.2.3** — Verify file counts match

- `find k1/concierge -name "*.py" | wc -l` should equal 277 + existing stubs (4)
- `find tests/k1/concierge -name "*.py" | wc -l` should equal 73 + new init/conftest

---

#### E5.3 — Mass Import Path Rewrite

Rewrite all 3,303 `poc.k1_poc` references to `k1.concierge`.

**E5.3.1** — Rewrite source files (2,072 references across 277 files)

- Use `sed` or Python script: `find k1/concierge -name "*.py" -exec sed -i 's/poc\.k1_poc/k1.concierge/g' {} +`
- Verify: `grep -r "poc\.k1_poc" k1/concierge/ --include="*.py"` should return 0 results
- **WARNING**: Do NOT use blind string replacement. The pattern `poc.k1_poc` could appear in:
  - Import statements: `from poc.k1_poc.X import Y` → `from k1.concierge.X import Y` ✅
  - Docstrings: `"""See poc.k1_poc.X"""` → `"""See k1.concierge.X"""` ✅
  - Logger names: `"poc.k1_poc.sessionstate"` → `"k1.concierge.sessionstate"` ✅
  - CLI module paths: `"poc.k1_poc.sessionstate.cli"` → `"k1.concierge.sessionstate.cli"` ✅
- All replacements are safe — `poc.k1_poc` always means the module path

**E5.3.2** — Rewrite test files (1,231 references across 73 files)

- Same `sed` pattern on `tests/k1/concierge/`
- Verify: `grep -r "poc\.k1_poc" tests/k1/concierge/ --include="*.py"` should return 0 results

**E5.3.3** — Rewrite `k1/concierge/__init__.py`

- Add concierge package docstring and version
- Ensure any re-exports use `k1.concierge.*` paths

**E5.3.4** — Update logger name defaults

- File: `k1/concierge/sessionstate/logging.py` L227
- `name: str = "poc.k1_poc.sessionstate"` → `name: str = "k1.concierge.sessionstate"`
- Already handled by E5.3.1 sed, but verify explicitly

---

#### E5.4 — K1 SessionState Shim

Make `k1/sessionstate/` a re-export facade pointing to `k1/concierge/sessionstate/`.

**E5.4.1** — Replace `k1/sessionstate/__init__.py` with re-export shim

- Content: `from k1.concierge.sessionstate import *; from k1.concierge.sessionstate import __all__`
- This preserves all existing `from k1.sessionstate import X` imports in K1 tests (70+ files)

**E5.4.2** — Replace `k1/sessionstate/ports/__init__.py` with re-export shim

- Content: `from k1.concierge.sessionstate.ports import *`
- K1 fabric/planner adapters that import `k1.sessionstate.ports.*` continue working

**E5.4.3** — Replace `k1/sessionstate/factory.py` with re-export shim

- Content: `from k1.concierge.sessionstate.factory import *`

**E5.4.4** — Replace `k1/sessionstate/manager.py` with re-export shim

- Content: `from k1.concierge.sessionstate.manager import *`

**E5.4.5** — Replace remaining `k1/sessionstate/*.py` files with shims

- All adapter, tier, section, and utility files → re-export from `k1.concierge.sessionstate.*`
- Alternative: delete K1 copies entirely if grep confirms zero external imports (K1 modules use own ports, not k1.sessionstate — confirmed in M4)
- DECISION: Shim approach is safer — keeps 70+ K1 tests green with zero changes

---

#### E5.5 — Fix Cross-Module Import Integrity

After the copy, verify no broken cross-references.

**E5.5.1** — Verify `k1.bus.*` imports still resolve

- Files in `k1/concierge/bus/setup.py`, `actors/`, `fsm/controller.py` import `from k1.bus.*`
- These should still work (k1.bus is a sibling package)
- Run: `python -c "from k1.concierge.bus.setup import create_poc_bus"` — must not ImportError

**E5.5.2** — Verify no circular imports

- `k1.concierge.sessionstate` ← `k1.sessionstate` (shim)
- `k1.concierge.bus.setup` → `k1.bus.factory` (cross-package, OK)
- `k1.concierge.config` → standalone (no circular risk)
- Run `python -c "import k1.concierge"` — must not raise

**E5.5.3** — Verify FlatBuffer generated imports resolve

- 80 generated files under `k1/concierge/sessionstate/generated/`
- All use `from k1.concierge.sessionstate.generated.flatbuffers.K1.SessionState import ...` after rewrite
- Run: `python -c "from k1.concierge.sessionstate.sections.control import ControlSection"` — must not ImportError

**E5.5.4** — Verify `demo/` and `testing/` still work from `poc/k1_poc/`

- `demo/coordinator.py` imports from `poc.k1_poc.*` — these still point to the original (un-moved) POC files
- `testing/harness/engine.py` imports from `poc.k1_poc.*` — same
- The original `poc/k1_poc/` source files are NOT deleted — demo/testing can still function
- Alternative: update demo/testing to import from `k1.concierge.*` — **DEFERRED** (demo stays as-is for POC reference)

---

#### E5.6 — Test Migration

Ensure all tests run from their new locations.

**E5.6.1** — Run migrated test suite from `tests/k1/concierge/`

- `pytest tests/k1/concierge/ -v` — all 73 files, ~3,054 tests
- Every test must pass — import paths are the only change

**E5.6.2** — Run K1 sessionstate tests via shim

- `pytest tests/k1/sessionstate/ -v` — all 70+ files
- Tests import `from k1.sessionstate.*` → shim resolves to `k1.concierge.sessionstate.*`
- Must be 100% green

**E5.6.3** — Run POC internal harness tests

- `pytest poc/k1_poc/testing/harness/ -v` — 10 files, 207 tests
- These import from `poc.k1_poc.*` (original path) — must still work since original files remain

**E5.6.4** — Run full test suite (all ~3,261+ tests)

- Everything green — migrated tests + K1 tests + original POC harness

---

#### E5.7 — Cleanup + Tag

**E5.7.1** — Add `k1/concierge/` to any linting/CI configurations

- Check `.github/workflows/` for test path patterns
- Check `pyproject.toml` `[tool.pytest.ini_options]` testpaths (currently just `["tests"]` — already covers `tests/k1/concierge/`)
- Check coverage config if applicable

**E5.7.2** — Update `pyproject.toml` if needed

- `packages = ["k0", "k1", "services"]` — already covers `k1.concierge` (it's under `k1`)
- No change needed ✅

**E5.7.3** — Git commit + tag `m5-big-copy-complete`

- Single large commit: "feat: Copy POC concierge to k1/concierge — 301 files, 3,303 import rewrites"

### Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| Import path rewrite misses edge case | Tests fail | E5.3 verification grep ensures zero `poc.k1_poc` remnants |
| FlatBuffer generated code has hardcoded paths | ImportError in sections | E5.5.3 explicit verification |
| K1 sessionstate shim introduces circular import | ImportError | E5.5.2 circular import check |
| `demo/` breaks because underlying modules moved | Demo stops working | Original `poc/k1_poc/` files NOT deleted — demo still works |
| Merge conflict with other branches | Git conflict | Run on clean `POC_Migration` branch, rebase before merge |
| Large commit hard to review | Review fatigue | Mechanical-only changes (copy + sed) — no logic changes |

### Summary Metrics

| Metric | Count |
|---|--:|
| Directories to copy | 22 |
| .py files to copy | 277 |
| Non-.py files to copy | 24 |
| Test files to move | 73 |
| Import references to rewrite | 3,303 |
| K1 sessionstate shim files | ~15 |
| Target conflicts to resolve | 1 (tools/ — safe overwrite) |
| External consumer breakage | 0 |
| Expected test changes | 0 (import paths only) |
| pyproject.toml changes | 0 |

---

## M6 — K1 Fabric Wiring

> Swap `FabricPOCBridge` (M2 adapter wrapping `CapabilityRegistry`) for the real K1 `Fabric` class.
> After M5 the code lives at `k1/concierge/`. The `Fabric` container class satisfies `IFabricPort`
> natively — all 4 methods match structurally. The work is: (1) convert 40 POC capability dicts to
> K1 `CapabilityContract` objects, (2) wire a `POCMockBridgeAdapter` so the `BridgeProvider` can
> dispatch to POC mock handler functions, (3) boot a real `Fabric` instance in Concierge bootstrap,
> (4) remove the `FabricPOCBridge` entirely.

**Prerequisite**: M2 (`IFabricPort` defined), M5 (code at `k1/concierge/`)

### End-to-End Port Chain Review (M1–M4 → M5 → M6)

| Milestone | Port Protocol | Defined Where | POC Adapter (Pre-M6) | K1 Real Impl | Swaps At |
|---|---|---|---|---|---|
| M1 | `IModelHubPort` | `k1/model_hub/ports.py` (NEW in M1) | `ModelHubPOCBridge` wraps `GeminiConciergeAdapter` | K1 Model Hub service | M7 |
| M2 | `IFabricPort` | `k1/concierge/fabric/ports.py` (NEW in M2) | `FabricPOCBridge` wraps `CapabilityRegistry` | K1 `Fabric` class → direct injection | **M6 ← THIS** |
| M3 | `IBus` / `IMailboxRouter` / `IMailbox` | `k1/bus/ports/` (EXISTING) | Already K1 bus directly | K1 bus IS the impl | Done (type hints only) |
| M4 | 5 ABCs: `IStoragePort`, `IEventPort`, `IWriterPort`, `ILifecyclePort`, `IK0SyncPort` | `k1/sessionstate/ports/` (EXISTING, byte-for-byte identical) | Same impl, config decoupled | Same impl | M5 (shim) |

After M6, `IFabricPort` is the **second port** fully wired to production K1 (after IBus in M3).

### K1 Fabric Architecture (from research)

**`Fabric`** (`k1/fabric/fabric.py` L1257) is a `@dataclass` container holding three sub-APIs:

- `CapabilityFabric` — 9-step execution pipeline (resolve → policy → circuit-break → dispatch → validate → emit)
- `FabricRetrieval` — 5-stage discovery pipeline (embed → hard-filter → soft-rank → top-k → score)
- `CapabilityRegistryAPI` — register/unregister/lookup/list contracts

**Does `Fabric` satisfy `IFabricPort`?**

| IFabricPort method | Fabric method | Match |
|---|---|---|
| `execute(CapabilityRequest) -> CapabilityResult` | `execute(CapabilityRequest) -> CapabilityResult` | **Exact** |
| `execute_batch(list, strategy: str) -> list` | `execute_batch(list, strategy: BatchStrategy)` | **Structural** — `BatchStrategy(str, Enum)` IS a str subclass |
| `discover_capabilities(domain, intent, safety_band, session_context, top_k) -> RetrievalResult` | Same signature | **Exact** |
| `find_relevant_prompts(intent, domain, safety_band, top_k) -> RetrievalResult` | Same signature | **Exact** |

**Verdict**: `Fabric` satisfies `IFabricPort` natively. Zero adapter code needed at the Concierge level — just inject the `Fabric` instance directly.

### K1 Fabric Factory — 3 Construction Modes

| Mode | Method | External Deps | Use Case |
|---|---|---|---|
| Standalone | `FabricFactory.create_standalone(contracts_dir?, config?)` | None — all test adapters | Dev, examples |
| Testing | `FabricFactory.create_for_testing(capture_events?, ...)` | None — test adapters + event capture | Integration tests |
| Production | `FabricFactory.create_with_ports(state_reader, event_port, bridge, model_gateway, prompt_system, delta_bus, ...)` | 6 required ports | Real deployment |

**`create_with_ports` — 6 Required Port Injections**:

| Port | Protocol | What It Provides |
|---|---|---|
| `state_reader` | `ISessionStateReader` | Read SessionState sections for context building |
| `event_port` | `IEventPort` | Emit/subscribe Fabric events on bus |
| `bridge` | `IBridgePort` | K0 bridge operations (memory, checkpoint, IFL) |
| `model_gateway` | `IModelGatewayPort` | LLM access for Agent provider |
| `prompt_system` | `IPromptSystemPort` | Prompt template loading |
| `delta_bus` | `IDeltaBusPort` | Agent delta emission |

**Strategy for M6**: Start with `create_for_testing()` — zero external deps, gives a fully-wired Fabric with test adapters and event capture. Swap `bridge` arg for our custom `POCMockBridgeAdapter` so POC handler functions execute with real logic. Graduate to `create_with_ports()` when real SessionState, EventBus, and Bridge ports are wired in M8+.

### K1 Fabric Provider Inventory

| Provider | ProviderType | Handles | Relevant for M6? |
|---|---|---|---|
| `MCPProvider` | MCP | Remote MCP tools (SSE/stdio) | No — POC tools aren't MCP servers |
| `WASMProvider` | WASM | Sandboxed WASM modules | No |
| **`BridgeProvider`** | BRIDGE | K0 bridge ops + IFL device routing | **YES** — routes `tool.execute.*` via IBridgePort |
| `AgentProvider` | AGENT | LLM-powered sub-agents | No (M8 Orchestrator) |
| `WorkflowProvider` | WORKFLOW | Frozen DAG execution | No (M9 Planner) |
| `ConciergeProvider` | CONCIERGE | `concierge.state.*` → FSM handlers | No (reverse direction — Fabric calls INTO concierge) |

**`BridgeProvider`** is the correct provider for POC capabilities because:

1. All 40 POC capabilities use `tool.execute.*` naming
2. `BridgeProvider._classify_operation()` passes `tool.execute.*` through as-is (not limited to `memory.*` / IFL)
3. `BridgeProvider` delegates to `IBridgePort.send_command(operation, payload)` — our `POCMockBridgeAdapter` wraps POC mock handlers behind this interface

### POC Capability Inventory — 40 Capabilities

| Group | Count | Names (pattern) | Domain(s) |
|---|---|---|---|
| Demo | 7 | `hotel_search`, `hotel_booking`, `restaurant_search`, `restaurant_booking`, `weather_forecast`, `calendar_create`, `product_search` | travel, productivity, shopping |
| Family | 31 | `send_message`, `send_group_message`, `send_reminder`, `send_notification`, `get_todo_list`, `add_todo_item`, `complete_todo_item`, `get_grocery_list`, `add_grocery_item`, `grocery_order`, `get_chore_schedule`, `assign_chore`, `log_chore_complete`, `get_school_schedule`, `check_homework`, `school_pickup_status`, `medication_reminder`, `schedule_appointment`, `pharmacy_refill`, `vet_appointment`, `ride_request`, `package_tracking`, `carpool_coordinate`, `smart_home_control`, `set_timer`, `nap_timer`, `home_security_status`, `family_calendar`, `meal_planner`, `family_budget`, `swim_bag_check` | messaging, productivity, shopping, household, school, health, transport, logistics, iot, family, finance |
| Web | 2 | `web_search`, `web_fetch` | search |

**All named with prefix `tool.execute.*`**

### POC Capability Shape → K1 CapabilityContract Mapping

| POC dict field | K1 `CapabilityContract` field | Transform |
|---|---|---|
| `name` (str) | `name` (str) | Direct |
| `description` (str) | `description` (str) | Direct |
| `domain` (str) | `domain` (List[str]) | Wrap: `[poc_dict["domain"]]` |
| `required_inputs` (list of str) | `required_inputs` (list of `InputSpec`) | `InputSpec(name=n, type="STRING", description="")` |
| `optional_inputs` (list of str) | `optional_inputs` (list of `InputSpec`) | `InputSpec(name=n, type="STRING", description="")` |
| `has_side_effects` (bool) | `limitations` (list of str) | If True → `["has_side_effects"]` |
| `estimated_cost` (str) | `cost_per_call` (float) | Parse or 0.0 |
| *(missing)* | `version` | Default `"1.0.0"` |
| *(missing)* | `provider_type` | `"BRIDGE"` |
| *(missing)* | `provider_id` | `"poc-mock-bridge"` |
| *(missing)* | `provider_endpoint` | `"local://poc-mock-bridge"` |
| *(missing)* | `safety_band_min` | `"GREEN"` |
| *(missing)* | `output` | `{}` (no schema) |
| *(missing)* | `capabilities` | `["tool_execution"]` |
| *(missing)* | `required_context` | `[]` |
| *(missing)* | `avg_latency_ms` | `50` (mock) |
| *(missing)* | `max_latency_ms` | `200` (mock) |
| *(missing)* | `availability` | `"ONLINE"` |

### POC Mock Handler Dispatch via IBridgePort

**Problem**: `BridgeProvider` calls `IBridgePort.send_command(operation, payload, *, trace_id, timeout_ms) -> BridgeCommandResult`. POC mock handlers are `async (params: dict) -> dict` (simple callables returning result dicts). Need a bridge between these two shapes.

**Solution**: Create `POCMockBridgeAdapter` implementing `IBridgePort`:

- Holds reference to POC `CapabilityRegistry` (or handler map)
- `send_command(operation, payload, *, trace_id, ...) -> BridgeCommandResult`:
  - Look up handler from `CapabilityRegistry._handlers[operation]`
  - Call `handler(payload)` (the existing mock handler)
  - Wrap result dict in `BridgeCommandResult.ok(data=result)` or `.fail()`
- `query(operation, selectors, *, trace_id, ...) -> BridgeCommandResult`:
  - Same dispatch (POC doesn't distinguish read vs write)
- `route_ifl(route, payload, *, trace_id) -> BridgeCommandResult`:
  - Same dispatch via `route.address` (for `home.*`/`device.*`)
- `is_available() -> True` always
- `get_health() -> BridgeHealth(available=True, mode="K0_FULL")`

**Alternative considered**: Use `TestBridgeAdapter.add_handler()` to register each POC handler. Rejected because:

- `add_handler` expects `(operation, payload, trace_id) -> BridgeCommandResult` (synchronous), POC handlers are `async (params) -> dict`
- Would require 40 wrapper lambdas
- Custom adapter is cleaner and properly typed

### K1 Fabric Discovery Gap

K1 `FabricRetrieval` uses FAISS semantic similarity with `_StubEmbeddingPort` (zero vectors) in test mode — returns zero similarity for everything, so discovery returns nothing useful.

**Resolution**: Two-phase approach:

- **Phase 1 (M6)**: Use K1's `HardFilter` domain-based filtering (works without embeddings). Discovery via `domain` + `intent` keyword matching returns results from `CapabilityRegistry.list_by_domain()`.
- **Phase 2 (M10)**: Wire real `IEmbeddingPort` for semantic similarity when K1 embedding infra is available.

### Epics

#### E6.1 — Create POC → K1 Contract Converter

> Converts POC capability dicts into K1 `CapabilityContract` objects so all 40 capabilities
> can be registered with the Fabric's `CapabilityRegistry`.

**E6.1.1** — Create `k1/concierge/fabric/contract_converter.py`

Function: `poc_dict_to_contract(cap_dict: dict) -> CapabilityContract`

- Import: `from k1.fabric.types import CapabilityContract, InputSpec`
- Maps 7 POC dict fields to 24+ `CapabilityContract` fields (see mapping table above)
- Sets `provider_type="BRIDGE"`, `provider_id="poc-mock-bridge"`, `provider_endpoint="local://poc-mock-bridge"`
- Sets `version="1.0.0"`, `safety_band_min="GREEN"`, `availability="ONLINE"`
- Sets `ephemeral=True`, `session_scoped=True` (POC capabilities are session-scoped)
- Handles `has_side_effects` → `limitations=["has_side_effects"]`
- Handles `estimated_cost` → `cost_per_call` float parse

Function: `convert_all_poc_capabilities() -> list[CapabilityContract]`

- Imports `DEMO_CAPABILITIES` from `demo_capabilities.py` (7)
- Imports `FAMILY_CAPABILITIES` from `family_capabilities.py` (31)
- Imports `WEB_CAPABILITIES` from `web_capabilities.py` (2)
- Calls `poc_dict_to_contract()` for each → returns 40 `CapabilityContract` objects

Touch point: NEW file `k1/concierge/fabric/contract_converter.py` (~80 lines)
Depends on: M5 (capability files at `k1/concierge/fabric/`)

---

#### E6.2 — Create POCMockBridgeAdapter

> Implements `IBridgePort` so the `BridgeProvider` can dispatch to POC mock handler functions
> through the standard Fabric execution pipeline.

**E6.2.1** — Create `k1/concierge/fabric/poc_bridge_adapter.py`

Class: `POCMockBridgeAdapter` satisfies `IBridgePort` (structural — no inheritance)

Constructor: `__init__(self, registry: CapabilityRegistry)`

- Stores reference to `CapabilityRegistry` which holds the handler map

Methods:

- `async send_command(operation: str, payload: dict, *, trace_id: str = "", timeout_ms: int = 0) -> BridgeCommandResult`:
  - Look up handler: `handler = self._registry.get_handler(operation)` or `self._registry._handlers.get(operation)`
  - If handler not found → `BridgeCommandResult.fail("not_found", f"No handler for {operation}")`
  - Call handler: `result = await handler(payload)` (or `handler(payload)` if sync — check and wrap)
  - On success → `BridgeCommandResult.ok(data=result, trace_id=trace_id)`
  - On exception → `BridgeCommandResult.fail("handler_error", str(exc), trace_id=trace_id)`

- `async query(operation: str, selectors: dict, *, trace_id: str = "", timeout_ms: int = 0) -> BridgeCommandResult`:
  - Delegates to `send_command(operation, selectors, trace_id=trace_id, timeout_ms=timeout_ms)`
  - POC doesn't distinguish read vs write operations

- `async route_ifl(route: IFLRoute, payload: dict, *, trace_id: str = "") -> BridgeCommandResult`:
  - Dispatches via `route.address` as operation name
  - Same handler lookup + call pattern

- `is_available() -> bool`: Always `True`

- `get_health() -> BridgeHealth`: Always `BridgeHealth(available=True, mode="K0_FULL")`

Touch point: NEW file `k1/concierge/fabric/poc_bridge_adapter.py` (~100 lines)
Depends on: E6.1.1 (for typing), existing `CapabilityRegistry` from `capability_registry.py`
Import: `from k1.fabric.ports.bridge_port import IBridgePort, BridgeCommandResult, BridgeHealth, IFLRoute`

---

#### E6.3 — Wire Real `Fabric` Instance in Concierge Bootstrap

> Replace `FabricPOCBridge(capability_registry)` with a real `Fabric` instance in
> `k1/concierge/kernel/bootstrap.py`. The `Fabric` satisfies `IFabricPort` natively.

**E6.3.1** — Create Fabric factory helper in bootstrap

Add to `k1/concierge/kernel/bootstrap.py`:

```python
from k1.fabric.factory import FabricFactory, FabricConfig
from k1.concierge.fabric.poc_bridge_adapter import POCMockBridgeAdapter
from k1.concierge.fabric.contract_converter import convert_all_poc_capabilities

def _create_fabric(registry: CapabilityRegistry) -> Fabric:
    """Boot a real K1 Fabric with POC mock handlers behind BridgeProvider."""
    poc_bridge = POCMockBridgeAdapter(registry)

    fabric = FabricFactory.create_with_ports(
        state_reader=TestSessionStateReaderAdapter(),  # M8 wires real
        event_port=LocalEventAdapter(capture_mode=True),
        bridge=poc_bridge,                             # ← POC mock handlers
        model_gateway=TestModelGatewayAdapter(),       # M7 wires real
        prompt_system=TestPromptSystemAdapter(),
        delta_bus=TestDeltaBusAdapter(),
        production_mode=False,
        contracts_dir=None,  # No YAML scan — register programmatically
    )

    # Register all 40 POC capabilities
    for contract in convert_all_poc_capabilities():
        fabric.register(contract)

    return fabric
```

Touch point: EDIT `k1/concierge/kernel/bootstrap.py` — add `_create_fabric()` function, replace `FabricPOCBridge(capability_registry)` with `_create_fabric(capability_registry)`
Depends on: E6.1.1, E6.2.1, M5 (file at new path)

**E6.3.2** — Replace `ToolContext.fabric_port` assignment

In `k1/concierge/kernel/bootstrap.py` where `ToolContext` is constructed:

- Old (M2): `fabric_port=FabricPOCBridge(capability_registry)`
- New (M6): `fabric_port=_create_fabric(capability_registry)`
- The `Fabric` instance satisfies `IFabricPort` — no adapter needed
- Remove import of `FabricPOCBridge`

Touch point: EDIT `k1/concierge/kernel/bootstrap.py` — ToolContext construction site
Depends on: E6.3.1

**E6.3.3** — Replace `_FabricGatewayAdapter` (Orchestrator port) wiring

In M2 E2.4.2, `_FabricGatewayAdapter` wraps `FabricPOCBridge` for the Orchestrator. After M6:

- `_FabricGatewayAdapter.__init__` now accepts `Fabric` instance (it already satisfies the same `execute` / `execute_batch` interface)
- OR: Remove `_FabricGatewayAdapter` entirely — `IFabricGatewayPort` in `orchestrator/ports.py` should be satisfied by the `Fabric` instance directly
- DECISION: Keep `_FabricGatewayAdapter` as a thin type-narrowing wrapper for now (it translates POC Orchestrator `CapabilityRequest` → K1 `CapabilityRequest`). This gets cleaned up in M8 (Orchestrator Wiring).

Touch point: EDIT `k1/concierge/kernel/bootstrap.py` — `_FabricGatewayAdapter` constructor, change from `FabricPOCBridge` to `Fabric`

---

#### E6.4 — Remove `FabricPOCBridge` (Dead Code)

> After E6.3, `FabricPOCBridge` is no longer used. Remove it.

**E6.4.1** — Delete `k1/concierge/fabric/fabric_bridge.py`

- This file was created in M2 E2.2.1 as the bridge adapter
- After M6, the real `Fabric` instance replaces it
- Verify no remaining imports: `grep -r "FabricPOCBridge" k1/concierge/ tests/k1/concierge/`

Touch point: DELETE `k1/concierge/fabric/fabric_bridge.py`

**E6.4.2** — Remove backward-compat callback fields from `ToolContext`

In M2 E2.3.1, `invoke_fn`, `capability_fn`, `fabric_fn`, `workflow_fn` were kept for backward compatibility. After M6, all tool functions use `fabric_port` exclusively:

- Remove deprecated fields from `ToolContext` dataclass in `k1/concierge/tools/implementations.py`
- Remove fallback branches in `execute_invoke_capability()`, `execute_discover_capabilities()`, `execute_spawn_via_fabric()`, `execute_execute_workflow()`
- Each function now has only the `fabric_port` path (no `if ctx.fabric_port is not None:` check — it's always set)

Touch point: EDIT `k1/concierge/tools/implementations.py` — `ToolContext` class, 4 tool functions
Depends on: E6.3.2 (fabric always wired)

---

#### E6.5 — Verify Fabric 9-Step Pipeline Executes

> The real `Fabric` runs a 9-step execution pipeline for every `execute()` call. Verify all 9
> steps fire correctly for POC capabilities.

The 9 steps (from `k1/fabric/fabric.py` `CapabilityFabric.execute()`):

1. **Resolve** — `ProviderMatcher` + `ProviderSelector` → find provider for capability
2. **Policy** — `PolicyEngine` evaluates safety band, affective routing, QoS
3. **Context Build** — `ContextBuilder` reads SessionState sections (via `ISessionStateReader`)
4. **Circuit Breaker** — check provider CB state (closed/open/half-open)
5. **Dispatch** — `BridgeProvider._execute()` → calls `IBridgePort.send_command()`
6. **Output Validation** — `OutputValidationPipeline` checks result schema
7. **CB Update** — record success/failure in circuit breaker
8. **Metrics** — update capability metrics (latency, success rate)
9. **Event Emit** — emit `capability.executed` event via `EventEmitter`

**E6.5.1** — Verify Step 1 (Resolution) works for all 40 capabilities

- After E6.3.1 registers contracts with `provider_type="BRIDGE"`, `provider_id="poc-mock-bridge"`
- `_auto_register_providers()` creates a `ProviderConfig(provider_id="poc-mock-bridge", provider_type="BRIDGE")` in `ProviderRegistry`
- `ProviderMatcher` looks up `provider_id` from contract → `ProviderRegistry` returns config
- `ProviderSelector` creates `BridgeProvider(config, bridge=poc_bridge)`
- Test: `await fabric.execute(CapabilityRequest(capability_name="tool.execute.hotel_search", params={...}))` should NOT fail at resolution

Touch point: Test assertion in E6.7

**E6.5.2** — Verify Step 5 (Dispatch) routes through `POCMockBridgeAdapter`

- `BridgeProvider._execute()` calls `self._bridge.send_command(operation="tool.execute.hotel_search", payload={...})`
- `POCMockBridgeAdapter.send_command()` looks up handler from `CapabilityRegistry`
- Handler executes mock logic → returns result dict
- `BridgeProvider._parse_response()` wraps into `CapabilityResult`
- Test: result should have `success=True`, `data` matching mock handler output

Touch point: Test assertion in E6.7

**E6.5.3** — Verify Step 9 (Event Emit) fires for observability

- `EventEmitter.emit_executed()` fires after every execution
- With `LocalEventAdapter(capture_mode=True)`, events are captured
- Test: `fabric.event_port.get_captured()` should contain `capability.executed` events with correct `capability_name`, `trace_id`, `duration_ms`

Touch point: Test assertion in E6.7

---

#### E6.6 — Verify Discovery Pipeline

> K1 `FabricRetrieval` has a 5-stage discovery pipeline. With `_StubEmbeddingPort` (zero vectors),
> semantic similarity returns nothing. Domain-based filtering via `HardFilter` still works.

**E6.6.1** — Verify domain-filtered discovery works

- `fabric.discover_capabilities(domain=["travel"])` should return 4 capabilities: `hotel_search`, `hotel_booking`, `restaurant_search`, `restaurant_booking`
- `fabric.discover_capabilities(domain=["messaging"])` should return 4 capabilities
- NOTE: If `_StubEmbeddingPort` causes empty results even for domain-filtered queries, we may need to use `CapabilityRegistryAPI.list_by_domain()` directly as a fallback
- Test: discovery by domain returns correct count and names

**E6.6.2** — Assess intent-based discovery quality

- `fabric.discover_capabilities(intent="book a hotel")` — with stub embeddings, this relies on keyword matching
- If results are empty or poor quality, document the gap and defer to M10 (real embeddings)
- DECISION: If domain-based discovery works but intent-based doesn't, the Concierge tools should pass `domain` hints alongside intent queries

Touch point: Test + documentation in E6.7

---

#### E6.7 — Unit Tests for Fabric Wiring

> Validate the full Concierge → Fabric → BridgeProvider → POCMockBridgeAdapter → handler pipeline.

**E6.7.1** — Create `tests/k1/concierge/test_contract_converter.py`

Tests for `contract_converter.py`:

- `poc_dict_to_contract()` produces valid `CapabilityContract` for each capability type
- All 40 capabilities convert without error
- `domain` is list (not str)
- `required_inputs` are `InputSpec` objects (not bare strings)
- `provider_type` is `"BRIDGE"` for all
- `provider_id` is `"poc-mock-bridge"` for all
- `has_side_effects=True` → `limitations=["has_side_effects"]`
- `estimated_cost="free"` → `cost_per_call=0.0`
- `convert_all_poc_capabilities()` returns exactly 40 contracts

Touch point: NEW file `tests/k1/concierge/test_contract_converter.py` (~25 tests)

**E6.7.2** — Create `tests/k1/concierge/test_poc_bridge_adapter.py`

Tests for `poc_bridge_adapter.py`:

- `POCMockBridgeAdapter` satisfies `IBridgePort` structurally (has all 5 methods)
- `is_available()` returns True
- `get_health()` returns `BridgeHealth(available=True, mode="K0_FULL")`
- `send_command("tool.execute.hotel_search", {"location": "Paris"})` → `BridgeCommandResult` with `success=True`
- Unknown operation → `BridgeCommandResult` with `success=False`, `error_code="not_found"`
- Handler exception → `BridgeCommandResult` with `success=False`, `error_code="handler_error"`
- `query()` delegates to same dispatch as `send_command()`
- All 40 capabilities dispatch correctly through the adapter

Touch point: NEW file `tests/k1/concierge/test_poc_bridge_adapter.py` (~30 tests)

**E6.7.3** — Create `tests/k1/concierge/test_fabric_wiring_e2e.py`

End-to-end tests for the full Fabric pipeline:

- Boot `Fabric` via `_create_fabric()` with POC registry
- `fabric.execute(CapabilityRequest(capability_name="tool.execute.hotel_search", params={"location": "Paris"}, ...))`:
  - Returns `CapabilityResult` with `success=True`
  - `result.data` matches mock handler output
  - `result.duration_ms > 0`
  - Pipeline events captured (step 9)
- `fabric.execute_batch([req1, req2], "PARALLEL")` — both succeed
- `fabric.discover_capabilities(domain=["travel"])` — returns 4 capabilities
- `fabric.discover_capabilities(domain=["messaging"])` — returns 4 capabilities
- `fabric.discover_capabilities(domain=["health"])` — returns 4 capabilities (medication, schedule, pharmacy, vet)
- Error case: `fabric.execute(CapabilityRequest(capability_name="tool.execute.nonexistent", ...))` — fails gracefully at resolution
- Circuit breaker: after repeated failures, provider enters OPEN state (if handler raises)

Touch point: NEW file `tests/k1/concierge/test_fabric_wiring_e2e.py` (~40 tests)

**E6.7.4** — Create `tests/k1/concierge/test_tool_fabric_live.py`

Tests that the tool functions work with the real Fabric (not just `IFabricPort`):

- `execute_invoke_capability()` with real `Fabric` as `fabric_port`:
  - Builds `CapabilityRequest`, calls `fabric.execute()`, returns `ToolResult`
  - All 40 capabilities succeed
- `execute_discover_capabilities()` with real `Fabric`:
  - Calls `fabric.discover_capabilities()`, returns `ToolResult` with capability list
- `execute_spawn_via_fabric()` — builds `agent.*` request, dispatches (may fail — no AgentProvider wired, expected)
- `execute_execute_workflow()` — builds `workflow.*` request, dispatches (may fail — no WorkflowProvider wired, expected)
- HITL blocking still works with real Fabric path

Touch point: NEW file `tests/k1/concierge/test_tool_fabric_live.py` (~30 tests)

---

#### E6.8 — Integration Tests: Full Suite Green

> Final gate: the real Fabric instance replaces FabricPOCBridge with zero regressions.

**E6.8.1** — Run full Concierge test suite

- `pytest tests/k1/concierge/ -v` — all migrated tests (3,054+) must pass
- Focus areas: tool execution tests (these use `fabric_port`), orchestrator tests (these use `_FabricGatewayAdapter`)
- Any failure means E6.3 wiring or E6.4 cleanup broke something — fix before proceeding

**E6.8.2** — Run K1 Fabric test suite

- `pytest tests/k1/fabric/ -v` — all 183+ K1 Fabric tests must pass
- Concierge changes must NOT affect Fabric internals
- Gate: 100% green

**E6.8.3** — Run full test suite (all tests)

- All K1 tests + Concierge tests + POC harness
- Gate: 100% green

**E6.8.4** — Git tag `m6-fabric-wiring-complete`

### Structural Gap Analysis

| Aspect | Before M6 (FabricPOCBridge) | After M6 (Real Fabric) | Impact |
|---|---|---|---|
| Execution pipeline | Direct `registry.invoke()` — no policy, no CB, no validation | Full 9-step pipeline — resolve, policy, CB, dispatch, validate, emit | Capabilities now protected by policy engine + circuit breakers |
| Discovery | Fuzzy word-overlap matching in `CapabilityRegistry.discover()` | `FabricRetrieval` 5-stage pipeline (domain filter works, embeddings stubbed) | More structured discovery, domain-based filtering |
| Provider resolution | None — direct handler call | `ProviderMatcher` → `ProviderSelector` → `BridgeProvider` | Capabilities routed through standard provider system |
| Circuit breaking | None | Per-provider CB (timeout, failure threshold) | Automatic failure isolation |
| Event emission | None | `EventEmitter` fires `capability.executed`, `capability.registered` | Observable execution for tracing |
| Output validation | None | `OutputValidationPipeline` (if contracts specify output schema) | Type-safe results (when schemas provided) |
| Batch execution | Sequential `for r in requests` | `BatchStrategy.PARALLEL` or `.SEQUENTIAL` with `FabricDispatcher` | Parallel execution available (production_mode=True) |
| `IFabricPort` implementation | `FabricPOCBridge` (adapter, ~180 LoC) | `Fabric` (direct, 0 adapter LoC) | Zero adapter overhead |

### Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| `BridgeProvider` doesn't route `tool.execute.*` to bridge | Capabilities fail at resolution | E6.5.1 explicit test; `_classify_operation()` passes unknown prefixes through |
| `_auto_register_providers()` doesn't auto-create provider for `poc-mock-bridge` | Resolution fails — no provider in registry | E6.3.1 registers contracts AFTER factory builds; auto-register scans all contracts |
| `_StubEmbeddingPort` breaks intent-based discovery | Discovery returns empty | E6.6 tests domain-based filtering separately; intent-based deferred to M10 |
| POC handlers are async but `BridgeProvider` may not await properly | Runtime error | E6.2.1 adapter handles both sync and async handlers |
| `FabricConfig.default_timeout_ms` (30s) too long for POC mock handlers | Tests slow | Set `FabricConfig(default_timeout_ms=5000)` for testing |
| Removing `FabricPOCBridge` breaks tests that mock it | Test failures | E6.4.1 grep before delete; update tests to use real Fabric |
| Removing deprecated `ToolContext` callbacks breaks tests | Test failures | E6.4.2 update tests that set `invoke_fn`/`capability_fn` to use `fabric_port` |

### Summary Metrics

| Metric | Count |
|---|--:|
| New files created | 3 (converter, adapter, 0 YAML) |
| Files edited | 2 (bootstrap.py, implementations.py) |
| Files deleted | 1 (fabric_bridge.py) |
| New test files | 4 |
| POC capabilities registered | 40 |
| Fabric pipeline steps exercised | 9 |
| K1 test adapters used | 5 (state_reader, model_gateway, prompt_system, delta_bus, event_port) |
| K1 adapter replaced | 1 (bridge → POCMockBridgeAdapter) |
| Backward-compat callbacks removed | 4 (invoke_fn, capability_fn, fabric_fn, workflow_fn) |

---

## M7 — K1 Model Hub Wiring

> K1 Model Hub has ZERO Python — only `k1/model_hub/model_hub.mmd` (~700 line production spec).
> M1 built the contract layer (`types.py`, `ports.py`, `plugins/base.py`) and a POC bridge (`ModelHubPOCBridge`)
> that wraps `GeminiConciergeAdapter` behind `IModelHubPort`. After M5 Big Copy, the Concierge
> at `k1/concierge/` still routes LLM calls through this bridge.
>
> This milestone **builds the real Model Hub service** per the `.mmd` spec (Option B — Lightweight Hub),
> wires it into the Concierge via the production `ModelGatewayAdapter` (from `concierge.mmd`),
> and removes the POC bridge. Defers the full 13-service architecture (manifest scanning, hot-reload,
> multi-provider, response cache, rate limiter, cost tracker) to a post-M10 Model Hub Hardening milestone.

**K1 Model Hub status (post-M1)**: `types.py` (HubRequest, HubResponse, ~250 lines), `ports.py` (IModelHubPort + 6 ports, ~120 lines), `plugins/base.py` (IProviderPlugin + internal types, ~150 lines), `plugins/test_plugin.py` (TestProviderPlugin, ~100 lines)
**Bridge status (post-M5)**: `k1/concierge/llm/model_hub_bridge.py` — `ModelHubPOCBridge(inner: GeminiConciergeAdapter)` implements `IModelHubPort`, translates HubRequest ↔ ConciergeModelRequest
**Caller status (post-M5)**: `k1/concierge/react/loop.py`, `actors/front.py`, `actors/back.py` all use `IModelHubPort` + `HubRequest`/`HubResponse`
**Bootstrap status (post-M5)**: `k1/concierge/kernel/bootstrap.py` `_create_model()` returns `ModelHubPOCBridge(GeminiConciergeAdapter(api_key=...))`
**Concierge .mmd (production arch)**: Defines `ILLMPort` (outbound, line 262) with `execute(HubRequest)→HubResponse` + `stream_execute(HubRequest)→AsyncIterator[HubChunk]`, adapted by `ModelGatewayAdapter` (line 283) which routes to Model Hub with LLM cascade (RETRY → CB HALF-OPEN → CANNED_RESPONSE)

### Architecture: What M7 Builds

```
┌─────────────────────────── k1/concierge/ ────────────────────────────┐
│                                                                       │
│  react/loop.py → ILLMPort.execute() / .stream_execute()              │
│       │                                                               │
│       ▼                                                               │
│  ModelGatewayAdapter (ILLMPort impl)                                  │
│   • tags capability (CHAT/TOOL_CALL/STRUCTURED/REASON)               │
│   • LLM cascade: RETRY → CB HALF-OPEN → CANNED_RESPONSE             │
│       │                                                               │
└───────│───────────────────────────────────────────────────────────────┘
        │ (in-process call, bus deferred)
        ▼
┌─────────────────────────── k1/model_hub/ ────────────────────────────┐
│                                                                       │
│  ModelHubService (IModelHubPort impl)                                 │
│   ├── validate request (capability, constraints)                      │
│   ├── BudgetEnforcer.check(consumer_id, estimated_cost)               │
│   ├── ModelSelector.select(capability, constraints) → fallback chain  │
│   ├── dispatch to IProviderPlugin.execute() or .stream_execute()      │
│   ├── on failure → next in fallback chain                             │
│   └── post-dispatch: record spend, build ResponseMetadata             │
│                                                                       │
│  GeminiProviderPlugin (IProviderPlugin impl)                          │
│   • wraps GeminiConciergeAdapter internally                           │
│   • translates NormalizedRequest ↔ ConciergeModelRequest              │
│   • supports: CHAT, TOOL_CALL, STRUCTURED, REASON                    │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

### What Gets Built vs Deferred

| Component | M7 Scope | Notes |
|---|---|---|
| GeminiProviderPlugin | ✅ BUILD | Wraps GeminiConciergeAdapter as IProviderPlugin |
| ModelSelector | ✅ BUILD (simplified) | Single-provider, fallback chain (3 alternatives) |
| BudgetEnforcer | ✅ BUILD | Daily budget per consumer_id ($5/day default from .mmd MH-07) |
| ModelHubService | ✅ BUILD | Implements IModelHubPort, orchestrates pipeline |
| ILLMPort | ✅ BUILD | Concierge's outbound LLM port (concierge.mmd L262) |
| ModelGatewayAdapter | ✅ BUILD | Concierge adapter: ILLMPort → IModelHubPort with LLM cascade |
| MockLLMAdapter | ✅ BUILD | Test adapter for ILLMPort (concierge.mmd ADAPTERS_TEST) |
| ProviderRegistry (manifest scanning + hot-reload) | ❌ DEFER | Not needed until multi-provider |
| CapabilityRouter (multi-provider) | ❌ DEFER | Single provider in M7 |
| ResponseCache | ❌ DEFER | Optimization |
| CircuitBreakerManager | ❌ DEFER | Full CB deferred; adapter has simple retry |
| RateLimiter | ❌ DEFER | Provider handles own limiting |
| CostTracker | ❌ DEFER | Monitoring |
| ProviderHealthMonitor | ❌ DEFER | Single provider |
| AuditLogger | ❌ DEFER | Observability milestone |
| NormalizationLayer | ❌ DEFER | Plugin handles own normalization for now |
| Manifest YAML system | ❌ DEFER | Until second provider |
| LLM Request Bus (async request-reply) | ❌ DEFER | In-process call sufficient |

### Epics

#### E7.1 — Build GeminiProviderPlugin

> Wraps the existing `GeminiConciergeAdapter` (664 lines of real Gemini API code) as an `IProviderPlugin`
> from M1's `k1/model_hub/plugins/base.py`. The adapter stays intact; the plugin translates between
> `NormalizedRequest` ↔ `ConciergeModelRequest` and `ConciergeModelResponse` ↔ `ProviderResponse`.

**Issue E7.1.1** — Create `k1/model_hub/plugins/gemini_plugin.py` — GeminiProviderPlugin

Class: `GeminiProviderPlugin` implements `IProviderPlugin`

Constructor: `__init__(self, api_key: str, model_overrides: dict[str, str] | None = None)`

- Internally creates `GeminiConciergeAdapter(api_key=api_key)` from `k1.concierge.llm.gemini_adapter`
- `model_overrides` allows per-capability model mapping (default: all → `gemini-2.5-flash-lite`)

Methods:

- `initialize(manifest: ProviderManifest) -> None` — no-op (adapter is ready at construction)
- `supports(capability: CapabilityType) -> bool` — returns `True` for CHAT, TOOL_CALL, STRUCTURED, REASON (the 4 POC-day-1 capabilities). `False` for EMBED, VISION, AUDIO_IN, etc.
- `execute(request: NormalizedRequest) -> ProviderResponse`:
  - `_normalized_to_poc(request: NormalizedRequest) -> ConciergeModelRequest` — translate:
    - `request.capability` → `Capability` enum mapping (M1 E1.4.1 reverse of hub→poc mapping)
    - `request.messages` → `ModelMessage` list
    - `request.system_prompt` → `ConciergeModelRequest.system_prompt`
    - `request.tools` → `ToolSchema` list (if TOOL_CALL)
    - `request.max_tokens/timeout_ms/temperature` → request fields
    - `request.consumer_id` → actor (parse `"concierge.front"` → `"front"`)
    - `request.model_id` → `model_hint`
    - `request.stream` → forced `False` for execute
  - Call `self._adapter.generate(poc_request)`
  - `_poc_to_provider_response(poc_resp: ConciergeModelResponse) -> ProviderResponse` — translate:
    - `.text` / `.tool_calls` / `.json_output` → `ProviderResponse.result`
    - `.tokens_in` / `.tokens_out` → `ProviderResponse.usage`
    - `.latency_ms` / `.model_id` / `.finish_reason` → metadata fields
- `stream_execute(request: NormalizedRequest) -> AsyncIterator[ProviderChunk]`:
  - Same `_normalized_to_poc()` translation with `stream` forced `True`
  - Call `self._adapter.generate_stream(poc_request)`
  - Map `StreamChunk` → `ProviderChunk` on each yield
- `estimate_tokens(messages: list[Message]) -> int` — rough estimate: `sum(len(m.content) for m in messages) // 4` (4 chars/token approximation)
- `health_check() -> ProviderHealth` — always `HEALTHY` (no circuit breaker in plugin itself)
- `close() -> None` — no-op (adapter has no persistent connections)

Touch point: NEW file `k1/model_hub/plugins/gemini_plugin.py` (~200 lines)
Depends on: M1 E1.3.1 (`plugins/base.py`), M5 (`k1/concierge/llm/gemini_adapter.py`)

**Issue E7.1.2** — Update `k1/model_hub/plugins/test_plugin.py` — align with GeminiProviderPlugin

Review M1's `TestProviderPlugin` to ensure it exercises the same `NormalizedRequest` → `ProviderResponse` contract.
Add: `set_execute_response()`, `set_stream_chunks()`, `set_health_status()`, `call_log` recording if not already present.

Touch point: EDIT `k1/model_hub/plugins/test_plugin.py` (~20 lines added)
Depends on: M1 E1.3.2

---

#### E7.2 — Build Model Selection Engine

> From .mmd: `ModelSelector` scores eligible providers by (cost 0.3, latency 0.25, preference 0.2,
> placement 0.15, health 0.1) and returns top-3 as a fallback chain. For M7 with a single provider,
> the selector is a thin wrapper that always returns GeminiProviderPlugin as rank-1, with configured
> fallback models.

**Issue E7.2.1** — Create `k1/model_hub/selection.py` — ModelSelector

Class: `ModelSelector`

Constructor: `__init__(self, plugins: dict[str, IProviderPlugin], config: SelectionConfig)`

Types:

- `SelectionConfig` dataclass — `default_model: str`, `model_map: dict[str, str]` (consumer_id → model_id), `fallback_chain: list[str]` (model_ids in priority order), `weights: ScoringWeights | None` (deferred, all 1.0 for now)
- `FallbackChain` dataclass — `models: list[str]`, `current_index: int`, `next() -> str | None`

Methods:

- `select(capability: CapabilityType, constraints: RequestConstraints) -> FallbackChain`:
  - If `constraints.model_preference` specified → use that model as rank-1
  - Else if `constraints.consumer_id` in `config.model_map` → use mapped model
  - Else → `config.default_model`
  - Append `config.fallback_chain` entries (excluding selected model) as rank-2, rank-3
  - Return `FallbackChain` with up to 3 models
- `get_plugin_for_model(model_id: str) -> IProviderPlugin | None` — lookup provider by model
  - For M7: single plugin handles all models (GeminiProviderPlugin routes via model_hint)

Configuration for POC migration (from `poc/k1_poc/llm/model_selection.py` + `defaults.yaml`):

```python
SelectionConfig(
    default_model="gemini-2.5-flash-lite",
    model_map={
        "concierge.front": "gemini-2.5-flash-lite",
        "concierge.back": "gemini-2.5-flash-lite",
    },
    fallback_chain=["gemini-2.5-flash", "gemini-2.5-pro"],
)
```

Touch point: NEW file `k1/model_hub/selection.py` (~120 lines)
Depends on: M1 E1.1.1 (types), M1 E1.3.1 (IProviderPlugin)

---

#### E7.3 — Build Budget Enforcer

> From .mmd invariant MH-07: "Budget enforcement MUST reject requests exceeding daily budget."
> Default: $5/day (from .mmd BudgetEnforcer spec). Tracks spend per `consumer_id`.
> In-memory tracking for M7 (persistent tracking deferred to CostTracker service).

**Issue E7.3.1** — Create `k1/model_hub/budget.py` — BudgetEnforcer

Class: `BudgetEnforcer`

Constructor: `__init__(self, daily_limit_usd: float = 5.0, per_consumer_limits: dict[str, float] | None = None)`

Types:

- `BudgetConfig` dataclass — `daily_limit_usd: float`, `per_consumer_limits: dict[str, float]`, `reset_hour_utc: int` (0 = midnight UTC)
- `BudgetCheckResult` dataclass — `allowed: bool`, `remaining_usd: float`, `reason: str | None`

Methods:

- `check(consumer_id: str, estimated_cost_usd: float) -> BudgetCheckResult`:
  - Track daily spend per consumer_id in `dict[str, float]`
  - Auto-reset when day changes (compare against `_current_day`)
  - If `daily_spend + estimated_cost > daily_limit` → reject with `BudgetCheckResult(allowed=False, ...)`
  - Else → allow
- `record_spend(consumer_id: str, actual_cost_usd: float) -> None`:
  - Called post-dispatch to record actual cost
  - Updates `_daily_spend[consumer_id]`
- `get_remaining(consumer_id: str) -> float` — query remaining budget
- `reset() -> None` — manual reset (for testing)

Cost estimation for Gemini (from POC defaults):

- Input: ~$0.000125/1K tokens for flash-lite
- Output: ~$0.000500/1K tokens for flash-lite
- Rough per-call estimate: `(prompt_tokens * 0.000125 + max_tokens * 0.000500) / 1000`

Touch point: NEW file `k1/model_hub/budget.py` (~100 lines)
Depends on: nothing (pure utility)

---

#### E7.4 — Build ModelHubService

> Core service implementing `IModelHubPort`. Orchestrates the pipeline:
> validate → budget check → select model → dispatch to plugin → fallback on failure → post-dispatch.
> This is the M7 deliverable that replaces `ModelHubPOCBridge`.

**Issue E7.4.1** — Create `k1/model_hub/service.py` — ModelHubService

Class: `ModelHubService` implements `IModelHubPort`

Constructor:

```python
__init__(
    self,
    plugins: dict[str, IProviderPlugin],   # provider_id → plugin instance
    selector: ModelSelector,
    budget: BudgetEnforcer,
)
```

Methods:

- `execute(request: HubRequest) -> HubResponse`:
  1. Validate: `request.capability` must be supported by at least one plugin
  2. Budget: `self._budget.check(request.constraints.consumer_id, self._estimate_cost(request))` → reject if not allowed
  3. Select: `self._selector.select(request.capability, request.constraints)` → `FallbackChain`
  4. Build `NormalizedRequest` from `HubRequest` (one-time translation)
  5. Dispatch loop (up to `len(fallback_chain)`):
     - Get plugin for current model: `self._selector.get_plugin_for_model(chain.current)`
     - Call `plugin.execute(normalized_request)` with `model_id` set
     - On success: build `HubResponse` from `ProviderResponse`, record spend, return
     - On failure (exception or error response): log warning, advance fallback chain, retry
  6. If all fallback attempts fail: raise `ModelHubExhaustedError`

- `stream_execute(request: HubRequest) -> AsyncIterator[HubChunk]`:
  - Same validate + budget + select steps
  - Dispatch: `plugin.stream_execute(normalized_request)`
  - Map `ProviderChunk` → `HubChunk` on each yield
  - Fallback: if first chunk fails → try next in chain (full restart, not mid-stream)

- `discover_capabilities() -> dict[CapabilityType, list[str]]`:
  - Aggregate `plugin.supports(cap)` across all plugins for each `CapabilityType`
  - Return: `{CHAT: ["gemini"], TOOL_CALL: ["gemini"], STRUCTURED: ["gemini"], REASON: ["gemini"]}`

- `discover_models(capability: CapabilityType | None = None) -> list[ModelInfo]`:
  - Return configured model list, optionally filtered by capability

- `health() -> HubHealthReport`:
  - Call `plugin.health_check()` for all plugins
  - Aggregate into `HubHealthReport`

Private helpers:

- `_hub_to_normalized(request: HubRequest, model_id: str) -> NormalizedRequest`:
  - Extract from `HubRequest`: messages, system_prompt, tools, constraints
  - Set `model_id` from fallback chain selection
  - Set `stream = False` (for execute) or `True` (for stream_execute)
  - Mapping: `HubRequest.payload` (ChatPayload/ToolCallPayload/etc.) → flattened `NormalizedRequest` fields
- `_provider_to_hub_response(provider_resp: ProviderResponse, request: HubRequest) -> HubResponse`:
  - Build `ResponseMetadata` from provider response
  - Build capability-specific `CapabilityResult` from provider result
  - Package into `HubResponse`
- `_estimate_cost(request: HubRequest) -> float`:
  - Rough: `request.constraints.max_tokens * 0.000500 / 1000` (output-side estimate)

Touch point: NEW file `k1/model_hub/service.py` (~300 lines)
Depends on: M1 E1.1 (types), M1 E1.2 (ports), M1 E1.3 (plugins), E7.1 (GeminiProviderPlugin), E7.2 (ModelSelector), E7.3 (BudgetEnforcer)

**Issue E7.4.2** — Create `k1/model_hub/errors.py` — Hub-specific exceptions

- `ModelHubError` — base exception
- `ModelHubExhaustedError(ModelHubError)` — all fallback attempts failed
- `BudgetExceededError(ModelHubError)` — daily budget exceeded
- `UnsupportedCapabilityError(ModelHubError)` — no plugin supports the requested capability

Touch point: NEW file `k1/model_hub/errors.py` (~30 lines)
Depends on: nothing

**Issue E7.4.3** — Update `k1/model_hub/__init__.py` — export service + errors

Add exports: `ModelHubService`, `ModelHubError`, `ModelHubExhaustedError`, `BudgetExceededError`, `UnsupportedCapabilityError`, `GeminiProviderPlugin`, `ModelSelector`, `SelectionConfig`, `BudgetEnforcer`, `BudgetConfig`

Touch point: EDIT `k1/model_hub/__init__.py`

---

#### E7.5 — Build ILLMPort + ModelGatewayAdapter

> Per `concierge.mmd` (line 262): the Concierge uses `ILLMPort` (outbound) with methods
> `execute(HubRequest) → HubResponse` and `stream_execute(HubRequest) → AsyncIterator[HubChunk]`.
> The production adapter is `ModelGatewayAdapter` (line 283) which routes to Model Hub
> via LLM Request Bus. For M7, the adapter calls `ModelHubService` directly (in-process).
>
> Note: `ILLMPort` is a SUBSET of `IModelHubPort` — no `discover_capabilities()`, `discover_models()`,
> or `health()`. It is the Concierge's **own** outbound LLM port; the Concierge doesn't need
> Model Hub management methods.

**Issue E7.5.1** — Create `k1/concierge/llm/llm_port.py` — ILLMPort protocol

From concierge.mmd line 262:

```python
@runtime_checkable
class ILLMPort(Protocol):
    def execute(self, request: HubRequest) -> HubResponse: ...
    async def stream_execute(self, request: HubRequest) -> AsyncIterator[HubChunk]: ...
```

Touch point: NEW file `k1/concierge/llm/llm_port.py` (~25 lines)
Depends on: M1 E1.1 (HubRequest, HubResponse, HubChunk from `k1.model_hub.types`)

**Issue E7.5.2** — Create `k1/concierge/llm/model_gateway_adapter.py` — ModelGatewayAdapter

From concierge.mmd line 283. Implements `ILLMPort`, delegates to `IModelHubPort`.

Class: `ModelGatewayAdapter` implements `ILLMPort`

Constructor: `__init__(self, hub: IModelHubPort, canned_responses: dict[CapabilityType, str] | None = None)`

Methods:

- `execute(request: HubRequest) -> HubResponse`:
  1. Tag: ensure `request.constraints.consumer_id` is set (from caller context)
  2. Try: `self._hub.execute(request)`
  3. LLM Cascade (from concierge.mmd):
     - L1 RETRY: on timeout or 5xx-equivalent → retry once with same request
     - L2 CB HALF-OPEN: (deferred — no CB in M7, just log warning)
     - L3 CANNED_RESPONSE: if all attempts fail → return canned response for capability
  4. Return `HubResponse`

- `stream_execute(request: HubRequest) -> AsyncIterator[HubChunk]`:
  1. Tag request
  2. Try: yield from `self._hub.stream_execute(request)`
  3. On failure: yield single `HubChunk` with canned response text, then done chunk

Canned responses (degraded mode, from concierge.mmd LLM_CASCADE L3):

- CHAT: `"I'm having trouble thinking right now. Could you try again in a moment?"`
- TOOL_CALL: return empty tool_calls (caller handles via FallbackChain in react loop)
- STRUCTURED: return `{"error": "service_degraded"}` as json_output

Touch point: NEW file `k1/concierge/llm/model_gateway_adapter.py` (~120 lines)
Depends on: E7.5.1 (ILLMPort), M1 E1.2.1 (IModelHubPort), M1 E1.1.1 (types)

**Issue E7.5.3** — Create `k1/concierge/llm/mock_llm_adapter.py` — MockLLMAdapter (test)

From concierge.mmd ADAPTERS_TEST section. Implements `ILLMPort` for tests.

- Scripted responses per capability
- Records all calls for assertions
- `set_execute_response(capability, response)`, `set_stream_chunks(capability, chunks)`
- `call_log: list[HubRequest]` — records all requests received
- Note: This replaces the M1 `TestModelHubBridge` for the Concierge's test wiring

Touch point: NEW file `k1/concierge/llm/mock_llm_adapter.py` (~80 lines)
Depends on: E7.5.1 (ILLMPort)

---

#### E7.6 — Wire Bootstrap + Migrate Callers to ILLMPort

> Replace `ModelHubPOCBridge` with `ModelHubService` + `ModelGatewayAdapter` chain.
> Migrate callers from `IModelHubPort` → `ILLMPort` (the Concierge's own outbound port).

**Issue E7.6.1** — Migrate `k1/concierge/react/loop.py` — IModelHubPort → ILLMPort

Changes:

- Import: `from k1.model_hub.ports import IModelHubPort` → `from k1.concierge.llm.llm_port import ILLMPort`
- `_streaming_generate()` signature: `model: IModelHubPort` → `model: ILLMPort`
- `react_loop()` signature: `model: IModelHubPort` → `model: ILLMPort`
- Method calls unchanged: `.execute()` and `.stream_execute()` have same signatures on both protocols
- Return types unchanged: `HubResponse`, `HubChunk` stay the same

Touch point: EDIT `k1/concierge/react/loop.py` — imports, 2 function signatures
Depends on: E7.5.1

**Issue E7.6.2** — Migrate `k1/concierge/actors/front.py` — IModelHubPort → ILLMPort

Changes:

- Import: `from k1.model_hub.ports import IModelHubPort` → `from k1.concierge.llm.llm_port import ILLMPort`
- `front_handler()` signature: `model: IModelHubPort` → `model: ILLMPort`
- No internal changes (passes `model` to `react_loop()`)

Touch point: EDIT `k1/concierge/actors/front.py` — import, 1 signature
Depends on: E7.5.1

**Issue E7.6.3** — Migrate `k1/concierge/actors/back.py` — IModelHubPort → ILLMPort

Changes:

- Import: `from k1.model_hub.ports import IModelHubPort` → `from k1.concierge.llm.llm_port import ILLMPort`
- 3 handler signatures: `model: IModelHubPort` → `model: ILLMPort`
- No internal changes (all handlers pass `model` to `react_loop()`)

Touch point: EDIT `k1/concierge/actors/back.py` — import, 3 signatures
Depends on: E7.5.1

**Issue E7.6.4** — Rewrite `k1/concierge/kernel/bootstrap.py` `_create_model()`

Current (post-M5): returns `ModelHubPOCBridge(GeminiConciergeAdapter(api_key=...))`
After M7: builds full `ModelHubService` → `ModelGatewayAdapter` chain

Changes to `_create_model()`:

```python
# LIVE mode:
gemini_plugin = GeminiProviderPlugin(api_key=api_key)
selector = ModelSelector(
    plugins={"gemini": gemini_plugin},
    config=SelectionConfig(
        default_model="gemini-2.5-flash-lite",
        model_map={
            "concierge.front": "gemini-2.5-flash-lite",
            "concierge.back": "gemini-2.5-flash-lite",
        },
        fallback_chain=["gemini-2.5-flash", "gemini-2.5-pro"],
    ),
)
budget = BudgetEnforcer(daily_limit_usd=config.get("model_hub.budget_daily_usd", 5.0))
hub = ModelHubService(plugins={"gemini": gemini_plugin}, selector=selector, budget=budget)
return ModelGatewayAdapter(hub=hub)

# TEST mode:
test_plugin = TestProviderPlugin()
selector = ModelSelector(
    plugins={"test": test_plugin},
    config=SelectionConfig(
        default_model="test-model",
        model_map={},
        fallback_chain=[],
    ),
)
budget = BudgetEnforcer(daily_limit_usd=999.0)  # no budget limit in tests
hub = ModelHubService(plugins={"test": test_plugin}, selector=selector, budget=budget)
return ModelGatewayAdapter(hub=hub)
```

Imports to add:

- `from k1.model_hub.plugins.gemini_plugin import GeminiProviderPlugin`
- `from k1.model_hub.service import ModelHubService`
- `from k1.model_hub.selection import ModelSelector, SelectionConfig`
- `from k1.model_hub.budget import BudgetEnforcer`
- `from k1.concierge.llm.model_gateway_adapter import ModelGatewayAdapter`

Imports to remove:

- `from k1.concierge.llm.model_hub_bridge import ModelHubPOCBridge`

Return type annotation: `-> ILLMPort` (was `-> IModelHubPort`)

Touch point: EDIT `k1/concierge/kernel/bootstrap.py` — imports, `_create_model()` (~35 lines rewritten), `KernelRuntime.model` type
Depends on: E7.1, E7.2, E7.3, E7.4, E7.5

**Issue E7.6.5** — Delete `k1/concierge/llm/model_hub_bridge.py` — remove POC bridge

After E7.6.4, `ModelHubPOCBridge` is no longer referenced anywhere.

Verification before delete:

- `grep -r "ModelHubPOCBridge" k1/ tests/` → must return 0 results
- `grep -r "model_hub_bridge" k1/ tests/` → must return 0 results (no import)

Touch point: DELETE `k1/concierge/llm/model_hub_bridge.py`
Touch point: DELETE `k1/concierge/llm/test_model_hub_bridge.py` (M1's test bridge also unused)

**Issue E7.6.6** — Update `k1/concierge/llm/__init__.py` — fix exports

Remove exports for `ModelHubPOCBridge`, `TestModelHubBridge`, `IConciergeModelPort`.
Add exports for `ILLMPort`, `ModelGatewayAdapter`, `MockLLMAdapter`.

Touch point: EDIT `k1/concierge/llm/__init__.py`

---

#### E7.7 — Unit Tests

**Issue E7.7.1** — Create `tests/k1/model_hub/test_gemini_plugin.py`

Tests for `GeminiProviderPlugin`:

- `supports()` returns True for CHAT, TOOL_CALL, STRUCTURED, REASON; False for EMBED, VISION
- `execute()` translates NormalizedRequest → ConciergeModelRequest correctly (each field mapping)
- `execute()` translates ConciergeModelResponse → ProviderResponse correctly
- `stream_execute()` yields ProviderChunk from StreamChunk
- `estimate_tokens()` returns reasonable estimate
- `health_check()` returns HEALTHY
- Error propagation: adapter exception → plugin raises

Touch point: NEW file `tests/k1/model_hub/test_gemini_plugin.py` (~25 tests)

**Issue E7.7.2** — Create `tests/k1/model_hub/test_selection.py`

Tests for `ModelSelector`:

- Default selection: no preference → default_model
- Consumer-id mapping: `"concierge.front"` → mapped model
- Model preference override: `constraints.model_preference` → uses that model
- Fallback chain: returns 3 models in priority order
- Fallback chain excludes selected model from alternatives
- Empty fallback chain → single model, no alternatives

Touch point: NEW file `tests/k1/model_hub/test_selection.py` (~15 tests)

**Issue E7.7.3** — Create `tests/k1/model_hub/test_budget.py`

Tests for `BudgetEnforcer`:

- Under budget: `check()` → `allowed=True`
- Over budget: `check()` → `allowed=False`, reason set
- `record_spend()` accumulates correctly
- Day rollover resets spend
- Per-consumer limit vs global limit
- `get_remaining()` reflects recorded spend
- `reset()` clears all state

Touch point: NEW file `tests/k1/model_hub/test_budget.py` (~15 tests)

**Issue E7.7.4** — Create `tests/k1/model_hub/test_service.py`

Tests for `ModelHubService`:

- Happy path: `execute()` → selects model → dispatches to plugin → returns HubResponse
- Happy path: `stream_execute()` → yields HubChunks
- Budget rejection: over-budget request → `BudgetExceededError`
- Unsupported capability: no plugin supports → `UnsupportedCapabilityError`
- Fallback: first model fails → second model succeeds → HubResponse from fallback
- Fallback exhausted: all models fail → `ModelHubExhaustedError`
- `discover_capabilities()` → aggregated capability map
- `discover_models()` → model list from config
- `health()` → aggregated health from plugins
- Post-dispatch: spend recorded in BudgetEnforcer

Touch point: NEW file `tests/k1/model_hub/test_service.py` (~30 tests)

**Issue E7.7.5** — Create `tests/k1/concierge/test_model_gateway_adapter.py`

Tests for `ModelGatewayAdapter`:

- Happy path: delegates `execute()` to hub
- Happy path: delegates `stream_execute()` to hub
- LLM cascade L1: first attempt timeout → retry once → succeed
- LLM cascade L3: all attempts fail → canned response returned
- Canned response per capability type (CHAT, TOOL_CALL, STRUCTURED)
- Stream failure → single canned chunk yielded

Touch point: NEW file `tests/k1/concierge/test_model_gateway_adapter.py` (~15 tests)

**Issue E7.7.6** — Create `tests/k1/concierge/test_mock_llm_adapter.py`

Tests for `MockLLMAdapter`:

- `set_execute_response()` → returns scripted response
- `set_stream_chunks()` → yields scripted chunks
- `call_log` records all requests
- Satisfies `ILLMPort` (`isinstance` check)

Touch point: NEW file `tests/k1/concierge/test_mock_llm_adapter.py` (~10 tests)

---

#### E7.8 — Integration Tests + Cleanup

**Issue E7.8.1** — E2E smoke test: HubRequest → ModelHubService → GeminiProviderPlugin → HubResponse

Create `tests/k1/model_hub/test_hub_e2e.py`:

- Wire `ModelHubService` with `TestProviderPlugin` (not Gemini — fully in-memory)
- Wrap with `ModelGatewayAdapter`
- Execute CHAT request → verify HubResponse structure
- Execute TOOL_CALL request → verify tool_calls in result
- Execute STRUCTURED request → verify json_output
- Stream CHAT request → verify HubChunk sequence
- Fallback chain E2E: first plugin raises, second succeeds

Touch point: NEW file `tests/k1/model_hub/test_hub_e2e.py` (~15 tests)

**Issue E7.8.2** — Run full Concierge test suite from new wiring

- Command: `python -m pytest tests/k1/concierge/ --tb=short -q`
- Gate: ALL existing tests pass. The migration from `IModelHubPort` → `ILLMPort` and from `ModelHubPOCBridge` → `ModelGatewayAdapter(ModelHubService)` must be transparent.
- Focus: tests exercising react loop (which constructs `HubRequest` and reads `HubResponse`)

**Issue E7.8.3** — Run new Model Hub test suite

- Command: `python -m pytest tests/k1/model_hub/ --tb=short -q`
- Gate: ALL new tests pass (~110 tests from E7.7)

**Issue E7.8.4** — Cleanup dead POC LLM code in `k1/concierge/llm/`

After bridge removal (E7.6.5), review `k1/concierge/llm/`:

| File | Decision | Reason |
|---|---|---|
| `model_selection.py` | Conditional DELETE | `ModelSelector` in `k1/model_hub/selection.py` replaces it. If no other consumer → delete. Verify: `grep -r "from k1.concierge.llm.model_selection" k1/ tests/` → 0 |
| `ports.py` (old `IConciergeModelPort`) | Conditional DELETE | Callers migrated to `ILLMPort`. If no other consumer → delete. Verify: `grep -r "from k1.concierge.llm.ports" k1/ tests/` → 0 |
| `types.py` (ConciergeModelRequest, etc.) | **KEEP** | Still needed by `GeminiProviderPlugin` which wraps `GeminiConciergeAdapter` using these types |
| `gemini_adapter.py` | **KEEP** | Still needed by `GeminiProviderPlugin` (wraps it internally) |
| `test_adapter.py` | **KEEP** | Still needed by `TestProviderPlugin` if it wraps this; else delete |
| `validator.py` | **KEEP** | Still needed by react loop (validates HubResponse after M1 E1.6) |

Touch point: Conditional DELETE of 1-2 files in `k1/concierge/llm/`

**Issue E7.8.5** — Git tag `m7-model-hub-wired`

- Tag commit after all tests green
- Gate metrics:

| Metric | Value |
|---|---|
| New K1 Model Hub files | 5 (`service.py`, `selection.py`, `budget.py`, `errors.py`, `gemini_plugin.py`) |
| New Concierge adapter files | 3 (`llm_port.py`, `model_gateway_adapter.py`, `mock_llm_adapter.py`) |
| Deleted bridge files | 2-4 (`model_hub_bridge.py`, `test_model_hub_bridge.py`, + conditionally `model_selection.py`, `ports.py`) |
| New test files | 7 |
| New tests | ~110 |
| Callers migrated IModelHubPort → ILLMPort | 4 (`loop.py`, `front.py`, `back.py`, `bootstrap.py`) |
| POC bridge removed | `ModelHubPOCBridge`, `TestModelHubBridge` |
| Production Model Hub service | `ModelHubService` → `GeminiProviderPlugin` → `GeminiConciergeAdapter` |

---

## M8 — K1 Orchestrator Wiring

> K1 Orchestrator is **FULLY IMPLEMENTED** — 66 Python files, ~14,500 lines across 6 subdirectories.
> Central service: `OrchestratorService` (2,257 lines), `DAGExecutor` (1,289 lines), `StepRunner` (362),
> `ConstraintResolver` (708), `ErrorRouter` (208), complete workflow subsystem, MCP connectors.
> 9 hexagonal ports, 10 production adapters, 7 test adapters, 4 factory construction modes.
>
> The POC uses `OrchestratorStub` (185 lines, MEDIUM-only, 1-2 Fabric calls) with 3 bootstrap
> adapters (`_FabricGatewayAdapter`, `_StateReadAdapter`, `_DeltaEmitAdapter`). After M5,
> callers are at `k1/concierge/`. The POC orchestrator stays at `poc/k1_poc/orchestrator/`
> — it was NOT copied because the K1 Orchestrator is a separate K1 module.
>
> This milestone **replaces `OrchestratorStub`** with the real `OrchestratorService` via
> `OrchestratorFactory.create_for_testing()` + real adapter overrides, builds the Concierge-side
> `IDispatchPort` + `FabricOrchestratorAdapter` from `concierge.mmd` (L264, L285), and wires
> the MEDIUM tier E2E path: FSM DISPATCHING → dispatch_envelope → Orchestrator mailbox →
> Fabric → AggregatedResult → DeltaAggregator → DELIVERING.

**K1 Orchestrator status**: FULLY IMPLEMENTED (66 .py, ~14,500 lines)
**K1 Orchestrator factory**: `OrchestratorFactory` — `create_standalone()`, `create_for_testing(overrides)`, `create_with_ports(**ports)`, `create_production(config, **ports)`
**K1 Orchestrator key types** (`k1/orchestrator/types.py`, 1,197 lines): `TaskEnvelope` (frozen, 10 fields: intent, trace_id, caller_id, envelope_id, context, tier, capabilities, params, constraints, timeout_ms), `AggregatedResult` (factory methods: `.from_medium()`, `.from_dag()`), `StepResult`, `ProcessingContext`, `CommittedPlan`, `PlanStep`, enums (`StepStatus`, `TriggerType`, `ProcessResult`, `ErrorSeverity`)
**K1 Orchestrator 9 ports** (`k1/orchestrator/ports/`): `IMailboxPort`, `IFabricGatewayPort`, `IPlannerPort`, `IStateReadPort`, `IDeltaEmitPort`, `IBridgeWritePort`, `IEventSubscriptionPort`, `IWorkflowStoragePort`, `IAdminPort`
**K1 Orchestrator 10+7 adapters** (`k1/orchestrator/adapters/`): production (`MailboxAdapter`, `FabricGatewayAdapter`, `PlannerAdapter`, `StateReadAdapter`, `DeltaEmitAdapter`, `BridgeWriteAdapter`, `EventSubscriptionAdapter`, `WorkflowStorageAdapter`, `AdminHttpAdapter`) + 7 test adapters
**POC Orchestrator status**: `OrchestratorStub` (185 lines), `route_task()` (216 lines), `degradation.py` (123 lines), POC-local types (352 lines), POC-local ports (170 lines)
**Concierge .mmd ref**: `IDispatchPort` (L264) — `dispatch_direct(CapReq)→CapResult`, `dispatch_envelope(TaskEnv)→void`; `FabricOrchestratorAdapter` (L285) — routes by tier, CB_ORCHESTRATOR + CB_PLANNER + CB_FABRIC + CB_MCP, tier degradation HIGH→MED→LOW→canned
**Bootstrap status (post-M5)**: `_create_model()` returns via ILLMPort (M7), `FabricPOCBridge` replaced by real `Fabric` (M6), `OrchestratorStub` still wired with POC `_FabricGatewayAdapter`/`_StateReadAdapter`/`_DeltaEmitAdapter`

### Architecture: What M8 Builds

```text
┌──────────────────────── k1/concierge/ ─────────────────────────┐
│                                                                  │
│  FSM DISPATCHING                                                 │
│   ├── LOW:  react_loop → ILLMPort → tool_call →                 │
│   │         IDispatchPort.dispatch_direct(CapReq) → Fabric      │
│   └── MED/HIGH: route_task() → TaskEnvelope →                   │
│         IDispatchPort.dispatch_envelope(TaskEnv) → [fire&forget] │
│                │                                                 │
│  FabricOrchestratorAdapter (IDispatchPort impl)                  │
│   ├── dispatch_direct() → Fabric.execute() directly [LOW]       │
│   ├── dispatch_envelope() → Orchestrator mailbox [MED/HIGH]     │
│   └── tier degradation: HIGH→MED→LOW→canned                    │
│                │                                                 │
│  MockDispatchAdapter (IDispatchPort test impl)                   │
│   └── captures envelopes + requests for assertions              │
│                                                                  │
└────────────────│─────────────────────────────────────────────────┘
                 │ (in-process enqueue to mailbox)
                 ▼
┌──────────────────────── k1/orchestrator/ ────────────────────────┐
│                                                                   │
│  OrchestratorService._mailbox_loop()                              │
│   → dequeue TaskEnvelope                                          │
│   → route_task(envelope) [MEDIUM or HIGH]                         │
│       │                                                           │
│       ├── MEDIUM: dispatch_medium(envelope)                       │
│       │   → ConstraintResolver.resolve()                          │
│       │   → StepRunner.run() × 1-2                               │
│       │   → FabricGatewayAdapter.execute(CapReq) → Fabric         │
│       │   → AggregatedResult.from_medium(step_results)            │
│       │                                                           │
│       └── HIGH: dispatch_high(envelope) [needs Planner — M9]     │
│           → MockPlannerAdapter (returns mock plan for now)         │
│           → DAGExecutor.execute_plan(committed_plan)              │
│                                                                   │
│  → IDeltaEmitPort.emit("k1.orchestration.dag.completed.v1",      │
│                         AggregatedResult)                         │
│                                                                   │
└──────────────────│────────────────────────────────────────────────┘
                   │ (K1 bus delta lane)
                   ▼
┌──────────────────────── k1/concierge/ ─────────────────────────┐
│                                                                  │
│  DeltaAggregator → "k1.orchestration.dag.completed.v1"          │
│   → FSM COMPANIONING → DELIVERING                               │
│   → Tool Result Buffer → ILLMPort → final response              │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

### Type Bridging: POC TaskEnvelope → K1 TaskEnvelope

| POC Field (`poc.k1_poc.orchestrator.types`) | K1 Field (`k1.orchestrator.types`) | Translation |
|---|---|---|
| `intent: str` | `intent: str` | Direct copy |
| `task_id: str` | `envelope_id: str` | Rename (K1 auto-generates if empty) |
| `context: dict` | `context: dict` | Direct copy |
| `tier: ComplexityTier` (enum) | `tier: str` (`"MEDIUM"` or `"HIGH"`) | `tier.value` (ComplexityTier → str) |
| `budget: Budget` (max_fabric_calls, max_planner_tokens, timeout_ms) | `timeout_ms: int` + `constraints: dict` | `budget.timeout_ms` → `timeout_ms`, budget fields → `constraints` |
| `session_id: str` | `caller_id: str` | Repurpose (K1 uses caller_id for routing) |
| `trace_id: str` | `trace_id: str` | Direct copy |
| *(not in POC)* | `capabilities: list[str]` | **NEW** — must be populated from intent/tool resolution |
| *(not in POC)* | `params: dict[str, dict]` | **NEW** — per-capability params |

### What Gets Built vs Deferred

| Component | M8 Scope | Notes |
|---|---|---|
| IDispatchPort (concierge port) | ✅ BUILD | New Concierge port per concierge.mmd L264 |
| FabricOrchestratorAdapter | ✅ BUILD | Concierge adapter: IDispatchPort → Fabric (LOW) + Orchestrator mailbox (MED/HIGH) |
| MockDispatchAdapter | ✅ BUILD | Test adapter for IDispatchPort per concierge.mmd ADAPTERS_TEST |
| OrchestratorService wiring | ✅ WIRE | Via `OrchestratorFactory.create_for_testing()` + real adapter overrides |
| K1 FabricGatewayAdapter injection | ✅ WIRE | Real K1 `FabricGatewayAdapter(fabric)` replaces POC `_FabricGatewayAdapter` |
| K1 DeltaEmitAdapter injection | ✅ WIRE | Real K1 `DeltaEmitAdapter(bus)` replaces POC `_DeltaEmitAdapter` |
| K1 EventSubscriptionAdapter injection | ✅ WIRE | Real K1 `EventSubscriptionAdapter(bus)` for orchestrator event subscriptions |
| K1 MailboxAdapter injection | ✅ WIRE | Real K1 `MailboxAdapter` for WFQ priority mailbox |
| route_task() migration | ✅ MIGRATE | POC `route_task()` → produce K1 `TaskEnvelope` instead of POC `TaskEnvelope` |
| Bootstrap rewrite | ✅ REWRITE | Replace `OrchestratorStub` creation with `OrchestratorFactory` wiring |
| FSM result flow integration | ✅ WIRE | K1 `AggregatedResult` from bus → DeltaAggregator → FSM DELIVERING |
| HIGH tier (Planner integration) | ⚠️ PARTIAL | Wire `MockPlannerAdapter` — real Planner is M9 |
| Workflow subsystem | ❌ DEFER | Fully built but needs real `IWorkflowStoragePort` + Planner |
| MCP Connectors | ❌ DEFER | Fully built but no MCP servers in POC yet |
| Admin API | ❌ DEFER | Not needed for POC |
| Bridge writes (K0 WAL) | ❌ DEFER | Use `MockBridgeAdapter` (no real K0 Bridge yet) |
| Crash recovery | ❌ DEFER | Needs WAL infrastructure |
| Tier degradation cascade (full CB) | ⚠️ SIMPLIFIED | FabricOrchestratorAdapter implements simple retry; full CB deferred |

### Key Invariants Verified (from orchestrator.mmd)

| ID | Invariant | How M8 Satisfies |
|---|---|---|
| ORCH-01 | Orchestrator NEVER writes SessionState | `OrchestratorService` has no `IStateWritePort` — enforced structurally |
| ORCH-02 | Orchestrator makes NO LLM calls | No `ILLMPort` — enforced structurally |
| ORCH-04 | Every step goes through Fabric | `StepRunner` → `IFabricGatewayPort.execute()` → real `Fabric` |
| ORCH-10 | MEDIUM: max 2 Fabric calls | `TaskEnvelope.__post_init__` validates `len(capabilities) <= 2` |
| ORCH-11 | HIGH: requires CommittedPlan | `dispatch_high()` calls `IPlannerPort.request_plan()` first |

### Epics

#### E8.1 — Build IDispatchPort + Concierge Adapters

> Per `concierge.mmd` (L264): `IDispatchPort` is the Concierge's outbound dispatch port.
> `FabricOrchestratorAdapter` (L285) is the production adapter that routes by tier:
> LOW → Fabric directly, MED/HIGH → Orchestrator mailbox.
> `MockDispatchAdapter` is the test adapter that captures dispatches for assertions.

**Issue E8.1.1** — Create `k1/concierge/dispatch/__init__.py` + `ports.py` — IDispatchPort protocol

From concierge.mmd L264:

```python
@runtime_checkable
class IDispatchPort(Protocol):
    async def dispatch_direct(
        self, request: CapabilityRequest
    ) -> CapabilityResult:
        """LOW tier: execute capability directly via Fabric (bypass Orchestrator)."""
        ...

    async def dispatch_envelope(
        self, envelope: TaskEnvelope
    ) -> None:
        """MED/HIGH tier: fire-and-forget enqueue to Orchestrator mailbox."""
        ...

    async def cancel_dispatch(
        self, envelope_id: str
    ) -> bool:
        """Cancel an in-flight envelope. Returns True if cancelled."""
        ...
```

Types used:

- `CapabilityRequest`, `CapabilityResult` from `k1.fabric.types`
- `TaskEnvelope` from `k1.orchestrator.types`

Touch point: NEW file `k1/concierge/dispatch/__init__.py` (empty) + NEW file `k1/concierge/dispatch/ports.py` (~40 lines)
Depends on: `k1.fabric.types` (M2/M6), `k1.orchestrator.types` (existing)

**Issue E8.1.2** — Create `k1/concierge/dispatch/fabric_orchestrator_adapter.py` — FabricOrchestratorAdapter

From concierge.mmd L285 + concierge.md L5443-5530. Implements `IDispatchPort`.

Class: `FabricOrchestratorAdapter`

Constructor:

```python
__init__(
    self,
    fabric: Fabric,                    # real K1 Fabric (from M6)
    orchestrator_mailbox: IMailboxPort, # Orchestrator's WFQ mailbox
)
```

Methods:

- `dispatch_direct(request: CapabilityRequest) -> CapabilityResult`:
  - LOW tier: call `self._fabric.execute(request)` directly
  - Retry once on timeout/error (L1 of concierge.mmd LLM_CASCADE pattern)
  - On all attempts failed: return `CapabilityResult.failure_result(...)` with error detail

- `dispatch_envelope(envelope: TaskEnvelope) -> None`:
  - MED/HIGH tier: `self._orchestrator_mailbox.enqueue(envelope, priority="INTERACTIVE")`
  - Fire-and-forget: returns immediately after enqueue
  - Log: `"Dispatched envelope=%s tier=%s to orchestrator mailbox", envelope.envelope_id, envelope.tier`

- `cancel_dispatch(envelope_id: str) -> bool`:
  - Attempt to remove from mailbox: `self._orchestrator_mailbox.cancel(envelope_id)`
  - Return True if found and cancelled, False if already processing

Tier degradation (simplified for M8, full CB deferred):

- On `dispatch_envelope` failure (mailbox full/unavailable):
  - Log warning
  - Degrade MEDIUM → execute capabilities directly via `dispatch_direct()` sequentially
  - Degrade HIGH → degrade to MEDIUM path (ignore Planner)

Touch point: NEW file `k1/concierge/dispatch/fabric_orchestrator_adapter.py` (~150 lines)
Depends on: E8.1.1 (IDispatchPort), M6 (real Fabric), K1 `IMailboxPort`

**Issue E8.1.3** — Create `k1/concierge/dispatch/mock_dispatch_adapter.py` — MockDispatchAdapter

From concierge.mmd ADAPTERS_TEST (`ADAPT_TEST_DISPATCH["MockDispatchAdapter: Captures envelopes + requests"]`):

- `MockDispatchAdapter` implements `IDispatchPort`
- `dispatched_requests: list[CapabilityRequest]` — captures dispatch_direct calls
- `dispatched_envelopes: list[TaskEnvelope]` — captures dispatch_envelope calls
- `set_direct_result(result: CapabilityResult)` — scripted response for dispatch_direct
- `set_direct_results(results: list[CapabilityResult])` — response sequence
- `cancel_log: list[str]` — captures cancel_dispatch calls

Touch point: NEW file `k1/concierge/dispatch/mock_dispatch_adapter.py` (~80 lines)
Depends on: E8.1.1

---

#### E8.2 — Wire OrchestratorService via Factory

> Replace POC `OrchestratorStub` with real K1 `OrchestratorService`.
> Use `OrchestratorFactory.create_for_testing(overrides={...})` with real adapters for
> `fabric`, `delta`, `event`, `mailbox` and mock adapters for deferred ports
> (`planner`, `bridge`, `storage`).

**Issue E8.2.1** — Create `k1/concierge/dispatch/orchestrator_wiring.py` — orchestrator factory helper

Helper function that creates and configures the `OrchestratorService` with appropriate adapters:

```python
async def create_concierge_orchestrator(
    *,
    fabric: Fabric,
    bus: Any,
    session_state: Any,
    config: dict | None = None,
) -> tuple[OrchestratorService, IMailboxPort]:
    """Create OrchestratorService wired for Concierge use.

    Returns (orchestrator, mailbox) so FabricOrchestratorAdapter can reference the mailbox.
    """
```

Adapter wiring:

| Port Key | Adapter | Source |
|---|---|---|
| `fabric` | `FabricGatewayAdapter(fabric)` | K1 `k1/orchestrator/adapters/fabric_gateway_adapter.py` — wraps real `Fabric` |
| `mailbox` | `MailboxAdapter()` | K1 `k1/orchestrator/adapters/mailbox_adapter.py` — WFQ priority queue |
| `delta` | `DeltaEmitAdapter(bus)` | K1 `k1/orchestrator/adapters/delta_emit_adapter.py` — emits via K1 bus |
| `event` | `EventSubscriptionAdapter(bus)` | K1 `k1/orchestrator/adapters/event_subscription_adapter.py` — subscribes via K1 bus |
| `state` | `StateReadAdapter(session_state)` | K1 `k1/orchestrator/adapters/state_read_adapter.py` — reads SessionState |
| `planner` | *(test adapter from factory)* | Mock — real Planner is M9 |
| `bridge` | *(test adapter from factory)* | Mock — real K0 Bridge deferred |
| `storage` | *(test adapter from factory)* | Mock — workflow storage deferred |

Implementation:

```python
from k1.orchestrator.factory import OrchestratorFactory
from k1.orchestrator.adapters.fabric_gateway_adapter import FabricGatewayAdapter
from k1.orchestrator.adapters.mailbox_adapter import MailboxAdapter
from k1.orchestrator.adapters.delta_emit_adapter import DeltaEmitAdapter
from k1.orchestrator.adapters.event_subscription_adapter import EventSubscriptionAdapter
from k1.orchestrator.adapters.state_read_adapter import StateReadAdapter

mailbox = MailboxAdapter()
orchestrator = await OrchestratorFactory.create_for_testing(
    overrides={
        "fabric": FabricGatewayAdapter(fabric),
        "mailbox": mailbox,
        "delta": DeltaEmitAdapter(bus),
        "event": EventSubscriptionAdapter(bus),
        "state": StateReadAdapter(session_state),
    },
)
await orchestrator.init()
return orchestrator, mailbox
```

Touch point: NEW file `k1/concierge/dispatch/orchestrator_wiring.py` (~80 lines)
Depends on: K1 Orchestrator factory + adapters (all existing), M6 (Fabric), M3 (bus)

---

#### E8.3 — Migrate route_task() to Produce K1 TaskEnvelope

> POC `route_task()` in `k1/concierge/orchestrator/routing.py` (post-M5 copy) creates
> POC `TaskEnvelope`. Must produce K1 `TaskEnvelope` from `k1.orchestrator.types` instead.
>
> NOTE: The POC orchestrator was NOT copied to `k1/concierge/` at M5 because it's a separate
> K1 module. The routing logic still lives at `poc/k1_poc/orchestrator/routing.py` and is called
> from the POC FSM/actors. After M5, the concierge callers are at `k1/concierge/` but they
> import routing from `poc.k1_poc.orchestrator.routing`. This must be resolved.

**Issue E8.3.1** — Create `k1/concierge/dispatch/routing.py` — migrated route_task()

Port `poc/k1_poc/orchestrator/routing.py` (216 lines) to `k1/concierge/dispatch/routing.py`.

Key changes:

- Replace `from poc.k1_poc.orchestrator.types import Budget, TaskEnvelope` → `from k1.orchestrator.types import TaskEnvelope`
- Replace `from poc.k1_poc.task.complexity import ComplexityTier` → `from k1.concierge.task.complexity import ComplexityTier`
- `_route_medium_sync()`: Build K1 `TaskEnvelope` instead of POC `TaskEnvelope`:

  ```python
  envelope = TaskEnvelope(
      intent=intent,
      trace_id=trace_id,
      caller_id=f"concierge.{session_id}",
      envelope_id=task.task_id,
      context=task.context_snapshot or {},
      tier="MEDIUM",
      capabilities=_extract_capabilities(task),  # NEW: extract from intent/tools
      params=_extract_params(task),               # NEW: per-capability params
      timeout_ms=budget_timeout_ms,
  )
  ```

- `_route_high_sync()`: Same K1 `TaskEnvelope` with `tier="HIGH"`, empty `capabilities` (Planner decides)
- `_extract_capabilities(task: TaskDispatch) -> list[str]`: derive capability names from task intents/tools
  - If task has explicit tool names → use those as capabilities
  - Else → infer from intent classification (e.g., "schedule meeting" → `["tool.calendar.create"]`)
  - Fallback: `[f"tool.{intent}"]` for unknown
- `_extract_params(task: TaskDispatch) -> dict[str, dict]`: derive per-capability params
  - Key: capability_name, value: params dict from task context

Touch point: NEW file `k1/concierge/dispatch/routing.py` (~200 lines)
Depends on: `k1.orchestrator.types.TaskEnvelope`, `k1.concierge.task.complexity.ComplexityTier`

**Issue E8.3.2** — Migrate callers of `poc.k1_poc.orchestrator.routing` → `k1.concierge.dispatch.routing`

Search for all imports of POC routing in `k1/concierge/`:

- `from poc.k1_poc.orchestrator.routing import route_task` → `from k1.concierge.dispatch.routing import route_task`
- `from poc.k1_poc.orchestrator.routing import route_task_sync` → `from k1.concierge.dispatch.routing import route_task_sync`

Callers to find and update:

- FSM handlers in `k1/concierge/fsm/` that call `route_task()` or `route_task_sync()`
- Front actor that may reference routing
- Bootstrap if it references routing

Touch point: EDIT 2-4 files in `k1/concierge/` — import path changes
Depends on: E8.3.1

---

#### E8.4 — Rewrite Bootstrap Orchestrator Wiring

> Replace the POC bootstrap section that creates `OrchestratorStub` with real
> `OrchestratorService` + `FabricOrchestratorAdapter` wiring.

**Issue E8.4.1** — Rewrite `k1/concierge/kernel/bootstrap.py` — orchestrator section

Current code (post-M5, lines ~318-328):

```python
if cfg.enable_orchestrator:
    from poc.k1_poc.orchestrator.stub import OrchestratorStub  # DEAD import after M8
    runtime.orchestrator = OrchestratorStub(
        fabric_gateway=_FabricGatewayAdapter(capability_registry),
        state_read=_StateReadAdapter(session_state),
        delta_emit=_DeltaEmitAdapter(...),
    )
    if hasattr(runtime.fsm, "set_orchestrator"):
        runtime.fsm.set_orchestrator(runtime.orchestrator)
```

New code:

```python
if cfg.enable_orchestrator:
    from k1.concierge.dispatch.orchestrator_wiring import create_concierge_orchestrator
    from k1.concierge.dispatch.fabric_orchestrator_adapter import FabricOrchestratorAdapter

    orchestrator, orchestrator_mailbox = await create_concierge_orchestrator(
        fabric=fabric,           # real Fabric from M6
        bus=bus,                  # K1 bus from M3
        session_state=session_state,
    )
    runtime.orchestrator = orchestrator
    runtime.dispatch_port = FabricOrchestratorAdapter(
        fabric=fabric,
        orchestrator_mailbox=orchestrator_mailbox,
    )
    if hasattr(runtime.fsm, "set_dispatch_port"):
        runtime.fsm.set_dispatch_port(runtime.dispatch_port)
```

Additional changes:

- Add `dispatch_port: Any = None` to `KernelRuntime` dataclass
- Remove `_FabricGatewayAdapter` class (847-870) — replaced by K1 `FabricGatewayAdapter`
- Remove `_StateReadAdapter` class (874-904) — replaced by K1 `StateReadAdapter`
- Keep `_DeltaEmitAdapter` temporarily if still used elsewhere; else remove

Imports to add:

- `from k1.concierge.dispatch.orchestrator_wiring import create_concierge_orchestrator`
- `from k1.concierge.dispatch.fabric_orchestrator_adapter import FabricOrchestratorAdapter`

Imports to remove:

- `from poc.k1_poc.orchestrator.stub import OrchestratorStub`

Touch point: EDIT `k1/concierge/kernel/bootstrap.py` — orchestrator section (~30 lines rewritten), `KernelRuntime` (add field), delete `_FabricGatewayAdapter`/`_StateReadAdapter` classes (~60 lines removed)
Depends on: E8.1.2, E8.2.1

**Issue E8.4.2** — Wire FSM DISPATCHING → IDispatchPort

The FSM's DISPATCHING state handler needs to call `IDispatchPort` instead of directly calling `OrchestratorStub`:

- Current: FSM calls `runtime.orchestrator.handle_task(envelope)` for MEDIUM tier
- After M8: FSM calls `runtime.dispatch_port.dispatch_envelope(k1_envelope)` for MEDIUM/HIGH tier
- Current: FSM calls tools → `ToolContext.invoke_fn()` for LOW tier
- After M8: FSM calls `runtime.dispatch_port.dispatch_direct(cap_request)` for LOW tier (via ToolDispatcher)

Changes:

- FSM handler (in `k1/concierge/fsm/` or `k1/concierge/actors/`) that invokes orchestrator:
  - Replace `runtime.orchestrator.handle_task(poc_envelope)` → `runtime.dispatch_port.dispatch_envelope(k1_envelope)`
  - The `k1_envelope` comes from `route_task_sync()` (E8.3.1) which now returns K1 `TaskEnvelope`

Touch point: EDIT 1-2 files in `k1/concierge/fsm/` or `k1/concierge/actors/`
Depends on: E8.3.1, E8.4.1

---

#### E8.5 — Wire Result Flow (Orchestrator → Concierge)

> K1 Orchestrator emits `AggregatedResult` on `k1.orchestration.dag.completed.v1` via K1 bus.
> The Concierge's DeltaAggregator must subscribe to this topic and route the result to the
> FSM for transition to DELIVERING.

**Issue E8.5.1** — Subscribe DeltaAggregator to orchestration completion events

The DeltaAggregator (or bus subscription handler) in `k1/concierge/` must subscribe to:

- `k1.orchestration.dag.completed.v1` — MEDIUM/HIGH task completed
- `k1.orchestration.task.accepted.v1` — Orchestrator accepted the task (for FSM state tracking)
- `k1.orchestration.step.completed.v1` — individual step completed (for progress updates)
- `k1.orchestration.step.failed.v1` — step failed (for error handling)

On receiving `k1.orchestration.dag.completed.v1`:

1. Deserialize `AggregatedResult` from event payload
2. Convert K1 `AggregatedResult` to the format expected by the FSM's DELIVERING handler:
   - Extract `step_results[].result.data` → build `tool_results[]` for the Tool Result Buffer
   - `aggregated_result.success` → determines response tone
   - `aggregated_result.trace_id` → link back to original turn
3. Buffer results in Tool Result Buffer
4. Trigger FSM transition: COMPANIONING → DELIVERING (or BACKGROUND_WORKING → DELIVERING per concierge.mmd L640)

Touch point: EDIT `k1/concierge/bus/setup.py` or `k1/concierge/delta/` — add subscription handler (~50 lines)
Depends on: E8.2.1 (Orchestrator emits events), M3 (bus subscriptions)

**Issue E8.5.2** — Create `k1/concierge/dispatch/result_converter.py` — AggregatedResult → tool_results

Converts K1 `AggregatedResult` (from `k1.orchestrator.types`) to the format the Concierge's DELIVERING state expects (tool_results list for the LLM context window):

```python
def aggregated_to_tool_results(result: AggregatedResult) -> list[dict]:
    """Convert AggregatedResult to tool_results[] for DELIVERING LLM context."""
    tool_results = []
    for step in result.step_results:
        if step.status == StepStatus.COMPLETED and step.result:
            tool_results.append({
                "tool_name": step.capability_name,
                "result": step.result.data,
                "success": step.result.success,
                "duration_ms": step.duration_ms,
            })
        elif step.status == StepStatus.FAILED:
            tool_results.append({
                "tool_name": step.capability_name,
                "result": {"error": step.error_detail or "step_failed"},
                "success": False,
                "duration_ms": step.duration_ms,
            })
    return tool_results
```

Touch point: NEW file `k1/concierge/dispatch/result_converter.py` (~50 lines)
Depends on: `k1.orchestrator.types` (AggregatedResult, StepResult, StepStatus)

---

#### E8.6 — Clean Up POC Orchestrator References

> After wiring the real K1 Orchestrator, remove all remaining references to the POC
> orchestrator module from `k1/concierge/`.

**Issue E8.6.1** — Remove POC orchestrator imports from `k1/concierge/`

Search and replace:

- `from poc.k1_poc.orchestrator.stub import OrchestratorStub` → remove
- `from poc.k1_poc.orchestrator.types import ...` → `from k1.orchestrator.types import ...`
- `from poc.k1_poc.orchestrator.routing import ...` → `from k1.concierge.dispatch.routing import ...`
- `from poc.k1_poc.orchestrator.ports import IDispatchPort` → `from k1.concierge.dispatch.ports import IDispatchPort`
- `from poc.k1_poc.orchestrator.degradation import ...` → remove (degradation logic now in FabricOrchestratorAdapter)

Verification: `grep -r "poc.k1_poc.orchestrator" k1/concierge/` → must return 0 results

Touch point: EDIT 3-6 files in `k1/concierge/` — import path changes
Depends on: E8.3, E8.4, E8.5

**Issue E8.6.2** — Delete bootstrap helper classes

After E8.4.1, these bootstrap helper classes are dead code:

- `_FabricGatewayAdapter` (bootstrap.py L847-870) — replaced by K1 `FabricGatewayAdapter`
- `_StateReadAdapter` (bootstrap.py L874-904) — replaced by K1 `StateReadAdapter`
- `_DeltaEmitAdapter` (if no other consumers) — replaced by K1 `DeltaEmitAdapter`

Verification before delete: `grep -r "_FabricGatewayAdapter\|_StateReadAdapter\|_DeltaEmitAdapter" k1/` → only bootstrap.py

Touch point: EDIT `k1/concierge/kernel/bootstrap.py` — delete 3 helper classes (~70 lines removed)
Depends on: E8.4.1

---

#### E8.7 — Unit Tests

**Issue E8.7.1** — Create `tests/k1/concierge/test_dispatch_port.py`

Tests for `IDispatchPort` + `FabricOrchestratorAdapter`:

- `dispatch_direct()` calls `Fabric.execute()` and returns `CapabilityResult`
- `dispatch_direct()` retries once on failure
- `dispatch_direct()` returns failure result when all retries exhausted
- `dispatch_envelope()` enqueues `TaskEnvelope` to mailbox
- `dispatch_envelope()` fire-and-forget: returns immediately
- `cancel_dispatch()` removes envelope from mailbox
- `cancel_dispatch()` returns False if envelope already processing
- Tier degradation: MEDIUM envelope enqueue fails → falls back to direct execution
- `IDispatchPort` is `runtime_checkable`, `FabricOrchestratorAdapter` satisfies it

Touch point: NEW file `tests/k1/concierge/test_dispatch_port.py` (~25 tests)

**Issue E8.7.2** — Create `tests/k1/concierge/test_mock_dispatch_adapter.py`

Tests for `MockDispatchAdapter`:

- Satisfies `IDispatchPort` (isinstance check)
- `dispatch_direct()` returns scripted result
- `dispatch_envelope()` records envelope in `dispatched_envelopes`
- `dispatched_requests` captures all dispatch_direct calls
- `cancel_log` captures cancel_dispatch calls

Touch point: NEW file `tests/k1/concierge/test_mock_dispatch_adapter.py` (~10 tests)

**Issue E8.7.3** — Create `tests/k1/concierge/test_routing_k1.py`

Tests for migrated `route_task()` producing K1 `TaskEnvelope`:

- LOW tier: returns `DispatchRecord` with topic, no envelope
- MEDIUM tier: returns `DispatchRecord` with K1 `TaskEnvelope`, `tier="MEDIUM"`, `capabilities` non-empty, `len <= 2`
- HIGH tier: returns `DispatchRecord` with K1 `TaskEnvelope`, `tier="HIGH"`
- K1 `TaskEnvelope` passes `__post_init__` validation (intent non-empty, trace_id non-empty, tier valid)
- `_extract_capabilities()` extracts tool names from TaskDispatch
- `_extract_params()` builds per-capability params dict

Touch point: NEW file `tests/k1/concierge/test_routing_k1.py` (~20 tests)

**Issue E8.7.4** — Create `tests/k1/concierge/test_result_converter.py`

Tests for `aggregated_to_tool_results()`:

- Converts successful steps to tool_results with success=True
- Converts failed steps to tool_results with error detail
- Handles mixed results (some success, some failed, some skipped)
- Empty AggregatedResult → empty tool_results
- Preserves capability_name and duration_ms

Touch point: NEW file `tests/k1/concierge/test_result_converter.py` (~10 tests)

**Issue E8.7.5** — Create `tests/k1/concierge/test_orchestrator_wiring.py`

Tests for `create_concierge_orchestrator()`:

- Returns `(OrchestratorService, IMailboxPort)` tuple
- `OrchestratorService` has real `FabricGatewayAdapter` (not test adapter)
- `OrchestratorService` has real `MailboxAdapter`
- `OrchestratorService` has mock `PlannerAdapter` (HIGH tier deferred)
- Mailbox accepts TaskEnvelope enqueue

Touch point: NEW file `tests/k1/concierge/test_orchestrator_wiring.py` (~10 tests)

---

#### E8.8 — Integration Tests + E2E Verification

**Issue E8.8.1** — MEDIUM tier E2E smoke test

Create `tests/k1/concierge/test_medium_tier_e2e.py`:

Full path test with in-memory components:

1. Create `Fabric` via `FabricFactory.create_for_testing()` with test capabilities registered
2. Create `OrchestratorService` via `create_concierge_orchestrator(fabric, bus, session_state)`
3. Create `FabricOrchestratorAdapter(fabric, mailbox)`
4. Build a MEDIUM tier `TaskEnvelope` via `route_task_sync()` with `capabilities=["tool.test.echo"]`
5. Call `adapter.dispatch_envelope(envelope)`
6. Wait for `k1.orchestration.dag.completed.v1` event on bus
7. Verify `AggregatedResult.success == True`
8. Verify `AggregatedResult.step_results[0].result.data` matches test capability output
9. Verify `aggregated_to_tool_results()` produces correct tool_results format

Touch point: NEW file `tests/k1/concierge/test_medium_tier_e2e.py` (~20 tests)

**Issue E8.8.2** — LOW tier regression (unchanged path)

Verify LOW tier still works after wiring changes:

- `route_task_sync(task, ComplexityTier.LOW)` → `DispatchRecord` with topic, no envelope
- `FabricOrchestratorAdapter.dispatch_direct(cap_request)` → `CapabilityResult` from Fabric
- React loop → tool_call → dispatch_direct → Fabric → tool_result (end-to-end)

Touch point: NEW tests in `tests/k1/concierge/test_medium_tier_e2e.py` or existing LOW tier tests (~5 tests)

**Issue E8.8.3** — Run full Concierge + Orchestrator test suites

- Command: `python -m pytest tests/k1/concierge/ tests/k1/orchestrator/ --tb=short -q`
- Gate: ALL tests pass
- Focus: existing orchestrator tests still green, new concierge dispatch tests green

**Issue E8.8.4** — Git tag `m8-orchestrator-wired`

- Tag commit after all tests green
- Gate metrics:

| Metric | Value |
|---|---|
| New Concierge dispatch files | 6 (`ports.py`, `fabric_orchestrator_adapter.py`, `mock_dispatch_adapter.py`, `orchestrator_wiring.py`, `routing.py`, `result_converter.py`) |
| New test files | 6 |
| New tests | ~100 |
| Bootstrap classes removed | 2-3 (`_FabricGatewayAdapter`, `_StateReadAdapter`, optionally `_DeltaEmitAdapter`) |
| POC OrchestratorStub replaced | Yes — real `OrchestratorService` via factory |
| K1 adapters injected | 5 (FabricGateway, Mailbox, DeltaEmit, EventSubscription, StateRead) |
| Callers migrated to IDispatchPort | FSM dispatching, ToolDispatcher |
| POC orchestrator imports removed from k1/concierge/ | All |
| HIGH tier status | Wired with MockPlannerAdapter — real Planner is M9 |

---

## M9 — K1 Planner Wiring

> K1 Planner is **FULLY IMPLEMENTED** — 33 Python files, ~10,566 lines across 7 subdirectories.
> Core service: `PlannerAgent` (733 lines) + `PipelineController` (1,301 lines), 4 stage services
> (`SketchService` 1,132, `ExpandService` 1,357, `ValidateService` 1,063, `CommitService` 454),
> `ToolCallRouter` (352 lines), `HILCoordinator` (482 lines), `PlanStateMachine` (11 states, 23 edges).
> 7 hexagonal ports, 7 production adapters, 7 test adapters, 4 factory creation modes via `PlannerFactory`.
> 40 test files, ~23,742 lines of existing test coverage.
>
> The POC has **ZERO planner code** — planning is purely a K1 concept. LOW/MEDIUM tasks go
> directly to Fabric without planning; only HIGH tier routes through the Planner's 4-stage
> pipeline: Sketch → Expand → Validate → Commit.
>
> M8 wired `MockPlannerAdapter` into `OrchestratorFactory.create_for_testing()` and deferred
> real Planner to M9. M8 also built `FabricOrchestratorAdapter` with simplified tier degradation
> (no real CB_PLANNER). This milestone **replaces `MockPlannerAdapter`** with real
> `PlannerAdapter(planner.mailbox, cb_planner)`, creates the `PlannerAgent` via
> `PlannerFactory.create_production()` with 7 real adapter ports, builds the Concierge-side
> HIL Response Routing for Planner's human-in-the-loop events, upgrades CB_PLANNER to a real
> `CircuitBreaker`, and verifies HIGH tier E2E: complex multi-step task → Planner 4-stage
> → CommittedPlan → Orchestrator DAGExecutor → Fabric → AggregatedResult → DELIVERING.

**K1 Planner status**: FULLY IMPLEMENTED (33 .py, ~10,566 lines)
**K1 Planner factory**: `PlannerFactory` — `create_standalone()`, `create_for_testing(overrides)`, `create_with_ports(**ports)`, `create_production(**ports)`
**K1 Planner key types** (`k1/planner/types.py`, 807 lines): `RoughStep`, `SketchResult`, `ExpandedPlan`, `ValidationIssue`, `ValidationVerdict`, `StageContext`, `DeltaPayload`, `StagePhase` (SKETCH/EXPAND/VALIDATE/COMMIT), `ToolCallStatus`, `RequestConstraints`, `HubRequest`, `HubResponse`, `RecallResponse`, `TokenUsageRecord`, `HealthStatus` + 14 custom exceptions
**K1 Planner shared types** (from `k1/orchestrator/types.py`): `PlanRequest`, `PlanAck`, `CommittedPlan`, `PlanStep` (14 fields), `MicroReplanRequest`, `StepResult` — Planner imports these, does NOT redefine them
**K1 Planner 7 ports** (`k1/planner/ports/`): `IMailboxPort`, `ILLMPort`, `IFabricRetrievalPort`, `IStateReadPort`, `IBridgePort`, `IDeltaEmitPort`, `IEventPort`
**K1 Planner 7+7 adapters** (`k1/planner/adapters/`): production (`MailboxAdapter`, `LLMGatewayAdapter`, `FabricRetrievalAdapter`, `SessionStateReadAdapter`, `BridgeAdapter`, `DeltaBusAdapter`, `EventBusAdapter`) + 7 test adapters
**K1 Planner pipeline**: `PlannerAgent` → `PipelineController` → `SketchService` → `ExpandService` → `ValidateService` → `CommitService`
**K1 Planner events** (`k1/planner/events.py`): Published: `k1.planner.plan.ready.v1`, `k1.planner.plan.failed.v1`, `k1.planner.plan.cancelled.v1`, `k1.planner.micro_replan.ready.v1`, `k1.planner.delta.v1`, `k1.hil.clarification.v1`, `k1.hil.approval_request.v1`; Subscribed: `k1.hil.clarification_response.v1`, `k1.hil.approval_response.v1`
**Orchestrator contract** (`k1/orchestrator/adapters/planner_adapter.py`): `PlannerAdapter(planner_mailbox: IPlannerMailbox, cb_planner: CircuitBreaker)` — `request_plan()` CB gate → enqueue, `cancel_plan()` best-effort, `micro_replan()` synchronous 10s timeout
**Connection point**: Orchestrator's `IPlannerMailbox` protocol (enqueue, send_cancel, micro_replan) is structurally identical to Planner's `IMailboxPort` — `planner.mailbox` property returns the `IMailboxPort` instance, which is passed as `planner_mailbox` to `PlannerAdapter`
**Concierge .mmd ref**: CB_PLANNER (L607) — 45s timeout, 2/min, fallback: skip planning direct execution, owner: FabricOrchestratorAdapter; HIL_RESPONSE_ROUTING (L208-213) — HILResponseDetector checks PENDING_CLARIFICATIONS, routes user responses to Planner (clarification_response.v1, approval_response.v1)
**Bootstrap ref** (`k1/kernel/kernel.md`): Phase 5 creates PlannerAgent, Phase 5b cross-wires `orchestrator._planner_port = PlannerAdapter(planner.mailbox, cb_planner)`

### Architecture: What M9 Builds

```text
┌──────────────────────── k1/concierge/ ─────────────────────────┐
│                                                                  │
│  FabricOrchestratorAdapter (from M8, UPGRADED in M9)             │
│   ├── CB_PLANNER — real CircuitBreaker(45s, 2/min)              │
│   ├── HIGH: dispatch_envelope → Orchestrator mailbox             │
│   │   └── Orchestrator.dispatch_high() → IPlannerPort            │
│   └── tier degradation: CB_PLANNER OPEN → degrade HIGH→MED      │
│                                                                  │
│  HIL Response Routing (NEW in M9, per concierge.mmd L208-213)   │
│   ├── subscribe k1.hil.clarification.v1 → user prompt            │
│   ├── subscribe k1.hil.approval_request.v1 → user approval       │
│   ├── PENDING_CLARIFICATIONS[request_id] = {originator, ...}    │
│   ├── HILResponseDetector: user input → match request_id         │
│   │   → emit k1.hil.clarification_response.v1 (to Planner)      │
│   │   → emit k1.hil.approval_response.v1 (to Planner)           │
│   └── clear PENDING_CLARIFICATIONS entry after response          │
│                                                                  │
└────────────────────────────────────────────────────────────────┘

┌──────────────────────── k1/orchestrator/ ────────────────────────┐
│                                                                   │
│  OrchestratorService.dispatch_high(envelope)                      │
│   → PlannerAdapter.request_plan(PlanRequest) — CB gate            │
│   → Planner mailbox enqueue (fire-and-forget)                     │
│   → PlanAck(ACCEPTED) returned immediately                        │
│                                                                   │
│  EventSubscriptionAdapter subscriptions:                          │
│   → k1.planner.plan.ready.v1: receive CommittedPlan              │
│     → DAGExecutor.execute_plan(committed_plan) → Fabric steps    │
│   → k1.planner.plan.failed.v1: mark task FAILED, emit to bus     │
│   → k1.planner.plan.cancelled.v1: mark task CANCELLED            │
│                                                                   │
│  Mid-DAG micro-replan:                                            │
│   → PlannerAdapter.micro_replan(MicroReplanRequest) — 10s sync   │
│   → Planner returns updated CommittedPlan or None (timeout)       │
│                                                                   │
└──────────────────│────────────────────────────────────────────────┘
                   │ (in-process, shared IMailboxPort)
                   ▼
┌──────────────────────── k1/planner/ ─────────────────────────────┐
│                                                                   │
│  PlannerAgent._run_loop()                                         │
│   → mailbox.dequeue() → PlanRequest                               │
│   → PipelineController.execute(request)                           │
│       │                                                           │
│       ├── SKETCH (SketchService, agentic, ~3-8s, ≤2048 tok)     │
│       │   ├── LLM receives 4 tool definitions                    │
│       │   │   (discover_capabilities, query_session_context,      │
│       │   │    recall_long_term_memory, find_prompts)             │
│       │   ├── ToolCallRouter routes tool calls → 3 backend ports │
│       │   ├── HILCoordinator → clarification if ambiguous         │
│       │   └── Output: SketchResult(rough_steps, candidates)       │
│       │                                                           │
│       ├── EXPAND (ExpandService, agentic, ~2-5s, ≤1024 tok)     │
│       │   ├── LLM with tool-use + post-LLM deterministic enrich  │
│       │   ├── 6 infrastructure fields from CapabilityContract     │
│       │   └── Output: ExpandedPlan(steps: PlanStep[14-field])     │
│       │                                                           │
│       ├── VALIDATE (ValidateService, non-agentic, ~1-3s, ≤500t) │
│       │   ├── Phase 1: deterministic (DAG cycle, capability, …)  │
│       │   ├── Phase 2: LLM arbiter (coherence, safety, …)        │
│       │   ├── Revise loop → back to EXPAND (max 1 loop)          │
│       │   ├── HILCoordinator → approval if high-risk              │
│       │   └── Output: ValidationVerdict(approved|revise|reject)   │
│       │                                                           │
│       └── COMMIT (CommitService, deterministic, <100ms, 0 tok)   │
│           ├── ZERO LLM calls (PLAN-03: structural enforcement)   │
│           ├── 11-step assembly: plan_id, steps, deps, WAL, event │
│           └── Output: CommittedPlan → k1.planner.plan.ready.v1   │
│                                                                   │
│  PlannerAgent.micro_replan(MicroReplanRequest)                    │
│   → micro_sketch → micro_expand → micro_validate → commit        │
│   → CommittedPlan returned synchronously (≤10s)                  │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

### What Gets Built vs What Exists

| Component | M9 Scope | Notes |
|---|---|---|
| PlannerAgent + pipeline (33 .py) | ✅ EXISTS | Zero new service code needed |
| PlannerFactory (4 modes) | ✅ EXISTS | Use `create_production()` or `create_for_testing()` |
| 7 Planner ports | ✅ EXISTS | All `@runtime_checkable Protocol` |
| 7 production adapters | ✅ EXISTS | MailboxAdapter, LLMGatewayAdapter, FabricRetrievalAdapter, SessionStateReadAdapter, BridgeAdapter, DeltaBusAdapter, EventBusAdapter |
| 7 test adapters | ✅ EXISTS | TestMailboxAdapter, TestLLMAdapter, TestFabricRetrievalAdapter, TestStateReadAdapter, TestBridgeAdapter, TestDeltaAdapter, TestEventAdapter |
| PlannerAdapter (Orchestrator side) | ✅ EXISTS | `k1/orchestrator/adapters/planner_adapter.py` (199 lines) |
| Planner wiring helper | ✅ BUILD | `k1/concierge/dispatch/planner_wiring.py` — PlannerFactory wrapper for Concierge |
| Cross-wire PlannerAdapter | ✅ WIRE | Replace MockPlannerAdapter with `PlannerAdapter(planner.mailbox, cb_planner)` |
| CB_PLANNER creation | ✅ BUILD | `CircuitBreaker("CB_PLANNER", failure_threshold=2, reset_timeout_s=45)` |
| FabricOrchestratorAdapter CB_PLANNER upgrade | ✅ UPGRADE | Add real CB_PLANNER health check for tier degradation |
| HIL Response Routing | ✅ BUILD | HILResponseDetector + PENDING_CLARIFICATIONS + event subscriptions/emissions |
| HIL event subscriptions | ✅ WIRE | Subscribe `k1.hil.clarification.v1` + `k1.hil.approval_request.v1` |
| HIL response emissions | ✅ WIRE | Emit `k1.hil.clarification_response.v1` + `k1.hil.approval_response.v1` |
| Planner lifecycle (start/stop) | ✅ WIRE | `asyncio.create_task(planner.start())` + `planner.stop()` at shutdown |
| Bootstrap Phase 5 integration | ✅ REWRITE | Add Planner creation + cross-wire to `bootstrap.py` |
| HIGH tier E2E verification | ✅ TEST | Complex task → Planner → CommittedPlan → DAG → Fabric → deliver |
| Planner 40 test files (23,742 lines) | ✅ EXISTS | Already built — just verify they pass |
| Workflow subsystem activation | ❌ DEFER | Needs real WorkflowStoragePort (separate milestone) |
| Real LLMGatewayAdapter for Planner | ⚠️ PHASE 2 | Phase 1 uses TestLLMAdapter; Phase 2 uses real Model Hub (post-M7 stable) |
| Real BridgeAdapter for Planner | ⚠️ PHASE 2 | Phase 1 uses TestBridgeAdapter; Phase 2 uses real K0 Bridge |

### Key Invariants Verified (from planner.mmd + kernel.md)

| ID | Invariant | How M9 Satisfies |
|---|---|---|
| PLAN-01 | Planner NEVER writes SessionState | `IStateReadPort` is read-only — no write methods structurally |
| PLAN-03 | CommitService makes ZERO LLM calls | `CommitService` constructor has NO `ILLMPort` parameter — enforced structurally |
| PLAN-05 | Tool call budget ≤ config.max_tool_calls_per_plan | `ToolCallRouter` enforces budget; `BudgetExhaustedError` on exceed |
| PLAN-10 | Max 2 HIL clarification rounds per plan | `HILCoordinator` enforces; `HILBudgetExceededError` on exceed |
| ORCH-11 | HIGH requires CommittedPlan | `dispatch_high()` calls `IPlannerPort.request_plan()` — now real PlannerAdapter |
| PROTOCOL-3 | micro_replan synchronous 10s timeout | `PlannerAdapter.micro_replan()` uses `asyncio.wait_for(…, timeout=10.0)` |
| INV-04 | Orchestrator/Planner/Agents NEVER write SessionState | Both Orchestrator and Planner have read-only state ports — verified in M8 and M9 |

### Epics

#### E9.1 — Create PlannerAgent via PlannerFactory (Phase 5 Wiring)

> Per `k1/kernel/kernel.md` Phase 5: create `PlannerAgent` via `PlannerFactory.create_production()`
> with 7 real infrastructure adapter ports wired to existing Bus, Fabric, and SessionState instances.
> The PlannerFactory validates all ports via `@runtime_checkable isinstance` checks and runs the
> 10-step wiring sequence (ToolCallRouter → HILCoordinator → 4 stages → PipelineController → PlannerAgent).

**Issue E9.1.1** — Create `k1/concierge/dispatch/planner_wiring.py` — planner factory helper

Helper function that creates and configures the `PlannerAgent` with appropriate adapters:

```python
from k1.planner.factory import PlannerFactory
from k1.planner.config import PlannerConfig
from k1.planner.adapters.fabric_retrieval_adapter import FabricRetrievalAdapter
from k1.planner.adapters.session_state_adapter import SessionStateReadAdapter as PlannerStateAdapter
from k1.planner.adapters.delta_bus_adapter import DeltaBusAdapter as PlannerDeltaAdapter
from k1.planner.adapters.event_bus_adapter import EventBusAdapter as PlannerEventAdapter
from k1.planner.adapters.mailbox_adapter import MailboxAdapter as PlannerMailboxAdapter
# Phase 1 stubs (replaced in Phase 2 when Model Hub and Bridge are stable):
from tests.k1.planner.adapters import TestLLMAdapter, TestBridgeAdapter

async def create_concierge_planner(
    *,
    fabric: Any,           # real K1 Fabric (from M6)
    fabric_bus: Any,       # FabricBusAdapter (from Phase 3)
    state_reader: Any,     # SessionStateReaderAdapter (from Phase 3)
    config: dict | None = None,
) -> PlannerAgent:
    """Create PlannerAgent wired for Concierge use.

    Returns the agent instance. Caller must:
    1. Call ``planner.mailbox`` to extract IMailboxPort for cross-wiring
    2. Spawn ``asyncio.create_task(planner.start())`` to begin dequeue loop
    """
    planner_config = PlannerConfig() if config is None else PlannerConfig.from_dict(config)

    planner = await PlannerFactory.create_production(
        llm_port=TestLLMAdapter(),                            # Phase 1 stub
        fabric_port=FabricRetrievalAdapter(fabric),           # wraps Fabric facade from M6
        state_port=PlannerStateAdapter(state_reader),         # wraps SessionStateReaderAdapter
        bridge_port=TestBridgeAdapter(),                      # Phase 1 stub
        delta_port=PlannerDeltaAdapter(fabric_bus),           # wraps FabricBusAdapter delta bus
        event_port=PlannerEventAdapter(fabric_bus),           # wraps FabricBusAdapter event port
        mailbox_port=PlannerMailboxAdapter(
            max_depth=planner_config.mailbox_max_depth,
        ),
        config=planner_config,
    )
    return planner
```

Adapter wiring:

| Port Slot | Adapter | Source | Status |
|---|---|---|---|
| `llm_port` | `TestLLMAdapter()` | `tests.k1.planner.adapters` | Phase 1 stub — Phase 2: `LLMGatewayAdapter(model_hub)` |
| `fabric_port` | `FabricRetrievalAdapter(fabric)` | `k1.planner.adapters.fabric_retrieval_adapter` | Real — wraps M6 Fabric |
| `state_port` | `SessionStateReadAdapter(state_reader)` | `k1.planner.adapters.session_state_adapter` | Real — wraps SessionStateReaderAdapter |
| `bridge_port` | `TestBridgeAdapter()` | `tests.k1.planner.adapters` | Phase 1 stub — Phase 2: `BridgeAdapter(bridge_client)` |
| `delta_port` | `DeltaBusAdapter(fabric_bus)` | `k1.planner.adapters.delta_bus_adapter` | Real — wraps FabricBusAdapter |
| `event_port` | `EventBusAdapter(fabric_bus)` | `k1.planner.adapters.event_bus_adapter` | Real — wraps FabricBusAdapter |
| `mailbox_port` | `MailboxAdapter(max_depth=5)` | `k1.planner.adapters.mailbox_adapter` | Real — standalone FIFO queue |

Touch point: NEW file `k1/concierge/dispatch/planner_wiring.py` (~80 lines)
Depends on: K1 Planner factory + adapters (all existing), M6 (Fabric), M3 (bus)

---

#### E9.2 — Cross-wire Orchestrator.IPlannerPort (Phase 5b)

> Per `k1/kernel/kernel.md` Phase 5b: extract Planner's `IMailboxPort` via `planner.mailbox` property,
> create a real `CircuitBreaker("CB_PLANNER")`, construct `PlannerAdapter(planner.mailbox, cb_planner)`,
> and hot-swap `orchestrator._planner_port` from `MockPlannerAdapter` to real `PlannerAdapter`.
>
> M8 (E8.2.1) created `create_concierge_orchestrator()` which left the `planner` port key using the
> factory's built-in test adapter (MockPlannerAdapter). M9 replaces this with the real PlannerAdapter
> after the PlannerAgent is created in E9.1.

**Issue E9.2.1** — Create CB_PLANNER CircuitBreaker instance

Per concierge.mmd L607 and kernel.md L326-330:

```python
from k1.fabric.circuit_breaker.breaker import CircuitBreaker

cb_planner = CircuitBreaker(
    "CB_PLANNER",
    failure_threshold=2,          # 2 failures per window → OPEN
    reset_timeout_s=45.0,         # 45s OPEN window before HALF-OPEN probe
)
```

Configuration source: `OrchestratorConfig.cb_planner_failure_threshold` (default 2), `OrchestratorConfig.cb_planner_reset_timeout_ms` (default 45000).

Touch point: NEW code in `k1/concierge/dispatch/planner_wiring.py` or `k1/concierge/dispatch/orchestrator_wiring.py` (~10 lines)
Depends on: `k1.fabric.circuit_breaker.breaker.CircuitBreaker` (existing)

**Issue E9.2.2** — Build `PlannerAdapter` and hot-swap into Orchestrator

Per kernel.md Phase 5b:

```python
from k1.orchestrator.adapters.planner_adapter import PlannerAdapter

planner_mailbox = planner.mailbox    # PlannerAgent.mailbox property → IMailboxPort
planner_adapter = PlannerAdapter(planner_mailbox, cb_planner)
orchestrator._planner_port = planner_adapter  # hot-swap MockPlannerAdapter → real
```

The `IPlannerMailbox` protocol (defined in `planner_adapter.py` L59-73) requires:

- `enqueue(request: PlanRequest) -> None`
- `send_cancel(request_id: str) -> None`
- `micro_replan(request: MicroReplanRequest) -> CommittedPlan`

Planner's `IMailboxPort` (from `k1/planner/ports/mailbox_port.py`) provides all three plus `dequeue()` and `drain()`. Since `IPlannerMailbox` is a structural protocol, `IMailboxPort` satisfies it via duck typing — no adapter needed.

Verification: `isinstance(planner.mailbox, IPlannerMailbox)` must pass (or at minimum structural match since IPlannerMailbox is not `@runtime_checkable` — verify at test time by calling all 3 methods).

Touch point: EDIT `k1/concierge/dispatch/orchestrator_wiring.py` (from M8) — add cross-wire function (~30 lines)
Depends on: E9.1.1 (planner created), E9.2.1 (CB_PLANNER created), M8 E8.2.1 (orchestrator created)

**Issue E9.2.3** — Update `create_concierge_orchestrator()` to accept optional planner override

M8's `create_concierge_orchestrator()` in `k1/concierge/dispatch/orchestrator_wiring.py` uses `MockPlannerAdapter` by default. Add an optional `planner_adapter` parameter so M9 can pass the real `PlannerAdapter`:

```python
async def create_concierge_orchestrator(
    *,
    fabric: Fabric,
    bus: Any,
    session_state: Any,
    planner_adapter: Any = None,   # NEW: pass real PlannerAdapter from E9.2.2
    config: dict | None = None,
) -> tuple[OrchestratorService, IMailboxPort]:
```

If `planner_adapter` is provided, use it as the `planner` override in `OrchestratorFactory.create_for_testing(overrides={..., "planner": planner_adapter})`. If not provided, factory uses built-in MockPlannerAdapter (backward-compatible with M8 tests).

Touch point: EDIT `k1/concierge/dispatch/orchestrator_wiring.py` — add parameter + conditional override (~15 lines changed)
Depends on: M8 E8.2.1 (existing function)

---

#### E9.3 — Upgrade FabricOrchestratorAdapter CB_PLANNER

> M8 (E8.1.2) built `FabricOrchestratorAdapter` with simplified tier degradation (no real CB_PLANNER).
> Per concierge.mmd L285 and L607, `FabricOrchestratorAdapter` OWNS `CB_PLANNER` and uses it for
> tier degradation: when CB_PLANNER is OPEN, HIGH tier degrades to MEDIUM (skip planning, direct execution).
>
> M9 adds the real CB_PLANNER reference and health check to `FabricOrchestratorAdapter`.

**Issue E9.3.1** — Add CB_PLANNER to FabricOrchestratorAdapter constructor

M8's `FabricOrchestratorAdapter.__init__` takes `(fabric, orchestrator_mailbox)`. Add `cb_planner`:

```python
class FabricOrchestratorAdapter:
    def __init__(
        self,
        fabric: Fabric,
        orchestrator_mailbox: IMailboxPort,
        cb_planner: CircuitBreaker | None = None,  # NEW: optional for backward compat
    ):
        self._fabric = fabric
        self._orchestrator_mailbox = orchestrator_mailbox
        self._cb_planner = cb_planner
```

`cb_planner=None` keeps M8 tests backward-compatible (simplified degradation when no CB).

Touch point: EDIT `k1/concierge/dispatch/fabric_orchestrator_adapter.py` — constructor + field (~5 lines)
Depends on: E9.2.1 (CB_PLANNER instance)

**Issue E9.3.2** — Implement CB_PLANNER tier degradation in `dispatch_envelope()`

In `FabricOrchestratorAdapter.dispatch_envelope()`, before enqueuing HIGH tier envelopes:

```python
async def dispatch_envelope(self, envelope: TaskEnvelope) -> None:
    if envelope.tier == "HIGH" and self._cb_planner is not None:
        if self._cb_planner.state == CircuitBreakerState.OPEN:
            logger.warning(
                "CB_PLANNER OPEN — degrading HIGH→MEDIUM for envelope=%s",
                envelope.envelope_id,
            )
            # Degrade: rewrite tier to MEDIUM, strip Planner-dependent fields
            envelope = TaskEnvelope(
                intent=envelope.intent,
                trace_id=envelope.trace_id,
                caller_id=envelope.caller_id,
                envelope_id=envelope.envelope_id,
                context=envelope.context,
                tier="MEDIUM",                    # DEGRADED
                capabilities=envelope.capabilities,
                params=envelope.params,
                timeout_ms=envelope.timeout_ms,
            )
    # ... existing enqueue to orchestrator mailbox
```

This matches concierge.mmd L607: "CB: Planner → Fallback: skip planning, direct execution" and the tier degradation cascade "HIGH→MED→LOW→canned".

Touch point: EDIT `k1/concierge/dispatch/fabric_orchestrator_adapter.py` — `dispatch_envelope()` method (~20 lines added)
Depends on: E9.3.1

---

#### E9.4 — Build HIL Response Routing (Concierge → Planner)

> Per concierge.mmd L208-213: the Concierge has an `HIL_RESPONSE_ROUTING` subgraph.
> When Planner's `HILCoordinator` emits `k1.hil.clarification.v1` or `k1.hil.approval_request.v1`,
> the Concierge receives these events, stores them in `PENDING_CLARIFICATIONS`, presents the
> question/approval to the user, and when the user responds, the `HILResponseDetector` matches
> the `request_id` in `PENDING_CLARIFICATIONS` and emits the corresponding response event back
> to Planner (`k1.hil.clarification_response.v1` or `k1.hil.approval_response.v1`).
>
> The POC has NO HIL for Planner — this is new Concierge-side code.

**Issue E9.4.1** — Create `k1/concierge/hil/__init__.py` + `types.py` — HIL types

Per concierge.mmd L248 (`PENDING_CLARIFICATIONS`) and L209 (`HILResponseDetector`):

```python
@dataclass(frozen=True)
class PendingHILRequest:
    """Active HIL request stored in PENDING_CLARIFICATIONS."""
    request_id: str               # correlation key from Planner's HIL event
    originator: str               # "planner" | "orchestrator" | "agent:{agent_id}"
    event_type: str               # "clarification" | "approval" | "fallback"
    question: str                 # question/prompt text for user
    context: dict                 # additional context from originator
    trace_id: str                 # tracing correlation
    created_at_ms: int            # timestamp for timeout tracking
```

Touch point: NEW file `k1/concierge/hil/__init__.py` (empty) + NEW file `k1/concierge/hil/types.py` (~40 lines)

**Issue E9.4.2** — Create `k1/concierge/hil/pending_store.py` — PENDING_CLARIFICATIONS store

In-memory store for active HIL requests, keyed by `request_id`:

```python
class PendingClarificationStore:
    """In-memory store for active HIL requests (concierge.mmd L248).

    PENDING_CLARIFICATIONS: Active HIL requests from Planner, Orchestrator, Sub-agents.
    Keyed by request_id. Cleared on user response or timeout (5min default).
    """
    def __init__(self, timeout_ms: int = 300_000):
        self._store: dict[str, PendingHILRequest] = {}
        self._timeout_ms = timeout_ms

    def add(self, request: PendingHILRequest) -> None: ...
    def match(self, request_id: str) -> PendingHILRequest | None: ...
    def has_active(self) -> bool: ...
    def remove(self, request_id: str) -> bool: ...
    def get_active_for_user(self) -> list[PendingHILRequest]: ...
    def expire_stale(self, now_ms: int) -> list[PendingHILRequest]: ...
```

Touch point: NEW file `k1/concierge/hil/pending_store.py` (~80 lines)
Depends on: E9.4.1

**Issue E9.4.3** — Create `k1/concierge/hil/hil_response_detector.py` — HILResponseDetector

Per concierge.mmd L209: checks `PENDING_CLARIFICATIONS` for active HIL request when user input arrives during active HIL. If matched, routes as HIL response (NOT new turn).

```python
class HILResponseDetector:
    """Detects if user input is a response to an active HIL request.

    Per concierge.mmd L209: checks PENDING_CLARIFICATIONS for active HIL.
    If active: route as HIL response, NOT new turn.
    Correlation: request_id from HIL request.
    """
    def __init__(
        self,
        pending_store: PendingClarificationStore,
        event_port: Any,   # bus/event emission
    ):
        self._store = pending_store
        self._event = event_port

    async def check_and_route(
        self, user_input: str, trace_id: str,
    ) -> PendingHILRequest | None:
        """Check if user_input is a response to active HIL.

        Returns the matched PendingHILRequest if routed as HIL response,
        or None if this is a normal new turn.
        """
        active = self._store.get_active_for_user()
        if not active:
            return None
        # Match first active request (FIFO — oldest pending)
        pending = active[0]
        # Emit appropriate response event based on originator + event_type
        if pending.originator == "planner" and pending.event_type == "clarification":
            await self._event.emit("k1.hil.clarification_response.v1", {
                "request_id": pending.request_id,
                "user_response": user_input,
                "trace_id": trace_id,
            })
        elif pending.originator == "planner" and pending.event_type == "approval":
            await self._event.emit("k1.hil.approval_response.v1", {
                "request_id": pending.request_id,
                "response_type": "approved",  # or "rejected" based on user input parsing
                "modifications": {},
                "trace_id": trace_id,
            })
        # Clear matched entry (concierge.mmd L880)
        self._store.remove(pending.request_id)
        return pending
```

Touch point: NEW file `k1/concierge/hil/hil_response_detector.py` (~100 lines)
Depends on: E9.4.2

**Issue E9.4.4** — Create `k1/concierge/hil/hil_event_handler.py` — subscribe to Planner HIL events

Subscribe to `k1.hil.clarification.v1` and `k1.hil.approval_request.v1` on the K1 bus. On receipt, store in `PENDING_CLARIFICATIONS` and present to user via output port:

```python
class HILEventHandler:
    """Handles inbound HIL events from Planner and Orchestrator.

    Subscribes to:
    - k1.hil.clarification.v1 (from Planner HILCoordinator)
    - k1.hil.approval_request.v1 (from Planner HILCoordinator)

    On receipt: stores in PendingClarificationStore, presents to user via IOutputPort.
    """
    def __init__(
        self,
        pending_store: PendingClarificationStore,
        event_port: Any,   # for subscriptions
        output_port: Any,  # for presenting to user
    ): ...

    async def setup_subscriptions(self) -> None:
        """Subscribe to HIL event topics."""
        await self._event.subscribe(
            "k1.hil.clarification.v1", self._on_clarification
        )
        await self._event.subscribe(
            "k1.hil.approval_request.v1", self._on_approval_request
        )

    async def _on_clarification(self, payload: dict) -> None:
        """Handle clarification request from Planner's HILCoordinator."""
        pending = PendingHILRequest(
            request_id=payload["request_id"],
            originator="planner",
            event_type="clarification",
            question=payload["question"],
            context=payload.get("context", {}),
            trace_id=payload.get("trace_id", ""),
            created_at_ms=_now_ms(),
        )
        self._store.add(pending)
        await self._output.send_to_user(pending.question, message_type="hil_clarification")

    async def _on_approval_request(self, payload: dict) -> None:
        """Handle approval request from Planner's HILCoordinator."""
        pending = PendingHILRequest(
            request_id=payload["request_id"],
            originator="planner",
            event_type="approval",
            question=payload.get("question", "Approve this plan?"),
            context=payload.get("context", {}),
            trace_id=payload.get("trace_id", ""),
            created_at_ms=_now_ms(),
        )
        self._store.add(pending)
        await self._output.send_to_user(pending.question, message_type="hil_approval")

    async def teardown_subscriptions(self) -> None:
        """Unsubscribe all HIL event subscriptions at shutdown."""
        ...
```

Touch point: NEW file `k1/concierge/hil/hil_event_handler.py` (~120 lines)
Depends on: E9.4.1, E9.4.2, M3 (bus), existing IOutputPort

---

#### E9.5 — Wire Planner Lifecycle (start/stop/shutdown)

> `PlannerAgent.start()` enters an infinite dequeue loop. The kernel must spawn it as a background
> `asyncio.Task` and cancel/stop it during shutdown. Per kernel.md Phase 5 and Shutdown Sequence.

**Issue E9.5.1** — Spawn planner background task in bootstrap

After creating PlannerAgent (E9.1.1), spawn its dequeue loop:

```python
planner_task = asyncio.create_task(planner.start())
```

Store the task in `KernelRuntime` for shutdown reference:

```python
@dataclass
class KernelRuntime:
    ...
    planner: Any = None          # PlannerAgent instance
    planner_task: Any = None     # asyncio.Task for planner.start()
```

Touch point: EDIT `k1/concierge/kernel/bootstrap.py` — add planner_task field to KernelRuntime + spawn task (~5 lines)
Depends on: E9.1.1, M8 E8.4.1 (bootstrap)

**Issue E9.5.2** — Wire planner shutdown sequence

Per kernel.md Shutdown Sequence:

1. `planner.stop()` — sets `_running=False`, drains mailbox (emits `plan.cancelled` for each), cancels in-flight plan (grace period), unsubscribes 4 events, logs `shutdown.complete`
2. `planner_task.cancel()` — cancel the background asyncio task

Add to existing shutdown handler in bootstrap:

```python
async def shutdown(runtime: KernelRuntime) -> None:
    ...  # existing M8 shutdown
    if runtime.planner is not None:
        await runtime.planner.stop()
    if runtime.planner_task is not None:
        runtime.planner_task.cancel()
        try:
            await runtime.planner_task
        except asyncio.CancelledError:
            pass
```

Touch point: EDIT `k1/concierge/kernel/bootstrap.py` — shutdown section (~10 lines added)
Depends on: E9.5.1

---

#### E9.6 — Bootstrap Integration (Concierge Kernel Phase 5)

> Tie together E9.1-E9.5 in the Concierge bootstrap: create PlannerAgent, cross-wire
> PlannerAdapter, create CB_PLANNER, upgrade FabricOrchestratorAdapter, set up HIL routing,
> spawn planner background task.

**Issue E9.6.1** — Add Planner section to `k1/concierge/kernel/bootstrap.py`

After the existing Orchestrator section (from M8 E8.4.1), add Planner section:

```python
# === Phase 5: Planner ===
if cfg.enable_planner:
    from k1.concierge.dispatch.planner_wiring import create_concierge_planner
    from k1.orchestrator.adapters.planner_adapter import PlannerAdapter
    from k1.fabric.circuit_breaker.breaker import CircuitBreaker

    # 5a. Create PlannerAgent
    planner = await create_concierge_planner(
        fabric=fabric,
        fabric_bus=fabric_bus,
        state_reader=state_reader,
        config=cfg.planner_overrides,
    )
    runtime.planner = planner

    # 5b. Cross-wire Orchestrator.IPlannerPort
    cb_planner = CircuitBreaker(
        "CB_PLANNER",
        failure_threshold=2,
        reset_timeout_s=45.0,
    )
    planner_adapter = PlannerAdapter(planner.mailbox, cb_planner)
    runtime.orchestrator._planner_port = planner_adapter

    # 5c. Upgrade FabricOrchestratorAdapter with CB_PLANNER
    runtime.dispatch_port._cb_planner = cb_planner

    # 5d. Spawn planner dequeue loop
    runtime.planner_task = asyncio.create_task(planner.start())
```

Touch point: EDIT `k1/concierge/kernel/bootstrap.py` — add Phase 5 section after Orchestrator (~30 lines)
Depends on: E9.1.1, E9.2.1, E9.2.2, E9.3.1, E9.5.1

**Issue E9.6.2** — Wire HIL event handler in bootstrap

After planner is created and bus is available:

```python
# === Phase 5e: HIL Response Routing ===
if cfg.enable_planner:
    from k1.concierge.hil.pending_store import PendingClarificationStore
    from k1.concierge.hil.hil_event_handler import HILEventHandler
    from k1.concierge.hil.hil_response_detector import HILResponseDetector

    pending_store = PendingClarificationStore(timeout_ms=300_000)
    hil_handler = HILEventHandler(
        pending_store=pending_store,
        event_port=fabric_bus,      # FabricBusAdapter from Phase 3
        output_port=runtime.output_port,
    )
    await hil_handler.setup_subscriptions()

    runtime.hil_detector = HILResponseDetector(
        pending_store=pending_store,
        event_port=fabric_bus,
    )
    runtime.hil_handler = hil_handler
    runtime.pending_clarification_store = pending_store
```

Touch point: EDIT `k1/concierge/kernel/bootstrap.py` — add HIL section after Planner (~20 lines)
Depends on: E9.4.1, E9.4.2, E9.4.3, E9.4.4, E9.6.1

**Issue E9.6.3** — Wire HILResponseDetector into FSM ACKING state

Per concierge.mmd L868: during ACKING, if there's an active HIL request, user input is routed as HIL response (not new turn).

In the FSM ACKING handler (or front actor), before classification:

```python
# Check if user input is a response to active HIL
if runtime.hil_detector is not None:
    hil_match = await runtime.hil_detector.check_and_route(
        user_input=user_message,
        trace_id=trace_id,
    )
    if hil_match is not None:
        # This was a HIL response, not a new turn
        logger.info("HIL response routed: request_id=%s", hil_match.request_id)
        return  # skip normal ACKING → DISPATCHING flow
```

Touch point: EDIT 1-2 files in `k1/concierge/fsm/` or `k1/concierge/actors/` — add HIL check before classification (~10 lines)
Depends on: E9.6.2, E9.4.3

**Issue E9.6.4** — Add `enable_planner` to Concierge config

Add configuration flag to control Planner wiring (default `False` for safe rollout):

- `enable_planner: bool = False` — when True, Phase 5 creates real PlannerAgent
- `planner_overrides: dict = {}` — passed to `PlannerConfig.from_dict()` for custom config

Touch point: EDIT config class in `k1/concierge/config/` (~5 lines added)
Depends on: None (config change)

---

#### E9.7 — Unit Tests

**Issue E9.7.1** — Create `tests/k1/concierge/test_planner_wiring.py`

Tests for `create_concierge_planner()`:

- Returns `PlannerAgent` instance
- `PlannerAgent.mailbox` returns `IMailboxPort` satisfying structural protocol
- Planner has 7 ports wired (fabric_port is real FabricRetrievalAdapter, not test)
- `PlannerAgent.mailbox.enqueue(PlanRequest)` succeeds without error
- Config overrides are applied (e.g., custom `mailbox_max_depth`)

Touch point: NEW file `tests/k1/concierge/test_planner_wiring.py` (~15 tests)

**Issue E9.7.2** — Create `tests/k1/concierge/test_planner_crosswire.py`

Tests for Phase 5b cross-wiring:

- `PlannerAdapter(planner.mailbox, cb_planner)` constructs successfully
- `planner_adapter.request_plan(PlanRequest)` enqueues to Planner's mailbox
- `planner_adapter.cancel_plan(request_id)` calls mailbox.send_cancel
- `planner_adapter.micro_replan(MicroReplanRequest)` returns CommittedPlan or None on timeout
- CB_PLANNER OPEN → `request_plan()` raises AdapterException(DEGRADED)
- CB_PLANNER CLOSED → `request_plan()` returns PlanAck(ACCEPTED)
- Hot-swap `orchestrator._planner_port = planner_adapter` replaces MockPlannerAdapter

Touch point: NEW file `tests/k1/concierge/test_planner_crosswire.py` (~20 tests)

**Issue E9.7.3** — Create `tests/k1/concierge/test_cb_planner_degradation.py`

Tests for FabricOrchestratorAdapter CB_PLANNER tier degradation:

- HIGH tier envelope + CB_PLANNER CLOSED → dispatches as HIGH (no degradation)
- HIGH tier envelope + CB_PLANNER OPEN → degrades to MEDIUM
- MEDIUM tier envelope + CB_PLANNER OPEN → no change (MEDIUM unaffected)
- LOW tier + CB_PLANNER OPEN → no change (LOW uses dispatch_direct)
- CB_PLANNER=None (M8 backward compat) → no degradation check
- After CB_PLANNER trips → subsequent HIGH calls degrade
- CB_PLANNER reset → HIGH calls go through normally

Touch point: NEW file `tests/k1/concierge/test_cb_planner_degradation.py` (~15 tests)

**Issue E9.7.4** — Create `tests/k1/concierge/test_hil_pending_store.py`

Tests for `PendingClarificationStore`:

- `add()` stores request, `match(request_id)` retrieves it
- `has_active()` returns True when store non-empty
- `remove(request_id)` clears entry, returns True
- `remove()` returns False for unknown request_id
- `get_active_for_user()` returns all active requests sorted by created_at_ms
- `expire_stale()` removes entries older than timeout_ms
- Concurrent add/remove is safe

Touch point: NEW file `tests/k1/concierge/test_hil_pending_store.py` (~15 tests)

**Issue E9.7.5** — Create `tests/k1/concierge/test_hil_response_detector.py`

Tests for `HILResponseDetector`:

- No active HIL → `check_and_route()` returns None (normal turn)
- Active clarification → user input → emits `k1.hil.clarification_response.v1` with correct payload
- Active approval → user input → emits `k1.hil.approval_response.v1` with correct payload
- After routing → pending entry is removed from store
- Multiple active → routes to oldest (FIFO)
- Expired pending → not matched

Touch point: NEW file `tests/k1/concierge/test_hil_response_detector.py` (~15 tests)

**Issue E9.7.6** — Create `tests/k1/concierge/test_hil_event_handler.py`

Tests for `HILEventHandler`:

- `setup_subscriptions()` subscribes to 2 topics
- `_on_clarification()` stores PendingHILRequest with originator="planner", event_type="clarification"
- `_on_clarification()` sends question to user via output_port
- `_on_approval_request()` stores PendingHILRequest with originator="planner", event_type="approval"
- `_on_approval_request()` sends approval prompt to user via output_port
- `teardown_subscriptions()` unsubscribes all handles

Touch point: NEW file `tests/k1/concierge/test_hil_event_handler.py` (~15 tests)

---

#### E9.8 — Integration Tests + HIGH Tier E2E Verification

**Issue E9.8.1** — HIGH tier E2E smoke test

Create `tests/k1/concierge/test_high_tier_e2e.py`:

Full path test with in-memory components (all test adapters for external deps):

1. Create `Fabric` via `FabricFactory.create_for_testing()` with 3+ test capabilities registered
2. Create `PlannerAgent` via `create_concierge_planner(fabric, fabric_bus, state_reader)`
3. Create `OrchestratorService` via `create_concierge_orchestrator(fabric, bus, session_state, planner_adapter=real_planner_adapter)`
4. Create `FabricOrchestratorAdapter(fabric, orch_mailbox, cb_planner=real_cb)`
5. Create `CB_PLANNER` CircuitBreaker
6. Cross-wire: `PlannerAdapter(planner.mailbox, cb_planner)` → `orchestrator._planner_port`
7. Spawn `asyncio.create_task(planner.start())`
8. Build a HIGH tier `TaskEnvelope` via `route_task_sync()` with `tier="HIGH"`
9. Call `adapter.dispatch_envelope(envelope)`
10. Wait for events on bus:
    - `k1.planner.plan.ready.v1` → CommittedPlan delivered to Orchestrator
    - `k1.orchestration.dag.completed.v1` → AggregatedResult from Orchestrator
11. Verify `AggregatedResult.success == True`
12. Verify plan went through all 4 stages (check delta events for SKETCH/EXPAND/VALIDATE/COMMIT)
13. Verify `CommittedPlan.steps` maps to `AggregatedResult.step_results`

Note: Uses `TestLLMAdapter` (scripted LLM responses) — real LLM integration is Phase 2.

Touch point: NEW file `tests/k1/concierge/test_high_tier_e2e.py` (~30 tests)

**Issue E9.8.2** — CB_PLANNER degradation E2E test

Test the full degradation cascade:

1. Setup: same as E9.8.1 but with CB_PLANNER configured with `failure_threshold=1`
2. Trip CB_PLANNER by failing a plan request (e.g., mailbox full)
3. Send HIGH tier task → verify it degrades to MEDIUM (no planning)
4. Wait for `k1.orchestration.dag.completed.v1` → verify MEDIUM-path execution (no CommittedPlan)
5. Reset CB_PLANNER → send another HIGH tier → verify it goes through Planner normally

Touch point: NEW tests in `tests/k1/concierge/test_high_tier_e2e.py` (~10 tests)

**Issue E9.8.3** — HIL round-trip integration test

Test the full HIL flow:

1. Setup: create Planner with `TestLLMAdapter` that triggers clarification (sets `needs_clarification=true`)
2. Send HIGH tier task → Planner enters SKETCH stage
3. Planner emits `k1.hil.clarification.v1` → HILEventHandler receives it
4. Verify `PendingClarificationStore.has_active() == True`
5. Simulate user response → `HILResponseDetector.check_and_route(user_input)`
6. Verify `k1.hil.clarification_response.v1` emitted to bus
7. Planner's HILCoordinator receives response → SKETCH continues
8. Pipeline completes → `k1.planner.plan.ready.v1` → CommittedPlan

Touch point: NEW file `tests/k1/concierge/test_hil_integration.py` (~15 tests)

**Issue E9.8.4** — MEDIUM tier regression (unchanged path)

Verify MEDIUM tier still works after M9 wiring changes (no regression from M8):

- MEDIUM tier envelope → Orchestrator dispatches via MEDIUM path (no Planner)
- `FabricOrchestratorAdapter.dispatch_envelope(medium_envelope)` → mailbox enqueue
- `OrchestratorService.dispatch_medium()` → ConstraintResolver → StepRunner → Fabric → AggregatedResult
- Bus event `k1.orchestration.dag.completed.v1` → DeltaAggregator → DELIVERING

Touch point: NEW tests in existing `tests/k1/concierge/test_medium_tier_e2e.py` (from M8) or separate file (~5 tests)

**Issue E9.8.5** — Run full Planner + Orchestrator + Concierge test suites

- Command: `python -m pytest tests/k1/planner/ tests/k1/orchestrator/ tests/k1/concierge/ --tb=short -q`
- Gate: ALL tests pass (existing Planner 23,742 lines + Orchestrator + new Concierge tests)
- Focus: existing planner tests still green, new cross-wire tests green, M8 tests unbroken

**Issue E9.8.6** — Git tag `m9-planner-wired`

- Tag commit after all tests green
- Gate metrics:

| Metric | Value |
|---|---|
| New Concierge files | 7 (`planner_wiring.py`, `hil/__init__.py`, `hil/types.py`, `hil/pending_store.py`, `hil/hil_response_detector.py`, `hil/hil_event_handler.py`) |
| Edited Concierge files | 3 (`orchestrator_wiring.py`, `fabric_orchestrator_adapter.py`, `bootstrap.py`) |
| New test files | 8 |
| New tests | ~140 |
| K1 Planner services built | 0 (all 33 .py already exist) |
| K1 Planner tests verified | 40 files, ~23,742 lines (existing, must all pass) |
| MockPlannerAdapter replaced | Yes — real `PlannerAdapter(planner.mailbox, cb_planner)` |
| PlannerFactory mode used | `create_production()` with 7 real adapter ports |
| CB_PLANNER created | Yes — `CircuitBreaker("CB_PLANNER", failure_threshold=2, reset_timeout_s=45)` |
| FabricOrchestratorAdapter upgraded | Yes — CB_PLANNER tier degradation (HIGH→MED when OPEN) |
| HIL Response Routing built | Yes — HILEventHandler, HILResponseDetector, PendingClarificationStore |
| Planner lifecycle wired | Yes — `asyncio.create_task(planner.start())` + `planner.stop()` |
| HIGH tier E2E verified | Yes — task → Planner 4-stage → CommittedPlan → DAG → Fabric → deliver |
| MEDIUM tier regression | Verified — no changes to MEDIUM path |
| Phase 1 stubs | `TestLLMAdapter` (llm_port), `TestBridgeAdapter` (bridge_port) — replaced in Phase 2 |

---

## M10 — Integration & Hardening

> Full regression, performance benchmarks, cleanup, documentation.
> All four K1 subsystems (Fabric, Model Hub, Orchestrator, Planner) are wired
> and individually gate-tested. M10 validates the **complete stack end-to-end**,
> hardens latency/token-budget invariants, resolves every deferred item from M1-M9,
> archives POC dead code, and publishes updated architecture diagrams and docs.

**Prerequisite**: M6 (Fabric), M7 (Model Hub), M8 (Orchestrator), M9 (Planner) all tagged green.

### Deferred Items Resolved in M10 (from M1-M9)

| Source | Item | Resolution in M10 |
|---|---|---|
| M1 E1.6.1 | Option B: update LLM validator to accept `HubResponse` directly (deferred from Option A shim) | E10.2.1 |
| M2 E2.3.1 | Deprecation notice on `ToolContext` old callback fields `invoke_fn`, `capability_fn`, `fabric_fn`, `workflow_fn` (M6 removed them — verify no resurfaced references) | E10.4.1 |
| M3 E3.5 | Wire K1 bus middleware: `TopicValidationMiddleware`, `TracingMiddleware` (flag), `MetricsMiddleware` (flag) | E10.2.2 |
| M6 E6.6.2 | Intent-based discovery: wire real `IEmbeddingPort` replacing `_StubEmbeddingPort` for semantic similarity | E10.2.3 |
| M9 E9.1.1 | Phase 1 stubs: `TestLLMAdapter` for Planner `llm_port`, `TestBridgeAdapter` for Planner `bridge_port` — replace with real adapters | E10.2.4 |
| M7 deferred | Full Model Hub services: manifest scanning, hot-reload, multi-provider, response cache, rate limiter, cost tracker, audit logger | **Post-M10** (Model Hub Hardening — separate milestone track) |
| M8 deferred | Workflow subsystem activation, MCP connectors, Admin API, K0 Bridge writes (WAL), crash recovery | **Post-M10** (production infrastructure — separate milestone track) |
| M8 E8.1.2 | Full CB cascade (CB_ORCHESTRATOR, CB_FABRIC, CB_MCP) — M8 has simplified retry | E10.2.5 |

**Items explicitly NOT in M10 scope** (post-M10 tracks):

- Model Hub multi-provider / manifest YAML / hot-reload / response cache / rate limiter
- Rust bus backend parity (`backend="auto"`)
- Workflow subsystem real `IWorkflowStoragePort`
- MCP connectors (no MCP servers in POC yet)
- Admin API
- K0 Bridge real WAL writes
- Crash recovery infrastructure

### Performance Baselines (from concierge.mmd PERF_BASELINES)

| Metric | Target | Source |
|---|---|---|
| LOW tier end-to-end | **< 2 s** | PERF_ENVELOPES |
| MEDIUM tier end-to-end | **< 10 s** | PERF_ENVELOPES |
| HIGH tier end-to-end | **< 45 s** (60 s CB timeout, 15 s headroom) | PERF_ENVELOPES |
| CRISIS tier end-to-end | **< 5 s** | PERF_ENVELOPES |
| Single LLM call timeout | 30 s | PERF_ENVELOPES |
| Planner stage timeout | 10 s / stage | PERF_ENVELOPES |
| FSM state transition | < 1 ms (INV-13) | INV_TIMING |
| System overhead per turn | ~32 ms | PERF_SYSTEM |

### Token Budgets (from concierge.mmd PERF_TOKENS + INV_TOKEN)

| Call Type | Max Tokens | Source |
|---|---|---|
| LOW response | 500 | PERF_TOKENS |
| MEDIUM response | 2,000 | PERF_TOKENS |
| HIGH response | 8,000 | PERF_TOKENS |
| Intent ack (`acknowledge_request`) | 150 (INV-19) | INV_TOKEN |
| Preliminary ack (MED/HIGH) | 200 (INV-20) | INV_TOKEN |
| Clarification question | 300 (INV-21) | INV_TOKEN |
| LLM context window per call | 128K (INV-18) | INV_TOKEN |

### Loop Budget Limits (from concierge.mmd LoopBudget)

| Tier | max_tools | timeout | max_tokens |
|---|---|---|---|
| LOW | 6 | 2 s | 500 |
| MEDIUM | 10 | 10 s | 2,000 |
| HIGH | 15 | 45 s | 8,000 |

### Rate Limits (from concierge.mmd INV_RATE)

| Invariant | Limit |
|---|---|
| INV-08: Tool calls per turn | 20 (hard cap) |
| INV-09: Clarification rounds per intent | 3 |
| INV-10: Output queue depth | 50 |
| INV-11: Workflow execution depth | 3 |
| INV-12: Concurrent active turns per session | 1 |

### Epics

#### E10.1 — E2E Test Suite: 3-Turn Conversation Flows

> Validate the complete Concierge stack with multi-turn conversations for each tier.
> Each test boots the full kernel (`bootstrap.py` → Fabric + Model Hub + Orchestrator + Planner),
> sends 3 user messages, and verifies the FSM traversal, tool execution, result delivery, and
> SessionState mutations at each turn.

**Issue E10.1.1** — Create `tests/k1/concierge/test_e2e_low_tier.py` — LOW tier 3-turn conversation

Full-stack test with `MockLLMAdapter` (scripted responses) + real Fabric (40 POC capabilities):

- **Turn 1** — User: "What's the weather in Seattle?"
  1. Boot kernel via `bootstrap.py` (TEST mode — `MockLLMAdapter`, real Fabric, real bus)
  2. Inject user message via `TestInputAdapter`
  3. Verify FSM: LISTENING → ACKING → DISPATCHING
  4. Verify ACKING: complexity classified as LOW
  5. Verify DISPATCHING: react loop executes `invoke_capability("tool.execute.weather_forecast", {"location": "Seattle"})`
  6. Verify Fabric pipeline: 9-step execution, `BridgeProvider` → `POCMockBridgeAdapter` → handler
  7. Verify `CapabilityResult.success == True`
  8. Verify FSM: DISPATCHING → DELIVERING → LISTENING
  9. Capture output via `TestOutputAdapter`: response contains weather data
  10. Verify SessionState mutations: `intent`, `safety_band`, `history_active` updated

- **Turn 2** — User: "What about Portland?"
  1. Verify context carryover: LLM receives history from Turn 1
  2. Verify `invoke_capability("tool.execute.weather_forecast", {"location": "Portland"})`
  3. Verify output contains Portland weather
  4. Verify `history_active` now has 2 turns

- **Turn 3** — User: "Compare them for me"
  1. Verify LLM receives context from both prior turns
  2. Verify LLM generates comparison text (no tool call needed — CHAT capability)
  3. Verify `history_active` has 3 turns
  4. Verify SessionState checkpoint triggered (turn 3 → checkpoint threshold)

Assertions:

- All 3 turns complete within LoopBudget(LOW): `max_tools=6`, `timeout=2s`, `tokens=500`
- Zero Orchestrator/Planner involvement (LOW tier bypasses)
- Bus events captured: 3× `turn.complete.v1`
- Fabric events captured: 2× `capability.executed`

Touch point: NEW file `tests/k1/concierge/test_e2e_low_tier.py` (~60 tests)

**Issue E10.1.2** — Create `tests/k1/concierge/test_e2e_medium_tier.py` — MEDIUM tier 3-turn conversation

Full-stack test with `MockLLMAdapter` + real Fabric + real Orchestrator (test adapters for Planner):

- **Turn 1** — User: "Book me a hotel in Paris and find a restaurant nearby"
  1. Boot kernel (TEST mode — full stack, `enable_orchestrator=True`)
  2. Verify ACKING: complexity classified as MEDIUM (2 capabilities)
  3. Verify `route_task_sync()` produces K1 `TaskEnvelope(tier="MEDIUM", capabilities=["tool.execute.hotel_booking", "tool.execute.restaurant_search"])`
  4. Verify `FabricOrchestratorAdapter.dispatch_envelope()` enqueues to Orchestrator mailbox
  5. Verify Orchestrator `dispatch_medium()` → `ConstraintResolver` → `StepRunner` × 2 → Fabric × 2
  6. Verify bus event `k1.orchestration.dag.completed.v1` emitted
  7. Verify `AggregatedResult.success == True` with 2 step results
  8. Verify `aggregated_to_tool_results()` converts to 2 tool_results
  9. Verify FSM: DISPATCHING → COMPANIONING → (wait for result) → DELIVERING → LISTENING
  10. Capture output: response synthesizes both hotel and restaurant results
  11. Verify SessionState: `intent`, `entities`, `history_active` updated

- **Turn 2** — User: "What about a cheaper hotel?"
  1. Verify context carryover: original Paris search context carried
  2. Verify MEDIUM tier: `capabilities=["tool.execute.hotel_search"]` (1 capability with constraints)
  3. Verify Orchestrator MEDIUM path (1 step)
  4. Verify output contains cheaper hotel options

- **Turn 3** — User: "Book the second one"
  1. Verify entity resolution from Turn 2 context (which hotel is "the second one")
  2. Verify MEDIUM tier: `capabilities=["tool.execute.hotel_booking"]` (side-effect tool)
  3. Verify Orchestrator MEDIUM path completes
  4. Verify output confirms booking
  5. Verify `history_active` has 3 turns

Assertions:

- All 3 turns complete within LoopBudget(MEDIUM): `max_tools=10`, `timeout=10s`, `tokens=2000`
- Orchestrator used for all 3 turns (MEDIUM bypasses Planner)
- Total Fabric calls: 4 (2 + 1 + 1)
- Bus events: 3× `turn.complete.v1`, 3× `k1.orchestration.dag.completed.v1`

Touch point: NEW file `tests/k1/concierge/test_e2e_medium_tier.py` (~60 tests)

**Issue E10.1.3** — Create `tests/k1/concierge/test_e2e_high_tier.py` — HIGH tier 3-turn conversation

Full-stack test with `TestLLMAdapter` (scripted Planner LLM) + real Fabric + real Orchestrator + real Planner:

- **Turn 1** — User: "Plan a family weekend trip — find flights, book a hotel, find restaurants, check weather, and create a calendar event"
  1. Boot kernel (TEST mode — full stack, `enable_orchestrator=True`, `enable_planner=True`)
  2. Verify ACKING: complexity classified as HIGH (5+ capabilities, multi-step)
  3. Verify `route_task_sync()` produces K1 `TaskEnvelope(tier="HIGH")`
  4. Verify `FabricOrchestratorAdapter.dispatch_envelope()` enqueues to Orchestrator
  5. Verify Orchestrator `dispatch_high()` → `PlannerAdapter.request_plan()` → Planner mailbox
  6. Verify Planner 4-stage pipeline:
     - SKETCH: `TestLLMAdapter` returns rough steps (5 capabilities)
     - EXPAND: `TestLLMAdapter` returns expanded plan with `PlanStep[14-field]` for each
     - VALIDATE: deterministic checks pass (DAG acyclic, capabilities valid, budget OK)
     - COMMIT: `CommittedPlan` assembled, `k1.planner.plan.ready.v1` emitted
  7. Verify Orchestrator receives `CommittedPlan` via event subscription
  8. Verify `DAGExecutor.execute_plan()` → 5 Fabric steps (some parallel, some sequential per DAG deps)
  9. Verify `AggregatedResult.success == True` with 5 step results
  10. Verify FSM: DISPATCHING → COMPANIONING → BACKGROUND_WORKING → DELIVERING → LISTENING
  11. Capture output: response summarizes all 5 results (flights, hotel, restaurants, weather, calendar)

- **Turn 2** — User: "Actually, change the hotel to something closer to the beach"
  1. Verify Orchestrator `micro_replan` path (not full re-plan — only hotel step changes)
  2. Verify Planner `micro_replan()` returns updated `CommittedPlan` (only hotel step re-expanded)
  3. Verify `DAGExecutor` re-runs only the hotel step
  4. Verify output confirms new hotel

- **Turn 3** — User: "Looks great, send the itinerary to the family group chat"
  1. Verify LOW or MEDIUM tier (simple send_message — no planning needed)
  2. Verify `invoke_capability("tool.execute.send_group_message", {...})`
  3. Verify output confirms message sent
  4. Verify full 3-turn `history_active`

Assertions:

- Turn 1 within LoopBudget(HIGH): `max_tools=15`, `timeout=45s`, `tokens=8000`
- Turns 2-3 within their respective tier budgets
- Planner used only for Turn 1 (HIGH), micro_replan for Turn 2
- Total Fabric calls: ~7 (5 + 1 + 1)
- Bus events: 3× `turn.complete.v1`, `k1.planner.plan.ready.v1`, `k1.orchestration.dag.completed.v1`

Touch point: NEW file `tests/k1/concierge/test_e2e_high_tier.py` (~80 tests)

**Issue E10.1.4** — Create `tests/k1/concierge/test_e2e_tier_degradation.py` — degradation cascade

Test the full tier degradation path from concierge.mmd:

- **Scenario 1**: HIGH → MEDIUM degradation (CB_PLANNER OPEN)
  1. Trip CB_PLANNER by failing 2 plan requests
  2. Send HIGH tier task → verify downgrade to MEDIUM (Orchestrator MEDIUM path, no Planner)
  3. Verify output still delivered (degraded but functional)

- **Scenario 2**: MEDIUM → LOW degradation (Orchestrator mailbox unavailable)
  1. Fill Orchestrator mailbox to capacity
  2. Send MEDIUM tier task → FabricOrchestratorAdapter falls back to `dispatch_direct()`
  3. Verify capabilities execute directly via Fabric (LOW path)

- **Scenario 3**: LOW → canned response (Fabric unavailable)
  1. Trip CB_FABRIC (all providers OPEN)
  2. Send LOW tier task → Fabric `execute()` fails
  3. Verify canned response from `CANNED_RESPONSES` store

- **Scenario 4**: LLM → canned response (CB_MODEL OPEN, concierge.mmd LLM_CASCADE L3)
  1. `MockLLMAdapter` configured to fail all calls
  2. Verify `ModelGatewayAdapter` LLM cascade: RETRY (L1) → CB HALF-OPEN (L2) → CANNED_RESPONSE (L3)
  3. Verify canned response per capability type (CHAT / TOOL_CALL / STRUCTURED)

Assertions:

- Each degradation preserves some response to user (never silent failure)
- Correct canned response text for each call type (concierge.mmd `CANNED_RESPONSES`)
- CB recovery: after reset timeout, traffic resumes normally

Touch point: NEW file `tests/k1/concierge/test_e2e_tier_degradation.py` (~40 tests)

**Issue E10.1.5** — Create `tests/k1/concierge/test_e2e_crisis.py` — CRISIS path

Test the hardcoded CRISIS keyword path (concierge.mmd HEURISTIC_FALLBACK):

- User: "I'm thinking about hurting myself"
  1. Verify UltraBERT or heuristic fallback detects CRISIS keywords
  2. Verify `safety_band = RED` (highest urgency)
  3. Verify CRISIS tier: timeout 5 s, response is immediate safety resource
  4. Verify CRISIS canned response is a **hardcoded string constant** (zero LLM dependency)
  5. Verify no tool execution (CRISIS bypasses Fabric/Orchestrator/Planner entirely)
  6. Verify `SessionState.safety_band` written as `RED`

Touch point: NEW file `tests/k1/concierge/test_e2e_crisis.py` (~10 tests)

---

#### E10.2 — Resolve Deferred Items from M1-M9

> Address every Phase 2 stub, deferred Option B, and optional wiring that was postponed.

**Issue E10.2.1** — Resolve M1 Option B: update LLM validator to accept `HubResponse` directly

- File: `k1/concierge/llm/validator.py`
- M1 E1.6.1 chose Option A (shim — validator still expects old fields, `_hub_to_legacy()` converts)
- M10 applies Option B: change `validate()` to accept `HubResponse` directly
- Update field access: `response.text` → `response.result.text`, `response.tool_calls` → `response.result.tool_calls`, etc.
- Remove `_hub_to_legacy()` shim
- Update all callers (react/loop.py passes `HubResponse` directly instead of converting)
- Verify: `grep -r "_hub_to_legacy" k1/concierge/` → 0 results after cleanup

Touch point: EDIT `k1/concierge/llm/validator.py` (~30 lines changed), EDIT `k1/concierge/react/loop.py` (remove shim call)

**Issue E10.2.2** — Resolve M3 E3.5: wire K1 bus middleware

M3 E3.5 was "optional but recommended." With full E2E suite now validating correctness, middleware can be safely wired:

- **TopicValidationMiddleware** (SOFT — warns, never drops):
  - File: `k1/concierge/bus/setup.py` → `create_poc_bus()`
  - Create `TopicRegistry`, register all 47 `ALL_TOPICS`
  - Build `TopicValidationMiddleware(registry)`, add to `MiddlewareChain`
  - Import: `from k1.bus.middleware.topic_validation import TopicRegistry, TopicValidationMiddleware`
  - Verify: existing tests still green (SOFT validation = no drops)

- **TracingMiddleware** (behind flag):
  - Add `bus_tracing_enabled: bool = false` to concierge config
  - Conditionally prepend `TracingMiddleware(enabled=config.bus_tracing_enabled)` to chain
  - Import: `from k1.bus.middleware.tracing import TracingMiddleware`

- **MetricsMiddleware** (behind flag):
  - Add `bus_metrics_enabled: bool = false` to concierge config
  - Conditionally append `MetricsMiddleware(enabled=config.bus_metrics_enabled)` to chain
  - Import: `from k1.bus.middleware.metrics import MetricsMiddleware`

Touch point: EDIT `k1/concierge/bus/setup.py` (~30 lines), EDIT config (~5 lines)

**Issue E10.2.3** — Resolve M6 E6.6.2: wire real `IEmbeddingPort` for intent-based discovery

M6 used `_StubEmbeddingPort` (zero vectors) — intent-based `discover_capabilities()` returned nothing useful. Wire a real embedding port:

- Assess K1 embedding infra: check if `k1/fabric/adapters/embedding_adapter.py` exists
- If exists: wire `EmbeddingAdapter` into `FabricFactory.create_with_ports()` replacing `_StubEmbeddingPort`
- If not: use a lightweight sentence-transformer (e.g., `SentenceTransformerEmbeddingPort`) or defer to post-M10
- Verify: `fabric.discover_capabilities(intent="book a hotel")` returns travel capabilities (semantic match)
- Verify: domain-filtered discovery still works (regression)

Touch point: EDIT `k1/concierge/kernel/bootstrap.py` `_create_fabric()` (~10 lines), potentially NEW adapter file

**Issue E10.2.4** — Resolve M9 Phase 1 stubs: replace `TestLLMAdapter` and `TestBridgeAdapter` in Planner

M9 E9.1.1 wired Phase 1 stubs:

- `llm_port=TestLLMAdapter()` — Planner stages SKETCH/EXPAND/VALIDATE use scripted LLM responses
- `bridge_port=TestBridgeAdapter()` — Planner bridge operations return canned results

Replace with real adapters:

- **Planner `llm_port`**: Wire `LLMGatewayAdapter(model_hub)` from `k1/planner/adapters/llm_gateway_adapter.py`
  - `model_hub` is the `ModelHubService` from M7
  - Planner LLM calls route through Model Hub → GeminiProviderPlugin → real Gemini API
  - Config: `planner.llm_model` defaults to `gemini-2.5-flash-lite` (same as Concierge)
  - Budget: Planner has own `consumer_id="planner"` for Model Hub budget tracking

- **Planner `bridge_port`**: Wire `BridgeAdapter(bridge_client)` from `k1/planner/adapters/bridge_adapter.py`
  - Assess: does a real bridge client exist? If not, keep `TestBridgeAdapter` — document as **post-M10 dependency on K0 Bridge**
  - If POC bridge exists: wire `POCMockBridgeAdapter` (from M6) as the bridge client for Planner too

Touch point: EDIT `k1/concierge/dispatch/planner_wiring.py` (~20 lines — replace TestLLMAdapter + optionally TestBridgeAdapter)

**Issue E10.2.5** — Resolve M8 simplified CB: wire full CB cascade

M8 `FabricOrchestratorAdapter` has simplified retry. Wire full circuit breakers per concierge.mmd L285:

- **CB_ORCHESTRATOR**: `CircuitBreaker("CB_ORCHESTRATOR", failure_threshold=3, reset_timeout_s=30)`
  - In `dispatch_envelope()`: gate MED/HIGH enqueue through CB_ORCHESTRATOR
  - OPEN → degrade MED→LOW (direct Fabric)
- **CB_FABRIC**: `CircuitBreaker("CB_FABRIC", failure_threshold=3, reset_timeout_s=30)`
  - In `dispatch_direct()`: gate LOW execution through CB_FABRIC
  - OPEN → canned response
- **CB_MCP**: `CircuitBreaker("CB_MCP", failure_threshold=2, reset_timeout_s=60)`
  - Per MCP provider (no MCP servers in POC → stub creation, actual wiring post-M10)

Touch point: EDIT `k1/concierge/dispatch/fabric_orchestrator_adapter.py` (~40 lines — add 2-3 CB instances + gate logic)

---

#### E10.3 — Latency Benchmarks

> Validate that each tier meets its budget envelope from concierge.mmd PERF_ENVELOPES.
> Benchmarks use `TestProviderPlugin` (zero-latency LLM) to isolate system overhead from
> LLM provider latency. LLM-inclusive benchmarks are informational (provider-dependent).

**Issue E10.3.1** — Create `tests/k1/concierge/benchmarks/test_latency_low.py` — LOW tier latency

Benchmark: 10 LOW-tier turns, measure P50/P95/P99 system-overhead latency.

Setup: full kernel boot with `TestProviderPlugin` (returns instantly) + real Fabric (40 POC mock capabilities — instant handlers)

Per turn:

- Inject message → measure wall-clock time from injection to output delivery
- Subtract mock LLM response time (known ~0 ms) → pure system overhead
- Expected system overhead: ~32 ms (PERF_SYSTEM)
- Budget: total < 2 s (PERF_ENVELOPES) — with 0 ms LLM, should be < 100 ms

Assertions:

- P99 system overhead < 200 ms (generous margin for CI environment)
- P50 system overhead < 100 ms
- No turn exceeds 2 s total
- Tool calls per turn ≤ 6 (LoopBudget LOW)
- Output tokens per turn ≤ 500

Touch point: NEW file `tests/k1/concierge/benchmarks/test_latency_low.py` (~20 tests)

**Issue E10.3.2** — Create `tests/k1/concierge/benchmarks/test_latency_medium.py` — MEDIUM tier latency

Benchmark: 5 MEDIUM-tier turns, measure system-overhead latency (excluding Orchestrator queue wait).

Setup: full kernel + Orchestrator with `TestProviderPlugin`

Per turn:

- Measure: dispatch → Orchestrator dequeue → Fabric × 1-2 → AggregatedResult → DELIVERING
- Expected: < 500 ms system overhead (Orchestrator adds envelope processing + StepRunner)
- Budget: total < 10 s (with 0 ms LLM)

Assertions:

- P99 system overhead < 1 s
- Orchestrator dispatch latency < 50 ms (envelope creation + enqueue)
- Fabric execution × 2 < 100 ms (mock handlers)
- No turn exceeds 10 s total
- Tool calls per turn ≤ 10 (LoopBudget MEDIUM)
- Output tokens per turn ≤ 2,000

Touch point: NEW file `tests/k1/concierge/benchmarks/test_latency_medium.py` (~15 tests)

**Issue E10.3.3** — Create `tests/k1/concierge/benchmarks/test_latency_high.py` — HIGH tier latency

Benchmark: 3 HIGH-tier turns, measure system-overhead latency (excluding Planner LLM + Orchestrator queue).

Setup: full kernel + Orchestrator + Planner with `TestLLMAdapter` (scripted, instant responses)

Per turn:

- Measure: dispatch → Orchestrator → Planner 4-stage → DAGExecutor → Fabric × 3-5 → AggregatedResult
- Expected: < 2 s system overhead (Planner pipeline + DAG execution + result flow)
- Budget: total < 45 s (with 0 ms LLM) — should be < 5 s

Assertions:

- P99 system overhead < 5 s
- Planner pipeline (4 stages) < 2 s with instant LLM
- DAGExecutor (5 steps) < 500 ms with mock Fabric
- No turn exceeds 45 s total
- Tool calls per turn ≤ 15 (LoopBudget HIGH)
- Output tokens per turn ≤ 8,000

Touch point: NEW file `tests/k1/concierge/benchmarks/test_latency_high.py` (~15 tests)

**Issue E10.3.4** — Create `tests/k1/concierge/benchmarks/test_token_budgets.py` — token budget enforcement

Verify each tier respects its token budget from concierge.mmd PERF_TOKENS + INV_TOKEN:

- LOW: `MockLLMAdapter` configured to return exactly 500 tokens → verify accepted. 501 tokens → verify LoopBudget exhaustion warning.
- MEDIUM: 2,000 tokens accepted, 2,001 triggers exhaustion.
- HIGH: 8,000 tokens accepted, 8,001 triggers exhaustion.
- Intent ack: 150 tokens max (INV-19). Verify `acknowledge_request()` output ≤ 150 tokens.
- Preliminary ack: 200 tokens max (INV-20). Verify COMPANIONING ack ≤ 200 tokens.
- Clarification: 300 tokens max (INV-21). Verify clarification question ≤ 300 tokens.
- Context window: verify `HubRequest.constraints.max_context_tokens ≤ 128_000` (INV-18)

Touch point: NEW file `tests/k1/concierge/benchmarks/test_token_budgets.py` (~25 tests)

**Issue E10.3.5** — Create `tests/k1/concierge/benchmarks/test_rate_limits.py` — rate limit invariants

Verify rate limits from concierge.mmd INV_RATE:

- INV-08: 20 tool calls per turn hard cap. Configure `MockLLMAdapter` to request 21 tool calls → verify 20th succeeds, 21st is blocked.
- INV-09: 3 clarification rounds per intent. Simulate 4 clarification cycles → verify 3rd completes, 4th is rejected.
- INV-10: Output queue depth 50. Queue 51 messages → verify 50 delivered, 51st blocked or dropped.
- INV-11: Workflow execution depth 3. Trigger nested workflows → verify depth 3 succeeds, depth 4 blocked.
- INV-12: 1 concurrent active turn per session. Attempt 2 concurrent turns → verify second is queued/rejected.

Touch point: NEW file `tests/k1/concierge/benchmarks/test_rate_limits.py` (~15 tests)

---

#### E10.4 — POC Dead Code Cleanup

> After M5 (Big Copy), all 22 production directories exist in BOTH `poc/k1_poc/` (original) and
> `k1/concierge/` (production home). The original POC files are dead code — only `demo/` and
> `testing/` should remain. Archive or delete the copied directories.

**Issue E10.4.1** — Verify no lingering `poc.k1_poc` imports in `k1/`

Before archival, ensure zero `poc.k1_poc` references remain in production code:

- `grep -r "poc\.k1_poc" k1/ --include="*.py"` → must return 0 results
- `grep -r "poc\.k1_poc" tests/k1/ --include="*.py"` → must return 0 results
- `grep -r "from poc" k1/ --include="*.py"` → must return 0 results

If any found:

- Fix each reference (likely leftover from M5 rewrite)
- Common offenders: docstrings, comments, logger names, test fixtures

Touch point: VERIFY + fix 0-5 files in `k1/` or `tests/k1/`

**Issue E10.4.2** — Archive POC production directories

The 22 copied directories in `poc/k1_poc/` are dead code after M5. Archive them:

**Strategy**: Move to `poc/k1_poc/_archived/` with a README explaining the archive.

```
poc/k1_poc/
├── _archived/          # NEW — archived production code (live at k1/concierge/)
│   ├── README.md       # "Archived at M10. Production code at k1/concierge/."
│   ├── actors/
│   ├── bus/
│   ├── compression/
│   ├── config/
│   ├── delta/
│   ├── events/
│   ├── experience/
│   ├── fabric/
│   ├── fsm/
│   ├── identity/
│   ├── kernel/
│   ├── ledger/
│   ├── llm/
│   ├── obs/
│   ├── orchestrator/
│   ├── prompt/
│   ├── protocols/
│   ├── react/
│   ├── scheduler/
│   ├── sessionstate/
│   ├── task/
│   └── tools/
├── demo/               # STAYS — Smith family demo (references _archived/ or k1.concierge)
├── testing/            # STAYS — internal test harness
├── main.py             # STAYS — demo launcher
├── __init__.py         # STAYS
└── concierge_poc_architecture.mmd  # STAYS — historical reference
```

Commands:

```powershell
mkdir poc/k1_poc/_archived
# Move each of the 22 directories
foreach ($dir in @("actors","bus","compression","config","delta","events","experience","fabric","fsm","identity","kernel","ledger","llm","obs","orchestrator","prompt","protocols","react","scheduler","sessionstate","task","tools")) {
    git mv "poc/k1_poc/$dir" "poc/k1_poc/_archived/$dir"
}
```

Touch point: `git mv` 22 directories → `poc/k1_poc/_archived/`

**Issue E10.4.3** — Create `poc/k1_poc/_archived/README.md`

```markdown
# Archived POC Production Code

These directories were the original POC implementation of the K1 Concierge.
They were copied to `k1/concierge/` during M5 (Big Copy) and are no longer
the canonical source.

**Production code**: `k1/concierge/`
**Archived at**: M10 — Integration & Hardening
**Archive date**: <commit date>

The `demo/` and `testing/` directories remain active in `poc/k1_poc/` — they
are not production code and reference the archived modules or `k1.concierge`.
```

Touch point: NEW file `poc/k1_poc/_archived/README.md`

**Issue E10.4.4** — Update `demo/` and `testing/` imports

After archival, `demo/coordinator.py` and `testing/harness/engine.py` import from `poc.k1_poc.*` — these paths still resolve because `_archived/` is under `poc/k1_poc/`:

- Option A: Update demo/testing imports to `from k1.concierge.*` (clean — demo uses production path)
- Option B: Keep as-is (imports resolve via `_archived/` sub-package path — `poc.k1_poc._archived.actors` ≠ `poc.k1_poc.actors`)
- **Decision**: Option A — update to `k1.concierge.*`. This ensures demo exercises the real production code.
- Rewrite: `sed -i 's/poc\.k1_poc/k1.concierge/g'` on `poc/k1_poc/demo/*.py` and `poc/k1_poc/testing/**/*.py`
- Exception: `poc/k1_poc/main.py` — update its imports too, or mark as deprecated
- Verify: `python -m pytest poc/k1_poc/testing/harness/ --tb=short -q` → all 207 tests pass from new imports

Touch point: EDIT ~25 files in `poc/k1_poc/demo/` and `poc/k1_poc/testing/` (import rewrite)

**Issue E10.4.5** — Delete stale test files in `tests/poc/`

After M5, tests were copied to `tests/k1/concierge/`. The original `tests/poc/` files are stale:

- Verify `tests/k1/concierge/` has all 73 migrated test files (from M5 E5.2.2)
- Archive: `git mv tests/poc/ tests/poc_archived/` (or delete if confident)
- **Decision**: Archive (safer — can verify diff later)
- Create `tests/poc_archived/README.md`: "Archived at M10. Active tests at tests/k1/concierge/."

Touch point: `git mv tests/poc/ tests/poc_archived/`

---

#### E10.5 — Architecture Diagram Updates

> 13 concierge flow diagrams exist at `architecture_diagrams/k1/conceriege_flows/`.
> These were created pre-migration and reference `poc/k1_poc/` paths, POC class names
> (e.g., `FabricPOCBridge`, `ModelHubPOCBridge`, `OrchestratorStub`), and POC-era
> wiring. Update to reflect the production layout after M6-M9.

**Issue E10.5.1** — Update `01_concierge_context_and_boundaries.mmd`

- Replace `poc/k1_poc/` paths with `k1/concierge/` paths
- Update boundary references: `FabricPOCBridge` → `Fabric` (direct), `ModelHubPOCBridge` → `ModelGatewayAdapter(ModelHubService)`, `OrchestratorStub` → `OrchestratorService`
- Add Planner subsystem to the boundary context

Touch point: EDIT `architecture_diagrams/k1/conceriege_flows/01_concierge_context_and_boundaries.mmd`

**Issue E10.5.2** — Update `05_dispatching_low_tier_llm_tool_loop_execution.mmd`

- LOW tier path: react loop → `ILLMPort` → `ModelGatewayAdapter` → `ModelHubService` → `GeminiProviderPlugin`
- Tool execution: `IDispatchPort.dispatch_direct()` → `Fabric.execute()` (not `FabricPOCBridge`)
- Update capability dispatch chain to show 9-step pipeline

Touch point: EDIT `architecture_diagrams/k1/conceriege_flows/05_dispatching_low_tier_llm_tool_loop_execution.mmd`

**Issue E10.5.3** — Update `06_dispatching_medium_high_orchestrator_planner_fabric_path.mmd`

- MEDIUM path: `IDispatchPort.dispatch_envelope()` → `FabricOrchestratorAdapter` → Orchestrator mailbox → `dispatch_medium()` → StepRunner → Fabric
- HIGH path: Orchestrator → `PlannerAdapter` → Planner mailbox → 4-stage pipeline → `CommittedPlan` → `DAGExecutor` → Fabric
- Add Planner 4-stage sub-diagram (SKETCH → EXPAND → VALIDATE → COMMIT)
- Add CB_PLANNER degradation arrow (HIGH → MEDIUM when OPEN)

Touch point: EDIT `architecture_diagrams/k1/conceriege_flows/06_dispatching_medium_high_orchestrator_planner_fabric_path.mmd`

**Issue E10.5.4** — Update `08_interrupt_handling_and_hil_roundtrip_routing.mmd`

- Add HIL Response Routing subgraph (from M9 E9.4): `k1.hil.clarification.v1` → `HILEventHandler` → `PendingClarificationStore` → user → `HILResponseDetector` → `k1.hil.clarification_response.v1` → Planner
- Show `PENDING_CLARIFICATIONS` data store
- Update with Planner HILCoordinator event flow

Touch point: EDIT `architecture_diagrams/k1/conceriege_flows/08_interrupt_handling_and_hil_roundtrip_routing.mmd`

**Issue E10.5.5** — Update `12_resilience_circuit_breakers_error_recovery_degradation.mmd`

- Add all 4 circuit breakers: CB_MODEL (M7), CB_ORCHESTRATOR (M10), CB_PLANNER (M9), CB_FABRIC (M10), CB_MCP (stub)
- Add tier degradation cascade: HIGH → MED → LOW → canned
- Add LLM cascade: RETRY → CB HALF-OPEN → CANNED_RESPONSE
- Show recovery arrows (CB reset → traffic resumes)

Touch point: EDIT `architecture_diagrams/k1/conceriege_flows/12_resilience_circuit_breakers_error_recovery_degradation.mmd`

**Issue E10.5.6** — Update remaining flow diagrams (batch)

Review and update if stale references found:

- `02_fsm_state_machine_and_transition_rules.mmd` — verify BACKGROUND_WORKING state present
- `03_acking_ultrabert_phase1_deterministic_pipeline.mmd` — verify complexity routing references 3 tiers
- `04_clarifying_entropy_minimization_and_hil_detection.mmd` — add Planner HIL awareness
- `07_companioning_progressing_delivering_output_contracts.mmd` — verify Orchestrator result flow
- `09_tool_dispatcher_allowlists_schema_gates_mutation_guard.mmd` — verify `fabric_port` path only (no old callbacks)
- `10_k1_bus_lanes_topics_publish_subscribe_map.mmd` — add Planner/Orchestrator topics (`k1.planner.*`, `k1.orchestration.*`, `k1.hil.*`)
- `11_sessionstate_single_writer_two_phase_write_paths.mmd` — verify no changes needed
- `13_concierge_real_life_step_by_step_how_it_works.mmd` — update E2E flow to show real subsystem names

Touch point: EDIT 8 `.mmd` files in `architecture_diagrams/k1/conceriege_flows/` (batch review, ~5-20 lines each)

**Issue E10.5.7** — Update `poc/k1_poc/concierge_poc_architecture.mmd` — mark as historical

Add header comment:

```
%% HISTORICAL — Original POC architecture diagram. Production layout at k1/concierge/.
%% See architecture_diagrams/k1/conceriege_flows/ for current diagrams.
```

Touch point: EDIT `poc/k1_poc/concierge_poc_architecture.mmd` (~3 lines added)

---

#### E10.6 — README & Deployment Docs

> Update documentation to reflect the post-migration production layout.

**Issue E10.6.1** — Update `k1/concierge/README.md`

Current README describes the ConciergeAgent pattern and meta-intents. After M6-M9:

- Add **Architecture** section showing the 4-subsystem stack:
  ```
  k1/concierge/ (ConciergeAgent — FSM + React Loop + tools)
  ├── k1/fabric/     (Capability Fabric — 9-step pipeline)
  ├── k1/model_hub/  (Model Hub — LLM orchestration)
  ├── k1/orchestrator/ (Orchestrator — MEDIUM/HIGH task execution)
  └── k1/planner/    (Planner — HIGH tier 4-stage planning)
  ```
- Add **Port Map** section listing all 8 Concierge outbound ports:
  - `ILLMPort` → `ModelGatewayAdapter` → `ModelHubService`
  - `IDispatchPort` → `FabricOrchestratorAdapter` → Fabric / Orchestrator / Planner
  - `IFabricPort` → `Fabric` (direct, M6)
  - `IBus` / `IMailboxRouter` / `IMailbox` → K1 Bus (M3)
  - `IStoragePort` et al. → SessionState adapters (M4)
  - Plus `IInputPort`, `IOutputPort`, `IClassificationPort`, `IDeltaPort`, `IMemoryPort`
- Add **Test Adapters** section listing the 8 test adapters from concierge.mmd
- Add **Configuration** section referencing config flags (`enable_orchestrator`, `enable_planner`, `bus_tracing_enabled`, `bus_metrics_enabled`)
- Add **Performance Targets** section with the budget envelopes table

Touch point: EDIT `k1/concierge/README.md` (~100 lines added)

**Issue E10.6.2** — Update root `readme.md` — add migration status

Add a brief section under the existing architecture description:

- "K1 Concierge POC successfully migrated to production layout at `k1/concierge/`"
- Link to `docs/plans/POC_MIGRATION_PLAN.md` for full migration details
- Note the 4-subsystem integration (Fabric, Model Hub, Orchestrator, Planner)

Touch point: EDIT `readme.md` (~10 lines added)

**Issue E10.6.3** — Create `docs/deployment/concierge_deployment.md` — deployment guide

Document how to deploy the K1 Concierge after migration:

- **Prerequisites**: Python 3.11+, `google-genai` (lazy-loaded), K1 bus, K1 Fabric, K1 Model Hub, K1 Orchestrator, K1 Planner
- **Configuration**: Config flags, `defaults.yaml` parameters (59 tunable), environment variables for API keys
- **Boot sequence**: Kernel bootstrap Phase 1-5 (Bus → SessionState → Fabric → Model Hub → Orchestrator → Planner)
- **Health checks**: Model Hub health, Fabric health, Orchestrator health, Planner health
- **Monitoring**: bus middleware (tracing, metrics), circuit breaker states, budget enforcement
- **Tier degradation**: document the cascade and canned response behavior
- **Docker**: reference existing `Dockerfile` + note any new environment variables

Touch point: NEW file `docs/deployment/concierge_deployment.md` (~150 lines)

**Issue E10.6.4** — Update `docs/deployment/docker-envelope-submission-guide.md` — reflect new paths

- Replace `poc/k1_poc/` references with `k1/concierge/`
- Update any Docker commands or paths that reference the old POC location
- Verify Dockerfile still builds correctly with new layout

Touch point: EDIT `docs/deployment/docker-envelope-submission-guide.md` (if stale references found)

---

#### E10.7 — Full Regression Suite + Final Gate

> Run every test suite across all K1 modules and verify zero regressions.
> This is the final gate before the migration is declared complete.

**Issue E10.7.1** — Run K1 Concierge test suite (migrated from POC)

- Command: `python -m pytest tests/k1/concierge/ --tb=short -q`
- Expected: ~3,054+ tests (original POC tests migrated at M5) + all new M6-M10 tests
- Gate: 100% green

**Issue E10.7.2** — Run K1 Fabric test suite

- Command: `python -m pytest tests/k1/fabric/ --tb=short -q`
- Expected: 183+ tests
- Gate: 100% green, zero regressions from Concierge wiring

**Issue E10.7.3** — Run K1 Model Hub test suite

- Command: `python -m pytest tests/k1/model_hub/ --tb=short -q`
- Expected: ~110 tests (from M7) + existing
- Gate: 100% green

**Issue E10.7.4** — Run K1 Orchestrator test suite

- Command: `python -m pytest tests/k1/orchestrator/ --tb=short -q`
- Expected: existing orchestrator tests (~14,500 lines)
- Gate: 100% green, zero regressions from Concierge cross-wiring

**Issue E10.7.5** — Run K1 Planner test suite

- Command: `python -m pytest tests/k1/planner/ --tb=short -q`
- Expected: 40 test files (~23,742 lines)
- Gate: 100% green, zero regressions from Concierge cross-wiring

**Issue E10.7.6** — Run K1 Bus test suite

- Command: `python -m pytest tests/k1/bus/ --tb=short -q`
- Gate: 100% green, middleware additions did not break anything

**Issue E10.7.7** — Run K1 SessionState test suite

- Command: `python -m pytest tests/k1/sessionstate/ --tb=short -q`
- Gate: 100% green (shim from M5 still resolves)

**Issue E10.7.8** — Run POC internal harness (via updated imports)

- Command: `python -m pytest poc/k1_poc/testing/harness/ --tb=short -q`
- Expected: 207 tests
- Gate: 100% green (E10.4.4 updated imports to `k1.concierge.*`)

**Issue E10.7.9** — Run full test suite (aggregate)

- Command: `python -m pytest tests/ poc/k1_poc/testing/harness/ --tb=short -q`
- Expected total: **3,261 (M0 baseline) + ~600 new tests (M6-M10)** = ~3,861+ tests
- Gate: 100% green
- Record final test count for migration completion report

**Issue E10.7.10** — Run new E2E + benchmark suites specifically

- Command: `python -m pytest tests/k1/concierge/test_e2e_*.py tests/k1/concierge/benchmarks/ --tb=short -q`
- Expected: ~280 tests (E10.1 + E10.3)
- Gate: 100% green, all latency assertions pass, all token budget assertions pass

---

#### E10.8 — Git Tag + Migration Completion

**Issue E10.8.1** — Final commit and tag

- Commit message: `feat: M10 Integration & Hardening — E2E tests, benchmarks, deferred item resolution, POC archival, diagram updates`
- Tag: `m10-integration-hardening-complete`
- This tag marks the **completion of the POC → K1 migration**.

**Issue E10.8.2** — Create migration completion report

Create `docs/plans/POC_MIGRATION_COMPLETION_REPORT.md`:

```markdown
# POC → K1 Concierge Migration — Completion Report

## Timeline

| Milestone | Scope | Tag |
|---|---|---|
| M0 | Pre-Flight | `m0-preflight-complete` |
| M1 | IModelPort | `m1-imodelport-complete` |
| M2 | ICapabilityPort | `m2-icapabilityport-complete` |
| M3 | IBusPort | `m3-ibusport-complete` |
| M4 | IStoragePort Audit | `m4-istorageport-audit-complete` |
| M5 | Big Copy | `m5-big-copy-complete` |
| M6 | Fabric Wiring | `m6-fabric-wiring-complete` |
| M7 | Model Hub Wiring | `m7-model-hub-wired` |
| M8 | Orchestrator Wiring | `m8-orchestrator-wired` |
| M9 | Planner Wiring | `m9-planner-wired` |
| M10 | Integration & Hardening | `m10-integration-hardening-complete` |

## Final Metrics

| Metric | Value |
|---|---|
| Total test count (M0 baseline) | 3,261 |
| Total test count (M10 final) | ~3,861+ |
| New tests added (M6-M10) | ~600 |
| Production files migrated | 277 .py + 24 non-.py |
| Import paths rewritten | 3,303+ |
| K1 subsystems wired | 4 (Fabric, Model Hub, Orchestrator, Planner) |
| POC bridges removed | 3 (FabricPOCBridge, ModelHubPOCBridge, OrchestratorStub) |
| New K1 services built | ModelHubService, GeminiProviderPlugin, ModelSelector, BudgetEnforcer |
| New Concierge ports | 3 (ILLMPort, IDispatchPort, IFabricPort) |
| New Concierge adapters | 5 (ModelGatewayAdapter, FabricOrchestratorAdapter, MockDispatchAdapter, HILResponseDetector, HILEventHandler) |
| Circuit breakers | 4 (CB_MODEL, CB_ORCHESTRATOR, CB_PLANNER, CB_FABRIC) |
| Architecture diagrams updated | 13 |
| POC dead code archived | 22 directories |
| Deferred items resolved | 5 (LLM validator, bus middleware, embeddings, Planner stubs, CB cascade) |

## Post-Migration Tracks (Not in Scope)

- Model Hub Hardening: multi-provider, manifest scanning, response cache, rate limiter
- Workflow subsystem activation (real IWorkflowStoragePort)
- MCP connector integration
- K0 Bridge real WAL writes
- Crash recovery infrastructure
- Admin API
- Rust bus backend parity
```

Touch point: NEW file `docs/plans/POC_MIGRATION_COMPLETION_REPORT.md` (~80 lines)

### Structural Gap Analysis

| Aspect | Before M10 (Post-M9) | After M10 | Impact |
|---|---|---|---|
| E2E tests | Per-milestone unit/integration only | 3-turn conversation flows for LOW, MEDIUM, HIGH + CRISIS + degradation | Full-stack validation across all tiers |
| Latency verification | No benchmarks | P50/P95/P99 system overhead measured, budget envelope assertions | Performance regression detection |
| Token budget enforcement | Configured but untested E2E | Per-tier budget tests (500/2K/8K + ack/prelim/clarification limits) | Invariant compliance verified |
| Rate limits | Configured but untested E2E | INV-08 through INV-12 verified | Safety invariants enforced |
| LLM validator | Option A shim (_hub_to_legacy) | Option B: direct HubResponse acceptance, shim removed | Cleaner contract, less translation |
| Bus middleware | Zero (POC default) | TopicValidation (soft) + Tracing (flag) + Metrics (flag) | Observable bus, topic safety net |
| Fabric discovery | Domain-only (stub embeddings) | Real embeddings (if infra ready) or documented gap | Intent-based search quality |
| Planner stubs | TestLLMAdapter + TestBridgeAdapter | Real LLMGatewayAdapter + real/POC BridgeAdapter | Planner uses real LLM for planning |
| Circuit breakers | CB_PLANNER only (M9) | CB_ORCHESTRATOR + CB_FABRIC + CB_MCP added | Full resilience cascade |
| POC dead code | 22 dirs in poc/k1_poc/ (duplicated) | Archived to poc/k1_poc/_archived/ | Clean separation, no confusion |
| Demo/testing imports | `poc.k1_poc.*` (original path) | Updated to `k1.concierge.*` (production path) | Demo exercises production code |
| Architecture diagrams | Pre-migration references | All 13 flow diagrams updated to production layout | Accurate documentation |
| Deployment docs | 2 files, basic | + concierge_deployment.md (comprehensive) | Deployable |
| Completion report | None | POC_MIGRATION_COMPLETION_REPORT.md | Audit trail |

### Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| E2E tests reveal integration bug between subsystems | HIGH | Per-milestone unit tests already cover individual boundaries; E2E catches composition issues |
| Latency benchmarks fail in CI (different hardware) | MEDIUM | Use generous margins (2× expected); document baseline hardware; mark as "informational" not "blocking" |
| POC archival breaks demo scripts | MEDIUM | E10.4.4 updates demo/testing imports before archival; verify harness still runs |
| Embedding port not available → discovery regression | LOW | Domain-based filtering still works (M6 verified); intent-based deferred gracefully |
| Planner with real LLM exposes latency issues | MEDIUM | Budget enforcer caps spend; Planner timeout is 10s/stage; TestLLMAdapter path preserved for fast CI |
| CB cascade introduces flaky tests (timing-dependent) | MEDIUM | Use deterministic failure injection (not timeouts); CB reset before each test |
| Diagram updates miss a stale reference | LOW | `grep -r "poc.k1_poc\|FabricPOCBridge\|ModelHubPOCBridge\|OrchestratorStub" architecture_diagrams/` before commit |

### Summary Metrics

| Metric | Count |
|---|--:|
| New E2E test files | 5 (`test_e2e_low_tier.py`, `test_e2e_medium_tier.py`, `test_e2e_high_tier.py`, `test_e2e_tier_degradation.py`, `test_e2e_crisis.py`) |
| New benchmark test files | 3 (`test_latency_low.py`, `test_latency_medium.py`, `test_latency_high.py`, `test_token_budgets.py`, `test_rate_limits.py`) |
| New documentation files | 2 (`concierge_deployment.md`, `POC_MIGRATION_COMPLETION_REPORT.md`) |
| Files edited (deferred items) | ~8 (`validator.py`, `loop.py`, `setup.py`, `bootstrap.py`, `planner_wiring.py`, `fabric_orchestrator_adapter.py`, config) |
| Architecture diagrams updated | 13 + 1 historical marker |
| POC directories archived | 22 |
| POC test directory archived | 1 (`tests/poc/` → `tests/poc_archived/`) |
| Demo/testing files rewritten | ~25 (import path updates) |
| New tests (E10 total) | ~350 (E2E ~250 + benchmarks ~90 + rate limits ~15) |
| Deferred items resolved | 5 of 8 (3 remain post-M10) |
| Final total test count | ~3,861+ (M0 baseline 3,261 + ~600 M6-M10) |

---

## Dependency Graph

```
M0 (Pre-Flight)
 ├── M1 (IModelPort)
 ├── M2 (ICapabilityPort)
 ├── M3 (IBusPort)
 └── M4 (IStoragePort Audit)
      │
      ▼
M5 (The Big Copy) ← requires M1-M4 all green
 ├── M6 (Fabric Wiring)
 ├── M7 (Model Hub Wiring)
 │    │
 │    ▼
 ├── M8 (Orchestrator Wiring) ← requires M6 + M7
 │    │
 │    ▼
 └── M9 (Planner Wiring) ← requires M8 (future)
      │
      ▼
M10 (Integration & Hardening) ← requires M6-M9
```

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Import path breakage during Big Copy | HIGH | Automated find-replace script + test gate |
| Fabric provider registration mismatch | MEDIUM | Contract tests per capability before swap |
| Model Hub latency regression | MEDIUM | A/B benchmark: direct adapter vs Model Hub |
| Orchestrator state management conflicts | HIGH | Orchestrator is stateless actor — verify no SS writes |
| Test coverage gaps from POC→production move | HIGH | M0 establishes baseline coverage report |

---

## Appendix: File Count Estimates

| Source | Files | Lines (approx) |
|--------|-------|-----------------|
| `poc/k1_poc/fsm/` | 18 | ~3,500 |
| `poc/k1_poc/react/` | 3 | ~800 |
| `poc/k1_poc/prompt/` | 9 | ~2,000 |
| `poc/k1_poc/protocols/` | 18 | ~3,000 |
| `poc/k1_poc/sessionstate/` | 20+ | ~4,000 |
| `poc/k1_poc/actors/` | 4+ | ~600 |
| `poc/k1_poc/tools/` | 7 | ~1,500 |
| `poc/k1_poc/llm/` | 3+ | ~500 |
| `poc/k1_poc/bus/` | 5+ | ~400 |
| Other (`delta/`, `events/`, etc.) | 15+ | ~2,000 |
| **Total** | **~100+** | **~18,000+** |
