"""I-0.5.10.2 -- SessionStateProdAdapter integration tests.

Verifies the production adapter reads real SessionState sections:
  1. Create real SS via SessionStateFactory.create_for_testing()
  2. Inject into SessionStateProdAdapter
  3. Read persona + control → verify real section data returned
  4. Read unknown section → verify omitted gracefully
  5. Verify IStateReadPort protocol conformance
  6. Verify degraded mode on error
"""

from __future__ import annotations

from typing import Any

import pytest

from k1.model_hub.adapters.session_state_prod import SessionStateProdAdapter
from k1.model_hub.ports.state_read_port import IStateReadPort, StateSnapshot
from k1.sessionstate.factory import SessionStateFactory

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ss_manager():
    """Create a real SessionStateManager for testing."""
    manager = SessionStateFactory.create_for_testing(session_id="test-prod-adapter")
    manager.start()
    yield manager
    manager.stop()


@pytest.fixture()
def adapter(ss_manager) -> SessionStateProdAdapter:
    """Create a SessionStateProdAdapter wrapping a real manager."""
    return SessionStateProdAdapter(ss_manager)


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """SessionStateProdAdapter satisfies IStateReadPort."""

    def test_isinstance_check(self, adapter: SessionStateProdAdapter) -> None:
        assert isinstance(adapter, IStateReadPort)

    def test_has_read_method(self, adapter: SessionStateProdAdapter) -> None:
        assert hasattr(adapter, "read")
        assert callable(adapter.read)

    def test_no_write_methods(self, adapter: SessionStateProdAdapter) -> None:
        """MH-01: adapter must have NO write methods."""
        for name in ("write", "set", "update", "delete", "mutate", "put"):
            assert not hasattr(adapter, name), f"Adapter has forbidden method: {name}"


# ---------------------------------------------------------------------------
# Read persona section
# ---------------------------------------------------------------------------


class TestReadPersona:
    """Read persona section from real SessionState."""

    @pytest.mark.asyncio
    async def test_read_persona_returns_data(self, adapter: SessionStateProdAdapter) -> None:
        result = await adapter.read(["persona"])
        assert isinstance(result, StateSnapshot)
        assert "persona" in result.sections
        persona = result.sections["persona"]
        assert isinstance(persona, dict)
        # Persona must have standard fields
        assert "personality" in persona
        assert "name" in persona  # section name field

    @pytest.mark.asyncio
    async def test_persona_has_personality_fields(self, adapter: SessionStateProdAdapter) -> None:
        result = await adapter.read(["persona"])
        persona = result.sections["persona"]
        personality = persona["personality"]
        # Default personality profile has these fields
        assert "warmth" in personality
        assert "formality" in personality
        assert "verbosity" in personality


# ---------------------------------------------------------------------------
# Read control section
# ---------------------------------------------------------------------------


class TestReadControl:
    """Read control section from real SessionState."""

    @pytest.mark.asyncio
    async def test_read_control_returns_data(self, adapter: SessionStateProdAdapter) -> None:
        result = await adapter.read(["control"])
        assert isinstance(result, StateSnapshot)
        assert "control" in result.sections
        control = result.sections["control"]
        assert isinstance(control, dict)

    @pytest.mark.asyncio
    async def test_control_has_session_id(self, adapter: SessionStateProdAdapter) -> None:
        result = await adapter.read(["control"])
        control = result.sections["control"]
        assert "session_id" in control
        assert control["session_id"] == "test-prod-adapter"


# ---------------------------------------------------------------------------
# Multi-section read
# ---------------------------------------------------------------------------


class TestMultiSectionRead:
    """Read multiple sections in a single call."""

    @pytest.mark.asyncio
    async def test_read_both_persona_and_control(self, adapter: SessionStateProdAdapter) -> None:
        result = await adapter.read(["persona", "control"])
        assert "persona" in result.sections
        assert "control" in result.sections

    @pytest.mark.asyncio
    async def test_read_empty_list(self, adapter: SessionStateProdAdapter) -> None:
        result = await adapter.read([])
        assert result.sections == {}


# ---------------------------------------------------------------------------
# Unknown / missing sections
# ---------------------------------------------------------------------------


class TestUnknownSections:
    """Unknown sections are silently omitted."""

    @pytest.mark.asyncio
    async def test_unknown_section_omitted(self, adapter: SessionStateProdAdapter) -> None:
        result = await adapter.read(["nonexistent_section"])
        assert "nonexistent_section" not in result.sections
        assert result.sections == {}

    @pytest.mark.asyncio
    async def test_mix_known_and_unknown(self, adapter: SessionStateProdAdapter) -> None:
        result = await adapter.read(["control", "nonexistent", "persona"])
        assert "control" in result.sections
        assert "persona" in result.sections
        assert "nonexistent" not in result.sections
        assert len(result.sections) == 2


# ---------------------------------------------------------------------------
# Error handling / degraded mode
# ---------------------------------------------------------------------------


class TestDegradedMode:
    """On catastrophic error, returns empty StateSnapshot."""

    @pytest.mark.asyncio
    async def test_broken_manager_returns_empty(self) -> None:
        """If manager.get_section() explodes, returns empty snapshot."""

        class _BrokenManager:
            def get_section(self, name: str) -> Any:
                raise RuntimeError("Manager is dead")

        adapter = SessionStateProdAdapter(_BrokenManager())
        result = await adapter.read(["persona", "control"])
        assert isinstance(result, StateSnapshot)
        assert result.sections == {}

    @pytest.mark.asyncio
    async def test_none_manager_section_omitted(self) -> None:
        """If get_section() returns None, section is omitted."""

        class _NoneManager:
            def get_section(self, name: str) -> Any:
                return None

        adapter = SessionStateProdAdapter(_NoneManager())
        result = await adapter.read(["persona"])
        assert result.sections == {}

    @pytest.mark.asyncio
    async def test_dict_section_passes_through(self) -> None:
        """If section is already a dict, it passes through as-is."""

        class _DictManager:
            def get_section(self, name: str) -> Any:
                return {"key": "value", "nested": {"a": 1}}

        adapter = SessionStateProdAdapter(_DictManager())
        result = await adapter.read(["persona"])
        assert result.sections["persona"] == {"key": "value", "nested": {"a": 1}}


# ---------------------------------------------------------------------------
# Slot efficiency
# ---------------------------------------------------------------------------


class TestSlotEfficiency:
    """Adapter uses __slots__ for memory efficiency."""

    def test_has_slots(self, adapter: SessionStateProdAdapter) -> None:
        assert hasattr(SessionStateProdAdapter, "__slots__")
        assert "_manager" in SessionStateProdAdapter.__slots__

    def test_no_dict(self, adapter: SessionStateProdAdapter) -> None:
        assert not hasattr(adapter, "__dict__")
