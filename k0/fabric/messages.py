"""
Capability Fabric Messages.

Dataclasses for request/response communication via CapabilityFabric.
Part of the Capability Mesh Architecture (ADR-K004).

Timing Safety:
- Uses time.monotonic() for deadlines and latency (clock-jump safe)
- Wall time (time.time()) stored only for logging, never for timers
- Deadline propagation via remaining_ms() for downstream budgeting

Related:
- k0/fabric/registry.py: CapabilityRegistry
- k0/fabric/fabric.py: CapabilityFabric
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RequestStatus(str, Enum):
    """Status of a capability request."""

    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass
class CapabilityRequest:
    """
    Request to invoke a capability.

    Attributes:
        capability: Capability name to invoke (e.g., "score_salience")
        payload: Arguments to pass to the capability handler (copied on init)
        request_id: Unique request identifier for tracing
        timeout_ms: Request timeout in milliseconds
        caller_id: Identifier of the calling module/pipeline
        trace_id: Distributed trace ID for observability
        created_mono: Monotonic timestamp for safe deadline/latency calculations
        deadline_mono: Computed deadline (monotonic, clock-jump safe)
        created_wall: Wall-clock time for logging only (never use for timers)

    Example:
        request = CapabilityRequest(
            capability="score_salience",
            payload={"content": "Hello world", "participants": ["Alice"]},
            timeout_ms=50,
            caller_id="P02_WRITE",
        )
        # Downstream can check remaining budget:
        if request.remaining_ms() > 10:
            # Still have time for this operation
            ...
    """

    capability: str
    payload: dict[str, Any]
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timeout_ms: int = 100
    caller_id: str | None = None
    trace_id: str | None = None

    # Monotonic timing (safe for deadlines/latency, immune to clock jumps)
    created_mono: float = field(default_factory=time.monotonic)
    deadline_mono: float = field(init=False)

    # Wall time for logs only (never for deadlines)
    created_wall: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        """Compute fixed deadline and freeze payload."""
        # Compute deadline once at construction
        self.deadline_mono = self.created_mono + (self.timeout_ms / 1000.0)
        # Copy payload to prevent mutation by handlers affecting tracing/debug
        self.payload = dict(self.payload)

    def elapsed_ms(self) -> float:
        """Return elapsed time since request creation in milliseconds (monotonic)."""
        return (time.monotonic() - self.created_mono) * 1000.0

    def remaining_ms(self) -> float:
        """Return remaining time until deadline in milliseconds.

        Downstream handlers can use this for budget propagation:
            child_timeout = int(parent_request.remaining_ms() * 0.8)
        """
        return max(0.0, (self.deadline_mono - time.monotonic()) * 1000.0)

    def is_expired(self) -> bool:
        """Check if request has exceeded its deadline (monotonic, clock-safe)."""
        return time.monotonic() >= self.deadline_mono


@dataclass
class CapabilityResponse:
    """
    Response from a capability invocation.

    Attributes:
        request_id: Matching request identifier
        status: Response status (success, error, timeout)
        result: Result data (on success)
        error_message: Error message (on error/timeout)
        provider_id: ID of provider that handled the request
        handler_ms: Time spent in handler execution
        e2e_ms: End-to-end request latency (includes queue, routing, retries)
        timeout_ms: Original timeout value (set on timeout responses)

    Example:
        response = CapabilityResponse.success(
            request_id="abc-123",
            result={"score": 0.85},
            provider_id="salience.score",
            handler_ms=3.5,
            e2e_ms=5.2,
        )
    """

    request_id: str
    status: RequestStatus
    result: Any = None
    error_message: str | None = None
    provider_id: str | None = None
    handler_ms: float = 0.0  # Handler execution time
    e2e_ms: float = 0.0  # End-to-end latency (handler + overhead)
    timeout_ms: float | None = None  # Structured timeout info (set on TIMEOUT)

    @property
    def is_success(self) -> bool:
        """Check if response indicates success."""
        return self.status == RequestStatus.SUCCESS

    @property
    def is_error(self) -> bool:
        """Check if response indicates an error."""
        return self.status == RequestStatus.ERROR

    @property
    def is_timeout(self) -> bool:
        """Check if response indicates a timeout."""
        return self.status == RequestStatus.TIMEOUT

    @classmethod
    def success(
        cls,
        request_id: str,
        result: Any,
        provider_id: str,
        handler_ms: float,
        e2e_ms: float = 0.0,
    ) -> CapabilityResponse:
        """Create a success response."""
        return cls(
            request_id=request_id,
            status=RequestStatus.SUCCESS,
            result=result,
            provider_id=provider_id,
            handler_ms=handler_ms,
            e2e_ms=e2e_ms if e2e_ms > 0 else handler_ms,
        )

    @classmethod
    def error(
        cls,
        request_id: str,
        error: str,
        provider_id: str | None = None,
        handler_ms: float = 0.0,
        e2e_ms: float = 0.0,
    ) -> CapabilityResponse:
        """Create an error response."""
        return cls(
            request_id=request_id,
            status=RequestStatus.ERROR,
            error_message=error,
            provider_id=provider_id,
            handler_ms=handler_ms,
            e2e_ms=e2e_ms if e2e_ms > 0 else handler_ms,
        )

    @classmethod
    def timeout(
        cls,
        request_id: str,
        timeout_ms: float,
        e2e_ms: float = 0.0,
    ) -> CapabilityResponse:
        """Create a timeout response with structured timeout info."""
        return cls(
            request_id=request_id,
            status=RequestStatus.TIMEOUT,
            error_message=f"Request timed out after {timeout_ms:.1f}ms",
            timeout_ms=timeout_ms,
            e2e_ms=e2e_ms if e2e_ms > 0 else timeout_ms,
        )
