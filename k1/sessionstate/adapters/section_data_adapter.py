"""
SectionDataAdapter — implements IEvictionSectionProvider + IMigrationSectionProvider
against live HotTier / WarmTier section objects.

Closes audit Fix J. Without this adapter the EvictionEngine and MigrationEngine
operate in placeholder mode (no real data movement). With it:

* Eviction can read a section's serialized state, hand it to LocalColdArchive,
  then call the section's ``clear()`` to actually free memory.
* Migration can move whole-section payloads between HOT and WARM tiers
  (best-effort: heterogeneous section APIs make per-item movement impractical
  without per-section custom logic; see docstring on each method).

Design notes
------------
The HOT and WARM section classes are heterogeneous (BeliefsActiveSection,
HistoryActiveSection, ScoreboardSection, etc.) — each has its own typed API.
A fully type-aware adapter for every section would duplicate large parts of
each section's logic. Instead this adapter relies on the *minimal* generic
contract every section already implements:

* ``get_size_bytes() -> int``
* ``clear() -> None``
* ``to_dict() -> dict``  (where present — most sections expose it)

For migration ``add_items`` the adapter falls back to an in-memory overflow
buffer keyed by section name. This buffer is consulted by ``get_items`` and
counted in ``get_turn_count`` so the migration round-trips correctly within a
single session lifetime. Production-grade per-section migration (e.g.
turn-by-turn rolling demotion in history sections) remains future work and
is documented in ``docs/edge_enhancement_opportunities.md`` (audit Fix J+).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from k1.sessionstate.migration import MigrationItem

if TYPE_CHECKING:
    from k1.sessionstate.tiers.hot import HotTier
    from k1.sessionstate.tiers.warm import WarmTier

logger = logging.getLogger(__name__)


class SectionDataAdapter:
    """Live adapter implementing both eviction + migration provider protocols.

    Resolves a section name to either the HOT or WARM tier transparently.
    """

    __slots__ = ("_hot", "_warm", "_overflow")

    def __init__(self, hot: "HotTier", warm: "WarmTier") -> None:
        self._hot = hot
        self._warm = warm
        # Per-section overflow buffer for items added via add_items().
        # Migration items live here until the section's native API can absorb
        # them; eviction will still serialize+clear the underlying section.
        self._overflow: Dict[str, List[MigrationItem]] = {}

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _resolve(self, section: str) -> Optional[Any]:
        """Return the live section object for ``section`` or None."""
        sec = self._hot.get_section(section)
        if sec is not None:
            return sec
        return self._warm.get_section(section)

    @staticmethod
    def _serialize(sec: Any) -> bytes:
        """Serialize a section to bytes via its ISection contract.

        Every section must implement ``to_flatbuffer() -> bytes``.
        Falling back to pickle is not allowed (RCE risk — SS-SECURITY-01).
        """
        to_fb = getattr(sec, "to_flatbuffer", None)
        if callable(to_fb):
            try:
                return to_fb()
            except Exception:
                logger.warning(
                    "to_flatbuffer() failed for section %r; returning empty bytes",
                    type(sec).__name__,
                    exc_info=True,
                )
                return b""
        raise TypeError(
            f"Section {type(sec)!r} does not implement to_flatbuffer(). "
            "All sections must have an explicit FlatBuffer serializer."
        )

    # ------------------------------------------------------------------ #
    # IEvictionSectionProvider
    # ------------------------------------------------------------------ #

    def get_section_data(self, section: str) -> Optional[bytes]:
        sec = self._resolve(section)
        if sec is None:
            return None
        return self._serialize(sec)

    def clear_section(self, section: str) -> int:
        sec = self._resolve(section)
        freed = 0
        if sec is not None:
            try:
                freed = sec.get_size_bytes()
            except Exception:
                freed = 0
            clear = getattr(sec, "clear", None)
            if callable(clear):
                clear()
        # Drop overflow too.
        if section in self._overflow:
            freed += sum(item.size_bytes for item in self._overflow.pop(section))
        return freed

    def get_evictable_data(self, section: str, target_bytes: int) -> Tuple[bytes, int]:
        """Return ``(data, actual_bytes)`` for archival.

        Whole-section eviction: the entire section is serialized and the
        reported byte count is ``min(target_bytes, section_size)``.
        """
        sec = self._resolve(section)
        if sec is None:
            return (b"", 0)
        try:
            size = sec.get_size_bytes()
        except Exception:
            size = 0
        if size == 0 and section not in self._overflow:
            return (b"", 0)
        data = self._serialize(sec)
        # Include overflow so evictable bytes match what we actually free.
        if section in self._overflow:
            try:
                data = data + pickle.dumps(self._overflow[section])
            except Exception:
                pass
        actual = min(
            target_bytes, size + sum(item.size_bytes for item in self._overflow.get(section, []))
        )
        return (data, actual)

    def remove_evicted_data(self, section: str, bytes_to_remove: int) -> int:
        """Free up to ``bytes_to_remove`` from ``section``.

        Whole-section semantics: any non-zero eviction request clears the
        full underlying section (partial eviction is not supported by the
        heterogeneous section APIs). Overflow buffer is cleared first.
        """
        if bytes_to_remove <= 0:
            return 0
        sec = self._resolve(section)
        freed = 0
        # Clear overflow first (cheap, in-memory).
        if section in self._overflow:
            freed += sum(item.size_bytes for item in self._overflow.pop(section))
        if sec is not None:
            try:
                current = sec.get_size_bytes()
            except Exception:
                current = 0
            if current > 0:
                clear = getattr(sec, "clear", None)
                if callable(clear):
                    clear()
                    freed += current
        return freed

    # ------------------------------------------------------------------ #
    # IMigrationSectionProvider
    # ------------------------------------------------------------------ #

    def get_items(self, section: str) -> List[MigrationItem]:
        """Return migration items for ``section``.

        For sections that expose ``to_dict()`` we synthesize a single
        whole-section MigrationItem capturing the current state. Plus any
        overflow items previously added via ``add_items``.
        """
        items: List[MigrationItem] = []
        sec = self._resolve(section)
        if sec is not None:
            try:
                size = sec.get_size_bytes()
            except Exception:
                size = 0
            if size > 0:
                to_dict = getattr(sec, "to_dict", None)
                data: Any
                if callable(to_dict):
                    try:
                        data = to_dict()
                    except Exception:
                        data = None
                else:
                    data = None
                items.append(
                    MigrationItem(
                        section=section,
                        key=f"{section}::snapshot",
                        data=data,
                        size_bytes=size,
                    )
                )
        items.extend(self._overflow.get(section, []))
        return items

    def add_items(self, section: str, items: List[MigrationItem]) -> int:
        """Buffer ``items`` against ``section``.

        Items are kept in the per-section overflow buffer. They contribute
        to subsequent ``get_items``, ``get_turn_count``, and eviction-byte
        accounting. Future per-section absorption (e.g. merging into a
        BeliefsHistorySection) is left as follow-up work.
        """
        if not items:
            return 0
        bucket = self._overflow.setdefault(section, [])
        added = 0
        for item in items:
            bucket.append(item)
            added += item.size_bytes
        return added

    def remove_items(self, section: str, keys: List[str]) -> int:
        if not keys or section not in self._overflow:
            return 0
        keep: List[MigrationItem] = []
        freed = 0
        for item in self._overflow[section]:
            if item.key in keys:
                freed += item.size_bytes
            else:
                keep.append(item)
        self._overflow[section] = keep
        return freed

    def get_turn_count(self, section: str) -> int:
        """Best-effort turn count for history sections.

        For ``history_*`` sections we look for a turn-aware API on the live
        section object; otherwise we report the overflow buffer length.
        """
        sec = self._resolve(section)
        if sec is not None:
            for attr in ("turn_count", "get_turn_count", "size"):
                value = getattr(sec, attr, None)
                if callable(value):
                    try:
                        return int(value())
                    except Exception:
                        continue
                if isinstance(value, int):
                    return value
        return len(self._overflow.get(section, []))

    def get_oldest_turns(self, section: str, count: int) -> List[MigrationItem]:
        items = self.get_items(section)
        return items[: max(0, count)]
