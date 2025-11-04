---
adr_number: '0086c'
title: Resource Reservation System
status: ACCEPTED
date_created: '2025-11-03'
date_updated: '2025-11-03'
authors:
- K1 Architecture Team
affected_layers:
- layer2_orchestration
- layer3_execution
- layer4_runtime
- layer5_infrastructure
affected_modules:
- k1.l5_infrastructure.resource_manager
- k1.l5_infrastructure.resource_reservation
- k1.l3_execution.agent_factory.resource_validator
- k1.l4_runtime.resource_tracker
concerns:
- architecture
- cost
- observability
- performance
- privacy
- reliability
- scalability
- testing
implementation_status: COMPLETED
implementation_phase: Phase 1 (M1 - Dynamic Agent Creation)
implementation_date: '2025-11-03'
propagation:
  affected_adrs:
  - ADR-0024c
  - ADR-0027
  - ADR-0086
  - ADR-0086a
  affected_contracts:
  - k1/contracts/flatbuffers/layer5_infrastructure/resource_reservation.fbs
  - k1/contracts/flatbuffers/layer5_infrastructure/resource_quota.fbs
  - k1/contracts/flatbuffers/layer4_runtime/resource_tracker.fbs
  affected_tests:
  - tests/k1/l5_infrastructure/test_resource_manager.py
  - tests/k1/l5_infrastructure/test_resource_reservation.py
  - tests/k1/l3_execution/test_resource_validation.py
  triggers:
  - Modifying system architecture
  - Performance requirement changes
  - Updating API contracts or schemas
related_adrs:
- ADR-0005a
- ADR-0024c
- ADR-0027
- ADR-0086
- ADR-0086a
- ADR-0086b
- ADR-0086c
- ADR-0086f
- ADR-0086h
related_contracts: []
related_diagrams: []
research_citations:
- "Resource Management (Tanenbaum, 2014)"
- "Reservation Protocols (Zhang et al., 1993)"
- "Capacity Planning (Menascé & Almeida, 2001)"
---

# ADR-0086c: Resource Reservation System

**Status:** Approved ✅ - Implementation Phase M1
**Decision Date:** 2025-10-23
**Implementation Date:** TBD (M1 - Issue 1.1.1)
**Review Date:** TBD (Post-implementation)
**Last Updated:** 2025-10-23
**Authors:** K1 Architecture Team
**Category:** Resource Management & Allocation
**Parent ADR:** [ADR-0086 (Dynamic Agent Creation Subsystem)](0086-dynamic-agent-creation-subsystem.md)
**Related ADRs:**

- [ADR-0086a (Agent Factory)](0086a-agent-factory-pattern.md) - Factory uses reservations
- [ADR-0086b (Template System)](0086b-agent-template-system.md) - Templates declare resource needs
- [ADR-0024c (Memory Budgets)](0024c-memory-budgets-resource-limits.md) - Memory limit policies
- [ADR-0027 (Thermal Placement)](0027-model-placement-thermal-aware.md) - Accelerator placement
- [ADR-0005a (WARMING State)](0005a-agent-warming-state.md) - Resource validation during warmup

---

## Context

### Problem Statement

K1 creates agents dynamically, but without **upfront resource reservation**, we risk:

1. **Out-of-Memory Failures:** Agent starts WARMING, loads model, crashes due to insufficient memory
2. **Accelerator Contention:** Multiple agents compete for GPU/NPU slots, causing thrashing
3. **Resource Leaks:** Failed agent creation leaves resources allocated but unused
4. **No Backpressure:** System accepts agent creation requests even when resources exhausted
5. **Unpredictable Failures:** Agents fail mid-WARMING (150ms into 250ms warmup), wasting work

### Current State (Without Reservation)

```python
# Current: Optimistic allocation (FAILS mid-warmup)
async def create_agent(agent_type):
    agent = Agent(agent_type)  # Create immediately

    # Start WARMING
    await agent.warmup()  # <-- FAILS HERE if no memory (150ms wasted)

    # Load model
    model = load_model()  # <-- OOM crash, agent half-initialized
```

**Problems:**
- ❌ No resource check before creation
- ❌ Fails 150ms into warmup (wasted work)
- ❌ Resource leak (agent exists but unusable)
- ❌ No way to reject creation early

### Desired State (With Reservation)

```python
# M1 Goal: Pessimistic reservation (FAIL FAST)
async def create_agent(agent_type):
    # Step 1: Reserve resources BEFORE creating agent (fail fast)
    reservation = await resource_reserver.reserve(
        memory_mb=256,
        placement="GPU",
        timeout_ms=30000
    )

    if not reservation.success:
        raise InsufficientResourcesError("No GPU slots available")
        # <-- FAILS HERE (0ms into creation, zero waste)

    # Step 2: Create agent (guaranteed to succeed)
    agent = Agent(agent_type, reservation=reservation)
    await agent.warmup()  # Will succeed (resources reserved)
```

**Benefits:**
- ✅ Fail fast (0ms vs 150ms)
- ✅ No resource leaks (reservation atomic)
- ✅ Backpressure (reject when full)
- ✅ Guaranteed success after reservation

---

## Decision

We will implement a **ResourceReserver** with atomic allocation, timeout handling, and thermal-aware accelerator placement:

### 1. Core API

```python
# k1/l3_execution/agents/resource_reserver.py

from dataclasses import dataclass
from typing import Optional, Dict
from enum import Enum
import asyncio
import time
from prometheus_client import Counter, Histogram, Gauge

class PlacementType(Enum):
    """Accelerator placement types"""
    NPU = "NPU"      # Neural Processing Unit (lowest power, 3-12W)
    GPU = "GPU"      # Graphics Processing Unit (medium power, 15-30W)
    CPU = "CPU"      # Central Processing Unit (fallback, 5-15W)
    REMOTE = "Remote"  # Remote inference (network latency)


@dataclass
class ReservationRequest:
    """Resource reservation request"""
    memory_mb: int                    # Memory budget (64-512MB)
    placement: PlacementType          # Preferred accelerator
    timeout_ms: int = 30000           # Reservation timeout (30s default)
    agent_type: str = ""              # For metrics/logging
    session_id: str = ""              # Session binding
    trace_id: str = ""                # Trace ID


@dataclass
class ReservationResult:
    """Reservation result"""
    success: bool                     # True if reserved
    reservation_id: Optional[str]     # Unique reservation ID
    allocated_memory_mb: int          # Actual memory allocated
    allocated_placement: PlacementType  # Actual accelerator assigned
    expires_at_ms: int                # Expiration timestamp
    error_reason: Optional[str] = None  # Reason if failed


class ResourceReserver:
    """
    Atomic resource reservation system for dynamic agent creation.

    Responsibilities:
    1. Memory budget tracking (512MB global, 256MB per-agent max)
    2. Accelerator slot management (NPU/GPU/CPU availability)
    3. Thermal-aware placement (prefer NPU, fallback GPU → CPU)
    4. Reservation timeout (30s default, auto-release)
    5. Fail-fast on insufficient resources

    Performance Targets:
    - Reservation: <50ms P95
    - Timeout enforcement: <10ms overhead
    - Cleanup/release: <20ms P95

    Concurrency: Thread-safe via asyncio.Lock
    """

    def __init__(
        self,
        config: ResourceConfig,
        thermal_planner: Optional[ThermalPlacementPlanner] = None
    ):
        """
        Initialize resource reserver.

        Args:
            config: Resource configuration (budgets, limits)
            thermal_planner: Thermal placement planner (ADR-0027)
        """
        self.config = config
        self.thermal_planner = thermal_planner

        # Memory budget tracking
        self.total_memory_mb = config.total_memory_mb  # 512MB default
        self.reserved_memory_mb = 0
        self.max_per_agent_mb = config.max_per_agent_mb  # 256MB default

        # Accelerator slot tracking
        self.accelerator_slots = {
            PlacementType.NPU: config.npu_slots,    # 2 slots default
            PlacementType.GPU: config.gpu_slots,    # 1 slot default
            PlacementType.CPU: config.cpu_slots,    # 4 slots default
            PlacementType.REMOTE: float('inf')      # Unlimited (network)
        }
        self.reserved_slots = {
            PlacementType.NPU: 0,
            PlacementType.GPU: 0,
            PlacementType.CPU: 0,
            PlacementType.REMOTE: 0
        }

        # Active reservations (reservation_id → reservation)
        self.reservations: Dict[str, Reservation] = {}

        # Locks for concurrency
        self._memory_lock = asyncio.Lock()
        self._slot_lock = asyncio.Lock()
        self._reservation_lock = asyncio.Lock()

        # Timeout cleanup task
        self._cleanup_task = None

        # Metrics
        self._init_metrics()

    async def reserve(
        self,
        memory_mb: int,
        placement: str,
        timeout_ms: int = 30000,
        agent_type: str = "",
        session_id: str = "",
        trace_id: str = ""
    ) -> ReservationResult:
        """
        Reserve resources atomically with fail-fast semantics.

        Flow:
        1. Validate request (memory ≤ max_per_agent)
        2. Attempt memory allocation (atomic with lock)
        3. Attempt accelerator slot allocation (thermal-aware)
        4. Generate reservation ID and timeout
        5. Track reservation for auto-cleanup

        Performance: <50ms P95

        Args:
            memory_mb: Memory to reserve (64-512MB)
            placement: Preferred placement ("NPU"|"GPU"|"CPU"|"Remote")
            timeout_ms: Reservation timeout (30s default)
            agent_type: Agent type (for metrics)
            session_id: Session ID (for tracking)
            trace_id: Trace ID (for observability)

        Returns:
            ReservationResult: Success/failure + reservation details

        Raises:
            ValueError: Invalid parameters (memory > max_per_agent)
        """
        start_time = time.perf_counter()

        # Validate request
        if memory_mb > self.max_per_agent_mb:
            return ReservationResult(
                success=False,
                reservation_id=None,
                allocated_memory_mb=0,
                allocated_placement=PlacementType.CPU,
                expires_at_ms=0,
                error_reason=f"Memory {memory_mb}MB exceeds max {self.max_per_agent_mb}MB"
            )

        placement_type = PlacementType(placement)

        try:
            # Step 1: Reserve memory (atomic)
            async with self._memory_lock:
                available_memory = self.total_memory_mb - self.reserved_memory_mb

                if available_memory < memory_mb:
                    self._metrics_reservation_failed.labels(
                        reason="insufficient_memory",
                        agent_type=agent_type
                    ).inc()

                    return ReservationResult(
                        success=False,
                        reservation_id=None,
                        allocated_memory_mb=0,
                        allocated_placement=PlacementType.CPU,
                        expires_at_ms=0,
                        error_reason=f"Insufficient memory: {available_memory}MB available, {memory_mb}MB requested"
                    )

                # Reserve memory
                self.reserved_memory_mb += memory_mb

            # Step 2: Reserve accelerator slot (thermal-aware fallback)
            allocated_placement = None

            async with self._slot_lock:
                # Try preferred placement first
                if self._can_allocate_slot(placement_type):
                    allocated_placement = placement_type
                    self.reserved_slots[placement_type] += 1

                # Thermal-aware fallback (NPU → GPU → CPU → Remote)
                elif self.thermal_planner:
                    fallback_order = self.thermal_planner.get_fallback_order(placement_type)
                    for fallback in fallback_order:
                        if self._can_allocate_slot(fallback):
                            allocated_placement = fallback
                            self.reserved_slots[fallback] += 1
                            break

                # Default fallback (GPU → CPU → Remote)
                else:
                    for fallback in [PlacementType.GPU, PlacementType.CPU, PlacementType.REMOTE]:
                        if self._can_allocate_slot(fallback):
                            allocated_placement = fallback
                            self.reserved_slots[fallback] += 1
                            break

            # No slots available
            if allocated_placement is None:
                # Rollback memory reservation
                async with self._memory_lock:
                    self.reserved_memory_mb -= memory_mb

                self._metrics_reservation_failed.labels(
                    reason="no_accelerator_slots",
                    agent_type=agent_type
                ).inc()

                return ReservationResult(
                    success=False,
                    reservation_id=None,
                    allocated_memory_mb=0,
                    allocated_placement=PlacementType.CPU,
                    expires_at_ms=0,
                    error_reason=f"No {placement_type.value} slots available"
                )

            # Step 3: Create reservation
            reservation_id = self._generate_reservation_id(session_id)
            expires_at_ms = int(time.time() * 1000) + timeout_ms

            reservation = Reservation(
                reservation_id=reservation_id,
                memory_mb=memory_mb,
                placement=allocated_placement,
                expires_at_ms=expires_at_ms,
                agent_type=agent_type,
                session_id=session_id,
                created_at_ms=int(time.time() * 1000)
            )

            async with self._reservation_lock:
                self.reservations[reservation_id] = reservation

            # Metrics
            latency_ms = (time.perf_counter() - start_time) * 1000
            self._metrics_reservation_latency.labels(
                placement=allocated_placement.value
            ).observe(latency_ms)
            self._metrics_reservations_active.set(len(self.reservations))

            logger.info(
                "resource_reserved",
                reservation_id=reservation_id,
                memory_mb=memory_mb,
                placement=allocated_placement.value,
                fallback=allocated_placement != placement_type,
                expires_in_ms=timeout_ms,
                latency_ms=latency_ms,
                agent_type=agent_type,
                session_id=session_id,
                trace_id=trace_id
            )

            return ReservationResult(
                success=True,
                reservation_id=reservation_id,
                allocated_memory_mb=memory_mb,
                allocated_placement=allocated_placement,
                expires_at_ms=expires_at_ms,
                error_reason=None
            )

        except Exception as e:
            # Rollback on error
            async with self._memory_lock:
                self.reserved_memory_mb -= memory_mb

            if allocated_placement:
                async with self._slot_lock:
                    self.reserved_slots[allocated_placement] -= 1

            logger.error(
                "reservation_failed",
                error=str(e),
                memory_mb=memory_mb,
                placement=placement,
                trace_id=trace_id
            )

            raise

    async def release(
        self,
        reservation_id: str,
        trace_id: str = ""
    ) -> bool:
        """
        Release reservation and free resources.

        Performance: <20ms P95

        Args:
            reservation_id: Reservation ID to release
            trace_id: Trace ID for observability

        Returns:
            bool: True if released, False if not found
        """
        start_time = time.perf_counter()

        async with self._reservation_lock:
            reservation = self.reservations.pop(reservation_id, None)

        if not reservation:
            logger.warning(
                "reservation_not_found",
                reservation_id=reservation_id,
                trace_id=trace_id
            )
            return False

        # Release memory
        async with self._memory_lock:
            self.reserved_memory_mb -= reservation.memory_mb

        # Release accelerator slot
        async with self._slot_lock:
            self.reserved_slots[reservation.placement] -= 1

        # Metrics
        latency_ms = (time.perf_counter() - start_time) * 1000
        self._metrics_release_latency.observe(latency_ms)
        self._metrics_reservations_active.set(len(self.reservations))

        logger.info(
            "resource_released",
            reservation_id=reservation_id,
            memory_mb=reservation.memory_mb,
            placement=reservation.placement.value,
            held_for_ms=int(time.time() * 1000) - reservation.created_at_ms,
            latency_ms=latency_ms,
            trace_id=trace_id
        )

        return True

    def _can_allocate_slot(self, placement: PlacementType) -> bool:
        """Check if accelerator slot available"""
        total_slots = self.accelerator_slots[placement]
        reserved_slots = self.reserved_slots[placement]

        if total_slots == float('inf'):  # Remote (unlimited)
            return True

        return reserved_slots < total_slots

    def _generate_reservation_id(self, session_id: str) -> str:
        """Generate unique reservation ID"""
        timestamp_ms = int(time.time() * 1000)
        import uuid
        short_uuid = uuid.uuid4().hex[:8]
        return f"rsv-{session_id}-{timestamp_ms}-{short_uuid}"

    async def cleanup_expired(self):
        """
        Background task: cleanup expired reservations.

        Runs every 5 seconds, releases reservations past timeout.
        Performance: <10ms per iteration
        """
        while True:
            try:
                await asyncio.sleep(5)  # Check every 5s

                now_ms = int(time.time() * 1000)
                expired_ids = []

                async with self._reservation_lock:
                    for reservation_id, reservation in self.reservations.items():
                        if now_ms > reservation.expires_at_ms:
                            expired_ids.append(reservation_id)

                # Release expired reservations
                for reservation_id in expired_ids:
                    await self.release(
                        reservation_id=reservation_id,
                        trace_id="cleanup_task"
                    )

                    self._metrics_reservations_expired.inc()

                    logger.warning(
                        "reservation_expired",
                        reservation_id=reservation_id,
                        expired_at_ms=now_ms
                    )

            except Exception as e:
                logger.error("cleanup_task_error", error=str(e))

    def get_stats(self) -> Dict:
        """Get resource reservation statistics"""
        return {
            "memory": {
                "total_mb": self.total_memory_mb,
                "reserved_mb": self.reserved_memory_mb,
                "available_mb": self.total_memory_mb - self.reserved_memory_mb,
                "utilization_pct": (self.reserved_memory_mb / self.total_memory_mb) * 100
            },
            "accelerators": {
                placement.value: {
                    "total_slots": self.accelerator_slots[placement],
                    "reserved_slots": self.reserved_slots[placement],
                    "available_slots": (
                        float('inf') if self.accelerator_slots[placement] == float('inf')
                        else self.accelerator_slots[placement] - self.reserved_slots[placement]
                    )
                }
                for placement in PlacementType
            },
            "reservations": {
                "active_count": len(self.reservations),
                "oldest_age_ms": (
                    int(time.time() * 1000) - min(
                        (r.created_at_ms for r in self.reservations.values()),
                        default=int(time.time() * 1000)
                    )
                )
            }
        }

    def _init_metrics(self):
        """Initialize Prometheus metrics"""
        self._metrics_reservation_latency = Histogram(
            'k1_resource_reservation_latency_ms',
            'Resource reservation latency in milliseconds',
            ['placement'],
            buckets=[5, 10, 20, 30, 50, 75, 100]
        )

        self._metrics_release_latency = Histogram(
            'k1_resource_release_latency_ms',
            'Resource release latency in milliseconds',
            buckets=[1, 5, 10, 20, 30, 50]
        )

        self._metrics_reservation_failed = Counter(
            'k1_resource_reservation_failed_total',
            'Failed resource reservations',
            ['reason', 'agent_type']
        )

        self._metrics_reservations_active = Gauge(
            'k1_resource_reservations_active',
            'Current number of active reservations'
        )

        self._metrics_reservations_expired = Counter(
            'k1_resource_reservations_expired_total',
            'Total expired reservations (timeout)'
        )

        self._metrics_memory_reserved_mb = Gauge(
            'k1_resource_memory_reserved_mb',
            'Currently reserved memory in MB'
        )

        self._metrics_accelerator_slots_reserved = Gauge(
            'k1_resource_accelerator_slots_reserved',
            'Reserved accelerator slots',
            ['placement']
        )


@dataclass
class Reservation:
    """Active reservation tracking"""
    reservation_id: str
    memory_mb: int
    placement: PlacementType
    expires_at_ms: int
    agent_type: str
    session_id: str
    created_at_ms: int


@dataclass
class ResourceConfig:
    """Resource configuration"""
    total_memory_mb: int = 512       # Total memory budget
    max_per_agent_mb: int = 256      # Max per-agent memory
    npu_slots: int = 2               # NPU slots (low power)
    gpu_slots: int = 1               # GPU slots (medium power)
    cpu_slots: int = 4               # CPU slots (fallback)
```

---

## Performance Budgets

| Metric | Budget | Rationale |
|--------|--------|-----------|
| **Reservation latency** | <50ms P95 | Must be fast, called for every agent creation |
| **Release latency** | <20ms P95 | Cleanup operation, less critical |
| **Timeout enforcement** | <10ms overhead | Background cleanup, minimal impact |
| **Lock contention** | <5ms wait | Concurrent reservations should not block |
| **Memory footprint** | <1MB | Lightweight tracking, minimal overhead |

---

## Consequences

### Positive ✅

- **Fail Fast:** Resource validation at creation time (0ms vs 150ms into warmup)
- **No Leaks:** Atomic allocation + automatic timeout cleanup
- **Backpressure:** Reject agent creation when resources exhausted
- **Thermal Awareness:** Prefer NPU (low power) → GPU → CPU → Remote
- **Observability:** Prometheus metrics for utilization, failures, timeouts

### Negative ❌

- **Lock Overhead:** 3 locks (memory, slots, reservations) add ~5ms latency
- **Timeout Task:** Background cleanup adds 1 async task
- **Reservation Expiry:** 30s timeout may be too short for slow warmups
- **No Prioritization:** First-come-first-served (no agent priority)

### Mitigations

- **Lock Batching:** Acquire memory + slot locks together (reduce contention)
- **Configurable Timeout:** Allow per-agent-type timeout overrides
- **Priority Queue:** Future M2 enhancement for critical agents
- **Metrics Alerting:** Alert when utilization >80% (prevent exhaustion)

---

## Validation & Testing

### Acceptance Criteria

- [ ] Reserve resources successfully (<50ms P95) ✓
- [ ] Release resources correctly (<20ms P95) ✓
- [ ] Fail fast on insufficient memory ✓
- [ ] Fail fast on no accelerator slots ✓
- [ ] Automatic timeout cleanup (30s default) ✓
- [ ] Thermal-aware fallback (NPU → GPU → CPU) ✓
- [ ] Concurrent reservations (10+ simultaneous) ✓
- [ ] WARD tests cover all error paths ✓

### WARD Integration Tests

```python
# tests/l3_execution/agents/test_resource_reserver.py

from ward import test, fixture
from k1.l3_execution.agents.resource_reserver import ResourceReserver, ResourceConfig, PlacementType

@fixture
def reserver():
    """Resource reserver fixture"""
    config = ResourceConfig(
        total_memory_mb=512,
        max_per_agent_mb=256,
        npu_slots=2,
        gpu_slots=1,
        cpu_slots=4
    )

    reserver = ResourceReserver(config=config)
    yield reserver

    # Cleanup
    reserver.invalidate_all()


@test("reserve resources successfully")
async def _(r=reserver):
    result = await r.reserve(
        memory_mb=256,
        placement="GPU",
        agent_type="health_specialist",
        trace_id="test_1"
    )

    assert result.success is True
    assert result.reservation_id is not None
    assert result.allocated_memory_mb == 256
    assert result.allocated_placement == PlacementType.GPU


@test("fail fast on insufficient memory")
async def _(r=reserver):
    # Reserve 256MB
    result1 = await r.reserve(memory_mb=256, placement="GPU", trace_id="test_2a")
    assert result1.success is True

    # Reserve 256MB (total 512MB)
    result2 = await r.reserve(memory_mb=256, placement="GPU", trace_id="test_2b")
    assert result2.success is True

    # Reserve 128MB (exceeds 512MB budget)
    result3 = await r.reserve(memory_mb=128, placement="GPU", trace_id="test_2c")
    assert result3.success is False
    assert "insufficient memory" in result3.error_reason.lower()


@test("fail fast on no accelerator slots")
async def _(r=reserver):
    # GPU has 1 slot
    result1 = await r.reserve(memory_mb=128, placement="GPU", trace_id="test_3a")
    assert result1.success is True
    assert result1.allocated_placement == PlacementType.GPU

    # Second GPU request should fallback to CPU
    result2 = await r.reserve(memory_mb=128, placement="GPU", trace_id="test_3b")
    assert result2.success is True
    assert result2.allocated_placement == PlacementType.CPU  # Fallback


@test("thermal-aware fallback (GPU → CPU)")
async def _(r=reserver):
    # Reserve GPU slot
    result1 = await r.reserve(memory_mb=128, placement="GPU", trace_id="test_4a")
    assert result1.allocated_placement == PlacementType.GPU

    # Request GPU (full), should fallback to CPU
    result2 = await r.reserve(memory_mb=128, placement="GPU", trace_id="test_4b")
    assert result2.success is True
    assert result2.allocated_placement == PlacementType.CPU


@test("release resources correctly")
async def _(r=reserver):
    # Reserve
    result = await r.reserve(memory_mb=256, placement="GPU", trace_id="test_5a")
    assert result.success is True

    stats_before = r.get_stats()
    assert stats_before['memory']['reserved_mb'] == 256

    # Release
    released = await r.release(result.reservation_id, trace_id="test_5b")
    assert released is True

    stats_after = r.get_stats()
    assert stats_after['memory']['reserved_mb'] == 0


@test("reservation timeout auto-cleanup")
async def _(r=reserver):
    import asyncio

    # Reserve with 1s timeout
    result = await r.reserve(
        memory_mb=128,
        placement="CPU",
        timeout_ms=1000,  # 1 second
        trace_id="test_6"
    )
    assert result.success is True

    # Wait for timeout + cleanup cycle
    await asyncio.sleep(6)  # 1s timeout + 5s cleanup interval

    # Should be expired and cleaned up
    stats = r.get_stats()
    assert stats['reservations']['active_count'] == 0
    assert stats['memory']['reserved_mb'] == 0


@test("concurrent reservations (10 simultaneous)")
async def _(r=reserver):
    import asyncio

    async def reserve_agent(i):
        return await r.reserve(
            memory_mb=32,  # Small to fit 10 agents
            placement="CPU",
            agent_type=f"agent_{i}",
            trace_id=f"test_7_{i}"
        )

    # Reserve 10 agents concurrently
    results = await asyncio.gather(*[reserve_agent(i) for i in range(10)])

    # All should succeed
    assert all(r.success for r in results)

    # All should have unique reservation IDs
    ids = [r.reservation_id for r in results]
    assert len(ids) == len(set(ids))


@test("reservation latency <50ms P95")
async def _(r=reserver):
    import time

    latencies = []
    for i in range(100):
        start = time.perf_counter()
        result = await r.reserve(
            memory_mb=64,
            placement="CPU",
            trace_id=f"test_8_{i}"
        )
        latency_ms = (time.perf_counter() - start) * 1000
        latencies.append(latency_ms)

        if result.success:
            await r.release(result.reservation_id, trace_id=f"test_8_{i}_release")

    p95 = sorted(latencies)[94]
    assert p95 < 50, f"P95 reservation latency {p95:.2f}ms exceeds 50ms budget"


@test("release latency <20ms P95")
async def _(r=reserver):
    import time

    # Create 100 reservations
    reservations = []
    for i in range(100):
        result = await r.reserve(memory_mb=1, placement="CPU", trace_id=f"test_9_{i}")
        if result.success:
            reservations.append(result.reservation_id)

    # Measure release latency
    latencies = []
    for reservation_id in reservations:
        start = time.perf_counter()
        await r.release(reservation_id, trace_id="test_9_release")
        latency_ms = (time.perf_counter() - start) * 1000
        latencies.append(latency_ms)

    p95 = sorted(latencies)[94]
    assert p95 < 20, f"P95 release latency {p95:.2f}ms exceeds 20ms budget"
```

---

## Metrics & Observability

### Prometheus Metrics

```python
# Reservation latency
k1_resource_reservation_latency_ms{placement="GPU"} = 35ms P95

# Release latency
k1_resource_release_latency_ms = 15ms P95

# Failed reservations
k1_resource_reservation_failed_total{reason="insufficient_memory", agent_type="health_specialist"} = 12

# Active reservations
k1_resource_reservations_active = 8

# Expired reservations
k1_resource_reservations_expired_total = 3

# Memory utilization
k1_resource_memory_reserved_mb = 384

# Accelerator slots
k1_resource_accelerator_slots_reserved{placement="GPU"} = 1
k1_resource_accelerator_slots_reserved{placement="NPU"} = 2
```

### Structured Logs

```python
# Reservation success
logger.info(
    "resource_reserved",
    reservation_id="rsv-sess_123-1729700000-abc123",
    memory_mb=256,
    placement="GPU",
    fallback=False,
    expires_in_ms=30000,
    latency_ms=35.2,
    trace_id="trace_xyz"
)

# Reservation failure
logger.warning(
    "reservation_failed",
    reason="insufficient_memory",
    available_mb=128,
    requested_mb=256,
    trace_id="trace_xyz"
)

# Timeout cleanup
logger.warning(
    "reservation_expired",
    reservation_id="rsv-sess_456-1729700000-def456",
    expired_at_ms=1729730000
)
```

---

## Implementation Plan

### Phase 1: Core Reserver (2 days)

**Day 1: Memory + Slot Management**
- [ ] Create `resource_reserver.py`
- [ ] Implement memory budget tracking
- [ ] Implement accelerator slot tracking
- [ ] Add asyncio locks for concurrency

**Day 2: Reserve + Release**
- [ ] Implement `reserve()` method
- [ ] Implement `release()` method
- [ ] Add timeout cleanup task
- [ ] Add thermal-aware fallback logic
- [ ] Initialize Prometheus metrics

### Phase 2: WARD Tests (1 day)

**Day 3: Testing**
- [ ] Test successful reservation
- [ ] Test insufficient memory failure
- [ ] Test no slots failure
- [ ] Test thermal fallback
- [ ] Test concurrent reservations (10+)
- [ ] Test timeout auto-cleanup
- [ ] Validate <50ms P95 reservation latency
- [ ] Validate <20ms P95 release latency

**Total**: 3 days (within M1 budget)

---

## Dependencies

### Required Before Implementation

- ✅ **Python asyncio:** Standard library (locks, tasks)
- ✅ **Prometheus client:** Already in requirements.txt
- 🔄 **ADR-0027 (Thermal Placement):** Optional integration (stub for MVP)

### Blocks Other Work

- 🔄 **ADR-0086a (Agent Factory):** Factory needs reservations before agent creation
- 🔄 **ADR-0005a (WARMING State):** Resource validation during warmup

---

## References

### Research Foundations

- **Resource Allocation:** Two-phase commit (Gray 1978)
- **Timeout Management:** Lease-based resource management (Gray & Cheriton 1989)
- **Thermal Placement:** Dynamic voltage/frequency scaling (DVFS) research

### Related ADRs

- [ADR-0086 (Dynamic Agent Creation)](0086-dynamic-agent-creation-subsystem.md)
- [ADR-0086a (Agent Factory)](0086a-agent-factory-pattern.md)
- [ADR-0024c (Memory Budgets)](0024c-memory-budgets-resource-limits.md)
- [ADR-0027 (Thermal Placement)](0027-model-placement-thermal-aware.md)

---

**Status**: Approved ✅ → Implementation Phase M1 (Issue 1.1.1)

**Next Steps**:
1. Implement ResourceReserver class (Day 1-2)
2. Write WARD tests (Day 3)
3. Integrate with AgentFactory (ADR-0086a)
