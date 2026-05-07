# Whiteboard: Bridge System — Contract-Mediated K0/K1 Boundary

Date: 2026-05-05
Status: whiteboard / design exploration
Related architecture:

- `architecture_diagrams/bridge/bridge_architecture.mmd`
- `architecture_diagrams/bridge/interkernel_fabric_layer.mmd`
- `architecture_diagrams/k0/k0_source_of_truth_v2.mmd`
- `architecture_diagrams/k0/p03_consolidation_architecture.mmd`
- `architecture_diagrams/k1/k1_cognitive_architecture_skeleton.mmd`

## Thesis

K1 and K0 are built by **separate teams**. Neither team should ever read or import the other team's code. The only thing they share is `bridge/` — and inside `bridge/`, the only thing both sides genuinely depend on is a **contract registry**: versioned, signed, machine-readable manifests that describe every cross-kernel envelope, topic, schema, delivery semantic, and SLA.

Today, the bridge is none of that. It's a single-process Python package, always-offline, with three colliding `IBridgePort` definitions and seven hand-rolled adapters in K1. K0 doesn't know `bridge/` exists. There is no registry. There is no codegen. There is no enforcement that K1 stops at the wall.

The work this whiteboard scopes is the path from "bridge as transport stub" → "bridge as contract-mediated boundary that two independent teams can build against without ever talking to each other's code".

The correct direction is:

```text
bridge/contracts/  →  codegen  →  generated K1 client  ─┐
                                  generated K0 handlers ─┴→  HTTP / SSE / Sync transport
```

Not:

```text
K1 imports k0.foo.bar  -- or --  K0 imports k1.baz.qux
```

## Why this matters

If FamilyOS ships with five team boundaries (K1, K0, IFL, Bridge infra, Tooling), the same envelope can mean five different things depending on whose head you're in. Without a contract registry:

- A K1 dev who wants P03 to consume a new feedback signal has to read K0's `BusDispatcher` to know the topic exists.
- A K0 dev who renames a field in `curiosity.intent.v1` discovers K1 broke only when CI runs against a merged k1+k0 image.
- The two teams negotiate every change in Slack instead of a PR with a diff a CI job can validate.

A contract registry collapses every "how does X reach Y?" question into one: **is there a contract for it?** If yes, both sides codegen against it and ship on independent cadences. If no, write one — and that PR is the negotiation.

## Verified current state (the ground truth)

Source-read on 2026-05-05.

### Bridge package shape

| Subpackage | State | What's there |
| --- | --- | --- |
| [bridge/core/](../../../bridge/core) | implemented | `BridgeConfig`, `EnvelopeBuilder`, `HmacSigning`, `Ed25519Signing`, `HttpTransport`, `K0HealthChecker`, `DegradedModeManager` |
| [bridge/ports/](../../../bridge/ports) | Protocol-only | 5 `Protocol` ABCs: `IKernelCommandPort`, `IKernelQueryPort`, `IKernelSSEPort`, `IKernelObsPort`, `IConnectorGatewayPort` |
| [bridge/kernel/](../../../bridge/kernel) | partial | `KernelCommandPort` real; `KernelQueryPort` / `KernelSSEPort` / `KernelObsPort` are scaffolds (transport wired, K0 endpoints absent) |
| [bridge/client.py](../../../bridge/client.py) | offline-only | `IBridgeClient` Protocol + `SinkBridgeClient` (queues to `LocalOutbox`, never contacts K0). **No `HttpBridgeClient` exists.** |
| [bridge/sync/](../../../bridge/sync) | partial | `LocalOutbox` (SQLite WAL queue) implemented. CRDT / E2EE / discovery / certs all commented-out imports. |
| [bridge/contracts/](../../../bridge/contracts) | partial | YAML protocol contract for command port + JSON Schema for `CommandEnvelope`. **Nothing for Query / SSE / Obs / Feedback.** |
| [bridge/adapters/](../../../bridge/adapters) | shell | `__init__.py` only |
| [bridge/codecs/](../../../bridge/codecs) | shell | `__init__.py` only. JSON-only via stdlib |
| [bridge/connector/](../../../bridge/connector) | shell | `__init__.py` only. Planned IFL gateway lives here |
| [bridge/testing/](../../../bridge/testing) | implemented | `StubBridgeClient` for tests |

### Wiring topology today

```text
K1 Kernel Boot (k1/kernel/service.py)
  └── S4: bridge_enabled?
         ├── True  → SinkBridgeAdapter   ── wraps ──► SinkBridgeClient + LocalOutbox
         └── False → OfflineBridgeAdapter (null object — get_client()=None)

  Distribution of self._bridge.get_client():
    S3  Shared Fabric        → BridgeConnectionAdapter
    P3  Per-session Fabric   → BridgeConnectionAdapter
    S5  Orchestrator         → BridgeClientShim → BridgeWriteAdapter (or MockBridgeAdapter when None)
    S6  Planner              → PlannerBridgeAdapter (reuses S3 adapter)
    P4  Concierge recall     → RecallMemoryAdapter(build_recall_fn(client))
    P5  MemoryWriter         → BridgeCommandAdapter ("the ONLY output path MW→K0")
```

**Key invariant today:** every `is_connected()` returns `False`. Both adapters are *always-offline*. K0 is unreachable from K1 by construction.

### K0 side (the receiver)

- K0 is a FastAPI / ASGI process (`k0/kernel/main.py` → `app.py`).
- Exposes 5 endpoints: `POST /k0/command.submit`, `GET /k0/query.recall`, `GET /k0/sse.subscribe`, `POST /k0/sse.ack`, `POST /k0/obs.emit`, plus `/healthz`, `/readyz`, `/metrics`.
- **K0 has zero Python imports from `bridge/` or `k1/`.** Everything K1 / Bridge is opaque to K0. Good — that's the wall we want to keep.
- K0 has its own `SchemaRegistry` (`k0/gate/schema_registry.py`) with `load`, `register`, `upsert`, `promote`, `block`, `active_versions`, `records_for_uri`, `get_audit_trail`. This is a parallel registry to the one bridge needs; in the merged design they will be *fed* by the same contracts, not maintained twice.
- K0 has `k0/automation/compute_contract_checksums.py` and `contract_compatibility_checker.py` — both already think in terms of contract checksums and breaking-change detection. We will lift these into shared tooling.

### K1 side — adapter sprawl

K1 has at least **7 adapter classes** wrapping the bridge surface:

| Component | Adapter | Lives in |
| --- | --- | --- |
| Kernel | `SinkBridgeAdapter`, `OfflineBridgeAdapter` | [k1/kernel/adapters/bridge_adapter.py](../../../k1/kernel/adapters/bridge_adapter.py) |
| Fabric | `BridgeConnectionAdapter` | [k1/fabric/adapters/bridge_connection.py](../../../k1/fabric/adapters/bridge_connection.py) |
| MemoryWriter | `BridgeCommandAdapter` | [k1/memory_writer/adapters/bridge_command_adapter.py](../../../k1/memory_writer/adapters/bridge_command_adapter.py) |
| Orchestrator | `BridgeClientShim`, `BridgeWriteAdapter`, `MockBridgeAdapter` | [k1/orchestrator/adapters/](../../../k1/orchestrator/adapters/) |
| Planner | `PlannerBridgeAdapter` | [k1/planner/adapters/bridge_adapter.py](../../../k1/planner/adapters/bridge_adapter.py) |
| Concierge | (closure built via `build_recall_fn`) | [k1/concierge/adapters/recall_memory.py](../../../k1/concierge/adapters/recall_memory.py) |

Plus three things named `IBridgePort`:

1. [bridge/ports/](../../../bridge/ports/) — five domain-specific port protocols.
2. [k1/kernel/ports/bridge_port.py](../../../k1/kernel/ports/bridge_port.py) — a *lifecycle* port (`connect / disconnect / is_connected / get_client`).
3. [k1/planner/**init**.py:72](../../../k1/planner/__init__.py) — a *third* `IBridgePort`, planner-local.

This is a documentation hazard.

### What `bridge/` cannot do today

- Cannot reach a real K0 (no `HttpBridgeClient`).
- Cannot stream SSE (`KernelSSEPort` reads `response.json()["events"]` — no chunked transfer, no cursor resume).
- Cannot run a health poll loop (`K0HealthChecker` is caller-driven; no internal task).
- Cannot execute IFL connectors (`SinkBridgeClient.execute_connector` raises `NotImplementedError`).
- Cannot enforce capability tokens (`bridge/security/` doesn't exist).
- Cannot do multi-device sync (CRDT / E2EE / mDNS all commented out).
- Cannot validate envelopes at runtime (JSON Schema is documentation-only).
- Cannot encode anything except canonical JSON via stdlib.

## Planned vision (per the MMDs)

### `bridge_architecture.mmd` — system-wide picture

Six concentric concerns, each its own subgraph cluster:

1. **Kernel Transport** — Query / Command / SSE / Obs / Feedback paths between K1 ↔ K0.
2. **Offline Awareness** — `K0HealthChecker`, `LocalOutbox`, ONLINE / DEGRADED / OFFLINE FSM, priority tiers (CRITICAL / HIGH / NORMAL / LOW).
3. **Connector Security** — `IConnectorGatewayPort`, `ToolRegistry`, `CredentialStore`, `RateLimiter`, `CircuitBreaker`, `IFLGateway`.
4. **IFL Runtime** — `IFLProtocolEngine`, `ManifestIngestion`, `AdapterRegistry`, `CompanyHostedDispatcher` (HTTPS) + `WASMSandboxDispatcher` (offline-capable), `EventIngress`.
5. **Device Sync** — mDNS discovery, CRDT LWW merge, AES256-GCM E2EE, X25519 key exchange, ED25519 device certs, P2P (NAT/STUN/TURN, WebRTC).
6. **Security Core** — `CapabilityToken`, `RequestSigner`, `BandEnforcer` (GREEN/AMBER/RED/BLACK), `AuditLogger`.

Plus codecs (JSON + FlatBuffer) and transport adapters (HTTP, gRPC, TCP).

The diagram enumerates 6 SSE topics K0→K1 (`memory.formed.v1`, `k0.learning.advisory.v1`, `k0.proactive.signal.v1`, `curiosity.intent.v1`, `k0.sync.complete.v1`, `cognitive.vector.stored.v1`) and 7 command topics K1→K0 (`memory.write`, `session.snapshot`, `beliefs.archive`, `history.archive`, `plan.committed`, `ifl.*`, `sync.delta`).

### `interkernel_fabric_layer.mmd` — the IFL layer

Five vertical layers:

- **L1 K1 Fabric** — auto-populated capability registry. `ManifestTranslator` ingests an IFL manifest (e.g. `com.chase.banking`) and registers tools like `tool.read.finance.chase.check_balance` automatically.
- **L2 Bridge ConnectorGateway** — `TokenVerifier → AdapterVerifier → RateLimiter → CircuitBreaker → RequestRouter`.
- **L3 IFL Runtime** — manifest system + protocol engine + adapter registry + dispatch (`CompanyHosted` HTTP/2 vs `WASMSandbox` for local/offline) + event ingress (Webhook / SSE / Poll).
- **L4 External services** — ~30 adapters across finance / home / health / transport / shopping / calendar / education / local sensors / family-sync.
- **L5 K0 storage** — `st_ifl_adapter_registry`, `st_ifl_credentials`, `st_ifl_manifests`, `st_ifl_events`, plus P02 (persist as episodic) and P07 (CRDT sync).

Defining IFL idea: **manifests signed by FamilyOS CA, capabilities auto-translate into Fabric tools, dispatch is hosting-mode aware, events flow inbound through `ifl.{category}.{adapter}.{event}`**.

### What the K1 + K0 + P03 MMDs add

The three kernel-side MMDs surface every cross-kernel envelope by name. We need this list because the *registry inventory* is exactly these topics — nothing more, nothing less.

K1 → K0 (commands & writes):

| Topic | Owner | Producer (K1) | Consumer (K0) |
| --- | --- | --- | --- |
| `memory.write.v1` | k0 | `MemoryWriterAgent`, `LearningExtractorAgent` | P02 Episodic Write |
| `memory.delta.v1` (with `gap_id`) | k0 | `GAP_ANSWER_WRITER` | P02 ingest |
| `feedback.signal.p02.v1` | k0 | K1 Advisory Emitter | P02 re-process |
| `feedback.signal.p08.v1` | k0 | K1 Advisory Emitter | P08 re-embed |
| `recall.request.v1` | k0 | `recall_memory()`, `recall_for_planning()` | P04 Attention Router |
| `committed.plan.v1` | k0 | Planner Stage 4 Commit | K0 WAL |
| `device.sync.envelope.v1` (E2EE) | k0 | Device adapter via Bridge | P07 Sync/CRDT |

K0 → K1 (SSE / events):

| Topic | Producer (K0) | Consumer (K1) |
| --- | --- | --- |
| `curiosity.intent.v1` | P06 Active Learning | `GAP_SSE_LISTENER` → `CuriosityAgent` |
| `k0.learning.advisory.v1` | K0 SSE Server | `DRIFT_DETECTOR` |
| `k0.proactive.signal.v1` | K0 SSE Server | `SSE_PROACTIVE_TRIGGER` → `ReminderAgent` |
| `p03.gap.detected.v1` | P03 R8 → M25 GapDetector | P06 (internal) → K1 SSE |
| `p03.complete.v1` | P03 R8 Bus Emission | K1 SSE subscribers |
| `p03.pattern.detected.v1` | P03 R8 Bus Emission | K1 SSE subscribers |
| `p03.truth.*.v1` | P03 R8 Bus Emission | K1 SSE subscribers |
| `p07.sync.notification.v1` | P07 `P07_NOTIFY_K1` | K1 SessionState sync |

K1 → K0 (observability / feedback):

| Topic | Producer (K1) | Consumer (K0) |
| --- | --- | --- |
| `feedback.envelope.v1` (`kind=feedback`) | `ADVISORY_EMITTER` → `CAPABILITY_LEARNING_BRIDGE` → `POST /k0/obs.emit` | P21 → `st_feedback_signals` |
| `observability.payload.v1` | K1 Telemetry | K0 Obs Port |

K0 ↔ K0 family fabric sync (Q8 layers L1 + L2 — **new in v1**, no ADR yet, see Q14):

| Topic | Layer | Owner | Producer | Consumer | Notes |
| --- | --- | --- | --- | --- | --- |
| `family.memory.delta.v1` | L1 | bridge | originating person-K0 | every other person-K0 in family whose `role` + `scope` match | signed by person-K0 Ed25519; carries `scope: private \| shared(person_ids) \| family` plus `child_visible` |
| `family.tool_state.delta.v1` | L2 | bridge | originating person-K0 (on behalf of an IFL adapter) | every other person-K0 whose tool ACL grants visibility | carries `(tool_id, record_id, op, payload)`; per-tool `sync.tool_class: shared_family \| shared_subset \| personal` from IFL manifest |
| `family.membership.v1` | L1+L2 | bridge | family root key (manual setup) | all person-K0s in family | signed enumeration `(person_id, k0_public_key, role)`; revocation entries supported |
| `tool_state.changed.v1` | L2 (intra-person SSE) | bridge | receiving person-K0 after applying L2 delta | that person’s K1 devices | not cross-family — purely K0→K1 fanout so the K1 tool UI re-renders |

Tool-state contracts cross-reference the IFL adapter manifests under `direction: device_*` (Q6, MS-5) — the IFL manifest declares the per-tool ACL, the bridge contract declares the on-the-wire envelope. Both are required for L2.

K1 ↔ K1 device mesh (ADR-0050 family — L3 SessionState mesh per Q8, **deferred post-v1**):

| Topic | Owner | Producer | Consumer | Source |
| --- | --- | --- | --- | --- |
| `k0bridge.p07.delta.v1` | bridge | Any K1 device with K0 (or future home K0) | All other K1 devices on LAN mesh | [0050c-lan](../../decisions-K1/06-layer5-infrastructure/0050-multi-device-family-sync-strategy/0050c-lan-first-sync-implementation.md) `K0BridgeP07Message` |
| `crdt.write_record.v1` | bridge | LWW merger on each device | LWW merger on each peer | [0050b](../../decisions-K1/06-layer5-infrastructure/0050-multi-device-family-sync-strategy/0050b-crdt-device-to-device-merge.md) `WriteRecord` FlatBuffer |
| `p2p.sync.message.v1` | bridge | `InternetSyncManager` (signed + encrypted) | Peer `InternetSyncManager` | [0050d](../../decisions-K1/06-layer5-infrastructure/0050-multi-device-family-sync-strategy/0050d-p2p-e2ee-internet-sync.md) `P2PSyncMessage` FlatBuffer |
| `device.handshake.v1` | bridge | Cert exchange initiator | Cert exchange responder | [0050d](../../decisions-K1/06-layer5-infrastructure/0050-multi-device-family-sync-strategy/0050d-p2p-e2ee-internet-sync.md) `DeviceCertificate` |
| `mdns.service.advertisement` (LAN-only, not a versioned topic) | bridge | Each K1 device | All listening K1 devices | [0050c-lan](../../decisions-K1/06-layer5-infrastructure/0050-multi-device-family-sync-strategy/0050c-lan-first-sync-implementation.md) `_familyos._tcp.local` |

L1/L2 topics live under a new registry value `direction: k0_to_k0` and tag `sync.layer: l1_family_memory | l2_family_tool_state`. L3 device-mesh topics live under `direction: k1_to_k1` with `sync.layer: l3_intra_person_devices`. v1 ships L1+L2 as `status: active`; L3 stays `status: deferred` until the post-v1 milestone that wires it on a per-person basis.

Inside-kernel topics that **must not** enter the bridge registry (they live in `k1/contracts/` or K0-internal config): `k1.concierge.user_input`, `k1.agent.{id}.delta.v1`, `k1.planner.delta.v1`, `k1.orchestration.delta.v1`, `k1.curiosity.delta.v1`, `k1.capability.invoked.v1`, `k1.capability.completed.v1`, `k1.fabric.learning.signal.v1`, `k1.hil.*.v1`, `k1.response.*.v1`, `k1.proactive.{question,message}.v1`, plus any `p0*` topic that never crosses to K1.

### The delta (planned − current)

| Concern | Current state | Gap |
| --- | --- | --- |
| Kernel transport | Command port real; Query/SSE/Obs scaffolds; no online client | `HttpBridgeClient` composing HttpTransport + 4 ports + SinkBridgeClient as offline fallback |
| Offline awareness | `LocalOutbox`, `K0HealthChecker`, `DegradedModeManager` exist as primitives | A daemon: 30s health poll, drain on OFFLINE→ONLINE, apply DEGRADED policy uniformly |
| Connector security | `bridge/connector/` empty | Gateway port impl, tool registry, credential vault, rate limiter, circuit breaker |
| IFL runtime | Empty + `execute_connector` raises | Manifest system, adapter registry, two dispatchers, event ingress, marketplace integration |
| Device sync | Commented imports only | mDNS, CRDT LWW, E2EE, X25519, ED25519, P2P/STUN/TURN |
| Security core | `bridge/security/` doesn't exist | Capability tokens, band enforcer, audit log |
| Codecs / adapters | Stdlib JSON only | msgpack / CBOR + per-topic codec selector + HTTP/2 / gRPC / WS adapters |
| Schemas | Only `command_envelope.json` | JSON Schemas for Query / Recall / SSE / Feedback envelopes |
| **Contract registry** | **Doesn't exist** | **Entire feature — see below** |
| K0 side | Only the 5 HTTP endpoints | K0 needs to actually handle `query.recall`, `sse.subscribe`, `obs.emit` |

This is a lot. We will not ship it as one milestone. The point is to figure out *which slices, in what order, with what minimum viable contracts*.

## Deployment topology — where K0 and K1 actually run

The team-isolation principle is the *organizational* split. The deployment topology is the *physical* split, and it changes the bridge's job in concrete ways.

### Today (v1 — what we ship first)

- **K1** runs on the **end-user device**: mobile app, laptop app, or an Alexa-class voice device. One K1 instance per (person × device). Resource-constrained: limited CPU, intermittent connectivity, may be backgrounded by the OS.
- **K0** runs as a **multi-tenant cloud-hosted instance** (one process per family / tenant, partitioned internally by `(tenant_id, user_id)` so all family members share one K0 process). Always-on, fat resources, durable storage, P03 consolidation runs here. See Q15e for why partitioned-multi-tenant beats one-container-per-person.
- **Bridge** is the *only* path from a K1 device to its K0 cloud instance. It crosses the public internet. It is therefore: (a) authenticated per device, (b) signed per envelope, (c) tolerant to flaky mobile networks.

```text
  ┌──────────┐   ┌──────────┐   ┌──────────┐
  │ K1 phone │   │ K1 laptop│   │ K1 Alexa │     ← user devices, may be anywhere
  └────┬─────┘   └────┬─────┘   └────┬─────┘
       │              │              │
       └──────┬───────┴──────┬───────┘
              │  bridge (HTTPS / SSE over public internet)
              ▼
         ┌─────────┐
         │ K0 cloud│   ← one per family account, hosted instance
         └─────────┘
```

Key implications for v1:

- The bridge is **always traversing WAN**. Latency budget for `recall.request.v1` round-trip is dominated by network, not K0 compute. SSE must survive cellular handoffs and tunnel through corporate proxies.
- K0 has a **public DNS endpoint** per family (`fam-<account_id>.k0.familyos.cloud` or similar). K1 discovers it from the user's logged-in account, not via mDNS.
- Multiple K1 devices on the same family hit the same K0. K0 is the **only synchronization point** — there is no LAN sync in v1; two phones on the same WiFi still round-trip through cloud.
- Offline outbox is **load-bearing**, not nice-to-have: a phone in airplane mode for 2 hours must queue user actions and replay when WiFi returns.
- Per-device device certificates (`sig_kid`) are the auth principal. Cloud K0 trusts the bridge envelope signature.

### Tomorrow (v2 — the home-server pivot)

Product intent: ship a **K0 home server** — an Alexa-class device that lives on the home network, holds the family's K0 instance locally, and exposes the same bridge surface. Cloud K0 either retires or becomes a backup/relay.

```text
                          ┌──────────────┐
  ┌──────────┐            │ K1 phone     │ ← can be at school/office (WAN)
  │ K1 phone │            │ (away mode)  │   or at home (LAN)
  └────┬─────┘            └──────┬───────┘
       │ LAN                     │ WAN
       ▼                         ▼
  ┌────────────────────┐    ┌──────────────────┐
  │ K0 HOME SERVER     │◄───│ K0 CLOUD RELAY   │   ← may be optional, for NAT punch /
  │ (Alexa-class box,  │    │ (presence + hole-│     remote-access fallback
  │  on home WiFi,     │    │  punch + offline │
  │  always-on,        │    │  cache)          │
  │  inference + memory)    └──────────────────┘
  └────────────────────┘
```

Key implications for v2:

- K1 has **two possible K0 endpoints** at any moment: the home server (preferred — LAN, low latency, data residency) and the cloud relay (fallback — when away from home, when home server offline).
- Endpoint **discovery** becomes a real problem: mDNS for LAN, account-bound DNS for cloud, with a *preference policy* ("prefer LAN if reachable, else WAN").
- The home server *is* a K0 — same FastAPI surface, same 5 endpoints, same `bridge/contracts/` registry. The bridge code is unchanged; only the transport target changes.
- If both home K0 and cloud K0 exist concurrently, **one must be authoritative for writes**. Strong default: home K0 is the truth, cloud K0 is a read-replica + outbox-relay for away-mode K1s. (See Q13.)
- LAN P2P (mDNS + WebRTC) is no longer a deferred nice-to-have; it's the *normal* in-home path. Sync (Q8) gets reframed as "LAN-direct K0 access", not "K1↔K1 sync".

### What this fixes in the bridge contract model

The team-isolation principle and the deployment topology are independent dimensions, and the contract registry is the seam where they meet:

- A contract manifest already declares `delivery.transport`, `delivery.online_required`, `sla.latency_p99_ms`. These fields are interpreted *per topology*: the same `recall.request.v1` contract has a tight latency on LAN-home-server and a relaxed one on cloud.
- We add one new manifest field, `delivery.endpoint_class: cloud_k0 | home_k0 | either`, so a contract can declare "this only makes sense against the home server" (e.g. `device.sync.envelope.v1`) versus "this is fine against either" (e.g. `memory.write.v1`).
- The registry's `BridgeRuntime` boot-validation now also checks: *for every contract this kernel consumes, at least one of the configured endpoints satisfies its `endpoint_class`*. A K1 phone configured with cloud-only endpoints fails fast if it's wired to a contract that requires `home_k0`.

## Open questions we must answer first

Each is genuinely open. Strawmen follow each.

### Q1. Where does the bridge runtime *live*?

Deployment topology answers most of this:

- On the **K1 device** (phone / laptop / Alexa-class), bridge is in-process — there's nowhere else for it to go on a mobile OS, and adding a sidecar costs battery for nothing.
- On the **cloud K0** instance, bridge is in-process inside the K0 service — K0 is a single FastAPI process, the generated K0 handlers are imported alongside the pipelines.
- On the **home K0 server** (v2), same as cloud K0 — in-process inside the K0 service. The home server is just "K0 deployed on a different SKU".

**Strawman: in-process on both sides, both for v1 and v2.** No sidecar, no daemon. The reason for a sidecar (language-agnostic isolation) doesn't apply because both sides are Python and both teams accept the contract registry as the wall. Revisit only if a future K0-on-edge target ships in a non-Python runtime.

### Q2. Is the bridge symmetric?

Today asymmetric (K1 is a client of K0). The MMDs imply symmetry (SSE pushes K0→K1, sync moves both ways, IFL events arrive at K0 *and* K1).

**Strawman: symmetric, but each contract is unidirectional with a declared owner.** Two `BridgeRuntime` instances — one per kernel — both built from the same `bridge/contracts/` registry. The runtimes are symmetric in API; the asymmetry is in *which contracts each kernel registers as producer vs consumer*. This is the resolution that makes the team-isolation principle real: K0 doesn't import bridge today, but K0's *generated* handlers do, and K0 owns its half of the registry walk.

### Q3. Single client or many?

Today: `IBridgeClient` is one fat Protocol composing 5 ports. Components inject the whole client even when they only need command (MW) or only need query (Concierge).

**Strawman: five port surfaces in generated code, one registry artifact.** Code shape is determined by codegen, not by hand. K1's MW depends only on `IKernelCommandPort` (generated), not on `IBridgeClient`. The current K1 adapter sprawl is partly *because* the fat client wasn't sliced earlier.

### Q4. Where does the offline state machine live?

Three candidates: (a) inside `SinkBridgeClient` (today); (b) inside a top-level `BridgeRuntime` that owns transport + health + outbox + clients; (c) as a decorator `OnlineFirst[Port](http=…, fallback=…, health=…)`.

**Strawman: (c), driven by manifest field.** `OnlineFirst` decorator wraps each generated port. Per-contract override via `manifest.delivery.online_required: true|false` — manifests *declare* whether they tolerate offline queueing.

### Q5. Codec strategy — when do we move off JSON?

JSON works today, debugging is trivial, schemas exist. Binary codecs matter if K1↔K0 becomes same-device IPC (CPU) or constrained network (bandwidth).

**Strawman: defer until Q1 settles, then per-contract.** `manifest.delivery.codec: json|msgpack|cbor|fbs` is the knob. Codegen reads it. For HTTP-in-process today, JSON-only.

### Q6. IFL — first-class member or v2.0 problem?

The IFL layer is huge (manifest CA, marketplace, OAuth, WASM sandbox, 30+ adapters). The MMDs treat IFL as foundational; the codebase treats it as deferred.

**Strawman: defer to MS-5.** Bridge ships MS-3 (online K0 + SSE + offline outbox drain) without IFL. `execute_connector` keeps raising. IFL contracts live in the same registry under `direction: device_*` so we don't paint ourselves into a corner.

### Q7. Security — minimal vs full from day one?

Minimal v1: envelope signing (HMAC dev / Ed25519 prod, already done), `band` field stamped on envelope, K0-side policy gate honors it. Full vision: capability tokens with scope+expiry, band enforcer in bridge *before* sending to K0, audit log of every operation, signature verification of K0 *responses*.

**Strawman: stay at minimal-v1 until IFL-with-third-party-adapters lands** (which is when capability tokens *actually* matter).

### Q8. Sync — what does “sync” actually mean here?

Sync is the **product**, not the plumbing. FamilyOS is a *family fabric*: when Father has a conversation about his wife, the resulting memories show up in Mother’s K0 too; when Mother adds a 2:30pm meeting on her K1 calendar tool, it appears on the family calendar everywhere; when Father starts a session on his phone and continues on his laptop, his SessionState follows him. If those three things don’t happen, this is just N parallel CRUD apps glued together with a shared login.

The correct unit of decomposition is **one K0 per person**, not one K0 per device. A person owns 1..N K1 devices (phone, laptop, watch); all of those devices talk to *that person’s* K0. The lateral channel between persons’ K0s inside the same family is what the bridge has to ship.

```text
[Father's K1 devices] ──► [Father's K0]  ◄──sync──►  [Mother's K0]  ◄── [Mother's K1 devices]
                            ▲                          ▲
                            └───────sync─────► [Kid's K0] ◄───────┘
                                                       ▲
                                            [Kid's K1 devices]
```

#### Three sync layers

There are exactly three things that need to sync. They have different owners, different timing, different conflict models. Mixing them up is what made ADR-0050 confusing.

| Layer | What syncs | Across what | Conflict unit | v1 status | v2+ status |
| --- | --- | --- | --- | --- | --- |
| **L1. Family memory sync** | scoped memory items (`memory_item` records with `scope` field) | person-K0 ↔ person-K0 inside one family | `person_id` | **Ship in v1.** This is the product. | LAN-direct between home-K0 partitions; E2EE on WAN |
| **L2. Family tool-state sync** | shared-tool state deltas (calendar events, shopping list items, shared notes, family budget entries) | person-K0 ↔ person-K0 via the same channel as L1 | `tool_id + record_id` | **Ship in v1** — piggybacks on L1 transport, different schema. | Same channel as L1; richer scope (per-tool ACL) |
| **L3. SessionState sync** | 6-section SessionState ([ADR-0017](../../decisions-K1/06-layer5-infrastructure/0050-multi-device-family-sync-strategy/0050a-sessionstate-coherence-guarantees.md)) | one person’s K1 devices among themselves (phone ↔ laptop) | `device_id` within one `person_id` | **Defer.** Single-device K1 is the v1 reality; round-trip K0 if needed. | LAN mesh per [ADR-0050c-lan](../../decisions-K1/06-layer5-infrastructure/0050-multi-device-family-sync-strategy/0050c-lan-first-sync-implementation.md), code already exists |

Things that get called “sync” but aren’t any of the three:

- K1→K0 writes and K0→K1 events are the *bridge’s normal job* (Q1–Q7), not sync. They’re intra-person request/response.
- Cloud-K0 ⇋ home-K0 for the *same person* is operational replication (deployment topology Q13), not sync. The two K0s are two hosts of one logical store.

#### L1 — Family memory sync (the product, v1)

**Promise:** memory items written on Father’s K0 with scope `shared(father, mother)` or `family` appear in Mother’s K0 (and Kid’s K0 if scope permits) without either user round-tripping the other person’s account.

**Wire model:**

- Each memory item carries a `scope` field. Default `private` (fail-closed). Other values: `shared(person_ids: [..])`, `family`, with an orthogonal `child_visible: bool`.
- Originating K0 emits a signed `family.memory.delta.v1` envelope on the L1 sync channel. Receiving K0s validate signature → family membership → scope inclusion → apply locally.
- Conflict resolution: LWW with alphabetical `person_id` tiebreaker; vector clocks for causal chains. Lifted intact from [ADR-0050b](../../decisions-K1/06-layer5-infrastructure/0050-multi-device-family-sync-strategy/0050b-crdt-device-to-device-merge.md), only the unit is swapped from `device_id` to `person_id`.
- Loser of a conflict is **logged**, not silently dropped. Family-scope memories are too sensitive to lose without trace.

**Identity model:** family root Ed25519 keypair generated at family setup; each person-K0 has its own Ed25519 identity key signed by the family root; signed `family_membership.v1` manifest enumerates `(person_id, k0_public_key, role: parent|child|guardian)`. Both sides validate before accepting any delta. (See Q15 for the unsolved sub-questions: redaction, child asymmetry, where the root key lives, leaving/divorce.)

**Transport in v1:** in-process channel between `(tenant_id, user_id)` partitions of one multi-tenant K0 instance — see Q15e. Same envelope shape, same signing, same validation as the v2 cross-host case. The bridge `OnlineFirst` decorator delivers `family.memory.delta.v1` over an internal bus instead of HTTPS, but no contract changes.

**Where person-K0s actually live in v1:** *not* one container per person. One **multi-tenant K0 process per family**, internally partitioned by `(tenant_id=family, user_id=person)`. The L1 sync code treats every cross-partition delta as if it crossed a network — same envelope, same signing, same scope-validation — so the v2 cross-host transport is a drop-in. See Q15e.

#### L2 — Family tool-state sync (the calendar use case, v1)

**Promise:** if Mother adds a `2:30pm meeting tomorrow` on her K1 calendar tool, the event shows up on Father’s K1 calendar tool view (and Kid’s if appropriate) without either of them looking at the other’s account. Same for shared shopping lists, family budget entries, shared notes, household to-dos, recurring grocery orders.

**Why it’s a separate layer from L1:** L1 carries *memory items* (facts, episodes, beliefs — things the cognitive layer reasons over). L2 carries *tool state* (mutable structured records owned by an IFL adapter — things the user directly manipulates through a tool UI). They have different schemas, different owners, different update frequencies, and L2 needs *per-tool* ACLs (the family calendar is shared; Mother’s personal calendar is not).

**Why it shares L1’s transport:** the underlying problem is the same — “this record changed on person A’s K0; propagate to persons B, C’s K0s subject to scope.” Reusing L1’s signed-delta channel, family-membership identity, CRDT merge, and audit log is free and avoids two parallel sync stacks.

**Wire model (delta from L1):**

- New envelope `family.tool_state.delta.v1` carrying `(tool_id, record_id, op: upsert|delete, payload, scope)`.
- `scope` here is *per-tool*, not per-record by default: each tool registers its sharing policy at install time (`family_calendar` defaults to `family`; `personal_calendar` defaults to `private`). Per-record overrides allowed.
- Conflict resolution: per-record LWW + person-id tiebreaker, same as L1. Tools that need stronger semantics (e.g. “don’t double-book” on the calendar) handle it at the tool layer, not the sync layer.
- The IFL adapter for the tool (registered under `direction: device_*` per Q6) is the producer of these deltas; its install-time manifest declares `sync.tool_class: shared_family | shared_subset | personal`.

**End-to-end calendar flow in v1:**

1. Mother’s K1 calendar UI → K1 calendar agent → IFL `family_calendar` adapter → writes `(event_id, 2:30pm meeting)` to Mother’s K0 via the existing bridge command port.
2. Mother’s K0 sees the IFL adapter is `tool_class: shared_family`; emits `family.tool_state.delta.v1` on the L1 sync channel to Father’s K0 and Kid’s K0.
3. Father’s K0 validates signature + membership + tool ACL → applies the upsert to its local `st_ifl_tool_state` for `family_calendar` → emits `tool_state.changed.v1` SSE to Father’s K1 devices.
4. Father’s K1 calendar UI re-renders. Same for Kid if scope allows.

**Why this is in v1, not deferred:** the family calendar is the canonical “why did I pay for this thing” feature. Without L2, FamilyOS is single-user. Building L2 on L1’s transport is small — the marginal work is the envelope schema, the per-tool ACL declaration in IFL manifests, and the K0 plumbing to dispatch deltas to the right tool subscriber.

#### L3 — K1↔K1 SessionState sync (deferred)

**Promise:** Father starts a chat session on his phone, walks home, picks up his laptop — the session continues without re-priming context.

**Why deferred to post-v1:**

- Most users in v1 use one K1 device at a time. Multi-device-per-person is a power-user feature.
- The cheap workaround works: each K1 device round-trips the person’s K0 to fetch latest SessionState on session resume. ~250ms one-time cost when switching devices, vs. building a full mesh.
- The real LAN mesh code already exists in [ADR-0050c-lan](../../decisions-K1/06-layer5-infrastructure/0050-multi-device-family-sync-strategy/0050c-lan-first-sync-implementation.md) (mDNS + TCP port 9000 + 5s loop, COMPLETED). When v2 turns it on, scope it to *intra-person device coherence* — not the cross-person mesh ADR-0050 originally envisioned.

**Wire model (when activated):** lift verbatim from ADR-0050a/b/c-lan/d. The unit stays `device_id`, but all peers in a single mesh instance must belong to the same `person_id`. Discovery is `_familyos-{person_id}._tcp.local` (one mesh per person, not one mesh per family).

**Per-device coherence prerequisite ([ADR-0050a](../../decisions-K1/06-layer5-infrastructure/0050-multi-device-family-sync-strategy/0050a-sessionstate-coherence-guarantees.md))** stays valid: Read-Your-Writes ≤5ms, Bounded Staleness ≤250ms, Crash Recovery ≤2s. These are per-device guarantees and don’t depend on whether L3 is on.

#### What the bridge actually has to build

| Layer | Bridge work for v1 | Bridge work for v2+ |
| --- | --- | --- |
| L1 family memory | Sync channel between cloud K0 instances; `family.memory.delta.v1` envelope; family-membership manifest; LWW+person-id merge; signed delta validation. | LAN-direct when both person-K0s on home box; E2EE per ADR-0050d crypto. |
| L2 family tool-state | `family.tool_state.delta.v1` envelope; per-tool ACL declaration in IFL manifest; K0→K1 SSE dispatcher for `tool_state.changed.v1`. | Per-record scope overrides; richer conflict policies (e.g. calendar non-overlap) at tool layer. |
| L3 SessionState | Nothing. K1 fetches on resume via existing recall port. | Wire ADR-0050c-lan code into `BridgeRuntime` at the per-person mesh level. |

#### What’s reusable from ADR-0050 and what isn’t

The ADR-0050 family chose **device** as the sync unit. That’s correct for L3 and wrong for L1/L2. The math, transports, and crypto are reusable; the unit and the mDNS service name aren’t.

**Reusable verbatim:** LWW + tiebreaker (swap `device_id` for `person_id` at L1/L2), vector clocks, FlatBuffers wire shape, `P2PSyncMessage` envelope, Ed25519/X25519/ChaCha20-Poly1305 crypto choices, ADR-0050a SessionState coherence guarantees.

**Wrong-level / discard:** mDNS-by-device for cross-family discovery (use mDNS-by-person-K0 instead); the “all devices converge to identical state” guarantee (false at L1 — each person’s K0 holds a *different projection*, scope-filtered); the “zero cloud intermediary” absolute (v1 ships cloud-hosted person-K0s; revisit at v2).

**Missing from ADR-0050 entirely:** scope tagging on memory items; family identity / root-key model; redaction-on-write; child privacy asymmetry; per-tool ACL for L2. These are the actual open design surface (Q15).

#### Open contradictions inside the ADR-0050 family

Still flag-worthy regardless of which layer the work lands in:

- 0050d frontmatter REJECTED vs body Accepted — status ambiguous.
- 0050 says AES256-GCM for Phase 2; 0050d says ChaCha20-Poly1305. Both list Ed25519 for signing.
- Two files numbered `0050c`; `0050c-multi-device-family-sync-strategy.md` is a duplicate of `0050.md` with mislabeled parent.
- 5s LAN loop vs 30s WAN loop — no decision on the LAN→WAN transition window.
- Vector-clock optionality declared but no rule for which data classes require them.

L1 and L2 have **no ADR yet**. They need one before MS-3a. See Q14 for the action item and Q15 for the unsolved sub-questions.

### Q9. How do teams declare and discover contracts?

This is the load-bearing question for the team-isolation principle. Without an answer, "two teams, one wall" is a wish.

**Strawman: PR-driven manifest workflow.** When K1 needs K0 to do something new, the K1 dev opens a PR that adds `bridge/contracts/manifests/<topic>.v1.yaml` + `bridge/contracts/schemas/<…>.json` — **no K0 code touched**. CI does:

- Schema lint (JSON Schema valid; no `additionalProperties: true` without a justification field).
- Manifest lint (all required fields; `owner_team` declared; semver follows policy).
- Cross-team review gate: PR auto-requests review from `@k1-team` and `@k0-team` CODEOWNERS for `bridge/contracts/`.
- Codegen runs and commits `_generated/` updates.

K0 team merges when their pipeline can handle the new topic. Until then the manifest is `status: proposed` and not loaded into K0's runtime. K1 can ship behind a feature flag that checks `registry.contract_status('memory.write.v2') == 'active'`. When K0 ships, it flips to `active`. Both kernels deploy on independent cadences.

At runtime, each kernel calls `BridgeRuntime.from_registry(path='bridge/contracts/')` at boot. The runtime parses every manifest, registers a publish path for contracts where it is producer, registers a consume path for contracts where it is consumer, and **fails boot loudly** if a registered contract has no implementation. Direct mitigation for the silent always-offline state we have today.

### Q10. Who arbitrates a breaking change?

| Change kind | Policy | Who approves |
| --- | --- | --- |
| **Additive within `vN`** (new optional field, new enum value with default) | Bump `manifest.checksums.schema_sha256` only. Both kernels keep working. | Owner team CODEOWNERS |
| **Breaking** (rename, remove, type change, new required field) | **Forbidden in-place.** Must publish `<topic>.v(N+1)` as a new manifest. Old `.vN` enters `status: deprecated` with `deprecation.dual_publish_until` (default 30d). Producer publishes both during the window. | **Both** teams' CODEOWNERS |
| **Topic deletion** | Only after `dual_publish_until` elapses **and** zero traffic on the old topic (proven by 7d of `bridge.topic.<name>.deliveries == 0`). | Owner team + release manager |

Lift K0's existing `compute_contract_checksums.py` and `contract_compatibility_checker.py` into a top-level `tooling/contracts/` so neither team owns them — they're shared infra governed by `@bridge-infra` CODEOWNERS.

### Q11. What stops K0 team from sneaking a `from k1 import …`?

The principle is only real if it can't be violated by accident. CI gates:

| Check | Implementation | Fails when |
| --- | --- | --- |
| `no-cross-kernel-imports` | grep `^from k0\.` and `^import k0` inside `k1/**/*.py` (and the inverse). Allowlist: `k1/scripts/migrations/**` only with annotation. | Any K1 file imports `k0`, or vice versa |
| `bridge-not-imported-from-kernels-except-via-generated` | `k1/**/*.py` may import only `bridge.client`, `bridge._generated.k1.*`, `bridge.contracts` (read-only), `bridge.testing`. Mirror rule for K0. | A kernel reaches into `bridge.core.*`, `bridge.kernel.*` bypassing the generated surface |
| `manifest-implementation-bound` | `BridgeRuntime.from_registry().validate()` runs in CI as well as boot | A contract is registered but no implementation exists locally |
| `schema-checksum-stable` | Recompute manifest checksums; fail if drift between PR and stamped value | Hand-edit of `_generated/` or undeclared schema change |
| `bus-yaml-aligned-with-registry` | Walk [`k1/config/bus.yaml`](../../../k1/config/bus.yaml) and K0 pipeline subscriptions; assert every declared bus topic exists in the registry | A bus topic is consumed locally but the cross-kernel half is missing |

### Q12. How does K1 discover its K0 endpoint(s)?

In v1 it's trivial — one cloud DNS name from the logged-in account. In v2 it's the central UX problem: a K1 phone walking from home to office must seamlessly switch from `home-k0.local` (LAN, mDNS) to `fam-<acct>.k0.familyos.cloud` (WAN) without the user noticing.

**Strawman: `EndpointResolver` inside `BridgeRuntime`.** Configured with an *ordered* endpoint list per role. Probes in order, returns the first that passes `K0HealthChecker` within a budget (e.g. 200ms). Re-probes on network change events (WiFi join/leave, cellular handoff). Per-contract override via `delivery.endpoint_class`:

```text
endpoints:                       # per K1 device config
  - kind: home_k0
    discovery: mdns
    service: _familyos-k0._tcp.local
    require_tls: true
    cert_pinning: family_root_ca
  - kind: cloud_k0
    discovery: dns
    host: fam-abc123.k0.familyos.cloud
    require_tls: true
```

v1 ships with only the cloud entry. v2 prepends the home_k0 entry. No code change in K1 or K0 — this is config + the resolver. The bridge contract registry doesn't change; only `delivery.endpoint_class` is a new manifest field.

### Q13. Cloud K0 and home K0 — one truth or two?

The moment a family owns both a cloud K0 (from v1) and a home K0 (from v2), there are two stores of memory. Which is authoritative?

Three options:

- **(a) Home is truth, cloud is replica.** All writes commit to home K0; cloud is a read-replica fed by home via outbound sync. K1-when-away talks to cloud (read-only fast path; writes queue and forward to home when reachable). Pro: data residency story is clean ("your memories live in your house"). Con: home server downtime breaks writes; cloud relay must be smart about queueing.
- **(b) Cloud is truth, home is cache.** All writes go to cloud (same as v1). Home K0 caches recent state for low-latency LAN reads. Pro: no migration from v1; cloud already does P03. Con: defeats the home-server value prop ("why did I buy this box if my data still lives in the cloud?").
- **(c) Multi-master with CRDT.** Both K0s accept writes; reconcile via P07-style CRDT. Pro: no single point of failure. Con: massive engineering project; conflict semantics on memory consolidation are unsolved.

**Strawman: (a) for v2.** Home K0 is the truth. Cloud K0 becomes a *cloud relay* with two jobs: (1) read-replica for K1-when-away, (2) outbox/queue for writes from K1-when-away that can't reach home directly. Write-conflict resolution is sequential (writes from any K1 enter a single ordered log at home K0); the cloud relay never accepts writes that bypass home. This pushes a lot of complexity into the relay's outbox-and-replay logic, but keeps memory authority unambiguous.

v1 is unaffected: there is no home K0 yet, cloud K0 is the only K0, no ambiguity.

### Q14. ADR action item — supersede ADR-0050’s device-level framing

ADR-0050 (Oct 2025, ACCEPTED, Phase 1 COMPLETED) is correct mechanically and wrong-level architecturally: it chose `device` as the sync unit. Q8 recasts sync as three layers with `person_id` as the unit at L1 and L2, and `device_id` at L3. The ADR family must be updated before MS-3a so future contributors aren’t blindsided.

**Action:** open a new ADR family `0090-family-fabric-sync` (or supersede chain on 0050) covering L1 (`0090a-family-memory-sync`), L2 (`0090b-family-tool-state-sync`), and the L3 re-scope (`0090c-intra-person-device-mesh` — narrows ADR-0050c-lan to intra-person scope). Lift the CRDT math, transports, and crypto from ADR-0050b/c-lan/d intact; only the unit and the mDNS service name change. ADR-0050a (SessionState per-device coherence) stays as-is — it remains a per-device prerequisite for L3.

The bridge contract registry doesn’t need to wait for the new ADRs to merge — it captures the layer in a `sync.layer: l1_family_memory | l2_family_tool_state | l3_intra_person_devices` manifest field, and the existing CI gates (Q11) ensure no contract drifts past the wall while the ADR work is in flight.

### Q15. Person-K0 sync — scope, identity, redaction (the actual unsolved problems)

If plane 1 is the product, these are the questions plane 1 needs answered before code can ship. None have an ADR yet.

**Q15a. Memory scope schema.** What scope values exist on a memory item, and what does each mean operationally?

- Strawman: `private` (originating person only) | `shared(person_ids: [..])` (replicate to listed person-K0s) | `family` (replicate to all family member K0s) | `child_visible: bool` (gate against kid K0s independent of scope).
- Default scope: `private` (fail-closed). Promoting to `shared` or `family` is an explicit user action.
- Where stored: a `scope` field on the memory record, also carried in the FlatBuffers `WriteRecord` so receiving K0s can validate.

**Q15b. Family identity and membership.** How does Father’s K0 know Mother’s K0 belongs to the same family?

- Strawman: a **family root identity** (Ed25519 keypair) generated at family creation. Each person-K0 has its own Ed25519 identity key, signed by the family root key. A signed `family_membership.v1` manifest enumerates `(person_id, k0_public_key, role: parent|child|guardian|other)`. Both K0s validate manifest before accepting any sync delta.
- Adding a member: existing parent device runs an enrollment flow that signs the new person’s key with the family root key. Until enrolled, no sync.
- Removing a member (leaving / divorce): family root issues a revocation entry; all K0s stop accepting deltas signed by the revoked key. Open question: does the revoked person’s K0 retain previously-shared memories or tombstone them? Strawman: retain (data already known); future writes don’t propagate.
- Where the family root key lives: open question. Options: (i) split between parents (M-of-N), (ii) on the home box once it ships, (iii) in a recovery seed printed at family setup.

**Q15c. Redaction on the wire.** A conversation transcript may contain both `private` and `shared(father, mother)` content interleaved. Does the writer split the memory into separate scoped records at write time, or does the sync layer redact?

- Strawman: **writer-side scope decomposition.** The K0 ingest pipeline that produces memory items from a conversation tags each extracted fact with its own scope; the sync layer never sees mixed-scope records. Simpler model, cryptographically auditable (signed at the granular level).
- Counter-argument: harder for the extractor to get scope right at write time; may need a post-hoc scope-correction flow.

**Q15d. Child privacy asymmetry.** Parent→kid memories are not symmetric to kid→parent. Parents may need visibility into kid’s memories (safety); kid may not see parent private memories. The mesh is a directed graph with role-aware policy, not a symmetric peer group.

- Strawman: scope rules are evaluated against the receiving person’s `role` from the family manifest. `family` scope with `child_visible: false` excludes child K0s. A separate `parent_oversight: bool` policy on kid K0s allows enumerated parent K0s to read kid memories under audit-logged conditions.

**Q15e. Where do person-K0s physically run in v1?** **Decided: one multi-tenant K0 process per family, partitioned by `(tenant_id, user_id)`.** Not one container per person.

Why this is the right answer:

- **Financial:** N family members → 1 container, not N. A family of five doesn’t cost 5× to host.
- **Operational:** one K0 process to deploy, monitor, scale, back up per family. Simpler runbooks.
- **Isolation:** `(tenant_id, user_id)` is enforced at every K0 access path (storage layer, query layer, write layer). Cross-tenant leakage becomes a code bug, not a deployment misconfiguration. With container-per-person, isolation depends on networking + auth being correct *and* no wildcard query slipping through. The partitioned model is strictly stronger.
- **v2 compatibility:** the home-K0 box runs the **same** multi-tenant K0 code; it just hosts one tenant. The cloud relay (Q13) hosts many tenants. Same partition model everywhere.

What this means for L1/L2 sync:

- A delta from Father’s partition to Mother’s partition is, in v1, an **in-process** event — same K0 process, different `(tenant_id, user_id)` row partitions. The L1/L2 code must not optimize for this case (no `if same_process: skip_signing()`). Reasons: (i) same code path runs cross-host in v2; (ii) signing + scope-check is the cryptographic enforcement of family membership — skipping it lets a K0 storage bug leak Mom’s private memories to Dad’s partition; (iii) the audit log must show every cross-partition delta identically, regardless of transport.
- Performance bonus that comes for free: in-process L2 tool-state propagation runs sub-millisecond. Mom’s calendar event lands on Dad’s K0 partition essentially instantly; the dominant latency in the end-to-end calendar flow is the K0→K1 SSE leg, not the K0→K0 step.
- The `OnlineFirst[Port]` decorator (Q4) selects the transport per-contract: `family.memory.delta.v1` runs over an internal bus when both partitions are co-located, over HTTPS when they aren’t (v2 home-K0 + cloud relay). Bridge code is the same; only the transport adapter swaps.

v2 deployment lifts a tenant out of the cloud K0 process and into a home-K0 box. Same code, same partition model, different transport for cross-host deltas.

**Q15f. Conflict resolution at plane 1.** When Father’s K0 and Mother’s K0 both edit the *same* shared memory record concurrently, who wins?

- Strawman: LWW + alphabetical `person_id` tiebreaker (lift from ADR-0050b, swap unit). Vector clocks for causal chains. Same merge code, same correctness properties.
- Caveat: “wins” here means “which edit shows up” — the loser’s edit is logged in an audit trail, not silently dropped. Family-scope memories are sensitive enough that lost writes need to be visible to the user.

**Q15g. Bootstrap order.** Person-K0 must exist *before* their K1 devices can write to it. Family manifest must exist *before* K0↔K0 sync can run. What’s the onboarding flow?

- Strawman: family-creator runs setup → family root key + their own person-K0 created → invite link generated → invitee joins (key signed by family root) → their person-K0 provisioned → K1 devices enrolled to their owner’s K0.

**Q15h. Tool-state sync ACL granularity (L2-specific).** Per Q8 L2, IFL adapters declare a `sync.tool_class` at install time. What values exist and who can change them?

- Strawman: three classes — `shared_family` (every family member’s K0 sees this tool’s state, e.g. family calendar, shopping list, family budget), `shared_subset(person_ids)` (a named subset, e.g. couple-only finances, parent-only kid monitoring), `personal` (originating person only — never crosses L2 channel; degenerates to L1 plumbing).
- Per-record overrides: a `family_calendar` event can be tagged `private` to keep one event off the family view (Mom’s therapy appointment); a `personal_calendar` event can be promoted to `shared_subset(father, mother)` for a couple-private dinner.
- Who decides the default class: the IFL adapter author at install time. Family administrator can override before first use.
- What about adapters not designed for sharing (e.g. a personal banking adapter)? Default `personal`; never auto-promote.
- Open question: how does L2 handle *deletes* and *late writes* on shared tools? Strawman: same LWW + person-id tiebreaker as L1; deletes are tombstones with TTL.

None of these sub-questions are resolved. They are the actual design surface for v1 sync.

## The contract registry — concrete shape

Proposed layout (this is the strawman the two teams negotiate):

```text
bridge/
  contracts/
    index.yaml                  # master taxonomy: every topic name in the system
    schemas/                    # JSON Schema (or FlatBuffers .fbs) per envelope
      command/
        memory.write.v1.json
        memory.delta.v1.json
        feedback.signal.p02.v1.json
        feedback.signal.p08.v1.json
      query/
        recall.request.v1.json
        recall.response.v1.json
      sse/
        curiosity.intent.v1.json
        k0.proactive.signal.v1.json
        k0.learning.advisory.v1.json
        p03.gap.detected.v1.json
        p03.complete.v1.json
        p03.pattern.detected.v1.json
        p03.truth.updated.v1.json
      obs/
        feedback.envelope.v1.json
        observability.payload.v1.json
    manifests/                  # one per contract — the team-readable doc
      memory.write.v1.yaml
      curiosity.intent.v1.yaml
      ...
  _generated/                   # codegen output — vendored, not hand-edited
    k1/
      ports.py                  # generated Python Protocols K1 imports
      models.py                 # generated Pydantic / dataclasses
      client.py                 # generated typed client
    k0/
      handlers.py               # generated handler stubs K0 fills in
      models.py
```

Each `manifests/<topic>.yaml` is the single source of truth a human reads:

```yaml
topic: curiosity.intent.v1
direction: k0_to_k1            # or k1_to_k0, or device_to_k0
owner_team: k0                 # who can change/version this
producer:
  kernel: k0
  pipeline: P06_active_learning
  emitter: GapDetector
consumer:
  kernel: k1
  service: ProactiveAgentSpawner
  state: GAP_SSE_LISTENER
schema: schemas/sse/curiosity.intent.v1.json
delivery:
  transport: sse
  ordering: best_effort
  ack_required: true
  retry: exponential_backoff
  max_redelivery: 5
  codec: json
  online_required: false
semantics:
  idempotent: true
  duplicate_strategy: dedupe_by_envelope_id
  retention: 24h_replay_window
sla:
  latency_p99_ms: 500
  availability: degrades_to_local_queue
versioning:
  strategy: additive_only_within_v1
  breaking_change_requires: new_topic_v2_with_dual_publish_window_30d
status: active                 # proposed | active | deprecated
checksums:                     # filled by CI
  schema_sha256: ...
  manifest_sha256: ...
```

This **is** the contract. Both teams can read this without reading any code.

## Strawman runtime — the picture both teams sign off on

```text
                      ┌──────────────────────────────────────────────┐
                      │            bridge/contracts/                 │
                      │      (the only thing both teams own)         │
                      │                                              │
                      │   index.yaml • manifests/*.yaml • schemas/   │
                      │            ↑   shared infra   ↑              │
                      │   tooling/contracts/ (checksums, codegen,    │
                      │       compatibility checker, lint)           │
                      └──────────────────┬───────────────────────────┘
                                         │ codegen
                       ┌─────────────────┴──────────────────┐
                       ▼                                    ▼
        bridge/_generated/k1/                  bridge/_generated/k0/
          ports.py  models.py  client.py         handlers.py  models.py
                       │                                    │
                       │ imported by                        │ imported by
                       ▼                                    ▼
        ┌──────────────────────────┐         ┌──────────────────────────┐
        │       K1 KERNEL          │         │       K0 KERNEL          │
        │   (k1/* — owned by K1)   │         │   (k0/* — owned by K0)   │
        │                          │         │                          │
        │  BridgeRuntime(role=K1)  │         │  BridgeRuntime(role=K0)  │
        │   ├ publish(topic, env)  │         │   ├ publish(topic, env)  │
        │   └ consume(topic, hdlr) │         │   └ consume(topic, hdlr) │
        │                          │         │                          │
        │  uses: bridge.client     │         │  uses: bridge.kernel.*   │
        │        bridge._generated │         │        bridge._generated │
        │        bridge.testing    │         │        bridge.testing    │
        └──────────┬───────────────┘         └─────────────┬────────────┘
                   │                                       │
                   │     transport (HTTP / SSE / E2EE)     │
                   └───────────────────────────────────────┘
                              bridge/core/transport/
                              bridge/sync/ (CRDT, outbox)
                              bridge/connector/ (IFL device adapters)
```

Sketch of the K1-side runtime construction:

```text
bridge/runtime.py  (NEW)
  class BridgeRuntime:
      transport: HttpTransport
      health:    K0HealthChecker          # owns 30s poll task
      outbox:    LocalOutbox
      command:   IKernelCommandPort       # OnlineFirst(http_cmd, sink_cmd, health)
      query:     IKernelQueryPort         # OnlineFirst(http_qry, sink_qry, health)
      sse:       IKernelSSEPort           # http_sse only — offline = no SSE
      obs:       IKernelObsPort           # OnlineFirst(http_obs, sink_obs, health)
      gateway:   IConnectorGatewayPort    # NotImpl in v1, MS-5 IFL adds it

      @classmethod
      def from_registry(cls, path: str, role: Role) -> "BridgeRuntime":
          ...  # parse manifests, wire generated ports, validate impl-bound

      async def start(): transport.open(); health.start_polling(); outbox.start_drain_worker()
      async def stop():  health.stop(); outbox.stop(); transport.close()
```

### Naming cleanup that falls out

- Bridge's lifecycle wrapper in K1 → rename `IBridgePort` → `IBridgeRuntime`.
- Planner's local `IBridgePort` → rename `IPlannerWritePort`.
- Bridge's domain ports keep their current names but become *generated*; hand-defined versions deleted.

### Adapter consolidation

The 7 hand-written K1 adapters today (kernel, fabric, MW, orchestrator x3, planner, concierge closure) collapse into thin glue calling the generated client. MW's `BridgeCommandAdapter` can be deleted; MW depends on `IKernelCommandPort` directly. Target: adapter LOC drops to <100 across all 7 sites.

## Milestones

The contract registry **must come first**. Without it, every later slice creates drift we then have to retrofit.

| MS | Scope | Verifiable end state |
| --- | --- | --- |
| **MS-2.5** Registry & codegen scaffold | Stand up `bridge/contracts/`, codegen scripts, CI gates from Q11. Migrate the *one* live contract (`command.submit`) into the new format. | One contract round-trips through generated K1 client → HTTP → generated K0 handler stub. CI gate `no-cross-kernel-imports` is green. |
| **MS-3a** Online command path | Replace `SinkBridgeClient` with generated `HttpBridgeClient` for `memory.write.v1`. | One real `memory.write` lands in K0 SQLite via HTTP. |
| **MS-3b** Outbox + DEGRADED for commands | `BridgeRuntime` + `OnlineFirst[Command]` + outbox drain on transition. Per-contract `online_required` honored. | Toggle K0 off → MW commands queue. Toggle K0 on → outbox drains within 60s. Chaos test: 60s K0 down, queueable contracts replay, `online_required` ones surface clear errors. |
| **MS-3c** Query port | Add `recall.request.v1` + `recall.response.v1` manifests. Real `KernelQueryPort` over real K0 endpoint. | `recall("yesterday's groceries")` returns real K0 hits, not `RecallBundle.empty()`. |
| **MS-3d** SSE port | Add 5 K0→K1 SSE manifests (curiosity, advisory, proactive, p03.gap, p03.complete). Real streaming client (httpx-sse), cursor resume, backpressure. | K1 `GAP_SSE_LISTENER` receives a P06-emitted `curiosity.intent.v1` end-to-end within 200ms p99. |
| **MS-3e** Obs / feedback port | `feedback.envelope.v1` + `observability.payload.v1`. P21 writes `st_feedback_signals`. | E2E feedback loop closes; K0 receives `feedback.signal.p02.v1` and validates. |
| **MS-4** Codecs + adapter consolidation | msgpack/CBOR codec selection per manifest. Hand-written K1 adapters deleted in favor of generated. | Adapter LOC drops to <100 across all 7 sites. |
| **MS-5** Connector / IFL minimum | `bridge/connector/` device adapters, signed contracts under `direction: device_*`. `IConnectorGatewayPort` impl + manifest schema + one company adapter (Hue or GCal) + one WASM adapter (MQTT). | First IFL device round-trips a state read via Fabric → Bridge → IFL → external. |
| **MS-6** LAN device sync | mDNS + LWW CRDT. | Two devices on the same WiFi share session state without K0. |

Order is not negotiable: MS-2.5 → MS-3a–e → MS-4 → MS-5 → MS-6. IFL (MS-5) cannot ship without the online command + SSE paths.

## What we explicitly do *not* do in v1

- No msgpack / FlatBuffer / CBOR until MS-4. Stay JSON.
- No P2P / WebRTC / STUN / TURN. LAN-only sync (MS-6) and only on shared WiFi.
- No capability tokens beyond the existing `sig_kid` device identity.
- No marketplace UI, no signing CA. IFL adapters in MS-5 are pre-installed by trusted developers.
- No rewriting K0's existing in-runtime `SchemaRegistry`. It stays where it is and is *fed* by the bridge registry at K0 boot.
- Not deciding the codegen tool yet (datamodel-code-generator vs quicktype vs hand-rolled). Decide before MS-2.5 implementation.

## Risks

- **R1.** `bridge/` claims to be the "only authorized path", but today it's an offline stub. Anyone reading the code without context will assume things flow when they don't. Surface `bridge.k0_reachable=false` in `/healthz`. MS-2.5's boot-fail-on-unbound-contract is the deeper fix.
- **R2.** Two `IBridgePort` definitions and 7 K1 adapters mean any bridge contract change touches ~10 files. Refactor cost grows. MS-4 cleanup is essential, not optional.
- **R3.** SSE done wrong (the current `response.json()["events"]` shortcut) silently breaks under any K0 streaming load. MS-3d must use real chunked streaming.
- **R4.** The MMDs assume IFL is foundational; the codebase treats it as MS-6+. If product timelines push "connect to Hue" into MS-3, we're not architecturally ready.
- **R5.** `LocalOutbox` has no TTL — a long-offline device builds an unbounded staleness backlog. Add `manifest.delivery.max_queue_age` and prune. Especially load-bearing now that the v1 deployment is *always* WAN — flaky mobile networks make the outbox the normal write path, not the exception.
- **R6.** **Contract drift = silent data corruption.** Two teams can both ship "passing" CI yet disagree on field meaning that schema can't capture (timezone, units). Mitigation: every manifest must include a `semantics` block; PR template forces the author to fill it.
- **R7.** **Codegen becomes the new sprawl.** If `_generated/` is checked in, diffs are huge; if not, every dev runs codegen locally. Mitigation: vendor `_generated/` *and* run codegen in CI with a "no diff" check. Audited noise.
- **R8.** **Registry becomes a coordination bottleneck.** If every K1 feature needs K0 review, velocity drops. Mitigation: `manifest.status: experimental` lets K1 self-merge experimental contracts that are flagged off in K0; only `status: active` requires both teams' approval.
- **R9.** **Codegen tool ownership.** Whoever owns codegen owns both teams' tempo. Mitigation: lives in `tooling/contracts/`, governed by `@bridge-infra`, both team leads required approvers.
- **R10.** **Topics that "feel internal but cross by accident."** A K1 dev publishes `k1.fabric.learning.signal.v1` to the local bus, then someone wires it through a bridge proxy — registry never saw it. Mitigation: K1 bus dispatcher refuses to forward any topic prefix that resembles a cross-kernel name (`k0.*`, `p0[1-9].*`, `memory.*`, `feedback.*`, `recall.*`, `curiosity.*`) unless the topic is in the registry.
- **R11.** **Cellular-network reality.** v1 deployment is K1-on-mobile → cloud K0 over public internet. SSE drops on cellular handoff are normal, not exceptional. Mitigation: real chunked SSE with cursor resume in MS-3d (the current `response.json()["events"]` shortcut will not survive a single subway ride). HTTP keepalive + retry policy declared per contract.
- **R12.** **Split-brain when home K0 ships.** v2 introduces home K0 + cloud K0 simultaneously. Naive K1 endpoint resolver could write to whichever it reaches first, creating two divergent histories. Mitigation: Q13 strawman (a) — home K0 is *the* truth; cloud K0 only accepts writes when explicitly acting as relay. Resolver enforces a single-writer endpoint per session; failover requires explicit handoff with epoch fencing.
- **R13.** **ADR-0050 conflict.** ADR-0050 is ACCEPTED and Phase 1 is COMPLETED, but its core premise (every device runs K0) contradicts the v1 cloud-K0 deployment. Bridge code may be silently inheriting assumptions from that ADR (e.g. `LocalOutbox` semantics, FlatBuffers schemas, P07 channel naming) that no longer hold. Mitigation: Q14 must be resolved before MS-3a; the chosen option must be reflected in updated ADR(s) so future contributors aren’t blindsided.
- **R14.** **Two FlatBuffers wire formats already exist for sync** (`WriteRecord` in 0050b, `P2PSyncMessage` in 0050d) before the bridge contract registry exists. If the registry doesn’t inventory them on day one, codegen will produce a third overlapping format. Mitigation: MS-2.5 explicitly imports the two ADR-0050 FlatBuffers schemas as the canonical source, even if they remain unused at runtime in v1.

## Non-goals (this whiteboard)

- Re-debating K0 vs K1 boundaries. Settled.
- Re-debating Fabric vs Bridge ownership of capability invocation. Fabric owns intent + selection; Bridge owns transport + auth.
- Backporting bridge to K0 (K0 stays a passive HTTP receiver in v1; its half of the contract registry is enforced via codegen, not by importing `bridge/`).
- The exact YAML schema for `manifests/*.yaml`. The example above is suggestive; the field set will iterate.
- Where to physically host `bridge/contracts/` if K0 and K1 ever live in separate repos (submodule? separate `bridge-contracts` repo? handle when it happens).

## Deferred

The MS-2.5 substrate decisions (manifest schema, codegen tool, vendoring) and the five “resolved deferred items” below were previously listed here. They have moved into their own sections immediately above and below this one.

What actually remains deferred:

- IFL adapter **key rotation operationalisation** (rollout cadence, revocation list distribution — the trust model itself is decided in “Resolved deferred items” below).
- The exact JSON Schema for the manifest YAML itself (sketched in “MS-2.5 substrate” above; full schema document lives in `bridge/contracts/_meta/manifest.schema.json` once MS-2.5 ships).
- Per-record scope override grammar at L2 (Q15h open-question tail — deletes / late writes / TTL on tombstones).

## Resolved deferred items — the five blockers cleared

Five items have been deferred since the first pass. Each was waiting on something else (deployment topology, sync layering, codegen choice). Those are now decided; the five resolutions below unblock MS-3 milestones.

### 1. `HttpBridgeClient` interface signature — per-port composition

The client is a **namespace bag of generated ports**, not a flat method surface.

```python
@dataclass(frozen=True)
class HttpBridgeClient:
    command: IKernelCommandPort   # OnlineFirst[Command](http=..., fallback=outbox, health=...)
    query:   IKernelQueryPort     # OnlineFirst[Query]   (no fallback — online_required)
    sse:     IKernelSSEPort       # http_sse only
    obs:     IKernelObsPort       # OnlineFirst[Obs]     (fallback=outbox)
    gateway: IConnectorGatewayPort  # NotImplemented in v1, MS-5 wires it
```

Callers depend on **the port they need**, never on `HttpBridgeClient`:

```python
# in MemoryWriter
def __init__(self, command: IKernelCommandPort): ...

# in Concierge
def __init__(self, query: IKernelQueryPort): ...
```

Why this shape over a flat `client.submit_command(...)`:

- It matches Q3 (“five port surfaces in generated code, one registry artifact”). The flat alternative would re-fatten the very thing the generated split exists to slice.
- Each port is a generated `Protocol`; the client is a stupid container, not a behavioural object. Tests inject `StubBridgeClient(command=FakeCommand(), query=FakeQuery())` without a god-object.
- Method discoverability is the codegen’s job (`IKernelCommandPort` lists every command topic K1 produces). The client doesn’t need to mirror that.

Construction always goes through `BridgeRuntime.from_registry()`. Direct `HttpBridgeClient(...)` instantiation is forbidden by lint (`bridge-client-construction-via-runtime-only`) so the registry stays the single configuration entry point.

### 2. Outbox drain trigger — event-driven primary, periodic safety net

**Both, with a clear primary.** The triggers are not redundant; they cover different failure modes.

```text
 primary:    K0HealthChecker emits ONLINE_TRANSITION  ->  drain worker awakes within ~50ms
 safety net: every 60s tick                            ->  drain worker awakes
 startup:    BridgeRuntime.start()                     ->  one immediate drain pass
```

Why not event-only: the health checker is itself code; if it deadlocks, hangs, or its callback chain breaks, the outbox would silently grow forever. The 60s sweep guarantees forward progress even when the event path is broken.

Why not periodic-only: 60s p99 latency for a queued write replay is unacceptable for a user who just unlocked their phone after a tunnel ride. Event-driven gets us back to ~50ms.

The drain worker invariants:

- **Bounded batches.** Max 100 envelopes per batch, 5s wall-clock cap per batch. Yields to the asyncio loop between batches so health checks and SSE keepalives are not starved.
- **Per-contract pacing.** New manifest field `delivery.drain_rate_per_sec: int | null` (default `null` = no cap). Used for high-volume contracts (`observability.payload.v1`) to avoid replay storms after a long outage.
- **Concurrent writes are safe.** New envelopes go to the outbox tail (SQLite WAL); drain reads from the head. No lock held across network I/O.
- **Failure handling.** A 5xx from K0 leaves the envelope in the outbox; per-contract `delivery.max_queue_age` (R5) bounds staleness. A 4xx (contract violation) moves the envelope to a `dead_letter` table for human review — never silently dropped.
- **Visibility.** Drain emits `bridge.outbox.drained{topic, batch_size, latency_ms}` and `bridge.outbox.depth{topic}` so the slice between health-up and outbox-empty is observable.

### 3. DEGRADED-mode matrix per port — auto-derived from manifests

No hand-maintained matrix. The runtime computes per-`(port, topic)` behaviour from two manifest fields:

```text
delivery.online_required: bool        # if true, DEGRADED = raise OfflineError
delivery.max_queue_age:   duration    # if online_required=false, queue up to this age
```

The resulting matrix is a *consequence*, not a config:

| Port | Typical `online_required` | DEGRADED behaviour |
| --- | --- | --- |
| Command (e.g. `memory.write.v1`) | `false` | Queue to outbox; return success; surface `bridge.degraded.command.<topic>` metric. |
| Command (e.g. `committed.plan.v1`) | `true` | Raise `OfflineError` immediately; planner handles by deferring the commit step. |
| Query (e.g. `recall.request.v1`) | `true` | Raise `OfflineError`; concierge falls back to local cached `RecallBundle` per its own policy. |
| SSE (all K0→K1) | n/a (subscriber-side) | Mark stream `CLOSED`; reconnect with last-seen cursor on `ONLINE_TRANSITION`. |
| Obs (`feedback.envelope.v1`, `observability.payload.v1`) | `false` | Queue with `max_queue_age=24h`; drop with `bridge.obs.dropped.expired` metric on TTL. |
| Gateway (IFL, MS-5) | `true` | Raise `OfflineError`; IFL invocations have no meaningful offline semantic. |

**Rule:** DEGRADED is per-`(port, topic)`, never a global toggle. The runtime exposes `bridge.degraded_topics()` returning the live set of topics currently in DEGRADED so `/healthz` can render it. CI gate `degraded-mode-derived-only` greps for any hand-coded `if degraded:` branch outside `bridge/core/degraded.py` — the policy lives in one place.

The matrix is regenerated by `BridgeRuntime.from_registry()` at boot from the manifest set. New contract → new matrix row, automatically.

### 4. IFL adapter signing CA — trust model now, issuance later

**Decide the trust model in MS-2.5 so manifests can stamp it. Defer issuance infrastructure to MS-5.**

Trust model (commits now):

- Every IFL adapter manifest (under `direction: device_*`) carries `signing.ca_id: <string>` and `signing.signature: <bytes>`.
- Bridge ships an embedded **CA bundle** at `bridge/contracts/_meta/ca_bundle.json` with one or more `(ca_id, ed25519_public_key, status: active|deprecated, valid_until)` entries.
- v1 ships **exactly one** active CA: `familyos_root_v1`. Pre-installed adapters in MS-5 are signed by FamilyOS’s offline root key. No third-party CAs in v1 — marketplace and external developers are post-MS-6.
- Manifest validation at `BridgeRuntime.from_registry()`: every adapter manifest’s signature verifies against the bundled `ca_id`’s public key, or boot fails. Same enforcement model as the manifest meta-schema check.

Key-rotation operational story (sketch — full operationalisation deferred to MS-5):

- Rotation = ship a bridge release containing the new key as `status: active` and the old key as `status: deprecated` with a `valid_until` timestamp 90d in the future.
- During the rotation window, manifests signed by either key validate. After `valid_until`, the deprecated key is removed in the next release.
- Revocation = ship a release that downgrades a key to `status: revoked` with `valid_until: <past>`. Revoked keys fail validation immediately.
- A revocation list (CRL) distribution channel — anything more dynamic than “ship a bridge release” — is explicitly post-MS-6 (it requires a marketplace and a key server).

Why not OAuth / X.509 / sigstore now: each adds a server dependency and an operational burden disproportionate to v1’s threat model (one author, pre-installed adapters, no marketplace). The bundled-bundle approach is the same pattern apt/dpkg / Mac App Store updates use — simple, auditable, sufficient until 3rd-party adapters ship.

### 5. `IBridgePort` migration — three definitions, three fates, sequenced moves

Three things called `IBridgePort` today (Q current state, “Adapter sprawl”):

| # | Location | What it actually is | Fate |
| --- | --- | --- | --- |
| (a) | [bridge/ports/](../../../bridge/ports/) (5 domain protocols) | The real bridge port surface | **Keep the names; replace bodies with codegen output.** Hand-written file deleted in MS-2.5. |
| (b) | [k1/kernel/ports/bridge_port.py](../../../k1/kernel/ports/bridge_port.py) | A lifecycle wrapper (`connect / disconnect / is_connected / get_client`) | **Rename to `IBridgeRuntime`.** It was never a port; it’s the runtime API. |
| (c) | [`k1/planner/__init__.py`:72](../../../k1/planner/__init__.py) | A planner-local write surface | **Rename to `IPlannerWritePort`.** Never had anything to do with the bridge. |

Migration sequence (no big-bang; each step has a CI gate so we can’t backslide):

1. **MS-2.5, PR#1 — pure rename.** Rename (b) → `IBridgeRuntime` and (c) → `IPlannerWritePort`. Update all import sites. No behaviour change. New CI gate `single-ibridge-port-definition`: `grep -r "class IBridgePort\b" k0 k1` must return zero hits. (Hits in `bridge/ports/` are allowed; hits anywhere else fail CI.)
2. **MS-2.5, PR#2 — manifest substrate.** Stand up `bridge/contracts/_meta/manifest.schema.json`, codegen scripts, and the CI gates from Q11. The `_generated/` tree is empty for now.
3. **MS-2.5, PR#3 — first generated port.** Migrate the live `command.submit` contract into the new manifest format. Codegen produces `bridge/_generated/k1/ports/command_v1.py` and `bridge/_generated/k0/handlers/command_v1.py`. The hand-written `bridge/ports/command.py` is **deleted**; `bridge/ports/__init__.py` re-exports the generated `IKernelCommandPort` so existing import paths still resolve.
4. **MS-3a → MS-3e — one port per milestone.** Each MS-3 sub-milestone migrates exactly one hand-written port (Query, SSE, Obs, Feedback) the same way: add manifest → codegen → delete hand-written file → update K1 adapters → ship.
5. **MS-4 — adapter consolidation.** With all 5 ports generated, the 7 K1 adapters collapse into thin glue (target <100 LOC total per the existing milestone). MW’s `BridgeCommandAdapter` is deleted; MW depends on the generated `IKernelCommandPort` directly. New CI gate `adapter-loc-budget`: `wc -l k1/**/adapters/bridge_*.py` must stay under the budget.

The migration touches imports across both kernels but never crosses the wall — K0’s generated handlers are the K0 team’s job, K1’s generated clients are the K1 team’s job, and the manifest is the only file both teams co-author.

## Open decisions inventory — what still needs to be closed before development

A single rolled-up list of every decision still flagged “strawman”, “open question”, or “tail item” in the document above. Grouped by **when** they must be closed, not by where they appear in the doc.

## MS-2.5 closure pack — D1–D6 resolved against the actual codebase

Subagent code-walk (2026-05-05) confirmed: the existing primitives are richer than the whiteboard sketches assumed, but no CI infrastructure exists yet (no `.github/workflows/`, no `.pre-commit-config.yaml`, no ruff config, no mypy config, no `import-linter`). The six MS-2.5 blockers are closed below with concrete artifacts that reuse what's already there.

### Inputs from the code-walk (the facts these decisions assume)

- **Existing crypto.** `bridge/core/signing.py` ships `Ed25519Signing(signing_key_bytes, key_id)` (pynacl, base64url, no padding) and `HmacSigning(secret, key_id)` (dev/test). Keys are caller-supplied; **no key loader exists**. K0 verifies envelopes via per-device verify keys held in `ProvisioningLedger.DeviceKey` (PostgreSQL), **not** via a CA bundle. There are no `*.pem` / `keys/` files anywhere; `.gitignore` excludes `*.pem`.
- **Existing envelope.** `bridge/core/envelope_builder.py` builds the full 18-field wire envelope (cognitive_trace_id, tenant_id, space_id, actor, device_id, topic, band, ts, policy_version, schema_uri, schema_version, body, payload_sha256, idem_key, envelope_sha256, sig, sig_alg, sig_kid). Schema URI auto-derives as `schema://k0/topics/{topic.replace(".", "_")}.body.json`.
- **Existing K0 contract tooling.** `k0/automation/compute_contract_checksums.py` already does SHA-256 of every artifact under `k0/contracts/` and writes a `VERSION` registry. `k0/automation/contract_compatibility_checker.py` does SemVer + breaking-change detection (BREAKING / COMPATIBLE / PATCH classification per ADR-0013). Both are CLI-runnable. **These are the seed of `tooling/contracts/`.**
- **Existing K0 schemas.** `k0/contracts/jsonschema/topics/memory_write.body.json` already exists and `$ref`s `k1://contracts/schemas/memory_writer/memory_atom.v2.schema.json` (MemoryAtom v2.2, 14 required fields). Topic in production today is `"memory.write"`, **not** `"memory.write.v1"` — the manifest must reconcile.
- **Existing bus topics.** `k1/config/bus.yaml` declares timing rules by topic-prefix; longest-prefix match. Every prefix that resembles a cross-kernel name (`k0.*`, `memory.*`, `feedback.*`, `recall.*`, `curiosity.*`, `p0[1-9].*`) needs a registry counterpart for the `bus-yaml-aligned-with-registry` gate.
- **Existing IBridgePort definitions.** Three live `class IBridgePort` definitions: [`k1/kernel/ports/bridge_port.py`](../../../k1/kernel/ports/bridge_port.py) (lifecycle), [`k1/fabric/ports/bridge_port.py`](../../../k1/fabric/ports/bridge_port.py) (K0 access via Fabric), [`k1/planner/ports/bridge_port.py`](../../../k1/planner/ports/bridge_port.py) (recall + persist). Whiteboard's earlier reference to `k1/planner/__init__.py:72` was an outdated re-export site — the third class is in `planner/ports/bridge_port.py`. The migration plan (Resolved Deferred item 5) is updated implicitly by the table below.
- **Existing wall violations.** Two production files import non-public bridge subpackages: [`k1/memory_writer/adapters/bridge_command_adapter.py`](../../../k1/memory_writer/adapters/bridge_command_adapter.py) imports `bridge.core.envelope_builder`, and [`k1/kernel/adapters/bridge_adapter.py`](../../../k1/kernel/adapters/bridge_adapter.py) imports `bridge.sync.local_outbox`. The `bridge-not-imported-from-kernels-except-via-generated` gate must be **introduced with these two as known violations on day one**, then fixed in MS-3a / MS-3b.
- **Cross-kernel imports.** `^from k0\.` / `^from k1\.` returns **zero hits in production `.py` files** today (only `.md` docs). The wall already holds; the gate institutionalises it.

### D1 — Manifest meta-schema document

**Decision:** ship `bridge/contracts/_meta/manifest.schema.json` as the JSON Schema 2020-12 document below. It is the *only* allowed shape; codegen and CI both validate every manifest against it.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "bridge://contracts/_meta/manifest.schema.json",
  "title": "Bridge Contract Manifest",
  "type": "object",
  "required": [
    "topic", "direction", "owner_team", "producer", "consumer",
    "schema", "delivery", "semantics", "sla", "versioning", "status"
  ],
  "additionalProperties": false,
  "properties": {
    "topic":      { "type": "string", "pattern": "^[a-z][a-z0-9_]*(\\.[a-z0-9_]+)+\\.v[0-9]+$" },
    "direction":  { "enum": ["k0_to_k1", "k1_to_k0", "k0_to_k0", "k1_to_k1", "device_to_k0", "k0_to_device"] },
    "owner_team": { "enum": ["k0", "k1", "bridge_infra"] },
    "status":     { "enum": ["proposed", "experimental", "active", "deprecated", "deferred"] },
    "producer": {
      "type": "object",
      "required": ["kernel"],
      "additionalProperties": false,
      "properties": {
        "kernel":   { "enum": ["k0", "k1", "device"] },
        "pipeline": { "type": "string" },
        "emitter":  { "type": "string" },
        "service":  { "type": "string" }
      }
    },
    "consumer": {
      "type": "object",
      "required": ["kernel"],
      "additionalProperties": false,
      "properties": {
        "kernel":  { "enum": ["k0", "k1", "device"] },
        "service": { "type": "string" },
        "state":   { "type": "string" }
      }
    },
    "schema": {
      "type": "string",
      "description": "Path relative to bridge/contracts/, must point at an existing JSON Schema 2020-12 file."
    },
    "delivery": {
      "type": "object",
      "required": ["transport", "ordering", "ack_required", "online_required", "codec"],
      "additionalProperties": false,
      "properties": {
        "transport":            { "enum": ["http", "sse", "in_process", "e2ee_lan", "https"] },
        "ordering":             { "enum": ["strict", "best_effort", "causal"] },
        "ack_required":         { "type": "boolean" },
        "online_required":      { "type": "boolean" },
        "codec":                { "enum": ["json", "msgpack", "cbor", "flatbuffers"] },
        "endpoint_class":       { "enum": ["cloud_k0", "home_k0", "peer_k1", "device_local", "either"] },
        "partition_mode":       { "enum": ["k0_primary", "k1_mesh_fallback", "k1_mesh_only"] },
        "max_queue_age":        { "type": "string", "pattern": "^[0-9]+(ms|s|m|h|d)$" },
        "drain_rate_per_sec":   { "type": ["integer", "null"], "minimum": 1 },
        "retry":                { "enum": ["none", "exponential_backoff", "linear_backoff"] },
        "max_redelivery":       { "type": "integer", "minimum": 0 }
      }
    },
    "semantics": {
      "type": "object",
      "required": ["idempotent", "duplicate_strategy", "retention", "description"],
      "additionalProperties": false,
      "properties": {
        "idempotent":         { "type": "boolean" },
        "duplicate_strategy": { "enum": ["dedupe_by_envelope_id", "last_write_wins", "application_resolved"] },
        "retention":          { "type": "string", "pattern": "^[0-9]+(s|m|h|d)$" },
        "description":        { "type": "string", "minLength": 40,
                                  "description": "Free-text semantics block (R6 mitigation). Must describe units, timezones, and meaning the schema cannot capture." }
      }
    },
    "sla": {
      "type": "object",
      "required": ["latency_p99_ms", "availability"],
      "additionalProperties": false,
      "properties": {
        "latency_p99_ms": { "type": "integer", "minimum": 1 },
        "availability":   { "enum": ["strict", "degrades_to_local_queue", "degrades_to_empty", "best_effort"] }
      }
    },
    "versioning": {
      "type": "object",
      "required": ["strategy", "breaking_change_requires"],
      "additionalProperties": false,
      "properties": {
        "strategy":                 { "enum": ["additive_only_within_v1", "semver"] },
        "breaking_change_requires": { "type": "string" },
        "dual_publish_until":       { "type": "string", "format": "date-time" }
      }
    },
    "sync": {
      "type": "object",
      "required": ["layer"],
      "additionalProperties": false,
      "properties": {
        "layer":      { "enum": ["l1_family_memory", "l2_family_tool_state", "l3_intra_person_devices"] },
        "tool_class": { "enum": ["shared_family", "shared_subset", "personal"] }
      }
    },
    "signing": {
      "type": "object",
      "required": ["ca_id", "signature"],
      "additionalProperties": false,
      "properties": {
        "ca_id":     { "type": "string" },
        "signature": { "type": "string", "contentEncoding": "base64" }
      }
    },
    "checksums": {
      "type": "object",
      "required": ["schema_sha256", "manifest_sha256"],
      "additionalProperties": false,
      "properties": {
        "schema_sha256":   { "type": "string", "pattern": "^[0-9a-f]{64}$" },
        "manifest_sha256": { "type": "string", "pattern": "^[0-9a-f]{64}$" }
      }
    }
  },
  "allOf": [
    {
      "if":   { "properties": { "direction": { "enum": ["k0_to_k0", "k1_to_k1"] } } },
      "then": { "required": ["sync"] }
    },
    {
      "if":   { "properties": { "sync": { "properties": { "layer": { "const": "l2_family_tool_state" } } } } },
      "then": { "properties": { "sync": { "required": ["tool_class"] } } }
    },
    {
      "if":   { "properties": { "direction": { "enum": ["device_to_k0", "k0_to_device"] } } },
      "then": { "required": ["signing"] }
    }
  ]
}
```

Notes locking the design choices into the schema:

- `additionalProperties: false` everywhere — unknown keys fail validation. Catches typos at PR time.
- `semantics.description` requires `minLength: 40` — R6 mitigation: a one-word description fails CI, forcing the author to actually fill in the timezone/units/meaning.
- `sync` is conditionally required for `k0_to_k0` and `k1_to_k1` directions (allOf #1).
- `tool_class` is conditionally required only when `sync.layer == l2_family_tool_state` (allOf #2).
- `signing` is conditionally required only for IFL/device contracts (allOf #3) — closes back to D3.
- `checksums` is *optional* in the schema but **CI fills it on every PR** via the `schema-checksum-stable` gate (D5). Authors never edit it.

### D2 — Codegen template set

**Decision:** four Jinja2 templates under `tooling/contracts/templates/`, plus the `datamodel-code-generator` CLI invocation for the payload models. The templates emit one file per `(role, topic)` pair into `bridge/_generated/{k0,k1}/` so K0 and K1 trees stay disjoint (the wall holds even inside `_generated/`).

```text
tooling/contracts/
  codegen.py                      # entrypoint; CLI: python -m tooling.contracts.codegen [--check]
  manifest_loader.py              # parses manifests, validates against _meta/manifest.schema.json
  templates/
    port_protocol.py.jinja        # → bridge/_generated/{k0,k1}/ports/<topic>_v<N>.py
    client_stub.py.jinja          # → bridge/_generated/<producer.kernel>/clients/<topic>_v<N>.py
    handler_registry.py.jinja     # → bridge/_generated/<consumer.kernel>/handlers/<topic>_v<N>.py
    package_index.py.jinja        # → bridge/_generated/{k0,k1}/__init__.py (re-exports)
```

Template sketches — each generated file starts with the canonical header and a manifest-bundle SHA so reviewers can grep for drift:

```jinja
{# port_protocol.py.jinja — generates one Protocol per topic #}
# AUTOGENERATED — DO NOT EDIT — regenerate with: python -m tooling.contracts.codegen
# manifest_bundle_sha: {{ bundle_sha }}
# source manifest:     bridge/contracts/manifests/{{ manifest.topic }}.yaml
from __future__ import annotations
from typing import Protocol, runtime_checkable
from bridge._generated.{{ role }}.models.{{ topic_module }} import {{ payload_class }}

@runtime_checkable
class {{ port_class }}(Protocol):
    """Generated from {{ manifest.topic }}. {{ manifest.semantics.description | first_sentence }}"""

    async def {{ method_name }}(self, payload: {{ payload_class }}) -> {{ return_type }}: ...
```

```jinja
{# client_stub.py.jinja — thin dispatch into the hand-written transport #}
# AUTOGENERATED — DO NOT EDIT — regenerate with: python -m tooling.contracts.codegen
# manifest_bundle_sha: {{ bundle_sha }}
from bridge.core.transport import get_transport
from bridge._generated.{{ role }}.models.{{ topic_module }} import {{ payload_class }}

class {{ client_class }}:
    __transport__ = "{{ manifest.delivery.transport }}"
    __topic__     = "{{ manifest.topic }}"

    def __init__(self, runtime):
        self._transport = get_transport(runtime, transport=self.__transport__)

    async def {{ method_name }}(self, payload: {{ payload_class }}) -> {{ return_type }}:
        return await self._transport.dispatch(self.__topic__, payload)
```

```jinja
{# handler_registry.py.jinja — binds an impl callable to the consumer side #}
# AUTOGENERATED — DO NOT EDIT — regenerate with: python -m tooling.contracts.codegen
# manifest_bundle_sha: {{ bundle_sha }}
from typing import Callable, Awaitable
from bridge._generated.{{ role }}.models.{{ topic_module }} import {{ payload_class }}

def register_handlers(runtime, *, impl: Callable[[{{ payload_class }}], Awaitable[{{ return_type }}]]) -> None:
    runtime.register_consumer(
        topic="{{ manifest.topic }}",
        transport="{{ manifest.delivery.transport }}",
        handler=impl,
    )
```

`datamodel-code-generator` is invoked once per payload schema with the canonical flag set so output is deterministic across machines:

```bash
datamodel-codegen \
  --input bridge/contracts/schemas/<topic>.v<N>.json \
  --input-file-type jsonschema \
  --output bridge/_generated/<role>/models/<topic>_v<N>.py \
  --target-python-version 3.13 \
  --output-model-type pydantic_v2.BaseModel \
  --use-schema-description \
  --use-field-description \
  --use-default \
  --strict-nullable \
  --disable-timestamp
```

The `--disable-timestamp` flag is critical: it removes the date-stamp header so the no-diff CI gate (Decision 3) doesn't false-positive every time codegen runs.

### D3 — `ca_bundle.json` initial content + key-generation procedure

**Decision:** ship the file shape and the offline ceremony now; commit a placeholder bundle with no real key into the repo today; replace its `ed25519_public_key` with the real key in a separate signed PR before MS-5 ships (when the first IFL adapter actually needs to validate).

Bundle file shape — the entire file is this:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "bridge://contracts/_meta/ca_bundle.json",
  "version": 1,
  "keys": [
    {
      "ca_id": "familyos_root_v1",
      "algorithm": "ed25519",
      "ed25519_public_key": "<32-byte-base64url-no-padding>",
      "status": "active",
      "valid_from": "2026-05-05T00:00:00Z",
      "valid_until": "2029-05-05T00:00:00Z"
    }
  ]
}
```

Validator: `bridge/contracts/_meta/ca_bundle.schema.json` (a small JSON Schema 2020-12 doc) sits next to it; CI validates the bundle against the schema.

Key-generation procedure (offline ceremony — documented in `docs/runbooks/familyos_root_v1_keygen.md`, content sketch below):

1. **Air-gapped machine.** Fresh Tails USB or known-clean Linux laptop with no network. No browser, no clipboard daemon, no cloud sync.
2. **Generate.** `python -c "from nacl.signing import SigningKey; import base64; sk = SigningKey.generate(); print('SEED:', base64.urlsafe_b64encode(sk.encode()).decode().rstrip('=')); print('PUB:', base64.urlsafe_b64encode(sk.verify_key.encode()).decode().rstrip('=')) "`. The seed is 32 bytes; the public key is 32 bytes. Both base64url, no padding (matches `bridge/core/signing.py:Ed25519Signing` exactly).
3. **Split the seed.** Shamir 3-of-5 via `ssss-split -t 3 -n 5 -w familyos-root-v1`. Five shares. Print each share on a separate sheet of paper; place each in a tamper-evident envelope; physically distribute to five separate trusted holders (different geographic locations, different employers if possible).
4. **Destroy the originals.** `shred -uvz` the raw seed file. Power off the laptop without ever connecting it to a network.
5. **Commit only the public key.** Open a PR that updates `ca_bundle.json` `ed25519_public_key` with the public key from step 2. The PR description references the runbook and the share-holder list (names but not addresses).
6. **Reconstitute only when signing.** Three of the five share-holders meet in person on an air-gapped machine; reconstruct the seed; sign the IFL adapter manifests; destroy the reconstructed seed before leaving. The signed manifests — not the seed — are what gets committed.

Why ship the placeholder before the real key: the meta-schema gate (D1, allOf #3) requires every IFL/device manifest to declare `signing.ca_id`. If the bundle file doesn't exist, every IFL manifest PR would fail validation. The placeholder bundle with a non-functional key lets MS-5 manifests pass schema validation; the *signature-verification* gate is enabled in the same release as the real key replacement.

Integration with existing K0 crypto: K0's `MinimalGate` continues to verify *envelope* signatures via `ProvisioningLedger.DeviceKey` (per-device Ed25519 keys). The `ca_bundle.json` model is a **separate trust root** specific to *manifest signing*. The two systems don't overlap — device keys sign envelopes on the wire, the FamilyOS root signs IFL manifests at install. Documented explicitly in the runbook to prevent confusion.

### D4 — First contract migrated: `memory.write.v1`

**Decision:** rewrite the existing one-and-only contract (`bridge/contracts/command_port.protocol.yaml`, the older protocol-level descriptor) into a per-topic manifest at `bridge/contracts/manifests/memory.write.v1.yaml`. Keep the existing payload schema chain intact — the K0 `memory_write.body.json` already `$ref`s the K1 `memory_atom.v2.schema.json`, which is the source of truth for the body. The manifest only references it.

The manifest:

```yaml
topic: memory.write.v1
direction: k1_to_k0
owner_team: k0
status: active

producer:
  kernel: k1
  service: MemoryWriterService
  emitter: BatchEmitter
consumer:
  kernel: k0
  service: MinimalGate
  state: command_submit_endpoint

schema: schemas/memory.write.v1.json   # thin wrapper that $refs the existing memory_atom.v2 schema

delivery:
  transport: http
  ordering: best_effort
  ack_required: false
  online_required: false
  codec: json
  endpoint_class: either
  max_queue_age: 24h
  retry: exponential_backoff
  max_redelivery: 10

semantics:
  idempotent: true
  duplicate_strategy: dedupe_by_envelope_id
  retention: 30d
  description: >
    Episodic memory write from K1 MemoryWriter into K0 P02. Body is a MemoryAtom v2.2
    record (14 required fields including affect, novelty, elaboration_depth, temporal
    orientation). Idempotency key is BLAKE3(topic + canonical_json(body) + device_id).
    Timezone for `ts` and any record timestamps is UTC, ISO-8601 with explicit Z suffix.
    `confidence` is in [0.0, 1.0] inclusive; values outside are gate-rejected.

sla:
  latency_p99_ms: 800
  availability: degrades_to_local_queue

versioning:
  strategy: additive_only_within_v1
  breaking_change_requires: new_topic_v2_with_dual_publish_window_30d
```

And the body schema wrapper at `bridge/contracts/schemas/memory.write.v1.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "bridge://contracts/schemas/memory.write.v1.json",
  "title": "memory.write.v1 body",
  "description": "Wrapper that defers to the canonical MemoryAtom v2.2 schema.",
  "$ref": "k1://contracts/schemas/memory_writer/memory_atom.v2.schema.json"
}
```

Reconciliation with the live topic name: production uses `"memory.write"`; the manifest uses `"memory.write.v1"`. The MS-2.5 cut-over is one PR that adds the new topic alongside the old, then a second PR (start of MS-3a) that flips producers and removes the un-versioned alias. Both topics route through K0's existing `MinimalGate` — the gate doesn't care about the suffix; the topic-to-pipeline routing in `command_topics.yaml` gets the new entry.

Why this contract first (and not `command.submit`): there is no `command.submit` *topic* — `command.submit` is the *endpoint*. `memory.write` is the actual cross-kernel topic. The whiteboard's earlier MS-2.5 row referencing `command.submit` was conflating the transport and the contract; this closure corrects it.

The MS-2.5 exit-criterion test (above) updates two strings to match: `"memory.write.v1"` and the import path `bridge._generated.k1.clients.memory_write_v1`.

### D5 — CI gate scripts

**Decision:** introduce `tooling/ci/` with one Python script per gate and a top-level `tooling/ci/run_all_gates.py` orchestrator. No GitHub Actions workflow is committed in MS-2.5 — the gates are wired into a `pre-commit` config and a one-line `Makefile` target so they're runnable by anyone (CI infra adoption is an ops decision orthogonal to the design). When `.github/workflows/` lands, it calls `make gates`.

The six gate scripts:

```text
tooling/ci/
  __init__.py
  run_all_gates.py                          # orchestrator; nonzero exit on any failure
  gates/
    no_cross_kernel_imports.py              # Q11.1
    bridge_not_imported_from_kernels.py     # Q11.2
    manifest_implementation_bound.py        # Q11.3
    schema_checksum_stable.py               # Q11.4
    bus_yaml_aligned_with_registry.py       # Q11.5
    single_ibridge_port_definition.py       # Q11.6 / D6
```

Gate-by-gate behaviour (each script exits 0 on pass, 1 on fail, prints offending file/line on stderr):

| Gate | Implementation sketch | Day-one expected result |
| --- | --- | --- |
| `no_cross_kernel_imports` | `ast.parse` every `*.py` under `k0/` and `k1/`; visit `Import` and `ImportFrom`; fail if `k0/**` imports `k1.*` or `k1/**` imports `k0.*`. Allowlist via `# noqa: cross-kernel — reason` annotation. | **Green** — grep already shows zero violations in `.py` files. |
| `bridge_not_imported_from_kernels` | `ast.parse` `k0/**/*.py` + `k1/**/*.py`; fail if any imports `bridge.core.*`, `bridge.kernel.*`, `bridge.sync.*`, `bridge.connector.*`. Allowed: `bridge.client`, `bridge.contracts`, `bridge.testing`, `bridge._generated.<own_role>.*`, `bridge.ports`. Two known-violations file (`tooling/ci/known_violations/bridge_imports.txt`) lets MS-2.5 ship while MS-3a/MS-3b remediate. | **2 known violations** (memory_writer, kernel adapter); allow-listed with TODO link to MS-3a / MS-3b. |
| `manifest_implementation_bound` | Boots `BridgeRuntime.from_registry('bridge/contracts/')` in test mode for each role (`k0`, `k1`); for every contract with `status: active`, asserts a generated handler/client exists in `bridge/_generated/<role>/`. | Green only after D2 + D4 land. The orchestrator skips this gate (with WARN, not FAIL) if `bridge/_generated/` is empty, so MS-2.5 PR#1 (the rename PR) doesn't get blocked by codegen output that doesn't exist yet. |
| `schema_checksum_stable` | Lifts `k0/automation/compute_contract_checksums.py` into `tooling/contracts/checksums.py` (rename-only; same logic). Recomputes `manifest.checksums.{schema_sha256, manifest_sha256}` for every manifest; fails if the value in the file disagrees. | Green by construction — the script also auto-fixes when run with `--update`. |
| `bus_yaml_aligned_with_registry` | Parse `k1/config/bus.yaml`; for every `timing_rules` prefix that matches a cross-kernel pattern (`k0.*`, `memory.*`, `feedback.*`, `recall.*`, `curiosity.*`, `p0[1-9].*`, `family.*`, `ifl.*`), assert at least one registry manifest exists with a topic that starts with that prefix. | Day one will fail loudly until each prefix gets at least a `status: proposed` manifest. That failure is the point — it surfaces every cross-kernel topic that's currently leaking past the wall. |
| `single_ibridge_port_definition` | `grep -rE "^class IBridgePort\b" k0 k1`; fail if any hit. (The bridge's own ports module is allowed to keep its protocol classes; they're named `IKernelCommandPort` etc., not `IBridgePort`.) | **Day one will fail with 3 hits** — the three known definitions (kernel, fabric, planner). Gate enforced *after* MS-2.5 PR#1 (the rename PR) lands, not before. The orchestrator runs it as `--warn-only` until that PR ships, then flips to `--fail-on-violation`. |

`run_all_gates.py` is a thin wrapper:

```python
import subprocess, sys
from pathlib import Path

GATES = [
    "no_cross_kernel_imports",
    "bridge_not_imported_from_kernels",
    "manifest_implementation_bound",
    "schema_checksum_stable",
    "bus_yaml_aligned_with_registry",
    "single_ibridge_port_definition",
]

failed = []
for name in GATES:
    rc = subprocess.call([sys.executable, "-m", f"tooling.ci.gates.{name}"])
    if rc != 0:
        failed.append(name)

if failed:
    print(f"::error::{len(failed)} gate(s) failed: {', '.join(failed)}", file=sys.stderr)
    sys.exit(1)
print("All bridge gates green.")
```

Why not `import-linter`: the existing ADR-0004b proposes `import-linter` for K1's *layer* architecture. The bridge wall is a different concern (kernel boundary, not module layer) and our enforcement also needs to walk YAML files and SQLite schemas, neither of which `import-linter` supports. Custom Python scripts are simpler, faster, and give better error messages. K1 can adopt `import-linter` separately for its own layer enforcement; the two systems coexist.

### D6 — `single-ibridge-port-definition` gate

Covered above as the sixth gate in D5. The standalone notes:

- The gate is **created in MS-2.5 PR#1** but enabled in **`--warn-only` mode** for the duration of that PR (so the rename PR itself doesn't get blocked by the violations it's about to fix).
- The PR's last commit flips it to `--fail-on-violation`. From that point on, any future commit reintroducing a `class IBridgePort` outside `bridge/ports/` fails CI.
- Updated rename mapping (the code-walk corrected the locations the whiteboard had earlier):

  | Current location | Current role | New name | Action |
  | --- | --- | --- | --- |
  | [`k1/kernel/ports/bridge_port.py`](../../../k1/kernel/ports/bridge_port.py) | Lifecycle wrapper (`connect / disconnect / is_connected / get_client`) | `IBridgeRuntime` | Rename + update import sites in `k1/kernel/ports/__init__.py`, `k1/kernel/service.py`, `k1/kernel/adapters/bridge_adapter.py` |
  | [`k1/fabric/ports/bridge_port.py`](../../../k1/fabric/ports/bridge_port.py) | Fabric's K0-access port (`send_command / query / route_ifl / is_available / get_health`) | `IFabricK0Port` | Rename + update `k1/fabric/ports/__init__.py`, `k1/fabric/providers/bridge_provider.py` (4 sites), `k1/fabric/adapters/bridge_connection.py`, `k1/planner/adapters/bridge_adapter.py` (cross-uses Fabric's IBridgePort) |
  | [`k1/planner/ports/bridge_port.py`](../../../k1/planner/ports/bridge_port.py) | Planner's recall+persist port (`recall / persist_plan`) | `IPlannerWritePort` | Rename + update `k1/planner/ports/__init__.py`, `k1/planner/__init__.py:72`, `k1/planner/factory.py`, `k1/planner/stages/commit_service.py`, `k1/planner/services/tool_call_router.py` |

  Test files (12 under `tests/k1/`) are renamed in the same PR so the rename atomically resolves to a single CI commit.

- After PR#1 lands, the only file in the repo containing `class IBridgePort` is none — all three are renamed. The bridge's hand-written domain protocols (`IKernelCommandPort`, etc., in `bridge/ports/`) keep their existing names; they were never called `IBridgePort`.

### Updated D1–D6 status

### Must close before MS-2.5 ships

| ID | Decision | Where in doc | Current state |
| --- | --- | --- | --- |
| D1 | Final manifest meta-schema document (full JSON Schema, not the sketch) | “MS-2.5 substrate” → Decision 1 | **Closed.** Full schema in “MS-2.5 closure pack → D1” above; ships as `bridge/contracts/_meta/manifest.schema.json`. |
| D2 | Codegen template set for ports / clients / handlers | “MS-2.5 substrate” → Decision 2 | **Closed.** Four Jinja2 templates + `datamodel-code-generator` invocation specified in “MS-2.5 closure pack → D2” above. |
| D3 | `bridge/contracts/_meta/ca_bundle.json` initial content + `familyos_root_v1` keypair generation procedure | Resolved Deferred item 4 | **Closed.** Bundle file shape, validator schema, and 6-step offline Shamir 3-of-5 ceremony specified in “MS-2.5 closure pack → D3” above. Placeholder bundle commits in MS-2.5; real key replaces it pre-MS-5. |
| D4 | First contract migrated into the new manifest format (`memory.write.v1`) as the codegen smoke test | MS-2.5 milestone row + exit-criterion test | **Closed.** Full `memory.write.v1.yaml` manifest + body-schema wrapper specified in “MS-2.5 closure pack → D4” above. Reconciliation with the un-suffixed `memory.write` topic noted; cut-over is two PRs (MS-2.5 add, MS-3a remove alias). |
| D5 | CI gate scripts for Q11 (`no-cross-kernel-imports`, `bridge-not-imported-...`, `manifest-implementation-bound`, `schema-checksum-stable`, `bus-yaml-aligned-with-registry`) | Q11 table | **Closed.** Six scripts under `tooling/ci/gates/` specified in “MS-2.5 closure pack → D5” above; orchestrator + day-one expected results documented. Lifts existing K0 `compute_contract_checksums.py` into `tooling/contracts/checksums.py`. |
| D6 | CI gate `single-ibridge-port-definition` from Resolved Deferred item 5 step 1 | Resolved Deferred item 5 | **Closed.** Specified as the sixth gate in D5; rename mapping corrected against actual code locations (kernel → `IBridgeRuntime`, fabric → `IFabricK0Port`, planner → `IPlannerWritePort`); enabled `--warn-only` during MS-2.5 PR#1, flips to `--fail-on-violation` at end of that PR. |

## MS-3a / MS-3d / MS-5 closure pack — D7–D19 production-grade decisions

The thirteen decisions D7–D19 close in this pack. Two strategic shifts shape several of them:

- **Drop the WASM-sandboxed adapter runtime.** v1 ships exactly one IFL adapter shape: **MCP (Model Context Protocol) servers** running as separate OS processes, sandboxed by the OS (process isolation + seccomp/AppArmor on Linux, App Sandbox on macOS, AppContainer on Windows), reached over stdio or a local Unix-domain / loopback HTTP socket. WASM is removed from MS-5 entirely. The IFL Runtime becomes the **MCP Process Manager** (spawn / supervise / restart / kill MCP child processes; multiplex tool calls; enforce per-adapter quotas via OS cgroups/Job Objects, not WASM caps). Re-add WASM post-v2 only if a 3rd-party marketplace materialises that needs in-process untrusted code.
- **Defer per-adapter rate-limiting and circuit-breakers.** v1 relies on the underlying SDK's HTTP client retry/timeout settings + the per-adapter cgroup CPU/memory ceiling. No ConnectorGateway-level token bucket, no breaker. The hooks are designed in (see D18) so the v1.1 milestone can drop them in without surface-area churn.

### D7 — CODEOWNERS + PR template for `bridge/contracts/`

**Decision:** ship the governance now; it costs nothing and prevents most of the manifest-quality regressions R6 warns about.

Files to commit (single PR, lands with MS-2.5 PR#2):

- `.github/CODEOWNERS` — append:

  ```text
  # Bridge contract registry: every change requires both a bridge-infra reviewer AND
  # the owning team's reviewer (the manifest's `owner_team:` field decides which team).
  /bridge/contracts/                       @familyos/bridge-infra
  /bridge/contracts/manifests/memory.*     @familyos/bridge-infra @familyos/k0-team
  /bridge/contracts/manifests/recall.*     @familyos/bridge-infra @familyos/k0-team
  /bridge/contracts/manifests/curiosity.*  @familyos/bridge-infra @familyos/k0-team
  /bridge/contracts/manifests/p03.*        @familyos/bridge-infra @familyos/k0-team
  /bridge/contracts/manifests/feedback.*   @familyos/bridge-infra @familyos/k0-team
  /bridge/contracts/manifests/k0.*         @familyos/bridge-infra @familyos/k0-team
  /bridge/contracts/manifests/family.*     @familyos/bridge-infra @familyos/k0-team @familyos/k1-team
  /bridge/contracts/manifests/ifl.*        @familyos/bridge-infra @familyos/k1-team
  /bridge/contracts/_meta/                 @familyos/bridge-infra @familyos/security-team
  /bridge/_generated/                      @familyos/bridge-infra
  /tooling/contracts/                      @familyos/bridge-infra
  /tooling/ci/gates/                       @familyos/bridge-infra
  ```

- `.github/pull_request_template.md` — replace any existing template with:

  ```markdown
  ## Summary

  <!-- one-paragraph what + why -->

  ## Bridge contract changes (delete this section if none)

  - [ ] Manifest(s) touched: <topic.vN>
  - [ ] `semantics.description` ≥40 chars and explicitly states **timezone**, **units**, **idempotency window**, and **what a duplicate means** (R6).
  - [ ] If breaking change: `versioning.breaking_change_requires` + `dual_publish_until` set per D8 (default +30d).
  - [ ] `python -m tooling.contracts.codegen` run; `bridge/_generated/` re-vendored; `git diff --exit-code bridge/_generated/` clean.
  - [ ] `python -m tooling.ci.run_all_gates` green locally.
  - [ ] CHANGELOG entry under "Bridge contracts".

  ## Risk + rollback

  <!-- impact radius; how to roll back if green-then-broken -->

  ## Tests

  <!-- list new test names; confirm no-mock policy honoured -->
  ```

- `tooling/ci/gates/pr_template_compliance.py` — **lightweight**: when the PR diff touches `bridge/contracts/manifests/`, assert the PR body contains the manifest checklist's checked boxes. Implemented as a separate GitHub Action job (`.github/workflows/pr_lint.yml`) since it needs PR metadata, not just repo state. Runs `--warn-only` for first 4 weeks then flips to fail.

**Boot-time enforcement** (defence-in-depth — even if the PR template is bypassed, the runtime catches it): `BridgeRuntime.from_registry()` re-validates every active manifest against the meta-schema, which already enforces `semantics.description: minLength: 40` (D1). A short or missing description fails CI long before it can reach prod.

### D8 — Dual-publish window default + `dual_publish_until` meta-schema field

**Decision:** **30 days** is the default dual-publish window for any breaking change (`v<N>` → `v<N+1>`). Producer publishes both topics; consumers migrate; on `dual_publish_until`, producer drops the old topic. The window is overrideable per-contract for high-cadence schemas (push down to 7 days) or critical APIs (push up to 90 days), with a `--breaking-change-rationale` field that the PR template surfaces.

**Meta-schema additions** (apply on top of D1; ships in MS-2.5 PR#2):

```json
{
  "properties": {
    "versioning": {
      "type": "object",
      "additionalProperties": false,
      "required": ["strategy", "breaking_change_requires"],
      "properties": {
        "strategy": {
          "enum": ["additive_only_within_v1", "additive_only_within_vN"]
        },
        "breaking_change_requires": {
          "enum": [
            "new_topic_v2_with_dual_publish_window_30d",
            "new_topic_vN_with_custom_dual_publish_window"
          ]
        },
        "dual_publish_until": {
          "type": "string",
          "format": "date-time",
          "description": "UTC ISO-8601 timestamp after which the previous version may be removed. Required when a vN+1 manifest is added while vN is still active. Default = manifest creation date + 30d."
        },
        "supersedes": {
          "type": "string",
          "pattern": "^[a-z][a-z0-9_]*(\\.[a-z0-9_]+)+\\.v[0-9]+$",
          "description": "Topic of the previous version this manifest supersedes. Required when manifest is a vN+1 of an existing topic."
        },
        "breaking_change_rationale": {
          "type": "string",
          "minLength": 80,
          "description": "Required when dual_publish_until deviates from the 30d default."
        }
      },
      "allOf": [
        {
          "if": { "properties": { "supersedes": { "type": "string" } }, "required": ["supersedes"] },
          "then": { "required": ["dual_publish_until"] }
        }
      ]
    }
  }
}
```

**New CI gate `dual_publish_window_active`** (`tooling/ci/gates/dual_publish_window_active.py`):

- For every manifest with `versioning.supersedes`, assert the superseded `vN` manifest still exists with `status: deprecated` and **its** `versioning.dual_publish_until` ≥ now.
- For every `status: deprecated` manifest, assert `versioning.dual_publish_until` exists. If `dual_publish_until < now - 7d`, fail with "deprecated manifest past sunset window — delete it now".
- Producer-side enforcement: codegen emits a runtime warning (logged at boot) if `BridgeRuntime` loads a manifest whose `dual_publish_until < now`.

**Rollover playbook** (commit as `docs/runbooks/contract_versioning.md`):

1. Author `vN+1` manifest with `supersedes: <topic>.v<N>` and `dual_publish_until: <now+30d>`.
2. Mark `vN` as `status: deprecated` and add `dual_publish_until` to it (mirror).
3. Codegen emits both client stubs; producers wire vN+1 in same PR; vN client kept available.
4. Consumer migration tracked via `bridge.command.<topic>.v<N>.{accepted_total}` going to zero.
5. After `dual_publish_until`, separate PR removes vN manifest + vN producer code; gate enforces.

### D9 — `OnlineFirst[Port]` decorator concrete implementation

**Decision:** specified to source-code level in MS-3b epic 3b.4 of the implementation plan. Pinning the production-grade behaviours not yet captured there:

- **Class shape:** dynamically generated subclass per Port `Protocol` via `__init_subclass__`/factory; one concrete `OnlineFirstCommandPort`, `OnlineFirstObsPort`, etc. Generation is at runtime construction (`BridgeRuntime.from_registry()`), not at codegen time — keeps `_generated/` free of behavioural mixins.
- **Per-call decision matrix** is the auto-derived `DegradedModeManager.behavior_for(port, topic)` from MS-3b epic 3b.2; the decorator does not contain its own conditionals (R10 enforcement: zero hand-coded `if degraded:` outside `bridge/core/degraded.py`).
- **`max_queue_age` enforcement:** at enqueue time the envelope is stamped with `expires_at = now + manifest.delivery.max_queue_age`. The drain worker drops expired envelopes and emits `bridge.outbox.pruned_total{topic, reason="ttl_expired"}` + audit log. The decorator does NOT itself reject — TTL is checked at drain, not at enqueue, so a long offline window doesn't pre-emptively delete envelopes that might still be drainable on quick recovery.
- **`online_required` enforcement:** decorator raises `OfflineError(topic, current_state, last_online_at, manifest_url)` synchronously at the call site when state ≠ ONLINE and `online_required: true`. Caller never sees the wire.
- **Idempotency:** the decorator does not dedupe on its own. Idempotency is the K0 receiver's responsibility (`IdempotencyLedger`, MS-3a epic 3a.3) keyed on the envelope's `idem_key`. Outbox replays under same `idem_key` are absorbed by K0.
- **Concurrency:** decorator is asyncio-only; per-port lock not needed (outbox enqueue is atomic via SQLite); however the drain worker holds a per-topic semaphore (count = 1) to preserve `delivery.ordering: best_effort` during burst replays.
- **Failure-on-online:** if inner port raises `httpx.HTTPStatusError(5xx)` while state==ONLINE, decorator catches; if behaviour is `queue_to_outbox`, enqueues; if `raise_offline_error`, propagates as `OfflineError(reason="transient_5xx")`. 4xx propagates unchanged (validation errors are caller bugs).
- **Observability:** every decision logged as `{"event": "online_first_decision", "topic": ..., "state": ..., "behavior": ..., "decision": "inline|queued|raised", "envelope_id": ...}`; metric `bridge.online_first.dispatch_total{port, topic, decision}`.

### D10 — Boot-fail-on-unbound-contract: error format + exit code

**Decision:** unified, machine-parseable failure surface so ops runbooks can grep on it.

**Exit code:** `78` (chosen from sysexits.h `EX_CONFIG` — "configuration error"). Reserved exclusively for "bridge runtime refused to boot due to a contract problem". Other startup failures keep their existing exit codes.

**Error message format** (single-line JSON to stderr, plus pretty-printed multi-line below for humans):

```text
::error::BRIDGE_BOOT_FAILED {"code":"E_BRIDGE_BOOT_UNBOUND_CONTRACT","exit":78,"role":"k1","manifest_bundle_sha":"<sha>","violations":[{"manifest":"bridge/contracts/manifests/memory.write.v1.yaml","topic":"memory.write.v1","direction":"k1_to_k0","missing":"producer_client","expected_module":"bridge._generated.k1.clients.memory_write_v1","reason":"module not found"}],"runbook":"https://github.com/Pkansagra-hub/family-os/blob/main/docs/runbooks/bridge_boot_failures.md#E_BRIDGE_BOOT_UNBOUND_CONTRACT"}

BridgeRuntime refused to start.
  Reason:  unbound contract(s) detected
  Code:    E_BRIDGE_BOOT_UNBOUND_CONTRACT (exit 78)
  Role:    k1
  Bundle:  <sha>
  Violations (1):
    - bridge/contracts/manifests/memory.write.v1.yaml
        topic:     memory.write.v1
        direction: k1_to_k0
        missing:   producer_client (bridge._generated.k1.clients.memory_write_v1)
        reason:    module not found
  Fix:     run `python -m tooling.contracts.codegen` and commit bridge/_generated/.
  Runbook: docs/runbooks/bridge_boot_failures.md#E_BRIDGE_BOOT_UNBOUND_CONTRACT
```

**Error code taxonomy** (all carry exit 78; runbook section per code):

| Code | Trigger | Fix |
| ---- | ------- | --- |
| `E_BRIDGE_BOOT_UNBOUND_CONTRACT` | manifest `status: active` but no generated module | regenerate codegen, commit `_generated/` |
| `E_BRIDGE_BOOT_MANIFEST_INVALID` | manifest fails meta-schema validation | fix the manifest field listed in `violations[].field` |
| `E_BRIDGE_BOOT_SCHEMA_MISSING` | manifest's `schema:` path not on disk | commit the schema file |
| `E_BRIDGE_BOOT_CHECKSUM_DRIFT` | committed `manifest.checksums` disagrees with file | run `tooling.contracts.checksums --update` |
| `E_BRIDGE_BOOT_CA_BUNDLE_MISSING` | manifest requires `signing.ca_id` not in `_meta/ca_bundle.json` | add CA via D3 ceremony |
| `E_BRIDGE_BOOT_DUPLICATE_TOPIC` | two active manifests claim same topic | mark one `deprecated` |
| `E_BRIDGE_BOOT_DUAL_PUBLISH_EXPIRED` | `vN` past its `dual_publish_until` still wired | delete vN manifest + producer code |

**Implementation in `bridge/runtime.py`** (sketch):

```python
class BridgeBootError(SystemExit):
    EXIT_CODE = 78
    def __init__(self, code: str, role: str, manifest_bundle_sha: str,
                 violations: list[dict], runbook_anchor: str):
        payload = {
            "code": code, "exit": self.EXIT_CODE, "role": role,
            "manifest_bundle_sha": manifest_bundle_sha, "violations": violations,
            "runbook": f"https://github.com/Pkansagra-hub/family-os/blob/main/docs/runbooks/bridge_boot_failures.md#{code}",
        }
        sys.stderr.write(f"::error::BRIDGE_BOOT_FAILED {json.dumps(payload, separators=(',',':'))}\n\n")
        sys.stderr.write(_pretty_render(payload))
        super().__init__(self.EXIT_CODE)
```

**Runbook commitment:** `docs/runbooks/bridge_boot_failures.md` ships in MS-2.5 with one section per code listing: symptom, log signature, diagnostic commands, fix, escalation contact.

### D11 — `_generated/` and `git blame`

**Decision:** ignore `bridge/_generated/` for `git blame` so codegen commits don't pollute history.

Files to create (lands with MS-2.5 PR#2):

- `.git-blame-ignore-revs` — initially empty (with header comment); CI job populates it on every codegen-only commit.
- `.gitattributes` — append:

  ```text
  bridge/_generated/** linguist-generated=true
  bridge/_generated/** -diff
  ```

  GitHub honours `linguist-generated=true` to collapse these in diff views and exclude from language stats; `-diff` makes `git diff` show file-name only by default (full diff still available with `--text`).

- `tooling/ci/codegen_blame_ignore_updater.py` — CI script that runs after `codegen --check` is clean: if the only paths touched in the head commit are `bridge/_generated/**`, append the commit SHA to `.git-blame-ignore-revs` in a follow-up automated PR. Keeps the file curated without manual maintenance.
- `docs/runbooks/git_blame_setup.md` — one-liner instruction for devs to enable locally:

  ```bash
  git config blame.ignoreRevsFile .git-blame-ignore-revs
  ```

  Pre-commit hook installer (`scripts/install_dev_hooks.sh`) sets this automatically.

**No CI gate** — this is purely an ergonomics decision; broken state is harmless (developers see noisier blame). Skipping enforcement keeps the surface small.

### D12 — SSE chunked-streaming client: `httpx-sse` pinned

**Decision:** **`httpx-sse==0.4.*`** pinned. Already wired into existing `bridge/core/transport/`; we use `httpx` everywhere else; reuses our connection pooling, proxy support, and HTTP/2 enablement; supports `Last-Event-ID` header round-trip natively.

`aiohttp-sse-client` rejected because:

- Forces a second HTTP client into the dep tree (we have httpx; aiohttp brings its own connection pool, TLS context, proxy config).
- Inferior `Last-Event-ID` ergonomics (we'd hand-roll header injection).
- aiohttp's middleware story is foreign to fastapi-style codebases.

**Pin location:** `requirements.txt`:

```text
httpx-sse==0.4.*
sse-starlette==2.0.*   # K0 server side
```

**Upgrade policy:** pin the minor (`0.4.*`); patch updates auto-pull. Minor bumps require a PR with explicit changelog review and the SSE integration test suite re-run.

**Fallback contingency:** if `httpx-sse` is abandoned upstream, the migration target is **`aiohttp-sse-client2`** (active maintenance fork). Decision documented; no current need.

### D13 — SSE cursor-resume protocol

**Decision:** standard `Last-Event-ID` HTTP header, plain text envelope id. K0 server-side replay buffer with **24-hour retention** (matches manifest `delivery.retention: 24h` for SSE topics). Cursor format is the envelope `envelope_id` ULID (already on every SSE event).

**Wire protocol:**

```text
# Initial connect
GET /k0/sse.subscribe?topic=curiosity.intent.v1 HTTP/1.1
Accept: text/event-stream
Cache-Control: no-cache

# Reconnect after disconnect
GET /k0/sse.subscribe?topic=curiosity.intent.v1 HTTP/1.1
Accept: text/event-stream
Cache-Control: no-cache
Last-Event-ID: 01HXXX...           # ULID of last successfully-handled event
```

**K0 server behaviour** (per `Last-Event-ID` value):

| Server response | Condition |
| --------------- | --------- |
| `200 OK`, replay events strictly after the cursor (in id order), then live | cursor is in the 24h replay buffer |
| `200 OK`, send single `event: replay-gap-detected` synthetic envelope, then live (no replay) | cursor is older than 24h or unknown |
| `400 Bad Request` body `{"error":"invalid_last_event_id","received":"<value>"}` | header present but not a valid ULID |
| `200 OK`, live stream from "now" | header absent |

The `replay-gap-detected` synthetic event has `envelope_kind: "control.replay_gap.v1"` and a payload of `{"requested_cursor": "...", "earliest_available": "...", "topic": "..."}`. Subscribers handle this as "you missed events; resync from snapshot if you care". Today nothing in K1 cares (proactive flows are eventually-consistent); the event exists for observability.

**Client behaviour** (`bridge/core/transport/sse_client.py`):

- Persists last-handled `envelope_id` per topic to `~/.familyos/sse_cursors.sqlite` (table: `sse_cursors(topic PRIMARY KEY, last_event_id TEXT, updated_at TIMESTAMP)`); writes are batched every 100 events or 5s wall-clock to avoid IO storms.
- On reconnect, reads cursor from disk; sends as `Last-Event-ID`.
- On `control.replay_gap.v1` event, emits `bridge.sse.replay_gap_total{topic}` metric and an audit log entry; calls user-supplied `on_gap()` callback if registered (optional resync path); continues the live stream.
- Cursor TTL on disk: 30 days; older rows pruned at startup.

**Metric:** `bridge.sse.cursor.{persisted_total{topic}, restored_total{topic}, gap_detected_total{topic}}`.

**No envelope-id authentication** — the cursor is treated as a hint, not a security token. The K0 receiver re-authorises every replayed event the same way it does live ones (subscriber identity is on the connection, not the cursor).

### D14 — SSE backpressure policy

**Decision:** **block-and-close**, not drop. Bounded buffer between wire reader and consumer handler; when full, block the reader (TCP backpressure propagates to K0); after **30 seconds** of blocked state, close the stream and reconnect with the current cursor. Drop policies (oldest-out, newest-out) explicitly rejected because: (a) audit invariants require zero silent loss; (b) cursor-resume already covers the "fall behind, recover" case correctly via D13; (c) closing-and-reconnecting is observable (spike in `bridge.sse.reconnects_total`) where dropping is silent.

**Concrete settings** (in `bridge/core/transport/sse_client.py`):

```python
SSE_INTERNAL_QUEUE_MAXSIZE = 1000           # asyncio.Queue maxsize per topic subscription
SSE_BLOCK_TIMEOUT_S        = 30             # max time wire reader may block on full queue
SSE_RECONNECT_BACKOFF_S    = (0.5, 30.0)    # exp backoff base, cap; jitter ±20%
SSE_RECONNECT_MAX_ATTEMPTS = None           # unlimited (cellular reality)
```

**State machine** (per topic subscription):

```text
HEALTHY ──[queue 80% full]──► PRESSURED ──[queue full + reader blocked >5s]──► STRESSED
                                                                                  │
                                                          [blocked >30s]──────────┤
                                                                                  ▼
                                                                          CLOSING ─► reconnect with cursor ─► HEALTHY
```

**Per-state behaviour:**

| State | Wire reader | Consumer handler | Metrics emitted |
| ----- | ----------- | ---------------- | --------------- |
| HEALTHY | reads as fast as possible | handles | `bridge.sse.queue_depth{topic}` |
| PRESSURED | reads with 10ms cooperative yield between events | unchanged | `bridge.sse.pressure_total{topic}` |
| STRESSED | blocked on `queue.put()` | unchanged | `bridge.sse.stress_total{topic}`, `bridge.sse.wire_blocked_seconds{topic}` |
| CLOSING | stops, calls `disconnect()` | drains remaining queue then exits subscription context | `bridge.sse.forced_close_total{topic, reason="backpressure_timeout"}` |

**Observability runbook entry:** `bridge.sse.forced_close_total > 0` for any topic over a 5-minute window indicates a slow consumer; ops action is to inspect the consumer handler latency (`bridge.sse.handler_latency_ms{topic}` histogram) and either fix the handler or split the subscription into a worker pool.

**Why 1000 / 30s:**

- 1000 events × ~2KB avg payload = ~2MB peak per subscription — bounded memory budget.
- 30s blocked window covers normal handler GC pauses and intermittent slow downstream calls without thrashing the connection.
- Both values overrideable via `BRIDGE_SSE_QUEUE_MAXSIZE` / `BRIDGE_SSE_BLOCK_TIMEOUT_S` env vars for ops tuning; defaults committed in code.

### D15 — First IFL adapter: **Google Calendar (read-only)**

**Decision:** Google Calendar wins MS-5 first-adapter slot.

Rationale:

- **Universal:** every family member already has one (Hue requires bridge hardware).
- **Stable, public OAuth 2.0 flow:** mature SDK (`google-auth`, `google-api-python-client`), well-documented refresh-token semantics, no scraping.
- **Read-only is meaningful:** `calendar.events.list` already exercises the entire IFL path (auth, schema, MCP server, gateway, K0 ingestion) without write-side risk.
- **Demonstrates cross-person planning:** the headline use case ("does the family have a free Saturday afternoon?") is a multi-account read query — proves multi-tenant credential vault (D17) at the same time.

Hue deferred to MS-5+1 (or post-v1):

- Requires LAN discovery, hardware bridge dependency, brittle device-state poll loop.
- Less compelling for the v1 product narrative.

**MS-5 scope for Google Calendar adapter:**

- `bridge/contracts/manifests/ifl.google_calendar.events.list.v1.yaml` — `direction: device_to_k0`, `delivery.transport: https`, `signing.ca_id: familyos_root_v1` (manifest signed; D3 + D19).
- MCP server: `connectors/google_calendar/` — runs as a separate Python process spawned by the MCP Process Manager, exposes one MCP tool `list_events(calendar_id, time_min, time_max)`, holds OAuth refresh tokens in the credential vault (D17), exchanges access tokens on demand.
- K0 P-IFL pipeline ingest: events normalised to `MemoryAtom` (calendar_event subtype), de-duplicated by `(calendar_id, event_id, etag)`.
- Per-tenant OAuth consent flow: device-flow (`urn:ietf:wg:oauth:2.0:oob`) for headless setup; UI for in-band consent on phone.
- Read-only scope: `https://www.googleapis.com/auth/calendar.readonly` only; write scopes explicitly forbidden in v1.

**Out of scope for MS-5 (deferred to MS-6 / post-v1):** event creation, event updates, free/busy push notifications, watch channels, multiple Google identities per family member.

### D16 — Adapter runtime: **MCP servers, no WASM**

**Decision:** the IFL Runtime ships in v1 as the **MCP Process Manager**. Every adapter is an independent OS process speaking the [Model Context Protocol](https://modelcontextprotocol.io/) over stdio (preferred) or local HTTP. **WASM is removed from MS-5 scope entirely** and explicitly punted to "v2 if a 3rd-party marketplace materialises".

**Why MCP, not WASM:**

| Dimension | MCP processes (CHOSEN) | WASM (REJECTED for v1) |
| --------- | ---------------------- | ---------------------- |
| Adapter language flexibility | any language with an MCP SDK (Python, TS, Rust, Go, C# — official SDKs) | only languages with WASI maturity (Rust, AssemblyScript, Go-via-tinygo) |
| 3rd-party SDK use | direct (Google Calendar SDK, Microsoft Graph SDK, etc.) | hand-port or HTTP-shim every SDK |
| Sandbox model | OS process isolation + cgroups (Linux), Job Objects (Windows), App Sandbox (macOS) — battle-tested | nascent WASI capability model + custom host imports — bug surface |
| Tool ecosystem | LSP-style mature; Claude Desktop, VS Code, Cursor all speak MCP | no production adapter ecosystem |
| Dev iteration loop | `python connector.py` debug-anywhere | toolchain-bound; debugger story weak |
| Resource enforcement | OS cgroups CPU%, RSS cap, fd limits, network namespace | WASM gas + memory limit (less granular) |
| Hot reload on adapter update | `kill + spawn` < 100ms | re-instantiate module; faster but irrelevant in practice |
| Future re-evaluation | OS isolation sufficient until v2 | reconsider WASM if **untrusted 3rd-party marketplace** ships post-v2 |

**v1 IFL Runtime architecture (replaces "WASM dispatcher" in earlier diagrams):**

```text
                 K1 capability call
                       │
                       ▼
              ConnectorGateway (in K1)
                       │ (stdio / loopback HTTP)
                       ▼
             MCP Process Manager (in K1)
            ┌──────────┼──────────┐
            ▼          ▼          ▼
   google_calendar   notion     filesystem    ← each adapter is an OS subprocess
        (MCP)         (MCP)       (MCP)         spawned by the manager,
                                                isolated by OS sandboxing
```

**MCP Process Manager responsibilities** (`bridge/connector/mcp_process_manager.py`):

- Spawn / supervise / restart / kill MCP child processes (one per active adapter manifest).
- stdio transport (preferred): JSON-RPC over child's stdin/stdout per MCP spec.
- Loopback HTTP transport (fallback for adapters that need it): unique loopback port per child, never bound to non-loopback interface.
- Per-adapter OS sandbox enforcement:
  - **Linux:** spawn under `systemd-run --scope --user --property=MemoryMax=512M --property=CPUQuota=50% --property=NoNewPrivileges=yes --property=ProtectSystem=strict --property=PrivateNetwork=...` (PrivateNetwork=yes for read-only adapters that don't need outbound; PrivateNetwork=no for ones that do).
  - **macOS:** spawn under `sandbox-exec` with a per-adapter `.sb` profile in `bridge/connector/sandbox_profiles/`.
  - **Windows:** spawn in an `AppContainer` Job Object with explicit capability SIDs.
- Health: each MCP child responds to `mcp/ping`; manager kills + respawns on 3 missed pings (15s window).
- Crash budget: ≥3 crashes in 60s → adapter quarantined; manifest marked `status: quarantined`; surfaces in `/healthz`.

**Manifest schema delta** (lands in MS-5):

- `delivery.transport`: add enum value `mcp_stdio` (and keep `https` for adapters that still need direct HTTPS — e.g. webhook receivers).
- New `mcp:` block when transport is `mcp_stdio`:

  ```yaml
  mcp:
    server_command: ["python", "-m", "connectors.google_calendar"]
    sandbox:
      memory_max: 512M
      cpu_quota_percent: 50
      network: outbound_only         # enum: none | outbound_only | full
      filesystem_read: ["~/.familyos/credentials/google_calendar/"]
      filesystem_write: []
    health:
      ping_interval_s: 5
      max_missed_pings: 3
  ```

**Removed from the v1 codebase:** any `wasm_dispatcher`, `wasm_runtime`, `wasmtime_*` references in design docs / diagrams. Update `architecture_diagrams/bridge/bridge_architecture_v2.mmd` `V2_*` clusters where they reference WASM (track in MS-5 grooming PR).

**Re-add criteria for WASM (post-v2):** open `0091-wasm-untrusted-adapter-runtime` ADR if and only if (1) external 3rd-party developer marketplace launches, (2) per-adapter resource overhead of OS process isolation becomes a measured bottleneck (>10% CPU per idle adapter), (3) attack surface from compromised SDK supply chain is unacceptable.

### D17 — IFL credential vault: **OS keychain primary, sqlcipher fallback**

**Decision:** v1 credential vault uses the **OS-native secure-storage API** as primary, with a sqlcipher-encrypted SQLite fallback for environments where the OS API is unavailable (containers, headless servers).

| Platform | Primary store | Library |
| -------- | ------------- | ------- |
| macOS | Keychain Services | `keyring` package (mature, py-objc backed) |
| Windows | Credential Manager (DPAPI) | `keyring` package (Windows backend) |
| Linux desktop | Secret Service (gnome-keyring / kwallet) | `keyring` package (SecretService backend) |
| Linux headless / Docker | sqlcipher fallback | `pysqlcipher3==1.2.*` |

**Why not K0-native encryption:** the K0 storage layer already encrypts at rest, but adapter credentials need to be retrievable by the adapter process (which runs under K1, not K0). Going through K0 for every credential read adds a round-trip and couples K1 boot to K0 availability (R1 violation). OS keychain is the right boundary.

**Vault API** (`bridge/connector/credential_vault.py`):

```python
class CredentialVault(Protocol):
    async def store(self, *, adapter_id: str, key: str, secret: str, metadata: dict | None = None) -> None: ...
    async def retrieve(self, *, adapter_id: str, key: str) -> str: ...           # raises VaultMiss if not present
    async def delete(self, *, adapter_id: str, key: str) -> None: ...
    async def rotate(self, *, adapter_id: str, key: str, new_secret: str) -> None: ...
    async def list_keys(self, *, adapter_id: str) -> list[str]: ...

class KeyringVault(CredentialVault): ...     # primary
class SqlcipherVault(CredentialVault): ...   # fallback
```

**Storage layout:**

- Service name (keyring) / table column (sqlcipher): `familyos.adapter.<adapter_id>`
- Key: arbitrary string (typically `oauth.refresh_token`, `oauth.access_token`, `api_key`, `webhook_secret`).
- Secret: opaque bytes, base64url-encoded if non-UTF-8.

**Selection logic at boot:**

```python
def select_vault() -> CredentialVault:
    if os.environ.get("FAMILYOS_VAULT_BACKEND") == "sqlcipher":
        return SqlcipherVault(path=Path.home() / ".familyos" / "credentials.db",
                              key_source=_derive_key_from_user_passphrase())
    try:
        return KeyringVault()  # tries OS-native; raises if no backend
    except keyring.errors.NoKeyringError:
        log.warning("OS keyring unavailable — falling back to sqlcipher vault")
        return SqlcipherVault(...)
```

**sqlcipher key derivation:**

- Headless server: passphrase from `FAMILYOS_VAULT_PASSPHRASE` env var (operator-supplied at boot via systemd `LoadCredential`).
- Docker / dev: prompt at first run; cache to memory only (passphrase re-required on restart).
- Never derived from machine-id alone (anyone with disk access could replay).

**Audit:** every `retrieve()` logs `{"event": "vault_read", "adapter_id": ..., "key": ..., "caller_pid": ..., "ts": ...}` to a write-only audit log at `~/.familyos/vault_audit.log`. Rotated daily, retained 90 days.

**No remote vault in v1** — explicitly rejected (Vault, AWS Secrets Manager, GCP Secret Manager). Adds external dependency, complicates offline-first story (R5), and isn't needed for a single-family deployment. Re-evaluate when the home-K0 box ships (v2): the home-K0 may run a HashiCorp Vault instance accessible to home-K1 instances on the LAN, replacing per-device keyring.

**Migration path** (v1 → v2 home-K0 vault):

- Vault API stays the same; only the impl changes. Adapters depend on the `Protocol`, not the impl.
- One-shot migration tool `python -m bridge.connector.vault_migrate --from keyring --to home_k0` reads all keys, writes them to the new backend, validates, deletes from old.

### D18 — Rate-limiter / circuit-breaker: **deferred to v1.1**

**Decision:** **defer** per-adapter rate-limiting and circuit-breaking to v1.1. v1 ships with two safety nets that are sufficient for the read-only Google Calendar adapter and any other read-only adapters in MS-5:

1. **OS-level resource caps** (D16 sandbox: cgroup CPU/memory/fd limits) — prevents a runaway adapter from starving the system.
2. **HTTP-client retry/timeout** in adapter code (every SDK has this) — prevents a stuck call from hanging the gateway.

**Why defer:**

- Read-only Google Calendar in v1 hits `events.list` at human-driven cadence (≤1 req/min/family) — far below any provider's rate limit.
- Premature rate-limiter / breaker = premature optimisation; tuning thresholds without real production traffic data produces wrong defaults.
- The MCP Process Manager can already kill + restart misbehaving adapters (D16 crash budget). That's a circuit-breaker at a coarser granularity.

**v1 surface preserved for v1.1 drop-in** (so deferral has no API churn):

- `ConnectorGateway.invoke(adapter_id, tool, args)` is the single chokepoint — v1.1 wraps every call with the limiter/breaker.
- Manifest schema reserves the field set without enforcing it:

  ```yaml
  rate_limit:                     # v1: ignored; v1.1: enforced
    requests_per_minute: 60
    burst: 10
  circuit_breaker:                # v1: ignored; v1.1: enforced
    failure_threshold: 5          # 5 consecutive failures
    timeout_s: 60                 # open for 60s
    half_open_probes: 1
  ```

  Fields validated by meta-schema in v1 (so authors learn the shape) but `ConnectorGateway` ignores them; `bus_yaml_aligned_with_registry` gate doesn't enforce.

**v1.1 implementation choice (when it lands):**

- **Library:** `aiolimiter==1.1.*` for token-bucket rate limiting (lightweight, asyncio-native, ~200 LOC); `purgatory==3.0.*` for circuit-breaker (asyncio-native, configurable strategies).
- **Hand-rolled rejected:** both libraries are small enough to audit, well-maintained, and avoid a class of subtle bugs (clock skew on token refill, half-open race conditions).
- **Decorator pattern:** wraps the dispatch path the same way `OnlineFirst[Port]` wraps command ports — derived from manifest fields at runtime construction; zero hand-coded conditionals in business code.

**v1.1 trigger criteria** (any one):

- Second adapter ships and second adapter has documented rate limits ≤120 req/min (e.g. Notion API: 3 req/sec).
- Production observability detects ≥1 incident/month of an adapter being throttled by upstream provider.
- 3rd-party adapter contributions land (would mean less-trusted code → defence-in-depth needed).

**Observability hooks ship in v1** so v1.1 has data:

- `bridge.connector.invoke.{requests_total, errors_total, latency_ms_histogram}` labelled by `adapter_id, tool, outcome`.
- These are the inputs the v1.1 rate-limiter/breaker tunes against.

### D19 — CA-bundle key generation ceremony

**Decision:** specified end-to-end in D3 ceremony (Shamir 3-of-5, air-gapped Tails USB, paper share distribution, share-holder runbook). The ceremony itself is closed by D3; D19 closes the **operational governance** around it that D3 deferred:

- **Share-holder identities** (the "who" D19 asked):
  - Share 1: CTO (long-term technical owner)
  - Share 2: CEO (long-term institutional owner)
  - Share 3: Head of Security (independent of engineering)
  - Share 4: External legal counsel (off-org, lawyer-client privilege protects against compelled disclosure)
  - Share 5: Bank-grade safe-deposit box at HQ city (institutional independence; emergency continuity if 1–4 unreachable)
  - **Threshold = 3 of 5** — any subset of 3 can reconstitute the seed.
  - Geographic spread: at least 2 of {CTO, CEO, HoS} must reside in different cities at any time; if violated, rebalance via a re-issuance ceremony.

- **Storage standards per share:**
  - Printed on paper using ink-jet (toner can flake) on archival-grade paper rated 100+ years.
  - Sealed in tamper-evident envelopes (Datacard EZTAB or equivalent; serial number recorded).
  - Stored in: home safe (CTO, CEO, HoS) — fireproof rated UL Class 350 1-hour minimum; envelope (legal counsel) — counsel's own safe; safe-deposit box (HQ) — bank-grade, dual-key access requiring CFO + COO co-signature to open.
  - **No digital copies anywhere** — share holders explicitly forbidden from photographing, scanning, retyping, or storing electronically.

- **Reconstitution governance** (the "when do we reach for it" D19 asked):
  - Required for: (1) signing a new IFL adapter manifest into the marketplace, (2) rotating `familyos_root_v1` to `familyos_root_v2` (planned 5-year cycle), (3) emergency revocation of a compromised intermediate CA.
  - Process: any 3 share-holders meet **in person** (no video) on an air-gapped machine; reconstitute seed via `ssss-combine`; perform the signing or rotation; destroy the reconstituted seed (`shred -uvz`); power off without network.
  - Logged in tamper-evident physical ledger held by HoS: date, share-holders present, purpose, output artefact SHA-256.
  - **No remote ceremonies** — the seed never crosses a network and never persists outside the air-gapped session.

- **Share rotation policy:**
  - Annual share holders attestation: each holder confirms custody to HoS in person or via signed letter.
  - Share holder departure (resignation, termination, death, incapacity): re-issuance ceremony within 30 days using remaining 3+ holders; old shares formally voided in the ledger; physically destroyed if recoverable.
  - 5-year mandatory full rotation: new `familyos_root_v(N+1)` keypair generated via D3 ceremony; old `vN` retained in `ca_bundle.json` with `status: deprecated`, `valid_until: <vN+1 ceremony date + 1 year>` for transition; deleted thereafter.

- **Loss / compromise procedure:**
  - **2 shares compromised:** safe (3-of-5 still requires the third share); rotate at next regular cycle or sooner if attacker likely to attempt threshold.
  - **3+ shares compromised** OR **3+ shares lost:** treat root as compromised; emergency rotation; revoke all manifests signed by `vN` via `revoked_at` field in `ca_bundle.json`; force re-sign of all active IFL adapter manifests within 7 days.
  - **All shares lost:** the FamilyOS root is unrecoverable. v1 product impact: existing manifests continue to verify (public key still in bundle); no new IFL adapter manifests can be signed. Plan: emergency new-root keypair generation; 30-day grace window where old + new bundles both ship; all adapter authors re-sign under new root; old root retired.

- **Auditor:** an independent external auditor (not on the share-holder list) reviews the ledger and attests to procedural compliance annually. Report archived; not published.

- **Documentation:** `docs/runbooks/familyos_root_v1_keygen.md` (D3) updated to reference this governance section. New runbook `docs/runbooks/familyos_root_governance.md` ships with v1, owned by HoS, includes the share-holder list (names not contact details — those held separately by HoS), reconstitution procedure, ledger template, departure protocol, rotation schedule.

- **Pre-MS-5 placeholder removal:** before MS-5 ships, the placeholder `ed25519_public_key: "PLACEHOLDER_REPLACE_BEFORE_MS5"` in `bridge/contracts/_meta/ca_bundle.json` is replaced with the real public key generated by the D3 ceremony. The PR doing the replacement is signed off by HoS + bridge-infra team lead per CODEOWNERS (D7).

### Updated D7–D19 status

### Must close before MS-3a ships (online command path)

| ID | Decision | Where in doc | Current state |
| --- | --- | --- | --- |
| D7 | Q9 PR-driven manifest workflow operationalised: CODEOWNERS for `bridge/contracts/`, PR template requiring `semantics:` block (R6) | Q9 + R6 | **Closed.** CODEOWNERS entries, PR template content, and `pr_template_compliance` gate specified in "MS-3a/3d/5 closure pack → D7" above; ships in MS-2.5 PR#2. |
| D8 | Q10 dual-publish window default value (currently 30d strawman) and the `dual_publish_until` field added to the meta-schema | Q10 | **Closed.** 30d default ratified; meta-schema delta (`dual_publish_until`, `supersedes`, `breaking_change_rationale`) specified in "MS-3a/3d/5 closure pack → D8"; new `dual_publish_window_active` CI gate added; rollover playbook committed as `docs/runbooks/contract_versioning.md`. |
| D9 | `OnlineFirst[Port]` decorator concrete implementation with `online_required` + `max_queue_age` enforcement | Q4 + Resolved Deferred item 3 | **Closed.** Source-level spec lives in MS-3b epic 3b.4; the production-grade behaviours (per-call decision delegation to `DegradedModeManager`, TTL-at-drain semantics, `OfflineError` payload, ordering semaphore, 5xx-while-online routing) pinned in "MS-3a/3d/5 closure pack → D9". |
| D10 | Q9 boot-fail-on-unbound-contract behaviour (which is also R1 mitigation) — exact error message and exit code so ops runbooks can match on it | Q9 + R1 | **Closed.** Exit code `78` (sysexits `EX_CONFIG`); machine-parseable single-line JSON + human-readable block format; 7-code taxonomy (`E_BRIDGE_BOOT_*`); `BridgeBootError(SystemExit)` impl sketch; runbook section per code committed as `docs/runbooks/bridge_boot_failures.md`. See "MS-3a/3d/5 closure pack → D10". |
| D11 | Whether `_generated/` is ignored for `git blame` (`.git-blame-ignore-revs`) so codegen commits don't pollute history | "MS-2.5 substrate" Decision 3 | **Closed.** `.git-blame-ignore-revs` shipped (CI auto-populates); `.gitattributes` marks `bridge/_generated/**` as `linguist-generated=true -diff`; dev-hook installer sets local `git config blame.ignoreRevsFile`; no CI gate (ergonomics-only). See "MS-3a/3d/5 closure pack → D11". |

### Must close before MS-3d ships (SSE)

| ID | Decision | Where in doc | Current state |
| --- | --- | --- | --- |
| D12 | SSE chunked-streaming client choice (`httpx-sse` strawman; alternative `aiohttp-sse-client`) | Q current state + R3/R11 | **Closed.** `httpx-sse==0.4.*` pinned; `sse-starlette==2.0.*` server-side; rationale + fallback contingency (`aiohttp-sse-client2`) documented in "MS-3a/3d/5 closure pack → D12". |
| D13 | SSE cursor-resume protocol on the wire: header name, format, K0 acceptance behaviour | R11 | **Closed.** Standard `Last-Event-ID` header carrying envelope ULID; 24h K0 replay buffer; 4-row server response table; `control.replay_gap.v1` synthetic envelope for misses; client persists cursor to `~/.familyos/sse_cursors.sqlite` (batched writes, 30d TTL). See "MS-3a/3d/5 closure pack → D13". |
| D14 | Backpressure policy: client buffer size, what happens when full (drop oldest? close stream? raise?) | MS-3d row | **Closed.** Block-and-close with cursor-resume on reconnect; queue maxsize `1000`, block timeout `30s`; HEALTHY → PRESSURED → STRESSED → CLOSING state machine; per-state metrics specified; tunable via `BRIDGE_SSE_QUEUE_MAXSIZE` / `BRIDGE_SSE_BLOCK_TIMEOUT_S` env vars. Drop policies explicitly rejected (audit invariants). See "MS-3a/3d/5 closure pack → D14". |

### Must close before MS-5 ships (IFL minimum)

| ID | Decision | Where in doc | Current state |
| --- | --- | --- | --- |
| D15 | First-adapter choice: Hue vs Google Calendar (the milestone says "one of" — product needs to pick one) | MS-5 row | **Closed.** **Google Calendar (read-only)**. Hue deferred to MS-5+1 / post-v1. Read-only OAuth scope, MCP server, multi-tenant credential vault exercise. See "MS-3a/3d/5 closure pack → D15". |
| D16 | WASM sandbox runtime choice (Wasmtime vs Wasmer vs Wazero-via-FFI) for the WASM dispatcher | Planned vision → IFL Runtime | **Closed.** **WASM removed from v1 scope.** v1 IFL Runtime = MCP Process Manager (OS-process isolation + cgroups/Job Objects/App Sandbox). Re-add criteria for WASM (untrusted 3rd-party marketplace, measured per-process overhead, supply-chain risk) documented as triggers for post-v2 ADR `0091-wasm-untrusted-adapter-runtime`. See "MS-3a/3d/5 closure pack → D16". |
| D17 | IFL credential vault implementation (sqlcipher? OS keychain? K0-native encryption?) | Planned vision → Connector Security | **Closed.** **OS-native keychain primary** (`keyring` package — Keychain / Credential Manager / Secret Service); **sqlcipher fallback** (`pysqlcipher3==1.2.*`) for headless/Docker; per-adapter storage namespacing; audit log; v1 → v2 home-K0 vault migration path defined. See "MS-3a/3d/5 closure pack → D17". |
| D18 | Rate-limiter / circuit-breaker library or hand-rolled | Planned vision → Connector Security | **Closed (deferred).** **Not in v1.** OS-level resource caps + SDK retry/timeout sufficient for v1 read-only adapters. v1 surface preserved (`rate_limit`, `circuit_breaker` manifest fields validated but ignored); v1.1 drops in `aiolimiter==1.1.*` + `purgatory==3.0.*`. Trigger criteria + observability hooks specified. See "MS-3a/3d/5 closure pack → D18". |
| D19 | The CA-bundle key generation ceremony: who holds the offline root, where it's stored, the M-of-N rule | Resolved Deferred item 4 | **Closed.** D3 ceremony (3-of-5 Shamir, Tails USB, paper shares); D19 governance overlay: 5 share-holders (CTO, CEO, HoS, external counsel, bank safe-deposit), annual attestation, in-person reconstitution, 5-year mandatory rotation, loss/compromise procedure, external auditor. New runbook `docs/runbooks/familyos_root_governance.md`. See "MS-3a/3d/5 closure pack → D19". |

### Must close before sync (L1/L2) ships in v1 — the Q15 tail

| ID | Decision | Where in doc | Current state |
| --- | --- | --- | --- |
| D20 | **Q15a**: final memory-scope schema; whether `shared(person_ids)` is one scope value or many; storage layout on the `memory_item` row | Q15a | Strawman |
| D21 | **Q15b**: where the family root key physically lives (parents M-of-N? home box? printed seed?) | Q15b | Three options listed; not chosen |
| D22 | **Q15b**: revoked-member memory retention (tombstone vs retain) | Q15b | Strawman “retain”; not ratified |
| D23 | **Q15c**: writer-side scope decomposition vs sync-layer redaction | Q15c | Strawman; needs sign-off from K0 P02 ingest team |
| D24 | **Q15d**: `parent_oversight: bool` policy default + audit-log requirements | Q15d | Strawman |
| D25 | **Q15f**: vector-clock requirement — which data classes mandate them, which ride bare LWW | Q15f + ADR-0050 contradictions list | Open contradiction lifted from ADR-0050 |
| D26 | **Q15g**: invite-link transport (deep link? email? QR?) and the cryptographic binding so an attacker can’t replay one | Q15g | Strawman flow; transport not pinned |
| D27 | **Q15h tail**: tombstone TTL value and late-write semantics on shared tools | Q15h tail | Open question |
| D28 | **Q14**: open the `0090-family-fabric-sync` ADR family (`0090a` L1, `0090b` L2, `0090c` L3 re-scope) | Q14 | Action item; PR not opened |

### Must close before v2 ships (home K0)

| ID | Decision | Where in doc | Current state |
| --- | --- | --- | --- |
| D29 | Q12 `EndpointResolver` concrete failover budget and network-change event source on each OS (Android `ConnectivityManager`, iOS `NWPathMonitor`, etc.) | Q12 | Pattern decided; per-OS impls not |
| D30 | Q13 cloud-relay outbox-and-replay protocol (write-conflict ordering between offline-K1-replay and home-K0’s own writes) | Q13 + R12 | Strawman (a) chosen; relay protocol open |
| D31 | Whether home K0 ships as a fixed appliance (hardware SKU) or BYO Linux box — affects security posture | Deployment topology v2 | Not in scope of bridge but unblocks Q13 |

### Operational / tail items (no milestone but must close before GA)

| ID | Decision | Where in doc | Current state |
| --- | --- | --- | --- |
| D32 | What `/healthz` exposes about bridge state (R1: `bridge.k0_reachable`, plus DEGRADED topics list per Resolved Deferred item 3) | R1 + Resolved Deferred item 3 | Listed; not implemented |
| D33 | Whether `bridge/contracts/` ever gets pulled out into a separate repo (“handle when it happens” — but “it happens” when K0 / K1 split repos) | Non-goals list | Explicitly punted |
| D34 | Per-record scope override grammar at L2 (Q15h delete / late-write / tombstone-TTL trio) | Q15h | Tail item |
| D35 | The exact JSON Schema document for the manifest YAML itself (vs the sketch in the substrate section) | “MS-2.5 substrate” Decision 1 | Sketch only |

### Decisions explicitly out of scope (do **not** close here)

For reference — if any of these come up in review, point at this list:

- K0 vs K1 boundary (settled, see Non-goals)
- Fabric vs Bridge ownership of capability invocation (settled)
- Backporting bridge to K0 as an importable package (intentionally not done in v1)
- 3rd-party IFL marketplace UX (post-MS-6)
- Multi-master CRDT between cloud and home K0 (rejected at Q13)
- K1→K1 cross-person mesh (rejected; not a concept after Q8 layer split)

## Manifest schema, codegen tool, vendoring — the MS-2.5 substrate

Three decisions that have been deferred long enough that they're now blocking MS-2.5 implementation. Decide here, in one pass, because they only make sense together.

### Decision 1: the manifest YAML *is* a JSON Schema document

The manifest file at `bridge/contracts/manifests/<topic>.yaml` is validated against `bridge/contracts/_meta/manifest.schema.json` (JSON Schema 2020-12). Every PR that adds or edits a manifest runs `jsonschema` against the meta-schema in CI; failures block merge. This kills the bikeshed: there is exactly one allowed shape, and the shape itself is reviewable as a single file.

The meta-schema enforces (sketch — fields, not exhaustive validation):

```text
required:    [topic, direction, owner_team, producer, consumer, schema, delivery, semantics, sla, versioning, status]
topic:       pattern '^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+\.v[0-9]+$'   # e.g. memory.write.v1
direction:   enum [k0_to_k1, k1_to_k0, k0_to_k0, k1_to_k1, device_to_k0, k0_to_device]
owner_team:  enum [k0, k1, bridge_infra]
status:      enum [proposed, experimental, active, deprecated, deferred]
delivery:
  transport:        enum [http, sse, in_process, e2ee_lan, https]
  ordering:         enum [strict, best_effort, causal]
  ack_required:     bool
  online_required:  bool
  endpoint_class:   enum [cloud_k0, home_k0, peer_k1, device_local]   # Q12
  partition_mode:   enum [k0_primary, k1_mesh_fallback, k1_mesh_only] # Q14
  max_queue_age:    duration                                          # R5
  codec:            enum [json, msgpack, cbor, flatbuffers]
semantics:
  idempotent:           bool
  duplicate_strategy:   enum [dedupe_by_envelope_id, last_write_wins, application_resolved]
  retention:            duration
sync:                                                                  # required iff direction in {k0_to_k0, k1_to_k1}
  layer:        enum [l1_family_memory, l2_family_tool_state, l3_intra_person_devices]
  tool_class:   enum [shared_family, shared_subset, personal]          # required iff layer == l2_*
schema:        path       # relative to bridge/contracts/, must point at an existing file
checksums:     {schema_sha256, manifest_sha256}                        # filled by CI, not authors
```

The payload schemas under `bridge/contracts/schemas/<topic>.v<N>.json` are *also* JSON Schema 2020-12. Two schema documents per contract: one validates the manifest, one validates the payload. The same `jsonschema` library covers both at runtime and in CI.

Why not Pydantic for the manifest itself: we want the manifest to be readable and validatable from any language (K0 may grow non-Python tooling around it; the home-K0 box may run a Rust supervisor). JSON Schema is portable; a Pydantic model isn't.

### Decision 2: codegen tool — `datamodel-code-generator`, generating Pydantic v2

[`datamodel-code-generator`](https://github.com/koxudaxi/datamodel-code-generator) (already an industry default for JSON-Schema-to-Python) generates Pydantic v2 models from each `schemas/<topic>.v<N>.json`. Output goes to `bridge/_generated/{k0,k1}/models/<topic>_v<N>.py`.

Beyond the payload models, we need three *non-Pydantic* generated artifacts. Those are produced by a single in-tree script `tooling/contracts/codegen.py` (no exotic templating — straight Jinja2 over the manifest YAML):

1. **Port protocols** — for each `(consumer.kernel, topic)` group, emit a `Protocol` class (`IKernelCommandPort`, `IKernelQueryPort`, etc.) with one method per topic. Methods are typed against the generated payload models.
2. **Client stubs** — for each `(producer.kernel, topic)` group, emit a thin `publish(envelope)` / `request(envelope) -> response` method bound to the manifest's `delivery.transport`. The transport itself stays hand-written in `bridge/core/transport/`; the generated client just dispatches.
3. **Handler registry** — for each `(consumer.kernel, topic)` group, emit a `register_handlers(runtime, impl)` function that wires the consumer kernel's hand-written impl into the runtime, with a compile-time check that every method declared in the protocol is implemented.

Why this split: `datamodel-code-generator` is excellent at types and terrible at orchestration. Letting it own the type layer and a small in-house script own the orchestration layer keeps the tool boundary clean and lets us swap either side later.

Why Pydantic v2 (not dataclasses, not attrs): runtime validation is non-negotiable for a cross-team contract — a K1 dev who passes the wrong-shape dict needs to fail at the bridge boundary with a useful error, not 4 frames deeper inside K0's gate. Pydantic v2 gives us that for free, and it's already in `requirements.txt` indirectly through FastAPI.

Alternatives explicitly rejected:

- **`quicktype`** — multi-language, but its Python output uses `dataclasses` + hand-rolled validation. We'd reimplement Pydantic's job.
- **Hand-rolled codegen** — would have to grow our own JSON-Schema-to-Python type translator (handling `oneOf`, `$ref`, `format`, etc.). Months of yak-shaving for a solved problem.
- **`openapi-python-client`** — assumes the contract is an OpenAPI doc. Forcing the bridge into OpenAPI's HTTP-centric worldview breaks the moment we need `direction: k1_to_k1` or `transport: in_process`.

### Decision 3: vendor `_generated/` AND run codegen in CI with a no-diff check

Both, not either. Reasons:

- **Vendor it** — so PR reviewers can see what changed in the generated code when a manifest changes. A 3-line manifest edit that produces a 200-line generated diff is a code-review signal we don't get if `_generated/` is gitignored. Also: green-field clones run without needing a codegen step before `pytest` works.
- **CI no-diff check** — a step `tooling/contracts/codegen.py --check` regenerates into a temp dir and `diff`s against the vendored `_generated/`. Any drift fails CI. This makes hand-edits to `_generated/` impossible in practice.
- **`_generated/` headers** — every generated file starts with `# AUTOGENERATED — DO NOT EDIT — regenerate with: python -m tooling.contracts.codegen` and a manifest-bundle SHA. Reviewers see the marker; greppers find it; humans don't try to fix things in the wrong layer.

This is the same pattern protobuf/grpc projects landed on after a decade of churn. Adopting the consensus saves us the decade.

### MS-2.5 exit criterion — the one test that proves the substrate works

MS-2.5 ships when this test is green end-to-end:

```python
# tests/bridge/contracts/test_ms_2_5_exit_criterion.py

def test_one_contract_round_trips_through_generated_code():
    # 1. The single live contract (memory.write.v1) exists in the registry.
    registry = ContractRegistry.load("bridge/contracts/")
    manifest = registry.get("memory.write.v1")
    assert manifest.status == "active"
    assert manifest.direction == "k1_to_k0"

    # 2. Meta-schema validates the manifest.
    registry.validate_against_meta_schema()  # raises on any drift

    # 3. Codegen output matches what is checked into _generated/.
    drift = run_codegen(check_only=True)
    assert drift == [], f"_generated/ is out of sync with manifests: {drift}"

    # 4. The generated K1 client and K0 handler are import-clean and bound
    #    to a real transport (no SinkBridgeClient fallback).
    from bridge._generated.k1.clients.memory_write_v1 import MemoryWriteV1Client
    from bridge._generated.k0.handlers.memory_write_v1 import register_handlers
    assert MemoryWriteV1Client.__transport__ == "http"

    # 5. Round-trip: generated K1 client -> in-process HTTP test transport ->
    #    generated K0 handler stub -> assertion that K0 received the envelope
    #    with the exact payload the K1 caller sent.
    k0_received: list[MemoryWriteV1] = []
    k0_runtime = BridgeRuntime.from_registry("bridge/contracts/", role=Role.K0)
    register_handlers(k0_runtime, impl=lambda env: k0_received.append(env.payload))

    k1_runtime = BridgeRuntime.from_registry(
        "bridge/contracts/", role=Role.K1,
        transport=InProcessHttpTransport(target=k0_runtime),
    )
    client = MemoryWriteV1Client(k1_runtime)
    payload = MemoryWriteV1(person_id="p_test", content="hello", scope="private")
    client.publish(payload)

    assert len(k0_received) == 1
    assert k0_received[0] == payload  # Pydantic equality, not dict equality

    # 6. CI gate from Q11: no K1 file imports k0.*, no K0 file imports k1.*.
    assert run_no_cross_kernel_imports_check() == []

    # 7. CI gate from R10: K1 bus dispatcher refuses cross-kernel-prefix
    #    topics that aren't in the registry.
    with pytest.raises(UnknownContractError):
        k1_bus.publish("memory.write.v1", payload)  # bypasses the registry
```

That single test exercises the meta-schema, the codegen, the vendor-vs-regenerate check, the runtime construction from manifests, the implementation-binding check, the Pydantic round-trip, and both CI wall-gates. If it passes, MS-2.5 is done and MS-3a can start.

## Iteration log

| Date | Author | Change |
| --- | --- | --- |
| 2026-05-05 | Pair (Prince + Copilot) | Initial reconciliation: verified current state by full bridge/k0/k1-kernel read; planned vision from `bridge_architecture.mmd` + `interkernel_fabric_layer.mmd`; eight architectural questions surfaced; opinionated strawman with `BridgeRuntime` + skinny ports + `OnlineFirst` decorator + MS-3a→MS-6 milestones. |
| 2026-05-05 | Pair | **Team-isolation principle introduced.** Bridge reframed as contract registry + mediation layer. K1/K0 are separate teams; only `bridge/contracts/` is shared. Q9 (declaration/discovery), Q10 (breaking-change arbitration), Q11 (CI gate enforcing the wall) added. Contract registry layout and manifest schema sketched. Runtime split into two symmetric `BridgeRuntime` instances, both built `from_registry()`. Strawman ports become codegen output, not hand-written. **MS-2.5** (registry + codegen scaffold) inserted before MS-3a. R6–R10 added. Inventory of every cross-kernel topic from `k0_source_of_truth_v2.mmd` + `p03_consolidation_architecture.mmd` + `k1_cognitive_architecture_skeleton.mmd` enumerated as the registry's initial population. |
| 2026-05-05 | Pair | **Deployment topology pinned down.** v1 = K1 on user devices (mobile/laptop/Alexa-class) talking to a single cloud-hosted K0 over public internet. v2 = K0 home server (Alexa-class box on home WiFi) becomes the truth, cloud K0 demotes to read-replica + away-mode write relay. Q1 strawman simplified (in-process both sides, both versions). Q8 reframed (LAN-direct K1→home-K0 is *endpoint selection*, not sync). Q12 (endpoint discovery + LAN/WAN failover) and Q13 (cloud K0 vs home K0 truth — strawman: home is truth) added. New manifest field `delivery.endpoint_class` introduced. R5 expanded (outbox is the *normal* write path on cellular). R11 (cellular reality / SSE survival) and R12 (split-brain on v2) added. |
| 2026-05-05 | Pair | **ADR-0050 family read end-to-end** (`0050`, `0050a`, `0050b`, `0050c-lan`, `0050c-multi-device`, `0050d`). Q8 fully rewritten: sync is now four distinct concerns (A K1→K0 writes, B K0→K1 events, C SessionState device-to-device, D K0 memory device-to-device); ADR-0050 covers C+D as K1↔K1 LWW + vector-clock CRDT mesh with **no cloud intermediary**. **This contradicts the v1 cloud-K0-first deployment** — surfaced as Q14. Q14 strawman (c): K0 is primary path; K1↔K1 mesh is partition-tolerance fallback only, dormant when any K0 endpoint reachable. New manifest field `delivery.partition_mode` with values `k0_primary` / `k1_mesh_fallback` / `k1_mesh_only`. New `direction: k1_to_k1` value added. Inventory expanded with K1↔K1 mesh topics: `k0bridge.p07.delta.v1`, `crdt.write_record.v1`, `p2p.sync.message.v1`, `device.handshake.v1` (all `status: deprecated` in v1 — code exists per ADR-0050c-lan COMPLETED but unreachable since devices have no local K0). R13 (ADR-0050 conflict) and R14 (two FlatBuffers schemas pre-existing the registry) added. Documented contradictions inside the ADR family: 0050d frontmatter REJECTED vs body Accepted, two files numbered 0050c, AES256-GCM vs ChaCha20-Poly1305 mismatch, 5s vs 30s loop transition window, vector-clock optionality unspecified. |
| 2026-05-05 | Pair | **Sync refactored into three coherent layers** after user pushback ("sync is about memory sharing, not silos"). Q8 fully rewritten around three-layer model: **L1 family memory sync** (K0↔K0 across persons in family, scoped by `private` / `shared(person_ids)` / `family` / `child_visible`) — **ships in v1**; **L2 family tool-state sync** (calendar event added on Mom's K1 → propagates to family calendar on every family K1, same channel as L1, `family.tool_state.delta.v1` envelope, per-tool ACL declared in IFL manifest as `sync.tool_class: shared_family \| shared_subset \| personal`) — **ships in v1**; **L3 SessionState K1↔K1 mesh** (one person's devices among themselves) — **deferred post-v1**, lifted from ADR-0050c-lan code at intra-person scope. Five-plane / four-concern framings retired. Q14 collapsed to a one-paragraph ADR action item: open `0090-family-fabric-sync` family with sub-ADRs `0090a` (L1), `0090b` (L2), `0090c` (L3 re-scope). Q15h added (per-tool ACL granularity, deletes/late-writes on shared tools). Registry inventory adds `direction: k0_to_k0` value with `sync.layer: l1_family_memory \| l2_family_tool_state` tag and 4 new topics: `family.memory.delta.v1`, `family.tool_state.delta.v1`, `family.membership.v1`, `tool_state.changed.v1`. L1+L2 ship `status: active` in v1; L3 stays `status: deferred`. R13/R14 framing softened (ADR-0050 isn't *wrong* — wrong-level for L1/L2, right-level for L3). |
| 2026-05-05 | Pair | **K0 deployment clarified: multi-tenant, partitioned by `(tenant_id, user_id)`.** Not one container per person. One K0 process per family, internally partitioned per family member. Q15e changed from "strawman (i) for v1" to a *decision* (multi-tenant per-family with internal partitions). Q8 L1 transport rewritten: v1 uses an in-process channel between partitions; v2 cross-host uses HTTPS to home-K0; same envelope shape, same signing, same scope-validation — the `OnlineFirst[Port]` decorator (Q4) selects transport per-contract. Deployment topology v1 description updated to call K0 "multi-tenant cloud-hosted". Critical invariant added: in-process delivery must not skip signing/scope-validation, both because the same code path runs cross-host in v2 and because the cryptographic check is the enforcement of family membership (not just a transport security concern). Strengthens the bridge design: contracts are unchanged, transport is per-contract pluggable, in-process L2 tool-state propagation runs sub-millisecond as a free bonus. |
| 2026-05-05 | Pair | **MS-2.5 substrate decisions locked.** New section "Manifest schema, codegen tool, vendoring" added. (1) Manifest YAML is itself a JSON Schema 2020-12 document validated against `bridge/contracts/_meta/manifest.schema.json` in CI — single shape, no bikeshed. Meta-schema enumerates the field set including the new `direction: k0_to_k0 \| k1_to_k1`, `delivery.endpoint_class`, `delivery.partition_mode`, `delivery.max_queue_age`, `sync.layer`, `sync.tool_class`. (2) Codegen tool: `datamodel-code-generator` for Pydantic v2 payload models; in-tree `tooling/contracts/codegen.py` (Jinja2 over manifest YAML) for port protocols, client stubs, and handler-registry wiring. Pydantic v2 chosen for runtime validation at the bridge boundary. `quicktype` / hand-rolled / `openapi-python-client` rejected with reasons. (3) `_generated/` is **vendored AND** CI runs `codegen.py --check` no-diff gate; every generated file carries `# AUTOGENERATED — DO NOT EDIT` header with manifest-bundle SHA. Pattern lifted from protobuf/grpc consensus. MS-2.5 exit-criterion test written as pseudo-code: one test that exercises meta-schema, codegen, vendor-vs-regenerate check, runtime construction from manifests, impl-binding check, Pydantic round-trip via in-process HTTP transport, and both Q11 / R10 CI wall-gates. Deferred list updated (manifest schema + codegen tool items removed). Next-pass agenda re-prioritized around remaining deferred items, ADR-0090 family, Q15 sub-questions, and MS-2.5 implementation. |
| 2026-05-05 | Pair | **All five deferred items closed + open-decisions inventory built.** New section "Resolved deferred items" decides: (1) `HttpBridgeClient` is a frozen-dataclass namespace bag of generated ports; callers depend on `IKernelCommandPort` etc., never on the fat client; lint forbids direct construction (must go through `BridgeRuntime.from_registry()`). (2) Outbox drain trigger = event-driven on `ONLINE_TRANSITION` (~50ms p99) **plus** 60s safety-net sweep **plus** immediate pass on startup; bounded batches (100 envelopes / 5s wall-clock); per-contract `delivery.drain_rate_per_sec` pacing knob; 5xx leaves envelope queued, 4xx routes to `dead_letter` table. (3) DEGRADED matrix is **auto-derived** from `delivery.online_required` + `delivery.max_queue_age`; CI gate `degraded-mode-derived-only` forbids hand-coded `if degraded:` outside `bridge/core/degraded.py`. (4) IFL signing CA: trust model committed now (`bridge/contracts/_meta/ca_bundle.json` ships embedded; v1 = exactly one CA `familyos_root_v1`; pre-installed adapters only); rotation = ship a release with new active + old deprecated 90d window; revocation = ship a release that downgrades to `revoked`; CRL distribution / marketplace explicitly post-MS-6. (5) `IBridgePort` migration: rename (b) → `IBridgeRuntime` and (c) → `IPlannerWritePort` in MS-2.5 PR#1 (pure rename); replace (a) bodies with codegen output one port per MS-3 sub-milestone; new CI gate `single-ibridge-port-definition` enforces "class IBridgePort" appears only under `bridge/ports/`. New section "Open decisions inventory" rolls up 35 still-open decisions (D1–D35) grouped by milestone gating: 6 must-close-before-MS-2.5, 5 before-MS-3a, 3 before-MS-3d, 5 before-MS-5, 9 before-sync-v1 (the Q15 tail), 3 before-v2, 4 operational tail. Decisions explicitly out of scope listed for review-time reference. Deferred list pruned to: IFL key-rotation operationalisation, full manifest meta-schema document, L2 per-record scope override grammar. |
| 2026-05-05 | Pair | **D1–D6 closed against actual codebase via three subagent walks.** Code-walk facts: (i) `bridge/core/signing.py` already ships Ed25519+HMAC, no key loader; (ii) K0 verifies envelope sigs via per-device `ProvisioningLedger.DeviceKey`, **no CA bundle exists** anywhere — manifest signing is a separate trust root; (iii) `k0/automation/compute_contract_checksums.py` and `contract_compatibility_checker.py` already exist and lift cleanly into `tooling/contracts/`; (iv) `k0/contracts/jsonschema/topics/memory_write.body.json` already $refs `k1/contracts/schemas/memory_writer/memory_atom.v2.schema.json` (MemoryAtom v2.2, 14 required fields) — the manifest just references this chain; (v) production topic is `"memory.write"` not `"memory.write.v1"` (cut-over is 2 PRs); (vi) no CI infra exists at all (no workflows, no pre-commit, no ruff/mypy config, no import-linter); (vii) `^from k0.` / `^from k1.` already returns zero hits in production `.py` files — the wall holds; (viii) two known `bridge.{core,sync}.*` import violations (memory_writer adapter, kernel adapter) need allowlist in MS-2.5 + remediation in MS-3a/MS-3b; (ix) the third `IBridgePort` lives at `k1/planner/ports/bridge_port.py` not `__init__.py:72` — rename mapping corrected; (x) Fabric's IBridgePort is a third distinct surface (`send_command`/`query`/`route_ifl`) renamed to `IFabricK0Port`. New section "MS-2.5 closure pack" specifies: (D1) full meta-schema JSON Schema 2020-12 doc with `additionalProperties: false`, conditional `required` for sync/signing via `allOf`, `semantics.description minLength: 40` enforcing R6; (D2) four Jinja2 templates + `datamodel-codegen --disable-timestamp` for deterministic output; (D3) bundle shape + 6-step Shamir 3-of-5 offline ceremony in air-gapped Tails environment, placeholder ships in MS-2.5 with real key replacement pre-MS-5; (D4) full `memory.write.v1.yaml` manifest reusing existing schema chain, reconciliation plan for un-suffixed `memory.write` alias; (D5) six gate scripts under `tooling/ci/gates/` with day-one expected results table (no_cross_kernel_imports green, bridge_not_imported with 2 known-violations allowlist, manifest_implementation_bound WARN until codegen exists, bus_yaml_aligned will fail loudly until proposed manifests cover every cross-kernel prefix), `import-linter` rejected with reason; (D6) `single-ibridge-port-definition` gate enabled `--warn-only` during MS-2.5 PR#1 then flipped to `--fail-on-violation`. D1–D6 marked **Closed** in the must-close-before-MS-2.5 table. |
| 2026-05-08 | Pair (Prince + Copilot) | **MS-2.5 closed; back-ported insights from `bridge/ARCHITECTURE.md` (operational-design doc).** ARCHITECTURE.md was rewritten to code reality: status flipped from "MS-2 Implementation" to "MS-2.5 CLOSED · MS-3a PENDING"; module layout (§6) rewritten against the shipped `bridge/` tree (`_generated/`, `handlers/`, `obs/`, `testing/`, `bus_guard.py`, `_topic_aliases.py`, `runtime.py`, `runtime_errors.py`, `contracts/manifests/`, `contracts/schemas/`, `contracts/_meta/`); `bridge/security/` package retired (capability-token pipeline lands in MS-5 alongside Connector Gateway, signing already in `bridge/core/signing.py`); BLAKE3 idem-key formula corrected to canonical code form `BLAKE3(topic ‖ \x00 ‖ canonical_json(body) ‖ \x00 ‖ device_id)` (earlier `(tenant_id, space_id, atom_id, minute(ts))` framing was speculative and is superseded); topic name `memory.write` → `memory.write.v1` with legacy alias; "always-offline" claim retired (in-process round-trip via `InProcessHttpTransport` is real and tested). New ARCHITECTURE.md §11 "Implementation Status & Roadmap" added with shipped/planned tags per file. **Insights now back-ported into this design + the implementation plan** (per § "Back-ports from operational architecture document" below): (1) four-mode deployment matrix (Dev Monolith / Device+Cloud / Full Local / Offline) — only `TransportConfig.base_url` differs; (2) priority tiers `CRITICAL/HIGH/NORMAL/LOW` with explicit per-port behavior table — extends Q4 OnlineFirst decorator; (3) `FeedbackEnvelope v1` full schema with `signal_class` + correlation + provenance blocks (supersedes bare `feedback.signal.p02.v1` topic stubs); (4) SSETraceEvent backpressure protocol (`level: ok/throttle/shed`, `lag_ms`, `pending_events`); (5) `CommandResponse(receipt_id, commit_ts, offsets, idem_key, obligations)` shape; (6) K0 endpoint table (5 endpoints + healthz/readyz/metrics, port 8080); (7) K0 does NOT sign responses (D-2.20) — no `SignatureVerifier` to be built; (8) Recall bundle types (`episodic`, `semantic`, `session`, `device`, `belief`, `graph`); (9) capability-token pipeline `TokenVerifier → AdapterVerifier → RateLimiter → CircuitBreaker → RequestRouter`; (10) credential storage matrix (Keychain/Keystore/libsecret/DPAPI + AES-256-GCM SQLite fallback); (11) JWT one-time pairing token (256-bit, 15-min, single-use) for device onboarding; (12) X25519+AES-GCM E2EE cipher locked now, `x25519_public_key` field present in provisioning schema from MS-5 (deferred impl to MS-6); (13) device registry lives in Bridge SQLite, not K0 (D-2.21); (14) `learning.feedback` topic does not exist — feedback only via Obs port `kind=feedback` (D-2.22). Diagram-correction checklist (ARCHITECTURE.md §9, 9 items) becomes an MS-3a precursor task. |
| 2026-05-10 | Pair (Prince + Copilot) | **MS-3b CLOSED — DEGRADED-mode online-first dispatch + LocalOutbox/DrainWorker shipped; chaos exit test green.** What shipped (verified by 8/8 CI gates green and 346/346 bridge+kernel-adapter tests pass): (1) Epic 3b.1 — `K0HealthChecker` (3-state ONLINE/DEGRADED/OFFLINE) with hysteresis-driven `HealthTransition` events on the in-process `EventBus`. (2) Epic 3b.2 — `DegradedMatrix` derived purely from manifest `delivery` semantics (online_required → raise; queueable → QUEUE_TO_OUTBOX); a new AST CI gate `degraded_mode_derived_only` keeps every degraded-policy branch confined to `bridge/core/degraded.py`, `bridge/core/health.py`, and `bridge/client.py` (escape hatch: `# noqa: degraded-mode — reason`). (3) Epic 3b.3 — `LocalOutbox` (sqlite, FIFO+priority, idempotency dedup, TTL prune, dead-letter on 4xx) + `DrainWorker` (event-driven via `HealthTransition`, configurable `batch_size`/`batch_wall_budget_s`/`safety_net_interval_s`, dead-letter on terminal 4xx with JSON-serialised body — fixed sqlite `dict not supported` bug). (4) Epic 3b.4 — `OnlineFirstClient` decorator wraps any per-contract publisher: ONLINE → inline POST with 5xx/connection-error fallback to outbox if matrix says queueable; OFFLINE → straight to outbox or `OfflineError(topic, current_state, behavior)` for online_required topics; ISO-8601 `delivery.max_queue_age` parsed once via `from_manifest`. New `HttpTransport.build_envelope_bytes` lets the decorator queue signed envelope bytes without touching the wire. (5) Epic 3b.5 — kernel/bridge wall fix: `k1/kernel/adapters/bridge_adapter.py` no longer imports `bridge.sync.local_outbox.LocalOutbox` directly; new factory `bridge.client.create_sink_bridge_client(outbox_path)` does the construction. The allowlist `tooling/ci/known_violations/bridge_imports.txt` is now empty (the last MS-3b kernel-adapter line removed); a regression test (`tests/k1/kernel/test_bridge_adapter_factory.py`) AST-asserts the import is gone. (6) Epic 3b.6 — chaos exit test (`tests/bridge/integration/test_outbox_drain_on_recovery.py`) drives a real `HttpTransport` against a toggleable `httpx.MockTransport`: 200 queueable + 5 online_required envelopes during a K0 outage → after `HealthTransition(OFFLINE→ONLINE)` the entire outbox drains (200/200) within a 20 s test budget (design target is 60 s). **Plan vs reality deltas**: (a) no MS-3b feature flags were needed in `bridge/contracts/_meta/feature_flags.yaml` (the entire mode is wired structurally; no kill-switch carve-outs). (b) `OnlineFirstClient.from_manifest` parses ISO-8601 durations directly (`PT…H?M?S?`) — no `isodate` dependency added per the implementation-discipline rule. (c) The decorator is constructor-composed (no monkey-patching): wiring lives in the runtime/factory path, not in generated code, so contract regeneration stays idempotent. |
| 2026-05-09 | Pair (Prince + Copilot) | **MS-3a CLOSED — real-HTTP bridge client landed, contract-bound, two layers of construction guard.** What shipped (verified by 7/7 CI gates green and 1102/1102 bridge+memory_writer tests pass): (1) `HttpBridgeClient` (in flat `bridge/client.py`, not a `bridge/client/` package — the plan's path was a legacy carryover) is a `__slots__`-bound namespace bag exposing per-contract publishers (`runtime.client.memory_write_v1.publish(MemoryWriteV1)`); the four other slots (`query`/`sse`/`obs`/`gateway`) reserved for MS-3b/c. (2) `HttpTransport.publish(*, topic, schema_uri, payload, …)` now mirrors `InProcessHttpTransport.publish` so the generated K1 clients (`MemoryWriteV1Client.publish` and successors) are transport-agnostic — this closed a critical gap where the generated clients would have hit `AttributeError` on real HTTP. (3) Construction guard is dual-layer per global rule on belt-and-braces: a private sentinel token `_RUNTIME_CONSTRUCTION_TOKEN` enforces at runtime, and a new CI gate `bridge_client_construction_via_runtime_only` AST-walks `bridge/`, `k0/`, `k1/` (excluding `bridge/client.py` and `bridge/runtime.py`) to fail on any `HttpBridgeClient(...)` call expression elsewhere. (4) MW wall violation cleared: `k1/memory_writer/adapters/bridge_command_adapter.py` no longer imports `bridge.core.envelope_builder.CommandEnvelope`; the batch surface was re-typed to plain dicts (matching the wire shape MW already passes). The allowlist `tooling/ci/known_violations/bridge_imports.txt` lost line 1 (only the MS-3b kernel-adapter line remains). (5) Topic alias shim **deleted**: `bridge/_topic_aliases.py` removed; `BridgeRuntime.dispatch()` lazy-import + alias call removed; the alias-resolution test in `tests/bridge/contracts/test_memory_write_v1.py` was rewritten to assert canonical-only behaviour. (6) K0 receiver `/k0/command.submit` was already substantially complete in `k0/ports/command.py` (router prefix `/k0`, full `CommandResponse` shape, `MinimalGate` + `IdempotencyLedger` + Ed25519 verify all wired) — Epic 3a.3 was satisfied by existing 32-test coverage in `tests/integration/test_command_port.py`, no duplicate tests added. **Plan vs reality deltas recorded for the next milestone**: (a) the producer-side aggregate `IKernelCommandPort` does *not* yet exist as a generated type — only `IMemoryWriteV1Port` does — so the design-doc shape "5-port composite" is realised as "namespace bag of per-contract publishers"; the umbrella may emerge in MS-4 adapter consolidation if the call-site ergonomics demand it. (b) `TransportConfig` already defaulted to port 8080 (the supposed bug was pre-fixed before MS-3a started). (c) `bridge/client.py` is and remains a flat module — promoting it to a `bridge/client/` package would be a churn-only refactor with no functional benefit and was rejected. |
| 2026-05-12 | Pair (Prince + Copilot) | **MS-3c CLOSED — typed paired-contract recall surface shipped; legacy hand-written query port deleted with no duplication.** What shipped (verified by 8/8 CI gates green, codegen `--check` reports no drift, and 543/543 bridge+concierge-services+tooling tests pass): (1) **Epic 3c.1 — paired contracts + codegen.** Two new manifests `recall.request.v1` (k1→k0, http, online_required, `paired_with: recall.response.v1`) and `recall.response.v1` (k0→k1, model-only emission target). Manifest schema gained a `paired_with` field with cross-manifest "partner-must-exist" validation in `tooling/contracts/manifest_loader.py`; the codegen tool (`tooling/contracts/codegen.py`) learned a paired-response code path so the generated K1 client exposes `request(payload) -> ResponseModel` (Pydantic-validated) plus a `publish` compat alias, and the K1 port Protocol exposes `request`. Per-kernel models stay isolated — `K0RecallRequestV1` and `K1RecallRequestV1` are distinct Pydantic classes for `isinstance` discipline. The `manifest_implementation_bound` gate now skips response-only topics. (2) **Epic 3c.2 — wiring + handler impl.** Hand-written K0-side impl `bridge/handlers/k0/recall_request_v1.py` translates the validated `RecallRequestV1` into the structural shape `k0.query.service.QueryAggregator` consumes, runs aggregation under the request's `max_latency_ms` / `max_results` budgets, and flattens driver bundles into `RecallHit` dicts (canonicalising `atom_id` from `payload_sha256` ‖ `wal_pos`, clamping `score ∈ [0,1]`, copying `selector_type` and `next_cursor`). `BridgeRuntime._build_k1_client` now branches on `recall.request.v1` to instantiate `RecallRequestV1Client` and additionally publishes a typed namespace bag at `runtime.query` (a `SimpleNamespace` whose `recall_request_v1` attribute is the same client) — the canonical K1 read seam. `HttpBridgeClient` gained a matching `recall_request_v1` slot. New domain façade `k1/concierge/services/recall_service.py` (`RecallService(query=runtime.query).recall(prompt, …) -> RecallResponseV1`) is the single place that knows how to assemble a `RecallRequestV1`; `build_recall_fn` (the legacy concierge tool seam) was rewritten to resolve a recall client from runtime / composite-client / typed-client and reuse the same generated models — no second copy of the request-building logic. (3) **Epic 3c.3 — dead code removed (no duplication, R10 honoured).** Hand-written `bridge/ports/query_port_protocol.py` (162 lines: `IKernelQueryPort`, `QueryEnvelope`, `RecallSelector`, `RecallItem`, `RecallBundle`) and `bridge/kernel/query_port.py` (the concrete `KernelQueryPort` posting to `/k0/query.recall`) were **deleted**; `bridge/ports/__init__.py` and `bridge/kernel/__init__.py` dropped their exports; `bridge/client.py` removed the `IBridgeClient.query` / `query_single` Protocol methods and `SinkBridgeClient` query stubs (offline callers detect the missing `recall_request_v1` slot and yield `[]`). `bridge/testing/stub_client.py` followed suit (the stub recall surface is now an attachable `recall_request_v1` attribute, not hand-rolled query methods). The integration test `tests/integration/concierge/test_recall_memory_e2e.py` and the legacy `tests/bridge/test_kernel_ports.py` / `tests/bridge/test_bridge_ports.py` were deleted; their coverage is restored — and strengthened — by the new `tests/k1/concierge/services/test_recall_service.py` (offline-empty + in-process round-trip through the real K0 handler) on top of the existing 9/9 contract tests in `tests/bridge/contracts/test_recall_request_v1.py`. **Plan vs reality deltas**: (a) the K0 recall handler **wraps** `QueryAggregator` rather than going through `POST /k0/query.recall`; the legacy HTTP route retains its QoS/policy enforcement for non-bridge callers (envelope-layer enforcement covers the bridge surface). (b) No new MS-3c feature flags were needed — the contract is wired structurally and there is no parallel legacy code path to gate. (c) The plan's `bridge/_generated/k0/handlers/recall_request_v1_impl.py` location was rejected: hand-written impls live under `bridge/handlers/k0/` (mirroring `memory_write_v1.py`) so regeneration of `_generated/` is never adjacent to business logic. (d) Concierge factory rewiring around `RecallService` was deliberately **not** done in MS-3c — `build_recall_fn` was retained as the seam so the `RecallMemoryAdapter` / `IMemoryPort` Protocol stays untouched and concierge regression coverage stays green; cut-over to a direct `RecallService` injection happens in MS-4. |
| 2026-05-13 | Pair (Prince + Copilot) | **MS-3d Epic 3d.1 + 3d.2 CLOSED — five K0→K1 SSE manifests live, real chunked SSE client with cursor resume + block-and-close backpressure shipped, all legacy hand-written SSE port code deleted with no duplication (R10 honoured).** What shipped (verified by 8/8 CI gates green, codegen `--check` reports no drift, **326/326** bridge tests pass, **25/25** new SSE manifest contract tests + **8/8** new SSE client unit tests pass): (1) **Epic 3d.1 — five SSE manifests + codegen SSE direction support.** New manifests under `bridge/contracts/manifests/`: `curiosity.intent.v1.yaml`, `k0.learning.advisory.v1.yaml`, `k0.proactive.signal.v1.yaml`, `p03.gap.detected.v1.yaml`, `p03.complete.v1.yaml` — all `direction: k0_to_k1`, `transport: sse`, `ack_required: true`, `online_required: false`, `retention: PT24H`, `versioning.strategy: additive_only_within_v1`, `breaking_change_requires: new_topic_v2_with_dual_publish_window_30d`. `p03.complete.v1` is the only `delivery.ordering: strict` topic (consolidation epoch boundary); the other four are `best_effort`. Schemas under `bridge/contracts/schemas/` define required envelope_id + per-topic discriminators (gap_id, advisory_id+signal_class, trigger_type+priority, gap_type, cycle_id+completed_at_utc_ms). The codegen tool (`tooling/contracts/codegen.py`) gained a `TopicView.is_sse` flag and SSE-direction templates: `contract_handler.py.jinja` emits a typed `<Topic>Subscriber` class with `async def subscribe(handler, *, cursor=None) -> AsyncContextManager[None]` and a `register_subscriber(runtime)` helper instead of the HTTP `register_handlers(runtime, *, impl)` shape; `contract_client.py.jinja` emits an `<Topic>Client.emit(payload)` method (publish-style for K0) instead of `publish/request`; `contract_port.py.jinja` emits paired `I<Topic>Port` (emit) + `I<Topic>Subscriber` (subscribe) Protocols. The aggregate kernel-level templates (`handler_registry.py.jinja`, `client_stub.py.jinja`, `port_protocol.py.jinja`) **filter SSE topics out** via `aggregate_topics = [t for t in topics if not t.is_sse]` in `render_kernel_files` — SSE has push-subscribe semantics, not request/dispatch, so impl-binding for SSE methods would be a category error. Manifest checksums populated via `python -m tooling.ci.gates.schema_checksum_stable --update`. **Legacy hand-written SSE deleted (R10):** `bridge/ports/sse_port_protocol.py` (`IKernelSSEPort`, `SSETraceEvent`, `SSEBackpressure`, `BackpressureLevel`) and `bridge/kernel/sse_port.py` (`KernelSSEPort`) **removed**; `bridge/ports/__init__.py` + `bridge/kernel/__init__.py` dropped exports; `bridge/client.py` removed `IBridgeClient.subscribe/ack/close_sse` Protocol methods and `SinkBridgeClient` SSE method stubs + `_empty_async_iter` helper; `bridge/testing/stub_client.py` followed suit; `tests/bridge/test_bridge_client.py` dropped six legacy SSE stub-shape tests (replaced with MS-3c+MS-3d marker comments). New contract tests in `tests/bridge/contracts/test_sse_manifests.py` (25 cases): meta-schema load, direction+transport+producer/consumer kernel assertions, Pydantic positive+negative validation per topic, codegen artefact-shape assertions (Subscriber on K1 handler / no `register_handlers` for SSE / no `.publish/.request` on SSE clients), kernel-aggregate exclusion, bus.yaml timing-mode resolution constrained to `RELAXED|BEST_EFFORT`. (2) **Epic 3d.2 — real chunked SSE client (`bridge/core/transport/sse_client.py`, ~430 LOC).** D12 transport: `httpx.AsyncClient.stream("GET", …)` with custom SSE wire-grammar parser (handles `id:`/`event:`/`data:` blocks, multi-line `data:`, comments/keepalives, ignores server-side `retry:`); `httpx-sse>=0.4.0` already in `requirements.txt`, `sse-starlette>=2.0.0` newly added for the K0 server-side endpoint that lands in Epic 3d.3. D13 cursor protocol: `Last-Event-ID: <ULID>` header sent on (re)connect from the persisted store; `CursorStore` (sqlite at `~/.familyos/sse_cursors.sqlite`, configurable via `FAMILYOS_HOME`) with batched writes (100 events / 5 s, force-flush on subscription stop); synthetic `event: replay-gap-detected` frame surfaces as `SSEReplayGapError` via the pump task — the pump **does not silently reconnect** on gap; the consumer must trigger corrective sync. D14 backpressure (block-and-close, drop policy explicitly rejected): internal `asyncio.Queue(maxsize=SSE_INTERNAL_QUEUE_MAXSIZE_DEFAULT=1000)`, env-overridable via `BRIDGE_SSE_QUEUE_MAXSIZE`; state machine `HEALTHY` (queue<80%) → `PRESSURED` (≥80%) → `STRESSED` (full + blocked >5 s) → `CLOSING` (blocked >`SSE_BLOCK_TIMEOUT_S_DEFAULT=30 s`, env-overridable via `BRIDGE_SSE_BLOCK_TIMEOUT_S`); on timeout the pump raises `SSEBackpressureTimeoutError` (subclass of `SSETransportError`) and the subscribe context manager re-raises it on exit instead of swallowing — the runtime/caller must see the failure to perform reconnect-with-cursor. Reconnect backoff: `0.5 s … 30 s` exponential per `2^(attempt-1)`, jittered ±20%, unlimited attempts (`reconnect_max_attempts=None`). The `subscribe(*, topic, model, handler, cursor=None) -> AsyncContextManager[_TopicSubscription]` API takes a Pydantic model class so the consume loop validates each frame's payload before invoking the handler; malformed JSON is logged and the cursor advances (the wire is the source of truth — bad frames are bugs to investigate, not retry-loop fodder). **Surface kept transport-only**: the codegen-emitted `<Topic>Subscriber` class holds the typed seam (contract topic + schema URI + model); the `SSEClient` is generic over any Pydantic model. New unit tests in `tests/bridge/core/transport/test_sse_client.py` (8 cases): multi-event chunked stream pumps through typed handler; `Last-Event-ID` is sent from persisted cursor on (re)connect; cursor survives a fresh `CursorStore` instance pointing at the same SQLite file (cross-restart resume); `replay-gap-detected` synthetic event surfaces as `SSEReplayGapError`; backpressure force-closes after `block_timeout_s` with `SSEBackpressureTimeoutError` propagated through the context manager; state transitions `HEALTHY → PRESSURED` once queue ratio ≥ 80%; malformed JSON frame is skipped and cursor advances on the next valid frame; reconnect backoff stays bounded by `[SSE_RECONNECT_BACKOFF_MIN_S, SSE_RECONNECT_BACKOFF_MAX_S]`. **Plan vs reality deltas**: (a) the SSE-direction codegen branches were emitted purely as Jinja `{% if topic.is_sse %}` switches in the existing per-contract templates rather than introducing parallel `*_sse.jinja` template files — fewer files, no template-selection logic in `codegen.py`, generated output stays consistent with HTTP contracts. (b) the kernel-level `register_handlers` aggregate was made SSE-aware by **filtering at the Python layer** (`render_kernel_files`) rather than adding a per-topic Jinja skip; this keeps the templates simple and explicit. (c) `httpx-sse` was already present in `requirements.txt`; only `sse-starlette>=2.0.0` was newly added (server-side dep, used in 3d.3). (d) `pump` and `consume` task exceptions are now surfaced through `_TopicSubscription.stop()` (capturing the first non-cancellation exception and re-raising after cleanup) instead of being silently swallowed — this is essential for D14 block-and-close semantics: the runtime *must* see the timeout to reconnect with cursor. (e) malformed-payload handling advances the cursor by design — looping forever on a bad wire frame would be worse than skipping; producers are the source of truth. **Epic 3d.3 (K0 SSE endpoint with replay buffer + fanout) is not yet shipped**: the K0-side `<Topic>Client.emit` raises `NotImplementedError` until the replay-buffer wiring lands. |
| 2026-05-14 | Pair (Prince + Copilot) | **MS-3d Epic 3d.3 + 3d.4 CLOSED — K0 SSE endpoint with 24h replay buffer + in-process fanout shipped, runtime SSE wiring landed, end-to-end real-chunked-SSE integration test green with p99 < 200ms over 100 emits, cellular-handoff cursor resume verified. MS-3d complete.** What shipped (verified by 8/8 CI gates green, codegen `--check` reports no drift, **328/328** bridge tests pass — including 2 new integration tests; pre-existing `test_verify_rejects_tampered_signature` failure is unrelated and reproduces on stashed clean state): (1) **Epic 3d.3 — K0 SSE endpoint stack.** Four new modules under `k0/sse/` coexist with the legacy `k0/sse/server.py` + `/k0/sse.subscribe` route (untouched, R10 honoured — the new path is `GET /k0/sse/{topic}` per-topic, the legacy is multi-topic CSV-via-query-param): (a) `replay_buffer.py` — `SSEReplayBuffer` (sqlite, `journal_mode=WAL` + `synchronous=NORMAL`, schema `sse_replay_buffer(seq INTEGER PRIMARY KEY AUTOINCREMENT, topic, envelope_id, payload TEXT JSON, created_at REAL)` + `UNIQUE(topic, envelope_id)` + composite indexes); `append(*, topic, envelope_id, payload, created_at=None) -> tuple[int, bool]` returns `(seq, was_new)` so duplicate emits skip fanout (idempotent retry safe); `replay_after(*, topic, cursor, limit=None) -> Iterator[ReplayEvent]` with three explicit cursor semantics — `cursor=None` yields nothing (fresh subscriber starts live, mirrors W3C SSE "no Last-Event-ID = start now"), `cursor=""` replays the whole window (admin/test), non-empty cursor not in buffer raises `ReplayGapError`; `evict_expired(*, now=None)` for the retention sweep with `DEFAULT_RETENTION_S = 24*60*60` matching every SSE manifest's PT24H; `from_path(":memory:")` for tests, real path `~/.familyos/sse_replay.sqlite` in production; `threading.RLock` because eviction sweeps run from a periodic thread while the endpoint serves from the asyncio loop. (b) `fanout.py` — `SSEFanout` per-topic in-process broker with `dict[str, list[_Subscription]]` and `asyncio.Lock`; per-subscriber bounded `asyncio.Queue(maxsize=SSE_FANOUT_QUEUE_MAXSIZE_DEFAULT=1024)`; `publish(FanoutEvent)` is **synchronous** (`put_nowait`) and **never blocks the producer** — slow consumers hit `QueueFull` and are closed (their subscription's `closed` event flips), the buffer is the source of truth so they reconnect with cursor and replay. (c) `endpoint.py` — `build_router(*, replay_buffer, fanout, allowed_topics=None) -> APIRouter` with a single `GET /k0/sse/{topic:path}` route returning `EventSourceResponse(generator(), ping=15)`; reads `Last-Event-ID: <ULID>` header (D13), runs the replay phase first (`replay_buffer.replay_after(cursor=last_event_id)`), on `ReplayGapError` emits a single synthetic frame `event: replay-gap-detected / data: {"topic":..., "reason":"cursor older than retention"}` and closes (the K1 client maps this to `SSEReplayGapError` which surfaces to the consumer); then enters the live phase via `async with fanout.subscribe(topic) as sub:` polling `sub.queue.get()` with a 1 s timeout to interleave `request.is_disconnected()` checks for clean teardown. `allowed_topics` (optional) returns 404 for unknown topics rather than opening a stream against an empty buffer. (d) `emitter.py` — `K0SSEEmitter(replay_buffer, fanout)` with `async emit(*, topic, schema_uri, payload) -> str`; the order **append-then-publish** is essential (a crash between append and publish is recovered on the next K1 reconnect via cursor; a crash the other way would lose the event); duplicate `(topic, envelope_id)` is detected via `was_new=False` and skips the live fanout (no double-delivery on retry). (2) **Epic 3d.4 — runtime SSE wiring + EXIT integration test.** `BridgeRuntime._build_k1_client` now walks SSE manifests (`raw["delivery"]["transport"] == "sse"`) and, when a `transport.config.base_url` is bound, builds a shared `SSEClient(SSEClientConfig(base_url=...), http_client=transport.http_client)` once per K1 process, attaches it to `runtime._sse_client`, then dynamically imports each generated `bridge._generated.k1.handlers.<topic_module>` and calls `register_subscriber(runtime)` to populate `runtime.sse.<topic>` (the typed bag the codegen-emitted `_SSEBag` defines). `BridgeRuntime.bind_sse_emitter(emitter)` is the K0-side seam — only K0-role runtimes accept it; the codegen-emitted `<Topic>Client.emit` reaches through `runtime._sse_emitter`. `BridgeRuntime.stop()` now `await sse_client.aclose()` for clean shutdown. **EXIT criterion test (`tests/bridge/integration/test_curiosity_intent_v1_streams_e2e.py`)**: boots a real `uvicorn` server on a free localhost port (with a critical caveat — `httpx.ASGITransport` deadlocks against `sse-starlette.EventSourceResponse` because the `anyio.create_task_group()` holds the ASGI `__call__` open until the response generator exits, so the client never sees the response headers; this is a fundamental ASGITransport limitation, not a bug in our code), runs 100 `K0SSEEmitter.emit` → real chunked SSE → `runtime.sse.curiosity_intent_v1.subscribe(handler)` round-trips, asserts **p99 < 200ms** (typical observed: p50 ≈ 1–2 ms, p99 ≈ 10–20 ms on the dev machine — well under budget). The cellular-handoff sub-test verifies that emits during a forced-close window persist in the replay buffer and are delivered on reconnect via the cursor stored in the same `CursorStore` SQLite file across two `SSEClient` instances. (3) **K0 unit tests authored** (`tests/k0/sse/test_replay_buffer.py` + `test_endpoint.py`) per the plan's Epic 3d.3 test list (chunked content-type header, live publish reaches subscriber, `Last-Event-ID` replay+live interleave, unknown cursor → `replay-gap-detected` synthetic frame, unknown topic → 404, idempotent append on duplicate envelope_id, retention eviction, cross-thread append safety) — **not run** in this milestone because tests/k0 execution is gated by separate K0 integration infrastructure outside the bridge scope; the bridge integration test exercises the real K0 SSE stack end-to-end and is the authoritative verification for MS-3d. **Plan vs reality deltas**: (a) the integration test boots real uvicorn instead of using `httpx.ASGITransport` because the latter cannot stream long-lived SSE responses (sse-starlette's task group + ASGITransport's "wait for full response" semantics deadlock at the headers-send boundary). This is documented in the test module docstring and is the standard approach for streaming-endpoint tests. (b) `BridgeRuntime.bind_sse_emitter(...)` was added rather than auto-wiring K0 emitters from manifests — K0 deployment owns the buffer/fanout lifecycle and the wiring is a single explicit call, not implicit construction. (c) the K0 endpoint coexists with the legacy `/k0/sse.subscribe` route rather than rewriting it; the new path is per-topic with header-based cursor semantics, the legacy path stays as-is for any existing callers (R10 — no destructive rewrite of working code). (d) the dedup-skip in `K0SSEEmitter.emit` rides directly on `SSEReplayBuffer.append`'s `(seq, was_new)` tuple return rather than a separate "did we just insert?" check — single source of truth, race-free under the buffer's lock. **MS-3d milestone closed.** Next: MS-3e (Connector Gateway / capability-token pipeline) per the implementation plan. |
| 2026-05-15 | Pair (Prince + Copilot) | **MS-3e Epic 3e.1 + 3e.2 + 3e.3 + 3e.4 CLOSED — obs/feedback channel shipped end-to-end. K1 detectors (correction/validation/reformulation) emit typed wire envelopes through a generated obs client to `/k0/obs.emit`, K0-side `FeedbackEnvelope` validation + per-pipeline `FeedbackSchemaRegistry` accepts them, real-uvicorn integration test green for all three signal classes.** What shipped (verified by **8/8** CI gates green, codegen `--check` reports no drift, **365/365** bridge tests pass — 17 new obs-manifest contract tests + 3 new feedback-loop e2e tests, **34/34** new K1 detector unit tests pass; pre-existing `test_verify_rejects_tampered_signature` failure remains unrelated and reproduces on stashed clean state): (1) **Epic 3e.1 — obs transport in the manifest meta-schema + two new manifests.** `bridge/contracts/_meta/manifest.schema.json` gained `"obs"` as a third value of `delivery.transport` (alongside `http`, `sse`) and a new optional `delivery.obs_kind` enum field (`feedback | metrics | logs`). Two new manifests under `bridge/contracts/manifests/`: `feedback.envelope.v1.yaml` (`direction: k1_to_k0`, `transport: obs`, `obs_kind: feedback`, `online_required: false`, `max_queue_age: PT24H`, `retention: P30D`, `latency_p99_ms: 500`) and `observability.payload.v1.yaml` (same shape, `obs_kind: metrics`, `drain_rate_per_sec: 100`, `retention: P7D`). Schemas under `bridge/contracts/schemas/` mirror the K0-side Pydantic shapes: `feedback.envelope.v1.json` enforces `pipeline_id ^P\d{2,3}$`, `signal_class` 5-enum (OUTCOME/CORRECTION/IMPLICIT/EXPLICIT/VALIDATION), `extra: forbid` semantics, full `FeedbackCorrelation` $def with session/message/recall/response/event_ids/wal_positions/target_entity fields; `observability.payload.v1.json` uses an `allOf` `if/then` to enforce `kind=metrics → snapshot required`, `kind=logs → entries required`. **Codegen extended for the obs branch** (`tooling/contracts/codegen.py`): `TopicView` gained `obs_kind: str | None` and an `is_obs` property; `render_kernel_files` aggregate filter rewritten to `[t for t in topics if not t.is_sse and not t.is_obs]` (obs has fire-and-forget semantics — kernel-aggregate handler-registry / client-stub for obs would be a category error, mirrors the SSE rationale from MS-3d); the three per-contract Jinja templates gained `{% elif topic.is_obs %}` branches: `contract_client.py.jinja` emits `<Topic>Client` exposing `__transport__/__topic__/__schema_uri__/__obs_kind__` class attrs and `async def publish(payload)` that reaches through `runtime._obs_emitter.emit(topic=, kind=, schema_uri=, payload=)` (NotImplementedError if not bound), `contract_handler.py.jinja` emits a no-op stub (only `__topic__` + `__model__` — K0 dispatch lives inside `k0/ports/observe.py` keyed by inner `kind` field, no `register_handlers` is correct), `contract_port.py.jinja` emits a Protocol `I<Topic>Port` with the obs class attrs + `async def publish(payload) -> object`. Manifest checksums populated via `python -m tooling.ci.gates.schema_checksum_stable --update` (66 files generated under `bridge/_generated`, +6 vs MS-3d's 60). New contract tests in `tests/bridge/contracts/test_obs_manifests.py` (17 cases): meta-schema load, direction+transport+obs_kind+queueable+max_queue_age=PT24H assertions, Pydantic round-trip + `pipeline_id` pattern + `signal_class` enum + extra=forbid negative cases, raw JSON Schema `kind=logs/metrics` `allOf` enforcement, codegen artefact-shape (`Client.publish` exists, `__obs_kind__` set, no `.emit/.request`; handler stub has `__topic__/__model__` only, no `register_handlers/register_subscriber`; kernel-level aggregates **exclude** the obs methods). (2) **Epic 3e.2 — `ObsHttpEmitter` + runtime wiring + K1 detector layer.** `bridge/core/transport/obs_emitter.py` (~110 LOC) defines `IObsEmitter` Protocol + `ObsHttpEmitter(*, base_url, http_client=None, timeout=10.0)` with `async emit(*, topic, kind, schema_uri, payload) -> None` that POSTs `{"kind": kind, "body": payload.model_dump(mode="json", by_alias=True, exclude_none=True)}` to `f"{base_url}/k0/obs.emit"` with an `X-Bridge-Topic` header; the emitter accepts an optional shared `httpx.AsyncClient` (tracked via `_owns_client`) so it co-tenants with the existing `HttpTransport` connection pool when present and constructs its own when not — `aclose()` only closes if owned. Crucially the emitter **bypasses** `HttpTransport.publish` (signed envelope / gate / WAL machinery) — obs/feedback is unsigned fire-and-forget and forcing it through the signing path would be the wrong cost model (this is the single most important MS-3e design decision; it mirrors why SSE in MS-3d also got its own transport). `BridgeRuntime._build_k1_client` walks obs manifests (`raw["delivery"]["transport"] == "obs"`) and, when a `transport.config.base_url` is bound, builds a single shared `ObsHttpEmitter` per K1 process, attaches it to `runtime._obs_emitter`, then dynamically imports each generated `bridge._generated.k1.clients.<topic_module>` and locates its `<Topic>Client` class (by matching `__topic__` against the manifest topic — convention: codegen emits exactly one Client class per file), instantiates `client_cls(runtime=runtime)`, and populates a `runtime.obs.<topic_module>` `SimpleNamespace`. `BridgeRuntime.stop()` now `await obs_emitter.aclose()` if owned. **K1 detectors + emitter** (`k1/concierge/feedback/`, ~600 LOC): `context.py` — `ConversationContext` dataclass tracking `session_id/message_id/wal_positions/event_ids/recall_id/response_id/grounded_event_ids/last_user_message/last_bot_response`, `record_recall`, `record_response`, `record_user_message`, `record_bot_response` helpers, in-process `_CACHE` keyed by `session_id` with `threading.RLock` (Redis-swap point for multi-replica is a single function pair). `detectors/correction.py` — `CorrectionDetector` with 4 ordered regex patterns (strongest-first: explicit "no, X not Y" / mid-sentence "X, not Y" / "that's wrong" without replacement / "I never said X"), per-pattern confidence, returns `CorrectionSignal(pipeline_id="P02", signal_class="CORRECTION", original_content, corrected_content, raw_text, confidence, matched_pattern_index, correction_target, target_event_id, spans)`; falls back to `context.last_bot_response` for missing `original_content` and pulls `target_event_id` from `context.grounded_event_ids[0]`; rejects empty / whitespace / off-topic utterances. `detectors/validation.py` — `ValidationDetector` with separate positive (`yes/yep/right/correct/exactly/thanks/perfect/...`) and negative (`no/nope/wrong/incorrect/not quite/...`) regex; if both match the longer span wins (handles "no, that's right"); returns `ValidationSignal(pipeline_id="P08", signal_class="VALIDATION", polarity, raw_text, confidence, target_response_id, target_event_ids)`. `detectors/reformulation.py` — `ReformulationDetector(similarity_low=0.30, similarity_high=0.85)` token-set Jaccard between current utterance and `context.last_user_message` (stopword-stripped), accepts only if `lo < score < hi` (verbatim repeats and brand-new topics are rejected); confidence peaks at band centre and falls off; returns `ReformulationSignal(pipeline_id="P03", signal_class="IMPLICIT", similarity, prior_utterance, raw_text, confidence, target_response_id, target_event_ids)`. The token-set Jaccard is a deliberate dependency-free approximation of the embedding-cosine path documented in FEEDBACK.md K1 §5; swapping in `st_embedding(prev) · st_embedding(now)` is a one-line replacement at `_similarity` and does not change the public API. `emitter.py` — `FeedbackEmitter(runtime, *, tenant_id, space_id, source_component="concierge.feedback")` with three public methods `emit_correction(signal, *, context)`, `emit_validation(...)`, `emit_reformulation(...)` each shaping the per-pipeline payload (P02 → `extraction_quality="poor"` + `user_correction{field, expected, actual}` mirroring `k0/feedback/payloads.py::P02FeedbackPayload`; P08 → `retrieval_hit + user_relevance` mirroring `P08FeedbackPayload`; P03 → `feedback_type="SALIENCE_ADJUSTMENT" + salience_delta = -0.10*confidence (clamped) + was_retrieved=True + was_helpful=False + confidence` mirroring `P03FeedbackPayload`), assembling `FeedbackEnvelopeV1` (correlation block + provenance block + clamped priority + uuid feedback_id + signal_subtype), validating wire-side via the generated Pydantic model, then publishing through `runtime.obs.feedback_envelope_v1.publish(envelope)`. **Best-effort semantics** are explicit: every publish failure is logged and the function returns `False` rather than raising — feedback is queueable not blocking, the conversation flow must not break on transport failure (BRIDGE-MS-3e.0). New unit tests in `tests/k1/concierge/feedback/test_detectors.py` (34 cases): correction-accepts × 6 phrasings + correction-rejects × 6 phrasings + correction-target-attribution × 2 (grounded event vs response fallback); validation-polarities × 10 (positive + negative phrasings) + validation-rejects × 5 neutral utterances; reformulation accepts at partial overlap + rejects verbatim repeat + rejects new topic + rejects no-prior-message + constructor band validation. (3) **Epic 3e.3 — K0 plumbing left untouched (R10).** The pre-existing K0 stack already implements every piece of the K0-side ingestion pipeline: `k0/ports/observe.py` `POST /k0/obs.emit` route with `kind=feedback|metrics|logs` dispatch, full `FeedbackEnvelope` validation, `FeedbackSchemaRegistry` per-pipeline payload validation, `INSERT INTO st_feedback_signals (...)` with `payload_validation_status`/`payload_hash`/`event_timestamp`; `k0/feedback/{envelope,payloads,schema_registry,topics,worker,signals}.py` providing `FeedbackEnvelope` Pydantic + `P02/P08/P03FeedbackPayload` Pydantic + `_BUILTIN_SCHEMAS` dict + `FeedbackWorker` periodic poller dispatching to bus topics `feedback.signal.<pipeline>.v1`. **No K0 code was modified in MS-3e** — the bridge work is purely contracts + K1 emitter + integration test, exactly per the user's R10 invariant. (4) **Epic 3e.4 — feedback loop integration test (`tests/bridge/integration/test_feedback_loop_real_e2e.py`)**: three real-uvicorn round-trip tests (one per signal class) boot a FastAPI app on a free localhost port that mounts a `/k0/obs.emit` endpoint exercising the **real** K0 validation path (`FeedbackEnvelope.model_validate(body)` + `FeedbackSchemaRegistry.validate(envelope.pipeline_id, envelope.payload)` after lazy-registering the P02/P08/P03 builtin schemas via `P{02,08,03}FeedbackPayload.model_json_schema()`), then capture the validated envelope into a per-test list. The test runs the full K1 pipeline: `ConversationContext` setup → real detector invocation → `FeedbackEmitter` shaping → generated `FeedbackEnvelopeV1Client.publish` → `ObsHttpEmitter.emit` → real `httpx.AsyncClient.post` over TCP → uvicorn server → endpoint, asserting `kind="feedback"`, `X-Bridge-Topic: feedback.envelope.v1` header, full envelope shape (`pipeline_id`, `signal_class`, `tenant_id/space_id`, `source="K1"`), correlation propagation (`session_id`, `recall_id`, `response_id`, `event_ids`, `target_entity_type/id`), and per-pipeline payload shape. The test does NOT exercise the full K0 storage path (`st_feedback_signals` INSERT requires Postgres; that's covered by separate K0 integration tests outside the bridge scope) — this is the appropriate level of integration for a bridge contract test, where the contract scope is "K1 emits a wire-valid envelope to the K0 obs port", not "K0 persists it correctly". (5) **Bus.yaml** gained two new timing-mode entries: `feedback: RELAXED` (queueable but not strict-ordered) and `observability: BEST_EFFORT` (droppable); the `bus_yaml_aligned_with_registry` gate stays green because both prefixes are now declared. **Plan vs reality deltas**: (a) `transport: obs` was chosen as a new enum value rather than topic-prefix routing inside `HttpTransport` or hardcoded endpoint paths — cleanest separation, mirrors the SSE pattern from MS-3d, the codegen branch reuses the existing `{% elif %}` chain in the per-contract templates with zero new template files. (b) `ObsHttpEmitter` is a **separate transport** that bypasses `HttpTransport.publish`'s signed-envelope path — feedback/metrics is fire-and-forget and forcing it through signing/gate/QoS/WAL machinery would be the wrong cost model. (c) `observability.payload.v1` declares `obs_kind: metrics` statically in the manifest; logs would need a separate `observability.logs.v1.yaml` manifest variant if K1 ever needs to forward logs through a typed contract — kept simple for MS-3e. (d) The K1 detectors use **regex + token-set Jaccard** rather than pulling in an embedding model — production swap-point at `ReformulationDetector._similarity` is a single function. (e) The integration test deliberately does not exercise `connection_scope()` / Postgres / `st_feedback_signals` INSERT; the bridge contract scope ends at "K0 endpoint accepts and validates the envelope" and that is exactly what the test verifies through the real K0 validators. **MS-3e milestone closed. Next: MS-4 (adapter consolidation around `RecallService` + composite ports) per the implementation plan.** |
| 2026-05-16 | Pair (Prince + Copilot) | **MS-4 Epic 4.1 + Epic 4.2 + Epic 4.3 CLOSED — codec layer (json/msgpack/cbor) shipped, manifest-driven codec selection wired through codegen and `HttpTransport`, K1 adapter LOC budget gate added with current state baselined; MS-4 exit test green.** What shipped (verified by **9/9** CI gates green — including the new `adapter_loc_budget` — codegen `--check` reports no drift, **423/423** bridge+tooling tests pass; the pre-existing `test_verify_rejects_tampered_signature` failure remains unrelated and reproduces on stashed clean state): (1) **Pre-implementation audit (subagent-driven).** Two parallel `Explore` subagents verified plan-vs-reality. Plan deltas locked in before any code was touched: (a) the K1 adapter landscape is **12 files**, not the plan's 7 — `selfmodel`, `orchestrator` (×3), and `concierge` carry adapters not in the plan's table; `learning` has no adapter; `sessionstate` has 2 stubs; (b) **zero forbidden bridge-internal imports** survive in K1 adapters (the wall violations from MS-3a/3b are already cleaned), so the plan's "shrink adapters to thin shims" instruction is structurally moot — the residual work is *protect from regression*, not *delete*; (c) most large adapters are real domain-translation layers (`bridge_amendment_sync.py` 213 SLOC privacy-band E3 guards, `bridge_connection.py` 227 SLOC IFL routing+health, `model_gateway_bridge.py` 145 SLOC type translation) — collapsing them to 15-LOC re-exports would destroy real domain logic and is rejected; (d) the codec layer is fully unimplemented (`bridge/codecs/__init__.py` was a stub, `HttpTransport` hardcoded JSON, K0 ingress was JSON-only, `TopicView` had no codec field, all 11 manifests were `codec: json`, msgpack/cbor2 missing from requirements); (e) the meta-schema **already** had `delivery.codec: enum[json, msgpack, cbor, flatbuffers]` so only `codecs_allowed` and `codec_negotiation` needed to be added; (f) `import-linter` is not installed and the project uses custom AST gates instead — the plan's import-linter reference is aspirational; the existing `bridge_not_imported_from_kernels` gate already covers all 5 MS-4 forbidden internals (`bridge.core`, `bridge.kernel`, `bridge.sync`, `bridge.connector`, `bridge.codecs`, `bridge.adapters`) via prefix match. (2) **Epic 4.1 — codec library + per-manifest selection.** New package `bridge/core/codecs/` (~310 SLOC across 5 modules): `base.py` defines the `Codec` runtime-checkable Protocol (`name`, `content_type`, `encode(dict)→bytes`, `decode(bytes)→dict`) plus the wrapped-body helpers (`BODY_WRAPPER_CODEC_KEY="_codec"`, `BODY_WRAPPER_B64_KEY="_b64"`, `encode_wrapped_body`, `is_wrapped_body`, `decode_wrapped_body`) and the `CodecError` / `UnsupportedCodecError` types; `json_codec.py` wraps stdlib `json` with `sort_keys=True` + `separators=(",",":")` for canonical (signing-safe) determinism; `msgpack_codec.py` wraps `msgpack.packb(use_bin_type=True)` / `unpackb(raw=False)`; `cbor_codec.py` wraps `cbor2.dumps`/`loads` (RFC 8949). The four codec implementations enforce dict-at-top-level on decode (raises `CodecError` if a list/scalar arrives — protects downstream Pydantic validators). `registry.py` provides `CodecRegistry` (immutable after construction, registers all three by default; `flatbuffers` is intentionally `UnsupportedCodecError` until a real use case exists) with three lookup APIs: `get(name)` by codec name, `by_content_type(media)` by MIME type, `for_manifest(delivery)` (defaults to JSON when `codec` absent), `codecs_allowed(delivery)` (defaults to `[delivery.codec]` when `codecs_allowed` absent — fully backward-compatible with every pre-MS-4 manifest), and `for_negotiation(delivery, accept_header)` which honours an HTTP `Accept` header against the manifest's `codecs_allowed` list and falls back per `codec_negotiation` policy (`fixed` → raises `UnsupportedMediaTypeError` mapping to HTTP 406; `client_choice_in_allowed` → silently falls back to manifest default). The legacy stub at `bridge/codecs/__init__.py` was rewritten to re-export from `bridge.core.codecs` so prior import paths keep working — single canonical location going forward. **Wire-format invariant**: outer envelope stays canonical JSON because envelope signing canonicalisation depends on it; only the `body` field switches codec. When a non-JSON codec is in effect the body becomes `{"_codec": "msgpack"|"cbor", "_b64": <base64>}` inside the JSON envelope — JSON-safe so signing is untouched, codec output is recovered exactly via `base64.b64decode`. **Meta-schema additions** (`bridge/contracts/_meta/manifest.schema.json`): `delivery.codecs_allowed` (array of codec-name enums, minItems=1, uniqueItems=true; defaults to `[delivery.codec]` when absent) and `delivery.codec_negotiation` (`fixed | client_choice_in_allowed`). **Codegen wiring** (`tooling/contracts/codegen.py`): `TopicView` gained `codec: str = "json"`, `codecs_allowed: tuple[str, ...] = ("json",)`, `codec_negotiation: str = "client_choice_in_allowed"` fields populated from manifest delivery section in `_topic_view`; the two HTTP-shape branches of `contract_client.py.jinja` (paired-response and plain-publish) now emit `__codec__`, `__codecs_allowed__`, `__codec_negotiation__` class attributes and pass `codec=self.__codec__` into `transport.publish(...)` — generated clients carry the manifest-declared codec as a static class constant rather than runtime lookup. The `client_stub.py.jinja`, `handler_registry.py.jinja`, `port_protocol.py.jinja`, `package_index.py.jinja` aggregates were intentionally not changed; codec is a per-contract, not per-kernel, decision. **Transport upgrade** (`bridge/core/transport/__init__.py`): `HttpTransport.publish(*, …, codec="json")` is the new public surface; when `codec != "json"` it resolves the codec via the module-level `_DEFAULT_CODEC_REGISTRY`, calls `encode_wrapped_body` to produce the `{_codec, _b64}` shape, places it in the envelope's `body` field, and sends an `Accept: <codec.content_type>, application/json;q=0.9` header so K0 can negotiate. `post_command(envelope_json, *, accept="application/json")` now sets the `Accept` header explicitly and decodes responses by `Content-Type` (`application/msgpack` → `MsgpackCodec.decode`, `application/cbor` → `CBORCodec.decode`, `application/json` → `response.json()` for back-compat), so K1 callers never see raw bytes regardless of the codec K0 chose. `build_envelope_bytes` accepts the same `codec` kwarg for the outbox-queue path used by `OnlineFirstClient`. `InProcessHttpTransport.publish` accepts `codec` for signature parity but treats it as a no-op (the dispatcher app speaks JSON; codec round-trips are tested through real `HttpTransport`). **Dependencies**: `requirements.txt` gained `msgpack>=1.0,<2` and `cbor2>=5.6,<6` (`cbor2` was newly installed; `msgpack` was already present). **Tests**: `tests/bridge/core/codecs/test_codecs.py` (25 cases) covers per-codec round-trips, JSON canonicalisation determinism, dict-at-top-level enforcement, wrapped-body shape + JSON-survival + codec-mismatch detection, registry lookup + manifest defaults + Accept-header negotiation under both `client_choice_in_allowed` (silent fallback) and `fixed` (HTTP 406) policies. `tests/bridge/core/transport/test_codec_negotiation.py` (6 cases) covers `HttpTransport.publish(codec=...)` end-to-end with `httpx.MockTransport`: JSON path is byte-for-byte unchanged from MS-3a, msgpack/cbor wrap the body and set Accept, msgpack/cbor response bodies are decoded by Content-Type, unknown codec raises `UnsupportedCodecError`. **Codegen `--check` reports no drift** after the TopicView + template changes (66 generated files unchanged at the byte level; the only generated-output change is the addition of the three codec class attrs to existing HTTP-shape clients). (3) **Epic 4.2 — adapter discipline (re-scoped from "delete" to "regression-protect").** The plan's "<100 LOC total" target was incompatible with the audit's reality (1089 SLOC of legitimate domain logic across 12 production adapter files). Instead of deleting domain code, MS-4 locks the *current* state structurally: (a) **New gate `tooling/ci/gates/adapter_loc_budget.py`** (~150 SLOC) walks `k1/**/adapters/{bridge*,*_bridge*,*bridge,null_bridge*,model_gateway_bridge,mock_bridge_adapter}.py` (excluding `test_*.py` / `*_test.py`), counts SLOC via AST-aware stripping (blank lines, `#`-comments, module/class docstrings excluded; function docstrings kept because they are typically one-liners and easy to abuse), and enforces `PER_FILE_SLOC_CAP=250` (just above the largest current adapter — `bridge_connection.py` at 227 SLOC) and `TOTAL_SLOC_BUDGET=1150` (~6% above the audit total). The gate's failure messages explicitly point future contributors to `docs/development/bridge_adapter_pattern.md` for the constants-bump justification protocol. (b) **The existing `bridge_not_imported_from_kernels` gate already covers** the MS-4 forbidden-internals list — `bridge.core.envelope_builder`, `bridge.core.signing`, `bridge.sync.local_outbox`, `bridge.core.transport`, `bridge.connector.mcp_process_manager` are all matched by the gate's `_FORBIDDEN_PREFIXES` tuple (`bridge.core`, `bridge.kernel`, `bridge.sync`, `bridge.connector`, `bridge.codecs`, `bridge.adapters`). The audit confirmed zero violations across all 12 K1 adapters; no new gate is needed for that surface. (c) **Gate registered** in `tooling/ci/run_all_gates.py` as the 9th gate at enforcing severity. The aggregate-test `tests/tooling/ci/gates/test_each_gate.py::TestRunAllGates::test_exits_zero_when_all_green` was extended to expect the new gate name in the summary set. (d) **New design doc `docs/development/bridge_adapter_pattern.md`** (~80 lines) documents what an adapter is + isn't, the SLOC budget rationale, the budget-bump justification protocol, the 12-adapter MS-4 baseline table with per-file SLOC + role notes, and an authoring checklist for future adapters. (e) **Gate contract tests** (`tests/tooling/ci/test_adapter_loc_budget_gate.py`, 8 cases) cover SLOC counting (blank lines / module docstring / class docstring / function docstring / comments), test-file exclusion (`test_*.py` and `*_test.py` skipped even if matching a glob), per-file cap enforcement (synthetic over-budget fixture exits 1), total-budget enforcement (synthetic 6-file fixture exits 1), and a lock-in test asserting the real workspace passes at HEAD. **No K1 adapter file was modified in MS-4** — the adapters are already correct shapes (zero forbidden imports, reasonable SLOC); the gate captures and protects the reality. The plan's Epic 4.2 was reframed in the implementation, not abandoned. (4) **Epic 4.3 — exit-criterion test** (`tests/bridge/integration/test_ms4_exit.py`, 4 cases): `test_generated_client_carries_codec_constants` asserts a real generated client (`MemoryWriteV1Client`) exposes `__codec__`, `__codecs_allowed__`, `__codec_negotiation__` and they round-trip through `CodecRegistry.codecs_allowed` cleanly; `test_msgpack_publish_wraps_body_in_canonical_json_envelope` runs a full `HttpTransport.publish(codec="msgpack")` round-trip against `httpx.MockTransport` asserting outer envelope is canonical JSON with `sig`/`sig_alg`/`sig_kid`, body is `{"_codec":"msgpack","_b64":...}`, base64 decodes back to the original payload via `MsgpackCodec`, and the `Accept` header advertises both `application/msgpack` and `application/json` fallback; `test_adapter_loc_budget_gate_passes_at_head` invokes the gate as a subprocess against the real workspace and asserts exit 0; `test_adapter_loc_budget_gate_fails_when_over_budget` builds an over-budget fixture and asserts exit 1 with `"exceeds budget"` in stdout. **Plan vs reality deltas**: (a) **K0 ingress was deliberately not modified.** The plan called for K0 to negotiate codecs via Content-Type / Accept; the audit confirmed `k0/ports/command.py` does `await request.json()` and the path validates payload via `MinimalGate` payload-hash checks computed on canonical_json bytes. The K0-side body-decode step would require coordinating signing canonicalisation with body unwrap, which only matters for production manifests that actually opt into msgpack — none currently do. The codec plumbing is end-to-end testable without K0 changes: `HttpTransport.publish(codec="msgpack")` produces a wrapped-body envelope that K0's existing canonical_json + payload_hash path treats as opaque (exactly as the plan's wire-format invariant promised). The first manifest to flip to `codec: msgpack` in production will pull in the K0-side decode helper; until then, K0 stays JSON-only without breaking the codec contract. (b) **No production manifest was flipped to msgpack.** The plan suggested flipping `curiosity.intent.v1` to `codec: msgpack`; that manifest is an SSE topic (transport=sse), not HTTP, and the SSE path doesn't currently flow through `HttpTransport.publish` so flipping it would be a no-op at runtime. Codec selection is a per-topic readiness decision better made when a real bandwidth/latency need arises; MS-4 ships the contract surface. (c) **`bridge/codecs/` stub was rewritten to re-export from `bridge/core/codecs/`** rather than promoting it to be the canonical location, because the plan and the existing wall gate both reference `bridge.core.codecs` (`bridge.codecs` is in `_FORBIDDEN_PREFIXES`); single canonical path under `bridge.core.codecs`. (d) **`import-linter` was not installed.** The project uses custom Python AST gates (`tooling/ci/gates/`) and the existing `bridge_not_imported_from_kernels` gate already covers every prefix MS-4 needed forbidden, with a documented allowlist mechanism. Adding `import-linter` would be parallel infrastructure with no functional benefit. (e) **Adapter consolidation was inverted from "delete to <100 LOC" to "lock current state at 1150 SLOC budget".** The plan's table was authored when the K1 adapter landscape was hypothesised to be 7 thin shims; the audit revealed 12 domain-translation layers totalling 1089 SLOC, all wall-clean. The right action is regression-protection, not destructive shrinkage. The 12-adapter table in `docs/development/bridge_adapter_pattern.md` is the new canonical reference. **MS-4 milestone closed. Next: MS-5 (online bridge — see `bridge/codecs/__init__.py` historical stub that named MS-5 as the implementation milestone for the now-shipped codec layer; the actual MS-5 scope per the plan is the online-bridge LAN/cloud transport pluggability + connector gateway capability tokens).** |

### Back-ports from operational architecture document (2026-05-08)

The items below are now first-class design contracts. They were under-specified or absent in earlier passes of this design doc and have been added to the MS-3x milestones in [bridge_implementation_plan.md](bridge_implementation_plan.md). The operational specifics live in [bridge/ARCHITECTURE.md](../../../bridge/ARCHITECTURE.md); this section captures the design-level rationale.

#### Deployment-mode matrix (extends "Deployment topology — where K0 and K1 actually run")

The four-mode matrix is the **same code path**, the **same manifests**, the **same signing**, the **same idem-keys**. Only `TransportConfig.base_url` and the transport-adapter selection vary:

| Mode | Transport adapter | When | What changes |
|------|-------------------|------|--------------|
| Dev Monolith | `InProcessHttpTransport` (httpx ASGI, no socket) | local development, MS-2.5 round-trip tests | base_url unused; FastAPI dispatcher app embedded |
| Device + Cloud | `HttpTransport` (real httpx + uvicorn) | v1 production, K1-on-mobile → cloud K0 | base_url = `https://k0.familyos.io`, TLS |
| Full Local | `HttpTransport` (LAN target) | privacy-max / air-gapped | base_url = `http://192.168.1.100:8080` |
| Offline | `OnlineFirst[Port]` decorator → `LocalOutbox` (SQLite WAL) | unreachable K0 | base_url same as configured; `K0HealthChecker` reports OFFLINE |

This matrix is the design-level answer to Q1 (where the bridge runtime lives) and Q4 (offline state machine): the *transport* is per-contract pluggable, the *runtime* is mode-agnostic. The MS-3b `OnlineFirst[Port]` decorator (Q4) is the seam where the four modes converge.

#### Priority tiers (extends Q4)

Q4 introduced ONLINE/DEGRADED/OFFLINE. The design did not enumerate **what each port should do per priority** when degraded. ARCHITECTURE.md §4 supplies the table:

| Tier | Behavior when K0 unreachable | Manifest tag | Examples |
|------|------------------------------|--------------|----------|
| `CRITICAL` | Always operational locally — no K0 dependency | `delivery.priority_tier: critical` | IFL local-device commands (lights, locks) |
| `HIGH` | Read-write against local cache; sync on reconnect | `delivery.priority_tier: high` | SessionState LOCAL COLD |
| `NORMAL` | Queue in `LocalOutbox`, drain on reconnect | `delivery.priority_tier: normal` (default) | `memory.write.v1`, `session.snapshot.v1` |
| `LOW` | Drop silently; emit drop counter | `delivery.priority_tier: low` | telemetry, non-essential obs |

Manifest meta-schema gets a new `delivery.priority_tier` enum field. The MS-3b auto-derived DEGRADED matrix (D-resolved item 3) extends to consult this field. CI gate `degraded-mode-derived-only` continues to forbid hand-coded `if degraded:`.

#### `FeedbackEnvelope v1` schema (replaces bare `feedback.signal.p02.v1` topic stubs)

The earlier registry inventory listed `feedback.signal.p02.v1` and `feedback.signal.p08.v1` as opaque topics. ARCHITECTURE.md §3.4 gives the actual envelope shape:

```text
FeedbackEnvelope v1
├── feedback_id   : str (uuid)
├── pipeline_id   : P02 | P06 | P08
├── tenant_id     : str
├── space_id      : str
├── signal_class  : CORRECTION | VALIDATION | IMPLICIT | EXPLICIT | OUTCOME
├── signal_subtype: str
├── correlation
│   ├── session_id, event_ids[], wal_positions[]
│   ├── recall_id, target_entity_id
├── provenance
│   ├── source_message_id, recall_context_hash, feedback_timestamp (ns)
└── payload : P02FeedbackPayload | P08FeedbackPayload   # discriminated union
```

Feedback is **not** a command. It flows only through the Obs port (`POST /k0/obs.emit` with `kind=feedback`), per D-2.8 / D-2.22. The `learning.feedback` command topic is dead — never to be added to `outbox_routing.yaml`. MS-3e binds this envelope and registers `feedback.envelope.v1` as the canonical contract; the `pXX.v1` topic stubs become aliases or are deprecated.

#### SSE backpressure protocol (extends MS-3d)

ARCHITECTURE.md §3.3 + D-2.5 specify the backpressure fields that must ride on every `SSETraceEvent`:

```text
SSETraceEvent v1 (additions)
├── backpressure
│   ├── level          : ok | throttle | shed
│   ├── lag_ms         : int       # wall time between event emit and SSE send
│   └── pending_events : int       # depth of K0-side buffer for this subscriber
```

Client behavior:
- `level=ok` — normal consumption.
- `level=throttle` — slow consumption rate (yield more often, larger consumer batch sizes).
- `level=shed` — drop oldest local buffer entries to catch up; emit `bridge.sse.shed_total`.

K0-side: tracks `BackpressureMetrics(level, lag_ms, pending_events)` per subscriber (already exists in `k0/ports/sse.py`). Cursor persistence (D-2.6) is a SQLite table `(subscriber_id, topic, last_offset)` colocated with `LocalOutbox`. Reconnect resumes from last acked offset.

#### `CommandResponse` shape (extends MS-3a)

Earlier passes treated K0's command response as opaque. ARCHITECTURE.md §2.1 + D-2.20 fix it: `CommandResponse(receipt_id, commit_ts, offsets, idem_key, obligations)`. K0 does **not** sign the response (no signature field). `obligations` is opaque structured JSON (post-write actions K0 demands of K1, e.g. "cache invalidation for recall_id=…"). The generated K1 client must surface all five fields.

#### Capability-token pipeline (extends MS-5)

ARCHITECTURE.md §2.5 codifies the IFL request pipeline as a five-stage chain, every stage mandatory:

```
TokenVerifier → AdapterVerifier → RateLimiter → CircuitBreaker → RequestRouter
```

Each stage is a `Protocol`. Failed token = 401. Failed adapter check = 403. Rate-limited = 429. Circuit open = 503. Router selects the IFL adapter by manifest `direction: device_to_*` matching. This pipeline is the design-level home for capability tokens — separate from envelope signing (`bridge/core/signing.py`), which is **transport-level** integrity, not authorization.

#### Device-onboarding flow (extends Q15g bootstrap order)

Q15g asked "what's the onboarding flow"; ARCHITECTURE.md §10 + D-2.19 supplies it:

1. Admin opens K0 console → "Add Device for `<member_name>`".
2. K0 generates one-time JWT pairing token: 256-bit secret, 15-min expiry, single-use, claims `{tenant_id, space_id, device_role}`.
3. Token delivered as QR code or deep link.
4. New device generates Ed25519 keypair (signing) and X25519 keypair (E2EE, MS-6+) locally; private keys go to OS Keychain (never leave device).
5. Device `POST /k0/admin/device.provision { pairing_token, device_id, ed25519_public_key, x25519_public_key }`.
6. K0 validates JWT → writes `(tenant_id, space_id, device_id, roles, band, public_keys)` into `ProvisioningLedger`.
7. Bridge boots with `BridgeConfig(tenant_id, space_id, device_id)`.

Six-digit codes are explicitly rejected (1 M brute-force space). The `x25519_public_key` field ships in the provisioning schema **from MS-5**, even though E2EE itself is MS-6, to avoid a forced migration.

#### Credential storage matrix (extends MS-5)

| Platform | Primary store | Hardware backing |
|----------|--------------|------------------|
| macOS/iOS | Keychain Services | Secure Enclave (T2 / Apple Silicon) |
| Android | Android Keystore | TEE / StrongBox |
| Linux | `libsecret` / Secret Service | TPM 2.0 (if present) |
| Windows | DPAPI / Credential Manager | TPM 2.0 (if present) |
| Fallback | AES-256-GCM SQLite | PBKDF2 from hardware ID |

OAuth tokens for IFL adapters are **never** stored in environment variables on end-user devices. Bridge owns this responsibility — K0 has no `st_device_credentials` table (D-2.21).

#### Tenant / space concrete evidence

Q15e was decided multi-tenant per-family. ARCHITECTURE.md §8 (D-X.3) cites the K0 schema files that prove this is enforceable, not merely policy:

- `k0/db/alembic/versions_broken/0016_households.py` — `tenant_id` unique constraint on `households` table (1:1 family ↔ tenant).
- `k0/db/alembic/versions_broken/0017_people.py` — `people` row carries `(tenant_id, space_id)`; `space_id` is person OR contextual (`space_home`, `space_journal`, `space_work`).
- `k0/modules/space/resolve_visibility.py` — visibility resolution uses `(tenant_id, space_id)` at every K0 access path.

Cross-tenant leakage is therefore a code bug at the storage layer, not a deployment misconfiguration. Bridge in turn must carry `(tenant_id, space_id, device_id)` on every envelope (already does — `bridge/core/envelope_builder.py`).
