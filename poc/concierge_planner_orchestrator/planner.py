"""
Planner Agent (Agentic Discovery)
====================================

Agent 2 in the pipeline. Uses Google Gemini with multi-turn function
calling to:
  1. DISCOVER available capabilities by calling discover_capabilities
     (this is Fabric Role 1 -- semantic retrieval from the registry)
  2. REASON about which capabilities serve the user's goal
  3. COMMIT a plan DAG by calling commit_plan

The Planner NEVER receives a pre-dumped capability catalog. It discovers
on its own -- just like a real agent would in production where the
registry might hold 100K+ tools.

Architecture contract:
  - Planner has TWO tools: discover_capabilities, commit_plan
  - discover_capabilities is a handler tool (executed locally)
  - commit_plan is a terminal tool (signals end of agentic loop)
  - The LLM calls discover first (possibly multiple times for different
    domains), then uses results to build and commit a plan
  - This is compositional function calling per the Gemini API

The Planner NEVER executes. It only discovers and plans (PLAN-06).
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from poc.session_state_demo.llm_client import SimpleLLMClient

from .types import CommittedPlan, PlanRequest, PlanStep

logger = logging.getLogger(__name__)

# -- System prompt for the Agentic Planner --

PLANNER_SYSTEM_PROMPT = """\
You are a planning engine for a family AI assistant.

You do NOT know what tools are available yet. You must discover them.

Your workflow:
1. DISCOVER -- Call discover_capabilities to find what tools exist.
   Pass a domain (like "WEATHER", "RECIPES", "CALENDAR", "NOTES", "META") and/or
   an intent description. You can call discover multiple times if the
   user's request spans multiple domains.
   The META domain contains agent creation tools like build_agent.

2. REASON -- Look at what you found. Each discovered capability returns a
   "parameters" object that is the EXACT schema. The keys in that object are
   the EXACT parameter names. Parameters marked "required": true MUST appear
   in your step params. Study the schema carefully.

3. COMMIT -- When you have a clear plan, call commit_plan with:
   - A reasoning explanation
   - An ordered list of steps forming a DAG
   - Each step references an EXACT capability name you discovered
   - Each step's "params_json" is a JSON STRING containing the parameters.
     Use the EXACT parameter names from the capability's "parameters" schema.
   - Steps that need output from earlier steps list those as dependencies
   - Independent steps will run in parallel automatically

Plan structure rules:
- Each step gets an ID: s1, s2, s3, etc.
- Use the EXACT capability name from discover results (e.g. "tool.read.recipe_search")
- For "params_json", write a valid JSON string with the parameters:
  Example: if weather_forecast requires "location" (required) and "days" (optional),
  set params_json to: '{"location": "London", "days": 7}'
  Use EXACT keys from the "parameters" schema. Do NOT invent your own keys.
- Steps that need prior results use depends_on: ["s1"]
- Use "$s1.result" style references in params_json when a step needs another step's output

IMPORTANT: Call discover_capabilities FIRST. Do not guess what tools exist.
After discovering, commit your plan. Always fill in params_json with actual values.
"""

# -- Tool declarations --

DISCOVER_TOOL = {
    "name": "discover_capabilities",
    "description": (
        "Search the capability registry to find what tools are available. "
        "Call this FIRST to discover tools before planning. "
        "You can call it multiple times with different domains or intents. "
        "Returns a list of capabilities with their names, descriptions, "
        "required inputs, and optional inputs."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "domain": {
                "type": "string",
                "description": (
                    "Domain to search in (e.g. WEATHER, RECIPES, CALENDAR, "
                    "NOTES, DATE_TIME, GENERAL). Leave empty to search all."
                ),
            },
            "intent": {
                "type": "string",
                "description": (
                    "Natural language description of what you're looking for "
                    "(e.g. 'find recipes', 'check weather forecast'). "
                    "Used for semantic matching."
                ),
            },
        },
    },
}

COMMIT_TOOL = {
    "name": "commit_plan",
    "description": (
        "Commit your finalized execution plan. Call this AFTER you have "
        "discovered capabilities and decided on the plan structure. "
        "The plan must only reference capabilities you actually discovered."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "reasoning": {
                "type": "string",
                "description": "Brief explanation of the plan structure and why this ordering",
            },
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "step_id": {
                            "type": "string",
                            "description": "Unique step ID (s1, s2, ...)",
                        },
                        "capability_name": {
                            "type": "string",
                            "description": "EXACT capability name from discover results",
                        },
                        "params_json": {
                            "type": "string",
                            "description": (
                                "A JSON string containing the parameters for the capability call. "
                                "Use the EXACT parameter names from the capability's 'parameters' "
                                "schema returned by discover. Example: "
                                '{"location": "London", "days": 7}'
                            ),
                        },
                        "depends_on": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of step_ids this step depends on",
                        },
                        "description": {
                            "type": "string",
                            "description": "Human-readable description of what this step does",
                        },
                    },
                    "required": ["step_id", "capability_name", "params_json", "description"],
                },
                "description": "List of plan steps forming a DAG",
            },
        },
        "required": ["reasoning", "steps"],
    },
}

PLANNER_TOOLS = [DISCOVER_TOOL, COMMIT_TOOL]


def _format_discovery_result(capabilities: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Format capability list into a structured result for the LLM.

    This is what discover_capabilities returns to the model via
    function_response so it can reason about what's available.

    Uses a JSON-schema-style "parameters" dict so the LLM sees
    the EXACT param names as keys rather than a list of objects.
    This dramatically reduces param-name hallucination.
    """
    formatted = []
    for cap in capabilities:
        entry: Dict[str, Any] = {
            "name": cap.get("name", "unknown"),
            "description": cap.get("description", ""),
            "domain": cap.get("domain", []),
        }

        # Build a JSON-schema-style parameters dict
        # Keys = exact param names the tool expects
        parameters: Dict[str, Any] = {}

        required = cap.get("required_inputs", [])
        for inp in required:
            param_name = inp.get("name", "")
            if param_name:
                param_entry: Dict[str, Any] = {
                    "type": inp.get("type", "STRING"),
                    "required": True,
                    "description": inp.get("description", ""),
                }
                parameters[param_name] = param_entry

        optional = cap.get("optional_inputs", [])
        for inp in optional:
            param_name = inp.get("name", "")
            if param_name:
                param_entry_opt: Dict[str, Any] = {
                    "type": inp.get("type", "STRING"),
                    "required": False,
                    "description": inp.get("description", ""),
                }
                if "default" in inp:
                    param_entry_opt["default"] = inp["default"]
                if "enum" in inp:
                    param_entry_opt["enum"] = inp["enum"]
                parameters[param_name] = param_entry_opt

        entry["parameters"] = parameters
        formatted.append(entry)

    return {
        "capabilities_found": len(formatted),
        "capabilities": formatted,
    }


class Planner:
    """
    Agent 2: Agentic Plan Architect.

    Uses multi-turn Gemini function calling to:
      1. Call discover_capabilities (one or more times)
      2. Reason about the results
      3. Call commit_plan with a validated DAG

    The Planner owns its own discovery -- no capability pre-loading.
    This is how the architecture says it should work: the Planner
    has discover_capabilities as a tool backed by Fabric Role 1
    (semantic retrieval).
    """

    def __init__(self, llm_client: SimpleLLMClient) -> None:
        self._llm = llm_client
        self._discovery_handler: Optional[Callable[..., Dict[str, Any]]] = None
        # Track all capabilities discovered across calls
        self._discovered_capabilities: List[Dict[str, Any]] = []

    def set_discovery_handler(self, handler: Callable[..., List[Dict[str, Any]]]) -> None:
        """
        Register the discovery handler that backs discover_capabilities.

        The handler receives (domain=..., intent=...) and returns a list
        of capability dicts from the registry.
        """
        self._discovery_handler = handler

    async def build_plan(
        self,
        plan_request: PlanRequest,
        on_tool_call: Optional[Callable[[str, Dict, Any, int], None]] = None,
    ) -> CommittedPlan:
        """
        Build a CommittedPlan using agentic multi-turn discovery.

        The LLM does NOT receive any pre-loaded capabilities. Instead:
          1. LLM calls discover_capabilities(domain=..., intent=...)
          2. We execute discovery and return results
          3. LLM may call discover again for other domains
          4. LLM calls commit_plan with the final plan

        Args:
            plan_request: Contains intent, user input, domains, context.
            on_tool_call: Optional callback for observability display.

        Returns:
            CommittedPlan with validated steps and dependencies.
        """
        logger.info(
            "[Planner] Building plan for intent='%s' (agentic discovery)",
            plan_request.intent,
        )

        self._discovered_capabilities = []

        if not self._discovery_handler:
            logger.error("[Planner] No discovery handler registered")
            return CommittedPlan(
                intent=plan_request.intent,
                steps=[],
                reasoning="No discovery handler -- cannot discover capabilities.",
                trace_id=plan_request.trace_id,
            )

        # Build the discover handler that wraps our discovery function
        def _handle_discover(**kwargs: Any) -> Dict[str, Any]:
            domain = kwargs.get("domain", "")
            intent = kwargs.get("intent", "")
            caps = self._discovery_handler(domain=domain, intent=intent)
            self._discovered_capabilities.extend(caps)
            return _format_discovery_result(caps)

        # Tool handlers: discover is executable, commit_plan is NOT in handlers
        # (missing from handlers = terminal tool in agentic_loop)
        tool_handlers = {
            "discover_capabilities": _handle_discover,
        }

        user_message = (
            f'The user said: "{plan_request.user_input}"\n\n'
            f"Their intent: {plan_request.intent}\n"
            f"Relevant domains: {', '.join(plan_request.domains)}\n\n"
            f"Discover capabilities for these domains, then build a plan."
        )

        # Run the agentic loop -- the LLM will call discover, get results,
        # then call commit_plan which ends the loop
        result = await self._llm.agentic_loop(
            system_prompt=PLANNER_SYSTEM_PROMPT,
            user_message=user_message,
            tools=PLANNER_TOOLS,
            tool_handlers=tool_handlers,
            max_turns=8,
            on_tool_call=on_tool_call,
        )

        # Parse the terminal tool call (commit_plan)
        if result["terminal_tool"] != "commit_plan":
            logger.error(
                "[Planner] Agentic loop ended without commit_plan. " "Terminal: %s, Content: %s",
                result.get("terminal_tool"),
                result.get("content", "")[:300],
            )
            return CommittedPlan(
                intent=plan_request.intent,
                steps=[],
                reasoning="Planner LLM failed to commit a plan.",
                trace_id=plan_request.trace_id,
            )

        args = result["terminal_args"]
        reasoning = str(args.get("reasoning", ""))
        raw_steps = args.get("steps", [])

        # Build valid name set from ALL discovered capabilities
        valid_cap_names = {c["name"] for c in self._discovered_capabilities}

        # Build short-name -> full-name mapping for fuzzy matching
        # LLM sometimes returns "recipe_search" instead of "tool.read.recipe_search"
        short_to_full: Dict[str, str] = {}
        for full_name in valid_cap_names:
            short = full_name.rsplit(".", 1)[-1] if "." in full_name else full_name
            short_to_full[short] = full_name
            short_to_full[full_name] = full_name

        # Convert to PlanStep objects
        steps = self._parse_steps(raw_steps, short_to_full)

        # Validate DAG is acyclic
        if not self._is_acyclic(steps):
            logger.error("[Planner] Plan contains cycles, returning empty plan")
            return CommittedPlan(
                intent=plan_request.intent,
                steps=[],
                reasoning="Plan contained circular dependencies.",
                trace_id=plan_request.trace_id,
            )

        plan = CommittedPlan(
            intent=plan_request.intent,
            steps=steps,
            reasoning=reasoning,
            trace_id=plan_request.trace_id,
        )

        logger.info(
            "[Planner] Plan committed: %d steps, %d discovery calls, reasoning='%s'",
            len(steps),
            len(
                [
                    t
                    for t in result.get("tool_calls_log", [])
                    if t["tool"] == "discover_capabilities"
                ]
            ),
            reasoning[:100],
        )

        return plan

    @staticmethod
    def _parse_steps(
        raw_steps: Any,
        short_to_full: Dict[str, str],
    ) -> List[PlanStep]:
        """Parse raw LLM output steps into validated PlanStep objects."""
        import json as _json

        steps = []
        for raw in raw_steps:
            # Force protobuf MapComposite to dict
            if hasattr(raw, "items"):
                raw = {str(k): v for k, v in raw.items()}
            else:
                raw = dict(raw)

            cap_name = str(raw.get("capability_name", ""))

            # Resolve short names to full canonical names
            resolved_name = short_to_full.get(cap_name)
            if not resolved_name:
                logger.warning(
                    "[Planner] LLM used unknown capability '%s', skipping step",
                    cap_name,
                )
                continue
            cap_name = resolved_name

            # Parse params from JSON string (params_json) to avoid
            # Gemini's nested-object-in-array serialization bug.
            # Falls back to "params" dict if params_json is missing.
            params: Dict[str, Any] = {}
            params_json_str = raw.get("params_json", "")
            if params_json_str and isinstance(params_json_str, str):
                try:
                    parsed = _json.loads(params_json_str)
                    if isinstance(parsed, dict):
                        params = parsed
                    else:
                        logger.warning("[Planner] params_json was not a dict: %s", type(parsed))
                except _json.JSONDecodeError as exc:
                    logger.warning(
                        "[Planner] Failed to parse params_json '%s': %s",
                        params_json_str[:100],
                        exc,
                    )

            # Fallback: try old-style "params" object (in case LLM uses it)
            if not params:
                raw_params = raw.get("params", {})
                if hasattr(raw_params, "items"):
                    params = {
                        str(k): (str(v) if not isinstance(v, (int, float, bool)) else v)
                        for k, v in raw_params.items()
                    }
                elif raw_params:
                    params = dict(raw_params)

            # Force depends_on to plain list of str
            raw_deps = raw.get("depends_on", [])
            depends_on = list(str(d) for d in raw_deps) if raw_deps else []

            step = PlanStep(
                step_id=str(raw.get("step_id", "")),
                capability_name=cap_name,
                params=params,
                depends_on=depends_on,
                description=str(raw.get("description", "")),
            )
            steps.append(step)

        return steps

    @staticmethod
    def _is_acyclic(steps: List[PlanStep]) -> bool:
        """Validate that the step dependency graph is acyclic (Kahn's algorithm)."""
        step_ids = {s.step_id for s in steps}
        in_degree: Dict[str, int] = {s.step_id: 0 for s in steps}
        for s in steps:
            for dep in s.depends_on:
                if dep in step_ids:
                    in_degree[s.step_id] = in_degree.get(s.step_id, 0) + 1

        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        visited = 0
        while queue:
            node = queue.pop(0)
            visited += 1
            for s in steps:
                if node in s.depends_on:
                    in_degree[s.step_id] -= 1
                    if in_degree[s.step_id] == 0:
                        queue.append(s.step_id)

        return visited == len(steps)
