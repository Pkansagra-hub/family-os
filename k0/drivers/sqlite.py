"""SQLite driver for ACID operations (K0 infrastructure + memory tables).

This driver implements the K0 Driver SPI (see K0 README §7) for SQLite backend.
It handles all ACID cohort operations: WAL, receipts, outbox, memory tables.

Architecture:
- ACID transactions via begin/commit/rollback
- WAL mode for durability
- Connection pooling for multi-threaded access
- Observability: cognitive_trace_id in all operations

Related ADRs:
- K0 README §6.1: Storage Contract
- K0 README §7: Driver SPI & Alias Map
- Migration 0006: Memory tables (st_epi, st_sem, st_proc, st_social, st_hipp_store, self_*)
- Migration 0007: Core directory tables (people, households)
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from k0.storage.outbox import OutboxEntry

logger = logging.getLogger(__name__)


class SQLiteDriver:
    """SQLite driver for ACID operations (K0 infrastructure + memory tables).

    Implements Driver SPI contract:
    - ACID cohort: open(config) → handle, begin/commit/rollback(handle), append/read/scan
    - Connection lifecycle: connect → begin → append/read/scan → commit/rollback → close

    Storage responsibilities:
    - K0 infrastructure: st_wal, st_receipts, st_outbox, st_dlq, idem_ledger, st_devices, schema_registry
    - Memory tables: st_hipp_store, st_epi, st_sem, st_ws, st_proc, st_social
    - Self-model tables: self_traits, self_preferences, self_health, self_roles
    - Core directory: people, households
    """

    def __init__(self, database_path: Path, cognitive_trace_id: str | None = None) -> None:
        """Initialize SQLite driver with database path.

        Args:
            database_path: Path to SQLite database file
            cognitive_trace_id: Optional trace ID for observability
        """
        self.database_path = database_path
        self.cognitive_trace_id = cognitive_trace_id
        self.conn: sqlite3.Connection | None = None
        self._in_transaction = False
        logger.info(
            "SQLiteDriver initialized",
            extra={
                "database_path": str(database_path),
                "cognitive_trace_id": cognitive_trace_id,
            },
        )

    def connect(self) -> None:
        """Open SQLite connection with WAL mode and optimal settings.

        Configuration:
        - WAL mode: Durable writes with async checkpointing
        - synchronous=NORMAL: Balance durability and performance
        - temp_store=MEMORY: Faster temporary tables
        - busy_timeout=5000: Retry on lock contention
        - Row factory: Dict-like row access

        Raises:
            RuntimeError: If connection already established
            sqlite3.Error: On database connection failure
        """
        if self.conn is not None:
            raise RuntimeError("Connection already established")

        try:
            self.conn = sqlite3.connect(
                self.database_path,
                check_same_thread=False,  # Allow multi-threaded access
                isolation_level=None,  # Manual transaction control
            )
            # Configure WAL mode and performance settings
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.execute("PRAGMA temp_store=MEMORY")
            self.conn.execute("PRAGMA busy_timeout=5000")
            self.conn.execute("PRAGMA foreign_keys=OFF")  # K0 invariants enforced by Ward harness

            # Enable dict-like row access
            self.conn.row_factory = sqlite3.Row

            logger.info(
                "SQLite connection established",
                extra={
                    "database_path": str(self.database_path),
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
        except sqlite3.Error as e:
            logger.error(
                "Failed to connect to SQLite",
                extra={
                    "database_path": str(self.database_path),
                    "error": str(e),
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
            raise

    def begin(self) -> None:
        """Start ACID transaction.

        Raises:
            RuntimeError: If connection not established or transaction already active
            sqlite3.Error: On transaction begin failure
        """
        if not self.conn:
            raise RuntimeError("Connection not established")
        if self._in_transaction:
            raise RuntimeError("Transaction already active")

        try:
            self.conn.execute("BEGIN")
            self._in_transaction = True
            logger.debug(
                "Transaction started",
                extra={"cognitive_trace_id": self.cognitive_trace_id},
            )
        except sqlite3.Error as e:
            logger.error(
                "Failed to begin transaction",
                extra={"error": str(e), "cognitive_trace_id": self.cognitive_trace_id},
            )
            raise

    def commit(self) -> None:
        """Commit ACID transaction.

        Raises:
            RuntimeError: If connection not established or no transaction active
            sqlite3.Error: On commit failure
        """
        if not self.conn:
            raise RuntimeError("Connection not established")
        if not self._in_transaction:
            raise RuntimeError("No transaction active")

        try:
            self.conn.commit()
            self._in_transaction = False
            logger.debug(
                "Transaction committed",
                extra={"cognitive_trace_id": self.cognitive_trace_id},
            )
        except sqlite3.Error as e:
            logger.error(
                "Failed to commit transaction",
                extra={"error": str(e), "cognitive_trace_id": self.cognitive_trace_id},
            )
            raise

    def rollback(self) -> None:
        """Rollback ACID transaction.

        Raises:
            RuntimeError: If connection not established or no transaction active
            sqlite3.Error: On rollback failure
        """
        if not self.conn:
            raise RuntimeError("Connection not established")
        if not self._in_transaction:
            raise RuntimeError("No transaction active")

        try:
            self.conn.rollback()
            self._in_transaction = False
            logger.debug(
                "Transaction rolled back",
                extra={"cognitive_trace_id": self.cognitive_trace_id},
            )
        except sqlite3.Error as e:
            logger.error(
                "Failed to rollback transaction",
                extra={"error": str(e), "cognitive_trace_id": self.cognitive_trace_id},
            )
            raise

    def append(self, table: str, data: dict[str, Any]) -> int:
        """Insert row into table (for outbox → driver → SQLite flow).

        Args:
            table: Table name (st_epi, st_sem, st_wal, etc.)
            data: Column-value dict for INSERT

        Returns:
            int: Row ID of inserted row (lastrowid)

        Raises:
            RuntimeError: If connection not established or lastrowid is None
            sqlite3.Error: On insert failure
        """
        if not self.conn:
            raise RuntimeError("Connection not established")

        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?" for _ in data])
        values = list(data.values())

        try:
            cursor = self.conn.execute(
                f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                values,
            )
            row_id = cursor.lastrowid
            if row_id is None:
                raise RuntimeError(f"Failed to get lastrowid for table {table}")
            logger.debug(
                "Row inserted",
                extra={
                    "table": table,
                    "row_id": row_id,
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
            return row_id
        except sqlite3.Error as e:
            logger.error(
                "Failed to append row",
                extra={
                    "table": table,
                    "error": str(e),
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
            raise

    def read(self, table: str, query: dict[str, Any]) -> list[dict[str, Any]]:
        """Read rows from table (for P01 recall queries).

        Args:
            table: Table name (st_epi, st_sem, etc.)
            query: WHERE clause filters as dict (column: value)

        Returns:
            List of rows as dicts

        Raises:
            RuntimeError: If connection not established
            sqlite3.Error: On query failure
        """
        if not self.conn:
            raise RuntimeError("Connection not established")

        where_clause = " AND ".join([f"{k} = ?" for k in query.keys()])
        values = list(query.values())

        try:
            cursor = self.conn.execute(
                f"SELECT * FROM {table} WHERE {where_clause}",
                values,
            )
            rows = [dict(row) for row in cursor.fetchall()]
            logger.debug(
                "Rows read",
                extra={
                    "table": table,
                    "row_count": len(rows),
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
            return rows
        except sqlite3.Error as e:
            logger.error(
                "Failed to read rows",
                extra={
                    "table": table,
                    "error": str(e),
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
            raise

    def scan(self, table: str, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """Scan table with pagination (for bulk queries).

        Args:
            table: Table name
            limit: Maximum rows to return (default 100)
            offset: Starting row offset (default 0)

        Returns:
            List of rows as dicts

        Raises:
            RuntimeError: If connection not established
            sqlite3.Error: On query failure
        """
        if not self.conn:
            raise RuntimeError("Connection not established")

        try:
            cursor = self.conn.execute(
                f"SELECT * FROM {table} LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = [dict(row) for row in cursor.fetchall()]
            logger.debug(
                "Table scanned",
                extra={
                    "table": table,
                    "limit": limit,
                    "offset": offset,
                    "row_count": len(rows),
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
            return rows
        except sqlite3.Error as e:
            logger.error(
                "Failed to scan table",
                extra={
                    "table": table,
                    "error": str(e),
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
            raise

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> sqlite3.Cursor:
        """Execute arbitrary SQL query (for advanced operations).

        Args:
            sql: SQL query string
            params: Optional query parameters

        Returns:
            sqlite3.Cursor: Query result cursor

        Raises:
            RuntimeError: If connection not established
            sqlite3.Error: On query failure
        """
        if not self.conn:
            raise RuntimeError("Connection not established")

        try:
            cursor = self.conn.execute(sql, params or ())
            logger.debug(
                "SQL executed",
                extra={
                    "sql": sql[:100],  # Log first 100 chars
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
            return cursor
        except sqlite3.Error as e:
            logger.error(
                "Failed to execute SQL",
                extra={
                    "sql": sql[:100],
                    "error": str(e),
                    "cognitive_trace_id": self.cognitive_trace_id,
                },
            )
            raise

    def close(self) -> None:
        """Close SQLite connection.

        Raises:
            sqlite3.Error: On connection close failure
        """
        if self.conn:
            try:
                if self._in_transaction:
                    logger.warning(
                        "Closing connection with active transaction, rolling back",
                        extra={"cognitive_trace_id": self.cognitive_trace_id},
                    )
                    self.conn.rollback()
                    self._in_transaction = False

                self.conn.close()
                self.conn = None
                logger.info(
                    "SQLite connection closed",
                    extra={
                        "database_path": str(self.database_path),
                        "cognitive_trace_id": self.cognitive_trace_id,
                    },
                )
            except sqlite3.Error as e:
                logger.error(
                    "Failed to close connection",
                    extra={
                        "error": str(e),
                        "cognitive_trace_id": self.cognitive_trace_id,
                    },
                )
                raise

    def __enter__(self) -> "SQLiteDriver":
        """Context manager entry: connect and begin transaction."""
        self.connect()
        self.begin()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit: commit or rollback, then close."""
        if exc_type is not None:
            # Exception occurred, rollback
            if self._in_transaction:
                self.rollback()
        else:
            # Success, commit
            if self._in_transaction:
                self.commit()
        self.close()

    def apply(self, entry: OutboxEntry) -> None:
        """Apply outbox entry to SQLite (Driver SPI requirement).

        This method is called by the outbox worker to process async operations.
        Currently a placeholder - full implementation pending.

        Args:
            entry: Outbox entry containing wal_pos, tenant_id, space_id, payload, etc.

        Raises:
            NotImplementedError: Full outbox integration not yet implemented
        """
        logger.warning(
            "SQLite driver outbox apply called but not yet implemented",
            extra={
                "driver": entry.driver,
                "op_kind": entry.op_kind,
                "wal_pos": entry.wal_pos,
                "cognitive_trace_id": self.cognitive_trace_id,
            },
        )
        # TODO: Parse entry.payload and route to appropriate operation
        # For now, no-op to avoid crashing the outbox worker


# Factory function for outbox worker compatibility
def build_driver() -> SQLiteDriver:
    """Factory function to create SQLiteDriver instance.

    Returns a SQLiteDriver with default configuration for outbox processing.
    Uses K0_DB_PATH from environment or default path.

    Returns:
        SQLiteDriver: Configured driver instance
    """
    import os
    from pathlib import Path

    db_path = Path(os.getenv("K0_DB_PATH", "/data/k0_kernel.db"))
    return SQLiteDriver(database_path=db_path)
