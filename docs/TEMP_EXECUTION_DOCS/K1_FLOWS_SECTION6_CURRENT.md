# K1 Flows — Section 6 (Sub-Agent Lifecycle) Current State

**Source-of-truth design doc:** [architecture_diagrams/k1/K1_FLOWS.md](../../architecture_diagrams/k1/K1_FLOWS.md) §6 (lines 2836–3236)
**Inventory:** [K1_FLOWS_ENUMERATED.md](K1_FLOWS_ENUMERATED.md) §6
**Companions:** [§1](K1_FLOWS_SECTION1_CURRENT.md) · [§2](K1_FLOWS_SECTION2_CURRENT.md) · [§3](K1_FLOWS_SECTION3_CURRENT.md) · [§4](K1_FLOWS_SECTION4_CURRENT.md) · [§5](K1_FLOWS_SECTION5_CURRENT.md)
**Verification basis:** subagent code-scan with **mandatory kernel-side wiring inspection** (`k1/kernel/service.py`, `k1/fabric/factory.py`, `k1/concierge/factory.py`)
**Date:** 2026-04-27

Legend: ✅ wired · ⚠️ partial · ❌ missing · 🔵 stub-only / aspirational

---

## Section 6 Status Summary

| F# | Name | Status | One-line gap |
|---|---|---|---|
| F60 | Agent Spawn via Fabric | ✅ wired | `AgentFactory` + `AgentProvider` in `k1/fabric/providers/agent_provider.py` (~1700 lines); registered in `ProviderFactory` as `ProviderType.AGENT`; **mailbox stub (`None`); kernel doesn't explicitly boot `AgentProvider`** |
| F61 | PENDING → WARMING → ACTIVE | ✅ wired | Inline FSM on `Agent` (`_VALID_TRANSITIONS` dict); `warm_up()` is synchronous pass-through (no real model load, no heartbeat, no event) |
| F62 | ACTIVE → IDLE → ACTIVE | ✅ wired | `AgentPool.put()/get()` + `sweep()` (TTL=60s, sweep_interval=15s); **no background task calls `pool.sweep()` — caller-driven only** |
| F63 | Agent Draining & Termination | ⚠️ partial | `Agent.drain()/terminate()` + `AgentPool.drain_all()` exist; **no `DrainController` class; no in-flight request guard; `drain_all()` not wired into kernel shutdown** |
| F64 | Sub-Agent Clarification via DeltaBus | ⚠️ partial | `DeltaEmitter` + `DELTA_TOPIC_PATTERN="k1.agent.{agent_id}.delta.v1"` + `DELTA_BATCH_WINDOW_MS=500`; **class name drift: `AggregationWindow` → `DeltaAggregator`; no clarification-specific delta type — emits to generic `history_active`** |
| F65 | Concierge Pending Clarifications Write | ⚠️ partial | `clarifications` section exists; single-writer enforced via `enforce_writer()` + `WriterRole.FRONT_LLM`; **section name drift: `PENDING_CLARIFICATIONS` → `clarifications`; no `SingleWriter` class; bus → `DeltaAggregator` subscription wiring unconfirmed** |

### Headline counts

| Status | Count | Flows |
|---|---|---|
| ✅ wired | **3** | F60, F61, F62 |
| ⚠️ partial | **3** | F63, F64, F65 |
| ❌ missing | **0** | — |

---

## 🚨 Big-picture finding — Sub-agents ARE real, but live in the wrong directory

`k1/agents/` (the workspace's top-level "agents" folder) contains **only README files** plus empty `dynamic/` and `mailboxes/` subdirectories with `__init__.py` stubs. **No `.py` classes there.**

The **actual sub-agent runtime** is a single ~1700-line file at [k1/fabric/providers/agent_provider.py](../../k1/fabric/providers/agent_provider.py) holding `Agent`, `AgentFactory`, `AgentPool`, `DeltaEmitter`. The agent runs as a Fabric provider (`ProviderType.AGENT`), not as a top-level kernel-managed component.

This is a **structural surprise** — anyone reading the workspace tree would conclude "sub-agents don't exist." They do; they live behind the Fabric provider abstraction. Same naming-drift pattern as §4's empty `k1/scheduler/` and `k1/supervision/` stubs.

---

## F60 — Agent Spawn via Fabric ✅ wired

| Item | Anchor |
|---|---|
| `AgentFactory` (8-step spawn) | [k1/fabric/providers/agent_provider.py](../../k1/fabric/providers/agent_provider.py) |
| `AgentProvider` registered | [k1/fabric/factory.py#L148](../../k1/fabric/factory.py#L148) — `ProviderType.AGENT` |
| Provider build wires deps | [k1/fabric/factory.py#L179](../../k1/fabric/factory.py#L179) — `_create_agent()` injects `model_gateway_port`, `state_reader`, `delta_bus`, `context_builder` |
| Module YAML contracts | Sub-agents spawned from module YAML definitions via `AgentFactory` |

**Gaps:**

- **Step 2 mailbox creation is a stub:** `mailbox = None` (Epic 4.4 deferred). Agents currently have no live mailbox — communication is request/response only via `Agent.execute()`
- **`contract_loader` plumbing not visible in `KernelService`:** factory expects a callable for agent registry lookup; the wire from `kernel/registries/agent_registry.py` → `AgentFactory` isn't visible in `service.py`
- **Kernel doesn't explicitly boot `AgentProvider`** — it's registered in `FabricFactory` only, so it activates lazily when a capability of `ProviderType.AGENT` is invoked

---

## F61 — PENDING → WARMING → ACTIVE ✅ wired (synchronous pass-through)

| Item | Anchor |
|---|---|
| FSM (inline on `Agent`) | `_lifecycle_state`, `_VALID_TRANSITIONS`, `Agent.warm_up()` in `agent_provider.py` |
| State enum | `AgentLifecycleState` from `k1.fabric.types` — `PENDING/WARMING/ACTIVE/IDLE/DRAINING/TERMINATED` |
| Warm-up flow | `warm_up()` does `PENDING→WARMING` then immediately `WARMING→ACTIVE` (synchronous, no `await`) |
| Spawn entry | `AgentFactory._spawn()` + `spawn_and_execute()` calls `agent.warm_up()` at Step 8 |

**Gaps:**

- **`AgentLifecycleFSM` is NOT a separate class** — the FSM is inline on `Agent` via `_transition()` + `_VALID_TRANSITIONS` dict
- **WARMING is a pass-through with no real work.** Code comment: `# Model preload would happen here with real ILLMHandle` — async model load not implemented
- **No heartbeat, no warmup timeout, no bus event** (`k1.agent.*.lifecycle.v1`) emitted on transitions

---

## F62 — ACTIVE → IDLE → ACTIVE ✅ wired (TTL-only, caller-driven)

| Item | Anchor |
|---|---|
| State transitions | `Agent.idle()` (`ACTIVE→IDLE`), `Agent.reactivate()` (`IDLE→ACTIVE`) |
| Pool checkout | `AgentPool.put()` enqueues by contract name; `AgentPool.get()` pops FIFO and reactivates |
| TTL eviction | `AgentPool.sweep()` — `idle_ttl_expired = idle_elapsed_s > IDLE_TTL_S` (60s) |
| Sweep interval | `AgentPoolConfig.sweep_interval_s = 15` |

**Gaps:**

- **No background task in `KernelService` calls `pool.sweep()`.** Sweep is caller-driven; if no one calls it, idle agents persist
- **No event-based idle detection** — purely TTL. No "agent has been ACTIVE-but-quiet for N seconds → mark IDLE"

---

## F63 — Agent Draining & Termination ⚠️ partial

| Item | Anchor |
|---|---|
| `Agent.drain()` | `ACTIVE/IDLE → DRAINING` |
| `Agent.terminate()` | `DRAINING → TERMINATED` (releases `mailbox=None`, `llm_handle=None`, `state_reader=None`) |
| Pool shutdown | `AgentPool.drain_all()` |
| Failure-path drain | `AgentFactory.spawn_and_execute()` calls `agent.drain()` then `agent.terminate()` on error |
| TTL config | `IDLE_TTL_S = 60`, configurable via `AgentFactoryConfig.idle_ttl_s` |

**Gaps:**

- **No `DrainController` class** — drain logic is inline in `Agent`, `AgentPool`, `AgentFactory` (name drift)
- **No in-flight request tracking.** Drain can cut off mid-execution; no "wait for pending tool calls to complete"
- **`drain_all()` is implemented but not wired into `KernelService` shutdown path** — graceful pool shutdown is dead code at the kernel level

---

## F64 — Sub-Agent Clarification via DeltaBus ⚠️ partial

| Item | Anchor |
|---|---|
| `DeltaEmitter` + `AgentDelta` + `IDeltaBusPort` | [k1/fabric/providers/agent_provider.py](../../k1/fabric/providers/agent_provider.py) |
| Topic pattern | `DELTA_TOPIC_PATTERN = "k1.agent.{agent_id}.delta.v1"` |
| Batch window | `DELTA_BATCH_WINDOW_MS = 500` |
| Emit point | `Agent.execute()` calls `delta_emitter.emit()` then `delta_emitter.flush()` (when `delta_bus is not None`) |
| Aggregator (consumer) | `DeltaAggregator` at [k1/concierge/delta/aggregator.py](../../k1/concierge/delta/aggregator.py) — 500ms fixed-window batching with LWW dedup |
| Flush path | `DeltaBatch` → flush callback → `DeltaApplicator.apply()` |

**Gaps:**

- **Class name drift:** doc `AggregationWindow` → code `DeltaAggregator`
- **No clarification-specific delta type or topic** — agents emit to `section="history_active"` (generic output channel), not a dedicated clarification stream
- **`DeltaEmitter.flush_if_ready()` is never called automatically** — manual flush only (caller must invoke)
- **Whether `DeltaAggregator` actually subscribes to `k1.agent.*.delta.v1` topics is not confirmed** in the concierge FSM/bus boot path — needs explicit verification

---

## F65 — Concierge Pending Clarifications Write ⚠️ partial

| Item | Anchor |
|---|---|
| Section definition | [k1/sessionstate/ARCHITECTURE.md#L172](../../k1/sessionstate/ARCHITECTURE.md#L172) — `clarifications` section (4KB HOT, `ClarificationsSection`) |
| Single-writer policy | [k1/concierge/delta/writer_registry.py#L89](../../k1/concierge/delta/writer_registry.py#L89) — `"clarifications": [WriterRole.FRONT_LLM]` (only FRONT_LLM may write) |
| Violation exception | [writer_registry.py#L57](../../k1/concierge/delta/writer_registry.py#L57) — `SingleWriterViolation` |
| Applicator | [k1/concierge/delta/applicator.py](../../k1/concierge/delta/applicator.py) — `DeltaApplicator.apply(DeltaBatch)` → `MutationGuard.preflight()` → write to SS section |
| Tool contract reference | [k1/contracts/tools/build_agent.yaml#L59](../../k1/contracts/tools/build_agent.yaml#L59) — `pending_clarifications` |
| Planner diagram reference | [k1/planner/planner.mmd#L321](../../k1/planner/planner.mmd#L321) — `PENDING_CLARIFICATIONS` map |

**Gaps:**

- **Section name drift:** doc `PENDING_CLARIFICATIONS` → code `clarifications` (the doc name only appears in YAML and `.mmd` diagrams as a logical concept)
- **No `SingleWriter` class** — single-writer invariant is enforced via `enforce_writer()` + `WriterRole` enum + `SingleWriterViolation` exception (name drift, same intent)
- **`single_writer.py` referenced in [k1/structure.md#L303](../../k1/structure.md#L303) does not exist** — only `writer_registry.py` is present
- **End-to-end path not confirmed:** sub-agent delta → `DeltaEmitter.flush()` → `IDeltaBusPort.emit_delta()` → bus → `DeltaAggregator` (500ms) → `DeltaApplicator.apply()` → `MutationGuard.preflight()` → `ClarificationsSection` write. The downstream half is implemented; the bus subscription in concierge boot is unconfirmed

---

## Cross-cutting findings

1. **Sub-agents are real but hidden in `k1/fabric/providers/agent_provider.py`.** The top-level `k1/agents/` directory is misleadingly empty (README + stubs). Same pattern as §4's empty `k1/scheduler/` and `k1/supervision/`.
2. **Lifecycle FSM is inline on `Agent`, not a standalone class.** Doc names `AgentLifecycleFSM` and `DrainController` don't exist — the behaviors do, just spread across `Agent` + `AgentPool` + `AgentFactory`.
3. **WARMING is a no-op pass-through.** Real model preload (Epic comment in code) deferred. Important: agent "warm" today means "marked ACTIVE", not "model is loaded."
4. **Mailboxes are `None` (Epic 4.4 deferred).** Sub-agents have no async inbox today — only synchronous `Agent.execute()` request/response.
5. **No background sweep loop.** `AgentPool.sweep()` and `AgentPool.drain_all()` exist but the kernel never calls them. Idle agents accumulate; shutdown doesn't drain.
6. **DeltaBus pipeline architecture is solid (emit → 500ms aggregate → apply with single-writer guard) but the bus subscription wiring is unconfirmed.** Need to trace whether `DeltaAggregator` subscribes to `k1.agent.*.delta.v1` topics in the actual concierge boot.
7. **Naming drift cluster (consistent with §4/§5 pattern):**
   - `AgentLifecycleFSM` → inline `Agent._VALID_TRANSITIONS`
   - `DrainController` → `Agent.drain()` + `AgentPool.drain_all()`
   - `AggregationWindow` → `DeltaAggregator`
   - `SingleWriter` → `enforce_writer()` + `WriterRole`
   - `PENDING_CLARIFICATIONS` → `clarifications` section
8. **No clarification-specific delta channel.** Sub-agent output goes to generic `history_active`. If F64/F65 want a real "clarification request" semantic, that's a new section + writer-role + delta type.
9. **No bus event for lifecycle transitions** (`k1.agent.*.lifecycle.v1`). Observability for spawn/warm/idle/drain is absent.

---

## Recommended next actions (priority order)

| Pri | Action | Touches | Source |
|---|---|---|---|
| P1 | Wire a periodic `pool.sweep()` background task in `KernelService._startup_*` so idle agents actually evict | F62 | new |
| P1 | Hook `AgentPool.drain_all()` into `KernelService` shutdown sequence | F63 | new |
| P1 | Verify (or wire) `DeltaAggregator` subscription to `k1.agent.*.delta.v1` topics in concierge boot path | F64, F65 | new |
| P2 | Implement Epic 4.4 mailbox creation in `AgentFactory` Step 2 (replace `mailbox=None`) — needed before any async sub-agent work | F60 | planned |
| P2 | Decide F64/F65 strategy: introduce a dedicated `clarification` delta type + section, OR amend doc to say "sub-agent output funnels into `history_active`" | F64, F65 | new |
| P2 | Add in-flight request guard in `Agent.drain()` to wait for pending `execute()` calls to complete | F63 | new |
| P3 | Either delete misleading `k1/agents/` stub directory OR move `agent_provider.py` content there | structure | new |
| P3 | Emit `k1.agent.*.lifecycle.v1` bus events on every state transition for observability | F61, F62, F63 | new |
| P3 | Rename in K1_FLOWS.md: `AgentLifecycleFSM` → "inline `Agent` FSM", `DrainController` → "`AgentPool.drain_all()`", `AggregationWindow` → `DeltaAggregator`, `SingleWriter` → `enforce_writer()` + `WriterRole`, `PENDING_CLARIFICATIONS` → `clarifications` section | doc | new |
| P3 | Implement real model preload in `Agent.warm_up()` (currently pass-through) | F61 | planned |

---

**Section 6 complete. Next:** §7 SessionState Flows (F66–F77) — 12 flows. Single-writer/multi-reader, delta bus, HOT/WARM/COLD tiering, emergency summarization. This is the densest section so far.
