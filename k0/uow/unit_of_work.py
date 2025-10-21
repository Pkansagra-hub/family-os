"""Unit of work abstraction for the kernel's ACID cohort."""

from __future__ import annotations

import logging
import sqlite3
import time
from contextlib import AbstractContextManager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field, replace
from types import TracebackType
from typing import TYPE_CHECKING, Callable, Iterable, Literal, Protocol

from k0.storage.offsets import Offset, OffsetStore
from k0.storage.outbox import OutboxEntry, OutboxStore
from k0.storage.receipts import Receipt, ReceiptStore
from k0.storage.wal import WalEntry, WriteAheadLog

from .connection_pool import connection_scope

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from k0.obs.metrics import MetricsExporter


class MetricsEmitter(Protocol):
    def __call__(self, metric_name: str, value: float, **labels: str) -> None: ...


_ACTIVE_UOW: ContextVar["UnitOfWork | None"] = ContextVar("k0_active_uow", default=None)


def _default_hook_list() -> list[Callable[[], None]]:
    return []


def _default_outbox_list() -> list[OutboxEntry]:
    return []


def _default_position_list() -> list[int]:
    return []


@dataclass
class UnitOfWork(AbstractContextManager["UnitOfWork"]):
    """Coordinates transactions across WAL, receipts, offsets, and the outbox."""

    outbox_store: OutboxStore | None = None
    write_ahead_log: WriteAheadLog | None = None
    receipt_store: ReceiptStore | None = None
    offset_store: OffsetStore | None = None
    metrics_emitter: MetricsEmitter | None = None
    metrics_exporter: "MetricsExporter | None" = None  # For histogram observations
    snapshot_watermark_gauge: "Callable[[float], None] | None" = (
        None  # For updating WAL watermark
    )
    on_commit: list[Callable[[], None]] = field(default_factory=_default_hook_list)
    on_rollback: list[Callable[[], None]] = field(default_factory=_default_hook_list)
    wal_fsync_mode: Literal["strict", "wal_only", "disabled"] = "strict"
    _scope: AbstractContextManager[sqlite3.Connection] | None = field(
        init=False, default=None
    )
    _connection: sqlite3.Connection | None = field(init=False, default=None)
    _entered: bool = field(init=False, default=False)
    _staged_outbox: list[OutboxEntry] = field(
        init=False, default_factory=_default_outbox_list
    )
    _wal_positions: list[int] = field(
        init=False, default_factory=_default_position_list
    )
    _start_time: float = field(init=False, default=0.0)
    _token: Token["UnitOfWork | None"] | None = field(init=False, default=None)

    def __enter__(self) -> "UnitOfWork":
        if self._entered:
            raise RuntimeError("UnitOfWork instances are not reentrant")
        self._entered = True
        self._scope = connection_scope()
        connection = self._scope.__enter__()
        assert isinstance(connection, sqlite3.Connection)  # runtime safety
        self._connection = connection
        self._connection.execute("BEGIN IMMEDIATE")
        self._start_time = time.perf_counter()
        self._token = _ACTIVE_UOW.set(self)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        logger.info("🔍 DEBUG: __exit__ called with exc_type=%s", exc_type)
        try:
            if exc_type is None:
                logger.info("🔍 DEBUG: No exception, calling _commit()")
                self._commit()
            else:
                logger.warning(
                    "🔍 DEBUG: Exception %s, calling _rollback()",
                    exc_type.__name__,
                )
                self._rollback(reason=exc_type.__name__)
                self._run_hooks(self.on_rollback)
        finally:
            self._cleanup(exc_type, exc, tb)
        # Do not suppress exceptions
        return False

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._connection

    @classmethod
    def current(cls) -> "UnitOfWork | None":
        return _ACTIVE_UOW.get()

    def add_commit_hook(self, hook: Callable[[], None]) -> None:
        self.on_commit.append(hook)

    def add_rollback_hook(self, hook: Callable[[], None]) -> None:
        self.on_rollback.append(hook)

    def stage_outbox(self, entry: OutboxEntry) -> None:
        if not self._entered or self._connection is None:
            raise RuntimeError(
                "Outbox entries can only be staged within an active UnitOfWork"
            )
        staged_entry = replace(entry, id=None)
        self._staged_outbox.append(staged_entry)

    def append_wal(self, entry: WalEntry) -> int:
        if not self._entered or self._connection is None:
            raise RuntimeError(
                "WAL entries can only be appended within an active UnitOfWork"
            )
        if self.write_ahead_log is None:
            raise RuntimeError(
                "WriteAheadLog has not been configured for this UnitOfWork"
            )
        position = self.write_ahead_log.append(entry, connection=self.connection)
        self._wal_positions.append(position)
        return position

    def save_receipt(self, receipt: Receipt) -> None:
        if not self._entered or self._connection is None:
            raise RuntimeError("Receipts can only be saved within an active UnitOfWork")
        if self.receipt_store is None:
            raise RuntimeError(
                "Receipt store has not been configured for this UnitOfWork"
            )
        self.receipt_store.save(receipt, connection=self.connection)

    def upsert_offset(self, record: Offset) -> None:
        if not self._entered or self._connection is None:
            raise RuntimeError(
                "Offsets can only be upserted within an active UnitOfWork"
            )
        if self.offset_store is None:
            raise RuntimeError(
                "Offset store has not been configured for this UnitOfWork"
            )
        self.offset_store.upsert(record, connection=self.connection)

    def _commit(self) -> None:
        if self._connection is None:
            return
        logger.info("🔍 DEBUG: _commit() method called")
        try:
            self._flush_outbox()
            self._connection.commit()
        except BaseException as error:
            self._emit_metric(
                "k0_uow_commit_total",
                1.0,
                outcome="failure",
                error=error.__class__.__name__,
            )
            self._rollback(reason="commit_error")
            self._run_hooks(self.on_rollback)
            raise
        else:
            elapsed = time.perf_counter() - self._start_time
            try:
                fsync_elapsed = self._fsync_wal()
            except BaseException as fsync_error:
                # Use histogram observe for duration metrics
                self._observe_histogram(
                    "uow_commit_seconds",
                    elapsed,
                    outcome="failure",
                )
                self._emit_metric(
                    "k0_uow_commit_total",
                    1.0,
                    outcome="failure",
                    error=fsync_error.__class__.__name__,
                )
                self._emit_metric(
                    "k0_uow_wal_fsync_total",
                    1.0,
                    outcome="failure",
                    error=fsync_error.__class__.__name__,
                )
                raise
            else:
                # Use histogram observe for duration metrics
                self._observe_histogram(
                    "uow_commit_seconds",
                    elapsed,
                    outcome="success",
                )
                if fsync_elapsed is not None:
                    self._observe_histogram(
                        "uow_wal_fsync_seconds",
                        fsync_elapsed,
                        outcome="success",
                    )
                    self._emit_metric(
                        "k0_uow_wal_fsync_total",
                        1.0,
                        outcome="success",
                    )
                self._emit_metric("k0_uow_commit_total", 1.0, outcome="success")
                self._run_hooks(self.on_commit)

                # Update snapshot watermark to current time on successful commit
                if self.snapshot_watermark_gauge is not None:
                    watermark_ts = time.time()
                    logger.info(
                        "🔍 DEBUG: Updating snapshot_watermark to %s",
                        watermark_ts,
                    )
                    self.snapshot_watermark_gauge(watermark_ts)
                    logger.info("🔍 DEBUG: snapshot_watermark update completed")
                else:
                    logger.warning(
                        "🔍 DEBUG: snapshot_watermark_gauge is None, skipping update"
                    )
        finally:
            self._staged_outbox.clear()
            self._wal_positions.clear()

    def _rollback(self, *, reason: str) -> None:
        if self._connection is not None:
            try:
                self._connection.rollback()
            except sqlite3.Error:  # pragma: no cover - defensive guard
                pass
        self._emit_metric(
            "k0_uow_rollback_total",
            1.0,
            outcome="error",
            reason=reason,
        )
        self._staged_outbox.clear()
        self._wal_positions.clear()

    def _flush_outbox(self) -> None:
        if not self._staged_outbox:
            return
        if self.outbox_store is None:
            raise RuntimeError(
                "Outbox store has not been configured for this UnitOfWork"
            )
        for entry in self._staged_outbox:
            self.outbox_store.enqueue(entry, connection=self.connection)

    def _run_hooks(self, hooks: Iterable[Callable[[], None]]) -> None:
        for hook in hooks:
            hook()

    def _emit_metric(self, metric_name: str, value: float, **labels: str) -> None:
        if self.metrics_emitter is None:
            return
        self.metrics_emitter(metric_name, value, **labels)

    def _observe_histogram(self, metric_name: str, value: float, **labels: str) -> None:
        """Emit a histogram observation using MetricsExporter if available."""
        if self.metrics_exporter is not None:
            self.metrics_exporter.observe(
                metric_name,
                value,
                labels=labels,
            )
        elif self.metrics_emitter is not None:
            # Fallback for environments without a MetricsExporter; still emit the
            # observation via the generic emitter so tests can assert behaviour.
            prefixed_name = f"k0_{metric_name}"
            self.metrics_emitter(prefixed_name, value, **labels)

    def _fsync_wal(self) -> float | None:
        if self.write_ahead_log is None or self._connection is None:
            return None
        if self.wal_fsync_mode == "disabled":
            return None
        start = time.perf_counter()
        self.write_ahead_log.fsync(
            connection=self._connection,
            mode=self.wal_fsync_mode,
            metrics_exporter=self.metrics_exporter,
        )
        return time.perf_counter() - start

    def _cleanup(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._scope is not None:
            self._scope.__exit__(exc_type, exc, tb)
        self._scope = None
        self._connection = None
        self._entered = False
        if self._token is not None:
            _ACTIVE_UOW.reset(self._token)
            self._token = None
            self._token = None
            self._token = None
