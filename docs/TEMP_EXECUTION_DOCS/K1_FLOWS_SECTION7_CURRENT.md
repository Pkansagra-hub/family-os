# K1 Flows — Section 7 (SessionState) Current State

**Source-of-truth design doc:** [architecture_diagrams/k1/K1_FLOWS.md](../../architecture_diagrams/k1/K1_FLOWS.md) §7 (lines 3237–3998)
**Inventory:** [K1_FLOWS_ENUMERATED.md](K1_FLOWS_ENUMERATED.md) §7
**Companions:** [§1](K1_FLOWS_SECTION1_CURRENT.md) · [§2](K1_FLOWS_SECTION2_CURRENT.md) · [§3](K1_FLOWS_SECTION3_CURRENT.md) · [§4](K1_FLOWS_SECTION4_CURRENT.md) · [§5](K1_FLOWS_SECTION5_CURRENT.md) · [§6](K1_FLOWS_SECTION6_CURRENT.md)
**Verification basis:** subagent code-scan with **mandatory kernel-side wiring inspection** (`k1/kernel/service.py`, `k1/sessionstate/`, `k1/concierge/factory.py`, `k1/concierge/delta/`)
**Date:** 2026-04-27

Legend: ✅ wired · ⚠️ partial · ❌ missing · 🔵 stub-only / aspirational

---

## Section 7 Status Summary

| F# | Name | Status | One-line gap |
|---|---|---|---|
| F66 | Concierge → Single Writer → SessionState | ⚠️ partial | `WriterRole` enum + `enforce_writer()` exist but **`enforce_writer()` is never called in the production write path** (`mutate()`/`DeltaApplicator`); `MutationGuard` is capacity-only, not role enforcement |
| F67 | Multi-Reader Access (RWLock, snapshot) | ⚠️ partial | **No `RWLock` class** — only `threading.RLock()` write lock; reads are lock-free by convention; **no copy-on-read** so partial-write reads possible |
| F68 | Agent Deltas → DeltaBus | ✅ wired | `DeltaBusProdAdapter` wired into Fabric/Orchestrator/Planner via `KernelService` S3; fire-and-forget (no back-pressure) |
| F69 | DeltaBus → Aggregation Window → Concierge | ⚠️ partial | `DeltaAggregator` (500ms) constructed; `DeltaApplicator` wired; **but `bus.subscribe(delta_topic, aggregator.collect)` is ABSENT** — aggregator silently idle in production |
| F70 | HOT → WARM Eviction | ⚠️ partial | `EvictionEngine` + `HotTier.demote_if_needed()` real; **`section_provider=None`** (audit-J) so engine can't read data; **`_evict_fn=None` in `DeltaApplicator`** so pressure never triggers it |
| F71 | WARM → COLD Archive | ⚠️ partial | `LocalColdArchive` (real SQLite at `~/.familyos/k1/sessionstate.db`) production-quality; blocked by same `section_provider=None` upstream |
| F72 | COLD → HOT Reconstruction | ⚠️ partial | `ReconstructionSLA` class **fully implemented but unused**; `manager.restore()` does its own simplified version at session start only; **no per-section lazy rehydration; no K0 fallback** |
| F73 | Emergency Summarization (≥95KB) | ❌ missing | **`EmergencySummarizer` class does not exist**; EMERGENCY pressure only blocks writes, no LLM compression |
| F74 | Emergency Read-Only Mode | ⚠️ partial | `MutationGuard._emergency_mode` flag + write rejection wired; **automatic entry on pressure breach not wired**; `set_emergency_mode()` never called from `mutate()` |
| F75 | Emergency Priority Shedding | ❌ missing | **`PriorityShedder` class does not exist**; `MutationPriority` enum (LOW/NORMAL/HIGH/CRITICAL/EMERGENCY) exists on `MutationRequest` but is never consumed for shedding |
| F76 | Write Request → Mutation Guard | ✅ wired | `MutationGuard.preflight()` real (7 checks: section/op allowlist, lock, emergency, section/tier/total capacity); **no JSON schema validation**; `DirectWriterAdapter` wired ✅; `DeltaApplicator` callbacks `None` ⚠️ |
| F77 | Eviction Engine Trigger | ⚠️ partial | `_trigger_eviction_if_needed()` called inline in `manager.mutate()` after every write; thresholds ELEVATED=90%, CRITICAL=95%; **`section_provider=None` makes eviction structurally wired but operationally hollow** |

### Headline counts

| Status | Count | Flows |
|---|---|---|
| ✅ wired | **2** | F68, F76 |
| ⚠️ partial | **8** | F66, F67, F69, F70, F71, F72, F74, F77 |
| ❌ missing | **2** | F73, F75 |

**Headline finding:** §7 is the **most pipework-rich and most production-leaky section so far**. Almost every component is real; the failures are at the **wiring seams**: aggregator has no bus subscription, `EvictionEngine` has no `section_provider`, `DeltaApplicator` callbacks are all `None`, `enforce_writer()` has no caller. The data structures and SQLite backend (`LocalColdArchive`) are production-quality. F73 and F75 are the only fully-missing components.

**Numerical correction:** docs say total budget is 95KB / emergency at 95KB. **Actual total is 106,496 bytes (104KB)** with EMERGENCY at 95% of that ≈ 98.8KB. Doc is wrong by ~10KB.

---

## 🚨 Two Critical Production Gaps

These are explicitly marked in source code (`TODO(audit-J)`, factory comments):

### Gap 1: `bus.subscribe(delta_topic, aggregator.collect)` is missing (F69)

`DeltaAggregator` is constructed in [k1/concierge/factory.py#L644](../../k1/concierge/factory.py#L644) Step 10 with `flush_fn=applicator.apply`, but **nothing subscribes the bus delta-topic to `aggregator.collect()`**. Consequence: every Back-LLM / sub-agent delta published to `k1.agent.*.delta.v1` reaches the bus, no consumer receives it, the aggregator never fires, the applicator never writes. `DeltaApplicator` write-path is dead in production.

### Gap 2: `EvictionEngine(section_provider=None)` (F70/F71/F77)

[k1/sessionstate/manager.py#L545](../../k1/sessionstate/manager.py#L545) constructs `EvictionEngine` with `section_provider=None` and an explicit `# TODO(audit-J)` comment + warning log. Compounded by [`_evict_fn=None`] in `DeltaApplicator`. Net: pressure thresholds trigger correctly, but eviction can't read real section data — only metadata bytes are freed; archive writes to `LocalColdArchive` will be stub/empty content.

Fix shape (both): implement `SectionDataAdapter` against `HotTier`/`WarmTier`, inject into `EvictionEngine`, and wire `bus.subscribe()` for the delta topic in `_construct_concierge`.

---

## F66 — Concierge → Single Writer → SessionState ⚠️ partial

| Item | Anchor |
|---|---|
| Write lock | `threading.RLock()` at [k1/sessionstate/manager.py#L522](../../k1/sessionstate/manager.py#L522), used by `mutate()` at [#L811](../../k1/sessionstate/manager.py#L811) |
| Writer role enum + matrix | `WriterRole`, `SECTION_WRITERS`, `enforce_writer()` at [k1/concierge/delta/writer_registry.py#L123](../../k1/concierge/delta/writer_registry.py#L123) |
| Capacity guard | `MutationGuard` at [k1/sessionstate/guard.py](../../k1/sessionstate/guard.py) |
| Write port adapter | `SSMStateAdapter(ssm)` at [k1/kernel/service.py#L1419](../../k1/kernel/service.py#L1419) |
| Production write path | FSM → `PortBundle.writer` (`DirectWriterAdapter`) → `ssm.mutate()` → RLock → section |

**Gap:** `enforce_writer()` exists and `SECTION_WRITERS` matrix is correct, but **no caller invokes it in the hot write path** (`mutate()`, `DeltaApplicator`). Role enforcement is aspirational. Per-write role validation needs hooking into `DirectWriterAdapter._request_mutation()` or `MutationGuard.preflight()`.

**Doc drift:** doc `SingleWriter` class → code `WriterRole` enum + `enforce_writer()` function (no class).

---

## F67 — Multi-Reader Access ⚠️ partial (no `RWLock`)

| Item | Anchor |
|---|---|
| Lock declaration | `__slots__` shows `_write_lock` only at [manager.py#L482](../../k1/sessionstate/manager.py#L482) |
| Read pattern | "Read operations are lock-free (snapshot-based)" docstring at [manager.py#L431](../../k1/sessionstate/manager.py#L431) |
| Snapshot API | `get_snapshot()` at [manager.py#L756](../../k1/sessionstate/manager.py#L756) uses `SizeTracker.get_snapshot()` (lock-free) |
| `SnapshotAPI` + `SessionSnapshot` | [k1/sessionstate/snapshot.py](../../k1/sessionstate/snapshot.py) (diagnostics only) |

**Gaps:**

- **No `RWLock` class anywhere.** Multi-reader safety is by convention (reads bypass any lock); writes serialize on `_write_lock` (`threading.RLock`)
- **No copy-on-read for section data** — readers could see partial writes if a section object is mutated mid-read. Not currently a problem under single-writer turn discipline, but a latent concurrency hazard

---

## F68 — Agent Deltas → DeltaBus ✅ wired

| Item | Anchor |
|---|---|
| `DeltaBusProdAdapter.emit_delta()` | [k1/fabric/adapters/delta_bus_prod.py#L41](../../k1/fabric/adapters/delta_bus_prod.py#L41) — publishes to `k1.agent.{agent_id}.delta.v1` |
| Kernel wiring (S3) | `delta_bus = DeltaBusProdAdapter(bus)` injected into Fabric/Orchestrator/Planner |
| Wrappers | `DeltaEmitAdapter(delta_bus=...)` (orchestrator), `PlannerDeltaBusAdapter` (planner) |

**Gap:** fire-and-forget (no back-pressure, no delivery guarantees). Bus drops under load are silent.

---

## F69 — DeltaBus → Aggregation Window → Concierge ⚠️ partial (CRITICAL)

| Item | Anchor |
|---|---|
| `DeltaAggregator.collect(delta)` | [k1/concierge/delta/aggregator.py#L103](../../k1/concierge/delta/aggregator.py#L103) (NOT `ingest()`) |
| Construction (Step 10) | [k1/concierge/factory.py#L644](../../k1/concierge/factory.py#L644) — `DeltaAggregator(flush_fn=applicator.apply)` |
| Applicator | [k1/concierge/delta/applicator.py](../../k1/concierge/delta/applicator.py) — `DeltaApplicator.apply(batch)` |
| Build helper | [k1/concierge/factory.py#L172](../../k1/concierge/factory.py#L172) — `_build_delta_applicator()` |
| Window | `DEFAULT_BATCH_WINDOW_MS = 500`; `asyncio.create_task(_wait_and_flush)` started on first `collect()` |

**Critical gap:** **No `bus.subscribe(delta_topic, aggregator.collect)` call exists.** The aggregator's docstring says "subscribes to delta bus topics" but the class never calls `bus.subscribe()`. Pipeline is correctly assembled but **silently idle** because nothing delivers to `collect()`.

**Doc drift:** doc `AggregationWindow` → code `DeltaAggregator`.

---

## F70 — HOT → WARM Eviction ⚠️ partial

| Item | Anchor |
|---|---|
| `EvictionEngine` + `evict()` + `evict_to_normal_pressure()` | [k1/sessionstate/eviction.py#L279](../../k1/sessionstate/eviction.py#L279), [#L424](../../k1/sessionstate/eviction.py#L424), [#L713](../../k1/sessionstate/eviction.py#L713) |
| `HotTier.demote_if_needed()` + demotion pairs | [k1/sessionstate/tiers/hot.py](../../k1/sessionstate/tiers/hot.py) |
| `WarmTier` + `EVICTION_ORDER` | [k1/sessionstate/tiers/warm.py](../../k1/sessionstate/tiers/warm.py) |
| Eviction construction | [manager.py#L545](../../k1/sessionstate/manager.py#L545) — `EvictionEngine(..., section_provider=None)` with explicit `# TODO(audit-J)` |

Demotion pairs: `beliefs_active→beliefs_history`, `history_active→history_recent`, `task_artifacts→artifacts_warm`. WARM eviction order: `telemetry→artifacts_warm→beliefs_history→history_recent→persona`.

**Gaps:**

- **`TieringManager` class does not exist** — functionality split across `HotTier.demote_if_needed()` + `EvictionEngine.evict()` + `MigrationEngine`
- **`section_provider=None`** (audit-J) — engine can't read real section data
- **`_evict_fn=None` in `DeltaApplicator`** — pressure never triggers eviction via the delta path (only inline `manager.mutate()` path triggers — see F77)

---

## F71 — WARM → COLD Archive ⚠️ partial

| Item | Anchor |
|---|---|
| `LocalColdArchive` | [k1/sessionstate/local_cold.py](../../k1/sessionstate/local_cold.py) |
| Backend | SQLite at `~/.familyos/k1/sessionstate.db` (tables: `st_session_checkpoints`, `st_beliefs_archive`, `st_history_archive`, `st_narrative_archive`) |
| Tier wrapper | `LocalColdTier` at [k1/sessionstate/tiers/local_cold.py](../../k1/sessionstate/tiers/local_cold.py) |
| Wiring | `LocalColdArchive()` injected into `EvictionEngine(local_cold=...)` in `manager.py` |
| Kernel storage | `SQLiteStorageAdapter(db_path=self._config.sessionstate_db_path)` at `KernelService` P2 |

**Gaps:**

- **Doc `ColdStore` → code `LocalColdArchive`** (name drift)
- **Storage is K1 SQLite (edge-first), not K0** — explicitly local
- **Archive writes are production-quality but blocked upstream** by `section_provider=None` — eviction can't supply real content; SQLite rows would store stubs

---

## F72 — COLD → HOT Reconstruction ⚠️ partial

| Item | Anchor |
|---|---|
| `ReconstructionSLA` | [k1/sessionstate/reconstruction.py#L130](../../k1/sessionstate/reconstruction.py#L130) — **fully implemented** |
| `LocalColdArchive` | [k1/sessionstate/local_cold.py#L63](../../k1/sessionstate/local_cold.py#L63) |
| `manager.restore()` | [manager.py#L1403](../../k1/sessionstate/manager.py#L1403) — calls `local_cold.restore("checkpoint")` directly |

**Gaps:**

- **`ReconstructionSLA` is unused in production** — `manager.restore()` bypasses it with a simplified inline version
- **No per-section lazy rehydration** at runtime; restore is all-or-nothing at session `start()` only
- **No K0 fallback** at restore — local cold only
- **Doc `ColdStore` → code `LocalColdArchive`** (consistent with F71 drift)

---

## F73 — Emergency Summarization (≥95KB) ❌ missing

- **`EmergencySummarizer` class does not exist anywhere.** Grep confirms zero hits for `EmergencySummarizer`, `summarize_section`
- At EMERGENCY pressure, `MutationGuard.preflight()` rejects writes with `RejectionReason.EMERGENCY_MODE` ([guard.py#L430-440](../../k1/sessionstate/guard.py#L430)) — only blocking, no compression
- ModelGateway is wired (`session_model_gw` at `service.py#L1399`) but unused for SS emergency path

**Gap:** entire flow is design intent. Implementation would need an `EmergencySummarizer` calling `ModelGateway` and `manager.mutate(section, "set", compressed)`.

---

## F74 — Emergency Read-Only Mode ⚠️ partial

| Item | Anchor |
|---|---|
| `MutationGuard._emergency_mode` flag | [k1/sessionstate/guard.py#L316](../../k1/sessionstate/guard.py#L316) |
| Write rejection check | `preflight()` Check 4 at [guard.py#L430](../../k1/sessionstate/guard.py#L430) — returns `Approval.reject(reason_code=EMERGENCY_MODE)` |
| Surface as rejection | `DirectWriterAdapter` → `RejectionCategory.EMERGENCY` at [direct_writer.py#L731](../../k1/sessionstate/adapters/direct_writer.py#L731) |

**Gaps:**

- **No `ReadOnlyGuard` class** — behavior lives inside `MutationGuard` as a flag (name drift)
- **Automatic entry on pressure breach not wired:** `manager.mutate()` calls `_trigger_eviction_if_needed()` on CRITICAL/EMERGENCY but never calls `mutation_guard.set_emergency_mode(True)`
- **No exit/clear path** after eviction succeeds

---

## F75 — Emergency Priority Shedding ❌ missing

- **`PriorityShedder` class does not exist**; no priority-drop logic anywhere
- `MutationPriority` enum (5 levels: LOW/NORMAL/HIGH/CRITICAL/EMERGENCY) defined in `ports/writer.py`; `MutationRequest` carries a `priority` field per `ARCHITECTURE.md §1.2`
- `DirectWriterAdapter` accepts priority but never uses it for shedding

**Gap:** would need a shedder intercepting in `DirectWriterAdapter._request_mutation()` between preflight approval and actual write, dropping LOW/NORMAL when `pressure == EMERGENCY`.

---

## F76 — Write Request → Mutation Guard ✅ wired (with caveats)

| Item | Anchor |
|---|---|
| `MutationGuard` | [k1/sessionstate/guard.py](../../k1/sessionstate/guard.py) |
| `DirectWriterAdapter.preflight` call | [direct_writer.py#L302](../../k1/sessionstate/adapters/direct_writer.py#L302) |
| `DeltaApplicator.preflight` callback | [applicator.py#L160](../../k1/concierge/delta/applicator.py#L160) (skipped if `_preflight_fn is None`) |

**Preflight runs 7 checks:**

1. Section in `ALL_SECTIONS` allowlist
2. Operation in `VALID_OPERATIONS` (38 ops) allowlist
3. Section not locked (eviction/migration)
4. `_emergency_mode` flag
5. Section capacity (`estimated_bytes > section_available`)
6. Tier capacity (HOT/WARM budget)
7. Total capacity (104KB / 106,496 bytes)

**Gaps:**

- **No JSON schema/payload validation** — only structural (section name, operation string) and capacity checks
- **No per-writer quota**
- **`DeltaApplicator` callbacks `_preflight_fn=None` at kernel wiring** ([service.py#L1364-1390](../../k1/kernel/service.py#L1364)) — preflight is silently skipped on the delta path

---

## F77 — Eviction Engine Trigger ⚠️ partial

| Item | Anchor |
|---|---|
| `EvictionEngine` | [k1/sessionstate/eviction.py#L290](../../k1/sessionstate/eviction.py#L290) |
| Trigger | `_trigger_eviction_if_needed()` at [manager.py#L1063](../../k1/sessionstate/manager.py#L1063), called inline by `mutate()` at [#L900-910](../../k1/sessionstate/manager.py#L900) after every successful write |
| Watermarks | `ELEVATED=90%`, `CRITICAL=95%` of 104KB at [config.py#L31-32](../../k1/sessionstate/config.py#L31) |
| Post-eviction target | 70% utilization |
| Priority order | telemetry→artifacts_warm→beliefs_history→history_recent→persona |

**Gaps:**

- **`section_provider=None`** (audit-J) — engine can't read actual section content; only frees metadata bytes; archive writes will be empty
- **No periodic background trigger** — eviction only runs after writes; idle session won't shed pressure
- **Doc threshold 95KB → actual ~98.8KB** (95% of 106,496 bytes)

---

## Cross-cutting findings

1. **The pipework is real; the seams are unwired.** Eight of twelve flows are ⚠️ partial because components exist and are constructed but the wire between them is missing (`bus.subscribe`, `section_provider`, `_evict_fn`, `_preflight_fn`, `set_emergency_mode` caller, `enforce_writer` caller).
2. **Two `audit-J` TODOs in source** (`section_provider=None` + delta-bus subscription) account for most of the production damage. Fixing both unblocks F69, F70, F71, F77 simultaneously.
3. **F73 (`EmergencySummarizer`) and F75 (`PriorityShedder`) are pure design intent** — no class scaffold exists. Build-or-drop decision needed.
4. **Total budget is 104KB, not 95KB.** Doc and code disagree by ~10KB. EMERGENCY threshold ≈ 98.8KB.
5. **Naming-drift cluster (consistent with §4/§5/§6 pattern):**
   - `SingleWriter` → `WriterRole` enum + `enforce_writer()`
   - `RWLock` → no class; `threading.RLock()` write + lock-free reads
   - `AggregationWindow` → `DeltaAggregator`
   - `TieringManager` → split across `HotTier.demote_if_needed()` + `EvictionEngine` + `MigrationEngine`
   - `ColdStore` → `LocalColdArchive`
   - `ReadOnlyGuard` → `MutationGuard._emergency_mode` flag
   - `PriorityShedder` → does not exist
   - `EmergencySummarizer` → does not exist
6. **`DirectWriterAdapter` is the only reliably-wired write path.** `DeltaApplicator` path is structurally sound but functionally disabled (3× `None` callbacks).
7. **`LocalColdArchive` (SQLite) is production-quality** — real schemas, `ArchiveEntry`/`ArchiveResult` types, edge-first design. The infrastructure is the most polished part of §7.
8. **`ReconstructionSLA` is fully built but bypassed.** Class exists, has SLA timers, hydration order — but `manager.restore()` does its own simplified version. Either wire `ReconstructionSLA` in or delete it.
9. **No copy-on-read for HOT sections (F67)** — latent concurrency hazard if multi-reader async usage grows.
10. **`MutationPriority` enum is plumbed but unused** — F75 `PriorityShedder` would consume it; today it's dead metadata on every write request.

---

## Recommended next actions (priority order)

| Pri | Action | Touches | Source |
|---|---|---|---|
| P0 | Wire `bus.subscribe("k1.agent.*.delta.v1", aggregator.collect)` in `_construct_concierge` Step 10 — currently the entire delta-write path is dead | F69, F65 (§6) | new |
| P0 | Implement `SectionDataAdapter` against `HotTier`/`WarmTier`, inject as `section_provider` into `EvictionEngine` (audit-J) — unblocks real eviction + archive | F70, F71, F77 | new |
| P1 | Wire `_preflight_fn`, `_write_fn`, `_evict_fn` into `DeltaApplicator` at kernel level (currently all `None`) | F69, F70, F76 | new |
| P1 | Hook `set_emergency_mode(True)` from `_trigger_eviction_if_needed()` when pressure breaches EMERGENCY; add exit path post-eviction | F74 | new |
| P1 | Wire `enforce_writer(section, role)` into `MutationGuard.preflight()` or `DirectWriterAdapter` — currently role matrix is unenforced | F66 | new |
| P2 | Decide F73 (`EmergencySummarizer`): build LLM-compression class OR amend doc to declare "emergency = blocking only" | F73 | new |
| P2 | Decide F75 (`PriorityShedder`): implement using existing `MutationPriority` enum OR amend doc + remove unused enum | F75 | new |
| P2 | Wire or delete `ReconstructionSLA` — currently fully implemented but bypassed by `manager.restore()` | F72 | new |
| P2 | Reconcile budget number: doc 95KB ↔ code 104KB; pick one and update both | F73, F77, doc | new |
| P3 | Add periodic background eviction trigger (idle sessions don't currently shed) | F77 | new |
| P3 | Add per-section lazy COLD→HOT rehydration on read miss (currently all-or-nothing at session start) | F72 | new |
| P3 | Add copy-on-read or proper `RWLock` for HOT sections (latent concurrency hazard) | F67 | new |
| P3 | Add JSON schema validation for write payloads in `MutationGuard.preflight()` (currently structural only) | F76 | new |
| P3 | Rename in K1_FLOWS.md per drift cluster (`SingleWriter`/`RWLock`/`AggregationWindow`/`TieringManager`/`ColdStore`/`ReadOnlyGuard`) | doc | new |

---

**Section 7 complete. Next:** §8 K0 Bridge Flows (F78–F87) — 10 flows. Memory writers, K0 P02/P03, SSE→EventBus, checkpoint, proactive trigger. Heavy K0 dependency — expect many `K0 undeployed` (MS-3) verdicts.
