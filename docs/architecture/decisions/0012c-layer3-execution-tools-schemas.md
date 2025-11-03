---
adr_number: 0012c
title: Layer 3 Execution & Tools Schemas (16 Schemas)
status: ACCEPTED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer1_input
- layer3_execution
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
- ADR-0012c
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
  - ADR-0012c
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


# ADR-0012c: Layer 3 Execution & Tools Schemas (16 Schemas)

**Status:** Accepted
**Date:** 2025-10-12
**Parent ADR:** [ADR-0012: 76 FlatBuffers Schemas](0012-76-flatbuffers-schemas.md)
**Related ADRs:**
- [ADR-0011a: FlatBuffers Schema Design Principles](0011a-flatbuffers-schema-design-principles.md)
- [ADR-0011c: Serialization Performance & Zero-Copy](0011c-serialization-performance-zero-copy.md)

---

## Context

Layer 3 (Execution & Tools) contains schemas for K1's execution layer: **Tool Runner** (MCP tool execution), **Model Hub** (LLM inference), **MCP Gateway** (Model Context Protocol), and **Streaming Engine** (audio/video streaming). These 16 schemas form the data model for tool calls, LLM inference, resource access, and real-time streaming.

**Layer 3 Modules:**
- `k1.tool_runner` (5 schemas)
- `k1.model_hub` (4 schemas)
- `k1.mcp_gateway` (4 schemas)
- `k1.streaming_engine` (3 schemas)

**Total:** 16 schemas, ~128MB memory budget (KV cache 128MB)

---

## Decision

### Schema Organization

**Namespace:** `k1.{module}` (Layer 3 modules)
**File Structure:** `k1/schemas/{module}/{entity}_{type}.fbs`
**File Identifiers:** 4-character codes (TDEF, TCLR, TCRS, MREQ, MRSP, MCPM, STCH, etc.)
**Version Strategy:** v1.0-v1.2 (backward compatible, 3-release deprecation policy)

---

## Tool Runner Schemas (5 Schemas)

### 34. ToolDefinition (TDEF)

**Purpose:** Tool definition (MCP tool registry)

**Schema Definition:**
```flatbuffers
namespace k1.tool_runner;

table ToolDefinition {
  tool_id: string (required);
  tool_name: string (required);
  description: string;

  // JSON schemas for parameters and return values
  parameters_schema: string (required);
  return_schema: string (required);

  // Execution constraints
  timeout_ms: uint32 = 3000;
  max_retries: uint8 = 2;
  cost_estimate: float32 = 0.0;

  // MCP server metadata
  server_id: string;
  server_version: string;
}

root_type ToolDefinition;
file_identifier "TDEF";
```

**Usage:** Tool registry, parameter validation, cost estimation
**Performance:** ~1-4KB size, 0.45ms serialize, 0.062ms deserialize ✅

---

### 35. ToolCallRequest (TCLR)

**Purpose:** Tool call request

**Schema Definition:**
```flatbuffers
namespace k1.tool_runner;

table ToolCallRequest {
  call_id: string (required);
  tool_id: string (required);
  parameters: string (required);  // JSON

  // Caller metadata
  caller_agent_id: string;
  turn_id: string;

  // Execution constraints
  timeout_ms: uint32 = 3000;
  priority: uint8 = 5;

  // Timestamps
  requested_at_ms: uint64 = 0;
  deadline_ms: uint64 = 0;
}

root_type ToolCallRequest;
file_identifier "TCLR";
```

**Usage:** Tool execution, parameter binding, timeout enforcement
**Performance:** 512B-4KB size, 0.38ms serialize, 0.052ms deserialize ✅

---

### 36. ToolCallResponse (TCRS)

**Purpose:** Tool call response

**Schema Definition:**
```flatbuffers
namespace k1.tool_runner;

enum ToolCallStatus : uint8 {
  SUCCESS = 0,
  FAILURE = 1,
  TIMEOUT = 2,
  CANCELLED = 3
}

table ToolCallResponse {
  call_id: string (required);
  status: ToolCallStatus = FAILURE;

  // Result (if SUCCESS)
  result_data: string;
  result_type: string;  // MIME type

  // Error (if FAILURE/TIMEOUT)
  error_message: string;
  error_code: string;

  // Performance metrics
  latency_ms: uint32 = 0;

  // Timestamps
  completed_at_ms: uint64 = 0;
}

root_type ToolCallResponse;
file_identifier "TCRS";
```

**Usage:** Tool results, error handling, performance tracking
**Performance:** 512B-16KB size, 0.85ms serialize, 0.12ms deserialize ✅

---

### 37. ToolCallProgress (TCPG)

**Purpose:** Tool call progress (streaming)

**Schema Definition:**
```flatbuffers
namespace k1.tool_runner;

table ToolCallProgress {
  call_id: string (required);
  progress_percent: float32 = 0.0;  // 0.0-100.0
  status_message: string;
  partial_results: string;  // JSON

  // Timestamps
  reported_at_ms: uint64 = 0;
}

root_type ToolCallProgress;
file_identifier "TCPG";
```

**Usage:** Long-running tools, progress UI, cancellation
**Performance:** ~512B size, 0.28ms serialize, 0.035ms deserialize ✅

---

### 38. ToolCallCancellation (TCCN)

**Purpose:** Tool call cancellation

**Schema Definition:**
```flatbuffers
namespace k1.tool_runner;

enum CancellationReason : uint8 {
  USER_CANCEL = 0,
  TIMEOUT = 1,
  BARGE_IN = 2,
  SYSTEM_SHUTDOWN = 3
}

table ToolCallCancellation {
  call_id: string (required);
  reason: CancellationReason (required);

  // Timestamps
  cancelled_at_ms: uint64 = 0;
}

root_type ToolCallCancellation;
file_identifier "TCCN";
```

**Usage:** Graceful cancellation, resource cleanup
**Performance:** ~128B size, 0.08ms serialize, 0.012ms deserialize ✅

---

## Model Hub Schemas (4 Schemas)

### 39. ModelRequest (MREQ)

**Purpose:** LLM inference request

**Schema Definition:**
```flatbuffers
namespace k1.model_hub;

table ModelParameters {
  temperature: float32 = 0.7;
  top_p: float32 = 0.9;
  max_tokens: uint32 = 2048;
  stop_sequences: [string];
}

table ModelRequest {
  request_id: string (required);
  model_id: string (required);
  prompt: string (required);

  // Parameters
  parameters: ModelParameters;

  // Streaming
  stream: bool = false;

  // Timestamps
  requested_at_ms: uint64 = 0;
}

root_type ModelRequest;
file_identifier "MREQ";
```

**Usage:** LLM inference, parameter tuning, streaming
**Performance:** 1-8KB size, 0.65ms serialize, 0.088ms deserialize ✅

---

### 40. ModelResponse (MRSP)

**Purpose:** LLM inference response

**Schema Definition:**
```flatbuffers
namespace k1.model_hub;

table TokenUsage {
  prompt_tokens: uint32 = 0;
  completion_tokens: uint32 = 0;
  total_tokens: uint32 = 0;
}

table ModelResponse {
  request_id: string (required);
  completion_text: string (required);
  finish_reason: string;  // "stop", "length", "content_filter"

  // Token accounting
  usage: TokenUsage;

  // Performance metrics
  latency_ms: uint32 = 0;
  ttft_ms: uint32 = 0;  // Time to first token

  // Timestamps
  completed_at_ms: uint64 = 0;
}

root_type ModelResponse;
file_identifier "MRSP";
```

**Usage:** LLM results, token accounting, performance tracking
**Performance:** 1-32KB size, 1.8ms serialize, 0.25ms deserialize ✅

---

### 41. ModelStreamChunk (MSCH)

**Purpose:** LLM streaming chunk

**Schema Definition:**
```flatbuffers
namespace k1.model_hub;

table ModelStreamChunk {
  request_id: string (required);
  chunk_id: uint32 = 0;
  delta_text: string (required);
  finish_reason: string;

  // Timestamps
  generated_at_ms: uint64 = 0;
}

root_type ModelStreamChunk;
file_identifier "MSCH";
```

**Usage:** Streaming inference, low-latency TTFT
**Performance:** ~512B size, 0.28ms serialize, 0.035ms deserialize ✅

---

### 42. ModelCacheEntry (MCHE)

**Purpose:** KV cache entry

**Schema Definition:**
```flatbuffers
namespace k1.model_hub;

table ModelCacheEntry {
  cache_key: string (required);
  cached_tokens: [uint32];
  attention_mask: [uint8];

  // Eviction metadata
  access_count: uint32 = 0;
  last_accessed_ms: uint64 = 0;
  eviction_priority: float32 = 0.0;

  // Memory tracking
  size_bytes: uint32 = 0;
}

root_type ModelCacheEntry;
file_identifier "MCHE";
```

**Usage:** KV cache management, thermal placement, eviction
**Performance:** 4-64KB size, 2.5ms serialize, 0.35ms deserialize ✅

---

## MCP Gateway Schemas (4 Schemas)

### 43. MCPMessage (MCPM)

**Purpose:** MCP protocol message

**Schema Definition:**
```flatbuffers
namespace k1.mcp_gateway;

enum MCPMessageType : uint8 {
  REQUEST = 0,
  RESPONSE = 1,
  NOTIFICATION = 2,
  ERROR = 3
}

table MCPMessage {
  message_id: string (required);
  message_type: MCPMessageType (required);
  payload: string (required);  // JSON-RPC 2.0

  // Timestamps
  timestamp_ms: uint64 = 0;
}

root_type MCPMessage;
file_identifier "MCPM";
```

**Usage:** MCP protocol, tool discovery, event streaming
**Performance:** 512B-16KB size, 0.85ms serialize, 0.12ms deserialize ✅

---

### 44. MCPToolDiscovery (MCTD)

**Purpose:** MCP tool discovery

**Schema Definition:**
```flatbuffers
namespace k1.mcp_gateway;

table MCPToolDiscovery {
  server_id: string (required);
  available_tools: [string];  // Tool names
  capabilities: [string];
  version: string;

  // Timestamps
  discovered_at_ms: uint64 = 0;
}

root_type MCPToolDiscovery;
file_identifier "MCTD";
```

**Usage:** Dynamic tool registry, server discovery
**Performance:** 2-16KB size, 1.2ms serialize, 0.16ms deserialize ✅

---

### 45. MCPResourceRequest (MCRR)

**Purpose:** MCP resource request

**Schema Definition:**
```flatbuffers
namespace k1.mcp_gateway;

table MCPResourceRequest {
  request_id: string (required);
  resource_uri: string (required);
  method: string (required);  // GET, POST, PUT, DELETE
  headers: [k1.agent_fabric.KeyValue];
  body: string;

  // Timestamps
  requested_at_ms: uint64 = 0;
}

root_type MCPResourceRequest;
file_identifier "MCRR";
```

**Usage:** MCP resources, file access, external data
**Performance:** 512B-16KB size, 0.85ms serialize, 0.12ms deserialize ✅

---

### 46. MCPResourceResponse (MCRS)

**Purpose:** MCP resource response

**Schema Definition:**
```flatbuffers
namespace k1.mcp_gateway;

table MCPResourceResponse {
  request_id: string (required);
  status_code: uint16 = 200;
  headers: [k1.agent_fabric.KeyValue];
  body: string;

  // Performance metrics
  latency_ms: uint32 = 0;

  // Timestamps
  completed_at_ms: uint64 = 0;
}

root_type MCPResourceResponse;
file_identifier "MCRS";
```

**Usage:** Resource results, error handling
**Performance:** 512B-64KB size, 3.2ms serialize, 0.45ms deserialize ✅

---

## Streaming Engine Schemas (3 Schemas)

### 47. StreamConfig (STCF)

**Purpose:** Stream configuration

**Schema Definition:**
```flatbuffers
namespace k1.streaming_engine;

enum StreamType : uint8 {
  AUDIO = 0,
  VIDEO = 1,
  TEXT = 2,
  MULTIMODAL = 3
}

table StreamConfig {
  stream_id: string (required);
  stream_type: StreamType (required);
  codec: string;
  bitrate: uint32 = 0;
  buffer_size_ms: uint32 = 100;

  // Timestamps
  configured_at_ms: uint64 = 0;
}

root_type StreamConfig;
file_identifier "STCF";
```

**Usage:** Stream setup, codec negotiation, buffer management
**Performance:** ~256B size, 0.18ms serialize, 0.022ms deserialize ✅

---

### 48. StreamChunk (STCH)

**Purpose:** Stream data chunk

**Schema Definition:**
```flatbuffers
namespace k1.streaming_engine;

table StreamChunk {
  stream_id: string (required);
  chunk_id: uint32 = 0;
  data: [uint8] (required);

  // Timestamps
  timestamp_ms: uint64 = 0;

  // Flags
  is_keyframe: bool = false;
  is_end_of_stream: bool = false;
}

root_type StreamChunk;
file_identifier "STCH";
```

**Usage:** Streaming data, buffer management, synchronization
**Performance:** 4-64KB size, 3.5ms serialize, 0.48ms deserialize ✅

---

### 49. StreamControl (STCT)

**Purpose:** Stream control message

**Schema Definition:**
```flatbuffers
namespace k1.streaming_engine;

enum StreamControlType : uint8 {
  START = 0,
  STOP = 1,
  PAUSE = 2,
  RESUME = 3,
  SEEK = 4
}

table StreamControl {
  stream_id: string (required);
  control_type: StreamControlType (required);
  parameters: [k1.agent_fabric.KeyValue];

  // Timestamps
  sent_at_ms: uint64 = 0;
}

root_type StreamControl;
file_identifier "STCT";
```

**Usage:** Stream lifecycle, playback control
**Performance:** ~128B size, 0.08ms serialize, 0.012ms deserialize ✅

---

## Performance Budgets (P95 Targets)

| Schema | Size | Serialize | Deserialize | Status |
|--------|------|-----------|-------------|--------|
| ToolDefinition (TDEF) | 1-4KB | 0.45ms | 0.062ms | ✅ |
| ToolCallRequest (TCLR) | 512B-4KB | 0.38ms | 0.052ms | ✅ |
| ToolCallResponse (TCRS) | 512B-16KB | 0.85ms | 0.12ms | ✅ |
| ToolCallProgress (TCPG) | ~512B | 0.28ms | 0.035ms | ✅ |
| ToolCallCancellation (TCCN) | ~128B | 0.08ms | 0.012ms | ✅ |
| ModelRequest (MREQ) | 1-8KB | 0.65ms | 0.088ms | ✅ |
| ModelResponse (MRSP) | 1-32KB | 1.8ms | 0.25ms | ✅ |
| ModelStreamChunk (MSCH) | ~512B | 0.28ms | 0.035ms | ✅ |
| ModelCacheEntry (MCHE) | 4-64KB | 2.5ms | 0.35ms | ✅ |
| MCPMessage (MCPM) | 512B-16KB | 0.85ms | 0.12ms | ✅ |
| MCPToolDiscovery (MCTD) | 2-16KB | 1.2ms | 0.16ms | ✅ |
| MCPResourceRequest (MCRR) | 512B-16KB | 0.85ms | 0.12ms | ✅ |
| MCPResourceResponse (MCRS) | 512B-64KB | 3.2ms | 0.45ms | ✅ |
| StreamConfig (STCF) | ~256B | 0.18ms | 0.022ms | ✅ |
| StreamChunk (STCH) | 4-64KB | 3.5ms | 0.48ms | ✅ |
| StreamControl (STCT) | ~128B | 0.08ms | 0.012ms | ✅ |

**Layer 3 Total:** <3s P95 for tool calls, <150ms TTFT for LLM, <100ms for stream chunks ✅

---

**Last Updated:** 2025-10-12
**Status:** Accepted (Layer 3 Execution & Tools Schemas - 16/76 schemas documented)