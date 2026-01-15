"""
Tests for CapabilityRequest and CapabilityResponse dataclasses.

Epic 2.1: CapabilityFabric Implementation
Issue 2.1.1: CapabilityRequest/Response Dataclasses

Coverage:
- CapabilityRequest creation and unique ID generation
- CapabilityRequest elapsed_ms, remaining_ms and expiration tracking
- CapabilityRequest monotonic timing and deadline propagation
- CapabilityResponse factory methods (success, error, timeout)
- RequestStatus enum values
"""

from __future__ import annotations

import time
import uuid

from k0.fabric.messages import CapabilityRequest, CapabilityResponse, RequestStatus


class TestRequestStatus:
    """Tests for RequestStatus enum."""

    def test_status_values_exist(self) -> None:
        """All expected status values exist."""
        assert RequestStatus.PENDING is not None
        assert RequestStatus.SUCCESS is not None
        assert RequestStatus.ERROR is not None
        assert RequestStatus.TIMEOUT is not None

    def test_status_values_are_distinct(self) -> None:
        """All status values are distinct."""
        values = [
            RequestStatus.PENDING,
            RequestStatus.SUCCESS,
            RequestStatus.ERROR,
            RequestStatus.TIMEOUT,
        ]
        assert len(values) == len(set(values))


class TestCapabilityRequest:
    """Tests for CapabilityRequest dataclass."""

    def test_request_generates_unique_id(self) -> None:
        """Each request gets a unique request_id by default."""
        req1 = CapabilityRequest(capability="test.cap", payload={})
        req2 = CapabilityRequest(capability="test.cap", payload={})
        assert req1.request_id != req2.request_id
        # Validate they are valid UUIDs
        uuid.UUID(req1.request_id)
        uuid.UUID(req2.request_id)

    def test_request_accepts_custom_id(self) -> None:
        """Request can accept a custom request_id."""
        custom_id = "custom-12345"
        req = CapabilityRequest(
            capability="test.cap",
            payload={},
            request_id=custom_id,
        )
        assert req.request_id == custom_id

    def test_request_stores_capability_and_payload(self) -> None:
        """Request correctly stores capability and payload."""
        payload = {"key": "value", "nested": {"a": 1}}
        req = CapabilityRequest(
            capability="memory.read",
            payload=payload,
        )
        assert req.capability == "memory.read"
        assert req.payload == payload

    def test_request_copies_payload(self) -> None:
        """Request copies payload to prevent mutation issues."""
        original = {"key": "value"}
        req = CapabilityRequest(capability="test.cap", payload=original)
        # Modify original
        original["key"] = "modified"
        # Request payload should be unchanged
        assert req.payload["key"] == "value"

    def test_request_default_timeout(self) -> None:
        """Request has default timeout of 100ms (fast by default)."""
        req = CapabilityRequest(capability="test.cap", payload={})
        assert req.timeout_ms == 100

    def test_request_custom_timeout(self) -> None:
        """Request accepts custom timeout."""
        req = CapabilityRequest(
            capability="test.cap",
            payload={},
            timeout_ms=10000,
        )
        assert req.timeout_ms == 10000

    def test_request_optional_fields(self) -> None:
        """Request supports optional caller_id and trace_id."""
        req = CapabilityRequest(
            capability="test.cap",
            payload={},
            caller_id="pipeline.P02",
            trace_id="trace-abc-123",
        )
        assert req.caller_id == "pipeline.P02"
        assert req.trace_id == "trace-abc-123"

    def test_request_has_monotonic_timing(self) -> None:
        """Request uses monotonic time for clock-safe deadlines."""
        before = time.monotonic()
        req = CapabilityRequest(capability="test.cap", payload={})
        after = time.monotonic()

        assert isinstance(req.created_mono, float)
        assert req.created_mono >= before
        assert req.created_mono <= after

    def test_request_has_wall_time_for_logging(self) -> None:
        """Request stores wall time for logging purposes."""
        before = time.time()
        req = CapabilityRequest(capability="test.cap", payload={})
        after = time.time()

        assert isinstance(req.created_wall, float)
        assert req.created_wall >= before
        assert req.created_wall <= after

    def test_request_deadline_computed_on_init(self) -> None:
        """Request deadline_mono is computed from timeout_ms."""
        req = CapabilityRequest(
            capability="test.cap",
            payload={},
            timeout_ms=500,
        )
        expected_deadline = req.created_mono + 0.5  # 500ms = 0.5s
        assert abs(req.deadline_mono - expected_deadline) < 0.001

    def test_request_elapsed_ms_uses_monotonic(self) -> None:
        """elapsed_ms uses monotonic time for clock safety."""
        req = CapabilityRequest(capability="test.cap", payload={})
        time.sleep(0.05)  # 50ms
        elapsed = req.elapsed_ms()
        assert elapsed >= 40  # Allow some tolerance

    def test_request_remaining_ms_for_budget_propagation(self) -> None:
        """remaining_ms returns time until deadline for downstream budgeting."""
        req = CapabilityRequest(
            capability="test.cap",
            payload={},
            timeout_ms=1000,  # 1 second
        )
        remaining = req.remaining_ms()
        # Should be close to 1000ms initially
        assert 900 <= remaining <= 1000

    def test_request_remaining_ms_decreases(self) -> None:
        """remaining_ms decreases as time passes."""
        req = CapabilityRequest(
            capability="test.cap",
            payload={},
            timeout_ms=1000,
        )
        time.sleep(0.05)  # 50ms
        remaining = req.remaining_ms()
        assert remaining < 960  # Should be less than 960ms

    def test_request_remaining_ms_never_negative(self) -> None:
        """remaining_ms returns 0 after deadline, never negative."""
        req = CapabilityRequest(
            capability="test.cap",
            payload={},
            timeout_ms=50,
        )
        time.sleep(0.1)  # Wait 100ms (past deadline)
        assert req.remaining_ms() == 0.0

    def test_request_is_expired_false_initially(self) -> None:
        """Request is not expired immediately after creation."""
        req = CapabilityRequest(
            capability="test.cap",
            payload={},
            timeout_ms=5000,
        )
        assert req.is_expired() is False

    def test_request_is_expired_after_timeout(self) -> None:
        """Request is expired after timeout_ms has passed."""
        req = CapabilityRequest(
            capability="test.cap",
            payload={},
            timeout_ms=50,  # 50ms timeout
        )
        time.sleep(0.1)  # Wait 100ms
        assert req.is_expired() is True


class TestCapabilityResponse:
    """Tests for CapabilityResponse dataclass."""

    def test_response_success_factory(self) -> None:
        """success() factory creates a success response."""
        req = CapabilityRequest(capability="test.cap", payload={})
        result = {"data": "value"}

        resp = CapabilityResponse.success(
            request_id=req.request_id,
            result=result,
            provider_id="module.TestProvider",
            handler_ms=5.0,
            e2e_ms=7.0,
        )

        assert resp.request_id == req.request_id
        assert resp.status == RequestStatus.SUCCESS
        assert resp.result == result
        assert resp.error_message is None
        assert resp.provider_id == "module.TestProvider"
        assert resp.handler_ms == 5.0
        assert resp.e2e_ms == 7.0
        assert resp.is_success is True
        assert resp.is_error is False
        assert resp.is_timeout is False

    def test_response_success_defaults_e2e_to_handler(self) -> None:
        """success() defaults e2e_ms to handler_ms if not provided."""
        resp = CapabilityResponse.success(
            request_id="req-123",
            result={},
            provider_id="test.provider",
            handler_ms=10.0,
        )
        assert resp.handler_ms == 10.0
        assert resp.e2e_ms == 10.0  # Defaults to handler_ms

    def test_response_error_factory(self) -> None:
        """error() factory creates an error response."""
        req = CapabilityRequest(capability="test.cap", payload={})
        error_msg = "Something went wrong"

        resp = CapabilityResponse.error(
            request_id=req.request_id,
            error=error_msg,
            provider_id="module.FailedProvider",
            handler_ms=3.0,
            e2e_ms=5.0,
        )

        assert resp.request_id == req.request_id
        assert resp.status == RequestStatus.ERROR
        assert resp.result is None
        assert resp.error_message == error_msg
        assert resp.provider_id == "module.FailedProvider"
        assert resp.handler_ms == 3.0
        assert resp.e2e_ms == 5.0
        assert resp.is_success is False
        assert resp.is_error is True
        assert resp.is_timeout is False

    def test_response_timeout_factory(self) -> None:
        """timeout() factory creates a timeout response with structured data."""
        req = CapabilityRequest(capability="test.cap", payload={})

        resp = CapabilityResponse.timeout(
            request_id=req.request_id,
            timeout_ms=100.0,
            e2e_ms=105.0,
        )

        assert resp.request_id == req.request_id
        assert resp.status == RequestStatus.TIMEOUT
        assert resp.result is None
        assert "100.0ms" in resp.error_message
        assert resp.provider_id is None
        assert resp.timeout_ms == 100.0  # Structured field
        assert resp.e2e_ms == 105.0
        assert resp.is_success is False
        assert resp.is_error is False
        assert resp.is_timeout is True

    def test_response_timeout_has_structured_field(self) -> None:
        """Timeout response stores timeout_ms for programmatic access."""
        resp = CapabilityResponse.timeout(
            request_id="req-123",
            timeout_ms=250.0,
        )
        # Can access timeout_ms programmatically (not just in error string)
        assert resp.timeout_ms == 250.0
        assert resp.is_timeout is True

    def test_response_latency_fields_distinct(self) -> None:
        """Response has separate handler_ms and e2e_ms fields."""
        resp = CapabilityResponse.success(
            request_id="req-123",
            result={},
            provider_id="test",
            handler_ms=10.0,
            e2e_ms=15.0,
        )
        # handler_ms = just the handler execution time
        assert resp.handler_ms == 10.0
        # e2e_ms = total time including queue, routing, retries
        assert resp.e2e_ms == 15.0

    def test_response_error_without_provider(self) -> None:
        """Error response can have no provider_id."""
        req = CapabilityRequest(capability="test.cap", payload={})

        resp = CapabilityResponse.error(
            request_id=req.request_id,
            error="No provider found",
        )

        assert resp.provider_id is None
        assert resp.is_error is True
