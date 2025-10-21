# FlatBuffers Contracts Overview

**Source ADRs:** ADR-0001b, ADR-0001c

## Overview

This directory contains all 76 FlatBuffers schema contracts organized by K1's 5-layer architecture. FlatBuffers provides zero-copy serialization with <1ms performance for all inter-component communication.

## Why FlatBuffers?

**Research Foundation:** FlatBuffers (Google) - zero-copy serialization for performance-critical systems

### Benefits
- **Zero-copy deserialization:** Access data without parsing
- **Performance:** <1ms serialization/deserialization
- **Memory efficiency:** Compact binary format
- **Type safety:** Strongly typed schemas
- **Forward/backward compatibility:** Schema evolution support
- **Language support:** C++, Python, Rust, TypeScript, etc.

## Directory Structure

```
flatbuffers/
├── layer1_kernel/          # Core kernel schemas (Agent, Orchestrator, Planner, Protocols, Learning)
├── layer2_state/           # State & persistence schemas (SessionState, Memory, K0 Bridge)
├── layer3_execution/       # Execution schemas (Tools, Model Hub, MCP, Streaming)
├── layer4_ingress/         # Ingress schemas (API, WebSocket, Voice, Barge-In)
└── layer5_infrastructure/  # Infrastructure schemas (Config, Observability, Thermal, Backpressure)
```

## Schema Distribution (76 Total)

```yaml
schema_count_by_layer:
  layer1_kernel: 18 schemas
    - Agent Fabric: 4 (AgentState, Capabilities, HireRequest, HireResponse)
    - Orchestrator: 4 (TaskAnnouncement, BidSubmission, TaskAssignment, TaskCompletion)
    - Planner: 4 (PlanSketch, ExpandedPlan, PlanValidation, CommittedPlan)
    - Protocol Monitor: 3 (ProtocolState, ProtocolViolation, ProtocolTimeout)
    - Learning Loop: 3 (FeedbackSignal, LearningDelta, DriftDetection)

  layer2_state: 16 schemas
    - SessionState: 8 (SessionState, 6 sections, StateDelta)
    - Memory Manager: 4 (MemoryEntry, MemoryMetadata, RecallQuery, RecallResult)
    - Receipt System: 2 (Receipt, ReceiptVerification)
    - K0 Bridge: 2 (K0Request, K0Response)

  layer3_execution: 14 schemas
    - Tool Runner: 3 (ToolInvocation, ToolResult, ToolError)
    - Model Hub: 4 (InferenceRequest, InferenceResponse, StreamingChunk, KVCache)
    - MCP Gateway: 3 (MCPRequest, MCPResponse, MCPToolSchema)
    - Streaming Engine: 4 (StreamStart, StreamChunk, StreamEnd, StreamMetadata)

  layer4_ingress: 14 schemas
    - API Gateway: 4 (HTTPRequest, HTTPResponse, SessionCreate, TurnRequest)
    - WebSocket: 3 (WSMessage, WSConnect, WSDisconnect)
    - Voice Pipeline: 4 (AudioFrame, VoiceCommand, TTSRequest, TTSAudio)
    - Barge-In: 3 (BargeInEvent, CancellationRequest, CancellationResponse)

  layer5_infrastructure: 14 schemas
    - Config Manager: 3 (Configuration, ConfigDelta, ConfigValidation)
    - Observability: 3 (LogEntry, MetricPoint, TraceSpan)
    - Thermal Manager: 3 (ThermalState, ThermalEvent, PlacementDecision)
    - Backpressure: 2 (BackpressureSignal, LoadMetrics)
    - Error Recovery: 3 (CircuitBreakerState, RetryPolicy, SagaState)

total_schemas: 76
```

## Schema Standards

### Naming Conventions

```yaml
naming_conventions:
  schema_files: PascalCase.fbs (e.g., AgentState.fbs)
  namespaces: k1.<layer>.<component> (e.g., k1.agent_fabric)
  tables: PascalCase (e.g., AgentState)
  fields: snake_case (e.g., agent_id, created_at)
  enums: PascalCase (e.g., AgentStateEnum)
  enum_values: UPPER_SNAKE_CASE (e.g., ACTIVE, WARMING)
```

### Required Fields

```yaml
required_fields:
  all_schemas:
    - version: uint16 (schema version)
    - timestamp: int64 (unix_ms, when applicable)
    - trace_id: string (cognitive_trace_id, for tracing)

  request_schemas:
    - Additional: request_id, timeout_ms

  response_schemas:
    - Additional: success, error (optional)
```

### Schema Template

```flatbuffers
// TemplateName.fbs
namespace k1.component;

/// Documentation for enum
enum StatusEnum: byte {
  PENDING = 0,
  ACTIVE = 1,
  COMPLETED = 2
}

/// Documentation for table
table TemplateName {
  // Required fields
  id: string (required);
  status: StatusEnum;

  // Optional fields
  metadata: [ubyte];  // JSON or nested table

  // Standard fields
  version: uint16 = 1;
  timestamp: int64;
  trace_id: string;
}

root_type TemplateName;
```

## Performance Characteristics

```yaml
performance_targets:
  serialization:
    p95_latency_us: 100
    p99_latency_us: 500
    throughput_ops_per_sec: 100000

  deserialization:
    p95_latency_us: 50  # Zero-copy
    p99_latency_us: 100
    throughput_ops_per_sec: 200000

  memory:
    overhead_bytes: <64 per message
    zero_copy: true

size_budgets:
  small_messages: <1KB (state transitions, events)
  medium_messages: 1-16KB (plans, contexts)
  large_messages: 16-64KB (SessionState, batches)
  max_message_size: 64KB
```

## Schema Evolution

```yaml
schema_evolution:
  versioning:
    - Include version field in all schemas
    - Increment version on breaking changes

  backward_compatibility:
    - Add new fields as optional
    - Never remove fields (deprecate instead)
    - Never change field types
    - Never change field IDs

  forward_compatibility:
    - Parser ignores unknown fields
    - Parser uses defaults for missing fields

  migration_strategy:
    - Old clients can read new schemas (ignore new fields)
    - New clients can read old schemas (use defaults)
    - Gradual rollout of schema changes
```

## Code Generation

```yaml
code_generation:
  supported_languages:
    - Python (primary for K1)
    - C++ (for performance-critical paths)
    - TypeScript (for frontend clients)
    - Rust (future consideration)

  build_process:
    - flatc compiler generates code from .fbs schemas
    - Generated code checked into repository
    - CI/CD validates schemas on changes

  commands:
    python: flatc --python schema.fbs
    cpp: flatc --cpp schema.fbs
    typescript: flatc --ts schema.fbs
```

## Usage Examples

### Python Serialization

```python
import flatbuffers
from k1.agent_fabric import AgentState, AgentStateEnum

# Create builder
builder = flatbuffers.Builder(1024)

# Create agent_id string
agent_id = builder.CreateString("agent-123")
trace_id = builder.CreateString("trace-abc")

# Create AgentState
AgentState.Start(builder)
AgentState.AddAgentId(builder, agent_id)
AgentState.AddState(builder, AgentStateEnum.ACTIVE)
AgentState.AddMemoryMb(builder, 500)
AgentState.AddTraceId(builder, trace_id)
AgentState.AddTimestamp(builder, time.time_ns() // 1_000_000)
AgentState.AddVersion(builder, 1)
agent_state = AgentState.End(builder)

builder.Finish(agent_state)
serialized = bytes(builder.Output())
```

### Python Deserialization (Zero-Copy)

```python
from k1.agent_fabric import AgentState

# Deserialize (zero-copy)
agent = AgentState.GetRootAs(serialized, 0)

# Access fields (no parsing overhead)
print(f"Agent ID: {agent.AgentId().decode()}")
print(f"State: {agent.State()}")
print(f"Memory: {agent.MemoryMb()} MB")
```

## Testing Strategies

```yaml
schema_tests:
  unit_tests:
    - Serialization/deserialization roundtrip
    - Field access correctness
    - Default value handling
    - Null safety

  integration_tests:
    - Cross-component message exchange
    - Schema version compatibility
    - Large message handling

  performance_tests:
    - Serialization latency benchmarks
    - Deserialization latency benchmarks
    - Memory usage profiling
    - Throughput testing

  compatibility_tests:
    - Old schema → new parser
    - New schema → old parser
    - Missing field handling
```

## Monitoring

```yaml
observability:
  metrics:
    - flatbuffers_serialization_duration_us{schema, percentile}
    - flatbuffers_deserialization_duration_us{schema, percentile}
    - flatbuffers_message_size_bytes{schema, percentile}
    - flatbuffers_serialization_errors_total{schema, error_type}

  alerts:
    - FlatBuffersSerializationSlow: p95 > 100us
    - FlatBuffersMessageTooLarge: size > 64KB
    - FlatBuffersSerializationError: error_rate > 0.1%
```

## Best Practices

```yaml
best_practices:
  schema_design:
    - Keep schemas small and focused
    - Use nested tables for complex structures
    - Prefer enums over magic numbers
    - Document all fields with comments

  field_ordering:
    - Order fields by size (largest first) for memory alignment
    - Group related fields together
    - Put required fields first

  versioning:
    - Always include version field
    - Document breaking changes in comments
    - Use semantic versioning (major.minor.patch)

  performance:
    - Reuse builders when possible
    - Avoid excessive nesting (max 3 levels)
    - Keep message sizes < 64KB
    - Profile serialization hot paths
```

## Tools & Resources

```yaml
tools:
  flatc_compiler:
    download: https://github.com/google/flatbuffers/releases
    version: 23.5.26 or later

  schema_validation:
    - flatc --conform schema.fbs (validate syntax)
    - flatc --cpp --gen-object-api (generate validation code)

  benchmarking:
    - flatbuffers_benchmark tool
    - py-spy for Python profiling
    - perf for C++ profiling
```

## Related Contracts

- K0 Bridge: `../k0_bridge/`
- SessionState: `../sessionstate/`
- Performance: `../performance/`
- All layer contracts: `./layer1_kernel/` through `./layer5_infrastructure/`

---

**Last Updated:** 2025-10-13

**Schema Count:** 76 total FlatBuffers schemas across 5 architectural layers
