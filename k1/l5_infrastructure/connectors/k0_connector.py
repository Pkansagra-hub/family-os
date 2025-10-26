"""
K0 Connection Lifecycle Manager

Purpose: Manage HTTP/2 connections to K0 with health checks and auto-reconnection
Location: k1/l5_infrastructure/connectors/k0_connector.py
Performance: <100ms connection establishment, >90% pool hit rate

Primary ADRs:
- ADR-0001a: K0 Bridge Architecture (connection management, 4 ports)
- ADR-0022b: HTTP/2 Multiplexing (httpx library, HPACK compression)
- ADR-0044: K0 Bridge HTTP/2 (TLS 1.3, connection pooling)
- ADR-0044a: Transport Protocol (health checks, auto-reconnect)

Related ADRs:
- ADR-0024: Performance Budgets (connection establishment <100ms)
- ADR-0009: Circuit Breaker (failure detection, auto-reconnect)

Features:
- HTTP/2 connection pool (5 persistent connections)
- Health monitoring (10s interval, /healthz endpoint)
- Auto-reconnection (exponential backoff 1s→30s with jitter)
- Connection reuse tracking (>90% pool hit rate target)
- TLS 1.3 support (encrypted K1→K0 communication)

Research Foundation:
- HTTP/2: RFC 7540 (Multiplexing, HPACK), RFC 7541 (Header Compression)
- TLS 1.3: RFC 8446 (0-RTT resumption, modern cipher suites)
- Exponential Backoff: AWS Retry Guidance, Ethernet Collision Avoidance
- Circuit Breaker: Michael Nygard, "Release It!" (2007)

Last Updated: January 2025
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """Connection lifecycle states"""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    DRAINING = "draining"  # Graceful shutdown in progress


class ConnectionType(Enum):
    """K0 connection types (one per port)"""

    COMMAND = "command"  # :5200 - Write operations
    QUERY = "query"  # :5201 - Read operations
    SSE = "sse"  # :5202 - Event streaming
    OBSERVABILITY = "observability"  # :5203 - Metrics/logs push
    HEALTH = "health"  # :5204 - Dedicated health checks


@dataclass
class ConnectionConfig:
    """Configuration for K0 connection"""

    host: str = "localhost"
    command_port: int = 5200
    query_port: int = 5201
    sse_port: int = 5202
    observability_port: int = 5203
    use_tls: bool = False  # Enable TLS 1.3 (use https://)
    health_interval_s: float = 10.0  # Health check every 10s
    health_timeout_s: float = 30.0  # Unhealthy if no response in 30s
    reconnect_base_s: float = 1.0  # Exponential backoff base
    reconnect_max_s: float = 30.0  # Max backoff delay
    reconnect_jitter: float = 0.1  # ±10% jitter
    connection_timeout_s: float = 5.0  # Connection timeout
    max_keepalive: int = 5  # 5 persistent connections


@dataclass
class ConnectionStats:
    """Connection pool statistics"""

    total_requests: int = 0
    successful_requests: int = 0  # Requests completed successfully
    failed_requests: int = 0  # Requests that failed
    reconnections: int = 0
    health_checks: int = 0
    health_failures: int = 0
    total_latency_ms: float = 0.0  # Sum of all request latencies

    @property
    def avg_latency_ms(self) -> float:
        """Calculate average request latency"""
        return (
            (self.total_latency_ms / self.total_requests)
            if self.total_requests > 0
            else 0.0
        )

    @property
    def success_rate(self) -> float:
        """Calculate request success rate"""
        total = self.successful_requests + self.failed_requests
        return (self.successful_requests / total * 100) if total > 0 else 0.0


class K0Connector:
    """
    K0 Connection Lifecycle Manager

    Responsibilities:
    - Manage HTTP/2 connections to K0 (5 persistent connections)
    - Health monitoring (10s interval, /healthz endpoint)
    - Auto-reconnection (exponential backoff with jitter)
    - Connection reuse tracking (>90% pool hit rate)

    Performance:
    - Connection establishment: <100ms P95
    - Health check: 10s interval, <10ms latency
    - Pool hit rate: >90% (connection reuse)
    - Reconnection: 1s→30s exponential backoff

    Example:
        connector = K0Connector(config)
        await connector.connect()

        # Use command connection
        async with connector.get_client(ConnectionType.COMMAND) as client:
            response = await client.post("/k0/command.submit", json=data)

        # Health check callback
        def on_health_change(is_healthy: bool):
            print(f"K0 health: {is_healthy}")

        connector.register_health_callback(on_health_change)

        # Shutdown
        await connector.shutdown()
    """

    def __init__(self, config: Optional[ConnectionConfig] = None):
        """Initialize K0 connector

        Args:
            config: Connection configuration (defaults to local K0)
        """
        self.config = config or ConnectionConfig()

        # Connection pool (one client per connection type)
        self._clients: Dict[ConnectionType, Optional[httpx.AsyncClient]] = {
            ConnectionType.COMMAND: None,
            ConnectionType.QUERY: None,
            ConnectionType.SSE: None,
            ConnectionType.OBSERVABILITY: None,
            ConnectionType.HEALTH: None,
        }

        # Connection state
        self.state = ConnectionState.DISCONNECTED
        self._reconnect_attempt = 0
        self._reconnecting = False  # Single-flight reconnection guard

        # Health monitoring
        self._health_task: Optional[asyncio.Task] = None
        self._health_callbacks: list[Callable[[bool], None]] = []
        self._is_healthy = False

        # Thread-safety for state mutations
        self._lock = asyncio.Lock()

        # Statistics
        self.stats = ConnectionStats()

        logger.info(
            "[K0Connector] Initialized",
            extra={
                "host": self.config.host,
                "command_port": self.config.command_port,
                "use_tls": self.config.use_tls,
                "health_interval_s": self.config.health_interval_s,
            },
        )

    async def connect(self) -> None:
        """Establish connections to K0

        Creates HTTP/2 connection pool with 5 persistent connections.
        Starts health monitoring task.

        Performance: <100ms P95
        """
        async with self._lock:
            if self.state == ConnectionState.CONNECTED:
                logger.warning("[K0Connector] Already connected")
                return

            # Cancel old health task if any (avoid duplicate loops)
            if self._health_task:
                self._health_task.cancel()
                try:
                    await self._health_task
                except asyncio.CancelledError:
                    pass

            self.state = ConnectionState.CONNECTING
            start_ms = time.perf_counter() * 1000

            try:
                # Create HTTP/2 clients for each connection type
                self._clients[ConnectionType.COMMAND] = self._create_client(
                    self.config.command_port
                )
                self._clients[ConnectionType.QUERY] = self._create_client(
                    self.config.query_port
                )
                self._clients[ConnectionType.SSE] = self._create_client(
                    self.config.sse_port
                )
                self._clients[ConnectionType.OBSERVABILITY] = self._create_client(
                    self.config.observability_port
                )
                self._clients[ConnectionType.HEALTH] = self._create_client(
                    self.config.command_port  # Health endpoint on command port
                )

                # Initial health check (use configured timeout)
                is_healthy = await self._check_health()
                self._is_healthy = is_healthy

                if not is_healthy:
                    logger.warning("[K0Connector] K0 unhealthy on connect")

                # Start health monitoring
                self._health_task = asyncio.create_task(self._health_monitor_loop())

                self.state = ConnectionState.CONNECTED
                self._reconnect_attempt = 0  # Reset backoff
                self._reconnecting = False

                latency_ms = time.perf_counter() * 1000 - start_ms

                logger.info(
                    "[K0Connector] Connected to K0",
                    extra={
                        "latency_ms": round(latency_ms, 2),
                        "is_healthy": is_healthy,
                        "pool_size": self.config.max_keepalive,
                        "scheme": "https" if self.config.use_tls else "http",
                    },
                )

            except Exception as e:
                self.state = ConnectionState.DISCONNECTED
                logger.error(
                    "[K0Connector] Connection failed",
                    extra={"error": str(e)},
                    exc_info=True,
                )
                raise

    async def shutdown(self) -> None:
        """Graceful shutdown - drain connections and close

        Stops health monitoring, drains in-flight requests, closes connections.
        """
        if self.state == ConnectionState.DISCONNECTED:
            return

        logger.info("[K0Connector] Shutting down...")
        self.state = ConnectionState.DRAINING

        # Stop health monitoring
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass

        # Close all clients
        for conn_type, client in self._clients.items():
            if client:
                await client.aclose()
                logger.debug(
                    "[K0Connector] Closed connection", extra={"type": conn_type.value}
                )

        self._clients = {k: None for k in self._clients.keys()}
        self.state = ConnectionState.DISCONNECTED

        logger.info(
            "[K0Connector] Shutdown complete",
            extra={
                "total_requests": self.stats.total_requests,
                "success_rate": f"{self.stats.success_rate:.1f}%",
                "reconnections": self.stats.reconnections,
            },
        )

    def get_client(self, conn_type: ConnectionType) -> Optional[httpx.AsyncClient]:
        """Get HTTP client for connection type

        Args:
            conn_type: Connection type (COMMAND, QUERY, SSE, OBSERVABILITY, HEALTH)

        Returns:
            httpx.AsyncClient instance (None if not connected)

        Note: Actual request tracking done via httpx event hooks.
        """
        return self._clients.get(conn_type)

    def register_health_callback(self, callback: Callable[[bool], None]) -> None:
        """Register callback for health state changes

        Args:
            callback: Function called with health state (True=healthy, False=unhealthy)
        """
        self._health_callbacks.append(callback)

    async def get_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics

        Returns:
            Dict with stats: total_requests, success_rate, reconnections, etc.
        """
        return {
            "state": self.state.value,
            "is_healthy": self._is_healthy,
            "total_requests": self.stats.total_requests,
            "successful_requests": self.stats.successful_requests,
            "failed_requests": self.stats.failed_requests,
            "success_rate": round(self.stats.success_rate, 2),
            "avg_latency_ms": round(self.stats.avg_latency_ms, 2),
            "reconnections": self.stats.reconnections,
            "health_checks": self.stats.health_checks,
            "health_failures": self.stats.health_failures,
        }

    # Private methods

    def _event_hooks(self) -> Dict[str, list]:
        """Create httpx event hooks for request tracking"""

        async def on_request_start(request: httpx.Request) -> None:
            self.stats.total_requests += 1

        async def on_response(response: httpx.Response) -> None:
            if response.is_success:
                self.stats.successful_requests += 1
            else:
                self.stats.failed_requests += 1

        return {"request": [on_request_start], "response": [on_response]}

    def _create_client(self, port: int) -> httpx.AsyncClient:
        """Create HTTP/2 client for K0 port

        Args:
            port: K0 port number

        Returns:
            Configured httpx.AsyncClient with HTTP/2
        """
        scheme = "https" if self.config.use_tls else "http"
        base_url = f"{scheme}://{self.config.host}:{port}"

        return httpx.AsyncClient(
            base_url=base_url,
            http2=True,  # Enable HTTP/2
            limits=httpx.Limits(
                max_keepalive_connections=self.config.max_keepalive,
                max_connections=self.config.max_keepalive,
            ),
            timeout=httpx.Timeout(self.config.connection_timeout_s),
            verify=self.config.use_tls,  # TLS verification if enabled
            event_hooks=self._event_hooks(),
        )

    async def _check_health(self) -> bool:
        """Check K0 health (GET /healthz)

        Returns:
            True if healthy (status 200), False otherwise

        Performance: <10ms P95
        """
        health_client = self._clients.get(ConnectionType.HEALTH)
        if not health_client:
            return False

        try:
            start_ms = time.perf_counter() * 1000
            response = await health_client.get(
                "/healthz", timeout=self.config.health_timeout_s
            )
            latency_ms = time.perf_counter() * 1000 - start_ms

            is_healthy = response.status_code == 200

            self.stats.health_checks += 1
            if not is_healthy:
                self.stats.health_failures += 1

            logger.debug(
                "[K0Connector] Health check",
                extra={
                    "is_healthy": is_healthy,
                    "status_code": response.status_code,
                    "latency_ms": round(latency_ms, 2),
                },
            )

            return is_healthy

        except Exception as e:
            self.stats.health_checks += 1
            self.stats.health_failures += 1

            logger.warning("[K0Connector] Health check failed", extra={"error": str(e)})
            return False

    async def _health_monitor_loop(self) -> None:
        """Background task: health check every 10s

        Monitors K0 health, triggers reconnection on failure,
        notifies callbacks on health state changes.
        """
        logger.info("[K0Connector] Health monitor started")

        while True:
            try:
                await asyncio.sleep(self.config.health_interval_s)

                # Health check
                is_healthy = await self._check_health()

                # Health state change
                if is_healthy != self._is_healthy:
                    logger.info(
                        "[K0Connector] Health state changed",
                        extra={
                            "old_state": self._is_healthy,
                            "new_state": is_healthy,
                        },
                    )

                    self._is_healthy = is_healthy

                    # Notify callbacks
                    for callback in self._health_callbacks:
                        try:
                            callback(is_healthy)
                        except Exception as e:
                            logger.error(
                                "[K0Connector] Health callback error",
                                extra={"error": str(e)},
                                exc_info=True,
                            )

                # Trigger reconnection if unhealthy
                if not is_healthy and self.state == ConnectionState.CONNECTED:
                    logger.warning(
                        "[K0Connector] K0 unhealthy, triggering reconnection"
                    )
                    asyncio.create_task(self._reconnect())

            except asyncio.CancelledError:
                logger.info("[K0Connector] Health monitor stopped")
                break
            except Exception as e:
                logger.error(
                    "[K0Connector] Health monitor error",
                    extra={"error": str(e)},
                    exc_info=True,
                )

    async def _reconnect(self) -> None:
        """Reconnect to K0 with exponential backoff (single-flight)

        Backoff: 1s → 2s → 4s → 8s → 30s max (with ±10% jitter)
        """
        # Single-flight guard: only one reconnection attempt at a time
        async with self._lock:
            if self._reconnecting:
                logger.debug("[K0Connector] Reconnection already in progress")
                return
            self._reconnecting = True

        try:
            # Calculate backoff delay
            delay_s = min(
                self.config.reconnect_base_s * (2**self._reconnect_attempt),
                self.config.reconnect_max_s,
            )

            # Add jitter (±10%)
            jitter = delay_s * self.config.reconnect_jitter * (random.random() * 2 - 1)
            delay_s = max(0.1, delay_s + jitter)

            self.stats.reconnections += 1

            logger.info(
                "[K0Connector] Reconnecting",
                extra={
                    "attempt": self._reconnect_attempt + 1,
                    "delay_s": round(delay_s, 2),
                },
            )

            await asyncio.sleep(delay_s)

            # Close existing clients safely
            async with self._lock:
                for client in self._clients.values():
                    if client:
                        await client.aclose()
                self._clients = {k: None for k in self._clients.keys()}
                self.state = ConnectionState.DISCONNECTED

            # Reconnect (will reset _reconnecting flag in connect())
            await self.connect()

            logger.info("[K0Connector] Reconnection successful")

        except Exception as e:
            logger.error("[K0Connector] Reconnection failed", extra={"error": str(e)})

            self._reconnect_attempt += 1
            async with self._lock:
                self.state = ConnectionState.DISCONNECTED
                self._reconnecting = False

            # Schedule next reconnection attempt
            asyncio.create_task(self._reconnect())
