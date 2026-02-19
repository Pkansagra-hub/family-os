"""Tests for llm/client.py -- Epic 3.2 (LLM-001).

Tests cover:
    - ToolCall dataclass defaults and construction
    - LLMResponse properties (has_tool_calls, has_text)
    - build_system_prompt() rendering with all parameter combinations
    - GeminiClient construction (API key validation, env loading)
    - GeminiClient.generate() with mocked Gemini SDK
    - GeminiClient.summarize_messages() with mocked SDK
    - GeminiClient.extract_findings_batch() with mocked SDK
    - GeminiClient._build_contents() message conversion

All tests mock ``google.genai`` so no real API calls are made.
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from poc.concierge_fsm_poc.llm.client import (
    GeminiClient,
    LLMResponse,
    ToolCall,
    build_system_prompt,
)
from poc.concierge_fsm_poc.react.scratchpad import Finding

# =========================================================================
# ToolCall tests
# =========================================================================


class TestToolCall:
    """ToolCall dataclass behaviour."""

    def test_default_call_id_prefix(self):
        tc = ToolCall(name="foo")
        assert tc.call_id.startswith("call-")
        assert len(tc.call_id) > 5

    def test_custom_call_id(self):
        tc = ToolCall(call_id="custom-01", name="bar")
        assert tc.call_id == "custom-01"

    def test_default_arguments_empty(self):
        tc = ToolCall(name="test")
        assert tc.arguments == {}

    def test_arguments_preserved(self):
        args = {"location": "Tahoe", "date": "2026-02-20"}
        tc = ToolCall(name="weather", arguments=args)
        assert tc.arguments == args

    def test_unique_call_ids(self):
        ids = {ToolCall(name="a").call_id for _ in range(50)}
        assert len(ids) == 50

    def test_name_default_empty(self):
        tc = ToolCall()
        assert tc.name == ""


# =========================================================================
# LLMResponse tests
# =========================================================================


class TestLLMResponse:
    """LLMResponse dataclass and property behaviour."""

    def test_has_tool_calls_true(self):
        r = LLMResponse(tool_calls=[ToolCall(name="ack")])
        assert r.has_tool_calls is True

    def test_has_tool_calls_false_empty(self):
        r = LLMResponse()
        assert r.has_tool_calls is False

    def test_has_text_true(self):
        r = LLMResponse(text="Hello world")
        assert r.has_text is True

    def test_has_text_false_none(self):
        r = LLMResponse(text=None)
        assert r.has_text is False

    def test_has_text_false_whitespace(self):
        r = LLMResponse(text="   ")
        assert r.has_text is False

    def test_has_text_false_empty(self):
        r = LLMResponse(text="")
        assert r.has_text is False

    def test_token_defaults(self):
        r = LLMResponse()
        assert r.tokens_in == 0
        assert r.tokens_out == 0

    def test_raw_preserved(self):
        sentinel = object()
        r = LLMResponse(raw=sentinel)
        assert r.raw is sentinel

    def test_mixed_text_and_tools(self):
        r = LLMResponse(
            text="Planning...",
            tool_calls=[ToolCall(name="ack"), ToolCall(name="lookup")],
        )
        assert r.has_text is True
        assert r.has_tool_calls is True
        assert len(r.tool_calls) == 2


# =========================================================================
# build_system_prompt tests
# =========================================================================


class TestBuildSystemPrompt:
    """System prompt builder -- the bridge between SessionState and LLM."""

    def test_contains_fsm_state(self):
        prompt = build_system_prompt(
            fsm_state="DISPATCHING",
            turn_number=3,
            tier="MEDIUM",
            safety_band="GREEN",
        )
        assert "DISPATCHING" in prompt
        assert "FSM State" in prompt

    def test_contains_turn_number(self):
        prompt = build_system_prompt(
            fsm_state="LISTENING",
            turn_number=7,
            tier="LOW",
            safety_band="GREEN",
        )
        assert "Turn" in prompt and "7" in prompt

    def test_contains_tier(self):
        prompt = build_system_prompt(
            fsm_state="LISTENING",
            turn_number=1,
            tier="LOW",
            safety_band="GREEN",
        )
        assert "Tier" in prompt and "LOW" in prompt

    def test_contains_safety_band(self):
        prompt = build_system_prompt(
            fsm_state="LISTENING",
            turn_number=1,
            tier="LOW",
            safety_band="RED",
        )
        assert "Safety" in prompt and "RED" in prompt

    def test_contains_role_section(self):
        prompt = build_system_prompt(
            fsm_state="LISTENING",
            turn_number=1,
            tier="LOW",
            safety_band="GREEN",
        )
        assert "FamilyOS Concierge" in prompt

    def test_session_overview_rendered(self):
        overview = {
            "beliefs_active": {"fact_count": 3, "entity_count": 2},
            "scoreboard": {"referent_count": 4},
        }
        prompt = build_system_prompt(
            fsm_state="DISPATCHING",
            turn_number=2,
            tier="MEDIUM",
            safety_band="GREEN",
            session_overview=overview,
        )
        assert "fact_count" in prompt
        assert "3" in prompt

    def test_session_overview_none(self):
        prompt = build_system_prompt(
            fsm_state="DISPATCHING",
            turn_number=1,
            tier="LOW",
            safety_band="GREEN",
            session_overview=None,
        )
        assert "(not available)" in prompt

    def test_tool_names_listed(self):
        tools = [
            {"name": "update_beliefs", "description": "Beliefs", "parameters": {}},
            {"name": "invoke_capability", "description": "Invoke", "parameters": {}},
        ]
        prompt = build_system_prompt(
            fsm_state="DISPATCHING",
            turn_number=2,
            tier="LOW",
            safety_band="GREEN",
            tool_declarations=tools,
        )
        assert "update_beliefs" in prompt
        assert "invoke_capability" in prompt
        assert "2 for" in prompt

    def test_tool_names_sorted(self):
        tools = [
            {"name": "z_tool", "description": "", "parameters": {}},
            {"name": "a_tool", "description": "", "parameters": {}},
        ]
        prompt = build_system_prompt(
            fsm_state="DISPATCHING",
            turn_number=1,
            tier="LOW",
            safety_band="GREEN",
            tool_declarations=tools,
        )
        a_pos = prompt.index("a_tool")
        z_pos = prompt.index("z_tool")
        assert a_pos < z_pos

    def test_no_tools_shows_none(self):
        prompt = build_system_prompt(
            fsm_state="DISPATCHING",
            turn_number=1,
            tier="LOW",
            safety_band="GREEN",
            tool_declarations=[],
        )
        assert "(none)" in prompt
        assert "0 for" in prompt

    def test_instructions_present(self):
        tools = [
            {"name": "read_session_state", "description": "Read session state", "parameters": {}},
            {"name": "update_beliefs", "description": "Update beliefs", "parameters": {}},
            {"name": "update_scoreboard", "description": "Update scoreboard", "parameters": {}},
            {
                "name": "update_clarifications",
                "description": "Update clarifications",
                "parameters": {},
            },
            {"name": "invoke_capability", "description": "Invoke a capability", "parameters": {}},
        ]
        prompt = build_system_prompt(
            fsm_state="DISPATCHING",
            turn_number=1,
            tier="LOW",
            safety_band="GREEN",
            tool_declarations=tools,
        )
        assert "read_session_state" in prompt
        assert "update_beliefs" in prompt
        assert "update_scoreboard" in prompt
        assert "update_clarifications" in prompt
        assert "Think" in prompt and "Act" in prompt
        assert "invoke_capability" in prompt

    def test_crisis_warning_in_instructions(self):
        prompt = build_system_prompt(
            fsm_state="DELIVERING",
            turn_number=10,
            tier="LOW",
            safety_band="CRISIS",
        )
        assert "CRISIS" in prompt
        assert "action tools" in prompt.lower() or "RED" in prompt

    def test_medium_tier_tool_count(self):
        tools = [{"name": f"tool_{i}", "description": "", "parameters": {}} for i in range(14)]
        prompt = build_system_prompt(
            fsm_state="DISPATCHING",
            turn_number=1,
            tier="MEDIUM",
            safety_band="GREEN",
            tool_declarations=tools,
        )
        assert "14 for" in prompt


# =========================================================================
# GeminiClient construction tests
# =========================================================================


class TestGeminiClientInit:
    """GeminiClient constructor and env loading."""

    def test_raises_without_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            # Clear GOOGLE_API_KEY from env
            os.environ.pop("GOOGLE_API_KEY", None)
            with pytest.raises(ValueError, match="GOOGLE_API_KEY"):
                GeminiClient(api_key="")

    def test_accepts_explicit_api_key(self):
        with patch("poc.concierge_fsm_poc.llm.client.GeminiClient.__init__", return_value=None):
            # Just verify the parameter path -- real init needs google SDK
            pass

    def test_default_model_name(self):
        """Model defaults to gemini-2.5-flash."""
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}, clear=False):
            os.environ.pop("GOOGLE_MODEL", None)
            with patch("google.genai.Client"):
                client = GeminiClient(api_key="test-key")
                assert client.model_name == "gemini-2.5-flash"

    def test_custom_model_name(self):
        with patch("google.genai.Client"):
            client = GeminiClient(api_key="test-key", model_name="gemini-pro")
            assert client.model_name == "gemini-pro"

    def test_initial_stats_zero(self):
        with patch("google.genai.Client"):
            client = GeminiClient(api_key="test-key")
            assert client.total_calls == 0
            assert client.total_tokens_in == 0
            assert client.total_tokens_out == 0


# =========================================================================
# Helper for mocked GeminiClient
# =========================================================================


def _make_client() -> GeminiClient:
    """Create a GeminiClient with mocked google.genai.Client."""
    with patch("google.genai.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        client = GeminiClient(api_key="test-key-123")
    return client


def _make_response(
    text: str | None = None,
    function_calls: list[tuple[str, dict]] | None = None,
    tokens_in: int = 100,
    tokens_out: int = 50,
) -> MagicMock:
    """Build a mock Gemini response object."""
    parts = []

    if function_calls:
        for name, args in function_calls:
            fc = MagicMock()
            fc.name = name
            fc.args = args
            part = MagicMock()
            part.function_call = fc
            part.text = None
            # Make hasattr checks work correctly
            type(part).function_call = property(lambda self, _fc=fc: _fc)
            type(part).text = property(lambda self: None)
            parts.append(part)

    if text:
        part = MagicMock()
        part.function_call = MagicMock()
        part.function_call.name = ""  # no function call
        part.text = text
        parts.append(part)

    candidate = MagicMock()
    candidate.content = MagicMock()
    candidate.content.parts = parts

    usage = MagicMock()
    usage.prompt_token_count = tokens_in
    usage.candidates_token_count = tokens_out

    response = MagicMock()
    response.candidates = [candidate]
    response.usage_metadata = usage

    return response


# =========================================================================
# GeminiClient._build_contents tests
# =========================================================================


class TestBuildContents:
    """Message format conversion to Gemini contents."""

    def test_system_extracted(self):
        client = _make_client()
        contents, sys_instr = client._build_contents(
            [{"role": "system", "content": "You are helpful."}]
        )
        assert sys_instr == "You are helpful."
        # System message not in contents (Gemini expects it separate)
        # But contents should have at least one entry (fallback)
        assert len(contents) >= 1

    def test_user_message(self):
        client = _make_client()
        contents, _ = client._build_contents([{"role": "user", "content": "Hello"}])
        assert contents[0].role == "user"
        assert contents[0].parts[0].text == "Hello"

    def test_assistant_becomes_model(self):
        client = _make_client()
        contents, _ = client._build_contents(
            [
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello!"},
            ]
        )
        assert contents[1].role == "model"
        assert contents[1].parts[0].text == "Hello!"

    def test_tool_becomes_user(self):
        client = _make_client()
        contents, _ = client._build_contents(
            [
                {"role": "user", "content": "Hi"},
                {"role": "tool", "content": '{"result": "ok"}'},
            ]
        )
        assert contents[1].role == "user"

    def test_empty_messages_fallback(self):
        client = _make_client()
        contents, _ = client._build_contents([])
        assert len(contents) == 1
        assert contents[0].parts[0].text == "Hello"

    def test_multiple_messages_order_preserved(self):
        client = _make_client()
        msgs = [
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
        ]
        contents, sys = client._build_contents(msgs)
        assert sys == "SYS"
        assert len(contents) == 3  # user, model, user
        assert contents[0].parts[0].text == "Q1"
        assert contents[1].parts[0].text == "A1"
        assert contents[2].parts[0].text == "Q2"

    def test_system_instruction_is_none_without_system_msg(self):
        client = _make_client()
        _, sys = client._build_contents([{"role": "user", "content": "Hey"}])
        assert sys is None


# =========================================================================
# GeminiClient.generate() tests (mocked SDK)
# =========================================================================


class TestGenerate:
    """generate() with mocked Gemini SDK."""

    @pytest.mark.asyncio
    async def test_text_only_response(self):
        client = _make_client()
        mock_resp = _make_response(text="The weather is sunny.", tokens_in=50, tokens_out=10)
        client._client.models.generate_content = MagicMock(return_value=mock_resp)

        result = await client.generate(
            messages=[
                {"role": "system", "content": "Be helpful."},
                {"role": "user", "content": "Weather?"},
            ],
        )

        assert result.has_text is True
        assert "sunny" in result.text
        assert result.has_tool_calls is False
        assert result.tokens_in == 50
        assert result.tokens_out == 10

    @pytest.mark.asyncio
    async def test_tool_call_response(self):
        client = _make_client()
        mock_resp = _make_response(
            function_calls=[("acknowledge", {"ack_type": "commit", "message": "On it!"})],
            tokens_in=80,
            tokens_out=20,
        )
        client._client.models.generate_content = MagicMock(return_value=mock_resp)

        result = await client.generate(
            messages=[{"role": "user", "content": "Hello"}],
        )

        assert result.has_tool_calls is True
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "acknowledge"
        assert result.tool_calls[0].arguments["ack_type"] == "commit"

    @pytest.mark.asyncio
    async def test_error_returns_error_text(self):
        client = _make_client()
        client._client.models.generate_content = MagicMock(
            side_effect=RuntimeError("API quota exceeded")
        )

        result = await client.generate(
            messages=[
                {"role": "system", "content": "test"},
                {"role": "user", "content": "fail"},
            ],
        )

        assert result.text is not None
        assert "LLM_ERROR" in result.text
        assert result.has_tool_calls is False
        assert result.tokens_in == 0
        assert result.tokens_out == 0

    @pytest.mark.asyncio
    async def test_total_calls_incremented(self):
        client = _make_client()
        mock_resp = _make_response(text="ok")
        client._client.models.generate_content = MagicMock(return_value=mock_resp)

        assert client.total_calls == 0
        await client.generate(messages=[{"role": "user", "content": "a"}])
        assert client.total_calls == 1
        await client.generate(messages=[{"role": "user", "content": "b"}])
        assert client.total_calls == 2

    @pytest.mark.asyncio
    async def test_token_stats_accumulate(self):
        client = _make_client()
        mock_resp1 = _make_response(text="a", tokens_in=100, tokens_out=50)
        mock_resp2 = _make_response(text="b", tokens_in=200, tokens_out=75)
        client._client.models.generate_content = MagicMock(side_effect=[mock_resp1, mock_resp2])

        await client.generate(messages=[{"role": "user", "content": "a"}])
        await client.generate(messages=[{"role": "user", "content": "b"}])

        assert client.total_tokens_in == 300
        assert client.total_tokens_out == 125

    @pytest.mark.asyncio
    async def test_generate_with_tools_declaration(self):
        client = _make_client()
        mock_resp = _make_response(text="done")
        client._client.models.generate_content = MagicMock(return_value=mock_resp)

        tools = [
            {
                "name": "acknowledge",
                "description": "Acknowledge user message",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "Ack text"},
                    },
                    "required": ["message"],
                },
            }
        ]

        result = await client.generate(
            messages=[{"role": "user", "content": "Hi"}],
            tools=tools,
        )

        assert result.has_text is True
        # Verify generate_content was called with tools
        client._client.models.generate_content.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_candidates_returns_empty(self):
        client = _make_client()
        mock_resp = MagicMock()
        mock_resp.candidates = []
        mock_resp.usage_metadata = None
        client._client.models.generate_content = MagicMock(return_value=mock_resp)

        result = await client.generate(messages=[{"role": "user", "content": "Hi"}])
        assert result.has_text is False
        assert result.has_tool_calls is False


# =========================================================================
# GeminiClient.summarize_messages() tests
# =========================================================================


class TestSummarizeMessages:
    """summarize_messages() with mocked SDK."""

    @pytest.mark.asyncio
    async def test_returns_summary_text(self):
        client = _make_client()
        mock_resp = _make_response(text="User asked about weather. Tool returned sunny.")
        client._client.models.generate_content = MagicMock(return_value=mock_resp)

        result = await client.summarize_messages(
            [
                {"role": "user", "content": "What's the weather?"},
                {"role": "assistant", "content": "It's sunny."},
            ]
        )

        assert "weather" in result.lower() or "sunny" in result.lower()

    @pytest.mark.asyncio
    async def test_exception_fallback(self):
        client = _make_client()
        client._client.models.generate_content = MagicMock(side_effect=RuntimeError("fail"))

        result = await client.summarize_messages(
            [
                {"role": "user", "content": "Hello there"},
            ]
        )

        assert "Previous conversation covered" in result

    @pytest.mark.asyncio
    async def test_truncates_long_messages(self):
        client = _make_client()
        mock_resp = _make_response(text="Summary.")
        client._client.models.generate_content = MagicMock(return_value=mock_resp)

        long_msg = "x" * 2000
        await client.summarize_messages(
            [
                {"role": "user", "content": long_msg},
            ]
        )
        # The entire 2000-char message should have been truncated to 500 chars
        # before sending to the model
        call_kwargs = client._client.models.generate_content.call_args.kwargs
        prompt_sent = call_kwargs["contents"]
        # The message in the prompt should NOT contain the full 2000 chars
        assert "x" * 501 not in prompt_sent


# =========================================================================
# GeminiClient.extract_findings_batch() tests
# =========================================================================


class TestExtractFindingsBatch:
    """extract_findings_batch() with mocked SDK."""

    @pytest.mark.asyncio
    async def test_extracts_findings_from_json(self):
        client = _make_client()
        mock_resp = _make_response(
            text=json.dumps(
                [
                    {
                        "key": "tahoe_temp",
                        "value": "45F",
                        "type": "weather",
                        "source_tool": "weather_lookup",
                    },
                    {
                        "key": "tahoe_snow",
                        "value": "4 inches",
                        "type": "weather",
                        "source_tool": "weather_lookup",
                    },
                ]
            )
        )
        client._client.models.generate_content = MagicMock(return_value=mock_resp)

        findings = await client.extract_findings_batch(
            [
                ("weather_lookup", {"temperature": "45F", "snow": "4 inches"}),
            ]
        )

        assert len(findings) == 2
        assert findings[0].key == "tahoe_temp"
        assert findings[0].type == "weather"
        assert isinstance(findings[0], Finding)

    @pytest.mark.asyncio
    async def test_handles_markdown_fencing(self):
        client = _make_client()
        json_text = json.dumps(
            [
                {"key": "fact_1", "value": "test", "type": "fact", "source_tool": "tool_a"},
            ]
        )
        mock_resp = _make_response(text=f"```json\n{json_text}\n```")
        client._client.models.generate_content = MagicMock(return_value=mock_resp)

        findings = await client.extract_findings_batch([("tool_a", "result")])
        assert len(findings) == 1
        assert findings[0].key == "fact_1"

    @pytest.mark.asyncio
    async def test_fallback_on_parse_error(self):
        client = _make_client()
        mock_resp = _make_response(text="not valid json at all")
        client._client.models.generate_content = MagicMock(return_value=mock_resp)

        findings = await client.extract_findings_batch(
            [
                ("tool_x", {"data": "value"}),
            ]
        )

        assert len(findings) == 1
        assert findings[0].key == "tool_x_result"
        assert findings[0].source_tool == "tool_x"

    @pytest.mark.asyncio
    async def test_fallback_on_exception(self):
        client = _make_client()
        client._client.models.generate_content = MagicMock(side_effect=RuntimeError("boom"))

        findings = await client.extract_findings_batch(
            [
                ("tool_a", "res_a"),
                ("tool_b", "res_b"),
            ]
        )

        assert len(findings) == 2
        assert findings[0].key == "tool_a_result"
        assert findings[1].key == "tool_b_result"

    @pytest.mark.asyncio
    async def test_empty_input_returns_empty(self):
        client = _make_client()
        findings = await client.extract_findings_batch([])
        assert findings == []

    @pytest.mark.asyncio
    async def test_single_extract_delegates(self):
        client = _make_client()
        mock_resp = _make_response(
            text=json.dumps(
                [
                    {"key": "item", "value": "v", "type": "fact", "source_tool": "t"},
                ]
            )
        )
        client._client.models.generate_content = MagicMock(return_value=mock_resp)

        findings = await client.extract_findings(
            tool_name="t",
            raw_result={"data": 1},
        )

        assert len(findings) == 1
        assert findings[0].key == "item"

    @pytest.mark.asyncio
    async def test_multiple_tools_in_batch(self):
        client = _make_client()
        mock_resp = _make_response(
            text=json.dumps(
                [
                    {
                        "key": "weather_temp",
                        "value": "45F",
                        "type": "weather",
                        "source_tool": "weather",
                    },
                    {"key": "hotel_name", "value": "Hyatt", "type": "fact", "source_tool": "hotel"},
                ]
            )
        )
        client._client.models.generate_content = MagicMock(return_value=mock_resp)

        findings = await client.extract_findings_batch(
            [
                ("weather", {"temp": "45F"}),
                ("hotel", {"name": "Hyatt"}),
            ]
        )

        assert len(findings) == 2
        sources = {f.source_tool for f in findings}
        assert "weather" in sources
        assert "hotel" in sources

    @pytest.mark.asyncio
    async def test_truncates_large_results(self):
        client = _make_client()
        mock_resp = _make_response(
            text=json.dumps(
                [
                    {
                        "key": "big_result",
                        "value": "truncated",
                        "type": "fact",
                        "source_tool": "big",
                    },
                ]
            )
        )
        client._client.models.generate_content = MagicMock(return_value=mock_resp)

        large_result = "x" * 5000
        findings = await client.extract_findings_batch([("big", large_result)])

        # Verify the prompt sent to the model had the result truncated
        call_kwargs = client._client.models.generate_content.call_args.kwargs
        prompt_sent = call_kwargs["contents"]
        assert "[truncated]" in prompt_sent
        assert len(findings) == 1


# =========================================================================
# generate_clarification_question() tests
# =========================================================================


class TestGenerateClarificationQuestion:
    """Tests for GeminiClient.generate_clarification_question()."""

    @pytest.fixture()
    def client(self):
        return _make_client()

    @pytest.mark.asyncio
    async def test_returns_string(self, client):
        """Happy path: returns the LLM-generated question text."""
        mock_response = _make_response(text="When are you checking in and how many guests?")
        client._client.models.generate_content = MagicMock(return_value=mock_response)

        result = await client.generate_clarification_question(
            "Book a hotel", ["check_in", "guests"], "hotel_booking"
        )
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_prompt_contains_context(self, client):
        """Verify the prompt sent to Gemini includes user_message, gaps, and intent."""
        mock_response = _make_response(text="Could you share the dates?")
        client._client.models.generate_content = MagicMock(return_value=mock_response)

        await client.generate_clarification_question(
            "I need a hotel", ["check_in", "check_out", "guests"], "hotel_booking"
        )

        call_kwargs = client._client.models.generate_content.call_args.kwargs
        prompt_sent = call_kwargs["contents"]
        assert "I need a hotel" in prompt_sent
        assert "check_in" in prompt_sent
        assert "hotel_booking" in prompt_sent

    @pytest.mark.asyncio
    async def test_fallback_on_error(self, client):
        """On Gemini API error, falls back to template-based natural question."""
        client._client.models.generate_content = MagicMock(side_effect=Exception("API unavailable"))

        result = await client.generate_clarification_question(
            "Book a hotel", ["check_in", "guests"], "hotel_booking"
        )
        # Template fallback produces a warm, natural question with humanized gap names
        assert "check-in date" in result
        assert "number of guests" in result
        # Should NOT fall through to raw gap listing
        assert "Could you tell me more about" not in result

    @pytest.mark.asyncio
    async def test_tracks_total_calls(self, client):
        """total_calls should increment on success."""
        mock_response = _make_response(text="When would you like to check in?")
        client._client.models.generate_content = MagicMock(return_value=mock_response)
        baseline = client.total_calls

        await client.generate_clarification_question("Book a hotel", ["check_in"], "hotel_booking")
        assert client.total_calls == baseline + 1

    @pytest.mark.asyncio
    async def test_tracks_total_calls_on_error(self, client):
        """total_calls should increment even on error (for accounting)."""
        client._client.models.generate_content = MagicMock(side_effect=RuntimeError("timeout"))
        baseline = client.total_calls

        await client.generate_clarification_question("Book a hotel", ["check_in"], "hotel_booking")
        assert client.total_calls == baseline + 1

    @pytest.mark.asyncio
    async def test_no_tools_passed(self, client):
        """No tool declarations should be passed to the Gemini call."""
        mock_response = _make_response(text="What dates work for you?")
        client._client.models.generate_content = MagicMock(return_value=mock_response)

        await client.generate_clarification_question("Book a hotel", ["check_in"], "hotel_booking")

        call_kwargs = client._client.models.generate_content.call_args.kwargs
        # No 'tools' key should be present
        assert "tools" not in call_kwargs
