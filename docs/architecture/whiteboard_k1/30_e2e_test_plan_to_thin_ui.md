# Kernel → Thin-UI End-to-End Test Plan

> **Source:** synthesis of [k1/kernel/service.py](../../../k1/kernel/service.py), `k1/concierge/_scan_temp/`, `docs/whiteboard/temp_kernel_bootstrap/` (28_consolidated_audit_findings, 09_wiring_plan, 08_end_to_end_wiring_requirements), and live inventory of `tests/k1/`, `tests/integration/k1/`, `tests/e2e/`, `scripts/kernel_probe_phase*.py`.
>
> **Goal:** boot the real `KernelService` (no POC, no mocks) and prove every component + every cross-seam + the full thin-UI loop works end-to-end.

---

## §0 Verified state of `k1/kernel/service.py` (composition root)

| Defect previously listed | Actual status | Evidence |
|---|---|---|
| `PlanStep.to_dict()` drops `safety_band_min` | ✅ FIXED | [k1/orchestrator/types.py L706-707](../../../k1/orchestrator/types.py#L706); `from_dict` L738; `envelope_to_step` L771 |
| `PlannerStateAdapter(reader=None)` | ✅ FIXED (P1.3) | [k1/kernel/service.py L1297-1300](../../../k1/kernel/service.py#L1297) — `reader=self._session_routing_reader` |
| `MockStateReadAdapter` in Orchestrator | ✅ FIXED (P1.2) | [k1/kernel/service.py L1254](../../../k1/kernel/service.py#L1254) — `StateReadAdapter(state_reader=session_routing_reader)` |
| Shared Fabric uses `NullSessionStateReaderAdapter` | ✅ FIXED (P1.1) | `self._session_routing_reader: SessionRoutingStateReader` built before S3 |
| SSM does not satisfy `IStatePort` (needs `SSMStateAdapter`) | ✅ FIXED | [k1/kernel/service.py L1696](../../../k1/kernel/service.py#L1696) — `session_state_port = SSMStateAdapter(ssm)` |
| Fabric WORKFLOW + CONCIERGE provider deps not injected | ✅ FIXED | [k1/fabric/factory.py L237-258](../../../k1/fabric/factory.py#L237) — explicit `port_deps` plumbing with `ValueError` if missing |
| Orchestrator `__slots__` blocks Planner hot-swap | ✅ FIXED | `_planner_port` reassignable; verified by [`_verify_planner_orchestrator_crosswire()`](../../../k1/kernel/service.py#L959) and `bind_planner()` |
| `NullMemoryAdapter` / `memory=None` in PortBundle | ✅ FIXED (P5.2) | [k1/kernel/service.py L1719](../../../k1/kernel/service.py#L1719) — `RecallMemoryAdapter(build_recall_fn(self._bridge.get_client()))` |
| `HealthAdapter.get_started=lambda: False` | ✅ FIXED (P5.3) | [k1/kernel/service.py L1761-1763](../../../k1/kernel/service.py#L1761) — `lambda: session_memory_writer.is_started` |
| `k1/kernel/` is dead, real path is `k1/concierge/kernel/bootstrap.py` | ✅ FIXED — `k1/kernel/service.py` IS the live composition root | `k1/concierge/kernel/bootstrap.py` is now a thin shim that re-exports from `k1.kernel.bootstrap` |
| `k1/concierge/kernel/bootstrap.py` imports `poc.k1_poc.*` | ✅ FIXED | grep returns zero `poc.*` imports in current bootstrap |
| `admin_http` `isinstance` bug | ✅ N/A — file `k1/orchestrator/adapters/admin_http.py` no longer exists | grep miss; admin path moved |

**Net:** the boot crashes the previous report described are gone. What follows is the actual remaining work.

---

## §1 Real remaining wiring gaps

Only items that genuinely block a real boot or a real first user turn.

### G1 — SessionState bridge/writer/lifecycle stubs are dormant code (was A-4)

| File | Stubbed methods | Wired into kernel? |
|---|---|---|
| [k1/sessionstate/adapters/bridge_storage.py](../../../k1/sessionstate/adapters/bridge_storage.py) | 4× `NotImplementedError` | NO |
| [k1/sessionstate/adapters/bridge_sync.py](../../../k1/sessionstate/adapters/bridge_sync.py) | 4× `NotImplementedError` | NO |
| [k1/sessionstate/adapters/concierge_writer.py](../../../k1/sessionstate/adapters/concierge_writer.py) | 3× `NotImplementedError` | NO |
| [k1/sessionstate/adapters/delta_bus.py](../../../k1/sessionstate/adapters/delta_bus.py) | 3× `NotImplementedError` | NO |
| [k1/sessionstate/adapters/fabric_lifecycle.py](../../../k1/sessionstate/adapters/fabric_lifecycle.py) | 2× `NotImplementedError` | NO |

Kernel boots clean today because these adapters are not used. They will block: (a) Bridge cloud sync when K0 HTTP API ships, (b) Bus→SS event bridging, (c) Concierge-routed SS mutations from FSM. Implement before the bridge surface lights up.

### G2 — Bridge surface is not built (was A-15, E-1..E-13)

[bridge/adapters/](../../../bridge/adapters) contains only `__init__.py`. Required adapters (none exist):

| Port (protocol) | Needed adapter | Scope |
|---|---|---|
| `IKernelQueryPort` ([bridge/ports/query_port_protocol.py](../../../bridge/ports/query_port_protocol.py)) | `KernelQueryPortOffline` | ~150 LOC |
| `IKernelSSEPort` ([bridge/ports/sse_port_protocol.py](../../../bridge/ports/sse_port_protocol.py)) | `KernelSSEPortOffline` | ~150 LOC |
| `IKernelObsPort` ([bridge/ports/obs_port_protocol.py](../../../bridge/ports/obs_port_protocol.py)) | `KernelObsPortOffline` (also fix NORMAL/HIGH drop bug in `bridge/client.py:emit_obs`) | ~200 LOC |
| `IConnectorGatewayPort` | deferred (IFL — MS-3) | n/a |
| `IBridgeClient` HTTP backend (`HttpBridgeClient`) | **BLOCKED** on K0 HTTP API | ~300 LOC |
| `IInputPort` thin-UI ingress | `WebSocketInputAdapter` ([k1/concierge/adapters/ws_input.py](../../../k1/concierge/adapters/ws_input.py)) | ~50 LOC |
| `IOutputPort` thin-UI egress | `SSEOutputAdapter` ([k1/concierge/adapters/sse_output.py](../../../k1/concierge/adapters/sse_output.py)) | ~50 LOC |

Without these, the kernel can run but no thin UI can connect.

### G3 — Concierge MED/HIGH dispatch still goes through `OrchestratorStub` (was B-12)

[k1/concierge/factory.py L263-283](../../../k1/concierge/factory.py#L263) wires `OrchestratorStub` into the Concierge `IDispatchPort`. The real Orchestrator boots in S5 and the Concierge `FabricDispatchAdapter` references it (line 1707), but tier resolution + `route_task_with_degradation` is not wired into the FSM yet (DEFERRED-9).

### G4 — Bus has no outbox at boot (was probe Phase 7 documented gap)

[k1/kernel/service.py](../../../k1/kernel/service.py) `BusFactory.create_local_ordered()` is invoked without `outbox=`. Crash-replay works in isolation tests but not in a real kernel restart.

### G5 — `emergency.activated` SSM event has no subscriber (was A-21)

SSM emits the event when memory pressure spikes; no component subscribes. Emergency mode is invisible — Orchestrator continues full-throttle, MemoryWriter does not throttle.

### G6 — Saga compensation body not wired (was Phase 5 INFO/WARN)

`OrchestratorService._compensate()` body absent per probe Phase 5 commentary. `Saga.compensate()` is interface-only.

### G7 — Empty test directories

| Directory | State |
|---|---|
| [tests/e2e/p03/](../../../tests/e2e/p03) | empty (only `__pycache__`) |
| [tests/k1/bridge_k0/](../../../tests/k1/bridge_k0) | empty (only `__pycache__`) |

### G8 — DEFERRED items still actionable (from 09_wiring_plan)

`DEFERRED-8`, `DEFERRED-9`, `DEFERRED-10`, `DEFERRED-11`, `DEFERRED-12` (MS-4 Epics 4.2–4.5: tier routing, CB degradation cascade, cross-component data flow, full turn cycle). `DEFERRED-13`, `DEFERRED-15`, `DEFERRED-16` (TD sweeps). `DEFERRED-17` partial (P7.1/2/3/5/6/7 actionable; P7.4 blocked).

### G9 — Concierge untested modules (from 12_tests.md)

Files with zero dedicated tests (high-priority subset):

- [k1/concierge/kernel/bootstrap.py](../../../k1/concierge/kernel/bootstrap.py) (now thin shim — low risk)
- [k1/concierge/kernel/runner.py](../../../k1/concierge/kernel/runner.py)
- [k1/concierge/orchestrator/{degradation,routing,stub}.py](../../../k1/concierge/orchestrator)
- [k1/concierge/protocols/hitl_{flow,persistence,pipeline}.py](../../../k1/concierge/protocols)
- [k1/concierge/scheduler/proactive_scheduler.py](../../../k1/concierge/scheduler/proactive_scheduler.py)
- [k1/concierge/task/{dependency_queue,envelope_bridge,tools}.py](../../../k1/concierge/task)
- Milestones M06, M07, M12–M14 have **no** test files in `tests/k1/concierge/`.

---

## §2 Test layering — 5 tiers

### Tier 1 — Per-component real-feature tests

Existing coverage is strong (~1,900 tests across `tests/k1/`). Gap suites to add — **all using real adapters, no `MagicMock`**:

| # | Component | Existing real-E2E | Gap to add |
|---|---|---|---|
| T1.1 | Bus | [tests/k1/bus/test_phase6_e2e.py](../../../tests/k1/bus/test_phase6_e2e.py), [tests/k1/bus/outbox/test_durability.py](../../../tests/k1/bus/outbox/test_durability.py) | `tests/k1/kernel/test_kernel_bus_outbox.py` — wire `outbox=BusOutbox(path)` in kernel S1, restart kernel, assert durable topics replay (G4) |
| T1.2 | SessionState | sections/, tiers/, [test_factory.py](../../../tests/k1/sessionstate/test_factory.py), [test_crash_recovery.py](../../../tests/k1/sessionstate/test_crash_recovery.py) | `tests/k1/sessionstate/test_emergency_subscriber_chain.py` — emit `emergency.activated`, assert Orch pause + MW throttle (G5) |
| T1.3 | SessionState bridge stubs | none | `tests/k1/sessionstate/adapters/test_no_unimplemented_in_prod_path.py` — invariant: every method on the 5 G1 adapters has a real impl before kernel uses them |
| T1.4 | Fabric | [test_safety_band_e2e.py](../../../tests/k1/fabric/test_safety_band_e2e.py), [test_fabric_execute_with_gate.py](../../../tests/k1/fabric/test_fabric_execute_with_gate.py), tools/ | `tests/k1/fabric/test_embedding_port_real.py` — assert `discover_capabilities("intent")` returns non-empty with real embedding port |
| T1.5 | ModelHub | [integration/test_full_pipeline.py](../../../tests/k1/model_hub/integration/test_full_pipeline.py) | `tests/k1/model_hub/test_bus_subscribed_execute.py` — `bus.publish("k1.model_hub.execute.v1", req)` → ModelHub responds via bus |
| T1.6 | Orchestrator | [test_workflow_e2e.py](../../../tests/k1/orchestrator/test_workflow_e2e.py), [test_dag_resume_after_hil.py](../../../tests/k1/orchestrator/test_dag_resume_after_hil.py) | `tests/k1/orchestrator/test_reaper_timeout_compensation.py` — force step timeout, assert reaper compensates (G6 surface) |
| T1.7 | Planner | [test_factory.py](../../../tests/k1/planner/test_factory.py), pipeline tests | `tests/k1/planner/test_real_state_read.py` — boot kernel, write SS belief, assert Planner reads it via wired `session_routing_reader` |
| T1.8 | Concierge | [test_bootstrap_smoke.py](../../../tests/k1/concierge/test_bootstrap_smoke.py), [test_concierge_factory.py](../../../tests/k1/concierge/test_concierge_factory.py), m08–m11 | `tests/k1/concierge/test_runner_smoke.py` + per untested module in G9 |
| T1.9 | MemoryWriter | [test_pipeline.py](../../../tests/k1/memory_writer/test_pipeline.py), [test_fabric_integration.py](../../../tests/k1/memory_writer/test_fabric_integration.py) | `tests/k1/memory_writer/test_recall_round_trip.py` — write memory, assert `recall_memory(query)` returns it (live `RecallMemoryAdapter`) |
| T1.10 | HIL | [test_service.py](../../../tests/k1/hil/test_service.py), [test_service_front_roundtrip.py](../../../tests/k1/hil/test_service_front_roundtrip.py) | strong — no gap |
| T1.11 | SelfModel | tests/k1/selfmodel/ + probe Phase 9a–e | `tests/integration/k1/selfmodel/test_kernel_with_selfmodel.py` already exists; extend with HIL escalation case |
| T1.12 | Bridge | none in [tests/k1/bridge_k0/](../../../tests/k1/bridge_k0) | `tests/k1/bridge_k0/test_offline_query_port.py` once G2 KernelQueryPort built |

### Tier 2 — Cross-component seams

Each test boots `KernelService.startup()` → `create_session()` and exercises **two real services on the real bus**.

| # | Seam | Status / file |
|---|---|---|
| T2.1 | dispatch_task → bus → tier subscriber (LOW/MED/HIGH) | exists: [tests/k1/integration/test_dispatch_task_bus_hop.py](../../../tests/k1/integration/test_dispatch_task_bus_hop.py); extend HIGH once G3 wired |
| T2.2 | Tier routing via `route_task_with_degradation` | `tests/k1/integration/test_tier_routing.py` — DEFERRED-8/9 |
| T2.3 | CB degradation cascade | `tests/k1/integration/test_cb_degradation.py` — DEFERRED-10 |
| T2.4 | SS → Orch → Planner → Fabric data flow | `tests/k1/integration/test_data_flow.py` — DEFERRED-11; assert one belief written in SS surfaces in Planner context, Orch safety gate, Fabric ContextBuilder |
| T2.5 | Concierge ↔ MW recall round-trip | `tests/k1/integration/test_concierge_mw_recall.py` — covers G9 recall, paired with T1.9 |
| T2.6 | Concierge ↔ Orchestrator HIGH tier | `tests/k1/integration/test_concierge_orch_high.py` — DEFERRED-19 (blocked on G3 + real Planner integration) |
| T2.7 | Workflow scheduling end-to-end | exists: [test_workflow_e2e.py](../../../tests/k1/orchestrator/test_workflow_e2e.py), [test_concurrent_workflow_user_e2e.py](../../../tests/k1/orchestrator/test_concurrent_workflow_user_e2e.py) — extend with cron trigger + supervisor restart |
| T2.8 | HIL across all 5 surfaces | exists: [tests/k1/integration/hil/](../../../tests/k1/integration/hil) — add `test_e2e_workflow_hil.py` for WorkflowSupervisor HIL |
| T2.9 | Delta aggregator → bus → SS update | `tests/k1/integration/test_delta_to_ss.py` — depends on G1 `delta_bus.py` impl |

### Tier 3 — Full-stack turn cycle

| # | Suite | Scope |
|---|---|---|
| T3.1 | `tests/k1/integration/test_turn_cycle_low.py` | LOW: publish `TOPIC_USER_INPUT` → FSM LISTENING→DISPATCHING→RESPONDING → assert `TOPIC_FINAL_RESPONSE` + ledger row + delta + MW write |
| T3.2 | `tests/k1/integration/test_turn_cycle_medium.py` | MED: T3.1 plus `TOPIC_TASK_DISPATCH` → real Orch DAG → result merged |
| T3.3 | `tests/k1/integration/test_turn_cycle_high.py` | HIGH: T3.2 plus Planner SKETCH→EXPAND→VALIDATE→COMMIT (depends on G3 + DEFERRED-19) |
| T3.4 | `tests/k1/integration/test_turn_multiturn.py` | 3 sequential turns; turns 2 + 3 must read recall from turn 1 |
| T3.5 | `tests/k1/integration/test_turn_concurrent.py` | 2 concurrent sessions; assert no cross-session belief leak |
| T3.6 | `tests/k1/integration/test_turn_dead_letter_recovery.py` | Inject second `user_input` while FSM in `DISPATCHING` — reproduces `scripts/smoke_tier_test.out.txt` failure; assert dead-letter handled, FSM returns to LISTENING, next turn succeeds |

### Tier 4 — Thin-UI surface

Build adapters in this order, then test:

| Build | File | Test |
|---|---|---|
| B1 | `bridge/adapters/kernel_query_port.py` (G2, ~150 LOC) | `tests/k1/bridge_k0/test_query_port_offline.py` |
| B2 | `bridge/adapters/kernel_sse_port.py` (G2, ~150 LOC) | `tests/k1/bridge_k0/test_sse_port_offline.py` |
| B3 | `bridge/adapters/kernel_obs_port.py` (G2, ~200 LOC + emit_obs NORMAL/HIGH drop bug) | `tests/k1/bridge_k0/test_obs_port_offline.py` |
| B4 | [k1/concierge/adapters/ws_input.py](../../../k1/concierge/adapters) (~50 LOC) | `tests/integration/concierge/test_ws_input_to_fsm.py` |
| B5 | [k1/concierge/adapters/sse_output.py](../../../k1/concierge/adapters) (~50 LOC) | `tests/integration/concierge/test_fsm_to_sse_output.py` |
| **B6** | n/a — composition test | **`tests/integration/test_ws_to_sse_full_loop.py`** — WS client connects → sends `user_input` → kernel processes → SSE chunks streamed → `[DONE]` marker. Drives every layer T3 covers, but over actual UI transport. **This is the thin-UI bootstrap proof.** |

`HttpBridgeClient` (G2 row 5) stays blocked on K0 HTTP API; `SinkBridgeClient` is the only valid path until then.

### Tier 5 — Continuous probe runner in CI

12 phase probes already exist in [scripts/](../../../scripts). Make them CI-runnable and add 5 missing phases:

1. New `scripts/run_all_probes.py` — invokes phase 1→9e in order, aggregates `data/kernel_probe_phase*.json` via `_aggregate_probe_gaps.py`, exits non-zero on any FAIL.
2. CI hook — `pytest -m kernel_probe` triggers the runner; fail build if FAIL count regresses.
3. New phases:
   - `kernel_probe_phase10_bridge.py` — once B1–B3 land, drive real bridge traffic + reconnect
   - `kernel_probe_phase11_planner_concierge.py` — real Planner from Concierge HIGH-tier turn (today uses `PassthroughPlannerStub`)
   - `kernel_probe_phase12_saga.py` — once G6 wired
   - `kernel_probe_phase13_multi_session.py` — two concurrent sessions, isolation
   - `kernel_probe_phase14_reaper.py` — force step timeout, observe reaper

---

## §3 Test harness

### `tests/integration/conftest.py` — `kernel_real()` fixture

```python
@pytest.fixture
async def kernel_real(tmp_path):
    cfg = KernelConfig(workflow_db_path=str(tmp_path / "workflow.db"))
    k = KernelService(cfg)
    await k.startup()
    sid = await k.create_session(device_id="test-device")
    yield k, sid
    await k.shutdown()
```

Every Tier 2/3 test uses this. Guarantees real boot, no per-test mock divergence.

### `scripts/drive_thin_ui.py`

Reuses `scripts/test_kernel_tiers.py` pattern but reads scenarios from a JSON file (10–20 scripted user turns covering LOW / MED / HIGH / interrupt / cancel / HIL / workflow). Output: pass/fail per turn + bus event trace. Becomes the daily smoke against a real kernel.

---

## §4 Gated execution order

```
GATE 0 — verify §0 status holds (run existing tests/k1/concierge/test_bootstrap_smoke.py + test_concierge_factory.py green)
   ↓
GATE 1 — fill Tier 1 gaps T1.1, T1.2, T1.4, T1.5, T1.6, T1.7, T1.9
   ↓
GATE 2 — Tier 2 seams T2.1, T2.2 (DEFERRED-8/9), T2.3 (DEFERRED-10), T2.4 (DEFERRED-11), T2.5, T2.7, T2.8, T2.9
   ↓
GATE 3 — Tier 3 turn cycles T3.1, T3.2, T3.4, T3.5, T3.6 (T3.3 needs G3 + DEFERRED-19)
   ↓
GATE 4 — implement G2 builds B1..B5
   ↓
GATE 5 — Tier 4 thin-UI full-loop test B6 green
   ↓
GATE 6 — Tier 5 all probes green in CI (12 existing + 5 new)
   ↓
KERNEL READY for thin-UI bootstrap
```

---

## §5 Concrete first sprint (one-week)

1. **Day 1** — implement G1: write real impls for the 5 dormant SS adapters (`bridge_storage`, `bridge_sync`, `concierge_writer`, `delta_bus`, `fabric_lifecycle`). Add T1.3 invariant test.
2. **Day 2** — Tier 1 gaps: T1.1 (kernel bus outbox), T1.2 (emergency subscriber), T1.9 (MW recall round-trip).
3. **Day 3** — Tier 2 seams: T2.4 (data flow — verifies §0 fixes hold), T2.5 (concierge↔MW), T2.9 (delta→SS — pairs with G1 `delta_bus`).
4. **Day 4** — Tier 3 turn cycles: T3.1 (LOW), T3.2 (MED), T3.6 (dead-letter recovery — closes the exact failure in `smoke_tier_test.out.txt`).
5. **Day 5** — Tier 4 builds B4 + B5 (WS-in / SSE-out) + B6 thin-UI full-loop test.

After this sprint: a thin UI client connects to a real kernel, sends a turn, receives a streamed response. Machine-checked proof that nothing along the path is a mock.

---

## §6 Out of scope (explicitly deferred)

- HIGH tier full pipeline (G3 + DEFERRED-19; needs Concierge `route_task_with_degradation` wired into FSM **and** real Planner end-to-end)
- `HttpBridgeClient` real K0 traffic (DEFERRED-17 P7.4 — blocked on K0 HTTP API)
- IFL connector (DEFERRED-18, MS-3 scope)
- UltraBERT / Prometheus real backends (DEFERRED-18)
- Saga compensation (G6 — implement after Tier 3 turn cycles green)

---

## §7 Definition of "kernel ready for thin-UI bootstrap"

All of the following must be GREEN in CI:

1. `pytest tests/k1/concierge/test_bootstrap_smoke.py tests/k1/concierge/test_concierge_factory.py` — full kernel boot
2. `pytest tests/k1/integration/` — every Tier 2 + Tier 3 suite listed above
3. `pytest tests/integration/test_ws_to_sse_full_loop.py` — Tier 4 B6 thin-UI loop
4. `python scripts/run_all_probes.py` — all 12 + 5 = 17 phase probes
5. `python scripts/drive_thin_ui.py scenarios/daily_smoke.json` — daily scripted scenario

When (1)–(5) are green, the kernel is ready to accept connections from the thin UI.
