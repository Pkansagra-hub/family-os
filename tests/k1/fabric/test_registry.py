"""
Unit tests for CapabilityRegistry -- Epic 6.2.3.

Tests the full CapabilityRegistry API:
  - register / unregister
  - lookup (O(1), version-aware)
  - list_by_domain / list_by_type / list_by_provider / list_all
  - update_availability / update_metrics
  - health()
  - Version conflict resolution (dup, upgrade, multi-version, regression)
  - Event emission on lifecycle operations
  - Thread-safety with concurrent register / lookup

Uses real CapabilityRegistry, real ContractValidator, real LocalEventAdapter.
NO MOCKS.

References:
  - fabric-implementation-plan.md Milestone 6, Epic 6.2.3
  - k1/fabric/core/registry.py
"""

from __future__ import annotations

import threading
from typing import List

import pytest

from k1.fabric.adapters.local_event import LocalEventAdapter
from k1.fabric.core.contract_validator import ContractValidator
from k1.fabric.core.registry import (
    EVENT_AVAILABILITY_CHANGED,
    EVENT_CAPABILITY_REGISTERED,
    EVENT_CAPABILITY_UNREGISTERED,
    EVENT_METRICS_UPDATED,
    EVENT_VERSION_UPGRADED,
    CapabilityNotFoundError,
    CapabilityRegistry,
    DuplicateCapabilityError,
    VersionConflictError,
    VersionRegressionError,
)
from k1.fabric.types import CapabilityContract, InputSpec, SafetyBand
from tests.k1.fabric.helpers import create_n_contracts, load_fixture_contract

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry(capture: bool = True) -> tuple[CapabilityRegistry, LocalEventAdapter]:
    """Create a registry + event adapter pair for testing."""
    validator = ContractValidator()
    adapter = LocalEventAdapter(capture_mode=capture)
    reg = CapabilityRegistry(validator=validator, event_port=adapter)  # type: ignore[arg-type]
    return reg, adapter


def _tool_contract(
    name: str = "tool.execute.test_tool",
    version: str = "1.0.0",
    domain: str = "TEST",
    provider_type: str = "MCP",
    provider_id: str = "test-provider",
    availability: str = "ONLINE",
) -> CapabilityContract:
    return CapabilityContract(
        name=name,
        version=version,
        domain=[domain],
        description="Test tool contract",
        capabilities=["test"],
        limitations=[],
        required_inputs=[
            InputSpec(name="x", type="STRING", description="input"),
        ],
        output={"type": "object"},
        provider_type=provider_type,
        provider_id=provider_id,
        safety_band_min=SafetyBand.GREEN.value,
        availability=availability,
    )


# ====================================================================
# Register / Unregister basics
# ====================================================================


class TestRegisterUnregister:
    """register() and unregister() basic operations."""

    def test_register_and_lookup(self, registry: CapabilityRegistry) -> None:
        contract = _tool_contract()
        registry.register(contract, skip_validation=True)
        result = registry.lookup("tool.execute.test_tool")
        assert result is not None
        assert result.name == "tool.execute.test_tool"

    def test_register_populates_contains(self, registry: CapabilityRegistry) -> None:
        contract = _tool_contract()
        registry.register(contract, skip_validation=True)
        assert registry.contains("tool.execute.test_tool") is True
        assert registry.contains("nonexistent") is False

    def test_unregister_removes(self, registry: CapabilityRegistry) -> None:
        contract = _tool_contract()
        registry.register(contract, skip_validation=True)
        removed = registry.unregister("tool.execute.test_tool")
        assert removed is True
        assert registry.lookup("tool.execute.test_tool") is None
        assert registry.contains("tool.execute.test_tool") is False

    def test_unregister_nonexistent_returns_false(self, registry: CapabilityRegistry) -> None:
        assert registry.unregister("nonexistent") is False

    def test_register_with_validation(self) -> None:
        """Register with validation enabled (full 2-phase)."""
        reg, _ = _make_registry()
        contract = _tool_contract()
        # Should succeed with validation
        reg.register(contract, skip_validation=False)
        assert reg.contains("tool.execute.test_tool")

    def test_register_all_4_types(self, registry: CapabilityRegistry) -> None:
        """All 4 contract types can be registered."""
        tool = load_fixture_contract("restaurant_booking")
        agent = load_fixture_contract("invitation_sender")
        prompt = load_fixture_contract("invitation_drafter_v1")
        workflow = load_fixture_contract("weekly_health_check")

        for c in [tool, agent, prompt, workflow]:
            registry.register(c, skip_validation=True)

        assert registry.size == 4
        assert registry.contains("tool.execute.restaurant_booking")
        assert registry.contains("agent.execute.invitation_sender")
        assert registry.contains("invitation_drafter_v1")
        assert registry.contains("workflow.run.weekly_health_check")


# ====================================================================
# Lookup (O(1), version-aware)
# ====================================================================


class TestLookup:
    """lookup(), lookup_latest(), list_versions()."""

    def test_lookup_returns_none_for_missing(self, registry: CapabilityRegistry) -> None:
        assert registry.lookup("nonexistent") is None

    def test_lookup_by_version(self, registry: CapabilityRegistry) -> None:
        contract = _tool_contract(version="1.2.3")
        registry.register(contract, skip_validation=True)
        result = registry.lookup("tool.execute.test_tool", version="1.2.3")
        assert result is not None
        assert result.version == "1.2.3"

    def test_lookup_wrong_version_returns_none(self, registry: CapabilityRegistry) -> None:
        contract = _tool_contract(version="1.0.0")
        registry.register(contract, skip_validation=True)
        result = registry.lookup("tool.execute.test_tool", version="9.9.9")
        assert result is None

    def test_list_versions(self, registry: CapabilityRegistry) -> None:
        v1 = _tool_contract(name="tool.execute.versioned", version="1.0.0")
        v2 = _tool_contract(name="tool.execute.versioned", version="1.1.0")
        registry.register(v1, skip_validation=True)
        registry.register(v2, skip_validation=True)  # upgrade
        versions = registry.list_versions("tool.execute.versioned")
        assert "1.1.0" in versions


# ====================================================================
# Version conflict resolution
# ====================================================================


class TestVersionConflictResolution:
    """register() version conflict rules a-d."""

    def test_same_version_raises_conflict(self, registry: CapabilityRegistry) -> None:
        """Rule a: same name + same version -> VersionConflictError."""
        v1 = _tool_contract(version="1.0.0")
        registry.register(v1, skip_validation=True)
        v1_dup = _tool_contract(version="1.0.0")
        with pytest.raises(VersionConflictError):
            registry.register(v1_dup, skip_validation=True)

    def test_newer_compatible_upgrades(self, registry: CapabilityRegistry) -> None:
        """Rule b: same major, newer minor -> in-place upgrade."""
        v1 = _tool_contract(version="1.0.0")
        v2 = _tool_contract(version="1.1.0")
        registry.register(v1, skip_validation=True)
        registry.register(v2, skip_validation=True)
        result = registry.lookup("tool.execute.test_tool")
        assert result is not None
        assert result.version == "1.1.0"

    def test_different_major_registers_both(self, registry: CapabilityRegistry) -> None:
        """Rule c: different major -> multi-version registration."""
        v1 = _tool_contract(version="1.0.0")
        v2 = _tool_contract(version="2.0.0")
        registry.register(v1, skip_validation=True)
        registry.register(v2, skip_validation=True)
        # Original stays under base name
        r1 = registry.lookup("tool.execute.test_tool")
        assert r1 is not None
        assert r1.version == "1.0.0"
        # New major stored under @major key
        r2 = registry.lookup("tool.execute.test_tool@2")
        assert r2 is not None
        assert r2.version == "2.0.0"

    def test_older_compatible_raises_regression(self, registry: CapabilityRegistry) -> None:
        """Rule d: same major, older minor -> VersionRegressionError."""
        v2 = _tool_contract(version="1.2.0")
        v1 = _tool_contract(version="1.1.0")
        registry.register(v2, skip_validation=True)
        with pytest.raises(VersionRegressionError):
            registry.register(v1, skip_validation=True)

    def test_no_version_duplicate_raises(self, registry: CapabilityRegistry) -> None:
        """No version -> DuplicateCapabilityError on second register."""
        c1 = CapabilityContract(
            name="tool.execute.no_ver",
            version="",
            domain=["TEST"],
            description="No version",
            capabilities=["t"],
            limitations=[],
            required_inputs=[InputSpec(name="x", type="STRING", description="x")],
            output={"type": "object"},
            provider_type="MCP",
            provider_id="p",
            safety_band_min="GREEN",
        )
        c2 = CapabilityContract(
            name="tool.execute.no_ver",
            version="",
            domain=["TEST"],
            description="No version dup",
            capabilities=["t"],
            limitations=[],
            required_inputs=[InputSpec(name="x", type="STRING", description="x")],
            output={"type": "object"},
            provider_type="MCP",
            provider_id="p",
            safety_band_min="GREEN",
        )
        registry.register(c1, skip_validation=True)
        with pytest.raises(DuplicateCapabilityError):
            registry.register(c2, skip_validation=True)


# ====================================================================
# Domain / Type / Provider indexes
# ====================================================================


class TestIndexLookups:
    """list_by_domain(), list_by_type(), list_by_provider()."""

    def test_list_by_domain(self, registry: CapabilityRegistry) -> None:
        c1 = _tool_contract(name="tool.execute.food_one", domain="FOOD")
        c2 = _tool_contract(name="tool.execute.food_two", domain="FOOD")
        c3 = _tool_contract(name="tool.execute.health_one", domain="HEALTH")
        for c in [c1, c2, c3]:
            registry.register(c, skip_validation=True)
        food = registry.list_by_domain("FOOD")
        assert len(food) == 2
        health = registry.list_by_domain("HEALTH")
        assert len(health) == 1
        assert registry.list_by_domain("UNKNOWN") == []

    def test_list_by_type(self, registry: CapabilityRegistry) -> None:
        tool = _tool_contract(name="tool.execute.test_exec")
        registry.register(tool, skip_validation=True)
        results = registry.list_by_type("tool.execute")
        assert len(results) >= 1
        names = [r.name for r in results]
        assert "tool.execute.test_exec" in names

    def test_list_by_provider(self, registry: CapabilityRegistry) -> None:
        c = _tool_contract(provider_id="my-provider")
        registry.register(c, skip_validation=True)
        results = registry.list_by_provider("my-provider")
        assert len(results) == 1
        assert registry.list_by_provider("other") == []

    def test_list_all(self, registry: CapabilityRegistry) -> None:
        contracts = create_n_contracts(5)
        for c in contracts:
            registry.register(c, skip_validation=True)
        assert len(registry.list_all()) == 5

    def test_list_names(self, registry: CapabilityRegistry) -> None:
        contracts = create_n_contracts(3)
        for c in contracts:
            registry.register(c, skip_validation=True)
        names = registry.list_names()
        assert len(names) == 3
        assert names == sorted(names)

    def test_size_property(self, registry: CapabilityRegistry) -> None:
        assert registry.size == 0
        contracts = create_n_contracts(10)
        for c in contracts:
            registry.register(c, skip_validation=True)
        assert registry.size == 10

    def test_unregister_cleans_indexes(self, registry: CapabilityRegistry) -> None:
        c = _tool_contract(name="tool.execute.to_remove", domain="FOOD")
        registry.register(c, skip_validation=True)
        assert len(registry.list_by_domain("FOOD")) == 1
        registry.unregister("tool.execute.to_remove")
        assert len(registry.list_by_domain("FOOD")) == 0


# ====================================================================
# update_availability
# ====================================================================


class TestUpdateAvailability:
    """update_availability() swaps frozen contract + updates metadata."""

    def test_update_availability(self, registry: CapabilityRegistry) -> None:
        c = _tool_contract(availability="ONLINE")
        registry.register(c, skip_validation=True)
        registry.update_availability("tool.execute.test_tool", "DEGRADED")
        result = registry.lookup("tool.execute.test_tool")
        assert result is not None
        assert result.availability == "DEGRADED"

    def test_update_availability_idempotent(self, registry: CapabilityRegistry) -> None:
        c = _tool_contract(availability="ONLINE")
        registry.register(c, skip_validation=True)
        # Same value = no-op
        registry.update_availability("tool.execute.test_tool", "ONLINE")
        result = registry.lookup("tool.execute.test_tool")
        assert result is not None
        assert result.availability == "ONLINE"

    def test_update_availability_not_found(self, registry: CapabilityRegistry) -> None:
        with pytest.raises(CapabilityNotFoundError):
            registry.update_availability("nonexistent", "ONLINE")

    def test_update_availability_invalid_value(self, registry: CapabilityRegistry) -> None:
        c = _tool_contract()
        registry.register(c, skip_validation=True)
        with pytest.raises(ValueError, match="Invalid availability"):
            registry.update_availability("tool.execute.test_tool", "INVALID")

    def test_update_availability_updates_metadata(self, registry: CapabilityRegistry) -> None:
        c = _tool_contract(availability="ONLINE")
        registry.register(c, skip_validation=True)
        registry.update_availability("tool.execute.test_tool", "OFFLINE")
        meta = registry.get_metadata("tool.execute.test_tool")
        assert meta is not None
        assert meta.availability == "OFFLINE"


# ====================================================================
# update_metrics
# ====================================================================


class TestUpdateMetrics:
    """update_metrics() updates rolling averages on frozen contracts."""

    def test_first_invocation(self, registry: CapabilityRegistry) -> None:
        c = _tool_contract()
        registry.register(c, skip_validation=True)
        registry.update_metrics("tool.execute.test_tool", success=True, latency_ms=100)
        result = registry.lookup("tool.execute.test_tool")
        assert result is not None
        assert result.total_invocations_30d == 1
        assert result.success_rate_30d > 0

    def test_multiple_invocations(self, registry: CapabilityRegistry) -> None:
        c = _tool_contract()
        registry.register(c, skip_validation=True)
        for _ in range(5):
            registry.update_metrics("tool.execute.test_tool", success=True, latency_ms=100)
        for _ in range(5):
            registry.update_metrics("tool.execute.test_tool", success=False, latency_ms=200)
        result = registry.lookup("tool.execute.test_tool")
        assert result is not None
        assert result.total_invocations_30d == 10
        assert 0.4 <= result.success_rate_30d <= 0.6

    def test_negative_latency_raises(self, registry: CapabilityRegistry) -> None:
        c = _tool_contract()
        registry.register(c, skip_validation=True)
        with pytest.raises(ValueError, match="latency_ms must be >= 0"):
            registry.update_metrics("tool.execute.test_tool", success=True, latency_ms=-1)

    def test_metrics_not_found(self, registry: CapabilityRegistry) -> None:
        with pytest.raises(CapabilityNotFoundError):
            registry.update_metrics("nonexistent", success=True, latency_ms=100)

    def test_metrics_update_metadata_cache(self, registry: CapabilityRegistry) -> None:
        c = _tool_contract()
        registry.register(c, skip_validation=True)
        registry.update_metrics("tool.execute.test_tool", success=True, latency_ms=150)
        meta = registry.get_metadata("tool.execute.test_tool")
        assert meta is not None
        assert meta.total_invocations_30d == 1
        assert meta.avg_latency_ms == 150


# ====================================================================
# health()
# ====================================================================


class TestHealth:
    """health() returns a RegistryHealth snapshot."""

    def test_empty_health(self, registry: CapabilityRegistry) -> None:
        h = registry.health()
        assert h.total_capabilities == 0
        assert h.by_type_counts == {}
        assert h.by_availability_counts == {}

    def test_health_counts(self, registry: CapabilityRegistry) -> None:
        contracts = create_n_contracts(5)
        for c in contracts:
            registry.register(c, skip_validation=True)
        h = registry.health()
        assert h.total_capabilities == 5
        assert h.index_size_bytes > 0

    def test_health_by_availability(self, registry: CapabilityRegistry) -> None:
        c1 = _tool_contract(name="tool.execute.online_tool", availability="ONLINE")
        c2 = _tool_contract(name="tool.execute.degraded_tool", availability="DEGRADED")
        registry.register(c1, skip_validation=True)
        registry.register(c2, skip_validation=True)
        h = registry.health()
        assert h.by_availability_counts.get("ONLINE", 0) >= 1
        assert h.by_availability_counts.get("DEGRADED", 0) >= 1

    def test_health_to_dict(self, registry: CapabilityRegistry) -> None:
        h = registry.health()
        d = h.to_dict()
        assert "total_capabilities" in d
        assert "by_type_counts" in d
        assert "index_size_bytes" in d


# ====================================================================
# Event emission
# ====================================================================


class TestEventEmission:
    """Registry emits events on lifecycle operations."""

    def test_register_emits_event(self) -> None:
        reg, adapter = _make_registry()
        contract = _tool_contract()
        reg.register(contract, skip_validation=True)
        events = adapter.get_captured(topic=EVENT_CAPABILITY_REGISTERED)
        assert len(events) >= 1
        _, payload = events[0]
        assert payload["name"] == "tool.execute.test_tool"

    def test_unregister_emits_event(self) -> None:
        reg, adapter = _make_registry()
        contract = _tool_contract()
        reg.register(contract, skip_validation=True)
        adapter.clear_captured()
        reg.unregister("tool.execute.test_tool")
        events = adapter.get_captured(topic=EVENT_CAPABILITY_UNREGISTERED)
        assert len(events) >= 1

    def test_upgrade_emits_event(self) -> None:
        reg, adapter = _make_registry()
        v1 = _tool_contract(version="1.0.0")
        v2 = _tool_contract(version="1.1.0")
        reg.register(v1, skip_validation=True)
        adapter.clear_captured()
        reg.register(v2, skip_validation=True)
        events = adapter.get_captured(topic=EVENT_VERSION_UPGRADED)
        assert len(events) >= 1

    def test_availability_change_emits_event(self) -> None:
        reg, adapter = _make_registry()
        contract = _tool_contract(availability="ONLINE")
        reg.register(contract, skip_validation=True)
        adapter.clear_captured()
        reg.update_availability("tool.execute.test_tool", "DEGRADED")
        events = adapter.get_captured(topic=EVENT_AVAILABILITY_CHANGED)
        assert len(events) >= 1
        _, payload = events[0]
        assert payload["old_availability"] == "ONLINE"
        assert payload["new_availability"] == "DEGRADED"

    def test_metrics_update_emits_event(self) -> None:
        reg, adapter = _make_registry()
        contract = _tool_contract()
        reg.register(contract, skip_validation=True)
        adapter.clear_captured()
        reg.update_metrics("tool.execute.test_tool", success=True, latency_ms=100)
        events = adapter.get_captured(topic=EVENT_METRICS_UPDATED)
        assert len(events) >= 1


# ====================================================================
# Bulk operations (100+ contracts)
# ====================================================================


class TestBulkOperations:
    """Registry handles 100+ contracts correctly."""

    def test_register_100_contracts(self, registry: CapabilityRegistry) -> None:
        contracts = create_n_contracts(100)
        for c in contracts:
            registry.register(c, skip_validation=True)
        assert registry.size == 100

    def test_lookup_across_100_contracts(self, registry: CapabilityRegistry) -> None:
        contracts = create_n_contracts(100)
        for c in contracts:
            registry.register(c, skip_validation=True)
        # Spot-check 10 random lookups
        for i in [0, 10, 25, 50, 75, 99]:
            name = f"tool.execute.test_cap_{i:04d}"
            result = registry.lookup(name)
            assert result is not None, f"Lookup failed for {name}"

    def test_list_all_returns_all(self, registry: CapabilityRegistry) -> None:
        contracts = create_n_contracts(50)
        for c in contracts:
            registry.register(c, skip_validation=True)
        assert len(registry.list_all()) == 50


# ====================================================================
# Thread-safety
# ====================================================================


class TestThreadSafety:
    """Concurrent register / lookup operations do not corrupt state."""

    def test_concurrent_register_and_lookup(self, registry: CapabilityRegistry) -> None:
        """20 threads concurrently register, then verify all present."""
        n_threads = 20
        errors: List[str] = []

        def register_worker(idx: int) -> None:
            try:
                c = _tool_contract(
                    name=f"tool.execute.thread_tool_{idx:03d}",
                    provider_id=f"thread-{idx}",
                )
                registry.register(c, skip_validation=True)
            except Exception as exc:
                errors.append(f"Thread {idx} failed: {exc}")

        threads = [threading.Thread(target=register_worker, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert errors == [], f"Thread errors: {errors}"
        assert registry.size == n_threads

        # Verify all lookups work
        for i in range(n_threads):
            name = f"tool.execute.thread_tool_{i:03d}"
            assert registry.contains(name), f"Missing after concurrent register: {name}"

    def test_concurrent_register_and_update(self, registry: CapabilityRegistry) -> None:
        """Mix of register + update_availability under concurrency."""
        # Pre-register 10 contracts
        for i in range(10):
            c = _tool_contract(
                name=f"tool.execute.upd_tool_{i:03d}",
                provider_id=f"upd-{i}",
            )
            registry.register(c, skip_validation=True)

        errors: List[str] = []

        def update_worker(idx: int) -> None:
            try:
                name = f"tool.execute.upd_tool_{idx:03d}"
                registry.update_availability(name, "DEGRADED")
            except Exception as exc:
                errors.append(f"Update thread {idx}: {exc}")

        threads = [threading.Thread(target=update_worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert errors == []
        for i in range(10):
            result = registry.lookup(f"tool.execute.upd_tool_{i:03d}")
            assert result is not None
            assert result.availability == "DEGRADED"


# ====================================================================
# Metadata cache
# ====================================================================


class TestMetadataCache:
    """get_metadata() returns hot-cache metadata."""

    def test_metadata_after_register(self, registry: CapabilityRegistry) -> None:
        c = _tool_contract(domain="FOOD")
        registry.register(c, skip_validation=True)
        meta = registry.get_metadata("tool.execute.test_tool")
        assert meta is not None
        assert meta.name == "tool.execute.test_tool"
        assert "FOOD" in meta.domain_tags
        assert meta.provider_type == "MCP"

    def test_metadata_returns_none_for_missing(self, registry: CapabilityRegistry) -> None:
        assert registry.get_metadata("nonexistent") is None

    def test_metadata_removed_on_unregister(self, registry: CapabilityRegistry) -> None:
        c = _tool_contract()
        registry.register(c, skip_validation=True)
        registry.unregister("tool.execute.test_tool")
        assert registry.get_metadata("tool.execute.test_tool") is None
