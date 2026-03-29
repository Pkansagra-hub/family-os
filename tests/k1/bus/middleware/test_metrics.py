"""
Tests for k1.bus.middleware.metrics -- MetricsMiddleware.

Covers:
    - No-op when prometheus_client is not installed
    - Explicit enabled=False disables metrics
    - Counter increments with correct labels (topic_prefix, priority)
    - Latency histogram recording
    - Topic prefix extraction (_topic_prefix helper)
    - Middleware Protocol conformance
    - Never drops envelopes
    - Priority label mapping for all 4 levels
    - Edge cases: empty topic, single-segment topic
"""

from __future__ import annotations

from unittest.mock import MagicMock

from k1.bus.envelope import Envelope, Priority
from k1.bus.middleware import Middleware
from k1.bus.middleware.metrics import MetricsMiddleware, _topic_prefix

# ---------------------------------------------------------------------------
# _topic_prefix helper
# ---------------------------------------------------------------------------


class TestTopicPrefix:
    """Test the topic prefix extraction used for metric labels."""

    def test_two_segments(self) -> None:
        assert _topic_prefix("k1.capability.completed.v1") == "k1.capability"

    def test_three_segments(self) -> None:
        assert _topic_prefix("k1.agent.abc.delta.v1") == "k1.agent"

    def test_exact_two(self) -> None:
        assert _topic_prefix("k1.test") == "k1.test"

    def test_single_segment(self) -> None:
        assert _topic_prefix("k1") == "k1"

    def test_empty_string(self) -> None:
        assert _topic_prefix("") == "unknown"


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestMetricsProtocol:
    """MetricsMiddleware satisfies the Middleware Protocol."""

    def test_isinstance_middleware(self) -> None:
        mw = MetricsMiddleware(enabled=False)
        assert isinstance(mw, Middleware)

    def test_has_process_method(self) -> None:
        mw = MetricsMiddleware(enabled=False)
        assert callable(getattr(mw, "process", None))


# ---------------------------------------------------------------------------
# No-op behavior
# ---------------------------------------------------------------------------


class TestMetricsNoOp:
    """When disabled, process() is a pass-through."""

    def test_disabled_returns_envelope(self) -> None:
        mw = MetricsMiddleware(enabled=False)
        env = Envelope(topic="k1.test", payload=b"x")
        result = mw.process(env)
        assert result is env

    def test_disabled_enabled_property(self) -> None:
        mw = MetricsMiddleware(enabled=False)
        assert mw.enabled is False

    def test_disabled_repr(self) -> None:
        mw = MetricsMiddleware(enabled=False)
        assert "disabled" in repr(mw)

    def test_never_drops_envelope(self) -> None:
        mw = MetricsMiddleware(enabled=False)
        env = Envelope(topic="k1.test", payload=b"x")
        result = mw.process(env)
        assert result is not None


# ---------------------------------------------------------------------------
# Counter + histogram with mock Prometheus
# ---------------------------------------------------------------------------


class TestMetricsCollection:
    """When Prometheus is available, metrics are recorded correctly."""

    def _make_middleware_with_mocks(
        self,
    ) -> tuple[MetricsMiddleware, MagicMock, MagicMock]:
        """Create MetricsMiddleware with mock counter and histogram."""
        mock_counter = MagicMock()
        mock_histogram = MagicMock()
        mw = MetricsMiddleware(enabled=False)
        # Force enable and inject mocks
        mw._enabled = True  # type: ignore[misc]
        mw._counter = mock_counter  # type: ignore[misc]
        mw._histogram = mock_histogram  # type: ignore[misc]
        return mw, mock_counter, mock_histogram

    def test_counter_incremented(self) -> None:
        mw, mock_counter, _ = self._make_middleware_with_mocks()
        env = Envelope(
            topic="k1.capability.completed.v1",
            priority=Priority.URGENT,
            envelope_id=1,
            sequence=1,
            created_ns=0,
            payload=b"x",
        )
        mw.process(env)
        mock_counter.labels.assert_called_once_with(
            topic_prefix="k1.capability",
            priority="urgent",
        )
        mock_counter.labels.return_value.inc.assert_called_once()

    def test_counter_realtime_label(self) -> None:
        mw, mock_counter, _ = self._make_middleware_with_mocks()
        env = Envelope(
            topic="k1.agent.delta",
            priority=Priority.REALTIME,
            envelope_id=2,
            created_ns=0,
            payload=b"x",
        )
        mw.process(env)
        mock_counter.labels.assert_called_with(
            topic_prefix="k1.agent",
            priority="realtime",
        )

    def test_counter_interactive_label(self) -> None:
        mw, mock_counter, _ = self._make_middleware_with_mocks()
        env = Envelope(
            topic="k1.session.start",
            priority=Priority.INTERACTIVE,
            envelope_id=3,
            created_ns=0,
            payload=b"x",
        )
        mw.process(env)
        mock_counter.labels.assert_called_with(
            topic_prefix="k1.session",
            priority="interactive",
        )

    def test_counter_background_label(self) -> None:
        mw, mock_counter, _ = self._make_middleware_with_mocks()
        env = Envelope(
            topic="k1.fabric.learning",
            priority=Priority.BACKGROUND,
            envelope_id=4,
            created_ns=0,
            payload=b"x",
        )
        mw.process(env)
        mock_counter.labels.assert_called_with(
            topic_prefix="k1.fabric",
            priority="background",
        )

    def test_histogram_records_latency(self) -> None:
        import time

        mw, _, mock_histogram = self._make_middleware_with_mocks()
        env = Envelope(
            topic="k1.test.latency",
            priority=Priority.INTERACTIVE,
            envelope_id=5,
            sequence=1,
            created_ns=time.monotonic_ns() - 1_000_000,  # 1ms ago
            payload=b"x",
        )
        mw.process(env)
        mock_histogram.labels.assert_called_with(topic_prefix="k1.test")
        mock_histogram.labels.return_value.observe.assert_called_once()
        latency = mock_histogram.labels.return_value.observe.call_args[0][0]
        assert 0 < latency < 1  # Should be ~1ms in seconds

    def test_histogram_skipped_when_created_ns_zero(self) -> None:
        mw, _, mock_histogram = self._make_middleware_with_mocks()
        env = Envelope(
            topic="k1.test.no_ts",
            priority=Priority.INTERACTIVE,
            envelope_id=6,
            created_ns=0,
            payload=b"x",
        )
        mw.process(env)
        mock_histogram.labels.return_value.observe.assert_not_called()

    def test_returns_same_envelope(self) -> None:
        mw, _, _ = self._make_middleware_with_mocks()
        env = Envelope(
            topic="k1.test",
            priority=Priority.INTERACTIVE,
            envelope_id=7,
            created_ns=0,
            payload=b"x",
        )
        result = mw.process(env)
        assert result is env

    def test_multiple_publishes_increment_counter(self) -> None:
        mw, mock_counter, _ = self._make_middleware_with_mocks()
        env = Envelope(
            topic="k1.test",
            priority=Priority.INTERACTIVE,
            envelope_id=8,
            created_ns=0,
            payload=b"x",
        )
        mw.process(env)
        mw.process(env)
        mw.process(env)
        assert mock_counter.labels.return_value.inc.call_count == 3
