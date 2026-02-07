"""
LLM-Driven Gap Detection
=========================

System prompts and logic for LLM-driven gap detection.
Instead of heuristic pattern matching, the LLM:
1. Understands the user's intent
2. Identifies which tool(s) to call
3. Recognizes when required parameters are missing
4. Generates natural clarification questions

This replaces the heuristic gap_detector.py with LLM intelligence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from poc.session_state_demo.anniversary_demo.tools.registry import ToolRegistry, get_registry

# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

GAP_DETECTION_SYSTEM_PROMPT = """You are an intelligent assistant that helps users accomplish tasks.

IMPORTANT INSTRUCTIONS FOR TOOL USAGE:

1. TOOL CALLING: You have access to tools that can perform actions. When the user asks you to do something, use the appropriate tool.

2. REQUIRED PARAMETERS: Each tool has required parameters. You MUST provide ALL required parameters when calling a tool.

3. GAP DETECTION: If the user's request is missing information needed for a tool's required parameters:
   - DO NOT make up or guess the missing information
   - DO NOT call the tool with incomplete parameters
   - Instead, ask the user for the specific missing information in a natural, conversational way
   - Be specific about what information you need

4. USING CONTEXT: Use any information the user has previously shared in this conversation. For example:
   - If they mentioned a shellfish allergy, include it in restaurant searches
   - If they specified a location, use it for related searches
   - If they gave a budget, respect it in recommendations

5. NATURAL QUESTIONS: When asking for missing information:
   - Be conversational, not robotic
   - Ask about multiple missing items at once if practical
   - Explain why you need the information if not obvious

EXAMPLE GAP DETECTION:

User: "Book a restaurant for Saturday"
WRONG: Call book_restaurant with made-up time
RIGHT: "I'd be happy to book a restaurant! What time works for you, and how many people will be dining?"

User: "Remind me about the meeting"
WRONG: Set a reminder without a time
RIGHT: "I can set that reminder! When is the meeting, or when would you like to be reminded?"
"""

CLARIFICATION_PROMPT_TEMPLATE = """Based on the user's request, I need to call the {tool_name} tool, but I'm missing some required information:

Missing parameters:
{missing_params_formatted}

Generate a natural, conversational question to ask the user for this information. Be specific and helpful.

Guidelines:
- Ask for all missing items in one question if practical
- Be conversational, not robotic
- If appropriate, explain why the information is needed
- Suggest reasonable defaults or examples if helpful

User's original request: "{user_request}"
"""

CONTEXT_AWARE_PROMPT_TEMPLATE = """You are helping with: {task_context}

Previously learned information that may be relevant:
{session_context}

When using tools, remember to:
- Apply any learned preferences (allergies, budget, etc.)
- Reference previously mentioned details
- Build on what the user has already shared
"""


# =============================================================================
# GAP DETECTION LOGIC
# =============================================================================


@dataclass
class GapAnalysis:
    """Result of analyzing gaps in a tool call."""

    tool_name: str
    has_gaps: bool
    missing_params: List[str] = field(default_factory=list)
    param_descriptions: Dict[str, str] = field(default_factory=dict)
    suggested_question: Optional[str] = None
    can_infer_from_context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ClarificationRequest:
    """A request for clarification from the user."""

    tool_name: str
    missing_params: List[str]
    question: str
    original_intent: str
    context: Dict[str, Any] = field(default_factory=dict)


class LLMGapDetector:
    """
    LLM-driven gap detection for tool calls.

    Unlike heuristic pattern matching, this uses:
    1. Tool schemas to know what's required
    2. LLM to generate natural clarification questions
    3. Session context to avoid asking for known info
    """

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        llm_client: Optional[Any] = None,
    ):
        self.registry = registry or get_registry()
        self.llm_client = llm_client
        self._session_context: Dict[str, Any] = {}

    def set_session_context(self, context: Dict[str, Any]) -> None:
        """Set session context for context-aware gap detection."""
        self._session_context = context

    def analyze_tool_call(
        self,
        tool_name: str,
        provided_params: Dict[str, Any],
        user_request: str,
    ) -> GapAnalysis:
        """
        Analyze a tool call for missing required parameters.

        Returns GapAnalysis with:
        - Whether there are gaps
        - What's missing
        - Suggested clarification question
        """
        schema = self.registry.get(tool_name)
        if not schema:
            return GapAnalysis(tool_name=tool_name, has_gaps=False)

        # Find missing required params
        provided_keys = set(provided_params.keys())
        required_keys = schema.required_param_names
        missing = list(required_keys - provided_keys)

        if not missing:
            return GapAnalysis(tool_name=tool_name, has_gaps=False)

        # Get descriptions for missing params
        descriptions = self.registry.get_missing_param_descriptions(tool_name, missing)

        # Check if any can be inferred from session context
        can_infer = self._check_context_inference(tool_name, missing)

        # Generate suggested question
        question = self._generate_clarification_question(
            tool_name, missing, descriptions, user_request
        )

        return GapAnalysis(
            tool_name=tool_name,
            has_gaps=True,
            missing_params=missing,
            param_descriptions=descriptions,
            suggested_question=question,
            can_infer_from_context=can_infer,
        )

    def _check_context_inference(self, tool_name: str, missing: List[str]) -> Dict[str, Any]:
        """Check if any missing params can be inferred from session context."""
        inferred = {}

        # Example inference rules based on session context
        beliefs = self._session_context.get("beliefs", {})
        persona = self._session_context.get("persona", {})

        for param in missing:
            # Party size inference
            if param == "party_size" and "trip_party_size" in beliefs:
                inferred[param] = beliefs["trip_party_size"]

            # Location inference
            if param == "location" and "trip_destination" in beliefs:
                inferred[param] = beliefs["trip_destination"]

            # Dietary restrictions
            if param == "avoid_ingredients":
                allergies = [
                    v
                    for k, v in beliefs.items()
                    if "allergy" in k.lower() or "dietary" in k.lower()
                ]
                if allergies:
                    inferred[param] = allergies

        return inferred

    def _generate_clarification_question(
        self,
        tool_name: str,
        missing: List[str],
        descriptions: Dict[str, str],
        user_request: str,
    ) -> str:
        """
        Generate a natural clarification question.

        If LLM client is available, uses it for natural language.
        Otherwise, uses a template-based approach.
        """
        if self.llm_client and hasattr(self.llm_client, "generate_clarification"):
            # Use LLM for natural question generation
            return self._llm_generate_question(tool_name, missing, descriptions, user_request)

        # Template-based fallback
        return self._template_generate_question(missing, descriptions)

    def _llm_generate_question(
        self,
        tool_name: str,
        missing: List[str],
        descriptions: Dict[str, str],
        user_request: str,
    ) -> str:
        """Use LLM to generate a natural clarification question."""
        # Format missing params for the prompt
        formatted = "\n".join(
            f"- {param}: {descriptions.get(param, 'Required')}" for param in missing
        )

        prompt = CLARIFICATION_PROMPT_TEMPLATE.format(
            tool_name=tool_name,
            missing_params_formatted=formatted,
            user_request=user_request,
        )

        try:
            response = self.llm_client.generate_clarification(prompt)
            return response
        except Exception:
            # Fallback to template
            return self._template_generate_question(missing, descriptions)

    def _template_generate_question(self, missing: List[str], descriptions: Dict[str, str]) -> str:
        """Generate question using templates."""
        if len(missing) == 1:
            param = missing[0]
            desc = descriptions.get(param, param)
            return f"Could you tell me the {desc.lower()}?"

        if len(missing) == 2:
            params = [descriptions.get(p, p).lower() for p in missing]
            return f"I need a couple more details: {params[0]} and {params[1]}?"

        # Multiple missing
        param_list = ", ".join(descriptions.get(p, p).lower() for p in missing[:-1])
        last_param = descriptions.get(missing[-1], missing[-1]).lower()
        return f"I need a few more details: {param_list}, and {last_param}?"

    def create_clarification_request(
        self, analysis: GapAnalysis, user_request: str
    ) -> ClarificationRequest:
        """Create a clarification request from gap analysis."""
        return ClarificationRequest(
            tool_name=analysis.tool_name,
            missing_params=analysis.missing_params,
            question=analysis.suggested_question or "Could you provide more details?",
            original_intent=user_request,
            context={
                "param_descriptions": analysis.param_descriptions,
                "can_infer": analysis.can_infer_from_context,
            },
        )

    def get_system_prompt(self, include_tools: bool = True) -> str:
        """Get the system prompt for gap-aware LLM calls."""
        base_prompt = GAP_DETECTION_SYSTEM_PROMPT

        if include_tools and self.registry:
            tool_summary = self._generate_tool_summary()
            base_prompt += f"\n\nAVAILABLE TOOLS:\n{tool_summary}"

        if self._session_context:
            context_prompt = self._format_session_context()
            base_prompt += f"\n\n{context_prompt}"

        return base_prompt

    def _generate_tool_summary(self) -> str:
        """Generate a summary of available tools for the prompt."""
        lines = []
        for category in self.registry.get_categories():
            tools = self.registry.get_by_category(category)
            lines.append(f"\n{category.upper()}:")
            for tool in tools:
                required = ", ".join(tool.required_param_names)
                lines.append(f"  - {tool.name}: {tool.description}")
                if required:
                    lines.append(f"    Required: {required}")
        return "\n".join(lines)

    def _format_session_context(self) -> str:
        """Format session context for the prompt."""
        context_parts = []

        if "beliefs" in self._session_context:
            beliefs = self._session_context["beliefs"]
            if beliefs:
                formatted = "\n".join(f"  - {k}: {v}" for k, v in beliefs.items())
                context_parts.append(f"Known facts:\n{formatted}")

        if "persona" in self._session_context:
            persona = self._session_context["persona"]
            if persona:
                formatted = "\n".join(f"  - {k}: {v}" for k, v in persona.items())
                context_parts.append(f"User preferences:\n{formatted}")

        if context_parts:
            return "SESSION CONTEXT:\n" + "\n\n".join(context_parts)
        return ""


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def create_gap_detector(
    llm_client: Optional[Any] = None, session_context: Optional[Dict[str, Any]] = None
) -> LLMGapDetector:
    """Create a configured gap detector."""
    detector = LLMGapDetector(llm_client=llm_client)
    if session_context:
        detector.set_session_context(session_context)
    return detector


def get_gap_detection_prompt() -> str:
    """Get the base gap detection system prompt."""
    return GAP_DETECTION_SYSTEM_PROMPT
