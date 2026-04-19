"""
k1.bus.outbox -- Durable outbox for the K1 bus (P6.13).

Provides ``BusOutbox`` (SQLite WAL-backed) for at-least-once delivery
of envelopes on durable topics.  See :mod:`k1.bus.outbox.sqlite_outbox`.
"""

from __future__ import annotations

from k1.bus.outbox.sqlite_outbox import BusOutbox, OutboxRecord

__all__ = ["BusOutbox", "OutboxRecord"]
