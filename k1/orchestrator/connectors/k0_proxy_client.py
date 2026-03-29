"""
k1.orchestrator.connectors.k0_proxy_client -- K0 Connector Proxy Client (5.1.4).

Optional client for routing MCP tool invocations through the K0 proxy.

The K0 proxy provides:
  - Auth token injection from K0 credential vault.
  - Rate limiting aggregation (K0 enforces per-account limits
    across all K1 instances).
  - Response caching (K0 caches for configured TTL).

This client is OPTIONAL:
  - Entirely absent in standalone / edge mode (``proxy_endpoint=None``).
  - When unavailable, Fabric's MCPProvider falls back to direct invoke.
  - Auth tokens are managed by K0, never stored in K1 (security boundary).
  - K1 does NOT implement its own MCP response cache (K0 owns caching).

Constructor:
  K0ProxyClient(bridge, proxy_endpoint)

References:
  - Issue 5.1.4 in orchestrator-implementation-plan.md
  - Edge-First architecture (K0 is optional)
  - IBridgeWritePort for token refresh requests

Exports:
  K0ProxyClient
  ProxyRequest
  ProxyResponse
  ProxyUnavailableError
  ProxyRateLimitedError
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProxyRequest:
    """
    Request to invoke an MCP tool via the K0 proxy.

    Attributes:
        server_id: The MCP server that owns the tool.
        tool_name: The tool to invoke.
        params: Tool invocation parameters.
        auth_context: Optional authentication context (opaque to K1;
            K0 proxy uses this to select the right credential vault).
    """

    server_id: str
    tool_name: str
    params: Dict[str, Any] = field(default_factory=dict)
    auth_context: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class ProxyResponse:
    """
    Response from a K0-proxied MCP tool invocation.

    Attributes:
        data: Tool result payload.
        cached: Whether the response was served from K0 cache.
        cache_ttl_s: Time-to-live of the cache entry in seconds.
            0 if not cached.
    """

    data: Dict[str, Any] = field(default_factory=dict)
    cached: bool = False
    cache_ttl_s: int = 0


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ProxyUnavailableError(RuntimeError):
    """
    Raised when the K0 proxy is not configured.

    Callers should catch this and fall back to direct MCP invocation.
    """


class ProxyRateLimitedError(RuntimeError):
    """
    Raised when K0 proxy returns HTTP 429 (rate limited).

    Attributes:
        retry_after_s: Seconds to wait before retrying.
    """

    def __init__(self, retry_after_s: float, message: str = "") -> None:
        self.retry_after_s = retry_after_s
        super().__init__(message or f"Rate limited; retry after {retry_after_s}s")


# ---------------------------------------------------------------------------
# HTTP Transport protocol (injectable for testing)
# ---------------------------------------------------------------------------


class IProxyTransport:
    """
    Protocol for K0 proxy HTTP communication.

    Abstracts actual HTTP calls.  Production: aiohttp / httpx.
    Tests: fake that returns canned responses.
    """

    async def post(
        self,
        url: str,
        body: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        POST JSON to the K0 proxy.

        Returns:
            Response dict with at minimum:
              - ``status``: HTTP status code (int)
              - ``body``: Response body (dict)
              - ``headers``: Response headers (dict)

        Raises:
            Exception on transport errors (timeout, DNS, etc.).
        """
        ...  # pragma: no cover

    async def get(
        self,
        url: str,
    ) -> Dict[str, Any]:
        """
        GET from the K0 proxy (for health checks).

        Returns:
            Response dict with ``status`` and ``body`` keys.
        """
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# 5.1.4 -- K0ProxyClient
# ---------------------------------------------------------------------------


class K0ProxyClient:
    """
    Optional client for K0 proxy MCP invocations.

    When ``proxy_endpoint`` is None, the client is disabled and
    ``invoke_via_proxy()`` raises ``ProxyUnavailableError``
    (caller falls back to direct MCP invoke).

    When available, routes MCP tool invocations through the K0
    proxy which handles auth, rate limiting, and caching.

    Constructor Args:
        bridge: IBridgeWritePort for token refresh requests on 401.
        proxy_endpoint: K0 proxy base URL, or None to disable.
        transport: IProxyTransport for HTTP communication. If None,
            a default (stub) is used.

    Thread Safety:
        Stateless per call -- safe for concurrent use.
    """

    __slots__ = ("_bridge", "_proxy_endpoint", "_transport")

    def __init__(
        self,
        bridge: Any,  # IBridgeWritePort
        proxy_endpoint: Optional[str] = None,
        transport: Optional[IProxyTransport] = None,
    ) -> None:
        self._bridge = bridge
        self._proxy_endpoint = proxy_endpoint
        self._transport = transport

    # ==================================================================
    # Public API
    # ==================================================================

    def is_available(self) -> bool:
        """
        Check if the K0 proxy is configured.

        Returns:
            True if ``proxy_endpoint`` was provided, False otherwise.
        """
        return self._proxy_endpoint is not None

    async def check_proxy_health(self) -> bool:
        """
        Lightweight health check against the K0 proxy.

        Sends GET to ``{proxy_endpoint}/health``.

        Returns:
            True if proxy responds with 200, False otherwise.
            False if proxy is not configured or transport is unavailable.
        """
        if not self.is_available():
            return False

        if self._transport is None:
            return False

        try:
            resp = await self._transport.get(f"{self._proxy_endpoint}/health")
            return resp.get("status", 0) == 200
        except Exception as exc:
            logger.warning("K0 proxy health check failed: %s", exc)
            return False

    async def invoke_via_proxy(
        self,
        request: ProxyRequest,
    ) -> ProxyResponse:
        """
        Invoke an MCP tool via the K0 proxy.

        K0 proxy handles:
          - Auth token injection from K0 credential vault.
          - Rate limiting aggregation across K1 instances.
          - Response caching with configurable TTL.

        Args:
            request: ProxyRequest with server_id, tool_name, params.

        Returns:
            ProxyResponse with data, cached flag, and cache TTL.

        Raises:
            ProxyUnavailableError: If proxy is not configured.
            ProxyRateLimitedError: If K0 returns HTTP 429.
            RuntimeError: On unexpected proxy errors.
        """
        if not self.is_available():
            raise ProxyUnavailableError("K0 proxy not configured (standalone/edge mode)")

        if self._transport is None:
            raise ProxyUnavailableError("No transport configured for K0 proxy")

        url = f"{self._proxy_endpoint}/mcp/invoke"
        body = {
            "server_id": request.server_id,
            "tool_name": request.tool_name,
            "params": request.params,
        }
        if request.auth_context is not None:
            body["auth_context"] = request.auth_context

        try:
            resp = await self._transport.post(url, body)
        except Exception as exc:
            raise RuntimeError(f"K0 proxy invocation failed: {exc}") from exc

        status = resp.get("status", 0)
        resp_body = resp.get("body", {})
        resp_headers = resp.get("headers", {})

        # Handle 401 -- trigger token refresh via bridge
        if status == 401:
            logger.warning(
                "K0 proxy returned 401 for server '%s'; " "triggering token refresh via bridge",
                request.server_id,
            )
            try:
                await self._bridge.submit_audit(
                    {
                        "type": "token_refresh_request",
                        "server_id": request.server_id,
                        "reason": "proxy_401",
                    },
                    trace_id=f"token-refresh-{request.server_id}",
                )
            except Exception as exc:
                logger.warning("Token refresh request failed: %s", exc)

            raise RuntimeError(f"K0 proxy returned 401 for server '{request.server_id}'")

        # Handle 429 -- rate limited
        if status == 429:
            retry_after = float(resp_headers.get("Retry-After", resp_body.get("retry_after_s", 60)))
            raise ProxyRateLimitedError(
                retry_after_s=retry_after,
                message=(
                    f"K0 proxy rate limited for server '{request.server_id}'; "
                    f"retry after {retry_after}s"
                ),
            )

        # Handle other errors
        if status >= 400:
            raise RuntimeError(
                f"K0 proxy returned {status} for server '{request.server_id}': " f"{resp_body}"
            )

        # Success
        return ProxyResponse(
            data=resp_body.get("data", resp_body),
            cached=resp_body.get("cached", False),
            cache_ttl_s=int(resp_body.get("cache_ttl_s", 0)),
        )
