"""Snapshot scheduler for capturing durable WAL checkpoints - Async PostgreSQL."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from k0.db.connection import connection_scope
from k0.obs.events import ObservabilityEmitter
from k0.obs.metrics import MetricsExporter
from k0.security.crypto import canonical_json, hash_payload

from .wal import WalEntry, WriteAheadLog

if TYPE_CHECKING:
    import asyncpg

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
    """Create point-in-time snapshots with WAL watermark markers - PostgreSQL."""

    def __init__(
        self,
        *,
        database_path: Path | str | None = None,
        metrics: MetricsExporter | None = None,
        observability: ObservabilityEmitter | None = None,
        write_ahead_log: WriteAheadLog | None = None,
    ) -> None:
        self._database_path = Path(database_path) if database_path else None
        self._metrics = metrics
        self._observability = observability
        self._wal = write_ahead_log or WriteAheadLog()

    async def create_snapshot(
        self,
        *,
        output_dir: Path,
        snapshot_id: str | None = None,
        dry_run: bool = False,
        connection: asyncpg.Connection | None = None,
    ) -> SnapshotManifest:
        """Capture a snapshot and emit WAL watermark markers.

        For PostgreSQL, snapshots are created using pg_dump or logical backups
        rather than SQLite file copies.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        resolved_snapshot_id = snapshot_id or self._generate_snapshot_id()
        created_at = datetime.now(timezone.utc).isoformat()

        begin_pos: int | None = None
        commit_pos: int | None = None
        manifest_path: Path | None = None

        try:
            async with connection_scope() as conn:
                watermark = await self._resolve_watermark(conn)

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
                    begin_pos = await self._append_marker(
                        conn,
                        marker_type="BEGIN",
                        snapshot_id=resolved_snapshot_id,
                        watermark=watermark,
                    )

                    # For PostgreSQL, we record the snapshot metadata
                    # Actual backup is done via pg_dump externally
                    manifest_path = output_dir / f"{resolved_snapshot_id}.json"
                    self._write_manifest(
                        manifest_path,
                        snapshot_id=resolved_snapshot_id,
                        created_at=created_at,
                        watermark=watermark,
                        begin_position=begin_pos,
                        database_path=self._database_path,
                        artifact_path=None,
                        size_bytes=None,
                    )

                    commit_pos = await self._append_marker(
                        conn,
                        marker_type="COMMIT",
                        snapshot_id=resolved_snapshot_id,
                        watermark=watermark,
                    )
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
                    "artifact_path": None,
                    "dry_run": dry_run,
                }
            )
            self._emit_metric(
                "snapshot_create_total",
                1.0,
                outcome="success",
                dry_run=str(dry_run).lower(),
            )
            self._set_watermark_gauge(float(watermark))

            return SnapshotManifest(
                snapshot_id=resolved_snapshot_id,
                created_at=created_at,
                watermark=watermark,
                database_path=self._database_path,
                artifact_path=None,
                manifest_path=manifest_path,
                begin_position=begin_pos,
                commit_position=commit_pos,
                size_bytes=None,
            )
        except Exception as exc:
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

    async def _append_marker(
        self,
        connection: asyncpg.Connection,
        *,
        marker_type: str,
        snapshot_id: str,
        watermark: int,
    ) -> int:
        """Append a snapshot marker to the WAL."""
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

        position = await connection.fetchval(
            """
            INSERT INTO st_wal (
                tenant_id, space_id, topic, envelope_json, body,
                redacted_body_json, payload_sha256, schema_uri, schema_version,
                idem_key, device_id, commit_ts, envelope_sha256, ingested_at,
                clock_skew_ms, policy_stamp_json, location_geohash, location_precision_m
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
            RETURNING pos
            """,
            entry.tenant_id,
            entry.space_id,
            entry.topic,
            entry.envelope_json,
            entry.body,
            entry.redacted_body_json,
            entry.payload_sha256,
            entry.schema_uri,
            entry.schema_version,
            entry.idem_key,
            entry.device_id,
            entry.commit_ts,
            entry.envelope_sha256,
            entry.ingested_at,
            entry.clock_skew_ms,
            entry.policy_stamp_json,
            entry.location_geohash,
            entry.location_precision_m,
        )

        if position is None:
            msg = "Failed to determine WAL position"
            raise RuntimeError(msg)

        LOGGER.info(
            "Appended snapshot marker %s at WAL position %s (snapshot_id=%s, watermark=%s)",
            marker_type,
            position,
            snapshot_id,
            watermark,
        )
        return int(position)

    def _write_manifest(
        self,
        manifest_path: Path,
        *,
        snapshot_id: str,
        created_at: str,
        watermark: int,
        begin_position: int | None,
        database_path: Path | None,
        artifact_path: Path | None,
        size_bytes: int | None,
    ) -> None:
        payload: dict[str, object | None] = {
            "snapshot_id": snapshot_id,
            "created_at": created_at,
            "watermark": watermark,
            "begin_position": begin_position,
            "database_path": database_path.as_posix() if database_path else None,
            "artifact": artifact_path.as_posix() if artifact_path else None,
            "size_bytes": size_bytes,
        }
        manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        LOGGER.info("Wrote snapshot manifest %s", manifest_path.as_posix())

    async def _resolve_watermark(self, connection: asyncpg.Connection) -> int:
        """Get the current WAL watermark (max position)."""
        watermark = await connection.fetchval("SELECT COALESCE(MAX(pos), 0) FROM st_wal")
        return int(watermark) if watermark is not None else 0

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

    def _set_watermark_gauge(self, value: float) -> None:
        """Emit snapshot_watermark gauge metric."""
        if self._metrics is None:
            return
        try:
            self._metrics.set_gauge("snapshot_watermark", value)
        except Exception:  # noqa: BLE001
            LOGGER.exception("Failed to update snapshot watermark gauge")

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
