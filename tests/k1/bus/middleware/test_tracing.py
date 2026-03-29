"""
Tests for k1.bus.middleware.tracing -- TracingMiddleware.

Covers:
    - No-op when OpenTelemetry is not installed/configured
    - Span creation when a mock tracer is injected
    - Trace attributes: topic, envelope_id, sequence, priority, parent_id
    - cognitive_trace_id and session_id added when present
    - Missing cognitive_trace_id does not add trace attribute
    - Explicit enabled=False disables tracing
    - Middleware Protocol conformance
    - Never drops envelopes (always returns envelope)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from k1.bus.envelope import Envelope, Priority
from k1.bus.middleware import Middleware
from k1.bus.middleware.tracing import TracingMiddleware

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def envelope() -> Envelope:
    """Stamped envelope with all header fields populated."""
    return Envelope(
        topic="k1.capability.completed.v1",
        priority=Priority.URGENT,
        envelope_id=42,
        sequence=7,
        cognitive_trace_id="trace-abc-123",
        session_id="sess-001",
        request_id="req-001",
        parent_id=10,
        created_ns=1_000_000_000,
        payload=b"opaque-data",
    )


@pytest.fixture
def envelope_no_trace() -> Envelope:
    """Envelope with no cognitive_trace_id or session_id."""
    return Envelope(
        topic="k1.agent.test.delta.v1",
        priority=Priority.INTERACTIVE,
        envelope_id=99,
        sequence=1,
        created_ns=2_000_000_000,
        payload=b"data",
    )


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestTracingMiddlewareProtocol:
    """TracingMiddleware satisfies the Middleware Protocol."""

    def test_isinstance_middleware(self) -> None:
        mw = TracingMiddleware(enabled=False)
        assert isinstance(mw, Middleware)

    def test_has_process_method(self) -> None:
        mw = TracingMiddleware(enabled=False)
        assert callable(getattr(mw, "process", None))


# ---------------------------------------------------------------------------
# No-op behavior (OTel not installed or disabled)
# ---------------------------------------------------------------------------


class TestTracingNoOp:
    """When tracing is disabled, process() is a pass-through."""

    def test_disabled_returns_envelope(self, envelope: Envelope) -> None:
        mw = TracingMiddleware(enabled=False)
        result = mw.process(envelope)
        assert result is envelope

    def test_disabled_enabled_property(self) -> None:
        mw = TracingMiddleware(enabled=False)
        assert mw.enabled is False

    def test_disabled_repr(self) -> None:
        mw = TracingMiddleware(enabled=False)
        assert "disabled" in repr(mw)

    @patch("k1.bus.middleware.tracing._HAS_OTEL", False)
    def test_no_otel_is_noop(self, envelope: Envelope) -> None:
        mw = TracingMiddleware.__new__(TracingMiddleware)
        mw._enabled = False
        mw._tracer = None
        result = mw.process(envelope)
        assert result is envelope

    def test_never_drops_envelope(self, envelope: Envelope) -> None:
        """Tracing middleware NEVER returns None."""
        mw = TracingMiddleware(enabled=False)
        result = mw.process(envelope)
        assert result is not None


# ---------------------------------------------------------------------------
# Span creation with mock tracer
# ---------------------------------------------------------------------------


class TestTracingSpanCreation:
    """When a tracer is injected, spans are created with correct attributes."""

    def _make_middleware_with_mock_tracer(self) -> tuple[TracingMiddleware, MagicMock]:
        """Create a TracingMiddleware with a mock tracer injected."""
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_span.return_value = mock_span
        mw = TracingMiddleware(enabled=False)
        # Force enable and inject mock tracer
        mw._enabled = True  # type: ignore[misc]
        mw._tracer = mock_tracer  # type: ignore[misc]
        return mw, mock_tracer

    def test_span_created_with_topic_name(self, envelope: Envelope) -> None:
        mw, mock_tracer = self._make_middleware_with_mock_tracer()
        mw.process(envelope)
        mock_tracer.start_span.assert_called_once()
        call_kwargs = mock_tracer.start_span.call_args
        assert call_kwargs[1]["name"] == "bus.publish k1.capability.completed.v1"

    def test_span_attributes_include_header_fields(self, envelope: Envelope) -> None:
        mw, mock_tracer = self._make_middleware_with_mock_tracer()
        mw.process(envelope)
        attrs = mock_tracer.start_span.call_args[1]["attributes"]
        assert attrs["bus.topic"] == "k1.capability.completed.v1"
        assert attrs["bus.envelope_id"] == 42
        assert attrs["bus.sequence"] == 7
        assert attrs["bus.priority"] == Priority.URGENT
        assert attrs["bus.parent_id"] == 10

    def test_span_cognitive_trace_id_set(self, envelope: Envelope) -> None:
        mw, mock_tracer = self._make_middleware_with_mock_tracer()
        mock_span = mock_tracer.start_span.return_value
        mw.process(envelope)
        mock_span.set_attribute.assert_any_call("bus.cognitive_trace_id", "trace-abc-123")

    def test_span_session_id_set(self, envelope: Envelope) -> None:
        mw, mock_tracer = self._make_middleware_with_mock_tracer()
        mock_span = mock_tracer.start_span.return_value
        mw.process(envelope)
        mock_span.set_attribute.assert_any_call("bus.session_id", "sess-001")

    def test_span_ended(self, envelope: Envelope) -> None:
        mw, mock_tracer = self._make_middleware_with_mock_tracer()
        mock_span = mock_tracer.start_span.return_value
        mw.process(envelope)
        mock_span.end.assert_called_once()

    def test_returns_same_envelope(self, envelope: Envelope) -> None:
        mw, _ = self._make_middleware_with_mock_tracer()
        result = mw.process(envelope)
        assert result is envelope

    def test_missing_trace_id_not_set(self, envelope_no_trace: Envelope) -> None:
        mw, mock_tracer = self._make_middleware_with_mock_tracer()
        mock_span = mock_tracer.start_span.return_value
        mw.process(envelope_no_trace)
        # cognitive_trace_id should NOT be set when empty
        for call in mock_span.set_attribute.call_args_list:
            assert call[0][0] != "bus.cognitive_trace_id"

    def test_missing_session_id_not_set(self, envelope_no_trace: Envelope) -> None:
        mw, mock_tracer = self._make_middleware_with_mock_tracer()
        mock_span = mock_tracer.start_span.return_value
        mw.process(envelope_no_trace)
        for call in mock_span.set_attribute.call_args_list:
            assert call[0][0] != "bus.session_id"


# ---------------------------------------------------------------------------
# Repr
# ---------------------------------------------------------------------------


class TestTracingRepr:
    def test_repr_disabled(self) -> None:
        mw = TracingMiddleware(enabled=False)
        assert repr(mw) == "TracingMiddleware(disabled)"

    def test_repr_enabled_with_mock(self) -> None:
        mw = TracingMiddleware(enabled=False)
        mw._enabled = True  # type: ignore[misc]
        assert repr(mw) == "TracingMiddleware(enabled)"
