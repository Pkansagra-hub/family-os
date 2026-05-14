# K1 Kernel Sweep — Testing Status Tracker

> **Purpose.** Formal checkpoint document for the K1 kernel-level testing sweep.
> Each row tracks one live-wiring probe step. Check the box when the step has a
> green test in `tests/integration/k1/live/<milestone>/`. A milestone receives the
> **production-grade stamp** only when every row in its section is checked AND all
> five acceptance gates (§ Acceptance Gates) pass.
>
> **How to update.** After each probe step: (1) change `[ ]` to `[x]`, (2) fill
> `Verdict`, `Test file`, and `Notes`, (3) commit.
>
> **Legend.**
>
> - `[ ]` = not yet tested
> - `[x]` = tested and green (or xfail confirmed for GAP probes)
> - `[~]` = in progress
> - `[!]` = tested but blocked / unexpected failure — see Notes
>
> **Companion docs.**
>
> - [k1_flows_availability_matrix.md](k1_flows_availability_matrix.md)
> - [kernel_tracing_plan.md](kernel_tracing_plan.md)
> - [live_kernel_wiring_test_procedure.md](live_kernel_wiring_test_procedure.md)
> - [architecture_diagrams/k1/K1_FLOWS.md](../../architecture_diagrams/k1/K1_FLOWS.md)

---

## Execution Order

```text
M2 → M5 → M3 → M1 → M4 → M6 → M7
```

## Sweep Workflow

For every milestone row, use the same co-develop / co-test / co-integration loop:

1. Invoke subagents to read the target flow end to end, covering both documentation and production code for the component or components being tested.
2. Identify any GAPs or missing prerequisites. If production code cannot support the verification yet, implement the smallest production change needed before writing the live test.
3. Update the touched component documentation as applicable: `WIRING.md`, `OPEN_ISSUES.md`, `STATE.md`, and `CONTRACT.md`.
4. Write and run the live-kernel test using the probe shapes in `live_kernel_wiring_test_procedure.md`.
5. Update this tracker row with `Status`, `Verdict`, `Test file`, and `Notes`. Stamp the milestone production-ready only after every row is green or strict-xfail and all acceptance gates pass.

Critical-path blockers from `kernel_tracing_plan.md` are **not** a separate pre-sweep batch. Treat them as priority issue rows that land during their owning milestone execution. When the sweep reaches one of those blocker rows, complete the full loop above — read, fix if needed, update docs, test, then stamp the row — before moving past it.

## Within-Milestone Probe Order

Use the SOP §3 probe pattern inside each milestone. Prefer this order when choosing the next test to write:

1. **PORT-IDENTITY** — prove the live object graph is wired to the expected real objects.
2. **SUBSCRIPTION-TOPOLOGY** — prove publishers and subscribers meet on the real bus topics.
3. **MESSAGE-FLOW** — drive real envelopes end to end only after identity and topology are known.
4. **LIFECYCLE-ORDER** — verify startup, teardown, flush, and leak behaviour on the live kernel.
5. **NEGATIVE-WIRE** — intentionally break one wire and assert the failure is loud, typed, or captured.

The milestone tables remain the actionable source of truth. If a row appears earlier than its probe type would normally suggest, handle any prerequisite identity/topology checks first and record that dependency in `Notes`.

---

## Prerequisites — Introspection Hooks

These hooks must exist before any live test can be written. Check them off first.

| # | Hook | Owner | Status | Notes |
| --- | --- | --- | --- | --- |
| H1 | `svc.describe_wiring() -> WiringSnapshot` | KernelService | `[x]` | implemented |
| H2 | `bus.list_subscriptions() -> list[(topic, handler_qualname)]` | LocalBus | `[x]` | implemented |
| H3 | `svc.lifecycle_events() -> list[LifecycleEvent]` | KernelService | `[x]` | implemented |
| H4 | `fabric.describe_capabilities() -> list[CapDescriptor]` | CapabilityFabric | `[x]` | implemented |
| H5 | `model_hub.describe_routes() -> list[RouteDescriptor]` | ModelHub | `[x]` | implemented |
| H6 | `ssm.pending_writes() -> int` | SessionStateManager | `[x]` | implemented |

---

## M2 — Kernel + Bridge

**Boot recipe:** A (SINK for L9, Recipe-D gated for outbox)
**Issues covered:** 30 (22 L + 8 X) | **GAPs covered:** 6
**Production-grade stamp:** `[ ]`

| Step | Probe type | Target | Tracing refs | Status | Verdict | Test file | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M2-L1 | LIFECYCLE | Startup S1→S7, shutdown S7→S1 (wrapper-recorded sequence) | E2.2, I2.1.3 | `[x]` | green | `tests/integration/k1/live/m2/test_m2_l1_kernel_lifecycle.py` | Recipe A live `KernelService`; lifecycle events assert startup/shutdown order; workflow SQLite storage close added. |
| M2-L2 | PORT-IDENTITY | S6b: `orchestrator._planner_port` is real `PlannerAdapter` over live planner mailbox (not Mock) | E2.3 | `[x]` | green | `tests/integration/k1/live/m2/test_m2_l2_planner_orchestrator_crosswire.py` | Recipe A live `KernelService`; asserts `PlannerAdapter`, not `MockPlannerAdapter`, mailbox identity with `svc._planner.get_mailbox()`, diagnostics edge, S6b before S7. |
| M2-L3 | PORT-IDENTITY | Per-session Fabric reader is real (`NullSessionStateReaderAdapter` forbidden) | E2.4 | `[x]` | green | `tests/integration/k1/live/m2/test_m2_l3_fabric_state_reader.py` | Recipe A live `KernelService`; 2 sessions; asserts `SessionStateReaderAdapter`, not `NullSessionStateReaderAdapter`; `reader._manager is session.session_state` (SSM identity); `reader._session_id == session_id`; readers are independent across sessions. |
| M2-L4 | NEGATIVE | `_FirstSessionSSMShim` — 2 sessions, distinct SS reads via ModelHub; assert results differ (expected xfail OPEN §1) | I2.5.1 | `[x]` | xfail | `tests/integration/k1/live/m2/test_m2_l4_modelhub_session_state_isolation.py` | `_NullSSMShim` confirmed: both sessions return identical `StateSnapshot(sections={})`. Structural port-presence test is green. Isolation xfail strict=True; unblocks at 3.1.x (thread session_id through IStateReadPort). Null/Mock audit in test docstring. |
| M2-L5 | NEGATIVE | Planner `state_port` sentinel `"__shared__"` → always None (expected xfail OPEN §2) | I2.5.2 | `[x]` | xfail | `tests/integration/k1/live/m2/test_m2_l5_planner_state_port_sentinel.py` | Sentinel cleaned up to `""` (was `"__shared__"`, task 3.1.2 partial). Structural adapter presence test green. xfail strict=True: sentinel `""` resolves `_sessions[""]` → empty `SessionSnapshot`. Direct read with real session_id WORKS — gap is that `PlannerAgent` never threads `session_id` through pipeline to `ToolCallRouter.read_context`. Fix: thread `PlanRequest.context.session_id` (3.1.x). |
| M2-L6 | LIFECYCLE | `destroy_session` reverses P6→P1; `_sessions[id]` gone, per-session Fabric `shutdown()` called, P6→P1 lifecycle events logged in order | I2.4.7, I2.4.11 | `[x]` | green (4/4) | `tests/integration/k1/live/m2/test_m2_l6_destroy_session_lifecycle.py` | Fixed OPEN §3 (Fabric.shutdown 3.3.1 already present); added `_log_lifecycle` calls for P6_teardown_start + P5..P1 teardown_complete |
| M2-L7 | NEGATIVE | `max_sessions=2`, create 3rd → `RuntimeError`; release-and-recreate works; duplicate-ID guard fires before max-sessions guard; `max_sessions=0` rejects first create | I2.5.3 | `[x]` | green (4/4) | `tests/integration/k1/live/m2/test_m2_l7_max_sessions_limit.py` | I2.5.3 / OPEN §4 CLOSED — guard at `service.py:789–792` already enforced; tracker row was stale xfail. |
| M2-L8 | SUBSCRIPTION | `BridgeAwareLocalBus` refuses publish on reserved topic; bus type wired into per-session P1; two sessions independent; known topics `memory.write.v1` / `recall.request.v1` guarded; non-reserved topics pass | I2.7.5, I2.7.11 | `[x]` | green (5/5) | `tests/integration/k1/live/m2/test_m2_l8_bridge_aware_bus_guard.py` | Production fix: wrapped raw session bus with `BridgeAwareLocalBus` at P1 of `_create_session_tier2`; I2.7.11/R10 gap closed. |
| M2-L9 | MESSAGE-FLOW | `SinkBridgeClient.submit_command` round-trip through `LocalOutbox`; SINK mode adapter identity; WAL row PENDING with correct topic + body JSON; multiple submits accumulate; MS-3c/3d placeholders None; offline mode get_client()=None | I2.7.2, I2.7.4 | `[x]` | green (5/5) | `tests/integration/k1/live/m2/test_m2_l9_sink_bridge_client_round_trip.py` | SINK mode: `bridge_enabled=True` + empty `k0_endpoint` → `SinkBridgeAdapter`. I2.7.4 MS-3c/3d surfaces confirmed None. |
| M2-L10 | PORT-IDENTITY | `bridge_client` identity is the same object across all sessions | I2.7.7 | `[x]` | green (5/5) | `tests/integration/k1/live/m2/test_m2_l10_bridge_client_identity.py` | Tier 1 `SinkBridgeAdapter` is created once at S4; `get_client()` returns the same `SinkBridgeClient` singleton across repeated calls, across two sessions, and after destroy+recreate. OFFLINE mode returns None in all cases. |

### M2 — Cross-component integration probes

| Step | Probe type | Target | Tracing refs | Status | Verdict | Test file | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M2-X1 | PORT-IDENTITY | `session.bus is session.concierge._bus`; Concierge router/mailbox attrs match `SessionInstance`; mailbox/router objects have no `_bus` | I2.X.1 | `[x]` | green (5/5 file) | `tests/integration/k1/live/m2/test_m2_x1_x5_port_identity.py` | Corrected original row wording: `front_mailbox._bus`, `back_mailbox._bus`, and `router._bus` do not exist. Live assertion proves Concierge holds the per-session `BridgeAwareLocalBus`; two sessions have independent wrapper + inner bus instances. |
| M2-X2 | PORT-IDENTITY | `session.fabric is not svc._shared_fabric` AND registries identical | I2.X.2 | `[x]` | green (5/5 file) | `tests/integration/k1/live/m2/test_m2_x1_x5_port_identity.py` | Two sessions get distinct Fabric containers; both reuse `svc._shared_fabric.registry`. |
| M2-X3 | PORT-IDENTITY | `SessionRoutingStateReader` is the same object inside shared Fabric context builder, Orchestrator state port, Planner tool router, and `svc._session_routing_reader` | I2.X.3 | `[x]` | green (5/5 file) | `tests/integration/k1/live/m2/test_m2_x1_x5_port_identity.py` | Corrected attribute paths: shared Fabric path is `.facade._context_builder._state_reader`; Orchestrator path is `._state_port._reader`; Planner path is `._pipeline._sketch._tool_router._state_read._reader`. |
| M2-X4 | PORT-IDENTITY | `svc._model_hub` singleton reaches shared/session Fabric gateways, Concierge runtime, Planner LLM adapter, and MemoryWriter agent adapter | I2.X.4 | `[x]` | green (5/5 file) | `tests/integration/k1/live/m2/test_m2_x1_x5_port_identity.py` | Corrected attribute paths: Fabric gateway via provider factory port deps; Concierge uses `_model`; Planner uses `LLMGatewayAdapter._bus._hub`; MW uses `_pipeline._writer_agent._model_hub._hub`. |
| M2-X5 | PORT-IDENTITY | `svc._bridge.get_client()` singleton stable across sessions (extends M2-L10) | I2.X.5 | `[x]` | green (5/5 + 5/5) | `tests/integration/k1/live/m2/test_m2_l10_bridge_client_identity.py`; `tests/integration/k1/live/m2/test_m2_x1_x5_port_identity.py` | Covered by M2-L10 and rechecked in focused X-row file using SINK mode. |
| M2-X6 | LIFECYCLE | S4 before all P-phases; P1 first per-session; P6 last | I2.X.6 | `[x]` | green (2/3 file) | `tests/integration/k1/live/m2/test_m2_x6_x8_lifecycle_deadwire.py` | Added P1..P6 creation lifecycle events in `KernelService._create_session_tier2`; live Recipe A test proves S4/startup complete before P1 and exact P1→P6 creation order. |
| M2-X7 | LIFECYCLE | `destroy_session` runs P6→P1 in order; MW.stop completes before SSM.stop | I2.X.7 | `[x]` | green (2/3 file) | `tests/integration/k1/live/m2/test_m2_x6_x8_lifecycle_deadwire.py` | Live Recipe A test proves teardown events are exactly P6_teardown_start → P5/P4/P3/P2/P1 teardown_complete; MW P5 completion precedes SSM P2 completion. |
| M2-X8 | NEGATIVE | `AsyncSSMBridge` constructed at P2 is never injected (dead-wire lock-in) | I2.X.8 | `[x]` | xfail strict | `tests/integration/k1/live/m2/test_m2_x6_x8_lifecycle_deadwire.py` | Strict xfail static wiring probe asserts desired future load/injection of `async_ssm`; current source has one P2 construction binding and zero downstream loads. |

---

## M5 — Bus + SessionState + MemoryWriter

**Boot recipe:** A
**Issues covered:** 29 (10 L + 19 X) | **GAPs covered:** 7
**Production-grade stamp:** `[ ]`

| Step | Probe type | Target | Tracing refs | Status | Verdict | Test file | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M5-L1 | SUBSCRIPTION | **MW01 killer test** — Concierge publish topic == MW subscribe topic (topic typo `complete` vs `completed`) | ISSUE-MW01 | `[ ]` | | | |
| M5-L2 | MESSAGE-FLOW | TTL: publish with ttl=100ms, consume at t+200ms → must be dropped | ISSUE-B01 | `[ ]` | | | |
| M5-L3 | LIFECYCLE | MW.stop() completes **before** SSM.stop() begins | I-5.11.4 | `[ ]` | | | |
| M5-L4 | MESSAGE-FLOW | `PlaceResolver` resolves known place name to non-zero coords | ISSUE-MW04 | `[ ]` | | | |
| M5-L5 | PORT-IDENTITY | Per-session bus isolation: session A's subscribers don't see session B's envelopes | E5.x | `[ ]` | | | |
| M5-L6 | LIFECYCLE | SS write-flush on session destroy: every pending mutation lands in SQLite | E5.x | `[ ]` | | | |

### M5 — Cross-component integration probes

| Step | Probe type | Target | Tracing refs | Status | Verdict | Test file | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M5-X1 | SUBSCRIPTION | `session.bus.list_subscriptions()` after P1..P6 contains one subscriber per CONTRACT topic, no orphans | I-5.X.1 | `[ ]` | | | |
| M5-X2 | LIFECYCLE | After `destroy_session`, bus has zero subscriptions and no handler refs leak | I-5.X.2 | `[ ]` | | | |
| M5-X3 | NEGATIVE | `BridgeAwareLocalBus` raises `UnknownContractError` on bridge-reserved direct publish (extends M2-L8) | I-5.X.3 | `[x]` | green | `tests/integration/k1/live/m2/test_m2_l8_bridge_aware_bus_guard.py` | Covered by M2-L8. |
| M5-X4 | PORT-IDENTITY | Concierge `_state_port._manager` and `_state_writer._manager` are the session SSM | I-5.X.4 | `[ ]` | | | |
| M5-X5 | PORT-IDENTITY | MW `_session_read_port._manager` is the session SSM | I-5.X.5 | `[ ]` | | | |
| M5-X6 | NEGATIVE | MW has no write port (single-writer invariant; `ssm.mutate` spy must not see MW caller) | I-5.X.6 | `[ ]` | | | |
| M5-X7 | LIFECYCLE | Pre-start `DirectWriterAdapter.mutate()` raises `LifecycleError`; post-start accepts | I-5.X.7 | `[ ]` | | | |
| M5-X8 | NEGATIVE | SSM eviction publishes only on `LocalEventAdapter`, not on `session_bus` (diagram-vs-code lock-in) | I-5.X.8 | `[ ]` | | | |
| M5-X9 | PORT-IDENTITY | MW cold-archive view is `ssm.get_local_cold_archive()` identity | I-5.X.9 | `[ ]` | | | |
| M5-X10 | MESSAGE-FLOW | Live turn → `k1.session.turn.completed.v1` published with full payload by `ConciergeController._emit_turn_completed` | I-5.X.10 | `[ ]` | | | |
| M5-X11 | SUBSCRIPTION | After `mw.start()`, session bus subscriber list includes `TurnDispatcher._on_turn_complete` on `k1.session.turn.completed.v1` | I-5.X.11 | `[ ]` | | | |
| M5-X12 | NEGATIVE | **MW01-A**: `TurnDispatcher.TOPIC == TOPIC_TURN_COMPLETED` (`completed`) — today stale `complete`; xfail strict | I-5.X.12 / ISSUE-MW01 | `[ ]` | xfail | | |
| M5-X13 | MESSAGE-FLOW | Concierge→MW end-to-end: turn published → `MWSessionReader.snapshot()` reads it back | I-5.X.13 | `[ ]` | | | |
| M5-X14 | NEGATIVE | Same `turn_id` published twice → MW `_processed_ids` dedups → `pipeline.process()` called once | I-5.X.14 | `[ ]` | | | |
| M5-X15 | MESSAGE-FLOW | After complete turn → `IBridgeCommandPort.submit_batch()` called with `memory.delta` + non-empty `cognitive_trace_id` | I-5.X.15 | `[ ]` | | | |
| M5-X16 | NEGATIVE | 3 LLM failures → MW CB OPEN; 4th turn skips agent; `k1.mw.circuit.open.v1` fired | I-5.X.16 | `[ ]` | | | |
| M5-X17 | LIFECYCLE | `_emitted_turn_ids` on controller prevents double-publish on dispatch+complete race | I-5.X.17 | `[ ]` | | | |
| M5-X18 | NEGATIVE | `_ledger==None` degenerate `turn_id == "turn:{N}"` path rejected before publish | I-5.X.18 | `[ ]` | | | |
| M5-X19 | NEGATIVE | Duplicate `dag.completed` subscription fires controller handler exactly once per event | I-5.X.19 | `[ ]` | | | |

---

## M3 — Fabric + Model Hub

**Boot recipe:** A
**Issues covered:** 25 (16 L + 9 X) | **GAPs covered:** 6
**Production-grade stamp:** `[ ]`

| Step | Probe type | Target | Tracing refs | Status | Verdict | Test file | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M3-L1 | MESSAGE-FLOW | `execute()` STEP 1–9 emits `k1.capability.invoked.v1` and `k1.capability.completed.v1` with matching `cognitive_trace_id` | I3.1.1 | `[ ]` | | | |
| M3-L2 | NEGATIVE | `safety_band` missing on request → defaults to GREEN (silent escalation confirms GAP) | M3 cross-cutting | `[ ]` | xfail | | |
| M3-L3 | NEGATIVE | CB CLOSED→OPEN at threshold; OPEN→HALF_OPEN→CLOSED on probe | I3.2.6/.7 | `[ ]` | | | |
| M3-L4 | PORT-IDENTITY | Fabric never gets a write call on `state_reader` (read-only proxy wrap) | E3.6 | `[ ]` | | | |
| M3-L5 | MESSAGE-FLOW | ModelHub 9-step on CHAT request — all 10 bus topics fire | I3.7.1, ISSUE-M01 | `[ ]` | | | |
| M3-L6 | NEGATIVE | `from_config` injected ports stored but disconnected → 0 events on all 10 topics (confirms ISSUE-M01) | ISSUE-M01 | `[ ]` | xfail | | |
| M3-L7 | MESSAGE-FLOW | Cache hit on identical CHAT, miss on TOOL_CALL | I3.7.2/.3 | `[ ]` | | | |
| M3-L8 | NEGATIVE | All providers' CBs OPEN → `NoEligibleProviderError`, not silent fallback | I3.7.5 | `[ ]` | | | |

### M3 — Cross-component integration probes

| Step | Probe type | Target | Tracing refs | Status | Verdict | Test file | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M3-X1 | MESSAGE-FLOW | One LLM-backed `fabric.execute()` → both `k1.capability.completed.v1` (session bus) and `k1.model_hub.response.complete.v1` (shared bus) with matching `trace_id` | I3.X.1 | `[ ]` | | | |
| M3-X2 | SUBSCRIPTION | `k1.fabric.learning.signal.v1` emitted on session bus after every `execute()` (success and failure paths) | I3.X.2 | `[ ]` | | | |
| M3-X3 | SUBSCRIPTION | `k1.model_hub.circuit.state.v1` fires on shared bus per CB transition (CLOSED↔OPEN↔HALF_OPEN) | I3.X.3 | `[ ]` | | | |
| M3-X4 | MESSAGE-FLOW | Provider failure cascade: `provider.failure.v1` → `fallback.triggered.v1` → `response.complete.v1` in order | I3.X.4 | `[ ]` | | | |
| M3-X5 | NEGATIVE | Malformed capability output → `k1.fabric.output.validation.failed.v1` + `CapabilityResult.success=False` | I3.X.5 | `[ ]` | | | |
| M3-X6 | MESSAGE-FLOW | Planner LLM call → `k1.model_hub.request.received.v1` with `consumer_id="planner"`, no `k1.capability.*` topics | I3.X.6 | `[ ]` | | | |
| M3-X7 | MESSAGE-FLOW | MW LLM call → `k1.model_hub.request.received.v1` with `consumer_id="memory_writer"` | I3.X.7 | `[ ]` | | | |
| M3-X8 | NEGATIVE | Lock in undocumented topics: `k1.model_hub.request.completed.v1` and `k1.model_hub.request.failed.v1` ARE emitted (code-vs-events.py drift) | I3.X.8 | `[ ]` | | | |
| M3-X9 | NEGATIVE | `k1.model_hub.budget.alert.v1` is NEVER emitted (mmd-vs-code drift); xfail strict | I3.X.9 | `[ ]` | xfail | | |

---

## M1 — Concierge

**Boot recipe:** A (B for M1-L8)
**Issues covered:** 30 (18 L + 12 X) | **GAPs covered:** 6
**Production-grade stamp:** `[ ]`

| Step | Probe type | Target | Tracing refs | Status | Verdict | Test file | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M1-L1 | PORT-IDENTITY | `concierge._input_port`, `_output_port`, `_state_port`, `_llm_port`, `_dispatch_port` are non-None and wired to per-session bus | E1.10, M2 P1/P2 | `[ ]` | | | |
| M1-L2 | SUBSCRIPTION | FSM subscribes to exactly the topics in CONTRACT.md §4 | E1.3 | `[ ]` | | | |
| M1-L3 | MESSAGE-FLOW | **LOW-tier happy path** (F04+F08+F138+F142+F145–F147+F149/F152) | E1.1, E1.3, E1.6 | `[ ]` | | | |
| M1-L4 | MESSAGE-FLOW | **MED-tier dispatch flow** (F05+F33+F36–F38+F132–F133+F136–F137) | E1.4, E1.5 | `[ ]` | | | |
| M1-L5 | NEGATIVE | **HIGH-tier — orchestrator path NOT wired today** (xfail I1.5.1 Finding N6) | I1.5.1 (N6) | `[ ]` | xfail | | |
| M1-L6 | LIFECYCLE | `set_self_model()` after `start()` → guarded error, not data race | I1.10.2 | `[ ]` | xfail | | |
| M1-L7 | NEGATIVE | EpisodicCompressor unwired — 16-turn conversation, history grows unbounded (confirms ISSUE-C02) | I1.1.5 | `[ ]` | xfail | | |
| M1-L8 | MESSAGE-FLOW | HITL relay: pause → external resolve → `back_resume_handler` | E1.8 | `[ ]` | | | |
| M1-L9 | LIFECYCLE | Crash-recovery priority order | I1.10.4 | `[ ]` | | | |

### M1 — Cross-component integration probes

| Step | Probe type | Target | Tracing refs | Status | Verdict | Test file | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M1-X1 | PORT-IDENTITY | All 5 Concierge ports non-None and bound to session-local objects (bus, SSM) / shared ModelHub | I1.X.1 | `[ ]` | | | |
| M1-X2 | SUBSCRIPTION | FSM subscribes to exactly the CONTRACT §4 topic set — no extras, no missing | I1.X.2 | `[ ]` | | | |
| M1-X3 | MESSAGE-FLOW | LOW-tier short-circuit: `dispatch_direct` only, no `dispatch_envelope`, one `session_fabric.execute()` | I1.X.3 | `[ ]` | | | |
| M1-X4 | MESSAGE-FLOW | MED-tier: Front emits `task.dispatch.v1` → BackHandler ReAct → `task.complete.v1` → Front DELIVERING | I1.X.4 | `[ ]` | | | |
| M1-X5 | NEGATIVE | HIGH-tier full DAG path NOT wired end-to-end (Finding N6); xfail strict | I1.X.5 / I1.5.1 | `[ ]` | xfail | | |
| M1-X6 | MESSAGE-FLOW | `task.complete.v1` → FSM DELIVERING → `k1.response.final.v1` → FSM LISTENING | I1.X.6 | `[ ]` | | | |
| M1-X7 | MESSAGE-FLOW | `turn_end()` → `k1.session.turn.completed.v1`; `_emitted_turn_ids` blocks re-emit | I1.X.7 | `[ ]` | | | |
| M1-X8 | NEGATIVE | CRISIS safety_band turn → FSM stays LISTENING, hardcoded CRISIS_STATIC reply, zero Fabric/LLM calls | I1.X.8 | `[ ]` | | | |
| M1-X9 | NEGATIVE | `WriteElisionGate` on backchannel turn → only `control.safety_band` mutated; other 5 sections elided | I1.X.9 | `[ ]` | | | |
| M1-X10 | MESSAGE-FLOW | HITL suspend → `hil.response.v1` → `task.resume.v1` → Back resumes with remaining budget | I1.X.10 | `[ ]` | | | |
| M1-X11 | NEGATIVE | `set_self_model()` after `start()` raises guarded error; FSM unchanged | I1.X.11 / I1.10.2 | `[ ]` | xfail | | |
| M1-X12 | NEGATIVE | Duplicate `dag.completed` subscription fires handler once per event | I1.X.12 | `[ ]` | | | |

---

## M4 — Orchestrator + Planner

**Boot recipe:** A
**Issues covered:** 25 (12 L + 13 X) | **GAPs covered:** 7
**Production-grade stamp:** `[ ]`

| Step | Probe type | Target | Tracing refs | Status | Verdict | Test file | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M4-L1 | PORT-IDENTITY | `_state_adapter` is **NOT** `MockStateReadAdapter` | I6.11.H5 | `[ ]` | | | |
| M4-L2 | MESSAGE-FLOW | End-to-end T3 plan: `plan.submit.v1` → step events → `plan.complete.v1` (F45+F95+F96) | E4.x | `[ ]` | | | |
| M4-L3 | NEGATIVE | `ConcurrencyGuard` depth limit: enqueue N=1000 same plan; assert hard cap | GAP-O02 | `[ ]` | xfail | | |
| M4-L4 | NEGATIVE | `PlanStep.to_dict()` round-trip preserves `safety_band_min` | I6.11.C1 | `[ ]` | | | |
| M4-L5 | NEGATIVE | `IEmbeddingPort` unwired → `fabric_search` returns error, not silent empty | I6.11.C5 | `[ ]` | xfail | | |
| M4-L6 | PORT-IDENTITY | Planner's `IFabricRetrievalPort` is the shared fabric, not None | E4.x | `[ ]` | | | |

### M4 — Cross-component integration probes

| Step | Probe type | Target | Tracing refs | Status | Verdict | Test file | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M4-X1 | PORT-IDENTITY | `orch._planner_port` is real `PlannerAdapter` over live planner mailbox (extends M2-L2) | I4.X.1 | `[x]` | green | `tests/integration/k1/live/m2/test_m2_l2_planner_orchestrator_crosswire.py` | Covered by M2-L2. |
| M4-X2 | PORT-IDENTITY | `orch._state_adapter._reader` is `svc._session_routing_reader` (shared with Fabric + Planner) | I4.X.2 | `[ ]` | | | |
| M4-X3 | PORT-IDENTITY | `FabricDispatchAdapter._orchestrator is svc._orchestrator` per session | I4.X.3 | `[ ]` | | | |
| M4-X4 | MESSAGE-FLOW | HIGH envelope → planner mailbox depth>0 → Planner emits `k1.planner.plan.ready.v1` on **kernel bus** → Orchestrator receives `CommittedPlan` | I4.X.4 | `[ ]` | | | |
| M4-X5 | MESSAGE-FLOW | 2-wave `CommittedPlan` → `DAGEngine` calls `execute_batch()` twice → `AggregatedResult` returned to Back | I4.X.5 | `[ ]` | | | |
| M4-X6 | NEGATIVE | Planner `query_planning_context(sid1)` reads `sid1`'s SS, not `sid2`'s (sentinel `""` blast-radius) | I4.X.6 / I2.5.2 | `[ ]` | xfail | | |
| M4-X7 | NEGATIVE | CB_PLANNER OPEN → HIGH envelope degrades to MED (`PlannerAdapter.request_plan` called 0 times) | I4.X.7 | `[ ]` | | | |
| M4-X8 | NEGATIVE | `k1.planner.plan.failed.v1` → `dispatch_envelope()` returns within timeout (Back not hung) | I4.X.8 / I1.5.1 | `[ ]` | | | |
| M4-X9 | MESSAGE-FLOW | Planner Stage-1 SKETCH `discover_capabilities()` returns freshly-registered test capability | I4.X.9 | `[ ]` | | | |
| M4-X10 | MESSAGE-FLOW | MicroReplan: ORCH-13 → `PlannerAdapter.micro_replan()` → partial `CommittedPlan` (remaining steps only) | I4.X.10 | `[ ]` | | | |
| M4-X11 | LIFECYCLE | S6 → S6a → S6b ordering: Orch.start, Planner.start, then cross-wire verification | I4.X.11 | `[ ]` | | | |
| M4-X12 | NEGATIVE | Workflow-triggered (cron) plan has no Back handle → return-path gap; xfail strict | I4.X.12 | `[ ]` | xfail | | |
| M4-X13 | MESSAGE-FLOW | `k1.hil.progress.v1` emitted on kernel bus by `ExecutionMonitor` reaches Concierge PROGRESSING via session bus (cross-bus bridge) | I4.X.13 | `[ ]` | | | |

---

## M6 — Cross-cutting

**Boot recipe:** A (B for M6-L2)
**Issues covered:** 24 (9 L + 15 X) | **GAPs covered:** 6
**Production-grade stamp:** `[ ]`

| Step | Probe type | Target | Tracing refs | Status | Verdict | Test file | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M6-L1 | PORT-IDENTITY | All three SS readers (Orch/Planner/Fabric) point to real per-session SSM — NOT Null/Mock | I6.11.C6 | `[ ]` | | | |
| M6-L2 | MESSAGE-FLOW | HIL approval gate end-to-end | E1.8, M6 HIL | `[ ]` | | | |
| M6-L3 | PORT-IDENTITY | SelfModel handle installed as step-0 on both Front and Back dispatchers | selfmodel test I3 | `[ ]` | | | |
| M6-L4 | LIFECYCLE | SelfModel bundle `health()` returns `status=ok` on live kernel | selfmodel test I4 | `[ ]` | | | |
| M6-L5 | NEGATIVE | Cancel parent task → all child traces cancelled, no orphan envelopes | M6 supervision | `[ ]` | | | |

### M6 — Cross-component integration probes

| Step | Probe type | Target | Tracing refs | Status | Verdict | Test file | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M6-X1 | PORT-IDENTITY | Front + Back dispatchers' `_policy_gate is self_model_handle.gate.evaluate` after P3.5 | I6.X.1 | `[ ]` | | | |
| M6-X2 | LIFECYCLE | `install_into_session` idempotent; `uninstall_from_session` restores originals exactly | I6.X.2 | `[ ]` | | | |
| M6-X3 | MESSAGE-FLOW | Tool call REQUIRE_CONFIRMATION → policy gate blocks → `HIL.ask_approval()` → `hil.response.v1` → Back resumes | I6.X.3 | `[ ]` | | | |
| M6-X4 | LIFECYCLE | `SelfModelServiceBundle.shutdown()` closes owned SQLite; second call is idempotent | I6.X.4 | `[ ]` | | | |
| M6-X5 | NEGATIVE | `enable_self_model=False` → bundle None, P3.5 skipped, no SelfModel topics fire | I6.X.5 | `[ ]` | | | |
| M6-X6 | LIFECYCLE | `bundle.health()` returns `ok` / `degraded` / `safe_mode` per Constitution state | I6.X.6 | `[ ]` | | | |
| M6-X7 | SUBSCRIPTION | HIL subscribes to `k1.hil.response.v1` on session bus; `ask_approval()` publishes `k1.hil.request.v1` and resolves Future on response | I6.X.7 | `[ ]` | | | |
| M6-X8 | NEGATIVE | `SafetyBandPolicy` ALLOW early-exit: GREEN + no side-effects → zero `hil.request.v1` emissions | I6.X.8 | `[ ]` | | | |
| M6-X9 | LIFECYCLE | `SuspensionManager` limits: 3rd suspension same task raises; per-mode timeouts auto-cancel FSM | I6.X.9 | `[ ]` | | | |
| M6-X10 | MESSAGE-FLOW | `back_resume_handler` re-reads SS at resume time (fresh snapshot, not stale stored) | I6.X.10 | `[ ]` | | | |
| M6-X11 | NEGATIVE | `enable_hil_service=False` → `_hil_service is None`; `_NullHILAdapter` injected; no `k1.hil.*` topics fire | I6.X.11 | `[ ]` | | | |
| M6-X12 | NEGATIVE | `k1/supervision/__init__.py` empty; no supervision tree wired; xfail strict lock-in | I6.X.12 | `[ ]` | xfail | | |
| M6-X13 | MESSAGE-FLOW | `back_cancel_handler` → `CancellationToken.cancel()` → ReAct loop exits before `max_iterations` | I6.X.13 | `[ ]` | | | |
| M6-X14 | NEGATIVE | `k1/learning/`, `k1/retention/`, `k1/scheduler/`, `k1/tracing/` `__init__.py` empty; no session-bus subs; no SSM touches; xfail strict lock-in | I6.X.14 | `[ ]` | xfail | | |
| M6-X15 | NEGATIVE | Learning loop never writes SSM (LEARN-01 single-writer invariant; guard for when learning ships) | I6.X.15 | `[ ]` | | | |

---

## M7 — Pseudo-K0 / Recipe-C Integration

**Boot recipe:** C (pseudo-K0 must be running: `python -m scripts.pseudo_k0 --port 8090 --db :memory:`)
**Issues covered:** 28 | **GAPs covered:** 4
**Production-grade stamp:** `[ ]`

> **Note.** All Recipe-C tests that exercise K0 policy paths carry
> `pytest.mark.xfail_on_real_k0` — they pass on pseudo-K0 but will need
> additional policy/gate/idem work on real K0.

| Step | Probe type | Target | Flows | Status | Verdict | Test file | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M7-L1 | MESSAGE-FLOW | `memory.write.v1` round-trip: K1 → Bridge LIVE → pseudo-K0 WAL | F35, F79, F80 | `[ ]` | | | |
| M7-L2 | MESSAGE-FLOW | `recall.request.v1` → pseudo-K0 LIKE search → `recall.response.v1` | F39, F40 | `[ ]` | | | |
| M7-L3 | MESSAGE-FLOW | `tool_state.changed.v1` SSE wired end-to-end K0 → K1 EventBus | F82 | `[ ]` | | | |
| M7-L4 | MESSAGE-FLOW | `connector.execute.*` → Bridge LIVE → pseudo-K0 `ConnectorHost` | F102 | `[ ]` | | | |
| M7-L5 | NEGATIVE | Kill pseudo-K0 mid-flight → `LocalOutbox` queues; restart → `DrainWorker` drains; Prometheus counter increments | Bridge outbox | `[ ]` | | | |
| M7-L6 | PORT-IDENTITY | Bridge mode selection at S4: assert correct client class per config (`HttpBridgeClient` / `SinkBridgeClient` / null) | E2.10 | `[ ]` | | | |

---

## Cross-Cutting / Implicit Flows (No F-Number)

These are not in K1_FLOWS.md but are covered by the SOP and require live coverage.

| # | Description | SOP ref | Status | Notes |
| --- | --- | --- | --- | --- |
| X1 | Bridge envelope signing round-trip (HMAC + Ed25519, canonical JSON, idem-key excluded) | E2.7.9 → M7-L1 | `[ ]` | |
| X2 | LocalOutbox durability under 5xx | E2.7.4 + E7.2.4 → M7-L5 | `[ ]` | |
| X3 | Bridge mode selection at S4 | E2.10 → M7-L6 | `[ ]` | |
| X4 | MW pipeline → K0 outbox (SINK mode) | MW + outbox | `[ ]` | |
| X5 | Per-session bus isolation (E2.2 P1) | M5-L5 | `[ ]` | |
| X6 | S6b Mock→real planner swap | E2.3 → M2-L2 | `[x]` | Covered by `tests/integration/k1/live/m2/test_m2_l2_planner_orchestrator_crosswire.py`. |
| X7 | Lifecycle teardown order | E2.4.7, E5.11.4 → M2-L1, M5-L3 | `[ ]` | |
| X8 | `BridgeAwareLocalBus` bridge-reserved topic guard (R10) | E2.7.5 → M2-L8 | `[x]` | Covered by M2-L8; production fix applied (wrapped per-session bus at P1). |
| X9 | Pseudo-K0 gap matrix: flows that pass pseudo-K0 but need real K0 policy | E7.6 → M7 series | `[ ]` | |

---

## Known Blocked Flows (Do NOT Mark Live-Verified Until Blocker Cleared)

| Flow(s) | Blocker | Blocker owner | Cleared? |
| --- | --- | --- | --- |
| F60–F64, F68, F90, F94, F131, F140, F148, F153 | **I3.4.5** AgentProvider `mailbox=None` | AgentProvider | `[ ]` |
| F06, F09 (HIGH leg) | **I1.5.1** K1 Orchestrator not wired on HIGH path | Orchestrator | `[ ]` |
| F41 | **I6.11.C5** IEmbeddingPort not wired in shared Fabric | Fabric S4 | `[ ]` |
| F78 (default path) | **ISSUE-MW01** topic typo `complete` vs `completed` | MemoryWriter | `[ ]` |
| F108 + planner LLM path | **GAP-P02** `build_payload` private import | Planner | `[ ]` |
| F07 (safety, full) | **I6.11.H5** MockStateReadAdapter in prod | Orchestrator | `[ ]` |
| ~22 M6 stub flows | **M6 stub cluster** | M6 (future milestone) | `[ ]` |

---

## LLM-COVERED Flows (F11–F23) — Contract Test Checklist

These vision flows are NOT tested per-flow. One contract test per acking handler covers all 13.

| Contract test | Asserts | Status |
| --- | --- | --- |
| Phase-1 LLM call shape | (a) hits `ModelHubPOCBridge`; (b) respects `KernelConfig` budget/timeout; (c) falls through to `StubPhase1Pipeline` on timeout | `[ ]` |
| LLM output intent field | `intent` field present and non-empty | `[ ]` |
| LLM output safety_band field | `safety_band` is one of GREEN/AMBER/RED | `[ ]` |
| LLM output complexity field | `complexity` feeds `complexity_router` | `[ ]` |
| Hermetic stub fallback | `model_mode="test"` → `StubPhase1Pipeline` auto-registered, no LLM round-trip | `[ ]` |

---

## Acceptance Gates Checklist (Per Milestone)

To stamp a milestone **production-grade**, all five must be `[x]`:

| Gate | M1 | M2 | M3 | M4 | M5 | M6 | M7 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1. Every SOP §4 row has green test in `tests/integration/k1/live/<ms>/` | `[ ]` | `[ ]` | `[ ]` | `[ ]` | `[ ]` | `[ ]` | `[ ]` |
| 2. Every GAP has `xfail(strict=True)` or positive close | `[ ]` | `[ ]` | `[ ]` | `[ ]` | `[ ]` | `[ ]` | `[ ]` |
| 3. Zero asyncio task leaks + zero open SQLite handles | `[ ]` | `[ ]` | `[ ]` | `[ ]` | `[ ]` | `[ ]` | `[ ]` |
| 4. All captured envelopes round-trip serialization | `[ ]` | `[ ]` | `[ ]` | `[ ]` | `[ ]` | `[ ]` | `[ ]` |
| 5. No Mock in assertion subjects | `[ ]` | `[ ]` | `[ ]` | `[ ]` | `[ ]` | `[ ]` | `[ ]` |
| **PRODUCTION-GRADE STAMP** | `[ ]` | `[ ]` | `[ ]` | `[ ]` | `[ ]` | `[ ]` | `[ ]` |

---

## Progress Summary

| Milestone | Total steps | Completed | xfail confirmed | Blocked | % done |
| --- | --- | --- | --- | --- | --- |
| Prerequisites (hooks) | 6 | 6 | — | 0 | 100% |
| M2 Kernel + Bridge (L1–L10) | 10 | 10 | 2 | 0 | 100% |
| M2 Cross-component (X1–X8) | 8 | 8 | 1 | 0 | 100% |
| M5 Bus + SS + MW (L1–L6) | 6 | 0 | 0 | 0 | 0% |
| M5 Cross-component (X1–X19) | 19 | 1 | 0 | 0 | 5% |
| M3 Fabric + ModelHub (L1–L8) | 8 | 0 | 0 | 0 | 0% |
| M3 Cross-component (X1–X9) | 9 | 0 | 0 | 0 | 0% |
| M1 Concierge (L1–L9) | 9 | 0 | 0 | 0 | 0% |
| M1 Cross-component (X1–X12) | 12 | 0 | 0 | 0 | 0% |
| M4 Orch + Planner (L1–L6) | 6 | 0 | 0 | 0 | 0% |
| M4 Cross-component (X1–X13) | 13 | 1 | 0 | 0 | 8% |
| M6 Cross-cutting (L1–L5) | 5 | 0 | 0 | 0 | 0% |
| M6 Cross-component (X1–X15) | 15 | 0 | 0 | 0 | 0% |
| M7 Pseudo-K0 | 6 | 0 | 0 | 0 | 0% |
| Cross-cutting (X1–X9) | 9 | 2 | — | 0 | 22% |
| LLM-COVERED contracts | 5 | 0 | — | 0 | 0% |
| **TOTAL** | **146** | **28** | **3** | **0** | **19%** |

---

*Tracker initialized: 2026-05-13. Expanded with cross-component integration probe rows (76 new X-rows) sourced from k1 `.mmd` diagrams + `service.py` composition root.*
*Sources: `k1_flows_availability_matrix.md` (154 flows) · `kernel_tracing_plan.md` (379 issues + 76 cross-component, 53+ GAPs) · `live_kernel_wiring_test_procedure.md` (44 probe steps) · `K1_FLOWS.md` (vision) · `architecture_diagrams/k1/*.mmd`*
