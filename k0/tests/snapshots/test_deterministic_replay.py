from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ward import test  # type: ignore[attr-defined]

from k0.gate.schema_registry import SchemaRecord, SchemaRegistry
from k0.obs import MetricsExporter, ObservabilityEmitter
from k0.storage.replayer import Replayer
from k0.storage.snapshots import SnapshotScheduler
from k0.uow.connection_pool import connection_scope
from k0.tests.storage.fixtures import sqlite_runtime  # type: ignore[misc]

ISO_NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")


def _seed_event(
    tenant_id: str,
    space_id: str,
    *,
    connection: sqlite3.Connection,
    schema_uri: str,
    schema_version: str,
    payload_hash: str,
) -> int:
    envelope = json.dumps(
        {
            "tenant_id": tenant_id,
            "space_id": space_id,
            "topic": "memory.topic",
            "schema_uri": schema_uri,
            "schema_version": schema_version,
            "payload_sha256": payload_hash,
        }
    )
    cursor = connection.execute(
        (
            "INSERT INTO st_wal (tenant_id, space_id, topic, envelope_json, body, payload_sha256, "
            "schema_uri, schema_version, idem_key, device_id, commit_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        ),
        (
            tenant_id,
            space_id,
            "memory.topic",
            envelope,
            b"{}",
            payload_hash,
            schema_uri,
            schema_version,
            None,
            "device-simulator",
            ISO_NOW,
        ),
    )
    wal_pos = cursor.lastrowid
    if wal_pos is None:  # pragma: no cover - SQLite always returns rowid
        raise AssertionError("expected WAL position to be assigned")
    connection.execute(
        (
            "INSERT INTO st_receipts (receipt_id, idem_key, wal_pos, commit_ts, tenant_id, space_id, "
            "device_id, mls_group_id, key_version, device_sig) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        ),
        (
            f"rcpt-{tenant_id}-{space_id}-{wal_pos}",
            f"idem-{wal_pos}",
            wal_pos,
            ISO_NOW,
            tenant_id,
            space_id,
            "device-simulator",
            "mls-1",
            "k1",
            "sig",
        ),
    )
    return wal_pos


@test("deterministic replay after snapshot watermark keeps parity at zero")
def _(sqlite_db: Path = sqlite_runtime) -> None:  # type: ignore[assignment]
    metrics = MetricsExporter(namespace="test_snapshot_deterministic")
    emitter = ObservabilityEmitter()
    registry = SchemaRegistry()

    payload_hash = "a" * 64
    schema_uri = "schema://memory.topic"
    schema_version = "1.0.0"

    with connection_scope() as connection:
        registry.upsert(
            SchemaRecord(
                uri=schema_uri,
                version=schema_version,
                sha256=payload_hash,
                status="ACTIVE",
            ),
            connection=connection,
        )
        last_position = _seed_event(
            "tenant-alpha",
            "space-main",
            connection=connection,
            schema_uri=schema_uri,
            schema_version=schema_version,
            payload_hash=payload_hash,
        )
        connection.commit()

    scheduler = SnapshotScheduler(
        database_path=sqlite_db,
        metrics=metrics,
        observability=emitter,
    )
    manifest = scheduler.create_snapshot(
        output_dir=Path(sqlite_db).parent,
        dry_run=True,
    )
    assert manifest.watermark == last_position

    replayer = Replayer(
        schema_registry=registry,
        metrics=metrics,
        observability=emitter,
    )
    result = replayer.run(from_position=0)
    assert result.processed == 1
    assert result.parity_failures == 0
    assert result.last_position == last_position

    parity_metric = metrics.registry.get_sample_value(
        "test_snapshot_deterministic_replay_parity_failures_total",
        {"tenant": "*", "space": "*"},
    )
    assert parity_metric == 0.0


@test("replay from snapshot watermark processes only new events without parity drift")
def _(sqlite_db: Path = sqlite_runtime) -> None:  # type: ignore[assignment]
    metrics = MetricsExporter(namespace="test_snapshot_incremental")
    emitter = ObservabilityEmitter()
    registry = SchemaRegistry()

    payload_hash = "b" * 64
    schema_uri = "schema://memory.topic"
    schema_version = "1.0.0"

    with connection_scope() as connection:
        registry.upsert(
            SchemaRecord(
                uri=schema_uri,
                version=schema_version,
                sha256=payload_hash,
                status="ACTIVE",
            ),
            connection=connection,
        )
        first_pos = _seed_event(
            "tenant-alpha",
            "space-primary",
            connection=connection,
            schema_uri=schema_uri,
            schema_version=schema_version,
            payload_hash=payload_hash,
        )
        connection.commit()

    scheduler = SnapshotScheduler(
        database_path=sqlite_db,
        metrics=metrics,
        observability=emitter,
    )
    manifest = scheduler.create_snapshot(
        output_dir=Path(sqlite_db).parent,
        dry_run=True,
    )
    assert manifest.watermark == first_pos

    with connection_scope() as connection:
        second_pos = _seed_event(
            "tenant-alpha",
            "space-primary",
            connection=connection,
            schema_uri=schema_uri,
            schema_version=schema_version,
            payload_hash=payload_hash,
        )
        connection.commit()

    replayer = Replayer(
        schema_registry=registry,
        metrics=metrics,
        observability=emitter,
    )
    incremental = replayer.run(from_position=manifest.watermark)
    assert incremental.processed == 1
    assert incremental.parity_failures == 0
    assert incremental.last_position == second_pos

    parity_metric = metrics.registry.get_sample_value(
        "test_snapshot_incremental_replay_parity_failures_total",
        {"tenant": "*", "space": "*"},
    )
    assert parity_metric == 0.0

