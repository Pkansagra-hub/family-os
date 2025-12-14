from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple

from ward import test  # type: ignore[attr-defined]

from k0.gate.schema_registry import SchemaRecord, SchemaRegistry
from k0.obs import MetricsExporter, ObservabilityEmitter
from k0.storage.replayer import Replayer
from k0.uow.connection_pool import connection_scope
from k0.tests.storage.fixtures import sqlite_runtime  # type: ignore[misc]

ISO_NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")
PAYLOAD_HASH = "c" * 64
SCHEMA_URI = "schema://memory.topic"
SCHEMA_VERSION = "1.0.0"


def _seed_dataset(
    connection: sqlite3.Connection,
) -> Dict[Tuple[str, str], Tuple[int, ...]]:
    dataset: Dict[Tuple[str, str], Tuple[int, ...]] = {}
    events = [
        ("tenant-alpha", "space-1"),
        ("tenant-alpha", "space-1"),
        ("tenant-alpha", "space-2"),
        ("tenant-beta", "space-9"),
    ]
    positions: Dict[Tuple[str, str], list[int]] = {}
    for tenant_id, space_id in events:
        envelope = json.dumps(
            {
                "tenant_id": tenant_id,
                "space_id": space_id,
                "topic": "memory.topic",
                "schema_uri": SCHEMA_URI,
                "schema_version": SCHEMA_VERSION,
                "payload_sha256": PAYLOAD_HASH,
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
                PAYLOAD_HASH,
                SCHEMA_URI,
                SCHEMA_VERSION,
                None,
                "device-simulator",
                ISO_NOW,
            ),
        )
        wal_pos = cursor.lastrowid
        if wal_pos is None:  # pragma: no cover - SQLite always assigns rowid
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
        positions.setdefault((tenant_id, space_id), []).append(int(wal_pos))
    for key, values in positions.items():
        dataset[key] = tuple(values)
    return dataset


@test("selective replay by tenant and space replays only scoped events")
def _(sqlite_db: Path = sqlite_runtime) -> None:  # type: ignore[assignment]
    metrics = MetricsExporter(namespace="test_replay_selective_space")
    emitter = ObservabilityEmitter()
    registry = SchemaRegistry()

    with connection_scope() as connection:
        registry.upsert(
            SchemaRecord(
                uri=SCHEMA_URI,
                version=SCHEMA_VERSION,
                sha256=PAYLOAD_HASH,
                status="ACTIVE",
            ),
            connection=connection,
        )
        dataset = _seed_dataset(connection)
        connection.commit()

    replayer = Replayer(
        schema_registry=registry,
        metrics=metrics,
        observability=emitter,
    )
    scoped_result = replayer.run(
        from_position=0,
        tenant_id="tenant-alpha",
        space_id="space-1",
    )
    expected_positions = dataset[("tenant-alpha", "space-1")]
    assert scoped_result.processed == len(expected_positions)
    assert scoped_result.parity_failures == 0
    assert scoped_result.last_position == expected_positions[-1]

    parity_metric = metrics.registry.get_sample_value(
        "test_replay_selective_space_replay_parity_failures_total",
        {"tenant": "tenant-alpha", "space": "space-1"},
    )
    assert parity_metric == 0.0

    duration_count = metrics.registry.get_sample_value(
        "test_replay_selective_space_replay_run_duration_seconds_count",
        {"tenant": "tenant-alpha", "space": "space-1"},
    )
    assert duration_count == 1.0
    throughput_count = metrics.registry.get_sample_value(
        "test_replay_selective_space_replay_throughput_events_per_second_count",
        {"tenant": "tenant-alpha", "space": "space-1"},
    )
    assert throughput_count == 1.0


@test("tenant-scoped replay spans all spaces for that tenant")
def _(sqlite_db: Path = sqlite_runtime) -> None:  # type: ignore[assignment]
    metrics = MetricsExporter(namespace="test_replay_selective_tenant")
    emitter = ObservabilityEmitter()
    registry = SchemaRegistry()

    with connection_scope() as connection:
        registry.upsert(
            SchemaRecord(
                uri=SCHEMA_URI,
                version=SCHEMA_VERSION,
                sha256=PAYLOAD_HASH,
                status="ACTIVE",
            ),
            connection=connection,
        )
        dataset = _seed_dataset(connection)
        connection.commit()

    replayer = Replayer(
        schema_registry=registry,
        metrics=metrics,
        observability=emitter,
    )
    tenant_result = replayer.run(
        from_position=0,
        tenant_id="tenant-alpha",
    )
    expected_total = sum(
        len(events) for key, events in dataset.items() if key[0] == "tenant-alpha"
    )
    assert tenant_result.processed == expected_total
    assert tenant_result.parity_failures == 0
    assert tenant_result.last_position == max(
        max(events) for key, events in dataset.items() if key[0] == "tenant-alpha"
    )

    parity_metric = metrics.registry.get_sample_value(
        "test_replay_selective_tenant_replay_parity_failures_total",
        {"tenant": "tenant-alpha", "space": "*"},
    )
    assert parity_metric == 0.0

    duration_count = metrics.registry.get_sample_value(
        "test_replay_selective_tenant_replay_run_duration_seconds_count",
        {"tenant": "tenant-alpha", "space": "*"},
    )
    assert duration_count == 1.0
    throughput_count = metrics.registry.get_sample_value(
        "test_replay_selective_tenant_replay_throughput_events_per_second_count",
        {"tenant": "tenant-alpha", "space": "*"},
    )
    assert throughput_count == 1.0

