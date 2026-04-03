"""Model Hub event topic constants and payload dataclasses [F04].

All event topics emitted by the Model Hub module. Each topic follows
the pattern ``k1.model_hub.{name}.v1``.

Import graph (Layer 0 -- no internal deps)
------------------------------------------
k1.model_hub.events
  -> k1.model_hub.types  (CapabilityType, HealthStatus, CircuitState)
  -> stdlib only

NEVER import from any service, port, adapter, or plugin module.

References
----------
- model_hub.mmd: MODEL_HUB_EVENTS section
- ADR-0001b: Model Hub Architecture
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from k1.model_hub.types import CapabilityType, CircuitState, HealthStatus

# ===========================================================================
# Topic Constants (11 topics)
# ===========================================================================

TOPIC_REQUEST_RECEIVED: str = "k1.model_hub.request.received.v1"
TOPIC_REQUEST_ROUTED: str = "k1.model_hub.request.routed.v1"
TOPIC_RESPONSE_COMPLETE: str = "k1.model_hub.response.complete.v1"
TOPIC_CACHE_HIT: str = "k1.model_hub.cache.hit.v1"
TOPIC_PROVIDER_FAILURE: str = "k1.model_hub.provider.failure.v1"
TOPIC_FALLBACK_TRIGGERED: str = "k1.model_hub.fallback.triggered.v1"
TOPIC_CIRCUIT_STATE: str = "k1.model_hub.circuit.state.v1"
TOPIC_BUDGET_ALERT: str = "k1.model_hub.budget.alert.v1"
TOPIC_PROVIDER_HEALTH: str = "k1.model_hub.provider.health.v1"
TOPIC_PROVIDER_REGISTERED: str = "k1.model_hub.provider.registered.v1"
TOPIC_CAPABILITY_AVAILABLE: str = "k1.model_hub.capability.available.v1"


# ===========================================================================
# Event Payload Dataclasses (one per topic)
# ===========================================================================


@dataclass(frozen=True)
class RequestReceivedPayload:
    """Payload for TOPIC_REQUEST_RECEIVED."""

    request_id: str
    consumer_id: str
    capability: CapabilityType
    budget_remaining_pct: float = 100.0
    trace_id: str = ""


@dataclass(frozen=True)
class RequestRoutedPayload:
    """Payload for TOPIC_REQUEST_ROUTED."""

    request_id: str
    provider_id: str
    model_id: str
    capability: CapabilityType
    trace_id: str = ""


@dataclass(frozen=True)
class ResponseCompletePayload:
    """Payload for TOPIC_RESPONSE_COMPLETE."""

    request_id: str
    tokens_used: int = 0
    latency_ms: int = 0
    cost_usd: float = 0.0
    provider_id: str = ""
    model_id: str = ""
    capability: Optional[CapabilityType] = None
    cache_hit: bool = False
    trace_id: str = ""


@dataclass(frozen=True)
class CacheHitPayload:
    """Payload for TOPIC_CACHE_HIT."""

    request_id: str
    cache_key: str
    capability: CapabilityType
    age_ms: int = 0
    trace_id: str = ""


@dataclass(frozen=True)
class ProviderFailurePayload:
    """Payload for TOPIC_PROVIDER_FAILURE."""

    request_id: str
    provider_id: str
    error_type: str = ""
    error_message: str = ""
    will_fallback: bool = False
    trace_id: str = ""


@dataclass(frozen=True)
class FallbackTriggeredPayload:
    """Payload for TOPIC_FALLBACK_TRIGGERED."""

    request_id: str
    from_provider: str
    to_provider: str
    reason: str = ""
    trace_id: str = ""


@dataclass(frozen=True)
class CircuitStatePayload:
    """Payload for TOPIC_CIRCUIT_STATE."""

    provider_id: str
    old_state: CircuitState
    new_state: CircuitState
    failure_count: int = 0


@dataclass(frozen=True)
class BudgetAlertPayload:
    """Payload for TOPIC_BUDGET_ALERT."""

    tenant_id: str = "default"
    level: str = "WARNING"
    pct: float = 0.0
    action: str = ""

    def __post_init__(self) -> None:
        if self.level not in ("WARNING", "EXCEEDED"):
            raise ValueError(f"BudgetAlertPayload.level must be WARNING|EXCEEDED, got {self.level}")


@dataclass(frozen=True)
class ProviderHealthPayload:
    """Payload for TOPIC_PROVIDER_HEALTH."""

    provider_id: str
    status: HealthStatus
    latency_p50: int = 0
    error_rate: float = 0.0


@dataclass(frozen=True)
class ProviderRegisteredPayload:
    """Payload for TOPIC_PROVIDER_REGISTERED."""

    provider_id: str
    capabilities: List[CapabilityType] = field(default_factory=list)
    model_count: int = 0


@dataclass(frozen=True)
class CapabilityAvailablePayload:
    """Payload for TOPIC_CAPABILITY_AVAILABLE."""

    capability: CapabilityType
    provider_ids: List[str] = field(default_factory=list)
    model_count: int = 0


# ===========================================================================
# __all__
# ===========================================================================

__all__ = [
    # Topic Constants
    "TOPIC_REQUEST_RECEIVED",
    "TOPIC_REQUEST_ROUTED",
    "TOPIC_RESPONSE_COMPLETE",
    "TOPIC_CACHE_HIT",
    "TOPIC_PROVIDER_FAILURE",
    "TOPIC_FALLBACK_TRIGGERED",
    "TOPIC_CIRCUIT_STATE",
    "TOPIC_BUDGET_ALERT",
    "TOPIC_PROVIDER_HEALTH",
    "TOPIC_PROVIDER_REGISTERED",
    "TOPIC_CAPABILITY_AVAILABLE",
    # Payload Dataclasses
    "RequestReceivedPayload",
    "RequestRoutedPayload",
    "ResponseCompletePayload",
    "CacheHitPayload",
    "ProviderFailurePayload",
    "FallbackTriggeredPayload",
    "CircuitStatePayload",
    "BudgetAlertPayload",
    "ProviderHealthPayload",
    "ProviderRegisteredPayload",
    "CapabilityAvailablePayload",
]
