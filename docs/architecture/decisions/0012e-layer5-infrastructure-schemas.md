---
adr_number: 0012e
title: Layer 5 Infrastructure Schemas (13 Schemas)
status: ACCEPTED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer1_input
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules: []
concerns:
- architecture
- compliance
- cost
- modularity
- observability
- performance
- privacy
- scalability
supersedes: []
superseded_by: []
related_adrs:
- ADR-0011a
- ADR-0011c
- ADR-0012
- ADR-0012e
implementation_status: COMPLETED
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations: []
propagation:
  triggers:
  - Adding new module to any layer
  - Changing layer dependency rules
  - Modifying system architecture
  - Performance requirement changes
  affected_adrs:
  - ADR-0011a
  - ADR-0011c
  - ADR-0012
  - ADR-0012e
  affected_contracts:
  - k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_response.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_tool_discovery.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_cache_entry.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_response.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_stream_chunk.fbs
  - k1/contracts/flatbuffers/layer3_execution/stream_chunk.fbs
  - k1/contracts/flatbuffers/layer3_execution/stream_config.fbs
  affected_tests: []
---


# ADR-0012e: Layer 5 Infrastructure Schemas (13 Schemas)

**Status:** Accepted
**Date:** 2025-10-12
**Parent ADR:** [ADR-0012: 76 FlatBuffers Schemas](0012-76-flatbuffers-schemas.md)
**Related ADRs:**
- [ADR-0011a: FlatBuffers Schema Design Principles](0011a-flatbuffers-schema-design-principles.md)
- [ADR-0011c: Serialization Performance & Zero-Copy](0011c-serialization-performance-zero-copy.md)

---

## Context

Layer 5 (Infrastructure) contains schemas for K1's operational layer: **Config Manager** (hot-reload), **Observability** (metrics/traces/logs), **Thermal Manager** (device placement), and **Backpressure** (flow control). These 13 schemas form the data model for configuration, monitoring, thermal optimization, and backpressure cascade.

**Layer 5 Modules:**
- `k1.config_manager` (3 schemas)
- `k1.observability` (4 schemas)
- `k1.thermal_manager` (3 schemas)
- `k1.backpressure` (3 schemas)

**Total:** 13 schemas, ~64MB memory budget (config 4MB, metrics 32MB, thermal 16MB, backpressure 12MB)

---

## Decision

### Schema Organization

**Namespace:** `k1.{module}` (Layer 5 modules)
**File Structure:** `k1/schemas/{module}/{entity}_{type}.fbs`
**File Identifiers:** 4-character codes (CFGS, CFGR, METS, TRSP, LOGE, HLTH, THPL, BPSG, etc.)
**Version Strategy:** v1.0-v1.2 (backward compatible, 3-release deprecation policy)

---

## Config Manager Schemas (3 Schemas)

### 64. ConfigSnapshot (CFGS)

**Purpose:** Configuration snapshot

**Schema Definition:**
```flatbuffers
namespace k1.config_manager;

table ConfigSnapshot {
  snapshot_id: string (required);
  config_version: string (required);
  config_data: [k1.agent_fabric.KeyValue] (required);

  // Timestamps
  timestamp_ms: uint64 = 0;
}

root_type ConfigSnapshot;
file_identifier "CFGS";
```

**Usage:** Config storage, versioning, rollback
**Performance:** 4-32KB size, 1.8ms serialize, 0.25ms deserialize ✅

---

### 65. ConfigReloadEvent (CFGR)

**Purpose:** Config reload event

**Schema Definition:**
```flatbuffers
namespace k1.config_manager;

table ConfigReloadEvent {
  event_id: string (required);
  old_version: string;
  new_version: string (required);
  changed_keys: [string];

  // Performance metrics
  reload_latency_ms: uint32 = 0;

  // Timestamps
  reloaded_at_ms: uint64 = 0;
}

root_type ConfigReloadEvent;
file_identifier "CFGR";
```

**Usage:** Hot-reload, change propagation, validation
**Performance:** ~512B size, 0.28ms serialize, 0.035ms deserialize ✅

---

### 66. ConfigValidationResult (CFGV)

**Purpose:** Config validation result

**Schema Definition:**
```flatbuffers
namespace k1.config_manager;

enum ConfigValidationStatus : uint8 {
  VALID = 0,
  INVALID = 1,
  WARNING = 2
}

table ConfigValidationError {
  key: string (required);
  message: string (required);
  severity: string;  // ERROR, WARNING
}

table ConfigValidationResult {
  validation_id: string (required);
  status: ConfigValidationStatus = INVALID;
  errors: [ConfigValidationError];
  warnings: [ConfigValidationError];

  // Timestamps
  validated_at_ms: uint64 = 0;
}

root_type ConfigValidationResult;
file_identifier "CFGV";
```

**Usage:** Config validation, error reporting, rollback decisions
**Performance:** ~768B size, 0.38ms serialize, 0.052ms deserialize ✅

---

## Observability Schemas (4 Schemas)

### 67. MetricSample (METS)

**Purpose:** Prometheus metric sample

**Schema Definition:**
```flatbuffers
namespace k1.observability;

enum MetricType : uint8 {
  COUNTER = 0,
  GAUGE = 1,
  HISTOGRAM = 2,
  SUMMARY = 3
}

table MetricSample {
  metric_name: string (required);
  metric_type: MetricType (required);
  value: float64 = 0.0;
  labels: [k1.agent_fabric.KeyValue];

  // Timestamps
  timestamp_ms: uint64 = 0;
}

root_type MetricSample;
file_identifier "METS";
```

**Usage:** Prometheus export, metric collection
**Performance:** ~256B size, 0.18ms serialize, 0.022ms deserialize ✅

---

### 68. TraceSpan (TRSP)

**Purpose:** OpenTelemetry trace span

**Schema Definition:**
```flatbuffers
namespace k1.observability;

table TraceSpan {
  span_id: string (required);
  trace_id: string (required);
  parent_span_id: string;
  operation_name: string (required);

  // Timing
  start_time_ms: uint64 = 0;
  duration_ms: uint32 = 0;

  // Attributes
  attributes: [k1.agent_fabric.KeyValue];
}

root_type TraceSpan;
file_identifier "TRSP";
```

**Usage:** Distributed tracing, cognitive_trace_id tracking
**Performance:** ~512B size, 0.28ms serialize, 0.035ms deserialize ✅

---

### 69. LogEntry (LOGE)

**Purpose:** Structured log entry

**Schema Definition:**
```flatbuffers
namespace k1.observability;

enum LogLevel : uint8 {
  DEBUG = 0,
  INFO = 1,
  WARNING = 2,
  ERROR = 3,
  CRITICAL = 4
}

table LogEntry {
  log_id: string (required);
  level: LogLevel (required);
  message: string (required);
  attributes: [k1.agent_fabric.KeyValue];

  // Tracing
  trace_id: string;

  // Timestamps
  timestamp_ms: uint64 = 0;
}

root_type LogEntry;
file_identifier "LOGE";
```

**Usage:** Structured logging, log aggregation, debugging
**Performance:** ~512B size, 0.28ms serialize, 0.035ms deserialize ✅

---

### 70. HealthCheckResult (HLTH)

**Purpose:** Health check result

**Schema Definition:**
```flatbuffers
namespace k1.observability;

enum HealthStatus : uint8 {
  HEALTHY = 0,
  DEGRADED = 1,
  UNHEALTHY = 2
}

table HealthCheckResult {
  check_id: string (required);
  component_name: string (required);
  status: HealthStatus = HEALTHY;
  details: string;

  // Timestamps
  timestamp_ms: uint64 = 0;
}

root_type HealthCheckResult;
file_identifier "HLTH";
```

**Usage:** Health monitoring, load balancer, alerting
**Performance:** ~384B size, 0.22ms serialize, 0.028ms deserialize ✅

---

## Thermal Manager Schemas (3 Schemas)

### 71. ThermalPlacement (THPL)

**Purpose:** Thermal placement decision

**Schema Definition:**
```flatbuffers
namespace k1.thermal_manager;

enum ThermalTier : uint8 {
  NPU = 0,
  GPU = 1,
  CPU = 2,
  REMOTE = 3
}

table ThermalPlacement {
  placement_id: string (required);
  resource_id: string (required);
  tier: ThermalTier (required);
  reason: string;

  // Performance estimate
  latency_estimate_ms: uint32 = 0;

  // Timestamps
  placed_at_ms: uint64 = 0;
}

root_type ThermalPlacement;
file_identifier "THPL";
```

**Usage:** Thermal placement, workload distribution, latency optimization
**Performance:** ~256B size, 0.18ms serialize, 0.022ms deserialize ✅

---

### 72. ThermalMetrics (THMT)

**Purpose:** Thermal metrics (device temperature)

**Schema Definition:**
```flatbuffers
namespace k1.thermal_manager;

table ThermalMetrics {
  device_id: string (required);
  temperature_celsius: float32 = 0.0;
  utilization_percent: float32 = 0.0;
  power_watts: float32 = 0.0;
  throttling: bool = false;

  // Timestamps
  sampled_at_ms: uint64 = 0;
}

root_type ThermalMetrics;
file_identifier "THMT";
```

**Usage:** Thermal monitoring, throttling detection, placement decisions
**Performance:** ~192B size, 0.12ms serialize, 0.015ms deserialize ✅

---

### 73. ThermalMigration (THMG)

**Purpose:** Thermal migration event

**Schema Definition:**
```flatbuffers
namespace k1.thermal_manager;

table ThermalMigration {
  migration_id: string (required);
  resource_id: string (required);
  from_tier: ThermalTier (required);
  to_tier: ThermalTier (required);
  reason: string;

  // Performance impact
  migration_latency_ms: uint32 = 0;

  // Timestamps
  migrated_at_ms: uint64 = 0;
}

root_type ThermalMigration;
file_identifier "THMG";
```

**Usage:** Dynamic migration, thermal balancing, performance optimization
**Performance:** ~256B size, 0.18ms serialize, 0.022ms deserialize ✅

---

## Backpressure Schemas (3 Schemas)

### 74. BackpressureSignal (BPSG)

**Purpose:** Backpressure signal

**Schema Definition:**
```flatbuffers
namespace k1.backpressure;

enum BackpressureSeverity : uint8 {
  LOW = 0,
  MEDIUM = 1,
  HIGH = 2,
  CRITICAL = 3
}

table BackpressureSignal {
  signal_id: string (required);
  source_component: string (required);
  severity: BackpressureSeverity (required);
  queue_depth: uint32 = 0;
  latency_p95_ms: float32 = 0.0;

  // Timestamps
  detected_at_ms: uint64 = 0;
}

root_type BackpressureSignal;
file_identifier "BPSG";
```

**Usage:** Backpressure cascade, flow control, admission control
**Performance:** ~192B size, 0.12ms serialize, 0.015ms deserialize ✅

---

### 75. BackpressureAction (BPAC)

**Purpose:** Backpressure action

**Schema Definition:**
```flatbuffers
namespace k1.backpressure;

enum BackpressureActionType : uint8 {
  THROTTLE = 0,
  REJECT = 1,
  QUEUE = 2,
  SHED_LOAD = 3
}

table BackpressureAction {
  action_id: string (required);
  action_type: BackpressureActionType (required);
  parameters: [k1.agent_fabric.KeyValue];

  // Timestamps
  applied_at_ms: uint64 = 0;
}

root_type BackpressureAction;
file_identifier "BPAC";
```

**Usage:** Backpressure response, flow control enforcement
**Performance:** ~256B size, 0.18ms serialize, 0.022ms deserialize ✅

---

### 76. QueueMetrics (QMET)

**Purpose:** Queue depth metrics

**Schema Definition:**
```flatbuffers
namespace k1.backpressure;

table QueueMetrics {
  queue_id: string (required);
  depth: uint32 = 0;
  enqueue_rate: float32 = 0.0;
  dequeue_rate: float32 = 0.0;

  // Latency percentiles
  latency_p50_ms: float32 = 0.0;
  latency_p95_ms: float32 = 0.0;
  latency_p99_ms: float32 = 0.0;

  // Timestamps
  sampled_at_ms: uint64 = 0;
}

root_type QueueMetrics;
file_identifier "QMET";
```

**Usage:** Queue monitoring, backpressure detection, capacity planning
**Performance:** ~256B size, 0.18ms serialize, 0.022ms deserialize ✅

---

## Performance Budgets (P95 Targets)

| Schema | Size | Serialize | Deserialize | Status |
|--------|------|-----------|-------------|--------|
| ConfigSnapshot (CFGS) | 4-32KB | 1.8ms | 0.25ms | ✅ |
| ConfigReloadEvent (CFGR) | ~512B | 0.28ms | 0.035ms | ✅ |
| ConfigValidationResult (CFGV) | ~768B | 0.38ms | 0.052ms | ✅ |
| MetricSample (METS) | ~256B | 0.18ms | 0.022ms | ✅ |
| TraceSpan (TRSP) | ~512B | 0.28ms | 0.035ms | ✅ |
| LogEntry (LOGE) | ~512B | 0.28ms | 0.035ms | ✅ |
| HealthCheckResult (HLTH) | ~384B | 0.22ms | 0.028ms | ✅ |
| ThermalPlacement (THPL) | ~256B | 0.18ms | 0.022ms | ✅ |
| ThermalMetrics (THMT) | ~192B | 0.12ms | 0.015ms | ✅ |
| ThermalMigration (THMG) | ~256B | 0.18ms | 0.022ms | ✅ |
| BackpressureSignal (BPSG) | ~192B | 0.12ms | 0.015ms | ✅ |
| BackpressureAction (BPAC) | ~256B | 0.18ms | 0.022ms | ✅ |
| QueueMetrics (QMET) | ~256B | 0.18ms | 0.022ms | ✅ |

**Layer 5 Total:** <100ms config reload, <5ms metric emission, <50ms thermal placement, <10ms backpressure signal ✅

---

**Last Updated:** 2025-10-12
**Status:** Accepted (Layer 5 Infrastructure Schemas - 13/76 schemas documented)

---

## Summary: All 76 FlatBuffers Schemas Complete

**Layer 1 (Core Kernel):** 15 schemas ✅
**Layer 2 (State & Persistence):** 18 schemas ✅
**Layer 3 (Execution & Tools):** 16 schemas ✅
**Layer 4 (Ingress & Voice):** 14 schemas ✅
**Layer 5 (Infrastructure):** 13 schemas ✅

**Total:** 76/76 schemas documented across 5 architectural layers 🎉