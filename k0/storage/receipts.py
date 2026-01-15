"""Receipt persistence adapter - Async PostgreSQL."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, AsyncIterator

from k0.db.connection import connection_scope

if TYPE_CHECKING:
    import asyncpg


def _format_timestamp(value: str | datetime | None) -> str | None:
    """Convert datetime to string for TEXT columns in PostgreSQL."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return value


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


@asynccontextmanager
async def _resolve_connection(
    connection: asyncpg.Connection | None,
) -> AsyncIterator[asyncpg.Connection]:
    """Resolve connection from provided or pool."""
    if connection is not None:
        yield connection
        return

    async with connection_scope() as pooled_connection:
        yield pooled_connection


class ReceiptStore:
    """Operations for persisting and retrieving receipts - PostgreSQL."""

    async def save(
        self,
        receipt: Receipt,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> None:
        """Save or update a receipt using upsert.

        Args:
            receipt: Receipt to persist
            connection: Optional existing connection
        """
        async with _resolve_connection(connection) as conn:
            await conn.execute(
                """
                INSERT INTO st_receipts (
                    receipt_id, idem_key, wal_pos, commit_ts, tenant_id,
                    space_id, device_id, mls_group_id, key_version,
                    device_sig, manifest_fingerprint
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (receipt_id) DO UPDATE SET
                    idem_key = EXCLUDED.idem_key,
                    wal_pos = EXCLUDED.wal_pos,
                    commit_ts = EXCLUDED.commit_ts,
                    tenant_id = EXCLUDED.tenant_id,
                    space_id = EXCLUDED.space_id,
                    device_id = EXCLUDED.device_id,
                    mls_group_id = EXCLUDED.mls_group_id,
                    key_version = EXCLUDED.key_version,
                    device_sig = EXCLUDED.device_sig,
                    manifest_fingerprint = EXCLUDED.manifest_fingerprint
                """,
                receipt.receipt_id,
                receipt.idem_key,
                receipt.wal_pos,
                _format_timestamp(receipt.commit_ts),
                receipt.tenant_id,
                receipt.space_id,
                receipt.device_id,
                receipt.mls_group_id,
                receipt.key_version,
                receipt.device_sig,
                receipt.manifest_fingerprint,
            )

    async def get(
        self,
        receipt_id: str,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> Receipt | None:
        """Get a receipt by ID.

        Args:
            receipt_id: The receipt ID to retrieve
            connection: Optional existing connection

        Returns:
            Receipt if found, None otherwise
        """
        async with _resolve_connection(connection) as conn:
            row = await conn.fetchrow(
                """
                SELECT receipt_id, idem_key, wal_pos, commit_ts, tenant_id, space_id,
                       device_id, mls_group_id, key_version, device_sig, manifest_fingerprint
                FROM st_receipts
                WHERE receipt_id = $1
                """,
                receipt_id,
            )

        if row is None:
            return None

        return Receipt(
            receipt_id=row["receipt_id"],
            idem_key=row["idem_key"],
            wal_pos=row["wal_pos"],
            commit_ts=str(row["commit_ts"]) if row["commit_ts"] else "",
            tenant_id=row["tenant_id"],
            space_id=row["space_id"],
            device_id=row["device_id"],
            mls_group_id=row["mls_group_id"],
            key_version=row["key_version"],
            device_sig=row["device_sig"],
            manifest_fingerprint=row["manifest_fingerprint"],
        )
