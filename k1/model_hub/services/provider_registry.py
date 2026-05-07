"""Provider registry -- manifest scanning, plugin lifecycle, capability indexing [F43].

Manages the runtime registry of provider plugins and their capabilities.
Scans manifest files, loads plugins, builds capability index for O(1)
capability-to-provider lookups.

Import graph (Layer 3 -- imports Layer 0 + Layer 1 + Layer 2)
--------------------------------------------------------------
k1.model_hub.services.provider_registry
  -> k1.model_hub.types       (Layer 0: CapabilityType, HealthStatus, PlacementType, ModelTier)
  -> k1.model_hub.config      (Layer 0: ModelHubConfig)
  -> k1.model_hub.manifest    (Layer 0: ProviderManifest, ModelSpec, load_manifest)
  -> k1.model_hub.plugins.base (Layer 2: IProviderPlugin, ProviderHealth)
  -> stdlib only

NEVER import from any adapter or runtime module.

References
----------
- model_hub.mmd: ProviderRegistry service
- Invariant MH-17: Plugin isolation
- Invariant MH-18: Manifest is SOLE capability truth
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from k1.model_hub.config import ModelHubConfig
from k1.model_hub.manifest import ModelSpec, ProviderManifest
from k1.model_hub.plugins.base import IProviderPlugin
from k1.model_hub.types import CapabilityType, HealthStatus, PlacementType

# ===========================================================================
# Supporting data types
# ===========================================================================


@dataclass(frozen=True)
class ProviderInfo:
    """Summary of a registered provider for routing decisions.

    Built from ProviderManifest on registration. Lightweight view
    for CapabilityRouter and ModelSelector.
    """

    provider_id: str
    capabilities: List[CapabilityType] = field(default_factory=list)
    models: List[ModelSpec] = field(default_factory=list)
    placement_type: PlacementType = PlacementType.REMOTE
    health_status: HealthStatus = HealthStatus.HEALTHY

    def __post_init__(self) -> None:
        if not self.provider_id:
            raise ValueError("ProviderInfo.provider_id must be non-empty")


# ===========================================================================
# ProviderRegistry
# ===========================================================================


class ProviderRegistry:
    """Runtime registry of provider plugins and capability index.

    Manages plugin lifecycle (register/unregister), manifest storage,
    and O(1) capability-to-provider lookups.

    Constructor:
        config: ModelHubConfig for manifest_dir, etc.

    Internal state:
        _plugins: dict[str, IProviderPlugin]
        _manifests: dict[str, ProviderManifest]
        _capability_index: dict[CapabilityType, list[ProviderInfo]]

    Invariants:
        MH-17: Plugin isolation (one plugin crash does not affect others).
        MH-18: Manifest is SOLE source of truth for provider capabilities.
    """

    def __init__(self, config: ModelHubConfig) -> None:
        self._config = config
        self._plugins: Dict[str, IProviderPlugin] = {}
        self._manifests: Dict[str, ProviderManifest] = {}
        self._provider_info: Dict[str, ProviderInfo] = {}
        self._capability_index: Dict[CapabilityType, List[ProviderInfo]] = {}

    # -- Registration ----------------------------------------------------------

    def register(
        self,
        manifest: ProviderManifest,
        plugin: IProviderPlugin,
    ) -> None:
        """Register a provider with its manifest and plugin instance.

        Builds ProviderInfo from manifest and updates capability index.
        Raises ValueError if provider_id is already registered.

        Args:
            manifest: Parsed provider manifest.
            plugin: Initialized plugin instance.
        """
        pid = manifest.provider_id
        if pid in self._plugins:
            raise ValueError(f"Provider already registered: {pid}")

        self._plugins[pid] = plugin
        self._manifests[pid] = manifest

        # Build ProviderInfo from manifest (MH-18)
        all_caps = set(manifest.capabilities)
        for model in manifest.models:
            all_caps.update(model.capabilities)

        info = ProviderInfo(
            provider_id=pid,
            capabilities=sorted(all_caps, key=lambda c: c.value),
            models=list(manifest.models),
            placement_type=manifest.placement.type,
        )
        self._provider_info[pid] = info

        # Rebuild capability index
        self._rebuild_capability_index()

    def unregister(self, provider_id: str) -> None:
        """Remove a provider from the registry.

        Raises KeyError if provider_id is not registered.

        Args:
            provider_id: ID of the provider to remove.
        """
        if provider_id not in self._plugins:
            raise KeyError(f"Provider not registered: {provider_id}")

        del self._plugins[provider_id]
        del self._manifests[provider_id]
        del self._provider_info[provider_id]

        # Rebuild capability index
        self._rebuild_capability_index()

    # -- Queries ---------------------------------------------------------------

    def get_plugin(self, provider_id: str) -> IProviderPlugin:
        """Get plugin instance for a provider.

        Raises KeyError if provider_id is not registered.
        """
        if provider_id not in self._plugins:
            raise KeyError(f"Provider not registered: {provider_id}")
        return self._plugins[provider_id]

    def get_manifest(self, provider_id: str) -> ProviderManifest:
        """Get manifest for a provider.

        Raises KeyError if provider_id is not registered.
        """
        if provider_id not in self._manifests:
            raise KeyError(f"Provider not registered: {provider_id}")
        return self._manifests[provider_id]

    def get_provider_info(self, provider_id: str) -> ProviderInfo:
        """Get ProviderInfo for a provider.

        Raises KeyError if provider_id is not registered.
        """
        if provider_id not in self._provider_info:
            raise KeyError(f"Provider not registered: {provider_id}")
        return self._provider_info[provider_id]

    def list_providers(self) -> List[ProviderInfo]:
        """List all registered providers."""
        return list(self._provider_info.values())

    def get_capability_index(self) -> Dict[CapabilityType, List[ProviderInfo]]:
        """Get the capability-to-provider index.

        O(1) lookup: "which providers support TOOL_CALL?"
        NEVER hardcodes provider names (MH-18).
        """
        return dict(self._capability_index)

    def get_providers_for_capability(self, capability: CapabilityType) -> List[ProviderInfo]:
        """Get providers supporting a given capability.

        Args:
            capability: Capability type to look up.

        Returns:
            List of ProviderInfo supporting the capability. Empty if none.
        """
        return list(self._capability_index.get(capability, []))

    def is_registered(self, provider_id: str) -> bool:
        """Check if a provider is registered."""
        return provider_id in self._plugins

    @property
    def provider_count(self) -> int:
        """Number of registered providers."""
        return len(self._plugins)

    # -- Internal --------------------------------------------------------------

    def _rebuild_capability_index(self) -> None:
        """Rebuild the capability index from all registered providers.

        Union of manifest-level and model-level capabilities.
        MH-18: Manifest is SOLE capability truth.
        """
        index: Dict[CapabilityType, List[ProviderInfo]] = {}
        for info in self._provider_info.values():
            for cap in info.capabilities:
                if cap not in index:
                    index[cap] = []
                index[cap].append(info)
        self._capability_index = index


__all__ = [
    "ProviderInfo",
    "ProviderRegistry",
]
