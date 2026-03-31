"""
k1.concierge.ledger.writer -- Ledger writer with idempotency.

M1 E1.2.1: LedgerWriter wraps ILedgerStore with idempotency logic.
If an event_id has already been written, the existing sequence number
is returned without a duplicate write.

The writer is scoped to a single session. Each FSM controller instance
creates its own LedgerWriter at session start.

Reference: v3_milestones.md E1.2.1 (idempotency key = event_id).
Reference: v3_whiteboard.md 3.A (append-only, dedup by event_id).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from k1.concierge.ledger.store import ILedgerStore, LedgerEntry

if TYPE_CHECKING:
    from k1.concierge.events.base import CanonicalEventMeta

logger = logging.getLogger(__name__)


class LedgerWriter:
    """Append-only writer with idempotency for a single session.

    Usage:
        store = InMemoryLedgerStore()
        writer = LedgerWriter(store, session_id="sess-001")
        seq = await writer.append(some_canonical_event)

    Idempotency guarantee: calling append() twice with the same event_id
    returns the same sequence number without writing a duplicate entry.

    Attributes:
        _store:      Underlying storage backend.
        _session_id: Session scope for all entries written by this writer.
    """

    __slots__ = ("_store", "_session_id")

    def __init__(self, store: ILedgerStore, session_id: str) -> None:
        self._store = store
        self._session_id = session_id
        logger.info("LedgerWriter created for session=%s", session_id)

    @property
    def session_id(self) -> str:
        """The session this writer is scoped to."""
        return self._session_id

    @property
    def store(self) -> ILedgerStore:
        """The underlying store (exposed for projections and replay)."""
        return self._store

    async def append(self, event: CanonicalEventMeta) -> int:
        """Append a canonical event to the ledger.

        Idempotency: if event.event_id already exists in the store,
        returns the existing sequence number without writing.

        Args:
            event: A CanonicalEventMeta instance (or subclass) to record.

        Returns:
            The sequence number assigned to (or already held by) this event.
        """
        event_id = event.event_id

        # Idempotency check
        if self._store.exists(event_id):
            existing = self._find_existing_seq(event_id)
            logger.debug(
                "Idempotent skip: event_id=%s already at seq=%d",
                event_id,
                existing,
            )
            return existing

        entry = LedgerEntry(
            seq=0,  # Assigned by store
            event_id=event_id,
            event_type=event.event_type,
            session_id=self._session_id,
            payload=event.to_payload(),
            written_at_utc=datetime.now(timezone.utc).isoformat(),
        )
        seq = self._store.append(entry)
        logger.debug(
            "Ledger write seq=%d type=%s event_id=%s session=%s",
            seq,
            event.event_type,
            event_id,
            self._session_id,
        )
        return seq

    def append_sync(self, event: CanonicalEventMeta) -> int:
        """Synchronous append for non-async contexts.

        Same idempotency guarantees as async append().
        Useful for mutation points in sync code paths.
        """
        event_id = event.event_id

        if self._store.exists(event_id):
            existing = self._find_existing_seq(event_id)
            logger.debug(
                "Idempotent skip (sync): event_id=%s already at seq=%d",
                event_id,
                existing,
            )
            return existing

        entry = LedgerEntry(
            seq=0,
            event_id=event_id,
            event_type=event.event_type,
            session_id=self._session_id,
            payload=event.to_payload(),
            written_at_utc=datetime.now(timezone.utc).isoformat(),
        )
        seq = self._store.append(entry)
        logger.debug(
            "Ledger write (sync) seq=%d type=%s event_id=%s session=%s",
            seq,
            event.event_type,
            event_id,
            self._session_id,
        )
        return seq

    def _find_existing_seq(self, event_id: str) -> int:
        """Locate the sequence number for an already-written event_id.

        Scans the session's entries. For InMemoryLedgerStore this is O(n)
        but acceptable for POC volumes.
        """
        entries = self._store.read(self._session_id)
        for entry in entries:
            if entry.event_id == event_id:
                return entry.seq
        # Should not happen if exists() returned True, but defensive
        logger.warning("event_id=%s reported as existing but not found in read", event_id)
        return -1
