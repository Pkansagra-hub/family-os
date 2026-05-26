"""Request/Response normalization layer [F45].

Bidirectional translation between hub-canonical HubRequest/HubResponse
and provider-agnostic NormalizedRequest/ProviderResponse.

Import graph (Layer 3 -- imports Layer 0 + Layer 1 + Layer 2)
--------------------------------------------------------------
k1.model_hub.services.normalization_layer
  -> k1.model_hub.types      (Layer 0)
  -> k1.model_hub.manifest   (Layer 1)
  -> k1.model_hub.plugins    (Layer 2)
  -> stdlib only

NEVER import from any adapter or runtime module.

References
----------
- model_hub.mmd: NormalizationLayer service
- ADR-0001b: Model Hub Architecture
"""

from __future__ import annotations

from typing import Any, Dict

from k1.model_hub.plugins.base import NormalizedRequest, ProviderResponse
from k1.model_hub.types import (
    AudioInputPayload,
    BatchPayload,
    CachePromptPayload,
    CapabilityType,
    ChatPayload,
    CodeExecPayload,
    EmbedPayload,
    HubRequest,
    HubResponse,
    ImageGenPayload,
    Message,
    ModeratePayload,
    ReasonPayload,
    ReasonResult,
    ResponseMetadata,
    StructuredOutputPayload,
    StructuredResult,
    TokenCountPayload,
    TokenUsage,
    ToolCallPayload,
    ToolCallResultSet,
    TTSPayload,
    VisionPayload,
    WebSearchPayload,
)

# ===========================================================================
# Capability extractors (dispatch table entries)
# ===========================================================================


def _extract_chat(payload: ChatPayload) -> Dict[str, Any]:
    """Extract NormalizedRequest fields from ChatPayload."""
    return {
        "messages": payload.messages,
        "system_prompt": payload.system_prompt,
    }


def _extract_tool_call(payload: ToolCallPayload) -> Dict[str, Any]:
    """Extract NormalizedRequest fields from ToolCallPayload."""
    tools = [
        {"name": t.name, "description": t.description, "parameters": t.parameters}
        for t in payload.tools
    ]
    return {
        "messages": payload.messages,
        "tools": tools,
        "tool_choice": payload.tool_choice,
        "system_prompt": payload.system_prompt,
    }


def _extract_structured(payload: StructuredOutputPayload) -> Dict[str, Any]:
    """Extract NormalizedRequest fields from StructuredOutputPayload."""
    return {
        "messages": payload.messages,
        "output_schema": payload.output_schema,
    }


def _extract_reason(payload: ReasonPayload) -> Dict[str, Any]:
    """Extract NormalizedRequest fields from ReasonPayload."""
    return {
        "messages": payload.messages,
        "reasoning_effort": payload.reasoning_effort,
    }


def _extract_embed(payload: EmbedPayload) -> Dict[str, Any]:
    """Extract NormalizedRequest fields from EmbedPayload."""
    messages = [Message(role="user", content=t) for t in payload.texts]
    extra: Dict[str, Any] = {"encoding_format": payload.encoding_format}
    if payload.dimensions is not None:
        extra["dimensions"] = payload.dimensions
    return {
        "messages": messages,
        "extra": extra,
    }


def _extract_vision(payload: VisionPayload) -> Dict[str, Any]:
    """Extract NormalizedRequest fields from VisionPayload."""
    extra: Dict[str, Any] = {
        "image_inputs": payload.image_inputs,
        "detail": payload.detail,
    }
    return {
        "messages": payload.messages,
        "extra": extra,
    }


def _extract_batch(payload: BatchPayload) -> Dict[str, Any]:
    """Extract NormalizedRequest fields from BatchPayload."""
    extra: Dict[str, Any] = {"requests": payload.requests}
    if payload.callback_topic:
        extra["callback_topic"] = payload.callback_topic
    return {
        "messages": [],
        "extra": extra,
    }


def _extract_moderate(payload: ModeratePayload) -> Dict[str, Any]:
    """Extract NormalizedRequest fields from ModeratePayload."""
    messages = [Message(role="user", content=payload.text)]
    extra: Dict[str, Any] = {}
    if payload.categories:
        extra["categories"] = payload.categories
    return {
        "messages": messages,
        "extra": extra,
    }


def _extract_token_count(payload: TokenCountPayload) -> Dict[str, Any]:
    """Extract NormalizedRequest fields from TokenCountPayload."""
    extra: Dict[str, Any] = {}
    if payload.model_id:
        extra["target_model_id"] = payload.model_id
    return {
        "messages": payload.messages,
        "extra": extra,
    }


def _extract_cache_prompt(payload: CachePromptPayload) -> Dict[str, Any]:
    """Extract NormalizedRequest fields from CachePromptPayload."""
    extra: Dict[str, Any] = {
        "cache_key": payload.cache_key,
        "ttl_s": payload.ttl_s,
    }
    return {
        "messages": payload.messages,
        "extra": extra,
    }


def _extract_audio_in(payload: AudioInputPayload) -> Dict[str, Any]:
    """Extract NormalizedRequest fields from AudioInputPayload."""
    extra: Dict[str, Any] = {"audio": payload.audio}
    if payload.voice_config:
        extra["voice_config"] = payload.voice_config
    return {
        "messages": payload.messages,
        "extra": extra,
    }


def _extract_tts(payload: TTSPayload) -> Dict[str, Any]:
    """Extract NormalizedRequest fields from TTSPayload."""
    messages = [Message(role="user", content=payload.text)]
    extra: Dict[str, Any] = {
        "voice": payload.voice,
        "format": payload.format,
        "speed": payload.speed,
    }
    return {
        "messages": messages,
        "extra": extra,
    }


def _extract_image_gen(payload: ImageGenPayload) -> Dict[str, Any]:
    """Extract NormalizedRequest fields from ImageGenPayload."""
    messages = [Message(role="user", content=payload.prompt)]
    extra: Dict[str, Any] = {
        "size": payload.size,
        "quality": payload.quality,
        "n": payload.n,
    }
    return {
        "messages": messages,
        "extra": extra,
    }


def _extract_web_search(payload: WebSearchPayload) -> Dict[str, Any]:
    """Extract NormalizedRequest fields from WebSearchPayload."""
    messages = [Message(role="user", content=payload.query)]
    extra: Dict[str, Any] = {"max_results": payload.max_results}
    return {
        "messages": messages,
        "extra": extra,
    }


def _extract_code_exec(payload: CodeExecPayload) -> Dict[str, Any]:
    """Extract NormalizedRequest fields from CodeExecPayload."""
    messages = [Message(role="user", content=payload.code)]
    extra: Dict[str, Any] = {
        "language": payload.language,
        "timeout_s": payload.timeout_s,
    }
    return {
        "messages": messages,
        "extra": extra,
    }


# ===========================================================================
# Capability dispatch table
# ===========================================================================

_CAPABILITY_EXTRACTORS = {
    CapabilityType.CHAT: _extract_chat,
    CapabilityType.TOOL_CALL: _extract_tool_call,
    CapabilityType.STRUCTURED: _extract_structured,
    CapabilityType.REASON: _extract_reason,
    CapabilityType.EMBED: _extract_embed,
    CapabilityType.VISION: _extract_vision,
    CapabilityType.BATCH: _extract_batch,
    CapabilityType.MODERATE: _extract_moderate,
    CapabilityType.TOKEN_COUNT: _extract_token_count,
    CapabilityType.CACHE_PROMPT: _extract_cache_prompt,
    CapabilityType.AUDIO_IN: _extract_audio_in,
    CapabilityType.TTS: _extract_tts,
    CapabilityType.IMAGE_GEN: _extract_image_gen,
    CapabilityType.WEB_SEARCH: _extract_web_search,
    CapabilityType.CODE_EXEC: _extract_code_exec,
}


# ===========================================================================
# NormalizationLayer
# ===========================================================================


class NormalizationLayer:
    """Bidirectional translation between hub-canonical and provider-agnostic forms.

    normalize(): HubRequest -> NormalizedRequest (for plugin consumption).
    denormalize(): ProviderResponse + original HubRequest -> HubResponse.

    Extensible via capability dispatch table -- new capabilities only need
    a new extractor function and dispatch table entry.

    References:
      - model_hub.mmd: NormalizationLayer service
      - Invariant MH-16: ALL traffic through RequestRouter
    """

    def normalize(
        self,
        request: HubRequest,
        target_provider_id: str,
    ) -> NormalizedRequest:
        """Convert HubRequest to provider-agnostic NormalizedRequest.

        Uses capability dispatch table to extract payload-specific fields.

        Args:
            request: Hub-canonical request envelope.
            target_provider_id: Selected provider ID for model_id resolution.

        Returns:
            NormalizedRequest ready for plugin consumption.

        Raises:
            ValueError: If capability has no registered extractor.
        """
        extractor = _CAPABILITY_EXTRACTORS.get(request.capability)
        if extractor is None:
            raise ValueError(f"No extractor registered for capability {request.capability!r}")

        fields = extractor(request.payload)

        return NormalizedRequest(
            capability=request.capability,
            messages=fields.get("messages", []),
            system_prompt=fields.get("system_prompt"),
            tools=fields.get("tools"),
            tool_choice=fields.get("tool_choice"),
            output_schema=fields.get("output_schema"),
            max_tokens=request.constraints.max_tokens,
            timeout_ms=request.constraints.timeout_ms,
            temperature=request.constraints.temperature,
            model_id=fields.get("model_id", ""),
            trace_id=request.trace_id,
            consumer_id=request.constraints.consumer_id,
            reasoning_effort=fields.get("reasoning_effort") or request.constraints.reasoning_effort,
            extra=fields.get("extra", {}),
        )

    def denormalize(
        self,
        response: ProviderResponse,
        original_request: HubRequest,
        *,
        provider_id: str = "",
        latency_ms: int = 0,
        cache_hit: bool = False,
        cost_usd: float = 0.0,
        fallback_used: bool = False,
    ) -> HubResponse:
        """Convert ProviderResponse back to hub-canonical HubResponse.

        Builds complete ResponseMetadata from provider response + original
        request context.

        Args:
            response: Provider plugin response.
            original_request: Original HubRequest for context (trace_id, etc.).
            provider_id: Provider that handled the request.
            latency_ms: End-to-end latency in milliseconds.
            cache_hit: Whether response came from cache.
            cost_usd: Computed cost for this request.
            fallback_used: Whether a fallback provider was used.

        Returns:
            HubResponse with full ResponseMetadata.
        """
        usage = TokenUsage(
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            total_tokens=response.prompt_tokens + response.completion_tokens,
        )

        metadata = ResponseMetadata(
            request_id=original_request.request_id,
            model_id=response.model_id,
            provider_id=provider_id,
            usage=usage,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            cache_hit=cache_hit,
            capability=original_request.capability,
            trace_id=original_request.trace_id,
            fallback_used=fallback_used,
            finish_reason=response.finish_reason,
        )

        # Build result based on capability type
        result = self._build_result(response, original_request.capability)

        return HubResponse(result=result, metadata=metadata)

    def _build_result(
        self,
        response: ProviderResponse,
        capability: CapabilityType,
    ) -> Any:
        """Build capability-appropriate result from provider response.

        Emits typed result dataclasses (``ChatResult``/``ToolCallResultSet``/
        ``StructuredResult``/``ReasonResult``) expected by downstream
        consumers (concierge ``_unwrap_response``).
        """
        if capability == CapabilityType.TOOL_CALL:
            return ToolCallResultSet(
                text=response.text or "",
                tool_calls=list(response.tool_calls or []),
            )
        if capability == CapabilityType.STRUCTURED:
            raw = response.raw_response or {}
            return StructuredResult(json_output=raw.get("json_output", {}))
        if capability == CapabilityType.REASON:
            raw = response.raw_response or {}
            return ReasonResult(
                text=response.text or "",
                thinking=raw.get("thought_text", ""),
            )
        return response.text or ""


__all__ = [
    "NormalizationLayer",
]
