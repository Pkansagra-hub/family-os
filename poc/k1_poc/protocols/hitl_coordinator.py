"""
poc.k1_poc.protocols.hitl_coordinator -- FSM-side HITL orchestration.

V2 Design Ref: Section 9.1 (HITL Closed Cycle -- all 8 steps)
V2 Design Ref: Section 9.2 (Three shapes: clarification, approval, selection)
V2 Design Ref: Section 9.3 (Safety Band Escalation)
V2 Design Ref: Section 9.4 (Front HITL_RELAY / HITL_RESOLVE modes)
V2 Design Ref: Section 9.5 (Suspension Rules, Timeouts, Persistence)
V2 Design Ref: Section 9.6 (Crash Recovery Protocol)
V2 Design Ref: Section 9.8 (Defense-in-Depth FSM Enforcement L2)
V2 Design Ref: Section 9.10 (HITL Invariants)

Epic 13.2: HILCoordinator.

The HILCoordinator is the FSM-side component that orchestrates the
HITL closed cycle.  It:

    1. Receives Back's submit_result(needs_human) via handle_needs_human().
    2. Validates safety band escalation (GREEN+side_effects -> AMBER).
    3. Checks suspension limits (max 2 per task).
    4. Builds HILRequest and persists to task_state.pending_hil.
    5. Delegates to SuspensionManager for timeout management.
    6. Emits task.suspended.v1 via bus callback.
    7. Handles user response via handle_user_response().
    8. Builds HILResponse, clears persistence, emits task.resume.v1.

Crash recovery (V2 Section 9.6):
    On startup, recover_pending_hitl() scans task_state for SUSPENDED
    entries with pending_hil.  For each: check timeout, re-present or
    auto-cancel.

Defense-in-depth L2 (V2 Section 9.8):
    validate_before_invoke() checks capability contracts for side_effects
    and safety_band before allowing invoke_capability calls through.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from poc.k1_poc.config import get_config
from poc.k1_poc.protocols.hitl import (
    HILRequest,
    HILResponse,
    SafetyBand,
    _get_hil_timeouts,
    escalate_safety_band,
)
from poc.k1_poc.protocols.suspension import (
    SuspensionLimitExceeded,
    SuspensionRequest,
    SuspensionResolution,
    SuspensionType,
)
from poc.k1_poc.protocols.suspension_manager import SuspensionManager

logger = logging.getLogger(__name__)

# Maps hil_type -> SuspensionType for SuspensionManager delegation
HIL_TO_SUSPENSION: dict[str, SuspensionType] = {
    "clarification": SuspensionType.CLARIFICATION,
    "approval": SuspensionType.APPROVAL,
    "selection": SuspensionType.SELECTION,
}


def _config_max_rounds() -> int:
    """Read max HITL rounds per task from central config."""
    return get_config().protocols.max_suspensions_per_task


@dataclass
class HILCoordinatorConfig:
    """Configuration for HILCoordinator behavior.

    V3 E0.2.1/E0.2.2: defaults now read from central config at
    construction time instead of importing module-level constants.

    Attributes:
        max_rounds:         Max HITL rounds per task (from config).
        timeouts:           Per-type timeout in seconds (from config).
        block_red:          Whether to block RED safety band (default True).
        auto_escalate_side_effects: Whether GREEN+side_effects -> AMBER.
    """

    max_rounds: int = field(default_factory=_config_max_rounds)
    timeouts: dict[str, float] = field(default_factory=_get_hil_timeouts)
    block_red: bool = True
    auto_escalate_side_effects: bool = True


class HILCoordinator:
    """Orchestrates the HITL closed cycle from the FSM side.

    V2 Design Ref: Section 9.1 (Closed Cycle steps 2-8)
    V2 Design Ref: Section 9.5 (Suspension Manager delegation)
    V2 Design Ref: Section 9.6 (Crash Recovery via pending_hil)

    The coordinator sits between Back's submit_result(needs_human) and
    Front's HITL_RELAY/HITL_RESOLVE modes.  It handles:
        - Safety band validation and escalation
        - Suspension limit enforcement
        - HILRequest construction and persistence
        - SuspensionManager delegation for timeouts
        - HILResponse construction on user answer
        - Crash recovery of pending HITL from task_state

    Callbacks:
        on_emit_suspended:  Called to emit task.suspended.v1 on bus.
        on_emit_resume:     Called to emit task.resume.v1 on bus.
        on_timeout:         Called when HITL timeout fires.
        on_blocked_red:     Called when RED safety band blocks execution.

    Attributes:
        _config:            Coordinator configuration.
        _suspension_mgr:    SuspensionManager instance for timeout management.
        _pending_requests:  Active HILRequests by task_id.
        _hil_counts:        HITL round counts per task_id.
        _on_emit_suspended: Callback for bus emission.
        _on_emit_resume:    Callback for bus emission.
        _on_timeout:        Callback for HITL timeout.
        _on_blocked_red:    Callback for RED band blocking.
    """

    __slots__ = (
        "_config",
        "_suspension_mgr",
        "_pending_requests",
        "_hil_counts",
        "_on_emit_suspended",
        "_on_emit_resume",
        "_on_timeout",
        "_on_blocked_red",
    )

    def __init__(
        self,
        config: HILCoordinatorConfig | None = None,
        on_emit_suspended: Callable[[HILRequest], Awaitable[None]] | None = None,
        on_emit_resume: Callable[[HILResponse], Awaitable[None]] | None = None,
        on_timeout: Callable[[str], Awaitable[None]] | None = None,
        on_blocked_red: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> None:
        self._config = config or HILCoordinatorConfig()
        self._pending_requests: dict[str, HILRequest] = {}
        self._hil_counts: dict[str, int] = {}
        self._on_emit_suspended = on_emit_suspended
        self._on_emit_resume = on_emit_resume
        self._on_timeout = on_timeout
        self._on_blocked_red = on_blocked_red

        # Create SuspensionManager with our timeout handler
        self._suspension_mgr = SuspensionManager(
            on_timeout_fn=self._handle_timeout,
            on_resume_fn=None,  # We handle resume directly
        )
        logger.info(
            "HILCoordinator initialised  max_rounds=%d block_red=%s auto_escalate=%s",
            self._config.max_rounds,
            self._config.block_red,
            self._config.auto_escalate_side_effects,
        )

    # -----------------------------------------------------------------
    # Public API -- Back -> FSM flow
    # -----------------------------------------------------------------

    async def handle_needs_human(
        self,
        task_id: str,
        hil_type: str,
        question: str,
        options: list[dict[str, Any]] | None = None,
        side_effects: list[str] | None = None,
        context: dict[str, Any] | None = None,
        safety_band: SafetyBand | str = SafetyBand.GREEN,
        react_history: list[dict[str, Any]] | None = None,
    ) -> HILRequest:
        """Process Back's submit_result(needs_human) call.

        V2 Design Ref: Section 9.1 (Steps 1-5)
        V2 Design Ref: Section 9.3 (Safety Band Escalation)
        V2 Design Ref: Section 9.5 (Suspension Limits)

        Flow:
            1. Validate and escalate safety band.
            2. Check RED band -> block if configured.
            3. Check suspension limits (max 2 per task).
            4. Build HILRequest with type-specific timeout.
            5. Persist to _pending_requests.
            6. Delegate to SuspensionManager for timeout.
            7. Invoke on_emit_suspended callback.

        Args:
            task_id:       The task requesting HITL.
            hil_type:      One of: clarification, approval, selection.
            question:      The question for the user.
            options:       Structured options (selection/approval).
            side_effects:  Side effects to present (approval).
            context:       Additional context (capability, params).
            safety_band:   Safety band from capability contract.
            react_history: Serialized ReAct history for resume.

        Returns:
            The constructed HILRequest.

        Raises:
            SuspensionLimitExceeded: If task exceeds max suspensions.
            ValueError: If safety band is RED and block_red is True.
        """
        # Normalize safety band
        if isinstance(safety_band, str):
            safety_band = SafetyBand(safety_band)

        # 1. Safety band escalation
        effective_band = safety_band
        if self._config.auto_escalate_side_effects and side_effects:
            effective_band = escalate_safety_band(safety_band, has_side_effects=True)
            if effective_band != safety_band:
                logger.info(
                    "Task %s: safety band escalated %s -> %s (side_effects present)",
                    task_id,
                    safety_band.value,
                    effective_band.value,
                )

        # 2. RED band check
        if effective_band == SafetyBand.RED and self._config.block_red:
            logger.warning("Task %s: RED safety band, execution blocked", task_id)
            if self._on_blocked_red is not None:
                await self._on_blocked_red(task_id, question)
            raise ValueError(
                f"Task {task_id}: RED safety band blocks execution. "
                f"Capability requires elevated authorization."
            )

        # 3. Check suspension limits
        count = self._hil_counts.get(task_id, 0) + 1
        if count > self._config.max_rounds:
            raise SuspensionLimitExceeded(task_id, count)

        # 4. Build HILRequest
        timeout_ms = self._config.timeouts.get(hil_type, 60_000)
        request = HILRequest(
            task_id=task_id,
            hil_type=hil_type,
            question=question,
            options=options or [],
            context=context or {},
            side_effects=side_effects or [],
            safety_band=effective_band,
            timeout_ms=timeout_ms,
            max_rounds=self._config.max_rounds,
        )

        # 5. Persist
        self._pending_requests[task_id] = request
        self._hil_counts[task_id] = count

        # 6. Delegate to SuspensionManager for timeout
        suspension_type = HIL_TO_SUSPENSION.get(hil_type, SuspensionType.CLARIFICATION)
        suspension_request = SuspensionRequest(
            task_id=task_id,
            suspension_type=suspension_type,
            question=question,
            options=options or [],
            react_history=react_history or [],
            suspension_count=count,
        )
        await self._suspension_mgr.suspend(suspension_request)

        # 7. Emit
        if self._on_emit_suspended is not None:
            await self._on_emit_suspended(request)

        logger.info(
            "Task %s: HITL requested [type=%s, band=%s, round=%d/%d, timeout=%dms]",
            task_id,
            hil_type,
            effective_band.value,
            count,
            self._config.max_rounds,
            timeout_ms,
        )

        return request

    # -----------------------------------------------------------------
    # Public API -- Front -> FSM flow (user answered)
    # -----------------------------------------------------------------

    async def handle_user_response(
        self,
        task_id: str,
        decision: str = "answered",
        resolution: dict[str, Any] | None = None,
        raw_user_text: str = "",
    ) -> HILResponse | None:
        """Process user's response to a HITL question.

        V2 Design Ref: Section 9.1 (Steps 7-8)
        V2 Design Ref: Section 9.4 (HITL_RESOLVE mode)

        Flow:
            1. Resolve the suspension (cancels timeout timer).
            2. Build HILResponse.
            3. Clear _pending_requests.
            4. Invoke on_emit_resume callback.

        Args:
            task_id:        The suspended task.
            decision:       High-level decision (approve/cancel/answered/modify).
            resolution:     Structured resolution payload.
            raw_user_text:  Original user text for audit.

        Returns:
            The constructed HILResponse, or None if task not suspended.
        """
        # 1. Resolve suspension (cancels timeout)
        suspension_resolution = SuspensionResolution(
            task_id=task_id,
            resolution=resolution or {},
            resolution_type=decision,
        )
        original_suspension = await self._suspension_mgr.resolve(suspension_resolution)

        if original_suspension is None:
            logger.warning("Task %s: user response for non-suspended task", task_id)
            return None

        # 2. Build HILResponse
        response = HILResponse(
            task_id=task_id,
            decision=decision,
            resolution=resolution or {},
            raw_user_text=raw_user_text,
        )

        # 3. Clear pending request
        self._pending_requests.pop(task_id, None)

        # 4. Emit resume
        if self._on_emit_resume is not None:
            await self._on_emit_resume(response)

        logger.info("Task %s: HITL resolved [decision=%s]", task_id, decision)

        return response

    # -----------------------------------------------------------------
    # Crash Recovery (V2 Section 9.6)
    # -----------------------------------------------------------------

    async def recover_pending_hitl(
        self,
        task_state: dict[str, dict[str, Any]],
        now_ms: int | None = None,
    ) -> list[str]:
        """Recover pending HITL requests from persisted task_state.

        V2 Design Ref: Section 9.6 (Crash Recovery Protocol)
        V2 Design Ref: Section 9.5 (pending_hil persistence)

        Called on FSM startup/reconnect.  Scans task_state for entries
        with status=SUSPENDED and pending_hil.  For each:
            - If timeout expired: auto-cancel via on_timeout.
            - If still within timeout: re-register for re-presentation.

        Args:
            task_state: Persisted task_state dict from Session State.
            now_ms:     Current time in milliseconds (for testing).

        Returns:
            List of task_ids that were recovered (still within timeout).
        """
        if now_ms is None:
            now_ms = int(time.monotonic_ns() / 1_000_000)

        recovered: list[str] = []
        timed_out: list[str] = []

        for task_id, entry in task_state.items():
            if entry.get("status") != "SUSPENDED":
                continue
            pending = entry.get("pending_hil")
            if pending is None:
                continue

            suspended_at_ms = pending.get("suspended_at_ms", 0)
            timeout_ms = pending.get("timeout_ms", 60_000)
            elapsed = now_ms - suspended_at_ms

            if elapsed >= timeout_ms:
                timed_out.append(task_id)
                logger.warning(
                    "Task %s: HITL timeout during recovery (elapsed=%dms, timeout=%dms)",
                    task_id,
                    elapsed,
                    timeout_ms,
                )
                if self._on_timeout is not None:
                    await self._on_timeout(task_id)
            else:
                # Re-register for re-presentation
                request = HILRequest.from_payload(pending)
                self._pending_requests[task_id] = request
                self._hil_counts[task_id] = entry.get("hil_suspensions_count", 1)
                recovered.append(task_id)
                logger.info(
                    "Task %s: HITL recovered (remaining=%dms)",
                    task_id,
                    timeout_ms - elapsed,
                )

        return recovered

    # -----------------------------------------------------------------
    # Defense-in-Depth L2 (V2 Section 9.8)
    # -----------------------------------------------------------------

    def validate_before_invoke(
        self,
        task_id: str,
        capability_contract: dict[str, Any],
        task_history: list[dict[str, Any]] | None = None,
    ) -> str:
        """L2 defense-in-depth check before invoke_capability.

        V2 Design Ref: Section 9.8 (FSM HITL Enforcement Layer)

        Called by tool dispatcher AFTER Back calls invoke_capability
        but BEFORE actual capability execution.

        Args:
            task_id:             The task requesting invocation.
            capability_contract: Capability contract with has_side_effects, safety_band.
            task_history:        Prior HITL history for this task.

        Returns:
            "allow" -- safe to execute.
            "block_needs_approval" -- side effects without prior approval.
            "block_red" -- RED safety band, never execute.
        """
        safety_band_str = capability_contract.get("safety_band", "AMBER")
        has_side_effects = capability_contract.get("has_side_effects", False)

        # RED: always block
        try:
            band = SafetyBand(safety_band_str)
        except ValueError:
            band = SafetyBand.AMBER  # Default to AMBER for unknown

        if band == SafetyBand.RED:
            logger.warning(
                "Task %s: L2 check -> block_red  capability=%s",
                task_id,
                capability_contract.get("name", "?"),
            )
            return "block_red"

        # Side effects without prior approval: block
        if has_side_effects:
            if not self._has_prior_approval(task_history or []):
                logger.info(
                    "Task %s: L2 check -> block_needs_approval  capability=%s",
                    task_id,
                    capability_contract.get("name", "?"),
                )
                return "block_needs_approval"

        logger.debug(
            "Task %s: L2 check -> allow  capability=%s band=%s",
            task_id,
            capability_contract.get("name", "?"),
            band.value,
        )
        return "allow"

    # -----------------------------------------------------------------
    # Query helpers
    # -----------------------------------------------------------------

    def get_pending_request(self, task_id: str) -> HILRequest | None:
        """Get the active HILRequest for a task."""
        return self._pending_requests.get(task_id)

    def is_pending(self, task_id: str) -> bool:
        """Check if a task has a pending HITL request."""
        return task_id in self._pending_requests

    def get_hil_count(self, task_id: str) -> int:
        """Get the HITL round count for a task."""
        return self._hil_counts.get(task_id, 0)

    @property
    def pending_count(self) -> int:
        """Number of tasks with active HITL requests."""
        return len(self._pending_requests)

    def cleanup_task(self, task_id: str) -> None:
        """Clean up all HITL state for a completed/cancelled task."""
        self._pending_requests.pop(task_id, None)
        self._hil_counts.pop(task_id, None)
        self._suspension_mgr.cleanup_task(task_id)

    # -----------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------

    async def _handle_timeout(self, task_id: str) -> None:
        """Called by SuspensionManager when HITL timeout fires.

        V2 Design Ref: Section 9.5 (Timeout Policy)
        """
        request = self._pending_requests.pop(task_id, None)
        if request is not None:
            logger.warning(
                "Task %s: HITL timeout [type=%s, timeout=%dms]",
                task_id,
                request.hil_type,
                request.timeout_ms,
            )
        if self._on_timeout is not None:
            await self._on_timeout(task_id)

    @staticmethod
    def _has_prior_approval(task_history: list[dict[str, Any]]) -> bool:
        """Check if task has a prior approval in HITL history.

        V2 Design Ref: Section 9.8 (L2 enforcement)
        """
        return any(
            h.get("hil_type") == "approval" and h.get("resolution", {}).get("decision") == "approve"
            for h in task_history
        )
