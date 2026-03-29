"""
k1.fabric.adapters.sessionstate_reader -- Production SessionState adapter (5.2.1).

Wraps a real ``SessionStateManager`` and exposes the Fabric's
``ISessionStateReader`` protocol for read-only section access.

Design:
  - Multi-reader, lock-free reads (SessionStateManager guarantees this).
  - Sections returned as dicts via ``section.to_dict()``.
  - ``SectionNotFoundError`` from manager maps to ``None``.
  - Single session_id bound at construction (adapter is per-session).
  - Production wiring: ``SessionStateFactory.create_standalone()`` or
    ``create_with_ports()`` produces a manager; this adapter wraps it.

Thread safety:
  All reads delegate to SessionStateManager which guarantees
  lock-free multi-reader concurrency.  No internal locking needed.

FAB-01 enforcement:
  This adapter exposes ONLY read methods.  There is no write path.

Consumers:
  - PolicyEngine, ContextBuilder, SemanticValidator, AgentFactory
  - Injected via FabricFactory (5.3.1)

References:
  - ISessionStateReader (5.1.1)
  - SessionStateManager (k1/sessionstate/manager.py)
  - FAB-01 (Fabric never writes SessionState)

Exports:
  SessionStateReaderAdapter
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from k1.fabric.ports.state_reader import SessionSnapshot

logger = logging.getLogger(__name__)


class SessionStateReaderAdapter:
    """
    Production adapter that wraps a real SessionStateManager.

    Implements ``ISessionStateReader`` via structural subtyping.
    All reads delegate to the underlying manager, converting section
    objects to plain dicts via ``to_dict()``.

    The adapter is bound to a single ``session_id`` at construction.
    If a caller passes a different session_id, it returns None/empty
    gracefully (the manager only holds one session).

    Attributes:
        _manager: The real SessionStateManager instance.
        _session_id: The session this adapter is bound to.
    """

    __slots__ = ("_manager", "_session_id")

    def __init__(self, manager: Any, session_id: str) -> None:
        """
        Initialize with a real SessionStateManager.

        Args:
            manager: A ``SessionStateManager`` instance (or any object
                with ``get_section(name)`` that returns objects with
                ``to_dict()``).  Typed as ``Any`` to avoid import
                dependency on sessionstate module.
            session_id: The session ID this adapter is bound to.
        """
        self._manager = manager
        self._session_id = session_id

    @property
    def session_id(self) -> str:
        """The session ID this adapter is bound to."""
        return self._session_id

    def read_section(
        self,
        session_id: str,
        section: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Read a single section from the real SessionState.

        Delegates to ``manager.get_section(section)`` and converts
        the result via ``to_dict()``.  If the section doesn't exist
        or the session_id doesn't match, returns None.

        Args:
            session_id: Must match the bound session_id.
            section: Section name (e.g. "affective_now").

        Returns:
            Section data as dict, or None if unavailable.
        """
        if session_id != self._session_id:
            logger.debug(
                "Session mismatch: requested=%s, bound=%s",
                session_id,
                self._session_id,
            )
            return None

        try:
            # Support dotted section paths used by some orchestrator reads,
            # e.g. "control.safety_band".
            base_section, nested_path = self._split_section_path(section)

            section_obj = self._manager.get_section(base_section)
            if section_obj is None:
                return None

            section_dict = self._section_obj_to_dict(section_obj)
            if section_dict is None:
                logger.warning(
                    "Section '%s' has no dict-compatible API; returning None",
                    base_section,
                )
                return None

            if not nested_path:
                return section_dict

            nested_value = self._resolve_nested_path(section_dict, nested_path)
            if nested_value is None:
                return None

            # Compatibility normalization for DAGExecutor safety-band reads:
            # _check_safety_band currently expects {'level': 'RED|BLACK|...'}
            # when querying section='control.safety_band'.
            if base_section == "control" and nested_path == ["safety_band"]:
                return {
                    "level": nested_value,
                    "safety_band": nested_value,
                }

            # Preserve existing adapter contract: read_section returns dict|None.
            # Wrap scalar nested values so callers can consistently .get(...).
            if isinstance(nested_value, dict):
                return nested_value
            leaf_key = nested_path[-1]
            return {leaf_key: nested_value}
        except (KeyError, Exception) as exc:
            # SectionNotFoundError is a KeyError subclass
            logger.debug("Section '%s' not found: %s", section, exc)
            return None

    def read_sections(
        self,
        session_id: str,
        names: List[str],
    ) -> Dict[str, Any]:
        """
        Read multiple sections in a single call.

        Args:
            session_id: Must match the bound session_id.
            names: List of section names to read.

        Returns:
            Dict of section_name -> section_data.  Missing sections
            are omitted (not None-valued).
        """
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
        """
        Capture a point-in-time snapshot of all sections.

        Reads all available sections from the manager and packages
        them into a Fabric ``SessionSnapshot``.

        Args:
            session_id: Must match the bound session_id.

        Returns:
            SessionSnapshot with all available sections as dicts.
        """
        if session_id != self._session_id:
            return SessionSnapshot(session_id=session_id)

        sections: Dict[str, Dict[str, Any]] = {}

        # Try all known section names from the manager
        # We iterate defensively -- if the manager doesn't have the section, skip
        known_sections = self._get_all_section_names()
        for name in known_sections:
            data = self.read_section(session_id, name)
            if data is not None:
                sections[name] = data

        return SessionSnapshot(
            session_id=session_id,
            sections=sections,
            timestamp_ms=int(time.time() * 1000),
        )

    def _get_all_section_names(self) -> List[str]:
        """
        Get all known section names from the manager.

        Tries manager-level constants, falls back to a static list.
        """
        # Try accessing the manager's ALL_SECTIONS or similar
        if hasattr(self._manager, "get_all_section_sizes"):
            try:
                sizes = self._manager.get_all_section_sizes()
                return list(sizes.keys())
            except Exception:
                pass

        # Fallback: K1 SessionState section names
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

    @staticmethod
    def _split_section_path(section: str) -> tuple[str, List[str]]:
        """Split dotted section path into base section + nested path.

        Example:
            "control.safety_band" -> ("control", ["safety_band"])
        """
        if "." not in section:
            return section, []
        parts = [p for p in section.split(".") if p]
        if not parts:
            return section, []
        return parts[0], parts[1:]

    @staticmethod
    def _section_obj_to_dict(section_obj: Any) -> Optional[Dict[str, Any]]:
        """Normalize a section object to a dictionary when possible."""
        if isinstance(section_obj, dict):
            return section_obj
        if hasattr(section_obj, "to_dict"):
            data = section_obj.to_dict()
            return data if isinstance(data, dict) else None
        if hasattr(section_obj, "get"):
            data = section_obj.get()
            return data if isinstance(data, dict) else None
        return None

    @staticmethod
    def _resolve_nested_path(data: Dict[str, Any], path: List[str]) -> Any:
        """Resolve a nested dotted path against a dictionary."""
        current: Any = data
        for segment in path:
            if not isinstance(current, dict) or segment not in current:
                return None
            current = current[segment]
        return current

    def __repr__(self) -> str:
        return (
            f"SessionStateReaderAdapter(session_id={self._session_id!r}, "
            f"manager={type(self._manager).__name__})"
        )
