"""Real component tests for HttpTransport.

Tests lifecycle (open/close), post_command, health check, and error handling
using httpx's built-in transport facility for deterministic HTTP responses.
No external mocking libraries -- httpx.MockTransport is httpx's own test API.

Milestone: M2 Epic 2.15
"""

from __future__ import annotations

import httpx
import pytest

from bridge.core.transport import HttpResult, HttpTransport, TransportConfig

# ---------------------------------------------------------------------------
# Helpers: httpx.MockTransport for deterministic HTTP responses
# ---------------------------------------------------------------------------


def _make_transport_with_handler(handler) -> HttpTransport:
    """Create an HttpTransport with a custom httpx handler for testing.

    Uses httpx.MockTransport -- httpx's built-in test transport,
    NOT an external mock library.
    """
    transport = HttpTransport(TransportConfig(base_url="http://test-k0:8000"))
    mock_transport = httpx.MockTransport(handler)
    transport._client = httpx.AsyncClient(
        transport=mock_transport,
        base_url="http://test-k0:8000",
    )
    return transport


def _handler_200(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"status": "ok", "idem_key": "abc123"})


def _handler_400(request: httpx.Request) -> httpx.Response:
    return httpx.Response(400, json={"reason": "BODY_VALIDATION_FAILED", "violations": []})


def _handler_403(request: httpx.Request) -> httpx.Response:
    return httpx.Response(403, json={"reason": "policy_denied"})


def _handler_409(request: httpx.Request) -> httpx.Response:
    return httpx.Response(409, json={"reason": "DUPLICATE", "idem_key": "abc123"})


def _handler_429(request: httpx.Request) -> httpx.Response:
    return httpx.Response(429, json={"reason": "rate_limited"})


def _handler_500(request: httpx.Request) -> httpx.Response:
    return httpx.Response(500, json={"error": "internal_error"})


def _handler_503(request: httpx.Request) -> httpx.Response:
    return httpx.Response(503, text="Service Unavailable")


def _handler_health_200(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/healthz":
        return httpx.Response(200, json={"status": "healthy"})
    return httpx.Response(404)


def _handler_health_503(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/healthz":
        return httpx.Response(503)
    return httpx.Response(404)


def _handler_no_json_body(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, text="OK")


# ===========================================================================
# Lifecycle: open / close
# ===========================================================================


class TestTransportLifecycle:
    """Verify HttpTransport lifecycle management."""

    async def test_open_creates_client(self) -> None:
        transport = HttpTransport()
        assert transport._client is None
        await transport.open()
        assert transport._client is not None
        await transport.close()

    async def test_close_destroys_client(self) -> None:
        transport = HttpTransport()
        await transport.open()
        await transport.close()
        assert transport._client is None

    async def test_double_open_is_idempotent(self) -> None:
        transport = HttpTransport()
        await transport.open()
        client1 = transport._client
        await transport.open()
        client2 = transport._client
        assert client1 is client2  # same client
        await transport.close()

    async def test_close_without_open_is_safe(self) -> None:
        transport = HttpTransport()
        await transport.close()  # should not raise

    async def test_not_opened_raises_on_post(self) -> None:
        transport = HttpTransport()
        with pytest.raises(RuntimeError, match="not opened"):
            await transport.post_command(b'{"test": true}')

    async def test_not_opened_raises_on_health(self) -> None:
        transport = HttpTransport()
        with pytest.raises(RuntimeError, match="not opened"):
            await transport.check_health()


# ===========================================================================
# post_command: various HTTP status codes
# ===========================================================================


class TestPostCommand:
    """Verify post_command returns correct HttpResult for each status."""

    async def test_200_success(self) -> None:
        transport = _make_transport_with_handler(_handler_200)
        result = await transport.post_command(b'{"topic":"memory.write"}')
        assert result.status_code == 200
        assert result.body is not None
        assert result.body["status"] == "ok"
        assert result.error is None
        await transport.close()

    async def test_400_contract_violation(self) -> None:
        transport = _make_transport_with_handler(_handler_400)
        result = await transport.post_command(b"{}")
        assert result.status_code == 400
        assert result.body is not None
        assert result.body["reason"] == "BODY_VALIDATION_FAILED"
        await transport.close()

    async def test_403_policy_denied(self) -> None:
        transport = _make_transport_with_handler(_handler_403)
        result = await transport.post_command(b"{}")
        assert result.status_code == 403
        assert result.body is not None
        assert result.body["reason"] == "policy_denied"
        await transport.close()

    async def test_409_duplicate(self) -> None:
        transport = _make_transport_with_handler(_handler_409)
        result = await transport.post_command(b"{}")
        assert result.status_code == 409
        assert result.body is not None
        assert result.body["reason"] == "DUPLICATE"
        await transport.close()

    async def test_429_rate_limited(self) -> None:
        transport = _make_transport_with_handler(_handler_429)
        result = await transport.post_command(b"{}")
        assert result.status_code == 429
        await transport.close()

    async def test_500_server_error(self) -> None:
        transport = _make_transport_with_handler(_handler_500)
        result = await transport.post_command(b"{}")
        assert result.status_code == 500
        assert result.body is not None
        assert result.body["error"] == "internal_error"
        await transport.close()

    async def test_503_no_json_body(self) -> None:
        transport = _make_transport_with_handler(_handler_503)
        result = await transport.post_command(b"{}")
        assert result.status_code == 503
        # text body, not JSON -- body should be None
        assert result.body is None
        await transport.close()

    async def test_200_no_json_body(self) -> None:
        transport = _make_transport_with_handler(_handler_no_json_body)
        result = await transport.post_command(b"{}")
        assert result.status_code == 200
        # "OK" is not valid JSON -> body is None
        assert result.body is None
        await transport.close()


# ===========================================================================
# post_command: sends correct request
# ===========================================================================


class TestPostCommandRequest:
    """Verify the request is formed correctly."""

    async def test_posts_to_command_submit_path(self) -> None:
        captured_requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured_requests.append(request)
            return httpx.Response(200, json={"status": "ok"})

        transport = _make_transport_with_handler(handler)
        await transport.post_command(b'{"topic":"test"}')
        assert len(captured_requests) == 1
        assert captured_requests[0].url.path == "/k0/command.submit"
        await transport.close()

    async def test_sends_json_content_type(self) -> None:
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={})

        transport = _make_transport_with_handler(handler)
        await transport.post_command(b"{}")
        assert captured[0].headers["content-type"] == "application/json"
        await transport.close()

    async def test_sends_exact_bytes(self) -> None:
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={})

        transport = _make_transport_with_handler(handler)
        payload = b'{"key":"value"}'
        await transport.post_command(payload)
        assert captured[0].content == payload
        await transport.close()


# ===========================================================================
# check_health
# ===========================================================================


class TestCheckHealth:
    """Verify lightweight health probe."""

    async def test_health_200_returns_true(self) -> None:
        transport = _make_transport_with_handler(_handler_health_200)
        assert await transport.check_health() is True
        await transport.close()

    async def test_health_503_returns_false(self) -> None:
        transport = _make_transport_with_handler(_handler_health_503)
        assert await transport.check_health() is False
        await transport.close()


# ===========================================================================
# Error handling: connection errors
# ===========================================================================


class TestConnectionErrors:
    """Verify graceful handling of network-level errors."""

    async def test_connect_error_returns_status_0(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        transport = _make_transport_with_handler(handler)
        result = await transport.post_command(b"{}")
        assert result.status_code == 0
        assert result.error is not None
        assert "connection_error" in result.error
        await transport.close()

    async def test_timeout_returns_status_0(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TimeoutException("Read timed out")

        transport = _make_transport_with_handler(handler)
        result = await transport.post_command(b"{}")
        assert result.status_code == 0
        assert result.error is not None
        assert "timeout" in result.error
        await transport.close()

    async def test_generic_http_error_returns_status_0(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.HTTPError("Protocol error")

        transport = _make_transport_with_handler(handler)
        result = await transport.post_command(b"{}")
        assert result.status_code == 0
        assert "http_error" in (result.error or "")
        await transport.close()


# ===========================================================================
# TransportConfig defaults
# ===========================================================================


class TestTransportConfig:
    """Verify default config values."""

    def test_default_values(self) -> None:
        cfg = TransportConfig()
        assert cfg.base_url == "http://localhost:8080"
        assert cfg.connect_timeout_s == 5.0
        assert cfg.read_timeout_s == 30.0
        assert cfg.tls_verify is False
        assert cfg.max_keepalive_connections == 5
        assert cfg.max_connections == 10

    def test_custom_values(self) -> None:
        cfg = TransportConfig(
            base_url="https://k0.example.com",
            connect_timeout_s=10.0,
            read_timeout_s=60.0,
            tls_verify=True,
            max_keepalive_connections=10,
            max_connections=20,
        )
        assert cfg.base_url == "https://k0.example.com"
        assert cfg.tls_verify is True

    def test_frozen(self) -> None:
        cfg = TransportConfig()
        with pytest.raises(AttributeError):
            cfg.base_url = "new"  # type: ignore[misc]


# ===========================================================================
# HttpResult properties
# ===========================================================================


class TestHttpResult:
    """Verify HttpResult dataclass."""

    def test_success_result(self) -> None:
        result = HttpResult(status_code=200, body={"ok": True})
        assert result.status_code == 200
        assert result.body == {"ok": True}
        assert result.error is None

    def test_error_result(self) -> None:
        result = HttpResult(status_code=0, error="timeout")
        assert result.status_code == 0
        assert result.body is None
        assert result.error == "timeout"

    def test_frozen(self) -> None:
        result = HttpResult(status_code=200)
        with pytest.raises(AttributeError):
            result.status_code = 500  # type: ignore[misc]
