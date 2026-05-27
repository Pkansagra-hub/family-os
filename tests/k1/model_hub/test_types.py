"""M1 Foundation -- Test Core Types [F01].

Tests all enums, dataclasses, frozen immutability, field validation,
and error hierarchy defined in k1.model_hub.types.

Covers:
  - 7 Enums: CapabilityType(15), Priority(3), FinishReason(5), HealthStatus(3),
    CircuitState(3), PlacementType(3), ModelTier(3)
  - Conversation primitives: Message, ToolDefinition, ToolCallResult
  - TokenUsage, ModelPreference, ModelInfo
  - RequestConstraints, HubRequest (MH-03 trace_id), ResponseMetadata, HubResponse, HubChunk
  - 15 Capability payloads: ChatPayload through CodeExecPayload
  - ProviderHealthStatus, HubHealthReport
  - 7 Error classes: ModelHubError hierarchy

NO MOCKS.  Pure data structure tests.
"""

from __future__ import annotations

import dataclasses

import pytest

from k1.model_hub.types import (  # Enums; Conversation Primitives; Token & Cost; Model Discovery; Request Envelope; Response Envelope; Capability Payloads; Health; Errors
    AudioInputPayload,
    BatchPayload,
    CachePromptPayload,
    CapabilityType,
    ChatPayload,
    CircuitOpenError,
    CircuitState,
    CodeExecPayload,
    EmbedPayload,
    FinishReason,
    HealthStatus,
    HubChunk,
    HubHealthReport,
    HubRequest,
    HubResponse,
    HubTimeoutError,
    ImageGenPayload,
    Message,
    ModelHubError,
    ModelInfo,
    ModelPreference,
    ModelTier,
    ModeratePayload,
    NoEligibleProviderError,
    PlacementType,
    Priority,
    ProviderError,
    ProviderHealthStatus,
    RateLimitError,
    ReasonPayload,
    RequestConstraints,
    ResponseMetadata,
    StructuredOutputPayload,
    TokenCountPayload,
    TokenUsage,
    ToolCallPayload,
    ToolCallResult,
    ToolDefinition,
    TTSPayload,
    ValidationError,
    VisionPayload,
    WebSearchPayload,
)

# =========================================================================
# Helpers
# =========================================================================


def _msg(role: str = "user", content: str = "hello") -> Message:
    return Message(role=role, content=content)


def _tool_def(name: str = "search") -> ToolDefinition:
    return ToolDefinition(name=name, description="desc", parameters={"type": "object"})


def _tool_result(id: str = "tc1", name: str = "search") -> ToolCallResult:
    return ToolCallResult(id=id, name=name, arguments='{"q":"test"}')


def _usage() -> TokenUsage:
    return TokenUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30)


def _meta() -> ResponseMetadata:
    return ResponseMetadata(
        request_id="r1",
        model_id="gpt-4o",
        provider_id="openai",
        usage=_usage(),
        cost_usd=0.01,
        latency_ms=150,
        cache_hit=False,
        capability=CapabilityType.CHAT,
        trace_id="t1",
    )


# =========================================================================
# Enums
# =========================================================================


class TestCapabilityType:
    def test_member_count(self) -> None:
        assert len(CapabilityType) == 15

    def test_is_str(self) -> None:
        assert isinstance(CapabilityType.CHAT, str)
        assert CapabilityType.CHAT == "CHAT"

    def test_all_members(self) -> None:
        expected = {
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
        assert {m.value for m in CapabilityType} == expected


class TestPriority:
    def test_member_count(self) -> None:
        assert len(Priority) == 3

    def test_values(self) -> None:
        assert Priority.REALTIME.value == "REALTIME"
        assert Priority.INTERACTIVE.value == "INTERACTIVE"
        assert Priority.BACKGROUND.value == "BACKGROUND"


class TestFinishReason:
    def test_member_count(self) -> None:
        assert len(FinishReason) == 6

    def test_values(self) -> None:
        vals = {m.value for m in FinishReason}
        assert vals == {
            "stop",
            "tool_calls",
            "length",
            "error",
            "safety",
            "malformed_tool_call",
        }


class TestHealthStatus:
    def test_members(self) -> None:
        assert len(HealthStatus) == 3
        assert {m.value for m in HealthStatus} == {"HEALTHY", "DEGRADED", "UNHEALTHY"}


class TestCircuitState:
    def test_members(self) -> None:
        assert len(CircuitState) == 3
        assert {m.value for m in CircuitState} == {"CLOSED", "OPEN", "HALF_OPEN"}


class TestPlacementType:
    def test_members(self) -> None:
        assert {m.value for m in PlacementType} == {"remote", "local_gpu", "local_cpu"}


class TestModelTier:
    def test_members(self) -> None:
        assert {m.value for m in ModelTier} == {"FAST", "STANDARD", "PREMIUM"}


# =========================================================================
# Conversation Primitives
# =========================================================================


class TestMessage:
    def test_construction(self) -> None:
        m = _msg()
        assert m.role == "user"
        assert m.content == "hello"
        assert m.tool_call_id is None
        assert m.name is None
        assert m.tool_calls is None

    def test_frozen(self) -> None:
        m = _msg()
        with pytest.raises(dataclasses.FrozenInstanceError):
            m.content = "changed"  # type: ignore[misc]

    def test_empty_role_rejected(self) -> None:
        with pytest.raises(ValueError, match="role must be non-empty"):
            Message(role="", content="hi")


class TestToolDefinition:
    def test_construction(self) -> None:
        t = _tool_def()
        assert t.name == "search"
        assert t.description == "desc"

    def test_frozen(self) -> None:
        t = _tool_def()
        with pytest.raises(dataclasses.FrozenInstanceError):
            t.name = "x"  # type: ignore[misc]

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="name must be non-empty"):
            ToolDefinition(name="", description="d")


class TestToolCallResult:
    def test_construction(self) -> None:
        r = _tool_result()
        assert r.id == "tc1"
        assert r.name == "search"

    def test_frozen(self) -> None:
        r = _tool_result()
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.id = "x"  # type: ignore[misc]

    def test_empty_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="id must be non-empty"):
            ToolCallResult(id="", name="search", arguments="{}")

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="name must be non-empty"):
            ToolCallResult(id="1", name="", arguments="{}")


# =========================================================================
# Token & Cost
# =========================================================================


class TestTokenUsage:
    def test_construction(self) -> None:
        u = _usage()
        assert u.prompt_tokens == 10
        assert u.completion_tokens == 20
        assert u.total_tokens == 30

    def test_defaults(self) -> None:
        u = TokenUsage()
        assert u.prompt_tokens == 0
        assert u.completion_tokens == 0
        assert u.total_tokens == 0

    def test_frozen(self) -> None:
        u = _usage()
        with pytest.raises(dataclasses.FrozenInstanceError):
            u.prompt_tokens = 99  # type: ignore[misc]

    def test_negative_prompt_tokens_rejected(self) -> None:
        with pytest.raises(ValueError, match="prompt_tokens must be >= 0"):
            TokenUsage(prompt_tokens=-1)

    def test_negative_completion_tokens_rejected(self) -> None:
        with pytest.raises(ValueError, match="completion_tokens must be >= 0"):
            TokenUsage(completion_tokens=-1)

    def test_negative_total_tokens_rejected(self) -> None:
        with pytest.raises(ValueError, match="total_tokens must be >= 0"):
            TokenUsage(total_tokens=-1)


# =========================================================================
# Model Discovery
# =========================================================================


class TestModelPreference:
    def test_defaults(self) -> None:
        p = ModelPreference()
        assert p.preferred_provider is None
        assert p.preferred_model is None
        assert p.preferred_tier is None
        assert p.avoid_providers == []

    def test_frozen(self) -> None:
        p = ModelPreference()
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.preferred_provider = "x"  # type: ignore[misc]


class TestModelInfo:
    def test_construction(self) -> None:
        m = ModelInfo(id="gpt-4o", provider_id="openai")
        assert m.id == "gpt-4o"
        assert m.tier == ModelTier.STANDARD
        assert m.supports_streaming is True

    def test_empty_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="id must be non-empty"):
            ModelInfo(id="", provider_id="openai")

    def test_empty_provider_rejected(self) -> None:
        with pytest.raises(ValueError, match="provider_id must be non-empty"):
            ModelInfo(id="gpt-4o", provider_id="")

    def test_negative_cost_rejected(self) -> None:
        with pytest.raises(ValueError, match="cost_per_1m_input must be >= 0"):
            ModelInfo(id="m", provider_id="p", cost_per_1m_input=-1)

    def test_frozen(self) -> None:
        m = ModelInfo(id="gpt-4o", provider_id="openai")
        with pytest.raises(dataclasses.FrozenInstanceError):
            m.id = "x"  # type: ignore[misc]


# =========================================================================
# Request Envelope
# =========================================================================


class TestRequestConstraints:
    def test_defaults(self) -> None:
        c = RequestConstraints()
        assert c.max_tokens == 65535
        assert c.timeout_ms == 30000
        assert c.priority == Priority.INTERACTIVE
        assert c.temperature == 0.7
        assert c.reasoning_effort is None

    def test_frozen(self) -> None:
        c = RequestConstraints()
        with pytest.raises(dataclasses.FrozenInstanceError):
            c.max_tokens = 1  # type: ignore[misc]

    def test_zero_max_tokens_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_tokens must be > 0"):
            RequestConstraints(max_tokens=0)

    def test_zero_timeout_rejected(self) -> None:
        with pytest.raises(ValueError, match="timeout_ms must be > 0"):
            RequestConstraints(timeout_ms=0)

    def test_temperature_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="temperature must be in"):
            RequestConstraints(temperature=2.5)

    def test_reasoning_effort_validation(self) -> None:
        assert RequestConstraints(reasoning_effort="low").reasoning_effort == "low"
        assert RequestConstraints(reasoning_effort="medium").reasoning_effort == "medium"
        assert RequestConstraints(reasoning_effort="high").reasoning_effort == "high"
        with pytest.raises(ValueError, match="reasoning_effort must be"):
            RequestConstraints(reasoning_effort="extreme")


class TestHubRequest:
    def test_construction(self) -> None:
        r = HubRequest(
            capability=CapabilityType.CHAT,
            payload=ChatPayload(messages=[_msg()]),
            trace_id="t1",
        )
        assert r.capability == CapabilityType.CHAT
        assert r.trace_id == "t1"
        assert r.request_id  # auto-generated UUID

    def test_frozen(self) -> None:
        r = HubRequest(
            capability=CapabilityType.CHAT,
            payload=None,
            trace_id="t1",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.trace_id = "x"  # type: ignore[misc]

    def test_empty_trace_id_rejected_mh03(self) -> None:
        """MH-03: trace_id must be non-empty."""
        with pytest.raises(ValueError, match="trace_id must be non-empty"):
            HubRequest(
                capability=CapabilityType.CHAT,
                payload=None,
                trace_id="",
            )

    def test_request_id_auto_generated(self) -> None:
        r1 = HubRequest(capability=CapabilityType.CHAT, payload=None, trace_id="t")
        r2 = HubRequest(capability=CapabilityType.CHAT, payload=None, trace_id="t")
        assert r1.request_id != r2.request_id


# =========================================================================
# Response Envelope
# =========================================================================


class TestResponseMetadata:
    def test_construction(self) -> None:
        m = _meta()
        assert m.request_id == "r1"
        assert m.cost_usd == 0.01
        assert m.finish_reason == FinishReason.STOP

    def test_frozen(self) -> None:
        m = _meta()
        with pytest.raises(dataclasses.FrozenInstanceError):
            m.cost_usd = 99.0  # type: ignore[misc]


class TestHubResponse:
    def test_construction(self) -> None:
        r = HubResponse(result="hello", metadata=_meta())
        assert r.result == "hello"
        assert r.metadata.request_id == "r1"

    def test_frozen(self) -> None:
        r = HubResponse(result="hello", metadata=_meta())
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.result = "x"  # type: ignore[misc]


class TestHubChunk:
    def test_defaults(self) -> None:
        c = HubChunk()
        assert c.content == ""
        assert c.thought == ""
        assert c.done is False
        assert c.metadata is None
        assert c.tool_calls is None

    def test_final_chunk(self) -> None:
        c = HubChunk(content="done", done=True, metadata=_meta())
        assert c.done is True
        assert c.metadata is not None

    def test_frozen(self) -> None:
        c = HubChunk()
        with pytest.raises(dataclasses.FrozenInstanceError):
            c.done = True  # type: ignore[misc]


# =========================================================================
# Capability Payloads
# =========================================================================


class TestChatPayload:
    def test_construction(self) -> None:
        p = ChatPayload(messages=[_msg()])
        assert len(p.messages) == 1
        assert p.system_prompt is None

    def test_empty_messages_rejected(self) -> None:
        with pytest.raises(ValueError, match="messages must be non-empty"):
            ChatPayload(messages=[])

    def test_frozen(self) -> None:
        p = ChatPayload(messages=[_msg()])
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.system_prompt = "x"  # type: ignore[misc]


class TestToolCallPayload:
    def test_construction(self) -> None:
        p = ToolCallPayload(messages=[_msg()], tools=[_tool_def()])
        assert p.tool_choice == "auto"
        assert p.parallel_tool_calls is True

    def test_empty_messages_rejected(self) -> None:
        with pytest.raises(ValueError, match="messages must be non-empty"):
            ToolCallPayload(messages=[], tools=[_tool_def()])

    def test_empty_tools_rejected(self) -> None:
        with pytest.raises(ValueError, match="tools must be non-empty"):
            ToolCallPayload(messages=[_msg()], tools=[])


class TestStructuredOutputPayload:
    def test_construction(self) -> None:
        p = StructuredOutputPayload(
            messages=[_msg()],
            output_schema={"type": "object"},
        )
        assert p.strict is True

    def test_empty_messages_rejected(self) -> None:
        with pytest.raises(ValueError, match="messages must be non-empty"):
            StructuredOutputPayload(messages=[], output_schema={"x": 1})

    def test_empty_schema_rejected(self) -> None:
        with pytest.raises(ValueError, match="output_schema must be non-empty"):
            StructuredOutputPayload(messages=[_msg()], output_schema={})


class TestReasonPayload:
    def test_construction(self) -> None:
        p = ReasonPayload(messages=[_msg()])
        assert p.reasoning_effort == "medium"
        assert p.include_thinking is False

    def test_invalid_effort_rejected(self) -> None:
        with pytest.raises(ValueError, match="reasoning_effort must be"):
            ReasonPayload(messages=[_msg()], reasoning_effort="extreme")


class TestEmbedPayload:
    def test_construction(self) -> None:
        p = EmbedPayload(texts=["hello"])
        assert p.encoding_format == "float"

    def test_empty_texts_rejected(self) -> None:
        with pytest.raises(ValueError, match="texts must be non-empty"):
            EmbedPayload(texts=[])

    def test_invalid_format_rejected(self) -> None:
        with pytest.raises(ValueError, match="encoding_format must be"):
            EmbedPayload(texts=["hi"], encoding_format="binary")


class TestVisionPayload:
    def test_construction(self) -> None:
        p = VisionPayload(messages=[_msg()])
        assert p.detail == "auto"

    def test_invalid_detail_rejected(self) -> None:
        with pytest.raises(ValueError, match="detail must be"):
            VisionPayload(messages=[_msg()], detail="ultra")


class TestBatchPayload:
    def test_construction(self) -> None:
        p = BatchPayload(requests=["r1"])
        assert p.callback_topic is None

    def test_empty_requests_rejected(self) -> None:
        with pytest.raises(ValueError, match="requests must be non-empty"):
            BatchPayload(requests=[])


class TestModeratePayload:
    def test_construction(self) -> None:
        p = ModeratePayload(text="hello")
        assert p.categories is None

    def test_empty_text_rejected(self) -> None:
        with pytest.raises(ValueError, match="text must be non-empty"):
            ModeratePayload(text="")


class TestTokenCountPayload:
    def test_construction(self) -> None:
        p = TokenCountPayload(messages=[_msg()])
        assert p.model_id is None

    def test_empty_messages_rejected(self) -> None:
        with pytest.raises(ValueError, match="messages must be non-empty"):
            TokenCountPayload(messages=[])


class TestCachePromptPayload:
    def test_construction(self) -> None:
        p = CachePromptPayload(cache_key="k1", messages=[_msg()])
        assert p.ttl_s == 300

    def test_empty_key_rejected(self) -> None:
        with pytest.raises(ValueError, match="cache_key must be non-empty"):
            CachePromptPayload(cache_key="", messages=[_msg()])

    def test_empty_messages_rejected(self) -> None:
        with pytest.raises(ValueError, match="messages must be non-empty"):
            CachePromptPayload(cache_key="k", messages=[])

    def test_zero_ttl_rejected(self) -> None:
        with pytest.raises(ValueError, match="ttl_s must be > 0"):
            CachePromptPayload(cache_key="k", messages=[_msg()], ttl_s=0)


class TestAudioInputPayload:
    def test_construction(self) -> None:
        p = AudioInputPayload()
        assert p.messages == []
        assert p.audio == {}


class TestTTSPayload:
    def test_construction(self) -> None:
        p = TTSPayload(text="hi")
        assert p.voice == "alloy"
        assert p.format == "mp3"
        assert p.speed == 1.0

    def test_empty_text_rejected(self) -> None:
        with pytest.raises(ValueError, match="text must be non-empty"):
            TTSPayload(text="")

    def test_invalid_format_rejected(self) -> None:
        with pytest.raises(ValueError, match="format must be"):
            TTSPayload(text="hi", format="wav")

    def test_speed_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="speed must be in"):
            TTSPayload(text="hi", speed=5.0)


class TestImageGenPayload:
    def test_construction(self) -> None:
        p = ImageGenPayload(prompt="cat")
        assert p.size == "1024x1024"
        assert p.n == 1

    def test_empty_prompt_rejected(self) -> None:
        with pytest.raises(ValueError, match="prompt must be non-empty"):
            ImageGenPayload(prompt="")

    def test_zero_n_rejected(self) -> None:
        with pytest.raises(ValueError, match="n must be > 0"):
            ImageGenPayload(prompt="cat", n=0)


class TestWebSearchPayload:
    def test_construction(self) -> None:
        p = WebSearchPayload(query="test")
        assert p.max_results == 5

    def test_empty_query_rejected(self) -> None:
        with pytest.raises(ValueError, match="query must be non-empty"):
            WebSearchPayload(query="")


class TestCodeExecPayload:
    def test_construction(self) -> None:
        p = CodeExecPayload(code="print(1)")
        assert p.language == "python"
        assert p.timeout_s == 30

    def test_empty_code_rejected(self) -> None:
        with pytest.raises(ValueError, match="code must be non-empty"):
            CodeExecPayload(code="")


# =========================================================================
# Health Report
# =========================================================================


class TestProviderHealthStatus:
    def test_construction(self) -> None:
        h = ProviderHealthStatus(provider_id="openai", status=HealthStatus.HEALTHY)
        assert h.latency_ms == 0
        assert h.error_rate == 0.0


class TestHubHealthReport:
    def test_construction(self) -> None:
        h = HubHealthReport(status=HealthStatus.HEALTHY)
        assert h.providers == []
        assert h.active_requests == 0

    def test_frozen(self) -> None:
        h = HubHealthReport(status=HealthStatus.HEALTHY)
        with pytest.raises(dataclasses.FrozenInstanceError):
            h.status = HealthStatus.DEGRADED  # type: ignore[misc]


# =========================================================================
# Error Hierarchy
# =========================================================================


class TestModelHubError:
    def test_base_error(self) -> None:
        e = ModelHubError("fail", request_id="r1", trace_id="t1")
        assert str(e) == "fail"
        assert e.request_id == "r1"
        assert e.trace_id == "t1"
        assert e.capability is None
        assert isinstance(e, Exception)

    def test_with_capability(self) -> None:
        e = ModelHubError("fail", capability=CapabilityType.CHAT)
        assert e.capability == CapabilityType.CHAT


class TestProviderError:
    def test_construction(self) -> None:
        e = ProviderError("api error", provider_id="openai", status_code=429)
        assert e.provider_id == "openai"
        assert e.status_code == 429
        assert isinstance(e, ModelHubError)


class TestNoEligibleProviderError:
    def test_construction(self) -> None:
        e = NoEligibleProviderError("no provider")
        assert isinstance(e, ModelHubError)


class TestRateLimitError:
    def test_construction(self) -> None:
        e = RateLimitError("limited", provider_id="openai", retry_after_ms=1000)
        assert e.provider_id == "openai"
        assert e.retry_after_ms == 1000
        assert isinstance(e, ModelHubError)


class TestCircuitOpenError:
    def test_construction(self) -> None:
        e = CircuitOpenError("open", provider_id="openai", cooldown_remaining_ms=30000)
        assert e.provider_id == "openai"
        assert e.cooldown_remaining_ms == 30000
        assert isinstance(e, ModelHubError)


class TestHubTimeoutError:
    def test_construction(self) -> None:
        e = HubTimeoutError("timeout")
        assert isinstance(e, ModelHubError)


class TestValidationError:
    def test_construction(self) -> None:
        e = ValidationError("bad request")
        assert isinstance(e, ModelHubError)
