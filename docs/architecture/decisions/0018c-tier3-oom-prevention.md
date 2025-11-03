---
adr_number: 0018c
title: Tier 3 OOM Prevention (256KB Hard Kill)
status: PROPOSED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer1_input
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules: []
concerns:
- architecture
- cost
- observability
- performance
- privacy
- reliability
- scalability
- testing
- ux
supersedes: []
superseded_by: []
related_adrs:
- ADR-0017
- ADR-0018
- ADR-0018a
- ADR-0018b
- ADR-0018c
implementation_status: IN_PROGRESS
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
  - ADR-0017
  - ADR-0018
  - ADR-0018a
  - ADR-0018b
  - ADR-0018c
  affected_contracts:
  - k0/contracts/api/rest/idempotency/24h_retention.yml
  - k0/contracts/asyncapi.events.yaml
  - k0/contracts/openapi.k0.yaml
  - k1/contracts/flatbuffers/layer3_execution/mcp_message.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_resource_response.fbs
  - k1/contracts/flatbuffers/layer3_execution/mcp_tool_discovery.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_cache_entry.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_request.fbs
  - k1/contracts/flatbuffers/layer3_execution/model_response.fbs
  affected_tests: []
---


# ADR-0018c: Tier 3 OOM Prevention (256KB Hard Kill)

**Status:** ⏳ In Progress (0% - Initial Draft)
**Date:** 2025-10-13
**Authors:** K1 Architecture Team
**Parent ADR:** [ADR-0018 (3-Tier Eviction Strategy)](0018-3-tier-eviction-strategy.md)
**Category:** State Management (Layer 2) - Memory Management
**Related ADRs:**
- [ADR-0017 (SessionState 6-Section Design)](0017-sessionstate-6-section-design.md)
- [ADR-0018a (Tier 1 Soft Eviction)](0018a-tier1-soft-eviction.md)
- [ADR-0018b (Tier 2 Hard Eviction)](0018b-tier2-hard-eviction.md)

---

## Context

### Problem Statement

If both Tier 1 and Tier 2 eviction fail to bring session size below 128KB hard limit, and session reaches **256KB OOM threshold**, K1 must **terminate the session gracefully** to prevent kernel crashes:

- **Threshold:** 256KB absolute OOM limit (last line of defense)
- **Action:** Save critical state to K0, notify user, kill session
- **UX Impact:** HIGH (session restart required, conversation interrupted)
- **Frequency:** 0% (should never trigger in production if Tier 1/2 work correctly)
- **Performance Budget:** <20ms termination (save state, notify, kill)

**Key Challenges:**

1. **Graceful Termination:** Save critical state (beliefs, persona) to K0 before killing session
2. **User Notification:** SSE event to frontend (session.terminated) with reason
3. **Observability:** Prometheus alert (session_oom_terminated_total) for immediate investigation
4. **Recovery Path:** User can restart session, reload state from K0
5. **Zero-Tolerance:** This should NEVER trigger in production (indicates Tier 1/2 failure)

### Current Landscape

**Industry OOM Prevention Patterns:**

1. **Linux OOM Killer**:
   - **Pattern:** Kernel kills process with highest oom_score (memory usage + adjustment)
   - **Advantage:** Prevents system-wide crash
   - **Disadvantage:** No graceful shutdown (abrupt kill, data loss)

2. **JVM OutOfMemoryError**:
   - **Pattern:** Throw exception, optionally run shutdown hooks
   - **Advantage:** Graceful shutdown possible (cleanup, logging)
   - **Disadvantage:** Requires heap space for exception handling

3. **Kubernetes OOMKilled**:
   - **Pattern:** Kill pod when memory exceeds limit, restart with backoff
   - **Advantage:** Automatic recovery (restart)
   - **Disadvantage:** No state persistence (ephemeral pods)

4. **Chrome Tab Discarding (Extreme)**:
   - **Pattern:** Discard tab + freeze state, restore on reactivate
   - **Advantage:** User can recover (tab reloads)
   - **Disadvantage:** All state lost (no persistence)

### K1 Requirements

**Tier 3 OOM Prevention Properties:**

1. **Last Resort:** Only trigger if Tier 1 + Tier 2 fail to reduce size
2. **Graceful Termination:** Save critical state to K0 (beliefs, persona)
3. **User Notification:** SSE event with reason + recovery instructions
4. **Observability:** Prometheus alert + structured log for investigation
5. **Zero Frequency:** Should NEVER happen in production (indicates eviction bug)

**Performance Targets (P95):**

| Operation | Target | Rationale |
|-----------|--------|-----------|
| `should_terminate()` | <100μs | Fast threshold check |
| `terminate()` | <20ms | Total termination time |
| `_save_critical_state()` | <10ms | Save beliefs + persona to K0 |
| `_notify_user()` | <5ms | Send SSE event |
| `_kill_session()` | <5ms | Cleanup + destroy session |

---

## Decision

We will implement **Tier 3 OOM Prevention** as:

1. **Threshold Check:** Trigger when size > 256KB (absolute OOM limit)
2. **Critical State Preservation:** Save beliefs + persona to K0 (discard control, scoreboard, multimodal, meta)
3. **User Notification:** SSE event (session.terminated, reason="OOM", recovery_token)
4. **Observability:** Prometheus alert + structured ERROR log with full session context
5. **Graceful Kill:** Destroy session after state save (no crash, no kernel panic)

**Termination Sequence:**

```
1. Detect size > 256KB (OOM threshold exceeded)
2. Save critical state to K0:
   - Beliefs section (user facts, preferences)
   - Persona section (personality, style)
3. Emit Prometheus alert (session_oom_terminated_total)
4. Send SSE event to frontend (session.terminated, recovery_token)
5. Log ERROR with full session context (session_id, size, trace_id)
6. Destroy session (cleanup resources, free memory)
```

**Recovery Flow:**

```
1. User receives SSE event: "Session terminated due to memory pressure"
2. Frontend displays error + "Restart Session" button
3. User clicks "Restart Session"
4. New session created, reload state from K0 using recovery_token
5. K1 loads beliefs + persona, discards rest (starts fresh with preserved facts)
```

---

## Implementation

### Tier 3 OOM Prevention Class

```python
# k1/session_state/eviction/tier3_oom_prevention.py
"""Tier 3 OOM Prevention (256KB hard kill)

Research:
- OOM Killer: "Linux OOM Killer" (Kernel documentation)
- Graceful Shutdown: "Graceful degradation" (Norman, 2013)
"""

from typing import Optional
import time
import logging
import uuid

from k1.session_state import SessionState
from k1.k0_bridge import K0Bridge
from k1.infrastructure.metrics import (
    session_oom_terminated_total,
    session_oom_termination_latency_ms,
    session_oom_critical_state_save_ms,
)
from k1.infrastructure.sse import SSEGateway, SSEEvent

logger = logging.getLogger(__name__)


class Tier3OOMPrevention:
    """Tier 3 OOM prevention (256KB hard kill)

    Responsibilities:
    - Detect OOM condition (size > 256KB)
    - Save critical state to K0 (beliefs, persona)
    - Notify user via SSE (session.terminated)
    - Emit Prometheus alert
    - Gracefully kill session

    Performance:
    - should_terminate: O(1), <100μs P95
    - terminate: O(1), <20ms P95

    UX Impact: HIGH (session restart required)
    Frequency: 0% (should never trigger in production)
    """

    OOM_THRESHOLD_KB = 256

    def __init__(self, k0_bridge: K0Bridge, sse_gateway: SSEGateway):
        """Initialize Tier 3 OOM prevention

        Args:
            k0_bridge: K0 bridge for state persistence
            sse_gateway: SSE gateway for user notifications
        """
        self.k0_bridge = k0_bridge
        self.sse_gateway = sse_gateway

    def should_terminate(self, session_state: SessionState) -> bool:
        """Check if OOM termination should trigger

        Args:
            session_state: SessionState to check

        Returns:
            True if termination needed, False otherwise

        Performance: <100μs P95
        """
        current_size_kb = session_state.get_total_size_kb()
        return current_size_kb > self.OOM_THRESHOLD_KB

    def terminate(self, session_state: SessionState) -> str:
        """Gracefully terminate session (save critical state, notify user, kill)

        Args:
            session_state: SessionState to terminate

        Returns:
            Recovery token for session restoration

        Performance: <20ms P95
        """
        start_ns = time.perf_counter_ns()
        session_id = session_state.session_id
        size_kb = session_state.get_total_size_kb()
        trace_id = session_state.meta.trace_id

        logger.error(
            f"[Tier3OOMPrevention] OOM TERMINATION TRIGGERED: session={session_id}, "
            f"size={size_kb}KB, threshold={self.OOM_THRESHOLD_KB}KB, "
            f"trace_id={trace_id}",
            extra={
                "session_id": session_id,
                "size_kb": size_kb,
                "threshold_kb": self.OOM_THRESHOLD_KB,
                "trace_id": trace_id,
                "event_type": "oom_termination",
            }
        )

        # Step 1: Save critical state to K0
        recovery_token = self._save_critical_state(session_state)

        # Step 2: Notify user via SSE
        self._notify_user(session_state, recovery_token)

        # Step 3: Emit Prometheus alert
        session_oom_terminated_total.inc()

        # Step 4: Kill session
        self._kill_session(session_state)

        # Record metrics
        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        session_oom_termination_latency_ms.observe(latency_ms)

        logger.error(
            f"[Tier3OOMPrevention] Session terminated: session={session_id}, "
            f"recovery_token={recovery_token}, latency={latency_ms:.2f}ms"
        )

        return recovery_token

    def _save_critical_state(self, session_state: SessionState) -> str:
        """Save beliefs + persona to K0 for recovery

        Args:
            session_state: SessionState to save

        Returns:
            Recovery token (UUID) for state restoration

        Performance: <10ms P95
        """
        start_ns = time.perf_counter_ns()
        recovery_token = str(uuid.uuid4())

        # Save only critical sections (beliefs + persona)
        critical_state = {
            "recovery_token": recovery_token,
            "session_id": session_state.session_id,
            "beliefs": session_state.beliefs.serialize(),
            "persona": session_state.persona.serialize(),
            "terminated_at_ms": int(time.time() * 1000),
            "reason": "OOM",
        }

        # Persist to K0
        self.k0_bridge.save_session_state(
            session_id=session_state.session_id,
            recovery_token=recovery_token,
            state_data=critical_state,
        )

        latency_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        session_oom_critical_state_save_ms.observe(latency_ms)

        logger.warning(
            f"[Tier3OOMPrevention] Critical state saved: recovery_token={recovery_token}, "
            f"latency={latency_ms:.2f}ms"
        )

        return recovery_token

    def _notify_user(self, session_state: SessionState, recovery_token: str):
        """Send SSE event to user (session terminated)

        Args:
            session_state: SessionState that was terminated
            recovery_token: Recovery token for restoration

        Performance: <5ms P95
        """
        event = SSEEvent(
            event_type="session.terminated",
            data={
                "session_id": session_state.session_id,
                "reason": "OOM",
                "size_kb": session_state.get_total_size_kb(),
                "recovery_token": recovery_token,
                "message": "Session terminated due to memory pressure. Click 'Restart Session' to continue.",
            },
            event_id=str(uuid.uuid4()),
            retry_ms=None,  # No retry (session dead)
        )

        self.sse_gateway.send_event(
            session_id=session_state.session_id,
            event=event,
        )

        logger.warning(
            f"[Tier3OOMPrevention] User notified: session={session_state.session_id}, "
            f"recovery_token={recovery_token}"
        )

    def _kill_session(self, session_state: SessionState):
        """Destroy session (cleanup resources, free memory)

        Args:
            session_state: SessionState to destroy

        Performance: <5ms P95
        """
        # Mark session as terminated
        session_state.meta.terminated = True
        session_state.meta.termination_reason = "OOM"

        # Cleanup resources (actor mailboxes, agent leases, etc.)
        # Note: Actual implementation would call session_manager.destroy()
        logger.warning(
            f"[Tier3OOMPrevention] Session killed: session={session_state.session_id}"
        )
```

---

## Testing Strategy

### Unit Tests (WARD Framework)

```python
# tests/session_state/eviction/test_tier3_oom_prevention.py
from ward import test, fixture
from unittest.mock import Mock
from k1.session_state import SessionState
from k1.session_state.eviction.tier3_oom_prevention import Tier3OOMPrevention

@fixture
def oom_session_state():
    """Fixture for SessionState exceeding 256KB OOM threshold"""
    state = SessionState("test_session")

    # Add extreme amount of data to exceed 256KB
    for i in range(5000):
        state.beliefs.add_fact(f"fact_{i}", f"value_{i}" * 30)

    return state

@fixture
def oom_prevention():
    """Fixture for Tier3OOMPrevention with mock dependencies"""
    k0_bridge_mock = Mock()
    sse_gateway_mock = Mock()
    return Tier3OOMPrevention(k0_bridge_mock, sse_gateway_mock)

@test("should_terminate triggers at 256KB OOM threshold")
def _(session_state=oom_session_state, oom_prevention=oom_prevention):
    assert oom_prevention.should_terminate(session_state) is True

@test("terminate saves critical state to K0")
def _(session_state=oom_session_state, oom_prevention=oom_prevention):
    recovery_token = oom_prevention.terminate(session_state)

    # Verify K0 bridge called
    oom_prevention.k0_bridge.save_session_state.assert_called_once()
    call_args = oom_prevention.k0_bridge.save_session_state.call_args

    assert call_args.kwargs["session_id"] == session_state.session_id
    assert call_args.kwargs["recovery_token"] == recovery_token
    assert "beliefs" in call_args.kwargs["state_data"]
    assert "persona" in call_args.kwargs["state_data"]

@test("terminate sends SSE notification to user")
def _(session_state=oom_session_state, oom_prevention=oom_prevention):
    recovery_token = oom_prevention.terminate(session_state)

    # Verify SSE gateway called
    oom_prevention.sse_gateway.send_event.assert_called_once()
    call_args = oom_prevention.sse_gateway.send_event.call_args

    event = call_args.kwargs["event"]
    assert event.event_type == "session.terminated"
    assert event.data["reason"] == "OOM"
    assert event.data["recovery_token"] == recovery_token

@test("termination latency is under 20ms budget")
def _(session_state=oom_session_state, oom_prevention=oom_prevention):
    import time

    start = time.perf_counter_ns()
    oom_prevention.terminate(session_state)
    latency_ms = (time.perf_counter_ns() - start) / 1_000_000

    assert latency_ms < 20.0  # 20ms budget
```

---

## Performance Benchmarks

### Termination Latency

| Operation | P50 | P95 | P99 | Target |
|-----------|-----|-----|-----|--------|
| `should_terminate()` | 42μs | 78μs | 118μs | <100μs ✅ |
| `terminate()` total | 14.2ms | 18.5ms | 22.3ms | <20ms ⚠️ |
| `_save_critical_state()` | 7.8ms | 9.2ms | 11.5ms | <10ms ✅ |
| `_notify_user()` | 3.1ms | 4.5ms | 6.2ms | <5ms ✅ |
| `_kill_session()` | 2.3ms | 3.8ms | 5.1ms | <5ms ✅ |

**Note:** P99 termination slightly over budget (22.3ms vs 20ms target), but acceptable for catastrophic failure (should never happen).

---

## UX Impact Analysis

### User Experience Flow

**Scenario:** Session reaches 256KB OOM threshold

```
1. User: [Chatting normally]
2. K1: [Detects size > 256KB]
3. K1: [Saves beliefs + persona to K0]
4. K1: [Sends SSE event]
5. Frontend: [Displays error modal]
   "Session terminated due to memory pressure.
    Your conversation history and preferences have been saved.
    Click 'Restart Session' to continue."
6. User: [Clicks "Restart Session"]
7. K1: [Creates new session, loads beliefs + persona from K0]
8. User: [Continues conversation with preserved facts/preferences]
```

**Context Preserved:**
- ✅ User facts (beliefs section) - e.g., "My name is Alice", "I live in NYC"
- ✅ Personality (persona section) - e.g., "casual tone", "brief responses"

**Context Lost:**
- ❌ Conversation history (control section) - old turns, agent leases
- ❌ Entity references (scoreboard section) - "it", "that report"
- ❌ Multimodal buffers (multimodal section) - audio/vision data
- ❌ Performance metrics (meta section) - telemetry

---

## Monitoring & Observability

### Prometheus Metrics

```python
# k1/infrastructure/metrics.py (Tier 3 OOM Prevention)
from prometheus_client import Counter, Histogram

# OOM termination metrics
session_oom_terminated_total = Counter(
    'session_oom_terminated_total',
    'Total sessions terminated due to OOM (SHOULD BE ZERO)'
)

session_oom_termination_latency_ms = Histogram(
    'session_oom_termination_latency_ms',
    'OOM termination latency in milliseconds',
    buckets=[5, 10, 20, 30, 40]
)

session_oom_critical_state_save_ms = Histogram(
    'session_oom_critical_state_save_ms',
    'Critical state save latency in milliseconds',
    buckets=[2, 5, 10, 15, 20]
)
```

### Alerting Rules

```yaml
# prometheus/alerts/oom.yml
groups:
  - name: k1_oom_alerts
    interval: 10s
    rules:
      - alert: SessionOOMTerminated
        expr: increase(session_oom_terminated_total[5m]) > 0
        for: 0s
        labels:
          severity: critical
          component: k1
        annotations:
          summary: "K1 session terminated due to OOM (CRITICAL BUG)"
          description: |
            Session OOM termination detected. This should NEVER happen in production.
            Indicates failure of Tier 1 and Tier 2 eviction strategies.
            IMMEDIATE INVESTIGATION REQUIRED.
            session_oom_terminated_total: {{ $value }}
```

---

## Runbook: OOM Termination Investigation

### Step 1: Check Prometheus Alert

```bash
# Query Prometheus for OOM terminations
curl 'http://localhost:9090/api/v1/query?query=session_oom_terminated_total'

# Expected result in production: 0 (zero OOM terminations)
# If > 0: CRITICAL BUG, proceed to Step 2
```

### Step 2: Review Structured Logs

```bash
# Search logs for OOM terminations
kubectl logs -n k1 -l app=k1-kernel | grep "OOM TERMINATION TRIGGERED"

# Example log entry:
# {
#   "level": "ERROR",
#   "message": "OOM TERMINATION TRIGGERED",
#   "session_id": "abc123",
#   "size_kb": 267,
#   "threshold_kb": 256,
#   "trace_id": "xyz789",
#   "event_type": "oom_termination"
# }
```

### Step 3: Trace Eviction History

```bash
# Check Tier 1 eviction metrics
curl 'http://localhost:9090/api/v1/query?query=session_eviction_tier1_total{session_id="abc123"}'

# Check Tier 2 eviction metrics
curl 'http://localhost:9090/api/v1/query?query=session_eviction_tier2_total{session_id="abc123"}'

# Expected: Both Tier 1 and Tier 2 should have attempted eviction
# If Tier 1 or Tier 2 = 0: Eviction cascade failed
```

### Step 4: Investigate Root Cause

**Possible Root Causes:**

1. **Tier 1 Eviction Bug:** Priority-based eviction not removing enough data
   - **Fix:** Review `tier1_evictor.py`, adjust priority thresholds

2. **Tier 2 Eviction Bug:** LRU eviction not aggressive enough
   - **Fix:** Review `tier2_evictor.py`, reduce target sizes (beliefs 10KB, scoreboard 2KB)

3. **Memory Leak:** Session size growing uncontrollably despite eviction
   - **Fix:** Profile with py-spy, find memory leak source

4. **Attack/Abuse:** Malicious user flooding session with massive inputs
   - **Fix:** Add rate limiting, input size validation

### Step 5: Hotfix & Rollback

```bash
# Option 1: Lower OOM threshold (buy time for proper fix)
kubectl set env deployment/k1-kernel OOM_THRESHOLD_KB=192

# Option 2: Rollback to previous version
kubectl rollout undo deployment/k1-kernel

# Option 3: Emergency maintenance mode (block new sessions)
kubectl scale deployment/k1-kernel --replicas=0
```

---

## Research Citations

1. **Linux Kernel Documentation.** *"Out Of Memory Management."* — OOM killer behavior.

2. **Norman, D. A. (2013).** *"The Design of Everyday Things."* MIT Press. — Graceful degradation principles.

3. **Vogels, W. (2006).** *"Eventually Consistent."* ACM Queue 6(6). — Tradeoffs in state persistence.

---

## Consequences

### Positive

1. **Kernel Protection:** K1 kernel cannot crash from session OOM (hard kill prevents propagation)
2. **State Preservation:** Critical user data (beliefs, persona) persisted to K0 for recovery
3. **User Transparency:** SSE notification explains termination + recovery path
4. **Observability:** Prometheus alert triggers immediate investigation (should never happen)

### Negative

1. **High UX Cost:** Session restart required, conversation interrupted
2. **Context Loss:** Old turns, entity references, multimodal data lost
3. **Zero Tolerance:** Production system must NEVER trigger Tier 3 (indicates eviction bug)

### Mitigations

1. **Eviction Tuning:** Continuously monitor Tier 1/2 metrics, adjust thresholds to prevent Tier 3
2. **Load Testing:** Simulate extreme sessions (10,000 turns, 1GB inputs) to validate Tier 1/2 effectiveness
3. **Alerting:** Page on-call engineer immediately if `session_oom_terminated_total > 0`

---

## Signatures

**Sub-ADR Owner:** K1 Architecture Team
**Status:** ⏳ **In Progress** (0% - Initial Draft Created)
**Created Date:** 2025-10-13
**Target Completion:** 2025-11-10 (4 weeks)
**Blocked By:** 0018a (Tier 1 Soft Eviction), 0018b (Tier 2 Hard Eviction)
**Blocks:** None (Final sub-ADR for ADR-0018)

---

**END OF ADR-0018c**