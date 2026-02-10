"""
k1.fabric.core.discovery_tools -- MCP discovery tool wrappers (4.5.3).

Two MCP-callable tool handlers that expose Fabric retrieval as capability
discovery tools for Planner consumption via Orchestrator DAG steps.

Public API:
  - ``DiscoverCapabilitiesHandler`` -- tool.read.discover_capabilities
  - ``FindPromptsHandler``          -- tool.read.find_prompts
  - ``DiscoveryToolError``          -- Input validation exception
  - ``DISCOVER_CAPABILITIES_NAME``  -- Tool capability name constant
  - ``DISCOVER_CAPABILITIES_PROVIDER_ID`` -- Provider ID constant
  - ``FIND_PROMPTS_NAME``           -- Tool capability name constant
  - ``FIND_PROMPTS_PROVIDER_ID``    -- Provider ID constant
  - ``DEFAULT_DISCOVER_TOP_K``      -- Default top_k for discover (10)
  - ``DEFAULT_FIND_PROMPTS_TOP_K``  -- Default top_k for find_prompts (5)

Both handlers:
  - GREEN band, read-only (no state mutation)
  - Protocol-based DI via ``RetrievalLike``
  - Thin delegation to ``RetrievalEngine.discover_capabilities()`` /
    ``find_relevant_prompts()`` (4.1.5)
  - Map ``RetrievalResult`` -> ``CapabilityResult.success/failure``
  - Track timing via ``_now_ms()``

Thread safety: Stateless handlers, safe for concurrent calls.

References:
  - fabric-implementation-plan.md Issue 4.5.3
  - meta-agent-creation-integration-proposal.md PART 1 (Option A)
  - ADR-K004 (Capability Fabric Adaptation)
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from k1.fabric.types import CapabilityRequest, CapabilityResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants (4.5.3)
# ---------------------------------------------------------------------------

DISCOVER_CAPABILITIES_NAME: str = "tool.read.discover_capabilities"
"""MCP tool name for capability discovery (4.5.3)."""

DISCOVER_CAPABILITIES_PROVIDER_ID: str = "discover_capabilities_handler"
"""Provider ID for DiscoverCapabilitiesHandler."""

FIND_PROMPTS_NAME: str = "tool.read.find_prompts"
"""MCP tool name for prompt template discovery (4.5.3)."""

FIND_PROMPTS_PROVIDER_ID: str = "find_prompts_handler"
"""Provider ID for FindPromptsHandler."""

DEFAULT_DISCOVER_TOP_K: int = 10
"""Default top_k for discover_capabilities (matches contract YAML)."""

DEFAULT_FIND_PROMPTS_TOP_K: int = 5
"""Default top_k for find_prompts (matches contract YAML)."""


# ---------------------------------------------------------------------------
# Protocol -- RetrievalLike
# ---------------------------------------------------------------------------


@runtime_checkable
class RetrievalLike(Protocol):
    """
    Minimal retrieval surface for discovery handlers (4.5.3).

    Satisfied by:
      - ``RetrievalEngine`` (4.1.5) -- sync, production use.
      - Any test adapter with matching method signatures.

    NOT satisfied by ``FabricRetrieval`` (5.3.3) which has async methods.
    Use ``RetrievalEngine`` directly or a sync adapter.
    """

    def discover_capabilities(
        self,
        domain: Optional[List[str]] = None,
        intent: str = "",
        safety_band: str = "GREEN",
        session_context: Optional[Dict[str, Any]] = None,
        top_k: Optional[int] = None,
    ) -> Any: ...

    def find_relevant_prompts(
        self,
        intent: str = "",
        domain: Optional[List[str]] = None,
        safety_band: str = "GREEN",
        top_k: Optional[int] = None,
    ) -> Any: ...


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class DiscoveryToolError(Exception):
    """
    Input validation error during discovery tool execution (4.5.3).

    Raised by handler input parsing when required inputs are missing
    or optional inputs have invalid types. Mapped to
    ``CapabilityResult.failure_result(error_code="validation_failed")``.

    Distinct from internal errors (engine failures) which map to
    ``error_code="internal_error"``.
    """

    def __init__(self, errors: List[str]) -> None:
        self.errors = errors
        super().__init__(f"Discovery tool error ({len(errors)} issue(s)): {'; '.join(errors)}")


# ---------------------------------------------------------------------------
# 4.5.3 -- DiscoverCapabilitiesHandler
# ---------------------------------------------------------------------------


class DiscoverCapabilitiesHandler:
    """
    Handler for tool.read.discover_capabilities MCP Tool (4.5.3).

    3-step execute() orchestrates capability discovery:
      1. Parse+validate inputs (intent required, domain required)
      2. Delegate to RetrievalEngine.discover_capabilities()
      3. Map RetrievalResult to CapabilityResult.success/failure

    Constructor injection (1 dep):
      retrieval: RetrievalLike (satisfied by RetrievalEngine 4.1.5)

    GREEN band, read-only, no state mutation.
    Registered in MCPProvider (3.3.1) handler_registry as local handler
    for ``tool.read.discover_capabilities``. Resolved via standard
    Resolver pipeline (3.1.5).

    Thread safety: stateless handler, safe for concurrent calls.
    """

    __slots__ = ("_retrieval",)

    def __init__(self, retrieval: RetrievalLike) -> None:
        """
        Args:
            retrieval: RetrievalEngine (4.1.5) or compatible adapter.
        """
        self._retrieval = retrieval

    # -- Public API --------------------------------------------------------

    def execute(self, request: CapabilityRequest) -> CapabilityResult:
        """
        Execute the discover_capabilities tool (3-step pipeline).

        Args:
            request: CapabilityRequest with params containing:
                Required: intent (str), domain (list[str])
                Optional: top_k (int, default=10), safety_band (str, default=GREEN)

        Returns:
            CapabilityResult with:
              - success: data={capabilities, total_matched, query_latency_ms, ...}
              - failure: error with code and message
        """
        trace_id = request.trace_id
        request_id = request.request_id
        params = request.params
        start_ms = _now_ms()

        try:
            # Step 1: Parse + validate inputs
            intent, domain, top_k, safety_band = self._parse_inputs(params)

            # Step 2: Delegate to retrieval engine
            result = self._retrieval.discover_capabilities(
                domain=domain,
                intent=intent,
                safety_band=safety_band,
                session_context=None,
                top_k=top_k,
            )

            # Step 3: Map to CapabilityResult
            result_data = result.to_dict() if hasattr(result, "to_dict") else {}

            return CapabilityResult.success_result(
                request_id=request_id,
                data=result_data,
                provider_id=DISCOVER_CAPABILITIES_PROVIDER_ID,
                trace_id=trace_id,
                duration_ms=_now_ms() - start_ms,
                retrieval_time_ms=getattr(result, "query_latency_ms", 0),
            )

        except DiscoveryToolError as exc:
            return CapabilityResult.failure_result(
                request_id=request_id,
                error_code="validation_failed",
                error_message=str(exc),
                trace_id=trace_id,
                duration_ms=_now_ms() - start_ms,
            )

        except Exception as exc:
            logger.error(
                "DiscoverCapabilitiesHandler unexpected error: %s",
                exc,
                exc_info=True,
            )
            return CapabilityResult.failure_result(
                request_id=request_id,
                error_code="internal_error",
                error_message=f"Unexpected error: {type(exc).__name__}: {exc}",
                trace_id=trace_id,
                duration_ms=_now_ms() - start_ms,
            )

    # -- Input parsing -----------------------------------------------------

    def _parse_inputs(
        self,
        params: Dict[str, Any],
    ) -> tuple:
        """
        Parse and validate discover_capabilities inputs.

        Args:
            params: Raw request parameters from CapabilityRequest.params.

        Returns:
            Tuple of (intent, domain, top_k, safety_band).

        Raises:
            DiscoveryToolError: If required inputs are missing or invalid.
        """
        errors: List[str] = []

        # Required: intent (non-empty string)
        intent = params.get("intent")
        if not isinstance(intent, str) or not intent.strip():
            errors.append("Missing or invalid required input: 'intent' (non-empty str)")

        # Required: domain (non-empty list of strings)
        domain = params.get("domain")
        if not isinstance(domain, list):
            errors.append("Missing or invalid required input: 'domain' (list[str])")
        elif len(domain) == 0:
            errors.append("'domain' must contain at least one tag")
        else:
            for tag in domain:
                if not isinstance(tag, str):
                    errors.append(
                        f"Each domain tag must be a string, " f"got {type(tag).__name__}: {tag!r}"
                    )
                    break

        if errors:
            raise DiscoveryToolError(errors)

        # Optional: top_k (positive int, default=10)
        top_k_raw = params.get("top_k", DEFAULT_DISCOVER_TOP_K)
        if not isinstance(top_k_raw, int) or top_k_raw < 1:
            errors.append(f"'top_k' must be a positive integer, got {top_k_raw!r}")

        # Optional: safety_band (non-empty string, default=GREEN)
        safety_band = params.get("safety_band", "GREEN")
        if not isinstance(safety_band, str) or not safety_band.strip():
            errors.append("'safety_band' must be a non-empty string")

        if errors:
            raise DiscoveryToolError(errors)

        top_k = top_k_raw
        return intent, domain, top_k, safety_band

    # -- Repr --------------------------------------------------------------

    def __repr__(self) -> str:
        return f"DiscoverCapabilitiesHandler(retrieval={self._retrieval!r})"


# ---------------------------------------------------------------------------
# 4.5.3 -- FindPromptsHandler
# ---------------------------------------------------------------------------


class FindPromptsHandler:
    """
    Handler for tool.read.find_prompts MCP Tool (4.5.3).

    3-step execute() orchestrates prompt template discovery:
      1. Parse+validate inputs (intent required, domain optional)
      2. Delegate to RetrievalEngine.find_relevant_prompts()
      3. Map RetrievalResult to CapabilityResult.success/failure

    Constructor injection (1 dep):
      retrieval: RetrievalLike (satisfied by RetrievalEngine 4.1.5)

    GREEN band, read-only, no state mutation.
    Registered in MCPProvider (3.3.1) handler_registry as local handler
    for ``tool.read.find_prompts``. Resolved via standard Resolver
    pipeline (3.1.5).

    Thread safety: stateless handler, safe for concurrent calls.
    """

    __slots__ = ("_retrieval",)

    def __init__(self, retrieval: RetrievalLike) -> None:
        """
        Args:
            retrieval: RetrievalEngine (4.1.5) or compatible adapter.
        """
        self._retrieval = retrieval

    # -- Public API --------------------------------------------------------

    def execute(self, request: CapabilityRequest) -> CapabilityResult:
        """
        Execute the find_prompts tool (3-step pipeline).

        Args:
            request: CapabilityRequest with params containing:
                Required: intent (str)
                Optional: domain (list[str]), top_k (int, default=5)

        Returns:
            CapabilityResult with:
              - success: data={capabilities, total_matched, query_latency_ms, ...}
              - failure: error with code and message
        """
        trace_id = request.trace_id
        request_id = request.request_id
        params = request.params
        start_ms = _now_ms()

        try:
            # Step 1: Parse + validate inputs
            intent, domain, top_k = self._parse_inputs(params)

            # Step 2: Delegate to retrieval engine
            result = self._retrieval.find_relevant_prompts(
                intent=intent,
                domain=domain,
                safety_band="GREEN",
                top_k=top_k,
            )

            # Step 3: Map to CapabilityResult
            result_data = result.to_dict() if hasattr(result, "to_dict") else {}

            return CapabilityResult.success_result(
                request_id=request_id,
                data=result_data,
                provider_id=FIND_PROMPTS_PROVIDER_ID,
                trace_id=trace_id,
                duration_ms=_now_ms() - start_ms,
                retrieval_time_ms=getattr(result, "query_latency_ms", 0),
            )

        except DiscoveryToolError as exc:
            return CapabilityResult.failure_result(
                request_id=request_id,
                error_code="validation_failed",
                error_message=str(exc),
                trace_id=trace_id,
                duration_ms=_now_ms() - start_ms,
            )

        except Exception as exc:
            logger.error(
                "FindPromptsHandler unexpected error: %s",
                exc,
                exc_info=True,
            )
            return CapabilityResult.failure_result(
                request_id=request_id,
                error_code="internal_error",
                error_message=f"Unexpected error: {type(exc).__name__}: {exc}",
                trace_id=trace_id,
                duration_ms=_now_ms() - start_ms,
            )

    # -- Input parsing -----------------------------------------------------

    def _parse_inputs(
        self,
        params: Dict[str, Any],
    ) -> tuple:
        """
        Parse and validate find_prompts inputs.

        Args:
            params: Raw request parameters from CapabilityRequest.params.

        Returns:
            Tuple of (intent, domain, top_k).

        Raises:
            DiscoveryToolError: If required inputs are missing or invalid.
        """
        errors: List[str] = []

        # Required: intent (non-empty string)
        intent = params.get("intent")
        if not isinstance(intent, str) or not intent.strip():
            errors.append("Missing or invalid required input: 'intent' (non-empty str)")

        if errors:
            raise DiscoveryToolError(errors)

        # Optional: domain (list of strings, default=None -> no domain filter)
        domain = params.get("domain")
        if domain is not None:
            if not isinstance(domain, list):
                errors.append("'domain' must be a list of strings")
            else:
                for tag in domain:
                    if not isinstance(tag, str):
                        errors.append(
                            f"Each domain tag must be a string, "
                            f"got {type(tag).__name__}: {tag!r}"
                        )
                        break

        # Optional: top_k (positive int, default=5)
        top_k_raw = params.get("top_k", DEFAULT_FIND_PROMPTS_TOP_K)
        if not isinstance(top_k_raw, int) or top_k_raw < 1:
            errors.append(f"'top_k' must be a positive integer, got {top_k_raw!r}")

        if errors:
            raise DiscoveryToolError(errors)

        top_k = top_k_raw
        return intent, domain, top_k

    # -- Repr --------------------------------------------------------------

    def __repr__(self) -> str:
        return f"FindPromptsHandler(retrieval={self._retrieval!r})"


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _now_ms() -> int:
    """Current epoch time in milliseconds."""
    return int(time.time() * 1000)
