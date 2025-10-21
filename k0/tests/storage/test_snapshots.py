from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

from ward import test  # type: ignore[attr-defined]

from k0.obs import MetricsExporter, ObservabilityEmitter
from k0.storage.snapshots import SNAPSHOT_TOPIC, SnapshotScheduler
from tests.storage.fixtures import sqlite_runtime  # type: ignore[misc]


@test("snapshot scheduler writes artifacts, manifest, and WAL markers")
def _(sqlite_db: Path = sqlite_runtime) -> None:  # type: ignore[assignment]
    metrics = MetricsExporter(namespace="test_snapshot")
    emitter = ObservabilityEmitter()
    scheduler = SnapshotScheduler(
        database_path=sqlite_db,
        metrics=metrics,
        observability=emitter,
    )

    with TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        manifest = scheduler.create_snapshot(output_dir=Path(tmpdir))
        assert manifest.artifact_path is not None
        assert manifest.artifact_path.exists()
        assert manifest.manifest_path is not None
        assert manifest.manifest_path.exists()

        payload = json.loads(manifest.manifest_path.read_text(encoding="utf-8"))
        assert payload["snapshot_id"] == manifest.snapshot_id
        assert payload["watermark"] == manifest.watermark

    with sqlite3.connect(str(sqlite_db)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT body FROM st_wal WHERE topic=? ORDER BY pos ASC",
            (SNAPSHOT_TOPIC,),
        ).fetchall()
        assert len(rows) == 2
        marker_types = {
            json.loads(row["body"].decode("utf-8"))["type"] for row in rows
        }
        assert marker_types == {"BEGIN", "COMMIT"}

    success_count = metrics.registry.get_sample_value(
        "test_snapshot_snapshot_create_total",
        {"outcome": "success", "dry_run": "false"},
    )
    assert success_count == 1.0

    gauge_value = metrics.registry.get_sample_value(
        "test_snapshot_snapshot_open_transactions",
        {"snapshot_id": manifest.snapshot_id},
    )
    assert gauge_value == 0

    events = emitter.snapshot()
    event_names = {event.get("event") for event in events}
    assert {"snapshot_preflight", "snapshot_complete"}.issubset(event_names)


@test("snapshot scheduler dry-run avoids writing artifacts or markers")
def _(sqlite_db: Path = sqlite_runtime) -> None:  # type: ignore[assignment]
    metrics = MetricsExporter(namespace="test_snapshot_dry_run")
    emitter = ObservabilityEmitter()
    scheduler = SnapshotScheduler(
        database_path=sqlite_db,
        metrics=metrics,
        observability=emitter,
    )

    with TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        manifest = scheduler.create_snapshot(
            output_dir=Path(tmpdir),
            dry_run=True,
        )

    assert manifest.artifact_path is None
    assert manifest.manifest_path is None
    assert manifest.begin_position is None
    assert manifest.commit_position is None

    with sqlite3.connect(str(sqlite_db)) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM st_wal WHERE topic=?",
            (SNAPSHOT_TOPIC,),
        ).fetchone()[0]
        assert count == 0

    success_metric = metrics.registry.get_sample_value(
        "test_snapshot_dry_run_snapshot_create_total",
        {"outcome": "success", "dry_run": "true"},
    )
    assert success_metric == 1.0

    events = emitter.snapshot()
    assert any(event.get("event") == "snapshot_complete" for event in events)
