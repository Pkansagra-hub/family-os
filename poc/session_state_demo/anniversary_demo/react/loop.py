"""FSM-Aware ReAct Loop for the anniversary demo.

Ported from ``concierge_fsm_poc/react/loop.py``.

Orchestrates LLM reasoning through structured tool-calling iterations
within FSM state rails.  The loop:

1. Builds context from session overview + Scratchpad findings
2. Calls SimpleLLMClient with tier-filtered tool declarations
3. Routes tool results through COGNITIVE_TOOLS filter
4. Manages FSM state transitions (DISPATCHING -> COMPANIONING ->
   PROGRESSING -> DELIVERING)
5. Handles interrupts, budget exhaustion, and compaction

Key adaptations vs the FSM PoC version:

* ``SimpleLLMClient`` replaces ``GeminiClient`` -- returns
  ``Dict[str, Any]`` with ``content`` and ``tool_calls`` keys
  instead of ``LLMResponse`` dataclass.
* ``Phase1Result`` is a local dataclass (same fields).
* ``build_system_prompt()`` is ported locally.
* Tool calls are dicts ``{"name": ..., "args": ...}`` instead of
  ``ToolCall`` dataclass.
* No ``response.raw`` -- message reconstruction uses synthetic content.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from poc.session_state_demo.anniversary_demo.fsm_controller import (
    Event,
    FSMController,
    State,
)
from poc.session_state_demo.anniversary_demo.react.events import (
    LoopEvent,
    LoopEventHandler,
    LoopEventType,
    NullEventHandler,
)
from poc.session_state_demo.anniversary_demo.react.scratchpad import (
    COGNITIVE_TOOLS,
    Finding,
    LoopBudget,
    Scratchpad,
    Tier,
)

logger = logging.getLogger("anniversary_demo.react")


# ---------------------------------------------------------------------------
# Phase1Result -- input to the loop (matches FSM PoC contract)
# ---------------------------------------------------------------------------


@dataclass
class Phase1Result:
    """Output of Phase 1 classification.

    Fields align to DISPATCHING routing requirements (tier, safety_band, gaps)
    and cognitive tool inputs (intent, entities, emotion).
    """

    intent: str = ""
    tier: str = "MEDIUM"
    safety_band: str = "GREEN"
    entities: dict[str, str] = field(default_factory=dict)
    emotion: str = "neutral"
    confidence: float = 1.0
    gaps: list[str] = field(default_factory=list)


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
    """

    pending: bool = False
    source: str = ""
    replacement_message: str = ""


# ---------------------------------------------------------------------------
# System prompt builder (ported from concierge_fsm_poc/llm/client.py)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_TEMPLATE = """\
You are the FamilyOS Concierge -- a proactive family assistant that acts \
on behalf of the family. You are warm, practical, and detail-oriented.

You help with any family need: trips, meals, scheduling, activities, \
logistics, errands, or conversation. Your scope is defined by your tools \
and the user's request.

---

## Context

**FSM State:** {fsm_state} | **Turn:** {turn_number} | **Tier:** {tier} | **Safety:** {safety_band}

### Family Profile
{family_profile}

### Session State
{session_overview}

### Available Tools ({tool_count} for {tier} tier)
{tool_descriptions}

---

## Core Principles

### 1. FUNCTIONAL TOOLS FIRST
Your primary job is to USE FUNCTIONAL TOOLS (search_accommodations, \
get_family_member_info, book_accommodation, etc.) to fulfill the user's \
request. Call the tools that will gather real data or take real actions. \
Do NOT call acknowledge, add_belief, or update_persona unless you have \
already called at least one functional tool in this turn, or you are \
deliberately responding with just text.

### 2. Cognitive Tools Are Secondary
- Call at most ONE acknowledge per response.
- Call at most ONE belief-write (add_belief / update_persona / update_emotion) per response.
- NEVER loop on cognitive tools. If you find yourself calling only \
cognitive tools, STOP and either call a functional tool or write your \
final answer.

### 3. Think -> Act (skip steps you don't need)
1. **Orient** -- check what tools/capabilities are available.
2. **Assess** -- review session state and family profile for context.
3. **Act** -- call the appropriate FUNCTIONAL tool(s).
4. **Record** -- optionally call ONE cognitive tool to store a key fact.
Skip steps when you already have the information.

### 4. Use Family Context
Check beliefs and the family profile for names, ages, allergies, \
and preferences. Apply them without being asked.

### 5. Respond with Substance
Include specific details from tool results: names, prices, times, ratings. \
End with a concrete next step. Do NOT apologize for tool issues.

### 6. Honor Constraints and Sources
Apply every constraint the user states. Only state facts if a tool returned them. \
NEVER invent, hallucinate, or fabricate names, prices, or details that were \
not in the tool results. Present ONLY the options the tools returned. \
If the tool returned 3 hotels, present exactly those 3 hotels by their \
exact names and prices -- do not add extras.

---

## Safety Band Behavior
| Band     | Behavior |
|----------|----------|
| GREEN    | Full access. Act freely with all tools. |
| AMBER    | Proceed with caution. Confirm before irreversible actions. |
| RED      | Read-only. Cognitive tools only. No external actions. |
| CRISIS   | Read-only. Prioritize user safety. Acknowledge and de-escalate. |
"""


def build_system_prompt(
    *,
    fsm_state: str,
    turn_number: int,
    tier: str,
    safety_band: str,
    session_overview: dict[str, Any] | None = None,
    tool_declarations: list[dict[str, Any]] | None = None,
    family_persona: dict[str, Any] | None = None,
) -> str:
    """Build the complete system prompt for a Gemini call."""
    if session_overview:
        overview_str = json.dumps(session_overview, indent=2, default=str)
    else:
        overview_str = "(not available)"

    if family_persona and family_persona.get("members"):
        lines = [f"Family: {family_persona.get('family_name', 'Unknown')}"]
        lines.append(f"Home: {family_persona.get('home_location', 'Unknown')}")
        for m in family_persona["members"]:
            parts = [f"{m['name']} ({m['role']})"]
            if m.get("age"):
                parts.append(f"age {m['age']}")
            if m.get("allergies"):
                parts.append(f"ALLERGIES: {', '.join(m['allergies'])}")
            if m.get("preferences"):
                parts.append(f"likes: {', '.join(m['preferences'])}")
            lines.append("- " + ", ".join(parts))
        family_profile_str = "\n".join(lines)
    else:
        family_profile_str = "(not loaded)"

    tools = tool_declarations or []
    if tools:
        tool_desc_lines = []
        for t in sorted(tools, key=lambda x: x.get("name", "")):
            name = t.get("name", "?")
            desc = t.get("description", "(no description)")
            # Truncate long descriptions for the prompt
            if len(desc) > 120:
                desc = desc[:117] + "..."
            tool_desc_lines.append(f"- **{name}**: {desc}")
        tool_descriptions_str = "\n".join(tool_desc_lines)
    else:
        tool_descriptions_str = "(none)"

    return _SYSTEM_PROMPT_TEMPLATE.format(
        fsm_state=fsm_state,
        turn_number=turn_number,
        tier=tier,
        safety_band=safety_band,
        session_overview=overview_str,
        family_profile=family_profile_str,
        tool_count=len(tools),
        tool_descriptions=tool_descriptions_str,
    )


# ---------------------------------------------------------------------------
# ReActLoop
# ---------------------------------------------------------------------------


class ReActLoop:
    """FSM-aware ReAct loop that drives Phase 2 tool calling.

    Integrates FSMController, ToolRegistry, SimpleLLMClient, and Scratchpad
    into a single coordinated reasoning loop.

    Parameters
    ----------
    fsm:
        FSMController instance (expected to be in DISPATCHING on entry).
    registry:
        Anniversary demo ToolRegistry with all tools registered.
    llm:
        SimpleLLMClient for LLM calls.
    scratchpad:
        Scratchpad for this turn (created fresh by the demo runner).
    event_handler:
        Optional handler for live loop events.
    """

    def __init__(
        self,
        fsm: FSMController,
        registry: Any,  # anniversary demo ToolRegistry
        llm: Any,  # SimpleLLMClient
        scratchpad: Scratchpad,
        event_handler: LoopEventHandler | None = None,
        tool_executor: Any | None = None,  # anniversary demo ToolExecutor
    ) -> None:
        self.fsm = fsm
        self.registry = registry
        self.llm = llm
        self.scratchpad = scratchpad
        self.event_handler: LoopEventHandler = event_handler or NullEventHandler()
        self.tool_executor = tool_executor
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
        """Execute a single tool via ToolExecutor (preferred) or registry handler.

        Returns a dict with ``success`` bool and either ``data`` or ``error``.
        Read-only tools are cached within the same loop run.
        """
        _CACHEABLE_TOOLS = frozenset({"get_family_member_info", "list_active_monitors"})
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

        # Primary path: use ToolExecutor if available
        if self.tool_executor is not None:
            try:
                result = self.tool_executor.execute(tool_name, arguments)
                # Adapt ToolResult dataclass to dict format
                rv: dict[str, Any] = {
                    "success": result.success,
                    "data": result.data if result.success else {},
                }
                if not result.success:
                    rv["error"] = result.message or "Tool execution failed"
                if result.data.get("formatted_message"):
                    rv["data"] = result.data
            except Exception as e:
                logger.warning("ToolExecutor %s failed: %s", tool_name, e)
                rv = {"success": False, "error": str(e)}

            if tool_name in _CACHEABLE_TOOLS and rv.get("success"):
                cache_key = f"{tool_name}:{json.dumps(arguments, sort_keys=True, default=str)}"
                self._tool_cache[cache_key] = rv
            return rv

        # Fallback: use registry handler
        tool_schema = self.registry.get(tool_name)
        if tool_schema is None:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

        handler = tool_schema.handler
        if handler is None:
            return {"success": False, "error": f"No handler for tool: {tool_name}"}

        try:
            result = handler(**arguments)
            rv = {"success": True, "data": result}
        except Exception as e:
            logger.warning("Tool %s failed: %s", tool_name, e)
            rv = {"success": False, "error": str(e)}

        if tool_name in _CACHEABLE_TOOLS and rv.get("success"):
            cache_key = f"{tool_name}:{json.dumps(arguments, sort_keys=True, default=str)}"
            self._tool_cache[cache_key] = rv

        return rv

    # ------------------------------------------------------------------ #
    # Core loop
    # ------------------------------------------------------------------ #

    async def run(
        self,
        phase1: Phase1Result,
        user_message: str,
        *,
        turn_number: int = 1,
        session_overview: dict[str, Any] | None = None,
        family_persona: dict[str, Any] | None = None,
        beliefs_context: str = "",
        conversation_history: list[dict[str, str]] | None = None,
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
            Current turn number in the conversation.
        session_overview:
            SessionState overview dict.
        family_persona:
            Family persona dict with members, allergies, preferences.
        beliefs_context:
            Formatted string of known beliefs/facts from session state.
            Injected into LLM context so it can use stored facts
            (dates, allergies, preferences) for tool arguments.

        Returns
        -------
        ``ReActResult`` with final response, metrics, and FSM trace.
        """
        self._fsm_transitions = []
        self._tool_cache.clear()
        self.scratchpad.user_query = user_message
        self.scratchpad.tier = Tier(phase1.tier)
        self.scratchpad.budget = LoopBudget.for_tier(Tier(phase1.tier))
        self.scratchpad.fsm_state = self.fsm.state

        tier = phase1.tier
        safety_band = phase1.safety_band

        # Tier-filtered tool declarations
        tool_declarations = self.registry.get_llm_declarations(tier)

        # Safety band filtering: remove action tools for RED/CRISIS
        if safety_band in ("RED", "CRISIS"):
            _ACTION_TOOLS = frozenset(
                {
                    "book_accommodation",
                    "book_restaurant",
                    "book_spa_service",
                    "send_family_message",
                    "create_calendar_event",
                    "schedule_reminder",
                    "spawn_agent",
                }
            )
            tool_declarations = [t for t in tool_declarations if t["name"] not in _ACTION_TOOLS]

        # MEDIUM path: fire PRELIMINARY_ACK_SENT -> COMPANIONING (T7)
        if tier == "MEDIUM" and self.fsm.state == State.DISPATCHING:
            self._fire(Event.PRELIMINARY_ACK_SENT)

        # Conversation messages accumulated during the loop.
        # Seed with actual conversation history so the model has
        # real user/assistant turns -- not just flat text in system.
        messages: list[dict[str, Any]] = []
        if conversation_history:
            for hist_turn in conversation_history[-5:]:
                u = hist_turn.get("user", "")
                a = hist_turn.get("assistant", "")
                if u:
                    messages.append({"role": "user", "content": u})
                if a:
                    messages.append({"role": "assistant", "content": a})
        _force_text_only = False

        # Cross-iteration cognitive caps (persist across the entire turn)
        _turn_ack_done = False  # Once ack delivered, block ALL further acks
        _turn_belief_count = 0  # Cap belief-writes across the turn
        _MAX_BELIEFS_PER_TURN = 2

        # ---- Main iteration loop ----------------------------------------
        while not self.scratchpad.is_complete:
            # -- Check interrupt at top of each iteration ------------------
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

            # Inject beliefs context so LLM knows stored facts (dates,
            # allergies, preferences) and can use them for tool arguments.
            if beliefs_context:
                iter_messages.append(
                    {
                        "role": "system",
                        "content": (
                            "## Known Facts From Session State\n"
                            "Use these facts for tool call arguments. "
                            "Do NOT ask the user to repeat information "
                            "already captured here.\n"
                            f"{beliefs_context}"
                        ),
                    }
                )

            # Inject findings context
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
            # After acknowledge has been delivered, remove it from tool
            # declarations so the LLM cannot even attempt to call it again.
            if _turn_ack_done and not _force_text_only:
                iter_tools = [t for t in tool_declarations if t.get("name") != "acknowledge"]
            else:
                iter_tools = [] if _force_text_only else tool_declarations
            self._emit(
                LoopEventType.LLM_CALL_START,
                message_count=len(iter_messages),
                tool_count=len(iter_tools) if iter_tools else 0,
            )
            response = await self.llm.generate_stream(
                system_prompt=system_prompt,
                messages=iter_messages,
                tools=iter_tools,
                on_text_delta=lambda t: self._emit(LoopEventType.TEXT_DELTA, text=t),
            )
            _force_text_only = False

            has_tool_calls = bool(response.get("tool_calls"))
            response_text = (response.get("content") or "").strip()
            tool_calls = response.get("tool_calls", [])

            self._emit(
                LoopEventType.LLM_CALL_END,
                has_tool_calls=has_tool_calls,
                tokens_in=0,
                tokens_out=0,
            )

            # -- Thought capture ------------------------------------------
            if response_text and has_tool_calls:
                self.scratchpad.record_thought(response_text, self.scratchpad.iteration)
                self._emit(
                    LoopEventType.THOUGHT,
                    text=response_text[:300],
                    iteration=self.scratchpad.iteration,
                )

            # -- If LLM returns text only: done ----------------------------
            if not has_tool_calls:
                if not response_text and self.scratchpad.iteration < 3:
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
                    logger.warning(
                        "Empty LLM response at iteration %d, falling through to "
                        "budget-exhausted path",
                        self.scratchpad.iteration,
                    )
                    break

                # Strip <tool_code> blocks that Gemini sometimes emits
                # when forced text-only (no tool declarations provided).
                response_text = re.sub(
                    r"<tool_code>.*?</tool_code>",
                    "",
                    response_text,
                    flags=re.DOTALL,
                ).strip()

                # Strip markdown code blocks containing tool_code or
                # function-call-like content that Gemini emits when
                # tools are unavailable.
                response_text = re.sub(
                    r"```[a-z]*\s*\n?\{[^}]*tool_code[^}]*\}\s*\n?```",
                    "",
                    response_text,
                    flags=re.DOTALL,
                ).strip()
                # Also strip standalone ```json blocks that look like
                # function calls (contain print(...) or function_name(...)).
                response_text = re.sub(
                    r"```[a-z]*\s*\n?.*?(?:print|search_|book_|plan_|get_|send_|create_|schedule_|start_|stop_|list_|generate_|spawn_)\w*\(.*?\).*?\n?```",
                    "",
                    response_text,
                    flags=re.DOTALL,
                ).strip()

                # Strip <ctrl42>call:... Gemini internal control tokens
                # that leak into text when the model tries to call tools
                # but tool declarations are not available.
                response_text = re.sub(
                    r"<ctrl42>[^\n]*",
                    "",
                    response_text,
                ).strip()

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

            # Append model response as assistant message (simplified --
            # no raw content available from SimpleLLMClient)
            if response_text:
                messages.append({"role": "assistant", "content": response_text})

            # --- Cognitive cap per-iteration + cross-iteration ack guard ---
            _iter_ack_used = False
            _iter_belief_used = False
            _iter_executed = 0  # Count tool calls actually executed
            _iter_blocked = 0  # Count tool calls blocked by caps
            _ack_next_tool: str | None = None  # Track acknowledge's planned next tool
            _BELIEF_WRITE_TOOLS = frozenset({"add_belief", "update_persona", "update_emotion"})

            for tc in tool_calls:
                tc_name = tc["name"]
                tc_args = tc.get("args", {})

                # Enforce cognitive cap (cross-iteration + per-iteration)
                if tc_name in COGNITIVE_TOOLS:
                    # CROSS-ITERATION: once ack delivered, block all further
                    if tc_name == "acknowledge" and _turn_ack_done:
                        logger.debug(
                            "Blocking acknowledge in iteration %d " "(already delivered this turn)",
                            self.scratchpad.iteration,
                        )
                        _iter_blocked += 1
                        continue
                    # PER-ITERATION: max 1 ack per iteration
                    if tc_name == "acknowledge" and _iter_ack_used:
                        logger.debug(
                            "Skipping duplicate acknowledge in iteration %d",
                            self.scratchpad.iteration,
                        )
                        _iter_blocked += 1
                        continue
                    # CROSS-ITERATION: cap belief-writes across the turn
                    if (
                        tc_name in _BELIEF_WRITE_TOOLS
                        and _turn_belief_count >= _MAX_BELIEFS_PER_TURN
                    ):
                        logger.debug(
                            "Blocking %s in iteration %d " "(turn belief cap %d reached)",
                            tc_name,
                            self.scratchpad.iteration,
                            _MAX_BELIEFS_PER_TURN,
                        )
                        _iter_blocked += 1
                        continue
                    # PER-ITERATION: max 1 belief-write per iteration
                    if tc_name in _BELIEF_WRITE_TOOLS and _iter_belief_used:
                        logger.debug(
                            "Skipping duplicate belief-write %s in iteration %d",
                            tc_name,
                            self.scratchpad.iteration,
                        )
                        _iter_blocked += 1
                        continue

                _iter_executed += 1
                self._emit(
                    LoopEventType.TOOL_CALL_START,
                    tool_name=tc_name,
                    arguments=tc_args,
                )
                result = self._execute_tool(tc_name, tc_args)

                if tc_name in COGNITIVE_TOOLS:
                    # Track cognitive cap usage (per-iteration + cross-iteration)
                    if tc_name == "acknowledge":
                        _iter_ack_used = True
                        _turn_ack_done = True
                        _ack_next_tool = tc_args.get("next_tool", "none")
                    if tc_name in _BELIEF_WRITE_TOOLS:
                        _iter_belief_used = True
                        _turn_belief_count += 1

                    summary = _cognitive_summary(result)
                    self.scratchpad.record_tool_call(
                        tc_name,
                        tc_args,
                        ok=result.get("success", False),
                        summary=f"[cognitive] {summary}",
                    )
                    self._emit(
                        LoopEventType.TOOL_CALL_END,
                        tool_name=tc_name,
                        success=result.get("success", False),
                        summary=summary[:120],
                    )
                    # Use "system" role so LLM does not echo cognitive
                    # tool results verbatim in its response to the user.
                    if tc_name == "acknowledge":
                        # Strong signal: ack is done, do not repeat
                        messages.append(
                            {
                                "role": "system",
                                "content": (
                                    "ACKNOWLEDGMENT COMPLETED - Message delivered to user. "
                                    "Do NOT call acknowledge again this turn. "
                                    "Now either call a FUNCTIONAL tool (search, book, plan) "
                                    "or respond directly with text."
                                ),
                            }
                        )
                    else:
                        messages.append(
                            {
                                "role": "system",
                                "content": f"[Internal] {tc_name} completed: {summary[:120]}",
                            }
                        )
                else:
                    if result.get("success"):
                        non_cognitive_results.append((tc_name, result["data"]))
                    else:
                        error_msg = str(result.get("error", "unknown error"))
                        self.scratchpad.add_findings(
                            [
                                Finding(
                                    key=f"{tc_name}_FAILED",
                                    value=f"TOOL FAILED: {error_msg}",
                                    type="error",
                                    source_tool=tc_name,
                                )
                            ]
                        )
                    self.scratchpad.record_tool_call(
                        tc_name,
                        tc_args,
                        ok=result.get("success", False),
                        summary=str(result.get("data", result.get("error", "")))[:200],
                    )
                    self._emit(
                        LoopEventType.TOOL_CALL_END,
                        tool_name=tc_name,
                        success=result.get("success", False),
                        summary=str(result.get("data", result.get("error", "")))[:120],
                    )
                    # Append tool result for context.
                    # Use role="user" so the model treats this as input
                    # (not something it said that it should continue).
                    # Summarise instead of raw JSON to prevent the model
                    # from echoing or completing truncated JSON fragments.
                    result_data = (
                        result.get("data", {})
                        if result.get("success")
                        else {
                            "error": str(result.get("error", "unknown")),
                            "status": "FAILED",
                        }
                    )
                    if isinstance(result_data, dict):
                        summary_parts: list[str] = []
                        for k, v in result_data.items():
                            # For lists of dicts (search results), format
                            # each item individually so nothing is truncated.
                            if isinstance(v, list) and v and isinstance(v[0], dict):
                                items_text: list[str] = []
                                for idx, item in enumerate(v[:6], 1):
                                    fields = ", ".join(
                                        f"{ik}: {iv}"
                                        for ik, iv in item.items()
                                        if ik not in ("available",)
                                    )
                                    items_text.append(f"    {idx}. {fields}")
                                summary_parts.append(f"  {k}:\n" + "\n".join(items_text))
                            else:
                                v_str = str(v)
                                if len(v_str) > 500:
                                    v_str = v_str[:497] + "..."
                                summary_parts.append(f"  {k}: {v_str}")
                        result_text = "\n".join(summary_parts)
                    else:
                        result_text = str(result_data)[:800]
                    messages.append(
                        {
                            "role": "user",
                            "content": (f"[System: Tool '{tc_name}' completed]\n" f"{result_text}"),
                        }
                    )

            # -- Anti-spin: force text if no functional work was done ----
            # Case 1: ALL tool calls blocked by caps
            _all_blocked = tool_calls and _iter_executed == 0 and _iter_blocked > 0
            # Case 2: Only cognitive tools executed (ack done, no functional)
            _cognitive_only = _iter_executed > 0 and _turn_ack_done and not non_cognitive_results

            # EXCEPTION: If acknowledge signaled a functional next_tool,
            # the LLM intends to call it in the next iteration. Do NOT
            # force text-only -- let the functional tool fire.
            if _cognitive_only and _ack_next_tool and _ack_next_tool != "none":
                logger.info(
                    "Cognitive-only iteration %d but acknowledge signaled "
                    "next_tool='%s' -- allowing functional tool next iteration",
                    self.scratchpad.iteration,
                    _ack_next_tool,
                )
                _cognitive_only = False

            if _all_blocked or _cognitive_only:
                logger.info(
                    "Cognitive-only iteration %d (executed=%d, blocked=%d, "
                    "functional=%d) -- forcing text-only next iteration",
                    self.scratchpad.iteration,
                    _iter_executed,
                    _iter_blocked,
                    len(non_cognitive_results),
                )
                _force_text_only = True
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "All cognitive tools for this turn are done. "
                            "Do NOT call any more tools. "
                            "Respond directly with text now. "
                            "Summarize what you know and suggest a concrete next step."
                        ),
                    }
                )

            # -- Extract findings from non-cognitive tool results ----------
            if non_cognitive_results:
                findings: list[Finding] = []
                for tool_name, raw_data in non_cognitive_results:
                    if isinstance(raw_data, dict):
                        for k, v in raw_data.items():
                            # For lists of dicts (search results), create
                            # a finding per item so each is individually
                            # visible without truncation.
                            if isinstance(v, list) and v and isinstance(v[0], dict):
                                for idx, item in enumerate(v[:6]):
                                    item_str = ", ".join(
                                        f"{ik}: {iv}"
                                        for ik, iv in item.items()
                                        if ik not in ("available",)
                                    )
                                    if len(item_str) > 500:
                                        item_str = item_str[:497] + "..."
                                    findings.append(
                                        Finding(
                                            key=f"{tool_name}_{k}_{idx}",
                                            value=item_str,
                                            type="fact",
                                            source_tool=tool_name,
                                        )
                                    )
                            else:
                                v_str = str(v)
                                if len(v_str) > 500:
                                    v_str = v_str[:497] + "..."
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
                                value=str(raw_data)[:500],
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
                logger.warning("Cycle detected: %s -- breaking loop", recent_names)

                # Compact scratchpad if there are findings
                if self.scratchpad.findings:
                    compact_text = self.scratchpad.findings_summary()
                    self.scratchpad.add_compaction_summary(compact_text)
                    self._emit(LoopEventType.COMPACTION, summary_len=len(compact_text))

                # Force one final text-only LLM call with a strong directive
                system_prompt = build_system_prompt(
                    fsm_state=self.fsm.state.value,
                    turn_number=turn_number,
                    tier=tier,
                    safety_band=safety_band,
                    session_overview=session_overview,
                    tool_declarations=tool_declarations,
                    family_persona=family_persona,
                )
                cycle_messages: list[dict[str, Any]] = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ]
                findings_text = self.scratchpad.findings_summary()
                if findings_text:
                    cycle_messages.append(
                        {
                            "role": "system",
                            "content": f"## Known Facts From Previous Tool Calls\n{findings_text}",
                        }
                    )
                cycle_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Now respond directly to the user's message. "
                            "Use what you know from the session and tools. "
                            "Be helpful, specific, and suggest a next step."
                        ),
                    }
                )
                recovery_response = await self.llm.generate_stream(
                    system_prompt=system_prompt,
                    messages=cycle_messages,
                    tools=[],  # No tools -- force text
                    on_text_delta=lambda t: self._emit(LoopEventType.TEXT_DELTA, text=t),
                )
                recovery_text = (recovery_response.get("content") or "").strip()
                if recovery_text:
                    # Fire FSM to DELIVERING
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
                        final_response=recovery_text,
                        tool_calls_made=self.scratchpad.budget.tools_used,
                        iterations=self.scratchpad.iteration,
                        findings_count=len(self.scratchpad.findings),
                        fsm_transitions=list(self._fsm_transitions),
                        budget_exhausted=False,
                    )
                # If recovery also empty, fall through to budget-exhausted path
                break

        # ---- Budget exhausted: generate best-effort response -------------
        if self.fsm.state in (
            State.DISPATCHING,
            State.COMPANIONING,
            State.PROGRESSING,
        ):
            self._fire(Event.DISPATCH_COMPLETE)

        # Attempt a final text-only LLM call for a substantive response
        try:
            system_prompt = build_system_prompt(
                fsm_state=self.fsm.state.value,
                turn_number=turn_number,
                tier=tier,
                safety_band=safety_band,
                session_overview=session_overview,
                tool_declarations=tool_declarations,
                family_persona=family_persona,
            )
            recovery_messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]
            findings_text = self.scratchpad.findings_summary()
            if findings_text:
                recovery_messages.append(
                    {
                        "role": "system",
                        "content": f"## Known Facts From Previous Tool Calls\n{findings_text}",
                    }
                )
            recovery_messages.append(
                {
                    "role": "user",
                    "content": (
                        "Respond helpfully to the user's message using what you "
                        "know from the conversation and session state. "
                        "Do NOT call any tools."
                    ),
                }
            )
            recovery_response = await self.llm.generate_stream(
                system_prompt=system_prompt,
                messages=recovery_messages,
                tools=[],
                on_text_delta=lambda t: self._emit(LoopEventType.TEXT_DELTA, text=t),
            )
            recovery_text = (recovery_response.get("content") or "").strip()
            if recovery_text:
                final_text = recovery_text
            elif self.scratchpad.findings:
                bullets: list[str] = []
                for f in self.scratchpad.findings.values():
                    if f.type == "error":
                        bullets.append(f"I encountered an issue: {f.value}")
                    else:
                        bullets.append(f"{f.key.replace('_', ' ').title()}: {f.value}")
                body = (
                    "; ".join(bullets)
                    if len(bullets) <= 3
                    else "\n".join(f"- {b}" for b in bullets)
                )
                final_text = f"Here is what I found so far: {body}"
            else:
                final_text = (
                    "I wasn't able to complete my search in time. "
                    "Could you tell me a bit more about what you need?"
                )
        except Exception:
            final_text = (
                "I wasn't able to complete my search in time. "
                "Could you tell me a bit more about what you need?"
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
    # Interrupt handling
    # ------------------------------------------------------------------ #

    def _handle_interrupt(self) -> ReActResult:
        """Handle an interrupt detected at the top of a loop iteration."""
        source = self.interrupt.source

        self._fire(Event.INTERRUPT_DETECTED)

        partial_response = ""
        if self.scratchpad.findings:
            partial_response = f"Partial results: {self.scratchpad.findings_summary()}"

        self._fire(Event.INTERRUPT_HANDLED)

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
    # External interrupt API
    # ------------------------------------------------------------------ #

    def signal_interrupt(
        self,
        source: str = "user",
        replacement_message: str = "",
    ) -> None:
        """Signal an interrupt to the loop."""
        self.interrupt.pending = True
        self.interrupt.source = source
        self.interrupt.replacement_message = replacement_message

    # ------------------------------------------------------------------ #
    # Cycle detection
    # ------------------------------------------------------------------ #

    def _detect_cycle(self) -> bool:
        """Detect repeating tool-call patterns that indicate a stuck loop.

        Only considers non-cognitive (functional) tools.  Cognitive tools
        (acknowledge, add_belief, update_persona, update_emotion) are
        capped at 1+1 per iteration and their repetition across iterations
        is expected, not a cycle.
        """
        # Filter to functional tools only
        functional_history = [
            e for e in self.scratchpad.tool_history if e.tool_name not in COGNITIVE_TOOLS
        ]
        if len(functional_history) < 3:
            return False

        recent = [e.tool_name for e in functional_history[-6:]]

        # Pattern 1: A-B-A-B alternating pair
        if len(recent) >= 4:
            pairs = list(zip(recent[:-2], recent[2:]))
            if all(a == b for a, b in pairs):
                return True

        # Pattern 2: A-A-A same tool 3+ times in a row
        if len(recent) >= 3 and len(set(recent[-3:])) == 1:
            return True

        # Pattern 3: same tool with similar arguments 3+ times
        last_3 = functional_history[-3:]
        if last_3[0].tool_name == last_3[1].tool_name == last_3[2].tool_name:
            arg_strs = [json.dumps(e.arguments, sort_keys=True, default=str) for e in last_3]
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
        for key in ("formatted_message", "message", "summary"):
            if key in data:
                return str(data[key])[:200]
        return str(data)[:200]
    return str(data)[:200]
