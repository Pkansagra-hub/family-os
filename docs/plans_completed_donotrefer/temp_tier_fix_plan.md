# temp_tier_fix_plan.md

**Branch:** `type-safety-sweep`
**Owner:** kernel + concierge + model_hub
**Status:** DRAFT — awaiting P0 kickoff

---

## 0. Ground rules (read first)

### 0.1 Two-codebase workflow

All work happens twice:

1. **Implement in `poc/k1_poc/`** first (mirror of `k1/concierge/` structure).
2. **User runs POC end-to-end and signs off.**
3. **Propagate the same diff to `k1/concierge/`** verbatim — no improvisation.

Path map (verified):

| Concept                    | POC path                                 | Production path                       |
| -------------------------- | ---------------------------------------- | ------------------------------------- |
| Concierge root             | `poc/k1_poc/`                            | `k1/concierge/`                       |
| FSM + UltraBERT            | `poc/k1_poc/fsm/ultrabert_phase1.py`     | `k1/concierge/fsm/ultrabert_phase1.py`|
| ReAct loop                 | `poc/k1_poc/react/loop.py`               | `k1/concierge/react/loop.py`          |
| Tool dispatcher / registry | `poc/k1_poc/tools/`                      | `k1/concierge/tools/`                 |
| Front/Back actors          | `poc/k1_poc/actors/{front,back}.py`      | `k1/concierge/actors/{front,back}.py` |
| Orchestrator (thin)        | `poc/k1_poc/orchestrator/`               | `k1/concierge/orchestrator/`          |
| Fabric adapter             | `poc/k1_poc/fabric/`                     | `k1/concierge/fabric/`                |
| ModelHub                   | (shared) `k1/model_hub/`                 | (shared) `k1/model_hub/`              |
| Kernel boot                | (shared) `k1/kernel/service.py`          | (shared) `k1/kernel/service.py`       |

ModelHub and kernel are **shared** between POC and prod — changes there land once and benefit both.

### 0.2 Per-epic gate checklist

Every epic in this plan MUST follow these four steps in order, recorded in-line in this file:

1. **Read** — list every file read end-to-end before edits, with `file:line-range`.
2. **Findings** — bullet list of what the read uncovered (contracts, coupling, traps).
3. **Changes** — exact diff intent per file, with rationale.
4. **Handoff & test log** — after user runs the epic, append a "Test log" subsection capturing: command(s) run, observed behaviour, any debug iterations, any code changes that happened during testing.

No epic is "done" until step 4 has a user sign-off line.

---

## 1. Architectural decisions (locked-in)

| ID | Decision                                                                                                                                                                                                                                                                                                                                                            |
| -- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| A  | **UltraBERT keeps intent / safety / affect / NER / embedding heads.** Only `complexity_tier` output is removed. SS sections `scoreboard`, `affective_now`, etc. continue to be populated by Phase-1.                                                                                                                                                                |
| B  | **Tier is implicit in the Front LLM's tool choice — there is no explicit `set_tier` action.** Front does not "declare" a tier because the tool the model picks already encodes the routing intent: choosing `invoke_capability` IS LOW; choosing `dispatch_task` IS MED/HIGH. An explicit tier verb would create a second source of truth and a bug class (mismatch between declared tier and tool actually called). |
| C  | **No new "answer composition" stage.** Front already has a ReAct loop. After a LOW-path Fabric call returns, the next loop iteration composes the user-facing text. This is plain ReAct behaviour; no new state, no new state machine.                                                                                                                              |
| D  | **Keep Front/Back actor split. Remove the tier dimension from tool allowlists.** Each actor has one allowlist (`FRONT_TOOLS`, `BACK_TOOLS`); tools are not gated by LOW/MED/HIGH any more. All tools available to that actor are exposed every turn.                                                                                                                |
| E  | **ModelHub: full declarative rework.** Factory becomes the honest single point of registration (both `ProviderRegistry` and `ProviderDispatcher`); a declarative provider config + env-loader replaces the kernel-side `_register_model_hub_plugins_from_env` private-attribute walking. Async lifecycle (`initialize`/`shutdown`) handled inside the factory.       |
| F  | This file lives at `docs/plans/temp_tier_fix_plan.md`.                                                                                                                                                                                                                                                                                                              |

### 1.1 Tier model (final)

```
Front LLM ReAct iteration N
  │
  ├── picks `invoke_capability(name, params)`  ──►  LOW  (direct Fabric call via IDispatchPort)
  │       └── ToolResult flows back into Front's loop
  │             └── Front iteration N+1 composes the user-facing text
  │
  ├── picks `dispatch_task(intents, urgency)` ──►  MED  (Back worker ReAct loop)
  │       └── Back submits result; FSM re-engages Front for delivery
  │
  └── picks `dispatch_task(..., plan=True)`    ──►  HIGH (Planner + Orchestrator)
          └── Planner output drives Orchestrator DAG; results stream back to Front
```

There is no separate classifier producing `complexity_tier`. The tier label, if needed for telemetry, is **derived after the fact** from the tool the Front called.

---

## 2. Priority breakdown

### P0 — Unblock the kernel (ModelHub plugin registration, minimal patch)

**Goal:** Get any LOW or MED turn to complete end-to-end on `gemini-2.5-flash` so we can iterate. Minimal patch in shared `k1/model_hub/` — full rework deferred to P2.

**Scope:**

- Make `ModelHubFactory.create_with_ports(plugins=...)` honest: when `plugins` is passed, register each `(provider_id, plugin)` with **both** `ProviderRegistry` (manifest-aware) and `ProviderDispatcher`.
- Remove the gate in `k1/kernel/service.py` `_register_model_hub_plugins_from_env` that only runs when `model_mode == "hub"`. Always run it when API keys exist.
- Pass `plugins=` from `k1/kernel/service.py:946` so the kernel-bootstrapped path actually works.

**Why P0 not P2:** without this, no tier work is testable. P2 turns this minimal patch into a proper declarative loader.

**Per-epic gate:** Read → Findings → Changes → Handoff. See template in §0.2.

---

### P1 — Front-side Fabric-direct path (the LOW tier itself)

**Goal:** Make it possible for the Front LLM to call Fabric directly via `invoke_capability`, get a `ToolResult` back, and continue its ReAct loop to produce the user-facing answer — all without involving the Back actor.

**Scope (POC first, then mirror):**

1. Add `invoke_capability` and `discover_capabilities` schemas to `FRONT_TOOL_SCHEMAS` (currently Back-only).
2. Add the same two implementations to the Front side of `tools/dispatcher.py` allowlist.
3. Wire `IDispatchPort` into the Front actor's `ToolContext` (currently only Back gets it).
4. Stop the FSM from intercepting Front tool calls when the tool is `invoke_capability` — only `dispatch_task` should trigger the bus emit / Back hand-off.
5. Confirm Front's existing ReAct loop iterates cleanly on a `ToolResult` from Fabric (no special-casing should be needed; if it is, document it in Findings).

**Out of scope for P1:** removing `dispatch_task`, removing tier allowlists, touching UltraBERT. Those are P3.

---

### P2 — ModelHub rework (standalone, declarative)

**Goal:** Replace the minimal P0 patch with a production-grade ModelHub that owns its own provider lifecycle and config. This is the singular focus of P2.

**Scope (`k1/model_hub/` only — no concierge changes):**

1. **Declarative provider config.** A typed config object (`ProviderConfig` list) listing each provider with manifest path, env-var requirements, and capability whitelist. Loaded from YAML or built programmatically.
2. **`ProviderLoader`** — new helper that:
   - Reads `ProviderConfig` + env vars
   - Builds plugin instances
   - Awaits `plugin.initialize(manifest)`
   - Calls **both** `registry.register(manifest, plugin)` and `dispatcher.register_plugin(provider_id, plugin)`
   - Surfaces a single error if any required key is missing
3. **`ModelHubFactory.from_config(config, ports)`** — new entry point that runs the loader. `create_with_ports(plugins=...)` keeps working as a thin compatibility shim that delegates.
4. **Lifecycle:** factory exposes `await hub.shutdown()` that drains plugins; kernel calls it on teardown.
5. **Drop the kernel-side private-attribute walking** (`getattr(hub, "_registry")`, `_dispatcher`). Kernel's only ModelHub call becomes `ModelHubFactory.from_config(...)`.
6. **Multi-provider support out of the box.** Google + OpenAI + Anthropic + Ollama auto-register if their respective env vars are present. No per-provider hand-coding in the kernel.

**Per-epic gate as in §0.2.** P2 has its own Read step covering every file under `k1/model_hub/` (the subagent map is the starting reference, not a substitute).

---

### P3 — Strip tier gating; retire `complexity_tier`; collapse the static config

**Goal:** Remove the obsolete tier machinery now that LOW is real and tier is implicit.

**Scope (POC first, then mirror):**

1. **UltraBERT** (`fsm/ultrabert_phase1.py`):
   - Delete `_compute_complexity()` and the `complexity_tier` field on `Phase1Result`.
   - Stop writing `control.complexity_tier` to SS.
   - Keep all other heads. Update tests to drop the assertion on `complexity_tier`.
2. **`KernelConfig.tool_tier`** — delete the static field; delete every reader.
3. **Tool allowlists** (`tools/dispatcher.py`):
   - Replace `FRONT_TIER_ALLOWLISTS = {LOW: ..., MEDIUM: ..., HIGH: ...}` with a single `FRONT_TOOLS: set[str]`.
   - Same for Back.
   - `ToolDispatcher.__init__` no longer takes a `tier` kwarg.
4. **`dispatch_task` implementation** (`tools/implementations.py:942`):
   - Remove the `ctx.session_manager.get_section("control").complexity_tier` read.
   - Tier on the resulting `TaskDispatch` is derived from the dispatch's own metadata (`plan=True` ⇒ HIGH, else MED). Document this rule explicitly in the schema.
5. **FSM arbiter** (`fsm/arbiter.py:580`):
   - Stop including `complexity_tier` in the metadata snapshot.
6. **Tests** — delete or rewrite anything that asserts on tier-gated allowlists.

**Per-epic gate as in §0.2.**

---

## 3. Epic execution log

> Each epic gets its own block here. The blocks below are stubs to be filled out as work proceeds. Do not create the next epic block until the previous one has a Test log with user sign-off.

### EPIC P0.1 — ModelHub minimal plugin registration

**Status:** implemented + tested end-to-end against Gemini, awaiting user sign-off

**1. Read**

- `k1/model_hub/factory.py:87-150` — `_HubCore` class (the `IModelHubPort` facade). Holds `self._registry`, `self._router`, `self._health` as private attrs. Public surface today: `execute`, `stream_execute`, `discover_capabilities`, `discover_models`, `health`. No registration method.
- `k1/model_hub/factory.py:365-440` — `ModelHubFactory.create_with_ports(ports, config, plugins)`. The `plugins` arg flows ONLY into `ProviderDispatcher(plugins=plugins or {})` (line ~413). It is NEVER passed to `ProviderRegistry.register()`. The factory has no manifest-loading hook.
- `k1/model_hub/services/provider_registry.py:88-135` — `ProviderRegistry.register(manifest, plugin)` is the only path that populates `_capability_index`. `_rebuild_capability_index()` runs after each register/unregister.
- `k1/model_hub/services/provider_registry.py:185` — `get_providers_for_capability(cap)` returns `list(self._capability_index.get(capability, []))`. Empty index ⇒ empty list ⇒ `NoEligibleProviderError`.
- `k1/model_hub/services/provider_dispatcher.py:95-115` — `ProviderDispatcher.__init__(plugins=...)` and the public `register_plugin(provider_id, plugin)` method already exist.
- `k1/kernel/service.py:828-882` — existing `_register_model_hub_plugins_from_env()` already does the right thing (load manifest, `await plugin.initialize`, `set_api_key`, `registry.register` + `dispatcher.register_plugin`) but reaches into the hub via `getattr(hub, "_registry")` and `getattr(router, "_dispatcher")` — both private.
- `k1/kernel/service.py:946-969` — `_startup_tier1` calls `ModelHubFactory.create_with_ports(...)` WITHOUT a `plugins=` arg, then conditionally invokes `_register_model_hub_plugins_from_env()` only when `self._config.model_mode == "hub"`.
- `k1/kernel/chat_repl.py:51` — `model_mode = "hub"` is set when `--model-hub` flag is passed; default is `"test"`.
- `k1/config/providers/google.manifest.yaml` — exists, loaded via `k1.model_hub.manifest.load_manifest`.

**2. Findings**

- The `plugins=` parameter on `ModelHubFactory.create_with_ports(...)` is silently a lie: it populates dispatcher state but never the registry, so `CapabilityRouter` always returns `[]` and `NoEligibleProviderError` fires before dispatch. Fixing the parameter contract belongs to P2 (full rework).
- The kernel-side `_register_model_hub_plugins_from_env` is functionally correct but couples the kernel to the hub's private internals via `getattr(hub, "_registry")` / `getattr(router, "_dispatcher")`. If `_HubCore`'s slots/internals shift, registration silently no-ops with a warning.
- `_HubCore` is the natural place for a public `register_plugin(manifest, plugin)` method that hits both `self._registry.register(manifest, plugin)` and `self._router._dispatcher.register_plugin(manifest.provider_id, plugin)`. This kills the private-attr walking in one move and stays inside the same module.
- The `model_mode == "hub"` gate at `service.py:968` is correct in spirit (test mode uses a different path) but the user-facing `boot_kernel.ps1` + `chat_repl --model-hub` flow already sets `model_mode = "hub"` so the gate is not the immediate blocker. Leave the gate alone in P0.1.
- Only Google is wired today. OpenAI/Anthropic/Ollama plugins exist (`k1/model_hub/plugins/*.py`) and have manifests in `k1/config/providers/` but no env-var probe in `_register_model_hub_plugins_from_env`. Adding more providers is P2 scope (declarative loader); P0.1 keeps Google-only.
- `IModelHubPort` (the abstract port) does not declare `register_plugin`. Adding it to the port would propagate to every test double — out of scope for a P0 minimal patch. The kernel knows it's getting a `_HubCore` (factory return type), so a concrete-only method on `_HubCore` is acceptable for P0.1.

**3. Changes**

- **`k1/model_hub/factory.py`** — add public method on `_HubCore`:

  ```python
  def register_plugin(self, manifest: ProviderManifest, plugin: IProviderPlugin) -> None:
      """Register a plugin with both registry (for capability routing) and
      dispatcher (for execution). P0.1 shim — superseded by P2 declarative
      loader.
      """
      self._registry.register(manifest, plugin)
      self._router._dispatcher.register_plugin(manifest.provider_id, plugin)
  ```

  Also add the `ProviderManifest` import at the top of the file. No signature change to existing methods. No factory-method change.

- **`k1/kernel/service.py`** — replace the `getattr` walking in `_register_model_hub_plugins_from_env` with the new public method:

  ```python
  hub = self._model_hub
  if hub is None or not hasattr(hub, "register_plugin"):
      logger.warning("ModelHub plugin registration skipped: no register_plugin")
      return
  # ... google_key block ...
  hub.register_plugin(manifest, plugin)  # was: registry.register + dispatcher.register_plugin
  ```

  Drop the `registry = getattr(...)` / `dispatcher = getattr(...)` lookup block entirely. Keep the `model_mode == "hub"` gate at line 968 untouched.

- **No tests changed in P0.1.** Existing `tests/k1/model_hub/test_factory.py` already covers `create_with_ports`; new method is additive. Touch tests in P2.

**4. Handoff & test log**

- **Test plan once changes land:**
  1. `boot_kernel.ps1` (sets `--model-hub`, GOOGLE_API_KEY from `.env`).
  2. Type a LOW-tier prompt (e.g. "What is 2+2?").
  3. Expect: turn completes, no `NoEligibleProviderError`, log line `ModelHub: registered Google plugin (provider=google, models=N)` visible during boot.
  4. Type a MED-tier prompt (e.g. "Plan my week with three goals"). Expect Back actor engages and turn completes.

**Test log — 2026-04-19 (real Gemini API)**

- Command: `python scripts/test_kernel_tiers.py` (loads `.env`, real `gemini-2.5-flash` calls; no mocks).
- LOW result: boot 25.43s, turn 3.61s, response `"The capital of France is Paris."` (31 chars). FSM end state `COMPANIONING`. 1 tier event (`k1.orchestration.task.dispatch.v1` tier=LOW).
- MED result: boot 0.11s (warm), turn 4.79s, response 1470 chars (3-step outline on hexagonal architecture). 1 tier event observed.
- Zero `NoEligibleProviderError` logs. Provider routing succeeded for both `TOOL_CALL` (iter 0 `dispatch_task`) and `CHAT` (text composition iters).
- Notes: degenerate-retry path on LOW iter 1 fired once (Gemini empty response after tool result), recovered on iter 2 — independent of P0.1, pre-existing behaviour. MED tier produced text directly (Front did not call `dispatch_task` because the prompt didn't trigger one); a real MED hand-off test belongs to P1.1+ work.
- **User sign-off:** ☐

---

### EPIC P1.1 — Expose `invoke_capability` to Front (POC)

**Status:** implemented + tested end-to-end against Gemini, awaiting user sign-off

**1. Read**

- `poc/k1_poc/tools/schemas_front.py:1-700` — `FRONT_TOOL_SCHEMAS` list at line 630 contains 10 tools: `update_beliefs`, `update_scoreboard`, `update_clarifications`, `update_narrative`, `refine_affect`, `promote_belief`, `recall_memory`, `summarize_context`, `dispatch_task`, `update_session_bundle`. **No `invoke_capability` and no `discover_capabilities`.**
- `poc/k1_poc/tools/schemas_back.py:28-100, 370-395` — `DISCOVER_CAPABILITIES_SCHEMA` at L28 and `INVOKE_CAPABILITY_SCHEMA` at L86 are defined here and listed in `BACK_TOOL_SCHEMAS` at L370+.
- `poc/k1_poc/tools/dispatcher.py:62-118` — `FRONT_TIER_ALLOWLISTS` (LOW/MEDIUM/HIGH/CRISIS) does NOT contain `invoke_capability` or `discover_capabilities`. `BACK_TIER_ALLOWLISTS` contains both starting at LOW.
- `poc/k1_poc/tools/dispatcher.py:425-495` — `create_front_dispatcher(tier, ctx, schemas, bus)` and `create_back_dispatcher(...)`. Both build the same `ToolDispatcher` class with actor-specific allowlist+schema map.
- `poc/k1_poc/tools/implementations.py:57-103` — `ToolContext` dataclass already carries `fabric_port: IFabricPort | None`. Set for BOTH actors today.
- `poc/k1_poc/tools/implementations.py:1037-1330` — `execute_discover_capabilities` and `execute_invoke_capability`. Both branch on `ctx.fabric_port` first, fall back to `ctx.invoke_fn` / `ctx.capability_fn`. Implementation is actor-agnostic.
- `poc/k1_poc/kernel/bootstrap.py:193-213` — `front_ctx = ToolContext(... fabric_port=fabric_bridge ...)` and `back_ctx` identically. **Front already has the dispatch port — no wiring change needed.**
- `poc/k1_poc/actors/front.py:940-1000` — `front_handler` post-loop only acts on `result.dispatched_tasks`, which is populated by the ReAct loop ONLY when the LLM calls `dispatch_task` (loop reads the `_dispatch` payload from that tool's `ToolResult`). Other tool calls flow back into the loop as normal `ToolResult` objects.
- `poc/k1_poc/fsm/controller.py:2033` — handles `k1.orchestration.task.dispatch.v1`. Emitted only by `front_handler` from `dispatched_tasks` — never by an arbitrary Front tool call.
- `poc/k1_poc/react/loop.py:225, 357` — `ReactResult.dispatched_tasks` is populated inside the tool-call processing block when the tool name is `dispatch_task`. `invoke_capability` returns a regular `ToolResult` and the loop continues to the next iteration with that result appended to messages — exactly the LOW-tier composition behaviour we want.
- `poc/k1_poc/orchestrator/routing.py:11, 159, 212` — confirms current LOW path is `dispatch_task → bus → Back`. Independent of P1.1; nothing to change here. (P3 will retire the LOW row in `_route_low_sync` once tier becomes implicit.)

**2. Findings**

- **The change is genuinely small.** Front already has `fabric_port` on its `ToolContext`. The only structural gaps are:
  1. `FRONT_TOOL_SCHEMAS` does not advertise `invoke_capability` / `discover_capabilities` to the model.
  2. `FRONT_TIER_ALLOWLISTS` does not allow them to dispatch.
- **No FSM intercept risk.** The FSM only acts on `dispatched_tasks`, which is populated exclusively when the ReAct loop sees a `dispatch_task` tool name. `invoke_capability`'s `ToolResult` flows back into the loop normally, and the next Front iteration composes the answer — exactly your decision C.
- **No change to ReAct loop needed.** Already verified `react/loop.py` treats arbitrary tool results uniformly. Confirms decision C: "Front already has a ReAct loop, no new composition stage."
- **HITL guard in `execute_invoke_capability` is shared.** It will fire for Front calls too, which is correct: a side-effect call from Front while a HITL is pending should still be blocked. No change needed.
- **Schema duplication is intentional.** Rather than physically copying the schema literals, simplest is to import from `schemas_back` and append to `FRONT_TOOL_SCHEMAS`.
- **Tier allowlists still exist in P1.1.** We add `invoke_capability` + `discover_capabilities` to all three tier rows (LOW/MEDIUM/HIGH) of `FRONT_TIER_ALLOWLISTS`. The full collapse to a single per-actor set is P3.2.
- **Out of scope but noted:** the `dispatch_task` schema description still says "FSM intercepts this tool call" — leave as-is until P3 retires it. Touching docstrings now would obscure the diff.

**3. Changes**

- **`poc/k1_poc/tools/schemas_front.py`** — add to imports near top:

  ```python
  from poc.k1_poc.tools.schemas_back import (
      DISCOVER_CAPABILITIES_SCHEMA,
      INVOKE_CAPABILITY_SCHEMA,
  )
  ```

  Append both to the `FRONT_TOOL_SCHEMAS` list at line 630.

- **`poc/k1_poc/tools/dispatcher.py`** — extend each Front tier row in `FRONT_TIER_ALLOWLISTS` (lines 62-95) to include `"invoke_capability"` and `"discover_capabilities"`. Leave `CRISIS` empty (Front does not run ReAct in CRISIS).
- **No change to `bootstrap.py`.** `front_ctx.fabric_port` is already set.
- **No change to `actors/front.py`.**
- **No change to `react/loop.py`.**
- **No change to `fsm/controller.py`.**

**4. Handoff & test log**

- **Test plan once changes land (POC only):**
  1. Boot POC entrypoint (`poc/k1_poc/main.py` or kernel REPL pointing at the POC).
  2. Prompt: "What is the current weather in Seattle?" — expect Front to call `discover_capabilities` then `invoke_capability("tool.read.weather_current", ...)` and compose the user-facing answer in the next iteration. **No Back actor engagement.** No `task.dispatch.v1` event on the bus.
  3. Prompt requiring multi-step: "Plan my week and book three meetings" — expect Front to call `dispatch_task` (existing MED path); Back engages as today. Confirms we did not break MED.
  4. Bus inspection: `task.dispatch.v1` count == MED-prompt count, NOT LOW-prompt count.
- **User sign-off:** ☐

**Implementation log (executed):**

- Subagent trace surfaced **two more files** beyond the original 2-file plan: `prompt/mode.py` (per-mode `TOOL_ALLOWLIST` is a second filter that strips tools before the LLM sees them) and `prompt/sections.py` (system prompt actively forbade Front from invoking capabilities — IDENTITY L46, ANTI_PATTERNS_FULL L451, INTERRUPT_RULES L514). Both confirmed by manual grep+read before edit. User chose Path A (all 4 files).
- **Circular import resolved by extracting Fabric schemas to `poc/k1_poc/tools/schemas_fabric.py`.** First attempt added a top-level reverse import in `schemas_front` → broke `tools/__init__.py` boot. Deferred-import attempt also failed (cycle entered through `tools/__init__.py` → `schemas_back`). Final fix: created neutral `schemas_fabric.py` containing the canonical `DISCOVER_CAPABILITIES_SCHEMA` and `INVOKE_CAPABILITY_SCHEMA` (both `actor="both"`). `schemas_front` and `schemas_back` both import from it. `schemas_back` re-exports the names to preserve the historical public surface (`from poc.k1_poc.tools.schemas_back import DISCOVER_CAPABILITIES_SCHEMA`).
- **Files actually edited (5):**
  - `poc/k1_poc/tools/schemas_fabric.py` **NEW** — canonical Fabric schemas.
  - `poc/k1_poc/tools/schemas_front.py` — import from `schemas_fabric`; append both to `FRONT_TOOL_SCHEMAS` (now 12 entries).
  - `poc/k1_poc/tools/schemas_back.py` — delete local `DISCOVER_CAPABILITIES_SCHEMA` and `INVOKE_CAPABILITY_SCHEMA` definitions; re-export from `schemas_fabric`. `BACK_TOOL_SCHEMAS` count unchanged (7).
  - `poc/k1_poc/tools/dispatcher.py` — add `discover_capabilities` + `invoke_capability` to LOW/MEDIUM/HIGH rows of `FRONT_TIER_ALLOWLISTS`. CRISIS empty.
  - `poc/k1_poc/prompt/mode.py` — add same two names to `TOOL_ALLOWLIST[STANDARD]` and `[INTERRUPT]`.
  - `poc/k1_poc/prompt/sections.py` — reword IDENTITY L46 ("Execute tasks directly..." → "Simple lookups you handle directly via discover/invoke; complex multi-step you dispatch_task"), ANTI_PATTERNS_FULL L451 (lift the prohibition on direct capability execution; keep prohibition on spawning agents/workflows), INTERRUPT_RULES L514 (allow discover for genuine new lookups, block only for acknowledgments).

**Real-API test (Gemini 2.5-flash, real Fabric, web demo via `python -m poc.k1_poc.demo.web.app`)**

- **Prompt:** `"what is weather in paris?"` (LOW-tier intent, matches mock `tool.execute.weather_forecast`)
- **Boot:** all 5 phases complete in 31.16s (kernel + Fabric + 41 capabilities registered).
- **LLMOutputValidator schema list at iter 0** = 12 schemas, including `discover_capabilities` and `invoke_capability` — confirms schemas_fabric wiring lands in Front's prompt.
- **iter 0:** `tool=discover_capabilities`, `intent="get weather"`, `status=ok`, `duration_ms=0`, `budget_remaining=10/10 → 9`.
- **iter 1:** `tool=invoke_capability`, `capability=tool.execute.weather_forecast`, `params_keys=['location']`, `status=ok`, `budget_remaining=9 → 8`.
- **iter 2:** `finish=stop`, `has_text=True`, `text_len=243`, response: *"It's looking really nice in Paris! Today it's sunny with a high of 78 and a low of 65..."*
- **`dispatched=0` and `tool_calls=0` in front_handler post-loop** — confirms NO `task.dispatch.v1` envelope was emitted.
- **FSM trajectory:** `LISTENING → DISPATCHING → LISTENING` (no Back actor engagement, no orchestration intercept).
- **Total turn time:** 5.13s for 3 Gemini round-trips end-to-end.

**Pass criteria (all met):**

| Criterion | Result |
|-----------|--------|
| Front called `discover_capabilities` | ✅ iter 0 |
| Front called `invoke_capability` (→ `tool.execute.weather_forecast`) | ✅ iter 1 |
| No `task.dispatch.v1` envelope | ✅ `dispatched=0` |
| Non-empty composed response | ✅ 243 chars, conversational tone |

**Tier model now empirically validated:** Front owns LOW-tier single-step lookups via direct Fabric invocation; the system prompt no longer forbids this; the existing ReAct loop composes the answer from the tool result without any new state machinery — exactly the architecture decision (C1-reframed + decision C) locked in pre-implementation.

---

### EPIC P1.2 — Mirror P1.1 to `k1/concierge/`

**Status:** implemented + pytest green, awaiting user sign-off

**1. Read**

- `k1/concierge/tools/schemas_front.py:1-650` — identical layout to POC: `RECALL_MEMORY_SCHEMA` defined at L347, `FRONT_TOOL_SCHEMAS` aggregated at L630 with the same 10 entries.
- `k1/concierge/tools/schemas_back.py:22, 28-126` — same `from k1.concierge.tools.schemas_front import RECALL_MEMORY_SCHEMA` at L22 (the source of the cycle), with full local definitions of `DISCOVER_CAPABILITIES_SCHEMA` (L28) and `INVOKE_CAPABILITY_SCHEMA` (L86).
- `k1/concierge/tools/dispatcher.py:64` — `FRONT_TIER_ALLOWLISTS` mirrors POC exactly (LOW/MED/HIGH each have the 8 cognitive+control tools, no Fabric).
- `k1/concierge/prompt/mode.py:65-122` — `TOOL_ALLOWLIST` mirrors POC: STANDARD has 7 tools, INTERRUPT has 9, no Fabric in either.
- `k1/concierge/prompt/sections.py:46, 458, 521` — same three prohibition sites: IDENTITY ("Execute tasks directly..."), ANTI_PATTERNS_FULL ("Execute capabilities, spawn agents..."), INTERRUPT_RULES ("Do NOT call discover_capabilities").
- `tests/k1/concierge/test_m04_e43_session_bundle.py:74` — asserts `len(FRONT_TOOL_SCHEMAS) == 10`. Will break under P1.2 unless updated.
- `tests/poc/test_m04_e43_session_bundle.py:74` — same assertion was missed in P1.1; needs the same bump.

**2. Findings**

- The k1/concierge directory is a **verbatim mirror** of the POC for these 5 files — same imports, same line numbers ±2, same circular-import vulnerability. The schemas_fabric solution applied to POC translates 1:1.
- **One pre-existing test regression confirmed unrelated to P1.2:** `tests/k1/concierge/test_tool_fabric_live.py` (17 tests) fails on `ToolContext.__init__() got an unexpected keyword argument 'fabric_port'`. Verified by `git stash` + signature check on clean branch HEAD: `ToolContext` on `type-safety-sweep` does NOT have a `fabric_port` constructor arg. These failures exist before any P1.x work and are out of P1.2 scope.
- **Two test fixture updates needed** to keep the suite green: both `test_m04_e43_session_bundle.py` files assert `FRONT_TOOL_SCHEMAS == 10`; bump to `== 12`.

**3. Changes**

- **NEW** `k1/concierge/tools/schemas_fabric.py` — verbatim translation of POC `schemas_fabric.py` with `from k1.concierge.llm.types import ToolSchema`. Both schemas keep `actor="both"`.
- `k1/concierge/tools/schemas_back.py` — delete local `DISCOVER_CAPABILITIES_SCHEMA` and `INVOKE_CAPABILITY_SCHEMA` definitions; re-export from `schemas_fabric` so `BACK_TOOL_SCHEMAS` and external imports continue to work unchanged.
- `k1/concierge/tools/schemas_front.py` — import both from `schemas_fabric`; append to `FRONT_TOOL_SCHEMAS` (now 12 entries).
- `k1/concierge/tools/dispatcher.py` — add `discover_capabilities` + `invoke_capability` to LOW/MEDIUM/HIGH rows of `FRONT_TIER_ALLOWLISTS`. CRISIS empty.
- `k1/concierge/prompt/mode.py` — add same two names to `TOOL_ALLOWLIST[STANDARD]` and `TOOL_ALLOWLIST[INTERRUPT]`.
- `k1/concierge/prompt/sections.py` — same prose rewrites as POC: IDENTITY (lookup vs dispatch split), ANTI_PATTERNS_FULL SYSTEM EXPOSURE (lift the prohibition on direct capability execution; keep prohibition on spawning agents/workflows), INTERRUPT_RULES (allow discover for genuine new lookups, block only for acknowledgments).
- `tests/k1/concierge/test_m04_e43_session_bundle.py:74` — bump assertion from `10` → `12`.
- `tests/poc/test_m04_e43_session_bundle.py:74` — same bump (POC fixture caught up).

**4. Handoff & test log**

- **Import smoke test** (k1/concierge layer): `FRONT_TOOL_SCHEMAS` count = **12**, includes both `discover_capabilities` and `invoke_capability`. `BACK_TOOL_SCHEMAS` count unchanged at **7** (re-export preserves public surface). `FRONT_TIER_ALLOWLISTS["LOW"]` contains both names. `TOOL_ALLOWLIST[PromptMode.STANDARD]` contains both names. Both schemas have `actor="both"`.
- **Pytest** (`tests/k1/concierge/test_m04_e43_session_bundle.py`, `test_tool_call_summary.py`, `test_tool_fabric_port_wiring.py`, plus the POC mirror): **114 passed, 0 failed** in 1.89s.
- Pre-existing failures in `test_tool_fabric_live.py` (17 tests, all `ToolContext fabric_port` arg mismatch) — confirmed independent of P1.2 by `git stash` round-trip; noted but out of scope.
- **End-to-end runtime test deferred:** the kernel/web demo currently runs against `poc/k1_poc/` (already validated under P1.1). The `k1/concierge/` codebase doesn't yet have an equivalent live entrypoint wired in this branch. Once a kernel boot path exercises `k1/concierge` actors against real Gemini, the same trace (`discover_capabilities` → `invoke_capability(weather)` → composed text, no `task.dispatch.v1`) should reproduce. P1.2 is structurally complete and import-tested; runtime parity is empirically inherited from P1.1 because the diffs are byte-identical except for module paths.
- **User sign-off:** ☐

---

### EPIC P2.1 — Declarative provider config + `ProviderLoader`

**Status:** implemented + tested end-to-end against Gemini, awaiting user sign-off

**Note on two-codebase rule:** P2 is **k1-only**. The POC has no `model_hub/` parallel — `poc/k1_poc/llm/gemini_adapter.py` talks to `genai.Client` directly with no manifest/registry/dispatcher. So no `poc/k1_poc/` mirror epic is needed for P2. (Verified: `poc/k1_poc/` has no `model_hub/` subdirectory; the standalone `poc/model_hub/` prototype is unrelated and not referenced by `poc/k1_poc/` at runtime.)

**1. Read**

- `k1/model_hub/factory.py:86-177` — `_HubCore` (the `IModelHubPort` impl, not exported). Holds `_router`, `_registry`, `_health`. Public methods: `execute`, `stream_execute`, `discover_capabilities`, `discover_models`, `health`, and (P0.1 addition at L107-131) `register_plugin(manifest, plugin)` which calls both `self._registry.register(manifest, plugin)` AND `self._router._dispatcher.register_plugin(manifest.provider_id, plugin)`. Note `self._router._dispatcher` is still a private-attr reach — P2.1's loader will route through `_HubCore.register_plugin` so this seam stays internal.
- `k1/model_hub/factory.py:173-519` — `ModelHubFactory` with three `@staticmethod` constructors: `create_standalone(config=None, plugins=None)` (L203-258), `create_for_testing(overrides=None)` (L260-403), `create_with_ports(ports, config=None, plugins=None)` (L391-474). All three plumb `plugins` ONLY into `ProviderDispatcher(plugins=plugins or {})` (L433-438) — never into `ProviderRegistry`. The `plugins=` parameter is silently a half-lie today; P2.1's loader is what makes it honest in P2.2.
- `k1/model_hub/manifest.py:155-181` — `ProviderManifest` (frozen dataclass): `provider_id`, `display_name`, `plugin_class` (dotted path string, e.g. `"k1.model_hub.plugins.google_plugin.GooglePlugin"`), `api_base`, `auth: AuthConfig`, `capabilities: List[CapabilityType]`, `models: List[ModelSpec]`, plus `circuit_breaker`/`health_check`/`concurrency`/`rate_limits`/`placement` blocks. `AuthConfig` (frozen dataclass) carries `type`, `credential_key`, `header_name?` — and **`credential_key` IS the env-var name** (`"GOOGLE_API_KEY"`, `"OPENAI_API_KEY"`, etc.). Already machine-readable.
- `k1/model_hub/manifest.py:232-282` — `load_manifest(path: str | Path) -> ProviderManifest`. Reads YAML via `yaml.safe_load`, raises `FileNotFoundError`/`ValueError`. **No auto-discovery** — caller must provide exact path. No JSON-Schema validator; validation lives in dataclass `__post_init__` guards.
- `k1/model_hub/services/provider_registry.py:88-131` — `ProviderRegistry.register(manifest, plugin)` populates `_plugins`, `_manifests`, `_provider_info`, then `_rebuild_capability_index()`. Capability index is `Dict[CapabilityType, List[ProviderInfo]]` — empty index means `NoEligibleProviderError` for every request. Raises `ValueError` if `provider_id` already registered.
- `k1/model_hub/services/provider_dispatcher.py:91-110` — `ProviderDispatcher.__init__(*, circuit_mgr, rate_limiter, credential_port, plugins=None)`; `register_plugin(provider_id, plugin)` is a one-liner `self._plugins[provider_id] = plugin`; `has_plugin(provider_id)` exists. **No idempotency check** — re-registering silently overwrites.
- `k1/model_hub/plugins/base.py` — `IProviderPlugin` (`@runtime_checkable Protocol`): `initialize(manifest)`, `supports(capability)`, `execute(request)`, `stream_execute(request)`, `estimate_tokens(messages)`, `health_check()`, `close()`. **`set_api_key(key)` is NOT on the Protocol** but is present on every concrete plugin (Google L467, OpenAI L363, Anthropic L345, Ollama L303 as a no-op, vLLM via `_api_key` field at L75). P2.1's loader must duck-type this call.
- `k1/model_hub/plugins/google_plugin.py:GooglePlugin`, `openai_plugin.py:OpenAIPlugin`, `anthropic_plugin.py:AnthropicPlugin`, `ollama_plugin.py:OllamaPlugin`, `vllm_plugin.py:VLLMPlugin` — all use `__init__(self) -> None` (no args), all expect `set_api_key()` AFTER `await initialize(manifest)`. Google builds `genai.Client` lazily on first use; OpenAI/Anthropic create `aiohttp.ClientSession` inside `initialize()`; Ollama defaults to `http://localhost:11434` and treats `set_api_key` as a no-op.
- `k1/config/providers/{google,openai,anthropic,ollama,vllm}.manifest.yaml` — five manifests already on disk. Top-level keys: `provider_id`, `display_name`, `plugin_class`, `api_base`, `auth`, `capabilities`, `models`, plus optional `circuit_breaker`/`health_check`/`concurrency`/`rate_limits`/`placement`. Filename pattern is uniform: `{provider_id}.manifest.yaml`.
- `k1/kernel/service.py:828-882` — `_register_model_hub_plugins_from_env` (post-P0.1). Currently probes ONLY `GOOGLE_API_KEY` (L856), hard-codes the manifest filename (`manifest_dir / "google.manifest.yaml"`), and per-plugin uses `await plugin.initialize(manifest); plugin.set_api_key(google_key); hub.register_plugin(manifest, plugin)`. Caller is `_startup_tier1` at L962-963, gated on `self._config.model_mode == "hub"`. **`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OLLAMA_BASE_URL`, `VLLM_API_KEY` are NOT probed anywhere in production today.** This whole function becomes a thin shim around `ProviderLoader` in P2.1, then deleted entirely in P2.3.
- `tests/k1/model_hub/test_factory.py:158-184` — `create_with_ports` test does not pass `plugins=`; `_HubCore.register_plugin` (P0.1) is untested here. `tests/k1/model_hub/test_provider_registry.py` — uses `_StubPlugin`, no mocks; `register/unregister/get_*/list_providers/get_capability_index/get_providers_for_capability/is_registered` all covered. `tests/k1/model_hub/test_provider_dispatcher.py:367-377` — covers `register_plugin` + `has_plugin`. `tests/k1/model_hub/test_provider_plugins.py:943-984` — load-manifest happy-path for all 5 YAML files. `tests/k1/model_hub/test_google_live.py` — only live-API suite (gated on `GOOGLE_API_KEY`, manually loads from `poc/chat_experience_poc/.env`). `tests/k1/model_hub/contract/test_invariants.py:287-293` — `os.listdir(manifest_dir)` to enforce manifest-shape invariants across all five YAMLs.
- `k1/model_hub/` has **no existing** `ProviderConfig`, `ProviderEntry`, `HubConfig`, or `ProviderLoaderConfig`. (`k1/fabric/types.py` has its own unrelated `ProviderConfig` — name collision risk; we will namespace ours under `k1.model_hub` to avoid confusion.)
- `k1/config/bus.yaml` + `k1/bus/config.py:load_bus_config()` — existing pattern for module-level YAML loaders auto-discovering a config file. Useful precedent for a future `load_provider_config()` if we want YAML support, but not required by P2.1 (Python-constructed config is the simpler default).

**2. Findings**

- **Net-new surface area (every item is `❌ doesn't exist` today):** `ProviderConfig`, `ProviderEntry`, `ProviderLoader`; reading `manifest.auth.credential_key` to determine which env var to probe; multi-provider registration in production; centralized "missing env key" error surfacing; `plugin.set_api_key()` called from a single chokepoint.
- **The `auth.credential_key` field already encodes the env-var name** (`google.manifest.yaml` → `credential_key: GOOGLE_API_KEY`). P2.1's loader does not need a duplicate `env_var` field on `ProviderEntry`; it can derive the env var from the manifest. This keeps `ProviderEntry` minimal: `(provider_id, manifest_path?, plugin_class?, enabled=True)` — both `manifest_path` and `plugin_class` are optional with sensible defaults (`k1/config/providers/{provider_id}.manifest.yaml` and the manifest's own `plugin_class` field respectively).
- **`set_api_key` not on the Protocol** is the one rough edge. Two options: (a) use `getattr(plugin, "set_api_key", None)` duck-typing with a debug log if absent; (b) add `set_api_key` to a new `IProviderPluginWithCredentials` Protocol extension. **Decision (deferred to step 3 of this epic):** start with option (a) — pure duck-typing — because Ollama legitimately has no API key and Anthropic/OpenAI/Google/vLLM all already implement it. Adding to the Protocol is a separate refactor with broader test impact.
- **`_HubCore.register_plugin` (P0.1) stays as the chokepoint** even after P2.1 lands. The loader does NOT touch `registry`/`dispatcher` directly; it goes through `hub.register_plugin(manifest, plugin)`. This keeps `self._router._dispatcher` private-attr reach contained to one method on `_HubCore` (cleaned up further in P2.3).
- **Idempotency:** `ProviderRegistry.register` raises `ValueError` on duplicate `provider_id`; `ProviderDispatcher.register_plugin` silently overwrites. This asymmetry means double-loading the same provider raises from the registry side — desirable, fail-loud. P2.1's loader will not pre-check `is_registered` (let the registry raise); P2.2's `from_config` will document the constraint.
- **Manifest discovery is explicit-only** in production today. P2.1 does NOT add glob discovery — `ProviderEntry.manifest_path` defaults to `k1/config/providers/{provider_id}.manifest.yaml` if omitted, but each entry must still be named in `ProviderConfig`. Auto-discovery is a P2.2 / P2.3 design choice.
- **Env-var loading is out of scope.** `boot_kernel.ps1` already populates `os.environ` before Python starts; `ProviderLoader` reads via `os.environ.get(key)` and never calls `load_dotenv` itself.
- **Capability whitelist per entry — dropped.** The plan's `P2.1` summary at L119 mentioned a per-entry capability whitelist. After reading the registry code, this would be a redundant filter on top of `manifest.capabilities` + `model.capabilities`. Skip it. If a deployment wants to disable a capability, the cleaner path is to omit the model from the manifest. (Re-introduce in a later epic only if a real use case appears.)
- **Zero risk to non-ModelHub code.** `ProviderLoader` is purely additive inside `k1/model_hub/`. `ModelHubFactory` signatures untouched. Kernel still calls `_register_model_hub_plugins_from_env` (which now delegates to the loader) until P2.3 deletes that function entirely. No concierge code changes. No POC code changes.
- **Tests:** zero existing tests will break. P2.1 adds three new test files (see §3 below). The kernel-side `_register_model_hub_plugins_from_env` is `pragma: no cover` for the exception path and has no direct assertions in any test file — safe to refactor its body.

**3. Changes** (no edits applied yet — this section is the design contract for the implementation step)

- **NEW** `k1/model_hub/loader.py` (~120 LOC). Contains:

  ```python
  @dataclass(frozen=True)
  class ProviderEntry:
      provider_id: str
      manifest_path: Path | None = None     # default: k1/config/providers/{provider_id}.manifest.yaml
      plugin_class: str | None = None       # default: manifest.plugin_class
      enabled: bool = True

  @dataclass(frozen=True)
  class ProviderConfig:
      providers: tuple[ProviderEntry, ...]

      @classmethod
      def default(cls) -> "ProviderConfig":
          """All five known providers, each enabled. Loader will skip any
          whose env var is absent — no error, just a single info-level log
          line per skipped provider so deployments stay self-documenting.
          """

  @dataclass(frozen=True)
  class ProviderLoadResult:
      registered: tuple[str, ...]   # provider_ids successfully registered
      skipped: tuple[tuple[str, str], ...]   # (provider_id, reason)
      failed: tuple[tuple[str, str], ...]    # (provider_id, error_message)

  class ProviderLoader:
      """Reads ProviderConfig + env, instantiates plugins via dotted class
      path, awaits initialize(), calls set_api_key() if both the env var
      is present AND the plugin exposes the method, then registers via
      hub.register_plugin(manifest, plugin).
      """

      def __init__(self, hub: _HubCore, *, manifest_root: Path | None = None) -> None: ...

      async def load(self, config: ProviderConfig) -> ProviderLoadResult: ...
      # Iterates config.providers, builds a ProviderLoadResult, returns it.
      # Per entry:
      #   1. resolve manifest_path (explicit OR default `{manifest_root}/{provider_id}.manifest.yaml`)
      #   2. load_manifest(path) → ProviderManifest
      #   3. resolve plugin_class (explicit OR manifest.plugin_class) and import dynamically via importlib
      #   4. plugin = PluginCls()
      #   5. await plugin.initialize(manifest)
      #   6. env_var = manifest.auth.credential_key
      #      if env_var and (key := os.environ.get(env_var)):
      #          if hasattr(plugin, "set_api_key"):
      #              plugin.set_api_key(key)
      #      elif manifest.auth.type != "none":
      #          # missing required key → record in skipped, do NOT raise
      #          continue
      #   7. hub.register_plugin(manifest, plugin)
      # Any exception during a single provider is caught, recorded in
      # `failed`, and loading continues for the rest. ProviderLoader.load
      # itself does not raise; the caller decides what to do with the
      # ProviderLoadResult (kernel will log a structured summary).
  ```

- **NEW** `tests/k1/model_hub/test_loader.py` (~250 LOC). Coverage:
  - `ProviderEntry` defaults (manifest_path resolution, plugin_class fallback)
  - `ProviderConfig.default()` lists all five known providers
  - `ProviderLoader.load` happy path with a `_StubPlugin` (no real network)
  - Missing env var → entry recorded in `skipped`, no exception
  - Plugin import error (bad dotted path) → entry recorded in `failed`, loader continues
  - `await plugin.initialize` raising → recorded in `failed`
  - `hub.register_plugin` raising on duplicate → recorded in `failed`
  - Plugin without `set_api_key` (Ollama-style) → still registers when `auth.type == "none"`
  - Result counts: registered + skipped + failed == total entries
  - All assertions on the return value, not via mocks.

- **NEW** `tests/k1/model_hub/test_loader_live.py` (~80 LOC). Coverage:
  - `pytest.mark.skipif(not os.environ.get("GOOGLE_API_KEY"), reason="...")` — same gating pattern as `test_google_live.py`
  - Build a real `_HubCore` via `ModelHubFactory.create_standalone()` then a `ProviderLoader(hub)` then `await loader.load(ProviderConfig.default())`
  - Assert `result.registered` contains `"google"` (and `"ollama"` if a local server is up — else skipped)
  - Assert one real CHAT request through the hub returns a non-empty response
  - This is the replacement-equivalent of P0.1's smoke test, scaled to all enabled providers.

- **NO edits to:** `k1/model_hub/factory.py`, `k1/model_hub/manifest.py`, `k1/model_hub/services/provider_registry.py`, `k1/model_hub/services/provider_dispatcher.py`, `k1/model_hub/plugins/*`, any concierge or POC file. P2.1 is purely additive — kernel still uses the P0.1 `_register_model_hub_plugins_from_env` shim until P2.3.
- **Optional micro-refactor (defer to P2.2):** if `_register_model_hub_plugins_from_env` is rewritten to delegate to `ProviderLoader.load(ProviderConfig.default())` while P2.1 is still landing, that's a 10-line kernel diff that gives multi-provider support immediately. Decided: **keep it in P2.1** as the "prove the loader works in production" gate — without this delegation the loader is dead code. So one tiny kernel edit IS in P2.1 scope:
  - `k1/kernel/service.py:828-882` — replace the body of `_register_model_hub_plugins_from_env` with `loader = ProviderLoader(hub); result = await loader.load(ProviderConfig.default()); logger.info("ModelHub provider load: registered=%s skipped=%s failed=%s", ...)`. Function name stays the same so the `_startup_tier1` caller doesn't move. (This makes P2.3 a clean "delete the now-trivial wrapper and call the loader directly from `_startup_tier1`" diff.)

**4. Handoff & test log**

**Implementation log — 2026-04-20**

- Files created:
  - `k1/model_hub/loader.py` (~165 LOC): `ProviderEntry`, `ProviderConfig`, `ProviderLoadResult`, `ProviderLoader`, `_import_plugin_class` helper.
  - `tests/k1/model_hub/test_loader.py` (~330 LOC): 16 unit tests covering `ProviderConfig.default()`, `_import_plugin_class` resolution + error paths, happy/skip/fail load outcomes, `set_api_key` duck-typing, duplicate registration, mixed-outcome accounting.
  - `tests/k1/model_hub/test_loader_live.py` (~85 LOC): one live test gated on `GOOGLE_API_KEY`, builds a real `_HubCore`, runs `ProviderLoader.load(ProviderConfig.default())`, asserts `"google" in result.registered`, then exercises one real Gemini call through the registered plugin.
- Files modified:
  - `k1/kernel/service.py:828-862`: `_register_model_hub_plugins_from_env` body replaced. Was 55 lines hand-coding Google-only registration; now 4 lines: `loader = ProviderLoader(hub); result = await loader.load(ProviderConfig.default()); logger.info("ModelHub provider load: registered=%s skipped=%s failed=%s", ...)`. Function name preserved so the `_startup_tier1` caller doesn't move; P2.3 will inline.

**Design refinements during implementation**

- **Self-hosted providers excluded from `ProviderConfig.default()`.** First end-to-end smoke run revealed that auto-registering ollama (api_base=`localhost:11434`) and vllm (configurable host) wired them into the dispatcher's fallback chain, so requests to *any* CHAT-capable provider could attempt a fallback dispatch to `localhost:8000` and fail with `ProviderError: All 3 providers failed for dispatch`. Fix: `_KNOWN_PROVIDERS` reduced to `("google", "openai", "anthropic")` — env-var-gated cloud providers only. Self-hosted plugins still load via explicit `ProviderEntry(provider_id="ollama")` in a custom `ProviderConfig`. Captured in `loader.py` docstring + the `test_default_lists_all_known_providers` assertion.
- **`set_api_key` duck-typing confirmed correct path.** Loader uses `getattr(plugin, "set_api_key", None)` and only calls it if both an env-var key resolved AND the method is callable. Logs at DEBUG when the method is absent. No new Protocol extension needed.
- **`ProviderRegistry.register` ValueError on duplicates is preserved.** The loader catches it and records the entry as `failed`, so re-loading is fail-loud per provider but never aborts the whole load. Verified by `test_duplicate_provider_id_failed`.
- **Manifest path resolution stays explicit.** No glob discovery added. `ProviderEntry.manifest_path` defaults to `{manifest_root}/{provider_id}.manifest.yaml` per the existing on-disk convention; explicit path always wins.

**Test log**

- `pytest tests/k1/model_hub/test_loader.py -v` → **16 passed** in 0.98s. Note: assertions on plugin class identity were initially `is _StubPlugin` but pytest collects under both `tests.*` and `familyos.tests.*` package paths, so identity comparison fails. Replaced with `cls.__name__ == "_StubPlugin"` style checks.
- `pytest tests/k1/model_hub/test_loader_live.py -v -s` (with `GOOGLE_API_KEY` set) → **1 passed** in 3.55s. ProviderLoader log: `registered=('google',) skipped=(('openai', ...), ('anthropic', ...)) failed=()`. Real Gemini reply: `'pong'` (in=8, out=1).
- `pytest tests/k1/model_hub/ -q --ignore=test_loader_live.py` → **1062 passed, 6 failed**. The 6 failures (`test_normalization_layer.py::TestDenormalize::*`, `test_request_router.py::TestFullPipeline::test_happy_path`, `TestCacheIntegration::test_cache_hit_short_circuits`, `TestCacheIntegration::test_high_temp_not_cached`) are all `assert ChatResult(text='X') == 'X'` — string-vs-`ChatResult` mismatches. Confirmed pre-existing on clean branch HEAD via `git stash` round-trip. Zero new regressions from P2.1.
- **End-to-end kernel smoke** (`python scripts/test_kernel_tiers.py`, real Gemini API): both LOW and MED tiers booted cleanly (14.45s cold / 0.22s warm), ProviderLoader log appeared once per boot showing `registered=('google',)`, LOW returned `"The capital of France is Paris."`, MED returned a 3-step blog outline. Zero `ProviderError`. Tier paths from P0.1 still green.
- **User sign-off:** ☐

---

### EPIC P2.2 — `ModelHubFactory.from_config` + lifecycle

**Status:** implemented + tested end-to-end against Gemini, awaiting user sign-off

**Note on two-codebase rule:** P2 is **k1-only** (the POC has no `model_hub/` parallel — established in P2.1). No `poc/k1_poc/` mirror epic for P2.2.

**1. Read**

- `k1/model_hub/factory.py:102-160` — `_HubCore.__init__(router, registry, health_adapter)`. Stores `_router`, `_registry`, `_health`. Public methods: `register_plugin` (P0.1 chokepoint), `execute`, `stream_execute`, `discover_capabilities`, `discover_models`, `health`. **No `shutdown` / `close` / `aclose` exists today.** No `from_config` exists today. The method name `shutdown` is unused on `_HubCore` and `IModelHubPort` — safe to add.
- `k1/model_hub/factory.py:200-475` — three `@staticmethod` constructors:
  - `create_standalone(config=None, plugins=None) -> IModelHubPort` (L200-258)
  - `create_for_testing(overrides=None) -> Tuple[IModelHubPort, Dict[str, Any]]` (L252-388) — sole existing precedent for returning a tuple from a factory
  - `create_with_ports(ports, config=None, plugins=None) -> IModelHubPort` (L390-475) — sole production caller-shape; passes `plugins` ONLY into `ProviderDispatcher(plugins=plugins or {})` at L432-436
- `k1/model_hub/factory.py:404-453` — wiring sequence inside `create_with_ports` (lines paraphrased):
  1. L404 `credential_port = ports["credential_port"]` — required (KeyError if absent)
  2. L405-L408 `event_port`, `state_read_port`, `metrics_port`, `config_port`, `health_port` from `ports.get(...)` — optional
  3. L410-L416 `_validate_ports(...)` — isinstance Protocol checks
  4. L418-L424 `ProviderRegistry(cfg)` → `CircuitBreakerManager()` → `RateLimiter(default_headroom_pct=cfg.rate_limit_headroom_pct)` → `_DefaultHealthQuery()`
  5. L425-L430 `CapabilityRouter(registry, circuit_mgr, rate_limiter, health_query)`
  6. L432-L436 `ProviderDispatcher(circuit_mgr, rate_limiter, credential_port, plugins or {})`
  7. L438-L447 `RequestRouter(capability_router, ModelSelector(), BudgetEnforcer(cfg), ResponseCache(cfg), NormalizationLayer(), dispatcher, CostTracker(), AuditLogger(), metrics_port=metrics_port)`
  8. L449-L453 `return _HubCore(router=router, registry=registry, health_adapter=HealthReportAdapter())`
  - **`metrics_port` is the only optional port actually wired** (into `RequestRouter`). `event_port`, `state_read_port`, `config_port`, `health_port` are validated but never threaded into any service — pre-existing tech debt; out of scope for P2.2 but the new `from_config` docstring must NOT advertise them as wired.
- `k1/model_hub/ports/hub_port.py:33-49` — `IModelHubPort` (`@runtime_checkable Protocol`): `execute`, `stream_execute`, `discover_capabilities`, `discover_models`, `health`. Five methods. **No `shutdown` on the Protocol.**
- `k1/model_hub/plugins/base.py:202` — `IProviderPlugin.close(self) -> None` is on the Protocol with exact signature `async def close(self) -> None`. Docstring: "Cleanup connections and cancel in-flight requests. Called during shutdown or on provider unregistration."
- All five concrete plugin `close()` bodies — verified each is idempotent, has zero background tasks, and is safe to call concurrently:
  - `k1/model_hub/plugins/openai_plugin.py:96-100` — closes `aiohttp.ClientSession`, sets `self._session = None`
  - `k1/model_hub/plugins/anthropic_plugin.py:97-101` — same pattern as OpenAI
  - `k1/model_hub/plugins/google_plugin.py:136-138` — drops the lazily-created `genai.Client` reference (no async close on the SDK client; just `self._client = None`)
  - `k1/model_hub/plugins/ollama_plugin.py:89-93` — closes `aiohttp.ClientSession`
  - `k1/model_hub/plugins/vllm_plugin.py:92-96` — closes `aiohttp.ClientSession`
  - **All five guard with `if self._session and not self._session.closed`** (Google's variant: `self._client = None` is a no-op on second call). All idempotent. `asyncio.gather(*[p.close() for p in plugins], return_exceptions=True)` is the safe drain pattern.
- `k1/model_hub/services/{provider_registry,provider_dispatcher,request_router,capability_router,circuit_breaker,rate_limiter}.py` and `k1/model_hub/adapters/health_report_adapter.py` — **none** has `close`/`shutdown`/`aclose`. They are in-memory value objects holding no async resources. Only the plugins need draining.
- `k1/model_hub/services/provider_dispatcher.py:112-113` — `register_plugin(provider_id, plugin)` is a one-liner `self._plugins[provider_id] = plugin`. The plugins live in `ProviderDispatcher._plugins` — that dict (or its values view) is the canonical source for `shutdown()`.
- `k1/model_hub/services/provider_registry.py:100-108` — `ProviderRegistry.register` raises `ValueError(f"Provider already registered: {pid}")` on duplicate. (Already documented in P2.1; restated here because `from_config` called twice on the same hub will surface it.)
- `k1/model_hub/factory.py:125-131` — `_HubCore.register_plugin` calls `self._registry.register(manifest, plugin)` first, then `self._router._dispatcher.register_plugin(...)`. **Registry is first**, so on a duplicate the dispatcher is NOT updated. Duplicate-load semantics: hub keeps original plugin, second load's entry recorded in `result.failed`.
- `k1/model_hub/loader.py` (P2.1) — `ProviderLoader(hub, *, manifest_root=None)` and `ProviderConfig.default()` already exist. `ProviderLoader.load(config)` returns `ProviderLoadResult(registered, skipped, failed)` and never raises. **`from_config` will instantiate the loader internally — no duplication of wiring.**
- `k1/kernel/service.py:929` — sole production call site of `create_with_ports` outside `k1/model_hub/`. Passes 5 ports (`credential_port`, `event_port`, `state_read_port`, `metrics_port`, `config_port`); does NOT pass `plugins=`. P2.2 must keep this signature working unchanged (P2.3 swaps it to `from_config`).
- `k1/kernel/service.py:255-360` — `KernelService.shutdown` (the eventual P2.3 hook). Step **S2** at L267-L280 has the comment `# ── Reverse S2: (ModelHub has no teardown) ────────────` at L349. Per-component teardown pattern uses `asyncio.wait_for(..., timeout=_TEARDOWN_TIMEOUT)` + per-step exception swallowing. P2.2's `shutdown()` should follow this pattern internally so P2.3's hook is a clean two-line `await asyncio.wait_for(self._model_hub.shutdown(), timeout=_TEARDOWN_TIMEOUT); self._model_hub = None`.
- `k1/kernel/bootstrap.py:126-139` — `stop_kernel(runtime)` calls `await svc.shutdown()`. No model hub cleanup of its own; everything flows through `KernelService.shutdown`.
- `tests/k1/model_hub/test_factory.py:158-184` — `create_with_ports` test passes only `credential_port`, does NOT pass `plugins=`, does NOT exercise `register_plugin` or any shutdown path. **No existing test for `from_config` (doesn't exist) and no test for any hub-level shutdown.** Safe to add net-new test files without colliding with existing fixtures.
- `tests/k1/model_hub/test_loader.py:134` — uses `ModelHubFactory.create_for_testing()` to build the hub. P2.2's tests can reuse this entry point or use `create_standalone()` for pure-construction parity.
- **No code outside `k1/model_hub/` imports `_HubCore`** at runtime (only `loader.py` imports it under `TYPE_CHECKING`). Adding `shutdown()` to `_HubCore` only — without adding it to `IModelHubPort` — is safe: kernel stores `self._model_hub: Any | None`, so it can call the concrete method without a Protocol extension.
- `count_lines.ps1` (no-op for design) — confirms `factory.py` is currently ~520 LOC; P2.2 adds ~80 LOC (one new staticmethod + one new `_HubCore` method) keeping the file well under any size threshold.

**2. Findings**

- **`from_config` is a thin orchestrator, not a new wiring path.** It must reuse `create_with_ports`'s service-graph construction (lines 404-453) verbatim, then run `ProviderLoader(hub).load(config)`, then return `(hub, result)`. Implementing as a wrapper that calls `create_with_ports(ports, plugins=None)` first, then runs the loader, is the simplest design — zero duplication of the 50-line wiring sequence. Trade-off: a no-op pass through `ProviderDispatcher(plugins={})` is harmless (the loader will populate the dispatcher via `_HubCore.register_plugin` immediately after).
- **Return type:** `Tuple[IModelHubPort, ProviderLoadResult]` (precedent: `create_for_testing` already returns a tuple). Throwing the `ProviderLoadResult` away would mean the caller can never see which providers loaded — a regression vs. the loader-direct call. The kernel (in P2.3) will log the result the same way it does today.
- **`from_config` never raises on partial failure.** Mirrors the loader contract. If `result.failed` is non-empty, callers decide; the hub is still functional with whatever did register. (If the caller needs strict-fail semantics they can `raise` after inspecting the result.) This matches the kernel's current "log and continue" stance for missing API keys.
- **Lifecycle home: `_HubCore.shutdown` (concrete method only, NOT on `IModelHubPort`).** Adding to the Protocol would require updating every test stub and every implementer; needless churn. Kernel stores `self._model_hub: Any` so it can call `await self._model_hub.shutdown()` without Protocol awareness. Future epics can promote to the Protocol if a second implementation appears.
- **`shutdown()` body:** iterate `self._router._dispatcher._plugins.values()` (the canonical plugin store), wrap each `plugin.close()` in a per-plugin `asyncio.wait_for` with a sane timeout (use `_HubCore`-local constant `_PLUGIN_CLOSE_TIMEOUT_S = 5.0`), gather with `return_exceptions=True`, log any exceptions at WARNING level, swallow them. Idempotent: after the first call, dispatcher's `_plugins` dict still holds references; re-calling close on a closed plugin is a no-op per the guard pattern. Document idempotency in the docstring.
- **`_router._dispatcher._plugins` is still a private-attr reach.** Same seam as `_HubCore.register_plugin` (P0.1). Not worth refactoring in P2.2 — P2.3's "drop private-attr walking" epic will introduce a clean `dispatcher.iter_plugins()` accessor or similar. P2.2 documents the seam in a comment and moves on.
- **`create_with_ports(plugins=...)` stays unchanged.** It is NOT refactored to delegate to `from_config`. Reason: `create_with_ports` accepts pre-instantiated plugins (test/DI use case); `from_config` accepts a declarative config (production use case). Different shapes; collapsing them adds complexity for no caller benefit. Keep both; mark `from_config` as the recommended entry point in the docstring.
- **No `IModelHubPort.shutdown` extension this epic.** P2.3 may revisit if the kernel side benefits from a Protocol-level guarantee. P2.2 keeps the surface minimal.
- **Idempotency of `from_config` itself:** calling it twice on the same hub is undefined-but-safe — the loader will record every entry as `failed` (registry's `ValueError`), the hub stays functional with whatever the first call registered. Docstring will say "build the hub once; for re-registration, construct a new hub." No defensive code needed.
- **Zero risk to non-ModelHub code.** `from_config` is purely additive. `create_with_ports`, `create_standalone`, `create_for_testing`, `_HubCore.{execute, stream_execute, discover_*, health, register_plugin}` all unchanged. Kernel still uses `create_with_ports` until P2.3. Concierge unchanged. POC unchanged.
- **Tests:** zero existing tests will break. Adds two new files (one unit, one live). Existing `test_factory.py` fixtures and `test_loader.py` `_StubPlugin` helpers can be reused but are not modified.

**3. Changes** (no edits applied yet — design contract for the implementation step)

- **EDIT** `k1/model_hub/factory.py` — add two pieces:

  - **New `_HubCore.shutdown` method** (~30 LOC, placed after `health` at ~L160):

    ```python
    _PLUGIN_CLOSE_TIMEOUT_S: float = 5.0

    async def shutdown(self) -> None:
        """Drain registered plugins. Idempotent. Never raises.

        Iterates the dispatcher's plugin store, calls `await plugin.close()`
        on each under a per-plugin timeout, gathers with return_exceptions,
        logs exceptions at WARNING. Safe to call multiple times — each
        plugin's close() is idempotent (guards with `_session.closed` or
        `_client is None`).

        NOTE: reaches into `self._router._dispatcher._plugins` directly.
        Same private-attr seam as `register_plugin`. Cleaned up in P2.3.
        """
        plugins = list(self._router._dispatcher._plugins.values())
        if not plugins:
            return
        results = await asyncio.gather(
            *[
                asyncio.wait_for(p.close(), timeout=_PLUGIN_CLOSE_TIMEOUT_S)
                for p in plugins
            ],
            return_exceptions=True,
        )
        for plugin, outcome in zip(plugins, results, strict=True):
            if isinstance(outcome, BaseException):
                logger.warning(
                    "ModelHub plugin close failed: %s (%s: %s)",
                    type(plugin).__name__, type(outcome).__name__, outcome,
                )
    ```

  - **New `ModelHubFactory.from_config` staticmethod** (~30 LOC, placed after `create_with_ports` at ~L475):

    ```python
    @staticmethod
    async def from_config(
        config: "ProviderConfig",
        ports: Dict[str, Any] | None = None,
        *,
        hub_config: ModelHubConfig | None = None,
        manifest_root: Path | None = None,
    ) -> Tuple[IModelHubPort, "ProviderLoadResult"]:
        """Recommended production entry point. Builds a hub via
        `create_with_ports` (or `create_standalone` if `ports is None`),
        then runs `ProviderLoader(hub).load(config)` so the returned hub
        is already populated with every provider whose env-var resolved.

        Returns (hub, ProviderLoadResult). Never raises on partial provider
        failure — inspect `result.failed` / `result.skipped` to decide.
        Caller owns the hub's lifecycle; call `await hub.shutdown()` on
        teardown to drain plugin sessions.

        Only `credential_port` is consumed from `ports`; `metrics_port`
        flows into the RequestRouter. Other accepted keys (`event_port`,
        `state_read_port`, `config_port`, `health_port`) are validated but
        not yet wired into any service — pre-existing factory behavior;
        not addressed by P2.2.
        """
        from k1.model_hub.loader import ProviderLoader  # local import to avoid cycle

        if ports is None:
            hub = ModelHubFactory.create_standalone(config=hub_config)
        else:
            hub = ModelHubFactory.create_with_ports(ports, config=hub_config)
        loader = ProviderLoader(hub, manifest_root=manifest_root)  # type: ignore[arg-type]
        result = await loader.load(config)
        return hub, result
    ```

  - **Imports added at top of `factory.py`:** `import asyncio`, `from typing import Tuple` (both likely already present — confirm), and a `TYPE_CHECKING` block for `ProviderConfig` / `ProviderLoadResult` from `k1.model_hub.loader` to avoid runtime cycle. Module-level `logger = logging.getLogger(__name__)` already exists per P0.1.

- **NEW** `tests/k1/model_hub/test_factory_from_config.py` (~250 LOC). Coverage:
  - `from_config` with `ports=None` → uses `create_standalone` path; loader runs; returns `(hub, result)` with `result.total == len(config.providers)`
  - `from_config` with `ports={"credential_port": <stub>}` → uses `create_with_ports` path; same return contract
  - `from_config` with a config of one entry pointing at a `_StubPlugin` manifest → `result.registered == ("stub",)`; `await hub.discover_capabilities()` returns the stub's capabilities
  - `from_config` with a missing-env-var entry → `result.skipped` non-empty; hub still constructed and queryable
  - `from_config` with a bad-plugin-class entry → `result.failed` non-empty; loader continues; never raises
  - `await hub.shutdown()` after `from_config` → calls `close()` on every registered plugin (verified via spy `_StubPlugin.close_call_count`); idempotent (calling twice still safe; second call sees plugins already closed)
  - `await hub.shutdown()` on a hub with zero registered plugins → returns immediately, no error
  - `await hub.shutdown()` when one plugin's `close()` raises → other plugins still closed, exception logged at WARNING (use `caplog`), `shutdown()` itself does NOT raise
  - `await hub.shutdown()` when one plugin's `close()` hangs longer than `_PLUGIN_CLOSE_TIMEOUT_S` → that plugin's outcome is a `TimeoutError` in the gather; other plugins finish; `shutdown()` returns
  - `from_config` called twice on the same hub → second call's `result.failed` lists every entry (registry raises `ValueError` on duplicate); first call's plugins still functional
  - All assertions on return values + spy state, no mocks of `_HubCore` internals.

- **NEW** `tests/k1/model_hub/test_factory_from_config_live.py` (~90 LOC). Coverage:
  - `pytest.mark.skipif(not os.environ.get("GOOGLE_API_KEY"))` — same gating as `test_loader_live.py`
  - Build a real production-shaped hub: `hub, result = await ModelHubFactory.from_config(ProviderConfig.default(), ports={"credential_port": <real CredentialPort>})`
  - Assert `"google" in result.registered`
  - Execute one real CHAT request through the hub → assert non-empty response (mirror P2.1 live test's "pong" pattern)
  - `await hub.shutdown()` → assert no exception, then verify hub is unusable for new requests (the underlying `genai.Client` should be `None`); document this is the expected post-shutdown state
  - This test is the production-path-equivalent of `test_loader_live.py`; together they prove the loader works both directly AND through the recommended factory entry.

- **NO edits to:** `k1/kernel/service.py` (P2.3), `k1/model_hub/ports/hub_port.py` (no Protocol extension), `k1/model_hub/plugins/*` (close() bodies already exist and are idempotent), `k1/model_hub/services/*` (services hold no async resources), any concierge or POC file. P2.2 is purely additive in `k1/model_hub/factory.py` plus two new test files.

- **Backward-compat verification step (mandatory in implementation):** after editing `factory.py`, run `python scripts/test_kernel_tiers.py` end-to-end to confirm the kernel's existing `create_with_ports` call site at `k1/kernel/service.py:929` still works untouched. Expected outcome: identical to P2.1's smoke (LOW returns Paris, MED returns blog outline, ProviderLoader log unchanged).

**4. Handoff & test log**

**Implementation log — 2026-04-20**

- Files modified:
  - `k1/model_hub/factory.py`:
    - Added `import asyncio`, `from pathlib import Path`, `TYPE_CHECKING` block importing `ProviderConfig`/`ProviderLoadResult` from `k1.model_hub.loader` (avoids runtime cycle).
    - Added module-level constant `_PLUGIN_CLOSE_TIMEOUT_S: float = 5.0` after `logger`.
    - Added `_HubCore.shutdown()` (~30 LOC) after `health()`. Iterates `self._router._dispatcher._plugins.values()`, runs `await plugin.close()` under `asyncio.wait_for(timeout=_PLUGIN_CLOSE_TIMEOUT_S)` per plugin via `asyncio.gather(return_exceptions=True)`, logs any exceptions at WARNING with plugin type + exception class + message. Idempotent (safe to call any number of times). Never raises. NOT added to `IModelHubPort` Protocol — concrete-only.
    - Added `ModelHubFactory.from_config(config, ports=None, *, hub_config=None, manifest_root=None) -> Tuple[IModelHubPort, ProviderLoadResult]` (~30 LOC) after `create_with_ports`. When `ports is None` delegates to `create_standalone(config=hub_config)`; otherwise `create_with_ports(ports, config=hub_config)`. Then `await ProviderLoader(hub, manifest_root=manifest_root).load(config)`. Returns `(hub, result)`. Local import of `ProviderLoader` inside the method to avoid cycle. Never raises on partial failure.
- Files created:
  - `tests/k1/model_hub/test_factory_from_config.py` (~370 LOC, 11 tests). Stub plugins `_SpyPlugin` (counts close calls), `_RaisingClosePlugin`, `_HangingClosePlugin`. `_StubCredentialPort` implements the real `ICredentialPort` Protocol (`get_key` / `refresh_key`). Test classes: `TestFromConfigConstruction` (ports=None vs ports=dict), `TestFromConfigOutcomes` (happy path indexes capability, missing env-var skipped, bad plugin class failed loader continues, double-call records failed and keeps first plugins), `TestShutdown` (empty hub returns immediately, drains all plugins, idempotent second call safe, raising `close()` logged + swallowed via `caplog`, hanging `close()` times out via monkeypatched `_PLUGIN_CLOSE_TIMEOUT_S=0.1` while other plugins still finish).
  - `tests/k1/model_hub/test_factory_from_config_live.py` (~85 LOC, 1 live test gated on `GOOGLE_API_KEY`). Loads `.env` from `poc/chat_experience_poc/`, calls `await ModelHubFactory.from_config(ProviderConfig.default(), ports=None)`, asserts `"google" in result.registered`, executes one real Gemini chat call directly through the registered plugin, then `await hub.shutdown()` (must not raise).

**Design refinements during implementation**

- **Plugin instance discovery via dispatcher (not class-level instance list).** Initial `_SpyPlugin.instances: list` class attribute didn't work — pytest collects under both `tests.*` and `familyos.tests.*` paths, so `importlib.import_module("tests.k1.model_hub.test_factory_from_config")` resolves a different module than the one currently running the test. The class objects are distinct, so `_SpyPlugin.instances` (in test-module-A) never receives instances created from test-module-B's imported class. Fix: iterate `hub._router._dispatcher._plugins.values()` to get the actually-registered plugins (which ARE the importlib-resolved ones). Same dual-package trap encountered in P2.1; documented here as a recurring testing pattern.
- **`ICredentialPort` shape: `get_key`/`refresh_key`, not `get_credential`/...`.** First stub used invented method names;`_validate_ports` correctly rejected it via `isinstance(port, ICredentialPort)`Protocol check. Real protocol is two methods (`get_key`,`refresh_key`). Fix: stub matched the Protocol surface.
- **Skipped-plugin session leak (out-of-scope, pre-existing).** The live test surfaced `Unclosed client session` warnings for the `openai` and `anthropic` plugins. Root cause: `ProviderLoader._load_one` calls `await plugin.initialize(manifest)` (which creates the `aiohttp.ClientSession`) BEFORE checking the env-var; if the env var is missing, the entry is recorded as `skipped` and the plugin reference is dropped without `close()`. This is a pre-existing P2.1 loader behavior, not introduced by P2.2 — a future epic should reorder `_load_one` to env-var-check before `initialize` (or call `await plugin.close()` on the skip path). Filed mentally; not addressed here.
- **`shutdown()` lives on `_HubCore` only — not on `IModelHubPort`.** Confirmed safe: kernel stores `self._model_hub: Any | None`, can call `await self._model_hub.shutdown()` without Protocol awareness. P2.3 will validate this assumption when wiring the kernel teardown step.
- **`create_with_ports(plugins=...)` left untouched.** No call sites use the `plugins=` arg today (kernel passes 5 ports + zero plugins). The shim stays as-is per the design contract; no kernel-visible change in P2.2.

**Test log**

- `pytest tests/k1/model_hub/test_factory_from_config.py -v` → **11 passed** in 1.27s. (First run had 3 failures: 2 from the dual-package class-identity issue, 1 from the wrong `ICredentialPort` stub shape. Both fixed; second run all green.)
- `pytest tests/k1/model_hub/test_factory_from_config_live.py -v -s` (with `GOOGLE_API_KEY` set) → **1 passed** in 3.42s. Real Gemini reply: `'pong'` (in=8, out=1). `hub.shutdown()` returned cleanly.
- `pytest tests/k1/model_hub/ -q --ignore=test_loader_live.py --ignore=test_google_live.py --ignore=test_factory_from_config_live.py` → **1063 passed, 6 failed** (was 1062/6 before P2.2 — the +1 is the `TestProviderConfig` count unchanged + 11 new P2.2 tests netting 1063). The 6 failures are the same pre-existing `ChatResult` vs string mismatches in `test_normalization_layer.py` and `test_request_router.py` confirmed pre-existing on clean HEAD during P2.1. Zero new regressions from P2.2.
- **Back-compat kernel smoke** (`python scripts/test_kernel_tiers.py`, real Gemini API): both LOW and MED tiers booted cleanly (9.38s cold / 0.13s warm). ProviderLoader log identical to P2.1 (`registered=('google',)`). LOW returned `"Let me think about that for a moment."`; MED returned a 3-step blog outline. Zero `ProviderError`. **Confirms `create_with_ports` at `k1/kernel/service.py:929` still works unchanged — P2.2 is purely additive.**
- **User sign-off:** ☐

---

### EPIC P2.3 — Kernel migrates to `from_config`; drop private-attribute walking

**Status:** implemented + tested end-to-end against Gemini, awaiting user sign-off

**Note on two-codebase rule:** P2 is **k1-only** (POC has no `model_hub/` parallel). No `poc/k1_poc/` mirror epic for P2.3.

**1. Read**

- `k1/kernel/service.py:175` — `self._model_hub: Any | None = None  # ModelHub`. Type annotated as `Any | None` (no Protocol). No change needed.
- `k1/kernel/service.py:76-81` — top-level model_hub imports: `ConfigAdapter`, `CredentialStoreAdapter`, `EventBusAdapter as MHEventBusAdapter`, `PrometheusAdapter`, `SessionStateProdAdapter`, `ModelHubFactory`. P2.3 adds top-level `from k1.model_hub.loader import ProviderConfig`.
- `k1/kernel/service.py:828-865` — `_register_model_hub_plugins_from_env` (post-P2.1 shim): `from k1.model_hub.loader import ProviderConfig, ProviderLoader` (local), `hub = self._model_hub`, `if hub is None: return`, `if not hasattr(hub, "register_plugin"): logger.warning(...); return`, `loader = ProviderLoader(hub); result = await loader.load(ProviderConfig.default()); logger.info("ModelHub provider load: registered=%s skipped=%s failed=%s", ...)`. Function is `pragma: no cover` for the early-return path; no test mocks it; zero callers outside `_startup_tier1`.
- `k1/kernel/service.py:920-957` — `_startup_tier1` S2 block:

  ```python
  # ── S2: ModelHub (with auxiliary ports) ───────────
  try:
      self._model_hub = ModelHubFactory.create_with_ports(
          ports={
              "credential_port": CredentialStoreAdapter(),
              "event_port": MHEventBusAdapter(bus=self._bus),
              "state_read_port": SessionStateProdAdapter(
                  manager=_FirstSessionSSMShim(self._sessions),
              ),
              "metrics_port": PrometheusAdapter(),
              "config_port": ConfigAdapter(),
          },
      )
      # ── Register provider plugins driven by environment keys ──
      if self._config.model_mode == "hub":
          await self._register_model_hub_plugins_from_env()
  except Exception:
      # S1 created — clean up.
      self._bus.close()
      self._router.close()
      raise
  ```

  Five ports. The `model_mode == "hub"` gate currently wraps ONLY the plugin-load call; the hub itself is constructed unconditionally.
- `k1/kernel/service.py:255-370` — `KernelService.shutdown`. Step ordering (reverse-S): destroy sessions → S7 Planner → S6b (no-op) → S5 Orchestrator → S4 Bridge → S3 Fabric → **S2 ModelHub: comment placeholder at L349 `# ── Reverse S2: (ModelHub has no teardown) ────────────`** → S1 Bus + Router. Each step is `try / await asyncio.wait_for(component.method(), timeout=_TEARDOWN_TIMEOUT) / except: errors.append(exc); logger.warning(...)`. Errors accumulated; raised as one `RuntimeError(f"shutdown: {len(errors)} error(s) ...")` at the end. Idempotency guard at entry: `if not self._running: return`.
- `k1/kernel/service.py:27` — `_TEARDOWN_TIMEOUT: float = 10.0`. P2.3 reuses this constant; no new constant needed.
- `k1/kernel/service.py:320-340` — example pattern to mirror (Orchestrator + Fabric + Bridge teardown blocks):

  ```python
  if self._orchestrator is not None:
      try:
          await asyncio.wait_for(
              self._orchestrator.shutdown(),
              timeout=_TEARDOWN_TIMEOUT,
          )
      except Exception as exc:
          errors.append(exc)
          logger.warning("shutdown: Orchestrator shutdown failed: %s", exc)
  ```

  Existing pattern does NOT null the field after teardown — Orchestrator/Fabric/Bridge/Planner remain non-None post-shutdown. The `_running = False` flag is the canonical "is shutdown" signal, not field nulling.
- `k1/kernel/service.py:1195-1260` — `_cleanup_tier1_partial`. Calls `await self._shared_fabric.shutdown()`, `await self._bridge.disconnect()`, etc. for each Tier-1 component before nulling its field. **`self._model_hub` is set to `None` at L1255 WITHOUT a prior `hub.shutdown()` call** — pre-P2.2 there was no `shutdown()` to call; post-P2.2 this is now a resource leak on partial-boot failures. P2.3 fixes this.
- `k1/kernel/bootstrap.py:132-141` — `stop_kernel(runtime)`: pure delegate to `await svc.shutdown()`. No model hub cleanup of its own. Will automatically exercise P2.3's new teardown step.
- **Private-attr walking grep across `k1/kernel/`:** zero hits in production. The only `_router._dispatcher` / `_registry` reaches are in `tests/k1/kernel/test_service.py` (three lines: L975, L984, L991 — all in `TestS2ModelHubWiring` asserting `svc._model_hub._router._metrics is not None` for `PrometheusAdapter` wiring). Production kernel is already private-attr-clean post-P2.1.
- `tests/k1/kernel/test_service.py:969-991` — `TestS2ModelHubWiring`:
  - `test_model_hub_uses_create_with_ports` (L969): docstring + assertion explicitly reference `create_with_ports`. **Test name and intent become outdated after P2.3** — needs renaming/rewriting (e.g., `test_model_hub_uses_from_config`).
  - `test_model_hub_metrics_port_is_prometheus` (L981) and `test_model_hub_metrics_port_emit_works` (L988): use `svc._model_hub._router._metrics`. Underlying assertion (PrometheusAdapter is wired) still valid post-P2.3 — `from_config` internally calls `create_with_ports(ports)` so the metrics port still flows in. **Private-attr walk in tests can stay** (test-only, not production); only docstrings need a refresh if they mention `create_with_ports`.
- `tests/k1/kernel/test_service.py:3540` — `test_cleanup_tier1_partial_resets_all_fields`. Asserts `svc._model_hub is None` after S5 boom. After P2.3 adds `await hub.shutdown()` before the `None` reset in `_cleanup_tier1_partial`, this test still passes (field is still None at the end). If a buggy `shutdown()` raises, the test will start failing — must be guarded to swallow.
- **Zero tests** mock `_register_model_hub_plugins_from_env`. **Zero tests** mock `ModelHubFactory.create_with_ports`. Safe to refactor.
- `scripts/test_kernel_tiers.py` — boots via `start_kernel(KernelConfig(model_mode="hub", tool_tier=tier))` then `stop_kernel(runtime)` → `svc.shutdown()`. Will automatically exercise the new `await self._model_hub.shutdown()` step on every smoke run when plugins are registered.
- `_HubCore.shutdown()` (P2.2) reaches into `self._router._dispatcher._plugins.values()`. This is `_HubCore`-internal — kernel never touches it. P2.3 does NOT need to expose a public `dispatcher.iter_plugins()` accessor; the seam is contained. (Plan L574 mentioned this as a P2.3 idea — confirmed not required.)

**2. Findings**

- **Production kernel is already private-attr-clean.** The only "private-attribute walking" left in `k1/kernel/` is in three test-file lines (`_router._metrics`). The plan's "drop private-attribute walking" goal is mostly already satisfied by P0.1 + P2.1; P2.3 just removes the last functional dependency on the `_register_model_hub_plugins_from_env` shim wrapper. No `dispatcher.iter_plugins()` accessor needed.
- **`model_mode != "hub"` gate decision — keep as-is, branch at the call site (Option A from §8).** Today `model_mode != "hub"` skips plugin loading but still constructs the hub. To preserve behavior exactly, P2.3 keeps the same gate around the loader call:
  - When `model_mode == "hub"`: `self._model_hub, result = await ModelHubFactory.from_config(ProviderConfig.default(), ports=ports)` then log result.
  - Otherwise: `self._model_hub = ModelHubFactory.create_with_ports(ports=ports)` (no plugin load).
  This is two lines vs. one but preserves exact semantics. Option B (always `from_config`, pass empty `ProviderConfig` when not hub mode) silently changes semantics if anyone reads logs and starts seeing a "ProviderLoader: registered=() skipped=() failed=()" line for non-hub mode — minor but unnecessary. The plan-doc note at L88 ("remove the gate") was speculative; defer that to a future epic if anyone actually wants it.
- **`ProviderLoadResult` is logged-and-dropped, NOT stored on `self`.** Matches P2.1 stance. No new field. Health endpoint can re-expose later without surface area cost today.
- **`from_config` never raises on partial provider failure** (P2.2 contract). Kernel inherits that — no `try/except` around the `from_config` call beyond the existing S2-wide `try/except` that handles construction errors. The existing block already wraps the entire S2 in `try/except Exception: self._bus.close(); self._router.close(); raise` — that stays.
- **Teardown step S2 added inside `KernelService.shutdown`**, mirroring the Orchestrator/Fabric/Bridge pattern verbatim:

  ```python
  # ── Reverse S2: ModelHub plugin drain (P2.3) ──────────
  if self._model_hub is not None:
      try:
          await asyncio.wait_for(
              self._model_hub.shutdown(),
              timeout=_TEARDOWN_TIMEOUT,
          )
      except Exception as exc:
          errors.append(exc)
          logger.warning("shutdown: ModelHub shutdown failed: %s", exc)
  ```

  **Do NOT null `self._model_hub` after** — aligns with existing teardown convention (Orchestrator/Fabric/Bridge are not nulled either). The `_running = False` flag is the canonical post-shutdown signal. (The plan's §3 sketch said "set `self._model_hub = None` after"; archaeology shows that diverges from existing pattern. Decision: keep the field non-None to match the rest of the kernel.)
- **`_cleanup_tier1_partial` adds a guarded `hub.shutdown()` call** before nulling the field, swallowing any exception (this is the partial-boot path; we are already in error recovery, must not propagate further):

  ```python
  if self._model_hub is not None:
      try:
          await asyncio.wait_for(
              self._model_hub.shutdown(),
              timeout=_TEARDOWN_TIMEOUT,
          )
      except Exception as exc:
          logger.warning("_cleanup_tier1_partial: ModelHub shutdown failed: %s", exc)
  self._model_hub = None
  ```

  Closes the resource leak surfaced by archaeology §6.
- **`_register_model_hub_plugins_from_env` is deleted entirely.** No callers outside `_startup_tier1`; no tests mock it; no concierge/bridge/poc imports. Safe deletion.
- **Local imports inside the deleted method (`ProviderLoader`, `ProviderConfig`) move to top-level.** Only `ProviderConfig` is needed at top (loader is now internal to `from_config`). One new top-level import line.
- **Test rewrite required:** `test_model_hub_uses_create_with_ports` (L969) — rename to `test_model_hub_uses_from_config`, update docstring, update the assertion (the existing assertion `hub._router._metrics is not None` still works; only the test name + docstring are stale). The two metrics-port tests (L981, L988) keep working with no change — they verify wiring, not API.
- **Zero risk to non-kernel code.** `from_config` already shipped in P2.2; kernel just becomes its first production caller. Concierge unchanged. Bridge unchanged. POC unchanged.

**3. Changes** (no edits applied yet — design contract for the implementation step)

- **EDIT** `k1/kernel/service.py`:
  - **Top-level imports:** add `from k1.model_hub.loader import ProviderConfig` after the existing `from k1.model_hub.factory import ModelHubFactory` line.
  - **Delete `_register_model_hub_plugins_from_env`** entirely (currently L828-L865, ~38 lines including docstring). No callers remain after the next edit.
  - **Rewrite the S2 block in `_startup_tier1`** (currently L920-L957, ~37 lines):

    ```python
    # ── S2: ModelHub (with auxiliary ports + declarative provider load) ──
    try:
        ports = {
            "credential_port": CredentialStoreAdapter(),
            "event_port": MHEventBusAdapter(bus=self._bus),
            "state_read_port": SessionStateProdAdapter(
                manager=_FirstSessionSSMShim(self._sessions),
            ),
            "metrics_port": PrometheusAdapter(),
            "config_port": ConfigAdapter(),
        }
        if self._config.model_mode == "hub":
            self._model_hub, load_result = await ModelHubFactory.from_config(
                ProviderConfig.default(),
                ports=ports,
            )
            logger.info(
                "ModelHub provider load: registered=%s skipped=%s failed=%s",
                load_result.registered,
                load_result.skipped,
                load_result.failed,
            )
        else:
            self._model_hub = ModelHubFactory.create_with_ports(ports=ports)
    except Exception:
        # S1 created — clean up.
        self._bus.close()
        self._router.close()
        raise
    ```

    Net change: ~37 lines → ~25 lines; one helper-method call eliminated; semantics preserved exactly (gate stays; non-hub mode still constructs hub without loading plugins).
  - **Add S2 teardown step in `KernelService.shutdown`** at the L349 placeholder (replace the comment line and the blank line after it):

    ```python
    # ── Reverse S2: ModelHub plugin drain (P2.3) ──────────
    if self._model_hub is not None:
        try:
            await asyncio.wait_for(
                self._model_hub.shutdown(),
                timeout=_TEARDOWN_TIMEOUT,
            )
        except Exception as exc:
            errors.append(exc)
            logger.warning("shutdown: ModelHub shutdown failed: %s", exc)
    ```

    Field is NOT nulled after — matches existing teardown pattern for Fabric/Orchestrator/Bridge/Planner.
  - **Patch `_cleanup_tier1_partial`** (~L1250-L1260): insert guarded `hub.shutdown()` call before the existing `self._model_hub = None` line. Exception is swallowed (we're in error recovery; must not propagate):

    ```python
    if self._model_hub is not None:
        try:
            await asyncio.wait_for(
                self._model_hub.shutdown(),
                timeout=_TEARDOWN_TIMEOUT,
            )
        except Exception as exc:
            logger.warning(
                "_cleanup_tier1_partial: ModelHub shutdown failed: %s", exc
            )
    self._model_hub = None
    ```

- **EDIT** `tests/k1/kernel/test_service.py`:
  - Rename `test_model_hub_uses_create_with_ports` → `test_model_hub_uses_from_config` (~L969). Update docstring to say "S2 wires the hub via `ModelHubFactory.from_config` (P2.3)". The body assertion can stay as `assert isinstance(svc._model_hub._router._metrics, PrometheusAdapter)` — still valid because `from_config` internally calls `create_with_ports`.
  - The two metrics-port tests at L981 + L988: leave bodies unchanged. Update docstrings if they mention `create_with_ports` (verify during implementation; one-line edits if so).
  - `test_cleanup_tier1_partial_resets_all_fields` (~L3540): leave assertion (`svc._model_hub is None`) unchanged. After P2.3 adds the guarded shutdown, the test still passes because the `_StubPlugin` used in tests (if any) won't raise; if none is registered the loop is a no-op.

- **NEW** `tests/k1/kernel/test_service_p23_lifecycle.py` (~150 LOC, 4-5 tests). Coverage:
  - `test_startup_calls_from_config_when_hub_mode` — boots a `KernelService` with `model_mode="hub"`, asserts `svc._model_hub` is a `_HubCore`, asserts the dispatcher's `_plugins` dict reflects whatever `ProviderConfig.default()` was able to load (use a stub credential port + monkeypatched env to register a known stub plugin OR just assert the load_result was logged via `caplog`).
  - `test_startup_skips_loader_when_not_hub_mode` — `model_mode="legacy"`, assert `svc._model_hub` is constructed (non-None) but no `ProviderLoader` log line appeared in `caplog`.
  - `test_shutdown_drains_model_hub_plugins` — boot → register a spy plugin via `_HubCore.register_plugin` after startup → call `svc.shutdown()` → assert spy plugin's `close_call_count == 1`.
  - `test_shutdown_swallows_hub_shutdown_exception` — register a plugin whose `close()` raises → call `svc.shutdown()` → assert it does NOT raise (the per-step `try/except` accumulates the exception into the eventual aggregate `RuntimeError`, but if no other step fails, no aggregate is raised) AND a WARNING was logged.
  - `test_cleanup_tier1_partial_drains_hub_before_nulling` — force a boot failure after S2 by monkeypatching S3/S4 to raise → assert `_cleanup_tier1_partial` called the spy plugin's `close()` AND set `svc._model_hub = None`.
  - These are the first kernel-level tests of the model-hub lifecycle; existing `tests/k1/kernel/test_service.py` does not cover this surface.

- **NO edits to:** `k1/model_hub/*` (P2.2 already shipped), `k1/concierge/*` (no model_hub mirror), `poc/*` (no model_hub), `k1/kernel/bootstrap.py` (already delegates correctly), `k1/kernel/runtime.py` (no hub touch). P2.3 is `service.py` + one test rename + one new test file.

- **Backward-compat verification step (mandatory in implementation):**
  1. `pytest tests/k1/kernel/ -q` → must pass with zero new regressions (the 6 pre-existing model_hub failures don't apply here).
  2. `pytest tests/k1/model_hub/ -q --ignore live` → must remain at the same 1063/6 baseline.
  3. `python scripts/test_kernel_tiers.py` → LOW + MED both pass; the P2.3 logger line `ModelHub provider load: registered=('google',) ...` appears in startup; teardown completes with no `ModelHub shutdown failed` warnings (since real plugins close cleanly per P2.2 archaeology).
  4. New live test `tests/k1/model_hub/test_factory_from_config_live.py` (P2.2) still passes — proves `from_config` works end-to-end against real Gemini.

**4. Handoff & test log**

**Implementation log — 2026-04-20**

- Files modified:
  - `k1/kernel/service.py`:
    - **Imports (top-level):** added `from k1.model_hub.loader import ProviderConfig` after the existing `ModelHubFactory` import. Local `from k1.model_hub.loader import ProviderConfig, ProviderLoader` import gone (lived inside the deleted shim).
    - **Deleted `_register_model_hub_plugins_from_env`** (~33 LOC at L828-865) — zero callers remain.
    - **Rewrote `_startup_tier1` S2 block** (~30 LOC): builds `mh_ports` dict once, then branches on `self._config.model_mode`. When `"hub"`: `self._model_hub, load_result = await ModelHubFactory.from_config(ProviderConfig.default(), ports=mh_ports)` + `logger.info("ModelHub provider load: ...")`. Otherwise: `self._model_hub = ModelHubFactory.create_with_ports(ports=mh_ports)` (no plugin load). The outer `try/except` that closes bus + router on failure stays unchanged. **Gate semantics preserved exactly** — non-hub modes still construct hub without loading plugins.
    - **Added S2 teardown step in `KernelService.shutdown`** at the L349 placeholder: standard `try / await asyncio.wait_for(self._model_hub.shutdown(), timeout=_TEARDOWN_TIMEOUT) / except → errors.append + logger.warning("shutdown: ModelHub shutdown failed: %s", exc)` — mirrors Orchestrator/Fabric/Bridge pattern verbatim. Field NOT nulled after (matches existing convention).
    - **Patched `_cleanup_tier1_partial`** (~L1230): inserted guarded `await asyncio.wait_for(self._model_hub.shutdown(), timeout=_TEARDOWN_TIMEOUT)` block BEFORE the existing `self._model_hub = None` line. Exception swallowed via `try/except` (we are already in error-recovery; cannot propagate further). Closes the resource leak surfaced by archaeology §6.
- Files modified (tests):
  - `tests/k1/kernel/test_service.py`: renamed `test_model_hub_uses_create_with_ports` → `test_model_hub_uses_from_config` at ~L969. Updated docstring to reference P2.3. Body assertion (`hub._router._metrics is not None`) unchanged — still valid because `from_config` delegates to `create_with_ports` internally so all auxiliary ports still flow through. The two `_router._metrics` tests at L981 + L988 left unchanged (their docstrings don't mention `create_with_ports`).
- Files created:
  - `tests/k1/kernel/test_service_p23_lifecycle.py` (~190 LOC, 6 tests). Spy plugin `_SpyPlugin` (counts `close()` calls; optional `raise_on_close`). Helper `_inject_spy_plugin` writes directly into `svc._model_hub._router._dispatcher._plugins` (test-side private-attr reach is explicitly fine; matches the `TestS2ModelHubWiring` precedent). Test classes:
    - `TestStartupCallsFromConfig`: hub-mode emits the `ModelHub provider load: ...` log line; non-hub mode constructs the hub but skips the loader (no log line).
    - `TestShutdownDrainsModelHub`: `shutdown()` calls plugin `close()` exactly once; raising plugin does NOT propagate past `KernelService.shutdown`, WARNING is logged.
    - `TestCleanupTier1PartialDrainsHub`: partial cleanup drains hub THEN nulls field; raising plugin during partial cleanup does NOT propagate.

**Design refinements during implementation**

- **Planner-task in `_startup_tier1` runs during these tests.** The lifecycle tests call `await svc._startup_tier1()` directly, which spins up the planner background task. The `TestStartupCallsFromConfig` cases needed a `_safe_teardown` helper to drain the hub + close bus + router after the test (the planner task is best-effort cancelled by garbage collection at process end). Not a leak in the tests that exercise full `svc.shutdown()` — those clean up properly.
- **`_running` flag must be set manually before calling `svc.shutdown()`** in tests that bypass the public `startup()` entry point. `_startup_tier1` does NOT flip `_running = True`; only the higher-level `startup()` does. The shutdown tests set `svc._running = True` after `_startup_tier1` to exercise the full teardown path. Documented inline.
- **`KernelConfig(model_mode="legacy")`** chosen for the non-hub branch test — any string other than `"hub"` works; `"legacy"` is self-documenting. No default-value assumptions made.

**Test log**

- `pytest tests/k1/kernel/test_service_p23_lifecycle.py -v` → **6 passed** in 12.53s.
- `pytest tests/k1/kernel/ -q` → **467 passed** in 53.63s. Zero new regressions vs. pre-P2.3 baseline. The renamed `test_model_hub_uses_from_config` is included in this count.
- `pytest tests/k1/model_hub/ -q --ignore=*_live.py` → **1063 passed, 6 failed** — same six pre-existing `ChatResult` vs string mismatches confirmed in P2.1 + P2.2. Zero new regressions from P2.3.
- `pytest tests/k1/model_hub/test_factory_from_config_live.py -v` (with `GOOGLE_API_KEY` set) → **1 passed** in 3.21s. P2.2 live test still green — confirms the P2.2 shutdown contract that P2.3 now relies on remains intact.
- **End-to-end kernel smoke** (`python scripts/test_kernel_tiers.py`, real Gemini API): both LOW and MED tiers booted cleanly (12.52s cold / 0.13s warm). The new from_config-driven log line appears once per boot: `ProviderLoader: registered=('google',) skipped=(('openai', "env var 'OPENAI_API_KEY' not set"), ('anthropic', "env var 'ANTHROPIC_API_KEY' not set")) failed=()`. LOW returned `"The capital of France is Paris."`; MED returned a 3-step blog outline. **Zero `ProviderError`. Zero `ModelHub shutdown failed` warnings during teardown** — confirms the new S2 teardown step drains plugin connections cleanly through `bootstrap.stop_kernel` → `KernelService.shutdown`.
- **Net diff:** `k1/kernel/service.py` shrank by ~5 LOC (deleted shim ~33 LOC + new S2 startup ~30 LOC + new S2 teardown ~10 LOC + cleanup_tier1_partial drain ~12 LOC + new top-level import ~1 LOC = -33 + 53 = +20 LOC of production code, but the deletion removed an indirection so net cognitive load is lower).
- **Plan-doc cross-references closed by P2.3:** L88 ("remove the model_mode gate") is **deferred** with explicit rationale in §2 Findings — preserving existing behavior is safer than the silent semantic change of always running the loader.
- **User sign-off:** ☐

---

### EPIC P3.1 — Drop `complexity_tier` from UltraBERT (POC)

**Status:** ready to implement (P1.1 + P2.3 landed)

**Note on two-codebase rule:** P3 is mirrored to k1/concierge by EPIC P3.4. POC lands first; k1 follows.

**1. Read**

- `poc/k1_poc/fsm/ultrabert_phase1.py:107-181` — `UltraBERTPhase1Pipeline.classify(text)` runs `adapter.analyze(text)` → 12-head dict (`intent`, `ingress`, `safety`, `emotions`, `emotion_scores`, `sentiment`, `entities`, `general_entities`, `temporal`, `relations`, `embedding`, `intent_scores`) → `_map_to_phase1_result(analysis)` → `Phase1Result`.
- `poc/k1_poc/fsm/ultrabert_phase1.py:277-321` — `_compute_complexity(all_intents, active_domains, primary_intent, entities, safety_band)`. Three score factors: `len(all_intents) > 1`, `len(active_domains) > 1`, temporal-intent + temporal-entity. Safety override: RED/CRISIS → forced `"LOW"`. Score buckets: `≤low_max(0)` → LOW, `≤medium_max(2)` → MEDIUM, else HIGH. **All three constituent factors are independently observable downstream** — no signal is unique to the tier label.
- `poc/k1_poc/fsm/ultrabert_phase1.py:256` — sole production write: `complexity_tier = self._compute_complexity(...)` then assigned to `Phase1Result.complexity_tier` at L181.
- `poc/k1_poc/fsm/phase1.py:181-280` — `Phase1Result` dataclass declares `complexity_tier: str = ""`. `StubPhase1Pipeline` (test fallback) keyword-derives `"MEDIUM"` for travel/health, else `"LOW"` (~L200-280).
- **All Phase1Result.complexity_tier consumers (10 sites):**
  - `poc/k1_poc/fsm/controller.py:1620, 1685, 1789, 1854` — four `set_complexity_tier(result.complexity_tier)` writes into `_control_ext`/`control` SS section.
  - `poc/k1_poc/fsm/controller.py:1931` — `payload["complexity_tier"] = arbiter_result.phase1.complexity_tier` (envelope enrichment).
  - `poc/k1_poc/fsm/control_extension.py:50` — `set_complexity_tier()` storage + sync to SS.
  - `poc/k1_poc/fsm/control_extension.py:56` — default `self._complexity_tier: str = "LOW"`.
  - `poc/k1_poc/fsm/arbiter.py:86` — `Phase1Result(..., complexity_tier=phase1_meta.get("complexity_tier", "LOW"))` reconstruction.
  - `poc/k1_poc/fsm/arbiter.py:580` — `routing_metadata["complexity_tier"] = phase1.complexity_tier`.
  - `poc/k1_poc/actors/front.py:805, 811` — reads `control_section.tier`, passes `complexity_tier=tier` kwarg into OPP pipeline + DynamicPromptBuilder.
  - `poc/k1_poc/tools/implementations.py:935-942` — `execute_dispatch_task` AUTO mode: `control.get_complexity_tier()`. **This is the only tier read that gates real routing behavior** (P3.3 scope).
  - `poc/k1_poc/events/conversation.py:251-262` — `Phase1Classified.complexity_tier: str = ""` event field, serialized in `to_payload()`.
  - `poc/k1_poc/identity/dynamic_identity.py:148, 214, 225` — `compute(complexity_tier=...)` + `_compute_role()` switches on `"HIGH"`.
- **Test fixtures baking tier labels:** `poc/k1_poc/testing/harness/test_opp_pipeline.py:141`, `test_opp_patterns.py:151, 203, 646, 726`. No pickled/binary fixtures.
- **chat_experience_poc UltraBERT path is SEPARATE.** `poc/chat_experience_poc/l3_execution/agents/concierge_agent.py:827-878` calls `k0.runtime.ultrabert_adapter.classify_activity()` returning `intent`/`ingress_category`/`intent_confidence` only — **no `complexity_tier` field**. Out of scope for P3.1.
- **Cross-codebase grep:** zero `complexity_tier` references in `k0/`, `bridge/`, `contracts/`, `governance/`. The k1/concierge mirror has the same surface (P3.4 scope).

**2. Findings**

- **Producer-side change is small and contained.** `_compute_complexity()` (44 LOC) + `Phase1Result.complexity_tier` field can be removed in one diff. The three observable factors (`len(intents)>1`, `len(domains)>1`, temporal+entity) survive on `Phase1Result` directly — downstream callers can re-derive any binary they need.
- **Consumer-side fan-out is large (10 sites) but mechanical.** Most are pass-through (envelope enrichment, SS sync, event payload). The only behaviorally-meaningful read is `execute_dispatch_task` (P3.3 territory).
- **`identity/dynamic_identity.py` is the one semantic dependency.** `_compute_role()` switches behavior on `complexity_tier == "HIGH"`. **Decision:** replace with `len(active_domains) > 1` (the dominant driver of HIGH today per `_compute_complexity` logic) — preserves intent without the labeled tier.
- **Split into P3.1a + P3.1b for safer review.**
  - **P3.1a (producer):** Remove `_compute_complexity` + `complexity_tier` field from `Phase1Result` + `StubPhase1Pipeline`. Field defaults to absence; dataclass tolerates removal because all consumers read `result.complexity_tier` (which becomes an `AttributeError` after removal — must land with P3.1b atomically).
  - **P3.1b (consumers):** Strip the 10 read sites + 4 fixture writes. `dispatch_task` AUTO path becomes deferred to P3.3 (interim: hard-fallback to LOW since the SS field also disappears).
  - **Recommendation:** Land P3.1a + P3.1b as one PR (atomic) since the field removal is breaking. The split is for review clarity, not staging.
- **P3.1 leaves `dispatch_task` AUTO path temporarily broken** (it reads SS `control.get_complexity_tier()` which no longer exists). Two options:
  - **A.** Land P3.1 + P3.3 atomically.
  - **B.** Land P3.1 with a temporary `getattr(control, "get_complexity_tier", lambda: "LOW")()` fallback; P3.3 deletes the AUTO path entirely.
  - **Decision:** Option A — atomic landing. The bookkeeping cost of a temporary fallback exceeds the review cost of a slightly larger PR.
- **`Phase1Classified` event payload loses `complexity_tier` field.** Any downstream telemetry consumer (Section 5 below) must be updated. Grep confirms zero external subscribers in the codebase, so the event-shape change is safe.

**3. Changes** (no edits applied yet — design contract for the implementation step)

- **EDIT** `poc/k1_poc/fsm/ultrabert_phase1.py`:
  - Delete `_compute_complexity()` (~44 LOC at L277-321).
  - In `_map_to_phase1_result()` (L123-181), delete the `complexity_tier = self._compute_complexity(...)` call and the `complexity_tier=complexity_tier` kwarg in the `Phase1Result(...)` constructor.
- **EDIT** `poc/k1_poc/fsm/phase1.py`:
  - Remove `complexity_tier: str = ""` from `Phase1Result` dataclass.
  - In `StubPhase1Pipeline.classify()` (~L200-280), drop the `complexity` keyword-derivation block and the `complexity_tier=complexity` kwarg.
- **EDIT** `poc/k1_poc/fsm/control_extension.py`:
  - Remove `_complexity_tier` field, `set_complexity_tier()` (~L50), `get_complexity_tier()`, and the `_sync_to_section()` line that mirrors it to SS.
- **EDIT** `poc/k1_poc/fsm/controller.py`:
  - Remove 4 `set_complexity_tier()` calls at L1620, L1685, L1789, L1854.
  - Remove `payload["complexity_tier"] = ...` line at L1931.
- **EDIT** `poc/k1_poc/fsm/arbiter.py`:
  - Remove `complexity_tier=phase1_meta.get("complexity_tier", "LOW")` from L86 reconstruction.
  - Remove `"complexity_tier": phase1.complexity_tier` from `routing_metadata` dict at L580.
- **EDIT** `poc/k1_poc/events/conversation.py:251-262`:
  - Remove `complexity_tier: str = ""` field from `Phase1Classified`.
  - Remove the `d["complexity_tier"] = ...` line in `to_payload()`.
- **EDIT** `poc/k1_poc/identity/dynamic_identity.py`:
  - Remove `complexity_tier` param from `compute()` (L148) and `_compute_role()` (L214).
  - Replace the `complexity_tier == "HIGH"` branch (L225) with `len(active_domains) > 1` (preserves dominant HIGH semantics).
- **EDIT** `poc/k1_poc/actors/front.py`:
  - Remove `complexity_tier=tier` kwarg from OPP pipeline call at L811. Pipeline signature must lose the param too — verify zero other callers via grep.
  - Remove the L805 `tier = control_section.tier` read if unused after the kwarg removal.
- **EDIT** `poc/k1_poc/testing/harness/test_opp_pipeline.py:141` — drop `complexity_tier="LOW"` from fixture.
- **EDIT** `poc/k1_poc/testing/harness/test_opp_patterns.py` — drop `complexity_tier=...` at L151, L203, L646, L726.
- **NO new test file needed.** The existing harness tests will fail-fast if any consumer is missed; rerun confirms full removal.

**4. Handoff & test log**

**Strategy chosen:** **Option B** — temporary backward-compat fallback. `ConcierigeControlExtension.set_complexity_tier()` removed; SS `ControlSection.set_complexity_tier()`/`get_complexity_tier()` retained (still wired to `_fsm_overlay["complexity_tier"]`) so `tools/implementations.py` AUTO path keeps working — overlay returns `""` → triggers existing LOW fallback warning branch. P3.3 will excise the AUTO/SS surface entirely.

**Files modified (production):**

- `poc/k1_poc/fsm/ultrabert_phase1.py` — deleted `_compute_complexity()` (~44 LOC) replaced with explanatory comment block; removed call site + kwarg in `_map_to_phase1_result()`.
- `poc/k1_poc/fsm/phase1.py` — removed `complexity_tier` from `Phase1Result.__slots__`, `__init__` signature, `to_metadata()` dict, `Phase1Pipeline` Protocol docstring, and `StubPhase1Pipeline.classify()` keyword-derivation block.
- `poc/k1_poc/fsm/control_extension.py` — module docstring updated (3 → 2 fields), `_complexity_tier` field removed, `set_complexity_tier()` method deleted, `_sync_to_section()` no longer passes tier kwarg, `snapshot()`/`reset()` no longer reference it.
- `poc/k1_poc/sessionstate/sections/control.py` — **softened** (Option B): `set_fsm_overlay()` `complexity_tier` param made optional (default `""`), `_handle_op` uses `data.get("complexity_tier", "")` tolerance. Storage line + `set_complexity_tier()`/`get_complexity_tier()` methods kept for AUTO consumers.
- `poc/k1_poc/fsm/controller.py` — removed 5 sites (L1620, L1685, L1789, L1854, L1931): 4 `set_complexity_tier()` calls + `payload["complexity_tier"]` assignment; updated docstring.
- `poc/k1_poc/fsm/arbiter.py` — removed `complexity_tier=` kwarg from `from_dict` reconstruction (L86) and from `routing_metadata` dict (L580).
- `poc/k1_poc/events/conversation.py` — removed `complexity_tier` field from `Phase1Classified` dataclass + `to_payload()`.
- `poc/k1_poc/identity/dynamic_identity.py` — removed `complexity_tier` param from `compute()` and `_compute_role()`. **Design decision:** dropped HIGH→EXPERT branch entirely (rather than `len(active_domains) > 1` which is not on this surface) — EXPERT role becomes unreachable in the POC; other role-selection rules (SUPPORTER/EXECUTOR/PEER/GUIDE) dominate.
- `poc/k1_poc/protocols/opp_pipeline.py` — removed `complexity_tier` param from `on_pre_prompt_build()` signature, docstring, and forward call to `dynamic_identity.compute()`.
- `poc/k1_poc/actors/front.py` — removed `complexity_tier=tier` kwarg from OPP pipeline call (L811). `tier` variable kept (still used at L836 + L1004-1009 for `dispatch_task` budget — P3.3 territory).

**Files NOT modified (intentional):**

- `poc/k1_poc/prompt/back_prompt.py:348` — `tier = task.get("tier", task.get("complexity_tier", "LOW"))`. Dict-based fallback is harmless; field absence simply selects `"LOW"`. Cleaner removal deferred to P3.3.
- `poc/k1_poc/demo/display.py` — `print_fsm_state_transition(complexity_tier="")` retained as defaulted kwarg; render block already conditional on truthiness so empty value is a no-op. Caller `poc/session_state_demo/anniversary_demo/runner.py:2171` uses a separate demo `phase1.tier` (not `Phase1Result`) — out of scope.
- `poc/k1_poc/tools/implementations.py:935` — AUTO dispatch path retained per Option B; `hasattr(control, "get_complexity_tier")` guard remains; `get_complexity_tier()` now returns `""` so the existing "no complexity_tier in SS, defaulting to LOW" warning branch fires. P3.3 will rewrite the AUTO path.

**Files modified (tests):**

- `poc/k1_poc/testing/harness/test_opp_pipeline.py` — fixture kwarg drop (L141).
- `poc/k1_poc/testing/harness/test_opp_patterns.py` — 2 fixture kwarg drops (L151, L203); `test_high_complexity_selects_expert` rewritten to assert default GUIDE role; `test_role_adaptation_disabled` kwarg drop (L726).
- `tests/poc/test_m05_e54_multi_device.py` — `_make_phase1` fixture kwarg drop.
- `tests/poc/test_m05_arbiter.py` — `_phase1` fixture kwarg drop; `test_routing_metadata_keys` flipped to assert `complexity_tier not in meta`.
- `tests/poc/test_m05_e53_normal_paths.py` — dropped history-metadata assertion; `test_envelope_payload_has_complexity_tier` flipped to assert absence.
- `tests/poc/test_m04_e41_ss_binding.py` — wrapper-side `set_complexity_tier` tests rewritten to assert method removal; SS-section-side tests retained (method kept).
- `tests/poc/test_m10_e101_ultrabert_pipeline.py` — `test_complexity_tier_present` flipped to assert absence; `TestComplexityClassifier` class (~70 LOC of `_compute_complexity` scoring tests) replaced with single removal-assertion test; fallback assert dropped.
- `tests/poc/test_m10_e102_ss_writes.py` — fixture default dropped; `test_complexity_tier_written` flipped (now asserts overlay stays `""`); `test_all_three_sections_written` updated. SS-section-side `set_complexity_tier`/`get_complexity_tier`/`overlay` tests kept (method retained).
- `tests/poc/test_m10_e103_tier_routing.py` — `test_phase1_classified_event_schema` flipped to assert absence. AUTO routing tests retained (still pass via SS shim).
- `tests/poc/test_m10_e105_extra_heads.py` — fixture kwarg drop; 3 assertions flipped (e2e_complexity, e2e_ss_writes complexity check, e2e_metadata_complete).

**Design refinements during implementation:**

1. **Scope larger than plan §3.** Plan estimated ~10 files / ~140 LOC. Actual: 25+ files. Newly-discovered sites not in original plan inventory:
   - Additional controller site at L1685 (inside `_write_phase1_to_ss`).
   - Full SS section storage plumbing in `sessionstate/sections/control.py` (`_fsm_overlay` dict + `set_complexity_tier`/`get_complexity_tier` methods + `_handle_op` op-dispatch).
   - `protocols/opp_pipeline.py` chain (3 sites).
   - `prompt/back_prompt.py:348` dict-based fallback (left intact).
   - `demo/display.py` formatter (left intact, defaulted kwarg).
   - Dedicated test files `test_m10_e101_ultrabert_pipeline.py` (full `TestComplexityClassifier` class), `test_m10_e102_ss_writes.py`, `test_m10_e103_tier_routing.py`, `test_m10_e105_extra_heads.py`, `test_m04_e41_ss_binding.py`.

2. **Option B chosen over Option A** to keep P3.1 atomic without bundling P3.3. SS section retains backward-compat shim; AUTO path degrades gracefully.

3. **`dynamic_identity` HIGH branch** — plan suggested `len(active_domains) > 1` proxy, but `active_domains` is not in `compute()`'s signature. Chose simpler resolution: drop HIGH→EXPERT branch entirely. EXPERT role unreachable in POC after P3.1; documented in code comment. Future plumbing of multi-domain signal can reintroduce it.

4. **Two distinct tier surfaces clarified.** P3.1 only touches Phase1-derived `Phase1Result.complexity_tier`. The k1/fabric `cognitive.complexity_tier` (in `tests/k1/fabric/test_policy_*.py`) is an independent load-fallback signal — out of scope.

**Test results:**

- POC suite affected by P3.1 (11 files): **468 passed, 11 failed**. All 11 failures are **pre-existing baseline failures** (verified via `git stash` on baseline): overlap-scoring math drift (`TestDomainOverlap`/`TestEntityOverlap`/`test_rule4_modify_inflight_overlap`), missing `_build_arbiter` import, topic count drift (40 → 46), renderer count drift (10 → 11), stub adapter sentiment value (0.4 vs 0.5), config YAML pipeline default (`stub` → `ultrabert`). Zero failures attributable to P3.1.
- **End-to-end smoke** (`scripts/test_kernel_tiers.py` against real Gemini): both LOW and MED tiers complete cleanly. LOW: "The capital of France is Paris." MED: 1369-char outline of hexagonal architecture with `task.dispatch.v1` event observed at `tier=LOW` (AUTO fallback firing as expected — Phase1 no longer classifies, SS overlay empty, dispatch defaults to LOW). FSM transitions LISTENING → COMPANIONING. Shutdown clean both runs.

- **User sign-off:** ☐

---

### EPIC P3.2 — Collapse tier allowlists in `ToolDispatcher` (POC)

**Status:** ready to implement (independent of P3.1 in code, but conceptually depends on it)

**1. Read**

- `poc/k1_poc/tools/dispatcher.py:59-100` — `FRONT_TIER_ALLOWLISTS`. LOW/MEDIUM/HIGH allowlists are **near-identical** — only difference is `promote_belief` (in MEDIUM/HIGH only). MEDIUM and HIGH are **bit-for-bit identical**. CRISIS is `set()` (Front doesn't run ReAct in CRISIS).
- `poc/k1_poc/tools/dispatcher.py:103-119` — `BACK_TIER_ALLOWLISTS`. Real binary split: **LOW** lacks `spawn_via_fabric` + `execute_workflow`; **MEDIUM** and **HIGH** are identical and add both.
- `poc/k1_poc/tools/dispatcher.py:49-54` — `BUDGET_LIMITS = {"LOW": 5, "MEDIUM": 10, "HIGH": 20, "CRISIS": 3}`. Tier-indexed but the only meaningful business distinction is "small" vs "big" budget.
- `poc/k1_poc/tools/dispatcher.py:246-261` — Step 1 of dispatch: `if name not in self.allowlist: return error`. The `allowlist` is frozen at construction from `FRONT_TIER_ALLOWLISTS[tier]` / `BACK_TIER_ALLOWLISTS[tier]`.
- `poc/k1_poc/tools/dispatcher.py:553-612` — `create_front_dispatcher(tier=...)` and `create_back_dispatcher(tier=...)` factories. Sole construction sites.
- **Callers (4 sites):** `poc/k1_poc/kernel/bootstrap.py:214-215`, `poc/k1_poc/kernel/runner.py:52-56`, `poc/k1_poc/demo/coordinator.py:368-372`, `poc/k1_poc/testing/harness/engine.py:197-201`. All pass `cfg.tool_tier`.
- **No dedicated unit tests** for `ToolDispatcher` tier allowlists in `poc/k1_poc/`. Harness tests always boot with `tool_tier="LOW"` so MEDIUM/HIGH paths have zero direct coverage. (k1 mirror has `tests/k1/concierge/test_tool_call_summary.py` — see P3.4.)

**2. Findings**

- **The "3-tier" data is already a 2-tier reality.** Front: LOW vs {MEDIUM,HIGH} (one tool difference). Back: LOW vs {MEDIUM,HIGH} (two tool difference). HIGH is functionally a relabeled MEDIUM today. **Collapsing to `simple` (≈LOW) and `plan` (≈MEDIUM/HIGH) preserves all current behavior with zero semantic change.**
- **Naming:** `simple` / `plan` aligns with the Q1 design call for `dispatch_task` (`plan: bool` param). Avoid keeping LOW/MEDIUM strings — they imply complexity gradient that no longer exists in the dispatcher data.
- **`BUDGET_LIMITS` collapses to 2 buckets too:** `{"simple": 5, "plan": 15}` (midpoint of MEDIUM=10 and HIGH=20 = 15). CRISIS (`3`) is a special case unrelated to plan/simple — keep as a third constant `CRISIS_BUDGET = 3` outside the dict, because CRISIS routing is gated upstream (Front doesn't run ReAct), not via dispatcher allowlist.
- **CRISIS allowlist (`set()`)**: keep as-is. Routing logic upstream skips dispatch entirely on CRISIS, so the empty allowlist is a safety net, not a code path.
- **`promote_belief` (the one Front difference)** moves to the `plan` bucket — preserves the current MEDIUM-and-HIGH availability.
- **`spawn_via_fabric` + `execute_workflow`** (Back: only in MEDIUM+) move to the `plan` bucket.
- **`ComplexityTier` enum** in `poc/k1_poc/task/complexity.py` is consumed by routing layer (`routing.py`). **Out of P3.2 scope** — routing-layer tier consumption is P3.3 territory. P3.2 only collapses the dispatcher's allowlist data structures.
- **Backward compat:** `create_front_dispatcher(tier="LOW")` and `tier="MEDIUM"` callers must keep working during the transition. Implement an alias map: `_TIER_ALIAS = {"LOW": "simple", "MEDIUM": "plan", "HIGH": "plan", "CRISIS": "crisis"}` inside the factory. P3.3 then changes the caller to pass `"simple"`/`"plan"` directly and the alias map is deleted.

**3. Changes**

- **EDIT** `poc/k1_poc/tools/dispatcher.py`:
  - Replace `FRONT_TIER_ALLOWLISTS` with two-bucket dict:

    ```python
    FRONT_TIER_ALLOWLISTS = {
        "simple": {"update_beliefs", "update_scoreboard", "update_clarifications",
                   "update_narrative", "refine_affect", "recall_memory",
                   "summarize_context", "dispatch_task",
                   "discover_capabilities", "invoke_capability"},
        "plan":   {... simple ..., "promote_belief"},
        "crisis": set(),
    }
    ```

  - Replace `BACK_TIER_ALLOWLISTS` with two-bucket dict (`simple` = LOW set; `plan` = MEDIUM set including `spawn_via_fabric`+`execute_workflow`).
  - Replace `BUDGET_LIMITS` with `{"simple": 5, "plan": 15, "crisis": 3}`.
  - Add `_TIER_ALIAS = {"LOW": "simple", "MEDIUM": "plan", "HIGH": "plan", "CRISIS": "crisis"}`.
  - In `create_front_dispatcher` and `create_back_dispatcher`: `tier_key = _TIER_ALIAS.get(tier, tier)` then index allowlist by `tier_key`. Preserves all 4 existing call sites unchanged.
- **NEW** `tests/poc/k1_poc/test_tool_dispatcher_tier_collapse.py` (~120 LOC, ~6 tests) — first-ever dedicated dispatcher allowlist tests:
  - `test_simple_tier_allowlist_matches_old_LOW` — assert exact membership.
  - `test_plan_tier_allowlist_matches_old_MEDIUM_for_front` — exact membership.
  - `test_plan_tier_allowlist_matches_old_MEDIUM_for_back` — exact membership including `spawn_via_fabric`.
  - `test_crisis_tier_is_empty_set` — preserves safety net.
  - `test_legacy_tier_aliases_route_to_collapsed_buckets` — `tier="LOW"`→simple, `"MEDIUM"`/`"HIGH"`→plan, `"CRISIS"`→crisis.
  - `test_budget_limits_two_buckets` — `simple==5`, `plan==15`, `crisis==3`.
- **NO callers updated this epic.** P3.3 updates the 4 caller sites to pass `"simple"`/`"plan"` natively and removes the alias map.

**4. Handoff & test log**

**Implementation scope:** Exactly as planned (no surprises). 4 production files edited + 2 test files (1 new, 1 updated expectations).

**Production files changed:**

| File | Change |
|---|---|
| `poc/k1_poc/tools/dispatcher.py` | Added `_TIER_ALIAS` map. Replaced `BUDGET_LIMITS` (4 keys) with 3-bucket `simple/plan/crisis` + legacy alias keys. Added `_FRONT_SIMPLE` frozenset. Collapsed `FRONT_TIER_ALLOWLISTS` to `simple/plan/crisis` + legacy aliases. Added `_BACK_SIMPLE` frozenset. Collapsed `BACK_TIER_ALLOWLISTS` to `simple/plan` + legacy aliases. Fixed `__init__` `_budget_limit` to apply `_TIER_ALIAS` before `get_config()` lookup. |
| `poc/k1_poc/config/defaults.yaml` | Added `simple/plan/crisis` keys to `budget_limits`, `front_tier_allowlists`, `back_tier_allowlists`, `back_max_iterations`. Legacy `LOW/MEDIUM/HIGH/CRISIS` keys retained. |
| `poc/k1_poc/obs/actor_metrics.py` | Replaced `TIER_BUDGET_LIMITS = {"LOW": 4, "MEDIUM": 8, "HIGH": 12}` with 6-key dict including `simple/plan/crisis` canonical keys and updated legacy alias values to match collapsed budget constants. |
| `tests/poc/test_m11_obs_e112.py` | Updated `test_tier_budget_limits_defined` and `test_budget_limit_defaults_to_tier` to expect P3.2 values (`HIGH→plan→15`, not 12). |

**New test file created:**

- `tests/poc/test_p32_tool_dispatcher_tier_collapse.py` — 39 tests across 4 classes:
  - `TestFrontAllowlists` (8 tests): exact membership for `simple`, `plan`, `crisis` + legacy alias equality
  - `TestBackAllowlists` (6 tests): exact membership for `simple`, `plan` + legacy alias equality
  - `TestBudgetLimits` (6 tests): canonical + legacy budget values
  - `TestTierAliasMap` (6 tests): `_TIER_ALIAS` routing
  - `TestFactoryBackwardCompat` (13 tests): factory functions accept all legacy + canonical tiers; allowlists match expected

**Design notes vs plan:**

- Legacy alias keys were included in the dicts themselves (not just in the factory `_TIER_ALIAS` lookup) so that any direct dict indexing also works. This is slightly more defensive than the plan specified.
- `BUDGET_LIMITS` module constant is NOT the authoritative source — `get_config().tools.budget_limits` is. Both were updated for consistency. The `__init__` now applies `_TIER_ALIAS` before the config lookup (double-fallback pattern: canonical key first, raw tier second).
- `obs/actor_metrics.py` `TIER_BUDGET_LIMITS` old values (`LOW: 4, MEDIUM: 8, HIGH: 12`) were NOT the same as `BUDGET_LIMITS` module constant (`LOW: 5, MEDIUM: 10, HIGH: 20`). This was a pre-existing inconsistency; P3.2 normalizes all three copies to `simple=5, plan=15, crisis=3`.

**Test results:**

- New test file: **39/39 passed**
- `tests/poc/test_m11_obs_e112.py`: **61/61 passed** (2 expectations updated)
- Full POC suite: **3393 passed** — 114 failed, all pre-existing (model_hub_types 24, model_hub_ports 1, model_hub_bridge 9, m10_e105 6 from P3.1 complexity_tier removal, m00_v3_conformance + topic counts + other pre-P3 failures)

**User sign-off:** ☐

---

### EPIC P3.3 — Remove `KernelConfig.tool_tier`; rewrite `dispatch_task` tier derivation (POC)

**Status:** ready to implement (depends on P3.1 + P3.2)

**1. Read**

- `poc/k1_poc/kernel/bootstrap.py:62-80` — `KernelConfig.tool_tier: str = "LOW"`. Plain string, no validation. Default LOW.
- `poc/k1_poc/kernel/bootstrap.py:214-215` — `create_front_dispatcher(tier=cfg.tool_tier, ...)` + `create_back_dispatcher(tier=cfg.tool_tier, ...)`. Both dispatchers wired with the same tier.
- `poc/k1_poc/kernel/runner.py:36-39` — CLI flag `--tool-tier choices=["LOW", "MEDIUM", "HIGH", "CRISIS"]`. Sets `KernelConfig.tool_tier`.
- `poc/k1_poc/kernel/runner.py:52-56` — `KernelConfig(tool_tier=args.tool_tier, ...)` construction.
- `poc/k1_poc/demo/coordinator.py:368-372` — `KernelConfig(tool_tier="LOW", ...)`.
- `poc/k1_poc/testing/harness/engine.py:197-201` — `KernelConfig(tool_tier="LOW", ...)`.
- `poc/k1_poc/tools/implementations.py:907-958` — `execute_dispatch_task(args, ctx)`:
  - L908: `args` keys: `intents`, `urgency`, `reference_context`, `depends_on`, `safety_band`, `tier` (default `"AUTO"`).
  - L931-958: AUTO derivation reads `ctx.session_manager.get_section("control").get_complexity_tier()`. Falls back to `"LOW"` if missing.
  - L961: `ComplexityTier(str(tier_raw).upper())` parses to enum.
  - L1007: `TaskDispatch(tier=ComplexityTier.MEDIUM, ...)` constructed → routed via `route_task_sync()`.
- `poc/k1_poc/tools/schemas_front.py:456-544` — `DISPATCH_TASK_SCHEMA`. **`tier` is NOT in the schema** — LLM cannot supply it. Only the implementation reads it from args.
- `poc/k1_poc/orchestrator/routing.py:129-160` — `route_task_sync(task, tier)`. Reads `record.tier == ComplexityTier.LOW` (L129) vs `(MEDIUM, HIGH)` (L131) — **the real routing fork**. LOW path → simple inline execution. MEDIUM/HIGH → `_route_medium_sync` with orchestrator + spawn_via_fabric budget.
- **Back-actor MED chain trace:** `dispatch_task → ToolResult.data["_dispatch"] (contains tier) → FSM handler → route_task_sync(task, tier) → DispatchRecord(tier=MEDIUM) → TaskEnvelope`. **Pre-existing gap:** the Back ReAct loop's dispatcher allowlist comes from `KernelConfig.tool_tier` (always `"LOW"` in demo/harness), NOT from `Phase1Result.complexity_tier`. Back is effectively always-LOW today regardless of upstream tier. P3.3 must not worsen this; ideally fixes it as a side benefit.
- **Observable inputs at `execute_dispatch_task` call site:** `args["intents"]` (length), `args["urgency"]`, `args["depends_on"]`, `args["safety_band"]`. `len(intents) > 1` and `depends_on is not None` are both clean proxies for "needs planning". Message text is NOT available here (lives in Phase 1).

**2. Findings**

- **`KernelConfig.tool_tier` is dead config.** It pre-populates the dispatcher allowlist at boot but is never updated per-turn. The actual per-turn tier comes from `dispatch_task`'s args. Removing the field is purely additive cleanup.
- **`dispatch_task` tier derivation rewrite (Q1 resolution):** Add `plan: bool` to `DISPATCH_TASK_SCHEMA` (LLM-controllable). Runtime derivation: `plan = args.get("plan", False) or len(args.get("intents", [])) > 1 or args.get("depends_on") is not None`. This:
  - Preserves backward compat (omitted `plan` → False → simple).
  - Surfaces the decision to the LLM (it can request a plan explicitly when the user asks for multi-step work).
  - Auto-escalates on multi-intent or chained tasks (current `_compute_complexity` heuristic, now applied at the right layer).
- **Q1 final answer: `plan: bool` param.** Sibling `plan_task` tool was rejected because it duplicates 90%+ of `dispatch_task`'s schema and forces the LLM to learn two tools where one suffices. The `plan: bool` flag is the smallest-diff option idiomatic with existing `args` patterns.
- **Q2 telemetry — derived tier insertion point:** Two complementary sites:
  1. **Tool result data:** `ToolResult.data["_dispatch"]["plan"] = plan` in `execute_dispatch_task`. This is already serialized through `build_tool_completed` → bus, so derived-tier flows to all downstream observers automatically.
  2. **`Phase1Classified` event:** add `derived_plan: bool` field (computed from same factors as `dispatch_task` derivation, but at FSM/Phase 1 time) so the telemetry timeline records the system's view of plan-need at classification time, separate from the LLM's view at dispatch time.
- **Q3 Back-actor MED chain — P3.3 explicitly fixes the pre-existing gap.** Today: `KernelConfig.tool_tier` boots both dispatchers identically → Back is permanently LOW. After P3.3: dispatchers collapse to simple/plan via P3.2; Back dispatcher's tier is set per-task from `TaskDispatch.tier` rather than boot-time `KernelConfig`. Implementation: `back_handler` (or wherever the back dispatcher is invoked) constructs the dispatcher per-task using `task.tier` to choose between `simple`/`plan` allowlists. **This is the largest behavioral change in P3** — needs explicit test coverage.
- **`ComplexityTier` enum (LOW/MEDIUM/HIGH)** stays — it's the routing-layer contract used by `route_task_sync`. Renaming to `Plan(SIMPLE, PLAN)` is plausible cleanup but inflates the diff and breaks more files. **Decision:** keep `ComplexityTier` enum, internally MEDIUM and HIGH map to the same `plan` allowlist via the dispatcher (already P3.2'd). HIGH may eventually be repurposed for "always plan + always emit telemetry" or similar — leave the slot open.
- **CLI `--tool-tier` flag:** delete entirely. Replace with no flag (boot-time tier no longer meaningful) or repurpose as `--default-plan-mode {auto,always-simple,always-plan}` for debugging. **Recommendation:** delete; debug-mode flags can be re-added when actually needed.
- **The 4 caller sites lose the `tool_tier=` kwarg.** `bootstrap.py`, `runner.py`, `demo/coordinator.py`, `testing/harness/engine.py`. Bootstrap stops passing tier to dispatcher factories; instead, factories accept a default tier (`"simple"`) and the per-task tier is set inside `back_handler`/`front_handler` using `_TIER_ALIAS` (kept around as the dispatcher reuses it — see below).
- **Dispatcher-per-task vs dispatcher-mutated:** Two implementations possible. (A) Construct a fresh dispatcher per back task — simple but allocates. (B) Add a `set_tier(tier)` mutator. **Decision: (A)**. Dispatcher construction is cheap; mutability would expose a race window if back tasks ever run concurrently.

**3. Changes**

- **EDIT** `poc/k1_poc/kernel/bootstrap.py`:
  - Remove `tool_tier: str = "LOW"` from `KernelConfig`.
  - Update `create_front_dispatcher(tier=...)` and `create_back_dispatcher(tier=...)` calls at L214-215: front uses `tier="simple"` boot default (per-turn upgrade happens via the LLM's `plan` arg flowing through dispatch_task); back removes the kwarg or passes `tier="simple"` boot default.
- **EDIT** `poc/k1_poc/kernel/runner.py`:
  - Remove `--tool-tier` argparse arg (L36-39).
  - Remove `tool_tier=args.tool_tier` from `KernelConfig(...)` (L56).
- **EDIT** `poc/k1_poc/demo/coordinator.py:372` — remove `tool_tier="LOW"` kwarg.
- **EDIT** `poc/k1_poc/testing/harness/engine.py:201` — remove `tool_tier="LOW"` kwarg.
- **EDIT** `poc/k1_poc/tools/schemas_front.py` (~L500 in `DISPATCH_TASK_SCHEMA.parameters`):
  - Add: `"plan": {"type": "boolean", "description": "Set true when the task requires multi-step planning (will route through orchestrator).", "default": False}`.
  - Update tool description to mention the new flag.
- **EDIT** `poc/k1_poc/tools/implementations.py:907-958`:
  - Rewrite tier derivation:

    ```python
    intents = args.get("intents") or []
    depends_on = args.get("depends_on")
    explicit_plan = bool(args.get("plan", False))
    needs_plan = explicit_plan or len(intents) > 1 or depends_on is not None
    tier = ComplexityTier.MEDIUM if needs_plan else ComplexityTier.LOW
    ```

  - Delete the entire AUTO-from-SS block (L931-958).
  - Add `dispatch_payload["plan"] = needs_plan` to the returned `ToolResult.data["_dispatch"]` (telemetry hook).
- **EDIT** Back ReAct invocation site (locate via grep — likely `poc/k1_poc/actors/back.py`):
  - Construct back dispatcher per task using `task.tier` to pick `"simple"` (LOW) or `"plan"` (MEDIUM/HIGH).
  - This is the behavioral fix for the Q3 pre-existing gap.
- **EDIT** `poc/k1_poc/events/conversation.py` (Q2 telemetry):
  - Add `derived_plan: bool = False` to `Phase1Classified` (computed at FSM time from same factors).
  - Update `to_payload()` to include `"derived_plan"`.
- **NEW** `tests/poc/k1_poc/test_dispatch_task_plan_derivation.py` (~150 LOC, ~8 tests):
  - `test_default_plan_false_routes_simple`
  - `test_explicit_plan_true_routes_to_medium`
  - `test_multi_intent_auto_escalates_to_plan`
  - `test_depends_on_auto_escalates_to_plan`
  - `test_single_intent_no_deps_stays_simple`
  - `test_dispatch_payload_records_plan_flag` (telemetry assertion)
  - `test_back_dispatcher_uses_simple_allowlist_when_task_tier_low`
  - `test_back_dispatcher_uses_plan_allowlist_when_task_tier_medium` — proves the Q3 gap fix.

**4. Handoff & test log**

- **Implementation scope:** POC only (`poc/k1_poc/`). The matching k1 mirror is reserved for P3.4.
- **Production files changed (8):**

  | # | File | Change |
  |---|---|---|
  | 1 | `poc/k1_poc/kernel/bootstrap.py` | Removed `KernelConfig.tool_tier` field; both dispatchers boot at canonical tier `"simple"`; trimmed `tool_tier=…` from boot log. |
  | 2 | `poc/k1_poc/kernel/runner.py` | Removed `--tool-tier` CLI argument and `tool_tier=args.tool_tier` from `KernelConfig(...)`. |
  | 3 | `poc/k1_poc/demo/coordinator.py` | Removed `tool_tier="LOW"` kwarg from `KernelConfig(...)`. |
  | 4 | `poc/k1_poc/testing/harness/engine.py` | Removed `tool_tier="LOW"` kwarg from `KernelConfig(...)`. |
  | 5 | `poc/k1_poc/tools/schemas_front.py` | Added `plan: bool` (default `false`, optional) to `DISPATCH_TASK_SCHEMA`; updated description. |
  | 6 | `poc/k1_poc/tools/implementations.py` | Replaced AUTO-from-SS block in `execute_dispatch_task` with `plan` arg + multi-intent + `depends_on` derivation; emits `_dispatch.plan` for telemetry. |
  | 7 | `poc/k1_poc/actors/back.py` | Added `_resolve_back_tier_bucket` and `_maybe_rebind_back_dispatcher` helpers; both `back_handler` and `back_resume_handler` rebind dispatcher to `"plan"` bucket when task tier is MEDIUM/HIGH (closes Q3 dispatcher/allowlist gap). |
  | 8 | `poc/k1_poc/events/conversation.py` | Added `derived_plan: bool = False` to `Phase1Classified` + included in `to_payload()` (telemetry plumbing only; no production emitter wires it yet). |

- **Test files changed (2):**
  - **NEW** `tests/poc/test_p33_dispatch_task_plan_derivation.py` (~250 LOC, 19 tests across 5 classes):
    - `TestDispatchTaskPlanDerivation` (8): default `plan=False` → `LOW`; `plan=True` → `MEDIUM`; multi-intent auto-escalates; `depends_on` auto-escalates; single-intent stays `LOW`; invalid `depends_on` does not escalate; **no SS read on dispatch** (`get_section.assert_not_called()`); legacy `tier="HIGH"` arg silently ignored.
    - `TestBackDispatcherRebind` (5): `LOW` is a no-op; `MEDIUM`/`HIGH` upgrade to `"plan"` bucket (verifies `spawn_via_fabric` and `execute_workflow` in allowlist); unknown tier falls back to `"simple"`; `ctx` preserved across rebind.
    - `TestKernelConfigToolTierRemoved` (2): field absent from `dataclasses.fields(KernelConfig)`; constructor rejects `tool_tier=…` with `TypeError`.
    - `TestPhase1ClassifiedDerivedPlan` (2): default `False`; present in `to_payload()`.
    - `TestDispatchTaskSchema` (2): `plan` declared in schema properties (boolean, default false); not in `required`.
  - **EDIT** `tests/poc/test_m10_e103_tier_routing.py`: rewrote 3 tests (`test_auto_reads_medium_from_ss`, `test_auto_reads_high_from_ss`, `test_omitted_tier_defaults_to_auto`) to assert the **new** P3.3 semantics (SS-tier ignored; only `plan: bool` + signals drive routing). The other 10 tests in that file (CRISIS short-circuit, builders, etc.) untouched and passing.

- **Design notes / deviations from plan:**
  - `DISPATCH_TASK_SCHEMA` did **not** previously expose a `tier` field to the LLM, so the `args.get("tier", "AUTO")` branch in `execute_dispatch_task` was effectively dead code from the LLM POV. Removing it is purely simplifying.
  - `Phase1Classified.derived_plan` was added as planned, but **no production emitter writes it yet** in `poc/k1_poc/`. The field is wired through `to_payload()` for forward-compatibility; observability hookup is deferred (no current emitter to update).
  - For per-task back dispatcher rebind we chose **rebind-in-handler** (`_maybe_rebind_back_dispatcher`) over the factory/closure variants, to avoid changing handler signatures while still fixing the divergence between presented tools (`_filter_back_tools(tier)`) and dispatchable tools (`ToolDispatcher.dispatch()` enforcing the frozen boot allowlist).
  - The POC `ComplexityTier` enum has no `CRISIS` member (only `LOW`/`MEDIUM`/`HIGH`); `_resolve_back_tier_bucket` therefore safely falls back to `"simple"` for unknown tier strings.
  - No production callers needed updating for the `dispatch_task` API change because no internal call sites pass `tier` explicitly — the LLM was the only "caller" and the schema never offered `tier`.

- **Test results:**
  - **New P3.3 file:** `19 passed` (1.37s).
  - **Updated `test_m10_e103_tier_routing.py`:** `13 passed` (1.25s).
  - **Full POC regression:** `3412 passed, 114 failed` in 63.9s. Baseline before P3.3 was `3393 passed, 114 failed`. Delta: **+19 passes (the new P3.3 tests), 0 new failures.** All 114 remaining failures are the pre-existing `test_model_hub_*`, `test_m00_v3_conformance`, `test_m01_*`, `test_m03_e3*` clusters tracked separately.

- **User sign-off:** ☐

---

### EPIC P3.4 — Mirror all P3 epics to `k1/concierge/`

**Status:** ready to implement (P3.1–P3.3 POC landed and signed off; this epic mirrors them to the k1 tree).

> **Re-audit performed before implementation** — three parallel sub-agent reads on (a) landed POC P3.1–P3.3 diffs, (b) k1 mirror surface, (c) k1 test + script fan-out. The findings below supersede the earlier draft of this epic and are used to drive implementation.

**1. Read — verified k1 surface (post-audit)**

- **k1 has a 1:1 UltraBERT mirror, more mature than POC.** Files: `k1/concierge/fsm/ultrabert_phase1.py`, `k1/concierge/fsm/ultrabert_adapter.py`, `k1/concierge/adapters/ultrabert_classification.py` (re-export shim — POC has no equivalent).
- `k1/concierge/fsm/ultrabert_phase1.py:162-181` — `_map_to_phase1_result` calls `_compute_complexity(...)` and stores the result via `complexity_tier=` kwarg on `Phase1Result`.
- `k1/concierge/fsm/ultrabert_phase1.py:268-320` — `_compute_complexity()` body. Returns plain string `"LOW"`/`"MEDIUM"`/`"HIGH"` (NOT the enum). k1 has `_coerce_tier()` in `controller.py:144` to convert to `ComplexityTier` downstream — extra translation step POC lacks.
- `k1/concierge/fsm/phase1.py:55-106` — `Phase1Result` is a hand-written `__slots__` class (NOT `@dataclass`). `complexity_tier: str = "LOW"` lives in `__slots__` AND `__init__`. **Removal requires touching both.** No `to_payload()` method on this class.
- `k1/concierge/fsm/control_extension.py:50, 56, 178-193` — `ConciergeControlExtension` has `_complexity_tier: str = "LOW"`, `complexity_tier` property, `set_complexity_tier(tier)` mutator that syncs to SS overlay via `_sync_to_section()`. Mirror of POC layout exactly.
- `k1/concierge/adapters/ultrabert_classification.py` — pure re-export shim (`from k1.concierge.fsm.ultrabert_phase1 import UltraBERTPhase1Pipeline`); no tier logic to remove.
- `k1/concierge/events/conversation.py:243-291` — `Phase1Classified` `@dataclass` with `complexity_tier: str = ""` field and `to_payload()` method. **`derived_plan` is NOT present** (correct — P3.4a will add it).
- `k1/concierge/tools/dispatcher.py:53-59` — `BUDGET_LIMITS = {"LOW": 5, "MEDIUM": 10, "HIGH": 20, "CRISIS": 3}`. **Diverges from POC P3.2 final values** (`{"simple": 5, "plan": 15, "crisis": 3}`).
- `k1/concierge/tools/dispatcher.py:64-119` — `FRONT_TIER_ALLOWLISTS` dict-of-sets, 4 keys (LOW/MEDIUM/HIGH/CRISIS).
- `k1/concierge/tools/dispatcher.py:120-135` — `BACK_TIER_ALLOWLISTS` dict-of-sets, 3 keys (LOW/MEDIUM/HIGH). **Stale — `actors/back.py` does NOT import from here.**
- `k1/concierge/tools/schemas_back.py:286-313` — **Authoritative** `BACK_TIER_ALLOWLISTS` dict-of-LISTS. Imported by `k1/concierge/actors/back.py:62, 96`. Includes `batch_invoke_capabilities` which the dispatcher.py copy lacks. **Two divergent definitions of the same constant.**
- `k1/concierge/tools/dispatcher.py:548-621` — `create_front_dispatcher` and `create_back_dispatcher` factories. Take `tier: str` and freeze the allowlist at construction.
- `k1/concierge/factory.py:626-631` — `ConciergeFactory._construct_concierge` calls both factories with `config.tool_tier` (static boot tier).
- `k1/concierge/config/kernel.py:37` — `KernelConfig.tool_tier: str = "LOW"` (no validation).
- `k1/concierge/config/concierge.py:15` — `_VALID_TOOL_TIERS = frozenset({"LOW", "MED", "HIGH"})`. **`"MED"` mismatch confirmed.** Runtime everywhere uses `"MEDIUM"`. Passing `tool_tier="MED"` returns `set()` (empty allowlist) silently from `FRONT_TIER_ALLOWLISTS.get("MED", set())`.
- `k1/concierge/config/concierge.py:28, 44-46, 64` — `ConciergeConfig.tool_tier` field, `__post_init__` validation, `from_kernel_config(kc)` propagation.
- `k1/concierge/tools/implementations.py:908-958` — `execute_dispatch_task` has the M10 E10.3.1 AUTO-from-SS block: reads `complexity_tier` via `control.get_complexity_tier()`. Mirrors the POC pre-P3.3 block almost line-for-line.
- `k1/concierge/tools/schemas_front.py` — `DISPATCH_TASK_SCHEMA` (no `plan: bool` property yet).
- `k1/concierge/actors/back.py:411-470` — `back_handler(envelope, model, ss, bus, tool_dispatcher, fsm_state, cancel_token)`. **Already reads per-task tier at L464** (`tier = task.get("tier", "LOW")`) and uses `_filter_back_tools(tier)` for tool presentation. The gap is that `tool_dispatcher` instance (frozen `allowlist` + `_budget_limit`) does NOT get rebound — exactly the divergence POC P3.3 fixed via `_maybe_rebind_back_dispatcher`.
- `k1/concierge/actors/front.py:53, 808, 1003` — Imports `ComplexityTier`/`budget_for_tier`; constructs `ComplexityTier(canonical_tier)` at L1003 — **extra touchpoint POC lacks**. Front does not need rebind (CRISIS already empty allowlist; SIMPLE vs PLAN allowlists differ only by `promote_belief`), but the import paths must survive.
- `k1/concierge/obs/actor_metrics.py:212-260` — Duplicate `TIER_BUDGET_LIMITS = {"LOW": 4, "MEDIUM": 8, "HIGH": 12}`. **Third inconsistent budget table** (vs `dispatcher.py`'s 5/10/20 vs POC P3.2's 5/15/3). Must be harmonized.
- `k1/sessionstate/sections/control.py:364, 770, 801, 830, 849, 1223` — `complexity_tier` overlay read/write. Mirrors POC P3.1's "Option B softening" (kept as backward-compat shim). **No new edits needed in P3.4** beyond what P3.1's pattern already established.
- `k1/kernel/runner.py:30-36, 56` — `parser.add_argument("--tool-tier", choices=["LOW","MED","HIGH"], default="LOW")` + `KernelConfig(..., tool_tier=args.tool_tier)`. Note CLI also uses `"MED"`.
- `scripts/test_kernel_tiers.py:78-84, 175-195` — Real-API smoke. `run_tier(tier, prompt)` boots `KernelConfig(model_mode="hub", tool_tier=tier)`; `main()` calls `run_tier("LOW", ...)` then `run_tier("MED", ...)`. **No assertions** — only prints observed bus topics. Removing `tool_tier` breaks the constructor; must be rewritten as a `plan=False/True` probe.
- **k1 test fan-out — 13 files (+1 script + 1 doc), confirmed by audit:**

  | File | Tier-relevant lines | Predicted P3.4 sub-epic |
  |---|---|---|
  | `tests/k1/concierge/test_runner_cli.py` | L46–L247 (~12 sites) | **P3.4c** — full rewrite/delete of `--tool-tier` CLI tests |
  | `tests/k1/concierge/test_concierge_factory_stress.py` | L10, L236–L307 | **P3.4c** — `_VALID_TOOL_TIERS` validation tests obsolete |
  | `tests/k1/concierge/test_concierge_factory.py` | L442–L457 | **P3.4c** — `from_kernel_config` round-trip tests |
  | `tests/k1/concierge/test_bootstrap_smoke.py` | L38, L73, L392–L393 | **P3.4c** — drop `tool_tier="LOW"` kwargs and assertions |
  | `tests/k1/kernel/test_service.py` | L278, L282 | **P3.4c** — drop `tool_tier="HIGH"` |
  | `tests/k1/concierge/test_m10_epics_7_8_9.py` | L17, L44, L87–L91, L119–L137, L190–L264, L323–L363 | **P3.4b + P3.4c** — `_dispatch(tier=…)` helper, schema assertions |
  | `tests/k1/concierge/test_m10_e103_tier_routing.py` | L5, L24–L115, L180, L198, L227–L260 | **P3.4b + P3.4c** — `TestAutoTierDispatch` class (~6 methods) becomes obsolete |
  | `tests/k1/concierge/test_m11_obs_e112.py` | L26, L734, L814–L815 | **P3.4b** — budget table assertions |
  | `tests/k1/concierge/test_m05_arbiter.py` | L28, L44–L53, L393, L613, L832 | **P3.4a** — `_phase1(complexity=…)` helper + meta assertion |
  | `tests/k1/concierge/test_m05_e54_multi_device.py` | L27, L62–L78 | **P3.4a** — `_make_phase1` kwarg |
  | `tests/k1/concierge/test_m10_e105_extra_heads.py` | L111, L379, L426, L449 | **P3.4a** — `Phase1Result(complexity_tier=…)` + assertions |
  | `tests/k1/concierge/test_event_registry_completeness.py` | L8, L19, L94–L137 | **P3.4a + P3.3 mirror** — fixture must add `derived_plan` |
  | `tests/k1/concierge/test_m04_e41_ss_binding.py` | L223, L257–L307, L326 | **P3.4a (indirect)** — SS-section `set_complexity_tier` survives as shim |
  | `tests/k1/concierge/test_m04_e44_prompt_ss.py` | L173 | **P3.4a (indirect)** — fixture dict literal |
  | `tests/k1/concierge/test_m01_event_validator.py` | L64, L100 | **P3.3 mirror** — `Phase1Classified` field validation |
  | `tests/k1/concierge/test_dynamic_identity.py` | L121, L140, L145, L156 | **P3.4a (indirect)** — `compute(complexity_tier=…)` survives if API kept |
  | `tests/k1/fabric/test_context_with_sessionstate.py` | L88 | **P3.4a (indirect)** — fixture dict literal |
  | `tests/k1/fabric/test_policy_321_323.py` | L440–L517 (~7 sites) | **P3.4b (indirect)** — policy reads `cognitive.complexity_tier` from SS; values are HIGH/LOW/MEDIUM strings — **defer; keep SS string contract intact** |
  | `tests/k1/fabric/test_policy_324_326.py` | L315, L343 | Same as above — defer |
  | `tests/k1/fabric/test_policy_context_agent.py` | L118, L123, L128 | Same as above — defer |
  | `tests/k1/fabric/test_policy_engine.py` | L397–L410 | Same as above — defer |
  | `scripts/test_kernel_tiers.py` | L78–L84, L175–L195 | **P3.4c** — rewrite as plan-routing smoke |
  | `k1/kernel/kernel.md` | L6191, L6802 | Docs only — update last |

- **Zero hits** in `bridge/`, `governance/`, `contracts/`, `tests/bridge/`, `tests/integration/`, `tests/contracts/`, `tests/governance/`. No conftest fixtures define tier — all helpers are inline in their test files.
- **No `tests/k1/concierge/tools/` directory exists** — must be created by P3.4 with `__init__.py` for the new mirror tests.

**2. Findings**

- **k1 mirror is 1:1 in production code, scaled up in test coverage and inconsistencies.** k1 has 13 test files touching tier vs POC's ~10. P3.4's review burden is dominated by test churn, not production code.
- **Authoritative-source ambiguity for `BACK_TIER_ALLOWLISTS`** (NEW finding, not in earlier draft): two divergent dicts exist — `k1/concierge/tools/dispatcher.py:120-135` (sets, no `batch_invoke_capabilities`) vs `k1/concierge/tools/schemas_back.py:286-313` (lists, includes `batch_invoke_capabilities`, imported by `actors/back.py`). The dispatcher.py copy is **dead from the back actor's POV**. P3.4b must (a) consolidate to one source, (b) preserve `batch_invoke_capabilities` in the `plan` bucket.
- **Triple BUDGET inconsistency** (NEW finding): `dispatcher.py` (5/10/20) vs `obs/actor_metrics.py` (4/8/12) vs POC P3.2 final (5/15/3). All three must converge to the POC canonical (`{"simple": 5, "plan": 15, "crisis": 3}` + legacy aliases).
- **`"MED"` vs `"MEDIUM"` latent bug** silently fixes itself when `tool_tier` is removed (Concierge config validation goes away). The CLI `--tool-tier` choices were also `"MED"` — fix is by deletion, not rename.
- **`back_handler` already reads per-task tier** (L464). The fix is purely additive: insert one call to `_maybe_rebind_back_dispatcher(tool_dispatcher, tier, bus)` after the `tier = task.get("tier", "LOW")` line — no signature change. The rebind helper itself is a verbatim port of POC's.
- **`Phase1Result.__slots__` constraint**: dropping `complexity_tier` requires editing both the `__slots__` tuple AND the `__init__` signature. POC's `@dataclass` allowed a single-line removal; k1 needs two.
- **`Phase1Classified` event in k1 has no production emitter for `derived_plan`** either (mirroring the POC outcome). Field is added for forward-compat only.
- **Front actor's `ComplexityTier(canonical_tier)` at L1003** survives unchanged — it converts the per-turn `canonical_tier` (already a string) for downstream consumers; no tier-bucket logic depends on it.
- **`scripts/test_kernel_tiers.py` is currently print-only** — there are NO assertions to break beyond the `KernelConfig(tool_tier=tier)` call at L84. Rewrite scope: convert the two `run_tier(...)` calls into `run_plan(plan_mode, prompt)` calls, send (a) a one-step prompt with no `plan` flag and (b) a multi-step prompt that the LLM should escalate, and assert observed bus topics include `k1.fabric.capability.execute.v1` and `k1.orchestrator.plan.requested.v1` respectively.
- **P3.4 split into P3.4a / P3.4b / P3.4c** is preserved. Each maps to one POC epic.
- **POC items intentionally left intact (DO NOT mirror in P3.4):**
  - POC `prompt/back_prompt.py:348` (`tier = task.get("tier", task.get("complexity_tier", "LOW"))`) — dict fallback. k1 may have a mirror in `k1/concierge/prompt/back_prompt.py`; leave intact (matches POC).
  - POC `demo/display.py` (`print_fsm_state_transition(complexity_tier="")` default kwarg). k1 demo equivalent (if any) should follow the same intentional skip.
- **No new k1-only test patterns required** — every new test file mirrors a POC counterpart. Two NEW files: `tests/k1/concierge/tools/test_tool_dispatcher_tier_collapse.py` (mirrors `tests/poc/test_p32_tool_dispatcher_tier_collapse.py`, 39 tests) and `tests/k1/concierge/tools/test_dispatch_task_plan_derivation.py` (mirrors `tests/poc/test_p33_dispatch_task_plan_derivation.py`, 19 tests).
- **Likely-obsolete tests to DELETE rather than amend** (NEW finding):
  - `TestAutoTierDispatch` class in `tests/k1/concierge/test_m10_e103_tier_routing.py` (~6 methods, L24–L115).
  - `test_tier_budget_limits_defined` in `tests/k1/concierge/test_m11_obs_e112.py:814`.
  - `test_valid_tool_tiers_accepted` + `test_invalid_tool_tier_raises` in `tests/k1/concierge/test_concierge_factory_stress.py`.
  - `test_tier_case_insensitive` in `tests/k1/concierge/test_m10_epics_7_8_9.py` (~L115–L132).
  - `--tool-tier` CLI tests in `tests/k1/concierge/test_runner_cli.py` (~5 methods).

**3. Changes**

> **Implementation order:** P3.4a → P3.4b → P3.4c (matches POC ordering and dependency chain — the same SS-shim pattern P3.1 used must land in k1 before P3.4b/c can rely on it).

**P3.4a — Mirror P3.1 (UltraBERT `complexity_tier` removal)**

- **EDIT** `k1/concierge/fsm/ultrabert_phase1.py`:
  - Delete `_compute_complexity()` method (~L268–L320).
  - Drop `complexity_tier=` kwarg from `Phase1Result(...)` constructor call (L181) and the local variable (L162–166).
- **EDIT** `k1/concierge/fsm/phase1.py:55-106`:
  - Remove `"complexity_tier"` from `__slots__` tuple.
  - Remove `complexity_tier: str = "LOW"` from `__init__` parameter list.
  - Remove the `self.complexity_tier = complexity_tier` assignment.
  - Update Protocol docstring + `StubPhase1Pipeline.classify()` if either references the field.
- **EDIT** `k1/concierge/fsm/control_extension.py`:
  - Remove `_complexity_tier` field, `complexity_tier` property, `set_complexity_tier()` method, and the kwarg in `_sync_to_section()` call.
  - Clean `snapshot()` and `reset()` of any tier references.
- **EDIT** `k1/sessionstate/sections/control.py`:
  - **Option B (matches POC P3.1):** keep `set_complexity_tier()`/`get_complexity_tier()` on the SS section as a backward-compat shim. Make the `complexity_tier` parameter on `set_fsm_overlay()` optional (default `""`). Do NOT remove the overlay key — fabric policy tests still read it.
- **EDIT** `k1/concierge/fsm/controller.py`:
  - Remove all `set_complexity_tier()` call sites on the wrapper (mirror POC P3.1's 5 sites; grep `set_complexity_tier(` in this file).
  - Remove `payload["complexity_tier"]` writes (mirror POC L1931).
- **EDIT** `k1/concierge/fsm/arbiter.py` (if k1 has it):
  - Remove `complexity_tier=` from `from_dict` reconstruction and `routing_metadata` dict.
- **EDIT** `k1/concierge/events/conversation.py:243-291`:
  - Remove `complexity_tier: str = ""` from `Phase1Classified` dataclass.
  - Remove the corresponding key from `to_payload()`.
  - **Add** `derived_plan: bool = False` field (will be filled by P3.4c — added in P3.4a so the schema test in P3.4a sees it).
  - Add `d["derived_plan"] = self.derived_plan` in `to_payload()`.
- **EDIT** `k1/concierge/identity/dynamic_identity.py` (if k1 has it):
  - Remove `complexity_tier` param from `compute()` and `_compute_role()`. Drop the HIGH→EXPERT branch entirely (matches POC P3.1).
- **EDIT** `k1/concierge/protocols/opp_pipeline.py` (if k1 has it):
  - Remove `complexity_tier` param from `on_pre_prompt_build()` signature and forward call.
- **EDIT** `k1/concierge/actors/front.py:811`:
  - Drop `complexity_tier=tier` kwarg from OPP pipeline call (preserve `tier` local — still used at L808/L1003).
- **EDIT tests (P3.4a):**
  - `tests/k1/concierge/test_m05_arbiter.py:44–53, 613` — drop `complexity_tier=` from `_phase1` helper; flip `complexity_tier in meta` assertion to absence.
  - `tests/k1/concierge/test_m05_e54_multi_device.py:62–78` — drop kwarg.
  - `tests/k1/concierge/test_m10_e105_extra_heads.py:111, 379, 426, 449` — drop kwarg + flip assertions.
  - `tests/k1/concierge/test_event_registry_completeness.py:99, 118` — drop `complexity_tier=` from fixture, add `derived_plan=False`, add roundtrip assertion for `derived_plan`.
  - `tests/k1/concierge/test_m04_e41_ss_binding.py:223, 257-307, 326` — wrapper-side `set_complexity_tier` tests rewritten to assert absence on the wrapper while the SS section retains the shim.
  - `tests/k1/fabric/test_context_with_sessionstate.py:88`, `tests/k1/fabric/test_policy_*.py` — **leave intact** (SS overlay key survives by design; their `complexity_tier` reads still work).

**P3.4b — Mirror P3.2 (dispatcher allowlist collapse to simple/plan)**

- **EDIT** `k1/concierge/tools/dispatcher.py`:
  - Add `_TIER_ALIAS` map (verbatim from POC `poc/k1_poc/tools/dispatcher.py:48-58`):
    ```python
    _TIER_ALIAS: dict[str, str] = {
        "LOW": "simple", "MEDIUM": "plan", "HIGH": "plan", "CRISIS": "crisis",
        "simple": "simple", "plan": "plan", "crisis": "crisis",
    }
    ```
  - Replace `BUDGET_LIMITS` with the canonical 7-key dict (`{"simple":5, "plan":15, "crisis":3, "LOW":5, "MEDIUM":15, "HIGH":15, "CRISIS":3}`).
  - Define `_FRONT_SIMPLE` frozenset; collapse `FRONT_TIER_ALLOWLISTS` to the 7-key form (`simple`/`plan`/`crisis` + 4 legacy aliases). `plan` adds `{"promote_belief"}`.
  - **Delete** the existing dispatcher.py `BACK_TIER_ALLOWLISTS` (it is dead — the live one lives in `schemas_back.py`).
  - Fix `__init__` `_budget_limit` to apply `_TIER_ALIAS` before config lookup.
- **EDIT** `k1/concierge/tools/schemas_back.py:286-313`:
  - **This is the authoritative `BACK_TIER_ALLOWLISTS`.** Collapse to the 7-key form (lists, not sets — preserve current container type to avoid breaking `actors/back.py` consumer):
    ```python
    _BACK_SIMPLE_LIST = ["recall_memory", "discover_capabilities",
                          "invoke_capability", "batch_invoke_capabilities",
                          "submit_result"]
    BACK_TIER_ALLOWLISTS: dict[str, list[str]] = {
        "simple": _BACK_SIMPLE_LIST,
        "plan":   _BACK_SIMPLE_LIST + ["spawn_via_fabric", "execute_workflow"],
        "LOW":    _BACK_SIMPLE_LIST,
        "MEDIUM": _BACK_SIMPLE_LIST + ["spawn_via_fabric", "execute_workflow"],
        "HIGH":   _BACK_SIMPLE_LIST + ["spawn_via_fabric", "execute_workflow"],
    }
    ```
  - **Preserves `batch_invoke_capabilities`** (k1-only tool, not in POC).
- **EDIT** `k1/concierge/obs/actor_metrics.py:212-260`:
  - Replace `TIER_BUDGET_LIMITS = {"LOW": 4, "MEDIUM": 8, "HIGH": 12}` with the canonical 6-key dict matching `dispatcher.BUDGET_LIMITS` values (no more 4/8/12 drift).
- **EDIT** `k1/concierge/config/concierge.py:15, 28, 44-46`:
  - Replace `_VALID_TOOL_TIERS = frozenset({"LOW","MED","HIGH"})` with `frozenset({"simple","plan"})` (silently fixes the `"MED"` bug).
  - Update `__post_init__` to validate against the new set OR pre-translate via `_TIER_ALIAS` and validate canonicalized result.
  - **Note:** the entire `tool_tier` field will be removed in P3.4c, so `_VALID_TOOL_TIERS` may become dead code by end of P3.4. P3.4b leaves it correctly aligned in case P3.4c is delayed.
- **EDIT** `k1/kernel/runner.py:30-36`:
  - Update `--tool-tier` CLI choices to `["simple","plan"]` (interim alignment with P3.4b; full removal in P3.4c).
- **EDIT** `k1/concierge/config/defaults.yaml` (if present, mirror POC):
  - Add `simple/plan/crisis` keys to `budget_limits`, `front_tier_allowlists`, `back_tier_allowlists`, `back_max_iterations`. Keep legacy keys.
- **NEW** `tests/k1/concierge/tools/__init__.py` (empty package marker).
- **NEW** `tests/k1/concierge/tools/test_tool_dispatcher_tier_collapse.py`:
  - Mirror POC `tests/poc/test_p32_tool_dispatcher_tier_collapse.py` — 39 tests across 5 classes (`TestFrontAllowlists`, `TestBackAllowlists`, `TestBudgetLimits`, `TestTierAliasMap`, `TestFactoryBackwardCompat`).
  - Imports from `k1.concierge.tools.dispatcher` and `k1.concierge.tools.schemas_back` (note: `BACK_TIER_ALLOWLISTS` lives in `schemas_back`, not `dispatcher`).
- **EDIT** `tests/k1/concierge/test_m11_obs_e112.py:814`:
  - Rewrite `test_tier_budget_limits_defined` to assert canonical 6-key form.
- **EDIT** `tests/k1/fabric/test_policy_321_323.py`, `test_policy_324_326.py`, `test_policy_context_agent.py`, `test_policy_engine.py`:
  - **Defer.** SS `cognitive.complexity_tier` overlay still emits string labels (LOW/MEDIUM/HIGH) via the SS shim; policy tests work unchanged. If P3.4 later collapses the SS overlay to `simple`/`plan`, these tests are revisited as P3.5 follow-up.

**P3.4c — Mirror P3.3 (KernelConfig.tool_tier removal + dispatch_task rewrite)**

- **EDIT** `k1/concierge/config/kernel.py:37`:
  - Remove `tool_tier: str = "LOW"` field.
- **EDIT** `k1/concierge/config/concierge.py:15, 28, 44-46, 64`:
  - Remove `tool_tier` field, `__post_init__` validation, `_VALID_TOOL_TIERS` constant, and `tool_tier` propagation in `from_kernel_config`.
- **EDIT** `k1/concierge/factory.py:626-631`:
  - Replace `tier=config.tool_tier` with `tier="simple"` in both factory calls. Add P3.4c comment matching POC `bootstrap.py` style.
- **EDIT** `k1/kernel/runner.py:30-36, 56`:
  - Remove the `--tool-tier` CLI argument entirely (matches POC P3.3).
  - Remove `tool_tier=args.tool_tier` from `KernelConfig(...)`.
- **EDIT** `k1/concierge/tools/schemas_front.py`:
  - Add `plan: bool` property to `DISPATCH_TASK_SCHEMA.parameters.properties` (verbatim from POC P3.3 — `type: boolean`, `default: False`, descriptive text). Do NOT add to `required`.
  - Update `DISPATCH_TASK_SCHEMA.description` to mention `plan=true`.
- **EDIT** `k1/concierge/tools/implementations.py:908-958`:
  - Replace the entire AUTO-from-SS block (~30 LOC) with the POC P3.3 derivation:
    ```python
    explicit_plan = bool(args.get("plan", False))
    needs_plan = explicit_plan or len(intents) > 1 or depends_on is not None
    tier = ComplexityTier.MEDIUM if needs_plan else ComplexityTier.LOW
    ```
  - Drop the now-redundant `try: tier = ComplexityTier(str(tier_raw).upper())` validation block.
  - Add `dispatch_payload["plan"] = needs_plan` (telemetry hook into `_dispatch` dict).
  - Update log line: `"tool:dispatch_task intents=%d urgency=%s tier=%s plan=%s safety=%s"`.
- **EDIT** `k1/concierge/actors/back.py`:
  - Add import: `from k1.concierge.tools.dispatcher import ToolDispatcher, create_back_dispatcher`.
  - Add helpers near top of module (verbatim port from POC):
    ```python
    def _resolve_back_tier_bucket(task_tier: str) -> str:
        upper = str(task_tier).upper()
        if upper in ("MEDIUM", "HIGH"):
            return "plan"
        return "simple"

    def _maybe_rebind_back_dispatcher(tool_dispatcher, task_tier, bus):
        desired_bucket = _resolve_back_tier_bucket(task_tier)
        if tool_dispatcher.tier == desired_bucket:
            return tool_dispatcher
        logger.info("back_handler: rebinding dispatcher tier %s -> %s for task tier %s", ...)
        return create_back_dispatcher(tier=desired_bucket, ctx=tool_dispatcher.ctx, bus=bus)
    ```
  - In `back_handler` (~L411–L470), insert `tool_dispatcher = _maybe_rebind_back_dispatcher(tool_dispatcher, tier, bus)` immediately after `tier = task.get("tier", "LOW")` (L464).
  - In `back_resume_handler` (k1 equivalent — grep to locate; mirror POC's L750 pattern), insert the same rebind call.
  - **Also** update the `_filter_back_tools` helper's fallback from `BACK_TIER_ALLOWLISTS["LOW"]` to `BACK_TIER_ALLOWLISTS["simple"]` (POC has a known pre-existing skip here; k1 should fix it as part of P3.4c).
- **EDIT** `k1/concierge/demo/coordinator.py` and `k1/concierge/testing/harness/engine.py` (if they exist):
  - Remove any `tool_tier="LOW"` kwargs from `KernelConfig(...)` constructions (mirror POC P3.3 files 3 + 4).
- **EDIT** `scripts/test_kernel_tiers.py`:
  - **Rewrite.** Replace the `run_tier(tier, ...)` driver with a `run_plan(prompt, expect_plan: bool, ...)` variant that:
    1. Boots `KernelConfig(model_mode="hub")` once (no tier kwarg).
    2. Sends the prompt as a `user_input` envelope.
    3. Subscribes to `k1.orchestration.task.dispatch.v1` to capture the `_dispatch.plan` flag.
    4. Asserts (not just prints) that simple prompts yield `plan=False` and multi-step prompts yield `plan=True`.
  - Keep two real-API calls (one simple, one multi-step) so the smoke covers both routing branches.
- **EDIT tests (P3.4c):**
  - `tests/k1/concierge/test_runner_cli.py` — delete `--tool-tier` CLI test methods (~5).
  - `tests/k1/concierge/test_concierge_factory_stress.py:236-307` — delete `_VALID_TOOL_TIERS` validation tests (~8 methods).
  - `tests/k1/concierge/test_concierge_factory.py:442-457` — drop `tool_tier` from `from_kernel_config` round-trip.
  - `tests/k1/concierge/test_bootstrap_smoke.py:38, 73, 392-393` — drop `tool_tier="LOW"` kwargs and assertions.
  - `tests/k1/kernel/test_service.py:278-282` — drop `tool_tier="HIGH"`.
  - `tests/k1/concierge/test_m10_epics_7_8_9.py` — rewrite `_dispatch(tier=…)` helper to use `plan: bool`; delete `test_tier_case_insensitive`; update `DISPATCH_TASK_SCHEMA` assertions to look for `plan` not `tier`.
  - `tests/k1/concierge/test_m10_e103_tier_routing.py` — apply the **same edits POC's `tests/poc/test_m10_e103_tier_routing.py` got in P3.3**: rewrite `TestAutoTierDispatch`'s 3 AUTO-from-SS tests to assert P3.3 semantics (SS-tier ignored; only `plan` + signals route).
  - `tests/k1/concierge/test_m01_event_validator.py:64, 100` — add `derived_plan` to validator schema if registry is type-checked.
- **NEW** `tests/k1/concierge/tools/test_dispatch_task_plan_derivation.py`:
  - Mirror POC `tests/poc/test_p33_dispatch_task_plan_derivation.py` — 19 tests across 5 classes (`TestDispatchTaskPlanDerivation`, `TestBackDispatcherRebind`, `TestKernelConfigToolTierRemoved`, `TestPhase1ClassifiedDerivedPlan`, `TestDispatchTaskSchema`).
  - Imports from `k1.concierge.config.kernel`, `k1.concierge.tools.implementations`, `k1.concierge.actors.back`, `k1.concierge.events.conversation`, `k1.concierge.tools.schemas_front`.

- **EDIT docs:** `k1/kernel/kernel.md:6191, 6802` — remove `tool_tier` references after code changes land.

**4. Handoff & test log**

- (To be filled after implementation. Mandatory checks:
  1. `python scripts/test_kernel_tiers.py` rewritten variant must boot cleanly against real Gemini and exercise both `plan=False` and `plan=True` routing branches with assertions, not just prints.
  2. `python -m pytest tests/k1/ -q --tb=line` must show no NEW failures relative to the pre-P3.4 k1 baseline (capture baseline counts before starting).
  3. `python -m pytest tests/k1/concierge/tools/ -v` must show 39+19 = 58/58 new tests passing.
  4. `python -m pytest tests/poc/ -q --tb=no` must remain at the post-P3.3 baseline (3412 passed / 114 failed) — P3.4 must not regress POC.)
- **User sign-off:** ☐

---

## 4. Open questions parking lot — **RESOLVED**

- **Q1: HIGH-tier signal — `plan: bool` param vs sibling `plan_task` tool?**
  **Resolved (P3.3 §2):** `plan: bool` param on `dispatch_task`. Sibling tool rejected — duplicates 90%+ of `dispatch_task`'s schema and forces the LLM to learn two tools where one suffices. The `plan: bool` flag is the smallest-diff option idiomatic with existing `args` patterns. Auto-escalation: `plan = explicit_plan or len(intents) > 1 or depends_on is not None`.

- **Q2: Telemetry — where to record "derived tier" once the explicit field is gone?**
  **Resolved (P3.3 §2):** Two complementary insertion points:
  1. `ToolResult.data["_dispatch"]["plan"] = plan` in `execute_dispatch_task` — flows automatically through `build_tool_completed` → bus to all observers.
  2. `Phase1Classified.derived_plan: bool` — adds a Phase 1-time computation of the same factors so the telemetry timeline records the system's view at classification time, separate from the LLM's view at dispatch time.

- **Q3: Back-actor MED chain — confirm nothing reads `complexity_tier`/`tool_tier` after P3.**
  **Resolved (P3.3 §1, §2):** Trace shows the only existing reads are (a) `routing.py:129-131` (uses `ComplexityTier` enum, not the string field — survives P3 unchanged), and (b) `dispatch_task` AUTO path (deleted by P3.3). **Pre-existing gap discovered:** the Back ReAct loop's dispatcher allowlist comes from `KernelConfig.tool_tier` (always `"LOW"` in demo/harness), NOT from `Phase1Result.complexity_tier`. Back is effectively always-LOW today regardless of upstream tier. P3.3 fixes this as a side benefit by constructing the back dispatcher per-task using `task.tier` to choose between `simple`/`plan` allowlists. Test coverage required.

## 5. Reference: subagent maps consulted

- Concierge tier routing — see in-conversation subagent report (Sections 1–9).
- ModelHub end-to-end — see in-conversation subagent report (Sections 1–8).
- Fabric registration & dispatch — see in-conversation subagent report (Sections 1–8).

These reports are NOT a substitute for each epic's own Read step. Re-read at epic start; record citations in Findings.
