"""
Integration tests for ModuleLoader 2.3.1-2.3.4.

Tests:
  2.3.1 -- ModuleLoader lifecycle (start, stop, properties)
  2.3.2 -- Hot-reload watcher (create, modify, delete detection)
  2.3.3 -- scan_directory() (recursive discovery, ScanResult)
  2.3.4 -- register_from_dict() (programmatic registration)

Covers:
  - Initial scan from real YAML files on disk
  - Hot-reload detects new, modified, and deleted files
  - Validation failure keeps old contract, emits event
  - register_from_dict with auto-detect and explicit type
  - Missing directories handled gracefully
  - Lifecycle: start/stop idempotency
  - Event emission tracking
  - File-to-name tracking (_file_map integrity)
"""

from __future__ import annotations

import textwrap
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

from k1.fabric.core.contract_validator import ContractValidator
from k1.fabric.core.module_loader import (
    EVENT_CONTRACT_HOT_RELOADED,
    EVENT_CONTRACT_REMOVED,
    EVENT_CONTRACT_VALIDATION_FAILED,
    ModuleLoader,
    ScanResult,
)
from k1.fabric.core.registry import (
    CapabilityRegistry,
    DuplicateCapabilityError,
    VersionConflictError,
)

# =========================================================================
# Test Helpers
# =========================================================================

VALID_TOOL_YAML = textwrap.dedent(
    """\
    tool_contract:
      name: tool.execute.weather
      version: "1.0.0"
      description: Get weather forecast
      domain:
        - WEATHER
      capabilities:
        - weather_lookup
      limitations:
        - no_historical_data
      required_inputs:
        - name: location
          type: string
          description: City name
      output:
        type: object
        properties:
          temperature:
            type: number
          conditions:
            type: string
      provider_type: MCP
      provider_id: mcp-weather-001
      safety_band_min: GREEN
      availability: ONLINE
"""
)

VALID_TOOL_YAML_V2 = textwrap.dedent(
    """\
    tool_contract:
      name: tool.execute.weather
      version: "2.0.0"
      description: Get weather forecast v2
      domain:
        - WEATHER
        - ENVIRONMENT
      capabilities:
        - weather_lookup
        - forecast_extended
      limitations:
        - no_historical_data
      required_inputs:
        - name: location
          type: string
          description: City or coordinates
      output:
        type: object
        properties:
          temperature:
            type: number
          conditions:
            type: string
          forecast:
            type: string
      provider_type: MCP
      provider_id: mcp-weather-002
      safety_band_min: GREEN
      availability: ONLINE
"""
)

VALID_AGENT_YAML = textwrap.dedent(
    """\
    agent_contract:
      name: agent.execute.planner
      version: "1.0.0"
      description: Planning agent
      domain:
        - PLANNING
      required_inputs:
        - name: goal
          type: string
          description: Goal to plan
      prompt_template: "Plan the following goal: {{goal}}"
      tools_granted:
        - tool.execute.weather
      llm_budget_tokens: 4096
      max_tool_calls: 10
      max_execution_time_ms: 30000
      output:
        type: object
        properties:
          plan:
            type: string
      provider_type: AGENT
      safety_band_min: GREEN
      availability: ONLINE
"""
)

VALID_PROMPT_YAML = textwrap.dedent(
    """\
    prompt_contract:
      name: greeting_v1
      version: "1.0.0"
      description: Greeting prompt
      domain:
        - SOCIAL
      variables:
        - name: user_name
          type: STRING
          required: true
          description: User name to greet
      template_file: greeting.txt
      max_tokens: 512
      output_format: TEXT
"""
)

INVALID_YAML = textwrap.dedent(
    """\
    tool_contract:
      name: ""
      version: "bad"
"""
)

BROKEN_YAML = "{{{{ not: valid: yaml: ["


class FakeEventPort:
    """Captures emitted events for assertion."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def emit(self, event_type: str, payload: Any) -> None:
        with self._lock:
            self.events.append({"type": event_type, "payload": payload})

    def events_of_type(self, event_type: str) -> List[Dict[str, Any]]:
        with self._lock:
            return [e for e in self.events if e["type"] == event_type]

    def clear(self) -> None:
        with self._lock:
            self.events.clear()


@pytest.fixture
def tmp_contracts_dir(tmp_path: Path) -> Path:
    """Create a temporary contracts directory with standard subdirs."""
    for subdir in ("tools", "agents", "prompts", "workflows"):
        (tmp_path / subdir).mkdir()
    return tmp_path


@pytest.fixture
def event_port() -> FakeEventPort:
    return FakeEventPort()


@pytest.fixture
def validator() -> ContractValidator:
    return ContractValidator()


@pytest.fixture
def registry(validator: ContractValidator, event_port: FakeEventPort) -> CapabilityRegistry:
    return CapabilityRegistry(validator=validator, event_port=event_port)


@pytest.fixture
def loader(
    registry: CapabilityRegistry,
    tmp_contracts_dir: Path,
    event_port: FakeEventPort,
    validator: ContractValidator,
):
    """Create a ModuleLoader with fast polling for tests."""
    ml = ModuleLoader(
        registry=registry,
        contracts_dir=tmp_contracts_dir,
        event_port=event_port,
        validator=validator,
        poll_interval_s=0.1,  # Fast polling for tests
    )
    yield ml
    # Ensure watcher is stopped after test
    ml.stop()


# =========================================================================
# 2.3.1 -- ModuleLoader class & lifecycle
# =========================================================================


class TestModuleLoaderLifecycle:
    """Tests for ModuleLoader construction, start, stop, properties."""

    def test_construction_defaults(
        self, registry: CapabilityRegistry, tmp_contracts_dir: Path
    ) -> None:
        """Constructor sets all attributes correctly."""
        ml = ModuleLoader(
            registry=registry,
            contracts_dir=tmp_contracts_dir,
        )
        assert ml.contracts_dir == tmp_contracts_dir
        assert ml.is_running is False
        assert ml.file_count == 0
        assert ml.tracked_files == {}

    def test_construction_custom_poll_interval(
        self, registry: CapabilityRegistry, tmp_contracts_dir: Path
    ) -> None:
        """Custom poll interval is respected (min 0.1s)."""
        ml = ModuleLoader(
            registry=registry,
            contracts_dir=tmp_contracts_dir,
            poll_interval_s=5.0,
        )
        assert ml._poll_interval_s == 5.0

    def test_poll_interval_floor(
        self, registry: CapabilityRegistry, tmp_contracts_dir: Path
    ) -> None:
        """Poll interval below 0.1s is clamped to 0.1s."""
        ml = ModuleLoader(
            registry=registry,
            contracts_dir=tmp_contracts_dir,
            poll_interval_s=0.01,
        )
        assert ml._poll_interval_s == 0.1

    def test_start_scans_and_watches(self, loader: ModuleLoader, tmp_contracts_dir: Path) -> None:
        """start() performs initial scan and starts watcher."""
        (tmp_contracts_dir / "tools" / "weather.yaml").write_text(VALID_TOOL_YAML, encoding="utf-8")
        result = loader.start(watch=True)
        assert isinstance(result, ScanResult)
        assert result.loaded == 1
        assert loader.is_running is True

    def test_start_without_watch(self, loader: ModuleLoader, tmp_contracts_dir: Path) -> None:
        """start(watch=False) scans but does not start watcher."""
        result = loader.start(watch=False)
        assert isinstance(result, ScanResult)
        assert loader.is_running is False

    def test_stop_idempotent(self, loader: ModuleLoader) -> None:
        """stop() is safe to call multiple times."""
        loader.start(watch=False)
        loader.stop()
        loader.stop()  # Second call should not raise

    def test_stop_halts_watcher(self, loader: ModuleLoader) -> None:
        """stop() terminates the watcher thread."""
        loader.start(watch=True)
        assert loader.is_running is True
        loader.stop()
        time.sleep(0.2)
        assert loader.is_running is False


# =========================================================================
# 2.3.3 -- scan_directory()
# =========================================================================


class TestScanDirectory:
    """Tests for scan_directory() recursive YAML discovery."""

    def test_scan_empty_directory(self, loader: ModuleLoader) -> None:
        """Empty directory produces zero results."""
        result = loader.scan_directory()
        assert result.loaded == 0
        assert result.failed == 0
        assert result.errors == []
        assert result.contracts == []

    def test_scan_single_tool(self, loader: ModuleLoader, tmp_contracts_dir: Path) -> None:
        """Single valid tool contract is discovered and registered."""
        (tmp_contracts_dir / "tools" / "weather.yaml").write_text(VALID_TOOL_YAML, encoding="utf-8")
        result = loader.scan_directory()
        assert result.loaded == 1
        assert result.failed == 0
        assert "tool.execute.weather" in result.contracts

    def test_scan_multiple_types(self, loader: ModuleLoader, tmp_contracts_dir: Path) -> None:
        """Contracts in different subdirs are all discovered."""
        (tmp_contracts_dir / "tools" / "weather.yaml").write_text(VALID_TOOL_YAML, encoding="utf-8")
        (tmp_contracts_dir / "agents" / "planner.yaml").write_text(
            VALID_AGENT_YAML, encoding="utf-8"
        )
        (tmp_contracts_dir / "prompts" / "greeting.yaml").write_text(
            VALID_PROMPT_YAML, encoding="utf-8"
        )
        result = loader.scan_directory()
        assert result.loaded == 3
        assert "tool.execute.weather" in result.contracts
        assert "agent.execute.planner" in result.contracts
        assert "greeting_v1" in result.contracts

    def test_scan_nested_subdirectory(self, loader: ModuleLoader, tmp_contracts_dir: Path) -> None:
        """Contracts in nested subdirectories are found recursively."""
        nested = tmp_contracts_dir / "tools" / "weather" / "v1"
        nested.mkdir(parents=True)
        (nested / "forecast.yaml").write_text(VALID_TOOL_YAML, encoding="utf-8")
        result = loader.scan_directory()
        assert result.loaded == 1

    def test_scan_yml_extension(self, loader: ModuleLoader, tmp_contracts_dir: Path) -> None:
        """Files with .yml extension are also discovered."""
        (tmp_contracts_dir / "tools" / "weather.yml").write_text(VALID_TOOL_YAML, encoding="utf-8")
        result = loader.scan_directory()
        assert result.loaded == 1

    def test_scan_invalid_yaml_captured_as_error(
        self, loader: ModuleLoader, tmp_contracts_dir: Path
    ) -> None:
        """Invalid YAML files are counted as failures."""
        (tmp_contracts_dir / "tools" / "broken.yaml").write_text(BROKEN_YAML, encoding="utf-8")
        result = loader.scan_directory()
        assert result.loaded == 0
        assert result.failed == 1
        assert len(result.errors) == 1
        assert "broken.yaml" in result.errors[0]["file"]

    def test_scan_validation_failure_captured(
        self, loader: ModuleLoader, tmp_contracts_dir: Path
    ) -> None:
        """Contract that fails validation is captured as error."""
        (tmp_contracts_dir / "tools" / "invalid.yaml").write_text(INVALID_YAML, encoding="utf-8")
        result = loader.scan_directory()
        assert result.loaded == 0
        assert result.failed == 1

    def test_scan_mixed_valid_and_invalid(
        self, loader: ModuleLoader, tmp_contracts_dir: Path
    ) -> None:
        """Mix of valid and invalid files: valid ones register, invalid counted."""
        (tmp_contracts_dir / "tools" / "weather.yaml").write_text(VALID_TOOL_YAML, encoding="utf-8")
        (tmp_contracts_dir / "tools" / "broken.yaml").write_text(BROKEN_YAML, encoding="utf-8")
        result = loader.scan_directory()
        assert result.loaded == 1
        assert result.failed == 1

    def test_scan_file_map_populated(self, loader: ModuleLoader, tmp_contracts_dir: Path) -> None:
        """scan_directory populates _file_map correctly."""
        (tmp_contracts_dir / "tools" / "weather.yaml").write_text(VALID_TOOL_YAML, encoding="utf-8")
        loader.scan_directory()
        tracked = loader.tracked_files
        assert len(tracked) == 1
        # Value should be the capability name
        assert list(tracked.values()) == ["tool.execute.weather"]

    def test_scan_missing_subdirs_graceful(
        self, loader: ModuleLoader, tmp_contracts_dir: Path
    ) -> None:
        """Missing subdirectories (e.g., no workflows/) do not cause errors."""
        # Remove workflows dir
        (tmp_contracts_dir / "workflows").rmdir()
        (tmp_contracts_dir / "tools" / "weather.yaml").write_text(VALID_TOOL_YAML, encoding="utf-8")
        result = loader.scan_directory()
        assert result.loaded == 1
        assert result.failed == 0

    def test_scan_duplicate_name_skipped(
        self, loader: ModuleLoader, tmp_contracts_dir: Path
    ) -> None:
        """Two files with same capability name: first wins, second is error."""
        (tmp_contracts_dir / "tools" / "a_weather.yaml").write_text(
            VALID_TOOL_YAML, encoding="utf-8"
        )
        (tmp_contracts_dir / "tools" / "b_weather.yaml").write_text(
            VALID_TOOL_YAML, encoding="utf-8"
        )
        result = loader.scan_directory()
        assert result.loaded == 1
        assert result.failed == 1
        assert any("Duplicate" in e["error"] for e in result.errors)

    def test_scan_custom_path(self, loader: ModuleLoader, tmp_path: Path) -> None:
        """scan_directory(path=...) overrides the default contracts_dir."""
        alt_dir = tmp_path / "alt_contracts"
        (alt_dir / "tools").mkdir(parents=True)
        (alt_dir / "tools" / "weather.yaml").write_text(VALID_TOOL_YAML, encoding="utf-8")
        result = loader.scan_directory(path=alt_dir)
        assert result.loaded == 1

    def test_scan_result_is_frozen(self, loader: ModuleLoader, tmp_contracts_dir: Path) -> None:
        """ScanResult is a frozen dataclass."""
        result = loader.scan_directory()
        with pytest.raises(AttributeError):
            result.loaded = 999


# =========================================================================
# 2.3.4 -- register_from_dict()
# =========================================================================


class TestRegisterFromDict:
    """Tests for programmatic registration from raw dicts."""

    def test_register_from_dict_auto_detect(
        self, loader: ModuleLoader, registry: CapabilityRegistry
    ) -> None:
        """Auto-detect contract type from root key."""
        contract_dict = {
            "tool_contract": {
                "name": "tool.execute.calc",
                "version": "1.0.0",
                "description": "Calculator tool",
                "domain": ["MATH"],
                "capabilities": ["calculate"],
                "limitations": [],
                "required_inputs": [
                    {"name": "expression", "type": "string", "description": "Math expression"}
                ],
                "output": {"type": "object", "properties": {"result": {"type": "number"}}},
                "provider_type": "MCP",
                "provider_id": "mcp-calc-001",
                "safety_band_min": "GREEN",
                "availability": "ONLINE",
            }
        }
        contract = loader.register_from_dict(contract_dict)
        assert contract.name == "tool.execute.calc"
        assert registry.contains("tool.execute.calc")

    def test_register_from_dict_explicit_type(
        self, loader: ModuleLoader, registry: CapabilityRegistry
    ) -> None:
        """Explicit contract_type uses parse_contract_body."""
        body = {
            "name": "tool.execute.timer",
            "version": "1.0.0",
            "description": "Timer tool",
            "domain": ["UTILITY"],
            "capabilities": ["set_timer"],
            "limitations": [],
            "required_inputs": [
                {"name": "seconds", "type": "number", "description": "Timer duration"}
            ],
            "output": {"type": "object", "properties": {"remaining": {"type": "number"}}},
            "provider_type": "MCP",
            "provider_id": "mcp-timer-001",
            "safety_band_min": "GREEN",
            "availability": "ONLINE",
        }
        contract = loader.register_from_dict(body, contract_type="tool_contract")
        assert contract.name == "tool.execute.timer"
        assert registry.contains("tool.execute.timer")

    def test_register_from_dict_duplicate_raises(
        self, loader: ModuleLoader, registry: CapabilityRegistry
    ) -> None:
        """Duplicate name from register_from_dict raises a registry error."""
        contract_dict = {
            "tool_contract": {
                "name": "tool.execute.dup",
                "version": "1.0.0",
                "description": "Dup tool",
                "domain": ["TEST"],
                "capabilities": ["test"],
                "limitations": [],
                "required_inputs": [{"name": "x", "type": "string", "description": "Input"}],
                "output": {"type": "string"},
                "provider_type": "MCP",
                "provider_id": "mcp-dup-001",
                "safety_band_min": "GREEN",
                "availability": "ONLINE",
            }
        }
        loader.register_from_dict(contract_dict)
        with pytest.raises((DuplicateCapabilityError, VersionConflictError)):
            loader.register_from_dict(contract_dict)

    def test_register_from_dict_invalid_raises(self, loader: ModuleLoader) -> None:
        """Invalid contract dict raises ContractParseError or ContractValidationError."""
        with pytest.raises(Exception):
            loader.register_from_dict({"tool_contract": {"name": "", "version": "bad"}})


# =========================================================================
# 2.3.2 -- Hot-reload watcher
# =========================================================================


class TestHotReloadWatcher:
    """Tests for polling-based hot-reload watcher."""

    def test_watcher_detects_new_file(
        self,
        loader: ModuleLoader,
        tmp_contracts_dir: Path,
        registry: CapabilityRegistry,
        event_port: FakeEventPort,
    ) -> None:
        """Watcher detects a new file and registers it."""
        loader.start(watch=True)
        time.sleep(0.15)

        # Drop a new file while watcher is running
        (tmp_contracts_dir / "tools" / "weather.yaml").write_text(VALID_TOOL_YAML, encoding="utf-8")
        # Wait for at least one poll cycle
        time.sleep(0.5)

        assert registry.contains("tool.execute.weather")
        # Check hot-reload event was emitted
        reload_events = event_port.events_of_type(EVENT_CONTRACT_HOT_RELOADED)
        assert any(
            e["payload"].get("action") == "created"
            and e["payload"].get("name") == "tool.execute.weather"
            for e in reload_events
        )

    def test_watcher_detects_modified_file(
        self,
        loader: ModuleLoader,
        tmp_contracts_dir: Path,
        registry: CapabilityRegistry,
        event_port: FakeEventPort,
    ) -> None:
        """Watcher detects a modified file and re-registers."""
        # Pre-load a file
        weather_path = tmp_contracts_dir / "tools" / "weather.yaml"
        weather_path.write_text(VALID_TOOL_YAML, encoding="utf-8")
        loader.start(watch=True)
        time.sleep(0.15)
        assert registry.contains("tool.execute.weather")

        # Modify the file (ensure mtime changes)
        event_port.clear()
        time.sleep(0.05)
        weather_path.write_text(VALID_TOOL_YAML_V2, encoding="utf-8")
        time.sleep(0.5)

        # Contract should still be registered (same name, new version)
        contract = registry.lookup("tool.execute.weather")
        assert contract is not None
        assert contract.version == "2.0.0"

        reload_events = event_port.events_of_type(EVENT_CONTRACT_HOT_RELOADED)
        assert any(e["payload"].get("action") == "modified" for e in reload_events)

    def test_watcher_detects_deleted_file(
        self,
        loader: ModuleLoader,
        tmp_contracts_dir: Path,
        registry: CapabilityRegistry,
        event_port: FakeEventPort,
    ) -> None:
        """Watcher detects a deleted file and unregisters."""
        weather_path = tmp_contracts_dir / "tools" / "weather.yaml"
        weather_path.write_text(VALID_TOOL_YAML, encoding="utf-8")
        loader.start(watch=True)
        time.sleep(0.15)
        assert registry.contains("tool.execute.weather")

        # Delete the file
        event_port.clear()
        weather_path.unlink()
        time.sleep(0.5)

        assert not registry.contains("tool.execute.weather")
        remove_events = event_port.events_of_type(EVENT_CONTRACT_REMOVED)
        assert any(e["payload"].get("name") == "tool.execute.weather" for e in remove_events)

    def test_watcher_validation_failure_keeps_old(
        self,
        loader: ModuleLoader,
        tmp_contracts_dir: Path,
        registry: CapabilityRegistry,
        event_port: FakeEventPort,
    ) -> None:
        """If modified file fails validation, old contract is kept."""
        weather_path = tmp_contracts_dir / "tools" / "weather.yaml"
        weather_path.write_text(VALID_TOOL_YAML, encoding="utf-8")
        loader.start(watch=True)
        time.sleep(0.15)

        old_contract = registry.lookup("tool.execute.weather")
        assert old_contract is not None

        # Overwrite with broken YAML
        event_port.clear()
        time.sleep(0.05)
        weather_path.write_text(BROKEN_YAML, encoding="utf-8")
        time.sleep(0.5)

        # Old contract should still be there (watcher keeps it)
        current = registry.lookup("tool.execute.weather")
        assert current is not None
        assert current.version == old_contract.version

        # Validation failure event emitted
        fail_events = event_port.events_of_type(EVENT_CONTRACT_VALIDATION_FAILED)
        assert len(fail_events) >= 1

    def test_start_watching_idempotent(self, loader: ModuleLoader) -> None:
        """Calling start_watching() twice does not create two threads."""
        loader.start(watch=True)
        thread1 = loader._watcher_thread
        loader.start_watching()
        thread2 = loader._watcher_thread
        assert thread1 is thread2

    def test_stop_watching_idempotent(self, loader: ModuleLoader) -> None:
        """Calling stop_watching() when not running is a no-op."""
        loader.stop_watching()  # Should not raise


# =========================================================================
# Event emission
# =========================================================================


class TestModuleLoaderEvents:
    """Tests for event emission without event port."""

    def test_no_event_port_no_error(
        self,
        registry: CapabilityRegistry,
        tmp_contracts_dir: Path,
        validator: ContractValidator,
    ) -> None:
        """ModuleLoader works fine with event_port=None."""
        ml = ModuleLoader(
            registry=registry,
            contracts_dir=tmp_contracts_dir,
            event_port=None,
            validator=validator,
        )
        (tmp_contracts_dir / "tools" / "weather.yaml").write_text(VALID_TOOL_YAML, encoding="utf-8")
        result = ml.scan_directory()
        assert result.loaded == 1


# =========================================================================
# File count and tracking
# =========================================================================


class TestFileTracking:
    """Tests for file_count and tracked_files properties."""

    def test_file_count_after_scan(self, loader: ModuleLoader, tmp_contracts_dir: Path) -> None:
        """file_count reflects number of tracked files."""
        (tmp_contracts_dir / "tools" / "weather.yaml").write_text(VALID_TOOL_YAML, encoding="utf-8")
        (tmp_contracts_dir / "agents" / "planner.yaml").write_text(
            VALID_AGENT_YAML, encoding="utf-8"
        )
        loader.scan_directory()
        assert loader.file_count == 2

    def test_tracked_files_returns_copy(
        self, loader: ModuleLoader, tmp_contracts_dir: Path
    ) -> None:
        """tracked_files returns a new dict each call."""
        (tmp_contracts_dir / "tools" / "weather.yaml").write_text(VALID_TOOL_YAML, encoding="utf-8")
        loader.scan_directory()
        t1 = loader.tracked_files
        t2 = loader.tracked_files
        assert t1 == t2
        assert t1 is not t2
        t1 = loader.tracked_files
        t2 = loader.tracked_files
        assert t1 == t2
        assert t1 is not t2
        t1 = loader.tracked_files
        t2 = loader.tracked_files
        assert t1 == t2
        assert t1 is not t2
