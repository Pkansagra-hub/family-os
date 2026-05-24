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

## M0 -- Contract Freeze And Evidence Cleanup

M0 reconciles stale tracker claims before behavior work continues. It does not stamp a
runtime milestone; it records which alleged gaps are already implemented and which gaps
remain intentionally open for M1-M6.

| Item | Status | Evidence | Notes |
| --- | --- | --- | --- |
| M0-C03 | `[x]` | `tests/k1/concierge/react/test_loop_tool_timeout.py` | ReAct tool dispatch is already wrapped in `asyncio.wait_for(...)`; M0 added focused coverage for normal and HIL-aware timeouts. |
| M0-C04 | `[x]` | `tests/k1/concierge/test_m01_event_validator.py`; `tests/k1/concierge/fsm/test_response_delivered.py` | `ResponseDelivered` exists and is written before `_execute_response_final_decision(...)`. Treat it as delivery intent, not post-render confirmation. |
| M1-L7 | `[x]` | `tests/integration/k1/live/m1/test_m1_l6_l9_concierge_lifecycle.py` | Closed by M6.E1.I5: `EpisodicCompressor` wired into `ExperienceLayer` via `ConciergeFactory` step 9; `xfail` removed; live 16-turn test passes (ISSUE-C02 closed). |
| M1-X9 | `[x]` | `tests/integration/k1/live/m1/test_m1_x3_x12_concierge_cross_component.py`; `tests/k1/concierge/acking/test_write_elision_gate.py` | Closed by M5: production gate is `k1.concierge.acking.write_elision.WriteElisionGate`, wired on `ConciergeController._write_elision_gate`; strict xfail removed. |
| M1-X10 | `[x]` | `tests/integration/k1/live/m1/test_m1_x3_x12_concierge_cross_component.py` | Closed by M1: legacy HITL emits bridge-only `k1.hil.response.v1` before `task.resume.v1`; targeted test is green. |

### True Remaining Concierge Gap Register

| Gap | Owning milestone | Notes |
| --- | --- | --- |
| HIL protocol drift and structured Front resolution | M1 | Closed by M1: unified responses stay service-owned, legacy emits bridge-only protocol evidence before adapter resume, and Front parses typed resolution fields. |
| Typed Back/Front handoff frames | M2 | Closed by M2: Back emits typed result frames; Front PRESENT/WEAVE consume frame facts; HIL resume carries typed resolution frames; leak guards strip Back frame/tool/scratchpad artifacts. |
| ReAct checkpoint, control events, and tool execution records | M3 | Timeout exists; checkpoint/resume/idempotent tool records remain future work. |
| Weave side-effect split, queue coherence, and proactive fill | M4 | Preserve policy purity and delivery timing without interrupting HIL/crisis. |
| `WriteElisionGate` | M5 | Closed by M5: pure decision gate exists, controller wiring preserves temporal and crisis safety writes, and M1-X9 is no longer strict xfail. |
| Live `EpisodicCompressor` / OPP wiring | M6 | Compressor implementation exists; live factory/session/experience wiring remains open. |

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
| M5-L1 | SUBSCRIPTION | **MW01 killer test** — Concierge publish topic == MW subscribe topic (topic typo `complete` vs `completed`) | ISSUE-MW01 | `[x]` | green | `tests/integration/k1/live/m5/test_m5_l1_l6_bus_ss_mw.py` | Live Recipe A session proves `Concierge` builder topic, MW event constant, `TurnDispatcher.TOPIC`, default `SessionBatchDispatcher.TOPIC`, dispatcher subscription, and `session.bus.list_subscriptions()` all agree on `k1.session.turn.completed.v1`; stop unsubscribes it. |
| M5-L2 | MESSAGE-FLOW | TTL: publish with ttl=100ms, consume at t+200ms → must be dropped | ISSUE-B01 | `[x]` | green | `tests/integration/k1/live/m5/test_m5_l1_l6_bus_ss_mw.py` | Live per-session bus publish with `ttl_ms=100` and dispatch-time age of 200ms delivers zero handlers and increments `ttl_drops`. |
| M5-L3 | LIFECYCLE | MW.stop() completes **before** SSM.stop() begins | I-5.11.4 | `[x]` | green | `tests/integration/k1/live/m5/test_m5_l1_l6_bus_ss_mw.py` | `destroy_session()` spy captures strict order: `mw_stop_begin`, `mw_stop_end`, `ssm_stop_begin`, `ssm_stop_end`. |
| M5-L4 | MESSAGE-FLOW | `PlaceResolver` resolves known place name to non-zero geohash seed | ISSUE-MW04 | `[x]` | green | `tests/integration/k1/live/m5/test_m5_l1_l6_bus_ss_mw.py` | Live MW session reader now reads `beliefs_active` via zero-arg `get()` fallback; `mentioned_entities` reaches the pipeline, context `place_id=place_olive_garden`, and known seed geohash resolves to `c23nb6` instead of `000000`. |
| M5-L5 | PORT-IDENTITY | Per-session bus isolation: session A's subscribers don't see session B's envelopes | E5.x | `[x]` | green | `tests/integration/k1/live/m5/test_m5_l1_l6_bus_ss_mw.py` | Two live sessions subscribe to the same topic; session A publish reaches only session A handler. Bus wrapper and inner bus identities differ between sessions. |
| M5-L6 | LIFECYCLE | SS write-flush on session destroy: every pending mutation lands in SQLite | E5.x | `[x]` | green | `tests/integration/k1/live/m5/test_m5_l1_l6_bus_ss_mw.py` | Direct writer mutation leaves pending writes; `destroy_session()` checkpoints to SQLite `st_session_checkpoints`, and decoded `beliefs_active` contains the pending fact. |

### M5 — Cross-component integration probes

| Step | Probe type | Target | Tracing refs | Status | Verdict | Test file | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M5-X1 | SUBSCRIPTION | `session.bus.list_subscriptions()` after P1..P6 contains one subscriber per CONTRACT topic, no orphans | I-5.X.1 | `[x]` | green | `tests/integration/k1/live/m5/test_m5_x1_x5_subscription_identity.py` | Live Recipe A P1..P6 topology has 28 owned subscriptions; `k1.session.user.input.v1` has two intentional owners (FSM + `BusInputAdapter`), MW owns one `k1.session.turn.completed.v1`, Fabric gap detector owns four Fabric/MCP topics, and raw bus subscription IDs equal component-owned handles. |
| M5-X2 | LIFECYCLE | After `destroy_session`, bus has zero subscriptions and no handler refs leak | I-5.X.2 | `[x]` | green | `tests/integration/k1/live/m5/test_m5_x1_x5_subscription_identity.py` | Production cleanup added: `ConciergeRuntime.stop()` now closes `BusInputAdapter` and front subscriptions; `Fabric.shutdown()` stops owned `ProactiveGapDetector` subscriptions. Live destroy leaves `bus.list_subscriptions()==[]`, `subscription_count==0`, and no retained `_sub_patterns`. |
| M5-X3 | NEGATIVE | `BridgeAwareLocalBus` raises `UnknownContractError` on bridge-reserved direct publish (extends M2-L8) | I-5.X.3 | `[x]` | green | `tests/integration/k1/live/m2/test_m2_l8_bridge_aware_bus_guard.py` | Covered by M2-L8. |
| M5-X4 | PORT-IDENTITY | Concierge `_state_port._manager` and `_state_writer._manager` are the session SSM | I-5.X.4 | `[x]` | green | `tests/integration/k1/live/m5/test_m5_x1_x5_subscription_identity.py` | Corrected live paths: Concierge read adapter is `SSMStateAdapter._ss is session.session_state`, FSM and tool contexts share that state port, and `DirectWriterAdapter._manager is session.session_state`. |
| M5-X5 | PORT-IDENTITY | MW `_session_read_port._manager` is the session SSM | I-5.X.5 | `[x]` | green | `tests/integration/k1/live/m5/test_m5_x1_x5_subscription_identity.py` | `MemoryWriterService._pipeline._session_reader` is `MWSessionReader`; its `SessionReadAdapter._manager is session.session_state` and `_cold_archive is session.session_state.get_local_cold_archive()`. |
| M5-X6 | NEGATIVE | MW has no write port (single-writer invariant; `ssm.mutate` spy must not see MW caller) | I-5.X.6 | `[x]` | green | `tests/integration/k1/live/m5/test_m5_x6_x10_ss_mw_turn_flow.py` | Live MW uses `SessionReadAdapter` only; adapter exposes no mutation APIs, and a class-level `SessionStateManager.mutate` spy sees zero calls while MW consumes and flushes a `turn.completed` event. |
| M5-X7 | LIFECYCLE | Pre-start `DirectWriterAdapter.request_mutation()` raises `LifecycleError`; post-start accepts | I-5.X.7 | `[x]` | green | `tests/integration/k1/live/m5/test_m5_x6_x10_ss_mw_turn_flow.py` | Production guard added in `DirectWriterAdapter.request_mutation()` for unbound/not-running managers. Test proves pre-start raises `LifecycleError`, then a live Recipe A session writer applies a telemetry mutation after `ssm.start()`. |
| M5-X8 | NEGATIVE | SSM eviction publishes only on `LocalEventAdapter`, not on `session_bus` (diagram-vs-code lock-in) | I-5.X.8 | `[x]` | green | `tests/integration/k1/live/m5/test_m5_x6_x10_ss_mw_turn_flow.py` | Live SSM event port is `LocalEventAdapter(capture_mode=False)` and not the session bus; eviction emits `sessionstate.eviction.triggered/completed` through that event port while the session-bus publish spy sees no `sessionstate.eviction.*` topic. |
| M5-X9 | PORT-IDENTITY | MW cold-archive view is `ssm.get_local_cold_archive()` identity | I-5.X.9 | `[x]` | green | `tests/integration/k1/live/m5/test_m5_x6_x10_ss_mw_turn_flow.py` | `SessionReadAdapter._cold_archive is session.session_state.get_local_cold_archive()` and the same object as `session.session_state._local_cold_archive`. |
| M5-X10 | MESSAGE-FLOW | Live turn -> `k1.session.turn.completed.v1` published with full payload by `ConciergeController._emit_turn_completed` | I-5.X.10 | `[x]` | green | `tests/integration/k1/live/m5/test_m5_x6_x10_ss_mw_turn_flow.py` | Live user input drives FSM to DISPATCHING, controlled final response returns to LISTENING, and captured `turn.completed` payload contains `turn_id`, ledger `session_id`, `cognitive_trace_id`, `user_message`, `assistant_response`, positive `timestamp_ms`, and `turn_number`. |
| M5-X11 | SUBSCRIPTION | After `mw.start()`, session bus subscriber list includes the default `SessionBatchDispatcher` subscription on `k1.session.turn.completed.v1` | I-5.X.11 | `[x]` | green | `tests/integration/k1/live/m5/test_m5_l1_l6_bus_ss_mw.py` | Covered by M5-L1; live subscriber list contains exactly one `k1.session.turn.completed.v1` entry after MW start and zero after MW stop. |
| M5-X12 | NEGATIVE | **MW01-A closed:** `TurnDispatcher.TOPIC == TOPIC_TURN_COMPLETED` (`completed`) | I-5.X.12 / ISSUE-MW01 | `[x]` | green | `tests/integration/k1/live/m5/test_m5_l1_l6_bus_ss_mw.py` | Covered by M5-L1; legacy per-turn and default session-batch dispatcher constants both use `k1.session.turn.completed.v1`. |
| M5-X13 | MESSAGE-FLOW | Concierge→MW end-to-end: turn published → `MWSessionReader.snapshot()` reads it back | I-5.X.13 | `[x]` | green | `tests/integration/k1/live/m5/test_m5_x13_x15_concierge_mw_e2e.py` | Live Recipe A turn writes `history_active` before publish; MW session-batch flush calls the real `MWSessionReader.read_snapshot_enriched()` and the captured snapshot contains the just-published user/assistant turn. |
| M5-X14 | NEGATIVE | Same `turn_id` published twice → MW `_processed_ids` dedups → `pipeline.process()` called once | I-5.X.14 | `[x]` | green | `tests/integration/k1/live/m5/test_m5_x13_x15_concierge_mw_e2e.py` | Two duplicate `k1.session.turn.completed.v1` envelopes on the live session bus leave one `_processed_ids` entry, one buffered turn, and one `process_session()` call on stop. |
| M5-X15 | MESSAGE-FLOW | After complete turn → `IBridgeCommandPort.submit_batch()` called with `memory.delta` + non-empty `cognitive_trace_id` | I-5.X.15 | `[x]` | green | `tests/integration/k1/live/m5/test_m5_x13_x15_concierge_mw_e2e.py` | Live Concierge turn drives the real MW session-batch pipeline; model/bridge are controlled external edges, and `submit_batch()` receives `memory.delta` envelopes whose `trace_id`, headers, and body carry the non-empty cognitive trace id. |
| M5-X16 | NEGATIVE | 3 LLM failures → MW CB OPEN; 4th turn skips agent; `k1.mw.circuit.open.v1` fired | I-5.X.16 | `[x]` | green | `tests/integration/k1/live/m5/test_m5_x16_x19_mw_cb_concierge_guards.py` | Production fix surfaces model-edge failures from `MemoryWriterAgent` to `MemoryWriterPipeline` while preserving the agent's `[]` return contract; live Recipe A test forces three external LLM failures, observes CB OPEN, then proves the fourth turn publishes `k1.mw.circuit.open.v1` without a fourth model call. |
| M5-X17 | LIFECYCLE | `_emitted_turn_ids` on controller prevents double-publish on dispatch+complete race | I-5.X.17 | `[x]` | green | `tests/integration/k1/live/m5/test_m5_x16_x19_mw_cb_concierge_guards.py` | Live Concierge turn publishes one ledger-scoped `turn.completed`; a second same-turn `_emit_turn_completed()` call with the same final envelope is skipped because the `turn_id` is already in `_emitted_turn_ids`. |
| M5-X18 | NEGATIVE | `_ledger==None` degenerate `turn_id == "turn:{N}"` path rejected before publish | I-5.X.18 | `[x]` | green | `tests/integration/k1/live/m5/test_m5_x16_x19_mw_cb_concierge_guards.py` | Production fix requires a session-scoped id from ledger or envelope before publish; live Recipe A with `enable_ledger=False` and an unscoped final response emits no `turn.completed` and never records `turn:1`. |
| M5-X19 | NEGATIVE | Duplicate `dag.completed` subscription fires controller handler exactly once per event | I-5.X.19 | `[x]` | green | `tests/integration/k1/live/m5/test_m5_x16_x19_mw_cb_concierge_guards.py` | Live session bus has exactly one `TOPIC_DAG_COMPLETED` subscription and zero bare `k1.orchestration.dag.completed` subscriptions; one `dag.completed.v1` envelope produces exactly one normalized `task.complete.v1`. |

---

## M3 — Fabric + Model Hub

**Boot recipe:** A
**Issues covered:** 25 (16 L + 9 X) | **GAPs covered:** 6
**Production-grade stamp:** `[ ]`

| Step | Probe type | Target | Tracing refs | Status | Verdict | Test file | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M3-L1 | MESSAGE-FLOW | `execute()` STEP 1–9 emits `k1.capability.invoked.v1` and `k1.capability.completed.v1` with matching `cognitive_trace_id` | I3.1.1 | `[x]` | green | `tests/integration/k1/live/m3/test_m3_l1_l4_fabric_modelhub.py` | Live Recipe A per-session Fabric executes a deterministic `LOCAL_STUB` contract through registry, resolver, policy, context build, provider factory, CB path, validation, and event emission; captured session-bus envelopes and payloads both carry the request `cognitive_trace_id`. |
| M3-L2 | NEGATIVE | `safety_band` missing on request → defaults to GREEN (silent escalation confirms GAP) | M3 cross-cutting | `[x]` | xfail | `tests/integration/k1/live/m3/test_m3_l1_l4_fabric_modelhub.py` | Strict-xfail GAP probe uses `CapabilityRequest.from_dict()` with no `safety_band`, confirms the API object defaults to `GREEN`, then expects the future desired rejection; current live Fabric executes instead. |
| M3-L3 | NEGATIVE | CB CLOSED→OPEN at threshold; OPEN→HALF_OPEN→CLOSED on probe | I3.2.6/.7 | `[x]` | green | `tests/integration/k1/live/m3/test_m3_l1_l4_fabric_modelhub.py` | Live per-session Fabric installs a real `CircuitBreaker` for a test provider; two controlled provider failures open it, OPEN blocks without provider call, `allow_probe()` moves HALF_OPEN, and a successful probe closes and clears failure count. |
| M3-L4 | PORT-IDENTITY | Fabric never gets a write call on `state_reader` (read-only proxy wrap) | E3.6 | `[x]` | green | `tests/integration/k1/live/m3/test_m3_l1_l4_fabric_modelhub.py` | Live per-session Fabric state-reader holders are wrapped with a read-only proxy; execution reads expected SS sections through `read_section` and records no write-method lookup (`write_section`/`request_mutation` absent). |
| M3-L5 | MESSAGE-FLOW | ModelHub CHAT request → `k1.model_hub.request.completed.v1` fires on bus with matching `trace_id` | I3.7.1 | `[x]` | green | `tests/integration/k1/live/m3/test_m3_l5_l8_modelhub.py` | Live Recipe A boots with StubProviderPlugin; subscribes to `k1.model_hub.request.completed.v1` on raw `svc._bus`; CHAT execute → event captured synchronously via MHEventBusAdapter; payload carries expected `trace_id`, `request_id`, and `capability` fields. Note: RequestRouter publishes 2 topics (completed + failed), not 10; events.py constants are forward-declarations. |
| M3-L6 | NEGATIVE | `create_standalone()` leaves `event_port=None` in RequestRouter → all bus-topic publications silently suppressed (confirms ISSUE-M01) | ISSUE-M01 | `[x]` | xfail | `tests/integration/k1/live/m3/test_m3_l5_l8_modelhub.py` | Strict-xfail GAP probe calls `ModelHubFactory.create_standalone()`; asserts `hub._router._event_port is not None`; assertion FAILS confirming `event_port` is never wired; live kernel uses `create_with_ports(mh_ports)` with `MHEventBusAdapter` at service.py:1324. Fix: `create_standalone()` should accept optional `event_port` param. |
| M3-L7 | MESSAGE-FLOW | Cache hit on identical CHAT (`r1 is r2`), miss on TOOL_CALL (`tc1 is not tc2`) | I3.7.2/.3 | `[x]` | green | `tests/integration/k1/live/m3/test_m3_l5_l8_modelhub.py` | Live Recipe A; same `HubRequest` object executed twice for CHAT → second returns identical Python object (LRU hit); same TOOL_CALL payload executed twice → distinct objects; confirms `_SKIP_CAPABILITIES = frozenset({TOOL_CALL, BATCH, MODERATE})` in ResponseCache. |
| M3-L8 | NEGATIVE | All providers' CBs OPEN → `NoEligibleProviderError`, not silent fallback | I3.7.5 | `[x]` | green | `tests/integration/k1/live/m3/test_m3_l5_l8_modelhub.py` | Live Recipe A; reach into `svc._model_hub._router._dispatcher._circuit_mgr`; register stub provider with `failure_threshold=3`; record 3 failures → CB OPEN; CHAT request → `CapabilityRouter` Step 3 filters OPEN providers → 0 eligible → `NoEligibleProviderError` raised (not silent). |

### M3 — Cross-component integration probes

| Step | Probe type | Target | Tracing refs | Status | Verdict | Test file | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M3-X1 | MESSAGE-FLOW | One LLM-backed `fabric.execute()` → both `k1.capability.completed.v1` (session bus) and `k1.model_hub.response.complete.v1` (shared bus) with matching `trace_id` | I3.X.1 | `[x]` | green | `tests/integration/k1/live/m3/test_m3_x1_x9_cross_component.py` | Live Recipe A AGENT contract drives Fabric `AgentProvider` → `ModelGatewayBridgeAdapter` → ModelHub; completed and response.complete payloads carry the same trace. |
| M3-X2 | SUBSCRIPTION | `k1.fabric.learning.signal.v1` emitted on session bus after every `execute()` (success and failure paths) | I3.X.2 | `[x]` | green | `tests/integration/k1/live/m3/test_m3_x1_x9_cross_component.py` | Live per-session Fabric emits learning signals for deterministic LOCAL_STUB success and controlled provider failure; payloads preserve trace and success/error_code. |
| M3-X3 | SUBSCRIPTION | `k1.model_hub.circuit.state.v1` fires on shared bus per CB transition (CLOSED↔OPEN↔HALF_OPEN) | I3.X.3 | `[x]` | green | `tests/integration/k1/live/m3/test_m3_x1_x9_cross_component.py` | `CircuitBreakerManager(event_port=MHEventBusAdapter)` publishes CLOSED→OPEN, OPEN→HALF_OPEN, HALF_OPEN→CLOSED for the live stub provider. |
| M3-X4 | MESSAGE-FLOW | Provider failure cascade: `provider.failure.v1` → `fallback.triggered.v1` → `response.complete.v1` in order | I3.X.4 | `[x]` | green | `tests/integration/k1/live/m3/test_m3_x1_x9_cross_component.py` | Live ModelHub registers controlled failing and fallback plugins; dispatcher emits provider.failure and fallback.triggered before router emits response.complete. |
| M3-X5 | NEGATIVE | Malformed capability output → `k1.fabric.output.validation.failed.v1` + `CapabilityResult.success=False` | I3.X.5 | `[x]` | green | `tests/integration/k1/live/m3/test_m3_x1_x9_cross_component.py` | Controlled LOCAL_STUB output violates strict JSON schema; Fabric returns `output_validation_failed` and emits output.validation.failed with trace/provider/capability evidence. |
| M3-X6 | MESSAGE-FLOW | Planner LLM call → `k1.model_hub.request.received.v1` with `consumer_id="planner"`, no `k1.capability.*` topics | I3.X.6 | `[x]` | green | `tests/integration/k1/live/m3/test_m3_x1_x9_cross_component.py` | Live Planner `LLMGatewayAdapter` sends HubRequest with `consumer_id="planner"`; ModelHub emits request.received and no Fabric capability topics fire. |
| M3-X7 | MESSAGE-FLOW | MW LLM call → `k1.model_hub.request.received.v1` with `consumer_id="memory_writer"` | I3.X.7 | `[x]` | green | `tests/integration/k1/live/m3/test_m3_x1_x9_cross_component.py` | Live MemoryWriter agent uses its ModelHub adapter; request.received carries `consumer_id="memory_writer"` and CHAT capability. |
| M3-X8 | NEGATIVE | Lock in undocumented topics: `k1.model_hub.request.completed.v1` and `k1.model_hub.request.failed.v1` ARE emitted (code-vs-events.py drift) | I3.X.8 | `[x]` | green | `tests/integration/k1/live/m3/test_m3_x1_x9_cross_component.py` | Live ModelHub success emits request.completed; forced no-eligible-provider path emits request.failed. These legacy topics remain emitted even though they are absent from `events.py`. |
| M3-X9 | NEGATIVE | `k1.model_hub.budget.alert.v1` is NEVER emitted (mmd-vs-code drift); xfail strict | I3.X.9 | `[x]` | xfail | `tests/integration/k1/live/m3/test_m3_x1_x9_cross_component.py` | Strict xfail confirms `cost_limit=0.0` is accepted but not enforced; no budget enforcer or `budget.alert.v1` constant exists (MH-04 gap). |

---

## M1 — Concierge

**Boot recipe:** A (B for M1-L8)
**Issues covered:** 30 (18 L + 12 X) | **GAPs covered:** 8
**Production-grade stamp:** `[ ]`

| Step | Probe type | Target | Tracing refs | Status | Verdict | Test file | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M1-L1 | PORT-IDENTITY | `concierge._input_port`, `_output_port`, `_state_port`, `_llm_port`, `_dispatch_port` are non-None and wired to per-session bus | E1.10, M2 P1/P2 | `[x]` | green | `tests/integration/k1/live/m1/test_m1_l1_l2_concierge_wiring.py` | Live Recipe A with two sessions; production fix preserves required `PortBundle.output` and dispatch/state/LLM aliases on `ConciergeRuntime`; asserts per-session bus/SSM/Fabric isolation, shared ModelHub, `BusInputAdapter`/`BusOutputAdapter`, and `FabricDispatchAdapter` identity. |
| M1-L2 | SUBSCRIPTION | FSM subscribes to exactly the topics in CONTRACT.md §4 | E1.3 | `[x]` | green | `tests/integration/k1/live/m1/test_m1_l1_l2_concierge_wiring.py` | Live Recipe A asserts the 19 controller-owned `ConciergeController._subscription_handles` topics exactly match the contract set; front actor subscriptions are only `FRONT_SUBSCRIPTIONS`; `k1.session.user.input.v1` has the expected FSM + input-port subscribers. |
| M1-L3 | MESSAGE-FLOW | **LOW-tier happy path** (F04+F08+F138+F142+F145–F147+F149/F152) | E1.1, E1.3, E1.6 | `[x]` | green | `tests/integration/k1/live/m1/test_m1_l3_low_tier_message_flow.py` | Live Recipe A with `ScriptedProviderPlugin`; drives real `k1.session.user.input.v1` through FSM/Front to stream, final, and `turn.completed`; asserts ordering, no task dispatch/dead-letter, LISTENING final state, and trace/session continuity. Production fix: Front now copies source envelope correlation headers onto emitted stream/final/dispatch envelopes. |
| M1-L4 | MESSAGE-FLOW | **MED-tier dispatch flow** (F05+F33+F36–F38+F132–F133+F136–F137) | E1.4, E1.5 | `[x]` | green | `tests/integration/k1/live/m1/test_m1_l3_low_tier_message_flow.py` | Live Recipe A dispatches `plan=True` to registered MED capability `tool.read.find_prompts`; Front emits correlated `task.dispatch`, FSM routes `TaskEnvelope` through `IDispatchPort.dispatch_envelope`, Orchestrator resolves/executes via shared Fabric with controlled MCP edge, and session bus receives correlated `task.complete` with no task.failed/dead-letter. Production fixes: Front/FSM/Back/orchestrator preserve trace/session headers; MED/HIGH routing copies `TaskIntent.params` into `TaskEnvelope.context["params"]`; same-turn task completion preserves ack text in `turn.completed`; teardown cancels deferred proactive timer. |
| M1-L5 | MESSAGE-FLOW | **HIGH-tier planner/orchestrator/Fabric flow** (F06+F09 HIGH) | I1.5.1 (N6) | `[x]` | green | `tests/integration/k1/live/m1/test_m1_l3_low_tier_message_flow.py` | Live Recipe A dispatches `plan=True` / `complexity=HIGH` to registered capability `tool.read.find_prompts`; Front emits correlated `task.dispatch`, FSM routes `TaskEnvelope` through `IDispatchPort.dispatch_envelope`, Orchestrator requests Planner SKETCH/EXPAND/VALIDATE, executes the committed DAG through shared Fabric with controlled MCP edge, and session bus receives correlated `task.complete`. Production fix: `LLMGatewayAdapter` now backfills planner `result["content"]` from plain ModelHub CHAT string results. |
| M1-L6 | LIFECYCLE | `set_self_model()` after `start()` → guarded error, not data race | I1.10.2 | `[x]` | green | `tests/integration/k1/live/m1/test_m1_l6_l9_concierge_lifecycle.py` | Production guard added in `ConciergeRuntime.set_self_model()`; post-start calls raise `RuntimeError`, preserve the existing handle, and leave FSM state unchanged. |
| M1-L7 | POSITIVE | EpisodicCompressor wired — 16-turn conversation triggers compression (M6.E1.I5 closes ISSUE-C02) | I1.1.5 | `[x]` | passing | `tests/integration/k1/live/m1/test_m1_l6_l9_concierge_lifecycle.py` | `ConciergeFactory` step 9 instantiates one `EpisodicCompressor` per session and shares it with `ExperienceLayer`; `tick()` calls `compress_all(...)` once history reaches `min_turns_to_compress`; `compression_count` increments at turn 15+. |
| M1-L8 | MESSAGE-FLOW | HITL relay: pause → external resolve → `back_resume_handler` | E1.8 | `[x]` | green | `tests/integration/k1/live/m1/test_m1_l6_l9_concierge_lifecycle.py` | Recipe B live path: Back `submit_result(needs_human)` emits `task.suspended`; FSM stays in `CLARIFYING_WORKER`; user answer runs Front `HITL_RESOLVE`, emits correlated `task.resume`, and Back resume invokes Fabric then emits correlated `task.complete`. Production fixes normalize live `TaskStateEntry`/dict shapes and keep HITL relay state open. |
| M1-L9 | LIFECYCLE | Crash-recovery priority order | I1.10.4 | `[x]` | green | `tests/integration/k1/live/m1/test_m1_l6_l9_concierge_lifecycle.py` | Direct priority probe validates `SUSPENDED -> CLARIFYING_WORKER`, pending results -> `WEAVING`, active tasks -> `COMPANIONING`, unresponded user input -> `DISPATCHING`, delivered response -> `LISTENING`. |

### M1 — Cross-component integration probes

| Step | Probe type | Target | Tracing refs | Status | Verdict | Test file | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M1-X1 | PORT-IDENTITY | All 5 Concierge ports non-None and bound to session-local objects (bus, SSM) / shared ModelHub | I1.X.1 | `[x]` | green | `tests/integration/k1/live/m1/test_m1_l1_l2_concierge_wiring.py` | Covered with M1-L1; verifies runtime port aliases plus front/back dispatcher contexts point at the same live `FabricDispatchAdapter`. |
| M1-X2 | SUBSCRIPTION | FSM subscribes to exactly the CONTRACT §4 topic set — no extras, no missing | I1.X.2 | `[x]` | green | `tests/integration/k1/live/m1/test_m1_l1_l2_concierge_wiring.py` | Covered with M1-L2; exact FSM handle set is 19 topics and is disjoint from `FRONT_SUBSCRIPTIONS`. |
| M1-X3 | MESSAGE-FLOW | LOW-tier short-circuit: `dispatch_direct` only, no `dispatch_envelope`, one `session_fabric.execute()` | I1.X.3 | `[x]` | green | `tests/integration/k1/live/m1/test_m1_x3_x12_concierge_cross_component.py` | Recipe A live path: Front dispatches LOW task, FSM routes canonical `task.dispatch.v1` to Back, Back ReAct invokes one capability through the per-session Fabric, and a monkeypatched `dispatch_envelope()` spy stays unused. Production fix: Back tool context now binds envelope `cognitive_trace_id`, `session_id`, and task id before direct Fabric calls. |
| M1-X4 | MESSAGE-FLOW | MED-tier: Front emits `task.dispatch.v1` → Orchestrator/Fabric → `task.complete.v1` → turn completion | I1.X.4 | `[x]` | green | `tests/integration/k1/live/m1/test_m1_l3_low_tier_message_flow.py` | Covered by M1-L4; row wording corrected from BackHandler to Orchestrator path. Live MED flow emits correlated `task.dispatch`, routes through `dispatch_envelope`, executes shared Fabric, emits correlated orchestrator `task.complete`, and closes the same turn without task.failed/dead-letter. |
| M1-X5 | MESSAGE-FLOW | HIGH-tier full DAG path: `dispatch_envelope` → Planner → Orchestrator DAG → shared Fabric → `task.complete.v1` | I1.X.5 / I1.5.1 | `[x]` | green | `tests/integration/k1/live/m1/test_m1_l3_low_tier_message_flow.py` | Covered by M1-L5; strict-xfail expectation retired because the live path now reaches Planner SKETCH/EXPAND/VALIDATE, executes the Fabric capability, and bridges the correlated orchestrator result back to the session bus. |
| M1-X6 | MESSAGE-FLOW | same-turn `task.complete.v1` closes from LISTENING; older/asynchronous completions use DELIVERING | I1.X.6 | `[x]` | green | `tests/integration/k1/live/m1/test_m1_l3_low_tier_message_flow.py`; `k1/concierge/WIRING.md` | Live M1-L4 records FSM state when `task.complete.v1` is observed: current MED same-turn branch stores a deferred proactive result and returns to `LISTENING` before `turn.completed`; docs updated to distinguish this from the older DELIVERING branch. |
| M1-X7 | MESSAGE-FLOW | `turn_end()` → `k1.session.turn.completed.v1`; `_emitted_turn_ids` blocks re-emit | I1.X.7 | `[x]` | green | `tests/integration/k1/live/m1/test_m1_l3_low_tier_message_flow.py` | Live M1-L4 publishes one ledger-scoped `turn.completed`; a second `_emit_turn_completed()` call with the same final envelope is skipped by `_emitted_turn_ids`. |
| M1-X8 | NEGATIVE | CRISIS safety_band turn → FSM stays LISTENING, hardcoded CRISIS_STATIC reply, zero Fabric/LLM calls | I1.X.8 | `[x]` | green | `tests/integration/k1/live/m1/test_m1_x3_x12_concierge_cross_component.py` | Recipe A crisis turn short-circuits before arbiter/Front LLM/Fabric, emits static `crisis_protocol` final with `988`, transitions back to LISTENING, and escalates control safety to RED. Production fix: crisis final response now copies source trace/session headers. |
| M1-X9 | NEGATIVE | `WriteElisionGate` on backchannel turn → temporal/safety writes preserved while optional low-signal sections are elided | I1.X.9 | `[x]` | green | `tests/integration/k1/live/m1/test_m1_x3_x12_concierge_cross_component.py`; `tests/k1/concierge/acking/test_write_elision_gate.py` | M5 added `k1.concierge.acking.write_elision.WriteElisionGate` and wires it as `ConciergeController._write_elision_gate`; the live probe now asserts the production module/controller attribute instead of strict-xfail design absence. |
| M1-X10 | MESSAGE-FLOW | HITL suspend → `hil.response.v1` → `task.resume.v1` → Back resumes with remaining budget | I1.X.10 | `[x]` | green | `tests/integration/k1/live/m1/test_m1_x3_x12_concierge_cross_component.py`; `tests/integration/k1/live/m1/test_m1_l6_l9_concierge_lifecycle.py` | Legacy HITL now persists a bridge-only HIL envelope, Front emits `k1.hil.response.v1` before correlated `task.resume.v1`, and Back resumes with retained HILSubTask history. The former strict xfail marker was removed. |
| M1-X11 | NEGATIVE | `set_self_model()` after `start()` raises guarded error; FSM unchanged | I1.X.11 / I1.10.2 | `[x]` | green | `tests/integration/k1/live/m1/test_m1_l6_l9_concierge_lifecycle.py` | Covered by M1-L6; stale xfail expectation retired because the runtime now has an explicit post-start guard. |
| M1-X12 | NEGATIVE | Duplicate `dag.completed` subscription fires handler once per event | I1.X.12 | `[x]` | green | `tests/integration/k1/live/m5/test_m5_x16_x19_mw_cb_concierge_guards.py` | Covered by M5-X19; live session bus has exactly one `TOPIC_DAG_COMPLETED` subscription and zero bare `k1.orchestration.dag.completed` subscriptions; one event produces one normalized `task.complete.v1`. |

---

## M4 — Orchestrator + Planner

**Boot recipe:** A
**Issues covered:** 25 (12 L + 13 X) | **GAPs covered:** 7
**Production-grade stamp:** `[ ]`

| Step | Probe type | Target | Tracing refs | Status | Verdict | Test file | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M4-L1 | PORT-IDENTITY | `_state_port` is real `StateReadAdapter`, **NOT** `MockStateReadAdapter` | I6.11.H5 | `[x]` | green | `tests/integration/k1/live/m4/test_m4_l1_l6_orchestrator_planner.py` | Live Recipe A `KernelService`; corrected stale row wording from `_state_adapter` to production `_state_port`; asserts `_state_port._reader is svc._session_routing_reader`. |
| M4-L2 | MESSAGE-FLOW | End-to-end T3/HIGH plan: `ORCH_PLAN_REQUESTED` → `k1.planner.plan.ready.v1` → step events → `k1.orchestration.dag.completed.v1` (F45+F95+F96) | E4.x | `[x]` | green | `tests/integration/k1/live/m4/test_m4_l1_l6_orchestrator_planner.py` | Live Recipe A direct `OrchestratorService.handle_task()` with real Planner mailbox and shared Fabric; spy captures production `PlanRequest` shape (`intent`, `trace_id`, `SessionSnapshot.context`, `request_id`); Planner emits `CommittedPlan` with matching `request_id`; DAG executes `tool.read.find_prompts` via controlled MCP edge and emits correlated step/dag completion. |
| M4-L3 | NEGATIVE | `ConcurrencyGuard` depth limit: enqueue N=1000 same plan; assert hard cap | GAP-O02 | `[x]` | xfail strict | `tests/integration/k1/live/m4/test_m4_l1_l6_orchestrator_planner.py` | Strict xfail confirms current `ConcurrencyGuard` exposes only `_active`/`_lock` and has no `max_depth` constructor/property. |
| M4-L4 | NEGATIVE | `PlanStep.to_dict()` round-trip preserves `safety_band_min` | I6.11.C1 | `[x]` | green | `tests/integration/k1/live/m4/test_m4_l1_l6_orchestrator_planner.py` | Direct production contract round-trip through `PlanStep.to_dict()` and `CommittedPlan.from_dict()` preserves non-None `safety_band_min`. |
| M4-L5 | NEGATIVE | `IEmbeddingPort` unwired → `fabric_search` returns error, not silent empty | I6.11.C5 | `[x]` | xfail strict | `tests/integration/k1/live/m4/test_m4_l1_l6_orchestrator_planner.py` | Strict xfail confirms shared Fabric still substitutes `_StubEmbeddingPort` when no embedding port is injected; desired `EmbeddingUnavailableError` is not raised. |
| M4-L6 | PORT-IDENTITY | Planner's `IFabricRetrievalPort` is the shared fabric, not None | E4.x | `[x]` | green | `tests/integration/k1/live/m4/test_m4_l1_l6_orchestrator_planner.py` | Live Recipe A; Planner `ValidateService` and `SketchService` `ToolCallRouter` share the same `FabricRetrievalAdapter`, and its `_fabric is svc._shared_fabric.retrieval`. |

### M4 — Cross-component integration probes

| Step | Probe type | Target | Tracing refs | Status | Verdict | Test file | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M4-X1 | PORT-IDENTITY | `orch._planner_port` is real `PlannerAdapter` over live planner mailbox (extends M2-L2) | I4.X.1 | `[x]` | green | `tests/integration/k1/live/m2/test_m2_l2_planner_orchestrator_crosswire.py` | Covered by M2-L2. |
| M4-X2 | PORT-IDENTITY | `orch._state_port._reader` is `svc._session_routing_reader` (shared with Fabric + Planner) | I4.X.2 | `[x]` | green | `tests/integration/k1/live/m4/test_m4_x2_x13_orchestrator_planner_cross_component.py` | Corrected stale `_state_adapter` wording to production `_state_port`; asserts Orchestrator, Planner `SessionStateReadAdapter`, and Fabric context builder all share `svc._session_routing_reader`. |
| M4-X3 | PORT-IDENTITY | `FabricDispatchAdapter._orchestrator is svc._orchestrator` per session | I4.X.3 | `[x]` | green | `tests/integration/k1/live/m4/test_m4_x2_x13_orchestrator_planner_cross_component.py` | Live Recipe A creates two sessions and asserts each front/back dispatch adapter targets the shared live `OrchestratorService`. |
| M4-X4 | MESSAGE-FLOW | HIGH envelope → planner mailbox depth>0 → Planner emits `k1.planner.plan.ready.v1` on **kernel bus** → Orchestrator receives `CommittedPlan` | I4.X.4 | `[x]` | green | `tests/integration/k1/live/m4/test_m4_x2_x13_orchestrator_planner_cross_component.py` | Live HIGH path with real Planner mailbox, mailbox-depth spy, `PLAN_READY` capture, `CommittedPlan.request_id` correlation, DAG completion, and controlled MCP edge. |
| M4-X5 | MESSAGE-FLOW | 2-wave `CommittedPlan` → `DAGExecutor.execute_wave()` twice → `AggregatedResult` bridged to Back/session bus | I4.X.5 | `[x]` | green | `tests/integration/k1/live/m4/test_m4_x2_x13_orchestrator_planner_cross_component.py` | Corrected stale `DAGEngine.execute_batch()` wording; deterministic planner port publishes `PLAN_READY`, DAG executes waves `[0, 1]`, and `FabricDispatchAdapter` publishes session `task.complete.v1`. |
| M4-X6 | NEGATIVE | Planner `query_planning_context(sid1)` reads `sid1`'s SS, not `sid2`'s (sentinel `""` blast-radius) | I4.X.6 / I2.5.2 | `[x]` | green | `tests/integration/k1/live/m4/test_m4_x2_x13_orchestrator_planner_cross_component.py` | Removed stale xfail: Planner tool router forwards per-call `session_id` and returns distinct `SessionSnapshot` data for `sid1` vs `sid2`. |
| M4-X7 | NEGATIVE | CB_PLANNER OPEN → HIGH envelope degrades to MED (`PlannerAdapter.request_plan` called 0 times) | I4.X.7 | `[x]` | xfail strict | `tests/integration/k1/live/m4/test_m4_x2_x13_orchestrator_planner_cross_component.py` | Strict xfail locks current gap: CB_OPEN raises through `PlannerAdapter.request_plan()` and returns `FAILED`; there is no HIGH→MED fallback path. |
| M4-X8 | NEGATIVE | `k1.planner.plan.failed.v1` → `dispatch_envelope()` returns within timeout (Back not hung) | I4.X.8 / I1.5.1 | `[x]` | xfail strict | `tests/integration/k1/live/m4/test_m4_x2_x13_orchestrator_planner_cross_component.py` | Strict xfail locks current gap: bus `PLAN_FAILED` clears pending context but does not resolve `handle_task()`/Back waiters promptly. |
| M4-X9 | MESSAGE-FLOW | Planner Stage-1 SKETCH `discover_capabilities()` returns freshly-registered test capability | I4.X.9 | `[x]` | green | `tests/integration/k1/live/m4/test_m4_x2_x13_orchestrator_planner_cross_component.py` | Registers valid `tool.read.m4_x9_fresh_capability` in shared Fabric and asserts Planner SKETCH `ToolCallRouter.discover()` returns it. |
| M4-X10 | MESSAGE-FLOW | MicroReplan: ORCH-13 → `PlannerAdapter.micro_replan()` → partial `CommittedPlan` (remaining steps only) | I4.X.10 | `[x]` | green | `tests/integration/k1/live/m4/test_m4_x2_x13_orchestrator_planner_cross_component.py` | Live `MicroReplanCheckpoint` receives post-wave discoveries, sends only remaining steps in `MicroReplanRequest`, and returns the replacement partial `CommittedPlan`. |
| M4-X11 | LIFECYCLE | S6 → S6b → S7 ordering: Planner built, Orchestrator↔Planner cross-wired, then Planner started | I4.X.11 | `[x]` | green | `tests/integration/k1/live/m4/test_m4_x2_x13_orchestrator_planner_cross_component.py` | Corrected stale S6a wording; lifecycle log asserts `S6_complete < S6b_complete < S7_complete` and live `PlannerAdapter._mailbox is svc._planner.get_mailbox()`. |
| M4-X12 | NEGATIVE | Workflow-triggered (cron) plan has no Back handle → return-path gap; xfail strict | I4.X.12 | `[x]` | xfail strict | `tests/integration/k1/live/m4/test_m4_x2_x13_orchestrator_planner_cross_component.py` | Strict xfail locks current gap: `WorkflowRunRequest` has no `session_id`/`reply_to` Back return handle. |
| M4-X13 | MESSAGE-FLOW | `k1.hil.progress.v1` emitted on kernel bus reaches Concierge PROGRESSING via session bus (cross-bus bridge) | I4.X.13 | `[x]` | xfail strict | `tests/integration/k1/live/m4/test_m4_x2_x13_orchestrator_planner_cross_component.py` | Strict xfail locks current gap: Orchestrator progress/HIL deltas emit on kernel bus (`k1.hil.progress.v1` / `k1.agent.orchestrator.delta.v1`) and are not bridged to the per-session bus. |

---

## M6 — Cross-cutting

**Boot recipe:** A (B for M6-L2)
**Issues covered:** 24 (9 L + 15 X) | **GAPs covered:** 6
**Production-grade stamp:** `[ ]`

| Step | Probe type | Target | Tracing refs | Status | Verdict | Test file | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M6-L1 | PORT-IDENTITY | All three SS readers (Orch/Planner/Fabric) point to real per-session SSM — NOT Null/Mock | I6.11.C6 | `[x]` | green | `tests/integration/k1/live/m6/test_m6_l1_l5_cross_cutting.py` | Recipe A live `KernelService`; shared Fabric, Orchestrator, and Planner all share `SessionRoutingStateReader`, it resolves the live session SSM, and per-session Fabric holds `SessionStateReaderAdapter`; Null/Test/Mock readers forbidden. |
| M6-L2 | MESSAGE-FLOW | HIL approval gate end-to-end | E1.8, M6 HIL | `[x]` | green | `tests/integration/k1/live/m6/test_m6_l1_l5_cross_cutting.py` | Recipe B live session HIL uses `HumanInTheLoopService` bound to the session bus; `request_approval()` publishes `k1.hil.request.v1`, a session-bus `k1.hil.response.v1` resolves the Future, and the typed response returns `decision=approve`. |
| M6-L3 | PORT-IDENTITY | SelfModel handle installed as step-0 on both Front and Back dispatchers | selfmodel test I3 | `[x]` | green | `tests/integration/k1/live/m6/test_m6_l1_l5_cross_cutting.py` | Recipe C live session builds `SelfModelHandle`, attaches it to `ConciergeRuntime`, and installs `handle.gate.evaluate` as the policy gate on both dispatchers before start. |
| M6-L4 | LIFECYCLE | SelfModel bundle `health()` returns `status=ok` on live kernel | selfmodel test I4 | `[x]` | green | `tests/integration/k1/live/m6/test_m6_l1_l5_cross_cutting.py` | Recipe C live kernel exposes `SelfModelServiceBundle.health()` with `status=ok`, active non-safe-mode constitution, and SQLite projection store for `family:m6`. |
| M6-L5 | NEGATIVE | Cancel parent task → all child traces cancelled, no orphan envelopes | M6 supervision | `[x]` | xfail strict | `tests/integration/k1/live/m6/test_m6_l1_l5_cross_cutting.py` | Strict xfail locks current supervision gap: `k1/supervision` is empty and `KernelService` has no parent/child cancellation tree; only per-task `CancellationToken` exists today. |

### M6 — Cross-component integration probes

| Step | Probe type | Target | Tracing refs | Status | Verdict | Test file | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M6-X1 | PORT-IDENTITY | Front + Back dispatchers' `_policy_gate is self_model_handle.gate.evaluate` after P3.5 | I6.X.1 | `[x]` | green | `tests/integration/k1/live/m6/test_m6_x1_x15_cross_component.py` | Recipe C live session asserts both dispatchers carry `handle.gate.evaluate` after P3.5 and are tracked by the handle. |
| M6-X2 | LIFECYCLE | `install_into_session` idempotent; `uninstall_from_session` restores originals exactly | I6.X.2 | `[x]` | green | `tests/integration/k1/live/m6/test_m6_x1_x15_cross_component.py` | Production fix: repeated install no longer duplicates dispatcher tracking; uninstall clears gates once and restores wrapped recall callbacks. |
| M6-X3 | MESSAGE-FLOW | Tool call REQUIRE_CONFIRMATION → policy gate blocks → `HIL.ask_approval()` → `hil.response.v1` → Back resumes | I6.X.3 | `[x]` | green | `tests/integration/k1/live/m6/test_m6_x1_x15_cross_component.py` | Production fix: task-scoped Back dispatcher rebind preserves the SelfModel policy gate; forced REQUIRE_CONFIRMATION flows through session HIL approval and resumes dispatch. |
| M6-X4 | LIFECYCLE | `SelfModelServiceBundle.shutdown()` closes owned SQLite; second call is idempotent | I6.X.4 | `[x]` | green | `tests/integration/k1/live/m6/test_m6_x1_x15_cross_component.py` | Owned SQLite projection store is closed on first shutdown, `_owns_store` flips false, and second shutdown is a no-op. |
| M6-X5 | NEGATIVE | `enable_self_model=False` → bundle None, P3.5 skipped, no SelfModel topics fire | I6.X.5 | `[x]` | green | `tests/integration/k1/live/m6/test_m6_x1_x15_cross_component.py` | Recipe A leaves bundle/session handle/runtime handle/gates unset and has no `S2.6_complete` lifecycle event. |
| M6-X6 | LIFECYCLE | `bundle.health()` returns `ok` / `degraded` / `safe_mode` per Constitution state | I6.X.6 | `[x]` | green | `tests/integration/k1/live/m6/test_m6_x1_x15_cross_component.py` | Live bundle reports `ok`; monkeypatched constitution failure reports `degraded`; `bundle.safe_mode=True` reports `safe_mode`. |
| M6-X7 | SUBSCRIPTION | HIL subscribes to `k1.hil.response.v1` on session bus; `ask_approval()` publishes `k1.hil.request.v1` and resolves Future on response | I6.X.7 | `[x]` | green | `tests/integration/k1/live/m6/test_m6_x1_x15_cross_component.py` | Recipe B session HIL subscribes on the session bus, request resolves from session-bus response, and no kernel-bus request is emitted. |
| M6-X8 | NEGATIVE | `SafetyBandPolicy` ALLOW early-exit: GREEN + no side-effects → zero `hil.request.v1` emissions | I6.X.8 | `[x]` | green | `tests/integration/k1/live/m6/test_m6_x1_x15_cross_component.py` | GREEN capability with no side effects returns `GateOutcome.ALLOW` with no HIL request. |
| M6-X9 | LIFECYCLE | `SuspensionManager` limits: 3rd suspension same task raises; per-mode timeouts auto-cancel FSM | I6.X.9 | `[x]` | green | `tests/integration/k1/live/m6/test_m6_x1_x15_cross_component.py` | Concurrent same-task suspension raises, third suspension raises `SuspensionLimitExceeded`, and timeout callback clears active state. |
| M6-X10 | MESSAGE-FLOW | `back_resume_handler` re-reads SS at resume time (fresh snapshot, not stale stored) | I6.X.10 | `[x]` | green | `tests/integration/k1/live/m6/test_m6_x1_x15_cross_component.py` | Resume handler uses a fresh SS read for the resumed prompt instead of the stale pre-suspension snapshot. |
| M6-X11 | NEGATIVE | `enable_hil_service=False` → `_hil_service is None`; `_NullHILAdapter` injected; no `k1.hil.*` topics fire | I6.X.11 | `[x]` | green | `tests/integration/k1/live/m6/test_m6_x1_x15_cross_component.py` | Kernel/session HIL ports are None where expected; Planner/Orchestrator use `_NullHILAdapter`; null approvals emit no HIL topics. |
| M6-X12 | NEGATIVE | `k1/supervision/__init__.py` empty; no supervision tree wired; xfail strict lock-in | I6.X.12 | `[x]` | xfail strict | `tests/integration/k1/live/m6/test_m6_x1_x15_cross_component.py` | Strict xfail locks current supervision gap: no shipped `SupervisionTree` and no KernelService supervision member yet. |
| M6-X13 | MESSAGE-FLOW | `back_cancel_handler` → `CancellationToken.cancel()` → ReAct loop exits before `max_iterations` | I6.X.13 | `[x]` | green | `tests/integration/k1/live/m6/test_m6_x1_x15_cross_component.py` | `back_cancel_handler` sets `CancelReason.USER_REQUESTED`; `react_loop` exits `cancelled` before model execution. |
| M6-X14 | NEGATIVE | `k1/learning/`, `k1/retention/`, `k1/scheduler/`, `k1/tracing/` `__init__.py` empty; no session-bus subs; no SSM touches; xfail strict lock-in | I6.X.14 | `[x]` | xfail strict | `tests/integration/k1/live/m6/test_m6_x1_x15_cross_component.py` | Strict xfail locks current stub-cluster gap: these packages have no shipped Python implementation or session-bus wiring. |
| M6-X15 | NEGATIVE | Learning loop never writes SSM (LEARN-01 single-writer invariant; guard for when learning ships) | I6.X.15 | `[x]` | green | `tests/integration/k1/live/m6/test_m6_x1_x15_cross_component.py` | Static guard scans `k1/learning/**/*.py` for direct SessionState write surfaces; none exist today. |

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
| M7-L1 | MESSAGE-FLOW | `memory.write.v1` round-trip: K1 → Bridge LIVE → pseudo-K0 WAL | F35, F79, F80 | `[x]` | green | `tests/integration/k1/live/m7/test_m7_l1_l6_pseudo_k0_integration.py` | Recipe-C `KernelService` boots `LiveBridgeAdapter`; generated `memory_write_v1.publish()` writes pseudo-K0 WAL with space/actor/band provenance and HMAC envelope fields. |
| M7-L2 | MESSAGE-FLOW | `recall.request.v1` → pseudo-K0 LIKE search → `recall.response.v1` | F39, F40 | `[x]` | green | `tests/integration/k1/live/m7/test_m7_l1_l6_pseudo_k0_integration.py` | `build_recall_fn()` uses live bridge client; seeded pseudo-K0 WAL returns `pseudo_k0.*` LIKE-search hit. Belief selector limitation is asserted as empty per I7.3.2. |
| M7-L3 | MESSAGE-FLOW | `tool_state.changed.v1` SSE wired end-to-end K0 → K1 EventBus | F82 | `[x]` | green | `tests/integration/k1/live/m7/test_m7_l1_l6_pseudo_k0_integration.py` | pseudo-K0 SSE subscriber receives `k1.tool_state.*` command and `_consume_tool_sse()` republishes `k1.tool_state.changed.v1` onto the K1 bus; SSE task is retained/cancelled on shutdown. |
| M7-L4 | MESSAGE-FLOW | `connector.execute.*` → Bridge LIVE → pseudo-K0 `ConnectorHost` | F102 | `[x]` | green | `tests/integration/k1/live/m7/test_m7_l1_l6_pseudo_k0_integration.py` | `LiveBridgeClient.execute_connector()` now routes through `/k0/command.submit` with `connector.execute.<adapter>.<action>` topic; pseudo-K0 `ConnectorHost` callback result returns to K1. |
| M7-L5 | NEGATIVE | Kill pseudo-K0 mid-flight → `LocalOutbox` queues; restart → `DrainWorker` drains; Prometheus counter increments | Bridge outbox | `[x]` | xfail strict | `tests/integration/k1/live/m7/test_m7_l1_l6_pseudo_k0_integration.py` | Strict xfail locks I7.2.4: live `LiveBridgeClient` has no owned `LocalOutbox`/`DrainWorker` recovery or counter path yet. |
| M7-L6 | PORT-IDENTITY | Bridge mode selection at S4: assert correct client class per config (`HttpBridgeClient` / `SinkBridgeClient` / null) | E2.10 | `[x]` | green | `tests/integration/k1/live/m7/test_m7_l1_l6_pseudo_k0_integration.py` | S4 selects LIVE `LiveBridgeAdapter` + runtime `HttpBridgeClient`, SINK `SinkBridgeClient`, and OFFLINE null bridge as configured; no asyncio task leaks after teardown. |

---

## Cross-Cutting / Implicit Flows (No F-Number)

These are not in K1_FLOWS.md but are covered by the SOP and require live coverage.

| # | Description | SOP ref | Status | Notes |
| --- | --- | --- | --- | --- |
| X1 | Bridge envelope signing round-trip (HMAC + Ed25519, canonical JSON, idem-key excluded) | E2.7.9 → M7-L1 | `[ ]` | |
| X2 | LocalOutbox durability under 5xx | E2.7.4 + E7.2.4 → M7-L5 | `[x]` | Covered as strict xfail by M7-L5: live bridge lacks `LocalOutbox`/`DrainWorker` recovery ownership today. |
| X3 | Bridge mode selection at S4 | E2.10 → M7-L6 | `[x]` | Covered by M7-L6 across LIVE/SINK/OFFLINE configurations. |
| X4 | MW pipeline → K0 outbox (SINK mode) | MW + outbox | `[ ]` | |
| X5 | Per-session bus isolation (E2.2 P1) | M5-L5 | `[x]` | Covered by `tests/integration/k1/live/m5/test_m5_l1_l6_bus_ss_mw.py`. |
| X6 | S6b Mock→real planner swap | E2.3 → M2-L2 | `[x]` | Covered by `tests/integration/k1/live/m2/test_m2_l2_planner_orchestrator_crosswire.py`. |
| X7 | Lifecycle teardown order | E2.4.7, E5.11.4 → M2-L1, M5-L3 | `[x]` | M2 teardown was covered by M2-X7; MW-before-SSM teardown is covered by M5-L3. |
| X8 | `BridgeAwareLocalBus` bridge-reserved topic guard (R10) | E2.7.5 → M2-L8 | `[x]` | Covered by M2-L8; production fix applied (wrapped per-session bus at P1). |
| X9 | Pseudo-K0 gap matrix: flows that pass pseudo-K0 but need real K0 policy | E7.6 → M7 series | `[ ]` | |

---

## Known Blocked Flows (Do NOT Mark Live-Verified Until Blocker Cleared)

| Flow(s) | Blocker | Blocker owner | Cleared? |
| --- | --- | --- | --- |
| F60–F64, F68, F90, F94, F131, F140, F148, F153 | **I3.4.5** AgentProvider `mailbox=None` | AgentProvider | `[ ]` |
| F06, F09 (HIGH leg) | **I1.5.1** K1 Orchestrator not wired on HIGH path | Orchestrator | `[x]` |
| F41 | **I6.11.C5** IEmbeddingPort not wired in shared Fabric | Fabric S4 | `[ ]` |
| F78 (default path) | **ISSUE-MW01** topic typo `complete` vs `completed` | MemoryWriter | `[x]` |
| F108 + planner LLM path | **GAP-P02** `build_payload` private import | Planner | `[ ]` |
| F07 (safety, full) | **I6.11.H5** MockStateReadAdapter in prod | Orchestrator | `[x]` |
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
| M5 Bus + SS + MW (L1–L6) | 6 | 6 | 0 | 0 | 100% |
| M5 Cross-component (X1–X19) | 19 | 19 | 0 | 0 | 100% |
| M3 Fabric + ModelHub (L1–L8) | 8 | 8 | 2 | 0 | 100% |
| M3 Cross-component (X1–X9) | 9 | 9 | 1 | 0 | 100% |
| M1 Concierge (L1–L9) | 9 | 9 | 1 | 0 | 100% |
| M1 Cross-component (X1–X12) | 12 | 12 | 2 | 0 | 100% |
| M4 Orch + Planner (L1–L6) | 6 | 6 | 2 | 0 | 100% |
| M4 Cross-component (X1–X13) | 13 | 13 | 4 | 0 | 100% |
| M6 Cross-cutting (L1–L5) | 5 | 5 | 1 | 0 | 100% |
| M6 Cross-component (X1–X15) | 15 | 15 | 2 | 0 | 100% |
| M7 Pseudo-K0 | 6 | 6 | 1 | 0 | 100% |
| Cross-cutting (X1–X9) | 9 | 6 | — | 0 | 67% |
| LLM-COVERED contracts | 5 | 0 | — | 0 | 0% |
| **TOTAL** | **146** | **123** | **17** | **0** | **84%** |

---

*Tracker initialized: 2026-05-13. Expanded with cross-component integration probe rows (76 new X-rows) sourced from k1 `.mmd` diagrams + `service.py` composition root.*
*Sources: `k1_flows_availability_matrix.md` (154 flows) · `kernel_tracing_plan.md` (379 issues + 76 cross-component, 53+ GAPs) · `live_kernel_wiring_test_procedure.md` (44 probe steps) · `K1_FLOWS.md` (vision) · `architecture_diagrams/k1/*.mmd`*
