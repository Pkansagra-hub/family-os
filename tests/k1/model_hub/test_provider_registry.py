"""M3 Routing & Selection -- Test ProviderRegistry [F43].

Tests provider registration/unregistration, capability index building,
plugin/manifest/info queries, and edge cases.

Covers:
  - ProviderInfo: construction, validation, defaults, frozen
  - ProviderRegistry: register, unregister, queries, capability index
  - Edge cases: duplicate registration, unknown provider, empty registry
  - Invariant MH-17: Plugin isolation (independent add/remove)
  - Invariant MH-18: Manifest is SOLE capability truth

NO MOCKS.  Minimal stub plugin for registration.
"""

from __future__ import annotations

from typing import AsyncIterator, List

import pytest

from k1.model_hub.config import ModelHubConfig
from k1.model_hub.manifest import ModelSpec, PlacementConfig, ProviderManifest
from k1.model_hub.plugins.base import (
    NormalizedRequest,
    ProviderChunk,
    ProviderHealth,
    ProviderResponse,
)
from k1.model_hub.services.provider_registry import ProviderInfo, ProviderRegistry
from k1.model_hub.types import CapabilityType, HealthStatus, ModelTier, PlacementType

# ===========================================================================
# Stub plugin (minimal implementation of IProviderPlugin)
# ===========================================================================


class _StubPlugin:
    """Minimal plugin stub for registry tests."""

    async def initialize(self, manifest: ProviderManifest) -> None:
        pass

    def supports(self, capability: CapabilityType) -> bool:
        return True

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        return ProviderResponse(text="stub")

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        yield ProviderChunk(delta="stub")

    def estimate_tokens(self, text: str) -> int:
        return len(text.split())

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(status=HealthStatus.HEALTHY)

    async def close(self) -> None:
        pass


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def config() -> ModelHubConfig:
    return ModelHubConfig()


@pytest.fixture
def registry(config: ModelHubConfig) -> ProviderRegistry:
    return ProviderRegistry(config)


@pytest.fixture
def stub_plugin() -> _StubPlugin:
    return _StubPlugin()


def _make_manifest(
    provider_id: str = "openai",
    capabilities: List[CapabilityType] | None = None,
    models: List[ModelSpec] | None = None,
    placement_type: PlacementType = PlacementType.REMOTE,
) -> ProviderManifest:
    """Helper to build ProviderManifest for tests."""
    return ProviderManifest(
        provider_id=provider_id,
        display_name=f"Test {provider_id}",
        capabilities=capabilities or [CapabilityType.CHAT],
        models=models
        or [
            ModelSpec(
                id="gpt-4o",
                capabilities=[CapabilityType.CHAT, CapabilityType.TOOL_CALL],
                cost_per_1m_input=2.5,
                cost_per_1m_output=10.0,
                tier=ModelTier.PREMIUM,
            ),
        ],
        placement=PlacementConfig(type=placement_type),
    )


# ===========================================================================
# ProviderInfo Tests
# ===========================================================================


class TestProviderInfo:
    """Tests for ProviderInfo dataclass."""

    def test_defaults(self) -> None:
        info = ProviderInfo(provider_id="openai")
        assert info.provider_id == "openai"
        assert info.capabilities == []
        assert info.models == []
        assert info.placement_type == PlacementType.REMOTE
        assert info.health_status == HealthStatus.HEALTHY

    def test_custom_values(self) -> None:
        info = ProviderInfo(
            provider_id="local-llm",
            capabilities=[CapabilityType.CHAT, CapabilityType.EMBED],
            placement_type=PlacementType.LOCAL_GPU,
            health_status=HealthStatus.DEGRADED,
        )
        assert info.provider_id == "local-llm"
        assert CapabilityType.CHAT in info.capabilities
        assert info.placement_type == PlacementType.LOCAL_GPU
        assert info.health_status == HealthStatus.DEGRADED

    def test_frozen(self) -> None:
        info = ProviderInfo(provider_id="openai")
        with pytest.raises(AttributeError):
            info.provider_id = "other"  # type: ignore[misc]

    def test_empty_provider_id_raises(self) -> None:
        with pytest.raises(ValueError, match="provider_id must be non-empty"):
            ProviderInfo(provider_id="")

    def test_with_models(self) -> None:
        model = ModelSpec(id="gpt-4o", capabilities=[CapabilityType.CHAT])
        info = ProviderInfo(provider_id="openai", models=[model])
        assert len(info.models) == 1
        assert info.models[0].id == "gpt-4o"


# ===========================================================================
# ProviderRegistry Registration Tests
# ===========================================================================


class TestProviderRegistryRegistration:
    """Tests for register/unregister operations."""

    def test_register_single_provider(
        self, registry: ProviderRegistry, stub_plugin: _StubPlugin
    ) -> None:
        manifest = _make_manifest("openai")
        registry.register(manifest, stub_plugin)

        assert registry.is_registered("openai")
        assert registry.provider_count == 1

    def test_register_multiple_providers(
        self, registry: ProviderRegistry, stub_plugin: _StubPlugin
    ) -> None:
        for pid in ["openai", "anthropic", "local-llm"]:
            manifest = _make_manifest(pid)
            registry.register(manifest, _StubPlugin())

        assert registry.provider_count == 3
        assert registry.is_registered("openai")
        assert registry.is_registered("anthropic")
        assert registry.is_registered("local-llm")

    def test_register_duplicate_raises(
        self, registry: ProviderRegistry, stub_plugin: _StubPlugin
    ) -> None:
        manifest = _make_manifest("openai")
        registry.register(manifest, stub_plugin)

        with pytest.raises(ValueError, match="already registered"):
            registry.register(manifest, _StubPlugin())

    def test_unregister_provider(
        self, registry: ProviderRegistry, stub_plugin: _StubPlugin
    ) -> None:
        manifest = _make_manifest("openai")
        registry.register(manifest, stub_plugin)
        registry.unregister("openai")

        assert not registry.is_registered("openai")
        assert registry.provider_count == 0

    def test_unregister_unknown_raises(self, registry: ProviderRegistry) -> None:
        with pytest.raises(KeyError, match="not registered"):
            registry.unregister("nonexistent")

    def test_register_after_unregister(
        self, registry: ProviderRegistry, stub_plugin: _StubPlugin
    ) -> None:
        manifest = _make_manifest("openai")
        registry.register(manifest, stub_plugin)
        registry.unregister("openai")
        registry.register(manifest, _StubPlugin())
        assert registry.is_registered("openai")


# ===========================================================================
# ProviderRegistry Query Tests
# ===========================================================================


class TestProviderRegistryQueries:
    """Tests for get_plugin, get_manifest, get_provider_info, list_providers."""

    def test_get_plugin(self, registry: ProviderRegistry, stub_plugin: _StubPlugin) -> None:
        manifest = _make_manifest("openai")
        registry.register(manifest, stub_plugin)

        plugin = registry.get_plugin("openai")
        assert plugin is stub_plugin

    def test_get_plugin_unknown_raises(self, registry: ProviderRegistry) -> None:
        with pytest.raises(KeyError, match="not registered"):
            registry.get_plugin("nonexistent")

    def test_get_manifest(self, registry: ProviderRegistry, stub_plugin: _StubPlugin) -> None:
        manifest = _make_manifest("openai")
        registry.register(manifest, stub_plugin)

        result = registry.get_manifest("openai")
        assert result.provider_id == "openai"
        assert result is manifest

    def test_get_manifest_unknown_raises(self, registry: ProviderRegistry) -> None:
        with pytest.raises(KeyError, match="not registered"):
            registry.get_manifest("nonexistent")

    def test_get_provider_info(self, registry: ProviderRegistry, stub_plugin: _StubPlugin) -> None:
        manifest = _make_manifest("openai")
        registry.register(manifest, stub_plugin)

        info = registry.get_provider_info("openai")
        assert info.provider_id == "openai"
        assert CapabilityType.CHAT in info.capabilities
        assert CapabilityType.TOOL_CALL in info.capabilities

    def test_get_provider_info_unknown_raises(self, registry: ProviderRegistry) -> None:
        with pytest.raises(KeyError, match="not registered"):
            registry.get_provider_info("nonexistent")

    def test_list_providers_empty(self, registry: ProviderRegistry) -> None:
        assert registry.list_providers() == []

    def test_list_providers(self, registry: ProviderRegistry, stub_plugin: _StubPlugin) -> None:
        for pid in ["openai", "anthropic"]:
            registry.register(_make_manifest(pid), _StubPlugin())

        providers = registry.list_providers()
        assert len(providers) == 2
        pids = {p.provider_id for p in providers}
        assert pids == {"openai", "anthropic"}

    def test_provider_count(self, registry: ProviderRegistry, stub_plugin: _StubPlugin) -> None:
        assert registry.provider_count == 0
        registry.register(_make_manifest("openai"), _StubPlugin())
        assert registry.provider_count == 1
        registry.register(_make_manifest("anthropic"), _StubPlugin())
        assert registry.provider_count == 2


# ===========================================================================
# Capability Index Tests (MH-18)
# ===========================================================================


class TestCapabilityIndex:
    """Tests for capability index building and querying."""

    def test_capability_index_empty(self, registry: ProviderRegistry) -> None:
        assert registry.get_capability_index() == {}

    def test_capability_index_single_provider(self, registry: ProviderRegistry) -> None:
        manifest = _make_manifest(
            "openai",
            capabilities=[CapabilityType.CHAT],
            models=[
                ModelSpec(
                    id="gpt-4o",
                    capabilities=[CapabilityType.CHAT, CapabilityType.TOOL_CALL],
                ),
            ],
        )
        registry.register(manifest, _StubPlugin())

        index = registry.get_capability_index()
        assert CapabilityType.CHAT in index
        assert CapabilityType.TOOL_CALL in index
        assert len(index[CapabilityType.CHAT]) == 1
        assert index[CapabilityType.CHAT][0].provider_id == "openai"

    def test_capability_index_multiple_providers_same_cap(self, registry: ProviderRegistry) -> None:
        for pid in ["openai", "anthropic"]:
            manifest = _make_manifest(
                pid,
                capabilities=[CapabilityType.CHAT],
                models=[ModelSpec(id=f"model-{pid}", capabilities=[CapabilityType.CHAT])],
            )
            registry.register(manifest, _StubPlugin())

        providers = registry.get_providers_for_capability(CapabilityType.CHAT)
        assert len(providers) == 2
        pids = {p.provider_id for p in providers}
        assert pids == {"openai", "anthropic"}

    def test_capability_index_union_of_manifest_and_model(self, registry: ProviderRegistry) -> None:
        """MH-18: capabilities are union of manifest-level + model-level."""
        manifest = _make_manifest(
            "openai",
            capabilities=[CapabilityType.CHAT],
            models=[
                ModelSpec(
                    id="gpt-4o",
                    capabilities=[CapabilityType.TOOL_CALL, CapabilityType.VISION],
                ),
            ],
        )
        registry.register(manifest, _StubPlugin())

        index = registry.get_capability_index()
        assert CapabilityType.CHAT in index
        assert CapabilityType.TOOL_CALL in index
        assert CapabilityType.VISION in index

    def test_get_providers_for_capability_unknown(self, registry: ProviderRegistry) -> None:
        result = registry.get_providers_for_capability(CapabilityType.EMBED)
        assert result == []

    def test_capability_index_rebuilt_after_unregister(self, registry: ProviderRegistry) -> None:
        registry.register(
            _make_manifest(
                "openai",
                capabilities=[CapabilityType.CHAT],
                models=[ModelSpec(id="m1", capabilities=[CapabilityType.CHAT])],
            ),
            _StubPlugin(),
        )
        registry.register(
            _make_manifest(
                "anthropic",
                capabilities=[CapabilityType.CHAT],
                models=[ModelSpec(id="m2", capabilities=[CapabilityType.CHAT])],
            ),
            _StubPlugin(),
        )

        assert len(registry.get_providers_for_capability(CapabilityType.CHAT)) == 2

        registry.unregister("openai")
        providers = registry.get_providers_for_capability(CapabilityType.CHAT)
        assert len(providers) == 1
        assert providers[0].provider_id == "anthropic"

    def test_provider_info_models_from_manifest(self, registry: ProviderRegistry) -> None:
        """Registered ProviderInfo should carry manifest models."""
        models = [
            ModelSpec(id="fast", capabilities=[CapabilityType.CHAT], tier=ModelTier.FAST),
            ModelSpec(id="premium", capabilities=[CapabilityType.CHAT], tier=ModelTier.PREMIUM),
        ]
        manifest = _make_manifest("openai", models=models)
        registry.register(manifest, _StubPlugin())

        info = registry.get_provider_info("openai")
        assert len(info.models) == 2
        ids = {m.id for m in info.models}
        assert ids == {"fast", "premium"}

    def test_placement_type_from_manifest(self, registry: ProviderRegistry) -> None:
        manifest = _make_manifest("local-llm", placement_type=PlacementType.LOCAL_GPU)
        registry.register(manifest, _StubPlugin())

        info = registry.get_provider_info("local-llm")
        assert info.placement_type == PlacementType.LOCAL_GPU

    def test_is_registered_false(self, registry: ProviderRegistry) -> None:
        assert not registry.is_registered("nonexistent")

    def test_capability_index_returns_copy(self, registry: ProviderRegistry) -> None:
        """get_capability_index returns a copy, not the internal dict."""
        registry.register(
            _make_manifest("openai", capabilities=[CapabilityType.CHAT]),
            _StubPlugin(),
        )
        idx1 = registry.get_capability_index()
        idx2 = registry.get_capability_index()
        assert idx1 is not idx2


# ===========================================================================
# Re-exports Test
# ===========================================================================


class TestProviderRegistryReExports:
    """Test that services/__init__.py re-exports M3 registry types."""

    def test_provider_info_reexport(self) -> None:
        from k1.model_hub.services import ProviderInfo as Reexported

        assert Reexported is ProviderInfo

    def test_provider_registry_reexport(self) -> None:
        from k1.model_hub.services import ProviderRegistry as Reexported

        assert Reexported is ProviderRegistry
