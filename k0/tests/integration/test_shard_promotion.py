from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterable, Iterator, Sequence

from ward import fixture, raises, test  # type: ignore[attr-defined]

from k0.obs import MetricsExporter, ObservabilityEmitter
from k0.storage.shard_promotion import ShardPromotionCoordinator, ShardPromotionError

REPO_ROOT = Path(__file__).resolve().parents[2]
STORAGE_SQL_PATH = REPO_ROOT / "k0" / "contracts" / "sql" / "storage.sql"
BASE_TS = datetime(2025, 10, 4, 12, 0, tzinfo=timezone.utc)
SCHEMA_URI = "schema://k0/shard.test"
SCHEMA_VERSION = "1.0.0"
TENANT_ID = "tenant-alpha"
SPACE_ID = "space-1"
DEVICE_ID = "device-sim"


@fixture
def shard_databases() -> Iterator[tuple[Path, Path]]:
    with TemporaryDirectory() as tmp_dir:
        primary_path = Path(tmp_dir) / "primary.sqlite3"
        standby_path = Path(tmp_dir) / "standby.sqlite3"
        _initialise_schema(primary_path)
        _initialise_schema(standby_path)
        yield primary_path, standby_path


def _initialise_schema(path: Path) -> None:
    connection = sqlite3.connect(path.as_posix())
    try:
        connection.executescript(STORAGE_SQL_PATH.read_text(encoding="utf-8"))
        connection.commit()
    finally:
        connection.close()


def _seed_primary(
    primary_path: Path,
    *,
    total_events: int,
    missing_receipts: Sequence[int] | None = None,
) -> None:
    connection = sqlite3.connect(primary_path.as_posix())
    try:
        for index in range(total_events):
            position = index + 1
            commit_ts = (BASE_TS + timedelta(seconds=index * 10)).isoformat()
            envelope_payload = {
                "tenant_id": TENANT_ID,
                "space_id": SPACE_ID,
                "topic": "memory.topic",
                "schema_uri": SCHEMA_URI,
                "schema_version": SCHEMA_VERSION,
                "payload_sha256": f"{index:064x}",
            }
            connection.execute(
                (
                    "INSERT INTO st_wal (pos, tenant_id, space_id, topic, envelope_json, body, payload_sha256, "
                    "schema_uri, schema_version, idem_key, device_id, commit_ts) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                ),
                (
                    position,
                    TENANT_ID,
                    SPACE_ID,
                    "memory.topic",
                    json.dumps(envelope_payload, separators=(",", ":")),
                    json.dumps({"index": index}).encode("utf-8"),
                    f"{index:064x}",
                    SCHEMA_URI,
                    SCHEMA_VERSION,
                    f"idem-{position}",
                    DEVICE_ID,
                    commit_ts,
                ),
            )
            if missing_receipts and position in missing_receipts:
                continue
            connection.execute(
                (
                    "INSERT INTO st_receipts (receipt_id, idem_key, wal_pos, commit_ts, tenant_id, space_id, device_id, "
                    "mls_group_id, key_version, device_sig) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                ),
                (
                    f"receipt-{position}",
                    f"idem-{position}",
                    position,
                    commit_ts,
                    TENANT_ID,
                    SPACE_ID,
                    DEVICE_ID,
                    "mls-1",
                    "k1",
                    "signature",
                ),
            )
        connection.commit()
    finally:
        connection.close()


def _copy_positions(
    primary_path: Path,
    standby_path: Path,
    positions: Iterable[int],
) -> None:
    primary = sqlite3.connect(primary_path.as_posix())
    standby = sqlite3.connect(standby_path.as_posix())
    try:
        primary.row_factory = sqlite3.Row
        for position in positions:
            wal_row = primary.execute(
                (
                    "SELECT pos, tenant_id, space_id, topic, envelope_json, body, payload_sha256, schema_uri, "
                    "schema_version, idem_key, device_id, commit_ts FROM st_wal WHERE pos = ?"
                ),
                (position,),
            ).fetchone()
            if wal_row is None:
                msg = f"Expected WAL position {position} to exist in primary"
                raise AssertionError(msg)
            standby.execute(
                (
                    "INSERT INTO st_wal (pos, tenant_id, space_id, topic, envelope_json, body, payload_sha256, "
                    "schema_uri, schema_version, idem_key, device_id, commit_ts) "
                    "VALUES (:pos, :tenant_id, :space_id, :topic, :envelope_json, :body, :payload_sha256, :schema_uri, "
                    ":schema_version, :idem_key, :device_id, :commit_ts)"
                ),
                {key: wal_row[key] for key in wal_row.keys()},
            )
            receipt_row = primary.execute(
                (
                    "SELECT receipt_id, idem_key, wal_pos, commit_ts, tenant_id, space_id, device_id, mls_group_id, "
                    "key_version, device_sig FROM st_receipts WHERE wal_pos = ?"
                ),
                (position,),
            ).fetchone()
            if receipt_row is not None:
                standby.execute(
                    (
                        "INSERT INTO st_receipts (receipt_id, idem_key, wal_pos, commit_ts, tenant_id, space_id, device_id, "
                        "mls_group_id, key_version, device_sig) "
                        "VALUES (:receipt_id, :idem_key, :wal_pos, :commit_ts, :tenant_id, :space_id, :device_id, :mls_group_id, "
                        ":key_version, :device_sig)"
                    ),
                    {key: receipt_row[key] for key in receipt_row.keys()},
                )
        standby.commit()
    finally:
        primary.close()
        standby.close()


def _fetch_positions(database_path: Path) -> list[int]:
    connection = sqlite3.connect(database_path.as_posix())
    try:
        rows = connection.execute("SELECT pos FROM st_wal ORDER BY pos ASC").fetchall()
        return [int(row[0]) for row in rows]
    finally:
        connection.close()


def _count_receipts(database_path: Path) -> int:
    connection = sqlite3.connect(database_path.as_posix())
    try:
        row = connection.execute("SELECT COUNT(*) FROM st_receipts").fetchone()
        return int(row[0]) if row else 0
    finally:
        connection.close()


@test("shard promotion synchronises standby and emits telemetry")
def _(dbs: tuple[Path, Path] = shard_databases) -> None:  # type: ignore[assignment]
    primary_path, standby_path = dbs
    _seed_primary(primary_path, total_events=5)
    _copy_positions(primary_path, standby_path, range(1, 4))

    metrics = MetricsExporter(namespace="k0")
    emitter = ObservabilityEmitter()
    coordinator = ShardPromotionCoordinator(
        shard_id=f"{TENANT_ID}:{SPACE_ID}",
        primary_path=primary_path,
        standby_path=standby_path,
        metrics=metrics,
        observability=emitter,
    )

    lag_before = coordinator.compute_replica_lag()
    assert lag_before > 0

    result = coordinator.promote()
    assert result.applied_positions == (4, 5)
    assert result.lag_after_seconds == 0
    assert _fetch_positions(standby_path) == [1, 2, 3, 4, 5]
    assert _count_receipts(standby_path) == 5

    lag_metric = metrics.registry.get_sample_value(
        "k0_wal_replica_lag_seconds",
        {"role": "standby", "shard": f"{TENANT_ID}:{SPACE_ID}"},
    )
    assert lag_metric == 0.0
    watermark_metric = metrics.registry.get_sample_value(
        "k0_kernel_replay_watermark",
        {"shard": f"{TENANT_ID}:{SPACE_ID}"},
    )
    assert watermark_metric == 5.0

    events = emitter.snapshot()
    event_names = [event.get("event") for event in events]
    assert "shard_promotion_sync_started" in event_names
    assert "shard_promotion_sync_completed" in event_names


@test("promotion aborts when receipts are missing")
def _(dbs: tuple[Path, Path] = shard_databases) -> None:  # type: ignore[assignment]
    primary_path, standby_path = dbs
    _seed_primary(primary_path, total_events=5, missing_receipts=(4,))
    _copy_positions(primary_path, standby_path, range(1, 4))

    metrics = MetricsExporter(namespace="k0")
    emitter = ObservabilityEmitter()
    coordinator = ShardPromotionCoordinator(
        shard_id=f"{TENANT_ID}:{SPACE_ID}",
        primary_path=primary_path,
        standby_path=standby_path,
        metrics=metrics,
        observability=emitter,
    )

    with raises(ShardPromotionError):
        coordinator.promote()

    assert _fetch_positions(standby_path) == [1, 2, 3]
    events = emitter.snapshot()
    assert events
    assert events[-1].get("event") == "shard_promotion_error"


@test("promotion is idempotent when standby is current")
def _(dbs: tuple[Path, Path] = shard_databases) -> None:  # type: ignore[assignment]
    primary_path, standby_path = dbs
    _seed_primary(primary_path, total_events=3)
    _copy_positions(primary_path, standby_path, range(1, 4))

    metrics = MetricsExporter(namespace="k0")
    emitter = ObservabilityEmitter()
    coordinator = ShardPromotionCoordinator(
        shard_id=f"{TENANT_ID}:{SPACE_ID}",
        primary_path=primary_path,
        standby_path=standby_path,
        metrics=metrics,
        observability=emitter,
    )

    lag_before = coordinator.compute_replica_lag()
    assert lag_before == 0

    result = coordinator.promote()
    assert result.applied_positions == ()
    assert result.lag_after_seconds == 0
    assert _fetch_positions(standby_path) == [1, 2, 3]

    events = emitter.snapshot()
    assert events
    assert events[-1].get("event") == "shard_promotion_noop"
