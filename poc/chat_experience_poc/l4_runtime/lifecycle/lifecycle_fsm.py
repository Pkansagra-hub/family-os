"""
Agent Lifecycle State Machine

Manages agent state transitions with validation, callbacks, and timeout enforcement.
Implements 6-state FSM: PENDING → WARMING → ACTIVE ↔ IDLE → DRAINING → TERMINATED

Related ADRs:
- ADR-0005: Agent Lifecycle FSM
- ADR-0073: WARMING/IDLE/DRAINING enhancements
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List, Optional

from .agent_lifecycle import (
    AgentState,
    StateTransition,
    get_state_metadata,
    log_state_transition,
    validate_state_transition,
)

logger = logging.getLogger(__name__)


@dataclass
class StateCallbacks:
    """
    Callback functions for state entry/exit behaviors

    Agents can override these to customize behavior for each state.
    """

    on_enter_pending: Optional[Callable] = None
    on_exit_pending: Optional[Callable] = None

    on_enter_warming: Optional[Callable] = None
    on_exit_warming: Optional[Callable] = None

    on_enter_active: Optional[Callable] = None
    on_exit_active: Optional[Callable] = None

    on_enter_idle: Optional[Callable] = None
    on_exit_idle: Optional[Callable] = None

    on_enter_draining: Optional[Callable] = None
    on_exit_draining: Optional[Callable] = None

    on_enter_terminated: Optional[Callable] = None
    on_exit_terminated: Optional[Callable] = None


class LifecycleFSM:
    """
    Agent Lifecycle Finite State Machine

    Manages state transitions with:
    - Validation (only allowed transitions)
    - Entry/exit callbacks for each state
    - Timeout enforcement (WARMING, IDLE, DRAINING)
    - State history tracking
    - DeltaBus event emission (future)

    States: PENDING → WARMING → ACTIVE ↔ IDLE → DRAINING → TERMINATED
    """

    def __init__(
        self,
        agent_id: str,
        callbacks: Optional[StateCallbacks] = None,
        initial_state: AgentState = AgentState.PENDING,
    ):
        """
        Initialize lifecycle FSM

        Args:
            agent_id: Unique identifier for the agent
            callbacks: Optional state entry/exit callbacks
            initial_state: Starting state (default: PENDING)
        """
        self.agent_id = agent_id
        self._current_state = initial_state
        self._state_history: List[StateTransition] = []
        self._callbacks = callbacks or StateCallbacks()

        # Timeout tasks for states with timeout enforcement
        self._timeout_tasks: Dict[AgentState, asyncio.Task] = {}

        # Timestamps for observability
        self._state_entry_time: Optional[datetime] = None
        self._last_transition_time: Optional[datetime] = None

        # Initialize state entry time
        self._state_entry_time = datetime.now()

        logger.info(f"[LifecycleFSM] Agent {agent_id} initialized in state {initial_state.value}")

    @property
    def current_state(self) -> AgentState:
        """Get current state"""
        return self._current_state

    @property
    def state_history(self) -> List[StateTransition]:
        """Get state transition history"""
        return self._state_history.copy()

    def can_transition_to(self, new_state: AgentState) -> bool:
        """
        Check if transition to new state is valid

        Args:
            new_state: Target state

        Returns:
            True if transition allowed, False otherwise
        """
        is_valid, _ = validate_state_transition(self._current_state, new_state)
        return is_valid

    async def transition_to(
        self,
        new_state: AgentState,
        reason: Optional[str] = None,
        triggered_by: Optional[str] = None,
    ) -> bool:
        """
        Transition to new state with validation and callbacks

        Workflow:
        1. Validate transition is allowed
        2. Execute exit behavior of old state
        3. Update current state
        4. Execute entry behavior of new state
        5. Start timeout enforcement (if applicable)
        6. Record transition in history
        7. Emit DeltaBus event (future)
        8. Log transition

        Args:
            new_state: Target state
            reason: Optional reason for transition
            triggered_by: Optional trigger ("timeout", "manual", "health_check")

        Returns:
            True if transition successful, False otherwise
        """
        old_state = self._current_state

        # Step 1: Validate transition
        is_valid, error = validate_state_transition(old_state, new_state, reason)
        if not is_valid:
            logger.error(f"[LifecycleFSM] Agent {self.agent_id}: {error}")
            return False

        # Calculate duration in old state
        duration_ms = 0
        if self._state_entry_time:
            duration_ms = (datetime.now() - self._state_entry_time).total_seconds() * 1000

        # Step 2: Execute exit behavior of old state
        await self._execute_exit_callback(old_state)

        # Cancel any active timeout for old state
        self._cancel_timeout(old_state)

        # Step 3: Update current state
        self._current_state = new_state
        self._state_entry_time = datetime.now()
        self._last_transition_time = datetime.now()

        # Step 4: Execute entry behavior of new state
        await self._execute_entry_callback(new_state)

        # Step 5: Start timeout enforcement for new state
        await self._start_timeout_enforcement(new_state)

        # Step 6: Record transition in history
        transition = StateTransition(
            from_state=old_state,
            to_state=new_state,
            timestamp=datetime.now(),
            reason=reason,
            triggered_by=triggered_by,
        )
        self._state_history.append(transition)

        # Step 7: Emit DeltaBus event (future implementation)
        # await self._emit_state_change_event(old_state, new_state, reason)

        # Step 8: Log transition
        log_state_transition(self.agent_id, old_state, new_state, reason, duration_ms)

        logger.info(
            f"[LifecycleFSM] Agent {self.agent_id}: {old_state.value} → {new_state.value} "
            f"(duration: {duration_ms:.2f}ms, reason: {reason or 'none'})"
        )

        return True

    async def _execute_entry_callback(self, state: AgentState) -> None:
        """Execute entry callback for state"""
        callback_name = f"on_enter_{state.value.lower()}"
        callback = getattr(self._callbacks, callback_name, None)

        if callback and callable(callback):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
                logger.debug(f"[LifecycleFSM] Agent {self.agent_id}: Executed {callback_name}")
            except Exception as e:
                logger.error(f"[LifecycleFSM] Agent {self.agent_id}: Error in {callback_name}: {e}")

    async def _execute_exit_callback(self, state: AgentState) -> None:
        """Execute exit callback for state"""
        callback_name = f"on_exit_{state.value.lower()}"
        callback = getattr(self._callbacks, callback_name, None)

        if callback and callable(callback):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
                logger.debug(f"[LifecycleFSM] Agent {self.agent_id}: Executed {callback_name}")
            except Exception as e:
                logger.error(f"[LifecycleFSM] Agent {self.agent_id}: Error in {callback_name}: {e}")

    async def _start_timeout_enforcement(self, state: AgentState) -> None:
        """
        Start timeout enforcement for states with timeout

        WARMING: 35s → auto-transition to TERMINATED
        IDLE: 10min → auto-transition to DRAINING
        DRAINING: 30s → force transition to TERMINATED
        """
        metadata = get_state_metadata(state)

        if metadata.timeout_seconds is None:
            return

        timeout_seconds = metadata.timeout_seconds

        # Create timeout task
        if state == AgentState.WARMING:
            task = asyncio.create_task(self._warming_timeout(timeout_seconds))
            self._timeout_tasks[state] = task
            logger.debug(
                f"[LifecycleFSM] Agent {self.agent_id}: Started WARMING timeout ({timeout_seconds}s)"
            )

        elif state == AgentState.IDLE:
            task = asyncio.create_task(self._idle_timeout(timeout_seconds))
            self._timeout_tasks[state] = task
            logger.debug(
                f"[LifecycleFSM] Agent {self.agent_id}: Started IDLE TTL ({timeout_seconds}s)"
            )

        elif state == AgentState.DRAINING:
            task = asyncio.create_task(self._draining_timeout(timeout_seconds))
            self._timeout_tasks[state] = task
            logger.debug(
                f"[LifecycleFSM] Agent {self.agent_id}: Started DRAINING timeout ({timeout_seconds}s)"
            )

    def _cancel_timeout(self, state: AgentState) -> None:
        """Cancel timeout task for state"""
        task = self._timeout_tasks.get(state)
        if task and not task.done():
            task.cancel()
            logger.debug(
                f"[LifecycleFSM] Agent {self.agent_id}: Cancelled timeout for {state.value}"
            )

    async def _warming_timeout(self, timeout_seconds: int) -> None:
        """
        WARMING timeout handler

        If agent doesn't transition to ACTIVE within timeout_seconds,
        automatically transition to TERMINATED (failed warmup).
        """
        try:
            await asyncio.sleep(timeout_seconds)

            # Check if still in WARMING state
            if self._current_state == AgentState.WARMING:
                logger.warning(
                    f"[LifecycleFSM] Agent {self.agent_id}: WARMING timeout exceeded ({timeout_seconds}s), "
                    "transitioning to TERMINATED"
                )
                await self.transition_to(
                    AgentState.TERMINATED,
                    reason=f"WARMING timeout exceeded ({timeout_seconds}s)",
                    triggered_by="timeout",
                )
        except asyncio.CancelledError:
            logger.debug(f"[LifecycleFSM] Agent {self.agent_id}: WARMING timeout cancelled")

    async def _idle_timeout(self, timeout_seconds: int) -> None:
        """
        IDLE timeout handler (TTL)

        If agent stays IDLE for timeout_seconds without reactivation,
        automatically transition to DRAINING (expired TTL).
        """
        try:
            await asyncio.sleep(timeout_seconds)

            # Check if still in IDLE state
            if self._current_state == AgentState.IDLE:
                logger.info(
                    f"[LifecycleFSM] Agent {self.agent_id}: IDLE TTL expired ({timeout_seconds}s), "
                    "transitioning to DRAINING"
                )
                await self.transition_to(
                    AgentState.DRAINING,
                    reason=f"IDLE TTL expired ({timeout_seconds}s)",
                    triggered_by="timeout",
                )
        except asyncio.CancelledError:
            logger.debug(f"[LifecycleFSM] Agent {self.agent_id}: IDLE timeout cancelled")

    async def _draining_timeout(self, timeout_seconds: int) -> None:
        """
        DRAINING timeout handler

        If agent doesn't complete draining within timeout_seconds,
        force transition to TERMINATED (drain timeout).
        """
        try:
            await asyncio.sleep(timeout_seconds)

            # Check if still in DRAINING state
            if self._current_state == AgentState.DRAINING:
                logger.warning(
                    f"[LifecycleFSM] Agent {self.agent_id}: DRAINING timeout exceeded ({timeout_seconds}s), "
                    "forcing TERMINATED"
                )
                await self.transition_to(
                    AgentState.TERMINATED,
                    reason=f"DRAINING timeout exceeded ({timeout_seconds}s)",
                    triggered_by="timeout",
                )
        except asyncio.CancelledError:
            logger.debug(f"[LifecycleFSM] Agent {self.agent_id}: DRAINING timeout cancelled")

    async def cleanup(self) -> None:
        """
        Cleanup FSM resources

        Cancel all active timeout tasks.
        """
        for state, task in self._timeout_tasks.items():
            if not task.done():
                task.cancel()
                logger.debug(
                    f"[LifecycleFSM] Agent {self.agent_id}: Cancelled timeout for {state.value}"
                )

        self._timeout_tasks.clear()
        logger.info(f"[LifecycleFSM] Agent {self.agent_id}: Cleaned up FSM resources")

    def get_time_in_state(self) -> float:
        """
        Get time spent in current state (milliseconds)

        Returns:
            Duration in milliseconds
        """
        if self._state_entry_time:
            return (datetime.now() - self._state_entry_time).total_seconds() * 1000
        return 0.0

    def get_transition_count(self) -> int:
        """Get total number of state transitions"""
        return len(self._state_history)

    def __repr__(self) -> str:
        return (
            f"LifecycleFSM(agent_id={self.agent_id}, "
            f"current_state={self._current_state.value}, "
            f"transitions={self.get_transition_count()})"
        )
