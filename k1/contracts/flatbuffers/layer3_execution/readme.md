# FlatBuffers Contracts - Layer 3 (Execution & Tools)

**Source ADRs:** ADR-0001b, ADR-0009

## Overview

This directory contains FlatBuffers schema contracts for Layer 3 (Execution & Tools) components: Tool Runner, Model Hub, MCP Gateway, and Streaming Engine.

## Layer 3 Components

Layer 3 handles execution of tools, LLM inference, and streaming responses.

## Contracts Included

### 1. Tool Runner Schemas
- `ToolInvocation.fbs` - Tool invocation request
- `ToolResult.fbs` - Tool execution result
- `ToolError.fbs` - Tool error details

### 2. Model Hub Schemas
- `InferenceRequest.fbs` - LLM inference request
- `InferenceResponse.fbs` - LLM inference response
- `StreamingChunk.fbs` - Streaming token chunk
- `KVCache.fbs` - KV cache entry

### 3. MCP Gateway Schemas
- `MCPRequest.fbs` - MCP protocol request
- `MCPResponse.fbs` - MCP protocol response
- `MCPToolSchema.fbs` - MCP tool schema

### 4. Streaming Engine Schemas
- `StreamStart.fbs` - Stream initialization
- `StreamChunk.fbs` - Stream data chunk
- `StreamEnd.fbs` - Stream completion

## Schema Example: ToolInvocation

```flatbuffers
// ToolInvocation.fbs
namespace k1.execution;

table ToolInvocation {
  tool_id: string (required);
  parameters: [ubyte];  // JSON-encoded parameters
  timeout_ms: uint32;
  idempotency_key: string;
  trace_id: string (required);
  timestamp: int64;
  version: uint16 = 1;
}

table ToolResult {
  tool_id: string (required);
  success: bool;
  result: [ubyte];  // JSON-encoded result
  error: ToolError;
  duration_ms: uint32;
  trace_id: string (required);
  timestamp: int64;
}

table ToolError {
  error_type: string;  // TIMEOUT, INVALID_PARAMETERS, etc.
  message: string;
  retryable: bool;
}

root_type ToolInvocation;
```

## Streaming Schema

```flatbuffers
// StreamingChunk.fbs
namespace k1.execution;

enum ChunkType: byte {
  TOKEN = 0,
  TOOL_CALL = 1,
  METADATA = 2,
  ERROR = 3,
  DONE = 4
}

table StreamingChunk {
  chunk_type: ChunkType;
  data: [ubyte];
  sequence: uint32;
  trace_id: string;
  timestamp: int64;
}

root_type StreamingChunk;
```

## Performance Characteristics

```yaml
performance:
  tool_invocation_serialization_us: 100
  inference_request_serialization_us: 200
  streaming_chunk_serialization_us: 50
  zero_copy_streaming: true
```

## Related Contracts

- Tools: `../../tools/`
- Performance: `../../performance/kv_cache.yaml`

---

**Last Updated:** 2025-10-13
