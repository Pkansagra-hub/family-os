"""PostgreSQL driver for ACID operations (K0 infrastructure + memory tables).

This driver implements the K0 Driver SPI (see K0 README §7) for PostgreSQL backend.
It handles all ACID cohort operations: WAL, receipts, outbox, memory tables.

Architecture:
- ACID transactions via begin/commit/rollback
- Connection pooling via asyncpg
- Observability: cognitive_trace_id in all operations

Related ADRs:
- K0 README §6.1: Storage Contract
- K0 README §7: Driver SPI & Alias Map
    - Migration 0006: Legacy memory tables (st_epi, st_sem, st_proc, st_social, st_hipp_store, self_*)
- Migration 0007: Core directory tables (people, households)
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import asyncpg

    from k0.storage.outbox import OutboxEntry

logger = logging.getLogger(__name__)

# Global bus dispatcher reference (injected during app startup)
_bus_dispatcher_ref: Any | None = None
_bus_loop_ref: asyncio.AbstractEventLoop | None = None


def set_bus_dispatcher(dispatcher: Any) -> None:
    """
    Inject bus dispatcher reference for outbox-to-bus bridging.

    Called during kernel startup (k0/kernel/app.py) to enable outbox worker
    to publish events to the bus for pipeline processing.

    Args:
        dispatcher: BusDispatcher instance from kernel app state
    """
    global _bus_dispatcher_ref, _bus_loop_ref
    _bus_dispatcher_ref = dispatcher
    try:
        _bus_loop_ref = asyncio.get_running_loop()
    except RuntimeError:
        pass


class PostgresDriver:
    """PostgreSQL driver for ACID operations (K0 infrastructure + memory tables).

    Implements Driver SPI contract:
    - ACID cohort: open(config) → handle, begin/commit/rollback(handle), append/read/scan
    - Connection lifecycle: connect → begin → append/read/scan → commit/rollback → close

    Storage responsibilities:
    - K0 infrastructure: st_wal, st_receipts, st_outbox, st_dlq, idem_ledger, st_devices, schema_registry
    - Memory tables (legacy): st_hipp_store, st_epi, st_sem, st_ws, st_proc, st_social
    - Canonical episodic events: st_hipp_events
    - Self-model tables: self_traits, self_preferences, self_health, self_roles
    - Core directory: people, households
    """

    def __init__(self, dsn: str, cognitive_trace_id: str | None = None) -> None:
        """Initialize PostgreSQL driver with connection DSN.

        Args:
            dsn: PostgreSQL connection string (e.g., postgresql://user:pass@host:port/db)
            cognitive_trace_id: Optional trace ID for observability
        """
        self.dsn = dsn
        self.cognitive_trace_id = cognitive_trace_id
        self.conn: "asyncpg.Connection | None" = None
        self._transaction: "asyncpg.Transaction | None" = None
        self._in_transaction = False
        logger.info(
            "PostgresDriver initialized",
            extra={
                "dsn": self._safe_dsn(),
                "cognitive_trace_id": cognitive_trace_id,
            },
        )

    def _safe_dsn(self) -> str:
        """Return DSN with password masked for logging."""
        import re

        return re.sub(r":([^:@]+)@", r":***@", self.dsn)

    async def connect(self) -> None:
        """Open PostgreSQL connection.

        Configuration:
        - Uses asyncpg for high-performance async access
        - Connection parameters optimized for transactional workloads

        Raises:
            RuntimeError: If connection already established
            asyncpg.PostgresError: On database connection failure
        """
        import asyncpg as asyncpg_module

        if self.conn is not None:
            raise RuntimeError("Connection already established")

        try:
            self.conn = await asyncpg_module.connect(self.dsn)

            logger.info(
                "PostgreSQL connection established",
                extra={
                    "dsn": self._safe_dsn(),
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
        except asyncpg_module.PostgresError as e:
            logger.error(
                "Failed to connect to PostgreSQL",
                extra={
                    "dsn": self._safe_dsn(),
                    "error": str(e),
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
            raise

    async def begin(self) -> None:
        """Start ACID transaction.

        Raises:
            RuntimeError: If connection not established or transaction already active
            asyncpg.PostgresError: On transaction begin failure
        """
        import asyncpg as asyncpg_module

        if not self.conn:
            raise RuntimeError("Connection not established")
        if self._in_transaction:
            raise RuntimeError("Transaction already active")

        try:
            self._transaction = self.conn.transaction()
            await self._transaction.start()
            self._in_transaction = True
            logger.debug(
                "Transaction started",
                extra={"cognitive_trace_id": self.cognitive_trace_id},
            )
        except asyncpg_module.PostgresError as e:
            logger.error(
                "Failed to begin transaction",
                extra={"error": str(e), "cognitive_trace_id": self.cognitive_trace_id},
            )
            raise

    async def commit(self) -> None:
        """Commit ACID transaction.

        Raises:
            RuntimeError: If connection not established or no transaction active
            asyncpg.PostgresError: On commit failure
        """
        import asyncpg as asyncpg_module

        if not self.conn:
            raise RuntimeError("Connection not established")
        if not self._in_transaction or self._transaction is None:
            raise RuntimeError("No transaction active")

        try:
            await self._transaction.commit()
            self._in_transaction = False
            self._transaction = None
            logger.debug(
                "Transaction committed",
                extra={"cognitive_trace_id": self.cognitive_trace_id},
            )
        except asyncpg_module.PostgresError as e:
            logger.error(
                "Failed to commit transaction",
                extra={"error": str(e), "cognitive_trace_id": self.cognitive_trace_id},
            )
            raise

    async def rollback(self) -> None:
        """Rollback ACID transaction.

        Raises:
            RuntimeError: If connection not established or no transaction active
            asyncpg.PostgresError: On rollback failure
        """
        import asyncpg as asyncpg_module

        if not self.conn:
            raise RuntimeError("Connection not established")
        if not self._in_transaction or self._transaction is None:
            raise RuntimeError("No transaction active")

        try:
            await self._transaction.rollback()
            self._in_transaction = False
            self._transaction = None
            logger.debug(
                "Transaction rolled back",
                extra={"cognitive_trace_id": self.cognitive_trace_id},
            )
        except asyncpg_module.PostgresError as e:
            logger.error(
                "Failed to rollback transaction",
                extra={"error": str(e), "cognitive_trace_id": self.cognitive_trace_id},
            )
            raise

    async def append(self, table: str, data: dict[str, Any]) -> int:
        """Insert row into table (for outbox → driver → PostgreSQL flow).

        Args:
            table: Table name (st_epi, st_sem, st_wal, etc.)
            data: Column-value dict for INSERT

        Returns:
            int: Row ID of inserted row (using RETURNING id)

        Raises:
            RuntimeError: If connection not established
            asyncpg.PostgresError: On insert failure
        """
        import asyncpg as asyncpg_module

        if not self.conn:
            raise RuntimeError("Connection not established")

        columns = ", ".join(data.keys())
        placeholders = ", ".join([f"${i+1}" for i in range(len(data))])
        values = list(data.values())

        try:
            row = await self.conn.fetchrow(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) RETURNING id",
                *values,
            )
            if row is None:
                raise RuntimeError(f"Failed to get row id for table {table}")
            row_id = row["id"]
            logger.debug(
                "Row inserted",
                extra={
                    "table": table,
                    "row_id": row_id,
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
            return row_id
        except asyncpg_module.PostgresError as e:
            logger.error(
                "Failed to append row",
                extra={
                    "table": table,
                    "error": str(e),
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
            raise

    async def read(self, table: str, query: dict[str, Any]) -> list[dict[str, Any]]:
        """Read rows from table (for P01 recall queries).

        Args:
            table: Table name (st_epi, st_sem, etc.)
            query: WHERE clause filters as dict (column: value)

        Returns:
            List of rows as dicts

        Raises:
            RuntimeError: If connection not established
            asyncpg.PostgresError: On query failure
        """
        import asyncpg as asyncpg_module

        if not self.conn:
            raise RuntimeError("Connection not established")

        where_parts = []
        values = []
        for i, (k, v) in enumerate(query.items()):
            where_parts.append(f"{k} = ${i+1}")
            values.append(v)
        where_clause = " AND ".join(where_parts)

        try:
            rows = await self.conn.fetch(
                f"SELECT * FROM {table} WHERE {where_clause}",
                *values,
            )
            result = [dict(row) for row in rows]
            logger.debug(
                "Rows read",
                extra={
                    "table": table,
                    "row_count": len(result),
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
            return result
        except asyncpg_module.PostgresError as e:
            logger.error(
                "Failed to read rows",
                extra={
                    "table": table,
                    "error": str(e),
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
            raise

    async def scan(self, table: str, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """Scan table with pagination (for bulk queries).

        Args:
            table: Table name
            limit: Maximum rows to return (default 100)
            offset: Starting row offset (default 0)

        Returns:
            List of rows as dicts

        Raises:
            RuntimeError: If connection not established
            asyncpg.PostgresError: On query failure
        """
        import asyncpg as asyncpg_module

        if not self.conn:
            raise RuntimeError("Connection not established")

        try:
            rows = await self.conn.fetch(
                f"SELECT * FROM {table} LIMIT $1 OFFSET $2",
                limit,
                offset,
            )
            result = [dict(row) for row in rows]
            logger.debug(
                "Table scanned",
                extra={
                    "table": table,
                    "limit": limit,
                    "offset": offset,
                    "row_count": len(result),
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
            return result
        except asyncpg_module.PostgresError as e:
            logger.error(
                "Failed to scan table",
                extra={
                    "table": table,
                    "error": str(e),
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
            raise

    async def execute(self, sql: str, *params: Any) -> str:
        """Execute arbitrary SQL query (for advanced operations).

        Args:
            sql: SQL query string with $N placeholders
            params: Query parameters

        Returns:
            str: Query result status (e.g., "SELECT 10", "INSERT 0 1")

        Raises:
            RuntimeError: If connection not established
            asyncpg.PostgresError: On query failure
        """
        import asyncpg as asyncpg_module

        if not self.conn:
            raise RuntimeError("Connection not established")

        try:
            result = await self.conn.execute(sql, *params)
            logger.debug(
                "SQL executed",
                extra={
                    "sql": sql[:100],  # Log first 100 chars
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
            return result
        except asyncpg_module.PostgresError as e:
            logger.error(
                "Failed to execute SQL",
                extra={
                    "sql": sql[:100],
                    "error": str(e),
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
            raise

    async def fetch(self, sql: str, *params: Any) -> list[dict[str, Any]]:
        """Execute SQL query and return rows as dicts.

        Args:
            sql: SQL query string with $N placeholders
            params: Query parameters

        Returns:
            List of rows as dicts

        Raises:
            RuntimeError: If connection not established
            asyncpg.PostgresError: On query failure
        """
        import asyncpg as asyncpg_module

        if not self.conn:
            raise RuntimeError("Connection not established")

        try:
            rows = await self.conn.fetch(sql, *params)
            result = [dict(row) for row in rows]
            logger.debug(
                "SQL fetched",
                extra={
                    "sql": sql[:100],
                    "row_count": len(result),
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
            return result
        except asyncpg_module.PostgresError as e:
            logger.error(
                "Failed to fetch SQL",
                extra={
                    "sql": sql[:100],
                    "error": str(e),
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
            raise

    async def fetchrow(self, sql: str, *params: Any) -> dict[str, Any] | None:
        """Execute SQL query and return single row as dict.

        Args:
            sql: SQL query string with $N placeholders
            params: Query parameters

        Returns:
            Single row as dict, or None if no rows

        Raises:
            RuntimeError: If connection not established
            asyncpg.PostgresError: On query failure
        """
        import asyncpg as asyncpg_module

        if not self.conn:
            raise RuntimeError("Connection not established")

        try:
            row = await self.conn.fetchrow(sql, *params)
            result = dict(row) if row else None
            logger.debug(
                "SQL fetchrow",
                extra={
                    "sql": sql[:100],
                    "found": result is not None,
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
            return result
        except asyncpg_module.PostgresError as e:
            logger.error(
                "Failed to fetchrow SQL",
                extra={
                    "sql": sql[:100],
                    "error": str(e),
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
            raise

    async def close(self) -> None:
        """Close PostgreSQL connection.

        Raises:
            asyncpg.PostgresError: On connection close failure
        """
        import asyncpg as asyncpg_module

        if self.conn:
            try:
                if self._in_transaction and self._transaction is not None:
                    logger.warning(
                        "Closing connection with active transaction, rolling back",
                        extra={"cognitive_trace_id": self.cognitive_trace_id},
                    )
                    await self._transaction.rollback()
                    self._in_transaction = False
                    self._transaction = None

                await self.conn.close()
                self.conn = None
                logger.info(
                    "PostgreSQL connection closed",
                    extra={
                        "dsn": self._safe_dsn(),
                        "cognitive_trace_id": self.cognitive_trace_id,
                    },
                )
            except asyncpg_module.PostgresError as e:
                logger.error(
                    "Failed to close connection",
                    extra={
                        "error": str(e),
                        "cognitive_trace_id": self.cognitive_trace_id,
                    },
                )
                raise

    async def __aenter__(self) -> "PostgresDriver":
        """Async context manager entry: connect and begin transaction."""
        await self.connect()
        await self.begin()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit: commit or rollback, then close."""
        if exc_type is not None:
            # Exception occurred, rollback
            if self._in_transaction:
                await self.rollback()
        else:
            # Success, commit
            if self._in_transaction:
                await self.commit()
        await self.close()

    async def apply(self, entry: "OutboxEntry") -> None:
        """Apply outbox entry to PostgreSQL (Driver SPI requirement).

        This method is called by the outbox worker to process async operations.
        For st_epi driver, this publishes events to the bus for pipeline processing.

        Args:
            entry: Outbox entry containing wal_pos, tenant_id, space_id, payload, etc.

        Flow:
            1. Parse payload (JSON envelope from WAL)
            2. Create BusMessage with topic routing
            3. Publish to bus dispatcher → triggers P02 pipeline
            4. P02 executes 14 modules → writes to st_hipp_events
        """
        import json

        # Only handle st_epi driver (episodic memory write path)
        if entry.driver != "st_epi":
            logger.debug(
                f"Skipping non-st_epi driver: {entry.driver}",
                extra={"driver": entry.driver, "wal_pos": entry.wal_pos},
            )
            return

        try:
            # Parse envelope from payload
            envelope = json.loads(entry.payload.decode("utf-8"))

            # Get bus dispatcher from global reference (set during app startup)
            bus_dispatcher = _bus_dispatcher_ref
            if bus_dispatcher is None:
                logger.error(
                    "Bus dispatcher not available - cannot publish envelope",
                    extra={
                        "wal_pos": entry.wal_pos,
                        "driver": entry.driver,
                        "cognitive_trace_id": envelope.get("cognitive_trace_id"),
                    },
                )
                return

            # Import BusMessage here to avoid circular imports
            from k0.bus.core import BusMessage

            # Use bus_topic from outbox payload (set by TopicRouter in command.py)
            # Falls back to legacy mapping for backward compatibility
            bus_topic = envelope.get("bus_topic")
            if not bus_topic:
                # Legacy fallback: map command topic to pipeline bus topic
                raw_topic = envelope.get("topic", "memory.delta")
                if raw_topic in ("memory.delta", "memory.write"):
                    bus_topic = "cognitive.memory.write.committed.v1"
                else:
                    bus_topic = raw_topic

            bus_message = BusMessage(
                topic=bus_topic,
                payload=json.dumps(envelope).encode("utf-8"),
                offset=entry.wal_pos,
                trace_id=envelope.get("cognitive_trace_id"),
                space_id=entry.space_id,
                metadata={
                    "driver": entry.driver,
                    "tenant_id": entry.tenant_id,
                    "band": envelope.get("band", "GREEN"),
                },
            )

            # Publish to bus (this will trigger P02 pipeline asynchronously)
            await bus_dispatcher.dispatch([bus_message])

            logger.debug(
                "Published envelope to bus for P02 processing",
                extra={
                    "wal_pos": entry.wal_pos,
                    "bus_topic": bus_topic,
                    "command_topic": envelope.get("topic"),
                    "cognitive_trace_id": envelope.get("cognitive_trace_id"),
                },
            )

        except json.JSONDecodeError:
            logger.error(
                "Failed to decode outbox payload as JSON",
                extra={
                    "wal_pos": entry.wal_pos,
                    "driver": entry.driver,
                },
                exc_info=True,
            )
        except Exception:
            logger.exception(
                "Failed to apply outbox entry",
                extra={
                    "wal_pos": entry.wal_pos,
                    "driver": entry.driver,
                },
            )


async def build_driver() -> PostgresDriver:
    """Factory function to create PostgresDriver instance.

    Returns a PostgresDriver with default configuration for outbox processing.
    Uses K0_DATABASE_URL from environment.

    Returns:
        PostgresDriver: Configured driver instance
    """
    import os

    dsn = os.getenv("K0_DATABASE_URL", "postgresql://k0:k0@localhost:5432/k0")
    return PostgresDriver(dsn=dsn)
    return PostgresDriver(dsn=dsn)
    return PostgresDriver(dsn=dsn)
    return PostgresDriver(dsn=dsn)
    return PostgresDriver(dsn=dsn)
    return PostgresDriver(dsn=dsn)
