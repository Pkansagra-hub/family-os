# ADR-0012d: Layer 4 Ingress & Voice Schemas (14 Schemas)

**Status:** Accepted
**Date:** 2025-10-12
**Parent ADR:** [ADR-0012: 76 FlatBuffers Schemas](0012-76-flatbuffers-schemas.md)
**Related ADRs:**
- [ADR-0011a: FlatBuffers Schema Design Principles](0011a-flatbuffers-schema-design-principles.md)
- [ADR-0011c: Serialization Performance & Zero-Copy](0011c-serialization-performance-zero-copy.md)

---

## Context

Layer 4 (Ingress & Voice) contains schemas for K1's user-facing interfaces: **API Gateway** (REST/WebSocket), **Voice Pipeline** (ASR/TTS), and **Barge-In** (interrupt detection). These 14 schemas form the data model for HTTP/WebSocket communication, voice processing, and real-time interaction.

**Layer 4 Modules:**
- `k1.api_gateway` (4 schemas)
- `k1.voice_pipeline` (4 schemas)
- `k1.barge_in` (3 schemas)
- `k1.websocket` (3 schemas)

**Total:** 14 schemas, ~32MB memory budget (voice buffers 16MB, WebSocket 16MB)

---

## Decision

### Schema Organization

**Namespace:** `k1.{module}` (Layer 4 modules)
**File Structure:** `k1/schemas/{module}/{entity}_{type}.fbs`
**File Identifiers:** 4-character codes (HREQ, HRSP, WSMG, AUDF, ASRR, TTSR, BGIN, etc.)
**Version Strategy:** v1.0-v1.2 (backward compatible, 3-release deprecation policy)

---

## API Gateway Schemas (4 Schemas)

### 50. HTTPRequest (HREQ)

**Purpose:** HTTP request (REST API)

**Schema Definition:**
```flatbuffers
namespace k1.api_gateway;

table HTTPRequest {
  request_id: string (required);
  method: string (required);  // GET, POST, PUT, DELETE
  path: string (required);
  headers: [k1.agent_fabric.KeyValue];
  query_params: [k1.agent_fabric.KeyValue];
  body: string;

  // Timestamps
  received_at_ms: uint64 = 0;
}

root_type HTTPRequest;
file_identifier "HREQ";
```

**Usage:** REST API, request parsing, routing
**Performance:** 512B-64KB size, 3.2ms serialize, 0.45ms deserialize ✅

---

### 51. HTTPResponse (HRSP)

**Purpose:** HTTP response (REST API)

**Schema Definition:**
```flatbuffers
namespace k1.api_gateway;

table HTTPResponse {
  request_id: string (required);
  status_code: uint16 = 200;
  headers: [k1.agent_fabric.KeyValue];
  body: string;

  // Performance metrics
  latency_ms: uint32 = 0;

  // Timestamps
  sent_at_ms: uint64 = 0;
}

root_type HTTPResponse;
file_identifier "HRSP";
```

**Usage:** REST API responses, error handling
**Performance:** 512B-64KB size, 3.2ms serialize, 0.45ms deserialize ✅

---

### 52. WebSocketMessage (WSMG)

**Purpose:** WebSocket message

**Schema Definition:**
```flatbuffers
namespace k1.api_gateway;

enum WSMessageType : uint8 {
  TEXT = 0,
  BINARY = 1,
  PING = 2,
  PONG = 3,
  CLOSE = 4
}

table WebSocketMessage {
  message_id: string (required);
  message_type: WSMessageType (required);
  payload: string (required);

  // Timestamps
  timestamp_ms: uint64 = 0;
}

root_type WebSocketMessage;
file_identifier "WSMG";
```

**Usage:** WebSocket protocol, bidirectional streaming
**Performance:** 512B-64KB size, 3.2ms serialize, 0.45ms deserialize ✅

---

### 53. SSEEvent (SSEV)

**Purpose:** Server-Sent Events event

**Schema Definition:**
```flatbuffers
namespace k1.api_gateway;

table SSEEvent {
  event_id: string (required);
  event_type: string (required);
  data: string (required);
  retry_ms: uint32 = 3000;

  // Timestamps
  sent_at_ms: uint64 = 0;
}

root_type SSEEvent;
file_identifier "SSEV";
```

**Usage:** SSE streaming, event push, reconnection
**Performance:** 512B-16KB size, 0.85ms serialize, 0.12ms deserialize ✅

---

## Voice Pipeline Schemas (4 Schemas)

### 54. AudioFrame (AUDF)

**Purpose:** Audio frame (16kHz, 16-bit PCM)

**Schema Definition:**
```flatbuffers
namespace k1.voice_pipeline;

table AudioFrame {
  frame_id: uint32 = 0;
  audio_data: [int16] (required);  // PCM samples
  timestamp_ms: uint64 = 0;

  // Audio metadata
  sample_rate: uint32 = 16000;
  channels: uint8 = 1;  // Mono
  bits_per_sample: uint8 = 16;
}

root_type AudioFrame;
file_identifier "AUDF";
```

**Usage:** Voice pipeline, VAD, ASR input
**Performance:** 2-16KB size, 0.85ms serialize, 0.12ms deserialize ✅

---

### 55. ASRResult (ASRR)

**Purpose:** ASR transcription result

**Schema Definition:**
```flatbuffers
namespace k1.voice_pipeline;

table ASRResult {
  result_id: string (required);
  transcript_text: string (required);
  confidence_score: float32 = 0.0;
  is_final: bool = false;

  // Performance metrics
  latency_ms: uint32 = 0;

  // Timestamps
  transcribed_at_ms: uint64 = 0;
}

root_type ASRResult;
file_identifier "ASRR";
```

**Usage:** Speech recognition, transcript streaming
**Performance:** ~512B size, 0.28ms serialize, 0.035ms deserialize ✅

---

### 56. TTSRequest (TTSR)

**Purpose:** TTS synthesis request

**Schema Definition:**
```flatbuffers
namespace k1.voice_pipeline;

table TTSParameters {
  speed: float32 = 1.0;
  pitch: float32 = 1.0;
  volume: float32 = 1.0;
}

table TTSRequest {
  request_id: string (required);
  text: string (required);
  voice_id: string;
  parameters: TTSParameters;

  // Timestamps
  requested_at_ms: uint64 = 0;
}

root_type TTSRequest;
file_identifier "TTSR";
```

**Usage:** Text-to-speech, voice synthesis
**Performance:** ~512B size, 0.28ms serialize, 0.035ms deserialize ✅

---

### 57. TTSAudioChunk (TTSA)

**Purpose:** TTS audio chunk (streaming)

**Schema Definition:**
```flatbuffers
namespace k1.voice_pipeline;

table TTSAudioChunk {
  request_id: string (required);
  chunk_id: uint32 = 0;
  audio_data: [int16] (required);

  // Timestamps
  timestamp_ms: uint64 = 0;
}

root_type TTSAudioChunk;
file_identifier "TTSA";
```

**Usage:** TTS streaming, low-latency playback
**Performance:** 2-16KB size, 0.85ms serialize, 0.12ms deserialize ✅

---

## Barge-In Schemas (3 Schemas)

### 58. BargeInEvent (BGIN)

**Purpose:** Barge-in detection event

**Schema Definition:**
```flatbuffers
namespace k1.barge_in;

table BargeInEvent {
  event_id: string (required);
  detection_time_ms: uint64 = 0;
  confidence_score: float32 = 0.0;
  audio_context: string;  // Brief audio snippet for context

  // Timestamps
  detected_at_ms: uint64 = 0;
}

root_type BargeInEvent;
file_identifier "BGIN";
```

**Usage:** Barge-in detection, VAD, interrupt handling
**Performance:** ~256B size, 0.18ms serialize, 0.022ms deserialize ✅

---

### 59. BargeInResponse (BGRS)

**Purpose:** Barge-in response (system action)

**Schema Definition:**
```flatbuffers
namespace k1.barge_in;

enum BargeInAction : uint8 {
  INTERRUPT_TTS = 0,
  CANCEL_TASKS = 1,
  CLEAR_QUEUE = 2
}

table BargeInResponse {
  event_id: string (required);
  action: BargeInAction (required);

  // Performance metrics
  latency_ms: uint32 = 0;

  // Timestamps
  responded_at_ms: uint64 = 0;
}

root_type BargeInResponse;
file_identifier "BGRS";
```

**Usage:** Barge-in handling, task cancellation, TTS stop
**Performance:** ~192B size, 0.12ms serialize, 0.015ms deserialize ✅

---

### 60. VADState (VADS)

**Purpose:** Voice Activity Detection state

**Schema Definition:**
```flatbuffers
namespace k1.barge_in;

enum VADStateType : uint8 {
  SILENCE = 0,
  SPEECH = 1,
  NOISE = 2
}

table VADState {
  state: VADStateType (required);
  confidence_score: float32 = 0.0;
  duration_ms: uint32 = 0;

  // Timestamps
  state_changed_at_ms: uint64 = 0;
}

root_type VADState;
file_identifier "VADS";
```

**Usage:** VAD state machine, barge-in trigger, ASR gating
**Performance:** ~128B size, 0.08ms serialize, 0.012ms deserialize ✅

---

## WebSocket Protocol Schemas (3 Schemas)

### 61. WSConnectionInit (WSIN)

**Purpose:** WebSocket connection init

**Schema Definition:**
```flatbuffers
namespace k1.websocket;

table WSConnectionInit {
  connection_id: string (required);
  client_version: string;
  supported_schemas: [string];
  auth_token: string;

  // Timestamps
  connected_at_ms: uint64 = 0;
}

root_type WSConnectionInit;
file_identifier "WSIN";
```

**Usage:** WebSocket handshake, version negotiation, auth
**Performance:** ~512B size, 0.28ms serialize, 0.035ms deserialize ✅

---

### 62. WSTurnMessage (WSTM)

**Purpose:** WebSocket turn message

**Schema Definition:**
```flatbuffers
namespace k1.websocket;

enum WSTurnMessageType : uint8 {
  USER_INPUT = 0,
  AGENT_OUTPUT = 1,
  SYSTEM_EVENT = 2
}

table WSTurnMessage {
  turn_id: string (required);
  message_type: WSTurnMessageType (required);
  payload: string (required);

  // Timestamps
  timestamp_ms: uint64 = 0;
}

root_type WSTurnMessage;
file_identifier "WSTM";
```

**Usage:** Turn-based conversation, message routing
**Performance:** 512B-64KB size, 3.2ms serialize, 0.45ms deserialize ✅

---

### 63. WSHeartbeat (WSHB)

**Purpose:** WebSocket heartbeat

**Schema Definition:**
```flatbuffers
namespace k1.websocket;

table WSHeartbeat {
  timestamp_ms: uint64 = 0;
  client_latency_ms: uint32 = 0;
  server_latency_ms: uint32 = 0;
}

root_type WSHeartbeat;
file_identifier "WSHB";
```

**Usage:** Connection keep-alive, latency monitoring
**Performance:** ~64B size, 0.05ms serialize, 0.008ms deserialize ✅

---

## Performance Budgets (P95 Targets)

| Schema | Size | Serialize | Deserialize | Status |
|--------|------|-----------|-------------|--------|
| HTTPRequest (HREQ) | 512B-64KB | 3.2ms | 0.45ms | ✅ |
| HTTPResponse (HRSP) | 512B-64KB | 3.2ms | 0.45ms | ✅ |
| WebSocketMessage (WSMG) | 512B-64KB | 3.2ms | 0.45ms | ✅ |
| SSEEvent (SSEV) | 512B-16KB | 0.85ms | 0.12ms | ✅ |
| AudioFrame (AUDF) | 2-16KB | 0.85ms | 0.12ms | ✅ |
| ASRResult (ASRR) | ~512B | 0.28ms | 0.035ms | ✅ |
| TTSRequest (TTSR) | ~512B | 0.28ms | 0.035ms | ✅ |
| TTSAudioChunk (TTSA) | 2-16KB | 0.85ms | 0.12ms | ✅ |
| BargeInEvent (BGIN) | ~256B | 0.18ms | 0.022ms | ✅ |
| BargeInResponse (BGRS) | ~192B | 0.12ms | 0.015ms | ✅ |
| VADState (VADS) | ~128B | 0.08ms | 0.012ms | ✅ |
| WSConnectionInit (WSIN) | ~512B | 0.28ms | 0.035ms | ✅ |
| WSTurnMessage (WSTM) | 512B-64KB | 3.2ms | 0.45ms | ✅ |
| WSHeartbeat (WSHB) | ~64B | 0.05ms | 0.008ms | ✅ |

**Layer 4 Total:** <50ms P95 for HTTP, <120ms barge-in latency, <50ms TTFT for TTS ✅

---

**Last Updated:** 2025-10-12
**Status:** Accepted (Layer 4 Ingress & Voice Schemas - 14/76 schemas documented)
