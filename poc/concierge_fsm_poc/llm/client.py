"""Gemini LLM Client -- Epic 3.2 (LLM-001).

Adapted from ``poc/react_scratchpad_poc/llm/gemini_client.py``.  Stripped of
benchmark-specific logging/metrics and scenario-specific code.  Adapted for
the Concierge FSM PoC with:

* ``build_system_prompt()`` -- FSM-aware system prompt  rebuilt before
  EVERY LLM call.  Injects current FSM state, SessionState overview, tier-
  filtered tool allowlist, and behavioural instructions.
* ``generate()`` -- function-calling via ``google-genai`` SDK (new API).
* ``extract_findings_batch()`` -- structured fact extraction from tool results.
* ``ToolCall`` / ``LLMResponse`` -- lightweight dataclasses (no Pydantic).

API key loaded from ``poc/chat_experience_poc/.env`` via ``GOOGLE_API_KEY``.

Architecture note
-----------------
``build_system_prompt()`` calls ``read_session_state(manager, section=None)``
for the ~200-token overview and ``registry.get_llm_declarations(tier)`` for
the tier-filtered tool list.  This is the bridge between SessionState and
the LLM -- rebuilt every iteration, never cached across calls.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("concierge_fsm.llm")

# ---------------------------------------------------------------------------
# Load environment -- API key from chat_experience_poc/.env
# ---------------------------------------------------------------------------

_ENV_PATH = Path(__file__).parent.parent.parent / "chat_experience_poc" / ".env"


def _load_env() -> None:
    """Load .env from chat_experience_poc directory."""
    if _ENV_PATH.exists():
        try:
            from dotenv import load_dotenv  # type: ignore[import-untyped]

            load_dotenv(_ENV_PATH, override=False)
        except ImportError:
            # Fall back to manual parsing if python-dotenv not installed
            with open(_ENV_PATH) as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        os.environ.setdefault(k, v)


_load_env()


# ---------------------------------------------------------------------------
# Data models -- plain dataclasses, no Pydantic
# ---------------------------------------------------------------------------


@dataclass
class ToolCall:
    """A single function-call request from the LLM."""

    call_id: str = field(default_factory=lambda: f"call-{uuid.uuid4().hex[:8]}")
    name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """Structured response from a Gemini ``generate_content`` call."""

    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    raw: Any = None

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0

    @property
    def has_text(self) -> bool:
        return self.text is not None and len(self.text.strip()) > 0


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

# ============================================================================
# IMPROVEMENT NOTES (what changed and why):
#
# 1. ADDED FEW-SHOT EXAMPLES: The single highest-impact change. LLMs comply
#    with demonstrated behavior 2-5x better than with stated rules. Each
#    critical behavior now has a concrete example showing the desired output.
#
# 2. REMOVED "NEVER SAY" LISTS: Telling a model "never say 'I can't help'"
#    actually primes it to produce that exact phrase. Replaced with positive
#    framing: "always route to the closest tool" instead of "never refuse."
#
# 3. RESTRUCTURED TOOL ARCHITECTURE SECTION: The two-tier explanation was
#    confusing. Now uses a decision-tree format with a clear IF/THEN rule
#    and a concrete example of the wrong vs. right way.
#
# 4. RESOLVED CONTRADICTIONS: "Never refuse" conflicted with "sourced claims
#    only" and "tool failure honesty." Now unified under a single principle:
#    "Always act, always be honest about what happened."
#
# 5. COLLAPSED 9 RULES -> 5 PRINCIPLES: Overlapping rules (1+2, 3+5, 6+7+8)
#    merged. Fewer rules = higher compliance. Each principle is self-contained.
#
# 6. MOVED DYNAMIC CONTEXT TO TOP: LLMs attend more strongly to the beginning
#    and end of the system prompt. Family profile and session state moved above
#    behavioral rules so the model has grounding context before instructions.
#
# 7. ADDED SAFETY BAND BEHAVIORS: The old prompt mentioned CRISIS/RED bands
#    once in passing. Now there's an explicit behavioral table so the model
#    knows exactly what changes per band.
#
# 8. TIGHTENED TOKEN BUDGET: The old prompt was ~1,200 tokens of static
#    instructions. This version is ~900 tokens static, freeing ~300 tokens
#    for richer session state and tool descriptions.
# ============================================================================

_SYSTEM_PROMPT_TEMPLATE = """\
You are the FamilyOS Concierge -- a proactive family assistant that acts \
on behalf of the family. You are warm, practical, and detail-oriented. \
You operate like a skilled human concierge: you take initiative, make \
reasonable assumptions, and move plans forward without unnecessary back-and-forth.

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

## Tool Architecture

You have two kinds of callable things. The rule is simple:

**Direct tools** -> call as a function call (e.g., `discover_capabilities()`, \
`read_session_state()`, `update_beliefs()`, `recall_memory()`).

**Capabilities** -> call ONLY via `invoke_capability(capability_name=...)`. \
These are services like `tool.execute.weather_lookup`, \
`tool.execute.hotel_booking`, etc.

Decision rule:
- If it's in your tool list above -> call it directly.
- If it's a service/action (weather, booking, search) -> first call \
`discover_capabilities()` to get the exact name, then pass that name \
to `invoke_capability()`.

<example id="tool-routing-wrong">
WRONG: invoke_capability("discover_capabilities")
WRONG: invoke_capability("tool.discover.capabilities")
WRONG: invoke_capability("hotel_search")  <- guessed name
</example>

<example id="tool-routing-right">
RIGHT: discover_capabilities()  -> returns ["tool.execute.hotel_booking", ...]
RIGHT: invoke_capability(capability_name="tool.execute.hotel_booking", ...)
</example>

---

## Core Principles

### 1. Always Act, Always Be Honest
Route every request to the closest available tool. If information is \
missing, infer from session state or make a reasonable assumption and \
state it. If a tool fails, say so and suggest an alternative.

<example id="act-with-assumption">
User: "Find us a hotel in Austin"
You think: No dates specified. Family profile shows 4 members. I'll assume \
this coming weekend and search for family-friendly options.
Action: discover_capabilities() -> invoke_capability("tool.execute.hotel_booking", \
destination="Austin, TX", check_in="2025-02-08", check_out="2025-02-09", guests=4)
Response: "I'm looking at Austin hotels for this weekend for your family of 4. \
(Assuming Sat-Sun -- let me know if you had different dates in mind!)"
</example>

<example id="tool-failure-honesty">
Tool returns: {{"status": "FAILED", "error": "service_unavailable"}}
Response: "The hotel search service is temporarily down. I can try again in \
a moment, or I can look up Austin hotels through a different approach -- \
want me to try?"
</example>

### 2. Think -> Act (skip steps you don't need)
Follow this reasoning flow, but skip steps when you already have the info:

1. **Orient** -- `discover_capabilities()` to know what's available.
2. **Assess** -- `read_session_state()` for current beliefs, scoreboard, \
clarifications.
3. **Recall** -- `recall_memory()` for long-term family knowledge.
4. **Update** -- `update_beliefs()`, `update_scoreboard()`, etc. to persist \
new facts.
5. **Act** -- `invoke_capability()` to execute the service.

<example id="skip-steps">
Turn 1: User asks about Austin hotels.
-> You run Orient + Assess + Act (full flow, first request).

Turn 2: User says "What about San Antonio instead?"
-> You already know capabilities and session state. Skip to Act -- just call \
invoke_capability with the new destination.
</example>

### 3. Use Family Context
Check `beliefs_active` and the family profile for names, ages, allergies, \
and preferences. Apply them without being asked.

<example id="family-context">
Family profile shows: Lily (age 8, allergies: peanuts, tree nuts)
User: "Find a restaurant for dinner tonight"
You: search for family-friendly restaurants, then FILTER results to exclude \
places that can't accommodate nut allergies. Mention this in your response: \
"I filtered for nut-allergy-safe options since Lily has peanut and tree nut \
allergies."
</example>

### 4. Respond with Substance
Include specific details from tool results: names, prices, times, ratings. \
Present all relevant options, not just "I found some results." End with a \
concrete next step.

<example id="good-response">
GOOD: "Here are three family-friendly restaurants near your hotel:
1. Uchi -- Japanese, 4.7 stars, ~$45/person, opens at 5pm. They have a dedicated \
allergen menu.
2. Loro -- Asian smokehouse, 4.5 stars, ~$25/person, outdoor seating.
3. Paperboy -- casual brunch/dinner, 4.3 stars, ~$20/person, very kid-friendly.
Want me to check availability at any of these?"
</example>

<example id="bad-response">
BAD: "I found some restaurant options for you! Let me know if you want details."
BAD: {{"results": [{{"name": "Uchi", "rating": 4.7}}]}}  <- never dump raw data
</example>

### 5. Honor Constraints and Sources
- Apply every constraint the user states (dietary, budget, time). If \
constraints come from an interrupt, they override the original request.
- Only state prices, availability, names, or addresses if a tool returned \
them. If you don't have the data yet, say "Let me look that up" and call \
the tool.

---

## Safety Band Behavior
| Band     | Behavior |
|----------|----------|
| GREEN    | Full access. Act freely with all tools. |
| AMBER    | Proceed with caution. Confirm before irreversible actions (bookings, payments). |
| RED      | Read-only. Use cognitive tools (read_session_state, recall_memory, update_beliefs) only. No external actions. |
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
    """Build the complete system prompt for a Gemini call.

    This MUST be called before EVERY LLM call (never cached across
    iterations) because FSM state and SessionState change between calls.

    Parameters
    ----------
    fsm_state:
        Current FSM state name (e.g. ``"DISPATCHING"``).
    turn_number:
        Current turn number in the conversation.
    tier:
        Complexity tier: ``"LOW"`` or ``"MEDIUM"``.
    safety_band:
        Safety classification: ``"GREEN"``, ``"AMBER"``, ``"RED"``, ``"CRISIS"``.
    session_overview:
        Output of ``read_session_state(manager, section=None)["data"]``.
        If ``None``, shows ``"(not available)"``.
    tool_declarations:
        Output of ``registry.get_llm_declarations(tier)``.
        Used only to list tool names in the prompt.
    family_persona:
        The FAMILY_PERSONA dict with members, allergies, preferences.
        If ``None``, shows ``"(not loaded)"``.

    Returns
    -------
    The fully rendered system prompt string.
    """
    # Format session overview as compact JSON
    if session_overview:
        overview_str = json.dumps(session_overview, indent=2, default=str)
    else:
        overview_str = "(not available)"

    # Format family profile as readable text
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

    # Format tool descriptions (name + description for each tool)
    tools = tool_declarations or []
    if tools:
        tool_desc_lines = []
        for t in sorted(tools, key=lambda x: x.get("name", "")):
            name = t.get("name", "?")
            desc = t.get("description", "(no description)")
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
# Findings extraction (reused from existing PoC)
# ---------------------------------------------------------------------------

# Finding is imported lazily inside methods to avoid circular import:
# llm.client -> react.scratchpad -> react.__init__ -> react.loop -> llm.client


# ---------------------------------------------------------------------------
# Findings extraction prompt (improved)
# ---------------------------------------------------------------------------

_FINDINGS_EXTRACTION_PROMPT = """\
Extract key facts from these {count} tool results as a JSON array.

Each object must have:
- key: snake_case, globally unique, prefixed with entity name (e.g., \
"uchi_restaurant_rating", "hilton_austin_price_per_night")
- value: the fact
- type: one of "weather", "flight", "hotel", "restaurant", "price", \
"location", "schedule", "preference", "error", "fact"
- source_tool: the tool that produced this fact

Rules:
- Keys MUST be descriptive and entity-prefixed. Generic keys like "name" \
or "result" are forbidden.
- Only extract facts useful for decision-making or memory.
- If a tool returned an error, extract it with type "error".

<example>
Input: weather_lookup returned {{"city": "Austin", "temp_f": 72, "condition": "sunny"}}
Output: [
  {{"key": "austin_current_temp_f", "value": 72, "type": "weather", "source_tool": "weather_lookup"}},
  {{"key": "austin_current_condition", "value": "sunny", "type": "weather", "source_tool": "weather_lookup"}}
]
</example>

{results_text}

Respond with ONLY a JSON array, no markdown formatting:
"""


# ---------------------------------------------------------------------------
# Gemini Client
# ---------------------------------------------------------------------------


class GeminiClient:
    """LLM client wrapping Google Gemini for the Concierge FSM PoC.

    Uses the new ``google-genai`` SDK (``from google import genai``).

    Capabilities:

    1. ``generate()``             -- Function-calling LLM call for the ReAct loop.
    2. ``summarize_messages()``   -- Compress old messages for compaction.
    3. ``extract_findings_batch()`` -- Structured fact extraction from tool output.
    4. ``build_system_prompt()``  -- (module-level function, not a method).
    """

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY", "")
        self.model_name = model_name or os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")

        if not self.api_key:
            raise ValueError(
                "GOOGLE_API_KEY not set. "
                "Check poc/chat_experience_poc/.env or set the environment variable."
            )

        from google import genai as genai_sdk  # new SDK
        from google.genai import types as genai_types

        self._client = genai_sdk.Client(api_key=self.api_key)
        self._types = genai_types

        # Cumulative stats
        self.total_calls: int = 0
        self.total_tokens_in: int = 0
        self.total_tokens_out: int = 0

    # ------------------------------------------------------------------
    # 1. Core generation (function calling)
    # ------------------------------------------------------------------

    async def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        force_tool_call: bool = False,
    ) -> LLMResponse:
        """Call Gemini with messages and optional tool declarations.

        Uses the new ``google-genai`` SDK: ``client.models.generate_content()``
        with ``types.GenerateContentConfig`` for tools, system instruction,
        and safety settings.

        Parameters
        ----------
        messages:
            List of message dicts.  Supported roles:
            - ``system`` -- extracted as system instruction
            - ``user`` -- user turn
            - ``assistant`` -- model turn
            - ``function_call`` -- model's tool call (has function_name, function_args)
            - ``tool_response`` -- tool result (has tool_name, tool_result)
            - ``tool`` -- legacy plain-text tool result (fallback)
        tools:
            Gemini-compatible function declaration dicts (from
            ``registry.get_llm_declarations(tier)``).  Passed directly
            to ``types.Tool(function_declarations=...)`` -- the new SDK
            accepts plain dicts.
        force_tool_call:
            If ``True``, forces the model to call at least one tool.

        Returns
        -------
        ``LLMResponse`` with ``text``, ``tool_calls``, and token counts.
        """
        types = self._types

        contents, system_instruction = self._build_contents(messages)

        # Build tool config
        gemini_tools = None
        tool_config_obj = None

        if tools:
            # New SDK accepts plain dicts for function_declarations
            func_decls = [types.FunctionDeclaration(**t) for t in tools]  # type: ignore[arg-type]
            gemini_tools = [types.Tool(function_declarations=func_decls)]
            if force_tool_call:
                tool_config_obj = types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(
                        mode=types.FunctionCallingConfigMode.ANY
                    )
                )

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=gemini_tools,  # type: ignore[arg-type]
            tool_config=tool_config_obj,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        self.total_calls += 1

        try:
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=config,
            )
        except Exception as e:
            logger.error("Gemini call failed: %s", e)
            return LLMResponse(
                text=f"LLM_ERROR: {e!s}",
                tool_calls=[],
                tokens_in=0,
                tokens_out=0,
            )

        # Extract token counts
        tokens_in = 0
        tokens_out = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            tokens_in = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
            tokens_out = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

        self.total_tokens_in += tokens_in
        self.total_tokens_out += tokens_out

        # Parse response parts
        tool_calls: list[ToolCall] = []
        text_parts: list[str] = []

        if response.candidates:
            candidate = response.candidates[0]
            if candidate.content and candidate.content.parts:
                for part in candidate.content.parts:
                    if (
                        hasattr(part, "function_call")
                        and part.function_call
                        and getattr(part.function_call, "name", None)
                    ):
                        fc = part.function_call
                        args = dict(fc.args) if fc.args else {}
                        tool_calls.append(ToolCall(name=fc.name or "", arguments=args))
                    elif hasattr(part, "text") and part.text:
                        text_parts.append(part.text)

        return LLMResponse(
            text="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            raw=response,
        )

    # ------------------------------------------------------------------
    # 1b. Streaming generation (function calling)
    # ------------------------------------------------------------------

    async def generate_stream(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        force_tool_call: bool = False,
        on_text_delta: Any | None = None,
    ) -> LLMResponse:
        """Call Gemini with streaming, emitting text deltas as they arrive.

        Uses ``client.models.generate_content_stream()`` for real-time
        text delivery.  Function-call responses are accumulated across
        chunks -- text deltas are NOT emitted when the response contains
        tool calls (since the text is not a final answer).

        Parameters
        ----------
        messages:
            Same format as ``generate()``.
        tools:
            Same format as ``generate()``.
        force_tool_call:
            Same as ``generate()``.
        on_text_delta:
            ``Callable[[str], None]`` called for each text chunk during
            streaming.  Only called for text-only responses (not when
            the response contains function calls).

        Returns
        -------
        ``LLMResponse`` -- identical structure to ``generate()``.
        """
        types = self._types

        contents, system_instruction = self._build_contents(messages)

        # Build tool config (same as generate())
        gemini_tools = None
        tool_config_obj = None

        if tools:
            func_decls = [types.FunctionDeclaration(**t) for t in tools]
            gemini_tools = [types.Tool(function_declarations=func_decls)]
            if force_tool_call:
                tool_config_obj = types.ToolConfig(
                    function_calling_config=types.FunctionCallingConfig(
                        mode=types.FunctionCallingConfigMode.ANY
                    )
                )

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=gemini_tools,
            tool_config=tool_config_obj,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        self.total_calls += 1

        try:
            # Use sync streaming iterator (wrapped for async context).
            # The google-genai SDK's sync generate_content_stream returns
            # an iterable of GenerateContentResponse chunks.
            stream = self._client.models.generate_content_stream(
                model=self.model_name,
                contents=contents,
                config=config,
            )
        except Exception as e:
            logger.warning("Streaming call setup failed, falling back to non-streaming: %s", e)
            self.total_calls -= 1  # undo: generate() will increment
            return await self.generate(messages, tools, force_tool_call)

        # Accumulate all parts across chunks.  We buffer everything
        # because function_call parts can appear in any chunk and we
        # must NOT emit text deltas if the response contains tool calls.
        all_text_parts: list[str] = []
        all_tool_calls: list[ToolCall] = []
        tokens_in = 0
        tokens_out = 0
        last_response = None
        has_function_calls = False

        try:
            for chunk in stream:
                last_response = chunk

                # Token metadata (available on last chunk typically)
                if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
                    tokens_in = getattr(chunk.usage_metadata, "prompt_token_count", 0) or 0
                    tokens_out = getattr(chunk.usage_metadata, "candidates_token_count", 0) or 0

                if not chunk.candidates:
                    continue

                candidate = chunk.candidates[0]
                if not candidate.content or not candidate.content.parts:
                    continue

                for part in candidate.content.parts:
                    if (
                        hasattr(part, "function_call")
                        and part.function_call
                        and getattr(part.function_call, "name", None)
                    ):
                        has_function_calls = True
                        fc = part.function_call
                        args = dict(fc.args) if fc.args else {}
                        all_tool_calls.append(ToolCall(name=fc.name or "", arguments=args))
                    elif hasattr(part, "text") and part.text:
                        all_text_parts.append(part.text)

        except Exception as e:
            logger.warning("Streaming iteration error, using partial data: %s", e)

        # Emit text deltas retroactively only for text-only responses.
        # For FC responses, the text is thinking/reasoning -- not for display.
        if not has_function_calls and on_text_delta and all_text_parts:
            for text_chunk in all_text_parts:
                on_text_delta(text_chunk)

        self.total_tokens_in += tokens_in
        self.total_tokens_out += tokens_out

        return LLMResponse(
            text="\n".join(all_text_parts) if all_text_parts else None,
            tool_calls=all_tool_calls,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            raw=last_response,
        )

    # ------------------------------------------------------------------
    # 2. Message summarization (for scratchpad compaction)
    # ------------------------------------------------------------------

    async def summarize_messages(self, messages: list[dict[str, str]]) -> str:
        """Summarise conversation messages into a concise digest.

        Used by scratchpad compaction to replace older turns with a brief
        summary, preserving key information while reducing token count.

        Parameters
        ----------
        messages:
            List of ``{"role": ..., "content": ...}`` dicts.

        Returns
        -------
        A 2-3 sentence summary string.
        """
        formatted = []
        for m in messages:
            role_label = m.get("role", "user").upper()
            content = m.get("content", "")[:500]
            formatted.append(f"[{role_label}]: {content}")

        messages_text = "\n".join(formatted)

        prompt = (
            "Summarize the following conversation excerpt in 2-3 sentences. "
            "Focus on: what was asked, what tools were called, what was found. "
            "Be factual and concise. Do not add opinions.\n\n"
            f"CONVERSATION:\n{messages_text}\n\n"
            "SUMMARY:"
        )

        try:
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            if response.candidates and response.candidates[0].content.parts:
                summary = response.candidates[0].content.parts[0].text
                if hasattr(response, "usage_metadata") and response.usage_metadata:
                    self.total_tokens_in += (
                        getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                    )
                    self.total_tokens_out += (
                        getattr(response.usage_metadata, "candidates_token_count", 0) or 0
                    )
                return summary.strip()
        except Exception:
            return f"Previous conversation covered: {messages_text[:200]}..."

        return "Previous conversation context (summarization failed)."

    # ------------------------------------------------------------------
    # 3. Finding extraction
    # ------------------------------------------------------------------

    async def extract_findings(
        self,
        tool_name: str,
        raw_result: Any,
    ) -> list[Any]:
        """Extract structured findings from a single tool result."""
        return await self.extract_findings_batch([(tool_name, raw_result)])

    async def extract_findings_batch(
        self,
        tool_results: list[tuple[str, Any]],
    ) -> list[Any]:
        """Extract structured findings from multiple tool results in ONE LLM call.

        Parameters
        ----------
        tool_results:
            List of ``(tool_name, raw_result)`` tuples.

        Returns
        -------
        Flat list of ``Finding`` objects from all results combined.
        """
        from poc.concierge_fsm_poc.react.scratchpad import (
            Finding,  # lazy: circular import guard
        )

        if not tool_results:
            return []

        result_sections = []
        for i, (tool_name, raw_result) in enumerate(tool_results, 1):
            result_str = (
                json.dumps(raw_result, default=str)
                if not isinstance(raw_result, str)
                else raw_result
            )
            if len(result_str) > 3000:
                result_str = result_str[:3000] + "... [truncated]"
            result_sections.append(f"TOOL_{i}: {tool_name}\nRESULT_{i}: {result_str}")

        all_results_text = "\n\n".join(result_sections)
        tool_names = [tn for tn, _ in tool_results]

        prompt = _FINDINGS_EXTRACTION_PROMPT.format(
            count=len(tool_results),
            results_text=all_results_text,
        )

        try:
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )
            if response.candidates and response.candidates[0].content.parts:
                text = response.candidates[0].content.parts[0].text.strip()
                if hasattr(response, "usage_metadata") and response.usage_metadata:
                    self.total_tokens_in += (
                        getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                    )
                    self.total_tokens_out += (
                        getattr(response.usage_metadata, "candidates_token_count", 0) or 0
                    )

                # Strip markdown fencing
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)

                findings_data = json.loads(text)
                findings: list[Finding] = []
                for fd in findings_data:
                    source = fd.get(
                        "source_tool",
                        tool_names[0] if len(tool_names) == 1 else "unknown",
                    )
                    findings.append(
                        Finding(
                            key=fd.get("key", "unknown"),
                            value=fd.get("value", ""),
                            type=fd.get("type", "fact"),
                            source_tool=source,
                        )
                    )
                return findings
        except Exception:
            pass

        # Fallback: one generic finding per tool result
        fallback: list[Finding] = []
        for tool_name, raw_result in tool_results:
            fallback.append(
                Finding(
                    key=f"{tool_name}_result",
                    value=str(raw_result)[:200],
                    type="fact",
                    source_tool=tool_name,
                )
            )
        return fallback

    # ------------------------------------------------------------------
    # 4. Clarification question generation
    # ------------------------------------------------------------------

    async def generate_clarification_question(
        self,
        user_message: str,
        gaps: list[str],
        intent: str,
        prior_answers: list[tuple[str, str]] | None = None,
    ) -> str:
        """Generate a natural clarifying question for detected information gaps.

        Uses a three-tier fallback chain:
        1. LLM generation (warm, natural phrasing)
        2. Template-based natural language (no LLM needed)
        3. Simple gap listing (last resort)

        Parameters
        ----------
        user_message:
            The original user message that triggered clarification.
        gaps:
            List of missing information field names (e.g. ``["check_in", "guests"]``).
        intent:
            The classified intent string (e.g. ``"hotel_booking"``).
        prior_answers:
            List of ``(round_label, answer)`` tuples from earlier rounds
            so the LLM does not repeat the same question.

        Returns
        -------
        A natural-language clarifying question string.
        """
        # --- Strategy 1: LLM generation (primary) ---
        try:
            result = await self._llm_clarification(user_message, gaps, intent, prior_answers)
            if result and not result.startswith("Could you tell me more about:"):
                return result
        except Exception as exc:
            logger.warning("Clarification LLM strategy failed: %s", exc)

        # --- Strategy 2: Template-based natural language ---
        template_result = self._template_clarification(gaps, intent)
        if template_result:
            return template_result

        # --- Strategy 3: Simple gap listing (last resort) ---
        return f"I need a few more details: {', '.join(g.replace('_', ' ') for g in gaps)}"

    def _template_clarification(self, gaps: list[str], intent: str) -> str:
        """Generate a natural clarification from templates (no LLM needed).

        Maps common intent categories to warm question templates and
        humanizes field names so the result reads naturally.
        """
        # Humanize field names: "check_in" -> "check-in date",
        # "num_guests" -> "number of guests", etc.
        _FIELD_LABELS: dict[str, str] = {
            "check_in": "check-in date",
            "check_out": "check-out date",
            "guests": "number of guests",
            "num_guests": "number of guests",
            "budget": "budget range",
            "destination": "destination",
            "location": "preferred location",
            "dates": "travel dates",
            "start_date": "start date",
            "end_date": "end date",
            "dietary": "dietary restrictions",
            "allergies": "any allergies",
            "cuisine": "cuisine preference",
            "party_size": "party size",
            "age_range": "ages of the kids",
            "activity_type": "type of activity",
            "time_of_day": "preferred time",
            "duration": "how long",
        }

        _INTENT_TEMPLATES: dict[str, str] = {
            "hotel_booking": "To find the perfect stay for your family, could you share {gaps}?",
            "restaurant_booking": "To book a great restaurant, I just need to know {gaps}.",
            "activity_search": "To find fun activities, could you tell me {gaps}?",
            "trip_planning": "To plan your trip, I need a few details: {gaps}.",
            "flight_booking": "To search for flights, could you share {gaps}?",
            "car_rental": "For your rental car, I need {gaps}.",
        }

        human_gaps = [_FIELD_LABELS.get(g, g.replace("_", " ")) for g in gaps]

        if len(human_gaps) == 1:
            gaps_str = human_gaps[0]
        elif len(human_gaps) == 2:
            gaps_str = f"{human_gaps[0]} and {human_gaps[1]}"
        else:
            gaps_str = ", ".join(human_gaps[:-1]) + f", and {human_gaps[-1]}"

        # Try intent-specific template
        intent_lower = intent.lower()
        for key, template in _INTENT_TEMPLATES.items():
            if key in intent_lower:
                return template.format(gaps=gaps_str)

        # Generic warm template
        return f"To help with your request, could you share {gaps_str}?"

    async def _llm_clarification(
        self,
        user_message: str,
        gaps: list[str],
        intent: str,
        prior_answers: list[tuple[str, str]] | None = None,
    ) -> str:
        """Internal: attempt LLM-based clarification generation."""
        gaps_joined = ", ".join(gaps)

        # Build context about what the user already told us
        prior_context = ""
        if prior_answers:
            prior_lines = []
            for label, ans in prior_answers:
                prior_lines.append(f'  - {label}: "{ans}"')
            prior_context = (
                "\n\nIMPORTANT: The user already provided these answers in previous rounds:\n"
                + "\n".join(prior_lines)
                + "\n\nDo NOT ask about information the user already provided above. "
                "Only ask about the REMAINING gaps that are still unresolved. "
                "If the user's prior answers address some gaps, acknowledge that "
                "and ask ONLY about what is still missing."
            )

        prompt = (
            "You are a warm family concierge. "
            f"The user said: '{user_message}'. "
            f"Their intent appears to be '{intent}'. "
            f"The following information is still missing: {gaps_joined}. "
            f"{prior_context}"
            "\nGenerate a single natural, warm clarifying question that asks "
            "for ONLY the missing information. Be concise (1-2 sentences). "
            "Do not list field names. Do not number items."
        )

        try:
            config = self._types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=1024,
            )
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )
            self.total_calls += 1

            if hasattr(response, "usage_metadata") and response.usage_metadata:
                self.total_tokens_in += (
                    getattr(response.usage_metadata, "prompt_token_count", 0) or 0
                )
                self.total_tokens_out += (
                    getattr(response.usage_metadata, "candidates_token_count", 0) or 0
                )

            if response.candidates and response.candidates[0].content.parts:
                # Collect text from all non-thought parts (gemini-2.5
                # models include thinking parts before the answer).
                text_parts: list[str] = []
                for part in response.candidates[0].content.parts:
                    if getattr(part, "thought", False):
                        continue
                    if hasattr(part, "text") and part.text:
                        text_parts.append(part.text)
                if text_parts:
                    return "\n".join(text_parts).strip()

            # No usable text from LLM -- return empty to trigger fallback
            return ""

        except Exception as exc:
            logger.warning("Clarification LLM call failed: %s", exc)
            self.total_calls += 1
            raise  # let the fallback chain in generate_clarification_question handle it

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_contents(
        self,
        messages: list[dict[str, Any]],
    ) -> tuple[list[Any], str | None]:
        """Convert standard message dicts to Gemini ``types.Content`` objects.

        Returns ``(contents, system_instruction)`` -- the new SDK passes
        system_instruction via ``GenerateContentConfig`` (not in contents).

        Supports roles:
        - ``system`` -- extracted into system_instruction string
        - ``user`` -- ``types.Content(role='user', ...)``
        - ``assistant`` -- ``types.Content(role='model', ...)``
        - ``function_call`` -- model turn with ``types.Part`` containing
          function call data (preserved from model response)
        - ``tool_response`` -- user turn with ``Part.from_function_response()``
        - ``tool`` -- legacy plain-text fallback
        """
        types = self._types
        system_instruction: str | None = None
        contents: list[Any] = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                if system_instruction:
                    system_instruction += "\n\n" + content
                else:
                    system_instruction = content
            elif role == "assistant":
                contents.append(
                    types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=content)],
                    )
                )
            elif role == "function_call":
                # Model's function call -- if we have the raw Content from
                # the response, use it directly (preserves thought_signature).
                raw_content = msg.get("_raw_content")
                if raw_content is not None:
                    contents.append(raw_content)
                else:
                    # Fallback: reconstruct from name/args
                    fc_name = msg.get("function_name", "unknown")
                    fc_args = msg.get("function_args", {})
                    contents.append(
                        types.Content(
                            role="model",
                            parts=[types.Part.from_function_call(name=fc_name, args=fc_args)],
                        )
                    )
            elif role == "tool_response":
                # Tool result -- proper function_response
                tool_name = msg.get("tool_name", "unknown")
                tool_result = msg.get("tool_result", {})
                contents.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_function_response(name=tool_name, response=tool_result)
                        ],
                    )
                )
            elif role == "tool":
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=content)],
                    )
                )
            else:
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=content)],
                    )
                )

        if not contents:
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text="Hello")],
                )
            )

        return contents, system_instruction
