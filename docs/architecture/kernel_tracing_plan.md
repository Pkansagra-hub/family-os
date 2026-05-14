# K1 Kernel Tracing & Test Skeleton Plan

> **Purpose:** Comprehensive component-by-component tracing/test plan covering every layer, every flow, and every end-to-end message path from origin to destination across the K1 kernel.
>
> **Methodology:** Six milestones (one per component cluster), each broken into epics (subsystems), each broken into issues (specific verifiable trace tasks). Every issue specifies *what to trace*, *file:line*, *expected behaviour*, and *risk*. Items marked **GAP** are places where contracts are silent, contradictory, or known to be broken.
>
> **Scope:** Tracing & verification only. **No code changes** are part of this plan — issues become test/observability tasks downstream.
>
> **Source corpus:** All 36 audit files under [docs/whiteboard/temp_kernel_bootstrap/](docs/whiteboard/temp_kernel_bootstrap/) plus `CONTRACT.md` / `STATE.md` / `WIRING.md` / `OPEN_ISSUES.md` for every `k1/*` component.
>
> **Companion doc:** [three_tier_findings_vs_expectations.md](three_tier_findings_vs_expectations.md) — LOW/MED/HIGH tier expectations vs. reality (prior-turn deliverable).

---

## Master Index

| Milestone | Component cluster | Epics | Issues | GAPs |
|-----------|------------------|------:|------:|-----:|
| **M1** | Concierge | 10 | 46 | 12 |
| **M2** | Kernel + Bridge (active, MS-2.5/MS-3a shipped) | 10 | 58 | 6 |
| **M3** | Fabric + Model Hub | 11 | 66 | 10 |
| **M4** | Orchestrator + Planner | 15 | 62 | 8 |
| **M5** | Bus + SessionState + MemoryWriter | 11 | 55 | 14 |
| **M6** | HIL + SelfModel + Scheduler + Retention + Cross-cutting | 13 | 64 | many |
| **M7** | Pseudo-K0 Integration (Recipe-C live target) | 6 | 28 | 4 |
| **TOTAL** | | **76** | **379** | **53+** |

> **2026-05-13 update.** Two architectural facts that supersede prior "BLOCKED" labels:
>
> 1. **UltraBERT removed by design.** The 1 GB Phase-1 multi-head classifier was deliberately deleted to reduce RAM. K1 now relies on the **LLM via ModelHub** (`IModelGatewayPort`) for intent/emotion/NER/relations/sentiment — what LLMs are already good at. `I1.7.1` (`StubPhase1Pipeline`) is therefore **no longer a blocker**; it is the production code path on every machine. The vision flows F11–F23 ("UltraBERT band") are reclassified to `LLM-COVERED` in [k1_flows_availability_matrix.md](k1_flows_availability_matrix.md).
> 2. **Bridge is active and CQRS-shaped, not offline.** Bridge is a 5-port cross-kernel security gateway (CMD / QRY / SSE / OBS / IFL), not a thin RPC client. MS-2.5 + MS-3a (CMD) + MS-3b (DEGRADED matrix + Outbox + Health) + MS-3c (QRY paired contracts, codegen-only) + MS-3d (SSE codegen subscribers + chunked transport) are **all shipped** ([bridge/ARCHITECTURE.md](bridge/ARCHITECTURE.md), [bridge/runtime.py](bridge/runtime.py)). Hand-written `IKernelQueryPort` and `IKernelSSEPort` were deleted; only codegen paths remain. `KernelService` has **three boot modes** selected at S4 by `KernelConfig.k0_endpoint` / `bridge_enabled`: LIVE (full CQRS surface bound to `HttpTransport`), SINK (`LocalOutbox` only; QRY/SSE return `DegradedMatrix` offline behavior), OFFLINE (null-object on all 5 ports). The live target today is **pseudo-K0** at [scripts/pseudo_k0/](scripts/pseudo_k0/) — a FastAPI emulator covering `/k0/command.submit`, `/k0/obs.emit`, SSE `tool_state.changed.v1`, and pluggable `ConnectorHost`. Production K0 is a separate future migration. Only MS-3e (broader Obs/Feedback), MS-5 (Connector Gateway full IFL impl), and MS-6 (LAN device sync) remain. See new **Milestone M7** below.

### Cross-milestone dependency map

```
                           ┌──────────────────────┐
                           │  M2  Kernel + Bridge │
                           │  (composition root)  │
                           └──────────┬───────────┘
                                      │ S1-S7, P1-P6
            ┌──────────┬──────────────┼───────────────┬──────────┐
            ▼          ▼              ▼               ▼          ▼
        M5 Bus    M5 SessionState  M3 Fabric+MH   M4 Orch+Planr  M1 Concierge
            ▲          ▲              ▲               ▲          ▲
            └──────────┴──────────────┴───────────────┴──────────┘
                                      │ cross-wires (S6b, P3.5)
                           ┌──────────┴───────────┐
                           ▼                      ▼
                       M6 HIL              M6 SelfModel
                       M6 Scheduler / Retention / Tracing / Supervision / Learning
                            (stubs, mostly empty)
```

### Top critical-path blockers (must address first)

| ID | Source | Description |
|---|---|---|
| **M5 I-5.8.1 / ISSUE-MW01** | MemoryWriter | **CLOSED by M5-L1:** Concierge and both MW dispatchers use `k1.session.turn.completed.v1`; live session bus subscription verified |
| **M6 I6.11.C6** | Cross-cutting | Systemic session-state blindness across Orch→Planner→Fabric (3 independent NULL/Mock adapters) |
| **M6 I6.11.C1** | Cross-cutting | `PlanStep.to_dict()` historically dropped `safety_band_min` — safety gate sees None |
| **M6 I6.11.H5** | Cross-cutting | `MockStateReadAdapter` wired in production — safety gate ALWAYS passes |
| **M6 I6.11.C5** | Cross-cutting | `IEmbeddingPort` not wired in shared Fabric S4 → Planner `fabric_search` non-functional |
| **M5 I-5.3.4 / ISSUE-B01** | Bus | **CLOSED by M5-L2:** Python `LocalBus` drops expired `ttl_ms` envelopes before handler delivery |
| **M5 I-5.11.4** | Lifecycle | **CLOSED by M5-L3:** MW stop completes before SSM stop begins during `destroy_session()` |
| **M5 I-5.8.6 / ISSUE-MW04** | MemoryWriter | **CLOSED by M5-L4:** MW refreshes `PlaceResolver` from live `beliefs_active` location entities |
| **M4 GAP-O02** | Orchestrator | `ConcurrencyGuard` re-enqueues plans without depth limit — mailbox flood |
| **M2 I2.5.1 / OPEN §1** | Kernel | `_FirstSessionSSMShim` always reads session 0 — multi-session ModelHub routing broken |
| **M2 I2.5.2 / OPEN §2** | Kernel | Planner `state_port` uses sentinel `"__shared__"` — always returns `None` |
| **M2 I2.4.11 / OPEN §3** | Kernel | Per-session `CapabilityFabric.shutdown()` not called on `destroy_session` |

> **No longer on the blocker list (resolved by architectural decisions, 2026-05-13):**
>
> - ~~`I1.7.1` / UltraBERT Stub returns fixed output~~ — UltraBERT removed by design; LLM via ModelHub is the production classifier.
> - ~~`OPEN §5` / Bridge permanently offline~~ — Bridge is shipped MS-2.5 + MS-3a active; selectable LIVE/SINK/OFFLINE at S4.
> - ~~`I3.4.4` / `BridgeConnectionAdapter` permanently disconnected~~ — adapter is wired conditionally on `KernelConfig.k0_endpoint`; LIVE mode exercises real HTTP path through `HttpBridgeClient`.

---

# Milestone M1 — Concierge

## Component overview

`ConciergeRuntime` is the **session-scoped conversational engine** of K1. It owns the two-actor LLM model (Front + Back), the 11-state cognitive FSM, response delivery timing, and the full SessionState write path. Sole user-facing component — every user message enters here and every response exits here.

Public surface: `start()` / `stop()` lifecycle, `set_self_model()`, and four dispatcher/context handles. Constructed via `ConciergeFactory.create_with_ports()`. Created by `KernelService._create_session_tier2()` (production) or `bootstrap.start_kernel()` (legacy).

## Dependency map

| Dependency | Port | Adapter | File |
|---|---|---|---|
| Session Bus | `IDeltaPort` | `BusFactory` → raw `IBus` | [k1/concierge/adapters/**init**.py](k1/concierge/adapters/__init__.py) |
| User input | `IInputPort` | `BusInputAdapter` (CO-A1) | same |
| User output | `IOutputPort` | `BusOutputAdapter` (CO-A2) | same |
| SessionState | `IStatePort` | `SSMStateAdapter` (CO-A5) | same |
| ModelHub | `ILLMPort ≡ IModelHubPort` | `ModelHubPOCBridge` | [k1/concierge/llm/model_hub_bridge.py](k1/concierge/llm/model_hub_bridge.py) |
| Phase-1 / ACKING | `IClassificationPort` | `UltraBERTPhase1Pipeline` / `StubPhase1Pipeline` | [k1/concierge/fsm/phase1.py](k1/concierge/fsm/phase1.py) |
| Fabric + Orchestrator | `IDispatchPort` | `FabricDispatchAdapter` (CO-A6) | adapters/**init**.py |
| K0 Memory | `IMemoryPort` | `RecallMemoryAdapter` (CO-A8) | same |
| MemoryWriter | bus only — `k1.delta.mutation.v1` | raw `IBus.publish()` | [k1/concierge/actors/front.py](k1/concierge/actors/front.py) |
| HIL Service | factory `hil_port` | `HILCoordinator` | [k1/concierge/factory.py](k1/concierge/factory.py) |
| Orchestrator (MED/HIGH) | `IDispatchPort.dispatch_envelope` | `OrchestratorStub` / production Orch | [k1/concierge/orchestrator/stub.py](k1/concierge/orchestrator/stub.py); HIGH **NOT WIRED** |

## Epic E1.1 — Front LLM ReAct Loop + Tool Execution

**Purpose:** Front Actor handles user-facing dialogue, assembles prompts from live SS sections, runs a tool-calling ReAct loop, emits final streaming response + task dispatches.

**Source:** [k1/concierge/actors/front.py](k1/concierge/actors/front.py) (~1,250 LOC); [k1/concierge/react/loop.py](k1/concierge/react/loop.py); [k1/concierge/prompt/builder.py](k1/concierge/prompt/builder.py); [k1/concierge/tools/dispatcher.py](k1/concierge/tools/dispatcher.py).

### Issues

- **I1.1.1** — Front guard correctly drops observability topics (`k1.concierge.state.updated.v1`). Trace: `front_handler` step 1 guard. Expected: no LLM call. Risk: infinite loop. **File:** front.py:~50–80.
- **I1.1.2** — Emission ordering invariant (cancel → dispatch → final) per CONTRACT.md §4. Trace: post-loop emission block. Risk: FSM races; `IllegalTransitionError`. **File:** front.py:~1100–1200.
- **I1.1.3** — `_strip_leaked_reasoning` / `_strip_leaked_system_blocks` non-fatal. Risk: user sees raw `<thinking>` XML.
- **I1.1.4** — HITL auto-resume (`task.resume.v1`) only in `HITL_RESOLVE` mode (not `HITL_RELAY`). Risk: suspended tasks never resume.
- **I1.1.5** — **GAP (ISSUE-C02):** OPP-6 `EpisodicCompressor` never wired into `ExperienceLayer`. **File:** [k1/concierge/experience/experience_layer.py](k1/concierge/experience/experience_layer.py) `process_turn()`. Expected: fire at turn ≥15. Risk: unbounded history growth → O(n) token cost.

## Epic E1.2 — Back LLM ReAct Loop + Tool Execution

**Source:** [k1/concierge/actors/back.py](k1/concierge/actors/back.py) (~1,380 LOC); [k1/concierge/react/loop.py](k1/concierge/react/loop.py); [k1/concierge/tools/schemas_back.py](k1/concierge/tools/schemas_back.py).

### Issues

- **I1.2.1** — SS snapshot-at-start invariant. Trace: exactly 1 bulk read at task start; 0 reads during iterations 2..N. Per STATE.md §2.2.
- **I1.2.2** — Budget iteration enforcement: LOW=6, MED=10, HIGH=14. **File:** back.py `_budget_to_iterations()`; loop.py `react_loop()`.
- **I1.2.3** — **GAP (ISSUE-C03):** `_run_tool()` not wrapped in `asyncio.wait_for`. **File:** loop.py `_run_tool()`. Risk: 30s+ tool blocks leave FSM stuck in `CANCELLING`.
- **I1.2.4** — `subscribe_back_events` deprecated path (back.py:~1127) is dead code (ISSUE-C07).
- **I1.2.5** — **GAP (ISSUE-C08):** `back_resume_handler` fallback `_get_pending_context()` silently returns `None` (back.py:~1457). Risk: Back resumes with `resolution=None` → hallucinated response.

## Epic E1.3 — FSM Controller (11 States, `_on_*` Handlers, Dispatch Routing)

**Source:** [k1/concierge/fsm/controller.py](k1/concierge/fsm/controller.py); [k1/concierge/fsm/transition_table.py](k1/concierge/fsm/transition_table.py) (~700 LOC, 330-cell guard matrix); [k1/concierge/fsm/states.py](k1/concierge/fsm/states.py); [k1/concierge/fsm/turn_state.py](k1/concierge/fsm/turn_state.py); [k1/concierge/fsm/front_lock.py](k1/concierge/fsm/front_lock.py); [k1/concierge/fsm/idempotency.py](k1/concierge/fsm/idempotency.py).

### Issues

- **I1.3.1** — Dead-letter on illegal transitions (e.g. `task.complete.v1` in `LISTENING`). Expected: `dead.letter.v1` published, state unchanged.
- **I1.3.2** — `IdempotencyLedger` LRU dedup (≥1000 envelopes) prevents replay.
- **I1.3.3** — `TurnLock` serializes Phase-1 classification; `turn_number` monotonic.
- **I1.3.4** — Interrupt routing CANCEL / MODIFY / PARALLEL_NEW / DEFER via `ConversationArbiter`. Risk: user cancel ignored.
- **I1.3.5** — `ConciergeControlExtension` keeps SS `control.flow_state` in sync with FSM state. Risk: stale → wrong PromptMode.

## Epic E1.4 — Tool Dispatcher + FabricDispatchAdapter Wiring

**Source:** [k1/concierge/tools/dispatcher.py](k1/concierge/tools/dispatcher.py); [k1/concierge/tools/implementations.py](k1/concierge/tools/implementations.py); [k1/concierge/tools/parallelism.py](k1/concierge/tools/parallelism.py); [k1/concierge/adapters/**init**.py](k1/concierge/adapters/__init__.py) (CO-A6); [k1/concierge/factory.py](k1/concierge/factory.py) step-14 `_FabricGatewayAdapter`.

### Issues

- **I1.4.1** — Tier allowlist: LOW=3, MED/HIGH=6 tools. Per API mapping §3.3.
- **I1.4.2** — `FabricDispatchAdapter.dispatch_envelope()` raises `RuntimeError` when orchestrator=None. Risk: MED/HIGH silently lost.
- **I1.4.3** — **GAP (Finding N5):** `_FabricGatewayAdapter` translates `name` → `capability_name`. Risk: silent `CapabilityNotFound`.
- **I1.4.4** — Parallel-safe partitioning via `PARALLEL_SAFE_GROUPS`.

## Epic E1.5 — `dispatch_task` Tier Classification + Envelope Routing

**Source:** [k1/concierge/actors/front.py](k1/concierge/actors/front.py); [k1/concierge/task/complexity.py](k1/concierge/task/complexity.py); [k1/concierge/orchestrator/routing.py](k1/concierge/orchestrator/routing.py); [k1/concierge/bus/builders.py](k1/concierge/bus/builders.py); [k1/concierge/tools/schemas_front.py](k1/concierge/tools/schemas_front.py).

### Issues

- **I1.5.1** — **GAP (Finding N6):** HIGH path creates `TaskEnvelope(Budget(max_fabric=10, planner_tokens=3500))` but K1 Orchestrator is **NOT wired**. Risk: HIGH tasks silently dropped.
- **I1.5.2** — CHAINED intents preserve `depends_on`.
- **I1.5.3** — Bus ordering: `task.dispatch.v1` before `response.final.v1`. Risk: dispatch dead-lettered after FSM moves to LISTENING.
- **I1.5.4** — `TaskBridge` mirrors lifecycle into SS `task_state`.

## Epic E1.6 — Prompt Mode Resolution + Iteration Budgets

**Source:** [k1/concierge/prompt/mode.py](k1/concierge/prompt/mode.py); [k1/concierge/prompt/builder.py](k1/concierge/prompt/builder.py); [k1/concierge/prompt/affect.py](k1/concierge/prompt/affect.py); [k1/concierge/experience/experience_layer.py](k1/concierge/experience/experience_layer.py); [k1/concierge/experience/dynamic_identity.py](k1/concierge/experience/dynamic_identity.py).

### Issues

- **I1.6.1** — `determine_mode()` → `CLARIFY_ASK` on `phase1.requires_clarification=True`.
- **I1.6.2** — **GAP (ISSUE-C10):** WEAVE mode history window currently 5-turn; insufficient grounding for pending results.
- **I1.6.3** — `DynamicIdentityContext` role priority: CRISIS→SUPPORTER > HIGH→EXPERT > inflight→EXECUTOR > >10turns→PEER > GUIDE.
- **I1.6.4** — **GAP (ISSUE-C02):** OPP-6 guard (`turn_count ≥ 15`) never satisfied — EpisodicCompressor not wired.

## Epic E1.7 — ACKING / Phase-1 Classification (LLM-Backed, UltraBERT Removed)

**Source:** [k1/concierge/fsm/phase1.py](k1/concierge/fsm/phase1.py); [k1/concierge/acking/](k1/concierge/acking/) (safety gate, complexity router, hypothesis pipeline).

> **Decision 2026-05-13.** The `UltraBERTPhase1Pipeline` (1 GB multi-head BERT classifier) was **intentionally removed** to reduce app size and RAM. Phase-1 classification (intent, ingress, safety_band, complexity, hypothesis) is now handled by **LLM calls via `ModelHubPOCBridge` / `IModelGatewayPort`** — what LLMs are already good at. `StubPhase1Pipeline` is the deterministic fast-path used in hermetic tests; `LLMPhase1Pipeline` (or equivalent ack-LLM call) is the production path. Treat any prior tracing-plan or audit reference to UltraBERT as historical.

### Issues

- **I1.7.1** — **HISTORICAL (resolved by design):** Was "`StubPhase1Pipeline` returns fixed `general/SINGLE/0.5` on non-GPU". UltraBERT is removed; LLM-backed Phase-1 is the only production path. Re-scope of this issue ID: verify Phase-1 LLM call latency budget (P95 < 200 ms target via fast-tier model) and that the LLM gateway is invoked exactly once per turn in `acking/`.
- **I1.7.2** — LLM Phase-1 timeout/error → static `StubPhase1Pipeline` fallback returns conservative defaults (`general/SINGLE/0.5`); no uncaught exception, TurnLock released.
- **I1.7.3** — `TurnLock` prevents concurrent Phase-1; sequential turn ordering.
- **I1.7.4** — `safety_band=RED` triggers CRISIS override regardless of intent.
- **I1.7.5** — **NEW:** Phase-1 LLM call shares the ModelHub budget/cache/CB pipeline (must NOT bypass like `ModelHubPOCBridge` does today — see E3.11.6 / I3.11.6).
- **I1.7.6** — **NEW:** Hermetic test mode: `StubPhase1Pipeline` registered automatically when `KernelConfig.model_mode="test"`; no LLM round-trip required for unit tests.

## Epic E1.8 — HITL Relay + Clarification Flows

**Source:** [k1/concierge/protocols/hitl.py](k1/concierge/protocols/hitl.py) (HILCoordinator, 3 variants + L2 enforcer); [k1/concierge/fsm/suspension_manager.py](k1/concierge/fsm/suspension_manager.py); [k1/concierge/actors/back.py](k1/concierge/actors/back.py) `back_resume_handler()`.

### Issues

- **I1.8.1** — `SuspensionManager.get_resolution()` populated before `back_resume_handler` reads. Risk → ISSUE-C08.
- **I1.8.2** — HITL timeout fires and auto-cancels; default 5 min.
- **I1.8.3** — `back_resume_handler` re-reads SS (intentional exception to snapshot-at-start).
- **I1.8.4** — HILCoordinator wiring guarded by `config.enable_hitl`; graceful degradation.

## Epic E1.9 — Weave / Async Result Delivery

**Source:** [k1/concierge/core/weave_policy.py](k1/concierge/core/weave_policy.py); [k1/concierge/protocols/weave.py](k1/concierge/protocols/weave.py); [k1/concierge/fsm/controller.py](k1/concierge/fsm/controller.py) `_on_task_complete`; [k1/concierge/factory.py](k1/concierge/factory.py) step-12.

### Issues

- **I1.9.1** — `WeavePolicy.decide()` failure falls back to static 500 ms BATCH.
- **I1.9.2** — **GAP (ISSUE-C04):** ledger projection at [k1/concierge/ledger/recovery.py](k1/concierge/ledger/recovery.py#L221) checks `WeaveEmitted` not `ResponseDelivered`. Risk: double-delivery window on crash.
- **I1.9.3** — **GAP (ISSUE-C06):** `WeavePolicy.enabled` has no runtime toggle API.
- **I1.9.4** — WEAVING → WEAVING re-entry drains pending_results queue.

## Epic E1.10 — Concierge Factory + Session Bootstrap

**Source:** [k1/concierge/factory.py](k1/concierge/factory.py) (~880 LOC, 16 steps); [k1/concierge/session.py](k1/concierge/session.py); [k1/kernel/service.py](k1/kernel/service.py); [k1/kernel/bootstrap.py](k1/kernel/bootstrap.py); [k1/concierge/core/crash_recovery.py](k1/concierge/core/crash_recovery.py); [k1/concierge/ledger/recovery.py](k1/concierge/ledger/recovery.py).

### Issues

- **I1.10.1** — `PortBundle.validate_required()` raises `ValueError` for missing required ports (5: delta, input_, output, state, llm).
- **I1.10.2** — **GAP:** `set_self_model()` must be called before `start()` — data race if called after; no guard.
- **I1.10.3** — Teardown ordering: `stop()` before `bus.close()`.
- **I1.10.4** — Crash recovery priority: CLARIFYING_WORKER > WEAVING > COMPANIONING > DISPATCHING > LISTENING.
- **I1.10.5** — **GAP (Finding N1):** `bootstrap.py` duplicates factory wiring; `chat_repl` uses legacy path.
- **I1.10.6** — `enable_ledger=False` must not produce `NullPointerError` on LedgerWriter.

---

# Milestone M2 — Kernel + Bridge

## Component overview

`KernelService` ([k1/kernel/service.py](k1/kernel/service.py)) is the single composition root. Owns Tier 1 (shared: Bus, ModelHub, optional HIL, optional SelfModel, Bridge, shared Fabric, Orchestrator, Planner) and Tier 2 (per-session: Bus, Router, SSM, per-session Fabric, SelfModelHandle, MemoryWriter, ConciergeRuntime). Exposes `ILifecyclePort` + `ISessionManagerPort`.

**Bridge** ([bridge/](bridge/)) is a **CQRS-shaped cross-kernel security gateway** — *not* a thin RPC client. The runtime ([bridge/runtime.py](bridge/runtime.py) `BridgeRuntime`) exposes five separate port surfaces matching the deployment-topology diagram in [bridge/ARCHITECTURE.md §1](bridge/ARCHITECTURE.md):

| Port surface | Direction | Runtime attr | Protocol ABC | Status |
|---|---|---|---|---|
| **CMD** (writes) | K1 → K0 fire-and-forget | `runtime.command` / `runtime.client.<contract>.publish(...)` | `IKernelCommandPort` ([bridge/ports/command_port_protocol.py](bridge/ports/command_port_protocol.py)) | **✅ MS-3a CLOSED** — `HttpBridgeClient` + `HttpTransport`; `memory.write.v1` E2E |
| **QRY** (reads) | K1 ↔ K0 paired req/resp | `runtime.query.<contract>.request(...)` | **codegen-only** (hand-written `IKernelQueryPort` removed in MS-3c) | **✅ MS-3c CLOSED** — paired `recall.request.v1` / `recall.response.v1`; typed clients under `bridge/_generated/k1/query/` |
| **SSE** (push) | K0 → K1 chunked stream | `runtime.sse.<contract>.subscribe(...)` | **codegen-only** (hand-written `IKernelSSEPort` removed in MS-3d) | **✅ MS-3d CLOSED** — generated subscriber port per K0→K1 manifest; real chunked transport `bridge/core/transport/sse_client.py` |
| **OBS** (telemetry) | K1 → K0 metrics/feedback | `runtime.obs` | `IKernelObsPort` ([bridge/ports/obs_port_protocol.py](bridge/ports/obs_port_protocol.py)) | **✅ shipped** — `observability.payload.v1`, `feedback.envelope.v1` contracts active |
| **IFL** (connector gateway) | K1 ↔ external (BLE/HomeKit/HTTP) | `runtime.gateway` | `IConnectorGatewayPort` ([bridge/ports/connector_gateway_protocol.py](bridge/ports/connector_gateway_protocol.py)) | **🟡 protocol shipped, full impl pending MS-5** — first manifest `ifl.google_calendar.events.list.v1` registered |

**Cross-cutting machinery** that backs every port:

- **Envelope core** ([bridge/core/envelope_builder.py](bridge/core/envelope_builder.py), [bridge/core/signing.py](bridge/core/signing.py)) — canonical-JSON HMAC/Ed25519 signing; idem-key excluded from hash; capability tokens; band policy enforcement.
- **DEGRADED matrix** ([bridge/core/degraded.py](bridge/core/degraded.py)) — `DegradedMatrix.behavior_for(port, topic)` *derived from manifest fields* (`delivery.online_required`, `priority_drop`, `max_queue_age`); CI gate `degraded_mode_derived_only` forbids hand-coded `if degraded:` branches. **MS-3b CLOSED.**
- **Health + OnlineFirst** ([bridge/core/health.py](bridge/core/health.py), [bridge/core/online_first.py](bridge/core/online_first.py)) — `K0HealthChecker` polls `base_url`, publishes on shared `EventBus`; `OnlineFirstCommandPort` consults `DegradedMatrix` per envelope.
- **Outbox + drain** ([bridge/sync/local_outbox.py](bridge/sync/local_outbox.py), [bridge/sync/drain_worker.py](bridge/sync/drain_worker.py)) — SQLite WAL, 10 K cap, 10 attempts; event/periodic/startup drain; 4xx → DLQ. **MS-3b CLOSED.**
- **Bus guard** ([bridge/bus_guard.py](bridge/bus_guard.py)) — `BridgeAwareLocalBus` refuses `bus.publish(<bridge_topic>, ...)` that bypasses the registry (R10).
- **Codegen tree** — manifest-driven generation under `bridge/_generated/{k0,k1}/{models,handlers,clients,ports,query}/`; deterministic; `BridgeRuntime.from_registry()` wires generated clients automatically for every `status: active` contract.
- **CI gates (7 green)** — manifest validity, schema sync, codegen freshness, no hand-written ports, no envelope-builder leaks past Bridge, `bridge_client_construction_via_runtime_only`, `degraded_mode_derived_only`.

**KernelService S4** selects one of three boot configurations on top of this CQRS substrate by `KernelConfig`:

| Mode | Trigger | Effect |
|---|---|---|
| **LIVE** | `k0_endpoint` set (e.g. `http://localhost:8090`) | `BridgeRuntime.from_registry(role=K1, transport=HttpTransport)` → `runtime.client` typed publishers + `runtime.query` request clients + `runtime.sse` subscribers + `runtime.health` + `DrainWorker` all active. K0 calls are real HTTP. |
| **SINK** | `bridge_enabled=True`, no `k0_endpoint` | `SinkBridgeClient` → `LocalOutbox` only; no transport bound; QRY surfaces fail offline per `DegradedMatrix`; commands persist in WAL. |
| **OFFLINE** | neither set (default) | Null-object adapter on all 5 port surfaces; commands accepted and dropped; no I/O. |

**Shipped active contracts (12, grouped by port surface):**

- **CMD:** `memory.write.v1`, `curiosity.intent.v1`, `p03.gap.detected.v1`, `p03.complete.v1`.
- **QRY paired:** `recall.request.v1` / `recall.response.v1`.
- **SSE:** `k1.k0.sse.v1`, `k0.learning.advisory.v1`, `k0.proactive.signal.v1` (K0→K1 push channels).
- **OBS:** `observability.payload.v1`, `feedback.envelope.v1`.
- **IFL:** `ifl.google_calendar.events.list.v1` (first connector-gateway contract).

**Still pending** (tracked in [docs/architecture/whiteboard_k1/bridge_implementation_plan.md](docs/architecture/whiteboard_k1/bridge_implementation_plan.md), not in this tracing plan):

- **MS-3e** — broaden Obs/Feedback beyond first manifest pair.
- **MS-5** — Connector Gateway full impl (IFL adapters: HomeKit, BLE, additional Google IFL endpoints, etc.); `bridge/connector/` skeleton only.
- **MS-6** — LAN device sync, mDNS discovery, CRDT-based multi-device state.

None of these block the hermetic Recipe-A test suite or the pseudo-K0 Recipe-C suite — they are forward-looking capacity expansion.

## Dependency map — S1-S7, S6b, P1-P6

| Phase | Component | service.py line | Key adapters |
|---|---|---:|---|
| S1 | Bus + AsyncBusBridge + MailboxRouter | [1125–1131](k1/kernel/service.py#L1125) | `BusFactory.create_local_ordered()`, `create_mailbox_router()` |
| S2 | ModelHub | [1134](k1/kernel/service.py#L1134) | `CredentialStoreAdapter`, `MHEventBusAdapter`, `SessionStateProdAdapter(_FirstSessionSSMShim)`, `PrometheusAdapter`, `ConfigAdapter` |
| S2.5 | HumanInTheLoopService | [1214](k1/kernel/service.py#L1214) | `KernelHILEventAdapter`, `HILLedgerAdapter(None)`, `SafetyBandPolicy` |
| S2.6 | SelfModel bundle | [1254](k1/kernel/service.py#L1254) | `build_self_model_bundle()` |
| pre-S3 | SessionRoutingStateReader | [225](k1/kernel/service.py#L225) | closure over `_sessions` |
| S4 | Bridge adapter + `bridge_client` | [1287](k1/kernel/service.py#L1287) | **LIVE:** `LiveBridgeAdapter` + `HttpBridgeClient` (k0_endpoint set); **SINK:** `SinkBridgeAdapter` + `LocalOutbox`; **OFFLINE:** null object. See new E2.10. |
| S3 | Shared CapabilityFabric | [1341](k1/kernel/service.py#L1341) | 7-adapter wiring; `NullSessionStateReaderAdapter` used |
| S5 | OrchestratorService | [1380](k1/kernel/service.py#L1380) | `MockPlannerAdapter` initially; `FabricGatewayAdapter`, `StateReadAdapter`, `DeltaEmitAdapter`, etc. |
| S6 | PlannerAgent | [1429](k1/kernel/service.py#L1429) | `PlannerStateAdapter(session_id="__shared__")` ← OPEN_ISSUES §2 |
| **S6b** | `orchestrator.bind_planner()` | [1478](k1/kernel/service.py#L1478) | hot-swaps Mock → real `PlannerAdapter` |
| S7 | `asyncio.create_task(planner.start())` | [1490](k1/kernel/service.py#L1490) | only kernel-managed background task |
| P1 | Per-session Bus + Router | [1809](k1/kernel/service.py#L1809) | full isolation from shared bus |
| P1.5 | Per-session HIL (session-bus-bound copy) | [1932](k1/kernel/service.py#L1932) | when `enable_hil_service=True` |
| P2 | SessionStateManager | ~1850 | SQLiteStorageAdapter, DirectWriterAdapter, StandaloneLifecycle |
| P3 | Per-session Fabric | ~1900 | `SessionStateReaderAdapter` (real, not Null) |
| P3.1 | Re-register NativeToolProvider | 1936 | singleton re-registration |
| P3.5 | SelfModelHandle (non-fatal) | ~1968 | session continues if this fails |
| P4 | MemoryWriter + Concierge | 2020, 2034 | `BridgeRecallAdapter` |
| P5 | `concierge.start()` task | ~2070 | `concierge_task is consumer_task` (OPEN_ISSUES §6) |
| P6 | `_sessions[session_id] = SessionInstance` | ~2090 | only after all P succeed |

## Epic E2.1 — Lifecycle FSM

States `UNSTARTED → STARTING → RUNNING → STOPPING → STOPPED`.

- **I2.1.1** — `startup()` happy path; all 9 Tier-1 fields non-None; `is_running == True`.
- **I2.1.2** — `startup()` when RUNNING → `RuntimeError("already running")`.
- **I2.1.3** — `shutdown()` reverse order S7→S1: planner.stop → orchestrator.shutdown → bridge.disconnect → fabric.shutdown → model_hub.shutdown → hil.shutdown → router.close → bus.close.
- **I2.1.4** — `shutdown()` idempotent on UNSTARTED/STOPPED.
- **I2.1.5** — **GAP:** `health_check()` aggregation strategy unspecified in CONTRACT.

## Epic E2.2 — S1–S7 Construction (9 issues)

- **I2.2.1** S1 Bus backend via `K1_BUS_BACKEND`. — **I2.2.2** S2 ModelHub with 5 port adapters + `_FirstSessionSSMShim` (see I2.5.1). — **I2.2.3** S2.5 HIL conditional on `enable_hil_service`. — **I2.2.4** S2.6 SelfModel conditional on `enable_self_model`. — **I2.2.5** S4 Bridge adapter selection. — **I2.2.6** S3 Shared Fabric 7-adapter wiring. — **I2.2.7** S5 Orchestrator with initial `MockPlannerAdapter`. — **I2.2.8** S6 Planner with `session_id="__shared__"` (OPEN_ISSUES §2). — **I2.2.9** S7 `_planner_task` is the only kernel-managed task.

## Epic E2.3 — S6b Cross-Wire

- **I2.3.1** — `bind_planner()` hot-swaps Mock → real `PlannerAdapter`.
- **I2.3.2** — `_verify_s6b_cross_wire` at [service.py:1061](k1/kernel/service.py#L1061) blocks `_running=True` if S6b failed.

## Epic E2.4 — P1–P6 Per-Session + Teardown (11 issues)

- **I2.4.1** P1 bus isolation. — **I2.4.2** P2 SSM SQLite per session. — **I2.4.3** P3 per-session Fabric gets real reader. — **I2.4.4** P3.5 SelfModel handle non-fatal. — **I2.4.5** P4 MW + Concierge per session. — **I2.4.6** `session.concierge_task is session.consumer_task` (OPEN §6). — **I2.4.7** Teardown order: MW → Concierge → SSM → Router → Bus. — **I2.4.8** `destroy_session("nonexistent")` → `KeyError`. — **I2.4.9** `_TEARDOWN_TIMEOUT = 10 s` per step. — **I2.4.10** **GAP:** `ssm.stop()` has no timeout guard — can hang indefinitely. — **I2.4.11** **GAP (OPEN §3):** per-session `CapabilityFabric.shutdown()` not called on `destroy_session`.

## Epic E2.5 — KernelConfig Flags + Dead Code

- **I2.5.1** — **GAP (OPEN §1) HIGH:** `_FirstSessionSSMShim` ([service.py:1134](k1/kernel/service.py#L1134)) always reads session 0 — multi-session ModelHub routing broken.
- **I2.5.2** — **GAP (OPEN §2) MED:** `PlannerStateAdapter(session_id="__shared__")` never matches any real session → always `None`.
- **I2.5.3** — **GAP (OPEN §4):** `KernelConfig.max_sessions=100` declared but never enforced in `create_session()`.
- **I2.5.4** — **GAP (OPEN §7):** Dead flags `enable_orchestrator`, `enable_experience`, `enable_delta`, `enable_hitl` are never read.

## Epic E2.6 — Port/Adapter Mapping Integrity

- **I2.6.1** No duplicate port registrations (except deliberate `FabricBusAdapter` dual-role).
- **I2.6.2** 5 planned-but-not-wired kernel ports remain bypassed by direct factory calls.
- **I2.6.3** — **GAP:** `fabric.IEmbeddingPort` production adapter not documented in CONTRACT.
- **I2.6.4** `DeltaEmitAdapter(event_port, delta_bus)` requires both args, distinct objects.

## Epic E2.7 — Bridge Runtime Path (CQRS — MS-2.5/3a/3b/3c/3d CLOSED)

- **I2.7.1** Bridge is in-process import (not sidecar). [bridge/ARCHITECTURE.md §1.3](bridge/ARCHITECTURE.md). Five port surfaces (CMD/QRY/SSE/OBS/IFL) all live in the same Python process as K1.
- **I2.7.2** **SINK mode** (`bridge_enabled=True`, no `k0_endpoint`): `SinkBridgeClient.submit_command()` enqueues to `LocalOutbox` — no HTTP. SQLite WAL durable. QRY/SSE surfaces return `DegradedMatrix` `RAISE_OFFLINE_ERROR` / `MARK_STREAM_CLOSED` per manifest derivation.
- **I2.7.3** **CQRS Command surface (MS-3a) shipped:** `BridgeRuntime.from_registry()` builds `runtime.client` (composite `HttpBridgeClient` with slot-bound typed publishers per active CMD contract). `runtime.client.memory_write_v1.publish(MemoryWriteV1(...))` posts to `{base_url}/k0/command.submit` with signed envelope.
- **I2.7.4** **CQRS Query surface (MS-3c) shipped:** Hand-written `IKernelQueryPort` + `QueryEnvelope` + `RecallBundle` were **deleted**; replaced by codegen-generated paired clients under `bridge/_generated/k1/query/`. Recall reachable only via `runtime.query.recall_request_v1.request(...)` with typed `recall.response.v1` reply. Verify no caller still imports the legacy types.
- **I2.7.5** **CQRS SSE surface (MS-3d) shipped:** Hand-written `IKernelSSEPort` + `SSETraceEvent` + `BackpressureLevel` were **deleted**; replaced by codegen one-subscriber-per-manifest. Real chunked SSE transport at [bridge/core/transport/sse_client.py](bridge/core/transport/sse_client.py). Three active K0→K1 channels: `k1.k0.sse.v1`, `k0.learning.advisory.v1`, `k0.proactive.signal.v1`.
- **I2.7.6** **CQRS Obs surface shipped:** `IKernelObsPort` with `observability.payload.v1` (telemetry, K1→K0) and `feedback.envelope.v1` (curiosity/learning feedback, K1→K0). `bridge_memory_write_v1_*` Prometheus counters per `bridge/obs/metrics.py`.
- **I2.7.7** **DEGRADED matrix (MS-3b) shipped:** [bridge/core/degraded.py](bridge/core/degraded.py) `DegradedMatrix.behavior_for(port, topic)` derives behavior from manifest fields (`delivery.online_required`, `priority_drop`, `max_queue_age`). CI gate `degraded_mode_derived_only` forbids hand-coded `if degraded:` branches anywhere in the bridge. Legacy `DegradedModeManager` survives only for `SinkBridgeClient`.
- **I2.7.8** **Outbox durability (MS-3b) shipped:** [bridge/sync/local_outbox.py](bridge/sync/local_outbox.py) SQLite WAL; `MAX_QUEUE_DEPTH=10_000`, `MAX_ATTEMPTS=10`; [bridge/sync/drain_worker.py](bridge/sync/drain_worker.py) `DrainWorker` drains on event/periodic/startup; 4xx → DLQ; 5xx/429 retry with exponential backoff up to `MAX_POLL_INTERVAL_S=60s`.
- **I2.7.9** **Health checker (MS-3b) shipped:** [bridge/core/health.py](bridge/core/health.py) `K0HealthChecker` polls `transport.config.base_url`, publishes liveness on shared `EventBus`; `OnlineFirstCommandPort` ([bridge/core/online_first.py](bridge/core/online_first.py)) consults matrix per envelope. Owned by runtime, lifecycle via `runtime.start()` / `runtime.stop()`.
- **I2.7.10** **Envelope core shipped:** `EnvelopeBuilder` ([bridge/core/envelope_builder.py](bridge/core/envelope_builder.py)) HMAC or Ed25519 selectable; canonical JSON; idem-key excluded from hash. CI gate forbids `CommandEnvelope` imports outside `bridge/` (first wall violation cleared MS-3a Epic 3a.2 in `k1/memory_writer/adapters/bridge_command_adapter.py`).
- **I2.7.11** **Bus topic guard shipped:** [bridge/bus_guard.py](bridge/bus_guard.py) `BridgeAwareLocalBus` refuses `bus.publish(<bridge_reserved_topic>, ...)` that bypasses `BridgeRuntime` (R10 mitigation).
- **I2.7.12** `bridge_client` (and `runtime.query` / `runtime.sse` / `runtime.obs`) is a single shared object across per-session adapters (STATE.md §6 inv-7). Per-session bridge would defeat the global outbox/drain semantics.
- **I2.7.13** **CI gates (7 green):** manifest meta-schema, schema sync, codegen freshness, no hand-written port classes, no `CommandEnvelope` leak, `bridge_client_construction_via_runtime_only` (AST walk asserts construction goes through `from_registry` sentinel), `degraded_mode_derived_only`.
- **I2.7.14** **Remaining surface area (NOT blocking Recipe-A / Recipe-C):** MS-3e widen Obs/Feedback contract coverage; MS-5 Connector Gateway full IFL implementation (`bridge/connector/` skeleton only); MS-6 LAN device sync / mDNS / CRDT.

## Epic E2.8 — Lifecycle Invariants (STATE.md §6)

- **I2.8.1** Inv-1: `_running == True` iff all 9 Tier-1 components live and S7 completed. — **I2.8.2** Inv-2: `_sessions[session_id]` exists iff P6 succeeded. — **I2.8.3** Inv-3: `_planner_task` only kernel-managed task. — **I2.8.4** Inv-4: Fabric before Planner. — **I2.8.5** Inv-5: Mock→real planner swap window. — **I2.8.6** Inv-6: `_hil_service` shared by Fabric/Orchestrator/Planner; per-session Concierge gets bus-bound copy. — **I2.8.7** Inv-7: shared `bridge_client`.

## Epic E2.9 — Stub Package / Facade

- **I2.9.1** — **GAP:** `k1/kernel/loader.py`, `hot_reload.py`, `registries/` are stubs; nothing imports from them.
- **I2.9.2** `bootstrap.py` is backward-compat facade over `KernelService`; verify `chat_repl`/`runner` call into `start_kernel()` → `KernelService`.

### OPEN_ISSUES.md cross-reference

| Entry | Severity | M2 Issue |
|---|---|---|
| §1 `_FirstSessionSSMShim` | High | I2.5.1 |
| §2 Planner `__shared__` | Med | I2.5.2 |
| §3 Per-session Fabric never torn down | Med | I2.4.11 |
| §4 `max_sessions` not enforced | Low | I2.5.3 |
| §5 Mock window S5→S6b | Low | I2.3.1 + I2.3.2 |
| §6 `concierge_task == consumer_task` | Low | I2.4.6 |
| §7 Dead config flags | Low | I2.5.4 |

---

# Milestone M3 — Fabric + Model Hub

## Component overview

**Fabric** ([k1/fabric/](k1/fabric/)) is the capability execution layer — single gateway for every tool invocation, agent spawn, workflow execution, and Concierge state transition. Owns: `CapabilityContract` registry with hot-reload; 3-stage retrieval pipeline (FAISS + hard filter + soft rank); **9-step `_execute_impl`** pipeline (resolve → conscience gate → HIL gate → context build → provider instantiate → CB dispatch → output validation → metrics → learning signal); 7 provider transports (MCP, WASM, Bridge, Agent, Workflow, Concierge, LocalStub); WFQ-priority dispatcher; circuit breakers + availability tracking; 3-tier output validation. **FAB-01 invariant:** Fabric is read-only for SessionState; never calls LLMs directly — routes agent LLM via `IModelGatewayPort` → Model Hub.

**Model Hub** ([k1/model_hub/](k1/model_hub/)) is the single LLM dispatch layer. All LLM-calling actors converge here. Owns: `ProviderRegistry` (manifest-driven, MH-18); **9-step `RequestRouter`** (validate → budget → priority → capability route → model select → cache → normalize → dispatch → denormalize/audit); circuit breaking + rate limiting per provider; LRU response cache (1000 entries / 5-min TTL); audit log; 6 provider plugins (OpenAI, Anthropic, Google/Gemini, Ollama, vLLM, stub). **Critical wiring gap (ISSUE-M01):** `from_config` four injected ports (`event_port`, `state_read_port`, `config_port`, `health_port`) stored but never connected — all 10 bus topics silently suppressed.

## Dependency map

```
Concierge ──(IDispatchPort)──────────────────► Fabric.execute()
Orchestrator ──(IFabricGatewayPort)──────────► Fabric.execute() / CapabilityRegistryAPI.lookup()
Planner ──(IFabricRetrievalPort)─────────────► Fabric.discover_capabilities()

Fabric agents ──(IModelGatewayPort / ModelGatewayBridgeAdapter)──► ModelHub.execute()
Concierge ──(ILLMPort / ModelHubPOCBridge)───► ModelHub.execute()  [POC, bypasses pipeline]
Planner ──(ILLMPort)──────────────────────────► ModelHub.execute()
MemoryWriter ──(LLMGatewayAdapter)────────────► ModelHub.execute()

ModelHub ──(IProviderPlugin)──────────────────► OpenAI / Anthropic / Google / Ollama / vLLM
Fabric ──(IBridgePort)────────────────────────► K0 Bridge  [DISCONNECTED — OPEN_ISSUES #5]
```

Key cross-cutting: `CapabilityRequest.safety_band` set by Concierge, consumed by Fabric `PolicyEngine.SecurityContext`. If omitted, Fabric defaults `GREEN` → silent privilege escalation. M3-L2 now locks this as a strict-xfail GAP in `tests/integration/k1/live/m3/test_m3_l1_l4_fabric_modelhub.py`: `CapabilityRequest.from_dict()` defaults the missing field to GREEN and current live Fabric executes instead of rejecting.

## Epic E3.1 — Fabric Public Surface (10 issues)

`execute`, `execute_batch`, `discover_capabilities`, `find_relevant_prompts`, `register`/`unregister`/`lookup`.

- **I3.1.1** Happy path `execute()` STEP 1-9; emits `k1.capability.invoked.v1` + `k1.capability.completed.v1` with `cognitive_trace_id` (FAB-09). **Covered by M3-L1:** `tests/integration/k1/live/m3/test_m3_l1_l4_fabric_modelhub.py` boots live Recipe A, executes a deterministic per-session Fabric `LOCAL_STUB` capability through resolve/policy/context/provider/CB/validation, and asserts matching trace ids on both bus envelopes and JSON payloads.
- **I3.1.2** `capability_name` prefix validation (`tool.|agent.|workflow.|concierge.`) — FAB-03.
- **I3.1.3** `execute_batch(BatchStrategy.PARALLEL)` via `asyncio.gather`; order preserved; single failure doesn't crash batch.
- **I3.1.4** `BatchStrategy.DAG` topological wave execution; cycle detection (FAB-12).
- **I3.1.5** `discover_capabilities` soft ranking: DEGRADED provider gets ×0.70 penalty (FAB-06).
- **I3.1.6** Hard filter: user `safety_band=GREEN` excludes `safety_band_min=AMBER` (FAB-04).
- **I3.1.7** `find_relevant_prompts` returns only `PromptContract` entries.
- **I3.1.8** `register` same-version → `DuplicateCapabilityError`.
- **I3.1.9** `register` semver upgrade → `VERSION_UPGRADED` event.
- **I3.1.10** `lookup` exact version: major=0 exact; major>0 same-major OK; different major fails (FAB-11).

## Epic E3.2 — `_execute_impl` 9-Step Pipeline (10 issues)

- **I3.2.1** STEP 2 resolve: unknown → `not_found`. — **I3.2.2** STEP 3 conscience gate: `is_forbidden` → `conscience_gate_blocked`; `None` port short-circuits (FAB-15). — **I3.2.3** STEP 4 HIL approval → proceed. — **I3.2.4** STEP 4 HIL timeout 120 s → `hil_denied`. — **I3.2.5** STEP 5 ContextBuilder reads 3 SS sections; `NullSessionStateReaderAdapter` graceful. — **I3.2.6** STEP 7 CB CLOSED→OPEN at threshold (FAB-05). **Covered by M3-L3:** live per-session Fabric uses a real `CircuitBreaker`; two controlled provider failures trip CLOSED→OPEN. — **I3.2.7** STEP 7 CB OPEN→HALF_OPEN→CLOSED probe. **Covered by M3-L3:** OPEN blocks without a provider call, `allow_probe()` moves HALF_OPEN, and a successful probe closes the breaker. — **I3.2.8** STEP 8 Tier-1 structural REJECT. — **I3.2.9** STEP 8 Tier-2 coercion. — **I3.2.10** STEP 8 Tier-3 semantic ANNOTATE only.

## Epic E3.3 — Registry + Contract Resolution (5 issues)

- **I3.3.1** ContractValidator rejects non-semver `version`. — **I3.3.2** ContractValidator rejects WorkflowContract DAG cycle (FAB-12). — **I3.3.3** EMA latency formula α=0.3. — **I3.3.4** `AvailabilityTracker` blocks OFFLINE→ONLINE direct; auto-inserts DEGRADED. — **I3.3.5** `ModuleLoader` hot-reload 2 s poll interval.

## Epic E3.4 — Provider Layer (8 issues)

- **I3.4.1** MCPProvider happy path. — **I3.4.2** MCPProvider `is_connected=False` → `provider_unavailable`. — **I3.4.3** WASMProvider sandbox `memory_limit_mb=64, allow_network=False`. — **I3.4.4** **RESOLVED 2026-05-13:** BridgeProvider `BridgeConnectionAdapter` is now wired conditionally on `KernelConfig.k0_endpoint`. LIVE mode (`HttpBridgeClient`) round-trips to K0 endpoint; SINK mode buffers to `LocalOutbox`; OFFLINE mode returns typed `K0_OFFLINE` error shape. Verify the K0_OFFLINE error shape under OFFLINE mode (was the original gap). — **I3.4.5** **GAP:** AgentProvider `mailbox=None` — known open issue. — **I3.4.6** AgentProvider `tools_granted` scope (FAB-07). — **I3.4.7** WorkflowProvider `MAX_WORKFLOW_DEPTH=3` (FAB-08). — **I3.4.8** **GAP:** `NativeToolProvider` not described in CONTRACT/WIRING.

## Epic E3.5 — `FabricDispatcher` WFQ Scheduling (3 issues)

- **I3.5.1** Semaphore lazily created on first `dispatch()` (OPEN §1 FIXED).
- **I3.5.2** **GAP:** WFQ `REALTIME` over `BACKGROUND` ordering not documented.
- **I3.5.3** `shutdown()` drains in-flight; skips if `_semaphore is None`.

## Epic E3.6 — Fabric Tier-Agnosticism (FAB-01)

- **I3.6.1** `create_shared()` with no `state_reader` → `NullSessionStateReaderAdapter` wired.
- **I3.6.2** Fabric never calls write methods on `ISessionStateReader` (structural invariant). **Covered by M3-L4:** `tests/integration/k1/live/m3/test_m3_l1_l4_fabric_modelhub.py` wraps the live per-session Fabric state-reader holders with a read-only tracking proxy, executes a capability requiring SS context, observes read calls, and records zero write-method lookups.

## Epic E3.7 — ModelHub Routing (7 issues)

- **I3.7.1** Happy path 9-step. — **I3.7.2** Cache hit on identical `CHAT` request (MH-06/07/08/09). — **I3.7.3** `TOOL_CALL` never cached. — **I3.7.4** `EMBED` routes only to embed-capable providers (MH-18). — **I3.7.5** `NoEligibleProviderError` when all CBs OPEN (MH-14). — **I3.7.6** Timeout by priority: REALTIME 10 s vs INTERACTIVE 30 s (MH-15). — **I3.7.7** **GAP (ISSUE-M09):** `stream_execute` token usage broken for ALL providers.

## Epic E3.8 — ModelHub Adapters (6 issues)

- **I3.8.1** OpenAI `CHAT` normalization. — **I3.8.2** Anthropic `STRUCTURED` via tool-param schema injection. — **I3.8.3** Google `REASON` → Gemini thinking budget. — **I3.8.4** Ollama `TOOL_CALL` dict-args JSON serialization (ISSUE-M08 FIXED regression). — **I3.8.5** vLLM `placement_type=LOCAL_GPU` wins on equal quality. — **I3.8.6** Google `stream_execute` materializes all chunks (ISSUE-M06 known regression).

## Epic E3.9 — Policy / Throttling / Quota (6 issues)

- **I3.9.1** RateLimiter two-phase RPM+TPM atomic (ISSUE-M03 FIXED). — **I3.9.2** Budget at 80% → `ALLOW_DEGRADED` cost-optimization (MH-04/13). — **I3.9.3** Budget at 95% → `REJECT` raises `BudgetExceededError`. — **I3.9.4** Token-bucket refill rate `rpm/60.0` per sec. — **I3.9.5** **GAP (ISSUE-M02):** `AuditLogger` unbounded growth at 10k+. — **I3.9.6** **GAP (ISSUE-M04):** `ResponseCache` key via `repr(payload)` — fix status unconfirmed.

## Epic E3.10 — LLMGatewayAdapter (P02 tie-in)

- **I3.10.1** **GAP:** `HubRequest.consumer_id` field existence unverified.
- **I3.10.2** **GAP (ISSUE-M01) HIGH:** `from_config` 4 unwired ports → all 10 bus topics silently suppressed.
- **I3.10.3** **GAP (ISSUE-M10-A):** `ProviderLoader` silently skips provider on missing credential.

## Epic E3.11 — Cross-Component Contract (6 issues)

- **I3.11.1** Full Concierge→Fabric→MCPProvider trace; `trace_id` + `cognitive_trace_id` propagated.
- **I3.11.2** **GAP:** Fabric agent → `IModelGatewayPort` → `ModelGatewayBridgeAdapter` → `IModelHubPort`; budget translation undocumented.
- **I3.11.3** `CapabilityRequest.safety_band` default `GREEN` — silent privilege baseline.
- **I3.11.4** **GAP (XREF-FAB-01):** `FabricGatewayAdapter._contract_to_entry()` may `AttributeError` on `compensation_capability`.
- **I3.11.5** PlanStep type collision: `WorkflowProvider` must import `k1.fabric.types.PlanStep` (6 fields) not orchestrator's (14 fields).
- **I3.11.6** **GAP:** Concierge POC path (`ModelHubPOCBridge`) bypasses ModelHub pipeline — zero budget/cache/CB.

---

# Milestone M4 — Orchestrator + Planner

## Component overview

`OrchestratorService` is the task execution engine for MEDIUM and HIGH tier requests. Owns mailbox loop, tier routing (`_dispatch_medium` / `_dispatch_high`), planner round-trip, DAG wave executor, workflow scheduler, MCP connector lifecycle. Only K1 component that calls Fabric capabilities.

`PlannerAgent` converts `PlanRequest` → `CommittedPlan` via 4-stage LLM pipeline (SKETCH → EXPAND → VALIDATE → COMMIT), delivers on event bus. Singleton async actor with one active plan at a time (PLAN-02).

Type boundary via [k1/orchestrator/types.py](k1/orchestrator/types.py) (canonical `CommittedPlan`, `PlanStep`, `PlanRequest`, `MicroReplanRequest`). Cross-wired at kernel S6b ([service.py:1478](k1/kernel/service.py#L1478)).

## Dependency map

```
Kernel S5 → OrchestratorService (factory) ← MockPlannerAdapter placeholder
Kernel S6 → PlannerFactory.create_production() → PlannerAgent
Kernel S6b → orchestrator.bind_planner(PlannerAdapter(planner.mailbox))
Kernel S7 → asyncio.create_task(planner.start())  + _verify_planner_orchestrator_crosswire()

Inbound:
  TaskEnvelope (Concierge) → IMailboxPort → OrchestratorService._mailbox_loop()
  k1.planner.plan.request.v1 → PlannerAgent._on_plan_request()
  k1.planner.plan.ready.v1  → OrchestratorService._on_plan_ready()
  k1.planner.plan.cancel.v1 → PlannerAgent._on_plan_cancel()

Outbound:
  Orchestrator → IFabricGatewayPort.execute() / execute_batch()
  Orchestrator → IPlannerPort.request_plan() / micro_replan()
  Planner → ILLMPort.execute()  (SketchService, ExpandService, ValidateService)
  Planner → IFabricRetrievalPort.discover_capabilities()
  Planner → IBridgePort.persist_plan()  (CommitService WAL)
```

## Epic E4.1 — OrchestratorService Lifecycle (5 issues)

- **I4.1.1** `init()` 10-step startup; `_running=True` only on success. [orchestrator_service.py:430](k1/orchestrator/orchestration/orchestrator_service.py#L430).
- **I4.1.2** `_subscribe_events()` registers exactly 5 topics. [orchestrator_service.py:588](k1/orchestrator/orchestration/orchestrator_service.py#L588).
- **I4.1.3** `_mailbox_loop()` FIFO within priority band.
- **I4.1.4** `reap_stale_contexts()` after 45 s timeout; resolves waiter future. [orchestrator_service.py:2356](k1/orchestrator/orchestration/orchestrator_service.py#L2356).
- **I4.1.5** **GAP (O03):** `WorkflowScheduler._last_run` not persisted; CRON re-fires on restart.

## Epic E4.2 — `handle_task` Tier Routing (4 issues)

- **I4.2.1** MEDIUM→`_dispatch_medium`, HIGH→`_dispatch_high`.
- **I4.2.2** `TaskEnvelope.__post_init__` MEDIUM max 2 capabilities (ORCH-10). [types.py:638](k1/orchestrator/types.py#L638).
- **I4.2.3** HIGH with `planner_port=None` → degrade or FAILED (not crash).
- **I4.2.4** MEDIUM empty `capabilities` → `ValueError`.

## Epic E4.3 — `_dispatch_medium` (3 issues)

- **I4.3.1** `execute_batch` invoked with correct `CapabilityRequest` per cap; `caller_id`. [orchestrator_service.py:1516](k1/orchestrator/orchestration/orchestrator_service.py#L1516).
- **I4.3.2** All success → COMPLETED.
- **I4.3.3** Partial fail → DEGRADED (or FAILED if not optional).

## Epic E4.4 — `_dispatch_high` (6 issues)

- **I4.4.1** `request_plan(PlanRequest)` populated correctly. — **I4.4.2** `PlanAck.REJECTED` → immediate FAILED. — **I4.4.3** `ACCEPTED` → `PendingPlanContext` + future. — **I4.4.4** `_on_plan_ready()` deserializes `CommittedPlan`; **GAP (PLN-GAP-02 verify):** `safety_band_min` round-trip. — **I4.4.5** `_on_plan_failed()` cleans up context + resolves waiter. — **I4.4.6** **GAP (O02) HIGH:** `ConcurrencyGuard` re-enqueues without depth limit — mailbox flood risk.

## Epic E4.5 — DAGExecutor (7 issues)

- **I4.5.1** `build_waves()` Kahn topological sort. [dag_executor.py:207](k1/orchestrator/orchestration/dag_executor.py#L207). — **I4.5.2** `CycleError` on cyclic deps. — **I4.5.3** `IFabricGatewayPort.execute()` per-step with correct fields. — **I4.5.4** `Semaphore(max_wave_parallelism)` enforced. — **I4.5.5** BFS cancellation: failed step cascades to transitive dependents only. — **I4.5.6** WAL checkpoints `WAVE_COMPLETE` + `DAG_COMPLETE` fire-and-forget. — **I4.5.7** `interrupt_flag=True` stops at next wave boundary (cooperative).

## Epic E4.6 — ExecutionMonitor (Wave HIL)

- **I4.6.1** **GAP (O06):** `after_wave()` HIL fires when >3 steps OR >5 s — UX over-interrupt. [execution_monitor.py:178](k1/orchestrator/orchestration/guards/execution_monitor.py#L178).
- **I4.6.2** HIL timeout 30 s → CONTINUE.
- **I4.6.3** `after_step()` CANCEL → `interrupt_flag=True`.

## Epic E4.7 — Step Timeout

- **I4.7.1** `asyncio.wait_for(execute, timeout_seconds)` (O01 FIXED at [step_runner.py:362](k1/orchestrator/orchestration/step_runner.py#L362)).
- **I4.7.2** Timeout → `step_timeout` error code; retry budget consumed.
- **I4.7.3** Default `step_timeout_default_ms=30_000`.

## Epic E4.8 — Planner SKETCH (4 issues)

- **I4.8.1** `_MAX_TOOL_ROUNDS=6` (shared with EXPAND — PLAN-05). [sketch_service.py:81](k1/planner/stages/sketch_service.py#L81).
- **I4.8.2** `needs_clarification=true` triggers HIL.
- **I4.8.3** HIL max 2 rounds (PLAN-10).
- **I4.8.4** Cancel checkpoint 1 (pre-lock) discards enqueued request.

## Epic E4.9 — Planner EXPAND (3 issues)

- **I4.9.1** Step IDs match `^s[0-9]+$`.
- **I4.9.2** 6 infrastructure fields injected deterministically from `CapabilityContract`, not LLM.
- **I4.9.3** No `hil_port`; `expand_timeout_ms=5000`.

## Epic E4.10 — Planner VALIDATE (6 issues)

- **I4.10.1** Phase-1 cycle detection (Kahn). — **I4.10.2** `CHECK_CAPABILITY_MISSING` fires on registry miss. — **I4.10.3** Phase-2 arbiter `STRUCTURED`, `max_tokens=512`, `temp=0.0`. — **I4.10.4** Arbiter unavailable → auto-approve if Phase-1 passed. — **I4.10.5** `VERDICT_REVISE` max 1 loop. — **I4.10.6** **GAP (P04):** `ValidationVerdict` direct construction may bypass `__post_init__` error-issue guard. [types.py:283](k1/planner/types.py#L283).

## Epic E4.11 — Planner COMMIT (4 issues)

- **I4.11.1** Emits `k1.planner.plan.ready.v1` with retry-once. [commit_service.py:176](k1/planner/stages/commit_service.py#L176).
- **I4.11.2** No `llm_port` (PLAN-03 invariant).
- **I4.11.3** WAL persist fire-and-forget — failure doesn't block delivery.
- **I4.11.4** `estimated_duration_ms` = critical-path longest-path DP.

## Epic E4.12 — `micro_replan` (4 issues)

- **I4.12.1** `asyncio.wait_for(timeout=10.0)`. [micro_replan.py:302](k1/orchestrator/orchestration/guards/micro_replan.py#L302).
- **I4.12.2** Timeout → CONTINUE on original plan.
- **I4.12.3** **HIGH:** Completed steps NOT in micro-replan output (PLAN-12).
- **I4.12.4** Micro-replan FSM: IDLE→MICRO_SKETCH→MICRO_EXPAND→MICRO_VALIDATE→COMMITTING.

## Epic E4.13 — Bus Topics (4 issues)

- **I4.13.1** `k1.planner.plan.request.v1` → `_on_plan_request()` → `create_task(_safe_enqueue)`.
- **I4.13.2** `k1.planner.plan.cancel.v1` → `_cancel_set` adds within `sketch_timeout_ms=8000`.
- **I4.13.3** **GAP (verify):** `CommittedPlan` round-trip preserves all fields including `safety_band_min`.
- **I4.13.4** `k1.orchestration.dag.completed.v1` emitted on every DAG terminal state.

## Epic E4.14 — S6b Cross-Wire (3 issues)

- **I4.14.1** `_verify_planner_orchestrator_crosswire()` raises if still `MockPlannerAdapter`. [kernel/service.py:1060](k1/kernel/service.py#L1060).
- **I4.14.2** **GAP (P01):** Ordering: S5 init → S6b bind → S7 verify → kernel `_running=True`.
- **I4.14.3** `PlannerAdapter.request_plan()` → `mailbox.enqueue()` returns `PlanAck("ACCEPTED")`; full mailbox → `REJECTED` not raise.

## Epic E4.15 — Open Issues P02 / P03 / P04 (3 issues)

- **I4.15.1** **GAP (P02):** `LLMGatewayAdapter` imports `build_payload` from `k1.model_hub.adapters` (private→public migration). [llm_gateway_adapter.py:185](k1/planner/adapters/llm_gateway_adapter.py#L185).
- **I4.15.2** **GAP (P03) HIGH:** `ToolCallRouter.get_schema()` uses `discover_capabilities(intent=name, top_k=1)` — semantic similarity for exact lookup. [tool_call_router.py:312](k1/planner/services/tool_call_router.py#L312).
- **I4.15.3** **GAP (P04):** Use `ValidationVerdict.from_components()` factory, not direct construction.

### Consolidated M4 GAP register

| ID | Severity | Location |
|---|---|---|
| GAP-O02 | High | `concurrency_guard.py` mailbox flood |
| GAP-O03 | Med | `workflow_scheduler.py` CRON restart |
| GAP-O06 | Low | `execution_monitor.py:127` UX |
| GAP-P02 | High | `llm_gateway_adapter.py:185` private→public |
| GAP-P03 | High | `tool_call_router.py:312` semantic vs exact |
| GAP-P04 | Med | `types.py:283` ValidationVerdict bypass |
| GAP-PLN-02 (verify) | Med | `PlanStep.to_dict()` safety_band_min round-trip |
| GAP-DOCS | Low | `WIRING.md:102` Phase 5 stale TODO |

---

# Milestone M5 — Bus + SessionState + MemoryWriter

## Component overview

**Bus** is the sole inter-component communication mechanism. Every event/task dispatch/tool result/HITL signal/affect update flows as `Envelope` through `IBus`. Production-ready (dual Python+Rust backend, causal ordering via `TimingChain`, async dispatch with DLQ, durable SQLite outbox, idempotency middleware, schema validation). TTL expiry is enforced in Python `LocalBus` (M5-L2). Remaining known issues: sequence gaps from middleware drops (B02), unbounded per-topic lock growth (B03), mailbox-full drops invisible (B04). P6.10: `k1.model_hub` not STRICT in `bus.yaml`.

**SessionState** is single source of truth for per-session cognitive state: 15 sections across HOT (52 KB) + WARM (48 KB) in-memory + LOCAL COLD SQLite. Standalone production path (`SQLiteStorageAdapter` + `DirectWriterAdapter` + `StandaloneLifecycle`) live; 5 MS-2+ adapters stub. Issues: 3 sections still JSON not FlatBuffer (SS-01); two SQLite classes share one file (SS-02); latent deadlock `DWA._lock → SSM._write_lock → MutationGuard._lock` (SS-03); no mutation audit (SS-04). Orchestrator gets only `MockStateReadAdapter`.

**MemoryWriter** is a stateless background agent observing `k1.session.turn.completed.v1`; default mode is `SessionBatchDispatcher` (`session_batch`) with legacy `TurnDispatcher` retained for `per_turn` compatibility. Both dispatchers use the same canonical Concierge topic. It runs the 7-stage pipeline (relevance → SS snapshot → context build → LLM extraction → validation → envelope build → batch emit) and submits ≤6 atoms per turn to K0 via `IBridgeCommandPort`.

## Dependency map

```
User input → [k1.session.user.input.v1] → Concierge FSM
  ├──writes──► SSM (15 sections)
  │           ├──reads──► Fabric (LIVE)
  │           ├──reads──► Planner (reader=None placeholder)
  │           ├──reads──► Orchestrator (MockStateReadAdapter — STUB)
  │           └──reads──► MemoryWriter (LIVE, 13 sections)
  ├──publishes──► [k1.session.turn.completed.v1] → TurnDispatcher (per_turn)
  ├──publishes──► [k1.session.turn.completed.v1] → SessionBatchDispatcher (default)
  ├──publishes──► [k1.orchestration.task.dispatch.v1] → Orchestrator → [k1.planner.plan.requested.v1] → Planner
  └──publishes──► [k1.response.final.v1] → UI

MemoryWriter Pipeline:
  ├──reads──► SS (ISessionReadPort, 13 sections, <1ms)
  ├──calls──► ModelHub (IModelHubPort.chat, budget=2000 tokens, BACKGROUND)
  └──submits──► Bridge (IBridgeCommandPort.submit_batch) → K0 P02
```

## Epic E5.1 — Bus Publish/Subscribe Contract + Topic Schemas (4 issues)

- **I-5.1.1** `LocalBus.publish()` stamps `envelope_id`, `sequence`, `created_ns` on new frozen instance.
- **I-5.1.2** Wildcard semantics `*` (single segment) vs `>` (greedy). **GAP:** Python/Rust parity unverified.
- **I-5.1.3** Handler isolation: exception in handler A doesn't suppress B; `stats.handler_errors++`.
- **I-5.1.4** `flush(timeout_ms)` blocks until async mailboxes drained; `False` on timeout.

## Epic E5.2 — Delivery Guarantees (4 issues)

- **I-5.2.1** Per-topic monotonic sequence under concurrent publishers.
- **I-5.2.2** STRICT causal ordering via `_gap_buffers[topic]._buffer`; `create_local_ordered()`.
- **I-5.2.3** BEST_EFFORT drops to `mailbox_full_drops` counter; **no DLQ callback (B04).**
- **I-5.2.4** **GAP (B02):** Middleware `None` return creates sequence gap; STRICT holds 5000 ms.

## Epic E5.3 — DLQ + Dead-Letter (4 issues)

- **I-5.3.1** DLQ callback on async retry exhaustion (P6.7).
- **I-5.3.2** `BusOutbox` durable replay via SQLite WAL.
- **I-5.3.3** `subscribe(consumer_id=...)` ack on success only; not on exception.
- **I-5.3.4** **CLOSED (B01):** Python `LocalBus` enforces TTL at dispatch time. M5-L2 verifies a `ttl_ms=100` envelope observed at +200 ms reaches zero handlers and increments `ttl_drops`. Rust parity remains a separate backend-parity question.

## Epic E5.4 — Topic Catalog (8 issues, 39 topics)

Complete enumeration tables for namespaces:

- **I-5.4.1** `k1.session.*` topics include user.input, turn.started, turn.completed, artifact.created, state.updated, and task.state. **MW01 closed:** Concierge and MW now converge on `turn.completed`.
- **I-5.4.2** `k1.orchestration.*` (13 topics): task.dispatch, cancel, resume, modify, accepted, complete, failed, suspended, findings.ready, clarification.request/response, dag.completed, delta — all STRICT.
- **I-5.4.3** `k1.planner.*` (5 topics): plan.requested, ready, failed, cancelled, micro_replan.ready. **GAP (P6.10):** should be STRICT but rule absent.
- **I-5.4.4** `k1.response.*` (3 topics) RELAXED.
- **I-5.4.5** `k1.affect.*`, `k1.proactive.*`, `k1.ui.*`, `k1.hil.*` (5 topics).
- **I-5.4.6** `k1.capability.*`, `k1.fabric.*` (6 topics) — capability.* STRICT.
- **I-5.4.7** `k1.mw.*`, `k1.sessionstate.*`, `k1.model_hub.*` (5+ topics). **GAP:** `k1.model_hub` not STRICT.
- **I-5.4.8** Validate `bus.yaml` STRICT/RELAXED assignments match expectations.

## Epic E5.5 — SSM Public API (6 issues)

- **I-5.5.1** 3-tier capacity check section→tier→total (SS-05); `FLATBUFFER_OVERHEAD_FACTOR=1.10`.
- **I-5.5.2** Emergency mode blocks all writes (SS-06); `set_emergency_mode` thread-safe.
- **I-5.5.3** `get_section()` lock-free <1 ms P99; `mutate()` acquires `_write_lock RLock`.
- **I-5.5.4** **GAP (SS-03) HIGH:** `MutationGuard._lock` is plain `Lock` not `RLock`; double-lock deadlock if event subscriber re-enters DWA.
- **I-5.5.5** Eviction order: telemetry → artifacts_warm → beliefs_history → history_recent → persona (SS-07).
- **I-5.5.6** **GAP (SS-01):** `task_state`, `task_artifacts`, `artifacts_warm` serialize JSON despite FlatBuffer bindings existing.

## Epic E5.6 — `_FirstSessionSSMShim` Multi-Session (3 issues)

- **I-5.6.1** One SSM per session; no shared global.
- **I-5.6.2** `LocalColdArchive` uses `session_id` as row discriminator; cross-session impossible.
- **I-5.6.3** **GAP (SS-02):** `SQLiteStorageAdapter` (4 tables) + `LocalColdArchive` (7 tables) share file; 3 tables missing.

## Epic E5.7 — SSM Read/Write Concurrency (4 issues)

- **I-5.7.1** `AsyncSSMBridge.mutate()` via `asyncio.to_thread()`; reads sync pass-through.
- **I-5.7.2** `MutationGuard._validate_operation()` enforces `VALID_OPERATIONS` frozenset.
- **I-5.7.3** `history_active` max-10 turns → demote oldest to `history_recent` (SS-13).
- **I-5.7.4** `task_state` prune 10 turns after `presented_at_turn > 0`; unpresented never pruned (SS-12).

## Epic E5.8 — MemoryWriter Pipeline (7 issues)

- **I-5.8.1** **CLOSED (ISSUE-MW01):** `SessionBatchDispatcher.TOPIC`, `TurnDispatcher.TOPIC`, MW event constant, and Concierge `TOPIC_TURN_COMPLETED` all equal `k1.session.turn.completed.v1`; M5-L1 verifies the live bus subscription.
- **I-5.8.2** `RelevanceFilter` skips CLARIFICATION/SYSTEM_TURN/DUPLICATE/EMPTY/TRIVIAL without LLM (MW-07).
- **I-5.8.3** `MemoryWriterAgent.extract()` returns `[]` on LLM error; never raises (MW-06).
- **I-5.8.4** `ExtractionValidator` caps: 6 atoms (MW-05), 50 words (MW-04), 0-5 temporal_links (MW-12).
- **I-5.8.5** `DeltaAggregator` dedup by `SHA256(sorted_participants:sorted_topics)[:16]`.
- **I-5.8.6** **CLOSED (ISSUE-MW04):** `PlaceResolver` is constructed empty but refreshed from live `beliefs_active` location entities during `process()` and `process_session()`; M5-L4 verifies `place_olive_garden` and non-sentinel seed geohash resolution.
- **I-5.8.7** **GAP (ISSUE-MW06) HIGH:** `TurnDispatcher` newest-wins drops correction turns (`correction_signal=True`).

## Epic E5.9 — MW Contracts + Storage (5 issues)

- **I-5.9.1** MW-01: factory rejects `IStateWritePort` in injected deps.
- **I-5.9.2** `EnvelopeBuilder.build()` asserts non-empty `cognitive_trace_id` (MW-10).
- **I-5.9.3** `PrivacyEnforcer.enforce()`: RED strips PII; GREEN passes.
- **I-5.9.4** **GAP (ISSUE-MW02):** `_processed_ids` unbounded `set[str]`; lost on restart → duplicate atoms.
- **I-5.9.5** `CircuitBreaker` trips at `failure_threshold` LLM failures; `recovery_probe_seconds`.

## Epic E5.10 — Cross-Component Lineage (4 issues)

- **I-5.10.1** Single-turn topic sequence (ordered): user.input → turn.started → task.dispatch → plan.requested → plan.ready → dag.started → step.execute → capability.completed → dag.completed → task.complete → response.final → turn.completed → *(async)* mw.extraction.complete → mw.batch.submitted.
- **I-5.10.2** `cognitive_trace_id` propagated across all envelopes + into K0 atoms.
- **I-5.10.3** `parent_id` causal chain: `task.dispatch` parent = `turn.started.envelope_id`.
- **I-5.10.4** **GAP (SS-04):** All 12 per-turn SS mutations share `cognitive_trace_id` but NOT persisted to SQLite — verify only via in-process event subscription.

## Epic E5.11 — Lifecycle Teardown (6 issues)

- **I-5.11.1** `SSM.start()` FSM CREATED→STARTING→RUNNING; idempotent call raises.
- **I-5.11.2** `StandaloneLifecycle` 30 s checkpoint timer; `stop(checkpoint_before_stop=True)`.
- **I-5.11.3** MW `stop()` flushes in-flight batch; `SessionBatchDispatcher` idle task cancelled cleanly.
- **I-5.11.4** **CLOSED:** Teardown order is verified by M5-L3: `MW.stop()` completes before `SSM.stop()` begins during `KernelService.destroy_session()`.
- **I-5.11.5** `LocalEventAdapter` dispatch queue bounded; joins within 1000 ms (SS-07 partial).
- **I-5.11.6** Reconstruction SLA < 50 ms P95 from LOCAL COLD SQLite (SS-09); no automated test exists.

### M5 highest-priority issues

1. **I-5.8.1 / MW01** — closed by M5-L1 live topic/subscription probe.
2. **I-5.3.4 / B01** — closed by M5-L2 live TTL-drop probe.
3. **I-5.11.4** — closed by M5-L3 live teardown-order probe.
4. **I-5.8.6 / MW04** — closed by M5-L4 live PlaceResolver probe.
5. **I-5.5.4 / SS-03** — `MutationGuard` deadlock.

---

# Milestone M7 — Pseudo-K0 Integration (Recipe-C Live Target)

## Component overview

`scripts/pseudo_k0` is a **FastAPI emulator** that stands in for the real K0 kernel while [k0/](k0/) is still being built. It is the **live integration target** for K1 → Bridge → K0 end-to-end tests today (Recipe-C in [live_kernel_wiring_test_procedure.md](live_kernel_wiring_test_procedure.md)). It is deliberately **not** a full K0: it exercises the wire-level contracts (envelope shape, signing, SSE, connector dispatch, durability) without emulating K0's policy, gate, idempotency, or graph layers.

**Real K0 ([k0/](k0/))** is a separate future milestone; touching `k0/` is out of scope until the pseudo-K0-backed test pyramid stabilises.

## Entry point + structure

| Path | Purpose |
|---|---|
| [scripts/pseudo_k0/**main**.py](scripts/pseudo_k0/__main__.py) | CLI: `python -m scripts.pseudo_k0 --port 8090 --db data/pseudo_k0.db` |
| [scripts/pseudo_k0/server.py](scripts/pseudo_k0/server.py) | FastAPI app factory `create_app()`; endpoint handlers; topic dispatch |
| [scripts/pseudo_k0/store.py](scripts/pseudo_k0/store.py) | `SQLiteK0Store` — WAL + obs_log tables |
| [scripts/pseudo_k0/models.py](scripts/pseudo_k0/models.py) | Pydantic v2 wire models (K0Envelope, RecallRequest/Response, ...) |
| [scripts/pseudo_k0/connector_host.py](scripts/pseudo_k0/connector_host.py) | Pluggable `(adapter_id, action)` dispatch registry for `connector.execute.*` |

## Emulated surfaces

| Endpoint | Method | Purpose |
|---|---|---|
| `/k0/command.submit` | POST | K1 command ingestion; topic-routed |
| `/k0/obs.emit` | POST | K1 observability emission |
| `/k0/sse/{topic}` | GET | SSE stream (heartbeat + push) |
| `/healthz` | GET | Liveness; returns `{ok, wal_rows, obs_rows}` |

### Topic dispatch inside `/k0/command.submit`

| Topic pattern | Behaviour |
|---|---|
| `recall.request.v1` | SQLite WAL `LIKE %query%` (no real FTS/vector) → `RecallResponseV1`-shape JSON |
| `connector.execute.*` | Routed to `ConnectorHost` by `(adapter_id, action)` |
| `k1.tool_state.*` | Persisted to WAL + broadcast to SSE `tool_state.changed.v1` |
| everything else | Persisted to WAL verbatim; ack-only |

## Storage

SQLite at `data/pseudo_k0.db` (or `:memory:`). Two tables: `wal` (one row per command envelope; columns `topic, memory_type, space_id, tenant_id, actor_id, band, trace_id, content, body, envelope`) and `obs_log` (one row per obs).

## Epic E7.1 — Pseudo-K0 ↔ Bridge wiring

- **I7.1.1** `K0_ENDPOINT` env var → `KernelConfig.k0_endpoint` ([k1/concierge/config/kernel.py:86](k1/concierge/config/kernel.py#L86)) → S4 selects LIVE mode → `LiveBridgeAdapter` + `HttpBridgeClient`.
- **I7.1.2** `BridgeConnectionConfig.endpoint` defaults to `http://localhost:8090` ([k1/fabric/adapters/bridge_connection.py:69](k1/fabric/adapters/bridge_connection.py#L69)).
- **I7.1.3** `bridge/contracts/command_port.protocol.yaml` template `{k0_base_url}/k0/command.submit` resolves against `K0_ENDPOINT`.
- **I7.1.4** Pseudo-K0 launch is **manual today** (no auto-launch from `KernelService`, no docker-compose target). Recipe-C SOP must start it as a fixture.

## Epic E7.2 — Memory write round-trip (`memory.write.v1`)

- **I7.2.1** K1 MW → `BridgeCommandAdapter.submit()` → `KernelCommandPort.submit()` → `EnvelopeBuilder` signs → `HttpTransport` POSTs → pseudo-K0 persists in `wal` table.
- **I7.2.2** Envelope provenance fields (`cognitive_trace_id`, `tenant_id`, `space_id`, `band`, `actor_id`) all round-trip to the WAL row.
- **I7.2.3** `bridge_memory_write_v1_*` Prometheus counters incremented on success.
- **I7.2.4** 5xx/429 from pseudo-K0 → `LocalOutbox.enqueue()` durable; `DrainWorker` retries up to 10 attempts.

## Epic E7.3 — Recall (`recall.request.v1`)

- **I7.3.1** K1 emits `recall.request.v1` → pseudo-K0 dispatches to `SQLiteK0Store.recall()` → returns `RecallResponseV1`-shape JSON; LIKE search on `content` projection.
- **I7.3.2** **KNOWN LIMITATION:** `belief`/`graph`/`device`/`session` selector types match no rows in pseudo-K0 ([scripts/pseudo_k0/store.py:22-26](scripts/pseudo_k0/store.py#L22)). Test as empty-bundle response, not as failure.
- **I7.3.3** Hit source tagging (`episodic`/`semantic`) preserved in response.

## Epic E7.4 — Tool-state SSE (`tool_state.changed.v1`)

- **I7.4.1** K1 writes `k1.tool_state.*` envelope → pseudo-K0 persists + broadcasts to SSE.
- **I7.4.2** K1 `KernelService._consume_tool_sse()` task ([k1/kernel/service.py](k1/kernel/service.py)) subscribes to `GET /k0/sse/tool_state.changed.v1` and republishes onto the K1 bus.
- **I7.4.3** SSE heartbeat frames; reconnect on disconnect.

## Epic E7.5 — Connector gateway dispatch (`connector.execute.*`)

- **I7.5.1** K1 `connector.execute.{adapter_id}.{action}` → pseudo-K0 `ConnectorHost.dispatch()` → registered `IMCPHandler`.
- **I7.5.2** Duplicate adapter registration → typed error.
- **I7.5.3** Unknown `(adapter_id, action)` → typed `not_found` error.

## Epic E7.6 — Gap matrix vs real K0

| Real K0 surface | Pseudo-K0 status |
|---|---|
| `bus/` (pub/sub routing) | ❌ ABSENT |
| `gate/` + `policy/` | ❌ ABSENT (signatures accepted but not verified) |
| `security/` | ❌ ABSENT |
| `idem/` + `receipts/` | ❌ ABSENT (no idempotency receipts) |
| `db/` (graph store) | ❌ ABSENT (graph/belief/device/session recall return empty) |
| `query/` FTS/vector | ⚠️ FAKED (LIKE only) |
| `outbox/` + `uow/` | ⚠️ PARTIAL (append-only WAL, no UoW transactions) |
| `sync/` (cross-device) | ❌ ABSENT |
| `scheduler/`, `chaos/`, `perf/`, `qos/` | ❌ ABSENT |
| `sse/` | ✅ EMULATED |
| `connectors/` (MCP gateway) | ✅ EMULATED (pluggable host; handlers external) |

## Epic E7.7 — Tests using pseudo-K0

| File | Coverage |
|---|---|
| [tests/scripts/pseudo_k0/test_store.py](tests/scripts/pseudo_k0/test_store.py) | `SQLiteK0Store` WAL recall, hit source tagging |
| [tests/scripts/pseudo_k0/test_server.py](tests/scripts/pseudo_k0/test_server.py) | HTTP endpoints, SSE streaming, connector dispatch |
| [tests/scripts/pseudo_k0/test_models.py](tests/scripts/pseudo_k0/test_models.py) | Pydantic wire-shape validation |
| [tests/scripts/pseudo_k0/test_connector_host.py](tests/scripts/pseudo_k0/test_connector_host.py) | Registry + dispatch errors |
| [tests/k1/kernel/adapters/test_live_bridge_adapter.py](tests/k1/kernel/adapters/test_live_bridge_adapter.py) | K1 → bridge → pseudo-K0 connect, submit, batch-write, recall |
| [tests/k1/sse/test_tool_state_sse.py](tests/k1/sse/test_tool_state_sse.py) | SSE fan-out via `broadcast_sse` |

### M7 highest-priority issues

1. **I7.1.4** — Pseudo-K0 launch automation (pytest fixture or docker target) — required before Recipe-C can ship as standard CI test.
2. **I7.4.2** — Verify `_consume_tool_sse()` reconnect-on-disconnect under pseudo-K0 process restart.
3. **I7.6 gap matrix** — Document which K1 production flows are silently "succeeding" because pseudo-K0 lacks policy/gate/idem (must be flagged as `xfail-on-real-K0` markers when present).
4. **I7.2.4** — Outbox drain behavior under pseudo-K0 5xx; verify `DrainWorker` retry-then-DLQ semantics.

---

# Milestone M6 — HIL + SelfModel + Scheduler + Retention + Cross-cutting

## Component overview

| Component | Path | Status |
|---|---|---|
| **HIL** | [k1/hil/](k1/hil/) | Scaffold+ — `HumanInTheLoopService`, 5 kinds, SafetyBandPolicy, SuspensionManager, ledger |
| **SelfModel** | [k1/selfmodel/](k1/selfmodel/) | M0/M1 — 5-layer projection (L1 Core/Identity, L2 Personality, L3 Patterns/Goals/Habits, L4 Context RAM, L5 State RAM), `IProjectionStorePort`, constitution signing |
| **Scheduler** | [k1/scheduler/](k1/scheduler/) | **Empty stub** — `__init__.py` only |
| **Retention** | [k1/retention/](k1/retention/) | **Empty stub** |
| **Tracing** | [k1/tracing/](k1/tracing/) | **Empty stub** — no span/correlation-id infrastructure |
| **Supervision** | [k1/supervision/](k1/supervision/) | **Empty stub** — no process supervisor |
| **Learning** | [k1/learning/](k1/learning/) | Architecture complete (LEARNING_LOOP_ARCHITECTURE.md + learning.mmd), impl deferred |
| **Coordination** | [k1/coordination/](k1/coordination/) | Sub-stubs only |

## Epic E6.1 — HIL Port: gate / needs_human / approval (4 issues)

- **I6.1.1** `SafetyBandPolicy.decide()` — all 9 branches across 5 bands × `rhc` × side-effect.
- **I6.1.2** `gate_capability()` publishes `HILEnvelope(kind=CAPABILITY_GATE)` on `k1.hil.request.v1`.
- **I6.1.3** `request_needs_human()` → `SuspensionManager.suspend()` → `LedgerWriter.write_requested()`.
- **I6.1.4** Distinguish `HILKind.APPROVAL` (Planner VALIDATE) vs `HILKind.OVERRIDE` (Orchestrator).

## Epic E6.2 — HIL Lifecycle (5 issues)

- **I6.2.1** `_pending` dict cleanup on timeout; **GAP:** no eviction sweep verified.
- **I6.2.2** Ledger ordering: requested → resolved/timed_out/blocked; `writer=None` silently skips.
- **I6.2.3** **GAP:** `TOPIC_HIL_AUDIT` emission untested; `enable_audit_topic` toggle untested.
- **I6.2.4** **GAP:** `_round_budget` enforcement on `max_clarification_rounds=2` untested.
- **I6.2.5** **GAP:** LLM synthesis path (`ILLMPort.synthesize`) untested; `enable_llm_synthesis` toggle untested.

## Epic E6.3 — HIL Pause/Cancel/Override (4 issues)

- **I6.3.1** Orchestrator `ExecutionMonitor` → `request_override()` (M-29 thresholds hardcoded).
- **I6.3.2** **GAP:** `_shutdown` flag pre-shutdown new-request rejection untested.
- **I6.3.3** `SuspensionManager._timeout_tasks` watcher lifecycle (L-28 Planner stub).
- **I6.3.4** **GAP:** Max-1 concurrent suspension per task untested.

## Epic E6.4 — SelfModel Read (5 issues)

- **I6.4.1** `SelfModelService.read(actor_id)` returns snapshot; L4/L5 never persisted in row (E0 invariant).
- **I6.4.2** L1/L2 seeding from `MetaSection.identity` on first-touch.
- **I6.4.3** **GAP (C-4 cascade):** Concierge integration: Concierge reads snapshot at session start; personality in prompt.
- **I6.4.4** `IProjectionStorePort` ABC: both `MemoryProjectionStore` + `SqliteProjectionStore` satisfy.
- **I6.4.5** **GAP:** `SelfModelReadResult.first_seen` concurrent-read race with RLock.

## Epic E6.5 — SelfModel Updates (4 issues)

- **I6.5.1** `ConstitutionService.ensure_writable()` raises `ConstitutionSafeModeError` on invalid chain; stub validator always returns True.
- **I6.5.2** **GAP:** Amendment lifecycle (DRAFT→PENDING→APPROVED→ACTIVE) is M3 work; not implemented in M1.
- **I6.5.3** **GAP (H-13):** `BridgeAmendmentSyncAdapter` permanently offline — no online BridgeClient.
- **I6.5.4** **GAP:** L3 pattern update emits no bus event; no `TOPIC_SELFMODEL_UPDATED` topic.

## Epic E6.6 — Scheduler (2 issues)

- **I6.6.1** Audit `k1/scheduler/__init__.py` — empty stub; **GAP (M-25):** trigger persistence absent.
- **I6.6.2** Learning Loop System 1 uses SSE push, not polling; **GAP:** SSE offline (H-12, H-13) → no fallback polling.

## Epic E6.7 — Retention (2 issues)

- **I6.7.1** Audit `k1/retention/__init__.py` — empty; SSM 52 KB hot limit depends on retention.
- **I6.7.2** **GAP:** No TTL/prune path on `SqliteProjectionStore`; unbounded growth.

## Epic E6.8 — Tracing (3 issues)

- **I6.8.1** **GAP (CRITICAL):** `k1/tracing/` empty; `trace_id` generated independently per component.
- **I6.8.2** **GAP:** `trace_id` propagation Concierge → Bus → HIL → Ledger broken at every hop.
- **I6.8.3** **GAP (M-40):** `BusStats` counters only; no histograms/spans; Prometheus integration unresolved.

## Epic E6.9 — Supervision (2 issues)

- **I6.9.1** **GAP (H-14/H-15):** `k1/supervision/` empty; real kernel `k1/concierge/kernel/` has no supervisor.
- **I6.9.2** **GAP (M-24/M-25):** `KernelService.shutdown()` force-compensate + persist triggers are V1 no-ops.

## Epic E6.10 — Learning Loop (3 issues)

- **I6.10.1** `k1/learning/` arch docs only; no Python service code.
- **I6.10.2** **GAP:** Signal detectors should hook into `k1.session.turn.completed.v1`, but `k1/tracing/` is empty → cannot build `event_ids[]`.
- **I6.10.3** **GAP (DEFERRED-17 / P7.3):** `KernelObsPort` offline `emit_obs` drops NORMAL/HIGH priority.

## Epic E6.11 — Cross-Cutting Meta Findings (19 issues from `28_consolidated_audit_findings.md`)

### Priority 1 — CRITICAL

- **I6.11.C1** — `PlanStep.to_dict()` omits `safety_band_min` → DAGExecutor safety gate sees None. (See M4 PLN-GAP-02 verify.)
- **I6.11.C2** — `PlannerStateAdapter(reader=None)` — `state_read` tool always fails; plans context-blind.
- **I6.11.C3** — `_contract_to_entry()` assumes `compensation_capability` → may `AttributeError`.
- **I6.11.C4** — Shared Fabric `NullSessionStateReaderAdapter` → PolicyEngine Affective/Cognitive scoring always 0.
- **I6.11.C5** — `IEmbeddingPort` not wired in S4 → Planner `fabric_search` non-functional.
- **I6.11.C6** — **SYSTEMIC:** Three independent session-state blindness gaps: Orch=`MockStateReadAdapter`, Planner=`reader=None`, Fabric=`NullSessionStateReaderAdapter`. Entire Orch→Planner→Fabric pipeline operates without session awareness.

### Priority 1 — HIGH

- **I6.11.H1** — SSM doesn't satisfy Concierge `IStatePort`; `SSMStateAdapter` IS required.
- **I6.11.H2** — 5 of 10 SS adapters are stubs raising `NotImplementedError`: `FabricLifecycleAdapter`, `DeltaBusAdapter`, `ConciergeWriterAdapter`, `BridgeStorageAdapter`, `BridgeSyncAdapter`.
- **I6.11.H3** — WORKFLOW + CONCIERGE Fabric providers: `workflow_registry`, `capability_lookup`, `orchestrator`, `concierge_router` not in `ProviderFactory` — would `ValueError`.
- **I6.11.H4** — Duplicate `IModelHubPort`: ModelHub's has `execute()`, MemoryWriter's has `chat()`. M-18 rename to `IMemoryWriterLLMPort` pending.
- **I6.11.H5** — `MockStateReadAdapter` wired in production — safety gate ALWAYS PASSES (compounds C1).
- **I6.11.H6** — `k1/kernel/` 100% dead code (69 LOC stubs); real kernel `k1/concierge/kernel/`.
- **I6.11.H7** — `bootstrap.py` imports `poc.k1_poc.main.boot()` — architecture boundary violation.
- **I6.11.H8** — 4 of 5 Bridge ports protocol-only: `IKernelQueryPort`, `IKernelSSEPort`, `IKernelObsPort`, `IConnectorGatewayPort`. K1 permanently offline.
- **I6.11.H9** — `emergency.activated` event has NO subscriber — backpressure broken.
- **I6.11.H10** — Planner hot-swap impossible: `_mailbox` in `__slots__`, no setter (Phase 2 blocker).
- **I6.11.H11** — `AdminHttpAdapter.list_circuit_breakers()` `isinstance` bug — always empty dict.
- **I6.11.H12** — Two parallel Concierge runtime types (~200 LOC duplicated): `KernelRuntime` (bootstrap.py) vs `ConciergeRuntime` (session.py).

### Priority 2 — MEDIUM (selected)

- **I6.11.M1** (M-23) — ErrorRouter HIGH→MEDIUM degradation dead code.
- **I6.11.M2** (M-24) — Force-compensate on shutdown V1 no-op.
- **I6.11.M3** (M-25) — Persist triggers on shutdown V1 no-op.
- **I6.11.M4** (M-26/M-32) — `crash_recovery()` calls `bridge_port.read_wal()` → `None`.
- **I6.11.M5** (M-11) — ABC vs Protocol architectural inconsistency.
- **I6.11.M6** (M-17) — `BusEnvelopeDeserializer` event-loop ownership unclear.
- **I6.11.M7** (M-36/L-31) — `PlanRequest` has no `to_dict()`/`from_dict()`.
- **I6.11.M8** (M-41) — `KernelConfig.tool_tier` accepts any string; `runner.py` uses non-matching values.
- **I6.11.M9** (M-42) — `KernelRuntime` undeclared fields via `setattr`.
- **I6.11.M10** (M-39) — `PlannerAgent.start()` not called by factory.

### Priority 3 — LOW (selected)

- **I6.11.L1** — Bus shared vs per-session architecture decision still pending.
- **I6.11.L2** (L-18) — `EventBusAdapter` has no `unsubscribe()` — subscription leak.
- **I6.11.L3** (M-19) — `IBridgeWritePort` name violation: contains `read_wal()`.
- **I6.11.L4** (P6.10) — Doc drift: P6.10 status OPEN in audit vs DONE in wiring plan.
- **I6.11.L5** (L-5) — `SessionState/Factory` depends on `poc.k1_poc.config.get_config()`.

## Epic E6.12 — End-to-End Wiring Requirements (6 issues, from `08_end_to_end_wiring_requirements.md`)

- **I6.12.1** Verify 38/52 ports wired; 14 missing adapters enumerated.
- **I6.12.2** Tier-1 bootstrap 6 shared components (S1–S7).
- **I6.12.3** Tier-2 `create_session()` wires 5 per-session components.
- **I6.12.4** DEFERRED-8..12 (MS-4 Epic 4.2-4.5) still correct next tests.
- **I6.12.5** Bridge DEFERRED-17 P7.1-P7.7 actionability; P7.4 blocking on K0 HTTP.
- **I6.12.6** P2.6 (MW Protocol stub `list[dict]` → `list[CommandEnvelope | dict]`) at [bridge_command_adapter.py:40](k1/memory_writer/adapters/bridge_command_adapter.py#L40) — 1-line fix.

## Epic E6.13 — Phase 6 PR Summary Residuals (5 issues)

- **I6.13.1** Verify P6.10 truly DONE: `k1.model_hub: STRICT` in `bus.yaml` + `defaults.py` parity.
- **I6.13.2** 5 pre-existing non-bus failures remain out-of-scope (asyncio loop, perf SLOs, deep-import policy, runner CLI, fabric_port `AttributeError`).
- **I6.13.3** **GAP:** `IdempotencyMiddleware` `(topic, request_id)` — HIL envelope idempotency key untested.
- **I6.13.4** **GAP:** HIL request topic durability not documented; lost on process restart mid-interaction.
- **I6.13.5** **GAP:** `TopicValidationMiddleware` schema not registered for `k1.hil.request.v1` / `response.v1`.

### M6 critical-path blockers

I6.11.C6 (systemic session-state blindness) + I6.11.C5 (IEmbeddingPort) + I6.11.H5 (MockStateReadAdapter in prod) + I6.11.H7 (POC boot()) must fix before any M6 E2E test can pass.

---

# Consolidated GAP Register (~49 entries)

| Milestone | GAP | Severity | Description |
|---|---|---|---|
| M1 | C02 | High | EpisodicCompressor never wired |
| M1 | C03 | High | `_run_tool()` no `asyncio.wait_for` |
| M1 | C04 | Med | Crash-mid-delivery checks WeaveEmitted not ResponseDelivered |
| M1 | C06 | Low | WeavePolicy has no runtime toggle |
| M1 | C08 | High | `back_resume_handler` fallback returns None silently |
| M1 | C09 | High | StubPhase1 returns fixed values |
| M1 | C10 | Med | WEAVE history window 5-turn |
| M1 | Finding N1 | Med | bootstrap duplicates factory wiring |
| M1 | Finding N5 | High | `_FabricGatewayAdapter` field translation |
| M1 | Finding N6 | High | HIGH-tier path NOT WIRED to K1 Orchestrator |
| M1 | factory race | Low | `set_self_model()` before `start()` no guard |
| M1 | I1.10.5 | Med | `chat_repl` uses legacy bootstrap |
| M2 | I2.1.5 | Low | `health_check()` aggregation unspecified |
| M2 | I2.4.10 | Med | `ssm.stop()` has no timeout guard |
| M2 | I2.5.1 / OPEN §1 | High | `_FirstSessionSSMShim` multi-session bug |
| M2 | I2.5.2 / OPEN §2 | Med | Planner `__shared__` sentinel |
| M2 | I2.4.11 / OPEN §3 | Med | per-session Fabric never torn down |
| M2 | I2.5.3 / OPEN §4 | Low | `max_sessions` unenforced |
| M2 | I2.5.4 / OPEN §7 | Low | Dead config flags |
| M2 | I2.6.3 | Low | `IEmbeddingPort` production adapter undocumented |
| M2 | I2.7.6 | Med | bridge `adapters/` + `connector/` empty |
| M2 | I2.9.1 | Info | `k1/kernel/loader.py` etc. stubs |
| M3 | GAP-3.4.4 | High | Bridge K0_OFFLINE shape undocumented |
| M3 | GAP-3.4.8 | Med | NativeToolProvider absent from CONTRACT |
| M3 | GAP-3.5.2 | Med | WFQ priority queue ordering undocumented |
| M3 | GAP-3.7.7 / M09 | High | Streaming token usage broken for all providers |
| M3 | GAP-3.9.6 / M04 | Med | `repr(payload)` cache key fix unconfirmed |
| M3 | GAP-3.10.1 | Med | `HubRequest.consumer_id` existence unverified |
| M3 | GAP-3.10.2 / M01 | High | 10 bus topics silently suppressed by `from_config` |
| M3 | GAP-3.11.2 | Med | budget→max_tokens translation undocumented |
| M3 | GAP-3.11.4 | Med | `compensation_capability` may not exist |
| M3 | GAP-3.11.6 | High | Concierge POC bypasses ModelHub pipeline |
| M4 | GAP-O02 | High | ConcurrencyGuard mailbox flood |
| M4 | GAP-O03 | Med | WorkflowScheduler CRON restart |
| M4 | GAP-O06 | Low | ExecutionMonitor over-interrupt |
| M4 | GAP-P02 | High | LLMGatewayAdapter private→public import |
| M4 | GAP-P03 | High | ToolCallRouter semantic vs exact |
| M4 | GAP-P04 | Med | ValidationVerdict bypass |
| M4 | PLN-GAP-02 verify | Med | PlanStep.safety_band_min round-trip |
| M5 | B01 | High | Closed by M5-L2: TTL enforced in Python LocalBus |
| M5 | B02 | Med | Sequence gap from middleware drop |
| M5 | B04 | Med | mailbox_full_drops not in DLQ |
| M5 | P6.10 | Med | `k1.model_hub` not STRICT in bus.yaml |
| M5 | SS-01 | Med | task_state/artifacts JSON not FlatBuffer |
| M5 | SS-02 | Med | Dual SQLite class file contention |
| M5 | SS-03 | High | MutationGuard latent deadlock |
| M5 | SS-04 | Med | No mutation audit trail |
| M5 | MW01 | **CRITICAL** | Closed by M5-L1: Concierge/MW topic aligned |
| M5 | MW02 | Med | `_processed_ids` unbounded |
| M5 | MW04 | High | Closed by M5-L4: PlaceResolver refreshed from SS entities |
| M5 | MW06 | High | Correction turn drop |
| M5 | I-5.11.4 | High | Closed by M5-L3: teardown order MW-before-SSM |
| M6 | tracing empty | Critical | `k1/tracing/` empty |
| M6 | supervision empty | High | `k1/supervision/` empty |
| M6 | scheduler empty | Med | `k1/scheduler/` empty |
| M6 | retention empty | Med | `k1/retention/` empty |
| M6 | I6.11.C1-C6 | Critical×6 | Systemic session-state blindness + safety bypass |
| M6 | I6.11.H1-H12 | High×12 | SSM/Fabric/Bridge/Orchestrator/Kernel wiring gaps |

---

# Master Issue Index

| Range | Milestone | Count |
|---|---|---|
| I1.1.1 – I1.10.6 | M1 Concierge | 46 |
| I2.1.1 – I2.9.2 | M2 Kernel + Bridge | 51 |
| I3.1.1 – I3.11.6 | M3 Fabric + ModelHub | 66 |
| I4.1.1 – I4.15.3 | M4 Orchestrator + Planner | 62 |
| I-5.1.1 – I-5.11.6 | M5 Bus + SS + MW | 55 |
| I6.1.1 – I6.13.5 | M6 HIL + SelfModel + Cross-cutting | 64 |
| **TOTAL** | | **344** |

---

# Suggested Execution Order

1. **Foundations first (M2):** Fix kernel composition root + Bridge + lifecycle invariants. Without M2 stable, every other milestone's tests are flaky.
2. **Resolve session-state blindness (M6 C-cluster):** Wire real `IStateReadPort` everywhere; replace all three Null/Mock adapters. This unblocks meaningful integration testing for M1, M3, M4.
3. **Wire Bus + SessionState correctly (M5):** MW01, TTL, teardown order, per-session bus isolation, PlaceResolver refresh, and SS destroy flush are live-verified; remaining M5 focus is MutationGuard deadlock plus the pending X-row probes.
4. **Fabric + ModelHub contract (M3):** Validate 9-step pipeline + LLM gateway; address ISSUE-M01 (4 unwired ports).
5. **Orchestrator + Planner correctness (M4):** Verify S6b cross-wire; resolve P02/P03 import + lookup gaps; depth-limit ConcurrencyGuard.
6. **Concierge end-to-end (M1):** Once all upstream gaps closed, validate Front/Back ReAct loops, FSM transitions, HITL flows.
7. **M6 stub components:** Implement `k1/tracing/`, `k1/supervision/` first (cross-cutting). Defer `k1/scheduler/`, `k1/retention/`, `k1/learning/` until K0 Bridge online.

Each issue becomes a single test (or observability instrumentation) downstream. No code changes are part of this plan.

---

# Cross-Component Integration Wiring Matrix (Live-Kernel)

> **Purpose.** Issue-by-issue tracing matrix for the **cross-component wires** that the original M1–M7 plan treated only inside each component's boundary. Every row below names a real wire in the live `KernelService` object graph (publisher → topic → subscriber, or caller → port → callee, or component → SSM section), the file:line where it lives in production code, and the live-kernel test that must prove it.
>
> **Why this section exists.** The M1–M7 milestones above answer "does component X work internally?". This section answers "is component X **plugged into** components Y and Z **in the live kernel composition root**?". Examples: does Concierge's `turn.completed.v1` actually reach MemoryWriter? Does Planner's `plan.ready.v1` actually reach Orchestrator? Does the per-session `BridgeAwareLocalBus` instance held by Concierge identically match the bus that MemoryWriter subscribes on?
>
> **Method.** Every row maps to one new probe row in [kernel_sweep_status.md](kernel_sweep_status.md) of the form `M<n>-X<k>` (X = cross-component). Probe types: PORT-IDENTITY (same object across components), SUBSCRIPTION (topic registered on right bus), MESSAGE-FLOW (envelope reaches destination), LIFECYCLE (start/stop ordering across components), NEGATIVE (wire absent or wrong).
>
> **Sources.** Verified via parallel subagent reads of: `k1/bus/k1_bus_core.mmd`, `k1/sessionstate/sessionstate.mmd` + `sessionstate_internal.mmd`, `k1/memory_writer/memory_writer.mmd`, `k1/fabric/fabric.mmd` + `fabric_new.mmd`, `k1/model_hub/model_hub.mmd`, `k1/concierge/concierge_unified.mmd` + `concierge_poc_architecture.mmd`, `k1/orchestrator/orchestrator.mmd`, `k1/planner/planner.mmd` + `planner_v2.mmd`, `k1/selfmodel/selfmodel.mmd`, `k1/learning/learning.mmd`, and `k1/kernel/service.py` composition root (S1–S7 + P1–P6).

---

## M2-X — Kernel + Bridge cross-component wires

These extend the existing M2 row set (L1..L10) with explicit cross-component integration assertions that the M2 internal rows do not cover.

| Issue ID | Probe | Wire (publisher · topic / port · subscriber · location) | Production evidence | Expected | Risk if broken |
|---|---|---|---|---|---|
| **I2.X.1** | PORT-IDENTITY | `session.bus is session.concierge._bus`; `session.concierge._router is session.router`; `session.concierge._front_mailbox/_back_mailbox` are the session mailboxes; mailbox/router objects do **not** store `_bus` | `service.py` P1/P4 `_create_session_tier2` ~L2040–2315; `k1/concierge/session.py` ctor | Concierge owns the same per-session `BridgeAwareLocalBus`; mailboxes/router are queue/routing objects only | Front and Back actors publish on different buses → silent message drops |
| **I2.X.2** | PORT-IDENTITY | `session.fabric is not svc._shared_fabric` AND `session.fabric.registry is svc._shared_fabric.registry` | `service.py` P3 + S3 | Two distinct Fabric instances, one shared registry | Per-session events fire on wrong bus or shared CB state corrupts session isolation |
| **I2.X.3** | PORT-IDENTITY | `svc._shared_fabric.facade._context_builder._state_reader is svc._session_routing_reader`; `svc._orchestrator._state_port._reader is svc._session_routing_reader`; `svc._planner._pipeline._sketch._tool_router._state_read._reader is svc._session_routing_reader` | `service.py` S3/S5/S6 | One `SessionRoutingStateReader` injected into Fabric, Orchestrator, and Planner | Three components see different views of the same session's SS |
| **I2.X.4** | PORT-IDENTITY | `svc._model_hub is shared/session Fabric model_gateway._hub`; `session.concierge._model is svc._model_hub`; `svc._planner._pipeline._sketch._llm_port._bus._hub is svc._model_hub`; `session.memory_writer._pipeline._writer_agent._model_hub._hub is svc._model_hub` | `service.py` S2 + S3/S6 + P3/P4/P5 | All call sites point at the same `ModelHub` object | CB state, response cache, and budget enforcement diverge per consumer |
| **I2.X.5** | PORT-IDENTITY | `svc._bridge.get_client()` returns the same singleton across repeated calls and sessions (already proven by M2-L10) | service.py S4 | Same `SinkBridgeClient` | All sessions enqueue to same outbox; otherwise per-session outboxes fragment durability |
| **I2.X.6** | LIFECYCLE | S4 (Bridge mounted) runs **before** any P-phase; P1 (per-session bus) is the **first** session phase; P6 assembly is the **last** | `service.py` `startup()` + `_create_session_tier2` P1..P6 `_log_lifecycle` events | Lifecycle events in this exact order | Reversed: components subscribe on a not-yet-existing bus |
| **I2.X.7** | LIFECYCLE | `destroy_session` teardown emits P6→P1 events in order AND P5 (MW.stop) completes before P2 (SSM.stop) — MW must drain before SSM shutdown | `service.py` `destroy_session` + `MemoryWriterService.stop()` + `SessionStateManager.stop()` | MW lifecycle event `P5_teardown_complete` precedes SSM `P2_teardown_complete` | MW flushes against a stopped SSM → silent data loss |
| **I2.X.8** | NEGATIVE | `AsyncSSMBridge` is constructed at P2 but **not injected** into any P3–P5 component | `service.py` P2 around `async_ssm = AsyncSSMBridge(ssm)` | `async_ssm` reference is unused outside its construction site | Dead code masquerading as a wire; future maintainers may assume async surface is active |

---

## M3-X — Fabric + ModelHub cross-component wires

| Issue ID | Probe | Wire | Production evidence | Expected | Risk |
|---|---|---|---|---|---|
| **I3.X.1** | MESSAGE-FLOW | One `session_fabric.execute()` of an LLM-backed capability emits **both** `k1.capability.completed.v1` (session bus) **and** `k1.model_hub.response.complete.v1` (shared bus) with matching `trace_id` | `Fabric._execute_impl` step 7 + `RequestRouter._route_inner` | Both topics observed with same `trace_id` | Trace continuity lost; ops cannot correlate user request to provider call |
| **I3.X.2** | SUBSCRIPTION | `k1.fabric.learning.signal.v1` (Fabric step 9) is emitted on the **session bus** after every `execute()` — both success and failure paths | `Fabric._execute_impl` step 9 + `EventEmitter.emit_learning` | Topic count ≥ 1 in session_bus captured | K0 never receives learning feedback; LEARN-* invariants silently fail |
| **I3.X.3** | SUBSCRIPTION | `k1.model_hub.circuit.state.v1` is published to the **shared bus** on each CB state transition (CLOSED→OPEN, OPEN→HALF_OPEN, HALF_OPEN→CLOSED) | `CircuitBreakerManager` + `MHEventBusAdapter` | One topic publish per transition | Dashboards/Ops have no observability into provider failure cascades |
| **I3.X.4** | MESSAGE-FLOW | Provider failure cascade: `k1.model_hub.provider.failure.v1` (with `will_fallback=true`) → `k1.model_hub.fallback.triggered.v1` → final `k1.model_hub.response.complete.v1` — all on shared bus, in this order | `ProviderDispatcher` fallback path | Three topics in this exact sequence | Silent fallback to secondary provider; cost/latency anomalies invisible |
| **I3.X.5** | NEGATIVE | Output validation failure path: a capability that returns malformed output emits `k1.fabric.output.validation.failed.v1` on session bus and `CapabilityResult.success=False, error_code="output_validation_failed"` | `Fabric._validate_output` + `_execute_impl` failure branch | Topic observed + result shape correct | Callers see generic failure; no signal for schema regression |
| **I3.X.6** | MESSAGE-FLOW | Planner LLM call (any stage) fires `k1.model_hub.request.received.v1` on the **shared bus** with `consumer_id="planner"` and emits **no** `k1.capability.*` events | `PlannerAgent.PlannerPipeline` + `ModelHubRequestBus` | MH topic present, Fabric topic absent | Confused trace topology; planner LLM cost attributed to wrong consumer |
| **I3.X.7** | MESSAGE-FLOW | MW LLM call (extraction stage) fires `k1.model_hub.request.received.v1` with `consumer_id="memory_writer"` | `MemoryWriterPipeline` S4 + `ModelHubAdapter` | Topic present with correct `consumer_id` | Budget attribution wrong; MW circuit breaker decisions misinterpreted |
| **I3.X.8** | NEGATIVE | Two undocumented MH topics actually emitted: `k1.model_hub.request.completed.v1` and `k1.model_hub.request.failed.v1` — assert their actual emission so the contract/code mismatch is locked in | `RequestRouter.route()` + `_route_inner()` exception paths | Both topics published | events.py contract drifts further from code; observability false-negatives |
| **I3.X.9** | NEGATIVE | `k1.model_hub.budget.alert.v1` referenced in `model_hub.mmd` (EVT_BUDGET_ALERT) is **not** emitted by any production code path | `events.py` + `request_router.py` | Topic never observed; GAP locked in xfail strict=True | Budget enforcement (MH-04 HARD) has no observable signal |

---

## M5-X — Bus + SessionState + MemoryWriter cross-component wires

The M5 milestone is the most under-specified in the original plan — its existing L1..L6 rows are internal smoke checks, not integration. The rows below are the actual integration probes.

### M5-X.A — Bus subscription topology (per-session)

| Issue ID | Probe | Wire | Verified in current plan? |
|---|---|---|---|
| **I-5.X.1** | SUBSCRIPTION | `session.bus.list_subscriptions()` after P1..P6 contains only component-owned subscribers; Recipe A currently has 28 live subscriptions, including two intentional `k1.session.user.input.v1` owners (FSM + input port) | covered by `tests/integration/k1/live/m5/test_m5_x1_x5_subscription_identity.py` |
| **I-5.X.2** | NEGATIVE | After `destroy_session`, `session.bus.list_subscriptions()` is empty AND no captured handler reference outlives teardown | covered by `tests/integration/k1/live/m5/test_m5_x1_x5_subscription_identity.py` |
| **I-5.X.3** | NEGATIVE | `BridgeAwareLocalBus` raises `UnknownContractError` on direct publish of any topic in `bridge_topics` (memory.write.v1, recall.request.v1, etc.) — already proven by M2-L8 | covered by M2-L8 |

### M5-X.B — SessionState ↔ component contract

| Issue ID | Probe | Wire | Production evidence |
|---|---|---|---|
| **I-5.X.4** | PORT-IDENTITY | `concierge._session_state._ss is session.session_state` AND `front/back_ctx.writer_port._manager is session.session_state` — Concierge reads/writes go through one SSM | covered by `tests/integration/k1/live/m5/test_m5_x1_x5_subscription_identity.py`; production uses `SSMStateAdapter._ss`, not `_manager` |
| **I-5.X.5** | PORT-IDENTITY | `memory_writer._pipeline._session_reader._port._manager is session.session_state` | covered by `tests/integration/k1/live/m5/test_m5_x1_x5_subscription_identity.py` |
| **I-5.X.6** | NEGATIVE | MW has **no** write port to SSM (MW-01 invariant: single-writer). After a full turn, spy on `ssm.mutate()` and assert MW is not a caller | covered by `tests/integration/k1/live/m5/test_m5_x6_x10_ss_mw_turn_flow.py`; MW session reader is `SessionReadAdapter`, exposes no mutation methods, and the live `ssm.mutate` spy sees zero MW calls during turn flush |
| **I-5.X.7** | LIFECYCLE | After `ssm.start()` returns, `DirectWriterAdapter.request_mutation()` accepts mutations; before it, mutations raise `LifecycleError` | covered by `tests/integration/k1/live/m5/test_m5_x6_x10_ss_mw_turn_flow.py`; production guard added in `DirectWriterAdapter.request_mutation()` for unbound/not-running managers |
| **I-5.X.8** | NEGATIVE | SSM eviction events (`sessionstate.eviction.triggered`) fire on `LocalEventAdapter` only — they are **not** published to `session_bus` | covered by `tests/integration/k1/live/m5/test_m5_x6_x10_ss_mw_turn_flow.py`; live P2 event port is `LocalEventAdapter(capture_mode=False)` and session-bus spy observes no `sessionstate.eviction.*` publish |
| **I-5.X.9** | PORT-IDENTITY | `mw._session_read_port._cold_archive is ssm.get_local_cold_archive()` — MW's cold-archive view is the same object as SSM's | covered by `tests/integration/k1/live/m5/test_m5_x6_x10_ss_mw_turn_flow.py`; `SessionReadAdapter._cold_archive` is the live SSM `LocalColdArchive` identity |

### M5-X.C — Concierge → MW message-flow (the ISSUE-MW01 cluster)

| Issue ID | Probe | Wire | Verified? |
|---|---|---|---|
| **I-5.X.10** | MESSAGE-FLOW | Live LOW turn: `ConciergeController._emit_turn_completed` (controller.py ~L3672) publishes `k1.session.turn.completed.v1` with full payload (`turn_id`, `session_id`, `cognitive_trace_id`, `user_message`, `assistant_response`, `timestamp_ms`, `turn_number`); a live session-bus subscriber captures the published envelope | covered by `tests/integration/k1/live/m5/test_m5_x6_x10_ss_mw_turn_flow.py` |
| **I-5.X.11** | SUBSCRIPTION | After `mw.start()` (P5), `session.bus.list_subscriptions()` contains the default `SessionBatchDispatcher` subscription on `k1.session.turn.completed.v1`; after `mw.stop()` it does **not** | covered by M5-L1 |
| **I-5.X.12** | NEGATIVE | **Topic identity assertion closed:** `TurnDispatcher.TOPIC == TOPIC_TURN_COMPLETED == "k1.session.turn.completed.v1"` | covered by M5-L1 |
| **I-5.X.13** | MESSAGE-FLOW | Concierge → MW pipeline: feed a real turn through the live kernel; assert `MWSessionReader.snapshot()` was called with `history_active` containing the turn just published. Race: SS write must complete before MW reads | covered by `tests/integration/k1/live/m5/test_m5_x13_x15_concierge_mw_e2e.py`; current production path is `MWSessionReader.read_snapshot_enriched()`, and the captured live snapshot contains the turn written by Concierge before `turn.completed` publish |
| **I-5.X.14** | NEGATIVE | Same `turn_id` published twice → `TurnDispatcher._processed_ids` dedups; `pipeline.process()` called exactly once | covered by `tests/integration/k1/live/m5/test_m5_x13_x15_concierge_mw_e2e.py`; default session-batch path dedups in `SessionBatchDispatcher._processed_ids`, leaving one buffered turn and one `process_session()` call |
| **I-5.X.15** | MESSAGE-FLOW | After complete turn passing R1–R6 filters → `IBridgeCommandPort.submit_batch()` called with topic `memory.delta` and body containing `cognitive_trace_id != ""` (MW-10) | covered by `tests/integration/k1/live/m5/test_m5_x13_x15_concierge_mw_e2e.py`; live Concierge + MW pipeline uses controlled model/bridge external edges and submits `memory.delta` envelopes with non-empty trace id in envelope, headers, and body |
| **I-5.X.16** | MESSAGE-FLOW | MW circuit breaker open path: 3 consecutive LLM failures → `CircuitBreaker.is_open == True`, 4th turn skips `MemoryWriterAgent`, `k1.mw.circuit.open.v1` published on session bus | covered by `tests/integration/k1/live/m5/test_m5_x16_x19_mw_cb_concierge_guards.py`; production now exposes `MemoryWriterAgent.last_error` and `MemoryWriterPipeline` records model-edge failures against the CB before the fourth-turn open-path publish |
| **I-5.X.17** | LIFECYCLE | `_emitted_turn_ids` set on `ConciergeController` prevents double-publish of same `turn_id` when dispatch+complete + proactive delivery race | covered by `tests/integration/k1/live/m5/test_m5_x16_x19_mw_cb_concierge_guards.py`; live Recipe A publishes one ledger-scoped `turn.completed`, then a second same-turn emit is skipped by `_emitted_turn_ids` |
| **I-5.X.18** | NEGATIVE | `_ledger == None` degenerate path: `turn_id` degrades to `"turn:{N}"` and `session_id==""`. MW dedup operates global → cross-session collision. Assert this path is rejected by MW or by `_emit_turn_completed` precondition | covered by `tests/integration/k1/live/m5/test_m5_x16_x19_mw_cb_concierge_guards.py`; production `_emit_turn_completed` now requires a session-scoped id from ledger or envelope and rejects the unscoped `turn:{N}` path before publishing |
| **I-5.X.19** | NEGATIVE | Duplicate `dag.completed` subscription bug (`TOPIC_DAG_COMPLETED` + bare `"k1.orchestration.dag.completed"`) — assert handler fires exactly **once** per event in live kernel | covered by `tests/integration/k1/live/m5/test_m5_x16_x19_mw_cb_concierge_guards.py`; live session bus has one `TOPIC_DAG_COMPLETED` subscription, no bare duplicate, and one `dag.completed.v1` event normalizes to exactly one `task.complete.v1` |

---

## M1-X — Concierge cross-component wires

| Issue ID | Probe | Wire | Production evidence |
|---|---|---|---|
| **I1.X.1** | PORT-IDENTITY | All five Concierge ports (`_input_port`, `_output_port`, `_state_port`, `_llm_port`, `_dispatch_port`) are non-None and bound to **session-local** objects (bus is `session.bus`, SSM is `session.session_state`, ModelHub is shared `svc._model_hub`) | `service.py` P4 |
| **I1.X.2** | SUBSCRIPTION | FSM subscribes exactly to the topic set in CONTRACT §4 — no extra subscriptions, no missing subscriptions | `ConciergeController._subscribe_topics` |
| **I1.X.3** | MESSAGE-FLOW | LOW-tier happy path: `k1.session.user.input.v1` → Front ReAct → `IDispatchPort.dispatch_direct(CapabilityRequest)` → `FabricDispatchAdapter` → `session_fabric.execute()` (single call, no `dispatch_envelope`) | LOW-tier short circuit |
| **I1.X.4** | MESSAGE-FLOW | MED-tier dispatch flow: Front emits `k1.orchestration.task.dispatch.v1` on session bus → BackHandler enters ReAct loop → emits `k1.orchestration.task.complete.v1` → Front DELIVERING | actors/front.py + actors/back.py |
| **I1.X.5** | MESSAGE-FLOW | HIGH-tier path: `dispatch_envelope(TaskEnvelope)` → `OrchestratorService.process()` → if HIGH: `PlannerAdapter.request_plan()` → DAG → `AggregatedResult` → Back → `task.complete.v1`. Today this path is **not wired end-to-end** (I1.5.1) — assert xfail strict=True | I1.5.1 / Finding N6 |
| **I1.X.6** | MESSAGE-FLOW | `task.complete.v1` on session bus → FSM transition to DELIVERING; final response emitted via `k1.response.final.v1`; FSM returns to LISTENING | controller.py state machine |
| **I1.X.7** | MESSAGE-FLOW | `turn_end()` → `k1.session.turn.completed.v1` published; `_emitted_turn_ids` records the id; same turn cannot be re-emitted | controller.py L3630–3693 |
| **I1.X.8** | NEGATIVE | CRISIS safety_band turn → FSM stays LISTENING, response is hardcoded `CRISIS_STATIC` constant, no LLM call, no Fabric dispatch | Front guard logic |
| **I1.X.9** | NEGATIVE | `WriteElisionGate`: backchannel (e.g. "ok") turn writes only `control.safety_band` (1 mutation), elides the other 5 SS sections | `MutationGuard` audit |
| **I1.X.10** | MESSAGE-FLOW | HITL suspend: Back emits `k1.orchestration.task.suspended.v1` → FSM enters CLARIFYING_WORKER → external clarification via `k1.hil.response.v1` → Front emits `k1.orchestration.task.resume.v1` → `back_resume_handler` resumes ReAct with remaining budget | HIL flow |
| **I1.X.11** | NEGATIVE | `set_self_model()` after `start()` raises guarded error (I1.10.2); does **not** corrupt FSM state | concierge factory |
| **I1.X.12** | NEGATIVE | Duplicate `dag.completed` subscription fires handler exactly once per event (matches I-5.X.19) | controller.py |

---

## M4-X — Orchestrator + Planner cross-component wires

| Issue ID | Probe | Wire | Production evidence |
|---|---|---|---|
| **I4.X.1** | PORT-IDENTITY | `orch._planner_port` is real `PlannerAdapter` (not `MockPlannerAdapter`); `orch._planner_port._mailbox is svc._planner.get_mailbox()` — already proven by M2-L2 | covered by M2-L2 |
| **I4.X.2** | PORT-IDENTITY | `orch._state_adapter._reader is svc._session_routing_reader` (shared with Fabric + Planner) | service.py S5 |
| **I4.X.3** | PORT-IDENTITY | Per-session `FabricDispatchAdapter._orchestrator is svc._orchestrator` — single shared orchestrator across sessions | service.py P4 |
| **I4.X.4** | MESSAGE-FLOW | HIGH-tier envelope into Orchestrator → `PlannerMailboxAdapter.depth() > 0` before Planner drains → Planner emits `k1.planner.plan.ready.v1` on **kernel bus** → Orchestrator `EventSubscriptionAdapter` receives `CommittedPlan` | service.py S6b verify_crosswire |
| **I4.X.5** | MESSAGE-FLOW | `CommittedPlan` with 2 waves → `DAGEngine` calls `FabricGatewayAdapter.execute_batch()` twice → `AggregatedResult` returned to Back Actor | orchestrator.mmd DAG_EXECUTOR |
| **I4.X.6** | MESSAGE-FLOW | Planner `query_planning_context(session_id=sid1)` reads `sid1`'s SS, **not** `sid2`'s (sentinel `""` bug guard) | I2.5.2 follow-up |
| **I4.X.7** | NEGATIVE | CB_PLANNER OPEN → HIGH envelope arrives → Orchestrator degrades to MED path (calls Fabric directly, skips Planner) — `PlannerAdapter.request_plan` call count == 0 | CB integration |
| **I4.X.8** | NEGATIVE | Planner publishes `k1.planner.plan.failed.v1` → `dispatch_envelope()` returns within timeout (not hang); Back emits `task.complete.v1` with degraded result | I1.5.1 follow-up |
| **I4.X.9** | MESSAGE-FLOW | Planner Stage-1 SKETCH calls `FabricRetrievalAdapter.discover_capabilities()` → returns capabilities registered in `_shared_registry`; a freshly-registered test capability appears in candidate list | planner_v2.mmd Stage 1 |
| **I4.X.10** | MESSAGE-FLOW | MicroReplan: ORCH-13 → `PlannerAdapter.micro_replan(MicroReplanRequest)` → Planner emits partial `CommittedPlan` (remaining steps only) | orchestrator.mmd + planner_v2.mmd PLAN-12 |
| **I4.X.11** | LIFECYCLE | `OrchestratorService.start()` runs at S6a; `PlannerAgent.start()` runs at S6; cross-wire verification at S6b — exact order asserted | service.py S6, S6b |
| **I4.X.12** | NEGATIVE | Workflow-triggered run (cron via `WorkflowScheduler`) returns `AggregatedResult` but has no Back Actor handle → return-path gap. Today this is an open architectural hole; xfail strict=True | orchestrator.mmd workflow path |
| **I4.X.13** | NEGATIVE | `k1.hil.progress.v1` emitted by `ExecutionMonitor` on kernel bus — does it reach Concierge PROGRESSING state on **session bus**? Cross-bus bridge integration | orchestrator.mmd ExecutionMonitor + bridge adapter |

---

## M6-X — Cross-cutting (SelfModel · HIL · Supervision · stubs)

### M6-X.A — SelfModel (when `enable_self_model=True`)

| Issue ID | Probe | Wire | Production evidence |
|---|---|---|---|
| **I6.X.1** | PORT-IDENTITY | After P3.5: `session.front_dispatcher._policy_gate is self_model_handle.gate.evaluate` AND same for `session.back_dispatcher` | `SelfModelHandle.install_into_session` |
| **I6.X.2** | LIFECYCLE | `install_into_session` is idempotent (second call is safe); `uninstall_from_session` restores originals exactly | selfmodel handle code |
| **I6.X.3** | MESSAGE-FLOW | Tool call returning `REQUIRE_CONFIRMATION` from `PolicyEvaluator` → `ConciergePolicyGate.evaluate` blocks dispatch → `HumanInTheLoopService.ask_approval()` invoked → response on `k1.hil.response.v1` → Back resumes | selfmodel + HIL integration |
| **I6.X.4** | LIFECYCLE | `SelfModelServiceBundle.shutdown()` closes owned SQLite store; second call idempotent (no double-close) | bundle teardown |
| **I6.X.5** | NEGATIVE | `enable_self_model=False` → `_self_model_bundle is None`, P3.5 skipped, session has no dispatcher gate, no SelfModel topics fire during a full turn | feature flag gate |
| **I6.X.6** | LIFECYCLE | `bundle.health()` returns `status="degraded"` when `ConstitutionService.get_active()` raises; `"safe_mode"` when `safe_mode=True`; `"ok"` otherwise | health probe |

### M6-X.B — HIL Service (when `enable_hil_service=True`)

| Issue ID | Probe | Wire | Production evidence |
|---|---|---|---|
| **I6.X.7** | SUBSCRIPTION | `HumanInTheLoopService` subscribes to `k1.hil.response.v1` on **session bus**; `ask_approval()` publishes `k1.hil.request.v1` and awaits Future resolved by `_on_response()` | hil/service.py |
| **I6.X.8** | NEGATIVE | `SafetyBandPolicy.decide()` ALLOW early-exit: GREEN + no-side-effects returns ALLOW without publishing to bus — assert zero `k1.hil.request.v1` emissions for safe tool calls | hil/policy.py |
| **I6.X.9** | LIFECYCLE | `SuspensionManager` limits: 3rd suspension on same task_id raises; 2nd concurrent suspension on same task raises; timeouts (clarification=60s, approval=120s, selection=90s) auto-cancel FSM | suspension_manager.py |
| **I6.X.10** | MESSAGE-FLOW | `back_resume_handler` re-reads SS at resume time → fresh snapshot used (not stale stored snapshot from suspension) | back.py resume path |
| **I6.X.11** | NEGATIVE | `enable_hil_service=False` → `svc._hil_service is None`; planner/fabric/concierge factories receive `None`; HIL is replaced by `_NullHILAdapter`; no `k1.hil.*` topics emitted during a full turn | feature flag gate |

### M6-X.C — Supervision (currently a stub)

| Issue ID | Probe | Wire | Production evidence |
|---|---|---|---|
| **I6.X.12** | NEGATIVE (lock-in) | `k1/supervision/__init__.py` is empty; no supervision tree wired in `KernelService`. Today the only cancellation is per-task `CancellationToken`. Lock this as xfail strict=True until supervision shipped | `k1/supervision/` |
| **I6.X.13** | MESSAGE-FLOW | `back_cancel_handler` receives `k1.orchestration.task.cancel.v1` → `CancellationToken.cancel()` → running `react_loop.cancellation_check()` exits before `max_iterations` | back.py + react/loop.py |

### M6-X.D — Learning · Retention · Scheduler · Tracing (stub cluster)

| Issue ID | Probe | Wire | Production evidence |
|---|---|---|---|
| **I6.X.14** | NEGATIVE (lock-in) | `k1/learning/__init__.py`, `k1/retention/__init__.py`, `k1/scheduler/__init__.py`, `k1/tracing/__init__.py` are all empty. None of these subscribe to the per-session bus. None of these touch SSM. Lock these as xfail strict=True until shipped | each module's `__init__.py` |
| **I6.X.15** | NEGATIVE | Learning loop invariant LEARN-01: learning loop never writes SSM (ADR-0017 single-writer Concierge). When learning is implemented, this row guards against regression | LEARN-01 invariant |

---

## Summary — new rows landed in `kernel_sweep_status.md`

Each issue above maps to one new probe row in the sweep tracker. Naming convention: `M<n>-X<k>` where X = cross-component integration.

| Milestone | New rows | Issue prefix |
|---|---|---|
| M2 | M2-X1..X8 | I2.X.* |
| M3 | M3-X1..X9 | I3.X.* |
| M5 | M5-X1..X19 | I-5.X.* |
| M1 | M1-X1..X12 | I1.X.* |
| M4 | M4-X1..X13 | I4.X.* |
| M6 | M6-X1..X15 | I6.X.* |
| **TOTAL new** | **76 cross-component rows** | |

These are **in addition to** the existing L1..Ln per-milestone rows. The original rows answer "does the component work?"; the X-rows answer "is the component plugged in correctly?".

> **Operational note.** When a milestone receives its production-grade stamp, both its `L*` rows AND its `X*` rows must be green or strict-xfail. The five acceptance gates apply to the combined set.
