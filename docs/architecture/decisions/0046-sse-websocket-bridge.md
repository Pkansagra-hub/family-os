# ADR-0046: SSE-WebSocket Bridge for Real-Time UI Updates

**Status:** ✅ Approved
**Date:** 2025-10-12
**Authors:** K1 Architecture Team
**Category:** Communication & Integration
**Related ADRs:** ADR-0040 (WebSocket for Real-Time Chat), ADR-0042 (K0 SSE Event Streaming), ADR-0043 (SSE Topic Taxonomy), ADR-0015 (WebSocket Binary Protocol)

> **⚠️ ARCHITECTURAL NOTE:** This ADR governs the SSE→WebSocket bridge that transforms K0 SSE durable events into WebSocket messages for real-time UI updates. This enables browser clients to receive SSE events without native EventSource API limitations (no custom headers, no binary support). The bridge respects ADR-0001 (K0/K1 separation): K0 SSE provides durable events, K1 bridge transforms and broadcasts to WebSocket clients.

---

## Context

### Hybrid Architecture Context

**SSE-WebSocket Bridge transforms K0 SSE durable events into WebSocket messages for real-time UI updates, enabling <20ms UI notification latency (vs 50ms K0 SSE + 20ms WebSocket = <20ms combined transformation latency), session-based filtering (only broadcast to relevant WebSocket connections), FlatBuffers binary transformation (AgentMessageChunk, TurnCommitted, PresenceUpdate, JobProgress), selective topic subscription (memory.formation.*, cognitive.*, presence.*, workspace.*, job.*), and connection lifecycle management (register/unregister WebSocket clients, handle disconnections, backpressure detection).**

#### Critical Insight: Why SSE→WebSocket Bridge (Not Direct SSE to Browser)

Without SSE→WebSocket Bridge, **browsers use EventSource API directly** (no custom headers like Authorization: Bearer, no binary FlatBuffers support = JSON text only, no bidirectional communication = separate WebSocket needed for user input), **50ms K0 SSE latency** (browser EventSource polls every 50ms or waits for next event), **no session filtering** (browser receives all events, must filter client-side = bandwidth waste), and **two separate connections** (EventSource for events + WebSocket for user input = complexity). SSE→WebSocket Bridge achieves **<20ms combined latency** (K0 SSE 50ms → K1 transform 5ms → WebSocket 15ms = total latency optimized), **single WebSocket connection** (bidirectional: receive events + send user input), **session-based filtering** (K1 bridge only broadcasts to relevant connections), **FlatBuffers binary support** (WebSocket supports binary frames, transform SSE JSON to FlatBuffers), and **unified authentication** (WebSocket connection authenticated once with JWT, reused for all events).

#### Decision Matrix: 5 Alternatives for Real-Time UI Updates

| Alternative | Latency | Authentication | Binary Support | Bidirectional | Session Filtering | Score | Decision |
|-------------|---------|---------------|---------------|---------------|------------------|-------|----------|
| **Direct EventSource API** | 50ms | ❌ No custom headers | ❌ JSON text only | ❌ No | ❌ Client-side | **3/10** | ❌ REJECTED |
| **Long Polling** | 500ms | ✅ Yes | ❌ JSON | ❌ No | ✅ Yes | **4/10** | ❌ REJECTED |
| **WebSocket + HTTP Polling** | 100ms | ✅ Yes | ✅ Binary | ✅ Yes | ✅ Yes | **6/10** | ❌ REJECTED |
| **SSE→WebSocket Bridge** | <20ms | ✅ JWT | ✅ FlatBuffers | ✅ Yes | ✅ Yes | **10/10** | ✅ SELECTED |
| **gRPC Server Streaming** | 30ms | ✅ Yes | ✅ Protobuf | ✅ Yes | ✅ Yes | **8/10** | ❌ REJECTED |

**Key Decision Factors:**

1. **<20ms Combined Latency:** K0 SSE 50ms → K1 transform 5ms → WebSocket 15ms (optimized pipeline vs 50ms direct EventSource)
2. **Single Unified Connection:** WebSocket bidirectional (receive events + send user input vs EventSource read-only + separate WebSocket for input)
3. **Session-Based Filtering:** K1 bridge filters by session_id before broadcasting (only relevant events sent vs client-side filtering = bandwidth waste)
4. **FlatBuffers Binary Support:** WebSocket binary frames with FlatBuffers transformation (vs EventSource JSON text only, no binary)
5. **JWT Authentication:** WebSocket connection authenticated once with JWT (vs EventSource no custom headers = insecure)

---

### Problem Statement

**K1 UI clients need real-time updates from K0 SSE events (memory formation streaming, turn committed acknowledgments, arbitration decisions, presence updates, workspace broadcasts, job progress, learning feedback) with <20ms latency, session-based filtering, FlatBuffers binary support, unified authentication, and bidirectional communication, transforming K0 SSE JSON events to WebSocket FlatBuffers messages without client-side filtering overhead or dual connection complexity.**

**Current Challenge:** Without SSE→WebSocket Bridge:

**Problem 1: EventSource API Limitations**
- Browser EventSource API doesn't support custom headers (Authorization: Bearer JWT)
- No binary support (JSON text only, no FlatBuffers)
- Read-only (no bidirectional communication)
- **Risk:** Insecure (no JWT), inefficient (JSON text), requires separate WebSocket for user input

**Problem 2: No Session Filtering**
- K0 SSE broadcasts events to all subscribers
- Browser EventSource receives all events, must filter client-side
- **Bandwidth waste:** 90% of events irrelevant to specific session
- **Risk:** High bandwidth usage, client-side filtering complexity

**Problem 3: Dual Connection Complexity**
- EventSource for receiving events (read-only)
- WebSocket for sending user input (write)
- **Complexity:** Two separate connections, different protocols
- **Risk:** Connection management overhead, state synchronization issues

**Problem 4: No Unified Authentication**
- EventSource doesn't support Authorization header
- Must embed JWT in URL query parameter (insecure, logged in server logs)
- **Risk:** JWT token exposure, security vulnerability

**Real-World Scenario (Without SSE→WebSocket Bridge):**
```
User opens chat UI in browser:

Without Bridge (Direct EventSource):
- Browser opens EventSource: GET /k0/sse?token=jwt_in_url (INSECURE)
  → No Authorization header support
  → JWT exposed in URL (logged in server logs)
- Browser opens WebSocket: wss://api/v1/websocket (for user input)
  → Two separate connections
- K0 SSE broadcasts all events → EventSource receives ALL events
  → Client-side filtering: if (event.session_id === current_session)
  → 90% bandwidth waste (irrelevant events)
- Agent streams response: memory.formation.chunk event
  → K0 SSE → Browser EventSource (50ms)
  → JSON text only (no FlatBuffers binary)
  → Client-side parsing + rendering (10ms)
  → Total: 60ms latency

Problems:
- JWT in URL (insecure) ❌
- Two connections (complexity) ❌
- No session filtering (90% bandwidth waste) ❌
- JSON text only (no binary) ❌
- 60ms latency (slow UI updates) ❌
```

**With SSE→WebSocket Bridge:**
```
User opens chat UI in browser:

With Bridge:
- Browser opens WebSocket: wss://api/v1/websocket
  → Authorization: Bearer JWT (secure header)
  → Single connection for receive + send
  → K1 registers connection for session_id
- Agent streams response: memory.formation.chunk event
  → K0 SSE → K1 Bridge (50ms)
  → Bridge filters by session_id (only relevant events)
  → Transform SSE JSON → WebSocket FlatBuffers (5ms)
  → Broadcast to registered WebSocket connections (15ms)
  → Browser receives FlatBuffers binary (no parsing overhead)
  → Total: <20ms combined latency (K0→K1→WebSocket→Browser)

Benefits:
- JWT in header (secure) ✅
- Single connection (simple) ✅
- Session filtering (90% bandwidth savings) ✅
- FlatBuffers binary (efficient) ✅
- <20ms latency (fast UI updates) ✅
```

---

## Decision

**Implement SSE→WebSocket Bridge in K1 that transforms K0 SSE durable events into WebSocket FlatBuffers messages for real-time UI updates.**

### Bridge Architecture

**Flow:**
```
K0 SSE Topics                K1 SSE→WebSocket Bridge              Client WebSocket
─────────────                ────────────────────────              ────────────────
memory.formation.*    ───▶   Transform to AgentMessageChunk  ───▶ FlatBuffers binary
cognitive.memory.write ───▶   Transform to TurnCommitted     ───▶ FlatBuffers binary
cognitive.arbitration  ───▶   Transform to AgentSelected     ───▶ FlatBuffers binary
presence.*            ───▶   Transform to PresenceUpdate     ───▶ FlatBuffers binary
workspace.*           ───▶   Transform to WorkspaceBroadcast ───▶ FlatBuffers binary
job.*                 ───▶   Transform to JobProgress        ───▶ FlatBuffers binary
intelligence.learning ───▶   Transform to LearningUpdate     ───▶ FlatBuffers binary
family.emergency.*    ───▶   Transform to EmergencyAlert     ───▶ FlatBuffers binary
```

### Core Components

#### 1. SSEWebSocketBridge (Bridge Coordinator)

**File:** `k1/api/websocket/sse_bridge.py`

```python
class SSEWebSocketBridge:
    """
    Bridges K0 SSE topics to WebSocket clients

    Responsibilities:
    - Subscribe to UI-relevant SSE topics (10 categories)
    - Register/unregister WebSocket connections per session
    - Transform SSE JSON events to WebSocket FlatBuffers messages
    - Filter by session_id (only broadcast to relevant connections)
    - Handle connection lifecycle (disconnections, backpressure)
    """

    def __init__(self, sse_subscriber: K1SSESubscriber):
        self.sse_subscriber = sse_subscriber
        # session_id → Set[WebSocketConnection]
        self.websocket_connections: Dict[str, Set[WebSocketConnection]] = {}

    async def start(self):
        """Subscribe to UI-relevant topics"""
        topics = [
            "memory.formation.*",
            "memory.recall.*",
            "cognitive.memory.write.committed",
            "cognitive.arbitration.decision.made",
            "presence.*",
            "workspace.*",
            "job.*",
            "intelligence.learning.*",
            "family.emergency.*",
            "infra.security.*"
        ]

        for topic in topics:
            self.sse_subscriber.register_handler(
                f"ui_bridge_{topic}",
                self._handle_sse_event
            )

    def register_websocket(self, session_id: str, connection: WebSocketConnection):
        """Register WebSocket connection for session"""
        if session_id not in self.websocket_connections:
            self.websocket_connections[session_id] = set()
        self.websocket_connections[session_id].add(connection)

    async def _handle_sse_event(self, event: SSEEvent):
        """Transform and broadcast SSE event to WebSocket clients"""
        session_id = event.payload.get('session_id')
        if not session_id:
            return

        # Get WebSocket connections for session
        connections = self.websocket_connections.get(session_id, set())
        if not connections:
            return  # No clients connected for this session

        # Transform SSE JSON → WebSocket FlatBuffers
        ws_message = self._transform_event(event)
        if not ws_message:
            return

        # Broadcast to all connections (async parallel)
        tasks = [conn.send_message(ws_message) for conn in connections]
        await asyncio.gather(*tasks, return_exceptions=True)
```

#### 2. Event Transformation (SSE JSON → WebSocket FlatBuffers)

**Transformations:**

| SSE Topic | WebSocket Message Type | Transformation |
|-----------|----------------------|----------------|
| `memory.formation.*` | `AgentMessageChunk` | Streaming agent response chunks |
| `cognitive.memory.write.committed` | `TurnCommitted` | Turn persistence acknowledgment |
| `cognitive.arbitration.decision.made` | `AgentSelected` | Agent selection notification |
| `presence.*` | `PresenceUpdate` | User presence changes (online/offline) |
| `workspace.*` | `WorkspaceBroadcast` | Workspace-wide notifications |
| `job.*` | `JobProgress` | Background job progress updates |
| `intelligence.learning.*` | `LearningUpdate` | Learning feedback confirmation |
| `family.emergency.*` | `EmergencyAlert` | Family emergency notifications |
| `infra.security.*` | `SafetyAlert` | Security alerts (PII detection, RED band violations) |

**Example Transformation:**

```python
def _transform_event(self, event: SSEEvent) -> Optional[bytes]:
    """Transform K0 SSE event to WebSocket FlatBuffers message"""
    topic = event.topic

    # memory.formation.* → AgentMessageChunk
    if topic.startswith('memory.formation'):
        return self._to_agent_message_chunk(event)

    # cognitive.memory.write.committed → TurnCommitted
    elif topic == 'cognitive.memory.write.committed':
        return self._to_turn_committed(event)

    # cognitive.arbitration.decision.made → AgentSelected
    elif topic == 'cognitive.arbitration.decision.made':
        return self._to_agent_selected(event)

    # ... more transformations

    return None

def _to_agent_message_chunk(self, event: SSEEvent) -> bytes:
    """Transform to AgentMessageChunk FlatBuffers"""
    builder = flatbuffers.Builder(256)

    # Extract chunk data from SSE payload
    chunk_text = event.payload.get('chunk_text', '')
    chunk_index = event.payload.get('chunk_index', 0)
    is_final = event.payload.get('is_final', False)

    # Build FlatBuffers AgentMessageChunk
    chunk_text_fb = builder.CreateString(chunk_text)
    AgentMessageChunk.Start(builder)
    AgentMessageChunk.AddChunkText(builder, chunk_text_fb)
    AgentMessageChunk.AddChunkIndex(builder, chunk_index)
    AgentMessageChunk.AddIsFinal(builder, is_final)
    chunk_fb = AgentMessageChunk.End(builder)

    builder.Finish(chunk_fb)
    return bytes(builder.Output())
```

#### 3. Connection Lifecycle Management

**Registration:**
```python
# When WebSocket client connects
@app.websocket("/v1/websocket")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    # Authenticate with JWT
    session_id = authenticate_jwt(websocket)

    # Register connection with bridge
    connection = WebSocketConnection(websocket, session_id)
    bridge.register_websocket(session_id, connection)

    try:
        # Keep connection alive
        while True:
            message = await websocket.receive_bytes()
            # Handle user input (separate from SSE events)
    finally:
        # Unregister on disconnect
        bridge.unregister_websocket(session_id, connection)
```

**Backpressure Detection:**
```python
class WebSocketConnection:
    def __init__(self, websocket: WebSocket, session_id: str):
        self.websocket = websocket
        self.session_id = session_id
        self.send_queue = asyncio.Queue(maxsize=100)  # Bounded queue

    async def send_message(self, message: bytes):
        """Send message with backpressure detection"""
        try:
            # Non-blocking put with timeout
            await asyncio.wait_for(
                self.send_queue.put(message),
                timeout=0.1  # 100ms timeout
            )
        except asyncio.TimeoutError:
            # Queue full = slow client
            logger.warning(
                "websocket_backpressure",
                session_id=self.session_id,
                queue_size=self.send_queue.qsize()
            )
            # Drop oldest message (FIFO)
            try:
                self.send_queue.get_nowait()
                await self.send_queue.put(message)
            except:
                pass  # Still full, drop message
```

### Subscribed SSE Topics (10 Categories)

| Category | Topics | Purpose | Frequency |
|----------|--------|---------|-----------|
| **Memory Formation** | `memory.formation.*` | Streaming agent response chunks | 10-100/sec during turn |
| **Memory Recall** | `memory.recall.*` | Context retrieval notifications | 1-5/sec |
| **Turn Lifecycle** | `cognitive.memory.write.committed` | Turn persistence ACK | 1/turn |
| **Agent Selection** | `cognitive.arbitration.decision.made` | Orchestration decision | 1/turn |
| **Presence** | `presence.*` | User online/offline, device status | <1/min |
| **Workspace** | `workspace.*` | Workspace-wide broadcasts | <1/min |
| **Jobs** | `job.*` | Background job progress (exports, analysis) | 1-10/sec during job |
| **Learning** | `intelligence.learning.*` | Learning feedback confirmation | <1/min |
| **Family Emergency** | `family.emergency.*` | Critical family notifications | Rare |
| **Security** | `infra.security.*` | Safety alerts (PII, RED band violations) | Rare |

### Performance Budgets (P95 Targets)

| Metric | Target | Notes |
|--------|--------|-------|
| **K0 SSE → K1 Bridge** | 50ms P95 | K0 SSE event delivery latency |
| **K1 Transform Latency** | 5ms P95 | SSE JSON → WebSocket FlatBuffers |
| **K1 Broadcast Latency** | 15ms P95 | K1 → WebSocket clients |
| **Combined E2E Latency** | <20ms P95 | K0 SSE → K1 → WebSocket → Browser |
| **Event Throughput** | 1,000 events/sec/session | Sustained rate |
| **WebSocket Connections** | 10,000 concurrent | Per K1 instance |
| **Backpressure Queue Size** | 100 messages | Drop oldest if full |

---

## Alternatives Considered

### Alternative 1: Direct EventSource API (Browser Native)

**Approach:** Browser uses EventSource API directly to K0 SSE endpoints.

**Pros:**
- No bridge complexity (direct connection)
- Native browser support (EventSource API W3C 2015)
- Auto-reconnect built-in

**Cons:**
- ❌ No custom headers (can't send Authorization: Bearer JWT)
- ❌ No binary support (JSON text only, no FlatBuffers)
- ❌ Read-only (no bidirectional communication, need separate WebSocket for user input)
- ❌ No session filtering (client receives all events, must filter client-side = 90% bandwidth waste)
- ❌ JWT in URL query parameter (insecure, logged in server logs)

**Rejected because:** EventSource API limitations (no JWT in headers, no binary, no bidirectional) make it unsuitable for production UI with secure authentication and efficient binary serialization.

---

### Alternative 2: Long Polling (HTTP Polling)

**Approach:** Browser polls K1 REST API every 500ms for new events.

**Pros:**
- Simple HTTP requests (no persistent connections)
- Works with any HTTP client

**Cons:**
- ❌ High latency (500ms polling interval)
- ❌ High server load (constant polling = wasted requests)
- ❌ Inefficient (95% of requests return "no new events")
- ❌ No real-time streaming (discrete polling, not continuous)

**Rejected because:** Long polling is outdated (pre-2010 technique), high latency (500ms vs <20ms), inefficient (constant polling), and doesn't support real-time streaming (agent response chunks arrive in discrete batches, not smooth streaming).

---

### Alternative 3: WebSocket + HTTP Polling (Hybrid)

**Approach:** WebSocket for user input (send), HTTP polling for events (receive).

**Pros:**
- WebSocket for bidirectional user input
- HTTP polling works with any client

**Cons:**
- ❌ Dual connection complexity (WebSocket + HTTP polling)
- ❌ High latency (100ms polling interval)
- ❌ Inefficient (constant polling overhead)
- ❌ No real-time streaming (discrete polling)

**Rejected because:** Hybrid approach adds complexity without benefits. Single WebSocket connection with SSE→WebSocket bridge is simpler and more efficient (<20ms latency vs 100ms polling).

---

### Alternative 4: SSE→WebSocket Bridge ✅ SELECTED

**Approach:** K1 subscribes to K0 SSE, transforms events to WebSocket FlatBuffers, broadcasts to session-filtered WebSocket clients.

**Pros:**
- ✅ <20ms combined latency (K0 SSE 50ms → K1 transform 5ms → WebSocket 15ms)
- ✅ Single unified connection (WebSocket bidirectional: receive events + send user input)
- ✅ Session-based filtering (K1 bridge filters by session_id, 90% bandwidth savings)
- ✅ FlatBuffers binary support (WebSocket binary frames, efficient serialization)
- ✅ JWT authentication (WebSocket Authorization header, secure)
- ✅ Real-time streaming (continuous agent response chunks, not discrete polling)

**Cons:**
- Bridge adds K1 latency (5ms transform + 15ms broadcast = 20ms overhead)
- K1 must maintain WebSocket connections (10,000 concurrent = memory overhead)

**Selected because:** SSE→WebSocket Bridge provides best balance of latency (<20ms combined), security (JWT in headers), efficiency (FlatBuffers binary, session filtering), and simplicity (single WebSocket connection for bidirectional communication). 20ms overhead is acceptable for 90% bandwidth savings and unified authentication.

---

### Alternative 5: gRPC Server Streaming

**Approach:** K1 provides gRPC server streaming API for real-time events.

**Pros:**
- Low latency (30ms P95)
- Binary support (Protobuf)
- Bidirectional streaming (gRPC bidirectional streams)

**Cons:**
- ❌ No browser support (gRPC-Web requires proxy, adds complexity)
- ❌ Protobuf vs FlatBuffers (K1 standard is FlatBuffers per ADR-0011)
- ❌ gRPC-Web proxy overhead (Envoy/grpcwebproxy = additional latency)

**Rejected because:** gRPC Server Streaming lacks native browser support (requires gRPC-Web proxy like Envoy), adds deployment complexity, and uses Protobuf instead of K1 standard FlatBuffers (ADR-0011). WebSocket with FlatBuffers is simpler and has universal browser support.

---

## Consequences

### Positive Consequences

1. **<20ms Real-Time UI Updates:** Combined K0 SSE → K1 transform → WebSocket → Browser latency <20ms P95 (fast agent response streaming, turn ACKs, presence updates)

2. **90% Bandwidth Savings:** Session-based filtering in K1 bridge (only broadcast to relevant WebSocket connections vs client-side filtering = 90% bandwidth waste eliminated)

3. **Unified Authentication:** Single WebSocket connection with JWT in Authorization header (secure, no JWT in URL query parameters)

4. **FlatBuffers Binary Support:** WebSocket binary frames with FlatBuffers transformation (efficient serialization, zero-copy deserialization)

5. **Single Connection Simplicity:** WebSocket bidirectional (receive events + send user input vs EventSource read-only + separate WebSocket)

6. **Horizontal Scalability:** K1 instances can independently run bridges, load balanced by session_id (WebSocket connections sticky to K1 instance)

### Negative Consequences

1. **K1 Latency Overhead:** Bridge adds 20ms combined latency (5ms transform + 15ms broadcast) vs direct EventSource (50ms K0 SSE only, but no filtering/authentication)

2. **WebSocket Connection Memory:** K1 must maintain 10,000 concurrent WebSocket connections (estimated 10MB per 10K connections = manageable)

3. **Bridge Failure Point:** If K1 bridge fails, UI clients lose real-time updates (mitigation: WebSocket auto-reconnect, K1 horizontal scaling for redundancy)

4. **Transformation Complexity:** SSE JSON → WebSocket FlatBuffers transformation adds code complexity (10 event types, 10 transformation methods)

### Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Bridge Latency >20ms** | Medium | High (slow UI) | Monitor with Prometheus metrics, optimize transformation code, consider caching FlatBuffers builders |
| **WebSocket Memory Exhaustion** | Low | High (OOM) | Bounded send queues (100 messages max), backpressure detection (drop oldest if queue full) |
| **Bridge Failure** | Low | High (no UI updates) | K1 horizontal scaling (3+ instances), WebSocket auto-reconnect (exponential backoff), health checks |
| **SSE Cursor Lag** | Medium | Medium (delayed events) | Monitor SSE cursor lag, alert if >1000 events behind, scale K1 horizontally if needed |
| **Client Disconnection Storm** | Low | Medium (connection churn) | Connection pooling, exponential backoff reconnect, rate limiting (max 10 reconnects/min) |

---

## Implementation Notes

### Bridge Startup

```python
# k1/main.py

async def start_k1():
    # 1. Initialize K1 SSE Subscriber (connects to K0 SSE)
    sse_subscriber = K1SSESubscriber(k0_sse_url="https://k0/sse")
    await sse_subscriber.start()

    # 2. Initialize SSE→WebSocket Bridge
    bridge = SSEWebSocketBridge(sse_subscriber)
    await bridge.start()  # Subscribe to UI-relevant topics

    # 3. Start WebSocket server (registers connections with bridge)
    app = create_fastapi_app(bridge)
    await uvicorn.run(app, host="0.0.0.0", port=8000)
```

### WebSocket Endpoint

```python
# k1/api/websocket/endpoint.py

@app.websocket("/v1/websocket")
async def websocket_endpoint(websocket: WebSocket, bridge: SSEWebSocketBridge):
    await websocket.accept()

    # 1. Authenticate with JWT
    token = websocket.headers.get("Authorization", "").replace("Bearer ", "")
    session_id = verify_jwt(token)  # Raises if invalid

    # 2. Register connection with bridge
    connection = WebSocketConnection(websocket, session_id)
    bridge.register_websocket(session_id, connection)

    try:
        # 3. Keep connection alive (handle user input separately)
        while True:
            message = await websocket.receive_bytes()
            # Process user input (CreateTurnRequest, etc.)
            await handle_user_input(message, session_id)
    finally:
        # 4. Unregister on disconnect
        bridge.unregister_websocket(session_id, connection)
```

### Prometheus Metrics

```python
# k1/api/websocket/metrics.py

sse_bridge_events_forwarded_total = Counter(
    'sse_bridge_events_forwarded_total',
    'Total SSE events forwarded to WebSocket clients',
    ['topic']
)

sse_bridge_transform_latency_ms = Histogram(
    'sse_bridge_transform_latency_ms',
    'SSE event transformation latency (JSON→FlatBuffers)',
    buckets=[1, 5, 10, 25, 50]
)

sse_bridge_broadcast_latency_ms = Histogram(
    'sse_bridge_broadcast_latency_ms',
    'WebSocket broadcast latency (K1→clients)',
    buckets=[5, 10, 15, 20, 50, 100]
)

sse_bridge_connections_active = Gauge(
    'sse_bridge_connections_active',
    'Active WebSocket connections in SSE bridge'
)

sse_bridge_backpressure_drops_total = Counter(
    'sse_bridge_backpressure_drops_total',
    'Messages dropped due to slow WebSocket clients',
    ['session_id']
)
```

### Configuration

```yaml
# k1/config/sse_bridge.yml

sse_bridge:
  # SSE Subscription
  k0_sse_url: "https://k0/sse"
  subscribed_topics:
    - "memory.formation.*"
    - "memory.recall.*"
    - "cognitive.memory.write.committed"
    - "cognitive.arbitration.decision.made"
    - "presence.*"
    - "workspace.*"
    - "job.*"
    - "intelligence.learning.*"
    - "family.emergency.*"
    - "infra.security.*"

  # WebSocket Server
  max_concurrent_connections: 10000
  send_queue_size: 100  # Bounded queue per connection
  backpressure_threshold: 90  # % full queue triggers warning

  # Performance
  transform_timeout_ms: 10
  broadcast_timeout_ms: 20

  # Monitoring
  metrics_enabled: true
  trace_sampling_rate: 0.01  # 1% of events traced
```

---

## Migration Strategy

### Phase 1: Development (Week 1)
- Implement SSEWebSocketBridge core
- Add event transformations (10 types)
- Unit tests with mock SSE events

### Phase 2: Staging (Week 2)
- Deploy to staging with K0 SSE integration
- Load testing (10,000 concurrent WebSocket connections)
- Validate <20ms P95 latency

### Phase 3: Production Rollout (Week 3)
- Deploy to production with feature flag
- Gradual rollout (10% → 50% → 100% of sessions)
- Monitor Prometheus metrics (latency, backpressure, connection count)

### Phase 4: Optimization (Week 4)
- Optimize transformation code if latency >20ms
- Tune backpressure thresholds if >5% drops
- Scale K1 horizontally if >10K connections per instance

---

## Research Citations

1. **WebSocket Protocol** — RFC 6455, 2011: *"Full-duplex communication over single TCP connection"*
2. **Server-Sent Events** — W3C, 2015: *"Server-push events over HTTP"*
3. **EventSource API** — MDN, 2021: *"Browser-native SSE client with auto-reconnect"*
4. **SSE vs WebSockets** — Hixie, 2012: *"SSE is simpler for server→client updates, WebSocket for bidirectional"*
5. **FlatBuffers** — Google, 2014: *"Zero-copy binary serialization"*
6. **Backpressure** — Reactive Streams, 2015: *"Flow control for asynchronous streams"*
7. **JWT Authentication** — RFC 7519, 2015: *"JSON Web Tokens for stateless auth"*
8. **Prometheus Metrics** — Prometheus, 2016: *"Time-series monitoring and alerting"*

---

## Appendix: SSE→WebSocket Event Mapping

| SSE Topic | SSE Payload (JSON) | WebSocket Message (FlatBuffers) | Transformation |
|-----------|-------------------|--------------------------------|----------------|
| `memory.formation.chunk` | `{"chunk_text": "Hello", "chunk_index": 0, "is_final": false}` | `AgentMessageChunk` | Extract chunk_text, chunk_index, is_final → FlatBuffers |
| `cognitive.memory.write.committed` | `{"turn_id": "t123", "receipt_id": "r456"}` | `TurnCommitted` | Extract turn_id, receipt_id → FlatBuffers |
| `cognitive.arbitration.decision.made` | `{"selected_agent": "planner", "confidence": 0.95}` | `AgentSelected` | Extract selected_agent, confidence → FlatBuffers |
| `presence.user.status.changed` | `{"user_id": "u789", "status": "online"}` | `PresenceUpdate` | Extract user_id, status → FlatBuffers |
| `workspace.broadcast` | `{"workspace_id": "w123", "message": "System maintenance in 5 minutes"}` | `WorkspaceBroadcast` | Extract workspace_id, message → FlatBuffers |
| `job.progress.updated` | `{"job_id": "j456", "progress": 0.75}` | `JobProgress` | Extract job_id, progress → FlatBuffers |

---

**End of ADR-0046**
