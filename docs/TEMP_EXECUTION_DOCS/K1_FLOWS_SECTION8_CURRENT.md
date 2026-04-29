# K1 Flows — Section 8 (K0 Bridge) Current State

**Source-of-truth design doc:** [architecture_diagrams/k1/K1_FLOWS.md](../../architecture_diagrams/k1/K1_FLOWS.md) §8 (F78–F87)
**Inventory:** [K1_FLOWS_ENUMERATED.md](K1_FLOWS_ENUMERATED.md) §8
**Companions:** [§1](K1_FLOWS_SECTION1_CURRENT.md) · [§2](K1_FLOWS_SECTION2_CURRENT.md) · [§3](K1_FLOWS_SECTION3_CURRENT.md) · [§4](K1_FLOWS_SECTION4_CURRENT.md) · [§5](K1_FLOWS_SECTION5_CURRENT.md) · [§6](K1_FLOWS_SECTION6_CURRENT.md) · [§7](K1_FLOWS_SECTION7_CURRENT.md)
**Verification basis:** subagent code-scan with **mandatory kernel-side wiring inspection** (`k1/kernel/service.py`, `k1/memory_writer/`, `bridge/`, `k1/sse/`, `k1/retention/`)
**Date:** 2026-04-28

**User-stated ground truth (confirmed by audit):** *"Only MemoryWriter is complete and nothing else."* This section's verdicts reflect that reality without inflation.

Legend: ✅ wired · ⚠️ partial · ❌ missing · 🔵 stub-only / aspirational · 🟣 K0-undeployed-blocked

---

## Section 8 Status Summary

| F# | Name | Status | One-line gap |
|---|---|---|---|
| F78 | MemoryWriter Agents → K0 | ⚠️ partial | MW pipeline real and wired to `BridgeCommandAdapter`; **`SinkBridgeClient` forces OFFLINE on init**, all writes land in SQLite outbox, never delivered to K0; doc's `LearningExtractorAgent` (P06) does not exist |
| F79 | DeltaAggregator → K0 | ⚠️ partial | MW-internal `DeltaAggregator` (250ms dedup window) real → `BatchEmitter.submit_batch()` → outbox; **Concierge `DeltaAggregator` has zero K0 forwarding** (no `submit_command`, no bridge ref); K0 dispatch step never runs |
| F80 | K0 P02 Episodic Pipeline | 🟣 K0-blocked | Pure K0-side execution; K1 just writes envelopes with `"pipeline":"P02"` to outbox; K0 undeployed (MS-3) |
| F81 | K0 P03 Consolidation | 🟣 K0-blocked | Pure K0-side execution; zero K1 surface area; K0 undeployed |
| F82 | K0 SSE → K1 EventBus | ❌ missing | **`k1/sse/__init__.py` is empty**; no `SSEEventHandler`, no K0 SSE consumer; `SinkBridgeClient.subscribe()` returns `_empty_async_iter()` |
| F83 | SSE → Proactive Subsystem | ❌ missing | **`k1/proactive/` directory does not exist**; `ProactiveDecisionEngine`/`ProactiveAgentSpawner`/`ProactiveTriggerManager` referenced in `structure.md` but never written |
| F84 | Session Checkpoint → K0 | ❌ missing | All checkpoints stay in `LocalColdArchive` SQLite (`~/.familyos/k1/sessionstate.db`); **zero `submit_command` calls in `k1/sessionstate/`**; no `K0StorageAdapter` |
| F85 | Retention Expiry → Automated Deletion | ❌ missing | **`k1/retention/__init__.py` is empty**; no `RetentionPolicyEngine`, no scheduler, no K0 scan |
| F86 | User Deletion → Soft Delete | ❌ missing | No `UserDeletionHandler`, no soft-delete API, no bridge call for deletion marking |
| F87 | Grace Period Recovery | ❌ missing | Depends on F84 + F86; neither exists; no recovery handler in K1 |

### Headline counts

| Status | Count | Flows |
|---|---|---|
| ✅ wired | **0** | — |
| ⚠️ partial | **2** | F78, F79 (both stuck at outbox; never reach K0) |
| 🟣 K0-blocked | **2** | F80, F81 |
| ❌ missing | **6** | F82, F83, F84, F85, F86, F87 |

**Headline finding:** §8 is the **first section with zero ✅-wired flows**. Only the MemoryWriter→outbox half-leg is real. K0 itself is undeployed (MS-3). F82–F87 are not blocked on K0 — they are **missing on the K1 side** (empty `__init__.py` files for `sse/` and `retention/`; `proactive/` directory absent). The user's ground truth is confirmed: the entire post-MemoryWriter K0 ecosystem is design intent only.

---

## 🚨 Critical Production Reality

### Reality 1: The bridge is a write-only outbox simulator

[bridge/client.py#L188](../../bridge/client.py#L188) `SinkBridgeClient.submit_command_batch()` → `LocalOutbox.enqueue()` → SQLite file. The client **forces `OFFLINE` state on init**. There is no `HttpTransport` to drain the outbox to K0. Every "K0 write" in K1 today is a disk write to an outbox table.

### Reality 2: K1's K0-consuming subsystems are empty scaffolding

- [k1/sse/**init**.py](../../k1/sse/__init__.py) — empty file
- [k1/retention/**init**.py](../../k1/retention/__init__.py) — empty file
- `k1/proactive/` — directory does not exist
- `SinkBridgeClient.subscribe()` returns `_empty_async_iter()` — drops all SSE events even if K0 were running

### Reality 3: Only MemoryWriter touches the bridge

Grep for `submit_command` / `BridgeCommandAdapter` callers across `k1/`: only `k1/memory_writer/batch/batch_emitter.py` and the kernel wiring itself. SessionState, Concierge DeltaAggregator, Planner, Orchestrator — none submit to K0.

---

## F78 — MemoryWriter Agents → K0 ⚠️ partial

| Item | Anchor |
|---|---|
| `MemoryWriterAgent` | [k1/memory_writer/extraction/writer_agent.py#L28](../../k1/memory_writer/extraction/writer_agent.py#L28) |
| Pipeline | [k1/memory_writer/pipeline/pipeline.py#L52](../../k1/memory_writer/pipeline/pipeline.py#L52) |
| `BatchEmitter.submit_batch()` | [k1/memory_writer/batch/batch_emitter.py#L50](../../k1/memory_writer/batch/batch_emitter.py#L50) |
| Kernel wiring (BridgeCommandAdapter) | [k1/kernel/service.py#L1463](../../k1/kernel/service.py#L1463) — `BridgeCommandAdapter(command_port=self._bridge.get_client())` |
| `SinkBridgeAdapter` (S4) | [k1/kernel/service.py#L975-L980](../../k1/kernel/service.py#L975) |
| Outbox enqueue | [bridge/client.py#L188](../../bridge/client.py#L188) `SinkBridgeClient.submit_command_batch()` → `LocalOutbox.enqueue()` |

**Gaps:**

- **`SinkBridgeClient` forces `OFFLINE` state on init** — no live K0 delivery; everything queues to SQLite outbox file
- **Outbox is never drained** — no `HttpTransport` exists to ship to K0 (MS-3 deliverable)
- **Doc's `LearningExtractorAgent` (P06 routing) does not exist** — only `MemoryWriterAgent` (episodic) is implemented
- **No P04/P06 routing** in K1; envelope `body.pipeline` field is set but only K0 would route on it

**Verdict:** the K1-side half-leg is production-quality and end-to-end wired into the kernel. The K0-side half-leg is non-existent. This is the only flow in §8 with a real K1 implementation.

---

## F79 — DeltaAggregator → K0 ⚠️ partial

| Item | Anchor |
|---|---|
| MW-internal `DeltaAggregator` (dedup + 250ms window) | [k1/memory_writer/batch/delta_aggregator.py#L22](../../k1/memory_writer/batch/delta_aggregator.py#L22) |
| Concierge `DeltaAggregator` | [k1/concierge/delta/aggregator.py#L64](../../k1/concierge/delta/aggregator.py#L64) — **no `submit_command`, no bridge reference** |
| K0 submission path | MW only: `BatchEmitter` → `BridgeCommandAdapter` → `SinkBridgeClient` → outbox |

**Gaps:**

- **Concierge `DeltaAggregator` has zero K0 forwarding** — grep for `bridge`/`K0`/`submit_command` in `k1/concierge/delta/`: 0 hits. It's purely K1-internal (feeds `DeltaApplicator` for SessionState writes per §7 F69)
- **MW `DeltaAggregator` forwards correctly to outbox** but K0 dispatch step (`PORT_CMD → BUS_DISPATCH → PIPELINE_ROUTER`) is K0-side and undeployed
- Doc shows a single `DELTA_AGGREGATOR` node; in code there are **two unrelated classes with the same name**, neither of which forwards Concierge deltas to K0

---

## F80 — K0 P02 Episodic Pipeline 🟣 K0-blocked

- **Zero K1 code** — pure K0-side execution
- K1's contribution: queue envelope with `"pipeline":"P02"` in body to outbox (see F78/F79)
- K0 P02 implementation lives in `k0/pipelines/` but K0 server is not deployed (MS-3)

**Verdict:** nothing for K1 to fix; blocked entirely on K0 deployment.

---

## F81 — K0 P03 Consolidation 🟣 K0-blocked

- Same as F80 — zero K1 surface area
- No K1 code references P03 processing
- 100% blocked on K0 (MS-3)

---

## F82 — K0 SSE → K1 EventBus ❌ missing

| Item | Anchor |
|---|---|
| `k1/sse/__init__.py` | [k1/sse/**init**.py](../../k1/sse/__init__.py) — **empty file** |
| `SinkBridgeClient.subscribe()` | [bridge/client.py#L220](../../bridge/client.py#L220) — returns `_empty_async_iter()` |
| Kernel SSE wiring | none — grep `kernel/service.py` for SSE subscribe: 0 hits |

**Gaps:**

- No `SSEEventHandler`, no `K0SSEConsumer`, no subscription loop, no EventBus injection
- Even if K0 were running, `SinkBridgeClient.subscribe()` drops all events
- Entire flow is **missing on K1 side**, not just K0-blocked

---

## F83 — SSE → Proactive Subsystem ❌ missing

- **`k1/proactive/` directory does not exist** (verified via `list_dir k1/`)
- `structure.md` references `ProactiveDecisionEngine`, `ProactiveAgentSpawner`, `SSEEventHandler`, `ProactiveTriggerManager` — none of these files exist on disk
- Prerequisite F82 (SSE consumer) also missing

**Verdict:** the entire proactive subsystem is design intent only. No file scaffolding exists.

---

## F84 — Session Checkpoint → K0 ❌ missing

| Item | Anchor |
|---|---|
| Local checkpoint (SQLite) | [k1/sessionstate/tiers/local_cold.py#L579](../../k1/sessionstate/tiers/local_cold.py#L579) |
| K0 submission | none — grep `submit_command` in `k1/sessionstate/`: 0 hits |
| `K0StorageAdapter` | does not exist in `k1/sessionstate/adapters/` |

**Gaps:**

- **All checkpoints stay in K1 SQLite** (`~/.familyos/k1/sessionstate.db`)
- **No K1-side submission code at all** — even if K0 were live, there's no caller wiring
- Doc's `K0_SESSION_CHECKPOINTS` (WAL + Object backend) target is unreachable from K1

**Verdict:** missing on both ends. K1 needs a `K0SessionCheckpointAdapter` + a hook in the checkpoint timer thread.

---

## F85 — Retention Expiry → Automated Deletion ❌ missing

- **`k1/retention/__init__.py` is empty** — module is scaffolding only
- No `RetentionPolicyEngine`, no deletion scheduler, no `K0_SESSION_CHECKPOINTS` scan logic
- Depends on F84 (checkpoint to K0) which also doesn't exist

**Verdict:** entire retention enforcement subsystem is missing.

---

## F86 — User Deletion → Soft Delete ❌ missing

- No `UserDeletionHandler` anywhere in `k1/`
- No soft-delete API handler
- No bridge call for deletion marking
- `k1/retention/` is empty

**Verdict:** missing on both K1 (no handler) and K0 (undeployed).

---

## F87 — Grace Period Recovery ❌ missing

- No grace-period recovery handler
- No K0 record restoration path
- Depends on F84 + F86; neither exists
- `k1/retention/` is empty

**Verdict:** missing entirely.

---

## Cross-cutting findings

1. **The bridge is an outbox simulator, not a bridge.** `SinkBridgeClient` forces OFFLINE state, queues to SQLite, never ships. No `HttpTransport`. No drain loop. K0 deployment (MS-3) is the only thing that can change this.
2. **Only MemoryWriter (F78) and its dedup aggregator (F79 partial) actually exercise the bridge.** Every other K1 subsystem assumes K0 doesn't exist.
3. **Three K1 subsystems are empty file/directory scaffolds:**
   - `k1/sse/__init__.py` — empty (F82)
   - `k1/retention/__init__.py` — empty (F85/F86/F87)
   - `k1/proactive/` — directory absent (F83)
4. **F84 (session checkpoint to K0) has no K1 code path.** It's not just K0-blocked — there's no submission caller in `k1/sessionstate/` at all.
5. **`SinkBridgeClient.subscribe()` returns an empty async iterator** ([bridge/client.py#L220](../../bridge/client.py#L220)) — even with K0 deployed, SSE events would silently drop until this is replaced with a real subscriber.
6. **Naming-drift cluster (consistent with §4–§7 pattern):**
   - `LearningExtractorAgent` (doc, P06) → does not exist
   - `SSEEventHandler` → does not exist
   - `ProactiveDecisionEngine` / `ProactiveAgentSpawner` / `ProactiveTriggerManager` → do not exist
   - `RetentionPolicyEngine` → does not exist
   - `UserDeletionHandler` → does not exist
   - `K0StorageAdapter` → does not exist
   - `DeltaAggregator` is **two unrelated classes** (MW-internal and Concierge-internal) with no K0 forwarding in either
7. **No flow in §8 reaches ✅-wired status** — first section in the audit with zero green verdicts.
8. **Doc envelope format (`"pipeline":"P02"` etc.) is preserved** even though K0 doesn't consume it — useful for future MS-3 cutover.

---

## Recommended next actions (priority order)

| Pri | Action | Touches | Source |
|---|---|---|---|
| P0 | **MS-3 deployment of K0** — unblocks F78/F79 actual delivery, F80, F81; required prerequisite for everything else | F78–F87 | existing roadmap |
| P0 | Implement `HttpTransport` + outbox drain loop in `SinkBridgeClient` — currently OFFLINE forced; no actual K0 delivery even when K0 is up | F78, F79 | new |
| P1 | Replace `SinkBridgeClient.subscribe()` empty iterator with real K0 SSE subscriber | F82 | new |
| P1 | Implement `k1/sse/` — `SSEEventHandler`, K0 SSE consumer, EventBus dispatch wiring in `KernelService` | F82 | new |
| P1 | Add `K0SessionCheckpointAdapter` + invoke from `StandaloneLifecycle` checkpoint timer; mirror `LocalColdArchive` writes to bridge | F84 | new |
| P2 | Build `k1/proactive/` from scratch — `ProactiveDecisionEngine`, `ProactiveAgentSpawner`, `ProactiveTriggerManager`, budget gate; depends on F82 SSE consumer | F83 | new |
| P2 | Implement `k1/retention/` — `RetentionPolicyEngine`, expiry scheduler, K0 scan + delete loop; depends on F84 K0 checkpoint path | F85 | new |
| P2 | Implement `UserDeletionHandler` (soft-delete API + bridge marker submission) | F86 | new |
| P3 | Implement grace-period recovery handler + K0 restoration path; depends on F84 + F86 | F87 | new |
| P3 | Implement `LearningExtractorAgent` (P06 routing) OR remove from doc | F78 | new |
| P3 | Add K0 forwarding to Concierge `DeltaAggregator` (currently K1-internal only); decide if Concierge deltas should reach K0 P02 at all | F79 | new/design |
| P3 | Rename in K1_FLOWS.md per drift cluster + add explicit "K0 server undeployed (MS-3)" callout to §8 header | doc | new |

---

**Section 8 complete. Next:** §9 Proactive Flows (F88–F94) — 7 flows. Given F83 verdict (entire `k1/proactive/` directory missing), §9 is expected to be ❌ missing across the board. Will verify but expect a quick pass.
