"""Post-commit dispatch coordinator."""

from __future__ import annotations

import asyncio
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime, timezone
from operator import attrgetter
from time import perf_counter
from typing import Awaitable, Callable, Iterable, List

from k0.qos import Scheduler, SchedulerToken

BusSink = Callable[["BusMessage"], Awaitable[None]]
BandResolver = Callable[["BusMessage"], str]


@dataclass(slots=True)
class BusMessage:
    """Immutable view of a post-commit WAL record to dispatch."""

    topic: str
    payload: bytes
    offset: int
    trace_id: str | None = None


@dataclass(slots=True)
class BusDispatchContext:
    """Runtime context exposed to bus middleware and sinks."""

    message: BusMessage
    band: str
    port: str
    token_cost: int
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    monotonic_start: float | None = None
    monotonic_end: float | None = None
    trace_id: str | None = None


BusMiddlewareHandler = Callable[[BusDispatchContext], Awaitable[None]]
BusMiddleware = Callable[[BusDispatchContext, BusMiddlewareHandler], Awaitable[None]]


_DISPATCH_CONTEXT: ContextVar[BusDispatchContext | None] = ContextVar(
    "k0_bus_dispatch_context",
    default=None,
)


def current_dispatch_context() -> BusDispatchContext | None:
    """Return the current bus dispatch context, if any."""

    return _DISPATCH_CONTEXT.get()


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


class BusDispatcher:
    """Fan out WAL commits to SSE and driver outbox facades."""

    def __init__(
        self,
        *,
        scheduler: Scheduler,
        sinks: Iterable[BusSink] | None = None,
        port: str = "bus",
        default_band: str = "GREEN",
        token_cost: int = 1,
        band_resolver: BandResolver | None = None,
        middlewares: Iterable[BusMiddleware] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if token_cost <= 0:
            raise ValueError("token_cost must be positive")
        self._scheduler = scheduler
        self._sinks: List[BusSink] = list(sinks or [])
        port_value = port.strip()
        if not port_value:
            raise ValueError("port must be a non-empty string")
        band_value = default_band.strip()
        if not band_value:
            raise ValueError("default_band must be a non-empty string")
        self._port = port_value
        self._default_band = band_value.upper()
        self._token_cost = token_cost
        self._band_resolver = band_resolver
        self._middlewares: List[BusMiddleware] = list(middlewares or [])
        self._clock = clock or _default_clock
        self._lock = asyncio.Lock()
        self._last_offset: int | None = None

    def register_sink(self, sink: BusSink) -> None:
        """Register an asynchronous sink invoked for every bus message."""

        if not callable(sink):
            raise TypeError("bus sink must be callable")
        self._sinks.append(sink)

    def register_middleware(self, middleware: BusMiddleware) -> None:
        """Register a middleware invoked around bus fan-out."""

        if not callable(middleware):
            raise TypeError("bus middleware must be callable")
        self._middlewares.append(middleware)

    @property
    def middlewares(self) -> tuple[BusMiddleware, ...]:
        """Return the configured middleware chain."""

        return tuple(self._middlewares)

    async def dispatch(self, messages: Iterable[BusMessage]) -> None:
        """Dispatch *messages* in WAL order using scheduler tokens."""

        batch = list(messages)
        if not batch:
            return

        batch.sort(key=attrgetter("offset"))

        async with self._lock:
            for message in batch:
                self._ensure_monotonic(message.offset)
                if self._sinks:
                    await self._dispatch_single(message)
                self._last_offset = message.offset

    def _ensure_monotonic(self, offset: int) -> None:
        if self._last_offset is not None and offset < self._last_offset:
            msg = "WAL offsets must be provided in non-decreasing order"
            raise ValueError(msg)

    async def _dispatch_single(self, message: BusMessage) -> None:
        band = self._resolve_band(message)
        token: SchedulerToken | None = None
        context_token: Token[BusDispatchContext | None] | None = None
        start_tick: float | None = None
        try:
            token = self._scheduler.acquire(
                band=band,
                port=self._port,
                cost=self._token_cost,
            )
            context = BusDispatchContext(
                message=message,
                band=band,
                port=self._port,
                token_cost=self._token_cost,
                started_at=self._clock(),
                trace_id=message.trace_id,
            )
            context_token = _DISPATCH_CONTEXT.set(context)
            start_tick = perf_counter()
            context.monotonic_start = start_tick
            try:
                await self._execute_middlewares(context)
            finally:
                end_tick = perf_counter()
                context.monotonic_end = end_tick
                if context.completed_at is None:
                    context.completed_at = self._clock()
                if context.duration_seconds is None:
                    context.duration_seconds = max(0.0, end_tick - start_tick)
        finally:
            if context_token is not None:
                _DISPATCH_CONTEXT.reset(context_token)
            if token is not None:
                token.release()

    def _resolve_band(self, message: BusMessage) -> str:
        if self._band_resolver is None:
            return self._default_band

        band = self._band_resolver(message)
        try:
            candidate = band.strip()
        except AttributeError as exc:  # pragma: no cover - defensive guard
            raise TypeError("band_resolver must return a string") from exc
        if not candidate:
            raise ValueError("band_resolver must return a non-empty string")
        return candidate.upper()

    async def _execute_middlewares(self, context: BusDispatchContext) -> None:
        if not self._sinks:
            return

        if not self._middlewares:
            await self._fan_out(context)
            return

        async def invoke(index: int, ctx: BusDispatchContext) -> None:
            if index >= len(self._middlewares):
                await self._fan_out(ctx)
                return

            async def next_handler(next_ctx: BusDispatchContext) -> None:
                await invoke(index + 1, next_ctx)

            await self._middlewares[index](ctx, next_handler)

        await invoke(0, context)

    async def _fan_out(self, context: BusDispatchContext) -> None:
        message = context.message
        tasks: List[asyncio.Task[None]] = []
        for sink in self._sinks:
            result = sink(message)
            if not asyncio.iscoroutine(result):
                raise TypeError("bus sink must return a coroutine")
            tasks.append(asyncio.create_task(result))

        if tasks:
            await asyncio.gather(*tasks)
