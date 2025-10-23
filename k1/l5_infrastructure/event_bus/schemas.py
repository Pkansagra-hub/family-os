"""
Event Bus Schema Definitions

Purpose: Event schemas for K1 internal event bus
Location: k1/l5_infrastructure/event_bus/schemas.py
Performance: N/A (static definitions)

Primary ADRs:
- ADR-0004a: Event Bus (event schema definitions)
- ADR-0030: Trace Sampling (cognitive_trace_id propagation)

Key Responsibilities:

1. Event Schemas:
   - IntentDetected: Intent classification results (tier, intent, confidence, entities)
   - UserInput: User input events (input_type, raw_text, cognitive_trace_id)
   - VoiceCommand: Voice command transcriptions (transcript, vad_confidence, language)
   - BargeIn: User interruption events (interrupt_time, cancellation_reason)

2. Cognitive Trace ID Propagation:
   - All events include cognitive_trace_id field (128-bit unique ID)
   - End-to-end tracing: L1→L2→L3→L4→L5→K0
   - W3C Trace Context format (traceparent header)

3. Schema Versioning:
   - SemVer versioning (1.0.0, 1.1.0, 2.0.0)
   - Backward compatibility: New fields are optional
   - Forward compatibility: Unknown fields ignored
   - 90-day deprecation window for breaking changes

Event Schemas:

1. IntentDetected:
   - tier: str (T1/T2/T3)
   - intent: str (intent name, e.g., "search_photos")
   - confidence: float (0.0-1.0)
   - entities: dict (extracted entities, e.g., {"query": "beach photos"})
   - cognitive_trace_id: str (128-bit hex)
   - timestamp: datetime (event creation time)

2. UserInput:
   - input_type: str (text/voice)
   - raw_text: str (user input text)
   - cognitive_trace_id: str (128-bit hex)
   - timestamp: datetime
   - metadata: dict (optional, e.g., voice_confidence, language)

3. VoiceCommand:
   - transcript: str (ASR transcription)
   - vad_confidence: float (0.0-1.0)
   - language: str (ISO 639-1, e.g., "en")
   - cognitive_trace_id: str (128-bit hex)
   - timestamp: datetime
   - partial: bool (partial vs final transcript)

4. BargeIn:
   - interrupt_time: datetime (when user interrupted)
   - cancellation_reason: str (user_interrupt, timeout, error)
   - cognitive_trace_id: str (128-bit hex)
   - interrupted_turn_id: str (turn that was interrupted)
   - timestamp: datetime

Implementation Notes:
- Use dataclasses for schema definitions (Python 3.7+)
- Use typing for type hints (strict type checking)
- Use datetime for timestamps (UTC timezone)
- Use UUID for cognitive_trace_id generation
- All events are immutable (frozen dataclasses)
- No serialization required (in-memory references only)

Example Usage:
    # Create IntentDetected event
    event = IntentDetected(
        tier="T1",
        intent="search_photos",
        confidence=0.95,
        entities={"query": "beach photos"},
        cognitive_trace_id="abc123",
        timestamp=datetime.utcnow()
    )

    # Create UserInput event
    event = UserInput(
        input_type="voice",
        raw_text="Show me beach photos",
        cognitive_trace_id="abc123",
        timestamp=datetime.utcnow(),
        metadata={"voice_confidence": 0.98, "language": "en"}
    )

    # Create BargeIn event
    event = BargeIn(
        interrupt_time=datetime.utcnow(),
        cancellation_reason="user_interrupt",
        cognitive_trace_id="abc123",
        interrupted_turn_id="turn_456",
        timestamp=datetime.utcnow()
    )

Research Foundation:
- Event schema design (JSON Schema, Avro, Protocol Buffers)
- Cognitive trace ID propagation (W3C Trace Context, OpenTelemetry)
- Immutable data structures (functional programming, dataclasses)

TODO:
- [ ] Implement IntentDetected dataclass (tier, intent, confidence, entities, cognitive_trace_id)
- [ ] Implement UserInput dataclass (input_type, raw_text, cognitive_trace_id, metadata)
- [ ] Implement VoiceCommand dataclass (transcript, vad_confidence, language, cognitive_trace_id)
- [ ] Implement BargeIn dataclass (interrupt_time, cancellation_reason, cognitive_trace_id, interrupted_turn_id)
- [ ] Add schema versioning (__version__ = "1.0.0")
- [ ] Add cognitive_trace_id generation utility (UUID4 or custom 128-bit)
- [ ] Add timestamp utilities (UTC timezone enforcement)
- [ ] Add schema validation (type hints, runtime checks)
- [ ] Add unit tests for schema instantiation and validation
- [ ] Add JSON serialization support (for logging/debugging, optional)
"""

# TODO: Implement event schema dataclasses (IntentDetected, UserInput, VoiceCommand, BargeIn)
