"""K0 Query Port client (read operations).

This module implements the query bridge between K1 and K0, posting recall
requests to ``/k0/query.recall`` and interpreting the multi-store response per
ADR-0001a (K0 Bridge Communication Protocol). Latency targets follow ADR-0024
(<100ms P95). Observability is emitted through the shared K0 observability
stack so traces and metrics include the originating ``cognitive_trace_id``.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

from k1.l5_infrastructure.bridge_k0.http2 import HTTP2ConnectionManager, K0Port
from k1.l5_infrastructure.observability import get_metrics, get_tracer

try:  # pragma: no cover - structlog is optional
    import structlog  # type: ignore

    logger = structlog.get_logger(__name__)  # type: ignore
except ImportError:  # pragma: no cover - fallback to stdlib logging
    import logging

    logger = logging.getLogger(__name__)

__all__ = [
    "RecallSelector",
    "RecallRequest",
    "RecallSelectorResult",
    "RecallResponseBundle",
    "K0QueryClient",
    "K0QueryError",
    "K0QueryRejected",
    "K0QueryPolicyDenied",
    "K0QueryQoSExhausted",
    "K0QueryUnavailable",
]


_metrics = get_metrics()
_tracer = get_tracer()

query_requests_total = _metrics.counter(
    "query_requests_total",
    "Total K0 query recall requests issued by K1",
    labelnames=["fusion_strategy", "status"],
)

query_latency_ms = _metrics.histogram(
    "query_latency_ms",
    "Latency of K0 query recall requests (ms)",
    labelnames=["fusion_strategy"],
    buckets=[10, 25, 50, 75, 100, 200, 500, 1000, 2000],
)

query_results_total = _metrics.counter(
    "query_results_total",
    "Total recall results returned per driver",
    labelnames=["driver"],
)


class K0QueryError(Exception):
    """Base exception for K0 Query Port failures."""


class K0QueryRejected(K0QueryError):
    """Raised when K0 rejects a request (HTTP 400)."""

    def __init__(self, *, reason: str, component: str) -> None:
        super().__init__(f"K0 rejected recall request: {reason} ({component})")
        self.reason = reason
        self.component = component


class K0QueryPolicyDenied(K0QueryError):
    """Raised when policy enforcement denies the request (HTTP 403)."""

    def __init__(self, *, reason: str) -> None:
        super().__init__(f"K0 policy denied recall request: {reason}")
        self.reason = reason


class K0QueryQoSExhausted(K0QueryError):
    """Raised when QoS budgets are exhausted (HTTP 429)."""

    def __init__(self, *, cap: str, reason: str, budgets: Dict[str, Any]) -> None:
        detail = f"QoS budget exhausted ({cap}): {reason}"
        super().__init__(detail)
        self.cap = cap
        self.reason = reason
        self.budgets = budgets


class K0QueryUnavailable(K0QueryError):
    """Raised when K0 is unavailable or a transport error occurs."""

    def __init__(self, *, status_code: int, detail: str) -> None:
        super().__init__(f"K0 query port unavailable: {status_code} - {detail}")
        self.status_code = status_code
        self.detail = detail


@dataclass(slots=True)
class RecallSelector:
    """Selector parameters mirroring the K0 query recall schema."""

    type: Optional[str] = None
    topic: Optional[str] = None
    limit: int = 20
    query: Optional[str] = None
    cursor: Optional[int] = None
    after: Optional[int] = None
    tenant_id: Optional[str] = None
    space_id: Optional[str] = None
    extras: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.limit <= 0 or self.limit > 256:
            msg = "selector limit must be between 1 and 256"
            raise ValueError(msg)

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "type": self.type,
            "topic": self.topic,
            "limit": self.limit,
            "query": self.query,
            "cursor": self.cursor,
            "after": self.after,
            "tenant_id": self.tenant_id,
            "space_id": self.space_id,
        }
        payload.update({k: v for k, v in self.extras.items() if v is not None})
        return {k: v for k, v in payload.items() if v is not None}


@dataclass(slots=True)
class RecallRequest:
    """Request envelope sent to K0's query recall port."""

    selectors: List[RecallSelector]
    space_id: str
    tenant_id: Optional[str] = None
    max_latency_ms: int = 100
    fanout_hints: Optional[Dict[str, Any]] = None
    qos_hints: Optional[Dict[str, Any]] = None
    fail_fast: bool = False
    fusion_strategy: str = "mmr"
    top_k: Optional[int] = None
    cognitive_trace_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.selectors:
            msg = "at least one selector is required"
            raise ValueError(msg)
        for selector in self.selectors:
            if selector.space_id and selector.space_id != self.space_id:
                msg = "selector space_id must match request space_id"
                raise ValueError(msg)
        if self.max_latency_ms <= 0:
            msg = "max_latency_ms must be positive"
            raise ValueError(msg)
        if self.top_k is not None and self.top_k <= 0:
            msg = "top_k must be positive when provided"
            raise ValueError(msg)
        strategy = self.fusion_strategy.lower().strip()
        if strategy not in {"mmr", "rrf"}:
            msg = "fusion_strategy must be 'mmr' or 'rrf'"
            raise ValueError(msg)
        self.fusion_strategy = strategy

    def to_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "selectors": [selector.to_payload() for selector in self.selectors],
            "space_id": self.space_id,
            "max_latency_ms": self.max_latency_ms,
            "fail_fast": self.fail_fast,
            "fusion": {"strategy": self.fusion_strategy.upper()},
        }
        if self.tenant_id:
            payload["tenant_id"] = self.tenant_id
        if self.fanout_hints:
            payload["fanout_hints"] = dict(self.fanout_hints)
        merged_qos: Dict[str, Any] = dict(self.qos_hints or {})
        if self.top_k is not None:
            merged_qos.setdefault("top_k", self.top_k)
        if merged_qos:
            payload["qos_hints"] = merged_qos
        return payload


@dataclass(slots=True)
class RecallSelectorResult:
    """Normalized selector result returned by K0."""

    driver: str
    selector: Dict[str, Any]
    items: List[Dict[str, Any]]
    next_cursor: Optional[int]
    latency_ms: float
    metadata: Dict[str, Any]

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "RecallSelectorResult":
        selector_section = dict(payload.get("selector", {}))
        metadata = dict(payload.get("metadata", {}))
        driver = selector_section.get("driver") or metadata.get("driver") or "unknown"
        return cls(
            driver=str(driver),
            selector=selector_section,
            items=list(payload.get("items", [])),
            next_cursor=payload.get("next_cursor"),
            latency_ms=float(payload.get("latency_ms", 0.0)),
            metadata=metadata,
        )


@dataclass(slots=True)
class RecallResponseBundle:
    """Structured recall response with helper accessors."""

    selectors: List[RecallSelectorResult]
    trace: Dict[str, Any]
    budgets: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "selectors": [
                {
                    "driver": selector.driver,
                    "selector": selector.selector,
                    "items": selector.items,
                    "next_cursor": selector.next_cursor,
                    "latency_ms": selector.latency_ms,
                    "metadata": selector.metadata,
                }
                for selector in self.selectors
            ],
            "trace": dict(self.trace),
            "budgets": dict(self.budgets),
        }

    def results_by_driver(self) -> Dict[str, List[RecallSelectorResult]]:
        grouped: Dict[str, List[RecallSelectorResult]] = {}
        for selector in self.selectors:
            grouped.setdefault(selector.driver, []).append(selector)
        return grouped


class K0QueryClient:
    """Async client for K0's query recall port."""

    def __init__(
        self,
        base_url: str = "http://localhost:5201",
        *,
        timeout: float = 10.0,
        connection_manager: Optional[HTTP2ConnectionManager] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        # HTTP/2 Connection Manager (ADR-0044, ADR-0044a)
        if connection_manager is None:
            import re

            match = re.match(r"^https?://([^:]+)", base_url)
            k0_host = match.group(1) if match else "localhost"
            use_tls = base_url.startswith("https://")

            self._connection_manager = HTTP2ConnectionManager(
                k0_base_url=k0_host,
                command_port=5200,
                query_port=5201,
                sse_port=5202,
                obs_port=5203,
                timeout=timeout,
                use_tls=use_tls,
            )
            self._own_connection_manager = True
        else:
            self._connection_manager = connection_manager
            self._own_connection_manager = False

        logger.info("k0_query_client_initialized", base_url=self.base_url)

    async def close(self) -> None:
        if self._own_connection_manager:
            await self._connection_manager.stop()
        logger.info("k0_query_client_closed")

    async def recall(self, request: RecallRequest) -> RecallResponseBundle:
        start_time = time.time()
        fusion_label = request.fusion_strategy
        status_label = "success"
        trace_id = request.cognitive_trace_id or _tracer.new_trace_id()
        token = _tracer.attach_cognitive_trace(trace_id)

        try:
            with _tracer.span(
                "k1.query_recall",
                attributes={
                    "space_id": request.space_id,
                    "tenant_id": request.tenant_id or "",
                    "fusion_strategy": fusion_label,
                    "selector_count": len(request.selectors),
                },
            ):
                payload = request.to_payload()
                headers = {
                    "Content-Type": "application/json",
                    "X-Cognitive-Trace-Id": trace_id,
                    "X-Fusion-Strategy": request.fusion_strategy.upper(),
                }
                _tracer.inject(headers)

                # Use HTTP/2 connection manager for consistent connection pooling
                async with self._connection_manager.get_client(
                    K0Port.QUERY, trace_id=trace_id
                ) as client:
                    response = await client.post(
                        f"{self.base_url}/k0/query.recall",
                        json=payload,
                        headers=headers,
                    )

                bundle = await self._process_response(response, trace_id)
        except K0QueryError as exc:
            status_label = "error"
            logger.error(
                "k0_query_failed",
                cognitive_trace_id=trace_id,
                error=str(exc),
            )
            raise
        except httpx.RequestError as exc:
            status_label = "unavailable"
            logger.error(
                "k0_query_network_error",
                cognitive_trace_id=trace_id,
                error=str(exc),
            )
            raise K0QueryUnavailable(status_code=503, detail=str(exc)) from exc
        finally:
            _tracer.detach(token)
            elapsed_ms = (time.time() - start_time) * 1000
            query_requests_total.labels(
                fusion_strategy=fusion_label, status=status_label
            ).inc()
            query_latency_ms.labels(fusion_strategy=fusion_label).observe(elapsed_ms)

        for selector in bundle.selectors:
            query_results_total.labels(driver=selector.driver).inc(len(selector.items))

        logger.info(
            "k0_query_success",
            cognitive_trace_id=trace_id,
            fusion_strategy=fusion_label,
            latency_ms=round((time.time() - start_time) * 1000, 2),
            selectors=len(bundle.selectors),
        )
        return bundle

    async def _process_response(
        self, response: httpx.Response, trace_id: str
    ) -> RecallResponseBundle:
        if response.status_code == 200:
            content_type = (response.headers.get("Content-Type") or "").lower()
            if "text/event-stream" in content_type:
                bundle_payload, trace_payload, budgets_payload = (
                    await self._parse_streaming_response(response)
                )
            else:
                data = response.json()
                bundle_payload = dict(data.get("bundle", {}))
                trace_payload = dict(data.get("trace", {}))
                budgets_payload = dict(data.get("budgets", {}))
            selectors_payload = bundle_payload.get("selectors", [])
            selectors = [
                RecallSelectorResult.from_payload(selector)
                for selector in selectors_payload
            ]
            return RecallResponseBundle(
                selectors=selectors,
                trace=trace_payload,
                budgets=budgets_payload,
            )

        if response.status_code == 400:
            error = response.json().get("error", {})
            raise K0QueryRejected(
                reason=error.get("reason", "UNKNOWN"),
                component=error.get("component", "kernel.query"),
            )
        if response.status_code == 403:
            error = response.json().get("error", {})
            raise K0QueryPolicyDenied(reason=error.get("reason", "UNKNOWN"))
        if response.status_code == 429:
            error = response.json().get("error", {})
            raise K0QueryQoSExhausted(
                cap=error.get("details", {}).get("cap", "unknown"),
                reason=error.get("reason", "UNKNOWN"),
                budgets=error.get("budgets", {}),
            )
        detail = response.text[:200]
        raise K0QueryUnavailable(status_code=response.status_code, detail=detail)

    async def _parse_streaming_response(
        self, response: httpx.Response
    ) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        bundle_selectors: List[Dict[str, Any]] = []
        trace_payload: Dict[str, Any] = {}
        budgets_payload: Dict[str, Any] = {}

        current_event: Optional[str] = None
        data_lines: List[str] = []

        async for line in response.aiter_lines():
            if line is None:
                continue
            stripped = line.strip()
            if not stripped:
                if current_event is not None:
                    self._apply_sse_event(
                        current_event,
                        "\n".join(data_lines).strip(),
                        bundle_selectors,
                        trace_payload,
                        budgets_payload,
                    )
                current_event = None
                data_lines = []
                continue
            if stripped.startswith(":"):
                continue
            if stripped.startswith("event:"):
                current_event = stripped[len("event:") :].strip()
                continue
            if stripped.startswith("data:"):
                data_lines.append(stripped[len("data:") :].strip())

        if current_event is not None:
            self._apply_sse_event(
                current_event,
                "\n".join(data_lines).strip(),
                bundle_selectors,
                trace_payload,
                budgets_payload,
            )

        await response.aclose()
        return (
            {"selectors": bundle_selectors},
            trace_payload,
            budgets_payload,
        )

    @staticmethod
    def _apply_sse_event(
        event: str,
        data: str,
        bundles: List[Dict[str, Any]],
        trace_payload: Dict[str, Any],
        budgets_payload: Dict[str, Any],
    ) -> None:
        if not data:
            return
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            logger.warning("k0_query_sse_invalid_json", event=event)
            return
        if event == "trace":
            trace_payload.update(payload)
        elif event == "selector":
            bundles.append(payload)
        elif event == "budgets":
            budgets_payload.update(payload)
        # "complete" events are informational and can be ignored here
