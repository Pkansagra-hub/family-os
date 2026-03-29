"""
k1.fabric.provider_resolution.resolver -- Resolver Pipeline (3.1.5).

Full resolution pipeline that maps a CapabilityRequest.name to a concrete
provider instance, ready for execution. Chains 5 steps:

  1. Registry Lookup  -- CapabilityRegistry.lookup(name) -> contract
  2. Provider Matching -- ProviderMatcher.match(contract) -> [ProviderConfig]
  3. Policy Evaluation -- PolicyEngine.evaluate(candidates, request) -> [ScoredCandidate]
  4. Provider Selection -- ProviderSelector.select(scored) -> ResolvedProvider
  5. Provider Instantiation -- ProviderFactory.create(config) -> CapabilityProvider

Design:
  - Constructor injection: all 5 dependencies injected by FabricFactory (5.3.1)
  - PolicyEngine is an Optional port: if None, all candidates get a default
    PolicyResult(allowed=True, score=1.0). This allows the Resolver to operate
    before the Policy Engine (Epic 3.2) is implemented.
  - Returns ResolvedProvider with provider_config, contract, policy_result.
  - Errors at any step produce CapabilityResult.failure_result() with
    structured ErrorInfo codes: capability_not_found, no_provider,
    access_denied, provider_instantiation_failed.
  - Timing: each step is timed and returned in CapabilityResult.resolution_time_ms.

References:
  - fabric_discussion.md Section 9 (Resolution Pipeline)
  - Epic 3.1.5 in fabric-implementation-plan.md

Exports:
  Resolver -- Full resolution pipeline
  ResolverError -- Base exception
  ResolutionFailedError -- Pipeline failed (wraps step-specific errors)
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional, Protocol, Union

from k1.fabric.core.registry import CapabilityRegistry
from k1.fabric.provider_resolution.provider_factory import ProviderFactory
from k1.fabric.provider_resolution.provider_matcher import NoProviderError, ProviderMatcher
from k1.fabric.provider_resolution.provider_selector import (
    AllProvidersRejectedError,
    NoCandidatesError,
    ProviderSelector,
    ScoredCandidate,
)
from k1.fabric.types import (
    AgentContract,
    CapabilityContract,
    CapabilityRequest,
    CapabilityResult,
    PolicyResult,
    PromptContract,
    ProviderConfig,
    ResolvedProvider,
    WorkflowContract,
)

logger = logging.getLogger(__name__)

# Type alias
ContractUnion = Union[CapabilityContract, AgentContract, PromptContract, WorkflowContract]


# ---------------------------------------------------------------------------
# Policy Engine port (Protocol for optional dependency)
# ---------------------------------------------------------------------------


class PolicyEnginePort(Protocol):
    """
    Minimal protocol for the Policy Engine (3.2.5).

    The Resolver accepts any object satisfying this interface.
    If no PolicyEngine is provided, the Resolver uses a default pass-all
    evaluator that gives every candidate score=1.0, allowed=True.
    """

    def evaluate(
        self,
        candidates: List[ProviderConfig],
        contract: ContractUnion,
        request: CapabilityRequest,
    ) -> List[ScoredCandidate]:
        """
        Evaluate policy for each candidate provider.

        Args:
            candidates: Matched provider configs.
            contract: The capability contract being fulfilled.
            request: The original capability request.

        Returns:
            List of ScoredCandidates with policy results.
        """
        ...


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ResolverError(Exception):
    """Base exception for resolution pipeline operations."""


class ResolutionFailedError(ResolverError):
    """Raised when the resolution pipeline fails at any step."""

    def __init__(self, capability_name: str, error_code: str, message: str):
        self.capability_name = capability_name
        self.error_code = error_code
        super().__init__(f"Resolution failed for '{capability_name}': [{error_code}] {message}")


# ---------------------------------------------------------------------------
# 3.1.5 -- Resolver (Full Pipeline)
# ---------------------------------------------------------------------------


class Resolver:
    """
    Full provider resolution pipeline.

    Chains 5 steps to map a capability name to a concrete, instantiated
    provider ready for execution:

      1. Registry Lookup -> contract
      2. Provider Matching -> [ProviderConfig]
      3. Policy Evaluation -> [ScoredCandidate]
      4. Provider Selection -> ResolvedProvider
      5. Provider Instantiation -> CapabilityProvider

    Constructor Args:
        capability_registry: The CapabilityRegistry (2.2.1) for name lookup.
        provider_matcher: The ProviderMatcher (3.1.2) for provider matching.
        provider_selector: The ProviderSelector (3.1.3) for deterministic selection.
        provider_factory: The ProviderFactory (3.1.4) for handler instantiation.
        policy_engine: Optional PolicyEngine (3.2.5). If None, all candidates
            receive PolicyResult(allowed=True, score=1.0).

    Thread Safety:
        All components are either stateless (Selector) or use internal locking
        (Registry, ProviderRegistry). The Resolver itself is stateless and
        safe for concurrent calls.

    References:
        - fabric_discussion.md Section 9
        - Epic 3.1.5
    """

    __slots__ = (
        "_capability_registry",
        "_provider_matcher",
        "_provider_selector",
        "_provider_factory",
        "_policy_engine",
    )

    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry,
        provider_matcher: ProviderMatcher,
        provider_selector: ProviderSelector,
        provider_factory: ProviderFactory,
        policy_engine: Optional[PolicyEnginePort] = None,
    ) -> None:
        self._capability_registry = capability_registry
        self._provider_matcher = provider_matcher
        self._provider_selector = provider_selector
        self._provider_factory = provider_factory
        self._policy_engine = policy_engine

    # ======================================================================
    # Public API
    # ======================================================================

    def resolve(self, request: CapabilityRequest) -> ResolvedProvider:
        """
        Execute the full resolution pipeline.

        Steps:
          1. Lookup contract by request.capability_name
          2. Match providers for the contract
          3. Evaluate policy for each candidate
          4. Select the best provider (deterministic, FAB-10)
          5. (Provider instantiation is NOT done here -- caller uses
             provider_factory.create() on the ResolvedProvider.provider_config)

        Note: Step 5 (instantiation) is separated because the caller
        (FabricFacade.execute) may need the ResolvedProvider metadata
        before instantiation (e.g., for circuit breaker lookup, logging).

        Args:
            request: The capability request to resolve.

        Returns:
            ResolvedProvider with provider_config, contract, policy_result.

        Raises:
            ResolutionFailedError: Pipeline failed at any step.
        """
        capability_name = request.capability_name

        # --- Step 1: Registry Lookup ---
        contract = self._capability_registry.lookup(capability_name)
        if contract is None:
            raise ResolutionFailedError(
                capability_name=capability_name,
                error_code="capability_not_found",
                message=f"No contract registered for '{capability_name}'",
            )

        # --- Step 2: Provider Matching ---
        try:
            candidates = self._provider_matcher.match_or_raise(contract)
        except NoProviderError as exc:
            raise ResolutionFailedError(
                capability_name=capability_name,
                error_code="no_provider",
                message=str(exc),
            ) from exc

        # --- Step 3: Policy Evaluation ---
        scored = self._evaluate_policy(candidates, contract, request)

        # --- Step 4: Provider Selection ---
        try:
            resolved = self._provider_selector.select(scored, capability_name=capability_name)
        except AllProvidersRejectedError as exc:
            raise ResolutionFailedError(
                capability_name=capability_name,
                error_code="access_denied",
                message=str(exc),
            ) from exc
        except NoCandidatesError as exc:
            raise ResolutionFailedError(
                capability_name=capability_name,
                error_code="no_provider",
                message=str(exc),
            ) from exc

        logger.debug(
            "Resolved %s -> provider=%s (score=%.3f)",
            capability_name,
            resolved.provider_config.provider_id,
            resolved.policy_result.score,
        )
        return resolved

    def resolve_to_result(self, request: CapabilityRequest) -> CapabilityResult:
        """
        Execute resolution pipeline and return a CapabilityResult on failure.

        Unlike resolve() which raises exceptions, this method catches
        resolution errors and returns CapabilityResult.failure_result().
        On success, returns a CapabilityResult with success=True and
        the provider_id + resolution timing in the result.

        This is the method called by FabricFacade.execute() for
        graceful error handling.

        Args:
            request: The capability request to resolve.

        Returns:
            CapabilityResult -- success with provider_id, or failure with error.
        """
        start = time.monotonic()
        try:
            resolved = self.resolve(request)
        except ResolutionFailedError as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return CapabilityResult.failure_result(
                request_id=request.request_id,
                error_code=exc.error_code,
                error_message=str(exc),
                retriable=exc.error_code in ("no_provider",),
                provider_id="",
                trace_id=request.trace_id,
                duration_ms=elapsed_ms,
                resolution_time_ms=elapsed_ms,
            )

        elapsed_ms = int((time.monotonic() - start) * 1000)
        return CapabilityResult.success_result(
            request_id=request.request_id,
            data={
                "provider_id": resolved.provider_config.provider_id,
                "provider_type": resolved.provider_config.provider_type,
                "policy_score": resolved.policy_result.score,
            },
            provider_id=resolved.provider_config.provider_id,
            trace_id=request.trace_id,
            duration_ms=elapsed_ms,
            resolution_time_ms=elapsed_ms,
        )

    # ======================================================================
    # Internal: policy evaluation
    # ======================================================================

    def _evaluate_policy(
        self,
        candidates: List[ProviderConfig],
        contract: ContractUnion,
        request: CapabilityRequest,
    ) -> List[ScoredCandidate]:
        """
        Evaluate policy for each candidate provider.

        If a PolicyEngine is wired, delegates to it. Otherwise, returns
        a default pass-all result: allowed=True, score=1.0 for every
        candidate. This enables the Resolver to work before Epic 3.2
        (Policy Engine) is implemented.
        """
        if self._policy_engine is not None:
            return self._policy_engine.evaluate(candidates, contract, request)

        # Default: pass-all policy (no PolicyEngine wired yet)
        return [
            ScoredCandidate(
                provider_config=cfg,
                contract=contract,
                policy_result=PolicyResult(
                    allowed=True,
                    score=1.0,
                    reasons=["default_pass_all"],
                ),
            )
            for cfg in candidates
        ]
