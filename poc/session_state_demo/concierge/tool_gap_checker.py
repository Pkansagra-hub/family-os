"""
Tool Gap Checker
================

Simple gap detection that ONLY runs when Concierge wants to call a tool.

Logic:
1. Tool has required params
2. Check if those params exist in SessionState (beliefs, referents, persona)
3. Have info? PASS. Missing info? ASK.

That's it. No LLM calls for gap detection. Just simple param checking.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from poc.session_state_demo.bridge import SessionLLMBridge

logger = logging.getLogger(__name__)


# =============================================================================
# TOOL PARAM REQUIREMENTS
# =============================================================================

TOOL_REQUIRED_PARAMS: Dict[str, Dict[str, Any]] = {
    # Sub-agent spawn tool
    "spawn_agent": {
        "required": ["agent_type", "task_type", "params"],
        "param_requirements": {
            "search_accommodations": ["location"],
            "search_restaurants": ["location"],
            "search_activities": ["location"],
            "book_accommodation": ["name", "check_in_date"],
            "book_restaurant": ["restaurant_name", "date", "time", "party_size"],
            "book_spa_service": ["service_type", "date"],
        },
    },
    # Direct tools (legacy - should use spawn_agent)
    "search_accommodations": {
        "required": ["location"],
        "optional": ["check_in_date", "budget", "guests"],
    },
    "search_restaurants": {
        "required": ["location"],
        "optional": ["cuisine", "date", "party_size"],
    },
    "search_activities": {
        "required": ["location"],
        "optional": ["activity_type", "date"],
    },
    "book_accommodation": {
        "required": ["name", "check_in_date"],
        "optional": ["guests", "room_type"],
    },
    "book_restaurant": {
        "required": ["restaurant_name", "date", "time", "party_size"],
        "optional": ["special_requests"],
    },
    "book_spa_service": {
        "required": ["service_type", "date"],
        "optional": ["time", "therapist"],
    },
    # Memory tools - no required params that need checking
    "add_belief": {"required": [], "optional": []},
    "update_persona": {"required": [], "optional": []},
    # Other tools
    "plan_route": {
        "required": ["origin", "destination"],
        "optional": [],
    },
    "send_family_message": {
        "required": ["recipient", "message"],
        "optional": [],
    },
    "create_calendar_event": {
        "required": ["title", "date"],
        "optional": ["time", "duration"],
    },
}

# Maps param names to what to look for in SessionState
PARAM_ALIASES: Dict[str, List[str]] = {
    "location": ["location", "city", "area", "region", "sonoma", "napa", "destination"],
    "check_in_date": ["date", "check_in", "start_date", "when", "saturday", "weekend"],
    "date": ["date", "when", "day", "saturday", "sunday"],
    "party_size": ["guests", "party_size", "people", "two", "2"],
    "guests": ["guests", "party_size", "people", "two", "2"],
    "name": ["hotel", "accommodation", "inn", "resort", "vineyard"],
    "restaurant_name": ["restaurant", "dining"],
    "service_type": ["spa", "massage", "treatment"],
    "recipient": ["emma", "jake", "mike", "family"],
}


@dataclass
class GapCheckResult:
    """Result of checking tool params against SessionState."""

    tool_name: str
    can_proceed: bool  # True = all required params found
    missing_params: List[str]  # Params that are missing
    found_values: Dict[str, Any]  # Values found in SessionState
    question: Optional[str] = None  # Question to ask if missing


class ToolGapChecker:
    """
    Checks if SessionState has required info for a tool call.

    Usage:
        checker = ToolGapChecker(bridge)
        result = checker.check_tool("search_accommodations", {"budget": 500})

        if result.can_proceed:
            # Execute tool with result.found_values merged with provided args
            pass
        else:
            # Ask user: result.question
            pass
    """

    def __init__(self, bridge: Optional["SessionLLMBridge"] = None):
        self._bridge = bridge
        self._session_cache: Dict[str, Any] = {}

    def refresh_session_cache(self) -> None:
        """Refresh cached SessionState data."""
        if not self._bridge:
            return

        self._session_cache = {}

        # Get beliefs
        try:
            beliefs_data = self._bridge.get_section_data("beliefs_active")
            if "error" not in beliefs_data:
                self._session_cache["beliefs"] = beliefs_data.get("beliefs", {})
        except Exception:
            pass

        # Get scoreboard (referents)
        try:
            scoreboard = self._bridge.get_section_data("scoreboard")
            if "error" not in scoreboard:
                self._session_cache["referents"] = scoreboard.get("referents", {})
                self._session_cache["topic"] = scoreboard.get("topic", "")
        except Exception:
            pass

        # Get persona
        try:
            persona = self._bridge.get_section_data("persona")
            if "error" not in persona:
                self._session_cache["persona"] = persona.get("traits", {})
        except Exception:
            pass

    def check_tool(
        self,
        tool_name: str,
        provided_args: Dict[str, Any],
        task_type: Optional[str] = None,
    ) -> GapCheckResult:
        """
        Check if we have all required params for a tool call.

        Args:
            tool_name: Name of the tool to call
            provided_args: Arguments already provided in the tool call
            task_type: For spawn_agent, the specific task type

        Returns:
            GapCheckResult indicating if we can proceed
        """
        self.refresh_session_cache()

        # Get tool requirements
        tool_spec = TOOL_REQUIRED_PARAMS.get(tool_name, {})
        required_params = list(tool_spec.get("required", []))

        # For spawn_agent, also check task-specific requirements
        if tool_name == "spawn_agent" and task_type:
            task_reqs = tool_spec.get("param_requirements", {}).get(task_type, [])
            # These are in the "params" object
            required_params.extend(task_reqs)

        # Check each required param
        missing = []
        found_values: Dict[str, Any] = {}

        for param in required_params:
            # First check if it's in provided_args
            if param in provided_args and provided_args[param]:
                found_values[param] = provided_args[param]
                continue

            # For spawn_agent, check params object
            if tool_name == "spawn_agent" and "params" in provided_args:
                params_obj = provided_args["params"]
                if isinstance(params_obj, dict) and param in params_obj:
                    found_values[param] = params_obj[param]
                    continue

            # Try to find in SessionState
            value = self._find_in_session(param)
            if value:
                found_values[param] = value
                continue

            # Param is missing
            missing.append(param)

        # Generate question if missing
        question = None
        if missing:
            question = self._generate_question(missing)

        return GapCheckResult(
            tool_name=tool_name,
            can_proceed=len(missing) == 0,
            missing_params=missing,
            found_values=found_values,
            question=question,
        )

    def _find_in_session(self, param: str) -> Optional[Any]:
        """Look for a param value in SessionState."""
        aliases = PARAM_ALIASES.get(param, [param])

        # Check beliefs
        beliefs = self._session_cache.get("beliefs", {})
        for subject, predicates in beliefs.items():
            # Check subject
            if any(alias.lower() in subject.lower() for alias in aliases):
                if isinstance(predicates, dict):
                    # Return first value
                    for pred, obj in predicates.items():
                        return obj
                return predicates

            # Check predicates
            if isinstance(predicates, dict):
                for pred, obj in predicates.items():
                    if any(alias.lower() in pred.lower() for alias in aliases):
                        return obj

        # Check referents (scoreboard)
        referents = self._session_cache.get("referents", {})
        for name in referents.keys():
            if any(alias.lower() in name.lower() for alias in aliases):
                return name

        # Check persona traits
        persona = self._session_cache.get("persona", {})
        for trait, value in persona.items():
            if any(alias.lower() in trait.lower() for alias in aliases):
                return value

        return None

    def _generate_question(self, missing_params: List[str]) -> str:
        """Generate a natural question for missing params."""
        questions = {
            "location": "Which location should I search in?",
            "check_in_date": "What date would you like to check in?",
            "date": "What date works for you?",
            "time": "What time would you prefer?",
            "party_size": "How many people will be attending?",
            "guests": "How many guests?",
            "name": "Which accommodation would you like to book?",
            "restaurant_name": "Which restaurant should I book?",
            "service_type": "What type of spa service would you like?",
            "recipient": "Who should I send the message to?",
            "origin": "Where will you be starting from?",
            "destination": "Where would you like to go?",
        }

        # Get questions for missing params
        missing_questions = []
        for param in missing_params:
            q = questions.get(param, f"What {param.replace('_', ' ')}?")
            missing_questions.append(q)

        if len(missing_questions) == 1:
            return missing_questions[0]
        elif len(missing_questions) == 2:
            return f"{missing_questions[0]} And {missing_questions[1].lower()}"
        else:
            return missing_questions[0]  # Just ask first one


def check_tool_gaps(
    bridge: Optional["SessionLLMBridge"],
    tool_name: str,
    tool_args: Dict[str, Any],
) -> GapCheckResult:
    """
    Convenience function to check tool gaps.

    Args:
        bridge: SessionState bridge
        tool_name: Tool to check
        tool_args: Provided arguments

    Returns:
        GapCheckResult
    """
    checker = ToolGapChecker(bridge)

    # For spawn_agent, get task_type
    task_type = None
    if tool_name == "spawn_agent":
        task_type = tool_args.get("task_type")

    return checker.check_tool(tool_name, tool_args, task_type)
