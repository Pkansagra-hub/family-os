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
| _(not in POC)_ | `capabilities: list[str]` | **NEW** — must be populated from intent/tool resolution |
| _(not in POC)_ | `params: dict[str, dict]` | **NEW** — per-capability params |

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
| `planner` | _(test adapter from factory)_ | Mock — real Planner is M9 |
| `bridge` | _(test adapter from factory)_ | Mock — real K0 Bridge deferred |
| `storage` | _(test adapter from factory)_ | Mock — workflow storage deferred |

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

## M9 — K1 Planner Wiring (Future)

> HIGH tier tasks route through `k1/planner/` 4-stage pipeline before Orchestrator execution.

**Work**:

- Planner 4-stage pipeline: Sketch → Expand → Validate → Commit
- Planner discovery tools: `discover_capabilities()`, `recall_for_planning()`, `query_planning_context()`
- CommittedPlan → Orchestrator → Fabric DAG execution
- Verify HIGH tier E2E: complex multi-step task → plan → execute → deliver

**Note**: This milestone is future. Defer until M8 is stable.

### Epics
<!-- TBD -->

### Issues
<!-- TBD -->

---

## M10 — Integration & Hardening

> Full regression, performance benchmarks, cleanup, documentation.

**Work**:

- E2E test suite: 3-turn conversation flows (LOW, MEDIUM, HIGH)
- Latency benchmarks: LOW <2s, MEDIUM <10s, HIGH <60s
- Token budget verification per tier
- Remove POC dead code from `poc/k1_poc/` (or archive)
- Update architecture diagrams to reflect final production layout
- Update README and deployment docs

### Epics
<!-- TBD -->

### Issues
<!-- TBD -->

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
