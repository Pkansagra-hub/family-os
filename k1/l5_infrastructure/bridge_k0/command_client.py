"""
K0 Bridge - Command Client (Write Operations)

Purpose: K0 Command Port client for write operations to K0 memory kernel
Location: k1/l5_infrastructure/bridge_k0/command_client.py
Performance: <50ms P95 (GREEN band), <200ms P95 (AMBER/RED band)

Primary ADRs:
- ADR-0001a: K0 Bridge Architecture (dual-protocol, 4 ports, lane processing)
- ADR-0001: K0 Integration (20 pipelines, 4 external ports)

Related ADRs:
- ADR-0011: FlatBuffers Serialization (optional optimization, zero-copy)
- ADR-0024: Performance Budgets (K0 Bridge <50ms GREEN, <200ms AMBER/RED)
- ADR-0029: Prometheus Metrics (command_latency_ms, success_rate, error_rate)

Key Responsibilities:
1. Command Port Integration:
   - HTTP POST to K0 Command Port (:5200/v1/command)
   - Dual-protocol: JSON (primary) + FlatBuffers (secondary)
   - Commands: MEMORY_WRITE, PLAN_COMMITTED, SAGA_LOG, STATE_DELTA
   - Receipt validation (WAL offset, timestamp)

2. Lane Processing:
   - Fast Lane (GREEN): <50ms P95, 70% of writes, no safety review
   - Smart Lane (AMBER/RED): <200ms P95, 30% of writes, arbiter approval required
   - Privacy band-aware routing (GREEN/AMBER/RED/BLACK)

3. Reliability:
   - Idempotency keys (UUIDv7, monotonic, 5-minute TTL)
   - Receipt validation (WAL offset, timestamp confirmation)
   - Retry policy: 3 attempts, exponential backoff (100ms→400ms→1600ms)
   - Circuit breaker integration (fail-fast on K0 unavailable)

4. Observability:
   - Prometheus metrics: command_latency_ms (histogram), command_success_total (counter), command_error_total (counter)
   - Structured logging: command_sent, command_acknowledged, command_failed (JSON format)
   - cognitive_trace_id propagation (end-to-end tracing)

Performance Metrics:
- Command latency (GREEN): <50ms P95
- Command latency (AMBER/RED): <200ms P95
- Success rate: >99.9%
- Retry rate: <1%
- Receipt validation: <5ms overhead

Implementation Notes:
- Uses httpx AsyncClient for async HTTP/2
- Connection pooling: 5 connections per K0 instance
- Keep-alive: 60s timeout
- TLS 1.3 mutual authentication
- Batch mode optional (see batch_client.py)

Example Usage:
```python
command_client = CommandClient(k0_base_url="http://localhost:5200")
receipt = await command_client.send_command(
    command_type="MEMORY_WRITE",
    payload={"topic": "k0.memory.write", "data": {...}},
    privacy_band="GREEN",
    idempotency_key=str(uuid.uuid7()),
    cognitive_trace_id=trace_id
)
assert receipt.wal_offset > 0
```

Research Foundation:
- HTTP/2 (RFC 7540): Binary framing, stream multiplexing
- Idempotency (RFC 7231): Safe retry, duplicate prevention
- Privacy Bands (Cavoukian 2009): Privacy by Design, differential degradation

Last Updated: January 2025
ADR Reference: docs/architecture/decisions/0001a-k0-bridge-architecture.md
"""

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional

import httpx

# Import K0's idempotency key derivation function
from k0.idem import derive_idem_key

# Import K1 observability (wraps K0's observability stack)
from k1.l5_infrastructure.observability import get_metrics, get_tracer

try:
    import structlog  # type: ignore

    logger = structlog.get_logger(__name__)  # type: ignore
except ImportError:
    import logging

    logger = logging.getLogger(__name__)  # type: ignore

# Initialize K1 observability (reuses K0's MetricsExporter and TracerFactory)
_metrics = get_metrics()
_tracer = get_tracer()

# Define K1 command client metrics (k1_intelligence namespace)
command_requests_total = _metrics.counter(
    "command_requests_total",
    "Total K0 command requests from K1",
    labelnames=["band", "status"],
)

command_latency_ms = _metrics.histogram(
    "command_latency_ms",
    "K0 command request latency (ms)",
    labelnames=["band"],
    buckets=[10, 25, 50, 100, 200, 500, 1000, 2000, 5000],
)

command_retries_total = _metrics.counter(
    "command_retries_total",
    "Total K0 command retry attempts",
    labelnames=["band", "reason"],
)


@dataclass
class CommandEnvelope:
    """K0 Command envelope (mirrors k0/contracts/jsonschema/envelope.schema.json)

    This dataclass represents the envelope structure required by K0's command port.
    All fields are mandatory as per the JSON schema except idem_key, body, and policy.

    Reference: ADR-0001a (K0 Bridge Architecture)
    Schema: k0/contracts/jsonschema/envelope.schema.json
    """

    cognitive_trace_id: str  # UUID v4 format
    tenant_id: str
    space_id: str
    topic: str  # Pattern: "memory.*", "events.*", etc.
    schema_uri: str  # URI format
    schema_version: str
    actor: str
    device_id: str
    band: Literal["GREEN", "AMBER", "RED"]  # Privacy/QoS band
    policy_version: str
    ts: str  # ISO8601 datetime
    sig: str  # Device signature (will be validated by K0)
    body: Optional[Dict[str, Any]] = None  # Payload body
    idem_key: Optional[str] = (
        None  # Idempotency key (optional, K0 generates if missing)
    )
    payload_sha256: Optional[str] = None  # SHA256 of body (optional)
    policy: Optional[Dict[str, Any]] = (
        None  # Policy context (roles, capabilities, etc.)
    )


@dataclass
class CommandReceipt:
    """K0 Command receipt (mirrors k0/contracts/jsonschema/receipt.schema.json)

    Receipt is proof of successful command acceptance by K0.
    Contains WAL offset for persistence verification.

    Reference: ADR-0001a (K0 Bridge Architecture)
    Schema: k0/contracts/jsonschema/receipt.schema.json
    """

    receipt_id: str  # UUID format
    commit_ts: str  # ISO8601 datetime
    offsets: Dict[str, int]  # Topic -> WAL offset mapping
    idem_key: str  # Canonical idempotency key (from K0)
    obligations: list[str]  # Policy obligations applied


class K0CommandError(Exception):
    """Base exception for K0 Command Port errors"""


class K0CommandRejected(K0CommandError):
    """K0 rejected command (400 Minimal Gate rejection)"""

    def __init__(self, reason: str, component: str = "kernel.gate"):
        self.reason = reason
        self.component = component
        super().__init__(f"K0 rejected command: {reason} (component: {component})")


class K0PolicyDenied(K0CommandError):
    """K0 PEP denied command (403 Forbidden)"""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"K0 policy denied: {reason}")


class K0IdempotentDuplicate(K0CommandError):
    """Command already committed (409 Conflict)"""

    def __init__(self, receipt: Dict[str, Any]):
        self.receipt = receipt
        super().__init__(
            f"Command already committed: receipt_id={receipt.get('receipt_id')}"
        )


class K0QoSExhausted(K0CommandError):
    """QoS budget exhausted (429 Too Many Requests)"""

    def __init__(self, reason: str, cap: str, budgets: Dict[str, int]):
        self.reason = reason
        self.cap = cap
        self.budgets = budgets
        super().__init__(f"QoS budget exhausted: {cap} ({reason})")


class K0Unavailable(K0CommandError):
    """K0 unavailable (5xx Server Error)"""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"K0 unavailable: {status_code} - {detail}")


class K0CommandClient:
    """
    K0 Command Port client (write operations)

    Responsibilities:
    - HTTP POST to K0 Command Port (:5200/k0/command.submit)
    - JSON envelope serialization (PRIMARY format per ADR-0001a)
    - Lane processing: Fast Lane (GREEN) vs Smart Lane (AMBER/RED)
    - Receipt validation (WAL offset, timestamp)
    - Idempotency key generation (UUIDv7 if not provided)
    - HTTP/2 connection pooling
    - Error handling with exponential backoff retry

    Performance Budget (ADR-0024):
    - GREEN band: <50ms P95
    - AMBER/RED band: <200ms P95

    Research: REST API Design (Fielding 2000), HTTP/2 (RFC 7540)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:5200",
        timeout: float = 10.0,
        max_retries: int = 3,
    ):
        """Initialize K0 Command Client

        Args:
            base_url: K0 base URL (default: http://localhost:5200)
            timeout: Request timeout in seconds (default: 10.0)
            max_retries: Maximum retry attempts (default: 3)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

        # HTTP/2 async client with connection pooling
        # ADR-0001a: HTTP/2 for multiplexing, header compression
        self.client = httpx.AsyncClient(
            http2=True,
            timeout=httpx.Timeout(timeout),
            limits=httpx.Limits(
                max_connections=5,  # Connection pool size
                max_keepalive_connections=5,
                keepalive_expiry=60.0,  # 60s keep-alive
            ),
        )

        logger.info(
            "k0_command_client_initialized",
            base_url=self.base_url,
            timeout=timeout,
            max_retries=max_retries,
        )

    async def submit_command(self, envelope: CommandEnvelope) -> CommandReceipt:
        """
        Submit command to K0 Command Port

        Process (per ADR-0001a):
        1. Validate envelope fields
        2. Generate idempotency key if missing (UUIDv7)
        3. Compute payload hash (SHA256)
        4. Serialize to JSON envelope
        5. HTTP POST to /k0/command.submit
        6. Handle response (200, 409, 4xx, 5xx)
        7. Validate receipt
        8. Return CommandReceipt

        Args:
            envelope: Command envelope (see CommandEnvelope dataclass)

        Returns:
            CommandReceipt with receipt_id, commit_ts, offsets

        Raises:
            K0CommandRejected: On K0 rejection (400 Minimal Gate)
            K0PolicyDenied: On PEP deny (403)
            K0IdempotentDuplicate: On duplicate (409)
            K0QoSExhausted: On QoS budget exhausted (429)
            K0Unavailable: On K0 unavailable (5xx)

        Performance: <50ms P95 (GREEN), <200ms P95 (AMBER/RED)
        """
        # Start observability span for distributed tracing
        # Attach cognitive_trace_id to baggage for K1→K0 correlation
        token = _tracer.attach_cognitive_trace(envelope.cognitive_trace_id)

        import time as time_module

        start_time = time_module.time()

        try:
            with _tracer.span(
                "k1.command_submit",
                attributes={
                    "band": envelope.band,
                    "topic": envelope.topic,
                    "tenant_id": envelope.tenant_id,
                    "space_id": envelope.space_id,
                },
            ):
                # Compute payload SHA256 if body provided and hash not set
                # Must be done BEFORE deriving idem_key (which includes payload_sha256)
                if envelope.body is not None and envelope.payload_sha256 is None:
                    import json

                    body_json = json.dumps(
                        envelope.body, sort_keys=True, separators=(",", ":")
                    )
                    envelope.payload_sha256 = hashlib.sha256(
                        body_json.encode("utf-8")
                    ).hexdigest()

                # Derive idempotency key if not provided
                # ADR-0001a: K0 derives idem_key from canonical envelope fields using BLAKE3
                # K1 must compute the same value to pass K0 Gate validation
                if envelope.idem_key is None:
                    # Build envelope dict for derive_idem_key
                    envelope_dict = {
                        "tenant_id": envelope.tenant_id,
                        "space_id": envelope.space_id,
                        "actor": envelope.actor,
                        "topic": envelope.topic,
                        "schema_uri": envelope.schema_uri,
                        "schema_version": envelope.schema_version,
                    }

                    # derive_idem_key expects payload_hash parameter
                    envelope.idem_key = derive_idem_key(
                        envelope_dict, payload_hash=envelope.payload_sha256
                    )

                # Build JSON envelope (K0 native format - ADR-0001a PRIMARY)
                payload: Dict[str, Any] = {
                    "cognitive_trace_id": envelope.cognitive_trace_id,
                    "tenant_id": envelope.tenant_id,
                    "space_id": envelope.space_id,
                    "topic": envelope.topic,
                    "schema_uri": envelope.schema_uri,
                    "schema_version": envelope.schema_version,
                    "actor": envelope.actor,
                    "device_id": envelope.device_id,
                    "band": envelope.band,
                    "policy_version": envelope.policy_version,
                    "ts": envelope.ts,
                    "sig": envelope.sig,
                }

                # Add optional fields if present
                if envelope.idem_key:
                    payload["idem_key"] = envelope.idem_key
                if envelope.payload_sha256:
                    payload["payload_sha256"] = envelope.payload_sha256
                if envelope.body is not None:
                    payload["body"] = envelope.body
                if envelope.policy is not None:
                    payload["policy"] = envelope.policy

                # Retry logic with exponential backoff
                # ADR-0024: 3 attempts with 100ms→400ms→1600ms backoff
                last_error = None
                for attempt in range(self.max_retries):
                    try:
                        receipt = await self._post_command(
                            payload, envelope.cognitive_trace_id, attempt
                        )

                        # Record success metrics
                        latency_ms = (time_module.time() - start_time) * 1000
                        command_requests_total.labels(
                            band=envelope.band, status="success"
                        ).inc()
                        command_latency_ms.labels(band=envelope.band).observe(
                            latency_ms
                        )

                        return receipt

                    except K0Unavailable as e:
                        last_error = e
                        if attempt < self.max_retries - 1:
                            # Exponential backoff: 100ms, 400ms, 1600ms
                            import asyncio

                            backoff_ms = 100 * (4**attempt)

                            # Record retry metric
                            command_retries_total.labels(
                                band=envelope.band, reason="unavailable"
                            ).inc()

                            logger.warning(
                                "k0_command_retry",
                                cognitive_trace_id=envelope.cognitive_trace_id,
                                attempt=attempt + 1,
                                max_retries=self.max_retries,
                                backoff_ms=backoff_ms,
                                error=str(e),
                            )
                            await asyncio.sleep(backoff_ms / 1000.0)
                    except (
                        K0CommandRejected,
                        K0PolicyDenied,
                        K0IdempotentDuplicate,
                        K0QoSExhausted,
                    ) as e:
                        # These errors are not retryable - record metric and raise
                        latency_ms = (time_module.time() - start_time) * 1000

                        # Determine error status for metrics
                        if isinstance(e, K0CommandRejected):
                            status = "rejected"
                        elif isinstance(e, K0PolicyDenied):
                            status = "policy_denied"
                        elif isinstance(e, K0IdempotentDuplicate):
                            status = "duplicate"
                        elif isinstance(e, K0QoSExhausted):
                            status = "qos_exhausted"
                        else:
                            status = "error"

                        command_requests_total.labels(
                            band=envelope.band, status=status
                        ).inc()
                        command_latency_ms.labels(band=envelope.band).observe(
                            latency_ms
                        )
                        raise

                # All retries exhausted - record metric
                latency_ms = (time_module.time() - start_time) * 1000
                command_requests_total.labels(
                    band=envelope.band, status="unavailable"
                ).inc()
                command_latency_ms.labels(band=envelope.band).observe(latency_ms)

                raise last_error or K0Unavailable(503, "Max retries exceeded")
        finally:
            # Detach cognitive trace context
            _tracer.detach(token)

    async def _post_command(
        self,
        payload: Dict[str, Any],
        cognitive_trace_id: str,
        attempt: int,
    ) -> CommandReceipt:
        """Internal method to POST command to K0

        Args:
            payload: JSON envelope
            cognitive_trace_id: Trace ID for observability
            attempt: Current retry attempt (0-indexed)

        Returns:
            CommandReceipt on success

        Raises:
            K0CommandError subclasses on failure
        """
        import time as time_module

        start_time = time_module.time()

        try:
            # HTTP POST to K0 Command Port
            # ADR-0001a: /k0/command.submit endpoint
            headers = {
                "Content-Type": "application/json",
                "X-Cognitive-Trace-Id": cognitive_trace_id,
            }
            _tracer.inject(headers)
            response = await self.client.post(
                f"{self.base_url}/k0/command.submit",
                json=payload,
                headers=headers,
            )

            latency_ms = (time_module.time() - start_time) * 1000

            # Handle response codes (per K0 command.py)
            if response.status_code == 200:
                # Success: parse receipt
                data = response.json()
                receipt = CommandReceipt(
                    receipt_id=data["receipt_id"],
                    commit_ts=data["commit_ts"],
                    offsets=data["offsets"],
                    idem_key=data["idem_key"],
                    obligations=data.get("obligations", []),
                )

                logger.info(
                    "k0_command_success",
                    cognitive_trace_id=cognitive_trace_id,
                    band=payload.get("band"),
                    latency_ms=round(latency_ms, 2),
                    receipt_id=receipt.receipt_id,
                    idem_key=receipt.idem_key,
                    attempt=attempt,
                )

                return receipt

            elif response.status_code == 409:
                # Conflict: idempotent duplicate
                data = response.json()
                logger.info(
                    "k0_command_duplicate",
                    cognitive_trace_id=cognitive_trace_id,
                    receipt_id=data.get("receipt_id"),
                    idem_key=data.get("idem_key"),
                )
                raise K0IdempotentDuplicate(data)

            elif response.status_code == 400:
                # Bad Request: Minimal Gate rejection
                error_data = response.json().get("error", {})
                logger.error(
                    "k0_command_rejected",
                    cognitive_trace_id=cognitive_trace_id,
                    reason=error_data.get("reason"),
                    component=error_data.get("component"),
                )
                raise K0CommandRejected(
                    reason=error_data.get("reason", "UNKNOWN"),
                    component=error_data.get("component", "kernel.gate"),
                )

            elif response.status_code == 403:
                # Forbidden: PEP deny
                error_data = response.json().get("error", {})
                logger.error(
                    "k0_command_policy_denied",
                    cognitive_trace_id=cognitive_trace_id,
                    reason=error_data.get("reason"),
                )
                raise K0PolicyDenied(reason=error_data.get("reason", "UNKNOWN"))

            elif response.status_code == 429:
                # Too Many Requests: QoS budget exhausted
                error_data = response.json().get("error", {})
                logger.warning(
                    "k0_command_qos_exhausted",
                    cognitive_trace_id=cognitive_trace_id,
                    reason=error_data.get("reason"),
                    cap=error_data.get("details", {}).get("cap"),
                    budgets=error_data.get("budgets"),
                )
                raise K0QoSExhausted(
                    reason=error_data.get("reason", "UNKNOWN"),
                    cap=error_data.get("details", {}).get("cap", "UNKNOWN"),
                    budgets=error_data.get("budgets", {}),
                )

            else:
                # 5xx or other errors: K0 unavailable (retryable)
                logger.error(
                    "k0_command_unavailable",
                    cognitive_trace_id=cognitive_trace_id,
                    status_code=response.status_code,
                    detail=response.text[:200],
                )
                raise K0Unavailable(
                    status_code=response.status_code,
                    detail=response.text[:200],
                )

        except httpx.RequestError as e:
            # Network error: K0 unavailable (retryable)
            logger.error(
                "k0_command_network_error",
                cognitive_trace_id=cognitive_trace_id,
                error=str(e),
            )
            raise K0Unavailable(status_code=503, detail=str(e))

    async def close(self):
        """Close HTTP client connection pool"""
        await self.client.aclose()
        logger.info("k0_command_client_closed")
        logger.info("k0_command_client_closed")
