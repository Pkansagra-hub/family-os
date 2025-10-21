"""Shard promotion and WAL synchronization utilities."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import ContextManager, Iterable, Iterator, Mapping, Sequence

from k0.obs import MetricsExporter, ObservabilityEmitter


class ShardPromotionError(RuntimeError):
    """Raised when shard promotion prerequisites are not satisfied."""


@dataclass(frozen=True)
class ShardPromotionResult:
    """Summary describing the outcome of a shard promotion run."""

    shard_id: str
    applied_positions: tuple[int, ...]
    lag_before_seconds: float
    lag_after_seconds: float
    primary_watermark: int
    standby_watermark: int


class ShardPromotionCoordinator:
    """Synchronise WAL state between a primary/standby pair before promotion."""

    def __init__(
        self,
        *,
        shard_id: str,
        primary_path: Path | str,
        standby_path: Path | str,
        metrics: MetricsExporter | None = None,
        observability: ObservabilityEmitter | None = None,
    ) -> None:
        self._shard_id = shard_id
        self._primary_path = Path(primary_path)
        self._standby_path = Path(standby_path)
        self._metrics = metrics
        self._observability = observability

    def compute_replica_lag(self) -> float:
        """Return the current replica lag in seconds (clamped to >=0)."""

        with self._connect_primary() as primary_conn, self._connect_standby() as standby_conn:
            lag = self._compute_lag_seconds(primary_conn, standby_conn)
            self._set_lag_metric(lag)
            return lag

    def promote(self) -> ShardPromotionResult:
        """Reconcile WAL delta onto the standby replica and emit telemetry."""

        with self._connect_primary() as primary_conn, self._connect_standby() as standby_conn:
            standby_watermark_before = self._resolve_watermark(standby_conn)
            primary_watermark_before = self._resolve_watermark(primary_conn)
            lag_before = self._compute_lag_seconds(primary_conn, standby_conn)

            delta_entries = tuple(
                self._fetch_wal_entries(primary_conn, standby_watermark_before)
            )
            if not delta_entries:
                self._set_lag_metric(lag_before)
                self._set_watermark_metric(standby_watermark_before)
                self._emit_event(
                    "shard_promotion_noop",
                    {
                        "shard_id": self._shard_id,
                        "lag_seconds": lag_before,
                        "primary_watermark": primary_watermark_before,
                        "standby_watermark": standby_watermark_before,
                    },
                )
                return ShardPromotionResult(
                    shard_id=self._shard_id,
                    applied_positions=(),
                    lag_before_seconds=lag_before,
                    lag_after_seconds=lag_before,
                    primary_watermark=primary_watermark_before,
                    standby_watermark=standby_watermark_before,
                )

            applied_positions = tuple(entry["pos"] for entry in delta_entries)
            receipts = self._fetch_receipts(primary_conn, applied_positions)
            missing_receipts = [pos for pos in applied_positions if pos not in receipts]
            if missing_receipts:
                self._set_lag_metric(lag_before)
                self._emit_event(
                    "shard_promotion_error",
                    {
                        "shard_id": self._shard_id,
                        "reason": "receipts_missing",
                        "positions": missing_receipts,
                        "lag_seconds": lag_before,
                    },
                )
                self._emit_metric("failure")
                msg = f"Receipts missing for WAL positions: {missing_receipts}"
                raise ShardPromotionError(msg)

            self._emit_event(
                "shard_promotion_sync_started",
                {
                    "shard_id": self._shard_id,
                    "positions": applied_positions,
                    "primary_watermark": primary_watermark_before,
                    "standby_watermark": standby_watermark_before,
                    "lag_seconds": lag_before,
                },
            )

            for entry in delta_entries:
                self._upsert_wal_entry(standby_conn, self._row_to_dict(entry))
            for receipt in receipts.values():
                self._upsert_receipt(standby_conn, self._row_to_dict(receipt))
            standby_conn.commit()

            missing_after = self._find_missing_receipts(standby_conn, applied_positions)
            if missing_after:
                lag_after_error = self._compute_lag_seconds(primary_conn, standby_conn)
                self._set_lag_metric(lag_after_error)
                self._emit_event(
                    "shard_promotion_error",
                    {
                        "shard_id": self._shard_id,
                        "reason": "receipt_parity_failed",
                        "positions": sorted(missing_after),
                        "lag_seconds": lag_after_error,
                    },
                )
                self._emit_metric("failure")
                msg = (
                    f"Receipt parity failed for WAL positions: {sorted(missing_after)}"
                )
                raise ShardPromotionError(msg)

            lag_after = self._compute_lag_seconds(primary_conn, standby_conn)
            primary_watermark_after = self._resolve_watermark(primary_conn)
            standby_watermark_after = self._resolve_watermark(standby_conn)

            self._set_lag_metric(lag_after)
            self._set_watermark_metric(standby_watermark_after)
            self._emit_metric("success")
            self._emit_event(
                "shard_promotion_sync_completed",
                {
                    "shard_id": self._shard_id,
                    "positions": applied_positions,
                    "lag_before_seconds": lag_before,
                    "lag_after_seconds": lag_after,
                    "primary_watermark": primary_watermark_after,
                    "standby_watermark": standby_watermark_after,
                },
            )

            return ShardPromotionResult(
                shard_id=self._shard_id,
                applied_positions=applied_positions,
                lag_before_seconds=lag_before,
                lag_after_seconds=lag_after,
                primary_watermark=primary_watermark_after,
                standby_watermark=standby_watermark_after,
            )

    def _emit_metric(self, outcome: str) -> None:
        metrics = self._metrics
        if metrics is None:
            return
        with suppress(Exception):  # pragma: no cover - defensive metrics guard
            metrics.emit(
                "shard_promotion_total", 1.0, shard=self._shard_id, outcome=outcome
            )

    def _emit_event(self, event: str, payload: Mapping[str, object]) -> None:
        emitter = self._observability
        if emitter is None:
            return
        body: dict[str, object] = {"event": event, **payload}
        with suppress(Exception):  # pragma: no cover - defensive observability guard
            emitter.emit(body)

    def _set_lag_metric(self, value: float) -> None:
        metrics = self._metrics
        if metrics is None:
            return
        with suppress(Exception):  # pragma: no cover
            metrics.set_gauge(
                "wal_replica_lag_seconds",
                value,
                shard=self._shard_id,
                role="standby",
            )

    def _set_watermark_metric(self, watermark: int) -> None:
        metrics = self._metrics
        if metrics is None:
            return
        with suppress(Exception):  # pragma: no cover
            metrics.set_gauge(
                "kernel_replay_watermark",
                float(watermark),
                shard=self._shard_id,
            )

    def _connect_primary(self) -> ContextManager[sqlite3.Connection]:
        return self._connect_database(self._primary_path)

    def _connect_standby(self) -> ContextManager[sqlite3.Connection]:
        return self._connect_database(self._standby_path)

    @staticmethod
    def _connect_database(path: Path) -> ContextManager[sqlite3.Connection]:
        @contextmanager
        def _connector() -> Iterator[sqlite3.Connection]:
            connection = sqlite3.connect(path.as_posix())
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout=5000;")
            try:
                yield connection
            finally:
                connection.close()

        return _connector()

    @staticmethod
    def _compute_lag_seconds(
        primary_conn: sqlite3.Connection, standby_conn: sqlite3.Connection
    ) -> float:
        primary_ts = ShardPromotionCoordinator._latest_commit_ts(primary_conn)
        standby_ts = ShardPromotionCoordinator._latest_commit_ts(standby_conn)
        if primary_ts is None or standby_ts is None:
            return 0.0
        delta = (primary_ts - standby_ts).total_seconds()
        return float(delta if delta > 0 else 0.0)

    @staticmethod
    def _latest_commit_ts(connection: sqlite3.Connection) -> datetime | None:
        row = connection.execute(
            "SELECT commit_ts FROM st_wal ORDER BY pos DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        commit_ts = row["commit_ts"]
        if not commit_ts:
            return None
        try:
            parsed = datetime.fromisoformat(commit_ts)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _resolve_watermark(connection: sqlite3.Connection) -> int:
        row = connection.execute(
            "SELECT COALESCE(MAX(pos), 0) AS watermark FROM st_wal"
        ).fetchone()
        if row is None:
            return 0
        return int(row["watermark"])

    @staticmethod
    def _fetch_wal_entries(
        connection: sqlite3.Connection, after_position: int
    ) -> Iterable[sqlite3.Row]:
        return connection.execute(
            (
                "SELECT pos, tenant_id, space_id, topic, envelope_json, body, payload_sha256, "
                "schema_uri, schema_version, idem_key, device_id, commit_ts "
                "FROM st_wal WHERE pos > ? ORDER BY pos ASC"
            ),
            (after_position,),
        )

    @staticmethod
    def _fetch_receipts(
        connection: sqlite3.Connection,
        positions: Sequence[int],
    ) -> dict[int, sqlite3.Row]:
        if not positions:
            return {}
        placeholders = ",".join(["?"] * len(positions))
        query = (
            "SELECT receipt_id, idem_key, wal_pos, commit_ts, tenant_id, space_id, device_id, "
            "mls_group_id, key_version, device_sig FROM st_receipts WHERE wal_pos IN ("
            f"{placeholders}"
            ")"
        )
        rows = connection.execute(query, tuple(positions)).fetchall()
        return {int(row["wal_pos"]): row for row in rows}

    @staticmethod
    def _find_missing_receipts(
        connection: sqlite3.Connection, positions: Sequence[int]
    ) -> set[int]:
        if not positions:
            return set()
        placeholders = ",".join(["?"] * len(positions))
        query = (
            "SELECT wal_pos FROM st_receipts WHERE wal_pos IN (" f"{placeholders}" ")"
        )
        rows = connection.execute(query, tuple(positions)).fetchall()
        present = {int(row["wal_pos"]) for row in rows}
        return {int(pos) for pos in positions if pos not in present}

    @staticmethod
    def _upsert_wal_entry(
        connection: sqlite3.Connection, entry: Mapping[str, object]
    ) -> None:
        connection.execute(
            (
                "INSERT INTO st_wal (pos, tenant_id, space_id, topic, envelope_json, body, payload_sha256, "
                "schema_uri, schema_version, idem_key, device_id, commit_ts) "
                "VALUES (:pos, :tenant_id, :space_id, :topic, :envelope_json, :body, :payload_sha256, :schema_uri, "
                ":schema_version, :idem_key, :device_id, :commit_ts) "
                "ON CONFLICT(pos) DO UPDATE SET "
                "tenant_id=excluded.tenant_id, space_id=excluded.space_id, topic=excluded.topic, "
                "envelope_json=excluded.envelope_json, body=excluded.body, payload_sha256=excluded.payload_sha256, "
                "schema_uri=excluded.schema_uri, schema_version=excluded.schema_version, idem_key=excluded.idem_key, "
                "device_id=excluded.device_id, commit_ts=excluded.commit_ts"
            ),
            entry,
        )

    @staticmethod
    def _upsert_receipt(
        connection: sqlite3.Connection, receipt: Mapping[str, object]
    ) -> None:
        connection.execute(
            (
                "INSERT INTO st_receipts (receipt_id, idem_key, wal_pos, commit_ts, tenant_id, space_id, device_id, "
                "mls_group_id, key_version, device_sig) "
                "VALUES (:receipt_id, :idem_key, :wal_pos, :commit_ts, :tenant_id, :space_id, :device_id, :mls_group_id, "
                ":key_version, :device_sig) "
                "ON CONFLICT(receipt_id) DO UPDATE SET "
                "idem_key=excluded.idem_key, wal_pos=excluded.wal_pos, commit_ts=excluded.commit_ts, "
                "tenant_id=excluded.tenant_id, space_id=excluded.space_id, device_id=excluded.device_id, "
                "mls_group_id=excluded.mls_group_id, key_version=excluded.key_version, device_sig=excluded.device_sig"
            ),
            receipt,
        )

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, object]:
        return {key: row[key] for key in row.keys()}


__all__ = [
    "ShardPromotionCoordinator",
    "ShardPromotionError",
    "ShardPromotionResult",
]
