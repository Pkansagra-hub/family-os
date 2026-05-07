"""vLLM provider plugin [F24].

Maps NormalizedRequest -> vLLM OpenAI-compatible API -> ProviderResponse.
API reference verified against https://docs.vllm.ai (2026-03-31).

Key API details:
  - OpenAI-compatible at /v1/* (same request/response format)
  - Auth: none by default (or --api-key CLI flag)
  - Health: GET /health
  - Single model per instance
  - Tool calling supported with various parsers
  - Streaming: identical SSE format to OpenAI
  - Placement: local_gpu (self-hosted)

Import graph (Layer 4 -- plugin)
---------------------------------
k1.model_hub.plugins.vllm_plugin
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
    ToolCallResult,
)

logger = logging.getLogger(__name__)

_FINISH_MAP: Dict[str, FinishReason] = {
    "stop": FinishReason.STOP,
    "tool_calls": FinishReason.TOOL_CALLS,
    "length": FinishReason.LENGTH,
}


class VLLMPlugin:
    """vLLM provider plugin implementing IProviderPlugin.

    vLLM exposes an OpenAI-compatible API, so request/response format
    mirrors OpenAI. Key difference: self-hosted, single model per instance,
    dedicated /health endpoint, no auth by default.

    Supports: CHAT, TOOL_CALL, STRUCTURED, VISION (model-dependent).
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
        self._api_base = manifest.api_base or "http://localhost:8000/v1"
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
        data = await self._post("/chat/completions", body, request)
        return self._parse_response(data, request)

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        body = self._build_body(request, stream=True)
        body["stream_options"] = {"include_usage": True}

        url = f"{self._api_base}/chat/completions"
        headers = self._auth_headers()

        async with self._get_session().post(url, json=body, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                self._raise_for_status(resp.status, text, request)

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

                tool_calls = self._parse_delta_tool_calls(delta)

                yield ProviderChunk(
                    text=content or "",
                    done=finish is not None,
                    tool_calls=tool_calls,
                )

    def estimate_tokens(self, messages: List[Message]) -> int:
        total = 0
        for msg in messages:
            total += 4
            total += len(msg.content) // 4
        total += 2
        return total

    async def health_check(self) -> ProviderHealth:
        """vLLM has a dedicated GET /health endpoint."""
        try:
            # Strip /v1 suffix for health endpoint
            base = self._api_base.rstrip("/")
            if base.endswith("/v1"):
                base = base[:-3]
            url = f"{base}/health"
            async with self._get_session().get(url) as resp:
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
        messages = self._format_messages(request)
        body: Dict[str, Any] = {
            "model": request.model_id,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": stream,
        }

        if request.tools:
            body["tools"] = [{"type": "function", "function": t} for t in request.tools]
            if request.tool_choice:
                body["tool_choice"] = request.tool_choice

        if request.output_schema:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"schema": request.output_schema},
            }

        return body

    def _format_messages(self, request: NormalizedRequest) -> List[Dict[str, Any]]:
        msgs: List[Dict[str, Any]] = []
        if request.system_prompt:
            msgs.append({"role": "system", "content": request.system_prompt})
        for msg in request.messages:
            entry: Dict[str, Any] = {"role": msg.role, "content": msg.content}
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            msgs.append(entry)
        return msgs

    # -- Internal: response parsing --------------------------------------------

    def _parse_response(
        self,
        data: Dict[str, Any],
        request: NormalizedRequest,
    ) -> ProviderResponse:
        choices = data.get("choices", [])
        if not choices:
            raise ProviderError(
                "No choices in vLLM response",
                provider_id="vllm",
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

    def _auth_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

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
        raise ProviderError(
            f"vLLM API error ({status}): {msg}",
            provider_id="vllm",
            request_id=request.trace_id,
        )

    def set_api_key(self, key: str) -> None:
        """Set API key (optional for vLLM -- only if --api-key is used)."""
        self._api_key = key


__all__ = ["VLLMPlugin"]
