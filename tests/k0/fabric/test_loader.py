"""
Tests for Capability Loader (Issue 2.2.2).

Tests:
- load_capability_definitions_from_yaml
- load_capability_definitions_missing_dir
- load_capability_definitions_invalid_yaml_skipped
- register_capabilities_from_definitions
- register_capabilities_resolves_handlers
- discover_and_register_full_flow
- get_capability_loader_stats
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from k0.fabric.loader import (
    discover_and_register_capabilities,
    get_capability_loader_stats,
    load_capability_definitions,
    register_capabilities_from_definitions,
)
from k0.fabric.registry import CapabilityRegistry, reset_capability_registry
from k0.runtime.module_registry import ModuleRegistry
from k0.runtime.schemas import CapabilityDefinition


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset capability registry before/after each test."""
    reset_capability_registry()
    yield
    reset_capability_registry()


class TestLoadCapabilityDefinitions:
    """Tests for load_capability_definitions."""

    def test_load_from_yaml(self, tmp_path: Path):
        """Load capability definitions from valid YAML."""
        yaml_content = """
version: v1
capabilities:
  test_capability:
    description: "Test capability"
    default_timeout_ms: 100
    providers:
      - type: module
        module_id: test.module
        priority: 1
"""
        (tmp_path / "test.yaml").write_text(yaml_content)

        definitions = load_capability_definitions(tmp_path)

        assert "test_capability" in definitions
        assert isinstance(definitions["test_capability"], CapabilityDefinition)
        assert definitions["test_capability"].description == "Test capability"
        assert definitions["test_capability"].default_timeout_ms == 100

    def test_load_multiple_files(self, tmp_path: Path):
        """Load from multiple YAML files."""
        (tmp_path / "core.yaml").write_text(
            """
version: v1
capabilities:
  cap_a:
    description: "Capability A"
    providers:
      - type: module
        module_id: mod.a
        priority: 1
"""
        )
        (tmp_path / "extended.yaml").write_text(
            """
version: v1
capabilities:
  cap_b:
    description: "Capability B"
    providers:
      - type: module
        module_id: mod.b
        priority: 1
"""
        )

        definitions = load_capability_definitions(tmp_path)

        assert len(definitions) == 2
        assert "cap_a" in definitions
        assert "cap_b" in definitions

    def test_load_missing_dir_returns_empty(self, tmp_path: Path):
        """Load from missing directory returns empty dict."""
        missing = tmp_path / "nonexistent"

        definitions = load_capability_definitions(missing)

        assert definitions == {}

    def test_load_invalid_yaml_skipped(self, tmp_path: Path):
        """Invalid YAML files are skipped."""
        # Valid file
        (tmp_path / "valid.yaml").write_text(
            """
version: v1
capabilities:
  good_cap:
    description: "Good"
    providers:
      - type: module
        module_id: good.mod
        priority: 1
"""
        )
        # Invalid file (bad syntax)
        (tmp_path / "invalid.yaml").write_text("not: valid: yaml: [")

        definitions = load_capability_definitions(tmp_path)

        # Valid file should still load
        assert "good_cap" in definitions

    def test_load_file_without_capabilities_skipped(self, tmp_path: Path):
        """Files without 'capabilities' key are skipped."""
        (tmp_path / "metadata.yaml").write_text("version: v1\nsome_other_key: value")
        (tmp_path / "valid.yaml").write_text(
            """
version: v1
capabilities:
  actual_cap:
    description: "Actual"
    providers:
      - type: module
        module_id: actual.mod
        priority: 1
"""
        )

        definitions = load_capability_definitions(tmp_path)

        assert len(definitions) == 1
        assert "actual_cap" in definitions

    def test_load_yml_extension(self, tmp_path: Path):
        """Support .yml extension."""
        (tmp_path / "test.yml").write_text(
            """
version: v1
capabilities:
  yml_cap:
    description: "YML capability"
    providers:
      - type: module
        module_id: yml.mod
        priority: 1
"""
        )

        definitions = load_capability_definitions(tmp_path)

        assert "yml_cap" in definitions


class TestRegisterCapabilities:
    """Tests for register_capabilities_from_definitions."""

    def test_register_from_definitions(self, tmp_path: Path):
        """Register providers from definitions."""
        yaml_content = """
version: v1
capabilities:
  test_cap:
    description: "Test"
    providers:
      - type: module
        module_id: test.mod
        priority: 1
"""
        (tmp_path / "test.yaml").write_text(yaml_content)
        definitions = load_capability_definitions(tmp_path)

        registry = CapabilityRegistry()
        count = register_capabilities_from_definitions(
            definitions,
            capability_registry=registry,
        )

        assert count == 1
        assert registry.list_capabilities() == ["test_cap"]

    def test_register_multiple_providers(self, tmp_path: Path):
        """Register multiple providers for same capability."""
        yaml_content = """
version: v1
capabilities:
  multi_cap:
    description: "Multiple providers"
    providers:
      - type: module
        module_id: primary.mod
        priority: 1
      - type: module
        module_id: fallback.mod
        priority: 2
"""
        (tmp_path / "test.yaml").write_text(yaml_content)
        definitions = load_capability_definitions(tmp_path)

        registry = CapabilityRegistry()
        count = register_capabilities_from_definitions(
            definitions,
            capability_registry=registry,
        )

        assert count == 2
        providers = registry.list_providers("multi_cap")
        assert len(providers) == 2

    def test_register_resolves_handlers(self, tmp_path: Path):
        """Register with ModuleRegistry resolves handlers."""
        yaml_content = """
version: v1
capabilities:
  handler_cap:
    description: "Handler resolution"
    providers:
      - type: module
        module_id: handler.mod
        priority: 1
"""
        (tmp_path / "test.yaml").write_text(yaml_content)
        definitions = load_capability_definitions(tmp_path)

        # Mock module registry
        mock_handler = MagicMock()
        module_registry = MagicMock(spec=ModuleRegistry)
        module_registry.get.return_value = mock_handler

        registry = CapabilityRegistry()
        count = register_capabilities_from_definitions(
            definitions,
            module_registry=module_registry,
            capability_registry=registry,
        )

        assert count == 1
        # Handler should be bound
        provider = registry.resolve("handler_cap")
        assert provider is not None
        assert provider.handler is mock_handler

    def test_register_handler_resolution_failure_continues(self, tmp_path: Path):
        """Handler resolution failure doesn't stop registration."""
        yaml_content = """
version: v1
capabilities:
  failing_cap:
    description: "Handler fails"
    providers:
      - type: module
        module_id: bad.mod
        priority: 1
"""
        (tmp_path / "test.yaml").write_text(yaml_content)
        definitions = load_capability_definitions(tmp_path)

        # Mock module registry that raises
        module_registry = MagicMock(spec=ModuleRegistry)
        module_registry.get.side_effect = Exception("Module not found")

        registry = CapabilityRegistry()
        count = register_capabilities_from_definitions(
            definitions,
            module_registry=module_registry,
            capability_registry=registry,
        )

        # Should still register (without handler)
        assert count == 1
        provider = registry.resolve("failing_cap")
        assert provider is not None
        assert provider.handler is None


class TestDiscoverAndRegister:
    """Tests for discover_and_register_capabilities."""

    def test_full_flow(self, tmp_path: Path):
        """Full discovery and registration flow."""
        yaml_content = """
version: v1
capabilities:
  discovered_cap:
    description: "Discovered"
    providers:
      - type: module
        module_id: discovered.mod
        priority: 1
"""
        (tmp_path / "cap.yaml").write_text(yaml_content)

        registry = CapabilityRegistry()
        count = discover_and_register_capabilities(
            contracts_dir=tmp_path,
            capability_registry=registry,
        )

        assert count == 1
        assert "discovered_cap" in registry.list_capabilities()

    def test_with_module_registry(self, tmp_path: Path):
        """Discovery with module registry for handler binding."""
        yaml_content = """
version: v1
capabilities:
  bound_cap:
    description: "With handler"
    providers:
      - type: module
        module_id: bound.mod
        priority: 1
"""
        (tmp_path / "cap.yaml").write_text(yaml_content)

        mock_handler = MagicMock()
        module_registry = MagicMock(spec=ModuleRegistry)
        module_registry.get.return_value = mock_handler

        registry = CapabilityRegistry()
        count = discover_and_register_capabilities(
            module_registry=module_registry,
            contracts_dir=tmp_path,
            capability_registry=registry,
        )

        assert count == 1
        provider = registry.resolve("bound_cap")
        assert provider.handler is mock_handler


class TestCapabilityLoaderStats:
    """Tests for get_capability_loader_stats."""

    def test_stats_empty(self):
        """Stats on empty registry."""
        stats = get_capability_loader_stats()

        assert stats["total_capabilities"] == 0
        assert stats["total_providers"] == 0

    def test_stats_after_registration(self, tmp_path: Path):
        """Stats reflect registered capabilities."""
        yaml_content = """
version: v1
capabilities:
  cap1:
    description: "Cap 1"
    providers:
      - type: module
        module_id: domain.mod_one
        priority: 1
  cap2:
    description: "Cap 2"
    providers:
      - type: module
        module_id: domain.mod_two_a
        priority: 1
      - type: module
        module_id: domain.mod_two_b
        priority: 2
"""
        (tmp_path / "caps.yaml").write_text(yaml_content)
        discover_and_register_capabilities(contracts_dir=tmp_path)

        stats = get_capability_loader_stats()

        assert stats["total_capabilities"] == 2
        assert stats["total_providers"] == 3
        assert stats["total_providers"] == 3
        assert stats["total_providers"] == 3
