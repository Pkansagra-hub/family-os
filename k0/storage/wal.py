"""Write-ahead log adapter."""

from __future__ import annotations

import errno
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterator, List, Literal, Set

from k0.uow.connection_pool import connection_scope


@dataclass(slots=True)
class WalEntry:
    """Domain representation of a WAL row."""

    tenant_id: str
    space_id: str
    topic: str
    envelope_json: str
    schema_uri: str
    schema_version: str
    device_id: str
    commit_ts: str
    body: bytes | None = None
    payload_sha256: str | None = None
    idem_key: str | None = None
    position: int | None = None


@dataclass(slots=True)
class WalBacklogStats:
    """Aggregate backlog information for a WAL topic scope."""

    pending_events: int
    latest_position: int | None
    latest_commit_ts: str | None


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


def _fsync_path(
    path: Path,
    chaos_config: Any | None = None,
    metrics_exporter: Any | None = None,
) -> None:
    """Flush file to disk with optional chaos injection.

    Args:
        path: File path to fsync
        chaos_config: Optional ChaosSettings for fault injection
        metrics_exporter: Optional MetricsExporter for telemetry

    Raises:
        OSError: If fsync fails (real or chaos-injected)
    """
    # Chaos injection check (before real fsync)
    if chaos_config is not None and chaos_config.enabled:
        from k0.chaos.toggles import should_fail_fsync

        decision = should_fail_fsync(chaos_config, metrics_exporter)
        if decision.should_inject:
            raise OSError(errno.EIO, "Chaos-injected fsync failure", str(path))

    # Normal fsync path
    binary_flag = os.O_BINARY if hasattr(os, "O_BINARY") else 0
    try:
        fd = os.open(str(path), os.O_RDWR | binary_flag)
    except OSError as exc:
        if exc.errno not in (errno.EACCES, errno.EROFS):
            raise
        fd = os.open(str(path), os.O_RDONLY | binary_flag)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class WriteAheadLog:
    """Abstraction over the `st_wal` SQLite table."""

    def append(
        self, entry: WalEntry, *, connection: sqlite3.Connection | None = None
    ) -> int:
        insert_entry = replace(entry)
        with _resolve_connection(connection) as conn:
            cursor = conn.execute(
                (
                    "INSERT INTO st_wal (tenant_id, space_id, topic, envelope_json, body, "
                    "payload_sha256, schema_uri, schema_version, idem_key, device_id, commit_ts) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                ),
                (
                    insert_entry.tenant_id,
                    insert_entry.space_id,
                    insert_entry.topic,
                    insert_entry.envelope_json,
                    insert_entry.body,
                    insert_entry.payload_sha256,
                    insert_entry.schema_uri,
                    insert_entry.schema_version,
                    insert_entry.idem_key,
                    insert_entry.device_id,
                    insert_entry.commit_ts,
                ),
            )
            row_id = cursor.lastrowid
            if (
                row_id is None
            ):  # pragma: no cover - defensive guard, SQLite always returns rowid
                msg = "Failed to determine WAL position"
                raise RuntimeError(msg)
            position = int(row_id)
            insert_entry.position = position
            return position

    def read_from(
        self,
        position: int,
        limit: int,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> List[WalEntry]:
        with _resolve_connection(connection) as conn:
            rows = conn.execute(
                (
                    "SELECT pos, tenant_id, space_id, topic, envelope_json, body, payload_sha256, "
                    "schema_uri, schema_version, idem_key, device_id, commit_ts "
                    "FROM st_wal WHERE pos > ? ORDER BY pos ASC LIMIT ?"
                ),
                (position, limit),
            ).fetchall()
            return [
                WalEntry(
                    tenant_id=row["tenant_id"],
                    space_id=row["space_id"],
                    topic=row["topic"],
                    envelope_json=row["envelope_json"],
                    schema_uri=row["schema_uri"],
                    schema_version=row["schema_version"],
                    device_id=row["device_id"],
                    commit_ts=row["commit_ts"],
                    body=row["body"],
                    payload_sha256=row["payload_sha256"],
                    idem_key=row["idem_key"],
                    position=row["pos"],
                )
                for row in rows
            ]

    def fsync(
        self,
        *,
        connection: sqlite3.Connection | None = None,
        chaos_config: Any | None = None,
        metrics_exporter: Any | None = None,
        mode: Literal["strict", "wal_only", "disabled"] = "strict",
    ) -> None:
        """Flush the database and WAL files to durable storage.

        Args:
            connection: Optional connection (uses pool if None)
            chaos_config: Optional ChaosSettings for fault injection
            metrics_exporter: Optional MetricsExporter for telemetry
            mode: Controls which files are flushed. ``strict`` flushes the main
                database, WAL, and SHM files. ``wal_only`` syncs just the WAL
                (and SHM when present). ``disabled`` skips flushing entirely.

        Raises:
            OSError: If fsync fails (real or chaos-injected)
        """

        if mode == "disabled":
            return

        with _resolve_connection(connection) as conn:
            database_list = conn.execute("PRAGMA database_list").fetchall()
            seen_paths: Set[Path] = set()
            for entry in database_list:
                file_path = entry["file"]
                if not file_path:
                    continue

                db_path = Path(file_path)
                wal_path = db_path.with_name(f"{db_path.name}-wal")
                shm_path = db_path.with_name(f"{db_path.name}-shm")
                if mode not in {"strict", "wal_only"}:
                    raise ValueError(f"Unsupported fsync mode: {mode}")

                if mode == "strict":
                    candidates = (db_path, wal_path, shm_path)
                else:  # mode == "wal_only"
                    candidates = (wal_path, shm_path)

                for candidate in candidates:
                    if candidate in seen_paths:
                        continue
                    if not candidate.exists():
                        continue
                    _fsync_path(candidate, chaos_config, metrics_exporter)
                    seen_paths.add(candidate)

    def backlog_stats(
        self,
        *,
        tenant_id: str,
        space_id: str,
        topic: str,
        offset: int,
        connection: sqlite3.Connection | None = None,
    ) -> WalBacklogStats:
        """Return backlog statistics beyond a subscriber's acknowledged offset."""

        with _resolve_connection(connection) as conn:
            row = conn.execute(
                (
                    "SELECT COUNT(*) AS pending, MAX(pos) AS latest_pos, MAX(commit_ts) AS latest_ts "
                    "FROM st_wal WHERE tenant_id=? AND space_id=? AND topic=? AND pos > ?"
                ),
                (tenant_id, space_id, topic, offset),
            ).fetchone()

            pending = int(row["pending"]) if row and row["pending"] is not None else 0
            latest_pos = row["latest_pos"] if row else None
            latest_ts = row["latest_ts"] if row else None

            return WalBacklogStats(
                pending_events=pending,
                latest_position=latest_pos,
                latest_commit_ts=latest_ts,
            )
