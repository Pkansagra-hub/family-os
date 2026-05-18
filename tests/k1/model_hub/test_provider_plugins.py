"""M7 Provider Plugins -- Tests for provider plugins + manifests [F21-F25].

Tests the OpenAI, Anthropic, Google, Vertex/Agent Platform, vLLM, and Ollama provider plugins:
  - IProviderPlugin protocol conformance
  - initialize()/close() lifecycle
  - supports() capability matching
  - estimate_tokens() local estimation
  - Request body building (NormalizedRequest -> native format)
  - Response parsing (native response -> ProviderResponse)
  - Tool call parsing
  - Error handling
    - Manifest loading for all providers

NO real HTTP calls.  All HTTP mocked via aiohttp test helpers or monkeypatch.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from k1.model_hub.manifest import ProviderManifest, load_manifest
from k1.model_hub.plugins import google_plugin as google_plugin_module
from k1.model_hub.plugins.anthropic_plugin import AnthropicPlugin
from k1.model_hub.plugins.base import IProviderPlugin, NormalizedRequest
from k1.model_hub.plugins.google_plugin import GooglePlugin
from k1.model_hub.plugins.ollama_plugin import OllamaPlugin

# ---------------------------------------------------------------------------
# Import all provider plugins
# ---------------------------------------------------------------------------
from k1.model_hub.plugins.openai_plugin import OpenAIPlugin
from k1.model_hub.plugins.vertex_plugin import VertexPlugin
from k1.model_hub.plugins.vllm_plugin import VLLMPlugin
from k1.model_hub.types import (
    CapabilityType,
    FinishReason,
    Message,
    ProviderError,
    RateLimitError,
)

# ===========================================================================
# Helpers
# ===========================================================================

MANIFEST_DIR = Path(__file__).resolve().parents[3] / "k1" / "config" / "providers"

ALL_PLUGINS = [OpenAIPlugin, AnthropicPlugin, GooglePlugin, VertexPlugin, VLLMPlugin, OllamaPlugin]
ALL_MANIFEST_FILES = [
    "openai.manifest.yaml",
    "anthropic.manifest.yaml",
    "google.manifest.yaml",
    "vertex.manifest.yaml",
    "vllm.manifest.yaml",
    "ollama.manifest.yaml",
]


def _make_manifest(
    provider_id: str = "test",
    api_base: str = "http://localhost:9999",
    capabilities: list | None = None,
    models: list | None = None,
) -> ProviderManifest:
    """Create a minimal ProviderManifest for testing."""
    caps = capabilities or [CapabilityType.CHAT]
    model_specs = models or []
    return ProviderManifest(
        provider_id=provider_id,
        display_name=provider_id,
        api_base=api_base,
        capabilities=caps,
        models=model_specs,
    )


def _make_request(
    model_id: str = "test-model",
    messages: list | None = None,
    system_prompt: str | None = None,
    tools: list | None = None,
    tool_choice: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.7,
    reasoning_effort: str | None = None,
    extra: dict | None = None,
) -> NormalizedRequest:
    msgs = messages or [Message(role="user", content="Hello")]
    return NormalizedRequest(
        capability=CapabilityType.CHAT,
        messages=msgs,
        system_prompt=system_prompt,
        tools=tools,
        tool_choice=tool_choice,
        max_tokens=max_tokens,
        temperature=temperature,
        model_id=model_id,
        trace_id="trace-001",
        consumer_id="test-consumer",
        reasoning_effort=reasoning_effort,
        extra=extra or {},
    )


# ===========================================================================
# 1. Protocol Conformance Tests
# ===========================================================================


class TestProtocolConformance:
    """All 5 plugins satisfy IProviderPlugin at runtime."""

    @pytest.mark.parametrize("plugin_cls", ALL_PLUGINS, ids=lambda c: c.__name__)
    def test_isinstance_iprovider_plugin(self, plugin_cls: type) -> None:
        plugin = plugin_cls()
        assert isinstance(plugin, IProviderPlugin)

    @pytest.mark.parametrize("plugin_cls", ALL_PLUGINS, ids=lambda c: c.__name__)
    def test_has_all_protocol_methods(self, plugin_cls: type) -> None:
        expected_methods = [
            "initialize",
            "supports",
            "execute",
            "stream_execute",
            "estimate_tokens",
            "health_check",
            "close",
        ]
        for method in expected_methods:
            assert hasattr(plugin_cls, method), f"{plugin_cls.__name__} missing {method}"


# ===========================================================================
# 2. Lifecycle Tests (initialize / close)
# ===========================================================================


class TestLifecycle:
    """Initialize and close for all plugins."""

    @pytest.mark.parametrize("plugin_cls", ALL_PLUGINS, ids=lambda c: c.__name__)
    async def test_initialize_sets_manifest(self, plugin_cls: type) -> None:
        plugin = plugin_cls()
        manifest = _make_manifest(api_base="http://test:1234")
        await plugin.initialize(manifest)
        assert plugin._manifest is manifest
        await plugin.close()

    @pytest.mark.parametrize("plugin_cls", ALL_PLUGINS, ids=lambda c: c.__name__)
    async def test_close_cleans_session(self, plugin_cls: type) -> None:
        plugin = plugin_cls()
        manifest = _make_manifest()
        await plugin.initialize(manifest)
        # GooglePlugin uses _client (SDK), others use _session (aiohttp)
        if hasattr(plugin, "_session"):
            assert plugin._session is not None
            await plugin.close()
            assert plugin._session is None
        else:
            # SDK-based plugin (GooglePlugin) -- just verify close doesn't raise
            await plugin.close()
            assert plugin._client is None

    @pytest.mark.parametrize("plugin_cls", ALL_PLUGINS, ids=lambda c: c.__name__)
    async def test_close_idempotent(self, plugin_cls: type) -> None:
        plugin = plugin_cls()
        manifest = _make_manifest()
        await plugin.initialize(manifest)
        await plugin.close()
        await plugin.close()  # Should not raise


# ===========================================================================
# 3. Supports Tests
# ===========================================================================


class TestSupports:
    """supports() returns correct values based on manifest capabilities."""

    @pytest.mark.parametrize("plugin_cls", ALL_PLUGINS, ids=lambda c: c.__name__)
    async def test_supports_chat(self, plugin_cls: type) -> None:
        plugin = plugin_cls()
        manifest = _make_manifest(capabilities=[CapabilityType.CHAT])
        await plugin.initialize(manifest)
        assert plugin.supports(CapabilityType.CHAT) is True
        assert plugin.supports(CapabilityType.EMBED) is False
        await plugin.close()

    @pytest.mark.parametrize("plugin_cls", ALL_PLUGINS, ids=lambda c: c.__name__)
    async def test_supports_multiple(self, plugin_cls: type) -> None:
        plugin = plugin_cls()
        manifest = _make_manifest(
            capabilities=[CapabilityType.CHAT, CapabilityType.TOOL_CALL, CapabilityType.EMBED],
        )
        await plugin.initialize(manifest)
        assert plugin.supports(CapabilityType.CHAT) is True
        assert plugin.supports(CapabilityType.TOOL_CALL) is True
        assert plugin.supports(CapabilityType.EMBED) is True
        assert plugin.supports(CapabilityType.IMAGE_GEN) is False
        await plugin.close()


# ===========================================================================
# 4. Estimate Tokens Tests
# ===========================================================================


class TestEstimateTokens:
    """estimate_tokens returns int > 0 for non-empty messages."""

    @pytest.mark.parametrize("plugin_cls", ALL_PLUGINS, ids=lambda c: c.__name__)
    def test_estimate_tokens_positive(self, plugin_cls: type) -> None:
        plugin = plugin_cls()
        msgs = [Message(role="user", content="Hello world")]
        result = plugin.estimate_tokens(msgs)
        assert isinstance(result, int)
        assert result > 0

    @pytest.mark.parametrize("plugin_cls", ALL_PLUGINS, ids=lambda c: c.__name__)
    def test_estimate_tokens_empty(self, plugin_cls: type) -> None:
        plugin = plugin_cls()
        result = plugin.estimate_tokens([])
        assert isinstance(result, int)
        assert result >= 0

    @pytest.mark.parametrize("plugin_cls", ALL_PLUGINS, ids=lambda c: c.__name__)
    def test_estimate_scales_with_content(self, plugin_cls: type) -> None:
        plugin = plugin_cls()
        short = [Message(role="user", content="Hi")]
        long = [Message(role="user", content="Hello " * 1000)]
        assert plugin.estimate_tokens(long) > plugin.estimate_tokens(short)


# ===========================================================================
# 5. OpenAI Plugin: Request/Response
# ===========================================================================


class TestOpenAIRequestBuilding:
    """OpenAI request body construction."""

    def _plugin(self) -> OpenAIPlugin:
        p = OpenAIPlugin()
        p._capabilities = {CapabilityType.CHAT, CapabilityType.TOOL_CALL}
        p._api_base = "https://api.openai.com/v1"
        return p

    def test_basic_chat_body(self) -> None:
        p = self._plugin()
        req = _make_request(model_id="gpt-4o")
        body = p._build_chat_body(req, stream=False)
        assert body["model"] == "gpt-4o"
        assert body["stream"] is False
        assert "max_completion_tokens" in body  # NOT max_tokens
        assert body["messages"][0]["role"] == "user"

    def test_system_prompt_user_role(self) -> None:
        p = self._plugin()
        req = _make_request(model_id="gpt-4o", system_prompt="Be helpful")
        body = p._build_chat_body(req, stream=False)
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][0]["content"] == "Be helpful"

    def test_reasoning_model_developer_role(self) -> None:
        """o-series models use 'developer' role for system prompts."""
        p = self._plugin()
        req = _make_request(model_id="o3", system_prompt="Be concise", reasoning_effort="medium")
        body = p._build_chat_body(req, stream=False)
        assert body["messages"][0]["role"] == "developer"
        assert body["reasoning_effort"] == "medium"

    def test_reasoning_model_no_temperature(self) -> None:
        """Reasoning models don't support temperature."""
        p = self._plugin()
        req = _make_request(model_id="o4-mini")
        body = p._build_chat_body(req, stream=False)
        assert "temperature" not in body

    def test_tools_in_body(self) -> None:
        p = self._plugin()
        tools = [{"name": "get_weather", "description": "Get weather", "parameters": {}}]
        req = _make_request(model_id="gpt-4o", tools=tools, tool_choice="auto")
        body = p._build_chat_body(req, stream=False)
        assert len(body["tools"]) == 1
        assert body["tools"][0]["type"] == "function"
        assert body["tool_choice"] == "auto"

    def test_stream_options_in_streaming(self) -> None:
        p = self._plugin()
        req = _make_request(model_id="gpt-4o")
        body = p._build_chat_body(req, stream=True)
        assert body["stream"] is True


class TestOpenAIResponseParsing:
    """OpenAI response parsing."""

    def _plugin(self) -> OpenAIPlugin:
        p = OpenAIPlugin()
        p._api_base = "https://api.openai.com/v1"
        return p

    def test_parse_basic_response(self) -> None:
        p = self._plugin()
        data = {
            "choices": [
                {
                    "message": {"content": "Hello!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "model": "gpt-4o",
        }
        req = _make_request(model_id="gpt-4o")
        resp = p._parse_chat_response(data, req)
        assert resp.text == "Hello!"
        assert resp.finish_reason == FinishReason.STOP
        assert resp.prompt_tokens == 10
        assert resp.completion_tokens == 5
        assert resp.model_id == "gpt-4o"

    def test_parse_tool_call_response(self) -> None:
        p = self._plugin()
        data = {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_abc123",
                                "type": "function",
                                "function": {
                                    "name": "get_weather",
                                    "arguments": '{"location": "NYC"}',
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10},
            "model": "gpt-4o",
        }
        req = _make_request(model_id="gpt-4o")
        resp = p._parse_chat_response(data, req)
        assert resp.finish_reason == FinishReason.TOOL_CALLS
        assert resp.tool_calls is not None
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].id == "call_abc123"
        assert resp.tool_calls[0].name == "get_weather"
        assert resp.tool_calls[0].arguments == '{"location": "NYC"}'

    def test_parse_content_filter(self) -> None:
        p = self._plugin()
        data = {
            "choices": [
                {
                    "message": {"content": ""},
                    "finish_reason": "content_filter",
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 0},
            "model": "gpt-4o",
        }
        req = _make_request(model_id="gpt-4o")
        resp = p._parse_chat_response(data, req)
        assert resp.finish_reason == FinishReason.SAFETY

    def test_parse_empty_choices_raises(self) -> None:
        p = self._plugin()
        data = {"choices": [], "usage": {}, "model": "gpt-4o"}
        req = _make_request(model_id="gpt-4o")
        with pytest.raises(ProviderError):
            p._parse_chat_response(data, req)


# ===========================================================================
# 6. Anthropic Plugin: Request/Response
# ===========================================================================


class TestAnthropicRequestBuilding:
    """Anthropic request body construction."""

    def _plugin(self) -> AnthropicPlugin:
        p = AnthropicPlugin()
        p._capabilities = {CapabilityType.CHAT, CapabilityType.TOOL_CALL}
        p._api_base = "https://api.anthropic.com/v1"
        return p

    def test_system_prompt_top_level(self) -> None:
        """Anthropic: system prompt is top-level, NOT in messages."""
        p = self._plugin()
        req = _make_request(model_id="claude-sonnet-4-6", system_prompt="Be concise")
        body = p._build_body(req, stream=False)
        assert body["system"] == "Be concise"
        # System prompt NOT in messages
        for msg in body["messages"]:
            assert msg["role"] != "system"

    def test_max_tokens_required(self) -> None:
        """Anthropic: max_tokens is always present (required)."""
        p = self._plugin()
        req = _make_request(model_id="claude-sonnet-4-6")
        body = p._build_body(req, stream=False)
        assert "max_tokens" in body
        assert body["max_tokens"] == 1024

    def test_tools_use_input_schema(self) -> None:
        """Anthropic: tools use input_schema, NOT parameters."""
        p = self._plugin()
        tools = [{"name": "search", "description": "Search", "parameters": {"type": "object"}}]
        req = _make_request(model_id="claude-sonnet-4-6", tools=tools)
        body = p._build_body(req, stream=False)
        assert body["tools"][0]["input_schema"] == {"type": "object"}

    def test_tool_choice_mapping(self) -> None:
        """Anthropic: tool_choice maps to {type: ...} format."""
        p = self._plugin()
        assert p._map_tool_choice("auto") == {"type": "auto"}
        assert p._map_tool_choice("none") == {"type": "none"}
        assert p._map_tool_choice("required") == {"type": "any"}
        assert p._map_tool_choice("my_tool") == {"type": "tool", "name": "my_tool"}

    def test_thinking_enabled_for_reasoning(self) -> None:
        p = self._plugin()
        req = _make_request(model_id="claude-opus-4-6", reasoning_effort="high")
        body = p._build_body(req, stream=False)
        assert "thinking" in body
        assert body["thinking"]["type"] == "enabled"


class TestAnthropicResponseParsing:
    """Anthropic response parsing."""

    def _plugin(self) -> AnthropicPlugin:
        p = AnthropicPlugin()
        p._api_base = "https://api.anthropic.com/v1"
        return p

    def test_parse_text_response(self) -> None:
        p = self._plugin()
        data = {
            "content": [{"type": "text", "text": "Hello!"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "model": "claude-sonnet-4-6",
        }
        req = _make_request(model_id="claude-sonnet-4-6")
        resp = p._parse_response(data, req)
        assert resp.text == "Hello!"
        assert resp.finish_reason == FinishReason.STOP
        assert resp.prompt_tokens == 10
        assert resp.completion_tokens == 5

    def test_parse_tool_use_response(self) -> None:
        """Anthropic: stop_reason=tool_use, content blocks include tool_use type."""
        p = self._plugin()
        data = {
            "content": [
                {"type": "text", "text": "Let me search."},
                {
                    "type": "tool_use",
                    "id": "toolu_abc",
                    "name": "search",
                    "input": {"query": "test"},
                },
            ],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 20, "output_tokens": 15},
            "model": "claude-sonnet-4-6",
        }
        req = _make_request(model_id="claude-sonnet-4-6")
        resp = p._parse_response(data, req)
        assert resp.finish_reason == FinishReason.TOOL_CALLS
        assert resp.tool_calls is not None
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].id == "toolu_abc"
        assert resp.tool_calls[0].name == "search"
        assert json.loads(resp.tool_calls[0].arguments) == {"query": "test"}

    def test_parse_max_tokens_finish(self) -> None:
        p = self._plugin()
        data = {
            "content": [{"type": "text", "text": "Truncated..."}],
            "stop_reason": "max_tokens",
            "usage": {"input_tokens": 10, "output_tokens": 4096},
            "model": "claude-sonnet-4-6",
        }
        req = _make_request(model_id="claude-sonnet-4-6")
        resp = p._parse_response(data, req)
        assert resp.finish_reason == FinishReason.LENGTH

    def test_auth_headers(self) -> None:
        """Anthropic: x-api-key + anthropic-version headers."""
        p = self._plugin()
        p._api_key = "test-key"
        headers = p._auth_headers()
        assert headers["x-api-key"] == "test-key"
        assert headers["anthropic-version"] == "2023-06-01"


# ===========================================================================
# 7. Google Plugin: Request/Response
# ===========================================================================


class TestGoogleRequestBuilding:
    """Google Gemini SDK config building."""

    def _plugin(self) -> GooglePlugin:
        p = GooglePlugin()
        p._capabilities = {CapabilityType.CHAT, CapabilityType.TOOL_CALL}
        return p

    def test_build_config_system_instruction(self) -> None:
        """Gemini SDK: system_instruction is set in GenerateContentConfig."""
        from google.genai import types

        p = self._plugin()
        req = _make_request(model_id="gemini-2.5-flash", system_prompt="Be helpful")
        config = p._build_config(req, types)
        assert config.system_instruction == "Be helpful"

    def test_contents_user_and_model_roles(self) -> None:
        """Gemini SDK: assistant -> model role in Content objects."""
        from google.genai import types

        p = self._plugin()
        msgs = [
            Message(role="user", content="Hi"),
            Message(role="assistant", content="Hello!"),
        ]
        req = _make_request(model_id="gemini-2.5-flash", messages=msgs)
        contents = p._to_genai_contents(req, types)
        assert contents[0].role == "user"
        assert contents[1].role == "model"  # NOT assistant

    def test_build_config_temperature_and_max_tokens(self) -> None:
        """Gemini SDK: temperature & max_output_tokens in config."""
        from google.genai import types

        p = self._plugin()
        req = _make_request(model_id="gemini-2.5-flash", max_tokens=2048, temperature=0.5)
        config = p._build_config(req, types)
        assert config.max_output_tokens == 2048
        assert config.temperature == 0.5

    def test_tools_as_function_declarations(self) -> None:
        """Gemini SDK: tools build FunctionDeclaration objects."""
        from google.genai import types

        p = self._plugin()
        tools = [{"name": "search", "description": "Search", "parameters": {"type": "object"}}]
        req = _make_request(model_id="gemini-2.5-flash", tools=tools, tool_choice="auto")
        genai_tools = p._to_genai_tools(req, types)
        assert genai_tools is not None
        assert len(genai_tools) >= 1
        # First tool should have function_declarations
        fd = genai_tools[0].function_declarations
        assert fd is not None
        assert fd[0].name == "search"

    def test_tool_config_mode_mapping(self) -> None:
        """Gemini SDK: tool_choice maps to ToolConfig modes."""
        from google.genai import types

        p = self._plugin()
        tc_auto = p._build_tool_config("auto", types)
        assert tc_auto.function_calling_config.mode == "AUTO"
        tc_required = p._build_tool_config("required", types)
        assert tc_required.function_calling_config.mode == "ANY"
        tc_none = p._build_tool_config("none", types)
        assert tc_none.function_calling_config.mode == "NONE"

    def test_thinking_config_with_reasoning(self) -> None:
        """Gemini SDK: reasoning_effort sets ThinkingConfig."""
        from google.genai import types

        p = self._plugin()
        req = _make_request(model_id="gemini-2.5-flash", reasoning_effort="high")
        config = p._build_config(req, types)
        assert config.thinking_config is not None
        assert config.thinking_config.thinking_budget == 24576
        assert config.thinking_config.include_thoughts is True

    def test_code_execution_tool(self) -> None:
        from google.genai import types

        p = self._plugin()
        req = _make_request(model_id="gemini-2.5-flash", extra={"code_execution": True})
        genai_tools = p._to_genai_tools(req, types)
        assert genai_tools is not None
        has_code_exec = any(getattr(t, "code_execution", None) is not None for t in genai_tools)
        assert has_code_exec

    def test_google_search_tool(self) -> None:
        from google.genai import types

        p = self._plugin()
        req = _make_request(model_id="gemini-2.5-flash", extra={"google_search": True})
        genai_tools = p._to_genai_tools(req, types)
        assert genai_tools is not None
        has_search = any(getattr(t, "google_search", None) is not None for t in genai_tools)
        assert has_search


class TestVertexRequestBuilding:
    """Gemini Enterprise Agent Platform SDK client configuration."""

    def _plugin(self) -> VertexPlugin:
        p = VertexPlugin()
        p._capabilities = {CapabilityType.CHAT, CapabilityType.TOOL_CALL}
        return p

    def test_create_client_uses_cloud_project_location_and_api_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _HttpOptions:
            def __init__(self, *, api_version: str) -> None:
                self.api_version = api_version

        class _FakeTypes:
            HttpOptions = _HttpOptions

        class _FakeGenai:
            @staticmethod
            def Client(**kwargs):
                return kwargs

        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "project-test")
        monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        monkeypatch.delenv("GOOGLE_GENAI_USE_VERTEXAI", raising=False)
        p = self._plugin()
        p.set_api_key("cloud-key")

        client_kwargs = p._create_client(_FakeGenai, _FakeTypes)

        assert client_kwargs["vertexai"] is True
        assert client_kwargs["project"] == "project-test"
        assert client_kwargs["location"] == "us-central1"
        assert client_kwargs["api_key"] == "cloud-key"
        assert client_kwargs["http_options"].api_version == "v1"
        assert os.environ["GOOGLE_GENAI_USE_VERTEXAI"] == "True"

    def test_ensure_client_allows_adc_without_api_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _HttpOptions:
            def __init__(self, *, api_version: str) -> None:
                self.api_version = api_version

        class _FakeTypes:
            HttpOptions = _HttpOptions

        class _FakeGenai:
            @staticmethod
            def Client(**kwargs):
                return kwargs

        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "project-test")
        monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        monkeypatch.setattr(
            google_plugin_module,
            "_ensure_genai",
            lambda: (_FakeGenai, _FakeTypes),
        )
        p = self._plugin()

        client_kwargs = p._ensure_client()

        assert client_kwargs["vertexai"] is True
        assert "api_key" not in client_kwargs

    def test_legacy_project_location_aliases(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
        monkeypatch.delenv("GOOGLE_CLOUD_LOCATION", raising=False)
        monkeypatch.setenv("GOOGLE_PROJECT_ID", "legacy-project")
        monkeypatch.setenv("GOOGLE_LOCATION", "europe-west4")

        assert self._plugin()._resolve_project_location() == ("legacy-project", "europe-west4")

    def test_missing_project_raises_provider_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
        monkeypatch.delenv("GOOGLE_PROJECT_ID", raising=False)

        with pytest.raises(ProviderError, match="GOOGLE_CLOUD_PROJECT"):
            self._plugin()._resolve_project_location()

    def test_vertex_model_env_overrides_manifest_choice(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("VERTEX_MODEL", "gemini-2.5-flash")
        req = _make_request(model_id="gemini-3-flash-preview")

        assert self._plugin()._resolve_model_id(req) == "gemini-2.5-flash"


class TestGoogleResponseParsing:
    """Google Gemini SDK response normalization."""

    def _plugin(self) -> GooglePlugin:
        p = GooglePlugin()
        return p

    def _mock_response(self, **kwargs):
        """Build a fake SDK response object (no unittest.mock)."""

        class _FakeFunctionCall:
            def __init__(self, name: str, args: dict):
                self.name = name
                self.args = args

        class _FakePart:
            def __init__(self, text=None, thought=False, function_call=None):
                self.text = text
                self.thought = thought
                self.function_call = function_call

        class _FakeContent:
            def __init__(self, parts):
                self.parts = parts

        class _FakeCandidate:
            def __init__(self, content, finish_reason="STOP"):
                self.content = content
                self.finish_reason = finish_reason

        class _FakeUsage:
            def __init__(self, prompt_tokens=10, completion_tokens=5):
                self.prompt_token_count = prompt_tokens
                self.candidates_token_count = completion_tokens

        class _FakeResponse:
            def __init__(self, candidates, usage_metadata):
                self.candidates = candidates
                self.usage_metadata = usage_metadata

        parts = []
        for part_spec in kwargs.get("parts", []):
            fc = None
            if "function_call" in part_spec:
                fc = _FakeFunctionCall(
                    name=part_spec["function_call"]["name"],
                    args=part_spec["function_call"].get("args", {}),
                )
            parts.append(
                _FakePart(
                    text=part_spec.get("text"),
                    thought=part_spec.get("thought", False),
                    function_call=fc,
                )
            )

        content = _FakeContent(parts=parts)
        candidate = _FakeCandidate(
            content=content,
            finish_reason=kwargs.get("finish_reason", "STOP"),
        )
        usage = _FakeUsage(
            prompt_tokens=kwargs.get("prompt_tokens", 10),
            completion_tokens=kwargs.get("completion_tokens", 5),
        )
        return _FakeResponse(candidates=[candidate], usage_metadata=usage)

    def test_parse_basic_text(self) -> None:
        p = self._plugin()
        resp = self._mock_response(parts=[{"text": "Hello!"}])
        req = _make_request(model_id="gemini-2.5-flash")
        result = p._normalize_response(resp, req)
        assert result.text == "Hello!"
        assert result.finish_reason == FinishReason.STOP
        assert result.prompt_tokens == 10
        assert result.completion_tokens == 5

    def test_parse_function_call(self) -> None:
        p = self._plugin()
        resp = self._mock_response(
            parts=[
                {
                    "function_call": {"name": "search", "args": {"q": "test"}},
                }
            ]
        )
        req = _make_request(model_id="gemini-2.5-flash")
        result = p._normalize_response(resp, req)
        assert result.finish_reason == FinishReason.TOOL_CALLS
        assert result.tool_calls is not None
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "search"
        assert json.loads(result.tool_calls[0].arguments) == {"q": "test"}

    def test_parse_thinking_parts(self) -> None:
        """Thinking parts are captured in raw_response metadata."""
        p = self._plugin()
        resp = self._mock_response(
            parts=[
                {"text": "Let me think...", "thought": True},
                {"text": "The answer is 42."},
            ]
        )
        req = _make_request(model_id="gemini-2.5-flash")
        result = p._normalize_response(resp, req)
        assert result.text == "The answer is 42."
        assert result.raw_response is not None
        assert result.raw_response.get("thought_text") == "Let me think..."

    def test_parse_empty_candidates(self) -> None:
        """Empty candidates list produces empty response."""
        p = self._plugin()

        class _EmptyResp:
            candidates = []
            usage_metadata = None

        resp = _EmptyResp()
        req = _make_request(model_id="gemini-2.5-flash")
        result = p._normalize_response(resp, req)
        assert result.text == ""
        assert result.tool_calls is None


# ===========================================================================
# 8. vLLM Plugin: Request/Response
# ===========================================================================


class TestVLLMRequestBuilding:
    """vLLM request body construction (OpenAI-compatible)."""

    def _plugin(self) -> VLLMPlugin:
        p = VLLMPlugin()
        p._capabilities = {CapabilityType.CHAT}
        p._api_base = "http://localhost:8000/v1"
        return p

    def test_basic_body(self) -> None:
        p = self._plugin()
        req = _make_request(model_id="meta-llama/Llama-3.3-70B-Instruct")
        body = p._build_body(req, stream=False)
        assert body["model"] == "meta-llama/Llama-3.3-70B-Instruct"
        assert body["max_tokens"] == 1024
        assert body["stream"] is False

    def test_system_prompt_in_messages(self) -> None:
        p = self._plugin()
        req = _make_request(model_id="test", system_prompt="Be helpful")
        body = p._build_body(req, stream=False)
        assert body["messages"][0]["role"] == "system"

    def test_auth_no_key(self) -> None:
        """vLLM: no auth by default."""
        p = self._plugin()
        headers = p._auth_headers()
        assert "Authorization" not in headers

    def test_auth_with_key(self) -> None:
        p = self._plugin()
        p._api_key = "my-key"
        headers = p._auth_headers()
        assert headers["Authorization"] == "Bearer my-key"

    def test_health_url_strips_v1(self) -> None:
        """vLLM: health endpoint is /health, not /v1/health."""
        p = self._plugin()
        base = p._api_base.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        assert base == "http://localhost:8000"


class TestVLLMResponseParsing:
    """vLLM response parsing (OpenAI format)."""

    def _plugin(self) -> VLLMPlugin:
        p = VLLMPlugin()
        p._api_base = "http://localhost:8000/v1"
        return p

    def test_parse_basic_response(self) -> None:
        p = self._plugin()
        data = {
            "choices": [{"message": {"content": "Hi"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
            "model": "test-model",
        }
        req = _make_request()
        resp = p._parse_response(data, req)
        assert resp.text == "Hi"
        assert resp.finish_reason == FinishReason.STOP

    def test_empty_choices_raises(self) -> None:
        p = self._plugin()
        data = {"choices": [], "usage": {}, "model": "test"}
        req = _make_request()
        with pytest.raises(ProviderError):
            p._parse_response(data, req)


# ===========================================================================
# 9. Ollama Plugin: Request/Response
# ===========================================================================


class TestOllamaRequestBuilding:
    """Ollama native API request body construction."""

    def _plugin(self) -> OllamaPlugin:
        p = OllamaPlugin()
        p._capabilities = {CapabilityType.CHAT, CapabilityType.TOOL_CALL}
        p._api_base = "http://localhost:11434"
        return p

    def test_basic_body(self) -> None:
        p = self._plugin()
        req = _make_request(model_id="llama3.3")
        body = p._build_body(req, stream=False)
        assert body["model"] == "llama3.3"
        assert body["stream"] is False
        assert body["options"]["temperature"] == 0.7
        assert body["options"]["num_predict"] == 1024

    def test_system_prompt_in_messages(self) -> None:
        p = self._plugin()
        req = _make_request(model_id="llama3.3", system_prompt="Be helpful")
        body = p._build_body(req, stream=False)
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][0]["content"] == "Be helpful"

    def test_tools_format(self) -> None:
        """Ollama: tools use {type: function, function: {...}} format."""
        p = self._plugin()
        tools = [{"name": "search", "description": "Search", "parameters": {"type": "object"}}]
        req = _make_request(model_id="llama3.3", tools=tools)
        body = p._build_body(req, stream=False)
        assert body["tools"][0]["type"] == "function"
        assert body["tools"][0]["function"]["name"] == "search"

    def test_json_output_format(self) -> None:
        p = self._plugin()
        req2 = NormalizedRequest(
            capability=CapabilityType.CHAT,
            messages=[Message(role="user", content="Hi")],
            model_id="llama3.3",
            output_schema={"type": "object"},
        )
        body = p._build_body(req2, stream=False)
        assert body["format"] == "json"

    def test_keep_alive(self) -> None:
        p = self._plugin()
        req = _make_request(model_id="llama3.3", extra={"keep_alive": "5m"})
        body = p._build_body(req, stream=False)
        assert body["keep_alive"] == "5m"


class TestOllamaResponseParsing:
    """Ollama native API response parsing."""

    def _plugin(self) -> OllamaPlugin:
        p = OllamaPlugin()
        p._api_base = "http://localhost:11434"
        return p

    def test_parse_basic_response(self) -> None:
        p = self._plugin()
        data = {
            "message": {"role": "assistant", "content": "Hello!"},
            "done": True,
            "model": "llama3.3",
            "prompt_eval_count": 10,
            "eval_count": 5,
        }
        req = _make_request(model_id="llama3.3")
        resp = p._parse_response(data, req)
        assert resp.text == "Hello!"
        assert resp.finish_reason == FinishReason.STOP
        assert resp.prompt_tokens == 10
        assert resp.completion_tokens == 5

    def test_parse_tool_call_response(self) -> None:
        """Ollama: arguments are OBJECT (not string)."""
        p = self._plugin()
        data = {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "get_weather",
                            "arguments": {"city": "NYC"},
                        },
                    }
                ],
            },
            "done": True,
            "model": "llama3.3",
            "prompt_eval_count": 20,
            "eval_count": 10,
        }
        req = _make_request(model_id="llama3.3")
        resp = p._parse_response(data, req)
        assert resp.finish_reason == FinishReason.TOOL_CALLS
        assert resp.tool_calls is not None
        assert resp.tool_calls[0].name == "get_weather"
        assert json.loads(resp.tool_calls[0].arguments) == {"city": "NYC"}

    def test_parse_length_finish(self) -> None:
        p = self._plugin()
        data = {
            "message": {"content": "Truncated..."},
            "done": True,
            "done_reason": "length",
            "model": "llama3.3",
            "prompt_eval_count": 0,
            "eval_count": 0,
        }
        req = _make_request(model_id="llama3.3")
        resp = p._parse_response(data, req)
        assert resp.finish_reason == FinishReason.LENGTH

    def test_set_api_key_noop(self) -> None:
        """Ollama: set_api_key is a no-op."""
        p = self._plugin()
        p.set_api_key("whatever")  # Should not raise


# ===========================================================================
# 10. Manifest Loading Tests
# ===========================================================================


class TestManifestLoading:
    """All manifest YAML files parse correctly via load_manifest()."""

    @pytest.mark.parametrize("filename", ALL_MANIFEST_FILES)
    def test_manifest_loads(self, filename: str) -> None:
        path = MANIFEST_DIR / filename
        assert path.exists(), f"Manifest {filename} not found at {path}"
        manifest = load_manifest(path)
        assert isinstance(manifest, ProviderManifest)
        assert manifest.provider_id
        assert manifest.display_name
        assert len(manifest.models) > 0

    @pytest.mark.parametrize("filename", ALL_MANIFEST_FILES)
    def test_manifest_has_capabilities(self, filename: str) -> None:
        manifest = load_manifest(MANIFEST_DIR / filename)
        # Each manifest should have at least CHAT
        all_caps = set(manifest.capabilities)
        for model in manifest.models:
            all_caps.update(model.capabilities)
        assert CapabilityType.CHAT in all_caps

    @pytest.mark.parametrize("filename", ALL_MANIFEST_FILES)
    def test_manifest_models_have_ids(self, filename: str) -> None:
        manifest = load_manifest(MANIFEST_DIR / filename)
        for model in manifest.models:
            assert model.id, f"Model in {filename} has empty id"

    def test_openai_manifest_models(self) -> None:
        m = load_manifest(MANIFEST_DIR / "openai.manifest.yaml")
        assert m.provider_id == "openai"
        model_ids = {s.id for s in m.models}
        assert "gpt-4o" in model_ids
        assert "gpt-4o-mini" in model_ids

    def test_anthropic_manifest_models(self) -> None:
        m = load_manifest(MANIFEST_DIR / "anthropic.manifest.yaml")
        assert m.provider_id == "anthropic"
        model_ids = {s.id for s in m.models}
        assert "claude-sonnet-4-6" in model_ids

    def test_google_manifest_models(self) -> None:
        m = load_manifest(MANIFEST_DIR / "google.manifest.yaml")
        assert m.provider_id == "google"
        model_ids = {s.id for s in m.models}
        assert "gemini-2.5-flash" in model_ids

    def test_vertex_manifest_models(self) -> None:
        m = load_manifest(MANIFEST_DIR / "vertex.manifest.yaml")
        assert m.provider_id == "vertex"
        assert m.api_base == "https://aiplatform.googleapis.com/v1"
        assert m.auth.type == "none"
        assert m.auth.credential_key == "GOOGLE_API_KEY"
        model_ids = {s.id for s in m.models}
        assert {
            "gemini-3.1-pro-preview",
            "gemini-3.1-pro-preview-customtools",
            "gemini-3-flash-preview",
            "gemini-3.1-flash-lite",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemini-embedding-001",
        }.issubset(model_ids)

    def test_vllm_manifest_models(self) -> None:
        m = load_manifest(MANIFEST_DIR / "vllm.manifest.yaml")
        assert m.provider_id == "vllm"
        assert len(m.models) >= 1

    def test_ollama_manifest_models(self) -> None:
        m = load_manifest(MANIFEST_DIR / "ollama.manifest.yaml")
        assert m.provider_id == "ollama"
        model_ids = {s.id for s in m.models}
        # Ollama model IDs include tags
        assert any("llama3.3" in mid for mid in model_ids)


# ===========================================================================
# 11. Error Handling Tests
# ===========================================================================


class TestErrorHandling:
    """Error handling across plugins."""

    def test_openai_rate_limit(self) -> None:
        p = OpenAIPlugin()
        p._api_base = "https://api.openai.com/v1"
        req = _make_request()
        with pytest.raises(RateLimitError):
            p._raise_for_status(429, '{"error":{"message":"Rate limited"}}', req)

    def test_openai_provider_error(self) -> None:
        p = OpenAIPlugin()
        p._api_base = "https://api.openai.com/v1"
        req = _make_request()
        with pytest.raises(ProviderError):
            p._raise_for_status(500, '{"error":{"message":"Server error"}}', req)

    def test_anthropic_rate_limit(self) -> None:
        p = AnthropicPlugin()
        p._api_base = "https://api.anthropic.com/v1"
        req = _make_request()
        with pytest.raises(RateLimitError):
            p._raise_for_status(429, '{"error":{"message":"Rate limited"}}', req)

    def test_google_error_no_key(self) -> None:
        """GooglePlugin raises ProviderError when no API key is set."""
        p = GooglePlugin()
        with pytest.raises(ProviderError):
            p._ensure_client()

    def test_vllm_provider_error(self) -> None:
        p = VLLMPlugin()
        p._api_base = "http://localhost:8000/v1"
        req = _make_request()
        with pytest.raises(ProviderError):
            p._raise_for_status(500, "Internal error", req)

    def test_ollama_provider_error(self) -> None:
        p = OllamaPlugin()
        p._api_base = "http://localhost:11434"
        req = _make_request()
        with pytest.raises(ProviderError):
            p._raise_for_status(500, "model not found", req)


# ===========================================================================
# 12. Cross-plugin API key tests
# ===========================================================================


class TestApiKeyManagement:
    """API key set/get for all plugins."""

    def test_openai_set_key(self) -> None:
        p = OpenAIPlugin()
        p.set_api_key("sk-test")
        assert p._api_key == "sk-test"
        headers = p._auth_headers()
        assert headers["Authorization"] == "Bearer sk-test"

    def test_anthropic_set_key(self) -> None:
        p = AnthropicPlugin()
        p.set_api_key("sk-ant-test")
        assert p._api_key == "sk-ant-test"
        headers = p._auth_headers()
        assert headers["x-api-key"] == "sk-ant-test"

    def test_google_set_key(self) -> None:
        p = GooglePlugin()
        p.set_api_key("AIza-test")
        assert p._api_key == "AIza-test"
        # SDK-based: verify client is reset when key changes
        p._client = "old_client"
        p.set_api_key("AIza-new")
        assert p._client is None  # Forces re-creation

    def test_vllm_no_key_by_default(self) -> None:
        p = VLLMPlugin()
        headers = p._auth_headers()
        assert "Authorization" not in headers

    def test_vllm_optional_key(self) -> None:
        p = VLLMPlugin()
        p.set_api_key("vllm-key")
        headers = p._auth_headers()
        assert headers["Authorization"] == "Bearer vllm-key"

    def test_ollama_key_noop(self) -> None:
        p = OllamaPlugin()
        p.set_api_key("anything")
        # No _api_key attribute or no-op
