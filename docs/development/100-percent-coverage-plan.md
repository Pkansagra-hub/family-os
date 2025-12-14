# 100% Coverage Plan: Core Kernel Components

**Date:** November 23, 2025
**Goal:** Achieve 100% test coverage for all critical kernel components
**Current Overall Coverage:** 10% (3967 statements, 3463 missed)

---

## Coverage Status by Component

### TIER 1: CRITICAL SECURITY & VALIDATION (Must be 100%)

| Component | Current | Missing | Priority | Risk |
|-----------|---------|---------|----------|------|
| **k0/gate/minimal_gate.py** | 16% | 312/400 stmts | **CRITICAL** | 🔴 HIGH |
| **k0/security/crypto.py** | 78% | 10/55 stmts | **HIGH** | � MEDIUM |
| **k0/gate/schema_registry.py** | 17% | 148/189 stmts | **CRITICAL** | � HIGH |
| **k0/idem/derive.py** | 34% | 32/54 stmts | **HIGH** | � MEDIUM |
| **k0/idem/ledger.py** | **63%** | 22/75 stmts | **MEDIUM** | 🟢 LOW |

**Total Statements to Cover:** 524 (gates + security + idem)

---

### TIER 2: POLICY & ACCESS CONTROL (Must be 100%)

| Component | Current | Missing | Priority | Risk |
|-----------|---------|---------|----------|------|
| **k0/policy/pep_syscall.py** | 0% | 328/328 stmts | **CRITICAL** | � HIGH |
| **k0/policy/redaction.py** | 0% | 164/164 stmts | **CRITICAL** | � HIGH |
| **k0/policy/retention_enforcer.py** | 0% | 119/119 stmts | **HIGH** | � HIGH |
| **k0/policy/acl_enforcer.py** | 0% | 78/78 stmts | **HIGH** | � HIGH |
| **k0/policy/location_privacy.py** | 0% | 75/75 stmts | **HIGH** | � MEDIUM |
| **k0/policy/policy_stamp.py** | 0% | 38/38 stmts | **MEDIUM** | 🟠 MEDIUM |

**Total Statements to Cover:** 802 (all policy components)

---

### TIER 3: TRANSACTION & STORAGE (Must be 95%+)

| Component | Current | Missing | Priority | Risk |
|-----------|---------|---------|----------|------|
| **k0/uow/unit_of_work.py** | 25% | 138/201 stmts | **CRITICAL** | 🔴 HIGH |
| **k0/uow/connection_pool.py** | 14% | 155/187 stmts | **HIGH** | 🟠 MEDIUM |
| **k0/receipts/issuer.py** | 0% | 82/82 stmts | **HIGH** | � MEDIUM |

**Total Statements to Cover:** 375 (transaction layer)

---

### TIER 4: QOS & SCHEDULING (Must be 90%+)

| Component | Current | Missing | Priority | Risk |
|-----------|---------|---------|----------|------|
| **k0/qos/scheduler.py** | 31% | 48/76 stmts | **HIGH** | � MEDIUM |
| **k0/qos/context.py** | 35% | 19/36 stmts | **MEDIUM** | 🟢 LOW |
| **k0/qos/metrics.py** | 36% | 23/36 stmts | **MEDIUM** | 🟢 LOW |
| **k0/qos/policy.py** | 12% | 55/68 stmts | **HIGH** | � MEDIUM |

**Total Statements to Cover:** 145 (QoS layer)

---

### TIER 5: BUS & SSE (Must be 85%+)

| Component | Current | Missing | Priority | Risk |
|-----------|---------|---------|----------|------|
| **k0/bus/core.py** | 23% | 120/172 stmts | **HIGH** | � MEDIUM |
| **k0/bus/middleware.py** | 19% | 49/62 stmts | **MEDIUM** | 🟢 LOW |
| **k0/sse/server.py** | 0% | 188/188 stmts | **HIGH** | � MEDIUM |

**Total Statements to Cover:** 357 (bus + SSE)

---

### TIER 6: PORTS (HTTP Layer - 80%+)

| Component | Current | Missing | Priority | Risk |
|-----------|---------|---------|----------|------|
| **k0/ports/command.py** | 0% | 414/414 stmts | **MEDIUM** | 🟢 LOW* |
| **k0/ports/query.py** | 0% | 361/361 stmts | **MEDIUM** | 🟢 LOW* |
| **k0/ports/sse.py** | 0% | 210/210 stmts | **MEDIUM** | 🟢 LOW* |
| **k0/ports/observe.py** | 0% | 130/130 stmts | **LOW** | 🟢 LOW* |
| **k0/ports/drivers.py** | 0% | 98/98 stmts | **LOW** | 🟢 LOW* |

*Note: Integration tests already cover ports behavior (26/27 passing). Unit tests needed for local coverage metrics.*

**Total Statements to Cover:** 1213 (all ports)

---

## Implementation Plan (Phased Approach)

### PHASE 1: Security & Validation (Week 1)
**Target:** 100% coverage of gate, security, idem
**Est. Tests:** 80-100 tests
**Priority:** 🔴 CRITICAL

#### 1.1 MinimalGate (k0/gate/minimal_gate.py) - 312 statements
**Current:** 16% | **Target:** 100%

**Test Categories:**
- ✅ **Initialization (23 tests)** - COMPLETE
- ⚠️ **Full validate() Flow (30 tests)** - NEEDED
  - Signature verification success/failure paths
  - Device provisioning lookups (cached + uncached)
  - Schema validation (ACTIVE/BLOCKED/SUNSET)
  - Payload hash validation
  - Envelope hash validation
  - Clock skew detection
  - Size limit enforcement
  - Replay detection
  - HMAC idem key derivation
  - All rejection reasons (15 error codes)
  - Metrics emission for each path

- ⚠️ **Helper Methods (20 tests)** - NEEDED
  - `_verify_with_rotation_support()`
  - `_check_envelope_replay()`
  - `_get_device_secret()`
  - `_validate_schema()`
  - `_normalize_body()`
  - `_normalize_hash()`
  - All telemetry methods

**Estimated:** 50 additional tests required

---

#### 1.2 SchemaRegistry (k0/gate/schema_registry.py) - 148 statements
**Current:** 17% | **Target:** 100%

**Test Categories:**
- ⚠️ **CRUD Operations (15 tests)** - NEEDED
  - `register()` - new schemas
  - `upsert()` - update existing
  - `promote()` - REGISTERED → ACTIVE
  - `block()` - mark as BLOCKED
  - `active_versions()` - query active schemas
  - `records_for_uri()` - query by URI
  - `get_audit_trail()` - audit history

- ⚠️ **Cache Behavior (10 tests)** - NEEDED
  - Cache hits/misses
  - `load()` population
  - `clear_cache()` invalidation
  - Metrics emission

- ⚠️ **Status Transitions (8 tests)** - NEEDED
  - REGISTERED → ACTIVE
  - ACTIVE → DEPRECATED
  - ACTIVE → BLOCKED
  - BLOCKED → ACTIVE (unblock)
  - Invalid transitions

**Estimated:** 33 tests required

---

#### 1.3 Security/Crypto (k0/security/crypto.py) - 10 statements
**Current:** 78% | **Target:** 100%

**Missing Coverage:**
- Error handling in `_decode_base64url()`
- Edge cases in signature verification
- Malformed envelope canonicalization

**Estimated:** 5-8 tests required

---

#### 1.4 Idem Derivation (k0/idem/derive.py) - 32 statements
**Current:** 34% | **Target:** 100%

**Test Categories:**
- ⚠️ **BLAKE3 Derivation (8 tests)** - NEEDED
  - Happy path with all fields
  - Missing required fields
  - Empty field values
  - Payload hash variants

- ⚠️ **HMAC Derivation (10 tests)** - PARTIALLY COMPLETE
  - ✅ Basic HMAC tests exist (18 tests)
  - ⚠️ Need edge cases:
    - Invalid timestamp formats
    - Time bucket boundaries
    - Device secret variations
    - Envelope SHA256 variants

**Estimated:** 10 additional tests required

---

#### 1.5 Idem Ledger (k0/idem/ledger.py) - 22 statements
**Current:** 63% | **Target:** 100%

**Missing Coverage:**
- ✅ Most paths covered (20 tests)
- ⚠️ Telemetry emission edge cases
- ⚠️ Connection pool error handling

**Estimated:** 5-10 tests required

---

### PHASE 2: Policy Engine (Week 2)
**Target:** 100% coverage of all policy components
**Est. Tests:** 120-150 tests
**Priority:** 🔴 CRITICAL

#### 2.1 PEP Syscall (k0/policy/pep_syscall.py) - 328 statements
**Current:** 0% | **Target:** 100%

**Test Categories:**
- **Envelope Evaluation (20 tests)**
  - Band-based policies (GREEN/AMBER/RED)
  - Device posture checks
  - Capability enforcement
  - Schema sunset checks
  - Role-based access
  - Size limits

- **Policy Stamp Creation (15 tests)**
  - Stamp generation
  - Obligation attachment
  - Manifest fingerprinting
  - JSON serialization

- **Obligation Building (25 tests)**
  - Redaction obligations
  - Retention obligations
  - Privacy obligations
  - QoS tightening
  - Deduplication

- **Helper Methods (15 tests)**
  - `_load_policy_manifest()`
  - `_lookup_band_policy()`
  - `_evaluate_*()` methods (6 evaluators)

**Estimated:** 75 tests required

---

#### 2.2 Redaction Engine (k0/policy/redaction.py) - 164 statements
**Current:** 0% | **Target:** 100%

**Test Categories:**
- **Directive Parsing (10 tests)**
  - Parse obligations into directives
  - Path normalization
  - Mask type resolution

- **Redaction Application (20 tests)**
  - Field masking (full, partial, hash)
  - Nested path redaction
  - Array element redaction
  - Location privacy integration

- **Location Privacy (12 tests)**
  - Geohash masking by band
  - Precision levels
  - Lat/lon to geohash conversion

**Estimated:** 42 tests required

---

#### 2.3 Retention Enforcer (k0/policy/retention_enforcer.py) - 119 statements
**Current:** 0% | **Target:** 100%

**Test Categories:**
- **Policy Application (15 tests)**
  - Band-based retention periods
  - Expiry timestamp calculation
  - Grace periods

- **Resource Management (15 tests)**
  - `get_expired_resources()`
  - Archive operations
  - Delete operations
  - Tombstone creation

**Estimated:** 30 tests required

---

#### 2.4 ACL Enforcer (k0/policy/acl_enforcer.py) - 78 statements
**Current:** 0% | **Target:** 100%

**Test Categories:**
- **Permission Checks (10 tests)**
  - `check_permission()` - allow/deny
  - Role hierarchies
  - Resource-level ACLs

- **CRUD Operations (15 tests)**
  - `grant_permission()`
  - `revoke_permission()`
  - `list_permissions()`
  - Bulk operations

**Estimated:** 25 tests required

---

#### 2.5 Location Privacy (k0/policy/location_privacy.py) - 75 statements
**Current:** 0% | **Target:** 100%

**Test Categories:**
- **Geohash Operations (12 tests)**
  - `lat_lon_to_geohash()`
  - Precision by band
  - Meter precision mapping

- **Masking Application (8 tests)**
  - `mask_location_for_band()`
  - `apply_location_privacy()`

**Estimated:** 20 tests required

---

#### 2.6 Policy Stamp (k0/policy/policy_stamp.py) - 38 statements
**Current:** 0% | **Target:** 100%

**Test Categories:**
- **Serialization (6 tests)**
  - `to_dict()` / `from_dict()`
  - `to_json()` / `from_json()`

- **Envelope Operations (6 tests)**
  - `attach_policy_stamp_to_envelope()`
  - `extract_policy_stamp()`

**Estimated:** 12 tests required

---

### PHASE 3: Transactions & Storage (Week 3)
**Target:** 95% coverage
**Est. Tests:** 60-80 tests
**Priority:** 🔴 CRITICAL

#### 3.1 UnitOfWork (k0/uow/unit_of_work.py) - 138 statements
**Current:** 25% | **Target:** 95%+

**Test Categories:**
- **Transaction Lifecycle (15 tests)**
  - `__enter__()` / `__exit__()`
  - COMMIT success
  - ROLLBACK on exception
  - Nested transactions

- **WAL Operations (12 tests)**
  - `append_wal()`
  - Fsync behavior
  - Write failures

- **Outbox Operations (10 tests)**
  - `stage_outbox()`
  - Flush behavior

- **Receipt Operations (10 tests)**
  - `save_receipt()`
  - Receipt generation

- **Hooks & Callbacks (8 tests)**
  - `add_commit_hook()`
  - Hook execution order
  - Hook failures

**Estimated:** 55 tests required

---

#### 3.2 Connection Pool (k0/uow/connection_pool.py) - 155 statements
**Current:** 14% | **Target:** 85%+

**Test Categories:**
- **Pool Management (12 tests)**
  - `acquire()` / `release()`
  - Connection limits
  - Timeout behavior
  - Pool exhaustion

- **Connection Lifecycle (10 tests)**
  - Creation
  - Reuse
  - Eviction
  - Health checks

**Estimated:** 22 tests required

---

#### 3.3 Receipt Issuer (k0/receipts/issuer.py) - 82 statements
**Current:** 0% | **Target:** 90%+

**Test Categories:**
- **Receipt Generation (15 tests)**
  - `issue()` happy path
  - Obligation normalization
  - Signature generation
  - Timestamp handling

- **Telemetry (5 tests)**
  - Metrics emission
  - Observability events

**Estimated:** 20 tests required

---

### PHASE 4: QoS & Scheduling (Week 4)
**Target:** 90% coverage
**Est. Tests:** 40-50 tests
**Priority:** 🟠 HIGH

#### 4.1 Scheduler (k0/qos/scheduler.py) - 48 statements
**Current:** 31% | **Target:** 90%+

**Test Categories:**
- **Token Management (12 tests)**
  - `acquire()` success/failure
  - `release()` behavior
  - Token limits by port/band

- **Fairness Algorithm (10 tests)**
  - Weighted Deficit Round Robin
  - Band priorities
  - Starvation prevention

**Estimated:** 22 tests required

---

#### 4.2 QoS Context (k0/qos/context.py) - 19 statements
**Current:** 35% | **Target:** 90%+

**Test Categories:**
- **Budget Management (8 tests)**
  - `consume_fanout()`
  - `consume_top_k()`
  - Budget exhaustion

- **Tightening (6 tests)**
  - `tighten()` from obligations

**Estimated:** 14 tests required

---

#### 4.3 QoS Policy (k0/qos/policy.py) - 55 statements
**Current:** 12% | **Target:** 90%+

**Test Categories:**
- **Obligation Processing (10 tests)**
  - `apply_qos_obligations()`
  - Tightening extraction
  - Value coercion

**Estimated:** 10 tests required

---

#### 4.4 QoS Metrics (k0/qos/metrics.py) - 23 statements
**Current:** 36% | **Target:** 90%+

**Test Categories:**
- **Metrics Recording (8 tests)**
  - Acquisition metrics
  - Rejection metrics
  - Port utilization

**Estimated:** 8 tests required

---

### PHASE 5: Bus & SSE (Week 5)
**Target:** 85% coverage
**Est. Tests:** 50-60 tests
**Priority:** 🟠 MEDIUM

#### 5.1 Bus Core (k0/bus/core.py) - 120 statements
**Current:** 23% | **Target:** 85%+

**Test Categories:**
- **Message Dispatch (15 tests)**
  - `dispatch()` single/batch
  - Topic routing
  - Band resolution

- **Sink Registration (8 tests)**
  - `register_sink()`
  - Multi-sink fanout

- **Middleware Chain (12 tests)**
  - `register_middleware()`
  - Execution order
  - Error handling

**Estimated:** 35 tests required

---

#### 5.2 SSE Server (k0/sse/server.py) - 188 statements
**Current:** 0% | **Target:** 85%+

**Test Categories:**
- **Subscription (15 tests)**
  - `subscribe()` flow
  - ACL checks
  - Cursor management

- **Backpressure (10 tests)**
  - `evaluate_backpressure()`
  - Levels (normal/warning/throttle/shed)

- **Acknowledgment (8 tests)**
  - `acknowledge()` updates
  - Cursor advancement

**Estimated:** 33 tests required

---

#### 5.3 Bus Middleware (k0/bus/middleware.py) - 49 statements
**Current:** 19% | **Target:** 85%+

**Test Categories:**
- **Middleware Functions (8 tests)**
  - Timestamp injection
  - Latency metrics
  - Tracing context

**Estimated:** 8 tests required

---

### PHASE 6: Ports (HTTP Layer) (Week 6)
**Target:** 80% coverage
**Est. Tests:** 60-80 tests
**Priority:** 🟢 MEDIUM

*Note: Integration tests already validate behavior. Unit tests boost local coverage metrics.*

#### 6.1 Command Port (k0/ports/command.py) - 414 statements
**Current:** 0% (integration tests hit Docker) | **Target:** 80%+

**Strategy:** Create unit tests with mocked dependencies

**Test Categories:**
- **Envelope Processing (20 tests)**
  - `submit_command()` happy path
  - Body extraction/normalization
  - State component resolution

- **Error Handling (15 tests)**
  - `_error_response()` variants
  - Validation failures
  - QoS rejections

- **QoS Integration (10 tests)**
  - Budget computation
  - Scheduler cost calculation
  - Telemetry emission

**Estimated:** 45 tests required

---

#### 6.2 Query Port (k0/ports/query.py) - 361 statements
**Current:** 0% | **Target:** 80%+

**Test Categories:**
- **Recall Queries (20 tests)**
  - `query_recall()` execution
  - Selector validation
  - Result aggregation

- **Policy Integration (12 tests)**
  - Policy envelope building
  - Capability merging
  - Band enforcement

- **Streaming (10 tests)**
  - `_should_stream()` logic
  - `_stream_query_response()`

**Estimated:** 42 tests required

---

#### 6.3 SSE Port (k0/ports/sse.py) - 210 statements
**Current:** 0% | **Target:** 80%+

**Test Categories:**
- **Subscribe Endpoint (15 tests)**
  - `subscribe()` flow
  - Topic parsing
  - Band resolution

- **Acknowledge Endpoint (8 tests)**
  - `acknowledge()` processing
  - Cursor updates

- **Backpressure (10 tests)**
  - Advisory generation
  - Event emission

**Estimated:** 33 tests required

---

#### 6.4 Observability Port (k0/ports/observe.py) - 130 statements
**Current:** 0% | **Target:** 75%+

**Test Categories:**
- **Health Probes (6 tests)**
  - `/healthz` endpoint
  - `/readyz` endpoint
  - `/metrics` endpoint

- **Emit Endpoint (8 tests)**
  - `POST /k0/obs.emit`
  - Log ingestion

**Estimated:** 14 tests required

---

#### 6.5 Driver Port (k0/ports/drivers.py) - 98 statements
**Current:** 0% | **Target:** 75%+

**Test Categories:**
- **Handshake (10 tests)**
  - `driver_handshake()` flow
  - Session creation
  - Lease management

**Estimated:** 10 tests required

---

## Test Infrastructure Requirements

### Fixtures & Harnesses
- ✅ **In-memory SQLite databases** (working)
- ✅ **Minimal envelope fixtures** (working)
- ⚠️ **Policy manifest fixtures** (needed)
- ⚠️ **Device provisioning fixtures** (needed)
- ⚠️ **Schema registry fixtures** (needed)
- ⚠️ **Cryptographic key fixtures** (needed)
- ⚠️ **UnitOfWork test harness** (needed)

### Mock Objects
- ⚠️ **Mock MetricsExporter** (needed)
- ⚠️ **Mock ObservabilityEmitter** (needed)
- ⚠️ **Mock BusDispatcher** (needed)
- ⚠️ **Mock QoSContext** (needed)

---

## Execution Timeline

| Phase | Duration | Tests | Statements | Priority |
|-------|----------|-------|------------|----------|
| Phase 1 | Week 1 | 100 | 524 | 🔴 CRITICAL |
| Phase 2 | Week 2 | 140 | 802 | 🔴 CRITICAL |
| Phase 3 | Week 3 | 80 | 375 | 🔴 CRITICAL |
| Phase 4 | Week 4 | 50 | 145 | 🟠 HIGH |
| Phase 5 | Week 5 | 60 | 357 | 🟠 MEDIUM |
| Phase 6 | Week 6 | 80 | 1213 | 🟢 MEDIUM |
| **TOTAL** | **6 weeks** | **510** | **3416** | - |

---

## Success Metrics

### Coverage Targets by Tier
- ✅ **TIER 1 (Security):** 100% coverage
- ✅ **TIER 2 (Policy):** 100% coverage
- ✅ **TIER 3 (Storage):** 95% coverage
- ✅ **TIER 4 (QoS):** 90% coverage
- ✅ **TIER 5 (Bus/SSE):** 85% coverage
- ✅ **TIER 6 (Ports):** 80% coverage

### Quality Gates
- ✅ All tests must pass
- ✅ No mocked behavior in critical paths
- ✅ Zero-simulation principle (real components only)
- ✅ Contract-aligned (use actual schemas)
- ✅ Fast execution (<10s per 100 tests)

---

## Current Progress

### Completed
- ✅ MinimalGate initialization tests (23/23)
- ✅ Idempotency ledger tests (20/20)
- ✅ HMAC idem tests (18/18)
- ✅ Full envelope signature tests (13/13)
- ✅ Command port integration tests (27/27)

### In Progress
- 🔄 MinimalGate validate() tests (0/50)
- 🔄 SchemaRegistry tests (0/33)
- 🔄 Security/crypto edge cases (0/8)

### Blocked
- ⚠️ All policy tests (no fixtures yet)
- ⚠️ UnitOfWork tests (harness needed)
- ⚠️ Port unit tests (mock infrastructure needed)

---

## Next Actions

### Immediate (Week 1)
1. **Create fixture library** for MinimalGate tests:
   - Complete envelopes with signatures
   - Device provisioning records
   - Schema registry entries
   - Policy manifests

2. **Write MinimalGate validate() tests** (50 tests):
   - All rejection paths (15 error codes)
   - Signature verification
   - Schema validation
   - Replay detection

3. **Complete SchemaRegistry tests** (33 tests):
   - CRUD operations
   - Status transitions
   - Cache behavior

4. **Finish idem/security tests** (18 tests):
   - Edge cases
   - Error handling

### Week 2 Priority
- Policy engine foundation (PEP + redaction)
- Establish mock infrastructure
- Create policy manifest fixtures

---

## References
- Architecture diagram: `architecture_diagrams/k0/k0_source_of_truth.mmd`
- Coverage summary: `docs/development/coverage-boost-summary.md`
- Test guidelines: `.github/instructions/tests.instructions.md`
- Zero-simulation principle: `.github/copilot-instructions.md`
