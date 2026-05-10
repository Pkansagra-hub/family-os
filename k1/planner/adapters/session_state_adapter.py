"""SessionStateReadAdapter -- production SessionState reader [F31].

Implements ``IStateReadPort`` (SS15.5) by wrapping
``ISessionStateReader`` (Fabric port 5.1.1) with a pre-bound
``session_id``.

Adapter wiring (SS16.1.4, SS16.3):
    IStateReadPort -> SessionStateReadAdapter -> ISessionStateReader

Design:
    - Session ID bound at construction (one adapter per session)
    - Multi-reader, lock-free (ISessionStateReader guarantees safety)
    - No write capability (PLAN-01 enforced at type level)
    - Reads HOT CORE + WARM sections (<100us serialization)

Import graph (Layer 2)
----------------------
k1.planner.adapters.session_state_adapter
  -> k1.planner.ports.state_read_port     (IStateReadPort)
  -> k1.fabric.ports.state_reader         (ISessionStateReader, SessionSnapshot)
  -> typing, logging
"""

from __future__ import annotations

import logging
from typing import Any, List

from k1.fabric.ports.state_reader import ISessionStateReader, SessionSnapshot

logger = logging.getLogger(__name__)


class SessionStateReadAdapter:
    """Production SessionState read adapter (SS16.1.4).

    Wraps ``ISessionStateReader`` with a pre-bound ``session_id`` so
    that callers (ToolCallRouter, SketchService via read_sections) do
    not need to know the active session.

    PLAN-01 enforcement:
        No write methods exist on this adapter or its wrapped interface.
    """

    __slots__ = ("_reader", "_session_id")

    def __init__(
        self,
        reader: ISessionStateReader,
        session_id: str,
    ) -> None:
        self._reader = reader
        self._session_id: str = session_id

    # ------------------------------------------------------------------
    # IStateReadPort implementation
    # ------------------------------------------------------------------

    async def read_sections(
        self,
        sections: List[str],
        trace_id: str = "",
        session_id: str = "",
    ) -> SessionSnapshot:
        """Read specified SessionState sections.

        Delegates to ``ISessionStateReader.read_sections(session_id, names)``.

        ``session_id`` resolution (3.2.2):
            - Caller-provided ``session_id`` (per-request, threaded from
              ``PlanRequest.context.session_id``) wins.
            - Empty caller ``session_id`` falls back to the pre-bound
              ``self._session_id`` for back-compat with legacy fixtures
              that constructed the adapter with a fixed session.

        Error handling:
            - SessionState unavailable -> empty ``SessionSnapshot``
            - Individual section missing -> omitted from result
        """
        effective_sid = session_id or self._session_id
        try:
            raw = self._reader.read_sections(effective_sid, sections)
            # If the reader returns a dict, wrap in SessionSnapshot
            if isinstance(raw, dict):
                return SessionSnapshot(
                    session_id=effective_sid,
                    sections=raw,
                )
            # If the reader already returns SessionSnapshot, return as-is
            if isinstance(raw, SessionSnapshot):
                return raw
            # Fallback: wrap whatever we got
            return SessionSnapshot(
                session_id=effective_sid,
                sections=raw if isinstance(raw, dict) else {},
            )
        except Exception:
            logger.exception(
                "read_sections failed, returning empty snapshot",
                extra={
                    "session_id": effective_sid,
                    "sections": sections,
                    "trace_id": trace_id,
                },
            )
            return SessionSnapshot(session_id=effective_sid)

    async def get_snapshot(
        self,
        trace_id: str = "",
    ) -> SessionSnapshot:
        """Capture a point-in-time snapshot of all available sections.

        Delegates to ``ISessionStateReader.get_snapshot(session_id)``
        with the pre-bound ``session_id``.

        Not part of ``IStateReadPort`` -- convenience method for callers
        that hold the concrete adapter type.

        Error handling:
            - SessionState unavailable -> empty ``SessionSnapshot``
        """
        try:
            raw = self._reader.get_snapshot(self._session_id)
            if isinstance(raw, SessionSnapshot):
                return raw
            # If get_snapshot returns a dict, wrap it
            if isinstance(raw, dict):
                return SessionSnapshot(
                    session_id=self._session_id,
                    sections=raw,
                )
            return SessionSnapshot(session_id=self._session_id)
        except Exception:
            logger.exception(
                "get_snapshot failed, returning empty snapshot",
                extra={
                    "session_id": self._session_id,
                    "trace_id": trace_id,
                },
            )
            return SessionSnapshot(session_id=self._session_id)


__all__ = ["SessionStateReadAdapter"]
