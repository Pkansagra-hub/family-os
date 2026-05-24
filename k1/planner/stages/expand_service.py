"""
k1.planner.stages.expand_service -- ExpandService (Epic 3.2).

Stage 2 of the planner pipeline: transforms SketchResult into a fully
parameterised ExpandedPlan (15-field PlanStep objects) via agentic
tool-calling loop, post-LLM enrichment of infrastructure fields, prompt
binding validation, and fallback-capable error recovery.

Design
------
- Layer 2 (Section 30.6): imports Layer 1 ports (ILLMPort), Layer 0
  types (SketchResult, ExpandedPlan, PlanStep, PlanRequest, StageContext,
  PlannerLLMRequest, PlannerLLMResponse, PlannerConstraints, ExpandFailedError), and
  shared types from Orchestrator (PlanStep, StepResult, PlanRequest,
  MicroReplanRequest).
- Stateless between calls: no per-plan instance state. All per-plan
  state flows through StageContext and method parameters.
- ExpandService does NOT hold a reference to PipelineController. Token
  recording is done by PipelineController after receiving ExpandedPlan.
- ExpandService does NOT hold HILCoordinator (no HIL in EXPAND).
- PLAN-01: zero writes to SessionState.
- PLAN-06: zero capability executions.

AGENTIC TOOL-USE DESIGN:
- The LLM receives tool definitions and decides what context to gather.
- 4 tools: discover_capabilities, get_capability_schema, find_prompts,
  query_session_context.
- The LLM calls tools as needed, then produces the final plan JSON.
- Post-LLM enrichment fills infrastructure fields from CapabilityContract
    metadata and validates prompt/profile bindings (not LLM-generated).

ToolCallRouter is referenced via the ToolCallRouterLike protocol from
sketch_service -- same protocol extended with get_schema() for EXPAND.

Public interface
----------------
async execute(sketch_result, request, ctx, arbiter_feedback?) -> ExpandedPlan
    Full EXPAND pipeline: agentic loop (LLM + tools) -> parse ->
    enrich -> result. Supports arbiter feedback injection for revise loop.
async micro_execute(micro_sketch_result, completed_results, ctx) -> ExpandedPlan
    Abbreviated micro-EXPAND for micro-replan: reduced budget, no
    arbiter feedback.

Consumers
---------
PipelineController._run_expand() -- calls execute() / micro_execute()

References
----------
- planner.md Section 7 (Stage 2 EXPAND Deep Dive)
- planner.md Section 11 (Discovery Tools)

Exports
-------
ExpandService, ExpandToolRouterLike,
EXPAND_OUTPUT_SCHEMA, EXPAND_TOOL_DEFINITIONS
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import (
    Any,
    Dict,
    List,
    Literal,
    Optional,
    Protocol,
    Tuple,
    runtime_checkable,
)

from k1.orchestrator.types import PlanRequest, PlanStep, StepResult
from k1.planner.ports.llm_port import ILLMPort
from k1.planner.types import (
    ExpandedPlan,
    ExpandFailedError,
    PlannerConstraints,
    PlannerLLMRequest,
    PlannerLLMResponse,
    SketchResult,
    StageContext,
)

log = logging.getLogger(__name__)

# Maximum number of agentic tool-calling rounds before forcing final answer.
_MAX_TOOL_ROUNDS = 6

# Default timeout_ms when no contract metadata is available.
_DEFAULT_TIMEOUT_MS = 10000

PromptBindingState = Literal["valid", "cleared", "missing_inventory"]


@dataclass(frozen=True)
class PromptBindingResult:
    """Validated binding for an LLM-proposed prompt template."""

    state: PromptBindingState
    resolved_name: Optional[str] = None
    reason: str = ""


@dataclass(frozen=True)
class _PromptDescriptor:
    """Small prompt contract view used by EXPAND validation."""

    name: str
    domains: Tuple[str, ...] = ()
    activity_profile: Optional[str] = None
    compatible_agents: Tuple[str, ...] = ()
    compatible_tools: Tuple[str, ...] = ()
    score: float = 0.0


def validate_prompt_binding(
    *,
    requested_template: str | None,
    capability_name: str,
    discovered_prompts: List[Dict[str, Any]],
    prompt_inventory: set[str],
) -> PromptBindingResult:
    """Validate an LLM-proposed prompt template against registry evidence."""
    requested = _clean_optional_str(requested_template)
    if requested is None:
        return PromptBindingResult(
            state="valid",
            resolved_name=None,
            reason="no_prompt_template_requested",
        )

    descriptors = _prompt_descriptors_from_items(discovered_prompts)
    discovered_names = {descriptor.name for descriptor in descriptors if descriptor.name}

    if requested in discovered_names:
        return PromptBindingResult(
            state="valid",
            resolved_name=requested,
            reason="discovered_prompt_match",
        )

    if requested in prompt_inventory:
        return PromptBindingResult(
            state="missing_inventory",
            resolved_name=requested,
            reason="prompt_inventory_match_without_discovery",
        )

    return PromptBindingResult(
        state="cleared",
        resolved_name=None,
        reason="prompt_not_discovered_or_in_inventory",
    )


def _clean_optional_str(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _prompt_descriptors_from_results(results: Any) -> List[_PromptDescriptor]:
    descriptors: List[_PromptDescriptor] = []
    for result in results or []:
        descriptors.extend(_prompt_descriptors_from_result(result))
    return descriptors


def _prompt_descriptors_from_result(result: Any) -> List[_PromptDescriptor]:
    if result is None:
        return []

    if isinstance(result, Mapping):
        for key in ("capabilities", "prompts", "templates", "results"):
            raw_items = result.get(key)
            if isinstance(raw_items, list):
                return _prompt_descriptors_from_items(raw_items)
        descriptor = _prompt_descriptor_from_value(result)
        return [descriptor] if descriptor is not None else []

    capabilities = getattr(result, "capabilities", None)
    if capabilities is not None:
        return _prompt_descriptors_from_items(list(capabilities))

    descriptor = _prompt_descriptor_from_value(result)
    return [descriptor] if descriptor is not None else []


def _prompt_descriptors_from_items(items: Iterable[Any]) -> List[_PromptDescriptor]:
    descriptors: List[_PromptDescriptor] = []
    for item in items:
        descriptor = _prompt_descriptor_from_value(item)
        if descriptor is not None:
            descriptors.append(descriptor)
    return descriptors


def _prompt_descriptor_from_value(value: Any) -> Optional[_PromptDescriptor]:
    if isinstance(value, _PromptDescriptor):
        return value

    score = _safe_float(_mapping_or_attr(value, "score"), default=0.0)
    contract = _mapping_or_attr(value, "contract")
    source = contract if contract is not None else value

    name = _clean_optional_str(_mapping_or_attr(source, "name"))
    if name is None:
        return None

    return _PromptDescriptor(
        name=name,
        domains=_string_tuple(_mapping_or_attr(source, "domain")),
        activity_profile=_clean_optional_str(_mapping_or_attr(source, "activity_profile")),
        compatible_agents=_string_tuple(_mapping_or_attr(source, "compatible_agents")),
        compatible_tools=_string_tuple(_mapping_or_attr(source, "compatible_tools")),
        score=score,
    )


def _mapping_or_attr(value: Any, key: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)


def _string_tuple(value: Any) -> Tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Iterable):
        return tuple(str(item) for item in value if item)
    return ()


def _safe_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_prompt_inventory(
    prompt_inventory: Mapping[str, Any] | Iterable[Any],
) -> Dict[str, _PromptDescriptor]:
    if isinstance(prompt_inventory, Mapping):
        coerced: Dict[str, _PromptDescriptor] = {}
        for name, value in prompt_inventory.items():
            source = dict(value) if isinstance(value, Mapping) else value
            if isinstance(source, dict) and "name" not in source:
                source["name"] = name
            descriptor = _prompt_descriptor_from_value(source)
            if descriptor is None:
                descriptor = _PromptDescriptor(name=str(name))
            coerced[descriptor.name or str(name)] = descriptor
        return coerced

    coerced = {}
    for value in prompt_inventory:
        descriptor = _prompt_descriptor_from_value(value)
        if descriptor is None and isinstance(value, str):
            descriptor = _PromptDescriptor(name=value)
        if descriptor is not None:
            coerced[descriptor.name] = descriptor
    return coerced


def _is_step_id(value: Any) -> bool:
    if not isinstance(value, str) or len(value) < 2 or value[0] != "s":
        return False
    return value[1:].isdigit()


def _format_temporal_constraint_block(temporal: Mapping[str, Any]) -> str:
    """Format typed temporal constraints for EXPAND without ad-hoc now strings."""
    fields = {
        "anchor_id": temporal.get("anchor_id"),
        "now_utc": temporal.get("now_utc"),
        "timezone": temporal.get("timezone"),
    }
    lines = ["Temporal:"]
    for key, value in fields.items():
        if value:
            lines.append(f"  {key}: {value}")
    for key in ("today", "tomorrow"):
        value = temporal.get(key)
        if isinstance(value, Mapping):
            start = value.get("start_local") or value.get("start_utc") or value.get("start")
            end = value.get("end_local") or value.get("end_utc") or value.get("end")
            if start or end:
                lines.append(f"  {key}: {start or '?'} -> {end or '?'}")
        elif value:
            lines.append(f"  {key}: {value}")
    resolved = temporal.get("resolved_expressions")
    if isinstance(resolved, list) and resolved:
        lines.append("  resolved_expressions:")
        for item in resolved:
            if isinstance(item, Mapping):
                raw = item.get("raw_text", "")
                label = item.get("normalized_label", item.get("resolution_kind", ""))
                if raw or label:
                    lines.append(f"    - {raw}: {label}")
            elif item:
                lines.append(f"    - {item}")
    return "\n".join(lines) if len(lines) > 1 else ""


# ---------------------------------------------------------------------------
# Output schema -- the JSON Schema the LLM must conform to (Section 7.4.1).
# ---------------------------------------------------------------------------

EXPAND_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["steps", "dependencies", "rationale"],
    "properties": {
        "steps": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["id", "capability", "params"],
                "properties": {
                    "id": {
                        "type": "string",
                        "description": (
                            "Unique step identifier: 's' followed by digits " "(e.g. 's1', 's2')."
                        ),
                    },
                    "capability": {
                        "type": "string",
                        "minLength": 1,
                        "description": (
                            "The exact capability name to execute. "
                            "Must match a discovered capability."
                        ),
                    },
                    "params": {
                        "type": "object",
                        "description": (
                            "Input parameters for the capability. "
                            "May contain inter-step references using "
                            "$<step_id>.result.<field> syntax."
                        ),
                    },
                    "deps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": ("Step IDs that must complete before this " "step begins."),
                    },
                    "prompt_template": {
                        "type": ["string", "null"],
                        "description": (
                            "Prompt template name for agent steps. "
                            "Use find_prompts to discover available "
                            "templates."
                        ),
                    },
                    "tools_granted": {
                        "type": ["array", "null"],
                        "items": {"type": "string"},
                        "description": ("Tools the step may use during execution."),
                    },
                    "output_schema": {
                        "type": ["object", "null"],
                        "description": (
                            "Expected output schema. Filled from " "capability contract if omitted."
                        ),
                    },
                    "is_optional": {
                        "type": "boolean",
                        "description": (
                            "Whether this step can be skipped without " "failing the plan."
                        ),
                    },
                },
            },
        },
        "dependencies": {
            "type": "object",
            "additionalProperties": {
                "type": "array",
                "items": {"type": "string"},
            },
            "description": (
                "Map of step_id -> [predecessor_step_ids]. " "Must form a DAG (no cycles)."
            ),
        },
        "rationale": {
            "type": "string",
            "minLength": 1,
            "description": (
                "Explain why these specific capabilities, parameters, "
                "and dependencies were chosen."
            ),
        },
    },
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Tool definitions for agentic tool-use (Issue 3.2.2).
# EXPAND uses 4 tools (no recall_long_term_memory -- SKETCH already
# gathered that context). Adds get_capability_schema for full contract
# lookup by exact name.
# ---------------------------------------------------------------------------

EXPAND_TOOL_DEFINITIONS: Tuple[Dict[str, Any], ...] = (
    {
        "type": "function",
        "function": {
            "name": "discover_capabilities",
            "description": (
                "Search the capability registry for capabilities that "
                "match a task intent. Returns scored matches with names, "
                "descriptions, required inputs, and domain tags. Use "
                "this to refine or confirm capability choices from the "
                "rough plan -- call per-step for precise matching."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": (
                            "Natural language description of the task "
                            "or sub-task you need a capability for."
                        ),
                    },
                    "domain": {
                        "type": "string",
                        "description": (
                            "Optional domain filter to narrow results "
                            "(e.g. 'calendar', 'messaging', 'finance')."
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
    {
        "type": "function",
        "function": {
            "name": "get_capability_schema",
            "description": (
                "Look up the full contract for a capability by its "
                "exact name. Returns full input/output schemas, "
                "required context, side effects, timeout, compensation "
                "logic, and safety band. Use this after discovering a "
                "capability to get the detail needed for precise "
                "parameterization."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "capability_name": {
                        "type": "string",
                        "description": (
                            "Exact capability name (e.g. " "'agent.execute.calendar_creator')."
                        ),
                    },
                    "version": {
                        "type": "string",
                        "description": (
                            "Optional version constraint (e.g. '>=1.0'). " "Defaults to latest."
                        ),
                    },
                },
                "required": ["capability_name"],
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
    {
        "type": "function",
        "function": {
            "name": "query_session_context",
            "description": (
                "Read the current session state to get concrete values "
                "for step parameters. Returns structured data about "
                "entities, persona, time, safety settings. Use this "
                "to fill in parameter values that depend on the user's "
                "current situation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sections": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Which sections to read. Available: "
                            "'beliefs_active', 'persona', 'temporal', "
                            "'history_recent'."
                        ),
                    },
                },
                "required": ["sections"],
            },
        },
    },
)


# ---------------------------------------------------------------------------
# Sentinel protocol for the tool router that EXPAND uses.
# Extends the SKETCH ToolCallRouterLike with get_schema().
# ---------------------------------------------------------------------------


@runtime_checkable
class ExpandToolRouterLike(Protocol):
    """Protocol for ToolCallRouter as seen by ExpandService.

    Extends the base ToolCallRouterLike (SKETCH) with get_schema()
    for exact-name capability contract lookup (Section 7.2.2).

    Section 11.5: router mapping 5 abstract tool names to 4 backend
    ports. Monotonic call counter per plan.
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
        """Discover capabilities via IFabricRetrievalPort (Section 11.1)."""
        ...  # pragma: no cover

    async def get_schema(
        self,
        capability_name: str,
        *,
        version: Optional[str] = None,
    ) -> Any:
        """Get full capability contract via IFabricRegistryPort (Section 11.2).

        Backed by Fabric GetCapabilitySchemaHandler -> RegistryLookupLike.
        Returns CapabilityContract (or compatible). Timeout <5ms.
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

    async def read_context(
        self,
        session_id: str,
        sections: list[str],
    ) -> Dict[str, Any]:
        """Query planning context via IStateReadPort (Section 11.3)."""
        ...  # pragma: no cover


# ---------------------------------------------------------------------------
# ExpandService
# ---------------------------------------------------------------------------


class ExpandService:
    """Stage 2 EXPAND: SketchResult -> ExpandedPlan (Section 7).

    Transforms a SketchResult (rough steps with capability hints) into
    a fully parameterised ExpandedPlan with 15-field PlanStep objects
    ready for DAG execution.

    The full execute() pipeline is:
      1. Build initial messages (system prompt + sketch context)
      2. Run agentic loop (LLM calls tools, gathers schema detail)
      3. Parse LLM's final JSON response
      4. Post-LLM enrichment of infrastructure fields
      5. Assemble ExpandedPlan
      6. Error recovery: try -> retry (simplified) -> fallback (degraded)

    The abbreviated micro_execute() pipeline is:
      Steps 1-5 with reduced budget, no arbiter feedback, no fallback.

    Stateless between calls: no mutable instance state. All per-plan
    state flows through method parameters and StageContext.

    Invariants
    ----------
    PLAN-01 : Zero writes to SessionState.
    PLAN-06 : Zero capability executions.
    PLAN-11 : Budget from StageContext.

    Thread safety
    -------------
    Safe for sequential calls from PipelineController. Not designed
    for concurrent execute() calls on the same instance.
    """

    __slots__ = (
        "_llm_port",
        "_tool_router",
        "_prompt_inventory",
    )

    def __init__(
        self,
        llm_port: ILLMPort,
        tool_router: ExpandToolRouterLike,
        prompt_inventory: Mapping[str, Any] | Iterable[Any] | None = None,
    ) -> None:
        """Construct ExpandService with injected dependencies.

        Args:
            llm_port: LLM gateway for structured/chat completions.
            tool_router: Tool call dispatcher (Section 11).
            prompt_inventory: Optional prompt-contract inventory used to
                validate LLM-selected prompt_template names.

        Raises:
            TypeError: If any dependency is None.
        """
        if llm_port is None:
            raise TypeError("llm_port must not be None")
        if tool_router is None:
            raise TypeError("tool_router must not be None")

        self._llm_port = llm_port
        self._tool_router = tool_router
        self._prompt_inventory = (
            {} if prompt_inventory is None else _coerce_prompt_inventory(prompt_inventory)
        )

    # ------------------------------------------------------------------
    # Read-only property accessors
    # ------------------------------------------------------------------

    @property
    def llm_port(self) -> ILLMPort:
        """LLM gateway port (read-only)."""
        return self._llm_port

    @property
    def tool_router(self) -> ExpandToolRouterLike:
        """Tool call router (read-only)."""
        return self._tool_router

    # ------------------------------------------------------------------
    # Prompt construction -- Agentic tool-use
    # ------------------------------------------------------------------

    def _assemble_system_prompt(self) -> str:
        """Build the SYSTEM message for the agentic EXPAND LLM call.

        The system prompt instructs the LLM to produce fully
        parameterised plan steps from the rough SKETCH output.
        Infrastructure fields are filled automatically post-LLM.

        Returns:
            The complete system prompt string.
        """
        schema_text = json.dumps(EXPAND_OUTPUT_SCHEMA, indent=2)

        return (
            "You are the EXPAND stage planner.\n"
            "\n"
            "You receive a rough plan (from SKETCH) and must produce "
            "fully parameterised executable steps.\n"
            "\n"
            "YOUR JOB:\n"
            "1. For each rough step, determine the EXACT capability "
            "to use. Call discover_capabilities or get_capability_schema "
            "to confirm.\n"
            "2. Fill in ALL required parameters for each capability. "
            "Call query_session_context if you need current values "
            "(user name, timezone, etc.).\n"
            "3. If a step needs a dynamically created agent, call "
            "find_prompts to select the right prompt template.\n"
            "4. Express step dependencies using step IDs.\n"
            "5. Output valid JSON conforming to the schema below.\n"
            "\n"
            "INFRASTRUCTURE FIELDS (filled automatically -- do NOT "
            "set these):\n"
            "- has_side_effects\n"
            "- compensation\n"
            "- timeout_ms\n"
            "- required_context\n"
            "- safety_band_min\n"
            "- condition\n"
            "\n"
            "YOU set these 8 fields per step:\n"
            "- id (s1, s2, ...)\n"
            "- capability (exact name)\n"
            "- params (all required inputs)\n"
            "- deps (predecessor step IDs)\n"
            "- prompt_template (if agent step)\n"
            "- tools_granted (if agent step)\n"
            "- output_schema (if known, otherwise filled from contract)\n"
            "- is_optional (true/false)\n"
            "\n"
            "INTER-STEP REFERENCES:\n"
            "Use $<step_id>.result.<field> syntax in params to "
            "reference outputs from predecessor steps. The step "
            "must appear in deps.\n"
            "\n"
            "When ready, respond with ONLY valid JSON conforming "
            "to this schema:\n"
            f"{schema_text}\n"
        )

    def _build_initial_messages(
        self,
        sketch_result: SketchResult,
        request: PlanRequest,
        arbiter_feedback: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Build the initial message list for the agentic LLM call.

        Contains:
          1. System message (EXPAND methodology + output schema)
          2. User message (original intent + SKETCH output +
             capability candidates + constraints + arbiter feedback)

        Args:
            sketch_result: Output from SKETCH stage.
            request: The original plan request.
            arbiter_feedback: Optional arbiter revision suggestions.

        Returns:
            List of message dicts with ``role`` and ``content`` keys.
        """
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self._assemble_system_prompt()},
        ]

        parts: List[str] = []

        # Original intent (alignment anchor).
        parts.append(f"USER INTENT: {request.intent}")

        # SKETCH rough plan.
        parts.append("\nROUGH PLAN FROM SKETCH:")
        for i, step in enumerate(sketch_result.rough_steps):
            cap_hint = (
                f" [capability: {step.suggested_capability}]" if step.suggested_capability else ""
            )
            deps_hint = f" [depends_on: {step.depends_on}]" if step.depends_on else ""
            parts.append(f"  Step {i + 1}: {step.intent}{cap_hint}{deps_hint}")

        parts.append(f"\nSKETCH RATIONALE: {sketch_result.rationale}")

        # Capability candidates from SKETCH discovery.
        if sketch_result.capability_candidates:
            parts.append("\nDISCOVERED CAPABILITIES:")
            for sc in sketch_result.capability_candidates:
                name = getattr(getattr(sc, "contract", None), "name", str(sc))
                desc = getattr(getattr(sc, "contract", None), "description", "")
                score = getattr(sc, "score", 0.0)
                parts.append(f"  - {name} (score={score:.2f}): {desc}")

        # Constraints.
        if request.constraints:
            constraint_lines: List[str] = []
            safety_band = request.constraints.get("safety_band")
            if safety_band and safety_band != "GREEN":
                constraint_lines.append(f"Safety restriction: {safety_band}")
            temporal = request.constraints.get("temporal", {})
            if isinstance(temporal, dict):
                temporal_block = _format_temporal_constraint_block(temporal)
                if temporal_block:
                    constraint_lines.append(temporal_block)
            if constraint_lines:
                parts.append("\nCONSTRAINTS:\n" + "\n".join(constraint_lines))

        # Arbiter feedback (revise loop).
        if arbiter_feedback:
            parts.append(
                "\nARBITER FEEDBACK: The following issues were found "
                "in the previous EXPAND attempt. Fix them:"
            )
            for fix in arbiter_feedback:
                parts.append(f"  - {fix}")

        messages.append({"role": "user", "content": "\n".join(parts)})

        return messages

    def _get_tool_definitions(self) -> Tuple[Dict[str, Any], ...]:
        """Return the tool definitions for the agentic EXPAND call.

        The 4 tools map to ToolCallRouter methods:
          - discover_capabilities -> tool_router.discover()
          - get_capability_schema -> tool_router.get_schema()
          - find_prompts -> tool_router.find_prompts()
          - query_session_context -> tool_router.read_context()

        Returns:
            Tuple of tool definition dicts in OpenAI function-calling
            format.
        """
        return EXPAND_TOOL_DEFINITIONS

    # ------------------------------------------------------------------
    # PlannerLLMRequest construction
    # ------------------------------------------------------------------

    def _build_hub_request(
        self,
        messages: List[Dict[str, Any]],
        ctx: StageContext,
        *,
        tools: Optional[Tuple[Dict[str, Any], ...]] = None,
    ) -> PlannerLLMRequest:
        """Build a PlannerLLMRequest for an LLM call.

        Key difference from SKETCH: temperature 0.3 (precision).

        Args:
            messages: Conversation messages list.
            ctx: Stage context with budget information.
            tools: Optional tool definitions for agentic calls.

        Returns:
            PlannerLLMRequest ready for ILLMPort.execute().
        """
        payload: Dict[str, Any] = {
            "messages": messages,
            "temperature": 0.3,
        }
        if tools:
            payload["tools"] = list(tools)

        constraints = PlannerConstraints(
            max_tokens=ctx.stage_budget.max_tokens if ctx.stage_budget else 1024,
            timeout_ms=ctx.stage_budget.timeout_ms if ctx.stage_budget else 5000,
            temperature=0.3,
            consumer_id="planner.expand",
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

        EXPAND routes 4 tools (vs SKETCH's 4 -- different set):
          - discover_capabilities -> router.discover()
          - get_capability_schema -> router.get_schema()
          - find_prompts -> router.find_prompts()
          - query_session_context -> router.read_context()

        Args:
            tool_call: Tool call dict from LLM response.
            request: Current plan request (for session_id, trace_id).
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
                    top_k=args.get("top_k", 5),
                )

            if name == "get_capability_schema":
                return await self._tool_router.get_schema(
                    capability_name=args.get("capability_name", ""),
                    version=args.get("version"),
                )

            if name == "find_prompts":
                return await self._tool_router.find_prompts(
                    intent=args.get("intent", ""),
                    domain=args.get("domain"),
                    top_k=args.get("top_k", 5),
                )

            if name == "query_session_context":
                session_id = ""
                if request.context is not None:
                    session_id = getattr(request.context, "session_id", "")
                return await self._tool_router.read_context(
                    session_id=session_id,
                    sections=args.get("sections", []),
                )

            log.warning("Unknown tool call: %s", name)
            return {"error": f"Unknown tool: {name}"}

        except Exception as exc:
            log.warning("Tool call %s failed: %s", name, exc)
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_response(self, content: str) -> Dict[str, Any]:
        """Parse LLM JSON output into a validated dict.

        Validates:
          - Valid JSON
          - steps array non-empty
                    - Each step has an id of 's' followed by digits, capability
                        (non-empty), params (object)
          - dependencies map present
          - rationale non-empty

        Args:
            content: Raw LLM output string.

        Returns:
            Parsed data dict with 'steps', 'dependencies', 'rationale'.

        Raises:
            ExpandFailedError: If content is invalid.
        """
        text = content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ExpandFailedError(
                f"LLM output is not valid JSON: {exc}",
                stage="EXPAND",
            ) from exc

        if not isinstance(data, dict):
            raise ExpandFailedError(
                "LLM output must be a JSON object",
                stage="EXPAND",
            )

        raw_steps = data.get("steps", [])
        if not raw_steps:
            raise ExpandFailedError(
                "LLM output missing or empty steps",
                stage="EXPAND",
            )

        for i, step in enumerate(raw_steps):
            step_id = step.get("id", "")
            if not _is_step_id(step_id):
                raise ExpandFailedError(
                    f"Step {i} has invalid id '{step_id}' (must be s followed by digits)",
                    stage="EXPAND",
                )
            cap = step.get("capability", "")
            if not cap:
                raise ExpandFailedError(
                    f"Step '{step_id}' missing capability",
                    stage="EXPAND",
                )
            params = step.get("params")
            if not isinstance(params, dict):
                raise ExpandFailedError(
                    f"Step '{step_id}' params must be an object",
                    stage="EXPAND",
                )

        rationale = data.get("rationale", "")
        if not rationale:
            raise ExpandFailedError(
                "LLM output missing rationale",
                stage="EXPAND",
            )

        # Ensure dependencies key exists.
        if "dependencies" not in data:
            data["dependencies"] = {}

        return data

    # ------------------------------------------------------------------
    # Post-LLM enrichment
    # ------------------------------------------------------------------

    def _enrich_steps(
        self,
        llm_steps: List[Dict[str, Any]],
        accumulated_results: Dict[str, Any],
    ) -> List[PlanStep]:
        """Enrich LLM steps with infrastructure fields from contract evidence.

        The LLM produces 8 fields. This method fills infrastructure
        fields from CapabilityContract metadata discovered during the
        agentic loop and validates prompt_template against discovered
        prompts or the prompt inventory.

        Args:
            llm_steps: Parsed step dicts from the LLM.
            accumulated_results: Tool call results keyed by tool name.

        Returns:
            List of fully populated PlanStep objects.
        """
        # Build a contract lookup from accumulated tool results.
        contracts = self._build_contract_lookup(accumulated_results)
        prompt_descriptors = _prompt_descriptors_from_results(
            accumulated_results.get("prompts", [])
        )
        discovered_prompt_items = [
            {
                "name": descriptor.name,
                "domain": list(descriptor.domains),
                "activity_profile": descriptor.activity_profile,
                "compatible_agents": list(descriptor.compatible_agents),
                "compatible_tools": list(descriptor.compatible_tools),
                "score": descriptor.score,
            }
            for descriptor in prompt_descriptors
        ]
        prompt_descriptors_by_name: Dict[str, _PromptDescriptor] = {
            descriptor.name: descriptor for descriptor in prompt_descriptors if descriptor.name
        }

        enriched: List[PlanStep] = []
        for step_dict in llm_steps:
            cap_name = step_dict.get("capability", "")
            contract = contracts.get(cap_name)

            # Infrastructure fields from contract metadata.
            has_side_effects = False
            compensation: Optional[str] = None
            timeout_ms = _DEFAULT_TIMEOUT_MS
            required_context: Optional[List[str]] = None
            safety_band_min: Optional[str] = None
            activity_profile: Optional[str] = None

            if contract is not None:
                has_side_effects = bool(getattr(contract, "has_side_effects", False))
                compensation = getattr(contract, "compensation", None)
                avg_latency = getattr(contract, "avg_latency_ms", 0)
                if avg_latency and avg_latency > 0:
                    timeout_ms = avg_latency * 2
                rc = getattr(contract, "required_context", None)
                if rc:
                    required_context = list(rc)
                safety_band_min = getattr(contract, "safety_band_min", None)
                activity_profile = _clean_optional_str(getattr(contract, "activity_profile", None))

            prompt_binding = validate_prompt_binding(
                requested_template=step_dict.get("prompt_template"),
                capability_name=cap_name,
                discovered_prompts=discovered_prompt_items,
                prompt_inventory=set(self._prompt_inventory.keys()),
            )
            if prompt_binding.state == "cleared":
                log.warning(
                    "EXPAND prompt binding %s: step=%s capability=%s requested=%r resolved=%r reason=%s",
                    prompt_binding.state,
                    step_dict.get("id", ""),
                    cap_name,
                    step_dict.get("prompt_template"),
                    prompt_binding.resolved_name,
                    prompt_binding.reason,
                )

            if activity_profile is None and prompt_binding.resolved_name is not None:
                descriptor = prompt_descriptors_by_name.get(
                    prompt_binding.resolved_name,
                ) or self._prompt_inventory.get(prompt_binding.resolved_name)
                if descriptor is not None:
                    activity_profile = descriptor.activity_profile

            # Meta-agent: build_agent always has side effects.
            if cap_name == "tool.meta.build_agent":
                has_side_effects = True

            # Output schema: use LLM value, fallback to contract.
            output_schema = step_dict.get("output_schema")
            if output_schema is None and contract is not None:
                contract_output = getattr(contract, "output", None)
                if contract_output:
                    output_schema = contract_output

            plan_step = PlanStep(
                id=step_dict["id"],
                capability=cap_name,
                params=step_dict.get("params", {}),
                deps=step_dict.get("deps", []),
                prompt_template=prompt_binding.resolved_name,
                tools_granted=step_dict.get("tools_granted"),
                output_schema=output_schema,
                condition=None,  # V1: always None
                is_optional=step_dict.get("is_optional", False),
                has_side_effects=has_side_effects,
                compensation=compensation,
                timeout_ms=timeout_ms,
                required_context=required_context,
                safety_band_min=safety_band_min,
                activity_profile=activity_profile,
            )
            log.debug(
                "EXPAND step=%s capability=%s prompt_template=%r activity_profile=%r",
                plan_step.id,
                plan_step.capability,
                plan_step.prompt_template,
                plan_step.activity_profile,
            )
            enriched.append(plan_step)

        return enriched

    def _build_contract_lookup(
        self,
        accumulated_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build capability_name -> contract mapping from tool results.

        Extracts contracts from discover_capabilities and
        get_capability_schema results accumulated during the agentic
        loop.

        Args:
            accumulated_results: Dict with 'discover' and 'schema' keys
                containing lists of tool call results.

        Returns:
            Dict mapping capability name to contract object.
        """
        contracts: Dict[str, Any] = {}

        # From discover_capabilities results (RetrievalResult.capabilities).
        for result in accumulated_results.get("discover", []):
            if result is None:
                continue
            caps = getattr(result, "capabilities", None)
            if caps:
                for sc in caps:
                    contract = getattr(sc, "contract", None)
                    if contract is not None:
                        name = getattr(contract, "name", "")
                        if name:
                            contracts[name] = contract

        # From get_capability_schema results (direct contract).
        for result in accumulated_results.get("schema", []):
            if result is None:
                continue
            # get_schema returns the contract directly.
            name = getattr(result, "name", "")
            if name:
                contracts[name] = result

        return contracts

    # ------------------------------------------------------------------
    # Degraded plan construction (fallback)
    # ------------------------------------------------------------------

    def _build_degraded_plan(
        self,
        sketch_result: SketchResult,
    ) -> ExpandedPlan:
        """Convert SKETCH output to minimal PlanSteps (Section 7.6.3).

        Used as a last-resort fallback when both EXPAND attempts fail.
        Produces minimal steps that proceed to VALIDATE (pipeline
        continues rather than dying).

        Args:
            sketch_result: The SKETCH output to degrade from.

        Returns:
            ExpandedPlan with minimal PlanStep objects.
        """
        steps: List[PlanStep] = []
        dependencies: Dict[str, List[str]] = {}

        for i, rough in enumerate(sketch_result.rough_steps):
            step_id = f"s{i + 1}"
            steps.append(
                PlanStep(
                    id=step_id,
                    capability=rough.suggested_capability or "UNRESOLVED",
                    params={},
                    timeout_ms=_DEFAULT_TIMEOUT_MS,
                )
            )
            # Convert depends_on indices to step IDs if possible.
            if rough.depends_on:
                dep_ids: List[str] = []
                for dep_intent in rough.depends_on:
                    # depends_on contains intents (resolved in SKETCH).
                    # Find matching step index by intent string.
                    for j, other in enumerate(sketch_result.rough_steps):
                        if other.intent == dep_intent and j < i:
                            dep_ids.append(f"s{j + 1}")
                            break
                if dep_ids:
                    dependencies[step_id] = dep_ids

        return ExpandedPlan(
            steps=steps,
            dependencies=dependencies,
            tool_mappings={s.id: s.capability for s in steps},
            rationale=f"Degraded plan from SKETCH (EXPAND fallback): {sketch_result.rationale}",
        )

    # ------------------------------------------------------------------
    # Agentic loop -- core of the EXPAND stage
    # ------------------------------------------------------------------

    async def _run_agentic_loop(
        self,
        messages: List[Dict[str, Any]],
        request: PlanRequest,
        ctx: StageContext,
        *,
        use_tools: bool = True,
    ) -> Tuple[str, Dict[str, Any]]:
        """Run the agentic tool-calling loop with the LLM.

        Same pattern as SKETCH (Section 6.2.3) but with EXPAND tools.

        Args:
            messages: Initial message list (system + user).
            request: The plan request (for tool dispatch context).
            ctx: Stage context.
            use_tools: Whether to provide tool definitions.

        Returns:
            Tuple of (final_content, accumulated_results).
            accumulated_results has keys: 'discover', 'schema',
            'prompts', 'context'.

        Raises:
            ExpandFailedError: If the LLM never produces a final
                answer within the round limit.
        """
        tools = self._get_tool_definitions() if use_tools else None
        accumulated: Dict[str, Any] = {
            "discover": [],
            "schema": [],
            "prompts": [],
            "context": [],
        }

        for round_num in range(_MAX_TOOL_ROUNDS):
            if ctx.cancel_check():
                raise ExpandFailedError(
                    "Plan cancelled during EXPAND",
                    stage="EXPAND",
                    request_id=ctx.request_id,
                    trace_id=ctx.trace_id,
                )

            hub_request = self._build_hub_request(messages, ctx, tools=tools)
            hub_response: PlannerLLMResponse = await self._llm_port.execute(hub_request)

            result = hub_response.result if hub_response.result else {}
            content = result.get("content", "")
            tool_calls = result.get("tool_calls", [])

            if not tool_calls:
                if not content:
                    raise ExpandFailedError(
                        "LLM returned empty response with no tool calls",
                        stage="EXPAND",
                        request_id=ctx.request_id,
                        trace_id=ctx.trace_id,
                    )
                return content, accumulated

            # LLM wants to call tools.
            messages.append(
                {
                    "role": "assistant",
                    "content": content or "",
                    "tool_calls": tool_calls,
                }
            )

            for tc in tool_calls:
                tc_result = await self._dispatch_tool_call(tc, request, ctx)

                # Track results by tool type.
                func_name = tc.get("function", {}).get("name", "")
                if func_name == "discover_capabilities":
                    accumulated["discover"].append(tc_result)
                elif func_name == "get_capability_schema":
                    accumulated["schema"].append(tc_result)
                elif func_name == "find_prompts":
                    accumulated["prompts"].append(tc_result)
                elif func_name == "query_session_context":
                    accumulated["context"].append(tc_result)

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
                "EXPAND agentic round %d: %d tool calls dispatched",
                round_num + 1,
                len(tool_calls),
            )

        raise ExpandFailedError(
            f"LLM did not produce a plan after {_MAX_TOOL_ROUNDS} tool-calling rounds",
            stage="EXPAND",
            request_id=ctx.request_id,
            trace_id=ctx.trace_id,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def execute(
        self,
        sketch_result: SketchResult,
        request: PlanRequest,
        ctx: StageContext,
        arbiter_feedback: Optional[List[str]] = None,
    ) -> ExpandedPlan:
        """Run the full EXPAND stage pipeline (Section 7).

        Orchestrates the complete Stage 2 flow:
          1. First attempt: agentic loop + parse + enrich
          2. On ExpandFailedError: retry simplified (no tools)
          3. On second failure: fallback to degraded plan from SKETCH

        Args:
            sketch_result: Output from SKETCH stage.
            request: The plan request from Orchestrator.
            ctx: Stage context with trace_id, budget, cancel_check.
            arbiter_feedback: Optional revision suggestions from VALIDATE.

        Returns:
            ExpandedPlan with fully parameterised PlanStep objects.
        """
        log.info(
            "EXPAND execute: request_id=%s, steps=%d",
            request.request_id,
            len(sketch_result.rough_steps),
        )

        try:
            return await self._execute_attempt(
                sketch_result,
                request,
                ctx,
                arbiter_feedback=arbiter_feedback,
            )
        except ExpandFailedError:
            log.warning(
                "EXPAND first attempt failed for request_id=%s, retrying simplified",
                request.request_id,
            )
            try:
                return await self._execute_attempt(
                    sketch_result,
                    request,
                    ctx,
                    simplified=True,
                )
            except ExpandFailedError:
                log.warning(
                    "EXPAND retry failed for request_id=%s, falling back to degraded plan",
                    request.request_id,
                )
                return self._build_degraded_plan(sketch_result)

    async def _execute_attempt(
        self,
        sketch_result: SketchResult,
        request: PlanRequest,
        ctx: StageContext,
        *,
        arbiter_feedback: Optional[List[str]] = None,
        simplified: bool = False,
    ) -> ExpandedPlan:
        """Single execution attempt (used by execute for try/retry).

        Args:
            sketch_result: SKETCH output.
            request: The plan request.
            ctx: Stage context.
            arbiter_feedback: Optional arbiter revision suggestions.
            simplified: If True, skip tools and ask LLM directly.

        Returns:
            ExpandedPlan.

        Raises:
            ExpandFailedError: On any unrecoverable error.
        """
        messages = self._build_initial_messages(
            sketch_result=sketch_result,
            request=request,
            arbiter_feedback=arbiter_feedback,
        )

        if simplified:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Parameterise the rough plan using your best "
                        "judgment. Do not call any tools. Output only JSON."
                    ),
                }
            )

        content, accumulated = await self._run_agentic_loop(
            messages, request, ctx, use_tools=not simplified
        )

        parsed = self._parse_response(content)
        steps = self._enrich_steps(parsed["steps"], accumulated)

        deps = parsed.get("dependencies", {})

        # Remove any circular dependency edges.
        deps = self._remove_cycles(deps)

        return ExpandedPlan(
            steps=steps,
            dependencies=deps,
            tool_mappings={s.id: s.capability for s in steps},
            rationale=parsed["rationale"],
        )

    def _remove_cycles(
        self,
        deps: Dict[str, List[str]],
    ) -> Dict[str, List[str]]:
        """Remove circular dependency edges from the dep graph.

        Uses depth-first search to detect back edges and removes them.
        This is the defensive handling for Section 7.6.2 "invalid deps
        (cycle) -> remove circular edges, flatten to sequential".

        Args:
            deps: step_id -> [predecessor_step_ids].

        Returns:
            Cleaned dependency map with no cycles.
        """
        # Build adjacency (step -> successors based on deps).
        # deps[X] = [A, B] means X depends on A, B (A -> X, B -> X).
        # For cycle detection, we walk forward edges: A -> X.
        all_steps = set(deps.keys())
        for preds in deps.values():
            all_steps.update(preds)

        # Build successor map.
        successors: Dict[str, List[str]] = {s: [] for s in all_steps}
        for step_id, preds in deps.items():
            for pred in preds:
                if pred in successors:
                    successors[pred].append(step_id)

        # DFS to find back edges.
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {s: WHITE for s in all_steps}
        back_edges: List[Tuple[str, str]] = []

        def dfs(node: str) -> None:
            color[node] = GRAY
            for succ in successors.get(node, []):
                if color.get(succ, WHITE) == GRAY:
                    back_edges.append((node, succ))
                elif color.get(succ, WHITE) == WHITE:
                    dfs(succ)
            color[node] = BLACK

        for node in all_steps:
            if color.get(node, WHITE) == WHITE:
                dfs(node)

        if not back_edges:
            return deps

        # Remove back edges from deps.
        log.warning("Removing %d circular dependency edges", len(back_edges))
        cleaned = {k: list(v) for k, v in deps.items()}
        for pred, succ in back_edges:
            if succ in cleaned and pred in cleaned[succ]:
                cleaned[succ].remove(pred)

        return cleaned

    async def micro_execute(
        self,
        micro_sketch_result: SketchResult,
        completed_results: Dict[str, StepResult],
        ctx: StageContext,
    ) -> ExpandedPlan:
        """Run abbreviated micro-EXPAND for micro-replan (Section 10.3.3).

        Simplified EXPAND pipeline for mid-DAG micro-replan:
          - Dedicated micro-replan system prompt (Section 10.3.3)
          - Structured user message: SKETCH_PLAN, COMPLETED_CONTEXT,
            CAPABILITY_SET, DEPENDENCY_RULES
          - No arbiter feedback / revise loop (Section 10.6.2)
          - No fallback to degraded PlanSteps
          - Budget: max_tokens=512, timeout_ms=3000, temp=0.3

        Cross-boundary dependencies (Section 10.3.3):
          Replacement steps CAN depend on completed steps via
          ``deps: ["s1"]`` where s1 already completed.  The
          Orchestrator resolves these from completed_results when
          merging. Inter-step references like
          ``$s1.result.data.field`` may reference completed outputs.

        Args:
            micro_sketch_result: SKETCH output for micro-replan.
            completed_results: Results from already-completed steps.
            ctx: Stage context with micro-replan budget envelope.

        Returns:
            ExpandedPlan for the micro-replanned portion.

        Raises:
            ExpandFailedError: If planning fails (no retry in micro).
        """
        log.info(
            "EXPAND micro_execute: request_id=%s, steps=%d",
            ctx.request_id,
            len(micro_sketch_result.rough_steps),
        )

        # Build a synthetic PlanRequest for tool dispatch.
        plan_request = PlanRequest(
            intent="micro-replan-expand",
            trace_id=ctx.trace_id,
            request_id=ctx.request_id,
        )

        messages = self._build_micro_expand_messages(
            micro_sketch_result,
            completed_results,
            plan_request,
        )

        try:
            content, accumulated = await self._run_agentic_loop(
                messages,
                plan_request,
                ctx,
            )
            parsed = self._parse_response(content)
            steps = self._enrich_steps(parsed["steps"], accumulated)
            deps = self._remove_cycles(
                parsed.get("dependencies", {}),
            )

            return ExpandedPlan(
                steps=steps,
                dependencies=deps,
                tool_mappings={s.id: s.capability for s in steps},
                rationale=parsed["rationale"],
            )
        except ExpandFailedError:
            raise
        except Exception as exc:
            raise ExpandFailedError(
                f"Micro-EXPAND failed: {exc}",
                stage="EXPAND",
                request_id=ctx.request_id,
                trace_id=ctx.trace_id,
            ) from exc

    # ------------------------------------------------------------------
    # Micro-replan prompt construction (Section 10.3.3)
    # ------------------------------------------------------------------

    def _build_micro_expand_messages(
        self,
        micro_sketch_result: SketchResult,
        completed_results: Dict[str, StepResult],
        plan_request: PlanRequest,
    ) -> List[Dict[str, Any]]:
        """Build message list for micro-EXPAND LLM call.

        Produces a micro-replan-specific system prompt and a
        structured user message with 4 sections per Section 10.3.3.

        Args:
            micro_sketch_result: SKETCH output (replacement steps).
            completed_results: Results from completed steps.
            plan_request: Synthetic PlanRequest for context.

        Returns:
            List of message dicts [system, user].
        """
        system_prompt = self._assemble_micro_expand_system_prompt()
        user_content = self._assemble_micro_expand_user_message(
            micro_sketch_result,
            completed_results,
            plan_request,
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

    def _assemble_micro_expand_system_prompt(self) -> str:
        """Build SYSTEM message for micro-EXPAND (Section 10.3.3).

        Key differences from full EXPAND system prompt:
          - Scoped to replacement steps only
          - Explicit cross-boundary dependency rules
          - Completed steps are frozen (PLAN-12)
          - At most 1 discover_capabilities call

        Returns:
            The complete micro-expand system prompt string.
        """
        schema_text = json.dumps(EXPAND_OUTPUT_SCHEMA, indent=2)

        return (
            "You are the MICRO-EXPAND stage planner.\n"
            "\n"
            "A plan was partially executed. You receive a rough plan "
            "of REPLACEMENT STEPS from micro-SKETCH. Your job is to "
            "produce fully parameterised executable steps for the "
            "replacement portion only.\n"
            "\n"
            "YOUR JOB:\n"
            "1. For each replacement step, determine the EXACT "
            "capability to use. Call discover_capabilities or "
            "get_capability_schema to confirm if needed.\n"
            "2. Fill in ALL required parameters. Use completed step "
            "outputs as context for parameter binding.\n"
            "3. Express step dependencies using step IDs.\n"
            "4. Output valid JSON conforming to the schema below.\n"
            "\n"
            "MICRO-REPLAN RULES:\n"
            "- Completed steps are FROZEN (PLAN-12). Do NOT include "
            "them in your output.\n"
            "- Replacement steps MAY depend on completed steps via "
            "deps (cross-boundary dependencies).\n"
            "- Use $<step_id>.result.<field> syntax to reference "
            "completed step outputs in params.\n"
            "- At most 1 discover_capabilities call if replacement "
            "steps need new capabilities.\n"
            "\n"
            "INFRASTRUCTURE FIELDS (filled automatically -- do NOT "
            "set these):\n"
            "- has_side_effects, compensation, timeout_ms, "
            "required_context, safety_band_min, condition\n"
            "\n"
            "YOU set these 8 fields per step:\n"
            "- id (s1, s2, ...), capability, params, deps, "
            "prompt_template, tools_granted, output_schema, "
            "is_optional\n"
            "\n"
            "When ready, respond with ONLY valid JSON conforming "
            "to this schema:\n"
            f"{schema_text}\n"
        )

    def _assemble_micro_expand_user_message(
        self,
        micro_sketch_result: SketchResult,
        completed_results: Dict[str, StepResult],
        plan_request: PlanRequest,
    ) -> str:
        """Build USER message for micro-EXPAND (Section 10.3.3).

        4 structured sections:
          1. SKETCH_PLAN -- replacement steps from micro-SKETCH
          2. COMPLETED_CONTEXT -- outputs from completed steps
          3. CAPABILITY_SET -- candidates from SKETCH discovery
          4. DEPENDENCY_RULES -- cross-boundary dep instructions

        Args:
            micro_sketch_result: The micro-SKETCH result.
            completed_results: Completed step results.
            plan_request: Synthetic PlanRequest.

        Returns:
            Formatted user message string.
        """
        parts: List[str] = []

        # Section 1: SKETCH_PLAN (replacement steps only)
        parts.append("SKETCH_PLAN (replacement steps):")
        for i, step in enumerate(micro_sketch_result.rough_steps):
            cap_hint = (
                f" [capability: {step.suggested_capability}]" if step.suggested_capability else ""
            )
            deps_hint = f" [depends_on: {step.depends_on}]" if step.depends_on else ""
            parts.append(f"  Step {i + 1}: {step.intent}{cap_hint}{deps_hint}")
        parts.append(f"\nSKETCH RATIONALE: {micro_sketch_result.rationale}")

        # Section 2: COMPLETED_CONTEXT
        parts.append("\nCOMPLETED_CONTEXT (available outputs):")
        if completed_results:
            for step_id, step_result in completed_results.items():
                status = getattr(
                    step_result.status,
                    "value",
                    str(step_result.status),
                )
                cap = step_result.capability_name or "unknown"
                line = f"  {step_id} ({cap}): {status}"
                # Include output data keys for param binding.
                result_data = getattr(step_result, "result", None)
                if result_data is not None:
                    data = getattr(result_data, "data", result_data)
                    if isinstance(data, dict):
                        keys = list(data.keys())[:8]
                        line += f" [outputs: {', '.join(keys)}]"
                parts.append(line)
        else:
            parts.append("  (no completed steps)")

        # Section 3: CAPABILITY_SET
        if micro_sketch_result.capability_candidates:
            parts.append("\nCAPABILITY_SET (discovered):")
            for sc in micro_sketch_result.capability_candidates:
                name = getattr(
                    getattr(sc, "contract", None),
                    "name",
                    str(sc),
                )
                desc = getattr(
                    getattr(sc, "contract", None),
                    "description",
                    "",
                )
                score = getattr(sc, "score", 0.0)
                parts.append(f"  - {name} (score={score:.2f}): {desc}")

        # Section 4: DEPENDENCY_RULES
        completed_ids = list(completed_results.keys())
        parts.append("\nDEPENDENCY_RULES:")
        parts.append(
            "  - Replacement steps MAY depend on completed steps: "
            + (", ".join(completed_ids) if completed_ids else "(none)")
        )
        parts.append(
            "  - Use $<step_id>.result.<field> to reference " "completed step outputs in params"
        )
        parts.append("  - Dependencies must form a DAG (no cycles)")

        return "\n".join(parts)
