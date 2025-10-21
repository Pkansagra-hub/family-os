"""Snapshot scheduler for capturing durable WAL checkpoints."""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from k0.obs.events import ObservabilityEmitter
from k0.obs.metrics import MetricsExporter
from k0.security.crypto import canonical_json, hash_payload

from .wal import WalEntry, WriteAheadLog

LOGGER = logging.getLogger(__name__)

SNAPSHOT_TOPIC = "infra.snapshot.event"
SNAPSHOT_SCHEMA_URI = "https://contracts.family-ai.dev/schemas/infra.snapshot.event.json"
SNAPSHOT_SCHEMA_VERSION = "1.0.0"
SYSTEM_TENANT = "__infra__"
SYSTEM_SPACE = "__kernel__"
SYSTEM_DEVICE = "k0ctl.snapshot"


@dataclass(frozen=True)
class SnapshotManifest:
    """Materialised metadata describing a completed snapshot."""

    snapshot_id: str
    created_at: str
    watermark: int
    database_path: Path
    artifact_path: Path | None
    manifest_path: Path | None
    begin_position: int | None
    commit_position: int | None
    size_bytes: int | None


class SnapshotError(RuntimeError):
    """Raised when snapshot orchestration fails."""


class SnapshotScheduler:
    """Create point-in-time snapshots with WAL watermark markers."""

    def __init__(
        self,
        *,
        database_path: Path | str,
        metrics: MetricsExporter | None = None,
        observability: ObservabilityEmitter | None = None,
        write_ahead_log: WriteAheadLog | None = None,
    ) -> None:
        self._database_path = Path(database_path)
        self._metrics = metrics
        self._observability = observability
        self._wal = write_ahead_log or WriteAheadLog()

    def create_snapshot(
        self,
        *,
        output_dir: Path,
        snapshot_id: str | None = None,
        dry_run: bool = False,
    ) -> SnapshotManifest:
        """Capture a snapshot and emit WAL watermark markers."""

        if not self._database_path.exists():
            raise SnapshotError(
                f"Database not found at {self._database_path.as_posix()}"
            )

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        resolved_snapshot_id = snapshot_id or self._generate_snapshot_id()
        created_at = datetime.now(timezone.utc).isoformat()

        begin_pos: int | None = None
        commit_pos: int | None = None
        artifact_path: Path | None = None
        manifest_path: Path | None = None
        artifact_size: int | None = None

        connection = sqlite3.connect(str(self._database_path))
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout=5000;")
            watermark = self._resolve_watermark(connection)

            self._emit_observability(
                {
                    "event": "snapshot_preflight",
                    "snapshot_id": resolved_snapshot_id,
                    "watermark": watermark,
                    "dry_run": dry_run,
                }
            )

            self._set_snapshot_gauge(1.0, snapshot_id=resolved_snapshot_id)

            if not dry_run:
                begin_pos = self._append_marker(
                    connection,
                    marker_type="BEGIN",
                    snapshot_id=resolved_snapshot_id,
                    watermark=watermark,
                )
                connection.commit()

                artifact_path = output_dir / f"{resolved_snapshot_id}.sqlite3"
                self._write_backup(connection, artifact_path)
                artifact_size = artifact_path.stat().st_size
                manifest_path = output_dir / f"{resolved_snapshot_id}.json"
                self._write_manifest(
                    manifest_path,
                    snapshot_id=resolved_snapshot_id,
                    created_at=created_at,
                    watermark=watermark,
                    begin_position=begin_pos,
                    database_path=self._database_path,
                    artifact_path=artifact_path,
                    size_bytes=artifact_size,
                )

                commit_pos = self._append_marker(
                    connection,
                    marker_type="COMMIT",
                    snapshot_id=resolved_snapshot_id,
                    watermark=watermark,
                )
                connection.commit()
            else:
                LOGGER.info(
                    "Dry-run snapshot at watermark %s (id=%s)",
                    watermark,
                    resolved_snapshot_id,
                )

            self._emit_observability(
                {
                    "event": "snapshot_complete",
                    "snapshot_id": resolved_snapshot_id,
                    "watermark": watermark,
                    "begin_position": begin_pos,
                    "commit_position": commit_pos,
                    "artifact_path": str(artifact_path) if artifact_path else None,
                    "dry_run": dry_run,
                }
            )
            self._emit_metric(
                "snapshot_create_total",
                1.0,
                outcome="success",
                dry_run=str(dry_run).lower(),
            )
            return SnapshotManifest(
                snapshot_id=resolved_snapshot_id,
                created_at=created_at,
                watermark=watermark,
                database_path=self._database_path,
                artifact_path=artifact_path,
                manifest_path=manifest_path,
                begin_position=begin_pos,
                commit_position=commit_pos,
                size_bytes=artifact_size,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Snapshot creation failed: snapshot_id=%s", resolved_snapshot_id)
            self._emit_metric(
                "snapshot_create_total",
                1.0,
                outcome="failure",
                dry_run=str(dry_run).lower(),
            )
            self._set_snapshot_gauge(0.0, snapshot_id=resolved_snapshot_id)
            raise SnapshotError(str(exc)) from exc
        finally:
            self._set_snapshot_gauge(0.0, snapshot_id=resolved_snapshot_id)
            connection.close()

    def _append_marker(
        self,
        connection: sqlite3.Connection,
        *,
        marker_type: str,
        snapshot_id: str,
        watermark: int,
    ) -> int:
        timestamp = datetime.now(timezone.utc).isoformat()
        trace_id = str(uuid.uuid4())
        payload: dict[str, object] = {
            "type": marker_type,
            "watermark": watermark,
            "snapshot_id": snapshot_id,
        }
        body_bytes = canonical_json(payload).encode("utf-8")
        payload_hash = hash_payload(body_bytes) or "0" * 64
        envelope: dict[str, object] = {
            "cognitive_trace_id": trace_id,
            "tenant_id": SYSTEM_TENANT,
            "space_id": SYSTEM_SPACE,
            "actor": SYSTEM_DEVICE,
            "device_id": SYSTEM_DEVICE,
            "topic": SNAPSHOT_TOPIC,
            "schema_uri": SNAPSHOT_SCHEMA_URI,
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "ts": timestamp,
            "payload_sha256": payload_hash,
            "body": payload,
        }
        entry = WalEntry(
            tenant_id=SYSTEM_TENANT,
            space_id=SYSTEM_SPACE,
            topic=SNAPSHOT_TOPIC,
            envelope_json=canonical_json(_strip_body(envelope)),
            schema_uri=SNAPSHOT_SCHEMA_URI,
            schema_version=SNAPSHOT_SCHEMA_VERSION,
            device_id=SYSTEM_DEVICE,
            commit_ts=timestamp,
            body=body_bytes,
            payload_sha256=payload_hash,
            idem_key=None,
        )
        position = self._wal.append(entry, connection=connection)
        LOGGER.info(
            "Appended snapshot marker %s at WAL position %s (snapshot_id=%s, watermark=%s)",
            marker_type,
            position,
            snapshot_id,
            watermark,
        )
        return position

    def _write_backup(self, connection: sqlite3.Connection, artifact_path: Path) -> None:
        LOGGER.info("Writing snapshot artifact to %s", artifact_path.as_posix())
        with sqlite3.connect(str(artifact_path)) as destination:
            connection.backup(destination)
            destination.execute("VACUUM;")

    def _write_manifest(
        self,
        manifest_path: Path,
        *,
        snapshot_id: str,
        created_at: str,
        watermark: int,
        begin_position: int | None,
        database_path: Path,
        artifact_path: Path | None,
        size_bytes: int | None,
    ) -> None:
        payload: dict[str, object | None] = {
            "snapshot_id": snapshot_id,
            "created_at": created_at,
            "watermark": watermark,
            "begin_position": begin_position,
            "database_path": database_path.as_posix(),
            "artifact": artifact_path.as_posix() if artifact_path else None,
            "size_bytes": size_bytes,
        }
        manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        LOGGER.info("Wrote snapshot manifest %s", manifest_path.as_posix())

    def _resolve_watermark(self, connection: sqlite3.Connection) -> int:
        cursor = connection.execute("SELECT COALESCE(MAX(pos), 0) AS watermark FROM st_wal")
        row = cursor.fetchone()
        return int(row["watermark"] if row else 0)

    def _set_snapshot_gauge(self, value: float, *, snapshot_id: str) -> None:
        if self._metrics is None:
            return
        try:
            self._metrics.set_gauge(
                "snapshot_open_transactions",
                value,
                snapshot_id=snapshot_id,
            )
        except Exception:  # noqa: BLE001
            LOGGER.exception("Failed to update snapshot gauge", extra={"snapshot_id": snapshot_id})

    def _emit_metric(self, metric_name: str, value: float, **labels: str) -> None:
        if self._metrics is None:
            return
        try:
            self._metrics.emit(metric_name, value, **labels)
        except Exception:  # noqa: BLE001
            LOGGER.exception("Failed to emit metric %s", metric_name)

    def _emit_observability(self, event: dict[str, object]) -> None:
        if self._observability is None:
            return
        try:
            self._observability.emit(event)
        except Exception:  # noqa: BLE001
            LOGGER.exception("Failed to emit snapshot observability event")

    @staticmethod
    def _generate_snapshot_id() -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        random_component = uuid.uuid4().hex[:8]
        return f"snap-{timestamp}-{random_component}"


def _strip_body(envelope: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in envelope.items() if key != "body"}
