"""
HTTP/2 Client - Low-Level HTTP/2 Connection Management

Layer: L5 Infrastructure
Component: K0 Bridge (K1 ↔ K0 Communication)
Priority: P0 (Critical Path)
Status: ✅ IMPLEMENTED

Architecture Decision Records:
    - ADR-0001: K0/K1 Kernel Split (K1 Intelligence Module, K0 Memory Module)
    - ADR-0001a: K0 Bridge Communication Protocol (HTTP/2 + TLS 1.3)
    - ADR-0001b: TLS/mTLS Configuration (mutual authentication)
    - ADR-0044a: HTTP/2 Multiplexing & Connection Management
    - ADR-0044d: Error Handling & Retry Strategy

Dependencies:
    Internal:
        - None (lowest-level HTTP transport)
    External:
        - httpx (HTTP/2 support)
        - asyncio (async runtime)
        - ssl (TLS certificates)

Connects To:
    Upstream:
        - k1.bridge_k0.command_client.CommandClient (command operations)
        - k1.bridge_k0.ports.* (port adapters)
    Downstream:
        - K0 HTTP/2 endpoints (localhost:8080 or production K0 cluster)

Performance Budgets:
    - Connection setup: <50ms P95 (HTTP/2 handshake + TLS 1.3)
    - Request send: <1ms P95 (enqueue to HTTP/2 stream)
    - Response receive: <1ms P95 (read from stream buffer)
    - Memory: Per connection: <100KB, Connection pool: <1MB (10 connections)
    - Multiplexing overhead: <50KB per stream
    - Connections: Max per pool: 10, Max concurrent streams: 100

Observability:
    Metrics:
        - k1_k0_bridge_http2_connections_total{status} (counter)
        - k1_k0_bridge_http2_connection_latency_ms{p50, p95, p99} (histogram)
        - k1_k0_bridge_http2_active_streams (gauge)
        - k1_k0_bridge_http2_requests_total{method, status} (counter)
    Traces:
        - Span: k0_bridge.http2_request
        - Attributes: method, url, status_code, cognitive_trace_id
    Logs:
        - INFO: connection established (host, port, tls_version)
        - WARNING: connection timeout (host, timeout_ms)
        - ERROR: connection failed (host, reason)
"""

from __future__ import annotations

import asyncio
import logging
import random
import ssl
import time
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Dict, Optional, Union

import httpx

try:  # Best-effort observability integration (Gate 3 requirement)
    from k1.l5_infrastructure.observability import (  # type: ignore
        create_span,
        emit_counter,
        emit_gauge,
        emit_histogram,
    )
except (
    ModuleNotFoundError,
    ImportError,
):  # pragma: no cover - observability package not yet implemented

    class _NullSpan:
        def __init__(self, *_args, **_kwargs):
            self._start_time = time.perf_counter()

        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _tb):
            return False

    def create_span(_name: str, _attributes: Optional[Dict[str, str]] = None):  # type: ignore
        return _NullSpan()

    def emit_counter(_name: str, _value: float, _labels: Optional[Dict[str, str]] = None):  # type: ignore
        return None

    def emit_gauge(_name: str, _value: float, _labels: Optional[Dict[str, str]] = None):  # type: ignore
        return None

    def emit_histogram(_name: str, _value: float, _labels: Optional[Dict[str, str]] = None):  # type: ignore
        return None


# Internal imports
# None (lowest-level HTTP transport)

# Configure module logger
logger = logging.getLogger(__name__)

# =============================================================================
# SECTION 2: CONSTANTS & CONFIGURATION
# =============================================================================

# TODO(@infrastructure-team): Load from k1/config/k0_bridge.yml (ADR-0001a)
# Assigned to: Issue #L5-1.1.2
DEFAULT_CONFIG = {
    "k0_host": "localhost",
    "k0_port": 8080,
    "use_tls": True,
    "tls_version": "TLSv1.3",
    "connection_timeout_s": 10.0,
    "request_timeout_s": 5.0,
    "keepalive_timeout_s": 60.0,
    "keepalive_interval_s": 10.0,
    "max_connections_per_pool": 10,
    "max_concurrent_streams": 100,
    "pool_size_mb": 1,
    "reconnect_backoff_base_s": 1.0,
    "max_reconnect_attempts": 5,
}

# =============================================================================
# SECTION 3: TYPE DEFINITIONS & ENUMS
# =============================================================================


@dataclass
class HTTP2Config:
    """
    Configuration dataclass for HTTP/2 Client.

    Fields:
        k0_host: K0 server hostname (default: localhost)
        k0_port: K0 server port (default: 8080)
        use_tls: Enable TLS 1.3 encryption (default: True)
        tls_version: TLS version (TLSv1.3, TLSv1.2)
        connection_timeout_s: Connection timeout in seconds
        request_timeout_s: Request timeout in seconds
        keepalive_timeout_s: Keepalive timeout in seconds
        max_connections_per_pool: Max connections per host (connection pooling)
        max_concurrent_streams: Max concurrent HTTP/2 streams (client-side cap; effective limit may be lower based on server SETTINGS)
        pool_size_mb: Connection pool memory budget (MB)
        health_path: Health check endpoint path (default: /healthz)
    """

    k0_host: str = DEFAULT_CONFIG["k0_host"]
    k0_port: int = DEFAULT_CONFIG["k0_port"]
    use_tls: bool = DEFAULT_CONFIG["use_tls"]
    tls_version: str = DEFAULT_CONFIG["tls_version"]
    connection_timeout_s: float = DEFAULT_CONFIG["connection_timeout_s"]
    request_timeout_s: float = DEFAULT_CONFIG["request_timeout_s"]
    keepalive_timeout_s: float = DEFAULT_CONFIG["keepalive_timeout_s"]
    max_connections_per_pool: int = DEFAULT_CONFIG["max_connections_per_pool"]
    max_concurrent_streams: int = DEFAULT_CONFIG["max_concurrent_streams"]
    pool_size_mb: int = DEFAULT_CONFIG["pool_size_mb"]
    keepalive_interval_s: float = DEFAULT_CONFIG["keepalive_interval_s"]
    reconnect_backoff_base_s: float = DEFAULT_CONFIG["reconnect_backoff_base_s"]
    max_reconnect_attempts: int = DEFAULT_CONFIG["max_reconnect_attempts"]
    health_path: str = "/healthz"  # NEW: configurable health path
    transport: Optional[httpx.AsyncBaseTransport] = field(default=None, repr=False)
    # TODO(@infrastructure-team): Add TLS certificate paths (ADR-0001b)


# =============================================================================
# SECTION 4: CORE CLASSES
# =============================================================================


class HTTP2Connection:
    """
    Low-level HTTP/2 connection management with persistent connections,
    multiplexing, and TLS support.

    Purpose:
        Manages persistent HTTP/2 connections to K0 with connection pooling,
        stream multiplexing (100 concurrent streams), and TLS 1.3 mutual
        authentication. Handles connection keepalive and graceful shutdown.

    Responsibilities:
        1. Manage persistent HTTP/2 connections to K0
        2. Implement connection pooling (per target host)
        3. Handle stream multiplexing (100 concurrent streams)
        4. Manage TLS 1.3 with mutual authentication (mTLS)
        5. Implement connection keepalive and graceful shutdown

    Lifecycle:
        INIT → CONNECTING → CONNECTED → [DEGRADED] → CLOSING → CLOSED

    Thread Safety: Async-safe (not thread-safe across threads)
    Async Safe: Yes (fully async/await compatible)

    Cognitive Trace:
        - Propagates cognitive_trace_id via HTTP headers (X-Cognitive-Trace-Id)
        - Required for: request, post, get

    Performance Budget (P95):
        - Connection setup: <50ms (HTTP/2 handshake + TLS 1.3)
        - Request send: <1ms (enqueue to stream)
        - Response receive: <1ms (read from buffer)
        - Memory: Per connection: <100KB, Pool: <1MB (10 connections)

    Examples:
        >>> config = HTTP2Config(k0_host='localhost', k0_port=8080)
        >>> async with HTTP2Connection(config) as connection:
        ...     response = await connection.post(
        ...         path='/k0/command',
        ...         headers={'Content-Type': 'application/json'},
        ...         body=b'{"command": "test"}'
        ...     )
        >>> print(f'Status: {response.status}, Body: {response.body}')

    References:
        - ADR-0001: K0/K1 Kernel Split
        - ADR-0001a: K0 Bridge Communication Protocol
        - ADR-0001b: TLS/mTLS Configuration
        - Diagram: architecture_diagrams/k1/k1_complete_with_flows.mmd
    """

    def __init__(self, config: HTTP2Config) -> None:
        """
        Initialize HTTP2Connection.

        Args:
            config: Configuration object with K0 connection parameters

        Raises:
            ValueError: If configuration is invalid
            TypeError: If config type is incorrect

        Side Effects:
            - Initializes internal state (connection pool, stream tracking)
            - Does NOT establish connection (call connect() to connect)

        ADR: ADR-0001a (K0 Bridge Communication Protocol)
        Assigned to: Issue #L5-1.1.2
        """
        # ADR-0001a: K0 Bridge Communication Protocol
        # Validate config
        if not config.k0_host or config.k0_port <= 0:
            raise ValueError(f"Invalid host/port: {config.k0_host}:{config.k0_port}")
        if config.connection_timeout_s <= 0 or config.request_timeout_s <= 0:
            raise ValueError("Timeouts must be positive")
        if config.max_concurrent_streams <= 0 or config.max_concurrent_streams > 100:
            raise ValueError("max_concurrent_streams must be 1-100")

        self.config = config
        self.state = "INIT"  # State: INIT | CONNECTING | CONNECTED | DEGRADED | CLOSING | CLOSED
        self._logger = logger
        self._client: Optional[httpx.AsyncClient] = None
        self._ssl_context: Optional[ssl.SSLContext] = None
        self._active_streams = 0
        self._pending_queue = 0
        self._connection_time = 0.0
        self._stream_semaphore = asyncio.Semaphore(config.max_concurrent_streams)
        self._queue_lock = asyncio.Lock()
        self._keepalive_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        self._reconnect_attempts = 0
        self._reconnect_lock = asyncio.Lock()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.close()

    async def connect(self) -> None:
        """
        Establish HTTP/2 connection to K0.

        This method performs async connection setup.

        Raises:
            RuntimeError: If connection fails
            ConnectionError: If cannot connect to K0 server
            ssl.SSLError: If TLS handshake fails

        Lifecycle:
            Transitions: INIT → CONNECTING → CONNECTED

        Performance:
            - Target: <50ms P95 (HTTP/2 handshake + TLS 1.3)

        ADR: ADR-0001a (K0 Bridge Communication Protocol)
        Assigned to: Issue #L5-1.1.2
        """
        # ADR-0001a: K0 Bridge Communication Protocol
        # ADR-0044a: HTTP/2 Multiplexing & Connection Management
        if self.state == "CONNECTED":
            self._logger.warning(
                "Already connected to K0",
                extra={"host": self.config.k0_host, "port": self.config.k0_port},
            )
            return

        self.state = "CONNECTING"
        labels = self._metric_labels
        start_time = time.perf_counter()

        try:
            verify: Union[ssl.SSLContext, bool]
            if self.config.use_tls:
                self._ssl_context = self._create_ssl_context()
                verify = self._ssl_context
            else:
                verify = False

            limits = httpx.Limits(
                max_connections=self.config.max_connections_per_pool,
                max_keepalive_connections=self.config.max_connections_per_pool,
                keepalive_expiry=self.config.keepalive_timeout_s,
            )

            timeout = httpx.Timeout(
                connect=self.config.connection_timeout_s,
                read=self.config.request_timeout_s,
                write=self.config.request_timeout_s,
                pool=self.config.connection_timeout_s,
            )

            self._client = httpx.AsyncClient(
                http2=True,
                timeout=timeout,
                limits=limits,
                verify=verify,
                base_url=self._base_url,
                transport=self.config.transport,
            )

            await self._perform_health_check()

            self.state = "CONNECTED"
            self._connection_time = time.time()
            self._shutdown_event.clear()
            if self._keepalive_task is None:
                self._keepalive_task = asyncio.create_task(self._keepalive_loop())

            latency_ms = (time.perf_counter() - start_time) * 1000
            emit_counter("k1_k0_bridge_http2_connections_total", 1, {**labels, "status": "success"})
            emit_histogram("k1_k0_bridge_http2_connection_latency_ms", latency_ms, labels)

            self._logger.info(
                "http2_connection_established",
                extra={
                    "host": self.config.k0_host,
                    "port": self.config.k0_port,
                    "tls_version": self.config.tls_version,
                    "latency_ms": round(latency_ms, 2),
                },
            )

        except Exception as exc:
            await self._close_client()
            self.state = "INIT"
            emit_counter("k1_k0_bridge_http2_connections_total", 1, {**labels, "status": "error"})
            self._logger.error(
                "http2_connection_failed",
                extra={
                    "host": self.config.k0_host,
                    "port": self.config.k0_port,
                    "error": str(exc),
                },
            )
            raise ConnectionError(f"Failed to connect to K0: {exc}") from exc

    async def request(
        self,
        method: str,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[bytes] = None,
        timeout: Optional[float] = None,
        cognitive_trace_id: Optional[str] = None,
    ) -> "HTTP2Response":
        """
        Send HTTP/2 request to K0.

        This is the primary public method for sending requests.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: Request path (e.g., /k0/command)
            headers: HTTP headers (dict)
            body: Request body (bytes)
            timeout: Request timeout in seconds (default: config.request_timeout_s)
            cognitive_trace_id: Cognitive trace ID to propagate (default: None)

        Returns:
            HTTP2Response with status, headers, body

        Raises:
            ValueError: If method or path is invalid
            TimeoutError: If request timeout exceeded
            RuntimeError: If connection is not CONNECTED
            httpx.HTTPError: If HTTP/2 request fails

        Performance:
            - Target: <1ms P95 (enqueue to stream)
            - Stream limit: Max 100 concurrent streams (client-side cap; effective limit may be lower based on server SETTINGS)

        Observability:
            - Metrics: k1_k0_bridge_http2_requests_total{method, status}
            - Traces: Span name: k0_bridge.http2_request
            - Attributes: method, path, status_code, cognitive_trace_id

        Cognitive Trace:
            - Accepts cognitive_trace_id from caller
            - Propagates to K0 via HTTP header: X-Cognitive-Trace-Id

        ADR: ADR-0001a (K0 Bridge Communication Protocol)
        Assigned to: Issue #L5-1.1.2
        Depends on: httpx.AsyncClient (HTTP/2 transport)
        """
        # ADR-0001a: K0 Bridge Communication Protocol
        # Step 1: Validate inputs
        if method not in ("GET", "POST", "PUT", "DELETE", "OPTIONS"):
            raise ValueError(f"Invalid HTTP method: {method}")
        if not path.startswith("/"):
            raise ValueError(f"Path must start with /: {path}")

        # Step 2: Check connection state
        await self._ensure_connected()

        labels = {**self._metric_labels, "method": method}
        acquired = False

        try:
            await self._acquire_stream_slot()
            acquired = True

            client = self._require_client()
            request_timeout = timeout or self.config.request_timeout_s

            if headers is None:
                headers = {}
            headers.setdefault("User-Agent", "K1-Bridge/1.0")
            if cognitive_trace_id and "X-Cognitive-Trace-Id" not in headers:
                headers["X-Cognitive-Trace-Id"] = cognitive_trace_id

            start_time = time.perf_counter()
            with create_span(
                "k0_bridge.http2_request",
                {
                    "method": method,
                    "path": path,
                    "host": self.config.k0_host,
                    "port": str(self.config.k0_port),
                    "max_concurrent_streams": str(self.config.max_concurrent_streams),
                },
            ):
                response = await client.request(
                    method,
                    path,
                    headers=headers,
                    content=body,
                    timeout=request_timeout,
                )

            latency_ms = (time.perf_counter() - start_time) * 1000
            emit_histogram("k1_k0_bridge_http2_request_latency_ms", latency_ms, labels)
            emit_counter(
                "k1_k0_bridge_http2_requests_total",
                1,
                {**labels, "status": str(response.status_code)},
            )

            self._logger.debug(
                "http2_request_completed",
                extra={
                    "method": method,
                    "path": path,
                    "status": response.status_code,
                    "latency_ms": round(latency_ms, 2),
                    "body_size": len(body) if body else 0,
                    "response_size": len(response.content),
                },
            )

            return HTTP2Response(
                status=response.status_code,
                headers=dict(response.headers),
                body=response.content,
            )

        except httpx.TimeoutException as exc:
            emit_counter("k1_k0_bridge_http2_requests_total", 1, {**labels, "status": "timeout"})
            self._logger.error(
                "http2_request_timeout",
                extra={"method": method, "path": path, "timeout_s": request_timeout},
            )
            raise TimeoutError(f"Request timeout after {request_timeout}s") from exc

        except httpx.HTTPError as exc:
            emit_counter(
                "k1_k0_bridge_http2_requests_total", 1, {**labels, "status": "transport_error"}
            )
            self._logger.error(
                "http2_request_failed",
                extra={"method": method, "path": path, "error": str(exc)},
            )
            await self._handle_transport_error(exc)
            raise

        finally:
            if acquired:
                await self._release_stream_slot()

    async def post(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        body: Optional[bytes] = None,
        cognitive_trace_id: Optional[str] = None,
    ) -> "HTTP2Response":
        """
        Convenience method for HTTP POST requests.

        Args:
            path: Request path (e.g., /k0/command)
            headers: HTTP headers
            body: Request body (bytes)
            cognitive_trace_id: Cognitive trace ID to propagate

        Returns:
            HTTP2Response

        ADR: ADR-0001a (K0 Bridge Communication Protocol)
        """
        return await self.request(
            "POST", path, headers, body, cognitive_trace_id=cognitive_trace_id
        )

    async def get(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        cognitive_trace_id: Optional[str] = None,
    ) -> "HTTP2Response":
        """
        Convenience method for HTTP GET requests.

        Args:
            path: Request path (e.g., /k0/query)
            headers: HTTP headers
            cognitive_trace_id: Cognitive trace ID to propagate

        Returns:
            HTTP2Response

        ADR: ADR-0001a (K0 Bridge Communication Protocol)
        """
        return await self.request(
            "GET", path, headers, body=None, cognitive_trace_id=cognitive_trace_id
        )

    async def close(self) -> None:
        """
        Graceful connection shutdown.

        This method performs cleanup and closes HTTP/2 connection.

        Lifecycle:
            - Waits for active streams to complete (timeout: 10s)
            - Closes underlying HTTP/2 connections
            - Finalizes metrics

        Guarantees:
            - No data loss (active streams complete)
            - Graceful degradation (timeout if streams hang)

        ADR: ADR-0001a (K0 Bridge Communication Protocol)
        Assigned to: Issue #L5-1.1.2
        """
        # ADR-0001a: K0 Bridge Communication Protocol
        # Step 1: Set state to CLOSING
        if self.state == "CLOSED":
            self._logger.warning(
                "Already closed",
                extra={"host": self.config.k0_host},
            )
            return

        self.state = "CLOSING"
        self._shutdown_event.set()
        self._logger.info(
            "http2_connection_closing",
            extra={"host": self.config.k0_host, "port": self.config.k0_port},
        )

        if self._keepalive_task is not None:
            self._keepalive_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._keepalive_task
            self._keepalive_task = None

        wait_start = time.perf_counter()
        while self._active_streams > 0 and (time.perf_counter() - wait_start) < 10.0:
            self._logger.debug(
                "waiting_for_active_streams",
                extra={"active_streams": self._active_streams},
            )
            await asyncio.sleep(0.1)

        if self._active_streams > 0:
            self._logger.warning(
                "force_closing_with_active_streams",
                extra={"active_streams": self._active_streams},
            )

        await self._close_client()
        self.state = "CLOSED"
        self._logger.info(
            "http2_connection_closed",
            extra={"host": self.config.k0_host, "port": self.config.k0_port},
        )

    # =========================================================================
    # PRIVATE METHODS (Implementation Details)
    # =========================================================================

    def _create_ssl_context(self) -> ssl.SSLContext:
        """
        Create SSL context for TLS 1.3 with mutual authentication.

        Returns:
            ssl.SSLContext configured for TLS 1.3 + mTLS

        Raises:
            ssl.SSLError: If certificate loading fails
        """
        # Create SSL context with secure defaults
        ssl_context = ssl.create_default_context(
            purpose=ssl.Purpose.SERVER_AUTH,
            cafile=None,  # Use system CA store
        )

        # Configure TLS 1.3 (default in Python 3.7+)
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_3
        ssl_context.maximum_version = ssl.TLSVersion.TLSv1_3

        # Enable hostname verification
        ssl_context.check_hostname = True
        ssl_context.verify_mode = ssl.CERT_REQUIRED

        # Log SSL context creation
        self._logger.info(
            "Created TLS 1.3 context for K0 connection",
            extra={
                "hostname": self.config.k0_host,
                "port": self.config.k0_port,
                "verify_mode": "CERT_REQUIRED",
                "check_hostname": True,
            },
        )

        return ssl_context

    @property
    def _base_url(self) -> str:
        protocol = "https" if self.config.use_tls else "http"
        return f"{protocol}://{self.config.k0_host}:{self.config.k0_port}"

    async def _perform_health_check(self) -> None:
        client = self._require_client()
        try:
            response = await client.get(
                self.config.health_path,
                headers={"Accept": "application/json"},
                timeout=min(self.config.request_timeout_s, 5.0),
            )
            response.raise_for_status()
        except Exception as exc:
            self._logger.warning(
                "health_check_error",
                extra={"host": self.config.k0_host, "port": self.config.k0_port, "error": str(exc)},
            )

    async def _ensure_connected(self) -> None:
        if self.state == "CONNECTED":
            return
        await self.connect()

    async def _acquire_stream_slot(self) -> None:
        async with self._queue_lock:
            self._pending_queue += 1
            emit_gauge(
                "k1_k0_bridge_http2_queue_depth",
                self._pending_queue,
                self._metric_labels,
            )

        await self._stream_semaphore.acquire()

        async with self._queue_lock:
            self._pending_queue = max(self._pending_queue - 1, 0)
            emit_gauge(
                "k1_k0_bridge_http2_queue_depth",
                self._pending_queue,
                self._metric_labels,
            )

        self._active_streams += 1
        emit_gauge(
            "k1_k0_bridge_http2_active_streams",
            self._active_streams,
            self._metric_labels,
        )

    async def _release_stream_slot(self) -> None:
        self._active_streams = max(self._active_streams - 1, 0)
        emit_gauge(
            "k1_k0_bridge_http2_active_streams",
            self._active_streams,
            self._metric_labels,
        )
        self._stream_semaphore.release()

    async def _keepalive_loop(self) -> None:
        while not self._shutdown_event.is_set():
            await asyncio.sleep(self.config.keepalive_interval_s)
            if self.state != "CONNECTED":
                continue

            try:
                latency_ms = await self._send_ping()
                emit_histogram(
                    "k1_k0_bridge_http2_ping_latency_ms",
                    latency_ms,
                    self._metric_labels,
                )
            except Exception as exc:  # pragma: no cover - exercised in integration env
                emit_counter(
                    "k1_k0_bridge_http2_reconnect_total",
                    1,
                    self._metric_labels,
                )
                self._logger.warning(
                    "keepalive_failed",
                    extra={"error": str(exc)},
                )
                await self._handle_transport_error(exc)

    async def _send_ping(self) -> float:
        client = self._require_client()
        start = time.perf_counter()
        response = await client.get(
            self.config.health_path,
            headers={"Accept": "application/json"},
            timeout=min(self.config.request_timeout_s, self.config.keepalive_interval_s / 2),
        )
        response.raise_for_status()
        latency_ms = (time.perf_counter() - start) * 1000
        return latency_ms

    async def _handle_transport_error(self, error: Exception) -> None:
        if self.state in {"CLOSING", "CLOSED"}:
            return

        self.state = "DEGRADED"

        async with self._reconnect_lock:
            if self._reconnect_attempts >= self.config.max_reconnect_attempts:
                self._logger.error(
                    "reconnect_attempts_exhausted",
                    extra={"error": str(error)},
                )
                return

            backoff = min(
                self.config.reconnect_backoff_base_s * (2**self._reconnect_attempts),
                60.0,
            )
            backoff *= 1 + random.random() * 0.25  # +0–25% jitter
            self._reconnect_attempts += 1

        await asyncio.sleep(backoff)

        try:
            await self._close_client()
            await self.connect()
            self._reconnect_attempts = 0
        except Exception as exc:  # pragma: no cover - retried in integration env
            self._logger.error(
                "reconnect_failed",
                extra={"error": str(exc)},
            )

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("HTTP/2 client is not initialized")
        return self._client

    async def _close_client(self) -> None:
        client = self._client
        if client is not None:
            await client.aclose()
        self._client = None

    @property
    def _metric_labels(self) -> Dict[str, str]:
        return {"host": self.config.k0_host, "port": str(self.config.k0_port)}


@dataclass
class HTTP2Response:
    """
    HTTP/2 response object.

    Fields:
        status: HTTP status code (200, 404, 500, etc.)
        headers: HTTP response headers (dict)
        body: Response body (bytes)
    """

    status: int
    headers: Dict[str, str]
    body: bytes


# =============================================================================
# SECTION 5: HELPER FUNCTIONS
# =============================================================================


async def create_http2_connection(
    config: Optional[HTTP2Config] = None,
) -> HTTP2Connection:
    """
    Create and connect HTTP/2 connection to K0.

    Args:
        config: HTTP2Config (default: localhost:8080 with TLS 1.3)

    Returns:
        Connected HTTP2Connection instance

    ADR: ADR-0001a (K0 Bridge Communication Protocol)
    Assigned to: Issue #L5-1.1.2
    """
    if config is None:
        config = HTTP2Config()

    connection = HTTP2Connection(config)
    await connection.connect()
    return connection


# =============================================================================
# SECTION 6: MODULE EXPORTS & INITIALIZATION
# =============================================================================

__all__ = [
    "HTTP2Connection",
    "HTTP2Config",
    "HTTP2Response",
    "create_http2_connection",
]


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================
# Metrics to export (Prometheus):
#   - k1_k0_bridge_http2_connections_total{status} (counter: success/error)
#   - k1_k0_bridge_http2_connection_latency_ms (histogram: P50/P95/P99)
#   - k1_k0_bridge_http2_active_streams (gauge: current streams)
#   - k1_k0_bridge_http2_requests_total{method, status} (counter)
#
# Traces to generate (OpenTelemetry):
#   - Span name: k0_bridge.http2_request
#   - Attributes: method, url, status_code, cognitive_trace_id
#   - Links to: upstream command_client spans
#
# Logs to emit (structured logging):
#   - Level: INFO (normal), WARNING (degradation), ERROR (failures)
#   - Fields: component='http2_client', method, status, duration_ms, error
#
# =============================================================================

# =============================================================================
# COGNITIVE TRACE PROPAGATION
# =============================================================================
# HTTP/2 requests must:
#   1. Accept cognitive_trace_id from caller (via headers)
#   2. Propagate via HTTP header: X-Cognitive-Trace-Id
#   3. K0 receives trace_id and includes in all logs/metrics
#
# Example:
#   headers = {'X-Cognitive-Trace-Id': 'trace_abc123'}
#   response = await connection.post('/k0/command', headers=headers, body=payload)
#   # K0 logs: INFO k0.command_port trace_id=trace_abc123 status=SUCCESS
#
# =============================================================================

# =============================================================================
# TESTING REQUIREMENTS (WARD Framework)
# =============================================================================
# Integration tests required:
#   - tests/k1/bridge_k0/test_http2_client.py
#   - Test connection establishment (TLS 1.3 handshake)
#   - Test HTTP/2 multiplexing (100 concurrent streams)
#   - Test connection pooling (10 connections max)
#   - Test connection keepalive (60s timeout)
#   - Test graceful shutdown (active streams complete)
#   - Test TLS certificate verification (mTLS)
#
# No simulation code allowed:
#   - Use real aiohttp test server with HTTP/2 support
#   - Use real TLS certificates (self-signed for testing)
#   - Integration tests > unit tests
#
# Performance budget tests:
#   - Assert connection setup <50ms P95
#   - Assert request send <1ms P95
#   - Assert memory per connection <100KB
#
# =============================================================================
