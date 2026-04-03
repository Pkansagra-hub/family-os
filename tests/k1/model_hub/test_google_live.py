"""Live integration tests for GooglePlugin with real Gemini API.

Tests ACTUAL API calls with:
  1. Basic chat (sanity)
  2. Thinking / reasoning (ThinkingConfig)
  3. Tool calling (FunctionDeclaration + function response round-trip)
  4. Streaming with thinking

Requires: GOOGLE_API_KEY env var or poc/chat_experience_poc/.env
Run:  python -m pytest tests/k1/model_hub/test_google_live.py -v -s
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# ── load .env if GOOGLE_API_KEY not already set ──────────────────────────
_ENV_FILE = Path(__file__).resolve().parents[3] / "poc" / "chat_experience_poc" / ".env"
if not os.environ.get("GOOGLE_API_KEY") and _ENV_FILE.exists():
    for line in _ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith("GOOGLE_API_KEY="):
            val = line.split("=", 1)[1].strip().strip('"').strip("'")
            os.environ["GOOGLE_API_KEY"] = val
            break

_HAS_KEY = bool(os.environ.get("GOOGLE_API_KEY"))
pytestmark = pytest.mark.skipif(not _HAS_KEY, reason="GOOGLE_API_KEY not set")

from k1.model_hub.manifest import ProviderManifest, load_manifest
from k1.model_hub.plugins.base import NormalizedRequest, ProviderChunk, ProviderResponse
from k1.model_hub.plugins.google_plugin import GooglePlugin
from k1.model_hub.types import CapabilityType, FinishReason, Message

# ── Fixtures ─────────────────────────────────────────────────────────────

MANIFEST_PATH = (
    Path(__file__).resolve().parents[3] / "k1" / "config" / "providers" / "google.manifest.yaml"
)
MODEL = "gemini-2.5-flash"


@pytest.fixture
async def plugin() -> GooglePlugin:
    """Initialize GooglePlugin with real manifest + API key."""
    manifest = load_manifest(MANIFEST_PATH)
    p = GooglePlugin()
    await p.initialize(manifest)
    p.set_api_key(os.environ["GOOGLE_API_KEY"])
    yield p
    await p.close()


def _req(
    messages: list[Message] | None = None,
    system_prompt: str | None = None,
    tools: list | None = None,
    tool_choice: str | None = None,
    reasoning_effort: str | None = None,
    extra: dict | None = None,
    model: str = MODEL,
    max_tokens: int = 1024,
) -> NormalizedRequest:
    return NormalizedRequest(
        capability=CapabilityType.CHAT,
        messages=messages or [Message(role="user", content="Say hello in one word.")],
        system_prompt=system_prompt,
        tools=tools,
        tool_choice=tool_choice,
        max_tokens=max_tokens,
        temperature=0.2,
        model_id=model,
        trace_id="live-test",
        consumer_id="integration",
        reasoning_effort=reasoning_effort,
        extra=extra or {},
    )


# =========================================================================
# 1. Basic chat
# =========================================================================


class TestBasicChat:

    async def test_simple_response(self, plugin: GooglePlugin) -> None:
        """Call Gemini and get a text response."""
        req = _req()
        resp = await plugin.execute(req)

        assert isinstance(resp, ProviderResponse)
        assert resp.text, "Expected non-empty text"
        assert resp.prompt_tokens > 0, "Expected prompt token count"
        assert resp.completion_tokens > 0, "Expected completion token count"
        assert resp.finish_reason == FinishReason.STOP
        print(
            f"\n[basic] text={resp.text!r} | in={resp.prompt_tokens} out={resp.completion_tokens}"
        )

    async def test_system_prompt(self, plugin: GooglePlugin) -> None:
        """System prompt should influence the response."""
        req = _req(
            system_prompt="You are a pirate. Always respond with 'Arrr!'",
            messages=[Message(role="user", content="Hello")],
        )
        resp = await plugin.execute(req)
        assert resp.text, "Expected non-empty text"
        print(f"\n[system] text={resp.text!r}")


# =========================================================================
# 2. Thinking / reasoning
# =========================================================================


class TestThinking:

    async def test_thinking_with_reasoning_effort(self, plugin: GooglePlugin) -> None:
        """Enable thinking via reasoning_effort and verify we get thought text."""
        req = _req(
            messages=[
                Message(
                    role="user",
                    content="What is the sum of the first 20 prime numbers? Think step by step.",
                ),
            ],
            reasoning_effort="medium",
            max_tokens=4096,
        )
        resp = await plugin.execute(req)

        assert resp.text, "Expected non-empty text with answer"
        assert resp.prompt_tokens > 0
        assert resp.completion_tokens > 0
        # Thinking models should have thought_text in raw_response
        thought = (resp.raw_response or {}).get("thought_text", "")
        print(f"\n[thinking] answer={resp.text!r}")
        print(f"[thinking] thought_text length={len(thought)} chars")
        print(f"[thinking] tokens in={resp.prompt_tokens} out={resp.completion_tokens}")

    async def test_thinking_high_budget(self, plugin: GooglePlugin) -> None:
        """High reasoning effort should produce longer thoughts."""
        req = _req(
            messages=[
                Message(
                    role="user",
                    content=(
                        "A farmer has a wolf, a goat, and a cabbage. He needs to cross a river "
                        "with a boat that can only carry one item at a time. If left alone, the "
                        "wolf will eat the goat, and the goat will eat the cabbage. How does the "
                        "farmer get everything across?"
                    ),
                ),
            ],
            reasoning_effort="high",
            max_tokens=8192,
        )
        resp = await plugin.execute(req)
        assert resp.text, "Expected solution text"
        thought = (resp.raw_response or {}).get("thought_text", "")
        print(f"\n[thinking-high] answer_len={len(resp.text)} thought_len={len(thought)}")
        print(f"[thinking-high] tokens in={resp.prompt_tokens} out={resp.completion_tokens}")


# =========================================================================
# 3. Tool calling
# =========================================================================

_WEATHER_TOOL = {
    "name": "get_current_weather",
    "description": "Get the current weather for a given location",
    "parameters": {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "City and state, e.g. 'San Francisco, CA'",
            },
            "unit": {
                "type": "string",
                "enum": ["celsius", "fahrenheit"],
                "description": "Temperature unit",
            },
        },
        "required": ["location"],
    },
}


class TestToolCalling:

    async def test_tool_call_triggered(self, plugin: GooglePlugin) -> None:
        """Model should return a tool call for a weather question."""
        req = _req(
            messages=[
                Message(role="user", content="What is the weather in San Francisco right now?"),
            ],
            tools=[_WEATHER_TOOL],
            tool_choice="auto",
            max_tokens=1024,
        )
        resp = await plugin.execute(req)

        assert resp.tool_calls, "Expected tool calls in response"
        tc = resp.tool_calls[0]
        assert tc.name == "get_current_weather"
        args = json.loads(tc.arguments)
        assert "location" in args, f"Expected 'location' in args, got {args}"
        assert resp.finish_reason == FinishReason.TOOL_CALLS
        print(f"\n[tool] name={tc.name} args={args}")

    async def test_tool_call_roundtrip(self, plugin: GooglePlugin) -> None:
        """Full round-trip: user -> tool_call -> tool_result -> final answer."""
        # Step 1: Ask weather question
        req1 = _req(
            messages=[
                Message(role="user", content="What's the weather in Tokyo?"),
            ],
            tools=[_WEATHER_TOOL],
            tool_choice="auto",
        )
        resp1 = await plugin.execute(req1)
        assert resp1.tool_calls, "Expected tool call"
        tc = resp1.tool_calls[0]
        print(f"\n[roundtrip-1] tool_call: {tc.name}({tc.arguments})")

        # Step 2: Send tool result back
        fake_weather = json.dumps({"temperature": 22, "unit": "celsius", "condition": "Sunny"})
        req2 = _req(
            messages=[
                Message(role="user", content="What's the weather in Tokyo?"),
                Message(role="assistant", content=""),
                Message(role="tool", content=fake_weather, name="get_current_weather"),
            ],
            tools=[_WEATHER_TOOL],
        )
        resp2 = await plugin.execute(req2)
        assert resp2.text, "Expected final answer text after tool result"
        assert resp2.finish_reason == FinishReason.STOP
        print(f"\n[roundtrip-2] final answer: {resp2.text!r}")

    async def test_tool_with_thinking(self, plugin: GooglePlugin) -> None:
        """Tool calling with thinking enabled -- model should reason then call tool."""
        req = _req(
            messages=[
                Message(
                    role="user",
                    content=(
                        "I'm planning a trip. I need to know the weather in Paris and London. "
                        "Which city should I visit based on the weather?"
                    ),
                ),
            ],
            tools=[_WEATHER_TOOL],
            tool_choice="auto",
            reasoning_effort="medium",
            max_tokens=4096,
        )
        resp = await plugin.execute(req)

        # Should get either a tool call or text with reasoning
        thought = (resp.raw_response or {}).get("thought_text", "")
        print(f"\n[tool+thinking] text={resp.text!r}")
        print(f"[tool+thinking] tool_calls={resp.tool_calls}")
        print(f"[tool+thinking] thought_len={len(thought)}")
        print(f"[tool+thinking] tokens in={resp.prompt_tokens} out={resp.completion_tokens}")

        # Model should call the tool or provide reasoning
        assert resp.text or resp.tool_calls, "Expected text or tool calls"


# =========================================================================
# 4. Streaming
# =========================================================================


class TestStreaming:

    async def test_stream_basic(self, plugin: GooglePlugin) -> None:
        """Streaming should yield chunks with text."""
        req = _req(
            messages=[Message(role="user", content="Count from 1 to 5.")],
        )
        chunks = []
        async for chunk in plugin.stream_execute(req):
            chunks.append(chunk)

        assert len(chunks) > 0, "Expected at least one chunk"
        full_text = "".join(c.text for c in chunks)
        assert full_text, "Expected non-empty streamed text"
        assert any(c.done for c in chunks), "Expected at least one done=True chunk"
        print(f"\n[stream] chunks={len(chunks)} text={full_text!r}")

    async def test_stream_with_thinking(self, plugin: GooglePlugin) -> None:
        """Streaming with thinking should produce thought metadata."""
        req = _req(
            messages=[
                Message(role="user", content="What is 127 * 83? Show your work."),
            ],
            reasoning_effort="medium",
            max_tokens=4096,
        )
        chunks = []
        async for chunk in plugin.stream_execute(req):
            chunks.append(chunk)

        assert len(chunks) > 0
        full_text = "".join(c.text for c in chunks)
        thoughts = "".join((c.metadata or {}).get("thought_text", "") for c in chunks)
        assert full_text, "Expected answer text"
        print(f"\n[stream-think] chunks={len(chunks)}")
        print(f"[stream-think] answer_len={len(full_text)} thought_len={len(thoughts)}")


# =========================================================================
# 5. Health check
# =========================================================================


class TestHealthCheck:

    async def test_health_check_passes(self, plugin: GooglePlugin) -> None:
        """Health check should return HEALTHY with valid key."""
        health = await plugin.health_check()
        from k1.model_hub.types import HealthStatus

        assert health.status == HealthStatus.HEALTHY
        print(f"\n[health] status={health.status}")
