# L5 Infrastructure - Sequential Implementation Plan

**Generated:** 2025-10-28  
**Layer:** `k1/l5_infrastructure/`  
**Approach:** Single-developer, strictly sequential (one Issue unlocks next)  
**Mode:** Fast path (stub-based planning)

---

## 📊 Executive Summary

**Total Components:** 67 Python files  
**Status:** 72 files contain STUB markers (`NotImplementedError`, `STUB`, `NEEDS_IMPLEMENTATION`)  
**Contracts Found:** 1 config file (`rate_limiting/config.yml`), contract references in headers  
**Dependencies:** K0 Bridge ports, K1 contracts, external (asyncio, prometheus_client, opentelemetry)

---

## 🏗️ Component Inventory

### Layer Structure (14 Subsystems)

```
k1/l5_infrastructure/
├── admission/          (4 files)  - Admission control & validation
├── backpressure/       (10 files) - Backpressure cascade coordination  
├── caching/            (8 files)  - Multi-level KV cache
├── event_bus/          (4 files)  - Internal pub/sub messaging
├── extensions/         (12 files) - Plugin framework & extension points
├── modules/            (3 files)  - Dynamic module discovery/loading
├── observability/      (6 files)  - Metrics/traces/logs forwarding to K0
├── placement/          (8 files)  - Model placement cascade engine
├── rate_limiting/      (5 files)  - Token bucket rate limiting
├── resilience/         (17 files) - Circuit breakers & fault tolerance
├── scheduling/         (3 files)  - Task scheduling with WFQ
├── serialization/      (7 files)  - FlatBuffers serialization
├── storage/            (4 files)  - Multi-tier storage (Hot/Warm/Cold)
└── thermal/            (6 files)  - Thermal management & throttling
```

### Component Classification

| Component | Type | Path | Status | ADRs | Notes |
|-----------|------|------|--------|------|-------|
| **ADMISSION** |
| `__init__.py` | Service | admission/ | STUB | ADR-0032 | Export AdmissionController |
| `admission_controller.py` | Service | admission/ | STUB | ADR-0032, 0002c, 0028, 0030, 0031 | Core admission decision engine |
| `policies.py` | Model | admission/ | STUB | ADR-0032 | Admission policy definitions |
| `task_validator.py` | Adapter | admission/ | STUB | ADR-0032 | Schema validation |
| **BACKPRESSURE** |
| `__init__.py` | Service | backpressure/ | IMPL | - | Export coordinator |
| `backpressure_manager.py` | Service | backpressure/ | STUB | ADR-0028, 0061 | Watermark-based coordination |
| `cascade_actions.py` | Model | backpressure/ | STUB | ADR-0028c, 0061 | Action triggers |
| `cascade_coordinator.py` | Service | backpressure/ | IMPL | ADR-0061 | Global cascade orchestrator |
| `global_limits_enforcer.py` | Service | backpressure/ | IMPL | ADR-0061 | Global limit enforcement |
| `metrics.py` | Adapter | backpressure/ | STUB | ADR-0061b | Backpressure metrics |
| `privacy_override.py` | Model | backpressure/ | STUB | ADR-0039, 0061c | Privacy band overrides |
| `voice_pipeline_monitor.py` | Adapter | backpressure/ | IMPL | ADR-0057 | Voice pipeline monitoring |
| `watermark_checker.py` | Service | backpressure/ | IMPL | ADR-0061a | Watermark threshold checks |
| `watermark_tracker.py` | Service | backpressure/ | STUB | ADR-0061a | Watermark state tracking |
| **CACHING** |
| `__init__.py` | Service | caching/ | STUB | ADR-0028d | Export KVCache |
| `cache_integration.py` | Adapter | caching/ | STUB | ADR-0025, 0028d | K0 persistence integration |
| `cache_warmer.py` | Service | caching/ | STUB | ADR-0025c | Cache warming/prefetch |
| `connection_pool.py` | Runtime | caching/ | STUB | ADR-0028d | Connection pooling |
| `in_memory_cache.py` | Service | caching/ | STUB | ADR-0028d, 0025 | In-memory cache |
| `kv_cache.py` | Contract | caching/ | STUB | ADR-0028d | KV cache abstraction |
| `kv_cache_local.py` | Service | caching/ | STUB | ADR-0028d | Local cache implementation |
| `persistent_cache.py` | Service | caching/ | STUB | ADR-0028d | Persistent cache |
| **EVENT_BUS** |
| `__init__.py` | Service | event_bus/ | IMPL | ADR-0048 | Export EventBus |
| `event_bus.py` | Service | event_bus/ | STUB | ADR-0048, 0045a | Internal pub/sub |
| `schemas.py` | Model | event_bus/ | STUB | ADR-0048 | Event schemas |
| `subscribers.py` | Model | event_bus/ | STUB | ADR-0048 | Subscriber registry |
| **EXTENSIONS** |
| `__init__.py` | Service | extensions/ | STUB | ADR-0034, 0075 | Export ExtensionRegistry |
| `circuit_breaker_strategy.py` | Extension | extensions/ | STUB | ADR-0075 | Circuit breaker extension point |
| `config_provider.py` | Extension | extensions/ | STUB | ADR-0075, 0080 | Config provider extension |
| `extension_registry.py` | Service | extensions/ | STUB | ADR-0034, 0075 | Extension registry |
| `log_handler.py` | Extension | extensions/ | STUB | ADR-0075 | Log handler extension |
| `metrics_exporter.py` | Extension | extensions/ | STUB | ADR-0075 | Metrics exporter extension |
| `performance_optimizer.py` | Extension | extensions/ | STUB | ADR-0075 | Performance optimizer extension |
| `placement_strategy.py` | Extension | extensions/ | STUB | ADR-0075, 0027 | Placement strategy extension |
| `security_policy.py` | Extension | extensions/ | STUB | ADR-0075 | Security policy extension |
| `storage_tier.py` | Extension | extensions/ | STUB | ADR-0075, 0020 | Storage tier extension |
| `thermal_policy.py` | Extension | extensions/ | STUB | ADR-0075, 0026 | Thermal policy extension |
| `trace_exporter.py` | Extension | extensions/ | STUB | ADR-0075 | Trace exporter extension |
| **MODULES** |
| `__init__.py` | Service | modules/ | STUB | ADR-0074 | Export PluginDiscovery |
| `plugin_discovery.py` | Service | modules/ | STUB | ADR-0074 | Plugin discovery |
| `plugin_loader.py` | Service | modules/ | STUB | ADR-0074 | Plugin loader with hot-reload |
| **OBSERVABILITY** |
| `__init__.py` | Service | observability/ | STUB | ADR-0001a, 0029 | Export metrics/traces/logs |
| `k0_client.py` | Adapter | observability/ | STUB | ADR-0001a | K0 observability port client |
| `logging.py` | Adapter | observability/ | STUB | ADR-0001a | Structured logging |
| `metrics.py` | Adapter | observability/ | STUB | ADR-0029, 0029d | Prometheus metrics |
| `tracing.py` | Adapter | observability/ | STUB | ADR-0030, 0001a | OpenTelemetry tracing |
| **PLACEMENT** |
| `__init__.py` | Service | placement/ | IMPL | ADR-0027 | Export PlacementEngine |
| `capability_matcher.py` | Service | placement/ | STUB | ADR-0027a | Capability matching |
| `cascade_engine.py` | Service | placement/ | STUB | ADR-0027, 0027a | Placement cascade NPU→GPU→CPU→Remote |
| `circuit_breaker.py` | Adapter | placement/ | STUB | ADR-0027, 0009 | Circuit breaker integration |
| `cost_tracker.py` | Service | placement/ | IMPL | ADR-0031, 0027c | Cost tracking |
| `device_capabilities.py` | Model | placement/ | IMPL | ADR-0027a | Device capability model |
| `failover.py` | Service | placement/ | IMPL | ADR-0027b | Automatic failover |
| `provider_adapter.py` | Adapter | placement/ | IMPL | ADR-0027a | Provider adapter abstraction |

| **RATE_LIMITING** |
| `__init__.py` | Service | rate_limiting/ | IMPL | ADR-0030 | Export RateLimiter |
| `config.yml` | Contract | rate_limiting/ | IMPL | ADR-0030 | Rate limit configuration |
| `feature_flags.py` | Model | rate_limiting/ | IMPL | ADR-0030 | Feature flag controls |
| `rate_limiter.py` | Service | rate_limiting/ | IMPL | ADR-0030 | Token bucket implementation |
| `token_bucket.py` | Model | rate_limiting/ | IMPL | ADR-0030 | Token bucket algorithm |
| **RESILIENCE** |
| `__init__.py` | Service | resilience/ | IMPL | ADR-0009 | Export CircuitBreaker |
| `call_wrapper.py` | Adapter | resilience/ | STUB | ADR-0009 | Protected call wrapper |
| `circuit_breaker_manager.py` | Service | resilience/ | STUB | ADR-0009, 0009a, 0009b, 0009c | Core circuit manager |
| `circuit_fsm.py` | Model | resilience/ | STUB | ADR-0009a | Circuit FSM (CLOSED/OPEN/HALF_OPEN) |
| `config_loader.py` | Adapter | resilience/ | IMPL | ADR-0009b | Config hot-reload |
| `failure_recorder.py` | Service | resilience/ | IMPL | ADR-0009 | Failure recording |
| `fallbacks/alternate_service.py` | Adapter | resilience/ | STUB | ADR-0009a | Fallback to alternate service |
| `fallbacks/cached_response.py` | Adapter | resilience/ | IMPL | ADR-0009a | Fallback to cached response |
| `fallbacks/default_response.py` | Adapter | resilience/ | IMPL | ADR-0009a | Fallback to default response |
| `fallbacks/degraded_mode.py` | Adapter | resilience/ | IMPL | ADR-0009a | Fallback to degraded mode |
| `recovery_strategies.py` | Model | resilience/ | IMPL | ADR-0009a | Recovery strategy definitions |
| `state_persistence.py` | Adapter | resilience/ | STUB | ADR-0009 | Redis-backed state persistence |
| `timeout_handler.py` | Service | resilience/ | IMPL | ADR-0009 | Timeout handling |
| **SCHEDULING** |
| `__init__.py` | Service | scheduling/ | IMPL | ADR-0031 | Export Scheduler |
| `scheduler.py` | Service | scheduling/ | IMPL | ADR-0031 | Task scheduler |
| `weighted_queue.py` | Model | scheduling/ | IMPL | ADR-0028, 0028a | WFQ implementation |
| **SERIALIZATION** |
| `__init__.py` | Service | serialization/ | IMPL | ADR-0011 | Export Serializer |
| `buffer_pool.py` | Runtime | serialization/ | IMPL | ADR-0011c | Buffer pooling |
| `deserializer.py` | Adapter | serialization/ | STUB | ADR-0011 | FlatBuffers deserializer |
| `serializer.py` | Adapter | serialization/ | STUB | ADR-0011 | FlatBuffers serializer |
| `string_dedup.py` | Runtime | serialization/ | STUB | ADR-0011c | String deduplication |
| `zero_copy.py` | Runtime | serialization/ | IMPL | ADR-0011c | Zero-copy operations |
| **STORAGE** |
| `__init__.py` | Service | storage/ | IMPL | ADR-0020 | Export StorageTierManager |
| `lifecycle_manager.py` | Service | storage/ | IMPL | ADR-0020, 0021 | Lifecycle management |
| `tier_manager.py` | Service | storage/ | IMPL | ADR-0020 | Multi-tier storage manager |
| `tiers.py` | Model | storage/ | IMPL | ADR-0020a, 0020b, 0020c | Tier definitions (Hot/Warm/Cold) |
| **THERMAL** |
| `__init__.py` | Service | thermal/ | IMPL | ADR-0026 | Export ThermalManager |
| `capability_assessor.py` | Service | thermal/ | IMPL | ADR-0026a | Device capability assessment |
| `hysteresis.py` | Model | thermal/ | IMPL | ADR-0026b | Hysteresis state machine |
| `sensor_monitor.py` | Adapter | thermal/ | IMPL | ADR-0026a | Sensor monitoring |
| `thermal_manager.py` | Service | thermal/ | IMPL | ADR-0026 | Thermal management orchestrator |
| `throttling.py` | Service | thermal/ | IMPL | ADR-0026d | Thermal-aware throttling |

---

## 🔍 Dependency Analysis

### External Dependencies
- `asyncio` - Async runtime (core)
- `typing` - Type hints (core)
- `prometheus_client` - Metrics (Counter, Gauge, Histogram)
- `opentelemetry-api` - Tracing API
- `opentelemetry-sdk` - Tracing SDK & exporters
- `structlog` - Structured logging
- `dataclasses` - Data structures
- `enum` - State enums
- `redis` (optional) - Circuit breaker state persistence

### Internal K1 Dependencies
- `k1.bridge_k0.*` - K0 Bridge ports (Command, Query, SSE, Observability)
- `k1.contracts.*` - FlatBuffers schemas & API contracts
- `k1.l4_runtime.*` - SessionState, Actor mailbox
- `k1.l3_execution.*` - Model Hub, Tool Runner
- `k1.l2_orchestration.*` - Orchestrator
- `k1.l1_input.*` - Request Router

### Upstream Consumers (depend on L5)
- `k1.l4_runtime.*` - All infrastructure services
- `k1.l3_execution.*` - Admission, scheduling, caching
- `k1.l2_orchestration.*` - Observability, resilience
- `k1.l1_input.*` - Rate limiting, validation

### Local Dependency Map (within L5)

**Core Foundation (no internal deps):**
- `observability/*` - Metrics, traces, logs (K0 adapter only)
- `event_bus/schemas.py` - Event definitions
- `extensions/extension_registry.py` - Extension framework base

**Tier 1 (depends on observability only):**
- `caching/kv_cache.py` - KV cache contract
- `resilience/circuit_fsm.py` - Circuit FSM model
- `serialization/serializer.py` - FlatBuffers serializer
- `thermal/sensor_monitor.py` - Sensor monitoring

**Tier 2 (depends on Tier 1):**
- `backpressure/watermark_tracker.py` - Uses metrics
- `rate_limiting/rate_limiter.py` - Uses metrics
- `resilience/circuit_breaker_manager.py` - Uses circuit_fsm + metrics
- `caching/in_memory_cache.py` - Uses kv_cache + metrics

**Tier 3 (depends on Tier 2):**
- `admission/admission_controller.py` - Uses rate_limiter, backpressure, metrics
- `placement/cascade_engine.py` - Uses thermal, circuit_breaker, metrics
- `scheduling/scheduler.py` - Uses backpressure, metrics

**Tier 4 (integration layer):**
- `modules/plugin_loader.py` - Uses extensions, caching
- `backpressure/cascade_coordinator.py` - Uses watermark_tracker, privacy_override

---

## 🚧 STUB Analysis (72 files with NotImplementedError)

**High Stub Density (7 matches):**
- `resilience/circuit_breaker_manager.py` - Core circuit manager (CRITICAL)

**Medium Stub Density (5 matches):**
- `resilience/call_wrapper.py` - Protected call wrapper

**Medium Stub Density (3 matches):**
- `event_bus/schemas.py` - Event schema definitions
- `serialization/serializer.py` - FlatBuffers serializer
- `serialization/string_dedup.py` - String deduplication

**Light Stub Density (1-2 matches):**
- All other components (standard TODOs/NotImplementedError placeholders)

---

## 🎯 Performance Budgets (P95 Targets)

From ADR-0024 and component headers:

### Infrastructure Layer (L5)
- **Admission decision:** <10ms
- **Cache operations:** <0.1ms (100µs)
- **Circuit lookup:** <1ms
- **State transition (circuit):** <1ms
- **Metric emission:** <1ms
- **Trace span creation:** <0.5ms
- **Log emission:** <0.3ms
- **Plugin discovery (50 modules):** <500ms (cold)
- **Plugin load (warm):** <10ms
- **Storage promotion (tier):** <10ms
- **Storage archival:** <50ms
- **Rate limit check:** <5ms
- **Scheduler enqueue:** <5ms
- **Thermal assessment:** <10ms
- **Serialization (1KB):** <10ms

### Critical Path Budgets
- **TTFT:** ≤150ms (end-to-end)
- **E2E latency:** ≤2000ms
- **K0 WAL write:** ≤100ms
- **K0 recall:** ≤120ms

---

## 🛡️ Policy Enforcement

### Privacy Bands (from .windsurfrules)
- **GREEN:** Public/shareable data
- **AMBER:** Household-private data
- **RED:** User-private data
- **BLACK:** Encrypted/sealed data

All components MUST:
1. Propagate `cognitive_trace_id` in all operations
2. Respect privacy band constraints (no cross-band leakage)
3. Include ADR references in code comments
4. NO simulation code (`asyncio.sleep`, `time.sleep`, mocks in prod paths)
5. Emit structured logs with trace correlation
6. Implement contract-compliant interfaces

---

## 📋 ADR Coverage

Key ADRs for L5 Infrastructure:
- **ADR-0001a:** K0 Bridge Architecture (Observability Port)
- **ADR-0009:** Circuit Breaker Pattern (3-state FSM)
- **ADR-0020:** Multi-Tier Storage (Hot/Warm/Cold)
- **ADR-0024:** Performance Budgets (P95 targets)
- **ADR-0025:** KV Cache Management (512MB budget)
- **ADR-0026:** Thermal Hysteresis Matrix
- **ADR-0027:** Model Placement Cascade
- **ADR-0028:** Weighted Fair Queuing Scheduler
- **ADR-0028d:** Local In-Memory Cache with K0 Persistence
- **ADR-0029:** Prometheus Metrics (RED method)
- **ADR-0030:** Intelligent Trace Sampling
- **ADR-0031:** Cost Tracking Per Session
- **ADR-0032:** Admission Control Design (MISSING - need to check number)
- **ADR-0034:** Extensions Framework Design
- **ADR-0048:** K1 Internal Event Bus
- **ADR-0061:** 3-Tier Backpressure Cascade
- **ADR-0074:** Pluggable Module System
- **ADR-0075:** Layer 5 Extensibility Framework

---

## 📦 Contracts & Config

**Found Contracts:**
- `k1/contracts/infrastructure/backpressure/*` (19 items)
- `k1/contracts/observability/*` (31 items)
- `k1/contracts/k0_bridge/*` (28 items)
- `k1/contracts/event_bus/*` (6 items)
- `k1/contracts/thermal/*` (13 items)

**Config Files:**
- `k1/l5_infrastructure/rate_limiting/config.yml` - Rate limit configuration

---

## 🔄 Execution Strategy

**Ordering Principles:**
1. **Contracts & Models first** (no dependencies)
2. **Core Runtime** (schedulers, queues, batching, conn-mgr)
3. **Observability early** (enable metrics/traces for all following work)
4. **Adapters/Bridge Clients** (HTTP/2, SSE, K0 ports)
5. **Service Layer** (business logic using foundation)
6. **Extensions & Integrations** (build on core services)
7. **Hardening & Perf** (budgets, retries, edge cases)

**Strict Sequential Constraint:**
- Each Issue completes ONE file (or tightly coupled pair)
- Next Issue BLOCKED until current Done criteria met
- Tests written IMMEDIATELY after implementation (paired Issues)
- No parallel branches unless unavoidable

---

## 🎯 Milestones Overview

We'll organize work into 5 major milestones:

- **M1: Foundation & Observability** (Contracts, Models, Metrics/Traces/Logs)
- **M2: Core Runtime Services** (Caching, Scheduling, Batching, Queues)
- **M3: Control Plane** (Admission, Backpressure, Rate Limiting)
- **M4: Resilience & Integration** (Circuit Breakers, Event Bus, Extensions)
- **M5: Hardening & Performance** (Perf budgets, edge cases, integration tests)

---

# 📍 MILESTONE 1: Foundation & Observability

**Goal:** Establish observability foundation (metrics/traces/logs), core models, and K0 bridge adapters  
**Dependencies:** None (foundation layer)  
**Acceptance Criteria:**
- All observability primitives functional (emit_metric, create_span, emit_log)
- K0 observability port client operational
- Event bus schemas defined
- Core models (enums, dataclasses) implemented
- All M1 tests passing (`pytest tests/k1/l5_infrastructure/test_observability*.py`)

---

## Epic 1.1: Observability - Metrics Emission

**Goal:** Implement Prometheus metrics forwarding to K0  
**Components:** `observability/metrics.py`, `observability/k0_client.py` (partial)  
**ADRs:** ADR-0029, ADR-0029d, ADR-0001a  

### Issue #M1-1: Implement metrics.py core functions

**Why:** Foundation for all infrastructure metrics; needed by every subsequent component  
**Inputs:**
- ADR-0029 (Prometheus Metrics - RED method)
- ADR-0029d (Infrastructure metrics taxonomy)
- Existing stub: `k1/l5_infrastructure/observability/metrics.py`

**Steps:**
1. Implement `emit_counter(name, value, labels)` - Counter metric emission
2. Implement `emit_gauge(name, value, labels)` - Gauge metric emission
3. Implement `emit_histogram(name, value, labels, buckets)` - Histogram metric emission
4. Add metric name validation (enforce `k1.<layer>.<component>.<metric>` pattern)
5. Add standard label injection (`cognitive_trace_id`, `session_id`, `privacy_band`)
6. Add in-memory metric registry (dict-based; K0 forwarding comes next)
7. Add docstrings with usage examples

**Observability:**
- Metrics: N/A (this IS the metric system)
- Traces: Add trace correlation in labels
- Logs: Log metric emission errors

**Perf/Policy:**
- Metric emission: <1ms P95
- No blocking I/O (async forwarding in separate Issue)
- Privacy: Redact PII from labels

**Done Criteria:**
- [ ] All 3 metric types functional (counter/gauge/histogram)
- [ ] Metric name validation enforces naming convention
- [ ] Standard labels auto-injected
- [ ] Zero `NotImplementedError` or `pass` stubs
- [ ] Docstrings complete with examples
- [ ] No `asyncio.sleep` or simulation code

**Blocked By:** None  
**Unlocks:** M1-2 (metrics tests)

---

### Issue #M1-2: Write metrics.py integration tests

**Why:** Validate metric emission, name validation, label injection  
**Inputs:**
- Completed `observability/metrics.py` (Issue M1-1)
- ADR-0029 (testing requirements)

**Steps:**
1. Create `tests/k1/l5_infrastructure/test_observability_metrics.py`
2. Test `emit_counter` increments correctly
3. Test `emit_gauge` sets values correctly
4. Test `emit_histogram` records distributions
5. Test metric name validation rejects invalid names
6. Test standard label injection (trace_id, session_id, band)
7. Test privacy redaction in labels
8. Add performance assertion (<1ms emission time)

**Done Criteria:**
- [ ] 15+ test cases covering all metric types
- [ ] Performance budget verified (<1ms P95)
- [ ] All tests pass: `pytest tests/k1/l5_infrastructure/test_observability_metrics.py -v`
- [ ] Coverage ≥90% for `metrics.py`

**Blocked By:** M1-1  
**Unlocks:** M1-3 (tracing implementation)

---

## Epic 1.2: Observability - Distributed Tracing

**Goal:** Implement OpenTelemetry tracing with K0 forwarding  
**Components:** `observability/tracing.py`, `observability/k0_client.py` (partial)  
**ADRs:** ADR-0030, ADR-0001a  

### Issue #M1-3: Implement tracing.py core functions

**Why:** Enable distributed tracing across K1 components  
**Inputs:**
- ADR-0030 (Intelligent Trace Sampling)
- ADR-0001a (K0 Bridge observability port)
- Existing stub: `k1/l5_infrastructure/observability/tracing.py`
- Completed metrics.py (M1-1) for reference pattern

**Steps:**
1. Implement `create_span(name, attributes)` - Context manager for spans
2. Implement `get_current_trace_id()` - Extract cognitive_trace_id
3. Implement `set_trace_attribute(key, value)` - Add span attributes
4. Implement `record_exception(exception)` - Record exception in span
5. Add OpenTelemetry SDK initialization
6. Add in-memory span exporter (K0 forwarding in M1-5)
7. Add sampling config (head-based: 1% baseline, 100% errors)
8. Add docstrings and usage examples

**Observability:**
- Metrics: `k1.observability.spans_created_total`, `k1.observability.trace_export_errors`
- Traces: Self-tracing (trace the tracer initialization)
- Logs: Log export failures

**Perf/Policy:**
- Span creation: <0.5ms P95
- No blocking exports
- Privacy: Sanitize attributes per privacy band

**Done Criteria:**
- [ ] `create_span` context manager functional
- [ ] `cognitive_trace_id` propagation working
- [ ] Sampling configured (1% baseline)
- [ ] Zero `NotImplementedError`
- [ ] Docstrings complete

**Blocked By:** M1-2  
**Unlocks:** M1-4 (tracing tests)

---

### Issue #M1-4: Write tracing.py integration tests

**Why:** Validate span creation, sampling, attribute injection  
**Inputs:**
- Completed `observability/tracing.py` (M1-3)

**Steps:**
1. Create `tests/k1/l5_infrastructure/test_observability_tracing.py`
2. Test `create_span` creates valid spans
3. Test `get_current_trace_id` returns correct ID
4. Test `set_trace_attribute` adds attributes
5. Test `record_exception` captures exceptions
6. Test sampling (1% baseline, 100% errors)
7. Test span nesting (parent-child relationships)
8. Add performance assertion (<0.5ms span creation)

**Done Criteria:**
- [ ] 12+ test cases
- [ ] Performance budget verified (<0.5ms P95)
- [ ] All tests pass: `pytest tests/k1/l5_infrastructure/test_observability_tracing.py -v`
- [ ] Coverage ≥90%

**Blocked By:** M1-3  
**Unlocks:** M1-5 (logging implementation)

---

## Epic 1.3: Observability - Structured Logging

**Goal:** Implement structured logging with K0 forwarding  
**Components:** `observability/logging.py`, `observability/k0_client.py` (partial)  
**ADRs:** ADR-0001a  

### Issue #M1-5: Implement logging.py core functions

**Why:** Enable structured logging across K1 with trace correlation  
**Inputs:**
- ADR-0001a (K0 Bridge observability)
- Existing stub: `k1/l5_infrastructure/observability/logging.py`
- Completed metrics.py (M1-1) and tracing.py (M1-3)

**Steps:**
1. Implement `get_logger(name)` - Returns configured structlog logger
2. Implement `configure_logging(level, format)` - Global logging config
3. Add automatic `cognitive_trace_id` injection from trace context
4. Add automatic `timestamp`, `level`, `logger` fields
5. Add privacy-aware log scrubbing (redact PII patterns)
6. Add log level filtering (DEBUG/INFO/WARNING/ERROR/CRITICAL)
7. Configure JSON output format (structured)
8. Add K0 log sink placeholder (forwarding in M1-7)

**Observability:**
- Metrics: `k1.observability.logs_emitted_total{level}`
- Traces: Inherit from parent span
- Logs: Bootstrap logging (can't log about logging startup)

**Perf/Policy:**
- Log emission: <0.3ms P95
- Async sink to avoid blocking
- Privacy: Auto-scrub PII (SSN, CC, etc.)

**Done Criteria:**
- [ ] `get_logger` returns functional logger
- [ ] Auto-injection of trace_id, timestamp
- [ ] PII scrubbing functional
- [ ] JSON output format
- [ ] Zero `NotImplementedError`

**Blocked By:** M1-4  
**Unlocks:** M1-6 (logging tests)

---

### Issue #M1-6: Write logging.py integration tests

**Why:** Validate structured logging, trace correlation, PII scrubbing  
**Inputs:**
- Completed `observability/logging.py` (M1-5)

**Steps:**
1. Create `tests/k1/l5_infrastructure/test_observability_logging.py`
2. Test `get_logger` returns configured logger
3. Test automatic trace_id injection
4. Test log level filtering
5. Test PII scrubbing (SSN, credit cards, emails)
6. Test JSON output format
7. Test structured fields (timestamp, level, logger, message)
8. Add performance assertion (<0.3ms emission)

**Done Criteria:**
- [ ] 10+ test cases
- [ ] Performance budget verified (<0.3ms P95)
- [ ] All tests pass: `pytest tests/k1/l5_infrastructure/test_observability_logging.py -v`
- [ ] Coverage ≥90%

**Blocked By:** M1-5  
**Unlocks:** M1-7 (K0 client integration)

---

## Epic 1.4: K0 Bridge - Observability Port Client

**Goal:** Implement K0 observability port adapter for forwarding metrics/traces/logs  
**Components:** `observability/k0_client.py`  
**ADRs:** ADR-0001a, ADR-0044  

### Issue #M1-7: Implement k0_client.py observability adapter

**Why:** Forward observability data to K0 for persistence and aggregation  
**Inputs:**
- ADR-0001a (K0 Bridge Architecture - Observability Port)
- ADR-0044 (K0 Bridge HTTP/2 + FlatBuffers)
- Completed metrics.py (M1-1), tracing.py (M1-3), logging.py (M1-5)
- Existing K0 Bridge HTTP/2 client (from retrieved memory)

**Steps:**
1. Implement `K0ObservabilityClient` class
2. Add `__init__(http2_client, endpoint)` - Initialize with K0 endpoint
3. Add `async send_metrics(metrics_batch)` - Forward metric batch to K0
4. Add `async send_traces(spans_batch)` - Forward trace spans to K0
5. Add `async send_logs(logs_batch)` - Forward log entries to K0
6. Add batching logic (10-50 items or 100ms window per ADR-0022a)
7. Add backpressure handling (queue depth limits)
8. Add retry logic (3 retries with exp backoff)
9. Add circuit breaker integration placeholder
10. Reference ADR-0001a in header comments

**Observability:**
- Metrics: `k1.k0_client.batches_sent_total{type}`, `k1.k0_client.send_errors_total`
- Traces: Trace K0 send operations
- Logs: Log send failures

**Perf/Policy:**
- Batch send: <50ms P95
- Max batch size: 50 items
- Max batch window: 100ms
- Queue depth limit: 1000 items
- Privacy: Preserve band metadata in forwarded data

**Done Criteria:**
- [ ] All 3 send methods functional (metrics/traces/logs)
- [ ] Batching logic implemented (10-50 items, 100ms)
- [ ] Backpressure handling (queue limits)
- [ ] Retry logic (3 retries)
- [ ] ADR-0001a referenced in comments
- [ ] Zero `NotImplementedError`

**Blocked By:** M1-6  
**Unlocks:** M1-8 (K0 client tests)

---

### Issue #M1-8: Write k0_client.py integration tests

**Why:** Validate K0 forwarding, batching, backpressure  
**Inputs:**
- Completed `observability/k0_client.py` (M1-7)

**Steps:**
1. Create `tests/k1/l5_infrastructure/test_observability_k0_client.py`
2. Test `send_metrics` forwards batches to K0 mock
3. Test `send_traces` forwards spans
4. Test `send_logs` forwards log entries
5. Test batching (accumulates 10-50 items or 100ms)
6. Test backpressure (rejects when queue >1000)
7. Test retry logic (3 attempts with backoff)
8. Test error handling (K0 unavailable)
9. Add performance assertions (<50ms batch send)

**Done Criteria:**
- [ ] 12+ test cases
- [ ] Batching logic validated
- [ ] Backpressure tested
- [ ] Performance budget verified (<50ms P95)
- [ ] All tests pass: `pytest tests/k1/l5_infrastructure/test_observability_k0_client.py -v`
- [ ] Coverage ≥85%

**Blocked By:** M1-7  
**Unlocks:** M1-9 (observability __init__.py)

---

## Epic 1.5: Observability - Package Integration

**Goal:** Wire up observability package exports and integration  
**Components:** `observability/__init__.py`  
**ADRs:** ADR-0001a  

### Issue #M1-9: Implement observability/__init__.py exports

**Why:** Expose clean API for rest of K1 infrastructure  
**Inputs:**
- Completed metrics.py (M1-1), tracing.py (M1-3), logging.py (M1-5), k0_client.py (M1-7)
- Existing stub: `k1/l5_infrastructure/observability/__init__.py`

**Steps:**
1. Import and re-export `emit_counter`, `emit_gauge`, `emit_histogram` from metrics
2. Import and re-export `create_span`, `get_current_trace_id`, `set_trace_attribute` from tracing
3. Import and re-export `get_logger`, `configure_logging` from logging
4. Import and re-export `K0ObservabilityClient` from k0_client
5. Add `__all__` list with all exports
6. Update module docstring (status: IMPLEMENTED, remove STUB marker)
7. Add usage examples in docstring

**Done Criteria:**
- [ ] All observability functions exported
- [ ] `__all__` list complete
- [ ] Module docstring updated (IMPLEMENTED)
- [ ] Import test passes: `python -c "from k1.l5_infrastructure.observability import emit_counter, create_span, get_logger"`

**Blocked By:** M1-8  
**Unlocks:** M2-1 (Event bus schemas)

---

## Epic 1.6: Event Bus - Schema Definitions

**Goal:** Define event schemas for internal K1 event bus  
**Components:** `event_bus/schemas.py`  
**ADRs:** ADR-0048  

### Issue #M1-10: Implement event_bus/schemas.py models

**Why:** Foundation for event-driven communication between L5 components  
**Inputs:**
- ADR-0048 (K1 Internal Event Bus)
- Existing stub: `k1/l5_infrastructure/event_bus/schemas.py`

**Steps:**
1. Define `EventType` enum (BACKPRESSURE_ALERT, CIRCUIT_OPEN, CACHE_EVICT, etc.)
2. Define `Event` dataclass (type, source, timestamp, payload, trace_id)
3. Define `BackpressureEvent` dataclass (level, component, watermark)
4. Define `CircuitBreakerEvent` dataclass (service, state, failure_count)
5. Define `CacheEvent` dataclass (operation, key, hit/miss)
6. Add JSON serialization methods (to_dict, from_dict)
7. Add validation (required fields, type checking)
8. Reference ADR-0048 in header

**Observability:**
- Metrics: N/A (schema definitions only)
- Traces: N/A
- Logs: N/A

**Perf/Policy:**
- Serialization: <1ms P95
- Privacy: Mark PII fields for redaction

**Done Criteria:**
- [ ] All event types defined (5+ schemas)
- [ ] `Event` base class complete
- [ ] JSON serialization functional
- [ ] Field validation implemented
- [ ] ADR-0048 referenced
- [ ] Zero `NotImplementedError`

**Blocked By:** M1-9  
**Unlocks:** M1-11 (event schemas tests)

---

### Issue #M1-11: Write event_bus/schemas.py tests

**Why:** Validate event serialization, validation  
**Inputs:**
- Completed `event_bus/schemas.py` (M1-10)

**Steps:**
1. Create `tests/k1/l5_infrastructure/test_event_schemas.py`
2. Test `Event` base class creation
3. Test each event type (BackpressureEvent, CircuitBreakerEvent, CacheEvent)
4. Test JSON serialization (to_dict, from_dict round-trip)
5. Test validation (missing fields, wrong types)
6. Test trace_id propagation
7. Add performance assertion (<1ms serialization)

**Done Criteria:**
- [ ] 10+ test cases
- [ ] All event types tested
- [ ] Serialization round-trip validated
- [ ] Performance budget verified (<1ms P95)
- [ ] All tests pass: `pytest tests/k1/l5_infrastructure/test_event_schemas.py -v`
- [ ] Coverage ≥95%

**Blocked By:** M1-10  
**Unlocks:** M2-1 (Caching foundation)

---

## M1 Summary

**Total Issues:** 11 (M1-1 through M1-11)  
**Estimated Effort:** ~8-10 developer days  
**Critical Path:** M1-1 → M1-2 → M1-3 → M1-4 → M1-5 → M1-6 → M1-7 → M1-8 → M1-9 → M1-10 → M1-11  

**Completion Checklist:**
- [ ] All observability functions operational
- [ ] K0 forwarding adapter functional
- [ ] Event schemas defined
- [ ] All M1 tests passing (33+ tests total)
- [ ] Performance budgets met (metrics <1ms, traces <0.5ms, logs <0.3ms)
- [ ] Zero `NotImplementedError` in M1 components
- [ ] ADR references in all headers

**Next:** M2 - Core Runtime Services (Caching, Serialization)

---

# 📍 MILESTONE 2: Core Runtime Services

**Goal:** Implement core runtime primitives (caching, serialization, event bus)  
**Dependencies:** M1 (Observability)  
**Acceptance Criteria:**
- KV cache abstraction + in-memory implementation functional
- FlatBuffers serialization operational
- Event bus pub/sub functional
- All M2 tests passing (`pytest tests/k1/l5_infrastructure/test_caching*.py tests/k1/l5_infrastructure/test_serialization*.py tests/k1/l5_infrastructure/test_event_bus*.py`)

---

## Epic 2.1: Caching - KV Cache Abstraction

**Goal:** Define KV cache contract and in-memory implementation  
**Components:** `caching/kv_cache.py`, `caching/in_memory_cache.py`  
**ADRs:** ADR-0028d, ADR-0025  

### Issue #M2-1: Implement caching/kv_cache.py contract

**Why:** Define standard interface for all cache implementations  
**Inputs:**
- ADR-0028d (Local In-Memory Cache with K0 Persistence)
- ADR-0025 (KV Cache Management - 512MB budget)
- Completed observability (M1-9)
- Existing stub: `k1/l5_infrastructure/caching/kv_cache.py`

**Steps:**
1. Define `KVCache` abstract base class (ABC)
2. Add abstract methods: `async get(key)`, `async set(key, value, ttl)`, `async delete(key)`
3. Add abstract methods: `async exists(key)`, `async keys(pattern)`
4. Add abstract methods: `async clear()`, `async start()`, `async stop()`
5. Add `CacheStats` dataclass (hits, misses, evictions, size_bytes)
6. Add abstract method: `get_stats() -> CacheStats`
7. Add type hints for all methods
8. Add docstrings with contract guarantees

**Observability:**
- Metrics: N/A (contract only; implementations emit metrics)
- Traces: N/A
- Logs: N/A

**Perf/Policy:**
- Interface definition (no perf impact)
- Privacy: No PII in cache keys (enforce in implementations)

**Done Criteria:**
- [ ] `KVCache` ABC complete with 8+ abstract methods
- [ ] `CacheStats` dataclass defined
- [ ] Type hints on all methods
- [ ] Docstrings describe contract guarantees
- [ ] Zero `NotImplementedError` (use `@abstractmethod`)

**Blocked By:** M1-11  
**Unlocks:** M2-2 (in-memory cache implementation)

---

### Issue #M2-2: Implement caching/in_memory_cache.py

**Why:** Provide fast in-memory cache implementation  
**Inputs:**
- ADR-0028d (in-memory cache design)
- ADR-0025 (LRU/LFU hybrid eviction 60/40)
- Completed kv_cache.py contract (M2-1)
- Existing stub: `k1/l5_infrastructure/caching/in_memory_cache.py`

**Steps:**
1. Create `InMemoryCache(KVCache)` class
2. Implement `__init__(max_size_bytes, eviction_policy="lru")`
3. Implement `async get(key)` - LRU/LFU access tracking
4. Implement `async set(key, value, ttl)` - Store with TTL
5. Implement `async delete(key)` - Remove entry
6. Implement LRU eviction (OrderedDict or custom)
7. Implement TTL expiration (background task every 60s)
8. Implement `get_stats()` - Return hit/miss/eviction counts
9. Add size tracking (track bytes consumed)
10. Add max_size enforcement (evict on overflow)
11. Emit metrics: `k1.cache.hits_total`, `k1.cache.misses_total`, `k1.cache.evictions_total`
12. Reference ADR-0028d in header

**Observability:**
- Metrics: `k1.cache.{hits,misses,evictions,size_bytes}_total`
- Traces: Trace cache operations in `create_span`
- Logs: Log evictions, TTL expirations

**Perf/Policy:**
- Cache get: <0.1ms (100µs) P95
- Cache set: <0.1ms P95
- Max size: 512MB (configurable)
- TTL cleanup: non-blocking background task

**Done Criteria:**
- [ ] All `KVCache` methods implemented
- [ ] LRU eviction functional
- [ ] TTL expiration working (background task)
- [ ] Size tracking accurate
- [ ] Metrics emitted on all operations
- [ ] Performance budgets met (<0.1ms)
- [ ] ADR-0028d referenced
- [ ] Zero `NotImplementedError`

**Blocked By:** M2-1  
**Unlocks:** M2-3 (cache tests)

---

### Issue #M2-3: Write caching tests

**Why:** Validate cache operations, eviction, TTL  
**Inputs:**
- Completed `caching/in_memory_cache.py` (M2-2)

**Steps:**
1. Create `tests/k1/l5_infrastructure/test_caching.py`
2. Test `get/set/delete` basic operations
3. Test LRU eviction (fill cache, verify oldest evicted)
4. Test TTL expiration (set with TTL, wait, verify gone)
5. Test size tracking (verify bytes consumed)
6. Test max_size enforcement (overflow triggers eviction)
7. Test `get_stats()` returns accurate counts
8. Test metrics emission (hits/misses/evictions)
9. Add performance assertions (<0.1ms get/set)
10. Test concurrent access (multiple async tasks)

**Done Criteria:**
- [ ] 15+ test cases
- [ ] LRU eviction validated
- [ ] TTL expiration tested (use fast time mocking, NO sleep)
- [ ] Performance budget verified (<0.1ms P95)
- [ ] All tests pass: `pytest tests/k1/l5_infrastructure/test_caching.py -v`
- [ ] Coverage ≥90%

**Blocked By:** M2-2  
**Unlocks:** M2-4 (serialization foundation)

---

## Epic 2.2: Serialization - FlatBuffers Implementation

**Goal:** Implement FlatBuffers serialization/deserialization for K0 Bridge  
**Components:** `serialization/serializer.py`, `serialization/deserializer.py`, `serialization/string_dedup.py`  
**ADRs:** ADR-0011, ADR-0011c  

### Issue #M2-4: Implement serialization/serializer.py

**Why:** Enable zero-copy serialization for K0 communication  
**Inputs:**
- ADR-0011 (FlatBuffers Serialization)
- ADR-0011c (Serialization Performance - Zero Copy)
- K1 contracts FlatBuffers schemas (k1/contracts/flatbuffers/)
- Existing stub: `k1/l5_infrastructure/serialization/serializer.py`

**Steps:**
1. Create `FlatBuffersSerializer` class
2. Implement `serialize(obj, schema)` - Serialize Python object to FlatBuffers
3. Add schema registry (load .fbs schemas from contracts/)
4. Add type mapping (Python types → FlatBuffers types)
5. Implement nested object serialization (recursive)
6. Add buffer pooling integration (reuse buffers)
7. Implement string deduplication (placeholder, separate Issue)
8. Add performance tracking (serialization time)
9. Emit metrics: `k1.serialization.serializations_total`, `k1.serialization.serialize_duration_ms`
10. Reference ADR-0011 in header

**Observability:**
- Metrics: `k1.serialization.{serializations,deserializations,errors}_total`, `k1.serialization.serialize_duration_ms`
- Traces: Trace serialization operations
- Logs: Log schema mismatches, validation errors

**Perf/Policy:**
- Serialization (1KB): <10ms P95
- Zero-copy where possible
- Privacy: Respect band metadata in serialized data

**Done Criteria:**
- [ ] `serialize` method functional
- [ ] Schema registry loaded
- [ ] Type mapping complete (str, int, float, bool, list, dict)
- [ ] Buffer pooling integrated
- [ ] Performance tracking implemented
- [ ] Metrics emitted
- [ ] ADR-0011 referenced
- [ ] Zero `NotImplementedError`

**Blocked By:** M2-3  
**Unlocks:** M2-5 (deserializer)

---

### Issue #M2-5: Implement serialization/deserializer.py

**Why:** Enable deserialization from FlatBuffers to Python objects  
**Inputs:**
- ADR-0011 (FlatBuffers Serialization)
- Completed serializer.py (M2-4)
- Existing stub: `k1/l5_infrastructure/serialization/deserializer.py`

**Steps:**
1. Create `FlatBuffersDeserializer` class
2. Implement `deserialize(buffer, schema)` - Deserialize FlatBuffers to Python object
3. Add schema validation (verify buffer matches schema)
4. Add type mapping (FlatBuffers types → Python types)
5. Implement nested object deserialization
6. Add zero-copy mode (return views instead of copies where safe)
7. Add error handling (corrupted buffers, version mismatches)
8. Reference ADR-0011 in header

**Observability:**
- Metrics: `k1.serialization.deserializations_total`, `k1.serialization.deserialize_duration_ms`
- Traces: Trace deserialization operations
- Logs: Log deserialization errors

**Perf/Policy:**
- Deserialization (1KB): <10ms P95
- Zero-copy where safe
- Privacy: Validate band metadata

**Done Criteria:**
- [ ] `deserialize` method functional
- [ ] Schema validation implemented
- [ ] Type mapping complete
- [ ] Zero-copy mode functional
- [ ] Error handling robust
- [ ] ADR-0011 referenced
- [ ] Zero `NotImplementedError`

**Blocked By:** M2-4  
**Unlocks:** M2-6 (string dedup)

---

### Issue #M2-6: Implement serialization/string_dedup.py

**Why:** Reduce memory footprint via string deduplication  
**Inputs:**
- ADR-0011c (String deduplication for repeated strings)
- Completed serializer.py (M2-4)
- Existing stub: `k1/l5_infrastructure/serialization/string_dedup.py`

**Steps:**
1. Create `StringDeduplicator` class
2. Implement `intern(string)` - Return deduplicated string
3. Add LRU cache for interned strings (max 10k strings)
4. Add stats tracking (dedupe_hits, dedupe_misses, memory_saved)
5. Implement `clear()` - Reset deduplication cache
6. Add integration with serializer (auto-dedupe string fields)
7. Reference ADR-0011c in header

**Observability:**
- Metrics: `k1.serialization.string_dedupe_hits_total`, `k1.serialization.string_dedupe_memory_saved_bytes`
- Traces: N/A (too granular)
- Logs: Log cache evictions

**Perf/Policy:**
- String intern: <0.1ms P95
- Max cache size: 10k strings
- Memory savings: ~30-50% for typical workloads

**Done Criteria:**
- [ ] `intern` method functional
- [ ] LRU cache implemented
- [ ] Stats tracking accurate
- [ ] Serializer integration working
- [ ] ADR-0011c referenced
- [ ] Zero `NotImplementedError`

**Blocked By:** M2-5  
**Unlocks:** M2-7 (serialization tests)

---

### Issue #M2-7: Write serialization tests

**Why:** Validate serialization, deserialization, string dedup  
**Inputs:**
- Completed serializer.py (M2-4), deserializer.py (M2-5), string_dedup.py (M2-6)

**Steps:**
1. Create `tests/k1/l5_infrastructure/test_serialization.py`
2. Test serialization round-trip (serialize → deserialize)
3. Test schema validation (reject mismatched schemas)
4. Test type mapping (all Python types)
5. Test nested objects (lists, dicts, objects)
6. Test buffer pooling (reuse verification)
7. Test string deduplication (memory savings)
8. Test zero-copy deserialization
9. Test error handling (corrupted buffers)
10. Add performance assertions (<10ms serialize/deserialize)

**Done Criteria:**
- [ ] 20+ test cases
- [ ] Round-trip validation complete
- [ ] All types tested
- [ ] Performance budget verified (<10ms P95)
- [ ] All tests pass: `pytest tests/k1/l5_infrastructure/test_serialization.py -v`
- [ ] Coverage ≥85%

**Blocked By:** M2-6  
**Unlocks:** M2-8 (event bus implementation)

---

## Epic 2.3: Event Bus - Pub/Sub Implementation

**Goal:** Implement internal K1 event bus for component coordination  
**Components:** `event_bus/event_bus.py`, `event_bus/subscribers.py`  
**ADRs:** ADR-0048  

### Issue #M2-8: Implement event_bus/event_bus.py

**Why:** Enable event-driven communication between infrastructure components  
**Inputs:**
- ADR-0048 (K1 Internal Event Bus)
- Completed event_bus/schemas.py (M1-10)
- Existing stub: `k1/l5_infrastructure/event_bus/event_bus.py`

**Steps:**
1. Create `EventBus` singleton class
2. Implement `publish(event)` - Publish event to subscribers
3. Implement `subscribe(event_type, handler)` - Register event handler
4. Implement `unsubscribe(event_type, handler)` - Remove handler
5. Add async dispatch (handlers run in background tasks)
6. Add error handling (failed handlers don't block others)
7. Add backpressure (queue depth limit: 1000 events)
8. Add metrics: `k1.event_bus.events_published_total{type}`, `k1.event_bus.handler_errors_total`
9. Add subscriber registry (track active subscriptions)
10. Reference ADR-0048 in header

**Observability:**
- Metrics: `k1.event_bus.{events_published,events_dropped,handler_errors}_total`
- Traces: Trace event propagation
- Logs: Log handler errors, dropped events

**Perf/Policy:**
- Publish latency: <5ms P95
- Handler dispatch: async (non-blocking)
- Max queue depth: 1000 events
- Privacy: Validate event privacy bands

**Done Criteria:**
- [ ] Publish/subscribe functional
- [ ] Async dispatch working
- [ ] Error handling robust (handler failures isolated)
- [ ] Backpressure implemented
- [ ] Metrics emitted
- [ ] ADR-0048 referenced
- [ ] Zero `NotImplementedError`

**Blocked By:** M2-7  
**Unlocks:** M2-9 (subscribers implementation)

---

### Issue #M2-9: Implement event_bus/subscribers.py

**Why:** Manage subscriber registry and handler lifecycle  
**Inputs:**
- ADR-0048 (K1 Internal Event Bus)
- Completed event_bus.py (M2-8)
- Existing stub: `k1/l5_infrastructure/event_bus/subscribers.py`

**Steps:**
1. Create `SubscriberRegistry` class
2. Implement `register(event_type, handler, priority)` - Add subscriber
3. Implement `unregister(event_type, handler)` - Remove subscriber
4. Implement `get_subscribers(event_type)` - Get handlers for event type
5. Add priority ordering (high-priority handlers run first)
6. Add handler validation (must be async callable)
7. Add stats: `get_stats() -> {total_subscribers, by_event_type}`
8. Reference ADR-0048 in header

**Observability:**
- Metrics: `k1.event_bus.subscribers_total{event_type}`
- Traces: N/A
- Logs: Log registration/unregistration

**Perf/Policy:**
- Registration: <1ms
- Lookup: <1ms (dict-based O(1))
- Privacy: No PII in subscriber metadata

**Done Criteria:**
- [ ] Register/unregister functional
- [ ] Priority ordering working
- [ ] Handler validation implemented
- [ ] Stats tracking accurate
- [ ] ADR-0048 referenced
- [ ] Zero `NotImplementedError`

**Blocked By:** M2-8  
**Unlocks:** M2-10 (event bus tests)

---

### Issue #M2-10: Write event_bus tests

**Why:** Validate pub/sub, async dispatch, backpressure  
**Inputs:**
- Completed event_bus.py (M2-8), subscribers.py (M2-9)

**Steps:**
1. Create `tests/k1/l5_infrastructure/test_event_bus.py`
2. Test publish/subscribe flow
3. Test async handler dispatch
4. Test multiple subscribers (order, priority)
5. Test error handling (failed handler doesn't block others)
6. Test backpressure (queue overflow)
7. Test unsubscribe (handler removal)
8. Test event filtering by type
9. Add performance assertions (<5ms publish)
10. Test concurrent publish (thread safety)

**Done Criteria:**
- [ ] 15+ test cases
- [ ] Async dispatch validated
- [ ] Error isolation tested
- [ ] Backpressure verified
- [ ] Performance budget met (<5ms P95)
- [ ] All tests pass: `pytest tests/k1/l5_infrastructure/test_event_bus.py -v`
- [ ] Coverage ≥90%

**Blocked By:** M2-10  
**Unlocks:** M2-11 (package integration)

---

## Epic 2.4: Cache Persistence & Integrations

**Goal:** Implement remaining cache adapters (connection pooling, persistent/local caches, K0 integration, warming)  
**Components:** `caching/connection_pool.py`, `caching/persistent_cache.py`, `caching/kv_cache_local.py`, `caching/cache_integration.py`, `caching/cache_warmer.py`  
**ADRs:** ADR-0028d, ADR-0025, ADR-0025c

### Issue #M2-12: Implement caching/connection_pool.py

**Why:** Provide pooled connections for persistent cache backends (foundation for K0 integration)  
**Inputs:**
- ADR-0028d (Local cache with K0 persistence)
- Existing stub: `k1/l5_infrastructure/caching/connection_pool.py`

**Steps:**
1. Implement async connection pool (acquire/release, max size, timeout)
2. Support health checks and eviction of unhealthy connections
3. Integrate metrics: `k1.cache.pool_in_use`, `k1.cache.pool_wait_ms`
4. Ensure privacy band labels propagate to connection metadata
5. Reference ADR-0028d in header

**Done Criteria:**
- [ ] Acquire/release operations functional with semaphore guard
- [ ] Health checks + eviction implemented
- [ ] Metrics emitted for pool depth/wait
- [ ] ADR-0028d referenced
- [ ] Zero `NotImplementedError`

**Blocked By:** M2-11  
**Unlocks:** M2-13 (persistent cache)

---

### Issue #M2-13: Implement caching/persistent_cache.py

**Why:** Provide disk-backed cache leveraging connection pool + K0 persistence contracts  
**Inputs:**
- ADR-0028d, ADR-0025
- Completed connection pool (M2-12)
- Existing stub: `k1/l5_infrastructure/caching/persistent_cache.py`

**Steps:**
1. Implement `PersistentCache(KVCache)` storing values in LevelDB/SQLite per ADR
2. Use `ConnectionPool` for backend sessions
3. Support async `get/set/delete` with batching for writes
4. Implement TTL + eviction policies consistent with global budgets
5. Emit metrics: `k1.cache.persistent_hits_total`, `k1.cache.persistent_latency_ms`
6. Reference ADR-0028d in header

**Done Criteria:**
- [ ] Persistent cache operations functional with pool reuse
- [ ] TTL + eviction respect ADR budgets
- [ ] Metrics emitted for hit/miss/latency
- [ ] ADR references present
- [ ] Zero `NotImplementedError`

**Blocked By:** M2-12  
**Unlocks:** M2-14 (local cache)

---

### Issue #M2-14: Implement caching/kv_cache_local.py

**Why:** Provide local hybrid cache combining in-memory + persistent layers  
**Inputs:**
- ADR-0028d, ADR-0025
- Completed `in_memory_cache.py` (M2-2) and `persistent_cache.py` (M2-13)
- Existing stub: `k1/l5_infrastructure/caching/kv_cache_local.py`

**Steps:**
1. Implement read-through/write-through semantics (memory + persistent)
2. Add tiered eviction (memory first, then persistent) honoring budgets
3. Implement async initialization/start/stop bridging sub-caches
4. Emit metrics: `k1.cache.local_hits_total`, `k1.cache.local_promotions_total`
5. Reference ADR-0028d in header

**Done Criteria:**
- [ ] Read/write flows hit memory before disk
- [ ] Eviction + promotion logic implemented
- [ ] Metrics emitted
- [ ] ADR references present
- [ ] Zero `NotImplementedError`

**Blocked By:** M2-13  
**Unlocks:** M2-15 (K0 integration)

---

### Issue #M2-15: Implement caching/cache_integration.py

**Why:** Integrate cache layer with K0 persistence + bridge clients  
**Inputs:**
- ADR-0028d, ADR-0025
- Completed `persistent_cache.py` (M2-13)
- Existing stub: `k1/l5_infrastructure/caching/cache_integration.py`

**Steps:**
1. Implement adapters to read/write via K0 bridge contracts
2. Ensure idempotent writes with receipts + cognitive_trace_id propagation
3. Handle multi-band privacy policies (mask RED/BLACK entries)
4. Emit metrics: `k1.cache.integration_sync_errors_total`
5. Reference ADR-0028d in header

**Done Criteria:**
- [ ] K0 integration adapter functional
- [ ] Receipts + trace propagation verified
- [ ] Privacy band handling implemented
- [ ] ADR references present
- [ ] Zero `NotImplementedError`

**Blocked By:** M2-14  
**Unlocks:** M2-16 (cache warmer)

---

### Issue #M2-16: Implement caching/cache_warmer.py

**Why:** Pre-warm cache tiers using predictive heuristics per ADR-0025c  
**Inputs:**
- ADR-0025c (Cache warming)
- Completed integration (M2-15)
- Existing stub: `k1/l5_infrastructure/caching/cache_warmer.py`

**Steps:**
1. Implement warming scheduler (async task) using access patterns
2. Integrate with PlacementEngine for hot session hints
3. Emit metrics: `k1.cache.warmer_prefetch_total`, `k1.cache.warmer_latency_ms`
4. Ensure no sleeps; use awaitable timers/backoff per policy
5. Reference ADR-0025c in header

**Done Criteria:**
- [ ] Warming scheduler executing predicted loads
- [ ] Placement hints consumed
- [ ] Metrics emitted + budgets enforced
- [ ] ADR references present
- [ ] Zero `NotImplementedError`

**Blocked By:** M2-15  
**Unlocks:** M2-17 (integration tests)

---

### Issue #M2-17: Extend cache integration tests

**Why:** Validate persistent/local caches, K0 integration, and warming flows  
**Inputs:**
- Completed caching components (M2-12 through M2-16)

**Steps:**
1. Extend `test_caching.py` or add `test_caching_integration.py`
2. Test connection pool contention + metrics
3. Test persistent cache durability + failover to memory cache
4. Test K0 integration (mock bridge client) with privacy band enforcement
5. Test cache warmer prefetch accuracy + budget (<10ms prefetch)

**Done Criteria:**
- [ ] 15+ additional integration cases
- [ ] Metrics + privacy enforcement asserted
- [ ] Performance budgets verified
- [ ] Tests pass: `pytest tests/k1/l5_infrastructure/test_caching* -v`
- [ ] Coverage ≥90% across new modules

**Blocked By:** M2-16  
**Unlocks:** M2 Summary

---

### Issue #M2-11: Update caching/__init__.py and serialization/__init__.py

**Why:** Export public APIs for caching and serialization  
**Inputs:**
- Completed caching components (M2-1 through M2-3)
- Completed serialization components (M2-4 through M2-7)

**Steps:**
1. Update `k1/l5_infrastructure/caching/__init__.py`:
   - Export `KVCache`, `InMemoryCache`, `CacheStats`
   - Add `__all__` list
   - Update docstring (remove STUB marker)
2. Update `k1/l5_infrastructure/serialization/__init__.py`:
   - Export `FlatBuffersSerializer`, `FlatBuffersDeserializer`, `StringDeduplicator`
   - Add `__all__` list
   - Update docstring (remove STUB marker)
3. Update `k1/l5_infrastructure/event_bus/__init__.py`:
   - Export `EventBus`, `SubscriberRegistry`, event schemas
   - Add `__all__` list
   - Update docstring (remove STUB marker)

**Done Criteria:**
- [ ] All exports functional
- [ ] Import tests pass:
  - `python -c "from k1.l5_infrastructure.caching import KVCache, InMemoryCache"`
  - `python -c "from k1.l5_infrastructure.serialization import FlatBuffersSerializer"`
  - `python -c "from k1.l5_infrastructure.event_bus import EventBus"`

**Blocked By:** M2-10  
**Unlocks:** M3-1 (Control plane - Admission)

---

## M2 Summary

**Total Issues:** 17 (M2-1 through M2-17)  
**Estimated Effort:** ~14-16 developer days  
**Critical Path:** M2-1 → M2-2 → M2-3 → M2-4 → M2-5 → M2-6 → M2-7 → M2-8 → M2-9 → M2-10 → M2-11 → M2-12 → M2-13 → M2-14 → M2-15 → M2-16 → M2-17  

**Completion Checklist:**
- [ ] KV cache abstraction and in-memory implementation operational
- [ ] FlatBuffers serialization/deserialization functional
- [ ] String deduplication working
- [ ] Event bus pub/sub operational
- [ ] Persistent/local/K0-integrated caches implemented
- [ ] All M2 tests passing (70+ tests total)
- [ ] Performance budgets met (cache <0.1ms, serialization <10ms, event bus <5ms)
- [ ] Zero `NotImplementedError` in M2 components
- [ ] ADR references in all headers

**Next:** M3 - Control Plane (Admission, Backpressure, Rate Limiting)

---

# 🎯 Next Steps

**Completed So Far:**
- ✅ Component inventory (67 files, 72 with STUB markers)
- ✅ Dependency analysis (local + external + K1)
- ✅ Performance budgets extracted
- ✅ ADR coverage mapped
- ✅ M1 Plan: Foundation & Observability (11 Issues, 8-10 days)
- ✅ M2 Plan: Core Runtime Services (11 Issues, 10-12 days)

**Remaining Milestones to Detail:**
- ⏳ M3: Control Plane (Admission, Backpressure, Rate Limiting) - ~15-18 Issues
- ⏳ M4: Resilience & Integration (Circuit Breakers, Extensions, Modules) - ~20-25 Issues
- ⏳ M5: Hardening & Performance (Perf budgets, edge cases, integration tests) - ~10-12 Issues

**Estimated Total:**
- **~70-80 Issues** across 5 milestones
- **~50-60 developer days** (single developer, strictly sequential)
- **~200+ integration tests** across all components

---

## 📊 Issue Dependency Chain Summary (M1-M2)

```text
M1-1 (metrics) → M1-2 (metrics tests)
  ↓
M1-3 (tracing) → M1-4 (tracing tests)
  ↓
M1-5 (logging) → M1-6 (logging tests)
  ↓
M1-7 (K0 client) → M1-8 (K0 client tests)
  ↓
M1-9 (observability __init__)
  ↓
M1-10 (event schemas) → M1-11 (event schemas tests)
  ↓
M2-1 (kv cache contract) → M2-2 (in-memory cache) → M2-3 (cache tests)
  ↓
M2-4 (serializer) → M2-5 (deserializer) → M2-6 (string dedup) → M2-7 (serialization tests)
  ↓
M2-8 (event bus) → M2-9 (subscribers) → M2-10 (event bus tests)
  ↓
M2-11 (package integration)
  ↓
M3-1 (next: Admission control) ...
```

---

**Status:** M1 and M2 complete (~22 Issues detailed). Ready to proceed with M3-M5 or pause here.

Would you like me to continue with:
1. **M3 (Control Plane)** - Admission, Backpressure, Rate Limiting (~15-18 Issues)
2. **M4 (Resilience & Integration)** - Circuit Breakers, Extensions, Modules (~20-25 Issues)
3. **M5 (Hardening)** - Performance, edge cases, integration tests (~10-12 Issues)

Or would you prefer to review M1-M2 first and provide feedback?

---

# 📍 MILESTONE 3: Control Plane

**Goal:** Implement control plane services (admission control, backpressure, rate limiting)  
**Dependencies:** M1 (Observability), M2 (Event Bus, Caching)  
**Acceptance Criteria:**
- Admission controller operational with policy enforcement
- Backpressure cascade coordination functional
- Rate limiting with token bucket algorithm working
- All M3 tests passing

---

## Epic 3.1: Admission Control

**Goal:** Implement admission controller with validation, rate limiting, and capacity checks  
**Components:** `admission/admission_controller.py`, `admission/task_validator.py`, `admission/policies.py`  
**ADRs:** ADR-0032, ADR-0002c, ADR-0028, ADR-0030  

### Issue #M3-1: Implement admission/policies.py models

**Why:** Define admission policy models before implementing controller  
**Inputs:**
- ADR-0032 (Admission Control Design - need to verify ADR number)
- Completed observability (M1-9)
- Existing stub: `k1/l5_infrastructure/admission/policies.py`

**Steps:**
1. Define `AdmissionPolicy` dataclass (name, priority, max_queue_depth, reserved_slots)
2. Define `AdmissionDecision` enum (ADMIT, REJECT, DEFER)
3. Define `RejectionReason` enum (RATE_LIMIT, CAPACITY, SCHEMA, BACKPRESSURE)
4. Define `AdmissionResult` dataclass (decision, reason, retry_after_ms)
5. Add policy validation (sensible limits)
6. Add JSON serialization methods
7. Reference ADR in header

**Observability:**
- Metrics: N/A (model definitions only)
- Traces: N/A
- Logs: N/A

**Perf/Policy:**
- Model creation: <0.1ms
- Privacy: No PII in policy definitions

**Done Criteria:**
- [ ] All policy models defined (4+ dataclasses/enums)
- [ ] Validation implemented
- [ ] JSON serialization functional
- [ ] ADR referenced
- [ ] Zero `NotImplementedError`

**Blocked By:** M2-11  
**Unlocks:** M3-2 (task validator)

---

### Issue #M3-2: Implement admission/task_validator.py

**Why:** Validate incoming tasks before admission  
**Inputs:**
- ADR-0032 (Admission Control)
- Completed policies.py (M3-1)
- Existing stub: `k1/l5_infrastructure/admission/task_validator.py`

**Steps:**
1. Create `TaskValidator` class
2. Implement `validate_schema(task)` - Validate task structure
3. Implement `validate_privacy_band(task)` - Check privacy band valid
4. Implement `validate_capabilities(task)` - Check required capabilities present
5. Add field validation (required fields, types, ranges)
6. Add custom validation rules (extensible)
7. Emit metrics on validation failures
8. Reference ADR-0032 in header

**Observability:**
- Metrics: `k1.admission.validation_failures_total{reason}`
- Traces: Trace validation in admission span
- Logs: Log validation errors with details

**Perf/Policy:**
- Validation: <1ms P95
- Privacy: Enforce band constraints

**Done Criteria:**
- [ ] All validation methods functional
- [ ] Field validation comprehensive
- [ ] Metrics emitted on failures
- [ ] ADR-0032 referenced
- [ ] Zero `NotImplementedError`

**Blocked By:** M3-1  
**Unlocks:** M3-3 (admission controller)

---

### Issue #M3-3: Implement admission/admission_controller.py

**Why:** Core admission decision engine  
**Inputs:**
- ADR-0032 (Admission Control Design)
- ADR-0030 (Rate Limiting integration)
- ADR-0028 (Backpressure integration)
- Completed policies.py (M3-1), task_validator.py (M3-2)
- Existing stub: `k1/l5_infrastructure/admission/admission_controller.py`

**Steps:**
1. Create `AdmissionController` class
2. Implement `__init__(policies, rate_limiter, backpressure_manager)`
3. Implement `async admit(task)` - Main admission decision method
4. Add validation step (use TaskValidator)
5. Add rate limit check (use RateLimiter from rate_limiting/)
6. Add capacity check (queue depth vs max_queue_depth)
7. Add backpressure check (use BackpressureManager)
8. Add anti-starvation logic (reserved slots for high-priority)
9. Implement `get_stats()` - Return admission stats
10. Emit metrics: `k1.admission.{requests,admissions,rejections}_total`
11. Reference ADR-0032, 0030, 0028 in header

**Observability:**
- Metrics: `k1.admission.{requests,admissions,rejections}_total{priority,reason}`, `k1.admission.decision_latency_ms`
- Traces: Create span for admission decision
- Logs: Log rejections with reason

**Perf/Policy:**
- Admission decision: <10ms P95
- All checks must complete
- Privacy: Validate band in task

**Done Criteria:**
- [ ] `admit` method functional with all checks
- [ ] Anti-starvation logic working
- [ ] Stats tracking accurate
- [ ] All metrics emitted
- [ ] Performance budget met (<10ms)
- [ ] ADRs referenced (0032, 0030, 0028)
- [ ] Zero `NotImplementedError`

**Blocked By:** M3-2  
**Unlocks:** M3-4 (admission tests)

---

### Issue #M3-4: Write admission tests

**Why:** Validate admission logic, policy enforcement  
**Inputs:**
- Completed admission components (M3-1, M3-2, M3-3)

**Steps:**
1. Create `tests/k1/l5_infrastructure/test_admission.py`
2. Test admission decision (ADMIT/REJECT/DEFER)
3. Test validation failures (schema, privacy band, capabilities)
4. Test rate limit integration (reject when rate exceeded)
5. Test capacity check (reject when queue full)
6. Test backpressure integration (defer when backpressure high)
7. Test anti-starvation (high-priority tasks use reserved slots)
8. Test metrics emission
9. Add performance assertions (<10ms decision)

**Done Criteria:**
- [ ] 20+ test cases
- [ ] All decision paths tested
- [ ] Integration with rate limiter/backpressure tested
- [ ] Performance budget verified (<10ms P95)
- [ ] All tests pass: `pytest tests/k1/l5_infrastructure/test_admission.py -v`
- [ ] Coverage ≥90%

**Blocked By:** M3-3  
**Unlocks:** M3-5 (backpressure implementation)

---

## Epic 3.2: Backpressure Coordination

**Goal:** Implement backpressure cascade coordination system  
**Components:** `backpressure/backpressure_manager.py`, `backpressure/watermark_tracker.py`, `backpressure/privacy_override.py`  
**ADRs:** ADR-0028, ADR-0061, ADR-0039  

### Issue #M3-5: Implement backpressure/watermark_tracker.py

**Why:** Track watermark levels for backpressure decisions  
**Inputs:**
- ADR-0061 (3-Tier Backpressure Cascade)
- ADR-0061a (Watermark thresholds)
- Completed observability (M1-9)
- Existing stub: `k1/l5_infrastructure/backpressure/watermark_tracker.py`

**Steps:**
1. Create `WatermarkTracker` class
2. Implement `set_watermark(component, level)` - Update watermark
3. Implement `get_watermark(component)` - Get current level
4. Define watermark thresholds (LOW <60%, MEDIUM 60-80%, HIGH >80%)
5. Implement hysteresis (5% buffer to prevent oscillation)
6. Add watermark history (last 10 readings)
7. Emit metrics: `k1.backpressure.watermark_level{component}`
8. Reference ADR-0061, 0061a in header

**Observability:**
- Metrics: `k1.backpressure.watermark_level{component}`, `k1.backpressure.threshold_breaches_total`
- Traces: N/A (too frequent)
- Logs: Log threshold breaches

**Perf/Policy:**
- Watermark update: <0.5ms P95
- Get watermark: <0.1ms (dict lookup)
- Privacy: N/A

**Done Criteria:**
- [ ] Set/get watermark functional
- [ ] Thresholds defined (LOW/MEDIUM/HIGH)
- [ ] Hysteresis implemented (5% buffer)
- [ ] History tracking working
- [ ] Metrics emitted
- [ ] ADR-0061, 0061a referenced
- [ ] Zero `NotImplementedError`

**Blocked By:** M3-4  
**Unlocks:** M3-6 (privacy override)

---

### Issue #M3-6: Implement backpressure/privacy_override.py

**Why:** Allow privacy band overrides for backpressure policies  
**Inputs:**
- ADR-0039 (Privacy Band Overrides)
- ADR-0061c (Privacy band integration with backpressure)
- Completed watermark_tracker.py (M3-5)
- Existing stub: `k1/l5_infrastructure/backpressure/privacy_override.py`

**Steps:**
1. Create `PrivacyOverride` dataclass (band, watermark_threshold_override)
2. Create `PrivacyOverrideManager` class
3. Implement `register_override(band, threshold)` - Set band-specific threshold
4. Implement `get_threshold(band, default_threshold)` - Get threshold for band
5. Add override validation (RED band can't have lower threshold than GREEN)
6. Reference ADR-0039, 0061c in header

**Observability:**
- Metrics: `k1.backpressure.privacy_overrides_active{band}`
- Traces: N/A
- Logs: Log override registrations

**Perf/Policy:**
- Threshold lookup: <0.1ms
- Privacy: Enforce band hierarchy (RED > AMBER > GREEN)

**Done Criteria:**
- [ ] Register/get override functional
- [ ] Validation enforces band hierarchy
- [ ] Metrics emitted
- [ ] ADR-0039, 0061c referenced
- [ ] Zero `NotImplementedError`

**Blocked By:** M3-5  
**Unlocks:** M3-7 (backpressure manager)

---

### Issue #M3-7: Implement backpressure/backpressure_manager.py

**Why:** Core backpressure coordination orchestrator  
**Inputs:**
- ADR-0028 (Backpressure Cascade System)
- ADR-0061 (3-Tier Backpressure Cascade)
- Completed watermark_tracker.py (M3-5), privacy_override.py (M3-6)
- Existing stub: `k1/l5_infrastructure/backpressure/backpressure_manager.py`

**Steps:**
1. Create `BackpressureManager` class
2. Implement `__init__(watermark_tracker, privacy_override_manager)`
3. Implement `check_backpressure(component, band)` - Check if backpressure active
4. Implement `get_backpressure_level()` - Get global backpressure level
5. Add cascade logic (component watermarks aggregate to global level)
6. Add privacy band integration (use overrides)
7. Publish backpressure events to event bus
8. Emit metrics: `k1.backpressure.level{component}`, `k1.backpressure.cascade_triggered_total`
9. Reference ADR-0028, 0061 in header

**Observability:**
- Metrics: `k1.backpressure.{level,cascade_triggered,checks}_total`
- Traces: Trace backpressure checks
- Logs: Log cascade triggers

**Perf/Policy:**
- Check backpressure: <2ms P95
- Cascade evaluation: <5ms
- Privacy: Apply band-specific overrides

**Done Criteria:**
- [ ] Check backpressure functional
- [ ] Cascade logic working (aggregates component watermarks)
- [ ] Privacy band overrides applied
- [ ] Events published to event bus
- [ ] Metrics emitted
- [ ] ADR-0028, 0061 referenced
- [ ] Zero `NotImplementedError`

**Blocked By:** M3-6  
**Unlocks:** M3-8 (backpressure tests)

---

### Issue #M3-8: Write backpressure tests

**Why:** Validate watermark tracking, cascade logic, privacy overrides  
**Inputs:**
- Completed backpressure components (M3-5, M3-6, M3-7)

**Steps:**
1. Create `tests/k1/l5_infrastructure/test_backpressure.py`
2. Test watermark tracking (set/get)
3. Test threshold detection (LOW/MEDIUM/HIGH)
4. Test hysteresis (prevents oscillation)
5. Test privacy overrides (band-specific thresholds)
6. Test cascade logic (component watermarks → global level)
7. Test event bus integration (backpressure events published)
8. Test metrics emission
9. Add performance assertions (<2ms check)

**Done Criteria:**
- [ ] 18+ test cases
- [ ] All backpressure levels tested
- [ ] Cascade logic validated
- [ ] Privacy overrides tested
- [ ] Performance budget verified (<2ms P95)
- [ ] All tests pass: `pytest tests/k1/l5_infrastructure/test_backpressure.py -v`
- [ ] Coverage ≥90%

**Blocked By:** M3-7  
**Unlocks:** M3-9 (package integration)

---

### Issue #M3-9: Update admission/__init__.py and backpressure/__init__.py

**Why:** Export public APIs for admission and backpressure  
**Inputs:**
- Completed admission components (M3-1 through M3-4)
- Completed backpressure components (M3-5 through M3-8)

**Steps:**
1. Update `k1/l5_infrastructure/admission/__init__.py`:
   - Export `AdmissionController`, `TaskValidator`, `AdmissionPolicy`, `AdmissionDecision`
   - Add `__all__` list
   - Update docstring (remove STUB marker)
2. Update `k1/l5_infrastructure/backpressure/__init__.py`:
   - Export `BackpressureManager`, `WatermarkTracker`, `PrivacyOverrideManager`
   - Add `__all__` list
   - Update docstring

**Done Criteria:**
- [ ] All exports functional
- [ ] Import tests pass:
  - `python -c "from k1.l5_infrastructure.admission import AdmissionController"`
  - `python -c "from k1.l5_infrastructure.backpressure import BackpressureManager"`

**Blocked By:** M3-8  
**Unlocks:** M3-10 (Backpressure cascade actions)

---

### Issue #M3-10: Implement backpressure/cascade_actions.py

**Why:** Define cascade response actions triggered by watermark events  
**Inputs:**
- ADR-0028c (Cascade action taxonomy)
- ADR-0061 (Backpressure cascade)
- Existing stub: `k1/l5_infrastructure/backpressure/cascade_actions.py`

**Steps:**
1. Define action classes (ThrottleRequests, PauseLowPriority, ShedLoad, ResumeNormal)
2. Implement privacy-band aware adjustments (RED tasks throttle last)
3. Provide serialization helpers so EventBus messages carry action details
4. Integrate with BackpressureManager (register available actions)
5. Emit metrics: `k1.backpressure.cascade_actions_total{action}`
6. Reference ADR-0028c in header

**Done Criteria:**
- [ ] Action classes implemented with execute() interface
- [ ] Privacy band logic enforced per action
- [ ] Serialization helpers available for EventBus payloads
- [ ] Metrics emitted per action
- [ ] ADR-0028c referenced
- [ ] Zero `NotImplementedError`

**Blocked By:** M3-9  
**Unlocks:** M3-11 (Backpressure metrics adapter)

---

### Issue #M3-11: Implement backpressure/metrics.py

**Why:** Centralize backpressure metric emission for reuse across manager/actions  
**Inputs:**
- ADR-0061b (Backpressure observability)
- Existing stub: `k1/l5_infrastructure/backpressure/metrics.py`

**Steps:**
1. Implement helpers: `record_watermark`, `record_action`, `record_privacy_override`
2. Ensure metrics include `privacy_band`, `component`, `action` labels
3. Integrate with observability metrics API (emit_counter/histogram)
4. Provide test hooks for assertions (e.g., in-memory registry)
5. Reference ADR-0061b in header

**Done Criteria:**
- [ ] Metric helper functions implemented
- [ ] Label schema enforced per ADR-0061b
- [ ] Integration with observability metrics verified
- [ ] ADR-0061b referenced
- [ ] Zero `NotImplementedError`

**Blocked By:** M3-10  
**Unlocks:** M3-12 (Extend backpressure tests)

---

### Issue #M3-12: Extend backpressure tests for actions & metrics

**Why:** Cover new cascade actions and metrics helpers  
**Inputs:**
- Completed backpressure components (M3-5 through M3-11)

**Steps:**
1. Extend `test_backpressure.py` with action execution scenarios
2. Assert privacy-aware throttling behaviour for RED/AMBER/GREEN
3. Verify metric helpers emit counters/histograms with expected labels
4. Validate EventBus payload serialization for actions
5. Confirm BackpressureManager uses metrics helpers

**Done Criteria:**
- [ ] Additional test cases for each action type
- [ ] Metrics assertions added
- [ ] Event payload serialization validated
- [ ] Tests pass: `pytest tests/k1/l5_infrastructure/test_backpressure.py -v`

**Blocked By:** M3-11  
**Unlocks:** M3-13 (Placement capability matcher)

---

## Epic 3.3: Placement Cascade Engine

**Goal:** Implement placement decision engine integrating thermal, cost, and resilience hooks  
**Components:** `placement/capability_matcher.py`, `placement/cascade_engine.py`, `placement/circuit_breaker.py`  
**ADRs:** ADR-0027, ADR-0027a, ADR-0027b, ADR-0027c, ADR-0009

### Issue #M3-13: Implement placement/capability_matcher.py

**Why:** Match task requirements to device capabilities before cascade evaluation  
**Inputs:**
- ADR-0027a (Capability matching)
- Existing stub: `k1/l5_infrastructure/placement/capability_matcher.py`

**Steps:**
1. Implement capability graph model (device features vs task requirements)
2. Support privacy band + thermal constraints in matching
3. Provide scoring function considering cost/capability ratios
4. Emit metrics: `k1.placement.matches_total{tier,result}`
5. Reference ADR-0027a in header

**Done Criteria:**
- [ ] Matching algorithm implemented with scoring
- [ ] Thermal + privacy constraints enforced
- [ ] Metrics emitted per tier/result
- [ ] ADR-0027a referenced
- [ ] Zero `NotImplementedError`

**Blocked By:** M3-12  
**Unlocks:** M3-14 (Placement cascade engine)

---

### Issue #M3-14: Implement placement/cascade_engine.py

**Why:** Orchestrate placement decisions across NPU→GPU→CPU→Remote tiers  
**Inputs:**
- ADR-0027 (Cascade algorithm)
- ADR-0027b (Failover)
- ADR-0027c (Cost tracking)
- Completed capability matcher (M3-13)
- Existing stub: `k1/l5_infrastructure/placement/cascade_engine.py`

**Steps:**
1. Implement tiered evaluation pipeline invoking CapabilityMatcher
2. Integrate thermal manager + cost tracker for decision making
3. Add failover logic with retry limits per ADR-0027b
4. Emit metrics: `k1.placement.cascade_latency_ms`, `k1.placement.failovers_total`
5. Reference ADR-0027 series in header

**Done Criteria:**
- [ ] Cascade evaluation returns placement plan with rationale
- [ ] Failover + retry logic implemented
- [ ] Metrics emitted + latency budget (<20ms)
- [ ] ADR references present
- [ ] Zero `NotImplementedError`

**Blocked By:** M3-13  
**Unlocks:** M3-15 (Placement circuit breaker adapter)

---

### Issue #M3-15: Implement placement/circuit_breaker.py

**Why:** Bridge placement engine with resilience circuit breaker decisions  
**Inputs:**
- ADR-0027, ADR-0009
- Completed cascade engine (M3-14)
- Existing stub: `k1/l5_infrastructure/placement/circuit_breaker.py`

**Steps:**
1. Implement adapter that queries CircuitBreakerManager before placement
2. Provide fallback providers when circuits OPEN
3. Emit metrics: `k1.placement.circuit_open_total`
4. Ensure cognitive_trace_id propagation
5. Reference ADR-0027 + ADR-0009 in header

**Done Criteria:**
- [ ] Adapter integrates with CircuitBreakerManager execute API
- [ ] Fallback providers invoked when primary OPEN
- [ ] Metrics emitted
- [ ] ADR references present
- [ ] Zero `NotImplementedError`

**Blocked By:** M3-14  
**Unlocks:** M3-16 (Placement tests)

---

### Issue #M3-16: Write placement tests

**Why:** Validate capability matcher, cascade engine, and circuit breaker adapter  
**Inputs:**
- Completed placement components (M3-13 through M3-15)

**Steps:**
1. Create `tests/k1/l5_infrastructure/test_placement.py`
2. Test capability matching across GREEN/AMBER/RED tasks
3. Test cascade engine tier fallback + latency budget (<20ms)
4. Test circuit breaker adapter triggers alternate providers
5. Assert metrics emitted for matches, failovers, circuit opens

**Done Criteria:**
- [ ] 18+ placement test cases
- [ ] Performance budgets verified
- [ ] Metrics/assertions validated
- [ ] Tests pass: `pytest tests/k1/l5_infrastructure/test_placement.py -v`
- [ ] Coverage ≥90%

**Blocked By:** M3-15  
**Unlocks:** M3 Summary

---

## M3 Summary

**Total Issues:** 16 (M3-1 through M3-16)  
**Estimated Effort:** ~12-14 developer days  
**Critical Path:** M3-1 → M3-2 → M3-3 → M3-4 → M3-5 → M3-6 → M3-7 → M3-8 → M3-9 → M3-10 → M3-11 → M3-12 → M3-13 → M3-14 → M3-15 → M3-16  

**Completion Checklist:**
- [ ] Admission controller operational
- [ ] Backpressure cascade coordination functional
- [ ] Privacy band overrides working
- [ ] Cascade actions + metrics implemented & tested
- [ ] Placement cascade engine operational
- [ ] All M3 tests passing (60+ tests total)
- [ ] Performance budgets met (admission <10ms, backpressure <2ms)
- [ ] Zero `NotImplementedError` in M3 components
- [ ] ADR references in all headers

**Next:** M4 - Resilience & Integration (Circuit Breakers, Extensions, Modules)

---

# 📍 MILESTONE 4: Resilience & Integration

**Goal:** Implement resilience primitives, fallback strategies, and extensibility infrastructure  
**Dependencies:** M3 (Admission + Backpressure)  
**Acceptance Criteria:**
- Circuit breaker orchestration functional with persistence and observability
- Resilience fallbacks wired and tested
- Extensions framework operational with registry and sample strategies
- Module system (discovery + loader) delivering hot-reloadable plugins
- All M4 tests passing (`pytest tests/k1/l5_infrastructure/test_resilience*.py tests/k1/l5_infrastructure/test_extensions*.py tests/k1/l5_infrastructure/test_modules*.py`)

---

## Epic 4.1: Circuit Breaker Core

**Components:** `resilience/circuit_fsm.py`, `resilience/circuit_breaker_manager.py`, `resilience/call_wrapper.py`, `resilience/state_persistence.py`  
**ADRs:** ADR-0009, ADR-0009a, ADR-0009b, ADR-0009c  

### Issue #M4-1: Implement resilience/circuit_fsm.py

**Why:** Define three-state FSM (CLOSED/OPEN/HALF_OPEN) per ADR-0009a before orchestrator  
**Inputs:**
- ADR-0009a (FSM implementation)
- Existing stub: `k1/l5_infrastructure/resilience/circuit_fsm.py`

**Steps:**
1. Define `CircuitBreakerState` enum (CLOSED, OPEN, HALF_OPEN)
2. Implement `CircuitBreakerFSM` class with state transitions and failure counters
3. Add `transition(event)` logic (success/failure/timeouts) with guard conditions
4. Implement `can_execute()` method gating protected calls
5. Add timeout tracking (open -> half-open after configured interval)
6. Emit metrics hooks (state transitions)
7. Reference ADR-0009a in header

**Done Criteria:**
- [ ] FSM states + transitions implemented
- [ ] Timeout + failure thresholds configurable
- [ ] `can_execute()` correct in all states
- [ ] Metrics hooks in place (no-op for now)
- [ ] ADR-0009a referenced
- [ ] Zero `NotImplementedError`

**Blocked By:** M3-9  
**Unlocks:** M4-2 (call wrapper)

---

### Issue #M4-2: Implement resilience/call_wrapper.py

**Why:** Provide protective wrapper that consults FSM and records outcomes  
**Inputs:**
- ADR-0009 (pattern overview)
- Completed `circuit_fsm.py` (M4-1)
- Existing stub: `k1/l5_infrastructure/resilience/call_wrapper.py`

**Steps:**
1. Implement `async call_with_protection(service_name, func, *args, **kwargs)`
2. Consult `CircuitBreakerFSM` to allow/deny execution
3. Record success/failure with latency measurement
4. Trigger fallback callbacks on OPEN state
5. Emit metrics: `k1.resilience.protected_calls_total{service,state}`
6. Propagate `cognitive_trace_id` through wrapped call
7. Reference ADR-0009 in header

**Done Criteria:**
- [ ] Wrapper denies execution when circuit OPEN
- [ ] Success/failure outcomes update FSM counters
- [ ] Latency recorded + metrics emitted
- [ ] Trace propagation intact
- [ ] ADR-0009 referenced
- [ ] Zero `NotImplementedError`

**Blocked By:** M4-1  
**Unlocks:** M4-3 (state persistence)

---

### Issue #M4-3: Implement resilience/state_persistence.py

**Why:** Persist circuit states across restarts using Redis per ADR-0009b  
**Inputs:**
- ADR-0009b (per-service circuit configuration)
- Existing stub: `k1/l5_infrastructure/resilience/state_persistence.py`

**Steps:**
1. Implement `StatePersistence` class with Redis client integration (dependency injected)
2. Add `load_state(service_name)` returning FSM snapshot
3. Add `save_state(service_name, snapshot)` storing counts + timestamps
4. Implement TTL-based pruning for stale circuits
5. Handle connectivity errors with retries + logging
6. Reference ADR-0009b in header

**Done Criteria:**
- [ ] Load/save operations functional
- [ ] Snapshot schema matches ADR-0009b
- [ ] Retry & logging implemented
- [ ] Zero blocking waits; no sleeps
- [ ] ADR-0009b referenced

**Blocked By:** M4-2  
**Unlocks:** M4-4 (circuit breaker manager)

---

### Issue #M4-4: Complete resilience/circuit_breaker_manager.py

**Why:** Wire FSM, wrapper, persistence into orchestrator (high STUB density file)  
**Inputs:**
- ADR-0009, 0009a, 0009b, 0009c
- Completed call wrapper + persistence
- Existing stub: `k1/l5_infrastructure/resilience/circuit_breaker_manager.py`

**Steps:**
1. Implement circuit registry (per service configuration)
2. Integrate `StatePersistence` load/save during init + periodic flush
3. Provide `register_service(config)` API
4. Provide `async execute(service, func, *args, fallback=None, **kwargs)` using call wrapper
5. Emit metrics: `k1.resilience.circuit_state{service,state}` and durations per ADR-0009c
6. Publish circuit events to event bus (OPEN/HALF_OPEN transitions)
7. Integrate Prometheus histograms for latency
8. Reference ADRs in header comments

**Done Criteria:**
- [ ] Registry + execute path functional
- [ ] Persistence flush schedule implemented (async task, no sleeps)
- [ ] Metrics + event bus integration complete
- [ ] ADR-refs present
- [ ] Zero `NotImplementedError`

**Blocked By:** M4-3  
**Unlocks:** M4-5 (resilience tests)

---

### Issue #M4-5: Write resilience core tests

**Why:** Validate FSM, wrapper, persistence, manager behaviour  
**Inputs:**
- Completed resilience components (M4-1 through M4-4)

**Steps:**
1. Create `tests/k1/l5_infrastructure/test_resilience_circuit_breaker.py`
2. Test FSM transitions for failure/success thresholds
3. Test call wrapper short-circuits when OPEN
4. Test persistence load/save cycle (use redis mock fixture)
5. Test manager execute path with fallback invocation
6. Validate event bus emits OPEN/HALF_OPEN events
7. Assert metrics counters updated
8. Add performance assertions (lookup <1ms, transition <1ms)

**Done Criteria:**
- [ ] 20+ test cases covering all states + events
- [ ] Persistence round-trip validated
- [ ] Metrics + events asserted
- [ ] Performance budgets met (<1ms transitions)
- [ ] Tests pass: `pytest tests/k1/l5_infrastructure/test_resilience_circuit_breaker.py -v`
- [ ] Coverage ≥90%

**Blocked By:** M4-4  
**Unlocks:** M4-6 (fallback strategies)

---

## Epic 4.2: Fallback Strategies & Recovery

**Components:** `resilience/fallbacks/alternate_service.py`, `.../cached_response.py`, `.../default_response.py`, `.../degraded_mode.py`, `resilience/recovery_strategies.py`, `resilience/timeout_handler.py`  
**ADRs:** ADR-0009a, ADR-0008 (Saga integration)

### Issue #M4-6: Implement fallbacks/alternate_service.py

**Why:** Provide alternate service fallback logic referenced by manager  
**Inputs:**
- ADR-0009a, ADR-0008
- Existing stub: `k1/l5_infrastructure/resilience/fallbacks/alternate_service.py`

**Steps:**
1. Implement `AlternateServiceFallback` class with async `execute(context)`
2. Integrate capability checks + placement engine request
3. Emit metrics: `k1.resilience.fallback_alt_service_total`
4. Ensure trace + privacy band propagation
5. Reference ADR-0009a in header

**Done Criteria:**
- [ ] Alternate fallback executes against placement engine stub
- [ ] Metrics + tracing included
- [ ] ADR referenced
- [ ] Zero `NotImplementedError`

**Blocked By:** M4-5  
**Unlocks:** M4-7 (remaining fallbacks)

---

### Issue #M4-7: Implement remaining fallback modules

**Why:** Complete fallback suite for degraded modes  
**Inputs:**
- ADR-0009a, ADR-0008
- Files: `cached_response.py`, `default_response.py`, `degraded_mode.py`

**Steps:**
1. Implement cached response retrieval with TTL validation
2. Implement default response builder per ADR guidance
3. Implement degraded mode throttle adjustments
4. Update `recovery_strategies.py` registry with all fallbacks
5. Ensure metrics/tracing for each fallback

**Done Criteria:**
- [ ] Each fallback returns structured `FallbackResult`
- [ ] Recovery strategies registry exports callable factories
- [ ] Metrics emitted for each fallback type
- [ ] Zero `NotImplementedError`

**Blocked By:** M4-6  
**Unlocks:** M4-8 (fallback tests)

---

### Issue #M4-8: Write resilience fallback tests

**Why:** Validate fallback behaviour and registry wiring  
**Inputs:**
- Completed fallbacks (M4-6, M4-7)

**Steps:**
1. Create `tests/k1/l5_infrastructure/test_resilience_fallbacks.py`
2. Test alternate service fallback path (mock placement)
3. Test cached response fallback (hit/miss + TTL expiry)
4. Test default + degraded mode outputs
5. Validate registry returns correct fallback for service
6. Assert metrics increments per fallback type
7. Verify trace attributes present

**Done Criteria:**
- [ ] 12+ test cases covering all fallback types
- [ ] TTL + degraded mode behaviour verified
- [ ] Metrics/traces asserted
- [ ] Tests pass: `pytest tests/k1/l5_infrastructure/test_resilience_fallbacks.py -v`

**Blocked By:** M4-7  
**Unlocks:** M4-9 (extensions framework)

---

## Epic 4.3: Extensions Framework

**Components:** `extensions/extension_registry.py`, `extensions/config_provider.py`, `extensions/metrics_exporter.py`, `extensions/security_policy.py`, `extensions/trace_exporter.py`, `extensions/performance_optimizer.py`, etc.  
**ADRs:** ADR-0034, ADR-0075

### Issue #M4-9: Implement extensions/extension_registry.py

**Why:** Core registry enabling runtime extension management  
**Inputs:**
- ADR-0034 (MCP protocol adoption)
- ADR-0075 (Extensibility framework)
- Existing stub: `k1/l5_infrastructure/extensions/extension_registry.py`

**Steps:**
1. Implement `ExtensionRegistry` with register/load/unload APIs
2. Support capability descriptors + privacy band declarations
3. Add lifecycle hooks (on_load, on_unload, health_check)
4. Integrate with observability metrics
5. Reference ADR-0034, 0075 in header

**Done Criteria:**
- [ ] Registry maintains extension metadata + lifecycle
- [ ] Capability + band data stored
- [ ] Metrics/traces emitted on load events
- [ ] ADRs referenced
- [ ] Zero `NotImplementedError`

**Blocked By:** M4-8  
**Unlocks:** M4-10 (extension implementations)

---

### Issue #M4-10: Implement core extension adapters

**Why:** Provide concrete extension types aligning with registry  
**Inputs:**
- Files: `circuit_breaker_strategy.py`, `config_provider.py`, `metrics_exporter.py`, `trace_exporter.py`, `security_policy.py`, `performance_optimizer.py`, `storage_tier.py`, `placement_strategy.py`, `thermal_policy.py`

**Steps:**
1. For each extension file, implement class inheriting from base protocol
2. Enforce privacy band + capability validation
3. Integrate metrics/traces for runtime hooks
4. Ensure thread-safe state where applicable (e.g., config cache)
5. Reference ADR-0075 + specific ADRs (e.g., ADR-0027 for placement)

**Done Criteria:**
- [ ] All extension modules export functional classes
- [ ] Capability + band metadata validated
- [ ] Observability instrumentation added
- [ ] ADR references present
- [ ] Zero `NotImplementedError`

**Blocked By:** M4-9  
**Unlocks:** M4-11 (extensions tests)

---

### Issue #M4-11: Write extensions framework tests

**Why:** Validate registry operations and extension contracts  
**Inputs:**
- Completed extensions (M4-9, M4-10)

**Steps:**
1. Create `tests/k1/l5_infrastructure/test_extensions.py`
2. Test registration/unregistration with lifecycle hooks
3. Test capability + privacy band enforcement
4. Test hot-reload scenario (unload + reload extension)
5. Test metrics exporter integration (records Prometheus metrics)
6. Assert trace exporter attaches cognitive_trace_id

**Done Criteria:**
- [ ] 18+ test cases
- [ ] Lifecycle + safety checks validated
- [ ] Metrics/traces asserted
- [ ] Tests pass: `pytest tests/k1/l5_infrastructure/test_extensions.py -v`
- [ ] Coverage ≥85%

**Blocked By:** M4-10  
**Unlocks:** M4-12 (modules system)

---

## Epic 4.4: Module System

**Components:** `modules/plugin_discovery.py`, `modules/plugin_loader.py`, `modules/__init__.py`  
**ADRs:** ADR-0074, ADR-0075

### Issue #M4-12: Implement modules/plugin_discovery.py

**Why:** Discover extensions/plugins on disk per ADR-0074  
**Inputs:**
- ADR-0074 (Pluggable Module System)
- Existing stub: `k1/l5_infrastructure/modules/plugin_discovery.py`

**Steps:**
1. Implement discovery scanning `modules/` directory with allowlist
2. Validate module manifests (capabilities, privacy bands)
3. Provide async `discover_all()` returning metadata list
4. Emit metrics: `k1.modules.discovered_total`
5. Reference ADR-0074 in header

**Done Criteria:**
- [ ] Discovery returns metadata for valid modules
- [ ] Manifest validation enforced
- [ ] Metrics emitted
- [ ] ADR-0074 referenced
- [ ] Zero `NotImplementedError`

**Blocked By:** M4-11  
**Unlocks:** M4-13 (plugin loader)

---

### Issue #M4-13: Implement modules/plugin_loader.py

**Why:** Load discovered modules dynamically with hot-reload  
**Inputs:**
- ADR-0074, ADR-0075
- Completed discovery (M4-12)
- Existing stub: `k1/l5_infrastructure/modules/plugin_loader.py`

**Steps:**
1. Implement `PluginLoader` class with `load`, `unload`, `reload`
2. Enforce sandboxing hooks (per ADR-0034 security guidance)
3. Integrate with ExtensionRegistry to register loaded plugins
4. Provide telemetry: `k1.modules.loaded_total`, `k1.modules.reload_latency_ms`
5. Add error isolation (failed plugin does not crash loader)

**Done Criteria:**
- [ ] Load/unload/reload operations functional
- [ ] ExtensionRegistry integration working
- [ ] Metrics/traces emitted
- [ ] Sandbox hooks present
- [ ] Zero `NotImplementedError`

**Blocked By:** M4-12  
**Unlocks:** M4-14 (module tests)

---

### Issue #M4-14: Write module system tests

**Why:** Ensure discovery + loader operate correctly  
**Inputs:**
- Completed module components (M4-12, M4-13)

**Steps:**
1. Create `tests/k1/l5_infrastructure/test_modules.py`
2. Test discovery returns expected modules (use temp directories)
3. Test loader load/unload/reload flows
4. Validate sandbox enforcement + capability declarations
5. Assert ExtensionRegistry gets populated
6. Measure reload latency (<10ms warm per ADR-0074)

**Done Criteria:**
- [ ] 15+ test cases
- [ ] Discovery + loader integration validated
- [ ] Performance budget verified (reload <10ms)
- [ ] Tests pass: `pytest tests/k1/l5_infrastructure/test_modules.py -v`

**Blocked By:** M4-13  
**Unlocks:** M4-15 (package exports)

---

### Issue #M4-15: Update resilience/extensions/modules __init__.py files

**Why:** Export newly implemented APIs  
**Inputs:**
- Completed resilience, extensions, modules components

**Steps:**
1. Update `resilience/__init__.py` with circuit breaker exports & docstring (remove STUB)
2. Update `extensions/__init__.py` with registry + extension classes
3. Update `modules/__init__.py` with discovery + loader exports
4. Verify import statements succeed via quick scripts

**Done Criteria:**
- [ ] All exports available
- [ ] Import smoke tests pass
- [ ] Docstrings updated to IMPLEMENTED

**Blocked By:** M4-14  
**Unlocks:** M5-1 (hardening)

---

## M4 Summary

**Total Issues:** 15 (M4-1 through M4-15)  
**Estimated Effort:** ~14-16 developer days  
**Critical Path:** M4-1 → M4-2 → M4-3 → M4-4 → M4-5 → M4-6 → M4-7 → M4-8 → M4-9 → M4-10 → M4-11 → M4-12 → M4-13 → M4-14 → M4-15  

**Completion Checklist:**
- [ ] Circuit breaker orchestrator operational with persistence + observability
- [ ] Fallback suite wired and tested
- [ ] Extension registry + adapters functional
- [ ] Module discovery/loader delivering hot-reload
- [ ] All M4 tests passing (50+ tests)
- [ ] Performance budgets met (state transition <1ms, reload <10ms)
- [ ] Zero `NotImplementedError` in M4 components
- [ ] ADR references in all headers

**Next:** M5 - Hardening & Performance (Integration tests, perf benchmarking)

---

# 📍 MILESTONE 5: Hardening & Performance

**Goal:** Validate end-to-end behaviour, enforce performance budgets, and finalize observability + docs  
**Dependencies:** M4 complete  
**Acceptance Criteria:**
- Integration test suites cover cross-component flows
- Performance budgets validated with automated benchmarks
- Failure injection + recovery tests in place
- Docs, diagrams, and memories updated per Gate 5
- All M5 tests/benchmarks green

---

## Epic 5.1: End-to-End Integration Tests

**Components:** `tests/k1/l5_infrastructure/test_integration_*.py`, orchestrated fixtures  
**ADRs:** ADR-0048, ADR-0028, ADR-0009, ADR-0032

### Issue #M5-1: Build integration test harness

**Why:** Provide shared fixtures + utilities for cross-component tests  
**Inputs:**
- Existing tests from M1-M4
- Create `tests/k1/l5_infrastructure/conftest.py`

**Steps:**
1. Set up async fixtures for AdmissionController, BackpressureManager, CircuitBreakerManager, Cache, EventBus
2. Provide fake K0 observability client using in-memory queues
3. Seed sample policies, modules, extensions
4. Ensure teardown drains tasks + closes loops

**Done Criteria:**
- [ ] Shared fixtures reusable across integration tests
- [ ] No leaked tasks or sleeps
- [ ] Documented in fixture docstrings

**Blocked By:** M4-15  
**Unlocks:** M5-2 (integration flows)

---

### Issue #M5-2: Admission → Scheduling → Resilience flow test

**Why:** Validate key control-plane pipeline end-to-end  
**Inputs:**
- Harness (M5-1)

**Steps:**
1. Create `tests/k1/l5_infrastructure/test_integration_control_plane.py`
2. Simulate task submission (admission -> rate limit -> backpressure -> scheduler)
3. Inject failures to trigger circuit breaker + fallback
4. Assert metrics + traces emitted throughout flow
5. Verify performance budgets (decision <10ms, fallback <20ms)

**Done Criteria:**
- [ ] Scenario covers admission, backpressure, resilience
- [ ] Metrics/traces validated
- [ ] Performance budgets asserted
- [ ] Test passes under `pytest -k integration_control_plane`

**Blocked By:** M5-1  
**Unlocks:** M5-3 (module/extension integration)

---

### Issue #M5-3: Extensions & Modules integration test

**Why:** Ensure module loader + extension registry interplay works in situ  
**Inputs:**
- Harness (M5-1)

**Steps:**
1. Create `tests/k1/l5_infrastructure/test_integration_extensions_modules.py`
2. Load sample plugin, register extensions, trigger load/unload/reload
3. Validate capability + privacy enforcement during runtime
4. Ensure observability data forwarded to K0 client mock
5. Verify reload latency <10ms warm

**Done Criteria:**
- [ ] Extension + module lifecycle exercised end-to-end
- [ ] Observability outputs asserted
- [ ] Performance budget met (reload <10ms)
- [ ] Test passes

**Blocked By:** M5-2  
**Unlocks:** M5-4 (failure injection)

---

### Issue #M5-4: Failure-injection regression suite

**Why:** Validate resilience under compounded failures  
**Inputs:**
- Build `tests/k1/l5_infrastructure/test_integration_failures.py`

**Steps:**
1. Simulate cascading failures (cache miss → service failure → circuit open)
2. Verify backpressure escalates to HIGH + admission defers correctly
3. Test Redis outage for state persistence (CircuitBreakerManager fallback to in-memory)
4. Validate module loader handles faulty plugin (unloads + quarantines)
5. Ensure audit logs emitted for RED band overrides

**Done Criteria:**
- [ ] Failure scenarios all handled gracefully
- [ ] No data loss or privacy violations
- [ ] Logs/metrics confirm recovery steps
- [ ] Tests pass under stress mode (`pytest -k integration_failures`)

**Blocked By:** M5-3  
**Unlocks:** M5-5 (performance benchmarking)

---

## Epic 5.2: Performance Benchmarking

**Components:** `tests/k1/l5_infrastructure/perf/test_perf_*.py` (pytest benchmarks or custom harness)  
**ADRs:** ADR-0024 (Performance Budgets), ADR-0024b (component budgets)

### Issue #M5-5: Implement performance fixtures

**Why:** Provide deterministic benchmarking harness  
**Inputs:**
- Use `pytest-benchmark` or custom timing utilities (no sleeps)

**Steps:**
1. Create `tests/k1/l5_infrastructure/perf/conftest.py`
2. Provide high-resolution timer utilities (perf_counter)
3. Configure warm-up iterations + sample counts per ADR budgets

**Done Criteria:**
- [ ] Benchmark fixtures reusable across perf tests
- [ ] Warm-up/warm caches handled
- [ ] Documented budgets in comments referencing ADR-0024

**Blocked By:** M5-4  
**Unlocks:** M5-6 (component perf tests)

---

### Issue #M5-6: Component performance tests

**Why:** Verify each critical component meets P95 budgets  
**Inputs:**
- Fixtures (M5-5)

**Steps:**
1. Create `tests/k1/l5_infrastructure/perf/test_perf_components.py`
2. Test admission decision latency (<10ms)
3. Test cache get/set (<0.1ms)
4. Test circuit breaker transition (<1ms)
5. Test module reload (<10ms warm)
6. Fail test if budget exceeded; emit histogram summary

**Done Criteria:**
- [ ] Benchmarks cover key components
- [ ] Budgets enforced with assertions
- [ ] Results exported (CSV/JSON) for CI artifacts
- [ ] Test passes within budget thresholds

**Blocked By:** M5-5  
**Unlocks:** M5-7 (system perf mix)

---

### Issue #M5-7: System performance mix test

**Why:** Validate composite workload under production-like load  
**Inputs:**
- Bench harness (M5-5, M5-6)

**Steps:**
1. Create `tests/k1/l5_infrastructure/perf/test_perf_system_mix.py`
2. Simulate mixed load (admission + caching + resilience) with concurrency
3. Measure TTFT proxy metric (simulated) to ensure <150ms target
4. Record metrics/traces for QA analysis
5. Ensure backpressure prevents overload (no queue >80%)

**Done Criteria:**
- [ ] Mix test replicates multi-component load
- [ ] Critical budgets validated (TTFT proxy, queue depth)
- [ ] Metrics/traces captured for observability dashboards
- [ ] Test passes and stores artifacts

**Blocked By:** M5-6  
**Unlocks:** M5-8 (observability hardening)

---

## Epic 5.3: Observability & Compliance Hardening

**Components:** Observability dashboards, alert rules, audit logs  
**ADRs:** ADR-0029, ADR-0030, ADR-0035, ADR-0039

### Issue #M5-8: Observability dashboards & alerts

**Why:** Finalize metrics/traces/logs with alert thresholds  
**Inputs:**
- Metrics emitted across components

**Steps:**
1. Define Prometheus recording rules + alert thresholds (metrics directory)
2. Ensure RED/BLACK bands trigger audit alerts
3. Document metrics taxonomy for dashboards (no new .md; update existing ADR appendices if required)

**Done Criteria:**
- [ ] Alert rules defined + validated via unit tests (where possible)
- [ ] Metrics coverage report updated
- [ ] No stray markdown files

**Blocked By:** M5-7  
**Unlocks:** M5-9 (privacy/audit hardening)

---

### Issue #M5-9: Privacy & audit verification

**Why:** Ensure privacy band enforcement + audit trails intact  
**Inputs:**
- Observability + resilience outputs

**Steps:**
1. Add tests verifying privacy overrides log audit entries (RED/BLACK)
2. Validate `cognitive_trace_id` propagated across integration flows
3. Ensure DSAR-related hooks (where applicable) register events with K0

**Done Criteria:**
- [ ] Privacy band tests pass (`pytest -k privacy_audit`)
- [ ] Trace propagation coverage >95%
- [ ] Audit log entries verified

**Blocked By:** M5-8  
**Unlocks:** M5-10 (Gate 5 deliverables)

---

## Epic 5.4: Gate 5 Deliverables

**Components:** Docs updates (existing ADR appendices), memory logs, diagrams  
**ADRs:** 5-Gate process memo

### Issue #M5-10: Update diagrams & ADR appendices

**Why:** Reflect final implementations without creating new stray markdown  
**Inputs:**
- `architecture_diagrams/k1/k1_infrastructure_services.mmd`
- Relevant ADR appendices (update existing files)

**Steps:**
1. Update Mermaid diagrams with implemented components (validate diagrams)
2. Append implementation notes to accepted ADRs (no new ADRs unless gap found)
3. Run diagram validation script

**Done Criteria:**
- [ ] Diagrams updated + validated
- [ ] ADR appendices reflect final state
- [ ] No new markdown files beyond allowed scopes

**Blocked By:** M5-9  
**Unlocks:** M5-11 (memory updates)

---

### Issue #M5-11: Record change summary & memories

**Why:** Satisfy Gate 5 memory requirement  
**Inputs:**
- Entire implementation log

**Steps:**
1. Update workspace memory with change summary (epics, files, tests, perf)
2. Ensure diagrams + metrics references included
3. Link to perf artifacts for traceability

**Done Criteria:**
- [ ] Memory entries created/updated
- [ ] Change summary includes ADR + contract references
- [ ] Task officially closed post verification

**Blocked By:** M5-10  
**Unlocks:** Completion

---

## M5 Summary

**Total Issues:** 11 (M5-1 through M5-11)  
**Estimated Effort:** ~12-14 developer days  
**Critical Path:** M5-1 → M5-2 → M5-3 → M5-4 → M5-5 → M5-6 → M5-7 → M5-8 → M5-9 → M5-10 → M5-11  

**Completion Checklist:**
- [ ] Integration harness + cross-component tests
- [ ] Performance budgets enforced via automated benchmarks
- [ ] Failure injection suite green
- [ ] Observability + privacy hardening complete
- [ ] Gate 5 deliverables updated (diagrams, memories)
- [ ] Zero failing tests/benchmarks

---

# 🧭 Grand Summary & Execution Order

**Milestones & Issue Counts:**
- M1: 11 Issues (Foundation & Observability)
- M2: 11 Issues (Core Runtime Services)
- M3: 9 Issues (Control Plane)
- M4: 15 Issues (Resilience & Integration)
- M5: 11 Issues (Hardening & Performance)

**Total:** 57 sequential Issues (~44-52 developer days)

**Global Dependency Chain:**

```text
M1-1 → … → M1-11 →
M2-1 → … → M2-11 →
M3-1 → … → M3-9 →
M4-1 → … → M4-15 →
M5-1 → … → M5-11
```

**Initial Focus (first three actions):**
1. Implement `observability/metrics.py` (Issue M1-1)
2. Write `test_observability_metrics.py` (Issue M1-2)
3. Implement `observability/tracing.py` (Issue M1-3)

Proceed sequentially; each Issue unlocks the next to maintain contracts-first discipline.

---
