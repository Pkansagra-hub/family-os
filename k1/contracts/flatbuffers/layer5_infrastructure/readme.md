# FlatBuffers Contracts - Layer 5 (Infrastructure)

**Source ADRs:** ADR-0001b, ADR-0012, ADR-0016

## Overview

This directory contains FlatBuffers schema contracts for Layer 5 (Infrastructure) components: Config Manager, Observability, Thermal Manager, and Backpressure.

## Layer 5 Components

Layer 5 provides foundational infrastructure services for the entire K1 system.

## Contracts Included

### 1. Config Manager Schemas
- `Configuration.fbs` - Complete K1 configuration
- `ConfigDelta.fbs` - Configuration update delta
- `ConfigValidation.fbs` - Validation result

### 2. Observability Schemas
- `LogEntry.fbs` - Structured log entry
- `MetricPoint.fbs` - Prometheus metric
- `TraceSpan.fbs` - OpenTelemetry span

### 3. Thermal Manager Schemas
- `ThermalState.fbs` - Device thermal state
- `ThermalEvent.fbs` - Thermal state change
- `PlacementDecision.fbs` - Execution placement

### 4. Backpressure Schemas
- `BackpressureSignal.fbs` - Backpressure notification
- `LoadMetrics.fbs` - System load metrics

## Schema Example: Configuration

```flatbuffers
// Configuration.fbs
namespace k1.infrastructure;

table AgentFabricConfig {
  max_agents_per_session: uint8;
  supervisor_check_interval_ms: uint32;
  warmup_timeout_ms: uint32;
  idle_timeout_ms: uint32;
}

table OrchestratorConfig {
  negotiation_timeout_ms: uint32;
  selection_timeout_ms: uint32;
  execution_timeout_ms: uint32;
}

table Configuration {
  version: string (required);
  agent_fabric: AgentFabricConfig;
  orchestrator: OrchestratorConfig;
  // ... other component configs

  updated_at: int64;
  updated_by: string;
  trace_id: string;
}

root_type Configuration;
```

## Observability Schema

```flatbuffers
// LogEntry.fbs
namespace k1.infrastructure.observability;

enum LogLevel: byte {
  DEBUG = 0,
  INFO = 1,
  WARNING = 2,
  ERROR = 3,
  CRITICAL = 4
}

table LogEntry {
  timestamp: int64 (required);
  level: LogLevel;
  logger: string;
  message: string;
  trace_id: string;
  span_id: string;
  session_id: string;
  actor_id: string;
  metadata: [ubyte];  // JSON metadata
}

root_type LogEntry;
```

## Thermal Schema

```flatbuffers
// ThermalState.fbs
namespace k1.infrastructure.thermal;

enum ThermalStateEnum: byte {
  COOL = 0,
  WARM = 1,
  HOT = 2,
  CRITICAL = 3
}

enum Device: byte {
  NPU = 0,
  GPU = 1,
  CPU = 2,
  REMOTE = 3
}

table ThermalState {
  device: Device;
  state: ThermalStateEnum;
  temperature_celsius: float;
  power_usage_watts: float;
  timestamp: int64;
  trace_id: string;
}

root_type ThermalState;
```

## Backpressure Schema

```flatbuffers
// BackpressureSignal.fbs
namespace k1.infrastructure.backpressure;

enum BackpressureLevel: byte {
  NONE = 0,
  WARNING = 1,
  CRITICAL = 2
}

table BackpressureSignal {
  component: string (required);
  level: BackpressureLevel;
  queue_size: uint32;
  queue_capacity: uint32;
  utilization_percent: float;
  timestamp: int64;
  trace_id: string;
}

root_type BackpressureSignal;
```

## Performance Characteristics

```yaml
performance:
  config_serialization_us: 500
  log_entry_serialization_us: 50
  thermal_state_serialization_us: 20
  backpressure_signal_serialization_us: 10
```

## Related Contracts

- Performance: `../../performance/`
- Observability: `../../observability/`
- Error Recovery: `../../error_recovery/backpressure_cascade.yaml`

---

**Last Updated:** 2025-10-13
