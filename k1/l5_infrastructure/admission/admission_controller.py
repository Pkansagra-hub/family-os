"""
Admission Controller - Core Admission Decision Engine

Layer: L5 Infrastructure
Component: Admission Control
Priority: P2 (Flow Control)
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

Architecture Decision Records:
    - ADR-0032: Admission Control Design
    - ADR-0002c: Actor Router & Admission Control (pattern reference)
    - ADR-0028: Backpressure Cascade System (integration)
    - ADR-0030: Rate Limiting Strategy (quota checks)
    - ADR-0031: Task Scheduling Strategy (queue integration)

Dependencies:
    Internal:
        - k1.l5_infrastructure.admission.task_validator (schema validation)
        - k1.l5_infrastructure.rate_limiting.rate_limiter (quota checks)
        - k1.l5_infrastructure.backpressure.backpressure_manager (watermark signals)
        - k1.l5_infrastructure.scheduling.scheduler (task queueing)
        - k1.l5_infrastructure.metrics (observability)
    External:
        - asyncio (async runtime)
        - typing (type hints)
        - enum (state enums)
        - dataclasses (data structures)
        - logging (structured logging)

Connects To:
    Upstream:
        - k1.l3_execution.request_router (incoming requests)
        - k1.l2_orchestration.orchestrator (system health signals)
    Downstream:
        - k1.l5_infrastructure.scheduling.scheduler (admitted tasks)
        - k1.l3_execution.model_hub (task execution)

Performance Budgets:
    - Admission decision: <10ms P95
    - Type validation: <1ms P95
    - Privacy check: <1ms P95
    - Rate limit check: <5ms P95
    - Capacity check: <1ms P95
    - Anti-starvation check: <1ms P95
    - Metrics emission: <0.5ms P95

Observability:
    - Metrics:
        - k1_admission_requests_total{status, priority} (counter)
        - k1_admission_decision_latency_ms{p50, p95, p99} (histogram)
        - k1_admission_acceptance_rate{window=1m, 5m, 15m} (gauge)
        - k1_admission_rejections_total{reason, priority} (counter)
        - k1_admission_queue_depth{gauge} (current)
        - k1_admission_anti_starvation_triggers_total (counter)
        - k1_admission_reserved_slots_used{priority} (gauge)
    - Traces:
        - Span: admission_controller.admit
        - Attributes: request_type, priority, privacy_band, decision, cognitive_trace_id
        - Child spans: task_validator.validate, rate_limiter.check, backpressure_manager.get_level
    - Logs:
        - INFO: admission decision (request_id, decision, latency_ms)
        - WARNING: rate limit exceeded (user_id, tenant_id, current_quota)
        - WARNING: capacity exceeded (queue_depth, threshold, priority)
        - ERROR: privacy violation (request_id, privacy_band, violation_reason)

References:
    - Diagram: architecture_diagrams/k1/k1_admission_control.mmd
    - Whiteboard: docs/whiteboard.md (Section 7: Flow Control)
    - Test: tests/k1/l5_infrastructure/admission/test_admission_controller.py
    - Config: k1/config/admission_control.yml
"""

import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum
# =============================================================================
# SECTION 1: IMPORTS
# =============================================================================
# Standard library imports
from typing import Any, Dict, List, Optional, Tuple

# Third-party imports
# None (pure Python)

# Internal imports
# TODO(@platform-team): Import after implementing dependent modules
# from k1.l5_infrastructure.admission.task_validator import TaskValidator, ValidationResult
# from k1.l5_infrastructure.rate_limiting.rate_limiter import RateLimiter
# from k1.l5_infrastructure.backpressure.backpressure_manager import BackpressureManager, BackpressureLevel
# from k1.l5_infrastructure.scheduling.scheduler import TaskScheduler
# from k1.l5_infrastructure.metrics import MetricsCollector

# Configure module logger
logger = logging.getLogger(__name__)

# =============================================================================
# SECTION 2: CONSTANTS & CONFIGURATION
# =============================================================================

# TODO(@platform-team): Load from k1/config/admission_control.yml (ADR-0032)
# Assigned to: Issue #L5-12.1.1
DEFAULT_CONFIG = {
    # Queue capacity and thresholds
    'queue_capacity': 10000,
    'reserved_slots_percentage': 10,  # 10% reserved for HIGH/CRITICAL

    # Watermark thresholds
    'soft_watermark': 0.75,  # Start throttling at 75%
    'hard_watermark': 0.85,  # Increase throttling at 85%
    'critical_watermark': 0.95,  # Reject LOW/BACKGROUND at 95%

    # Throttle rates
    'soft_throttle_rate': 0.10,  # Reject 10% of NORMAL tasks
    'hard_throttle_rate': 0.20,  # Reject 20% of NORMAL tasks

    # Anti-starvation config
    'starvation_check_interval_ms': 100,
    'starvation_threshold': 1000,  # Check after 1000 tasks admitted
    'high_priority_boost_factor': 4,  # If CRITICAL/HIGH underserved, boost admission

    # Performance budgets
    'admission_decision_timeout_ms': 10,
    'validation_timeout_ms': 2,
}

# =============================================================================
# SECTION 3: TYPE DEFINITIONS & ENUMS
# =============================================================================

class AdmissionDecision(Enum):
    """Admission decision states (ADR-0032)"""
    ADMITTED = 'ADMITTED'  # Task accepted, added to scheduler queue
    QUEUED = 'QUEUED'  # Task accepted but delayed, added to overflow queue
    RATE_LIMITED = 'RATE_LIMITED'  # Request rejected (quota exceeded)
    CAPACITY_EXCEEDED = 'CAPACITY_EXCEEDED'  # Request rejected (queue full)
    PRIVACY_VIOLATION = 'PRIVACY_VIOLATION'  # Request rejected (RED-band mismatch)
    TYPE_INVALID = 'TYPE_INVALID'  # Request rejected (unknown task type)
    SCHEMA_INVALID = 'SCHEMA_INVALID'  # Request rejected (schema validation failed)
    FALLBACK_DEGRADED = 'FALLBACK_DEGRADED'  # Task accepted with reduced SLA


class TaskPriority(Enum):
    """Task priority levels (ADR-0031)"""
    CRITICAL = 'CRITICAL'  # System tasks, errors, alerts
    HIGH = 'HIGH'  # User-facing requests, priority users
    NORMAL = 'NORMAL'  # Standard requests
    LOW = 'LOW'  # Background tasks
    BACKGROUND = 'BACKGROUND'  # Maintenance, cleanup


class PrivacyBand(Enum):
    """Privacy classification bands (ADR-0028d)"""
    RED = 'RED'  # Highly sensitive (e.g., health records, financial data)
    AMBER = 'AMBER'  # Moderately sensitive (e.g., personal preferences)
    GREEN = 'GREEN'  # Public or low-sensitivity data


class BackpressureLevel(Enum):
    """Backpressure watermark levels (ADR-0028)"""
    NORMAL = 'NORMAL'  # <75% queue depth
    SOFT = 'SOFT'  # 75-85% queue depth
    HARD = 'HARD'  # 85-95% queue depth
    CRITICAL = 'CRITICAL'  # >95% queue depth


@dataclass
class Request:
    """
    Incoming task request structure.

    Fields:
        request_id: Unique identifier (UUID4)
        task_type: Task type (e.g., "inference", "training")
        priority: Task priority level
        privacy_band: Privacy classification
        user_id: User identifier
        tenant_id: Tenant identifier
        payload: Request payload (task-specific data)
        deadline_ms: SLA deadline (milliseconds from now)
        cognitive_trace_id: Trace ID for observability
    """
    request_id: str
    task_type: str
    priority: TaskPriority
    privacy_band: PrivacyBand
    user_id: str
    tenant_id: str
    payload: Dict[str, Any]
    deadline_ms: int = 5000  # Default 5 second deadline
    cognitive_trace_id: Optional[str] = None


@dataclass
class AdmissionResult:
    """
    Admission decision result.

    Fields:
        decision: AdmissionDecision enum
        reason: Rejection reason (if rejected)
        queue_position: Position in queue (if queued)
        wait_estimate_ms: Estimated wait time (if queued)
        fallback_sla_ms: Reduced SLA (if degraded)
        metadata: Additional decision metadata
    """
    decision: AdmissionDecision
    reason: Optional[str] = None
    queue_position: Optional[int] = None
    wait_estimate_ms: Optional[int] = None
    fallback_sla_ms: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AdmissionStatus:
    """
    Current admission control state.

    Fields:
        queue_depth: Current tasks in queue
        queue_capacity: Max queue capacity
        queue_utilization: Queue depth / capacity
        backpressure_level: Current backpressure level
        acceptance_rate_1m: Acceptance rate (last 1 minute)
        acceptance_rate_5m: Acceptance rate (last 5 minutes)
        rejection_rate_1m: Rejection rate (last 1 minute)
        reserved_slots_used: High-priority reserved slots in use
        reserved_slots_total: Total high-priority reserved slots
    """
    queue_depth: int
    queue_capacity: int
    queue_utilization: float
    backpressure_level: BackpressureLevel
    acceptance_rate_1m: float
    acceptance_rate_5m: float
    rejection_rate_1m: float
    reserved_slots_used: int
    reserved_slots_total: int


@dataclass
class AdmissionMetrics:
    """
    Admission metrics snapshot.

    Fields:
        total_requests: Total requests processed
        total_admitted: Total requests admitted
        total_rejected: Total requests rejected
        acceptance_rate: Overall acceptance rate
        rejection_breakdown: Rejections by reason
        avg_decision_latency_ms: Average decision latency
        p95_decision_latency_ms: P95 decision latency
        anti_starvation_triggers: Count of anti-starvation interventions
    """
    total_requests: int
    total_admitted: int
    total_rejected: int
    acceptance_rate: float
    rejection_breakdown: Dict[str, int]
    avg_decision_latency_ms: float
    p95_decision_latency_ms: float
    anti_starvation_triggers: int


# =============================================================================
# SECTION 4: CORE CLASSES
# =============================================================================

class AdmissionController:
    """
    Core admission decision engine with multi-level validation and capacity checks.

    Purpose:
        Orchestrate admission decision pipeline: type validation → privacy check →
        rate limit check → capacity check → anti-starvation check → backpressure
        evaluation → admit/reject decision.

    Responsibilities:
        1. Receive incoming task requests
        2. Apply multi-level validation pipeline
        3. Check system capacity and backpressure signals
        4. Make binary admit/reject decision
        5. Apply fallback strategies (queueing, circuit breaker)
        6. Track admission metrics and telemetry
        7. Enforce anti-starvation guarantees for high-priority tasks

    Admission Pipeline (7 Checks in Order):
        1. Type Validation: Is task_type registered?
        2. Schema Validation: Does payload match schema?
        3. Privacy Check: Is privacy_band allowed?
        4. Rate Limit Check: Is user/tenant quota available?
        5. Anti-Starvation Check: Reserve slots for HIGH/CRITICAL
        6. Capacity Check: Is queue below thresholds?
        7. Backpressure Evaluation: Apply watermark policies

    Lifecycle:
        INIT → ACTIVE → [DEGRADED] → TERMINATED

    Thread Safety: Yes (async-safe with locks)
    Async Safe: Yes (fully async)

    Cognitive Trace:
        - Propagates cognitive_trace_id to downstream components
        - Required for: admit(), get_admission_status()

    Performance Budget (P95):
        - Admission decision: <10ms latency
        - Memory: <10MB for admission state
        - CPU: <5% target

    Examples:
        >>> config = DEFAULT_CONFIG
        >>> controller = AdmissionController(config)
        >>> await controller.initialize()
        >>> request = Request(request_id='req_123', task_type='inference', priority=TaskPriority.NORMAL, ...)
        >>> result = await controller.admit(request)
        >>> if result.decision == AdmissionDecision.ADMITTED:
        ...     # Enqueue to scheduler
        >>> await controller.shutdown()

    References:
        - ADR-0032: Admission Control Design
        - ADR-0002c: Actor Router & Admission Control (pattern reference)
        - Diagram: architecture_diagrams/k1/k1_admission_control.mmd
        - Connects to: TaskValidator, RateLimiter, BackpressureManager, TaskScheduler
    """

    def __init__(self, config: Dict[str, Any] = DEFAULT_CONFIG) -> None:
        """
        Initialize Admission Controller.

        Args:
            config: Configuration dict with queue capacity, thresholds, throttle rates

        Raises:
            ValueError: If configuration is invalid
            TypeError: If config type is incorrect

        Side Effects:
            - Initializes admission state
            - Creates metrics collectors
            - Registers with backpressure manager

        ADR: ADR-0032 (Admission Control Design)
        Assigned to: Issue #L5-12.1.1
        """
        # TODO(@platform-team): Implement initialization (ADR-0032)
        # 1. Validate config
        # 2. Initialize admission state
        # 3. Setup metrics exporters
        # 4. Create component references (task_validator, rate_limiter, etc.)
        # 5. Register with backpressure manager for watermark signals
        self.config = config
        self._logger = logger

        # Admission state
        self.queue_depth = 0
        self.queue_capacity = config['queue_capacity']
        self.reserved_slots_percentage = config['reserved_slots_percentage']
        self.reserved_slots_total = int(self.queue_capacity * self.reserved_slots_percentage / 100)
        self.reserved_slots_used = 0

        # Backpressure state
        self.backpressure_level = BackpressureLevel.NORMAL

        # Metrics state
        self.total_requests = 0
        self.total_admitted = 0
        self.total_rejected = 0
        self.rejection_breakdown: Dict[str, int] = {}
        self.anti_starvation_triggers = 0

        # Decision latency tracking (for P95 calculation)
        self.decision_latencies: List[float] = []

        # Anti-starvation tracking
        self.high_priority_admits_count = 0
        self.last_starvation_check_count = 0

        self._logger.info(f"AdmissionController initialized with queue_capacity={self.queue_capacity}, reserved_slots={self.reserved_slots_total}")

    async def initialize(self) -> None:
        """
        Async initialization phase (called after __init__).

        This method performs async setup that cannot be done in __init__.

        Raises:
            RuntimeError: If initialization fails
            ConnectionError: If cannot connect to dependencies

        Lifecycle:
            Called after __init__, before controller becomes active

        ADR: ADR-0032
        Assigned to: Issue #L5-12.1.1
        """
        # TODO(@platform-team): Implement async initialization (ADR-0032)
        # 1. Connect to task_validator
        # 2. Connect to rate_limiter
        # 3. Connect to backpressure_manager (register for signals)
        # 4. Connect to task_scheduler
        # 5. Start background tasks (metrics collection, starvation checks)
        # 6. Register with observability stack
        self._logger.info("AdmissionController async initialization started")
        pass

    async def admit(
        self,
        request: Request,
    ) -> AdmissionResult:
        """
        Evaluate and admit/reject incoming task request.

        This is the primary admission decision method that orchestrates the full
        validation pipeline.

        Args:
            request: Task request with type, priority, privacy_band, user_id, tenant_id

        Returns:
            AdmissionResult with decision, reason, queue position, wait estimate

        Raises:
            ValueError: If request is invalid
            TimeoutError: If decision exceeds budget (>10ms)
            RuntimeError: If controller is not ACTIVE

        Performance:
            - Target: <10ms P95 decision time
            - Max memory: <1KB per decision
            - Concurrent decisions: Unlimited (async-safe)

        Admission Pipeline (7 Checks):
            1. Type Validation: Is task_type registered?
            2. Schema Validation: Does payload match schema?
            3. Privacy Check: Is privacy_band allowed?
            4. Rate Limit Check: Is user/tenant quota available?
            5. Anti-Starvation Check: Reserve slots for HIGH/CRITICAL
            6. Capacity Check: Is queue below thresholds?
            7. Backpressure Evaluation: Apply watermark policies

        Observability:
            - Metrics: k1_admission_requests_total{status, priority}
            - Metrics: k1_admission_decision_latency_ms{p50, p95, p99}
            - Traces: Span name: admission_controller.admit
            - Logs: INFO: admission decision (request_id, decision, latency_ms)

        Cognitive Trace:
            - Accepts cognitive_trace_id from request
            - Propagates to all validation checks
            - Logs include trace_id

        ADR: ADR-0032 (Admission Control Design)
        Assigned to: Issue #L5-12.1.1
        Depends on: TaskValidator, RateLimiter, BackpressureManager
        """
        # TODO(@platform-team): Implement admission decision pipeline (ADR-0032)
        # 1. Record start time (for latency measurement)
        # 2. Create trace span with cognitive_trace_id
        # 3. Run validation pipeline (7 checks)
        # 4. Make admit/reject decision
        # 5. Apply fallback strategies if needed
        # 6. Record metrics (decision, latency, priority)
        # 7. Emit logs and traces
        # 8. Return AdmissionResult
        # Performance target: <10ms P95

        start_time_ms = time.time() * 1000
        self.total_requests += 1

        self._logger.info(
            f"Admission request received: request_id={request.request_id}, "
            f"task_type={request.task_type}, priority={request.priority.value}, "
            f"trace_id={request.cognitive_trace_id}"
        )

        # Algorithm implementation (pseudo-code from milestone spec)
        decision, reason = await self._evaluate_admission_pipeline(request)

        # Calculate decision latency
        end_time_ms = time.time() * 1000
        decision_latency_ms = end_time_ms - start_time_ms
        self.decision_latencies.append(decision_latency_ms)

        # Update metrics
        if decision == AdmissionDecision.ADMITTED:
            self.total_admitted += 1
            self.queue_depth += 1
        else:
            self.total_rejected += 1
            self.rejection_breakdown[decision.value] = self.rejection_breakdown.get(decision.value, 0) + 1

        result = AdmissionResult(
            decision=decision,
            reason=reason,
            metadata={'decision_latency_ms': decision_latency_ms}
        )

        self._logger.info(
            f"Admission decision: request_id={request.request_id}, "
            f"decision={decision.value}, reason={reason or 'N/A'}, "
            f"latency_ms={decision_latency_ms:.2f}"
        )

        return result

    async def _evaluate_admission_pipeline(
        self,
        request: Request,
    ) -> Tuple[AdmissionDecision, Optional[str]]:
        """
        Run admission pipeline checks (internal method).

        Args:
            request: Task request to evaluate

        Returns:
            (decision, reason) tuple

        Checks (in order):
            1. Type validation
            2. Schema validation
            3. Privacy check
            4. Rate limit check
            5. Anti-starvation check
            6. Capacity check
            7. Backpressure evaluation

        ADR: ADR-0032
        """
        # TODO(@platform-team): Implement pipeline checks (ADR-0032)
        # This is the core decision algorithm from the milestone spec

        # 1. Type Validation
        # if not is_valid_task_type(request.task_type):
        #     return AdmissionDecision.TYPE_INVALID, f"Unknown task type: {request.task_type}"

        # 2. Schema Validation
        # validation_result = await task_validator.validate(request)
        # if not validation_result.is_valid:
        #     return AdmissionDecision.SCHEMA_INVALID, validation_result.error_message

        # 3. Privacy Check
        # if not privacy_enforcer.can_admit(request.privacy_band):
        #     return AdmissionDecision.PRIVACY_VIOLATION, f"Privacy band {request.privacy_band.value} not allowed"

        # 4. Rate Limit Check
        # is_allowed, rate_limit_info = await rate_limiter.is_allowed(request.user_id, request.tenant_id)
        # if not is_allowed:
        #     return AdmissionDecision.RATE_LIMITED, f"User/tenant quota exceeded"

        # 5. Anti-Starvation Check (Override if needed)
        if request.priority in [TaskPriority.CRITICAL, TaskPriority.HIGH]:
            if self.reserved_slots_used < self.reserved_slots_total:
                # Use reserved slot
                self.reserved_slots_used += 1
                self._logger.info(f"Anti-starvation: Using reserved slot for {request.priority.value} task (used={self.reserved_slots_used}/{self.reserved_slots_total})")
                return AdmissionDecision.ADMITTED, "Reserved slot used (anti-starvation)"

        # 6. Capacity Check
        queue_utilization = self.queue_depth / self.queue_capacity
        if queue_utilization >= self.config['critical_watermark']:  # 95%
            if request.priority in [TaskPriority.LOW, TaskPriority.BACKGROUND]:
                return AdmissionDecision.CAPACITY_EXCEEDED, "Critical watermark: LOW/BACKGROUND rejected"
            if request.priority == TaskPriority.NORMAL:
                # Throttle NORMAL tasks (allow 20%)
                if random.random() > 0.8:
                    return AdmissionDecision.QUEUED, "Critical watermark: NORMAL throttled (20% allowed)"
                else:
                    return AdmissionDecision.CAPACITY_EXCEEDED, "Critical watermark: NORMAL rejected"

        # 7. Backpressure Evaluation
        if self.backpressure_level == BackpressureLevel.CRITICAL and request.priority == TaskPriority.LOW:
            return AdmissionDecision.CAPACITY_EXCEEDED, "Critical backpressure: LOW rejected"

        # If all checks pass, admit
        return AdmissionDecision.ADMITTED, None

    async def get_admission_status(self) -> AdmissionStatus:
        """
        Get current admission control state (capacity, queue depth, rejection rate).

        Returns:
            AdmissionStatus with queue_depth, capacity, rejection_rate, backpressure_level

        Performance:
            - <5ms P95

        Observability:
            - Metrics: k1_admission_queue_depth (gauge)
            - Metrics: k1_admission_acceptance_rate{window} (gauge)

        ADR: ADR-0032
        Assigned to: Issue #L5-12.1.1
        """
        # TODO(@platform-team): Implement status reporting (ADR-0032)
        # 1. Calculate queue utilization
        # 2. Calculate acceptance rates (1m, 5m windows)
        # 3. Get current backpressure level
        # 4. Return AdmissionStatus

        queue_utilization = self.queue_depth / self.queue_capacity if self.queue_capacity > 0 else 0.0
        acceptance_rate_1m = self.total_admitted / self.total_requests if self.total_requests > 0 else 1.0
        acceptance_rate_5m = acceptance_rate_1m  # TODO: Implement time-windowed calculation
        rejection_rate_1m = self.total_rejected / self.total_requests if self.total_requests > 0 else 0.0

        return AdmissionStatus(
            queue_depth=self.queue_depth,
            queue_capacity=self.queue_capacity,
            queue_utilization=queue_utilization,
            backpressure_level=self.backpressure_level,
            acceptance_rate_1m=acceptance_rate_1m,
            acceptance_rate_5m=acceptance_rate_5m,
            rejection_rate_1m=rejection_rate_1m,
            reserved_slots_used=self.reserved_slots_used,
            reserved_slots_total=self.reserved_slots_total,
        )

    async def update_backpressure_signal(self, level: BackpressureLevel) -> None:
        """
        Receive backpressure signal from downstream (watermark change).

        Args:
            level: BackpressureLevel (NORMAL, SOFT, HARD, CRITICAL)

        Behavior:
            - Updates internal backpressure state
            - Adjusts admission thresholds dynamically
            - Emits metrics on level change

        Observability:
            - Logs: INFO: backpressure level changed

        ADR: ADR-0028 (Backpressure integration)
        Assigned to: Issue #L5-12.1.1
        """
        # TODO(@platform-team): Implement backpressure signal handling (ADR-0028)
        # 1. Update internal backpressure state
        # 2. Adjust admission thresholds if needed
        # 3. Emit metrics
        # 4. Log level change

        old_level = self.backpressure_level
        self.backpressure_level = level

        if old_level != level:
            self._logger.info(f"Backpressure level changed: {old_level.value} → {level.value}")

    async def get_metrics(self) -> AdmissionMetrics:
        """
        Get admission metrics (acceptance rate, rejections by reason, anti-starvation triggers).

        Returns:
            AdmissionMetrics with acceptance_rate, rejection_breakdown, starvation_triggers

        Performance:
            - <5ms P95

        Observability:
            - Metrics: All admission metrics exported to Prometheus

        ADR: ADR-0032
        Assigned to: Issue #L5-12.1.1
        """
        # TODO(@platform-team): Implement metrics collection (ADR-0032)
        # 1. Calculate acceptance rate
        # 2. Calculate rejection breakdown
        # 3. Calculate P95 decision latency
        # 4. Return AdmissionMetrics

        acceptance_rate = self.total_admitted / self.total_requests if self.total_requests > 0 else 1.0

        # Calculate P95 latency
        sorted_latencies = sorted(self.decision_latencies)
        p95_index = int(len(sorted_latencies) * 0.95)
        p95_latency_ms = sorted_latencies[p95_index] if sorted_latencies else 0.0
        avg_latency_ms = sum(self.decision_latencies) / len(self.decision_latencies) if self.decision_latencies else 0.0

        return AdmissionMetrics(
            total_requests=self.total_requests,
            total_admitted=self.total_admitted,
            total_rejected=self.total_rejected,
            acceptance_rate=acceptance_rate,
            rejection_breakdown=self.rejection_breakdown.copy(),
            avg_decision_latency_ms=avg_latency_ms,
            p95_decision_latency_ms=p95_latency_ms,
            anti_starvation_triggers=self.anti_starvation_triggers,
        )

    async def shutdown(self) -> None:
        """
        Graceful shutdown sequence.

        This method performs cleanup and state transitions.

        Lifecycle:
            - Stops accepting new requests
            - Waits for in-flight admission decisions (timeout: 10s)
            - Flushes metrics
            - Closes connections

        Guarantees:
            - No data loss
            - Graceful degradation

        ADR: ADR-0032
        Assigned to: Issue #L5-12.1.1
        """
        # TODO(@platform-team): Implement shutdown (ADR-0032)
        # 1. Stop accepting new requests
        # 2. Wait for in-flight decisions (with timeout)
        # 3. Flush final metrics
        # 4. Close connections to dependencies
        # 5. Log shutdown complete
        self._logger.info("AdmissionController shutdown initiated")
        pass

    # =========================================================================
    # PRIVATE METHODS (Implementation Details)
    # =========================================================================

    async def _check_anti_starvation(self) -> None:
        """
        Periodic anti-starvation check (background task).

        Behavior:
            - Runs every starvation_check_interval_ms
            - Checks if HIGH/CRITICAL tasks underserved
            - Boosts admission probability if needed

        ADR: ADR-0032
        Assigned to: Issue #L5-12.1.1
        """
        # TODO(@platform-team): Implement anti-starvation monitoring (ADR-0032)
        # 1. Calculate service rate for HIGH/CRITICAL
        # 2. Compare to expected rate (based on arrival rate)
        # 3. If underserved: Boost reserved slots temporarily
        # 4. Record anti_starvation_triggers metric
        pass


# =============================================================================
# SECTION 5: HELPER FUNCTIONS
# =============================================================================

def calculate_queue_utilization(queue_depth: int, queue_capacity: int) -> float:
    """
    Calculate queue utilization percentage.

    Args:
        queue_depth: Current tasks in queue
        queue_capacity: Max queue capacity

    Returns:
        Utilization as float (0.0-1.0)

    Raises:
        ValueError: If capacity is 0 or negative

    ADR: ADR-0032
    Assigned to: Issue #L5-12.1.1
    """
    # TODO(@platform-team): Implement queue utilization calculation (ADR-0032)
    if queue_capacity <= 0:
        raise ValueError("Queue capacity must be positive")
    return queue_depth / queue_capacity


def should_throttle(
    queue_utilization: float,
    priority: TaskPriority,
    soft_threshold: float,
    hard_threshold: float,
    soft_throttle_rate: float,
    hard_throttle_rate: float,
) -> Tuple[bool, Optional[str]]:
    """
    Determine if request should be throttled based on queue utilization.

    Args:
        queue_utilization: Current queue utilization (0.0-1.0)
        priority: Task priority
        soft_threshold: Soft watermark (e.g., 0.75)
        hard_threshold: Hard watermark (e.g., 0.85)
        soft_throttle_rate: Throttle rate at soft (e.g., 0.10)
        hard_throttle_rate: Throttle rate at hard (e.g., 0.20)

    Returns:
        (should_throttle: bool, reason: optional)

    Logic:
        - <soft: No throttling
        - soft-hard: Throttle NORMAL at soft_throttle_rate
        - >hard: Throttle NORMAL at hard_throttle_rate
        - CRITICAL/HIGH: Never throttled (except at critical watermark)

    ADR: ADR-0032, ADR-0028
    Assigned to: Issue #L5-12.1.1
    """
    # TODO(@platform-team): Implement throttling decision logic (ADR-0032, ADR-0028)
    # 1. Check priority (CRITICAL/HIGH bypass throttling)
    # 2. Check queue utilization against thresholds
    # 3. Apply probabilistic throttling (random() > threshold)
    # 4. Return throttle decision with reason
    return False, None


# =============================================================================
# SECTION 6: MODULE EXPORTS & INITIALIZATION
# =============================================================================

__all__ = [
    'AdmissionController',
    'AdmissionDecision',
    'AdmissionResult',
    'AdmissionStatus',
    'AdmissionMetrics',
    'Request',
    'TaskPriority',
    'PrivacyBand',
    'BackpressureLevel',
]

# Module initialization hook (optional)
async def initialize_admission_controller(config: Dict[str, Any] = DEFAULT_CONFIG) -> AdmissionController:
    """
    Initialize admission controller with default configuration.

    Args:
        config: Configuration dict (defaults to DEFAULT_CONFIG)

    Returns:
        Initialized AdmissionController instance

    ADR: ADR-0032
    """
    # TODO(@platform-team): Implement module initialization (ADR-0032)
    controller = AdmissionController(config)
    await controller.initialize()
    return controller


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================
# Metrics to export:
#   - k1_admission_requests_total{status, priority} - Total admission requests
#   - k1_admission_decision_latency_ms{p50, p95, p99} - Decision latency histogram
#   - k1_admission_acceptance_rate{window} - Acceptance rate by time window
#   - k1_admission_rejections_total{reason, priority} - Rejection count by reason
#   - k1_admission_queue_depth - Current queue depth gauge
#   - k1_admission_anti_starvation_triggers_total - Anti-starvation interventions
#   - k1_admission_reserved_slots_used{priority} - Reserved slots in use
#
# Traces to generate:
#   - Span name: admission_controller.admit
#   - Attributes: request_id, task_type, priority, privacy_band, decision, cognitive_trace_id
#   - Child spans: task_validator.validate, rate_limiter.check, backpressure_manager.get_level
#
# Logs to emit:
#   - Level: INFO (admission decision), WARNING (rate limit, capacity), ERROR (privacy violation)
#   - Fields: request_id, task_type, priority, decision, reason, latency_ms, trace_id
#
# =============================================================================

# =============================================================================
# COGNITIVE TRACE PROPAGATION
# =============================================================================
# All async methods must:
#   1. Accept cognitive_trace_id parameter in Request
#   2. Create trace span with this ID
#   3. Pass ID to downstream components (task_validator, rate_limiter, etc.)
#   4. Include ID in all log statements
#
# This enables end-to-end request tracing across K1 layers.
#
# =============================================================================

# =============================================================================
# TESTING REQUIREMENTS (pytest Framework)
# =============================================================================
# Integration tests required:
#   - tests/k1/l5_infrastructure/admission/test_admission_controller.py
#   - Contract validation tests (Request schema, AdmissionResult schema)
#   - Performance budget tests (ensure <10ms P95 decision time)
#   - Error handling tests (rate limit, capacity, privacy violations)
#   - Anti-starvation tests (verify reserved slots work correctly)
#   - Backpressure integration tests (verify watermark policy enforcement)
#
# No simulation code allowed:
#   - No asyncio.sleep() for testing timeouts
#   - Use real components or pytest fixtures
#   - Integration tests > unit tests
#
# =============================================================================
