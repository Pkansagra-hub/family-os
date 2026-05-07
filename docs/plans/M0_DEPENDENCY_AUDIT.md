# M0 E0.2 — Dependency Audit Report

**Date**: 2026-03-30
**Files scanned**: 310
**Folders with imports**: 26

---

## 1. Folder-to-Folder Import Matrix

| Source Folder | Imports From |
|---|---|
| `(root)` | bus |
| `actors` | bus, config, llm, prompt, protocols, react, task, tools |
| `bus` | config, events |
| `delta` | config |
| `demo` | actors, bus, config, delta, experience, fabric, fsm, kernel, llm, main, orchestrator, prompt, protocols, sessionstate, tools |
| `experience` | config |
| `fsm` | bus, config, events, ledger, llm, orchestrator, protocols, sessionstate, task |
| `kernel` | actors, bus, config, delta, experience, fabric, fsm, ledger, llm, main, orchestrator, protocols, sessionstate, tools |
| `ledger` | events, protocols |
| `llm` | config |
| `obs` | bus |
| `orchestrator` | config, task |
| `prompt` | bus, config, llm, sessionstate |
| `protocols` | config, events, fsm, ledger, prompt, sessionstate, task |
| `react` | config, llm, task, tools |
| `sessionstate` | config |
| `task` | bus, config |
| `testing` | actors, bus, compression, delta, events, fsm, identity, kernel, ledger, prompt, protocols, scheduler, sessionstate, tools |
| `tools` | bus, config, llm, sessionstate, task |

**Leaf folders** (no outgoing internal imports): `compression`, `config`, `events`, `fabric`, `identity`, `main`, `scheduler`

## 2. Circular Dependency Check

⚠️ **2 circular dependency chains found** (runtime-safe, not import-time errors):

1. `protocols` → `fsm` → `ledger` → `protocols`
2. `protocols` → `fsm` → `protocols`

**Cycle 1 details** (`protocols` ↔ `fsm`):
- `protocols → fsm`: `hitl_wiring.py` imports `ConversationArbiter`, `InflightContext`; `opp_pipeline.py` imports `is_short_input`; `weave_policy.py`/`weave_state.py` import `ConciergeState`
- `fsm → protocols`: `controller.py` imports `CancellationHandler`, `CancellationToken`, `HILSubTask`, `SuspensionManager`, `WeavePolicy`, etc.

**Cycle 2 details** (`protocols` → `ledger` → `protocols`):
- `protocols → ledger`: `cancel_handler.py`, `hitl_coordinator.py`, `suspension_manager.py` import `LedgerEntry`, `LedgerWriter`, projections
- `ledger → protocols`: `projections.py`, `recovery.py` import `TaskStateEntry`, `TaskStatus` from `hitl_persistence`

**Classification**: `pre-existing` — these are architectural tangles (protocols and fsm are tightly coupled by design). Python resolves them at module load time without error. **Not a migration blocker** — the Big Copy (M5) preserves the same structure.

### Hub Analysis

| Folder | Outgoing Imports | Incoming Imports |
|---|---|---|
| `(root)` | 1 | 0 |
| `actors` | 8 | 3 |
| `bus` | 2 | 10 |
| `compression` | 0 | 1 |
| `config` | 0 | 15 |
| `delta` | 1 | 3 |
| `demo` | 15 | 0 | ⭐ HUB
| `events` | 0 | 5 |
| `experience` | 1 | 2 |
| `fabric` | 0 | 2 |
| `fsm` | 9 | 4 |
| `identity` | 0 | 1 |
| `kernel` | 14 | 2 | ⭐ HUB
| `ledger` | 2 | 4 |
| `llm` | 1 | 7 |
| `main` | 0 | 2 |
| `obs` | 1 | 0 |
| `orchestrator` | 2 | 3 |
| `prompt` | 4 | 4 |
| `protocols` | 7 | 6 |
| `react` | 4 | 1 |
| `scheduler` | 0 | 1 |
| `sessionstate` | 1 | 7 |
| `task` | 2 | 6 |
| `testing` | 14 | 0 | ⭐ HUB
| `tools` | 5 | 5 |

## 3. K1 Framework Imports (`k1.*`)

These imports reference `k1.*` packages (Bus, Fabric, etc.) that will NOT change path during the Big Copy (M5).

**Total unique k1.\* modules imported**: 7

### 3a. Unique k1.* Modules

- `k1.bus.adapters.session_adapter`
- `k1.bus.envelope`
- `k1.bus.factory`
- `k1.bus.impl.local_bus`
- `k1.bus.impl.local_mailbox`
- `k1.bus.ports.bus`
- `k1.bus.ports.mailbox`

### 3b. Files Importing k1.* (by folder)

| File | k1.* Imports |
|---|---|
| `actors/back.py` | `k1.bus.envelope`, `k1.bus.ports.bus` |
| `actors/front.py` | `k1.bus.envelope`, `k1.bus.ports.bus` |
| `actors/shared.py` | `k1.bus.envelope` |
| `bus/builders.py` | `k1.bus.envelope` |
| `bus/setup.py` | `k1.bus.adapters.session_adapter`, `k1.bus.factory`, `k1.bus.impl.local_bus`, `k1.bus.impl.local_mailbox`, `k1.bus.ports.mailbox` |
| `demo/iot_stubs.py` | `k1.bus.ports.bus` |
| `demo/output_channel.py` | `k1.bus.envelope`, `k1.bus.ports.bus` |
| `demo/spinner.py` | `k1.bus.envelope`, `k1.bus.ports.bus` |
| `demo/web/app.py` | `k1.bus.envelope` |
| `fsm/controller.py` | `k1.bus.envelope`, `k1.bus.ports.bus`, `k1.bus.ports.mailbox` |
| `fsm/dead_letter_consumer.py` | `k1.bus.envelope`, `k1.bus.ports.bus` |
| `fsm/front_lock.py` | `k1.bus.envelope` |
| `fsm/turn_state.py` | `k1.bus.envelope` |
| `kernel/bootstrap.py` | `k1.bus.envelope` |
| `main.py` | `k1.bus.factory` |
| `testing/harness/engine.py` | `k1.bus.envelope` |

### 3c. Plan vs Reality — k1.* Import Diff

The migration plan (E0.2.3) listed 9 k1.* imports. Our scan found 7. Diff:

| Module | Plan | Actual | Status |
|---|---|---|---|
| `k1.bus.envelope` | ✅ | ✅ | Match |
| `k1.bus.factory` | ✅ | ✅ | Match |
| `k1.bus.impl.local_bus` | ✅ | ✅ | Match |
| `k1.bus.impl.local_mailbox` | ✅ | ✅ | Match |
| `k1.bus.ports.bus` | ✅ | ✅ | Match |
| `k1.bus.ports.mailbox` | ✅ | ✅ | Match |
| `k1.bus.adapters.session_adapter` | Listed as `k1.bus.adapters` | ✅ (more specific) | Match (refined) |
| `k1.bus.timing.defaults` | ✅ | ❌ NOT FOUND | **Plan error** |
| `k1.bus.timing.timing_chain` | ✅ | ❌ NOT FOUND | **Plan error** |

**Note**: `k1.bus.timing.*` modules are NOT imported anywhere in poc/k1_poc/. The plan's E0.2.3 should drop these 2 phantom entries.

### 3d. DEPENDENCY_MAP.md Status

The plan references `poc/k1_poc/docs/DEPENDENCY_MAP.md` (dated 2026-02-23) for diffing. **This file does not exist in the repository.** This audit serves as the first and authoritative dependency map.

## 4. Summary

| Metric | Value |
|---|---|
| Python files scanned | 310 |
| Unique folders | 26 |
| Folder-to-folder edges | 94 |
| Circular dependencies | 2 |
| Unique k1.* modules | 7 |
| Files importing k1.* | 16 |
