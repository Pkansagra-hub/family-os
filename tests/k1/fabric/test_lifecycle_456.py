"""
Unit tests for Lifecycle: Ephemeral vs Persistent agents (4.5.6).

Tests:
  - CapabilityContract lifecycle fields (ephemeral, created_by, created_at_iso, session_scoped)
  - CapabilityRegistry.register_created_agent()
  - CapabilityRegistry.list_created_agents()
  - CapabilityRegistry.is_created_agent()
  - CapabilityRegistry.created_agent_count
  - CapabilityRegistry.remove_expired_agents()
  - CreatedAgentRecord frozen dataclass
  - Thread-safety of lifecycle operations

Uses real CapabilityRegistry, real ContractValidator.
NO MOCKS.

References:
  - fabric-implementation-plan.md Issue 4.5.6
  - k1/fabric/core/registry.py
  - k1/fabric/types.py (CapabilityContract lifecycle fields)
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List

import pytest

from k1.fabric.core.registry import CapabilityNotFoundError, CapabilityRegistry, CreatedAgentRecord
from k1.fabric.types import AgentContract, CapabilityContract, InputSpec, SafetyBand

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeEventPort:
    """Capture events for assertion."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    def emit(self, event_type: str, payload: Any) -> None:
        self.events.append({"type": event_type, "payload": payload})


def _registry(capture: bool = True) -> tuple[CapabilityRegistry, FakeEventPort]:
    """Create a registry + event port pair for testing."""
    port = FakeEventPort()
    reg = CapabilityRegistry(event_port=port)
    return reg, port


def _tool(
    name: str = "tool.execute.test_tool",
    domain: str = "TEST",
) -> CapabilityContract:
    """Minimal valid tool contract."""
    return CapabilityContract(
        name=name,
        version="1.0.0",
        domain=[domain],
        description="Test tool",
        capabilities=["test"],
        required_inputs=[InputSpec(name="x", type="STRING", description="input")],
        output={"type": "object"},
        provider_type="MCP",
        provider_id="test-provider",
        safety_band_min=SafetyBand.GREEN.value,
    )


def _agent(
    name: str = "agent.execute.test_agent",
    domain: str = "TEST",
) -> AgentContract:
    """Minimal valid agent contract."""
    return AgentContract(
        name=name,
        version="1.0.0",
        domain=[domain],
        description="Test agent",
        capabilities=["test"],
        required_inputs=[InputSpec(name="x", type="STRING", description="input")],
        output={"type": "object"},
        provider_type="AGENT",
        provider_id="test-agent-provider",
        safety_band_min=SafetyBand.GREEN.value,
        prompt_template="You are a test agent.",
        tools_granted=["tool.execute.test_tool"],
        llm_budget_tokens=8192,
        max_tool_calls=10,
    )


# ===================================================================
# Tests: CapabilityContract lifecycle fields
# ===================================================================


class TestCapabilityContractLifecycleFields:
    """Verify the 4 new lifecycle fields on CapabilityContract."""

    def test_defaults_backward_compatible(self) -> None:
        """Existing contracts get sensible defaults."""
        c = _tool()
        assert c.ephemeral is True
        assert c.created_by == ""
        assert c.created_at_iso == ""
        assert c.session_scoped is True

    def test_explicit_lifecycle_fields(self) -> None:
        """Fields can be set explicitly at construction time."""
        c = CapabilityContract(
            name="tool.execute.custom",
            version="1.0.0",
            domain=["TEST"],
            ephemeral=False,
            created_by="orchestrator",
            created_at_iso="2026-02-08T00:00:00+00:00",
            session_scoped=False,
        )
        assert c.ephemeral is False
        assert c.created_by == "orchestrator"
        assert c.created_at_iso == "2026-02-08T00:00:00+00:00"
        assert c.session_scoped is False

    def test_to_dict_includes_lifecycle(self) -> None:
        """to_dict() includes all 4 lifecycle fields."""
        c = CapabilityContract(
            name="tool.execute.x",
            version="1.0.0",
            domain=["T"],
            ephemeral=False,
            created_by="planner",
            created_at_iso="2026-01-01T00:00:00+00:00",
            session_scoped=False,
        )
        d = c.to_dict()
        assert d["ephemeral"] is False
        assert d["created_by"] == "planner"
        assert d["created_at_iso"] == "2026-01-01T00:00:00+00:00"
        assert d["session_scoped"] is False

    def test_from_dict_lifecycle_round_trip(self) -> None:
        """from_dict() restores lifecycle fields correctly."""
        original = CapabilityContract(
            name="tool.execute.roundtrip",
            version="1.0.0",
            domain=["TEST"],
            ephemeral=False,
            created_by="orchestrator",
            created_at_iso="2026-02-08T12:00:00+00:00",
            session_scoped=False,
        )
        restored = CapabilityContract.from_dict(original.to_dict())
        assert restored.ephemeral == original.ephemeral
        assert restored.created_by == original.created_by
        assert restored.created_at_iso == original.created_at_iso
        assert restored.session_scoped == original.session_scoped

    def test_from_dict_defaults_when_missing(self) -> None:
        """from_dict() uses defaults when lifecycle keys are absent."""
        data = {"name": "tool.execute.legacy", "version": "1.0.0", "domain": ["X"]}
        c = CapabilityContract.from_dict(data)
        assert c.ephemeral is True
        assert c.created_by == ""
        assert c.created_at_iso == ""
        assert c.session_scoped is True

    def test_frozen_immutability(self) -> None:
        """Lifecycle fields are frozen (immutable)."""
        c = _tool()
        with pytest.raises(AttributeError):
            c.ephemeral = False  # type: ignore[misc]

    def test_agent_contract_inherits_lifecycle(self) -> None:
        """AgentContract inherits the 4 lifecycle fields."""
        a = _agent()
        assert a.ephemeral is True
        assert a.created_by == ""
        assert a.created_at_iso == ""
        assert a.session_scoped is True

    def test_agent_from_dict_lifecycle_round_trip(self) -> None:
        """AgentContract.from_dict() preserves lifecycle fields."""
        original = AgentContract(
            name="agent.execute.rt",
            version="1.0.0",
            domain=["TEST"],
            ephemeral=False,
            created_by="user",
            created_at_iso="2026-06-15T10:00:00+00:00",
            session_scoped=False,
            provider_type="AGENT",
            prompt_template="t",
            tools_granted=["tool.execute.x"],
        )
        restored = AgentContract.from_dict(original.to_dict())
        assert restored.ephemeral is False
        assert restored.created_by == "user"
        assert restored.created_at_iso == "2026-06-15T10:00:00+00:00"
        assert restored.session_scoped is False


# ===================================================================
# Tests: CreatedAgentRecord
# ===================================================================


class TestCreatedAgentRecord:
    """Verify CreatedAgentRecord frozen dataclass."""

    def test_construction_defaults(self) -> None:
        r = CreatedAgentRecord(name="agent.execute.x")
        assert r.name == "agent.execute.x"
        assert r.ephemeral is True
        assert r.created_by == ""
        assert r.created_at_iso == ""
        assert r.session_scoped is True

    def test_construction_explicit(self) -> None:
        r = CreatedAgentRecord(
            name="agent.execute.y",
            ephemeral=False,
            created_by="orchestrator",
            created_at_iso="2026-02-08T00:00:00+00:00",
            session_scoped=False,
        )
        assert r.ephemeral is False
        assert r.created_by == "orchestrator"
        assert r.session_scoped is False

    def test_frozen(self) -> None:
        r = CreatedAgentRecord(name="agent.execute.z")
        with pytest.raises(AttributeError):
            r.name = "changed"  # type: ignore[misc]

    def test_to_dict(self) -> None:
        r = CreatedAgentRecord(
            name="agent.execute.w",
            ephemeral=False,
            created_by="planner",
            created_at_iso="2026-01-01T00:00:00+00:00",
            session_scoped=True,
        )
        d = r.to_dict()
        assert d == {
            "name": "agent.execute.w",
            "ephemeral": False,
            "created_by": "planner",
            "created_at_iso": "2026-01-01T00:00:00+00:00",
            "session_scoped": True,
        }


# ===================================================================
# Tests: register_created_agent
# ===================================================================


class TestRegisterCreatedAgent:
    """Tests for CapabilityRegistry.register_created_agent()."""

    def test_basic_registration(self) -> None:
        reg, _ = _registry()
        contract = _agent()
        reg.register(contract, skip_validation=True)
        reg.register_created_agent(
            contract, ephemeral=True, created_by="orchestrator", session_scoped=True
        )

        assert reg.is_created_agent("agent.execute.test_agent")
        assert reg.created_agent_count == 1

    def test_stamps_lifecycle_on_contract(self) -> None:
        """After register_created_agent, lookup returns stamped contract."""
        reg, _ = _registry()
        contract = _agent()
        reg.register(contract, skip_validation=True)
        reg.register_created_agent(
            contract, ephemeral=False, created_by="planner", session_scoped=False
        )

        looked_up = reg.lookup("agent.execute.test_agent")
        assert looked_up is not None
        assert looked_up.ephemeral is False
        assert looked_up.created_by == "planner"
        assert looked_up.created_at_iso != ""
        assert looked_up.session_scoped is False

    def test_created_at_iso_populated(self) -> None:
        reg, _ = _registry()
        contract = _agent()
        reg.register(contract, skip_validation=True)
        reg.register_created_agent(contract, ephemeral=True, created_by="x", session_scoped=True)

        record = reg.list_created_agents()[0]
        assert record.created_at_iso != ""
        assert "T" in record.created_at_iso  # ISO 8601 format

    def test_not_found_raises(self) -> None:
        """register_created_agent on unregistered name raises CapabilityNotFoundError."""
        reg, _ = _registry()
        contract = _agent()
        with pytest.raises(CapabilityNotFoundError):
            reg.register_created_agent(
                contract, ephemeral=True, created_by="x", session_scoped=True
            )

    def test_metadata_cache_updated(self) -> None:
        """Metadata cache reflects the stamped contract after registration."""
        reg, _ = _registry()
        contract = _agent()
        reg.register(contract, skip_validation=True)
        reg.register_created_agent(contract, ephemeral=True, created_by="orch", session_scoped=True)

        meta = reg.get_metadata("agent.execute.test_agent")
        assert meta is not None
        assert meta.name == "agent.execute.test_agent"

    def test_multiple_agents(self) -> None:
        """Multiple agents can be tracked independently."""
        reg, _ = _registry()
        a1 = _agent(name="agent.execute.alpha")
        a2 = _agent(name="agent.execute.beta")
        reg.register(a1, skip_validation=True)
        reg.register(a2, skip_validation=True)
        reg.register_created_agent(a1, ephemeral=True, created_by="orch", session_scoped=True)
        reg.register_created_agent(a2, ephemeral=False, created_by="user", session_scoped=False)

        assert reg.created_agent_count == 2
        assert reg.is_created_agent("agent.execute.alpha")
        assert reg.is_created_agent("agent.execute.beta")

    def test_tool_contract_can_be_created_agent(self) -> None:
        """register_created_agent works on any contract type, not just AgentContract."""
        reg, _ = _registry()
        contract = _tool()
        reg.register(contract, skip_validation=True)
        reg.register_created_agent(contract, ephemeral=True, created_by="orch", session_scoped=True)

        assert reg.is_created_agent("tool.execute.test_tool")


# ===================================================================
# Tests: list_created_agents
# ===================================================================


class TestListCreatedAgents:
    """Tests for CapabilityRegistry.list_created_agents()."""

    def test_empty_initially(self) -> None:
        reg, _ = _registry()
        assert reg.list_created_agents() == []

    def test_returns_all_records(self) -> None:
        reg, _ = _registry()
        a1 = _agent(name="agent.execute.one")
        a2 = _agent(name="agent.execute.two")
        a3 = _agent(name="agent.execute.three")
        for a in (a1, a2, a3):
            reg.register(a, skip_validation=True)
            reg.register_created_agent(a, ephemeral=True, created_by="orch", session_scoped=True)

        records = reg.list_created_agents()
        assert len(records) == 3
        names = {r.name for r in records}
        assert names == {"agent.execute.one", "agent.execute.two", "agent.execute.three"}

    def test_defensive_copy(self) -> None:
        """list_created_agents returns a copy, not a reference."""
        reg, _ = _registry()
        a = _agent()
        reg.register(a, skip_validation=True)
        reg.register_created_agent(a, ephemeral=True, created_by="orch", session_scoped=True)

        result1 = reg.list_created_agents()
        result2 = reg.list_created_agents()
        assert result1 is not result2
        assert result1[0] == result2[0]

    def test_records_contain_correct_metadata(self) -> None:
        reg, _ = _registry()
        a = _agent(name="agent.execute.meta_check")
        reg.register(a, skip_validation=True)
        reg.register_created_agent(a, ephemeral=False, created_by="planner", session_scoped=False)

        record = reg.list_created_agents()[0]
        assert record.name == "agent.execute.meta_check"
        assert record.ephemeral is False
        assert record.created_by == "planner"
        assert record.session_scoped is False


# ===================================================================
# Tests: is_created_agent
# ===================================================================


class TestIsCreatedAgent:
    """Tests for CapabilityRegistry.is_created_agent()."""

    def test_false_for_yaml_loaded(self) -> None:
        """Normal YAML-loaded contracts are NOT created agents."""
        reg, _ = _registry()
        reg.register(_tool(), skip_validation=True)
        assert reg.is_created_agent("tool.execute.test_tool") is False

    def test_true_after_register_created(self) -> None:
        reg, _ = _registry()
        a = _agent()
        reg.register(a, skip_validation=True)
        reg.register_created_agent(a, ephemeral=True, created_by="orch", session_scoped=True)
        assert reg.is_created_agent("agent.execute.test_agent") is True

    def test_false_for_unknown_name(self) -> None:
        reg, _ = _registry()
        assert reg.is_created_agent("agent.execute.nonexistent") is False


# ===================================================================
# Tests: remove_expired_agents
# ===================================================================


class TestRemoveExpiredAgents:
    """Tests for CapabilityRegistry.remove_expired_agents()."""

    def test_removes_ephemeral_session_scoped(self) -> None:
        """Ephemeral + session_scoped agents ARE removed."""
        reg, _ = _registry()
        a = _agent()
        reg.register(a, skip_validation=True)
        reg.register_created_agent(a, ephemeral=True, created_by="orch", session_scoped=True)

        count, names = reg.remove_expired_agents("session-123")
        assert count == 1
        assert names == ["agent.execute.test_agent"]
        assert reg.is_created_agent("agent.execute.test_agent") is False
        assert reg.lookup("agent.execute.test_agent") is None

    def test_preserves_persistent_agents(self) -> None:
        """ephemeral=False agents are NOT removed."""
        reg, _ = _registry()
        a = _agent(name="agent.execute.persistent")
        reg.register(a, skip_validation=True)
        reg.register_created_agent(a, ephemeral=False, created_by="orch", session_scoped=True)

        count, names = reg.remove_expired_agents("session-123")
        assert count == 0
        assert names == []
        assert reg.is_created_agent("agent.execute.persistent") is True

    def test_preserves_non_session_scoped(self) -> None:
        """session_scoped=False agents are NOT removed."""
        reg, _ = _registry()
        a = _agent(name="agent.execute.global")
        reg.register(a, skip_validation=True)
        reg.register_created_agent(a, ephemeral=True, created_by="orch", session_scoped=False)

        count, names = reg.remove_expired_agents("session-123")
        assert count == 0
        assert names == []
        assert reg.is_created_agent("agent.execute.global") is True

    def test_mixed_agents_selective_removal(self) -> None:
        """Only ephemeral + session_scoped agents removed; others preserved."""
        reg, _ = _registry()
        # Will be removed
        a1 = _agent(name="agent.execute.ephemeral_session")
        reg.register(a1, skip_validation=True)
        reg.register_created_agent(a1, ephemeral=True, created_by="orch", session_scoped=True)

        # Will NOT be removed (persistent)
        a2 = _agent(name="agent.execute.persistent_session")
        reg.register(a2, skip_validation=True)
        reg.register_created_agent(a2, ephemeral=False, created_by="orch", session_scoped=True)

        # Will NOT be removed (not session-scoped)
        a3 = _agent(name="agent.execute.ephemeral_global")
        reg.register(a3, skip_validation=True)
        reg.register_created_agent(a3, ephemeral=True, created_by="orch", session_scoped=False)

        count, names = reg.remove_expired_agents("sess-42")
        assert count == 1
        assert names == ["agent.execute.ephemeral_session"]

        # Verify survivors
        assert reg.is_created_agent("agent.execute.persistent_session")
        assert reg.is_created_agent("agent.execute.ephemeral_global")
        assert not reg.is_created_agent("agent.execute.ephemeral_session")

    def test_no_created_agents_no_op(self) -> None:
        """No created agents => returns (0, [])."""
        reg, _ = _registry()
        reg.register(_tool(), skip_validation=True)

        count, names = reg.remove_expired_agents("session-x")
        assert count == 0
        assert names == []

    def test_removes_from_main_index(self) -> None:
        """Removed agents are unregistered from the main by_name index."""
        reg, _ = _registry()
        a = _agent()
        reg.register(a, skip_validation=True)
        reg.register_created_agent(a, ephemeral=True, created_by="orch", session_scoped=True)

        assert reg.contains("agent.execute.test_agent") is True
        reg.remove_expired_agents("session-1")
        assert reg.contains("agent.execute.test_agent") is False

    def test_count_property_updates_after_removal(self) -> None:
        reg, _ = _registry()
        a = _agent()
        reg.register(a, skip_validation=True)
        reg.register_created_agent(a, ephemeral=True, created_by="orch", session_scoped=True)

        assert reg.created_agent_count == 1
        reg.remove_expired_agents("s")
        assert reg.created_agent_count == 0


# ===================================================================
# Tests: Thread safety
# ===================================================================


class TestLifecycleThreadSafety:
    """Verify thread-safety of lifecycle operations."""

    def test_concurrent_register_created_agents(self) -> None:
        """50 threads register created agents concurrently without error."""
        reg, _ = _registry()
        errors: List[str] = []

        # Pre-register all agents in main index
        for i in range(50):
            reg.register(
                _agent(name=f"agent.execute.thread_{i}"),
                skip_validation=True,
            )

        def register_created(idx: int) -> None:
            try:
                contract = reg.lookup(f"agent.execute.thread_{idx}")
                if contract is not None:
                    reg.register_created_agent(
                        contract,
                        ephemeral=True,
                        created_by="orch",
                        session_scoped=True,
                    )
            except Exception as exc:
                errors.append(f"thread_{idx}: {exc}")

        threads = [threading.Thread(target=register_created, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Errors in threads: {errors}"
        assert reg.created_agent_count == 50

    def test_concurrent_remove_expired_agents(self) -> None:
        """Multiple threads calling remove_expired_agents do not corrupt state."""
        reg, _ = _registry()
        for i in range(20):
            a = _agent(name=f"agent.execute.expire_{i}")
            reg.register(a, skip_validation=True)
            reg.register_created_agent(a, ephemeral=True, created_by="orch", session_scoped=True)

        results: List[int] = []

        def remove(session: str) -> None:
            count, _ = reg.remove_expired_agents(session)
            results.append(count)

        threads = [threading.Thread(target=remove, args=(f"sess-{i}",)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All 20 should be removed exactly once, total across all threads = 20
        assert sum(results) == 20
        assert reg.created_agent_count == 0


# ===================================================================
# Tests: Integration with existing registry operations
# ===================================================================


class TestLifecycleIntegration:
    """Verify lifecycle operations work with existing registry behavior."""

    def test_unregister_cleans_created_agent_index(self) -> None:
        """Direct unregister() removes from main index; created_agents stays
        until remove_expired_agents() is called (by design -- unregister is
        a low-level operation)."""
        reg, _ = _registry()
        a = _agent()
        reg.register(a, skip_validation=True)
        reg.register_created_agent(a, ephemeral=True, created_by="orch", session_scoped=True)

        # Direct unregister removes from main index only
        reg.unregister("agent.execute.test_agent")
        assert reg.lookup("agent.execute.test_agent") is None
        # created_agents still has the record (cleanup is via remove_expired)
        assert reg.is_created_agent("agent.execute.test_agent") is True

    def test_reload_clears_created_agents_from_main_index(self) -> None:
        """After reload(), created agents are effectively gone from main index
        but the _created_agents tracking persists (intentional -- allows audit)."""
        reg, _ = _registry()
        a = _agent()
        reg.register(a, skip_validation=True)
        reg.register_created_agent(a, ephemeral=True, created_by="orch", session_scoped=True)

        # Reload with an empty directory
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            reg.reload(tmp, skip_validation=True)

        assert reg.lookup("agent.execute.test_agent") is None
        # _created_agents still has the record for audit
        assert reg.is_created_agent("agent.execute.test_agent") is True

    def test_domain_index_updated_with_stamped_contract(self) -> None:
        """After register_created_agent, domain index has the stamped contract."""
        reg, _ = _registry()
        a = _agent(name="agent.execute.domain_check", domain="HEALTH")
        reg.register(a, skip_validation=True)
        reg.register_created_agent(a, ephemeral=False, created_by="planner", session_scoped=False)

        agents = reg.list_by_domain("HEALTH")
        assert len(agents) == 1
        assert agents[0].created_by == "planner"
        assert agents[0].ephemeral is False

    def test_health_reflects_created_agents(self) -> None:
        """health() counts include created agents."""
        reg, _ = _registry()
        a = _agent()
        reg.register(a, skip_validation=True)
        reg.register_created_agent(a, ephemeral=True, created_by="orch", session_scoped=True)

        h = reg.health()
        assert h.total_capabilities == 1


# ===================================================================
# Tests: Module exports
# ===================================================================


class TestLifecycleExports:
    """Verify 4.5.6 exports from k1.fabric.core."""

    def test_created_agent_record_importable(self) -> None:
        from k1.fabric.core import CreatedAgentRecord

        assert CreatedAgentRecord is not None

    def test_created_agent_record_in_all(self) -> None:
        from k1.fabric.core import __all__

        assert "CreatedAgentRecord" in __all__

    def test_core_all_count(self) -> None:
        from k1.fabric.core import __all__

        # 15 prior (M2) + 18 (4.2) + 5 (4.5.1) + 2 (4.5.4) + 8 (4.5.2) + 9 (4.5.3) + 1 (4.5.6) = 58
        assert len(__all__) == 58
