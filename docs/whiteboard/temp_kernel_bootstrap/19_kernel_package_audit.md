# 19 — Epic 1.10: Kernel Package Audit

> Generated from subagent code reads across `k1/kernel/` and `k1/concierge/kernel/`.
> Two "kernel" packages exist — `k1/kernel/` is **100% stubs** (dead code), while `k1/concierge/kernel/` is the **real composition root**.

---

## Summary Verdict

| Issue | What To Check | Verdict |
| ----- | ------------- | ------- |
| 1.10.1 | Read k1/kernel/ — loader.py, hot_reload.py — stubs? | ✅ **ALL STUBS** — `ModuleLoader` (19 LOC, all `pass`), `HotReloadEngine` (12 LOC, all `pass`). Zero imports from anywhere in codebase |
| 1.10.2 | Read registries — agent, prompt, tool — stubs? | ✅ **ALL STUBS** — 3 minimal dict wrappers (11-15 LOC each). No types, no validation, no versioning, no hot-reload |
| 1.10.3 | Read runner.py, chat_repl.py — how is kernel started today? | ✅ Both REAL. `runner.py` (76 LOC, argparse + signals), `chat_repl.py` (225 LOC, sys.argv + model swap). Both call `start_kernel()` from bootstrap.py |

---

## The Two Kernel Packages

| Package | Status | LOC | Purpose |
| ------- | ------ | --- | ------- |
| `k1/kernel/` | **100% STUBS** | ~69 total | Planned top-level kernel — loader, hot-reload, registries. Zero working code |
| `k1/concierge/kernel/` | **100% REAL** | ~1,201 total | Actual composition root — bootstrap.py (900), runner.py (76), chat_repl.py (225) |

**Nothing in the codebase imports from `k1.kernel`.**

---

## k1/kernel/ — Directory Structure

```
k1/kernel/
├── __init__.py           (1 LOC — comment only)
├── loader.py             (19 LOC — STUB)
├── hot_reload.py         (12 LOC — STUB)
├── kernel.md             (~200 LOC — planning doc, "Status: PLANNING")
└── registries/
    ├── __init__.py        (1 LOC — comment only)
    ├── agent_registry.py  (11 LOC — STUB)
    ├── prompt_registry.py (11 LOC — STUB)
    └── tool_registry.py   (15 LOC — STUB)
```

**No `ports/` or `adapters/` subdirectories.** No hexagonal infrastructure at all.

---

## Issue 1.10.1 — Loader & Hot-Reload (STUBS)

### `ModuleLoader` (19 LOC) — STUB

```python
class ModuleLoader:
    def __init__(self, modules_path, registries):
        self.modules_path = modules_path
        self.registries = registries

    async def scan_and_load(self):
        pass  # intended to scan k1/modules/*/module.yaml

    async def hot_reload(self):
        pass
```

**Purpose:** Scan `k1/modules/*/module.yaml` and install tools/prompts/agents into registries. Entirely unimplemented. No type hints, no cross-module imports.

### `HotReloadEngine` (12 LOC) — STUB

```python
class HotReloadEngine:
    def __init__(self, loader):
        self.loader = loader

    async def start_watching(self):
        pass  # intended as file watcher for dev mode
```

Entirely unimplemented. No type hints, no imports (not even `ModuleLoader`).

---

## Issue 1.10.2 — Registries (ALL STUBS)

### `AgentRegistry` (11 LOC)

| Method | Signature | Implementation |
| ------ | --------- | -------------- |
| `__init__` | `(self)` | `self.templates = {}` |
| `register_template` | `(self, template_name, template_yaml)` | Dict insert |
| `get_template` | `(self, template_name)` | Dict get, returns `None` on miss |

No type hints, no validation, no deregistration, no events.

### `PromptRegistry` (11 LOC)

| Method | Signature | Implementation |
| ------ | --------- | -------------- |
| `__init__` | `(self)` | `self.prompts = {}` |
| `register_prompt` | `(self, prompt_name, content)` | Dict insert |
| `get_prompt` | `(self, prompt_name)` | Dict get |

No type hints, no validation, no versioning.

### `ToolRegistry` (15 LOC)

| Method | Signature | Implementation |
| ------ | --------- | -------------- |
| `__init__` | `(self)` | `self.tools = {}` |
| `register_tool` | `(self, tool_name, tool_contract, impl)` | Stores `{"contract": ..., "impl": ...}` |
| `get_tool` | `(self, tool_name)` | Dict get |
| `list_tools` | `(self)` | `list(self.tools.keys())` |

Comment says "versions" but no version tracking exists.

### Registry Summary

| Registry | Data Structure | Type Hints | Validation | Versioning | Hot-Reload | Deregister |
| -------- | -------------- | ---------- | ---------- | ---------- | ---------- | ---------- |
| Agent | `dict` | No | No | No | No | No |
| Prompt | `dict` | No | No | No | No | No |
| Tool | `dict` of `{contract, impl}` | No | No | No | No | No |

---

## Issue 1.10.3 — Runner & Chat REPL (REAL)

### `runner.py` (76 LOC) — Headless Daemon

**Entry:** `python -m k1.concierge.kernel.runner`

**CLI Arguments (argparse):**

| Argument | Type | Default | Choices |
| -------- | ---- | ------- | ------- |
| `--test-mode` | flag | `False` | — |
| `--unordered` | flag | `False` | — |
| `--session-mode` | choice | `"standalone"` | `standalone`, `testing` |
| `--tool-tier` | choice | `"LOW"` | `LOW`, `MEDIUM`, `HIGH`, `CRISIS` |
| `--log-level` | choice | `"INFO"` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

**Flow:** Parse args → build `KernelConfig` → `await start_kernel(cfg)` → print "Kernel started" → wait on `asyncio.Event` → `finally: await stop_kernel(runtime)`.

**Shutdown:** Registers `SIGINT` + `SIGTERM` handlers that set the stop event.

### `chat_repl.py` (225 LOC) — Interactive REPL

**Entry:** `python -m k1.concierge.kernel.chat_repl`

**CLI Arguments (manual `sys.argv`, NOT argparse):**

| Argument | Effect |
| -------- | ------ |
| `--model-hub` | Production ModelHub + GooglePlugin |
| `--no-test-mode` | Legacy POC bridge (GeminiConciergeAdapter) |
| `--log-level=LEVEL` | Set logging level |
| *(default)* | `TestModelHubBridge` (canned responses) |

**Model Swap Behavior:**
1. Always boots with `test_mode=True`
2. Post-boot swaps `runtime.model` with requested adapter
3. Both `--model-hub` and `--no-test-mode` require `GOOGLE_API_KEY` env var

**Interactive Loop:**
- Publishes user input to bus → subscribes to `TOPIC_FINAL_RESPONSE` + `TOPIC_RESPONSE_STREAM`
- Shows streaming chunks in real-time, 30s timeout for final response
- Displays FSM state after each turn
- Exit on `quit`/`exit`/`q`/Ctrl+C/EOF

**Shutdown:** `try/finally` → unsubscribe bus handlers → `await stop_kernel(runtime)`. No signal handlers.

---

## End-to-End Kernel Startup Flow

```
runner.py (or chat_repl.py)
  │
  ├─ Parse CLI args
  ├─ Build KernelConfig
  │
  └─ await start_kernel(cfg)                    [bootstrap.py, ~900 LOC]
       │
       ├─ poc.k1_poc.main.boot()               → bus, router, adapter, mailboxes  ⚠️ POC dep
       ├─ _create_model(cfg)                    → TestModelHubBridge | Gemini
       ├─ _create_session_state(cfg)            → SessionStateFactory
       ├─ _create_capability_registry()         → demo registry (40 POC caps)
       ├─ _create_fabric(registry)              → FabricFactory (test adapters + POC bridge)
       ├─ LedgerWriter + InMemoryLedgerStore
       ├─ ConciergeController(bus, router)      → FSM + UltraBERT Phase 1
       ├─ Tool dispatchers (front + back)
       ├─ Build KernelRuntime dataclass (24+ fields)
       ├─ ExperienceLayer, DeltaAggregator, HILCoordinator
       ├─ WeaveBatcher + WeavePolicy + UserActivityTracker
       ├─ DeadLetterConsumer
       ├─ OrchestratorStub (with 3 private adapters)
       ├─ Front event subscriptions
       └─ asyncio.create_task(_mailbox_consumer)
```

### `stop_kernel()` Teardown

1. Cancel consumer task
2. Flush ledger, log dead-letter summary
3. Flush delta aggregator
4. `fsm.teardown()`
5. `session_state.close()`
6. `model.close()`
7. Set `runtime.started = False`

---

## `kernel.md` — Planning Document

**Status:** `PLANNING -- fill as implementation proceeds`

Contains the K1 Kernel Wiring Specification:
- Full dependency graph for 7 managed components (Bus, Fabric, SessionState, Orchestrator, Planner, ModelHub, Concierge)
- Port wiring matrix (~42 ports)
- This is the **target architecture**, not current implementation

---

## Cross-Module Import Map

| Source | Imports From |
| ------ | ------------ |
| `k1/kernel/*` | **NOTHING** — zero cross-module imports |
| `runner.py` | `k1.concierge.kernel.bootstrap.{KernelConfig, start_kernel, stop_kernel}` |
| `chat_repl.py` | `bootstrap.*`, `k1.concierge.bus.{builders, topics}`, lazy: `k1.model_hub.factory`, `k1.model_hub.plugins.google_plugin`, `k1.concierge.llm.*` |
| `bootstrap.py` | 20+ internal imports + **`poc.k1_poc.main.boot`** (critical POC dependency) |

---

## STUB vs REAL Classification

| File | Classification | LOC |
| ---- | -------------- | --- |
| `k1/kernel/__init__.py` | **STUB** | 1 |
| `k1/kernel/loader.py` | **STUB** | 19 |
| `k1/kernel/hot_reload.py` | **STUB** | 12 |
| `k1/kernel/kernel.md` | **PLANNING DOC** | ~200 |
| `k1/kernel/registries/__init__.py` | **STUB** | 1 |
| `k1/kernel/registries/agent_registry.py` | **STUB** | 11 |
| `k1/kernel/registries/prompt_registry.py` | **STUB** | 11 |
| `k1/kernel/registries/tool_registry.py` | **STUB** | 15 |
| `k1/concierge/kernel/__init__.py` | **REAL** | 5 |
| `k1/concierge/kernel/bootstrap.py` | **REAL** | ~900 |
| `k1/concierge/kernel/runner.py` | **REAL** | 76 |
| `k1/concierge/kernel/chat_repl.py` | **REAL** | ~225 |

---

## Anomalies & Risks

| # | Anomaly | Severity | Impact |
| -- | ------- | -------- | ------ |
| 1 | **Two "kernel" packages** — `k1/kernel/` (dead) vs `k1/concierge/kernel/` (real) | **HIGH** | Confusing. Real kernel lives inside Concierge, not at top level |
| 2 | **`k1/kernel/` is 100% dead code** — nothing imports from it | **HIGH** | 69 LOC of stubs that could mislead developers |
| 3 | **`bootstrap.py` imports `poc.k1_poc.main.boot()`** | **HIGH** | Production composition root depends on POC layer for bus infrastructure |
| 4 | **`chat_repl.py` mutates `runtime.model` post-boot** | **MEDIUM** | FSM/actors briefly reference test model before swap |
| 5 | **`chat_repl.py` uses `sys.argv` manually** vs `runner.py` uses argparse | **LOW** | Inconsistent CLI parsing |
| 6 | **Registries have no type hints** | **LOW** | Every parameter untyped, every method unguarded |
| 7 | **ToolRegistry comment says "versions" but no versioning exists** | **LOW** | Misleading comment |
| 8 | **`tool_tier` mismatch** — runner offers `MEDIUM`/`CRISIS`, ConciergeConfig validates `{"LOW","MED","HIGH"}` | **MEDIUM** | (Already flagged in Epic 1.7) |

---

## Key Insight

The planned architecture (kernel.md) envisions `k1/kernel/` as the top-level kernel owning Bus, Fabric, SessionState, Orchestrator, Planner, ModelHub, and Concierge as 7 peer components. **Today the kernel is embedded inside Concierge** and wires everything from that vantage point via `bootstrap.py`. MS-2 (KernelService) will need to:

1. Move the composition root from `k1/concierge/kernel/bootstrap.py` → `k1/kernel/service.py`
2. Eliminate the `poc.k1_poc.main.boot()` dependency
3. Implement the registries (or decide they're not needed)
4. Decide whether loader + hot-reload are MS-2 or MS-4 scope
