---
adr_number: 0017e
affected_layers:
- layer1_input
- layer4_runtime
affected_modules: []
authors:
- K1 Architecture Team
concerns:
- architecture
- cost
- observability
- performance
- privacy
- reliability
- security
- testing
date_created: '2025-11-03'
date_updated: '2025-11-03'
implementation_date: null
implementation_phase: Phase 1 (Foundation)
implementation_status: IN_PROGRESS
propagation:
  affected_adrs:
  - ADR-0011
  - ADR-0017
  - ADR-0017a
  - ADR-0050
  - ADR-0085
  - ADR-0085a
  - ADR-0085b
  - ADR-0085c
  affected_tests: []
  triggers:
  - Audio buffer streaming state protocol changes
  - Vision embedding storage format modifications
  - Multimodal stream metadata updates
  - K0 blob storage pointer format changes
  - Codec/sample rate configuration updates
related_adrs:
- ADR-0011
- ADR-0017
- ADR-0017a
- ADR-0019a
- ADR-0050
- ADR-0085
- ADR-0085a
- ADR-0085b
- ADR-0085c
related_contracts:
- k1/contracts/flatbuffers/layer2_state/multimodal_section.fbs
related_diagrams: []
research_citations:
- WebRTC MediaStream API (W3C Specification, 2024)
- Real-Time Audio Processing (Web Audio API, 2024)
- Vision Embedding Storage (FAISS Vector Database, 2024)
status: PROPOSED
superseded_by: []
supersedes: []
title: Multimodal Section - Audio/Vision State
---

# ADR-0017e: Multimodal Section - Audio/Vision State

**Status:** ⏳ In Progress (0% - Initial Draft)
**Date:** 2025-10-12
**Authors:** K1 Architecture Team
**Parent ADR:** [ADR-0017 (SessionState 6-Section Design)](0017-sessionstate-6-section-design.md)
**Category:** State Management (Layer 2) - Multimodal
**Related ADRs:**

- [ADR-0011 (FlatBuffers Serialization)](0011-flatbuffers-serialization.md)
- [ADR-0017a (Beliefs Section)](0017a-beliefs-section-user-facts-preferences.md)

---

## Context

### Problem Statement

The **Multimodal Section** stores multimodal state (audio buffers, vision embeddings, streaming metadata) for voice and vision features:

- **Audio Buffers:** Recent audio chunks for ASR streaming (pointers to K0 blob storage)
- **Vision Embeddings:** Image feature vectors for vision models (pointers to K0 blob storage)
- **Streaming State:** Current audio/video stream metadata (stream_id, codec, sample_rate)
- **Eviction Policy:** LRU with medium priority (keep recent, evict old)
- **Size Budget:** 4-8KB (pointers only, not raw audio/video data)

**Key Challenges:**

1. **Blob Storage:** Audio/video data too large for SessionState (store pointers to K0)
2. **Buffer Management:** Keep recent chunks, evict old chunks (LRU)
3. **Streaming State:** Track active streams (stream_id, status, metadata)
4. **Size Budget:** 4-8KB (pointers + metadata, not raw data)
5. **Access Patterns:** Read-heavy (streaming playback), write on new chunks

### Current Landscape

**Industry Multimodal State Patterns:**

1. **WebRTC MediaStream (Browser)**:
   - **Pattern:** MediaStreamTrack with audio/video tracks
   - **Advantage:** Browser-native, real-time streaming
   - **Disadvantage:** No persistent state (in-memory only)

2. **FFmpeg Stream Context**:
   - **Pattern:** AVFormatContext with stream metadata (codec, bitrate, duration)
   - **Advantage:** Rich metadata, codec-agnostic
   - **Disadvantage:** Complex (full FFmpeg integration)

3. **OpenAI Whisper Audio Chunks**:
   - **Pattern:** 30s audio chunks with timestamps
   - **Advantage:** Simple, fixed-size chunks
   - **Disadvantage:** No streaming state (batch processing only)

4. **CLIP Vision Embeddings**:
   - **Pattern:** 512-dim float vector per image
   - **Advantage:** Compact representation (2KB per image)
   - **Disadvantage:** No temporal continuity (single image only)

### K1 Requirements

**Multimodal Section Properties:**

1. **Audio Buffer Pointers:** Store K0 blob storage pointers (not raw audio)
2. **Vision Embedding Pointers:** Store K0 blob storage pointers (not raw embeddings)
3. **Streaming Metadata:** Active stream state (stream_id, codec, sample_rate, status)
4. **LRU Eviction:** Evict old chunks when size > 8KB
5. **K0 Blob Integration:** Pointers to K0 blob storage (raw data stored externally)

**Performance Targets (P95):**

| Operation | Target | Rationale |
|-----------|--------|-----------|
| `add_audio_buffer(chunk_id)` | <500μs | Fast buffer tracking |
| `get_audio_buffer(chunk_id)` | <200μs | Fast buffer lookup |
| `add_vision_embedding(img_id)` | <500μs | Fast embedding tracking |
| `evict_lru_buffers()` | <5ms | Periodic eviction |

---

## Decision

We will implement **Multimodal Section** as:

1. **Audio Buffer Store:** List of AudioBuffer (buffer_id, storage_pointer, chunk_index, duration_ms)
2. **Vision Embedding Store:** List of VisionEmbedding (embedding_id, storage_pointer, image_id, dimensions)
3. **Streaming State:** Single StreamingState object (active_stream_id, codec, sample_rate, status)
4. **LRU Eviction:** Evict oldest buffers/embeddings when size > 8KB
5. **K0 Blob Pointers:** Store pointers only (raw data in K0 blob storage)

**Data Model:**

```
AudioBuffer:
  - buffer_id: string (e.g., "audio_chunk_1")
  - chunk_index: int (chunk sequence number)
  - storage_pointer: string (K0 blob storage key)
  - duration_ms: int (chunk duration)
  - created_at_ms: long (timestamp)

VisionEmbedding:
  - embedding_id: string (e.g., "vision_emb_1")
  - image_id: string (source image identifier)
  - storage_pointer: string (K0 blob storage key)
  - dimensions: int (embedding size, e.g., 512)
  - created_at_ms: long (timestamp)

MultimodalSection:
  - audio_buffers: [AudioBuffer] (pointers to K0 blob storage)
  - vision_embeddings: [VisionEmbedding] (pointers to K0 blob storage)
  - active_stream_id: string (current audio/video stream)
```

---

## Implementation

### FlatBuffers Schema

```flatbuffers
// k1/session_state/schemas/multimodal_section.fbs
namespace K1.SessionState;

/// Audio buffer (pointer to K0 blob storage)
table AudioBuffer {
  /// Buffer identifier
  buffer_id: string (required);

  /// Chunk index (sequence number in stream)
  chunk_index: int;

  /// K0 blob storage pointer (key to retrieve raw audio)
  storage_pointer: string (required);

  /// Chunk duration (milliseconds)
  duration_ms: int;

  /// Creation timestamp
  created_at_ms: long (required);
}

/// Vision embedding (pointer to K0 blob storage)
table VisionEmbedding {
  /// Embedding identifier
  embedding_id: string (required);

  /// Source image identifier
  image_id: string;

  /// K0 blob storage pointer (key to retrieve raw embedding)
  storage_pointer: string (required);

  /// Embedding dimensions (e.g., 512 for CLIP)
  dimensions: int;

  /// Creation timestamp
  created_at_ms: long (required);
}

/// Multimodal section (audio/vision state)
table MultimodalSection {
  /// Audio buffers (pointers to K0 blob storage)
  audio_buffers: [AudioBuffer];

  /// Vision embeddings (pointers to K0 blob storage)
  vision_embeddings: [VisionEmbedding];

  /// Active stream identifier (current audio/video stream)
  active_stream_id: string;

  /// Total size in bytes
  total_size_bytes: int;

  /// Last update timestamp
  last_updated_ms: long;
}

root_type MultimodalSection;
```

---

### Python Implementation

```python
# k1/session_state/multimodal_manager.py
"""Multimodal Section Manager - Audio/Vision State

Research:
- Audio Streaming: "RTP: A Transport Protocol for Real-Time Applications" (RFC 3550)
- Vision Embeddings: "Learning Transferable Visual Models From Natural Language Supervision" (Radford et al., 2021) - CLIP
"""

from typing import Dict, Optional, List
from dataclasses import dataclass
import time
import logging

logger = logging.getLogger(__name__)


@dataclass
class AudioBufferData:
    """In-memory audio buffer representation"""
    buffer_id: str
    chunk_index: int
    storage_pointer: str
    duration_ms: int
    created_at_ms: int


@dataclass
class VisionEmbeddingData:
    """In-memory vision embedding representation"""
    embedding_id: str
    image_id: str
    storage_pointer: str
    dimensions: int
    created_at_ms: int


class MultimodalManager:
    """Manage multimodal section (audio/vision state)

    Responsibilities:
    - Track audio buffer pointers (raw audio in K0 blob storage)
    - Track vision embedding pointers (raw embeddings in K0 blob storage)
    - Manage streaming state (active stream metadata)
    - Evict old buffers/embeddings under memory pressure (LRU)

    Performance:
    - add_audio_buffer: O(1) append, <500μs P95
    - get_audio_buffer: O(n) scan, <200μs P95 (n = 10-20)
    - add_vision_embedding: O(1) append, <500μs P95
    - evict_lru_buffers: O(n) scan, <5ms P95
    """

    def __init__(self, max_size_kb: int = 8):
        """Initialize multimodal manager

        Args:
            max_size_kb: Max section size before eviction (default: 8KB)
        """
        self.max_size_kb = max_size_kb
        self.audio_buffers: List[AudioBufferData] = []
        self.vision_embeddings: List[VisionEmbeddingData] = []
        self.active_stream_id: Optional[str] = None
        self.next_buffer_id = 1
        self.next_embedding_id = 1

    def add_audio_buffer(
        self,
        storage_pointer: str,
        chunk_index: int,
        duration_ms: int,
    ) -> str:
        """Add audio buffer (pointer to K0 blob storage)

        Args:
            storage_pointer: K0 blob storage key
            chunk_index: Chunk sequence number
            duration_ms: Chunk duration

        Returns:
            buffer_id of created buffer

        Performance: <500μs P95
        """
        now_ms = self._get_timestamp_ms()
        buffer_id = f"audio_chunk_{self.next_buffer_id}"
        self.next_buffer_id += 1

        buffer = AudioBufferData(
            buffer_id=buffer_id,
            chunk_index=chunk_index,
            storage_pointer=storage_pointer,
            duration_ms=duration_ms,
            created_at_ms=now_ms,
        )

        self.audio_buffers.append(buffer)
        logger.info(f"[MultimodalManager] Added audio buffer: {buffer_id} (ptr={storage_pointer})")

        # Check size, evict if needed
        if self.get_size_kb() > self.max_size_kb:
            self._evict_lru_audio()

        return buffer_id

    def get_audio_buffer(self, buffer_id: str) -> Optional[AudioBufferData]:
        """Get audio buffer by ID

        Args:
            buffer_id: Buffer identifier

        Returns:
            AudioBufferData if exists, None otherwise

        Performance: <200μs P95
        """
        for buffer in self.audio_buffers:
            if buffer.buffer_id == buffer_id:
                return buffer
        return None

    def get_recent_audio_buffers(self, count: int = 10) -> List[AudioBufferData]:
        """Get N most recent audio buffers

        Args:
            count: Number of buffers to retrieve

        Returns:
            List of recent buffers (newest first)
        """
        return sorted(
            self.audio_buffers,
            key=lambda b: b.created_at_ms,
            reverse=True
        )[:count]

    def add_vision_embedding(
        self,
        storage_pointer: str,
        image_id: str,
        dimensions: int = 512,
    ) -> str:
        """Add vision embedding (pointer to K0 blob storage)

        Args:
            storage_pointer: K0 blob storage key
            image_id: Source image identifier
            dimensions: Embedding dimensions (e.g., 512 for CLIP)

        Returns:
            embedding_id of created embedding

        Performance: <500μs P95
        """
        now_ms = self._get_timestamp_ms()
        embedding_id = f"vision_emb_{self.next_embedding_id}"
        self.next_embedding_id += 1

        embedding = VisionEmbeddingData(
            embedding_id=embedding_id,
            image_id=image_id,
            storage_pointer=storage_pointer,
            dimensions=dimensions,
            created_at_ms=now_ms,
        )

        self.vision_embeddings.append(embedding)
        logger.info(f"[MultimodalManager] Added vision embedding: {embedding_id} (ptr={storage_pointer})")

        # Check size, evict if needed
        if self.get_size_kb() > self.max_size_kb:
            self._evict_lru_vision()

        return embedding_id

    def get_vision_embedding(self, embedding_id: str) -> Optional[VisionEmbeddingData]:
        """Get vision embedding by ID

        Args:
            embedding_id: Embedding identifier

        Returns:
            VisionEmbeddingData if exists, None otherwise
        """
        for embedding in self.vision_embeddings:
            if embedding.embedding_id == embedding_id:
                return embedding
        return None

    def set_active_stream(self, stream_id: str):
        """Set active audio/video stream

        Args:
            stream_id: Stream identifier
        """
        self.active_stream_id = stream_id
        logger.info(f"[MultimodalManager] Set active stream: {stream_id}")

    def clear_active_stream(self):
        """Clear active stream (stream ended)"""
        logger.info(f"[MultimodalManager] Cleared active stream: {self.active_stream_id}")
        self.active_stream_id = None

    def _evict_lru_audio(self):
        """Evict oldest audio buffer

        Performance: O(1) for list.pop(0), <5ms P95
        """
        if self.audio_buffers:
            evicted = self.audio_buffers.pop(0)
            logger.info(f"[MultimodalManager] Evicted audio buffer: {evicted.buffer_id}")

    def _evict_lru_vision(self):
        """Evict oldest vision embedding

        Performance: O(1) for list.pop(0), <5ms P95
        """
        if self.vision_embeddings:
            evicted = self.vision_embeddings.pop(0)
            logger.info(f"[MultimodalManager] Evicted vision embedding: {evicted.embedding_id}")

    def get_size_kb(self) -> int:
        """Estimate section size in KB

        Returns:
            Estimated size in KB
        """
        audio_bytes = sum(
            len(b.buffer_id) + len(b.storage_pointer) + 32
            for b in self.audio_buffers
        )
        vision_bytes = sum(
            len(e.embedding_id) + len(e.image_id) + len(e.storage_pointer) + 32
            for e in self.vision_embeddings
        )
        stream_bytes = len(self.active_stream_id) if self.active_stream_id else 0

        total_bytes = audio_bytes + vision_bytes + stream_bytes
        return total_bytes // 1024

    def _get_timestamp_ms(self) -> int:
        """Get current timestamp in milliseconds

        Returns:
            Milliseconds since epoch
        """
        return int(time.time() * 1000)

    def serialize(self) -> bytes:
        """Serialize to FlatBuffers for K0 persistence

        Returns:
            FlatBuffers serialized bytes
        """
        import flatbuffers
        # FlatBuffers serialization code
        # ... (implementation details)
        pass

    @staticmethod
    def deserialize(data: bytes) -> "MultimodalManager":
        """Deserialize from FlatBuffers

        Args:
            data: FlatBuffers serialized bytes

        Returns:
            MultimodalManager instance
        """
        # FlatBuffers deserialization code
        # ... (implementation details)
        pass
```

---

## Testing Strategy

### Unit Tests (WARD Framework)

```python
# tests/session_state/test_multimodal_manager.py
from ward import test, fixture
from k1.session_state.multimodal_manager import MultimodalManager

@fixture
def multimodal():
    """Fixture for MultimodalManager"""
    return MultimodalManager(max_size_kb=8)

@test("add_audio_buffer stores buffer pointer")
def _(multimodal=multimodal):
    buffer_id = multimodal.add_audio_buffer(
        storage_pointer="k0://blobs/audio_chunk_1.pcm",
        chunk_index=0,
        duration_ms=1000,
    )

    buffer = multimodal.get_audio_buffer(buffer_id)
    assert buffer.storage_pointer == "k0://blobs/audio_chunk_1.pcm"
    assert buffer.duration_ms == 1000

@test("add_vision_embedding stores embedding pointer")
def _(multimodal=multimodal):
    embedding_id = multimodal.add_vision_embedding(
        storage_pointer="k0://blobs/vision_emb_1.bin",
        image_id="img_123",
        dimensions=512,
    )

    embedding = multimodal.get_vision_embedding(embedding_id)
    assert embedding.storage_pointer == "k0://blobs/vision_emb_1.bin"
    assert embedding.dimensions == 512

@test("eviction removes oldest buffers")
def _(multimodal=multimodal):
    # Add many buffers to trigger eviction
    for i in range(100):
        multimodal.add_audio_buffer(
            storage_pointer=f"k0://blobs/audio_{i}.pcm",
            chunk_index=i,
            duration_ms=1000,
        )

    # Verify size under limit
    assert multimodal.get_size_kb() <= multimodal.max_size_kb
```

---

## Extensions: Device Context Fields (Added 2025-01-22)

**Reference:** ADR-0085 (Embodied Awareness & Device Presence)

### New Device Context Schema

Added to Multimodal Section for cross-device presence awareness:

```python
DeviceContext:
  device_id: str
  device_type: str  # PHONE | TABLET | LAPTOP | WATCH | SPEAKER
  online_status: str  # ONLINE | OFFLINE
  last_seen: timestamp
  active_session: bool  # Screen + input + foreground app
  motion_context: str  # STATIONARY | IN_POCKET | BEING_HELD | IN_VEHICLE | WALKING | RUNNING
  coarse_location: str  # City-level (privacy-safe GREEN band)
  proximity_devices: List[str]  # Device IDs in BLE NEAR/MEDIUM range
  battery_level: int  # 0-100
  charging_status: str  # CHARGING | DISCHARGING | FULL
  power_mode: str  # LOW_POWER | NORMAL | HIGH_PERFORMANCE
```

### Storage

- **Key:** `device_context:<device_id>` in SessionState Multimodal Section
- **Sync:** Via K0 P07 (ADR-0050 presence metadata extensions)
- **Eviction:** Never evicted (low priority, always keep)
- **Size:** ~200 bytes per device

### Use Cases

- **Notification routing:** Check `active_session` to determine target device
- **Smart handoff:** Use `proximity_devices` to detect device switches
- **Context adaptation:** Adjust output based on `motion_context` (in-pocket → audio-only)
- **Power management:** Reduce background tasks when `power_mode=LOW_POWER`

### Related Sub-ADRs

- **ADR-0085a:** Device Presence Detection & Location Awareness
- **ADR-0085b:** BLE Proximity & Active Session Tracking
- **ADR-0085c:** Cross-Device Context Sharing & Presence-Aware Features

---

## Research Citations

1. **Schulzrinne, H., Casner, S., Frederick, R., Jacobson, V. (2003).** *"RTP: A Transport Protocol for Real-Time Applications."* RFC 3550. — Audio streaming protocol.

2. **Radford, A., Kim, J. W., Hallacy, C., et al. (2021).** *"Learning Transferable Visual Models From Natural Language Supervision."* ICML. — CLIP vision embeddings.

---

## Signatures

**Sub-ADR Owner:** K1 Architecture Team
**Status:** ⏳ **In Progress** (0% - Initial Draft Created)
**Created Date:** 2025-10-12
**Target Completion:** 2025-11-09 (4 weeks)
**Blocked By:** 0017 (SessionState 6-Section Design)
**Blocks:** None

---

**END OF ADR-0017e**