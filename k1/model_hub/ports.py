"""
K1 Model Hub Ports -- Hexagonal Boundary Contracts
====================================================

ADR: 0001b (Model Hub Architecture & LLM Integration)
Spec: k1/model_hub/model_hub.mmd — PORTS section

7 ports defining the hexagonal boundary:
  Inbound:  IModelHubPort (THE single gateway), IConfigPort, ICredentialPort, IStateReadPort
  Outbound: IMetricsPort, IHealthPort
  Both:     IEventPort

All are typing.Protocol with @runtime_checkable for boot-time validation.
No implementation here — adapters satisfy these contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Protocol, runtime_checkable

from k1.model_hub.types import CapabilityType, HubChunk, HubRequest, HubResponse, ModelInfo

# ---------------------------------------------------------------------------
# Supporting types for port signatures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HubHealthReport:
    """Overall hub health report."""

    status: str = "HEALTHY"  # "HEALTHY" | "DEGRADED" | "UNHEALTHY"
    providers: list[ProviderHealthStatus] = field(default_factory=list)


@dataclass(frozen=True)
class ProviderHealthStatus:
    """Health status for a single provider."""

    provider_id: str = ""
    status: str = "HEALTHY"  # "HEALTHY" | "DEGRADED" | "UNHEALTHY"
    latency_ms: int = 0
    error_rate: float = 0.0
    circuit_state: str = "CLOSED"  # "CLOSED" | "OPEN" | "HALF_OPEN"


@dataclass(frozen=True)
class StateSnapshot:
    """Read-only snapshot of session state sections."""

    sections: dict[str, Any] = field(default_factory=dict)


class Subscription:
    """Handle for event/config subscriptions. Call .cancel() to unsubscribe."""

    def cancel(self) -> None:
        """Cancel this subscription."""


# ---------------------------------------------------------------------------
# IModelHubPort -- THE Single Gateway (Inbound)
# ---------------------------------------------------------------------------


@runtime_checkable
class IModelHubPort(Protocol):
    """The single entry point for all Model Hub operations.

    Every consumer (Concierge, Planner, Orchestrator, agents) calls this.
    MH-16: ALL traffic through this port -- no direct provider access.
    """

    async def execute(self, request: HubRequest) -> HubResponse:
        """Execute a single model request. Returns complete response."""
        ...

    async def stream_execute(self, request: HubRequest) -> AsyncIterator[HubChunk]:
        """Streaming model request. Yields chunks until done."""
        ...

    async def discover_capabilities(self) -> dict[CapabilityType, list[str]]:
        """Return available capabilities and which providers support each."""
        ...

    async def discover_models(self, capability: CapabilityType | None = None) -> list[ModelInfo]:
        """Return available models, optionally filtered by capability."""
        ...

    async def health(self) -> HubHealthReport:
        """Return overall hub health report."""
        ...


# ---------------------------------------------------------------------------
# IEventPort -- Event Bus (Both directions)
# ---------------------------------------------------------------------------


@runtime_checkable
class IEventPort(Protocol):
    """Event bus port for Model Hub events.

    Publishes: all k1.model_hub.*.v1 events
    Subscribes: k1.model_hub.config_update.v1
    """

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        """Publish an event to the bus."""
        ...

    async def subscribe(
        self,
        topics: list[str],
        handler: Callable[[str, dict[str, Any]], Any],
    ) -> Subscription:
        """Subscribe to one or more topics."""
        ...


# ---------------------------------------------------------------------------
# IStateReadPort -- Session State Read-Only (Inbound)
# ---------------------------------------------------------------------------


@runtime_checkable
class IStateReadPort(Protocol):
    """Read-only access to session state for model selection context.

    MH-01: Model Hub NEVER writes SessionState.
    Multi-reader, lock-free.
    Sections: persona (model pref), control (user_band)
    """

    async def read(self, sections: list[str]) -> StateSnapshot:
        """Read one or more state sections."""
        ...


# ---------------------------------------------------------------------------
# IMetricsPort -- Observability (Outbound)
# ---------------------------------------------------------------------------


@runtime_checkable
class IMetricsPort(Protocol):
    """Metrics emission port.

    Labels: provider, model, consumer, capability, priority.
    """

    async def emit(
        self,
        metric_name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Emit a metric datapoint."""
        ...


# ---------------------------------------------------------------------------
# IConfigPort -- Configuration (Inbound)
# ---------------------------------------------------------------------------


@runtime_checkable
class IConfigPort(Protocol):
    """Configuration port for hub settings.

    Keys: budgets, timeouts, placement rules.
    Provider config comes from manifests, not this port.
    """

    def get(self, key: str) -> Any:
        """Get a config value by key."""
        ...

    def watch(
        self,
        key: str,
        callback: Callable[[str, Any], Any],
    ) -> Subscription:
        """Watch a config key for changes."""
        ...


# ---------------------------------------------------------------------------
# ICredentialPort -- Credential Store (Inbound)
# ---------------------------------------------------------------------------


@runtime_checkable
class ICredentialPort(Protocol):
    """Credential port for provider API keys.

    MH-02: Credentials NEVER in config/env/manifest YAML.
    Source: OS keychain / Vault / env.
    """

    async def get_key(self, provider_id: str) -> str:
        """Get the API key for a provider."""
        ...

    async def refresh_key(self, provider_id: str) -> str:
        """Force-refresh the API key for a provider."""
        ...


# ---------------------------------------------------------------------------
# IHealthPort -- Health Reporting (Outbound)
# ---------------------------------------------------------------------------


@runtime_checkable
class IHealthPort(Protocol):
    """Health reporting port for hub components.

    Status: HEALTHY | DEGRADED | UNHEALTHY
    """

    async def report_health(self, component: str, status: str) -> None:
        """Report health status for a component."""
        ...

    async def check_health(self) -> HubHealthReport:
        """Check overall health."""
        ...
