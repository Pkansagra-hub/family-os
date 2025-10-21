"""Outbox worker implementation with retry scheduling and DLQ fallback."""

from __future__ import annotations

from datetime import datetime, timezone
from importlib import import_module
from typing import Callable, Dict, Optional, Protocol, cast

from k0.drivers.alias_map import AliasMap
from k0.storage.dlq import DeadLetter, DeadLetterQueue
from k0.storage.outbox import OutboxEntry, OutboxStore

from .scheduler import RetryScheduler


class MetricsEmitter(Protocol):
    def __call__(self, metric_name: str, value: float, **labels: str) -> None: ...


class OutboxDriver(Protocol):
    """Protocol describing the expected driver apply interface."""

    def apply(self, entry: OutboxEntry) -> None: ...


def load_driver_from_alias_map(alias_map: AliasMap) -> Callable[[str], OutboxDriver]:
    """Return a driver loader that resolves aliases via *alias_map*."""

    def _loader(alias: str) -> OutboxDriver:
        driver_key = alias_map.resolve(alias)
        module = import_module(f"k0.drivers.{driver_key}")
        driver: object | None = None
        builder = getattr(module, "build_driver", None)
        if callable(builder):
            driver = builder()
        else:
            driver_cls = getattr(module, "Driver", None)
            if driver_cls is not None:
                driver = driver_cls()
            else:
                candidate = getattr(module, "driver", None)
                if candidate is not None:
                    driver = candidate() if callable(candidate) else candidate

        if driver is None:
            msg = f"Driver module '{driver_key}' does not expose a known factory"
            raise RuntimeError(msg)

        if not hasattr(driver, "apply") or not callable(getattr(driver, "apply")):
            msg = f"Driver '{driver_key}' must expose an 'apply' method"
            raise RuntimeError(msg)

        return cast(OutboxDriver, driver)

    return _loader


class OutboxWorker:
    """Drain driver queues with retry scheduling and DLQ fallback."""

    def __init__(
        self,
        *,
        outbox_store: OutboxStore,
        dead_letter_queue: DeadLetterQueue,
        retry_scheduler: RetryScheduler,
        driver_loader: Callable[[str], OutboxDriver],
        metrics_emitter: MetricsEmitter | None = None,
        clock: Callable[[], datetime] | None = None,
        batch_size: int = 128,
    ) -> None:
        if batch_size <= 0:
            msg = "batch_size must be greater than zero"
            raise ValueError(msg)

        self._outbox_store = outbox_store
        self._dead_letter_queue = dead_letter_queue
        self._retry_scheduler = retry_scheduler
        self._driver_loader = driver_loader
        self._metrics_emitter = metrics_emitter
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._batch_size = batch_size
        self._drivers: Dict[str, OutboxDriver] = {}

    def process_driver(self, alias: str, *, limit: Optional[int] = None) -> None:
        """Drain pending outbox entries for the given driver alias."""

        driver = self._get_driver(alias)
        batch_limit = limit or self._batch_size
        entries = self._outbox_store.dequeue_batch(alias, limit=batch_limit)
        if not entries:
            return

        for entry in entries:
            if entry.id is None:
                continue
            try:
                driver.apply(entry)
            except Exception as error:  # noqa: BLE001
                self._handle_failure(alias, entry, error)
            else:
                self._outbox_store.mark_applied(entry.id)
                self._emit_metric(
                    "k0_outbox_apply_total", 1.0, outcome="success", driver=alias
                )

    def _get_driver(self, alias: str) -> OutboxDriver:
        driver = self._drivers.get(alias)
        if driver is not None:
            return driver
        driver = self._driver_loader(alias)
        self._drivers[alias] = driver
        return driver

    def _handle_failure(self, alias: str, entry: OutboxEntry, error: Exception) -> None:
        message = str(error)
        if len(message) > 512:
            message = message[:512]
        decision = self._retry_scheduler.decide(entry)

        if decision.action == "retry":
            self._outbox_store.record_failure(
                entry,
                retries=decision.retries,
                requeue_seq=decision.requeue_seq,
                last_error=message,
            )
            self._emit_metric(
                "k0_outbox_apply_total", 1.0, outcome="retry", driver=alias
            )
            return

        timestamp = self._clock().isoformat()
        reason = f"{alias}:{error.__class__.__name__}"
        if message:
            reason = f"{reason}:{message}"
        if len(reason) > 512:
            reason = reason[:512]
        self._dead_letter_queue.record(
            DeadLetter(
                id=None,
                wal_pos=entry.wal_pos,
                tenant_id=entry.tenant_id,
                space_id=entry.space_id,
                driver=entry.driver,
                op_kind=entry.op_kind,
                fingerprint=entry.fingerprint,
                payload=entry.payload,
                reason=reason,
                retries=decision.retries,
                requeue_seq=entry.requeue_seq,
                first_failure_ts=timestamp,
                last_failure_ts=timestamp,
                state="PENDING",
            )
        )
        if entry.id is not None:
            self._outbox_store.mark_applied(entry.id)
        self._emit_metric(
            "k0_outbox_apply_total", 1.0, outcome="quarantine", driver=alias
        )

    def _emit_metric(self, metric_name: str, value: float, **labels: str) -> None:
        if self._metrics_emitter is None:
            return
        self._metrics_emitter(metric_name, value, **labels)

    def register_driver(self, alias: str, driver: OutboxDriver) -> None:
        """Inject or replace the driver instance cached for *alias*."""

        self._drivers[alias] = driver

    def unregister_driver(self, alias: str) -> None:
        """Remove any cached driver instance for *alias*."""

        self._drivers.pop(alias, None)
