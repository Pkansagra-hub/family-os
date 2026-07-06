"""DeepSeek provider plugin — httpx-based, subclass of OpenAIPlugin.

DeepSeek API is OpenAI-compatible.  This plugin uses a synchronous httpx
client dispatched through ``loop.run_in_executor`` (same pattern as
GooglePlugin), so HTTP I/O never touches the event loop directly.  That
makes the plugin safe to call from daemon threads, secondary event loops,
and Python 3.13+ without cross-loop aiohttp errors.

Key differences from standard OpenAI:
  - Base URL: https://api.deepseek.com (no /v1)
  - max_tokens (NOT max_completion_tokens)
  - thinking param: {"type": "enabled"} for reasoning mode
  - Always system role (no developer role)
  - stream_options supported (include_usage works)
  - DEEPSEEK_MODEL env var for model override
  - reasoning_content returned in responses; must be preserved across
    multi-turn tool-call conversations per DeepSeek API docs.

API reference: https://api-docs.deepseek.com (2026-06-20).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import queue as _queue_mod
import threading as _threading_mod
from dataclasses import replace
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from k1.model_hub.plugins.base import (
    NormalizedRequest,
    ProviderChunk,
    ProviderResponse,
)
from k1.model_hub.plugins.openai_plugin import OpenAIPlugin
from k1.model_hub.types import (
    FinishReason,
    ProviderError,
    RateLimitError,
    ToolCallResult,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reasoning-model set (thinking mode enabled)
# ---------------------------------------------------------------------------
# Per 2026-06-20 API docs:
#   deepseek-v4-pro  – thinking mode supported (default enabled)
#   deepseek-v4-flash – thinking mode supported (default enabled)
#   deepseek-chat    – non-thinking alias for v4-flash (deprecated 2026-07-24)
#   deepseek-reasoner – thinking alias for v4-flash (deprecated 2026-07-24)
_DEEPSEEK_REASONING_MODELS = frozenset(
    {
        "deepseek-v4-pro",
        "deepseek-v4-flash",
        "deepseek-chat",
        "deepseek-reasoner",
    }
)

# Timeout for httpx sync client (total, not per-operation).
_HTTPX_TIMEOUT_S = 120.0


class DeepSeekPlugin(OpenAIPlugin):
    """DeepSeek provider plugin — httpx + run_in_executor (loop-agnostic).

    Overrides OpenAI-specific API differences for DeepSeek compatibility.
    HTTP is synchronous (httpx) and dispatched via ``run_in_executor`` so
    the plugin is safe from any event loop, including daemon threads.
    """

    # -- Lifecycle ---------------------------------------------------------

    async def initialize(self, manifest) -> None:
        """Store manifest + api_base."""
        from k1.model_hub.manifest import ProviderManifest

        self._manifest: ProviderManifest = manifest
        self._api_base = (manifest.api_base or "https://api.deepseek.com").rstrip("/")
        self._capabilities = set(manifest.capabilities)
        for model in manifest.models:
            self._capabilities.update(model.capabilities)

    async def close(self) -> None:
        pass  # No persistent resources; httpx clients are per-request.

    def _ensure_client(self) -> httpx.Client:
        """Return a thread-safe httpx.Client.

        httpx.Client is NOT thread-safe, so each call gets a fresh
        instance.  This is cheap — the client is just a connection-pool
        wrapper with timeouts.
        """
        return httpx.Client(
            headers={"Content-Type": "application/json"},
            timeout=httpx.Timeout(_HTTPX_TIMEOUT_S),
        )

    # -- Model resolution --------------------------------------------------

    def _resolve_model_id(self, request: NormalizedRequest) -> str:
        return os.environ.get("DEEPSEEK_MODEL") or request.model_id

    # -- Execute (sync httpx via run_in_executor) --------------------------

    async def execute(self, request: NormalizedRequest) -> ProviderResponse:
        model_id = self._resolve_model_id(request)
        if model_id != request.model_id:
            request = replace(request, model_id=model_id)
        body = self._build_chat_body(request, stream=False)
        url = f"{self._api_base}/chat/completions"
        headers = self._auth_headers(request)

        loop = asyncio.get_running_loop()

        def _call() -> httpx.Response:
            with self._ensure_client() as client:
                return client.post(url, json=body, headers=headers)

        try:
            resp = await loop.run_in_executor(None, _call)
        except Exception as exc:
            raise ProviderError(
                f"DeepSeek API error: {exc}",
                provider_id="deepseek",
                request_id=request.trace_id,
            ) from exc

        if resp.status_code != 200:
            logger.error(
                "DeepSeek API error (%s) trace=%s body=%s",
                resp.status_code,
                request.trace_id,
                resp.text[:500],
            )
            self._raise_for_status(resp.status_code, resp.text, request)

        data = resp.json()
        return self._parse_chat_response(data, request)

    # -- Stream execute (sync httpx stream via producer thread + queue) ----

    async def stream_execute(self, request: NormalizedRequest) -> AsyncIterator[ProviderChunk]:
        model_id = self._resolve_model_id(request)
        if model_id != request.model_id:
            request = replace(request, model_id=model_id)
        body = self._build_chat_body(request, stream=True)
        body["stream_options"] = {"include_usage": True}  # supported per docs

        url = f"{self._api_base}/chat/completions"
        headers = self._auth_headers(request)

        _SENTINEL = object()
        chunk_queue: _queue_mod.Queue = _queue_mod.Queue()

        def _produce() -> None:
            try:
                with self._ensure_client() as client:
                    with client.stream("POST", url, json=body, headers=headers) as resp:
                        if resp.status_code != 200:
                            chunk_queue.put(
                                ProviderError(
                                    f"DeepSeek API error ({resp.status_code}): {resp.text}",
                                    provider_id="deepseek",
                                    request_id=request.trace_id,
                                )
                            )
                            return
                        for line in resp.iter_lines():
                            if not line or not line.startswith("data:"):
                                continue
                            payload = line[len("data:") :].strip()
                            if payload == "[DONE]":
                                break
                            if not payload:
                                continue
                            try:
                                chunk_queue.put(json.loads(payload))
                            except json.JSONDecodeError:
                                logger.debug(
                                    "DeepSeek stream: skipping non-JSON line: %s",
                                    line[:120],
                                )
            except Exception as exc:
                chunk_queue.put(exc)
            finally:
                chunk_queue.put(_SENTINEL)

        loop = asyncio.get_running_loop()
        _threading_mod.Thread(target=_produce, daemon=True).start()

        _pending_finish = False
        _pending_tool_calls: Optional[List[ToolCallResult]] = None

        while True:
            item = await loop.run_in_executor(None, chunk_queue.get)
            if item is _SENTINEL:
                break
            if isinstance(item, BaseException):
                if isinstance(item, ProviderError):
                    raise item
                raise ProviderError(
                    f"DeepSeek stream error: {item}",
                    provider_id="deepseek",
                    request_id=request.trace_id,
                ) from item

            # item is a dict (JSON chunk)
            chunk_data = item
            choices = chunk_data.get("choices", [])
            if not choices:
                usage = chunk_data.get("usage") or {}
                if _pending_finish or usage:
                    yield ProviderChunk(
                        text="",
                        done=True,
                        tool_calls=_pending_tool_calls,
                        prompt_tokens=int(usage.get("prompt_tokens", 0)),
                        completion_tokens=int(usage.get("completion_tokens", 0)),
                    )
                    _pending_finish = False
                    _pending_tool_calls = None
                continue

            delta = choices[0].get("delta", {})
            content = delta.get("content", "")
            finish = choices[0].get("finish_reason")

            tool_calls = self._parse_delta_tool_calls(delta)

            if finish is not None:
                _pending_finish = True
                _pending_tool_calls = tool_calls
                if content:
                    yield ProviderChunk(text=content, done=False)
            else:
                yield ProviderChunk(
                    text=content or "",
                    done=False,
                    tool_calls=tool_calls,
                )

        if _pending_finish:
            yield ProviderChunk(text="", done=True, tool_calls=_pending_tool_calls)

    # -- Request building --------------------------------------------------

    def _build_chat_body(self, request: NormalizedRequest, *, stream: bool) -> Dict[str, Any]:
        is_reasoning = self._is_reasoning_model(request.model_id)
        messages = self._format_messages(request)
        body: Dict[str, Any] = {
            "model": request.model_id,
            "messages": messages,
            "stream": stream,
        }
        body["max_tokens"] = request.max_tokens
        if not is_reasoning:
            body["temperature"] = request.temperature
        if is_reasoning:
            body["thinking"] = {"type": "enabled"}
            if request.reasoning_effort:
                body["reasoning_effort"] = request.reasoning_effort
        if request.tools:
            body["tools"] = [{"type": "function", "function": t} for t in request.tools]
            # DeepSeek thinking mode rejects explicit tool_choice (returns
            # 400: "Thinking mode does not support this tool_choice").
            # Omit it when thinking is enabled; the API defaults to "auto"
            # which still triggers tool calls when tools are present.
            if request.tool_choice and not is_reasoning:
                body["tool_choice"] = request.tool_choice
        if request.extra.get("response_format"):
            body["response_format"] = request.extra["response_format"]
        return body

    def _format_messages(self, request: NormalizedRequest) -> List[Dict[str, Any]]:
        msgs: List[Dict[str, Any]] = []
        if request.system_prompt:
            msgs.append({"role": "system", "content": request.system_prompt})
        # Per-msg reasoning_content map (keyed by index) for multi-turn
        # tool-call conversations where reasoning_content must be preserved
        # across requests (DeepSeek API docs).
        rc_map: Dict[int, str] = request.extra.get("_reasoning_content", {}) or {}
        for i, msg in enumerate(request.messages):
            entry: Dict[str, Any] = {"role": msg.role}
            entry["content"] = msg.content if msg.content else None
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            if msg.name:
                entry["name"] = msg.name
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": (
                                tc.arguments
                                if isinstance(tc.arguments, str)
                                else json.dumps(tc.arguments, ensure_ascii=False)
                            ),
                        },
                    }
                    for tc in msg.tool_calls
                ]
                # Per DeepSeek API docs: reasoning_content MUST be passed
                # back for assistant messages that contain tool_calls.
                rc = rc_map.get(i)
                if rc:
                    entry["reasoning_content"] = rc
            msgs.append(entry)
        return msgs

    def _is_reasoning_model(self, model_id: str) -> bool:
        if model_id in _DEEPSEEK_REASONING_MODELS:
            return True
        for prefix in (
            "deepseek-v4-pro",
            "deepseek-v4-flash",
            "deepseek-chat",
            "deepseek-reasoner",
        ):
            if model_id.startswith(prefix):
                return True
        return False

    # -- Response parsing --------------------------------------------------

    def _parse_chat_response(
        self,
        data: Dict[str, Any],
        request: NormalizedRequest,
    ) -> ProviderResponse:
        """Parse DeepSeek response, extracting reasoning_content for multi-turn."""
        choices = data.get("choices", [])
        if not choices:
            raise ProviderError(
                "No choices in DeepSeek response",
                provider_id="deepseek",
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

        # Preserve reasoning_content in raw_response for multi-turn callers.
        raw = dict(data)
        raw.setdefault("_reasoning_content", message.get("reasoning_content") or "")

        return ProviderResponse(
            text=message.get("content", "") or "",
            tool_calls=tool_calls,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            model_id=data.get("model", request.model_id),
            finish_reason=finish,
            raw_response=raw,
        )

    # -- Error handling ----------------------------------------------------

    def _raise_for_status(self, status: int, text: str, request: NormalizedRequest) -> None:
        try:
            err = json.loads(text).get("error", {})
            msg = err.get("message", text)
        except (json.JSONDecodeError, AttributeError):
            msg = text
        if status == 429:
            raise RateLimitError(
                f"DeepSeek rate limited: {msg}",
                provider_id="deepseek",
                request_id=request.trace_id,
            )
        raise ProviderError(
            f"DeepSeek API error ({status}): {msg}",
            provider_id="deepseek",
            request_id=request.trace_id,
        )


# Re-export from parent for local use.
_FINISH_MAP = {
    "stop": FinishReason.STOP,
    "length": FinishReason.LENGTH,
    "tool_calls": FinishReason.TOOL_CALLS,
    "error": FinishReason.ERROR,
    "safety": FinishReason.SAFETY,
}


__all__ = ["DeepSeekPlugin"]
