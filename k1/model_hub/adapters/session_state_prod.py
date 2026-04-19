"""SessionStateProdAdapter -- production IStateReadPort binding [E-0.5.10].

Wraps ``SessionStateManager`` for real ``persona`` + ``control`` reads.
Replaces the stub ``SessionStateReadAdapter`` which uses in-memory dicts.

Design
------
* Implements ``IStateReadPort.read(sections) -> StateSnapshot``.
* Calls ``manager.get_section(name)`` → ``.to_dict()`` / ``.get_metadata()``.
* ``SectionNotFoundError`` (KeyError subclass) → section omitted silently.
* Any other exception → returns empty ``StateSnapshot`` (degraded mode).
* MH-01 enforced: NO write methods.
* Lock-free: ``SessionStateManager`` guarantees multi-reader concurrency.

Import graph (Layer 3 -- adapter)
---------------------------------
k1.model_hub.adapters.session_state_prod
  -> k1.model_hub.ports.state_read_port  (Layer 1)
  -> stdlib only
  (manager injected as Any to avoid import coupling)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from k1.model_hub.ports.state_read_port import StateSnapshot

logger = logging.getLogger(__name__)


@runtime_checkable
class _ISessionStateManager(Protocol):
    """Minimal local Protocol for SessionStateManager dependency.

    Avoids cross-module import coupling (MH-01) while still giving
    type-checkers an explicit contract for the only method this
    adapter calls.
    """

    def get_section(self, name: str) -> Any: ...


class SessionStateProdAdapter:
    """Production IStateReadPort — wraps SessionStateManager.

    Reads ``persona`` and ``control`` sections (plus any other requested)
    from a real SessionState instance.

    MH-01: This adapter has NO write methods.
    Error handling: return empty snapshot on failure, never crash hub.

    Args:
        manager: A ``SessionStateManager`` instance.  Typed via the
                 minimal local ``_ISessionStateManager`` Protocol to
                 avoid import coupling with the sessionstate module
                 (same pattern as MW's ``SessionReadAdapter``).
    """

    __slots__ = ("_manager",)

    def __init__(self, manager: _ISessionStateManager) -> None:
        self._manager = manager

    async def read(self, sections: List[str]) -> StateSnapshot:
        """Read requested sections from SessionState.

        Each section is fetched via ``manager.get_section(name)``
        and converted to a dict via ``to_dict()``.

        Returns:
            StateSnapshot with available sections.
            Missing or unknown sections are silently omitted.
            On catastrophic error, returns empty StateSnapshot.
        """
        try:
            data: Dict[str, Any] = {}
            for name in sections:
                section_data = self._read_one(name)
                if section_data is not None:
                    data[name] = section_data
            return StateSnapshot(sections=data)
        except Exception:
            logger.exception("SessionStateProdAdapter.read failed")
            return StateSnapshot(sections={})

    def _read_one(self, name: str) -> Optional[Dict[str, Any]]:
        """Read a single section, returning None on missing/error."""
        try:
            section_obj = self._manager.get_section(name)
            if section_obj is None:
                return None
            return self._section_to_dict(section_obj)
        except KeyError:
            # SectionNotFoundError is a KeyError subclass
            logger.debug("Section '%s' not found in SessionState", name)
            return None

    @staticmethod
    def _section_to_dict(section_obj: Any) -> Optional[Dict[str, Any]]:
        """Convert a section object to dict.

        WARM/COLD sections expose ``to_dict()``.
        HOT sections (control, task_state, …) expose ``get_metadata()``.
        """
        if hasattr(section_obj, "to_dict"):
            return section_obj.to_dict()
        if hasattr(section_obj, "get_metadata"):
            return section_obj.get_metadata()
        if isinstance(section_obj, dict):
            return section_obj
        logger.warning(
            "Section %s has no to_dict()/get_metadata() method",
            type(section_obj).__name__,
        )
        return None


__all__ = ["SessionStateProdAdapter"]
