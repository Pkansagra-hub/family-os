"""Idempotency ledger interface."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from k0.obs import MetricsExporter, ObservabilityEmitter
from k0.uow.connection_pool import connection_scope

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class LedgerEntry:
    idem_key: str
    receipt_id: str
    first_seen_ts: str
    state: str
    expiry_ts: str | None = None


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


class IdempotencyLedger:
    """Thin abstraction over the storage-backed idempotency ledger."""

    def __init__(
        self,
        *,
        metrics: MetricsExporter | None = None,
        observability: ObservabilityEmitter | None = None,
    ) -> None:
        self._metrics = metrics
        self._observability = observability

    def attach_metrics_exporter(self, metrics: MetricsExporter | None) -> None:
        """Attach or replace the metrics exporter used for ledger telemetry."""

        self._metrics = metrics

    def attach_observability_emitter(
        self, emitter: ObservabilityEmitter | None
    ) -> None:
        """Attach or replace the observability emitter used for ledger events."""

        self._observability = emitter

    def lookup(
        self,
        idem_key: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> LedgerEntry | None:
        with _resolve_connection(connection) as conn:
            row = conn.execute(
                "SELECT idem_key, receipt_id, first_seen_ts, state, expiry_ts FROM idem_ledger WHERE idem_key = ?",
                (idem_key,),
            ).fetchone()
            if row is None:
                self._emit_lookup_telemetry(idem_key, None, outcome="miss")
                return None
            entry = LedgerEntry(
                idem_key=row["idem_key"],
                receipt_id=row["receipt_id"],
                first_seen_ts=row["first_seen_ts"],
                state=row["state"],
                expiry_ts=row["expiry_ts"],
            )
            self._emit_lookup_telemetry(idem_key, entry, outcome="hit")
            return entry

    def upsert(
        self,
        entry: LedgerEntry,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        with _resolve_connection(connection) as conn:
            conn.execute(
                (
                    "INSERT INTO idem_ledger (idem_key, receipt_id, first_seen_ts, state, expiry_ts) "
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(idem_key) DO UPDATE SET receipt_id=excluded.receipt_id, "
                    "first_seen_ts=excluded.first_seen_ts, state=excluded.state, expiry_ts=excluded.expiry_ts"
                ),
                (
                    entry.idem_key,
                    entry.receipt_id,
                    entry.first_seen_ts,
                    entry.state,
                    entry.expiry_ts,
                ),
            )
        self._emit_upsert_telemetry(entry)

    def _emit_lookup_telemetry(
        self,
        idem_key: str,
        entry: LedgerEntry | None,
        *,
        outcome: str,
    ) -> None:
        state_label = entry.state if entry is not None else "NONE"
        metrics = self._metrics
        if metrics is not None:
            try:
                metrics.emit(
                    "k0_idem_lookup",
                    outcome=outcome,
                    state=state_label,
                )
                if outcome == "hit" and entry is not None:
                    metrics.emit("k0_idem_duplicate_detected", state=state_label)
            except Exception:  # pragma: no cover - defensive guard  # noqa: BLE001
                LOGGER.exception(
                    "Failed to emit idempotency lookup metric",
                    extra={"idem_key": idem_key, "outcome": outcome},
                )

        emitter = self._observability
        if emitter is not None:
            payload: dict[str, object] = {
                "event": "idem_ledger_lookup",
                "outcome": outcome,
                "idem_key": idem_key,
                "state": state_label,
            }
            if entry is not None:
                payload["receipt_id"] = entry.receipt_id
                payload["first_seen_ts"] = entry.first_seen_ts
                if entry.expiry_ts is not None:
                    payload["expiry_ts"] = entry.expiry_ts
            try:
                emitter.emit(payload)
            except Exception:  # pragma: no cover - defensive guard  # noqa: BLE001
                LOGGER.exception(
                    "Failed to emit idempotency lookup event",
                    extra={"idem_key": idem_key, "outcome": outcome},
                )

    def _emit_upsert_telemetry(self, entry: LedgerEntry) -> None:
        metrics = self._metrics
        if metrics is not None:
            try:
                metrics.emit(
                    "k0_idem_commit_recorded",
                    state=entry.state,
                )
            except Exception:  # pragma: no cover - defensive guard  # noqa: BLE001
                LOGGER.exception(
                    "Failed to emit idempotency upsert metric",
                    extra={"idem_key": entry.idem_key},
                )

        emitter = self._observability
        if emitter is not None:
            payload: dict[str, object] = {
                "event": "idem_ledger_upsert",
                "idem_key": entry.idem_key,
                "receipt_id": entry.receipt_id,
                "state": entry.state,
                "first_seen_ts": entry.first_seen_ts,
            }
            if entry.expiry_ts is not None:
                payload["expiry_ts"] = entry.expiry_ts
            try:
                emitter.emit(payload)
            except Exception:  # pragma: no cover - defensive guard  # noqa: BLE001
                LOGGER.exception(
                    "Failed to emit idempotency upsert event",
                    extra={"idem_key": entry.idem_key},
                )
