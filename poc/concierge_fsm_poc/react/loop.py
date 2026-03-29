"""FSM-Aware ReAct Loop -- Epic 3.3 (LOOP-001, LOOP-002, LOOP-003).

Orchestrates LLM reasoning through structured tool-calling iterations
within FSM state rails.  The loop:

1. Builds context from SessionState snapshot + Scratchpad findings
2. Calls GeminiClient with tier-filtered tool declarations
3. Routes tool results through COGNITIVE_TOOLS filter
4. Manages FSM state transitions (DISPATCHING -> COMPANIONING ->
   PROGRESSING -> DELIVERING)
5. Handles interrupts, budget exhaustion, and compaction

FSM transition map (fired by this loop):
    LOW  path:  DISPATCHING -(DISPATCH_COMPLETE)-> DELIVERING
    MEDIUM path: DISPATCHING -(PRELIMINARY_ACK_SENT)-> COMPANIONING
                 COMPANIONING -(PROGRESS_RECEIVED)-> PROGRESSING
                 PROGRESSING|COMPANIONING -(DISPATCH_COMPLETE)-> DELIVERING
    Interrupt:   any interruptible -(INTERRUPT_DETECTED)-> INTERRUPT_HANDLING
                 INTERRUPT_HANDLING -(INTERRUPT_HANDLED)-> ACKING

RESPONSE_DELIVERED is NOT fired here -- the demo runner fires it after
displaying the response to the user.

COGNITIVE_TOOLS routing:
    Tools in COGNITIVE_TOOLS (update_beliefs, update_scoreboard, etc.)
    write directly to SessionState.  Their results are confirmation dicts,
    NOT raw data.  The loop records a ToolEntry but does NOT extract
    findings.

    Tools NOT in COGNITIVE_TOOLS (read/action/meta) produce raw data.
    Their results are passed to ``llm.extract_findings_batch()`` and the
    resulting Finding objects are added to the scratchpad.

Files: ``react/loop.py``  (~280 lines)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from poc.concierge_fsm_poc.fsm.controller import Event, FSMController, State
from poc.concierge_fsm_poc.fsm.phase1_mock import Phase1Result
from poc.concierge_fsm_poc.llm.client import GeminiClient, build_system_prompt
from poc.concierge_fsm_poc.react.events import (
    LoopEvent,
    LoopEventHandler,
    LoopEventType,
    NullEventHandler,
)
from poc.concierge_fsm_poc.react.scratchpad import (
    COGNITIVE_TOOLS,
    LoopBudget,
    Scratchpad,
    Tier,
)
from poc.concierge_fsm_poc.tools.registry import ToolRegistry

logger = logging.getLogger("concierge_fsm.react")


# ---------------------------------------------------------------------------
# ReActResult -- output of the loop
# ---------------------------------------------------------------------------


@dataclass
class ReActResult:
    """Structured output of a ReAct loop execution.

    Contains the final response text, execution metrics, and a complete
    trace of FSM transitions fired during the loop.
    """

    final_response: str = ""
    tool_calls_made: int = 0
    iterations: int = 0
    findings_count: int = 0
    fsm_transitions: list[tuple[str, str, str]] = field(default_factory=list)
    budget_exhausted: bool = False
    interrupted: bool = False
    interrupt_source: str = ""
    error: str | None = None
    partial_response: str = ""


# ---------------------------------------------------------------------------
# InterruptSignal -- mutable flag container
# ---------------------------------------------------------------------------


@dataclass
class InterruptSignal:
    """Mutable flag checked at the top of each iteration.

    Set by calling ``ReActLoop.signal_interrupt()`` from the demo runner.
    The loop checks ``pending`` at the start of each iteration and
    handles the interrupt if the FSM is in an interruptible state.
    """

    pending: bool = False
    source: str = ""
    replacement_message: str = ""


# ---------------------------------------------------------------------------
# ReActLoop
# ---------------------------------------------------------------------------


class ReActLoop:
    """FSM-aware ReAct loop that drives Phase 2.

    Integrates FSMController, ToolRegistry, GeminiClient, and Scratchpad
    into a single coordinated reasoning loop.

    Parameters
    ----------
    fsm:
        FSMController instance (expected to be in DISPATCHING on entry).
    registry:
        ToolRegistry with all tools registered.
    llm:
        GeminiClient for LLM calls and finding extraction.
    scratchpad:
        Scratchpad for this turn (created fresh by the demo runner).
    """

    def __init__(
        self,
        fsm: FSMController,
        registry: ToolRegistry,
        llm: GeminiClient,
        scratchpad: Scratchpad,
        event_handler: LoopEventHandler | None = None,
    ) -> None:
        self.fsm = fsm
        self.registry = registry
        self.llm = llm
        self.scratchpad = scratchpad
        self.event_handler: LoopEventHandler = event_handler or NullEventHandler()
        self.interrupt = InterruptSignal()
        self._fsm_transitions: list[tuple[str, str, str]] = []
        self._tool_cache: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------ #
    # Event emission
    # ------------------------------------------------------------------ #

    def _emit(self, event_type: LoopEventType, **data: Any) -> None:
        """Emit a loop event to the attached handler."""
        self.event_handler.on_event(LoopEvent(type=event_type, data=data))

    # ------------------------------------------------------------------ #
    # FSM transition helper
    # ------------------------------------------------------------------ #

    def _fire(self, event: Event) -> tuple[State, list[Any]]:
        """Fire an FSM event, record the transition, and sync scratchpad."""
        from_state = self.fsm.state
        new_state, actions = self.fsm.transition(event)
        self._fsm_transitions.append((from_state.value, event.value, new_state.value))
        self.scratchpad.fsm_state = new_state
        self._emit(
            LoopEventType.FSM_TRANSITION,
            from_state=from_state.value,
            event=event.value,
            to_state=new_state.value,
        )
        logger.info(
            "FSM: %s --%s--> %s (actions: %s)",
            from_state.value,
            event.value,
            new_state.value,
            [a.value for a in actions],
        )
        return new_state, actions

    # ------------------------------------------------------------------ #
    # Tool execution
    # ------------------------------------------------------------------ #

    def _execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a single tool via the registry.

        Returns a dict with ``success`` bool and either ``data`` or ``error``.
        Read-only tools are cached for 5 seconds within the same loop run
        to avoid redundant calls (the LLM often calls discover_capabilities
        and read_session_state on every iteration).
        """
        _CACHEABLE_TOOLS = frozenset(
            {"read_session_state", "recall_memory", "discover_capabilities", "summarize_context"}
        )
        if tool_name in _CACHEABLE_TOOLS:
            cache_key = f"{tool_name}:{json.dumps(arguments, sort_keys=True, default=str)}"
            if cache_key in self._tool_cache:
                self._emit(
                    LoopEventType.TOOL_CACHE_HIT,
                    tool_name=tool_name,
                    arguments=arguments,
                )
                logger.debug("Cache hit: %s", tool_name)
                return self._tool_cache[cache_key]

        tool_def = self.registry.get(tool_name)
        try:
            result = tool_def.handler(**arguments)
            rv: dict[str, Any] = {"success": True, "data": result}
        except Exception as e:
            logger.warning("Tool %s failed: %s", tool_name, e)
            rv = {"success": False, "error": str(e)}

        if tool_name in _CACHEABLE_TOOLS and rv.get("success"):
            cache_key = f"{tool_name}:{json.dumps(arguments, sort_keys=True, default=str)}"
            self._tool_cache[cache_key] = rv

        return rv

    # ------------------------------------------------------------------ #
    # Core loop (LOOP-001)
    # ------------------------------------------------------------------ #

    async def run(
        self,
        phase1: Phase1Result,
        user_message: str,
        *,
        turn_number: int = 1,
        session_overview: dict[str, Any] | None = None,
        family_persona: dict[str, Any] | None = None,
    ) -> ReActResult:
        """Execute the Phase 2 ReAct loop.

        Expected FSM state on entry: DISPATCHING (after PHASE1_COMPLETE
        or MAX_ROUNDS_REACHED).

        Parameters
        ----------
        phase1:
            Result from Phase 1 classification.
        user_message:
            The raw user message for this turn.
        turn_number:
            Current turn number (injected into system prompt).
        session_overview:
            SessionState overview dict (from ``read_session_state(section=None)``).
        family_persona:
            Family persona dict with members, allergies, preferences.

        Returns
        -------
        ``ReActResult`` with final response, metrics, and FSM trace.
        """
        self._fsm_transitions = []
        self._tool_cache.clear()  # per-turn cache: fresh each run
        self.scratchpad.user_query = user_message
        self.scratchpad.tier = Tier(phase1.tier)
        self.scratchpad.budget = LoopBudget.for_tier(Tier(phase1.tier))
        self.scratchpad.fsm_state = self.fsm.state

        tier = phase1.tier
        safety_band = phase1.safety_band

        # Tier-filtered tool declarations (rebuilt once per run)
        tool_declarations = self.registry.get_llm_declarations(tier)

        # Safety band filtering: remove action tools for RED/CRISIS
        if safety_band in ("RED", "CRISIS"):
            _ACTION_TOOLS = frozenset({"invoke_capability", "store_memory", "commit_plan"})
            tool_declarations = [t for t in tool_declarations if t["name"] not in _ACTION_TOOLS]

        # MEDIUM path: fire PRELIMINARY_ACK_SENT -> COMPANIONING (T7)
        if tier == "MEDIUM" and self.fsm.state == State.DISPATCHING:
            self._fire(Event.PRELIMINARY_ACK_SENT)

        # Conversation messages accumulated during the loop
        messages: list[dict[str, Any]] = []
        _force_text_only = False  # set by cycle detection to strip tools

        # ---- Main iteration loop ----------------------------------------
        while not self.scratchpad.is_complete:
            # -- LOOP-003: Check interrupt at top of each iteration --------
            if self.interrupt.pending and self.fsm.is_interruptible():
                return self._handle_interrupt()

            self.scratchpad.iteration += 1
            self.scratchpad.budget.consume_iteration()
            self.scratchpad.budget.elapsed_ms = self.scratchpad.elapsed_ms()
            self._emit(LoopEventType.ITERATION_START, iteration=self.scratchpad.iteration)

            # -- Build system prompt (rebuilt every iteration) -------------
            system_prompt = build_system_prompt(
                fsm_state=self.fsm.state.value,
                turn_number=turn_number,
                tier=tier,
                safety_band=safety_band,
                session_overview=session_overview,
                tool_declarations=tool_declarations,
                family_persona=family_persona,
            )
            self.scratchpad.system_prompt = system_prompt

            # -- Build messages for LLM -----------------------------------
            iter_messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]

            # Inject findings context as system-level context
            # (NOT as assistant, which makes the model anchor on stale data)
            findings_text = self.scratchpad.findings_summary()
            if findings_text:
                iter_messages.append(
                    {
                        "role": "system",
                        "content": f"## Known Facts From Previous Tool Calls\n{findings_text}",
                    }
                )

            # Append accumulated conversation messages
            iter_messages.extend(messages)

            # -- Call LLM (streaming) -------------------------------------
            # When cycle detection fired, strip tools to force text-only
            iter_tools = None if _force_text_only else tool_declarations
            self._emit(
                LoopEventType.LLM_CALL_START,
                message_count=len(iter_messages),
                tool_count=len(iter_tools) if iter_tools else 0,
            )
            response = await self.llm.generate_stream(
                iter_messages,
                tools=iter_tools,
                on_text_delta=lambda t: self._emit(LoopEventType.TEXT_DELTA, text=t),
            )
            _force_text_only = False  # reset after use
            self._emit(
                LoopEventType.LLM_CALL_END,
                has_tool_calls=response.has_tool_calls,
                tokens_in=response.tokens_in,
                tokens_out=response.tokens_out,
            )

            # Track token spend
            self.scratchpad.budget.add_tokens(response.tokens_in, response.tokens_out)

            # -- Thought capture: if the LLM returned both text and tool
            #    calls, the text is its reasoning chain ("thinking").
            #    Record it for debugging visibility.
            if response.text and response.has_tool_calls:
                thought = response.text.strip()
                if thought:
                    self.scratchpad.record_thought(thought, self.scratchpad.iteration)
                    self._emit(
                        LoopEventType.THOUGHT,
                        text=thought[:300],
                        iteration=self.scratchpad.iteration,
                    )

            # -- If LLM returns text only: done ----------------------------
            if not response.has_tool_calls:
                # Guard against empty/whitespace responses early in the loop
                response_text = (response.text or "").strip()
                if not response_text and self.scratchpad.iteration < 3:
                    # Empty response -- nudge the model to try again
                    messages.append(
                        {
                            "role": "user",
                            "content": (
                                "Please provide a helpful response to the user's "
                                "request based on what you know so far."
                            ),
                        }
                    )
                    continue

                if not response_text:
                    # Empty response after iteration 3+.  Don't return empty;
                    # fall through to the budget-exhausted path which builds
                    # a proper findings-based response.
                    logger.warning(
                        "Empty LLM response at iteration %d, falling through to "
                        "budget-exhausted path",
                        self.scratchpad.iteration,
                    )
                    break

                # Fire DISPATCH_COMPLETE from current dispatch-phase state
                if self.fsm.state in (
                    State.DISPATCHING,
                    State.COMPANIONING,
                    State.PROGRESSING,
                ):
                    self._fire(Event.DISPATCH_COMPLETE)

                self._emit(
                    LoopEventType.LOOP_COMPLETE,
                    iterations=self.scratchpad.iteration,
                    tools_used=self.scratchpad.budget.tools_used,
                    budget_exhausted=False,
                )
                return ReActResult(
                    final_response=response_text,
                    tool_calls_made=self.scratchpad.budget.tools_used,
                    iterations=self.scratchpad.iteration,
                    findings_count=len(self.scratchpad.findings),
                    fsm_transitions=list(self._fsm_transitions),
                    budget_exhausted=False,
                )

            # -- Process tool calls ----------------------------------------
            non_cognitive_results: list[tuple[str, Any]] = []

            # Append the model's response content (contains all function_call
            # parts with thought_signature intact) as a single model turn.
            # The _raw_content key lets _build_contents pass it through
            # directly instead of reconstructing it.
            raw_model_content = None
            if response.raw and hasattr(response.raw, "candidates") and response.raw.candidates:
                candidate = response.raw.candidates[0]
                if candidate.content:
                    raw_model_content = candidate.content
            if raw_model_content is not None:
                messages.append(
                    {
                        "role": "function_call",
                        "_raw_content": raw_model_content,
                        "content": "",
                    }
                )

            for tc in response.tool_calls:
                self._emit(
                    LoopEventType.TOOL_CALL_START,
                    tool_name=tc.name,
                    arguments=tc.arguments,
                )
                result = self._execute_tool(tc.name, tc.arguments)

                if tc.name in COGNITIVE_TOOLS:
                    # Cognitive/signal: record ToolEntry only, skip extraction
                    summary = _cognitive_summary(result)
                    self.scratchpad.record_tool_call(
                        tc.name,
                        tc.arguments,
                        ok=result.get("success", False),
                        summary=f"[cognitive] {summary}",
                    )
                    self._emit(
                        LoopEventType.TOOL_CALL_END,
                        tool_name=tc.name,
                        success=result.get("success", False),
                        summary=summary[:120],
                    )
                    # Cognitive tools: send a minimal tool_response
                    # (no raw data to echo -- the data is already in SessionState)
                    # The function_call part is already in the model response
                    # content appended above.
                    messages.append(
                        {
                            "role": "tool_response",
                            "tool_name": tc.name,
                            "tool_result": {"status": "ok", "message": summary[:200]},
                            "content": "",
                        }
                    )
                else:
                    # Read/action/meta: queue for finding extraction
                    if result.get("success"):
                        non_cognitive_results.append((tc.name, result["data"]))
                    else:
                        # MutationGuard: record tool failure as a finding so
                        # the model cannot claim the action succeeded.
                        from poc.concierge_fsm_poc.react.scratchpad import Finding

                        error_msg = str(result.get("error", "unknown error"))
                        self.scratchpad.add_findings(
                            [
                                Finding(
                                    key=f"{tc.name}_FAILED",
                                    value=f"TOOL FAILED: {error_msg}",
                                    type="error",
                                    source_tool=tc.name,
                                )
                            ]
                        )
                    self.scratchpad.record_tool_call(
                        tc.name,
                        tc.arguments,
                        ok=result.get("success", False),
                        summary=str(result.get("data", result.get("error", "")))[:200],
                    )
                    self._emit(
                        LoopEventType.TOOL_CALL_END,
                        tool_name=tc.name,
                        success=result.get("success", False),
                        summary=str(result.get("data", result.get("error", "")))[:120],
                    )
                    # Non-cognitive: append tool_response only
                    # (function_call is already in the model response content above)
                    result_data = (
                        result.get("data", {})
                        if result.get("success")
                        else {
                            "error": str(result.get("error", "unknown")),
                            "status": "FAILED",
                            "instruction": "Do NOT claim this action succeeded. "
                            "Tell the user the action failed.",
                        }
                    )
                    # Ensure result_data is a dict for function_response
                    if not isinstance(result_data, dict):
                        result_data = {"result": str(result_data)[:500]}
                    messages.append(
                        {
                            "role": "tool_response",
                            "tool_name": tc.name,
                            "tool_result": result_data,
                            "content": "",
                        }
                    )

            # -- Extract findings from non-cognitive tool results ----------
            # Direct extraction: create findings from raw tool results
            # without an extra LLM call.  The model already has the full
            # tool results in its message history; this just populates
            # the scratchpad for the budget-exhausted fallback path.
            if non_cognitive_results:
                from poc.concierge_fsm_poc.react.scratchpad import Finding

                findings: list[Finding] = []
                for tool_name, raw_data in non_cognitive_results:
                    if isinstance(raw_data, dict):
                        for k, v in raw_data.items():
                            v_str = str(v)
                            if len(v_str) > 300:
                                v_str = v_str[:300] + "..."
                            findings.append(
                                Finding(
                                    key=f"{tool_name}_{k}",
                                    value=v_str,
                                    type="fact",
                                    source_tool=tool_name,
                                )
                            )
                    else:
                        findings.append(
                            Finding(
                                key=f"{tool_name}_result",
                                value=str(raw_data)[:300],
                                type="fact",
                                source_tool=tool_name,
                            )
                        )
                self.scratchpad.add_findings(findings)
                for f in findings:
                    self._emit(
                        LoopEventType.FINDING_EXTRACTED,
                        key=f.key,
                        value=str(f.value)[:120],
                        source_tool=f.source_tool,
                    )

            # -- MEDIUM: PROGRESS_RECEIVED after first tool batch ----------
            if (
                tier == "MEDIUM"
                and self.fsm.state == State.COMPANIONING
                and self.scratchpad.budget.tools_used > 0
            ):
                self._fire(Event.PROGRESS_RECEIVED)

            # -- Compaction check ------------------------------------------
            if self.scratchpad.needs_compaction():
                summary = await self.llm.summarize_messages(messages)
                self.scratchpad.add_compaction_summary(summary)
                self._emit(LoopEventType.COMPACTION, summary_len=len(summary))
                messages = [
                    {
                        "role": "assistant",
                        "content": f"[Compacted]: {summary}",
                    }
                ]

            # -- Cycle detection -------------------------------------------
            if self._detect_cycle():
                recent_names = [e.tool_name for e in self.scratchpad.tool_history[-6:]]
                self._emit(
                    LoopEventType.CYCLE_DETECTED,
                    pattern=recent_names,
                    iteration=self.scratchpad.iteration,
                )
                logger.warning("Cycle detected: %s", recent_names)
                # Force the NEXT iteration to call LLM without tools,
                # guaranteeing a text-only response.
                _force_text_only = True
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "You are repeating the same tool calls. "
                            "Based on the facts you have gathered so far, "
                            "provide your best answer to the user now."
                        ),
                    }
                )

        # ---- Budget exhausted: generate best-effort response -------------
        if self.fsm.state in (
            State.DISPATCHING,
            State.COMPANIONING,
            State.PROGRESSING,
        ):
            self._fire(Event.DISPATCH_COMPLETE)

        # Build a clean natural-language fallback instead of dumping
        # raw scratchpad findings.  Summarise findings as bullet points
        # so the response reads like a concierge answer.
        if self.scratchpad.findings:
            bullets: list[str] = []
            for f in self.scratchpad.findings.values():
                if f.type == "error":
                    bullets.append(f"I encountered an issue: {f.value}")
                else:
                    bullets.append(f"{f.key.replace('_', ' ').title()}: {f.value}")
            body = "; ".join(bullets) if len(bullets) <= 3 else "\n".join(f"- {b}" for b in bullets)
            final_text = f"Here is what I found so far: {body}"
        else:
            final_text = (
                "I was unable to gather enough information to answer "
                "your request. Could you please try rephrasing?"
            )

        self._emit(
            LoopEventType.LOOP_COMPLETE,
            iterations=self.scratchpad.iteration,
            tools_used=self.scratchpad.budget.tools_used,
            budget_exhausted=True,
        )
        return ReActResult(
            final_response=final_text,
            tool_calls_made=self.scratchpad.budget.tools_used,
            iterations=self.scratchpad.iteration,
            findings_count=len(self.scratchpad.findings),
            fsm_transitions=list(self._fsm_transitions),
            budget_exhausted=True,
        )

    # ------------------------------------------------------------------ #
    # Interrupt handling (LOOP-003)
    # ------------------------------------------------------------------ #

    def _handle_interrupt(self) -> ReActResult:
        """Handle an interrupt detected at the top of a loop iteration.

        Fires INTERRUPT_DETECTED (-> INTERRUPT_HANDLING) and then
        INTERRUPT_HANDLED (-> ACKING).  Returns a ReActResult with
        ``interrupted=True`` and any partial findings.
        """
        source = self.interrupt.source

        # Fire FSM: current state -(INTERRUPT_DETECTED)-> INTERRUPT_HANDLING
        self._fire(Event.INTERRUPT_DETECTED)

        # Save partial findings as partial_response
        partial_response = ""
        if self.scratchpad.findings:
            partial_response = f"Partial results: {self.scratchpad.findings_summary()}"

        # Fire FSM: INTERRUPT_HANDLING -(INTERRUPT_HANDLED)-> ACKING
        self._fire(Event.INTERRUPT_HANDLED)

        # Reset interrupt flag
        self.interrupt.pending = False

        return ReActResult(
            final_response="",
            partial_response=partial_response,
            tool_calls_made=self.scratchpad.budget.tools_used,
            iterations=self.scratchpad.iteration,
            findings_count=len(self.scratchpad.findings),
            fsm_transitions=list(self._fsm_transitions),
            interrupted=True,
            interrupt_source=source,
        )

    # ------------------------------------------------------------------ #
    # External interrupt API (called by demo runner)
    # ------------------------------------------------------------------ #

    def signal_interrupt(
        self,
        source: str = "user",
        replacement_message: str = "",
    ) -> None:
        """Signal an interrupt to the loop.

        This sets the interrupt flag which is checked at the top of each
        iteration.  If the FSM is in an interruptible state, the loop
        will break and fire the interrupt FSM events.

        Parameters
        ----------
        source:
            Interrupt source: ``"user"``, ``"watchdog"``, ``"cancel"``,
            ``"timeout"``.
        replacement_message:
            The new user message that caused the interrupt (if any).
        """
        self.interrupt.pending = True
        self.interrupt.source = source
        self.interrupt.replacement_message = replacement_message

    # ------------------------------------------------------------------ #
    # Cycle detection
    # ------------------------------------------------------------------ #

    def _detect_cycle(self) -> bool:
        """Detect repeating tool-call patterns that indicate a stuck loop.

        Checks for three patterns in recent tool history:
        1. A-B-A-B alternating pair (last 6 calls)
        2. A-A-A same tool 3+ times in a row
        3. Same tool with similar arguments 3+ times (argument-aware)
        """
        history = self.scratchpad.tool_history
        if len(history) < 3:
            return False

        recent = [e.tool_name for e in history[-6:]]

        # Pattern 1: A-B-A-B alternating pair
        if len(recent) >= 4:
            pairs = list(zip(recent[:-2], recent[2:]))
            if all(a == b for a, b in pairs):
                return True

        # Pattern 2: A-A-A same tool 3+ times in a row
        if len(recent) >= 3 and len(set(recent[-3:])) == 1:
            return True

        # Pattern 3: same tool with similar arguments 3+ times
        # (catches discover_capabilities called with slightly different args)
        last_3 = history[-3:]
        if last_3[0].tool_name == last_3[1].tool_name == last_3[2].tool_name:
            arg_strs = [json.dumps(e.arguments, sort_keys=True, default=str) for e in last_3]
            # 2 or fewer unique arg sets among 3 calls = redundant
            if len(set(arg_strs)) <= 2:
                return True

        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cognitive_summary(result: dict[str, Any]) -> str:
    """Extract a short summary from a cognitive tool result dict."""
    if not result.get("success"):
        return result.get("error", "failed")[:200]
    data = result.get("data", {})
    if isinstance(data, dict):
        # Try common keys from cognitive tool outputs
        for key in ("formatted_message", "message", "summary"):
            if key in data:
                return str(data[key])[:200]
        return str(data)[:200]
    return str(data)[:200]
