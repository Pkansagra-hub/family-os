"""Model Hub domain types [F01].

All types that cross the Model Hub boundary and are used by LLM consumers
(Concierge, Planner, Orchestrator, Fabric, Memory Writer, Learning, Agents).

Design decisions
----------------
- All types frozen=True (immutable after creation).
- Pure dataclasses with NO I/O, NO port references, NO service logic.
- No async methods on dataclasses.
- All enums are (str, Enum) for JSON serialization.
- Capability payloads are typed per CapabilityType.

Import graph (Layer 0 -- no internal deps)
------------------------------------------
k1.model_hub.types
  -> stdlib only

NEVER import from any service, port, adapter, or plugin module.

References
----------
- model_hub.mmd: Capability Taxonomy, Payload Schemas, Invariants
- ADR-0001b: Model Hub Architecture & LLM Integration
- ADR-0027:  Placement Cascade
- ADR-0027c: Cost-Aware Fallback
- ADR-0027d: Remote Resilience
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# ===========================================================================
# Enums
# ===========================================================================


class CapabilityType(str, Enum):
    """Capability taxonomy (15 members).

    Core (Day 1): CHAT, TOOL_CALL, STRUCTURED, REASON, TOKEN_COUNT.
    Multimodal: VISION, AUDIO_IN, TTS, IMAGE_GEN.
    Operational: EMBED, BATCH, MODERATE, CACHE_PROMPT, WEB_SEARCH, CODE_EXEC.

    New capabilities added by extending this enum + plugin handler
    (zero hub service changes).
    """

    CHAT = "CHAT"
    TOOL_CALL = "TOOL_CALL"
    STRUCTURED = "STRUCTURED"
    REASON = "REASON"
    EMBED = "EMBED"
    VISION = "VISION"
    BATCH = "BATCH"
    MODERATE = "MODERATE"
    TOKEN_COUNT = "TOKEN_COUNT"
    CACHE_PROMPT = "CACHE_PROMPT"
    AUDIO_IN = "AUDIO_IN"
    TTS = "TTS"
    IMAGE_GEN = "IMAGE_GEN"
    WEB_SEARCH = "WEB_SEARCH"
    CODE_EXEC = "CODE_EXEC"


class Priority(str, Enum):
    """Request priority tier (MH-15).

    REALTIME:    10s timeout (ack, dispatch, delivery).
    INTERACTIVE: 30s timeout (plan, response, tools).
    BACKGROUND:  60s timeout (extraction, learning, batch).
    """

    REALTIME = "REALTIME"
    INTERACTIVE = "INTERACTIVE"
    BACKGROUND = "BACKGROUND"


class FinishReason(str, Enum):
    """Provider response finish reason."""

    STOP = "stop"
    TOOL_CALLS = "tool_calls"
    LENGTH = "length"
    ERROR = "error"
    SAFETY = "safety"
    # Workflow v2 / Fix F: Gemini emits MALFORMED_FUNCTION_CALL when its
    # tool-call schema decoder fails (often token-budget pressure shears the
    # JSON mid-stream). Distinct value lets the ReAct loop run a targeted
    # retry (slim context + restrict tools) instead of aborting like a hard
    # error.
    MALFORMED_TOOL_CALL = "malformed_tool_call"


class HealthStatus(str, Enum):
    """Provider/component health status."""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"


class CircuitState(str, Enum):
    """Circuit breaker state (MH-05)."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class PlacementType(str, Enum):
    """Provider placement type (MH-13, ADR-0027)."""

    REMOTE = "remote"
    LOCAL_GPU = "local_gpu"
    LOCAL_CPU = "local_cpu"


class ModelTier(str, Enum):
    """Performance tier hint from provider manifest."""

    FAST = "FAST"
    STANDARD = "STANDARD"
    PREMIUM = "PREMIUM"


# ===========================================================================
# Conversation Primitives
# ===========================================================================


@dataclass(frozen=True)
class Message:
    """Provider-agnostic conversation message.

    Hub normalizes these to provider-native formats via NormalizationLayer.
    """

    role: str
    content: str
    tool_call_id: Optional[str] = None
    name: Optional[str] = None
    tool_calls: Optional[List[ToolCallResult]] = None

    def __post_init__(self) -> None:
        if not self.role:
            raise ValueError("Message.role must be non-empty")


@dataclass(frozen=True)
class ToolDefinition:
    """Tool schema for function calling (TOOL_CALL capability)."""

    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("ToolDefinition.name must be non-empty")


@dataclass(frozen=True)
class ToolCallResult:
    """Tool call output from provider."""

    id: str
    name: str
    arguments: str

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("ToolCallResult.id must be non-empty")
        if not self.name:
            raise ValueError("ToolCallResult.name must be non-empty")


# ===========================================================================
# Token & Cost
# ===========================================================================


@dataclass(frozen=True)
class TokenUsage:
    """Token usage breakdown from provider response."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __post_init__(self) -> None:
        if self.prompt_tokens < 0:
            raise ValueError(f"TokenUsage.prompt_tokens must be >= 0, got {self.prompt_tokens}")
        if self.completion_tokens < 0:
            raise ValueError(
                f"TokenUsage.completion_tokens must be >= 0, got {self.completion_tokens}"
            )
        if self.total_tokens < 0:
            raise ValueError(f"TokenUsage.total_tokens must be >= 0, got {self.total_tokens}")


# ===========================================================================
# Model Discovery
# ===========================================================================


@dataclass(frozen=True)
class ModelPreference:
    """User/consumer model selection hints.

    Read from SessionState persona (MH-01: read-only).
    """

    preferred_provider: Optional[str] = None
    preferred_model: Optional[str] = None
    preferred_tier: Optional[str] = None
    avoid_providers: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ModelInfo:
    """Model details for discovery (IModelHubPort.discover_models)."""

    id: str
    provider_id: str
    capabilities: List[CapabilityType] = field(default_factory=list)
    cost_per_1m_input: float = 0.0
    cost_per_1m_output: float = 0.0
    max_context: int = 0
    max_output: Optional[int] = None
    tier: ModelTier = ModelTier.STANDARD
    supports_streaming: bool = True

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("ModelInfo.id must be non-empty")
        if not self.provider_id:
            raise ValueError("ModelInfo.provider_id must be non-empty")
        if self.cost_per_1m_input < 0:
            raise ValueError("ModelInfo.cost_per_1m_input must be >= 0")
        if self.cost_per_1m_output < 0:
            raise ValueError("ModelInfo.cost_per_1m_output must be >= 0")


# ===========================================================================
# Request Envelope (MH-03: trace_id required, MH-16: single entry point)
# ===========================================================================


@dataclass(frozen=True)
class RequestConstraints:
    """Request constraints carried in every HubRequest.

    timeout_ms defaults per Priority tier (MH-15):
      REALTIME=10000, INTERACTIVE=30000, BACKGROUND=60000.
    """

    max_tokens: int = 65536
    timeout_ms: int = 30000
    priority: Priority = Priority.INTERACTIVE
    temperature: float = 0.7
    model_preference: Optional[ModelPreference] = None
    provider_preference: Optional[str] = None
    cost_limit: Optional[float] = None
    consumer_id: str = ""

    def __post_init__(self) -> None:
        if self.max_tokens <= 0:
            raise ValueError(f"RequestConstraints.max_tokens must be > 0, got {self.max_tokens}")
        if self.timeout_ms <= 0:
            raise ValueError(f"RequestConstraints.timeout_ms must be > 0, got {self.timeout_ms}")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError(
                f"RequestConstraints.temperature must be in [0.0, 2.0], got {self.temperature}"
            )


@dataclass(frozen=True)
class HubRequest:
    """Unified request envelope for ALL LLM capabilities.

    Single envelope for ALL capabilities. payload is capability-specific
    (ChatPayload, ToolCallPayload, etc.).

    Invariants:
      MH-03: trace_id must be non-empty (end-to-end tracing).
      MH-16: ALL traffic through RequestRouter.
    """

    capability: CapabilityType
    payload: Any
    constraints: RequestConstraints = field(default_factory=RequestConstraints)
    trace_id: str = ""
    idempotency_key: Optional[str] = None
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    # 3.1.1: Per-request session context. Empty string = no session bound
    # (boot tier / shared traffic). RequestRouter will use this to look up
    # the per-session SessionState read port (3.1.3) and ResponseCache will
    # include it in the cache key to prevent cross-session cache hits.
    session_id: str = ""

    def __post_init__(self) -> None:
        if not self.trace_id:
            raise ValueError("HubRequest.trace_id must be non-empty (MH-03)")


# ===========================================================================
# Response Envelope
# ===========================================================================


@dataclass(frozen=True)
class ResponseMetadata:
    """Full response metadata attached to every HubResponse.

    Invariant MH-11: audited fields.
    """

    request_id: str
    model_id: str
    provider_id: str
    usage: TokenUsage
    cost_usd: float
    latency_ms: int
    cache_hit: bool
    capability: CapabilityType
    trace_id: str
    fallback_used: bool = False
    finish_reason: FinishReason = FinishReason.STOP


@dataclass(frozen=True)
class HubResponse:
    """Unified response envelope for ALL LLM capabilities.

    result is capability-specific (text, embeddings, moderation, etc.).
    metadata is always ResponseMetadata.
    """

    result: Any
    metadata: ResponseMetadata


@dataclass(frozen=True)
class HubChunk:
    """Streaming response chunk yielded by stream_execute().

    done=True on final chunk with full metadata.
    """

    content: str = ""
    done: bool = False
    metadata: Optional[ResponseMetadata] = None
    tool_calls: Optional[List[ToolCallResult]] = None


# ===========================================================================
# Capability Payload Dataclasses (one per CapabilityType)
# ===========================================================================


@dataclass(frozen=True)
class ChatPayload:
    """CHAT capability payload."""

    messages: List[Message] = field(default_factory=list)
    system_prompt: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("ChatPayload.messages must be non-empty")


@dataclass(frozen=True)
class ToolCallPayload:
    """TOOL_CALL capability payload."""

    messages: List[Message] = field(default_factory=list)
    tools: List[ToolDefinition] = field(default_factory=list)
    tool_choice: str = "auto"
    parallel_tool_calls: bool = True
    system_prompt: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("ToolCallPayload.messages must be non-empty")
        if not self.tools:
            raise ValueError("ToolCallPayload.tools must be non-empty")


@dataclass(frozen=True)
class StructuredOutputPayload:
    """STRUCTURED capability payload."""

    messages: List[Message] = field(default_factory=list)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    strict: bool = True

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("StructuredOutputPayload.messages must be non-empty")
        if not self.output_schema:
            raise ValueError("StructuredOutputPayload.output_schema must be non-empty")


@dataclass(frozen=True)
class ReasonPayload:
    """REASON capability payload (extended thinking)."""

    messages: List[Message] = field(default_factory=list)
    reasoning_effort: str = "medium"
    include_thinking: bool = False

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("ReasonPayload.messages must be non-empty")
        if self.reasoning_effort not in ("low", "medium", "high"):
            raise ValueError(
                f"ReasonPayload.reasoning_effort must be low|medium|high, "
                f"got {self.reasoning_effort}"
            )


@dataclass(frozen=True)
class EmbedPayload:
    """EMBED capability payload."""

    texts: List[str] = field(default_factory=list)
    dimensions: Optional[int] = None
    encoding_format: str = "float"

    def __post_init__(self) -> None:
        if not self.texts:
            raise ValueError("EmbedPayload.texts must be non-empty")
        if self.encoding_format not in ("float", "base64"):
            raise ValueError(
                f"EmbedPayload.encoding_format must be float|base64, " f"got {self.encoding_format}"
            )


@dataclass(frozen=True)
class VisionPayload:
    """VISION capability payload (image + text input)."""

    messages: List[Message] = field(default_factory=list)
    image_inputs: List[Dict[str, Any]] = field(default_factory=list)
    detail: str = "auto"

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("VisionPayload.messages must be non-empty")
        if self.detail not in ("auto", "low", "high"):
            raise ValueError(f"VisionPayload.detail must be auto|low|high, got {self.detail}")


@dataclass(frozen=True)
class BatchPayload:
    """BATCH capability payload (async batch processing)."""

    requests: List[Any] = field(default_factory=list)
    callback_topic: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.requests:
            raise ValueError("BatchPayload.requests must be non-empty")


@dataclass(frozen=True)
class ModeratePayload:
    """MODERATE capability payload (content safety)."""

    text: str = ""
    categories: Optional[List[str]] = None

    def __post_init__(self) -> None:
        if not self.text:
            raise ValueError("ModeratePayload.text must be non-empty")


@dataclass(frozen=True)
class TokenCountPayload:
    """TOKEN_COUNT capability payload (pre-request token estimation)."""

    messages: List[Message] = field(default_factory=list)
    model_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.messages:
            raise ValueError("TokenCountPayload.messages must be non-empty")


@dataclass(frozen=True)
class CachePromptPayload:
    """CACHE_PROMPT capability payload."""

    cache_key: str = ""
    messages: List[Message] = field(default_factory=list)
    ttl_s: int = 300

    def __post_init__(self) -> None:
        if not self.cache_key:
            raise ValueError("CachePromptPayload.cache_key must be non-empty")
        if not self.messages:
            raise ValueError("CachePromptPayload.messages must be non-empty")
        if self.ttl_s <= 0:
            raise ValueError(f"CachePromptPayload.ttl_s must be > 0, got {self.ttl_s}")


@dataclass(frozen=True)
class AudioInputPayload:
    """AUDIO_IN capability payload."""

    messages: List[Message] = field(default_factory=list)
    audio: Dict[str, Any] = field(default_factory=dict)
    voice_config: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class TTSPayload:
    """TTS capability payload (text-to-speech)."""

    text: str = ""
    voice: str = "alloy"
    format: str = "mp3"
    speed: float = 1.0

    def __post_init__(self) -> None:
        if not self.text:
            raise ValueError("TTSPayload.text must be non-empty")
        if self.format not in ("mp3", "opus", "aac", "flac"):
            raise ValueError(f"TTSPayload.format must be mp3|opus|aac|flac, got {self.format}")
        if not 0.25 <= self.speed <= 4.0:
            raise ValueError(f"TTSPayload.speed must be in [0.25, 4.0], got {self.speed}")


@dataclass(frozen=True)
class ImageGenPayload:
    """IMAGE_GEN capability payload."""

    prompt: str = ""
    size: str = "1024x1024"
    quality: str = "standard"
    n: int = 1

    def __post_init__(self) -> None:
        if not self.prompt:
            raise ValueError("ImageGenPayload.prompt must be non-empty")
        if self.n <= 0:
            raise ValueError(f"ImageGenPayload.n must be > 0, got {self.n}")


@dataclass(frozen=True)
class WebSearchPayload:
    """WEB_SEARCH capability payload."""

    query: str = ""
    max_results: int = 5

    def __post_init__(self) -> None:
        if not self.query:
            raise ValueError("WebSearchPayload.query must be non-empty")


@dataclass(frozen=True)
class CodeExecPayload:
    """CODE_EXEC capability payload (sandboxed execution)."""

    code: str = ""
    language: str = "python"
    timeout_s: int = 30

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("CodeExecPayload.code must be non-empty")


# ===========================================================================
# Capability Result Types (one per CapabilityType)
# ===========================================================================

# Union type for all capability-specific results
CapabilityResult = Any  # Union of ChatResult, ToolCallResultSet, etc.


@dataclass(frozen=True)
class ChatResult:
    """CHAT capability result."""

    text: str = ""


@dataclass(frozen=True)
class ToolCallResultSet:
    """TOOL_CALL capability result (text + tool calls)."""

    text: str = ""
    tool_calls: List[ToolCallResult] = field(default_factory=list)


@dataclass(frozen=True)
class StructuredResult:
    """STRUCTURED capability result (JSON output)."""

    json_output: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReasonResult:
    """REASON capability result (text + thinking trace)."""

    text: str = ""
    thinking: str = ""


# Backward-compat alias: Usage → TokenUsage
Usage = TokenUsage


@dataclass(frozen=True)
class EmbedResult:
    """EMBED capability result (list of embedding vectors)."""

    embeddings: List[List[float]] = field(default_factory=list)


@dataclass(frozen=True)
class ModerationCategory:
    """Single moderation category flag."""

    category: str = ""
    flagged: bool = False
    score: float = 0.0


@dataclass(frozen=True)
class ModerateResult:
    """MODERATE capability result (content safety flags)."""

    flagged: bool = False
    categories: List[ModerationCategory] = field(default_factory=list)


@dataclass(frozen=True)
class TokenCountResult:
    """TOKEN_COUNT capability result."""

    count: int = 0


@dataclass(frozen=True)
class ImageInput:
    """Image input for VisionPayload."""

    data: str = ""
    media_type: str = "image/jpeg"


@dataclass(frozen=True)
class AudioInput:
    """Audio input for AudioInputPayload."""

    data: str = ""
    format: str = "wav"


@dataclass(frozen=True)
class VoiceConfig:
    """Voice configuration for AudioInputPayload."""

    voice: str = "alloy"
    speed: float = 1.0


# ===========================================================================
# Health Report
# ===========================================================================


@dataclass(frozen=True)
class ProviderHealthStatus:
    """Health status for a single provider."""

    provider_id: str
    status: HealthStatus
    latency_ms: int = 0
    error_rate: float = 0.0
    details: str = ""


@dataclass(frozen=True)
class HubHealthReport:
    """Aggregate hub health report (IModelHubPort.health)."""

    status: HealthStatus
    providers: List[ProviderHealthStatus] = field(default_factory=list)
    active_requests: int = 0
    budget_pct: float = 0.0
    cache_hit_rate: float = 0.0


# ===========================================================================
# Error Hierarchy
# ===========================================================================


class ModelHubError(Exception):
    """Base exception for all Model Hub errors."""

    def __init__(
        self,
        message: str,
        *,
        request_id: str = "",
        trace_id: str = "",
        capability: Optional[CapabilityType] = None,
    ) -> None:
        super().__init__(message)
        self.request_id = request_id
        self.trace_id = trace_id
        self.capability = capability


class ProviderError(ModelHubError):
    """Provider returned an error (API error, auth error)."""

    def __init__(
        self,
        message: str,
        *,
        provider_id: str = "",
        status_code: int = 0,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.provider_id = provider_id
        self.status_code = status_code


class NoEligibleProviderError(ModelHubError):
    """No provider supports the requested capability + constraints."""


class RateLimitError(ModelHubError):
    """All providers rate-limited for the requested capability."""

    def __init__(
        self,
        message: str,
        *,
        provider_id: str = "",
        retry_after_ms: int = 0,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.provider_id = provider_id
        self.retry_after_ms = retry_after_ms


class CircuitOpenError(ModelHubError):
    """All providers circuit-broken for the requested capability."""

    def __init__(
        self,
        message: str,
        *,
        provider_id: str = "",
        cooldown_remaining_ms: int = 0,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.provider_id = provider_id
        self.cooldown_remaining_ms = cooldown_remaining_ms


class HubTimeoutError(ModelHubError):
    """Request exceeded timeout_ms (MH-15)."""


class ValidationError(ModelHubError):
    """Invalid HubRequest (missing trace_id, unknown capability)."""


# ===========================================================================
# __all__
# ===========================================================================

__all__ = [
    # Enums
    "CapabilityType",
    "Priority",
    "FinishReason",
    "HealthStatus",
    "CircuitState",
    "PlacementType",
    "ModelTier",
    # Conversation Primitives
    "Message",
    "ToolDefinition",
    "ToolCallResult",
    # Token & Cost
    "TokenUsage",
    # Model Discovery
    "ModelPreference",
    "ModelInfo",
    # Request Envelope
    "RequestConstraints",
    "HubRequest",
    # Response Envelope
    "ResponseMetadata",
    "HubResponse",
    "HubChunk",
    # Capability Payloads
    "ChatPayload",
    "ToolCallPayload",
    "StructuredOutputPayload",
    "ReasonPayload",
    "EmbedPayload",
    "VisionPayload",
    "BatchPayload",
    "ModeratePayload",
    "TokenCountPayload",
    "CachePromptPayload",
    "AudioInputPayload",
    "TTSPayload",
    "ImageGenPayload",
    "WebSearchPayload",
    "CodeExecPayload",
    # Capability Results
    "CapabilityResult",
    "ChatResult",
    "ToolCallResultSet",
    "StructuredResult",
    "ReasonResult",
    "EmbedResult",
    "ModerationCategory",
    "ModerateResult",
    "TokenCountResult",
    "ImageInput",
    "AudioInput",
    "VoiceConfig",
    "Usage",
    # Health
    "ProviderHealthStatus",
    "HubHealthReport",
    # Errors
    "ModelHubError",
    "ProviderError",
    "NoEligibleProviderError",
    "RateLimitError",
    "CircuitOpenError",
    "HubTimeoutError",
    "ValidationError",
]
