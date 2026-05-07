"""
k1.concierge.protocols.trust_accumulator -- Trust Accumulator (OPP-4)

Generalized kernel primitive: tracks per-session trust score based on
HITL interaction outcomes. Higher trust = fewer HITL interruptions.

The kernel provides the accumulator; verticals configure:
    - Initial trust level
    - Reward/penalty amounts per outcome
    - Auto-approval threshold
    - Trust decay rate

Trust flows:
    1. User approves HITL request -> trust increases
    2. User rejects/modifies -> trust decreases (learning signal)
    3. User cancels -> moderate trust decrease
    4. HITL timeout -> no trust change (user absence, not distrust)
    5. Successful task completion after auto-approve -> trust increases

The accumulator is consumed by HILCoordinator to:
    - Skip HITL for low-risk actions when trust is high
    - Reduce max_rounds dynamically based on trust
    - Log trust-based decisions for audit
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# =========================================================================
# Trust configuration
# =========================================================================


@dataclass
class TrustConfig:
    """Configuration for trust accumulator behavior.

    All values are generalized defaults. Verticals override via config.

    Attributes:
        initial_trust:        Starting trust score (0.0 - 1.0).
        reward_approve:       Trust increase on user approval.
        penalty_reject:       Trust decrease on rejection.
        penalty_cancel:       Trust decrease on cancellation.
        penalty_modify:       Trust decrease on modification.
        reward_auto_success:  Trust increase on successful auto-approve.
        auto_approve_threshold: Trust level above which low-risk HITL
                                can be auto-approved.
        min_trust:            Floor for trust score.
        max_trust:            Ceiling for trust score.
        decay_per_turn:       Trust decay per turn of inactivity.
    """

    initial_trust: float = 0.5
    reward_approve: float = 0.05
    penalty_reject: float = -0.10
    penalty_cancel: float = -0.07
    penalty_modify: float = -0.03
    reward_auto_success: float = 0.08
    auto_approve_threshold: float = 0.85
    min_trust: float = 0.0
    max_trust: float = 1.0
    decay_per_turn: float = 0.0


# =========================================================================
# Trust event types
# =========================================================================

TRUST_EVENT_APPROVE = "approve"
TRUST_EVENT_REJECT = "reject"
TRUST_EVENT_CANCEL = "cancel"
TRUST_EVENT_MODIFY = "modify"
TRUST_EVENT_AUTO_SUCCESS = "auto_success"
TRUST_EVENT_TIMEOUT = "timeout"


# =========================================================================
# Trust Accumulator
# =========================================================================


@dataclass
class TrustSnapshot:
    """Point-in-time trust state for audit and persistence."""

    trust_score: float
    total_interactions: int
    approvals: int
    rejections: int
    auto_approvals: int
    last_event: str
    last_event_ns: int


class TrustAccumulator:
    """Per-session trust accumulator for dynamic HITL thresholds.

    Generalized kernel primitive. Tracks trust score based on HITL
    interaction outcomes to reduce unnecessary human interruptions
    over time.

    Thread safety: single event loop, no locks needed.
    """

    __slots__ = (
        "_config",
        "_trust",
        "_total_interactions",
        "_approvals",
        "_rejections",
        "_auto_approvals",
        "_last_event",
        "_last_event_ns",
        "_history",
    )

    def __init__(self, config: TrustConfig | None = None) -> None:
        self._config = config or TrustConfig()
        self._trust: float = self._config.initial_trust
        self._total_interactions: int = 0
        self._approvals: int = 0
        self._rejections: int = 0
        self._auto_approvals: int = 0
        self._last_event: str = ""
        self._last_event_ns: int = 0
        self._history: list[tuple[str, float, float]] = []
        logger.info(
            "TrustAccumulator initialised  trust=%.2f auto_threshold=%.2f",
            self._trust,
            self._config.auto_approve_threshold,
        )

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def record_outcome(self, event: str) -> float:
        """Record a HITL interaction outcome and update trust.

        Args:
            event: One of the TRUST_EVENT_* constants.

        Returns:
            The new trust score after the update.
        """
        delta = self._event_delta(event)
        old_trust = self._trust
        self._trust = max(
            self._config.min_trust,
            min(self._config.max_trust, self._trust + delta),
        )

        self._total_interactions += 1
        self._last_event = event
        self._last_event_ns = time.monotonic_ns()
        self._history.append((event, delta, self._trust))

        if event == TRUST_EVENT_APPROVE:
            self._approvals += 1
        elif event in (TRUST_EVENT_REJECT, TRUST_EVENT_CANCEL):
            self._rejections += 1
        elif event == TRUST_EVENT_AUTO_SUCCESS:
            self._auto_approvals += 1

        logger.info(
            "TrustAccumulator: event=%s delta=%.3f trust=%.3f->%.3f",
            event,
            delta,
            old_trust,
            self._trust,
        )
        return self._trust

    def should_auto_approve(self, risk_level: str = "low") -> bool:
        """Check if current trust allows auto-approval.

        Only low-risk HITL requests can be auto-approved. Medium and
        high risk always require human input regardless of trust.

        Args:
            risk_level: "low", "medium", or "high".

        Returns:
            True if trust is above threshold AND risk is low.
        """
        if risk_level != "low":
            return False
        return self._trust >= self._config.auto_approve_threshold

    def get_dynamic_max_rounds(self, base_max_rounds: int = 2) -> int:
        """Compute dynamic max HITL rounds based on trust.

        High trust = fewer rounds needed (user trusts the system).
        Low trust = keep all rounds (user wants control).

        Args:
            base_max_rounds: The static max_rounds from config.

        Returns:
            Adjusted max_rounds (never less than 1).
        """
        if self._trust >= 0.9:
            return max(1, base_max_rounds - 1)
        if self._trust <= 0.2:
            return base_max_rounds + 1
        return base_max_rounds

    @property
    def trust_score(self) -> float:
        """Current trust score."""
        return self._trust

    @property
    def total_interactions(self) -> int:
        """Total HITL interactions recorded."""
        return self._total_interactions

    def snapshot(self) -> TrustSnapshot:
        """Create a point-in-time snapshot for persistence/audit."""
        return TrustSnapshot(
            trust_score=self._trust,
            total_interactions=self._total_interactions,
            approvals=self._approvals,
            rejections=self._rejections,
            auto_approvals=self._auto_approvals,
            last_event=self._last_event,
            last_event_ns=self._last_event_ns,
        )

    def restore(self, snapshot: TrustSnapshot) -> None:
        """Restore from a persisted snapshot (crash recovery)."""
        self._trust = snapshot.trust_score
        self._total_interactions = snapshot.total_interactions
        self._approvals = snapshot.approvals
        self._rejections = snapshot.rejections
        self._auto_approvals = snapshot.auto_approvals
        self._last_event = snapshot.last_event
        self._last_event_ns = snapshot.last_event_ns

    # -----------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------

    def _event_delta(self, event: str) -> float:
        """Map event type to trust delta."""
        deltas = {
            TRUST_EVENT_APPROVE: self._config.reward_approve,
            TRUST_EVENT_REJECT: self._config.penalty_reject,
            TRUST_EVENT_CANCEL: self._config.penalty_cancel,
            TRUST_EVENT_MODIFY: self._config.penalty_modify,
            TRUST_EVENT_AUTO_SUCCESS: self._config.reward_auto_success,
            TRUST_EVENT_TIMEOUT: 0.0,
        }
        return deltas.get(event, 0.0)
