"""
K1 Model Hub Types -- Source of Truth for All Consumers
========================================================

ADR: 0001b (Model Hub Architecture & LLM Integration)
Spec: k1/model_hub/model_hub.mmd

Every type comes from the mmd diagram specification.
All dataclasses are frozen (immutable after construction).

Capability Taxonomy (15 capabilities -- extensible without hub changes):
  CHAT, TOOL_CALL, STRUCTURED, REASON, EMBED, VISION, BATCH,
  MODERATE, TOKEN_COUNT, CACHE_PROMPT, AUDIO_IN, TTS,
  IMAGE_GEN, WEB_SEARCH, CODE_EXEC
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Union

# ---------------------------------------------------------------------------
# CapabilityType -- what the hub can route
# ---------------------------------------------------------------------------


class CapabilityType(str, Enum):
    """LLM capability type. Hub routes requests by this tag.

    Core (Day 1): CHAT, TOOL_CALL, STRUCTURED, REASON, TOKEN_COUNT
    Multimodal: VISION, AUDIO_IN, TTS, IMAGE_GEN
    Operational: EMBED, BATCH, MODERATE, CACHE_PROMPT, WEB_SEARCH, CODE_EXEC
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
    """Request priority tier. Affects timeout defaults (MH-15).

    REALTIME: 10s timeout (acks, dispatching)
    INTERACTIVE: 30s timeout (user-facing generation)
    BACKGROUND: 60s timeout (batch, memory, learning)
    """

    REALTIME = "REALTIME"
    INTERACTIVE = "INTERACTIVE"
    BACKGROUND = "BACKGROUND"


class FinishReason(str, Enum):
    """Why the model stopped generating."""

    STOP = "stop"
    TOOL_CALLS = "tool_calls"
    LENGTH = "length"
    ERROR = "error"
    SAFETY = "safety"


# ---------------------------------------------------------------------------
# Message types -- provider-agnostic conversation primitives
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Message:
    """Provider-agnostic conversation message.

    role: "user" | "assistant" | "tool" | "system"
    """

    role: str
    content: str
    tool_call_id: str | None = None
    name: str | None = None
    tool_calls: list[ToolCallResult] | None = None


@dataclass(frozen=True)
class ToolDefinition:
    """Provider-agnostic tool definition (JSON Schema parameters)."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCallResult:
    """Single tool call extracted from model response."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Request types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelPreference:
    """Hint for model selection."""

    model_id: str | None = None
    provider_id: str | None = None
    tier: str | None = None  # "FAST" | "STANDARD" | "PREMIUM"


@dataclass(frozen=True)
class RequestConstraints:
    """Budget and routing constraints for a hub request.

    Default timeouts per priority tier (MH-15):
      REALTIME: 10_000ms, INTERACTIVE: 30_000ms, BACKGROUND: 60_000ms
    """

    max_tokens: int = 65536
    timeout_ms: int = 30_000
    priority: Priority = Priority.INTERACTIVE
    temperature: float = 0.7
    model_preference: ModelPreference | None = None
    provider_preference: str | None = None
    cost_limit: float | None = None
    consumer_id: str = ""


# ---------------------------------------------------------------------------
# Capability Payloads -- polymorphic by CapabilityType
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChatPayload:
    """Payload for CHAT capability."""

    messages: list[Message] = field(default_factory=list)
    system_prompt: str = ""


@dataclass(frozen=True)
class ToolCallPayload:
    """Payload for TOOL_CALL capability."""

    messages: list[Message] = field(default_factory=list)
    system_prompt: str = ""
    tools: list[ToolDefinition] = field(default_factory=list)
    tool_choice: str = "auto"  # "auto" | "required" | "none" | specific name
    parallel_tool_calls: bool = True


@dataclass(frozen=True)
class StructuredOutputPayload:
    """Payload for STRUCTURED capability."""

    messages: list[Message] = field(default_factory=list)
    system_prompt: str = ""
    output_schema: dict[str, Any] = field(default_factory=dict)
    strict: bool = True


@dataclass(frozen=True)
class ReasonPayload:
    """Payload for REASON capability (extended thinking)."""

    messages: list[Message] = field(default_factory=list)
    system_prompt: str = ""
    reasoning_effort: str = "medium"  # "low" | "medium" | "high"
    include_thinking: bool = False


@dataclass(frozen=True)
class EmbedPayload:
    """Payload for EMBED capability."""

    texts: list[str] = field(default_factory=list)
    dimensions: int | None = None
    encoding_format: str = "float"  # "float" | "base64"


@dataclass(frozen=True)
class ImageInput:
    """Single image input for vision capabilities."""

    data: str  # base64-encoded or URL
    media_type: str = "image/png"


@dataclass(frozen=True)
class VisionPayload:
    """Payload for VISION capability."""

    messages: list[Message] = field(default_factory=list)
    image_inputs: list[ImageInput] = field(default_factory=list)
    detail: str = "auto"  # "auto" | "low" | "high"


@dataclass(frozen=True)
class BatchPayload:
    """Payload for BATCH capability."""

    requests: list[Any] = field(default_factory=list)  # list[HubRequest] (forward ref)
    callback_topic: str | None = None


@dataclass(frozen=True)
class ModeratePayload:
    """Payload for MODERATE capability."""

    text: str = ""
    categories: list[str] | None = None  # all categories if None


@dataclass(frozen=True)
class TokenCountPayload:
    """Payload for TOKEN_COUNT capability."""

    messages: list[Message] = field(default_factory=list)
    model_id: str | None = None


@dataclass(frozen=True)
class CachePromptPayload:
    """Payload for CACHE_PROMPT capability."""

    cache_key: str = ""
    messages: list[Message] = field(default_factory=list)
    ttl_s: int = 300


@dataclass(frozen=True)
class AudioInput:
    """Audio data for AUDIO_IN capability."""

    data: str  # base64-encoded
    format: str = "wav"  # "wav" | "mp3" | "ogg" | "flac"


@dataclass(frozen=True)
class VoiceConfig:
    """Voice configuration for audio capabilities."""

    voice: str = "alloy"
    speed: float = 1.0


@dataclass(frozen=True)
class AudioInputPayload:
    """Payload for AUDIO_IN capability."""

    messages: list[Message] = field(default_factory=list)
    audio: AudioInput | None = None
    voice_config: VoiceConfig | None = None


@dataclass(frozen=True)
class TTSPayload:
    """Payload for TTS capability."""

    text: str = ""
    voice: str = "alloy"
    format: str = "mp3"  # "mp3" | "opus" | "aac" | "flac"
    speed: float = 1.0


# Union of all capability payloads
CapabilityPayload = Union[
    ChatPayload,
    ToolCallPayload,
    StructuredOutputPayload,
    ReasonPayload,
    EmbedPayload,
    VisionPayload,
    BatchPayload,
    ModeratePayload,
    TokenCountPayload,
    CachePromptPayload,
    AudioInputPayload,
    TTSPayload,
    dict[str, Any],  # FuturePayload fallback
]


# ---------------------------------------------------------------------------
# HubRequest -- the unified envelope (MH-16: all traffic through this)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HubRequest:
    """Unified request envelope for all Model Hub operations.

    Every consumer (Concierge, Planner, Orchestrator, agents) constructs
    a HubRequest and passes it to IModelHubPort.execute().
    """

    capability: CapabilityType
    payload: CapabilityPayload
    constraints: RequestConstraints = field(default_factory=RequestConstraints)
    trace_id: str = ""
    idempotency_key: str | None = None


# ---------------------------------------------------------------------------
# Response types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Usage:
    """Token usage for a single request."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class ResponseMetadata:
    """Metadata attached to every hub response."""

    request_id: str = ""
    model_id: str = ""
    provider_id: str = ""
    usage: Usage = field(default_factory=Usage)
    cost_usd: float = 0.0
    latency_ms: int = 0
    cache_hit: bool = False
    capability: CapabilityType = CapabilityType.CHAT
    trace_id: str = ""
    fallback_used: bool = False
    finish_reason: FinishReason = FinishReason.STOP


# ---------------------------------------------------------------------------
# Capability Results -- polymorphic by CapabilityType
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChatResult:
    """Result for CHAT capability."""

    text: str = ""


@dataclass(frozen=True)
class ToolCallResultSet:
    """Result for TOOL_CALL capability."""

    text: str = ""
    tool_calls: list[ToolCallResult] = field(default_factory=list)


@dataclass(frozen=True)
class StructuredResult:
    """Result for STRUCTURED capability."""

    json_output: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReasonResult:
    """Result for REASON capability."""

    text: str = ""
    thinking: str = ""


@dataclass(frozen=True)
class EmbedResult:
    """Result for EMBED capability."""

    embeddings: list[list[float]] = field(default_factory=list)


@dataclass(frozen=True)
class ModerationCategory:
    """Single moderation category result."""

    category: str = ""
    flagged: bool = False
    score: float = 0.0


@dataclass(frozen=True)
class ModerateResult:
    """Result for MODERATE capability."""

    flagged: bool = False
    categories: list[ModerationCategory] = field(default_factory=list)


@dataclass(frozen=True)
class TokenCountResult:
    """Result for TOKEN_COUNT capability."""

    count: int = 0


# Union of all capability results
CapabilityResult = Union[
    ChatResult,
    ToolCallResultSet,
    StructuredResult,
    ReasonResult,
    EmbedResult,
    ModerateResult,
    TokenCountResult,
    dict[str, Any],  # generic fallback for future capabilities
]


# ---------------------------------------------------------------------------
# HubResponse -- the unified response envelope
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HubResponse:
    """Unified response envelope for all Model Hub operations."""

    result: CapabilityResult = field(default_factory=lambda: ChatResult())
    metadata: ResponseMetadata = field(default_factory=ResponseMetadata)


# ---------------------------------------------------------------------------
# HubChunk -- streaming chunk
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HubChunk:
    """Single chunk from streaming response.

    chunk_type values:
      "text_delta":      incremental text for real-time display
      "tool_call_delta": tool call accumulating across chunks
      "thought_delta":   thinking/reasoning text
      "done":            final signal with complete HubResponse
    """

    chunk_type: str  # "text_delta" | "tool_call_delta" | "thought_delta" | "done"
    text: str = ""
    tool_call_partial: ToolCallResult | None = None
    thought_text: str = ""
    response: HubResponse | None = None  # populated on "done"


# ---------------------------------------------------------------------------
# ModelInfo -- returned by discover_models()
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelInfo:
    """Information about an available model."""

    model_id: str = ""
    provider_id: str = ""
    capabilities: list[CapabilityType] = field(default_factory=list)
    max_context: int = 0
    max_output: int | None = None
    supports_streaming: bool = True
    tier: str = "STANDARD"  # "FAST" | "STANDARD" | "PREMIUM"
    cost_per_1m_input: float = 0.0
    cost_per_1m_output: float = 0.0
