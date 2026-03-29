"""
Tests for ControlSection - System Control Block (HOT CORE)
============================================================

Epic 2.2: HOT CORE Sections
Issue 2.2.1: ControlSection

Tests cover:
- Construction and initialization
- ISection protocol compliance
- Agent lease management
- Flow state management
- Turn lock management
- Domain management
- Safety management
- FlatBuffer serialization round-trip
- Legacy API compatibility
"""

import time
import uuid

import pytest

from k1.sessionstate.sections.control import (
    AgentState,
    ControlSection,
    DomainContext,
    FlowPhase,
    FlowState,
    ISection,
    PrivacyBand,
    SafetyContext,
    TurnLock,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def section() -> ControlSection:
    """Create fresh ControlSection for testing."""
    return ControlSection(session_id="test-session-123")


@pytest.fixture
def populated_section() -> ControlSection:
    """Create ControlSection with data."""
    section = ControlSection(session_id="test-session-456")

    # Add agents
    section.register_agent("agent-1", "planner", ["plan", "reason"])
    section.register_agent("agent-2", "executor", ["execute"])

    # Set flow state
    section.start_turn()
    section.set_flow_phase(FlowPhase.EXECUTION)

    # Set domain
    section.set_primary_domain("calendar")

    return section


# =============================================================================
# Construction Tests
# =============================================================================


class TestControlSectionConstruction:
    """Test ControlSection construction."""

    def test_create_with_session_id(self):
        """Test creating with explicit session ID."""
        section = ControlSection(session_id="my-session")
        assert section.session_id == "my-session"

    def test_create_without_session_id_generates_uuid(self):
        """Test creating without session ID generates UUID."""
        section = ControlSection()
        assert section.session_id != ""
        # Should be valid UUID format
        uuid.UUID(section.session_id)

    def test_initial_state(self, section):
        """Test initial state is correct."""
        assert section.turn_count == 0
        assert section.current_turn_id != ""
        assert section.last_updated_ms > 0

    def test_schema_version(self, section):
        """Test schema version is set."""
        assert section.schema_version == "1.0.0"

    def test_custom_schema_version(self):
        """Test custom schema version."""
        section = ControlSection(schema_version="2.0.0")
        assert section.schema_version == "2.0.0"


# =============================================================================
# ISection Protocol Tests
# =============================================================================


class TestISectionProtocol:
    """Test ISection protocol compliance."""

    def test_implements_isection(self, section):
        """Test implements ISection protocol."""
        assert isinstance(section, ISection)

    def test_name_property(self, section):
        """Test name property."""
        assert section.name == "control"

    def test_tier_property(self, section):
        """Test tier property."""
        assert section.tier == "hot"

    def test_budget_bytes_property(self, section):
        """Test budget_bytes property."""
        assert section.budget_bytes == 8192

    def test_can_evict_property(self, section):
        """Test can_evict is always False."""
        assert section.can_evict is False

    def test_get_size_bytes(self, section):
        """Test get_size_bytes returns positive value."""
        size = section.get_size_bytes()
        assert size > 0
        assert size <= section.budget_bytes

    def test_get_size_bytes_increases_with_data(self, section):
        """Test size increases as data is added."""
        initial_size = section.get_size_bytes()

        # Add agents
        for i in range(5):
            section.register_agent(f"agent-{i}", "test", [f"cap-{i}"])

        new_size = section.get_size_bytes()
        assert new_size > initial_size

    def test_clear(self, populated_section):
        """Test clear resets to initial state."""
        populated_section.clear()

        assert len(populated_section.list_agents()) == 0
        assert populated_section.turn_count == 0
        assert populated_section.get_flow_state().current_phase == FlowPhase.IDLE

    def test_get_metadata(self, section):
        """Test get_metadata returns expected keys."""
        meta = section.get_metadata()

        assert "name" in meta
        assert "tier" in meta
        assert "budget_bytes" in meta
        assert "current_size_bytes" in meta
        assert "utilization_pct" in meta
        assert "session_id" in meta
        assert "turn_count" in meta
        assert meta["name"] == "control"


# =============================================================================
# Agent Lease Tests
# =============================================================================


class TestAgentLeaseManagement:
    """Test agent lease management."""

    def test_register_agent(self, section):
        """Test registering an agent."""
        lease = section.register_agent(
            "agent-1",
            "planner",
            capabilities=["plan", "reason"],
            priority=5,
        )

        assert lease.agent_id == "agent-1"
        assert lease.agent_type == "planner"
        assert "plan" in lease.capabilities
        assert lease.priority == 5
        assert lease.state == AgentState.PENDING

    def test_register_duplicate_raises(self, section):
        """Test registering duplicate agent raises."""
        section.register_agent("agent-1", "planner")

        with pytest.raises(ValueError, match="already registered"):
            section.register_agent("agent-1", "executor")

    def test_get_agent(self, section):
        """Test getting agent by ID."""
        section.register_agent("agent-1", "planner")

        agent = section.get_agent("agent-1")
        assert agent is not None
        assert agent.agent_id == "agent-1"

    def test_get_nonexistent_agent(self, section):
        """Test getting nonexistent agent returns None."""
        agent = section.get_agent("nonexistent")
        assert agent is None

    def test_list_agents(self, section):
        """Test listing all agents."""
        section.register_agent("agent-1", "planner")
        section.register_agent("agent-2", "executor")

        agents = section.list_agents()
        assert len(agents) == 2

    def test_list_agents_by_state(self, section):
        """Test filtering agents by state."""
        section.register_agent("agent-1", "planner")
        section.register_agent("agent-2", "executor")
        section.set_agent_state("agent-1", AgentState.ACTIVE)

        active = section.list_agents(state=AgentState.ACTIVE)
        pending = section.list_agents(state=AgentState.PENDING)

        assert len(active) == 1
        assert len(pending) == 1
        assert active[0].agent_id == "agent-1"

    def test_set_agent_state(self, section):
        """Test updating agent state."""
        section.register_agent("agent-1", "planner")

        result = section.set_agent_state("agent-1", AgentState.ACTIVE)
        assert result is True

        agent = section.get_agent("agent-1")
        assert agent.state == AgentState.ACTIVE

    def test_set_nonexistent_agent_state(self, section):
        """Test setting state for nonexistent agent."""
        result = section.set_agent_state("nonexistent", AgentState.ACTIVE)
        assert result is False

    def test_unregister_agent(self, section):
        """Test unregistering agent."""
        section.register_agent("agent-1", "planner")

        result = section.unregister_agent("agent-1")
        assert result is True
        assert section.get_agent("agent-1") is None

    def test_renew_lease(self, section):
        """Test renewing agent lease."""
        section.register_agent("agent-1", "planner")

        original = section.get_agent("agent-1")
        original_expires = original.lease_expires_ms

        time.sleep(0.01)  # Small delay

        result = section.renew_lease("agent-1", ttl_ms=60000)
        assert result is True

        renewed = section.get_agent("agent-1")
        assert renewed.lease_expires_ms > original_expires

    def test_lease_expiration(self, section):
        """Test lease expiration detection."""
        section.register_agent("agent-1", "planner", ttl_ms=1)  # 1ms TTL

        time.sleep(0.01)  # Wait for expiration

        agent = section.get_agent("agent-1")
        assert agent.is_expired() is True

    def test_expire_stale_leases(self, section):
        """Test expiring stale leases."""
        section.register_agent("agent-1", "planner", ttl_ms=1)
        section.register_agent("agent-2", "executor", ttl_ms=60000)

        time.sleep(0.01)

        expired = section.expire_stale_leases()
        assert "agent-1" in expired
        assert "agent-2" not in expired
        assert section.get_agent("agent-1") is None
        assert section.get_agent("agent-2") is not None


# =============================================================================
# Flow State Tests
# =============================================================================


class TestFlowStateManagement:
    """Test flow state management."""

    def test_get_flow_state(self, section):
        """Test getting flow state."""
        flow = section.get_flow_state()
        assert isinstance(flow, FlowState)
        assert flow.current_phase == FlowPhase.IDLE

    def test_set_flow_phase(self, section):
        """Test setting flow phase."""
        section.set_flow_phase(FlowPhase.EXECUTION)

        flow = section.get_flow_state()
        assert flow.current_phase == FlowPhase.EXECUTION

    def test_start_turn(self, section):
        """Test starting a new turn."""
        initial_turn = section.turn_count

        turn_id = section.start_turn()

        assert section.turn_count == initial_turn + 1
        assert turn_id == section.current_turn_id
        assert section.get_flow_state().turn_id == turn_id

    def test_start_turn_with_timeout(self, section):
        """Test starting turn with custom timeout."""
        section.start_turn(timeout_ms=120000)

        flow = section.get_flow_state()
        assert flow.timeout_ms == 120000

    def test_add_pending_agent(self, section):
        """Test adding pending agent."""
        section.start_turn()
        section.add_pending_agent("agent-1")
        section.add_pending_agent("agent-2")

        flow = section.get_flow_state()
        assert "agent-1" in flow.pending_agents
        assert "agent-2" in flow.pending_agents

    def test_add_duplicate_pending_agent_no_duplicate(self, section):
        """Test adding duplicate pending agent doesn't duplicate."""
        section.start_turn()
        section.add_pending_agent("agent-1")
        section.add_pending_agent("agent-1")

        flow = section.get_flow_state()
        assert flow.pending_agents.count("agent-1") == 1

    def test_mark_agent_completed(self, section):
        """Test marking agent as completed."""
        section.start_turn()
        section.add_pending_agent("agent-1")
        section.mark_agent_completed("agent-1")

        flow = section.get_flow_state()
        assert "agent-1" not in flow.pending_agents
        assert "agent-1" in flow.completed_agents

    def test_flow_timeout_detection(self, section):
        """Test flow timeout detection."""
        section.start_turn(timeout_ms=1)  # 1ms timeout

        time.sleep(0.01)

        flow = section.get_flow_state()
        assert flow.is_timed_out() is True


# =============================================================================
# Turn Lock Tests
# =============================================================================


class TestTurnLockManagement:
    """Test turn lock management."""

    def test_get_turn_lock(self, section):
        """Test getting turn lock."""
        lock = section.get_turn_lock()
        assert isinstance(lock, TurnLock)
        assert lock.locked is False

    def test_acquire_lock(self, section):
        """Test acquiring lock."""
        turn_id = section.start_turn()

        result = section.acquire_lock("agent-1", turn_id)
        assert result is True

        lock = section.get_turn_lock()
        assert lock.locked is True
        assert lock.lock_holder == "agent-1"
        assert lock.turn_id == turn_id

    def test_acquire_lock_when_locked(self, section):
        """Test acquiring lock when already locked."""
        turn_id = section.start_turn()
        section.acquire_lock("agent-1", turn_id)

        result = section.acquire_lock("agent-2", turn_id)
        assert result is False

        lock = section.get_turn_lock()
        assert lock.lock_holder == "agent-1"

    def test_release_lock(self, section):
        """Test releasing lock."""
        turn_id = section.start_turn()
        section.acquire_lock("agent-1", turn_id)

        result = section.release_lock("agent-1")
        assert result is True

        lock = section.get_turn_lock()
        assert lock.locked is False

    def test_release_lock_wrong_holder(self, section):
        """Test releasing lock by wrong holder."""
        turn_id = section.start_turn()
        section.acquire_lock("agent-1", turn_id)

        result = section.release_lock("agent-2")
        assert result is False

        lock = section.get_turn_lock()
        assert lock.locked is True

    def test_force_release_lock(self, section):
        """Test force releasing lock."""
        turn_id = section.start_turn()
        section.acquire_lock("agent-1", turn_id)

        section.force_release_lock()

        lock = section.get_turn_lock()
        assert lock.locked is False

    def test_acquire_expired_lock(self, section):
        """Test acquiring expired lock."""
        turn_id = section.start_turn()
        section.acquire_lock("agent-1", turn_id, timeout_ms=1)

        time.sleep(0.01)

        result = section.acquire_lock("agent-2", turn_id)
        assert result is True

        lock = section.get_turn_lock()
        assert lock.lock_holder == "agent-2"


# =============================================================================
# Domain Tests
# =============================================================================


class TestDomainManagement:
    """Test domain management."""

    def test_get_domains(self, section):
        """Test getting domain context."""
        domains = section.get_domains()
        assert isinstance(domains, DomainContext)

    def test_set_primary_domain(self, section):
        """Test setting primary domain."""
        section.set_primary_domain("calendar")

        domains = section.get_domains()
        assert domains.primary_domain == "calendar"
        assert "calendar" in domains.active_domains

    def test_add_domain(self, section):
        """Test adding domain."""
        section.add_domain("calendar")
        section.add_domain("email")

        domains = section.get_domains()
        assert "calendar" in domains.active_domains
        assert "email" in domains.active_domains

    def test_add_duplicate_domain(self, section):
        """Test adding duplicate domain doesn't duplicate."""
        section.add_domain("calendar")
        section.add_domain("calendar")

        domains = section.get_domains()
        assert domains.active_domains.count("calendar") == 1

    def test_remove_domain(self, section):
        """Test removing domain."""
        section.add_domain("calendar")
        section.add_domain("email")

        section.remove_domain("calendar")

        domains = section.get_domains()
        assert "calendar" not in domains.active_domains
        assert "email" in domains.active_domains

    def test_remove_primary_domain_selects_new(self, section):
        """Test removing primary domain selects new primary."""
        section.set_primary_domain("calendar")
        section.add_domain("email")

        section.remove_domain("calendar")

        domains = section.get_domains()
        assert domains.primary_domain == "email"


# =============================================================================
# Safety Tests
# =============================================================================


class TestSafetyManagement:
    """Test safety management."""

    def test_get_safety(self, section):
        """Test getting safety context."""
        safety = section.get_safety()
        assert isinstance(safety, SafetyContext)
        assert safety.band == PrivacyBand.GREEN

    def test_escalate_safety(self, section):
        """Test escalating safety."""
        section.escalate_safety(PrivacyBand.RED, "Sensitive data detected")

        safety = section.get_safety()
        assert safety.band == PrivacyBand.RED
        assert safety.escalation_reason == "Sensitive data detected"
        assert safety.escalated_at_ms > 0

    def test_escalate_with_confirmation(self, section):
        """Test escalating with confirmation required."""
        section.escalate_safety(
            PrivacyBand.AMBER,
            "Action needs approval",
            require_confirmation=True,
        )

        safety = section.get_safety()
        assert safety.requires_confirmation is True

    def test_is_escalated(self, section):
        """Test is_escalated detection."""
        safety = section.get_safety()
        assert safety.is_escalated() is False

        section.escalate_safety(PrivacyBand.AMBER, "Test")

        safety = section.get_safety()
        assert safety.is_escalated() is True

    def test_block_action(self, section):
        """Test blocking action."""
        section.block_action("delete_file")
        section.block_action("send_email")

        safety = section.get_safety()
        assert "delete_file" in safety.blocked_actions
        assert "send_email" in safety.blocked_actions

    def test_unblock_action(self, section):
        """Test unblocking action."""
        section.block_action("delete_file")
        section.unblock_action("delete_file")

        safety = section.get_safety()
        assert "delete_file" not in safety.blocked_actions

    def test_reset_safety(self, section):
        """Test resetting safety."""
        section.escalate_safety(PrivacyBand.RED, "Test")
        section.block_action("delete_file")

        section.reset_safety()

        safety = section.get_safety()
        assert safety.band == PrivacyBand.GREEN
        assert len(safety.blocked_actions) == 0


# =============================================================================
# Serialization Tests
# =============================================================================


class TestSerialization:
    """Test FlatBuffer serialization."""

    def test_to_flatbuffer(self, section):
        """Test serialization produces bytes."""
        data = section.to_flatbuffer()
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_from_flatbuffer(self, section):
        """Test deserialization."""
        section.register_agent("agent-1", "planner", ["plan"])
        section.set_primary_domain("calendar")

        data = section.to_flatbuffer()

        new_section = ControlSection()
        new_section.from_flatbuffer(data)

        # Verify agents preserved
        agent = new_section.get_agent("agent-1")
        assert agent is not None
        assert agent.agent_type == "planner"

        # Verify domains preserved
        domains = new_section.get_domains()
        assert domains.primary_domain == "calendar"

    def test_round_trip_preserves_all_data(self, populated_section):
        """Test round-trip preserves all data."""
        # Capture original state
        orig_agents = populated_section.list_agents()
        orig_flow = populated_section.get_flow_state()
        orig_domains = populated_section.get_domains()

        # Serialize and deserialize
        data = populated_section.to_flatbuffer()
        new_section = ControlSection()
        new_section.from_flatbuffer(data)

        # Verify agents
        new_agents = new_section.list_agents()
        assert len(new_agents) == len(orig_agents)

        # Verify flow state
        new_flow = new_section.get_flow_state()
        assert new_flow.current_phase == orig_flow.current_phase

        # Verify domains
        new_domains = new_section.get_domains()
        assert new_domains.primary_domain == orig_domains.primary_domain

    def test_serialization_caching(self, section):
        """Test serialization caching works."""
        data1 = section.to_flatbuffer()
        data2 = section.to_flatbuffer()

        assert data1 == data2

        # Modify and check cache invalidation
        section.register_agent("agent-1", "test")
        data3 = section.to_flatbuffer()

        assert data3 != data1

    def test_serialization_size_within_budget(self, populated_section):
        """Test serialized size is within budget."""
        data = populated_section.to_flatbuffer()
        assert len(data) <= populated_section.budget_bytes


# =============================================================================
# Legacy API Tests
# =============================================================================


class TestLegacyAPI:
    """Test legacy API compatibility."""

    def test_get_returns_dict(self, section):
        """Test get() returns dictionary."""
        data = section.get()
        assert isinstance(data, dict)
        assert "session_id" in data
        assert "turn_count" in data

    def test_set_mode(self, section):
        """Test set_mode maps to flow phase."""
        section.set_mode("execution")

        flow = section.get_flow_state()
        assert flow.current_phase == FlowPhase.EXECUTION

    def test_advance_turn(self, section):
        """Test advance_turn increments turn."""
        initial = section.turn_count
        turn_id = section.advance_turn()

        assert section.turn_count == initial + 1
        assert section.current_turn_id == turn_id

    def test_set_focus_clear_focus(self, section):
        """Test focus management."""
        section.set_focus("task-123", "Complete the task")

        domains = section.get_domains()
        assert domains.primary_domain == "task-123"

        section.clear_focus()
        domains = section.get_domains()
        assert domains.primary_domain == ""

    def test_touch_updates_timestamp(self, section):
        """Test touch updates timestamp."""
        initial = section.last_updated_ms

        time.sleep(0.01)
        section.touch()

        assert section.last_updated_ms > initial

    def test_serialize_deserialize(self, section):
        """Test legacy serialize/deserialize methods."""
        section.register_agent("agent-1", "test")

        data = section.serialize()
        assert isinstance(data, bytes)

        new_section = ControlSection()
        new_section.deserialize(data)

        assert new_section.get_agent("agent-1") is not None

    def test_apply_set_mode(self, section):
        """Test apply with set_mode operation."""
        section.apply("set_mode", {"mode": "execution"})

        flow = section.get_flow_state()
        assert flow.current_phase == FlowPhase.EXECUTION

    def test_apply_advance_turn(self, section):
        """Test apply with advance_turn operation."""
        initial = section.turn_count

        section.apply("advance_turn", {})

        assert section.turn_count == initial + 1

    def test_apply_register_agent(self, section):
        """Test apply with register_agent operation."""
        section.apply(
            "register_agent",
            {
                "agent_id": "agent-1",
                "agent_type": "planner",
                "capabilities": ["plan"],
            },
        )

        agent = section.get_agent("agent-1")
        assert agent is not None

    def test_apply_acquire_lock(self, section):
        """Test apply with acquire_lock operation."""
        turn_id = section.start_turn()

        result = section.apply(
            "acquire_lock",
            {
                "holder": "agent-1",
                "turn_id": turn_id,
            },
        )

        assert result is True

    def test_apply_unknown_operation(self, section):
        """Test apply with unknown operation raises."""
        with pytest.raises(ValueError, match="Unknown operation"):
            section.apply("unknown_op", {})


# =============================================================================
# Edge Cases and Stress Tests
# =============================================================================


class TestEdgeCases:
    """Test edge cases and stress scenarios."""

    def test_many_agents(self, section):
        """Test with many agents."""
        for i in range(20):
            section.register_agent(f"agent-{i}", "worker", [f"cap-{i}"])

        assert len(section.list_agents()) == 20
        assert section.get_size_bytes() <= section.budget_bytes

    def test_empty_strings(self, section):
        """Test handling empty strings."""
        section.set_primary_domain("")
        section.escalate_safety(PrivacyBand.AMBER, "")

        # Should not crash
        data = section.to_flatbuffer()
        assert len(data) > 0

    def test_unicode_content(self, section):
        """Test Unicode content handling."""
        section.register_agent("agent-日本語", "テスト", ["機能"])
        section.set_primary_domain("カレンダー")

        data = section.to_flatbuffer()
        new_section = ControlSection()
        new_section.from_flatbuffer(data)

        agent = new_section.get_agent("agent-日本語")
        assert agent is not None
        assert agent.agent_type == "テスト"

    def test_concurrent_turn_operations(self, section):
        """Test multiple turn operations."""
        for i in range(10):
            section.start_turn()

        assert section.turn_count == 10

    def test_timestamp_updates(self, section):
        """Test that operations update timestamps."""
        initial = section.last_updated_ms

        time.sleep(0.01)
        section.register_agent("agent-1", "test")
        after_register = section.last_updated_ms

        assert after_register > initial

        time.sleep(0.01)
        section.set_flow_phase(FlowPhase.EXECUTION)
        after_phase = section.last_updated_ms

        assert after_phase > after_register
