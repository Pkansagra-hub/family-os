"""Kernel-tier bootstrap helpers for k1.temporal."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from k1.temporal.adapters import (
    EventBusAdapter,
    NullMetricsAdapter,
    NullRoutineAdapter,
    SystemClockAdapter,
    TemporalStateAdapter,
    UuidIdAdapter,
)
from k1.temporal.config import TemporalConfig
from k1.temporal.ports import (
    IClockPort,
    IRoutinePort,
    ITemporalDeviceContextPort,
    ITemporalEventPort,
    ITemporalIdPort,
    ITemporalMetricsPort,
    ITemporalPolicyPort,
    ITemporalStatePort,
    ITimezonePort,
)
from k1.temporal.service import TemporalService
from k1.temporal.service.health import TemporalHealthStatus


@dataclass(frozen=True)
class TemporalServiceBundle:
    """Shared Temporal service dependencies owned by KernelService Tier 1."""

    service: TemporalService
    renderer: Any
    config: TemporalConfig
    clock_port: IClockPort
    id_port: ITemporalIdPort
    event_port: ITemporalEventPort | None = None
    device_context_port: ITemporalDeviceContextPort | None = None
    spatial_timezone_port: ITimezonePort | None = None
    persona_timezone_port: ITimezonePort | None = None
    routine_port: IRoutinePort | None = None
    metrics_port: ITemporalMetricsPort | None = None
    policy_port: ITemporalPolicyPort | None = None

    def build_service(
        self,
        *,
        state_port: ITemporalStatePort,
        persona_timezone_port: ITimezonePort | None = None,
    ) -> TemporalService:
        """Build a per-session TemporalService from shared Tier-1 ports."""
        return TemporalService(
            clock=self.clock_port,
            id_port=self.id_port,
            state_port=state_port,
            event_port=self.event_port,
            device_context_port=self.device_context_port,
            spatial_timezone_port=self.spatial_timezone_port,
            persona_timezone_port=persona_timezone_port or self.persona_timezone_port,
            routine_port=self.routine_port,
            metrics_port=self.metrics_port,
            config=self.config,
        )

    def health(self) -> TemporalHealthStatus:
        """Return the bundle's service health snapshot."""
        return self.service.health()

    def shutdown(self) -> None:
        """Synchronously mark the shared service closed."""
        setattr(self.service, "_closed", True)


def build_temporal_bundle(
    *,
    bus: Any | None = None,
    clock_port: IClockPort | None = None,
    event_port: ITemporalEventPort | None = None,
    state_port: ITemporalStatePort | None = None,
    device_context_port: ITemporalDeviceContextPort | None = None,
    timezone_port: ITimezonePort | None = None,
    spatial_timezone_port: ITimezonePort | None = None,
    persona_timezone_port: ITimezonePort | None = None,
    routine_port: IRoutinePort | None = None,
    id_port: ITemporalIdPort | None = None,
    metrics_port: ITemporalMetricsPort | None = None,
    policy_port: ITemporalPolicyPort | None = None,
    config: TemporalConfig | None = None,
) -> TemporalServiceBundle:
    """Build the Tier-1 Temporal bundle with production defaults."""
    from k1.temporal.factory import TemporalFactory

    event = (
        event_port
        if event_port is not None
        else (EventBusAdapter(bus) if bus is not None else None)
    )
    return TemporalFactory.create_production(
        clock_port=clock_port or SystemClockAdapter(),
        event_port=event,
        state_port=state_port or TemporalStateAdapter(allow_memory_fallback=True),
        device_context_port=device_context_port,
        timezone_port=timezone_port,
        spatial_timezone_port=spatial_timezone_port,
        persona_timezone_port=persona_timezone_port,
        routine_port=routine_port or NullRoutineAdapter(),
        id_port=id_port or UuidIdAdapter(),
        metrics_port=metrics_port or NullMetricsAdapter(),
        policy_port=policy_port,
        config=config,
    )


__all__ = ["TemporalServiceBundle", "build_temporal_bundle"]
