"""Shard promotion and WAL synchronization utilities - Async PostgreSQL."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Mapping, Sequence

from k0.db.connection import connection_scope
from k0.obs import MetricsExporter, ObservabilityEmitter

if TYPE_CHECKING:
    import asyncpg


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
    """Synchronise WAL state between a primary/standby pair before promotion - PostgreSQL."""

    def __init__(
        self,
        *,
        shard_id: str,
        primary_dsn: str | None = None,
        standby_dsn: str | None = None,
        metrics: MetricsExporter | None = None,
        observability: ObservabilityEmitter | None = None,
    ) -> None:
        self._shard_id = shard_id
        self._primary_dsn = primary_dsn
        self._standby_dsn = standby_dsn
        self._metrics = metrics
        self._observability = observability

    async def compute_replica_lag(self) -> float:
        """Return the current replica lag in seconds (clamped to >=0)."""
        async with connection_scope() as primary_conn:
            async with connection_scope() as standby_conn:
                lag = await self._compute_lag_seconds(primary_conn, standby_conn)
                self._set_lag_metric(lag)
                return lag

    async def promote(self) -> ShardPromotionResult:
        """Reconcile WAL delta onto the standby replica and emit telemetry."""
        async with connection_scope() as primary_conn:
            async with connection_scope() as standby_conn:
                standby_watermark_before = await self._resolve_watermark(standby_conn)
                primary_watermark_before = await self._resolve_watermark(primary_conn)
                lag_before = await self._compute_lag_seconds(primary_conn, standby_conn)

                delta_entries = await self._fetch_wal_entries(
                    primary_conn, standby_watermark_before
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
                receipts = await self._fetch_receipts(primary_conn, applied_positions)
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
                    await self._upsert_wal_entry(standby_conn, dict(entry))
                for receipt in receipts.values():
                    await self._upsert_receipt(standby_conn, dict(receipt))

                missing_after = await self._find_missing_receipts(standby_conn, applied_positions)
                if missing_after:
                    lag_after_error = await self._compute_lag_seconds(primary_conn, standby_conn)
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
                    msg = f"Receipt parity failed for WAL positions: {sorted(missing_after)}"
                    raise ShardPromotionError(msg)

                lag_after = await self._compute_lag_seconds(primary_conn, standby_conn)
                primary_watermark_after = await self._resolve_watermark(primary_conn)
                standby_watermark_after = await self._resolve_watermark(standby_conn)

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
        with suppress(Exception):
            metrics.emit("shard_promotion_total", 1.0, shard=self._shard_id, outcome=outcome)

    def _emit_event(self, event: str, payload: Mapping[str, object]) -> None:
        emitter = self._observability
        if emitter is None:
            return
        body: dict[str, object] = {"event": event, **payload}
        with suppress(Exception):
            emitter.emit(body)

    def _set_lag_metric(self, value: float) -> None:
        metrics = self._metrics
        if metrics is None:
            return
        with suppress(Exception):
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
        with suppress(Exception):
            metrics.set_gauge(
                "kernel_replay_watermark",
                float(watermark),
                shard=self._shard_id,
            )

    @staticmethod
    async def _compute_lag_seconds(
        primary_conn: asyncpg.Connection,
        standby_conn: asyncpg.Connection,
    ) -> float:
        primary_ts = await ShardPromotionCoordinator._latest_commit_ts(primary_conn)
        standby_ts = await ShardPromotionCoordinator._latest_commit_ts(standby_conn)
        if primary_ts is None or standby_ts is None:
            return 0.0
        delta = (primary_ts - standby_ts).total_seconds()
        return float(delta if delta > 0 else 0.0)

    @staticmethod
    async def _latest_commit_ts(connection: asyncpg.Connection) -> datetime | None:
        row = await connection.fetchrow("SELECT commit_ts FROM st_wal ORDER BY pos DESC LIMIT 1")
        if row is None:
            return None
        commit_ts = row["commit_ts"]
        if not commit_ts:
            return None
        try:
            if isinstance(commit_ts, datetime):
                parsed = commit_ts
            else:
                parsed = datetime.fromisoformat(str(commit_ts))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    async def _resolve_watermark(connection: asyncpg.Connection) -> int:
        watermark = await connection.fetchval("SELECT COALESCE(MAX(pos), 0) FROM st_wal")
        return int(watermark) if watermark is not None else 0

    @staticmethod
    async def _fetch_wal_entries(
        connection: asyncpg.Connection,
        after_position: int,
    ) -> list[asyncpg.Record]:
        return await connection.fetch(
            """
            SELECT pos, tenant_id, space_id, topic, envelope_json, body, payload_sha256,
                   schema_uri, schema_version, idem_key, device_id, commit_ts
            FROM st_wal
            WHERE pos > $1
            ORDER BY pos ASC
            """,
            after_position,
        )

    @staticmethod
    async def _fetch_receipts(
        connection: asyncpg.Connection,
        positions: Sequence[int],
    ) -> dict[int, asyncpg.Record]:
        if not positions:
            return {}
        rows = await connection.fetch(
            """
            SELECT receipt_id, idem_key, wal_pos, commit_ts, tenant_id, space_id,
                   device_id, mls_group_id, key_version, device_sig
            FROM st_receipts
            WHERE wal_pos = ANY($1)
            """,
            list(positions),
        )
        return {int(row["wal_pos"]): row for row in rows}

    @staticmethod
    async def _find_missing_receipts(
        connection: asyncpg.Connection,
        positions: Sequence[int],
    ) -> set[int]:
        if not positions:
            return set()
        rows = await connection.fetch(
            "SELECT wal_pos FROM st_receipts WHERE wal_pos = ANY($1)",
            list(positions),
        )
        present = {int(row["wal_pos"]) for row in rows}
        return {int(pos) for pos in positions if pos not in present}

    @staticmethod
    async def _upsert_wal_entry(
        connection: asyncpg.Connection,
        entry: Mapping[str, object],
    ) -> None:
        await connection.execute(
            """
            INSERT INTO st_wal (
                pos, tenant_id, space_id, topic, envelope_json, body, payload_sha256,
                schema_uri, schema_version, idem_key, device_id, commit_ts
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (pos) DO UPDATE SET
                tenant_id = EXCLUDED.tenant_id,
                space_id = EXCLUDED.space_id,
                topic = EXCLUDED.topic,
                envelope_json = EXCLUDED.envelope_json,
                body = EXCLUDED.body,
                payload_sha256 = EXCLUDED.payload_sha256,
                schema_uri = EXCLUDED.schema_uri,
                schema_version = EXCLUDED.schema_version,
                idem_key = EXCLUDED.idem_key,
                device_id = EXCLUDED.device_id,
                commit_ts = EXCLUDED.commit_ts
            """,
            entry["pos"],
            entry["tenant_id"],
            entry["space_id"],
            entry["topic"],
            entry["envelope_json"],
            entry["body"],
            entry["payload_sha256"],
            entry["schema_uri"],
            entry["schema_version"],
            entry["idem_key"],
            entry["device_id"],
            entry["commit_ts"],
        )

    @staticmethod
    async def _upsert_receipt(
        connection: asyncpg.Connection,
        receipt: Mapping[str, object],
    ) -> None:
        await connection.execute(
            """
            INSERT INTO st_receipts (
                receipt_id, idem_key, wal_pos, commit_ts, tenant_id, space_id,
                device_id, mls_group_id, key_version, device_sig
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (receipt_id) DO UPDATE SET
                idem_key = EXCLUDED.idem_key,
                wal_pos = EXCLUDED.wal_pos,
                commit_ts = EXCLUDED.commit_ts,
                tenant_id = EXCLUDED.tenant_id,
                space_id = EXCLUDED.space_id,
                device_id = EXCLUDED.device_id,
                mls_group_id = EXCLUDED.mls_group_id,
                key_version = EXCLUDED.key_version,
                device_sig = EXCLUDED.device_sig
            """,
            receipt["receipt_id"],
            receipt["idem_key"],
            receipt["wal_pos"],
            receipt["commit_ts"],
            receipt["tenant_id"],
            receipt["space_id"],
            receipt["device_id"],
            receipt["mls_group_id"],
            receipt["key_version"],
            receipt["device_sig"],
        )


__all__ = [
    "ShardPromotionCoordinator",
    "ShardPromotionError",
    "ShardPromotionResult",
]
