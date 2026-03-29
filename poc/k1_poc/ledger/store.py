"""
poc.k1_poc.ledger.store -- Ledger storage protocol and in-memory implementation.

M1 E1.2.1: Defines the storage contract (ILedgerStore) and a POC-ready
InMemoryLedgerStore. A future SqliteLedgerStore (M2+) will implement
the same protocol for production persistence.

LedgerEntry is an immutable record: once written, never mutated.
The store assigns monotonic sequence numbers within each session scope.

Reference: v3_milestones.md E1.2.1 (ILedgerStore protocol).
Reference: v3_whiteboard.md 3.A (append-only, immutable entries).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """Immutable record in the conversation ledger.

    Attributes:
        seq:            Monotonic sequence number within session (1-based).
        event_id:       Domain UUID4 from CanonicalEventMeta (idempotency key).
        event_type:     Canonical event type string (e.g. "task.completed").
        session_id:     Session scope identifier.
        payload:        Full serialized event payload (from to_payload()).
        written_at_utc: Wall-clock UTC timestamp when entry was written (ISO 8601).
    """

    seq: int
    event_id: str
    event_type: str
    session_id: str
    payload: dict[str, Any]
    written_at_utc: str


@runtime_checkable
class ILedgerStore(Protocol):
    """Storage protocol for the conversation ledger.

    Implementations must be safe for single-writer usage.
    The writer handles idempotency; the store handles ordering.
    """

    def append(self, entry: LedgerEntry) -> int:
        """Append an entry to the ledger. Returns the assigned sequence number.

        The store MUST assign the seq field (caller may pass seq=0 as placeholder).
        """
        ...

    def read(
        self,
        session_id: str,
        from_seq: int = 0,
        to_seq: int | None = None,
    ) -> list[LedgerEntry]:
        """Read entries for a session within a sequence range.

        Args:
            session_id: Session to read from.
            from_seq:   Inclusive lower bound (0 means from start).
            to_seq:     Inclusive upper bound (None means to end).

        Returns:
            List of LedgerEntry in sequence order.
        """
        ...

    def read_by_type(
        self,
        session_id: str,
        event_type: str,
    ) -> list[LedgerEntry]:
        """Read all entries of a specific event type for a session.

        Args:
            session_id: Session to read from.
            event_type: Canonical event type string to filter by.

        Returns:
            List of matching LedgerEntry in sequence order.
        """
        ...

    def exists(self, event_id: str) -> bool:
        """Check if an event_id has already been written (idempotency check).

        Args:
            event_id: Domain UUID4 to check.

        Returns:
            True if a ledger entry with this event_id exists.
        """
        ...


class InMemoryLedgerStore:
    """In-memory ledger store for POC and testing.

    Thread-safe via a lock. Entries are stored in a flat list with
    an O(1) set lookup for idempotency checks.

    Not suitable for production -- no persistence across restarts.
    Future: SqliteLedgerStore (M2+) for durable storage.
    """

    __slots__ = ("_entries", "_event_ids", "_next_seq", "_lock")

    def __init__(self) -> None:
        self._entries: list[LedgerEntry] = []
        self._event_ids: set[str] = set()
        self._next_seq: int = 1
        self._lock = threading.Lock()

    def append(self, entry: LedgerEntry) -> int:
        """Append entry, assigning the next monotonic sequence number.

        The caller provides entry with seq=0; the store replaces it
        with the actual sequence number.
        """
        with self._lock:
            seq = self._next_seq
            self._next_seq += 1
            # Frozen dataclass -- must create new instance with correct seq
            stored = LedgerEntry(
                seq=seq,
                event_id=entry.event_id,
                event_type=entry.event_type,
                session_id=entry.session_id,
                payload=entry.payload,
                written_at_utc=entry.written_at_utc,
            )
            self._entries.append(stored)
            self._event_ids.add(entry.event_id)
            logger.debug(
                "Ledger append seq=%d type=%s event_id=%s session=%s",
                seq,
                entry.event_type,
                entry.event_id,
                entry.session_id,
            )
            return seq

    def read(
        self,
        session_id: str,
        from_seq: int = 0,
        to_seq: int | None = None,
    ) -> list[LedgerEntry]:
        """Read entries for a session within a sequence range."""
        with self._lock:
            result: list[LedgerEntry] = []
            for entry in self._entries:
                if entry.session_id != session_id:
                    continue
                if entry.seq < from_seq:
                    continue
                if to_seq is not None and entry.seq > to_seq:
                    continue
                result.append(entry)
            return result

    def read_by_type(
        self,
        session_id: str,
        event_type: str,
    ) -> list[LedgerEntry]:
        """Read all entries of a specific event type for a session."""
        with self._lock:
            return [
                e
                for e in self._entries
                if e.session_id == session_id and e.event_type == event_type
            ]

    def exists(self, event_id: str) -> bool:
        """O(1) idempotency check via event_id set."""
        with self._lock:
            return event_id in self._event_ids

    def count(self, session_id: str | None = None) -> int:
        """Return total entry count, optionally filtered by session_id.

        Convenience method for testing and diagnostics.
        """
        with self._lock:
            if session_id is None:
                return len(self._entries)
            return sum(1 for e in self._entries if e.session_id == session_id)

    def read_all(self, session_id: str | None = None) -> list[LedgerEntry]:
        """Read all entries, optionally filtered by session.

        Convenience method for replay and testing.
        """
        with self._lock:
            if session_id is None:
                return list(self._entries)
            return [e for e in self._entries if e.session_id == session_id]
