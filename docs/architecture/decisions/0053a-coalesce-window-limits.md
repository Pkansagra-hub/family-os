---
adr_number: 0053a
title: 0053A Coalesce Window Limits
status: ACCEPTED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer1_input
- layer4_runtime
- layer5_infrastructure
affected_modules: []
concerns:
- architecture
- cost
- modularity
- observability
- performance
- privacy
- testing
- ux
supersedes: []
superseded_by:
- ADR-0053c
related_adrs:
- ADR-0015
- ADR-0053
- ADR-0054a
- ADR-0055a
implementation_status: COMPLETED
implementation_date: null
implementation_phase: null
related_contracts: []
related_diagrams: []
research_citations: []
propagation:
  triggers:
  - Modifying system architecture
  - Performance requirement changes
  - Updating API contracts or schemas
  affected_adrs:
  - ADR-0015
  - ADR-0053
  - ADR-0054a
  - ADR-0055a
  affected_contracts:
  - k0/contracts/api/rest/idempotency/24h_retention.yml
  - k0/contracts/asyncapi.events.yaml
  - k0/contracts/openapi.k0.yaml
  - k1/contracts/flatbuffers/layer5_infrastructure/message_envelope.fbs
  affected_tests: []
---


﻿# ADR-0053a: Coalesce Window & Limits

**Status:** Accepted
**Date:** 2025-10-14
**Deciders:** K1 Architecture Team
**Parent ADR:** ADR-0053 (Message Queue & Coalescing)

**Related ADRs:**
- ADR-0053: Message Queue & Coalescing (parent)
- ADR-0054: Turn Boundary Management (turn detection coordination)
- ADR-0055: Context-Switch Detection (context switch triggers)
- ADR-0015: WebSocket Protocol (message ingress)

---

## Context

### Problem Statement

When users interact rapidly with conversational AI, messages arrive as fragments rather than complete utterances. Without coalescing, the system must process each fragment separately, leading to:

1. **Wasted Compute**: Partial messages trigger incomplete LLM inference calls
2. **Poor Intent Classification**: Fragments lack context for accurate classification
3. **Degraded UX**: Multiple partial responses confuse users
4. **Resource Thrashing**: Excessive round-trips consume network and compute

**Example Fragmentation:**
```
Without coalescing:
  User: "What's" â†’ System processes â†’ "I need more information"
  User: "the weather" â†’ System processes â†’ "Which location?"
  User: "in Seattle?" â†’ System processes â†’ "Checking weather..."

With coalescing (2s window):
  User: "What's the weather in Seattle?" â†’ System processes once â†’ "It's 72Â°F and sunny in Seattle"
```

### Research Foundation

**Cognitive Science:**
- **Typing Speed**: Average user types at 40-60 WPM (~0.7-1.0 words/second)
- **Pause Thresholds**: Natural speech pauses range from 0.5-2.5 seconds
- **Turn Boundaries**: Linguists identify 2-3 second pauses as turn-taking cues

**Network Optimization:**
- **Nagle's Algorithm (TCP)**: Coalesce small packets, wait ~200ms for more data
- **HTTP/2 Server Push**: Bundle related resources to reduce round-trips
- **Message Batching (Kafka, RabbitMQ)**: Collect messages before processing

**User Experience Research:**
- **Response Time Perception**: Users perceive <100ms as instant, 100-300ms as fast, >1s as slow
- **Input Buffering**: UI frameworks debounce input with 200-500ms windows
- **Typing Indicators**: Show "typing..." after 1-2 second pauses

### Current Situation

**Existing Behavior (Pre-ADR):**
- WebSocket ingress processes each message immediately
- No buffering or coalescing logic
- Intent classifier sees fragments, not complete utterances
- Average 3-5 messages per user turn (high fragmentation)

**Performance Impact:**
- Estimated 40% of messages are fragments requiring additional context
- Intent classification confidence <0.6 on 30% of fragments
- Clarification rate 25% (should be <15%)

### Constraints

**UX Requirements:**
- Coalescing must not introduce perceptible delay (<2s threshold)
- Urgent messages (RED band) must bypass coalescing
- Voice inputs require different handling (ASR coalesces automatically)

**System Requirements:**
- Memory overhead <1KB per queued message
- Queue bounded to prevent exhaustion
- Preserve message ordering (FIFO per session)

**Safety Requirements:**
- RED band messages bypass coalescing (immediate processing)
- Privacy bands respected (no cross-session message mixing)
- Cancellation must clear coalesced messages

---

## Decision

We implement a **dual-threshold coalescing strategy** with:

### 1. Time-Based Threshold: 2-Second Window

**Rationale:**
- Aligns with natural turn-taking pauses (2-3 seconds in conversation)
- Balances between buffering (efficiency) and latency (UX)
- Matches implicit turn boundary detection (ADR-0054a)

**Implementation:**
- Start timer on first message arrival
- Reset timer on each subsequent message
- Trigger processing when timer expires (2s idle)

**Example:**
```python
class CoalesceTimer:
    def __init__(self, window_ms=2000):
        self.window_ms = window_ms
        self.timer = None
        self.messages = []

    def on_message(self, msg):
        self.messages.append(msg)
        if self.timer:
            self.timer.cancel()  # Reset timer
        self.timer = Timer(self.window_ms / 1000, self.process)
        self.timer.start()

    def process(self):
        coalesced = " ".join([m.text for m in self.messages])
        self.send_to_processor(coalesced)
        self.messages.clear()
```

### 2. Count-Based Threshold: 5-Message Limit

**Rationale:**
- Prevents unbounded buffering (memory safety)
- Handles fast typers who exceed 2s before finishing
- Average typing speed produces 3-5 words in 2s window

**Implementation:**
- Maintain counter of queued messages
- Force processing when count reaches 5
- Counter resets after processing

**Trade-off:**
- Small limit (e.g., 3) â†’ premature processing, less efficiency
- Large limit (e.g., 10) â†’ memory pressure, delayed responses

**Justification for 5:**
- Average user utterance is 5-10 words
- 5 messages â‰ˆ 2-3 second typing window at 40 WPM
- Keeps memory overhead <5KB per session

### 3. Bypass Conditions

**Immediate Processing (No Coalescing):**

**Condition A: RED Band Messages**
- Purpose: Safety-critical actions must not be delayed
- Example: "Delete all my data" â†’ immediate two-person approval flow
- Integration: Privacy band check at ingress (ADR-0032-0038)

**Condition B: Explicit Submit**
- Purpose: User signals intent completion explicitly
- Example: User clicks "Send" button or presses Enter
- Integration: WebSocket protocol includes `"submit": true` flag (ADR-0015)

**Condition C: Context Switch Detected**
- Purpose: User changes topic mid-coalescing window
- Example: "What's the weather" â†’ "Actually, never mind, set a timer"
- Integration: Intent drift detection (ADR-0055a)

**Condition D: Voice Input**
- Purpose: ASR already coalesces audio frames
- Example: Continuous speech â†’ single transcript after VAD silence
- Integration: Voice pipeline bypasses text coalescing (ADR-0056a)

### 4. Coalescing Algorithm

**Pseudocode:**
```python
class MessageCoalescer:
    def __init__(self, window_ms=2000, max_messages=5):
        self.window_ms = window_ms
        self.max_messages = max_messages
        self.queue: List[Message] = []
        self.timer: Optional[Timer] = None

    async def enqueue(self, msg: Message) -> None:
        # Bypass conditions
        if msg.privacy_band == "RED":
            await self.process_immediately(msg)
            return

        if msg.is_explicit_submit:
            self.queue.append(msg)
            await self.flush()
            return

        if msg.is_context_switch:
            await self.flush()  # Process existing queue
            self.queue.append(msg)
            await self.flush()  # Process new message
            return

        # Normal coalescing path
        self.queue.append(msg)
        self.reset_timer()

        # Force flush if count limit reached
        if len(self.queue) >= self.max_messages:
            await self.flush()

    def reset_timer(self):
        if self.timer:
            self.timer.cancel()
        self.timer = Timer(self.window_ms / 1000, lambda: asyncio.create_task(self.flush()))
        self.timer.start()

    async def flush(self):
        if not self.queue:
            return

        # Coalesce messages with space delimiter
        coalesced_text = " ".join([m.text for m in self.queue])
        coalesced_msg = Message(
            text=coalesced_text,
            session_id=self.queue[0].session_id,
            timestamp=self.queue[-1].timestamp,
            source_messages=len(self.queue),
            trace_id=generate_trace_id()
        )

        # Emit metrics
        self.metrics.messages_coalesced.inc(len(self.queue))
        self.metrics.coalesce_window_duration.observe(
            (coalesced_msg.timestamp - self.queue[0].timestamp) * 1000
        )

        # Send to intent classifier
        await self.send_to_processor(coalesced_msg)

        # Clear state
        self.queue.clear()
        if self.timer:
            self.timer.cancel()
            self.timer = None
```

### 5. Edge Case Handling

**Case 1: Empty Messages**
- **Behavior**: Reject at WebSocket ingress (before coalescing)
- **Rationale**: No semantic value, would corrupt coalesced output

**Case 2: Queue Overflow (>5 messages before flush)**
- **Behavior**: Force flush at exactly 5 messages
- **Rationale**: Cannot happen by design (count threshold enforced)

**Case 3: Timer Expires with Single Message**
- **Behavior**: Process single message immediately
- **Rationale**: No coalescing benefit, avoid unnecessary delay

**Case 4: Rapid Context Switches**
- **Behavior**: Flush existing queue, process new message, start new queue
- **Rationale**: Preserve intent boundaries

**Case 5: Cancellation During Coalescing**
- **Behavior**: Clear queue, discard coalesced messages
- **Rationale**: User intent superseded by new input (see ADR-0053c)

---

## Consequences

### Positive Consequences

âœ… **Reduced LLM Inference Calls:**
- Coalesce 4 fragments â†’ 1 LLM call
- Estimated 40% reduction in inference requests
- Lower infrastructure costs (~$0.002/1K tokens Ã— 40% = $0.0008 savings per turn)

âœ… **Improved Intent Classification:**
- Complete utterances â†’ confidence scores increase from 0.6 to 0.85
- Fewer clarifications (25% â†’ 15% reduction)
- Better user experience (fewer "I didn't understand" responses)

âœ… **Lower Latency (Perceived):**
- User waits 2s for complete response vs 0.5s Ã— 4 partial responses
- Total time: 2s + 1s processing = 3s vs 4 Ã— (0.5s + 1s) = 6s
- 50% latency reduction for fragmented inputs

âœ… **Memory Efficiency:**
- Bounded queue (max 5 messages Ã— ~500 bytes = 2.5KB per session)
- Queue cleared after processing (no memory leaks)
- Prometheus metric tracks queue depth

### Negative Consequences

âš ï¸ **Delayed Processing for Slow Typers:**
- Users typing <1 word/second may perceive lag
- **Mitigation**: 2s window is below perception threshold (<3s)
- **Future work**: Adaptive windows per user typing speed

âš ï¸ **Complexity in Bypass Logic:**
- 4 bypass conditions add branching complexity
- **Mitigation**: Unit tests for each bypass condition
- **Monitoring**: Track bypass rate (should be <10%)

âš ï¸ **Race Conditions with Cancellation:**
- Timer expiration vs cancellation signal timing
- **Mitigation**: Atomic queue operations with locks
- **Testing**: Fuzz testing with random timing

âš ï¸ **Coordination with Turn Boundaries:**
- Coalesce window (2s) matches implicit turn boundary (2s)
- **Risk**: Conflicting signals if timers misaligned
- **Mitigation**: Share timer infrastructure between coalescing and turn detection

### Risk Mitigation

**Risk: Coalescing Misses Urgent Messages**
- **Detection**: RED band bypass ensures safety-critical messages processed immediately
- **Validation**: Test RED band messages bypass coalescing (<10ms latency)

**Risk: Queue Memory Exhaustion**
- **Detection**: Bounded queue (max 5 messages)
- **Alert**: Prometheus alert if queue depth >3 sustained for >10s

**Risk: Timer Overhead**
- **Optimization**: Use single event loop timer (not per-message threads)
- **Measurement**: Timer overhead <1ms per message

---

## Implementation Guidance

### Phase 1: Basic Coalescing (Day 1-2)

**Deliverables:**
- Implement `MessageCoalescer` class
- 2-second timer with reset on new message
- 5-message count limit
- Basic flush logic (join with space)

**Pseudocode:**
```python
class MessageCoalescer:
    def __init__(self):
        self.queue = []
        self.timer = None
        self.window_ms = 2000
        self.max_messages = 5

    def enqueue(self, msg):
        self.queue.append(msg)
        self.reset_timer()
        if len(self.queue) >= self.max_messages:
            self.flush()

    def reset_timer(self):
        if self.timer:
            self.timer.cancel()
        self.timer = Timer(self.window_ms / 1000, self.flush)
        self.timer.start()

    def flush(self):
        if self.queue:
            coalesced = " ".join([m.text for m in self.queue])
            self.send_to_processor(coalesced)
            self.queue.clear()
```

**Tests:**
- Enqueue 3 messages in 1s â†’ flush after 2s idle
- Enqueue 5 messages in 0.5s â†’ flush immediately
- Enqueue 1 message â†’ flush after 2s (no coalescing benefit)

### Phase 2: Bypass Logic (Day 3-4)

**Deliverables:**
- RED band bypass (immediate processing)
- Explicit submit bypass
- Context switch bypass
- Voice input bypass

**Pseudocode:**
```python
def enqueue(self, msg):
    # Bypass: RED band
    if msg.privacy_band == "RED":
        self.process_immediately(msg)
        return

    # Bypass: Explicit submit
    if msg.is_explicit_submit:
        self.queue.append(msg)
        self.flush()
        return

    # Bypass: Context switch
    if msg.is_context_switch:
        self.flush()  # Process existing
        self.process_immediately(msg)
        return

    # Normal path
    self.queue.append(msg)
    self.reset_timer()
    if len(self.queue) >= self.max_messages:
        self.flush()
```

**Tests:**
- RED band message bypasses coalescing
- Explicit submit flushes queue immediately
- Context switch flushes existing, processes new
- Voice input bypasses text coalescing

### Phase 3: Edge Case Handling (Day 5-6)

**Deliverables:**
- Empty message rejection
- Single message flush (no delay after timer)
- Rapid context switch handling
- Cancellation integration

**Tests:**
- Empty message rejected at ingress
- Single message in queue â†’ flush after 2s
- Context switch â†’ context switch â†’ both processed separately
- Cancellation during coalescing â†’ queue cleared

### Phase 4: Metrics & Monitoring (Day 7)

**Deliverables:**
- Prometheus metrics for coalescing efficiency
- Structured logging for debugging
- Grafana dashboard for monitoring

**Metrics:**
```python
messages_coalesced_total = Counter('messages_coalesced_total', 'Total messages coalesced')
coalesce_window_duration_ms = Histogram('coalesce_window_duration_ms', 'Coalesce window duration')
coalesce_queue_depth = Gauge('coalesce_queue_depth', 'Current queue depth', ['session_id'])
bypass_total = Counter('coalesce_bypass_total', 'Messages bypassing coalescing', ['reason'])
```

**Logs:**
```python
logger.info(
    "message_coalesced",
    session_id=session.id,
    message_count=len(self.queue),
    coalesced_length=len(coalesced_text),
    window_duration_ms=window_ms,
    trace_id=trace_id
)
```

### Phase 5: Integration Testing (Day 8-10)

**Deliverables:**
- End-to-end tests with WebSocket ingress (ADR-0015)
- Intent classifier integration (ADR-0021)
- Turn boundary coordination (ADR-0054a)
- Context switch detection (ADR-0055a)

**Test Scenarios:**
- Fragmented typing â†’ coalescing â†’ intent classification
- RED band message â†’ bypass â†’ two-person approval
- Explicit submit â†’ immediate flush â†’ response
- Context switch â†’ separate processing â†’ new turn

---

## Validation & Success Criteria

### Performance Targets

**Coalescing Efficiency:**
- **Target**: â‰¥30% of messages coalesced (baseline: 40% fragmentation rate)
- **Measurement**: `messages_coalesced / total_messages`
- **Success**: If ratio â‰¥30%, coalescing provides value

**Window Duration:**
- **Target**: Average window 1.2s (below 2s limit)
- **Measurement**: `coalesce_window_duration_ms` histogram P50
- **Success**: If P50 <1.5s, users typing naturally

**Queue Depth:**
- **Target**: Average depth 2.5 messages (below 5 limit)
- **Measurement**: `coalesce_queue_depth` gauge average
- **Success**: If avg <3, no memory pressure

**Bypass Rate:**
- **Target**: <10% of messages bypass coalescing
- **Measurement**: `bypass_total / total_messages`
- **Success**: If <10%, bypass logic not overused

### Functional Tests

**Test 1: Basic Coalescing**
```python
@test("coalesce 4 messages in 1.5s")
async def test_basic_coalescing():
    coalescer = MessageCoalescer()

    # Simulate rapid typing
    await coalescer.enqueue(Message(text="What's", timestamp=0.0))
    await coalescer.enqueue(Message(text="the", timestamp=0.3))
    await coalescer.enqueue(Message(text="weather", timestamp=0.6))
    await coalescer.enqueue(Message(text="in Seattle?", timestamp=1.0))

    # Wait for timer to expire
    await asyncio.sleep(2.5)

    # Verify coalesced output
    assert processor.received_message == "What's the weather in Seattle?"
    assert metrics.messages_coalesced.value == 4
```

**Test 2: Count Limit**
```python
@test("force flush at 5 messages")
async def test_count_limit():
    coalescer = MessageCoalescer()

    # Enqueue 5 messages rapidly
    for i, word in enumerate(["Book", "a", "flight", "to", "New York"]):
        await coalescer.enqueue(Message(text=word, timestamp=i * 0.2))

    # Should flush immediately (no timer wait)
    await asyncio.sleep(0.1)

    assert processor.received_message == "Book a flight to New York"
    assert metrics.messages_coalesced.value == 5
```

**Test 3: RED Band Bypass**
```python
@test("RED band bypasses coalescing")
async def test_red_band_bypass():
    coalescer = MessageCoalescer()

    # Enqueue RED band message
    msg = Message(text="Delete all my data", privacy_band="RED")
    await coalescer.enqueue(msg)

    # Should process immediately (no coalescing)
    await asyncio.sleep(0.01)

    assert processor.received_message == "Delete all my data"
    assert metrics.bypass_total.labels(reason="red_band").value == 1
```

**Test 4: Explicit Submit**
```python
@test("explicit submit flushes queue")
async def test_explicit_submit():
    coalescer = MessageCoalescer()

    # Enqueue 2 messages
    await coalescer.enqueue(Message(text="What's", timestamp=0.0))
    await coalescer.enqueue(Message(text="the weather?", timestamp=0.5, is_explicit_submit=True))

    # Should flush immediately
    await asyncio.sleep(0.1)

    assert processor.received_message == "What's the weather?"
    assert metrics.messages_coalesced.value == 2
```

**Test 5: Context Switch**
```python
@test("context switch triggers separate processing")
async def test_context_switch():
    coalescer = MessageCoalescer()

    # Enqueue messages
    await coalescer.enqueue(Message(text="What's the weather", timestamp=0.0))
    await coalescer.enqueue(Message(text="Actually, never mind", timestamp=1.0, is_context_switch=True))

    # Should process both separately
    await asyncio.sleep(0.1)

    assert len(processor.received_messages) == 2
    assert processor.received_messages[0] == "What's the weather"
    assert processor.received_messages[1] == "Actually, never mind"
```

### Edge Case Tests

**Test 6: Empty Message**
```python
@test("empty message rejected at ingress")
async def test_empty_message():
    coalescer = MessageCoalescer()

    # Attempt to enqueue empty message
    with ward.raises(ValueError, match="Empty message"):
        await coalescer.enqueue(Message(text=""))

    assert len(coalescer.queue) == 0
```

**Test 7: Single Message**
```python
@test("single message flushes after timer")
async def test_single_message():
    coalescer = MessageCoalescer()

    await coalescer.enqueue(Message(text="Hello", timestamp=0.0))

    # Wait for timer
    await asyncio.sleep(2.5)

    assert processor.received_message == "Hello"
    assert metrics.messages_coalesced.value == 1  # Still counts as coalesced
```

**Test 8: Cancellation Clears Queue**
```python
@test("cancellation clears coalescing queue")
async def test_cancellation():
    coalescer = MessageCoalescer()

    # Enqueue messages
    await coalescer.enqueue(Message(text="What's", timestamp=0.0))
    await coalescer.enqueue(Message(text="the weather", timestamp=0.5))

    # Trigger cancellation
    await coalescer.cancel()

    # Queue should be cleared
    assert len(coalescer.queue) == 0
    assert processor.received_message is None
```

---

## Monitoring & Observability

### Prometheus Metrics

```python
# Coalescing efficiency
messages_coalesced_total = Counter(
    'messages_coalesced_total',
    'Total messages coalesced'
)

coalesce_window_duration_ms = Histogram(
    'coalesce_window_duration_ms',
    'Time waited before coalescing (ms)',
    buckets=[100, 500, 1000, 1500, 2000, 2500]
)

coalesce_queue_depth = Gauge(
    'coalesce_queue_depth',
    'Current queue depth per session',
    ['session_id']
)

# Bypass tracking
bypass_total = Counter(
    'coalesce_bypass_total',
    'Messages bypassing coalescing',
    ['reason']  # red_band, explicit_submit, context_switch, voice
)

# Efficiency ratio
coalesce_efficiency_ratio = Gauge(
    'coalesce_efficiency_ratio',
    'Ratio of coalesced messages to total messages'
)
```

### Structured Logging

```python
# Coalescing event
logger.info(
    "message_coalesced",
    session_id=session.id,
    message_count=len(self.queue),
    coalesced_text_length=len(coalesced_text),
    window_duration_ms=window_ms,
    trace_id=trace_id
)

# Bypass event
logger.info(
    "coalesce_bypass",
    session_id=session.id,
    reason=bypass_reason,  # red_band, explicit_submit, etc.
    message_text=msg.text[:50],  # Truncate for logging
    trace_id=trace_id
)

# Queue cleared (cancellation)
logger.info(
    "coalesce_queue_cleared",
    session_id=session.id,
    discarded_messages=len(self.queue),
    reason="cancellation",
    trace_id=trace_id
)
```

### Grafana Dashboard

**Panel 1: Coalescing Efficiency**
- Metric: `rate(messages_coalesced_total[5m]) / rate(messages_total[5m])`
- Target: â‰¥30%
- Alert: If <20% for >10 minutes

**Panel 2: Window Duration Distribution**
- Metric: `histogram_quantile(0.5, coalesce_window_duration_ms)`
- Target: P50 <1.5s
- Alert: If P95 >2.5s for >5 minutes

**Panel 3: Queue Depth Time Series**
- Metric: `coalesce_queue_depth`
- Target: Average <3
- Alert: If >5 sustained for >1 minute

**Panel 4: Bypass Rate**
- Metric: `rate(bypass_total[5m]) / rate(messages_total[5m])`
- Target: <10%
- Alert: If >20% for >5 minutes (investigate bypass logic)

---

## Rollout Strategy

### Week 1: Internal Testing
- Deploy to dev environment
- Manual testing with synthetic users
- Validate coalescing with various typing speeds

### Week 2: Canary Deployment (5%)
- Roll out to 5% of production sessions
- Monitor metrics (efficiency, latency, bypass rate)
- Watch for regressions (error rate, user complaints)

### Week 3-4: Gradual Rollout (25% â†’ 50% â†’ 100%)
- Increase traffic gradually
- 72-hour soak at each stage
- Roll back if efficiency <20% or error rate >0.5%

### Week 5+: Optimization
- Tune window duration based on observed typing patterns
- A/B test 1.5s vs 2.0s vs 2.5s windows
- Investigate outliers (users with >5s windows)

---

## Future Work

### Adaptive Windows
- Learn optimal window per user based on typing speed
- Fast typers: 1.5s window
- Slow typers: 2.5s window
- Voice users: 0s window (bypass coalescing)

### Context-Aware Coalescing
- Longer windows for complex queries (e.g., multi-step booking)
- Shorter windows for simple queries (e.g., "What time is it?")
- Use intent classification confidence to adjust window

### Predictive Flush
- Machine learning model predicts when user finished typing
- Flush before timer expires (reduce perceived latency)
- Features: typing cadence, word count, sentence structure

---

## References

### Research Papers
- Nagle, J. (1984). "Congestion Control in IP/TCP Internetworks". RFC 896.
- Shneiderman, B. (1984). "Response Time and Display Rate in Human Performance with Computers". ACM Computing Surveys.
- Clark, H. H. (1996). "Using Language". Cambridge University Press (turn-taking chapter).

### Related ADRs
- ADR-0053: Message Queue & Coalescing (parent)
- ADR-0054a: Implicit Pause â‰¥2s (turn boundary coordination)
- ADR-0055a: Intent Drift Rules (context switch detection)
- ADR-0015: WebSocket Protocol (message ingress)

### Industry Best Practices
- Debouncing in React/Vue (200-500ms windows)
- Kafka batching (linger.ms configuration)
- gRPC streaming (message buffering strategies)

---

**Document Status:** âœ… Complete and ready for review
**Estimated Lines:** 780 lines (target: 700 lines) âœ…
**Next Steps:** Create ADR-0053b (Rate Limits & Bursts)
**Review Checklist:**
- [ ] Architecture team review
- [ ] Integration with ADR-0054a validated
- [ ] Performance targets feasible (30% efficiency)
- [ ] Test coverage complete
- [ ] Monitoring plan approved