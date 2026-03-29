"""
Integration tests for Capability Versioning (Epic 2.4, issues 2.4.1-2.4.3).

Tests:
  2.4.1 -- CapabilityVersion type (parse, compare, compatibility)
  2.4.2 -- Version conflict resolution in CapabilityRegistry.register()
  2.4.3 -- Backward compatibility rules (version-aware lookup)

Covers:
  - Semver parsing (valid, invalid, edge cases)
  - Comparison operators (==, <, >, <=, >=)
  - Compatibility rules (same major=compatible, major=0=unstable)
  - Version conflict: same version -> VersionConflictError
  - Version upgrade: newer compatible -> in-place upgrade
  - Multi-version: different major -> register both
  - Version regression: older compatible -> VersionRegressionError
  - Unversioned contracts: legacy duplicate behavior
  - lookup(version=...) exact match
  - lookup_latest() across all majors
  - lookup_latest_compatible(name, major) within one major
  - list_versions() sorted ascending
  - unregister() cleans _by_version and versioned keys
  - Event emission for upgrade and multi-version scenarios
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from k1.fabric.core.registry import (
    EVENT_CAPABILITY_REGISTERED,
    EVENT_CAPABILITY_UNREGISTERED,
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

# =========================================================================
# Test Helpers
# =========================================================================


class FakeEventPort:
    """Captures emitted events for assertion."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    def emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        self.events.append({"event_type": event_type, "payload": payload})


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


def _registry(event_port: Optional[FakeEventPort] = None) -> CapabilityRegistry:
    """Create a registry with validation disabled for speed."""
    return CapabilityRegistry(event_port=event_port)


# =========================================================================
# 2.4.1 -- CapabilityVersion Type
# =========================================================================


class TestCapabilityVersionParse:
    """Parsing semver strings."""

    def test_parse_basic(self) -> None:
        v = CapabilityVersion.parse("1.2.3")
        assert v.major == 1
        assert v.minor == 2
        assert v.patch == 3

    def test_parse_zero(self) -> None:
        v = CapabilityVersion.parse("0.0.0")
        assert v == CapabilityVersion(0, 0, 0)

    def test_parse_large_numbers(self) -> None:
        v = CapabilityVersion.parse("100.200.300")
        assert v.major == 100
        assert v.minor == 200
        assert v.patch == 300

    def test_parse_strips_whitespace(self) -> None:
        v = CapabilityVersion.parse("  1.2.3  ")
        assert v == CapabilityVersion(1, 2, 3)

    @pytest.mark.parametrize(
        "bad",
        [
            "",
            "1",
            "1.2",
            "1.2.3.4",
            "a.b.c",
            "1.2.x",
            "v1.2.3",
            "1.2.3-alpha",
            "-1.0.0",
            "1.0.0 extra",
        ],
    )
    def test_parse_invalid(self, bad: str) -> None:
        with pytest.raises(CapabilityVersionError) as exc_info:
            CapabilityVersion.parse(bad)
        assert bad.strip() in str(exc_info.value)


class TestCapabilityVersionComparison:
    """Ordering and equality."""

    def test_equal(self) -> None:
        assert CapabilityVersion(1, 2, 3) == CapabilityVersion(1, 2, 3)

    def test_not_equal(self) -> None:
        assert CapabilityVersion(1, 2, 3) != CapabilityVersion(1, 2, 4)

    def test_lt_by_major(self) -> None:
        assert CapabilityVersion(1, 9, 9) < CapabilityVersion(2, 0, 0)

    def test_lt_by_minor(self) -> None:
        assert CapabilityVersion(1, 2, 9) < CapabilityVersion(1, 3, 0)

    def test_lt_by_patch(self) -> None:
        assert CapabilityVersion(1, 2, 3) < CapabilityVersion(1, 2, 4)

    def test_gt(self) -> None:
        assert CapabilityVersion(2, 0, 0) > CapabilityVersion(1, 9, 9)

    def test_le_equal(self) -> None:
        assert CapabilityVersion(1, 0, 0) <= CapabilityVersion(1, 0, 0)

    def test_le_less(self) -> None:
        assert CapabilityVersion(1, 0, 0) <= CapabilityVersion(1, 0, 1)

    def test_ge_equal(self) -> None:
        assert CapabilityVersion(1, 0, 0) >= CapabilityVersion(1, 0, 0)

    def test_ge_greater(self) -> None:
        assert CapabilityVersion(1, 0, 1) >= CapabilityVersion(1, 0, 0)

    def test_hash_equal(self) -> None:
        v1 = CapabilityVersion(1, 2, 3)
        v2 = CapabilityVersion(1, 2, 3)
        assert hash(v1) == hash(v2)
        assert len({v1, v2}) == 1

    def test_hash_different(self) -> None:
        v1 = CapabilityVersion(1, 2, 3)
        v2 = CapabilityVersion(1, 2, 4)
        assert len({v1, v2}) == 2

    def test_compare_static_less(self) -> None:
        assert (
            CapabilityVersion.compare(CapabilityVersion(1, 0, 0), CapabilityVersion(2, 0, 0)) == -1
        )

    def test_compare_static_equal(self) -> None:
        assert (
            CapabilityVersion.compare(CapabilityVersion(1, 0, 0), CapabilityVersion(1, 0, 0)) == 0
        )

    def test_compare_static_greater(self) -> None:
        assert (
            CapabilityVersion.compare(CapabilityVersion(2, 0, 0), CapabilityVersion(1, 0, 0)) == 1
        )

    def test_str(self) -> None:
        assert str(CapabilityVersion(1, 2, 3)) == "1.2.3"

    def test_repr(self) -> None:
        assert "CapabilityVersion(1, 2, 3)" in repr(CapabilityVersion(1, 2, 3))


class TestCapabilityVersionCompatibility:
    """Compatibility rules."""

    def test_same_major_compatible(self) -> None:
        v1 = CapabilityVersion(1, 0, 0)
        v2 = CapabilityVersion(1, 5, 3)
        assert v1.is_compatible_with(v2)
        assert v2.is_compatible_with(v1)

    def test_different_major_incompatible(self) -> None:
        v1 = CapabilityVersion(1, 0, 0)
        v2 = CapabilityVersion(2, 0, 0)
        assert not v1.is_compatible_with(v2)
        assert not v2.is_compatible_with(v1)

    def test_major_zero_unstable_exact_match_only(self) -> None:
        v1 = CapabilityVersion(0, 1, 0)
        v2 = CapabilityVersion(0, 1, 0)
        assert v1.is_compatible_with(v2)

    def test_major_zero_different_minor_incompatible(self) -> None:
        v1 = CapabilityVersion(0, 1, 0)
        v2 = CapabilityVersion(0, 2, 0)
        assert not v1.is_compatible_with(v2)

    def test_major_zero_vs_nonzero_incompatible(self) -> None:
        v1 = CapabilityVersion(0, 1, 0)
        v2 = CapabilityVersion(1, 0, 0)
        assert not v1.is_compatible_with(v2)

    def test_to_dict(self) -> None:
        v = CapabilityVersion(1, 2, 3)
        d = v.to_dict()
        assert d == {"major": 1, "minor": 2, "patch": 3, "string": "1.2.3"}

    def test_frozen(self) -> None:
        v = CapabilityVersion(1, 0, 0)
        with pytest.raises(AttributeError):
            v.major = 2  # type: ignore[misc]


# =========================================================================
# 2.4.2 -- Version Conflict Resolution
# =========================================================================


class TestVersionConflictSameVersion:
    """Rule (a): same name + same version -> VersionConflictError."""

    def test_exact_same_version_raises(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        with pytest.raises(VersionConflictError) as exc_info:
            reg.register(_tool(version="1.0.0"), skip_validation=True)
        assert "1.0.0" in str(exc_info.value)
        assert exc_info.value.name == "tool.execute.weather"
        assert exc_info.value.version == "1.0.0"

    def test_same_version_different_patch_not_conflict(self) -> None:
        """1.0.0 and 1.0.1 are NOT the same version (upgrade scenario)."""
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        # Should succeed as an upgrade (1.0.1 > 1.0.0, same major)
        reg.register(_tool(version="1.0.1"), skip_validation=True)
        result = reg.lookup("tool.execute.weather")
        assert result is not None
        assert result.version == "1.0.1"


class TestVersionUpgrade:
    """Rule (b): same name + newer compatible -> UPGRADE in-place."""

    def test_upgrade_minor(self) -> None:
        ep = FakeEventPort()
        reg = _registry(event_port=ep)
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="1.1.0"), skip_validation=True)

        # Old version replaced
        result = reg.lookup("tool.execute.weather")
        assert result is not None
        assert result.version == "1.1.0"

        # Only one entry in registry
        assert reg.size == 1
        assert "tool.execute.weather" in reg.list_names()

    def test_upgrade_emits_event(self) -> None:
        ep = FakeEventPort()
        reg = _registry(event_port=ep)
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="1.2.0"), skip_validation=True)

        upgrade_events = [e for e in ep.events if e["event_type"] == EVENT_VERSION_UPGRADED]
        assert len(upgrade_events) == 1
        assert upgrade_events[0]["payload"]["old_version"] == "1.0.0"
        assert upgrade_events[0]["payload"]["new_version"] == "1.2.0"

    def test_upgrade_updates_version_index(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        assert reg.list_versions("tool.execute.weather") == ["1.0.0"]

        reg.register(_tool(version="1.3.0"), skip_validation=True)
        # Old version removed, new version present
        assert reg.list_versions("tool.execute.weather") == ["1.3.0"]

    def test_upgrade_preserves_domain_index(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0", domain=["WEATHER"]), skip_validation=True)
        reg.register(_tool(version="1.1.0", domain=["WEATHER"]), skip_validation=True)
        by_domain = reg.list_by_domain("WEATHER")
        assert len(by_domain) == 1
        assert by_domain[0].version == "1.1.0"

    def test_upgrade_preserves_type_index(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="1.1.0"), skip_validation=True)
        by_type = reg.list_by_type("tool.execute")
        assert len(by_type) == 1
        assert by_type[0].version == "1.1.0"

    def test_upgrade_preserves_metadata(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="1.1.0"), skip_validation=True)
        meta = reg.get_metadata("tool.execute.weather")
        assert meta is not None


class TestVersionMultiVersion:
    """Rule (c): different major -> register both."""

    def test_different_major_registers_both(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="2.0.0"), skip_validation=True)

        # Original under base name
        v1 = reg.lookup("tool.execute.weather")
        assert v1 is not None
        assert v1.version == "1.0.0"

        # New under versioned key
        v2 = reg.lookup("tool.execute.weather@2")
        assert v2 is not None
        assert v2.version == "2.0.0"

    def test_different_major_both_in_version_index(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="2.0.0"), skip_validation=True)

        versions = reg.list_versions("tool.execute.weather")
        assert "1.0.0" in versions
        assert "2.0.0" in versions

    def test_different_major_emits_registered_with_multi_version(self) -> None:
        ep = FakeEventPort()
        reg = _registry(event_port=ep)
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="2.0.0"), skip_validation=True)

        registered_events = [e for e in ep.events if e["event_type"] == EVENT_CAPABILITY_REGISTERED]
        # Two registered events: one for v1 and one for v2
        assert len(registered_events) == 2
        multi = [e for e in registered_events if e["payload"].get("multi_version")]
        assert len(multi) == 1
        assert multi[0]["payload"]["name"] == "tool.execute.weather@2"


class TestVersionRegression:
    """Rule (d): same name + older compatible version -> VersionRegressionError."""

    def test_older_compatible_raises(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.5.0"), skip_validation=True)
        with pytest.raises(VersionRegressionError) as exc_info:
            reg.register(_tool(version="1.3.0"), skip_validation=True)
        assert exc_info.value.name == "tool.execute.weather"
        assert exc_info.value.old_version == "1.5.0"
        assert exc_info.value.new_version == "1.3.0"

    def test_older_patch_raises(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.2.5"), skip_validation=True)
        with pytest.raises(VersionRegressionError):
            reg.register(_tool(version="1.2.3"), skip_validation=True)


class TestVersionUnversioned:
    """Legacy behavior when contracts have no version string."""

    def test_empty_version_falls_back_to_duplicate(self) -> None:
        reg = _registry()
        reg.register(_tool(version=""), skip_validation=True)
        with pytest.raises(DuplicateCapabilityError):
            reg.register(_tool(version=""), skip_validation=True)

    def test_one_versioned_one_empty_falls_back_to_duplicate(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        # Second contract has no version -- can't do version resolution
        with pytest.raises(DuplicateCapabilityError):
            reg.register(_tool(version=""), skip_validation=True)


class TestVersionConflictWithAgentContract:
    """Version conflict rules apply to all contract types."""

    def test_agent_upgrade(self) -> None:
        reg = _registry()
        reg.register(_agent(version="1.0.0"), skip_validation=True)
        reg.register(_agent(version="1.1.0"), skip_validation=True)
        result = reg.lookup("agent.execute.planner")
        assert result is not None
        assert result.version == "1.1.0"

    def test_agent_same_version_conflict(self) -> None:
        reg = _registry()
        reg.register(_agent(version="2.0.0"), skip_validation=True)
        with pytest.raises(VersionConflictError):
            reg.register(_agent(version="2.0.0"), skip_validation=True)

    def test_prompt_upgrade(self) -> None:
        reg = _registry()
        reg.register(_prompt(version="1.0.0"), skip_validation=True)
        reg.register(_prompt(version="1.1.0"), skip_validation=True)
        result = reg.lookup("greeting_v1")
        assert result is not None
        assert result.version == "1.1.0"


# =========================================================================
# 2.4.3 -- Backward Compatibility / Version-Aware Lookup
# =========================================================================


class TestLookupWithVersion:
    """lookup(name, version=...) for exact version match."""

    def test_lookup_exact_version(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        result = reg.lookup("tool.execute.weather", version="1.0.0")
        assert result is not None
        assert result.version == "1.0.0"

    def test_lookup_nonexistent_version(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        assert reg.lookup("tool.execute.weather", version="2.0.0") is None

    def test_lookup_nonexistent_name(self) -> None:
        reg = _registry()
        assert reg.lookup("nonexistent", version="1.0.0") is None

    def test_lookup_multi_version_by_version(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="2.0.0"), skip_validation=True)

        v1 = reg.lookup("tool.execute.weather", version="1.0.0")
        v2 = reg.lookup("tool.execute.weather", version="2.0.0")
        assert v1 is not None and v1.version == "1.0.0"
        assert v2 is not None and v2.version == "2.0.0"


class TestLookupLatest:
    """lookup_latest() across all majors."""

    def test_latest_single_version(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.2.3"), skip_validation=True)
        result = reg.lookup_latest("tool.execute.weather")
        assert result is not None
        assert result.version == "1.2.3"

    def test_latest_after_upgrade(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="1.5.0"), skip_validation=True)
        result = reg.lookup_latest("tool.execute.weather")
        assert result is not None
        assert result.version == "1.5.0"

    def test_latest_multi_version(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="2.0.0"), skip_validation=True)
        result = reg.lookup_latest("tool.execute.weather")
        assert result is not None
        assert result.version == "2.0.0"

    def test_latest_not_found(self) -> None:
        reg = _registry()
        assert reg.lookup_latest("nonexistent") is None


class TestLookupLatestCompatible:
    """lookup_latest_compatible(name, major) within one major."""

    def test_latest_compatible_in_major(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="1.3.0"), skip_validation=True)
        # After upgrade: only 1.3.0 should be in index
        result = reg.lookup_latest_compatible("tool.execute.weather", major=1)
        assert result is not None
        assert result.version == "1.3.0"

    def test_latest_compatible_specific_major_in_multi(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.5.0"), skip_validation=True)
        reg.register(_tool(version="2.0.0"), skip_validation=True)

        v1 = reg.lookup_latest_compatible("tool.execute.weather", major=1)
        v2 = reg.lookup_latest_compatible("tool.execute.weather", major=2)
        assert v1 is not None and v1.version == "1.5.0"
        assert v2 is not None and v2.version == "2.0.0"

    def test_latest_compatible_nonexistent_major(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        assert reg.lookup_latest_compatible("tool.execute.weather", major=3) is None

    def test_latest_compatible_not_found(self) -> None:
        reg = _registry()
        assert reg.lookup_latest_compatible("nonexistent", major=1) is None


class TestListVersions:
    """list_versions() sorted ascending."""

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

    def test_empty_for_unknown(self) -> None:
        reg = _registry()
        assert reg.list_versions("nonexistent") == []

    def test_unversioned_not_in_list(self) -> None:
        reg = _registry()
        reg.register(_tool(version=""), skip_validation=True)
        assert reg.list_versions("tool.execute.weather") == []


class TestUnregisterWithVersions:
    """unregister() cleans _by_version and versioned keys."""

    def test_unregister_cleans_version_index(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        assert reg.list_versions("tool.execute.weather") == ["1.0.0"]
        reg.unregister("tool.execute.weather")
        assert reg.list_versions("tool.execute.weather") == []

    def test_unregister_removes_versioned_keys(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="2.0.0"), skip_validation=True)

        assert reg.contains("tool.execute.weather")
        assert reg.contains("tool.execute.weather@2")

        reg.unregister("tool.execute.weather")

        assert not reg.contains("tool.execute.weather")
        assert not reg.contains("tool.execute.weather@2")
        assert reg.size == 0

    def test_unregister_emits_event(self) -> None:
        ep = FakeEventPort()
        reg = _registry(event_port=ep)
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.unregister("tool.execute.weather")

        unreg_events = [e for e in ep.events if e["event_type"] == EVENT_CAPABILITY_UNREGISTERED]
        assert len(unreg_events) == 1


class TestUpgradeSequence:
    """Multi-step upgrade sequences."""

    def test_triple_upgrade(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="1.1.0"), skip_validation=True)
        reg.register(_tool(version="1.2.0"), skip_validation=True)
        result = reg.lookup("tool.execute.weather")
        assert result is not None
        assert result.version == "1.2.0"
        assert reg.size == 1

    def test_upgrade_then_multi_version(self) -> None:
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="1.5.0"), skip_validation=True)
        reg.register(_tool(version="2.0.0"), skip_validation=True)
        assert reg.lookup("tool.execute.weather").version == "1.5.0"
        assert reg.lookup("tool.execute.weather@2").version == "2.0.0"
        assert reg.size == 2

    def test_multi_version_then_upgrade_v1(self) -> None:
        """Register v1 and v2, then upgrade v1 to v1.1."""
        reg = _registry()
        reg.register(_tool(version="1.0.0"), skip_validation=True)
        reg.register(_tool(version="2.0.0"), skip_validation=True)
        # Now upgrade v1 -> v1.1
        reg.register(_tool(version="1.1.0"), skip_validation=True)
        assert reg.lookup("tool.execute.weather").version == "1.1.0"
        assert reg.lookup("tool.execute.weather@2").version == "2.0.0"
