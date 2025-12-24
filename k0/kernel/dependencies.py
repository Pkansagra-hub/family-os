"""Dependency wiring used by FastAPI routes.

This module centralises runtime dependencies so FastAPI routes can rely on
well-defined factories for database sessions, policy context, and
telemetry span generation. The factories are small, production-ready
adapters that can also be swapped in tests for instrumentation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncIterator, Callable, Coroutine, Dict

from ..obs.tracing import TracerFactory
from ..qos import QoSContext, Scheduler, SchedulerProfile
from .config import KernelSettings

if TYPE_CHECKING:
    import asyncpg

DEPENDENCY_NOT_CONFIGURED_MSG = (
    "Kernel dependency overrides have not been configured. Ensure "
    "`build_request_dependencies` is applied to the FastAPI application."
)


async def database_session() -> AsyncIterator["asyncpg.Connection"]:
    """Return an asyncpg connection bound to the kernel datastore."""
    raise RuntimeError(DEPENDENCY_NOT_CONFIGURED_MSG)
    yield  # type: ignore[misc]  # pragma: no cover - makes this an async generator


@dataclass(slots=True)
class PolicyContext:
    """Surface area made available to the policy subsystem."""

    environment: str
    scheduler_profile: str
    settings_path: Path | None


def policy_context_dependency() -> PolicyContext:
    """Return a policy context describing the active environment."""

    raise RuntimeError(DEPENDENCY_NOT_CONFIGURED_MSG)


def telemetry_span_factory() -> TracerFactory:
    """Return the tracer factory used to create span identifiers."""

    raise RuntimeError(DEPENDENCY_NOT_CONFIGURED_MSG)


def scheduler_dependency() -> Scheduler:
    """Return the shared QoS scheduler instance."""

    raise RuntimeError(DEPENDENCY_NOT_CONFIGURED_MSG)


def qos_context_dependency() -> QoSContext:
    """Return the per-request QoS context."""

    raise RuntimeError(DEPENDENCY_NOT_CONFIGURED_MSG)


ConnectionFactory = Callable[[], Coroutine[Any, Any, "asyncpg.Connection"]]
SchedulerFactory = Callable[[KernelSettings], Scheduler]


@dataclass(slots=True)
class RequestDependencyProvider:
    """Aggregates per-request dependencies for FastAPI overrides."""

    settings: KernelSettings
    connection_factory: ConnectionFactory | None = None
    tracer_factory: TracerFactory | None = None
    scheduler_factory: SchedulerFactory | None = None
    _policy_template: PolicyContext | None = field(init=False, default=None)
    _scheduler: Scheduler | None = field(init=False, default=None)
    _fanout_budget: int = field(init=False, default=0)
    _top_k_budget: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        if self.connection_factory is None:
            self.connection_factory = self._default_connection_factory
        if self.tracer_factory is None:
            telemetry_settings = getattr(self.settings, "telemetry", None)
            otlp_endpoint = (
                getattr(telemetry_settings, "otlp_endpoint", None) if telemetry_settings else None
            )
            otlp_headers_raw = (
                getattr(telemetry_settings, "otlp_headers", {}) if telemetry_settings else {}
            )
            otlp_headers = {str(key): str(value) for key, value in dict(otlp_headers_raw).items()}
            sample_ratio = (
                float(getattr(telemetry_settings, "trace_sample_ratio", 1.0))
                if telemetry_settings
                else 1.0
            )
            self.tracer_factory = TracerFactory(
                service_name="k0-kernel",
                service_version=self.settings.version,
                environment=self.settings.environment,
                otlp_endpoint=otlp_endpoint,
                otlp_headers=otlp_headers,
                sample_ratio=sample_ratio,
            )
        if self.scheduler_factory is None:
            self.scheduler_factory = self._default_scheduler_factory
        qos_settings = getattr(self.settings, "qos")
        self._scheduler = self.scheduler_factory(self.settings)
        self._fanout_budget = int(getattr(qos_settings, "fanout_max"))
        self._top_k_budget = int(getattr(qos_settings, "top_k_max"))
        self._policy_template = PolicyContext(
            environment=self.settings.environment,
            scheduler_profile=str(getattr(qos_settings, "scheduler_profile")),
            settings_path=self.settings.config_file,
        )

    async def _default_connection_factory(self) -> "asyncpg.Connection":
        """Create a new asyncpg connection using the global pool."""
        from ..db.pool import get_pool

        pool = get_pool()
        return await pool._pool.acquire()

    async def _database_session(self) -> AsyncIterator["asyncpg.Connection"]:
        """Async generator that yields a pooled connection."""
        from ..db.connection import connection_scope

        async with connection_scope() as conn:
            yield conn

    def _policy_context(self) -> PolicyContext:
        assert self._policy_template is not None  # nosec - post-init guarantee
        return PolicyContext(
            environment=self._policy_template.environment,
            scheduler_profile=self._policy_template.scheduler_profile,
            settings_path=self._policy_template.settings_path,
        )

    def _tracer_factory(self) -> TracerFactory:
        assert self.tracer_factory is not None  # nosec - post-init guarantee
        return self.tracer_factory

    def _scheduler_dependency(self) -> Scheduler:
        assert self._scheduler is not None  # nosec - post-init guarantee
        return self._scheduler

    def _qos_context(self) -> QoSContext:
        assert self._scheduler is not None  # nosec - post-init guarantee
        return QoSContext(
            scheduler=self._scheduler,
            fanout_budget=self._fanout_budget,
            top_k_budget=self._top_k_budget,
        )

    def as_fastapi_overrides(
        self,
    ) -> Dict[Callable[..., object], Callable[..., object]]:
        """Return the overrides dict expected by `FastAPI.dependency_overrides`."""

        return {
            database_session: self._database_session,
            policy_context_dependency: self._policy_context,
            telemetry_span_factory: self._tracer_factory,
            scheduler_dependency: self._scheduler_dependency,
            qos_context_dependency: self._qos_context,
        }

    @property
    def scheduler(self) -> Scheduler:
        """Expose the shared scheduler instance."""

        assert self._scheduler is not None  # nosec - post-init guarantee
        return self._scheduler

    @property
    def tracer(self) -> TracerFactory:
        """Expose the configured tracer factory."""

        assert self.tracer_factory is not None  # nosec - post-init guarantee
        return self.tracer_factory

    def _default_scheduler_factory(self, settings: KernelSettings) -> Scheduler:
        qos_settings = getattr(settings, "qos")
        fanout_max = int(getattr(qos_settings, "fanout_max"))
        top_k_max = int(getattr(qos_settings, "top_k_max"))
        profile = SchedulerProfile(
            name=str(getattr(qos_settings, "scheduler_profile")),
            description=f"Configured profile {getattr(qos_settings, 'scheduler_profile')}",
            port_limits={
                "command": max(4, fanout_max * 4),
                "query": max(8, top_k_max * 2),
                "sse": 32,
            },
            default_port_limit=max(8, fanout_max * 4),
        )
        return Scheduler(profile=profile)


def build_request_dependencies(
    settings: KernelSettings,
    *,
    connection_factory: ConnectionFactory | None = None,
    tracer_factory: TracerFactory | None = None,
    scheduler_factory: SchedulerFactory | None = None,
) -> RequestDependencyProvider:
    """Factory used by the application bootstrap."""

    return RequestDependencyProvider(
        settings=settings,
        connection_factory=connection_factory,
        tracer_factory=tracer_factory,
        scheduler_factory=scheduler_factory,
    )


__all__ = [
    "ConnectionFactory",
    "SchedulerFactory",
    "PolicyContext",
    "RequestDependencyProvider",
    "build_request_dependencies",
    "database_session",
    "policy_context_dependency",
    "qos_context_dependency",
    "scheduler_dependency",
    "telemetry_span_factory",
]
