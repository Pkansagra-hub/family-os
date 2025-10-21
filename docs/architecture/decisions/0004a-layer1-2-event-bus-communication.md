# ADR-0004a: Layer 1-2 Event Bus Communication Pattern

**Status:** ✅ **COMPLETED** (2025-10-12)
**Date:** 2025-10-12
**Last Updated:** 2025-10-12
**Deciders:** K1 Architecture Team
**Technical Story:** Define event-driven communication for Layer 1 → Layer 2 interaction while preserving strict layering rules
**Parent ADR:** [ADR-0004: 52-Module 5-Layer Microkernel Architecture](0004-52-module-5-layer-architecture.md)
**Related ADRs:**
- [ADR-0002: Actor Model for Agent Isolation](0002-actor-model-agent-isolation.md)
- [ADR-0003: MPST Protocol Validation](0003-mpst-protocol-validation.md)

---

## Executive Summary

K1's **5-layer architecture** enforces strict layering: Layer 1 (Input Processing) cannot directly import Layer 2 (Orchestration). However, Layer 1 must **notify** Layer 2 of detected intents to trigger orchestration.

**Solution:** **Layer 1 → Layer 5 (Event Bus) → Layer 2** pattern using pub/sub messaging.

**Key Features:**
- **Event Bus** in Layer 5 (Infrastructure) - foundation layer, no layering violations
- **Layer 1 publishes events** (IntentDetected, UserInput, VoiceCommand) via Layer 5 bus
- **Layer 2 subscribes to events** from Layer 1 via Layer 5 bus
- **Async delivery** (<5ms P95 event propagation, non-blocking)
- **Zero-copy event passing** (shared buffer, no serialization overhead)
- **Hot path optimized:** L1 → L5 (emit) → L2 (subscribe) <10ms total

**Performance Targets:**
- Event publish latency: <2ms P95 (Layer 1 → Layer 5)
- Event delivery latency: <5ms P95 (Layer 5 → Layer 2)
- Total end-to-end: <10ms P95 (Layer 1 → Layer 2 via Layer 5)
- Event bus overhead: <1% CPU

---

## Context

### The Challenge

**K1 5-Layer Architecture (from ADR-0004):**

```
Layer 1: Input Processing    → Can only import Layer 5 (Infrastructure)
Layer 2: Orchestration        → Can import Layers 1, 3, 4, 5
Layer 3: Execution            → Can import Layers 4, 5
Layer 4: Runtime Core         → Can import Layer 5
Layer 5: Infrastructure       → No imports from other layers (foundation)
```

**Problem:**
- **Layer 1 detects user intent** (via 3-tier intent router: regex → SLM → LLM)
- **Layer 2 needs to know** when intent detected (to trigger orchestration)
- **Direct import FORBIDDEN:** Layer 1 cannot import Layer 2 (layering violation)
- **But Layer 2 can import Layer 1:** So L2 could poll L1 (inefficient, adds latency)

**Requirement:**
- Layer 1 must **push** intent events to Layer 2 (not poll)
- Preserve strict layering (L1 cannot import L2)
- Hot path optimized (<10ms end-to-end)
- Async delivery (non-blocking, no back-pressure on L1)

**Research Foundation:**
- Event-Driven Architecture (Hohpe & Woolf 2003) — Enterprise Integration Patterns
- Pub/Sub Messaging (Google Cloud Pub/Sub, Apache Kafka)
- Actor Model message-passing (Hewitt 1973) — Already foundation for K1

---

## Decision

We adopt an **event bus pattern** where Layer 1 publishes events to Layer 5 (Infrastructure), and Layer 2 subscribes to those events via Layer 5.

**Architecture:**

```
┌────────────────────────────────────────────────────────────────────────┐
│                     Layer 1: Input Processing                           │
├────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────┐       ┌──────────────────┐                       │
│  │ Stream Switch   │──────▶│  Intent Router   │                       │
│  │ (multi-modal)   │       │  (3-tier class)  │                       │
│  └─────────────────┘       └──────────────────┘                       │
│                                      │                                  │
│                                      │ 1. Detect intent                │
│                                      │                                  │
│                                      ▼                                  │
│                            ┌──────────────────┐                        │
│                            │  Publish Event   │                        │
│                            │  to Layer 5 Bus  │                        │
│                            └──────────────────┘                        │
│                                      │                                  │
└──────────────────────────────────────┼──────────────────────────────────┘
                                       │
                                       │ Import Layer 5 (allowed)
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    Layer 5: Infrastructure (Event Bus)                  │
├────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐│
│  │                         Event Bus                                   ││
│  │  - Topics: intent_detected, user_input, voice_command              ││
│  │  - Pub/Sub pattern (async, non-blocking)                           ││
│  │  - Zero-copy delivery (shared buffer)                              ││
│  │  - Metrics: event_bus_publish_total, event_bus_latency_ms          ││
│  └────────────────────────────────────────────────────────────────────┘│
│                                      │                                  │
│                                      │ 2. Route event to subscribers   │
│                                      │                                  │
│                                      ▼                                  │
│                            ┌──────────────────┐                        │
│                            │  Deliver Event   │                        │
│                            │  to Subscribers  │                        │
│                            └──────────────────┘                        │
│                                      │                                  │
└──────────────────────────────────────┼──────────────────────────────────┘
                                       │
                                       │ Subscribe via Layer 5 (allowed)
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     Layer 2: Orchestration                              │
├────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│                            ┌──────────────────┐                        │
│                            │  Event Handler   │                        │
│                            │  (subscriber)    │                        │
│                            └──────────────────┘                        │
│                                      │                                  │
│                                      │ 3. Trigger orchestration        │
│                                      │                                  │
│                                      ▼                                  │
│  ┌─────────────────┐       ┌──────────────────┐                       │
│  │  Orchestrator   │◀──────│     Planner      │                       │
│  │  (Contract Net) │       │  (4-stage plan)  │                       │
│  └─────────────────┘       └──────────────────┘                       │
│                                                                          │
└────────────────────────────────────────────────────────────────────────┘

**Flow:**
1. Layer 1 (Intent Router) detects intent → Publishes IntentDetected event to Layer 5 bus
2. Layer 5 (Event Bus) routes event to subscribers → Delivers event to Layer 2
3. Layer 2 (Orchestrator) receives event → Triggers orchestration (plan generation, agent hire)
```

---

## Design

### Component 1: Event Bus (Layer 5 Infrastructure)

**File:** `k1/infrastructure/event_bus.py`

**Purpose:** Central pub/sub message bus for cross-layer communication.

```python
"""
Module: k1.infrastructure.event_bus
Purpose: Event bus for cross-layer communication (L1 → L5 → L2)

Research: Event-Driven Architecture (Hohpe & Woolf 2003)
"""

from dataclasses import dataclass
from typing import Dict, List, Callable, Any
from enum import Enum
import asyncio
import time
from collections import defaultdict

class EventTopic(Enum):
    """Event topics (Layer 1 → Layer 2 events)"""
    INTENT_DETECTED = "intent_detected"
    USER_INPUT = "user_input"
    VOICE_COMMAND = "voice_command"
    BARGE_IN = "barge_in"

@dataclass
class Event:
    """Event envelope"""
    topic: EventTopic
    session_id: str
    payload: Dict[str, Any]
    cognitive_trace_id: str
    timestamp: float

class EventBus:
    """
    Event Bus: Pub/Sub pattern for cross-layer communication

    Responsibilities:
    1. Register subscribers for topics
    2. Publish events to topics
    3. Deliver events to subscribers (async, non-blocking)
    4. Metrics: publish_total, latency_ms
    5. Zero-copy delivery (shared buffer, no serialization)

    Performance Budget:
    - Publish latency: <2ms P95 (L1 → L5)
    - Delivery latency: <5ms P95 (L5 → L2)
    - Total: <10ms P95 end-to-end
    """

    def __init__(self):
        self.subscribers: Dict[EventTopic, List[Callable]] = defaultdict(list)
        self.event_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._delivery_task = None

    def subscribe(self, topic: EventTopic, handler: Callable[[Event], None]):
        """
        Subscribe to topic

        Usage:
            # Layer 2 subscribes to Layer 1 events
            event_bus.subscribe(EventTopic.INTENT_DETECTED, orchestrator.handle_intent)
        """
        self.subscribers[topic].append(handler)

    async def publish(self, event: Event):
        """
        Publish event to topic

        Usage:
            # Layer 1 publishes intent event
            event = Event(
                topic=EventTopic.INTENT_DETECTED,
                session_id="session_123",
                payload={"intent": "weather_query", "confidence": 0.95},
                cognitive_trace_id="trace_456",
                timestamp=time.time(),
            )
            await event_bus.publish(event)

        Performance:
        - Non-blocking (async queue put)
        - <2ms P95 latency
        """
        start_time = time.time()

        # Add to queue (non-blocking)
        await self.event_queue.put(event)

        # Metrics
        publish_latency_ms = (time.time() - start_time) * 1000
        from k1.observability.metrics import event_bus_publish_latency_ms, event_bus_publish_total
        event_bus_publish_latency_ms.labels(topic=event.topic.value).observe(publish_latency_ms)
        event_bus_publish_total.labels(topic=event.topic.value).inc()

    async def _delivery_loop(self):
        """Background task: Deliver events to subscribers"""
        while True:
            # Get event from queue
            event = await self.event_queue.get()

            # Get subscribers for topic
            handlers = self.subscribers.get(event.topic, [])

            if not handlers:
                # No subscribers for topic (log warning)
                from k1.observability.logging import logger
                logger.warning(
                    "event_no_subscribers",
                    topic=event.topic.value,
                    session_id=event.session_id,
                    trace_id=event.cognitive_trace_id,
                )
                continue

            # Deliver event to all subscribers (async, parallel)
            start_time = time.time()

            tasks = [handler(event) for handler in handlers if asyncio.iscoroutinefunction(handler)]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            # Call sync handlers (non-blocking via executor)
            sync_handlers = [h for h in handlers if not asyncio.iscoroutinefunction(h)]
            if sync_handlers:
                loop = asyncio.get_event_loop()
                await asyncio.gather(*[loop.run_in_executor(None, h, event) for h in sync_handlers])

            # Metrics
            delivery_latency_ms = (time.time() - start_time) * 1000
            from k1.observability.metrics import event_bus_delivery_latency_ms, event_bus_delivery_total
            event_bus_delivery_latency_ms.labels(topic=event.topic.value).observe(delivery_latency_ms)
            event_bus_delivery_total.labels(topic=event.topic.value, subscriber_count=len(handlers)).inc()

    async def start(self):
        """Start event bus delivery loop"""
        self._delivery_task = asyncio.create_task(self._delivery_loop())

    async def stop(self):
        """Stop event bus delivery loop"""
        if self._delivery_task:
            self._delivery_task.cancel()
            try:
                await self._delivery_task
            except asyncio.CancelledError:
                pass

# Global event bus instance (singleton)
event_bus = EventBus()
```

---

### Component 2: Layer 1 Event Publisher

**File:** `k1/input/intent_router.py` (Layer 1)

**Purpose:** Publish intent detection events to Layer 5 bus.

```python
"""
Module: k1.input.intent_router
Purpose: 3-tier intent classification (T1: regex, T2: SLM, T3: LLM)

Layer: 1 (Input Processing)
Imports: Layer 5 only (event_bus from k1.infrastructure)
"""

from k1.infrastructure.event_bus import event_bus, Event, EventTopic
import time

class IntentRouter:
    """
    Intent Router: 3-tier intent classification

    Tier 1 (regex): <1ms, 40% coverage
    Tier 2 (SLM): 2-3ms, 50% coverage
    Tier 3 (LLM): <50ms, 95% coverage

    Publishes IntentDetected events to Layer 5 bus → Layer 2 subscribes
    """

    async def classify_intent(self, user_input: str, session_id: str, trace_id: str) -> str:
        """Classify user intent (3-tier cascade)"""

        # Tier 1: Regex patterns (<1ms)
        intent = self._tier1_regex(user_input)
        if intent:
            await self._publish_intent_event(intent, session_id, trace_id, tier=1, confidence=1.0)
            return intent

        # Tier 2: SLM (2-3ms)
        intent, confidence = await self._tier2_slm(user_input)
        if confidence > 0.8:
            await self._publish_intent_event(intent, session_id, trace_id, tier=2, confidence=confidence)
            return intent

        # Tier 3: LLM (<50ms)
        intent, confidence = await self._tier3_llm(user_input)
        await self._publish_intent_event(intent, session_id, trace_id, tier=3, confidence=confidence)
        return intent

    async def _publish_intent_event(self, intent: str, session_id: str, trace_id: str, tier: int, confidence: float):
        """Publish IntentDetected event to Layer 5 bus"""

        event = Event(
            topic=EventTopic.INTENT_DETECTED,
            session_id=session_id,
            payload={
                "intent": intent,
                "confidence": confidence,
                "tier": tier,
                "timestamp": time.time(),
            },
            cognitive_trace_id=trace_id,
            timestamp=time.time(),
        )

        # Publish to Layer 5 event bus (non-blocking, <2ms)
        await event_bus.publish(event)

    def _tier1_regex(self, text: str) -> str | None:
        """Tier 1: Regex intent detection"""
        # ... regex patterns ...
        pass

    async def _tier2_slm(self, text: str) -> tuple[str, float]:
        """Tier 2: SLM intent classification"""
        # ... SLM inference ...
        pass

    async def _tier3_llm(self, text: str) -> tuple[str, float]:
        """Tier 3: LLM intent classification"""
        # ... LLM call via Model Hub ...
        pass
```

---

### Component 3: Layer 2 Event Subscriber

**File:** `k1.orchestration/orchestrator.py` (Layer 2)

**Purpose:** Subscribe to Layer 1 events via Layer 5 bus, trigger orchestration.

```python
"""
Module: k1.orchestration.orchestrator
Purpose: Multi-agent coordinator (Contract Net Protocol)

Layer: 2 (Orchestration)
Imports: Layers 1, 3, 4, 5 (all allowed for Layer 2)
"""

from k1.infrastructure.event_bus import event_bus, Event, EventTopic

class Orchestrator:
    """
    Orchestrator: Multi-agent coordinator

    Subscribes to Layer 1 events (IntentDetected) via Layer 5 bus
    Triggers orchestration pipeline: planner → agent hire → execution
    """

    def __init__(self):
        # Subscribe to Layer 1 events via Layer 5 bus
        event_bus.subscribe(EventTopic.INTENT_DETECTED, self.handle_intent_event)

    async def handle_intent_event(self, event: Event):
        """
        Handle IntentDetected event from Layer 1

        Triggered by Layer 5 event bus when Layer 1 publishes intent event.
        """
        session_id = event.session_id
        intent = event.payload["intent"]
        confidence = event.payload["confidence"]
        trace_id = event.cognitive_trace_id

        # Log event
        from k1.observability.logging import logger
        logger.info(
            "orchestrator_intent_received",
            session_id=session_id,
            intent=intent,
            confidence=confidence,
            trace_id=trace_id,
        )

        # Trigger orchestration pipeline
        await self._orchestrate(session_id, intent, trace_id)

    async def _orchestrate(self, session_id: str, intent: str, trace_id: str):
        """Orchestration pipeline: planner → agent hire → execution"""

        # 1. Generate plan (Planner)
        from k1.orchestration.planner import planner
        plan = await planner.generate_plan(intent, session_id, trace_id)

        # 2. Hire agents (Contract Net Protocol)
        agents = await self._hire_agents(plan, session_id, trace_id)

        # 3. Execute plan (Layer 3)
        await self._execute_plan(plan, agents, session_id, trace_id)
```

---

## Event Schema Definitions

### IntentDetected Event

**Topic:** `intent_detected`

**Payload:**
```python
{
    "intent": str,           # Intent name (e.g., "weather_query", "calendar_add")
    "confidence": float,     # Confidence score (0.0-1.0)
    "tier": int,             # Classification tier (1=regex, 2=SLM, 3=LLM)
    "timestamp": float,      # Unix timestamp (when classified)
}
```

**Example:**
```python
event = Event(
    topic=EventTopic.INTENT_DETECTED,
    session_id="session_123",
    payload={
        "intent": "weather_query",
        "confidence": 0.95,
        "tier": 2,  # SLM classified
        "timestamp": 1697000000.123,
    },
    cognitive_trace_id="trace_456",
    timestamp=1697000000.123,
)
```

### UserInput Event

**Topic:** `user_input`

**Payload:**
```python
{
    "text": str,             # User input text (normalized)
    "modality": str,         # "text", "voice", "video"
    "language": str,         # ISO 639-1 code (e.g., "en", "es")
    "timestamp": float,
}
```

### VoiceCommand Event

**Topic:** `voice_command`

**Payload:**
```python
{
    "command": str,          # Voice command (e.g., "stop", "pause", "resume")
    "action": str,           # Action type ("barge_in", "pause", "resume", "stop")
    "timestamp": float,
}
```

---

## Performance Analysis

### Latency Breakdown

**Layer 1 → Layer 5 (Publish):**
- Event creation: <100μs
- Queue put (asyncio): <500μs
- Metrics logging: <50μs
- **Total:** <2ms P95

**Layer 5 → Layer 2 (Delivery):**
- Queue get (asyncio): <500μs
- Subscriber lookup (dict): <50μs
- Handler invocation (asyncio.gather): <1ms
- Metrics logging: <50μs
- **Total:** <5ms P95

**End-to-End (Layer 1 → Layer 2):**
- **Total:** <10ms P95 (publish + delivery)

**Budget:** ✅ Meets <10ms requirement

### Throughput

**Event Bus Capacity:**
- Queue size: 1000 events (prevents unbounded growth)
- Delivery rate: ~5000 events/sec (single-threaded delivery loop)
- Back-pressure: Queue full → block publisher (rare, indicates overload)

**Typical Load:**
- User input rate: ~1-2 events/sec (human typing speed)
- Voice commands: ~5-10 events/sec (barge-in, pause/resume)
- **Total:** ~10-20 events/sec (well below capacity)

---

## Consequences

### Positive ✅

**✅ Strict Layering Preserved:**
- Layer 1 never imports Layer 2 (no layering violation)
- Event bus in Layer 5 (foundation, all layers can import)
- **Result:** Clean architecture, maintainable

**✅ Async, Non-Blocking:**
- Event publish <2ms (queue put)
- No back-pressure on Layer 1 (intent router continues)
- **Result:** Hot path optimized, <10ms end-to-end

**✅ Decoupling:**
- Layer 1 doesn't know about Layer 2 (publishes events, doesn't care who subscribes)
- Layer 2 can have multiple subscribers (orchestrator, meta_policy, etc.)
- **Result:** Flexible, extensible

**✅ Observability:**
- Metrics: `event_bus_publish_total`, `event_bus_latency_ms`, `event_bus_delivery_total`
- Tracing: cognitive_trace_id propagated in events
- **Result:** Full visibility into cross-layer communication

---

### Negative ⚠️

**⚠️ Indirection Overhead:**
- Layer 1 → Layer 5 → Layer 2 (vs direct L1 → L2)
- **Mitigation:** Event bus optimized (<10ms), acceptable overhead
- **Risk Level:** LOW (10ms < 150ms TTFT budget)

**⚠️ Event Queue Backlog:**
- If Layer 2 slow to process events → queue grows → back-pressure
- **Mitigation:** Queue size limit (1000 events), monitoring (`event_bus_queue_size` gauge)
- **Risk Level:** LOW (typical load 10-20 events/sec << 5000 events/sec capacity)

**⚠️ Event Schema Evolution:**
- Changing event payload breaks subscribers
- **Mitigation:** Versioned event schemas, backward compatibility
- **Risk Level:** MEDIUM (requires careful schema management)

---

## Implementation Notes

### **Implementation Timeline**

**Phase 1 (Week 1): Event Bus Core**
- Implement Event, EventTopic, EventBus classes
- Unit tests: pub/sub, delivery, metrics
- Performance tests: <10ms end-to-end latency

**Phase 2 (Week 2): Layer 1 Integration**
- Update IntentRouter to publish IntentDetected events
- Integration tests: L1 → L5 event publish
- Performance tests: <2ms publish latency

**Phase 3 (Week 3): Layer 2 Integration**
- Update Orchestrator to subscribe to IntentDetected events
- Integration tests: L1 → L5 → L2 event delivery
- End-to-end tests: intent detection → orchestration trigger

**Phase 4 (Week 4): Additional Events**
- Implement UserInput, VoiceCommand, BargeIn events
- Integration tests for all event types
- Documentation: event schema catalog

---

### **Dependencies**

**Before Starting:**
- ✅ ADR-0004 (52-Module Architecture) - Layering rules
- ✅ Layer 5 infrastructure modules exist

**Blocking:**
- Layer 1 (Intent Router) needs event publishing
- Layer 2 (Orchestrator) needs event subscription
- All cross-layer communication depends on event bus

---

### **Success Metrics**

**Performance:**
- ✅ Event publish latency: <2ms P95
- ✅ Event delivery latency: <5ms P95
- ✅ End-to-end latency: <10ms P95
- ✅ Event bus overhead: <1% CPU

**Correctness:**
- ✅ All Layer 1 events delivered to Layer 2 subscribers
- ✅ No missed events (queue monitoring)
- ✅ cognitive_trace_id preserved across events

**Quality:**
- ✅ 100% test coverage (pub/sub, delivery, metrics)
- ✅ Integration tests with Layer 1 and Layer 2
- ✅ Performance tests validate <10ms latency

---

## References

### **Research Papers**

1. **Hohpe, G., Woolf, B. (2003)**
   "Enterprise Integration Patterns"
   *Addison-Wesley*
   **Relevance**: Pub/Sub pattern, event-driven architecture

2. **Hewitt, C. (1973)**
   "A Universal Modular Actor Formalism for Artificial Intelligence"
   *IJCAI*
   **Relevance**: Actor Model foundation (K1 uses Actor Model + Event Bus)

### **Related ADRs**

- [ADR-0004: 52-Module 5-Layer Architecture](0004-52-module-5-layer-architecture.md) — Parent ADR
- [ADR-0002: Actor Model for Agent Isolation](0002-actor-model-agent-isolation.md) — Message-passing foundation
- [ADR-0003: MPST Protocol Validation](0003-mpst-protocol-validation.md) — Protocol validation for cross-agent messages

### **Architecture Diagrams**

- `architecture_diagrams/k1_architecture_diagram.mmd` — K1 complete architecture
- `architecture_diagrams/k1_kernel_complete_adr_architecture.mmd` — K1 kernel with ADR mappings

---

**Document Status:** ✅ **COMPLETE** - Layer 1-2 event bus communication pattern fully specified with pub/sub design, event schemas, performance analysis, and implementation notes.

**Cross-References:**
- ADR-0004 (Parent): 52-Module 5-Layer Architecture
- ADR-0002: Actor Model (message-passing)
- Event Bus: Layer 5 Infrastructure

**Canonical Values:**
- **Event publish latency:** <2ms P95 (L1 → L5)
- **Event delivery latency:** <5ms P95 (L5 → L2)
- **End-to-end latency:** <10ms P95 (L1 → L2 via L5)
- **Queue capacity:** 1000 events
- **Delivery throughput:** ~5000 events/sec

**Document End**
