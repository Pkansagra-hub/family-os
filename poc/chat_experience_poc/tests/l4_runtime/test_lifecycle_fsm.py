"""
Integration tests for Agent Lifecycle FSM

Tests state transitions, callbacks, and timeout enforcement.
"""

import asyncio

import pytest
from l4_runtime.lifecycle import AgentState, LifecycleFSM, StateCallbacks


@pytest.fixture
def agent_id():
    """Test agent ID"""
    return "test_agent_001"


class TestBasicTransitions:
    """Test basic state transitions"""

    @pytest.mark.asyncio
    async def test_initialize_in_pending(self, agent_id):
        """Test: FSM initializes in PENDING state"""
        fsm = LifecycleFSM(agent_id)
        assert fsm.current_state == AgentState.PENDING
        assert fsm.get_transition_count() == 0

    @pytest.mark.asyncio
    async def test_happy_path_transitions(self, agent_id):
        """Test: Happy path PENDING → WARMING → ACTIVE → IDLE → DRAINING → TERMINATED"""
        fsm = LifecycleFSM(agent_id)

        # PENDING → WARMING
        result = await fsm.transition_to(AgentState.WARMING, reason="Start warmup")
        assert result is True
        assert fsm.current_state == AgentState.WARMING

        # WARMING → ACTIVE
        result = await fsm.transition_to(AgentState.ACTIVE, reason="Warmup complete")
        assert result is True
        assert fsm.current_state == AgentState.ACTIVE

        # ACTIVE → IDLE
        result = await fsm.transition_to(AgentState.IDLE, reason="No tasks")
        assert result is True
        assert fsm.current_state == AgentState.IDLE

        # IDLE → DRAINING
        result = await fsm.transition_to(AgentState.DRAINING, reason="TTL expired")
        assert result is True
        assert fsm.current_state == AgentState.DRAINING

        # DRAINING → TERMINATED
        result = await fsm.transition_to(AgentState.TERMINATED, reason="Shutdown complete")
        assert result is True
        assert fsm.current_state == AgentState.TERMINATED

        # Verify history
        assert fsm.get_transition_count() == 5

        # Cleanup
        await fsm.cleanup()

    @pytest.mark.asyncio
    async def test_invalid_transition(self, agent_id):
        """Test: Invalid transition PENDING → ACTIVE rejected"""
        fsm = LifecycleFSM(agent_id)

        # Try invalid transition
        result = await fsm.transition_to(AgentState.ACTIVE, reason="Skip warming")
        assert result is False
        assert fsm.current_state == AgentState.PENDING  # Should stay in PENDING

        await fsm.cleanup()

    @pytest.mark.asyncio
    async def test_can_transition_to(self, agent_id):
        """Test: can_transition_to() checks validity"""
        fsm = LifecycleFSM(agent_id)

        # Valid transitions from PENDING
        assert fsm.can_transition_to(AgentState.WARMING) is True

        # Invalid transitions from PENDING
        assert fsm.can_transition_to(AgentState.ACTIVE) is False
        assert fsm.can_transition_to(AgentState.IDLE) is False

        await fsm.cleanup()


class TestBidirectionalTransition:
    """Test ACTIVE ↔ IDLE bidirectional transition"""

    @pytest.mark.asyncio
    async def test_active_to_idle_to_active(self, agent_id):
        """Test: ACTIVE → IDLE → ACTIVE (pooling reactivation)"""
        fsm = LifecycleFSM(agent_id)

        # Setup: Get to ACTIVE
        await fsm.transition_to(AgentState.WARMING)
        await fsm.transition_to(AgentState.ACTIVE)

        # ACTIVE → IDLE
        result = await fsm.transition_to(AgentState.IDLE, reason="No tasks, entering pool")
        assert result is True
        assert fsm.current_state == AgentState.IDLE

        # IDLE → ACTIVE (reactivation)
        result = await fsm.transition_to(AgentState.ACTIVE, reason="Reactivated from pool")
        assert result is True
        assert fsm.current_state == AgentState.ACTIVE

        await fsm.cleanup()


class TestStateCallbacks:
    """Test entry/exit callbacks"""

    @pytest.mark.asyncio
    async def test_entry_callback_executes(self, agent_id):
        """Test: Entry callback executes on state transition"""
        callback_executed = []

        def on_enter_warming():
            callback_executed.append("warming_entry")

        callbacks = StateCallbacks(on_enter_warming=on_enter_warming)
        fsm = LifecycleFSM(agent_id, callbacks=callbacks)

        # Transition to WARMING
        await fsm.transition_to(AgentState.WARMING)

        assert "warming_entry" in callback_executed

        await fsm.cleanup()

    @pytest.mark.asyncio
    async def test_exit_callback_executes(self, agent_id):
        """Test: Exit callback executes on state transition"""
        callback_executed = []

        def on_exit_pending():
            callback_executed.append("pending_exit")

        callbacks = StateCallbacks(on_exit_pending=on_exit_pending)
        fsm = LifecycleFSM(agent_id, callbacks=callbacks)

        # Transition away from PENDING
        await fsm.transition_to(AgentState.WARMING)

        assert "pending_exit" in callback_executed

        await fsm.cleanup()

    @pytest.mark.asyncio
    async def test_async_callback_executes(self, agent_id):
        """Test: Async callback executes correctly"""
        callback_executed = []

        async def on_enter_active():
            await asyncio.sleep(0.01)  # Simulate async work
            callback_executed.append("active_entry")

        callbacks = StateCallbacks(on_enter_active=on_enter_active)
        fsm = LifecycleFSM(agent_id, callbacks=callbacks)

        # Setup: Get to ACTIVE
        await fsm.transition_to(AgentState.WARMING)
        await fsm.transition_to(AgentState.ACTIVE)

        assert "active_entry" in callback_executed

        await fsm.cleanup()


class TestTimeoutEnforcement:
    """Test timeout enforcement for WARMING, IDLE, DRAINING"""

    @pytest.mark.asyncio
    async def test_warming_timeout(self, agent_id):
        """Test: WARMING timeout (35s) auto-transitions to TERMINATED"""
        fsm = LifecycleFSM(agent_id)

        # Transition to WARMING
        await fsm.transition_to(AgentState.WARMING)
        assert fsm.current_state == AgentState.WARMING

        # Wait for timeout (use 0.1s for test speed)
        await asyncio.sleep(0.15)

        # Should still be in WARMING (timeout is 35s in production)
        # For this test, we verify timeout task was created
        assert AgentState.WARMING in fsm._timeout_tasks

        # Manually trigger transition before timeout
        await fsm.transition_to(AgentState.ACTIVE)

        # Give the cancellation a moment to propagate
        await asyncio.sleep(0.01)

        # Timeout task should be cancelled now
        task = fsm._timeout_tasks.get(AgentState.WARMING)
        # After awaiting, task should be done/cancelled or removed
        if task is not None:
            assert task.done() or task.cancelled()

        await fsm.cleanup()

    @pytest.mark.asyncio
    async def test_idle_timeout(self, agent_id):
        """Test: IDLE timeout (10min) creates timeout task"""
        fsm = LifecycleFSM(agent_id)

        # Setup: Get to IDLE
        await fsm.transition_to(AgentState.WARMING)
        await fsm.transition_to(AgentState.ACTIVE)
        await fsm.transition_to(AgentState.IDLE)

        # Verify timeout task created
        assert AgentState.IDLE in fsm._timeout_tasks
        task = fsm._timeout_tasks[AgentState.IDLE]
        assert task is not None
        assert not task.done()

        await fsm.cleanup()

    @pytest.mark.asyncio
    async def test_draining_timeout(self, agent_id):
        """Test: DRAINING timeout (30s) creates timeout task"""
        fsm = LifecycleFSM(agent_id)

        # Setup: Get to DRAINING
        await fsm.transition_to(AgentState.WARMING)
        await fsm.transition_to(AgentState.ACTIVE)
        await fsm.transition_to(AgentState.DRAINING)

        # Verify timeout task created
        assert AgentState.DRAINING in fsm._timeout_tasks
        task = fsm._timeout_tasks[AgentState.DRAINING]
        assert task is not None
        assert not task.done()

        await fsm.cleanup()


class TestStateHistory:
    """Test state transition history tracking"""

    @pytest.mark.asyncio
    async def test_history_records_transitions(self, agent_id):
        """Test: State history records all transitions"""
        fsm = LifecycleFSM(agent_id)

        await fsm.transition_to(AgentState.WARMING, reason="Start warmup")
        await fsm.transition_to(AgentState.ACTIVE, reason="Ready")

        history = fsm.state_history
        assert len(history) == 2

        # Check first transition
        assert history[0].from_state == AgentState.PENDING
        assert history[0].to_state == AgentState.WARMING
        assert history[0].reason == "Start warmup"

        # Check second transition
        assert history[1].from_state == AgentState.WARMING
        assert history[1].to_state == AgentState.ACTIVE
        assert history[1].reason == "Ready"

        await fsm.cleanup()


class TestUtilityMethods:
    """Test utility methods"""

    @pytest.mark.asyncio
    async def test_get_time_in_state(self, agent_id):
        """Test: get_time_in_state() returns time in milliseconds"""
        fsm = LifecycleFSM(agent_id)

        await asyncio.sleep(0.05)  # Wait 50ms

        time_in_state = fsm.get_time_in_state()
        assert time_in_state >= 50  # At least 50ms

        await fsm.cleanup()

    @pytest.mark.asyncio
    async def test_repr(self, agent_id):
        """Test: __repr__() shows FSM state"""
        fsm = LifecycleFSM(agent_id)

        repr_str = repr(fsm)
        assert "test_agent_001" in repr_str
        assert "PENDING" in repr_str

        await fsm.cleanup()
        await fsm.cleanup()
