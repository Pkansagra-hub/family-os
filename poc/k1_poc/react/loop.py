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
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from poc.k1_poc.config import get_config
from poc.k1_poc.llm.ports import IConciergeModelPort
from poc.k1_poc.llm.types import (
    Capability,
    ConciergeModelRequest,
    ConciergeModelResponse,
    FinishReason,
    ModelMessage,
    StreamChunk,
    ToolSchema,
)
from poc.k1_poc.llm.types import tool_result_to_message as _tool_result_to_msg
from poc.k1_poc.llm.validator import LLMOutputValidator, ValidationResult
from poc.k1_poc.tools.dispatcher import ToolDispatcher
from poc.k1_poc.tools.result_protocol import ToolResult

logger = logging.getLogger(__name__)

# =========================================================================
# Max iterations constants (Epic 5.5)
# Kept as module-level constants for backward compatibility.
# Runtime code reads from get_config().react.* and get_config().prompt.*
# =========================================================================

DEFAULT_FRONT_MAX_ITERATIONS: int = 6
DEFAULT_BACK_MAX_ITERATIONS: int = 10

# NOTE: MODE_MAX_ITERATIONS and CRISIS_MAX_ITERATIONS duplicate the tables
# in prompt.max_iterations / prompt.crisis_iterations (config/defaults.yaml).
# New code should use get_config().prompt.max_iterations instead.
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
    model: IConciergeModelPort,
    request: ConciergeModelRequest,
    on_stream: Callable[[StreamChunk], Awaitable[None]],
) -> ConciergeModelResponse:
    """Call model.generate_stream(), forward chunks, return final response.

    Consumes the async iterator from generate_stream(), forwards each
    thinking/text chunk to the on_stream callback, and returns the
    completed ConciergeModelResponse from the final "done" chunk.

    Falls back to model.generate() if generate_stream() is not available
    or raises an error.
    """
    try:
        response: ConciergeModelResponse | None = None
        async for chunk in model.generate_stream(request):
            if chunk.chunk_type == "done":
                response = chunk.response
            else:
                await on_stream(chunk)

        if response is None:
            logger.warning("generate_stream ended without done chunk, falling back")
            return await model.generate(request)

        return response

    except (NotImplementedError, AttributeError):
        logger.info("generate_stream not available, falling back to generate()")
        return await model.generate(request)
    except Exception as exc:
        logger.warning("generate_stream failed (%s), falling back to generate()", exc)
        return await model.generate(request)


# =========================================================================
# react_loop (Epic 5.1.3, 5.1.4)
# =========================================================================


async def react_loop(
    actor: str,
    system_prompt: str,
    messages: list[ModelMessage],
    tools: list[ToolSchema],
    max_iterations: int,
    model: IConciergeModelPort,
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
    original_tools = tools  # Preserve original list; tools may be cleared on degenerate retry

    logger.info(
        "react_loop START: actor=%s max_iter=%d tools=%d scenario=%s trace=%s",
        actor,
        max_iterations,
        len(tools),
        scenario,
        trace_id[:8] if trace_id else "",
    )

    for iteration in range(max_iterations):

        # ---- CANCELLATION CHECK (ITEM #14) ----
        if await cancellation_check():
            return ReactResult(status="cancelled", dispatched_tasks=dispatched_tasks)

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

        request = ConciergeModelRequest(
            capability=(
                Capability.CHAT
                if force_text
                else (Capability.TOOL_CALL if tools else Capability.CHAT)
            ),
            system_prompt=system_prompt,
            messages=messages,
            tools=effective_tools if effective_tools else None,
            tool_choice="none" if force_text else _resolve_tool_choice(iteration, actor, tools),
            max_tokens=65536,
            actor=actor,
            scenario=scenario,
            trace_id=trace_id,
        )

        # ---- LLM CALL (streaming on Front iter 0 when on_stream provided) ----
        use_streaming = (
            on_stream is not None and actor == "front" and iteration == 0 and not force_text
        )

        if use_streaming:
            response = await _streaming_generate(
                model,
                request,
                on_stream,
            )
        else:
            response = await model.generate(request)

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
                        )
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
                                "any more tools."
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
                    )
                fallback = get_config().react.front_degenerate_fallback
                # Do NOT fire on_text_response here; front_handler
                # controls emission order (dispatches before final).
                return ReactResult(
                    status="complete",
                    text=fallback,
                    dispatched_tasks=dispatched_tasks,
                )
            # Back degenerate: nudge to submit what it has
            if iteration < max_iterations - 1:
                messages.append(
                    ModelMessage(
                        role="user",
                        content=(
                            "Your last response was empty. Call submit_result "
                            "now with the results gathered so far."
                        ),
                    )
                )
                logger.info(
                    "react_loop: back degenerate on iter=%d, nudging submit_result",
                    iteration,
                )
            continue

        # ---- TEXT WITHOUT TOOL CALLS ----
        if response.has_text and not response.has_tool_calls:
            if actor == "front":
                # L1 termination: text is the final response.
                # Do NOT fire on_text_response here; front_handler
                # emits task dispatches first, THEN response.final,
                # so the FSM sees DISPATCHING -> COMPANIONING -> ...
                # before DISPATCHING -> LISTENING.
                return ReactResult(
                    status="complete",
                    text=response.text,
                    dispatched_tasks=dispatched_tasks,
                )
            # Back (ITEM #19): text = "thinking aloud", NOT terminal
            messages.append(ModelMessage(role="assistant", content=response.text))
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

        for tc in response.tool_calls:

            # Back termination (L2): submit_result
            if tc.name == "submit_result":
                await tool_dispatcher.dispatch(tc)
                status = (
                    "complete" if tc.arguments.get("result_type") == "complete" else "suspended"
                )
                return ReactResult(
                    status=status,
                    data=tc.arguments,
                    dispatched_tasks=dispatched_tasks,
                )

        # ---- PARALLEL TOOL EXECUTION ----
        # Execute all non-terminal tool calls concurrently via
        # asyncio.gather to cut wall-clock time when the model
        # invokes multiple tools in one turn (e.g. recall_memory
        # + update_beliefs + update_scoreboard).
        non_terminal = [tc for tc in response.tool_calls if tc.name != "submit_result"]

        async def _run_tool(tc: Any) -> tuple[Any, ToolResult]:
            result = await tool_dispatcher.dispatch(tc)
            return tc, result

        paired_results: list[tuple[Any, ToolResult]] = await asyncio.gather(
            *[_run_tool(tc) for tc in non_terminal]
        )

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
            )
        # Do NOT fire on_text_response here; front_handler handles emission.
        return ReactResult(
            status="budget_exhausted",
            text=get_config().react.front_budget_fallback,
            dispatched_tasks=dispatched_tasks,
        )

    return ReactResult(status="budget_exhausted", dispatched_tasks=dispatched_tasks)
