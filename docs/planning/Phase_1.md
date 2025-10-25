# Phase 1: Layer 5 Infrastructure - Detailed Implementation Plan

**Duration:** 4 Weeks (Weeks 1-4)
**Team Size:** 2-3 Engineers
**Priority:** 🔴 CRITICAL - All other layers depend on this foundation

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Milestone 1: Week 1 - K0 Bridge Core](#milestone-1-week-1---k0-bridge-core)
4. [Milestone 2: Week 2 - Event Bus & Resilience](#milestone-2-week-2---event-bus--resilience)
5. [Milestone 3: Week 3 - Thermal & Observability](#milestone-3-week-3---thermal--observability)
6. [Milestone 4: Week 4 - Config & Connectors](#milestone-4-week-4---config--connectors)
7. [Testing Strategy](#testing-strategy)
8. [Success Criteria](#success-criteria)
9. [Reference Documentation](#reference-documentation)

---

## Overview

### Why Phase 1 First?

Layer 5 (Infrastructure) is the **foundation** of K1. Every other layer depends on these services:

- **K0 Bridge:** All K1→K0 communication (memory writes, queries, events)
- **Event Bus:** Layer 1→2 communication (intent routing)
- **Resilience:** Circuit breakers protect all external calls
- **Thermal:** Model placement for AI agents
- **Observability:** Metrics, tracing, logging for all layers
- **Config:** Global configuration management

**Zero Dependencies:** Layer 5 has no K1 dependencies (only K0 HTTP API and standard libraries).

### Performance Budgets

| Component | Budget | Why Critical |
|-----------|--------|--------------|
| K0 Command (GREEN) | <50ms P95 | Fast lane memory writes |
| K0 Command (AMBER/RED) | <200ms P95 | Smart lane with hippocampus |
| K0 Query | <100ms P95 | Memory recall for agents |
| Event Bus | <5ms P95 | L1→L2 intent routing |
| Circuit Breaker | <10ms | Failure detection |
| Thermal Placement | <10ms | Model placement decision |

---

## Prerequisites

### Development Environment

```powershell
# 1. Python 3.11+ installed
python --version  # Should be 3.11+

# 2. Install K0 dependencies (K0 must be running)
cd d:\familyos\k0
pip install -r requirements.txt

# 3. Start K0 kernel (separate terminal)
cd d:\familyos\k0
python -m k0.kernel.main

# 4. Verify K0 is running
curl http://localhost:5200/k0/health
# Expected: {"status": "healthy", "version": "1.0.0"}

# 5. Install K1 development dependencies
cd d:\familyos\k1
pip install httpx prometheus-client opentelemetry-api structlog pyyaml watchdog
```

### K0 Running Verification

```powershell
# Test K0 Command Port
curl -X POST http://localhost:5200/k0/command.submit `
  -H "Content-Type: application/json" `
  -d '{
    "cognitive_trace_id": "test-123",
    "tenant_id": "test",
    "space_id": "test",
    "topic": "test",
    "schema_uri": "test",
    "schema_version": "1.0",
    "actor": "test",
    "device_id": "test",
    "band": "GREEN",
    "policy_version": "1.0",
    "ts": "2025-10-24T00:00:00Z",
    "sig": "test",
    "payload": {}
  }'

# Test K0 Query Port
curl http://localhost:5201/k0/query.recall

# Test K0 SSE Port
curl http://localhost:5202/k0/sse.subscribe?topics=test
```

### Documentation to Read First

**CRITICAL - Read before coding:**

1. **ADR-0001a:** K0 Bridge Architecture
   - Location: `docs/architecture/decisions/0001a-k0-bridge-communication-protocol.md`
   - Focus: Dual-protocol (JSON/FlatBuffers), 4 ports, lane processing

2. **Layer 5 ADR Map:** Complete module reference
   - Location: `k1/l5_infrastructure/layer5_adr_map.md`
   - Focus: All 19 modules, ADR references, performance budgets

3. **K0 Ports Implementation:** Actual K0 code
   - Location: `k0/ports/command.py`, `k0/ports/query.py`, `k0/ports/sse.py`
   - Focus: Request/response schemas, error handling

4. **K0 Contracts:** API schemas
   - Location: `k0/contracts/openapi.k0.yaml`, `k0/contracts/jsonschema/*.json`
   - Focus: Envelope schemas, receipt schemas, error schemas

---

## Milestone 1: Week 1 - K0 Bridge Core

**Goal:** Implement K0 Bridge clients for Command, Query, SSE ports
**Duration:** 5 days
**Unlocks:** All K1→K0 communication (memory writes, queries, events)

### Epic 1.1: K0 Command Client (Priority: 🔴 CRITICAL)

**Purpose:** Write operations to K0 (memory formation, plan persistence)
**Files:** `k1/l5_infrastructure/bridge_k0/command_client.py`
**Performance:** <50ms P95 (GREEN), <200ms P95 (AMBER/RED)

#### Issue 1.1.1: Command Client Core Implementation

**Story:** As a K1 agent, I need to write memories to K0 so that user memories persist

**Acceptance Criteria:**

- [ ] HTTP POST to K0 Command Port (`:5200/v1/command`)
- [ ] JSON envelope serialization (PRIMARY format)
- [ ] Lane processing: Fast Lane (GREEN) vs Smart Lane (AMBER/RED)
- [ ] Receipt validation (WAL offset, timestamp)
- [ ] Idempotency keys (UUIDv7)
- [ ] HTTP/2 connection pooling

**Implementation Steps:**

1. **Read K0 command.py implementation**

   ```powershell
   # Context: K0 Command Port implementation
   code d:\familyos\k0\ports\command.py
   ```

2. **Read K0 envelope schema**

   ```powershell
   # Context: Envelope JSON schema
   code d:\familyos\k0\contracts\jsonschema\envelope.schema.json
   ```

3. **Create command_client.py skeleton**

   ```python
   # File: k1/l5_infrastructure/bridge_k0/command_client.py
   """
   K0 Command Port Client - Write operations (memory formation, plan persistence)

   ADRs: ADR-0001a (K0 Bridge), ADR-0024 (Performance Budgets)
   K0 Reference: k0/ports/command.py (K0 implementation)
   Contracts: k0/contracts/jsonschema/envelope.schema.json

   Performance Budget:
   - GREEN band: <50ms P95
   - AMBER/RED band: <200ms P95
   """

   import httpx
   import uuid
   from datetime import datetime, timezone
   from typing import Dict, Any, Literal
   from dataclasses import dataclass

   @dataclass
   class CommandEnvelope:
       """K0 Command envelope (mirrors k0/contracts/jsonschema/envelope.schema.json)"""
       cognitive_trace_id: str
       tenant_id: str
       space_id: str
       topic: str
       schema_uri: str
       schema_version: str
       actor: str
       device_id: str
       band: Literal["GREEN", "AMBER", "RED"]
       policy_version: str
       ts: str
       sig: str
       payload: Dict[str, Any]
       idem_key: str | None = None

   class K0CommandClient:
       """
       K0 Command Port client (write operations)

       Research: REST API Design (Fielding 2000), HTTP/2 (RFC 7540)
       """

       def __init__(self, base_url: str = "http://localhost:5200"):
           self.base_url = base_url
           self.client = httpx.AsyncClient(http2=True, timeout=10.0)

       async def submit_command(self, envelope: CommandEnvelope) -> Dict[str, Any]:
           """
           Submit command to K0 Command Port

           Args:
               envelope: Command envelope (see k0/contracts/jsonschema/envelope.schema.json)

           Returns:
               Receipt (see k0/contracts/jsonschema/receipt.schema.json)

           Raises:
               K0CommandError: On K0 rejection (400, 403, 409, 429)
           """
           # TODO: Implement HTTP POST to /k0/command.submit
           pass
   ```

4. **Implement HTTP POST logic**
   - Reference: `k0/ports/command.py` line 100-150
   - Use `httpx.AsyncClient` for HTTP/2
   - POST to `/k0/command.submit`
   - Handle 200 (success), 409 (idempotent duplicate), 4xx/5xx errors

5. **Add lane processing**
   - GREEN band: Fast lane (<50ms target)
   - AMBER/RED band: Smart lane (<200ms target)
   - Set `qos_band` in envelope

6. **Add receipt validation**
   - Verify `receipt_id` in response
   - Check `commit_ts` is recent
   - Validate `offsets` are monotonic

7. **Write unit tests**

   ```python
   # File: tests/k1/l5_infrastructure/bridge_k0/test_command_client.py
   import pytest
   from k1.l5_infrastructure.bridge_k0.command_client import K0CommandClient, CommandEnvelope

   @pytest.mark.asyncio
   async def test_submit_command_green_band():
       """Test GREEN band command submission (<50ms)"""
       client = K0CommandClient()
       envelope = CommandEnvelope(
           cognitive_trace_id=str(uuid.uuid4()),
           tenant_id="test",
           space_id="test",
           topic="memory.write",
           schema_uri="familyos://schemas/memory/v1",
           schema_version="1.0",
           actor="user_dad",
           device_id="device_dad_phone",
           band="GREEN",
           policy_version="1.0",
           ts=datetime.now(timezone.utc).isoformat(),
           sig="test_signature",
           payload={"content": "Test memory"}
       )

       receipt = await client.submit_command(envelope)
       assert receipt["receipt_id"]
       assert receipt["commit_ts"]
   ```

**Time Estimate:** 2 days

---

#### Issue 1.1.2: Command Client Error Handling

**Story:** As a K1 developer, I need proper error handling so failures are graceful

**Acceptance Criteria:**

- [ ] Handle 400 (Minimal Gate rejection)
- [ ] Handle 403 (PEP deny)
- [ ] Handle 409 (Idempotent duplicate - return existing receipt)
- [ ] Handle 429 (QoS budget exhausted)
- [ ] Handle 5xx (K0 unavailable)
- [ ] Exponential backoff retry (3 attempts: 100ms→400ms→1600ms)

**Implementation Steps:**

1. **Read K0 error schemas**

   ```powershell
   code d:\familyos\k0\contracts\jsonschema\error.schema.json
   ```

2. **Create K0 exception hierarchy**

   ```python
   # File: k1/l5_infrastructure/bridge_k0/exceptions.py
   class K0BridgeError(Exception):
       """Base exception for K0 Bridge errors"""
       pass

   class K0CommandRejected(K0BridgeError):
       """K0 rejected command (400 Minimal Gate)"""
       pass

   class K0PolicyDenied(K0BridgeError):
       """K0 PEP denied command (403)"""
       pass

   class K0IdempotentDuplicate(K0BridgeError):
       """Command already committed (409)"""
       def __init__(self, receipt):
           self.receipt = receipt

   class K0QoSExhausted(K0BridgeError):
       """QoS budget exhausted (429)"""
       pass

   class K0Unavailable(K0BridgeError):
       """K0 unavailable (5xx)"""
       pass
   ```

3. **Implement retry logic**

   ```python
   async def _retry_with_backoff(self, operation, max_retries=3):
       """Exponential backoff: 100ms → 400ms → 1600ms"""
       for attempt in range(max_retries):
           try:
               return await operation()
           except K0Unavailable:
               if attempt == max_retries - 1:
                   raise
               await asyncio.sleep(0.1 * (4 ** attempt))  # 100, 400, 1600ms
       ```

4. **Add error response parsing**
   - Reference: `k0/ports/errors.py`
   - Parse error envelope
   - Map HTTP status to exception type

**Time Estimate:** 1 day

---

#### Issue 1.1.3: Command Client Observability

**Story:** As a DevOps engineer, I need metrics/logs to monitor K0 Bridge

**Acceptance Criteria:**

- [ ] Prometheus metrics: `k0_command_requests_total`, `k0_command_latency_ms`
- [ ] Structured logging (JSON format)
- [ ] `cognitive_trace_id` propagation
- [ ] Log request/response on error

**Implementation note (recommended):**

K1 should reuse K0's proven observability primitives rather than creating a parallel stack. The K0 package exposes a small, well-tested observability surface (`k0.obs.metrics.MetricsExporter`, `k0.obs.tracing.TracerFactory` and an optional `ObservabilityEmitter`) that integrates with Prometheus, Tempo (OTLP) and Grafana. Reusing these primitives ensures consistent naming, common OTLP endpoints, and end-to-end `cognitive_trace_id` propagation between K1 and K0.

**Implementation Steps (preferred approach):**

1. Import and initialise K0 observability primitives in K1:

   ```python
   # Use K0's MetricsExporter and TracerFactory to avoid duplication
   from k0.obs.metrics import MetricsExporter
   from k0.obs.tracing import TracerFactory

   metrics = MetricsExporter(namespace="k1_intelligence")
   tracer = TracerFactory(
       service_name="k1_intelligence",
       service_version="1.0.0",
       environment="dev",
       otlp_endpoint="http://localhost:4318/v1/traces",
   )
   ```

2. Define K1-specific metrics using the `MetricsExporter` (K1 namespace):

   - `k1_intelligence_command_requests_total` (labels: `band`, `status`)
   - `k1_intelligence_command_latency_ms` (histogram, labels: `band`, buckets as in K0)

   These metrics will be registered with the same Prometheus server (9090) used by K0.

3. Instrument `K0CommandClient.submit_command` to emit metrics and spans, and log structured events using the existing structlog configuration. Ensure `cognitive_trace_id` is attached to OpenTelemetry baggage before starting spans so traces correlate across K1→K0.

4. Expose metrics via the same Prometheus scrape endpoint (reuse K0's exporter or register K1 metrics with a shared registry). Coordinate scrape targets and dashboard panels in Grafana to include both `k0_kernel` and `k1_intelligence` namespaces.

**Acceptance Criteria (updated):**

- [ ] K1 uses `k0.obs` primitives for metrics and tracing
- [ ] K1 exposes `k1_intelligence_command_requests_total` and `k1_intelligence_command_latency_ms`
- [ ] `cognitive_trace_id` is propagated through spans and logs from K1 into K0

**Time Estimate:** 0.25 days (integration + dashboard updates)

---

### Epic 1.2: K0 Query Client (Priority: 🔴 CRITICAL)

**Purpose:** Read operations from K0 (memory recall, knowledge graph queries)
**Files:** `k1/l5_infrastructure/bridge_k0/query_client.py`
**Performance:** <100ms P95

#### Issue 1.2.1: Query Client Core Implementation

**Story:** As a K1 agent, I need to query memories from K0 for context assembly

**Acceptance Criteria:**

- [ ] HTTP POST to K0 Query Port (`:5201/v1/query`)
- [ ] Multi-store retrieval (FTS5, FAISS, KG, Episodic)
- [ ] Fusion strategy (MMR, RRF)
- [ ] Top-k selection (default: 20 results)

**Implementation Steps:**

1. **Read K0 query.py implementation**

   ```powershell
   code d:\familyos\k0\ports\query.py
   ```

2. **Read query schemas**

   ```powershell
   code d:\familyos\k0\contracts\jsonschema\query.recall.request.json
   code d:\familyos\k0\contracts\jsonschema\query.recall.response.json
   ```

3. **Create query_client.py**

   ```python
   # File: k1/l5_infrastructure/bridge_k0/query_client.py
   """
   K0 Query Port Client - Read operations (memory recall, KG queries)

   ADRs: ADR-0001a (K0 Bridge), ADR-0024 (Performance Budgets)
   K0 Reference: k0/ports/query.py
   Contracts: k0/contracts/jsonschema/query.recall.request.json

   Performance Budget: <100ms P95
   """

   from typing import List, Dict, Any
   from dataclasses import dataclass

   @dataclass
   class RecallSelector:
       """Query selector (see k0/contracts/jsonschema/query.recall.request.json)"""
       type: str | None = None  # episodic, semantic, procedural
       topic: str | None = None
       limit: int = 20
       query: str | None = None

   @dataclass
   class RecallRequest:
       """Query request"""
       selectors: List[RecallSelector]
       space_id: str
       tenant_id: str
       max_latency_ms: int = 100

   class K0QueryClient:
       """K0 Query Port client"""

       async def recall(self, request: RecallRequest) -> Dict[str, Any]:
           """
           Query K0 for memories

           Returns:
               bundle: {results: [...], trace: {...}, budgets: {...}}
           """
           # TODO: Implement HTTP POST to /k0/query.recall
           pass
   ```

4. **Implement recall logic**
   - POST to `/k0/query.recall`
   - Handle bundle response (results, trace, budgets)
   - Parse multi-store results

5. **Write unit tests**

   ```python
   @pytest.mark.asyncio
   async def test_recall_episodic_memories():
       """Test episodic memory recall"""
       client = K0QueryClient()
       request = RecallRequest(
           selectors=[RecallSelector(type="episodic", limit=10)],
           space_id="test",
           tenant_id="test"
       )

       bundle = await client.recall(request)
       assert "results" in bundle
       assert len(bundle["results"]) <= 10
   ```

**Time Estimate:** 1 day

---

### Epic 1.3: K0 SSE Client (Priority: 🔴 CRITICAL)

**Purpose:** Event streaming from K0 (memory updates, consolidation events)
**Files:** `k1/l5_infrastructure/bridge_k0/sse_client.py`
**Performance:** <5ms event delivery

#### Issue 1.3.1: SSE Client Core Implementation

**Story:** As a K1 agent, I need real-time K0 events for coordination

**Acceptance Criteria:**

- [ ] HTTP GET to K0 SSE Port (`:5202/v1/events`)
- [ ] EventSource client (SSE protocol)
- [ ] Topic-based filtering
- [ ] Reconnection logic (exponential backoff)
- [ ] Cursor-based resume (Last-Event-ID)

**Implementation Steps:**

1. **Read K0 sse.py implementation**

   ```powershell
   code d:\familyos\k0\ports\sse.py
   ```

2. **Create sse_client.py**

   ```python
   # File: k1/l5_infrastructure/bridge_k0/sse_client.py
   """
   K0 SSE Port Client - Event streaming (real-time K0 updates)

   ADRs: ADR-0001a (K0 Bridge), ADR-0042 (SSE Event Streaming)
   K0 Reference: k0/ports/sse.py

   Performance Budget: <5ms event delivery
   """

   import httpx
   from typing import AsyncIterator, Dict, Any, List

   class K0SSEClient:
       """K0 SSE Port client (event streaming)"""

       def __init__(self, base_url: str = "http://localhost:5202"):
           self.base_url = base_url

       async def subscribe(
           self,
           topics: List[str],
           subscriber_id: str,
           cursor: str | None = None
       ) -> AsyncIterator[Dict[str, Any]]:
           """
           Subscribe to K0 events

           Args:
               topics: Event topics to subscribe to
               subscriber_id: Unique subscriber ID
               cursor: Resume from cursor (Last-Event-ID)

           Yields:
               Event: {id, event, data, retry}
           """
           # TODO: Implement SSE subscription
           pass
   ```

3. **Implement SSE subscription**
   - GET to `/k0/sse.subscribe?topics=topic1,topic2`
   - Add `X-SSE-Subscriber` header
   - Parse SSE events (id, event, data fields)
   - Handle reconnection with Last-Event-ID

4. **Write integration test**

   ```python
   @pytest.mark.asyncio
   async def test_sse_subscription():
       """Test SSE event subscription"""
       client = K0SSEClient()

       events = []
       async for event in client.subscribe(topics=["test"], subscriber_id="test-sub"):
           events.append(event)
           if len(events) >= 5:
               break

       assert len(events) == 5
   ```

**Time Estimate:** 1.5 days

---

### Epic 1.4: Batch Client & Observability Client

**Purpose:** Delta batching and telemetry push

#### Issue 1.4.1: Batch Client (SessionState deltas)

**Story:** As K1 runtime, I need to batch SessionState deltas for efficiency

**Files:** `k1/l5_infrastructure/bridge_k0/batch_client.py`
**Performance:** <10ms per batch

**Implementation:**

- 250ms flush interval OR 64KB size trigger
- Field-level deltas: `(field_path, old_value, new_value)`
- 80% reduction in K0 writes

**Time Estimate:** 1 day

#### Issue 1.4.2: Observability Client (metrics/logs push)

**Story:** As DevOps, I need K1 telemetry pushed to K0

**Files:** `k1/l5_infrastructure/bridge_k0/observability_client.py`
**Performance:** <20ms

**Implementation:**

- Metric batch: 10s interval
- Log batch: 5s interval
- Push to K0 Observability Port

**Time Estimate:** 0.5 days

---

## Milestone 2: Week 2 - Event Bus & Resilience

**Goal:** Implement Event Bus (L1→L2 communication) and Circuit Breakers
**Duration:** 5 days
**Unlocks:** Cross-layer communication, fault tolerance

### Epic 2.1: Event Bus (Priority: 🔴 CRITICAL)

**Purpose:** Pub/sub messaging for Layer 1 → Layer 2
**Files:** `k1/l5_infrastructure/event_bus/event_bus.py`
**Performance:** <5ms P95 event delivery
very (non-blocking)

- [ ] Backpressure handling (queue depth 50, DROP_OLDEST policy)

**Context Files:**

- **ADR:** `docs/architecture/decisions/0004a-layer1-2-event-bus-communication.md`
- **K0 Event Bus:** `k0/bus/core.py` (inspiration, not dependency)

**Implementation Steps:**

1. **Read ADR-0004a**

   ```powershell
   code d:\familyos\docs\architecture\decisions\0004a-layer1-2-event-bus-communication.md
   ```

2. **Create event_bus.py**

   ```python
   # File: k1/l5_infrastructure/event_bus/event_bus.py
   """
   Event Bus - Pub/Sub for Layer 1→2 communication

   ADRs: ADR-0004a (Event Bus), ADR-0004 (5-Layer Architecture)
   Inspiration: k0/bus/core.py (NOT a dependency)

   Performance Budget: <5ms P95 event delivery
   """

   from enum import Enum
   from typing import Dict, List, Callable, Any
   from dataclasses import dataclass
   import asyncio

   class EventTopic(Enum):
       """Event topics (Layer 1 → Layer 2)"""
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
       Event Bus: Pub/Sub for cross-layer communication

       Research: Enterprise Integration Patterns (Hohpe & Woolf 2003)
       """

       def __init__(self):
           self._subscribers: Dict[EventTopic, List[Callable]] = {}
           self._queue_depth = 50
           self._queues: Dict[EventTopic, asyncio.Queue] = {}

       def subscribe(self, topic: EventTopic, handler: Callable):
           """Subscribe to topic"""
           if topic not in self._subscribers:
               self._subscribers[topic] = []
               self._queues[topic] = asyncio.Queue(maxsize=self._queue_depth)
           self._subscribers[topic].append(handler)

       async def publish(self, event: Event):
           """Publish event to topic (non-blocking)"""
           if event.topic not in self._queues:
               return

           queue = self._queues[event.topic]
           if queue.full():
               # Backpressure: DROP_OLDEST
               await queue.get()

           await queue.put(event)

       async def _deliver_events(self, topic: EventTopic):
           """Event delivery loop (background task)"""
           queue = self._queues[topic]
           while True:
               event = await queue.get()
               for handler in self._subscribers[topic]:
                   await handler(event)
   ```

3. **Add metrics**

   ```python
   from prometheus_client import Counter, Histogram

   event_bus_publish_total = Counter(
       "event_bus_publish_total",
       "Total events published",
       ["topic", "status"]
   )

   event_bus_latency_ms = Histogram(
       "event_bus_latency_ms",
       "Event delivery latency (ms)",
       ["topic"],
       buckets=[1, 2, 5, 10, 25, 50]
   )
   ```

**Time Estimate:** 2 days

#### Issue 2.1.1: Event Bus Core

**Story:** As Layer 1, I need to publish intent events to Layer 2

**Acceptance Criteria:**

- [ ] Topic-based pub/sub
- [ ] Topics: `INTENT_DETECTED`, `USER_INPUT`, `VOICE_COMMAND`, `BARGE_IN`
- [ ] Zero-copy delivery (shared buffer)
- [ ] Async deli

---

#### Issue 2.1.2: Event Schemas

**Story:** As K1 developer, I need event schema definitions

**Files:** `k1/l5_infrastructure/event_bus/schemas.py`

**Implementation:**

```python
# File: k1/l5_infrastructure/event_bus/schemas.py
"""Event schema definitions"""

from dataclasses import dataclass
from typing import Dict, Any

@dataclass
class IntentDetectedEvent:
    """Intent detection event (L1 → L2)"""
    intent: str  # "weather_query", "calendar_add", etc.
    confidence: float  # 0.0-1.0
    tier: str  # "T1_RULE", "T2_SLM", "T3_LLM"
    entities: Dict[str, Any]  # Extracted entities
    session_id: str
    cognitive_trace_id: str

@dataclass
class UserInputEvent:
    """User input event"""
    text: str
    modality: str  # "text", "voice"
    session_id: str
    cognitive_trace_id: str
```

**Time Estimate:** 0.5 days

---

### Epic 2.2: Circuit Breaker (Priority: 🟡 HIGH)

**Purpose:** Prevent cascading failures for external calls
**Files:** `k1/l5_infrastructure/resilience/circuit_breaker.py`
**Performance:** <10ms state check

#### Issue 2.2.1: Circuit Breaker Core

**Story:** As K1 agent, I need circuit breakers to protect external API calls

**Acceptance Criteria:**

- [ ] 3-state FSM: CLOSED → OPEN → HALF-OPEN
- [ ] Failure threshold: 3 failures → OPEN
- [ ] Timeout: 60s (OPEN → HALF-OPEN)
- [ ] Probe: 1 success → CLOSED
- [ ] Per-service circuit breakers

**Context Files:**

- **ADR:** `docs/architecture/decisions/0009-circuit-breaker-pattern.md`
- **FSM ADR:** `docs/architecture/decisions/0009a-circuit-breaker-fsm-implementation.md`

**Implementation Steps:**

1. **Read ADR-0009**

   ```powershell
   code d:\familyos\docs\architecture\decisions\0009-circuit-breaker-pattern.md
   ```

2. **Create circuit_breaker.py**

   ```python
   # File: k1/l5_infrastructure/resilience/circuit_breaker.py
   """
   Circuit Breaker Pattern - Cascading failure prevention

   ADRs: ADR-0009 (Circuit Breaker), ADR-0009a (FSM Implementation)
   Research: Nygard 2007 (Release It!), Netflix Hystrix 2012

   Performance Budget: <10ms state check
   """

   from enum import Enum
   from dataclasses import dataclass
   import time

   class CircuitState(Enum):
       """Circuit breaker states"""
       CLOSED = "CLOSED"        # Normal operation
       OPEN = "OPEN"            # Failing, reject calls
       HALF_OPEN = "HALF_OPEN"  # Testing, allow 1 probe

   @dataclass
   class CircuitBreakerConfig:
       """Circuit breaker configuration"""
       failure_threshold: int = 3       # Open after 3 failures
       timeout_s: float = 60.0          # Half-open after 60s
       success_threshold: int = 1       # Close after 1 success
       name: str = "circuit_breaker"

   class CircuitBreaker:
       """
       Circuit breaker pattern (Nygard 2007)

       Prevents cascading failures by:
       1. Tracking failure count
       2. Opening circuit when threshold reached (fail-fast)
       3. Periodically probing service (half-open)
       4. Closing circuit when service recovers
       """

       def __init__(self, config: CircuitBreakerConfig):
           self.config = config
           self.state = CircuitState.CLOSED
           self.failure_count = 0
           self.last_failure_time = None

       def call(self, operation):
           """Execute operation through circuit breaker"""
           if self.state == CircuitState.OPEN:
               if self._should_attempt_reset():
                   self.state = CircuitState.HALF_OPEN
               else:
                   raise CircuitBreakerOpen(f"{self.config.name} circuit open")

           try:
               result = operation()
               self._on_success()
               return result
           except Exception as e:
               self._on_failure()
               raise

       def _should_attempt_reset(self) -> bool:
           """Check if timeout elapsed for half-open probe"""
           if self.last_failure_time is None:
               return False
           elapsed = time.time() - self.last_failure_time
           return elapsed >= self.config.timeout_s

       def _on_success(self):
           """Handle successful operation"""
           if self.state == CircuitState.HALF_OPEN:
               self.state = CircuitState.CLOSED
               self.failure_count = 0

       def _on_failure(self):
           """Handle failed operation"""
           self.failure_count += 1
           self.last_failure_time = time.time()

           if self.failure_count >= self.config.failure_threshold:
               self.state = CircuitState.OPEN

   class CircuitBreakerOpen(Exception):
       """Exception raised when circuit is open"""
       pass
   ```

3. **Write unit tests**

   ```python
   def test_circuit_breaker_opens_after_threshold():
       """Test circuit opens after 3 failures"""
       cb = CircuitBreaker(CircuitBreakerConfig(failure_threshold=3))

       # 3 failures → circuit opens
       for _ in range(3):
           with pytest.raises(Exception):
               cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))

       assert cb.state == CircuitState.OPEN

       # Next call rejected immediately
       with pytest.raises(CircuitBreakerOpen):
           cb.call(lambda: "success")
   ```

**Time Estimate:** 1.5 days

---

### Epic 2.3: Retry Policy & Hot Reload

#### Issue 2.3.1: Retry Policy

**Story:** As K1 developer, I need retry logic for transient failures

**Files:** `k1/l5_infrastructure/resilience/retry_policy.py`

**Implementation:**

- Exponential backoff: 100ms → 400ms → 1600ms
- Max 3 retries
- 20% jitter (prevent thundering herd)

**Time Estimate:** 1 day

#### Issue 2.3.2: Hot Reload

**Story:** As DevOps, I need config hot reload without restart

**Files:** `k1/l5_infrastructure/resilience/hot_reload.py`

**Implementation:**

- Watch `circuit_breaker.yaml`, `retry_policy.yaml`
- Async reload on file change
- <100ms reload latency

**Time Estimate:** 0.5 days

---

## Milestone 3: Week 3 - Thermal & Observability

**Goal:** Implement thermal management and observability stack
**Duration:** 5 days
**Unlocks:** Model placement, performance monitoring

### Epic 3.1: Thermal Management (Priority: 🟡 HIGH)

**Purpose:** Thermal-aware model placement (NPU→GPU→CPU→Remote)
**Files:** `k1/l5_infrastructure/thermal/`
**Performance:** <10ms placement decision

#### Issue 3.1.1: Thermal Monitor

**Story:** As K1, I need to monitor NPU/GPU/CPU temperatures

**Files:** `k1/l5_infrastructure/thermal/monitor.py`

**Context Files:**

- **ADR:** `docs/architecture/decisions/0026-thermal-hysteresis-matrix.md`
- **Sensor ADR:** `docs/architecture/decisions/0026a-thermal-sensor-monitoring-state-detection.md`

**Implementation:**

```python
# File: k1/l5_infrastructure/thermal/monitor.py
"""
Thermal Monitor - Temperature sensor polling

ADRs: ADR-0026 (Thermal Hysteresis), ADR-0026a (Sensor Monitoring)
Performance Budget: <5ms per reading
"""

import platform
from typing import Dict

class ThermalMonitor:
    """Thermal sensor monitoring"""

    def __init__(self):
        self.platform = platform.system()

    def get_temperatures(self) -> Dict[str, float]:
        """
        Get current temperatures (°C)

        Returns:
            {"npu": 72.0, "gpu": 68.0, "cpu": 65.0}
        """
        if self.platform == "Windows":
            return self._get_temperatures_windows()
        elif self.platform == "Linux":
            return self._get_temperatures_linux()
        else:
            return self._get_temperatures_mock()

    def _get_temperatures_windows(self) -> Dict[str, float]:
        """Read Windows thermal sensors (WMI)"""
        # TODO: Use WMI to read temperatures
        # Reference: wmi.WMI().MSAcpi_ThermalZoneTemperature()
        pass

    def _get_temperatures_linux(self) -> Dict[str, float]:
        """Read Linux thermal sensors (/sys/class/thermal)"""
        # TODO: Read from /sys/class/thermal/thermal_zone*/temp
        pass

    def _get_temperatures_mock(self) -> Dict[str, float]:
        """Mock temperatures for testing"""
        return {"npu": 70.0, "gpu": 68.0, "cpu": 65.0}
```

**Time Estimate:** 1 day

---

#### Issue 3.1.2: Placement Planner

**Story:** As Model Hub, I need thermal-aware placement decisions

**Files:** `k1/l5_infrastructure/thermal/placement_planner.py`

**Implementation:**

- 4-tier cascade: NPU (30ms, 10W) → GPU (50ms, 12W) → CPU (120ms, 15W) → Remote (500ms, 5W)
- Asymmetric hysteresis: Upgrade +5°C, downgrade -2°C
- Cooldown periods: Upgrade 10s, downgrade 30s
- Emergency jump: ≥85°C → Remote

**Time Estimate:** 1.5 days

---

### Epic 3.2: Observability Stack (Priority: 🔴 CRITICAL)

**Purpose:** Metrics, tracing, logging for all K1 layers

#### Observability strategy (reuse K0 infrastructure)

K1 should integrate with the existing K0 observability infrastructure rather than rebuilding it. K0 already provides a robust observability surface (`k0.obs.metrics.MetricsExporter`, `k0.obs.tracing.TracerFactory` and an `ObservabilityEmitter`) that registers to the shared Prometheus/Tempo/Grafana stack. The work for K1 is therefore primarily integration, defining K1-specific metrics, ensuring trace/log correlation, and updating Grafana dashboards.

#### Issue 3.2.1: Prometheus Metrics (K1 integration)

**Story:** As DevOps, I need K1 metrics available in the same Prometheus instance as K0 for unified monitoring

**Files:** `k1/l5_infrastructure/observability/` (integration glue; prefer importing `k0.obs`)

**Implementation:**

- Import and initialise `k0.obs.metrics.MetricsExporter(namespace="k1_intelligence")` in K1 services
- Define K1-specific metrics (examples):
  - `k1_intelligence_command_requests_total{band, status}`
  - `k1_intelligence_command_latency_ms{band}` (histogram using same buckets as K0)
  - Agent lifecycle metrics, query latencies, SSE event rates
- Register K1 metrics with the shared Prometheus registry (or expose a combined scrape endpoint)
- Collaborate with the platform team to add K1 panels to the existing Grafana dashboards (reuse K0 panels as templates)

**Time Estimate:** 0.5 days

#### Issue 3.2.2: OpenTelemetry Tracing (K1 integration)

**Story:** As developer, I need distributed tracing that correlates K1 and K0 spans

**Files:** small glue in `k1/l5_infrastructure/observability/tracing.py` that reuses `k0.obs.tracing.TracerFactory`

**Implementation:**

- Initialise `TracerFactory(service_name="k1_intelligence", ...)` using the same OTLP endpoint as K0
- Ensure `cognitive_trace_id` is attached to baggage before creating spans so K1 spans correlate with K0 spans
- Use the same sampling and export configuration (controlled centrally by K0 ops)

**Time Estimate:** 0.5 days

#### Issue 3.2.3: Structured Logging (K1 integration)

**Story:** As developer, I need structured logs that include `cognitive_trace_id` and match the cluster logging format

**Files:** `k1/l5_infrastructure/observability/logging.py` (lightweight glue)

**Implementation:**

- Reuse the project's `structlog` configuration and ensure `cognitive_trace_id` is added to log context (pull from OpenTelemetry baggage)
- Keep log schema compatible with existing K0 log parsers/dashboards

**Time Estimate:** 0.25 days

---

## Milestone 4: Week 4 - Config & Connectors

**Goal:** Configuration management and connector lifecycle
**Duration:** 5 days
**Unlocks:** Global config, connection pooling

### Epic 4.1: Configuration Management

#### Issue 4.1.1: Config Loader

**Story:** As K1, I need to load YAML configuration files

**Files:** `k1/l5_infrastructure/config/loader.py`

**Implementation:**

- Load from `k1/config/*.yml`
- Schema validation (JSON Schema)
- Environment variable override

**Time Estimate:** 1 day

#### Issue 4.1.2: Config Manager (Hot Reload)

**Story:** As DevOps, I need config updates without restart

**Files:** `k1/l5_infrastructure/config/config_manager.py`

**Implementation:**

- Watch config files for changes
- Trigger reload on change
- <100ms reload latency

**Time Estimate:** 1 day

---

### Epic 4.2: Connectors

#### Issue 4.2.1: K0 Connector (Connection Lifecycle)

**Story:** As K1, I need K0 connection pooling

**Files:** `k1/l5_infrastructure/connectors/k0_connector.py`

**Implementation:**

- HTTP/2 connection pool (5 connections)
- Connection health checks
- >90% pool hit rate

**Time Estimate:** 1 day

#### Issue 4.2.2: Model Hub Client (Placeholder)

**Story:** As L3, I need Model Hub interface

**Files:** `k1/l5_infrastructure/connectors/model_hub_client.py`

**Implementation:**

- Placeholder interface (implemented in Phase 4)
- Type definitions

**Time Estimate:** 0.5 days

---

## Testing Strategy

### Unit Tests (Per Issue)

**Coverage Target:** >80%

```powershell
# Run unit tests
cd d:\familyos
python -m ward test --path tests/k1/l5_infrastructure/

# Coverage report
python -m ward test --path tests/k1/l5_infrastructure/ --coverage
```

### Integration Tests (Per Epic)

**Test K0 Integration:**

```python
# File: tests/k1/l5_infrastructure/integration/test_k0_bridge.py

@pytest.mark.integration
async def test_k0_bridge_end_to_end():
    """Test full K0 Bridge workflow (command → query → sse)"""

    # 1. Write memory via Command Port
    command_client = K0CommandClient()
    envelope = CommandEnvelope(...)
    receipt = await command_client.submit_command(envelope)

    # 2. Query memory via Query Port
    query_client = K0QueryClient()
    request = RecallRequest(...)
    bundle = await query_client.recall(request)
    assert len(bundle["results"]) > 0

    # 3. Receive event via SSE Port
    sse_client = K0SSEClient()
    async for event in sse_client.subscribe(topics=["memory.write"], ...):
        assert event["data"]["receipt_id"] == receipt["receipt_id"]
        break
```

### Performance Tests (Per Milestone)

**Test Performance Budgets:**

```python
@pytest.mark.performance
async def test_k0_command_latency_green_band():
    """Test K0 command latency <50ms P95 (GREEN band)"""

    client = K0CommandClient()
    latencies = []

    for _ in range(100):
        start = time.time()
        await client.submit_command(envelope)
        latency = (time.time() - start) * 1000
        latencies.append(latency)

    p95 = np.percentile(latencies, 95)
    assert p95 < 50, f"P95 latency {p95}ms exceeds 50ms budget"
```

---

## Success Criteria

### Week 1: K0 Bridge Core

- [ ] Command client: 200+ writes, <50ms P95 (GREEN)
- [ ] Query client: 100+ queries, <100ms P95
- [ ] SSE client: Receive 1000+ events, <5ms delivery
- [ ] All unit tests passing (>80% coverage)
- [ ] Integration test: Write→Query→SSE workflow

### Week 2: Event Bus & Resilience

- [ ] Event bus: 1000+ events/sec, <5ms P95
- [ ] Circuit breaker: Opens after 3 failures, closes after recovery
- [ ] Retry policy: 3 retries with exponential backoff
- [ ] All unit tests passing

### Week 3: Thermal & Observability

- [ ] Thermal monitor: Read NPU/GPU/CPU temps
- [ ] Placement planner: 4-tier cascade decisions
- [ ] Prometheus: 50+ metrics exposed
- [ ] Tracing: `cognitive_trace_id` propagation
- [ ] Logging: Structured JSON logs

### Week 4: Config & Connectors

- [ ] Config loader: Load all YAML files
- [ ] Config manager: Hot reload <100ms
- [ ] K0 connector: Connection pool >90% hit rate
- [ ] All integration tests passing

---

## Reference Documentation

### Must Read Before Starting

1. **ADR-0001a:** K0 Bridge Architecture
   - `docs/architecture/decisions/0001a-k0-bridge-communication-protocol.md`

2. **Layer 5 ADR Map:** Complete module reference
   - `k1/l5_infrastructure/layer5_adr_map.md`

3. **ADR-0004a:** Event Bus Communication
   - `docs/architecture/decisions/0004a-layer1-2-event-bus-communication.md`

4. **ADR-0009:** Circuit Breaker Pattern
   - `docs/architecture/decisions/0009-circuit-breaker-pattern.md`

5. **ADR-0026:** Thermal Hysteresis Matrix
   - `docs/architecture/decisions/0026-thermal-hysteresis-matrix.md`

### K0 Code References

1. **K0 Ports:** HTTP handlers
   - `k0/ports/command.py`, `k0/ports/query.py`, `k0/ports/sse.py`

2. **K0 Contracts:** API schemas
   - `k0/contracts/openapi.k0.yaml`
   - `k0/contracts/jsonschema/*.json`

3. **K0 Event Bus:** Pub/sub implementation (inspiration)
   - `k0/bus/core.py`

### Architecture Diagrams

1. **K0-K1 Integration:** Complete architecture
   - `architecture_diagrams/k0_k1_integration_architecture.mmd`

2. **K1 Complete Flows:** Layer interactions
   - `architecture_diagrams/k1/k1_complete_with_flows.mmd`

---

## Risk Mitigation

### Risk 1: K0 Unavailability

**Mitigation:**

- Run local K0 instance
- K0 health check in CI/CD
- Mock K0 responses in unit tests

### Risk 2: Performance Budget Violations

**Mitigation:**

- Performance tests per milestone
- Profile with `py-spy` if slow
- Optimize hot paths first

### Risk 3: Schema Mismatches

**Mitigation:**

- Read K0 contracts first
- Validate with K0 in integration tests
- Ask architecture team if unclear

---

**Next Phase:** [Phase 2: Layer 4 Runtime Core](Phase_2.md) (Weeks 5-6)
