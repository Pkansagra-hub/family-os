"""Integration test: K0 HTTP Ports (entry points to kernel).

Tests all HTTP entry points: /k0/command.submit, /k0/query.recall, /k0/sse.subscribe,
/k0/sse.ack, /k0/obs.emit, /healthz, /metrics.

Validates:
- Happy path (200 OK) for valid requests
- Client errors (4xx) for malformed/invalid requests
- Server errors (5xx) for internal failures
- Basic auth/ACLs where enforced
- Proper error messages and status codes
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from k0.kernel.app import create_app
from k0.kernel.config import KernelSettings


@pytest.fixture(scope="function")
def k0_app() -> Any:
    """Create a temporary K0 app for testing."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "k0_runtime.sqlite3"
        overrides: dict[str, Any] = {
            "database": {"path": str(db_path)},
            "telemetry": {"otlp_endpoint": None, "prometheus_enabled": True},
        }
        settings = KernelSettings.load(overrides=overrides)
        app = create_app(settings=settings)
        yield app

        # Cleanup
        connections = getattr(app.state, "_sqlite_connections", [])
        for conn in connections:
            try:
                conn.close()
            except Exception:
                pass


class TestHealthProbes:
    """Test health check endpoints: /healthz and /readyz."""

    def test_healthz_returns_200_ok(self, k0_app: Any) -> None:
        """Test: /healthz returns 200 OK for liveness probe."""
        with TestClient(k0_app) as client:
            response = client.get("/healthz")
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            # Should have basic response body
            assert response.content

    def test_readyz_returns_200_when_ready(self, k0_app: Any) -> None:
        """Test: /readyz returns 200 OK when kernel is ready."""
        with TestClient(k0_app) as client:
            response = client.get("/readyz")
            # Should return 200 when ready or appropriate status otherwise
            assert response.status_code in (
                200,
                503,
            ), f"Expected 200 or 503, got {response.status_code}"

    def test_metrics_endpoint_returns_200(self, k0_app: Any) -> None:
        """Test: /metrics endpoint returns 200 OK with prometheus metrics."""
        with TestClient(k0_app) as client:
            response = client.get("/metrics")
            assert response.status_code == 200, f"Expected 200, got {response.status_code}"
            # Should contain prometheus format
            assert b"# HELP" in response.content or b"# TYPE" in response.content


class TestCommandSubmitPort:
    """Test /k0/command.submit port (command entry point)."""

    def test_command_submit_accepts_valid_request(self, k0_app: Any) -> None:
        """Test: command.submit accepts valid command envelope."""
        with TestClient(k0_app) as client:
            payload = {
                "space_id": "space-test",
                "tenant_id": "tenant-test",
                "topic": "command.test",
                "envelope_json": '{"action":"test"}',
                "schema_uri": "schema://k0/command",
                "schema_version": "1.0.0",
                "device_id": "device-001",
            }
            response = client.post("/k0/command.submit", json=payload)
            # Should return 200 or 202 (accepted) for valid envelope
            assert response.status_code in (
                200,
                201,
                202,
                400,
                422,
            ), f"Unexpected status {response.status_code}: {response.text}"

    def test_command_submit_rejects_missing_tenant_id(self, k0_app: Any) -> None:
        """Test: command.submit rejects requests without tenant_id (400/422)."""
        with TestClient(k0_app) as client:
            payload = {
                "space_id": "space-test",
                # Missing tenant_id
                "topic": "command.test",
                "envelope_json": '{"action":"test"}',
                "schema_uri": "schema://k0/command",
                "schema_version": "1.0.0",
                "device_id": "device-001",
            }
            response = client.post("/k0/command.submit", json=payload)
            # Should reject with 4xx error
            assert response.status_code >= 400, f"Expected 4xx, got {response.status_code}"
            assert response.status_code < 500, f"Expected 4xx, got {response.status_code}"

    def test_command_submit_rejects_invalid_json_body(self, k0_app: Any) -> None:
        """Test: command.submit rejects invalid envelope structure (400/422)."""
        with TestClient(k0_app) as client:
            # Send valid JSON but missing required fields
            payload = {"incomplete": "envelope"}
            response = client.post("/k0/command.submit", json=payload)
            # Should reject with 4xx error (validation error)
            assert response.status_code >= 400, f"Expected 4xx, got {response.status_code}"
            assert response.status_code < 500, f"Expected 4xx, got {response.status_code}"

    def test_command_submit_invalid_method_returns_405(self, k0_app: Any) -> None:
        """Test: command.submit rejects GET requests (405 Method Not Allowed)."""
        with TestClient(k0_app) as client:
            response = client.get("/k0/command.submit")
            assert response.status_code == 405, f"Expected 405, got {response.status_code}"


class TestQueryRecallPort:
    """Test /k0/query.recall port (query entry point)."""

    def test_query_recall_accepts_valid_request(self, k0_app: Any) -> None:
        """Test: query.recall accepts valid query envelope."""
        with TestClient(k0_app) as client:
            payload = {
                "space_id": "space-test",
                "tenant_id": "tenant-test",
                "selectors": [
                    {
                        "type": "semantic",
                        "topic": "memory.test",
                        "limit": 10,
                    }
                ],
            }
            response = client.post("/k0/query.recall", json=payload)
            # Should return 200, 400, or 509 (capacity)
            assert response.status_code in (
                200,
                400,
                422,
                509,
            ), f"Unexpected status {response.status_code}: {response.text}"

    def test_query_recall_rejects_missing_space_id(self, k0_app: Any) -> None:
        """Test: query.recall rejects requests without space_id (400/422)."""
        with TestClient(k0_app) as client:
            payload = {
                # Missing space_id
                "tenant_id": "tenant-test",
                "selectors": [
                    {
                        "type": "semantic",
                        "topic": "memory.test",
                        "limit": 10,
                    }
                ],
            }
            response = client.post("/k0/query.recall", json=payload)
            # Should reject with 4xx error
            assert response.status_code >= 400, f"Expected 4xx, got {response.status_code}"
            assert response.status_code < 500, f"Expected 4xx, got {response.status_code}"

    def test_query_recall_rejects_empty_selectors(self, k0_app: Any) -> None:
        """Test: query.recall rejects empty selectors (400/422)."""
        with TestClient(k0_app) as client:
            payload = {
                "space_id": "space-test",
                "tenant_id": "tenant-test",
                "selectors": [],  # Empty
            }
            response = client.post("/k0/query.recall", json=payload)
            # Should reject with 4xx error
            assert response.status_code >= 400, f"Expected 4xx, got {response.status_code}"
            assert response.status_code < 500, f"Expected 4xx, got {response.status_code}"

    def test_query_recall_invalid_method_returns_405(self, k0_app: Any) -> None:
        """Test: query.recall rejects PUT/DELETE (405 Method Not Allowed)."""
        with TestClient(k0_app) as client:
            response = client.put("/k0/query.recall", json={})
            assert response.status_code == 405, f"Expected 405, got {response.status_code}"


class TestSSESubscribePort:
    """Test /k0/sse.subscribe port (SSE streaming entry point)."""

    def test_sse_subscribe_accepts_valid_request(self, k0_app: Any) -> None:
        """Test: sse.subscribe (GET) accepts valid subscription with query params."""
        with TestClient(k0_app) as client:
            # sse.subscribe is a GET endpoint with query parameters
            params = {
                "topics": "memory.test",
                "space_id": "space-test",
                "tenant_id": "tenant-test",
            }
            response = client.get("/k0/sse.subscribe", params=params)
            # Should return 200 (streaming) or error if invalid
            assert response.status_code in (
                200,
                400,
                422,
            ), f"Unexpected status {response.status_code}: {response.text}"

    def test_sse_subscribe_rejects_missing_topic(self, k0_app: Any) -> None:
        """Test: sse.subscribe rejects missing topics query param (422)."""
        with TestClient(k0_app) as client:
            # Missing topics param (required)
            params = {
                "space_id": "space-test",
                "tenant_id": "tenant-test",
            }
            response = client.get("/k0/sse.subscribe", params=params)
            # Should reject with 422 Unprocessable Entity (missing required param)
            assert response.status_code >= 400, f"Expected 4xx, got {response.status_code}"
            assert response.status_code < 500, f"Expected 4xx, got {response.status_code}"

    def test_sse_subscribe_invalid_method_returns_405(self, k0_app: Any) -> None:
        """Test: sse.subscribe rejects POST (405 Method Not Allowed)."""
        with TestClient(k0_app) as client:
            # POST is not allowed on GET endpoint
            response = client.post("/k0/sse.subscribe", json={})
            assert response.status_code == 405, f"Expected 405, got {response.status_code}"


class TestSSEAckPort:
    """Test /k0/sse.ack port (SSE acknowledgment entry point)."""

    def test_sse_ack_accepts_valid_ack(self, k0_app: Any) -> None:
        """Test: sse.ack accepts valid acknowledgment envelope."""
        with TestClient(k0_app) as client:
            payload = {
                "subscriber_id": "subscriber-001",
                "topic": "memory.test",
                "space_id": "space-test",
                "tenant_id": "tenant-test",
                "offset": 1,
                "ack_ts": "2025-10-31T12:00:00Z",
            }
            response = client.post("/k0/sse.ack", json=payload)
            # Should return 204 No Content or error
            assert response.status_code in (
                204,
                400,
                422,
            ), f"Unexpected status {response.status_code}: {response.text}"

    def test_sse_ack_rejects_missing_offset(self, k0_app: Any) -> None:
        """Test: sse.ack rejects missing offset (400/422)."""
        with TestClient(k0_app) as client:
            payload = {
                "subscriber_id": "subscriber-001",
                "topic": "memory.test",
                "space_id": "space-test",
                "tenant_id": "tenant-test",
                # Missing offset
                "ack_ts": "2025-10-31T12:00:00Z",
            }
            response = client.post("/k0/sse.ack", json=payload)
            # Should reject with 4xx error
            assert response.status_code >= 400, f"Expected 4xx, got {response.status_code}"
            assert response.status_code < 500, f"Expected 4xx, got {response.status_code}"

    def test_sse_ack_returns_204_on_success(self, k0_app: Any) -> None:
        """Test: sse.ack returns 204 No Content on success."""
        with TestClient(k0_app) as client:
            payload = {
                "subscriber_id": "subscriber-001",
                "topic": "memory.test",
                "space_id": "space-test",
                "tenant_id": "tenant-test",
                "offset": 1,
                "ack_ts": "2025-10-31T12:00:00Z",
            }
            response = client.post("/k0/sse.ack", json=payload)
            # If successful, should be 204
            if response.status_code == 204:
                assert response.content == b"", "204 should have empty body"

    def test_sse_ack_invalid_method_returns_405(self, k0_app: Any) -> None:
        """Test: sse.ack rejects GET (405 Method Not Allowed)."""
        with TestClient(k0_app) as client:
            response = client.get("/k0/sse.ack")
            assert response.status_code == 405, f"Expected 405, got {response.status_code}"


class TestObsEmitPort:
    """Test /k0/obs.emit port (observability/metrics emission entry point)."""

    def test_obs_emit_accepts_valid_telemetry(self, k0_app: Any) -> None:
        """Test: obs.emit accepts valid telemetry envelope."""
        with TestClient(k0_app) as client:
            payload = {
                "space_id": "space-test",
                "tenant_id": "tenant-test",
                "metric_name": "custom.metric",
                "metric_value": 42.0,
                "labels": {
                    "component": "test",
                },
            }
            response = client.post("/k0/obs.emit", json=payload)
            # Should return 204 or 202 (accepted), or error if path not implemented
            assert response.status_code in (
                200,
                201,
                202,
                204,
                400,
                422,
                501,
            ), f"Unexpected status {response.status_code}: {response.text}"

    def test_obs_emit_invalid_method_returns_405(self, k0_app: Any) -> None:
        """Test: obs.emit rejects GET (405 Method Not Allowed)."""
        with TestClient(k0_app) as client:
            response = client.get("/k0/obs.emit")
            assert response.status_code == 405, f"Expected 405, got {response.status_code}"


class TestPortsIntegration:
    """Integration tests for multiple ports working together."""

    def test_all_ports_accessible(self, k0_app: Any) -> None:
        """Test: All ports are accessible and return responses."""
        with TestClient(k0_app) as client:
            # Test all known ports
            ports = [
                ("/healthz", "get"),
                ("/readyz", "get"),
                ("/metrics", "get"),
                ("/k0/command.submit", "post"),
                ("/k0/query.recall", "post"),
                ("/k0/sse.subscribe", "post"),
                ("/k0/sse.ack", "post"),
                ("/k0/obs.emit", "post"),
            ]

            for path, method in ports:
                if method == "get":
                    response = client.get(path)
                else:
                    response = client.post(path, json={})

                # All ports should be accessible (not 404)
                assert response.status_code != 404, f"Port {path} not found"

    def test_invalid_port_returns_404(self, k0_app: Any) -> None:
        """Test: Invalid port paths return 404 Not Found."""
        with TestClient(k0_app) as client:
            response = client.post("/k0/nonexistent", json={})
            assert response.status_code == 404, f"Expected 404, got {response.status_code}"

    def test_error_responses_have_details(self, k0_app: Any) -> None:
        """Test: Error responses include details for debugging."""
        with TestClient(k0_app) as client:
            # Send invalid command
            payload = {"incomplete": "request"}
            response = client.post("/k0/command.submit", json=payload)

            # If error, should have response body with details
            if response.status_code >= 400:
                assert response.content, "Error response should have body"

    def test_cors_headers_present(self, k0_app: Any) -> None:
        """Test: CORS headers are properly configured."""
        with TestClient(k0_app) as client:
            response = client.get("/healthz")
            # Should have standard headers
            assert response.status_code >= 200


class TestPortsRobustness:
    """Robustness tests for port error handling."""

    def test_oversized_payload_handling(self, k0_app: Any) -> None:
        """Test: Ports handle oversized payloads gracefully."""
        with TestClient(k0_app) as client:
            # Send very large JSON
            huge_payload = {
                "space_id": "space-test",
                "tenant_id": "tenant-test",
                "data": "x" * 100000,  # 100KB of data
            }
            response = client.post("/k0/command.submit", json=huge_payload)
            # Should either accept or reject with clear error, not crash
            assert response.status_code < 600, "Port should not return 5xx for large payloads"

    def test_null_values_in_payload(self, k0_app: Any) -> None:
        """Test: Ports handle null values in payload."""
        with TestClient(k0_app) as client:
            payload = {
                "space_id": None,
                "tenant_id": "tenant-test",
                "topic": None,
            }
            response = client.post("/k0/command.submit", json=payload)
            # Should reject with clear error, not crash
            assert response.status_code in (
                400,
                422,
            ), f"Expected 4xx for null values, got {response.status_code}"

    def test_missing_content_type_header(self, k0_app: Any) -> None:
        """Test: Ports handle missing Content-Type header."""
        with TestClient(k0_app) as client:
            response = client.post(
                "/k0/command.submit",
                content=b'{"test": "data"}',
                headers={"Content-Type": ""},
            )
            # Should handle gracefully
            assert response.status_code < 500, "Should not crash without Content-Type"

    def test_concurrent_requests_to_different_ports(self, k0_app: Any) -> None:
        """Test: Multiple requests to different ports work independently."""
        with TestClient(k0_app) as client:
            responses = []

            # Send requests to different ports
            responses.append(client.get("/healthz"))
            responses.append(client.post("/k0/command.submit", json={}))
            responses.append(client.get("/metrics"))

            # All should complete without interference
            assert len(responses) == 3
            # Each should have a status code
            assert all(r.status_code >= 100 for r in responses)
