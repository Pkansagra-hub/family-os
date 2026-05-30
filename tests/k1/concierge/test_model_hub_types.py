"""
E1.7.1 — Unit Tests for k1/model_hub/types.py
==============================================

Validates:
  - All 15 CapabilityType enum values match mmd table
  - HubRequest construction with each payload type
  - RequestConstraints defaults (timeout per priority tier)
  - HubResponse + ResponseMetadata round-trip
  - HubChunk for each chunk_type
  - Message / ToolDefinition / ToolCallResult immutability (frozen)
"""

from __future__ import annotations

import dataclasses

import pytest

from k1.model_hub.types import (
    AudioInputPayload,
    BatchPayload,
    CachePromptPayload,
    CapabilityType,
    ChatPayload,
    ChatResult,
    EmbedPayload,
    EmbedResult,
    FinishReason,
    HubChunk,
    HubRequest,
    HubResponse,
    Message,
    ModelInfo,
    ModelPreference,
    ModeratePayload,
    ModerateResult,
    ModerationCategory,
    Priority,
    ReasonPayload,
    ReasonResult,
    RequestConstraints,
    ResponseMetadata,
    StructuredOutputPayload,
    StructuredResult,
    TokenCountPayload,
    TokenCountResult,
    ToolCallPayload,
    ToolCallResult,
    ToolCallResultSet,
    ToolDefinition,
    TTSPayload,
    Usage,
    VisionPayload,
)

# =====================================================================
# CapabilityType enum
# =====================================================================


class TestCapabilityType:
    """All 15 capabilities from the mmd table exist."""

    EXPECTED = {
        "CHAT",
        "TOOL_CALL",
        "STRUCTURED",
        "REASON",
        "EMBED",
        "VISION",
        "BATCH",
        "MODERATE",
        "TOKEN_COUNT",
        "CACHE_PROMPT",
        "AUDIO_IN",
        "TTS",
        "IMAGE_GEN",
        "WEB_SEARCH",
        "CODE_EXEC",
    }

    def test_count(self) -> None:
        assert len(CapabilityType) == 15

    def test_all_values_present(self) -> None:
        actual = {c.value for c in CapabilityType}
        assert actual == self.EXPECTED

    @pytest.mark.parametrize("name", EXPECTED)
    def test_lookup_by_name(self, name: str) -> None:
        cap = CapabilityType(name)
        assert cap.value == name

    def test_is_str_enum(self) -> None:
        assert isinstance(CapabilityType.CHAT, str)
        assert CapabilityType.CHAT == "CHAT"


# =====================================================================
# Priority enum
# =====================================================================


class TestPriority:
    def test_three_tiers(self) -> None:
        assert len(Priority) == 3

    def test_values(self) -> None:
        assert Priority.REALTIME.value == "REALTIME"
        assert Priority.INTERACTIVE.value == "INTERACTIVE"
        assert Priority.BACKGROUND.value == "BACKGROUND"


# =====================================================================
# FinishReason enum
# =====================================================================


class TestFinishReason:
    def test_values(self) -> None:
        assert FinishReason.STOP.value == "stop"
        assert FinishReason.TOOL_CALLS.value == "tool_calls"
        assert FinishReason.LENGTH.value == "length"
        assert FinishReason.ERROR.value == "error"
        assert FinishReason.SAFETY.value == "safety"
        assert FinishReason.MALFORMED_TOOL_CALL.value == "malformed_tool_call"


# =====================================================================
# Message / ToolDefinition / ToolCallResult — frozen immutability
# =====================================================================


class TestMessage:
    def test_construction(self) -> None:
        msg = Message(role="user", content="hello")
        assert msg.role == "user"
        assert msg.content == "hello"
        assert msg.tool_call_id is None
        assert msg.name is None
        assert msg.tool_calls is None

    def test_frozen(self) -> None:
        msg = Message(role="user", content="hello")
        with pytest.raises(dataclasses.FrozenInstanceError):
            msg.role = "assistant"  # type: ignore[misc]


class TestToolDefinition:
    def test_construction(self) -> None:
        td = ToolDefinition(name="search", description="search the web")
        assert td.name == "search"
        assert td.parameters == {}

    def test_with_parameters(self) -> None:
        params = {"type": "object", "properties": {"q": {"type": "string"}}}
        td = ToolDefinition(name="search", description="search", parameters=params)
        assert td.parameters == params

    def test_frozen(self) -> None:
        td = ToolDefinition(name="x", description="y")
        with pytest.raises(dataclasses.FrozenInstanceError):
            td.name = "z"  # type: ignore[misc]


class TestToolCallResult:
    def test_construction(self) -> None:
        tc = ToolCallResult(id="tc1", name="search", arguments='{"q": "test"}')
        assert tc.id == "tc1"
        assert tc.name == "search"
        assert tc.arguments == '{"q": "test"}'

    def test_arguments_is_str(self) -> None:
        tc = ToolCallResult(id="tc1", name="search", arguments="")
        assert tc.arguments == ""

    def test_frozen(self) -> None:
        tc = ToolCallResult(id="tc1", name="search", arguments="")
        with pytest.raises(dataclasses.FrozenInstanceError):
            tc.id = "tc2"  # type: ignore[misc]


# =====================================================================
# RequestConstraints defaults
# =====================================================================


class TestRequestConstraints:
    def test_defaults(self) -> None:
        rc = RequestConstraints()
        assert rc.max_tokens == 65535
        assert rc.timeout_ms == 30_000
        assert rc.priority == Priority.INTERACTIVE
        assert rc.temperature == 0.7
        assert rc.model_preference is None
        assert rc.provider_preference is None
        assert rc.cost_limit is None
        assert rc.consumer_id == ""

    def test_with_model_preference(self) -> None:
        pref = ModelPreference(preferred_model="gemini-2.0-flash", preferred_tier="FAST")
        rc = RequestConstraints(model_preference=pref)
        assert rc.model_preference.preferred_model == "gemini-2.0-flash"
        assert rc.model_preference.preferred_tier == "FAST"


# =====================================================================
# Payload types — construction
# =====================================================================


class TestChatPayload:
    def test_construction(self) -> None:
        msgs = [Message(role="user", content="hi")]
        p = ChatPayload(messages=msgs, system_prompt="You are helpful.")
        assert len(p.messages) == 1
        assert p.system_prompt == "You are helpful."

    def test_defaults(self) -> None:
        p = ChatPayload(messages=[Message(role="user", content="hi")])
        assert p.system_prompt is None


class TestToolCallPayload:
    def test_construction(self) -> None:
        tools = [ToolDefinition(name="search", description="search")]
        p = ToolCallPayload(
            messages=[Message(role="user", content="find")],
            tools=tools,
            tool_choice="required",
        )
        assert len(p.tools) == 1
        assert p.tool_choice == "required"
        assert p.parallel_tool_calls is True

    def test_defaults(self) -> None:
        p = ToolCallPayload(
            messages=[Message(role="user", content="find")],
            tools=[ToolDefinition(name="t", description="d")],
        )
        assert p.tool_choice == "auto"


class TestStructuredOutputPayload:
    def test_construction(self) -> None:
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        p = StructuredOutputPayload(
            messages=[Message(role="user", content="extract")],
            output_schema=schema,
            strict=True,
        )
        assert p.output_schema == schema
        assert p.strict is True


class TestReasonPayload:
    def test_construction(self) -> None:
        p = ReasonPayload(
            messages=[Message(role="user", content="think")],
            reasoning_effort="high",
            include_thinking=True,
        )
        assert p.reasoning_effort == "high"
        assert p.include_thinking is True

    def test_defaults(self) -> None:
        p = ReasonPayload(messages=[Message(role="user", content="think")])
        assert p.reasoning_effort == "medium"
        assert p.include_thinking is False


class TestEmbedPayload:
    def test_construction(self) -> None:
        p = EmbedPayload(texts=["hello", "world"], dimensions=768)
        assert len(p.texts) == 2
        assert p.dimensions == 768

    def test_defaults(self) -> None:
        p = EmbedPayload(texts=["hello"])
        assert p.encoding_format == "float"


class TestVisionPayload:
    def test_construction(self) -> None:
        img = {"data": "base64data", "media_type": "image/jpeg"}
        p = VisionPayload(
            messages=[Message(role="user", content="describe")],
            image_inputs=[img],
        )
        assert len(p.image_inputs) == 1
        assert p.detail == "auto"


class TestBatchPayload:
    def test_construction(self) -> None:
        p = BatchPayload(requests=[{"fake": True}], callback_topic="done")
        assert len(p.requests) == 1
        assert p.callback_topic == "done"


class TestModeratePayload:
    def test_construction(self) -> None:
        p = ModeratePayload(text="check this", categories=["violence"])
        assert p.text == "check this"
        assert p.categories == ["violence"]


class TestTokenCountPayload:
    def test_construction(self) -> None:
        p = TokenCountPayload(
            messages=[Message(role="user", content="hello")],
            model_id="gemini-2.0-flash",
        )
        assert len(p.messages) == 1
        assert p.model_id == "gemini-2.0-flash"


class TestCachePromptPayload:
    def test_construction(self) -> None:
        p = CachePromptPayload(
            cache_key="k1",
            messages=[Message(role="user", content="cache me")],
            ttl_s=600,
        )
        assert p.cache_key == "k1"
        assert p.ttl_s == 600


class TestAudioInputPayload:
    def test_construction(self) -> None:
        audio = {"data": "base64wav", "format": "wav"}
        voice = {"voice": "nova", "speed": 1.2}
        p = AudioInputPayload(audio=audio, voice_config=voice)
        assert p.audio["data"] == "base64wav"
        assert p.voice_config["voice"] == "nova"


class TestTTSPayload:
    def test_construction(self) -> None:
        p = TTSPayload(text="Hello world", voice="alloy", format="opus")
        assert p.text == "Hello world"
        assert p.voice == "alloy"
        assert p.format == "opus"
        assert p.speed == 1.0


# =====================================================================
# HubRequest construction with each payload type
# =====================================================================


# Helpers for valid construction
_MSG = [Message(role="user", content="hi")]
_TOOL = [ToolDefinition(name="t", description="d")]
_TID = "trace-1"


class TestHubRequest:
    def test_chat_request(self) -> None:
        req = HubRequest(
            capability=CapabilityType.CHAT,
            payload=ChatPayload(messages=_MSG),
            trace_id=_TID,
        )
        assert req.capability == CapabilityType.CHAT
        assert isinstance(req.payload, ChatPayload)
        assert req.trace_id == _TID
        assert req.idempotency_key is None

    def test_tool_call_request(self) -> None:
        req = HubRequest(
            capability=CapabilityType.TOOL_CALL,
            payload=ToolCallPayload(messages=_MSG, tools=_TOOL),
            trace_id=_TID,
        )
        assert req.capability == CapabilityType.TOOL_CALL

    def test_structured_request(self) -> None:
        req = HubRequest(
            capability=CapabilityType.STRUCTURED,
            payload=StructuredOutputPayload(
                messages=_MSG,
                output_schema={"type": "object"},
            ),
            trace_id=_TID,
        )
        assert isinstance(req.payload, StructuredOutputPayload)

    def test_reason_request(self) -> None:
        req = HubRequest(
            capability=CapabilityType.REASON,
            payload=ReasonPayload(messages=_MSG, reasoning_effort="high"),
            trace_id=_TID,
        )
        assert isinstance(req.payload, ReasonPayload)

    def test_embed_request(self) -> None:
        req = HubRequest(
            capability=CapabilityType.EMBED,
            payload=EmbedPayload(texts=["hello"]),
            trace_id=_TID,
        )
        assert req.capability == CapabilityType.EMBED

    def test_vision_request(self) -> None:
        req = HubRequest(
            capability=CapabilityType.VISION,
            payload=VisionPayload(
                messages=_MSG,
                image_inputs=[{"data": "x"}],
            ),
            trace_id=_TID,
        )
        assert req.capability == CapabilityType.VISION

    def test_moderate_request(self) -> None:
        req = HubRequest(
            capability=CapabilityType.MODERATE,
            payload=ModeratePayload(text="test"),
            trace_id=_TID,
        )
        assert req.capability == CapabilityType.MODERATE

    def test_token_count_request(self) -> None:
        req = HubRequest(
            capability=CapabilityType.TOKEN_COUNT,
            payload=TokenCountPayload(messages=_MSG),
            trace_id=_TID,
        )
        assert req.capability == CapabilityType.TOKEN_COUNT

    def test_batch_request(self) -> None:
        req = HubRequest(
            capability=CapabilityType.BATCH,
            payload=BatchPayload(requests=[{"fake": True}]),
            trace_id=_TID,
        )
        assert req.capability == CapabilityType.BATCH

    def test_cache_prompt_request(self) -> None:
        req = HubRequest(
            capability=CapabilityType.CACHE_PROMPT,
            payload=CachePromptPayload(
                cache_key="ck",
                messages=_MSG,
            ),
            trace_id=_TID,
        )
        assert req.capability == CapabilityType.CACHE_PROMPT

    def test_audio_in_request(self) -> None:
        req = HubRequest(
            capability=CapabilityType.AUDIO_IN,
            payload=AudioInputPayload(),
            trace_id=_TID,
        )
        assert req.capability == CapabilityType.AUDIO_IN

    def test_tts_request(self) -> None:
        req = HubRequest(
            capability=CapabilityType.TTS,
            payload=TTSPayload(text="speak"),
            trace_id=_TID,
        )
        assert req.capability == CapabilityType.TTS

    def test_with_constraints(self) -> None:
        rc = RequestConstraints(
            max_tokens=1024,
            timeout_ms=5000,
            priority=Priority.REALTIME,
            consumer_id="concierge.front",
        )
        req = HubRequest(
            capability=CapabilityType.CHAT,
            payload=ChatPayload(messages=_MSG),
            constraints=rc,
            trace_id="t-123",
            idempotency_key="idem-1",
        )
        assert req.constraints.max_tokens == 1024
        assert req.constraints.priority == Priority.REALTIME
        assert req.trace_id == "t-123"
        assert req.idempotency_key == "idem-1"

    def test_frozen(self) -> None:
        req = HubRequest(
            capability=CapabilityType.CHAT,
            payload=ChatPayload(messages=_MSG),
            trace_id=_TID,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            req.capability = CapabilityType.REASON  # type: ignore[misc]

    def test_dict_payload_fallback(self) -> None:
        """Future payload types use dict fallback."""
        req = HubRequest(
            capability=CapabilityType.IMAGE_GEN,
            payload={"prompt": "draw a cat"},
            trace_id=_TID,
        )
        assert isinstance(req.payload, dict)


# =====================================================================
# Usage / ResponseMetadata / Result types
# =====================================================================


class TestUsage:
    def test_defaults(self) -> None:
        u = Usage()
        assert u.prompt_tokens == 0
        assert u.completion_tokens == 0
        assert u.total_tokens == 0

    def test_construction(self) -> None:
        u = Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
        assert u.total_tokens == 30


class TestResponseMetadata:
    def test_all_fields(self) -> None:
        m = ResponseMetadata(
            request_id="r1",
            model_id="m1",
            provider_id="p1",
            usage=Usage(),
            cost_usd=0.0,
            latency_ms=0,
            cache_hit=False,
            capability=CapabilityType.CHAT,
            trace_id="t-1",
        )
        assert m.request_id == "r1"
        assert m.model_id == "m1"
        assert m.provider_id == "p1"
        assert m.cost_usd == 0.0
        assert m.latency_ms == 0
        assert m.cache_hit is False
        assert m.capability == CapabilityType.CHAT
        assert m.trace_id == "t-1"
        assert m.fallback_used is False
        assert m.finish_reason == FinishReason.STOP

    def test_round_trip(self) -> None:
        m = ResponseMetadata(
            request_id="r1",
            model_id="gemini-2.0-flash",
            provider_id="google",
            usage=Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            cost_usd=0.001,
            latency_ms=234,
            cache_hit=False,
            capability=CapabilityType.TOOL_CALL,
            trace_id="t-1",
            finish_reason=FinishReason.TOOL_CALLS,
        )
        assert m.usage.prompt_tokens == 100
        assert m.capability == CapabilityType.TOOL_CALL
        assert m.finish_reason == FinishReason.TOOL_CALLS


class TestCapabilityResults:
    def test_chat_result(self) -> None:
        r = ChatResult(text="hello")
        assert r.text == "hello"

    def test_tool_call_result_set(self) -> None:
        tc = ToolCallResult(id="tc1", name="search", arguments='{"q": "test"}')
        r = ToolCallResultSet(text="", tool_calls=[tc])
        assert len(r.tool_calls) == 1
        assert r.tool_calls[0].name == "search"

    def test_structured_result(self) -> None:
        r = StructuredResult(json_output={"name": "Alice"})
        assert r.json_output["name"] == "Alice"

    def test_reason_result(self) -> None:
        r = ReasonResult(text="answer", thinking="step by step")
        assert r.thinking == "step by step"

    def test_embed_result(self) -> None:
        r = EmbedResult(embeddings=[[0.1, 0.2], [0.3, 0.4]])
        assert len(r.embeddings) == 2

    def test_moderate_result(self) -> None:
        cat = ModerationCategory(category="violence", flagged=True, score=0.9)
        r = ModerateResult(flagged=True, categories=[cat])
        assert r.flagged is True
        assert r.categories[0].score == 0.9

    def test_token_count_result(self) -> None:
        r = TokenCountResult(count=42)
        assert r.count == 42


# =====================================================================
# HubResponse round-trip
# =====================================================================


def _meta(**overrides: object) -> ResponseMetadata:
    """Build a valid ResponseMetadata with overrides."""
    defaults = dict(
        request_id="r1",
        model_id="m1",
        provider_id="p1",
        usage=Usage(),
        cost_usd=0.0,
        latency_ms=0,
        cache_hit=False,
        capability=CapabilityType.CHAT,
        trace_id="t-1",
    )
    defaults.update(overrides)
    return ResponseMetadata(**defaults)


class TestHubResponse:
    def test_construction(self) -> None:
        r = HubResponse(result=ChatResult(text=""), metadata=_meta())
        assert isinstance(r.result, ChatResult)
        assert r.result.text == ""
        assert r.metadata.model_id == "m1"

    def test_with_chat_result(self) -> None:
        r = HubResponse(
            result=ChatResult(text="hi"),
            metadata=_meta(model_id="m1", latency_ms=100),
        )
        assert r.result.text == "hi"
        assert r.metadata.latency_ms == 100

    def test_with_tool_call_result(self) -> None:
        r = HubResponse(
            result=ToolCallResultSet(
                text="",
                tool_calls=[ToolCallResult(id="tc1", name="search", arguments='{"q": "x"}')],
            ),
            metadata=_meta(
                finish_reason=FinishReason.TOOL_CALLS,
                capability=CapabilityType.TOOL_CALL,
            ),
        )
        assert isinstance(r.result, ToolCallResultSet)
        assert r.metadata.finish_reason == FinishReason.TOOL_CALLS

    def test_with_structured_result(self) -> None:
        r = HubResponse(
            result=StructuredResult(json_output={"key": "val"}),
            metadata=_meta(capability=CapabilityType.STRUCTURED),
        )
        assert isinstance(r.result, StructuredResult)

    def test_frozen(self) -> None:
        r = HubResponse(result=ChatResult(text=""), metadata=_meta())
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.result = ChatResult(text="x")  # type: ignore[misc]


# =====================================================================
# HubChunk for each chunk_type
# =====================================================================


class TestHubChunk:
    def test_text_delta(self) -> None:
        c = HubChunk(content="hello ")
        assert c.content == "hello "
        assert c.done is False
        assert c.metadata is None
        assert c.tool_calls is None

    def test_tool_call_delta(self) -> None:
        tc = ToolCallResult(id="tc1", name="search", arguments="")
        c = HubChunk(tool_calls=[tc])
        assert c.tool_calls[0].name == "search"

    def test_done_chunk(self) -> None:
        c = HubChunk(content="", done=True, metadata=_meta())
        assert c.done is True
        assert c.metadata.model_id == "m1"

    def test_frozen(self) -> None:
        c = HubChunk(content="x")
        with pytest.raises(dataclasses.FrozenInstanceError):
            c.content = "y"  # type: ignore[misc]


# =====================================================================
# ModelInfo
# =====================================================================


class TestModelInfo:
    def test_construction(self) -> None:
        m = ModelInfo(
            id="gemini-2.0-flash",
            provider_id="google",
            capabilities=[CapabilityType.CHAT, CapabilityType.TOOL_CALL],
            max_context=1_000_000,
        )
        assert m.id == "gemini-2.0-flash"
        assert len(m.capabilities) == 2
        assert m.supports_streaming is True

    def test_defaults(self) -> None:
        m = ModelInfo(id="m1", provider_id="p1")
        assert m.cost_per_1m_input == 0.0
