# Stream Switch - Unified Multi-Modal Input Bus

**Module:** `k1/l1_input/streams/stream_switch/` (Module #53)
**Architecture:** ADR-0004f, ADR-0004 Amendment #2
**Capability:** #1 (Cross-Modal Continuity)
**Status:** 🔴 NEEDS_IMPLEMENTATION (P0 - MVP CRITICAL)

---

## Purpose

Unified multi-modal input bus enabling seamless transitions between voice, text, images, touch, and GPS inputs while preserving conversation context.

## Problem

Users expect seamless modality switches:

```
User (voice): "Show me photos of Seattle"
[System displays photos]
User (text): "Book flight there"      ← LLM needs "there" = Seattle from voice context
```

Without Stream Switch → "Where do you want to fly?" ❌
With Stream Switch → "Booking flight to Seattle" ✅

## Components

### 1. Multi-Modal Input Bus (`bus.py`)

**Responsibilities:**
- Accept inputs from 5 stream operators (audio, video, text, touch, GPS)
- Tag each input with modality metadata
- Maintain input sequence order (timestamp-based)
- Zero-copy ring buffer (1000 inputs max)
- <1ms input acceptance latency

**Schema:**
```python
@dataclass
class UnifiedInput:
    input_id: str
    session_id: str
    timestamp_ms: int
    modality: InputModality  # VOICE | TEXT | IMAGE | TOUCH | LOCATION
    content: Any
    context_refs: List[str]  # Cross-modal links
    cognitive_trace_id: str
```

### 2. Modality Transition Manager (`transition_manager.py`)

**Responsibilities:**
- Track active modality per session
- Detect transitions (voice → text, text → voice)
- Device state sync (pause audio, resume playback)
- Publish `ModalityTransition` events
- <5ms P95 transition latency

**Transitions:**
- VOICE_TO_TEXT: User stops speaking, starts typing
- TEXT_TO_VOICE: User stops typing, starts speaking
- SCREEN_TO_VOICE: User stops touching, starts speaking
- VOICE_TO_SCREEN: User stops speaking, touches screen

### 3. Cross-Modal Context Preserver (`context_preserver.py`)

**Responsibilities:**
- Entity tracking (extract "Seattle" from voice)
- Reference resolution ("there" → "Seattle")
- Conversation continuity across modalities
- Context injection to SessionState beliefs
- spaCy NER <5ms

**Example:**
```python
# Turn 1 (voice): "Show me photos of Seattle"
entities = {"Seattle": LOCATION}

# Turn 2 (text): "Book flight there"
resolved = {"there": "Seattle"}  # Coreference resolution
```

## Integration

**Upstream (Layer 1 Inputs):**
- `k1/l1_input/streams/operators/audio_operator.py`
- `k1/l1_input/streams/operators/video_operator.py`
- `k1/l1_input/streams/operators/text_operator.py`
- `k1/l1_input/streams/operators/touch_operator.py`
- `k1/l1_input/streams/operators/gps_operator.py`

**Downstream (Layer 2 Orchestration):**
- `k1/l2_orchestration/intent_router/` ← receives `UserInput` events
- `SessionState` ← stores cross-modal context

**Cross-Layer:**
- Event Bus (L5) ← publishes `ModalityTransition` events
- Observability (L5) ← metrics + tracing

## Performance Budgets

| Component | Budget | Measurement |
|-----------|--------|-------------|
| Input acceptance | <1ms | `bus.accept_input()` |
| Transition detection | <1ms | `transition_manager.detect()` |
| Device sync | <5ms | Async fire-and-forget |
| Entity extraction | <5ms | spaCy NER |
| **Total P95** | **<5ms** | End-to-end transition |

## Observability

**Metrics:**
- `stream_switch_transitions_total{from_modality, to_modality}`
- `stream_switch_transition_latency_ms`
- `stream_switch_entity_resolution_success_rate`
- `stream_switch_active_modality{session_id, modality}`

**Tracing:**
- Span: `stream_switch.transition`
- Attributes: `modality`, `session_id`, `input_id`

## Research Foundation

- **Multi-Modal Deep Learning:** Baltrusaitis et al. (2018)
- **Context-Aware Computing:** Dey (2001)
- **Google Assistant Multi-Modal:** 2019 architecture paper
- **Event-Driven Architecture:** Brewer (2000)

## Related ADRs

- **ADR-0004f:** Stream Switch Multi-Modal Bus (detailed architecture)
- **ADR-0004:** 56-Module Architecture (Amendment #2)
- **ADR-0001f:** SessionState Management (cross-modal context storage)
- **ADR-0004a:** Event Bus Communication (`ModalityTransition` events)

## Implementation Plan

**Phase 1: Foundation (Week 1)**
- Create module structure + README ✅ (this file)
- Implement `MultiModalInputBus` (zero-copy ring buffer)
- Unit tests for input acceptance

**Phase 2: Transition Detection (Week 1-2)**
- Implement `ModalityTransitionManager` (state machine)
- Device state sync (async)
- Event Bus integration

**Phase 3: Context Preservation (Week 2)**
- Implement `CrossModalContextPreserver` (entity tracking)
- spaCy integration (<5ms)
- SessionState integration

**Phase 4: Integration & Performance (Week 2-3)**
- Connect 5 stream operators
- End-to-end integration tests
- Performance validation (<5ms P95)

## Status

🔴 **NEEDS_IMPLEMENTATION** (P0 - MVP CRITICAL)

**Timeline:** 2-3 weeks implementation + 1 week testing + 1 week canary rollout

**Blockers:** None (foundational capability)

**Next Steps:**
1. Implement `bus.py` (Multi-Modal Input Bus)
2. Implement `transition_manager.py` (Modality Transition Manager)
3. Implement `context_preserver.py` (Cross-Modal Context Preserver)
4. Write WARD integration tests
5. Performance validation (<5ms P95)
