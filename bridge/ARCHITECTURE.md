# Bridge Architecture

> **Module:** `bridge`
> **Status:** MS-2 Implementation
> **Updated:** 2026-04-10

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

| Mode | K1 | Bridge | K0 | Use Case |
|------|-----|--------|----|----------|
| **Dev Monolith** | `localhost` | `in-process` | `docker-compose :8080` | Local development |
| **Device + Cloud** | Device process | Device process | Remote server | Production |
| **Full Local** | Device process | Device process | Device Docker | Privacy-max / air-gapped |
| **Offline** | Device process | Device process | `UNREACHABLE` | No internet, LocalOutbox queues |

Only `TransportConfig.base_url` changes between modes. Everything else is identical.

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
              │                 K0 does NOT sign responses
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

```
bridge/
├── __init__.py
├── ARCHITECTURE.md          ← this file
├── README.md                ← overview + quick start
│
├── kernel/                  ← K0 port implementations
│   ├── command_port.py      ← IKernelCommandPort (existing)
│   ├── query_port.py        ← IKernelQueryPort (planned)
│   ├── sse_port.py          ← IKernelSSEPort (planned)
│   └── obs_port.py          ← IKernelObsPort (planned)
│
├── core/                    ← Shared infrastructure
│   ├── envelope_builder.py  ← CommandEnvelope construction (existing)
│   ├── signing.py           ← Ed25519 + BLAKE3 (existing)
│   ├── transport.py         ← HttpTransport (existing)
│   ├── query_types.py       ← QueryEnvelope, RecallSelector (planned)
│   ├── query_builder.py     ← Fluent query builder (planned)
│   ├── sse_types.py         ← SSETraceEvent, backpressure (planned)
│   ├── health_checker.py    ← K0 health polling (planned)
│   └── degraded_mode.py     ← Offline mode manager (planned)
│
├── connector/               ← IFL Connector Gateway
│   ├── gateway.py           ← Security pipeline (planned)
│   ├── tool_registry.py     ← Adapter registration (planned)
│   └── credentials.py       ← OAuth + key store (planned)
│
├── adapters/                ← IFL device adapters
│   ├── homekit.py           ← Apple HomeKit (planned)
│   ├── nest.py              ← Google Nest (planned)
│   ├── tesla.py             ← Tesla Vehicle (planned)
│   ├── mqtt.py              ← Generic MQTT (planned)
│   └── family_sync.py       ← K0 P07 sync (planned)
│
├── sync/                    ← Offline queue + device sync
│   └── local_outbox.py      ← SQLite WAL queue (existing)
│
├── codecs/                  ← Serialization
│   └── json_codec.py        ← JSON envelope codec (planned)
│
├── security/                ← Security core (planned)
│   ├── tokens.py            ← CapabilityToken issue/verify
│   ├── bands.py             ← Band enforcement (GREEN/AMBER/RED)
│   └── audit.py             ← Audit logger + exporter
│
├── contracts/               ← Protocol ABCs
│   ├── ports.py             ← 5 port Protocols (planned)
│   └── envelopes.py         ← Envelope type contracts (planned)
│
├── client.py                ← IBridgeClient facade (planned)
│
└── architecture_diagrams/   ← Mermaid diagrams
    ├── bridge_architecture.mmd
    └── interkernel_fabric_layer.mmd
```

---

## 7. Data Flow Summary

```
┌────────────────────────────────────────────────────────────────────┐
│                        K1 → K0 FLOWS                               │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  Memory Write ──→ CMD Port ──→ POST /k0/command.submit             │
│                       topic: memory.write                          │
│                                                                    │
│  Session Save ──→ CMD Port ──→ POST /k0/command.submit             │
│                       topic: session.snapshot                      │
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
