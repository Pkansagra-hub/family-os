"""
IProviderPlugin -- Single Contract ALL Providers Implement
===========================================================

ADR: 0001b (Model Hub Architecture & LLM Integration)
Spec: k1/model_hub/model_hub.mmd — PLUGIN_INTERFACE section

Each provider (Gemini, OpenAI, Anthropic, Ollama, local) implements
this interface. The hub never calls provider-native APIs directly;
all traffic flows through the NormalizationLayer → IProviderPlugin.

MH-17: Plugin isolation — one plugin crash does not affect others.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol, runtime_checkable

from k1.model_hub.types import CapabilityType, Message

# ---------------------------------------------------------------------------
# NormalizedRequest — provider-agnostic intermediate form
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NormalizedRequest:
    """Provider-agnostic request after hub normalization.

    The NormalizationLayer converts HubRequest → NormalizedRequest.
    Each plugin translates this to its native API format.
    Hub does NOT know about /chat/completions vs /messages.
    """

    capability: CapabilityType = CapabilityType.CHAT
    messages: list[Message] = field(default_factory=list)
    system_prompt: str = ""
    tools: list[dict[str, Any]] | None = None  # tool definitions as dicts
    tool_choice: str = "auto"
    output_schema: dict[str, Any] | None = None
    max_tokens: int = 65536
    timeout_ms: int = 30_000
    temperature: float = 0.7
    model_id: str = ""
    trace_id: str = ""
    consumer_id: str = ""
    reasoning_effort: str | None = None  # "low" | "medium" | "high"
    extra: dict[str, Any] = field(default_factory=dict)  # capability-specific extras


# ---------------------------------------------------------------------------
# ProviderResponse — provider-agnostic response
# ---------------------------------------------------------------------------


@dataclass
class ProviderResponse:
    """Provider-agnostic response returned by plugin.execute()."""

    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    json_output: dict[str, Any] | None = None
    thinking_text: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    thinking_tokens: int = 0
    model_id: str = ""
    finish_reason: str = "stop"
    latency_ms: int = 0


# ---------------------------------------------------------------------------
# ProviderChunk — streaming chunk from provider
# ---------------------------------------------------------------------------


@dataclass
class ProviderChunk:
    """Single streaming chunk from a provider plugin."""

    chunk_type: str = "text_delta"  # "text_delta" | "tool_call_delta" | "thought_delta" | "done"
    text: str = ""
    tool_call_partial: dict[str, Any] | None = None
    thought_text: str = ""
    response: ProviderResponse | None = None  # populated on "done"


# ---------------------------------------------------------------------------
# ProviderHealth — health check result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderHealth:
    """Health status from a provider health check."""

    status: str = "HEALTHY"  # "HEALTHY" | "DEGRADED" | "UNHEALTHY"
    latency_ms: int = 0
    error_rate: float = 0.0
    message: str = ""


# ---------------------------------------------------------------------------
# ProviderManifest — parsed YAML manifest structure
# ---------------------------------------------------------------------------


@dataclass
class ModelManifest:
    """Single model entry in a provider manifest."""

    id: str = ""
    capabilities: list[CapabilityType] = field(default_factory=list)
    cost_per_1m_input: float = 0.0
    cost_per_1m_output: float = 0.0
    max_context: int = 128_000
    max_output: int | None = None
    supports_streaming: bool = True
    supports_parallel_tools: bool = True
    embedding_dimensions: int | None = None
    rate_limit_rpm: int | None = None
    rate_limit_tpm: int | None = None
    tier: str = "STANDARD"  # "FAST" | "STANDARD" | "PREMIUM"


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker settings from provider manifest."""

    failure_threshold: int = 3
    failure_window_s: int = 60
    cooldown_s: int = 30


@dataclass
class HealthCheckConfig:
    """Health check settings from provider manifest."""

    endpoint: str = ""
    interval_s: int = 30
    timeout_s: int = 5


@dataclass
class ProviderManifest:
    """Parsed provider manifest YAML.

    File location: k1/config/providers/{provider_id}.manifest.yaml
    """

    provider_id: str = ""
    display_name: str = ""
    plugin_class: str = ""
    api_base: str = ""
    auth_type: str = "bearer"  # "bearer" | "api_key_header" | "none"
    credential_key: str = ""
    auth_header_name: str | None = None
    capabilities: list[CapabilityType] = field(default_factory=list)
    models: list[ModelManifest] = field(default_factory=list)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    health_check: HealthCheckConfig = field(default_factory=HealthCheckConfig)
    max_concurrent: int = 10
    rate_limit_rpm: int = 500
    rate_limit_tpm: int = 100_000
    headroom_pct: float = 0.80
    placement_type: str = "remote"  # "remote" | "local_gpu" | "local_cpu"
    device_requirements: str | None = None


# ---------------------------------------------------------------------------
# IProviderPlugin — the contract
# ---------------------------------------------------------------------------


@runtime_checkable
class IProviderPlugin(Protocol):
    """Single contract that ALL provider plugins implement.

    PLUGIN ISOLATION (MH-17):
      Each plugin runs in its own error boundary.
      Plugin crash → circuit breaker OPEN → fallback to next provider.
      Plugin hang → timeout (from manifest) → same fallback.
      Plugins share NOTHING except this interface.
    """

    async def initialize(self, manifest: ProviderManifest) -> None:
        """Called once on registration. Setup connections, validate keys."""
        ...

    def supports(self, capability: CapabilityType) -> bool:
        """Check if this provider supports a capability. O(1) from manifest."""
        ...

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        """Blocking call. Maps NormalizedRequest → provider API → ProviderResponse."""
        ...

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        """Streaming variant. Yields chunks. Supports backpressure + cancel."""
        ...

    async def estimate_tokens(self, messages: list[Message]) -> int:
        """Fast local token estimate. Provider-specific tokenizer or fallback."""
        ...

    async def health_check(self) -> ProviderHealth:
        """Lightweight probe from manifest.health_check.endpoint."""
        ...

    async def close(self) -> None:
        """Cleanup connections, cancel in-flight requests."""
        ...
