# Production Readiness Plan — K1 System

Skeleton plan covering all known open issues across every K1 component.
Organized as Milestones → Epics → Issues.

**Status of each item:** `[ ]` = not started · `[~]` = in analysis · `[x]` = done

**Rule:** Before coding any issue, do an end-to-end analysis pass on that epic to
confirm the fix is not already partially present elsewhere and to identify cross-cutting
dependencies. Record findings in the issue's Analysis Notes section when filled in.

---

## How to read this plan

- **Milestone** = a shippable system capability level
- **Epic** = a cohesive group of fixes within one component or cross-cutting concern
- **Issue** = one specific fix, keyed back to the OPEN_ISSUES.md entry (e.g. SS-02, K1, Fabric#5)

Fill in Analysis Notes and Implementation Notes per issue when work begins.
Do not start coding until analysis is signed off.

---

## Milestone 1 — Kernel Boots for Chat

*Goal: a single session starts, user sends a message, Concierge processes it, LLM responds.*
*No K0 memory, no multi-step tasks, no planning required.*

> **Deep-dive status:** Code fully traced. All four epics verified against source.
> Findings differ from original skeleton in several places — see Analysis Notes per issue.

---

### Epic 1.1 — SessionState Storage Unification

**Blocks:** Correct persistence path for checkpoints; config isolation per session.
**Source issues:** SS-02
**Severity (actual):** Medium — does NOT crash boot; session works but checkpoints land at
wrong path in production and `SQLiteStorageAdapter` is dead code.

**What the code actually does (traced):**

`KernelService._create_session_tier2` (service.py:1608) creates:

```python
ss_storage = SQLiteStorageAdapter(db_path=self._config.sessionstate_db_path)  # e.g. ./data/k1/sessionstate.db
ssm = SessionStateFactory.create_with_ports(session_id, storage=ss_storage, ...)
```

`SessionStateFactory.create_with_ports` (factory.py:283) passes `ss_storage` as
`storage_port` to `SessionStateManager.__init__` where it is stored as `self._storage_port`
**but never called from any method** (confirmed: grep for `_storage_port\.` returns 0 matches
in manager.py).

Inside `SessionStateManager.__init__`, the actual storage is:

```python
self._local_cold_archive = local_cold_archive or LocalColdArchive()
# ↑ local_cold_archive=None because create_with_ports never accepts/passes it
# ↑ So LocalColdArchive() is created with DEFAULT path ~/.familyos/k1/sessionstate.db
```

All `checkpoint()` and `restore()` calls go through `self._local_cold` (LocalColdTier
wrapping `_local_cold_archive`), **ignoring** the configured `sessionstate_db_path`.

Schema mismatch confirmed:

- `SQLiteStorageAdapter.ALL_TABLES` = 4 tables (no telemetry/persona/artifacts)
- `LocalColdArchive.ARCHIVE_TABLES` = 7 tables (adds `st_telemetry_archive`,
  `st_persona_archive`, `st_artifacts_archive`)
- No OperationalError — both create their tables independently. The confusion is
  architectural (two classes, same file, different table sets) not a runtime crash.

**Original assessment ("OperationalError on first checkpoint") was wrong.**
The actual issues are: (a) `SQLiteStorageAdapter` is dead code, (b) the db_path
configured in KernelConfig is silently ignored for actual checkpoints.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 1.1.1 | SS-02-A: Thread `db_path` from KernelConfig through `SessionStateFactory.create_with_ports` into `LocalColdArchive` construction inside `SessionStateManager.__init__` | [ ] | **Files:** `k1/sessionstate/factory.py:283` (`create_with_ports`), `k1/sessionstate/manager.py:518` (`__init__`), `k1/kernel/service.py:1608` (`_create_session_tier2`). **Scope:** S. Add `db_path: Optional[Path] = None` param to `create_with_ports`; pass to `SessionStateManager.__init__`; pass to `LocalColdArchive(db_path=db_path)`. |
| 1.1.2 | SS-02-B: Remove `SQLiteStorageAdapter` dead code from `create_with_ports` path OR make it a thin façade over `LocalColdArchive` (unify schema to 7 tables) | [ ] | **Files:** `k1/sessionstate/adapters/sqlite_storage.py`, `k1/sessionstate/factory.py`. **Decision needed:** Delete `ss_storage` from `_create_session_tier2` (since it's never used), OR keep it as the IStoragePort impl and route checkpoint/restore through it. If deleted, `IStoragePort` param in `create_with_ports` becomes unused — remove or repurpose. |
| 1.1.3 | SS-02-C: Standalone factory path: `create_standalone()` creates both `SQLiteStorageAdapter` and `LocalColdArchive` pointing to same db — same dead-code issue | [ ] | **File:** `k1/sessionstate/factory.py:167`. Same fix: remove `SQLiteStorageAdapter` construction from `create_standalone`; the `LocalColdArchive` already handles all persistence. **Scope:** S. |

---

### Epic 1.2 — Concierge Config (C05 — VERIFY, LIKELY ALREADY FIXED)

**Blocks:** Concierge import at boot.
**Source issues:** C05
**IMPORTANT:** Code trace shows this may already be fixed.

**What the code actually does (traced):**

`k1/concierge/config/__init__.py` imports **only** from `k1.concierge.config.loader`:

```python
from k1.concierge.config.loader import (ActorsConfig, ..., get_config, load_config, ...)
```

`k1/concierge/config/loader.py` is a **standalone 1,400-line module** containing all config
dataclasses, `get_config()`, `load_config()`, `reset_config()`, and `_build_config()`.
It has **zero imports from `poc/`** in production code paths. The docstring header
mentions `poc.k1_poc.config.loader` but that is leftover copy-paste in comments only.

Grep for `from poc.` across all `k1/concierge/**/*.py` (non-test, non-doc) returns:
**zero matches** in production source files.

**Conclusion:** C05 appears already resolved. The OPEN_ISSUES.md entry was likely filed
against an older version before the migration was completed.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 1.2.1 | C05-VERIFY: Confirm `k1/concierge/config/__init__.py` has no `from poc.` imports; close C05 if verified | [ ] | **Files:** `k1/concierge/config/__init__.py`, `k1/concierge/config/loader.py`. Run `grep -r "from poc" k1/concierge/ --include="*.py"` excluding tests and `_scan_temp/`. If clean → mark C05 resolved in OPEN_ISSUES.md. **Scope:** XS. |
| 1.2.2 | C05-CLEANUP: Remove stale doc header from `loader.py` that says `poc.k1_poc.config.loader`; add `py.typed` marker to `k1/concierge/config/` | [ ] | **File:** `k1/concierge/config/loader.py` line 2–4. Fix misleading docstring. **Scope:** XS. |

---

### Epic 1.3 — Kernel Startup Hardening

**Blocks:** Resource safety, config coherence.
**Source issues:** K4, K7, K8
**Severity (actual):** Low — none of these block a chat turn; they are safety/config issues.

**What the code actually does (traced):**

**K4 — max_sessions not enforced:**
`KernelService.create_session()` (service.py:567):

```python
if not self._running:     raise RuntimeError(...)
if session_id in self._sessions:    raise ValueError(...)
session = await self._create_session_tier2(session_id, device_id)
```

No check against `self._config.max_sessions` (defined as `100` in KernelConfig at line 77
of `k1/concierge/config/kernel.py`). Confirmed.

**K7 — dead flags in KernelConfig:**
`KernelConfig` (k1/concierge/config/kernel.py) has: `enable_experience`, `enable_delta`,
`enable_hitl`, `enable_orchestrator`. These flags exist. KernelService `_startup_tier1`
and `_create_session_tier2` do **not** read them. However, `ConciergeFactory` (called
from `_create_session_tier2` at P4) DOES read `enable_experience` (line 661),
`enable_delta` (line 669), `enable_hitl` (line 693), `enable_orchestrator` (line 729).
So the flags are used in ConciergeFactory, not dead globally — but the kernel's tier-1
orchestrator/experience startup does not gate on them. The real confusion is that
`enable_orchestrator=False` disables orchestrator in the concierge dispatch but NOT
in the kernel's S5 Orchestrator startup.

**K8 — scaffolding ports not enforced:**
`k1/kernel/ports/` contains `IFabricPort`, `IOrchestratorPort`, `IPlannerPort`.
`KernelService._validate_ports()` (service.py:758) uses `hasattr` structural checks
(`execute`, `process`, `start`) NOT `isinstance` against these Protocol classes.
The Protocol files exist but are never imported into KernelService. Confirmed.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 1.3.1 | K4: Add `max_sessions` guard in `create_session()` | [ ] | **File:** `k1/kernel/service.py:567`. Add: `if len(self._sessions) >= self._config.max_sessions: raise RuntimeError(f"session limit reached ({self._config.max_sessions})")`. **Scope:** XS. No cross-deps. |
| 1.3.2 | K7: Decide fate of `enable_experience`/`enable_delta`/`enable_hitl`/`enable_orchestrator` flags — document that they control Concierge wiring not kernel tier-1 startup, OR add matching tier-1 guards | [ ] | **Files:** `k1/concierge/config/kernel.py`, `k1/concierge/factory.py:661,669,693,729`. The flags DO work for concierge-level gating. Fix: Add comment to each flag explaining it gates ConciergeFactory, not KernelService S5/S6. Rename to `concierge_enable_*` if confusion persists. `enable_hitl` vs `enable_hil_service` — `enable_hitl` gates concierge's internal HIL path; `enable_hil_service` gates the shared `HumanInTheLoopService` at S2.5. Both are meaningful and different. **Scope:** XS (doc/rename). |
| 1.3.3 | K8: Either add `isinstance(..., IFabricPort)` etc. checks at S3/S5/S6 or delete unused port files in `k1/kernel/ports/` | [ ] | **Files:** `k1/kernel/ports/model_hub_port.py`, `orchestrator_port.py`, `planner_port.py`; `k1/kernel/service.py:758`. **Scope:** S. Decision: if delete, remove port files + fix any imports. If wire, add `@runtime_checkable` to protocols and use `isinstance`. |

---

### Epic 1.4 — Model Hub Port Wiring

**Blocks:** All 10 bus topic emissions from Model Hub; health reporting; monitoring.
**Source issues:** M01
**Severity (actual):** High — system works but is monitoring-blind; all `k1.model_hub.*` events
are suppressed; health endpoint shows stale data.

**What the code actually does (traced):**

`KernelService._startup_tier1` S2 (service.py) assembles `mh_ports`:

```python
mh_ports = {
    "credential_port": CredentialStoreAdapter(),
    "event_port":      MHEventBusAdapter(bus=self._bus),      # ← passes in
    "state_read_port": SessionStateProdAdapter(...),           # ← passes in
    "metrics_port":    PrometheusAdapter(),                    # ← passes in
    "config_port":     ConfigAdapter(),                        # ← passes in
    # health_port NOT IN DICT                                  # ← missing!
}
```

`ModelHubFactory.from_config()` (factory.py:331–344) receives `ports` dict and extracts:

```python
event_port       = ov.get("event_port",       TestEventAdapter())    # ← used from mh_ports
state_read_port  = ov.get("state_read_port",  TestStateReadAdapter()) # ← used from mh_ports
health_port      = ov.get("health_port",      TestHealthAdapter())   # ← MISSING → uses Test stub
config_port      = ov.get("config_port",      ...)                   # ← used from mh_ports
```

**BUT** even after extraction, from_config **stores** them but does NOT inject them into
internal services (`RequestRouter`, `HealthReportAdapter`, etc.). OPEN_ISSUES.md §M01
explicitly states: "stored but never injected into any internal service."

So the real problem is two-layered:

1. `health_port` is not even passed in `mh_ports` (uses `TestHealthAdapter` fallback)
2. ALL 4 injected ports go into `from_config` but are never wired into `RequestRouter`
   or other internals — confirmed by OPEN_ISSUES.md

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 1.4.1 | M01-A: Wire `event_port` into `RequestRouter._event_port` inside `from_config` | [ ] | **File:** `k1/model_hub/factory.py` (from_config, around line 393+). After constructing `RequestRouter`, assign `router._event_port = event_port`. Verify `RequestRouter` has this attribute slot. **Scope:** S. |
| 1.4.2 | M01-B: Wire `health_port` into `HealthReportAdapter` inside `from_config`; add `health_port` to `mh_ports` dict in kernel service.py S2 | [ ] | **Files:** `k1/model_hub/factory.py`, `k1/kernel/service.py` (S2 mh_ports dict). Add `"health_port": HealthReportAdapter(...)` to `mh_ports`. Then in `from_config`, wire into health service. **Scope:** S. |
| 1.4.3 | M01-C: Wire `config_port` into `ConfigAdapter` in `from_config`; wire `state_read_port` into `RequestRouter` | [ ] | **File:** `k1/model_hub/factory.py`. Confirm all 4 ports have a target service to receive them. Add the assignments. **Scope:** S. |

---

## Milestone 2 — Chat with Memory

*Goal: turns are extracted, atoms written to K0, recall works on next session.*

> **Deep-dive status:** All 4 epics fully traced by parallel subagents. All findings verified against source.
> Several skeleton descriptions were inaccurate — see Analysis Notes per issue.

---

### Epic 2.1 — Memory Writer Topic Alignment

**Blocks:** `TurnDispatcher` receiving any events; stale module-level topic constant; contract drift.
**Source issues:** MW-01
**IMPORTANT:** Original skeleton was partially wrong — `SessionBatchDispatcher` (the production path) already subscribes to the correct topic. The real bugs are in `TurnDispatcher` and `events.py`.

**What the code actually does (traced):**

Canonical topic registry: `k1/concierge/bus/topics.py:38`:

```python
TOPIC_TURN_COMPLETED = "k1.session.turn.completed.v1"   # canonical — with 'd'
```

Concierge emits via `fsm/controller.py → build_turn_completed() → bus.publish(TOPIC_TURN_COMPLETED)`.

Two dispatchers in Memory Writer:

| Class | File | Line | TOPIC | Receives events? |
|---|---|---|---|---|
| `SessionBatchDispatcher` | `pipeline/session_batch_dispatcher.py` | 47 | `"k1.session.turn.completed.v1"` | ✅ YES — already correct |
| `TurnDispatcher` | `pipeline/turn_dispatcher.py` | 37 | `"k1.session.turn.complete.v1"` | ❌ DEAD — never fires |

Also stale:

- `k1/memory_writer/events.py:37`: `TOPIC_TURN_COMPLETE = "k1.session.turn.complete.v1"` — wrong (no `d`)
- `k1/contracts/modules/memory_writer/wiring.contract.yaml:259`: references wrong topic

Cross-dependency: `k1/learning/` docs reference `turn.complete.v1` (no `d`) — learning loop may also be dead, needs separate audit.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 2.1.1 | MW-01-A: Fix `TurnDispatcher.TOPIC` from `turn.complete.v1` to `turn.completed.v1`, OR delete `TurnDispatcher` if it is fully superseded by `SessionBatchDispatcher` | [x] | **File:** `k1/memory_writer/pipeline/turn_dispatcher.py:37`. First determine if `TurnDispatcher` is used anywhere in production (check callers). If no callers → delete. If callers → fix string. **Scope:** XS. |
| 2.1.2 | MW-01-B: Fix stale `TOPIC_TURN_COMPLETE` constant in `events.py`; rename to `TOPIC_TURN_COMPLETED` to match canonical name | [x] | **File:** `k1/memory_writer/events.py:37`. Change value to `"k1.session.turn.completed.v1"`, rename constant. Fix any imports of the old name. **Scope:** XS. |
| 2.1.3 | MW-01-C: Update `wiring.contract.yaml` to correct topic string | [x] | **File:** `k1/contracts/modules/memory_writer/wiring.contract.yaml:259`. **Scope:** XS. |
| 2.1.4 | MW-01-D: Add startup assertion comparing `SessionBatchDispatcher.TOPIC` against `k1.concierge.bus.topics.TOPIC_TURN_COMPLETED` to prevent future drift | [x] | **File:** `k1/memory_writer/pipeline/session_batch_dispatcher.py` (in `__init__` or module-level). **Scope:** XS. |
| 2.1.5 | MW-01-E: Audit `k1/learning/` actual subscription code — docs say `turn.complete.v1` (no `d`), suggesting learning loop events are also dead | [ ] | **Scope:** S (audit + fix if needed). Separate issue, not blocking chat-with-memory. |

---

### Epic 2.2 — Bridge / K0 Connection

**Blocks:** All K0 memory operations (store, recall, checkpoint, feedback, IFL routing).
**Source issues:** Fabric#5
**Severity (actual):** XL — this is a fundamentally incomplete subsystem, not just a wiring bug.

**What the code actually does (traced):**

Chain: `KernelService._startup_tier1` S4:

```python
self._bridge = SinkBridgeAdapter(outbox_path=...)   # bridge_enabled=True
bridge_client = self._bridge.get_client()            # returns SinkBridgeClient
bridge_adapter = BridgeConnectionAdapter(client=bridge_client)
```

`SinkBridgeAdapter.connect()` (kernel/adapters/bridge_adapter.py:63): **explicit no-op** — docstring: "No-op — SinkBridgeClient is always offline."

`BridgeConnectionAdapter.__init__` calls `_probe_connection()` which does:

```python
if hasattr(self._client, "is_connected") and self._client.is_connected():
    self._mark_connected()
```

`SinkBridgeClient` has **no `is_connected()` method** → probe no-ops → `_connected = False` forever.

`reconnect()` exists in `BridgeConnectionAdapter` but is **never called** from service.py or any lifecycle hook.

**Two-layer problem:**

1. `SinkBridgeClient` is an intentional **offline queue sink** (writes to SQLite outbox, no K0 connection). `connect()` and `is_connected()` don't exist on it by design.
2. `HttpBridgeClient` exists in `bridge/client.py:280` but is construction-guarded behind `_RUNTIME_CONSTRUCTION_TOKEN` — only buildable via `BridgeRuntime.from_registry()` which is called **nowhere** in service.py.
3. **API mismatch**: `BridgeConnectionAdapter.send_command()` calls `client.send(...)` — the `HttpBridgeClient` API. `SinkBridgeClient` has `submit_command()` instead. Even if `_connected` were `True`, calls would `AttributeError`.

Operations silently failing when offline: `memory.store`, `memory.recall`, `memory.delta`, `checkpoint`, `feedback.signal`, `route_ifl` — all return `BridgeCommandResult.fail("k0_offline", ...)` with **no alarm**.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 2.2.1 | Fabric#5-A: Add `is_connected()` to `SinkBridgeClient` (returns `False`) so probe doesn't silently no-op; add `connect()` as a no-op with a logged warning | [x] | **File:** `bridge/client.py`. Minimal fix: adapter at least knows it probed and got False (documented offline), instead of "probe skipped entirely." **Scope:** XS. Does NOT restore K0. |
| 2.2.2 | Fabric#5-B: Document in `KernelConfig.bridge_enabled` docstring that `True` = "enable outbox queueing" NOT "live K0 connection" — rename or add `bridge_live` flag for when `HttpBridgeClient` is ready | [x] | **File:** `k1/concierge/config/kernel.py`. Prevents operator confusion. **Scope:** XS. |
| 2.2.3 | Fabric#5-C: Add `BridgeConnectionAdapter.add_done_callback()` / startup log that explicitly states "K0 bridge: OFFLINE (SinkBridgeClient mode)" at S4 | [x] | **File:** `k1/kernel/service.py` after bridge_adapter construction. Makes offline mode visible in logs rather than silent. **Scope:** XS. |
| 2.2.4 | Fabric#5-D: **Full K0 integration** — Build `BridgeRuntime.from_registry()` call path; construct `HttpBridgeClient`; wire into `KernelService` when `bridge_live=True`; implement `reconnect()` lifecycle | [ ] | **Files:** `bridge/client.py`, `bridge/runtime.py` (new), `k1/kernel/service.py`, `k1/kernel/adapters/bridge_adapter.py`. Fix the API mismatch (`send()` vs `submit_command()`). **Scope:** XL. This is a new subsystem build, not a bug fix. |

---

### Epic 2.3 — Memory Writer Correctness

**Blocks:** Reliable, non-duplicating, location-aware memory writes.
**Source issues:** MW-02, MW-03, MW-04, MW-06, MW-07

**What the code actually does (traced):**

All 5 issues confirmed real. Key findings:

- **MW-04**: `PlaceResolver([])` singleton in `factory.py:112` — comment says "populated per-turn from SS" but no `set_entities()` method exists on `PlaceResolver`. Every geohash written is `"000000"`. `context_assembly.py` has a separate working `PlaceResolver` path but `FieldMapper` (the envelope-writing path) always uses the empty singleton.
- **MW-07**: `affective_baseline` and `ifl` are absent from `SECTION_BUDGETS` in `sizetracker.py:121`. `ContextBuilder` reads them via `snapshot.get(...)` → always gets `None`/`{}`. Both are listed in the contract yaml as expected. Need to confirm: does any writer populate these sections? If not, fix is a warning log, not a budget entry.
- **MW-03**: Worst case partially mitigated — `if not self._buffer: return` under lock prevents truly empty LLM call, but two concurrent `process_session()` calls on a 1-turn buffer race are still possible.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 2.3.1 | MW-02-A: Replace `_processed_ids: set[str]` with `deque(maxlen=200)` in both `TurnDispatcher` and `SessionBatchDispatcher` | [x] | **Files:** `k1/memory_writer/pipeline/turn_dispatcher.py:48`, `pipeline/session_batch_dispatcher.py:68`. Change `.add()` to `.append()`. Note: `in` on `deque` is O(n) — at maxlen=200 negligible. If O(1) needed, maintain parallel set. **Scope:** XS. |
| 2.3.2 | MW-02-B (long-term): Persist `_processed_ids` to K0 KV store; restore on startup for crash-proof dedup | [ ] | **Depends on:** Fabric#5-D (K0 connection). **Scope:** M. Deferred until K0 live. |
| 2.3.3 | MW-03: Add `_flush_in_progress: bool` guard to `SessionBatchDispatcher._flush_buffer()` | [x] | **File:** `k1/memory_writer/pipeline/session_batch_dispatcher.py:165`. Add flag to `__init__`; set True before async pipeline call, False in `finally`. **Scope:** XS. |
| 2.3.4 | MW-04-A: Add `set_entities()` method to `PlaceResolver`; call it in `pipeline.py:process()` Stage 2 from `beliefs_active.mentioned_entities` | [x] | **Files:** `k1/memory_writer/place_resolver.py`, `k1/memory_writer/pipeline/pipeline.py`. Option A (minimal): add `set_entities()`, call before envelope build. Option B (cleaner): pass entities through `ExtractionContext`. **Scope:** S. |
| 2.3.5 | MW-04-B: First confirm whether any writer currently populates `beliefs_active.mentioned_entities` — if phantom, add a warning instead of trying to resolve | [x] | **Cross-dep:** grep for `.mentioned_entities` writes in `k1/concierge/`. If absent → warning log in `PlaceResolver`. |
| 2.3.6 | MW-06: Add `correction_signal`/`contradiction_signal` priority check before overwriting `_queued_payload` in `TurnDispatcher` | [x] | **File:** `k1/memory_writer/pipeline/turn_dispatcher.py:85-92`. First confirm these field names on `TurnCompletePayload` in `events.py` (use `getattr(..., False)` default for safety). **Scope:** XS. |
| 2.3.7 | MW-07-A: Confirm which component (if any) writes `affective_baseline` and `ifl` sections to SessionState | [x] | **Action:** grep for `affective_baseline` and `ifl` in `k1/concierge/**/*.py`. If no writer → fix is warning log in `ContextBuilder`. If writer exists → add section budget in `sizetracker.py`. |
| 2.3.8 | MW-07-B: Add budget entries for `affective_baseline` and `ifl` in `k1/sessionstate/sizetracker.py` IF writers exist | [ ] | **File:** `k1/sessionstate/sizetracker.py:121`. Proposed: `affective_baseline` WARM tier 4KB eviction-priority 9; `ifl` HOT tier 2KB never-evict. **Scope:** S. **Depends on:** 2.3.7. |

---

### Epic 2.4 — Memory Writer Observability

**Source issues:** MW-05, MW-08
**Severity (actual):** Medium — these don't block extraction but blind operators to extraction quality and cause unbounded context in long sessions.

**What the code actually does (traced):**

**MW-05:** `PipelineResult` fields: `skipped`, `skip_reason`, `atoms_extracted`, `envelopes_submitted`, `llm_tokens_used`, `llm_latency_ms`, `trace_id`, `error` — no `atoms_below_confidence_floor`. The drop happens in `ExtractionValidator.validate()` (extraction_validator.py:116) via `if ext.confidence < floor: continue` — dropped count is computed nowhere, logged only as individual `log.info`. The `k1.mw.extraction.complete.v1` event only carries `atom_count` (post-filter). `HealthAdapter` exists but `last_extraction_ms` is hardcoded `0.0` permanently.

**MW-08:** `read_snapshot_enriched()` (session_reader.py:46) defaults `history_limit=50` cold archive turns plus up to 25 live turns = 75 turns total. `config.llm_token_budget_session = 4000` (config.py:88) exists but is **never consulted** to derive the history limit. The literal `50` has no config field — it's a bare constant. Only one call site in `pipeline.py:282` with no `history_limit` argument passed.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 2.4.1 | MW-05-A: Add `dropped_confidence: int` return field to `ExtractionValidator.validate()`; propagate to `PipelineResult.atoms_below_confidence_floor` | [x] | **Files:** `k1/memory_writer/extraction/extraction_validator.py:116`, `k1/memory_writer/pipeline/pipeline.py:34` (`PipelineResult`). Return `ValidateResult(atoms, dropped_confidence)` namedtuple. Populate in `process()` and `process_session()`. **Scope:** XS. |
| 2.4.2 | MW-05-B: Add `atoms_dropped` to `k1.mw.extraction.complete.v1` event payload | [x] | **File:** `k1/memory_writer/pipeline/pipeline.py:207`. Add key to dict. **Scope:** XS. |
| 2.4.3 | MW-05-C: Fix `HealthAdapter.last_extraction_ms` hardcoded `0.0` — add `last_ms_fn: Callable[[], float]` constructor parameter | [x] | **File:** `k1/memory_writer/adapters/health_adapter.py:58`. Note: the parameter doesn't exist at all — needs to be added to `__init__` signature AND wired in `MemoryWriterFactory`. **Scope:** S. |
| 2.4.4 | MW-08-A: Add `archive_history_limit: int = 50` to `MWConfig` (config.py:72); replace bare literal in `read_snapshot_enriched()` | [x] | **Files:** `k1/memory_writer/config.py:72`, `k1/memory_writer/context/session_reader.py:46`. **Scope:** XS. |
| 2.4.5 | MW-08-B: Derive adaptive `history_limit` from remaining token budget before calling `read_snapshot_enriched()` in `pipeline.py:process_session()` | [ ] | **File:** `k1/memory_writer/pipeline/pipeline.py:282`. Estimate batch tokens → compute remaining budget → derive archive slots. Add `context_truncated: bool` to `PipelineResult`. **Scope:** S. |

---

## Milestone 3 — Multi-session + Session Identity

*Goal: two sessions run concurrently with correct per-session persona and state.*

> **Deep-dive status:** All 3 epics fully traced by parallel subagents. All findings verified against source.
> Several issues are latent (not active bugs today) due to M01 port-wiring not yet done — noted per issue.

---

### Epic 3.1 — ModelHub Per-Request Session Context

**Blocks:** Correct persona/control routing in multi-session mode (latent until M01 port wiring lands).
**Source issues:** K1
**Severity (actual):** High (latent) — bug has zero runtime impact today only because `state_read_port` is not yet wired into `RequestRouter` (M01). The moment M01 is fixed, session B's LLM calls use session A's persona/control.

**What the code actually does (traced):**

`_FirstSessionSSMShim` — defined at `k1/kernel/service.py:134`:

```python
class _FirstSessionSSMShim:
    def get_section(self, name: str) -> Any | None:
        for session in self._sessions.values():   # insertion-order dict
            return session.session_state.get_section(name)   # always first session
        return None
```

Instantiated at S2 (service.py:1050) and passed as `manager=` to `SessionStateProdAdapter`, which becomes `state_read_port` in `mh_ports`.

`ModelHubFactory.from_config()` (factory.py:510): explicitly comments *"state_read_port validated but not yet wired into any service."* `RequestRouter.route()` never calls it. Bug is latent.

**Correct infrastructure already exists:** `SessionRoutingStateReader` at `k1/kernel/adapters/session_routing_reader.py` already does per-`session_id` dispatch and is wired for Orchestrator/Planner. The shim replacement is a 3-line swap at S2.

`HubRequest` dataclass (`k1/model_hub/types.py:277`): fields are `capability`, `payload`, `constraints`, `trace_id`, `idempotency_key`, `request_id` — **no `session_id`**. Must be added before routing can use per-session state.

Note: `HubRequest` is `frozen=True`. Adding `session_id` will silently invalidate existing `ResponseCache` keys (ISSUE-M04 interaction — not a correctness issue but affects cache hit rate in staging).

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 3.1.1 | K1-A: Add `session_id: str = ""` to `HubRequest` dataclass | [x] | **File:** `k1/model_hub/types.py:277`. Add as optional field with default `""`. `frozen=True` means all existing construction sites still compile (no positional arg change). **Scope:** XS. **Note:** Will silently bust `ResponseCache` keys — M04 fix should accompany this. |
| 3.1.2 | K1-B: Delete `_FirstSessionSSMShim`; replace S2 wiring with `SessionRoutingStateReader`-backed adapter | [x] | **Resolution:** Replaced `_FirstSessionSSMShim` with `_NullSSMShim` (mirrors 3.2.1 pattern). The plan's suggested `SessionRoutingStateReader(self._sessions)` swap was incompatible — wrong constructor signature AND wrong interface (`read_section(session_id, section)` vs adapter's `get_section(name)`). The session-aware path now flows through `request.session_id` → `RequestRouter` → port (3.1.1+3.1.3). **Scope:** XS. |
| 3.1.3 | K1-C: Wire `state_read_port` into `RequestRouter` so it actually resolves per-session state | [x] | **File:** `k1/model_hub/factory.py` around line 393+. This is the M01-C issue (1.4.3) — same fix required here. **Scope:** S. **Dependency:** Must be done in same batch as 3.1.1 + 3.1.2 or shim removal is cosmetic. |

---

### Epic 3.2 — Planner Shared State Fix

**Blocks:** All state-dependent planning decisions silently degrading to defaults.
**Source issues:** K2
**Severity (actual):** Medium — active bug, not latent. Every `state_port.read_sections()` call in the Planner returns `{}`.

**What the code actually does (traced):**

`KernelService._startup_tier1` S6 (service.py:1298):

```python
pl_state = PlannerStateAdapter(
    reader=self._session_routing_reader,
    session_id="__shared__",   # ← sentinel, never a real session key
)
```

`SessionRoutingStateReader._resolve_manager("__shared__")` does a `dict.get("__shared__")` on `KernelService._sessions` → returns `None` every time. The DEBUG log at `session_routing_reader.py:133` is the only indication. No ERROR, no metric, no bus event.

Planning decisions that depend on persona, control, or task state silently use empty snapshots — no exception raised.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 3.2.1 | K2-A: Replace `PlannerStateAdapter(session_id="__shared__")` with `NullSessionStateReaderAdapter` (explicit documented no-op) | [x] | **File:** `k1/kernel/service.py:1298`. Create `NullSessionStateReaderAdapter` that returns `{}` and logs a WARNING once. Swap at S6. Makes the degradation visible and intentional rather than a silent sentinel lookup. **Scope:** XS. **Resolution:** Created `k1/planner/adapters/null_state_read_adapter.py::NullStateReadAdapter`. After 3.2.2 made per-call session_id work, S6 was reverted to `PlannerStateAdapter(reader=..., session_id="")` since the empty sentinel now fails-open via `effective_sid` fallback. |
| 3.2.2 | K2-B (long-term): Thread requesting `session_id` into each Planner invocation — Planner becomes per-request session-aware | [x] | **Resolution:** Trace showed Orchestrator already extracts session_id and packs into `PlanRequest.context.session_id`; sketch/expand stages already pass session_id to `tool_router.read_context()`. Only the final hop was dropping it. Added `session_id: str = ""` to `IStateReadPort.read_sections()`, threaded through `SessionStateReadAdapter` (with `effective_sid = session_id or self._session_id` fallback) and `ToolCallRouter.read_context` / `_resolve_port_method`. **Scope:** S (smaller than estimated). |

---

### Epic 3.3 — Session Teardown Completeness

**Blocks:** Resource cleanup on session destroy; event-loop stall risk during high-load teardown.
**Source issues:** K3, K9
**Severity (actual):** K9 is more severe than OPEN_ISSUES states — `ssm.stop()` blocks the **event loop thread** (no `asyncio.to_thread`), freezing all other sessions' I/O during the SQLite WAL checkpoint.

**What the code actually does (traced):**

`destroy_session` at `k1/kernel/service.py:608–712` currently:

```
selfmodel.uninstall_from_session()    ← no timeout
memory_writer.stop()                  ← ✅ wait_for 10s
concierge.stop()                      ← ✅ wait_for 10s
[fabric.shutdown() MISSING]           ← K3 gap
session_state.stop()                  ← ❌ bare sync call, blocks event loop
bus.close()                           ← sync, low risk
router.close()                        ← sync, low risk
```

`Fabric.shutdown()` (`k1/fabric/fabric.py:1655`) — **exists and is already implemented**. Stops `health_checker` (async) and `module_loader` (sync flag). Safe to call, no hang risk.

`SessionStateManager.stop()` (`k1/sessionstate/manager.py:1274`) — **synchronous**. Serializes HOT+WARM sections → `json.dumps` + `base64.b64encode` → `LocalColdArchive.archive()` → **SQLite write, no timeout**. On locked/corrupt DB: hangs indefinitely on the event loop thread.

**Additional gaps found (beyond K3/K9):**

- `experience_layer`, `delta_aggregator`, `delta_applicator` fields on `SessionInstance` — **zero teardown lines reference them**. Unknown if they hold background tasks or DB handles.
- `dead_letter_consumer` stored on `SessionInstance` — not explicitly stopped in teardown.
- `hil_port`, `ledger`, `ledger_store` — not touched (likely stateless but needs audit).
- `front_dispatcher`, `back_dispatcher` — not explicitly torn down (may hold bus subscriptions open post-`bus.close()`).

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 3.3.1 | K3: Add `await session.fabric.shutdown()` wrapped in `_with_timeout` after `concierge.stop()` | [x] | **File:** `k1/kernel/service.py` inside `destroy_session`, after concierge stop line. `fabric.shutdown()` already implemented at `k1/fabric/fabric.py:1655`. Insert: `await asyncio.wait_for(session.fabric.shutdown(), timeout=_TEARDOWN_TIMEOUT)`. **Scope:** XS. |
| 3.3.2 | K9: Wrap `session.session_state.stop()` with `asyncio.wait_for(asyncio.to_thread(session.session_state.stop), timeout=10.0)` | [x] | **File:** `k1/kernel/service.py` inside `destroy_session`. The sync call blocks the event loop thread, not just the coroutine — affects all active sessions. Must use `asyncio.to_thread` to offload the SQLite write. **Scope:** XS. |
| 3.3.3 | Audit `experience_layer`, `delta_aggregator`, `delta_applicator` lifecycle — add stop calls if they hold background tasks or DB handles | [x] | **Resolution:** Added `await asyncio.wait_for(agg.flush(), timeout=_TEARDOWN_TIMEOUT)` for delta_aggregator in destroy_session before fabric shutdown. `experience_layer` and `delta_applicator` audit confirmed stateless / no resources requiring teardown. **Scope:** S. |
| 3.3.4 | Audit `dead_letter_consumer` — if it's a running Task or has a `.stop()` method, add explicit cancellation/stop in teardown | [x] | **Resolution:** Added idempotent `stop()` method to `k1/concierge/fsm/dead_letter_consumer.py` (calls `self._bus.unsubscribe(self._handle)`, sets `_handle = None`). Wired into `destroy_session`. **Scope:** XS. |

---

## Milestone 4 — Full Planning (HIGH-tier Tasks)

*Goal: complex multi-step tasks ("book a vacation") produce a real plan and execute it.*

> **Deep-dive status:** All 3 epics fully traced end-to-end, kernel/service.py read completely.
> **Major finding:** P01 is FULLY IMPLEMENTED — the planner OPEN_ISSUES.md entry is stale.
> Several P02–P08 descriptions were inaccurate — corrected per source.

---

### Epic 4.1 — Activate Real Planner in Kernel

**Blocks:** Any HIGH-tier task from working end to end.
**Source issues:** P01
**VERDICT: ALREADY DONE. Mark P01 closed in planner OPEN_ISSUES.md.**

**What the code actually does (traced — kernel/service.py read fully):**

S5 (service.py:1250): `MockPlannerAdapter()` created as placeholder passed to `OrchestratorFactory.create_production()`.

S6 (service.py:1291–1320): Real `PlannerAgent` fully constructed with all 7 ports:

```python
pl_llm     = LLMGatewayAdapter(llm_request_bus=ModelHubRequestBus(self._model_hub))
pl_fabric  = FabricRetrievalAdapter(fabric_retrieval=self._shared_fabric.retrieval)
pl_state   = PlannerStateAdapter(reader=self._session_routing_reader, session_id="__shared__")
pl_bridge  = PlannerBridgeAdapter(bridge_port=bridge_adapter)
pl_delta   = PlannerDeltaBusAdapter(delta_bus=delta_bus)
pl_event   = PlannerEventBusAdapter(event_port=event_port)
pl_mailbox = PlannerMailboxAdapter()

self._planner = await PlannerFactory.create_production(
    llm_port=pl_llm, fabric_port=pl_fabric, state_port=pl_state,
    bridge_port=pl_bridge, delta_port=pl_delta, event_port=pl_event,
    mailbox_port=pl_mailbox, hil_port=self._hil_service,
)
```

S6b (service.py:1326–1334): Per-instance `CircuitBreaker` created; hot-swap executed:

```python
planner_cb = CircuitBreaker(provider_id="planner", config=CircuitBreakerConfig())
self._orchestrator.bind_planner(
    PlannerAdapter(planner_mailbox=self._planner.get_mailbox(), cb_planner=planner_cb)
)
```

S7 (service.py:1341): `asyncio.create_task(self._planner.start(), name="planner-agent")`

`_verify_planner_orchestrator_crosswire()` (service.py:955): raises `RuntimeError` if swap didn't happen. Runs before `self._running = True`. `MockPlannerAdapter` is never visible during any live session.

**All 7 ports wired:** `llm_port` ✅, `fabric_port` ✅, `state_port` ✅ (has `__shared__` bug, tracked as K2 in M3), `bridge_port` ✅, `delta_port` ✅, `event_port` ✅, `mailbox_port` ✅.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 4.1.1 | P01-CLOSE: Mark P01 resolved in `k1/planner/OPEN_ISSUES.md` | [ ] | **File:** `k1/planner/OPEN_ISSUES.md`. All 6 steps from P01 "Fix" are live in `service.py`. No code change needed — admin only. **Scope:** XS. |

---

### Epic 4.2 — Planner Internal Fixes

**Source issues:** P02, P03, P04, P05, P06, P07, P08

**What the code actually does (traced):**

| Issue | Real? | Key Finding |
|---|---|---|
| P02 | ✅ Real | `_build_payload` imported via **deferred local import** inside `_to_hub_request()` — `ImportError` fires at call time, not import time. No public re-export exists. |
| P03 | ✅ Real | `get_schema()` uses `discover_capabilities(intent=name, top_k=1)` semantic search. TODO comment in code. No `IFabricRegistryPort` exists anywhere. |
| P04 | ⚠️ Latent | `ValidationVerdict.__post_init__` already blocks approved+errors propagation. Acute failure mode is guarded. Refactor is design quality, not a crash-risk fix. |
| P05 | ⚠️ Overstated | `MailboxAdapter._plan_lock` and `PlannerAgent._plan_lock` are **different lock instances** — no direct deadlock today. Fix is rename for clarity. |
| P06 | ✅ Real | `_cancel_set: Set[str]` grows forever. Entries for: mailbox-rejected plans, already-completed plans, duplicate cancels — never removed. |
| P07 | ✅ Real | After both WAL write attempts fail: only `log.error` + `wal_persisted:false` in stage-transition delta. No dedicated `WAL_WRITE_FAILED` event on the bus. |
| P08 | ✅ Real | `depends_on` resolved by integer index from LLM output. OOB check silently drops bad indices (`if 0 <= i < len(raw_steps)` — no error, no retry). System prompt tells LLM to use zero-based indices. |

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 4.2.1 | P02: Expose `build_payload` as public in `k1/model_hub/adapters/__init__.py`; update planner import | [ ] | **File:** `k1/model_hub/adapters/__init__.py` — add `from k1.model_hub.adapters.bus_envelope_deserializer import _build_payload as build_payload` + add to `__all__`. **File:** `k1/planner/adapters/llm_gateway_adapter.py:~155` — change local import to `from k1.model_hub.adapters import build_payload`. **Scope:** XS. |
| 4.2.2 | P03: Create `IFabricRegistryPort` with `lookup(name, version)` method; add to `ToolCallRouter`; replace semantic-search fallback | [ ] | **Files:** new `k1/planner/ports/fabric_registry_port.py` (~30 lines); `k1/planner/services/tool_call_router.py:264` — replace `discover_capabilities` call with direct `lookup`; `k1/planner/factory.py` — add 4th port dependency; `k1/kernel/service.py` S6 — construct registry adapter. **Scope:** S. |
| 4.2.3 | P04: Split `ValidationVerdict` into `DeterministicValidationResult` + `ArbiterVerdict`; assemble explicitly | [ ] | **File:** `k1/planner/types.py:270-330`. Note: `__post_init__` already prevents acute propagation failure — this is a design quality fix. Callers: `validate_service.py`, `pipeline_controller.py`, `commit_service.py`. **Scope:** M. |
| 4.2.4 | P05: Rename `MailboxAdapter._plan_lock` to `_micro_replan_lock`; add comment explaining separation from `PlannerAgent._plan_lock` | [ ] | **File:** `k1/planner/adapters/mailbox_adapter.py:56`. The two locks are already separate. Rename + comment prevents future mis-wiring. **Scope:** XS. |
| 4.2.5 | P06: Change `_cancel_set: Set[str]` to `Dict[str, float]` (request_id → monotonic timestamp); add stale-entry sweep at top of each `_run_loop()` iteration | [ ] | **File:** `k1/planner/planner_agent.py:175` (decl), `:378` (add), `:440` (check/discard), `:527` (finally discard). Sweep: `stale_cutoff = time.monotonic() - (config.pipeline_timeout_ms/1000 + 5)`. **Scope:** S. |
| 4.2.6 | P07: Emit dedicated `k1.planner.delta.v1` with `delta_type="WAL_WRITE_FAILED"` in `_persist_to_wal()` after both attempts fail | [ ] | **File:** `k1/planner/stages/commit_service.py:~420` (after `else` branch). `ctx` is already in scope. Wrap emit in try/except. **Scope:** XS. |
| 4.2.7 | P08-A: After resolving `depends_on` in `_parse_response()`, raise `SketchFailedError` if dropped count > 0 (OOB index detected) | [ ] | **File:** `k1/planner/stages/sketch_service.py:~793`. Short-term: count raw vs resolved, raise on mismatch → triggers retry. **Scope:** S. |
| 4.2.8 | P08-B (long-term): Change system prompt to use intent-string `depends_on` instead of integer indices; update `SKETCH_OUTPUT_SCHEMA` and `_parse_response()` | [ ] | **Files:** `k1/planner/stages/sketch_service.py` (`_assemble_system_prompt`, `SKETCH_OUTPUT_SCHEMA`, `_parse_response`). String IDs are stable under reordering; integers are not. **Scope:** M. |

---

### Epic 4.3 — Concierge Intent Classification

**Blocks:** Correct arbiter path selection, domain routing, complexity tiering.
**Source issues:** C09
**Severity (actual):** Enhancement — system is not broken (stub runs), but all requests route as `domain=general` / `intent=general`, privacy routing is stuck, domain enrichments never fire.

**What the code actually does (traced):**

Classification port: `k1/concierge/ports.py:44` — `IClassificationPort = Phase1Pipeline`

Factory default (`k1/concierge/factory.py:539`): `"classification": StubPhase1Pipeline()` — hardwired for all non-production paths.

`StubPhase1Pipeline.classify()` (`k1/concierge/fsm/phase1.py:221`): **~15 keywords across 5 groups**:

- `hotel/flight/travel/book/trip` → `domain=travel`
- `doctor/dentist/health/appointment` → `domain=health`
- `weather/forecast` → `domain=information`
- `cancel/stop/nevermind` → `intent=cancel`
- `hi/hello/hey` → `intent=greeting`
- **Everything else** → `domain=general, intent=general` ← always fires in practice

**UltraBERT is real, not just a comment:**

- `K1UltraBERTAdapter` (`k1/concierge/fsm/ultrabert_adapter.py`): wraps `familyos_ultrabert.Client(backend="auto")` with LRU/TTL cache and thread safety. Fully implemented.
- `UltraBERTPhase1Pipeline` (`k1/concierge/fsm/ultrabert_phase1.py`): fully implemented with 12-head output mapping, confidence thresholding, `_degraded` fallback to stub.
- **Problem:** `familyos_ultrabert` requires GPU. Factory never auto-wires it — only wires if caller of `create_with_ports()` passes `classification=` port explicitly. In standard deployments: nobody passes it → `StubPhase1Pipeline` runs.
- **No availability gate** anywhere: no `if adapter.is_available()` check in factory or startup path.

C09 missing pieces:

1. Keyword fallback is only ~15 words — needs ~200 covering `home/finance/health/calendar` + `SINGLE` vs `BUNDLE` intent (neither domain nor `SINGLE/BUNDLE` detection implemented).
2. Factory must auto-try UltraBERT and fall through to keyword fallback.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 4.3.1 | C09-A: Create `KeywordPhase1Pipeline` with ~200 keywords across 4 domains (`home`, `finance`, `health`, `calendar`) + `SINGLE` vs `BUNDLE` intent detection | [ ] | **File:** `k1/concierge/fsm/phase1.py` (extend or subclass `StubPhase1Pipeline`). Must implement `SINGLE` (one clear intent) vs `BUNDLE` (multiple intents in one turn) detection. **Scope:** M. |
| 4.3.2 | C09-B: Add UltraBERT availability gate in `ConciergeFactory._construct_concierge()` Step 2 | [ ] | **File:** `k1/concierge/factory.py:588`. If `ports.classification is None`: try `K1UltraBERTAdapter()` → if `adapter.is_available()` → use `UltraBERTPhase1Pipeline`; else fall through to `KeywordPhase1Pipeline`. **Scope:** S. |

---

## Milestone 5 — Orchestration Reliability

*Goal: complex DAG plans execute reliably, cancellation is clean, crash recovery is safe.*

> **Deep-dive status:** All 4 epics fully traced end-to-end. Every file read completely.
> Several skeleton descriptions were wrong — corrected below with exact file/line citations.

---

### Epic 5.1 — Orchestrator Concurrency + Cancellation

**Source issues:** O01, O02

**What the code actually does (traced):**

**O01:** `StepRunner._execute_with_retry()` calls `await self._fabric_port.execute(current_request)` with **no `asyncio.wait_for()` wrapper** at all. `timeout_ms` is packed into `CapabilityRequest` as metadata only — enforcement depends entirely on Fabric internals. If Fabric hangs, the step truly never times out at the orchestrator boundary. Cancellation is via `interrupt_flag: bool = False` on `DAGExecutor` (set externally) — checked only at **wave boundaries**, not mid-step. `IFabricGatewayPort.execute()` (`k1/orchestrator/ports/fabric_gateway_port.py:64`) has no cancellation parameter. `default_step_timeout_ms = 30_000` in `config.py:77`.

**O02:** Two independent unbounded re-enqueue paths:

- Path 1 (service.py:1101): pre-dispatch check — if `concurrency_guard.active`, re-enqueues at BACKGROUND priority with **no counter and no limit**.
- Path 2 (service.py:1931): inside `_receive_plan()` — returns `ProcessResult.DEFERRED` silently, leaving the plan's waiter **hanging forever** (never resolved). Worse than Path 1.

`CommittedPlan` (`types.py:882`) fields: `plan_id`, `request_id`, `intent`, `steps`, `trace_id`, `dependencies`, `estimated_duration_ms`, `created_at` — **no `dequeue_count`**. `OrchestratorConfig` has no `max_deferred_plan_retries`. `OrchestratorMetrics` has no `deferred_plan_depth` gauge.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 5.1.1 | O01-A: Add `asyncio.wait_for(fabric_port.execute(...), timeout=step_timeout_ms/1000)` wrapper in `StepRunner._execute_with_retry()` | [ ] | **File:** `k1/orchestrator/orchestration/step_runner.py:~357`. Currently no timeout enforcement at orchestrator level — Fabric hang = step hangs forever. `timeout_ms` is already in `CapabilityRequest` metadata; just need to actually enforce it. **Scope:** S. |
| 5.1.2 | O01-B: Add `cancellation_token: Optional[asyncio.Event] = None` parameter to `IFabricGatewayPort.execute()` and propagate through adapter | [ ] | **Files:** `k1/orchestrator/ports/fabric_gateway_port.py:64` (port protocol), `k1/orchestrator/adapters/fabric_gateway_adapter.py:87` (adapter). Thread token from `DAGExecutor.interrupt_flag` into step execution so mid-step cancellation is possible (not just wave-boundary). **Scope:** M. |
| 5.1.3 | O01-C: Lower `default_step_timeout_ms` from `30_000` to a reasonable value (e.g. `10_000`) | [ ] | **File:** `k1/orchestrator/config.py:77`. **Scope:** XS. |
| 5.1.4 | O02-A: Add `dequeue_count: int = 0` to `CommittedPlan`; increment in Path 1 re-enqueue (service.py:1101); fail plan and resolve waiter when `dequeue_count >= config.max_deferred_plan_retries` | [ ] | **Files:** `k1/orchestrator/types.py:882`, `k1/orchestrator/orchestration/orchestrator_service.py:1101`. Add `max_deferred_plan_retries: int = 5` to `OrchestratorConfig`. **Scope:** S. |
| 5.1.5 | O02-B: Fix Path 2 deferred — `_receive_plan()` returning `DEFERRED` must resolve the plan's `PendingPlanContext` waiter with FAILED instead of leaving it hanging forever | [ ] | **File:** `k1/orchestrator/orchestration/orchestrator_service.py:1931`. This is a separate code path from Path 1 and currently **worse** — waiters hang indefinitely. **Scope:** S. **Cross-dep:** 5.1.4. |
| 5.1.6 | O02-C: Add `deferred_plan_depth` gauge to `OrchestratorMetrics`; call after each Path-1 enqueue/dequeue | [ ] | **File:** `k1/orchestrator/metrics.py`. Add `set_deferred_plan_depth(depth: int)`. **Scope:** XS. |

---

### Epic 5.2 — Orchestrator Crash Safety

**Source issues:** O03, O07

**What the code actually does (traced):**

**O03:** `_last_run` **does not exist** in `WorkflowScheduler` — STATE.md describes it but it was never implemented. The scheduler already uses `IWorkflowStoragePort`: `get_due_triggers(now)` fetches rows where `next_fire_time <= now`. `update_trigger_state()` advances timestamps **only after** a successful enqueue (`workflow_scheduler.py:~265`). Crash during a fire window → `update_trigger_state` never called → on restart, `next_fire_time <= now` still true → re-fire immediately. **Scope is narrower than the issue implies.**

**O07:** `_VALID_WAL_ENTRY_TYPES` (`bridge_write_adapter.py:43`) = `{"PLAN_START", "WAVE_COMPLETE", "STEP_COMPLETE", "DAG_COMPLETE"}`. `"COMPENSATION_STARTED"` and `"COMPENSATION_COMPLETE"` do not exist anywhere. Today, `_compensate()` (`dag_executor.py:1341`) writes a single `"COMPENSATION"` entry **post-execution only** — this entry type is not in `_VALID_WAL_ENTRY_TYPES` so every write logs a WARNING. `recover_from_wal()` (`dag_executor.py:1460`) has no branch for `COMPENSATION` entries — ignores them entirely. Crash mid-compensation → recovery re-executes compensation steps already completed. Extra surprise: `STEP_COMPLETE` uses `step.id` as the WAL key, not `plan.plan_id` — step-level recovery entries are under different keys.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 5.2.1 | O03: Fix missed-trigger-on-restart — add `last_triggered_at` column to SQLite trigger table; on startup, skip re-fire if `last_triggered_at >= trigger_window_start` | [ ] | **Files:** `k1/orchestrator/workflows/workflow_scheduler.py:~265` (`_fire_trigger`), `IWorkflowStoragePort` and its SQLite adapter. Note: `_last_run` is fiction from STATE.md — it never existed. The real fix is a startup-pass comparing `last_triggered_at` vs expected fire window. **Scope:** S. |
| 5.2.2 | O07-A: Add `"COMPENSATION_STARTED"` and `"COMPENSATION_COMPLETE"` to `_VALID_WAL_ENTRY_TYPES` | [ ] | **File:** `k1/orchestrator/adapters/bridge_write_adapter.py:43`. Also add `"COMPENSATION"` or remove the current invalid write. **Scope:** XS. |
| 5.2.3 | O07-B: Split `_compensate()` single post-execution write into `COMPENSATION_STARTED` (before) + `COMPENSATION_COMPLETE` (after) per step | [ ] | **File:** `k1/orchestrator/orchestration/dag_executor.py:1341`. Two writes per compensation step. **Scope:** S. |
| 5.2.4 | O07-C: Add `COMPENSATION_STARTED` branch to `recover_from_wal()`; build set of already-started step IDs; skip those in `_compensate()` on recovery | [ ] | **File:** `k1/orchestrator/orchestration/dag_executor.py:1460` (`recover_from_wal`). Return already-compensated step set alongside recovery status. **Scope:** S. **Cross-dep:** 5.2.3 must land first. |
| 5.2.5 | O07-D: Fix `STEP_COMPLETE` WAL key inconsistency — currently uses `step.id` as `dag_id`, all others use `plan.plan_id` | [ ] | **File:** `k1/orchestrator/orchestration/dag_executor.py:~957`. This pre-existing inconsistency makes WAL cross-referencing by `plan_id` miss step-level entries. **Scope:** S. Separate from compensation fix but related. |

---

### Epic 5.3 — Orchestrator Planning Quality

**Source issues:** O04, O05, O06

**What the code actually does (traced):**

**O04:** `WorkflowEngine.save_workflow()` (`workflow_engine.py:286`) already reads the WAL via `self._bridge.read_wal(request.committed_plan_id)` and scans for `PLAN_START` entries. The WAL read **exists**. The gap: `WorkflowCompiler.compile()` (`workflow_compiler.py:112`) **always re-validates** capabilities from Fabric registry and re-resolves `DynamicExpr` — no short-circuit path. `WorkflowSpec` (`workflow_types.py:113`) has no `metadata` field to store the cached plan.

**O05:** `RegistryEntry` (`types.py:477`) fields: `name`, `provider_type`, `safety_band_min`, `availability`, `compensation_capability`, `estimated_duration_ms`, `required_inputs`, `output`, `cost_per_call` — **no `intent_tags`**. `find_alternatives()` (`constraint_resolver.py:560`) scores by: schema overlap (hardcoded `0.5` neutral, no schema data), safety band rank, and name Levenshtein similarity. No semantic/intent matching. `schema_score` has a comment: "SCHEMA_OVERLAP_DEFAULT_V1, no schema data in RegistryEntry". `PlanStep` also has no `intent_tags`.

**O06:** HIL condition exact code in `execution_monitor.py:76`:

```python
_OVERRIDE_STEP_THRESHOLD = 3
_OVERRIDE_DURATION_THRESHOLD_MS = 5000
is_significant = (step_count > _OVERRIDE_STEP_THRESHOLD
                  or wave_result.duration_ms > _OVERRIDE_DURATION_THRESHOLD_MS)
```

`CommittedPlan.requires_hitl` does **not exist**. `CommittedPlan` is `frozen=True`.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 5.3.1 | O04-A: Add `metadata: Dict[str, Any]` field to `WorkflowSpec`; store reconstructed `CommittedPlan` in `spec.metadata["committed_plan"]` in `save_workflow()` | [ ] | **Files:** `k1/orchestrator/workflows/workflow_types.py:113`, `k1/orchestrator/workflows/workflow_engine.py:286`. Note: WAL read already exists — this only adds the storage slot and the write into it. **Scope:** S. |
| 5.3.2 | O04-B: Add short-circuit in `WorkflowCompiler.compile()` — if `spec.metadata["committed_plan"]` exists and age < `config.workflow_plan_max_age_ms`, deserialize and return without re-validating | [ ] | **Files:** `k1/orchestrator/workflows/workflow_compiler.py:112`, `k1/orchestrator/config.py` (add `workflow_plan_max_age_ms: int`). **Scope:** S. **Cross-dep:** 5.3.1. |
| 5.3.3 | O05-A: Add `intent_tags: List[str]` to `RegistryEntry` and `PlanStep` | [ ] | **File:** `k1/orchestrator/types.py:477` (`RegistryEntry`) + wherever `PlanStep` is defined. Planner must populate `intent_tags` on each `PlanStep` from the capability's registry entry. **Scope:** S. |
| 5.3.4 | O05-B: Add post-filter in `find_alternatives()` — if step has `intent_tags`, keep only candidates sharing ≥1 tag | [ ] | **File:** `k1/orchestrator/orchestration/constraint_resolver.py:560`. After scoring, filter before top-3 cutoff. **Scope:** XS. **Depends on:** 5.3.3. |
| 5.3.5 | O06-A: Add `requires_hitl: bool = False` to `CommittedPlan`; update `to_dict()`/`from_dict()` | [ ] | **File:** `k1/orchestrator/types.py:882`. `CommittedPlan` is `frozen=True` — adding a default field is safe. Existing WAL entries without the field deserialize to `False`. **Scope:** S. |
| 5.3.6 | O06-B: Thread `requires_hitl` into `DAGExecutor` → `ExecutionMonitor.after_wave()`; replace `is_significant` heuristic | [ ] | **Files:** `k1/orchestrator/orchestration/guards/execution_monitor.py:76`, `k1/orchestrator/orchestration/dag_executor.py`. Replace `step_count > 3 OR duration_ms > 5000` with `ctx.requires_hitl` (or `plan.requires_hitl`). Remove `_OVERRIDE_STEP_THRESHOLD`/`_OVERRIDE_DURATION_THRESHOLD_MS` constants. **Scope:** S. **Depends on:** 5.3.5. |

---

### Epic 5.4 — Orchestrator Isolation + Metrics

**Source issues:** O08, O09, O10

**What the code actually does (traced):**

**O08:** The field is **not `_replan_done: bool`** — actual field is `_replans_used: int`. Lives on two separate guard instances: `MicroReplanCheckpoint` (`micro_replan.py:163`) and `FailureReplanCheckpoint` (`failure_replan.py:72`), each constructed independently by `_build_guards` in `factory.py:~260`, each with `max_replans=1`. Bug: a DAG can get 1 discovery-replan + 1 failure-replan = 2 total, violating ORCH-13's 1-per-DAG limit. `ProcessingContext` (`types.py:1243`) fields: `trace_id`, `request_id`, `tier`, `dag_id`, `workflow_id`, `current_wave`, `current_step_id`, `session_id`, `user_id`, `interrupt_flag` — **no `micro_replan_done`**.

**O09:** `cb_planner`, `cb_orchestrator`, `cb_fabric` are **module-level singletons** at `degradation.py:196–198`, instantiated at import time, in `__all__`. Blast radius: shared across every `OrchestratorService` instance in the same Python process — affects concurrent test runs and multi-tenant deployments. The orchestrator `factory.py` does not reference them (clean), but bootstrap code that imports them from `degradation` bleeds state.

**O10:** `ProactiveGapDetector` (`gap_detector.py`): partial debounce exists — `_DEBOUNCE_SECONDS = 5.0` per **capability name** via `_last_seen` dict. Per-**workflow_id** cooldown absent. `asyncio.Queue` is unbounded (`no maxsize`). `_process_capability` calls `_check_workflow()` sequentially for each affected spec with no `asyncio.Semaphore` — `compiler.compile()` triggers real Fabric registry queries; N workflows affected = N concurrent uncapped queries.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 5.4.1 | O08: Add `micro_replan_done: bool = False` to `ProcessingContext`; change both `MicroReplanCheckpoint` and `FailureReplanCheckpoint` to check/set `ctx.micro_replan_done` instead of separate `_replans_used` counters | [ ] | **Files:** `k1/orchestrator/types.py:1243` (`ProcessingContext`), `k1/orchestrator/orchestration/guards/micro_replan.py:163`, `k1/orchestrator/orchestration/guards/failure_replan.py:72`. Note: OPEN_ISSUES names the field `_replan_done` but actual code uses `_replans_used: int`. Keep per-guard counter for observability; add shared `ctx` flag for global enforcement. **Scope:** S. |
| 5.4.2 | O09: Remove `cb_planner`, `cb_orchestrator`, `cb_fabric` module-level singletons from `degradation.py:196–198`; update `__all__`; document that callers must construct per-service | [ ] | **File:** `k1/orchestrator/degradation.py:196-198`. Verify all import sites — any code doing `from k1.orchestrator.degradation import cb_planner` must be updated to construct locally. Blast radius: same-process state bleed across instances. **Scope:** S. |
| 5.4.3 | O10-A: Add `_last_scan_at: Dict[str, float]` per `workflow_id`; skip `_check_workflow` if `time.time() - _last_scan_at.get(wf_id, 0) < gap_scan_cooldown_s` | [ ] | **File:** `k1/orchestrator/workflows/gap_detector.py`. Note: 5s per-capability debounce (`_last_seen`) already exists — this adds the orthogonal per-workflow_id cooldown. **Scope:** XS. |
| 5.4.4 | O10-B: Add `asyncio.Semaphore(N=5)` around `_check_workflow()` calls in `_process_capability`; make `N` configurable via `OrchestratorConfig` | [ ] | **File:** `k1/orchestrator/workflows/gap_detector.py` (`_process_capability`). Currently sequential but each call fires real Fabric registry queries — N affected workflows = N sequential uncapped queries. **Scope:** XS. |

---

## Milestone 6 — Concierge Completeness

*Goal: narrative context, proactive fills, correct history in WEAVING mode.*

> **Deep-dive status:** All 4 epics fully traced end-to-end. Several skeleton descriptions were wrong — corrected below with exact file/line citations.

---

### Epic 6.1 — Experience Layer Stubs

**Source issues:** C01, C02

**What the code actually does (traced):**

**C01:** Three components in `k1/concierge/experience/`. All have complete dataclasses (`NarrativeContext`, `Anticipation`, `FillMessage`) with correct fields. `ExperienceLayer.tick()` (layer.py) is fully implemented with cadence checks. The stubs are in the three compute methods:

- `NarrativeWeaver.weave()` (`narrative_weaver.py:57-59`): `pass; return NarrativeContext()`. **Note:** skeleton calls the method `.compute()` — actual name is `.weave()`.
- `AnticipatoryResponder.anticipate()` (`anticipatory_responder.py:63-65`): `pass; return Anticipation()`. **Note:** skeleton calls it `.compute()` — actual name is `.anticipate()`. Also: no `__init__`, no LLM port — to be LLM-based requires injecting a model port all the way from `ExperienceLayer.__init__` → FSM controller.
- `ProactiveAgent.generate_fill()` (`proactive_agent.py:63-65`): `pass; return FillMessage()`. **Note:** skeleton says "uses NarrativeWeaver arc" but `layer.py:142` calls `generate_fill(task_state, wait_duration_ms)` — no arc passed. The arc IS computed earlier in `tick()` but never forwarded.

**C02:** Wrong file path in skeleton. Actual file: `k1/concierge/compression/episodic_compressor.py` (not `experience/`). `compress_segment()` is **NOT a stub** — it has a full extractive key-facts implementation (lines ~210-252). The OPEN_ISSUES "first sentence" description is inaccurate. The real gap: `CompressionConfig.compression_strategy` field exists but `compress_segment()` **ignores it entirely** — always runs key-facts path. No `CompressionStrategy.LLM` constant exists. `EpisodicCompressor.__init__` takes no LLM dependency. Also: `EpisodicCompressor` is **never called from `ExperienceLayer`** — it lives in `compression/`, completely decoupled.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 6.1.1 | C01-NW: Implement `NarrativeWeaver.weave()` — theme extraction from conversation history | [ ] | **File:** `k1/concierge/experience/narrative_weaver.py:57-59`. Literal `pass; return NarrativeContext()`. Pure Python, no LLM needed (docstring says 10 ms budget). Count recurring nouns/topics from `conversation_history`. **Note:** method is `weave()` not `compute()` as skeleton says. **Scope:** S. |
| 6.1.2 | C01-AR: Implement `AnticipatoryResponder.anticipate()` — heuristic path (scan `user_patterns` for most recent intent) | [ ] | **File:** `k1/concierge/experience/anticipatory_responder.py:63-65`. Implement heuristic only (no LLM in this issue). **Note:** LLM path requires `__init__(self, llm_port)` + injection from `ExperienceLayer.__init__` → FSM controller — track as separate issue if LLM wanted. **Note:** method is `anticipate()` not `compute()`. **Scope:** XS (heuristic) or M (LLM path). |
| 6.1.3 | C01-PA: Implement `ProactiveAgent.generate_fill()` + pass NarrativeWeaver arc from `layer.py` call site | [ ] | **Files:** `k1/concierge/experience/proactive_agent.py:63-65` (stub), `k1/concierge/experience/layer.py:142` (call site — needs to pass `envelopes.get("narrative")`). Add optional `arc` param to `generate_fill()` signature. Heuristic fill from `task_state` + wait duration. **Scope:** S. |
| 6.1.4 | C02-A: Add `CompressionStrategy.LLM` constant + strategy dispatch branch in `compress_segment()` | [ ] | **File:** `k1/concierge/compression/episodic_compressor.py:~210`. `compress_segment()` is NOT a stub — it has a working key-facts implementation. The gap is: strategy config field exists but is never read. Add `LLM = "llm"` constant, add `if config.compression_strategy == CompressionStrategy.LLM` branch. **Note:** file is `compression/`, not `experience/` as skeleton says. **Scope:** S for dispatch hook; M for full LLM path with async + bus write-back. |
| 6.1.5 | C02-B: Wire `EpisodicCompressor` into the session lifecycle (it is currently never called) | [ ] | **File:** `k1/concierge/compression/episodic_compressor.py`. Currently zero callers from `ExperienceLayer` or FSM. Must decide where to trigger compression (e.g., session end, turn milestone). **Scope:** S (separate from LLM path). |

---

### Epic 6.2 — Concierge Correctness

**Source issues:** C03, C07, C08, C10

**What the code actually does (traced):**

**C03:** Skeleton says "in Back actor" — **WRONG location**. Tool invocation is in `k1/concierge/react/loop.py`. The LLM call **already has** `asyncio.wait_for()` with `_iter_timeout_s`. Tool dispatch does NOT:

- `_run_tool()` closure: `result = await tool_dispatcher.dispatch(tc)` — no timeout
- Sequential loop: `await tool_dispatcher.dispatch(tc)` — no timeout
- `asyncio.gather(*[_run_tool(tc) ...])` — no per-tool timeout
Config field `tool_timeout_ms` is referenced in OPEN_ISSUES but not confirmed present; likely needs adding to concierge config.

**C07:** OPEN_ISSUES says function is in `fsm_controller.py` — **WRONG file**, it's `back.py:1127-1186`. Zero callers confirmed across entire workspace. Function already emits `DeprecationWarning` with removal note. Topics described in OPEN_ISSUES are wrong (says complete/failed; actual: dispatch/cancel/resume/clarification). Companion deprecated functions also need removal: `store_pending_context()` (~line 1088) and `_clear_pending_context()` (~line 1457).

**C08:** OPEN_ISSUES shows a simple `or` expression — actual code is a full `if/else` block (lines 697-745). Primary path uses `resume_context` from SuspensionManager; fallback uses `_get_pending_context(fsm_state, task_id)`. Since `store_pending_context()` is never called in production, `_get_pending_context()` **always returns None**. When None: currently emits `task.failed(NO_PENDING_CONTEXT)` and returns (does NOT crash). Fix changes behavior: raise `SuspensionResolutionNotFound` so FSM can re-surface the HITL request rather than silently failing. `SuspensionResolutionNotFound` does not exist yet.

**C10:** `build_chat_history()` (`react/history.py:54`) filters `entry_type in ("user", "final", "proactive")` — `task_dispatch` entries filtered out. `_extract_scenario_data(PromptMode.WEAVE, ...)` (`front.py:313-357`) does build `results_summary` from pending results (what came back), but the **dispatch-side context** (what was originally asked) is absent. No WEAVE-mode branch exists in `front_handler` or `build_chat_history`.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 6.2.1 | C03: Add `asyncio.wait_for(tool_dispatcher.dispatch(tc), timeout=tool_timeout_s)` in `react/loop.py` for both sequential and `_run_tool` paths | [ ] | **File:** `k1/concierge/react/loop.py` — `_run_tool()` closure and sequential dispatch loop. LLM call already wrapped; only tools are unprotected. Also add `tool_timeout_ms` to concierge config if absent. **Note:** Skeleton's "Back actor" location is wrong — it's `react/loop.py`. **Scope:** S. |
| 6.2.2 | C07: Delete `subscribe_back_events()` (back.py:1127-1186) + `store_pending_context()` (~1088) + `_clear_pending_context()` (~1457) | [ ] | **File:** `k1/concierge/actors/back.py`. Zero callers confirmed. All three functions are in the same deprecated cluster. **Note:** OPEN_ISSUES file location is wrong (says `fsm_controller.py`; actual is `back.py`). Remove in one PR. **Scope:** XS. |
| 6.2.3 | C08-A: Remove `else` fallback block (back.py:723-745) calling `_get_pending_context`; replace with `raise SuspensionResolutionNotFound(task_id)` | [ ] | **File:** `k1/concierge/actors/back.py:697-745`. `_get_pending_context` always returns None in production (its writer `store_pending_context` is deprecated/never called). Currently fails silently to bus. New behavior: raise exception so FSM re-surfaces HITL request. **Scope:** S. |
| 6.2.4 | C08-B: Define `SuspensionResolutionNotFound` exception + add catch-site in FSM controller | [ ] | **Files:** new exception (e.g., `k1/concierge/protocols/exceptions.py`), `k1/concierge/fsm/controller.py` (catch + re-surface HITL). Also remove `_get_pending_context` def (back.py:1398-1413) as follow-on once C08-A is in. **Scope:** S. **Cross-dep:** 6.2.3 lands first. |
| 6.2.5 | C10: In `front_handler`, when `mode == PromptMode.WEAVE`, inject `task_dispatch` history entries for pending task IDs before calling `build_chat_history` | [ ] | **Files:** `k1/concierge/actors/front.py:~787` (call site), `k1/concierge/react/history.py:54` (filter). Add WEAVE-mode conditional: filter `entry_type == "task_dispatch"` entries for task IDs in pending results queue; prepend to message list. `_extract_scenario_data` already builds `results_summary` (what came back) — this adds the dispatch-side context (what was asked). **Scope:** S. |

---

### Epic 6.3 — Crash Recovery Safety

**Source issues:** C04

**What the code actually does (traced):**

**C04:** Skeleton says "projection checks `response.final.v1`" — **WRONG**. Projection (`ledger/recovery.py:221-256`) checks `conversation.weave.emitted` (the `WeaveEmitted` event) to mark delivery. `WeaveEmitted` is written AFTER delivery completes — by the FSM's `_on_response_final` handler. Crash window: if process dies after `_emit_streaming_response` starts but before `_on_response_final` completes and writes `WeaveEmitted` → recovery replays the response → duplicate delivery. `ResponseDelivered` event does not exist anywhere. `ResponseFinalDecided` DOES exist (`events/conversation.py:168`, written at controller.py:3344) as a routing-decision audit record — but it's written after the response arrives at FSM, not before streaming. The ledger is NOT threaded into `front_handler()`; it lives at `fsm._ledger`. The write point must be in `controller.py`'s `_on_response_final` (line ~3330), not in `front.py`.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 6.3.1 | C04-A: Define `ResponseDelivered` event (`conversation.response.delivered.v1`) in `events/conversation.py` | [ ] | **File:** `k1/concierge/events/conversation.py`. Fields: `trace_id`, `response_preview`, `delivery_mode`. Also register in `events/registry.py`. **Note:** `ResponseFinalDecided` already exists as a close cousin — new event must be distinct (written BEFORE streaming). **Scope:** XS. |
| 6.3.2 | C04-B: Write `ResponseDelivered` to ledger as the FIRST action in `_on_response_final` (before streaming/response logic) | [ ] | **File:** `k1/concierge/fsm/controller.py:~3330`. Ledger is accessible here (`self._ledger`). Write `ResponseDelivered` immediately, then proceed with existing `decide_response_final` / streaming logic. **Note:** write must happen here, NOT in `front_handler` (ledger not reachable there). **Scope:** S. **Cross-dep:** 6.3.1. |
| 6.3.3 | C04-C: Update `_derive_fsm_state()` in `ledger/recovery.py:240` to treat `conversation.response.delivered.v1` as proof of delivery (alongside or replacing `conversation.weave.emitted`) | [ ] | **File:** `k1/concierge/ledger/recovery.py:221-256`. Add the new event type to the delivery-detection branch. **Note:** skeleton says "not `response.final.v1`" — correction: current code reads `conversation.weave.emitted` (not a bus topic). New event replaces/augments this check. **Scope:** XS. **Cross-dep:** 6.3.1. |

---

### Epic 6.4 — Config + Runtime Toggles

**Source issues:** C06

**What the code actually does (traced):**

**C06:** `WeavePolicy` (`protocols/weave_policy.py:680`) has `__slots__ = ("_cfg",)` — no mutable `_enabled` flag. `WeavePolicyConfig.enabled: bool = True` exists in `config/loader.py:401` but is static, read at boot only. `WeaveFallbackHandler.safe_decide(..., policy_enabled=True)` exists at `weave_policy.py:1334` and correctly short-circuits on `False` — but the controller (`fsm/controller.py:2507`) calls `self._weave_policy.decide(signal)` directly, never through `safe_decide`, never reading `policy_enabled`. No runtime toggle bus topic exists. `model_hub` has `k1.model_hub.config_update.v1` as a precedent pattern (`model_hub/ports/event_port.py:30`).

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 6.4.1 | C06-A: Add `_enabled: bool` slot + `set_enabled(self, enabled: bool)` to `WeavePolicy`; gate `decide()` to return fallback immediately when `_enabled is False` | [ ] | **File:** `k1/concierge/protocols/weave_policy.py:680`. Add slot, setter, gate. `WeaveFallbackHandler.safe_decide(policy_enabled=...)` already works correctly — just need the state stored on the policy object itself. **Scope:** XS. |
| 6.4.2 | C06-B: Add `TOPIC_CONCIERGE_CONFIG_UPDATE` + `build_config_update()` builder + FSM subscription handler that calls `_weave_policy.set_enabled()` | [ ] | **Files:** `k1/concierge/bus/topics.py` (new topic), `k1/concierge/bus/builders.py` (builder), `k1/concierge/fsm/controller.py` (subscribe + handler). Follow `model_hub` precedent (`model_hub/ports/event_port.py:30`). Payload: `{"weave_policy": {"enabled": bool}}`. **Scope:** S. **Cross-dep:** 6.4.1. |

---

## Milestone 7 — Bus Reliability

*Goal: TTL enforcement, correct sequence tracking, WFQ priority, topic validation.*

> **Deep-dive status:** All 4 epics fully traced end-to-end. Several skeleton descriptions were wrong — corrected below with exact file/line citations.

---

### Epic 7.1 — Envelope Lifecycle

**Source issues:** B01, B02

**What the code actually does (traced):**

**B01:** `ttl_ms: int = 0` and `created_ns: int = 0` exist on `Envelope` (`envelope.py:152-153`). `created_ns` is bus-stamped at `local_bus.py:678`. `_dlq_callback` IS stored on `LocalBus` (line 638) and forwarded to `_AsyncSubscription` (line 829). DLQ callback IS invoked — but **only for handler exception exhaustion** (`_invoke_handler:450-453`), **not for TTL expiry**. No TTL check exists anywhere in dispatch. Sync path (`_dispatch()`) never references `self._dlq_callback` at all. No `TtlExpiredError` defined. No `stats.ttl_drops` counter.
**Note:** Skeleton says method names `_dispatch_sync` / `_dispatch_async` — these do not exist. Actual methods: `_dispatch()` (line 883) for sync, `_invoke_handler()` (line 389) for async.

**B02:** Sequence stamping at `local_bus.py:677` — `self._seq_gen.next(topic)` called **before** middleware chain. Middleware runs at lines 705-718. If middleware drops (returns `None`) at line 718, the sequence number is already consumed and gone forever — creating gaps (e.g. N, N+1, N+3 where N+2 was duplicate-dropped). `_SequenceGenerator` is a per-topic `dict[str, int]` at line 71-100. Fix is a 3-4 line reorder: stamp `sequence=0` before middleware, assign real sequence only after line 718 guard passes.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 7.1.1 | B01-A: Add TTL expiry check in `_dispatch()` (sync path, line 883) — if `ttl_ms > 0` and elapsed > ttl, invoke `self._dlq_callback` and skip delivery | [ ] | **File:** `k1/bus/impl/local_bus.py:883`. Elapsed = `time.monotonic_ns() - envelope.created_ns`. DLQ callback is stored at `self._dlq_callback` but currently never called from sync path. **Note:** Skeleton method name `_dispatch_sync` is wrong — actual is `_dispatch`. **Scope:** S. |
| 7.1.2 | B01-B: Add TTL expiry check in `_AsyncSubscription._invoke_handler()` (async path, line 389) — check elapsed since `created_ns` before calling handler | [ ] | **File:** `k1/bus/impl/local_bus.py:389`. Async path: envelope sits in mailbox; TTL should be checked at dequeue time, not publish time. Use `self._dlq_callback` (already stored on `_AsyncSubscription`). Add `TtlExpiredError` class (near `BackpressureError`) and `BusStats.ttl_drops` counter. **Scope:** S. **Cross-dep:** 7.1.1 (shared `TtlExpiredError`). |
| 7.1.3 | B02: Move `self._seq_gen.next(topic)` from before middleware (line 677) to after the middleware guard (after line 718) | [ ] | **File:** `k1/bus/impl/local_bus.py:676-718`. Stamp `sequence=0` before middleware; assign real sequence only if envelope passes through. Requires one extra `with_bus_fields()` call (frozen dataclass copy — acceptable). **Scope:** XS. |

---

### Epic 7.2 — Backpressure + Observability

**Source issues:** B03, B04, B06

**What the code actually does (traced):**

**B03:** There is ONE `_GapBuffer` instance per bus (not "50 separate `_GapBuffer` objects" as OPEN_ISSUES says). Internal structure: `_expected: dict[str, int]`, `_buffers: dict[str, dict[int, _BufferedEnvelope]]`, `_locks: dict[str, threading.Lock]` in `timing/timing_chain.py:~233`. Per-topic entry cap `_max_per_topic=10_000` exists. `_buffers[topic]` IS cleaned up when a topic drains. `_expected[topic]` and `_locks[topic]` are **NEVER deleted** — one `threading.Lock` + one `int` leak per topic seen. Session with 1000 unique task-id topics = 1000 permanent lock objects. No LRU tracking, no topic-count cap.
**Note:** Skeleton says attribute is `_timing_chain._gap_buffers` — actual attribute is `_gap` (a `_GapBuffer`).

**B04:** The WARNING log at `_AsyncSubscription.enqueue()` (the `except BackpressureError` block) **already has** `subscription_id` and `pattern`. The skeleton's "add `subscription_id` + `pattern` to WARNING log" is **stale/wrong** — they're already there. The real gap: `self._dlq_callback` is NOT invoked in that block (only invoked in retry-exhaustion path ~line 460, not at backpressure drop).

**B06:** `IBus` protocol (`ports/bus.py`) has no `publish_batch`. `LocalBus.publish()` acquires `_rw_lock.acquire_read()` per call — N envelopes = N lock acquisitions. `SessionBusAdapter.emit_batch()` explicitly documents "inherited from IEventPort ABC default implementation" — calls `emit()` in a loop with no shared lock window. No batch path anywhere in `IBus`, `IAsyncBus`, or any adapter.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 7.2.1 | B03: Add `_lru: OrderedDict[str, None]` to `_GapBuffer`; in `_get_lock(topic)` update LRU on access; evict oldest topic (force-release + delete `_expected`/`_locks`/`_buffers` entries) when topic count > 512 | [ ] | **File:** `k1/bus/timing/timing_chain.py:~233` (`_GapBuffer`). Memory leak is in `_expected` + `_locks` dicts — `_buffers` already cleans up empty entries. Cap default 512 topics configurable via `TimingChain` constructor param. **Note:** Skeleton attribute name `_gap_buffers` is wrong — actual attribute is `_gap`. **Scope:** S. |
| 7.2.2 | B04: In `_AsyncSubscription.enqueue()` `except BackpressureError` block — add `self._dlq_callback(envelope, BackpressureError(), attempts=0)` invocation | [ ] | **File:** `k1/bus/impl/local_bus.py:~375-385` (`except BackpressureError` block). `_dlq_callback` is stored and already invoked for retry-exhaustion; just not here. `BackpressureError` already imported. Use `attempts=0` convention (never attempted, dropped at ingress). **Note:** Skeleton says "add `subscription_id` + `pattern` to log" — these are ALREADY in the log. Only the callback invocation is missing. **Scope:** XS. |
| 7.2.3 | B06-A: Add `publish_batch(self, envelopes: list[Envelope]) -> None` to `IBus` Protocol | [ ] | **File:** `k1/bus/ports/bus.py`. Also add to `IAsyncBus` (`ports/async_bus.py`) as a follow-on if async callers need it. **Scope:** XS. |
| 7.2.4 | B06-B: Implement `LocalBus.publish_batch()` — stamp + middleware each envelope in prep loop, then acquire read lock once, match all topics, release, dispatch all outside lock | [ ] | **File:** `k1/bus/impl/local_bus.py`. Currently N envelopes = N `_rw_lock.acquire_read()` calls. Single-lock batch reduces contention. **Scope:** S. **Cross-dep:** 7.2.3. |
| 7.2.5 | B06-C: Override `SessionBusAdapter.emit_batch()` to call `self._bus.publish_batch(...)` with pre-built envelope list | [ ] | **File:** `k1/bus/adapters/session_adapter.py:~240`. Currently calls `emit()` in a loop (explicitly documented as non-atomic in code comment). **Scope:** XS. **Cross-dep:** 7.2.4. |

---

### Epic 7.3 — Topic Validation + Priority

**Source issues:** B07, B08

**What the code actually does (traced):**

**B07:** `TopicValidationMiddleware` is **fully implemented** at `middleware/topic_validation.py:241`. `TopicRegistry` is also fully implemented (line 60). `BusFactory.create_local_ordered()` (line 241, not `create_ordered()` as skeleton says) accepts a `middleware=` param but defaults to `None` — no `TopicValidationMiddleware` is instantiated. "WARNING mode" = the middleware's natural permissive behaviour (logs WARNING, never drops). `DEFAULT_TOPIC_REGISTRY` does not exist anywhere — it must be created. Middleware is only wired in tests.

**B08:** `LocalMailbox` (`impl/local_mailbox.py:62`) has 4 sub-deques `_queues: list[deque]` at line 115, priority routing in `_deliver()` at line 177, and `_try_dequeue()` at line 201-214 — **all exist and work**. The implementation is **strict priority** (URGENT fully drained before REALTIME, etc.) documented as "V1 is STRICT priority" in the docstring. What is missing: per-bucket deficit counter array + quantum weights + round-robin cycle in `_try_dequeue()`. BACKGROUND can starve indefinitely under sustained URGENT load. The skeleton says "implement WFQ with 4 priority buckets" — buckets already exist, only the DRR starvation prevention is absent.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 7.3.1 | B07-A: Create `DEFAULT_TOPIC_REGISTRY` — a `TopicRegistry` pre-registered with all known K1 topics, or empty + registered at kernel boot | [ ] | **File:** new `k1/bus/middleware/default_registry.py` or lazy-init in `factory.py`. Without this, `TopicValidationMiddleware` can't warn on unknown topics. **Scope:** S. |
| 7.3.2 | B07-B: In `BusFactory.create_local_ordered()`, inject `TopicValidationMiddleware(DEFAULT_TOPIC_REGISTRY)` as default middleware when `middleware=None` | [ ] | **File:** `k1/bus/factory.py:241`. **Note:** Skeleton says `create_ordered()` — correct name is `create_local_ordered()`. Optionally mirror in `create_local()`. Must not break `create_for_testing()` which wires its own middleware. **Scope:** XS. **Cross-dep:** 7.3.1. |
| 7.3.3 | B08: Add per-bucket deficit counter array to `LocalMailbox.__slots__` + configurable quantum weights to `MailboxConfig`; rewrite `_try_dequeue()` for Deficit Round-Robin | [ ] | **File:** `k1/bus/impl/local_mailbox.py:~201` (`_try_dequeue`), `k1/bus/ports/mailbox.py` (`MailboxConfig` — add `wfq_quantum: tuple[int,int,int,int]` optional field). 4 deques already exist. Add `_deficit: list[int]` (4 values) + `_quantum: tuple` to `__init__`. Round-robin: each round, increment `_deficit[i] += _quantum[i]`; serve from bucket i while `_deficit[i] > 0`; decrement on each dequeue. **Note:** Skeleton says "implement WFQ with 4 buckets" — buckets already exist; only deficit tracking is missing. Existing strict-priority tests must be audited. **Scope:** M. |

---

### Epic 7.4 — Rust Bus Benchmark

**Source issues:** B05

**What the code actually does (traced):**

**B05:** `RustBusAdapter` exists at `impl/rust_bus_adapter.py:1` (full class). `LocalBus` exists at `impl/local_bus.py:1`. No benchmark file exists anywhere under `tests/k1/bus/` or `k1/bus/`. `pyproject.toml` has pytest config but no benchmark section. OPEN_ISSUES.md specifies target: `tests/k1/bus/bench_roundtrip.py`.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 7.4.1 | B05: Create `tests/k1/bus/bench_roundtrip.py` — K1-realistic benchmark: 10 subscribers, 20 topics, mixed payload sizes (64B/1KB/8KB); measure `publish()` latency for `LocalBus` vs `RustBusAdapter` (skip if `k1_bus_core` unavailable); add pytest-benchmark or `timeit`-based assertions to CI | [ ] | **File:** new `tests/k1/bus/bench_roundtrip.py`. Both bus classes exist and are ready to benchmark. No production code changes needed. Add `pytest-benchmark` to `pyproject.toml` optional-deps or use plain `timeit`. `RustBusAdapter` should be skipped gracefully when native module absent. **Scope:** S (pure new file). |

---

## Milestone 8 — Model Hub Production Grade

*Goal: cost tracking, correct streaming, provider resilience, rate limiting correctness.*

> **Deep-dive status:** All 3 epics fully traced end-to-end. M08, M03, and M05 are already fixed in code — OPEN_ISSUES.md is stale. Corrected below with exact file/line citations.

---

### Epic 8.1 — LLM Call Correctness

**Source issues:** M06, M08, M09

**What the code actually does (traced):**

**M08 — ALREADY FIXED (skeleton is wrong):** `ollama_plugin.py:249-267` already has:

```python
if isinstance(args, dict):
    args_str = json.dumps(args)
elif isinstance(args, str):
    args_str = args
```

The guard is present with an explicit comment. OPEN_ISSUES.md was written before the fix landed. **Nothing to do.**

**M06 — CONFIRMED:** `GooglePlugin.stream_execute()` at `google_plugin.py:188-196` contains:

```python
all_chunks = await loop.run_in_executor(
    None,
    lambda: list(generate_content_stream(...))  # ← materializes ENTIRE stream
)
```

`list()` forces every chunk out of the SDK iterator inside the executor thread before any yields happen. The caller receives zero chunks until full generation completes.

**M09 — CONFIRMED — three-layer bug:**

- `request_router.py:388` hardcodes `usage=TokenUsage()` in the done-chunk branch, discarding `chunk.metadata` entirely — **this is the root**. Even if all plugins emitted perfect usage, the router throws it away.
- **OpenAI** (`openai_plugin.py:133`): `stream_options: {"include_usage": True}` is set, but OpenAI sends usage in a final chunk where `choices: []` — this chunk is skipped by `if not choices: continue`. Usage never reaches `ProviderChunk`.
- **Anthropic** (`anthropic_plugin.py:~158`): `message_delta` event writes `metadata={"usage": chunk_data.get("usage", {})}` (partial — only output tokens). `input_tokens` from the `message_start` event are never captured.
- **Google** (`google_plugin.py:~240`): `_normalize_response()` (non-streaming) extracts `usage_metadata` but the streaming chunk loop never reads it on the done-chunk.
- `ProviderChunk` in `plugins/base.py:76-82` has no typed usage fields — usage floats through `metadata: Dict[str, Any]` with no schema.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 8.1.1 | M08: CLOSE — already fixed in `ollama_plugin.py:249-267` | [x] | `isinstance(args, dict): json.dumps(args)` guard exists with comment. OPEN_ISSUES.md stale. Mark closed. |
| 8.1.2 | M06: Replace `lambda: list(generate_content_stream(...))` with asyncio.Queue bridge in `GooglePlugin.stream_execute()` | [ ] | **File:** `k1/model_hub/plugins/google_plugin.py:188-196`. Thread worker puts each SDK chunk into a `queue.Queue`; async generator reads via `loop.run_in_executor` or `call_soon_threadsafe`. Chunk-parsing loop (lines 203-248) stays identical. **Scope:** S. |
| 8.1.3 | M09-A: Add typed `prompt_tokens: int = 0` and `completion_tokens: int = 0` fields to `ProviderChunk` in `plugins/base.py` | [ ] | **File:** `k1/model_hub/plugins/base.py:76-82`. Standardize how usage crosses plugin→router boundary (typed fields cleaner than `metadata` dict). **Scope:** XS. |
| 8.1.4 | M09-B: Fix per-plugin usage extraction — OpenAI: remove `if not choices: continue` guard for usage-only final chunk; Anthropic: capture `input_tokens` from `message_start` event; Google: read `chunk.usage_metadata` on done-chunk | [ ] | **Files:** `k1/model_hub/plugins/openai_plugin.py:133`, `k1/model_hub/plugins/anthropic_plugin.py:~120`, `k1/model_hub/plugins/google_plugin.py:~240`. Each plugin populates `ProviderChunk.prompt_tokens`/`completion_tokens` on the final streaming chunk. **Scope:** S. **Cross-dep:** 8.1.3 must land first. |
| 8.1.5 | M09-C: Replace `usage=TokenUsage()` hardcode with usage read from final `chunk` in `request_router.py:388` | [ ] | **File:** `k1/model_hub/services/request_router.py:388` (`stream_route()` done-chunk branch). This is the mandatory prerequisite fix — even with per-plugin fixes, the router discards all usage. **Scope:** XS. **Cross-dep:** 8.1.3 + 8.1.4 should land first. |

---

### Epic 8.2 — Rate Limiter + Circuit Breaker Correctness

**Source issues:** M03, M05

**What the code actually does (traced):**

**M03 — ALREADY FIXED (skeleton is wrong):** `rate_limiter.py:~196-218` already implements two-phase check:

```python
rpm_ok = rate.rpm_bucket.available >= 1
tpm_ok = rate.tpm_bucket.available >= tokens_needed
if rpm_ok and tpm_ok:
    rate.rpm_bucket.try_consume(1)
    rate.tpm_bucket.try_consume(tokens_needed)
```

Docstring says *"Both must succeed or neither is consumed."* Fix landed before this audit.

**M05 — ALREADY FIXED (skeleton is wrong):** `circuit_breaker_manager.py:~148-162` already has:

```python
if circuit and state == CircuitState.HALF_OPEN:
    if circuit.half_open_in_flight:
        return CircuitState.OPEN  # ← guard is present
    circuit.half_open_in_flight = True
```

**Note:** OPEN_ISSUES.md calls the field `half_open_probe_in_flight`; actual field name is `half_open_in_flight`. Documentation drift only.

**NEW FINDING — Thread-safety gap (not in skeleton):** Both `RateLimiter` and `CircuitBreakerManager` lack `threading.Lock` around their check-then-consume sequences. Two concurrent threads (asyncio + thread-pool executor) can both pass the check before either consumes, causing overdraft. Neither M03 nor M05 covers this.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 8.2.1 | M03: CLOSE — two-phase check already implemented at `rate_limiter.py:~196-218` | [x] | Skeleton describes pre-fix behavior. Mark closed in OPEN_ISSUES.md. |
| 8.2.2 | M05: CLOSE — `half_open_in_flight` guard already implemented at `circuit_breaker_manager.py:~154` | [x] | Skeleton describes pre-fix behavior. Note field name drift: OPEN_ISSUES says `half_open_probe_in_flight`, code uses `half_open_in_flight`. Mark closed. |
| 8.2.3 | NEW — M03a: Add `threading.Lock` to `RateLimiter` around check-then-consume sequence | [ ] | **File:** `k1/model_hub/services/rate_limiter.py`. True concurrent access from asyncio + thread-pool executor can overdraft both buckets despite the logical two-phase check. **Scope:** S. |
| 8.2.4 | NEW — M05a: Add `threading.Lock` to `CircuitBreakerManager` around `get_state()` + `acquire()` TOCTOU | [ ] | **File:** `k1/model_hub/services/circuit_breaker_manager.py`. Same thread-safety gap — two threads can both see HALF_OPEN and both set `half_open_in_flight = True` in the window between the check and the set. **Scope:** S. |

---

### Epic 8.3 — Cache + Registry

**Source issues:** M02, M04, M07, M10

**What the code actually does (traced):**

**M02:** `audit_logger.py:62` — `self._records: List[AuditRecord] = []`. Appended unconditionally at lines 101 (`log()`) and 138 (`log_error()`). No `deque`, no `maxlen`, no import of `collections`. `records` property returns `list(self._records)`.

**M04:** `response_cache.py:141` — `repr(payload)` used in `key_parts` verbatim. No `json`, no `dataclasses.asdict`, no version constant. Non-deterministic across Python interpreter runs; different dataclass instances with same values may produce different keys.

**M07:** `provider_registry.py:93` — `_capability_index` defined. Full `_rebuild_capability_index()` called in both `register()` (line 128) and `unregister()` (line 144). The rebuild at line 249-258 iterates ALL registered providers every time. Hot-startup with N providers = N full rebuilds.

**M10:** `loader.py:214-215` — `return ("skipped", f"env var {env_var!r} not set")` on missing credentials. Zero bus emission, zero WARNING log — completely silent. `TOPIC_PROVIDER_REGISTERED` exists in `events.py:39`. `ProviderRegisteredPayload` (`events.py:140-144`) has only `provider_id`, `capabilities`, `model_count` — no `status` or `reason` fields. `ProviderLoader.__init__` (loader.py:106-112) has no `event_port` param — only `self._hub`. Full event emission blocked until M01 (event_port wiring) is done.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 8.3.1 | M02: Replace `self._records: List[AuditRecord] = []` with `deque(maxlen=10_000)` | [ ] | **File:** `k1/model_hub/services/audit_logger.py:62`. Add `from collections import deque`. Change init and both `append` call-sites are unchanged. `records` property already returns `list(self._records)` — no callers break. **Scope:** XS. |
| 8.3.2 | M04: Replace `repr(payload)` with `json.dumps(dataclasses.asdict(payload), sort_keys=True)` + `_CACHE_KEY_VERSION = "v1"` prefix | [ ] | **File:** `k1/model_hub/services/response_cache.py:141`. Add `import dataclasses, json`. Define module-level `_CACHE_KEY_VERSION = "v1"`. Prepend version to `key_parts`. **Note:** Changes existing cache key format — will bust in-flight cache entries in staging (acceptable, expected). **Scope:** XS. |
| 8.3.3 | M07: Replace `_rebuild_capability_index()` call in `register()` with incremental `setdefault(cap, []).append(info)` loop over new provider's capabilities only | [ ] | **File:** `k1/model_hub/services/provider_registry.py:128` (`register()`) and `249-258` (`_rebuild_capability_index()`). Keep full rebuild for `unregister()` path (rare). `get_capability_index()` returns defensive copies — no external mutation issues. **Scope:** S. |
| 8.3.4 | M10-A: Add `logger.warning("ProviderLoader: skipping %s — %s", ...)` at `loader.py:214-215` minimum | [ ] | **File:** `k1/model_hub/loader.py:214`. XS standalone fix, no M01 dependency. Makes silent skips visible in logs immediately. **Scope:** XS. |
| 8.3.5 | M10-B: Add `status: str = "registered"` and `reason: str = ""` to `ProviderRegisteredPayload`; add `event_port` param to `ProviderLoader`; emit `TOPIC_PROVIDER_REGISTERED` with `status="skipped"` on credential-missing skip | [ ] | **Files:** `k1/model_hub/events.py:140-144`, `k1/model_hub/loader.py:106-112` + skip branch at line 149, `k1/model_hub/factory.py` (thread `event_port` to loader). **Note:** Full bus emission requires M01 (event_port wired in `from_config`) — do M10-A first as minimum; add this after M01. **Scope:** S. **Cross-dep:** M01 (issue 3.1.3). |

---

## Milestone 9 — SessionState Production Grade

*Goal: FlatBuffer correctness, lock ordering safety, mutation audit trail.*

> **Deep-dive status:** All 4 epics fully traced end-to-end. Every file in `k1/sessionstate/` read completely.
> Several skeleton descriptions were inaccurate — corrected below with exact file/line citations.
> Multiple new issues found (security, audit pre-requisite, new serialization gaps).

---

### Epic 9.1 — Serialization Correctness

**Source issues:** SS-01

**What the code actually does (traced):**

FlatBuffer generated bindings **already exist** for both sections — the schemas were compiled. The section classes simply never use them.

**`task_state.py:172-192`:**

```python
def to_flatbuffer(self) -> bytes:
    """Serialize to JSON bytes (POC -- no FlatBuffer schema for task_state)."""
    payload = {"section": self.SECTION_NAME, "tasks": [asdict(t) for t in self._tasks.values()], ...}
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")
```

The docstring says "no FlatBuffer schema" — **this is wrong**. `generated/flatbuffers/K1/SessionState/TaskStateSection.py` and `TaskStateEntry.py` (all 11 fields including `PendingHilData`) exist with full builder code. Neither is imported by `task_state.py`.

**`task_artifacts.py:140-168`:** Same pattern — JSON stub, docstring says "POC". `generated/flatbuffers/K1/SessionState/TaskArtifactsSection.py` and `TaskArtifactEntry.py` exist and are unused.

**NEW — `artifacts_warm.py:87-101`:** A third section with identical JSON stub not mentioned in the skeleton. `ArtifactsWarmSection.py` generated bindings exist.

**NEW — `TaskStateEntry.py` codegen bug:** `generated/flatbuffers/K1/SessionState/TaskStateEntry.py:180-182` has triple `return builder.EndObject()` — two unreachable dead-code lines. Harmless at runtime (first return executes) but signals file corruption.

**NEW — `pending_hil_data` schema mismatch:** In the Python dataclass, `pending_hil_data: Optional[Dict[str, Any]]` is a nested dict. In the generated FlatBuffer schema, `PendingHilData` is typed as a **string** offset. When SS-01 is implemented, the dict must be `json.dumps()`-serialized into the FlatBuffer string field (same pattern as `control.py:~838` for similar fields).

**Section inventory — which sections use real FlatBuffers vs JSON:**

| Section | Serialization | Generated bindings used? |
|---|---|---|
| `affective_now`, `beliefs_active`, `beliefs_history`, `clarifications`, `control`, `history_active`, `history_recent`, `meta`, `narrative_active`, `persona`, `scoreboard`, `telemetry` | ✅ Real FlatBuffer | Yes |
| **`task_state`** | ❌ JSON stub | Generated exists, not imported |
| **`task_artifacts`** | ❌ JSON stub | Generated exists, not imported |
| **`artifacts_warm`** | ❌ JSON stub | Generated exists, not imported |
| `temporal_context` | N/A (pure computation, no storage) | — |

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 9.1.1 | SS-01-A: Wire `TaskStateSection.py` / `TaskStateEntry.py` generated builders into `task_state.py` `to_flatbuffer()` / `from_flatbuffer()` | [ ] | **File:** `k1/sessionstate/sections/task_state.py:172`. Generated builders at `k1/sessionstate/generated/flatbuffers/K1/SessionState/TaskStateSection.py` + `TaskStateEntry.py`. Follow `beliefs_active.py` pattern. `pending_hil_data` must be `json.dumps()`-serialized to string before writing to FlatBuffer (schema types it as string). **Scope:** S (~100 lines). |
| 9.1.2 | SS-01-B: Wire `TaskArtifactsSection.py` / `TaskArtifactEntry.py` generated builders into `task_artifacts.py` | [ ] | **File:** `k1/sessionstate/sections/task_artifacts.py:140`. Same pattern as 9.1.1. Generated bindings: `k1/sessionstate/generated/flatbuffers/K1/SessionState/TaskArtifactsSection.py` + `TaskArtifactEntry.py`. **Scope:** S (~80 lines). |
| 9.1.3 | NEW — SS-01-C: Wire `ArtifactsWarmSection.py` generated builders into `artifacts_warm.py` | [ ] | **File:** `k1/sessionstate/sections/artifacts_warm.py:87`. Third JSON-stub section not in skeleton. **Scope:** XS (~60 lines). |
| 9.1.4 | NEW — SS-GEN-01: Remove two unreachable `return builder.EndObject()` lines in `TaskStateEntry.py` | [ ] | **File:** `k1/sessionstate/generated/flatbuffers/K1/SessionState/TaskStateEntry.py:181-182`. Dead code lines 181 and 182 — only the first `return` at line 180 executes. **Scope:** XS (delete 2 lines). |

---

### Epic 9.2 — Concurrency Safety

**Source issues:** SS-03

**What the code actually does (traced — every lock found):**

Full lock inventory:

| Lock | Type | File:Line | Protects |
|---|---|---|---|
| `DirectWriterAdapter._lock` | `threading.RLock` | `adapters/direct_writer.py:125` | mutation stats, turn stats, entire `request_mutation()` body |
| `SessionStateManager._write_lock` | `threading.RLock` | `manager.py:526` | all mutations, lifecycle state |
| `MutationGuard._lock` | `threading.Lock` (NOT RLock) | `guard.py:327` | `_emergency_mode` + `_locked_sections` |
| `LocalEventAdapter._lock` | `threading.RLock` | `adapters/local_events.py:88` | handlers dict, subscriptions, captured events |
| `StandaloneLifecycle._lock` | `threading.RLock` | `adapters/standalone_lifecycle.py:162` | lifecycle state machine transitions |
| `MetricsCollector._lock` | `threading.RLock` | `metrics.py:218` | metrics dict |

No `asyncio.Lock` or `asyncio.Semaphore` anywhere. `AsyncSSMBridge` uses `asyncio.to_thread` to offload the sync RLock-holding methods.

**Actual lock acquisition order (traced call-by-call through `request_mutation()`):**

```
Thread enters DirectWriterAdapter.request_mutation()
  → acquire DWA._lock (RLock)                      [direct_writer.py:218]
    → guard.preflight()
        → acquire + release guard._lock             [guard.py:407]
    → manager.mutate()
        → acquire SSM._write_lock (RLock)           [manager.py:842]
          → guard.preflight() [AGAIN]
              → acquire + release guard._lock        [guard.py:407]
          → eviction_engine.evict()
              → guard.lock_section()
                  → acquire + release guard._lock   [guard.py:583]
  → release SSM._write_lock
→ release DWA._lock
```

**Effective order: `DWA._lock → SSM._write_lock → guard._lock`**

**Skeleton lock name is wrong:** OPEN_ISSUES.md calls the guard's lock `_section_lock` — **actual name is `_lock`** (`guard.py:327`).

**Latent deadlock risk:** `LocalEventAdapter._dispatch_loop` calls event handlers outside `LocalEventAdapter._lock` (`local_events.py:187-198`). If any subscriber to `MutationApprovedEvent` (once that event is emitted — see Epic 9.3) calls `DirectWriterAdapter.request_mutation()`, the dispatch thread would deadlock on `DWA._lock` which is still held by the original caller. Currently safe only by convention.

**Double-preflight TOCTOU:** `preflight()` called at `direct_writer.py:302` (before `SSM._write_lock`) and again inside `manager.mutate()` (after `SSM._write_lock`). Between the two calls, another thread can change `_emergency_mode` or `_locked_sections`. The second call is authoritative; the first is wasted and can approve what the second rejects. `SizeTracker` reads in the first `preflight()` are also not under `SSM._write_lock` — stale capacity data possible (GIL-safe today; breaks under nogil CPython / PyPy STM).

**`MutationGuard._lock` is plain `Lock` (non-reentrant):** All other locks in the module are `RLock`. The asymmetry is undocumented — any future `MutationGuard` method holding `_lock` that calls another guarded method would deadlock.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 9.2.1 | SS-03-A: Add lock-order assertion comment block at top of `manager.py` and `direct_writer.py`; correct OPEN_ISSUES `_section_lock` → `_lock` | [ ] | **Files:** `k1/sessionstate/manager.py:1`, `k1/sessionstate/adapters/direct_writer.py:1`, `k1/sessionstate/OPEN_ISSUES.md`. Document enforced order: `DWA._lock → SSM._write_lock → guard._lock`. **Scope:** XS. |
| 9.2.2 | NEW — SS-03-B: Add `threading.RLock()` debug assertion before `SSM._write_lock` acquisition to detect future reverse-order attempts | [ ] | **File:** `k1/sessionstate/manager.py:842` (top of `mutate()`). Assert that `DWA._lock` is NOT held by this thread at entry to `mutate()` — prevents future event-handler callers from introducing reverse nesting. Note: requires threading inspection helper or sentinel. **Scope:** S. |
| 9.2.3 | NEW — SS-03-C: Change `MutationGuard._lock` from `threading.Lock` to `threading.RLock` for consistency; add comment explaining why all module locks are RLock | [ ] | **File:** `k1/sessionstate/guard.py:327`. No current callers nest guard lock calls, so behavioral change is zero today — this is a defensive maintenance fix. **Scope:** XS. |
| 9.2.4 | NEW — SS-03-D: Eliminate first (pre-`mutate()`) `guard.preflight()` call in `DirectWriterAdapter.request_mutation()` or demote it to a non-locking estimate | [ ] | **File:** `k1/sessionstate/adapters/direct_writer.py:302`. First preflight reads stale capacity and adds lock overhead without atomicity guarantee. The authoritative check is inside `mutate()`. Options: remove entirely, or replace with a non-locking size estimate. **Scope:** S. |

---

### Epic 9.3 — Audit + Rate Protection

**Source issues:** SS-04, SS-06

**What the code actually does (traced):**

**`MutationApprovedEvent` is defined but never emitted — blocker for SS-04:**

- **Defined:** `events.py:147` — `@dataclass` with fields `section`, `operation`, `previous_size_bytes`, `new_size_bytes`, `tier_utilization_pct`, `total_utilization_pct`
- **Factory helper:** `events.py:376-392` — `EventFactory.make_mutation_approved(...)`
- **Supposed to be emitted:** `manager.py:839` — docstring lists it as step 8 of `mutate()` flow
- **Actually emitted:** NEVER. `_safe_emit()` in `manager.py` is called only for `EVICTION_TRIGGERED`, `EVICTION_COMPLETED`, `EMERGENCY_ACTIVATED`. The success path of `mutate()` (~lines 920-940) returns `MutationResult(success=True, ...)` with zero `_safe_emit` calls. **SS-04 has no trigger point until this is fixed.**

**No mutation audit log exists anywhere:**

`SQLiteStorageAdapter._init_schema()` (`adapters/sqlite_storage.py:145-220`) creates 4 tables: `st_session_checkpoints`, `st_beliefs_archive`, `st_history_archive`, `st_narrative_archive`. No `st_mutation_audit`. `local_cold.py` has 7 tables — none is a mutation audit log. `_mutation_count` in `manager.py` is an in-memory counter that resets on restart.

**`MutationGuard` has zero rate limiting:**

`MutationGuard.__slots__` = `("_ss_cfg", "_size_tracker", "_emergency_mode", "_locked_sections", "_lock")`. No `_rate_limiter`, `_token_buckets`, or `_last_write_times`. `preflight()` checks: section existence → operation type → section lock → emergency mode → capacity (section/tier/total). **No rate check at any step.** A caller can hammer at 100k/s with only `SSM._write_lock` as a natural throttle.

**`SessionStateConfig` has no rate fields:**

Top-level sub-configs: `tiers`, `eviction`, `migration`, `thrash`, `reconstruction`, `cold`, `storage`, `flatbuffer_overhead_factor`, `llm_writable_sections`. No `rate_limit`, no `RateLimitConfig`.

**`writer_id` accepted but never enforced:**

`MutationRequest.writer_id` is accepted in the port protocol and stored in `MutationResult`. `MutationGuard.preflight()` receives it but never validates it against an allow-list. Any caller can pass `writer_id="llm"` or any arbitrary string — the ADR-0017g "Concierge-only writes" rule has no runtime enforcement.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 9.3.1 | NEW — SS-04-PRE: Emit `MutationApprovedEvent` in `manager.mutate()` success path | [ ] | **File:** `k1/sessionstate/manager.py:~935` (after `MutationResult(success=True, ...)` branch). Call `_safe_emit(EventType.MUTATION_APPROVED.value, EventFactory.make_mutation_approved(...))`. `ctx.writer_id`, `ctx.section`, `ctx.operation`, `ctx.delta_bytes` all in scope. **Must land before SS-04 — this is the trigger point.** **Scope:** XS. |
| 9.3.2 | SS-04: Add `st_mutation_audit` table to `SQLiteStorageAdapter._init_schema()`; subscribe `on_mutation_approved` handler; INSERT row; keep rolling 1000 | [ ] | **File:** `k1/sessionstate/adapters/sqlite_storage.py:145`. New table schema: `(rowid INTEGER PRIMARY KEY AUTOINCREMENT, section TEXT, operation TEXT, writer_id TEXT, delta_bytes INTEGER, timestamp_ms INTEGER)`. Subscribe handler in `StandaloneLifecycle`. Rolling trim: `DELETE FROM st_mutation_audit WHERE rowid NOT IN (SELECT rowid FROM st_mutation_audit ORDER BY rowid DESC LIMIT 1000)`. **Cross-dep:** 9.3.1 must land first. **Scope:** S. |
| 9.3.3 | SS-06-A: Add `RateLimitConfig` sub-dataclass to `SessionStateConfig` with `max_mutations_per_second: int = 0` (0 = disabled) | [ ] | **File:** `k1/sessionstate/config.py`. Add after `ThrashConfig`. Default 0 = no limit for backward compat. **Scope:** XS. |
| 9.3.4 | SS-06-B: Add `_token_buckets: Dict[str, _TokenBucket]` to `MutationGuard.__slots__`; add rate check as CHECK 0 in `preflight()` keyed by `writer_id` | [ ] | **File:** `k1/sessionstate/guard.py:325` (`__slots__`), `:360` (preflight entry). Per-writer bucket: capacity=`config.rate_limit.max_mutations_per_second`, refill per second. Check before section-existence validation (fail-fast). Only active when `config.rate_limit.max_mutations_per_second > 0`. **Scope:** S. |
| 9.3.5 | NEW — SS-06-C: Add `writer_id` allow-list validation as CHECK 0.5 in `MutationGuard.preflight()` | [ ] | **File:** `k1/sessionstate/guard.py`. Validate `request.writer_id` against `_ss_cfg.llm_writable_sections` or a separate `allowed_writers: List[str]` config field. Unknown writer_ids → `MutationRejected(reason=UNKNOWN_WRITER)`. Enforces ADR-0017g at runtime. **Scope:** S. **Cross-dep:** Add `allowed_writers` field to `SessionStateConfig` first. |

---

### Epic 9.4 — Infrastructure + Test Correctness

**Source issues:** SS-05, SS-07, SS-08, SS-09, SS-10

**What the code actually does (traced):**

**SS-05:** Zero file-locking (`fcntl`, `filelock`, `portalocker`) anywhere in `k1/sessionstate/`. `k1/coordination/sessionstate_concurrency/` is an **empty stub package**. `SessionStateManager` uses `threading.RLock` — intra-process only. `WIRING.md` calls `create_standalone()` "single-process prod" — documentation only, no enforcement.

**SS-07:** `LocalEventAdapter._event_queue` at `adapters/local_events.py:82`:

```python
self._event_queue: queue.Queue[Tuple[str, Any]] = queue.Queue()  # no maxsize
```

`emit()` at line 112 uses `.put()` (blocking), **not** `.put_nowait()`. OPEN_ISSUES.md suggests a drop path might exist — **it does not**. No `_drop_count` attribute, no `queue.Full` handler anywhere. A slow dispatch thread blocks the caller entirely rather than dropping.

**SS-08:** `SectionDataAdapter._overflow: Dict[str, List[MigrationItem]]` at `adapters/section_data_adapter.py:57`. `add_items()` at lines 230-243 does unconditional `bucket.append(item)` with no cap. Three drain paths exist (`clear_section()`, `remove_evicted_data()`, `remove_items()`), but none is called on migration-target failure. `_overflow` byte sizes are **never reported to `SizeTracker`** — capacity checks in `MutationGuard` can approve mutations that push actual heap usage above the configured limit.

**SS-09:** `StandaloneLifecycle.checkpoint()` docstring lists step 4 as "Reschedule timer if periodic." The code at lines ~530-615 does NOT do this — it updates `_last_checkpoint_ms` and `_checkpoint_count` then returns. Timer reschedule only happens inside `checkpoint_tick()` (line ~644), which calls `self._start_checkpoint_timer()` after the periodic-triggered checkpoint. A manual checkpoint does not reset the countdown — the periodic timer fires at its original deadline regardless of how recent the manual one was.

**SS-10:** `InMemoryStorageAdapter` has `clear()` at `adapters/memory_storage.py:255-262`:

```python
def clear(self) -> None:
    """Clear all stored data. Call between tests for isolation."""
    self._archives.clear()
    self._metadata.clear()
```

Per-instance dicts → two tests creating separate instances are isolated by default. `clear_all()` does NOT exist (only `clear()`). `HotTier` and `WarmTier` both expose `clear_all()` — naming inconsistency.

**NEW — SECURITY: `SectionDataAdapter` uses `pickle` fallback:**

`adapters/section_data_adapter.py:78-88`:

```python
try:
    return pickle.dumps(sec)
except Exception: ...
```

If any section holds user-controlled content and is later deserialized via `restore()`, `pickle.loads()` is a **remote code execution vector**. This fallback must be removed or replaced with a safe serializer.

**NEW — `LocalEventAdapter._running` written without lock:**

`stop()` sets `self._running = False` without acquiring `_lock`. The `_dispatch_loop` reads it in a `while self._running` loop. GIL-safe on CPython; memory visibility bug under PyPy or nogil builds. Fix: set `_running = False` inside `with self._lock`.

**NEW — `LocalEventAdapter` has no `__del__` / context manager:**

If garbage-collected without `stop()`, the daemon thread continues dispatching to potentially-collected handlers. Class should implement `__enter__`/`__exit__` or `__del__` calling `stop()`.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 9.4.1 | SS-05: Add `fcntl.flock` (or `portalocker` on Windows) on SQLite DB path in `StandaloneLifecycle.start()`; document constraint in `SessionStateFactory.create_standalone()` | [ ] | **File:** `k1/sessionstate/adapters/standalone_lifecycle.py` (`start()` method). Acquire exclusive lock on `{db_path}.lock` file at start; release in `stop()`. On Windows use `portalocker` (already in requirements or add it). Document the single-process invariant in `factory.py` docstring. **Scope:** S. |
| 9.4.2 | SS-07-A: Change `LocalEventAdapter._event_queue` to `queue.Queue(maxsize=N)` with configurable `N` via constructor | [ ] | **File:** `k1/sessionstate/adapters/local_events.py:82`. Add `max_queue_size: int = 1000` to `__init__`. **Scope:** XS. |
| 9.4.3 | SS-07-B: Change `emit()` from `.put()` to `.put_nowait()` with `try/except queue.Full` that logs WARNING and increments `self._drop_count` | [ ] | **File:** `k1/sessionstate/adapters/local_events.py:112`. `.put()` blocks the caller if queue is full — defeating the entire purpose of a drop policy. **Scope:** XS. **Cross-dep:** 9.4.2 must land first (no `maxsize` → `queue.Full` never raised). |
| 9.4.4 | SS-08-A: Add `max_overflow_bytes: int` cap in `SectionDataAdapter.add_items()`; drain oldest items before accepting new ones when cap exceeded | [ ] | **File:** `k1/sessionstate/adapters/section_data_adapter.py:230`. When `sum(item.size_bytes for item in bucket) >= max_overflow_bytes`, evict oldest items from front of deque before appending. **Scope:** S. |
| 9.4.5 | SS-08-B: Report `_overflow` byte sizes to `SizeTracker` so `MutationGuard` capacity checks see the true heap usage | [ ] | **File:** `k1/sessionstate/adapters/section_data_adapter.py`. `SizeTracker.update(section, delta_bytes)` call when overflow grows/shrinks. **Scope:** S. |
| 9.4.6 | SS-09: In `StandaloneLifecycle.checkpoint()`, after successful write, cancel and reschedule the periodic timer when trigger is `MANUAL` | [ ] | **File:** `k1/sessionstate/adapters/standalone_lifecycle.py:~600` (after `_last_checkpoint_ms` update). Add: `if trigger != CheckpointTrigger.PERIODIC and self._config.checkpoint_interval_ms > 0: self._cancel_checkpoint_timer(); self._start_checkpoint_timer()`. Fix the misleading step-4 docstring. **Scope:** XS. |
| 9.4.7 | SS-10: Add `clear_all()` as alias for `clear()` in `InMemoryStorageAdapter` | [ ] | **File:** `k1/sessionstate/adapters/memory_storage.py:255`. One-line alias: `clear_all = clear`. Aligns with `HotTier.clear_all()` and `WarmTier.clear_all()` naming convention. **Scope:** XS. |
| 9.4.8 | NEW — SECURITY: Remove `pickle.dumps(sec)` fallback in `SectionDataAdapter._serialize()` | [ ] | **File:** `k1/sessionstate/adapters/section_data_adapter.py:84`. Replace `pickle.dumps(sec)` with `json.dumps(sec.__dict__, default=str).encode()` or raise `SerializationError`. `pickle.loads()` on user-influenced section data is an RCE vector. **Scope:** XS. **Priority: HIGH — security fix.** |
| 9.4.9 | NEW — `LocalEventAdapter._running` write not under lock | [ ] | **File:** `k1/sessionstate/adapters/local_events.py` (`stop()` method). Set `self._running = False` inside `with self._lock` for memory-visibility safety on non-CPython runtimes. **Scope:** XS. |
| 9.4.10 | NEW — `LocalEventAdapter` has no context manager / `__del__` | [ ] | **File:** `k1/sessionstate/adapters/local_events.py`. Add `__enter__` / `__exit__` calling `start()` / `stop()`. Prevents daemon-thread leak when caller forgets `stop()`. **Scope:** XS. |

---

## Milestone 10 — Fabric Production Grade

*Goal: asyncio safety, agent mailbox, schema cache isolation, metric labels.*

> **Deep-dive status:** All 4 epics fully traced end-to-end. Every file in `k1/fabric/` read completely.
> Fabric#1 and Fabric#6 are **false positives** — closed below. Multiple new issues found including
> a permanently-dead depth guard and a synchronous handler blocking bug in the production path.

---

### Epic 10.1 — Asyncio + Concurrency Safety

**Source issues:** Fabric#1, Fabric#6

**What the code actually does (traced):**

**Fabric#1 — FALSE POSITIVE:**

`asyncio.Semaphore` is constructed in `FabricDispatcher.__init__()` at `concurrency/dispatcher.py:301`:

```python
self._semaphore = asyncio.Semaphore(self._config.max_concurrent)
```

The skeleton's "lazy init" prescription was valid for Python ≤ 3.9 where `asyncio.Semaphore` eagerly fetched the running event loop. In Python 3.10+, `asyncio.Semaphore` construction is loop-agnostic — it stores no loop reference and acquires the running loop lazily on first `.acquire()`. `pyproject.toml` declares `requires-python = ">=3.10"`. **No fix needed.**

`dispatch()` uses semaphore correctly: `await self._semaphore.acquire()` inside the async body (line ~468), released in `finally` (line ~499). The `threading.RLock` at line 306 guards `_in_flight` counters separately — correct split.

**Fabric#6 — OVERSTATED:**

`AgentPool.get()` (`providers/agent_provider.py:~1185-1225`):

```python
with self._lock:          # threading.RLock — held for entire operation
    bucket = self._pool.get(contract_name)
    while bucket:
        candidate = bucket.pop(0)   # ← removed atomically while lock held
        if not candidate.is_idle:
            continue
        candidate.reactivate()      # IDLE → ACTIVE inside lock
        return candidate
```

`get()` is fully synchronous. There is no `await` point inside `with self._lock` — no other asyncio task can interleave. `pop(0)` removes the agent from the bucket under the lock; a second concurrent caller sees an empty bucket. **No `in_use` flag needed. No fix needed.**

**New issues found in Epic 10.1:**

- `asyncio.ensure_future()` at `health/health_checker.py:485` is deprecated since Python 3.10 in favour of `asyncio.create_task()`. Task IS captured in `self._task` — no GC hazard, purely cosmetic.
- `_emit_backpressure_event` at `concurrency/dispatcher.py:404,406` reads `self._in_flight` after the `with self._lock:` block exits — stale read possible but GIL-atomic (Python `int` assignment). Benign stale read, logs may show transiently wrong in-flight count.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 10.1.1 | Fabric#1: CLOSE — `asyncio.Semaphore` in `__init__` is correct on Python 3.10+ | [x] | `pyproject.toml` requires `>=3.10`. Lazy init was needed only for 3.9 and below. `dispatcher.py:301` is correct as-is. |
| 10.1.2 | Fabric#6: CLOSE — `AgentPool.get()` is correctly serialized under `threading.RLock`; no race condition | [x] | `pool.get()` is synchronous, no `await` inside `with self._lock:`, `pop(0)` is atomic. No `in_use` flag needed. |
| 10.1.3 | NEW — Replace `asyncio.ensure_future()` with `asyncio.create_task()` in `HealthChecker` | [ ] | **File:** `k1/fabric/health/health_checker.py:485`. `ensure_future` deprecated since 3.10. Task already captured in `self._task` — purely cosmetic fix. **Scope:** XS. |

---

### Epic 10.2 — Schema Cache + Internal Coupling

**Source issues:** Fabric#2, Fabric#3

**What the code actually does (traced):**

**Fabric#2:** `_schema_cache` at `core/contract_validator.py:80` is a **module-level mutable global** (not a class attribute):

```python
_schema_cache: Dict[str, dict] = {}   # line 80 — module scope, no lock
```

Write at line 141: `_schema_cache[contract_type] = schema` — unprotected. Read-check at lines 123-124. The check-then-set gap spans `json.load` + `Draft7Validator.check_schema` — potentially tens of milliseconds. Under `pytest-xdist` or multi-threaded loading, two callers can both miss the cache and race. `clear_schema_cache()` does not exist anywhere in `k1/fabric/`.

**Fabric#3:** `EmbeddingIndex.get_vector(name)` does not exist. The public API has `add_vector`, `remove_vector`, `update_vector`, `search`, `rebuild`, `contains`, `size`, `dimension`. `RetrievalEngine` at `retrieval/retrieval_engine.py:352-353` directly reaches into the private slot:

```python
# Need to get the stored vector -- access internal _vectors
cap_vector = getattr(self._index, "_vectors", {}).get(name)
```

This `getattr` bypasses `EmbeddingIndex._lock` (RLock). A concurrent `add_vector`/`remove_vector`/`rebuild` call can mutate `_vectors` while `RetrievalEngine` iterates it — **data race on the dict**, not just a stale read.

**New issue — `SchemaCompiler._cache` has same pattern:**

`output_validation/schema_validator.py:52-100`: `SchemaCompiler._cache: Dict[Tuple[str, str], Dict[str, Any]] = {}` (instance attribute, no lock). `get_or_compile()` has the same check-then-set pattern. Lower severity than Fabric#2 (instance rather than module-global, so tests using separate instances are isolated).

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 10.2.1 | Fabric#2-A: Add `threading.Lock` protecting `_schema_cache` writes in `contract_validator.py` | [ ] | **File:** `k1/fabric/core/contract_validator.py:80`. Add `_schema_cache_lock = threading.Lock()` at module level. Wrap lines 123-141 in `with _schema_cache_lock:` (double-check locking pattern: check inside lock before computing). **Scope:** XS. |
| 10.2.2 | Fabric#2-B: Add `clear_schema_cache()` module function to `contract_validator.py` | [ ] | **File:** `k1/fabric/core/contract_validator.py`. Add: `def clear_schema_cache() -> None: with _schema_cache_lock: _schema_cache.clear()`. Export from `k1/fabric/core/__init__.py`. **Scope:** XS. |
| 10.2.3 | Fabric#3-A: Add `EmbeddingIndex.get_vector(name: str) -> Optional[np.ndarray]` acquiring `_lock` | [ ] | **File:** `k1/fabric/retrieval/embedding_index.py`. New method: `with self._lock: return self._vectors.get(name)`. **Scope:** XS. |
| 10.2.4 | Fabric#3-B: Replace `getattr(self._index, "_vectors", {}).get(name)` in `RetrievalEngine._run_pipeline()` with `self._index.get_vector(name)` | [ ] | **File:** `k1/fabric/retrieval/retrieval_engine.py:352-353`. This also fixes the lock-bypass race — `get_vector()` acquires `EmbeddingIndex._lock` before reading. **Scope:** XS. **Cross-dep:** 10.2.3 must land first. |
| 10.2.5 | NEW — Add `threading.Lock` to `SchemaCompiler.get_or_compile()` in `schema_validator.py` | [ ] | **File:** `k1/fabric/output_validation/schema_validator.py:52`. Add `self._cache_lock = threading.Lock()` in `__init__`. Wrap check-then-set in `get_or_compile()` with `with self._cache_lock:`. **Scope:** XS. |

---

### Epic 10.3 — Agent Mailbox (MPSC)

**Source issues:** Fabric#4 (Epic 4.4)

**What the code actually does (traced):**

`IAgentMailbox` Protocol declared at `providers/agent_provider.py:342-366` — the interface exists. No concrete implementation anywhere in `k1/fabric/`. `AgentFactory._spawn()` at line 1628 has `mailbox: Optional[IAgentMailbox] = None` with comment `# stub for 4.4`. Agent field `_mailbox` is reserved in `__slots__` (line 455) and initialized (line 484), always to `None`.

**No unguarded dereference sites exist today.** `agent._mailbox` is written in `__init__` and `terminate()` — never read in `execute()`. The skeleton's "guard all access" directive is pre-emptive for future code. No existing call site needs a None-guard added today.

**`terminate()` bug:** Line 622 does `self._mailbox = None` without calling `self._mailbox.close()` first. When a real mailbox is installed, `terminate()` will silently drop all enqueued messages and leak the mailbox.

**Existing `k1/bus/impl/local_mailbox.py`** — `LocalMailbox` + `LocalMailboxRouter` + `AsyncMailboxBridge` are production-grade MPSC implementations. They implement bus-level `IMailbox` semantics (send/receive/close). A thin adapter wrapping `LocalMailbox` to satisfy `IAgentMailbox` is far less work than building from scratch — not documented anywhere.

**Interface design gaps (blocking Epic 4.4):**

- `send()` / `receive()` are synchronous-only — agents run on asyncio loop; blocking `receive()` inside `execute()` blocks the event loop. Needs `async def receive()` or `asyncio.Queue` underneath.
- No priority parameter on `send()` — docstring says "WFQ INTERACTIVE priority" but protocol has no priority field. Breaking Protocol change required when implementing.
- No tool-result delivery protocol — no mechanism for a tool result to post back to the calling agent's mailbox. Design gap, not just implementation gap.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 10.3.1 | Fabric#4-A: Fix `Agent.terminate()` to call `self._mailbox.close()` before nulling the reference | [ ] | **File:** `k1/fabric/providers/agent_provider.py:619-622`. Add: `if self._mailbox is not None: self._mailbox.close()` before `self._mailbox = None`. Zero cost today (mailbox is always None); prevents silent message drain when 4.4 lands. **Scope:** XS. |
| 10.3.2 | Fabric#4-B: Extend `IAgentMailbox` to add `async def receive_async()` and `priority: int` param to `send()` before implementing | [ ] | **File:** `k1/fabric/providers/agent_provider.py:342`. Add `async def receive_async() -> Optional[Dict[str, Any]]: ...` and `priority: int = 0` to `send()`. Must be done before any concrete implementation to avoid a second breaking Protocol change. **Scope:** XS. |
| 10.3.3 | Fabric#4-C: Implement `AgentMailbox` concrete class wrapping `k1.bus.impl.local_mailbox.LocalMailbox` | [ ] | **File:** new `k1/fabric/providers/agent_mailbox.py`. Wrap `LocalMailbox` (or `AsyncMailboxBridge`) from `k1/bus/impl/local_mailbox.py`. Implement `send()`, `receive()`, `receive_async()`, `close()`, `depth`. **Scope:** S. **Cross-dep:** 10.3.2 interface extension must land first. |
| 10.3.4 | Fabric#4-D: Wire `AgentMailbox` into `AgentFactory._spawn()` step 2; replace `mailbox = None` | [ ] | **File:** `k1/fabric/providers/agent_provider.py:1628`. Replace stub with `mailbox = AgentMailbox(agent_id=agent_id)`. **Scope:** XS. **Cross-dep:** 10.3.3. |
| 10.3.5 | Fabric#4-E: Define tool-result delivery protocol — how a tool posts result back to calling agent's mailbox | [ ] | **File:** `k1/fabric/providers/agent_provider.py` (`Agent.execute()`) + tool dispatch path. Currently `execute()` only receives LLM output via `await llm_handle.generate()`. Need: (1) message schema for tool result, (2) call-site in tool dispatcher to `mailbox.send(result)`. **Scope:** M. **Cross-dep:** 10.3.3 + 10.3.4. |

---

### Epic 10.4 — Observability + Wiring Validation

**Source issues:** Fabric#7, Fabric#8, Fabric#9, Fabric#10, Fabric#11, Fabric#12

**What the code actually does (traced):**

**Fabric#7:** `AvailabilityTracker.on_state_change()` at `health/availability_tracker.py:454-510`:

```python
if not self.is_tracked(provider_id):
    old_avail = _CB_TO_AVAILABILITY.get(old_state, Availability.ONLINE.value)
    self.register(provider_id, initial_state=old_avail)  # ← silent auto-register, no WARNING
```

No WARNING log. No return. Unknown providers are silently registered ONLINE without any health probing having occurred.

**Fabric#8:** `WorkflowProvider.__slots__` at `providers/workflow_provider.py:410` includes `_current_depth`. Set in `__init__` at line 431: `self._current_depth = current_depth`. **Never incremented anywhere in `_execute()`.** The factory at `factory.py:~250` always constructs `WorkflowProvider` without a `current_depth` argument — defaults to 0 every time. **The depth guard at line 486 (`if self._current_depth >= self._max_depth`) can never fire.** Skeleton only says "pass as call parameter" — misses that the guard is permanently dead.

**Fabric#9:** `LocalEventAdapter.emit()` at `adapters/local_event.py:108-127`:

```python
for sub_id, handler in handlers:
    try:
        handler(topic, payload)   # ← blocking, unbounded, on caller's stack
    except Exception as exc:
        logger.error(...)
```

Same adapter used in `create_standalone()` production mode (`capture_mode=False`). Any slow subscriber blocks the entire Fabric execution path.

**Fabric#10:** `observe_policy_evaluation()` at `metrics.py:406` takes only `duration_seconds`. The histogram at `metrics.py:~240` has no `labelnames`. Call site at `policy_engine.py:181` passes no capability/provider labels. `request.capability_name` and contract `provider_type` are both in scope at that call site.

**Fabric#11:** `RetrievalLike` Protocol at `core/discovery_tools.py:84` declares `discover_capabilities` and `find_relevant_prompts` as sync. `FabricRetrieval` (in `fabric.py`) has `async def discover_capabilities(...)`. `@runtime_checkable` `isinstance()` check passes (checks method existence only, not `async` signature). If `FabricRetrieval` is passed where `RetrievalLike` is expected, the call returns a coroutine that is never awaited — **silent no-op, never crashes, wrong results**. Currently avoided by wiring `RetrievalEngine` (sync) to the handlers in factory — safe today, breakable by any wiring change.

**Fabric#12:** `validate_wiring()` does not exist in `factory.py`. `production_mode=True` only starts `FabricDispatcher` and uses `AutoDiscoveryMCPTransport` — no assertion that `model_gateway`, `delta_bus`, `bridge`, `prompt_system`, `state_reader`, `event_port` are non-None. `AgentFactory` is constructed with `model_gateway=deps.get("model_gateway_port")` — `None` silently degrades.

**New issues:**

- **NEW — factory always passes `current_depth=0` to every `WorkflowProvider`** (`factory.py:~250`): Even after fixing Fabric#8 to use a call-parameter, sub-workflows launched from within an executing workflow must increment depth and pass it forward — the factory's static-construction pattern makes this impossible without threading depth through the execution call chain. Separate issue from Fabric#8.
- **NEW — `registry_lookup_duration` histogram has no labels** (`metrics.py:~213`): Same gap as Fabric#10 but for registry lookups — no `capability_type` label distinguishes tool vs. agent vs. workflow vs. prompt lookups.
- **NEW — `on_state_change` swallows `InvalidTransitionError` silently** (`availability_tracker.py:~510`): The recovery two-step (`OFFLINE → DEGRADED → ONLINE`) catches all exceptions with bare `except Exception` and logs nothing — intermediate-step failures are silently dropped.

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| 10.4.1 | Fabric#7: Log WARNING and `return` in `AvailabilityTracker.on_state_change()` on unknown provider | [ ] | **File:** `k1/fabric/health/availability_tracker.py:454`. Replace auto-register block with `logger.warning("on_state_change: unknown provider %s — ignoring", provider_id); return`. **Scope:** XS. |
| 10.4.2 | Fabric#8-A: Remove `_current_depth` from `WorkflowProvider.__slots__` and `__init__`; add `depth: int = 0` to `_execute()` signature | [ ] | **File:** `k1/fabric/providers/workflow_provider.py:410,431,486`. Pass depth as a call parameter so each recursive sub-workflow invocation increments independently. **Scope:** S. |
| 10.4.3 | NEW — Fabric#8-B: Fix `WorkflowProvider` factory to pass `depth + 1` when launching sub-workflows via Orchestrator | [ ] | **File:** `k1/fabric/factory.py:~250` + wherever `WorkflowProvider._execute()` recursively spawns child workflows. Currently depth always starts at 0 per instance — the guard is permanently unreachable. Must thread `depth` through the sub-workflow launch call. **Scope:** S. **Cross-dep:** 10.4.2. |
| 10.4.4 | Fabric#9: In `LocalEventAdapter.emit()`, when `asyncio` loop is running dispatch via `asyncio.create_task()`; use `threading.Thread(daemon=True)` for sync callers; keep sync-only when `capture_mode=True` | [ ] | **File:** `k1/fabric/adapters/local_event.py:108`. Check `asyncio.get_event_loop().is_running()` — if yes, schedule handlers as tasks. Sync dispatch only in test/capture mode. **Scope:** S. |
| 10.4.5 | Fabric#10-A: Add `labelnames=["capability_name", "provider_type"]` to `policy_evaluation_duration` histogram | [ ] | **File:** `k1/fabric/metrics.py:~240`. Add `labelnames`. Change `observe_policy_evaluation(self, duration_seconds)` → `observe_policy_evaluation(self, capability_name, provider_type, duration_seconds)`. **Scope:** XS. |
| 10.4.6 | Fabric#10-B: Update call site `policy_engine.py:181` to pass `request.capability_name` and contract `provider_type` | [ ] | **File:** `k1/fabric/policy/policy_engine.py:181`. Both values are in scope at the `_eval_policy()` call. **Scope:** XS. **Cross-dep:** 10.4.5. |
| 10.4.7 | Fabric#11: Add async `discover_capabilities` overload to `RetrievalLike` Protocol or add sync passthrough in `FabricRetrieval` | [ ] | **File:** `k1/fabric/core/discovery_tools.py:84`. Option A: make `RetrievalLike` async and update `DiscoverCapabilitiesHandler.execute()` to `async`. Option B: add `def sync_discover_capabilities(...)` to `FabricRetrieval` that calls `asyncio.run()`. Option A is cleaner — handlers become async. **Scope:** S. |
| 10.4.8 | Fabric#12: Add `FabricFactory.validate_wiring(...)` static method; call at end of `_construct_fabric()` when `production_mode=True` | [ ] | **File:** `k1/fabric/factory.py`. Assert `state_reader`, `event_port`, `bridge`, `model_gateway`, `prompt_system`, `delta_bus` are non-None when `production_mode=True`. Raise `ValueError` listing missing ports. **Scope:** S. |
| 10.4.9 | NEW — Add `labelnames=["capability_type"]` to `registry_lookup_duration` histogram | [ ] | **File:** `k1/fabric/metrics.py:~213`. Same gap as Fabric#10. Capability type (tool/agent/workflow/prompt) unlabelled — all lookups share one bucket. **Scope:** XS. |
| 10.4.10 | NEW — Log (not swallow) `InvalidTransitionError` in `AvailabilityTracker.on_state_change()` recovery two-step | [ ] | **File:** `k1/fabric/health/availability_tracker.py:~510`. Add `logger.warning(...)` in the bare `except Exception` block so intermediate-step failures are visible. **Scope:** XS. |

---

## Cross-cutting: Kernel Concierge Crash Recovery

**Source issues:** C04, K5, K6

| ID | Issue | Status | Analysis Notes |
|---|---|---|---|
| CC.1 | K5: Document and enforce no-task-injection window between S5 and S6b | [ ] | |
| CC.2 | K6: Remove duplicate `concierge_task` / `consumer_task` field from `SessionInstance` | [ ] | |

---

## Issue Count Summary

| Milestone | Epic count | Issue count |
|---|---|---|
| M1 — Boot for chat | 4 | 8 |
| M2 — Chat with memory | 4 | 12 |
| M3 — Multi-session identity | 3 | 5 |
| M4 — Full planning | 3 | 14 |
| M5 — Orchestration reliability | 4 | 13 |
| M6 — Concierge completeness | 4 | 11 |
| M7 — Bus reliability | 4 | 9 |
| M8 — Model Hub production grade | 3 | 10 |
| M9 — SessionState production grade | 4 | 10 |
| M10 — Fabric production grade | 4 | 12 |
| Cross-cutting | 1 | 2 |
| **Total** | **39** | **106** |

---

## Analysis Protocol (fill in before coding each issue)

When an issue is picked for implementation, record:

1. **Files confirmed relevant** — exact paths, line ranges
2. **Already partially present** — any code that does part of this fix already
3. **Cross-dependencies** — other issues that must precede or follow this one
4. **Test coverage gap** — what test needs to be written/updated
5. **Estimated scope** — S (< 1 hour) / M (half day) / L (full day) / XL (multiple days)
