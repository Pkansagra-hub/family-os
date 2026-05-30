"""Kernel-tier bootstrap helpers for k1.grounding."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from k1.grounding.adapters import (
    EventBusAdapter,
    GroundingStateAdapter,
    NullMetricsAdapter,
    SelfModelPolicyAdapter,
    SpatialHandleAdapter,
    StaticIdentityAdapter,
    UuidIdAdapter,
)
from k1.grounding.config import GroundingConfig
from k1.grounding.ports import (
    IGroundingEventPort,
    IGroundingIdentityPort,
    IGroundingIdPort,
    IGroundingMetricsPort,
    IGroundingPolicyPort,
    IGroundingSpatialPort,
    IGroundingStatePort,
    IGroundingTemporalPort,
)
from k1.grounding.service import GroundingHealthStatus, GroundingService


@dataclass(frozen=True)
class GroundingServiceBundle:
    """Shared Grounding service dependencies owned by KernelService Tier 1."""

    service: GroundingService
    renderer: Any
    config: GroundingConfig
    temporal_port: IGroundingTemporalPort
    spatial_port: IGroundingSpatialPort
    id_port: IGroundingIdPort
    state_port: IGroundingStatePort
    identity_port: IGroundingIdentityPort | None = None
    policy_port: IGroundingPolicyPort | None = None
    event_port: IGroundingEventPort | None = None
    metrics_port: IGroundingMetricsPort | None = None

    def build_service(
        self,
        *,
        state_port: IGroundingStatePort,
        temporal_port: IGroundingTemporalPort | None = None,
        spatial_port: IGroundingSpatialPort | None = None,
        identity_port: IGroundingIdentityPort | None = None,
        policy_port: IGroundingPolicyPort | None = None,
    ) -> GroundingService:
        """Build a per-session GroundingService from shared Tier-1 ports."""
        return GroundingService(
            temporal_port=temporal_port or self.temporal_port,
            spatial_port=spatial_port or self.spatial_port,
            id_port=self.id_port,
            state_port=state_port,
            identity_port=identity_port if identity_port is not None else self.identity_port,
            policy_port=policy_port if policy_port is not None else self.policy_port,
            event_port=self.event_port,
            metrics_port=self.metrics_port,
            config=self.config,
        )

    def health(self) -> GroundingHealthStatus:
        """Return the bundle's service health snapshot."""
        return self.service.health()

    def shutdown(self) -> None:
        """Synchronously mark the shared service closed."""
        setattr(self.service, "_closed", True)


def build_grounding_bundle(
    *,
    bus: Any | None = None,
    temporal_port: IGroundingTemporalPort | None = None,
    spatial_port: IGroundingSpatialPort | None = None,
    id_port: IGroundingIdPort | None = None,
    state_port: IGroundingStatePort | None = None,
    identity_port: IGroundingIdentityPort | None = None,
    policy_port: IGroundingPolicyPort | None = None,
    event_port: IGroundingEventPort | None = None,
    metrics_port: IGroundingMetricsPort | None = None,
    config: GroundingConfig | None = None,
) -> GroundingServiceBundle:
    """Build the Tier-1 Grounding bundle with production defaults."""
    from k1.grounding.factory import GroundingFactory

    event = (
        event_port
        if event_port is not None
        else (EventBusAdapter(bus) if bus is not None else None)
    )
    if temporal_port is None:
        return GroundingFactory.create_standalone(config=config)
    return GroundingFactory.create_production(
        temporal_port=temporal_port,
        spatial_port=spatial_port or SpatialHandleAdapter(),
        id_port=id_port or UuidIdAdapter(),
        state_port=state_port or GroundingStateAdapter(allow_memory_fallback=True),
        identity_port=identity_port or StaticIdentityAdapter(),
        policy_port=policy_port or SelfModelPolicyAdapter(),
        event_port=event,
        metrics_port=metrics_port or NullMetricsAdapter(),
        config=config,
    )


__all__ = ["GroundingServiceBundle", "build_grounding_bundle"]
