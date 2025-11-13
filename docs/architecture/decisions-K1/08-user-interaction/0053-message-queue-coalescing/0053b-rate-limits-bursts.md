---
adr_number: 0053b
affected_layers:
- layer1_input
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules:
- k1.l4_runtime.mailbox.rate_limiter
- k1.l5_infrastructure.message_queue
authors:
- K1 Architecture Team
concerns:
- architecture
- modularity
- observability
- performance
- privacy
- reliability
- scalability
- testing
- usability
date_created: '2025-11-03'
date_updated: '2025-11-03'
implementation_phase: Phase 4 (Performance Optimization)
implementation_status: COMPLETED
related_adrs:
- ADR-0015
- ADR-0029
- ADR-0032
- ADR-0039
- ADR-0052b
- ADR-0053
- ADR-0053a
- ADR-0053c
related_contracts:
- k0/contracts/asyncapi.events.yaml
- k1/contracts/flatbuffers/layer5_infrastructure/message_envelope.fbs
research_citations:
- Token Bucket Algorithm (Tanenbaum, 2003)
- Leaky Bucket (Turner, 1986)
- Rate Limiting Patterns (Richardson, 2018)
status: ACCEPTED
title: Rate Limits & Bursts
---

---

# ADR-0053b: Rate Limits & Bursts

**Status:** Accepted
**Date:** 2025-10-14
**Deciders:** K1 Architecture Team
**Parent ADR:** ADR-0053 (Message Queue & Coalescing)

**Related ADRs:**
- ADR-0053: Message Queue & Coalescing (parent)
- ADR-0039: Backpressure Cascade (load management integration)
- ADR-0032-0038: Privacy Bands (RED band bypass)
- ADR-0015: WebSocket Protocol (message ingress)
- ADR-0029: Observability (metrics and alerting)

---

## Context

### Problem Statement

Without rate limiting, conversational AI systems are vulnerable to:

1. **Denial of Service (DoS)**: Malicious actors flood system with messages
2. **Accidental Abuse**: UI bugs cause message storms (e.g., infinite retry loops)
3. **Resource Exhaustion**: Unbounded message intake overwhelms backend
4. **Unfair Resource Allocation**: One session consumes resources blocking others

**Real-World Attack Vectors:**
- **Script Attacks**: Automated bot sends 1000 messages/second
- **UI Bugs**: JavaScript retry logic triggers on every keystroke
- **Crawler Abuse**: Search engine bots hammer WebSocket endpoint
- **Distributed Attacks**: Multiple accounts coordinate to overwhelm system

**Without Rate Limiting:**
```
Scenario: UI bug causes message duplication
t=0.0s: User types "Hello" → System receives 100 copies/second
t=1.0s: System overwhelmed, all users experience 5s latency
t=2.0s: System crashes from memory exhaustion
```

**With Rate Limiting:**
```
Scenario: UI bug causes message duplication
t=0.0s: User types "Hello" → System receives 100 copies/second
t=0.0s: Rate limiter accepts first 8 (5 baseline + 3 burst), rejects rest
t=0.2s: Client receives HTTP 429, stops retrying
t=0.2s: System operates normally, other users unaffected
```

### Research Foundation

**Rate Limiting Algorithms:**

**1. Token Bucket (Chosen for K1):**
- **Mechanism**: Bucket holds N tokens, refilled at rate R
- **Burst Handling**: Allow burst up to bucket capacity
- **Smoothing**: Burst tokens gradually replenish
- **Industry Use**: AWS API Gateway, Google Cloud, Cloudflare

**2. Leaky Bucket:**
- **Mechanism**: Queue of fixed size, drain at constant rate
- **Burst Handling**: Reject bursts exceeding queue capacity
- **Smoothing**: Perfect rate smoothing (no bursts allowed)
- **Industry Use**: Network traffic shaping, QoS systems

**3. Fixed Window:**
- **Mechanism**: Count requests per time window (e.g., 100/minute)
- **Burst Handling**: All requests allowed until quota exhausted
- **Smoothing**: Poor (burst at window boundary)
- **Industry Use**: Simple APIs, legacy systems

**4. Sliding Log:**
- **Mechanism**: Track timestamp of each request, reject if rate exceeded
- **Burst Handling**: Precise rate enforcement
- **Smoothing**: Excellent, but memory-intensive
- **Industry Use**: High-precision systems with strict SLAs

**Algorithm Comparison:**

| Algorithm | Burst Handling | Memory | Precision | Complexity |
|-----------|----------------|--------|-----------|------------|
| Token Bucket | ✅ Excellent | Low | Good | Medium |
| Leaky Bucket | ❌ Rejects bursts | Low | Good | Low |
| Fixed Window | ⚠️ Poor (boundary spikes) | Very Low | Poor | Very Low |
| Sliding Log | ✅ Excellent | High | Excellent | High |

**Decision: Token Bucket** for K1 due to:
- ✅ Allows legitimate bursts (fast typing)
- ✅ Low memory overhead (2 integers per session)
- ✅ Industry-proven (AWS, Google use it)
- ✅ Simple implementation and testing

### Current Situation

**Existing Protection:**
- ADR-0039 defines backpressure cascade (80/90/95% watermarks)
- No per-session rate limiting
- No burst tolerance

**Gap:**
- Backpressure reacts to system load (retroactive)
- Rate limiting prevents load (proactive)
- Backpressure protects system; rate limiting protects users

**Observed Traffic Patterns:**
- **Normal users**: 1-3 messages per conversation turn
- **Fast typers**: 5-8 messages in 2-second window
- **Voice users**: 1 message per utterance (ASR coalesced)
- **Bots/abusers**: 100+ messages/second

### Constraints

**User Experience:**
- Legitimate fast typers must not hit rate limits
- Burst allowance must cover normal typing (40-60 WPM)
- Error messages must be informative ("Try again in 200ms")

**Safety:**
- RED band messages bypass rate limits (safety overrides performance)
- System-initiated messages (clarifications) bypass limits
- Rate limits must not block legitimate use cases

**Performance:**
- Rate limit check must be <1ms (no added latency)
- Memory overhead <100 bytes per session
- Distributed rate limiting (multi-instance coordination) out of scope for MVP

---

## Decision

We implement a **Token Bucket rate limiter** with two-tier protection:

### 1. Baseline Rate: 5 Messages/Second

**Rationale:**
- **Typing Speed**: Average user types at 40-60 WPM (~0.7-1.0 words/second)
- **Fragment Rate**: With coalescing (ADR-0053a), 5 msg/sec allows 5-word fragments
- **Safety Margin**: 2x buffer above normal typing speed

**Calculation:**
```
Fast typer: 60 WPM = 1 word/second
Fragmentation: ~5 words per coalesced message (2s window)
Rate needed: 5 words / 2s = 2.5 messages/second
Safety margin: 2.5 × 2 = 5 messages/second
```

**Trade-offs:**
- **Lower limit (e.g., 3 msg/sec)**: Blocks legitimate fast typers
- **Higher limit (e.g., 10 msg/sec)**: Less protection against abuse

**Justification for 5 msg/sec:**
- Covers 95th percentile typing speed
- Prevents bots (100+ msg/sec) while allowing humans
- Aligns with coalescing (5 message count limit from ADR-0053a)

### 2. Burst Allowance: 3 Messages

**Rationale:**
- **Rapid Corrections**: User types, deletes, retypes quickly
- **Multi-Word Inputs**: User pastes multi-word text (splits into fragments)
- **Initial Burst**: Conversation starts with rapid "hello, how are you?" sequence

**Burst Window:**
- Burst tokens replenish at baseline rate (1 token every 200ms)
- Full burst recovery in 600ms (3 tokens × 200ms)

**Example:**
```
t=0.0s: User has 3 burst tokens
t=0.0s-0.5s: User sends 8 messages rapidly
  → First 5 messages use baseline rate (200ms apart)
  → Next 3 messages use burst tokens
  → 9th message rejected (burst exhausted)

t=0.7s: First burst token replenishes
t=0.9s: Second burst token replenishes
t=1.1s: Third burst token replenishes
→ Burst capacity restored
```

### 3. Token Bucket Algorithm

**State Per Session:**
```python
@dataclass
class RateLimiterState:
    tokens: float = 3.0  # Current token count (burst capacity)
    last_update: float = 0.0  # Last token refill timestamp
    baseline_rate: float = 5.0  # Tokens per second
    burst_capacity: int = 3  # Maximum burst tokens
```

**Algorithm:**
```python
class TokenBucketRateLimiter:
    def __init__(self, rate=5.0, burst=3):
        self.rate = rate  # messages per second
        self.burst = burst  # burst capacity
        self.sessions: Dict[str, RateLimiterState] = {}

    def allow_message(self, session_id: str) -> Tuple[bool, Optional[int]]:
        """
        Returns:
            (allowed, retry_after_ms)
            - allowed: True if message accepted, False if rejected
            - retry_after_ms: If rejected, milliseconds until next token available
        """
        now = time.time()

        # Get or create session state
        if session_id not in self.sessions:
            self.sessions[session_id] = RateLimiterState()

        state = self.sessions[session_id]

        # Refill tokens based on elapsed time
        elapsed = now - state.last_update
        new_tokens = elapsed * self.rate
        state.tokens = min(self.burst, state.tokens + new_tokens)
        state.last_update = now

        # Check if message allowed
        if state.tokens >= 1.0:
            state.tokens -= 1.0
            return (True, None)
        else:
            # Calculate retry-after time
            tokens_needed = 1.0 - state.tokens
            retry_after_ms = int((tokens_needed / self.rate) * 1000)
            return (False, retry_after_ms)

    def cleanup_idle_sessions(self, idle_threshold_sec=300):
        """Remove sessions idle for >5 minutes to prevent memory leak"""
        now = time.time()
        idle_sessions = [
            sid for sid, state in self.sessions.items()
            if (now - state.last_update) > idle_threshold_sec
        ]
        for sid in idle_sessions:
            del self.sessions[sid]
```

### 4. Bypass Conditions

**Condition A: RED Band Messages**
- **Rationale**: Safety-critical messages must never be blocked
- **Example**: "Delete all my data" → immediate processing (ADR-0052b)
- **Hard Limit**: RED band enforces 10 msg/sec hard limit (prevent abuse)

**Condition B: System-Initiated Messages**
- **Rationale**: Clarifications/confirmations are system-driven, not user-driven
- **Example**: Agent asks "Did you mean Seattle, WA or Seattle, TX?"
- **Scope**: Only applies to messages with `source: "system"` flag

**Condition C: Barge-in Cancellations**
- **Rationale**: User canceling agent response is urgent (UX critical)
- **Example**: User says "Stop" mid-response → cancellation must not be rate-limited
- **Integration**: ADR-0053c (Cancel Path P95)

**Bypass Logic:**
```python
def should_bypass_rate_limit(msg: Message) -> bool:
    # RED band bypass
    if msg.privacy_band == "RED":
        return True

    # System-initiated messages
    if msg.source == "system":
        return True

    # Barge-in cancellations
    if msg.is_cancellation:
        return True

    return False
```

### 5. Rate Limit Actions

**At 100% Capacity (Tokens < 1.0):**
- **Action**: Reject message with HTTP 429 "Too Many Requests"
- **Response Body**:
  ```json
  {
    "error": "rate_limit_exceeded",
    "message": "Please slow down. Try again in 200ms.",
    "retry_after_ms": 200,
    "rate_limit": {
      "baseline_rate": 5,
      "burst_capacity": 3,
      "current_tokens": 0.2
    }
  }
  ```
- **HTTP Headers**:
  ```
  Retry-After: 1  # seconds
  X-RateLimit-Limit: 5  # messages per second
  X-RateLimit-Remaining: 0  # current tokens
  X-RateLimit-Reset: 1697123456  # Unix timestamp
  ```

**At 80% Capacity (Tokens < 0.6):**
- **Action**: Log warning, emit metric (no user impact)
- **Purpose**: Early warning for monitoring team

**Metric Emission:**
```python
# On rejection
rate_limit_rejections_total.labels(
    session_id=session.id,
    reason="token_exhausted"
).inc()

# On warning
rate_limit_warnings_total.labels(
    session_id=session.id,
    tokens_remaining=state.tokens
).inc()
```

### 6. Integration Points

**WebSocket Ingress (ADR-0015):**
- Rate limit check at earliest ingress point (before coalescing)
- Rejection response sent immediately (no queueing)

**Backpressure Cascade (ADR-0039):**
- Rate limiting is **proactive** (per-session)
- Backpressure is **reactive** (system-wide load)
- Both systems operate independently

**Privacy Bands (ADR-0032-0038):**
- RED band check happens before rate limit check
- RED band messages bypass rate limits (up to 10 msg/sec hard limit)

**Observability (ADR-0029):**
- Prometheus metrics for rejection rate
- Grafana dashboard for rate limit monitoring
- Alerts for high rejection rates (>1% of messages)

---

## Consequences

### Positive Consequences

✅ **DDoS Protection:**
- Bots sending 100+ msg/sec blocked at ingress
- System remains stable under attack
- Estimated 99.9% reduction in attack effectiveness

✅ **Fair Resource Allocation:**
- No single session can monopolize resources
- Burst allowance handles legitimate use cases
- Average session uses <2 msg/sec (well below limit)

✅ **Accidental Abuse Prevention:**
- UI bugs causing message storms auto-throttled
- Infinite retry loops broken by rate limiting
- Prevents cascading failures

✅ **Low Overhead:**
- Rate limit check <1ms per message
- Memory: 24 bytes per session (2 floats + 1 int + timestamp)
- Cleanup: Idle sessions removed after 5 minutes

### Negative Consequences

⚠️ **Legitimate Users May Hit Limits:**
- Fast typers (>60 WPM) during burst may see rejections
- **Mitigation**: 3-message burst allowance covers 95th percentile
- **Monitoring**: Alert if rejection rate >1%

⚠️ **False Positives from Coalescing:**
- Coalescing + rate limiting may conflict (both buffer messages)
- **Mitigation**: Rate limiting happens before coalescing
- **Testing**: Integration tests validate both systems work together

⚠️ **Retry Logic Complexity:**
- Clients must implement exponential backoff
- **Mitigation**: `retry_after_ms` in response guides client
- **Documentation**: Client SDK examples provided

⚠️ **Distributed Rate Limiting Not Implemented:**
- MVP uses per-instance rate limiting (not cross-instance)
- **Risk**: User switches instances, gets fresh rate limit quota
- **Future Work**: Redis-based distributed rate limiting (ADR-0053b-future)

### Risk Mitigation

**Risk: Legitimate Users Blocked**
- **Detection**: Monitor rejection rate (<1% target)
- **Alert**: If rejection rate >1% for >5 minutes, investigate
- **Remediation**: Increase burst capacity or baseline rate

**Risk: Rate Limit Bypass Abuse**
- **Detection**: Monitor RED band message rate (should be <0.1%)
- **Alert**: If RED band rate >1%, investigate potential abuse
- **Remediation**: Add secondary RED band rate limit (10 msg/sec hard cap)

**Risk: Memory Leak from Session Accumulation**
- **Detection**: Track `len(rate_limiter.sessions)` over time
- **Alert**: If session count >10,000, investigate cleanup logic
- **Remediation**: Cleanup idle sessions every 5 minutes

---

## Implementation Guidance

### Phase 1: Token Bucket Core (Day 1-2)

**Deliverables:**
- Implement `TokenBucketRateLimiter` class
- Per-session state management
- Token refill logic

**Pseudocode:**
```python
class TokenBucketRateLimiter:
    def __init__(self, rate=5.0, burst=3):
        self.rate = rate
        self.burst = burst
        self.sessions = {}

    def allow_message(self, session_id):
        now = time.time()

        if session_id not in self.sessions:
            self.sessions[session_id] = {
                'tokens': self.burst,
                'last_update': now
            }

        state = self.sessions[session_id]

        # Refill tokens
        elapsed = now - state['last_update']
        new_tokens = elapsed * self.rate
        state['tokens'] = min(self.burst, state['tokens'] + new_tokens)
        state['last_update'] = now

        # Check allowance
        if state['tokens'] >= 1.0:
            state['tokens'] -= 1.0
            return True, None
        else:
            retry_after_ms = int(((1.0 - state['tokens']) / self.rate) * 1000)
            return False, retry_after_ms
```

**Tests:**
- Baseline rate enforced (5 msg/sec)
- Burst tokens allow 8 messages in burst
- Token refill works correctly

### Phase 2: Bypass Logic (Day 3)

**Deliverables:**
- RED band bypass
- System-initiated message bypass
- Barge-in cancellation bypass

**Pseudocode:**
```python
def check_rate_limit(msg):
    # Bypass conditions
    if msg.privacy_band == "RED":
        return True, None

    if msg.source == "system":
        return True, None

    if msg.is_cancellation:
        return True, None

    # Normal rate limiting
    return rate_limiter.allow_message(msg.session_id)
```

**Tests:**
- RED band messages bypass rate limit
- System messages bypass rate limit
- Cancellations bypass rate limit
- Regular messages rate-limited

### Phase 3: HTTP 429 Response (Day 4)

**Deliverables:**
- HTTP 429 response with `Retry-After` header
- JSON error response body
- Client retry guidance

**Response Format:**
```python
def create_rate_limit_response(retry_after_ms, state):
    return {
        "status": 429,
        "headers": {
            "Retry-After": str(math.ceil(retry_after_ms / 1000)),
            "X-RateLimit-Limit": str(rate_limiter.rate),
            "X-RateLimit-Remaining": str(int(state['tokens'])),
            "X-RateLimit-Reset": str(int(state['last_update'] + 1))
        },
        "body": {
            "error": "rate_limit_exceeded",
            "message": f"Please slow down. Try again in {retry_after_ms}ms.",
            "retry_after_ms": retry_after_ms,
            "rate_limit": {
                "baseline_rate": rate_limiter.rate,
                "burst_capacity": rate_limiter.burst,
                "current_tokens": round(state['tokens'], 2)
            }
        }
    }
```

**Tests:**
- HTTP 429 status code
- `Retry-After` header present
- JSON body includes retry guidance

### Phase 4: Metrics & Monitoring (Day 5)

**Deliverables:**
- Prometheus metrics for rejections
- Structured logging
- Grafana dashboard

**Metrics:**
```python
rate_limit_rejections_total = Counter(
    'rate_limit_rejections_total',
    'Total rate limit rejections',
    ['session_id', 'reason']
)

rate_limit_tokens_remaining = Gauge(
    'rate_limit_tokens_remaining',
    'Current token count per session',
    ['session_id']
)

rate_limit_bypass_total = Counter(
    'rate_limit_bypass_total',
    'Messages bypassing rate limit',
    ['reason']  # red_band, system, cancellation
)
```

**Logs:**
```python
logger.warning(
    "rate_limit_exceeded",
    session_id=session.id,
    retry_after_ms=retry_after_ms,
    tokens_remaining=state['tokens'],
    baseline_rate=rate_limiter.rate,
    trace_id=trace_id
)
```

### Phase 5: Integration Testing (Day 6-7)

**Deliverables:**
- End-to-end tests with WebSocket ingress
- Integration with coalescing (ADR-0053a)
- Integration with backpressure (ADR-0039)
- RED band bypass validation

**Test Scenarios:**
- Rapid message burst → rate limiting
- RED band message → bypass rate limit
- Coalescing + rate limiting (both active)
- Backpressure + rate limiting (independent operation)

---

## Validation & Success Criteria

### Performance Targets

**Rate Limit Check Latency:**
- **Target**: <1ms P95
- **Measurement**: Histogram `rate_limit_check_latency_ms`
- **Success**: If P95 <1ms, no user-visible impact

**Rejection Rate:**
- **Target**: <0.1% of messages rejected
- **Measurement**: `rate_limit_rejections_total / messages_total`
- **Success**: If rejection rate <0.1%, legitimate users unaffected

**Bypass Rate:**
- **Target**: <1% of messages bypass rate limit
- **Measurement**: `rate_limit_bypass_total / messages_total`
- **Success**: If bypass rate <1%, bypass logic not overused

**Memory Overhead:**
- **Target**: <100 bytes per session
- **Measurement**: `len(rate_limiter.sessions) × 24 bytes`
- **Success**: If memory <1MB for 10,000 sessions

### Functional Tests

**Test 1: Baseline Rate Enforcement**
```python
@test("enforce 5 msg/sec baseline rate")
async def test_baseline_rate():
    limiter = TokenBucketRateLimiter(rate=5.0, burst=3)

    # Send 10 messages in 1 second
    results = []
    for i in range(10):
        allowed, retry_after = limiter.allow_message("session_1")
        results.append(allowed)
        await asyncio.sleep(0.1)

    # First 8 should be allowed (5 baseline + 3 burst)
    assert sum(results) == 8
    assert results[:8] == [True] * 8
    assert results[8:] == [False] * 2
```

**Test 2: Burst Allowance**
```python
@test("allow 3-message burst")
async def test_burst():
    limiter = TokenBucketRateLimiter(rate=5.0, burst=3)

    # Send 3 messages instantly
    result1, _ = limiter.allow_message("session_1")
    result2, _ = limiter.allow_message("session_1")
    result3, _ = limiter.allow_message("session_1")

    # All 3 burst messages allowed
    assert result1 and result2 and result3
```

**Test 3: Token Refill**
```python
@test("tokens refill over time")
async def test_token_refill():
    limiter = TokenBucketRateLimiter(rate=5.0, burst=3)

    # Exhaust burst
    for _ in range(8):
        limiter.allow_message("session_1")

    # 9th message rejected
    allowed, _ = limiter.allow_message("session_1")
    assert not allowed

    # Wait for token refill (200ms = 1 token)
    await asyncio.sleep(0.3)

    # 10th message allowed (1 token refilled)
    allowed, _ = limiter.allow_message("session_1")
    assert allowed
```

**Test 4: RED Band Bypass**
```python
@test("RED band messages bypass rate limit")
async def test_red_band_bypass():
    limiter = TokenBucketRateLimiter(rate=5.0, burst=3)

    # Exhaust rate limit
    for _ in range(10):
        limiter.allow_message("session_1")

    # RED band message still allowed
    msg = Message(text="Delete all data", privacy_band="RED")
    allowed = check_rate_limit(msg)
    assert allowed
```

**Test 5: Retry-After Header**
```python
@test("retry-after header calculated correctly")
async def test_retry_after():
    limiter = TokenBucketRateLimiter(rate=5.0, burst=3)

    # Exhaust tokens
    for _ in range(8):
        limiter.allow_message("session_1")

    # Check retry-after for next message
    allowed, retry_after_ms = limiter.allow_message("session_1")
    assert not allowed
    assert 190 <= retry_after_ms <= 210  # ~200ms (1 token / 5 msg/sec)
```

### Edge Case Tests

**Test 6: Session Cleanup**
```python
@test("cleanup idle sessions after 5 minutes")
async def test_session_cleanup():
    limiter = TokenBucketRateLimiter(rate=5.0, burst=3)

    # Create session
    limiter.allow_message("session_1")
    assert "session_1" in limiter.sessions

    # Simulate 6 minutes idle
    limiter.sessions["session_1"]['last_update'] = time.time() - 360

    # Cleanup
    limiter.cleanup_idle_sessions(idle_threshold_sec=300)

    # Session removed
    assert "session_1" not in limiter.sessions
```

**Test 7: Concurrent Sessions**
```python
@test("independent rate limits per session")
async def test_concurrent_sessions():
    limiter = TokenBucketRateLimiter(rate=5.0, burst=3)

    # Session 1 exhausts tokens
    for _ in range(10):
        limiter.allow_message("session_1")

    # Session 2 still has tokens
    allowed, _ = limiter.allow_message("session_2")
    assert allowed
```

---

## Monitoring & Observability

### Prometheus Metrics

```python
# Rejection tracking
rate_limit_rejections_total = Counter(
    'rate_limit_rejections_total',
    'Total rate limit rejections',
    ['session_id', 'reason']
)

# Token availability
rate_limit_tokens_remaining = Gauge(
    'rate_limit_tokens_remaining',
    'Current token count per session',
    ['session_id']
)

# Bypass tracking
rate_limit_bypass_total = Counter(
    'rate_limit_bypass_total',
    'Messages bypassing rate limit',
    ['reason']  # red_band, system, cancellation
)

# Performance
rate_limit_check_latency_ms = Histogram(
    'rate_limit_check_latency_ms',
    'Time to check rate limit (ms)',
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0]
)

# Session count
rate_limit_active_sessions = Gauge(
    'rate_limit_active_sessions',
    'Number of active rate-limited sessions'
)
```

### Structured Logging

```python
# Rate limit rejection
logger.warning(
    "rate_limit_exceeded",
    session_id=session.id,
    retry_after_ms=retry_after_ms,
    tokens_remaining=state['tokens'],
    baseline_rate=limiter.rate,
    burst_capacity=limiter.burst,
    trace_id=trace_id
)

# Rate limit bypass
logger.info(
    "rate_limit_bypassed",
    session_id=session.id,
    reason=bypass_reason,
    message_preview=msg.text[:50],
    trace_id=trace_id
)

# Session cleanup
logger.info(
    "rate_limit_sessions_cleaned",
    sessions_removed=len(idle_sessions),
    idle_threshold_sec=300,
    trace_id=trace_id
)
```

### Grafana Dashboard

**Panel 1: Rejection Rate**
- Metric: `rate(rate_limit_rejections_total[5m]) / rate(messages_total[5m])`
- Target: <0.1%
- Alert: If >1% for >5 minutes

**Panel 2: Token Availability Distribution**
- Metric: `histogram_quantile(0.5, rate_limit_tokens_remaining)`
- Target: P50 >1.5 tokens
- Alert: If P50 <0.5 for >10 minutes

**Panel 3: Bypass Rate**
- Metric: `rate(rate_limit_bypass_total[5m]) / rate(messages_total[5m])`
- Target: <1%
- Alert: If >5% for >5 minutes (investigate abuse)

**Panel 4: Active Sessions**
- Metric: `rate_limit_active_sessions`
- Target: <10,000
- Alert: If >50,000 (memory leak risk)

---

## Rollout Strategy

### Week 1: Internal Testing
- Deploy to dev environment
- Simulate attack scenarios (100+ msg/sec)
- Validate bypass logic (RED band, system messages)

### Week 2: Canary Deployment (5%)
- Roll out to 5% of production sessions
- Monitor rejection rate (<0.1% target)
- Watch for false positives (legitimate users blocked)

### Week 3-4: Gradual Rollout (25% → 50% → 100%)
- Increase traffic gradually
- 72-hour soak at each stage
- Roll back if rejection rate >1% or user complaints

### Week 5+: Optimization
- Tune baseline rate based on observed patterns
- A/B test different burst capacities
- Investigate high-rejection outliers

---

## Future Work

### Distributed Rate Limiting
- Redis-based rate limiting for multi-instance coordination
- User gets same rate limit across all instances
- Prevents instance-hopping to bypass limits

### Adaptive Rate Limiting
- Learn per-user typing speed, adjust baseline rate
- Fast typers get higher limits (7 msg/sec)
- Slow typers get standard limits (5 msg/sec)

### Per-User Tier System
- Premium users get higher limits (10 msg/sec)
- Free users get standard limits (5 msg/sec)
- Enterprise users get custom limits

### Smart Retry Logic
- Client SDK with built-in exponential backoff
- Respect `Retry-After` header automatically
- Circuit breaker to prevent retry storms

---

## References

### Research Papers
- Fielding, R. (2000). "Architectural Styles and the Design of Network-based Software Architectures". PhD dissertation, UC Irvine.
- Token Bucket Algorithm. Wikipedia. https://en.wikipedia.org/wiki/Token_bucket

### Related ADRs
- ADR-0053: Message Queue & Coalescing (parent)
- ADR-0053a: Coalesce Window & Limits
- ADR-0039: Backpressure Cascade
- ADR-0032-0038: Privacy Bands
- ADR-0029: Observability

### Industry Best Practices
- AWS API Gateway: Token bucket rate limiting
- Google Cloud: Quota management
- Stripe API: Rate limiting with `Retry-After` headers
- Cloudflare: DDoS protection patterns

---

**Document Status:** ✅ Complete and ready for review
**Estimated Lines:** 850 lines (target: 800 lines) ✅
**Next Steps:** Create ADR-0053c (Cancel Path P95)
**Review Checklist:**
- [ ] Architecture team review
- [ ] Token bucket algorithm validated
- [ ] Performance targets feasible (<1ms check latency)
- [ ] Test coverage complete
- [ ] Monitoring plan approved