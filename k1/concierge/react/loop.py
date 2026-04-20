"""
Shared ReAct Loop -- react_loop() and ReactResult
==================================================

V2 Design Ref: Section 7.5 (react_loop implementation), 7.4 (ReactResult)

One implementation for both Front and Back actors. Differences are:
  1. Termination: Front=text-without-tools (L1), Back=submit_result (L2)
  2. tool_choice on iteration 0: Front="required", Back="auto"
  3. Text-without-tools: Front=terminal, Back="thinking aloud" (continues)
  4. Cancellation: Front=always False, Back=checks FSMTurnState
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from k1.concierge.config import get_config
from k1.concierge.llm.types import (
    ConciergeModelResponse,
    FinishReason,
    ModelMessage,
    StreamChunk,
    ToolCallResult,
    ToolSchema,
)
from k1.concierge.llm.types import tool_result_to_message as _tool_result_to_msg
from k1.concierge.llm.validator import LLMOutputValidator, ValidationResult
from k1.concierge.task.parallel_safety import classify_tool_batch
from k1.concierge.tools.dispatcher import ToolDispatcher
from k1.concierge.tools.result_protocol import ToolResult
from k1.model_hub.ports import IModelHubPort
from k1.model_hub.types import CapabilityType, ChatPayload, ChatResult
from k1.model_hub.types import FinishReason as K1FinishReason
from k1.model_hub.types import HubChunk, HubRequest, HubResponse
from k1.model_hub.types import Message as K1Message
from k1.model_hub.types import ReasonResult, RequestConstraints, ResponseMetadata, StructuredResult, TokenUsage, ToolCallPayload
from k1.model_hub.types import ToolCallResult as K1ToolCallResult
from k1.model_hub.types import ToolCallResultSet
from k1.model_hub.types import ToolDefinition as K1ToolDefinition

logger = logging.getLogger(__name__)


# =========================================================================
# K1 ↔ POC Type Conversion Helpers (M1 E1.5 — minimal-diff bridge layer)
# =========================================================================


def _to_k1_messages(msgs: list[ModelMessage]) -> list[K1Message]:
    """Convert POC ModelMessages to K1 Messages for HubRequest payloads."""
    out: list[K1Message] = []
    for m in msgs:
        tc = None
        if m.tool_calls:
            tc = [
                K1ToolCallResult(id=c.id, name=c.name, arguments=c.arguments) for c in m.tool_calls
            ]
        out.append(
            K1Message(
                role=m.role,
                content=m.content,
                tool_call_id=m.tool_call_id,
                name=m.name,
                tool_calls=tc,
            )
        )
    return out


def _to_k1_tools(tools: list[ToolSchema]) -> list[K1ToolDefinition]:
    """Convert POC ToolSchemas to K1 ToolDefinitions for HubRequest payloads."""
    return [
        K1ToolDefinition(name=t.name, description=t.description, parameters=t.parameters)
        for t in tools
    ]


def _unwrap_response(hub_resp: HubResponse) -> ConciergeModelResponse:
    """Convert K1 HubResponse back to POC ConciergeModelResponse.

    Allows all existing response field access (response.text,
    response.has_tool_calls, etc.) to remain unchanged.
    """
    result = hub_resp.result
    text = getattr(result, "text", "")
    tool_calls: list[ToolCallResult] = []
    json_output = None
    thought_text = ""

    if isinstance(result, ToolCallResultSet):
        tool_calls = [
            ToolCallResult(
                id=tc.id,
                name=tc.name,
                arguments=(
                    json.loads(tc.arguments) if isinstance(tc.arguments, str) else tc.arguments
                ),
            )
            for tc in result.tool_calls
        ]
    elif isinstance(result, StructuredResult):
        json_output = result.json_output
    elif isinstance(result, ReasonResult):
        thought_text = result.thinking

    m = hub_resp.metadata
    fr = (
        m.finish_reason.value
        if isinstance(m.finish_reason, K1FinishReason)
        else str(m.finish_reason)
    )
    return ConciergeModelResponse(
        text=text,
        tool_calls=tool_calls,
        json_output=json_output,
        thought_text=thought_text,
        tokens_in=m.usage.prompt_tokens,
        tokens_out=m.usage.completion_tokens,
        latency_ms=m.latency_ms,
        model_id=m.model_id,
        finish_reason=fr,
    )


def _unwrap_chunk(hub_chunk: HubChunk) -> StreamChunk:
    """Convert K1 HubChunk to POC StreamChunk for on_stream callbacks.

    HubChunk has fields ``content``, ``done``, ``metadata``, ``tool_calls``
    (see ``k1/model_hub/types.py``). The concierge ``StreamChunk`` has a
    richer ``chunk_type`` taxonomy (``text_delta``/``tool_call_delta``/
    ``done``), so we derive chunk_type from the HubChunk shape:

    - ``done=True``                → build a full ConciergeModelResponse
    - ``tool_calls`` non-empty     → ``tool_call_delta`` with first call
    - otherwise (text present)     → ``text_delta`` with ``content``
    """
    if hub_chunk.done:
        # Build a synthetic HubResponse so we can reuse _unwrap_response.
        tool_calls = hub_chunk.tool_calls or []
        if tool_calls:
            result: Any = ToolCallResultSet(text=hub_chunk.content, tool_calls=tool_calls)
        else:
            result = ChatResult(text=hub_chunk.content)
        metadata = hub_chunk.metadata
        if metadata is None:
            # Synthesize a minimal metadata block. _unwrap_response reads
            # finish_reason, model_id, usage.* and latency_ms.
            metadata = ResponseMetadata(
                request_id="",
                model_id="",
                provider_id="",
                usage=TokenUsage(),
                cost_usd=0.0,
                latency_ms=0,
                cache_hit=False,
                capability=CapabilityType.CHAT,
                trace_id="",
                finish_reason=(
                    K1FinishReason.TOOL_CALLS if tool_calls else K1FinishReason.STOP
                ),
            )
        hub_resp = HubResponse(result=result, metadata=metadata)
        return StreamChunk(chunk_type="done", response=_unwrap_response(hub_resp))

    if hub_chunk.tool_calls:
        tc = hub_chunk.tool_calls[0]
        return StreamChunk(
            chunk_type="tool_call_delta",
            tool_call_partial=ToolCallResult(
                id=tc.id, name=tc.name, arguments=tc.arguments
            ),
        )

    return StreamChunk(chunk_type="text_delta", text=hub_chunk.content)


# =========================================================================
# Max iterations constants (Epic 5.5)
# Kept as module-level constants for backward compatibility.
# Runtime code reads from get_config().react.* and get_config().prompt.*
# =========================================================================

DEFAULT_FRONT_MAX_ITERATIONS: int = 6
DEFAULT_BACK_MAX_ITERATIONS: int = 10


# ---- M3 E3.4.4: Config-backed accessors replace hardcoded dicts ----
# DEPRECATED: Use get_config().prompt.max_iterations instead.
# These remain importable for backward compatibility but delegate to config.
def get_mode_max_iterations() -> dict[str, int]:
    """Return per-mode iteration limits from config (single source of truth)."""
    return dict(get_config().prompt.max_iterations)


def get_crisis_max_iterations() -> dict[str, int]:
    """Return per-mode crisis iteration limits from config."""
    return dict(get_config().prompt.crisis_iterations)


# Backward-compat aliases -- lazy-evaluated via get_config() at import time.
# NOTE: These are snapshots taken at import; prefer the functions above.
# TODO: Remove in M8 when all consumers migrate to get_config().
MODE_MAX_ITERATIONS: dict[str, int] = {
    "STANDARD": 6,
    "CLARIFY_ASK": 3,
    "CLARIFY_RESOLVE": 5,
    "HITL_RELAY": 1,
    "HITL_RESOLVE": 3,
    "PRESENT": 3,
    "WEAVE": 3,
    "CANCEL": 3,
    "INTERRUPT": 6,
    "ERROR": 2,
}

CRISIS_MAX_ITERATIONS: dict[str, int] = {
    "STANDARD": 4,
    "CLARIFY_ASK": 2,
    "CLARIFY_RESOLVE": 4,
    "HITL_RELAY": 1,
    "HITL_RESOLVE": 2,
    "PRESENT": 2,
    "WEAVE": 2,
    "CANCEL": 2,
    "INTERRUPT": 4,
    "ERROR": 2,
}

# Fallback messages (V2 Section 7.5, 7.6)
# Kept as module-level constants for backward compatibility.
FRONT_DEGENERATE_FALLBACK: str = "Let me think about that for a moment."
FRONT_BUDGET_FALLBACK: str = "Let me get back to you on that."


# =========================================================================
# ReactResult dataclass (Epic 5.1.2)
# =========================================================================


@dataclass
class ReactResult:
    """Return value from react_loop().

    status values:
      - "complete":         Front: text response emitted.
                            Back: submit_result(result_type="complete") called.
      - "suspended":        Back only: submit_result(result_type="needs_human").
                            HITL pending.
      - "cancelled":        cancellation_check() returned True between iterations.
      - "budget_exhausted": max_iterations reached without termination.
    """

    status: str  # "complete" | "suspended" | "cancelled" | "budget_exhausted"
    text: str | None = None  # Front: final response text. Back: None.
    data: dict | None = None  # Back: submit_result() arguments. Front: None.
    dispatched_tasks: list[dict] = field(default_factory=list)  # L3: dispatch_task calls
    parallel_tool_calls: int = 0  # M3 E3.7.4: count of parallel-executed tool calls
    sequential_tool_calls: int = 0  # M3 E3.7.4: count of sequential-executed tool calls
    iteration_durations_ms: list[int] = field(default_factory=list)  # Per-iteration wall-clock ms


# =========================================================================
# _resolve_tool_choice helper (Epic 5.1.5)
# =========================================================================


def _resolve_tool_choice(iteration: int, actor: str, tools: list[ToolSchema]) -> str:
    """Determine tool_choice for this iteration.

    Rules (V2 Section 7.5, ITEM #13):
      - Front, iteration 0, tools available: "required"
        Forces the first tool call.
      - All other cases: "auto"
        Let the model decide whether to call a tool or respond with text.
    """
    if iteration == 0 and actor == "front" and tools:
        return "required"
    return "auto"


# =========================================================================
# _result_to_dict helper
# =========================================================================


def _result_to_dict(result: ToolResult) -> dict[str, Any]:
    """Convert a ToolResult to a dict for tool_result_to_message.

    For errors, returns error info dict. For success, returns result.data.
    """
    if result.is_error():
        return {"error": result.error, "tool": result.tool_name}
    return result.data


# =========================================================================
# Streaming helper (Epic 2.1)
# =========================================================================


async def _streaming_generate(
    model: IModelHubPort,
    request: HubRequest,
    on_stream: Callable[[StreamChunk], Awaitable[None]],
) -> ConciergeModelResponse:
    """Call model.stream_execute(), forward chunks, return final response.

    Consumes the async iterator from stream_execute(), converts each
    K1 HubChunk to POC StreamChunk, forwards to the on_stream callback,
    and returns the completed ConciergeModelResponse (unwrapped from
    the final "done" chunk's HubResponse).

    Falls back to model.execute() if stream_execute() is not available
    or raises an error.
    """
    try:
        response: ConciergeModelResponse | None = None
        async for hub_chunk in model.stream_execute(request):
            chunk = _unwrap_chunk(hub_chunk)
            if chunk.chunk_type == "done":
                response = chunk.response
            else:
                await on_stream(chunk)

        if response is None:
            logger.warning("stream_execute ended without done chunk, falling back")
            return _unwrap_response(await model.execute(request))

        return response

    except (NotImplementedError, AttributeError):
        logger.info("stream_execute not available, falling back to execute()")
        return _unwrap_response(await model.execute(request))
    except Exception as exc:
        logger.warning("stream_execute failed (%s), falling back to execute()", exc)
        return _unwrap_response(await model.execute(request))


# =========================================================================
# react_loop (Epic 5.1.3, 5.1.4)
# =========================================================================


async def react_loop(
    actor: str,
    system_prompt: str,
    messages: list[ModelMessage],
    tools: list[ToolSchema],
    max_iterations: int,
    model: IModelHubPort,
    tool_dispatcher: ToolDispatcher,
    on_text_response: Callable[[str], Awaitable[None]],
    cancellation_check: Callable[[], Awaitable[bool]],
    trace_id: str = "",
    scenario: str = "",
    validator: LLMOutputValidator | None = None,
    on_stream: Callable[[StreamChunk], Awaitable[None]] | None = None,
) -> ReactResult:
    """Shared ReAct loop for both Front and Back actors.

    Termination:
      Front (L1): text response with NO tool calls -> final response.
                  NOTE: on_text_response is NOT called inside the loop.
                  The caller (front_handler) emits response.final AFTER
                  emitting task dispatches, ensuring correct FSM ordering.
      Back (L2):  submit_result() tool call -> structured result
                  (text-without-tool-calls from Back = "thinking aloud", continues)

    ITEM #13: tool_choice="required" on Front iteration 0 forces a tool call.
    ITEM #14: cancellation_check at top of each iteration.
    ITEM #19: Back text-without-tools = "thinking aloud", NOT terminal.

    Args:
        actor: "front" or "back"
        system_prompt: Built by DynamicPromptBuilder (M08/M09)
        messages: Chat history + current user input. MUTATED in-place.
        tools: Actor-specific tool schemas
        max_iterations: Front: mode+affect driven. Back: tier driven.
        model: LLM adapter (M03)
        tool_dispatcher: Validates + executes tool calls (M04, async)
        on_text_response: Unused by react_loop -- kept for interface
            compatibility. front_handler calls it after task dispatches.
        cancellation_check: Check if task/turn is cancelled.
        trace_id: End-to-end trace ID for observability.
        scenario: Mode/scenario label for observability.

    Returns:
        ReactResult with status, text, data, and dispatched_tasks.
    """
    dispatched_tasks: list[dict] = []
    last_text_with_tools: str | None = None  # Track text from mixed (text+tools) responses
    # M3 E3.7.4: Parallel safety observability counters
    _parallel_count = 0
    _sequential_count = 0
    _iteration_durations: list[int] = []  # Per-iteration wall-clock ms
    original_tools = tools  # Preserve original list; tools may be cleared on degenerate retry
    _degenerate_retry_active = False  # Track if we're in a degenerate retry

    # Per-iteration LLM call timeout (prevents hangs from API stalls)
    _iter_timeout_s: float = get_config().llm.default_timeout_ms / 1000.0

    # Hoist _run_tool outside the loop to avoid re-creating the closure
    async def _run_tool(tc: Any) -> tuple[Any, ToolResult]:
        result = await tool_dispatcher.dispatch(tc)
        return tc, result

    logger.info(
        "react_loop START: actor=%s max_iter=%d tools=%d scenario=%s trace=%s",
        actor,
        max_iterations,
        len(tools),
        scenario,
        trace_id[:8] if trace_id else "",
    )

    for iteration in range(max_iterations):
        _iter_start = time.monotonic()

        # ---- RESTORE TOOLS AFTER DEGENERATE RETRY ----
        # If the previous iteration was a degenerate retry (tools=[]),
        # restore the original tool list so the loop can resume normally.
        if _degenerate_retry_active:
            tools = original_tools
            _degenerate_retry_active = False
            logger.debug(
                "react_loop: restored %d tools after degenerate retry",
                len(tools),
            )

        # ---- CANCELLATION CHECK (ITEM #14) ----
        if await cancellation_check():
            return ReactResult(
                status="cancelled",
                dispatched_tasks=dispatched_tasks,
                parallel_tool_calls=_parallel_count,
                sequential_tool_calls=_sequential_count,
                iteration_durations_ms=_iteration_durations,
            )

        # ---- BUILD REQUEST ----
        # On the last iteration for Front, strip tools to force text-only
        # output. Without this, the model may keep calling tools and
        # exhaust the budget without ever producing a text response.
        # tools may already be [] from a degenerate retry (see below).
        is_last = iteration == max_iterations - 1
        force_text = (is_last and actor == "front") or not tools
        # For Back on the last iteration, nudge it to call submit_result
        # with whatever partial results it has, rather than exhausting budget.
        force_submit = is_last and actor == "back" and tools
        effective_tools = [] if force_text else tools

        if force_submit:
            messages.append(
                ModelMessage(
                    role="user",
                    content=(
                        "You are on your LAST iteration. You MUST call "
                        "submit_result now with whatever results you have "
                        "gathered so far. Summarize your findings in "
                        "final_answer. Use result_type='complete'."
                    ),
                )
            )
            logger.info(
                "react_loop: iter=%d LAST ITERATION (back) -- nudging submit_result",
                iteration,
            )

        if force_text and tools:
            logger.info(
                "react_loop: iter=%d LAST ITERATION -- forcing text-only (no tools)",
                iteration,
            )

        # Build K1 HubRequest (bridge translates to POC adapter internally)
        _cap = (
            CapabilityType.CHAT
            if force_text
            else (CapabilityType.TOOL_CALL if tools else CapabilityType.CHAT)
        )
        _tc = "none" if force_text else _resolve_tool_choice(iteration, actor, tools)
        _k1_msgs = _to_k1_messages(messages)
        # Ensure at least one message for payload validation
        if not _k1_msgs and system_prompt:
            _k1_msgs = [K1Message(role="system", content=system_prompt)]
        if _cap == CapabilityType.TOOL_CALL and effective_tools:
            _payload = ToolCallPayload(
                messages=_k1_msgs,
                tools=_to_k1_tools(effective_tools),
                tool_choice=_tc,
            )
        else:
            _payload = ChatPayload(
                messages=_k1_msgs,
                system_prompt=system_prompt,
            )
        request = HubRequest(
            capability=_cap,
            payload=_payload,
            constraints=RequestConstraints(
                max_tokens=65536,
                consumer_id=f"concierge.{actor}",
            ),
            trace_id=trace_id or f"concierge-{actor}-{iteration}",
        )

        # ---- LLM CALL (streaming on all Front iterations when on_stream provided) ----
        use_streaming = on_stream is not None and actor == "front" and not force_text

        try:
            if use_streaming:
                response = await asyncio.wait_for(
                    _streaming_generate(model, request, on_stream),
                    timeout=_iter_timeout_s,
                )
            else:
                response = _unwrap_response(
                    await asyncio.wait_for(
                        model.execute(request),
                        timeout=_iter_timeout_s,
                    )
                )
        except asyncio.TimeoutError:
            logger.error(
                "react_loop: LLM call TIMED OUT on iter=%d actor=%s "
                "(timeout=%.1fs) -- aborting. trace=%s",
                iteration,
                actor,
                _iter_timeout_s,
                trace_id[:8] if trace_id else "",
            )
            _iter_dur = int((time.monotonic() - _iter_start) * 1000)
            _iteration_durations.append(_iter_dur)
            fallback = get_config().react.front_degenerate_fallback if actor == "front" else ""
            return ReactResult(
                status="complete" if actor == "front" else "budget_exhausted",
                text=fallback if actor == "front" else None,
                dispatched_tasks=dispatched_tasks,
                parallel_tool_calls=_parallel_count,
                sequential_tool_calls=_sequential_count,
                iteration_durations_ms=_iteration_durations,
            )

        logger.info(
            "react_loop: iter=%d actor=%s has_text=%s has_tools=%s finish=%s "
            "streamed=%s text=%s",
            iteration,
            actor,
            response.has_text,
            response.has_tool_calls,
            response.finish_reason,
            use_streaming,
            (response.text or "")[:60],
        )

        # ---- LLM ERROR: bail immediately instead of wasting iterations ----
        if response.finish_reason == FinishReason.ERROR:
            logger.error(
                "react_loop: LLM returned ERROR on iter=%d actor=%s -- aborting loop "
                "(check model name, API key, or quota)",
                iteration,
                actor,
            )
            fallback = get_config().react.front_degenerate_fallback if actor == "front" else ""
            return ReactResult(
                status="complete",
                text=fallback,
                dispatched_tasks=dispatched_tasks,
                parallel_tool_calls=_parallel_count,
                sequential_tool_calls=_sequential_count,
                iteration_durations_ms=_iteration_durations,
            )

        # ---- VALIDATION (Epic 4.1) ----
        if validator is not None and response.has_tool_calls:
            avail_names = (
                frozenset(t.name for t in effective_tools) if effective_tools else frozenset()
            )
            vr: ValidationResult = validator.validate(
                response,
                actor=actor,
                iteration=iteration,
                available_tool_names=avail_names,
            )
            if not vr.valid:
                if vr.fixed_response is not None:
                    response = vr.fixed_response
                    logger.info(
                        "react_loop: validation fixed response, " "stripped %d -> %d tool calls",
                        len(vr.fixed_response.tool_calls) + len(vr.issues),
                        len(vr.fixed_response.tool_calls),
                    )
                else:
                    # No salvageable tool calls -- treat as degenerate
                    logger.warning(
                        "react_loop: validation failed, no fix possible: %s",
                        "; ".join(vr.issues),
                    )
                    if actor == "front":
                        return ReactResult(
                            status="complete",
                            text=get_config().react.front_degenerate_fallback,
                            dispatched_tasks=dispatched_tasks,
                            parallel_tool_calls=_parallel_count,
                            sequential_tool_calls=_sequential_count,
                            iteration_durations_ms=_iteration_durations,
                        )
                    continue

        # ---- MALFORMED TOOL CALL: model tried a tool call but JSON was invalid ----
        if response.finish_reason == FinishReason.MALFORMED_TOOL_CALL:
            logger.warning(
                "Malformed tool call from %s on iteration %d -- nudging to simplify",
                actor,
                iteration,
            )
            if iteration < max_iterations - 1:
                messages.append(
                    ModelMessage(
                        role="user",
                        content=(
                            "Your function call had invalid JSON and was rejected. "
                            "Call submit_result now. Keep the results array simple: "
                            "use plain strings instead of nested objects. "
                            "Summarize each web result as a single string like "
                            "'Title - URL - Snippet'."
                        ),
                    )
                )
                logger.info(
                    "react_loop: %s malformed_tool_call on iter=%d/%d, nudging to simplify",
                    actor,
                    iteration,
                    max_iterations,
                )
            _iter_dur = int((time.monotonic() - _iter_start) * 1000)
            _iteration_durations.append(_iter_dur)
            continue

        # ---- DEGENERATE: no text AND no tool calls ----
        if not response.has_text and not response.has_tool_calls:
            logger.warning("Degenerate response from %s on iteration %d", actor, iteration)
            if actor == "front":
                # Retry once with a nudge AND strip tools so the model
                # MUST produce text. Gemini 3 models sometimes exhaust
                # their thinking budget processing tool results and
                # return empty output. Forcing text-only on the retry
                # guarantees we get a real answer.
                if iteration < max_iterations - 1:
                    messages.append(
                        ModelMessage(
                            role="user",
                            content=(
                                "Now respond directly to the user. Synthesize "
                                "everything you learned from the tools above "
                                "into a helpful, natural response. Do NOT call "
                                "any more tools. Do NOT include your reasoning "
                                "or analysis -- output ONLY the user-facing message."
                            ),
                        )
                    )
                    logger.info(
                        "react_loop: front degenerate on iter=%d, "
                        "retrying with nudge + tools stripped",
                        iteration,
                    )
                    # Force text-only on the retry by temporarily
                    # clearing tools for the next iteration
                    tools = []
                    _degenerate_retry_active = True
                    _iter_dur = int((time.monotonic() - _iter_start) * 1000)
                    _iteration_durations.append(_iter_dur)
                    continue
                # If we have saved text from a mixed response, use it
                if last_text_with_tools:
                    logger.info(
                        "react_loop: degenerate on last iter but have saved text (%d chars)",
                        len(last_text_with_tools),
                    )
                    return ReactResult(
                        status="complete",
                        text=last_text_with_tools,
                        dispatched_tasks=dispatched_tasks,
                        parallel_tool_calls=_parallel_count,
                        sequential_tool_calls=_sequential_count,
                        iteration_durations_ms=_iteration_durations,
                    )
                fallback = get_config().react.front_degenerate_fallback
                # Do NOT fire on_text_response here; front_handler
                # controls emission order (dispatches before final).
                return ReactResult(
                    status="complete",
                    text=fallback,
                    dispatched_tasks=dispatched_tasks,
                    parallel_tool_calls=_parallel_count,
                    sequential_tool_calls=_sequential_count,
                    iteration_durations_ms=_iteration_durations,
                )
            # Back degenerate: nudge to submit what it has
            if iteration < max_iterations - 1:
                # Early iterations: gentle nudge -- Back may still do useful work
                if iteration < max_iterations // 2:
                    nudge = (
                        "Your last response was empty. Continue working on "
                        "the task -- discover capabilities and invoke them. "
                        "If you cannot make progress, call submit_result."
                    )
                else:
                    # Late iterations: urgent nudge -- wrap it up
                    nudge = (
                        "Your last response was empty. Call submit_result "
                        "now with the results gathered so far."
                    )
                messages.append(ModelMessage(role="user", content=nudge))
                logger.info(
                    "react_loop: back degenerate on iter=%d/%d, nudging (%s)",
                    iteration,
                    max_iterations,
                    "gentle" if iteration < max_iterations // 2 else "urgent",
                )
            _iter_dur = int((time.monotonic() - _iter_start) * 1000)
            _iteration_durations.append(_iter_dur)
            continue

        # ---- TEXT WITHOUT TOOL CALLS ----
        if response.has_text and not response.has_tool_calls:
            if actor == "front":
                # L1 termination: text is the final response.
                # Do NOT fire on_text_response here; front_handler
                # emits task dispatches first, THEN response.final,
                # so the FSM sees DISPATCHING -> COMPANIONING -> ...
                # before DISPATCHING -> LISTENING.
                _iter_dur = int((time.monotonic() - _iter_start) * 1000)
                _iteration_durations.append(_iter_dur)
                return ReactResult(
                    status="complete",
                    text=response.text,
                    dispatched_tasks=dispatched_tasks,
                    parallel_tool_calls=_parallel_count,
                    sequential_tool_calls=_sequential_count,
                    iteration_durations_ms=_iteration_durations,
                )
            # Back (ITEM #19): text without tool calls
            # Detect pseudo-code pattern: model writes code instead of
            # making a real tool call (e.g. "tool_code\nprint(...)").
            _txt = response.text or ""
            _is_pseudo = any(
                marker in _txt for marker in ("tool_code", "default_api.", "print(", "```python")
            )
            _has_prior_tools = (_parallel_count + _sequential_count) > 0
            if _is_pseudo:
                messages.append(
                    ModelMessage(
                        role="user",
                        content=(
                            "Do NOT write code or pseudo-code. Use the "
                            "submit_result function call directly. Call "
                            "submit_result now with result_type='complete'."
                        ),
                    )
                )
                logger.warning(
                    "react_loop: back pseudo-code detected on iter=%d, nudging",
                    iteration,
                )
            elif _has_prior_tools:
                # Back already invoked capabilities but wrote conversational
                # text instead of calling submit_result -- nudge it.
                messages.append(
                    ModelMessage(
                        role="user",
                        content=(
                            "You already invoked capabilities successfully. "
                            "Now call submit_result to deliver those results. "
                            "Do NOT write conversational text."
                        ),
                    )
                )
                logger.info(
                    "react_loop: back text-only after tools on iter=%d, " "nudging submit_result",
                    iteration,
                )
            else:
                # Genuine thinking aloud before any tool calls
                messages.append(ModelMessage(role="assistant", content=response.text))
            _iter_dur = int((time.monotonic() - _iter_start) * 1000)
            _iteration_durations.append(_iter_dur)
            continue

        # ---- PROCESS TOOL CALLS ----
        # Track text from mixed (text + tools) responses so we never
        # lose useful content if the model keeps calling tools until
        # budget exhaustion.
        if response.has_text and response.has_tool_calls and actor == "front":
            last_text_with_tools = response.text
            logger.info(
                "react_loop: iter=%d text+tools -- saving text as fallback (%d chars)",
                iteration,
                len(response.text),
            )

        # Append ONE assistant message with ALL tool calls (Step 7f)
        messages.append(
            ModelMessage(
                role="assistant",
                content=response.text if response.text else "",
                tool_calls=response.tool_calls,
                _raw_provider_content=getattr(response, "_raw_provider_content", None),
            )
        )

        # E3.4.5: warn if submit_result appears alongside other tools.
        # submit_result is processed first (early-return below) and the
        # other tools are skipped, which is correct but indicates LLM
        # confusion when it happens.
        _has_submit = any(tc.name == "submit_result" for tc in response.tool_calls)
        _has_others = any(tc.name != "submit_result" for tc in response.tool_calls)
        if _has_submit and _has_others:
            logger.warning(
                "react_loop: submit_result returned alongside %d other tools "
                "(LLM confusion?) -- submit_result processed first, others "
                "skipped. trace=%s",
                sum(1 for tc in response.tool_calls if tc.name != "submit_result"),
                trace_id[:8] if trace_id else "",
            )

        for tc in response.tool_calls:

            # Back termination (L2): submit_result
            if tc.name == "submit_result":
                result = await tool_dispatcher.dispatch(tc)
                if result.status == "error":
                    # Schema validation or execution failed -- feed
                    # error back to LLM so it can retry with valid args.
                    logger.warning(
                        "react_loop: submit_result dispatch failed "
                        "(error=%s), feeding back to LLM. trace=%s",
                        result.error,
                        trace_id[:8] if trace_id else "",
                    )
                    messages.append(
                        ModelMessage(
                            role="tool",
                            content=json.dumps(
                                {"error": result.error, "hint": "Fix arguments and retry"}
                            ),
                            tool_call_id=getattr(tc, "id", None),
                        )
                    )
                    break  # Let LLM retry on next iteration
                status = (
                    "complete" if tc.arguments.get("result_type") == "complete" else "suspended"
                )
                _iter_dur = int((time.monotonic() - _iter_start) * 1000)
                _iteration_durations.append(_iter_dur)
                return ReactResult(
                    status=status,
                    data=tc.arguments,
                    dispatched_tasks=dispatched_tasks,
                    parallel_tool_calls=_parallel_count,
                    sequential_tool_calls=_sequential_count,
                    iteration_durations_ms=_iteration_durations,
                )

        # ---- CLASSIFIED TOOL EXECUTION (M3 E3.4.2/3.4.3/3.4.5) ----
        # Split non-terminal tool calls into parallel-safe and sequential
        # groups using the safety classifier.  A config toggle can force
        # all tools to run sequentially for debugging.
        non_terminal = [tc for tc in response.tool_calls if tc.name != "submit_result"]

        parallel_enabled = get_config().react.parallel_tools_enabled
        parallel_names, sequential_names = classify_tool_batch([tc.name for tc in non_terminal])

        logger.info(
            "react_loop: tool_batch_classified  parallel=%s sequential=%s "
            "parallel_enabled=%s trace=%s",
            parallel_names,
            sequential_names,
            parallel_enabled,
            trace_id[:8] if trace_id else "",
        )

        # Build lookup: name -> list of tool calls (preserves order for dupes)
        _tc_by_name: dict[str, list[Any]] = {}
        for tc in non_terminal:
            _tc_by_name.setdefault(tc.name, []).append(tc)

        paired_results: list[tuple[Any, ToolResult]] = []

        if parallel_enabled and parallel_names:
            # Gather parallel-safe tools from the original order
            parallel_tcs = [tc for tc in non_terminal if tc.name in set(parallel_names)]
            parallel_results = await asyncio.gather(*[_run_tool(tc) for tc in parallel_tcs])
            paired_results.extend(parallel_results)
            _parallel_count += len(parallel_tcs)

        # Sequential tools (always sequential, or ALL tools when toggle off)
        if parallel_enabled:
            sequential_tcs = [tc for tc in non_terminal if tc.name in set(sequential_names)]
        else:
            sequential_tcs = non_terminal

        for tc in sequential_tcs:
            result = await tool_dispatcher.dispatch(tc)
            paired_results.append((tc, result))
            _sequential_count += 1

        # Re-sort results to match the LLM's original tool call order.
        # parallel+sequential execution may interleave; the LLM expects
        # observations in the same order it issued calls.
        _tc_order = {id(tc): idx for idx, tc in enumerate(non_terminal)}
        paired_results.sort(key=lambda pair: _tc_order.get(id(pair[0]), 999))

        for tc, result in paired_results:

            # Collect dispatch_task calls (L3)
            if tc.name == "dispatch_task":
                task_entry = dict(tc.arguments)
                # Merge system-generated task_id from ToolResult so the
                # downstream dispatch envelope carries the canonical ID.
                if result.is_ok() and result.data:
                    task_id = result.data.get("task_id")
                    if task_id:
                        task_entry["task_id"] = task_id
                    # Also merge the full _dispatch payload if present
                    dispatch_payload = result.data.get("_dispatch")
                    if isinstance(dispatch_payload, dict):
                        task_entry.update(dispatch_payload)
                dispatched_tasks.append(task_entry)

            # Log artifact creation (invoke_capability with artifact_type)
            if (
                tc.name == "invoke_capability"
                and result.is_ok()
                and result.data.get("artifact_type")
            ):
                logger.info("Artifact created: type=%s", result.data.get("artifact_type"))

            # Append tool result as observation (ReAct pattern)
            messages.append(_tool_result_to_msg(tc, _result_to_dict(result)))

        # Per-iteration timing for the tool-execution branch
        _iter_dur = int((time.monotonic() - _iter_start) * 1000)
        _iteration_durations.append(_iter_dur)
        logger.debug(
            "react_loop: iter=%d completed in %dms (actor=%s)",
            iteration,
            _iter_dur,
            actor,
        )

    # ---- BUDGET EXHAUSTED ----
    if actor == "front":
        # If we captured text from a mixed (text+tools) response, use it
        # instead of the generic fallback -- it's real LLM output.
        if last_text_with_tools:
            logger.info(
                "react_loop: budget exhausted but recovered text from mixed response (%d chars)",
                len(last_text_with_tools),
            )
            return ReactResult(
                status="complete",
                text=last_text_with_tools,
                dispatched_tasks=dispatched_tasks,
                parallel_tool_calls=_parallel_count,
                sequential_tool_calls=_sequential_count,
                iteration_durations_ms=_iteration_durations,
            )
        # Do NOT fire on_text_response here; front_handler handles emission.
        return ReactResult(
            status="budget_exhausted",
            text=get_config().react.front_budget_fallback,
            dispatched_tasks=dispatched_tasks,
            parallel_tool_calls=_parallel_count,
            sequential_tool_calls=_sequential_count,
            iteration_durations_ms=_iteration_durations,
        )

    return ReactResult(
        status="budget_exhausted",
        dispatched_tasks=dispatched_tasks,
        parallel_tool_calls=_parallel_count,
        sequential_tool_calls=_sequential_count,
        iteration_durations_ms=_iteration_durations,
    )

    return ReactResult(
        status="budget_exhausted",
        dispatched_tasks=dispatched_tasks,
        parallel_tool_calls=_parallel_count,
        sequential_tool_calls=_sequential_count,
        iteration_durations_ms=_iteration_durations,
    )
