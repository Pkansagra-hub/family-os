"""
Layer 5 - Event Bus Module

This module provides K1's internal event bus for Layer 1→2 communication
using pub/sub pattern with zero-copy delivery.

Components:
- event_bus: Topic-based pub/sub with async delivery
- schemas: Event schema definitions (IntentDetected, UserInput, VoiceCommand, BargeIn)

Event Bus Architecture (ADR-0004a, ADR-0048):
- 100% K1-internal (no K0 boundary crossing)
- In-memory pub/sub (asyncio.Queue per subscriber)
- Zero-copy: Pass references, no serialization
- Topic-based routing (INTENT_DETECTED, USER_INPUT, VOICE_COMMAND, BARGE_IN)
- Multiple subscribers per topic (1-to-N fanout)
- <5ms delivery latency (<2ms typical, <1ms per event)

Key Topics:
- k1.intent.detected: Intent classification results (T1/T2/T3)
- k1.user.input: User input events (text/voice)
- k1.voice.command: Voice command transcriptions
- k1.barge_in: User interruption events

Backpressure (ADR-0048):
- Subscriber queue depth: 50 max (1000 for K1 internal)
- Overflow: DROP_OLDEST policy
- Slow subscriber detection: >100ms processing time (>90% full queue)
- Graceful degradation

Performance (ADR-0024):
- Event delivery: <5ms P95 (<2ms typical)
- Throughput: 1000+ events/sec
- Subscriber queue depth: <10 typical, <50 max
- Backpressure events: <1% of deliveries

Primary ADRs:
- ADR-0004a: Event Bus (Layer 1-2 communication, pub/sub, zero-copy)
- ADR-0048: K1 Internal Event Bus (in-memory pub/sub, k1.* namespace)
- ADR-0024: Performance Budgets (event bus <5ms)

Research Foundation:
- Pub/sub pattern (observer pattern, message broker)
- Zero-copy message passing (shared memory, reference passing)
- Backpressure management (queue depth, overflow policies)
"""

# __all__ = [
#     "EventBus",
#     "IntentDetected",
#     "UserInput",
#     "VoiceCommand",
#     "BargeIn",
# ]
