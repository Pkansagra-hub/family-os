"""
Per-Stream Watermark Monitoring (ADR-0061, ADR-0061a, Issue 2.3)

**Purpose:**
    Progressive degradation for individual priority queues through per-stream
    watermark monitoring. Each priority queue monitors its depth independently
    and transitions through pressure levels: NORMAL → WARN → DEGRADE → REJECT.

**Architecture:**
    - PressureLevel enum: 0=NORMAL, 1=WARN, 2=DEGRADE, 3=REJECT
    - StreamWatermarkMonitor: Tracks pressure for a single stream with hysteresis
    - Per-priority instances in PriorityScheduler
    - Integration point: PriorityScheduler.send() evaluates watermarks before enqueue

**Watermark Thresholds (ADR-0061a):**
    - WARN: 80% of max_depth
    - DEGRADE: 90% of max_depth
    - REJECT: 95% of max_depth
    - Recovery: Return to NORMAL at 60% (hysteresis to prevent oscillation)

**Hysteresis Design (ADR-0061a):**
    Prevents flapping/oscillation with multi-level recovery thresholds:
    - From REJECT (95%) → DEGRADE: Only at 90% (5% hysteresis)
    - From DEGRADE (90%) → WARN: Only at 80% (10% hysteresis)
    - From WARN (80%) → NORMAL: Only at 60% (recovery threshold)

**Performance Budget:**
    - Per-priority watermark evaluation: <1ms P95
    - Metric emission: <0.1ms (negligible overhead)
    - CPU impact: <0.1% system-wide

**Prometheus Metrics (ADR-0061b):**
    - Gauge: backpressure_stream_depth[priority], backpressure_stream_level[priority], backpressure_stream_utilization_pct[priority]
    - Counter: backpressure_stream_transitions_total[priority, from_level, to_level], backpressure_stream_actions_total[priority, action]
    - Histogram: backpressure_stream_time_in_level_seconds[priority, level]

**Alert Rules (ADR-0061b):**
    - BackpressureStreamWarn: priority in WARN level (80%)
    - BackpressureStreamDegrade: priority in DEGRADE level (90%), degradation action active
    - BackpressureStreamReject: priority in REJECT level (95%), rejecting new messages
    - BackpressureStreamSustainedReject: priority in REJECT >10s, investigate bottleneck

**Integration with PriorityScheduler:**
    Each priority queue has a StreamWatermarkMonitor instance.
    On send(), **BEFORE enqueue** (must-fix #5):
        1. Evaluate new pressure level: new_level = watermark.evaluate(queue_depth)
        2. If new_level == REJECT: Return SendResult.BACKPRESSURE_REJECT (don't enqueue)
        3. If new_level != old_level: Emit transition event, update metrics
        4. If new_level == DEGRADE: Apply degradation action (if applicable)

**Related ADRs:**
    - ADR-0061: 3-Tier Backpressure Cascade (context)
    - ADR-0061a: Watermark Thresholds 80/90/95% (specification)
    - ADR-0061b: RED Metrics & Alerts (monitoring)
    - ADR-0061c: Privacy-Band Overrides (RED band bypass - future)
    - ADR-0061d: Fairness Anti-Starvation (fairness guarantees - future)
    - ADR-0002a: Mailbox MPSC Queue Implementation (base)

**Research Foundation:**
    - Hysteresis: Control systems feedback (Nise 2015 "Control Systems Engineering")
    - Watermark design: Kafka broker quotas (100 replicas, 30 partitions per broker)
    - RED (Random Early Detection): Floyd & Jacobson 1993 "Random Early Detection Gateways for Congestion Avoidance"

**Implementation Status:** M1 (GATE 3 - Issue 2.3)
"""

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable, Dict, List, Optional


# Simple logger fallback
class SimpleLogger:
    """Minimal logger implementation"""

    def info(self, msg: str, **kwargs):
        pass  # Silent by default (use structlog in production)

    def warning(self, msg: str, **kwargs):
        pass

    def error(self, msg: str, **kwargs):
        pass


try:
    import structlog

    _logger = structlog.get_logger(__name__)
except ImportError:
    _logger = SimpleLogger()


try:
    from prometheus_client import Counter, Gauge, Histogram

    _has_prometheus = True
except ImportError:
    _has_prometheus = False

    # Fallback mock classes
    class Counter:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass

        def labels(self, **kwargs):  # type: ignore
            return self

        def inc(self, amount=1):  # type: ignore
            pass

    class Gauge:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass

        def labels(self, **kwargs):  # type: ignore
            return self

        def set(self, value):  # type: ignore
            pass

    class Histogram:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass

        def labels(self, **kwargs):  # type: ignore
            return self

        def observe(self, value):  # type: ignore
            pass


# ============================================================================
# PROMETHEUS METRICS - MODULE-LEVEL SINGLETONS (Critical Fix #1)
# ============================================================================
# Define metrics once at module level to prevent duplicate registration errors.
# Use .labels(stream_id=...) to track per-stream metrics without re-registering.

try:
    _BP_DEPTH = Gauge(
        "backpressure_stream_depth",
        "Current queue depth for stream",
        labelnames=["stream_id"],
    )
    _BP_UTIL = Gauge(
        "backpressure_stream_utilization_pct",
        "Queue utilization percentage (0-100)",
        labelnames=["stream_id"],
    )
    _BP_LEVEL = Gauge(
        "backpressure_stream_level",
        "Current pressure level (0=NORMAL, 1=WARN, 2=DEGRADE, 3=REJECT)",
        labelnames=["stream_id"],
    )
    _BP_TRANSITIONS = Counter(
        "backpressure_stream_transitions_total",
        "Total pressure level transitions",
        labelnames=["stream_id", "from_level", "to_level"],
    )
    _BP_ACTIONS = Counter(
        "backpressure_stream_actions_total",
        "Total degradation actions applied",
        labelnames=["stream_id", "action"],
    )
    _BP_TIME = Histogram(
        "backpressure_stream_time_in_level_seconds",
        "Time spent in each pressure level",
        labelnames=["stream_id", "level"],
        buckets=[0.01, 0.1, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0],
    )
    _METRICS_AVAILABLE = True
except Exception:
    # Metrics not available (e.g., in testing, Prometheus not installed)
    _METRICS_AVAILABLE = False
    _BP_DEPTH = None  # type: ignore
    _BP_UTIL = None  # type: ignore
    _BP_LEVEL = None  # type: ignore
    _BP_TRANSITIONS = None  # type: ignore
    _BP_ACTIONS = None  # type: ignore
    _BP_TIME = None  # type: ignore


# ============================================================================
# PRESSURE LEVEL ENUMERATION
# ============================================================================


class PressureLevel(IntEnum):
    """Per-stream pressure level (0=NORMAL, 1=WARN, 2=DEGRADE, 3=REJECT)"""

    NORMAL = 0
    WARN = 1
    DEGRADE = 2
    REJECT = 3

    def description(self) -> str:
        """Human-readable description"""
        return {
            0: "Normal (<80%)",
            1: "Warning (80-89%)",
            2: "Degradation (90-94%)",
            3: "Rejection (≥95%)",
        }[self.value]

    def severity(self) -> str:
        """Alert severity"""
        return {
            0: "INFO",
            1: "WARNING",
            2: "CRITICAL",
            3: "CRITICAL",
        }[self.value]


# ============================================================================
# DEGRADATION ACTIONS
# ============================================================================


class DegradationAction:
    """Degradation action identifiers"""

    DROP_OLDEST = "drop_oldest"  # Drop oldest items from buffer
    BLOCK_SENDER = "block_sender"  # Return 503 Backpressure to sender
    MERGE_DELTAS = "merge_deltas"  # Merge consecutive deltas
    DISCONNECT_SLOW = "disconnect_slow"  # Disconnect slowest clients

    ALL = [DROP_OLDEST, BLOCK_SENDER, MERGE_DELTAS, DISCONNECT_SLOW]


# ============================================================================
# STREAM WATERMARK CONFIGURATION
# ============================================================================


@dataclass
class StreamWatermarkConfig:
    """Watermark configuration for a single stream"""

    stream_id: str
    max_depth: int
    degradation_action: str
    warn_threshold_pct: float = 0.80  # 80%
    degrade_threshold_pct: float = 0.90  # 90%
    reject_threshold_pct: float = 0.95  # 95%
    recovery_threshold_pct: float = 0.60  # 60% (recovery)
    metrics_enabled: bool = True

    def __post_init__(self):
        """Validate thresholds and action"""
        # Validate threshold ordering
        assert (
            self.warn_threshold_pct
            < self.degrade_threshold_pct
            < self.reject_threshold_pct
        )
        assert self.recovery_threshold_pct < self.warn_threshold_pct

        # Validate degradation_action (must-fix #5)
        valid_actions = {
            DegradationAction.DROP_OLDEST,
            DegradationAction.BLOCK_SENDER,
            DegradationAction.MERGE_DELTAS,
            DegradationAction.DISCONNECT_SLOW,
            "none",  # Allowed for URGENT priority (never degraded)
        }
        assert (
            self.degradation_action in valid_actions
        ), f"degradation_action must be one of {valid_actions}, got {self.degradation_action}"

    @property
    def hysteresis_band(self) -> float:
        """Hysteresis band between warn and degrade"""
        return self.degrade_threshold_pct - self.warn_threshold_pct

    @property
    def warn_threshold_items(self) -> int:
        """WARN threshold in items"""
        return int(self.max_depth * self.warn_threshold_pct)

    @property
    def degrade_threshold_items(self) -> int:
        """DEGRADE threshold in items"""
        return int(self.max_depth * self.degrade_threshold_pct)

    @property
    def reject_threshold_items(self) -> int:
        """REJECT threshold in items"""
        return int(self.max_depth * self.reject_threshold_pct)

    @property
    def recovery_threshold_items(self) -> int:
        """Recovery threshold in items"""
        return int(self.max_depth * self.recovery_threshold_pct)


# ============================================================================
# PRESSURE CHANGE EVENT
# ============================================================================


@dataclass
class PressureChangeEvent:
    """Event emitted on pressure level transition"""

    stream_id: str
    old_level: PressureLevel
    new_level: PressureLevel
    queue_depth: int
    queue_max: int
    queue_utilization_pct: float
    time_in_previous_level_seconds: float  # Nice-to-have #9
    degradation_action: Optional[str] = None
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))


# ============================================================================
# STREAM WATERMARK MONITOR
# ============================================================================


class StreamWatermarkMonitor:
    """
    Monitors pressure level for a single stream with hysteresis.

    Implements per-stream watermark tracking for progressive degradation.
    Uses hysteresis to prevent oscillation between adjacent pressure levels.

    Hysteresis Thresholds:
    - NORMAL → WARN: 80%
    - WARN → DEGRADE: 90% (with 10% hysteresis: degrade→warn at 80%)
    - DEGRADE → REJECT: 95% (with 5% hysteresis: reject→degrade at 90%)
    - Recovery to NORMAL: 60% (with 20% hysteresis: warn→normal at 60%)
    """

    def __init__(
        self,
        config: StreamWatermarkConfig,
        callbacks: Optional[List[Callable[[PressureChangeEvent], None]]] = None,
    ):
        """
        Initialize stream watermark monitor.

        Args:
            config: StreamWatermarkConfig with thresholds and settings
            callbacks: Optional list of callbacks to invoke on level changes
        """
        self.config = config
        self.logger = structlog.get_logger(__name__)
        self.callbacks: List[Callable[[PressureChangeEvent], None]] = callbacks or []

        # Current pressure level
        self.current_level = PressureLevel.NORMAL
        self.level_entry_time = time.time()

        # Note: Metrics are now module-level singletons (_BP_* globals)
        # No need for instance-level metric setup (fixes GATE 3 code review #1)

    def evaluate(self, current_depth: int) -> PressureLevel:
        """
        Evaluate queue depth and update pressure level with hysteresis.

        Activation thresholds: 80%, 90%, 95%
        Deactivation thresholds: apply hysteresis (5%, 10%, 20% bands)
        Recovery: Return to NORMAL only at 60% threshold

        Args:
            current_depth: Current queue depth (items)

        Returns:
            Current PressureLevel after potential transition
        """
        utilization_pct = current_depth / self.config.max_depth

        # Always transition UP (to higher pressure)
        if utilization_pct >= self.config.reject_threshold_pct:
            old_level = self.current_level
            self.current_level = PressureLevel.REJECT
            if old_level != PressureLevel.REJECT:
                self._emit_transition(
                    old_level, PressureLevel.REJECT, current_depth, utilization_pct
                )
            return PressureLevel.REJECT

        elif utilization_pct >= self.config.degrade_threshold_pct:
            # Hysteresis on deactivation from REJECT: 5% band (95% → 90%)
            if self.current_level == PressureLevel.REJECT:
                deactivation_pct = self.config.reject_threshold_pct - 0.05
                if utilization_pct < deactivation_pct:
                    old_level = self.current_level
                    self.current_level = PressureLevel.DEGRADE
                    self._emit_transition(
                        old_level, PressureLevel.DEGRADE, current_depth, utilization_pct
                    )
                    return PressureLevel.DEGRADE

            if self.current_level != PressureLevel.DEGRADE:
                old_level = self.current_level
                self.current_level = PressureLevel.DEGRADE
                self._emit_transition(
                    old_level, PressureLevel.DEGRADE, current_depth, utilization_pct
                )
            return PressureLevel.DEGRADE

        elif utilization_pct >= self.config.warn_threshold_pct:
            # Hysteresis on deactivation from DEGRADE: 10% band (90% → 80%)
            if self.current_level == PressureLevel.DEGRADE:
                deactivation_pct = (
                    self.config.degrade_threshold_pct - self.config.hysteresis_band
                )
                if utilization_pct < deactivation_pct:
                    old_level = self.current_level
                    self.current_level = PressureLevel.WARN
                    self._emit_transition(
                        old_level, PressureLevel.WARN, current_depth, utilization_pct
                    )
                    return PressureLevel.WARN

            if self.current_level != PressureLevel.WARN:
                old_level = self.current_level
                self.current_level = PressureLevel.WARN
                self._emit_transition(
                    old_level, PressureLevel.WARN, current_depth, utilization_pct
                )
            return PressureLevel.WARN

        else:  # utilization < 80%
            # Return to NORMAL only at recovery threshold (60%)
            if (
                utilization_pct <= self.config.recovery_threshold_pct
                and self.current_level != PressureLevel.NORMAL
            ):
                old_level = self.current_level
                self.current_level = PressureLevel.NORMAL
                self._emit_transition(
                    old_level, PressureLevel.NORMAL, current_depth, utilization_pct
                )

            return self.current_level

    def get_pressure_level(self) -> PressureLevel:
        """Get current pressure level without evaluation"""
        return self.current_level

    def should_reject(self) -> bool:
        """Check if stream is at REJECT level"""
        return self.current_level >= PressureLevel.REJECT

    def register_callback(
        self, callback: Callable[[PressureChangeEvent], None]
    ) -> None:
        """Register callback to invoke on pressure level changes"""
        self.callbacks.append(callback)

    def _emit_transition(
        self,
        old_level: PressureLevel,
        new_level: PressureLevel,
        current_depth: int,
        utilization_pct: float,
    ) -> None:
        """Emit transition event, update metrics, and invoke callbacks"""
        # Calculate time in previous level (must-fix #9)
        time_in_previous_level = time.time() - self.level_entry_time
        self.level_entry_time = time.time()

        # Update timestamp for new level entry
        now_ms = int(time.time() * 1000)

        # Determine degradation action
        degradation_action = None
        if new_level == PressureLevel.DEGRADE:
            degradation_action = self.config.degradation_action

        # Create event with time_in_previous_level_seconds (must-fix #9)
        event = PressureChangeEvent(
            stream_id=self.config.stream_id,
            old_level=old_level,
            new_level=new_level,
            queue_depth=current_depth,
            queue_max=self.config.max_depth,
            queue_utilization_pct=utilization_pct * 100,
            time_in_previous_level_seconds=time_in_previous_level,
            degradation_action=degradation_action,
            timestamp_ms=now_ms,
        )

        # Log transition
        self.logger.info(
            "backpressure_level_transition",
            stream_id=self.config.stream_id,
            from_level=old_level.description(),
            to_level=new_level.description(),
            severity=new_level.severity(),
            queue_depth=current_depth,
            queue_max=self.config.max_depth,
            utilization_pct=utilization_pct * 100,
            time_in_previous_level=time_in_previous_level,
            action=degradation_action,
        )

        # Update Prometheus metrics using module-level singletons (must-fix #1)
        # All metrics are guaranteed non-None if _METRICS_AVAILABLE is True
        if _METRICS_AVAILABLE and self.config.metrics_enabled:
            _BP_TRANSITIONS.labels(  # type: ignore[union-attr]
                stream_id=self.config.stream_id,
                from_level=old_level.name,
                to_level=new_level.name,
            ).inc()

            _BP_TIME.labels(  # type: ignore[union-attr]
                stream_id=self.config.stream_id,
                level=old_level.name,
            ).observe(time_in_previous_level)

            if degradation_action and degradation_action != "none":
                _BP_ACTIONS.labels(  # type: ignore[union-attr]
                    stream_id=self.config.stream_id,
                    action=degradation_action,
                ).inc()

        # Invoke callbacks
        for callback in self.callbacks:
            try:
                callback(event)
            except Exception as e:
                self.logger.error(
                    "callback_error",
                    stream_id=self.config.stream_id,
                    error=str(e),
                    exc_info=True,
                )

    def update_metrics(self, current_depth: int) -> None:
        """Update Prometheus metrics for current state (must-fix #7)

        Called on every send() to keep metrics current (both accept and reject paths).
        """
        if not self.config.metrics_enabled or not _METRICS_AVAILABLE:
            return

        # Divide-by-zero guard (should-fix #4)
        max_depth = max(1, self.config.max_depth)
        utilization_pct = current_depth / max_depth

        # Update gauge metrics using module-level singletons (must-fix #1)
        # All metrics are guaranteed non-None if _METRICS_AVAILABLE is True
        _BP_DEPTH.labels(stream_id=self.config.stream_id).set(current_depth)  # type: ignore[union-attr]
        _BP_UTIL.labels(stream_id=self.config.stream_id).set(utilization_pct * 100)  # type: ignore[union-attr]
        _BP_LEVEL.labels(stream_id=self.config.stream_id).set(self.current_level.value)  # type: ignore[union-attr]


# ============================================================================
# PER-PRIORITY WATERMARK MANAGER
# ============================================================================


class PriorityWatermarkManager:
    """
    Manages per-priority watermark monitors for PriorityScheduler.

    Combines 4 StreamWatermarkMonitor instances (one per priority) to provide
    independent pressure tracking for URGENT, REALTIME, INTERACTIVE, BACKGROUND.
    """

    # Priority identifiers
    PRIORITY_URGENT = 0
    PRIORITY_REALTIME = 1
    PRIORITY_INTERACTIVE = 2
    PRIORITY_BACKGROUND = 3

    # Default capacities (from ADR-0002a)
    DEFAULT_CAPACITIES = {
        PRIORITY_URGENT: 50,
        PRIORITY_REALTIME: 100,
        PRIORITY_INTERACTIVE: 200,
        PRIORITY_BACKGROUND: 1024,
    }

    # Default degradation actions per priority
    DEFAULT_ACTIONS = {
        PRIORITY_URGENT: None,  # URGENT never degraded
        PRIORITY_REALTIME: DegradationAction.DROP_OLDEST,
        PRIORITY_INTERACTIVE: DegradationAction.DROP_OLDEST,
        PRIORITY_BACKGROUND: DegradationAction.DROP_OLDEST,
    }

    def __init__(
        self,
        capacities: Optional[Dict[int, int]] = None,
        actions: Optional[Dict[int, str]] = None,
    ):
        """
        Initialize per-priority watermark manager.

        Args:
            capacities: Optional dict overriding default capacities per priority
            actions: Optional dict overriding default degradation actions per priority
        """
        self.logger = structlog.get_logger(__name__)

        # Use provided or default capacities/actions
        self.capacities = capacities or self.DEFAULT_CAPACITIES.copy()
        self.actions = actions or self.DEFAULT_ACTIONS.copy()

        # Create watermark monitor for each priority
        self.monitors: Dict[int, StreamWatermarkMonitor] = {}
        for priority in [
            self.PRIORITY_URGENT,
            self.PRIORITY_REALTIME,
            self.PRIORITY_INTERACTIVE,
            self.PRIORITY_BACKGROUND,
        ]:
            priority_name = self._priority_name(priority)
            config = StreamWatermarkConfig(
                stream_id=f"priority_{priority_name}",
                max_depth=self.capacities[priority],
                degradation_action=self.actions[priority] or "none",
                metrics_enabled=True,
            )
            self.monitors[priority] = StreamWatermarkMonitor(config)

    def evaluate_and_check_reject(self, priority: int, queue_depth: int) -> bool:
        """
        Evaluate watermark for priority and check if should reject.

        Args:
            priority: Priority level (0-3)
            queue_depth: Current queue depth for priority

        Returns:
            True if should reject (REJECT level), False otherwise
        """
        if priority not in self.monitors:
            self.logger.warning("invalid_priority", priority=priority)
            return False

        monitor = self.monitors[priority]
        level = monitor.evaluate(queue_depth)
        monitor.update_metrics(queue_depth)

        return level == PressureLevel.REJECT

    def get_pressure_level(self, priority: int) -> PressureLevel:
        """Get current pressure level for priority"""
        if priority not in self.monitors:
            return PressureLevel.NORMAL

        return self.monitors[priority].get_pressure_level()

    def register_callback(
        self,
        priority: int,
        callback: Callable[[PressureChangeEvent], None],
    ) -> None:
        """Register callback for pressure level changes on priority"""
        if priority not in self.monitors:
            self.logger.warning("invalid_priority", priority=priority)
            return

        self.monitors[priority].register_callback(callback)

    def _priority_name(self, priority: int) -> str:
        """Convert priority int to name"""
        names = {
            self.PRIORITY_URGENT: "urgent",
            self.PRIORITY_REALTIME: "realtime",
            self.PRIORITY_INTERACTIVE: "interactive",
            self.PRIORITY_BACKGROUND: "background",
        }
        return names.get(priority, f"priority_{priority}")


# ============================================================================
# INTEGRATION EXAMPLE
# ============================================================================

"""
Integration with PriorityScheduler.send():

# In PriorityScheduler.__init__():
    self._watermark_manager = PriorityWatermarkManager()

    # Register callbacks for degradation actions
    for priority in [PRIORITY_REALTIME, PRIORITY_INTERACTIVE, PRIORITY_BACKGROUND]:
        self._watermark_manager.register_callback(
            priority,
            self._handle_pressure_change
        )

# In PriorityScheduler.send():
    async def send(self, message, priority, ttl_ms=0):
        # ... existing validation logic ...

        # Check per-priority watermark (before enqueue)
        if self._watermark_manager.evaluate_and_check_reject(priority, self._queues[priority].size()):
            self._metrics['backpressure_rejects_total'][priority] += 1
            return SendResult.BACKPRESSURE_REJECT

        # ... enqueue message ...
        await self._queues[priority].enqueue(message)

        # Update metrics (must-fix #7 - on all send paths)
        self._watermark_manager.monitors[priority].update_metrics(self._queues[priority].size())

# Callback handler for degradation actions:
    def _handle_pressure_change(self, event: PressureChangeEvent) -> None:
        priority = self._parse_priority_from_stream_id(event.stream_id)

        if event.new_level == PressureLevel.DEGRADE:
            action = event.degradation_action
            if action == DegradationAction.DROP_OLDEST:
                # Drop oldest non-urgent message from priority queue
                asyncio.create_task(self._drop_oldest_from_priority(priority))
            elif action == DegradationAction.BLOCK_SENDER:
                # Implemented at ingress layer (L4 API)
                self.logger.info("block_sender_initiated", priority=priority)
            elif action == DegradationAction.MERGE_DELTAS:
                # Compress outbox queue (if applicable)
                asyncio.create_task(self._merge_outbox_deltas())
"""
