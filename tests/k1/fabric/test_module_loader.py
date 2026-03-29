"""
Unit tests for ModuleLoader -- Epic 6.2.4.

Tests the full ModuleLoader API:
  - start() / stop() lifecycle
  - scan_directory() with valid and invalid YAMLs
  - Hot-reload: create / modify / delete detection
  - register_from_dict() programmatic registration
  - File tracking (_file_map, _mtime_cache)

Uses real ModuleLoader, real CapabilityRegistry, real ContractValidator.
NO MOCKS. Tests use tmp_path for contract directories.

References:
  - fabric-implementation-plan.md Milestone 6, Epic 6.2.4
  - k1/fabric/core/module_loader.py
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import yaml

from k1.fabric.adapters.local_event import LocalEventAdapter
from k1.fabric.core.contract_validator import ContractValidator
from k1.fabric.core.module_loader import EVENT_CONTRACT_VALIDATION_FAILED, ModuleLoader, ScanResult
from k1.fabric.core.registry import CapabilityRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_loader(
    contracts_dir: Path,
    *,
    capture: bool = True,
    poll_interval_s: float = 0.2,
) -> tuple[ModuleLoader, CapabilityRegistry, LocalEventAdapter]:
    """Create a wired ModuleLoader + Registry + EventAdapter."""
    validator = ContractValidator()
    adapter = LocalEventAdapter(capture_mode=capture)
    registry = CapabilityRegistry(validator=validator, event_port=adapter)  # type: ignore[arg-type]
    loader = ModuleLoader(
        registry=registry,
        contracts_dir=str(contracts_dir),
        event_port=adapter,  # type: ignore[arg-type]
        validator=validator,
        poll_interval_s=poll_interval_s,
    )
    return loader, registry, adapter


def _write_tool_yaml(
    directory: Path,
    name: str = "tool.execute.test_scan_tool",
    version: str = "1.0.0",
    filename: str = "test_tool.yaml",
) -> Path:
    """Write a valid tool contract YAML to directory/tools/<filename>."""
    tools_dir = directory / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    fpath = tools_dir / filename
    data = {
        "tool_contract": {
            "name": name,
            "version": version,
            "domain": ["TEST"],
            "description": "A scannable test tool",
            "capabilities": ["test_action"],
            "limitations": [],
            "required_inputs": [
                {"name": "x", "type": "STRING", "description": "input"},
            ],
            "output": {"type": "object"},
            "provider_type": "MCP",
            "provider_id": "test-provider",
            "safety_band_min": "GREEN",
            "availability": "ONLINE",
        }
    }
    fpath.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")
    return fpath


def _write_agent_yaml(
    directory: Path,
    name: str = "agent.execute.test_scan_agent",
    filename: str = "test_agent.yaml",
) -> Path:
    """Write a valid agent contract YAML to directory/agents/<filename>."""
    agents_dir = directory / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    fpath = agents_dir / filename
    data = {
        "agent_contract": {
            "name": name,
            "version": "1.0.0",
            "domain": ["TEST"],
            "description": "A scannable test agent",
            "capabilities": ["test_action"],
            "limitations": [],
            "required_inputs": [
                {"name": "x", "type": "STRING", "description": "input"},
            ],
            "output": {"type": "object"},
            "provider_type": "AGENT",
            "provider_id": "test-agent",
            "safety_band_min": "GREEN",
            "availability": "ONLINE",
            "prompt_template": "test_v1",
            "tools_granted": [],
            "llm_budget_tokens": 1024,
            "max_tool_calls": 3,
            "max_execution_time_ms": 10000,
        }
    }
    fpath.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")
    return fpath


def _write_invalid_yaml(directory: Path, filename: str = "bad.yaml") -> Path:
    """Write an invalid YAML file to directory/tools/."""
    tools_dir = directory / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    fpath = tools_dir / filename
    fpath.write_text(":::not valid yaml:::", encoding="utf-8")
    return fpath


def _write_invalid_contract_yaml(directory: Path, filename: str = "bad_contract.yaml") -> Path:
    """Write a YAML with invalid contract structure to directory/tools/."""
    tools_dir = directory / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    fpath = tools_dir / filename
    data = {
        "tool_contract": {
            "name": "INVALID_NAME",
            "version": "bad",
            "domain": [],
            "description": "",
        }
    }
    fpath.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")
    return fpath


# ====================================================================
# ScanResult dataclass
# ====================================================================


class TestScanResult:
    """ScanResult is a frozen dataclass with correct defaults."""

    def test_default_values(self) -> None:
        r = ScanResult()
        assert r.loaded == 0
        assert r.failed == 0
        assert r.errors == []
        assert r.contracts == []

    def test_frozen(self) -> None:
        r = ScanResult(loaded=5, failed=1)
        with pytest.raises(AttributeError):
            r.loaded = 10  # type: ignore[misc]


# ====================================================================
# scan_directory()
# ====================================================================


class TestScanDirectory:
    """scan_directory() discovers, parses, and registers YAML contracts."""

    def test_scan_empty_directory(self, tmp_path: Path) -> None:
        loader, registry, _ = _make_loader(tmp_path)
        result = loader.scan_directory()
        assert result.loaded == 0
        assert result.failed == 0

    def test_scan_single_tool(self, tmp_path: Path) -> None:
        _write_tool_yaml(tmp_path)
        loader, registry, _ = _make_loader(tmp_path)
        result = loader.scan_directory()
        assert result.loaded == 1
        assert result.failed == 0
        assert "tool.execute.test_scan_tool" in result.contracts
        assert registry.contains("tool.execute.test_scan_tool")

    def test_scan_multiple_contracts(self, tmp_path: Path) -> None:
        _write_tool_yaml(tmp_path, name="tool.execute.tool_one", filename="tool_one.yaml")
        _write_tool_yaml(tmp_path, name="tool.execute.tool_two", filename="tool_two.yaml")
        _write_agent_yaml(tmp_path)
        loader, registry, _ = _make_loader(tmp_path)
        result = loader.scan_directory()
        assert result.loaded == 3
        assert registry.size == 3

    def test_scan_mix_valid_and_invalid(self, tmp_path: Path) -> None:
        _write_tool_yaml(tmp_path)
        _write_invalid_yaml(tmp_path, filename="bad1.yaml")
        _write_invalid_contract_yaml(tmp_path, filename="bad_contract.yaml")
        loader, registry, _ = _make_loader(tmp_path)
        result = loader.scan_directory()
        assert result.loaded == 1
        assert result.failed >= 1
        assert len(result.errors) >= 1

    def test_scan_tracks_files(self, tmp_path: Path) -> None:
        _write_tool_yaml(tmp_path)
        loader, _, _ = _make_loader(tmp_path)
        loader.scan_directory()
        assert loader.file_count == 1
        tracked = loader.tracked_files
        assert len(tracked) == 1
        # Value is the capability name
        assert "tool.execute.test_scan_tool" in tracked.values()

    def test_scan_with_override_path(self, tmp_path: Path) -> None:
        """scan_directory(path=...) overrides the configured contracts_dir."""
        alt_dir = tmp_path / "alt"
        alt_dir.mkdir()
        _write_tool_yaml(alt_dir, name="tool.execute.alt_tool")
        loader, registry, _ = _make_loader(tmp_path)
        result = loader.scan_directory(path=alt_dir)
        assert result.loaded == 1
        assert registry.contains("tool.execute.alt_tool")


# ====================================================================
# start() / stop() lifecycle
# ====================================================================


class TestLifecycle:
    """start() scans + starts watcher, stop() cleans up."""

    def test_start_scans_and_reports(self, tmp_path: Path) -> None:
        _write_tool_yaml(tmp_path)
        loader, registry, _ = _make_loader(tmp_path)
        result = loader.start(watch=False)
        assert result.loaded == 1
        assert registry.contains("tool.execute.test_scan_tool")

    def test_start_with_watch(self, tmp_path: Path) -> None:
        _write_tool_yaml(tmp_path)
        loader, _, _ = _make_loader(tmp_path, poll_interval_s=0.1)
        try:
            result = loader.start(watch=True)
            assert result.loaded == 1
            assert loader.is_running is True
        finally:
            loader.stop()
        assert loader.is_running is False

    def test_stop_idempotent(self, tmp_path: Path) -> None:
        loader, _, _ = _make_loader(tmp_path)
        loader.start(watch=True)
        loader.stop()
        loader.stop()  # Should not raise
        assert loader.is_running is False

    def test_properties(self, tmp_path: Path) -> None:
        _write_tool_yaml(tmp_path)
        loader, _, _ = _make_loader(tmp_path)
        assert loader.contracts_dir == tmp_path
        loader.scan_directory()
        assert loader.file_count >= 1


# ====================================================================
# Hot-reload: create / modify / delete
# ====================================================================


class TestHotReload:
    """Watcher detects file create, modify, and delete events."""

    def test_detect_new_file(self, tmp_path: Path) -> None:
        loader, registry, adapter = _make_loader(tmp_path, poll_interval_s=0.1)
        try:
            loader.start(watch=True)
            # Write a new file after watcher started
            _write_tool_yaml(tmp_path, name="tool.execute.hot_new", filename="hot_new.yaml")
            # Wait for detection
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                if registry.contains("tool.execute.hot_new"):
                    break
                time.sleep(0.1)
            assert registry.contains(
                "tool.execute.hot_new"
            ), "Watcher did not detect new file within 3s"
        finally:
            loader.stop()

    def test_detect_modified_file(self, tmp_path: Path) -> None:
        fpath = _write_tool_yaml(tmp_path, name="tool.execute.hot_mod", filename="hot_mod.yaml")
        loader, registry, _ = _make_loader(tmp_path, poll_interval_s=0.1)
        try:
            loader.start(watch=True)
            assert registry.contains("tool.execute.hot_mod")

            # Modify the file with updated version
            time.sleep(0.3)  # Ensure mtime difference
            data = {
                "tool_contract": {
                    "name": "tool.execute.hot_mod",
                    "version": "1.1.0",
                    "domain": ["TEST"],
                    "description": "Modified test tool",
                    "capabilities": ["test"],
                    "limitations": [],
                    "required_inputs": [
                        {"name": "x", "type": "STRING", "description": "input"},
                    ],
                    "output": {"type": "object"},
                    "provider_type": "MCP",
                    "provider_id": "test-provider",
                    "safety_band_min": "GREEN",
                    "availability": "ONLINE",
                }
            }
            fpath.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")

            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                result = registry.lookup("tool.execute.hot_mod")
                if result is not None and result.version == "1.1.0":
                    break
                time.sleep(0.1)
            result = registry.lookup("tool.execute.hot_mod")
            assert result is not None
            assert result.version == "1.1.0", f"Expected v1.1.0 after modify, got {result.version}"
        finally:
            loader.stop()

    def test_detect_deleted_file(self, tmp_path: Path) -> None:
        fpath = _write_tool_yaml(tmp_path, name="tool.execute.hot_del", filename="hot_del.yaml")
        loader, registry, _ = _make_loader(tmp_path, poll_interval_s=0.1)
        try:
            loader.start(watch=True)
            assert registry.contains("tool.execute.hot_del")

            # Delete the file
            fpath.unlink()

            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                if not registry.contains("tool.execute.hot_del"):
                    break
                time.sleep(0.1)
            assert not registry.contains(
                "tool.execute.hot_del"
            ), "Watcher did not detect file deletion within 3s"
        finally:
            loader.stop()


# ====================================================================
# register_from_dict()
# ====================================================================


class TestRegisterFromDict:
    """register_from_dict() parses and registers a raw dict."""

    def test_register_from_dict_auto_detect(self, tmp_path: Path) -> None:
        loader, registry, _ = _make_loader(tmp_path)
        data = {
            "tool_contract": {
                "name": "tool.execute.from_dict",
                "version": "1.0.0",
                "domain": ["TEST"],
                "description": "Dict-registered tool",
                "capabilities": ["test"],
                "limitations": [],
                "required_inputs": [
                    {"name": "x", "type": "STRING", "description": "input"},
                ],
                "output": {"type": "object"},
                "provider_type": "MCP",
                "provider_id": "test",
                "safety_band_min": "GREEN",
                "availability": "ONLINE",
            }
        }
        contract = loader.register_from_dict(data)
        assert contract.name == "tool.execute.from_dict"
        assert registry.contains("tool.execute.from_dict")

    def test_register_from_dict_with_type(self, tmp_path: Path) -> None:
        loader, registry, _ = _make_loader(tmp_path)
        body = {
            "name": "tool.execute.typed_dict",
            "version": "1.0.0",
            "domain": ["TEST"],
            "description": "Typed dict tool",
            "capabilities": ["test"],
            "limitations": [],
            "required_inputs": [
                {"name": "x", "type": "STRING", "description": "input"},
            ],
            "output": {"type": "object"},
            "provider_type": "MCP",
            "provider_id": "test",
            "safety_band_min": "GREEN",
            "availability": "ONLINE",
        }
        contract = loader.register_from_dict(body, contract_type="tool_contract")
        assert contract.name == "tool.execute.typed_dict"
        assert registry.contains("tool.execute.typed_dict")

    def test_register_from_dict_skip_validation(self, tmp_path: Path) -> None:
        loader, registry, _ = _make_loader(tmp_path)
        data = {
            "tool_contract": {
                "name": "tool.execute.skipped",
                "version": "1.0.0",
                "domain": ["TEST"],
                "description": "Skip validation",
                "capabilities": ["test"],
                "limitations": [],
                "required_inputs": [
                    {"name": "x", "type": "STRING", "description": "input"},
                ],
                "output": {"type": "object"},
                "provider_type": "MCP",
                "provider_id": "test",
                "safety_band_min": "GREEN",
            }
        }
        loader.register_from_dict(data, skip_validation=True)
        assert registry.contains("tool.execute.skipped")


# ====================================================================
# Invalid file handling
# ====================================================================


class TestInvalidFileHandling:
    """ModuleLoader handles invalid files gracefully."""

    def test_invalid_yaml_in_scan(self, tmp_path: Path) -> None:
        _write_invalid_yaml(tmp_path)
        loader, registry, _ = _make_loader(tmp_path)
        result = loader.scan_directory()
        assert result.failed >= 1
        assert result.loaded == 0

    def test_validation_failure_in_scan(self, tmp_path: Path) -> None:
        _write_invalid_contract_yaml(tmp_path)
        loader, _, _ = _make_loader(tmp_path)
        result = loader.scan_directory()
        assert result.failed >= 1
        assert len(result.errors) >= 1

    def test_hot_reload_invalid_file_emits_event(self, tmp_path: Path) -> None:
        """Invalid file during hot-reload emits validation_failed event."""
        loader, _, adapter = _make_loader(tmp_path, poll_interval_s=0.1)
        try:
            loader.start(watch=True)
            # Write an invalid file
            _write_invalid_yaml(tmp_path, filename="bad_hot.yaml")

            deadline = time.monotonic() + 3.0
            found = False
            while time.monotonic() < deadline:
                events = adapter.get_captured(topic=EVENT_CONTRACT_VALIDATION_FAILED)
                if len(events) > 0:
                    found = True
                    break
                time.sleep(0.1)
            assert found, "Expected validation_failed event for invalid hot-reload file"
        finally:
            loader.stop()


# ====================================================================
# File discovery (subdirectory structure)
# ====================================================================


class TestFileDiscovery:
    """ModuleLoader only scans expected subdirectories."""

    def test_only_scans_known_subdirs(self, tmp_path: Path) -> None:
        """Files outside tools/agents/prompts/workflows are ignored."""
        random_dir = tmp_path / "random"
        random_dir.mkdir()
        fpath = random_dir / "undetected.yaml"
        data = {
            "tool_contract": {
                "name": "tool.execute.undetected",
                "version": "1.0.0",
                "domain": ["TEST"],
                "description": "Should not be found",
                "capabilities": ["test"],
                "limitations": [],
                "required_inputs": [
                    {"name": "x", "type": "STRING", "description": "input"},
                ],
                "output": {"type": "object"},
                "provider_type": "MCP",
                "provider_id": "test",
                "safety_band_min": "GREEN",
            }
        }
        fpath.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")

        loader, registry, _ = _make_loader(tmp_path)
        result = loader.scan_directory()
        assert result.loaded == 0
        assert not registry.contains("tool.execute.undetected")

    def test_scans_nested_subdirectories(self, tmp_path: Path) -> None:
        """YAML files in nested subdirectories within tools/ are found."""
        nested = tmp_path / "tools" / "food" / "restaurants"
        nested.mkdir(parents=True)
        fpath = nested / "booking.yaml"
        data = {
            "tool_contract": {
                "name": "tool.execute.nested_tool",
                "version": "1.0.0",
                "domain": ["TEST"],
                "description": "Nested discovery test",
                "capabilities": ["test"],
                "limitations": [],
                "required_inputs": [
                    {"name": "x", "type": "STRING", "description": "input"},
                ],
                "output": {"type": "object"},
                "provider_type": "MCP",
                "provider_id": "test",
                "safety_band_min": "GREEN",
                "availability": "ONLINE",
            }
        }
        fpath.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")

        loader, registry, _ = _make_loader(tmp_path)
        result = loader.scan_directory()
        assert result.loaded == 1
        assert registry.contains("tool.execute.nested_tool")
