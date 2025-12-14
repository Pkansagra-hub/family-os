from __future__ import annotations

from typing import Any

from ward import test  # type: ignore[attr-defined]

from k0.idem.ledger import IdempotencyLedger, LedgerEntry
from k0.tests.storage.fixtures import sqlite_runtime  # type: ignore[misc]


@test("idempotency ledger upserts and retrieves entries")
def _(sqlite_runtime: Any = sqlite_runtime) -> None:
    ledger = IdempotencyLedger()
    entry = LedgerEntry(
        idem_key="idem-123",
        receipt_id="rcpt-123",
        first_seen_ts="2025-09-28T12:00:00Z",
        state="COMMITTED",
        expiry_ts="2025-10-01T00:00:00Z",
    )

    ledger.upsert(entry)
    fetched = ledger.lookup(entry.idem_key)
    assert fetched == entry

    updated = LedgerEntry(
        idem_key="idem-123",
        receipt_id="rcpt-123",
        first_seen_ts="2025-09-28T12:00:00Z",
        state="REJECTED",
        expiry_ts=None,
    )
    ledger.upsert(updated)

    fetched_updated = ledger.lookup(entry.idem_key)
    assert fetched_updated == updated

