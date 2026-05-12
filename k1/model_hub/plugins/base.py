"""Provider plugin interface and supporting types [F20].

Defines the single contract (IProviderPlugin) that ALL provider plugins
implement. This is the extension point for adding new LLM providers with
zero hub code changes.

Import graph (Layer 2 -- imports Layer 0 + Layer 1)
----------------------------------------------------
k1.model_hub.plugins.base
  -> k1.model_hub.types      (CapabilityType, FinishReason, HealthStatus, Message, ToolCallResult)
  -> k1.model_hub.manifest   (ProviderManifest)
  -> stdlib only

NEVER import from any service, adapter, or runtime module.

References
----------
- model_hub.mmd: PLUGIN_INTERFACE section
- ADR-0001b: Model Hub Architecture & LLM Integration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Protocol, runtime_checkable

from k1.model_hub.manifest import ProviderManifest
from k1.model_hub.types import CapabilityType, FinishReason, HealthStatus, Message, ToolCallResult

# ===========================================================================
# Plugin Data Types (provider-agnostic intermediate forms)
# ===========================================================================


@dataclass(frozen=True)
class NormalizedRequest:
    """Provider-agnostic intermediate request form.

    NormalizationLayer converts HubRequest -> NormalizedRequest.
    Each plugin translates NormalizedRequest to its native API format.
    Hub NEVER knows about /chat/completions vs /messages.
    """

    capability: CapabilityType
    messages: List[Message] = field(default_factory=list)
    system_prompt: Optional[str] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[str] = None
    output_schema: Optional[Dict[str, Any]] = None
    max_tokens: int = 65536
    timeout_ms: int = 30000
    temperature: float = 0.7
    model_id: str = ""
    trace_id: str = ""
    consumer_id: str = ""
    reasoning_effort: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderResponse:
    """Response from a provider plugin after execute().

    NormalizationLayer converts ProviderResponse -> HubResponse.
    """

    text: str = ""
    tool_calls: Optional[List[ToolCallResult]] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model_id: str = ""
    finish_reason: FinishReason = FinishReason.STOP
    raw_response: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class ProviderChunk:
    """Streaming response chunk from a provider plugin.

    done=True on final chunk.
    """

    text: str = ""
    done: bool = False
    tool_calls: Optional[List[ToolCallResult]] = None
    metadata: Optional[Dict[str, Any]] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(frozen=True)
class ProviderHealth:
    """Health status reported by a provider plugin.

    Status: HEALTHY, DEGRADED, UNHEALTHY.
    """

    status: HealthStatus = HealthStatus.HEALTHY
    latency_ms: int = 0
    error_rate: float = 0.0
    details: str = ""


# ===========================================================================
# IProviderPlugin Protocol (the single contract)
# ===========================================================================


@runtime_checkable
class IProviderPlugin(Protocol):
    """Single contract that ALL provider plugins implement.

    Extension point for adding new LLM providers with zero hub code changes.
    Plugin isolation (MH-17): each plugin runs in its own error boundary.

    Lifecycle:
      1. initialize(manifest) -- setup connections, validate keys.
      2. supports/execute/stream_execute/estimate_tokens/health_check -- runtime.
      3. close() -- cleanup connections, cancel in-flight.

    References:
      - model_hub.mmd: PLUGIN_INTERFACE section
      - Invariant MH-17: Plugin isolation (crash boundary)
      - Invariant MH-18: Manifest is SOLE capability truth
    """

    async def initialize(self, manifest: ProviderManifest) -> None:
        """Initialize plugin with provider manifest.

        Called once on registration. Setup connections, validate API keys.

        Args:
            manifest: Parsed provider manifest (ProviderManifest).
        """
        ...

    def supports(self, capability: CapabilityType) -> bool:
        """Check if provider supports the given capability.

        O(1) lookup from manifest capabilities.

        Args:
            capability: Capability type to check.

        Returns:
            True if provider supports the capability.
        """
        ...

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        """Execute a request against the provider's native API.

        Maps NormalizedRequest -> provider-native API -> ProviderResponse.

        Args:
            request: Provider-agnostic normalized request.

        Returns:
            ProviderResponse with text, tool_calls, token usage.

        Raises:
            ProviderError: Provider returned an error.
            HubTimeoutError: Request exceeded timeout_ms.
            RateLimitError: Provider rate limited.
        """
        ...

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        """Streaming variant of execute().

        Yields chunks with backpressure support. Final chunk has done=True.

        Args:
            request: Provider-agnostic normalized request.

        Yields:
            ProviderChunk instances. Last chunk has done=True.
        """
        ...

    def estimate_tokens(self, messages: List[Message]) -> int:
        """Estimate token count for messages.

        Fast local estimate. Provider-specific tokenizer or tiktoken fallback.

        Args:
            messages: List of conversation messages.

        Returns:
            Estimated token count.
        """
        ...

    async def health_check(self) -> ProviderHealth:
        """Lightweight health probe.

        Uses manifest.health_check.endpoint for probing.

        Returns:
            ProviderHealth with status, latency, error_rate.
        """
        ...

    async def close(self) -> None:
        """Cleanup connections and cancel in-flight requests.

        Called during shutdown or on provider unregistration.
        """
        ...


# ===========================================================================
# __all__
# ===========================================================================

__all__ = [
    # Plugin interface
    "IProviderPlugin",
    # Data types
    "NormalizedRequest",
    "ProviderResponse",
    "ProviderChunk",
    "ProviderHealth",
]
