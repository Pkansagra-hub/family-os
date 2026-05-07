"""
E1.7.3 — Unit Tests for poc/k1_poc/llm/model_hub_bridge.py
===========================================================

Validates:
  - ModelHubPOCBridge satisfies IModelHubPort (isinstance check)
  - CHAT capability: HubRequest → POC → HubResponse round-trip
  - TOOL_CALL capability: tools + tool_choice translate correctly
  - STRUCTURED capability: response_schema → json_output mapping
  - REASON capability: thinking level mapping
  - Streaming: stream_execute() yields HubChunk from StreamChunk
  - Token usage: prompt_tokens + completion_tokens in ResponseMetadata
  - discover_capabilities() returns correct set
  - TestModelHubBridge scripted response pass-through

IMPORTANT: Bridge sets scenario="" so test responses keyed to (actor, "").
"""

from __future__ import annotations

import pytest

from k1.concierge.llm.model_hub_bridge import ModelHubPOCBridge
from k1.concierge.llm.test_model_hub_bridge import TestModelHubBridge
from k1.concierge.llm.types import ConciergeModelResponse
from k1.concierge.llm.types import ToolCallResult as POCToolCallResult
from k1.model_hub.ports import IModelHubPort
from k1.model_hub.types import (
    CapabilityType,
    ChatPayload,
    ChatResult,
    HubRequest,
    Message,
    ReasonPayload,
    ReasonResult,
    RequestConstraints,
    StructuredOutputPayload,
    StructuredResult,
    ToolCallPayload,
    ToolCallResultSet,
    ToolDefinition,
)

# =====================================================================
# Fixtures
# =====================================================================


@pytest.fixture
def bridge() -> TestModelHubBridge:
    return TestModelHubBridge()


def _make_chat_request(
    text: str = "hello",
    actor: str = "front",
    trace_id: str = "test-trace",
) -> HubRequest:
    return HubRequest(
        capability=CapabilityType.CHAT,
        payload=ChatPayload(messages=[Message(role="user", content=text)]),
        constraints=RequestConstraints(consumer_id=f"concierge.{actor}"),
        trace_id=trace_id,
    )


# =====================================================================
# isinstance check — bridge satisfies IModelHubPort
# =====================================================================


class TestBridgeSatisfiesProtocol:
    def test_isinstance(self, bridge: TestModelHubBridge) -> None:
        assert isinstance(bridge, IModelHubPort)

    def test_raw_bridge_isinstance(self) -> None:
        from k1.concierge.llm.test_adapter import TestConciergeAdapter

        raw = ModelHubPOCBridge(TestConciergeAdapter())
        assert isinstance(raw, IModelHubPort)


# =====================================================================
# CHAT round-trip
# =====================================================================


class TestChatRoundTrip:
    @pytest.mark.asyncio
    async def test_basic_chat(self, bridge: TestModelHubBridge) -> None:
        bridge.set_response(
            "front",
            "",
            ConciergeModelResponse(
                text="Hi there!",
                model_id="gemini-2.0-flash",
                tokens_in=10,
                tokens_out=5,
                latency_ms=100,
            ),
        )
        req = _make_chat_request("hello", actor="front")
        resp = await bridge.execute(req)

        assert isinstance(resp.result, ChatResult)
        assert resp.result.text == "Hi there!"
        assert resp.metadata.model_id == "gemini-2.0-flash"
        assert resp.metadata.provider_id == "poc-bridge"
        assert resp.metadata.usage.prompt_tokens == 10
        assert resp.metadata.usage.completion_tokens == 5
        assert resp.metadata.latency_ms == 100
        assert resp.metadata.capability == CapabilityType.CHAT

    @pytest.mark.asyncio
    async def test_trace_id_passthrough(self, bridge: TestModelHubBridge) -> None:
        bridge.set_response("front", "", ConciergeModelResponse(text="ok"))
        req = _make_chat_request(trace_id="trace-abc")
        resp = await bridge.execute(req)
        assert resp.metadata.trace_id == "trace-abc"

    @pytest.mark.asyncio
    async def test_consumer_id_parsing(self, bridge: TestModelHubBridge) -> None:
        """'concierge.back' → actor='back' for POC adapter lookup."""
        bridge.set_response("back", "", ConciergeModelResponse(text="back-reply"))
        req = HubRequest(
            capability=CapabilityType.CHAT,
            payload=ChatPayload(messages=[Message(role="user", content="hi")]),
            constraints=RequestConstraints(consumer_id="concierge.back"),
            trace_id="test-trace",
        )
        resp = await bridge.execute(req)
        assert resp.result.text == "back-reply"

    @pytest.mark.asyncio
    async def test_default_response_used(self, bridge: TestModelHubBridge) -> None:
        bridge.set_default_response(ConciergeModelResponse(text="default"))
        req = _make_chat_request(actor="unknown")
        resp = await bridge.execute(req)
        assert resp.result.text == "default"


# =====================================================================
# TOOL_CALL round-trip
# =====================================================================


class TestToolCallRoundTrip:
    @pytest.mark.asyncio
    async def test_tool_call_response(self, bridge: TestModelHubBridge) -> None:
        bridge.set_response(
            "front",
            "",
            ConciergeModelResponse(
                text="",
                tool_calls=[
                    POCToolCallResult(id="tc1", name="search_web", arguments={"q": "test"}),
                    POCToolCallResult(id="tc2", name="get_weather", arguments={"city": "SF"}),
                ],
                tokens_in=20,
                tokens_out=30,
                finish_reason="tool_calls",
            ),
        )
        req = HubRequest(
            capability=CapabilityType.TOOL_CALL,
            payload=ToolCallPayload(
                messages=[Message(role="user", content="search")],
                tools=[
                    ToolDefinition(name="search_web", description="search"),
                    ToolDefinition(name="get_weather", description="weather"),
                ],
                tool_choice="auto",
            ),
            constraints=RequestConstraints(consumer_id="concierge.front"),
            trace_id="test-trace",
        )
        resp = await bridge.execute(req)

        assert isinstance(resp.result, ToolCallResultSet)
        assert len(resp.result.tool_calls) == 2
        assert resp.result.tool_calls[0].name == "search_web"
        assert resp.result.tool_calls[0].arguments == '{"q": "test"}'
        assert resp.result.tool_calls[1].name == "get_weather"
        assert resp.metadata.finish_reason.value == "tool_calls"

    @pytest.mark.asyncio
    async def test_tool_choice_passthrough(self, bridge: TestModelHubBridge) -> None:
        bridge.set_response("front", "", ConciergeModelResponse(text="ok"))
        req = HubRequest(
            capability=CapabilityType.TOOL_CALL,
            payload=ToolCallPayload(
                messages=[Message(role="user", content="x")],
                tools=[ToolDefinition(name="t", description="d")],
                tool_choice="required",
            ),
            constraints=RequestConstraints(consumer_id="concierge.front"),
            trace_id="test-trace",
        )
        # Just verify no error (tool_choice gets passed to POC adapter)
        resp = await bridge.execute(req)
        assert resp is not None


# =====================================================================
# STRUCTURED round-trip
# =====================================================================


class TestStructuredRoundTrip:
    @pytest.mark.asyncio
    async def test_structured_json_output(self, bridge: TestModelHubBridge) -> None:
        bridge.set_response(
            "front",
            "",
            ConciergeModelResponse(
                json_output={"intent": "greeting", "confidence": 0.95},
            ),
        )
        req = HubRequest(
            capability=CapabilityType.STRUCTURED,
            payload=StructuredOutputPayload(
                messages=[Message(role="user", content="classify")],
                output_schema={"type": "object"},
            ),
            constraints=RequestConstraints(consumer_id="concierge.front"),
            trace_id="test-trace",
        )
        resp = await bridge.execute(req)

        assert isinstance(resp.result, StructuredResult)
        assert resp.result.json_output["intent"] == "greeting"
        assert resp.result.json_output["confidence"] == 0.95


# =====================================================================
# REASON round-trip
# =====================================================================


class TestReasonRoundTrip:
    @pytest.mark.asyncio
    async def test_reason_with_thinking(self, bridge: TestModelHubBridge) -> None:
        bridge.set_response(
            "front",
            "",
            ConciergeModelResponse(
                text="The answer is 42",
                thought_text="Let me think step by step...",
                tokens_in=50,
                tokens_out=30,
                tokens_thoughts=100,
            ),
        )
        req = HubRequest(
            capability=CapabilityType.REASON,
            payload=ReasonPayload(
                messages=[Message(role="user", content="what is 6*7?")],
                reasoning_effort="high",
            ),
            constraints=RequestConstraints(consumer_id="concierge.front"),
            trace_id="test-trace",
        )
        resp = await bridge.execute(req)

        assert isinstance(resp.result, ReasonResult)
        assert resp.result.text == "The answer is 42"
        assert resp.result.thinking == "Let me think step by step..."
        # total_tokens includes thinking tokens
        assert resp.metadata.usage.total_tokens == 50 + 30 + 100


# =====================================================================
# Streaming
# =====================================================================


class TestStreaming:
    @pytest.mark.asyncio
    async def test_stream_execute_yields_chunks(self, bridge: TestModelHubBridge) -> None:
        bridge.set_response(
            "front",
            "",
            ConciergeModelResponse(
                text="Hello world",
                tokens_in=5,
                tokens_out=2,
            ),
        )
        req = _make_chat_request("hi", actor="front")
        chunks = []
        async for chunk in bridge.stream_execute(req):
            chunks.append(chunk)

        # Should have text deltas + done
        assert len(chunks) >= 2
        # Last chunk is "done"
        assert chunks[-1].done is True
        assert chunks[-1].metadata is not None
        # At least one content chunk before done
        text_chunks = [c for c in chunks if c.content and not c.done]
        assert len(text_chunks) >= 1
        combined_text = "".join(c.content for c in text_chunks)
        assert combined_text == "Hello world"


# =====================================================================
# Token usage
# =====================================================================


class TestTokenUsage:
    @pytest.mark.asyncio
    async def test_usage_mapping(self, bridge: TestModelHubBridge) -> None:
        bridge.set_response(
            "front",
            "",
            ConciergeModelResponse(
                text="ok",
                tokens_in=100,
                tokens_out=50,
                tokens_thoughts=25,
                latency_ms=234,
            ),
        )
        req = _make_chat_request()
        resp = await bridge.execute(req)

        assert resp.metadata.usage.prompt_tokens == 100
        assert resp.metadata.usage.completion_tokens == 50
        assert resp.metadata.usage.total_tokens == 175  # 100+50+25


# =====================================================================
# discover_capabilities
# =====================================================================


class TestDiscoverCapabilities:
    @pytest.mark.asyncio
    async def test_returns_four_poc_capabilities(self, bridge: TestModelHubBridge) -> None:
        caps = await bridge.discover_capabilities()
        expected = {
            CapabilityType.CHAT,
            CapabilityType.TOOL_CALL,
            CapabilityType.STRUCTURED,
            CapabilityType.REASON,
        }
        assert set(caps.keys()) == expected
        for cap, providers in caps.items():
            assert providers == ["poc-bridge"]


# =====================================================================
# health
# =====================================================================


class TestHealth:
    @pytest.mark.asyncio
    async def test_health_returns_healthy(self, bridge: TestModelHubBridge) -> None:
        report = await bridge.health()
        assert report.status == "HEALTHY"
        assert len(report.providers) == 1
        assert report.providers[0].provider_id == "poc-bridge"


# =====================================================================
# TestModelHubBridge scripted responses
# =====================================================================


class TestTestModelHubBridge:
    @pytest.mark.asyncio
    async def test_set_response(self, bridge: TestModelHubBridge) -> None:
        bridge.set_response("front", "", ConciergeModelResponse(text="scripted"))
        req = _make_chat_request()
        resp = await bridge.execute(req)
        assert resp.result.text == "scripted"

    @pytest.mark.asyncio
    async def test_set_response_sequence(self, bridge: TestModelHubBridge) -> None:
        bridge.set_response_sequence(
            "front",
            "",
            [
                ConciergeModelResponse(text="first"),
                ConciergeModelResponse(text="second"),
                ConciergeModelResponse(text="third"),
            ],
        )
        req = _make_chat_request()
        r1 = await bridge.execute(req)
        r2 = await bridge.execute(req)
        r3 = await bridge.execute(req)
        assert r1.result.text == "first"
        assert r2.result.text == "second"
        assert r3.result.text == "third"

    @pytest.mark.asyncio
    async def test_call_count(self, bridge: TestModelHubBridge) -> None:
        bridge.set_default_response(ConciergeModelResponse(text="x"))
        req = _make_chat_request()
        await bridge.execute(req)
        await bridge.execute(req)
        assert bridge.call_count == 2

    @pytest.mark.asyncio
    async def test_reset(self, bridge: TestModelHubBridge) -> None:
        bridge.set_default_response(ConciergeModelResponse(text="x"))
        req = _make_chat_request()
        await bridge.execute(req)
        bridge.reset()
        assert bridge.call_count == 0

    def test_inner_access(self, bridge: TestModelHubBridge) -> None:
        from k1.concierge.llm.test_adapter import TestConciergeAdapter

        assert isinstance(bridge.inner, TestConciergeAdapter)


# =====================================================================
# Finish reason mapping
# =====================================================================


class TestFinishReasonMapping:
    @pytest.mark.asyncio
    async def test_stop(self, bridge: TestModelHubBridge) -> None:
        bridge.set_response("front", "", ConciergeModelResponse(text="ok", finish_reason="stop"))
        resp = await bridge.execute(_make_chat_request())
        assert resp.metadata.finish_reason.value == "stop"

    @pytest.mark.asyncio
    async def test_tool_calls(self, bridge: TestModelHubBridge) -> None:
        bridge.set_response(
            "front",
            "",
            ConciergeModelResponse(
                tool_calls=[POCToolCallResult(id="t1", name="x", arguments={})],
                finish_reason="tool_calls",
            ),
        )
        req = HubRequest(
            capability=CapabilityType.TOOL_CALL,
            payload=ToolCallPayload(
                messages=[Message(role="user", content="go")],
                tools=[ToolDefinition(name="x", description="d")],
            ),
            constraints=RequestConstraints(consumer_id="concierge.front"),
            trace_id="test-trace",
        )
        resp = await bridge.execute(req)
        assert resp.metadata.finish_reason.value == "tool_calls"

    @pytest.mark.asyncio
    async def test_length(self, bridge: TestModelHubBridge) -> None:
        bridge.set_response("front", "", ConciergeModelResponse(text="...", finish_reason="length"))
        resp = await bridge.execute(_make_chat_request())
        assert resp.metadata.finish_reason.value == "length"

    @pytest.mark.asyncio
    async def test_error(self, bridge: TestModelHubBridge) -> None:
        bridge.set_response("front", "", ConciergeModelResponse(text="", finish_reason="error"))
        resp = await bridge.execute(_make_chat_request())
        assert resp.metadata.finish_reason.value == "error"

    @pytest.mark.asyncio
    async def test_safety(self, bridge: TestModelHubBridge) -> None:
        bridge.set_response("front", "", ConciergeModelResponse(text="", finish_reason="safety"))
        resp = await bridge.execute(_make_chat_request())
        assert resp.metadata.finish_reason.value == "safety"
