"""
K0 Kernel Python SDK Client

Black-box HTTP client for K0 kernel ports. Designed for:
- E2E testing (Ward integration tests)
- External service integration
- Demonstration and exploration

All interactions use public HTTP APIs only—no internal imports.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, Iterator, Optional, cast
from urllib.parse import urljoin
from uuid import uuid4

import httpx
from httpx_sse import aconnect_sse


@dataclass
class K0Response:
    """Unified response wrapper for all K0 operations."""

    status_code: int
    """HTTP status code."""

    body: Optional[Dict[str, Any]] = None
    """Parsed JSON body (if applicable)."""

    headers: Dict[str, str] = field(default_factory=dict)
    """Response headers."""

    raw_content: bytes = b""
    """Raw response bytes."""

    @property
    def ok(self) -> bool:
        """True if status code indicates success (2xx)."""
        return 200 <= self.status_code < 300

    @property
    def error(self) -> Optional[Dict[str, Any]]:
        """Extracts error envelope if present."""
        if self.body and "error" in self.body:
            return cast(Dict[str, Any], self.body["error"])
        return None

    def __repr__(self) -> str:
        return f"<K0Response status={self.status_code} ok={self.ok}>"


@dataclass
class CommandReceipt:
    """Receipt returned from command submission."""

    receipt_id: str
    idem_key: str
    wal_pos: int
    commit_ts: str
    device_id: str
    device_sig: str
    obligations: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_response(cls, response: K0Response) -> CommandReceipt:
        """Parse receipt from command.submit response."""
        if not response.ok or not response.body:
            raise ValueError(f"Cannot extract receipt from response: {response}")
        # Response body contains receipt fields directly at root level
        # Extract WAL position from offsets dict (take first value)
        offsets = response.body.get("offsets", {})
        wal_pos = next(iter(offsets.values())) if offsets else 0
        return cls(
            receipt_id=response.body["receipt_id"],
            idem_key=response.body["idem_key"],
            wal_pos=wal_pos,
            commit_ts=response.body["commit_ts"],
            device_id=response.body.get("device_id", ""),
            device_sig=response.body.get("device_sig", response.body.get("sig", "")),
            obligations=response.body.get("obligations", []),
        )


class K0Client:
    """
    Synchronous Python SDK for K0 Kernel.

    Example:
        >>> client = K0Client(base_url="http://localhost:8000")
        >>> response = client.submit_command(envelope={...})
        >>> if response.ok:
        ...     receipt = CommandReceipt.from_response(response)
        ...     print(f"Committed at WAL position {receipt.wal_pos}")
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
        headers: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize K0 client.

        Args:
            base_url: Base URL for K0 kernel (e.g., "http://localhost:8000")
            timeout: Default request timeout in seconds
            headers: Additional headers to include in all requests
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.default_headers = headers or {}
        self._client = httpx.Client(timeout=timeout)

    def __enter__(self) -> K0Client:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close underlying HTTP client."""
        self._client.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> K0Response:
        """Execute HTTP request and wrap response."""
        url = urljoin(self.base_url, path)
        request_headers = {**self.default_headers, **(headers or {})}

        try:
            response = self._client.request(
                method=method,
                url=url,
                json=json_data,
                headers=request_headers,
            )
            body = None
            if response.content:
                try:
                    body = response.json()
                except Exception:
                    pass

            return K0Response(
                status_code=response.status_code,
                body=body,
                headers=dict(response.headers),
                raw_content=response.content,
            )
        except httpx.RequestError as exc:
            raise ConnectionError(f"Request to {url} failed: {exc}") from exc

    # === Command Port ===

    def submit_command(
        self,
        envelope: Dict[str, Any],
        *,
        trace_id: Optional[str] = None,
    ) -> K0Response:
        """
        Submit a command envelope to the kernel.

        Args:
            envelope: Command envelope (must include tenant_id, space_id, topic, body, schema, device_id, signature)
            trace_id: Optional cognitive_trace_id (generated if not provided)

        Returns:
            K0Response with receipt in body on success
        """
        if "cognitive_trace_id" not in envelope and trace_id:
            envelope["cognitive_trace_id"] = trace_id
        elif "cognitive_trace_id" not in envelope:
            envelope["cognitive_trace_id"] = str(uuid4())

        return self._request("POST", "/k0/command.submit", json_data=envelope)

    # === Query Port ===

    def query_recall(
        self,
        tenant_id: str,
        space_id: str,
        selectors: list[dict[str, Any]],
        *,
        trace_id: Optional[str] = None,
        fanout_hints: Optional[dict[str, Any]] = None,
        qos_hints: Optional[dict[str, Any]] = None,
    ) -> K0Response:
        """
        Execute a recall query against the kernel.

        Args:
            tenant_id: Tenant identifier
            space_id: Space identifier
            selectors: List of selector specifications
            trace_id: Optional cognitive_trace_id
            fanout_hints: Optional fanout configuration
            qos_hints: Optional QoS hints

        Returns:
            K0Response with bundle, trace, and budgets in body
        """
        payload: Dict[str, Any] = {
            "cognitive_trace_id": trace_id or str(uuid4()),
            "tenant_id": tenant_id,
            "space_id": space_id,
            "selectors": selectors,
        }
        if fanout_hints:
            payload["fanout_hints"] = fanout_hints
        if qos_hints:
            payload["qos_hints"] = qos_hints

        return self._request("POST", "/k0/query.recall", json_data=payload)

    # === SSE Port ===

    def sse_subscribe(
        self,
        tenant_id: str,
        space_id: str,
        topics: list[str],
        *,
        subscriber_id: Optional[str] = None,
        resume_from: Optional[int] = None,
    ) -> Iterator[Dict[str, Any]]:
        """
        Subscribe to SSE event stream (synchronous iterator).

        Args:
            tenant_id: Tenant identifier
            space_id: Space identifier
            topics: List of topics to subscribe to
            subscriber_id: Optional subscriber ID (generated if not provided)
            resume_from: Optional WAL position to resume from

        Yields:
            Parsed event data dictionaries

        Example:
            >>> for event in client.sse_subscribe("tenant-1", "space-main", ["ui.interaction"]):
            ...     print(event["wal_pos"], event["topic"])
        """
        params = {
            "tenant_id": tenant_id,
            "space_id": space_id,
            "topics": ",".join(topics),
        }
        if resume_from is not None:
            params["cursor_token"] = str(resume_from)

        # Subscriber ID goes in header, not query params
        headers = {}
        if subscriber_id:
            headers["X-SSE-Subscriber"] = subscriber_id

        url = urljoin(self.base_url, "/k0/sse.subscribe")

        with self._client.stream(
            "GET", url, params=params, headers=headers
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]  # Strip "data: " prefix
                    try:
                        yield json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

    def sse_ack(
        self,
        subscriber_id: str,
        topic: str,
        space_id: str,
        tenant_id: str,
        offset: int,
        *,
        ack_ts: Optional[str] = None,
    ) -> K0Response:
        """
        Acknowledge receipt of SSE events up to a given offset.

        Args:
            subscriber_id: Subscriber identifier
            topic: Topic being acknowledged
            space_id: Space identifier
            tenant_id: Tenant identifier
            offset: WAL offset to acknowledge
            ack_ts: Optional acknowledgment timestamp (ISO 8601, generated if not provided)

        Returns:
            K0Response (204 No Content on success)
        """
        payload = {
            "subscriber_id": subscriber_id,
            "topic": topic,
            "space_id": space_id,
            "tenant_id": tenant_id,
            "offset": offset,
            "ack_ts": ack_ts or datetime.now(timezone.utc).isoformat(),
        }
        return self._request("POST", "/k0/sse.ack", json_data=payload)

    # === Observability Port ===

    def health(self) -> K0Response:
        """
        Check kernel liveness.

        Returns:
            K0Response with status (200 = alive)
        """
        return self._request("GET", "/healthz")

    def readiness(self) -> K0Response:
        """
        Check kernel readiness (migrations complete, WAL replay done).

        Returns:
            K0Response with status (200 = ready)
        """
        return self._request("GET", "/readyz")

    def metrics(self) -> K0Response:
        """
        Retrieve Prometheus metrics.

        Returns:
            K0Response with raw_content containing Prometheus text format
        """
        return self._request("GET", "/metrics")

    # === Helpers ===

    def wait_for_ready(self, max_attempts: int = 30, interval: float = 1.0) -> bool:
        """
        Poll readiness endpoint until ready or max attempts exhausted.

        Args:
            max_attempts: Maximum polling attempts
            interval: Seconds between attempts

        Returns:
            True if kernel became ready, False otherwise
        """
        import time

        for _ in range(max_attempts):
            try:
                response = self.readiness()
                if response.ok:
                    return True
            except Exception:
                pass
            time.sleep(interval)
        return False


class K0AsyncClient:
    """
    Async Python SDK for K0 Kernel.

    Provides async/await interface for non-blocking operations.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.default_headers = headers or {}
        self._client = httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self) -> K0AsyncClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close underlying HTTP client."""
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> K0Response:
        """Execute async HTTP request."""
        url = urljoin(self.base_url, path)
        request_headers = {**self.default_headers, **(headers or {})}

        try:
            response = await self._client.request(
                method=method,
                url=url,
                json=json_data,
                headers=request_headers,
            )
            body = None
            if response.content:
                try:
                    body = response.json()
                except Exception:
                    pass

            return K0Response(
                status_code=response.status_code,
                body=body,
                headers=dict(response.headers),
                raw_content=response.content,
            )
        except httpx.RequestError as exc:
            raise ConnectionError(f"Request to {url} failed: {exc}") from exc

    async def submit_command(
        self,
        envelope: Dict[str, Any],
        *,
        trace_id: Optional[str] = None,
    ) -> K0Response:
        """Async command submission."""
        if "cognitive_trace_id" not in envelope and trace_id:
            envelope["cognitive_trace_id"] = trace_id
        elif "cognitive_trace_id" not in envelope:
            envelope["cognitive_trace_id"] = str(uuid4())

        return await self._request("POST", "/k0/command.submit", json_data=envelope)

    async def query_recall(
        self,
        tenant_id: str,
        space_id: str,
        selectors: list[dict[str, Any]],
        *,
        trace_id: Optional[str] = None,
        fanout_hints: Optional[dict[str, Any]] = None,
        qos_hints: Optional[dict[str, Any]] = None,
    ) -> K0Response:
        """Async query recall."""
        payload: Dict[str, Any] = {
            "cognitive_trace_id": trace_id or str(uuid4()),
            "tenant_id": tenant_id,
            "space_id": space_id,
            "selectors": selectors,
        }
        if fanout_hints:
            payload["fanout_hints"] = fanout_hints
        if qos_hints:
            payload["qos_hints"] = qos_hints

        return await self._request("POST", "/k0/query.recall", json_data=payload)

    async def sse_subscribe(
        self,
        tenant_id: str,
        space_id: str,
        topics: list[str],
        *,
        subscriber_id: Optional[str] = None,
        resume_from: Optional[int] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Async SSE subscription."""
        params = {
            "tenant_id": tenant_id,
            "space_id": space_id,
            "topics": ",".join(topics),
        }
        if subscriber_id:
            params["subscriber_id"] = subscriber_id
        if resume_from is not None:
            params["resume_from"] = str(resume_from)

        url = urljoin(self.base_url, "/k0/sse.subscribe")

        async with aconnect_sse(
            self._client, "GET", url, params=params
        ) as event_source:
            async for sse in event_source.aiter_sse():
                if sse.data:
                    try:
                        yield json.loads(sse.data)
                    except json.JSONDecodeError:
                        continue

    async def sse_ack(
        self,
        subscriber_id: str,
        topic: str,
        space_id: str,
        tenant_id: str,
        offset: int,
        *,
        ack_ts: Optional[str] = None,
    ) -> K0Response:
        """Async SSE acknowledgment."""
        payload = {
            "subscriber_id": subscriber_id,
            "topic": topic,
            "space_id": space_id,
            "tenant_id": tenant_id,
            "offset": offset,
            "ack_ts": ack_ts or datetime.now(timezone.utc).isoformat(),
        }
        return await self._request("POST", "/k0/sse.ack", json_data=payload)

    async def health(self) -> K0Response:
        """Async health check."""
        return await self._request("GET", "/healthz")

    async def readiness(self) -> K0Response:
        """Async readiness check."""
        return await self._request("GET", "/readyz")

    async def metrics(self) -> K0Response:
        """Async metrics retrieval."""
        return await self._request("GET", "/metrics")
