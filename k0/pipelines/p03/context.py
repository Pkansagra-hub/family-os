"""
P03CycleContext - Immutable batch-level context set during R0.

This module implements the frozen dataclass that holds all batch metadata.
These fields NEVER change after R0 completes.

Spec Reference: docs/pipelines/P03_envelope_fields_discovery.md section 15.2

Issue 1.3.5: Added R0TriggerInputs for explicit trigger-to-R0 plumbing.

TIMESTAMP CONVENTION (LOCKED):
    All `*_at` and `*_ms` fields in P03 use MILLISECONDS since Unix epoch.
    Do NOT use seconds. Do NOT add `*_at` fields that use seconds.
    Examples: triggered_at=1735600000000 (ms), deadline_ms=300000 (ms)

TRACE ID CONVENTION (LOCKED):
    P03 uses `trace_id` as the cognitive trace identifier.
    This is the same as `cognitive_trace_id` used elsewhere in K0/K1.
    All observability, logging, and correlation should use this field.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, List, Optional, Tuple

if TYPE_CHECKING:
    pass


def generate_ulid() -> str:
    """
    Generate a ULID-like identifier.

    Format: 26-character string (10 timestamp + 16 random)
    Uses Crockford's base32 encoding for timestamp portion.

    This is a lightweight implementation that maintains ULID properties:
    - Lexicographically sortable by time
    - Unique across distributed systems (128 bits of randomness)

    Note: This does NOT guarantee strict monotonicity within the same
    millisecond. For M1 purposes (cycle IDs, trace IDs), this is sufficient.
    Consider switching to a strict ULID library if stronger guarantees needed.

    Returns:
        26-character ULID-like string
    """
    # Crockford's base32 alphabet (excludes I, L, O, U)
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

    # Timestamp portion: 48 bits (milliseconds since epoch)
    ts_ms = int(time.time() * 1000)
    ts_chars = []
    for _ in range(10):
        ts_chars.append(alphabet[ts_ms & 0x1F])
        ts_ms >>= 5
    ts_part = "".join(reversed(ts_chars))

    # Random portion: 80 bits (16 characters)
    rand_bytes = secrets.token_bytes(10)
    rand_int = int.from_bytes(rand_bytes, "big")
    rand_chars = []
    for _ in range(16):
        rand_chars.append(alphabet[rand_int & 0x1F])
        rand_int >>= 5
    rand_part = "".join(reversed(rand_chars))

    return ts_part + rand_part


@dataclass(frozen=True)
class P03CycleContext:
    """
    Immutable batch-level context set during R0.

    These fields NEVER change after R0 completes.
    Use frozen=True to enforce immutability at runtime.

    INVARIANTS:
        - batch_size == len(event_ids) (always, enforced by create())
        - event_ids contains NO duplicates (enforced by create())
        - event_ids is sorted (deterministic batch_id)
        - All timestamps are in MILLISECONDS

    Attributes:
        cycle_id: ULID uniquely identifying this consolidation cycle
        batch_id: Deterministic hash of sorted unique event IDs (SHA256[:16])
        tenant_id: Multi-tenant isolation identifier
        space_id: User/family space identifier
        trace_id: Cognitive trace identifier for observability (= cognitive_trace_id)
        trigger_type: What initiated this cycle (INTERVAL/THRESHOLD/MANUAL/IDLE)
        trigger_reason: Human-readable description of trigger
        triggered_at: Unix timestamp in MILLISECONDS when trigger fired
        batch_size: Number of unique events in batch (== len(event_ids))
        event_ids: Immutable tuple of unique event ULIDs (sorted, deduplicated)
        pending_before: Count of pending events before selection
        scheduler_token: QoS scheduler token from K0 (optional)
        qos_band: Quality-of-service band (GREEN/AMBER/RED)
        priority: Batch priority 0-100 (higher = more urgent)
        deadline_ms: Hard deadline for cycle completion in MILLISECONDS
    """

    # === IDENTIFICATION ===
    cycle_id: str
    batch_id: str
    tenant_id: str
    space_id: str
    trace_id: str  # This IS the cognitive_trace_id for P03

    # === TRIGGER CONTEXT ===
    trigger_type: str  # INTERVAL / THRESHOLD / MANUAL / IDLE
    trigger_reason: str
    triggered_at: int  # MILLISECONDS since Unix epoch

    # === BATCH METADATA ===
    batch_size: int  # INVARIANT: == len(event_ids)
    event_ids: Tuple[str, ...]  # Sorted, deduplicated, immutable
    pending_before: int

    # === SCHEDULER CONTEXT ===
    scheduler_token: Optional[str] = None
    qos_band: str = "AMBER"  # GREEN / AMBER / RED
    priority: int = 50  # 0-100
    deadline_ms: int = 300000  # 5 minutes default, in MILLISECONDS

    @classmethod
    def create(
        cls,
        tenant_id: str,
        space_id: str,
        event_ids: List[str],
        trigger_type: str = "MANUAL",
        trigger_reason: str = "",
        trace_id: Optional[str] = None,
        pending_before: int = 0,
        scheduler_token: Optional[str] = None,
        qos_band: str = "AMBER",
        priority: int = 50,
        deadline_ms: int = 300000,
    ) -> P03CycleContext:
        """
        Factory method for creating cycle context.

        Generates cycle_id (ULID), batch_id (deterministic hash),
        and triggered_at timestamp (MILLISECONDS) automatically.

        IMPORTANT: Duplicates in event_ids are silently removed.
        batch_size will reflect the unique count.

        Args:
            tenant_id: Multi-tenant isolation identifier
            space_id: User/family space identifier
            event_ids: List of event ULIDs to process (duplicates removed, sorted)
            trigger_type: Trigger classification (INTERVAL/THRESHOLD/MANUAL/IDLE)
            trigger_reason: Human-readable trigger description
            trace_id: Cognitive trace ID (auto-generated if None)
            pending_before: Total pending events before selection
            scheduler_token: K0 scheduler QoS token
            qos_band: Quality-of-service band (GREEN/AMBER/RED)
            priority: Batch priority 0-100
            deadline_ms: Hard deadline in MILLISECONDS

        Returns:
            Frozen P03CycleContext instance

        Example:
            >>> ctx = P03CycleContext.create(
            ...     tenant_id="tenant-001",
            ...     space_id="family-abc",
            ...     event_ids=["01JFXYZ...", "01JFXYZ..."],
            ...     trigger_type="INTERVAL",
            ...     trigger_reason="Scheduled 4-hour consolidation",
            ... )
            >>> ctx.batch_id  # deterministic hash
            'a1b2c3d4e5f67890'
        """
        # INVARIANT: Deduplicate and sort event IDs
        # This ensures batch_size == len(event_ids) always
        unique_sorted_ids = sorted(set(event_ids))

        # Compute deterministic batch_id: SHA256(comma-joined sorted unique IDs)[:16]
        batch_hash = hashlib.sha256(",".join(unique_sorted_ids).encode()).hexdigest()[:16]

        # All timestamps in MILLISECONDS
        now_ms = int(time.time() * 1000)

        return cls(
            cycle_id=generate_ulid(),
            batch_id=batch_hash,
            tenant_id=tenant_id,
            space_id=space_id,
            trace_id=trace_id or generate_ulid(),
            trigger_type=trigger_type,
            trigger_reason=trigger_reason,
            triggered_at=now_ms,
            batch_size=len(unique_sorted_ids),  # INVARIANT: matches len(event_ids)
            event_ids=tuple(unique_sorted_ids),
            pending_before=pending_before,
            scheduler_token=scheduler_token,
            qos_band=qos_band,
            priority=priority,
            deadline_ms=deadline_ms,
        )

    def remaining_deadline_ms(self) -> int:
        """
        Calculate remaining time until deadline.

        Returns:
            Milliseconds remaining (negative if deadline passed)
        """
        now_ms = int(time.time() * 1000)
        elapsed_ms = now_ms - self.triggered_at
        return self.deadline_ms - elapsed_ms

    def is_deadline_exceeded(self) -> bool:
        """Check if the deadline has been exceeded."""
        return self.remaining_deadline_ms() < 0

    def contains_event(self, event_id: str) -> bool:
        """Check if event_id is in this batch."""
        return event_id in self.event_ids


@dataclass(frozen=True)
class P03ManualTriggerOptions:
    """
    Options for P03 manual trigger API.

    These options are passed via TriggerEvent.context when a manual trigger
    is fired via the admin API.

    Spec Reference: docs/pipelines/P03_consolidation_dossier_v2.md Appendix D.5.3

    API Endpoint:
        POST /k0/admin/pipelines/P03_CONSOLIDATION/trigger
        {
            "reason": "Manual consolidation before demo",
            "options": {
                "skip_r5": false,
                "max_events": 1000,
                "space_id": null,
                "tenant_id": null
            }
        }

    Attributes:
        reason: Human-readable reason for manual trigger (required for audit)
        skip_r5: If True, skip R5 dream exploration phase
        max_events: Override default batch size limit (None = use default)
        space_id: Target specific space for debug/testing (None = all spaces)
        tenant_id: Target specific tenant for debug/testing (None = all tenants)
    """

    reason: str
    skip_r5: bool = False
    max_events: Optional[int] = None
    space_id: Optional[str] = None
    tenant_id: Optional[str] = None

    @classmethod
    def from_trigger_context(cls, context: dict) -> "P03ManualTriggerOptions":
        """
        Parse P03ManualTriggerOptions from TriggerEvent.context.

        Args:
            context: The context dict from TriggerEvent

        Returns:
            P03ManualTriggerOptions with parsed values

        Example context:
            {
                "reason": "Manual consolidation",
                "options": {
                    "skip_r5": True,
                    "max_events": 500
                }
            }
        """
        options = context.get("options", {})
        return cls(
            reason=context.get("reason", "Manual trigger (no reason provided)"),
            skip_r5=options.get("skip_r5", False),
            max_events=options.get("max_events"),
            space_id=options.get("space_id"),
            tenant_id=options.get("tenant_id"),
        )

    def to_dict(self) -> dict:
        """Convert to dict for serialization."""
        return {
            "reason": self.reason,
            "options": {
                "skip_r5": self.skip_r5,
                "max_events": self.max_events,
                "space_id": self.space_id,
                "tenant_id": self.tenant_id,
            },
        }

    def should_skip_r5(self) -> bool:
        """Check if R5 should be skipped based on options."""
        return self.skip_r5

    def get_effective_batch_size(self, default_batch_size: int) -> int:
        """Get effective batch size, using max_events if set."""
        if self.max_events is not None and self.max_events > 0:
            return min(self.max_events, default_batch_size)
        return default_batch_size


# =============================================================================
# R0 Trigger Inputs (Issue 1.3.5)
# =============================================================================


class BackpressureAction:
    """
    Backpressure actions for R0 batch selection.

    Used when the system is under load or capacity constraints.
    """

    SELECT_FULL = "select_full"  # Select up to max_events
    SELECT_REDUCED = "select_reduced"  # Select smaller batch due to constraints
    DEFER = "defer"  # Defer to next trigger


@dataclass(frozen=True)
class R0TriggerInputs:
    """
    All trigger-derived inputs for R0 batch selection.

    Issue 1.3.5: Make batch selection (R0) explicitly parameterized
    by trigger and resource context.

    These inputs are extracted from TriggerEvent, TriggerSpec, and QoS context
    at the start of a consolidation cycle and used by R0 to determine:
    - How many events to select
    - What priority/deadline to apply
    - Whether to defer if under backpressure

    Spec Reference: docs/pipelines/P03_consolidation_dossier_v2.md Appendix D.5.1

    INVARIANT: All fields have sensible defaults for deterministic behavior.

    Attributes:
        trigger_type: What initiated this cycle (INTERVAL/THRESHOLD/MANUAL/IDLE)
        trigger_reason: Human-readable description of trigger
        trigger_id: ID of the trigger that fired
        fired_at_ms: When trigger fired (MILLISECONDS since epoch)
        max_events: Override batch size limit (from manual context)
        threshold_count: Pending count that triggered (for THRESHOLD type)
        batch_size: Default batch size from TriggerSpec config
        deadline_ms: Hard deadline for cycle completion (MILLISECONDS)
        qos_band: Quality-of-service band (GREEN/AMBER/RED)
        skip_r5: Whether to skip R5 dream exploration (manual option)
        target_space_id: Target specific space (manual option, None = all)
        target_tenant_id: Target specific tenant (manual option, None = all)
    """

    # Trigger identification
    trigger_type: str  # INTERVAL / THRESHOLD / MANUAL / IDLE
    trigger_reason: str
    trigger_id: str
    fired_at_ms: int  # MILLISECONDS since epoch

    # Batch sizing inputs
    max_events: Optional[int] = None  # Manual override
    threshold_count: Optional[int] = None  # For THRESHOLD triggers
    batch_size: int = 500  # Default from TriggerSpec

    # Deadline/QoS inputs
    deadline_ms: int = 300000  # 5 minutes default
    qos_band: str = "AMBER"  # GREEN / AMBER / RED

    # Manual trigger options
    skip_r5: bool = False
    target_space_id: Optional[str] = None
    target_tenant_id: Optional[str] = None

    @classmethod
    def from_trigger_event(
        cls,
        trigger_type: str,
        trigger_id: str,
        fired_at_ms: int,
        context: Optional[dict] = None,
        batch_size: int = 500,
        threshold_count: Optional[int] = None,
        deadline_ms: int = 300000,
        qos_band: str = "AMBER",
    ) -> "R0TriggerInputs":
        """
        Factory method to create R0TriggerInputs from trigger event data.

        This is the primary constructor used by the P03 runner when starting
        a consolidation cycle.

        Args:
            trigger_type: INTERVAL / THRESHOLD / MANUAL / IDLE
            trigger_id: ID of the trigger that fired
            fired_at_ms: Monotonic timestamp when trigger fired (MILLISECONDS)
            context: Optional context dict from TriggerEvent
            batch_size: Default batch size from TriggerSpec
            threshold_count: For THRESHOLD triggers, the count that triggered
            deadline_ms: Hard deadline in MILLISECONDS
            qos_band: QoS band (GREEN/AMBER/RED)

        Returns:
            Frozen R0TriggerInputs instance
        """
        context = context or {}

        # Extract manual trigger options if present
        manual_options = None
        if trigger_type.upper() == "MANUAL" and context:
            manual_options = P03ManualTriggerOptions.from_trigger_context(context)

        # Determine trigger reason
        if manual_options:
            trigger_reason = manual_options.reason
        elif "reason" in context:
            trigger_reason = context["reason"]
        else:
            trigger_reason = cls._default_reason(trigger_type, threshold_count)

        return cls(
            trigger_type=trigger_type.upper(),
            trigger_reason=trigger_reason,
            trigger_id=trigger_id,
            fired_at_ms=fired_at_ms,
            max_events=manual_options.max_events if manual_options else None,
            threshold_count=threshold_count,
            batch_size=batch_size,
            deadline_ms=deadline_ms,
            qos_band=qos_band,
            skip_r5=manual_options.skip_r5 if manual_options else False,
            target_space_id=manual_options.space_id if manual_options else None,
            target_tenant_id=manual_options.tenant_id if manual_options else None,
        )

    @staticmethod
    def _default_reason(trigger_type: str, threshold_count: Optional[int]) -> str:
        """Generate default trigger reason based on type."""
        trigger_type = trigger_type.upper()
        if trigger_type == "INTERVAL":
            return "Scheduled interval consolidation"
        elif trigger_type == "THRESHOLD":
            count = threshold_count or "N"
            return f"Threshold reached: {count} pending events"
        elif trigger_type == "MANUAL":
            return "Manual trigger (no reason provided)"
        elif trigger_type == "IDLE":
            return "System idle with pending events"
        else:
            return f"Unknown trigger type: {trigger_type}"

    def get_effective_batch_size(self) -> int:
        """
        Get effective batch size considering all inputs.

        Priority order (lowest wins):
        1. max_events (manual override) if set
        2. batch_size (from TriggerSpec)

        Returns:
            Effective batch size for R0 selection
        """
        if self.max_events is not None and self.max_events > 0:
            return min(self.max_events, self.batch_size)
        return self.batch_size

    def should_skip_r5(self) -> bool:
        """Check if R5 dream exploration should be skipped."""
        return self.skip_r5

    def has_space_filter(self) -> bool:
        """Check if a specific space is targeted."""
        return self.target_space_id is not None

    def has_tenant_filter(self) -> bool:
        """Check if a specific tenant is targeted."""
        return self.target_tenant_id is not None

    def evaluate_backpressure(self, pending_count: int, available_capacity: int) -> str:
        """
        Evaluate backpressure and return recommended action.

        Backpressure Policy (from Issue 1.3.5):
        | Scenario                      | Action          |
        |-------------------------------|-----------------|
        | Backlog large, capacity OK    | SELECT_FULL     |
        | Backlog large, capacity limited| SELECT_REDUCED  |
        | No capacity / QoS fail        | DEFER           |

        Args:
            pending_count: Number of pending events
            available_capacity: Available processing capacity (e.g., tokens)

        Returns:
            BackpressureAction value
        """
        if available_capacity <= 0:
            return BackpressureAction.DEFER

        effective_batch = self.get_effective_batch_size()

        if pending_count <= available_capacity:
            return BackpressureAction.SELECT_FULL

        if available_capacity >= effective_batch // 2:
            return BackpressureAction.SELECT_REDUCED

        return BackpressureAction.DEFER

    def to_dict(self) -> dict:
        """Convert to dict for serialization/logging."""
        return {
            "trigger_type": self.trigger_type,
            "trigger_reason": self.trigger_reason,
            "trigger_id": self.trigger_id,
            "fired_at_ms": self.fired_at_ms,
            "max_events": self.max_events,
            "threshold_count": self.threshold_count,
            "batch_size": self.batch_size,
            "deadline_ms": self.deadline_ms,
            "qos_band": self.qos_band,
            "skip_r5": self.skip_r5,
            "target_space_id": self.target_space_id,
            "target_tenant_id": self.target_tenant_id,
            "effective_batch_size": self.get_effective_batch_size(),
        }


# =============================================================================
# Issue 1.3.6: QoS Integration Classes
# =============================================================================


class P03QoSError(Exception):
    """Base exception for P03 QoS-related errors."""

    pass


class P03CapacityError(P03QoSError):
    """
    Raised when scheduler capacity is exhausted.

    Appropriate action: DEFER the cycle and retry later.
    """

    def __init__(
        self,
        band: str,
        port: str,
        cost: float,
        limit: int,
        message: str = "Scheduler capacity exhausted",
    ):
        self.band = band
        self.port = port
        self.cost = cost
        self.limit = limit
        super().__init__(f"{message}: band={band}, port={port}, cost={cost}, limit={limit}")


class P03BudgetExhaustedError(P03QoSError):
    """
    Raised when QoS budgets (fanout or top_k) are exhausted.

    Appropriate action: Stop or reduce processing scope.
    """

    def __init__(self, budget_type: str, requested: int, remaining: int):
        self.budget_type = budget_type
        self.requested = requested
        self.remaining = remaining
        super().__init__(
            f"{budget_type} budget exhausted: requested={requested}, remaining={remaining}"
        )


@dataclass
class P03QoSIntegration:
    """
    P03-specific QoS integration for scheduler token lifecycle and budget enforcement.

    Implements the dossier section 15.2 P03SchedulerIntegration pattern:
    - Token acquisition at cycle start (R0)
    - Token release in all exit paths (try/finally)
    - Budget enforcement at phase boundaries

    Attributes:
        scheduler: K0 Scheduler instance for token acquisition
        port: Scheduler port name (default: "command" for P03)
        default_band: Default QoS band if not specified (default: "GREEN")
        default_fanout_budget: Default fanout budget (default: 1000)
        default_top_k_budget: Default top_k budget (default: 500)

    Usage:
        qos = P03QoSIntegration(scheduler=k0_scheduler)

        # At R0 start
        token = qos.acquire_batch_token(batch_size=50, band="GREEN")
        try:
            # ... cycle processing ...
            qos.consume_fanout(10)  # During fanout operations
            qos.consume_top_k(5)    # During top-k operations
        finally:
            qos.release_token(token)
    """

    scheduler: Any = None  # K0 Scheduler or compatible duck-typed mock
    port: str = "command"
    default_band: str = "GREEN"
    default_fanout_budget: int = 1000
    default_top_k_budget: int = 500

    # Internal state
    _active_token: Any = field(default=None, init=False, repr=False)
    _fanout_budget: int = field(default=0, init=False, repr=False)
    _top_k_budget: int = field(default=0, init=False, repr=False)
    _token_acquired: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        """Initialize budgets to defaults."""
        self._fanout_budget = self.default_fanout_budget
        self._top_k_budget = self.default_top_k_budget

    @property
    def fanout_budget(self) -> int:
        """Current remaining fanout budget."""
        return self._fanout_budget

    @property
    def top_k_budget(self) -> int:
        """Current remaining top_k budget."""
        return self._top_k_budget

    @property
    def has_active_token(self) -> bool:
        """Check if a scheduler token is currently held (or unbounded mode active)."""
        return self._token_acquired

    def acquire_batch_token(
        self,
        batch_size: int,
        band: Optional[str] = None,
        cost_multiplier: float = 0.1,
    ) -> Any:
        """
        Acquire a scheduler token for the batch.

        Cost is calculated as: batch_size * cost_multiplier

        Args:
            batch_size: Number of events in the batch
            band: QoS band (GREEN/AMBER/RED), uses default_band if None
            cost_multiplier: Multiplier for cost calculation (default: 0.1)

        Returns:
            SchedulerToken if scheduler is configured, None otherwise

        Raises:
            P03CapacityError: If scheduler capacity is exhausted
            ValueError: If a token is already held (must release first)
        """
        if self._token_acquired:
            raise ValueError("Token already held - must release before acquiring new token")

        if self.scheduler is None:
            # No scheduler configured - operate in unbounded mode
            self._token_acquired = True
            return None

        effective_band = band or self.default_band
        cost = int(batch_size * cost_multiplier)

        try:
            # Import here to avoid circular dependency at module load
            from k0.qos import SchedulerCapacityError

            token = self.scheduler.acquire(
                band=effective_band,
                port=self.port,
                cost=max(1, cost),  # Minimum cost of 1
            )
            self._active_token = token
            self._token_acquired = True
            return token
        except SchedulerCapacityError as e:
            raise P03CapacityError(
                band=effective_band,
                port=self.port,
                cost=cost,
                limit=getattr(e, "limit", 0),
            ) from e

    def release_token(self, token: Any = None) -> None:
        """
        Release the scheduler token.

        Safe to call even if no token is held - will be a no-op.

        Args:
            token: Token to release (uses internal token if None)
        """
        target_token = token or self._active_token

        if target_token is not None:
            try:
                target_token.release()
            except Exception:
                # Best effort - token may already be released
                pass

        self._active_token = None
        self._token_acquired = False

    def check_fanout_budget(self, amount: int) -> bool:
        """
        Check if fanout budget allows the requested amount.

        Args:
            amount: Amount of fanout budget to check

        Returns:
            True if budget allows, False otherwise
        """
        return amount <= self._fanout_budget

    def check_top_k_budget(self, amount: int) -> bool:
        """
        Check if top_k budget allows the requested amount.

        Args:
            amount: Amount of top_k budget to check

        Returns:
            True if budget allows, False otherwise
        """
        return amount <= self._top_k_budget

    def consume_fanout(self, amount: int) -> None:
        """
        Consume from the fanout budget.

        Args:
            amount: Amount to consume

        Raises:
            P03BudgetExhaustedError: If budget is insufficient
            ValueError: If amount is negative
        """
        if amount < 0:
            raise ValueError("Fanout amount must be non-negative")

        if amount > self._fanout_budget:
            raise P03BudgetExhaustedError(
                budget_type="fanout",
                requested=amount,
                remaining=self._fanout_budget,
            )

        self._fanout_budget -= amount

    def consume_top_k(self, amount: int) -> None:
        """
        Consume from the top_k budget.

        Args:
            amount: Amount to consume

        Raises:
            P03BudgetExhaustedError: If budget is insufficient
            ValueError: If amount is negative
        """
        if amount < 0:
            raise ValueError("Top_k amount must be non-negative")

        if amount > self._top_k_budget:
            raise P03BudgetExhaustedError(
                budget_type="top_k",
                requested=amount,
                remaining=self._top_k_budget,
            )

        self._top_k_budget -= amount

    def tighten_budgets(
        self,
        fanout: Optional[int] = None,
        top_k: Optional[int] = None,
    ) -> None:
        """
        Tighten budgets to lower values (cannot increase).

        Args:
            fanout: New fanout budget (only applied if lower than current)
            top_k: New top_k budget (only applied if lower than current)
        """
        if fanout is not None and fanout >= 0:
            self._fanout_budget = min(self._fanout_budget, fanout)
        if top_k is not None and top_k >= 0:
            self._top_k_budget = min(self._top_k_budget, top_k)

    def reset_budgets(self) -> None:
        """Reset budgets to their default values."""
        self._fanout_budget = self.default_fanout_budget
        self._top_k_budget = self.default_top_k_budget

    def evaluate_capacity_action(self, pending_count: int) -> str:
        """
        Evaluate QoS capacity and return recommended backpressure action.

        Uses the fanout budget as a proxy for available capacity.

        Args:
            pending_count: Number of pending events

        Returns:
            BackpressureAction value (SELECT_FULL, SELECT_REDUCED, DEFER)
        """
        if self._fanout_budget <= 0:
            return BackpressureAction.DEFER

        if pending_count <= self._fanout_budget:
            return BackpressureAction.SELECT_FULL

        if self._fanout_budget >= pending_count // 2:
            return BackpressureAction.SELECT_REDUCED

        return BackpressureAction.DEFER

    def to_dict(self) -> dict:
        """Convert current state to dict for logging/observability."""
        return {
            "port": self.port,
            "default_band": self.default_band,
            "has_scheduler": self.scheduler is not None,
            "has_active_token": self.has_active_token,
            "fanout_budget": self._fanout_budget,
            "top_k_budget": self._top_k_budget,
            "default_fanout_budget": self.default_fanout_budget,
            "default_top_k_budget": self.default_top_k_budget,
        }

    def __enter__(self) -> P03QoSIntegration:
        """Context manager entry - for use with with statement."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - ensures token is released."""
        self.release_token()


@dataclass(frozen=True)
class P03QoSSnapshot:
    """
    Immutable snapshot of QoS state at a point in time.

    Useful for logging, observability, and debugging.
    Captures budgets and token state at creation time.
    """

    fanout_budget: int
    top_k_budget: int
    has_active_token: bool
    port: str
    band: str
    captured_at_ms: int

    @classmethod
    def capture(cls, qos: P03QoSIntegration, band: str = "GREEN") -> P03QoSSnapshot:
        """
        Capture a snapshot of the current QoS state.

        Args:
            qos: P03QoSIntegration instance to capture
            band: Current QoS band

        Returns:
            Frozen snapshot of QoS state
        """
        return cls(
            fanout_budget=qos.fanout_budget,
            top_k_budget=qos.top_k_budget,
            has_active_token=qos.has_active_token,
            port=qos.port,
            band=band,
            captured_at_ms=int(time.time() * 1000),
        )
