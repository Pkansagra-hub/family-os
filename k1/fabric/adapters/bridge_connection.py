"""
k1.fabric.adapters.bridge_connection -- BridgeConnectionAdapter (5.2.8).

Production adapter for IBridgePort.  Connects to the Cross-Kernel Bridge
WHEN AVAILABLE.

Design:
  - Bridge design is complete (``bridge_architecture.mmd``) but Bridge
    code is NOT yet built.  This adapter is bridge-ready from day one.
  - On init: optionally accepts a bridge client object (typed as Any to
    avoid hard dependency).  If no client is provided, starts in
    LOCAL COLD mode (all operations return offline fallback).
  - ``is_available()``: True only if client is connected and healthy.
  - All operations: if available, route through client; if not, return
    graceful ``BridgeCommandResult.fail("k0_offline", ...)`` fallback.
  - Auto-reconnect: ``reconnect()`` attempts to re-establish connection.
    Callers (e.g. a health-check loop) can call this periodically.
  - Thread-safe via RLock.

Bridge client protocol (future):
  The adapter expects a bridge client with methods:
    - async send(operation, payload, trace_id, timeout_ms) -> dict
    - async query(operation, selectors, trace_id, timeout_ms) -> dict
    - async route_ifl(address, payload, trace_id) -> dict
    - is_connected() -> bool
    - get_health() -> dict  (keys: available, mode, latency_ms, ...)
    - async connect() -> bool
    - async disconnect() -> None
  When the client is built, it will satisfy this shape.

Structural subtyping:
  Satisfies IBridgePort protocol without inheriting from it.

Exports:
  BridgeConnectionAdapter
  BridgeConnectionConfig
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from k1.fabric.ports.bridge_port import BridgeCommandResult, BridgeHealth, IFLRoute

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BridgeConnectionConfig:
    """
    Configuration for the BridgeConnectionAdapter.

    Attributes:
        endpoint: Bridge endpoint URL (e.g. ``"http://localhost:8090"``).
        default_timeout_ms: Default per-operation timeout.
        reconnect_interval_ms: Minimum interval between reconnect attempts.
        max_reconnect_attempts: Max consecutive reconnect failures before
            giving up (0 = unlimited).
    """

    endpoint: str = "http://localhost:8090"
    default_timeout_ms: int = 5000
    reconnect_interval_ms: int = 10000
    max_reconnect_attempts: int = 0


# ---------------------------------------------------------------------------
# BridgeConnectionAdapter
# ---------------------------------------------------------------------------

_OFFLINE_HEALTH = BridgeHealth(
    available=False,
    mode="K0_OFFLINE",
    error_message="Bridge not connected",
)

_OFFLINE_FAIL_CODE = "k0_offline"
_OFFLINE_FAIL_MSG = "Bridge unavailable (LOCAL COLD mode)"


class BridgeConnectionAdapter:
    """
    Production Bridge adapter for K0 access (5.2.8).

    Implements IBridgePort structurally:
      - async send_command(operation, payload, *, trace_id, timeout_ms) -> BridgeCommandResult
      - async query(operation, selectors, *, trace_id, timeout_ms) -> BridgeCommandResult
      - async route_ifl(route, payload, *, trace_id) -> BridgeCommandResult
      - is_available() -> bool
      - get_health() -> BridgeHealth

    Lifecycle:
      - ``reconnect()`` -- attempt to (re-)establish connection
      - ``disconnect()`` -- cleanly close the connection
      - ``config`` -- read-only access to BridgeConnectionConfig

    The adapter starts in LOCAL COLD mode.  When a bridge client is
    provided and connected, operations route through it.  Otherwise
    all operations return graceful offline fallback responses.
    """

    def __init__(
        self,
        *,
        config: Optional[BridgeConnectionConfig] = None,
        client: Any = None,
    ) -> None:
        self._config = config or BridgeConnectionConfig()
        self._client = client
        self._connected = False
        self._last_reconnect_ms = 0
        self._reconnect_attempts = 0
        self._health = _OFFLINE_HEALTH
        self._lock = threading.RLock()

        # Probe on init if client provided
        if client is not None:
            self._probe_connection()

    @property
    def config(self) -> BridgeConnectionConfig:
        """Read-only configuration."""
        return self._config

    # -- Protocol methods --------------------------------------------------

    async def send_command(
        self,
        operation: str,
        payload: Dict[str, Any],
        *,
        trace_id: str = "",
        timeout_ms: int = 0,
    ) -> BridgeCommandResult:
        """Send a command to K0 via the Bridge."""
        if not self.is_available():
            return self._offline_result(trace_id)

        effective_timeout = timeout_ms or self._config.default_timeout_ms

        try:
            data = await self._client.send(operation, payload, trace_id, effective_timeout)
            return BridgeCommandResult.ok(
                data=data if isinstance(data, dict) else {},
                trace_id=trace_id,
            )
        except Exception as exc:
            logger.warning(
                "Bridge send_command failed: operation=%s error=%s",
                operation,
                exc,
            )
            self._mark_disconnected(str(exc))
            return BridgeCommandResult.fail(
                "bridge_error",
                str(exc),
                k0_mode="K0_OFFLINE",
                trace_id=trace_id,
            )

    async def query(
        self,
        operation: str,
        selectors: Dict[str, Any],
        *,
        trace_id: str = "",
        timeout_ms: int = 0,
    ) -> BridgeCommandResult:
        """Query K0 via the Bridge."""
        if not self.is_available():
            return self._offline_result(trace_id)

        effective_timeout = timeout_ms or self._config.default_timeout_ms

        try:
            data = await self._client.query(operation, selectors, trace_id, effective_timeout)
            return BridgeCommandResult.ok(
                data=data if isinstance(data, dict) else {},
                trace_id=trace_id,
            )
        except Exception as exc:
            logger.warning(
                "Bridge query failed: operation=%s error=%s",
                operation,
                exc,
            )
            self._mark_disconnected(str(exc))
            return BridgeCommandResult.fail(
                "bridge_error",
                str(exc),
                k0_mode="K0_OFFLINE",
                trace_id=trace_id,
            )

    async def route_ifl(
        self,
        route: IFLRoute,
        payload: Dict[str, Any],
        *,
        trace_id: str = "",
    ) -> BridgeCommandResult:
        """Route an IFL tool call via the Bridge."""
        if not self.is_available():
            return self._offline_result(trace_id)

        try:
            data = await self._client.route_ifl(route.address, payload, trace_id)
            return BridgeCommandResult.ok(
                data=data if isinstance(data, dict) else {},
                trace_id=trace_id,
            )
        except Exception as exc:
            logger.warning(
                "Bridge route_ifl failed: address=%s error=%s",
                route.address,
                exc,
            )
            self._mark_disconnected(str(exc))
            return BridgeCommandResult.fail(
                "bridge_error",
                str(exc),
                k0_mode="K0_OFFLINE",
                trace_id=trace_id,
            )

    def is_available(self) -> bool:
        """True only if Bridge client is connected and healthy."""
        with self._lock:
            return self._connected

    def get_health(self) -> BridgeHealth:
        """Return current K0 health as observed through the Bridge."""
        with self._lock:
            return self._health

    # -- Lifecycle ---------------------------------------------------------

    async def reconnect(self) -> bool:
        """
        Attempt to (re-)establish Bridge connection.

        Respects ``reconnect_interval_ms`` throttle.
        Returns True if connection succeeded.
        """
        now_ms = int(time.time() * 1000)

        with self._lock:
            # Throttle reconnect attempts
            elapsed = now_ms - self._last_reconnect_ms
            if elapsed < self._config.reconnect_interval_ms:
                return self._connected

            # Check max attempts
            if (
                self._config.max_reconnect_attempts > 0
                and self._reconnect_attempts >= self._config.max_reconnect_attempts
            ):
                return False

            self._last_reconnect_ms = now_ms
            self._reconnect_attempts += 1

        if self._client is None:
            return False

        try:
            result = await self._client.connect()
            if result:
                self._mark_connected()
                return True
            return False
        except Exception as exc:
            logger.warning("Bridge reconnect failed: %s", exc)
            return False

    async def disconnect(self) -> None:
        """Cleanly close the Bridge connection."""
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception as exc:
                logger.warning("Bridge disconnect error: %s", exc)

        self._mark_disconnected("Disconnected by request")

    # -- Internals ---------------------------------------------------------

    def _probe_connection(self) -> None:
        """Check if client is already connected on init."""
        try:
            if hasattr(self._client, "is_connected") and self._client.is_connected():
                self._mark_connected()
        except Exception:
            pass  # Leave as offline

    def _mark_connected(self) -> None:
        """Update state to connected."""
        with self._lock:
            self._connected = True
            self._reconnect_attempts = 0

            # Try to get health from client
            health_dict = {}
            try:
                if hasattr(self._client, "get_health"):
                    health_dict = self._client.get_health()
            except Exception:
                pass

            self._health = BridgeHealth(
                available=True,
                mode=health_dict.get("mode", "K0_FULL"),
                last_heartbeat_ms=int(time.time() * 1000),
                latency_ms=health_dict.get("latency_ms", 0),
            )

    def _mark_disconnected(self, error_message: str) -> None:
        """Update state to disconnected."""
        with self._lock:
            self._connected = False
            self._health = BridgeHealth(
                available=False,
                mode="K0_OFFLINE",
                error_message=error_message,
            )

    @staticmethod
    def _offline_result(trace_id: str) -> BridgeCommandResult:
        """Standard offline fallback response."""
        return BridgeCommandResult.fail(
            _OFFLINE_FAIL_CODE,
            _OFFLINE_FAIL_MSG,
            k0_mode="K0_OFFLINE",
            trace_id=trace_id,
        )

    def __repr__(self) -> str:
        with self._lock:
            return (
                f"BridgeConnectionAdapter("
                f"connected={self._connected}, "
                f"endpoint={self._config.endpoint!r}, "
                f"mode={self._health.mode!r})"
            )
