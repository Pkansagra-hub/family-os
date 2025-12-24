"""Subscriber offset storage - Async PostgreSQL."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, AsyncIterator

from k0.db.connection import connection_scope

if TYPE_CHECKING:
    import asyncpg


@dataclass(slots=True)
class Offset:
    subscriber_id: str
    topic: str
    space_id: str
    tenant_id: str
    offset: int
    updated_ts: str


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


class OffsetStore:
    """Persistence surface for subscriber offsets - PostgreSQL."""

    async def upsert(
        self,
        record: Offset,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> None:
        """Upsert a subscriber offset.

        Args:
            record: Offset record to persist
            connection: Optional existing connection
        """
        async with _resolve_connection(connection) as conn:
            await conn.execute(
                """
                INSERT INTO st_offsets (
                    subscriber_id, topic, space_id, tenant_id, "offset", updated_ts
                ) VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (subscriber_id, topic, space_id, tenant_id) DO UPDATE SET
                    "offset" = EXCLUDED."offset",
                    updated_ts = EXCLUDED.updated_ts
                """,
                record.subscriber_id,
                record.topic,
                record.space_id,
                record.tenant_id,
                record.offset,
                record.updated_ts,
            )

    async def fetch(
        self,
        subscriber_id: str,
        topic: str,
        space_id: str,
        tenant_id: str,
        *,
        connection: asyncpg.Connection | None = None,
    ) -> Offset | None:
        """Fetch a subscriber offset.

        Args:
            subscriber_id: Subscriber identifier
            topic: Topic name
            space_id: Space identifier
            tenant_id: Tenant identifier
            connection: Optional existing connection

        Returns:
            Offset if found, None otherwise
        """
        async with _resolve_connection(connection) as conn:
            row = await conn.fetchrow(
                """
                SELECT subscriber_id, topic, space_id, tenant_id, "offset", updated_ts
                FROM st_offsets
                WHERE subscriber_id = $1 AND topic = $2 AND space_id = $3 AND tenant_id = $4
                """,
                subscriber_id,
                topic,
                space_id,
                tenant_id,
            )

        if row is None:
            return None

        return Offset(
            subscriber_id=row["subscriber_id"],
            topic=row["topic"],
            space_id=row["space_id"],
            tenant_id=row["tenant_id"],
            offset=row["offset"],
            updated_ts=str(row["updated_ts"]) if row["updated_ts"] else "",
        )
