from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ward import raises, test  # type: ignore[attr-defined]

from k0.gate.schema_registry import SchemaRegistry
from k0.obs import MetricsExporter, ObservabilityEmitter
from k0.storage.replayer import ReplayError, Replayer
from k0.uow.connection_pool import connection_scope
from tests.storage.fixtures import sqlite_runtime  # type: ignore[misc]

ISO_NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")


@test("replayer succeeds when schema and receipts parity hold")
def _(sqlite_db: Path = sqlite_runtime) -> None:  # type: ignore[assignment]
    metrics = MetricsExporter(namespace="test_replay")
    emitter = ObservabilityEmitter()
    registry = SchemaRegistry()
    replayer = Replayer(
        schema_registry=registry,
        metrics=metrics,
        observability=emitter,
    )

    with connection_scope() as connection:
        connection.execute(
            "INSERT INTO schema_registry (schema_uri, version, sha256, status) VALUES (?, ?, ?, ?)",
            ("schema://memory/topic", "1.0.0", "a" * 64, "ACTIVE"),
        )
        wal_cursor = connection.execute(
            "INSERT INTO st_wal (tenant_id, space_id, topic, envelope_json, body, payload_sha256, schema_uri, schema_version, idem_key, device_id, commit_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "tenant-A",
                "space-A",
                "memory.topic",
                '{"tenant_id":"tenant-A","topic":"memory.topic"}',
                b"{}",
                "b" * 64,
                "schema://memory/topic",
                "1.0.0",
                None,
                "device-A",
                ISO_NOW,
            ),
        )
        wal_pos = wal_cursor.lastrowid
        connection.execute(
            "INSERT INTO st_receipts (receipt_id, idem_key, wal_pos, commit_ts, tenant_id, space_id, device_id, mls_group_id, key_version, device_sig) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "rcpt-1",
                "idem-1",
                wal_pos,
                ISO_NOW,
                "tenant-A",
                "space-A",
                "device-A",
                "mls-1",
                "v1",
                "sig",
            ),
        )
        connection.commit()

    result = replayer.run(from_position=0)
    assert result.processed == 1
    assert result.parity_failures == 0
    assert result.last_position == wal_pos

    success_metric = metrics.registry.get_sample_value(
        "test_replay_replay_runs_total",
        {"outcome": "success", "dry_run": "false"},
    )
    assert success_metric == 1.0

    parity_samples = metrics.registry.get_sample_value(
        "test_replay_replay_parity_failures_total",
        {"tenant": "*", "space": "*"},
    )
    assert parity_samples == 0.0

    events = emitter.snapshot()
    assert any(event.get("event") == "replay_complete" for event in events)


@test("replayer raises when schema is missing and not in dry-run mode")
def _(sqlite_db: Path = sqlite_runtime) -> None:  # type: ignore[assignment]
    metrics = MetricsExporter(namespace="test_replay_missing_schema")
    emitter = ObservabilityEmitter()
    registry = SchemaRegistry()
    replayer = Replayer(
        schema_registry=registry,
        metrics=metrics,
        observability=emitter,
    )

    with connection_scope() as connection:
        connection.execute(
            "INSERT INTO st_wal (tenant_id, space_id, topic, envelope_json, body, payload_sha256, schema_uri, schema_version, idem_key, device_id, commit_ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "tenant-A",
                "space-A",
                "memory.topic",
                '{"tenant_id":"tenant-A","topic":"memory.topic"}',
                b"{}",
                "c" * 64,
                "schema://missing/topic",
                "1.0.0",
                None,
                "device-A",
                ISO_NOW,
            ),
        )
        connection.commit()

    with raises(ReplayError):
        replayer.run(from_position=0)

    failure_metric = metrics.registry.get_sample_value(
        "test_replay_missing_schema_replay_parity_failures_total",
        {"component": "schema_missing", "topic": "memory.topic"},
    )
    assert failure_metric == 1.0
