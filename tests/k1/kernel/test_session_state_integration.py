"""P1.6 — Session-state wiring integration tests.

Validates the full read chain from consumer (Orchestrator, Planner,
Fabric) through adapter through ``SessionRoutingStateReader`` to
a fake SSM.  No mocks on the adapters themselves — only the SSM
layer is stubbed.

Test categories (per 09_wiring_plan Issue P1.6):
  (a) Orchestrator reads safety_band from a real session
  (b) Planner reads beliefs from a real session
  (c) Shared Fabric reader reads context from a real session
  (d) Two sessions have isolated state

Ref docs: 08_end_to_end_wiring_requirements, 05_port_adapter_mapping.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

import pytest

from k1.fabric.ports.state_reader import ISessionStateReader, SessionSnapshot
from k1.kernel.adapters.session_routing_reader import SessionRoutingStateReader
from k1.orchestrator.adapters.state_read_adapter import StateReadAdapter
from k1.planner.adapters.session_state_adapter import SessionStateReadAdapter

# ---------------------------------------------------------------------------
# Helpers — lightweight SSM stubs
# ---------------------------------------------------------------------------


class _FakeSection:
    """Mimics a SessionState section object with to_dict()."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def to_dict(self) -> dict:
        return dict(self._data)


class _FakeSSM:
    """Minimal SessionStateManager stub."""

    def __init__(self, sections: Dict[str, dict]) -> None:
        self._sections = {k: _FakeSection(v) for k, v in sections.items()}

    def get_section(self, name: str) -> _FakeSection:
        if name not in self._sections:
            from k1.sessionstate.errors import SectionNotFoundError

            raise SectionNotFoundError(name)
        return self._sections[name]

    def get_all_section_sizes(self) -> Dict[str, int]:
        return {k: 100 for k in self._sections}


def _build_routing_reader(
    sessions: Dict[str, _FakeSSM],
) -> SessionRoutingStateReader:
    """Build a SessionRoutingStateReader over a dict of fake SSMs."""
    return SessionRoutingStateReader(
        session_lookup=lambda sid: sessions.get(sid),
    )


# ---------------------------------------------------------------------------
# (a) Orchestrator reads safety_band from a real session
# ---------------------------------------------------------------------------


class TestOrchestratorReadsSessionState:
    """StateReadAdapter → SessionRoutingStateReader → SSM chain."""

    @pytest.fixture()
    def wiring(self):
        ssm = _FakeSSM(
            {
                "control": {"safety_band": "GREEN", "mode": "normal"},
                "beliefs_active": {"facts": ["sky is blue"]},
            }
        )
        sessions = {"session-orch-1": ssm}
        routing_reader = _build_routing_reader(sessions)
        adapter = StateReadAdapter(state_reader=routing_reader)
        return adapter, sessions

    @pytest.mark.asyncio
    async def test_read_section_safety_band(self, wiring) -> None:
        adapter, _ = wiring
        result = await adapter.read_section("session-orch-1", "control")
        assert result is not None
        assert result["safety_band"] == "GREEN"

    @pytest.mark.asyncio
    async def test_read_sections_multiple(self, wiring) -> None:
        adapter, _ = wiring
        result = await adapter.read_sections("session-orch-1", ["control", "beliefs_active"])
        assert "control" in result
        assert "beliefs_active" in result
        assert result["control"]["safety_band"] == "GREEN"
        assert result["beliefs_active"]["facts"] == ["sky is blue"]

    @pytest.mark.asyncio
    async def test_get_snapshot_returns_all(self, wiring) -> None:
        adapter, _ = wiring
        snap = await adapter.get_snapshot("session-orch-1")
        assert isinstance(snap, SessionSnapshot)
        assert snap.session_id == "session-orch-1"
        assert "control" in snap.sections
        assert "beliefs_active" in snap.sections

    @pytest.mark.asyncio
    async def test_unknown_session_returns_none(self, wiring) -> None:
        adapter, _ = wiring
        result = await adapter.read_section("no-such-session", "control")
        assert result is None


# ---------------------------------------------------------------------------
# (b) Planner reads beliefs from a real session
# ---------------------------------------------------------------------------


class TestPlannerReadsSessionState:
    """SessionStateReadAdapter → SessionRoutingStateReader → SSM chain."""

    @pytest.fixture()
    def wiring(self):
        ssm = _FakeSSM(
            {
                "beliefs_active": {
                    "facts": ["child age 5", "loves dinosaurs"],
                    "confidence": 0.9,
                },
                "scoreboard": {"math": 7, "reading": 5},
            }
        )
        sessions = {"session-plan-1": ssm}
        routing_reader = _build_routing_reader(sessions)
        # Planner adapter pre-binds session_id
        adapter = SessionStateReadAdapter(
            reader=routing_reader,
            session_id="session-plan-1",
        )
        return adapter, sessions

    @pytest.mark.asyncio
    async def test_read_sections_beliefs(self, wiring) -> None:
        adapter, _ = wiring
        snap = await adapter.read_sections(["beliefs_active"])
        # Returns SessionSnapshot (adapter wraps dict → snapshot)
        assert isinstance(snap, SessionSnapshot)
        assert "beliefs_active" in snap.sections
        assert snap.sections["beliefs_active"]["facts"][0] == "child age 5"

    @pytest.mark.asyncio
    async def test_read_sections_multiple(self, wiring) -> None:
        adapter, _ = wiring
        snap = await adapter.read_sections(["beliefs_active", "scoreboard"])
        assert "beliefs_active" in snap.sections
        assert "scoreboard" in snap.sections
        assert snap.sections["scoreboard"]["math"] == 7

    @pytest.mark.asyncio
    async def test_read_sections_missing_section_omitted(self, wiring) -> None:
        adapter, _ = wiring
        snap = await adapter.read_sections(["beliefs_active", "nonexistent_section"])
        assert "beliefs_active" in snap.sections
        assert "nonexistent_section" not in snap.sections

    @pytest.mark.asyncio
    async def test_session_id_is_bound(self, wiring) -> None:
        """Planner adapter should use the pre-bound session_id."""
        adapter, _ = wiring
        snap = await adapter.read_sections(["beliefs_active"])
        assert snap.session_id == "session-plan-1"


# ---------------------------------------------------------------------------
# (c) Shared Fabric reader reads context from a real session
# ---------------------------------------------------------------------------


class TestFabricReadsSessionState:
    """ISessionStateReader (routing reader) used directly as Fabric does."""

    @pytest.fixture()
    def wiring(self):
        ssm = _FakeSSM(
            {
                "control": {"safety_band": "AMBER", "mode": "guided"},
                "affective_now": {"valence": 0.6, "arousal": 0.3},
                "persona": {"name": "Koda", "traits": ["patient", "warm"]},
            }
        )
        sessions = {"session-fab-1": ssm}
        routing_reader = _build_routing_reader(sessions)
        return routing_reader, sessions

    def test_protocol_conformance(self, wiring) -> None:
        reader, _ = wiring
        assert isinstance(reader, ISessionStateReader)

    def test_read_section_affective(self, wiring) -> None:
        reader, _ = wiring
        result = reader.read_section("session-fab-1", "affective_now")
        assert result is not None
        assert result["valence"] == 0.6

    def test_read_sections_for_context_build(self, wiring) -> None:
        """Fabric's ContextBuilder reads multiple sections at once."""
        reader, _ = wiring
        result = reader.read_sections("session-fab-1", ["control", "affective_now", "persona"])
        assert len(result) == 3
        assert result["control"]["safety_band"] == "AMBER"
        assert result["persona"]["name"] == "Koda"

    def test_get_snapshot_for_policy_engine(self, wiring) -> None:
        """Fabric's PolicyEngine uses full snapshot for routing decisions."""
        reader, _ = wiring
        snap = reader.get_snapshot("session-fab-1")
        assert isinstance(snap, SessionSnapshot)
        assert snap.session_id == "session-fab-1"
        assert "control" in snap.sections
        assert "affective_now" in snap.sections
        assert "persona" in snap.sections
        assert snap.timestamp_ms > 0


# ---------------------------------------------------------------------------
# (d) Two sessions have isolated state
# ---------------------------------------------------------------------------


class TestTwoSessionIsolation:
    """All three adapters see isolated state per session_id."""

    @pytest.fixture()
    def wiring(self):
        ssm_child_a = _FakeSSM(
            {
                "control": {"safety_band": "GREEN"},
                "beliefs_active": {"facts": ["age 5"]},
            }
        )
        ssm_child_b = _FakeSSM(
            {
                "control": {"safety_band": "RED"},
                "beliefs_active": {"facts": ["age 12"]},
            }
        )
        sessions = {"child-a": ssm_child_a, "child-b": ssm_child_b}
        routing_reader = _build_routing_reader(sessions)
        orch_adapter = StateReadAdapter(state_reader=routing_reader)
        planner_a = SessionStateReadAdapter(reader=routing_reader, session_id="child-a")
        planner_b = SessionStateReadAdapter(reader=routing_reader, session_id="child-b")
        return orch_adapter, planner_a, planner_b, routing_reader

    @pytest.mark.asyncio
    async def test_orchestrator_sees_different_safety_bands(self, wiring) -> None:
        orch, _, _, _ = wiring
        ctrl_a = await orch.read_section("child-a", "control")
        ctrl_b = await orch.read_section("child-b", "control")
        assert ctrl_a["safety_band"] == "GREEN"
        assert ctrl_b["safety_band"] == "RED"

    @pytest.mark.asyncio
    async def test_planner_adapters_are_isolated(self, wiring) -> None:
        _, planner_a, planner_b, _ = wiring
        snap_a = await planner_a.read_sections(["beliefs_active"])
        snap_b = await planner_b.read_sections(["beliefs_active"])
        assert snap_a.sections["beliefs_active"]["facts"] == ["age 5"]
        assert snap_b.sections["beliefs_active"]["facts"] == ["age 12"]
        # Session IDs should match the pre-bound IDs
        assert snap_a.session_id == "child-a"
        assert snap_b.session_id == "child-b"

    def test_fabric_reader_isolation(self, wiring) -> None:
        _, _, _, reader = wiring
        snap_a = reader.get_snapshot("child-a")
        snap_b = reader.get_snapshot("child-b")
        assert snap_a.sections["control"]["safety_band"] == "GREEN"
        assert snap_b.sections["control"]["safety_band"] == "RED"
        assert "beliefs_active" in snap_a.sections
        assert "beliefs_active" in snap_b.sections

    @pytest.mark.asyncio
    async def test_mutation_in_one_session_doesnt_leak(self, wiring) -> None:
        """Changing SSM data in one session doesn't affect the other."""
        orch, _, _, _ = wiring
        # Read initial values
        ctrl_a = await orch.read_section("child-a", "control")
        assert ctrl_a["safety_band"] == "GREEN"

        ctrl_b = await orch.read_section("child-b", "control")
        assert ctrl_b["safety_band"] == "RED"

        # Verify they're independent dict copies
        ctrl_a["safety_band"] = "MODIFIED"
        fresh_a = await orch.read_section("child-a", "control")
        assert fresh_a["safety_band"] == "GREEN"  # original unaffected
