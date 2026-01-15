"""
Capability Fabric - Request/reply by capability name.

The CapabilityFabric provides a capability-based request/reply layer
that sits above the event bus. It enables modules to invoke capabilities
without knowing the concrete provider implementation.

Part of the Capability Mesh Architecture (ADR-K004).
Layer 2: CapabilityFabric

Production Features:
- Real timeout enforcement via ThreadPoolExecutor (handlers can't block forever)
- Thread-safe pending requests and stats (guarded by locks)
- Monotonic timing for clock-safe deadlines
- Deadline propagation for downstream budget management

Related:
- k0/fabric/registry.py: CapabilityRegistry
- k0/fabric/messages.py: CapabilityRequest, CapabilityResponse
- docs/architecture/decisions-K0/k004-capability-mesh-architecture.md
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any

from k0.fabric.messages import CapabilityRequest, CapabilityResponse, RequestStatus
from k0.fabric.registry import CapabilityRegistry, ResolutionStrategy, get_capability_registry

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Default thread pool for handler execution with timeout enforcement
_DEFAULT_MAX_WORKERS = 4


class CapabilityNotFoundError(Exception):
    """Raised when a capability cannot be resolved."""

    def __init__(self, capability: str):
        self.capability = capability
        super().__init__(f"Capability not found: {capability}")


class CapabilityTimeoutError(Exception):
    """Raised when a capability request times out."""

    def __init__(self, capability: str, timeout_ms: float):
        self.capability = capability
        self.timeout_ms = timeout_ms
        super().__init__(f"Capability {capability} timed out after {timeout_ms:.1f}ms")


class CapabilityInvocationError(Exception):
    """Raised when a capability invocation fails."""

    def __init__(self, capability: str, provider_id: str, error: str):
        self.capability = capability
        self.provider_id = provider_id
        self.error = error
        super().__init__(f"Capability {capability} failed ({provider_id}): {error}")


class CapabilityFabric:
    """
    Capability Fabric for request/reply by capability name.

    Provides a synchronous request/reply pattern for invoking capabilities.
    Handles provider resolution, timeout enforcement, and metrics collection.

    Thread Safety:
        All public methods are thread-safe. The fabric uses locks to guard
        pending requests and statistics, and a ThreadPoolExecutor for
        timeout-enforced handler execution.

    Timeout Enforcement:
        Handlers are executed in a thread pool with real timeout enforcement.
        If a handler stalls beyond the deadline, a TimeoutError is raised and
        the request returns a TIMEOUT response.

    Example:
        fabric = CapabilityFabric.get_instance()

        # Invoke by capability name
        result = fabric.invoke(
            "score_salience",
            content="Hello world",
            participants=["Alice"],
        )

        # Or with full request control
        response = fabric.call(
            CapabilityRequest(
                capability="score_salience",
                payload={"content": "Hello"},
                timeout_ms=50,
            )
        )
    """

    _instance: CapabilityFabric | None = None
    _instance_lock: threading.Lock = threading.Lock()

    def __init__(
        self,
        registry: CapabilityRegistry | None = None,
        max_workers: int = _DEFAULT_MAX_WORKERS,
    ):
        """
        Initialize the fabric.

        Args:
            registry: Optional registry instance (uses global if not provided)
            max_workers: Max threads for handler execution (default: 4)
        """
        self._registry = registry or get_capability_registry()
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="fabric-")

        # Thread-safe state
        self._lock = threading.Lock()
        self._pending_requests: dict[str, CapabilityRequest] = {}
        self._total_calls: int = 0
        self._total_errors: int = 0
        self._total_timeouts: int = 0

    @classmethod
    def get_instance(cls) -> CapabilityFabric:
        """Get the singleton fabric instance (thread-safe)."""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton (for testing)."""
        with cls._instance_lock:
            if cls._instance is not None:
                cls._instance.shutdown()
            cls._instance = None

    def shutdown(self) -> None:
        """Shutdown the executor (call on cleanup)."""
        self._executor.shutdown(wait=False)

    @property
    def registry(self) -> CapabilityRegistry:
        """Get the underlying capability registry."""
        return self._registry

    @property
    def pending_count(self) -> int:
        """Get the number of pending requests (thread-safe)."""
        with self._lock:
            return len(self._pending_requests)

    def _add_pending(self, request: CapabilityRequest) -> None:
        """Add request to pending (thread-safe)."""
        with self._lock:
            self._pending_requests[request.request_id] = request

    def _remove_pending(self, request_id: str) -> None:
        """Remove request from pending (thread-safe)."""
        with self._lock:
            self._pending_requests.pop(request_id, None)

    def _increment_stat(self, stat: str) -> None:
        """Increment a statistic counter (thread-safe)."""
        with self._lock:
            if stat == "calls":
                self._total_calls += 1
            elif stat == "errors":
                self._total_errors += 1
            elif stat == "timeouts":
                self._total_timeouts += 1

    def invoke(
        self,
        capability: str,
        timeout_ms: int = 100,
        caller_id: str | None = None,
        trace_id: str | None = None,
        strategy: ResolutionStrategy = ResolutionStrategy.PRIORITY,
        **kwargs: Any,
    ) -> Any:
        """
        Invoke a capability by name (convenience method).

        Args:
            capability: Capability name to invoke
            timeout_ms: Request timeout in milliseconds
            caller_id: Identifier of the calling module/pipeline
            trace_id: Distributed trace ID for observability
            strategy: Resolution strategy for multiple providers
            **kwargs: Arguments to pass to the capability handler

        Returns:
            Result from the capability handler

        Raises:
            CapabilityNotFoundError: If capability cannot be resolved
            CapabilityTimeoutError: If request times out
            CapabilityInvocationError: If handler raises an exception
        """
        request = CapabilityRequest(
            capability=capability,
            payload=kwargs,
            timeout_ms=timeout_ms,
            caller_id=caller_id,
            trace_id=trace_id,
        )

        response = self.call(request, strategy=strategy)

        # Map response status to appropriate exception
        if response.is_success:
            return response.result
        elif response.is_timeout:
            raise CapabilityTimeoutError(capability, response.timeout_ms or timeout_ms)
        elif response.error_message and "not found" in response.error_message.lower():
            # Raise specific not-found exception for clean ergonomics
            raise CapabilityNotFoundError(capability)
        else:
            raise CapabilityInvocationError(
                capability,
                response.provider_id or "unknown",
                response.error_message or "Unknown error",
            )

    def call(
        self,
        request: CapabilityRequest,
        strategy: ResolutionStrategy = ResolutionStrategy.PRIORITY,
    ) -> CapabilityResponse:
        """
        Execute a capability request (full control method).

        Timeout Enforcement:
            Handler is executed via ThreadPoolExecutor with real timeout.
            If handler exceeds remaining deadline, a TIMEOUT response is returned.

        Args:
            request: The capability request to execute
            strategy: Resolution strategy for multiple providers

        Returns:
            CapabilityResponse with result or error
        """
        self._increment_stat("calls")
        self._add_pending(request)

        try:
            # Resolve capability to provider
            provider = self._registry.resolve(request.capability, strategy)

            if provider is None:
                self._increment_stat("errors")
                return CapabilityResponse.error(
                    request_id=request.request_id,
                    error=f"Capability not found: {request.capability}",
                )

            # Check if handler is bound
            if provider.handler is None:
                self._increment_stat("errors")
                return CapabilityResponse.error(
                    request_id=request.request_id,
                    error=f"No handler bound for capability: {request.capability}",
                    provider_id=provider.provider_id,
                )

            # Check timeout before invocation
            remaining = request.remaining_ms()
            if remaining <= 0:
                self._increment_stat("timeouts")
                return CapabilityResponse.timeout(
                    request_id=request.request_id,
                    timeout_ms=request.timeout_ms,
                    e2e_ms=request.elapsed_ms(),
                )

            # Submit handler to executor with real timeout enforcement
            handler_start = time.monotonic()
            future = self._executor.submit(provider.handler, **request.payload)

            try:
                # Wait with timeout (remaining budget in seconds)
                timeout_sec = remaining / 1000.0
                result = future.result(timeout=timeout_sec)
                handler_ms = (time.monotonic() - handler_start) * 1000.0
                e2e_ms = request.elapsed_ms()

                # Record metrics with richer tags
                self._registry.record_call(
                    request.capability,
                    provider.provider_id,
                    handler_ms,
                    error=False,
                    status=RequestStatus.SUCCESS.value,
                    caller_id=request.caller_id,
                    trace_id=request.trace_id,
                    strategy=strategy.value,
                )

                logger.debug(
                    "Capability %s invoked via %s in %.2fms (e2e: %.2fms) [caller=%s, trace=%s]",
                    request.capability,
                    provider.provider_id,
                    handler_ms,
                    e2e_ms,
                    request.caller_id,
                    request.trace_id,
                )

                return CapabilityResponse.success(
                    request_id=request.request_id,
                    result=result,
                    provider_id=provider.provider_id,
                    handler_ms=handler_ms,
                    e2e_ms=e2e_ms,
                )

            except TimeoutError:
                # Real timeout - handler exceeded deadline
                handler_ms = (time.monotonic() - handler_start) * 1000.0
                e2e_ms = request.elapsed_ms()
                self._increment_stat("timeouts")

                # Record timeout with richer tags
                self._registry.record_call(
                    request.capability,
                    provider.provider_id,
                    handler_ms,
                    error=True,
                    status=RequestStatus.TIMEOUT.value,
                    caller_id=request.caller_id,
                    trace_id=request.trace_id,
                    strategy=strategy.value,
                )

                logger.warning(
                    "Capability %s timed out via %s after %.2fms (budget: %.2fms) [caller=%s]",
                    request.capability,
                    provider.provider_id,
                    handler_ms,
                    request.timeout_ms,
                    request.caller_id,
                )

                # Note: The handler may still be running in the thread pool.
                # We can't forcibly kill it, but the response is returned immediately.
                return CapabilityResponse.timeout(
                    request_id=request.request_id,
                    timeout_ms=request.timeout_ms,
                    e2e_ms=e2e_ms,
                )

            except Exception as e:
                handler_ms = (time.monotonic() - handler_start) * 1000.0
                e2e_ms = request.elapsed_ms()
                self._increment_stat("errors")

                # Record error with richer tags
                self._registry.record_call(
                    request.capability,
                    provider.provider_id,
                    handler_ms,
                    error=True,
                    status=RequestStatus.ERROR.value,
                    caller_id=request.caller_id,
                    trace_id=request.trace_id,
                    strategy=strategy.value,
                )

                logger.warning(
                    "Capability %s failed via %s after %.2fms: %s [caller=%s]",
                    request.capability,
                    provider.provider_id,
                    handler_ms,
                    str(e),
                    request.caller_id,
                )

                return CapabilityResponse.error(
                    request_id=request.request_id,
                    error=str(e),
                    provider_id=provider.provider_id,
                    handler_ms=handler_ms,
                    e2e_ms=e2e_ms,
                )

        finally:
            # Remove from pending (thread-safe)
            self._remove_pending(request.request_id)

    def has_capability(self, capability: str) -> bool:
        """Check if a capability is registered."""
        return self._registry.has_capability(capability)

    def list_capabilities(self) -> list[str]:
        """List all registered capabilities."""
        return self._registry.list_capabilities()

    def get_stats(self) -> dict[str, Any]:
        """Get fabric statistics (thread-safe)."""
        registry_stats = self._registry.get_stats()
        with self._lock:
            return {
                "total_calls": self._total_calls,
                "total_errors": self._total_errors,
                "total_timeouts": self._total_timeouts,
                "pending_requests": len(self._pending_requests),
                "registry": registry_stats,
            }


# Global accessor
_capability_fabric: CapabilityFabric | None = None


def get_capability_fabric() -> CapabilityFabric:
    """Get the global CapabilityFabric instance."""
    return CapabilityFabric.get_instance()


def reset_capability_fabric() -> None:
    """Reset the global fabric instance (for testing)."""
    CapabilityFabric.reset_instance()
