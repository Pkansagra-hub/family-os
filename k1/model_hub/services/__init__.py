"""Model Hub services package.

Re-exports service classes for single-import convenience.
"""

from k1.model_hub.services.audit_logger import AuditLogger, AuditRecord
from k1.model_hub.services.budget_enforcer import BudgetCheckResult, BudgetEnforcer, SpendingRecord
from k1.model_hub.services.capability_router import (
    CapabilityRouter,
    EligibleProvider,
    ICircuitBreakerQuery,
    IHealthQuery,
    IRateLimiterQuery,
)
from k1.model_hub.services.circuit_breaker_manager import CircuitBreakerManager, CircuitTransition
from k1.model_hub.services.cost_tracker import CostRecord, CostTracker
from k1.model_hub.services.model_selector import FallbackEntry, ModelChoice, ModelSelector
from k1.model_hub.services.normalization_layer import NormalizationLayer
from k1.model_hub.services.provider_dispatcher import DispatchResult, ProviderDispatcher
from k1.model_hub.services.provider_registry import ProviderInfo, ProviderRegistry
from k1.model_hub.services.rate_limiter import RateDecision, RateLimiter
from k1.model_hub.services.request_router import RequestRouter
from k1.model_hub.services.response_cache import CacheResult, ResponseCache

__all__ = [
    "AuditLogger",
    "AuditRecord",
    "BudgetCheckResult",
    "BudgetEnforcer",
    "CacheResult",
    "CapabilityRouter",
    "CircuitBreakerManager",
    "CircuitTransition",
    "CostRecord",
    "CostTracker",
    "DispatchResult",
    "EligibleProvider",
    "FallbackEntry",
    "ICircuitBreakerQuery",
    "IHealthQuery",
    "IRateLimiterQuery",
    "ModelChoice",
    "ModelSelector",
    "NormalizationLayer",
    "ProviderDispatcher",
    "ProviderInfo",
    "ProviderRegistry",
    "RateDecision",
    "RateLimiter",
    "RequestRouter",
    "ResponseCache",
    "SpendingRecord",
]
