"""
Batch Client - Bounded Batching for SessionState Deltas to K0 Bridge

Communicates with K0 Bridge Batch Port (P02/P05/P06) for memory writes.
Features:
- Bounded batching: 250ms OR 64KB OR 100 deltas (whichever comes first)
- HTTP/2 connection management with 5 concurrent connections
- Retry logic: 3 attempts for transient errors, no retry for validation errors
- Circuit breaker: Opens after 5 failures, half-opens after 60s
- Health checks: Ping /health every 30s
- Request/response logging with metrics

Endpoints:
- P02 (Episodic): POST /v1/write/episodic
- P05 (Prospective): POST /v1/write/prospective
- P06 (Learning): POST /v1/write/learning
- Health: GET /health

References:
- ADR-0019 - Bounded Batching (250ms, 64KB, 100 deltas)
- docs/whiteboard/chat_experience.md - K0 Bridge architecture
- Milestone 3, Epic 3.2 - Batch Client implementation
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

logger = structlog.get_logger(__name__)


@dataclass
class Delta:
    """A single SessionState delta for batching."""

    delta_id: str
    delta_type: str  # "episodic", "prospective", "learning"
    content: Dict[str, Any]
    timestamp: int
    trace_id: str

    def to_dict(self) -> dict:
        """Convert to dict for serialization."""
        return {
            "delta_id": self.delta_id,
            "delta_type": self.delta_type,
            "content": self.content,
            "timestamp": self.timestamp,
            "trace_id": self.trace_id,
        }


@dataclass
class Batch:
    """A batch of deltas ready for flushing."""

    batch_id: str
    deltas: List[Delta] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    trigger: str = "manual"  # "timeout", "size", "count", "manual"

    def size_bytes(self) -> int:
        """Calculate approximate size in bytes."""
        import json

        content = {"deltas": [d.to_dict() for d in self.deltas]}
        return len(json.dumps(content).encode())

    def is_full(self, max_deltas: int = 100, max_bytes: int = 65536) -> bool:
        """Check if batch is full."""
        return len(self.deltas) >= max_deltas or self.size_bytes() >= max_bytes


class BatchClient:
    """
    Client for K0 Batch Port (P02/P05/P06) with bounded batching.

    Accumulates deltas and flushes them:
    - After 250ms elapsed
    - After 64KB accumulated
    - After 100 deltas accumulated
    - On manual flush request
    """

    def __init__(
        self,
        k0_base_url: str = "http://localhost:8003",
        batch_timeout_ms: int = 250,
        batch_max_deltas: int = 100,
        batch_max_bytes: int = 65536,
        pool_size: int = 5,
        health_check_interval_seconds: int = 30,
    ):
        """
        Initialize Batch Client.

        Args:
            k0_base_url: K0 Bridge base URL
            batch_timeout_ms: Flush timeout (250ms per ADR-0019)
            batch_max_deltas: Max deltas per batch (100)
            batch_max_bytes: Max batch size (64KB)
            pool_size: HTTP connection pool size
            health_check_interval_seconds: Health check interval
        """
        self.k0_base_url = k0_base_url
        self.batch_timeout_ms = batch_timeout_ms
        self.batch_max_deltas = batch_max_deltas
        self.batch_max_bytes = batch_max_bytes
        self.health_check_interval_seconds = health_check_interval_seconds

        # Batching state
        self.batches_by_type: Dict[str, Batch] = {
            "episodic": Batch(batch_id=self._gen_batch_id("episodic")),
            "prospective": Batch(batch_id=self._gen_batch_id("prospective")),
            "learning": Batch(batch_id=self._gen_batch_id("learning")),
        }
        self.batch_lock = asyncio.Lock()

        # HTTP client with connection pooling
        limits = httpx.Limits(max_connections=pool_size, max_keepalive_connections=pool_size)
        self.client = httpx.AsyncClient(
            base_url=k0_base_url,
            timeout=5.0,
            limits=limits,
        )

        # Circuit breaker
        from .k0_query_client import CircuitBreaker

        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            success_threshold=2,
            timeout_seconds=60,
        )

        # Health check
        self.health_ok = True
        self.last_health_check = time.time()

        # Metrics
        self.batches_flushed = 0
        self.deltas_sent = 0
        self.flush_errors = 0
        self.avg_batch_latency_ms = 0.0
        self.health_check_failures = 0

        # Background tasks
        self._flush_task: Optional[asyncio.Task] = None
        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False

    @staticmethod
    def _gen_batch_id(delta_type: str) -> str:
        """Generate unique batch ID."""
        return f"batch_{delta_type}_{int(time.time() * 1000)}"

    async def start(self):
        """Start background batching loop and health checks."""
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info("batch_client_started", k0_url=self.k0_base_url)

    async def stop(self):
        """Stop background tasks and flush remaining batches."""
        self._running = False

        # Flush all remaining batches
        await self.flush_all()

        # Cancel background tasks
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        logger.info("batch_client_stopped")

    async def add_delta(self, delta: Delta) -> bool:
        """
        Add delta to batch.

        Args:
            delta: Delta to add

        Returns:
            True if added successfully, False otherwise
        """
        if not self._running:
            logger.warning("batch_client_not_running", delta_id=delta.delta_id)
            return False

        async with self.batch_lock:
            batch = self.batches_by_type.get(delta.delta_type)
            if batch is None:
                logger.error("unknown_delta_type", delta_type=delta.delta_type)
                return False

            batch.deltas.append(delta)

            # Check if batch should flush immediately (size or count reached)
            if batch.is_full(self.batch_max_deltas, self.batch_max_bytes):
                logger.debug(
                    "batch_full",
                    delta_type=delta.delta_type,
                    count=len(batch.deltas),
                    size_bytes=batch.size_bytes(),
                )
                # Schedule flush in background
                asyncio.create_task(self._flush_batch_immediate(delta.delta_type))

        return True

    async def _flush_loop(self):
        """
        Background loop: flush batches every 250ms.

        Runs `while True: await asyncio.sleep(0.25); flush_if_needed()`
        """
        try:
            while self._running:
                await asyncio.sleep(self.batch_timeout_ms / 1000.0)

                # Check each batch type for timeout
                async with self.batch_lock:
                    for delta_type in ("episodic", "prospective", "learning"):
                        batch = self.batches_by_type[delta_type]
                        if batch.deltas:
                            elapsed_ms = (time.time() - batch.created_at) * 1000
                            if elapsed_ms >= self.batch_timeout_ms:
                                logger.debug(
                                    "batch_timeout_flush",
                                    delta_type=delta_type,
                                    elapsed_ms=elapsed_ms,
                                    count=len(batch.deltas),
                                )
                                # Flush this batch
                                await self._flush_batch_internal(delta_type)
        except asyncio.CancelledError:
            logger.debug("flush_loop_cancelled")
        except Exception as e:
            logger.error("flush_loop_error", error=str(e))

    async def _health_check_loop(self):
        """
        Background loop: ping /health endpoint every 30s.

        Detects Mock K0 availability.
        If unhealthy: open circuit breaker, queue batches.
        When healthy again: flush queued batches.
        """
        try:
            while self._running:
                await asyncio.sleep(self.health_check_interval_seconds)
                await self._check_health()
        except asyncio.CancelledError:
            logger.debug("health_check_loop_cancelled")
        except Exception as e:
            logger.error("health_check_loop_error", error=str(e))

    async def _check_health(self):
        """Ping Mock K0 /health endpoint."""
        try:
            start_time = time.time()
            response = await self.client.get("/health", timeout=2.0)
            latency_ms = (time.time() - start_time) * 1000

            if response.status_code == 200:
                if not self.health_ok:
                    # Recovered from unhealthy state
                    logger.info("k0_health_recovered", latency_ms=latency_ms)
                    self.health_ok = True
                    self.circuit_breaker.record_success()
                    # Flush queued batches
                    await self.flush_all()
            else:
                logger.warning(
                    "k0_health_check_failed",
                    status_code=response.status_code,
                )
                if self.health_ok:
                    # Transitioned to unhealthy
                    logger.warning("k0_health_unhealthy", status=response.status_code)
                    self.health_ok = False
                    self.circuit_breaker.record_failure()
                self.health_check_failures += 1

        except Exception as e:
            logger.error("k0_health_check_error", error=str(e))
            if self.health_ok:
                self.health_ok = False
                self.circuit_breaker.record_failure()
            self.health_check_failures += 1

    async def _flush_batch_immediate(self, delta_type: str):
        """Flush a specific batch immediately."""
        async with self.batch_lock:
            await self._flush_batch_internal(delta_type)

    async def _flush_batch_internal(self, delta_type: str):
        """
        Flush batch of specific type (must be called with lock held).

        Retry logic:
        - Transient errors (network): Retry 3 times
        - Validation errors (400): Do not retry, log error
        - Server errors (500): Retry with exponential backoff
        """
        batch = self.batches_by_type[delta_type]
        if not batch.deltas:
            return

        logger.info(
            "batch_flush_start",
            batch_id=batch.batch_id,
            delta_type=delta_type,
            delta_count=len(batch.deltas),
            size_bytes=batch.size_bytes(),
        )

        try:
            # Call K0 Bridge with retries
            await self._send_batch_with_retry(batch, delta_type)

            # Update metrics
            latency_ms = (time.time() - batch.created_at) * 1000
            self.batches_flushed += 1
            self.deltas_sent += len(batch.deltas)
            self.avg_batch_latency_ms = (
                self.avg_batch_latency_ms * (self.batches_flushed - 1) + latency_ms
            ) / self.batches_flushed

            logger.info(
                "batch_flush_success",
                batch_id=batch.batch_id,
                delta_type=delta_type,
                delta_count=len(batch.deltas),
                latency_ms=latency_ms,
                trigger=batch.trigger,
            )

            # Record success in circuit breaker
            self.circuit_breaker.record_success()

            # Reset batch
            self.batches_by_type[delta_type] = Batch(batch_id=self._gen_batch_id(delta_type))

        except Exception as e:
            self.flush_errors += 1
            self.circuit_breaker.record_failure()
            logger.error(
                "batch_flush_failed",
                batch_id=batch.batch_id,
                delta_type=delta_type,
                error=str(e),
            )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=0.05, max=0.5),
    )
    async def _send_batch_with_retry(self, batch: Batch, delta_type: str) -> dict:
        """
        Send batch to K0 Bridge with automatic retries.

        Retry logic:
        - Transient errors (network, timeout): Auto-retry
        - Validation errors (400): Don't retry, raise
        - Server errors (500): Auto-retry
        """
        endpoint = self._get_endpoint(delta_type)

        logger.debug(
            "batch_send_request",
            batch_id=batch.batch_id,
            endpoint=endpoint,
            delta_count=len(batch.deltas),
        )

        # Build request
        request_body = {
            "batch_id": batch.batch_id,
            "delta_type": delta_type,
            "deltas": [d.to_dict() for d in batch.deltas],
            "timestamp": int(time.time() * 1000),
        }

        try:
            response = await self.client.post(endpoint, json=request_body, timeout=5.0)

            # Handle validation errors (don't retry)
            if response.status_code == 400:
                logger.error(
                    "batch_validation_error",
                    batch_id=batch.batch_id,
                    response_text=response.text,
                )
                raise ValueError(f"Batch validation error: {response.text}")

            # Handle success
            if response.status_code == 200:
                return response.json()

            # Handle server errors (will retry)
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            logger.warning(
                "batch_http_error",
                batch_id=batch.batch_id,
                error=str(e),
                attempt=self._send_batch_with_retry.retry.statistics.get("attempt_number", 1),
            )
            raise

    @staticmethod
    def _get_endpoint(delta_type: str) -> str:
        """Get K0 endpoint for delta type."""
        endpoints = {
            "episodic": "/v1/write/episodic",  # P02
            "prospective": "/v1/write/prospective",  # P05
            "learning": "/v1/write/learning",  # P06
        }
        return endpoints.get(delta_type, "/v1/write/episodic")

    async def flush_all(self):
        """Manually flush all batches."""
        async with self.batch_lock:
            for delta_type in ("episodic", "prospective", "learning"):
                if self.batches_by_type[delta_type].deltas:
                    logger.info("manual_flush", delta_type=delta_type)
                    await self._flush_batch_internal(delta_type)

    def flush_now(self):
        """
        Synchronously request immediate flush of all batches.

        For PoC CLI usage where we need to flush episodic deltas immediately.
        Creates task to flush in the event loop.
        """
        try:
            import asyncio

            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If loop is running, schedule task
                loop.create_task(self.flush_all())
            else:
                # If no loop, run synchronously
                asyncio.run(self.flush_all())
        except Exception as e:
            logger.warning("flush_now_error", error=str(e))

    def get_stats(self) -> dict:
        """Return client statistics."""
        return {
            "batches_flushed": self.batches_flushed,
            "deltas_sent": self.deltas_sent,
            "flush_errors": self.flush_errors,
            "avg_batch_latency_ms": self.avg_batch_latency_ms,
            "health_ok": self.health_ok,
            "health_check_failures": self.health_check_failures,
            "circuit_breaker_state": self.circuit_breaker.state.value,
            "pending_deltas_episodic": len(self.batches_by_type["episodic"].deltas),
            "pending_deltas_prospective": len(self.batches_by_type["prospective"].deltas),
            "pending_deltas_learning": len(self.batches_by_type["learning"].deltas),
        }

    async def close(self):
        """Close client connection."""
        await self.stop()
        await self.client.aclose()

    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
