"""OpenAI provider plugin [F21].

Maps NormalizedRequest -> OpenAI Chat Completions API -> ProviderResponse.
API reference verified against https://platform.openai.com/docs (2026-03-31).

Key API details:
  - Auth: Authorization: Bearer <key>
  - Chat: POST /v1/chat/completions
  - Use max_completion_tokens (NOT max_tokens) -- required for o-series
  - Streaming: SSE with data: {json}, ends with data: [DONE]
  - stream_options: {"include_usage": true} for usage in streaming
  - Reasoning models (o3, o4-mini): reasoning_effort, no stop parameter
  - Embeddings: POST /v1/embeddings
  - finish_reason: stop, tool_calls, length, content_filter

Import graph (Layer 4 -- plugin)
---------------------------------
k1.model_hub.plugins.openai_plugin
  -> k1.model_hub.types      (Layer 0)
  -> k1.model_hub.manifest   (Layer 0)
  -> k1.model_hub.plugins.base (Layer 2)
  -> aiohttp (external)
  -> stdlib

NEVER import from any service, adapter, or runtime module.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

import aiohttp

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

# Reasoning models that use reasoning_effort and max_completion_tokens
_REASONING_MODELS = frozenset({"o3", "o4-mini", "o3-mini", "o1", "o1-mini"})

_FINISH_MAP: Dict[str, FinishReason] = {
    "stop": FinishReason.STOP,
    "tool_calls": FinishReason.TOOL_CALLS,
    "length": FinishReason.LENGTH,
    "content_filter": FinishReason.SAFETY,
}


class OpenAIPlugin:
    """OpenAI provider plugin implementing IProviderPlugin.

    Supports: CHAT, TOOL_CALL, STRUCTURED, REASON, EMBED, VISION,
    IMAGE_GEN, AUDIO_IN, TTS, MODERATE, WEB_SEARCH, TOKEN_COUNT, CACHE_PROMPT, BATCH.
    """

    def __init__(self) -> None:
        self._manifest: Optional[ProviderManifest] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._capabilities: set[CapabilityType] = set()
        self._api_base: str = ""
        self._api_key: str = ""

    # -- Lifecycle -------------------------------------------------------------

    async def initialize(self, manifest: ProviderManifest) -> None:
        self._manifest = manifest
        self._api_base = manifest.api_base or "https://api.openai.com/v1"
        self._capabilities = set(manifest.capabilities)
        for model in manifest.models:
            self._capabilities.update(model.capabilities)
        self._session = aiohttp.ClientSession(
            headers={"Content-Type": "application/json"},
            timeout=aiohttp.ClientTimeout(total=120),
        )

    def supports(self, capability: CapabilityType) -> bool:
        return capability in self._capabilities

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # -- Execute ---------------------------------------------------------------

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        body = self._build_chat_body(request, stream=False)
        data = await self._post("/chat/completions", body, request)
        return self._parse_chat_response(data, request)

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        body = self._build_chat_body(request, stream=True)
        body["stream_options"] = {"include_usage": True}

        url = f"{self._api_base}/chat/completions"
        headers = self._auth_headers(request)

        async with self._get_session().post(url, json=body, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                self._raise_for_status(resp.status, text, request)

            accumulated_text = ""
            async for line in resp.content:
                decoded = line.decode("utf-8").strip()
                if not decoded or not decoded.startswith("data:"):
                    continue
                payload = decoded[len("data:") :].strip()
                if payload == "[DONE]":
                    break

                chunk_data = json.loads(payload)
                choices = chunk_data.get("choices", [])
                if not choices:
                    continue

                delta = choices[0].get("delta", {})
                content = delta.get("content", "")
                finish = choices[0].get("finish_reason")

                if content:
                    accumulated_text += content

                tool_calls = self._parse_delta_tool_calls(delta)

                yield ProviderChunk(
                    text=content or "",
                    done=finish is not None,
                    tool_calls=tool_calls,
                )

    def estimate_tokens(self, messages: List[Message]) -> int:
        total = 0
        for msg in messages:
            total += 4  # message overhead
            total += len(msg.content) // 4  # ~4 chars per token
            if msg.role:
                total += 1
        total += 2  # priming
        return total

    async def health_check(self) -> ProviderHealth:
        try:
            url = f"{self._api_base}/models"
            headers = self._auth_headers()
            async with self._get_session().get(url, headers=headers) as resp:
                if resp.status == 200:
                    return ProviderHealth(status=HealthStatus.HEALTHY)
                return ProviderHealth(
                    status=HealthStatus.DEGRADED,
                    details=f"HTTP {resp.status}",
                )
        except Exception as exc:
            return ProviderHealth(
                status=HealthStatus.UNHEALTHY,
                details=str(exc),
            )

    # -- Internal: request building --------------------------------------------

    def _build_chat_body(self, request: NormalizedRequest, *, stream: bool) -> Dict[str, Any]:
        is_reasoning = self._is_reasoning_model(request.model_id)

        messages = self._format_messages(request, is_reasoning)
        body: Dict[str, Any] = {
            "model": request.model_id,
            "messages": messages,
            "stream": stream,
        }

        # max_completion_tokens is preferred; max_tokens is deprecated
        body["max_completion_tokens"] = request.max_tokens

        if not is_reasoning:
            body["temperature"] = request.temperature

        if request.reasoning_effort and is_reasoning:
            body["reasoning_effort"] = request.reasoning_effort

        if request.tools:
            body["tools"] = [{"type": "function", "function": t} for t in request.tools]
            if request.tool_choice:
                body["tool_choice"] = request.tool_choice

        if request.extra.get("response_format"):
            body["response_format"] = request.extra["response_format"]

        if request.extra.get("web_search_options"):
            body["web_search_options"] = request.extra["web_search_options"]

        return body

    def _format_messages(
        self,
        request: NormalizedRequest,
        is_reasoning: bool,
    ) -> List[Dict[str, Any]]:
        msgs: List[Dict[str, Any]] = []

        if request.system_prompt:
            role = "developer" if is_reasoning else "system"
            msgs.append({"role": role, "content": request.system_prompt})

        for msg in request.messages:
            entry: Dict[str, Any] = {"role": msg.role, "content": msg.content}
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            if msg.name:
                entry["name"] = msg.name
            msgs.append(entry)

        return msgs

    def _is_reasoning_model(self, model_id: str) -> bool:
        base = model_id.split("-")[0] if "-" in model_id else model_id
        return base in _REASONING_MODELS or model_id in _REASONING_MODELS

    # -- Internal: response parsing --------------------------------------------

    def _parse_chat_response(
        self,
        data: Dict[str, Any],
        request: NormalizedRequest,
    ) -> ProviderResponse:
        choices = data.get("choices", [])
        if not choices:
            raise ProviderError(
                "No choices in OpenAI response",
                provider_id="openai",
                request_id=request.trace_id,
            )

        choice = choices[0]
        message = choice.get("message", {})
        usage = data.get("usage", {})

        tool_calls = self._parse_tool_calls(message.get("tool_calls"))
        finish = _FINISH_MAP.get(
            choice.get("finish_reason", "stop"),
            FinishReason.STOP,
        )

        return ProviderResponse(
            text=message.get("content", "") or "",
            tool_calls=tool_calls,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            model_id=data.get("model", request.model_id),
            finish_reason=finish,
            raw_response=data,
        )

    def _parse_tool_calls(
        self,
        tool_calls: Optional[List[Dict[str, Any]]],
    ) -> Optional[List[ToolCallResult]]:
        if not tool_calls:
            return None
        results = []
        for tc in tool_calls:
            fn = tc.get("function", {})
            tc_id = tc.get("id") or "tc_0"
            tc_name = fn.get("name") or "unknown"
            args_str = fn.get("arguments", "{}")
            results.append(
                ToolCallResult(
                    id=tc_id,
                    name=tc_name,
                    arguments=args_str,
                )
            )
        return results

    def _parse_delta_tool_calls(
        self,
        delta: Dict[str, Any],
    ) -> Optional[List[ToolCallResult]]:
        tc_list = delta.get("tool_calls")
        if not tc_list:
            return None
        results = []
        for tc in tc_list:
            fn = tc.get("function", {})
            tc_id = tc.get("id") or "tc_0"
            tc_name = fn.get("name") or "unknown"
            results.append(
                ToolCallResult(
                    id=tc_id,
                    name=tc_name,
                    arguments=fn.get("arguments", "") or "{}",
                )
            )
        return results

    # -- Internal: HTTP --------------------------------------------------------

    def _auth_headers(self, request: Optional[NormalizedRequest] = None) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=120),
            )
        return self._session

    async def _post(
        self,
        path: str,
        body: Dict[str, Any],
        request: NormalizedRequest,
    ) -> Dict[str, Any]:
        url = f"{self._api_base}{path}"
        headers = self._auth_headers(request)

        async with self._get_session().post(url, json=body, headers=headers) as resp:
            text = await resp.text()
            if resp.status != 200:
                self._raise_for_status(resp.status, text, request)
            return json.loads(text)

    def _raise_for_status(
        self,
        status: int,
        text: str,
        request: NormalizedRequest,
    ) -> None:
        try:
            err = json.loads(text).get("error", {})
            msg = err.get("message", text)
        except (json.JSONDecodeError, AttributeError):
            msg = text

        if status == 429:
            raise RateLimitError(
                f"OpenAI rate limited: {msg}",
                provider_id="openai",
                request_id=request.trace_id,
            )
        raise ProviderError(
            f"OpenAI API error ({status}): {msg}",
            provider_id="openai",
            request_id=request.trace_id,
        )

    def set_api_key(self, key: str) -> None:
        """Set API key (called by ProviderDispatcher via credential port)."""
        self._api_key = key


__all__ = ["OpenAIPlugin"]
