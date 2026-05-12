"""
k1.tools.family.storage -- ``K1FamilyStore`` SQLite wrapper.

The store owns a single ``sqlite3.Connection`` shared across every
family-tool service in a kernel process.  Sharing one connection (with
WAL journaling) is correct because:

* Every action runs sequentially on the asyncio event loop -- no
  inter-thread contention from the family-tool layer itself.
* SQLite's WAL mode allows concurrent readers from background tasks
  (cold-sync, eval harness) without blocking the loop.
* Foreign-key enforcement is enabled so adapter DDL can declare proper
  cross-table relationships.
* The store does NOT own per-adapter DDL -- each ``BaseToolService``
  applies its own ``ToolDefinition.tables_sql`` at construction time
  against this shared connection.

Plan reference: ``docs/plans/KERNEL_BOOTUP_PLAN.md`` §E15.0.10 (Step A).
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default on-disk location for the K1-hot family tools database.  Kept
# under ``data/`` to live alongside the other K1 SQLite stores; callers
# can override per-process via the ``db_path`` argument.
DEFAULT_DB_PATH: str = "data/k1_family.db"


class K1FamilyStore:
    """Thin, shared sqlite3 connection holder for the family-tool layer."""

    __slots__ = ("_db_path", "_conn")

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self._db_path = db_path
        # Ensure the parent directory exists; sqlite3 will not mkdir for us.
        Path(self._db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)

        self._conn: Optional[sqlite3.Connection] = sqlite3.connect(
            self._db_path,
            check_same_thread=False,
            isolation_level=None,  # autocommit; per-transaction control via ``with conn:``
            timeout=5.0,
        )
        # Pragmas: WAL for concurrent readers, FK enforcement on, modest
        # busy timeout so transient writer contention does not raise.
        self._conn.execute("PRAGMA journal_mode = WAL;")
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._conn.execute("PRAGMA busy_timeout = 5000;")
        self._conn.row_factory = sqlite3.Row

        logger.info("K1FamilyStore: opened sqlite at %s (WAL, FK=ON)", self._db_path)

    # ------------------------------------------------------------------ #
    # Accessors
    # ------------------------------------------------------------------ #

    @property
    def conn(self) -> sqlite3.Connection:
        """Return the shared sqlite3 connection.

        Raises ``RuntimeError`` if the store has already been closed.
        """

        if self._conn is None:
            raise RuntimeError("K1FamilyStore.conn requested after close()")
        return self._conn

    @property
    def db_path(self) -> str:
        """Return the on-disk path the store was opened at."""

        return self._db_path

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def close(self) -> None:
        """Close the underlying connection (idempotent)."""

        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None
                logger.info("K1FamilyStore: closed sqlite at %s", self._db_path)
