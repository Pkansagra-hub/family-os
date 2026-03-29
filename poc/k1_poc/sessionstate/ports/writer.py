"""
IWriterPort - Single Writer Pattern Interface
===============================================

IMPLEMENTATION PLAN REFERENCE: docs/plans/sessionstate-implementation-plan.md
EPIC: 3.3 Define Writer Port
ISSUE: 3.3.1

ADRs:
- ADR-0017g: Single-Writer Concurrency Pattern

==============================================================================
SPECIFICATION
==============================================================================

PURPOSE:
    Enforce single-writer pattern for SessionState mutations.
    Only Concierge should write to SessionState. Sub-agents propose
    deltas to Concierge, who applies them via this port.

SINGLE WRITER PATTERN:
    - Concierge is the ONLY authorized writer
    - Sub-agents propose deltas, don't write directly
    - MutationGuard validates capacity pre-write
    - Rejected mutations return detailed error

DELTA FLOW:
    Sub-agent: "I want to add belief X"
        ↓
    Concierge: Aggregates delta with others
        ↓
    IWriterPort.request_mutation()
        ↓
    MutationGuard.preflight() → Approve/Reject
        ↓
    Section.apply() (if approved)
        ↓
    SizeTracker.update()
        ↓
    IEventPort.emit(MutationApprovedEvent or MutationRejectedEvent)

IMPLEMENTATIONS:
    - DirectWriterAdapter: Direct mutation (standalone/testing)
    - ConciergeAdapter: Full Concierge integration (future)

==============================================================================
INTERFACE: IWriterPort
==============================================================================
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# =============================================================================
# ENUMS
# =============================================================================


class MutationPriority(str, Enum):
    """
    Priority levels for mutation requests.

    Used for ordering in batch processing and queue management.
    """

    CRITICAL = "critical"  # Control section updates, emergency
    HIGH = "high"  # User-facing operations (beliefs, history)
    NORMAL = "normal"  # Standard operations
    LOW = "low"  # Background operations (telemetry)
    DEFERRED = "deferred"  # Can be delayed (persona calibration)


class MutationStatus(str, Enum):
    """
    Status of a mutation request.

    Tracks the lifecycle of a mutation through the system.
    """

    PENDING = "pending"  # Awaiting processing
    VALIDATING = "validating"  # In preflight validation
    APPROVED = "approved"  # Passed validation, applying
    APPLIED = "applied"  # Successfully applied
    REJECTED = "rejected"  # Failed validation
    FAILED = "failed"  # Error during application
    CANCELLED = "cancelled"  # Cancelled before processing


class RejectionCategory(str, Enum):
    """
    Categories of mutation rejection.

    Enables programmatic handling of different rejection types.
    """

    CAPACITY = "capacity"  # Size limits exceeded
    AUTHORIZATION = "authorization"  # Writer not authorized
    VALIDATION = "validation"  # Invalid section/operation
    LOCKED = "locked"  # Section locked for eviction/migration
    EMERGENCY = "emergency"  # Emergency mode active
    INTERNAL = "internal"  # Internal error


# =============================================================================
# DATACLASSES
# =============================================================================


@dataclass
class MutationRequest:
    """
    A request to mutate SessionState.

    Attributes:
        request_id: Unique request identifier (UUID)
        section: Target section name
        operation: Operation type (set, append, update, clear, delete)
        data: Operation-specific data payload
        estimated_bytes: Estimated size change in bytes
        writer_id: ID of the writer (should be 'concierge' in production)
        cognitive_trace_id: Trace ID for distributed tracing
        priority: Request priority for ordering
        delegation_chain: Audit trail of delegation (agent -> concierge)
        created_at_ms: Request creation timestamp
        timeout_ms: Request timeout (0 = no timeout)
        metadata: Additional request metadata
    """

    request_id: str
    section: str
    operation: str
    data: Any
    estimated_bytes: int
    writer_id: str
    cognitive_trace_id: str
    priority: MutationPriority = MutationPriority.NORMAL
    delegation_chain: List[str] = field(default_factory=list)
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    timeout_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "request_id": self.request_id,
            "section": self.section,
            "operation": self.operation,
            "data": self.data,
            "estimated_bytes": self.estimated_bytes,
            "writer_id": self.writer_id,
            "cognitive_trace_id": self.cognitive_trace_id,
            "priority": self.priority.value,
            "delegation_chain": self.delegation_chain,
            "created_at_ms": self.created_at_ms,
            "timeout_ms": self.timeout_ms,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MutationRequest:
        """Create from dictionary."""
        return cls(
            request_id=data["request_id"],
            section=data["section"],
            operation=data["operation"],
            data=data.get("data"),
            estimated_bytes=data.get("estimated_bytes", 0),
            writer_id=data["writer_id"],
            cognitive_trace_id=data["cognitive_trace_id"],
            priority=MutationPriority(data.get("priority", "normal")),
            delegation_chain=data.get("delegation_chain", []),
            created_at_ms=data.get("created_at_ms", int(time.time() * 1000)),
            timeout_ms=data.get("timeout_ms", 0),
            metadata=data.get("metadata", {}),
        )

    @staticmethod
    def create(
        section: str,
        operation: str,
        data: Any,
        writer_id: str,
        cognitive_trace_id: str,
        estimated_bytes: int = 0,
        priority: MutationPriority = MutationPriority.NORMAL,
        delegated_from: Optional[str] = None,
    ) -> MutationRequest:
        """
        Factory method to create a new mutation request.

        Args:
            section: Target section name
            operation: Operation type
            data: Operation data
            writer_id: ID of the writer
            cognitive_trace_id: Trace ID
            estimated_bytes: Size estimate (0 = auto-calculate)
            priority: Request priority
            delegated_from: Agent that delegated this request

        Returns:
            New MutationRequest instance
        """
        chain = [delegated_from] if delegated_from else []
        return MutationRequest(
            request_id=str(uuid.uuid4()),
            section=section,
            operation=operation,
            data=data,
            estimated_bytes=estimated_bytes,
            writer_id=writer_id,
            cognitive_trace_id=cognitive_trace_id,
            priority=priority,
            delegation_chain=chain,
        )

    def is_expired(self) -> bool:
        """Check if request has expired."""
        if self.timeout_ms <= 0:
            return False
        elapsed = int(time.time() * 1000) - self.created_at_ms
        return elapsed > self.timeout_ms


@dataclass
class MutationResponse:
    """
    Response to a mutation request.

    Attributes:
        request_id: Original request ID
        status: Final status of the mutation
        approved: Whether mutation was approved and applied
        new_size_bytes: New section size (if approved)
        bytes_delta: Actual change in bytes
        available_bytes: Remaining capacity after mutation
        section: Target section (echoed from request)
        operation: Operation type (echoed from request)
        reason: Rejection/failure reason (if not approved)
        rejection_category: Category of rejection for programmatic handling
        error: Error message (if error occurred)
        duration_ms: Processing duration
        timestamp_ms: Response timestamp
    """

    request_id: str
    status: MutationStatus
    approved: bool
    new_size_bytes: int = 0
    bytes_delta: int = 0
    available_bytes: int = 0
    section: str = ""
    operation: str = ""
    reason: str = ""
    rejection_category: Optional[RejectionCategory] = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "request_id": self.request_id,
            "status": self.status.value,
            "approved": self.approved,
            "new_size_bytes": self.new_size_bytes,
            "bytes_delta": self.bytes_delta,
            "available_bytes": self.available_bytes,
            "section": self.section,
            "operation": self.operation,
            "reason": self.reason,
            "rejection_category": (
                self.rejection_category.value if self.rejection_category else None
            ),
            "error": self.error,
            "duration_ms": round(self.duration_ms, 3),
            "timestamp_ms": self.timestamp_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MutationResponse:
        """Create from dictionary."""
        return cls(
            request_id=data["request_id"],
            status=MutationStatus(data["status"]),
            approved=data["approved"],
            new_size_bytes=data.get("new_size_bytes", 0),
            bytes_delta=data.get("bytes_delta", 0),
            available_bytes=data.get("available_bytes", 0),
            section=data.get("section", ""),
            operation=data.get("operation", ""),
            reason=data.get("reason", ""),
            rejection_category=(
                RejectionCategory(data["rejection_category"])
                if data.get("rejection_category")
                else None
            ),
            error=data.get("error"),
            duration_ms=data.get("duration_ms", 0.0),
            timestamp_ms=data.get("timestamp_ms", int(time.time() * 1000)),
        )

    @staticmethod
    def approved(
        request_id: str,
        section: str,
        operation: str,
        new_size_bytes: int,
        bytes_delta: int,
        available_bytes: int,
        duration_ms: float = 0.0,
    ) -> MutationResponse:
        """Factory for approved mutation response."""
        return MutationResponse(
            request_id=request_id,
            status=MutationStatus.APPLIED,
            approved=True,
            new_size_bytes=new_size_bytes,
            bytes_delta=bytes_delta,
            available_bytes=available_bytes,
            section=section,
            operation=operation,
            duration_ms=duration_ms,
        )

    @staticmethod
    def rejected(
        request_id: str,
        section: str,
        operation: str,
        reason: str,
        category: RejectionCategory,
        available_bytes: int = 0,
        duration_ms: float = 0.0,
    ) -> MutationResponse:
        """Factory for rejected mutation response."""
        return MutationResponse(
            request_id=request_id,
            status=MutationStatus.REJECTED,
            approved=False,
            section=section,
            operation=operation,
            reason=reason,
            rejection_category=category,
            available_bytes=available_bytes,
            duration_ms=duration_ms,
        )

    @staticmethod
    def failed(
        request_id: str,
        section: str,
        operation: str,
        error: str,
        duration_ms: float = 0.0,
    ) -> MutationResponse:
        """Factory for failed mutation response."""
        return MutationResponse(
            request_id=request_id,
            status=MutationStatus.FAILED,
            approved=False,
            section=section,
            operation=operation,
            error=error,
            duration_ms=duration_ms,
        )

    @staticmethod
    def cancelled(request_id: str, reason: str = "Cancelled") -> MutationResponse:
        """Factory for cancelled mutation response."""
        return MutationResponse(
            request_id=request_id,
            status=MutationStatus.CANCELLED,
            approved=False,
            reason=reason,
        )


@dataclass
class BatchRequest:
    """
    A batch of mutation requests.

    Attributes:
        batch_id: Unique batch identifier
        requests: List of mutation requests
        writer_id: ID of the batch writer
        cognitive_trace_id: Shared trace ID for the batch
        stop_on_rejection: Whether to stop on first rejection
        created_at_ms: Batch creation timestamp
    """

    batch_id: str
    requests: List[MutationRequest]
    writer_id: str
    cognitive_trace_id: str
    stop_on_rejection: bool = False
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "batch_id": self.batch_id,
            "requests": [r.to_dict() for r in self.requests],
            "writer_id": self.writer_id,
            "cognitive_trace_id": self.cognitive_trace_id,
            "stop_on_rejection": self.stop_on_rejection,
            "created_at_ms": self.created_at_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BatchRequest:
        """Create from dictionary."""
        return cls(
            batch_id=data["batch_id"],
            requests=[MutationRequest.from_dict(r) for r in data["requests"]],
            writer_id=data["writer_id"],
            cognitive_trace_id=data["cognitive_trace_id"],
            stop_on_rejection=data.get("stop_on_rejection", False),
            created_at_ms=data.get("created_at_ms", int(time.time() * 1000)),
        )

    @staticmethod
    def create(
        requests: List[MutationRequest],
        writer_id: str,
        cognitive_trace_id: str,
        stop_on_rejection: bool = False,
    ) -> BatchRequest:
        """Factory to create a new batch request."""
        return BatchRequest(
            batch_id=str(uuid.uuid4()),
            requests=requests,
            writer_id=writer_id,
            cognitive_trace_id=cognitive_trace_id,
            stop_on_rejection=stop_on_rejection,
        )


@dataclass
class BatchResult:
    """
    Result of a batch mutation request.

    Attributes:
        batch_id: Original batch ID
        total_requests: Number of requests in batch
        applied_count: Number successfully applied
        rejected_count: Number rejected
        failed_count: Number failed
        cancelled_count: Number cancelled
        responses: Individual responses in order
        total_bytes_delta: Total bytes changed
        duration_ms: Total processing duration
        stopped_early: Whether batch stopped before completing
        timestamp_ms: Result timestamp
    """

    batch_id: str
    total_requests: int
    applied_count: int
    rejected_count: int
    failed_count: int
    cancelled_count: int
    responses: List[MutationResponse]
    total_bytes_delta: int = 0
    duration_ms: float = 0.0
    stopped_early: bool = False
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "batch_id": self.batch_id,
            "total_requests": self.total_requests,
            "applied_count": self.applied_count,
            "rejected_count": self.rejected_count,
            "failed_count": self.failed_count,
            "cancelled_count": self.cancelled_count,
            "responses": [r.to_dict() for r in self.responses],
            "total_bytes_delta": self.total_bytes_delta,
            "duration_ms": round(self.duration_ms, 3),
            "stopped_early": self.stopped_early,
            "timestamp_ms": self.timestamp_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> BatchResult:
        """Create from dictionary."""
        return cls(
            batch_id=data["batch_id"],
            total_requests=data["total_requests"],
            applied_count=data["applied_count"],
            rejected_count=data["rejected_count"],
            failed_count=data["failed_count"],
            cancelled_count=data["cancelled_count"],
            responses=[MutationResponse.from_dict(r) for r in data["responses"]],
            total_bytes_delta=data.get("total_bytes_delta", 0),
            duration_ms=data.get("duration_ms", 0.0),
            stopped_early=data.get("stopped_early", False),
            timestamp_ms=data.get("timestamp_ms", int(time.time() * 1000)),
        )

    @property
    def all_applied(self) -> bool:
        """Check if all requests were applied."""
        return self.applied_count == self.total_requests

    @property
    def success_rate(self) -> float:
        """Calculate success rate (0.0 to 1.0)."""
        if self.total_requests == 0:
            return 1.0
        return self.applied_count / self.total_requests

    @staticmethod
    def from_responses(
        batch_id: str,
        responses: List[MutationResponse],
        duration_ms: float = 0.0,
        stopped_early: bool = False,
    ) -> BatchResult:
        """Factory to create BatchResult from list of responses."""
        applied = sum(1 for r in responses if r.status == MutationStatus.APPLIED)
        rejected = sum(1 for r in responses if r.status == MutationStatus.REJECTED)
        failed = sum(1 for r in responses if r.status == MutationStatus.FAILED)
        cancelled = sum(1 for r in responses if r.status == MutationStatus.CANCELLED)
        total_delta = sum(r.bytes_delta for r in responses if r.approved)

        return BatchResult(
            batch_id=batch_id,
            total_requests=len(responses),
            applied_count=applied,
            rejected_count=rejected,
            failed_count=failed,
            cancelled_count=cancelled,
            responses=responses,
            total_bytes_delta=total_delta,
            duration_ms=duration_ms,
            stopped_early=stopped_early,
        )


@dataclass
class WriterAuthorization:
    """
    Authorization result for a writer.

    Attributes:
        writer_id: ID of the writer being authorized
        authorized: Whether writer is authorized
        permissions: List of granted permissions
        reason: Rejection reason if not authorized
    """

    writer_id: str
    authorized: bool
    permissions: List[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "writer_id": self.writer_id,
            "authorized": self.authorized,
            "permissions": self.permissions,
            "reason": self.reason,
        }


# =============================================================================
# INTERFACE
# =============================================================================


class IWriterPort(ABC):
    """
    Interface for single-writer pattern enforcement.

    SessionState uses this port to:
    - Accept mutation requests from Concierge
    - Enforce single-writer pattern
    - Batch mutations for efficiency
    - Track delegation chains for audit

    Thread Safety:
        Implementations MUST be thread-safe.
        Use locks or queues for mutation serialization.

    Example:
        class DirectWriterAdapter(IWriterPort):
            def request_mutation(self, request: MutationRequest) -> MutationResponse:
                # Validate authorization
                auth = self.validate_writer(request.writer_id)
                if not auth.authorized:
                    return MutationResponse.rejected(
                        request_id=request.request_id,
                        section=request.section,
                        operation=request.operation,
                        reason=auth.reason,
                        category=RejectionCategory.AUTHORIZATION,
                    )

                # Check capacity via MutationGuard
                approval = self._guard.preflight(
                    request.section,
                    request.operation,
                    request.estimated_bytes,
                )
                if not approval.approved:
                    return MutationResponse.rejected(
                        request_id=request.request_id,
                        section=request.section,
                        operation=request.operation,
                        reason=approval.reason,
                        category=RejectionCategory.CAPACITY,
                    )

                # Apply mutation
                result = self._manager.mutate(
                    request.section,
                    request.operation,
                    request.data,
                    request.estimated_bytes,
                )

                if result.success:
                    return MutationResponse.approved(
                        request_id=request.request_id,
                        section=request.section,
                        operation=request.operation,
                        new_size_bytes=result.new_size_bytes,
                        bytes_delta=result.bytes_delta,
                        available_bytes=result.available_bytes,
                    )
                else:
                    return MutationResponse.failed(
                        request_id=request.request_id,
                        section=request.section,
                        operation=request.operation,
                        error=result.error,
                    )
    """

    @property
    @abstractmethod
    def writer_id(self) -> str:
        """
        Get the ID of the authorized writer.

        Returns:
            str: Writer identifier (e.g., 'concierge', 'direct', 'test')

        Notes:
            - In production: 'concierge'
            - In standalone: 'direct'
            - In tests: 'test' or custom ID
        """
        pass

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """
        Check if writer port is connected and ready.

        Returns:
            bool: True if mutations can be processed

        Notes:
            - DirectWriterAdapter: Always True
            - ConciergeAdapter: True if Concierge is available
        """
        pass

    @abstractmethod
    def request_mutation(
        self,
        request: MutationRequest,
    ) -> MutationResponse:
        """
        Request a single mutation.

        Args:
            request: Mutation request with all details

        Returns:
            MutationResponse: Result with status, reason, and metrics

        Flow:
            1. Check request expiration
            2. Validate writer authorization
            3. Call MutationGuard.preflight()
            4. If approved, apply mutation via SessionStateManager
            5. Emit events (approved/rejected)
            6. Return response

        Thread Safety:
            Must serialize concurrent requests.

        Performance:
            Target: <5ms for typical mutations
        """
        pass

    @abstractmethod
    def batch_mutations(
        self,
        batch: BatchRequest,
    ) -> BatchResult:
        """
        Process multiple mutations in batch.

        Args:
            batch: Batch of mutation requests

        Returns:
            BatchResult: Aggregated results with per-request responses

        Behavior:
            - Mutations applied in order (by list position)
            - Priority within batch is advisory (for logging)
            - If stop_on_rejection=True: stop at first rejection
            - If stop_on_rejection=False: continue with remaining
            - All mutations share same cognitive_trace_id

        Use case:
            Turn completion: Update beliefs, history, telemetry atomically

        Performance:
            Target: <10ms for batch of 5 mutations
        """
        pass

    @abstractmethod
    def validate_writer(self, writer_id: str) -> WriterAuthorization:
        """
        Validate that a writer is authorized.

        Args:
            writer_id: ID of writer to validate

        Returns:
            WriterAuthorization: Authorization result with permissions

        Authorization Rules:
            - In standalone: All writers authorized
            - In production: Only 'concierge' authorized
            - Permissions: 'read', 'write', 'batch', 'admin'
        """
        pass

    def cancel_request(self, request_id: str) -> bool:
        """
        Cancel a pending mutation request.

        Args:
            request_id: ID of request to cancel

        Returns:
            bool: True if cancelled, False if not found or already processed

        Notes:
            Default implementation returns False (no queueing).
            Override in adapters that queue requests.
        """
        return False

    def get_pending_count(self) -> int:
        """
        Get number of pending mutation requests.

        Returns:
            int: Number of requests awaiting processing

        Notes:
            Default implementation returns 0 (no queueing).
            Override in adapters that queue requests.
        """
        return 0

    def get_stats(self) -> Dict[str, Any]:
        """
        Get writer port statistics.

        Returns:
            dict: Statistics including:
                - total_requests: Total requests received
                - applied_count: Successfully applied
                - rejected_count: Rejected by guard
                - failed_count: Failed during apply
                - avg_duration_ms: Average processing time
                - pending_count: Currently pending

        Notes:
            Default implementation returns empty dict.
            Override for production monitoring.
        """
        return {}


# =============================================================================
# IMPLEMENTATION NOTES
# =============================================================================
"""
1. SINGLE WRITER ENFORCEMENT:
   - Only Concierge should have IWriterPort instance
   - Sub-agents propose deltas to Concierge
   - Concierge aggregates and applies via this port
   - Delegation chain tracks the audit trail

2. MUTATION FLOW:
   Sub-agent: "I want to add belief X"
       ↓
   Concierge: Aggregates delta with others
       ↓
   IWriterPort.request_mutation()
       ↓
   validate_writer() → Authorization check
       ↓
   MutationGuard.preflight() → Capacity check
       ↓
   SessionStateManager.mutate() (if approved)
       ↓
   IEventPort.emit(MutationApprovedEvent or MutationRejectedEvent)

3. BATCH SEMANTICS:
   - Not atomic by default (partial success allowed)
   - Applied in list order
   - stop_on_rejection controls early termination
   - All responses returned regardless of failures

4. REJECTION CATEGORIES:
   - CAPACITY: Size limits exceeded
   - AUTHORIZATION: Writer not allowed
   - VALIDATION: Invalid section/operation
   - LOCKED: Section under eviction/migration
   - EMERGENCY: Emergency mode blocks all writes
   - INTERNAL: Unexpected errors

5. IMPLEMENTATIONS TO CREATE:
   - DirectWriterAdapter (k1/sessionstate/adapters/direct_writer.py)
     Purpose: Standalone operation, testing
     Authorization: All writers allowed

   - ConciergeAdapter (k1/concierge/adapters/sessionstate.py) - FUTURE
     Purpose: Production Concierge integration
     Authorization: Only Concierge allowed

6. TESTING:
   DirectWriterAdapter allows direct mutation for tests.
   Use with InMemoryStorageAdapter and LocalEventAdapter.

   Example:
       adapter = DirectWriterAdapter(manager)
       request = MutationRequest.create(
           section="beliefs_active",
           operation="append",
           data={"fact": "User likes coffee"},
           writer_id="test",
           cognitive_trace_id="trace-123",
       )
       response = adapter.request_mutation(request)
       assert response.approved

7. OBSERVABILITY:
   - All requests should log with cognitive_trace_id
   - Rejections should log with category and reason
   - Batch operations should log start/end with metrics
   - get_stats() enables monitoring dashboards
"""
