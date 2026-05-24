"""Kernel-tier bootstrap helpers for k1.spatial."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from k1.spatial.adapters import (
    BridgePlaceRegistryAdapter,
    BrowserDeviceLocationAdapter,
    LocalPlaceRegistryAdapter,
    NominatimGeocoderAdapter,
    NullGeocoderAdapter,
    NullPresenceAdapter,
    NullSpatialMetricsAdapter,
    SelfModelSpatialPolicyAdapter,
    SpatialEventBusAdapter,
    SpatialStateAdapter,
    UUIDSpatialIdAdapter,
)
from k1.spatial.config import SpatialConfig
from k1.spatial.ports import (
    IDeviceLocationPort,
    IGeocoderPort,
    IPlaceRegistryPort,
    IPresencePort,
    ISpatialDeviceContextPort,
    ISpatialEventPort,
    ISpatialIdPort,
    ISpatialMetricsPort,
    ISpatialPolicyPort,
    ISpatialStatePort,
)
from k1.spatial.service import SpatialService
from k1.spatial.service.health import SpatialHealth


@dataclass(frozen=True)
class SpatialServiceBundle:
    """Shared Spatial service dependencies owned by KernelService Tier 1."""

    service: SpatialService
    renderer: Any
    config: SpatialConfig
    device_context_port: ISpatialDeviceContextPort
    device_location_port: IDeviceLocationPort | None
    place_registry_port: IPlaceRegistryPort
    geocoder_port: IGeocoderPort | None
    presence_port: IPresencePort | None
    policy_port: ISpatialPolicyPort | None
    state_port: ISpatialStatePort
    event_port: ISpatialEventPort | None
    id_port: ISpatialIdPort
    metrics_port: ISpatialMetricsPort | None = None

    def build_service(
        self,
        *,
        state_port: ISpatialStatePort,
        policy_port: ISpatialPolicyPort | None = None,
        place_registry_port: IPlaceRegistryPort | None = None,
        presence_port: IPresencePort | None = None,
    ) -> SpatialService:
        """Build a per-session SpatialService from shared Tier-1 ports."""
        return SpatialService(
            device_context_port=self.device_context_port,
            device_location_port=self.device_location_port,
            place_registry_port=place_registry_port or self.place_registry_port,
            geocoder_port=self.geocoder_port,
            presence_port=presence_port if presence_port is not None else self.presence_port,
            policy_port=policy_port if policy_port is not None else self.policy_port,
            state_port=state_port,
            event_port=self.event_port,
            id_port=self.id_port,
            config=self.config,
        )

    def health(self) -> SpatialHealth:
        """Return the bundle's service health snapshot."""
        return self.service.health()

    def shutdown(self) -> None:
        """Synchronously mark the shared service closed."""
        setattr(self.service, "_closed", True)


def build_spatial_bundle(
    *,
    bus: Any | None = None,
    device_context_port: ISpatialDeviceContextPort | None = None,
    device_location_port: IDeviceLocationPort | None = None,
    place_registry_port: IPlaceRegistryPort | None = None,
    bridge_client: Any | None = None,
    geocoder_port: IGeocoderPort | None = None,
    presence_port: IPresencePort | None = None,
    policy_port: ISpatialPolicyPort | None = None,
    state_port: ISpatialStatePort | None = None,
    event_port: ISpatialEventPort | None = None,
    id_port: ISpatialIdPort | None = None,
    metrics_port: ISpatialMetricsPort | None = None,
    config: SpatialConfig | None = None,
) -> SpatialServiceBundle:
    """Build the Tier-1 Spatial bundle with production defaults."""
    from k1.spatial.factory import SpatialFactory

    if device_context_port is None:
        return SpatialFactory.create_standalone(config=config)
    event = (
        event_port
        if event_port is not None
        else (SpatialEventBusAdapter(bus) if bus is not None else None)
    )
    registry = place_registry_port
    if registry is None:
        registry = (
            BridgePlaceRegistryAdapter(bridge_client)
            if bridge_client is not None
            else LocalPlaceRegistryAdapter()
        )
    location = device_location_port or BrowserDeviceLocationAdapter(device_context_port)
    return SpatialFactory.create_production(
        device_context_port=device_context_port,
        device_location_port=location,
        place_registry_port=registry,
        geocoder_port=geocoder_port or _default_geocoder(),
        presence_port=presence_port or NullPresenceAdapter(),
        policy_port=policy_port or SelfModelSpatialPolicyAdapter(config=config),
        state_port=state_port or SpatialStateAdapter(),
        event_port=event,
        id_port=id_port or UUIDSpatialIdAdapter(),
        metrics_port=metrics_port or NullSpatialMetricsAdapter(),
        config=config,
    )


def _default_geocoder() -> IGeocoderPort:
    mode = os.environ.get("K1_SPATIAL_GEOCODER", "none").strip().lower()
    if mode in {"nominatim", "osm", "openstreetmap"}:
        return NominatimGeocoderAdapter(
            endpoint=os.environ.get(
                "K1_SPATIAL_GEOCODER_ENDPOINT",
                "https://nominatim.openstreetmap.org",
            ),
            user_agent=os.environ.get(
                "K1_SPATIAL_GEOCODER_USER_AGENT",
                "familyos-k1-spatial/1.0",
            ),
        )
    return NullGeocoderAdapter()


__all__ = ["SpatialServiceBundle", "build_spatial_bundle"]
