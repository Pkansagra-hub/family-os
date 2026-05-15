# K1 Live-Kernel End-to-End Wiring Test Procedure (SOP)

> **Purpose.** Define a **standard operating procedure** for verifying every component
> of the K1 kernel on a *live, booted* `KernelService` — **not** with isolated unit
> mocks. We boot the real composition root, attach probes to the real bus and the
> real adapter graph, drive real envelopes through real ports, and assert real
> identities, real subscriptions, real ordering, and real lifecycle behaviour.
>
> **Companion docs:**
>
> - [kernel_tracing_plan.md](kernel_tracing_plan.md) — *what* to verify (344 issues)
> - [three_tier_findings_vs_expectations.md](three_tier_findings_vs_expectations.md) — tier gap analysis
> - This doc — *how* to verify it on a live kernel
>
> **Scope of this document.** Process and methodology only. Concrete probe code
> goes in `tests/integration/k1/live/` (new subtree) once this SOP is ratified.

---

## 0. Why live-kernel wiring tests

A written audit (the tracing plan) catches **declarative** drift: a contract says X,
the code does Y. It cannot catch the bugs that bit us most:

| Failure class | Caught by audit? | Caught by unit mock test? | Caught by live kernel? |
|---|:---:|:---:|:---:|
| Topic name typo (`turn.complete` vs `turn.completed`, MW01) | sometimes | **no** — mock subscribes to same string | **yes** — publisher and subscriber don't meet on real bus |
| Object identity drift (shared vs per-session instance) | no | no — mock returns whatever | **yes** — `is` check on live graph |
| Subscriber registered to the wrong bus instance | no | no | **yes** — publish on bus A, capture on bus B |
| Lifecycle stop order (`ssm.stop()` before MW flush, MW04) | partial | no — mocks have no ordering constraints | **yes** — real stop sequence, real flush |
| Background task identity (`concierge_task is consumer_task`, OPEN §6) | yes | n/a | **yes** — `asyncio.all_tasks()` walk |
| Mock adapter wired in production (`MockStateReadAdapter`, H5) | yes | no — test installs another mock on top | **yes** — `isinstance(adapter, Mock*)` assertion on live graph |
| Cross-wire failure (S6b Mock→real planner swap) | yes | no | **yes** — `orchestrator._planner_port` is a real `PlannerAdapter` over `svc._planner.get_mailbox()` |
| Silent fallback (`_FirstSessionSSMShim` reads session 0 always) | yes | no | **yes** — boot 2 sessions, observe MH routing |
| TTL not enforced on `LocalBus` (B01) | yes | no | **yes** — time skew + capture |

**Decision:** mocks are reserved for **external** edges (K0 bridge sink, real LLM
providers, real MCP servers). Every internal port/adapter wire is exercised with
the actual implementation.

---

## 1. Vocabulary

| Term | Definition |
|---|---|
| **Live kernel** | A real `KernelService` instance, booted via `svc = KernelService(cfg); await svc.startup()`. |
| **Hermetic boot** | Live kernel with `KernelConfig(test_mode=True, model_mode="test", bridge_enabled=False, otel_enabled=False)` and SQLite paths under `tmp_path` so the test owns the whole world. |
| **Probe** | A read-only inspection on a live kernel (introspection, capture, identity check). |
| **Drive** | A write into the live kernel (publish envelope, call `create_session`, invoke capability). |
| **Wire-path test** | A test whose assertions all reference *real* objects reachable from `svc`. No `unittest.mock.Mock` in the assertion subject. |
| **Negative-wire test** | A test that intentionally breaks one wire (deletes a subscription, swaps in `Null*Adapter`) and asserts the failure mode is loud, not silent. |

---

## 2. Booting the kernel — recipes

Every live test starts from one of these recipes. All four boot a **real** kernel;
they differ only in which external edges are stubbed.

### Recipe A — Hermetic (default)

Use for: M1, M2, M4, M5 wiring. The whole kernel runs in-process; no K0, no
internet, no real LLM. Bridge is `OfflineBridgeAdapter`.

```text
KernelConfig(
    test_mode=True, model_mode="test",
    ordered_bus=True, session_mode="standalone",
    bridge_enabled=False, bridge_offline_ok=True,
    otel_enabled=False,
    sessionstate_db_path=tmp_path / "ssm.db",
    workflow_db_path=tmp_path / "wf.db",
    bridge_outbox_path=tmp_path / "bridge.db",
)
```

Source of truth: [tests/k1/integration/concierge/conftest.py](tests/k1/integration/concierge/conftest.py) `kernel_config` fixture.

### Recipe B — HIL enabled

Use for: M6 HIL epics, M1 E1.8.

```text
Recipe A + enable_hitl=True, enable_hil_service=True
```

### Recipe C — SelfModel enabled

Use for: M6 SelfModel epics.

```text
Recipe A + enable_self_model=True, selfmodel_family_space_id="family:test"
```

See [tests/integration/k1/kernel/test_kernel_with_selfmodel.py](tests/integration/k1/kernel/test_kernel_with_selfmodel.py) as the reference shape.

### Recipe D — Live K0 (rare)

Use for: bridge command outbox round-trip only (M2 E2.7 §I2.7.2).
Requires `docker compose up -d` and is gated by the `requires_live_k0` marker in
[tests/integration/harness/conftest.py](tests/integration/harness/conftest.py).

---

## 3. The five canonical probe types

Every live-kernel test is **exactly one** of these five shapes. If a test does not
fit, redesign it before writing it.

### 3.1 PORT-IDENTITY probe

**Question answered:** *"Is the port that component A holds the same object the
factory wired into component B?"*

**Recipe.**

1. Boot a live kernel.
2. Reach into `svc` and grab the adapter on each side.
3. Assert `a is b` (or `a is b._port`, depending on layer).
4. Tear down.

**Example targets** (mapped to tracing plan):

| Tracing-plan issue | Identity claim |
|---|---|
| M2 I2.7.7 inv-7 | `svc.sessions[s1].bridge_client is svc.sessions[s2].bridge_client is svc.bridge_client` |
| M2 I2.3.1 (S6b) | `svc._orchestrator._planner_port` is `PlannerAdapter`, not `MockPlannerAdapter`, and `._mailbox is svc._planner.get_mailbox()` (post-startup) |
| M2 I2.4.6 (OPEN §6) | `svc.sessions[s].concierge_task is svc.sessions[s].consumer_task` |
| M3 E3.6 (FAB-01) | `svc.sessions[s].fabric._state_reader is svc.sessions[s].ssm` (or wraps it), **not** `NullSessionStateReaderAdapter` |
| M4 H5 / I6.11.H5 | `not isinstance(svc.orchestrator._state_adapter, MockStateReadAdapter)` |
| M2 I2.5.1 (OPEN §1) | `svc.model_hub._state_read_port is svc.sessions[s].ssm` — currently fails (reads session 0 always) |

### 3.2 SUBSCRIPTION-TOPOLOGY probe

**Question answered:** *"On the live bus, who is subscribed to what, and does any
publisher's topic actually match any subscriber's topic?"*

**Recipe.**

1. Boot live kernel.
2. Enumerate subscriptions on `bus._subscriptions` (or expose a read-only API —
   see §6 *Required introspection hooks*).
3. Enumerate static publisher topics by grepping bus envelope builders in
   [k1/concierge/bus/builders.py](k1/concierge/bus/builders.py),
   [k1/memory_writer/bus/](k1/memory_writer/bus/), etc.
4. Compute set difference. Any publish-only or subscribe-only topic is a smoking gun.

**Killer test (MW01).** Publish `k1.session.turn.complete.v1` via the real
`ConciergeRuntime` end-of-turn path; subscribe a `BusCapture` to the live MW
dispatcher's actual subscription. If `complete` vs `completed` is wrong, capture
times out. **Mock unit tests cannot catch this** because they typically subscribe to
the same constant the publisher uses.

| Tracing-plan issue | Pair to verify on live bus |
|---|---|
| M5 I-5.8.1 (MW01) | publisher: Concierge end-of-turn; subscriber: `SessionBatchDispatcher` |
| M5 I-5.3.4 (B01)  | TTL: publish at t, capture at t+ttl+ε must NOT deliver |
| M1 I1.5.3 | order: `task.dispatch.v1` strictly before `response.final.v1` |
| M2 I2.7.5 (R10) | `BridgeAwareLocalBus` refuses publish on reserved topics |
| M5 I-5.6.x | per-session bus isolation: publish on session A's bus must NOT reach session B's subscribers |

### 3.3 MESSAGE-FLOW probe (end-to-end envelope trace)

**Question answered:** *"When I push a real user message in at the input port,
does the envelope graph match the contract from origin to destination?"*

**Recipe.**

1. Boot live kernel.
2. Attach `BusCapture` to *every* topic in the expected path (use a list — one
   `BusCapture` per topic).
3. Drive: `await svc.create_session(...)`, then publish a synthetic
   `k1.input.user.v1` envelope onto the session bus.
4. `await asyncio.wait_for(asyncio.gather(*[c.wait_one() for c in captures]), timeout=10)`.
5. Assert (a) every expected envelope arrived, (b) envelope **ordering** is correct,
   (c) every envelope carries `cognitive_trace_id` and `session_id` consistently,
   (d) no unexpected dead-letter on `k1.dead.letter.v1`.

**Reference flow — LOW-tier happy path** (T1, Front-only):

```text
k1.input.user.v1
   → fsm.phase1_complete
   → fsm.state=DISPATCHING
   → k1.front.response.delta.v1 (stream)
   → k1.front.response.final.v1
   → k1.session.turn.complete.v1
   → k1.delta.mutation.v1 (MW intake)
   → fsm.state=LISTENING
```

**Reference flow — MED-tier with dispatch** (T2):

```text
k1.input.user.v1
   → k1.task.dispatch.v1                  (← Front emits)
   → k1.capability.invoked.v1             (← Fabric STEP 1)
   → k1.capability.completed.v1           (← Fabric STEP 9)
   → k1.task.complete.v1                  (← Orchestrator)
   → k1.weave.emit.v1                     (← WeavePolicy)
   → k1.front.response.final.v1
   → k1.session.turn.complete.v1
```

**Reference flow — HIGH-tier with planner** (T3):

```text
k1.input.user.v1
   → k1.task.dispatch.v1                  (← Front emits plan=True / HIGH)
   → IDispatchPort.dispatch_envelope      (← FSM canonical TaskEnvelope)
   → OrchestratorService.process()
   → Planner SKETCH / EXPAND / VALIDATE
   → committed DAG execution via shared Fabric
   → k1.capability.invoked.v1             (← Fabric STEP 1)
   → k1.capability.completed.v1           (← Fabric STEP 9)
   → k1.task.complete.v1                  (← Orchestrator result bridge)
   → k1.front.response.final.v1           (← same-turn deterministic ack)
   → k1.session.turn.complete.v1
```

### 3.4 LIFECYCLE-ORDER probe

**Question answered:** *"Does the live kernel actually tear down in the documented
order, and does anything leak?"*

**Recipe.**

1. Monkey-patch each component's `start()` / `stop()` (or wrap with a `__call__`
   that appends to a shared list) **before** `await svc.startup()`.
2. Boot, exercise minimally, shutdown.
3. Assert the recorded sequence equals the documented order.
4. After `await svc.shutdown()`:
   - `assert len(asyncio.all_tasks()) - baseline == 0`
   - `assert svc._running is False`
   - all SQLite files in `tmp_path` are closed (no `.shm` / `.wal` lingering).

| Tracing-plan issue | Ordering assertion |
|---|---|
| M2 I2.1.3 | startup S1→S7; shutdown S7→S1 |
| M2 I2.4.7 | per-session teardown MW → Concierge → SSM → Router → Bus |
| M5 I-5.11.4 | MW.stop must complete **before** SSM.stop begins |
| M1 I1.10.3 | concierge.stop before bus.close |
| M2 I2.4.9 | each step bounded by `_TEARDOWN_TIMEOUT = 10 s` |
| M2 I2.4.10 (GAP) | `ssm.stop()` currently has no timeout — assert ≤ 10 s; if it hangs, that's the GAP confirmed |

### 3.5 NEGATIVE-WIRE probe

**Question answered:** *"When a wire is intentionally broken, does the kernel fail
loudly (typed error, dead-letter, structured log) instead of silently?"*

**Recipe.**

1. Boot live kernel.
2. After startup, **break one wire** at the live object graph:
   - swap an adapter to `None`,
   - unsubscribe a critical handler,
   - publish a malformed envelope,
   - exceed a budget / depth / TTL.
3. Drive the same flow as §3.3.
4. Assert the failure surface:
   - a typed exception is raised on the call site (preferred), **or**
   - an envelope is published on `k1.dead.letter.v1` with `reason` populated, **or**
   - a structured log entry is emitted (captured via `caplog`).

**Forbidden outcome:** flow completes "successfully" with degraded behaviour and no
visible signal. Every silent-fallback GAP in the tracing plan owns a negative-wire
test that proves the GAP exists today.

| GAP | Negative probe |
|---|---|
| M3 FAB-15 (`None` conscience port short-circuits) | `svc.fabric._conscience_port = None`; expect `safety_band=AMBER` invocation to be REJECTED, not allowed. Today: allowed silently. |
| M6 I6.11.H5 (`MockStateReadAdapter`) | assert `isinstance(...)` is not Mock; if it is, fail with explicit message. |
| M1 ISSUE-C08 (Back resumes with `None` resolution) | drop a `SuspensionManager` row, trigger resume, expect explicit error not hallucination |
| M4 GAP-O02 (`ConcurrencyGuard` no depth limit) | enqueue plan recursively N=10000; expect hard cap, not OOM |
| M3 ISSUE-M01 (ModelHub 10 bus topics suppressed) | subscribe to all 10; drive a CHAT call; assert *each* topic fires at least once |

---

## 4. Per-milestone live procedure

For each milestone, the SOP is:

1. **Boot recipe** (A / B / C / D).
2. **Mandatory probes** (which of §3.1–3.5).
3. **Live-only invariants** (things only observable post-boot).
4. **Map to tracing-plan issues** so coverage can be tracked.

### M1 — Concierge (live)

| Step | Probe type | Target | Tracing-plan refs |
|---|---|---|---|
| M1-L1 | PORT-IDENTITY | `concierge._input_port`, `_output_port`, `_state_port`, `_llm_port`, `_dispatch_port` are non-None and wired to the *per-session* bus, not the shared one | E1.10, M2 P1/P2 |
| M1-L2 | SUBSCRIPTION | FSM subscribes to exactly the topics in CONTRACT.md §4 | E1.3 |
| M1-L3 | MESSAGE-FLOW | LOW-tier flow (§3.3 reference) | E1.1, E1.3, E1.6 |
| M1-L4 | MESSAGE-FLOW | MED-tier dispatch flow | E1.4, E1.5 |
| M1-L5 | MESSAGE-FLOW | HIGH-tier dispatch — Planner SKETCH/EXPAND/VALIDATE → Orchestrator DAG → shared Fabric → `task.complete.v1` | I1.5.1 (N6) |
| M1-L6 | LIFECYCLE | `set_self_model()` after `start()` → guarded error, not data race | I1.10.2 |
| M1-L7 | NEGATIVE | EpisodicCompressor unwired — drive 16-turn conversation, assert history grows unbounded (confirms ISSUE-C02) | I1.1.5 |
| M1-L8 | MESSAGE-FLOW | HITL relay: pause → external resolve → `back_resume_handler` | E1.8 |
| M1-L9 | LIFECYCLE | crash-recovery priority order | I1.10.4 |

### M2 — Kernel + Bridge (live)

| Step | Probe type | Target | Tracing-plan refs |
|---|---|---|---|
| M2-L1 | LIFECYCLE | startup phase order S1→S7 captured via wrapper | E2.2, I2.1.3 |
| M2-L2 | PORT-IDENTITY | S6b cross-wire: `orchestrator._planner_port` is a real `PlannerAdapter` over the live planner mailbox, not `MockPlannerAdapter` | E2.3 |
| M2-L3 | PORT-IDENTITY | Per-session Fabric reader is real (`NullSessionStateReaderAdapter` is forbidden) | E2.4 |
| M2-L4 | NEGATIVE | `_FirstSessionSSMShim` — boot 2 sessions, drive distinct SS reads via ModelHub from each; assert results differ. Today: identical (confirms OPEN §1) | I2.5.1 |
| M2-L5 | NEGATIVE | Planner `state_port` with `"__shared__"` → always `None` | I2.5.2 |
| M2-L6 | LIFECYCLE | `destroy_session` reverses P6→P1; assert `_sessions[id]` gone, per-session Fabric `shutdown()` called (GAP today — assert fails) | I2.4.7, I2.4.11 |
| M2-L7 | NEGATIVE | `KernelConfig.max_sessions=2`, create 3rd → today succeeds; assert it should raise | I2.5.3 |
| M2-L8 | SUBSCRIPTION | `BridgeAwareLocalBus` refuses publish on reserved topic | I2.7.5 |
| M2-L9 | MESSAGE-FLOW | `SinkBridgeClient.submit_command` round-trip through `LocalOutbox` | I2.7.2, I2.7.4 |
| M2-L10 | PORT-IDENTITY | `bridge_client` identity across all sessions | I2.7.7 |

### M3 — Fabric + Model Hub (live)

| Step | Probe type | Target | Tracing-plan refs |
|---|---|---|---|
| M3-L1 | MESSAGE-FLOW | `execute()` STEP 1-9 emits both `k1.capability.invoked.v1` and `k1.capability.completed.v1` with matching `cognitive_trace_id` | I3.1.1 |
| M3-L2 | NEGATIVE | `safety_band` missing on request → defaults to GREEN (silent escalation; confirms gap) | M3 cross-cutting |
| M3-L3 | NEGATIVE | CB CLOSED→OPEN at threshold; OPEN→HALF_OPEN→CLOSED on probe | I3.2.6/.7 |
| M3-L4 | PORT-IDENTITY | Fabric never gets a *write* method call on `state_reader` (wrap with read-only proxy, assert no AttributeError on `read_section`, AttributeError on `write_section`) | E3.6 |
| M3-L5 | MESSAGE-FLOW | ModelHub 9-step on a CHAT request, assert all 10 bus topics fire | I3.7.1, ISSUE-M01 |
| M3-L6 | NEGATIVE | `from_config` injected ports stored but disconnected — drive once, capture 0 events on all 10 topics (confirms ISSUE-M01) | ISSUE-M01 |
| M3-L7 | MESSAGE-FLOW | Cache hit on identical CHAT, miss on TOOL_CALL | I3.7.2/.3 |
| M3-L8 | NEGATIVE | All providers' CBs OPEN → `NoEligibleProviderError`, not silent fallback | I3.7.5 |

### M4 — Orchestrator + Planner (live)

| Step | Probe type | Target | Tracing-plan refs |
|---|---|---|---|
| M4-L1 | PORT-IDENTITY | `_state_adapter` is **not** `MockStateReadAdapter` | I6.11.H5 |
| M4-L2 | MESSAGE-FLOW | end-to-end T3 plan: `plan.submit.v1` → step events → `plan.complete.v1` | E4.x |
| M4-L3 | NEGATIVE | `ConcurrencyGuard` depth limit: enqueue same plan N=1000; assert hard cap | GAP-O02 |
| M4-L4 | NEGATIVE | `PlanStep.to_dict()` round-trip preserves `safety_band_min` | I6.11.C1 |
| M4-L5 | NEGATIVE | `IEmbeddingPort` unwired → `fabric_search` returns error (not silent empty) | I6.11.C5 |
| M4-L6 | PORT-IDENTITY | Planner's `IFabricRetrievalPort` is the shared fabric, not None | E4.x |

### M5 — Bus + SessionState + MemoryWriter (live)

| Step | Probe type | Target | Tracing-plan refs |
|---|---|---|---|
| M5-L1 | SUBSCRIPTION | Concierge publish topic == MW subscribe topic | ISSUE-MW01 |
| M5-L2 | MESSAGE-FLOW | TTL: publish at t with ttl=100ms, consume at t+200ms → must be dropped | ISSUE-B01 |
| M5-L3 | LIFECYCLE | MW.stop() completes before SSM.stop() begins | I-5.11.4 |
| M5-L4 | MESSAGE-FLOW | `PlaceResolver` resolves a known place name to non-zero coords | ISSUE-MW04 |
| M5-L5 | PORT-IDENTITY | Per-session bus isolation: A's subscribers don't see B's envelopes | E5.x |
| M5-L6 | LIFECYCLE | SS write-flush on session destroy: every pending mutation lands in SQLite | E5.x |

### M6 — Cross-cutting (live)

| Step | Probe type | Target | Tracing-plan refs |
|---|---|---|---|
| M6-L1 | PORT-IDENTITY | All three readers (Orch/Planner/Fabric) point to a real per-session SSM | I6.11.C6 |
| M6-L2 | MESSAGE-FLOW | HIL approval gate end-to-end | E1.8, M6 HIL |
| M6-L3 | PORT-IDENTITY | SelfModel handle installed as step-0 on both Front and Back dispatchers | test_kernel_with_selfmodel.py I3 |
| M6-L4 | LIFECYCLE | SelfModel bundle `health()` returns `status=ok` on live kernel | I4 in selfmodel test |
| M6-L5 | NEGATIVE | Cancel a parent task → all child traces cancelled, no orphan envelopes | M6 supervision |

---

## 5. Acceptance gates

A milestone is **"live-verified"** when:

1. Every row in its §4 table has a green test in `tests/integration/k1/live/<milestone>/`.
2. Every **GAP** listed in [kernel_tracing_plan.md](kernel_tracing_plan.md) for that milestone has either:
   - a green negative-wire test that proves the GAP is real (test is `xfail` until fix), or
   - a green positive test that proves the GAP is closed.
3. The lifecycle probe leaves zero leaked `asyncio` tasks and zero open SQLite files.
4. All bus envelopes captured during the test serialize/deserialize round-trip (no schema drift).
5. No `unittest.mock.Mock`, `MagicMock`, or `AsyncMock` appears in the assertion subject — the only allowed mocks are at K0/LLM/MCP edges.

---

## 6. Required introspection hooks

Some probes need read-only APIs that **don't exist yet** on `KernelService` /
`LocalBus` / `CapabilityFabric`. These are part of the SOP — they ship before
live tests can be written.

| Hook | Owner | Used by | Notes |
|---|---|---|---|
| `svc.describe_wiring() -> WiringSnapshot` | KernelService | every PORT-IDENTITY probe | Returns dict: tier1 components, per-session adapter map, port→adapter chain, background task names |
| `bus.list_subscriptions() -> list[(topic, handler_qualname)]` | LocalBus | every SUBSCRIPTION probe | Read-only; must not expose handler internals |
| `svc.lifecycle_events() -> list[LifecycleEvent]` | KernelService | LIFECYCLE probes | Append-only log of `(phase, component, ts)` from start/stop |
| `fabric.describe_capabilities() -> list[CapDescriptor]` | CapabilityFabric | M3 probes | Includes provider class name, CB state, EMA latency |
| `model_hub.describe_routes() -> list[RouteDescriptor]` | ModelHub | M3 probes | Per-capability, current provider, CB state, cache size |
| `ssm.pending_writes() -> int` | SessionStateManager | M5 lifecycle | For flush-on-shutdown verification |

These are **observability**, not API surface — they live on a `Diagnostics` mixin
or a debug-only namespace (`svc.diagnostics.*`). No production code reads them.

---

## 7. Execution order (matches tracing plan)

Live procedures land in this order so each milestone's probes can rely on the
previous milestone being green:

1. **M2 first** — without a clean live kernel boot/shutdown nothing else is
   trustworthy. Land the introspection hooks (§6) here.
2. **M5** — bus + SSM are the substrate every other component publishes on.
3. **M3 (Fabric only, then ModelHub)** — capability path is the workhorse.
4. **M1** — Concierge end-to-end LOW and MED tiers.
5. **M4** — Orchestrator + Planner. T3 HIGH tier is a *gated* live test
   (expected red until I1.5.1 is fixed).
6. **M6** — HIL, SelfModel, scheduler/retention/supervision/learning.

Cross-cutting (lifecycle, leak, identity) is run **per milestone** as the
acceptance gate of §5.

---

## 8. Anti-patterns (do not do)

- **Do not** import `unittest.mock` in a live-wire test file. If you need to stub
  an LLM, use the existing `StubProviderPlugin` registered via
  `model_mode="test"`. If you need to stub MCP, use
  `inject_test_mcp_transport()` from
  [tests/k1/integration/concierge/conftest.py](tests/k1/integration/concierge/conftest.py).
- **Do not** assert on internal mock call counts (`mock.call_args_list`). Assert on
  envelopes captured from the **real bus**.
- **Do not** instantiate components directly (e.g. `ConciergeRuntime(...)`). Go
  through `KernelService.create_session()`. The point of these tests is the
  wiring — bypassing the composition root defeats the test.
- **Do not** sleep with magic constants. Use `BusCapture.wait_one(timeout)` and
  drive deterministically. If a flow is non-deterministic, that's a bug to file.
- **Do not** silence a probe with `try/except`. A failing probe is the signal.
- **Do not** mark a GAP test as `skip` — mark it `xfail(strict=True)` so the day
  the GAP is fixed the test goes red and forces the marker removal.

---

## 9. Reporting template

Each live-wiring suite emits a JSON report consumed by CI:

```json
{
  "milestone": "M2",
  "boot_recipe": "A",
  "probes": [
    {"id": "M2-L1", "type": "LIFECYCLE", "status": "pass", "duration_ms": 412},
    {"id": "M2-L4", "type": "NEGATIVE", "status": "xfail", "gap": "OPEN §1"}
  ],
  "leaks": {"asyncio_tasks": 0, "sqlite_handles": 0},
  "issues_covered": ["I2.1.3", "I2.3.1", "I2.4.7", "I2.5.1"],
  "gaps_confirmed": ["OPEN §1", "OPEN §2"],
  "gaps_closed": []
}
```

Aggregated weekly into `docs/test_results/live_wiring_<date>.md` so trend is
visible across the 344 issues in the tracing plan.

---

## 10. Open methodology questions

These are **not** code questions — they are SOP gaps to resolve before scaling:

1. **Determinism budget.** Live tests touch real `asyncio` schedulers, real
   SQLite, real semaphores. What's the acceptable flake rate? Proposed: 0% with
   retry budget 0; if a test flakes, the flake is a bug.
2. **Time control.** TTL and timeout probes need controllable time. Do we adopt
   `freezegun` (process-global, risky) or inject a `Clock` port? Proposed: inject
   a `Clock` port; it's also listed as a M2 missing-port today.
3. **Bus capture cardinality.** `BusCapture.wait_one` returns the first envelope.
   For ordering tests we need `wait_n(n, timeout)` — add to the helper.
4. **Cross-session leak detection.** How do we prove session B never observed an
   envelope intended for session A? Proposed: attach a `BusCapture` to session B
   for every topic published on session A; assert empty.
5. **Bridge live tests.** Recipe D requires Docker. Should `tests/integration/k1/live/`
   include recipe-D tests or stay hermetic and push them to
   `tests/integration/harness/`? Proposed: hermetic-only here; harness-rooted
   tests stay where they are.

---

## Appendix A — Mapping summary

| Live probe step | Tracing-plan issue count | GAP count covered |
|---|---:|---:|
| M1 live (9 steps) | 18 issues | 4 GAPs |
| M2 live (10 steps) | 22 issues | 5 GAPs |
| M3 live (8 steps) | 16 issues | 4 GAPs |
| M4 live (6 steps) | 12 issues | 5 GAPs |
| M5 live (6 steps) | 10 issues | 5 GAPs |
| M6 live (5 steps) | 9 issues | 3 GAPs |
| **Total** | **87** | **26** |

Remaining 257 issues from the tracing plan are non-wiring concerns (algorithmic
correctness, prompt content, model-specific behaviour) and stay in the unit/
behavioural test layer. The **wiring** layer is fully covered by ≤ 44 live
procedures.
