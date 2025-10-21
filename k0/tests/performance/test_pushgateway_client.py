"""Ward tests for PushgatewayClient implementation."""

from unittest.mock import Mock, patch

import httpx
from ward import raises, test

from k0.perf.runner import PushgatewayClient


@test("PushgatewayClient initializes with endpoint and job name")
def test_client_initialization():
    """Verify client initialization with default and custom job names."""
    client = PushgatewayClient("http://localhost:9091")
    assert client.endpoint == "http://localhost:9091"
    assert client.job_name == "k0-perf"

    custom_client = PushgatewayClient("http://pushgateway:9091/", "custom-job")
    assert custom_client.endpoint == "http://pushgateway:9091"
    assert custom_client.job_name == "custom-job"


@test("_build_push_url constructs correct URL without labels")
def test_build_url_no_labels():
    """Verify URL construction with job name only."""
    client = PushgatewayClient("http://localhost:9091", "test-job")
    url = client._build_push_url()
    assert url == "http://localhost:9091/metrics/job/test-job"


@test("_build_push_url constructs correct URL with single label")
def test_build_url_single_label():
    """Verify URL construction with one label."""
    client = PushgatewayClient("http://localhost:9091", "test-job")
    url = client._build_push_url({"scenario": "burst"})
    assert url == "http://localhost:9091/metrics/job/test-job/scenario/burst"


@test("_build_push_url constructs correct URL with multiple labels")
def test_build_url_multiple_labels():
    """Verify URL construction with multiple labels in sorted order."""
    client = PushgatewayClient("http://localhost:9091", "test-job")
    url = client._build_push_url(
        {"git_sha": "abc123", "scenario": "fanout", "environment": "ci"}
    )
    # Labels should be sorted alphabetically
    expected = (
        "http://localhost:9091/metrics/job/test-job"
        "/environment/ci/git_sha/abc123/scenario/fanout"
    )
    assert url == expected


@test("_build_push_url URL-encodes label values with special characters")
def test_build_url_encodes_special_chars():
    """Verify URL encoding for label values with spaces and special chars."""
    client = PushgatewayClient("http://localhost:9091", "test-job")
    url = client._build_push_url({"branch": "feature/new-api", "user": "john doe"})
    # Slashes and spaces should be URL-encoded
    assert "feature%2Fnew-api" in url
    assert "john%20doe" in url


@test("_format_metrics formats simple metrics correctly")
def test_format_simple_metrics():
    """Verify Prometheus text format for simple metrics."""
    client = PushgatewayClient("http://localhost:9091")
    formatted = client._format_metrics(
        {"p99_latency_ms": 123.45, "success_rate": 0.998, "total_requests": 1000.0}
    )

    lines = formatted.strip().split("\n")
    assert len(lines) == 3
    assert "p99_latency_ms 123.45" in lines
    assert "success_rate 0.998" in lines
    assert "total_requests 1000.0" in lines


@test("_format_metrics handles NaN values correctly")
def test_format_metrics_nan():
    """Verify NaN values are formatted as 'NaN' per Prometheus spec."""
    client = PushgatewayClient("http://localhost:9091")
    formatted = client._format_metrics({"nan_metric": float("nan")})
    assert "nan_metric NaN\n" == formatted


@test("_format_metrics handles positive infinity correctly")
def test_format_metrics_positive_inf():
    """Verify positive infinity is formatted as '+Inf'."""
    client = PushgatewayClient("http://localhost:9091")
    formatted = client._format_metrics({"inf_metric": float("inf")})
    assert "inf_metric +Inf\n" == formatted


@test("_format_metrics handles negative infinity correctly")
def test_format_metrics_negative_inf():
    """Verify negative infinity is formatted as '-Inf'."""
    client = PushgatewayClient("http://localhost:9091")
    formatted = client._format_metrics({"neg_inf_metric": float("-inf")})
    assert "neg_inf_metric -Inf\n" == formatted


@test("_format_metrics accepts metric names with underscores and colons")
def test_format_metrics_valid_names():
    """Verify metric names with underscores and colons are accepted."""
    client = PushgatewayClient("http://localhost:9091")
    formatted = client._format_metrics(
        {"http_requests_total": 100.0, "process:cpu:seconds": 5.5}
    )
    assert "http_requests_total 100.0" in formatted
    assert "process:cpu:seconds 5.5" in formatted


@test("_format_metrics rejects invalid metric names")
def test_format_metrics_invalid_names():
    """Verify metric names with invalid characters raise ValueError."""
    client = PushgatewayClient("http://localhost:9091")

    with raises(ValueError) as exc_info:
        client._format_metrics({"invalid-metric-name": 10.0})

    assert "Invalid metric name" in str(exc_info.raised)


@test("push_metrics sends POST request with correct headers")
def test_push_metrics_http_post():
    """Verify push_metrics sends HTTP POST with Prometheus format."""
    client = PushgatewayClient("http://localhost:9091", "test-job")
    metrics = {"test_metric": 42.0}

    mock_response = Mock()
    mock_response.raise_for_status = Mock()

    with patch("httpx.Client") as mock_client_cls:
        mock_client_instance = Mock()
        mock_client_cls.return_value.__enter__.return_value = mock_client_instance
        mock_client_instance.post.return_value = mock_response

        client.push_metrics(metrics)

        # Verify POST was called with correct URL and headers
        mock_client_instance.post.assert_called_once()
        call_args = mock_client_instance.post.call_args

        assert call_args[0][0] == "http://localhost:9091/metrics/job/test-job"
        assert call_args[1]["content"] == "test_metric 42.0\n"
        assert call_args[1]["headers"]["Content-Type"] == "text/plain; charset=utf-8"


@test("push_metrics includes labels in URL")
def test_push_metrics_with_labels():
    """Verify push_metrics includes labels in push URL."""
    client = PushgatewayClient("http://localhost:9091", "test-job")
    metrics = {"latency": 100.0}
    labels = {"scenario": "burst", "env": "ci"}

    mock_response = Mock()
    mock_response.raise_for_status = Mock()

    with patch("httpx.Client") as mock_client_cls:
        mock_client_instance = Mock()
        mock_client_cls.return_value.__enter__.return_value = mock_client_instance
        mock_client_instance.post.return_value = mock_response

        client.push_metrics(metrics, labels)

        # Verify URL includes labels
        call_args = mock_client_instance.post.call_args
        url = call_args[0][0]
        assert "/env/ci" in url
        assert "/scenario/burst" in url


@test("push_metrics raises HTTPError on request failure")
def test_push_metrics_http_error():
    """Verify push_metrics raises HTTPError when POST fails."""
    client = PushgatewayClient("http://localhost:9091")
    metrics = {"test_metric": 42.0}

    with patch("httpx.Client") as mock_client_cls:
        mock_client_instance = Mock()
        mock_client_cls.return_value.__enter__.return_value = mock_client_instance
        mock_client_instance.post.side_effect = httpx.ConnectError("Connection refused")

        with raises(httpx.HTTPError) as exc_info:
            client.push_metrics(metrics)

        assert "Failed to push metrics" in str(exc_info.raised)


@test("push_metrics uses 10 second timeout")
def test_push_metrics_timeout():
    """Verify push_metrics configures 10 second timeout."""
    client = PushgatewayClient("http://localhost:9091")
    metrics = {"test_metric": 42.0}

    mock_response = Mock()
    mock_response.raise_for_status = Mock()

    with patch("httpx.Client") as mock_client_cls:
        mock_client_instance = Mock()
        mock_client_cls.return_value.__enter__.return_value = mock_client_instance
        mock_client_instance.post.return_value = mock_response

        client.push_metrics(metrics)

        # Verify Client was created with timeout=10.0
        mock_client_cls.assert_called_once_with(timeout=10.0)


@test("delete_metrics sends DELETE request to correct URL")
def test_delete_metrics_http_delete():
    """Verify delete_metrics sends HTTP DELETE to Pushgateway."""
    client = PushgatewayClient("http://localhost:9091", "test-job")

    mock_response = Mock()
    mock_response.raise_for_status = Mock()

    with patch("httpx.Client") as mock_client_cls:
        mock_client_instance = Mock()
        mock_client_cls.return_value.__enter__.return_value = mock_client_instance
        mock_client_instance.delete.return_value = mock_response

        client.delete_metrics()

        # Verify DELETE was called with correct URL
        mock_client_instance.delete.assert_called_once_with(
            "http://localhost:9091/metrics/job/test-job"
        )


@test("delete_metrics includes labels in URL")
def test_delete_metrics_with_labels():
    """Verify delete_metrics includes labels in deletion URL."""
    client = PushgatewayClient("http://localhost:9091", "test-job")
    labels = {"scenario": "burst"}

    mock_response = Mock()
    mock_response.raise_for_status = Mock()

    with patch("httpx.Client") as mock_client_cls:
        mock_client_instance = Mock()
        mock_client_cls.return_value.__enter__.return_value = mock_client_instance
        mock_client_instance.delete.return_value = mock_response

        client.delete_metrics(labels)

        # Verify URL includes labels
        call_args = mock_client_instance.delete.call_args
        url = call_args[0][0]
        assert "/scenario/burst" in url


@test("delete_metrics raises HTTPError on request failure")
def test_delete_metrics_http_error():
    """Verify delete_metrics raises HTTPError when DELETE fails."""
    client = PushgatewayClient("http://localhost:9091")

    with patch("httpx.Client") as mock_client_cls:
        mock_client_instance = Mock()
        mock_client_cls.return_value.__enter__.return_value = mock_client_instance
        mock_client_instance.delete.side_effect = httpx.TimeoutException(
            "Request timeout"
        )

        with raises(httpx.HTTPError) as exc_info:
            client.delete_metrics()

        assert "Failed to delete metrics" in str(exc_info.raised)


@test("delete_metrics uses 10 second timeout")
def test_delete_metrics_timeout():
    """Verify delete_metrics configures 10 second timeout."""
    client = PushgatewayClient("http://localhost:9091")

    mock_response = Mock()
    mock_response.raise_for_status = Mock()

    with patch("httpx.Client") as mock_client_cls:
        mock_client_instance = Mock()
        mock_client_cls.return_value.__enter__.return_value = mock_client_instance
        mock_client_instance.delete.return_value = mock_response

        client.delete_metrics()

        # Verify Client was created with timeout=10.0
        mock_client_cls.assert_called_once_with(timeout=10.0)
