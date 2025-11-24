"""Tests for k0/ports/drivers.py"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

from k0.outbox import DriverHandshakeError, DriverWorkerPool
from k0.ports.drivers import (
    DriverHandshakeRequest,
    DriverHandshakeResponse,
    _error_response,
    _format_timestamp,
    _resolve_trace_id,
    driver_handshake,
)


class TestDriverHandshakeRequest:
    """Test DriverHandshakeRequest model."""

    def test_valid_http_request(self):
        """Test creating a valid HTTP driver handshake request."""
        request = DriverHandshakeRequest(
            alias="test-driver",
            transport="http",
            endpoint="https://example.com/api",
            capabilities=["command", "query"],
            metadata={"version": "1.0"},
        )
        assert request.alias == "test-driver"
        assert request.transport == "http"
        assert request.endpoint == "https://example.com/api"
        assert request.capabilities == ["command", "query"]

    def test_valid_grpc_request(self):
        """Test creating a valid gRPC driver handshake request."""
        request = DriverHandshakeRequest(
            alias="grpc-driver",
            transport="grpc",
            endpoint="localhost:50051",
            capabilities=["observe"],
        )
        assert request.alias == "grpc-driver"
        assert request.transport == "grpc"

    def test_invalid_empty_alias(self):
        """Test validation with empty alias."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError) as exc_info:
            DriverHandshakeRequest(
                alias="",
                transport="http",
                endpoint="https://example.com",
            )
        assert "alias" in str(exc_info.value)
        assert "too_short" in str(exc_info.value)

    def test_invalid_empty_endpoint(self):
        """Test validation with empty endpoint."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError) as exc_info:
            DriverHandshakeRequest(
                alias="test",
                transport="http",
                endpoint="",
            )
        assert "endpoint" in str(exc_info.value)
        assert "too_short" in str(exc_info.value)

    def test_invalid_http_endpoint(self):
        """Test validation with invalid HTTP endpoint."""
        with pytest.raises(ValueError, match="HTTP transport requires a valid http"):
            DriverHandshakeRequest(
                alias="test",
                transport="http",
                endpoint="invalid-url",
            )

    def test_invalid_grpc_endpoint(self):
        """Test validation with invalid gRPC endpoint."""
        with pytest.raises(ValueError, match="gRPC transport requires a scheme"):
            DriverHandshakeRequest(
                alias="test",
                transport="grpc",
                endpoint="invalid",
            )

    def test_duplicate_capabilities_removed(self):
        """Test that duplicate capabilities are removed."""
        request = DriverHandshakeRequest(
            alias="test",
            transport="http",
            endpoint="https://example.com",
            capabilities=["cmd", "cmd", "query"],
        )
        assert request.capabilities == ["cmd", "query"]

    def test_empty_capability_removed(self):
        """Test that empty capabilities are removed."""
        with pytest.raises(ValueError, match="capabilities entries must not be empty"):
            DriverHandshakeRequest(
                alias="test",
                transport="http",
                endpoint="https://example.com",
                capabilities=["", "valid"],
            )


class TestDriverHandshakeResponse:
    """Test DriverHandshakeResponse model."""

    def test_valid_response(self):
        """Test creating a valid response."""
        response = DriverHandshakeResponse(
            session_id="1234567890abcdef1234567890abcdef",
            alias="test-driver",
            driver_module="test.module",
            transport="http",
            endpoint="https://example.com",
            lease_seconds=3600,
            issued_at="2023-01-01T00:00:00Z",
            expires_at="2023-01-01T01:00:00Z",
            capabilities=["command"],
            metadata={"key": "value"},
        )
        assert response.session_id == "1234567890abcdef1234567890abcdef"
        assert response.alias == "test-driver"

    def test_invalid_session_id_pattern(self):
        """Test validation with invalid session ID pattern."""
        with pytest.raises(ValueError):
            DriverHandshakeResponse(
                session_id="invalid",
                alias="test",
                driver_module="test.module",
                transport="http",
                endpoint="https://example.com",
                lease_seconds=3600,
                issued_at="2023-01-01T00:00:00Z",
                expires_at="2023-01-01T01:00:00Z",
            )


class TestUtilityFunctions:
    """Test utility functions."""

    def test_format_timestamp(self):
        """Test timestamp formatting."""
        from datetime import datetime, timezone
        dt = datetime(2023, 1, 1, 12, 30, 45, 123456, tzinfo=timezone.utc)
        formatted = _format_timestamp(dt)
        assert formatted == "2023-01-01T12:30:45Z"

    def test_resolve_trace_id_existing(self):
        """Test resolving existing trace ID."""
        request = MagicMock()
        request.state.cognitive_trace_id = "existing-trace-id"
        trace_id = _resolve_trace_id(request)
        assert trace_id == "existing-trace-id"

    def test_resolve_trace_id_generate_new(self):
        """Test generating new trace ID."""
        request = MagicMock()
        del request.state.cognitive_trace_id  # Simulate missing attribute
        trace_id = _resolve_trace_id(request)
        assert len(trace_id) == 32  # UUID hex length
        assert request.state.cognitive_trace_id == trace_id

    def test_error_response(self):
        """Test error response creation."""
        request = MagicMock()
        response = _error_response(
            request,
            status_code=400,
            code="TEST_ERROR",
            reason="Test error",
            hint="Try again",
        )
        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        content = response.body
        assert b"TEST_ERROR" in content
        assert b"Test error" in content


class TestDriverHandshakeEndpoint:
    """Test the driver_handshake endpoint."""

    @pytest.fixture
    def mock_request(self):
        """Create a mock request."""
        request = MagicMock(spec=Request)
        request.app.state.driver_worker_pool = None
        return request

    @pytest.fixture
    def mock_pool(self):
        """Create a mock driver worker pool."""
        pool = MagicMock(spec=DriverWorkerPool)
        pool.lease_seconds = 3600
        return pool

    @pytest.fixture
    def mock_session(self):
        """Create a mock session."""
        from datetime import datetime, timezone
        session = MagicMock()
        session.session_id = "1234567890abcdef1234567890abcdef"
        session.alias = "test-driver"
        session.driver_module = "test.module"
        session.transport = "http"
        session.endpoint = "https://example.com"
        session.issued_at = datetime(2023, 1, 1, tzinfo=timezone.utc)
        session.expires_at = datetime(2023, 1, 1, 1, tzinfo=timezone.utc)
        session.capabilities = ["command"]
        session.metadata = {"version": "1.0"}
        return session

    @pytest.mark.asyncio
    async def test_handshake_success(self, mock_request, mock_pool, mock_session):
        """Test successful driver handshake."""
        mock_request.app.state.driver_worker_pool = mock_pool
        mock_pool.register_handshake.return_value = mock_session

        payload = DriverHandshakeRequest(
            alias="test-driver",
            transport="http",
            endpoint="https://example.com",
            capabilities=["command"],
        )

        response = await driver_handshake(payload, mock_request)

        assert isinstance(response, DriverHandshakeResponse)
        assert response.session_id == "1234567890abcdef1234567890abcdef"
        assert response.alias == "test-driver"
        assert response.lease_seconds == 3600
        mock_pool.register_handshake.assert_called_once()

    @pytest.mark.asyncio
    async def test_pool_unavailable(self, mock_request):
        """Test handshake when pool is unavailable."""
        mock_request.app.state.driver_worker_pool = None

        payload = DriverHandshakeRequest(
            alias="test-driver",
            transport="http",
            endpoint="https://example.com",
        )

        response = await driver_handshake(payload, mock_request)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 503
        content = response.body
        assert b"DRIVER_POOL_UNAVAILABLE" in content

    @pytest.mark.asyncio
    async def test_handshake_error(self, mock_request, mock_pool):
        """Test handshake with registration error."""
        mock_request.app.state.driver_worker_pool = mock_pool
        mock_pool.register_handshake.side_effect = DriverHandshakeError(
            status_code=400,
            code="INVALID_DRIVER",
            reason="Driver validation failed",
            hint="Check driver configuration",
        )

        payload = DriverHandshakeRequest(
            alias="invalid-driver",
            transport="http",
            endpoint="https://example.com",
        )

        response = await driver_handshake(payload, mock_request)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        content = response.body
        assert b"INVALID_DRIVER" in content
        assert b"Driver validation failed" in content