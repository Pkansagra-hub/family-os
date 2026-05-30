"""Factory for k1.spatial service wiring."""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import combinations
from typing import Any

from k1.grounding.types import DeviceContextSnapshot
from k1.spatial.adapters import (
    BrowserDeviceLocationAdapter,
    LocalPlaceRegistryAdapter,
    NullGeocoderAdapter,
    NullPresenceAdapter,
    NullSpatialMetricsAdapter,
    SelfModelSpatialPolicyAdapter,
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


class MissingSpatialPortError(ValueError):
    """Raised when a required spatial port is absent."""


class InvalidSpatialPortError(TypeError):
    """Raised when an injected port does not satisfy its Protocol."""


class DuplicateSpatialPortError(ValueError):
    """Raised when two spatial port roles share one object identity."""


class SpatialFactory:
    """Composition root for :class:`SpatialService` and its bundle."""

    def __init__(self) -> None:
        raise TypeError("SpatialFactory uses static factory methods; do not instantiate it")

    @staticmethod
    def create_standalone(config: SpatialConfig | None = None):
        """Create a standalone spatial bundle with explicit unknown device state."""
        device_context = _StandaloneDeviceContextPort()
        return SpatialFactory.create_with_ports(
            device_context_port=device_context,
            device_location_port=BrowserDeviceLocationAdapter(device_context),
            place_registry_port=LocalPlaceRegistryAdapter(),
            geocoder_port=NullGeocoderAdapter(),
            presence_port=NullPresenceAdapter(),
            policy_port=SelfModelSpatialPolicyAdapter(config=config),
            state_port=SpatialStateAdapter(),
            event_port=None,
            id_port=UUIDSpatialIdAdapter(),
            metrics_port=NullSpatialMetricsAdapter(),
            config=config,
        )

    @staticmethod
    def create_for_testing(config: SpatialConfig | None = None, **overrides: Any):
        """Create a test bundle plus the concrete adapter dictionary."""
        device_context = _StandaloneDeviceContextPort()
        adapters: dict[str, Any] = {
            "device_context_port": device_context,
            "device_location_port": BrowserDeviceLocationAdapter(device_context),
            "place_registry_port": LocalPlaceRegistryAdapter(),
            "geocoder_port": NullGeocoderAdapter(),
            "presence_port": NullPresenceAdapter(),
            "policy_port": SelfModelSpatialPolicyAdapter(config=config),
            "state_port": SpatialStateAdapter(),
            "event_port": None,
            "id_port": UUIDSpatialIdAdapter(),
            "metrics_port": NullSpatialMetricsAdapter(),
        }
        adapters.update(overrides)
        bundle = SpatialFactory.create_with_ports(config=config, **adapters)
        return bundle, adapters

    @staticmethod
    def create_production(
        *,
        device_context_port: ISpatialDeviceContextPort,
        device_location_port: IDeviceLocationPort | None = None,
        place_registry_port: IPlaceRegistryPort | None = None,
        geocoder_port: IGeocoderPort | None = None,
        presence_port: IPresencePort | None = None,
        policy_port: ISpatialPolicyPort | None = None,
        state_port: ISpatialStatePort | None = None,
        event_port: ISpatialEventPort | None = None,
        id_port: ISpatialIdPort | None = None,
        metrics_port: ISpatialMetricsPort | None = None,
        config: SpatialConfig | None = None,
    ):
        """Create the production spatial bundle from explicit ports."""
        return SpatialFactory.create_with_ports(
            device_context_port=device_context_port,
            device_location_port=device_location_port,
            place_registry_port=place_registry_port or LocalPlaceRegistryAdapter(),
            geocoder_port=geocoder_port,
            presence_port=presence_port,
            policy_port=policy_port,
            state_port=state_port or SpatialStateAdapter(),
            event_port=event_port,
            id_port=id_port or UUIDSpatialIdAdapter(),
            metrics_port=metrics_port,
            config=config,
        )

    @staticmethod
    def create_with_ports(
        *,
        device_context_port: ISpatialDeviceContextPort,
        device_location_port: IDeviceLocationPort | None = None,
        place_registry_port: IPlaceRegistryPort,
        geocoder_port: IGeocoderPort | None = None,
        presence_port: IPresencePort | None = None,
        policy_port: ISpatialPolicyPort | None = None,
        state_port: ISpatialStatePort,
        event_port: ISpatialEventPort | None = None,
        id_port: ISpatialIdPort,
        metrics_port: ISpatialMetricsPort | None = None,
        config: SpatialConfig | None = None,
    ):
        """Create a spatial bundle from explicit port implementations."""
        cfg = config or SpatialConfig()
        effective_location = device_location_port or BrowserDeviceLocationAdapter(
            device_context_port
        )
        effective_geocoder = geocoder_port or NullGeocoderAdapter()
        effective_presence = presence_port or NullPresenceAdapter()
        effective_policy = policy_port or SelfModelSpatialPolicyAdapter(config=cfg)
        effective_metrics = metrics_port or NullSpatialMetricsAdapter()

        ports: dict[str, tuple[Any, Any, bool]] = {
            "device_context_port": (device_context_port, ISpatialDeviceContextPort, True),
            "device_location_port": (effective_location, IDeviceLocationPort, False),
            "place_registry_port": (place_registry_port, IPlaceRegistryPort, True),
            "geocoder_port": (effective_geocoder, IGeocoderPort, False),
            "presence_port": (effective_presence, IPresencePort, False),
            "policy_port": (effective_policy, ISpatialPolicyPort, False),
            "state_port": (state_port, ISpatialStatePort, True),
            "event_port": (event_port, ISpatialEventPort, False),
            "id_port": (id_port, ISpatialIdPort, True),
            "metrics_port": (effective_metrics, ISpatialMetricsPort, False),
        }
        SpatialFactory._validate_ports(ports)

        service = SpatialService(
            device_context_port=device_context_port,
            device_location_port=effective_location,
            place_registry_port=place_registry_port,
            geocoder_port=effective_geocoder,
            presence_port=effective_presence,
            policy_port=effective_policy,
            state_port=state_port,
            event_port=event_port,
            id_port=id_port,
            config=cfg,
        )

        from k1.spatial.kernel.bootstrap import SpatialServiceBundle
        from k1.spatial.service import projection_renderer

        return SpatialServiceBundle(
            service=service,
            renderer=projection_renderer,
            config=cfg,
            device_context_port=device_context_port,
            device_location_port=effective_location,
            place_registry_port=place_registry_port,
            geocoder_port=effective_geocoder,
            presence_port=effective_presence,
            policy_port=effective_policy,
            state_port=state_port,
            event_port=event_port,
            id_port=id_port,
            metrics_port=effective_metrics,
        )

    @staticmethod
    def _validate_ports(ports: dict[str, tuple[Any, Any, bool]]) -> None:
        failures: list[str] = []
        present: dict[str, Any] = {}
        for name, (port, protocol, required) in ports.items():
            if port is None:
                if required:
                    failures.append(f"missing required port: {name}")
                continue
            if not isinstance(port, protocol):
                failures.append(
                    f"invalid port: {name} ({type(port).__name__}) does not satisfy "
                    f"{protocol.__name__}"
                )
                continue
            present[name] = port

        for left, right in combinations(present, 2):
            if present[left] is present[right]:
                failures.append(f"duplicate port identity: {left} and {right}")

        if failures:
            if any(item.startswith("missing") for item in failures):
                raise MissingSpatialPortError("; ".join(failures))
            if any(item.startswith("duplicate") for item in failures):
                raise DuplicateSpatialPortError("; ".join(failures))
            raise InvalidSpatialPortError("; ".join(failures))


class _StandaloneDeviceContextPort(ISpatialDeviceContextPort):
    """Small unknown-device provider for standalone/test wiring."""

    async def get_device_snapshot(
        self,
        session_id: str,
        device_id: str,
        installation_id: str,
    ) -> DeviceContextSnapshot:
        now = datetime.now(UTC).isoformat()
        return DeviceContextSnapshot(
            session_id=session_id,
            device_id=device_id or "device:unknown",
            installation_id=installation_id or "installation:unknown",
            observed_at_utc=now,
            surface="unknown",
            location_permission="unavailable",
            semantic_place_hint=None,
        )


__all__ = [
    "DuplicateSpatialPortError",
    "InvalidSpatialPortError",
    "MissingSpatialPortError",
    "SpatialFactory",
]
