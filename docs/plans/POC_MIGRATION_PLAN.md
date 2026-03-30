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

## M2 — Port: ICapabilityPort

> Extract capability resolution boundary. Back's `invoke_capability()` calls port instead of flat dict lookup.

**Boundary**: `poc/k1_poc/fabric/family_capabilities.py` → `CAPABILITY_HANDLERS` dict
**Callers**: `tools/implementations.py` (`execute_invoke_capability`), `tools/dispatcher.py`
**Port location**: `poc/k1_poc/fabric/ports/capability_port.py`
**POC adapter**: `poc/k1_poc/fabric/adapters/dict_capability_adapter.py` (wraps existing dict)
**K1 adapter** (M6): `k1/concierge/fabric/adapters/fabric_gateway_adapter.py`

### Epics
<!-- TBD -->

### Issues
<!-- TBD -->

---

## M3 — Port: IBusPort

> Normalize bus instantiation to match `k1/bus/ports/bus.py` interface.

**Boundary**: `poc/k1_poc/bus/` → direct `LocalBus` + `TimingChain` instantiation
**Callers**: `kernel/bootstrap.py`, `fsm/controller.py`, `actors/*.py`
**Port location**: `poc/k1_poc/bus/ports/bus_port.py`
**Status**: POC bus IS the k1 bus implementation — mostly an import-path alignment

### Epics
<!-- TBD -->

### Issues
<!-- TBD -->

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
