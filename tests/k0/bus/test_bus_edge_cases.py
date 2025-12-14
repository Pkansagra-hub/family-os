"""Phase 4: Bus Edge Cases Tests."""

import warnings
from unittest.mock import AsyncMock, MagicMock

import pytest

from k0.bus.core import BusDispatchContext, BusDispatcher, BusMessage, current_dispatch_context
from k0.bus.middleware import latency_metrics_middleware, timestamp_middleware, tracing_middleware
from k0.obs import MetricsExporter, TracerFactory
from k0.qos import Scheduler, SchedulerProfile


@pytest.fixture
def scheduler():
    """Create a test scheduler."""
    return Scheduler(
        SchedulerProfile(
            name="test",
            description="test profile",
            port_limits={"bus": 10},
            default_port_limit=10,
        )
    )


class TestBusDispatcherConstructorEdgeCases:
    """Test BusDispatcher constructor edge cases."""

    def test_constructor_with_invalid_token_cost(self, scheduler):
        """Test constructor raises ValueError for invalid token_cost."""
        with pytest.raises(ValueError, match="token_cost must be positive"):
            BusDispatcher(scheduler=scheduler, token_cost=0)

        with pytest.raises(ValueError, match="token_cost must be positive"):
            BusDispatcher(scheduler=scheduler, token_cost=-1)

    def test_constructor_with_empty_port(self, scheduler):
        """Test constructor raises ValueError for empty port."""
        with pytest.raises(ValueError, match="port must be a non-empty string"):
            BusDispatcher(scheduler=scheduler, port="")

        with pytest.raises(ValueError, match="port must be a non-empty string"):
            BusDispatcher(scheduler=scheduler, port="   ")

    def test_constructor_with_empty_default_band(self, scheduler):
        """Test constructor raises ValueError for empty default_band."""
        with pytest.raises(ValueError, match="default_band must be a non-empty string"):
            BusDispatcher(scheduler=scheduler, default_band="")

        with pytest.raises(ValueError, match="default_band must be a non-empty string"):
            BusDispatcher(scheduler=scheduler, default_band="   ")


class TestBusDispatcherSubscribeEdgeCases:
    """Test BusDispatcher.subscribe edge cases and error conditions."""

    def test_subscribe_with_non_callable_handler(self, scheduler):
        """Test subscribe raises TypeError for non-callable handler."""
        dispatcher = BusDispatcher(scheduler=scheduler)
        with pytest.raises(TypeError, match="handler must be callable"):
            dispatcher.subscribe("test.topic", "not_callable")  # type: ignore

    def test_subscribe_with_empty_topic(self, scheduler):
        """Test subscribe raises ValueError for empty topic."""
        dispatcher = BusDispatcher(scheduler=scheduler)

        async def handler(msg):
            pass

        with pytest.raises(ValueError, match="topic must be a non-empty string"):
            dispatcher.subscribe("", handler)

    def test_subscribe_with_whitespace_only_topic(self, scheduler):
        """Test subscribe raises ValueError for whitespace-only topic."""
        dispatcher = BusDispatcher(scheduler=scheduler)

        async def handler(msg):
            pass

        with pytest.raises(ValueError, match="topic must be a non-empty string"):
            dispatcher.subscribe("   ", handler)

    def test_subscribe_strips_topic_whitespace(self, scheduler):
        """Test subscribe strips whitespace from topic."""
        dispatcher = BusDispatcher(scheduler=scheduler)
        handler = AsyncMock()
        dispatcher.subscribe("  test.topic  ", handler)

        # Check that topic was stripped
        assert "test.topic" in dispatcher._topic_subscriptions
        assert "  test.topic  " not in dispatcher._topic_subscriptions


class TestBusDispatcherTapEdgeCases:
    """Test BusDispatcher.tap edge cases and error conditions."""

    def test_tap_with_non_callable_handler(self, scheduler):
        """Test tap raises TypeError for non-callable handler."""
        dispatcher = BusDispatcher(scheduler=scheduler)
        with pytest.raises(TypeError, match="handler must be callable"):
            dispatcher.tap("not_callable")  # type: ignore

    def test_tap_adds_to_taps_list(self, scheduler):
        """Test tap adds handler to taps list."""
        dispatcher = BusDispatcher(scheduler=scheduler)
        handler = AsyncMock()
        dispatcher.tap(handler)
        assert handler in dispatcher._taps


class TestBusDispatcherRegisterSinkEdgeCases:
    """Test BusDispatcher.register_sink edge cases and error conditions."""

    def test_register_sink_with_non_callable_sink(self, scheduler):
        """Test register_sink raises TypeError for non-callable sink."""
        dispatcher = BusDispatcher(scheduler=scheduler)
        with pytest.raises(TypeError, match="bus sink must be callable"):
            dispatcher.register_sink("not_callable")  # type: ignore

    def test_register_sink_emits_deprecation_warning(self, scheduler):
        """Test register_sink emits deprecation warning."""
        dispatcher = BusDispatcher(scheduler=scheduler)
        sink = AsyncMock()

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            dispatcher.register_sink(sink)
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "register_sink() is deprecated" in str(w[0].message)

    def test_register_sink_converts_to_wildcard_subscription(self, scheduler):
        """Test register_sink converts to wildcard subscription."""
        dispatcher = BusDispatcher(scheduler=scheduler)
        sink = AsyncMock()
        dispatcher.register_sink(sink)

        # Should be added as wildcard subscription
        assert "*" in dispatcher._topic_subscriptions
        assert sink in dispatcher._topic_subscriptions["*"]


class TestBusDispatcherRegisterMiddlewareEdgeCases:
    """Test BusDispatcher.register_middleware edge cases and error conditions."""

    def test_register_middleware_with_non_callable_middleware(self, scheduler):
        """Test register_middleware raises TypeError for non-callable middleware."""
        dispatcher = BusDispatcher(scheduler=scheduler)
        with pytest.raises(TypeError, match="bus middleware must be callable"):
            dispatcher.register_middleware("not_callable")  # type: ignore

    def test_register_middleware_adds_to_middlewares_list(self, scheduler):
        """Test register_middleware adds middleware to middlewares list."""
        dispatcher = BusDispatcher(scheduler=scheduler)
        middleware = MagicMock()
        dispatcher.register_middleware(middleware)
        assert middleware in dispatcher._middlewares


class TestBusDispatcherResolveBandEdgeCases:
    """Test BusDispatcher._resolve_band edge cases and error conditions."""

    def test_resolve_band_with_none_resolver_uses_default(self, scheduler):
        """Test _resolve_band uses default band when no resolver."""
        dispatcher = BusDispatcher(scheduler=scheduler)
        message = BusMessage(topic="test", payload=b"test", offset=1)
        band = dispatcher._resolve_band(message)
        assert band == dispatcher._default_band

    def test_resolve_band_with_resolver_returning_non_string(self, scheduler):
        """Test _resolve_band raises TypeError when resolver returns non-string."""
        dispatcher = BusDispatcher(scheduler=scheduler, band_resolver=lambda msg: 123)  # type: ignore
        message = BusMessage(topic="test", payload=b"test", offset=1)
        with pytest.raises(TypeError, match="band_resolver must return a string"):
            dispatcher._resolve_band(message)

    def test_resolve_band_with_resolver_returning_empty_string(self, scheduler):
        """Test _resolve_band raises ValueError when resolver returns empty string."""
        dispatcher = BusDispatcher(scheduler=scheduler, band_resolver=lambda msg: "")
        message = BusMessage(topic="test", payload=b"test", offset=1)
        with pytest.raises(ValueError, match="band_resolver must return a non-empty string"):
            dispatcher._resolve_band(message)

    def test_resolve_band_with_resolver_returning_whitespace_only(self, scheduler):
        """Test _resolve_band raises ValueError when resolver returns whitespace-only."""
        dispatcher = BusDispatcher(scheduler=scheduler, band_resolver=lambda msg: "   ")
        message = BusMessage(topic="test", payload=b"test", offset=1)
        with pytest.raises(ValueError, match="band_resolver must return a non-empty string"):
            dispatcher._resolve_band(message)

    def test_resolve_band_converts_to_uppercase(self, scheduler):
        """Test _resolve_band converts band to uppercase."""
        dispatcher = BusDispatcher(scheduler=scheduler, band_resolver=lambda msg: "test_band")
        message = BusMessage(topic="test", payload=b"test", offset=1)
        band = dispatcher._resolve_band(message)
        assert band == "TEST_BAND"


class TestBusDispatcherEnsureMonotonicEdgeCases:
    """Test BusDispatcher._ensure_monotonic edge cases."""

    def test_ensure_monotonic_with_decreasing_offset(self, scheduler):
        """Test _ensure_monotonic raises ValueError for decreasing offset."""
        dispatcher = BusDispatcher(scheduler=scheduler)
        dispatcher._last_offset = 10
        with pytest.raises(
            ValueError, match="WAL offsets must be provided in non-decreasing order"
        ):
            dispatcher._ensure_monotonic(5)

    def test_ensure_monotonic_allows_equal_offset(self, scheduler):
        """Test _ensure_monotonic allows equal offset."""
        dispatcher = BusDispatcher(scheduler=scheduler)
        dispatcher._last_offset = 10
        # Should not raise
        dispatcher._ensure_monotonic(10)

    def test_ensure_monotonic_allows_increasing_offset(self, scheduler):
        """Test _ensure_monotonic allows increasing offset."""
        dispatcher = BusDispatcher(scheduler=scheduler)
        dispatcher._last_offset = 10
        # Should not raise
        dispatcher._ensure_monotonic(15)


class TestBusDispatcherResolveHandlersEdgeCases:
    """Test BusDispatcher._resolve_handlers edge cases."""

    def test_resolve_handlers_with_exact_topic_match(self, scheduler):
        """Test _resolve_handlers returns exact topic matches."""
        dispatcher = BusDispatcher(scheduler=scheduler)
        handler1 = AsyncMock()
        handler2 = AsyncMock()
        dispatcher.subscribe("test.topic", handler1)
        dispatcher.subscribe("test.topic", handler2)

        handlers = dispatcher._resolve_handlers("test.topic")
        assert handler1 in handlers
        assert handler2 in handlers

    def test_resolve_handlers_with_wildcard_subscription(self, scheduler):
        """Test _resolve_handlers includes wildcard subscriptions."""
        dispatcher = BusDispatcher(scheduler=scheduler)
        wildcard_handler = AsyncMock()
        dispatcher.subscribe("*", wildcard_handler)

        handlers = dispatcher._resolve_handlers("any.topic")
        assert wildcard_handler in handlers

    def test_resolve_handlers_with_legacy_sinks(self, scheduler):
        """Test _resolve_handlers includes legacy sinks."""
        dispatcher = BusDispatcher(scheduler=scheduler)
        legacy_sink = AsyncMock()
        dispatcher._sinks.append(legacy_sink)

        handlers = dispatcher._resolve_handlers("any.topic")
        assert legacy_sink in handlers

    def test_resolve_handlers_combines_all_types(self, scheduler):
        """Test _resolve_handlers combines exact, wildcard, and legacy handlers."""
        dispatcher = BusDispatcher(scheduler=scheduler)
        exact_handler = AsyncMock()
        wildcard_handler = AsyncMock()
        legacy_sink = AsyncMock()

        dispatcher.subscribe("test.topic", exact_handler)
        dispatcher.subscribe("*", wildcard_handler)
        dispatcher._sinks.append(legacy_sink)

        handlers = dispatcher._resolve_handlers("test.topic")
        assert exact_handler in handlers
        assert wildcard_handler in handlers
        assert legacy_sink in handlers


class TestBusDispatcherFanOutEdgeCases:
    """Test BusDispatcher._fan_out edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_fan_out_with_non_coroutine_handler(self, scheduler):
        """Test _fan_out raises TypeError for non-coroutine handler."""
        dispatcher = BusDispatcher(scheduler=scheduler)
        handler = MagicMock(return_value="not_a_coroutine")
        dispatcher.subscribe("test.topic", handler)

        message = BusMessage(topic="test.topic", payload=b"test", offset=1)
        context = BusDispatchContext(message=message, band="TEST", port="bus", token_cost=1)

        with pytest.raises(TypeError, match="bus sink must return a coroutine"):
            await dispatcher._fan_out(context)

    @pytest.mark.asyncio
    async def test_fan_out_with_non_coroutine_tap(self, scheduler):
        """Test _fan_out raises TypeError for non-coroutine tap."""
        dispatcher = BusDispatcher(scheduler=scheduler)
        tap = MagicMock(return_value="not_a_coroutine")
        dispatcher.tap(tap)

        message = BusMessage(topic="test.topic", payload=b"test", offset=1)
        context = BusDispatchContext(message=message, band="TEST", port="bus", token_cost=1)

        with pytest.raises(TypeError, match="tap handler must return a coroutine"):
            await dispatcher._fan_out(context)

    @pytest.mark.asyncio
    async def test_fan_out_with_mixed_handler_types(self, scheduler):
        """Test _fan_out handles mix of sync and async handlers."""
        dispatcher = BusDispatcher(scheduler=scheduler)

        # Add a proper async handler
        async_handler = AsyncMock()
        dispatcher.subscribe("test.topic", async_handler)

        # Add a tap
        tap_handler = AsyncMock()
        dispatcher.tap(tap_handler)

        message = BusMessage(topic="test.topic", payload=b"test", offset=1)
        context = BusDispatchContext(message=message, band="TEST", port="bus", token_cost=1)

        await dispatcher._fan_out(context)

        # Both should have been called
        async_handler.assert_called_once_with(message)
        tap_handler.assert_called_once_with(message)


class TestBusDispatcherDispatchEdgeCases:
    """Test BusDispatcher.dispatch edge cases."""

    @pytest.mark.asyncio
    async def test_dispatch_with_empty_message_batch(self, scheduler):
        """Test dispatch handles empty message batch."""
        dispatcher = BusDispatcher(scheduler=scheduler)
        # Should not raise or do anything
        await dispatcher.dispatch([])

    @pytest.mark.asyncio
    async def test_middlewares_property(self, scheduler):
        """Test middlewares property returns configured middleware chain."""
        middleware1 = MagicMock()
        middleware2 = MagicMock()

        dispatcher = BusDispatcher(scheduler=scheduler, middlewares=[middleware1, middleware2])

        assert dispatcher.middlewares == (middleware1, middleware2)

    @pytest.mark.asyncio
    async def test_fan_out_with_multiple_tasks(self, scheduler):
        """Test _fan_out executes multiple tasks concurrently."""
        dispatcher = BusDispatcher(scheduler=scheduler)

        call_order = []

        async def handler1(msg):
            call_order.append(1)

        async def handler2(msg):
            call_order.append(2)

        dispatcher.subscribe("test", handler1)
        dispatcher.subscribe("test", handler2)

        message = BusMessage(topic="test", payload=b"test", offset=1)
        context = BusDispatchContext(message=message, band="GREEN", port="bus", token_cost=1)

        await dispatcher._fan_out(context)

        # Both handlers should have been called
        assert 1 in call_order
        assert 2 in call_order


class TestTimestampMiddlewareEdgeCases:
    """Test timestamp_middleware edge cases."""

    @pytest.mark.asyncio
    async def test_timestamp_middleware_with_custom_clock(self, scheduler):
        """Test timestamp_middleware uses custom clock function."""
        from datetime import datetime, timezone

        custom_times = [
            datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            datetime(2023, 1, 1, 12, 0, 1, tzinfo=timezone.utc),
        ]
        time_iter = iter(custom_times)

        middleware = timestamp_middleware(clock=lambda: next(time_iter))
        context = BusDispatchContext(
            message=BusMessage(topic="test", payload=b"test", offset=1),
            band="TEST",
            port="bus",
            token_cost=1,
        )

        call_count = 0

        async def handler(ctx):
            nonlocal call_count
            call_count += 1
            assert ctx.started_at == custom_times[0]

        await middleware(context, handler)
        assert call_count == 1  # Handler called once by timestamp middleware


class TestLatencyMetricsMiddlewareEdgeCases:
    """Test latency_metrics_middleware edge cases."""

    @pytest.mark.asyncio
    async def test_latency_metrics_middleware_success_path(self):
        """Test latency_metrics_middleware records success metrics."""
        metrics = MagicMock(spec=MetricsExporter)
        middleware = latency_metrics_middleware(metrics)

        context = BusDispatchContext(
            message=BusMessage(topic="test.topic", payload=b"test", offset=1),
            band="TEST",
            port="bus",
            token_cost=1,
        )

        async def handler(ctx):
            pass  # Success

        await middleware(context, handler)

        # Should emit success metrics
        metrics.observe.assert_called()
        metrics.emit.assert_called()

    @pytest.mark.asyncio
    async def test_latency_metrics_middleware_failure_path(self):
        """Test latency_metrics_middleware records failure metrics."""
        metrics = MagicMock(spec=MetricsExporter)
        middleware = latency_metrics_middleware(metrics)

        context = BusDispatchContext(
            message=BusMessage(topic="test.topic", payload=b"test", offset=1),
            band="TEST",
            port="bus",
            token_cost=1,
        )

        async def handler(ctx):
            raise ValueError("Test failure")

        with pytest.raises(ValueError, match="Test failure"):
            await middleware(context, handler)

        # Should emit failure metrics
        metrics.observe.assert_called()
        metrics.emit.assert_called()


class TestTracingMiddlewareEdgeCases:
    """Test tracing_middleware edge cases."""

    @pytest.mark.asyncio
    async def test_tracing_middleware_with_existing_trace_id(self):
        """Test tracing_middleware uses existing trace_id."""
        tracer_factory = MagicMock(spec=TracerFactory)
        tracer_factory.new_trace_id.return_value = "generated_id"
        tracer_factory.attach_cognitive_trace.return_value = MagicMock()
        tracer_factory.span.return_value.__enter__ = MagicMock()
        tracer_factory.span.return_value.__exit__ = MagicMock()

        middleware = tracing_middleware(tracer_factory=tracer_factory)

        message = BusMessage(topic="test.topic", payload=b"test", offset=1, trace_id="existing_id")
        context = BusDispatchContext(message=message, band="TEST", port="bus", token_cost=1)

        async def handler(ctx):
            assert ctx.trace_id == "existing_id"

        await middleware(context, handler)

        # Should not generate new trace ID
        tracer_factory.new_trace_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_tracing_middleware_generates_trace_id_when_missing(self):
        """Test tracing_middleware generates trace_id when missing."""
        tracer_factory = MagicMock(spec=TracerFactory)
        tracer_factory.new_trace_id.return_value = "generated_id"
        tracer_factory.attach_cognitive_trace.return_value = MagicMock()
        span_mock = MagicMock()
        span_mock.__enter__ = MagicMock()
        span_mock.__exit__ = MagicMock()
        tracer_factory.span.return_value = span_mock
        tracer_factory.attach_cognitive_trace.return_value = MagicMock()
        tracer_factory.detach = MagicMock()

        middleware = tracing_middleware(tracer_factory=tracer_factory)

        message = BusMessage(topic="test.topic", payload=b"test", offset=1, trace_id=None)
        context = BusDispatchContext(
            message=message, band="TEST", port="bus", token_cost=1, trace_id=None
        )

        async def handler(ctx):
            assert ctx.trace_id == "generated_id"

        await middleware(context, handler)

        # Should generate new trace ID
        tracer_factory.new_trace_id.assert_called_once()

        # Should create span with generated_trace attribute
        tracer_factory.span.assert_called_once()
        call_args = tracer_factory.span.call_args
        attributes = call_args[1]["attributes"]
        assert attributes["k0.bus.generated_trace"] is True


class TestCurrentDispatchContextEdgeCases:
    """Test current_dispatch_context edge cases."""

    @pytest.mark.asyncio
    async def test_current_dispatch_context_outside_dispatch(self):
        """Test current_dispatch_context returns None outside dispatch."""
        assert current_dispatch_context() is None

    @pytest.mark.asyncio
    async def test_current_dispatch_context_within_dispatch(self, scheduler):
        """Test current_dispatch_context returns context within dispatch."""
        dispatcher = BusDispatcher(scheduler=scheduler)

        captured_context = None

        async def sink(msg):
            nonlocal captured_context
            captured_context = current_dispatch_context()

        dispatcher.subscribe("*", sink)

        message = BusMessage(topic="test", payload=b"test", offset=1)
        await dispatcher.dispatch([message])

        assert captured_context is not None
        assert captured_context.message == message
