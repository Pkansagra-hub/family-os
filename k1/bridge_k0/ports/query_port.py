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

import logging
from dataclasses import dataclass
from enum import Enum

# =============================================================================
# SECTION 1: IMPORTS
# =============================================================================
# Standard library imports
from typing import Any, Dict, List, Optional

# Third-party imports
# None

# Internal imports
# from k1.bridge_k0.http2_client import HTTP2Connection
# from k1.bridge_k0.protocol import ProtocolNegotiator, SerializationFormat

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
    lane: QueryLane = QueryLane.SMART
    privacy_band: str = "GREEN"
    stores: List[QueryStore] = None
    max_results: int = 10
    mmr_diversity: float = 0.5
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

    def __init__(self, config: Dict[str, Any]) -> None:
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
        self.config = config
        self.state = "INIT"  # State: INIT | CONNECTING | READY | DEGRADED | TERMINATED
        self._logger = logger
        pass

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
        # TODO(@infrastructure-team): Implement async initialization (ADR-0001a)
        # 1. Connect to K0 Query Port (HTTP/2 connection)
        # 2. Negotiate format (JSON vs FlatBuffers via OPTIONS request)
        # 3. Transition state: INIT → CONNECTING → READY
        self.state = "READY"
        self._logger.info(
            "query_port_initialized",
            k0_host=self.config.get("k0_host"),
            k0_port=self.config.get("k0_query_port"),
        )
        pass

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
        # TODO(@infrastructure-team): Implement query (ADR-0001f)
        # 1. Validate request (query text, lane, stores)
        # 2. Create HTTP request payload (JSON or FlatBuffers)
        # 3. Send via HTTP/2 (POST /k0/query)
        # 4. Parse response (MMR-fused results from K0)
        # 5. Convert to QueryResponse (results, latency, stores_queried)
        # 6. Record metrics (latency, result count, lane)
        # 7. Return QueryResponse
        #
        # CRITICAL: K1 does NOT implement MMR fusion or multi-store logic.
        # K0 P01 Pipeline returns results already ranked and deduplicated.
        self._logger.info(
            "query_executed",
            query_text=request.query,
            lane=request.lane.value,
            trace_id=request.cognitive_trace_id,
        )

        # Placeholder return (MUST be replaced with actual implementation)
        return QueryResponse(
            results=[], query_latency_ms=0.0, stores_queried=request.stores
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
        # TODO(@infrastructure-team): Implement shutdown (ADR-0001a)
        # 1. Set state to TERMINATED
        # 2. Close HTTP/2 connection
        # 3. Flush metrics (Prometheus)
        self.state = "TERMINATED"
        self._logger.info("query_port_shutdown_complete")
        pass


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
