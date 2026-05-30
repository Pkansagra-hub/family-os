"""
k1.fabric.providers.base_provider -- CapabilityProvider protocol & base class (3.3.1).

Defines the common interface that ALL provider types implement.
This is the canonical location for the CapabilityProvider protocol.

Three methods:
  async execute(request, context, trace_id) -> CapabilityResult
  async health_check() -> ProviderHealth
  capabilities() -> list[str]

Also provides ``BaseProvider``, an abstract base with common boilerplate:
  - Timing and logging in execute()
  - Default health_check() returning UNKNOWN status
  - Config storage and provider_id property

References:
  - fabric_discussion.md Section 11 (Common Provider Interface)
  - Epic 3.3.1 in fabric-implementation-plan.md
  - provider_factory.py (ProviderFactory consumes CapabilityProvider)

Exports:
  CapabilityProvider     -- Protocol (structural subtype interface)
  BaseProvider           -- Abstract base with common boilerplate
  ProviderError          -- Base exception for provider operations
  ProviderExecutionError -- Execution-specific failure
  ProviderTimeoutError   -- Execution exceeded deadline
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Protocol

from k1.fabric.types import (
    CapabilityRequest,
    CapabilityResult,
    ExecutionContext,
    ProviderConfig,
    ProviderHealth,
    ProviderStatus,
)

logger = logging.getLogger(__name__)


def build_provider_metadata(
    request: CapabilityRequest,
    context: ExecutionContext,
) -> Dict[str, Any]:
    """Build reserved prompt/profile metadata for provider transports."""

    metadata: Dict[str, Any] = {}
    if context.prompt:
        metadata["__system_instructions__"] = context.prompt

    override: Dict[str, Any] = {}
    raw_override = (context.session_sections or {}).get("context_override")
    if isinstance(raw_override, dict):
        override = raw_override

    activity_profile = override.get("activity_profile")
    if isinstance(activity_profile, str) and activity_profile:
        metadata["__activity_profile__"] = activity_profile

    prompt_template = override.get("prompt_template") or request.prompt_template
    if prompt_template:
        metadata["__prompt_template__"] = prompt_template

    grounding_invocation = override.get("grounding_invocation")
    if isinstance(grounding_invocation, dict) and grounding_invocation:
        metadata["__grounding_invocation__"] = dict(grounding_invocation)

    return metadata


def attach_provider_metadata(
    params: Dict[str, Any],
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    """Attach reserved provider metadata without mutating the request params."""

    out = dict(params)
    if not metadata:
        return out

    existing = out.get("__metadata__")
    if isinstance(existing, dict):
        merged_metadata = dict(existing)
        merged_metadata.update(metadata)
    elif existing is not None:
        merged_metadata = {"__original_metadata__": existing}
        merged_metadata.update(metadata)
    else:
        merged_metadata = dict(metadata)

    out["__metadata__"] = merged_metadata
    return out


# ---------------------------------------------------------------------------
# CapabilityProvider Protocol (canonical definition)
# ---------------------------------------------------------------------------


class CapabilityProvider(Protocol):
    """
    Common interface for all provider types.

    All providers implement execute(), health_check(), capabilities().
    Defined as Protocol for structural subtyping (duck typing with
    type-checker support).

    Any class satisfying this interface can be used as a provider
    by ProviderFactory (3.1.4) and CircuitBreaker (3.4.1).

    References:
        - fabric_discussion.md Section 11
        - Epic 3.3.1
    """

    async def execute(
        self,
        request: CapabilityRequest,
        context: ExecutionContext,
        trace_id: str,
    ) -> CapabilityResult:
        """
        Execute the capability.

        Args:
            request: What to do (capability name, params).
            context: Assembled SessionState sections + prompt
                (from Context Builder 4.2.1).
            trace_id: cognitive_trace_id for observability.

        Returns:
            CapabilityResult with success/failure, data, timing.
        """
        ...

    async def health_check(self) -> ProviderHealth:
        """Check if the provider is healthy and responsive."""
        ...

    def capabilities(self) -> List[str]:
        """List of capability names this provider handles."""
        ...


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ProviderError(Exception):
    """Base exception for provider operations."""

    def __init__(self, provider_id: str, message: str) -> None:
        self.provider_id = provider_id
        super().__init__(f"[{provider_id}] {message}")


class ProviderExecutionError(ProviderError):
    """Raised when provider execution fails."""

    def __init__(
        self,
        provider_id: str,
        message: str,
        *,
        retriable: bool = False,
        error_code: str = "provider_error",
    ) -> None:
        self.retriable = retriable
        self.error_code = error_code
        super().__init__(provider_id, message)


class ProviderTimeoutError(ProviderError):
    """Raised when provider execution exceeds the deadline."""

    def __init__(self, provider_id: str, timeout_ms: int) -> None:
        self.timeout_ms = timeout_ms
        super().__init__(
            provider_id,
            f"Execution exceeded {timeout_ms}ms deadline",
        )


# ---------------------------------------------------------------------------
# BaseProvider (abstract base class with common boilerplate)
# ---------------------------------------------------------------------------


class BaseProvider(ABC):
    """
    Abstract base class for capability providers.

    Provides common boilerplate:
      - Config storage and property access
      - Timing + logging wrapper around execute()
      - Default health_check() returning UNKNOWN
      - capabilities() delegation to subclass

    Subclasses MUST implement:
      - _execute(request, context, trace_id) -> CapabilityResult
      - capabilities() -> list[str]

    Optionally override:
      - health_check() for real health probing

    Usage::

        class MCPProvider(BaseProvider):
            async def _execute(self, request, context, trace_id):
                # ... MCP-specific logic ...
                return CapabilityResult.success_result(...)

            def capabilities(self):
                return ["tool.execute.weather"]
    """

    __slots__ = ("_config",)

    def __init__(self, config: ProviderConfig) -> None:
        """
        Args:
            config: Provider configuration (endpoint, transport, limits).
        """
        self._config = config

    @property
    def config(self) -> ProviderConfig:
        """The provider's configuration."""
        return self._config

    @property
    def provider_id(self) -> str:
        """Shortcut for config.provider_id."""
        return self._config.provider_id

    @property
    def provider_type(self) -> str:
        """Shortcut for config.provider_type."""
        return self._config.provider_type

    # ======================================================================
    # Public API (final -- delegates to _execute)
    # ======================================================================

    async def execute(
        self,
        request: CapabilityRequest,
        context: ExecutionContext,
        trace_id: str,
    ) -> CapabilityResult:
        """
        Execute capability with timing, logging, and error handling.

        Delegates to ``_execute()`` which subclasses implement.
        Catches ``ProviderError`` and converts to CapabilityResult.failure.
        Catches unexpected exceptions as provider_error.

        Args:
            request: The capability request.
            context: Execution context (SessionState sections + prompt).
            trace_id: Cognitive trace ID for observability.

        Returns:
            CapabilityResult (never raises to caller).
        """
        start = time.monotonic()
        logger.debug(
            "[%s] execute: %s (trace=%s)",
            self.provider_id,
            request.capability_name,
            trace_id,
        )

        try:
            result = await self._execute(request, context, trace_id)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.debug(
                "[%s] execute complete: %s in %dms (success=%s)",
                self.provider_id,
                request.capability_name,
                elapsed_ms,
                result.success,
            )
            return result

        except ProviderTimeoutError as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.warning(
                "[%s] timeout: %s after %dms",
                self.provider_id,
                request.capability_name,
                elapsed_ms,
            )
            return CapabilityResult.timeout_result(
                request_id=request.request_id,
                timeout_ms=exc.timeout_ms,
                provider_id=self.provider_id,
                trace_id=trace_id,
                duration_ms=elapsed_ms,
            )

        except ProviderExecutionError as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.error(
                "[%s] execution error: %s (%s)",
                self.provider_id,
                request.capability_name,
                exc,
            )
            return CapabilityResult.failure_result(
                request_id=request.request_id,
                error_code=exc.error_code,
                error_message=str(exc),
                retriable=exc.retriable,
                provider_id=self.provider_id,
                trace_id=trace_id,
                duration_ms=elapsed_ms,
            )

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.error(
                "[%s] unexpected error: %s (%s: %s)",
                self.provider_id,
                request.capability_name,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return CapabilityResult.failure_result(
                request_id=request.request_id,
                error_code="provider_error",
                error_message=f"Unexpected error: {type(exc).__name__}: {exc}",
                retriable=False,
                provider_id=self.provider_id,
                trace_id=trace_id,
                duration_ms=elapsed_ms,
            )

    async def health_check(self) -> ProviderHealth:
        """
        Default health check: returns UNKNOWN status.

        Subclasses should override for real health probing
        (e.g., MCPProvider pings the MCP server, WASMProvider
        verifies module is loaded).
        """
        return ProviderHealth(
            provider_id=self.provider_id,
            status=ProviderStatus.UNKNOWN.value,
        )

    # ======================================================================
    # Abstract methods (subclasses MUST implement)
    # ======================================================================

    @abstractmethod
    async def _execute(
        self,
        request: CapabilityRequest,
        context: ExecutionContext,
        trace_id: str,
    ) -> CapabilityResult:
        """
        Provider-specific execution logic.

        Subclasses implement this with their specific protocol/transport.
        May raise ProviderError subclass for structured error handling,
        or return CapabilityResult.failure_result() directly.

        Args:
            request: The capability request.
            context: Execution context.
            trace_id: Cognitive trace ID.

        Returns:
            CapabilityResult on success or structured failure.

        Raises:
            ProviderTimeoutError: Execution exceeded deadline.
            ProviderExecutionError: Known execution failure.
        """
        ...

    @abstractmethod
    def capabilities(self) -> List[str]:
        """Return list of capability names this provider handles."""
        ...

    # ======================================================================
    # Helpers for subclasses
    # ======================================================================

    def _check_timeout(self, start: float) -> None:
        """
        Check if execution has exceeded max_execution_ms.

        Call this periodically in long-running _execute() implementations.

        Args:
            start: time.monotonic() at execution start.

        Raises:
            ProviderTimeoutError: If elapsed > config.max_execution_ms.
        """
        elapsed_ms = int((time.monotonic() - start) * 1000)
        if elapsed_ms > self._config.max_execution_ms:
            raise ProviderTimeoutError(self.provider_id, self._config.max_execution_ms)

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}("
            f"provider_id={self.provider_id!r}, "
            f"type={self.provider_type!r})"
        )
