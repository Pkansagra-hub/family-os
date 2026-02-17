"""
Smart ReAct runner -- the scratchpad-powered innovation.

Implements the managed ReAct loop with:
  1. Structured findings (facts extracted from tool results)
  2. LLM-based compaction (older turns summarized, not just appended)
  3. Budget tracking (tool calls, iterations, tokens, time)
  4. Sub-agent management (nested loops with inherited budget)
  5. Failure tracking (recovery from tool errors)
  6. Cognitive write audit trail

The scratchpad keeps context bounded at ~4-5K tokens regardless of
how many iterations run, while maintaining perfect fact recall.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

from core.models import (
    Finding,
    LoopBudget,
    Message,
    RunResult,
    Scenario,
    Scratchpad,
    ToolResult,
    TurnRecord,
)
from core.protocols import LLMClient, LLMResponse, ToolRegistry
from eval import trace as T

logger = logging.getLogger("react_poc.smart")

# Tools that write to SessionState directly (cognitive + signal).
# Their responses are just confirmations ({success: true, id: ...}).
# Extracting findings from them would duplicate data already in
# SessionState and pollute KNOWN FACTS with meta-noise.
COGNITIVE_TOOLS = frozenset(
    {
        "acknowledge",
        "update_beliefs",
        "update_scoreboard",
        "update_clarifications",
        "update_narrative",
        "refine_affect",
        "promote_belief",
    }
)


class SmartReactRunner:
    """
    Smart ReAct loop with managed scratchpad.

    Instead of accumulating messages forever, this runner:
    - Extracts structured findings from every tool result
    - Compacts older messages via LLM summarization
    - Injects findings, budget status, and failure history into context
    - Manages sub-agent hierarchies with budget inheritance
    - Keeps context bounded regardless of iteration count

    This is the production-ready pattern specified in ADR-0098.
    """

    def __init__(self, max_iterations: int = 50):
        self.max_iterations = max_iterations

    @property
    def name(self) -> str:
        return "smart_react"

    async def run(
        self,
        scenario: Scenario,
        tools: ToolRegistry,
        llm: LLMClient,
        depth: int = 0,
        parent_scratchpad: Optional[Scratchpad] = None,
        budget_override: Optional[LoopBudget] = None,
        trace: bool = False,
    ) -> RunResult:
        """Execute a scenario using the managed scratchpad."""
        started_at = datetime.now(timezone.utc).isoformat()

        # Create scratchpad
        budget = budget_override or LoopBudget(
            max_tools=scenario.max_tools,
            max_iterations=min(scenario.max_iterations, self.max_iterations),
            timeout_ms=300_000,  # 5 min -- generous for PoC (LLM calls dominate wall-clock)
        )

        scratchpad = Scratchpad(
            system_prompt=scenario.system_prompt,
            user_query=scenario.user_query,
            tier=scenario.tier,
            budget=budget,
            depth=depth,
            parent_turn_id=parent_scratchpad.turn_id if parent_scratchpad else None,
        )

        # Initialize messages with user query
        scratchpad.messages.append(Message(role="user", content=scenario.user_query))

        tool_declarations = tools.get_tool_declarations()
        turns: List[TurnRecord] = []
        errors: List[str] = []
        total_compactions = 0
        max_nesting = depth

        while not scratchpad.is_complete():
            try:
                iter_start_ns = time.time_ns()
                scratchpad.budget.consume_iteration()
                scratchpad.iteration += 1

                # 1. BUILD CONTEXT via scratchpad
                context_messages = scratchpad.to_llm_messages()
                context_tokens = sum(len(m.get("content", "")) for m in context_messages) // 4

                # Withhold final_answer from declarations during early forced iterations
                iter_tools = tool_declarations
                should_force = scenario.force_tool_call
                current_iter = scratchpad.iteration
                if (
                    scenario.min_tool_iterations > 0
                    and current_iter <= scenario.min_tool_iterations
                ):
                    iter_tools = [t for t in tool_declarations if t["name"] != "final_answer"]
                elif (
                    current_iter > scenario.min_tool_iterations and scenario.min_tool_iterations > 0
                ):
                    should_force = False

                # Context preservation trace: log findings available at this iteration
                findings_keys = sorted(scratchpad.findings.keys())
                logger.debug(
                    "[SMART iter=%d] ctx_tokens=%d tools=%d should_force=%s min_tool_iter=%d findings_available=%d",
                    current_iter,
                    context_tokens,
                    len(iter_tools),
                    should_force,
                    scenario.min_tool_iterations,
                    len(findings_keys),
                )
                if findings_keys:
                    logger.debug(
                        "[SMART iter=%d] CONTEXT PRESERVATION -- findings injected into LLM context: %s",
                        current_iter,
                        findings_keys,
                    )
                # Log the system prompt length (contains injected findings + budget)
                sys_msg = next((m for m in context_messages if m.get("role") == "system"), None)
                if sys_msg:
                    logger.debug(
                        "[SMART iter=%d] system_prompt_length=%d (includes KNOWN FACTS + BUDGET STATUS)",
                        current_iter,
                        len(sys_msg.get("content", "")),
                    )

                # Trace: iteration start
                if trace:
                    T.trace_iteration_start(
                        runner_name="smart_react",
                        iteration=current_iter,
                        context_tokens=context_tokens,
                        message_count=len(context_messages),
                        tools_available=len(iter_tools),
                        force_tool_call=should_force,
                        findings_available=findings_keys if findings_keys else None,
                    )

                # 2. CALL LLM with managed context (not full history)
                try:
                    response: LLMResponse = await llm.generate(
                        messages=context_messages,
                        tools=iter_tools,
                        force_tool_call=should_force,
                    )
                except Exception as e:
                    errors.append(f"LLM error at iteration {scratchpad.iteration}: {str(e)}")
                    break

                logger.debug(
                    "[SMART iter=%d] response: has_tool_calls=%s tool_count=%d text_len=%d",
                    current_iter,
                    response.has_tool_calls,
                    len(response.tool_calls),
                    len(response.text) if response.text else 0,
                )
                if response.tool_calls:
                    for tc in response.tool_calls:
                        logger.debug("  -> tool_call: %s(%s)", tc.name, str(tc.arguments)[:200])

                turn = TurnRecord(
                    iteration=scratchpad.iteration,
                    context_tokens_estimate=context_tokens,
                )

                # Check for text-only response (no tool calls = final answer)
                if not response.has_tool_calls:
                    scratchpad.final_content = response.text or ""
                    turn.assistant_message = scratchpad.final_content
                    turn.final_answer_fragment = scratchpad.final_content
                    turn.findings_snapshot = {
                        k: {"value": v.value, "type": v.type}
                        for k, v in scratchpad.findings.items()
                    }
                    if trace:
                        T.trace_llm_decision(
                            iteration=current_iter,
                            tool_calls=[],
                            reasoning_text=response.text,
                            is_final_answer=True,
                            final_answer_text=scratchpad.final_content,
                            tokens_in=response.tokens_in,
                            tokens_out=response.tokens_out,
                        )
                    turns.append(turn)
                    break

                # Check for final_answer tool
                is_final = False
                for tc in response.tool_calls:
                    if tc.name == "final_answer":
                        scratchpad.final_content = tc.arguments.get("answer", "")
                        is_final = True
                        break

                if is_final:
                    turn.assistant_message = scratchpad.final_content
                    turn.final_answer_fragment = scratchpad.final_content
                    turn.tool_calls = response.tool_calls
                    turn.findings_snapshot = {
                        k: {"value": v.value, "type": v.type}
                        for k, v in scratchpad.findings.items()
                    }
                    if trace:
                        T.trace_llm_decision(
                            iteration=current_iter,
                            tool_calls=[],
                            is_final_answer=True,
                            final_answer_text=scratchpad.final_content,
                            tokens_in=response.tokens_in,
                            tokens_out=response.tokens_out,
                        )
                    turns.append(turn)
                    break

                # Add assistant reasoning to messages
                if response.text:
                    scratchpad.messages.append(
                        Message(
                            role="assistant",
                            content=response.text,
                        )
                    )

                # Trace: LLM decision (tool calls)
                if trace:
                    T.trace_llm_decision(
                        iteration=current_iter,
                        tool_calls=[
                            {"name": tc.name, "arguments": tc.arguments}
                            for tc in response.tool_calls
                        ],
                        reasoning_text=response.text,
                        tokens_in=response.tokens_in,
                        tokens_out=response.tokens_out,
                    )

                # 3. EXECUTE TOOLS
                turn.tool_calls = response.tool_calls
                tool_results: List[ToolResult] = []
                tools_called: List[str] = []

                for tc in response.tool_calls:
                    tools_called.append(tc.name)

                    # Handle sub-agent spawning
                    if tc.name == "spawn_agent":
                        if trace:
                            T.trace_sub_agent_spawn(
                                agent_id=f"pending-{tc.call_id}",
                                task=tc.arguments.get("task", ""),
                                tool_budget=tc.arguments.get("tool_budget", 5),
                                depth=depth + 1,
                            )
                        agent_result = await self._handle_spawn_agent(
                            scratchpad=scratchpad,
                            task=tc.arguments.get("task", ""),
                            tool_budget=tc.arguments.get("tool_budget", 5),
                            tools=tools,
                            llm=llm,
                            scenario=scenario,
                            trace=trace,
                        )
                        max_nesting = max(max_nesting, depth + 1)
                        result = ToolResult(
                            tool_name="spawn_agent",
                            call_id=tc.call_id,
                            ok=True,
                            output=agent_result,
                        )
                        tool_results.append(result)
                        scratchpad.record_tool_result(tc, result)
                        if trace:
                            T.trace_sub_agent_complete(
                                agent_id=agent_result.get("agent_id", "?"),
                                status=agent_result.get("status", "unknown"),
                                findings_count=agent_result.get("findings_count", 0),
                                iterations_used=agent_result.get("iterations_used", 0),
                                answer=agent_result.get("answer"),
                                error=agent_result.get("error"),
                            )
                        continue

                    # Execute normal tool
                    if scratchpad.budget.remaining_tools <= 0:
                        result = ToolResult(
                            tool_name=tc.name,
                            call_id=tc.call_id,
                            ok=False,
                            error_code="BUDGET_EXHAUSTED",
                            error_message="No tool calls remaining in budget",
                        )
                        tool_results.append(result)
                        scratchpad.record_tool_result(tc, result)
                        continue

                    result = await tools.execute(tc.name, tc.arguments)
                    result.call_id = tc.call_id
                    tool_results.append(result)

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

                    # 3b. Record tool result WITHOUT findings for now
                    #     (findings will be batch-extracted after all tools run)
                    scratchpad.record_tool_result(tc, result)

                # -- BATCH EXTRACTION: one LLM call for READ + ACTION tools only --
                # Cognitive/signal tools (COGNITIVE_TOOLS) write to SessionState
                # directly.  Skip them -- only extract from tools that produce
                # novel external data (read/action/spawn results).
                extractable = [
                    (tr.tool_name, tr.output)
                    for tr in tool_results
                    if tr.ok and tr.output and tr.tool_name not in COGNITIVE_TOOLS
                ]
                all_findings: List[Finding] = []
                if extractable:
                    try:
                        all_findings = await llm.extract_findings_batch(extractable)
                    except Exception:
                        # Fallback: one generic finding per tool result
                        for tname, tout in extractable:
                            all_findings.append(
                                Finding(
                                    key=f"{tname}_result_{scratchpad.iteration}",
                                    value=str(tout)[:200],
                                    type="fact",
                                    source_tool=tname,
                                )
                            )

                    scratchpad.add_findings(all_findings)

                    # Context preservation trace: log what was extracted
                    if all_findings:
                        logger.debug(
                            "[SMART iter=%d] BATCH FINDINGS EXTRACTED (%d findings from %d tools): %s",
                            current_iter,
                            len(all_findings),
                            len(extractable),
                            [f"{f.key}={str(f.value)[:80]}" for f in all_findings],
                        )
                        if trace:
                            T.trace_findings_extracted(
                                tool_name=f"batch({','.join(t[0] for t in extractable)})",
                                findings=[
                                    {"key": f.key, "value": f.value, "type": f.type}
                                    for f in all_findings
                                ],
                            )

                turn.tool_results = tool_results
                turn.assistant_message = response.text or ""
                turn.findings_snapshot = {
                    k: {"value": v.value, "type": v.type} for k, v in scratchpad.findings.items()
                }

                # Context preservation trace: log cumulative findings after this iteration
                logger.debug(
                    "[SMART iter=%d] CUMULATIVE FINDINGS: %d total (%s)",
                    current_iter,
                    len(scratchpad.findings),
                    sorted(scratchpad.findings.keys()),
                )

                # 4. CHECK BUDGET (handled by scratchpad.is_complete())
                # Update elapsed time
                scratchpad.budget.elapsed_ms = scratchpad.elapsed_ms()

                # 5. COMPACT IF NEEDED
                compacted = False
                msgs_before_compact = len(scratchpad.messages)
                if scratchpad.needs_compaction():
                    try:
                        await scratchpad.compact_messages(llm.summarize_messages)
                        total_compactions += 1
                        compacted = True
                        if trace:
                            T.trace_compaction(
                                messages_before=msgs_before_compact,
                                messages_after=len(scratchpad.messages),
                                iteration=current_iter,
                            )
                    except Exception as e:
                        errors.append(
                            f"Compaction failed at iteration {scratchpad.iteration}: {str(e)}"
                        )

                # 6. SNAPSHOT ITERATION
                iter_ms = (time.time_ns() - iter_start_ns) // 1_000_000
                scratchpad.snapshot_iteration(
                    thought=response.text,
                    tools_called=tools_called,
                    tokens_in=response.tokens_in,
                    tokens_out=response.tokens_out,
                    duration_ms=iter_ms,
                    compacted=compacted,
                )

                # Trace: iteration end
                if trace:
                    T.trace_iteration_end(
                        iteration=current_iter,
                        cumulative_findings=len(scratchpad.findings),
                        context_tokens=context_tokens,
                        compacted=compacted,
                        tools_called=tools_called,
                    )

                turns.append(turn)

            except Exception as exc:
                logger.error(
                    "[SMART] Unhandled error at iteration %d: %s",
                    scratchpad.iteration,
                    exc,
                    exc_info=True,
                )
                errors.append(f"Unhandled error at iteration {scratchpad.iteration}: {exc}")
                break

        # Build final answer from scratchpad
        final_answer = scratchpad.final_content

        # If budget exhausted without final answer, synthesize from findings
        if not final_answer and scratchpad.budget.exhausted:
            summary_parts = ["Budget exhausted. Summary of findings:"]
            summary_parts.append(scratchpad.findings_summary())
            final_answer = "\n".join(summary_parts)
            errors.append("ITERATION_BUDGET_EXHAUSTED")

        # Build metrics
        elapsed_ms = scratchpad.elapsed_ms()

        # Compute final context token estimate from the ACTUAL scratchpad context
        # (not just message count -- the old "scratchpad_messages_final" was a count, not tokens)
        final_context = scratchpad.to_llm_messages()
        final_context_tokens = sum(len(m.get("content", "")) for m in final_context) // 4

        metrics = {
            "iterations": len(turns),
            "tool_calls": scratchpad.budget.tools_used,
            "compactions": total_compactions,
            "scratchpad_messages_final": len(scratchpad.messages),
            "context_tokens_final": final_context_tokens,
            "findings_count": len(scratchpad.findings),
            "typed_findings_count": len(set(f.type for f in scratchpad.findings.values())),
            "failed_count": len(scratchpad.failed_attempts),
            "cognitive_writes_count": len(scratchpad.cognitive_writes),
            "remaining_tool_calls": scratchpad.budget.remaining_tools,
            "remaining_iterations": scratchpad.budget.remaining_iterations,
            "token_input": scratchpad.budget.tokens_in,
            "token_output": scratchpad.budget.tokens_out,
            "elapsed_budget_ms": elapsed_ms,
            "latency_ms": elapsed_ms,
            "sub_agent_count": len(scratchpad.sub_agents),
            "max_nesting_depth": max_nesting,
            # Context growth tracking (should stay flat for smart)
            "context_tokens_per_iteration": [t.context_tokens_estimate for t in turns],
            # Findings accumulation per iteration (proves context preservation)
            "findings_per_iteration": [len(t.findings_snapshot) for t in turns],
        }

        return RunResult(
            runner_name=self.name,
            scenario_id=scenario.id,
            success=final_answer is not None and "BUDGET_EXHAUSTED" not in (final_answer or ""),
            final_answer=final_answer,
            turns=turns,
            metrics=metrics,
            errors=errors,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc).isoformat(),
            total_compactions=total_compactions,
            total_findings=len(scratchpad.findings),
            total_sub_agents=len(scratchpad.sub_agents),
            max_nesting_depth=max_nesting,
            budget_overspend=scratchpad.budget.tools_used > scratchpad.budget.max_tools,
        )

    # ------------------------------------------------------------------
    # Sub-agent handling
    # ------------------------------------------------------------------

    async def _handle_spawn_agent(
        self,
        scratchpad: Scratchpad,
        task: str,
        tool_budget: int,
        tools: ToolRegistry,
        llm: LLMClient,
        scenario: Scenario,
        trace: bool = False,
    ) -> Dict:
        """Spawn a sub-agent with inherited budget and run it."""
        # Create sub-agent record in parent scratchpad
        agent = scratchpad.spawn_sub_agent(
            task=task,
            tool_budget=tool_budget,
            depth=scratchpad.depth + 1,
        )

        # Create a sub-scenario for the nested loop
        sub_scenario = Scenario(
            id=f"{scenario.id}_sub_{agent.agent_id}",
            name=f"Sub-agent: {task[:50]}",
            system_prompt=(
                f"You are a specialized sub-agent. Your task: {task}\n"
                f"Complete this task efficiently using the available tools.\n"
                f"When done, use final_answer to report your findings."
            ),
            user_query=task,
            tier=scenario.tier,
            max_iterations=tool_budget + 2,
            max_tools=tool_budget,
        )

        # Run nested smart loop
        try:
            sub_result = await self.run(
                scenario=sub_scenario,
                tools=tools,
                llm=llm,
                depth=scratchpad.depth + 1,
                parent_scratchpad=scratchpad,
                budget_override=agent.budget_consumed,
                trace=trace,
            )

            # Extract findings from sub-result
            sub_findings = []
            if sub_result.turns:
                last_turn = sub_result.turns[-1]
                for key, val in last_turn.findings_snapshot.items():
                    sub_findings.append(
                        Finding(
                            key=key,
                            value=val.get("value", ""),
                            type=val.get("type", "fact"),
                            source_tool=f"sub_agent_{agent.agent_id}",
                        )
                    )

            # Complete sub-agent in parent scratchpad
            scratchpad.complete_sub_agent(
                agent_id=agent.agent_id,
                findings=sub_findings,
                result=sub_result.final_answer,
            )

            return {
                "agent_id": agent.agent_id,
                "status": "complete",
                "findings_count": len(sub_findings),
                "answer": sub_result.final_answer,
                "iterations_used": len(sub_result.turns),
                "tools_used": sub_result.metrics.get("tool_calls", 0),
            }

        except Exception as e:
            scratchpad.complete_sub_agent(
                agent_id=agent.agent_id,
                findings=[],
                error=str(e),
            )
            return {
                "agent_id": agent.agent_id,
                "status": "failed",
                "error": str(e),
            }
