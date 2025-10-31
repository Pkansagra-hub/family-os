"""
Query Port Adapter - K0 Query Port (P01 RecallQuery)

Layer: L5 Infrastructure
Component: K0 Bridge → Query Port
Priority: P0 (Critical Path)
Status: 🚧 STUB - NEEDS_IMPLEMENTATION

Architecture Decision Records:
    - ADR-0001a: K0 Bridge Dual Protocol (JSON PRIMARY + FlatBuffers SECONDARY)
    - ADR-0001f: K0-K1 Pipeline Boundary (K1 NEVER implements lanes/multi-store retrieval)
    - ADR-0051: Maximal Marginal Relevance (MMR) fusion for multi-store results
    - ADR-0014: JSON REST API Dual Format (content negotiation)

CRITICAL ARCHITECTURAL BOUNDARY (ADR-0001f):
    ⚠️ K1 NEVER implements lanes or multi-store retrieval.
    ⚠️ K1 ONLY sends queries to K0 Query Port (P01).
    ⚠️ K0 P01 Pipeline handles all retrieval logic (FTS, Vector, KG, Episodic).
    ⚠️ K0 returns MMR-fused results (already ranked, deduplicated).

Dependencies:
    Internal:
        - k1.bridge_k0.http2_client.HTTP2Connection (transport)
        - k1.bridge_k0.protocol.ProtocolNegotiator (format switching)
    External:
        - None (no external dependencies)

Connects To:
    Upstream:
        - k1.l2_orchestration.orchestrator (query requests)
        - k1.l3_execution.agents (context retrieval)
    Downstream:
        - K0 Query Port: POST /k0/query (P01 RecallQuery)

Performance Budgets:
    - Query latency: <50ms P95 (K1 → K0 Query Port → results)
    - Payload size: <100KB per query response
    - Throughput: 100+ queries/sec per session

Observability:
    Metrics:
        - k1_k0_query_port_requests_total{lane, status} (counter)
        - k1_k0_query_port_latency_ms{lane, p50, p95, p99} (histogram)
        - k1_k0_query_port_result_count{lane, p50, p95, p99} (histogram)
    Traces:
        - Span: k0_bridge.query_port_query
        - Attributes: session_id, query_text, lane, stores, cognitive_trace_id
    Logs:
        - INFO: query executed (query_text, lane, result_count, latency_ms)
        - WARNING: query slow (latency_ms >100ms)
        - ERROR: query failed (reason, retry_attempt)

References:
    - Diagram: architecture_diagrams/k1/k1_complete_with_flows.mmd
    - Whiteboard: docs/whiteboard.md (Section: K0 Query Port P01)
    - Test: tests/k1/bridge_k0/ports/test_query_port.py
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from enum import Enum

# =============================================================================
# SECTION 1: IMPORTS
# =============================================================================
# Standard library imports
from typing import Any, Dict, List, Optional, Tuple

from k1.bridge_k0.http2_client import HTTP2Config, HTTP2Connection, HTTP2Response
from k1.bridge_k0.protocol import ProtocolConfig, ProtocolNegotiator, SerializationFormat

# Third-party imports
# None

# Observability (best-effort; fall back to no-ops if module not available)
try:  # pragma: no cover
    from k1.l5_infrastructure.observability import (  # type: ignore
        create_span,
        emit_counter,
        emit_gauge,
        emit_histogram,
    )
except (ModuleNotFoundError, ImportError):  # pragma: no cover
    def create_span(name: str, **_: object):  # type: ignore
        class _NullSpan:
            def __enter__(self) -> "_NullSpan":
                return self

            def __exit__(self, *_exc: object) -> None:
                return None

            def set_attribute(self, *_args: object, **_kwargs: object) -> None:
                return None

        return _NullSpan()

    def emit_counter(_name: str, _value: float = 1.0, _labels: Optional[Dict[str, Any]] = None) -> None:
        return None

    def emit_histogram(_name: str, _value: float, _labels: Optional[Dict[str, Any]] = None) -> None:
        return None

    def emit_gauge(_name: str, _value: float, _labels: Optional[Dict[str, Any]] = None) -> None:
        return None

# Configure module logger
logger = logging.getLogger(__name__)

# =============================================================================
# SECTION 2: CONSTANTS & CONFIGURATION
# =============================================================================

# TODO(@infrastructure-team): Load from k1/config/k0_bridge.yml (ADR-0001a)
# Assigned to: Issue #L5-1.2.2
DEFAULT_CONFIG = {
    "k0_host": "localhost",
    "k0_query_port": 8080,
    "endpoint": "/k0/query",  # K0 Query Port endpoint
    "timeout_ms": 5000,  # 5s timeout for query requests
    "max_results": 10,  # Max results per query
    "mmr_diversity": 0.5,  # MMR diversity parameter (0.0-1.0)
    "default_lane": "SMART",  # Default lane (SMART | FAST)
}

# =============================================================================
# SECTION 3: TYPE DEFINITIONS & ENUMS
# =============================================================================


class QueryLane(Enum):
    """Query lane selection (ADR-0001f)"""

    SMART = "SMART"  # Multi-store retrieval (FTS + Vector + KG + Episodic)
    FAST = "FAST"  # FTS-only retrieval (fast path)


class QueryStore(Enum):
    """Query store types (K0 P01 Pipeline)"""

    FTS = "FTS"  # Full-text search (BM25)
    VECTOR = "VECTOR"  # Vector similarity (cosine)
    KG = "KG"  # Knowledge graph (traversal)
    EPISODIC = "EPISODIC"  # Episodic memory (temporal)


@dataclass
class QueryRequest:
    """
    Query request payload for K0 Query Port.

    Fields:
        query: Query text (e.g., "What did I say about X?")
        lane: Query lane (SMART | FAST)
        privacy_band: Privacy band filter (GREEN | AMBER | RED)
        stores: List of stores to query (FTS, VECTOR, KG, EPISODIC)
        max_results: Max results to return (default: 10)
        mmr_diversity: MMR diversity parameter (0.0=relevance, 1.0=diversity)
        cognitive_trace_id: Trace ID for observability
    """

    query: str
    session_id: str
    query_type: str = "episodic"
    lane: QueryLane = QueryLane.SMART
    privacy_band: str = "GREEN"
    stores: Optional[List[QueryStore]] = None
    max_results: int = 10
    mmr_diversity: float = 0.5
    cursor: Optional[str] = None
    filters: Optional[Dict[str, Any]] = None
    cognitive_enhancements: Optional[Dict[str, Any]] = None
    cognitive_trace_id: Optional[str] = None

    def __post_init__(self):
        if self.stores is None:
            # Default: Query all stores in SMART lane
            if self.lane == QueryLane.SMART:
                self.stores = [
                    QueryStore.FTS,
                    QueryStore.VECTOR,
                    QueryStore.KG,
                    QueryStore.EPISODIC,
                ]
            else:
                self.stores = [QueryStore.FTS]  # FAST lane: FTS only


@dataclass
class QueryResult:
    """
    Query result from K0 Query Port (single result).

    Fields:
        rank: Result rank (1-based)
        store: Source store (FTS | VECTOR | KG | EPISODIC)
        text: Result text snippet
        score: Relevance score (0.0-1.0, higher = more relevant)
        source: Source field path (e.g., "turn[0].user_input")
        metadata: Additional metadata (dict)
    """

    rank: int
    store: QueryStore
    text: str
    score: float
    source: str
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class QueryResponse:
    """
    Query response from K0 Query Port.

    Fields:
        results: List of query results (MMR-fused, ranked)
        query_latency_ms: Query latency in milliseconds
        stores_queried: List of stores queried (FTS, VECTOR, KG, EPISODIC)
    """

    results: List[QueryResult]
    query_latency_ms: float
    stores_queried: List[QueryStore]
    total_count: int
    next_cursor: Optional[str] = None


# =============================================================================
# SECTION 4: CORE CLASSES
# =============================================================================


class QueryPort:
    """
    Adapter for K0 Query Port (P01 RecallQuery).

    Purpose:
        Sends queries to K0 Query Port, receives MMR-fused results from
        multiple stores (FTS, Vector, KG, Episodic), handles lane selection
        (SMART vs FAST), manages format negotiation (JSON vs FlatBuffers).

    CRITICAL BOUNDARY (ADR-0001f):
        K1 NEVER implements lanes or multi-store retrieval.
        K1 ONLY sends queries to K0 Query Port (P01).
        K0 P01 Pipeline handles all retrieval logic.

    Responsibilities:
        1. Send queries to K0 Query Port (POST /k0/query)
        2. Parse MMR-fused results (already ranked by K0)
        3. Format negotiation (JSON PRIMARY, FlatBuffers SECONDARY)
        4. Lane selection (SMART multi-store vs FAST FTS-only)
        5. Error handling (retries, circuit breaker integration)

    Lifecycle:
        INIT → CONNECTING → READY → [DEGRADED] → TERMINATED

    Thread Safety: Yes (async-safe)
    Async Safe: Yes (fully async/await compatible)

    Cognitive Trace:
        - Propagates cognitive_trace_id to K0 Query Port
        - Required for: query

    Performance Budget (P95):
        - Query latency: <50ms (K1 → K0 Query Port → results)
        - FAST lane: <20ms (FTS-only)
        - SMART lane: <50ms (multi-store + MMR fusion)

    Examples:
        >>> config = {'k0_host': 'localhost', 'k0_query_port': 8080}
        >>> query_port = QueryPort(config)
        >>> await query_port.initialize()
        >>>
        >>> # Execute query (SMART lane, multi-store)
        >>> request = QueryRequest(
        ...     query='What did I say about X?',
        ...     lane=QueryLane.SMART,
        ...     max_results=10,
        ...     cognitive_trace_id='trace_456'
        ... )
        >>> response = await query_port.query(request)
        >>> print(f'Found {len(response.results)} results in {response.query_latency_ms}ms')
        >>> await query_port.shutdown()

    References:
        - ADR-0001f: K0-K1 Pipeline Boundary (K1 NEVER implements retrieval)
        - ADR-0051: Maximal Marginal Relevance (MMR) fusion
        - Diagram: architecture_diagrams/k1/k1_complete_with_flows.mmd
    """

    def __init__(self, config: Dict[str, Any], protocol_config: Optional[ProtocolConfig] = None) -> None:
        """
        Initialize QueryPort adapter.

        Args:
            config: Configuration dict with K0 host, port, endpoints

        Raises:
            ValueError: If configuration is invalid
            TypeError: If config type is incorrect

        Side Effects:
            - Initializes internal state (connection pool, protocol negotiator)
            - Does NOT connect to K0 (call initialize() to connect)

        ADR: ADR-0001a (K0 Bridge Dual Protocol)
        Assigned to: Issue #L5-1.2.2
        """
        # TODO(@infrastructure-team): Implement initialization (ADR-0001a)
        # 1. Validate config (check k0_host, k0_query_port, endpoint)
        # 2. Initialize state machine (INIT → CONNECTING → READY)
        # 3. Initialize protocol negotiator (JSON vs FlatBuffers)
        merged_config = {**DEFAULT_CONFIG, **config}
        self.config = merged_config
        self.state = "INIT"  # State: INIT | CONNECTING | READY | DEGRADED | TERMINATED
        self._logger = logger
        self._http2_config = HTTP2Config(
            k0_host=merged_config["k0_host"],
            k0_port=merged_config["k0_query_port"],
        )
        self._http2_connection = HTTP2Connection(self._http2_config)
        self._protocol_negotiator = ProtocolNegotiator(
            ProtocolConfig() if protocol_config is None else protocol_config
        )
        self._shutdown_event = asyncio.Event()
        self._query_semaphore = asyncio.Semaphore(merged_config.get("max_concurrent_queries", 32))
        self._query_queue_depth = 0
        self._queue_lock = asyncio.Lock()
        emit_gauge("k1_k0_query_port_queue_depth", 0, {"lane": merged_config["default_lane"]})

    async def initialize(self) -> None:
        """
        Async initialization phase - connect to K0 Query Port.

        This method performs async setup (HTTP/2 connection, format negotiation).

        Raises:
            RuntimeError: If initialization fails
            ConnectionError: If cannot connect to K0 Query Port

        Lifecycle:
            Transitions: INIT → CONNECTING → READY

        ADR: ADR-0001a (K0 Bridge Dual Protocol)
        Assigned to: Issue #L5-1.2.2
        """
        if self.state != "INIT":
            raise RuntimeError("QueryPort already initialized")

        await self._http2_connection.connect()
        await self._protocol_negotiator.initialize()

        self.state = "READY"
        self._logger.info(
            "query_port_initialized",
            k0_host=self.config.get("k0_host"),
            k0_port=self.config.get("k0_query_port"),
            default_lane=self.config.get("default_lane"),
            max_results=self.config.get("max_results"),
        )

    async def query(self, request: QueryRequest) -> QueryResponse:
        """
        Execute query against K0 Query Port.

        This method sends query to K0 P01 Pipeline, receives MMR-fused results.

        Args:
            request: QueryRequest with query text, lane, stores, etc.

        Returns:
            QueryResponse with MMR-fused results (ranked by K0)

        Raises:
            ValueError: If request is invalid
            RuntimeError: If K0 Query Port unavailable

        Performance:
            - Target: <50ms P95 (SMART lane)
            - Target: <20ms P95 (FAST lane)

        Observability:
            - Metrics: k1_k0_query_port_requests_total{lane, status}
            - Traces: Span name: k0_bridge.query_port_query
            - Logs: INFO: query executed (query_text, lane, result_count)

        ADR: ADR-0001f (K0-K1 Pipeline Boundary)
        Assigned to: Issue #L5-1.2.2
        Depends on: K0 P01 Pipeline (multi-store retrieval + MMR fusion)
        """
        if self.state not in {"READY", "DEGRADED"}:
            raise RuntimeError("QueryPort is not ready")

        if not request.query:
            raise ValueError("query text must be provided")
        if request.max_results <= 0 or request.max_results > 100:
            raise ValueError("max_results must be within 1..100")

        if request.lane == QueryLane.SMART:
            target_lane = "SMART"
        elif request.lane == QueryLane.FAST:
            target_lane = "FAST"
        else:
            raise ValueError(f"Unsupported lane: {request.lane}")

        serialized_body, format_used = await self._serialize_request(request)
        headers = self._build_headers(request, format_used)

        query_labels = {
            "lane": target_lane,
            "status": "pending",
        }

        async with self._acquire_query_slot(target_lane):
            start_time = time.perf_counter()
            response = await self._dispatch_request(serialized_body, headers, request)
            latency_ms = (time.perf_counter() - start_time) * 1000

        emit_histogram("k1_k0_query_port_latency_ms", latency_ms, query_labels)
        emit_counter("k1_k0_query_port_requests_total", 1, {**query_labels, "status": str(response.status)})

        parsed_results, result_count, next_cursor, total_count, query_latency = self._parse_response(
            response,
            request,
        )

        emit_histogram(
            "k1_k0_query_port_result_count",
            float(result_count),
            {"lane": target_lane},
        )

        self._logger.info(
            "query_executed",
            query_text=request.query,
            lane=target_lane,
            result_count=result_count,
            latency_ms=round(query_latency, 2),
            trace_id=request.cognitive_trace_id,
        )

        return QueryResponse(
            results=parsed_results,
            query_latency_ms=query_latency,
            stores_queried=request.stores,
            total_count=total_count,
            next_cursor=next_cursor,
        )

    async def shutdown(self) -> None:
        """
        Graceful shutdown sequence.

        This method performs cleanup and state transitions.

        Lifecycle:
            - Close HTTP/2 connection
            - Finalize metrics

        ADR: ADR-0001a (K0 Bridge Dual Protocol)
        Assigned to: Issue #L5-1.2.2
        """
        if self.state == "TERMINATED":
            return

        self.state = "DEGRADED"
        self._shutdown_event.set()

        await self._http2_connection.close()

        self.state = "TERMINATED"
        self._logger.info("query_port_shutdown_complete")

    async def _acquire_query_slot(self, lane: str):
        class _QuerySlot:
            def __init__(self, outer: "QueryPort", lane_value: str) -> None:
                self._outer = outer
                self._lane = lane_value

            async def __aenter__(self) -> "_QuerySlot":
                async with self._outer._queue_lock:
                    self._outer._query_queue_depth += 1
                    emit_gauge(
                        "k1_k0_query_port_queue_depth",
                        self._outer._query_queue_depth,
                        {"lane": self._lane},
                    )
                await self._outer._query_semaphore.acquire()
                return self

            async def __aexit__(self, *_exc: object) -> None:
                self._outer._query_semaphore.release()
                async with self._outer._queue_lock:
                    self._outer._query_queue_depth = max(self._outer._query_queue_depth - 1, 0)
                    emit_gauge(
                        "k1_k0_query_port_queue_depth",
                        self._outer._query_queue_depth,
                        {"lane": self._lane},
                    )

        return _QuerySlot(self, lane)

    async def _serialize_request(self, request: QueryRequest) -> Tuple[bytes, SerializationFormat]:
        payload = {
            "port_id": "P01",
            "command_type": "recall_query",
            "cognitive_trace_id": request.cognitive_trace_id or "",
            "session_id": request.session_id,
            "privacy_band": request.privacy_band,
            "capability": "READ_MEMORY/RECALL",
            "payload": {
                "query": request.query,
                "query_type": request.query_type,
                "lane": request.lane.value,
                "stores": [store.value for store in request.stores],
                "max_results": request.max_results,
                "mmr_diversity": request.mmr_diversity,
            },
        }
        if request.cursor:
            payload["payload"]["cursor"] = request.cursor
        if request.filters:
            payload["payload"]["filters"] = request.filters
        if request.cognitive_enhancements:
            payload["payload"]["cognitive_enhancements"] = request.cognitive_enhancements

        format_used = await self._protocol_negotiator.select_format(
            endpoint=self.config["endpoint"],
            payload=payload,
        )

        serialized_body = await self._protocol_negotiator.serialize(
            payload,
            format_used,
        )

        return serialized_body, format_used

    def _build_headers(self, request: QueryRequest, format_used: SerializationFormat) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json" if format_used == SerializationFormat.JSON else "application/octet-stream",
            "Accept": "application/json",
            "X-Cognitive-Trace-Id": request.cognitive_trace_id or "",  # propagate trace
            "X-Query-Lane": request.lane.value,
            "X-Privacy-Band": request.privacy_band,
            "X-Query-Max-Results": str(request.max_results),
        }
        return headers

    async def _dispatch_request(
        self,
        body: bytes,
        headers: Dict[str, str],
        request: QueryRequest,
    ) -> HTTP2Response:
        path = self.config["endpoint"]
        timeout_s = self.config["timeout_ms"] / 1000.0
        with create_span(
            "k0_bridge.query_port.request",
            query=request.query,
            lane=request.lane.value,
            max_results=request.max_results,
        ) as span:
            span.set_attribute("privacy_band", request.privacy_band)
            span.set_attribute("stores", ",".join(store.value for store in request.stores))
            response = await self._http2_connection.request(
                method="POST",
                path=path,
                headers=headers,
                body=body,
                timeout=timeout_s,
            )
            span.set_attribute("status", response.status)
        return response

    def _parse_response(
        self,
        response: HTTP2Response,
        request: QueryRequest,
    ) -> Tuple[List[QueryResult], int, Optional[str], int, float]:
        if response.status != 200:
            raise RuntimeError(f"Query failed with status {response.status}")

        try:
            decoded = json.loads(response.body.decode("utf-8"))
        except json.JSONDecodeError as exc:  # pragma: no cover - indicates upstream bug
            raise RuntimeError("Invalid JSON response from K0") from exc

        results_payload = decoded.get("results", [])
        query_latency = float(decoded.get("query_latency_ms", 0.0))
        total_count = int(decoded.get("total_count", len(results_payload)))
        next_cursor = decoded.get("next_cursor")

        results: List[QueryResult] = []
        for index, result in enumerate(results_payload, start=1):
            store_value = result.get("store") or result.get("memory_type", "FTS")
            try:
                store_enum = QueryStore(store_value.upper())
            except ValueError:
                store_enum = QueryStore.FTS
            results.append(
                QueryResult(
                    rank=index,
                    store=store_enum,
                    text=result.get("content", ""),
                    score=float(result.get("relevance_score", 0.0)),
                    source=result.get("memory_id", ""),
                    metadata=result.get("provenance"),
                )
            )

        if total_count < len(results):
            raise RuntimeError("K0 returned total_count less than results length")

        if next_cursor:
            emit_counter("k1_k0_query_port_pagination", 1, {"lane": request.lane.value})

        return results, len(results_payload), next_cursor, total_count, query_latency

    def _require_session_id(self, request: QueryRequest) -> str:
        return request.session_id


# =============================================================================
# SECTION 5: HELPER FUNCTIONS
# =============================================================================


def create_query_port(config: Optional[Dict[str, Any]] = None) -> QueryPort:
    """
    Create QueryPort with default or provided configuration.

    Args:
        config: Configuration dict (default: localhost:8080)

    Returns:
        QueryPort instance

    ADR: ADR-0001a (K0 Bridge Dual Protocol)
    Assigned to: Issue #L5-1.2.2
    """
    if config is None:
        config = DEFAULT_CONFIG

    return QueryPort(config)


# =============================================================================
# SECTION 6: MODULE EXPORTS & INITIALIZATION
# =============================================================================

__all__ = [
    "QueryPort",
    "QueryRequest",
    "QueryResponse",
    "QueryResult",
    "QueryLane",
    "QueryStore",
    "create_query_port",
]


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================
# Metrics to export (Prometheus):
#   - k1_k0_query_port_requests_total{lane, status} (counter)
#   - k1_k0_query_port_latency_ms{lane, p50, p95, p99} (histogram)
#   - k1_k0_query_port_result_count{lane, p50, p95, p99} (histogram)
#
# Traces to generate (OpenTelemetry):
#   - Span name: k0_bridge.query_port_query
#   - Attributes: session_id, query_text, lane, stores, cognitive_trace_id
#   - Links to: upstream orchestrator spans
#
# Logs to emit (structured logging):
#   - Level: INFO (normal), WARNING (slow query), ERROR (failures)
#   - Fields: component='query_port', query_text, lane, result_count
#
# =============================================================================

# =============================================================================
# COGNITIVE TRACE PROPAGATION
# =============================================================================
# All async methods must:
#   1. Accept cognitive_trace_id parameter (in QueryRequest)
#   2. Include trace_id in HTTP request headers (X-Cognitive-Trace-Id)
#   3. Include trace_id in all log statements
#
# Example:
#   request = QueryRequest(
#       query='What did I say about X?',
#       cognitive_trace_id='trace_abc123'
#   )
#   response = await query_port.query(request)
#   # HTTP request includes: X-Cognitive-Trace-Id: trace_abc123
#
# =============================================================================

# =============================================================================
# TESTING REQUIREMENTS (WARD Framework)
# =============================================================================
# Integration tests required:
#   - tests/k1/bridge_k0/ports/test_query_port.py
#   - Test query execution (SMART and FAST lanes)
#   - Test multi-store retrieval (FTS, Vector, KG, Episodic)
#   - Test MMR-fused results parsing
#   - Test format negotiation (JSON vs FlatBuffers)
#   - Test error handling (K0 unavailable, timeouts)
#
# No simulation code allowed:
#   - Use real K0 mock server with /k0/query endpoint
#   - Test both JSON and FlatBuffers paths
#   - Integration tests > unit tests
#
# Performance budget tests:
#   - Assert query latency <50ms P95 (SMART lane)
#   - Assert query latency <20ms P95 (FAST lane)
#   - Assert result count matches max_results
#
# =============================================================================
