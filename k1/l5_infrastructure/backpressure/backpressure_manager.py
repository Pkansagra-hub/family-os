"""
Backpressure Manager - 3-Tier Cascading Backpressure with Privacy Overrides

Layer: L5 Infrastructure
Component: Backpressure Coordination
Priority: 🔴 CRITICAL (Prevents system overload, ensures graceful degradation)
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

Architecture Decision Records:
    - ADR-0039a: Tier Triggers & Watermark Thresholds (3-tier cascade, hysteresis)
    - ADR-0039b: Backpressure Propagation & Signal Flow (event-based coordination)
    - ADR-0039c: Recovery & Gradual Resume (stepwise descent, rate limiting)
    - ADR-0002a: Mailbox Backpressure (actor-level watermarks)

Backpressure Philosophy:
    - Graceful degradation: Progressively shed load to prevent collapse
    - Privacy-aware: RED band bypasses soft/hard (medical/financial priority)
    - Hysteresis stability: 10% buffer prevents oscillation (tier flapping)
    - Stepwise recovery: Gradual resume to avoid thundering herd

3-Tier Cascade Architecture:
    Tier 1: Reject New Turns (Soft Protection)
        - Queue depth >50 turns OR E2E latency >2500ms OR Active turns >80
        - Action: Return HTTP 503 to new turn requests (active turns continue)
        - Recovery: Queue <45 turns AND E2E <2250ms AND Active <72 (10s sustained)

    Tier 2: Cancel Background Tasks (Medium Protection)
        - Queue depth >100 turns OR Memory >450MB OR CPU >85%
        - Action: Cancel learning loops, analytics, non-interactive sessions
        - Recovery: Queue <90 turns AND Memory <405MB AND CPU <77% (10s sustained)

    Tier 3: Emergency Throttle (Hard Protection)
        - Queue depth >200 turns OR Memory >480MB OR Thermal CRITICAL (3+)
        - Action: Throttle ALL processing, force GC, evict caches, timeout tools at 1s
        - Recovery: Queue <180 turns AND Memory <432MB AND Thermal WARM (1) (30s sustained)

Privacy Band Overrides (from planning doc):
    RED-Band (Highly Sensitive - Medical/Financial):
      - Bypass soft watermarks (75%)
      - Can use hard watermark (85%)
      - Cannot bypass critical (95%)
      - Rationale: Sensitive data = high-priority processing

    AMBER-Band (Sensitive - User Preferences):
      - Standard watermark enforcement
      - Can go to 85% but not 95%

    GREEN-Band (Non-Sensitive - Public Data):
      - Strict enforcement
      - Cannot exceed 85%
      - Rationale: Non-essential traffic limited first

Watermark Thresholds (with 10% hysteresis):
    Soft Watermark: 75% queue depth (reduce non-priority)
    Hard Watermark: 85% queue depth (reject non-priority)
    Critical Watermark: 95% queue depth (emergency mode)

Dependencies:
    Internal:
        - k1.l5_infrastructure.backpressure.watermark_tracker (Watermark tracking)
        - k1.telemetry.metrics (Prometheus metrics)
        - k1.l2_orchestration.orchestrator (Turn rejection)
    External:
        - None (pure Python)

Connects To:
    Upstream:
        - k1.l5_infrastructure.backpressure.watermark_tracker (Receives watermark breaches)
        - k1.telemetry.metrics_collector (Receives queue depth, memory, CPU, thermal)
    Downstream:
        - k1.api.gateway (HTTP 503 rejection)
        - k1.l2_orchestration.orchestrator (Cancel background tasks)
        - k1.l3_execution.agent_fabric (Drain idle agents)

Performance Budgets:
    - update_queue_depth(): <10ms P95 (decision latency)
    - should_accept_request(): <5ms P95 (admission check)
    - get_backpressure_action(): <5ms P95 (action selection)
    - get_backpressure_status(): <20ms P95 (status query)

Observability:
    - Metrics: k1_backpressure_tier (gauge: 0=NORMAL, 1=TIER_1, 2=TIER_2, 3=TIER_3)
    - Metrics: k1_backpressure_transitions_total{from_tier, to_tier} (counter)
    - Metrics: k1_turns_rejected_backpressure_total (counter)
    - Metrics: k1_queue_depth_messages (gauge)
    - Traces: Span backpressure_manager.update_queue_depth
    - Logs: WARNING tier transitions, INFO queue depth updates

References:
    - Whiteboard: docs/whiteboard.md (Section: Backpressure Coordination)
    - Planning: docs/planning/stub_generation_plan_layer5.md (Milestone 8, Epic 8.1)
    - Test: tests/k1/l5_infrastructure/backpressure/test_backpressure_manager.py
"""

import logging
from dataclasses import dataclass
from enum import Enum

# =============================================================================
# SECTION 1: IMPORTS
# =============================================================================
from typing import Any, Callable, Dict, Optional, Tuple

# Internal imports
# TODO(@resilience-team): Import from existing modules (Issue #L5-8.1.1)
# from k1.l5_infrastructure.backpressure.watermark_tracker import WatermarkTracker
# from k1.telemetry.metrics import (
#     k1_backpressure_tier,
#     k1_backpressure_transitions_total,
#     k1_turns_rejected_backpressure_total,
#     k1_queue_depth_messages,
# )

logger = logging.getLogger(__name__)

# =============================================================================
# SECTION 2: CONSTANTS & CONFIGURATION
# =============================================================================

# Watermark thresholds (default, configurable via YAML)
DEFAULT_SOFT_THRESHOLD_PCT = 0.75  # 75% queue depth
DEFAULT_HARD_THRESHOLD_PCT = 0.85  # 85% queue depth
DEFAULT_CRITICAL_THRESHOLD_PCT = 0.95  # 95% queue depth

# Hysteresis buffer (prevents oscillation)
HYSTERESIS_BUFFER_PCT = 0.10  # 10% gap between activation and deactivation

# Tier thresholds (from ADR-0039a)
TIER_1_THRESHOLDS = {
    "activation": {
        "queue_depth": 50,  # turns
        "e2e_latency_p95_ms": 2500,  # milliseconds
        "active_turns": 80,  # concurrent turns
        "sustained_seconds": 5,  # must be sustained
    },
    "deactivation": {
        "queue_depth": 45,  # 10% hysteresis
        "e2e_latency_p95_ms": 2250,  # 10% hysteresis
        "active_turns": 72,  # 10% hysteresis
        "sustained_seconds": 10,  # longer for deactivation
    },
}

TIER_2_THRESHOLDS = {
    "activation": {
        "queue_depth": 100,  # turns
        "k1_memory_mb": 450,  # 90% of 500MB budget
        "cpu_utilization_percent": 85,  # near saturation
        "sustained_seconds": 5,
    },
    "deactivation": {
        "queue_depth": 90,  # 10% hysteresis
        "k1_memory_mb": 405,  # 10% hysteresis
        "cpu_utilization_percent": 77,  # 10% hysteresis
        "sustained_seconds": 10,
    },
}

TIER_3_THRESHOLDS = {
    "activation": {
        "queue_depth": 200,  # turns
        "k1_memory_mb": 480,  # 96% of 500MB budget (OOM imminent)
        "thermal_state": 3,  # CRITICAL or higher
        "sustained_seconds": 3,  # shorter duration (urgency)
    },
    "deactivation": {
        "queue_depth": 180,  # 10% hysteresis
        "k1_memory_mb": 432,  # 10% hysteresis
        "thermal_state": 1,  # WARM or lower
        "sustained_seconds": 30,  # longer for stability
        "no_oom_seconds": 60,  # no OOM events for 60s
    },
}

# Privacy band override rules (from planning doc Milestone 8)
PRIVACY_OVERRIDE_RULES = {
    "red": {
        "bypass_soft": True,  # Can exceed 75%
        "bypass_hard": True,  # Can exceed 85%
        "bypass_critical": False,  # Cannot exceed 95%
        "priority_boost": 10,  # Priority points
    },
    "amber": {
        "bypass_soft": False,  # Standard enforcement
        "bypass_hard": False,  # Can reach 85% but not exceed
        "bypass_critical": False,  # Cannot exceed 85%
        "priority_boost": 0,
    },
    "green": {
        "bypass_soft": False,  # Strict enforcement
        "bypass_hard": False,  # Cannot exceed 85%
        "bypass_critical": False,  # Cannot exceed 85%
        "priority_boost": -10,  # Lower priority
    },
}

# =============================================================================
# SECTION 3: TYPE DEFINITIONS & ENUMS
# =============================================================================


class BackpressureTier(Enum):
    """Backpressure tiers with increasing severity."""

    NORMAL = 0  # No backpressure
    TIER_1_REJECT_NEW = 1  # Reject new turns
    TIER_2_CANCEL_BG = 2  # Cancel background tasks
    TIER_3_EMERGENCY = 3  # Emergency throttle


class BackpressureAction(Enum):
    """Backpressure actions to take at each tier."""

    NONE = "none"
    SLOW_DOWN = "slow_down"  # Soft watermark: reduce non-priority
    REDUCE_BATCH = "reduce_batch"  # Hard watermark: reduce batch sizes
    DOWNGRADE = "downgrade"  # Critical watermark: downgrade tier or reject


@dataclass
class QueueDepthSnapshot:
    """
    Queue depth snapshot for backpressure evaluation.

    Fields:
        layer: Layer name (app, cache, breaker)
        current_depth: Current queue items
        max_depth: Maximum capacity
        depth_pct: Depth as percentage
        timestamp: When snapshot taken
    """

    layer: str
    current_depth: int
    max_depth: int
    depth_pct: float
    timestamp: float


@dataclass
class BackpressureDecision:
    """
    Backpressure decision result.

    Fields:
        tier: Current backpressure tier
        action: Action to take
        depth_pct: Queue depth percentage
        override_applied: Privacy override in effect
        reason: Reason for decision
        reduction_pct: Rate reduction percentage
    """

    tier: BackpressureTier
    action: BackpressureAction
    depth_pct: float
    override_applied: bool
    reason: str
    reduction_pct: float


# =============================================================================
# SECTION 4: BACKPRESSURE MANAGER
# =============================================================================


class BackpressureManager:
    """
    Cascading backpressure manager with privacy-aware overrides.

    Responsibilities:
        - Track queue depths across layers (app, cache, breaker)
        - Calculate watermark percentages (soft/hard/critical)
        - Trigger backpressure actions at thresholds
        - Coordinate with placement engine (reduce tier)
        - Report backpressure metrics
        - Enforce privacy-aware overrides (RED bypasses soft/hard)

    3-Tier Cascade (from ADR-0039a):
        1. App Level (75% soft): Slow down non-priority
        2. Cache Level (85% hard): Reduce batch/increase TTL
        3. Circuit Breaker (95% critical): Downgrade/reject

    Privacy Handling (from planning doc):
        - RED: High-priority, can exceed soft/hard (not critical)
        - AMBER: Standard enforcement
        - GREEN: Strict, cannot exceed hard

    Thread Safety: Yes (uses locks for state updates)
    Async Safe: Yes

    Cognitive Trace:
        - Accepts cognitive_trace_id from caller
        - Includes in all logs and metrics

    Performance Budget (P95):
        - update_queue_depth(): <10ms (decision time)
        - should_accept_request(): <5ms (admission check)
        - get_backpressure_action(): <5ms (action selection)
        - get_backpressure_status(): <20ms (status query)

    Examples:
        >>> manager = BackpressureManager(
        ...     soft_threshold_pct=0.75,
        ...     hard_threshold_pct=0.85,
        ...     critical_threshold_pct=0.95
        ... )
        >>> decision = manager.update_queue_depth(
        ...     layer='app',
        ...     current_depth=60,
        ...     max_depth=100,
        ...     cognitive_trace_id='trace_123'
        ... )
        >>> print(decision)
        BackpressureDecision(tier=NORMAL, action=NONE, depth_pct=0.60, ...)

    References:
        - ADR-0039a: Tier Triggers & Watermark Thresholds
        - ADR-0039b: Backpressure Propagation & Signal Flow
        - ADR-0039c: Recovery & Gradual Resume
    """

    def __init__(
        self,
        soft_threshold_pct: float = DEFAULT_SOFT_THRESHOLD_PCT,
        hard_threshold_pct: float = DEFAULT_HARD_THRESHOLD_PCT,
        critical_threshold_pct: float = DEFAULT_CRITICAL_THRESHOLD_PCT,
        cascade_action: Optional[Callable] = None,
    ):
        """
        Initialize backpressure manager.

        Args:
            soft_threshold_pct: Soft watermark (default: 75%)
            hard_threshold_pct: Hard watermark (default: 85%)
            critical_threshold_pct: Critical watermark (default: 95%)
            cascade_action: Callback for cascade triggers

        Side Effects:
            - Initializes queue depth tracking
            - Registers cascade callback
            - Initializes watermark thresholds

        ADR: ADR-0039a (Watermark Initialization)
        Assigned to: Issue #L5-8.1.1
        """
        # TODO(@resilience-team): Implement initialization
        # 1. Store watermark thresholds
        # 2. Initialize queue depth tracking dict (layer -> QueueDepthSnapshot)
        # 3. Initialize current tier (NORMAL)
        # 4. Store cascade_action callback
        # 5. Initialize sustained condition tracking (activation/deactivation timers)
        # 6. Initialize privacy override rules
        # 7. Initialize metrics (tier gauge, transitions counter)
        self._logger = logger
        self._soft_threshold_pct = soft_threshold_pct
        self._hard_threshold_pct = hard_threshold_pct
        self._critical_threshold_pct = critical_threshold_pct
        self._cascade_action = cascade_action
        pass

    def update_queue_depth(
        self,
        layer: str,  # "app", "cache", "breaker"
        current_depth: int,
        max_depth: int,
        cognitive_trace_id: Optional[str] = None,
    ) -> BackpressureDecision:
        """
        Update queue depth and evaluate backpressure.

        Args:
            layer: Layer name (app, cache, breaker)
            current_depth: Current queue items
            max_depth: Maximum capacity
            cognitive_trace_id: Trace ID

        Returns:
            BackpressureDecision with:
                - tier: Current watermark tier (normal/soft/hard/critical)
                - action: Action to take (None/slow_down/reduce_batch/downgrade)
                - depth_pct: Current depth as %
                - override_applied: Privacy override in effect
                - reason: Reason for decision
                - reduction_pct: Rate reduction percentage

        Flow:
            1. Calculate depth percentage
            2. Check watermark thresholds
            3. Apply privacy override if needed
            4. Trigger cascade if threshold breached
            5. Return decision

        Performance:
            - Decision time: <10ms P95

        ADR: ADR-0039a (Queue Depth Evaluation)
        Assigned to: Issue #L5-8.1.1
        """
        # TODO(@resilience-team): Implement queue depth tracking
        # 1. Store depth snapshot (QueueDepthSnapshot)
        # 2. Calculate depth_pct = current_depth / max_depth
        # 3. Check watermark thresholds (soft/hard/critical)
        # 4. Evaluate tier based on thresholds (TIER_1/TIER_2/TIER_3)
        # 5. Check sustained duration (activation/deactivation timers)
        # 6. Apply privacy overrides if needed
        # 7. Trigger cascade_action if tier changed
        # 8. Emit metrics (queue depth gauge, tier gauge)
        # 9. Log: INFO queue depth update, WARNING tier change
        # 10. Return BackpressureDecision
        pass

    async def should_accept_request(
        self,
        request_type: str,  # "priority", "normal", "batch"
        privacy_band: str,  # "red", "amber", "green"
        current_depth_pct: float,
    ) -> Tuple[bool, Optional[str]]:
        """
        Determine if should accept new request based on backpressure.

        Args:
            request_type: Type of request (priority, normal, batch)
            privacy_band: Privacy classification (red, amber, green)
            current_depth_pct: Current queue depth %

        Returns:
            (accept: bool, reason: optional explanation)

        Rules:
            Priority requests:
              - Accept until hard threshold (85%)
            Normal requests:
              - Accept until soft threshold (75%)
            Batch requests:
              - Accept until soft threshold (75%)

        Privacy Overrides (from planning doc):
            RED: Can bypass soft (75%), not hard/critical (85%/95%)
            AMBER: Standard enforcement
            GREEN: Strict, cannot exceed hard (85%)

        Examples:
            >>> accept, reason = await manager.should_accept_request(
            ...     request_type='normal',
            ...     privacy_band='green',
            ...     current_depth_pct=0.80
            ... )
            >>> print(accept, reason)
            False, 'queue depth 80% exceeds soft watermark (75%) for GREEN band'

        ADR: ADR-0039a (Admission Control)
        Assigned to: Issue #L5-8.1.1
        """
        # TODO(@resilience-team): Implement request acceptance logic
        # 1. Get current tier (NORMAL/TIER_1/TIER_2/TIER_3)
        # 2. Check privacy override rules:
        #    - RED: bypass_soft=True, bypass_hard=True (can exceed 75%/85%)
        #    - AMBER: standard enforcement
        #    - GREEN: strict enforcement (cannot exceed 85%)
        # 3. Check request_type priority:
        #    - priority: accept until hard (85%)
        #    - normal: accept until soft (75%)
        #    - batch: accept until soft (75%)
        # 4. Combine tier + privacy + request_type:
        #    - TIER_3 (95%): Reject ALL (except RED priority)
        #    - TIER_2 (85%): Reject normal/batch, accept priority
        #    - TIER_1 (75%): Reject batch, slow normal, accept priority
        #    - NORMAL (<75%): Accept ALL
        # 5. Return (accept=True/False, reason=string)
        pass

    def get_backpressure_action(
        self,
        current_tier: BackpressureTier,  # "soft", "hard", "critical"
    ) -> Dict[str, Any]:
        """
        Get recommended backpressure action for tier.

        Args:
            current_tier: Watermark tier (TIER_1/TIER_2/TIER_3)

        Returns:
            Dict with recommended action:
                tier=TIER_1: {"action": "slow_down", "reduction_pct": 10}
                tier=TIER_2: {"action": "reduce_batch", "reduction_pct": 20}
                tier=TIER_3: {"action": "downgrade_tier", "reduction_pct": 30}

        Cascade Actions (from ADR-0039b):
            TIER_1: Reject new turns (HTTP 503)
            TIER_2: Cancel background tasks (learning loops, analytics)
            TIER_3: Emergency throttle (all work, force GC, evict caches)

        ADR: ADR-0039b (Action Selection)
        Assigned to: Issue #L5-8.1.1
        """
        # TODO(@resilience-team): Implement action selection
        # 1. Map tier to action:
        #    - NORMAL: {"action": "none", "reduction_pct": 0}
        #    - TIER_1: {"action": "slow_down", "reduction_pct": 10}
        #    - TIER_2: {"action": "reduce_batch", "reduction_pct": 20}
        #    - TIER_3: {"action": "downgrade", "reduction_pct": 30}
        # 2. Return action dict
        pass

    def get_backpressure_status(self) -> Dict[str, Any]:
        """
        Get current backpressure status.

        Returns:
            Dict with:
                - app_queue_pct: App queue depth %
                - cache_queue_pct: Cache queue depth %
                - breaker_queue_pct: Circuit breaker queue depth %
                - active_tier: Current highest watermark breached
                - active_actions: Current mitigation actions
                - request_rate_reduction_pct: Current rate limit reduction
                - privacy_overrides_active: Active privacy overrides

        Performance:
            - Status query: <20ms P95

        ADR: ADR-0039a (Status Query)
        Assigned to: Issue #L5-8.1.1
        """
        # TODO(@resilience-team): Implement status collection
        # 1. Get queue depth snapshots for all layers (app, cache, breaker)
        # 2. Get current tier (NORMAL/TIER_1/TIER_2/TIER_3)
        # 3. Get active actions for current tier
        # 4. Calculate aggregate rate reduction %
        # 5. Check privacy overrides active (RED/AMBER/GREEN)
        # 6. Build status dict
        # 7. Return status
        pass

    def apply_privacy_override(
        self,
        privacy_band: str,
        base_threshold_pct: float,
    ) -> float:
        """
        Apply privacy band override to watermark threshold.

        Args:
            privacy_band: Privacy classification (red/amber/green)
            base_threshold_pct: Base watermark threshold (0.75/0.85/0.95)

        Returns:
            Adjusted threshold percentage

        Privacy Override Rules (from planning doc Milestone 8):
            RED: Can bypass soft (75%), hard (85%), NOT critical (95%)
            AMBER: Standard enforcement (no bypass)
            GREEN: Strict enforcement (cannot exceed 85%)

        Examples:
            >>> adjusted = manager.apply_privacy_override('red', 0.75)
            >>> print(adjusted)
            1.0  # RED can exceed soft watermark

            >>> adjusted = manager.apply_privacy_override('green', 0.85)
            >>> print(adjusted)
            0.85  # GREEN strict enforcement

        ADR: Milestone 8 Planning (Privacy Override Logic)
        Assigned to: Issue #L5-8.1.1
        """
        # TODO(@resilience-team): Implement privacy override
        # 1. Get override rules for privacy_band (red/amber/green)
        # 2. Check if base_threshold_pct is soft (75%), hard (85%), or critical (95%)
        # 3. Apply override:
        #    - RED: bypass_soft=True → 1.0, bypass_hard=True → 1.0, bypass_critical=False → 0.95
        #    - AMBER: standard (no override) → base_threshold_pct
        #    - GREEN: strict (cannot exceed 85%) → min(base_threshold_pct, 0.85)
        # 4. Return adjusted threshold
        pass

    def reset_backpressure(self):
        """
        Reset backpressure manager to NORMAL state.

        Side Effects:
            - Clears all queue depth snapshots
            - Resets tier to NORMAL
            - Clears sustained condition timers
            - Emits metric (tier gauge = 0)

        Use Case:
            - System startup
            - Emergency recovery
            - Testing

        ADR: ADR-0039c (Recovery Reset)
        Assigned to: Issue #L5-8.1.1
        """
        # TODO(@resilience-team): Implement reset
        # 1. Clear queue depth snapshots
        # 2. Set tier to NORMAL
        # 3. Clear sustained timers (activation/deactivation)
        # 4. Emit metric: k1_backpressure_tier.set(0)
        # 5. Log: INFO backpressure reset
        pass


# =============================================================================
# SECTION 5: MODULE EXPORTS
# =============================================================================

__all__ = [
    "BackpressureManager",
    "BackpressureTier",
    "BackpressureAction",
    "BackpressureDecision",
    "QueueDepthSnapshot",
]


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================
# Prometheus Metrics Exported:
#
# Backpressure Tier:
#   - k1_backpressure_tier (gauge: 0=NORMAL, 1=TIER_1, 2=TIER_2, 3=TIER_3)
#
# Tier Transitions:
#   - k1_backpressure_transitions_total{from_tier, to_tier} (counter)
#
# Turn Rejections:
#   - k1_turns_rejected_backpressure_total (counter)
#
# Queue Depth:
#   - k1_queue_depth_messages{layer} (gauge)
#
# Privacy Overrides:
#   - k1_backpressure_privacy_overrides_total{privacy_band, threshold} (counter)
#
# Cascade Actions:
#   - k1_backpressure_actions_total{tier, action} (counter)
#
# =============================================================================

# =============================================================================
# TESTING REQUIREMENTS (WARD Framework)
# =============================================================================
# Integration tests required:
#   - tests/k1/l5_infrastructure/backpressure/test_backpressure_manager.py
#   - Test tier transitions (NORMAL → TIER_1 → TIER_2 → TIER_3)
#   - Test hysteresis (oscillation prevention)
#   - Test privacy overrides (RED bypasses soft/hard, GREEN strict)
#   - Test request acceptance (priority/normal/batch with privacy bands)
#   - Test cascade actions (slow_down, reduce_batch, downgrade)
#   - Test sustained condition enforcement (5s/10s/30s)
#   - Test recovery (gradual descent TIER_3 → TIER_2 → TIER_1 → NORMAL)
#
# No simulation code allowed:
#   - Use real queue implementations
#   - Use ward fixtures for queue mocks
#   - Integration tests > unit tests
#
# =============================================================================
