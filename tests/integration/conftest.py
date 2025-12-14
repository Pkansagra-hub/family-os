"""
Pytest configuration for integration tests.

Exposes fixtures for test discovery.
"""

import pytest

from tests.integration.fixtures.p02_fixtures import (
    SAMPLE_ENVELOPES,
    assert_embedding_job_created,
    assert_exit_events_emitted,
    assert_row_in_hipp_events,
    create_enriched_envelope,
    create_minimal_envelope,
    mock_context,
    mock_syscalls,
)


@pytest.fixture
def test_client():
    """
    HTTP client for command port integration tests.

    Uses requests library to hit real K0 service (Docker or local).
    """
    import requests

    class HTTPClient:
        """Minimal client matching TestClient interface"""

        def __init__(self, base_url="http://localhost:8080"):
            self.base_url = base_url

        def post(self, path, json=None, content=None, headers=None):
            url = self.base_url + path
            if content is not None:
                return requests.post(url, data=content, headers=headers or {})
            return requests.post(url, json=json, headers=headers or {})

    # Check if K0 is running
    try:
        import requests

        requests.get("http://localhost:8080/health", timeout=1)
        return HTTPClient()
    except Exception:
        pytest.skip("K0 service not running on localhost:8080")


__all__ = [
    "mock_context",
    "mock_syscalls",
    "SAMPLE_ENVELOPES",
    "create_minimal_envelope",
    "create_enriched_envelope",
    "assert_row_in_hipp_events",
    "assert_exit_events_emitted",
    "assert_embedding_job_created",
]
