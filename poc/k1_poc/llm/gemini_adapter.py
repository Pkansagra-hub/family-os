"""
GeminiConciergeAdapter -- Gemini Provider Implementation
=========================================================

V2 Design Ref: Section 10.9 (GeminiConciergeAdapter)
API Ref: google-genai SDK (genai.Client)

This is the ONLY class that imports google.genai.
All provider-specific translation happens here:
  - ModelMessage -> Gemini Content/Part
  - ToolSchema -> Gemini FunctionDeclaration
  - Gemini response -> ConciergeModelResponse
  - tool_choice -> Gemini ToolConfig
  - Streaming via generate_content_stream
  - JSON mode via response_mime_type + response_json_schema
  - Thinking config via ThinkingConfig
  - Timeout enforcement via asyncio.wait_for
  - Concurrent batch via asyncio.gather
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator
from uuid import uuid4

from poc.k1_poc.llm.model_selection import select_model
from poc.k1_poc.llm.types import (
    Capability,
    ConciergeModelRequest,
    ConciergeModelResponse,
    FinishReason,
    StreamChunk,
    ThinkingLevel,
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


# ---------------------------------------------------------------------------
# GeminiConciergeAdapter
# ---------------------------------------------------------------------------


class GeminiConciergeAdapter:
    """IConciergeModelPort implementation for Google Gemini.

    This is the ONLY class that imports google.genai.
    All provider-specific translation happens here.

    Features:
      - generate()        : single completion with tool calling
      - generate_stream() : streaming text deltas + tool calls
      - generate_json()   : structured JSON output (JSON mode)
      - generate_batch()  : concurrent batch of independent requests
      - Thinking config   : control thinking budget per request
      - Model selection   : capability-based model routing
      - Timeout           : asyncio.wait_for enforcement
      - Token tracking    : usage metadata extraction
    """

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str | None = None,
    ):
        """Initialize with API key.

        Args:
            api_key: Google AI API key. If None, reads GOOGLE_API_KEY env var.
            default_model: Fallback model when selection table has no match.
                If None, reads from central config.
        """
        genai, types = _ensure_genai()

        import os

        from poc.k1_poc.config import get_config

        resolved_key = api_key or os.getenv("GOOGLE_API_KEY", "")
        if not resolved_key:
            raise ValueError("API key required. Pass api_key= or set GOOGLE_API_KEY env var.")

        self._client = genai.Client(api_key=resolved_key)
        self._default_model = (
            default_model if default_model is not None else get_config().llm.default_model
        )
        logger.info(
            "GeminiConciergeAdapter initialised  default_model=%s",
            self._default_model,
        )

    # ------------------------------------------------------------------
    # Public: generate (single call)
    # ------------------------------------------------------------------

    async def generate(self, request: ConciergeModelRequest) -> ConciergeModelResponse:
        """Single LLM inference call. Returns complete response."""
        logger.info(
            "GeminiConciergeAdapter.generate  actor=%s scenario=%s capability=%s "
            "tool_choice=%s tools=%d messages=%d timeout=%dms",
            request.actor,
            request.scenario,
            request.capability,
            request.tool_choice,
            len(request.tools) if request.tools else 0,
            len(request.messages) if request.messages else 0,
            request.timeout_ms,
        )

        # --- DIAGNOSTIC: dump what the LLM actually sees ---
        logger.info(
            "DIAG PROMPT (first 500 chars): %s",
            (request.system_prompt or "")[:500],
        )
        if request.messages:
            for _mi, _mm in enumerate(request.messages):
                _tc_summary = ""
                if _mm.tool_calls:
                    _tc_summary = f" tool_calls=[{', '.join(tc.name for tc in _mm.tool_calls)}]"
                logger.info(
                    "DIAG MSG[%d] role=%s len=%d%s content=%s",
                    _mi,
                    _mm.role,
                    len(_mm.content) if _mm.content else 0,
                    _tc_summary,
                    (_mm.content or "")[:120],
                )
        if request.tools:
            logger.info(
                "DIAG TOOLS: %s",
                [t.name for t in request.tools],
            )
        _, types = _ensure_genai()

        model = self._select_model(request)
        contents = self._to_gemini_contents(request.messages)
        gemini_tools = self._to_gemini_tools(request.tools) if request.tools else None
        config = self._build_config(request, gemini_tools, types)

        start_ms = _now_ms()
        try:
            response = await asyncio.wait_for(
                self._async_generate(model, contents, config),
                timeout=request.timeout_ms / 1000.0,
            )
        except asyncio.TimeoutError:
            elapsed = _now_ms() - start_ms
            logger.warning(
                "Gemini timeout after %dms (limit=%dms) model=%s actor=%s",
                elapsed,
                request.timeout_ms,
                model,
                request.actor,
            )
            return ConciergeModelResponse(
                text="",
                model_id=model,
                latency_ms=elapsed,
                finish_reason=FinishReason.ERROR,
            )
        except Exception as exc:
            elapsed = _now_ms() - start_ms
            # Distinguish quota exhaustion from transient errors.
            exc_str = str(exc)
            is_quota = "RESOURCE_EXHAUSTED" in exc_str or "429" in exc_str
            if is_quota:
                logger.error(
                    "Gemini QUOTA EXHAUSTED: %s model=%s actor=%s -- "
                    "check API key, project billing, or model availability",
                    exc,
                    model,
                    request.actor,
                )
            else:
                logger.error(
                    "Gemini error: %s model=%s actor=%s",
                    exc,
                    model,
                    request.actor,
                    exc_info=True,
                )
            return ConciergeModelResponse(
                text="",
                model_id=model,
                latency_ms=elapsed,
                finish_reason=FinishReason.ERROR,
            )

        elapsed = _now_ms() - start_ms
        result = self._normalize(response, model)
        result.latency_ms = elapsed

        logger.info(
            "GeminiConciergeAdapter.generate done  actor=%s model=%s latency=%dms finish=%s "
            "has_text=%s has_tools=%d thought_len=%d tokens_in=%d tokens_out=%d tokens_thought=%d",
            request.actor,
            model,
            elapsed,
            result.finish_reason,
            result.has_text,
            len(result.tool_calls),
            len(result.thought_text),
            result.tokens_in,
            result.tokens_out,
            result.tokens_thoughts,
        )

        # Parse JSON output for STRUCTURED capability
        if request.capability == Capability.STRUCTURED and result.has_text:
            try:
                result.json_output = json.loads(result.text)
            except json.JSONDecodeError:
                logger.warning("STRUCTURED response not valid JSON: %.100s", result.text)

        return result

    # ------------------------------------------------------------------
    # Public: generate_stream (streaming)
    # ------------------------------------------------------------------

    async def generate_stream(self, request: ConciergeModelRequest) -> AsyncIterator[StreamChunk]:
        """Streaming LLM inference. Yields text deltas then done.

        Runs the sync streaming iterator in a thread executor so the
        event loop is not blocked.  Enforces the same timeout_ms as
        the non-streaming generate() path.
        """
        _, types = _ensure_genai()

        model = self._select_model(request)
        contents = self._to_gemini_contents(request.messages)
        gemini_tools = self._to_gemini_tools(request.tools) if request.tools else None
        config = self._build_config(request, gemini_tools, types)

        start_ms = _now_ms()
        accumulated_text = ""
        accumulated_thought = ""
        tool_calls: list[ToolCallResult] = []
        tokens_in = 0
        tokens_out = 0
        tokens_thoughts = 0
        finish_reason = FinishReason.STOP

        # Accumulate raw Part objects so we can reconstruct a Content
        # that preserves thought_signature fields.  Gemini 3 requires
        # these signatures in function-call round-trips; without them
        # the next generate() call fails with 400 INVALID_ARGUMENT.
        raw_parts: list = []

        timeout_s = request.timeout_ms / 1000.0

        try:
            # Collect all chunks from the sync stream in an executor
            # so we don't block the event loop AND can enforce a timeout.
            loop = asyncio.get_event_loop()
            all_chunks: list = await asyncio.wait_for(
                loop.run_in_executor(
                    None, lambda: list(self._sync_stream(model, contents, config))
                ),
                timeout=timeout_s,
            )

            for chunk in all_chunks:
                if not chunk.candidates:
                    continue

                candidate = chunk.candidates[0]
                if not candidate.content or not candidate.content.parts:
                    continue

                for part in candidate.content.parts:
                    # Accumulate raw parts to preserve thought_signature
                    raw_parts.append(part)
                    # Thinking text
                    if getattr(part, "thought", False) and hasattr(part, "text") and part.text:
                        accumulated_thought += part.text
                        yield StreamChunk(
                            chunk_type="thought_delta",
                            thought_text=part.text,
                        )
                    # Regular text
                    elif (
                        hasattr(part, "text") and part.text and not getattr(part, "thought", False)
                    ):
                        accumulated_text += part.text
                        yield StreamChunk(
                            chunk_type="text_delta",
                            text=part.text,
                        )
                    # Function call
                    elif hasattr(part, "function_call") and part.function_call:
                        fc = part.function_call
                        tc = ToolCallResult(
                            id=f"call_{uuid4().hex[:8]}",
                            name=fc.name,
                            arguments=dict(fc.args) if fc.args else {},
                        )
                        tool_calls.append(tc)
                        finish_reason = FinishReason.TOOL_CALLS
                        yield StreamChunk(
                            chunk_type="tool_call_delta",
                            tool_call_partial=tc,
                        )

                # Extract usage metadata from chunk if available
                if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                    um = chunk.usage_metadata
                    if hasattr(um, "prompt_token_count") and um.prompt_token_count:
                        tokens_in = um.prompt_token_count
                    if hasattr(um, "candidates_token_count") and um.candidates_token_count:
                        tokens_out = um.candidates_token_count
                    if hasattr(um, "thoughts_token_count") and um.thoughts_token_count:
                        tokens_thoughts = um.thoughts_token_count

        except asyncio.TimeoutError:
            elapsed = _now_ms() - start_ms
            logger.warning(
                "Gemini stream timeout after %dms (limit=%dms) model=%s actor=%s",
                elapsed,
                request.timeout_ms,
                model,
                request.actor,
            )
            finish_reason = FinishReason.ERROR

        except Exception as exc:
            logger.error("Gemini stream error: %s", exc, exc_info=True)
            finish_reason = FinishReason.ERROR

        elapsed = _now_ms() - start_ms

        # Build a synthetic Content object from accumulated raw parts so
        # thought_signature fields survive the round-trip.  This is used
        # by _to_gemini_contents via ModelMessage._raw_provider_content.
        raw_content = None
        if raw_parts:
            raw_content = types.Content(role="model", parts=raw_parts)

        # Final done chunk with complete response
        final_response = ConciergeModelResponse(
            text=accumulated_text,
            tool_calls=tool_calls,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            tokens_thoughts=tokens_thoughts,
            latency_ms=elapsed,
            model_id=model,
            finish_reason=finish_reason,
            thought_text=accumulated_thought,
            _raw_provider_content=raw_content,
        )

        if request.capability == Capability.STRUCTURED and accumulated_text:
            try:
                final_response.json_output = json.loads(accumulated_text)
            except json.JSONDecodeError:
                pass

        yield StreamChunk(chunk_type="done", response=final_response)

    # ------------------------------------------------------------------
    # Public: generate_json (structured output -- JSON mode)
    # ------------------------------------------------------------------

    async def generate_json(
        self,
        request: ConciergeModelRequest,
        schema: dict[str, Any] | None = None,
    ) -> ConciergeModelResponse:
        """Generate structured JSON output using Gemini's JSON mode.

        If request.response_schema is set, it's used.
        Otherwise the explicit schema parameter is used.
        Falls back to plain JSON mode without schema validation.
        """
        # Override capability and schema if needed
        effective_schema = request.response_schema or schema

        # Create a modified request with STRUCTURED capability
        from dataclasses import replace

        modified = replace(
            request,
            capability=Capability.STRUCTURED,
            response_schema=effective_schema,
            tools=None,  # no tools in JSON mode
            tool_choice="none",
        )
        return await self.generate(modified)

    # ------------------------------------------------------------------
    # Public: generate_batch (concurrent requests)
    # ------------------------------------------------------------------

    async def generate_batch(
        self,
        requests: list[ConciergeModelRequest],
        max_concurrency: int | None = None,
    ) -> list[ConciergeModelResponse]:
        """Execute multiple independent LLM requests concurrently.

        Uses asyncio.Semaphore to limit concurrency. Useful for:
          - Parallel tool result processing
          - Multi-agent concurrent reasoning
          - Batch classification/extraction
        """
        from poc.k1_poc.config import get_config

        if max_concurrency is None:
            max_concurrency = get_config().llm.batch_max_concurrency
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _bounded(req: ConciergeModelRequest) -> ConciergeModelResponse:
            async with semaphore:
                return await self.generate(req)

        return await asyncio.gather(*[_bounded(r) for r in requests])

    # ------------------------------------------------------------------
    # Internal: model selection
    # ------------------------------------------------------------------

    def _select_model(self, request: ConciergeModelRequest) -> str:
        """Select model based on capability, actor, and hint."""
        return select_model(
            capability=request.capability,
            actor=request.actor,
            hint=request.model_hint,
            default=self._default_model,
        )

    # ------------------------------------------------------------------
    # Internal: build Gemini config
    # ------------------------------------------------------------------

    def _build_config(self, request: ConciergeModelRequest, gemini_tools, types):
        """Build GenerateContentConfig from request."""
        config_kwargs: dict[str, Any] = {}

        # System instruction
        if request.system_prompt:
            config_kwargs["system_instruction"] = request.system_prompt

        # Tools
        if gemini_tools:
            config_kwargs["tools"] = gemini_tools

        # Tool config (calling mode)
        if gemini_tools:
            config_kwargs["tool_config"] = self._tool_config(request.tool_choice, types)

        # Temperature
        config_kwargs["temperature"] = request.temperature

        # Max output tokens
        config_kwargs["max_output_tokens"] = request.max_tokens

        # Stop sequences
        if request.stop_sequences:
            config_kwargs["stop_sequences"] = request.stop_sequences

        # JSON mode (STRUCTURED capability)
        if request.capability == Capability.STRUCTURED:
            config_kwargs["response_mime_type"] = "application/json"
            if request.response_schema:
                config_kwargs["response_json_schema"] = request.response_schema

        # Thinking config
        if request.thinking is not None and request.thinking != ThinkingLevel.NONE:
            config_kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_level=request.thinking.value,
            )

        return types.GenerateContentConfig(**config_kwargs)

    # ------------------------------------------------------------------
    # Internal: content conversion
    # ------------------------------------------------------------------

    def _to_gemini_contents(self, messages: list) -> list:
        """Convert ModelMessage list to Gemini Content objects.

        Consecutive tool-result messages are merged into a single
        Content(role="user") with multiple FunctionResponse parts.
        Gemini requires this grouping so the model understands that
        the function results correspond to the parallel function
        calls it made in the preceding model turn.  Without merging,
        each tool result looks like a separate user turn, which
        teaches the model to call one tool at a time.
        """
        _, types = _ensure_genai()
        contents = []

        # Accumulator for consecutive tool-result parts
        _pending_tool_parts: list = []

        def _flush_tool_parts() -> None:
            """Emit a single Content with all accumulated FunctionResponse parts."""
            if _pending_tool_parts:
                contents.append(types.Content(role="user", parts=list(_pending_tool_parts)))
                _pending_tool_parts.clear()

        for msg in messages:
            if msg.role == "system":
                # System messages are handled via system_instruction, skip
                continue
            elif msg.role == "user":
                _flush_tool_parts()
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=msg.content)],
                    )
                )
            elif msg.role == "assistant":
                _flush_tool_parts()
                # Prefer the raw provider Content (preserves thought
                # signatures required by Gemini 3 function calling).
                if getattr(msg, "_raw_provider_content", None) is not None:
                    contents.append(msg._raw_provider_content)
                else:
                    parts = []
                    if msg.content:
                        parts.append(types.Part.from_text(text=msg.content))
                    # If assistant made tool calls, append them as function_call parts
                    if msg.tool_calls:
                        for tc in msg.tool_calls:
                            parts.append(
                                types.Part(
                                    function_call=types.FunctionCall(
                                        name=tc.name,
                                        args=tc.arguments,
                                    )
                                )
                            )
                    if parts:
                        contents.append(types.Content(role="model", parts=parts))
            elif msg.role == "tool":
                # Accumulate tool results -- they will be flushed as a
                # single Content(role="user") with multiple FunctionResponse
                # parts when the next non-tool message appears (or at end).
                try:
                    result_data = json.loads(msg.content)
                except (json.JSONDecodeError, TypeError):
                    result_data = {"result": msg.content}

                _pending_tool_parts.append(
                    types.Part.from_function_response(
                        name=msg.name or "unknown_tool",
                        response=result_data,
                    )
                )

        # Flush any remaining tool parts at the end of the message list
        _flush_tool_parts()

        return contents

    # ------------------------------------------------------------------
    # Internal: tool schema conversion
    # ------------------------------------------------------------------

    def _to_gemini_tools(self, tools: list) -> list:
        """Convert ToolSchema list to Gemini FunctionDeclaration list."""
        _, types = _ensure_genai()

        func_decls = []
        for tool in tools:
            func_decls.append(
                types.FunctionDeclaration(
                    name=tool.name,
                    description=tool.description,
                    parameters_json_schema=tool.parameters,
                )
            )
        return [types.Tool(function_declarations=func_decls)]

    # ------------------------------------------------------------------
    # Internal: tool_config (calling mode)
    # ------------------------------------------------------------------

    def _tool_config(self, tool_choice: str, types) -> Any:
        """Convert tool_choice string to Gemini ToolConfig."""
        mode_map = {
            "auto": "AUTO",
            "required": "ANY",
            "none": "NONE",
        }

        mode = mode_map.get(tool_choice, "AUTO")

        # If tool_choice is a specific function name, use ANY with allowed list
        allowed = None
        if tool_choice not in mode_map and tool_choice:
            mode = "ANY"
            allowed = [tool_choice]

        config_kwargs: dict[str, Any] = {"mode": mode}
        if allowed:
            config_kwargs["allowed_function_names"] = allowed

        return types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(**config_kwargs)
        )

    # ------------------------------------------------------------------
    # Internal: response normalization
    # ------------------------------------------------------------------

    def _normalize(self, response, model: str) -> ConciergeModelResponse:
        """Convert Gemini response to ConciergeModelResponse."""
        text = ""
        tool_calls = []
        thought_text = ""

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
                                name=fc.name,
                                arguments=dict(fc.args) if fc.args else {},
                            )
                        )
                    else:
                        logger.debug(
                            "GeminiAdapter._normalize: unhandled part type=%s",
                            type(part).__name__,
                        )
            else:
                logger.warning(
                    "GeminiAdapter._normalize: candidate has no content/parts "
                    "(finish_reason=%s)",
                    getattr(candidate, "finish_reason", "unknown"),
                )
        else:
            logger.warning("GeminiAdapter._normalize: response has no candidates")

        # Extract token usage
        tokens_in = 0
        tokens_out = 0
        tokens_thoughts = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            um = response.usage_metadata
            tokens_in = getattr(um, "prompt_token_count", 0) or 0
            tokens_out = getattr(um, "candidates_token_count", 0) or 0
            tokens_thoughts = getattr(um, "thoughts_token_count", 0) or 0

        # Determine finish reason
        finish_reason = FinishReason.STOP
        if tool_calls:
            finish_reason = FinishReason.TOOL_CALLS
        elif response.candidates:
            candidate = response.candidates[0]
            fr = getattr(candidate, "finish_reason", None)
            if fr is not None:
                fr_str = str(fr).upper()
                if "STOP" in fr_str:
                    finish_reason = FinishReason.STOP
                elif "MAX_TOKENS" in fr_str or "LENGTH" in fr_str:
                    finish_reason = FinishReason.LENGTH
                elif "SAFETY" in fr_str:
                    finish_reason = FinishReason.SAFETY

        # Preserve the raw Content object so thought signatures survive
        # the round-trip through ModelMessage -> _to_gemini_contents.
        raw_content = None
        if response.candidates:
            raw_content = response.candidates[0].content

        return ConciergeModelResponse(
            text=text,
            tool_calls=tool_calls,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            tokens_thoughts=tokens_thoughts,
            model_id=model,
            finish_reason=finish_reason,
            thought_text=thought_text,
            _raw_provider_content=raw_content,
        )

    # ------------------------------------------------------------------
    # Internal: async wrappers for sync SDK methods
    # ------------------------------------------------------------------

    async def _async_generate(self, model: str, contents: list, config) -> Any:
        """Run sync generate_content in executor for async compatibility."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            ),
        )

    def _sync_stream(self, model: str, contents: list, config) -> Any:
        """Return sync streaming iterator."""
        return self._client.models.generate_content_stream(
            model=model,
            contents=contents,
            config=config,
        )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _now_ms() -> int:
    return int(time.time() * 1000)
