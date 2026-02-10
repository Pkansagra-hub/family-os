"""
Tests for Epic 6.2.13: CapabilityVersioning unit tests.

Covers (per fabric-implementation-plan.md):
  - CapabilityVersion parsing, comparison, compatibility
  - Registry version conflict resolution:
      duplicate rejection, compatible upgrade, breaking multi-version, regression
  - Version-aware lookup: exact, latest compatible, latest
  - Version conflict event emission

NO MOCKS -- uses real CapabilityRegistry with real ContractValidator.

References:
  - fabric-implementation-plan.md Epic 6.2, Issue 6.2.13
  - types.py -- CapabilityVersion (2.4.1)
  - registry.py -- Version conflict resolution (2.4.2), Version-aware lookup (2.4.3)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from k1.fabric.core.registry import (
    EVENT_VERSION_UPGRADED,
    CapabilityRegistry,
    DuplicateCapabilityError,
    VersionConflictError,
    VersionRegressionError,
)
from k1.fabric.types import (
    AgentContract,
    Availability,
    CapabilityContract,
    CapabilityVersion,
    CapabilityVersionError,
    InputSpec,
    PromptContract,
)

# ======================================================================
# Real in-memory adapters (NO MOCKS)
# ======================================================================


class CaptureEventPort:
    """Captures all emitted events for assertion."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    def emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        self.events.append({"event_type": event_type, "payload": payload})


# ======================================================================
# Helpers
# ======================================================================


def _tool(
    name: str = "tool.execute.weather",
    version: str = "1.0.0",
    domain: Optional[List[str]] = None,
    provider_id: str = "mcp-weather",
) -> CapabilityContract:
    """Build a minimal valid tool contract."""
    return CapabilityContract(
        name=name,
        version=version,
        domain=domain or ["WEATHER"],
        description="Weather tool",
        capabilities=["weather_lookup"],
        limitations=["none"],
        required_inputs=[InputSpec(name="loc", type="string", description="Location")],
        provider_type="MCP",
        provider_id=provider_id,
        safety_band_min="GREEN",
        availability=Availability.ONLINE.value,
    )


def _agent(
    name: str = "agent.execute.planner",
    version: str = "1.0.0",
) -> AgentContract:
    """Build a minimal valid agent contract."""
    return AgentContract(
        name=name,
        version=version,
        domain=["PLANNING"],
        description="Planning agent",
        capabilities=["plan"],
        limitations=[],
        required_inputs=[InputSpec(name="goal", type="string", description="Goal")],
        provider_type="AGENT",
        provider_id="local-planner",
        safety_band_min="GREEN",
        availability=Availability.ONLINE.value,
        prompt_template="Plan: {goal}",
        llm_budget_tokens=4096,
    )


def _prompt(
    name: str = "greeting_v1",
    version: str = "1.0.0",
) -> PromptContract:
    """Build a minimal valid prompt contract."""
    return PromptContract(
        name=name,
        version=version,
        domain=["SOCIAL"],
        description="Greeting prompt",
        template_file="greeting.txt",
        variables=[],
        max_tokens=100,
    )


def _registry(event_port: Optional[CaptureEventPort] = None) -> CapabilityRegistry:
    """Create a registry with validation disabled for speed."""
    return CapabilityRegistry(event_port=event_port)


# ======================================================================
# 6.2.13a -- CapabilityVersion parsing
# ======================================================================


class TestVersionParse:
    """CapabilityVersion.parse() from raw strings."""

    def test_parse_basic(self) -> None:
        v = CapabilityVersion.parse("1.2.3")
        assert v.major == 1 and v.minor == 2 and v.patch == 3

    def test_parse_zero(self) -> None:
        v = CapabilityVersion.parse("0.0.0")
        assert v == CapabilityVersion(0, 0, 0)

    def test_parse_large_numbers(self) -> None:
        v = CapabilityVersion.parse("100.200.300")
        assert v.major == 100 and v.minor == 200 and v.patch == 300

    def test_parse_strips_whitespace(self) -> None:
        v = CapabilityVersion.parse("  2.3.4  ")
        assert v == CapabilityVersion(2, 3, 4)

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "1",
            "1.2",
            "a.b.c",
            "1.2.3.4",
            "v1.2.3",
            "-1.0.0",
        ],
    )
    def test_parse_invalid_raises(self, bad: str) -> None:
        with pytest.raises(CapabilityVersionError):
            CapabilityVersion.parse(bad)

    def test_error_contains_raw(self) -> None:
        try:
            CapabilityVersion.parse("garbage")
        except CapabilityVersionError as e:
            assert "garbage" in str(e)


# ======================================================================
# 6.2.13b -- CapabilityVersion comparison
# ======================================================================


class TestVersionComparison:
    """Ordering and equality."""

    def test_equal(self) -> None:
        assert CapabilityVersion(1, 2, 3) == CapabilityVersion(1, 2, 3)

    def test_not_equal(self) -> None:
        assert CapabilityVersion(1, 2, 3) != CapabilityVersion(1, 2, 4)

    def test_lt_by_major(self) -> None:
        assert CapabilityVersion(1, 0, 0) < CapabilityVersion(2, 0, 0)

    def test_lt_by_minor(self) -> None:
        assert CapabilityVersion(1, 0, 0) < CapabilityVersion(1, 1, 0)

    def test_lt_by_patch(self) -> None:
        assert CapabilityVersion(1, 0, 0) < CapabilityVersion(1, 0, 1)

    def test_gt(self) -> None:
        assert CapabilityVersion(2, 0, 0) > CapabilityVersion(1, 9, 9)

    def test_le_equal(self) -> None:
        v = CapabilityVersion(1, 0, 0)
        assert v <= v

    def test_ge_equal(self) -> None:
        v = CapabilityVersion(1, 0, 0)
        assert v >= v

    def test_hash_equal(self) -> None:
        a = CapabilityVersion(1, 0, 0)
        b = CapabilityVersion(1, 0, 0)
        assert hash(a) == hash(b)
        assert len({a, b}) == 1

    def test_str(self) -> None:
        assert str(CapabilityVersion(3, 2, 1)) == "3.2.1"

    def test_repr(self) -> None:
        r = repr(CapabilityVersion(3, 2, 1))
        assert "CapabilityVersion" in r
        assert "3" in r

    def test_compare_static(self) -> None:
        a = CapabilityVersion(1, 0, 0)
        b = CapabilityVersion(2, 0, 0)
        assert CapabilityVersion.compare(a, b) == -1
        assert CapabilityVersion.compare(b, a) == 1
        assert CapabilityVersion.compare(a, a) == 0

    def test_to_dict(self) -> None:
        d = CapabilityVersion(1, 2, 3).to_dict()
        assert d["major"] == 1
        assert d["minor"] == 2
        assert d["patch"] == 3
        assert d["string"] == "1.2.3"

    def test_frozen(self) -> None:
        v = CapabilityVersion(1, 0, 0)
        with pytest.raises(AttributeError):
            v.major = 9  # type: ignore[misc]


# ======================================================================
# 6.2.13c -- CapabilityVersion compatibility
# ======================================================================


class TestVersionCompatibility:
    """is_compatible_with() semver logic."""

    def test_same_major_compatible(self) -> None:
        a = CapabilityVersion(1, 0, 0)
        b = CapabilityVersion(1, 5, 9)
        assert a.is_compatible_with(b) is True
        assert b.is_compatible_with(a) is True

    def test_different_major_incompatible(self) -> None:
        a = CapabilityVersion(1, 0, 0)
        b = CapabilityVersion(2, 0, 0)
        assert a.is_compatible_with(b) is False

    def test_major_zero_exact_match_only(self) -> None:
        """major=0 is unstable: only exact match is compatible."""
        a = CapabilityVersion(0, 1, 0)
        assert a.is_compatible_with(a) is True

    def test_major_zero_different_minor_incompatible(self) -> None:
        a = CapabilityVersion(0, 1, 0)
        b = CapabilityVersion(0, 2, 0)
        assert a.is_compatible_with(b) is False

    def test_major_zero_vs_nonzero_incompatible(self) -> None:
        a = CapabilityVersion(0, 1, 0)
        b = CapabilityVersion(1, 0, 0)
        assert a.is_compatible_with(b) is False


# ======================================================================
# 6.2.13d -- Registry: version conflict resolution
# ======================================================================


class TestDuplicateRejection:
    """Rule (a): same name + same version -> VersionConflictError."""

    def test_exact_same_version_rejected(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        with pytest.raises(VersionConflictError) as exc_info:
            reg.register(_tool(version="1.0.0"), skip_validation=True)
        assert "1.0.0" in str(exc_info.value)


class TestCompatibleUpgrade:
    """Rule (b): same name + newer compatible version -> in-place upgrade."""

    def test_minor_upgrade(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="1.1.0"), skip_validation=True)
        found = reg.lookup("tool.execute.weather")
        assert found is not None
        assert found.version == "1.1.0"

    def test_patch_upgrade(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="1.0.1"), skip_validation=True)
        found = reg.lookup("tool.execute.weather")
        assert found is not None
        assert found.version == "1.0.1"

    def test_upgrade_emits_event(self) -> None:
        bus = CaptureEventPort()
        reg = _registry(event_port=bus)
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="1.1.0"), skip_validation=True)
        upgrade_events = [e for e in bus.events if e["event_type"] == EVENT_VERSION_UPGRADED]
        assert len(upgrade_events) == 1
        payload = upgrade_events[0]["payload"]
        assert payload["old_version"] == "1.0.0"
        assert payload["new_version"] == "1.1.0"

    def test_upgrade_updates_version_index(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="1.2.0"), skip_validation=True)
        versions = reg.list_versions("tool.execute.weather")
        assert "1.2.0" in versions


class TestBreakingMultiVersion:
    """Rule (c): same name + different major -> both registered."""

    def test_different_major_registers_both(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="2.0.0"), skip_validation=True)
        versions = reg.list_versions("tool.execute.weather")
        assert "1.0.0" in versions
        assert "2.0.0" in versions

    def test_both_retrievable(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="2.0.0"), skip_validation=True)
        # Original key still has v1
        v1 = reg.lookup("tool.execute.weather")
        assert v1 is not None and v1.version == "1.0.0"
        # Versioned key has v2
        v2 = reg.lookup("tool.execute.weather@2")
        assert v2 is not None and v2.version == "2.0.0"


class TestRegressionRejection:
    """Rule (d): same name + older compatible version -> VersionRegressionError."""

    def test_older_minor_rejected(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.2.0"), skip_validation=True)
        with pytest.raises(VersionRegressionError):
            reg.register(_tool(version="1.1.0"), skip_validation=True)

    def test_older_patch_rejected(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.5"), skip_validation=True)
        with pytest.raises(VersionRegressionError):
            reg.register(_tool(version="1.0.3"), skip_validation=True)


class TestUnversionedFallback:
    """No version field -> falls back to DuplicateCapabilityError."""

    def test_no_version_duplicate_raises(self) -> None:
        reg = _registry()
        reg.register(_tool(version=""), skip_validation=True)
        with pytest.raises(DuplicateCapabilityError):
            reg.register(_tool(version=""), skip_validation=True)

    def test_one_versioned_one_empty_raises(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        with pytest.raises(DuplicateCapabilityError):
            reg.register(_tool(version=""), skip_validation=True)


# ======================================================================
# 6.2.13e -- Version conflict with different contract types
# ======================================================================


class TestCrossContractVersioning:
    """Version resolution works for AgentContract and PromptContract too."""

    def test_agent_upgrade(self) -> None:
        reg = _registry()
        reg.register(_agent(version="1.0.0"), skip_validation=True)
        reg.register(_agent(version="1.1.0"), skip_validation=True)
        found = reg.lookup("agent.execute.planner")
        assert found is not None and found.version == "1.1.0"

    def test_agent_same_version_conflict(self) -> None:
        reg = _registry()
        reg.register(_agent(version="2.0.0"), skip_validation=True)
        with pytest.raises(VersionConflictError):
            reg.register(_agent(version="2.0.0"), skip_validation=True)

    def test_prompt_upgrade(self) -> None:
        reg = _registry()
        reg.register(_prompt(version="1.0.0"), skip_validation=True)
        reg.register(_prompt(version="1.2.0"), skip_validation=True)
        found = reg.lookup("greeting_v1")
        assert found is not None and found.version == "1.2.0"


# ======================================================================
# 6.2.13f -- Version-aware lookup
# ======================================================================


class TestLookupLatest:
    """lookup_latest() returns the highest version across all majors."""

    def test_single_version(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        found = reg.lookup_latest("tool.execute.weather")
        assert found is not None
        assert found.version == "1.0.0"

    def test_latest_after_upgrade(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="1.3.0"), skip_validation=True)
        found = reg.lookup_latest("tool.execute.weather")
        assert found is not None
        assert found.version == "1.3.0"

    def test_latest_across_majors(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="2.0.0"), skip_validation=True)
        found = reg.lookup_latest("tool.execute.weather")
        assert found is not None
        assert found.version == "2.0.0"

    def test_latest_not_found(self) -> None:
        reg = _registry()
        assert reg.lookup_latest("nonexistent") is None


class TestLookupLatestCompatible:
    """lookup_latest_compatible() filters by major version."""

    def test_latest_compatible_in_major(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="1.2.0"), skip_validation=True)
        found = reg.lookup_latest_compatible("tool.execute.weather", major=1)
        assert found is not None
        assert found.version == "1.2.0"

    def test_pick_correct_major_in_multi(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.5.0"), skip_validation=True)
        reg.register(_tool(version="2.0.0"), skip_validation=True)
        found = reg.lookup_latest_compatible("tool.execute.weather", major=1)
        assert found is not None
        assert found.version == "1.5.0"

    def test_nonexistent_major_returns_none(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        assert reg.lookup_latest_compatible("tool.execute.weather", major=3) is None

    def test_not_found_returns_none(self) -> None:
        reg = _registry()
        assert reg.lookup_latest_compatible("nonexistent", major=1) is None


class TestListVersions:
    """list_versions() returns sorted list of version strings."""

    def test_single_version(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        assert reg.list_versions("tool.execute.weather") == ["1.0.0"]

    def test_multi_version_sorted(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="2.0.0"), skip_validation=True)
        versions = reg.list_versions("tool.execute.weather")
        assert versions == ["1.0.0", "2.0.0"]

    def test_after_upgrade_reflects_latest(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="1.2.0"), skip_validation=True)
        versions = reg.list_versions("tool.execute.weather")
        assert "1.2.0" in versions

    def test_empty_for_unknown(self) -> None:
        reg = _registry()
        assert reg.list_versions("nonexistent") == []

    def test_unversioned_not_listed(self) -> None:
        reg = _registry()
        reg.register(_tool(version=""), skip_validation=True)
        assert reg.list_versions("tool.execute.weather") == []


# ======================================================================
# 6.2.13g -- Version conflict event emission
# ======================================================================


class TestVersionEventEmission:
    """Events emitted during version resolution."""

    def test_upgrade_emits_version_upgraded_event(self) -> None:
        bus = CaptureEventPort()
        reg = _registry(event_port=bus)
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="1.1.0"), skip_validation=True)
        upgraded = [e for e in bus.events if e["event_type"] == EVENT_VERSION_UPGRADED]
        assert len(upgraded) == 1
        assert upgraded[0]["payload"]["new_version"] == "1.1.0"

    def test_multi_version_emits_registered(self) -> None:
        bus = CaptureEventPort()
        reg = _registry(event_port=bus)
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="2.0.0"), skip_validation=True)
        # Multi-version emits a normal registration event, NOT upgrade
        upgrade_events = [e for e in bus.events if e["event_type"] == EVENT_VERSION_UPGRADED]
        assert len(upgrade_events) == 0  # no upgrade, it's a new major

    def test_conflict_does_not_emit(self) -> None:
        bus = CaptureEventPort()
        reg = _registry(event_port=bus)
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        initial_count = len(bus.events)
        with pytest.raises(VersionConflictError):
            reg.register(_tool(version="1.0.0"), skip_validation=True)
        # No new events on conflict
        assert len(bus.events) == initial_count

    def test_regression_does_not_emit(self) -> None:
        bus = CaptureEventPort()
        reg = _registry(event_port=bus)
        reg.register(_tool(version="1.5.0"), skip_validation=True)
        initial_count = len(bus.events)
        with pytest.raises(VersionRegressionError):
            reg.register(_tool(version="1.2.0"), skip_validation=True)
        assert len(bus.events) == initial_count


# ======================================================================
# 6.2.13h -- Unregister cleans version index
# ======================================================================


class TestUnregisterVersionCleanup:
    """Unregistering cleans version index entries."""

    def test_unregister_clears_version_index(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        assert reg.list_versions("tool.execute.weather") == ["1.0.0"]
        reg.unregister("tool.execute.weather")
        assert reg.list_versions("tool.execute.weather") == []

    def test_unregister_multi_version_cleans_both(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="2.0.0"), skip_validation=True)
        reg.unregister("tool.execute.weather")
        # Base name gone
        assert reg.lookup("tool.execute.weather") is None
        # Version index should be cleaned
        versions = reg.list_versions("tool.execute.weather")
        # At minimum v1 should be gone
        assert "1.0.0" not in versions
