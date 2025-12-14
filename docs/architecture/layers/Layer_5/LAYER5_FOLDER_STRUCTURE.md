# Layer 5 Folder Structure

**Total Folders Required: 15 Primary + 3 Supporting = 18 Total**

---

## Primary L5 Infrastructure Folders (15)

### 1. `k1/bridge_k0/` - K0 Communication Bridge

**Purpose:** HTTP/2 bidirectional communication with K0, FlatBuffers batching, protocol switching

**Key Files:**
- `command_client.py` - Command execution with response callbacks
- `protocol.py` - Protocol switching (JSON ↔ FlatBuffers)
- `ports/` - Network port management
- `lanes.py` - Request lane prioritization (6 lanes)
- `retrieval.py` - Long-tail retrieval (>250ms batches)
- `batch_client.py` - Batched command sending
- `wal_writer.py` - Write-ahead logs (PLAN_COMMITTED topic)
- `state_delta_emitter.py` - State field_path updates
- `saga_logger.py` - Compensation logs
- `saga_persistence.py` - Saga log persistence

**Status:** 🚧 NEEDS_IMPLEMENTATION

---

### 2. `k1/l5_infrastructure/event_bus/` - Event Pub/Sub

**Purpose:** L1-L2 asynchronous communication, <5ms latency, FIFO ordering

**Key Files:**
- `event_bus.py` - Core pub/sub engine
- `schemas.py` - Event type definitions

**Status:** 🚧 NEEDS_IMPLEMENTATION

---

### 3. `k1/l5_infrastructure/serialization/` - FlatBuffers Serialization

**Purpose:** Zero-copy serialization, 150× faster than JSON

**Key Files:**
- `serializer.py` - FlatBuffers encoding
- `deserializer.py` - FlatBuffers decoding
- `buffer_pool.py` - Reusable buffer management
- `alignment.py` - Memory alignment for SIMD

**Status:** 🚧 NEEDS_IMPLEMENTATION

---

### 4. `k1/l5_infrastructure/resilience/` - Circuit Breaker Pattern

**Purpose:** 3-state FSM (CLOSED→OPEN→HALF_OPEN), per-service configuration

**Key Files:**
- `circuit_breaker_manager.py` - FSM orchestration
- `circuit_fsm.py` - Finite state machine logic
- `call_wrapper.py` - Fail-fast execution wrapper
- `states/` (subdirectory)
  - `closed.py` - Normal operation
  - `open.py` - Failure mode
  - `half_open.py` - Recovery testing
- `fallbacks/` (subdirectory) - Fallback strategies
- `config_manager.py` - Configuration management
- `failure_recorder.py` - Track failures (5 consecutive → OPEN)

**Config:** `k1/config/circuit_breakers.yml`

**Status:** 🚧 NEEDS_IMPLEMENTATION

---

### 5. `k1/l5_infrastructure/storage/` - Multi-Tier Storage Manager
**Purpose:** Hot/Warm/Cold tiering, 99.4% cost reduction
**Key Files:**
- `tier_manager.py` - Tier coordination
- `lifecycle_manager.py` - Eviction policies
- Related L4 implementations:
  - `k1/l4_runtime/storage/hot_tier.py` (in-memory cache)
  - `k1/l4_runtime/storage/warm_tier.py` (SSD cache)
  - `k1/l4_runtime/storage/cold_tier.py` (cloud storage)

**Status:** 🚧 NEEDS_IMPLEMENTATION

---

### 5. `k1/l5_infrastructure/storage/` - Multi-Tier Storage Manager

**Purpose:** Hot/Warm/Cold tiering, 99.4% cost reduction

**Key Files:**
- `tier_manager.py` - Tier coordination
- `lifecycle_manager.py` - Eviction policies
- Related L4 implementations:
  - `k1/l4_runtime/storage/hot_tier.py` (in-memory cache)
  - `k1/l4_runtime/storage/warm_tier.py` (SSD cache)
  - `k1/l4_runtime/storage/cold_tier.py` (cloud storage)

**Status:** 🚧 NEEDS_IMPLEMENTATION

---

### 6. `k1/l5_infrastructure/thermal/` - Thermal Management

**Purpose:** Hysteresis FSM, 4-tier placement cascade

**Key Files:**
- `placement_manager.py` - Placement decisions
- `device_capability.py` - Device form factor & baseline detection
- `sensors.py` - Multi-platform thermal APIs
  - Linux thermal zones
  - Windows WMI
  - macOS IOKit
  - Intel RAPL
  - NVIDIA SMI
  - AMD uProf
- `placement_decision.py` - Hysteresis checks, cooldown enforcement
- `metrics.py` - P50/P95/P99 thermal metrics

**Status:** 🚧 NEEDS_IMPLEMENTATION

---

### 7. `k1/l5_infrastructure/placement/` - Model Placement Cascade

**Purpose:** 4-tier fallback (NPU→GPU→CPU→Remote), <$0.01/inference cost

**Key Files:**
- `cascade_engine.py` - 4-tier decision logic
- `circuit_breaker.py` - Per-adapter state (degradation)
- `capability_matcher.py` - Model requirement validation
- `cost_tracker.py` - Cost accounting ($0.001-0.01/remote)
- `metrics.py` - Placement distribution, privacy compliance

**Status:** 🚧 NEEDS_IMPLEMENTATION

---

### 8. `k1/l5_infrastructure/backpressure/` - Backpressure Coordination

**Purpose:** 3-tier cascading (watermark→pipeline→global)

**Key Files:**
- `watermark_checker.py` - Memory watermark thresholds (80%/90%/95%)
- `voice_pipeline_monitor.py` - 5-stage degradation
- `global_limits_enforcer.py` - Global constraints (512MB memory, 5000 items)
- `cascade_coordinator.py` - Event broadcast coordination (<50ms propagation)
- `privacy_overrides.py` - RED band emergency bypass
- `metrics.py` - Tier transitions, hysteresis gap tracking

**Status:** 🚧 NEEDS_IMPLEMENTATION

---

### 9. `k1/l5_infrastructure/resilience/redis/` - Caching Backend

**Purpose:** KV cache with <1ms latency, 5-minute TTL

**Key Files:**
- `client.py` - Redis GET/SETEX operations
- `connection_pool.py` - Connection pooling

**Note:** L3 maintains KV cache broker: `k1/l3_execution/model_hub/kv_cache_broker.py` (128MB global pool, 64MB prompt cache)

**Status:** 🚧 NEEDS_IMPLEMENTATION

---

### 10. `k1/l5_infrastructure/` - Module System (Root Level)

**Purpose:** Dynamic module discovery, loading, isolation, hot-reload

**Key Files:**
- `module_registry.py` - Module discovery & metadata
- `module_loader.py` - Dynamic loading with isolation
- Related: `k1/modules/` (plugin directory)

**Config Example:** `k1/modules/example_module/metadata.yml`

**Status:** 🚧 NEEDS_IMPLEMENTATION

---

### 11. `k1/l5_infrastructure/extensions/` - Extensibility Framework

**Purpose:** 10 extension points for customization

**Key Files:**
- `config_provider.py` - Config management extension
- `metrics_exporter.py` - Metrics export (Prometheus, CloudWatch)
- `trace_exporter.py` - Trace export (Jaeger, Tempo)
- `log_handler.py` - Custom logging
- `thermal_policy.py` - Thermal policy customization
- `placement_strategy.py` - Model placement strategies
- `storage_tier.py` - Storage tier implementations
- `circuit_breaker_strategy.py` - Circuit breaker strategies
- `security_policy.py` - Security policy enforcement
- `performance_optimizer.py` - Performance tuning
- `extension_registry.py` - Plugin management

**Status:** 🚧 NEEDS_IMPLEMENTATION

---

### 12. `k1/l5_infrastructure/rate_limiting/` - Rate Limiting

**Purpose:** Per-service, per-user rate limits

**Key Files:**
- `limiter.py` - Token bucket algorithm
- `config.yml` - Rate limit policies

**Status:** 🚧 NEEDS_IMPLEMENTATION

---

### 13. `k1/l5_infrastructure/scheduler/` - Task Scheduling

**Purpose:** 4-tier WFQ (URGENT→REALTIME→INTERACTIVE→BACKGROUND)

**Key Files:**
- `wfq.py` - Weighted Fair Queuing implementation
- `task_queue.py` - Task queue management

**Status:** 🚧 NEEDS_IMPLEMENTATION

---

### 14. `k1/l5_infrastructure/admission/` - Admission Control

**Purpose:** Task admission, anti-starvation

**Key Files:**
- `controller.py` - Admission decision logic
- `policies.py` - Admission policies

**Status:** 🚧 NEEDS_IMPLEMENTATION

---

### 15. `k1/config/` - Configuration (Shared)

**Purpose:** YAML-based configuration for all L5 components

**Key Files:**
- `circuit_breakers.yml` - Circuit breaker policies
- `rate_limits.yml` - Rate limiting policies
- `thermal_profiles.yml` - Thermal thresholds
- `placement_cascade.yml` - Model placement rules
- `backpressure_tiers.yml` - Backpressure watermarks
- `performance_budgets.yml` - Turn-level/component budgets

**Status:** 🚧 NEEDS_IMPLEMENTATION

---

## Supporting Folders (3)

### 16. `k1/l4_runtime/storage/` - Storage Tier Implementations

**Purpose:** Hot/Warm/Cold tier implementations (shared with L5)

**Related to L5:** `k1/l5_infrastructure/storage/`

**Key Files:**
- `hot_tier.py` - In-memory cache
- `warm_tier.py` - SSD cache
- `cold_tier.py` - Cloud storage

**Status:** 🚧 NEEDS_IMPLEMENTATION

---

### 17. `k1/l3_execution/model_hub/` - KV Cache Broker

**Purpose:** Global KV cache management (coordinated with L5)

**Related to L5:** `k1/l5_infrastructure/resilience/redis/`

**Key Files:**
- `kv_cache_broker.py` - 128MB global pool, 64MB prompt cache

**Status:** 🚧 NEEDS_IMPLEMENTATION

---

### 18. `k0/` (External - K0 Stack)

**Purpose:** Shared observability infrastructure (NOT duplicated in K1)

**Shared by L5:**
- Prometheus metrics
- Grafana dashboards
- Tempo tracing
- Structured logging

**Status:** 🚧 NEEDS_IMPLEMENTATION

---

## Summary

| # | Folder | Status | Component | Priority |
|----|--------|--------|-----------|----------|
| 1 | `k1/bridge_k0/` | 🚧 NEEDS_IMPLEMENTATION | K0 Bridge | P0 |
| 2 | `k1/l5_infrastructure/event_bus/` | 🚧 NEEDS_IMPLEMENTATION | Event Bus | P0 |
| 3 | `k1/l5_infrastructure/serialization/` | 🚧 NEEDS_IMPLEMENTATION | Serialization | P0 |
| 4 | `k1/l5_infrastructure/resilience/` | 🚧 NEEDS_IMPLEMENTATION | Circuit Breaker | P1 |
| 5 | `k1/l5_infrastructure/storage/` | 🚧 NEEDS_IMPLEMENTATION | Multi-Tier Storage | P1 |
| 6 | `k1/l5_infrastructure/thermal/` | 🚧 NEEDS_IMPLEMENTATION | Thermal Management | M1 |
| 7 | `k1/l5_infrastructure/placement/` | 🚧 NEEDS_IMPLEMENTATION | Model Placement | M1 |
| 8 | `k1/l5_infrastructure/backpressure/` | 🚧 NEEDS_IMPLEMENTATION | Backpressure | M1 |
| 9 | `k1/l5_infrastructure/resilience/redis/` | 🚧 NEEDS_IMPLEMENTATION | Caching | P1 |
| 10 | `k1/l5_infrastructure/` (root) | 🚧 NEEDS_IMPLEMENTATION | Module System | M2 |
| 11 | `k1/l5_infrastructure/extensions/` | 🚧 NEEDS_IMPLEMENTATION | Extensibility | M2 |
| 12 | `k1/l5_infrastructure/rate_limiting/` | 🚧 NEEDS_IMPLEMENTATION | Rate Limiting | P2 |
| 13 | `k1/l5_infrastructure/scheduler/` | 🚧 NEEDS_IMPLEMENTATION | Scheduling | P2 |
| 14 | `k1/l5_infrastructure/admission/` | 🚧 NEEDS_IMPLEMENTATION | Admission Control | P2 |
| 15 | `k1/config/` | 🚧 NEEDS_IMPLEMENTATION | Configuration | P0 |
| 16 | `k1/l4_runtime/storage/` | 🚧 NEEDS_IMPLEMENTATION | Storage Tiers (L4) | P1 |
| 17 | `k1/l3_execution/model_hub/` | 🚧 NEEDS_IMPLEMENTATION | KV Cache (L3) | P1 |
| 18 | `k0/` | 🚧 NEEDS_IMPLEMENTATION | Observability (K0) | P0 |

---

## Implementation Priority

**All 18 Folders:** 🚧 NEEDS_IMPLEMENTATION (Starting Fresh)
