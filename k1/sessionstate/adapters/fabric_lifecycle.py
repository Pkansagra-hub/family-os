"""FabricLifecycleAdapter -- Fabric-managed SS lifecycle [E-0.5.11 stub].

Replaces ``StandaloneLifecycle`` when Fabric coordinates SessionState
start/stop/checkpoint across multiple per-session instances.

Blocked by: Fabric lifecycle coordination (MS-2+).
Current stand-in: ``StandaloneLifecycle`` (self-managed).
"""

from __future__ import annotations

from ..ports.lifecycle import (
    CheckpointResult,
    CheckpointTrigger,
    HealthStatus,
    ILifecyclePort,
    LifecycleConfig,
    LifecycleState,
    StartResult,
    StopResult,
)

_BLOCKED = "FabricLifecycleAdapter blocked by Fabric wiring — target: MS-2+"


class FabricLifecycleAdapter(ILifecyclePort):
    """Stub ILifecyclePort for Fabric-managed lifecycle.

    All methods raise ``NotImplementedError`` until Fabric lifecycle
    coordination is wired.
    """

    __slots__ = ()

    @property
    def state(self) -> LifecycleState:  # noqa: D102
        return LifecycleState.CREATED

    @property
    def session_id(self) -> str:  # noqa: D102
        return ""

    @property
    def config(self) -> LifecycleConfig:  # noqa: D102
        return LifecycleConfig.default()

    @property
    def started_at_ms(self) -> int:  # noqa: D102
        return 0

    @property
    def checkpoint_count(self) -> int:  # noqa: D102
        return 0

    @property
    def last_checkpoint_ms(self) -> int:  # noqa: D102
        return 0

    def start(self, restore_if_exists: bool = True) -> StartResult:  # noqa: D102
        raise NotImplementedError(_BLOCKED)

    def stop(self, checkpoint_before_stop: bool = True) -> StopResult:  # noqa: D102
        raise NotImplementedError(_BLOCKED)

    def health(self) -> HealthStatus:  # noqa: D102
        raise NotImplementedError(_BLOCKED)

    def checkpoint(
        self,
        trigger: CheckpointTrigger = CheckpointTrigger.MANUAL,
    ) -> CheckpointResult:  # noqa: D102
        raise NotImplementedError(_BLOCKED)
