"""Work-conserving scheduler enforcing coarse port budgets."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from types import TracebackType
from typing import Callable, Optional, Type, cast


@dataclass(slots=True)
class SchedulerProfile:
    name: str
    description: str
    port_limits: dict[str, int] = field(
        default_factory=lambda: cast(dict[str, int], {})
    )
    default_port_limit: int = 16


@dataclass(slots=True)
class SchedulerToken:
    """Token returned by the scheduler representing reserved capacity."""

    _release_cb: Callable[[str, int], None]
    port: str
    cost: int
    _released: bool = field(init=False, default=False)

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._release_cb(self.port, self.cost)

    def __enter__(self) -> "SchedulerToken":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:  # pragma: no cover - context sugar
        self.release()


class SchedulerCapacityError(RuntimeError):
    """Raised when a scheduler port exceeds its configured capacity."""

    def __init__(self, *, band: str, port: str, cost: int, limit: int) -> None:
        self.band = band
        self.port = port
        self.cost = cost
        self.limit = limit
        super().__init__(
            f"Scheduler capacity exceeded for port '{port}': "
            f"requested {cost}, available {max(limit, 0)}"
        )


class Scheduler:
    """Distributes work tokens across kernel ports and bands."""

    def __init__(
        self,
        profile: SchedulerProfile | None = None,
        chaos_config=None,
        metrics_exporter=None,
    ) -> None:
        """Initialize scheduler with optional chaos starvation.

        Args:
            profile: Scheduler profile with port limits
            chaos_config: Optional ChaosSettings for capacity reduction
            metrics_exporter: Optional MetricsExporter for telemetry
        """
        base_profile = profile or SchedulerProfile(
            name="balanced",
            description="Default placeholder profile",
            port_limits={"command": 16, "query": 24, "sse": 32},
            default_port_limit=16,
        )

        # Apply chaos starvation if enabled
        if chaos_config is not None and chaos_config.enabled:
            from k0.chaos.toggles import apply_scheduler_starvation

            self.profile = apply_scheduler_starvation(
                base_profile, chaos_config, metrics_exporter
            )
        else:
            self.profile = base_profile

        self._lock = Lock()
        self._active: dict[str, int] = {}

    def acquire(self, *, band: str, port: str, cost: int) -> SchedulerToken:
        if cost <= 0:
            raise ValueError("scheduler cost must be positive")

        limit = self.profile.port_limits.get(port, self.profile.default_port_limit)
        with self._lock:
            current = self._active.get(port, 0)
            if current + cost > limit:
                raise SchedulerCapacityError(
                    band=band,
                    port=port,
                    cost=cost,
                    limit=limit - current,
                )
            self._active[port] = current + cost

        return SchedulerToken(self._release, port, cost)

    def tighten(self, profile: SchedulerProfile) -> None:
        with self._lock:
            self.profile = profile
            self._active = {
                port: min(
                    count, profile.port_limits.get(port, profile.default_port_limit)
                )
                for port, count in self._active.items()
            }

    def _release(self, port: str, cost: int) -> None:
        with self._lock:
            current = self._active.get(port, 0)
            new_value = max(current - cost, 0)
            if new_value == 0:
                self._active.pop(port, None)
            else:
                self._active[port] = new_value

    def active_tokens(self, port: str) -> int:
        with self._lock:
            return self._active.get(port, 0)
