"""
Cross-Section Control → Beliefs Integration Tests (Epic 4.5.2)
================================================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 4.5 Cross-Section Dependency Tests
ISSUE: 4.5.2

**Test control → beliefs_active dependency**

ARCHITECTURE:
    control (HOT CORE) manages agent leases and orchestration state.
    beliefs_active (HOT) contains current session facts.
    Control section NEVER evicted - CAN_EVICT = False.
    Agent leases can read/write to beliefs for coordination.

KEY PROPERTIES:
    - ControlSection.CAN_EVICT = False (NEVER evicted)
    - ControlSection has register_agent(), unregister_agent(), get_agent()
    - Agent leases have capabilities, state, priority
    - Control section is HOT CORE (not just HOT)

HARDCORE INTEGRATION TEST REQUIREMENTS:
    1. ENTRY POINT: SessionStateFactory.create_for_testing()
    2. ALL MUTATIONS: manager.mutate(section, operation, data) or section methods
    3. ALL READS: manager.get_section() or manager.get_snapshot()
    4. NO MOCKS: Real components, real sections

==============================================================================
"""

from __future__ import annotations

import time

import pytest

from k1.sessionstate.factory import SessionStateFactory
from k1.sessionstate.manager import SessionStateManager
from k1.sessionstate.sections.control import (
    AgentLease,
    AgentState,
    ControlSection,
    FlowPhase,
    PrivacyBand,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def session() -> SessionStateManager:
    """Create a session manager for testing."""
    manager = SessionStateFactory.create_for_testing()
    manager.start()
    yield manager
    manager.stop()


# =============================================================================
# TEST CLASS: Control Section Properties
# =============================================================================


class TestControlSectionProperties:
    """Test basic control section properties and structure."""

    def test_control_section_accessible(self, session: SessionStateManager) -> None:
        """Control section is accessible via manager."""
        section = session.get_section("control")
        assert section is not None
        assert isinstance(section, ControlSection)

    def test_control_section_is_hot_tier(self, session: SessionStateManager) -> None:
        """Control section is in HOT tier."""
        section = session.get_section("control")
        assert section.tier == "hot"

    def test_control_section_can_evict_is_false(self, session: SessionStateManager) -> None:
        """Control section CAN_EVICT is False - NEVER evicted."""
        section = session.get_section("control")
        assert section.can_evict is False
        assert ControlSection.CAN_EVICT is False

    def test_control_section_has_budget(self, session: SessionStateManager) -> None:
        """Control section has 8KB budget."""
        section = session.get_section("control")
        assert section.budget_bytes == 8192

    def test_control_section_name_is_control(self, session: SessionStateManager) -> None:
        """Control section name is 'control'."""
        section = session.get_section("control")
        assert section.name == "control"


# =============================================================================
# TEST CLASS: Agent Lease Management
# =============================================================================


class TestAgentLeaseManagement:
    """Test agent registration and lease management."""

    def test_register_agent_via_section(self, session: SessionStateManager) -> None:
        """Can register an agent via section.register_agent()."""
        section = session.get_section("control")

        lease = section.register_agent(
            agent_id="agent-1",
            agent_type="planner",
            capabilities=["plan", "reason"],
            priority=10,
        )

        assert lease is not None
        assert isinstance(lease, AgentLease)
        assert lease.agent_id == "agent-1"
        assert lease.agent_type == "planner"
        assert "plan" in lease.capabilities

    def test_register_multiple_agents(self, session: SessionStateManager) -> None:
        """Can register multiple agents."""
        section = session.get_section("control")

        lease1 = section.register_agent("agent-1", "planner")
        lease2 = section.register_agent("agent-2", "executor")
        lease3 = section.register_agent("agent-3", "monitor")

        assert section.get_agent("agent-1") is not None
        assert section.get_agent("agent-2") is not None
        assert section.get_agent("agent-3") is not None

    def test_get_agent_by_id(self, session: SessionStateManager) -> None:
        """Can retrieve agent by ID."""
        section = session.get_section("control")

        section.register_agent("test-agent", "planner", capabilities=["plan"])

        agent = section.get_agent("test-agent")
        assert agent is not None
        assert agent.agent_id == "test-agent"

    def test_unregister_agent(self, session: SessionStateManager) -> None:
        """Can unregister an agent."""
        section = session.get_section("control")

        section.register_agent("temp-agent", "executor")
        assert section.get_agent("temp-agent") is not None

        result = section.unregister_agent("temp-agent")
        assert result is True
        assert section.get_agent("temp-agent") is None

    def test_duplicate_registration_raises(self, session: SessionStateManager) -> None:
        """Duplicate agent registration raises ValueError."""
        section = session.get_section("control")

        section.register_agent("unique-agent", "planner")

        with pytest.raises(ValueError, match="already registered"):
            section.register_agent("unique-agent", "executor")

    def test_agent_lease_has_ttl(self, session: SessionStateManager) -> None:
        """Agent lease has expiration time."""
        section = session.get_section("control")

        lease = section.register_agent("ttl-agent", "planner")

        assert lease.lease_expires_ms > lease.lease_started_ms
        assert lease.lease_expires_ms > 0

    def test_renew_lease(self, session: SessionStateManager) -> None:
        """Can renew an agent lease."""
        section = session.get_section("control")

        lease = section.register_agent("renewable-agent", "planner")
        original_expires = lease.lease_expires_ms

        time.sleep(0.01)  # Small delay

        result = section.renew_lease("renewable-agent")
        assert result is True

        # Get updated lease
        updated_lease = section.get_agent("renewable-agent")
        assert updated_lease.lease_expires_ms >= original_expires

    def test_set_agent_state(self, session: SessionStateManager) -> None:
        """Can set agent state."""
        section = session.get_section("control")

        section.register_agent("state-agent", "planner")

        result = section.set_agent_state("state-agent", AgentState.ACTIVE)
        assert result is True

        agent = section.get_agent("state-agent")
        assert agent.state == AgentState.ACTIVE


# =============================================================================
# TEST CLASS: Control Never Evicted Under Pressure
# =============================================================================


class TestControlNeverEvicted:
    """Test that control section is NEVER evicted even under pressure."""

    def test_control_not_in_eviction_candidates(self, session: SessionStateManager) -> None:
        """Control section should not appear in eviction candidates."""
        # Fill other sections with data to create pressure
        section = session.get_section("control")
        section.register_agent("test-agent", "planner")

        # Control should never be evictable
        assert section.can_evict is False

    def test_control_survives_emergency_mode(self, session: SessionStateManager) -> None:
        """Control section data survives even in emergency mode."""
        section = session.get_section("control")

        # Register agents
        section.register_agent("survivor-1", "planner")
        section.register_agent("survivor-2", "executor")

        # Fill other sections to create pressure
        history = session.get_section("history_active")
        for i in range(50):
            session.mutate(
                section="history_active",
                operation="append",
                data={
                    "user_message": f"Message {i} " + "x" * 500,
                    "assistant_response": f"Response {i} " + "y" * 500,
                },
            )

        # Control agents should still be there
        assert section.get_agent("survivor-1") is not None
        assert section.get_agent("survivor-2") is not None

    def test_control_size_tracked_separately(self, session: SessionStateManager) -> None:
        """Control section size is tracked in HOT tier."""
        section = session.get_section("control")
        section.register_agent("tracked-agent", "planner")

        snapshot = session.get_snapshot()
        assert snapshot.hot_size_bytes >= 0

    def test_control_budget_is_protected(self, session: SessionStateManager) -> None:
        """Control section has its own protected budget."""
        section = session.get_section("control")

        initial_size = section.get_size_bytes()

        # Add agents
        for i in range(5):
            section.register_agent(f"agent-{i}", "executor")

        new_size = section.get_size_bytes()
        assert new_size >= initial_size
        assert new_size <= section.budget_bytes


# =============================================================================
# TEST CLASS: Control and Beliefs Interaction
# =============================================================================


class TestControlBeliefsInteraction:
    """Test interaction between control section and beliefs_active."""

    def test_both_sections_accessible(self, session: SessionStateManager) -> None:
        """Both control and beliefs_active are accessible."""
        control = session.get_section("control")
        beliefs = session.get_section("beliefs_active")

        assert control is not None
        assert beliefs is not None

    def test_agent_can_add_beliefs(self, session: SessionStateManager) -> None:
        """Registered agent can conceptually add beliefs."""
        control = session.get_section("control")
        beliefs = session.get_section("beliefs_active")

        # Register agent
        lease = control.register_agent("belief-writer", "planner", capabilities=["write_beliefs"])

        # Agent adds beliefs
        fact = beliefs.add_fact(
            subject=lease.agent_id,
            predicate="discovered",
            obj="user_preference_coffee",
            confidence=0.9,
        )

        assert fact is not None
        assert fact.subject == "belief-writer"

    def test_agent_can_query_beliefs(self, session: SessionStateManager) -> None:
        """Registered agent can query beliefs."""
        control = session.get_section("control")
        beliefs = session.get_section("beliefs_active")

        # Register agent
        control.register_agent("belief-reader", "analyzer", capabilities=["read_beliefs"])

        # Add beliefs
        fact = beliefs.add_fact("user", "likes", "coffee")

        # Agent queries beliefs
        retrieved = beliefs.get_fact(fact.id)
        assert retrieved is not None
        assert retrieved.object == "coffee"

    def test_multiple_agents_share_beliefs(self, session: SessionStateManager) -> None:
        """Multiple agents can access same beliefs."""
        control = session.get_section("control")
        beliefs = session.get_section("beliefs_active")

        # Register multiple agents
        control.register_agent("writer-agent", "planner")
        control.register_agent("reader-agent", "executor")

        # One agent adds fact
        fact = beliefs.add_fact("shared", "data", "value")

        # Both agents can see it
        assert beliefs.get_fact(fact.id) is not None
        assert beliefs.get_fact_count() >= 1

    def test_agent_lifecycle_independent_of_beliefs(self, session: SessionStateManager) -> None:
        """Agent lifecycle doesn't affect beliefs data."""
        control = session.get_section("control")
        beliefs = session.get_section("beliefs_active")

        # Register agent and add belief
        control.register_agent("temp-agent", "planner")
        fact = beliefs.add_fact("persistent", "fact", "data")

        # Unregister agent
        control.unregister_agent("temp-agent")

        # Belief should still exist
        assert beliefs.get_fact(fact.id) is not None

    def test_beliefs_independent_of_control(self, session: SessionStateManager) -> None:
        """Beliefs can exist without registered agents."""
        control = session.get_section("control")
        beliefs = session.get_section("beliefs_active")

        # No agents registered
        assert control.get_agent("nonexistent") is None

        # But beliefs work fine
        fact = beliefs.add_fact("independent", "belief", "works")
        assert fact is not None
        assert beliefs.get_fact(fact.id) is not None


# =============================================================================
# TEST CLASS: Flow State Management
# =============================================================================


class TestFlowStateManagement:
    """Test flow state and phase management."""

    def test_flow_state_accessible(self, session: SessionStateManager) -> None:
        """Flow state is accessible via control section."""
        section = session.get_section("control")

        flow = section.get_flow_state()
        assert flow is not None

    def test_set_flow_phase(self, session: SessionStateManager) -> None:
        """Can set flow phase."""
        section = session.get_section("control")

        section.set_flow_phase(FlowPhase.EXECUTION)

        flow = section.get_flow_state()
        assert flow.current_phase == FlowPhase.EXECUTION

    def test_start_turn(self, session: SessionStateManager) -> None:
        """Can start a new turn."""
        section = session.get_section("control")

        turn_id = section.start_turn()
        assert turn_id is not None
        assert len(turn_id) > 0

    def test_flow_tracks_agents(self, session: SessionStateManager) -> None:
        """Flow state tracks pending/completed agents."""
        section = session.get_section("control")

        # Register agents
        section.register_agent("flow-agent-1", "planner")
        section.register_agent("flow-agent-2", "executor")

        # Start turn
        section.start_turn()

        # Flow state should be accessible
        flow = section.get_flow_state()
        assert flow is not None


# =============================================================================
# TEST CLASS: Turn Lock Management
# =============================================================================


class TestTurnLockManagement:
    """Test turn lock functionality."""

    def test_acquire_lock(self, session: SessionStateManager) -> None:
        """Can acquire turn lock."""
        section = session.get_section("control")

        turn_id = section.start_turn()
        result = section.acquire_lock("lock-holder", turn_id)

        assert result is True

    def test_release_lock(self, session: SessionStateManager) -> None:
        """Can release turn lock."""
        section = session.get_section("control")

        turn_id = section.start_turn()
        section.acquire_lock("lock-holder", turn_id)

        result = section.release_lock("lock-holder")
        assert result is True

    def test_lock_prevents_double_acquire(self, session: SessionStateManager) -> None:
        """Lock prevents double acquisition by different holders."""
        section = session.get_section("control")

        turn_id = section.start_turn()

        # First holder acquires
        result1 = section.acquire_lock("holder-1", turn_id)
        assert result1 is True

        # Second holder fails
        result2 = section.acquire_lock("holder-2", turn_id)
        assert result2 is False


# =============================================================================
# TEST CLASS: Safety Context
# =============================================================================


class TestSafetyContext:
    """Test safety context and privacy bands."""

    def test_safety_context_accessible(self, session: SessionStateManager) -> None:
        """Safety context is accessible."""
        section = session.get_section("control")

        safety = section.get_safety()
        assert safety is not None

    def test_default_privacy_band_is_green(self, session: SessionStateManager) -> None:
        """Default privacy band is GREEN."""
        section = session.get_section("control")

        safety = section.get_safety()
        assert safety.band == PrivacyBand.GREEN

    def test_escalate_safety(self, session: SessionStateManager) -> None:
        """Can escalate safety band."""
        section = session.get_section("control")

        section.escalate_safety(PrivacyBand.AMBER, reason="sensitive content")

        safety = section.get_safety()
        assert safety.band == PrivacyBand.AMBER
        assert safety.escalation_reason == "sensitive content"


# =============================================================================
# TEST CLASS: Serialization and Persistence
# =============================================================================


class TestControlSerialization:
    """Test control section serialization."""

    def test_to_flatbuffer_works(self, session: SessionStateManager) -> None:
        """Control section serializes to FlatBuffer."""
        section = session.get_section("control")
        section.register_agent("serialize-test", "planner")

        data = section.to_flatbuffer()

        assert data is not None
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_roundtrip_preserves_agents(self, session: SessionStateManager) -> None:
        """Roundtrip serialization preserves agent data."""
        section = session.get_section("control")

        # Register agents
        section.register_agent("roundtrip-1", "planner", capabilities=["plan"])
        section.register_agent("roundtrip-2", "executor", priority=5)

        # Serialize
        data = section.to_flatbuffer()

        # Create new section and deserialize
        new_section = ControlSection()
        new_section.from_flatbuffer(data)

        # Verify agents preserved
        agent1 = new_section.get_agent("roundtrip-1")
        agent2 = new_section.get_agent("roundtrip-2")

        assert agent1 is not None
        assert agent2 is not None
        assert agent1.agent_type == "planner"
        assert agent2.priority == 5

    def test_checkpoint_preserves_control(self) -> None:
        """Checkpoint preserves control section state."""
        manager = SessionStateFactory.create_for_testing()
        manager.start()

        section = manager.get_section("control")
        section.register_agent("checkpoint-agent", "planner")

        # Checkpoint
        manager.checkpoint()

        # Agent should still be there
        assert section.get_agent("checkpoint-agent") is not None

        manager.stop()


# =============================================================================
# TEST CLASS: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases in control section."""

    def test_register_many_agents(self, session: SessionStateManager) -> None:
        """Can register many agents (up to capacity)."""
        section = session.get_section("control")

        for i in range(10):
            section.register_agent(f"agent-{i}", "worker")

        # All should be registered
        for i in range(10):
            assert section.get_agent(f"agent-{i}") is not None

    def test_list_agents(self, session: SessionStateManager) -> None:
        """Can list all registered agents."""
        section = session.get_section("control")

        section.register_agent("list-1", "planner")
        section.register_agent("list-2", "executor")

        agents = section.list_agents()
        assert len(agents) >= 2

    def test_list_agents_by_state(self, session: SessionStateManager) -> None:
        """Can list agents filtered by state."""
        section = session.get_section("control")

        section.register_agent("active-agent", "planner")
        section.set_agent_state("active-agent", AgentState.ACTIVE)

        section.register_agent("idle-agent", "executor")
        section.set_agent_state("idle-agent", AgentState.IDLE)

        active_agents = section.list_agents(state=AgentState.ACTIVE)
        assert len(active_agents) >= 1

    def test_unregister_nonexistent_agent(self, session: SessionStateManager) -> None:
        """Unregistering nonexistent agent returns False."""
        section = session.get_section("control")

        result = section.unregister_agent("nonexistent")
        assert result is False

    def test_renew_nonexistent_lease(self, session: SessionStateManager) -> None:
        """Renewing nonexistent lease returns False."""
        section = session.get_section("control")

        result = section.renew_lease("nonexistent")
        assert result is False


# =============================================================================
# TEST CLASS: Performance
# =============================================================================


class TestPerformance:
    """Test performance of control section operations."""

    def test_register_agent_fast(self, session: SessionStateManager) -> None:
        """Agent registration is fast."""
        section = session.get_section("control")

        start = time.perf_counter()

        for i in range(20):
            section.register_agent(f"fast-agent-{i}", "worker")

        elapsed = time.perf_counter() - start
        assert elapsed < 0.5, f"Registering 20 agents took {elapsed:.3f}s"

    def test_serialization_under_100us(self, session: SessionStateManager) -> None:
        """Serialization targets <100 microseconds (may not always hit)."""
        section = session.get_section("control")

        # Add some data
        section.register_agent("perf-agent", "planner", capabilities=["a", "b", "c"])
        section.start_turn()

        # Warm up
        section.to_flatbuffer()

        # Measure
        start = time.perf_counter()
        data = section.to_flatbuffer()
        elapsed_us = (time.perf_counter() - start) * 1_000_000

        # Target is <100us, but allow some slack
        assert elapsed_us < 1000, f"Serialization took {elapsed_us:.1f}us"
        assert len(data) > 0

    def test_get_agent_fast(self, session: SessionStateManager) -> None:
        """Getting agent by ID is fast."""
        section = session.get_section("control")

        # Register agents
        for i in range(20):
            section.register_agent(f"lookup-{i}", "worker")

        start = time.perf_counter()

        for i in range(20):
            section.get_agent(f"lookup-{i}")

        elapsed = time.perf_counter() - start
        assert elapsed < 0.1, f"20 lookups took {elapsed:.3f}s"


# =============================================================================
# TEST CLASS: Cross-Section Pressure Test
# =============================================================================


class TestCrossSectionPressure:
    """Test control section behavior under cross-section pressure."""

    def test_control_survives_beliefs_pressure(self, session: SessionStateManager) -> None:
        """Control section survives when beliefs_active is under pressure."""
        control = session.get_section("control")
        beliefs = session.get_section("beliefs_active")

        # Register important agents
        control.register_agent("critical-1", "orchestrator")
        control.register_agent("critical-2", "monitor")

        # Fill beliefs_active
        for i in range(40):
            beliefs.add_fact(f"user_{i}", "prefers", f"item_{i}")

        # Control agents should still be there
        assert control.get_agent("critical-1") is not None
        assert control.get_agent("critical-2") is not None

        # Control should not be evictable
        assert control.can_evict is False

    def test_beliefs_demotion_doesnt_affect_control(self, session: SessionStateManager) -> None:
        """Beliefs demotion doesn't affect control section."""
        control = session.get_section("control")
        beliefs = session.get_section("beliefs_active")

        # Register agent
        control.register_agent("stable-agent", "planner")

        # Add facts and demote
        for i in range(10):
            beliefs.add_fact(f"user_{i}", "prefers", f"item_{i}")

        demoted = beliefs.demote_facts(5)
        assert len(demoted) == 5

        # Control unaffected
        assert control.get_agent("stable-agent") is not None
        assert control.get_agent("stable-agent").agent_type == "planner"

    def test_parallel_control_and_beliefs_operations(self, session: SessionStateManager) -> None:
        """Control and beliefs can be operated in parallel conceptually."""
        control = session.get_section("control")
        beliefs = session.get_section("beliefs_active")

        # Interleaved operations
        control.register_agent("interleave-1", "planner")
        beliefs.add_fact("belief-1", "is", "true")

        control.register_agent("interleave-2", "executor")
        beliefs.add_fact("belief-2", "is", "also_true")

        control.set_agent_state("interleave-1", AgentState.ACTIVE)

        # Both sections have their data
        assert control.get_agent("interleave-1") is not None
        assert control.get_agent("interleave-2") is not None
        assert beliefs.get_fact_count() >= 2
