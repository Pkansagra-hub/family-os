# FlatBuffers Contracts - Layer 4 (Ingress & Voice)

**Source ADRs:** ADR-0001b, ADR-0019, ADR-0020

## Overview

This directory contains FlatBuffers schema contracts for Layer 4 (Ingress & Voice) components: API Gateway, WebSocket, Voice Pipeline, and Barge-In.

## Layer 4 Components

Layer 4 handles external communication, voice processing, and user interruptions.

## Contracts Included

### 1. API Gateway Schemas
- `HTTPRequest.fbs` - HTTP request wrapper
- `HTTPResponse.fbs` - HTTP response wrapper
- `SessionCreate.fbs` - Session creation request
- `TurnRequest.fbs` - Turn submission

### 2. WebSocket Schemas
- `WSMessage.fbs` - WebSocket message wrapper
- `WSConnect.fbs` - Connection initialization
- `WSDisconnect.fbs` - Disconnect notification

### 3. Voice Pipeline Schemas
- `AudioFrame.fbs` - Audio frame data
- `VoiceCommand.fbs` - Recognized voice command
- `TTSRequest.fbs` - Text-to-speech request
- `TTSAudio.fbs` - Synthesized audio

### 4. Barge-In Schemas
- `BargeInEvent.fbs` - User interruption event
- `CancellationRequest.fbs` - Task cancellation

## Schema Example: TurnRequest

```flatbuffers
// TurnRequest.fbs
namespace k1.ingress;

enum Modality: byte {
  TEXT = 0,
  VOICE = 1,
  MULTIMODAL = 2
}

table TurnRequest {
  session_id: string (required);
  turn_id: string (required);
  modality: Modality;
  content: [ubyte];  // Text or audio data
  metadata: [ubyte];  // JSON metadata
  trace_id: string (required);
  timestamp: int64;
  version: uint16 = 1;
}

root_type TurnRequest;
```

## Voice Schema

```flatbuffers
// AudioFrame.fbs
namespace k1.ingress.voice;

enum AudioCodec: byte {
  PCM_16KHZ_16BIT = 0,
  OPUS = 1,
  AAC = 2
}

table AudioFrame {
  session_id: string (required);
  sequence: uint32;
  codec: AudioCodec;
  sample_rate: uint32;
  channels: ubyte;
  data: [ubyte];  // Raw audio bytes
  timestamp: int64;
  trace_id: string;
}

root_type AudioFrame;
```

## Barge-In Schema

```flatbuffers
// BargeInEvent.fbs
namespace k1.ingress;

enum BargeInReason: byte {
  USER_INTERRUPT = 0,
  TIMEOUT = 1,
  ERROR = 2
}

table BargeInEvent {
  session_id: string (required);
  turn_id: string;  // Turn being interrupted
  reason: BargeInReason;
  timestamp: int64;
  trace_id: string (required);
}

root_type BargeInEvent;
```

## Performance Characteristics

```yaml
performance:
  api_request_serialization_us: 100
  websocket_message_serialization_us: 50
  audio_frame_serialization_us: 20
  barge_in_event_serialization_us: 10

  latency_targets:
    barge_in_detection_ms: 120
    voice_frame_processing_ms: 50
```

## Related Contracts

- API Specs: `../../api_specs/`
- Protocols: `../../protocols/barge_in.yaml`

---

**Last Updated:** 2025-10-13
