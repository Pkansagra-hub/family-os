"""
Integration tests for CapabilityRegistry 2.2.5-2.2.8.

Tests:
  2.2.5 -- update_availability()
  2.2.6 -- update_metrics()
  2.2.7 -- reload()
  2.2.8 -- health()

Covers:
  - Frozen-contract copy-on-write via dataclasses.replace
  - Index consistency after updates
  - Metadata cache synchronization
  - Event emission (with and without event port)
  - Edge cases (not found, invalid values, no-op)
  - reload() from real YAML directory
  - health() snapshot accuracy
  - Concurrency under 50 threads
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from k1.fabric.core.registry import (
    EVENT_AVAILABILITY_CHANGED,
    EVENT_METRICS_UPDATED,
    EVENT_REGISTRY_RELOADED,
    CapabilityNotFoundError,
    CapabilityRegistry,
    RegistryHealth,
)
from k1.fabric.types import AgentContract, Availability, CapabilityContract, InputSpec

# =========================================================================
# Fixtures
# =========================================================================


def _tool_contract(
    name: str = "tool.execute.weather",
    domain: Optional[List[str]] = None,
    provider_id: str = "mcp-weather",
    availability: str = Availability.ONLINE.value,
) -> CapabilityContract:
    """Build a minimal valid tool contract for testing."""
    return CapabilityContract(
        name=name,
        version="1.0.0",
        domain=domain or ["WEATHER"],
        description="Get weather forecast",
        capabilities=["weather_lookup"],
        limitations=["no_historical"],
        required_inputs=[InputSpec(name="location", type="string", description="City name")],
        provider_type="MCP",
        provider_id=provider_id,
        safety_band_min="GREEN",
        availability=availability,
    )


def _agent_contract(
    name: str = "agent.execute.planner",
    domain: Optional[List[str]] = None,
) -> AgentContract:
    """Build a minimal valid agent contract for testing."""
    return AgentContract(
        name=name,
        version="1.0.0",
        domain=domain or ["PLANNING"],
        description="Planning agent",
        capabilities=["plan_creation"],
        limitations=[],
        required_inputs=[InputSpec(name="goal", type="string", description="Goal")],
        provider_type="AGENT",
        provider_id="local-planner",
        safety_band_min="GREEN",
        availability=Availability.ONLINE.value,
        prompt_template="You are a planner.",
        max_tool_calls=5,
    )


class FakeEventPort:
    """Capture events for assertion."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    def emit(self, event_type: str, payload: Any) -> None:
        self.events.append({"type": event_type, "payload": payload})


@pytest.fixture
def event_port() -> FakeEventPort:
    return FakeEventPort()


@pytest.fixture
def registry(event_port: FakeEventPort) -> CapabilityRegistry:
    return CapabilityRegistry(event_port=event_port)


@pytest.fixture
def registry_no_port() -> CapabilityRegistry:
    return CapabilityRegistry()


@pytest.fixture
def loaded_registry(registry: CapabilityRegistry) -> CapabilityRegistry:
    """Registry pre-loaded with 3 diverse contracts."""
    registry.register(_tool_contract(), skip_validation=True)
    registry.register(_agent_contract(), skip_validation=True)
    registry.register(
        CapabilityContract(
            name="tool.execute.translate",
            version="2.1.0",
            domain=["LANGUAGE", "WEATHER"],
            description="Translate text",
            capabilities=["translate"],
            limitations=[],
            required_inputs=[InputSpec(name="text", type="string", description="Text")],
            provider_type="MCP",
            provider_id="mcp-translate",
            safety_band_min="GREEN",
            availability=Availability.ONLINE.value,
        ),
        skip_validation=True,
    )
    return registry


# =========================================================================
# 2.2.5 -- update_availability()
# =========================================================================


class TestUpdateAvailability:
    """Tests for CapabilityRegistry.update_availability()."""

    def test_online_to_degraded(
        self, loaded_registry: CapabilityRegistry, event_port: FakeEventPort
    ) -> None:
        """Transition from ONLINE to DEGRADED updates contract and metadata."""
        loaded_registry.update_availability("tool.execute.weather", Availability.DEGRADED.value)

        contract = loaded_registry.lookup("tool.execute.weather")
        assert contract is not None
        assert contract.availability == Availability.DEGRADED.value

        meta = loaded_registry.get_metadata("tool.execute.weather")
        assert meta is not None
        assert meta.availability == Availability.DEGRADED.value

    def test_online_to_offline(self, loaded_registry: CapabilityRegistry) -> None:
        """Transition from ONLINE to OFFLINE."""
        loaded_registry.update_availability("tool.execute.weather", Availability.OFFLINE.value)
        contract = loaded_registry.lookup("tool.execute.weather")
        assert contract is not None
        assert contract.availability == Availability.OFFLINE.value

    def test_offline_to_online(self, loaded_registry: CapabilityRegistry) -> None:
        """Recovery: OFFLINE -> ONLINE."""
        loaded_registry.update_availability("tool.execute.weather", Availability.OFFLINE.value)
        loaded_registry.update_availability("tool.execute.weather", Availability.ONLINE.value)
        contract = loaded_registry.lookup("tool.execute.weather")
        assert contract is not None
        assert contract.availability == Availability.ONLINE.value

    def test_noop_same_availability(
        self, loaded_registry: CapabilityRegistry, event_port: FakeEventPort
    ) -> None:
        """No-op when setting to current availability (no event emitted)."""
        # Clear prior registration events
        event_port.events.clear()
        loaded_registry.update_availability("tool.execute.weather", Availability.ONLINE.value)
        avail_events = [e for e in event_port.events if e["type"] == EVENT_AVAILABILITY_CHANGED]
        assert len(avail_events) == 0

    def test_not_found_raises(self, loaded_registry: CapabilityRegistry) -> None:
        """CapabilityNotFoundError for unknown name."""
        with pytest.raises(CapabilityNotFoundError, match="ghost"):
            loaded_registry.update_availability("ghost", Availability.OFFLINE.value)

    def test_invalid_availability_raises(self, loaded_registry: CapabilityRegistry) -> None:
        """ValueError for invalid availability string."""
        with pytest.raises(ValueError, match="Invalid availability"):
            loaded_registry.update_availability("tool.execute.weather", "BROKEN")

    def test_event_emitted(
        self, loaded_registry: CapabilityRegistry, event_port: FakeEventPort
    ) -> None:
        """Availability change emits EVENT_AVAILABILITY_CHANGED."""
        event_port.events.clear()
        loaded_registry.update_availability("tool.execute.weather", Availability.DEGRADED.value)
        avail_events = [e for e in event_port.events if e["type"] == EVENT_AVAILABILITY_CHANGED]
        assert len(avail_events) == 1
        payload = avail_events[0]["payload"]
        assert payload["name"] == "tool.execute.weather"
        assert payload["old_availability"] == Availability.ONLINE.value
        assert payload["new_availability"] == Availability.DEGRADED.value

    def test_index_consistency_after_update(self, loaded_registry: CapabilityRegistry) -> None:
        """After update, list_by_domain returns the NEW contract reference."""
        loaded_registry.update_availability("tool.execute.weather", Availability.DEGRADED.value)

        # by_domain should return new contract
        weather_caps = loaded_registry.list_by_domain("WEATHER")
        weather_names = [c.name for c in weather_caps]
        assert "tool.execute.weather" in weather_names
        for c in weather_caps:
            if c.name == "tool.execute.weather":
                assert c.availability == Availability.DEGRADED.value

        # by_type should also be updated
        tool_caps = loaded_registry.list_by_type("tool.execute")
        for c in tool_caps:
            if c.name == "tool.execute.weather":
                assert c.availability == Availability.DEGRADED.value

    def test_frozen_contract_not_mutated(self, loaded_registry: CapabilityRegistry) -> None:
        """Original contract object is NOT mutated (new object created)."""
        original = loaded_registry.lookup("tool.execute.weather")
        loaded_registry.update_availability("tool.execute.weather", Availability.OFFLINE.value)
        updated = loaded_registry.lookup("tool.execute.weather")

        # Different objects
        assert original is not updated
        # Original still has old value
        assert original.availability == Availability.ONLINE.value
        assert updated.availability == Availability.OFFLINE.value

    def test_no_event_port_works(self, registry_no_port: CapabilityRegistry) -> None:
        """update_availability works fine without event port."""
        registry_no_port.register(_tool_contract(), skip_validation=True)
        registry_no_port.update_availability("tool.execute.weather", Availability.DEGRADED.value)
        c = registry_no_port.lookup("tool.execute.weather")
        assert c is not None
        assert c.availability == Availability.DEGRADED.value


# =========================================================================
# 2.2.6 -- update_metrics()
# =========================================================================


class TestUpdateMetrics:
    """Tests for CapabilityRegistry.update_metrics()."""

    def test_first_invocation(self, loaded_registry: CapabilityRegistry) -> None:
        """First invocation: rate = 1.0 (success), latency = exact value."""
        loaded_registry.update_metrics("tool.execute.weather", success=True, latency_ms=100)

        contract = loaded_registry.lookup("tool.execute.weather")
        assert contract is not None
        assert contract.total_invocations_30d == 1
        assert contract.success_rate_30d == 1.0
        assert contract.avg_latency_ms == 100

    def test_first_failure(self, loaded_registry: CapabilityRegistry) -> None:
        """First invocation that fails: rate = 0.0."""
        loaded_registry.update_metrics("tool.execute.weather", success=False, latency_ms=50)

        contract = loaded_registry.lookup("tool.execute.weather")
        assert contract is not None
        assert contract.total_invocations_30d == 1
        assert contract.success_rate_30d == 0.0

    def test_multiple_invocations_running_average(
        self, loaded_registry: CapabilityRegistry
    ) -> None:
        """Multiple invocations produce correct running average."""
        loaded_registry.update_metrics("tool.execute.weather", success=True, latency_ms=100)
        loaded_registry.update_metrics("tool.execute.weather", success=True, latency_ms=200)
        loaded_registry.update_metrics("tool.execute.weather", success=False, latency_ms=300)

        contract = loaded_registry.lookup("tool.execute.weather")
        assert contract is not None
        assert contract.total_invocations_30d == 3
        # success_rate: (1 + 1 + 0) / 3 = 0.666...
        assert abs(contract.success_rate_30d - 2.0 / 3.0) < 0.001

    def test_ema_latency(self, loaded_registry: CapabilityRegistry) -> None:
        """EMA latency converges toward recent values (alpha=0.3)."""
        loaded_registry.update_metrics("tool.execute.weather", success=True, latency_ms=100)
        loaded_registry.update_metrics("tool.execute.weather", success=True, latency_ms=200)

        contract = loaded_registry.lookup("tool.execute.weather")
        assert contract is not None
        # First: 100, second: int(0.3 * 200 + 0.7 * 100) = int(130) = 130
        assert contract.avg_latency_ms == 130

    def test_metadata_cache_synced(self, loaded_registry: CapabilityRegistry) -> None:
        """Metadata cache reflects updated metrics."""
        loaded_registry.update_metrics("tool.execute.weather", success=True, latency_ms=50)

        meta = loaded_registry.get_metadata("tool.execute.weather")
        assert meta is not None
        assert meta.total_invocations_30d == 1
        assert meta.success_rate_30d == 1.0
        assert meta.avg_latency_ms == 50

    def test_not_found_raises(self, loaded_registry: CapabilityRegistry) -> None:
        """CapabilityNotFoundError for unknown name."""
        with pytest.raises(CapabilityNotFoundError):
            loaded_registry.update_metrics("ghost", success=True, latency_ms=10)

    def test_negative_latency_raises(self, loaded_registry: CapabilityRegistry) -> None:
        """ValueError for negative latency."""
        with pytest.raises(ValueError, match="latency_ms must be >= 0"):
            loaded_registry.update_metrics("tool.execute.weather", success=True, latency_ms=-1)

    def test_event_emitted(
        self, loaded_registry: CapabilityRegistry, event_port: FakeEventPort
    ) -> None:
        """update_metrics emits EVENT_METRICS_UPDATED."""
        event_port.events.clear()
        loaded_registry.update_metrics("tool.execute.weather", success=True, latency_ms=42)
        metrics_events = [e for e in event_port.events if e["type"] == EVENT_METRICS_UPDATED]
        assert len(metrics_events) == 1
        payload = metrics_events[0]["payload"]
        assert payload["name"] == "tool.execute.weather"
        assert payload["total_invocations_30d"] == 1

    def test_index_consistency_after_metrics(self, loaded_registry: CapabilityRegistry) -> None:
        """After metrics update, list_by_domain returns updated contract."""
        loaded_registry.update_metrics("tool.execute.weather", success=True, latency_ms=100)

        weather_caps = loaded_registry.list_by_domain("WEATHER")
        for c in weather_caps:
            if c.name == "tool.execute.weather":
                assert c.total_invocations_30d == 1
                assert c.avg_latency_ms == 100

    def test_frozen_contract_replaced(self, loaded_registry: CapabilityRegistry) -> None:
        """Original contract object is replaced, not mutated."""
        original = loaded_registry.lookup("tool.execute.weather")
        loaded_registry.update_metrics("tool.execute.weather", success=True, latency_ms=100)
        updated = loaded_registry.lookup("tool.execute.weather")
        assert original is not updated
        assert original.total_invocations_30d == 0
        assert updated.total_invocations_30d == 1

    def test_zero_latency_accepted(self, loaded_registry: CapabilityRegistry) -> None:
        """Latency of 0 is valid (cached result)."""
        loaded_registry.update_metrics("tool.execute.weather", success=True, latency_ms=0)
        contract = loaded_registry.lookup("tool.execute.weather")
        assert contract is not None
        assert contract.avg_latency_ms == 0


# =========================================================================
# 2.2.7 -- reload()
# =========================================================================


class TestReload:
    """Tests for CapabilityRegistry.reload()."""

    # Complete schema-compliant YAML for testing
    TOOL_YAML = """\
tool_contract:
  name: tool.execute.weather
  version: "1.0.0"
  domain: [WEATHER]
  description: Get weather
  capabilities: [weather_lookup]
  limitations: [no_historical]
  required_inputs:
    - name: location
      type: string
      description: City name
  output:
    type: object
    properties:
      temp:
        type: number
  provider_type: MCP
  provider_id: mcp-weather
  safety_band_min: GREEN
  availability: ONLINE
"""

    AGENT_YAML = """\
agent_contract:
  name: agent.execute.planner
  version: "1.0.0"
  domain: [PLANNING]
  description: Planner agent
  capabilities: [plan_creation]
  limitations: []
  required_inputs:
    - name: goal
      type: string
      description: Goal
  output:
    type: object
    properties:
      plan:
        type: string
  provider_type: AGENT
  provider_id: local-planner
  safety_band_min: GREEN
  availability: ONLINE
  prompt_template: You are a planner.
  tools_granted: []
  llm_budget_tokens: 1000
  max_tool_calls: 5
  max_execution_time_ms: 30000
"""

    def test_reload_from_yaml_directory(self, registry: CapabilityRegistry, tmp_path: Path) -> None:
        """Reload discovers and parses YAML files from subdirectories."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        (tools_dir / "weather.yaml").write_text(self.TOOL_YAML, encoding="utf-8")

        result = registry.reload(tmp_path)

        assert result["loaded"] == 1
        assert result["failed"] == 0
        assert registry.size == 1
        assert registry.contains("tool.execute.weather")

    def test_reload_clears_old_registrations(
        self, loaded_registry: CapabilityRegistry, tmp_path: Path
    ) -> None:
        """Reload replaces all existing registrations."""
        assert loaded_registry.size == 3

        # Reload from empty directory
        (tmp_path / "tools").mkdir()
        result = loaded_registry.reload(tmp_path)

        assert result["loaded"] == 0
        assert loaded_registry.size == 0

    def test_reload_records_failures(self, registry: CapabilityRegistry, tmp_path: Path) -> None:
        """Invalid YAML files are recorded as failures."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        (tools_dir / "bad.yaml").write_text("not: a: valid: yaml: {{", encoding="utf-8")

        result = registry.reload(tmp_path)

        assert result["loaded"] == 0
        assert result["failed"] == 1
        assert len(result["errors"]) == 1

    def test_reload_sets_timestamp(self, registry: CapabilityRegistry, tmp_path: Path) -> None:
        """Reload sets last_reload_at timestamp."""
        (tmp_path / "tools").mkdir()
        registry.reload(tmp_path)

        h = registry.health()
        assert h.last_reload_at != ""
        # Should be a valid ISO timestamp
        assert "T" in h.last_reload_at

    def test_reload_emits_event(
        self, registry: CapabilityRegistry, event_port: FakeEventPort, tmp_path: Path
    ) -> None:
        """Reload emits EVENT_REGISTRY_RELOADED."""
        (tmp_path / "tools").mkdir()
        event_port.events.clear()
        registry.reload(tmp_path)

        reload_events = [e for e in event_port.events if e["type"] == EVENT_REGISTRY_RELOADED]
        assert len(reload_events) == 1
        assert reload_events[0]["payload"]["loaded"] == 0

    def test_reload_multiple_subdirs(self, registry: CapabilityRegistry, tmp_path: Path) -> None:
        """Reload scans tools/, agents/, prompts/, workflows/ subdirs."""
        for subdir in ["tools", "agents", "prompts", "workflows"]:
            (tmp_path / subdir).mkdir()

        (tmp_path / "tools" / "weather.yaml").write_text(self.TOOL_YAML, encoding="utf-8")
        (tmp_path / "agents" / "planner.yaml").write_text(self.AGENT_YAML, encoding="utf-8")

        result = registry.reload(tmp_path)
        assert result["loaded"] == 2
        assert registry.contains("tool.execute.weather")
        assert registry.contains("agent.execute.planner")

    def test_reload_handles_missing_subdirs(
        self, registry: CapabilityRegistry, tmp_path: Path
    ) -> None:
        """Reload works when subdirectories don't exist."""
        result = registry.reload(tmp_path)
        assert result["loaded"] == 0
        assert result["failed"] == 0

    def test_reload_duplicate_names_kept_first(
        self, registry: CapabilityRegistry, tmp_path: Path
    ) -> None:
        """When two files define same name, first wins, second recorded as error."""
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()

        (tools_dir / "weather_a.yaml").write_text(self.TOOL_YAML, encoding="utf-8")
        (tools_dir / "weather_b.yaml").write_text(self.TOOL_YAML, encoding="utf-8")

        result = registry.reload(tmp_path)
        assert result["loaded"] == 1
        # The duplicate is recorded as an error
        dup_errors = [e for e in result["errors"] if "Duplicate" in e["error"]]
        assert len(dup_errors) == 1


# =========================================================================
# 2.2.8 -- health()
# =========================================================================


class TestHealth:
    """Tests for CapabilityRegistry.health()."""

    def test_empty_registry(self, registry: CapabilityRegistry) -> None:
        """Health of empty registry."""
        h = registry.health()
        assert isinstance(h, RegistryHealth)
        assert h.total_capabilities == 0
        assert h.by_type_counts == {}
        assert h.by_availability_counts == {}
        assert h.index_size_bytes > 0  # dict overhead
        assert h.last_reload_at == ""

    def test_counts_after_registration(self, loaded_registry: CapabilityRegistry) -> None:
        """Health reflects correct counts after registration."""
        h = loaded_registry.health()
        assert h.total_capabilities == 3
        # tool.execute: 2 (weather + translate), agent.execute: 1 (planner)
        assert h.by_type_counts.get("tool.execute") == 2
        assert h.by_type_counts.get("agent.execute") == 1
        # All ONLINE
        assert h.by_availability_counts.get("ONLINE") == 3

    def test_health_reflects_availability_changes(
        self, loaded_registry: CapabilityRegistry
    ) -> None:
        """Health availability counts update after update_availability."""
        loaded_registry.update_availability("tool.execute.weather", Availability.OFFLINE.value)
        h = loaded_registry.health()
        assert h.by_availability_counts.get("ONLINE") == 2
        assert h.by_availability_counts.get("OFFLINE") == 1

    def test_health_is_frozen(self, loaded_registry: CapabilityRegistry) -> None:
        """RegistryHealth is a frozen dataclass."""
        h = loaded_registry.health()
        with pytest.raises(AttributeError):
            h.total_capabilities = 99  # type: ignore[misc]

    def test_health_to_dict(self, loaded_registry: CapabilityRegistry) -> None:
        """RegistryHealth.to_dict() serializes correctly."""
        h = loaded_registry.health()
        d = h.to_dict()
        assert isinstance(d, dict)
        assert d["total_capabilities"] == 3
        assert isinstance(d["by_type_counts"], dict)
        assert isinstance(d["by_availability_counts"], dict)

    def test_health_after_unregister(self, loaded_registry: CapabilityRegistry) -> None:
        """Health counts decrease after unregister."""
        loaded_registry.unregister("tool.execute.weather")
        h = loaded_registry.health()
        assert h.total_capabilities == 2

    def test_index_size_positive(self, loaded_registry: CapabilityRegistry) -> None:
        """Index size is always positive (dict memory overhead)."""
        h = loaded_registry.health()
        assert h.index_size_bytes > 0


# =========================================================================
# Concurrency tests
# =========================================================================


class TestConcurrency:
    """Thread-safety tests for update_availability and update_metrics."""

    def test_concurrent_availability_updates(self, registry: CapabilityRegistry) -> None:
        """50 threads toggling availability don't corrupt indexes."""
        # Register 10 contracts
        for i in range(10):
            registry.register(
                _tool_contract(
                    name=f"tool.execute.cap_{i}",
                    domain=[f"DOM_{i}"],
                    provider_id=f"prov_{i}",
                ),
                skip_validation=True,
            )

        statuses = [
            Availability.ONLINE.value,
            Availability.DEGRADED.value,
            Availability.OFFLINE.value,
        ]
        errors: List[str] = []

        def toggle(idx: int) -> None:
            try:
                name = f"tool.execute.cap_{idx % 10}"
                for status in statuses:
                    registry.update_availability(name, status)
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=toggle, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == [], f"Errors during concurrent updates: {errors}"
        assert registry.size == 10

    def test_concurrent_metrics_updates(self, registry: CapabilityRegistry) -> None:
        """50 threads updating metrics don't corrupt state."""
        registry.register(
            _tool_contract(name="tool.execute.hotpath"),
            skip_validation=True,
        )

        errors: List[str] = []

        def update(idx: int) -> None:
            try:
                for _ in range(10):
                    registry.update_metrics(
                        "tool.execute.hotpath",
                        success=(idx % 2 == 0),
                        latency_ms=idx * 10,
                    )
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=update, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == []
        contract = registry.lookup("tool.execute.hotpath")
        assert contract is not None
        assert contract.total_invocations_30d == 500  # 50 threads * 10 each
