"""SessionReadAdapter -- bridges MW's ISessionReadPort to SessionStateManager.

Translates:
  MW  async snapshot(sections) -> Dict[str, Any]
  MW  async read_section(name) -> Optional[Dict[str, Any]]
    SS  sync  get_section(name)  -> section_obj  (with .to_dict() or zero-arg .get())

The adapter wraps SessionStateManager directly (not through Fabric's
ISessionStateReader) to minimize latency for MW-02 (<1ms P99).

Design:
  - Lock-free reads: SSM guarantees multi-reader concurrency.
    - Sections returned as dicts via ``section.to_dict()`` or zero-arg ``section.get()``.
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
from inspect import Parameter, signature
from typing import Any, Dict, FrozenSet, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class _ISessionStateManager(Protocol):
    """Minimal local Protocol for SessionStateManager dependency (MW-01)."""

    def get_section(self, name: str) -> Any: ...


class SessionReadAdapter:
    """Implements MW's ISessionReadPort by wrapping SessionStateManager.

    Translation:
        snapshot(sections) -> loop get_section(name) -> dict conversion -> collect
        read_section(name) -> get_section(name) -> dict conversion -> return

    MW-01 enforced: this class exposes NO write methods.
    MW-02 target: all hot reads lock-free, <1ms P99.

    Constructor Args:
        manager: A SessionStateManager instance (typed as Any to avoid
            import coupling with the sessionstate module, matching the
            pattern used by Fabric's SessionStateReaderAdapter).
        cold_archive: Optional LocalColdArchive for the enriched
            ``read_archived_history`` path. When ``None`` the enriched
            method returns ``[]`` (graceful fallback for test /
            standalone modes).
    """

    __slots__ = ("_manager", "_cold_archive")

    def __init__(
        self,
        manager: _ISessionStateManager,
        cold_archive: Optional[Any] = None,
    ) -> None:
        self._manager = manager
        self._cold_archive = cold_archive

    async def snapshot(
        self,
        sections: List[str],
    ) -> Dict[str, Any]:
        """Retrieve multiple SessionState sections in a single read.

        Args:
            sections: List of section names to retrieve.

        Returns:
            Dict mapping section name -> section data.
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
        """Convert a section object to dict via to_dict() or zero-arg get().

        Args:
            section_obj: Section instance from SessionStateManager.

        Returns:
            Dict representation, or None if conversion fails.
        """
        if hasattr(section_obj, "to_dict"):
            return section_obj.to_dict()
        get_fn = getattr(section_obj, "get", None)
        if callable(get_fn) and SessionReadAdapter._callable_without_args(get_fn):
            data = get_fn()
            if isinstance(data, dict):
                return data
        if isinstance(section_obj, dict):
            return section_obj
        logger.warning(
            "Section object %s has no snapshot dict method",
            type(section_obj).__name__,
        )
        return None

    @staticmethod
    def _callable_without_args(func: Any) -> bool:
        try:
            params = signature(func).parameters.values()
        except (TypeError, ValueError):
            return False
        return all(
            param.default is not Parameter.empty
            or param.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD)
            for param in params
        )

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

    async def read_archived_history(
        self,
        session_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Recover archived ``history_active`` turns from LOCAL COLD.

        Enriched (NON-SLA) read used by the session-batch extractor to
        recover turns that have been demoted out of the live 16KB
        ``history_active`` window into K1 SQLite. The hot path NEVER
        calls this — it is best-effort and may take >1ms.

        Behaviour:
          * If no ``cold_archive`` was injected, returns ``[]``.
          * Calls ``LocalColdArchive.restore_all("history_active",
            session_id)`` to fetch all archive blobs (newest first).
          * Each blob is a serialized ``HistoryActiveSection``
            FlatBuffer; we deserialize, extract its ``turns``, and
            de-duplicate across blobs by ``turn_id``.
          * Returns turns sorted oldest-first, capped at ``limit``.
          * Any exception is caught and logged; the method returns
            ``[]`` rather than propagating (callers must not fail).
        """
        if self._cold_archive is None:
            return []

        try:
            results = self._cold_archive.restore_all("history_active", session_id, limit=limit)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "read_archived_history: restore_all failed for session %s: %s",
                session_id,
                exc,
            )
            return []

        if not results:
            return []

        # Lazy import to avoid module-load coupling with sessionstate.
        try:
            from k1.sessionstate.sections.history_active import HistoryActiveSection
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("read_archived_history: cannot import HistoryActiveSection: %s", exc)
            return []

        seen_ids: set[str] = set()
        merged: List[Dict[str, Any]] = []
        for r in results:
            if not getattr(r, "success", False):
                continue
            data = getattr(r, "data", None)
            if not data:
                continue
            try:
                section = HistoryActiveSection(session_id=session_id)
                section.from_flatbuffer(data)
                turns_dict = section.to_dict().get("turns", [])
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("read_archived_history: deserialize failed: %s", exc)
                continue
            for t in turns_dict:
                tid = t.get("turn_id", "")
                if tid and tid in seen_ids:
                    continue
                if tid:
                    seen_ids.add(tid)
                merged.append(t)

        # Oldest-first ordering. Cross-blob ``turn_number`` may overlap
        # (each evicted section started its own counter at 1), so we sort
        # by ``timestamp_ms`` first and fall back to ``turn_number`` when
        # timestamps are missing/equal.
        merged.sort(
            key=lambda t: (
                int(t.get("timestamp_ms", 0)),
                int(t.get("turn_number", 0)),
            )
        )
        if len(merged) > limit:
            # Keep the most recent ``limit`` archived turns when over budget.
            merged = merged[-limit:]
        return merged
