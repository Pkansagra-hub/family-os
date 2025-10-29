# Bridge K0 — Sequential Implementation Plan

**Generated:** 2025-10-28  
**Layer:** `k1/bridge_k0/`  
**Approach:** Single-developer, strictly sequential (Issue unlocks Issue)  
**Mode:** /pl-adv (fast path — stub-focused planning)

---

## 📊 Executive Summary

- **Components (python files):** 14
- **Detected STUB/Needs Implementation:** 13 (all core runtime files)  
- **Primary Focus Areas:** HTTP/2 transport, protocol negotiation, batching/command clients, K0 ports (command/query/SSE), WAL + saga persistence/logging, resilience integration  
- **Key ADRs Referenced:** ADR-0001/0001a/0001f (bridge architecture), ADR-0011 (FlatBuffers), ADR-0022 (bounded batching), ADR-0022b (HTTP/2 multiplexing), ADR-0009 (circuit breaker), ADR-0044d (error handling), ADR-0038 (receipts/audit), ADR-0008 (saga)

---

## 🏗️ Component Inventory

| Component | Path | Type | Status | ADRs | Notes |
|-----------|------|------|--------|------|-------|
| Batch Client | `bridge_k0/batch_client.py` | Service | STUB | ADR-0022, 0022b, 0001a, 0001f | Bounded batching for SessionState deltas |
| Circuit Breaker Bridge | `bridge_k0/circuit_breaker.py` | Service | STUB | ADR-0009, 0044d | Adapter hooking bridge traffic into resilience layer |
| Command Client | `bridge_k0/command_client.py` | Service | STUB | ADR-0001a, 0001f, 0022, 0009 | HTTP/2 command sender |
| Compression | `bridge_k0/compression.py` | Adapter | STUB | ADR-0001a, 0022d | Payload compression (zstd/gzip) |
| HTTP/2 Transport | `bridge_k0/http2_client.py` | Adapter | STUB | ADR-0001a, 0044, 0044a, 0022b | Connection pooling, multiplexing |
| Protocol Negotiator | `bridge_k0/protocol.py` | Adapter | STUB | ADR-0001, 0001a, 0011, 0013 | JSON/FlatBuffers selection |
| Command Port Adapter | `bridge_k0/ports/command_port.py` | Adapter | STUB | ADR-0001a, 0022, 0022d | K0 command port binding |
| Query Port Adapter | `bridge_k0/ports/query_port.py` | Adapter | STUB | ADR-0001a, 0038 | Reads receipts/query interfaces |
| SSE Port Adapter | `bridge_k0/ports/sse_port.py` | Adapter | STUB | ADR-0042, 0042d | SSE stream ingestion |
| Saga Logger | `bridge_k0/saga_logger.py` | Service | STUB | ADR-0008, 0044d | Structured logging for saga actions |
| Saga Persistence | `bridge_k0/saga_persistence.py` | Service | STUB | ADR-0008, 0038 | Persists saga checkpoints to K0 |
| State Delta Emitter | `bridge_k0/state_delta_emitter.py` | Service | STUB | ADR-0022, 0038 | Streams deltas to batching/ports |
| WAL Writer | `bridge_k0/wal_writer.py` | Service | STUB | ADR-0038, 0001f | Writes immutable receipts to K0 WAL |
| Ports Init | `bridge_k0/ports/__init__.py` | Service | IMPL | — | Export convenience module |

---

## 🔍 Dependency & Integration Notes

- **Transport Stack:** `http2_client` sits at the bottom; `command_client`, `ports/*`, and batching layers depend on it.  
- **Serialization Stack:** `protocol.py` selects JSON vs FlatBuffers, depending on `compression.py` for payload optimization and `k1.l5_infrastructure.serialization` APIs.  
- **Batching Flow:** `state_delta_emitter` → `batch_client` → `command_client` → `command_port`. Query and SSE ports provide read-side streaming (receipts/events).  
- **Resilience:** `circuit_breaker.py`, saga components, and `wal_writer.py` form reliability chain (circuit breaker, durable persistence, saga logging).  
- **External Contracts:** Bridges rely on K0 command/query/SSE HTTP/2 endpoints, plus K0 WAL. Tests referenced (under `tests/k1/bridge_k0/`) exist but expect full implementation.  
- **Observability:** Every module targets metrics/traces/logs with `cognitive_trace_id` propagation; final plan must ensure instrumentation is wired to `k1.l5_infrastructure.observability`.

---

## 🚧 STUB Analysis

- Docs at top of each file mark `🚧 STUB - NEEDS_IMPLEMENTATION`; multiple TODO imports commented out.  
- No functional code beyond data classes/enums; plan must deliver full implementations, config loading (`k1/config/k0_bridge.yml`), and integration tests (existing test files are placeholders referencing these modules).

---

*Planning begins with Milestone 1 below. Additional Milestones/Epics will be appended sequentially as implemented.*

---

# 📍 MILESTONE 1: Transport & Protocol Foundations

**Goal:** Establish HTTP/2 transport, protocol negotiation, and payload compression so downstream clients can rely on a stable bridge base.  
**Dependencies:** None (foundation components)  
**Acceptance Criteria:**
- HTTP/2 client manages pooled, multiplexed connections with backpressure awareness.
- Protocol negotiator selects JSON vs FlatBuffers per ADR guidance and leverages compression module.
- Compression utilities (encode/decode) wired and tested.
- Observability instrumentation (metrics/traces/logs) in place for transport/protocol path.
- Tests in `tests/k1/bridge_k0/test_http2_client.py` & `test_protocol.py` green.

---

## Epic 1.1: HTTP/2 Transport

**Components:** `http2_client.py`

### Issue #M1-1: Implement HTTP2Connection core

**Why:** All bridge clients depend on stable HTTP/2 transport.  
**Inputs:** `k1/bridge_k0/http2_client.py`, ADR-0001a, ADR-0044/0044a, ADR-0022b.  
**Steps:**
1. Implement `HTTP2Config` handling (timeouts, pool sizing, TLS options) with validation.
2. Build connection pool (max connections, idle cleanup) using `asyncio` locks/semaphores.
3. Support multiplexed streams with bounded concurrency (100 streams) and per-stream flow control.
4. Implement request method(s) (`async send_request`) handling headers, payload, retries, circuit breaker hooks.
5. Integrate timeouts/backoff; ensure no `asyncio.sleep` fake waits.
6. Emit metrics (`k1_k0_bridge_http2_*`), traces, logs with `cognitive_trace_id`.
7. Reference ADR IDs in module comments.

**Observability:** Metrics counters/histograms, trace spans per request, structured logs on retries/error.

**Perf/Policy:** Connection setup <50ms, request latency <10ms (P95). Obey privacy bands in headers.

**Done:** All TODOs removed, tests stubbed out replaced with real behaviour, no `NotImplementedError` remains.

---

### Issue #M1-2: Implement HTTP/2 keepalive & backpressure

**Why:** Maintain healthy connections and avoid overload.  
**Inputs:** Same file; ADR-0022b, ADR-0044d.  
**Steps:**
1. Add ping/keepalive scheduler, detect stalled streams.
2. Integrate queue depth monitoring (per-connection, global) with backpressure signals.
3. Provide graceful shutdown waiting active streams.
4. Emit metrics: queue depth, ping latency, reconnect count.

**Done:** Keepalive/backpressure logic active; metrics/traces reflect state; tests cover ping failure/reconnect.

---

### Issue #M1-3: Write HTTP/2 transport tests

**Why:** Validate full transport behaviour.  
**Inputs:** `tests/k1/bridge_k0/test_http2_client.py`; previous Issues.

**Steps:**
1. Implement fixtures mocking remote K0 endpoints (no sleeps; use fast loop controls).
2. Test pooling, multiplexing, retry/backoff, keepalive, graceful shutdown.
3. Assert performance budgets (<10ms request) via timeouts.
4. Verify metrics/traces/logs captured.

**Done:** Tests pass (`pytest tests/k1/bridge_k0/test_http2_client.py -v`), coverage ≥85%.

---

## Epic 1.2: Protocol Negotiation & Compression

**Components:** `protocol.py`, `compression.py`

### Issue #M1-4: Implement compression utilities

**Why:** Protocol negotiator needs ready encode/decode for FlatBuffers/JSON payloads.  
**Inputs:** `compression.py`, ADR-0022d, ADR-0001a.

**Steps:**
1. Provide compression codec interface (zstd primary, gzip fallback, identity).
2. Support streaming encode/decode with memory limits (<5MB).
3. Add auto-detection from headers; integrate with observability metrics.

**Done:** `compress/decompress` functions implemented; metrics/traces/logs wired.

---

### Issue #M1-5: Implement protocol negotiator logic

**Why:** Downstream clients rely on negotiated format.  
**Inputs:** `protocol.py`; ADR-0001/0001a/0011/0013.

**Steps:**
1. Implement negotiation handshake (OPTIONS) with caching (TTL=3600s).
2. Implement payload serialization/deserialization hooks for JSON + FlatBuffers (call into `k1.l5_infrastructure.serialization`).
3. Use compression utilities for payload size > threshold.
4. Provide fallback when FlatBuffers unsupported; log/metric decisions.

**Done:** Negotiation + serialization methods functional, docstring TODOs removed, tests to follow.

---

### Issue #M1-6: Protocol/compression tests

**Why:** Ensure negotiation & compression meet ADR budgets.  
**Inputs:** `tests/k1/bridge_k0/test_protocol.py`; Issues M1-4/5.

**Steps:**
1. Add fixtures simulating K0 responses supporting JSON/FlatBuffers.
2. Test negotiation caching, threshold switching, compression ratio, error fallback.
3. Assert performance budgets (<10ms JSON serialize, <1ms FlatBuffers).

**Done:** Tests pass (`pytest tests/k1/bridge_k0/test_protocol.py -v`), coverage ≥90%.

---

## Epic 1.3: Shared Transport Observability

**Components:** `http2_client.py`, `protocol.py`, `compression.py`

### Issue #M1-7: Centralize transport metrics/traces

**Why:** Standardize observability for downstream use.  
**Steps:**
1. Create helper functions to emit standard labels (band, trace, command_type).
2. Ensure all transport modules use helpers rather than ad-hoc metrics.
3. Document observability schema in comments referencing ADR-0029.

**Done:** Common observability helpers; verified via tests (M1-3/M1-6) capturing metrics & traces.

---

**Milestone 1 Completion Checklist**
- [ ] HTTP/2 transport operational with keepalive/backpressure metrics.
- [ ] Protocol negotiator + compression fully implemented.
- [ ] Tests for transport/protocol passing with budgets enforced.
- [ ] Observability helpers integrated.
- [ ] No `NotImplementedError` or placeholder `pass` remaining in transport modules.

---

# 📍 MILESTONE 2: Command & Batching Pipeline

**Goal:** Implement command client, bounded batching, state delta emitter, and WAL writer so K1 can push deltas/commands reliably to K0.  
**Dependencies:** Milestone 1 transport/protocol complete.  
**Acceptance Criteria:**
- Command client sends commands with receipts, retries, circuit breaker integration.
- Batch client aggregates deltas per ADR-0022; cache handles size/time/count triggers.
- State delta emitter orchestrates delta publishing to batch client.
- WAL writer persists immutable receipts to K0.
- Tests (`test_command_client.py`, `test_batch_client.py`, `test_state_delta_emitter.py`, `test_wal_writer.py`) pass.

---

## Epic 2.1: Command Client Implementation

**Components:** `command_client.py`, `compression.py` (reuse), `protocol.py` (reuse)

### Issue #M2-1: Implement CommandClient enqueue/send logic

**Steps:**
1. Implement queue for pending commands with bounded memory (5MB, 1000 commands).
2. Serialize using ProtocolNegotiator + Compression; send via HTTP2Connection.
3. Handle receipts (ACK) with timeout/retry (3 retries, exp backoff).
4. Integrate circuit breaker states (OPEN → reject, HALF_OPEN probing) via `circuit_breaker.py` (later).
5. Emit metrics/traces/logs per ADR specs.

---

### Issue #M2-2: Receipt handling & backpressure

**Steps:**
1. Track pending receipts; on timeout escalate to resilience (Saga).
2. Publish receipt events to EventBus; push status to WAL writer.
3. Failure path updates circuit breaker + metrics.

---

### Issue #M2-3: Command client tests

**Inputs:** `tests/k1/bridge_k0/test_command_client.py`
1. Mock HTTP2Connection, ProtocolNegotiator, CircuitBreaker.
2. Test enqueue/send, retries, receipt success/failure, backpressure.
3. Verify metrics/traces coverage, performance (<5ms send).

---

## Epic 2.2: Batching & Delta Emission

**Components:** `batch_client.py`, `state_delta_emitter.py`

### Issue #M2-4: Implement BatchClient core

**Steps:** Accumulate deltas, flush by window/size/count, manage receipts, integrate with CommandClient.

### Issue #M2-5: Implement batch backpressure & observability

**Steps:** Monitor buffer usage, connect to L5 backpressure signals, emit metrics/traces.

### Issue #M2-6: Batch client tests

**Steps:** Validate triggers, buffer limits, receipts; ensure performance budgets (<250ms flush).

### Issue #M2-7: Implement StateDeltaEmitter

**Steps:** Subscribe to SessionState deltas, enrich with trace IDs, route to BatchClient; handle privacy band enforcement.

### Issue #M2-8: State delta emitter tests

**Steps:** Simulate delta streams, verify batching decisions, observability, privacy filtering.

---

## Epic 2.3: WAL Writer & Receipts

**Components:** `wal_writer.py`

### Issue #M2-9: Implement WAL writer

**Steps:**
1. Accept receipts from CommandClient/BatchClient.
2. Format immutable envelope per ADR-0038; write via K0 command port.
3. Ensure idempotency (receipt IDs) and privacy obligations.

### Issue #M2-10: WAL writer tests

**Steps:** Validate persistence calls, failure retries, audit logging, performance budgets.

---

**Milestone 2 Completion Checklist**
- [ ] Command client fully functional (send + receipts + circuit hooks).
- [ ] Batch client + delta emitter operational, budgets honored.
- [ ] WAL writer persisting receipts safely.
- [ ] All related tests passing; coverage ≥85%.

---

# 📍 MILESTONE 3: Ports & Query Interfaces

**Goal:** Implement K0 port adapters (command/query/SSE) and load balancing/resilience integration.  
**Dependencies:** Milestones 1 & 2.

## Epic 3.1: Command Port Adapter
- Issue #M3-1: Implement `ports/command_port.py` (HTTP/2 request/response, concurrency limits, privacy band headers).  
- Issue #M3-2: Tests for command port adapter.

## Epic 3.2: Query Port Adapter
- Issue #M3-3: Implement `ports/query_port.py` (receipt polling, pagination, error handling).  
- Issue #M3-4: Tests verifying query flows, metrics, budgets (<100ms fetch).

## Epic 3.3: SSE Port Adapter
- Issue #M3-5: Implement `ports/sse_port.py` (subscribe to K0 SSE streams, reconnection, filter by topic).  
- Issue #M3-6: Tests ensuring SSE reconnection, buffering, metrics/traces.

**Checklist:** All port adapters operational, tests passing, metrics/traces integrated.

---

# 📍 MILESTONE 4: Resilience & Saga Infrastructure

**Goal:** Wire bridge into resilience stack — circuit breaker adapter, saga logging/persistence — to guarantee durability and recovery.

## Epic 4.1: Circuit Breaker Integration
- Issue #M4-1: Implement `circuit_breaker.py` hooking into `k1.l5_infrastructure.resilience`.  
- Issue #M4-2: Tests verifying open/half-open behaviour with CommandClient integration.

## Epic 4.2: Saga Logging & Persistence
- Issue #M4-3: Implement `saga_logger.py` (structured logs, metrics).  
- Issue #M4-4: Implement `saga_persistence.py` (persist saga checkpoints to K0) with retry/backoff.  
- Issue #M4-5: Tests covering saga logging/persistence flows.

## Epic 4.3: Receipt + WAL Coordination
- Issue #M4-6: Integrate `wal_writer.py` with sagas and circuit breaker failover.  
- Issue #M4-7: Tests ensuring saga rollback, WAL durability, audit compliance.

---

# 📍 MILESTONE 5: Hardening & Performance

**Goal:** End-to-end validation, performance benchmarking, observability hardening.

- Issue #M5-1: Integration harness for bridge stack (`tests/k1/bridge_k0/test_integration_bridge.py`).
- Issue #M5-2: End-to-end delta→WAL flow test (success/failure paths). 
- Issue #M5-3: Performance benchmarks (batch flush latency, command throughput, SSE recovery) verifying ADR budgets.  
- Issue #M5-4: Observability + privacy compliance audit (metrics dashboards, audit log verification).  
- Issue #M5-5: Gate 5 deliverables (diagrams, memory updates, perf artifacts recorded).

---

## 🧭 Global Dependency Chain (Abbreviated)

```
M1-1 → M1-2 → M1-3 → M1-4 → M1-5 → M1-6 → M1-7 →
M2-1 → M2-2 → M2-3 → M2-4 → M2-5 → M2-6 → M2-7 → M2-8 → M2-9 → M2-10 →
M3-1 → M3-2 → M3-3 → M3-4 → M3-5 → M3-6 →
M4-1 → M4-2 → M4-3 → M4-4 → M4-5 → M4-6 → M4-7 →
M5-1 → M5-2 → M5-3 → M5-4 → M5-5
```

**Initial execution focus:** start with Issue M1-1 (HTTP2 transport core), then proceed sequentially.
