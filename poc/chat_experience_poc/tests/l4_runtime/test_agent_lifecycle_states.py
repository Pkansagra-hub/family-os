"""
Unit tests for Agent Lifecycle States

Tests state definitions, transitions, and validation logic.
"""

from datetime import datetime

from l4_runtime.lifecycle.agent_lifecycle import (
    DEFAULT_TIMEOUTS,
    AgentState,
    StateTransition,
    get_allowed_transitions,
    get_state_metadata,
    is_valid_transition,
    validate_state_transition,
)


class TestAgentStates:
    """Test agent state definitions"""

    def test_all_states_defined(self):
        """Test: All 6 states are defined"""
        expected_states = {"PENDING", "WARMING", "ACTIVE", "IDLE", "DRAINING", "TERMINATED"}
        actual_states = {state.value for state in AgentState}
        assert actual_states == expected_states

    def test_state_enum_values(self):
        """Test: State enum values match their names"""
        assert AgentState.PENDING.value == "PENDING"
        assert AgentState.WARMING.value == "WARMING"
        assert AgentState.ACTIVE.value == "ACTIVE"
        assert AgentState.IDLE.value == "IDLE"
        assert AgentState.DRAINING.value == "DRAINING"
        assert AgentState.TERMINATED.value == "TERMINATED"


class TestStateTransitions:
    """Test state transition validation"""

    def test_valid_transitions_pending_to_warming(self):
        """Test: PENDING → WARMING is valid"""
        assert is_valid_transition(AgentState.PENDING, AgentState.WARMING)

    def test_valid_transitions_warming_to_active(self):
        """Test: WARMING → ACTIVE is valid"""
        assert is_valid_transition(AgentState.WARMING, AgentState.ACTIVE)

    def test_valid_transitions_active_to_idle(self):
        """Test: ACTIVE → IDLE is valid"""
        assert is_valid_transition(AgentState.ACTIVE, AgentState.IDLE)

    def test_valid_transitions_idle_to_active(self):
        """Test: IDLE → ACTIVE is valid (bidirectional)"""
        assert is_valid_transition(AgentState.IDLE, AgentState.ACTIVE)

    def test_valid_transitions_active_to_draining(self):
        """Test: ACTIVE → DRAINING is valid"""
        assert is_valid_transition(AgentState.ACTIVE, AgentState.DRAINING)

    def test_valid_transitions_draining_to_terminated(self):
        """Test: DRAINING → TERMINATED is valid"""
        assert is_valid_transition(AgentState.DRAINING, AgentState.TERMINATED)

    def test_invalid_transition_pending_to_active(self):
        """Test: PENDING → ACTIVE is invalid (must go through WARMING)"""
        assert not is_valid_transition(AgentState.PENDING, AgentState.ACTIVE)

    def test_invalid_transition_warming_to_idle(self):
        """Test: WARMING → IDLE is invalid"""
        assert not is_valid_transition(AgentState.WARMING, AgentState.IDLE)

    def test_invalid_transition_from_terminated(self):
        """Test: TERMINATED → any is invalid (final state)"""
        assert not is_valid_transition(AgentState.TERMINATED, AgentState.ACTIVE)
        assert not is_valid_transition(AgentState.TERMINATED, AgentState.PENDING)

    def test_get_allowed_transitions(self):
        """Test: Get allowed transitions from ACTIVE"""
        allowed = get_allowed_transitions(AgentState.ACTIVE)
        assert AgentState.IDLE in allowed
        assert AgentState.DRAINING in allowed
        assert len(allowed) == 2

    def test_get_allowed_transitions_terminated(self):
        """Test: TERMINATED has no allowed transitions"""
        allowed = get_allowed_transitions(AgentState.TERMINATED)
        assert len(allowed) == 0


class TestStateValidation:
    """Test state transition validation with error messages"""

    def test_validate_valid_transition(self):
        """Test: Valid transition returns True with no error"""
        is_valid, error = validate_state_transition(AgentState.PENDING, AgentState.WARMING)
        assert is_valid
        assert error is None

    def test_validate_invalid_transition(self):
        """Test: Invalid transition returns False with error message"""
        is_valid, error = validate_state_transition(AgentState.PENDING, AgentState.ACTIVE)
        assert not is_valid
        assert error is not None
        assert "Invalid transition" in error
        assert "PENDING → ACTIVE" in error

    def test_validate_transition_from_final_state(self):
        """Test: Transition from TERMINATED returns error"""
        is_valid, error = validate_state_transition(AgentState.TERMINATED, AgentState.ACTIVE)
        assert not is_valid
        assert error is not None
        assert "Invalid transition" in error
        assert "TERMINATED" in error


class TestStateMetadata:
    """Test state metadata"""

    def test_state_metadata_exists_for_all_states(self):
        """Test: Metadata exists for all 6 states"""
        for state in AgentState:
            metadata = get_state_metadata(state)
            assert metadata is not None
            assert metadata.name == state.value

    def test_pending_metadata(self):
        """Test: PENDING state metadata"""
        metadata = get_state_metadata(AgentState.PENDING)
        assert metadata.name == "PENDING"
        assert not metadata.is_final
        assert not metadata.allows_pooling
        assert metadata.timeout_seconds is None

    def test_warming_metadata(self):
        """Test: WARMING state has 35s timeout"""
        metadata = get_state_metadata(AgentState.WARMING)
        assert metadata.timeout_seconds == 35
        assert not metadata.is_final

    def test_idle_metadata(self):
        """Test: IDLE state allows pooling and has TTL"""
        metadata = get_state_metadata(AgentState.IDLE)
        assert metadata.allows_pooling
        assert metadata.timeout_seconds == 600  # 10 minutes
        assert not metadata.is_final

    def test_terminated_metadata(self):
        """Test: TERMINATED state is final"""
        metadata = get_state_metadata(AgentState.TERMINATED)
        assert metadata.is_final
        assert not metadata.allows_pooling
        assert metadata.timeout_seconds is None


class TestStateTimeouts:
    """Test state timeout configuration"""

    def test_warming_timeout(self):
        """Test: WARMING timeout is 35 seconds"""
        assert DEFAULT_TIMEOUTS.warming_timeout_seconds == 35

    def test_idle_ttl(self):
        """Test: IDLE TTL is 600 seconds (10 minutes)"""
        assert DEFAULT_TIMEOUTS.idle_ttl_seconds == 600

    def test_draining_timeout(self):
        """Test: DRAINING timeout is 30 seconds"""
        assert DEFAULT_TIMEOUTS.draining_timeout_seconds == 30

    def test_health_check_interval(self):
        """Test: Health check interval is 30 seconds"""
        assert DEFAULT_TIMEOUTS.health_check_interval_seconds == 30


class TestStateTransitionDataclass:
    """Test StateTransition dataclass"""

    def test_create_state_transition(self):
        """Test: Create StateTransition with all fields"""
        transition = StateTransition(
            from_state=AgentState.ACTIVE,
            to_state=AgentState.IDLE,
            timestamp=datetime.now(),
            reason="No tasks available",
            triggered_by="manual",
        )

        assert transition.from_state == AgentState.ACTIVE
        assert transition.to_state == AgentState.IDLE
        assert transition.reason == "No tasks available"
        assert transition.triggered_by == "manual"

    def test_create_state_transition_minimal(self):
        """Test: Create StateTransition with required fields only"""
        transition = StateTransition(
            from_state=AgentState.PENDING,
            to_state=AgentState.WARMING,
            timestamp=datetime.now(),
        )

        assert transition.from_state == AgentState.PENDING
        assert transition.to_state == AgentState.WARMING
        assert transition.reason is None
        assert transition.triggered_by is None
        assert transition.triggered_by is None
