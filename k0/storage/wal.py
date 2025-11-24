"""Write-ahead log adapter."""

from __future__ import annotations

import asyncio
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
    """Domain representation of a WAL row (V1 with full envelope integrity)."""

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
    redacted_body_json: str | None = None
    position: int | None = None

    # V1 NEW: Envelope integrity tracking
    envelope_sha256: str | None = None

    # V1 NEW: Time tracking
    ingested_at: str | None = None
    clock_skew_ms: int | None = None

    # V1.3 NEW: Policy stamp (attached by PolicyEvaluator)
    policy_stamp_json: str | None = None

    # V1.3 NEW: Location privacy fields
    location_geohash: str | None = None
    location_precision_m: int | None = None


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

    def __init__(self, *, metrics: Any | None = None) -> None:
        """Issue #044: Initialize with optional metrics exporter."""
        self._metrics = metrics

    async def append(self, entry: WalEntry, *, connection: sqlite3.Connection | None = None) -> int:
        insert_entry = replace(entry)
        loop = asyncio.get_running_loop()

        def _execute_append() -> int:
            with _resolve_connection(connection) as conn:
                cursor = conn.execute(
                    (
                        "INSERT INTO st_wal (tenant_id, space_id, topic, envelope_json, body, "
                        "redacted_body_json, payload_sha256, schema_uri, schema_version, idem_key, device_id, commit_ts, "
                        "envelope_sha256, ingested_at, clock_skew_ms, policy_stamp_json, "
                        "location_geohash, location_precision_m) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        insert_entry.tenant_id,
                        insert_entry.space_id,
                        insert_entry.topic,
                        insert_entry.envelope_json,
                        insert_entry.body,
                        insert_entry.redacted_body_json,
                        insert_entry.payload_sha256,
                        insert_entry.schema_uri,
                        insert_entry.schema_version,
                        insert_entry.idem_key,
                        insert_entry.device_id,
                        insert_entry.commit_ts,
                        # V1 NEW: Envelope integrity tracking
                        insert_entry.envelope_sha256,
                        insert_entry.ingested_at,
                        insert_entry.clock_skew_ms,
                        # V1.3 NEW: Policy stamp (attached by PolicyEvaluator)
                        insert_entry.policy_stamp_json,
                        # V1.3 NEW: Location privacy fields
                        insert_entry.location_geohash,
                        insert_entry.location_precision_m,
                    ),
                )
                row_id = cursor.lastrowid
                if (
                    row_id is None
                ):  # pragma: no cover - defensive guard, SQLite always returns rowid
                    msg = "Failed to determine WAL position"
                    raise RuntimeError(msg)
                return int(row_id)

        position = await loop.run_in_executor(None, _execute_append)
        insert_entry.position = position

        # Issue #044: Emit wal_current_position gauge
        if self._metrics is not None:
            try:
                self._metrics.set_gauge("wal_current_position", float(position))
            except Exception:  # noqa: BLE001
                pass  # Don't fail WAL append on metrics error

        return position

    async def read_from(
        self,
        position: int,
        limit: int,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> List[WalEntry]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._read_from_sync, position, limit, connection)

    def _read_from_sync(
        self,
        position: int,
        limit: int,
        connection: sqlite3.Connection | None = None,
    ) -> List[WalEntry]:
        with _resolve_connection(connection) as conn:
            rows = conn.execute(
                (
                    "SELECT pos, tenant_id, space_id, topic, envelope_json, body, payload_sha256, "
                    "redacted_body_json, schema_uri, schema_version, idem_key, device_id, commit_ts, "
                    "envelope_sha256, ingested_at, clock_skew_ms, policy_stamp_json, "
                    "location_geohash, location_precision_m "
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
                    redacted_body_json=row["redacted_body_json"],
                    payload_sha256=row["payload_sha256"],
                    idem_key=row["idem_key"],
                    position=row["pos"],
                    # V1 NEW: Envelope integrity tracking
                    envelope_sha256=row["envelope_sha256"],
                    ingested_at=row["ingested_at"],
                    clock_skew_ms=row["clock_skew_ms"],
                    # V1.3 NEW: Policy stamp
                    policy_stamp_json=row["policy_stamp_json"],
                    # V1.3 NEW: Location privacy fields
                    location_geohash=row["location_geohash"],
                    location_precision_m=row["location_precision_m"],
                )
                for row in rows
            ]

    async def fsync(
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

        loop = asyncio.get_running_loop()

        def _execute_fsync() -> None:
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

        await loop.run_in_executor(None, _execute_fsync)

    async def backlog_stats(
        self,
        *,
        tenant_id: str,
        space_id: str,
        topic: str,
        offset: int,
        connection: sqlite3.Connection | None = None,
    ) -> WalBacklogStats:
        """Return backlog statistics beyond a subscriber's acknowledged offset."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._backlog_stats_sync, tenant_id, space_id, topic, offset, connection
        )

    def _backlog_stats_sync(
        self,
        tenant_id: str,
        space_id: str,
        topic: str,
        offset: int,
        connection: sqlite3.Connection | None = None,
    ) -> WalBacklogStats:
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
