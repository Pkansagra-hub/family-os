"""
k1.planner.stages.sketch_service -- SketchService (Epic 3.1).

Stage 1 of the planner pipeline: transforms raw user intent into a
SketchResult (rough plan with capability references).

Design
------
- Layer 2 (Section 30.6): imports Layer 1 ports (ILLMPort), Layer 0
  types (PlanRequest, SketchResult, RoughStep, StageContext, PlannerLLMRequest,
  PlannerLLMResponse, PlannerConstraints, SketchFailedError), and shared types
  from Orchestrator (PlanRequest, MicroReplanRequest).
- Stateless between calls: no per-plan instance state. All per-plan
  state flows through StageContext and method parameters.
- SketchService does NOT hold a reference to PipelineController. Token
  recording is done by PipelineController after receiving SketchResult.
- PLAN-01: zero writes to SessionState.
- PLAN-06: zero capability executions.

AGENTIC TOOL-USE DESIGN:
- The LLM receives tool definitions and decides what context to gather.
- 4 tools: discover_capabilities, query_session_context,
  recall_long_term_memory, find_prompts.
- The LLM calls tools as needed, then produces the final plan JSON.
- This naturally generalises to any planning scenario without domain-
  specific prompt engineering.

ToolCallRouter and HILCoordinator are defined as local Protocol stubs
below until Milestone 4 delivers their concrete implementations. This
follows the established codebase pattern (see OrchestratorService's
DAGExecutorLike, ConstraintResolverLike sentinel protocols).

Public interface
----------------
async execute(request, ctx) -> SketchResult
    Full SKETCH pipeline: agentic loop (LLM + tools) -> parse ->
    optional HIL -> result.
async micro_execute(request, ctx) -> SketchResult
    Abbreviated micro-SKETCH for micro-replan: no HIL, reduced budget,
    uses MicroReplanRequest context.

Consumers
---------
PipelineController._run_sketch() -- calls execute() / micro_execute()

References
----------
- planner.md Section 6 (Stage 1 SKETCH Deep Dive)
- planner.md Section 11 (Discovery Tools)
- planner.md Section 12 (HIL Clarification)

Exports
-------
SketchService, ToolCallRouterLike,
SKETCH_OUTPUT_SCHEMA, SKETCH_TOOL_DEFINITIONS
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable

from k1.hil.types import ClarificationRequest
from k1.kernel.ports.hil_port import IHILPort
from k1.orchestrator.types import MicroReplanRequest, PlanRequest
from k1.planner.ports.llm_port import ILLMPort
from k1.planner.types import (
    PlannerConstraints,
    PlannerLLMRequest,
    PlannerLLMResponse,
    RoughStep,
    SketchFailedError,
    SketchResult,
    StageContext,
)

log = logging.getLogger(__name__)

# Maximum number of agentic tool-calling rounds before forcing final answer.
_MAX_TOOL_ROUNDS = 6


# ---------------------------------------------------------------------------
# Output schema -- the JSON Schema the LLM must conform to (Section 6.3.1).
# Defined as a module-level constant so tests can introspect it and so
# the schema is never accidentally mutated at runtime.
# ---------------------------------------------------------------------------

SKETCH_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["rough_steps", "rationale", "needs_clarification"],
    "properties": {
        "rough_steps": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["intent"],
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": (
                            "A clear, actionable description of what this "
                            "step accomplishes. Must be self-contained."
                        ),
                    },
                    "suggested_capability": {
                        "type": "string",
                        "description": (
                            "The exact name of a capability from the "
                            "catalog that best fulfills this step. "
                            "Omit if no catalog entry is a good match."
                        ),
                    },
                    "depends_on": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Intent strings of preceding steps that "
                            "must complete before this step can begin. "
                            "Each entry must exactly match the intent of "
                            "another step in this list."
                        ),
                    },
                },
            },
            "minItems": 1,
        },
        "rationale": {
            "type": "string",
            "description": (
                "Explain the reasoning behind this plan structure: "
                "why these steps, why this ordering, and how they "
                "collectively satisfy the user's intent."
            ),
        },
        "needs_clarification": {
            "type": "boolean",
            "description": (
                "Set to true ONLY if the intent is too ambiguous to "
                "produce a meaningful plan without additional "
                "information from the user."
            ),
        },
        "clarification_question": {
            "type": "string",
            "description": (
                "A single, specific question to ask the user. "
                "Required when needs_clarification is true. "
                "Must be conversational and context-aware."
            ),
        },
    },
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Tool definitions for agentic tool-use (Issue 3.1.2).
# The LLM receives these as callable tools and decides which to invoke
# based on the planning task at hand.  This replaces the old pre-fetch +
# slot-based prompt approach: the LLM gathers its own context.
#
# Each definition follows the OpenAI function-calling schema format
# (type + function{name, description, parameters}).  This is the de facto
# standard consumed by ModelHub / LLM adapters.
# ---------------------------------------------------------------------------

SKETCH_TOOL_DEFINITIONS: Tuple[Dict[str, Any], ...] = (
    {
        "type": "function",
        "function": {
            "name": "discover_capabilities",
            "description": (
                "Search the system's capability registry for capabilities "
                "that can accomplish a task. Returns scored matches with "
                "names, descriptions, required inputs, and domain tags. "
                "Call this to find out what the system can actually do "
                "before assigning capabilities to plan steps."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": (
                            "Natural language description of the task or "
                            "sub-task you need a capability for."
                        ),
                    },
                    "domain": {
                        "type": "string",
                        "description": (
                            "Optional domain filter to narrow results "
                            "(e.g. 'calendar', 'messaging', 'finance', "
                            "'health', 'shopping')."
                        ),
                    },
                    "top_k": {
                        "type": "integer",
                        "description": ("Maximum number of results to return. " "Default: 10."),
                    },
                },
                "required": ["intent"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_session_context",
            "description": (
                "Read the current session state to understand the user's "
                "real-world situation. Returns structured data about "
                "active entities, relationships, persona, time context, "
                "safety settings, and recent interaction history. Use "
                "this to ground your plan in what is actually happening."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sections": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Which sections to read. Available: "
                            "'beliefs_active' (known entities, relationships, "
                            "facts about the world), "
                            "'persona' (user identity and preferences), "
                            "'temporal' (current time, timezone, schedules), "
                            "'control' (safety band, active restrictions), "
                            "'history_recent' (recent conversation turns)."
                        ),
                    },
                },
                "required": ["sections"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_long_term_memory",
            "description": (
                "Search long-term memory for facts, user preferences, "
                "and outcomes of past plans relevant to this task. "
                "Returns historical context that personalises the plan. "
                "This tool may be unavailable if the memory system is "
                "offline -- if it returns an error or empty results, "
                "proceed without it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Natural language query describing what "
                            "memories would help with this planning task."
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_prompts",
            "description": (
                "Search for prompt templates that can guide agent "
                "behaviour for a specific task. Returns scored matches "
                "with template names, descriptions, required variables, "
                "and domain tags. Call this when a plan step needs a "
                "dynamically created agent (meta-agent pattern) so you "
                "can assign the right prompt template to it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": (
                            "Natural language description of the agent's "
                            "task or behaviour you need a prompt for."
                        ),
                    },
                    "domain": {
                        "type": "string",
                        "description": (
                            "Optional domain filter to narrow results "
                            "(e.g. 'messaging', 'health', 'finance')."
                        ),
                    },
                    "top_k": {
                        "type": "integer",
                        "description": ("Maximum number of results to return. " "Default: 5."),
                    },
                },
                "required": ["intent"],
            },
        },
    },
)


# ---------------------------------------------------------------------------
# Sentinel / placeholder protocols for collaborators not yet implemented.
# These will be replaced with real imports when Milestone 4 is delivered
# (Epic 4.1 ToolCallRouter, Epic 4.2 HILCoordinator).
# Using Protocol stubs keeps SketchService testable in isolation.
# ---------------------------------------------------------------------------


@runtime_checkable
class ToolCallRouterLike(Protocol):
    """Placeholder protocol for ToolCallRouter (4.1.x).

    Defines the subset of the ToolCallRouter interface that
    SketchService actually calls.  The concrete ToolCallRouter
    (k1.planner.services.tool_call_router) will satisfy this
    structurally when it is implemented.

    Section 11.5: deterministic router mapping 5 abstract tool names
    to 4 backend ports. Monotonic call counter per plan.
    """

    @property
    def tool_call_count(self) -> int:
        """Current monotonic tool-call counter value (PLAN-05)."""
        ...  # pragma: no cover

    def reset(self) -> None:
        """Reset tool_call_count to 0 (LC_PLAN_START / micro-replan)."""
        ...  # pragma: no cover

    async def discover(
        self,
        intent: str,
        *,
        domain: Optional[str] = None,
        safety_band: str = "GREEN",
        top_k: int = 10,
    ) -> Any:
        """Discover capabilities via IFabricRetrievalPort (Section 11.1).

        Returns RetrievalResult (or compatible). Timeout 50ms, 1 retry.
        """
        ...  # pragma: no cover

    async def read_context(
        self,
        session_id: str,
        sections: list[str],
    ) -> Dict[str, Any]:
        """Query planning context via IStateReadPort (Section 11.3).

        Returns section data dict. Timeout 10ms, 0 retries.
        """
        ...  # pragma: no cover

    async def recall_memory(
        self,
        query: str,
        trace_id: str,
    ) -> Any:
        """Recall for planning via IBridgePort (Section 11.4).

        Returns BridgeCommandResult (or compatible). Timeout 100ms,
        0 retries. Graceful K0 offline degradation.
        """
        ...  # pragma: no cover

    async def find_prompts(
        self,
        intent: str,
        *,
        domain: Optional[str] = None,
        top_k: int = 5,
    ) -> Any:
        """Find prompt templates via IFabricRetrievalPort (Section 11.2).

        Backed by Fabric FindPromptsHandler -> RetrievalLike.
        Returns RetrievalResult (or compatible). Timeout 50ms, 1 retry.
        """
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# SketchService
# ---------------------------------------------------------------------------


class SketchService:
    """Stage 1 SKETCH: intent -> SketchResult (Section 6).

    Transforms a raw user intent (PlanRequest) into a SketchResult
    containing rough steps with capability references, discovered
    capability candidates, and the LLM's planning rationale.

    The full execute() pipeline is:
      1. 3 concurrent discovery tool calls via ToolCallRouter (Section 6.2)
      2. Slot-based LLM prompt composition (Section 6.3.1)
      3. LLM call via ILLMPort (Section 6.3.2)
      4. Response parsing and SketchResult assembly (Section 6.5)
      5. Optional HIL clarification (Section 6.4)
      6. Error recovery with simplified retry (Section 6.6)

    The abbreviated micro_execute() pipeline is:
      Steps 1-4 with reduced budget, no HIL, and MicroReplanRequest
      context (remaining_steps, completed_results, discoveries).

    Stateless between calls: no mutable instance state. All per-plan
    state flows through method parameters and StageContext.

    Invariants
    ----------
    PLAN-01 : Zero writes to SessionState.
    PLAN-02 : Slot-based prompt, output_schema = SketchPlanSchema.
    PLAN-06 : Zero capability executions.
    PLAN-11 : Budget from StageContext.

    Thread safety
    -------------
    Safe for sequential calls from PipelineController. Not designed
    for concurrent execute() calls on the same instance (pipeline is
    sequential: SKETCH -> EXPAND -> VALIDATE -> COMMIT).
    """

    __slots__ = (
        "_llm_port",
        "_tool_router",
        "_hil_port",
    )

    def __init__(
        self,
        llm_port: ILLMPort,
        tool_router: ToolCallRouterLike,
        hil_port: IHILPort,
    ) -> None:
        """Construct SketchService with injected dependencies.

        All dependencies are constructor-injected (hexagonal pattern).
        SketchService never constructs its own collaborators.

        Args:
            llm_port: LLM gateway for structured/chat completions.
                Single exit point for all LLM calls (Section 5.2).
            tool_router: Deterministic tool call dispatcher (Section 11).
                Routes discovery tool names to backend ports. Manages
                monotonic call counter (PLAN-05).
            hil_port: Unified Human-in-the-Loop port (k1.hil) used for
                clarification during SKETCH. Round budget is enforced
                per ``caller_key`` inside HumanInTheLoopService.

        Raises:
            TypeError: If any dependency is None.
        """
        if llm_port is None:
            raise TypeError("llm_port must not be None")
        if tool_router is None:
            raise TypeError("tool_router must not be None")
        if hil_port is None:
            raise TypeError("hil_port must not be None")

        self._llm_port = llm_port
        self._tool_router = tool_router
        self._hil_port = hil_port

    # ------------------------------------------------------------------
    # Read-only property accessors
    # ------------------------------------------------------------------

    @property
    def llm_port(self) -> ILLMPort:
        """LLM gateway port (read-only)."""
        return self._llm_port

    @property
    def tool_router(self) -> ToolCallRouterLike:
        """Tool call router (read-only)."""
        return self._tool_router

    @property
    def hil_port(self) -> IHILPort:
        """Unified HIL port (read-only)."""
        return self._hil_port

    # ------------------------------------------------------------------
    # Prompt construction -- Agentic tool-use
    #
    # The LLM receives tool definitions and decides what context to
    # gather. This naturally generalises to any planning scenario
    # without domain-specific prompt engineering.
    # ------------------------------------------------------------------

    def _assemble_system_prompt(self) -> str:
        """Build the SYSTEM message for the agentic SKETCH LLM call.

        The system prompt teaches a universal planning methodology.
        It does NOT contain domain-specific instructions -- the LLM
        discovers domain context through the tools provided to it.

        Returns:
            The complete system prompt string.
        """
        schema_text = json.dumps(SKETCH_OUTPUT_SCHEMA, indent=2)

        return (
            "You are a planning engine.\n"
            "\n"
            "Given a user's intent, your job is to:\n"
            "1. UNDERSTAND what the user actually wants.\n"
            "2. GATHER context by calling the tools available to "
            "you. Search for relevant capabilities, check the "
            "user's current situation, and recall relevant history.\n"
            "3. DECOMPOSE the intent into concrete, actionable "
            "steps that the system's capabilities can execute.\n"
            "4. OUTPUT a structured plan as JSON.\n"
            "\n"
            "PLANNING PRINCIPLES:\n"
            "- Call discover_capabilities to find what the system "
            "can do. You may call it multiple times.\n"
            "- Call query_session_context to understand the user's "
            "current situation.\n"
            "- Call recall_long_term_memory to learn from history "
            "and preferences.\n"
            "- Call find_prompts when a step needs a dynamically "
            "created agent -- find the right prompt template for "
            "the agent's behaviour.\n"
            "- Each step must describe ONE concrete action.\n"
            "- Prefer the minimal number of steps.\n"
            "- Express step dependencies via depends_on using the "
            "exact intent strings of preceding steps (NOT indices).\n"
            "- Only suggest capabilities you discovered via "
            "discover_capabilities.\n"
            "- If the intent is genuinely ambiguous, set "
            "needs_clarification to true and ask ONE specific "
            "question.\n"
            "\n"
            "When ready, respond with ONLY valid JSON conforming "
            "to this schema:\n"
            f"{schema_text}\n"
        )

    def _build_initial_messages(
        self,
        intent: str,
        constraints: Optional[Dict[str, Any]] = None,
        hil_addendum: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Build the initial message list for the agentic LLM call.

        Contains:
          1. System message (planning methodology + output schema)
          2. User message (intent + optional constraint hints +
             optional HIL clarification from a prior round)

        Args:
            intent: The raw user intent.
            constraints: Optional hard constraints dict.
            hil_addendum: Optional clarification text from HIL.

        Returns:
            List of message dicts with ``role`` and ``content`` keys.
        """
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self._assemble_system_prompt()},
        ]

        parts: List[str] = [intent]

        if constraints:
            constraint_lines: List[str] = []
            safety_band = constraints.get("safety_band")
            if safety_band and safety_band != "GREEN":
                constraint_lines.append(f"Safety restriction: {safety_band}")
            temporal = constraints.get("temporal", {})
            if isinstance(temporal, dict):
                now = temporal.get("now")
                if now:
                    constraint_lines.append(f"Current time: {now}")
                tz = temporal.get("device_tz")
                if tz:
                    constraint_lines.append(f"Timezone: {tz}")
            if constraint_lines:
                parts.append("\n[Context: " + ", ".join(constraint_lines) + "]")

        if hil_addendum:
            parts.append(f"\n[User clarification: {hil_addendum}]")

        messages.append({"role": "user", "content": "\n".join(parts)})

        return messages

    def _get_tool_definitions(self) -> Tuple[Dict[str, Any], ...]:
        """Return the tool definitions for the agentic SKETCH call.

        The 4 tools map to ToolCallRouter methods:
          - discover_capabilities -> tool_router.discover()
          - query_session_context -> tool_router.read_context()
          - recall_long_term_memory -> tool_router.recall_memory()
          - find_prompts -> tool_router.find_prompts()

        Returns:
            Tuple of tool definition dicts in OpenAI function-calling
            format.
        """
        return SKETCH_TOOL_DEFINITIONS

    # ------------------------------------------------------------------
    # HubRequest construction
    # ------------------------------------------------------------------

    def _build_hub_request(
        self,
        messages: List[Dict[str, Any]],
        ctx: StageContext,
        *,
        tools: Optional[Tuple[Dict[str, Any], ...]] = None,
    ) -> PlannerLLMRequest:
        """Build a PlannerLLMRequest for an LLM call.

        Args:
            messages: Conversation messages list.
            ctx: Stage context with budget information.
            tools: Optional tool definitions for agentic calls.

        Returns:
            PlannerLLMRequest ready for ILLMPort.execute().
        """
        payload: Dict[str, Any] = {
            "messages": messages,
            "temperature": 0.7,
        }
        if tools:
            payload["tools"] = list(tools)

        constraints = PlannerConstraints(
            max_tokens=ctx.stage_budget.max_tokens if ctx.stage_budget else 2048,
            timeout_ms=ctx.stage_budget.timeout_ms if ctx.stage_budget else 8000,
            temperature=0.7,
            consumer_id="planner",
        )

        return PlannerLLMRequest(
            capability="CHAT",
            payload=payload,
            constraints=constraints,
            trace_id=ctx.trace_id,
        )

    # ------------------------------------------------------------------
    # Tool call dispatch
    # ------------------------------------------------------------------

    async def _dispatch_tool_call(
        self,
        tool_call: Dict[str, Any],
        request: PlanRequest,
        ctx: StageContext,
    ) -> Any:
        """Route a single LLM tool call to the ToolCallRouter.

        Parses the tool call, dispatches to the correct router method,
        and returns the result (or an error dict on failure).

        Args:
            tool_call: Tool call dict from LLM response with
                ``function.name`` and ``function.arguments``.
            request: The current plan request (for session_id, trace_id).
            ctx: Stage context.

        Returns:
            Tool result (any JSON-serialisable value).
        """
        func = tool_call.get("function", {})
        name = func.get("name", "")
        raw_args = func.get("arguments", "{}")

        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except (json.JSONDecodeError, TypeError):
            args = {}

        try:
            if name == "discover_capabilities":
                return await self._tool_router.discover(
                    intent=args.get("intent", ""),
                    domain=args.get("domain"),
                    top_k=args.get("top_k", 10),
                )

            if name == "query_session_context":
                session_id = ""
                if request.context is not None:
                    session_id = getattr(request.context, "session_id", "")
                return await self._tool_router.read_context(
                    session_id=session_id,
                    sections=args.get("sections", []),
                )

            if name == "recall_long_term_memory":
                return await self._tool_router.recall_memory(
                    query=args.get("query", ""),
                    trace_id=ctx.trace_id,
                )

            if name == "find_prompts":
                return await self._tool_router.find_prompts(
                    intent=args.get("intent", ""),
                    domain=args.get("domain"),
                    top_k=args.get("top_k", 5),
                )

            log.warning("Unknown tool call: %s", name)
            return {"error": f"Unknown tool: {name}"}

        except Exception as exc:
            log.warning("Tool call %s failed: %s", name, exc)
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_response(
        self,
        content: str,
        discovery_results: List[Any],
    ) -> Tuple[SketchResult, bool, str]:
        """Parse LLM JSON output into a SketchResult.

        Validates the JSON structure against SKETCH_OUTPUT_SCHEMA
        expectations, builds RoughStep objects, and assembles the
        final SketchResult.

        Args:
            content: Raw LLM output string (should be valid JSON).
            discovery_results: Accumulated capability discovery results
                from tool calls during the agentic loop.

        Returns:
            Tuple of (SketchResult, needs_clarification, clarification_question).

        Raises:
            SketchFailedError: If the content cannot be parsed or
                does not contain valid plan data.
        """
        # Strip markdown fences if present.
        text = content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last fence lines.
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SketchFailedError(
                f"LLM output is not valid JSON: {exc}",
                stage="SKETCH",
            ) from exc

        if not isinstance(data, dict):
            raise SketchFailedError(
                "LLM output must be a JSON object",
                stage="SKETCH",
            )

        raw_steps = data.get("rough_steps", [])
        if not raw_steps:
            raise SketchFailedError(
                "LLM output missing or empty rough_steps",
                stage="SKETCH",
            )

        rationale = data.get("rationale", "")
        if not rationale:
            raise SketchFailedError(
                "LLM output missing rationale",
                stage="SKETCH",
            )

        # Build RoughStep list.
        # P08 fix: depends_on entries are intent strings (stable identifiers),
        # not zero-based integer indices. The previous integer scheme was
        # fragile under reordering and silently dropped out-of-range indices.
        known_intents: set[str] = set()
        for raw in raw_steps:
            intent = raw.get("intent", "")
            if intent:
                known_intents.add(intent)

        steps: List[RoughStep] = []
        for raw in raw_steps:
            raw_deps = raw.get("depends_on", [])
            unknown_deps = [d for d in raw_deps if not (isinstance(d, str) and d in known_intents)]
            if unknown_deps:
                raise SketchFailedError(
                    (
                        "LLM produced unknown depends_on intent strings "
                        f"{unknown_deps!r} for step intent="
                        f"{raw.get('intent', '')!r}; valid intents are "
                        f"{sorted(known_intents)!r}"
                    ),
                    stage="SKETCH",
                )
            step = RoughStep(
                intent=raw.get("intent", ""),
                suggested_capability=raw.get("suggested_capability"),
                depends_on=list(raw_deps),
            )
            steps.append(step)

        # Collect ScoredCapability objects from discovery results.
        scored_capabilities: List[Any] = []
        for result in discovery_results:
            if result is None:
                continue
            # RetrievalResult has a .capabilities attribute.
            caps = getattr(result, "capabilities", None)
            if caps:
                scored_capabilities.extend(caps)

        # Build SketchResult -- its __post_init__ validates.
        needs_clarification = data.get("needs_clarification", False)
        clarification_question = data.get("clarification_question", "")

        return (
            SketchResult(
                rough_steps=steps,
                capability_candidates=scored_capabilities,
                rationale=rationale,
            ),
            needs_clarification,
            clarification_question,
        )

    # ------------------------------------------------------------------
    # Agentic loop -- core of the SKETCH stage
    # ------------------------------------------------------------------

    async def _run_agentic_loop(
        self,
        messages: List[Dict[str, Any]],
        request: PlanRequest,
        ctx: StageContext,
        *,
        use_tools: bool = True,
    ) -> Tuple[str, List[Any]]:
        """Run the agentic tool-calling loop with the LLM.

        Sends messages to the LLM with tool definitions. If the LLM
        responds with tool calls, dispatches them and feeds results
        back. Repeats until the LLM produces a final text response
        or the round limit is reached.

        Args:
            messages: Initial message list (system + user).
            request: The plan request (for tool dispatch context).
            ctx: Stage context.
            use_tools: Whether to provide tool definitions.

        Returns:
            Tuple of (final_content, discovery_results).

        Raises:
            SketchFailedError: If the LLM never produces a final
                answer within the round limit.
        """
        tools = self._get_tool_definitions() if use_tools else None
        discovery_results: List[Any] = []

        for round_num in range(_MAX_TOOL_ROUNDS):
            if ctx.cancel_check():
                raise SketchFailedError(
                    "Plan cancelled during SKETCH",
                    stage="SKETCH",
                    request_id=ctx.request_id,
                    trace_id=ctx.trace_id,
                )

            hub_request = self._build_hub_request(messages, ctx, tools=tools)
            hub_response: PlannerLLMResponse = await self._llm_port.execute(hub_request)

            result = hub_response.result if hub_response.result else {}
            content = result.get("content", "")
            tool_calls = result.get("tool_calls", [])

            if not tool_calls:
                # LLM produced final answer.
                if not content:
                    raise SketchFailedError(
                        "LLM returned empty response with no tool calls",
                        stage="SKETCH",
                        request_id=ctx.request_id,
                        trace_id=ctx.trace_id,
                    )
                return content, discovery_results

            # LLM wants to call tools -- process them.
            messages.append(
                {
                    "role": "assistant",
                    "content": content or "",
                    "tool_calls": tool_calls,
                }
            )

            for tc in tool_calls:
                tc_result = await self._dispatch_tool_call(tc, request, ctx)

                # Track discovery results.
                func_name = tc.get("function", {}).get("name", "")
                if func_name == "discover_capabilities":
                    discovery_results.append(tc_result)

                # Serialize tool result for the LLM.
                try:
                    serialized = json.dumps(tc_result, default=str)
                except (TypeError, ValueError):
                    serialized = str(tc_result)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": serialized,
                    }
                )

            log.debug(
                "SKETCH agentic round %d: %d tool calls dispatched",
                round_num + 1,
                len(tool_calls),
            )

        # Exhausted rounds without a final answer.
        raise SketchFailedError(
            f"LLM did not produce a plan after {_MAX_TOOL_ROUNDS} tool-calling rounds",
            stage="SKETCH",
            request_id=ctx.request_id,
            trace_id=ctx.trace_id,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def execute(
        self,
        request: PlanRequest,
        ctx: StageContext,
    ) -> SketchResult:
        """Run the full SKETCH stage pipeline (Section 6).

        Orchestrates the complete Stage 1 flow using an agentic
        tool-calling loop:
          1. Build initial messages (system prompt + user intent)
          2. Run agentic loop (LLM calls tools, gathers context)
          3. Parse LLM's final JSON response into SketchResult
          4. If needs_clarification: HIL flow, then re-run
          5. On failure: one retry with simplified prompt

        Args:
            request: The plan request from Orchestrator.
            ctx: Stage context with trace_id, budget, cancel_check.

        Returns:
            SketchResult with rough_steps, capability_candidates,
            and rationale.

        Raises:
            SketchFailedError: After all retry paths exhausted.
        """
        log.info(
            "SKETCH execute: request_id=%s, intent=%.80s",
            request.request_id,
            request.intent,
        )

        try:
            return await self._execute_attempt(request, ctx, hil_addendum=None, allow_hil=True)
        except SketchFailedError:
            # Retry once with simplified prompt (no tools, direct ask).
            log.warning(
                "SKETCH first attempt failed for request_id=%s, retrying simplified",
                request.request_id,
            )
            try:
                return await self._execute_attempt(
                    request, ctx, hil_addendum=None, allow_hil=False, simplified=True
                )
            except Exception as retry_exc:
                raise SketchFailedError(
                    f"SKETCH failed after retry: {retry_exc}",
                    stage="SKETCH",
                    request_id=ctx.request_id,
                    trace_id=ctx.trace_id,
                ) from retry_exc

    async def _execute_attempt(
        self,
        request: PlanRequest,
        ctx: StageContext,
        *,
        hil_addendum: Optional[str] = None,
        allow_hil: bool = True,
        simplified: bool = False,
    ) -> SketchResult:
        """Single execution attempt (used by execute for try/retry).

        Args:
            request: The plan request.
            ctx: Stage context.
            hil_addendum: Optional HIL clarification from prior round.
            allow_hil: Whether to allow HIL clarification flow.
            simplified: If True, skip tools and ask LLM directly.

        Returns:
            SketchResult.

        Raises:
            SketchFailedError: On any unrecoverable error.
        """
        messages = self._build_initial_messages(
            intent=request.intent,
            constraints=request.constraints,
            hil_addendum=hil_addendum,
        )

        if simplified:
            # Add a note asking for a direct plan without tool calls.
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Generate a plan using your best judgment. "
                        "Do not call any tools. Output only JSON."
                    ),
                }
            )

        content, discovery_results = await self._run_agentic_loop(
            messages, request, ctx, use_tools=not simplified
        )

        parsed, needs_clarification, clarification_question = self._parse_response(
            content, discovery_results
        )

        # HIL clarification flow.
        if needs_clarification and allow_hil and clarification_question:
            caller_key = f"planner:sketch:{request.request_id}"
            clar_resp = await self._hil_port.ask_clarification(
                ClarificationRequest(
                    caller_key=caller_key,
                    trace_id=request.request_id,
                    pre_formed_question=clarification_question,
                    synthesize_with_llm=False,
                    question_context={
                        "question": clarification_question,
                        "intent": request.intent,
                    },
                )
            )
            # ANSWERED -> re-run with addendum; TIMEOUT or
            # MAX_ROUNDS_EXCEEDED (round_budget_exhausted) -> proceed
            # with original parsed sketch (best-effort).
            if (
                clar_resp.answer
                and not clar_resp.timed_out
                and not clar_resp.round_budget_exhausted
            ):
                return await self._execute_attempt(
                    request,
                    ctx,
                    hil_addendum=clar_resp.answer,
                    allow_hil=False,  # Only 1 clarification round.
                )

        return parsed

    async def micro_execute(
        self,
        request: MicroReplanRequest,
        ctx: StageContext,
    ) -> SketchResult:
        """Run abbreviated micro-SKETCH for micro-replan (Section 10.3.2).

        Simplified SKETCH pipeline for mid-DAG micro-replan:
          - Dedicated micro-replan system prompt (not full SKETCH)
          - Structured user message with 5 sections: ORIGINAL_INTENT,
            COMPLETED_SUMMARY, REMAINING_STEPS, DISCOVERIES,
            FAILURE_CONTEXT
          - No HIL clarification (PLAN-12, Section 10.5.4)
          - At most 1 discover_capabilities tool call (vs 3 in full)
          - Budget: max_tokens=1024, timeout_ms=5000, temp=0.7

        Args:
            request: Micro-replan request with partial plan context.
            ctx: Stage context with micro-replan budget envelope.

        Returns:
            SketchResult for the micro-replanned portion.

        Raises:
            SketchFailedError: If planning fails (no retry in micro).
        """
        log.info(
            "SKETCH micro_execute: request_id=%s, original_plan=%s",
            request.request_id,
            request.original_plan_id,
        )

        messages = self._build_micro_sketch_messages(request)

        try:
            content, discovery_results = await self._run_agentic_loop(
                messages, _micro_to_plan_request(request), ctx
            )
            parsed, _needs_hil, _question = self._parse_response(
                content,
                discovery_results,
            )
            return parsed
        except SketchFailedError:
            raise
        except Exception as exc:
            raise SketchFailedError(
                f"Micro-SKETCH failed: {exc}",
                stage="SKETCH",
                request_id=ctx.request_id,
                trace_id=ctx.trace_id,
            ) from exc

    # ------------------------------------------------------------------
    # Micro-replan prompt construction (Section 10.3.2)
    # ------------------------------------------------------------------

    def _build_micro_sketch_messages(
        self,
        request: MicroReplanRequest,
    ) -> List[Dict[str, Any]]:
        """Build message list for micro-SKETCH LLM call.

        Produces a micro-replan-specific system prompt (not the
        generic SKETCH prompt) and a structured user message with
        5 sections per Section 10.3.2.

        Args:
            request: The MicroReplanRequest.

        Returns:
            List of message dicts [system, user].
        """
        system_prompt = self._assemble_micro_system_prompt()
        user_content = self._assemble_micro_user_message(request)
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

    def _assemble_micro_system_prompt(self) -> str:
        """Build the SYSTEM message for micro-SKETCH (Section 10.3.2).

        Key differences from full SKETCH system prompt:
          - Role is micro-replan (re-plan remaining portion)
          - No multi-tool gathering instructions (context already provided)
          - At most 1 discover_capabilities call if LLM needs new caps
          - Output schema reuses SKETCH_OUTPUT_SCHEMA (rough_steps)

        Returns:
            The complete micro-replan system prompt string.
        """
        schema_text = json.dumps(SKETCH_OUTPUT_SCHEMA, indent=2)

        return (
            "You are a MICRO-REPLAN planning engine.\n"
            "\n"
            "A plan was partially executed. Some steps completed "
            "successfully, but new information (discoveries or a "
            "failure) means the remaining steps need replanning.\n"
            "\n"
            "YOUR JOB:\n"
            "1. UNDERSTAND what changed based on the discoveries "
            "and/or failure context provided.\n"
            "2. DETERMINE which remaining steps are still valid and "
            "which need replacement or modification.\n"
            "3. PRODUCE replacement steps that account for the new "
            "information and completed step outputs.\n"
            "4. OUTPUT a structured plan as JSON.\n"
            "\n"
            "MICRO-REPLAN RULES:\n"
            "- Completed steps are FROZEN. Do NOT modify, remove, "
            "or re-execute them.\n"
            "- You MAY call discover_capabilities ONCE if replacement "
            "steps need new capabilities not in the original plan.\n"
            "- Do NOT call query_session_context or "
            "recall_long_term_memory -- completed_results provides "
            "sufficient context.\n"
            "- Prefer the minimal change: reuse remaining steps that "
            "are still valid.\n"
            "- Express step dependencies via depends_on using the "
            "exact intent strings of preceding steps (NOT indices). "
            "Replacement steps may depend on completed step outputs by "
            "intent string.\n"
            "- Do NOT request clarification (set "
            "needs_clarification to false).\n"
            "\n"
            "When ready, respond with ONLY valid JSON conforming "
            "to this schema:\n"
            f"{schema_text}\n"
        )

    def _assemble_micro_user_message(
        self,
        request: MicroReplanRequest,
    ) -> str:
        """Build the USER message for micro-SKETCH (Section 10.3.2).

        5 structured sections:
          1. ORIGINAL_INTENT -- from original plan context
          2. COMPLETED_SUMMARY -- step_id + capability + status + outputs
          3. REMAINING_STEPS -- uncompleted steps needing replan
          4. DISCOVERIES -- new info that invalidated remaining steps
          5. FAILURE_CONTEXT -- if present: failed step details

        Args:
            request: The MicroReplanRequest.

        Returns:
            Formatted user message string.
        """
        parts: List[str] = []

        # Section 1: ORIGINAL_INTENT
        intent = getattr(request, "intent", None) or "micro-replan"
        parts.append(f"ORIGINAL_INTENT: {intent}")

        # Section 2: COMPLETED_SUMMARY
        parts.append("\nCOMPLETED_SUMMARY:")
        completed = getattr(request, "completed_results", {}) or {}
        if completed:
            for step_id, result in completed.items():
                status = getattr(
                    result.status,
                    "value",
                    str(result.status),
                )
                cap = result.capability_name or "unknown"
                line = f"  {step_id} ({cap}): {status}"
                # Include key output data if available.
                result_data = getattr(result, "result", None)
                if result_data is not None:
                    data = getattr(result_data, "data", result_data)
                    if isinstance(data, dict):
                        keys = list(data.keys())[:5]
                        line += f" [outputs: {', '.join(keys)}]"
                parts.append(line)
        else:
            parts.append("  (no completed steps)")

        # Section 3: REMAINING_STEPS
        parts.append("\nREMAINING_STEPS:")
        for step in request.remaining_steps:
            sid = getattr(step, "id", "?")
            cap = getattr(step, "capability", "unknown")
            params = getattr(step, "params", {}) or {}
            param_keys = ", ".join(params.keys()) if params else "none"
            parts.append(f"  {sid} ({cap}): params=[{param_keys}]")

        # Section 4: DISCOVERIES
        discoveries = getattr(request, "discoveries", []) or []
        parts.append("\nDISCOVERIES:")
        if discoveries:
            for disc in discoveries:
                field = getattr(disc, "field", "?")
                value = getattr(disc, "value", "?")
                source = getattr(disc, "source_step_id", "?")
                parts.append(f"  {field} = {value} (from step {source})")
        else:
            parts.append("  (no discoveries)")

        # Section 5: FAILURE_CONTEXT
        fc = getattr(request, "failure_context", None)
        if fc:
            parts.append("\nFAILURE_CONTEXT:")
            parts.append(f"  step_id: {fc.step_id}")
            parts.append(f"  error_code: {fc.error_code}")
            parts.append(f"  error_message: {fc.error_message}")
            partial = getattr(fc, "partial_result", None)
            if partial is not None:
                parts.append(f"  partial_result: {partial}")

        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _micro_to_plan_request(micro: MicroReplanRequest) -> PlanRequest:
    """Adapt a MicroReplanRequest to PlanRequest for tool dispatch.

    The agentic loop needs a PlanRequest for _dispatch_tool_call
    context (session_id, trace_id). This creates a minimal adapter.
    """
    return PlanRequest(
        intent="micro-replan",
        trace_id=micro.trace_id,
        request_id=micro.request_id,
    )
