"""K1 Layer 1→2 event bus implementation."""

from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Awaitable, Callable, Dict, List, Optional

from k1.l5_infrastructure.event_bus.schemas import EventBase, EventTopic
from k1.l5_infrastructure.observability import get_metrics, get_tracer

try:  # pragma: no cover - structlog optional at runtime
    import structlog  # type: ignore

    logger = structlog.get_logger(__name__)  # type: ignore
except ImportError:  # pragma: no cover - fallback to stdlib logging
    import logging

    class _StructLogShim:
        """Minimal shim to emulate structlog-style API on stdlib logging."""

        def __init__(self, base_logger: logging.Logger) -> None:
            self._base_logger = base_logger

        def _emit(self, level: int, event: str, **kwargs: object) -> None:
            if kwargs:
                self._base_logger.log(level, "%s %s", event, kwargs)
            else:
                self._base_logger.log(level, "%s", event)

        def debug(self, event: str, **kwargs: object) -> None:
            self._emit(logging.DEBUG, event, **kwargs)

        def info(self, event: str, **kwargs: object) -> None:
            self._emit(logging.INFO, event, **kwargs)

        def warning(self, event: str, **kwargs: object) -> None:
            self._emit(logging.WARNING, event, **kwargs)

        def exception(self, event: str, **kwargs: object) -> None:
            self._base_logger.exception("%s %s", event, kwargs)

    logger = _StructLogShim(logging.getLogger(__name__))


EventHandler = Callable[[EventBase], Awaitable[None] | None]


@dataclass(slots=True)
class SubscriptionHandle:
    """Handle returned to callers for managing a subscription."""

    topic_pattern: str
    handler_repr: str
    _bus: "EventBus" = field(repr=False)
    _subscriber_id: int = field(repr=False)

    async def unsubscribe(self) -> None:
        """Remove the subscription and cancel the background delivery task."""

        await self._bus.remove_subscription(self._subscriber_id)


# noinspection PyProtectedMember - internal helper for EventBus operation
class _Subscriber:
    """Internal representation of a subscriber with its own delivery queue."""

    __slots__ = (
        "id",
        "handler",
        "pattern",
        "queue",
        "task",
        "queue_depth",
        "bus",
        "name",
    )

    def __init__(
        self,
        *,
        subscriber_id: int,
        handler: EventHandler,
        pattern: str,
        queue_depth: int,
        bus: "EventBus",
    ) -> None:
        self.id = subscriber_id
        self.handler = handler
        self.pattern = pattern
        self.queue_depth = queue_depth
        self.queue: asyncio.Queue[EventBase] = asyncio.Queue(maxsize=queue_depth)
        self.task: Optional[asyncio.Task[None]] = None
        self.bus = bus
        self.name = _derive_handler_name(handler)

    def start(self) -> None:
        loop = asyncio.get_running_loop()
        self.task = loop.create_task(
            self._run(), name=f"event-bus-subscriber-{self.id}"
        )

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:  # pragma: no cover - expected path
                pass

    def matches(self, topic: str) -> bool:
        return fnmatch(topic, self.pattern)

    async def enqueue(self, topic: str, event: EventBase) -> None:
        """Enqueue event for delivery to subscriber.

        If queue is full, applies DROP_OLDEST policy: removes the oldest event
        from the queue (FIFO head) to make room for the new event. This ensures
        subscribers always process the most recent events under backpressure.

        Args:
            topic: Normalized topic name for metrics
            event: Event to deliver
        """
        queue = self.queue
        if queue.full():
            try:
                queue.get_nowait()
                _event_overflow_total.labels(topic=topic, subscriber=self.name).inc()
            except asyncio.QueueEmpty:  # pragma: no cover - defensive guard
                pass
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:  # pragma: no cover - double guard
            _event_overflow_total.labels(topic=topic, subscriber=self.name).inc()
            return
        _event_queue_depth.labels(topic=topic, subscriber=self.name).set(queue.qsize())

    async def _run(self) -> None:
        while True:
            event = await self.queue.get()
            topic_value = event.topic.value
            _event_queue_depth.labels(topic=topic_value, subscriber=self.name).set(
                self.queue.qsize()
            )

            trace_id = getattr(event, "cognitive_trace_id", None)
            start = time.perf_counter()

            # Start delivery tracing span if trace_id present
            with (
                _TRACER.span(
                    "event_bus.deliver",
                    attributes={
                        "topic": topic_value,
                        "subscriber": self.name,
                        "cognitive_trace_id": trace_id,
                    },
                )
                if trace_id
                else _TRACER.noop_span()
            ):
                try:
                    result = self.handler(event)
                    if inspect.isawaitable(result):
                        await result
                except Exception:  # pragma: no cover - handler failure path
                    logger.exception(
                        "event_bus_handler_error",
                        topic=topic_value,
                        handler=self.name,
                        trace_id=trace_id,
                    )
                finally:
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    _event_delivery_latency_ms.labels(
                        topic=topic_value,
                        subscriber=self.name,
                    ).observe(elapsed_ms)

                    if elapsed_ms > _SLOW_SUBSCRIBER_THRESHOLD_MS:
                        _event_slow_subscriber_total.labels(
                            topic=topic_value,
                            subscriber=self.name,
                            reason="handler_latency",
                        ).inc()
                        logger.warning(
                            "event_bus_slow_handler",
                            topic=topic_value,
                            handler=self.name,
                            latency_ms=elapsed_ms,
                            threshold_ms=_SLOW_SUBSCRIBER_THRESHOLD_MS,
                        )

                    queue_pressure = (
                        self.queue.qsize() / self.queue_depth
                        if self.queue_depth
                        else 0.0
                    )
                    if queue_pressure >= _QUEUE_PRESSURE_RATIO:
                        _event_slow_subscriber_total.labels(
                            topic=topic_value,
                            subscriber=self.name,
                            reason="queue_pressure",
                        ).inc()
                        logger.warning(
                            "event_bus_queue_pressure",
                            topic=topic_value,
                            handler=self.name,
                            queue_depth=self.queue.qsize(),
                            capacity=self.queue_depth,
                        )

                    self.queue.task_done()


def _derive_handler_name(handler: EventHandler) -> str:
    if hasattr(handler, "__qualname__"):
        return handler.__qualname__  # pragma: no cover - attribute presence check
    if hasattr(handler, "__name__"):
        return handler.__name__
    return repr(handler)


def _normalise_topic_identifier(identifier: EventTopic | str) -> str:
    if isinstance(identifier, EventTopic):
        return identifier.value

    topic = identifier
    if topic.startswith("k1."):
        topic = topic[3:]
    return topic.replace(".", "_")


_METRICS = get_metrics()
_TRACER = get_tracer()

_event_publish_total = _METRICS.counter(
    "event_bus_publish_total",
    "Total events published to the K1 event bus",
    labelnames=["topic", "status"],
)
_event_publish_latency_ms = _METRICS.histogram(
    "event_bus_publish_latency_ms",
    "Event publish overhead (Layer 1 → Event Bus) in milliseconds",
    labelnames=["topic"],
    buckets=[0.05, 0.1, 0.2, 0.5, 1, 2, 5],
)
_event_delivery_latency_ms = _METRICS.histogram(
    "event_bus_delivery_latency_ms",
    "Event delivery latency (Event Bus → subscriber handler) in milliseconds",
    labelnames=["topic", "subscriber"],
    buckets=[0.1, 0.25, 0.5, 1, 2, 5, 10, 25],
)
_event_overflow_total = _METRICS.counter(
    "event_bus_overflow_total",
    "Events dropped because a subscriber queue exceeded its capacity",
    labelnames=["topic", "subscriber"],
)
_event_queue_depth = _METRICS.gauge(
    "event_bus_queue_depth",
    "Current queue depth per subscriber",
    labelnames=["topic", "subscriber"],
)
_event_slow_subscriber_total = _METRICS.counter(
    "event_bus_slow_subscriber_total",
    "Occurrences of slow subscriber processing or sustained high queue depth",
    labelnames=["topic", "subscriber", "reason"],
)

_DEFAULT_QUEUE_DEPTH = 50
_SLOW_SUBSCRIBER_THRESHOLD_MS = 100.0
_QUEUE_PRESSURE_RATIO = 0.9


class EventBus:
    """Async pub/sub event bus supporting wildcard subscriptions and backpressure."""

    def __init__(self, *, default_queue_depth: int = _DEFAULT_QUEUE_DEPTH) -> None:
        self._default_queue_depth = default_queue_depth
        self._subscribers: Dict[int, _Subscriber] = {}
        self._topic_index: Dict[str, List[int]] = {}
        self._wildcard_subscribers: List[int] = []
        self._next_subscriber_id = 1
        self._shutdown = False
        self._lock = asyncio.Lock()

    async def publish(self, event: EventBase) -> None:
        if self._shutdown:
            raise RuntimeError("EventBus.publish() called after shutdown")

        topic_value = _normalise_topic_identifier(event.topic)
        start = time.perf_counter()

        async with self._lock:
            subscriber_ids = list(self._topic_index.get(topic_value, ()))
            if self._wildcard_subscribers:
                for sub_id in self._wildcard_subscribers:
                    subscriber = self._subscribers.get(sub_id)
                    if subscriber and subscriber.matches(topic_value):
                        subscriber_ids.append(sub_id)

        if not subscriber_ids:
            _event_publish_total.labels(
                topic=topic_value, status="no_subscribers"
            ).inc()
            logger.debug(
                "event_bus_no_subscribers",
                topic=topic_value,
                trace_id=getattr(event, "cognitive_trace_id", None),
            )
            return

        for sub_id in subscriber_ids:
            subscriber = self._subscribers.get(sub_id)
            if subscriber is None:  # pragma: no cover - defensive guard
                continue
            await subscriber.enqueue(topic_value, event)

        _event_publish_total.labels(topic=topic_value, status="accepted").inc()
        _event_publish_latency_ms.labels(topic=topic_value).observe(
            (time.perf_counter() - start) * 1000
        )

        trace_id = getattr(event, "cognitive_trace_id", None)
        if trace_id:
            with _TRACER.span(
                "event_bus.publish",
                attributes={
                    "topic": topic_value,
                    "subscriber_count": len(subscriber_ids),
                    "cognitive_trace_id": trace_id,
                },
            ):
                pass

    def subscribe(
        self,
        topic: EventTopic | str,
        handler: EventHandler,
        *,
        queue_depth: Optional[int] = None,
    ) -> SubscriptionHandle:
        if self._shutdown:
            raise RuntimeError("EventBus.subscribe() called after shutdown")

        pattern = _normalise_topic_identifier(topic)
        subscriber_id = self._next_subscriber_id
        self._next_subscriber_id += 1

        subscriber = _Subscriber(
            subscriber_id=subscriber_id,
            handler=handler,
            pattern=pattern,
            queue_depth=queue_depth or self._default_queue_depth,
            bus=self,
        )

        try:
            subscriber.start()
        except RuntimeError as exc:  # pragma: no cover - missing running loop
            raise RuntimeError(
                "EventBus.subscribe() must be called within a running event loop"
            ) from exc

        self._subscribers[subscriber_id] = subscriber
        if "*" in pattern:
            self._wildcard_subscribers.append(subscriber_id)
        else:
            self._topic_index.setdefault(pattern, []).append(subscriber_id)

        logger.debug(
            "event_bus_subscribed",
            pattern=pattern,
            handler=subscriber.name,
            queue_depth=subscriber.queue_depth,
        )

        return SubscriptionHandle(
            topic_pattern=pattern,
            handler_repr=subscriber.name,
            _bus=self,
            _subscriber_id=subscriber_id,
        )

    async def remove_subscription(self, subscriber_id: int) -> None:
        async with self._lock:
            subscriber = self._subscribers.pop(subscriber_id, None)
            if subscriber is None:
                return

            if "*" in subscriber.pattern:
                if subscriber_id in self._wildcard_subscribers:
                    self._wildcard_subscribers.remove(subscriber_id)
            else:
                subscriber_list = self._topic_index.get(subscriber.pattern)
                if subscriber_list and subscriber_id in subscriber_list:
                    subscriber_list.remove(subscriber_id)
                    if not subscriber_list:
                        self._topic_index.pop(subscriber.pattern, None)

        await subscriber.stop()
        _event_queue_depth.labels(
            topic=subscriber.pattern, subscriber=subscriber.name
        ).set(0)
        logger.debug(
            "event_bus_unsubscribed",
            pattern=subscriber.pattern,
            handler=subscriber.name,
        )

    async def shutdown(self) -> None:
        if self._shutdown:
            return
        self._shutdown = True

        async with self._lock:
            subscribers = list(self._subscribers.values())
            self._subscribers.clear()
            self._topic_index.clear()
            self._wildcard_subscribers.clear()

        await asyncio.gather(
            *(subscriber.stop() for subscriber in subscribers), return_exceptions=True
        )
        logger.info("event_bus_shutdown", subscriber_count=len(subscribers))


__all__ = ["EventBus", "EventHandler", "SubscriptionHandle"]
