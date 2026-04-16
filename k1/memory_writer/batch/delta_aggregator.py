"""
k1.memory_writer.batch.delta_aggregator -- Time-window batching with dedup.

Collects envelopes during the batch window (MW-08: 250ms default),
deduplicates by participants+topics hash, sorts by causal order.

Each MW session instance has its own DeltaAggregator.
No shared state between sessions.
"""

from __future__ import annotations

import hashlib
import logging

from k1.memory_writer.config import MWConfig
from k1.memory_writer.invariants import assert_mw08_batch_window

log = logging.getLogger(__name__)


class DeltaAggregator:
    """Time-window batching for K0 command envelopes.

    Collects envelopes during the batch window (MW-08: 250ms default),
    deduplicates by participants+topics hash, sorts by causal order.

    Each MW session instance has its own DeltaAggregator.
    No shared state between sessions.
    """

    def __init__(self, config: MWConfig) -> None:
        # MW-08: validate batch window
        assert_mw08_batch_window(config)
        self._window_ms = config.batch_window_ms
        self._pending: list[dict] = []
        self._seen_hashes: set[str] = set()

    @property
    def window_ms(self) -> int:
        return self._window_ms

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    def add(self, envelope: dict) -> bool:
        """Add envelope to current batch. Dedup by participants+topics hash.

        Args:
            envelope: Envelope dict from EnvelopeBuilder.

        Returns:
            True if added, False if deduplicated (skipped).

        K0 gap G9: Deduplicated envelopes are skipped entirely.
        K0 R3 reconciliation is saved a DB query per dedup.
        """
        hash_key = self._compute_hash(envelope)
        if hash_key in self._seen_hashes:
            log.info("MW: dedup within batch window", extra={"hash": hash_key[:8]})
            return False
        self._seen_hashes.add(hash_key)
        self._pending.append(envelope)
        return True

    def flush(self) -> list[dict]:
        """Flush the current batch. Returns envelopes in causal order.

        Called after the batch window timer expires (250ms).
        Clears the pending list and seen hashes for the next window.

        Returns:
            List of envelope dicts sorted by conversation_turn, then
            extraction_sequence. Empty list if nothing pending.
        """
        batch = sorted(
            self._pending,
            key=lambda e: (
                e.get("body", {}).get("conversation_turn", 0),
                e.get("body", {}).get("extraction_sequence", 0),
            ),
        )
        self._pending = []
        self._seen_hashes = set()
        return batch

    @staticmethod
    def _compute_hash(envelope: dict) -> str:
        """Dedup key: sorted participants + sorted topics.

        Catches duplicate extractions from the same turn that describe
        the same event with the same people and topics.
        """
        body = envelope.get("body", {})
        parts = sorted(body.get("participants", []))
        topics = sorted(body.get("topics", []))
        raw = f"{parts}:{topics}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
