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

> Session State already has ports/adapters in POC. Verify contracts are clean and aligned with K1 expectations.

**Existing ports**: `poc/k1_poc/sessionstate/ports/`
**Existing adapters**: `poc/k1_poc/sessionstate/adapters/`
**Work**: Audit interface alignment, add any missing contract tests

### Epics
<!-- TBD -->

### Issues
<!-- TBD -->

---

## M5 — The Big Copy

> Single mechanical move: `poc/k1_poc/` → `k1/concierge/`. Fix imports. Verify all tests pass from new location.

**What copies** (the organs):

- `fsm/` — 18 files, FSM controller + guard matrix + states
- `react/` — ReAct loop engine + history
- `prompt/` — DynamicPromptBuilder + 10 modes
- `protocols/` — OPP (8 primitives), HITL, Weave, Suspension (18 files)
- `sessionstate/` — manager + tiers + sections + ports + adapters
- `actors/` — Front + Back handlers
- `events/` — event type definitions
- `delta/` — delta applicator + aggregation
- `experience/` — 6 experience layer stubs
- `identity/` — persona engine
- `compression/` — episodic compression
- `ledger/` — idempotency ledger
- `obs/` — observability
- `task/` — task model
- `orchestrator/` — POC simple orchestrator (becomes LOW-tier path)
- `llm/` — model port + POC adapter
- `bus/` — bus port + POC adapter (or direct k1/bus/ import)
- `fabric/` — capability port + POC adapter
- `tools/` — dispatcher + schemas + implementations
- `scheduler/` — proactive scheduler
- `config/` — YAML configs (may merge with k1/config/)

**What stays behind** (not production):

- `demo/` — test harness
- `testing/` — test utilities
- `main.py` — POC entrypoint
- `concierge_poc_architecture.mmd` — moves to `k1/concierge/docs/` or `architecture_diagrams/`

**What moves to tests**:

- All POC test files → `tests/k1/concierge/`

### Epics
<!-- TBD -->

### Issues
<!-- TBD -->

---

## M6 — K1 Fabric Wiring

> Swap `ICapabilityPort` POC adapter → real `k1/fabric/` adapter. Capabilities resolve through Fabric provider resolution.

**Work**:

- Register POC capabilities as Fabric providers
- Implement `FabricGatewayAdapter` behind `ICapabilityPort`
- `discover_capabilities()` routes through Fabric retrieval
- `invoke_capability()` routes through Fabric execution engine
- Verify all 40 capabilities resolve correctly

### Epics
<!-- TBD -->

### Issues
<!-- TBD -->

---

## M7 — K1 Model Hub Wiring

> Swap `IModelPort` POC adapter → `k1/model_hub/` adapter. LLM calls route through Model Hub with proper model selection, token budgets, and fallback.

**Work**:

- Implement `ModelHubAdapter` behind `IModelPort`
- Model selection table: Front/Back × streaming/non-streaming
- Token budget enforcement at Model Hub level
- Fallback chains (pro → flash → canned)

### Epics
<!-- TBD -->

### Issues
<!-- TBD -->

---

## M8 — K1 Orchestrator Wiring

> MEDIUM tier tasks route through `k1/orchestrator/` instead of direct Front→Back dispatch.

**Work**:

- FSM DISPATCHING emits `TaskEnvelope` to Orchestrator for MEDIUM tier
- Orchestrator resolves capabilities through Fabric (via its own `FabricGatewayPort`)
- Results flow back through `k1.orchestration.dag.completed.v1`
- LOW tier remains direct Front→Back (unchanged)
- Verify MEDIUM tier E2E: user input → orchestrator → fabric → result → delivery

### Epics
<!-- TBD -->

### Issues
<!-- TBD -->

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
