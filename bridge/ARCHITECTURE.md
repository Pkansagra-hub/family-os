# Bridge Architecture

> **Module:** `bridge`
> **Status:** MS-3a CLOSED · MS-3b PENDING
> **Last code-reality sweep:** 2026-05-09
>
> **What MS-3a shipped (verified by `tests/bridge/client/`, `tests/tooling/ci/gates/test_bridge_client_construction_gate.py`, all 7 CI gates green):**
>
> - `HttpBridgeClient` (`bridge/client.py`) — real-HTTP composite client, slots-bound namespace bag exposing per-contract publishers (`client.memory_write_v1.publish(MemoryWriteV1)`). Construction is restricted to `BridgeRuntime.from_registry` via a private sentinel token; the new CI gate `bridge_client_construction_via_runtime_only` enforces the same property at AST-walk time.
> - `HttpTransport.publish(*, topic, schema_uri, payload, …)` (`bridge/core/transport/__init__.py`) — builds a fully-signed K0 envelope via `EnvelopeBuilder`, POSTs to `/k0/command.submit`, raises `BridgeTransportError` on non-2xx. Matches the ASGI shape of `InProcessHttpTransport.publish` so generated K1 clients are transport-agnostic.
> - `BridgeRuntime.from_registry()` extended — when `role == K1` and a `transport` is bound, walks the active manifests and instantiates the generated client for each `status: active` contract; assigns the result to `runtime.client` and `runtime.command`.
> - First wall violation cleared (MS-3a Epic 3a.2): `k1/memory_writer/adapters/bridge_command_adapter.py` no longer imports `bridge.core.envelope_builder.CommandEnvelope`. The batch surface uses plain dicts; per-contract typed publishing flows through `HttpBridgeClient`. Allowlist line removed from `tooling/ci/known_violations/bridge_imports.txt`.
> - Topic alias shim removed (MS-3a Epic 3a.4): `bridge/_topic_aliases.py` deleted; `BridgeRuntime.dispatch()` no longer translates `memory.write` → `memory.write.v1`. Callers must supply the canonical versioned topic.
> - 7th CI gate added: `tooling/ci/gates/bridge_client_construction_via_runtime_only.py` (mode `fail`).
>
> **What MS-2.5 shipped (verified by `tests/bridge/contracts/test_ms_2_5_exit_criterion.py`):**
>
> - Contract registry under `bridge/contracts/manifests/` + `bridge/contracts/schemas/` + `bridge/contracts/_meta/` (meta-schema, feature flags).
> - Codegen toolchain under `tooling/contracts/` (datamodel-code-generator Python API, deterministic).
> - Vendored generated tree under `bridge/_generated/{k0,k1}/{models,handlers,clients,ports}/`.
> - `BridgeRuntime` + `HandlerRegistry` (`bridge/runtime.py`) — manifest-driven, fail-loud on unbound contracts.
> - First contract live: `memory.write.v1` round-trips end-to-end via `InProcessHttpTransport` (real httpx ASGI) → FastAPI dispatcher (`bridge/testing/dispatcher_app.py`) → hand-written impl in `bridge/handlers/k0/memory_write_v1.py` → K0 P02 ingest stub.
> - 6/6 MS-2.5 CI gates GREEN at `--fail-on-violation` against the real repo (`python -m tooling.ci.run_all_gates --repo-root .`).
> - `BridgeAwareLocalBus` proxy (`bridge/bus_guard.py`) — refuses `bus.publish(<bridge_topic>, …)` that bypasses the registry (R10 mitigation).
> - Observability primitives (`bridge/obs/metrics.py`): `bridge_runtime_up`, `bridge_memory_write_v1_*` counters + latency histogram.
>
> **What is still pre-MS-3b (NOT yet shipped, tracked in [bridge_implementation_plan.md](../docs/architecture/whiteboard_k1/bridge_implementation_plan.md)):**
>
> - Outbox + DEGRADED state machine (MS-3b).
> - Query / SSE / Obs / Feedback ports (MS-3c–3e).
> - Connector Gateway (MS-5) and LAN device sync (MS-6).
>
> The diagrams and prose below describe the **target architecture**. Each section now flags `[shipped]`, `[partial]`, or `[planned]` against the MS-2.5 close.

---

## 1. Deployment Topology

Bridge is **device-side, co-located with K1**. It is NOT a cloud component and NOT a K0 component.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DEVICE (Phone / Laptop / Hub)                │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │                          K1 PROCESS                           │  │
│  │                                                               │  │
│  │  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐  │  │
│  │  │  Concierge  │  │ MemoryWriter │  │   Orchestrator      │  │  │
│  │  │  (FSM+LLM)  │  │  (Pipeline)  │  │   (Planner+Fabric)  │  │  │
│  │  └──────┬──────┘  └──────┬───────┘  └──────────┬──────────┘  │  │
│  │         │                │                      │             │  │
│  │         ▼                ▼                      ▼             │  │
│  │  ┌─────────────────────────────────────────────────────────┐  │  │
│  │  │                    K1 INTERNAL BUS                      │  │  │
│  │  │              (Delta, Events, Commands)                  │  │  │
│  │  └──────────────────────┬──────────────────────────────────┘  │  │
│  │                         │                                     │  │
│  └─────────────────────────┼─────────────────────────────────────┘  │
│                            │                                        │
│                            ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                         BRIDGE                                  ││
│  │                (Cross-Kernel Security Gateway)                  ││
│  │                                                                 ││
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ ┌───────┐ ││
│  │  │ CMD Port │ │ QRY Port │ │ SSE Port │ │OBS Port │ │  IFL  │ ││
│  │  │ K1→K0    │ │ K1↔K0    │ │ K0→K1    │ │ K1→K0   │ │ BiDir │ ││
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬────┘ └───┬───┘ ││
│  │       │             │            │             │          │      ││
│  │  ┌────┴─────────────┴────────────┴─────────────┴──────────┴───┐ ││
│  │  │              SECURITY CORE                                 │ ││
│  │  │  CapabilityTokens · Signing · Bands · Audit · E2EE        │ ││
│  │  └────┬─────────────┬────────────┬─────────────┬──────────────┘ ││
│  │       │             │            │             │                 ││
│  │  ┌────┴─────────────┴────────────┴─────────────┴──────────────┐ ││
│  │  │              OFFLINE AWARENESS                             │ ││
│  │  │  HealthChecker · DegradedMode · LocalOutbox (SQLite WAL)  │ ││
│  │  └───────────────────────┬────────────────────────────────────┘ ││
│  │                          │                                      ││
│  └──────────────────────────┼──────────────────────────────────────┘│
│                             │                                       │
└─────────────────────────────┼───────────────────────────────────────┘
                              │ HTTPS / TLS
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         K0 CLOUD STACK                              │
│                                                                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ kernel   │ │ postgres │ │  neo4j   │ │ grafana  │ │prometheus│ │
│  │  :8080   │ │  :5432   │ │  :7474   │ │  :3000   │ │  :9090   │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                           │
│  │pgbouncer │ │  tempo   │ │alertmgr  │                           │
│  │  :6432   │ │  :3200   │ │  :9093   │                           │
│  └──────────┘ └──────────┘ └──────────┘                           │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.1 Why Device-Side

| Reason | Detail |
|--------|--------|
| **Latency** | LLM tool calls need sub-100ms port access. Network hop to a separate Bridge container adds 5-50ms per call. Co-located = in-process function call. |
| **Offline-first** | K1 must work without K0. Bridge owns LocalOutbox (SQLite WAL) for queuing commands when K0 is unreachable. If Bridge were cloud-side, K1 has no way to queue. |
| **Security boundary** | Bridge enforces capability tokens + band policy BEFORE anything leaves the device. Placing it cloud-side means unprotected traffic on the wire. |
| **IFL locality** | Connector Gateway talks to local devices (HomeKit, BLE sensors) via LAN. Bridge must be on the same network segment. |

### 1.2 Deployment Modes

| Mode | K1 | Bridge | K0 | Transport | Status |
|------|-----|--------|----|-----------|--------|
| **Dev Monolith** | `localhost` | `in-process` | in-process FastAPI dispatcher | `InProcessHttpTransport` (httpx ASGI, no socket) | **[shipped MS-2.5]** — used by `memory.write.v1` round-trip test |
| **Device + Cloud** | Device process | Device process | Remote server | `HttpTransport` (real httpx + uvicorn loopback in tests) | **[planned MS-3a]** |
| **Full Local** | Device process | Device process | Device Docker | `HttpTransport` (LAN target) | **[planned MS-3a]** |
| **Offline** | Device process | Device process | `UNREACHABLE` | `OnlineFirst[Port]` → `LocalOutbox` (SQLite WAL) | **[planned MS-3b]** |

Only `TransportConfig.base_url` and the transport adapter selection change between modes. Everything else (manifest registry, codegen output, runtime wiring, signing, idem-keys) is identical across all four modes — that property is what the contract substrate buys.

```python
# Dev Monolith
TransportConfig(base_url="http://localhost:8080")

# Device + Cloud
TransportConfig(base_url="https://k0.familyos.io", tls_verify=True)

# Full Local
TransportConfig(base_url="http://192.168.1.100:8080")

# Offline — same config, HealthChecker detects UNREACHABLE → LocalOutbox queues
```

### 1.3 Process Boundary

```
K1 Process
├── K1 Kernel (Concierge, MemoryWriter, Orchestrator)
├── Bridge (imported as python package, same process)
│   ├── 5 Ports (CMD, QRY, SSE, OBS, IFL)
│   ├── Security Core
│   ├── Offline Awareness (HealthChecker + LocalOutbox)
│   └── Codecs (JSON only — FlatBuffer deferred)
└── SessionState (SQLite, local to device)
```

Bridge is a **Python package import**, not a separate service. K1 calls `bridge.client.BridgeClient` directly. No IPC, no sidecar, no container boundary.

---

## 2. Port Architecture

Five ports define the complete K1↔K0 communication surface:

```
                    K1 COMPONENTS
                         │
        ┌────────┬───────┼───────┬──────────┐
        ▼        ▼       ▼       ▼          ▼
   ┌─────────┐┌──────┐┌─────┐┌───────┐┌─────────┐
   │CMD Port ││QRY   ││SSE  ││OBS    ││IFL      │
   │         ││Port  ││Port ││Port   ││Gateway  │
   │ K1→K0   ││K1↔K0 ││K0→K1││K1→K0  ││BiDir   │
   │ ACK'D   ││REQ/  ││PUSH ││1-WAY  ││        │
   │ WRITE   ││RESP  ││STRM ││telemetry│Devices │
   └────┬────┘└──┬───┘└──┬──┘└───┬───┘└────┬───┘
        │        │       │       │         │
        ▼        ▼       ▼       ▼         ▼
   ┌─────────────────────────────────────────────┐
   │            SECURITY CORE                    │
   │  Signing · Tokens · Bands · Audit           │
   └─────────────────────┬───────────────────────┘
                         │
   ┌─────────────────────┴───────────────────────┐
   │          OFFLINE AWARENESS                  │
   │  HealthChecker · DegradedMode · LocalOutbox │
   └─────────────────────┬───────────────────────┘
                         │
                    K0 ENDPOINTS
```

| Port | Protocol | Direction | K0 Endpoint | Purpose |
|------|----------|-----------|-------------|---------|
| `IKernelCommandPort` | `Protocol` | K1→K0 ACK'D WRITE | `POST /k0/command.submit` | Acknowledged writes returning `CommandResponse(receipt_id, commit_ts, offsets, idem_key, obligations)`: memory, session, beliefs, history, plans, IFL events, sync deltas |
| `IKernelQueryPort` | `Protocol` | K1↔K0 REQ/RESP | `POST /k0/query.recall` | Multi-selector recall bundles: episodic, semantic, session, device, belief, graph |
| `IKernelSSEPort` | `Protocol` | K0→K1 STREAM | `GET /k0/sse.subscribe` | Real-time push: memory.formed, learning.advisory, proactive.signal, sync.complete |
| `IKernelObsPort` | `Protocol` | K1→K0 ONE-WAY | `POST /k0/obs.emit` | Telemetry (metrics, logs) + feedback (FeedbackEnvelope for System 2 learning) |
| `IConnectorGatewayPort` | `Protocol` | BIDIRECTIONAL | IFL Runtime | ALL external traffic: devices, APIs, services, sensors via IFL adapters |

### 2.1 Command Port (Existing)

```
K1 Component
     │
     ▼
KernelCommandPort.submit(topic, body, schema_uri, band, trace_id)
     │
     ├── EnvelopeBuilder.build() ─── signs with Ed25519, adds idem_key (BLAKE3)
     │
     ├── HttpTransport.post_command(envelope_json)
     │       │
     │       ├── K0 ONLINE  → POST /k0/command.submit → CommandResponse(receipt_id, commit_ts, offsets, idem_key, obligations)
     │       └── K0 OFFLINE → raise TransportError
     │
     └── [on TransportError] → LocalOutbox.enqueue(topic, envelope_json, priority)
                                     │
                                     └── SQLite WAL → drain when K0 returns
```

**Command Topics:**

| Topic | Pipeline | Description |
|-------|----------|-------------|
| `memory.write` | P02 | Episodic memory from conversations |
| `session.snapshot` | Archive | SessionState checkpoints |
| `beliefs.archive` | Archive | Evicted beliefs from SessionState |
| `history.archive` | Archive | Evicted turn history |
| `plan.committed` | P02 | Planner Stage 4 committed plans |
| `ifl.*` | P02 | IFL inbound sensor/device data |
| `sync.delta` | P07 | CRDT device sync deltas |

### 2.2 Query Port (Planned)

```
K1 Component
     │
     ▼
KernelQueryPort.query(selectors[], space_id, max_latency_ms, fail_fast)
     │
     ├── QueryBuilder.build() ─── constructs QueryEnvelope
     │
     ├── HttpTransport.post_query(query_json)
     │       │
     │       ├── K0 ONLINE  → POST /k0/query.recall → RecallBundle
     │       └── K0 OFFLINE → raise TransportError
     │
     └── [on TransportError + fail_fast=false] → LocalCache fallback
```

**Query Selectors:**

| Type | Topic Pattern | Source | Description |
|------|---------------|--------|-------------|
| `episodic` | `memory.delta` | WAL position recall | Recent episodic memories |
| `semantic` | free-text query | pgvector similarity | Semantic memory search |
| `session` | `session.*` | SessionState history | Session context |
| `device` | `device.event.*` | IFL event history | Device sensor data |
| `belief` | archived beliefs | Belief store | Archived beliefs |
| `graph` | KG traversal | Neo4j | Knowledge graph queries |

### 2.3 SSE Port (Planned)

```
K0 kernel
     │
     ▼ (push)
GET /k0/sse.subscribe?topics=memory.formed,learning.advisory&cursor=<last_wal_pos>
     │
     ▼
SSEReceiver (httpx-sse / aiohttp-sse-client)
     │
     ├── Parse SSETraceEvent { cursor, topic, wal_pos, commit_ts, policy_stamp }
     │
     ├── EventRouter.dispatch(topic, event)
     │       │
     │       ├── memory.formed.v1         → MemoryWriter (refresh local cache)
     │       ├── k0.learning.advisory.v1  → Concierge (validated feedback signal)
     │       ├── k0.proactive.signal.v1   → Orchestrator (proactive trigger)
     │       ├── curiosity.intent.v1      → Concierge (curiosity agent)
     │       ├── k0.sync.complete.v1      → SyncManager (sync finished)
     │       └── cognitive.vector.stored.v1 → MemoryWriter (embedding indexed)
     │
     ├── SSEAcknowledger.ack(topic, wal_pos)
     │
     └── Backpressure: { level: ok|throttle|shed, lag_ms, pending_events }
              │
              ├── ok      → normal processing
              ├── throttle → reduce consumption rate
              └── shed    → drop LOW priority, HTTP 429 back-off
```

### 2.4 Observability Port (Planned)

```
K1 Component
     │
     ▼
KernelObsPort.emit(kind, body)
     │
     ├── kind=metrics  → TelemetryBuffer.add(snapshot)
     │                       └── flush every 30s → POST /k0/obs.emit
     │
     ├── kind=logs     → TelemetryBuffer.add(entries[])
     │                       └── flush every 10s → POST /k0/obs.emit
     │
     └── kind=feedback → FeedbackBuilder.build(FeedbackEnvelope)
                              └── POST /k0/obs.emit (immediate, no batching)
```

### 2.5 Connector Gateway (Planned)

```
K1 Orchestrator
     │
     ▼
ConnectorGateway.execute(adapter_id, action, params)
     │
     ├── TokenVerifier ─── validate CapabilityToken
     ├── AdapterVerifier ─── check FamilyOS CA signature
     ├── RateLimiter ─── per-adapter TokenBucket
     ├── CircuitBreaker ─── per-adapter failure isolation
     │
     └── RequestRouter → IFL Adapter
              │
              ├── HomeKitAdapter  → Apple HomeKit API
              ├── NestAdapter     → Google Nest API
              ├── TeslaAdapter    → Tesla Vehicle API
              ├── HealthKitAdapter→ Apple HealthKit
              ├── SonosAdapter    → Sonos Control
              ├── RingAdapter     → Ring Doorbell
              ├── MqttAdapter     → Generic MQTT
              └── FamilySyncAdapter → K0 P07
```

---

## 3. Envelope Schemas

### 3.1 CommandEnvelope

```
┌──────────────────────────────────────────┐
│            CommandEnvelope v1             │
├──────────────────────────────────────────┤
│ cognitive_trace_id : str (uuid)          │
│ tenant_id          : str                 │
│ space_id           : str                 │
│ topic              : str                 │
│ schema_uri         : str                 │
│ body               : dict                │
│ actor              : str                 │
│ device_id          : str                 │
│ band               : GREEN|AMBER|RED      │
├──────────────────────────────────────────┤
│ sig_alg            : Ed25519             │
│ sig_kid            : str (key id)        │
│ sig                : bytes (signature)   │
│ envelope_sha256    : str (integrity)     │
│ idem_key           : str (BLAKE3 dedup)  │
└──────────────────────────────────────────┘
```

### 3.2 QueryEnvelope

```
┌──────────────────────────────────────────┐
│            QueryEnvelope v1              │
├──────────────────────────────────────────┤
│ selectors[]                              │
│   ├── type   : episodic|semantic|session │
│   │            |device|belief|graph      │
│   ├── topic  : str                       │
│   ├── limit  : int                       │
│   ├── cursor : str (pagination)          │
│   ├── after  : int (timestamp ns)        │
│   └── query  : str (for semantic)        │
│ space_id       : str                     │
│ tenant_id      : str                     │
│ max_latency_ms : int (timeout)           │
│ fail_fast      : bool                    │
└──────────────────────────────────────────┘
```

### 3.3 SSETraceEvent

```
┌──────────────────────────────────────────┐
│           SSETraceEvent v1               │
├──────────────────────────────────────────┤
│ cursor       : str (opaque position)     │
│ topic        : str (event topic)         │
│ wal_pos      : int (WAL position)        │
│ commit_ts    : int (nanosecond epoch)    │
│ policy_stamp : str (policy version)      │
├──────────────────────────────────────────┤
│ backpressure                             │
│   ├── level          : ok|throttle|shed  │
│   ├── lag_ms         : int               │
│   └── pending_events : int               │
└──────────────────────────────────────────┘
```

### 3.4 FeedbackEnvelope

```
┌──────────────────────────────────────────┐
│         FeedbackEnvelope v1              │
├──────────────────────────────────────────┤
│ feedback_id   : str (uuid)               │
│ pipeline_id   : P02|P06|P08             │
│ tenant_id     : str                      │
│ space_id      : str                      │
│ signal_class  : CORRECTION|VALIDATION    │
│                |IMPLICIT|EXPLICIT|OUTCOME│
│ signal_subtype: str                      │
├──────────────────────────────────────────┤
│ correlation                              │
│   ├── session_id      : str              │
│   ├── event_ids[]     : str[]            │
│   ├── wal_positions[] : int[]            │
│   ├── recall_id       : str              │
│   └── target_entity_id: str              │
├──────────────────────────────────────────┤
│ provenance                               │
│   ├── source_message_id    : str         │
│   ├── recall_context_hash  : str         │
│   └── feedback_timestamp   : int (ns)    │
├──────────────────────────────────────────┤
│ payload : P02FeedbackPayload             │
│         | P08FeedbackPayload             │
└──────────────────────────────────────────┘
```

---

## 4. Offline Awareness

```
         HealthChecker (30s poll → GET /healthz)
              │
              ▼
    ┌───────────────────┐
    │  K0Availability   │
    │     Status        │
    ├───────────────────┤
    │ ONLINE            │──── All ports active, normal operation
    │ DEGRADED          │──── Partial failures, circuit breakers tripping
    │ OFFLINE           │──── K0 unreachable, full offline mode
    └───────────────────┘
              │
              ▼
    ┌───────────────────────────────────────────────────┐
    │           Degradation Policy Per Port              │
    ├────────────┬──────────────────────────────────────┤
    │ CMD Port   │ → LocalOutbox queue (SQLite WAL)     │
    │ QRY Port   │ → Local cache fallback               │
    │ SSE Port   │ → Reconnect loop with exp. backoff   │
    │ OBS Port   │ → Drop LOW priority, buffer HIGH     │
    │ IFL Gateway│ → Local devices ALWAYS work (no K0)  │
    └────────────┴──────────────────────────────────────┘

    Priority enforcement (offline):
    ┌──────────┬────────────────────────────────────────┐
    │ CRITICAL │ IFL local devices — always operational  │
    │ HIGH     │ SessionState LOCAL COLD — works offline │
    │ NORMAL   │ Memory writes — queued in LocalOutbox   │
    │ LOW      │ Telemetry — dropped silently            │
    └──────────┴────────────────────────────────────────┘
```

---

## 5. Security Core

```
    Inbound Request (from K1 or IFL)
              │
              ▼
    ┌─────────────────────┐
    │  CapabilityToken    │──── Verify issuer, subject, capabilities[], band, expiry
    │  Validator          │     Reject if expired or insufficient capability
    └─────────┬───────────┘
              │
              ▼
    ┌─────────────────────┐
    │  Envelope Signing   │──── Ed25519 signature on canonical envelope
    │  (Ed25519SHA512)    │     BLAKE3 idem_key for dedup
    └─────────┬───────────┘     ONE signing op (no request-level HMAC)
              │                 K0 does NOT sign responses (D-2.20)
              │
              │   Idem-key formula (code-reality, `bridge/core/envelope_builder.py`):
              │     idem_key = BLAKE3(topic || \x00 || canonical_json(body) || \x00 || device_id).hex()
              │   NOTE: differs from earlier prose draft `(tenant_id, space_id, atom_id, minute(ts))`.
              │   Honored: deterministic per (topic, body bytes, device); replays within retention
              │   collapse to a single committed receipt at K0 P02 ingest.
              ▼
    ┌─────────────────────┐
    │  Band Enforcement   │──── GREEN: public info
    │  (Privacy Bands)    │     AMBER: family-private
    └─────────┬───────────┘     RED: individual-private
              │
              ▼
    ┌─────────────────────┐
    │  Audit Logger       │──── Every operation logged
    │                     │     Structured events for compliance
    └─────────────────────┘
```

---

## 6. Module Layout

Reflects the **shipped tree** as of MS-2.5 close. `[shipped]` = code on disk + tests; `[planned]` = roadmap path under MS-3a/3b/3c/3d/3e/4/5/6.

```
bridge/
├── __init__.py                           [shipped]
├── ARCHITECTURE.md                       ← this file
├── README.md
├── client.py                             [shipped — thin facade; HttpBridgeClient lands MS-3a]
├── runtime.py                            [shipped] BridgeRuntime + HandlerRegistry, manifest-bound
├── runtime_errors.py                     [shipped] UnknownTopicError, ContractNotBoundError, ...
├── bus_guard.py                          [shipped] BridgeAwareLocalBus proxy (R10 mitigation)
├── _topic_aliases.py                     [shipped] {"memory.write": "memory.write.v1"} — pruned MS-3a
│
├── contracts/                            [shipped] the SOURCE OF TRUTH — both teams own this
│   ├── manifests/                        [shipped] one YAML per topic (memory.write.v1, k1.k0.sse.v1, ...)
│   ├── schemas/                          [shipped] JSON Schemas; thin $ref wrappers allowed (memory.write.v1.json)
│   ├── _meta/                            [shipped] meta-schema, feature_flags.yaml
│   └── command_port.protocol.yaml        [legacy — superseded by manifests/]
│
├── _generated/                           [shipped] codegen output, vendored, AUTOGENERATED header
│   ├── k0/{models,handlers}/             memory_write_v1.py, ...
│   └── k1/{models,clients,ports}/        memory_write_v1.py, ...
│
├── handlers/                             [shipped] hand-written impls OUTSIDE _generated/
│   └── k0/                               memory_write_v1.py → calls k0.pipelines.p02_write_ingest
│
├── core/                                 [shipped — partial; query/sse/health expand MS-3b–3d]
│   ├── envelope_builder.py               [shipped] CommandEnvelope build + BLAKE3 idem-key
│   ├── signing.py                        [shipped] Ed25519SHA512 + HMAC-SHA256 backends
│   ├── health.py                         [shipped — types only; HealthChecker lands MS-3b]
│   └── transport/
│       ├── in_process_http.py            [shipped] httpx ASGI — no socket; used MS-2.5 tests
│       └── http.py                       [shipped — class exists; production wiring MS-3a]
│
├── obs/                                  [shipped] Prometheus metrics + structured logs
│   └── metrics.py                        bridge_runtime_up, bridge_memory_write_v1_*
│
├── testing/                              [shipped] FastAPI dispatcher app for in-process tests
│   └── dispatcher_app.py                 build_app(*, runtime) → POST /bridge/v1/dispatch
│
├── ports/                                [shipped — Protocol shells; concrete impls MS-3a–3e]
│
├── kernel/                               [shipped — legacy stubs; replaced by _generated/k0/]
│   ├── command_port.py
│   ├── query_port.py                     [planned MS-3c]
│   ├── sse_port.py                       [planned MS-3d]
│   └── obs_port.py                       [planned MS-3e]
│
├── adapters/                             [shipped — K1-side adapter shims; consolidate MS-4]
│
├── connector/                            [planned MS-5] Connector Gateway + IFL
│
├── sync/                                 [shipped — local_outbox stub] [planned MS-3b: enriched]
│   └── local_outbox.py                   SQLite WAL queue (TTL + dead-letter land MS-3b)
│
├── codecs/                               [shipped — JSON only] [planned MS-4: msgpack/CBOR]
│
└── architecture_diagrams/                Mermaid diagrams (see Section 9 corrections)
    ├── bridge_architecture.mmd
    └── interkernel_fabric_layer.mmd
```

**Removed from earlier draft (do not recreate):**

- `bridge/security/` — capability tokens / bands / audit are folded into `bridge/core/signing.py` plus generated handlers; a separate `security/` package is YAGNI for v1. Capability-token pipeline lands in MS-5 alongside Connector Gateway.
- `bridge/contracts/ports.py` and `bridge/contracts/envelopes.py` — superseded by `_generated/k1/ports/` and `_generated/{k0,k1}/models/` produced from the registry. Hand-written contract types are forbidden by the `bridge_not_imported_from_kernels` gate.

**Tooling lives outside `bridge/`:**

```
tooling/
├── contracts/                            [shipped MS-2.5]
│   ├── codegen.py                        datamodel-code-generator Python API
│   ├── manifest_loader.py                load + meta-schema validation
│   ├── checksums.py                      schema_sha256 + manifest_sha256 stamping
│   └── templates/                        Jinja2 (StrictUndefined) — contract_client.py.jinja
└── ci/
    ├── gates/                            [shipped] 6 gates, all --fail-on-violation
    │   ├── no_cross_kernel_imports.py
    │   ├── bridge_not_imported_from_kernels.py
    │   ├── manifest_implementation_bound.py
    │   ├── schema_checksum_stable.py
    │   ├── bus_yaml_aligned_with_registry.py
    │   └── single_ibridge_port_definition.py
    └── run_all_gates.py                  orchestrator → CI exit code
```

---

## 7. Data Flow Summary

```
┌────────────────────────────────────────────────────────────────────┐
│                        K1 → K0 FLOWS                               │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  Memory Write ──→ CMD Port ──→ POST /k0/command.submit             │
│                       topic: memory.write.v1   [shipped MS-2.5]    │
│                       (legacy alias "memory.write" → v1; alias     │
│                        removed at MS-3a EXIT, see _topic_aliases)  │
│                                                                    │
│  Session Save ──→ CMD Port ──→ POST /k0/command.submit             │
│                       topic: session.snapshot.v1   [planned MS-3b] │
│                                                                    │
│  Recall Query ──→ QRY Port ──→ POST /k0/query.recall               │
│                       selectors: [episodic, semantic]              │
│                                                                    │
│  Metrics/Logs ──→ OBS Port ──→ POST /k0/obs.emit                  │
│                       kind: metrics | logs                         │
│                                                                    │
│  Feedback     ──→ OBS Port ──→ POST /k0/obs.emit                  │
│                       kind: feedback                               │
│                                                                    │
├────────────────────────────────────────────────────────────────────┤
│                        K0 → K1 FLOWS                               │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  memory.formed.v1      ──→ SSE Port ──→ MemoryWriter               │
│  learning.advisory.v1  ──→ SSE Port ──→ Concierge                  │
│  proactive.signal.v1   ──→ SSE Port ──→ Orchestrator               │
│  curiosity.intent.v1   ──→ SSE Port ──→ Concierge                  │
│  sync.complete.v1      ──→ SSE Port ──→ SyncManager                │
│  vector.stored.v1      ──→ SSE Port ──→ MemoryWriter               │
│                                                                    │
├────────────────────────────────────────────────────────────────────┤
│                      DEVICE FLOWS (IFL)                            │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  K1 Orchestrator ──→ IFL Gateway ──→ HomeKit / Nest / Tesla / ...  │
│  Sensor Data     ──→ IFL Gateway ──→ CMD Port ──→ K0 (device.event)│
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

---

## 8. Architectural Decisions

All decisions resolved by code analysis of K0 and K1 source.
Evidence references point to actual source files.

### Tenant & Space Model (Cross-Cutting)

| ID | Decision | Resolution | Evidence |
|----|----------|------------|----------|
| D-X.2 | K0 shared vs per-device | K0 is a **shared cloud instance** for the whole family. Each device is provisioned with `tenant_id` + `space_id`. | `k0/deploy/scripts/provisioning/provision_device.py` |
| D-X.3 | Tenant/space semantics | `tenant_id` = household/family (1:1 in `households` table, unique constraint). `space_id` = person within family OR contextual space (`space_home`, `space_journal`, `space_work`). Family onboards → admin adds members → each member gets a `space_id`. | `k0/db/alembic/versions_broken/0016_households.py` (tenant_id unique), `k0/db/alembic/versions_broken/0017_people.py` (person has tenant_id + space_id), `k0/modules/space/resolve_visibility.py` (person_dad, space_home examples) |

### Signing & Security

| ID | Decision | Resolution | Evidence |
|----|----------|------------|----------|
| D-2.1 | Signing algorithm | **Ed25519SHA512** for production, **HMAC-SHA256** for dev/test. Both already implemented as pluggable `SigningBackend` protocol. | `k0/security/crypto.py` (nacl Ed25519 verify), `bridge/core/signing.py` (HMAC + Ed25519 backends) |
| D-X.4 | Signing layers | **ONE** signing operation per envelope. `canonical_envelope()` excludes `sig` + `envelope_sha256`, then Ed25519 signs the canonical JSON. No separate request-level HMAC. | `k0/security/crypto.py` L30-55 (canonical_envelope), `k0/gate/__init__.py` (SIGNATURE_INVALID/SIGNATURE_MISSING) |
| D-X.1 | Bridge packaging | Bridge is a **Python package import** co-located with K1. The existing Dockerfiles are for K0 only. Bridge ships as `import bridge` inside the K1 process. | `Dockerfile` / `Dockerfile.gpu` (K0 only), `bridge/__init__.py` |

### Privacy Bands

| ID | Decision | Resolution | Evidence |
|----|----------|------------|----------|
| D-2.2 | Band count | **3 bands only**: `GREEN`, `AMBER`, `RED`. **BLACK does not exist on the wire**. The `command_envelope.json` schema enumerates exactly 3. All K0 provisioning validates 3 bands. If BLACK is needed later it is a K1-local concern only. | `bridge/contracts/schemas/command_envelope.json` (enum: GREEN/AMBER/RED), `k0/deploy/scripts/provisioning/provision_device.py` (validates 3 bands), grep for BLACK across all K0 → zero matches |

### Port & Transport

| ID | Decision | Resolution | Evidence |
|----|----------|------------|----------|
| D-2.15 | Health endpoint | **`/healthz`** (not `/health`, not `/k0/health`). Bridge `HealthChecker` must target this path. | `k0/kernel/app.py` (registers /healthz), `k0/ports/test_all_ports.py` |
| D-2.16 | K0 port | **8080**. Bridge `TransportConfig` default of 8000 is a **BUG** — must be fixed to 8080. | `k0/kernel/config.py` (KernelSettings.port=8080), all K0 scripts use 8080 |
| D-2.8 | Feedback path | Feedback goes **only via Obs Port** (`POST /k0/obs.emit` with `kind=feedback`). The `learning.feedback` command topic is legacy/unused — no handler exists in K0 command port. | `k0/ports/observe.py` L150-220 (feedback processing → st_feedback_signals), grep for learning.feedback in K0 command handlers → zero matches |
| D-2.13 | BridgeClient async | **Fully async** (`async def` on all port methods). K1 is already fully async. Bridge adapters use `httpx.AsyncClient`. | `bridge/adapters/` (existing httpx async pattern), K1 concierge is async throughout |

### SSE Port

| ID | Decision | Resolution | Evidence |
|----|----------|------------|----------|
| D-2.4 | SSE client library | **`httpx` + manual SSE parsing** (line-based `text/event-stream`). No external SSE library needed — K0 SSE is simple line protocol. | `k0/ports/sse.py` (SSETraceEvent is cursor+topic+wal_pos+commit_ts+policy_stamp — simple model) |
| D-2.5 | SSE shed behavior | K0 tracks `BackpressureMetrics` (level, lag_ms, pending_events). Bridge should **drop oldest** when backpressure level exceeds threshold, and **log shed count** to Obs Port. | `k0/ports/sse.py` (BackpressureMetrics model) |
| D-2.6 | SSE cursor persistence | **SQLite** (via existing `local_outbox.py` pattern). Persist `(subscriber_id, topic, last_offset)` so Bridge can resume after restart. K0 AckRequest requires subscriber_id + topic + offset. | `k0/ports/sse.py` (AckRequest model), `bridge/sync/local_outbox.py` (SQLite pattern exists) |

### Observability Port

| ID | Decision | Resolution | Evidence |
|----|----------|------------|----------|
| D-2.7 | Obs batching | **Configurable flush interval** (default 5s) + **max batch size** (default 50). Three payload kinds: `metrics` (ForwardedMetricsBuffer), `logs` (entries[]), `feedback` (FeedbackEnvelope). | `k0/ports/observe.py` (3 distinct kind handlers), `k0/feedback/envelope.py` (FeedbackEnvelope model) |

### Infrastructure & Deferral

| ID | Decision | Resolution | Evidence |
|----|----------|------------|----------|
| D-2.9 | ConnectorGateway | MS-2 = **skeleton only** (Protocol + `NotImplementedError`). MS-3 fills in IFL adapter logic. | Architecture diagrams show IFL as MS-3 scope |
| D-2.10 | FlatBuffer codec | **Deferred**. JSON-only for MS-2. FlatBuffer is an optimization for high-throughput device telemetry in MS-3+. | No FlatBuffer usage anywhere in K0/K1/bridge code today |
| D-2.11 | gRPC transport | **Deferred (YAGNI)**. HTTP+JSON for MS-2. gRPC only if latency measurements justify it. | No gRPC anywhere in codebase |
| D-2.12 | Device sync | **Entirely MS-6** scope. Bridge sync/ directory handles offline outbox only. Full device-to-device sync is P07. | `bridge/sync/local_outbox.py` (offline queue only) |
| D-2.14 | HouseholdProjection | **Lazy fetch on first use**, cached in memory. Not required at boot — avoids blocking startup if K0 is unreachable. | K0 households table structure supports query; Bridge should be resilient to offline boot |
| D-2.3 | Query cache | **LRU in-memory cache** with TTL (default 60s). Optional — disabled by default in MS-2, tunable later. | No caching in current bridge code; K0 query.recall is stateless |
| D-X.5 | Bridge test strategy | **Unit tests with mocked ports** for MS-2. Integration tests with Docker K0 deferred to MS-3 CI pipeline. | Existing bridge tests use mocks; Docker compose for K0 is complex |

### Credential Storage & Crypto (Cross-Cutting)

| ID | Decision | Resolution | Evidence |
|----|----------|------------|----------|
| D-2.17 | IFL credential storage | **OS Keychain primary, encrypted SQLite fallback**. macOS/iOS: Keychain Services (Secure Enclave). Android: Android Keystore (TEE/StrongBox). Linux: `libsecret` / DBUS Secret Service. Fallback: AES-256-GCM encrypted SQLite with key derived from device hardware ID via PBKDF2. Env vars are NEVER used for OAuth tokens on end-user devices. | No credential storage in K0 ports — K0 has no `st_device_credentials` table. Device registry and credentials are Bridge-local only. |
| D-2.18 | E2EE cipher choice | **X25519 (Curve25519 ECDH) + AES-256-GCM**. Decision locked now, implementation deferred to MS-6. The `x25519_public_key` field should be added to device provisioning schema from day one to avoid future migrations. Used by Signal, WireGuard, age encryption. | No E2EE code in K0 ports — encryption is purely Bridge-to-Bridge (P2P). K0 only stores `sync.delta` results via P07. |
| D-2.19 | Device onboarding / pairing | **Admin provisioning via K0 + one-time JWT pairing token**. No 6-digit codes (only 1M combinations, weak against brute force). Flow: Admin → K0 web console → "Add Device" → K0 generates 256-bit JWT (15min expiry) → QR code / deep link → device presents token → K0 provisions `(tenant_id, space_id, device_id, public_key)` → device receives Ed25519 signing credentials. Single-use, time-limited, cryptographically strong. | `k0/ports/command.py` uses `ProvisioningLedger.lookup(tenant_id, space_id, device_id)` — devices must be pre-provisioned. `k0/deploy/scripts/provisioning/provision_device.py` provisions with `tenant_id, space_id, device_id, roles, band, public_key`. |

### K0 Response Signing

| ID | Decision | Resolution | Evidence |
|----|----------|------------|----------|
| D-2.20 | K0 response signatures | **K0 does NOT sign responses**. Command returns `CommandResponse(receipt_id, commit_ts, offsets, idem_key)` — no signature. Obs returns `204 No Content`. Query returns `RecallResponse(bundle, trace, budgets)` — no signature. Bridge signs outbound envelopes only. | `k0/ports/command.py` (CommandResponse model), `k0/ports/observe.py` (returns 204), `k0/ports/query.py` (RecallResponse model) |

### IFL Device Registry

| ID | Decision | Resolution | Evidence |
|----|----------|------------|----------|
| D-2.21 | Device registry location | **Bridge SQLite (local to device)**, NOT K0. K0 has no `st_device_registry` or `st_device_credentials` tables. K0 only receives `ifl.*` events via command port for storage in `st_hipp_events`. The `POST /k0/driver.handshake` endpoint is for K0 outbox pipeline workers, NOT IoT device registration. | `k0/ports/drivers.py` (`DriverHandshakeRequest` has `alias, transport, endpoint` — pipeline drivers, not IoT), `k0/contracts/taxonomies/outbox_routing.yaml` (`ifl.*` glob → `st_epi` driver → P02 pipeline) |

### Command Topic Correction

| ID | Decision | Resolution | Evidence |
|----|----------|------------|----------|
| D-2.22 | `learning.feedback` topic | **Does not exist**. `TopicRouter` would return 400 `UNKNOWN_TOPIC` for this command. K0 `outbox_routing.yaml` has 7 routes: `memory.write`, `session.snapshot`, `beliefs.archive`, `history.archive`, `plan.committed`, `ifl.*`, `sync.delta`. Feedback goes ONLY via Obs Port (`kind=feedback`). | `k0/contracts/taxonomies/outbox_routing.yaml` (no learning.feedback route), `k0/ports/topic_router.py` (UnknownTopicError for unmatched topics) |

---

## 9. Diagram Corrections

The Mermaid diagrams in `bridge/architecture_diagrams/` predate code analysis.
The following items are **known inaccuracies** that must be corrected when diagrams are next updated:

| # | Diagram | Node/Flow | Correction |
|---|---------|-----------|------------|
| 1 | `bridge_architecture.mmd` | `CMD_LEARNING` node (`learning.feedback`) | **Remove**. Topic does not exist in K0 `outbox_routing.yaml`. TopicRouter rejects it with 400. |
| 2 | `bridge_architecture.mmd` | `BAND_ENFORCER` text `GREEN/AMBER/RED/BLACK` | **Change to** `GREEN/AMBER/RED`. K0 Pydantic model `Literal["GREEN", "AMBER", "RED"]` rejects BLACK. |
| 3 | `bridge_architecture.mmd` | `FAMILY_DEVICES` subgraph (K0 on every device) | **Remove K0 from device nodes**. K0 requires PostgreSQL + pgvector — cannot run on phones. Devices run K1 + Bridge only. Single shared K0 cloud. |
| 4 | `bridge_architecture.mmd` | `REQ_SIGNER` labeled `HMAC-SHA256` + `SIG_VERIFY` "Validate K0 responses" | **Change to** `Ed25519SHA512` envelope signing. K0 never signs responses (commands return receipts, obs returns 204, queries return plain JSON). Drop `SignatureVerifier`. |
| 5 | `bridge_architecture.mmd` | `FB_CODEC` (FlatBufferCodec) + `GRPC_ADAPTER` | **Remove or mark `(future)`**. All K0 ports are JSON-over-HTTP. No FlatBuffer deserialization in K0. |
| 6 | `bridge_architecture.mmd` | `SYNC_ENVELOPE → FB_CODEC` flow | **Remove**. Sync is MS-6, FlatBuffer is deferred. |
| 7 | `interkernel_fabric_layer.mmd` | `IFL_REG_DEVICE → DB_DEVICE_REG` (K0 storage) | **Remove K0 arrows**. Device registry lives in Bridge SQLite, not K0. K0 has no `st_device_registry` table. |
| 8 | `interkernel_fabric_layer.mmd` | `IFL_ACQUIRE_LEASE → DB_DEVICE_CREDS` (K0 storage) | **Remove K0 arrows**. Credentials live in Bridge OS Keychain / encrypted SQLite. K0 has no `st_device_credentials` table. |
| 9 | `interkernel_fabric_layer.mmd` | `GrpcAdapter`, `WebSocketAdapter` in Custom Adapters | **Remove or mark `(future)`**. No gRPC/WebSocket in codebase. |

---

## 10. Device Onboarding Flow

Target platforms: macOS, iOS, Android, Linux, Windows.

```
    Admin (existing device)
         │
         ▼
    K0 Web Console / CLI
    "Add Device for <member_name>"
         │
         ├── Generate one-time JWT pairing token
         │     ├── 256-bit random secret
         │     ├── 15-minute expiry
         │     ├── Claims: tenant_id, space_id, device_role
         │     └── Single-use (revoked after first claim)
         │
         ├── Deliver via QR code or deep link
         │
         ▼
    New Device (K1 + Bridge first boot)
         │
         ├── Scan QR / open deep link → extract JWT
         │
         ├── Generate Ed25519 keypair locally
         │     └── Private key → OS Keychain (never leaves device)
         │
         ├── Generate X25519 keypair locally (for future E2EE sync)
         │     └── Private key → OS Keychain
         │
         ├── POST /k0/admin/device.provision (or CLI equivalent)
         │     ├── pairing_token (JWT)
         │     ├── device_id (generated UUID)
         │     ├── ed25519_public_key
         │     └── x25519_public_key
         │
         ├── K0 validates JWT → provisions device in ProvisioningLedger
         │     └── (tenant_id, space_id, device_id, roles, band, public_keys)
         │
         └── Device receives confirmation → Bridge boots with config:
               BridgeConfig(tenant_id, space_id, device_id)
```

**Credential Storage by Platform:**

| Platform | Primary Store | Hardware Backing |
|----------|--------------|------------------|
| macOS/iOS | Keychain Services | Secure Enclave (T2/Apple Silicon) |
| Android | Android Keystore | TEE / StrongBox |
| Linux | `libsecret` / Secret Service | TPM 2.0 (if available) |
| Windows | DPAPI / Credential Manager | TPM 2.0 (if available) |
| Fallback (any) | AES-256-GCM encrypted SQLite | PBKDF2 key from hardware ID |

---

## 11. Implementation Status & Roadmap

This section is the **code-reality bridge** between the target architecture above and the milestone plan in [bridge_implementation_plan.md](../docs/architecture/whiteboard_k1/bridge_implementation_plan.md). It is updated at every milestone close.

### 11.1 What is shipped (MS-2.5 close, 2026-04-25)

| Capability | Source | Test |
|-----------|--------|------|
| Contract registry | [bridge/contracts/manifests/](contracts/manifests/), [bridge/contracts/schemas/](contracts/schemas/), [bridge/contracts/_meta/](contracts/_meta/) | `tests/tooling/contracts/test_*.py` |
| Codegen toolchain | [tooling/contracts/codegen.py](../tooling/contracts/codegen.py) | `tests/tooling/contracts/test_codegen.py` |
| Generated tree (k0+k1) | [bridge/_generated/](_generated/) | codegen `--check` zero drift |
| `BridgeRuntime` + `HandlerRegistry` | [bridge/runtime.py](runtime.py) | `tests/bridge/test_runtime.py` |
| `InProcessHttpTransport` | [bridge/core/transport/in_process_http.py](core/transport/in_process_http.py) | round-trip in exit-criterion test |
| FastAPI dispatcher (testing) | [bridge/testing/dispatcher_app.py](testing/dispatcher_app.py) | exit-criterion test |
| First contract live | `memory.write.v1` manifest + impl in [bridge/handlers/k0/memory_write_v1.py](handlers/k0/memory_write_v1.py) | 19 contract tests |
| Topic aliases (legacy → v1) | [bridge/_topic_aliases.py](_topic_aliases.py) | alias resolution test (D-test) |
| `BridgeAwareLocalBus` proxy (R10) | [bridge/bus_guard.py](bus_guard.py) | D7 in `test_ms_2_5_exit_criterion.py` |
| Observability | [bridge/obs/metrics.py](obs/metrics.py) | metric-shape tests |
| 6 CI gates @ `--fail-on-violation` | [tooling/ci/gates/](../tooling/ci/gates/) + [tooling/ci/run_all_gates.py](../tooling/ci/run_all_gates.py) | `tests/tooling/ci/gates/test_each_gate.py` (22 tests) |
| MS-2.5 EXIT CRITERION | [tests/bridge/contracts/test_ms_2_5_exit_criterion.py](../tests/bridge/contracts/test_ms_2_5_exit_criterion.py) | 7 D-tests |

### 11.2 Roadmap (per [bridge_implementation_plan.md](../docs/architecture/whiteboard_k1/bridge_implementation_plan.md))

| MS | Scope | Architecture sections it activates |
|----|-------|------------------------------------|
| **MS-3a** | Real `HttpBridgeClient` + production `memory.write.v1` over real TCP + K0 receiver `/k0/command.submit` + alias removal | §1.2 (Device+Cloud, Full Local) · §2.1 · §3.1 |
| **MS-3b** | `K0HealthChecker` + ONLINE/DEGRADED/OFFLINE FSM + `LocalOutbox` (TTL, dead-letter, drain pacing) + `OnlineFirst[Port]` decorator + priority-tier enforcement | §1.2 (Offline) · §4 |
| **MS-3c** | Query port: `recall.request.v1` + `recall.response.v1` manifests, real `KernelQueryPort` over `POST /k0/query.recall` | §2.2 · §3.2 |
| **MS-3d** | SSE port: 5–6 K0→K1 manifests (curiosity, advisory, proactive, p03.gap, p03.complete, memory.formed), real chunked streaming, cursor resume, backpressure protocol | §2.3 · §3.3 |
| **MS-3e** | Obs/Feedback: `feedback.envelope.v1` + `observability.payload.v1`, P21 writes `st_feedback_signals` | §2.4 · §3.4 |
| **MS-4** | Codec consolidation (msgpack/CBOR per manifest), hand-written K1 adapter consolidation (<100 LOC across 7 sites) | §6 codecs/ |
| **MS-5** | Connector Gateway + IFL: capability tokens, signed device contracts, OS Keychain credentials, JWT pairing, X25519+AES-GCM E2EE keys generated | §2.5 · §5 · §10 |
| **MS-6** | LAN device sync (mDNS + LWW CRDT + FlatBuffers wire), intra-person device mesh per Q14 ADR-0090c | §6 sync/ · §10 X25519 |

### 11.3 Resolved drift items (cleared before MS-2.5 close)

These appeared in earlier drafts of this document and have been **resolved by code, not just by editing prose**:

| Drift | Status | Resolution |
|-------|--------|------------|
| Three colliding `IBridgePort` definitions | **RESOLVED** in Epic 2.5.3 | Renamed to `IBridgeRuntime` (lifecycle), `IFabricK0Port` (fabric K0 calls), `IPlannerWritePort` (planner local). Gate `single_ibridge_port_definition` enforces no regressions. |
| Always-offline `SinkBridgeClient` | **PARTIALLY RESOLVED** in MS-2.5 | In-process round-trip via `InProcessHttpTransport` is real; out-of-process `HttpBridgeClient` lands MS-3a. `SinkBridgeClient` deletion happens at MS-3a Epic 3a.1. |
| Topic name `memory.write` (un-versioned) | **RESOLVED** in Epic 2.5.5 | Migrated to `memory.write.v1`; legacy spelling resolved via `_topic_aliases.TOPIC_ALIASES`. Alias removed in MS-3a Epic 3a.4. |
| BLAKE3 idem-key formula divergence | **RESOLVED, code is canonical** | Real impl: `BLAKE3(topic ‖ \x00 ‖ canonical_json(body) ‖ \x00 ‖ device_id)`. Earlier prose `(tenant_id, space_id, atom_id, minute(ts))` was speculative and is superseded. See §5 and `bridge/core/envelope_builder.py:_compute_idem_key`. |
| `learning.feedback` topic | **DOES NOT EXIST** (D-2.22) | Feedback flows only via Obs port `kind=feedback`. Diagram correction #1 in §9. |
| `bridge/security/` package | **WILL NOT BE CREATED** | Capability-token + audit pipeline ships as part of Connector Gateway in MS-5; signing already lives in `bridge/core/signing.py`. |

### 11.4 Reading map for new contributors

1. Read §1 (deployment topology) and §1.2 (4 modes table) for the why.
2. Read §6 (module layout) for what files to open.
3. Read [bridge_system_design.md](../docs/architecture/whiteboard_k1/bridge_system_design.md) for the *contract registry rationale* and the open Q1–Q15 design questions.
4. Read [bridge_implementation_plan.md](../docs/architecture/whiteboard_k1/bridge_implementation_plan.md) §"Global rules" + the next pending milestone before opening any PR that touches `bridge/`.
5. Run the exit-criterion test locally before any non-trivial change: `pytest tests/bridge/contracts/test_ms_2_5_exit_criterion.py -v`.
