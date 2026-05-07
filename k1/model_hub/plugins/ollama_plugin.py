"""Ollama provider plugin [F25].

Maps NormalizedRequest -> Ollama native API -> ProviderResponse.
API reference verified against https://github.com/ollama/ollama/blob/main/docs/api.md (2026-03-31).

Key API details:
  - Native API at /api/chat (NDJSON streaming)
  - Embeddings: POST /api/embed -> embeddings[] array
  - Token counts: prompt_eval_count/eval_count from response
  - Health: GET / -> "Ollama is running"
  - Tool calling: tools with {type: function, function: {name, description, parameters}}
    response has tool_calls[].function.{name, arguments(object NOT string)}
  - Streaming: NDJSON, each line is JSON with message.content, final has done:true
  - Auth: none
  - Images: base64 in message.images[]
  - Options: temperature -> options.temperature, max_tokens -> options.num_predict
  - keep_alive for model management
  - tool_choice NOT supported on OpenAI compat endpoint

Import graph (Layer 4 -- plugin)
---------------------------------
k1.model_hub.plugins.ollama_plugin
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


class OllamaPlugin:
    """Ollama provider plugin implementing IProviderPlugin.

    Uses Ollama's native /api/chat endpoint with NDJSON streaming
    (NOT the OpenAI compat endpoint, which lacks tool_choice support).

    Supports: CHAT, TOOL_CALL, VISION, EMBED.
    """

    def __init__(self) -> None:
        self._manifest: Optional[ProviderManifest] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._capabilities: set[CapabilityType] = set()
        self._api_base: str = ""

    # -- Lifecycle -------------------------------------------------------------

    async def initialize(self, manifest: ProviderManifest) -> None:
        self._manifest = manifest
        self._api_base = manifest.api_base or "http://localhost:11434"
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
        data = await self._post("/api/chat", body, request)
        return self._parse_response(data, request)

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        body = self._build_body(request, stream=True)
        url = f"{self._api_base}/api/chat"

        async with self._get_session().post(url, json=body) as resp:
            if resp.status != 200:
                text = await resp.text()
                self._raise_for_status(resp.status, text, request)

            # NDJSON: each line is a JSON object
            async for line in resp.content:
                decoded = line.decode("utf-8").strip()
                if not decoded:
                    continue

                chunk_data = json.loads(decoded)
                done = chunk_data.get("done", False)
                message = chunk_data.get("message", {})
                content = message.get("content", "")

                tool_calls = self._parse_tool_calls(message.get("tool_calls"))

                yield ProviderChunk(
                    text=content,
                    done=done,
                    tool_calls=tool_calls,
                    metadata=(
                        {
                            "prompt_eval_count": chunk_data.get("prompt_eval_count", 0),
                            "eval_count": chunk_data.get("eval_count", 0),
                        }
                        if done
                        else None
                    ),
                )

    def estimate_tokens(self, messages: List[Message]) -> int:
        total = 0
        for msg in messages:
            total += 4
            total += len(msg.content) // 4
        total += 2
        return total

    async def health_check(self) -> ProviderHealth:
        """Ollama health: GET / returns 'Ollama is running'."""
        try:
            url = self._api_base.rstrip("/")
            async with self._get_session().get(url) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    if "Ollama is running" in text:
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
            "stream": stream,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }

        if request.tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.get("name", ""),
                        "description": t.get("description", ""),
                        "parameters": t.get("parameters", {}),
                    },
                }
                for t in request.tools
            ]

        if request.extra.get("keep_alive"):
            body["keep_alive"] = request.extra["keep_alive"]

        if request.output_schema:
            body["format"] = "json"

        return body

    def _format_messages(self, request: NormalizedRequest) -> List[Dict[str, Any]]:
        msgs: List[Dict[str, Any]] = []
        if request.system_prompt:
            msgs.append({"role": "system", "content": request.system_prompt})
        for msg in request.messages:
            entry: Dict[str, Any] = {"role": msg.role, "content": msg.content}
            # Vision: base64 images in images field
            if msg.role == "user" and request.extra.get("images"):
                entry["images"] = request.extra["images"]
            msgs.append(entry)
        return msgs

    # -- Internal: response parsing --------------------------------------------

    def _parse_response(
        self,
        data: Dict[str, Any],
        request: NormalizedRequest,
    ) -> ProviderResponse:
        message = data.get("message", {})
        content = message.get("content", "")
        tool_calls = self._parse_tool_calls(message.get("tool_calls"))

        finish = FinishReason.STOP
        if tool_calls:
            finish = FinishReason.TOOL_CALLS
        elif data.get("done_reason") == "length":
            finish = FinishReason.LENGTH

        return ProviderResponse(
            text=content,
            tool_calls=tool_calls,
            prompt_tokens=data.get("prompt_eval_count", 0),
            completion_tokens=data.get("eval_count", 0),
            model_id=data.get("model", request.model_id),
            finish_reason=finish,
            raw_response=data,
        )

    def _parse_tool_calls(
        self,
        tool_calls: Optional[List[Dict[str, Any]]],
    ) -> Optional[List[ToolCallResult]]:
        """Parse Ollama tool calls.

        NOTE: Ollama returns arguments as an OBJECT (not JSON string).
        """
        if not tool_calls:
            return None
        results = []
        for idx, tc in enumerate(tool_calls):
            fn = tc.get("function", {})
            tc_name = fn.get("name") or "unknown"
            args = fn.get("arguments", {})
            # Ollama returns arguments as object, not string -- serialize
            if isinstance(args, dict):
                args_str = json.dumps(args)
            elif isinstance(args, str):
                args_str = args
            else:
                args_str = json.dumps(args)
            results.append(
                ToolCallResult(
                    id=f"ollama_tc_{idx}",
                    name=tc_name,
                    arguments=args_str,
                )
            )
        return results

    # -- Internal: HTTP --------------------------------------------------------

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

        async with self._get_session().post(url, json=body) as resp:
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
        raise ProviderError(
            f"Ollama API error ({status}): {text}",
            provider_id="ollama",
            request_id=request.trace_id,
        )

    def set_api_key(self, key: str) -> None:
        """No-op: Ollama does not use API keys."""
        pass


__all__ = ["OllamaPlugin"]
