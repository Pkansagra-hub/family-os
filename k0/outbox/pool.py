"""Driver worker pool and handshake coordination for outbox processing."""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from typing import Any, Callable, Dict, Mapping, Sequence
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlparse

from k0.drivers.alias_map import AliasMap
from k0.storage.dlq import DeadLetterQueue
from k0.storage.outbox import OutboxEntry, OutboxStore

from .scheduler import RetryScheduler
from .worker import (
    MetricsEmitter,
    OutboxDriver,
    OutboxWorker,
    load_driver_from_alias_map,
)


def _serialize_entry(entry: OutboxEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "wal_pos": entry.wal_pos,
        "tenant_id": entry.tenant_id,
        "space_id": entry.space_id,
        "driver": entry.driver,
        "op_kind": entry.op_kind,
        "payload_base64": base64.b64encode(entry.payload).decode("ascii"),
        "fingerprint": entry.fingerprint,
        "requeue_seq": entry.requeue_seq,
        "retries": entry.retries,
        "last_error": entry.last_error,
    }


@dataclass(slots=True)
class DriverSession:
    """Represents an active handshake session for a driver alias."""

    session_id: str
    alias: str
    driver_module: str
    transport: str
    endpoint: str
    capabilities: tuple[str, ...]
    metadata: Mapping[str, Any]
    issued_at: datetime
    expires_at: datetime


@dataclass(slots=True)
class DriverHandshakeError(Exception):
    """Error raised when a driver handshake request cannot be satisfied."""

    code: str
    status_code: int
    reason: str
    hint: str | None = None

    def __str__(self) -> str:  # pragma: no cover - diagnostic helper
        hint_segment = f" ({self.hint})" if self.hint else ""
        return f"{self.code}: {self.reason}{hint_segment}"


class HTTPDriverAdapter:
    """Outbox driver adapter that forwards apply calls to an HTTP endpoint."""

    def __init__(
        self,
        *,
        endpoint: str,
        session_id: str,
        timeout: float = 5.0,
    ) -> None:
        self._endpoint = endpoint
        self._session_id = session_id
        self._timeout = timeout

    def apply(self, entry: OutboxEntry) -> None:
        payload = json.dumps(
            _serialize_entry(entry),
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        request = urllib_request.Request(
            self._endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-K0-Driver-Session": self._session_id,
            },
            method="POST",
        )
        try:
            with urllib_request.urlopen(request, timeout=self._timeout) as response:
                if response.status >= 300:
                    msg = f"remote driver responded with status {response.status}"
                    raise RuntimeError(msg)
        except urllib_error.URLError as exc:  # pragma: no cover - network error guard
            raise RuntimeError(
                "failed to deliver outbox entry to remote driver"
            ) from exc


class DriverWorkerPool:
    """Manage outbox workers and driver handshakes."""

    def __init__(
        self,
        *,
        alias_map: AliasMap,
        outbox_store: OutboxStore,
        dead_letter_queue: DeadLetterQueue,
        retry_scheduler_factory: Callable[[], RetryScheduler],
        metrics_emitter: MetricsEmitter | None = None,
        batch_size: int = 128,
        clock: Callable[[], datetime] | None = None,
        lease_seconds: int = 300,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be greater than zero")

        self._alias_map = alias_map
        self._alias_loader = load_driver_from_alias_map(alias_map)
        self._outbox_store = outbox_store
        self._dead_letter_queue = dead_letter_queue
        self._retry_scheduler_factory = retry_scheduler_factory
        self._metrics_emitter = metrics_emitter
        self._batch_size = batch_size
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lease_seconds = lease_seconds

        self._workers: Dict[str, OutboxWorker] = {}
        self._driver_overrides: Dict[str, OutboxDriver] = {}
        self._sessions: Dict[str, DriverSession] = {}
        self._alias_sessions: Dict[str, str] = {}

    @property
    def lease_seconds(self) -> int:
        return self._lease_seconds

    def register_handshake(
        self,
        *,
        alias: str,
        transport: str,
        endpoint: str,
        capabilities: Sequence[str] | None = None,
        metadata: Mapping[str, Any] | None = None,
        lease_seconds: int | None = None,
    ) -> DriverSession:
        self._cleanup_expired_sessions()

        normalized_alias = alias.strip()
        if not normalized_alias:
            raise DriverHandshakeError(
                code="DRIVER_HANDSHAKE_INVALID",
                status_code=int(HTTPStatus.BAD_REQUEST),
                reason="alias must not be empty",
            )

        try:
            driver_module = self._alias_map.resolve(normalized_alias)
        except KeyError as exc:  # pragma: no cover - defensive map guard
            raise DriverHandshakeError(
                code="DRIVER_ALIAS_NOT_FOUND",
                status_code=int(HTTPStatus.NOT_FOUND),
                reason=f"Driver alias '{normalized_alias}' not found",
                hint="Verify drivers/alias_map.yaml contains the alias",
            ) from exc

        normalized_transport = transport.strip().lower()
        if normalized_transport not in {"http", "grpc"}:
            raise DriverHandshakeError(
                code="DRIVER_HANDSHAKE_INVALID",
                status_code=int(HTTPStatus.BAD_REQUEST),
                reason="transport must be 'http' or 'grpc'",
            )

        normalized_endpoint = endpoint.strip()
        if not normalized_endpoint:
            raise DriverHandshakeError(
                code="DRIVER_HANDSHAKE_INVALID",
                status_code=int(HTTPStatus.BAD_REQUEST),
                reason="endpoint must not be empty",
            )

        if normalized_transport == "http":
            parsed = urlparse(normalized_endpoint)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise DriverHandshakeError(
                    code="DRIVER_HANDSHAKE_INVALID",
                    status_code=int(HTTPStatus.BAD_REQUEST),
                    reason="HTTP transport requires a valid http(s) URL",
                    hint="Provide an endpoint such as https://indexer.local/apply",
                )
        else:
            if "://" not in normalized_endpoint and ":" not in normalized_endpoint:
                raise DriverHandshakeError(
                    code="DRIVER_HANDSHAKE_INVALID",
                    status_code=int(HTTPStatus.BAD_REQUEST),
                    reason="gRPC transport requires a scheme or host:port",
                    hint="Provide endpoints like dns:///indexer:7443",
                )

        bound_capabilities: tuple[str, ...]
        if capabilities:
            seen: set[str] = set()
            deduped: list[str] = []
            for item in capabilities:
                candidate = item.strip()
                if not candidate:
                    raise DriverHandshakeError(
                        code="DRIVER_HANDSHAKE_INVALID",
                        status_code=int(HTTPStatus.BAD_REQUEST),
                        reason="capabilities entries must not be empty",
                    )
                if candidate in seen:
                    continue
                seen.add(candidate)
                deduped.append(candidate)
            bound_capabilities = tuple(deduped)
        else:
            bound_capabilities = ()

        session_id = uuid.uuid4().hex
        issued_at = self._clock()
        ttl_seconds = lease_seconds or self._lease_seconds
        expires_at = issued_at + timedelta(seconds=ttl_seconds)

        session_metadata: Mapping[str, Any]
        if metadata:
            session_metadata = dict(metadata)
        else:
            session_metadata = {}

        session = DriverSession(
            session_id=session_id,
            alias=normalized_alias,
            driver_module=driver_module,
            transport=normalized_transport,
            endpoint=normalized_endpoint,
            capabilities=bound_capabilities,
            metadata=session_metadata,
            issued_at=issued_at,
            expires_at=expires_at,
        )

        self._sessions[session_id] = session
        self._alias_sessions[normalized_alias] = session_id

        if normalized_transport == "http":
            self._register_http_driver(session)

        if self._metrics_emitter is not None:
            self._metrics_emitter(
                "k0_driver_handshakes_total",
                1.0,
                alias=normalized_alias,
                transport=normalized_transport,
                outcome="accepted",
            )

        return session

    def process_driver(self, alias: str, *, limit: int | None = None) -> None:
        worker = self._ensure_worker(alias)
        worker.process_driver(alias, limit=limit)

    def get_session(self, session_id: str) -> DriverSession | None:
        self._cleanup_expired_sessions()
        return self._sessions.get(session_id)

    def active_sessions(self, alias: str) -> list[DriverSession]:
        self._cleanup_expired_sessions()
        return [
            session for session in self._sessions.values() if session.alias == alias
        ]

    def _ensure_worker(self, alias: str) -> OutboxWorker:
        worker = self._workers.get(alias)
        if worker is not None:
            return worker
        worker = OutboxWorker(
            outbox_store=self._outbox_store,
            dead_letter_queue=self._dead_letter_queue,
            retry_scheduler=self._retry_scheduler_factory(),
            driver_loader=self._resolve_driver,
            metrics_emitter=self._metrics_emitter,
            batch_size=self._batch_size,
        )
        self._workers[alias] = worker
        return worker

    def _resolve_driver(self, alias: str) -> OutboxDriver:
        override = self._driver_overrides.get(alias)
        if override is not None:
            return override
        return self._alias_loader(alias)

    def _register_http_driver(self, session: DriverSession) -> None:
        adapter = HTTPDriverAdapter(
            endpoint=session.endpoint,
            session_id=session.session_id,
        )
        self._driver_overrides[session.alias] = adapter
        worker = self._ensure_worker(session.alias)
        worker.register_driver(session.alias, adapter)

    def _cleanup_expired_sessions(self) -> None:
        now = self._clock()
        expired: list[str] = [
            session_id
            for session_id, session in list(self._sessions.items())
            if session.expires_at <= now
        ]
        for session_id in expired:
            session = self._sessions.pop(session_id)
            current_binding = self._alias_sessions.get(session.alias)
            if current_binding == session_id:
                self._alias_sessions.pop(session.alias, None)
                self._driver_overrides.pop(session.alias, None)
                worker = self._workers.get(session.alias)
                if worker is not None:
                    worker.unregister_driver(session.alias)


__all__ = [
    "DriverWorkerPool",
    "DriverSession",
    "DriverHandshakeError",
]
