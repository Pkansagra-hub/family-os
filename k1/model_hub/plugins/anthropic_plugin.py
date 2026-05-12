"""Anthropic provider plugin [F22].

Maps NormalizedRequest -> Anthropic Messages API -> ProviderResponse.
API reference verified against https://docs.anthropic.com/en/api (2026-03-31).

Key API details:
  - Auth: x-api-key header + anthropic-version: 2023-06-01
  - Chat: POST /v1/messages
  - system prompt is TOP-LEVEL 'system' field (NOT in messages)
  - max_tokens is REQUIRED
  - Content is array of blocks [{type: "text", text: "..."}]
  - stop_reason values: end_turn, tool_use, max_tokens, stop_sequence
  - Tool definition uses input_schema (NOT parameters)
  - Streaming: SSE with event types:
      message_start -> content_block_start -> content_block_delta -> content_block_stop
      -> message_delta (has stop_reason + usage) -> message_stop
  - Extended thinking: thinking: {type: "adaptive"} for sonnet/opus 4.6
  - Token counting: POST /v1/messages/count_tokens

Import graph (Layer 4 -- plugin)
---------------------------------
k1.model_hub.plugins.anthropic_plugin
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

_ANTHROPIC_VERSION = "2023-06-01"

_STOP_REASON_MAP: Dict[str, FinishReason] = {
    "end_turn": FinishReason.STOP,
    "tool_use": FinishReason.TOOL_CALLS,
    "max_tokens": FinishReason.LENGTH,
    "stop_sequence": FinishReason.STOP,
}


class AnthropicPlugin:
    """Anthropic provider plugin implementing IProviderPlugin.

    Supports: CHAT, TOOL_CALL, STRUCTURED, REASON, VISION, TOKEN_COUNT, CACHE_PROMPT.
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
        self._api_base = manifest.api_base or "https://api.anthropic.com/v1"
        self._capabilities = set(manifest.capabilities)
        for model in manifest.models:
            self._capabilities.update(model.capabilities)
        self._session = aiohttp.ClientSession(
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
        body = self._build_body(request, stream=False)
        data = await self._post("/messages", body, request)
        return self._parse_response(data, request)

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        body = self._build_body(request, stream=True)
        url = f"{self._api_base}/messages"
        headers = self._auth_headers()

        async with self._get_session().post(url, json=body, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                self._raise_for_status(resp.status, text, request)

            event_type = ""
            _input_tokens = 0  # captured from message_start
            async for line in resp.content:
                decoded = line.decode("utf-8").strip()
                if not decoded:
                    continue

                if decoded.startswith("event:"):
                    event_type = decoded[len("event:") :].strip()
                    continue

                if not decoded.startswith("data:"):
                    continue

                payload = decoded[len("data:") :].strip()
                chunk_data = json.loads(payload)

                if event_type == "message_start":
                    # Capture prompt token count for the done-chunk later.
                    msg_usage = chunk_data.get("message", {}).get("usage", {})
                    _input_tokens = int(msg_usage.get("input_tokens", 0))

                elif event_type == "content_block_delta":
                    delta = chunk_data.get("delta", {})
                    delta_type = delta.get("type", "")
                    if delta_type == "text_delta":
                        yield ProviderChunk(
                            text=delta.get("text", ""),
                            done=False,
                        )
                    elif delta_type == "input_json_delta":
                        # Streaming tool call arguments
                        yield ProviderChunk(
                            text="",
                            done=False,
                            metadata={"tool_input_delta": delta.get("partial_json", "")},
                        )

                elif event_type == "message_delta":
                    delta = chunk_data.get("delta", {})
                    usage = chunk_data.get("usage", {})
                    yield ProviderChunk(
                        text="",
                        done=True,
                        prompt_tokens=_input_tokens,
                        completion_tokens=int(usage.get("output_tokens", 0)),
                        metadata={"stop_reason": delta.get("stop_reason")},
                    )

                elif event_type == "message_stop":
                    break

    def estimate_tokens(self, messages: List[Message]) -> int:
        total = 0
        for msg in messages:
            total += 4  # message overhead
            total += len(msg.content) // 4  # ~4 chars per token
        total += 2  # priming
        return total

    async def health_check(self) -> ProviderHealth:
        """Check health via a minimal count_tokens call."""
        try:
            url = f"{self._api_base}/messages/count_tokens"
            headers = self._auth_headers()
            body = {
                "model": "claude-haiku-4-5",
                "messages": [{"role": "user", "content": "hi"}],
            }
            async with self._get_session().post(url, json=body, headers=headers) as resp:
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

    def _build_body(self, request: NormalizedRequest, *, stream: bool) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "model": request.model_id,
            "messages": self._format_messages(request),
            "max_tokens": request.max_tokens,  # REQUIRED by Anthropic
            "stream": stream,
        }

        # System prompt is a TOP-LEVEL field, NOT in messages
        if request.system_prompt:
            body["system"] = request.system_prompt

        body["temperature"] = request.temperature

        # Tools use input_schema, NOT parameters
        if request.tools:
            body["tools"] = [
                {
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                    "input_schema": t.get("parameters", t.get("input_schema", {})),
                }
                for t in request.tools
            ]
            if request.tool_choice:
                body["tool_choice"] = self._map_tool_choice(request.tool_choice)

        # Extended thinking for capable models
        if request.reasoning_effort:
            body["thinking"] = {"type": "enabled", "budget_tokens": request.max_tokens // 2}

        return body

    def _format_messages(self, request: NormalizedRequest) -> List[Dict[str, Any]]:
        msgs: List[Dict[str, Any]] = []
        for msg in request.messages:
            entry: Dict[str, Any] = {
                "role": msg.role,
                "content": msg.content,
            }
            msgs.append(entry)
        return msgs

    def _map_tool_choice(self, choice: str) -> Dict[str, Any]:
        if choice == "auto":
            return {"type": "auto"}
        if choice == "none":
            return {"type": "none"}
        if choice == "required":
            return {"type": "any"}
        # Specific tool name
        return {"type": "tool", "name": choice}

    # -- Internal: response parsing --------------------------------------------

    def _parse_response(
        self,
        data: Dict[str, Any],
        request: NormalizedRequest,
    ) -> ProviderResponse:
        content_blocks = data.get("content", [])
        text_parts: List[str] = []
        tool_calls: List[ToolCallResult] = []

        for block in content_blocks:
            btype = block.get("type", "")
            if btype == "text":
                text_parts.append(block.get("text", ""))
            elif btype == "tool_use":
                tc_id = block.get("id") or "tc_0"
                tc_name = block.get("name") or "unknown"
                tool_calls.append(
                    ToolCallResult(
                        id=tc_id,
                        name=tc_name,
                        arguments=json.dumps(block.get("input", {})),
                    )
                )

        usage = data.get("usage", {})
        stop_reason = data.get("stop_reason", "end_turn")
        finish = _STOP_REASON_MAP.get(stop_reason, FinishReason.STOP)

        return ProviderResponse(
            text="\n".join(text_parts),
            tool_calls=tool_calls if tool_calls else None,
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
            model_id=data.get("model", request.model_id),
            finish_reason=finish,
            raw_response=data,
        )

    # -- Internal: HTTP --------------------------------------------------------

    def _auth_headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

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
        headers = self._auth_headers()

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
                f"Anthropic rate limited: {msg}",
                provider_id="anthropic",
                request_id=request.trace_id,
            )
        raise ProviderError(
            f"Anthropic API error ({status}): {msg}",
            provider_id="anthropic",
            request_id=request.trace_id,
        )

    def set_api_key(self, key: str) -> None:
        """Set API key (called by ProviderDispatcher via credential port)."""
        self._api_key = key


__all__ = ["AnthropicPlugin"]
