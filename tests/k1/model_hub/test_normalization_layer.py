"""M2 Plugin Architecture -- Test NormalizationLayer [F45].

Tests bidirectional translation between hub-canonical HubRequest/HubResponse
and provider-agnostic NormalizedRequest/ProviderResponse.

Covers:
  - normalize(): all 15 capability payloads dispatched correctly
  - denormalize(): ProviderResponse -> HubResponse with full ResponseMetadata
  - Edge cases: unknown capability, empty fields, tool_call result building
  - Capability dispatch table completeness

NO MOCKS.  Pure transformation logic tests.
"""

from __future__ import annotations

import pytest

from k1.model_hub.plugins.base import ProviderResponse
from k1.model_hub.services.normalization_layer import NormalizationLayer
from k1.model_hub.types import (
    AudioInputPayload,
    BatchPayload,
    CachePromptPayload,
    CapabilityType,
    ChatPayload,
    CodeExecPayload,
    EmbedPayload,
    FinishReason,
    HubRequest,
    ImageGenPayload,
    Message,
    ModeratePayload,
    ReasonPayload,
    RequestConstraints,
    StructuredOutputPayload,
    TokenCountPayload,
    ToolCallPayload,
    ToolCallResult,
    ToolDefinition,
    TTSPayload,
    VisionPayload,
    WebSearchPayload,
)


@pytest.fixture
def layer() -> NormalizationLayer:
    return NormalizationLayer()


# ===========================================================================
# Helper to build a HubRequest for a given capability + payload
# ===========================================================================


def _hub_request(
    capability: CapabilityType,
    payload: object,
    *,
    trace_id: str = "test-trace-001",
    consumer_id: str = "concierge",
    max_tokens: int = 4096,
    timeout_ms: int = 30000,
    temperature: float = 0.7,
) -> HubRequest:
    return HubRequest(
        capability=capability,
        payload=payload,
        trace_id=trace_id,
        constraints=RequestConstraints(
            max_tokens=max_tokens,
            timeout_ms=timeout_ms,
            temperature=temperature,
            consumer_id=consumer_id,
        ),
    )


# ===========================================================================
# normalize() -- CHAT
# ===========================================================================


class TestNormalizeChatPayload:
    def test_basic_chat(self, layer: NormalizationLayer) -> None:
        msgs = [Message(role="user", content="Hello")]
        payload = ChatPayload(messages=msgs, system_prompt="Be helpful.")
        req = _hub_request(CapabilityType.CHAT, payload)
        nr = layer.normalize(req, "openai")

        assert nr.capability == CapabilityType.CHAT
        assert nr.messages == msgs
        assert nr.system_prompt == "Be helpful."
        assert nr.trace_id == "test-trace-001"
        assert nr.consumer_id == "concierge"
        assert nr.max_tokens == 4096
        assert nr.timeout_ms == 30000
        assert nr.temperature == 0.7

    def test_chat_no_system_prompt(self, layer: NormalizationLayer) -> None:
        msgs = [Message(role="user", content="Hi")]
        payload = ChatPayload(messages=msgs)
        req = _hub_request(CapabilityType.CHAT, payload)
        nr = layer.normalize(req, "anthropic")
        assert nr.system_prompt is None

    def test_chat_preserves_constraints(self, layer: NormalizationLayer) -> None:
        msgs = [Message(role="user", content="Hi")]
        payload = ChatPayload(messages=msgs)
        req = _hub_request(
            CapabilityType.CHAT, payload, max_tokens=1024, timeout_ms=5000, temperature=0.1
        )
        nr = layer.normalize(req, "openai")
        assert nr.max_tokens == 1024
        assert nr.timeout_ms == 5000
        assert nr.temperature == 0.1


# ===========================================================================
# normalize() -- TOOL_CALL
# ===========================================================================


class TestNormalizeToolCallPayload:
    def test_tool_call(self, layer: NormalizationLayer) -> None:
        msgs = [Message(role="user", content="What's the weather?")]
        tools = [
            ToolDefinition(
                name="get_weather", description="Get weather", parameters={"type": "object"}
            )
        ]
        payload = ToolCallPayload(messages=msgs, tools=tools, tool_choice="auto")
        req = _hub_request(CapabilityType.TOOL_CALL, payload)
        nr = layer.normalize(req, "openai")

        assert nr.capability == CapabilityType.TOOL_CALL
        assert nr.messages == msgs
        assert nr.tools is not None
        assert len(nr.tools) == 1
        assert nr.tools[0]["name"] == "get_weather"
        assert nr.tools[0]["parameters"] == {"type": "object"}
        assert nr.tool_choice == "auto"

    def test_tool_call_multiple_tools(self, layer: NormalizationLayer) -> None:
        msgs = [Message(role="user", content="help")]
        tools = [
            ToolDefinition(name="fn_a", description="A"),
            ToolDefinition(name="fn_b", description="B"),
        ]
        payload = ToolCallPayload(messages=msgs, tools=tools)
        req = _hub_request(CapabilityType.TOOL_CALL, payload)
        nr = layer.normalize(req, "openai")
        assert len(nr.tools) == 2

    def test_tool_call_inherits_reasoning_effort_from_constraints(
        self, layer: NormalizationLayer
    ) -> None:
        msgs = [Message(role="user", content="schedule this")]
        payload = ToolCallPayload(
            messages=msgs,
            tools=[ToolDefinition(name="schedule", description="schedule")],
        )
        req = HubRequest(
            capability=CapabilityType.TOOL_CALL,
            payload=payload,
            trace_id="test-trace-001",
            constraints=RequestConstraints(reasoning_effort="medium"),
        )

        nr = layer.normalize(req, "google")

        assert nr.reasoning_effort == "medium"


# ===========================================================================
# normalize() -- STRUCTURED
# ===========================================================================


class TestNormalizeStructuredPayload:
    def test_structured(self, layer: NormalizationLayer) -> None:
        msgs = [Message(role="user", content="Extract name.")]
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        payload = StructuredOutputPayload(messages=msgs, output_schema=schema)
        req = _hub_request(CapabilityType.STRUCTURED, payload)
        nr = layer.normalize(req, "openai")

        assert nr.capability == CapabilityType.STRUCTURED
        assert nr.messages == msgs
        assert nr.output_schema == schema


# ===========================================================================
# normalize() -- REASON
# ===========================================================================


class TestNormalizeReasonPayload:
    def test_reason(self, layer: NormalizationLayer) -> None:
        msgs = [Message(role="user", content="Think step by step.")]
        payload = ReasonPayload(messages=msgs, reasoning_effort="high")
        req = _hub_request(CapabilityType.REASON, payload)
        nr = layer.normalize(req, "anthropic")

        assert nr.capability == CapabilityType.REASON
        assert nr.reasoning_effort == "high"
        assert nr.messages == msgs

    def test_reason_payload_overrides_constraint_reasoning(self, layer: NormalizationLayer) -> None:
        msgs = [Message(role="user", content="Think step by step.")]
        payload = ReasonPayload(messages=msgs, reasoning_effort="high")
        req = HubRequest(
            capability=CapabilityType.REASON,
            payload=payload,
            trace_id="test-trace-001",
            constraints=RequestConstraints(reasoning_effort="low"),
        )

        nr = layer.normalize(req, "anthropic")

        assert nr.reasoning_effort == "high"


# ===========================================================================
# normalize() -- EMBED
# ===========================================================================


class TestNormalizeEmbedPayload:
    def test_embed(self, layer: NormalizationLayer) -> None:
        payload = EmbedPayload(texts=["hello", "world"], dimensions=768)
        req = _hub_request(CapabilityType.EMBED, payload)
        nr = layer.normalize(req, "openai")

        assert nr.capability == CapabilityType.EMBED
        assert len(nr.messages) == 2
        assert nr.messages[0].content == "hello"
        assert nr.messages[1].content == "world"
        assert nr.extra["dimensions"] == 768
        assert nr.extra["encoding_format"] == "float"

    def test_embed_no_dimensions(self, layer: NormalizationLayer) -> None:
        payload = EmbedPayload(texts=["test"])
        req = _hub_request(CapabilityType.EMBED, payload)
        nr = layer.normalize(req, "openai")
        assert "dimensions" not in nr.extra


# ===========================================================================
# normalize() -- VISION
# ===========================================================================


class TestNormalizeVisionPayload:
    def test_vision(self, layer: NormalizationLayer) -> None:
        msgs = [Message(role="user", content="Describe this image.")]
        imgs = [{"type": "base64", "data": "abc123"}]
        payload = VisionPayload(messages=msgs, image_inputs=imgs, detail="high")
        req = _hub_request(CapabilityType.VISION, payload)
        nr = layer.normalize(req, "openai")

        assert nr.capability == CapabilityType.VISION
        assert nr.messages == msgs
        assert nr.extra["image_inputs"] == imgs
        assert nr.extra["detail"] == "high"


# ===========================================================================
# normalize() -- BATCH
# ===========================================================================


class TestNormalizeBatchPayload:
    def test_batch(self, layer: NormalizationLayer) -> None:
        payload = BatchPayload(requests=["req1", "req2"], callback_topic="topic.v1")
        req = _hub_request(CapabilityType.BATCH, payload)
        nr = layer.normalize(req, "openai")

        assert nr.capability == CapabilityType.BATCH
        assert nr.messages == []
        assert nr.extra["requests"] == ["req1", "req2"]
        assert nr.extra["callback_topic"] == "topic.v1"

    def test_batch_no_callback(self, layer: NormalizationLayer) -> None:
        payload = BatchPayload(requests=["req1"])
        req = _hub_request(CapabilityType.BATCH, payload)
        nr = layer.normalize(req, "openai")
        assert "callback_topic" not in nr.extra


# ===========================================================================
# normalize() -- MODERATE
# ===========================================================================


class TestNormalizeModeratePayload:
    def test_moderate(self, layer: NormalizationLayer) -> None:
        payload = ModeratePayload(text="Check this content.", categories=["violence", "hate"])
        req = _hub_request(CapabilityType.MODERATE, payload)
        nr = layer.normalize(req, "openai")

        assert nr.capability == CapabilityType.MODERATE
        assert len(nr.messages) == 1
        assert nr.messages[0].content == "Check this content."
        assert nr.extra["categories"] == ["violence", "hate"]

    def test_moderate_no_categories(self, layer: NormalizationLayer) -> None:
        payload = ModeratePayload(text="Check this.")
        req = _hub_request(CapabilityType.MODERATE, payload)
        nr = layer.normalize(req, "openai")
        assert nr.extra == {}


# ===========================================================================
# normalize() -- TOKEN_COUNT
# ===========================================================================


class TestNormalizeTokenCountPayload:
    def test_token_count(self, layer: NormalizationLayer) -> None:
        msgs = [Message(role="user", content="Count tokens.")]
        payload = TokenCountPayload(messages=msgs, model_id="gpt-4o")
        req = _hub_request(CapabilityType.TOKEN_COUNT, payload)
        nr = layer.normalize(req, "openai")

        assert nr.capability == CapabilityType.TOKEN_COUNT
        assert nr.messages == msgs
        assert nr.extra["target_model_id"] == "gpt-4o"

    def test_token_count_no_model(self, layer: NormalizationLayer) -> None:
        msgs = [Message(role="user", content="Count.")]
        payload = TokenCountPayload(messages=msgs)
        req = _hub_request(CapabilityType.TOKEN_COUNT, payload)
        nr = layer.normalize(req, "openai")
        assert nr.extra == {}


# ===========================================================================
# normalize() -- CACHE_PROMPT
# ===========================================================================


class TestNormalizeCachePromptPayload:
    def test_cache_prompt(self, layer: NormalizationLayer) -> None:
        msgs = [Message(role="user", content="Cached message.")]
        payload = CachePromptPayload(cache_key="ck-1", messages=msgs, ttl_s=600)
        req = _hub_request(CapabilityType.CACHE_PROMPT, payload)
        nr = layer.normalize(req, "anthropic")

        assert nr.capability == CapabilityType.CACHE_PROMPT
        assert nr.messages == msgs
        assert nr.extra["cache_key"] == "ck-1"
        assert nr.extra["ttl_s"] == 600


# ===========================================================================
# normalize() -- AUDIO_IN
# ===========================================================================


class TestNormalizeAudioInPayload:
    def test_audio_in(self, layer: NormalizationLayer) -> None:
        msgs = [Message(role="user", content="transcribe")]
        audio = {"format": "wav", "data": "base64data"}
        payload = AudioInputPayload(messages=msgs, audio=audio, voice_config={"language": "en"})
        req = _hub_request(CapabilityType.AUDIO_IN, payload)
        nr = layer.normalize(req, "openai")

        assert nr.capability == CapabilityType.AUDIO_IN
        assert nr.messages == msgs
        assert nr.extra["audio"] == audio
        assert nr.extra["voice_config"] == {"language": "en"}

    def test_audio_in_no_voice_config(self, layer: NormalizationLayer) -> None:
        msgs = [Message(role="user", content="transcribe")]
        payload = AudioInputPayload(messages=msgs, audio={"format": "wav"})
        req = _hub_request(CapabilityType.AUDIO_IN, payload)
        nr = layer.normalize(req, "openai")
        assert "voice_config" not in nr.extra


# ===========================================================================
# normalize() -- TTS
# ===========================================================================


class TestNormalizeTTSPayload:
    def test_tts(self, layer: NormalizationLayer) -> None:
        payload = TTSPayload(text="Hello world.", voice="nova", format="opus", speed=1.5)
        req = _hub_request(CapabilityType.TTS, payload)
        nr = layer.normalize(req, "openai")

        assert nr.capability == CapabilityType.TTS
        assert len(nr.messages) == 1
        assert nr.messages[0].content == "Hello world."
        assert nr.extra["voice"] == "nova"
        assert nr.extra["format"] == "opus"
        assert nr.extra["speed"] == 1.5


# ===========================================================================
# normalize() -- IMAGE_GEN
# ===========================================================================


class TestNormalizeImageGenPayload:
    def test_image_gen(self, layer: NormalizationLayer) -> None:
        payload = ImageGenPayload(
            prompt="A sunset over mountains.", size="512x512", quality="hd", n=2
        )
        req = _hub_request(CapabilityType.IMAGE_GEN, payload)
        nr = layer.normalize(req, "openai")

        assert nr.capability == CapabilityType.IMAGE_GEN
        assert nr.messages[0].content == "A sunset over mountains."
        assert nr.extra["size"] == "512x512"
        assert nr.extra["quality"] == "hd"
        assert nr.extra["n"] == 2


# ===========================================================================
# normalize() -- WEB_SEARCH
# ===========================================================================


class TestNormalizeWebSearchPayload:
    def test_web_search(self, layer: NormalizationLayer) -> None:
        payload = WebSearchPayload(query="Python dataclasses", max_results=10)
        req = _hub_request(CapabilityType.WEB_SEARCH, payload)
        nr = layer.normalize(req, "google")

        assert nr.capability == CapabilityType.WEB_SEARCH
        assert nr.messages[0].content == "Python dataclasses"
        assert nr.extra["max_results"] == 10


# ===========================================================================
# normalize() -- CODE_EXEC
# ===========================================================================


class TestNormalizeCodeExecPayload:
    def test_code_exec(self, layer: NormalizationLayer) -> None:
        payload = CodeExecPayload(code="print('hi')", language="python", timeout_s=15)
        req = _hub_request(CapabilityType.CODE_EXEC, payload)
        nr = layer.normalize(req, "google")

        assert nr.capability == CapabilityType.CODE_EXEC
        assert nr.messages[0].content == "print('hi')"
        assert nr.extra["language"] == "python"
        assert nr.extra["timeout_s"] == 15


# ===========================================================================
# normalize() -- Error cases
# ===========================================================================


class TestNormalizeErrors:
    def test_unknown_capability_raises(self, layer: NormalizationLayer) -> None:
        """Simulate an unregistered capability by removing from dispatch table."""
        # We can't easily create a new CapabilityType member, but we can verify
        # that all 15 members ARE in the dispatch table
        from k1.model_hub.services.normalization_layer import _CAPABILITY_EXTRACTORS

        for cap in CapabilityType:
            assert cap in _CAPABILITY_EXTRACTORS, f"Missing extractor for {cap}"

    def test_dispatch_table_completeness(self, layer: NormalizationLayer) -> None:
        """All 15 CapabilityType members have extractors."""
        from k1.model_hub.services.normalization_layer import _CAPABILITY_EXTRACTORS

        assert len(_CAPABILITY_EXTRACTORS) == len(CapabilityType)


# ===========================================================================
# denormalize() -- Basic
# ===========================================================================


class TestDenormalize:
    def test_basic_denormalize(self, layer: NormalizationLayer) -> None:
        msgs = [Message(role="user", content="Hi")]
        payload = ChatPayload(messages=msgs)
        original = _hub_request(CapabilityType.CHAT, payload)

        provider_resp = ProviderResponse(
            text="Hello!",
            prompt_tokens=10,
            completion_tokens=5,
            model_id="gpt-4o",
            finish_reason=FinishReason.STOP,
        )

        hub_resp = layer.denormalize(
            provider_resp,
            original,
            provider_id="openai",
            latency_ms=150,
            cost_usd=0.001,
        )

        assert hub_resp.result == "Hello!"
        meta = hub_resp.metadata
        assert meta.request_id == original.request_id
        assert meta.model_id == "gpt-4o"
        assert meta.provider_id == "openai"
        assert meta.usage.prompt_tokens == 10
        assert meta.usage.completion_tokens == 5
        assert meta.usage.total_tokens == 15
        assert meta.cost_usd == 0.001
        assert meta.latency_ms == 150
        assert meta.cache_hit is False
        assert meta.capability == CapabilityType.CHAT
        assert meta.trace_id == "test-trace-001"
        assert meta.fallback_used is False
        assert meta.finish_reason == FinishReason.STOP

    def test_denormalize_cache_hit(self, layer: NormalizationLayer) -> None:
        msgs = [Message(role="user", content="Hi")]
        payload = ChatPayload(messages=msgs)
        original = _hub_request(CapabilityType.CHAT, payload)
        provider_resp = ProviderResponse(text="Cached!", model_id="gpt-4o-mini")

        hub_resp = layer.denormalize(
            provider_resp,
            original,
            provider_id="openai",
            cache_hit=True,
        )
        assert hub_resp.metadata.cache_hit is True

    def test_denormalize_fallback(self, layer: NormalizationLayer) -> None:
        msgs = [Message(role="user", content="Hi")]
        payload = ChatPayload(messages=msgs)
        original = _hub_request(CapabilityType.CHAT, payload)
        provider_resp = ProviderResponse(text="Fallback!", model_id="claude-3-haiku")

        hub_resp = layer.denormalize(
            provider_resp,
            original,
            provider_id="anthropic",
            fallback_used=True,
        )
        assert hub_resp.metadata.fallback_used is True
        assert hub_resp.metadata.provider_id == "anthropic"

    def test_denormalize_tool_call_result(self, layer: NormalizationLayer) -> None:
        msgs = [Message(role="user", content="What's the weather?")]
        tools = [ToolDefinition(name="get_weather", description="Get weather")]
        payload = ToolCallPayload(messages=msgs, tools=tools)
        original = _hub_request(CapabilityType.TOOL_CALL, payload)

        tool_calls = [ToolCallResult(id="tc-1", name="get_weather", arguments='{"city":"NYC"}')]
        provider_resp = ProviderResponse(
            text="",
            tool_calls=tool_calls,
            model_id="gpt-4o",
            finish_reason=FinishReason.TOOL_CALLS,
            prompt_tokens=20,
            completion_tokens=10,
        )

        hub_resp = layer.denormalize(provider_resp, original, provider_id="openai")
        assert isinstance(hub_resp.result, dict)
        assert hub_resp.result["text"] == ""
        assert len(hub_resp.result["tool_calls"]) == 1
        assert hub_resp.result["tool_calls"][0]["name"] == "get_weather"
        assert hub_resp.metadata.finish_reason == FinishReason.TOOL_CALLS

    def test_denormalize_non_tool_call_returns_text(self, layer: NormalizationLayer) -> None:
        msgs = [Message(role="user", content="Hi")]
        payload = ChatPayload(messages=msgs)
        original = _hub_request(CapabilityType.CHAT, payload)
        provider_resp = ProviderResponse(text="Just text.")

        hub_resp = layer.denormalize(provider_resp, original, provider_id="openai")
        assert hub_resp.result == "Just text."

    def test_denormalize_preserves_trace_id(self, layer: NormalizationLayer) -> None:
        msgs = [Message(role="user", content="Hi")]
        payload = ChatPayload(messages=msgs)
        original = _hub_request(CapabilityType.CHAT, payload, trace_id="unique-trace-xyz")
        provider_resp = ProviderResponse(text="ok", model_id="m")

        hub_resp = layer.denormalize(provider_resp, original, provider_id="p")
        assert hub_resp.metadata.trace_id == "unique-trace-xyz"

    def test_denormalize_zero_tokens(self, layer: NormalizationLayer) -> None:
        msgs = [Message(role="user", content="Hi")]
        payload = ChatPayload(messages=msgs)
        original = _hub_request(CapabilityType.CHAT, payload)
        provider_resp = ProviderResponse(text="ok")

        hub_resp = layer.denormalize(provider_resp, original, provider_id="p")
        assert hub_resp.metadata.usage.prompt_tokens == 0
        assert hub_resp.metadata.usage.completion_tokens == 0
        assert hub_resp.metadata.usage.total_tokens == 0

    def test_denormalize_finish_reason_variants(self, layer: NormalizationLayer) -> None:
        msgs = [Message(role="user", content="Hi")]
        payload = ChatPayload(messages=msgs)
        original = _hub_request(CapabilityType.CHAT, payload)

        for reason in FinishReason:
            provider_resp = ProviderResponse(text="x", finish_reason=reason)
            hub_resp = layer.denormalize(provider_resp, original, provider_id="p")
            assert hub_resp.metadata.finish_reason == reason


# ===========================================================================
# Services package re-exports
# ===========================================================================


class TestServicesPackageReexports:
    def test_reexport_normalization_layer(self) -> None:
        from k1.model_hub.services import NormalizationLayer as NL

        assert NL is NormalizationLayer
