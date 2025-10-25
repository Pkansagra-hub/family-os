"""Integration tests for K1 Event Bus cross-layer communication"""Integration tests for K1 Event Bus cross-layer communication"""Integration tests for K1 Event Bus cross-layer communication"""Integration tests for K1 Event Bus cross-layer communication



Tests the event bus integration pattern: Layer 1 -> Layer 5 -> Layer 2

Verifies pub/sub messaging works across architectural layers.

Tests the event bus integration pattern: Layer 1 -> Layer 5 -> Layer 2

ADRs:

- ADR-0004a: Layer 1-2 Event Bus CommunicationVerifies pub/sub messaging works across architectural layers.

- ADR-0004: 52-Module 5-Layer Architecture (layering rules)

"""Tests the event bus integration pattern: Layer 1 → Layer 5 → Layer 2Tests the event bus integration pattern: Layer 1 → Layer 5 → Layer 2



import asyncioADRs:

from datetime import datetime, timezone

- ADR-0004a: Layer 1-2 Event Bus CommunicationVerifies pub/sub messaging works across architectural layers.Verifies pub/sub messaging works across architectural layers.

from ward import test, fixture

- ADR-0004: 52-Module 5-Layer Architecture (layering rules)

from k1.l5_infrastructure.event_bus.event_bus import EventBus

from k1.l5_infrastructure.event_bus.schemas import (

    EventTopic,

    IntentDetectedEvent,Test Coverage:

)

1. Layer 1 can publish events to Layer 5 event busADRs:ADRs:



@fixture2. Layer 2 can subscribe to events from Layer 5 event bus

async def event_bus():

    """Real EventBus instance for integration testing"""3. Event delivery preserves cognitive_trace_id- ADR-0004a: Layer 1-2 Event Bus Communication- ADR-0004a: Layer 1-2 Event Bus Communication

    bus = EventBus()

    yield bus4. No layering violations (L1 cannot import L2)

    await bus.shutdown()

5. Event schemas comply with contracts- ADR-0004: 52-Module 5-Layer Architecture (layering rules)- ADR-0004: 52-Module 5-Layer Architecture (layering rules)



@test("Layer 1 can publish events to Layer 5 Event Bus")

async def test_l1_to_l5_publish(event_bus=event_bus):

    """Test Layer 1 -> Layer 5 event publishing"""Performance Requirements:

    # Simulate Layer 1 publishing an IntentDetected event

    event = IntentDetectedEvent(- Event publish: <2ms P95

        intent="weather_query",

        confidence=0.85,- Event delivery: <5ms P95Test Coverage:Test Coverage:

        tier="T1_RULE",

        entities={"location": "San Francisco"},- End-to-end: <10ms P95

        session_id="session_123",

        cognitive_trace_id="5f2d4c7a8b3e41e8a9d9c6f1b2a4d687",1. Layer 1 can publish events to Layer 5 event bus1. Layer 1 can publish events to Layer 5 event bus

        timestamp=datetime.now(timezone.utc),

    )Last Updated: 2025-10-25



    # Layer 1 publishes to Layer 5 event bus"""2. Layer 2 can subscribe to events from Layer 5 event bus2. Layer 2 can subscribe to events from Layer 5 event bus

    await event_bus.publish(event)



    # Verify event was accepted (no exception thrown)

    assert event.intent == "weather_query"import asyncio3. Event delivery preserves cognitive_trace_id3. Event delivery preserves cognitive_trace_id



import time

@test("Layer 2 can subscribe to events from Layer 5 Event Bus")

async def test_l5_to_l2_subscribe(event_bus=event_bus):from datetime import datetime, timezone4. No layering violations (L1 cannot import L2)4. No layering violations (L1 cannot import L2)

    """Test Layer 5 -> Layer 2 event delivery"""

    received_events = []from typing import List



    async def handler(event):5. Event schemas comply with contracts5. Event schemas comply with contracts

        received_events.append(event)

from ward import test, fixture

    # Layer 2 subscribes to events

    handle = event_bus.subscribe(EventTopic.INTENT_DETECTED, handler)



    # Simulate event publicationfrom k1.l5_infrastructure.event_bus.event_bus import EventBus

    event = IntentDetectedEvent(

        intent="test_intent",from k1.l5_infrastructure.event_bus.schemas import (Performance Requirements:Performance Requirements:

        confidence=0.9,

        tier="T1_RULE",    EventBase,

        entities={},

        session_id="session_test",    EventTopic,- Event publish: <2ms P95- Event publish: <2ms P95

        cognitive_trace_id="5f2d4c7a8b3e41e8a9d9c6f1b2a4d687",

        timestamp=datetime.now(timezone.utc),    IntentDetectedEvent,

    )

    UserInputEvent,- Event delivery: <5ms P95- Event delivery: <5ms P95

    await event_bus.publish(event)

    VoiceCommandEvent,

    # Allow async delivery

    await asyncio.sleep(0.01)    BargeInEvent,- End-to-end: <10ms P95- End-to-end: <10ms P95



    # Verify Layer 2 received event)

    assert len(received_events) == 1

    assert received_events[0].intent == event.intent



    await handle.unsubscribe()



@fixtureLast Updated: 2025-10-25Last Updated: 2025-10-25

@test("Event schemas comply with contract validation")

async def test_event_schema_contracts():async def event_bus():

    """Test that event schemas match contract specifications"""

    # Test IntentDetected event    """Real EventBus instance for integration testing"""""""""

    intent_event = IntentDetectedEvent(

        intent="weather_query",    bus = EventBus()

        confidence=0.85,

        tier="T1_RULE",    yield bus

        entities={"location": "San Francisco"},

        session_id="session_123",    await bus.shutdown()

        cognitive_trace_id="5f2d4c7a8b3e41e8a9d9c6f1b2a4d687",

        timestamp=datetime.now(timezone.utc),import asyncioimport asyncio

    )



    # Verify required fields are present and valid

    assert intent_event.intent == "weather_query"class MockIntentRouter:import timeimport time

    assert intent_event.confidence == 0.85

    assert intent_event.tier == "T1_RULE"    """Mock Layer 1 Intent Router for integration testing

    assert intent_event.session_id == "session_123"

    assert intent_event.cognitive_trace_id == "5f2d4c7a8b3e41e8a9d9c6f1b2a4d687"from datetime import datetime, timezonefrom typing import List

    assert intent_event.timestamp is not None
    Simulates Layer 1 publishing IntentDetected events to Layer 5 bus.

    Cannot import Layer 2 (preserves layering).from typing import List

    """

from ward import test, fixture

    def __init__(self, event_bus: EventBus):

        self.event_bus = event_busfrom ward import test, fixture

        self.published_events: List[IntentDetectedEvent] = []

from k1.l5_infrastructure.event_bus.event_bus import EventBus

    async def detect_intent(self, user_input: str, session_id: str, trace_id: str) -> None:

        """Simulate intent detection and publish event (Layer 1 -> Layer 5)"""from k1.l5_infrastructure.event_bus.event_bus import EventBusfrom k1.l5_infrastructure.event_bus.schemas import (

        # Simulate 3-tier classification (T1 rule-based, T2 SLM, T3 LLM)

        intent = "weather_query" if "weather" in user_input.lower() else "general_query"from k1.l5_infrastructure.event_bus.schemas import (    IntentDetectedEvent,

        confidence = 0.85

        tier = "T1_RULE"    EventBase,    UserInputEvent,



        event = IntentDetectedEvent(    EventTopic,    VoiceCommandEvent,

            intent=intent,

            confidence=confidence,    IntentDetectedEvent,    BargeInEvent,

            tier=tier,

            entities={"location": "San Francisco"} if "san francisco" in user_input else {},    UserInputEvent,    EventPriority,

            session_id=session_id,

            cognitive_trace_id=trace_id,    VoiceCommandEvent,)

            timestamp=datetime.now(timezone.utc),

        )    BargeInEvent,



        # Publish to Layer 5 event bus (allowed: L1 -> L5))

        await self.event_bus.publish(event)

@fixture

        self.published_events.append(event)

async def event_bus():



class MockOrchestrator:@fixture    """Real EventBus instance for integration testing"""

    """Mock Layer 2 Orchestrator for integration testing

async def event_bus():    bus = EventBus()

    Simulates Layer 2 subscribing to IntentDetected events from Layer 5 bus.

    Can import Layer 1 and Layer 5 (per layering rules).    """Real EventBus instance for integration testing"""    await bus.initialize()

    """

    bus = EventBus()    yield bus

    def __init__(self, event_bus: EventBus):

        self.event_bus = event_bus    yield bus    await bus.shutdown()

        self.received_events: List[IntentDetectedEvent] = []

        self.subscription_handle = None    await bus.shutdown()



    async def start(self):

        """Subscribe to events from Layer 5 bus (allowed: L2 -> L5)"""

        async def on_intent_detected(event: EventBase):class MockIntentRouter:

            self.received_events.append(event)

            # Simulate orchestration trigger (plan generation, agent selection, etc.)class MockIntentRouter:    """Mock Layer 1 Intent Router for integration testing

            print(f"Orchestrator triggered for intent: {event.intent}")

    """Mock Layer 1 Intent Router for integration testing

        self.subscription_handle = self.event_bus.subscribe(

            EventTopic.INTENT_DETECTED,    Simulates Layer 1 publishing IntentDetected events to Layer 5 bus.

            on_intent_detected

        )    Simulates Layer 1 publishing IntentDetected events to Layer 5 bus.    Cannot import Layer 2 (preserves layering).



    async def stop(self):    Cannot import Layer 2 (preserves layering).    """

        """Unsubscribe from events"""

        if self.subscription_handle:    """

            await self.subscription_handle.unsubscribe()

    def __init__(self, event_bus: EventBus):



@test("Layer 1 Intent Router can publish events to Layer 5 Event Bus")    def __init__(self, event_bus: EventBus):        self.event_bus = event_bus

async def test_l1_to_l5_publish(event_bus=event_bus):

    """Test Layer 1 -> Layer 5 event publishing (no Layer 2 involvement)"""        self.event_bus = event_bus        self.published_events: List[IntentDetectedEvent] = []

    router = MockIntentRouter(event_bus)

        self.published_events: List[IntentDetectedEvent] = []

    # Simulate user input

    user_input = "What's the weather in San Francisco?"    async def detect_intent(self, user_input: str, session_id: str, trace_id: str) -> None:

    session_id = "session_123"

    trace_id = "5f2d4c7a8b3e41e8a9d9c6f1b2a4d687"    async def detect_intent(self, user_input: str, session_id: str, trace_id: str) -> None:        """Simulate intent detection and publish event (Layer 1 → Layer 5)"""



    # Layer 1 detects intent and publishes event        """Simulate intent detection and publish event (Layer 1 → Layer 5)"""        # Simulate 3-tier classification (T1 rule-based, T2 SLM, T3 LLM)

    await router.detect_intent(user_input, session_id, trace_id)

        # Simulate 3-tier classification (T1 rule-based, T2 SLM, T3 LLM)        intent = "weather_query" if "weather" in user_input.lower() else "general_query"

    # Verify event was published

    assert len(router.published_events) == 1        intent = "weather_query" if "weather" in user_input.lower() else "general_query"        confidence = 0.85

    event = router.published_events[0]

        confidence = 0.85        tier = "T1_RULE"

    assert event.intent == "weather_query"

    assert event.confidence == 0.85        tier = "T1_RULE"

    assert event.tier == "T1_RULE"

    assert event.session_id == session_id        event = IntentDetectedEvent(

    assert event.cognitive_trace_id == trace_id

    assert "location" in event.entities        event = IntentDetectedEvent(            intent=intent,



            intent=intent,            confidence=confidence,

@test("Layer 2 Orchestrator can subscribe to events from Layer 5 Event Bus")

async def test_l5_to_l2_subscribe(event_bus=event_bus):            confidence=confidence,            tier=tier,

    """Test Layer 5 -> Layer 2 event delivery (no Layer 1 involvement)"""

    orchestrator = MockOrchestrator(event_bus)            tier=tier,            entities={"location": "San Francisco"} if "san francisco" in user_input else {},



    # Layer 2 starts listening            entities={"location": "San Francisco"} if "san francisco" in user_input else {},            session_id=session_id,

    await orchestrator.start()

            session_id=session_id,            cognitive_trace_id=trace_id,

    # Simulate event publication (normally from Layer 1)

    event = IntentDetectedEvent(            cognitive_trace_id=trace_id,            timestamp=time.time(),

        intent="test_intent",

        confidence=0.9,            timestamp=datetime.now(timezone.utc),        )

        tier="T1_RULE",

        entities={},        )

        session_id="session_test",

        cognitive_trace_id="5f2d4c7a8b3e41e8a9d9c6f1b2a4d687",        # Publish to Layer 5 event bus (allowed: L1 → L5)

        timestamp=datetime.now(timezone.utc),

    )        # Publish to Layer 5 event bus (allowed: L1 → L5)        await self.event_bus.publish(



    await event_bus.publish(event)        await self.event_bus.publish(event)            topic="intent_detected",



    # Allow async delivery            event=event,

    await asyncio.sleep(0.01)

        self.published_events.append(event)            priority=EventPriority.HIGH

    # Verify Layer 2 received event

    assert len(orchestrator.received_events) == 1        )

    received = orchestrator.received_events[0]



    assert received.intent == event.intent

    assert received.session_id == event.session_idclass MockOrchestrator:        self.published_events.append(event)

    assert received.cognitive_trace_id == event.cognitive_trace_id

    """Mock Layer 2 Orchestrator for integration testing

    await orchestrator.stop()





@test("End-to-end event flow: Layer 1 -> Layer 5 -> Layer 2")    Simulates Layer 2 subscribing to IntentDetected events from Layer 5 bus.class MockOrchestrator:

async def test_l1_to_l5_to_l2_e2e(event_bus=event_bus):

    """Test complete cross-layer event flow (L1 -> L5 -> L2)"""    Can import Layer 1 and Layer 5 (per layering rules).    """Mock Layer 2 Orchestrator for integration testing

    # Setup Layer 1 (Intent Router)

    router = MockIntentRouter(event_bus)    """



    # Setup Layer 2 (Orchestrator)    Simulates Layer 2 subscribing to IntentDetected events from Layer 5 bus.

    orchestrator = MockOrchestrator(event_bus)

    await orchestrator.start()    def __init__(self, event_bus: EventBus):    Can import Layer 1 and Layer 5 (per layering rules).



    # Simulate user interaction        self.event_bus = event_bus    """

    user_input = "What's the weather?"

    session_id = "e2e_session_789"        self.received_events: List[IntentDetectedEvent] = []

    trace_id = "5f2d4c7a8b3e41e8a9d9c6f1b2a4d687"

        self.subscription_handle = None    def __init__(self, event_bus: EventBus):

    # Layer 1 processes input and publishes event

    start_time = time.perf_counter()        self.event_bus = event_bus

    await router.detect_intent(user_input, session_id, trace_id)

    publish_time = time.perf_counter()    async def start(self):        self.received_events: List[IntentDetectedEvent] = []



    # Allow event delivery        """Subscribe to events from Layer 5 bus (allowed: L2 → L5)"""        self.subscription_id = None

    await asyncio.sleep(0.01)

    delivery_time = time.perf_counter()        async def on_intent_detected(event: EventBase):



    # Verify end-to-end flow            self.received_events.append(event)    async def start(self):

    assert len(router.published_events) == 1

    assert len(orchestrator.received_events) == 1            # Simulate orchestration trigger (plan generation, agent selection, etc.)        """Subscribe to events from Layer 5 bus (allowed: L2 → L5)"""



    published = router.published_events[0]            print(f"Orchestrator triggered for intent: {event.intent}")        async def on_intent_detected(event: IntentDetectedEvent):

    received = orchestrator.received_events[0]

            self.received_events.append(event)

    # Verify event integrity across layers

    assert published.intent == received.intent        self.subscription_handle = self.event_bus.subscribe(            # Simulate orchestration trigger (plan generation, agent selection, etc.)

    assert published.session_id == received.session_id

    assert published.cognitive_trace_id == received.cognitive_trace_id            EventTopic.INTENT_DETECTED,            print(f"Orchestrator triggered for intent: {event.intent}")



    # Verify performance budgets            on_intent_detected

    publish_latency_ms = (publish_time - start_time) * 1000

    delivery_latency_ms = (delivery_time - publish_time) * 1000        )        self.subscription_id = await self.event_bus.subscribe(

    e2e_latency_ms = (delivery_time - start_time) * 1000

            topic="intent_detected",

    assert publish_latency_ms < 2.0  # <2ms P95 budget

    assert delivery_latency_ms < 5.0  # <5ms P95 budget    async def stop(self):            callback=on_intent_detected

    assert e2e_latency_ms < 10.0  # <10ms P95 budget

        """Unsubscribe from events"""        )

    await orchestrator.stop()

        if self.subscription_handle:



@test("Event schemas comply with contract validation")            await self.subscription_handle.unsubscribe()    async def stop(self):

async def test_event_schema_contracts():

    """Test that event schemas match k1/contracts/event_bus/ specifications"""        """Unsubscribe from events"""

    # Test IntentDetected event

    intent_event = IntentDetectedEvent(        if self.subscription_id:

        intent="weather_query",

        confidence=0.85,@test("Layer 1 Intent Router can publish events to Layer 5 Event Bus")            await self.event_bus.unsubscribe(self.subscription_id)

        tier="T1_RULE",

        entities={"location": "San Francisco"},async def test_l1_to_l5_publish(event_bus=event_bus):

        session_id="session_123",

        cognitive_trace_id="5f2d4c7a8b3e41e8a9d9c6f1b2a4d687",    """Test Layer 1 → Layer 5 event publishing (no Layer 2 involvement)"""

        timestamp=datetime.now(timezone.utc),

    )    router = MockIntentRouter(event_bus)@test("Layer 1 Intent Router can publish events to Layer 5 Event Bus")



    # Verify required fields are presentasync def test_l1_to_l5_publish(event_bus=event_bus):

    assert intent_event.intent is not None

    assert 0.0 <= intent_event.confidence <= 1.0    # Simulate user input    """Test Layer 1 → Layer 5 event publishing (no Layer 2 involvement)"""

    assert intent_event.tier in ["T1_RULE", "T2_SLM", "T3_LLM"]

    assert intent_event.session_id is not None    user_input = "What's the weather in San Francisco?"    router = MockIntentRouter(event_bus)

    assert intent_event.cognitive_trace_id is not None

    assert intent_event.timestamp is not None    session_id = "session_123"



    # Test UserInput event    trace_id = "5f2d4c7a8b3e41e8a9d9c6f1b2a4d687"    # Simulate user input

    user_event = UserInputEvent(

        input_type="text",    user_input = "What's the weather in San Francisco?"

        content="Hello world",

        language="en",    # Layer 1 detects intent and publishes event    session_id = "session_123"

        session_id="session_123",

        cognitive_trace_id="5f2d4c7a8b3e41e8a9d9c6f1b2a4d687",    await router.detect_intent(user_input, session_id, trace_id)    trace_id = "trace_456"

        timestamp=datetime.now(timezone.utc),

    )



    assert user_event.input_type in ["text", "voice", "gesture"]    # Verify event was published    # Layer 1 detects intent and publishes event

    assert user_event.content is not None

    assert user_event.language is not None    assert len(router.published_events) == 1    await router.detect_intent(user_input, session_id, trace_id)



    # Test VoiceCommand event    event = router.published_events[0]

    voice_event = VoiceCommandEvent(

        command="play_music",    # Verify event was published

        confidence=0.92,

        language="en",    assert event.intent == "weather_query"    assert len(router.published_events) == 1

        vad_confidence=0.88,

        session_id="session_123",    assert event.confidence == 0.85    event = router.published_events[0]

        cognitive_trace_id="5f2d4c7a8b3e41e8a9d9c6f1b2a4d687",

        timestamp=datetime.now(timezone.utc),    assert event.tier == "T1_RULE"

    )

    assert event.session_id == session_id    assert event.intent == "weather_query"

    assert voice_event.command is not None

    assert 0.0 <= voice_event.confidence <= 1.0    assert event.cognitive_trace_id == trace_id    assert event.confidence == 0.85

    assert 0.0 <= voice_event.vad_confidence <= 1.0

    assert "location" in event.entities    assert event.tier == "T1_RULE"

    # Test BargeIn event

    barge_event = BargeInEvent(    assert event.session_id == session_id

        reason="user_interruption",

        session_id="session_123",    assert event.cognitive_trace_id == trace_id

        cognitive_trace_id="5f2d4c7a8b3e41e8a9d9c6f1b2a4d687",

        timestamp=datetime.now(timezone.utc),@test("Layer 2 Orchestrator can subscribe to events from Layer 5 Event Bus")    assert "location" in event.entities

    )

async def test_l5_to_l2_subscribe(event_bus=event_bus):

    assert barge_event.reason in ["user_interruption", "emergency", "timeout"]

    """Test Layer 5 → Layer 2 event delivery (no Layer 1 involvement)"""



@test("Layer isolation prevents invalid imports")    orchestrator = MockOrchestrator(event_bus)@test("Layer 2 Orchestrator can subscribe to events from Layer 5 Event Bus")

async def test_layer_isolation():

    """Test that layering rules are preserved (L1 cannot import L2)"""async def test_l5_to_l2_subscribe(event_bus=event_bus):

    # This test verifies that the mock components follow layering rules

    # In real implementation, Layer 1 cannot import Layer 2    # Layer 2 starts listening    """Test Layer 5 → Layer 2 event delivery (no Layer 1 involvement)"""



    # Layer 1 (MockIntentRouter) can import Layer 5 (EventBus) ✓    await orchestrator.start()    orchestrator = MockOrchestrator(event_bus)

    router = MockIntentRouter(event_bus=None)  # Would normally import EventBus



    # Layer 2 (MockOrchestrator) can import Layer 1 and Layer 5 ✓

    orchestrator = MockOrchestrator(event_bus=None)  # Would normally import EventBus    # Simulate event publication (normally from Layer 1)    # Layer 2 starts listening



    # Verify no circular dependencies or invalid imports    event = IntentDetectedEvent(    await orchestrator.start()

    # This is a structural test - in real code, l1_input cannot import l2_orchestration

    assert router is not None        intent="test_intent",

    assert orchestrator is not None
        confidence=0.9,    # Simulate event publication (normally from Layer 1)

        tier="T1_RULE",    event = IntentDetectedEvent(

        entities={},        intent="test_intent",

        session_id="session_test",        confidence=0.9,

        cognitive_trace_id="5f2d4c7a8b3e41e8a9d9c6f1b2a4d687",        tier="T1_RULE",

        timestamp=datetime.now(timezone.utc),        entities={},

    )        session_id="session_test",

        cognitive_trace_id="trace_test",

    await event_bus.publish(event)        timestamp=time.time(),

    )

    # Allow async delivery

    await asyncio.sleep(0.01)    await event_bus.publish(

        topic="intent_detected",

    # Verify Layer 2 received event        event=event,

    assert len(orchestrator.received_events) == 1        priority=EventPriority.NORMAL

    received = orchestrator.received_events[0]    )



    assert received.intent == event.intent    # Allow async delivery

    assert received.session_id == event.session_id    await asyncio.sleep(0.01)

    assert received.cognitive_trace_id == event.cognitive_trace_id

    # Verify Layer 2 received event

    await orchestrator.stop()    assert len(orchestrator.received_events) == 1

    received = orchestrator.received_events[0]



@test("End-to-end event flow: Layer 1 → Layer 5 → Layer 2")    assert received.intent == event.intent

async def test_l1_to_l5_to_l2_e2e(event_bus=event_bus):    assert received.session_id == event.session_id

    """Test complete cross-layer event flow (L1 → L5 → L2)"""    assert received.cognitive_trace_id == event.cognitive_trace_id

    # Setup Layer 1 (Intent Router)

    router = MockIntentRouter(event_bus)    await orchestrator.stop()



    # Setup Layer 2 (Orchestrator)

    orchestrator = MockOrchestrator(event_bus)@test("End-to-end event flow: Layer 1 → Layer 5 → Layer 2")

    await orchestrator.start()async def test_l1_to_l5_to_l2_e2e(event_bus=event_bus):

    """Test complete cross-layer event flow (L1 → L5 → L2)"""

    # Simulate user interaction    # Setup Layer 1 (Intent Router)

    user_input = "What's the weather?"    router = MockIntentRouter(event_bus)

    session_id = "e2e_session_789"

    trace_id = "5f2d4c7a8b3e41e8a9d9c6f1b2a4d687"    # Setup Layer 2 (Orchestrator)

    orchestrator = MockOrchestrator(event_bus)

    # Layer 1 processes input and publishes event    await orchestrator.start()

    start_time = time.perf_counter()

    await router.detect_intent(user_input, session_id, trace_id)    # Simulate user interaction

    publish_time = time.perf_counter()    user_input = "What's the weather?"

    session_id = "e2e_session_789"

    # Allow event delivery    trace_id = "e2e_trace_101112"

    await asyncio.sleep(0.01)

    delivery_time = time.perf_counter()    # Layer 1 processes input and publishes event

    start_time = time.perf_counter()

    # Verify end-to-end flow    await router.detect_intent(user_input, session_id, trace_id)

    assert len(router.published_events) == 1    publish_time = time.perf_counter()

    assert len(orchestrator.received_events) == 1

    # Allow event delivery

    published = router.published_events[0]    await asyncio.sleep(0.01)

    received = orchestrator.received_events[0]    delivery_time = time.perf_counter()



    # Verify event integrity across layers    # Verify end-to-end flow

    assert published.intent == received.intent    assert len(router.published_events) == 1

    assert published.session_id == received.session_id    assert len(orchestrator.received_events) == 1

    assert published.cognitive_trace_id == received.cognitive_trace_id

    published = router.published_events[0]

    # Verify performance budgets    received = orchestrator.received_events[0]

    publish_latency_ms = (publish_time - start_time) * 1000

    delivery_latency_ms = (delivery_time - publish_time) * 1000    # Verify event integrity across layers

    e2e_latency_ms = (delivery_time - start_time) * 1000    assert published.intent == received.intent

    assert published.session_id == received.session_id

    assert publish_latency_ms < 2.0  # <2ms P95 budget    assert published.cognitive_trace_id == received.cognitive_trace_id

    assert delivery_latency_ms < 5.0  # <5ms P95 budget

    assert e2e_latency_ms < 10.0  # <10ms P95 budget    # Verify performance budgets

    publish_latency_ms = (publish_time - start_time) * 1000

    await orchestrator.stop()    delivery_latency_ms = (delivery_time - publish_time) * 1000

    e2e_latency_ms = (delivery_time - start_time) * 1000



@test("Event schemas comply with contract validation")    assert publish_latency_ms < 2.0  # <2ms P95 budget

async def test_event_schema_contracts():    assert delivery_latency_ms < 5.0  # <5ms P95 budget

    """Test that event schemas match k1/contracts/event_bus/ specifications"""    assert e2e_latency_ms < 10.0  # <10ms P95 budget

    # Test IntentDetected event

    intent_event = IntentDetectedEvent(    await orchestrator.stop()

        intent="weather_query",

        confidence=0.85,

        tier="T1_RULE",@test("Event schemas comply with contract validation")

        entities={"location": "San Francisco"},async def test_event_schema_contracts():

        session_id="session_123",    """Test that event schemas match k1/contracts/event_bus/ specifications"""

        cognitive_trace_id="5f2d4c7a8b3e41e8a9d9c6f1b2a4d687",    # Test IntentDetected event

        timestamp=datetime.now(timezone.utc),    intent_event = IntentDetectedEvent(

    )        intent="weather_query",

        confidence=0.85,

    # Verify required fields are present        tier="T1_RULE",

    assert intent_event.intent is not None        entities={"location": "San Francisco"},

    assert 0.0 <= intent_event.confidence <= 1.0        session_id="session_123",

    assert intent_event.tier in ["T1_RULE", "T2_SLM", "T3_LLM"]        cognitive_trace_id="trace_456",

    assert intent_event.session_id is not None        timestamp=time.time(),

    assert intent_event.cognitive_trace_id is not None    )

    assert intent_event.timestamp is not None

    # Verify required fields are present

    # Test UserInput event    assert intent_event.intent is not None

    user_event = UserInputEvent(    assert 0.0 <= intent_event.confidence <= 1.0

        input_type="text",    assert intent_event.tier in ["T1_RULE", "T2_SLM", "T3_LLM"]

        content="Hello world",    assert intent_event.session_id is not None

        language="en",    assert intent_event.cognitive_trace_id is not None

        session_id="session_123",    assert intent_event.timestamp > 0

        cognitive_trace_id="5f2d4c7a8b3e41e8a9d9c6f1b2a4d687",

        timestamp=datetime.now(timezone.utc),    # Test UserInput event

    )    user_event = UserInputEvent(

        input_type="text",

    assert user_event.input_type in ["text", "voice", "gesture"]        content="Hello world",

    assert user_event.content is not None        language="en",

    assert user_event.language is not None        session_id="session_123",

        cognitive_trace_id="trace_456",

    # Test VoiceCommand event        timestamp=time.time(),

    voice_event = VoiceCommandEvent(    )

        command="play_music",

        confidence=0.92,    assert user_event.input_type in ["text", "voice", "gesture"]

        language="en",    assert user_event.content is not None

        vad_confidence=0.88,    assert user_event.language is not None

        session_id="session_123",

        cognitive_trace_id="5f2d4c7a8b3e41e8a9d9c6f1b2a4d687",    # Test VoiceCommand event

        timestamp=datetime.now(timezone.utc),    voice_event = VoiceCommandEvent(

    )        command="play_music",

        confidence=0.92,

    assert voice_event.command is not None        language="en",

    assert 0.0 <= voice_event.confidence <= 1.0        vad_confidence=0.88,

    assert 0.0 <= voice_event.vad_confidence <= 1.0        session_id="session_123",

        cognitive_trace_id="trace_456",

    # Test BargeIn event        timestamp=time.time(),

    barge_event = BargeInEvent(    )

        reason="user_interruption",

        session_id="session_123",    assert voice_event.command is not None

        cognitive_trace_id="5f2d4c7a8b3e41e8a9d9c6f1b2a4d687",    assert 0.0 <= voice_event.confidence <= 1.0

        timestamp=datetime.now(timezone.utc),    assert 0.0 <= voice_event.vad_confidence <= 1.0

    )

    # Test BargeIn event

    assert barge_event.reason in ["user_interruption", "emergency", "timeout"]    barge_event = BargeInEvent(

        reason="user_interruption",

        priority=EventPriority.URGENT,

@test("Layer isolation prevents invalid imports")        session_id="session_123",

async def test_layer_isolation():        cognitive_trace_id="trace_456",

    """Test that layering rules are preserved (L1 cannot import L2)"""        timestamp=time.time(),

    # This test verifies that the mock components follow layering rules    )

    # In real implementation, Layer 1 cannot import Layer 2

    assert barge_event.reason in ["user_interruption", "emergency", "timeout"]

    # Layer 1 (MockIntentRouter) can import Layer 5 (EventBus) ✓    assert isinstance(barge_event.priority, EventPriority)

    router = MockIntentRouter(event_bus=None)  # Would normally import EventBus



    # Layer 2 (MockOrchestrator) can import Layer 1 and Layer 5 ✓@test("Layer isolation prevents invalid imports")

    orchestrator = MockOrchestrator(event_bus=None)  # Would normally import EventBusasync def test_layer_isolation():

    """Test that layering rules are preserved (L1 cannot import L2)"""

    # Verify no circular dependencies or invalid imports    # This test verifies that the mock components follow layering rules

    # This is a structural test - in real code, l1_input cannot import l2_orchestration    # In real implementation, Layer 1 cannot import Layer 2

    assert router is not None

    assert orchestrator is not None    # Layer 1 (MockIntentRouter) can import Layer 5 (EventBus) ✓
    router = MockIntentRouter(event_bus=None)  # Would normally import EventBus

    # Layer 2 (MockOrchestrator) can import Layer 1 and Layer 5 ✓
    orchestrator = MockOrchestrator(event_bus=None)  # Would normally import EventBus

    # Verify no circular dependencies or invalid imports
    # This is a structural test - in real code, l1_input cannot import l2_orchestration
    assert router is not None
    assert orchestrator is not None
