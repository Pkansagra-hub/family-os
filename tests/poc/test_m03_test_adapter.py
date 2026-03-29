"""
M03 Tests: TestConciergeAdapter
================================

Tests for the deterministic test adapter:
  - Fixed responses by (actor, scenario)
  - Sequence responses
  - Streaming simulation
  - Assertion helpers
  - Call recording and querying
  - Protocol compliance (IConciergeModelPort)
"""

from __future__ import annotations

import asyncio

import pytest

from poc.k1_poc.llm.ports import IConciergeModelPort
from poc.k1_poc.llm.test_adapter import TestConciergeAdapter
from poc.k1_poc.llm.types import (
    Capability,
    ConciergeModelRequest,
    ConciergeModelResponse,
    FinishReason,
    ModelMessage,
    ToolCallResult,
    ToolSchema,
)


def _run(coro):
    """Run async coroutine synchronously."""
    return asyncio.run(coro)


# ===================================================================
# Protocol Compliance
# ===================================================================


class TestProtocolCompliance:
    def test_is_runtime_checkable(self):
        """TestConciergeAdapter satisfies IConciergeModelPort protocol."""
        adapter = TestConciergeAdapter()
        assert isinstance(adapter, IConciergeModelPort)

    def test_has_generate(self):
        adapter = TestConciergeAdapter()
        assert hasattr(adapter, "generate")
        assert callable(adapter.generate)

    def test_has_generate_stream(self):
        adapter = TestConciergeAdapter()
        assert hasattr(adapter, "generate_stream")
        assert callable(adapter.generate_stream)


# ===================================================================
# Default Response
# ===================================================================


class TestDefaultResponse:
    def test_returns_ok_by_default(self):
        adapter = TestConciergeAdapter()
        req = ConciergeModelRequest(actor="front", scenario="unknown")
        resp = _run(adapter.generate(req))
        assert resp.text == "OK"
        assert resp.finish_reason == FinishReason.STOP
        assert resp.model_id == "test-model"

    def test_custom_default(self):
        adapter = TestConciergeAdapter()
        adapter.set_default_response(
            ConciergeModelResponse(text="Custom default", model_id="custom")
        )
        req = ConciergeModelRequest(actor="x", scenario="y")
        resp = _run(adapter.generate(req))
        assert resp.text == "Custom default"
        assert resp.model_id == "custom"


# ===================================================================
# Fixed Responses
# ===================================================================


class TestFixedResponses:
    def test_set_and_get_response(self):
        adapter = TestConciergeAdapter()
        adapter.set_response(
            "front",
            "user_input",
            ConciergeModelResponse(
                text="",
                tool_calls=[
                    ToolCallResult(id="c1", name="acknowledge", arguments={"text": "On it!"}),
                ],
                finish_reason=FinishReason.TOOL_CALLS,
            ),
        )
        req = ConciergeModelRequest(actor="front", scenario="user_input")
        resp = _run(adapter.generate(req))
        assert resp.has_tool_calls
        assert resp.tool_calls[0].name == "acknowledge"
        assert resp.finish_reason == FinishReason.TOOL_CALLS

    def test_different_actor_scenario_pairs(self):
        adapter = TestConciergeAdapter()
        adapter.set_response(
            "front",
            "user_input",
            ConciergeModelResponse(text="Front response"),
        )
        adapter.set_response(
            "back",
            "task_dispatch",
            ConciergeModelResponse(text="Back response"),
        )

        front_resp = _run(
            adapter.generate(ConciergeModelRequest(actor="front", scenario="user_input"))
        )
        back_resp = _run(
            adapter.generate(ConciergeModelRequest(actor="back", scenario="task_dispatch"))
        )

        assert front_resp.text == "Front response"
        assert back_resp.text == "Back response"

    def test_same_response_multiple_calls(self):
        adapter = TestConciergeAdapter()
        adapter.set_response(
            "front",
            "ack",
            ConciergeModelResponse(text="Ack!"),
        )
        for _ in range(3):
            resp = _run(adapter.generate(ConciergeModelRequest(actor="front", scenario="ack")))
            assert resp.text == "Ack!"


# ===================================================================
# Sequence Responses
# ===================================================================


class TestSequenceResponses:
    def test_sequence_returns_in_order(self):
        adapter = TestConciergeAdapter()
        adapter.set_response_sequence(
            "front",
            "react",
            [
                ConciergeModelResponse(
                    text="",
                    tool_calls=[ToolCallResult(id="c1", name="acknowledge", arguments={})],
                    finish_reason=FinishReason.TOOL_CALLS,
                ),
                ConciergeModelResponse(
                    text="",
                    tool_calls=[ToolCallResult(id="c2", name="dispatch_task", arguments={})],
                    finish_reason=FinishReason.TOOL_CALLS,
                ),
                ConciergeModelResponse(
                    text="Here is your answer.",
                    finish_reason=FinishReason.STOP,
                ),
            ],
        )

        req = ConciergeModelRequest(actor="front", scenario="react")

        r1 = _run(adapter.generate(req))
        assert r1.tool_calls[0].name == "acknowledge"

        r2 = _run(adapter.generate(req))
        assert r2.tool_calls[0].name == "dispatch_task"

        r3 = _run(adapter.generate(req))
        assert r3.text == "Here is your answer."
        assert r3.finish_reason == FinishReason.STOP

    def test_sequence_repeats_last(self):
        adapter = TestConciergeAdapter()
        adapter.set_response_sequence(
            "back",
            "execute",
            [
                ConciergeModelResponse(text="Step 1"),
                ConciergeModelResponse(text="Done"),
            ],
        )

        req = ConciergeModelRequest(actor="back", scenario="execute")
        _run(adapter.generate(req))  # Step 1
        _run(adapter.generate(req))  # Done

        # Extra calls should repeat last
        r3 = _run(adapter.generate(req))
        assert r3.text == "Done"


# ===================================================================
# Streaming
# ===================================================================


class TestStreaming:
    def test_stream_text_response(self):
        adapter = TestConciergeAdapter()
        adapter.set_response(
            "front",
            "ack",
            ConciergeModelResponse(text="Hello world!", finish_reason=FinishReason.STOP),
        )

        req = ConciergeModelRequest(actor="front", scenario="ack")

        async def collect():
            chunks = []
            async for chunk in adapter.generate_stream(req):
                chunks.append(chunk)
            return chunks

        chunks = _run(collect())

        # Should have text deltas and a done chunk
        text_chunks = [c for c in chunks if c.chunk_type == "text_delta"]
        done_chunks = [c for c in chunks if c.chunk_type == "done"]

        assert len(text_chunks) >= 1
        assert len(done_chunks) == 1

        # Concatenated text should match original
        full_text = "".join(c.text for c in text_chunks)
        assert full_text == "Hello world!"

        # Done chunk has complete response
        assert done_chunks[0].response.text == "Hello world!"

    def test_stream_tool_calls(self):
        adapter = TestConciergeAdapter()
        adapter.set_response(
            "front",
            "react",
            ConciergeModelResponse(
                text="",
                tool_calls=[
                    ToolCallResult(id="c1", name="acknowledge", arguments={"text": "Got it"}),
                    ToolCallResult(id="c2", name="dispatch_task", arguments={"action": "search"}),
                ],
                finish_reason=FinishReason.TOOL_CALLS,
            ),
        )

        req = ConciergeModelRequest(actor="front", scenario="react")

        async def collect():
            chunks = []
            async for chunk in adapter.generate_stream(req):
                chunks.append(chunk)
            return chunks

        chunks = _run(collect())
        tool_chunks = [c for c in chunks if c.chunk_type == "tool_call_delta"]
        assert len(tool_chunks) == 2
        assert tool_chunks[0].tool_call_partial.name == "acknowledge"
        assert tool_chunks[1].tool_call_partial.name == "dispatch_task"

    def test_stream_empty_response(self):
        adapter = TestConciergeAdapter()
        adapter.set_response(
            "front",
            "empty",
            ConciergeModelResponse(text="", finish_reason=FinishReason.STOP),
        )

        req = ConciergeModelRequest(actor="front", scenario="empty")

        async def collect():
            chunks = []
            async for chunk in adapter.generate_stream(req):
                chunks.append(chunk)
            return chunks

        chunks = _run(collect())
        text_chunks = [c for c in chunks if c.chunk_type == "text_delta"]
        done_chunks = [c for c in chunks if c.chunk_type == "done"]

        assert len(text_chunks) == 0
        assert len(done_chunks) == 1


# ===================================================================
# Call Recording & Assertion Helpers
# ===================================================================


class TestCallRecording:
    def test_call_count(self):
        adapter = TestConciergeAdapter()
        assert adapter.call_count == 0

        req = ConciergeModelRequest(actor="front", scenario="test")
        _run(adapter.generate(req))
        assert adapter.call_count == 1

        _run(adapter.generate(req))
        assert adapter.call_count == 2

    def test_last_call(self):
        adapter = TestConciergeAdapter()
        assert adapter.last_call is None

        req1 = ConciergeModelRequest(actor="front", scenario="first")
        req2 = ConciergeModelRequest(actor="back", scenario="second")

        _run(adapter.generate(req1))
        assert adapter.last_call.scenario == "first"

        _run(adapter.generate(req2))
        assert adapter.last_call.scenario == "second"

    def test_calls_for(self):
        adapter = TestConciergeAdapter()
        _run(adapter.generate(ConciergeModelRequest(actor="front", scenario="a")))
        _run(adapter.generate(ConciergeModelRequest(actor="back", scenario="b")))
        _run(adapter.generate(ConciergeModelRequest(actor="front", scenario="a")))

        front_a = adapter.calls_for("front", "a")
        assert len(front_a) == 2

        back_b = adapter.calls_for("back", "b")
        assert len(back_b) == 1

        front_b = adapter.calls_for("front", "b")
        assert len(front_b) == 0

    def test_calls_for_actor(self):
        adapter = TestConciergeAdapter()
        _run(adapter.generate(ConciergeModelRequest(actor="front", scenario="a")))
        _run(adapter.generate(ConciergeModelRequest(actor="front", scenario="b")))
        _run(adapter.generate(ConciergeModelRequest(actor="back", scenario="c")))

        assert len(adapter.calls_for_actor("front")) == 2
        assert len(adapter.calls_for_actor("back")) == 1

    def test_assert_called_passes(self):
        adapter = TestConciergeAdapter()
        _run(adapter.generate(ConciergeModelRequest(actor="front", scenario="test")))
        adapter.assert_called("front", "test")  # should not raise

    def test_assert_called_fails(self):
        adapter = TestConciergeAdapter()
        with pytest.raises(AssertionError, match="Expected call for"):
            adapter.assert_called("front", "never_called")

    def test_assert_not_called_passes(self):
        adapter = TestConciergeAdapter()
        adapter.assert_not_called("front", "test")  # should not raise

    def test_assert_not_called_fails(self):
        adapter = TestConciergeAdapter()
        _run(adapter.generate(ConciergeModelRequest(actor="front", scenario="test")))
        with pytest.raises(AssertionError, match="Expected no calls"):
            adapter.assert_not_called("front", "test")

    def test_assert_tool_called(self):
        adapter = TestConciergeAdapter()
        tools = [ToolSchema(name="acknowledge", description="Ack", parameters={})]
        _run(adapter.generate(ConciergeModelRequest(actor="front", scenario="test", tools=tools)))
        adapter.assert_tool_called("acknowledge")

    def test_assert_tool_called_fails(self):
        adapter = TestConciergeAdapter()
        _run(adapter.generate(ConciergeModelRequest(actor="front", scenario="test")))
        with pytest.raises(AssertionError, match="Tool .* never included"):
            adapter.assert_tool_called("nonexistent_tool")

    def test_reset(self):
        adapter = TestConciergeAdapter()
        adapter.set_response("front", "test", ConciergeModelResponse(text="X"))
        _run(adapter.generate(ConciergeModelRequest(actor="front", scenario="test")))

        assert adapter.call_count == 1
        assert len(adapter.responses) == 1

        adapter.reset()
        assert adapter.call_count == 0
        assert len(adapter.responses) == 0

    def test_records_request_details(self):
        """Verify that recorded calls preserve all request fields."""
        adapter = TestConciergeAdapter()
        tools = [ToolSchema(name="test_tool", description="Test", parameters={})]
        req = ConciergeModelRequest(
            capability=Capability.TOOL_CALL,
            system_prompt="You are a test.",
            messages=[ModelMessage(role="user", content="Hello")],
            tools=tools,
            tool_choice="required",
            max_tokens=512,
            actor="front",
            scenario="validate",
            model_hint="fast",
        )
        _run(adapter.generate(req))

        recorded = adapter.last_call
        assert recorded.capability == Capability.TOOL_CALL
        assert recorded.system_prompt == "You are a test."
        assert recorded.tool_choice == "required"
        assert recorded.max_tokens == 512
        assert recorded.model_hint == "fast"
        assert len(recorded.messages) == 1
        assert len(recorded.tools) == 1


# ===================================================================
# Streaming records calls too
# ===================================================================


class TestStreamRecordsCalls:
    def test_stream_also_records(self):
        adapter = TestConciergeAdapter()
        req = ConciergeModelRequest(actor="front", scenario="stream_test")

        async def consume():
            async for _ in adapter.generate_stream(req):
                pass

        _run(consume())
        assert adapter.call_count == 1
        assert adapter.last_call.scenario == "stream_test"
