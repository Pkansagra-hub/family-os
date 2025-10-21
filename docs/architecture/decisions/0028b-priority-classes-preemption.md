# ADR-0028b: Priority Classes & Preemption

**Status:** Accepted
**Date:** 2025-06-15
**Author:** K1 Architecture Team
**Parent ADR:** [ADR-0028: Weighted Fair Queuing Scheduler](0028-weighted-fair-queuing-scheduler.md)
**Related ADRs:**
- [ADR-0028a: WFQ Scheduler Algorithm & Virtual Time](0028a-wfq-scheduler-algorithm-virtual-time.md)
- [ADR-0028c: Starvation Prevention (Max Wait 5s)](0028c-starvation-prevention-max-wait-5s.md)

---

## Context

Safety-critical sessions require immediate response, even if lower-priority sessions are running:

### Preemption Requirement

**Scenario:** Background learning session running long inference (5 seconds):
- **T=0s:** Background session starts inference on GPU
- **T=2s:** Safety alert arrives (user distress detected)
- **Current behavior (no preemption):** Safety waits 3 seconds → UNACCEPTABLE
- **Required behavior (preemption):** Interrupt Background immediately, run Safety

**Problem:** Without preemption, high-priority sessions experience unacceptable latency.

### Industry Preemption Patterns

1. **Linux Real-Time Scheduler (SCHED_FIFO/SCHED_RR):**
   - Priority levels: 1 (lowest) to 99 (highest)
   - Preemption: Higher priority always preempts lower
   - SCHED_FIFO: Run until blocked or yielded
   - SCHED_RR: Round-robin within priority level
   - Real-time priority > normal priority (CFS)

2. **Kubernetes Pod Priority & Preemption:**
   - PriorityClass resources: system-cluster-critical (2000000000), system-node-critical (2000001000)
   - Preemption: High priority pod evicts low priority pods
   - Graceful termination: 30s default grace period
   - Node pressure eviction: BestEffort → Burstable → Guaranteed

3. **NVIDIA GPU Preemption:**
   - Context switching: Save GPU state, load new context
   - Compute preemption: CUDA kernels can be interrupted (Pascal+)
   - Graphics preemption: Pixel-level on Turing+
   - Preemption latency: 1-10ms depending on kernel complexity

4. **AWS ECS Task Priority:**
   - Task priorities: 0 (lowest) to 10 (highest)
   - Preemption: Higher priority tasks evict lower priority
   - Drain time: 120s default for task to gracefully stop
   - Spot instances: Can be preempted by AWS with 2-minute warning

### K1 Priority Classes

| Priority Class | Weight | Preempts          | Preemptable By | Use Case               |
|----------------|--------|-------------------|----------------|------------------------|
| SAFETY         | 2.0    | Active, Background| None           | Safety monitoring      |
| ACTIVE         | 1.0    | Background        | Safety         | Active conversation    |
| BACKGROUND     | 0.3    | None              | Safety, Active | Background learning    |

---

## Decision

We will implement **3 priority classes with preemption support** for safety-critical responsiveness.

### Preemption Rules

```python
PREEMPTION_RULES = {
    PriorityClass.SAFETY: {
        "can_preempt": [PriorityClass.ACTIVE, PriorityClass.BACKGROUND],
        "preemptable_by": []
    },
    PriorityClass.ACTIVE: {
        "can_preempt": [PriorityClass.BACKGROUND],
        "preemptable_by": [PriorityClass.SAFETY]
    },
    PriorityClass.BACKGROUND: {
        "can_preempt": [],
        "preemptable_by": [PriorityClass.SAFETY, PriorityClass.ACTIVE]
    }
}
```

### Preemption Flow

```
1. High priority turn arrives
2. Check if lower priority session running
3. If yes:
   a. Save inference state (KV cache, position)
   b. Interrupt current inference
   c. Run high priority turn
   d. Resume preempted turn from checkpoint
```

---

## Implementation

### 1. Priority Manager

**`k1/orchestrator/scheduler/priority_manager.py`:**

```python
"""
Module: k1.orchestrator.scheduler.priority_manager
Purpose: Priority classes with preemption support

Research: Linux SCHED_FIFO, Kubernetes Pod Priority, NVIDIA GPU Preemption
"""

from dataclasses import dataclass
from typing import Optional, Dict
from enum import Enum
import time
import structlog
from prometheus_client import Counter, Histogram, Gauge

logger = structlog.get_logger()

# Prometheus metrics
preemption_events_total = Counter(
    'k1_preemption_events_total',
    'Total preemption events',
    ['preemptor_class', 'preempted_class']
)

resume_latency_ms = Histogram(
    'k1_resume_latency_ms',
    'Latency to resume preempted session',
    buckets=[10, 50, 100, 200, 500, 1000]
)

preemption_checkpoint_size_kb = Histogram(
    'k1_preemption_checkpoint_size_kb',
    'Size of preemption checkpoint in KB',
    buckets=[1, 10, 50, 100, 500, 1000, 5000]
)

currently_preempted_gauge = Gauge(
    'k1_currently_preempted_sessions',
    'Number of sessions currently preempted'
)


class PriorityClass(Enum):
    """Session priority classes"""
    SAFETY = "SAFETY"           # Weight 2.0 - preempts all
    ACTIVE = "ACTIVE"           # Weight 1.0 - preempts Background
    BACKGROUND = "BACKGROUND"   # Weight 0.3 - preemptable by all


# Preemption rules
PREEMPTION_RULES = {
    PriorityClass.SAFETY: {
        "can_preempt": [PriorityClass.ACTIVE, PriorityClass.BACKGROUND],
        "preemptable_by": []
    },
    PriorityClass.ACTIVE: {
        "can_preempt": [PriorityClass.BACKGROUND],
        "preemptable_by": [PriorityClass.SAFETY]
    },
    PriorityClass.BACKGROUND: {
        "can_preempt": [],
        "preemptable_by": [PriorityClass.SAFETY, PriorityClass.ACTIVE]
    }
}


@dataclass
class PreemptionCheckpoint:
    """State saved when session is preempted"""
    session_id: str
    priority_class: PriorityClass

    # Inference state
    kv_cache: bytes  # Serialized KV cache
    inference_position: int  # Token position when preempted
    prompt: str

    # Timing
    preempted_at_ms: int
    original_start_ms: int
    cpu_time_used_ms: int

    # Metadata
    checkpoint_size_kb: int


@dataclass
class PreemptionEvent:
    """Record of a preemption event"""
    preemptor_session_id: str
    preemptor_class: PriorityClass
    preempted_session_id: str
    preempted_class: PriorityClass
    timestamp_ms: int
    checkpoint_size_kb: int


class PriorityManager:
    """Manage priority classes and preemption"""

    def __init__(self):
        # Currently running session
        self.running_session_id: Optional[str] = None
        self.running_priority: Optional[PriorityClass] = None

        # Preempted sessions (session_id -> checkpoint)
        self.preempted_checkpoints: Dict[str, PreemptionCheckpoint] = {}

        # Preemption history
        self.preemption_history: list[PreemptionEvent] = []

        logger.info("priority_manager_initialized")

    def can_preempt(
        self,
        preemptor_class: PriorityClass,
        preempted_class: PriorityClass
    ) -> bool:
        """
        Check if preemptor can preempt preempted

        Args:
            preemptor_class: Priority class trying to preempt
            preempted_class: Priority class currently running

        Returns:
            True if preemption is allowed
        """
        can_preempt_list = PREEMPTION_RULES[preemptor_class]["can_preempt"]
        return preempted_class in can_preempt_list

    def start_session_execution(
        self,
        session_id: str,
        priority_class: PriorityClass
    ):
        """Mark session as currently running"""
        self.running_session_id = session_id
        self.running_priority = priority_class

        logger.debug(
            "session_execution_started",
            session_id=session_id,
            priority_class=priority_class.value
        )

    def should_preempt(
        self,
        incoming_session_id: str,
        incoming_priority: PriorityClass
    ) -> tuple[bool, Optional[str]]:
        """
        Check if incoming session should preempt running session

        Args:
            incoming_session_id: Session wanting to run
            incoming_priority: Priority class of incoming session

        Returns:
            (should_preempt, reason)
        """
        # No session running
        if self.running_session_id is None:
            return (False, None)

        # Same session (resume)
        if self.running_session_id == incoming_session_id:
            return (False, None)

        # Check preemption rules
        can_preempt = self.can_preempt(incoming_priority, self.running_priority)

        if can_preempt:
            reason = (
                f"{incoming_priority.value} session preempting "
                f"{self.running_priority.value} session"
            )
            return (True, reason)

        return (False, None)

    def preempt_current_session(
        self,
        preemptor_session_id: str,
        preemptor_class: PriorityClass,
        kv_cache: bytes,
        inference_position: int,
        prompt: str,
        cpu_time_used_ms: int
    ) -> PreemptionCheckpoint:
        """
        Preempt currently running session

        Args:
            preemptor_session_id: Session doing the preemption
            preemptor_class: Priority class of preemptor
            kv_cache: Serialized KV cache of preempted session
            inference_position: Token position when preempted
            prompt: Original prompt
            cpu_time_used_ms: CPU time used so far

        Returns:
            PreemptionCheckpoint for later resume
        """
        if self.running_session_id is None:
            raise ValueError("No session running to preempt")

        preempted_session_id = self.running_session_id
        preempted_class = self.running_priority

        # Create checkpoint
        checkpoint = PreemptionCheckpoint(
            session_id=preempted_session_id,
            priority_class=preempted_class,
            kv_cache=kv_cache,
            inference_position=inference_position,
            prompt=prompt,
            preempted_at_ms=int(time.time() * 1000),
            original_start_ms=int(time.time() * 1000) - cpu_time_used_ms,
            cpu_time_used_ms=cpu_time_used_ms,
            checkpoint_size_kb=len(kv_cache) // 1024
        )

        # Store checkpoint
        self.preempted_checkpoints[preempted_session_id] = checkpoint

        # Record event
        event = PreemptionEvent(
            preemptor_session_id=preemptor_session_id,
            preemptor_class=preemptor_class,
            preempted_session_id=preempted_session_id,
            preempted_class=preempted_class,
            timestamp_ms=checkpoint.preempted_at_ms,
            checkpoint_size_kb=checkpoint.checkpoint_size_kb
        )
        self.preemption_history.append(event)

        # Update metrics
        preemption_events_total.labels(
            preemptor_class=preemptor_class.value,
            preempted_class=preempted_class.value
        ).inc()

        preemption_checkpoint_size_kb.observe(checkpoint.checkpoint_size_kb)

        currently_preempted_gauge.inc()

        logger.warning(
            "session_preempted",
            preempted_session_id=preempted_session_id,
            preempted_class=preempted_class.value,
            preemptor_session_id=preemptor_session_id,
            preemptor_class=preemptor_class.value,
            checkpoint_size_kb=checkpoint.checkpoint_size_kb
        )

        # Clear running session
        self.running_session_id = None
        self.running_priority = None

        return checkpoint

    def resume_preempted_session(
        self,
        session_id: str
    ) -> Optional[PreemptionCheckpoint]:
        """
        Resume a preempted session

        Args:
            session_id: Session to resume

        Returns:
            PreemptionCheckpoint with saved state, or None if not preempted
        """
        if session_id not in self.preempted_checkpoints:
            return None

        start_ms = int(time.time() * 1000)

        checkpoint = self.preempted_checkpoints.pop(session_id)

        resume_latency = int(time.time() * 1000) - start_ms
        resume_latency_ms.observe(resume_latency)

        currently_preempted_gauge.dec()

        logger.info(
            "session_resumed",
            session_id=session_id,
            preempted_duration_ms=start_ms - checkpoint.preempted_at_ms,
            resume_latency_ms=resume_latency
        )

        return checkpoint

    def finish_session_execution(self, session_id: str):
        """Mark session execution as complete"""
        if self.running_session_id == session_id:
            self.running_session_id = None
            self.running_priority = None

            logger.debug(
                "session_execution_finished",
                session_id=session_id
            )

    def get_preemption_stats(self) -> dict:
        """Get preemption statistics"""
        # Count preemptions by class
        preemption_counts = {}

        for event in self.preemption_history:
            key = f"{event.preemptor_class.value}->{event.preempted_class.value}"
            preemption_counts[key] = preemption_counts.get(key, 0) + 1

        return {
            "total_preemptions": len(self.preemption_history),
            "currently_preempted": len(self.preempted_checkpoints),
            "preemption_counts": preemption_counts,
            "running_session": self.running_session_id,
            "running_priority": self.running_priority.value if self.running_priority else None
        }


class PreemptiveExecutor:
    """Execute inference with preemption support"""

    def __init__(self, priority_manager: PriorityManager):
        self.priority_manager = priority_manager

        logger.info("preemptive_executor_initialized")

    async def execute_with_preemption_check(
        self,
        session_id: str,
        priority_class: PriorityClass,
        inference_fn,
        checkpoint_fn
    ):
        """
        Execute inference with preemption checking

        Args:
            session_id: Session identifier
            priority_class: Session priority class
            inference_fn: Async function to run inference
            checkpoint_fn: Function to create checkpoint if preempted

        Returns:
            Inference result
        """
        # Check if we should preempt running session
        should_preempt, reason = self.priority_manager.should_preempt(
            session_id, priority_class
        )

        if should_preempt:
            # Preempt current session
            current_checkpoint = checkpoint_fn()

            self.priority_manager.preempt_current_session(
                preemptor_session_id=session_id,
                preemptor_class=priority_class,
                kv_cache=current_checkpoint["kv_cache"],
                inference_position=current_checkpoint["position"],
                prompt=current_checkpoint["prompt"],
                cpu_time_used_ms=current_checkpoint["cpu_time_ms"]
            )

            logger.info("preemption_triggered", reason=reason)

        # Mark as running
        self.priority_manager.start_session_execution(session_id, priority_class)

        try:
            # Check if this session was preempted (resume)
            checkpoint = self.priority_manager.resume_preempted_session(session_id)

            if checkpoint:
                # Resume from checkpoint
                result = await inference_fn(
                    resume_from=checkpoint
                )
            else:
                # Fresh execution
                result = await inference_fn()

            return result

        finally:
            # Mark as finished
            self.priority_manager.finish_session_execution(session_id)
```

---

## Testing Strategy

### WARD Test Suite

**`tests/orchestrator/scheduler/test_priority_manager.py`:**

```python
"""
WARD Tests: Priority Manager
"""

from ward import test, fixture

from k1.orchestrator.scheduler.priority_manager import (
    PriorityManager,
    PriorityClass
)


@fixture
def priority_mgr():
    """Fixture for priority manager"""
    return PriorityManager()


@test("priority manager allows Safety to preempt Background")
def _(mgr=priority_mgr):
    can_preempt = mgr.can_preempt(
        PriorityClass.SAFETY,
        PriorityClass.BACKGROUND
    )
    assert can_preempt is True


@test("priority manager prevents Background from preempting Safety")
def _(mgr=priority_mgr):
    can_preempt = mgr.can_preempt(
        PriorityClass.BACKGROUND,
        PriorityClass.SAFETY
    )
    assert can_preempt is False


@test("priority manager creates checkpoint on preemption")
def _(mgr=priority_mgr):
    # Start Background session
    mgr.start_session_execution("bg-1", PriorityClass.BACKGROUND)

    # Safety arrives, preempts Background
    checkpoint = mgr.preempt_current_session(
        preemptor_session_id="safety-1",
        preemptor_class=PriorityClass.SAFETY,
        kv_cache=b"fake_kv_cache_data",
        inference_position=42,
        prompt="Test prompt",
        cpu_time_used_ms=500
    )

    assert checkpoint.session_id == "bg-1"
    assert checkpoint.inference_position == 42
    assert checkpoint.cpu_time_used_ms == 500


@test("priority manager resumes preempted session")
def _(mgr=priority_mgr):
    # Preempt session
    mgr.start_session_execution("bg-1", PriorityClass.BACKGROUND)
    mgr.preempt_current_session(
        "safety-1",
        PriorityClass.SAFETY,
        b"kv_cache",
        42,
        "prompt",
        500
    )

    # Resume
    checkpoint = mgr.resume_preempted_session("bg-1")

    assert checkpoint is not None
    assert checkpoint.session_id == "bg-1"
    assert checkpoint.inference_position == 42


@test("priority manager tracks preemption statistics")
def _(mgr=priority_mgr):
    # Preempt twice
    for i in range(2):
        mgr.start_session_execution(f"bg-{i}", PriorityClass.BACKGROUND)
        mgr.preempt_current_session(
            f"safety-{i}",
            PriorityClass.SAFETY,
            b"kv",
            0,
            "prompt",
            100
        )

    stats = mgr.get_preemption_stats()

    assert stats["total_preemptions"] == 2
    assert "SAFETY->BACKGROUND" in stats["preemption_counts"]
    assert stats["preemption_counts"]["SAFETY->BACKGROUND"] == 2
```

---

## Performance Characteristics

### Preemption Latency Budget

**Preemption overhead:**
- Save KV cache: 20ms (copy tensors)
- Serialize state: 5ms (position, prompt)
- Context switch: 2ms (interrupt current inference)
- **Total preemption: ~27ms**

**Resume overhead:**
- Deserialize state: 5ms (position, prompt)
- Load KV cache: 20ms (copy tensors back)
- Resume inference: 3ms (restart from position)
- **Total resume: ~28ms**

**End-to-end preemption cost:**
- Preemption: 27ms
- High priority turn: 150ms (typical TTFT)
- Resume: 28ms
- **Total: ~205ms**

**Comparison:**
- Without preemption: Low priority turn completes (5000ms) + high priority turn (150ms) = **5150ms**
- With preemption: 205ms + remaining low priority (4500ms) = **4705ms** (total)
- **High priority latency reduction: 5000ms → 205ms (24× faster!)**

---

## Prometheus Metrics & Alerts

### Metrics

```yaml
# Preemption events by class
k1_preemption_events_total{preemptor_class="SAFETY", preempted_class="BACKGROUND"}

# Resume latency
k1_resume_latency_ms

# Checkpoint size
k1_preemption_checkpoint_size_kb

# Currently preempted sessions
k1_currently_preempted_sessions
```

### Alert Rules

```yaml
groups:
  - name: preemption_alerts
    interval: 30s
    rules:
      - alert: FrequentPreemptions
        expr: rate(k1_preemption_events_total[5m]) > 1.0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Frequent session preemptions (>1/sec)"
          description: "Many safety alerts or excessive priority contention"

      - alert: LongResumeLatency
        expr: histogram_quantile(0.95, k1_resume_latency_ms) > 100
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Long resume latency (P95 >100ms)"
          description: "Preempted sessions taking too long to resume"

      - alert: ManyPreemptedSessions
        expr: k1_currently_preempted_sessions > 5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: ">5 sessions currently preempted"
          description: "Possible resource exhaustion or priority imbalance"
```

---

## Consequences

### Positive

1. **Low safety latency:** Safety sessions preempt Background → 24× faster
2. **Checkpoint & resume:** Preempted sessions don't lose work
3. **Configurable rules:** Easy to add new priority classes
4. **Observable:** Metrics track preemption frequency and latency
5. **Fair within class:** WFQ applies within same priority

### Negative

1. **Resume overhead:** 28ms to restore preempted session
2. **State complexity:** Checkpoints require memory (~50KB each)
3. **Fairness impact:** Low priority may be preempted repeatedly
4. **Testing complexity:** Preemption race conditions hard to test

### Mitigations

- **Starvation prevention:** Max wait time (ADR-0028c) prevents indefinite preemption
- **Checkpoint caching:** Reuse KV cache buffers to reduce overhead
- **Preemption throttling:** Limit preemptions to 1 per session per 10 seconds
- **Integration tests:** Use WARD to test preemption scenarios

---

## Research & References

1. **Linux Real-Time Scheduler:** [SCHED_FIFO/SCHED_RR Documentation](https://man7.org/linux/man-pages/man7/sched.7.html)
2. **Kubernetes Pod Priority:** [Pod Priority and Preemption](https://kubernetes.io/docs/concepts/scheduling-eviction/pod-priority-preemption/)
3. **NVIDIA GPU Preemption:** [CUDA Preemption](https://docs.nvidia.com/cuda/cuda-c-programming-guide/index.html#compute-preemption)
4. **ECS Task Priority:** [Amazon ECS Task Placement](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-placement.html)

---

## Implementation Roadmap

### Week 1: Priority Rules
- Implement `PriorityManager` with preemption rules
- Add checkpoint/resume support
- Write WARD tests for preemption rules

### Week 2: Preemptive Executor
- Implement `PreemptiveExecutor` with inference interruption
- Add KV cache save/restore for checkpoints
- Test preemption latency (<50ms overhead)

### Week 3: Metrics & Observability
- Add Prometheus metrics for preemptions and resume latency
- Create Grafana dashboards for priority classes
- Alert rules for excessive preemptions

### Week 4: Integration & Testing
- Integrate with WFQ Scheduler (ADR-0028a)
- Load testing: Safety preempting Background/Active
- Validate P95 resume latency <100ms

---

**Related Files:**
- `k1/orchestrator/scheduler/priority_manager.py` — Priority manager implementation
- `tests/orchestrator/scheduler/test_priority_manager.py` — WARD test suite
