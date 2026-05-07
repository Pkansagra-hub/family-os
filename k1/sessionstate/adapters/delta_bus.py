"""DeltaBusAdapter -- K1 Bus event dispatch for SessionState [E-0.5.11 stub].

Replaces ``LocalEventAdapter`` when SessionState events should be routed
onto the K1 Bus (``mutation.approved``, ``eviction.triggered``, etc.).

Blocked by: Bus→SessionState wiring (MS-2+).
Current stand-in: ``LocalEventAdapter`` (in-process callbacks).
"""

from __future__ import annotations

from typing import Any, Callable

from ..ports.events import IEventPort

_BLOCKED = "DeltaBusAdapter blocked by Bus wiring — target: MS-2+"


class DeltaBusAdapter(IEventPort):
    """Stub IEventPort for K1 DeltaBus event dispatch.

    All methods raise ``NotImplementedError`` until the Bus→SS
    integration path is wired.
    """

    __slots__ = ()

    @property
    def is_connected(self) -> bool:  # noqa: D102
        return False

    def emit(self, event_type: str, payload: Any) -> None:  # noqa: D102
        raise NotImplementedError(_BLOCKED)

    def subscribe(
        self,
        event_type: str,
        handler: Callable[[Any], None],
    ) -> str:  # noqa: D102
        raise NotImplementedError(_BLOCKED)

    def unsubscribe(self, subscription_id: str) -> bool:  # noqa: D102
        raise NotImplementedError(_BLOCKED)
