"""
k1.concierge.scheduler.proactive_scheduler -- Proactive Scheduler (OPP-5)

Generalized kernel primitive: decides WHEN to trigger proactive messages
during user idle periods. Separates scheduling logic from content generation.

Architecture:
    ProactiveScheduler (WHEN to trigger)
        -> ProactiveAgent (WHAT to say)
        -> Bus topic PROACTIVE_FILL (HOW to deliver)
        -> FSM routes to Front

The kernel provides the scheduler; verticals configure:
    - Trigger rules (idle thresholds, context conditions)
    - Cooldown periods between proactive messages
    - Suppression conditions (affect band, active HITL, etc.)
    - Maximum proactive messages per session

Scheduling model:
    1. Idle timer fires (configurable, default 5s)
    2. Scheduler checks suppression conditions
    3. If allowed, selects trigger type based on context
    4. Emits proactive trigger event
    5. Cooldown timer starts (prevents spam)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ProactiveTriggerType(str, Enum):
    """Types of proactive messages the scheduler can trigger."""

    WAIT_STATUS = "wait_status"
    PROGRESS_UPDATE = "progress_update"
    CONTEXT_TIP = "context_tip"
    IDLE_CHECK_IN = "idle_check_in"


@dataclass
class ProactiveSchedulerConfig:
    """Configuration for proactive scheduling behavior.

    Attributes:
        idle_threshold_ms:   Minimum idle time before first trigger.
        cooldown_ms:         Minimum time between proactive messages.
        max_per_session:     Maximum proactive messages per session.
        suppress_on_affect:  Affect bands that suppress proactive messages.
        suppress_on_hitl:    Whether to suppress during pending HITL.
        enabled:             Master switch for proactive scheduling.
    """

    idle_threshold_ms: int = 5000
    cooldown_ms: int = 15000
    max_per_session: int = 10
    suppress_on_affect: list[str] | None = None
    suppress_on_hitl: bool = True
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.suppress_on_affect is None:
            self.suppress_on_affect = ["crisis", "low"]


@dataclass
class ProactiveTrigger:
    """A scheduled proactive trigger ready for execution."""

    trigger_type: ProactiveTriggerType
    reason: str
    context: dict[str, str]
    scheduled_at_ns: int


class ProactiveScheduler:
    """Decides when to fire proactive messages during idle periods.

    Generalized kernel primitive. The scheduler evaluates context and
    decides IF and WHAT TYPE of proactive message should fire.
    Content generation is delegated to ProactiveAgent.

    Thread safety: single event loop, no locks needed.
    """

    __slots__ = (
        "_config",
        "_trigger_count",
        "_last_trigger_ns",
        "_suppressed_count",
        "_session_start_ns",
    )

    def __init__(self, config: ProactiveSchedulerConfig | None = None) -> None:
        self._config = config or ProactiveSchedulerConfig()
        self._trigger_count: int = 0
        self._last_trigger_ns: int = 0
        self._suppressed_count: int = 0
        self._session_start_ns: int = time.monotonic_ns()
        logger.info(
            "ProactiveScheduler initialised  idle=%dms cooldown=%dms max=%d",
            self._config.idle_threshold_ms,
            self._config.cooldown_ms,
            self._config.max_per_session,
        )

    def evaluate(
        self,
        idle_ms: int,
        affect_band: str = "neutral",
        has_pending_hitl: bool = False,
        has_inflight_tasks: bool = False,
        inflight_task_count: int = 0,
    ) -> ProactiveTrigger | None:
        """Evaluate whether a proactive message should fire now.

        Called by the experience layer tick or FSM idle handler.

        Args:
            idle_ms:             Current user idle duration in ms.
            affect_band:         Current affect band string.
            has_pending_hitl:    Whether any HITL is pending user response.
            has_inflight_tasks:  Whether there are active background tasks.
            inflight_task_count: Number of inflight tasks.

        Returns:
            ProactiveTrigger if conditions are met, None otherwise.
        """
        if not self._config.enabled:
            return None

        # Suppression checks
        if self._trigger_count >= self._config.max_per_session:
            return None

        if idle_ms < self._config.idle_threshold_ms:
            return None

        if self._config.suppress_on_hitl and has_pending_hitl:
            self._suppressed_count += 1
            return None

        if affect_band in (self._config.suppress_on_affect or []):
            self._suppressed_count += 1
            return None

        # Cooldown check
        now_ns = time.monotonic_ns()
        if self._last_trigger_ns > 0:
            elapsed_ms = (now_ns - self._last_trigger_ns) / 1_000_000
            if elapsed_ms < self._config.cooldown_ms:
                return None

        # Select trigger type based on context
        trigger_type, reason = self._select_trigger_type(
            idle_ms=idle_ms,
            has_inflight=has_inflight_tasks,
            inflight_count=inflight_task_count,
        )

        trigger = ProactiveTrigger(
            trigger_type=trigger_type,
            reason=reason,
            context={
                "idle_ms": str(idle_ms),
                "affect_band": affect_band,
                "inflight_count": str(inflight_task_count),
            },
            scheduled_at_ns=now_ns,
        )

        self._trigger_count += 1
        self._last_trigger_ns = now_ns

        logger.info(
            "ProactiveScheduler: trigger %s (reason=%s, count=%d)",
            trigger_type.value,
            reason,
            self._trigger_count,
        )
        return trigger

    @property
    def trigger_count(self) -> int:
        """Total proactive triggers fired this session."""
        return self._trigger_count

    @property
    def suppressed_count(self) -> int:
        """Total triggers suppressed by conditions."""
        return self._suppressed_count

    def reset(self) -> None:
        """Reset scheduler state (e.g. on session restart)."""
        self._trigger_count = 0
        self._last_trigger_ns = 0
        self._suppressed_count = 0
        self._session_start_ns = time.monotonic_ns()

    # -----------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------

    def _select_trigger_type(
        self,
        idle_ms: int,
        has_inflight: bool,
        inflight_count: int,
    ) -> tuple[ProactiveTriggerType, str]:
        """Select the most appropriate trigger type."""
        if has_inflight and inflight_count > 0:
            if idle_ms > 15000:
                return ProactiveTriggerType.PROGRESS_UPDATE, "long_wait_with_tasks"
            return ProactiveTriggerType.WAIT_STATUS, "waiting_for_tasks"

        if idle_ms > 30000:
            return ProactiveTriggerType.IDLE_CHECK_IN, "extended_idle"

        return ProactiveTriggerType.CONTEXT_TIP, "moderate_idle"
