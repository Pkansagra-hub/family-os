"""
Tests for ModuleRegistry capability indexing (Issue 2.2.1).

Tests:
- register_capability adds to index
- register_capability prevents duplicates
- resolve_capability returns correct modules
- resolve_capability returns empty for unknown
- load_contracts auto-registers fabric_capabilities
- get_capability_stats returns accurate counts
- list_capabilities returns all capabilities
- unregister_capability removes mapping
"""

from __future__ import annotations

from pathlib import Path

import pytest

from k0.runtime.module_registry import (
    ModuleRegistry,
    get_module_registry,
    reset_module_registry,
    set_module_registry,
)


@pytest.fixture
def registry() -> ModuleRegistry:
    """Create fresh registry for each test."""
    return ModuleRegistry()


@pytest.fixture(autouse=True)
def reset_global_registry():
    """Reset global registry before/after each test."""
    reset_module_registry()
    yield
    reset_module_registry()


class TestRegisterCapability:
    """Tests for register_capability method."""

    def test_register_capability_adds_to_index(self, registry: ModuleRegistry):
        """Register capability creates index entry."""
        registry.register_capability("score_salience", "salience.score:v1")

        assert "score_salience" in registry.list_capabilities()
        assert registry.resolve_capability("score_salience") == ["salience.score:v1"]

    def test_register_capability_no_duplicates(self, registry: ModuleRegistry):
        """Register same module twice does not duplicate."""
        registry.register_capability("score_salience", "salience.score:v1")
        registry.register_capability("score_salience", "salience.score:v1")

        modules = registry.resolve_capability("score_salience")
        assert len(modules) == 1
        assert modules == ["salience.score:v1"]

    def test_register_capability_multiple_providers(self, registry: ModuleRegistry):
        """Multiple modules can provide same capability."""
        registry.register_capability("embed", "embedding.fast:v1")
        registry.register_capability("embed", "embedding.accurate:v1")

        modules = registry.resolve_capability("embed")
        assert len(modules) == 2
        assert "embedding.fast:v1" in modules
        assert "embedding.accurate:v1" in modules

    def test_register_capability_multiple_capabilities(self, registry: ModuleRegistry):
        """Module can provide multiple capabilities."""
        registry.register_capability("cap1", "multi.module:v1")
        registry.register_capability("cap2", "multi.module:v1")

        assert registry.resolve_capability("cap1") == ["multi.module:v1"]
        assert registry.resolve_capability("cap2") == ["multi.module:v1"]


class TestResolveCapability:
    """Tests for resolve_capability method."""

    def test_resolve_capability_returns_modules(self, registry: ModuleRegistry):
        """Resolve returns list of module IDs."""
        registry.register_capability("pattern_separate", "hippocampus.pattern_separate:v1")

        result = registry.resolve_capability("pattern_separate")

        assert isinstance(result, list)
        assert result == ["hippocampus.pattern_separate:v1"]

    def test_resolve_unknown_capability_empty(self, registry: ModuleRegistry):
        """Resolve unknown capability returns empty list."""
        result = registry.resolve_capability("nonexistent")

        assert result == []

    def test_resolve_returns_copy(self, registry: ModuleRegistry):
        """Resolve returns copy, not internal list."""
        registry.register_capability("test", "test.module:v1")

        result = registry.resolve_capability("test")
        result.append("modified")

        # Original should be unchanged
        assert registry.resolve_capability("test") == ["test.module:v1"]


class TestUnregisterCapability:
    """Tests for unregister_capability method."""

    def test_unregister_removes_mapping(self, registry: ModuleRegistry):
        """Unregister removes module from capability."""
        registry.register_capability("cap", "module.a:v1")
        registry.register_capability("cap", "module.b:v1")

        result = registry.unregister_capability("cap", "module.a:v1")

        assert result is True
        assert registry.resolve_capability("cap") == ["module.b:v1"]

    def test_unregister_unknown_capability_returns_false(self, registry: ModuleRegistry):
        """Unregister unknown capability returns False."""
        result = registry.unregister_capability("unknown", "module:v1")

        assert result is False

    def test_unregister_unknown_module_returns_false(self, registry: ModuleRegistry):
        """Unregister unknown module returns False."""
        registry.register_capability("cap", "module.a:v1")

        result = registry.unregister_capability("cap", "module.b:v1")

        assert result is False


class TestCapabilityStats:
    """Tests for capability statistics methods."""

    def test_list_capabilities_empty(self, registry: ModuleRegistry):
        """List capabilities returns empty on fresh registry."""
        assert registry.list_capabilities() == []

    def test_list_capabilities_returns_all(self, registry: ModuleRegistry):
        """List capabilities returns all registered."""
        registry.register_capability("cap1", "mod1:v1")
        registry.register_capability("cap2", "mod2:v1")
        registry.register_capability("cap3", "mod3:v1")

        caps = registry.list_capabilities()

        assert set(caps) == {"cap1", "cap2", "cap3"}

    def test_get_capability_stats_empty(self, registry: ModuleRegistry):
        """Stats on empty registry."""
        stats = registry.get_capability_stats()

        assert stats["total_capabilities"] == 0
        assert stats["total_mappings"] == 0

    def test_get_capability_stats_counts(self, registry: ModuleRegistry):
        """Stats returns accurate counts."""
        registry.register_capability("cap1", "mod1:v1")
        registry.register_capability("cap1", "mod2:v1")
        registry.register_capability("cap2", "mod3:v1")

        stats = registry.get_capability_stats()

        assert stats["total_capabilities"] == 2
        assert stats["total_mappings"] == 3


class TestGlobalRegistry:
    """Tests for global registry singleton."""

    def test_get_module_registry_creates_singleton(self):
        """Get creates registry on first call."""
        registry = get_module_registry()

        assert isinstance(registry, ModuleRegistry)

    def test_get_module_registry_returns_same(self):
        """Get returns same instance."""
        reg1 = get_module_registry()
        reg2 = get_module_registry()

        assert reg1 is reg2

    def test_set_module_registry_replaces(self):
        """Set replaces global registry."""
        custom = ModuleRegistry()
        custom.register_capability("custom_cap", "custom:v1")

        set_module_registry(custom)

        assert get_module_registry() is custom
        assert get_module_registry().resolve_capability("custom_cap") == ["custom:v1"]

    def test_reset_clears_global(self):
        """Reset clears global registry."""
        _ = get_module_registry()
        reset_module_registry()

        # Next call creates fresh instance
        new_reg = get_module_registry()
        assert new_reg.list_capabilities() == []


class TestAutoRegistration:
    """Tests for auto-registration during contract load."""

    @pytest.mark.asyncio
    async def test_load_contracts_registers_fabric_capabilities(
        self,
        registry: ModuleRegistry,
        tmp_path: Path,
    ):
        """Loading contract with fabric_capabilities auto-registers."""
        # Create test contract YAML
        contract_yaml = tmp_path / "test_module.v1.yaml"
        contract_yaml.write_text(
            """
module_id: "test.module"
version: "v1"
latency_budget_ms: 50
fabric_callable: true
fabric_capabilities:
  - score_salience
  - analyze_content
"""
        )

        await registry.load_contracts(tmp_path)

        # Capabilities should be registered
        assert "score_salience" in registry.list_capabilities()
        assert "analyze_content" in registry.list_capabilities()
        assert registry.resolve_capability("score_salience") == ["test.module:v1"]
        assert registry.resolve_capability("analyze_content") == ["test.module:v1"]

    @pytest.mark.asyncio
    async def test_load_contracts_no_capabilities(
        self,
        registry: ModuleRegistry,
        tmp_path: Path,
    ):
        """Loading contract without fabric_capabilities registers nothing."""
        # Create test contract YAML without fabric_capabilities
        contract_yaml = tmp_path / "simple.v1.yaml"
        contract_yaml.write_text(
            """
module_id: "simple.module"
version: "v1"
latency_budget_ms: 50
"""
        )

        await registry.load_contracts(tmp_path)

        # No capabilities registered
        assert registry.list_capabilities() == []

    @pytest.mark.asyncio
    async def test_load_multiple_contracts_capabilities(
        self,
        registry: ModuleRegistry,
        tmp_path: Path,
    ):
        """Multiple contracts register capabilities correctly."""
        # Create two modules providing same capability
        (tmp_path / "mod_a.v1.yaml").write_text(
            """
module_id: "domain.mod_a"
version: "v1"
latency_budget_ms: 50
fabric_capabilities:
  - shared_cap
  - unique_a
"""
        )
        (tmp_path / "mod_b.v1.yaml").write_text(
            """
module_id: "domain.mod_b"
version: "v1"
latency_budget_ms: 50
fabric_capabilities:
  - shared_cap
  - unique_b
"""
        )

        await registry.load_contracts(tmp_path)

        # Both registered for shared_cap
        shared_providers = registry.resolve_capability("shared_cap")
        assert len(shared_providers) == 2
        assert "domain.mod_a:v1" in shared_providers
        assert "domain.mod_b:v1" in shared_providers

        # Unique capabilities
        assert registry.resolve_capability("unique_a") == ["domain.mod_a:v1"]
        assert registry.resolve_capability("unique_b") == ["domain.mod_b:v1"]
        assert registry.resolve_capability("unique_b") == ["domain.mod_b:v1"]
        assert registry.resolve_capability("unique_b") == ["domain.mod_b:v1"]
