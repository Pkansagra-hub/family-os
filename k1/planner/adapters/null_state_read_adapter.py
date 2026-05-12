"""NullStateReadAdapter -- IStateReadPort no-op for shared/boot-tier Planner.

Used at S6 wiring when no specific session is bound to the Planner. Every
``read_sections()`` call returns an empty ``SessionSnapshot`` and emits a
WARNING on first use so the silent-degradation footgun (see issue K2 /
3.2.1) is visible in production logs.

Replaces the prior ``PlannerStateAdapter(reader=..., session_id="__shared__")``
pattern which silently returned ``{}`` because the sentinel never matched
any real session in ``KernelService._sessions``.

Once 3.2.2 lands and ``IStateReadPort.read_sections()`` accepts
``session_id``, this adapter remains the appropriate "no session bound at
boot" placeholder; the real per-session lookup happens via the routing
reader threaded through the planner pipeline.
"""

from __future__ import annotations

import logging
from typing import List

from k1.fabric.ports.state_reader import SessionSnapshot

log = logging.getLogger(__name__)


class NullStateReadAdapter:
    """Empty IStateReadPort. Returns no sections; logs WARNING on first use.

    Satisfies the structural Protocol ``k1.planner.ports.state_read_port.IStateReadPort``.
    """

    __slots__ = ("_warned",)

    def __init__(self) -> None:
        self._warned: bool = False

    async def read_sections(
        self,
        sections: List[str],
        trace_id: str = "",
        session_id: str = "",
    ) -> SessionSnapshot:
        if not self._warned:
            log.warning(
                "Planner state_port is NullStateReadAdapter -- no SessionState "
                "is bound. Planning decisions will silently degrade to defaults. "
                "(K2 / 3.2.1: replace once per-session Planner wiring lands.)"
            )
            self._warned = True
        return SessionSnapshot(session_id=session_id, sections={})


__all__ = ["NullStateReadAdapter"]
