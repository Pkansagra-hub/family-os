"""Factory for k1.temporal service wiring."""

from __future__ import annotations

from itertools import combinations
from typing import Any

from k1.temporal.adapters import (
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


class MissingTemporalPortError(ValueError):
    """Raised when a required temporal port is absent."""


class InvalidTemporalPortError(TypeError):
    """Raised when an injected port does not satisfy its Protocol."""


class DuplicateTemporalPortError(ValueError):
    """Raised when two temporal port roles share one object identity."""


class TemporalFactory:
    """Composition root for :class:`TemporalService` and its bundle."""

    def __init__(self) -> None:
        raise TypeError("TemporalFactory uses static factory methods; do not instantiate it")

    @staticmethod
    def create_standalone(config: TemporalConfig | None = None):
        """Create a standalone temporal bundle with in-memory state."""
        return TemporalFactory.create_with_ports(
            clock_port=SystemClockAdapter(),
            event_port=None,
            state_port=TemporalStateAdapter(allow_memory_fallback=True),
            device_context_port=None,
            timezone_port=None,
            routine_port=NullRoutineAdapter(),
            id_port=UuidIdAdapter(),
            metrics_port=NullMetricsAdapter(),
            policy_port=None,
            config=config,
        )

    @staticmethod
    def create_for_testing(config: TemporalConfig | None = None, **overrides: Any):
        """Create a test bundle plus the concrete adapter dictionary."""
        adapters: dict[str, Any] = {
            "clock_port": SystemClockAdapter(),
            "event_port": None,
            "state_port": TemporalStateAdapter(allow_memory_fallback=True),
            "device_context_port": None,
            "timezone_port": None,
            "routine_port": NullRoutineAdapter(),
            "id_port": UuidIdAdapter(),
            "metrics_port": NullMetricsAdapter(),
            "policy_port": None,
        }
        adapters.update(overrides)
        bundle = TemporalFactory.create_with_ports(config=config, **adapters)
        return bundle, adapters

    @staticmethod
    def create_production(
        *,
        clock_port: IClockPort,
        event_port: ITemporalEventPort | None,
        state_port: ITemporalStatePort,
        device_context_port: ITemporalDeviceContextPort | None = None,
        timezone_port: ITimezonePort | None = None,
        routine_port: IRoutinePort | None = None,
        id_port: ITemporalIdPort,
        metrics_port: ITemporalMetricsPort | None = None,
        policy_port: ITemporalPolicyPort | None = None,
        config: TemporalConfig | None = None,
        spatial_timezone_port: ITimezonePort | None = None,
        persona_timezone_port: ITimezonePort | None = None,
    ):
        """Create the production temporal bundle from explicit ports."""
        return TemporalFactory.create_with_ports(
            clock_port=clock_port,
            event_port=event_port,
            state_port=state_port,
            device_context_port=device_context_port,
            timezone_port=timezone_port,
            routine_port=routine_port,
            id_port=id_port,
            metrics_port=metrics_port,
            policy_port=policy_port,
            config=config,
            spatial_timezone_port=spatial_timezone_port,
            persona_timezone_port=persona_timezone_port,
        )

    @staticmethod
    def create_with_ports(
        *,
        clock_port: IClockPort,
        event_port: ITemporalEventPort | None,
        state_port: ITemporalStatePort,
        device_context_port: ITemporalDeviceContextPort | None = None,
        timezone_port: ITimezonePort | None = None,
        routine_port: IRoutinePort | None = None,
        id_port: ITemporalIdPort,
        metrics_port: ITemporalMetricsPort | None = None,
        policy_port: ITemporalPolicyPort | None = None,
        config: TemporalConfig | None = None,
        spatial_timezone_port: ITimezonePort | None = None,
        persona_timezone_port: ITimezonePort | None = None,
    ):
        """Create a temporal bundle from explicit port implementations."""
        cfg = config or TemporalConfig()
        effective_persona_timezone = persona_timezone_port or timezone_port
        effective_routine = routine_port or NullRoutineAdapter()
        effective_metrics = metrics_port or NullMetricsAdapter()

        ports: dict[str, tuple[Any, Any, bool]] = {
            "clock_port": (clock_port, IClockPort, True),
            "state_port": (state_port, ITemporalStatePort, True),
            "id_port": (id_port, ITemporalIdPort, True),
            "event_port": (event_port, ITemporalEventPort, False),
            "device_context_port": (device_context_port, ITemporalDeviceContextPort, False),
            "spatial_timezone_port": (spatial_timezone_port, ITimezonePort, False),
            "persona_timezone_port": (effective_persona_timezone, ITimezonePort, False),
            "routine_port": (effective_routine, IRoutinePort, False),
            "metrics_port": (effective_metrics, ITemporalMetricsPort, False),
            "policy_port": (policy_port, ITemporalPolicyPort, False),
        }
        TemporalFactory._validate_ports(ports)

        service = TemporalService(
            clock=clock_port,
            id_port=id_port,
            state_port=state_port,
            event_port=event_port,
            device_context_port=device_context_port,
            spatial_timezone_port=spatial_timezone_port,
            persona_timezone_port=effective_persona_timezone,
            routine_port=effective_routine,
            metrics_port=effective_metrics,
            config=cfg,
        )

        from k1.temporal.kernel.bootstrap import TemporalServiceBundle
        from k1.temporal.service import projection_renderer

        return TemporalServiceBundle(
            service=service,
            renderer=projection_renderer,
            config=cfg,
            clock_port=clock_port,
            id_port=id_port,
            event_port=event_port,
            device_context_port=device_context_port,
            spatial_timezone_port=spatial_timezone_port,
            persona_timezone_port=effective_persona_timezone,
            routine_port=effective_routine,
            metrics_port=effective_metrics,
            policy_port=policy_port,
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
                raise MissingTemporalPortError("; ".join(failures))
            if any(item.startswith("duplicate") for item in failures):
                raise DuplicateTemporalPortError("; ".join(failures))
            raise InvalidTemporalPortError("; ".join(failures))


__all__ = [
    "DuplicateTemporalPortError",
    "InvalidTemporalPortError",
    "MissingTemporalPortError",
    "TemporalFactory",
]
