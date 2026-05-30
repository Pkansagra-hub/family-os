"""Factory for k1.grounding service wiring."""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import combinations
from typing import Any

from k1.grounding.adapters import (
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
from k1.grounding.service import GroundingService
from k1.temporal.types import TemporalAnchor, TemporalProjection, TemporalTurnSnapshot


class MissingGroundingPortError(ValueError):
    """Raised when a required grounding port is absent."""


class InvalidGroundingPortError(TypeError):
    """Raised when an injected port does not satisfy its Protocol."""


class DuplicateGroundingPortError(ValueError):
    """Raised when two grounding port roles share one object identity."""


class GroundingFactory:
    """Composition root for GroundingService and its bundle."""

    def __init__(self) -> None:
        raise TypeError("GroundingFactory uses static factory methods; do not instantiate it")

    @staticmethod
    def create_standalone(config: GroundingConfig | None = None):
        """Create a standalone grounding bundle with in-memory state."""
        return GroundingFactory.create_with_ports(
            temporal_port=_StandaloneTemporalPort(),
            spatial_port=SpatialHandleAdapter(),
            id_port=UuidIdAdapter(),
            state_port=GroundingStateAdapter(allow_memory_fallback=True),
            identity_port=StaticIdentityAdapter(),
            policy_port=SelfModelPolicyAdapter(),
            event_port=None,
            metrics_port=NullMetricsAdapter(),
            config=config,
        )

    @staticmethod
    def create_for_testing(config: GroundingConfig | None = None, **overrides: Any):
        """Create a test bundle plus the concrete adapter dictionary."""
        adapters: dict[str, Any] = {
            "temporal_port": _StandaloneTemporalPort(),
            "spatial_port": SpatialHandleAdapter(),
            "id_port": UuidIdAdapter(),
            "state_port": GroundingStateAdapter(allow_memory_fallback=True),
            "identity_port": StaticIdentityAdapter(),
            "policy_port": SelfModelPolicyAdapter(),
            "event_port": None,
            "metrics_port": NullMetricsAdapter(),
        }
        adapters.update(overrides)
        bundle = GroundingFactory.create_with_ports(config=config, **adapters)
        return bundle, adapters

    @staticmethod
    def create_production(
        *,
        temporal_port: IGroundingTemporalPort,
        spatial_port: IGroundingSpatialPort,
        id_port: IGroundingIdPort,
        state_port: IGroundingStatePort,
        identity_port: IGroundingIdentityPort | None = None,
        policy_port: IGroundingPolicyPort | None = None,
        event_port: IGroundingEventPort | None = None,
        metrics_port: IGroundingMetricsPort | None = None,
        config: GroundingConfig | None = None,
    ):
        """Create the production grounding bundle from explicit ports."""
        return GroundingFactory.create_with_ports(
            temporal_port=temporal_port,
            spatial_port=spatial_port,
            id_port=id_port,
            state_port=state_port,
            identity_port=identity_port,
            policy_port=policy_port,
            event_port=event_port,
            metrics_port=metrics_port,
            config=config,
        )

    @staticmethod
    def create_with_ports(
        *,
        temporal_port: IGroundingTemporalPort,
        spatial_port: IGroundingSpatialPort,
        id_port: IGroundingIdPort,
        state_port: IGroundingStatePort,
        identity_port: IGroundingIdentityPort | None = None,
        policy_port: IGroundingPolicyPort | None = None,
        event_port: IGroundingEventPort | None = None,
        metrics_port: IGroundingMetricsPort | None = None,
        config: GroundingConfig | None = None,
    ):
        """Create a grounding bundle from explicit port implementations."""
        cfg = config or GroundingConfig()
        effective_metrics = metrics_port or NullMetricsAdapter()
        effective_policy = policy_port or SelfModelPolicyAdapter()

        ports: dict[str, tuple[Any, Any, bool]] = {
            "temporal_port": (temporal_port, IGroundingTemporalPort, True),
            "spatial_port": (spatial_port, IGroundingSpatialPort, True),
            "id_port": (id_port, IGroundingIdPort, True),
            "state_port": (state_port, IGroundingStatePort, True),
            "identity_port": (identity_port, IGroundingIdentityPort, False),
            "policy_port": (effective_policy, IGroundingPolicyPort, False),
            "event_port": (event_port, IGroundingEventPort, False),
            "metrics_port": (effective_metrics, IGroundingMetricsPort, False),
        }
        GroundingFactory._validate_ports(ports)

        service = GroundingService(
            temporal_port=temporal_port,
            spatial_port=spatial_port,
            id_port=id_port,
            state_port=state_port,
            identity_port=identity_port,
            policy_port=effective_policy,
            event_port=event_port,
            metrics_port=effective_metrics,
            config=cfg,
        )

        from k1.grounding.kernel.bootstrap import GroundingServiceBundle
        from k1.grounding.service import prompt_block_renderer

        return GroundingServiceBundle(
            service=service,
            renderer=prompt_block_renderer,
            config=cfg,
            temporal_port=temporal_port,
            spatial_port=spatial_port,
            id_port=id_port,
            state_port=state_port,
            identity_port=identity_port,
            policy_port=effective_policy,
            event_port=event_port,
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
                raise MissingGroundingPortError("; ".join(failures))
            if any(item.startswith("duplicate") for item in failures):
                raise DuplicateGroundingPortError("; ".join(failures))
            raise InvalidGroundingPortError("; ".join(failures))


class _StandaloneTemporalPort(IGroundingTemporalPort):
    """Small UTC temporal provider used only for standalone/test wiring."""

    async def build_projection(self, session_id: str, consumer: str) -> TemporalProjection:
        anchor = _build_utc_anchor(session_id)
        return TemporalProjection(
            anchor=anchor,
            windows={},
            resolved_expressions=(),
            consumer=consumer,
            freshness="live",
            precision="exact",
        )

    async def refresh_turn(self, session_id: str, **kwargs: Any) -> TemporalTurnSnapshot:
        anchor = _build_utc_anchor(session_id)
        return TemporalTurnSnapshot(
            session_id=session_id,
            turn_id=kwargs.get("turn_id"),
            anchor=anchor,
            windows={},
            resolved_expressions=(),
            refreshed_at_utc=anchor.now_utc,
            source="k1.grounding.standalone_temporal",
        )


def _build_utc_anchor(session_id: str) -> TemporalAnchor:
    now = datetime.now(UTC)
    return TemporalAnchor(
        anchor_id=f"temporal-standalone-{session_id}",
        captured_at_utc=now.isoformat(),
        now_utc=now.isoformat(),
        now_local=now.isoformat(),
        timezone="UTC",
        timezone_source="utc",
        local_date=now.date().isoformat(),
        local_time=now.time().replace(microsecond=0).isoformat(),
        day_of_week=now.strftime("%A"),
        hour_24=now.hour,
        time_of_day="midday",
        is_weekend=now.weekday() >= 5,
        locale=None,
        week_start_day="monday",
        freshness_ms=0,
        source="k1.grounding.standalone_temporal",
        confidence=1.0,
    )


__all__ = [
    "DuplicateGroundingPortError",
    "GroundingFactory",
    "InvalidGroundingPortError",
    "MissingGroundingPortError",
]
