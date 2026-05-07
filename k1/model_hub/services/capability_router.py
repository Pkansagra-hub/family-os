"""Capability-aware provider routing [F41].

Filters eligible providers by capability, circuit breaker state, rate limit
headroom, and health status using a 5-step filtering pipeline.

Import graph (Layer 3 -- imports Layer 0 + Layer 1 + Layer 2)
--------------------------------------------------------------
k1.model_hub.services.capability_router
  -> k1.model_hub.types              (Layer 0)
  -> k1.model_hub.services.provider_registry (Layer 3, sibling)
  -> stdlib only

NEVER import from any adapter or runtime module.

References
----------
- model_hub.mmd: CapabilityRouter service
- Invariant MH-06: Fallback is CAPABILITY-AWARE
- Invariant MH-18: Manifest is SOLE capability truth
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Protocol, runtime_checkable

from k1.model_hub.manifest import ModelSpec
from k1.model_hub.services.provider_registry import ProviderInfo, ProviderRegistry
from k1.model_hub.types import CapabilityType, CircuitState, HealthStatus, RequestConstraints

# ===========================================================================
# Dependency protocols (M4 services not yet built)
# ===========================================================================


@runtime_checkable
class ICircuitBreakerQuery(Protocol):
    """Query interface for circuit breaker state (M4 dependency)."""

    def get_state(self, provider_id: str) -> CircuitState:
        """Get current circuit breaker state for a provider."""
        ...


@runtime_checkable
class IRateLimiterQuery(Protocol):
    """Query interface for rate limit availability (M4 dependency)."""

    def has_capacity(self, provider_id: str, token_estimate: int) -> bool:
        """Check if provider has rate limit capacity."""
        ...


@runtime_checkable
class IHealthQuery(Protocol):
    """Query interface for provider health status (M4 dependency)."""

    def get_status(self, provider_id: str) -> HealthStatus:
        """Get current health status for a provider."""
        ...


# ===========================================================================
# EligibleProvider -- output of routing
# ===========================================================================


@dataclass(frozen=True)
class EligibleProvider:
    """A provider that passed all 5 routing filters.

    Carries the ProviderInfo + eligible models for downstream ModelSelector.
    """

    provider_info: ProviderInfo
    eligible_models: List[ModelSpec] = field(default_factory=list)
    circuit_state: CircuitState = CircuitState.CLOSED
    health_status: HealthStatus = HealthStatus.HEALTHY


# ===========================================================================
# CapabilityRouter
# ===========================================================================


class CapabilityRouter:
    """5-step filtering pipeline for capability-aware provider routing.

    Steps:
      1. Lookup capability in ProviderRegistry index (MH-18).
      2. Filter: model supports capability (model-level).
      3. Filter: circuit breaker not OPEN.
      4. Filter: rate limit not exhausted.
      5. Filter: health status >= DEGRADED.

    If 0 eligible after filtering: returns empty list (caller handles
    cache fallback / template fallback).

    NEVER hardcodes provider names (MH-18).

    Constructor deps:
        registry: ProviderRegistry for capability index.
        circuit_breaker: ICircuitBreakerQuery for CB state checks.
        rate_limiter: IRateLimiterQuery for rate limit headroom.
        health_monitor: IHealthQuery for provider health.
    """

    def __init__(
        self,
        registry: ProviderRegistry,
        circuit_breaker: ICircuitBreakerQuery,
        rate_limiter: IRateLimiterQuery,
        health_monitor: IHealthQuery,
    ) -> None:
        self._registry = registry
        self._circuit_breaker = circuit_breaker
        self._rate_limiter = rate_limiter
        self._health_monitor = health_monitor

    def route(
        self,
        capability: CapabilityType,
        constraints: RequestConstraints,
        *,
        token_estimate: int = 0,
    ) -> List[EligibleProvider]:
        """Run the 5-step filtering pipeline.

        Args:
            capability: Requested capability type.
            constraints: Request constraints (priority, timeout, etc.).
            token_estimate: Estimated tokens for rate limit check.

        Returns:
            List of EligibleProvider that passed all 5 filters.
            Empty list if no provider qualifies.
        """
        # Step 1: Lookup capability in registry (MH-18)
        providers = self._registry.get_providers_for_capability(capability)
        if not providers:
            return []

        eligible: List[EligibleProvider] = []

        for info in providers:
            # Step 2: Filter models that support the capability (model-level)
            eligible_models = self._filter_models_by_capability(info.models, capability)
            if not eligible_models:
                # Provider declared capability but no specific model supports it
                # Still eligible if provider-level capability declared
                eligible_models = info.models if info.models else []

            # Step 3: Filter circuit breaker not OPEN
            cb_state = self._circuit_breaker.get_state(info.provider_id)
            if cb_state == CircuitState.OPEN:
                continue

            # Step 4: Filter rate limit not exhausted
            if not self._rate_limiter.has_capacity(info.provider_id, token_estimate):
                continue

            # Step 5: Filter health status >= DEGRADED
            health = self._health_monitor.get_status(info.provider_id)
            if health == HealthStatus.UNHEALTHY:
                continue

            eligible.append(
                EligibleProvider(
                    provider_info=info,
                    eligible_models=eligible_models,
                    circuit_state=cb_state,
                    health_status=health,
                )
            )

        return eligible

    @staticmethod
    def _filter_models_by_capability(
        models: List[ModelSpec],
        capability: CapabilityType,
    ) -> List[ModelSpec]:
        """Filter models that support a specific capability."""
        return [m for m in models if capability in m.capabilities]


__all__ = [
    "CapabilityRouter",
    "EligibleProvider",
    "ICircuitBreakerQuery",
    "IHealthQuery",
    "IRateLimiterQuery",
]
