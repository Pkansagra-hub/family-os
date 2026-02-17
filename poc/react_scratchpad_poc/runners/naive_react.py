"""
Naive ReAct runner -- the control baseline.

Implements the standard ReAct loop pattern:
  messages = [system, user]
  loop:
    response = llm(messages)      # send ALL messages
    if no tool calls -> break
    execute tools
    messages.append(tool results)  # append EVERYTHING
  return final answer

This is the pattern used by SimpleLLMClient.agentic_loop() and most
LLM frameworks. Context grows monotonically, no compaction, no budget,
no structured findings. This is what the scratchpad replaces.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from core.models import RunResult, Scenario, ToolResult, TurnRecord
from core.protocols import LLMClient, LLMResponse, ToolRegistry
from eval import trace as T

logger = logging.getLogger("react_poc.naive")


class NaiveReactRunner:
    """
    Naive ReAct loop -- appends all messages, no compaction.

    This runner exists to demonstrate what happens without a scratchpad:
    - Context grows with every iteration
    - Token usage increases monotonically
    - Old information buried in long message lists
    - No budget tracking -- runs until max iterations or text response
    - No structured findings -- facts buried in raw text
    """

    def __init__(self, max_iterations: int = 50):
        self.max_iterations = max_iterations

    @property
    def name(self) -> str:
        return "naive_react"

    async def run(
        self,
        scenario: Scenario,
        tools: ToolRegistry,
        llm: LLMClient,
        trace: bool = False,
    ) -> RunResult:
        """Execute a scenario using naive message accumulation."""
        started_at = datetime.now(timezone.utc).isoformat()
        start_ns = time.time_ns()

        # Initialize messages with system prompt + user query
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": scenario.system_prompt},
            {"role": "user", "content": scenario.user_query},
        ]

        tool_declarations = tools.get_tool_declarations()
        turns: List[TurnRecord] = []
        errors: List[str] = []
        final_answer: Optional[str] = None
        total_tools_used = 0
        total_tokens_in = 0
        total_tokens_out = 0

        max_iter = min(scenario.max_iterations, self.max_iterations)

        for iteration in range(max_iter):
            # Estimate context size before LLM call
            context_tokens = self._estimate_tokens(messages)

            # Withhold final_answer from declarations during early forced iterations
            iter_tools = tool_declarations
            should_force = scenario.force_tool_call
            if scenario.min_tool_iterations > 0 and iteration < scenario.min_tool_iterations:
                iter_tools = [t for t in tool_declarations if t["name"] != "final_answer"]
            elif iteration >= scenario.min_tool_iterations and scenario.min_tool_iterations > 0:
                # After min iterations, stop forcing so the LLM can call final_answer
                should_force = False

            logger.debug(
                "[NAIVE iter=%d] ctx_tokens=%d messages=%d tools=%d should_force=%s min_tool_iter=%d",
                iteration,
                context_tokens,
                len(messages),
                len(iter_tools),
                should_force,
                scenario.min_tool_iterations,
            )

            if trace:
                T.trace_iteration_start(
                    runner_name="naive_react",
                    iteration=iteration,
                    context_tokens=context_tokens,
                    message_count=len(messages),
                    tools_available=len(iter_tools),
                    force_tool_call=should_force,
                )

            # Call LLM with ALL accumulated messages
            try:
                response: LLMResponse = await llm.generate(
                    messages=messages,
                    tools=iter_tools,
                    force_tool_call=should_force,
                )
            except Exception as e:
                errors.append(f"LLM error at iteration {iteration}: {str(e)}")
                break

            logger.debug(
                "[NAIVE iter=%d] response: has_tool_calls=%s tool_count=%d text_len=%d",
                iteration,
                response.has_tool_calls,
                len(response.tool_calls),
                len(response.text) if response.text else 0,
            )
            if response.tool_calls:
                for tc in response.tool_calls:
                    logger.debug("  -> tool_call: %s(%s)", tc.name, str(tc.arguments)[:200])

            total_tokens_in += response.tokens_in
            total_tokens_out += response.tokens_out

            turn = TurnRecord(
                iteration=iteration,
                context_tokens_estimate=context_tokens,
            )

            # Check if LLM returned a final text answer (no tool calls)
            if not response.has_tool_calls:
                final_answer = response.text or ""
                turn.assistant_message = final_answer
                turn.final_answer_fragment = final_answer
                if trace:
                    T.trace_llm_decision(
                        iteration=iteration,
                        tool_calls=[],
                        reasoning_text=response.text,
                        is_final_answer=True,
                        final_answer_text=final_answer,
                        tokens_in=response.tokens_in,
                        tokens_out=response.tokens_out,
                    )
                turns.append(turn)
                break

            # Check for final_answer tool
            is_final = False
            for tc in response.tool_calls:
                if tc.name == "final_answer":
                    final_answer = tc.arguments.get("answer", "")
                    is_final = True
                    break

            if is_final:
                turn.assistant_message = final_answer
                turn.final_answer_fragment = final_answer
                turn.tool_calls = response.tool_calls
                if trace:
                    T.trace_llm_decision(
                        iteration=iteration,
                        tool_calls=[],
                        is_final_answer=True,
                        final_answer_text=final_answer,
                        tokens_in=response.tokens_in,
                        tokens_out=response.tokens_out,
                    )
                turns.append(turn)
                break

            # Trace: LLM decided to call tools
            if trace:
                T.trace_llm_decision(
                    iteration=iteration,
                    tool_calls=[
                        {"name": tc.name, "arguments": tc.arguments} for tc in response.tool_calls
                    ],
                    reasoning_text=response.text,
                    tokens_in=response.tokens_in,
                    tokens_out=response.tokens_out,
                )

            # Process tool calls
            turn.tool_calls = response.tool_calls

            # Add assistant message with tool calls to history
            tool_call_text = response.text or ""
            for tc in response.tool_calls:
                tool_call_text += f"\n[Calling {tc.name}({tc.arguments})]"
            messages.append({"role": "assistant", "content": tool_call_text})

            # Execute each tool and append results
            tool_results: List[ToolResult] = []
            for tc in response.tool_calls:
                if tc.name in ("spawn_agent", "check_agent_status", "get_agent_result"):
                    # Naive runner doesn't support sub-agents
                    result = ToolResult(
                        tool_name=tc.name,
                        call_id=tc.call_id,
                        ok=False,
                        error_code="NOT_SUPPORTED",
                        error_message="Sub-agent operations not supported in naive runner",
                    )
                else:
                    result = await tools.execute(tc.name, tc.arguments)
                    result.call_id = tc.call_id

                tool_results.append(result)
                total_tools_used += 1

                # Trace: tool execution
                if trace:
                    T.trace_tool_execution(
                        tool_name=tc.name,
                        arguments=tc.arguments,
                        ok=result.ok,
                        output=result.output if result.ok else None,
                        error=(
                            f"{result.error_code}: {result.error_message}"
                            if not result.ok
                            else None
                        ),
                    )

                # Append raw tool result to messages (the naive approach)
                if result.ok:
                    result_text = f"Tool {result.tool_name} result: {result.output}"
                else:
                    result_text = f"Tool {result.tool_name} error: {result.error_code} - {result.error_message}"
                messages.append({"role": "user", "content": result_text})

            turn.tool_results = tool_results
            turn.assistant_message = tool_call_text

            # Trace: iteration end
            if trace:
                T.trace_iteration_end(
                    iteration=iteration,
                    cumulative_findings=0,  # Naive has no findings
                    context_tokens=context_tokens,
                    compacted=False,  # Naive never compacts
                    tools_called=[tc.name for tc in response.tool_calls],
                )

            turns.append(turn)

        # Build metrics
        elapsed_ms = (time.time_ns() - start_ns) // 1_000_000
        final_context_tokens = self._estimate_tokens(messages)

        metrics = {
            "iterations": len(turns),
            "tool_calls": total_tools_used,
            "message_count_final": len(messages),
            "context_tokens_final": final_context_tokens,
            "token_input": total_tokens_in,
            "token_output": total_tokens_out,
            "latency_ms": elapsed_ms,
            # Context growth tracking
            "context_tokens_per_iteration": [t.context_tokens_estimate for t in turns],
        }

        return RunResult(
            runner_name=self.name,
            scenario_id=scenario.id,
            success=final_answer is not None,
            final_answer=final_answer,
            turns=turns,
            metrics=metrics,
            errors=errors,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _estimate_tokens(messages: List[Dict[str, str]]) -> int:
        """Rough token estimate: ~4 chars per token."""
        total_chars = sum(len(m.get("content", "")) for m in messages)
        return total_chars // 4
