"""
k1.concierge.delta.snapshot_reader -- Lock-free point-in-time SS reads.

V2 Design Ref: Section 5 (Cross-Actor Read Consistency)

Both Front and Back read SS freely.  Reads return a point-in-time
snapshot (<1ms).  If Back reads beliefs_active while Front is
updating it, Back gets the pre-update version.  This is fine --
eventual consistency for reads, strict consistency for writes.

Implementation: dict.copy() provides a shallow snapshot.  For the
POC, SS sections are flat dicts, so shallow copy is sufficient.
Production would use immutable data structures or copy-on-write.

Cross-actor read scenarios (V2 Section 5):
    Front reads task_artifacts while FSM writes  -> Front gets pre-write snapshot
    Back reads beliefs_active while Front writes -> Back gets pre-write snapshot
    Both read history_active simultaneously      -> Both get same snapshot
    Front reads task_state to check progress     -> Gets latest committed state
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SectionSnapshot:
    """Immutable point-in-time snapshot of a SS section.

    Returned by SnapshotReader.read().  The data dict is a shallow
    copy of the section's data at the time of the read.  Mutations
    to the live section after this snapshot was taken do not affect
    this snapshot's data.

    Attributes:
        section:     Section name.
        data:        Shallow copy of section data at snapshot time.
        snapshot_ns: Monotonic timestamp (ns) when snapshot was taken.
        version:     Section version at snapshot time (monotonic counter).
    """

    section: str
    data: dict[str, Any]
    snapshot_ns: int
    version: int

    @property
    def age_ms(self) -> float:
        """How old this snapshot is in milliseconds.

        Useful for staleness checks.  V2 Section 5 targets <1ms
        for snapshot creation; this measures time since creation.
        """
        return (time.monotonic_ns() - self.snapshot_ns) / 1_000_000


class SnapshotReader:
    """Provides lock-free SS section reads.

    Each read captures a point-in-time copy.  The reader never
    blocks on writes.  Writes and reads are isolated -- a write
    that occurs during a read does not corrupt the read's result.

    V2 Section 5, Rule 3: "Reads are lock-free snapshots."

    Attributes:
        _sections: The live SS section data (mutable).
        _versions: Per-section monotonic version counter.
    """

    __slots__ = ("_sections", "_versions")

    def __init__(self) -> None:
        self._sections: dict[str, dict[str, Any]] = {}
        self._versions: dict[str, int] = {}

    def register_section(self, name: str, initial_data: dict[str, Any] | None = None) -> None:
        """Register a section with optional initial data.

        Args:
            name:         Section name.
            initial_data: Initial key-value data for the section.
        """
        self._sections[name] = dict(initial_data or {})
        self._versions[name] = 0

    def read(self, section: str) -> SectionSnapshot:
        """Read a point-in-time snapshot of a section.

        Returns an immutable SectionSnapshot with a shallow copy of
        the section's current data.  The caller can inspect this
        snapshot without worrying about concurrent writes.

        Performance target: <1ms (V2 Section 5).

        Args:
            section: Section name to read.

        Returns:
            Frozen SectionSnapshot with copied data.
        """
        data = self._sections.get(section, {})
        return SectionSnapshot(
            section=section,
            data=dict(data),  # Shallow copy -- isolates from writes
            snapshot_ns=time.monotonic_ns(),
            version=self._versions.get(section, 0),
        )

    def write(self, section: str, key: str, value: Any) -> None:
        """Write a value to a section.

        Used by FSM / authorized writers to update live section data.
        Each write increments the section's version counter.

        Args:
            section: Target section name.
            key:     Key within the section.
            value:   Value to write.
        """
        if section not in self._sections:
            self._sections[section] = {}
        self._sections[section][key] = value
        self._versions[section] = self._versions.get(section, 0) + 1

    def delete(self, section: str, key: str) -> bool:
        """Delete a key from a section.

        Args:
            section: Target section name.
            key:     Key to delete.

        Returns:
            True if the key existed and was deleted.
        """
        if section in self._sections and key in self._sections[section]:
            del self._sections[section][key]
            self._versions[section] = self._versions.get(section, 0) + 1
            return True
        return False

    def read_multiple(self, sections: list[str]) -> dict[str, SectionSnapshot]:
        """Read snapshots of multiple sections.

        Each section is independently snapshotted.  This is NOT
        atomically consistent across sections -- each snapshot
        reflects the section's state at a slightly different time.
        For the POC, this is acceptable.  Production would use a
        global version counter or snapshot isolation.

        Args:
            sections: List of section names to read.

        Returns:
            Dict mapping section name to its SectionSnapshot.
        """
        return {s: self.read(s) for s in sections}

    @property
    def section_names(self) -> frozenset[str]:
        """All registered section names."""
        return frozenset(self._sections.keys())

    def section_version(self, section: str) -> int:
        """Current version of a section.

        Args:
            section: Section name.

        Returns:
            Monotonic version counter, or 0 if unregistered.
        """
        return self._versions.get(section, 0)
