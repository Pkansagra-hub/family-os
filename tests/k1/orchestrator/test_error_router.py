"""
Tests for ErrorRouter -- Stateless Error Classification (Issue 2.1.7).

Validates: route_error() classification matrix (7 adapter/severity combos),
ErrorAction returned per spec, ORCH_ERROR_ROUTED delta emission,
classify() backward-compat interface, statelessness, and defensive
handling of unknown adapters/severities.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from k1.orchestrator.events import ORCH_ERROR_ROUTED
from k1.orchestrator.orchestration.error_router import ErrorRouter
from k1.orchestrator.orchestration.orchestrator_service import AdapterException
from k1.orchestrator.types import AdapterError, ErrorAction, ErrorSeverity, ProcessingContext

# ===========================================================================
# Fakes
# ===========================================================================


class FakeDeltaEmitPort:
    """Records emitted events for assertion."""

    def __init__(self, *, fail: bool = False) -> None:
        self.events: List[Dict[str, Any]] = []
        self._fail = fail

    async def emit(self, event_topic: str, payload: Dict[str, Any], trace_id: str) -> None:
        if self._fail:
            raise RuntimeError("delta emit failed")
        self.events.append({"topic": event_topic, "payload": payload, "trace_id": trace_id})

    def find(self, topic: str) -> List[Dict[str, Any]]:
        return [e for e in self.events if e["topic"] == topic]


# ===========================================================================
# Helpers
# ===========================================================================


def _make_error(
    *,
    severity: ErrorSeverity = ErrorSeverity.DEGRADED,
    adapter_name: str = "fabric_gateway",
    operation: str = "execute",
    error_code: str = "TIMEOUT",
    error_message: str = "timed out",
    trace_id: str = "t1",
) -> AdapterError:
    return AdapterError(
        severity=severity,
        adapter_name=adapter_name,
        operation=operation,
        error_code=error_code,
        error_message=error_message,
        trace_id=trace_id,
    )


def _make_exception(
    *,
    severity: ErrorSeverity = ErrorSeverity.DEGRADED,
    adapter_name: str = "fabric_gateway",
    operation: str = "execute",
    error_code: str = "TIMEOUT",
    error_message: str = "timed out",
) -> AdapterException:
    return AdapterException(
        _make_error(
            severity=severity,
            adapter_name=adapter_name,
            operation=operation,
            error_code=error_code,
            error_message=error_message,
        )
    )


def _make_ctx(trace_id: str = "t1") -> Dict[str, Any]:
    return {"trace_id": trace_id}


# ===========================================================================
# Tests: _classify_error (pure classification logic)
# ===========================================================================


class TestClassifyError:
    """Validate the 7-row classification matrix + defensive cases."""

    # --- RECOVERABLE severity ---

    def test_mailbox_recoverable_returns_retry(self) -> None:
        error = _make_error(severity=ErrorSeverity.RECOVERABLE, adapter_name="mailbox")
        action = ErrorRouter._classify_error(error)
        assert action.action == "RETRY"
        assert action.retry_count == 1
        assert action.fallback_value is None
        assert action.reason == "transient error"

    def test_delta_emit_recoverable_returns_retry(self) -> None:
        error = _make_error(severity=ErrorSeverity.RECOVERABLE, adapter_name="delta_emit")
        action = ErrorRouter._classify_error(error)
        assert action.action == "RETRY"
        assert action.retry_count == 1

    def test_bridge_write_recoverable_returns_retry(self) -> None:
        error = _make_error(severity=ErrorSeverity.RECOVERABLE, adapter_name="bridge_write")
        action = ErrorRouter._classify_error(error)
        assert action.action == "RETRY"
        assert action.retry_count == 1

    def test_event_sub_recoverable_returns_retry(self) -> None:
        error = _make_error(severity=ErrorSeverity.RECOVERABLE, adapter_name="event_sub")
        action = ErrorRouter._classify_error(error)
        assert action.action == "RETRY"
        assert action.retry_count == 1

    # --- DEGRADED severity ---

    def test_fabric_gateway_degraded_returns_degrade(self) -> None:
        error = _make_error(severity=ErrorSeverity.DEGRADED, adapter_name="fabric_gateway")
        action = ErrorRouter._classify_error(error)
        assert action.action == "DEGRADE"
        assert action.retry_count == 0
        assert action.fallback_value is None
        assert action.reason == "Fabric step failed"

    def test_planner_degraded_returns_fallback(self) -> None:
        error = _make_error(severity=ErrorSeverity.DEGRADED, adapter_name="planner")
        action = ErrorRouter._classify_error(error)
        assert action.action == "FALLBACK"
        assert action.retry_count == 0
        assert action.fallback_value is None
        assert action.reason == "degrade HIGH to MEDIUM"

    def test_state_read_degraded_returns_degrade_with_empty_snapshot(self) -> None:
        error = _make_error(severity=ErrorSeverity.DEGRADED, adapter_name="state_read")
        action = ErrorRouter._classify_error(error)
        assert action.action == "DEGRADE"
        assert action.retry_count == 0
        assert action.fallback_value == {}
        assert action.reason == "stale context"

    # --- TERMINAL severity ---

    def test_terminal_any_adapter_returns_abort(self) -> None:
        error = _make_error(
            severity=ErrorSeverity.TERMINAL,
            adapter_name="fabric_gateway",
            error_message="disk full",
        )
        action = ErrorRouter._classify_error(error)
        assert action.action == "ABORT"
        assert action.retry_count == 0
        assert action.fallback_value is None
        assert action.reason == "disk full"

    def test_terminal_mailbox_returns_abort(self) -> None:
        error = _make_error(severity=ErrorSeverity.TERMINAL, adapter_name="mailbox")
        action = ErrorRouter._classify_error(error)
        assert action.action == "ABORT"

    # --- Defensive: unknown adapters ---

    def test_unknown_adapter_recoverable_still_retries(self) -> None:
        error = _make_error(severity=ErrorSeverity.RECOVERABLE, adapter_name="unknown_port")
        action = ErrorRouter._classify_error(error)
        assert action.action == "RETRY"
        assert action.retry_count == 1
        assert "unknown adapter" in action.reason

    def test_unknown_adapter_degraded_still_degrades(self) -> None:
        error = _make_error(severity=ErrorSeverity.DEGRADED, adapter_name="unknown_port")
        action = ErrorRouter._classify_error(error)
        assert action.action == "DEGRADE"
        assert action.retry_count == 0
        assert "unknown adapter" in action.reason


# ===========================================================================
# Tests: route_error() (async, with delta emission)
# ===========================================================================


class TestRouteError:
    """Validate async route_error returns ErrorAction and emits delta."""

    @pytest.mark.asyncio
    async def test_route_error_returns_correct_action(self) -> None:
        delta = FakeDeltaEmitPort()
        router = ErrorRouter(delta_port=delta)
        error = _make_error(severity=ErrorSeverity.RECOVERABLE, adapter_name="mailbox")
        action = await router.route_error(error, _make_ctx())

        assert action.action == "RETRY"
        assert action.retry_count == 1

    @pytest.mark.asyncio
    async def test_route_error_emits_diagnostic_delta(self) -> None:
        delta = FakeDeltaEmitPort()
        router = ErrorRouter(delta_port=delta)
        error = _make_error(
            severity=ErrorSeverity.DEGRADED,
            adapter_name="fabric_gateway",
            error_code="TIMEOUT",
            error_message="timed out",
            trace_id="trace-42",
        )
        await router.route_error(error, {"trace_id": "trace-42"})

        events = delta.find(ORCH_ERROR_ROUTED)
        assert len(events) == 1
        payload = events[0]["payload"]
        assert payload["adapter"] == "fabric_gateway"
        assert payload["severity"] == "DEGRADED"
        assert payload["action"] == "DEGRADE"
        assert payload["retry_count"] == 0
        assert payload["reason"] == "Fabric step failed"
        assert payload["error_code"] == "TIMEOUT"
        assert payload["error_message"] == "timed out"
        assert payload["trace_id"] == "trace-42"
        assert events[0]["trace_id"] == "trace-42"

    @pytest.mark.asyncio
    async def test_route_error_delta_trace_id_from_context(self) -> None:
        """trace_id comes from context dict, not error."""
        delta = FakeDeltaEmitPort()
        router = ErrorRouter(delta_port=delta)
        error = _make_error(trace_id="error-trace")
        await router.route_error(error, {"trace_id": "ctx-trace"})

        events = delta.find(ORCH_ERROR_ROUTED)
        assert events[0]["trace_id"] == "ctx-trace"

    @pytest.mark.asyncio
    async def test_route_error_delta_fallback_trace_id_from_error(self) -> None:
        """If context has no trace_id, fall back to error.trace_id."""
        delta = FakeDeltaEmitPort()
        router = ErrorRouter(delta_port=delta)
        error = _make_error(trace_id="error-trace")
        await router.route_error(error, {})

        events = delta.find(ORCH_ERROR_ROUTED)
        assert events[0]["trace_id"] == "error-trace"

    @pytest.mark.asyncio
    async def test_route_error_delta_emission_failure_does_not_raise(self) -> None:
        """Delta emission failure is swallowed -- ErrorRouter must not amplify."""
        delta = FakeDeltaEmitPort(fail=True)
        router = ErrorRouter(delta_port=delta)
        error = _make_error(severity=ErrorSeverity.TERMINAL, error_message="fatal")
        # Must not raise.
        action = await router.route_error(error, _make_ctx())
        assert action.action == "ABORT"
        assert action.reason == "fatal"

    @pytest.mark.asyncio
    async def test_route_error_terminal_emits_delta(self) -> None:
        delta = FakeDeltaEmitPort()
        router = ErrorRouter(delta_port=delta)
        error = _make_error(
            severity=ErrorSeverity.TERMINAL,
            adapter_name="planner",
            error_message="unrecoverable",
        )
        action = await router.route_error(error, _make_ctx())

        assert action.action == "ABORT"
        events = delta.find(ORCH_ERROR_ROUTED)
        assert len(events) == 1
        assert events[0]["payload"]["action"] == "ABORT"


# ===========================================================================
# Tests: classify() (sync backward-compat interface)
# ===========================================================================


class TestClassify:
    """Validate sync classify() returns ErrorSeverity from exception."""

    def test_classify_returns_severity_from_exception(self) -> None:
        router = ErrorRouter(delta_port=FakeDeltaEmitPort())
        exc = _make_exception(severity=ErrorSeverity.DEGRADED)
        ctx = ProcessingContext(trace_id="t1", request_id="r1", tier="MEDIUM")
        assert router.classify(exc, ctx) == ErrorSeverity.DEGRADED

    def test_classify_recoverable(self) -> None:
        router = ErrorRouter(delta_port=FakeDeltaEmitPort())
        exc = _make_exception(severity=ErrorSeverity.RECOVERABLE)
        ctx = ProcessingContext(trace_id="t1", request_id="r1", tier="MEDIUM")
        assert router.classify(exc, ctx) == ErrorSeverity.RECOVERABLE

    def test_classify_terminal(self) -> None:
        router = ErrorRouter(delta_port=FakeDeltaEmitPort())
        exc = _make_exception(severity=ErrorSeverity.TERMINAL)
        ctx = ProcessingContext(trace_id="t1", request_id="r1", tier="MEDIUM")
        assert router.classify(exc, ctx) == ErrorSeverity.TERMINAL


# ===========================================================================
# Tests: statelessness
# ===========================================================================


class TestStatelessness:
    """Verify ErrorRouter has no mutable state."""

    @pytest.mark.asyncio
    async def test_repeated_calls_produce_same_result(self) -> None:
        delta = FakeDeltaEmitPort()
        router = ErrorRouter(delta_port=delta)
        error = _make_error(severity=ErrorSeverity.DEGRADED, adapter_name="planner")
        a1 = await router.route_error(error, _make_ctx())
        a2 = await router.route_error(error, _make_ctx())
        assert a1 == a2
        assert len(delta.events) == 2  # two independent deltas

    def test_no_mutable_attributes(self) -> None:
        """ErrorRouter should only have _delta_port (immutable ref)."""
        router = ErrorRouter(delta_port=FakeDeltaEmitPort())
        # __slots__ restricts attributes.
        assert hasattr(router, "_delta_port")
        with pytest.raises(AttributeError):
            router.some_new_state = "bad"  # type: ignore[attr-defined]


# ===========================================================================
# Tests: ErrorAction dataclass
# ===========================================================================


class TestErrorAction:
    """Validate ErrorAction is a frozen dataclass with correct fields."""

    def test_frozen(self) -> None:
        action = ErrorAction(action="RETRY", retry_count=1, reason="test")
        with pytest.raises(AttributeError):
            action.action = "ABORT"  # type: ignore[misc]

    def test_default_values(self) -> None:
        action = ErrorAction(action="ABORT")
        assert action.retry_count == 0
        assert action.fallback_value is None
        assert action.reason == ""

    def test_equality(self) -> None:
        a1 = ErrorAction(action="RETRY", retry_count=1, reason="x")
        a2 = ErrorAction(action="RETRY", retry_count=1, reason="x")
        assert a1 == a2

    def test_fields_populated(self) -> None:
        action = ErrorAction(
            action="DEGRADE",
            retry_count=0,
            fallback_value={"data": []},
            reason="partial",
        )
        assert action.action == "DEGRADE"
        assert action.fallback_value == {"data": []}
