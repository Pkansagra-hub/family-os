"""HTTP transport for K0 command port communication.

Implements connection pooling, timeouts, and TLS configuration per
bridge/contracts/command_port.protocol.yaml transport section.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HttpResult:
    """Outcome of an HTTP request to K0."""

    status_code: int
    body: dict[str, Any] | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Transport configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TransportConfig:
    """Configuration for the K0 HTTP transport layer."""

    base_url: str = "http://localhost:8080"
    connect_timeout_s: float = 5.0
    read_timeout_s: float = 30.0
    tls_verify: bool = False
    max_keepalive_connections: int = 5
    max_connections: int = 10


# ---------------------------------------------------------------------------
# HttpTransport
# ---------------------------------------------------------------------------


class HttpTransport:
    """Async HTTP client for communicating with the K0 command port.

    Provides connection pooling, configurable timeouts, and a lightweight
    health-check endpoint.  Designed for reuse across the Bridge lifetime.
    """

    COMMAND_PATH = "/k0/command.submit"
    HEALTH_PATH = "/healthz"

    def __init__(self, config: TransportConfig | None = None) -> None:
        self._config = config or TransportConfig()
        self._client: httpx.AsyncClient | None = None

    # -- lifecycle -----------------------------------------------------------

    async def open(self) -> None:
        """Create the underlying ``httpx.AsyncClient`` with pooling."""
        if self._client is not None:
            return
        timeout = httpx.Timeout(
            connect=self._config.connect_timeout_s,
            read=self._config.read_timeout_s,
            write=self._config.read_timeout_s,
            pool=self._config.connect_timeout_s,
        )
        limits = httpx.Limits(
            max_keepalive_connections=self._config.max_keepalive_connections,
            max_connections=self._config.max_connections,
        )
        self._client = httpx.AsyncClient(
            base_url=self._config.base_url,
            timeout=timeout,
            limits=limits,
            verify=self._config.tls_verify,
        )

    async def close(self) -> None:
        """Shut down the HTTP client and release connections."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # -- public API ----------------------------------------------------------

    async def post_command(self, envelope_json: bytes) -> HttpResult:
        """POST an envelope to ``/k0/command.submit``.

        Returns:
            HttpResult with status code and parsed response body.
        """
        client = self._ensure_client()
        try:
            response = await client.post(
                self.COMMAND_PATH,
                content=envelope_json,
                headers={"Content-Type": "application/json"},
            )
            body = None
            try:
                body = response.json()
            except Exception:  # noqa: BLE001
                pass
            return HttpResult(status_code=response.status_code, body=body)
        except httpx.TimeoutException as exc:
            logger.warning("K0 command port timeout: %s", exc)
            return HttpResult(status_code=0, error=f"timeout: {exc}")
        except httpx.ConnectError as exc:
            logger.warning("K0 command port connection error: %s", exc)
            return HttpResult(status_code=0, error=f"connection_error: {exc}")
        except httpx.HTTPError as exc:
            logger.error("K0 command port HTTP error: %s", exc)
            return HttpResult(status_code=0, error=f"http_error: {exc}")

    async def check_health(self) -> bool:
        """Lightweight health probe against ``/healthz``.

        Returns True if K0 responds with 200, False on any failure.
        """
        client = self._ensure_client()
        try:
            response = await client.get(self.HEALTH_PATH)
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    # -- internals -----------------------------------------------------------

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            msg = "HttpTransport not opened. Call await transport.open() first."
            raise RuntimeError(msg)
        return self._client
