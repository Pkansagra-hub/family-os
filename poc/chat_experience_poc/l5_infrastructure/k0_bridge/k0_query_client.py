"""
K0 Bridge Query Client

Communicates with K0 directly via K0 Bridge Query Port (P01) for memory retrieval.
This is NOT MCP - it's direct K0 communication using the ADR-0001a protocol.

Features:
- Multi-store retrieval: FTS5 (keyword) + FAISS (vector) + SQLite KG
- 4 memory types: episodic, semantic, procedural, working_memory
- Filtering: time_range, tags, keywords, similarity threshold
- Relevance scoring with provenance (FTS score + vector score + KG score)
- Caching: 60s cache for repeated queries (optimization)
- Error handling: network errors, timeout (>50ms), K0 unavailable
- Retry logic: 3 attempts with exponential backoff

K0 Query Port: HTTP POST to http://localhost:5201/v1/query

References:
- ADR-0001a - K0 Bridge Communication Protocol (P01 RecallQuery specification)
- docs/whiteboard/chat_experience.md - K0 Query Port section
- Multi-store retrieval: FTS5 + FAISS + SQLite KG (ADR-0001a P01 spec)
"""

import asyncio
import hashlib
import time
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger(__name__)


class CircuitBreakerState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failures detected, rejecting requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker pattern implementation.

    Opens after 5 consecutive failures.
    Half-opens after 60s to test recovery.
    Closes after 2 consecutive successes.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout_seconds: int = 60,
    ):
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout_seconds = timeout_seconds

        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None

    def record_success(self):
        """Record successful call."""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                logger.info("circuit_breaker_closed")
        elif self.state == CircuitBreakerState.CLOSED:
            self.failure_count = 0

    def record_failure(self):
        """Record failed call."""
        self.last_failure_time = time.time()

        if self.state == CircuitBreakerState.HALF_OPEN:
            # Failed while testing recovery, open again
            self.state = CircuitBreakerState.OPEN
            self.success_count = 0
            logger.warning("circuit_breaker_open", reason="failed_during_test")
        elif self.state == CircuitBreakerState.CLOSED:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitBreakerState.OPEN
                logger.warning(
                    "circuit_breaker_open",
                    consecutive_failures=self.failure_count,
                )

    def can_execute(self) -> bool:
        """Check if call can be executed."""
        if self.state == CircuitBreakerState.CLOSED:
            return True

        if self.state == CircuitBreakerState.OPEN:
            # Check if timeout has passed to transition to half-open
            if self.last_failure_time is not None:
                elapsed = time.time() - self.last_failure_time
                if elapsed >= self.timeout_seconds:
                    self.state = CircuitBreakerState.HALF_OPEN
                    self.success_count = 0
                    logger.info("circuit_breaker_half_open")
                    return True
            return False

        # HALF_OPEN - allow test request
        return True


@dataclass
class Memory:
    """Single memory result from K0."""

    memory_id: str
    memory_type: str  # episodic, semantic, procedural, working_memory
    content: str
    timestamp: int
    relevance_score: float  # 0.0-1.0
    fts_score: Optional[float]  # FTS5 keyword match score
    vector_score: Optional[float]  # FAISS semantic similarity score
    kg_score: Optional[float]  # SQLite KG relationship score
    tags: List[str]
    provenance: Dict[str, Any]  # Metadata about how score was computed

    def to_dict(self) -> dict:
        """Convert to dict."""
        return asdict(self)


@dataclass
class QueryFilters:
    """Query filters for K0 memory retrieval."""

    time_range: Optional[Dict[str, int]] = None  # {"start": epoch, "end": epoch}
    tags: Optional[List[str]] = None  # Filter by tags
    keywords: Optional[str] = None  # Full-text search keywords
    similarity_threshold: float = 0.5  # FAISS vector similarity threshold

    def to_dict(self) -> dict:
        """Convert to dict, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}

    def validate(self) -> tuple[bool, Optional[str]]:
        """
        Validate filter structure.

        Returns:
            (is_valid, error_message)
        """
        if self.time_range:
            if not isinstance(self.time_range, dict):
                return False, "time_range must be dict"
            if "start" not in self.time_range or "end" not in self.time_range:
                return False, "time_range must have 'start' and 'end' keys"
            start = self.time_range["start"]
            end = self.time_range["end"]
            if not isinstance(start, int) or not isinstance(end, int):
                return False, "time_range values must be integers (epoch)"
            if start > end:
                return False, "time_range start must be <= end"

        if self.tags:
            if not isinstance(self.tags, list):
                return False, "tags must be list"
            if not all(isinstance(t, str) for t in self.tags):
                return False, "all tags must be strings"

        if not 0.0 <= self.similarity_threshold <= 1.0:
            return False, "similarity_threshold must be between 0.0 and 1.0"

        return True, None


class K0QueryError(Exception):
    """Base exception for K0 Query errors."""

    pass


class K0QueryTimeout(K0QueryError):
    """Query exceeded latency budget."""

    pass


class K0QueryCache:
    """Simple query result cache (60s TTL)."""

    def __init__(self, ttl_seconds: int = 60):
        self.ttl_seconds = ttl_seconds
        self.cache: Dict[str, tuple[List[Memory], float]] = {}

    @staticmethod
    def _make_key(query_type: str, filters: QueryFilters, limit: int) -> str:
        """Generate cache key from query params."""
        key_str = f"{query_type}:{str(filters.to_dict())}:{limit}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def get(self, query_type: str, filters: QueryFilters, limit: int) -> Optional[List[Memory]]:
        """Get cached result if available and not expired."""
        key = self._make_key(query_type, filters, limit)
        if key in self.cache:
            results, timestamp = self.cache[key]
            age = time.time() - timestamp
            if age < self.ttl_seconds:
                logger.debug("cache_hit", age=age, query_type=query_type)
                return results
            else:
                # Expired, remove
                del self.cache[key]
        return None

    def set(self, query_type: str, filters: QueryFilters, limit: int, results: List[Memory]):
        """Cache query results."""
        key = self._make_key(query_type, filters, limit)
        self.cache[key] = (results, time.time())
        logger.debug("cache_set", query_type=query_type, num_results=len(results))

    def clear(self):
        """Clear entire cache."""
        self.cache.clear()


class K0QueryClient:
    """
    Client for K0 Query Port (P01) memory retrieval.

    Supports 4 memory types:
    - episodic: Recent conversation turns, facts learned
    - semantic: General knowledge, KG relationships
    - procedural: Skills, habits, patterns
    - working_memory: Active working memory from current session
    """

    def __init__(
        self,
        k0_base_url: str = "http://localhost:8003",
        timeout_seconds: float = 0.050,
        max_retries: int = 3,
        cache_ttl_seconds: int = 60,
        pool_size: int = 5,
    ):
        """
        Initialize K0 Query client.

        Args:
            k0_base_url: K0 Bridge base URL (default: Mock K0 at localhost:8003)
            timeout_seconds: Request timeout (50ms default per P01 budget)
            max_retries: Max retry attempts (3 with exponential backoff)
            cache_ttl_seconds: Query cache TTL
            pool_size: HTTP connection pool size (5 concurrent connections)
        """
        self.k0_base_url = k0_base_url
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.cache = K0QueryCache(ttl_seconds=cache_ttl_seconds)

        # Circuit breaker for fault tolerance
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,  # Open after 5 failures
            success_threshold=2,  # Close after 2 successes
            timeout_seconds=60,  # Test recovery after 60s
        )

        # HTTP client with connection pooling (5 concurrent connections)
        limits = httpx.Limits(max_connections=pool_size, max_keepalive_connections=pool_size)
        self.client = httpx.AsyncClient(
            base_url=k0_base_url,
            timeout=timeout_seconds,
            limits=limits,
        )

        # Metrics
        self.query_count = 0
        self.error_count = 0
        self.cache_hits = 0
        self.circuit_breaker_rejections = 0
        self.avg_latency_ms = 0.0

    async def query_memory(
        self,
        query_type: str = "episodic",
        filters: Optional[QueryFilters] = None,
        limit: int = 10,
        session_id: str = "default",
        user_id: str = "default",
        trace_id: Optional[str] = None,
    ) -> List[Memory]:
        """
        Query K0 for memories of specific type.

        Args:
            query_type: Type of memory (episodic, semantic, procedural, working_memory)
            filters: Query filters (time_range, tags, keywords, similarity_threshold)
            limit: Max results to return
            session_id: Current session ID
            user_id: User ID
            trace_id: Optional trace ID for correlation

        Returns:
            List of Memory objects with relevance scores

        Raises:
            K0QueryError: On K0 communication failure
            K0QueryTimeout: If query exceeds latency budget (>50ms)
        """
        trace_id = trace_id or f"query_{int(time.time() * 1000)}"
        filters = filters or QueryFilters()

        # Check circuit breaker first
        if not self.circuit_breaker.can_execute():
            self.circuit_breaker_rejections += 1
            logger.warning(
                "k0_query_rejected_circuit_open",
                trace_id=trace_id,
                state=self.circuit_breaker.state.value,
            )
            raise K0QueryError("K0 Query service unavailable (circuit open)")

        # Validate inputs
        if query_type not in ("episodic", "semantic", "procedural", "working_memory"):
            raise K0QueryError(f"Invalid query_type: {query_type}")

        is_valid, error = filters.validate()
        if not is_valid:
            raise K0QueryError(f"Invalid filters: {error}")

        # Check cache first
        cached = self.cache.get(query_type, filters, limit)
        if cached is not None:
            self.cache_hits += 1
            return cached

        logger.info(
            "k0_query_start",
            query_type=query_type,
            trace_id=trace_id,
            limit=limit,
        )

        start_time = time.time()

        try:
            # Build K0 Bridge request (ADR-0001a P01 RecallQuery format)
            request_body = {
                "port": "query",
                "command_type": "recall_query",
                "envelope_id": f"env_query_{int(time.time() * 1000)}",
                "cognitive_trace_id": trace_id,
                "session_id": session_id,
                "user_id": user_id,
                "qos_band": "GREEN",
                "payload": {
                    "query_type": query_type,
                    "filters": {
                        **filters.to_dict(),
                        "limit": limit,
                    },
                },
            }

            # Call K0 Query Port with retries and circuit breaker
            response = await self._send_query_with_retry(request_body, trace_id, query_type)

            # Parse response
            memories = self._parse_response(response, query_type)

            # Cache results
            self.cache.set(query_type, filters, limit, memories)

            # Record metrics
            latency_ms = (time.time() - start_time) * 1000
            self.query_count += 1
            self.avg_latency_ms = (
                self.avg_latency_ms * (self.query_count - 1) + latency_ms
            ) / self.query_count

            # Record success in circuit breaker
            self.circuit_breaker.record_success()

            # Check latency budget (50ms P95 per ADR-0001a)
            if latency_ms > 50:
                logger.warning(
                    "k0_query_slow",
                    trace_id=trace_id,
                    latency_ms=latency_ms,
                    budget_ms=50,
                )

            # Log with metrics
            logger.info(
                "k0_query_success",
                trace_id=trace_id,
                query_type=query_type,
                num_results=len(memories),
                latency_ms=latency_ms,
                cache_hit=False,
            )

            return memories

        except asyncio.TimeoutError as e:
            self.error_count += 1
            self.circuit_breaker.record_failure()
            logger.error("k0_query_timeout", trace_id=trace_id, timeout_sec=self.timeout_seconds)
            raise K0QueryTimeout(f"K0 query timeout after {self.timeout_seconds}s") from e

        except Exception as e:
            self.error_count += 1
            self.circuit_breaker.record_failure()
            logger.error("k0_query_error", trace_id=trace_id, error=str(e))
            raise K0QueryError(f"K0 query failed: {str(e)}") from e

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=0.05, max=0.2),
    )
    async def _send_query_with_retry(
        self, request_body: dict, trace_id: str, query_type: str
    ) -> dict:
        """
        Send query with automatic retries (exponential backoff: 50ms, 100ms, 200ms).

        Args:
            request_body: Request payload
            trace_id: Trace ID for logging
            query_type: Query type for metrics

        Returns:
            Response dict from K0 API
        """
        logger.debug(
            "k0_query_request",
            trace_id=trace_id,
            endpoint="/v1/query",
            query_type=query_type,
        )

        response = await self.client.post(
            "/v1/query",
            json=request_body,
        )
        response.raise_for_status()

        return response.json()

    def _parse_response(self, response: dict, query_type: str) -> List[Memory]:
        """Parse K0 response into Memory objects."""
        memories = []

        # Response format (ADR-0001a P01 specification):
        # {
        #   "status": "success",
        #   "memories": [
        #     {
        #       "memory_id": "mem_123",
        #       "content": "...",
        #       "timestamp": 1728000000,
        #       "relevance_score": 0.95,
        #       "scores": {
        #         "fts_score": 0.9,
        #         "vector_score": 0.95,
        #         "kg_score": 0.8
        #       },
        #       "tags": ["health", "recovery"],
        #       "provenance": {...}
        #     },
        #     ...
        #   ]
        # }

        if response.get("status") != "success":
            logger.warning("k0_query_not_success", status=response.get("status"))
            return []

        for mem_data in response.get("memories", []):
            try:
                scores = mem_data.get("scores", {})
                memory = Memory(
                    memory_id=mem_data.get("memory_id", "unknown"),
                    memory_type=query_type,
                    content=mem_data.get("content", ""),
                    timestamp=mem_data.get("timestamp", 0),
                    relevance_score=mem_data.get("relevance_score", 0.0),
                    fts_score=scores.get("fts_score"),
                    vector_score=scores.get("vector_score"),
                    kg_score=scores.get("kg_score"),
                    tags=mem_data.get("tags", []),
                    provenance=mem_data.get("provenance", {}),
                )
                memories.append(memory)
            except Exception as e:
                logger.warning("k0_parse_memory_error", error=str(e), mem_data=mem_data)
                continue

        return memories

    def get_stats(self) -> dict:
        """Return client statistics."""
        return {
            "query_count": self.query_count,
            "error_count": self.error_count,
            "cache_hits": self.cache_hits,
            "cache_hit_rate": (self.cache_hits / self.query_count if self.query_count > 0 else 0.0),
            "avg_latency_ms": self.avg_latency_ms,
            "circuit_breaker_state": self.circuit_breaker.state.value,
            "circuit_breaker_rejections": self.circuit_breaker_rejections,
        }

    async def close(self):
        """Close client connection."""
        await self.client.aclose()

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
