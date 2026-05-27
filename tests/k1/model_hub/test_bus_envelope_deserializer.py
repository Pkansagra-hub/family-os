"""I-0.5.9.2 -- Bus→ModelHub round-trip integration tests.

Verifies the full pipeline:
  1. Build a JSON-serialised HubRequest
  2. Wrap it in an Envelope
  3. Publish to ``TOPIC_HUB_EXECUTE``
  4. BusEnvelopeDeserializer deserializes → HubRequest
  5. Dispatches to LLMRequestBusAdapter.execute()
  6. Response serialised back → Envelope on ``TOPIC_HUB_RESPONSE``

Tests use LocalBus (in-process) and a stub IModelHubPort.
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, AsyncIterator, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest

from k1.bus.envelope import Envelope, PayloadFormat
from k1.bus.envelope import Priority as BusPriority
from k1.bus.impl.local_bus import LocalBus
from k1.model_hub.adapters.bus_envelope_deserializer import (
    TOPIC_HUB_EXECUTE,
    TOPIC_HUB_RESPONSE,
    BusEnvelopeDeserializer,
    deserialize_hub_request,
    serialize_hub_response,
)
from k1.model_hub.adapters.llm_request_bus_adapter import LLMRequestBusAdapter
from k1.model_hub.types import (
    CapabilityType,
    ChatPayload,
    ChatResult,
    FinishReason,
    HubChunk,
    HubHealthReport,
    HubRequest,
    HubResponse,
    ModelInfo,
    ResponseMetadata,
    TokenUsage,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_response(text: str = "Hello!", request_id: str = "r1") -> HubResponse:
    return HubResponse(
        result=ChatResult(text=text),
        metadata=ResponseMetadata(
            request_id=request_id,
            model_id="gpt-4",
            provider_id="openai",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            cost_usd=0.001,
            latency_ms=100,
            cache_hit=False,
            capability=CapabilityType.CHAT,
            trace_id="trace-1",
            finish_reason=FinishReason.STOP,
        ),
    )


def _make_request_dict(
    capability: str = "CHAT",
    trace_id: str = "trace-1",
    request_id: str = "req-1",
) -> Dict[str, Any]:
    """Build a raw dict that mirrors a serialised HubRequest."""
    return {
        "capability": capability,
        "payload": {
            "messages": [{"role": "user", "content": "hi"}],
            "system_prompt": "You are helpful.",
        },
        "constraints": {
            "max_tokens": 1024,
            "timeout_ms": 5000,
            "priority": "INTERACTIVE",
            "temperature": 0.7,
        },
        "trace_id": trace_id,
        "request_id": request_id,
    }


def _make_envelope(
    data: Dict[str, Any],
    topic: str = TOPIC_HUB_EXECUTE,
) -> Envelope:
    """Wrap a dict into a JSON Envelope."""
    return Envelope(
        topic=topic,
        payload=json.dumps(data).encode("utf-8"),
        payload_format=PayloadFormat.JSON,
        priority=BusPriority.INTERACTIVE,
        cognitive_trace_id=data.get("trace_id", ""),
        session_id="sess-1",
        request_id=data.get("request_id", ""),
    )


class _StubHub:
    """Minimal IModelHubPort that records calls and returns canned response."""

    def __init__(self, response: Optional[HubResponse] = None) -> None:
        self.calls: List[HubRequest] = []
        self._response = response or _make_response()

    async def execute(self, request: HubRequest) -> HubResponse:
        self.calls.append(request)
        return self._response

    async def stream_execute(self, request: HubRequest) -> AsyncIterator[HubChunk]:
        yield HubChunk(content="chunk", done=True)

    async def discover_capabilities(self) -> Dict[CapabilityType, List[str]]:
        return {}

    async def discover_models(self, capability: Optional[CapabilityType] = None) -> List[ModelInfo]:
        return []

    async def health(self) -> HubHealthReport:
        from k1.model_hub.types import HealthStatus

        return HubHealthReport(status=HealthStatus.HEALTHY)


# ===========================================================================
# Unit tests -- deserialize_hub_request / serialize_hub_response
# ===========================================================================


class TestDeserializeHubRequest:
    """Test the standalone deserialization function."""

    def test_chat_request_round_trip(self) -> None:
        data = _make_request_dict()
        req = deserialize_hub_request(data)

        assert req.capability == CapabilityType.CHAT
        assert req.trace_id == "trace-1"
        assert req.request_id == "req-1"
        assert isinstance(req.payload, ChatPayload)
        assert len(req.payload.messages) == 1
        assert req.payload.messages[0].role == "user"
        assert req.payload.messages[0].content == "hi"
        assert req.payload.system_prompt == "You are helpful."
        assert req.constraints.max_tokens == 1024
        assert req.constraints.timeout_ms == 5000

    def test_tool_call_request(self) -> None:
        data = {
            "capability": "TOOL_CALL",
            "payload": {
                "messages": [{"role": "user", "content": "search"}],
                "tools": [{"name": "search", "description": "web search"}],
                "tool_choice": "auto",
            },
            "trace_id": "t-2",
            "request_id": "r-2",
        }
        req = deserialize_hub_request(data)
        assert req.capability == CapabilityType.TOOL_CALL
        assert req.payload.tools == [{"name": "search", "description": "web search"}]

    def test_missing_capability_raises(self) -> None:
        with pytest.raises((ValueError, KeyError)):
            deserialize_hub_request({"trace_id": "t"})

    def test_empty_trace_id_raises(self) -> None:
        data = _make_request_dict(trace_id="")
        with pytest.raises(ValueError, match="trace_id"):
            deserialize_hub_request(data)

    def test_default_constraints(self) -> None:
        data = {
            "capability": "CHAT",
            "payload": {"messages": [{"role": "user", "content": "hi"}]},
            "trace_id": "t-3",
        }
        req = deserialize_hub_request(data)
        assert req.constraints.max_tokens == 65535
        assert req.constraints.timeout_ms == 30000

    def test_unknown_capability_raises(self) -> None:
        data = _make_request_dict(capability="NONEXISTENT")
        with pytest.raises(ValueError):
            deserialize_hub_request(data)

    def test_unknown_payload_passes_raw_dict(self) -> None:
        """Capabilities without a builder pass the raw dict through."""
        data = {
            "capability": "EMBED",
            "payload": {"texts": ["hello"], "dimensions": 768},
            "trace_id": "t-4",
        }
        req = deserialize_hub_request(data)
        assert req.capability == CapabilityType.EMBED
        assert req.payload == {"texts": ["hello"], "dimensions": 768}


class TestSerializeHubResponse:
    """Test the standalone serialization function."""

    def test_round_trip_json(self) -> None:
        resp = _make_response()
        data = serialize_hub_response(resp)
        parsed = json.loads(data)

        assert parsed["result"]["text"] == "Hello!"
        assert parsed["metadata"]["model_id"] == "gpt-4"
        assert parsed["metadata"]["capability"] == "CHAT"
        assert parsed["metadata"]["finish_reason"] == FinishReason.STOP.value

    def test_bytes_output(self) -> None:
        resp = _make_response()
        data = serialize_hub_response(resp)
        assert isinstance(data, bytes)


# ===========================================================================
# Integration tests -- BusEnvelopeDeserializer end-to-end
# ===========================================================================


class TestBusEnvelopeDeserializer:
    """Full pipeline tests using LocalBus."""

    def test_subscribe_on_init(self) -> None:
        """Deserializer subscribes to TOPIC_HUB_EXECUTE on creation."""
        bus = LocalBus()
        hub = _StubHub()
        adapter = LLMRequestBusAdapter(hub)
        deser = BusEnvelopeDeserializer(bus, adapter, loop=asyncio.new_event_loop())

        assert deser.is_subscribed is True
        deser.close()
        assert deser.is_subscribed is False

    def test_close_unsubscribes(self) -> None:
        bus = LocalBus()
        hub = _StubHub()
        adapter = LLMRequestBusAdapter(hub)
        deser = BusEnvelopeDeserializer(bus, adapter, loop=asyncio.new_event_loop())
        deser.close()
        # Double close is safe
        deser.close()
        assert deser.is_subscribed is False

    def test_non_json_envelope_dropped(self) -> None:
        """Envelopes with non-JSON payload_format are logged and dropped."""
        bus = LocalBus()
        hub = _StubHub()
        adapter = LLMRequestBusAdapter(hub)
        loop = asyncio.new_event_loop()
        deser = BusEnvelopeDeserializer(bus, adapter, loop=loop)

        opaque_env = Envelope(
            topic=TOPIC_HUB_EXECUTE,
            payload=b"not json",
            payload_format=PayloadFormat.OPAQUE,
        )
        bus.publish(opaque_env)

        # Give the event loop a tick to process any scheduled coros
        loop.run_until_complete(asyncio.sleep(0.05))

        assert len(hub.calls) == 0
        deser.close()
        loop.close()

    def test_malformed_json_dropped(self) -> None:
        """Invalid JSON is logged and dropped."""
        bus = LocalBus()
        hub = _StubHub()
        adapter = LLMRequestBusAdapter(hub)
        loop = asyncio.new_event_loop()
        deser = BusEnvelopeDeserializer(bus, adapter, loop=loop)

        bad_json_env = Envelope(
            topic=TOPIC_HUB_EXECUTE,
            payload=b"{invalid json",
            payload_format=PayloadFormat.JSON,
        )
        bus.publish(bad_json_env)

        loop.run_until_complete(asyncio.sleep(0.05))
        assert len(hub.calls) == 0
        deser.close()
        loop.close()

    def test_invalid_hub_request_dropped(self) -> None:
        """Valid JSON but bad HubRequest fields are dropped."""
        bus = LocalBus()
        hub = _StubHub()
        adapter = LLMRequestBusAdapter(hub)
        loop = asyncio.new_event_loop()
        deser = BusEnvelopeDeserializer(bus, adapter, loop=loop)

        # Missing capability
        bad_request = Envelope(
            topic=TOPIC_HUB_EXECUTE,
            payload=json.dumps({"trace_id": "t1"}).encode("utf-8"),
            payload_format=PayloadFormat.JSON,
        )
        bus.publish(bad_request)

        loop.run_until_complete(asyncio.sleep(0.05))
        assert len(hub.calls) == 0
        deser.close()
        loop.close()

    def test_full_round_trip(self) -> None:
        """Publish HubRequest → deserialize → execute → publish HubResponse."""
        bus = LocalBus()
        canned = _make_response(text="world", request_id="req-rt")
        hub = _StubHub(response=canned)
        adapter = LLMRequestBusAdapter(hub)

        loop = asyncio.new_event_loop()
        # Run loop in background thread so bus handler can schedule coros
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()

        deser = BusEnvelopeDeserializer(bus, adapter, loop=loop)

        # Capture response envelope
        responses: List[Envelope] = []
        bus.subscribe(TOPIC_HUB_RESPONSE, lambda env: responses.append(env))

        # Publish request
        request_data = _make_request_dict(trace_id="trace-rt", request_id="req-rt")
        request_env = _make_envelope(request_data)
        bus.publish(request_env)

        # Wait for async dispatch
        import time

        deadline = time.monotonic() + 5.0
        while len(hub.calls) == 0 and time.monotonic() < deadline:
            time.sleep(0.01)

        # Verify adapter received the HubRequest
        assert len(hub.calls) == 1
        received = hub.calls[0]
        assert received.capability == CapabilityType.CHAT
        assert received.trace_id == "trace-rt"
        assert received.request_id == "req-rt"
        assert isinstance(received.payload, ChatPayload)
        assert received.payload.messages[0].content == "hi"
        assert received.constraints.max_tokens == 1024

        # Wait for response envelope
        deadline = time.monotonic() + 5.0
        while len(responses) == 0 and time.monotonic() < deadline:
            time.sleep(0.01)

        assert len(responses) == 1
        resp_env = responses[0]
        assert resp_env.topic == TOPIC_HUB_RESPONSE
        assert resp_env.payload_format == PayloadFormat.JSON
        assert resp_env.cognitive_trace_id == "trace-rt"
        assert resp_env.session_id == "sess-1"

        # Verify response payload
        resp_data = json.loads(resp_env.payload.decode("utf-8"))
        assert resp_data["result"]["text"] == "world"
        assert resp_data["metadata"]["model_id"] == "gpt-4"

        # Cleanup
        deser.close()
        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join(timeout=2)
        loop.close()

    def test_execute_error_does_not_crash_bus(self) -> None:
        """If adapter.execute() raises, bus continues functioning."""
        bus = LocalBus()
        mock_hub = AsyncMock()
        mock_hub.execute = AsyncMock(side_effect=RuntimeError("boom"))
        adapter = LLMRequestBusAdapter(mock_hub)

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()

        deser = BusEnvelopeDeserializer(bus, adapter, loop=loop)

        request_data = _make_request_dict()
        request_env = _make_envelope(request_data)

        # Should not raise
        bus.publish(request_env)

        import time

        time.sleep(0.1)

        # Bus should still be alive -- publish another
        request_data2 = _make_request_dict(request_id="req-2", trace_id="t-2")
        bus.publish(_make_envelope(request_data2))
        time.sleep(0.05)

        deser.close()
        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join(timeout=2)
        loop.close()

    def test_response_envelope_parent_id(self) -> None:
        """Response envelope's parent_id links to source envelope_id."""
        bus = LocalBus()
        hub = _StubHub()
        adapter = LLMRequestBusAdapter(hub)

        loop = asyncio.new_event_loop()
        loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
        loop_thread.start()

        deser = BusEnvelopeDeserializer(bus, adapter, loop=loop)

        responses: List[Envelope] = []
        bus.subscribe(TOPIC_HUB_RESPONSE, lambda env: responses.append(env))

        request_data = _make_request_dict()
        request_env = _make_envelope(request_data)
        bus.publish(request_env)

        import time

        deadline = time.monotonic() + 5.0
        while len(responses) == 0 and time.monotonic() < deadline:
            time.sleep(0.01)

        assert len(responses) == 1
        # parent_id should be the envelope_id assigned by the bus to the request
        assert responses[0].parent_id >= 0

        deser.close()
        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join(timeout=2)
        loop.close()

    def test_topic_constants_correct(self) -> None:
        """Topic strings follow k1 naming convention."""
        assert TOPIC_HUB_EXECUTE == "k1.model_hub.execute.v1"
        assert TOPIC_HUB_RESPONSE == "k1.model_hub.execute.response.v1"
