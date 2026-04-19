"""SessionReadAdapter -- bridges MW's ISessionReadPort to SessionStateManager.

Translates:
  MW  async snapshot(sections) -> Dict[str, Any]
  MW  async read_section(name) -> Optional[Dict[str, Any]]
  SS  sync  get_section(name)  -> section_obj  (with .to_dict())

The adapter wraps SessionStateManager directly (not through Fabric's
ISessionStateReader) to minimize latency for MW-02 (<1ms P99).

Design:
  - Lock-free reads: SSM guarantees multi-reader concurrency.
  - Sections returned as dicts via ``section.to_dict()``.
  - SectionNotFoundError -> omit (snapshot) / None (read_section).
    This handles phantom sections (affective_baseline, ifl) that MW
    config references but do not exist in SessionState.
  - No session_id binding: MW operates in single-session context.
  - MW-01 enforced: NO write methods. Read-only adapter.

Error mapping:
  - SectionNotFoundError (KeyError subclass) -> graceful omit/None
  - Any other exception -> re-raise (signals SS unreachable)

References:
  - E-0.5.6: SessionState->MemoryWriter Missing Adapter
  - I-0.5.6.1: SessionReadAdapter implementation
  - k1/memory_writer/ports/session_read_port.py (ISessionReadPort)
  - k1/sessionstate/manager.py (SessionStateManager)
  - k1/fabric/adapters/sessionstate_reader.py (pattern reference)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, FrozenSet, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class _ISessionStateManager(Protocol):
    """Minimal local Protocol for SessionStateManager dependency (MW-01)."""

    def get_section(self, name: str) -> Any: ...


class SessionReadAdapter:
    """Implements MW's ISessionReadPort by wrapping SessionStateManager.

    Translation:
        snapshot(sections) -> loop get_section(name) -> to_dict() -> collect
        read_section(name) -> get_section(name) -> to_dict() -> return

    MW-01 enforced: this class exposes NO write methods.
    MW-02 target: all reads lock-free, <1ms P99.

    Constructor Args:
        manager: A SessionStateManager instance (typed as Any to avoid
            import coupling with the sessionstate module, matching the
            pattern used by Fabric's SessionStateReaderAdapter).
    """

    __slots__ = ("_manager",)

    def __init__(self, manager: _ISessionStateManager) -> None:
        self._manager = manager

    async def snapshot(
        self,
        sections: List[str],
    ) -> Dict[str, Any]:
        """Retrieve multiple SessionState sections in a single read.

        Args:
            sections: List of section names to retrieve.

        Returns:
            Dict mapping section name -> section data (via to_dict()).
            Missing or unavailable sections are omitted from the result.
            Phantom sections (affective_baseline, ifl) are silently skipped.
        """
        result: Dict[str, Any] = {}
        for name in sections:
            data = await self.read_section(name)
            if data is not None:
                result[name] = data
        return result

    async def read_section(
        self,
        name: str,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a single named section from SessionState.

        Args:
            name: Section name (e.g. "beliefs_active", "persona").

        Returns:
            Section data as a dict, or None if the section is
            unavailable or does not exist.
        """
        try:
            section_obj = self._manager.get_section(name)
            if section_obj is None:
                return None
            return self._section_to_dict(section_obj)
        except KeyError:
            # SectionNotFoundError is a KeyError subclass.
            # Covers real unknown sections AND phantom sections
            # (affective_baseline, ifl) that MW config references
            # but SS does not have.
            logger.debug("Section '%s' not found in SessionState", name)
            return None

    @staticmethod
    def _section_to_dict(section_obj: Any) -> Optional[Dict[str, Any]]:
        """Convert a section object to dict via to_dict().

        Args:
            section_obj: Section instance from SessionStateManager.

        Returns:
            Dict representation, or None if conversion fails.
        """
        if hasattr(section_obj, "to_dict"):
            return section_obj.to_dict()
        if isinstance(section_obj, dict):
            return section_obj
        logger.warning(
            "Section object %s has no to_dict() method",
            type(section_obj).__name__,
        )
        return None

    async def list_sections(self) -> FrozenSet[str]:
        """Return the authoritative set of all SessionState section names.

        Lazy-imports ALL_SECTIONS from sizetracker to avoid circular
        imports at module load time.
        """
        from k1.sessionstate.sizetracker import ALL_SECTIONS

        return ALL_SECTIONS

    async def snapshot_all(
        self,
        exclude: FrozenSet[str] = frozenset(),
    ) -> Dict[str, Any]:
        """Read ALL sections except those in exclude set.

        Delegates to list_sections() for the authoritative section set,
        then calls snapshot() with the filtered list.
        """
        all_sections = await self.list_sections()
        sections_to_read = sorted(all_sections - exclude)
        return await self.snapshot(sections_to_read)
