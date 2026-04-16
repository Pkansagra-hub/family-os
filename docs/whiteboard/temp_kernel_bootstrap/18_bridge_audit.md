# 18 — Epic 1.9: Bridge Audit

> Generated from 2 parallel subagent code reads across `bridge/`.
> Bridge is the **most incomplete component** — only 1 of 5 ports has a concrete implementation. The system is permanently offline (no online `BridgeClient` exists).

---

## Summary Verdict

| Issue | What To Check | Verdict |
| ----- | ------------- | ------- |
| 1.9.1 | Read 5 bridge port protocols | ✅ All 5 Protocol, `@runtime_checkable`, all-async. Rich supporting types (13 dataclasses). 493 LOC |
| 1.9.2 | Read BridgeClient facade — what methods exist? | ✅ `IBridgeClient` Protocol (11 methods) + `StubBridgeClient` (test) + `SinkBridgeClient` (offline). 277 LOC |
| 1.9.3 | Read KernelCommandPort — submit() signature | ✅ REAL — 189 LOC. HTTP POST + offline fallback to LocalOutbox. Custom errors: `ContractViolationError`, `PolicyDeniedError` |
| 1.9.4 | Read LocalOutbox — offline queueing | ✅ REAL — 215 LOC. SQLite WAL-backed queue with drain(), max 10K depth, max 10 attempts |
| 1.9.5 | Read bridge core — transport, signing, health, envelope builder | ✅ ALL 4 REAL — 688 LOC total. HttpTransport (httpx), HMAC+Ed25519 signing, health state machine, BLAKE3 integrity |
| 1.9.6 | Check bridge/adapters/ — what's missing? | ❌ **EMPTY** — zero adapter files. Placeholder `__init__.py` only |
| 1.9.7 | Check bridge/connector/ — what's missing? | ❌ **EMPTY** — zero connector files. Deferred to MS-3 (IFL) |

---

## Package Structure

```
bridge/
├── __init__.py                          (15 LOC, __status__ = "planning")
├── ARCHITECTURE.md
├── client.py                            (277 LOC — IBridgeClient, StubBridgeClient, SinkBridgeClient)
├── README.md
├── adapters/
│   └── __init__.py                      (EMPTY placeholder)
├── codecs/
│   └── __init__.py                      (EMPTY placeholder)
├── connector/
│   └── __init__.py                      (EMPTY placeholder)
├── contracts/
│   ├── command_port.protocol.yaml
│   └── schemas/command_envelope.json
├── core/
│   ├── __init__.py                      (28 LOC — re-exports)
│   ├── envelope_builder.py              (192 LOC — EnvelopeBuilder + BridgeConfig)
│   ├── health.py                        (217 LOC — K0HealthChecker + DegradedModeManager)
│   ├── signing.py                       (147 LOC — HMAC + Ed25519)
│   └── transport.py                     (132 LOC — HttpTransport + httpx)
├── kernel/
│   ├── __init__.py                      (10 LOC — re-exports)
│   └── command_port.py                  (189 LOC — KernelCommandPort)
├── ports/
│   ├── __init__.py                      (47 LOC — re-exports 15 symbols)
│   ├── command_port_protocol.py         (50 LOC)
│   ├── query_port_protocol.py           (133 LOC)
│   ├── sse_port_protocol.py             (113 LOC)
│   ├── obs_port_protocol.py             (101 LOC)
│   └── connector_gateway_protocol.py    (96 LOC)
└── sync/
    ├── __init__.py                      (45 LOC — re-exports + planned None stubs)
    └── local_outbox.py                  (215 LOC — SQLite offline queue)
```

---

## Issue 1.9.1 — Port Protocols (5 Ports, 493 LOC)

All 5 ports: `Protocol` base, `@runtime_checkable`, all-async. Self-contained with rich supporting types.

### BR-P1: `IKernelCommandPort` (50 LOC)

| Method | Signature | Returns |
| ------ | --------- | ------- |
| `submit` | `async (topic, body, *, schema_uri, band, trace_id)` | `None` |
| `submit_batch` | `async (envelopes: list[CommandEnvelope])` | `None` |

Fire-and-forget K1→K0 commands. Offline-queues to `LocalOutbox`.

### BR-P2: `IKernelQueryPort` (133 LOC)

| Method | Signature | Returns |
| ------ | --------- | ------- |
| `query` | `async (envelope: QueryEnvelope)` | `RecallBundle` |
| `query_single` | `async (selector: RecallSelector, *, trace_id)` | `RecallBundle` |

K1→K0→K1 request/response recall. 4 frozen dataclasses: `RecallSelector`, `QueryEnvelope`, `RecallItem`, `RecallBundle` (with `empty()` classmethod).

### BR-P3: `IKernelSSEPort` (113 LOC)

| Method | Signature | Returns |
| ------ | --------- | ------- |
| `subscribe` | `async (topics, *, cursor)` | `AsyncIterator[SSETraceEvent]` |
| `ack` | `async (topic, cursor)` | `None` |
| `close` | `async ()` | `None` |

K0→K1 server-sent events with backpressure: `BackpressureLevel` enum (`OK`, `THROTTLE`, `SHED`), cursor-based resumption.

### BR-P4: `IKernelObsPort` (101 LOC)

| Method | Signature | Returns |
| ------ | --------- | ------- |
| `emit` | `async (kind, body, *, priority, trace_id)` | `None` |
| `emit_feedback` | `async (envelope: FeedbackEnvelope)` | `None` |

K1→K0 one-way observability. Offline policy: LOW dropped, NORMAL/HIGH queued. `ObsKind` enum (`METRICS`, `LOGS`, `FEEDBACK`), `ObsPriority` enum.

### BR-P5: `IConnectorGatewayPort` (96 LOC)

| Method | Signature | Returns |
| ------ | --------- | ------- |
| `execute` | `async (adapter_id, action, params, *, trace_id, timeout_ms)` | `ConnectorResult` |
| `list_adapters` | `async ()` | `list[AdapterStatus]` |

Bidirectional external traffic via IFL. **Explicitly deferred to MS-3.** `SinkBridgeClient` raises `NotImplementedError`.

### Cross-Module Imports from Ports

| Port | External Imports |
| ---- | ---------------- |
| `IKernelCommandPort` | `bridge.core.envelope_builder.CommandEnvelope` |
| All others | None (self-contained with inline dataclasses) |

---

## Issue 1.9.2 — BridgeClient Facade (277 LOC)

**File:** `bridge/client.py`

### `IBridgeClient` Protocol (`@runtime_checkable`)

Unified facade over all 5 port protocols — kernel bootstrap wires ONE `IBridgeClient`, per-component adapters narrow it to their local port.

| Category | Method | Signature |
| -------- | ------ | --------- |
| Command | `submit_command` | `async (topic, body, *, schema_uri, band, trace_id) -> None` |
| Command | `submit_command_batch` | `async (envelopes: list[dict]) -> None` |
| Query | `query` | `async (envelope: QueryEnvelope) -> RecallBundle` |
| Query | `query_single` | `async (selector: RecallSelector, *, trace_id) -> RecallBundle` |
| SSE | `subscribe` | `async (topics: list[str], *, cursor) -> AsyncIterator[SSETraceEvent]` |
| SSE | `ack` | `async (topic, cursor) -> None` |
| SSE | `close_sse` | `async () -> None` |
| Obs | `emit_obs` | `async (kind, body, *, priority, trace_id) -> None` |
| Obs | `emit_feedback` | `async (envelope: FeedbackEnvelope) -> None` |
| IFL | `execute_connector` | `async (adapter_id, action, params, *, trace_id, timeout_ms) -> dict` |
| Health | `health` | `() -> K0HealthSnapshot` (**sync!**) |

### `StubBridgeClient` (Test Double)

- Records all calls to `self.calls: list[tuple]`
- Returns `RecallBundle.empty()` for queries, empty async iter for SSE
- Health defaults to `ONLINE`
- No constructor deps

### `SinkBridgeClient` (Offline-First / Pre-MS-3 Production)

**Constructor:** `(outbox: Any, health_checker: K0HealthChecker | None, degraded_manager: DegradedModeManager | None)`

| Port | Offline Behaviour |
| ---- | ----------------- |
| Command | Queues to `LocalOutbox` via `outbox.enqueue()` |
| Query | Returns `RecallBundle.empty()` |
| SSE | Returns empty async iterator |
| Obs | Drops LOW priority, logs NORMAL/HIGH (**does NOT queue** despite docstring) |
| IFL | Raises `NotImplementedError("IFL connector gateway: MS-3")` |
| Health | Returns snapshot from `K0HealthChecker` (forced OFFLINE at init) |

---

## Issue 1.9.3 — KernelCommandPort (189 LOC)

**File:** `bridge/kernel/command_port.py` — **REAL implementation**

**Constructor:** `(transport: HttpTransport, builder: EnvelopeBuilder, outbox: Any | None = None)`

### Public Methods

| Method | Signature |
| ------ | --------- |
| `submit` | `async (topic, body, *, schema_uri, band, trace_id) -> None` |
| `submit_batch` | `async (envelopes: list[CommandEnvelope]) -> None` |

### Response Handling (`_send_envelope`)

| K0 Status | Behaviour |
| --------- | --------- |
| 200 | Success (fire-and-forget) |
| 409 | Idempotent duplicate — silently ignored |
| 400 | Raises `ContractViolationError` |
| 403 | Raises `PolicyDeniedError` |
| 429 / 5xx / network | Queue to `LocalOutbox` if available; log LOST otherwise |

**Batch:** `_MAX_BATCH_CONCURRENCY = 3`, `_MAX_BATCH_SIZE = 50`.

### Custom Errors

- `ContractViolationError(Exception)` — K0 Gate rejected
- `PolicyDeniedError(ContractViolationError)` — K0 PEP denied

---

## Issue 1.9.4 — LocalOutbox (215 LOC)

**File:** `bridge/sync/local_outbox.py` — **REAL implementation**

SQLite WAL-backed offline queue. Guarantees MW-09 (no envelope loss).

### `OutboxQueueEntry` (dataclass, `slots=True`)

Fields: `id`, `topic`, `envelope_json`, `priority`, `created_at`, `attempts`, `last_attempt_at`, `status`.

### `LocalOutbox` — Constructor: `(db_path: str | Path)`

| Method | Signature | Purpose |
| ------ | --------- | ------- |
| `enqueue` | `(envelope_json, topic, priority=2) -> int` | INSERT, enforces MAX_QUEUE_DEPTH=10,000 |
| `pending_count` | `() -> int` | COUNT WHERE status='PENDING' |
| `list_pending` | `(limit=50) -> list[OutboxQueueEntry]` | SELECT ordered by priority, created_at |
| `drain` | `async (transport, max_concurrent=5) -> int` | Send pending to K0, return success count |
| `mark_failed` | `(entry_id) -> None` | UPDATE status='FAILED' |
| `delete` | `(entry_id) -> None` | DELETE row |
| `close` | `() -> None` | Close SQLite connection |

**Constants:** `MAX_QUEUE_DEPTH=10,000`, `MAX_ATTEMPTS=10`, `DEFAULT_DRAIN_CONCURRENCY=5`.

---

## Issue 1.9.5 — Bridge Core (4 Modules, 688 LOC)

### `HttpTransport` (132 LOC)

Async HTTP client via `httpx` with connection pooling and TLS config.

| Method | Purpose |
| ------ | ------- |
| `open()` | Create `httpx.AsyncClient` |
| `close()` | Shutdown client |
| `post_command(envelope_json: bytes)` | POST to `/k0/command.submit` |
| `check_health()` | GET `/healthz` |

### `signing` (147 LOC)

Pluggable envelope signing. `SigningBackend` Protocol (NOT `@runtime_checkable`).

| Backend | Algorithm | Key |
| ------- | --------- | --- |
| `HmacSigning` | hmac-sha256 | `secret: bytes` (≥16) |
| `Ed25519Signing` | ed25519 | `signing_key_bytes: bytes` (32/64) |

Both have `sign()` and `verify()`.

### `health` (217 LOC)

K0 availability tracking with state machine.

**`K0HealthChecker`:** ONLINE→DEGRADED (high latency), →OFFLINE (≥3 failures), OFFLINE→ONLINE (1 success).

**`DegradedModeManager`:** Policy engine wrapping health checker — `should_queue_command()`, `should_drop_obs()`, `should_use_cache()`, `query_timeout_ms()`.

### `EnvelopeBuilder` (192 LOC)

Constructs signed K0 command envelopes. `BridgeConfig` (frozen dataclass): `tenant_id`, `space_id`, `device_id`, `actor`, `policy_version`, `default_band`.

Produces 18 envelope fields including SHA-256 payload hash, BLAKE3 idempotency key, and signature.

---

## Issue 1.9.6 — bridge/adapters/ (EMPTY)

**Zero adapter implementations.** The directory contains only `__init__.py` with a comment. README mentions a planned `mock_adapter.py` but it doesn't exist.

All "adapter" logic lives in `bridge/kernel/command_port.py` (KernelCommandPort) and `bridge/client.py` (StubBridgeClient, SinkBridgeClient).

---

## Issue 1.9.7 — bridge/connector/ (EMPTY)

**Zero connector implementations.** Deferred to MS-3 (IFL milestone). Contains only `__init__.py` with a comment.

---

## Port Implementation Coverage

| Port Protocol | Concrete Implementation | Status |
| ------------- | ----------------------- | ------ |
| `IKernelCommandPort` | `KernelCommandPort` (189 LOC) | **REAL** |
| `IKernelQueryPort` | **NONE** — only `RecallBundle.empty()` in SinkBridgeClient | **MISSING** |
| `IKernelSSEPort` | **NONE** — only empty async iter in Stub/Sink | **MISSING** |
| `IKernelObsPort` | **NONE** — only drop/log in SinkBridgeClient | **MISSING** |
| `IConnectorGatewayPort` | **NONE** — raises `NotImplementedError` | **MISSING (MS-3)** |
| `IBridgeClient` (facade) | `StubBridgeClient` (test) + `SinkBridgeClient` (offline) | **SEMI-REAL** |

**Only 1 of 5 ports has a real implementation.** The system is permanently in offline mode.

---

## Third-Party Dependencies

| Package | Used By | Purpose |
| ------- | ------- | ------- |
| `httpx` | `HttpTransport` | Async HTTP client |
| `blake3` | `EnvelopeBuilder` | Idempotency key hash |
| `pynacl` | `Ed25519Signing` | Ed25519 signatures (optional) |

---

## Anomalies & Risks

| # | Anomaly | Severity | Impact |
| -- | ------- | -------- | ------ |
| 1 | **4 of 5 ports have NO concrete implementation** | **HIGH** | Query, SSE, Obs, IFL are protocol-only. K1 cannot recall from K0, receive events, or send telemetry |
| 2 | **No online `BridgeClient` exists** | **HIGH** | `SinkBridgeClient` IS the production client — system is permanently offline |
| 3 | **`SinkBridgeClient.emit_obs` does NOT queue** despite docstring saying it does | **MEDIUM** | NORMAL/HIGH obs are logged then dropped, not queued to LocalOutbox |
| 4 | **`IBridgeClient.submit_command_batch` takes `list[dict]`** but port takes `list[CommandEnvelope]` | **MEDIUM** | Type mismatch between facade and port protocol |
| 5 | **`SigningBackend` Protocol is NOT `@runtime_checkable`** | **LOW** | `isinstance()` checks on signers would fail — inconsistent with all port protocols |
| 6 | **`bridge/__init__.py` has `__status__ = "planning"`** | **LOW** | Stale — substantial implementation exists (core, ports, kernel, client) |
| 7 | **`bridge/codecs/` is empty** | **LOW** | No serialization layer despite being in architecture |
| 8 | **`bridge/sync/__init__.py` exports 6 symbols that are `None`** | **LOW** | Phase 1 sync: `CertificateManager`, `CRDTMerge`, `DeviceDiscovery`, `E2EEncryption`, `ISyncPort`, `SyncPortImpl` — all resolve to None |
| 9 | **Test doubles live in production `client.py`** | **LOW** | `StubBridgeClient` is in prod code, not test directory |
| 10 | **`KernelCommandPort` doesn't declare Protocol conformance** | **LOW** | Structural subtyping — valid but no static type-check at class definition |

---

## Comparison With Prior Epics

| Dimension | Bus (1.1) | SSM (1.2) | Fabric (1.3) | ModelHub (1.4) | Orch (1.5) | Planner (1.6) | Concierge (1.7) | MemWriter (1.8) | **Bridge (1.9)** |
| --------- | --------- | --------- | ------------ | -------------- | ---------- | -------------- | --------------- | --------------- | ---------------- |
| Port style | Protocol | ABC | Protocol | Protocol | Protocol | Protocol | Protocol | Protocol | **Protocol** |
| Port count | 3 | 5 | 6 | 7 | 9 | 7 | 9 | 5 | **5** |
| Port LOC | ~150 | ~2,430 | ~1,150 | ~400 | ~1,099 | ~537 | ~155 | ~371 | **~493** |
| Factory | 200 | 180 | 350 | 280 | 560 | 573 | 860 | 143 | **N/A (facade)** |
| Prod adapters | 2 | 4+5 stub | 9 | 3+6 semi | 9 | 6+1 semi | 3+2+3 | 4+1 semi | **1 REAL** |
| Missing impls | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **4 ports** |
| Core infra | — | — | — | — | — | — | — | — | **688 LOC (transport, signing, health, envelope)** |

**Bridge is architecturally complete (rich port protocols + core infrastructure) but implementation-incomplete (4 of 5 ports unimplemented, no online client).**
