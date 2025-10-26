# K1 Trace Propagation Implementation Guide

**Purpose:** cognitive_trace_id propagation across K1 layers (L1→L2→L3→L4→L5) for end-to-end tracing

**ADR Reference:** ADR-0030 (Intelligent Trace Sampling)

---

## Architecture Overview

K1 inherits K0's OpenTelemetry-based tracing via integration layer (`k1.l5_infrastructure.observability.get_tracer()`).

**Key Concepts:**
- **cognitive_trace_id**: Baggage key (lowercase, NOT HTTP header) for end-to-end correlation
- **W3C Trace Context**: HTTP headers (`traceparent`, `tracestate`) for cross-service propagation
- **Sampling Strategy**: ADR-0030 (1% baseline + 100% errors)

**Trace Flow:**
```
L1 Ingress (API Gateway/SSE)
  ↓ [attach_cognitive_trace(trace_id)]
L2 Orchestrator (Contract Net Protocol)
  ↓ [propagate via mailbox messages]
L3 Agents (Actor Model)
  ↓ [inherit from parent context]
L4 Runtime (SessionState, Memory)
  ↓ [use current_cognitive_trace_id()]
L5 K0 Bridge (Command/Query/SSE clients)
  ↓ [inject(headers) → traceparent/tracestate]
K0 Command Port (:5200)
```

---

## Layer-by-Layer Implementation

### L1 Ingress: Trace Initiation

**Location:** `k1/l4_ingress/api_gateway/` (when implemented)

**Pattern:**
```python
from k1.l5_infrastructure.observability import get_tracer

_tracer = get_tracer()

@app.post("/k1/command.execute")
async def execute_command(request: Request):
    # Extract trace_id from HTTP headers or generate new
    trace_id = request.headers.get("x-cognitive-trace-id") or _tracer.new_trace_id()

    # Attach to context (returns token for detach)
    token = _tracer.attach_cognitive_trace(trace_id)

    try:
        with _tracer.span("k1.command_execute", attributes={"command": "..."}):
            result = await orchestrator.negotiate(task)
            return result
    finally:
        _tracer.detach(token)
```

**Key Points:**
- Extract `x-cognitive-trace-id` from HTTP headers (user-provided or upstream)
- Generate new trace_id if missing: `_tracer.new_trace_id()` (UUID v4 hex)
- Attach to context: `token = _tracer.attach_cognitive_trace(trace_id)`
- Always detach in finally block: `_tracer.detach(token)`

---

### L2 Orchestrator: Propagate to Agents

**Location:** `k1/l2_orchestration/orchestrator/negotiation.py`, `selection.py`, `execution.py`

**Pattern:**
```python
from k1.l5_infrastructure.observability import get_tracer

_tracer = get_tracer()

async def negotiate(self, task):
    # Retrieve current trace_id from context
    cognitive_trace_id = _tracer.current_cognitive_trace_id()

    with _tracer.span("k1.orchestrator.negotiate", attributes={"task_id": task.id}):
        # Send mailbox message to agents with trace_id
        for agent in self.agents:
            await agent.mailbox.send({
                "cognitive_trace_id": cognitive_trace_id,
                "task": task,
                "phase": "negotiation"
            })

        proposals = await self._gather_proposals()
        return proposals
```

**Key Points:**
- Retrieve trace_id: `_tracer.current_cognitive_trace_id()` (returns str or None)
- Include `cognitive_trace_id` field in all mailbox messages
- Wrap orchestration phases in spans: `_tracer.span("k1.orchestrator.negotiate")`
- Already instrumented in negotiation.py, selection.py, execution.py (GATE 3.4-3.5)

---

### L3 Agents: Inherit from Mailbox

**Location:** `k1/l3_execution/agents/hire_fire/__init__.py`, agent implementations

**Pattern:**
```python
from k1.l5_infrastructure.observability import get_tracer

_tracer = get_tracer()

async def process_mailbox_message(self, message: dict):
    # Extract trace_id from mailbox message
    cognitive_trace_id = message.get("cognitive_trace_id")

    # Attach to agent's context
    token = _tracer.attach_cognitive_trace(cognitive_trace_id) if cognitive_trace_id else None

    try:
        with _tracer.span("k1.agent.process_message", attributes={"agent_id": self.id}):
            result = await self._handle_task(message["task"])
            return result
    finally:
        if token:
            _tracer.detach(token)
```

**Key Points:**
- Extract `cognitive_trace_id` from mailbox message
- Attach to agent's context (agents run in separate async tasks)
- All agent operations inherit trace context from parent
- Agent lifecycle transitions (PENDING→WARMING→ACTIVE) should be traced

---

### L4 Runtime: Use Current Trace

**Location:** `k1/l4_runtime/session_state/`, `k1/l4_runtime/memory_manager/`

**Pattern:**
```python
from k1.l5_infrastructure.observability import get_tracer

_tracer = get_tracer()

async def serialize_session_state(session_state: SessionState):
    cognitive_trace_id = _tracer.current_cognitive_trace_id()

    with _tracer.span("k1.session_state.serialize", attributes={
        "session_id": session_state.id,
        "cognitive_trace_id": cognitive_trace_id
    }):
        serialized = await full_serializer.serialize(session_state)
        _record_serialization_size("full", len(serialized))
        return serialized
```

**Key Points:**
- No need to attach/detach (inherit from orchestrator/agent context)
- Use `_tracer.current_cognitive_trace_id()` for logging/attributes
- Wrap critical operations in spans (serialization, eviction, K0 WAL writes)

---

### L5 K0 Bridge: Inject into HTTP Headers

**Location:** `k1/l5_infrastructure/bridge_k0/command_client.py`, `query_client.py`

**Already Implemented:**
```python
# command_client.py line 324-370
async def submit_command(self, envelope: CommandEnvelope) -> CommandReceipt:
    token = _tracer.attach_cognitive_trace(envelope.cognitive_trace_id)
    start_time = time.time()

    try:
        with _tracer.span("k1.command_submit", attributes={"band": envelope.band, ...}):
            # ... envelope preparation

            # Inject trace context into HTTP headers
            headers = {}
            _tracer.inject(headers)  # Adds traceparent, tracestate headers

            response = await self._http_client.post(
                "/k0/command.submit",
                json=payload,
                headers=headers  # W3C Trace Context propagated
            )

            return CommandReceipt(...)
    finally:
        _tracer.detach(token)
```

**Key Points:**
- Already implemented in `command_client.py` (lines 324-505)
- Already implemented in `query_client.py` (similar pattern)
- `_tracer.inject(headers)` adds W3C Trace Context headers automatically
- K0 Command Port extracts trace context from `traceparent` header

---

## Verification Checklist

### End-to-End Trace Flow
- [ ] L1 generates/extracts trace_id from HTTP request
- [ ] L2 propagates trace_id to agents via mailbox
- [ ] L3 agents attach trace_id from mailbox message
- [ ] L4 runtime uses current_cognitive_trace_id() for logging
- [ ] L5 bridge injects trace_id into K0 HTTP headers

### Trace Continuity
- [ ] Same trace_id flows from L1 → L5
- [ ] K0 receives trace_id in `traceparent` header
- [ ] All spans share same trace_id (verify in OTLP exporter)
- [ ] Baggage key `cognitive_trace_id` persists across layers

### Performance
- [ ] `attach_cognitive_trace()` < 10μs P95
- [ ] `current_cognitive_trace_id()` < 5μs P95
- [ ] `inject(headers)` < 20μs P95
- [ ] Total tracing overhead < 1% CPU (continuous profiling)

---

## Testing Strategy

### Unit Tests (WARD)
```python
from ward import test, fixture
from k1.l5_infrastructure.observability import get_tracer

@test("cognitive_trace_id propagates across layers")
async def _():
    tracer = get_tracer()
    trace_id = tracer.new_trace_id()

    # L1: Attach
    token = tracer.attach_cognitive_trace(trace_id)
    assert tracer.current_cognitive_trace_id() == trace_id

    # L2: Propagate via mailbox
    message = {"cognitive_trace_id": tracer.current_cognitive_trace_id()}

    # L3: Agent attaches from message
    agent_token = tracer.attach_cognitive_trace(message["cognitive_trace_id"])
    assert tracer.current_cognitive_trace_id() == trace_id

    # L5: Inject into headers
    headers = {}
    tracer.inject(headers)
    assert "traceparent" in headers

    # Cleanup
    tracer.detach(agent_token)
    tracer.detach(token)
```

### Integration Tests (K1→K0)
```python
@test("K1→K0 trace correlation")
async def _(command_client: CommandClient):
    trace_id = tracer.new_trace_id()
    token = tracer.attach_cognitive_trace(trace_id)

    try:
        envelope = CommandEnvelope(
            cognitive_trace_id=trace_id,
            topic="k0.memory.write",
            ...
        )
        receipt = await command_client.submit_command(envelope)

        # Verify K0 received same trace_id
        # (check K0 logs or OTLP exporter for matching trace_id)
        assert receipt.receipt_id  # K0 acknowledged
    finally:
        tracer.detach(token)
```

---

## OpenTelemetry Concepts

### Baggage (cognitive_trace_id)
- **Key:** `cognitive_trace_id` (lowercase, NOT HTTP header)
- **Scope:** Thread-local context (propagates via OpenTelemetry Context API)
- **Usage:** `baggage.set_baggage("cognitive_trace_id", trace_id)`
- **Retrieval:** `baggage.get_baggage("cognitive_trace_id")`

### W3C Trace Context (HTTP headers)
- **traceparent:** `00-<trace_id>-<span_id>-<trace_flags>`
- **tracestate:** Vendor-specific key-value pairs
- **Propagation:** `propagate.inject(headers)` / `propagate.extract(headers)`
- **K0 Integration:** Command Port reads `traceparent` header (line 224)

### Spans (OpenTelemetry)
- **Purpose:** Represent units of work (e.g., `k1.command_execute`, `k1.orchestrator.negotiate`)
- **Attributes:** Key-value metadata (task_id, agent_id, band, etc.)
- **Parent-Child:** Automatically linked via Context API
- **Export:** OTLP exporter sends spans to observability backend (Jaeger, Tempo)

---

## Common Pitfalls

### ❌ Forgetting to Detach
```python
# BAD: token leak (context never released)
token = tracer.attach_cognitive_trace(trace_id)
return result  # Forgot to detach!
```

**Fix:** Always use try/finally:
```python
token = tracer.attach_cognitive_trace(trace_id)
try:
    return result
finally:
    tracer.detach(token)
```

---

### ❌ Using HTTP Header Name (X-Cognitive-Trace-Id)
```python
# BAD: COGNITIVE_TRACE_BAGGAGE_KEY is lowercase, not HTTP header
baggage.set_baggage("X-Cognitive-Trace-Id", trace_id)  # WRONG!
```

**Fix:** Use lowercase baggage key:
```python
baggage.set_baggage("cognitive_trace_id", trace_id)  # CORRECT
```

---

### ❌ Not Propagating in Mailbox Messages
```python
# BAD: Agent receives task without trace context
await agent.mailbox.send({"task": task})  # No trace_id!
```

**Fix:** Include cognitive_trace_id in message:
```python
await agent.mailbox.send({
    "task": task,
    "cognitive_trace_id": tracer.current_cognitive_trace_id()
})
```

---

## References

- **ADR-0030:** Intelligent Trace Sampling (1% baseline + 100% errors)
- **ADR-0024:** Performance Budgets (tracing overhead <1% CPU)
- **K0 Tracing:** `k0/obs/tracing.py` (TracerFactory, COGNITIVE_TRACE_BAGGAGE_KEY)
- **OpenTelemetry:** https://opentelemetry.io/docs/instrumentation/python/
- **W3C Trace Context:** https://www.w3.org/TR/trace-context/

---

**Last Updated:** January 2025
**Status:** Implementation guide for GATE 3.9 (Epic 3.2)
