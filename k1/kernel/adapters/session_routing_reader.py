"""
k1.kernel.adapters.session_routing_reader -- SessionRoutingStateReader.

Routes ``ISessionStateReader`` calls to the correct per-session
``SessionStateManager`` based on ``session_id``.

Orchestrator and Planner are shared (Tier 1) but need to read
per-session state. This adapter bridges the gap by looking up the
session from ``KernelService._sessions[session_id].session_state``
at read time.

Satisfies ``ISessionStateReader`` (k1.fabric.ports.state_reader)
via structural subtyping, so it can be injected into
``StateReadAdapter`` (Orchestrator) and ``PlannerStateAdapter``
(Planner) as a drop-in replacement for per-session readers.

Findings addressed: C-6, H-18, M-66, M-67.

Exports:
    SessionRoutingStateReader
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from k1.fabric.ports.state_reader import SessionSnapshot

logger = logging.getLogger(__name__)


class SessionRoutingStateReader:
    """
    Routes state reads to the correct per-session SSM.

    Implements ``ISessionStateReader`` (structural).  On each call,
    resolves ``session_id`` → ``SessionStateManager`` via the
    provided ``session_lookup`` callable, then reads from that
    manager.

    Constructor Args:
        session_lookup:
            ``Callable[[str], Any]`` that maps a ``session_id`` to
            a ``SessionStateManager`` (or ``None`` if the session
            does not exist).  Typically a closure over
            ``KernelService._sessions``.
    """

    __slots__ = ("_session_lookup",)

    def __init__(
        self,
        session_lookup: Callable[[str], Any],
    ) -> None:
        self._session_lookup = session_lookup

    # ==================================================================
    # ISessionStateReader implementation
    # ==================================================================

    def read_section(
        self,
        session_id: str,
        section: str,
    ) -> Optional[Dict[str, Any]]:
        """Read a single section from the session's SSM."""
        manager = self._resolve_manager(session_id)
        if manager is None:
            return None

        try:
            section_obj = manager.get_section(section)
            return self._section_to_dict(section_obj)
        except (KeyError, Exception) as exc:
            logger.debug(
                "Section '%s' not found for session '%s': %s",
                section,
                session_id,
                exc,
            )
            return None

    def read_sections(
        self,
        session_id: str,
        names: List[str],
    ) -> Dict[str, Any]:
        """Read multiple sections in a single call."""
        result: Dict[str, Any] = {}
        for name in names:
            data = self.read_section(session_id, name)
            if data is not None:
                result[name] = data
        return result

    def get_snapshot(
        self,
        session_id: str,
    ) -> SessionSnapshot:
        """Capture a point-in-time snapshot of all sections."""
        manager = self._resolve_manager(session_id)
        if manager is None:
            return SessionSnapshot(session_id=session_id)

        sections: Dict[str, Dict[str, Any]] = {}
        section_names = self._get_section_names(manager)
        for name in section_names:
            try:
                section_obj = manager.get_section(name)
                data = self._section_to_dict(section_obj)
                if data is not None:
                    sections[name] = data
            except (KeyError, Exception):
                continue

        return SessionSnapshot(
            session_id=session_id,
            sections=sections,
            timestamp_ms=int(time.time() * 1000),
        )

    # ==================================================================
    # Internal helpers
    # ==================================================================

    def _resolve_manager(self, session_id: str) -> Any:
        """Look up the SSM for *session_id*, or ``None``."""
        try:
            manager = self._session_lookup(session_id)
        except (KeyError, Exception):
            logger.debug("No session found for id '%s'", session_id)
            return None

        if manager is None:
            logger.debug("Session '%s' has no state manager", session_id)
        return manager

    @staticmethod
    def _section_to_dict(section_obj: Any) -> Optional[Dict[str, Any]]:
        """Convert a section object to a plain dict."""
        if isinstance(section_obj, dict):
            return section_obj
        if hasattr(section_obj, "to_dict"):
            data = section_obj.to_dict()
            return data if isinstance(data, dict) else None
        return None

    @staticmethod
    def _get_section_names(manager: Any) -> List[str]:
        """Get all section names from a manager."""
        if hasattr(manager, "get_all_section_sizes"):
            try:
                return list(manager.get_all_section_sizes().keys())
            except Exception:
                pass
        # Fallback: K1 SessionState known sections
        return [
            "control",
            "beliefs_active",
            "scoreboard",
            "history_active",
            "clarifications",
            "affective_now",
            "narrative_active",
            "meta",
            "beliefs_history",
            "history_recent",
            "persona",
            "telemetry",
        ]

    def __repr__(self) -> str:
        return "SessionRoutingStateReader()"
