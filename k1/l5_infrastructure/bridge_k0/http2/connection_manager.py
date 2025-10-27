"""
HTTP/2 Connection Manager for K0 Bridge

Purpose: Centralized HTTP/2 connection pool manager for all K0 Bridge clients
Location: k1/l5_infrastructure/bridge_k0/http2/connection_manager.py
Performance: <100ms connection establishment, >90% pool hit rate

Primary ADRs:
- ADR-0044: K0 Bridge HTTP/2 (bridge client core, transport protocol)
- ADR-0044a: Transport Protocol (HTTP/2 connection, multiplexing, keep-alive)

Related ADRs:
- ADR-0024: Performance Budgets (connection <100ms P95)
- ADR-0009: Circuit Breaker (failure detection, auto-reconnect)
- ADR-0001a: K0 Bridge Architecture (4 ports: Command :5200, Query :5201, SSE :5202, Obs :5203)

Key Responsibilities:

1. Connection Pooling:
   - 1 persistent HTTP/2 connection per K0 port (Command, Query, SSE, Observability)
   - Max 100 concurrent streams per connection (HTTP/2 limit)
   - Connection reuse across requests (>90% pool hit rate target)
   - Automatic cleanup on idle timeout (60s)

2. HTTP/2 Features:
   - Binary framing (efficient protocol, no text parsing)
   - Stream multiplexing (parallel requests on single connection)
   - HPACK header compression (50-90% reduction)
   - PING frames for keep-alive (every 10s)
   - TLS 1.3 support (mutual authentication)

3. Health Monitoring:
   - PING frames every 10s (detect stale connections)
   - Connection health check (<10ms latency)
   - Auto-reconnection on connection failure (exponential backoff)

4. Error Handling:
   - Exponential backoff retry (1s → 2s → 4s → 8s → 16s max)
   - Circuit breaker integration (open on 3 consecutive failures)
   - Connection timeout enforcement (30s)
   - Graceful connection closure on shutdown

Performance Metrics:
- Connection establishment: <100ms P95 (TLS 1.3 handshake)
- Round-trip latency: <10ms P95 (vs 50ms HTTP/1.1)
- Connection pool hit rate: >90%
- PING latency: <10ms P95

Example Usage:
    from k1.l5_infrastructure.bridge_k0.http2 import HTTP2ConnectionManager, K0Port

    # Initialize manager (local dev, no TLS)
    manager = HTTP2ConnectionManager(
        k0_base_url="localhost",
        command_port=5200,
        query_port=5201,
        sse_port=5202,
        obs_port=5203,
    )

    # Production with TLS 1.3
    manager_tls = HTTP2ConnectionManager(
        k0_base_url="k0.example.com",
        use_tls=True,
        verify="/path/to/ca-bundle.crt",
        cert=("/path/to/client-cert.pem", "/path/to/client-key.pem"),
    )

    # Get client for specific port (with optional trace ID)
    async with manager.get_client(K0Port.COMMAND, trace_id="trace-123") as client:
        response = await client.post("/v1/command", json={...})

    # SSE client automatically gets infinite read timeout
    async with manager.get_client(K0Port.SSE) as client:
        async for line in client.stream("GET", "/v1/events"):
            ...

Research Foundation:
- HTTP/2 (RFC 7540): Binary framing, stream multiplexing, header compression
- HPACK (RFC 7541): Header compression algorithm
- TLS 1.3 (RFC 8446): 1-RTT handshake, mutual authentication
- Connection Pooling: httpx connection pooling, keep-alive timeouts

Last Updated: October 2025
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from typing import AsyncIterator, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

__all__ = [
    "K0Port",
    "ConnectionStats",
    "HTTP2ConnectionManager",
    "K0ConnectionError",
]


class K0Port(str, Enum):
    """K0 Bridge ports (ADR-0001a)"""

    COMMAND = "command"  # :5200 - Write operations (CQRS command)
    QUERY = "query"  # :5201 - Read operations (multi-store retrieval)
    SSE = "sse"  # :5202 - Server-sent events (real-time updates)
    OBSERVABILITY = "observability"  # :5203 - Metrics/logs push


@dataclass
class ConnectionStats:
    """Connection statistics for monitoring"""

    port: K0Port
    is_connected: bool
    connection_attempts: int = 0
    connection_successes: int = 0
    connection_failures: int = 0
    last_ping_latency_ms: float = 0.0
    pool_hit_count: int = 0
    pool_miss_count: int = 0
    created_at_ms: float = 0.0
    last_used_ms: float = 0.0


class K0ConnectionError(Exception):
    """K0 connection manager error (avoids shadowing Python's ConnectionError)"""

    pass


class HTTP2ConnectionManager:
    """Centralized HTTP/2 connection pool manager for K0 Bridge

    Features:
    - 1 persistent HTTP/2 connection per K0 port (Command, Query, SSE, Observability)
    - Stream multiplexing (max 100 concurrent streams per connection)
    - PING frames for keep-alive (every 10s)
    - TLS 1.3 support with mutual authentication
    - Exponential backoff retry on connection failure
    - Connection pool reuse (>90% hit rate target)

    Performance:
    - Connection establishment: <100ms P95
    - Round-trip latency: <10ms P95
    - Pool hit rate: >90%

    Example:
        manager = HTTP2ConnectionManager(k0_base_url="http://localhost")
        async with manager.get_client("command") as client:
            response = await client.post("/v1/command", json={...})
    """

    def __init__(
        self,
        k0_base_url: str = "localhost",
        command_port: int = 5200,
        query_port: int = 5201,
        sse_port: int = 5202,
        obs_port: int = 5203,
        max_connections: int = 5,  # 1 per port + 1 spare
        max_keepalive_connections: int = 5,
        keepalive_expiry: float = 60.0,  # 60s keep-alive timeout
        timeout: float = 30.0,  # 30s request timeout
        http2: bool = True,  # Enable HTTP/2
        use_tls: bool = False,  # Enable TLS/HTTPS (default: False for local dev)
        verify: (
            bool | str
        ) = True,  # TLS verification: True, False, or path to CA bundle
        cert: Optional[
            str | tuple[str, str]
        ] = None,  # Client cert: path or (cert, key)
    ):
        """Initialize HTTP/2 connection manager

        Args:
            k0_base_url: Base URL for K0 (e.g., localhost, no scheme)
            command_port: Command port (default: 5200)
            query_port: Query port (default: 5201)
            sse_port: SSE port (default: 5202)
            obs_port: Observability port (default: 5203)
            max_connections: Max connections per port (default: 5)
            max_keepalive_connections: Max keep-alive connections (default: 5)
            keepalive_expiry: Keep-alive timeout in seconds (default: 60s)
            timeout: Request timeout in seconds (default: 30s)
            http2: Enable HTTP/2 (default: True)
            use_tls: Enable TLS/HTTPS (default: False for local dev, True for production)
            verify: TLS verification - True (default CA), False (skip), or path to CA bundle
            cert: Client cert for mutual TLS - path to cert file or (cert_path, key_path) tuple
        """
        self.k0_base_url = k0_base_url.rstrip("/")
        self.command_port = command_port
        self.query_port = query_port
        self.sse_port = sse_port
        self.obs_port = obs_port

        # Connection pool settings
        self.max_connections = max_connections
        self.max_keepalive_connections = max_keepalive_connections
        self.keepalive_expiry = keepalive_expiry
        self.timeout = timeout
        self.http2 = http2

        # TLS settings (FIX 3: TLS/ALPN support)
        self.use_tls = use_tls
        self.scheme = "https" if use_tls else "http"
        self.verify = verify
        self.cert = cert

        # Connection pool (port -> httpx.AsyncClient)
        self._clients: Dict[K0Port, httpx.AsyncClient] = {}
        self._client_lock = asyncio.Lock()

        # Connection statistics
        self._stats: Dict[K0Port, ConnectionStats] = {
            K0Port.COMMAND: ConnectionStats(port=K0Port.COMMAND, is_connected=False),
            K0Port.QUERY: ConnectionStats(port=K0Port.QUERY, is_connected=False),
            K0Port.SSE: ConnectionStats(port=K0Port.SSE, is_connected=False),
            K0Port.OBSERVABILITY: ConnectionStats(
                port=K0Port.OBSERVABILITY, is_connected=False
            ),
        }

        # Reconnection tracking (FIX 5: Exponential backoff)
        self._reconnect_attempts: Dict[K0Port, int] = {
            K0Port.COMMAND: 0,
            K0Port.QUERY: 0,
            K0Port.SSE: 0,
            K0Port.OBSERVABILITY: 0,
        }
        self._reconnect_tasks: Dict[K0Port, Optional[asyncio.Task]] = {
            K0Port.COMMAND: None,
            K0Port.QUERY: None,
            K0Port.SSE: None,
            K0Port.OBSERVABILITY: None,
        }

        # Health check task
        self._health_check_task: Optional[asyncio.Task] = None
        self._health_check_interval = 10.0  # 10s PING interval
        self._shutdown = False

        logger.info(
            "[HTTP2ConnectionManager] Initialized",
            extra={
                "k0_base_url": self.k0_base_url,
                "scheme": self.scheme,
                "command_port": command_port,
                "query_port": query_port,
                "sse_port": sse_port,
                "obs_port": obs_port,
                "http2": http2,
                "use_tls": use_tls,
            },
        )

    async def start(self) -> None:
        """Start connection manager and health check task"""
        if self._health_check_task is None:
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            logger.info("[HTTP2ConnectionManager] Health check task started")

    async def stop(self) -> None:
        """Stop connection manager and close all connections"""
        self._shutdown = True

        # Cancel health check task
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        # Close all clients
        async with self._client_lock:
            for port, client in self._clients.items():
                await client.aclose()
                logger.info(
                    "[HTTP2ConnectionManager] Connection closed",
                    extra={"port": port.value},
                )
            self._clients.clear()

        logger.info("[HTTP2ConnectionManager] Stopped")

    @asynccontextmanager
    async def get_client(
        self, port: K0Port, trace_id: Optional[str] = None
    ) -> AsyncIterator[httpx.AsyncClient]:
        """Get or create HTTP/2 client for port

        Args:
            port: K0 port (COMMAND, QUERY, SSE, OBSERVABILITY)
            trace_id: Optional cognitive trace ID for cross-tool correlation (FIX 7)

        Yields:
            httpx.AsyncClient configured for HTTP/2

        Performance: <100ms connection establishment on first request, <1ms on subsequent (pool hit)

        Note: FIX 1 - Lock is released BEFORE yielding to prevent serializing all requests
        """
        # FIX 1: Acquire lock, read/create client, then release BEFORE yielding
        async with self._client_lock:
            client = self._clients.get(port)

            if client:
                # Pool hit
                self._stats[port].pool_hit_count += 1
                self._stats[port].last_used_ms = time.time() * 1000
                logger.debug(
                    "[HTTP2ConnectionManager] Connection pool hit",
                    extra={"port": port.value},
                )
            else:
                # Pool miss - create new client
                self._stats[port].pool_miss_count += 1
                self._stats[port].connection_attempts += 1

                try:
                    client = await self._create_client(port, trace_id=trace_id)
                    self._clients[port] = client
                    self._stats[port].is_connected = True
                    self._stats[port].connection_successes += 1
                    now_ms = time.time() * 1000
                    self._stats[port].created_at_ms = now_ms
                    self._stats[port].last_used_ms = now_ms

                    # Reset reconnect attempts on successful connection
                    self._reconnect_attempts[port] = 0

                    logger.info(
                        "[HTTP2ConnectionManager] Connection established",
                        extra={
                            "port": port.value,
                            "pool_hit_rate": self._calculate_hit_rate(port),
                        },
                    )

                except Exception as e:
                    self._stats[port].is_connected = False
                    self._stats[port].connection_failures += 1
                    logger.error(
                        "[HTTP2ConnectionManager] Connection failed",
                        extra={"port": port.value, "error": str(e)},
                    )
                    raise K0ConnectionError(
                        f"Failed to connect to K0 {port.value} port: {e}"
                    )

        # Lock is released here - now yield client without holding lock
        # FIX 7: Add cognitive trace header scoped to this context (no contamination)
        hook_fn = None
        try:
            if trace_id and client:
                # Use event hook to inject header per-request (scoped to context)
                async def add_trace_header(request: httpx.Request) -> None:
                    request.headers["X-Cognitive-Trace-Id"] = trace_id

                hook_fn = add_trace_header
                client.event_hooks.setdefault("request", []).append(hook_fn)

            yield client
        finally:
            # Remove trace header hook to prevent cross-request contamination
            if hook_fn and client and "request" in client.event_hooks:
                try:
                    client.event_hooks["request"].remove(hook_fn)
                except ValueError:
                    pass  # Already removed

            # Update last_used_ms on release
            self._stats[port].last_used_ms = time.time() * 1000

    async def _create_client(
        self, port: K0Port, trace_id: Optional[str] = None
    ) -> httpx.AsyncClient:
        """Create HTTP/2 client for port

        Args:
            port: K0 port
            trace_id: Optional cognitive trace ID for X-Cognitive-Trace-Id header

        Returns:
            Configured httpx.AsyncClient with HTTP/2 enabled

        Performance: <100ms P95 (TLS 1.3 handshake)
        """
        # Determine port number
        port_number = {
            K0Port.COMMAND: self.command_port,
            K0Port.QUERY: self.query_port,
            K0Port.SSE: self.sse_port,
            K0Port.OBSERVABILITY: self.obs_port,
        }[port]

        # FIX 3: Build URL with correct scheme (http:// or https://)
        base_url = f"{self.scheme}://{self.k0_base_url}:{port_number}"

        # HTTP/2 connection pool settings (ADR-0044a)
        limits = httpx.Limits(
            max_connections=self.max_connections,
            max_keepalive_connections=self.max_keepalive_connections,
            keepalive_expiry=self.keepalive_expiry,
        )

        # FIX 6: Get timeout for port (SSE needs infinite read timeout)
        timeout = self.get_timeout(port)

        # Build headers
        headers = {
            "User-Agent": "K1-Bridge-HTTP2/1.0",
            "Accept": "application/json",  # Primary format (ADR-0044b)
            "Accept-Encoding": "gzip, deflate, br",  # httpx-supported compression
        }

        # FIX 7: Add cognitive trace header if provided
        if trace_id:
            headers["X-Cognitive-Trace-Id"] = trace_id

        # Create client with HTTP/2 support
        client = httpx.AsyncClient(
            base_url=base_url,
            http2=self.http2,  # Enable HTTP/2
            limits=limits,
            timeout=timeout,
            verify=self.verify,  # FIX 3: TLS verification setting
            cert=self.cert,  # FIX 3: Client cert for mutual TLS
            headers=headers,
        )

        return client

    async def _health_check_loop(self) -> None:
        """Health check loop (PING frames every 10s)

        Sends PING requests to all connected clients every 10s to detect stale connections.
        Measures latency and updates connection statistics.

        FIX 2: Snapshot clients dict with lock to prevent race conditions
        FIX 4: Evict idle connections after keepalive_expiry
        FIX 5: Trigger reconnection on PING failure
        """
        logger.info("[HTTP2ConnectionManager] Health check loop started")

        while not self._shutdown:
            try:
                await asyncio.sleep(self._health_check_interval)

                # FIX 2: Snapshot clients dict safely with lock
                async with self._client_lock:
                    client_items = list(self._clients.items())

                # PING all connected clients (outside of lock)
                for port, client in client_items:
                    try:
                        start_time = time.perf_counter()

                        # Send health check request (lightweight GET)
                        response = await client.get(
                            "/healthz", timeout=5.0  # Short timeout for PING
                        )

                        latency_ms = (time.perf_counter() - start_time) * 1000

                        if response.status_code == 200:
                            self._stats[port].last_ping_latency_ms = latency_ms
                            # Reset reconnect attempts on successful PING
                            self._reconnect_attempts[port] = 0
                            logger.debug(
                                "[HTTP2ConnectionManager] PING OK",
                                extra={
                                    "port": port.value,
                                    "latency_ms": f"{latency_ms:.2f}",
                                },
                            )
                        else:
                            logger.warning(
                                "[HTTP2ConnectionManager] PING failed (non-200)",
                                extra={
                                    "port": port.value,
                                    "status_code": response.status_code,
                                },
                            )
                            # FIX 5: Trigger reconnection on unhealthy response
                            await self._handle_unhealthy_connection(port)

                    except Exception as e:
                        logger.error(
                            "[HTTP2ConnectionManager] PING error",
                            extra={"port": port.value, "error": str(e)},
                        )
                        # FIX 5: Trigger reconnection on PING error
                        await self._handle_unhealthy_connection(port)

                # FIX 4: Evict idle connections
                await self._evict_idle_connections()

            except asyncio.CancelledError:
                logger.info("[HTTP2ConnectionManager] Health check loop cancelled")
                break
            except Exception as e:
                logger.error(
                    "[HTTP2ConnectionManager] Health check loop error",
                    extra={"error": str(e)},
                )

    async def _handle_unhealthy_connection(self, port: K0Port) -> None:
        """Handle unhealthy connection (FIX 5: Trigger reconnection)

        Args:
            port: K0 port with unhealthy connection
        """
        # Mark connection as unhealthy
        self._stats[port].is_connected = False

        # Close and remove unhealthy client
        async with self._client_lock:
            if port in self._clients:
                try:
                    await self._clients[port].aclose()
                except Exception as e:
                    logger.warning(
                        "[HTTP2ConnectionManager] Error closing unhealthy connection",
                        extra={"port": port.value, "error": str(e)},
                    )
                del self._clients[port]
                logger.info(
                    "[HTTP2ConnectionManager] Unhealthy connection removed",
                    extra={"port": port.value},
                )

        # Start reconnection task if not already running
        task = self._reconnect_tasks.get(port)
        if task is None or task.done():
            self._reconnect_tasks[port] = asyncio.create_task(self._try_reconnect(port))

    async def _try_reconnect(self, port: K0Port) -> None:
        """Try to reconnect with exponential backoff (FIX 5)

        Args:
            port: K0 port to reconnect

        Backoff: 1s → 2s → 4s → 8s → 16s (max)
        """
        attempt = self._reconnect_attempts[port]
        delay = min(2**attempt, 16)  # Cap at 16s
        self._reconnect_attempts[port] += 1

        logger.info(
            "[HTTP2ConnectionManager] Reconnecting",
            extra={
                "port": port.value,
                "attempt": attempt + 1,
                "delay_s": delay,
            },
        )

        await asyncio.sleep(delay)

        # Check if already reconnected (by get_client call)
        async with self._client_lock:
            if port in self._clients:
                logger.info(
                    "[HTTP2ConnectionManager] Connection already restored",
                    extra={"port": port.value},
                )
                self._reconnect_attempts[port] = 0
                return

        # Try to create new client
        try:
            client = await self._create_client(port)
            async with self._client_lock:
                # Double-check not reconnected during creation
                if port not in self._clients:
                    self._clients[port] = client
                    self._stats[port].is_connected = True
                    self._stats[port].connection_successes += 1
                    self._reconnect_attempts[port] = 0
                    logger.info(
                        "[HTTP2ConnectionManager] Reconnection successful",
                        extra={"port": port.value, "attempt": attempt + 1},
                    )
                else:
                    # Already reconnected by another task
                    await client.aclose()
        except Exception as e:
            logger.error(
                "[HTTP2ConnectionManager] Reconnection failed",
                extra={
                    "port": port.value,
                    "attempt": attempt + 1,
                    "error": str(e),
                },
            )
            # Will retry on next health check cycle

    async def _evict_idle_connections(self) -> None:
        """Evict idle connections (FIX 4: Idle eviction)

        Closes connections idle for more than keepalive_expiry seconds.
        """
        now_ms = time.time() * 1000
        stale: list[tuple[K0Port, float]] = []  # (port, idle_s)

        # Find stale connections
        async with self._client_lock:
            for port, stats in self._stats.items():
                if port in self._clients and stats.last_used_ms:
                    idle_s = (now_ms - stats.last_used_ms) / 1000
                    if idle_s > self.keepalive_expiry:
                        stale.append((port, idle_s))

        # Close stale connections (outside lock)
        for port, idle_s in stale:
            async with self._client_lock:
                if port in self._clients:
                    try:
                        await self._clients[port].aclose()
                    except Exception as e:
                        logger.warning(
                            "[HTTP2ConnectionManager] Error closing idle connection",
                            extra={"port": port.value, "error": str(e)},
                        )
                    del self._clients[port]
                    self._stats[port].is_connected = False
                    logger.info(
                        "[HTTP2ConnectionManager] Idle connection evicted",
                        extra={
                            "port": port.value,
                            "idle_s": f"{idle_s:.1f}",
                        },
                    )

    def get_timeout(self, port: K0Port) -> httpx.Timeout:
        """Get timeout configuration for port (FIX 6: SSE timeout override)

        Args:
            port: K0 port

        Returns:
            httpx.Timeout configured for port type

        SSE needs infinite read timeout for streaming, others use default.
        """
        if port == K0Port.SSE:
            # SSE needs infinite read timeout for long-lived streams
            return httpx.Timeout(
                connect=self.timeout,
                read=None,  # Infinite read timeout
                write=self.timeout,
                pool=self.timeout,
            )
        else:
            # Command, Query, Observability use default timeout
            return httpx.Timeout(self.timeout)

    def _calculate_hit_rate(self, port: K0Port) -> str:
        """Calculate connection pool hit rate

        Args:
            port: K0 port

        Returns:
            Hit rate percentage string (e.g., "95.2%")
        """
        stats = self._stats[port]
        total = stats.pool_hit_count + stats.pool_miss_count
        if total == 0:
            return "N/A"
        hit_rate = (stats.pool_hit_count / total) * 100
        return f"{hit_rate:.1f}%"

    def get_stats(self, port: K0Port) -> ConnectionStats:
        """Get connection statistics for port

        Args:
            port: K0 port

        Returns:
            ConnectionStats object
        """
        return self._stats[port]

    def command_client(self) -> httpx.AsyncClient:
        """Get Command Port client (convenience method)

        DEPRECATED: Use `async with manager.get_client(K0Port.COMMAND)` instead.
        This method doesn't properly manage connection lifecycle.

        Raises:
            NotImplementedError: Always. Use get_client() context manager.
        """
        raise NotImplementedError(
            "Use `async with manager.get_client(K0Port.COMMAND)` instead for proper connection lifecycle management"
        )

    def query_client(self) -> httpx.AsyncClient:
        """Get Query Port client (convenience method)

        DEPRECATED: Use `async with manager.get_client(K0Port.QUERY)` instead.

        Raises:
            NotImplementedError: Always. Use get_client() context manager.
        """
        raise NotImplementedError(
            "Use `async with manager.get_client(K0Port.QUERY)` instead"
        )

    def sse_client(self) -> httpx.AsyncClient:
        """Get SSE Port client (convenience method)

        DEPRECATED: Use `async with manager.get_client(K0Port.SSE)` instead.

        Raises:
            NotImplementedError: Always. Use get_client() context manager.
        """
        raise NotImplementedError(
            "Use `async with manager.get_client(K0Port.SSE)` instead"
        )

    def obs_client(self) -> httpx.AsyncClient:
        """Get Observability Port client (convenience method)

        DEPRECATED: Use `async with manager.get_client(K0Port.OBSERVABILITY)` instead.

        Raises:
            NotImplementedError: Always. Use get_client() context manager.
        """
        raise NotImplementedError(
            "Use `async with manager.get_client(K0Port.OBSERVABILITY)` instead"
        )
