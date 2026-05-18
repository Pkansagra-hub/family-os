"""Google Gemini provider plugin [F23].

Maps NormalizedRequest -> google-genai SDK -> ProviderResponse.
Uses the official google-genai SDK (genai.Client) for full support of:
  - Thinking (ThinkingConfig with budget)
  - Tool calling (FunctionDeclaration + ToolConfig)
  - Streaming (generate_content_stream)
  - Structured output (JSON mode)

Credential reference: poc/chat_experience_poc/.env -> GOOGLE_API_KEY

Import graph (Layer 4 -- plugin)
---------------------------------
k1.model_hub.plugins.google_plugin
  -> k1.model_hub.types      (Layer 0)
  -> k1.model_hub.manifest   (Layer 0)
  -> k1.model_hub.plugins.base (Layer 2)
  -> google.genai (external SDK)
  -> stdlib

NEVER import from any service, adapter, or runtime module.
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue as _queue_mod
import threading as _threading_mod
import time
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4

from k1.model_hub.manifest import ProviderManifest
from k1.model_hub.plugins.base import (
    NormalizedRequest,
    ProviderChunk,
    ProviderHealth,
    ProviderResponse,
)
from k1.model_hub.types import (
    CapabilityType,
    FinishReason,
    HealthStatus,
    Message,
    ProviderError,
    RateLimitError,
    ToolCallResult,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy import of google.genai -- only this module touches it
# ---------------------------------------------------------------------------
_genai = None
_types = None


def _ensure_genai():
    """Lazy-load google.genai SDK. Fails fast with clear message."""
    global _genai, _types
    if _genai is None:
        try:
            from google import genai
            from google.genai import types

            _genai = genai
            _types = types
        except ImportError as exc:
            raise ImportError(
                "google-genai package not installed. Run: pip install google-genai"
            ) from exc
    return _genai, _types


_FINISH_MAP: Dict[str, FinishReason] = {
    "STOP": FinishReason.STOP,
    "MAX_TOKENS": FinishReason.LENGTH,
    "SAFETY": FinishReason.SAFETY,
    "RECITATION": FinishReason.SAFETY,
    "LANGUAGE": FinishReason.SAFETY,
    "BLOCKLIST": FinishReason.SAFETY,
    "PROHIBITED_CONTENT": FinishReason.SAFETY,
    "SPII": FinishReason.SAFETY,
    "MALFORMED_FUNCTION_CALL": FinishReason.ERROR,
}


def _map_finish_reason(raw_finish: Any) -> FinishReason:
    if raw_finish is None:
        return FinishReason.STOP
    finish_text = str(raw_finish).upper()
    for key, mapped in _FINISH_MAP.items():
        if key in finish_text:
            return mapped
    return FinishReason.STOP


# Thinking budget mapping for Gemini 2.5 models (0-24576 for Flash)
_THINKING_BUDGET_MAP: Dict[str, int] = {
    "low": 1024,
    "medium": 8192,
    "high": 24576,
}


class GooglePlugin:
    """Google Gemini provider plugin implementing IProviderPlugin.

    Uses the google-genai SDK (genai.Client) for proper thinking,
    tool calling, and streaming support.

    Supports: CHAT, TOOL_CALL, STRUCTURED, REASON, EMBED, VISION,
    WEB_SEARCH, CODE_EXEC, TOKEN_COUNT.
    """

    provider_id = "google"

    def __init__(self) -> None:
        self._manifest: Optional[ProviderManifest] = None
        self._client: Any = None
        self._capabilities: set[CapabilityType] = set()
        self._api_key: str = ""

    # -- Lifecycle -------------------------------------------------------------

    async def initialize(self, manifest: ProviderManifest) -> None:
        self._manifest = manifest
        self._capabilities = set(manifest.capabilities)
        for model in manifest.models:
            self._capabilities.update(model.capabilities)
        # Client is created lazily on first use (needs api_key set first)

    def _ensure_client(self) -> Any:
        """Create the genai.Client lazily once api_key is available."""
        if self._client is None:
            genai, _ = _ensure_genai()
            if self._requires_api_key() and not self._api_key:
                raise ProviderError(
                    "Google API key not set. Call set_api_key() first.",
                    provider_id=self.provider_id,
                )
            self._client = self._create_client(genai, _)
        return self._client

    def _requires_api_key(self) -> bool:
        """Whether this provider requires API-key auth before client creation."""
        return True

    def _create_client(self, genai: Any, types: Any) -> Any:
        """Create the SDK client for the Gemini Developer API."""
        return genai.Client(api_key=self._api_key)

    def _resolve_model_id(self, request: NormalizedRequest) -> str:
        """Return the provider model id for this request."""
        return request.model_id

    def supports(self, capability: CapabilityType) -> bool:
        return capability in self._capabilities

    async def close(self) -> None:
        self._client = None

    # -- Execute ---------------------------------------------------------------

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        client = self._ensure_client()
        _, types = _ensure_genai()

        contents = self._to_genai_contents(request, types)
        config = self._build_config(request, types)
        model_id = self._resolve_model_id(request)

        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model=model_id,
                    contents=contents,
                    config=config,
                ),
            )
        except Exception as exc:
            exc_str = str(exc)
            if "RESOURCE_EXHAUSTED" in exc_str or "429" in exc_str:
                raise RateLimitError(
                    f"Gemini rate limited: {exc_str}",
                    provider_id=self.provider_id,
                    request_id=request.trace_id,
                )
            raise ProviderError(
                f"Gemini API error: {exc_str}",
                provider_id=self.provider_id,
                request_id=request.trace_id,
            )

        return self._normalize_response(response, request, model_id=model_id)

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        client = self._ensure_client()
        _, types = _ensure_genai()

        contents = self._to_genai_contents(request, types)
        config = self._build_config(request, types)
        model_id = self._resolve_model_id(request)

        # Bridge the synchronous google-genai streaming iterator into async
        # using a thread + queue so chunks are yielded progressively.
        _SENTINEL = object()
        chunk_queue: _queue_mod.Queue = _queue_mod.Queue()

        def _produce() -> None:
            try:
                for raw_chunk in client.models.generate_content_stream(
                    model=model_id,
                    contents=contents,
                    config=config,
                ):
                    chunk_queue.put(raw_chunk)
            except Exception as exc:
                chunk_queue.put(exc)
            finally:
                chunk_queue.put(_SENTINEL)

        loop = asyncio.get_event_loop()
        _threading_mod.Thread(target=_produce, daemon=True).start()
        streamed_text_chars = 0
        streamed_tool_calls = 0

        while True:
            item = await loop.run_in_executor(None, chunk_queue.get)
            if item is _SENTINEL:
                break
            if isinstance(item, BaseException):
                exc_str = str(item)
                if "RESOURCE_EXHAUSTED" in exc_str or "429" in exc_str:
                    raise RateLimitError(
                        f"Gemini rate limited: {exc_str}",
                        provider_id=self.provider_id,
                        request_id=request.trace_id,
                    )
                raise ProviderError(
                    f"Gemini stream error: {exc_str}",
                    provider_id=self.provider_id,
                    request_id=request.trace_id,
                )
            chunk = item
            if not chunk.candidates:
                continue
            candidate = chunk.candidates[0]
            if not candidate.content or not candidate.content.parts:
                # No content parts, but check if this is the final chunk
                # (finish_reason set without content — common in Gemini streaming)
                if candidate.finish_reason is not None:
                    finish_reason = _map_finish_reason(candidate.finish_reason)
                    prompt_tokens = 0
                    completion_tokens = 0
                    if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                        um = chunk.usage_metadata
                        prompt_tokens = int(getattr(um, "prompt_token_count", 0) or 0)
                        completion_tokens = int(getattr(um, "candidates_token_count", 0) or 0)
                    if streamed_text_chars == 0 and streamed_tool_calls == 0:
                        logger.warning(
                            "GooglePlugin.stream_execute: empty terminal chunk "
                            "finish_reason=%s prompt_tokens=%d completion_tokens=%d trace=%s",
                            candidate.finish_reason,
                            prompt_tokens,
                            completion_tokens,
                            request.trace_id[:8] if request.trace_id else "",
                        )
                    yield ProviderChunk(
                        text="",
                        done=True,
                        tool_calls=None,
                        metadata={
                            "finish_reason": finish_reason.value,
                            "provider_finish_reason": str(candidate.finish_reason),
                        },
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                    )
                continue

            text_parts = []
            thought_text = ""
            tool_calls: List[ToolCallResult] = []

            for part in candidate.content.parts:
                if getattr(part, "thought", False) and hasattr(part, "text") and part.text:
                    thought_text += part.text
                elif hasattr(part, "text") and part.text and not getattr(part, "thought", False):
                    text_parts.append(part.text)
                elif hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    tc_name = fc.name or "unknown"
                    tool_calls.append(
                        ToolCallResult(
                            id=f"call_{uuid4().hex[:8]}",
                            name=tc_name,
                            arguments=json.dumps(dict(fc.args) if fc.args else {}),
                        )
                    )

            finish = candidate.finish_reason is not None
            finish_reason = (
                _map_finish_reason(candidate.finish_reason) if finish else FinishReason.STOP
            )
            metadata = {}
            if finish:
                metadata["finish_reason"] = finish_reason.value
                metadata["provider_finish_reason"] = str(candidate.finish_reason)
            if thought_text:
                metadata["thought_text"] = thought_text

            prompt_tokens = 0
            completion_tokens = 0
            if finish and hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                um = chunk.usage_metadata
                prompt_tokens = int(getattr(um, "prompt_token_count", 0) or 0)
                completion_tokens = int(getattr(um, "candidates_token_count", 0) or 0)

            visible_text = "".join(text_parts)
            if (
                finish
                and not visible_text
                and not tool_calls
                and streamed_text_chars == 0
                and streamed_tool_calls == 0
            ):
                logger.warning(
                    "GooglePlugin.stream_execute: terminal chunk has no text/tool calls "
                    "finish_reason=%s thought_chars=%d prompt_tokens=%d completion_tokens=%d trace=%s",
                    candidate.finish_reason,
                    len(thought_text),
                    prompt_tokens,
                    completion_tokens,
                    request.trace_id[:8] if request.trace_id else "",
                )

            streamed_text_chars += len(visible_text)
            streamed_tool_calls += len(tool_calls)

            yield ProviderChunk(
                text=visible_text,
                done=finish,
                tool_calls=tool_calls if tool_calls else None,
                metadata=metadata if metadata else None,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

    def estimate_tokens(self, messages: List[Message]) -> int:
        total = 0
        for msg in messages:
            total += 4
            total += len(msg.content) // 4
        total += 2
        return total

    async def health_check(self) -> ProviderHealth:
        try:
            client = self._ensure_client()
            loop = asyncio.get_event_loop()
            models = await loop.run_in_executor(
                None,
                lambda: list(client.models.list()),
            )
            if models:
                return ProviderHealth(status=HealthStatus.HEALTHY)
            return ProviderHealth(status=HealthStatus.DEGRADED, details="No models listed")
        except Exception as exc:
            return ProviderHealth(
                status=HealthStatus.UNHEALTHY,
                details=str(exc),
            )

    # -- Internal: config building ---------------------------------------------

    def _build_config(self, request: NormalizedRequest, types: Any) -> Any:
        """Build GenerateContentConfig from NormalizedRequest."""
        config_kwargs: Dict[str, Any] = {}

        # System instruction
        if request.system_prompt:
            config_kwargs["system_instruction"] = request.system_prompt

        # Temperature
        config_kwargs["temperature"] = request.temperature

        # Max output tokens
        config_kwargs["max_output_tokens"] = request.max_tokens

        # Tools
        gemini_tools = self._to_genai_tools(request, types)
        if gemini_tools:
            config_kwargs["tools"] = gemini_tools
            # Tool calling mode
            if request.tool_choice:
                config_kwargs["tool_config"] = self._build_tool_config(
                    request.tool_choice,
                    types,
                )

        # Thinking config
        if request.reasoning_effort:
            budget = _THINKING_BUDGET_MAP.get(request.reasoning_effort, 8192)
            config_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_budget=budget,
                include_thoughts=True,
            )

        # Structured output (JSON mode)
        if request.output_schema:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_json_schema"] = request.output_schema

        return types.GenerateContentConfig(**config_kwargs)

    # -- Internal: content conversion ------------------------------------------

    def _to_genai_contents(self, request: NormalizedRequest, types: Any) -> list:
        """Convert NormalizedRequest messages to Gemini Content objects."""
        contents = []
        for msg in request.messages:
            if msg.role == "user":
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=msg.content)],
                    )
                )
            elif msg.role == "assistant":
                parts = []
                if msg.content:
                    parts.append(types.Part.from_text(text=msg.content))
                if parts:
                    contents.append(types.Content(role="model", parts=parts))
            elif msg.role == "tool":
                # Tool result -> FunctionResponse
                try:
                    result_data = json.loads(msg.content)
                except (json.JSONDecodeError, TypeError):
                    result_data = {"result": msg.content}
                contents.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_function_response(
                                name=msg.name or "unknown_tool",
                                response=result_data,
                            )
                        ],
                    )
                )
        return contents

    # -- Internal: tool conversion ---------------------------------------------

    def _to_genai_tools(self, request: NormalizedRequest, types: Any) -> Optional[list]:
        """Convert NormalizedRequest tools to Gemini FunctionDeclaration list."""
        result_tools: list = []

        if request.tools:
            func_decls = []
            for t in request.tools:
                func_decls.append(
                    types.FunctionDeclaration(
                        name=t.get("name", ""),
                        description=t.get("description", ""),
                        parameters_json_schema=t.get("parameters", {}),
                    )
                )
            result_tools.append(types.Tool(function_declarations=func_decls))

        # Gemini-specific tools
        if request.extra.get("code_execution"):
            result_tools.append(types.Tool(code_execution=types.ToolCodeExecution()))
        if request.extra.get("google_search"):
            result_tools.append(types.Tool(google_search=types.GoogleSearch()))

        return result_tools if result_tools else None

    def _build_tool_config(self, tool_choice: str, types: Any) -> Any:
        """Convert tool_choice to Gemini ToolConfig."""
        mode_map = {"auto": "AUTO", "required": "ANY", "none": "NONE"}
        mode = mode_map.get(tool_choice, "AUTO")

        allowed = None
        if tool_choice not in mode_map and tool_choice:
            mode = "ANY"
            allowed = [tool_choice]

        config_kwargs: Dict[str, Any] = {"mode": mode}
        if allowed:
            config_kwargs["allowed_function_names"] = allowed

        return types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(**config_kwargs),
        )

    # -- Internal: response normalization --------------------------------------

    def _normalize_response(
        self,
        response: Any,
        request: NormalizedRequest,
        *,
        model_id: str | None = None,
    ) -> ProviderResponse:
        """Convert Gemini SDK response to ProviderResponse."""
        text = ""
        thought_text = ""
        tool_calls: List[ToolCallResult] = []

        if response.candidates:
            candidate = response.candidates[0]
            if candidate.content and candidate.content.parts:
                for part in candidate.content.parts:
                    # Thinking parts
                    if getattr(part, "thought", False) and hasattr(part, "text") and part.text:
                        thought_text += part.text
                    # Regular text
                    elif (
                        hasattr(part, "text") and part.text and not getattr(part, "thought", False)
                    ):
                        text += part.text
                    # Function calls
                    elif hasattr(part, "function_call") and part.function_call:
                        fc = part.function_call
                        tool_calls.append(
                            ToolCallResult(
                                id=f"call_{uuid4().hex[:8]}",
                                name=fc.name or "unknown",
                                arguments=json.dumps(dict(fc.args) if fc.args else {}),
                            )
                        )

        # Token usage
        tokens_in = 0
        tokens_out = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            um = response.usage_metadata
            tokens_in = getattr(um, "prompt_token_count", 0) or 0
            tokens_out = getattr(um, "candidates_token_count", 0) or 0

        # Finish reason
        finish_reason = FinishReason.STOP
        if tool_calls:
            finish_reason = FinishReason.TOOL_CALLS
        elif response.candidates:
            fr = getattr(response.candidates[0], "finish_reason", None)
            if fr is not None:
                finish_reason = _map_finish_reason(fr)

        raw = {"thought_text": thought_text} if thought_text else {}

        return ProviderResponse(
            text=text,
            tool_calls=tool_calls if tool_calls else None,
            prompt_tokens=tokens_in,
            completion_tokens=tokens_out,
            model_id=model_id or request.model_id,
            finish_reason=finish_reason,
            raw_response=raw,
        )

    # -- Public: API key -------------------------------------------------------

    def set_api_key(self, key: str) -> None:
        """Set API key. Invalidates existing client so next call creates a new one."""
        self._api_key = key
        self._client = None  # Force re-creation with new key


def _now_ms() -> int:
    return int(time.time() * 1000)


__all__ = ["GooglePlugin"]
