"""IStateReadPort -- Planner SessionState read-only protocol [F15].

The SessionState read port provides multi-reader, lock-free access to
SessionState sections.  This is the Planner's primary context window
during planning.

Design decisions (SS15.5)
-------------------------
- Read-only by design: NO write/update/set/delete methods exist.
  PLAN-01 is enforced at the interface level.
- ``session_id`` is threaded per call (3.2.2). The Planner is a singleton
  that serves multiple sessions; binding session_id at construction
  caused every plan to read from one fixed (or sentinel) session. Callers
  pass the requesting session's id via ``PlanRequest.context.session_id``
  (already extracted by Orchestrator at dispatch_high()).
  Implementations MAY accept an empty ``session_id`` and fall back to
  a pre-bound default (back-compat for legacy fixtures).
- Returns ``SessionSnapshot`` (atomic capture of requested sections).

Canonical read set (SKETCH stage)
---------------------------------
``["beliefs_active", "control", "history_recent"]``

Callers
-------
- ToolCallRouter only (routes ``query_planning_context`` -> ``read_sections``)
- NOT called directly by any stage service

Adapter: SessionStateReadAdapter [F31] wraps ISessionStateReader
         (lock-free multi-reader, <10ms)

Import graph (Layer 1)
----------------------
k1.planner.ports.state_read_port
  -> k1.fabric.ports.state_reader  (SessionSnapshot)
  -> typing
"""

from __future__ import annotations

from typing import List, Protocol, runtime_checkable

from k1.fabric.ports.state_reader import SessionSnapshot


@runtime_checkable
class IStateReadPort(Protocol):
    """Read-only SessionState access port.

    This is a structural protocol (``typing.Protocol``).  Any object with
    a matching ``read_sections()`` signature satisfies it.

    PLAN-01 enforcement
    -------------------
    This port declares ``read_sections()`` ONLY.  There is no write method.
    Enforced at the interface level: the Protocol simply does not declare
    any write/mutate methods.  This is the architectural guarantee that the
    Planner never writes SessionState.

    Thread safety
    -------------
    Implementations MUST support concurrent reads from multiple
    threads/tasks without external synchronisation.
    """

    async def read_sections(
        self,
        sections: List[str],
        trace_id: str = "",
        session_id: str = "",
    ) -> SessionSnapshot:
        """Read specified SessionState sections.

        The adapter maps sections to the requested session and returns an
        atomic snapshot of the requested data.

        Args:
            sections: List of section names to read (e.g.
                ``["beliefs_active", "control", "history_recent"]``).
            trace_id: Distributed trace ID for observability (FAB-09).
            session_id: The session whose state to read (3.2.2). When
                empty, the adapter MAY fall back to a pre-bound default;
                production callers should always pass the requesting
                session id from ``PlanRequest.context.session_id``.

        Returns:
            ``SessionSnapshot`` containing the requested sections.
            Missing sections are omitted from the snapshot (not None-valued).
        """
        ...  # pragma: no cover


__all__ = ["IStateReadPort"]
