"""Receipt persistence adapter."""

from __future__ import annotations

import asyncio
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from k0.uow.connection_pool import connection_scope


@dataclass(slots=True)
class Receipt:
    receipt_id: str
    idem_key: str
    wal_pos: int
    commit_ts: str
    tenant_id: str
    space_id: str
    device_id: str
    mls_group_id: str
    key_version: str
    device_sig: str
    manifest_fingerprint: str | None = None


@contextmanager
def _resolve_connection(
    connection: sqlite3.Connection | None,
) -> Iterator[sqlite3.Connection]:
    if connection is not None:
        yield connection
        return

    with connection_scope() as pooled_connection:
        yield pooled_connection
        pooled_connection.commit()


class ReceiptStore:
    """Operations for persisting and retrieving receipts."""

    async def save_async(
        self, receipt: Receipt, *, connection: sqlite3.Connection | None = None
    ) -> None:
        """Async wrapper for save."""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: self.save(receipt, connection=connection))

    def save(self, receipt: Receipt, *, connection: sqlite3.Connection | None = None) -> None:
        with _resolve_connection(connection) as conn:
            conn.execute(
                (
                    "INSERT INTO st_receipts (receipt_id, idem_key, wal_pos, commit_ts, tenant_id, "
                    "space_id, device_id, mls_group_id, key_version, device_sig, manifest_fingerprint) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(receipt_id) DO UPDATE SET idem_key=excluded.idem_key, wal_pos=excluded.wal_pos, "
                    "commit_ts=excluded.commit_ts, tenant_id=excluded.tenant_id, space_id=excluded.space_id, "
                    "device_id=excluded.device_id, mls_group_id=excluded.mls_group_id, key_version=excluded.key_version, "
                    "device_sig=excluded.device_sig, manifest_fingerprint=excluded.manifest_fingerprint"
                ),
                (
                    receipt.receipt_id,
                    receipt.idem_key,
                    receipt.wal_pos,
                    receipt.commit_ts,
                    receipt.tenant_id,
                    receipt.space_id,
                    receipt.device_id,
                    receipt.mls_group_id,
                    receipt.key_version,
                    receipt.device_sig,
                    receipt.manifest_fingerprint,
                ),
            )

    def get(
        self,
        receipt_id: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> Receipt | None:
        with _resolve_connection(connection) as conn:
            row = conn.execute(
                (
                    "SELECT receipt_id, idem_key, wal_pos, commit_ts, tenant_id, space_id, device_id, "
                    "mls_group_id, key_version, device_sig, manifest_fingerprint FROM st_receipts WHERE receipt_id = ?"
                ),
                (receipt_id,),
            ).fetchone()
            if row is None:
                return None
            return Receipt(
                receipt_id=row["receipt_id"],
                idem_key=row["idem_key"],
                wal_pos=row["wal_pos"],
                commit_ts=row["commit_ts"],
                tenant_id=row["tenant_id"],
                space_id=row["space_id"],
                device_id=row["device_id"],
                mls_group_id=row["mls_group_id"],
                key_version=row["key_version"],
                device_sig=row["device_sig"],
                manifest_fingerprint=row["manifest_fingerprint"],
            )
