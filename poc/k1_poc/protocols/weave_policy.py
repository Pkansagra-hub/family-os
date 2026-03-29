"""
poc.k1_poc.protocols.weave_policy -- Adaptive Weave Signal Collector.

M8 E8.1: Collects the 6 signal categories that feed the adaptive weave
decision engine (E8.2).  The static get_weave_action(ConciergeState) in
weave_state.py reads ONLY the FSM state.  This module collects urgency,
user typing, idle duration, pending count profile, affect band, and
BackPool utilization into a single WeaveSignal snapshot that the policy
engine uses to make context-aware decisions.

Issues covered:
    8.1.1 -- WeaveSignal dataclass with from_runtime() factory
    8.1.2 -- UserActivityTracker (typing start/stop)
    8.1.3 -- Idle duration tracker with threshold constants
    8.1.4 -- Pending urgency profiler (urgency flow from dispatch)
    8.1.5 -- Affect-based weave gating (emotional_gate field)

Signal sources:
    - FSM state: ConciergeState enum
    - Turn state: FSMTurnState.pending_results deque
    - BackPool: get_pool_state() for utilization
    - SessionState: affective_now section for affect/valence
    - UserActivityTracker: typing status + idle duration
    - HITL: pending sub-task status from controller
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from poc.k1_poc.fsm.states import ConciergeState

logger = logging.getLogger(__name__)


# =====================================================================
# 8.1.3 -- Idle duration threshold constants
# =====================================================================

# User idle 10+ seconds: eager delivery (shorter batch window).
IDLE_EAGER_MS: int = 10_000

# User active within 3s: mid-conversation, extend batch window.
IDLE_BATCH_MS: int = 3_000

# Typing detected within 500ms: suppress non-urgent delivery.
TYPING_SUPPRESS_MS: int = 500


# =====================================================================
# 8.1.5 -- Emotional gate values
# =====================================================================

EMOTIONAL_GATE_OPEN: str = "open"
EMOTIONAL_GATE_SUPPRESS_TRIVIAL: str = "suppress_trivial"
EMOTIONAL_GATE_SUPPRESS_ALL_NON_SAFETY: str = "suppress_all_non_safety"

# Valence threshold below which trivial results are suppressed.
EMOTIONAL_SUPPRESS_VALENCE: float = -0.5


# =====================================================================
# 8.1.2 -- UserActivityTracker
# =====================================================================


class UserActivityTracker:
    """Tracks user typing status and idle duration for weave policy.

    M8 E8.1.2: User typing status comes from the UI layer via
    k1.ui.typing.v1 (RELAXED delivery, best-effort).  If no UI typing
    signal is available (headless mode, API-only), defaults to
    user_typing=False and user_idle_ms=time_since_last_user_input.

    M8 E8.1.3: Maintains last_user_input_ns for idle duration
    calculation.  user_idle_ms = (now_ns - last_user_input_ns) / 1e6.

    All state is in-memory only -- typing events do NOT go to the
    ledger (high-frequency, low-value).
    """

    __slots__ = (
        "_typing",
        "_last_typing_ns",
        "_last_user_input_ns",
        "_last_typing_start_ns",
    )

    def __init__(self) -> None:
        self._typing: bool = False
        self._last_typing_ns: int = 0
        self._last_user_input_ns: int = time.monotonic_ns()
        self._last_typing_start_ns: int = 0

    # -----------------------------------------------------------------
    # Signal inputs
    # -----------------------------------------------------------------

    def on_typing_start(self) -> None:
        """UI reports user started typing.

        M8 E8.1.2: Sets user_typing=True and records timestamp.
        """
        now = time.monotonic_ns()
        self._typing = True
        self._last_typing_ns = now
        self._last_typing_start_ns = now
        logger.debug("UserActivityTracker: typing_start at %d", now)

    def on_typing_stop(self) -> None:
        """UI reports user stopped typing.

        M8 E8.1.2: Sets user_typing=False.  The idle timer resumes
        from now (not from last_user_input_ns).
        """
        now = time.monotonic_ns()
        self._typing = False
        self._last_typing_ns = now
        logger.debug("UserActivityTracker: typing_stop at %d", now)

    def on_user_input(self) -> None:
        """User sent a message.

        M8 E8.1.3: Resets idle timer and clears typing status
        (message sent implies typing stopped).
        """
        now = time.monotonic_ns()
        self._typing = False
        self._last_user_input_ns = now
        self._last_typing_ns = now
        logger.debug("UserActivityTracker: user_input at %d", now)

    def on_user_idle_tick(self) -> None:
        """Periodic tick to update idle duration.

        M8 E8.1.3: Called by the FSM on a timer (e.g. every 1s).
        Currently a no-op since idle_ms is calculated on read.
        """

    # -----------------------------------------------------------------
    # Signal outputs (read by WeaveSignal.from_runtime)
    # -----------------------------------------------------------------

    @property
    def is_typing(self) -> bool:
        """Whether the user is currently typing.

        M8 E8.1.2: If no UI typing signal has been received,
        defaults to False (headless mode).
        """
        return self._typing

    @property
    def idle_ms(self) -> int:
        """Milliseconds since last user input.

        M8 E8.1.3: user_idle_ms = (now_ns - last_user_input_ns) / 1e6.
        """
        now_ns = time.monotonic_ns()
        elapsed_ns = now_ns - self._last_user_input_ns
        return max(0, int(elapsed_ns / 1_000_000))

    @property
    def last_user_input_ns(self) -> int:
        """Monotonic timestamp of last user input."""
        return self._last_user_input_ns

    @property
    def typing_duration_ms(self) -> int:
        """How long the user has been typing (0 if not typing)."""
        if not self._typing:
            return 0
        elapsed_ns = time.monotonic_ns() - self._last_typing_start_ns
        return max(0, int(elapsed_ns / 1_000_000))


# =====================================================================
# 8.1.4 -- Pending urgency profiler helpers
# =====================================================================


def _profile_urgency(
    pending: list[dict[str, Any]] | Any,
) -> dict[str, int]:
    """Count pending results by urgency level.

    M8 E8.1.4: Reads the 'urgency' field from each queued result dict.
    If no urgency field exists (pre-M8 results), defaults to "normal".

    Args:
        pending: Iterable of result dicts (from FSMTurnState.pending_results).

    Returns:
        Dict mapping urgency level to count, e.g.
        {"critical": 1, "normal": 2, "low": 0}.
    """
    profile: dict[str, int] = {"critical": 0, "normal": 0, "low": 0}
    for item in pending:
        urgency = "normal"
        if isinstance(item, dict):
            urgency = item.get("urgency", "normal")
        profile[urgency] = profile.get(urgency, 0) + 1
    return profile


def _has_critical(pending: list[dict[str, Any]] | Any) -> bool:
    """Check if any pending result has critical or urgent urgency.

    M8 E8.1.4: If ANY result has urgency "critical" or "urgent",
    returns True.  This signal overrides many policy rules.

    Args:
        pending: Iterable of result dicts.

    Returns:
        True if any result is critical/urgent.
    """
    for item in pending:
        if isinstance(item, dict):
            urgency = item.get("urgency", "normal")
            if urgency in ("critical", "urgent"):
                return True
    return False


# =====================================================================
# 8.1.5 -- Affect-based weave gating helpers
# =====================================================================


def _get_affect_dict_from_ss(ss: Any) -> dict[str, Any]:
    """Read affective_now section from SessionState.

    M8 E8.1.5: Uses the same path as Front: _get_affect_dict in
    actors/front.py L330-336.  Extracted here to avoid circular
    imports between protocols and actors.

    Args:
        ss: SessionState instance (or None).

    Returns:
        Dict with valence, arousal, current_emotion, safety_band etc.
        Empty dict if ss is None or section missing.
    """
    if ss is None:
        return {}
    section = None
    if hasattr(ss, "get_section"):
        section = ss.get_section("affective_now")
    elif hasattr(ss, "sections"):
        section = ss.sections.get("affective_now")
    if section is None:
        return {}
    if hasattr(section, "to_dict"):
        return section.to_dict()
    if isinstance(section, dict):
        return section
    return {}


def _compute_emotional_gate(affect_dict: dict[str, Any]) -> str:
    """Determine the emotional gate based on affect state.

    M8 E8.1.5: Three gate levels:
        - "open": valence >= 0 (neutral/positive). All results can be woven.
        - "suppress_trivial": valence < -0.5 (grief, anger, frustration).
          Only critical/urgent results should be woven.
        - "suppress_all_non_safety": current_emotion == "crisis" or
          safety_band == "RED".  Only safety-critical results break through.

    Args:
        affect_dict: Dict from affective_now section.

    Returns:
        One of EMOTIONAL_GATE_OPEN, EMOTIONAL_GATE_SUPPRESS_TRIVIAL,
        or EMOTIONAL_GATE_SUPPRESS_ALL_NON_SAFETY.
    """
    if not affect_dict:
        return EMOTIONAL_GATE_OPEN

    # Check for crisis / RED band first (most restrictive)
    current_emotion = affect_dict.get("current_emotion", "")
    safety_band = affect_dict.get("safety_band", "")
    if current_emotion == "crisis" or safety_band == "RED":
        return EMOTIONAL_GATE_SUPPRESS_ALL_NON_SAFETY

    # Check valence threshold
    valence = affect_dict.get("valence", 0.0)
    if isinstance(valence, (int, float)) and valence < EMOTIONAL_SUPPRESS_VALENCE:
        return EMOTIONAL_GATE_SUPPRESS_TRIVIAL

    return EMOTIONAL_GATE_OPEN


# =====================================================================
# 8.2.1 -- WeaveDecision enum
# =====================================================================


class WeaveDecision(IntEnum):
    """Outcome of the adaptive weave decision engine.

    M8 E8.2.1: Five possible decisions, ordered by delivery urgency.
    The engine is a pure function: (WeaveSignal) -> WeaveDecisionResult.

    Values:
        IMMEDIATE -- Deliver now (0ms window). Used for idle-eager and
                     critical-urgency results.
        BATCH     -- Deliver after a dynamic window (200-5000ms). Window
                     is adjusted based on idle duration, pool pressure,
                     and pending count.
        DEFER     -- Hold until user sends next message or explicitly asks.
                     Result is injected into the STANDARD prompt as
                     async_results_context, not delivered via WEAVE mode.
        DIGEST    -- Accumulate for 10-30s then synthesize into a summary
                     before delivering. Used for 3+ low-urgency results.
        SUPPRESS  -- Do not deliver. Result is logged but not presented.
                     Used for stale, cancelled, or emotionally inappropriate
                     results (suppress_all_non_safety gate).
    """

    IMMEDIATE = 0
    BATCH = 1
    DEFER = 2
    DIGEST = 3
    SUPPRESS = 4


# =====================================================================
# 8.2.1 -- WeaveDecisionResult dataclass
# =====================================================================


@dataclass(frozen=True)
class WeaveDecisionResult:
    """Outcome of a single WeavePolicy.decide() call.

    M8 E8.2.1: Immutable result carrying the decision, dynamic window,
    human-readable reasoning, and flags indicating which overrides
    were applied.

    Attributes:
        decision:              The WeaveDecision value.
        window_ms:             Batch/digest window in milliseconds.
                               0 for IMMEDIATE, dynamic for BATCH/DIGEST,
                               0 for DEFER/SUPPRESS (no timer needed).
        reasoning:             Human-readable explanation of the decision.
                               Included in the weave.decided event for
                               auditable decision replay.
        urgency_override:      True if critical urgency overrode the
                               normal policy (rules 1-2 in the table).
        emotional_gate_applied: True if the emotional gate (suppress_trivial
                               or suppress_all) changed the decision from
                               what it would have been without affect.
    """

    decision: WeaveDecision = WeaveDecision.BATCH
    window_ms: int = 500
    reasoning: str = ""
    urgency_override: bool = False
    emotional_gate_applied: bool = False


# =====================================================================
# OPP-1 -- Paced Delivery Protocol (generalized kernel primitive)
# =====================================================================


class PacingStrategy(IntEnum):
    """How batched results should be paced to the user.

    Generalized kernel primitive: verticals configure which strategy
    to apply via policy hooks. The kernel provides the execution.

    Values:
        NONE           -- Deliver all results in a single envelope (default).
        STAGGER        -- Deliver one result at a time with inter-group delay.
        GROUP_BY_DOMAIN -- Group results by domain, deliver each group
                          with inter-group delay.
        PRIORITY_CASCADE -- Deliver critical/urgent first, then normal,
                           then low priority with escalating delays.
    """

    NONE = 0
    STAGGER = 1
    GROUP_BY_DOMAIN = 2
    PRIORITY_CASCADE = 3


@dataclass(frozen=True)
class PacingPlan:
    """Execution plan for paced delivery of batched results.

    Produced by compute_pacing_plan(), consumed by WeaveBatcher.flush().

    Attributes:
        strategy:            The PacingStrategy used.
        groups:              Ordered list of result groups. Each group is
                             delivered as a single envelope.
        inter_group_delay_ms: Delay in ms before delivering each group
                             (index-aligned with groups; first is always 0).
    """

    strategy: PacingStrategy = PacingStrategy.NONE
    groups: list[list[dict[str, Any]]] = field(default_factory=list)
    inter_group_delay_ms: list[int] = field(default_factory=list)


def compute_pacing_plan(
    results: list[dict[str, Any]],
    strategy: PacingStrategy = PacingStrategy.NONE,
    base_delay_ms: int = 800,
) -> PacingPlan:
    """Compute a PacingPlan for the given results and strategy.

    Generalized kernel primitive: the strategy is selected by the
    vertical's weave policy hook. The kernel computes the plan.

    Args:
        results:       Sorted result dicts from sort_results_for_delivery().
        strategy:      Pacing strategy to apply.
        base_delay_ms: Base inter-group delay (scaled by strategy).

    Returns:
        PacingPlan ready for execution by WeaveBatcher.
    """
    if not results or strategy == PacingStrategy.NONE:
        return PacingPlan(
            strategy=PacingStrategy.NONE,
            groups=[results] if results else [],
            inter_group_delay_ms=[0] if results else [],
        )

    if strategy == PacingStrategy.STAGGER:
        groups = [[r] for r in results]
        delays = [0] + [base_delay_ms] * (len(groups) - 1)
        return PacingPlan(
            strategy=strategy,
            groups=groups,
            inter_group_delay_ms=delays,
        )

    if strategy == PacingStrategy.GROUP_BY_DOMAIN:
        domain_buckets: dict[str, list[dict[str, Any]]] = {}
        for r in results:
            domain = _extract_domain(r)
            domain_buckets.setdefault(domain, []).append(r)
        groups = list(domain_buckets.values())
        delays = [0] + [base_delay_ms] * (len(groups) - 1)
        return PacingPlan(
            strategy=strategy,
            groups=groups,
            inter_group_delay_ms=delays,
        )

    if strategy == PacingStrategy.PRIORITY_CASCADE:
        urgency_order = {"critical": 0, "urgent": 0, "normal": 1, "low": 2}
        buckets: dict[int, list[dict[str, Any]]] = {}
        for r in results:
            urg = r.get("urgency", "normal")
            rank = urgency_order.get(urg, 1)
            buckets.setdefault(rank, []).append(r)
        groups = [buckets[k] for k in sorted(buckets)]
        delays = [0]
        for i in range(1, len(groups)):
            delays.append(base_delay_ms * i)
        return PacingPlan(
            strategy=strategy,
            groups=groups,
            inter_group_delay_ms=delays,
        )

    return PacingPlan(
        strategy=PacingStrategy.NONE,
        groups=[results],
        inter_group_delay_ms=[0],
    )


# =====================================================================
# 8.1.1 -- WeaveSignal dataclass
# =====================================================================


@dataclass(frozen=True)
class WeaveSignal:
    """Snapshot of all signals needed for the adaptive weave decision.

    M8 E8.1.1: Immutable snapshot collected atomically in a single
    synchronous pass (no awaits between field reads).  All 6 signal
    categories are represented:

    1. FSM state          -> fsm_state
    2. Task urgency       -> pending_urgency_profile, has_critical
    3. User typing        -> user_typing, user_idle_ms
    4. Pending count      -> pending_count, pending_urgency_profile
    5. Affect band        -> affect_band, affect_valence, emotional_gate
    6. BackPool util      -> backpool_utilization

    Additional cross-milestone signals:
    - hitl_pending (M6): True if any task has PENDING HILSubTask
    - recent_weave_count: weaves in last 5 minutes (from turn state)

    WeaveSignal is NOT visible to the LLM.  It feeds the WeavePolicy
    decision engine (E8.2) which determines what the LLM sees.
    """

    # FSM state (ConciergeState enum value name)
    fsm_state: str = ""

    # Task urgency (8.1.4)
    pending_count: int = 0
    pending_urgency_profile: dict[str, int] = field(
        default_factory=lambda: {"critical": 0, "normal": 0, "low": 0}
    )
    has_critical: bool = False

    # User activity (8.1.2, 8.1.3)
    user_typing: bool = False
    user_idle_ms: int = 0

    # Affect (8.1.5)
    affect_band: str = ""
    affect_valence: float = 0.0
    emotional_gate: str = EMOTIONAL_GATE_OPEN

    # BackPool utilization (8.1.5 / M7 cross-ref)
    backpool_utilization: float = 0.0

    # Cross-milestone signals
    hitl_pending: bool = False
    recent_weave_count: int = 0

    # -----------------------------------------------------------------
    # Factory: atomic collection from runtime sources
    # -----------------------------------------------------------------

    @classmethod
    def from_runtime(
        cls,
        *,
        fsm_state: ConciergeState,
        turn_state: Any = None,
        back_pool: Any = None,
        ss: Any = None,
        activity_tracker: UserActivityTracker | None = None,
        hitl_pending: bool = False,
        recent_weave_count: int = 0,
    ) -> WeaveSignal:
        """Collect all signals atomically from runtime sources.

        M8 E8.1.1: All reads are synchronous -- no awaits between
        field reads to avoid state changes mid-collection.

        M8 E8.5.3: Reads BackPool from same instance as InflightContext
        (no duplicate queries).  Affect read is stable (post-Phase 1).

        Args:
            fsm_state:          Current ConciergeState.
            turn_state:         FSMTurnState instance (for pending_results).
            back_pool:          BackPool instance (for utilization).
            ss:                 SessionState (for affective_now).
            activity_tracker:   UserActivityTracker (for typing/idle).
            hitl_pending:       True if any task has PENDING HILSubTask.
            recent_weave_count: Weaves in last 5 minutes.

        Returns:
            Immutable WeaveSignal snapshot.
        """
        # --- Pending results (8.1.4) ---
        pending_items: list[dict[str, Any]] = []
        if turn_state is not None:
            pending_items = list(turn_state.pending_results)
        p_count = len(pending_items)
        p_profile = _profile_urgency(pending_items)
        p_critical = _has_critical(pending_items)

        # --- User activity (8.1.2, 8.1.3) ---
        u_typing = False
        u_idle_ms = 0
        if activity_tracker is not None:
            u_typing = activity_tracker.is_typing
            u_idle_ms = activity_tracker.idle_ms

        # --- Affect (8.1.5) ---
        affect_dict = _get_affect_dict_from_ss(ss)
        a_band = affect_dict.get("affect_band", "")
        if not a_band:
            a_band = affect_dict.get("band", "")
        a_valence = affect_dict.get("valence", 0.0)
        if not isinstance(a_valence, (int, float)):
            a_valence = 0.0
        e_gate = _compute_emotional_gate(affect_dict)

        # --- BackPool utilization (M7 cross-ref) ---
        bp_util = 0.0
        if back_pool is not None:
            try:
                pool_state = back_pool.get_pool_state()
                size = pool_state.get("size", 0)
                active = pool_state.get("active", 0)
                bp_util = active / max(size, 1)
            except Exception:
                logger.debug(
                    "WeaveSignal.from_runtime: failed to read BackPool state",
                    exc_info=True,
                )

        return cls(
            fsm_state=fsm_state.name if isinstance(fsm_state, ConciergeState) else str(fsm_state),
            pending_count=p_count,
            pending_urgency_profile=p_profile,
            has_critical=p_critical,
            user_typing=u_typing,
            user_idle_ms=u_idle_ms,
            affect_band=a_band,
            affect_valence=float(a_valence),
            emotional_gate=e_gate,
            backpool_utilization=round(bp_util, 4),
            hitl_pending=hitl_pending,
            recent_weave_count=recent_weave_count,
        )

    # -----------------------------------------------------------------
    # Serialization (for WeaveDecisionMadeEvent.signal_snapshot)
    # -----------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for event payload / debugging.

        M8 E8.2.4: Included in WeaveDecisionMadeEvent.signal_snapshot
        for auditable decision replay.
        """
        return {
            "fsm_state": self.fsm_state,
            "pending_count": self.pending_count,
            "pending_urgency_profile": dict(self.pending_urgency_profile),
            "has_critical": self.has_critical,
            "user_typing": self.user_typing,
            "user_idle_ms": self.user_idle_ms,
            "affect_band": self.affect_band,
            "affect_valence": self.affect_valence,
            "emotional_gate": self.emotional_gate,
            "backpool_utilization": self.backpool_utilization,
            "hitl_pending": self.hitl_pending,
            "recent_weave_count": self.recent_weave_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WeaveSignal:
        """Deserialize from dict (for replay / testing)."""
        return cls(
            fsm_state=data.get("fsm_state", ""),
            pending_count=data.get("pending_count", 0),
            pending_urgency_profile=data.get(
                "pending_urgency_profile",
                {"critical": 0, "normal": 0, "low": 0},
            ),
            has_critical=data.get("has_critical", False),
            user_typing=data.get("user_typing", False),
            user_idle_ms=data.get("user_idle_ms", 0),
            affect_band=data.get("affect_band", ""),
            affect_valence=data.get("affect_valence", 0.0),
            emotional_gate=data.get("emotional_gate", EMOTIONAL_GATE_OPEN),
            backpool_utilization=data.get("backpool_utilization", 0.0),
            hitl_pending=data.get("hitl_pending", False),
            recent_weave_count=data.get("recent_weave_count", 0),
        )


# =====================================================================
# 8.2.2 -- WeavePolicy decision engine
# =====================================================================


class WeavePolicy:
    """Adaptive weave decision engine.

    M8 E8.2.2: Pure-function decision engine that maps a WeaveSignal
    snapshot to a WeaveDecisionResult.  The decide() method implements
    a priority-ordered decision table (9 rules, first-match wins).
    Each rule has a clear LLM consequence documented inline.

    The engine is stateless -- all context comes from the WeaveSignal.
    Configuration comes from WeavePolicyConfig (loaded from config/loader.py).

    Usage::

        from poc.k1_poc.config.loader import get_config
        policy = WeavePolicy(get_config().weave_policy)
        signal = WeaveSignal.from_runtime(...)
        result = policy.decide(signal)
        # result.decision, result.window_ms, result.reasoning
    """

    __slots__ = ("_cfg",)

    def __init__(self, config: Any = None) -> None:
        """Initialize with optional WeavePolicyConfig.

        Args:
            config: WeavePolicyConfig instance from config/loader.py.
                    If None, uses default thresholds from E8.1 constants.
        """
        self._cfg = config

    # -----------------------------------------------------------------
    # Config accessors (fall back to module constants / spec defaults)
    # -----------------------------------------------------------------

    @property
    def _idle_eager_ms(self) -> int:
        if self._cfg is not None and hasattr(self._cfg, "idle_eager_ms"):
            return self._cfg.idle_eager_ms
        return IDLE_EAGER_MS

    @property
    def _idle_batch_ms(self) -> int:
        if self._cfg is not None and hasattr(self._cfg, "idle_batch_ms"):
            return self._cfg.idle_batch_ms
        return IDLE_BATCH_MS

    @property
    def _digest_threshold_count(self) -> int:
        if self._cfg is not None and hasattr(self._cfg, "digest_threshold_count"):
            return self._cfg.digest_threshold_count
        return 3

    @property
    def _digest_window_ms(self) -> int:
        if self._cfg is not None and hasattr(self._cfg, "digest_window_ms"):
            return self._cfg.digest_window_ms
        return 15_000

    @property
    def _pool_pressure_threshold(self) -> float:
        if self._cfg is not None and hasattr(self._cfg, "pool_pressure_threshold"):
            return self._cfg.pool_pressure_threshold
        return 0.8

    @property
    def _pool_pressure_batch_ms(self) -> int:
        if self._cfg is not None and hasattr(self._cfg, "pool_pressure_batch_ms"):
            return self._cfg.pool_pressure_batch_ms
        return 2_000

    @property
    def _default_batch_ms(self) -> int:
        if self._cfg is not None and hasattr(self._cfg, "default_batch_ms"):
            return self._cfg.default_batch_ms
        return 500

    @property
    def _max_batch_ms(self) -> int:
        if self._cfg is not None and hasattr(self._cfg, "max_batch_ms"):
            return self._cfg.max_batch_ms
        return 5_000

    @property
    def _max_consecutive_defers(self) -> int:
        if self._cfg is not None and hasattr(self._cfg, "max_consecutive_defers"):
            return self._cfg.max_consecutive_defers
        return 5

    # -----------------------------------------------------------------
    # Core decision method
    # -----------------------------------------------------------------

    def decide(self, signal: WeaveSignal) -> WeaveDecisionResult:
        """Evaluate the 9-rule priority-ordered decision table.

        M8 E8.2.2: First-match wins.  Each rule produces a
        WeaveDecisionResult with decision, window_ms, reasoning,
        and override flags.

        Rules:
            1. LISTENING + idle > IDLE_EAGER_MS -> IMMEDIATE
            2. has_critical + gate open -> IMMEDIATE
            3. user_typing -> DEFER
            4. gate == suppress_all_non_safety -> SUPPRESS
            5. gate == suppress_trivial + no critical -> DEFER
            6. pending >= digest_threshold + all low -> DIGEST
            7. pending >= 1 + idle > IDLE_BATCH_MS -> BATCH (dynamic)
            8. backpool_utilization > pool_pressure_threshold -> BATCH
            9. default -> BATCH (default_batch_ms)

        Args:
            signal: Immutable WeaveSignal snapshot.

        Returns:
            WeaveDecisionResult with decision, window_ms, reasoning.
        """
        # ----- Rule 1: LISTENING + long idle -> eager delivery -----
        if (
            signal.fsm_state == ConciergeState.LISTENING.name
            and signal.user_idle_ms > self._idle_eager_ms
        ):
            return WeaveDecisionResult(
                decision=WeaveDecision.IMMEDIATE,
                window_ms=0,
                reasoning=(
                    f"R1: LISTENING + idle {signal.user_idle_ms}ms "
                    f"> {self._idle_eager_ms}ms -> IMMEDIATE"
                ),
                urgency_override=False,
                emotional_gate_applied=False,
            )

        # ----- Rule 2: critical urgency + gate open -> immediate -----
        if signal.has_critical and signal.emotional_gate == EMOTIONAL_GATE_OPEN:
            return WeaveDecisionResult(
                decision=WeaveDecision.IMMEDIATE,
                window_ms=0,
                reasoning="R2: has_critical + gate=open -> IMMEDIATE",
                urgency_override=True,
                emotional_gate_applied=False,
            )

        # ----- Rule 3: user typing -> defer -----
        if signal.user_typing:
            return WeaveDecisionResult(
                decision=WeaveDecision.DEFER,
                window_ms=0,
                reasoning="R3: user_typing=True -> DEFER",
                urgency_override=False,
                emotional_gate_applied=False,
            )

        # ----- Rule 4: suppress_all_non_safety -> suppress -----
        if signal.emotional_gate == EMOTIONAL_GATE_SUPPRESS_ALL_NON_SAFETY:
            return WeaveDecisionResult(
                decision=WeaveDecision.SUPPRESS,
                window_ms=0,
                reasoning="R4: gate=suppress_all_non_safety -> SUPPRESS",
                urgency_override=False,
                emotional_gate_applied=True,
            )

        # ----- Rule 5: suppress_trivial + no critical -> defer -----
        if signal.emotional_gate == EMOTIONAL_GATE_SUPPRESS_TRIVIAL and not signal.has_critical:
            return WeaveDecisionResult(
                decision=WeaveDecision.DEFER,
                window_ms=0,
                reasoning="R5: gate=suppress_trivial + no critical -> DEFER",
                urgency_override=False,
                emotional_gate_applied=True,
            )

        # ----- Rule 5.5: HITL pending -> defer non-critical -----
        if signal.hitl_pending and not signal.has_critical:
            return WeaveDecisionResult(
                decision=WeaveDecision.DEFER,
                window_ms=0,
                reasoning="R5.5: hitl_pending + no critical -> DEFER (HITL flow priority)",
                urgency_override=False,
                emotional_gate_applied=False,
            )

        # ----- Rule 6: 3+ pending + all low -> digest -----
        if signal.pending_count >= self._digest_threshold_count:
            profile = signal.pending_urgency_profile
            all_low = (
                profile.get("critical", 0) == 0
                and profile.get("normal", 0) == 0
                and profile.get("low", 0) >= self._digest_threshold_count
            )
            if all_low:
                return WeaveDecisionResult(
                    decision=WeaveDecision.DIGEST,
                    window_ms=self._digest_window_ms,
                    reasoning=(
                        f"R6: pending={signal.pending_count} >= "
                        f"{self._digest_threshold_count} + all low -> "
                        f"DIGEST({self._digest_window_ms}ms)"
                    ),
                    urgency_override=False,
                    emotional_gate_applied=False,
                )

        # ----- Rule 7: pending >= 1 + idle > IDLE_BATCH_MS -> batch -----
        if signal.pending_count >= 1 and signal.user_idle_ms > self._idle_batch_ms:
            # Dynamic window: shorter when user has been idle longer
            raw_ms = self._default_batch_ms - signal.user_idle_ms // 20
            window = max(200, min(raw_ms, self._max_batch_ms))
            return WeaveDecisionResult(
                decision=WeaveDecision.BATCH,
                window_ms=window,
                reasoning=(
                    f"R7: pending={signal.pending_count} + idle "
                    f"{signal.user_idle_ms}ms > {self._idle_batch_ms}ms "
                    f"-> BATCH({window}ms)"
                ),
                urgency_override=False,
                emotional_gate_applied=False,
            )

        # ----- Rule 8: pool pressure -> batch (wider window) -----
        if signal.backpool_utilization > self._pool_pressure_threshold:
            return WeaveDecisionResult(
                decision=WeaveDecision.BATCH,
                window_ms=self._pool_pressure_batch_ms,
                reasoning=(
                    f"R8: pool_util={signal.backpool_utilization:.2f} "
                    f"> {self._pool_pressure_threshold} -> "
                    f"BATCH({self._pool_pressure_batch_ms}ms)"
                ),
                urgency_override=False,
                emotional_gate_applied=False,
            )

        # ----- Rule 9: default -> batch (500ms) -----
        return WeaveDecisionResult(
            decision=WeaveDecision.BATCH,
            window_ms=self._default_batch_ms,
            reasoning=f"R9: default -> BATCH({self._default_batch_ms}ms)",
            urgency_override=False,
            emotional_gate_applied=False,
        )


# =====================================================================
# 8.4.1 -- WeaveIntegrationRouter
# =====================================================================


@dataclass(frozen=True)
class RoutingResult:
    """Outcome of WeaveIntegrationRouter.route_decision().

    M8 E8.4.1: Describes the action the FSM controller should take
    after the WeavePolicy decision has been made.

    Attributes:
        action:      Short action tag ("flush_now", "schedule_flush",
                     "mark_deferred", "schedule_digest", "suppress").
        window_ms:   Timer delay for schedule_flush / schedule_digest.
        decision:    The underlying WeaveDecisionResult.
        reasoning:   Human-readable routing explanation.
    """

    action: str = "suppress"
    window_ms: int = 0
    decision: WeaveDecisionResult = field(
        default_factory=WeaveDecisionResult,
    )
    reasoning: str = ""


class WeaveIntegrationRouter:
    """Routes a WeavePolicy decision to the appropriate FSM handler.

    M8 E8.4.1: Takes a WeavePolicy + WeaveSignal and produces a
    RoutingResult that the FSM controller executes.  Implements the
    canonical 12-step ordering from the spec (8.5.2).

    The router is a thin routing layer -- it does NOT own timers,
    queues, or delivery.  It maps decision -> action tag that the
    controller interprets.

    Usage::

        router = WeaveIntegrationRouter(policy)
        routing = router.route_decision(signal)
        if routing.action == "flush_now":
            controller._deliver_weave_immediate()
        elif routing.action == "schedule_flush":
            controller._schedule_weave_flush(routing.window_ms)
        ...
    """

    __slots__ = ("_policy",)

    def __init__(self, policy: WeavePolicy) -> None:
        self._policy = policy

    @property
    def policy(self) -> WeavePolicy:
        """The underlying WeavePolicy instance."""
        return self._policy

    def route_decision(self, signal: WeaveSignal) -> RoutingResult:
        """Evaluate the policy and route to the correct action.

        M8 E8.4.1: Canonical ordering:
          1. Collect signal (caller did this).
          2. Call policy.decide(signal).
          3. Map decision to action tag.

        Args:
            signal: Immutable WeaveSignal snapshot.

        Returns:
            RoutingResult with action tag, window_ms, and decision.
        """
        decision_result = self._policy.decide(signal)
        return self._map_decision(decision_result)

    def route_with_result(
        self,
        decision_result: WeaveDecisionResult,
    ) -> RoutingResult:
        """Route a pre-computed decision (for fallback / re-evaluation).

        Args:
            decision_result: Already-computed WeaveDecisionResult.

        Returns:
            RoutingResult with action tag.
        """
        return self._map_decision(decision_result)

    # -----------------------------------------------------------------
    # Internal mapping
    # -----------------------------------------------------------------

    @staticmethod
    def _map_decision(dr: WeaveDecisionResult) -> RoutingResult:
        """Map WeaveDecisionResult to RoutingResult action tag."""
        d = dr.decision
        if d == WeaveDecision.IMMEDIATE:
            return RoutingResult(
                action="flush_now",
                window_ms=0,
                decision=dr,
                reasoning=f"IMMEDIATE -> flush_now: {dr.reasoning}",
            )
        if d == WeaveDecision.BATCH:
            return RoutingResult(
                action="schedule_flush",
                window_ms=dr.window_ms,
                decision=dr,
                reasoning=f"BATCH({dr.window_ms}ms) -> schedule_flush: {dr.reasoning}",
            )
        if d == WeaveDecision.DEFER:
            return RoutingResult(
                action="mark_deferred",
                window_ms=0,
                decision=dr,
                reasoning=f"DEFER -> mark_deferred: {dr.reasoning}",
            )
        if d == WeaveDecision.DIGEST:
            return RoutingResult(
                action="schedule_digest",
                window_ms=dr.window_ms,
                decision=dr,
                reasoning=f"DIGEST({dr.window_ms}ms) -> schedule_digest: {dr.reasoning}",
            )
        # SUPPRESS or unknown
        return RoutingResult(
            action="suppress",
            window_ms=0,
            decision=dr,
            reasoning=f"SUPPRESS -> suppress: {dr.reasoning}",
        )


# =====================================================================
# 8.4.2 -- TypingPolicyReEvaluator
# =====================================================================


@dataclass(frozen=True)
class ReEvalResult:
    """Outcome of a typing-based policy re-evaluation.

    M8 E8.4.2: Describes what happened when typing state changed.

    Attributes:
        action:        "cancel_timer" | "restart_timer" | "no_change"
        new_decision:  The re-evaluated WeaveDecisionResult (or None).
        reasoning:     Human-readable explanation.
    """

    action: str = "no_change"
    new_decision: WeaveDecisionResult | None = None
    reasoning: str = ""


class TypingPolicyReEvaluator:
    """Re-evaluates pending BATCH timers when typing state changes.

    M8 E8.4.2: When user starts typing, any active BATCH timer should
    be paused (cancelled) and results marked as deferred.  When user
    stops typing (+ debounce), the policy re-evaluates and may restart
    the BATCH timer with a new window.

    This creates a responsive loop:
        timer starts on task.complete ->
        pauses on typing ->
        resumes on silence.

    The re-evaluator is stateless; timer state is owned by the FSM
    controller.  This class determines the INTENT (cancel/restart);
    the controller executes it.
    """

    __slots__ = ("_policy", "_debounce_ms")

    def __init__(
        self,
        policy: WeavePolicy,
        debounce_ms: int = 500,
    ) -> None:
        self._policy = policy
        self._debounce_ms = debounce_ms

    @property
    def policy(self) -> WeavePolicy:
        """The underlying WeavePolicy instance."""
        return self._policy

    @property
    def debounce_ms(self) -> int:
        """Debounce window for typing_stop in milliseconds."""
        return self._debounce_ms

    def on_typing_start(
        self,
        signal: WeaveSignal,
        has_active_timer: bool = False,
    ) -> ReEvalResult:
        """User started typing -- re-evaluate pending BATCH timer.

        M8 E8.4.2: If a BATCH timer is active, cancel it and DEFER.
        The policy should return DEFER because signal.user_typing=True
        (Rule 3).

        Args:
            signal:           Current WeaveSignal (should have user_typing=True).
            has_active_timer: Whether a flush timer is currently running.

        Returns:
            ReEvalResult with action.
        """
        if not has_active_timer:
            return ReEvalResult(
                action="no_change",
                reasoning="No active timer to cancel on typing_start.",
            )

        # Re-evaluate the policy with typing=True signal
        decision = self._policy.decide(signal)

        if decision.decision == WeaveDecision.DEFER:
            return ReEvalResult(
                action="cancel_timer",
                new_decision=decision,
                reasoning=(f"Typing detected, policy returned DEFER: " f"{decision.reasoning}"),
            )

        # Policy did not return DEFER (maybe critical urgency overrode).
        # Keep the timer running.
        return ReEvalResult(
            action="no_change",
            new_decision=decision,
            reasoning=(
                f"Typing detected but policy returned "
                f"{decision.decision.name}: {decision.reasoning}"
            ),
        )

    def on_typing_stop(
        self,
        signal: WeaveSignal,
        has_pending_results: bool = False,
    ) -> ReEvalResult:
        """User stopped typing (after debounce) -- re-evaluate.

        M8 E8.4.2: After debounce_ms since typing_stop, re-evaluate
        the policy.  If it returns BATCH, a new timer should be
        started.

        Args:
            signal:              Current WeaveSignal (user_typing=False).
            has_pending_results: Whether deferred/pending results exist.

        Returns:
            ReEvalResult with action.
        """
        if not has_pending_results:
            return ReEvalResult(
                action="no_change",
                reasoning="No pending results to re-evaluate on typing_stop.",
            )

        # Re-evaluate with typing=False signal
        decision = self._policy.decide(signal)

        if decision.decision in (WeaveDecision.BATCH, WeaveDecision.IMMEDIATE):
            return ReEvalResult(
                action="restart_timer",
                new_decision=decision,
                reasoning=(
                    f"Typing stopped, policy returned "
                    f"{decision.decision.name}({decision.window_ms}ms): "
                    f"{decision.reasoning}"
                ),
            )

        if decision.decision == WeaveDecision.DIGEST:
            return ReEvalResult(
                action="restart_timer",
                new_decision=decision,
                reasoning=(
                    f"Typing stopped, policy returned DIGEST"
                    f"({decision.window_ms}ms): {decision.reasoning}"
                ),
            )

        # Still DEFER or SUPPRESS -- no timer restart
        return ReEvalResult(
            action="no_change",
            new_decision=decision,
            reasoning=(
                f"Typing stopped but policy returned "
                f"{decision.decision.name}: {decision.reasoning}"
            ),
        )


# =====================================================================
# 8.4.3 -- WeaveFallbackHandler
# =====================================================================


# Mapping from static WeaveAction to adaptive WeaveDecision for fallback
_ACTION_TO_DECISION: dict[str, WeaveDecision] = {
    "immediate": WeaveDecision.IMMEDIATE,
    "queue_weave": WeaveDecision.BATCH,
    "queue": WeaveDecision.BATCH,
    "chain": WeaveDecision.BATCH,
    "dead_letter": WeaveDecision.SUPPRESS,
}

# Fixed fallback window matching pre-M8 behavior
_FALLBACK_WINDOW_MS: int = 500


class WeaveFallbackHandler:
    """Deterministic fallback when adaptive policy fails.

    M8 E8.4.3: If WeaveSignal.from_runtime() or WeavePolicy.decide()
    raises any exception, the fallback produces IDENTICAL behavior to
    the pre-M8 static get_weave_action() + fixed 500ms window.

    Also activated when WeavePolicyConfig.enabled == False (safe
    rollout: deploy M8 code with policy disabled, enable per-session
    for A/B testing).

    Usage::

        handler = WeaveFallbackHandler()
        try:
            decision = policy.decide(signal)
        except Exception:
            decision = handler.fallback_decide(fsm_state)
    """

    __slots__ = ("_fallback_window_ms",)

    def __init__(self, fallback_window_ms: int = _FALLBACK_WINDOW_MS) -> None:
        self._fallback_window_ms = fallback_window_ms

    @property
    def fallback_window_ms(self) -> int:
        """The fixed fallback window in milliseconds."""
        return self._fallback_window_ms

    def fallback_decide(
        self,
        fsm_state: ConciergeState,
    ) -> WeaveDecisionResult:
        """Deterministic fallback using static state table.

        M8 E8.4.3: Maps get_weave_action(fsm_state) -> WeaveDecision.
        IMMEDIATE stays IMMEDIATE (0ms). Everything else becomes
        BATCH(500ms).

        Args:
            fsm_state: Current ConciergeState.

        Returns:
            WeaveDecisionResult with reasoning="fallback: ...".
        """
        from poc.k1_poc.protocols.weave_state import get_weave_action

        action = get_weave_action(fsm_state)
        decision = _ACTION_TO_DECISION.get(
            action.value,
            WeaveDecision.BATCH,
        )

        if decision == WeaveDecision.IMMEDIATE:
            return WeaveDecisionResult(
                decision=WeaveDecision.IMMEDIATE,
                window_ms=0,
                reasoning=(
                    f"fallback: state={fsm_state.name} -> " f"{action.value} -> IMMEDIATE(0ms)"
                ),
                urgency_override=False,
                emotional_gate_applied=False,
            )

        if decision == WeaveDecision.SUPPRESS:
            return WeaveDecisionResult(
                decision=WeaveDecision.SUPPRESS,
                window_ms=0,
                reasoning=(f"fallback: state={fsm_state.name} -> " f"{action.value} -> SUPPRESS"),
                urgency_override=False,
                emotional_gate_applied=False,
            )

        return WeaveDecisionResult(
            decision=WeaveDecision.BATCH,
            window_ms=self._fallback_window_ms,
            reasoning=(
                f"fallback: state={fsm_state.name} -> "
                f"{action.value} -> BATCH({self._fallback_window_ms}ms)"
            ),
            urgency_override=False,
            emotional_gate_applied=False,
        )

    def safe_decide(
        self,
        policy: WeavePolicy,
        signal: WeaveSignal,
        fsm_state: ConciergeState,
        *,
        policy_enabled: bool = True,
    ) -> WeaveDecisionResult:
        """Try adaptive policy, fall back on any error.

        M8 E8.4.3: Wraps WeavePolicy.decide() in a try/except.
        If policy_enabled is False, skips the policy entirely.

        Args:
            policy:         WeavePolicy instance.
            signal:         WeaveSignal snapshot.
            fsm_state:      Current ConciergeState (for fallback).
            policy_enabled: WeavePolicyConfig.enabled flag.

        Returns:
            WeaveDecisionResult (from policy or fallback).
        """
        if not policy_enabled:
            logger.info(
                "WeaveFallbackHandler: policy disabled, using fallback " "for state=%s",
                fsm_state.name,
            )
            return self.fallback_decide(fsm_state)

        try:
            return policy.decide(signal)
        except Exception:
            logger.warning(
                "WeaveFallbackHandler: policy.decide() failed for " "state=%s, using fallback",
                fsm_state.name,
                exc_info=True,
            )
            return self.fallback_decide(fsm_state)


# =====================================================================
# 8.4.4 -- WeaveMetricsCollector
# =====================================================================


class WeaveMetricsCollector:
    """Per-session weave quality metrics tracker.

    M8 E8.4.4: Tracks decision counts, latency, and acknowledgement
    rate for empirical policy tuning.  Metrics are emitted at session
    end as k1.metrics.weave.v1.

    Fields tracked:
        weave_count:       Total IMMEDIATE + BATCH deliveries.
        digest_count:      Total DIGEST deliveries.
        defer_count:       Total DEFER decisions (including re-evals).
        suppress_count:    Total SUPPRESS decisions.
        weave_latencies:   List of (task.complete -> delivery) ms.
        acknowledged:      Count of results user acknowledged.
        total_delivered:   Count of total results delivered.

    The collector is NOT a bus event emitter.  It collects in-memory
    and provides to_metrics_dict() and to_event() for the session-end
    emission path.
    """

    __slots__ = (
        "_weave_count",
        "_digest_count",
        "_defer_count",
        "_suppress_count",
        "_batch_count",
        "_immediate_count",
        "_weave_latencies",
        "_acknowledged",
        "_total_delivered",
        "_fallback_count",
    )

    def __init__(self) -> None:
        self._weave_count: int = 0
        self._digest_count: int = 0
        self._defer_count: int = 0
        self._suppress_count: int = 0
        self._batch_count: int = 0
        self._immediate_count: int = 0
        self._weave_latencies: list[float] = []
        self._acknowledged: int = 0
        self._total_delivered: int = 0
        self._fallback_count: int = 0

    # -----------------------------------------------------------------
    # Recording
    # -----------------------------------------------------------------

    def record_decision(
        self,
        decision_result: WeaveDecisionResult,
        latency_ms: float = 0.0,
        *,
        fallback_used: bool = False,
    ) -> None:
        """Record a weave decision and optional delivery latency.

        M8 E8.4.4: Called after every WeavePolicy.decide() or fallback.

        Args:
            decision_result: The decision that was made.
            latency_ms:      Time from task.complete to delivery (0 if
                             not yet delivered, e.g. DEFER/SUPPRESS).
            fallback_used:   True if deterministic fallback was used.
        """
        d = decision_result.decision

        if d == WeaveDecision.IMMEDIATE:
            self._weave_count += 1
            self._immediate_count += 1
            self._total_delivered += 1
            if latency_ms > 0:
                self._weave_latencies.append(latency_ms)

        elif d == WeaveDecision.BATCH:
            self._weave_count += 1
            self._batch_count += 1
            self._total_delivered += 1
            if latency_ms > 0:
                self._weave_latencies.append(latency_ms)

        elif d == WeaveDecision.DEFER:
            self._defer_count += 1

        elif d == WeaveDecision.DIGEST:
            self._digest_count += 1
            self._total_delivered += 1
            if latency_ms > 0:
                self._weave_latencies.append(latency_ms)

        elif d == WeaveDecision.SUPPRESS:
            self._suppress_count += 1

        if fallback_used:
            self._fallback_count += 1

    def record_acknowledgement(self) -> None:
        """Record that user acknowledged a woven result.

        M8 E8.4.4: Called heuristically when the user's next message
        references a previously woven task result.
        """
        self._acknowledged += 1

    # -----------------------------------------------------------------
    # Read-out
    # -----------------------------------------------------------------

    @property
    def weave_count(self) -> int:
        """Total IMMEDIATE + BATCH deliveries."""
        return self._weave_count

    @property
    def digest_count(self) -> int:
        """Total DIGEST deliveries."""
        return self._digest_count

    @property
    def defer_count(self) -> int:
        """Total DEFER decisions."""
        return self._defer_count

    @property
    def suppress_count(self) -> int:
        """Total SUPPRESS decisions."""
        return self._suppress_count

    @property
    def batch_count(self) -> int:
        """Total BATCH decisions (subset of weave_count)."""
        return self._batch_count

    @property
    def immediate_count(self) -> int:
        """Total IMMEDIATE decisions (subset of weave_count)."""
        return self._immediate_count

    @property
    def fallback_count(self) -> int:
        """Total decisions that used the fallback path."""
        return self._fallback_count

    @property
    def total_delivered(self) -> int:
        """Total results delivered to user."""
        return self._total_delivered

    @property
    def avg_latency_ms(self) -> float:
        """Average weave delivery latency in milliseconds."""
        if not self._weave_latencies:
            return 0.0
        return sum(self._weave_latencies) / len(self._weave_latencies)

    @property
    def user_acknowledged_rate(self) -> float:
        """Fraction of delivered results that user acknowledged (0.0-1.0)."""
        if self._total_delivered == 0:
            return 0.0
        return min(1.0, self._acknowledged / self._total_delivered)

    def to_metrics_dict(self) -> dict[str, Any]:
        """Serialize for structured logging / event payload.

        M8 E8.4.4: Complete metrics snapshot for session-end emission.
        """
        return {
            "weave_count": self._weave_count,
            "immediate_count": self._immediate_count,
            "batch_count": self._batch_count,
            "digest_count": self._digest_count,
            "defer_count": self._defer_count,
            "suppress_count": self._suppress_count,
            "fallback_count": self._fallback_count,
            "total_delivered": self._total_delivered,
            "acknowledged": self._acknowledged,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "user_acknowledged_rate": round(self.user_acknowledged_rate, 4),
            "latency_samples": len(self._weave_latencies),
        }

    def to_event(self, session_id: str = "") -> dict[str, Any]:
        """Build a k1.metrics.weave.v1 event payload.

        M8 E8.4.4: Emitted at session end by the controller.

        Args:
            session_id: Session identifier for correlation.

        Returns:
            Event payload dict for bus emission.
        """
        metrics = self.to_metrics_dict()
        metrics["session_id"] = session_id
        return metrics

    def reset(self) -> None:
        """Reset all counters (e.g. for test isolation)."""
        self._weave_count = 0
        self._digest_count = 0
        self._defer_count = 0
        self._suppress_count = 0
        self._batch_count = 0
        self._immediate_count = 0
        self._weave_latencies.clear()
        self._acknowledged = 0
        self._total_delivered = 0
        self._fallback_count = 0


# =====================================================================
# 8.4.5 -- WeaveQueue (alias for WeaveBatcher with policy delegation)
# =====================================================================


class WeaveQueue:
    """Queue manager for pending weave results.

    M8 E8.4.5: Consolidates WeaveBatcher role into a policy-aware
    queue.  WeaveBatcher retains its queue management (pending/queued
    lists, front_busy gating).  WeaveQueue delegates timing decisions
    to WeavePolicy -- it does NOT own its own timer.

    The FSM controller manages timers via _schedule_weave_flush().
    WeaveQueue manages only the queue state:
        - add_result(): enqueue a result
        - drain(): drain all pending results
        - set_front_busy(): toggle front busy gating
        - set_policy_window(): update the batch window from policy

    This replaces the independent WeaveBatcher timer with
    policy-driven timing.

    Usage::

        queue = WeaveQueue()
        queue.add_result(result_dict)
        # Policy decides timing -> controller schedules timer
        results = queue.drain()
    """

    __slots__ = (
        "_pending",
        "_queued",
        "_front_busy",
        "_max_depth",
        "_batch_window_ms",
        "_drain_count",
    )

    def __init__(
        self,
        max_depth: int = 16,
        batch_window_ms: int = 500,
    ) -> None:
        self._pending: list[dict[str, Any]] = []
        self._queued: list[dict[str, Any]] = []
        self._front_busy: bool = False
        self._max_depth = max_depth
        self._batch_window_ms = batch_window_ms
        self._drain_count: int = 0

    # -----------------------------------------------------------------
    # Queue management
    # -----------------------------------------------------------------

    def add_result(self, result: dict[str, Any]) -> dict[str, Any] | None:
        """Enqueue a result.

        M8 E8.4.5: If front is busy, result goes to the queued list.
        Otherwise it goes to pending.  If overflow, oldest is evicted.

        Args:
            result: Result dict from _on_task_complete.

        Returns:
            The evicted result dict if overflow, else None.
        """
        target = self._queued if self._front_busy else self._pending
        evicted: dict[str, Any] | None = None

        if len(target) >= self._max_depth:
            evicted = target.pop(0)
            logger.warning(
                "WeaveQueue: overflow at max_depth=%d, evicting task=%s",
                self._max_depth,
                evicted.get("task_id", "unknown"),
            )

        target.append(result)
        return evicted

    def drain(self) -> list[dict[str, Any]]:
        """Drain all pending results.

        Returns:
            List of result dicts.  Pending list is cleared.
        """
        results = list(self._pending)
        self._pending.clear()
        if results:
            self._drain_count += 1
        return results

    def set_front_busy(self, busy: bool) -> None:
        """Toggle front busy gating.

        When front finishes and queued results exist, they move
        to pending.
        """
        self._front_busy = busy
        if not busy and self._queued:
            self._pending.extend(self._queued)
            self._queued.clear()

    def set_policy_window(self, window_ms: int) -> None:
        """Update batch window from WeavePolicy decision.

        M8 E8.4.5: The controller reads this and uses it for
        timer scheduling.

        Args:
            window_ms: New batch window in milliseconds.
        """
        self._batch_window_ms = max(0, window_ms)

    # -----------------------------------------------------------------
    # Properties
    # -----------------------------------------------------------------

    @property
    def pending_count(self) -> int:
        """Number of results in the pending list."""
        return len(self._pending)

    @property
    def queued_count(self) -> int:
        """Number of results queued (front busy)."""
        return len(self._queued)

    @property
    def drain_count(self) -> int:
        """Total number of drain() calls that returned results."""
        return self._drain_count

    @property
    def batch_window_ms(self) -> int:
        """Current batch window in milliseconds."""
        return self._batch_window_ms

    @property
    def is_empty(self) -> bool:
        """Whether both pending and queued lists are empty."""
        return len(self._pending) == 0 and len(self._queued) == 0

    @property
    def total_count(self) -> int:
        """Total results across pending + queued."""
        return len(self._pending) + len(self._queued)


# =====================================================================
# 8.3.1 -- Dynamic batch window helper
# =====================================================================


def schedule_weave_flush(decision_result: WeaveDecisionResult) -> dict[str, Any]:
    """Determine flush scheduling parameters from a WeaveDecisionResult.

    M8 E8.3.1: Replaces the fixed WEAVE_BATCH_WINDOW_MS constant with
    a dynamic window_ms from the policy decision.  Returns a dict that
    the controller uses to schedule or skip the flush timer.

    Returns:
        Dict with keys:
            mode:       "immediate" | "delayed" | "skip"
            window_ms:  Delay in ms (0 for immediate, >0 for delayed)
            decision:   The WeaveDecision value name
            reasoning:  Human-readable reasoning from the decision

    Rules:
        - IMMEDIATE (window_ms == 0): mode="immediate", flush now.
        - BATCH / DIGEST (window_ms > 0): mode="delayed", use window_ms.
        - DEFER / SUPPRESS: mode="skip", no timer scheduled.
    """
    decision = decision_result.decision
    window = decision_result.window_ms

    if decision == WeaveDecision.IMMEDIATE or window == 0:
        if decision in (WeaveDecision.DEFER, WeaveDecision.SUPPRESS):
            return {
                "mode": "skip",
                "window_ms": 0,
                "decision": decision.name,
                "reasoning": decision_result.reasoning,
            }
        return {
            "mode": "immediate",
            "window_ms": 0,
            "decision": decision.name,
            "reasoning": decision_result.reasoning,
        }

    if decision in (WeaveDecision.DEFER, WeaveDecision.SUPPRESS):
        return {
            "mode": "skip",
            "window_ms": 0,
            "decision": decision.name,
            "reasoning": decision_result.reasoning,
        }

    # BATCH or DIGEST with positive window
    return {
        "mode": "delayed",
        "window_ms": window,
        "decision": decision.name,
        "reasoning": decision_result.reasoning,
    }


# =====================================================================
# 8.3.3 -- DigestPayload dataclass
# =====================================================================


@dataclass(frozen=True)
class DigestPayload:
    """Pre-synthesized digest of multiple low-urgency results.

    M8 E8.3.3: When pending_count >= digest_threshold_count and all
    results are low urgency, the system collects results for
    digest_window_ms and groups them by domain.  The digest is a
    compressed summary delivered via WEAVE mode instead of N raw
    [ASYNC RESULT ARRIVED] blocks.

    Attributes:
        result_count:     Total number of results in the digest.
        groups:           List of (domain, summaries) tuples.
                          Each summary is a list of one-line strings.
        total_window_ms:  The digest window used for accumulation.
        summary_text:     Pre-formatted summary text for the LLM prompt.
    """

    result_count: int = 0
    groups: tuple[tuple[str, tuple[str, ...]], ...] = ()
    total_window_ms: int = 15_000
    summary_text: str = ""

    @classmethod
    def from_results(
        cls,
        results: list[dict[str, Any]],
        window_ms: int = 15_000,
    ) -> DigestPayload:
        """Build a digest from a list of result dicts.

        M8 E8.3.3: Groups results by domain (from task dispatch
        metadata), sorts groups by urgency (critical first), and
        generates a 1-2 sentence summary per group using deterministic
        string formatting (no LLM call).

        Args:
            results:    List of result dicts (from pending_results).
            window_ms:  The digest window used.

        Returns:
            Immutable DigestPayload with pre-formatted summary.
        """
        if not results:
            return cls(
                result_count=0,
                groups=(),
                total_window_ms=window_ms,
                summary_text="No results to summarize.",
            )

        # Group by domain
        domain_map: dict[str, list[dict[str, Any]]] = {}
        for item in results:
            domain = _extract_domain(item)
            domain_map.setdefault(domain, []).append(item)

        # Sort domains: critical-containing domains first, then alpha
        def _domain_sort_key(entry: tuple[str, list[dict[str, Any]]]) -> tuple[int, str]:
            domain_name, items = entry
            has_crit = any(it.get("urgency", "normal") in ("critical", "urgent") for it in items)
            return (0 if has_crit else 1, domain_name)

        sorted_domains = sorted(domain_map.items(), key=_domain_sort_key)

        # Build groups and summary text
        groups: list[tuple[str, tuple[str, ...]]] = []
        summary_lines: list[str] = []

        for domain, items in sorted_domains:
            # Sort items within domain by urgency
            items_sorted = sorted(items, key=_result_sort_key)
            summaries: list[str] = []
            for item in items_sorted:
                task_id = item.get("task_id", "unknown")
                result_data = item.get("result", item.get("result_data", {}))
                desc = _one_line_summary(task_id, result_data)
                summaries.append(desc)
            groups.append((domain, tuple(summaries)))
            domain_label = domain if domain != "general" else "General"
            if len(items) == 1:
                summary_lines.append(f"{domain_label}: {summaries[0]}")
            else:
                summary_lines.append(
                    f"{domain_label} ({len(items)} tasks): " + "; ".join(summaries)
                )

        summary_text = "\n".join(summary_lines)

        return cls(
            result_count=len(results),
            groups=tuple(groups),
            total_window_ms=window_ms,
            summary_text=summary_text,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize for event payload / debugging."""
        return {
            "result_count": self.result_count,
            "groups": [{"domain": d, "summaries": list(s)} for d, s in self.groups],
            "total_window_ms": self.total_window_ms,
            "summary_text": self.summary_text,
        }


# =====================================================================
# 8.3.3 / 8.3.5 -- Result sorting and domain extraction helpers
# =====================================================================


# Urgency sort order: critical first, then normal, then low
_URGENCY_ORDER: dict[str, int] = {
    "critical": 0,
    "urgent": 0,
    "normal": 1,
    "low": 2,
}


def _extract_domain(item: dict[str, Any]) -> str:
    """Extract domain from a pending result dict.

    M8 E8.3.3/8.3.5: Looks for domain in result metadata, task_id
    prefix, or defaults to "general".

    Args:
        item: Result dict from pending_results.

    Returns:
        Domain string (e.g. "travel", "health", "general").
    """
    # Check explicit domain field
    domain = item.get("domain", "")
    if domain:
        return str(domain).lower()

    # Check result sub-dict for domain
    result = item.get("result", {})
    if isinstance(result, dict):
        domain = result.get("domain", "")
        if domain:
            return str(domain).lower()

    # Infer from task_id prefix (e.g. "travel_hotel_123" -> "travel")
    task_id = item.get("task_id", "")
    if task_id and "_" in task_id:
        prefix = task_id.split("_")[0]
        if prefix and len(prefix) > 1:
            return prefix.lower()

    return "general"


def _one_line_summary(task_id: str, result_data: Any) -> str:
    """Generate a one-line summary of a task result.

    M8 E8.3.3: Deterministic string formatting, no LLM call.

    Args:
        task_id:     Task identifier.
        result_data: Result payload (dict or other).

    Returns:
        One-line summary string.
    """
    if isinstance(result_data, dict):
        # Use 'summary' or 'description' if available
        for key in ("summary", "description", "message", "status"):
            if key in result_data:
                return str(result_data[key])[:120]
        # Fallback: first key-value pair
        for key, value in result_data.items():
            return f"{key}: {str(value)[:100]}"
    if result_data:
        return str(result_data)[:120]
    return f"Task {task_id} completed"


def _result_sort_key(item: dict[str, Any]) -> tuple[int, str, int]:
    """Sort key for result ordering.

    M8 E8.3.5: Sort by (a) urgency (critical first), (b) domain group,
    (c) FIFO within domain (queued_at_ns).

    Args:
        item: Result dict from pending_results.

    Returns:
        Tuple for sorting: (urgency_order, domain, queued_at_ns).
    """
    urgency = item.get("urgency", "normal")
    urgency_rank = _URGENCY_ORDER.get(urgency, 1)
    domain = _extract_domain(item)
    queued_at = item.get("queued_at_ns", 0)
    return (urgency_rank, domain, queued_at)


def sort_results_for_delivery(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Sort drained results before building the weave envelope.

    M8 E8.3.5: Ordering rules:
        (a) Critical urgency first.
        (b) Domain grouping (cluster related results together).
        (c) FIFO within a domain group (by queued_at_ns).

    This ordering feeds into the [ASYNC RESULT ARRIVED] blocks that
    the Front LLM receives.  Input ordering determines output ordering.

    Args:
        results: List of result dicts from drain_results().

    Returns:
        New sorted list (original list is not modified).
    """
    return sorted(results, key=_result_sort_key)


# =====================================================================
# 8.3.4 -- Urgency label and emotional context generators
# =====================================================================


def generate_urgency_label(
    results: list[dict[str, Any]],
    decision: WeaveDecision | None = None,
) -> str:
    """Generate an urgency label string for the WEAVE prompt.

    M8 E8.3.4: Gives the Front LLM explicit guidance on how
    prominently to present the results.

    Args:
        results:  List of result dicts being delivered.
        decision: The WeaveDecision that triggered delivery.

    Returns:
        One of:
            "URGENT -- present these results prominently"
            "Informational -- weave these results lightly into your response"
            "Summary -- present as a brief update"
    """
    if not results:
        return "Informational -- weave these results lightly into your response"

    # Check for any critical/urgent results
    has_crit = any(item.get("urgency", "normal") in ("critical", "urgent") for item in results)
    if has_crit:
        return "URGENT -- present these results prominently"

    # DIGEST mode -> summary label
    if decision == WeaveDecision.DIGEST:
        return "Summary -- present as a brief update"

    return "Informational -- weave these results lightly into your response"


def generate_emotional_context(
    emotional_gate: str = EMOTIONAL_GATE_OPEN,
    affect_valence: float = 0.0,
    affect_band: str = "",
) -> str:
    """Generate emotional context guidance for the WEAVE prompt.

    M8 E8.3.4: Gives the Front LLM explicit guidance on emotional
    tone to use when presenting async results.  Prevents jarring
    transitions (e.g. "hotel booked!" during grief).

    Args:
        emotional_gate: Gate value from WeaveSignal.
        affect_valence: Current valence from affective_now.
        affect_band:    Current affect band string.

    Returns:
        Emotional guidance string for the WEAVE scenario template.
    """
    if emotional_gate == EMOTIONAL_GATE_SUPPRESS_ALL_NON_SAFETY:
        return (
            "User is in crisis. Only safety-critical results should be "
            "presented. Be extremely gentle and brief."
        )

    if emotional_gate == EMOTIONAL_GATE_SUPPRESS_TRIVIAL:
        return (
            "User affect is negative -- be gentle, acknowledge their "
            "state before presenting this result. Use a compassionate "
            "tone and frame the result as reducing their burden."
        )

    if affect_valence < -0.2:
        band_note = f" (affect: {affect_band})" if affect_band else ""
        return (
            f"User mood is somewhat low{band_note}. Present results "
            "warmly and supportively, avoiding overly enthusiastic tone."
        )

    if affect_valence > 0.5:
        return (
            "User affect is positive. Standard weave -- you can be "
            "upbeat when sharing these results."
        )

    return "User affect is neutral. Standard weave delivery."


# =====================================================================
# Module exports
# =====================================================================

__all__ = [
    # Constants (8.1.3)
    "IDLE_EAGER_MS",
    "IDLE_BATCH_MS",
    "TYPING_SUPPRESS_MS",
    # Emotional gate values (8.1.5)
    "EMOTIONAL_GATE_OPEN",
    "EMOTIONAL_GATE_SUPPRESS_TRIVIAL",
    "EMOTIONAL_GATE_SUPPRESS_ALL_NON_SAFETY",
    "EMOTIONAL_SUPPRESS_VALENCE",
    # UserActivityTracker (8.1.2, 8.1.3)
    "UserActivityTracker",
    # WeaveDecision enum + result (8.2.1)
    "WeaveDecision",
    "WeaveDecisionResult",
    # WeavePolicy (8.2.2)
    "WeavePolicy",
    # WeaveSignal (8.1.1)
    "WeaveSignal",
    # 8.3.1 -- Dynamic batch window
    "schedule_weave_flush",
    # 8.3.3 -- DigestPayload
    "DigestPayload",
    # 8.3.4 -- Urgency + emotional labels
    "generate_urgency_label",
    "generate_emotional_context",
    # 8.3.5 -- Result ordering
    "sort_results_for_delivery",
    # 8.4.1 -- WeaveIntegrationRouter
    "WeaveIntegrationRouter",
    "RoutingResult",
    # 8.4.2 -- TypingPolicyReEvaluator
    "TypingPolicyReEvaluator",
    "ReEvalResult",
    # 8.4.3 -- WeaveFallbackHandler
    "WeaveFallbackHandler",
    # 8.4.4 -- WeaveMetricsCollector
    "WeaveMetricsCollector",
    # 8.4.5 -- WeaveQueue
    "WeaveQueue",
    # Helpers (8.1.4, 8.1.5) -- exposed for testing
    "_profile_urgency",
    "_has_critical",
    "_get_affect_dict_from_ss",
    "_compute_emotional_gate",
    # 8.3.3/8.3.5 helpers -- exposed for testing
    "_extract_domain",
    "_one_line_summary",
    "_result_sort_key",
    # 8.4.3 fallback constants -- exposed for testing
    "_ACTION_TO_DECISION",
    "_FALLBACK_WINDOW_MS",
]
