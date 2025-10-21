"""Connection pooling primitives for coordinating SQLite access."""

from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Mapping


@dataclass(frozen=True)
class PoolStats:
    """Introspection data describing the current pool state."""

    created: int
    available: int
    in_use: int


class SQLiteConnectionPool:
    """Lightweight thread-safe pool for SQLite connections."""

    def __init__(
        self,
        database_path: Path,
        *,
        max_size: int = 8,
        pragmas: Mapping[str, str | int] | None = None,
        busy_timeout_ms: int = 5_000,
    ) -> None:
        if max_size <= 0:
            msg = "max_size must be greater than zero"
            raise ValueError(msg)

        self._path = Path(database_path)
        if self._path.parent:
            self._path.parent.mkdir(parents=True, exist_ok=True)

        self._max_size = max_size
        self._pragmas: dict[str, str | int] = {
            "journal_mode": "WAL",
            "synchronous": "NORMAL",
            "temp_store": "MEMORY",
            "foreign_keys": 1,
        }
        if pragmas:
            for key, value in pragmas.items():
                self._pragmas[key] = value
        self._busy_timeout_ms = busy_timeout_ms

        self._condition = threading.Condition()
        self._available: list[sqlite3.Connection] = []
        self._created = 0
        self._in_use = 0
        self._closed = False

    def acquire(self, *, timeout: float | None = None) -> sqlite3.Connection:
        """Acquire a connection from the pool."""

        with self._condition:
            if self._closed:
                raise RuntimeError("Connection pool has been closed")

            remaining = timeout
            while True:
                if self._available:
                    connection = self._available.pop()
                    self._in_use += 1
                    return connection

                if self._created < self._max_size:
                    connection = self._create_connection()
                    self._in_use += 1
                    return connection

                if timeout is None:
                    self._condition.wait()
                    continue

                if remaining is None:
                    remaining = timeout

                if remaining <= 0:
                    raise TimeoutError("Timed out waiting for SQLite connection")

                start = time.monotonic()
                self._condition.wait(timeout=remaining)
                elapsed = time.monotonic() - start
                remaining = max(0.0, remaining - elapsed)

    def release(self, connection: sqlite3.Connection) -> None:
        """Return a connection to the pool."""

        with self._condition:
            if self._closed:
                connection.close()
                return

            try:
                connection.rollback()
            except sqlite3.ProgrammingError:
                # No active transaction.
                pass

            self._available.append(connection)
            self._in_use -= 1
            self._condition.notify()

    def close(self) -> None:
        """Close all idle connections and prevent further acquisition."""

        with self._condition:
            if self._closed:
                return
            self._closed = True
            while self._available:
                connection = self._available.pop()
                connection.close()
            self._condition.notify_all()

    def stats(self) -> PoolStats:
        """Expose current pool statistics for diagnostics and testing."""

        with self._condition:
            return PoolStats(
                created=self._created,
                available=len(self._available),
                in_use=self._in_use,
            )

    def _create_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self._path,
            detect_types=sqlite3.PARSE_DECLTYPES,
            check_same_thread=False,
        )
        cursor = connection.cursor()
        for pragma, value in self._pragmas.items():
            cursor.execute(f"PRAGMA {pragma}={value}")
        cursor.execute(f"PRAGMA busy_timeout={self._busy_timeout_ms}")
        cursor.close()
        connection.row_factory = sqlite3.Row
        self._created += 1
        return connection


_pool_lock = threading.Lock()
_pool: SQLiteConnectionPool | None = None


def configure_pool(
    database_path: Path,
    *,
    max_size: int = 8,
    pragmas: Mapping[str, str | int] | None = None,
    busy_timeout_ms: int = 5_000,
) -> None:
    """Initialise the global SQLite connection pool."""

    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
        _pool = SQLiteConnectionPool(
            database_path,
            max_size=max_size,
            pragmas=pragmas,
            busy_timeout_ms=busy_timeout_ms,
        )


def shutdown_pool() -> None:
    """Close and discard the global pool."""

    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
        _pool = None


def get_pool() -> SQLiteConnectionPool:
    """Return the configured pool or raise if missing."""

    with _pool_lock:
        if _pool is None:
            raise RuntimeError("Connection pool has not been configured")
        return _pool


@contextmanager
def connection_scope(*, timeout: float | None = None) -> Iterator[sqlite3.Connection]:
    """Yield a pooled SQLite connection."""

    pool = get_pool()
    connection = pool.acquire(timeout=timeout)
    try:
        yield connection
    finally:
        pool.release(connection)


__all__ = [
    "PoolStats",
    "SQLiteConnectionPool",
    "configure_pool",
    "connection_scope",
    "get_pool",
    "shutdown_pool",
]
