"""Real chunked SSE client for K0\u2192K1 push streams (MS-3d Epic 3d.2).

Design references:
    docs/architecture/whiteboard_k1/bridge_system_design.md
    \u2022 D12: chunked transport choice (httpx-sse + sse-starlette)
    \u2022 D13: cursor protocol \u2014 ``Last-Event-ID`` header, 24h replay buffer,
            ``replay-gap-detected`` synthetic frame on stale cursor.
    \u2022 D14: backpressure semantics \u2014 block-and-close, never drop. Internal
            queue maxsize ``SSE_INTERNAL_QUEUE_MAXSIZE`` (1000), block-timeout
            ``SSE_BLOCK_TIMEOUT_S`` (30), reconnect backoff
            ``SSE_RECONNECT_BACKOFF_S`` (0.5\u201330s) jittered \u00b120%.
            State machine: HEALTHY (queue<80%) \u2192 PRESSURED (\u226580%) \u2192
            STRESSED (full + blocked >5s) \u2192 CLOSING (blocked >30s) \u2192
            reconnect with cursor \u2192 HEALTHY.

This module is **transport only**. The codegen-emitted subscriber files
(see ``bridge/_generated/<kernel>/handlers/<topic>.py``) hold the typed
seam: they decode each event body into the contract Pydantic model
before invoking the user-supplied handler.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import sqlite3
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, TypeVar

import httpx

if TYPE_CHECKING:  # pragma: no cover - typing only
    from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants \u2014 all values come from D14. Env vars override at process boot.
# ---------------------------------------------------------------------------

SSE_INTERNAL_QUEUE_MAXSIZE_DEFAULT = 1000
SSE_BLOCK_TIMEOUT_S_DEFAULT = 30.0
SSE_RECONNECT_BACKOFF_MIN_S = 0.5
SSE_RECONNECT_BACKOFF_MAX_S = 30.0
SSE_RECONNECT_JITTER = 0.20
SSE_PRESSURE_THRESHOLD = 0.80  # queue \u2265 80% \u21d2 PRESSURED
SSE_STRESS_BLOCKED_S = 5.0  # blocked \u2265 5s \u21d2 STRESSED
SSE_CURSOR_FLUSH_EVENTS = 100
SSE_CURSOR_FLUSH_S = 5.0


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("invalid env %s=%r \u2014 using default %d", name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("invalid env %s=%r \u2014 using default %s", name, raw, default)
        return default


def _queue_maxsize() -> int:
    return _env_int("BRIDGE_SSE_QUEUE_MAXSIZE", SSE_INTERNAL_QUEUE_MAXSIZE_DEFAULT)


def _block_timeout_s() -> float:
    return _env_float("BRIDGE_SSE_BLOCK_TIMEOUT_S", SSE_BLOCK_TIMEOUT_S_DEFAULT)


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


class SSEConnectionState(str, Enum):
    """Connection-level state machine per D14."""

    HEALTHY = "HEALTHY"
    PRESSURED = "PRESSURED"
    STRESSED = "STRESSED"
    CLOSING = "CLOSING"
    DISCONNECTED = "DISCONNECTED"


# ---------------------------------------------------------------------------
# Cursor persistence
# ---------------------------------------------------------------------------


_CURSOR_SCHEMA = """
CREATE TABLE IF NOT EXISTS sse_cursors (
    topic TEXT PRIMARY KEY,
    last_event_id TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


@dataclass
class CursorStore:
    """SQLite-backed last-event-id store at ``~/.familyos/sse_cursors.sqlite``.

    Writes are batched: every ``SSE_CURSOR_FLUSH_EVENTS`` events or
    ``SSE_CURSOR_FLUSH_S`` seconds, whichever comes first. Reads are
    direct (no caching) since they only happen on (re)connect.
    """

    path: Path
    _conn: sqlite3.Connection | None = field(default=None, init=False, repr=False)

    @classmethod
    def default(cls) -> "CursorStore":
        home = Path(os.environ.get("FAMILYOS_HOME", str(Path.home() / ".familyos")))
        home.mkdir(parents=True, exist_ok=True)
        return cls(path=home / "sse_cursors.sqlite")

    def _ensure_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.path, isolation_level=None)
            self._conn.execute(_CURSOR_SCHEMA)
        return self._conn

    def get(self, topic: str) -> str | None:
        conn = self._ensure_conn()
        row = conn.execute(
            "SELECT last_event_id FROM sse_cursors WHERE topic = ?",
            (topic,),
        ).fetchone()
        return row[0] if row else None

    def set(self, topic: str, last_event_id: str) -> None:
        """Synchronously upsert ``last_event_id`` for ``topic``.

        The async :class:`SSEClient` calls :meth:`set_batched` for the hot
        path; this direct method is for tests and explicit flushes.
        """
        conn = self._ensure_conn()
        conn.execute(
            "INSERT INTO sse_cursors(topic, last_event_id) VALUES(?, ?) "
            "ON CONFLICT(topic) DO UPDATE SET "
            "last_event_id = excluded.last_event_id, updated_at = CURRENT_TIMESTAMP",
            (topic, last_event_id),
        )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None


# ---------------------------------------------------------------------------
# Public exceptions
# ---------------------------------------------------------------------------


class SSETransportError(RuntimeError):
    """Raised for unrecoverable SSE wire errors."""


class SSEReplayGapError(SSETransportError):
    """Raised when the K0 server signals the cursor is older than 24h.

    The K0 server emits a synthetic ``replay-gap-detected`` event with
    envelope_kind ``control.replay_gap.v1``; the client surfaces this
    to the caller so consolidation/recovery can trigger a full resync.
    """


class SSEBackpressureTimeoutError(SSETransportError):
    """Raised when the consumer handler has blocked the queue past
    ``SSE_BLOCK_TIMEOUT_S`` (default 30s), forcing a graceful close."""


# ---------------------------------------------------------------------------
# Wire frame
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SSEFrame:
    """Decoded server-sent-event frame (one per ``data:`` block).

    ``envelope_id`` is sourced from the ``id:`` field, which doubles as
    the cursor ack target. ``event`` is the SSE ``event:`` name (the
    contract topic for normal frames, ``replay-gap-detected`` for the
    synthetic gap signal). ``payload`` is the parsed JSON body.
    """

    envelope_id: str
    event: str
    payload: dict[str, Any]


_T = TypeVar("_T", bound="BaseModel")


# ---------------------------------------------------------------------------
# SSE Client
# ---------------------------------------------------------------------------


@dataclass
class SSEClientConfig:
    """Tunable SSE client configuration. Constants come from D14."""

    base_url: str
    """Root URL of the K0 SSE endpoint (e.g. ``http://k0:8080``).

    The full subscribe URL is composed as ``{base_url}/k0/sse/{topic}``.
    """

    queue_maxsize: int = field(default_factory=_queue_maxsize)
    block_timeout_s: float = field(default_factory=_block_timeout_s)
    reconnect_max_attempts: int | None = None  # ``None`` \u21d2 unlimited
    request_timeout_s: float = 60.0
    """Per-request connect/read timeout. Idle SSE streams are kept alive
    by server keepalive pings; this is the *initial* connect budget."""


class SSEClient:
    """Async chunked SSE client with cursor resume + backpressure.

    Lifecycle: construct once per K1 process, share across all
    :class:`<Topic>Subscriber` instances. The shared
    :class:`httpx.AsyncClient` is owned by this class (closed at
    :meth:`aclose`); per-topic state (queue, state machine, last cursor)
    lives in :class:`_TopicSubscription` instances created by
    :meth:`subscribe`.
    """

    def __init__(
        self,
        config: SSEClientConfig,
        *,
        cursor_store: CursorStore | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config
        self._cursor_store = cursor_store or CursorStore.default()
        self._owns_http = http_client is None
        self._http = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(config.request_timeout_s, read=None),
        )

    @property
    def cursor_store(self) -> CursorStore:
        return self._cursor_store

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()
        self._cursor_store.close()

    @asynccontextmanager
    async def subscribe(
        self,
        *,
        topic: str,
        model: type[_T],
        handler: Callable[[_T], Awaitable[None]],
        cursor: str | None = None,
    ) -> AsyncIterator["_TopicSubscription[_T]"]:
        """Open a subscription on ``topic`` and pump events into ``handler``.

        Returns an async-context-manager. On entry, the wire connection
        is opened (resuming from the persisted cursor if no explicit
        ``cursor`` is supplied); on exit, the wire is closed cleanly and
        the last-acknowledged envelope_id is flushed to the cursor
        store.
        """
        sub = _TopicSubscription(
            client=self,
            topic=topic,
            model=model,
            handler=handler,
            initial_cursor=cursor or self._cursor_store.get(topic),
        )
        await sub.start()
        try:
            yield sub
        finally:
            await sub.stop()

    # Internal helper exposed for the subscription class.
    def _http_client(self) -> httpx.AsyncClient:
        return self._http

    def _stream_url(self, topic: str) -> str:
        return f"{self._config.base_url.rstrip('/')}/k0/sse/{topic}"


class _TopicSubscription(Generic[_T]):
    """Per-topic subscription state. Created by :meth:`SSEClient.subscribe`."""

    def __init__(
        self,
        *,
        client: SSEClient,
        topic: str,
        model: type[_T],
        handler: Callable[[_T], Awaitable[None]],
        initial_cursor: str | None,
    ) -> None:
        self._client = client
        self._topic = topic
        self._model = model
        self._handler = handler
        self._cursor = initial_cursor
        self._state = SSEConnectionState.DISCONNECTED
        cfg = client._config
        self._queue: asyncio.Queue[SSEFrame] = asyncio.Queue(maxsize=cfg.queue_maxsize)
        self._pump_task: asyncio.Task[None] | None = None
        self._consume_task: asyncio.Task[None] | None = None
        self._closing = asyncio.Event()
        self._unflushed_count = 0
        self._last_flush_ts = time.monotonic()
        self._reconnect_attempts = 0
        self._first_block_ts: float | None = None

    # ------------------------------------------------------------------
    # Public state surface (used by tests).
    # ------------------------------------------------------------------

    @property
    def state(self) -> SSEConnectionState:
        return self._state

    @property
    def cursor(self) -> str | None:
        return self._cursor

    @property
    def topic(self) -> str:
        return self._topic

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    # ------------------------------------------------------------------
    # Lifecycle.
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._consume_task = asyncio.create_task(
            self._consume_loop(), name=f"sse-consume:{self._topic}"
        )
        self._pump_task = asyncio.create_task(self._pump_loop(), name=f"sse-pump:{self._topic}")

    async def stop(self) -> None:
        self._closing.set()
        # Cancel pump first so no new frames enter the queue.
        if self._pump_task is not None:
            self._pump_task.cancel()
        if self._consume_task is not None:
            self._consume_task.cancel()
        # Await both, capturing the first non-cancellation exception so
        # the subscribe() context manager can surface it.
        first_exc: BaseException | None = None
        for task in (self._pump_task, self._consume_task):
            if task is None:
                continue
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # noqa: BLE001
                if first_exc is None:
                    first_exc = exc
        self._flush_cursor(force=True)
        self._state = SSEConnectionState.DISCONNECTED
        if first_exc is not None:
            raise first_exc

    # ------------------------------------------------------------------
    # Pump loop \u2014 reads chunked SSE frames from the wire onto the queue.
    # ------------------------------------------------------------------

    async def _pump_loop(self) -> None:
        cfg = self._client._config
        url = self._client._stream_url(self._topic)
        while not self._closing.is_set():
            headers = self._build_headers()
            try:
                await self._stream_once(url, headers)
                # Clean EOF \u2014 server closed; break out unless we're meant
                # to keep reconnecting.
                if self._closing.is_set():
                    return
            except SSEReplayGapError:
                # Surface to consume_loop via the queue (already enqueued
                # the synthetic frame) and stop reconnecting; caller must
                # take corrective action.
                self._state = SSEConnectionState.CLOSING
                raise
            except SSEBackpressureTimeoutError:
                # Block-and-close per D14: consumer is stuck, never drop,
                # never silently reconnect. Surface to caller.
                self._state = SSEConnectionState.CLOSING
                raise
            except (httpx.HTTPError, SSETransportError, asyncio.IncompleteReadError) as exc:
                logger.warning("sse_client: pump error topic=%s err=%s", self._topic, exc)
            self._reconnect_attempts += 1
            if (
                cfg.reconnect_max_attempts is not None
                and self._reconnect_attempts >= cfg.reconnect_max_attempts
            ):
                self._state = SSEConnectionState.DISCONNECTED
                return
            self._state = SSEConnectionState.DISCONNECTED
            await self._sleep_backoff()

    def _build_headers(self) -> dict[str, str]:
        h = {"Accept": "text/event-stream", "Cache-Control": "no-cache"}
        if self._cursor:
            h["Last-Event-ID"] = self._cursor
        return h

    async def _stream_once(self, url: str, headers: dict[str, str]) -> None:
        client = self._client._http_client()
        async with client.stream("GET", url, headers=headers) as resp:
            if resp.status_code != 200:
                body = await resp.aread()
                raise SSETransportError(f"SSE connect failed: {resp.status_code} {body!r}")
            self._state = SSEConnectionState.HEALTHY
            self._reconnect_attempts = 0
            async for frame in self._parse_stream(resp):
                if frame.event == "replay-gap-detected":
                    await self._enqueue(frame)
                    raise SSEReplayGapError(
                        f"K0 reported replay gap on {self._topic}: cursor={self._cursor}"
                    )
                await self._enqueue(frame)

    @staticmethod
    async def _parse_stream(resp: httpx.Response) -> AsyncIterator[SSEFrame]:
        """Parse text/event-stream chunks into :class:`SSEFrame`.

        Handles the SSE wire grammar: ``id:``, ``event:``, ``data:``,
        ``retry:`` lines separated by blank lines. Multi-line ``data:``
        is concatenated with newlines. Comments (``: keepalive``) are
        ignored.
        """
        event = "message"
        event_id: str | None = None
        data_parts: list[str] = []
        async for raw_line in resp.aiter_lines():
            line = raw_line.rstrip("\r")
            if line == "":
                if data_parts and event_id is not None:
                    body = "\n".join(data_parts)
                    try:
                        payload = json.loads(body)
                    except json.JSONDecodeError as exc:
                        raise SSETransportError(
                            f"malformed SSE data block: {exc}: {body!r}"
                        ) from exc
                    yield SSEFrame(envelope_id=event_id, event=event, payload=payload)
                event = "message"
                event_id = None
                data_parts = []
                continue
            if line.startswith(":"):
                continue  # comment / keepalive
            if line.startswith("id:"):
                event_id = line[3:].lstrip()
            elif line.startswith("event:"):
                event = line[6:].lstrip()
            elif line.startswith("data:"):
                data_parts.append(line[5:].lstrip())
            # ``retry:`` ignored \u2014 we manage backoff ourselves.

    async def _enqueue(self, frame: SSEFrame) -> None:
        cfg = self._client._config
        # State pre-check: 80% threshold.
        ratio = self._queue.qsize() / cfg.queue_maxsize
        if ratio >= SSE_PRESSURE_THRESHOLD and self._state == SSEConnectionState.HEALTHY:
            self._state = SSEConnectionState.PRESSURED
        # If queue full, block-with-timeout per D14 (block-and-close).
        try:
            self._queue.put_nowait(frame)
            return
        except asyncio.QueueFull:
            pass
        if self._first_block_ts is None:
            self._first_block_ts = time.monotonic()
        deadline = self._first_block_ts + cfg.block_timeout_s
        while True:
            blocked = time.monotonic() - self._first_block_ts
            if blocked >= SSE_STRESS_BLOCKED_S and self._state != SSEConnectionState.STRESSED:
                self._state = SSEConnectionState.STRESSED
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._state = SSEConnectionState.CLOSING
                raise SSEBackpressureTimeoutError(
                    f"SSE consumer blocked >{cfg.block_timeout_s:.1f}s on {self._topic}"
                )
            try:
                await asyncio.wait_for(self._queue.put(frame), timeout=min(remaining, 0.5))
                self._first_block_ts = None
                if self._state == SSEConnectionState.STRESSED:
                    self._state = SSEConnectionState.PRESSURED
                return
            except asyncio.TimeoutError:
                continue

    async def _sleep_backoff(self) -> None:
        attempt = max(1, self._reconnect_attempts)
        base = min(
            SSE_RECONNECT_BACKOFF_MIN_S * (2 ** (attempt - 1)),
            SSE_RECONNECT_BACKOFF_MAX_S,
        )
        jitter = base * SSE_RECONNECT_JITTER
        delay = base + random.uniform(-jitter, jitter)
        delay = max(SSE_RECONNECT_BACKOFF_MIN_S, delay)
        await asyncio.sleep(delay)

    # ------------------------------------------------------------------
    # Consume loop \u2014 drains the queue, decodes payloads, calls handler.
    # ------------------------------------------------------------------

    async def _consume_loop(self) -> None:
        while not self._closing.is_set():
            try:
                frame = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                self._maybe_periodic_flush()
                continue
            if frame.event == "replay-gap-detected":
                # Surface as exception inside the consumer's context.
                raise SSEReplayGapError(
                    f"K0 reported replay gap on {self._topic}: cursor={self._cursor}"
                )
            try:
                instance = self._model.model_validate(frame.payload)
            except Exception:
                logger.exception(
                    "sse_client: payload validation failed topic=%s id=%s",
                    self._topic,
                    frame.envelope_id,
                )
                # Skip the bad event but advance the cursor \u2014 otherwise
                # we'd loop forever on a malformed wire frame. The K0
                # producer is the source of truth; bad frames are bugs
                # to investigate, not data to retry.
                self._advance_cursor(frame.envelope_id)
                continue
            await self._handler(instance)
            self._advance_cursor(frame.envelope_id)

    def _advance_cursor(self, envelope_id: str) -> None:
        self._cursor = envelope_id
        self._unflushed_count += 1
        self._maybe_periodic_flush()

    def _maybe_periodic_flush(self) -> None:
        if self._cursor is None:
            return
        elapsed = time.monotonic() - self._last_flush_ts
        if self._unflushed_count >= SSE_CURSOR_FLUSH_EVENTS or elapsed >= SSE_CURSOR_FLUSH_S:
            self._flush_cursor()

    def _flush_cursor(self, *, force: bool = False) -> None:
        if self._cursor is None:
            return
        if not force and self._unflushed_count == 0:
            return
        self._client._cursor_store.set(self._topic, self._cursor)
        self._unflushed_count = 0
        self._last_flush_ts = time.monotonic()


__all__ = (
    "CursorStore",
    "SSEBackpressureTimeoutError",
    "SSEClient",
    "SSEClientConfig",
    "SSEConnectionState",
    "SSEFrame",
    "SSEReplayGapError",
    "SSETransportError",
)
