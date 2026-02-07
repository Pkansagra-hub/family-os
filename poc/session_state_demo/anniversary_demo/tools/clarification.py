"""
Clarification Generator
========================

Generates natural clarification questions when tool calls have missing parameters.
Uses real LLM calls to create conversational questions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from poc.session_state_demo.anniversary_demo.tools.gap_detection import GapAnalysis, LLMGapDetector


@dataclass
class ClarificationResult:
    """Result of generating a clarification."""

    question: str
    tool_name: str
    missing_params: List[str]
    param_hints: Dict[str, str] = field(default_factory=dict)
    follow_up_context: Dict[str, Any] = field(default_factory=dict)


CLARIFICATION_EXAMPLES = """
Examples of good clarification questions:

For booking a restaurant:
- "I'd be happy to book that! What time works for Saturday, and how many will be dining?"
- "Great choice! Should I book for 2 people? And what time - around 7pm?"

For scheduling:
- "I can set that reminder! When would you like to be reminded - the morning of the meeting?"
- "Sure! What day and time is the meeting?"

For travel planning:
- "I'll look into that! Are you driving from home, or coming from somewhere else?"
- "What dates are you thinking for the trip?"

For family messages:
- "I can send that message to Emma! What should I include - emergency contacts, Jake's schedule?"
"""


class ClarificationGenerator:
    """
    Generates natural clarification questions using LLM.

    Features:
    - Uses real LLM for natural language generation
    - Context-aware (uses session history)
    - Combines multiple missing params into single question
    - Provides hints and examples when helpful
    """

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        gap_detector: Optional[LLMGapDetector] = None,
    ):
        self.llm_client = llm_client
        self.gap_detector = gap_detector or LLMGapDetector()
        self._session_context: Dict[str, Any] = {}

    def set_session_context(self, context: Dict[str, Any]) -> None:
        """Set session context for context-aware clarification."""
        self._session_context = context
        self.gap_detector.set_session_context(context)

    async def generate_clarification(
        self,
        tool_name: str,
        missing_params: List[str],
        param_descriptions: Dict[str, str],
        user_request: str,
    ) -> ClarificationResult:
        """
        Generate a natural clarification question for missing parameters.

        Uses LLM if available, otherwise falls back to templates.
        """
        if self.llm_client:
            question = await self._llm_generate(
                tool_name, missing_params, param_descriptions, user_request
            )
        else:
            question = self._template_generate(
                tool_name, missing_params, param_descriptions, user_request
            )

        # Generate hints for each missing param
        hints = self._generate_param_hints(tool_name, missing_params)

        return ClarificationResult(
            question=question,
            tool_name=tool_name,
            missing_params=missing_params,
            param_hints=hints,
            follow_up_context={
                "original_request": user_request,
                "tool_name": tool_name,
                "pending_params": missing_params,
            },
        )

    async def _llm_generate(
        self,
        tool_name: str,
        missing_params: List[str],
        param_descriptions: Dict[str, str],
        user_request: str,
    ) -> str:
        """Generate clarification using real LLM call."""
        import asyncio

        prompt = f"""The user said: "{user_request}"

I want to help by calling the {tool_name} tool, but I'm missing these required parameters:
"""
        for p in missing_params:
            prompt += f"- {p}: {param_descriptions.get(p, 'required')}\n"

        prompt += f"""
Generate a single, natural, conversational question to ask for this information.
- Be friendly and helpful
- Combine all missing items into one question if practical
- Suggest reasonable defaults or examples if appropriate
- Don't be robotic or list-like

{CLARIFICATION_EXAMPLES}

Your clarification question:"""

        try:
            # Use async LLM call
            if hasattr(self.llm_client, "complete_async"):
                response = await self.llm_client.complete_async(
                    system_prompt="You are a helpful assistant generating clarification questions.",
                    messages=[{"role": "user", "content": prompt}],
                )
            elif hasattr(self.llm_client, "complete"):
                # Sync fallback
                response = await asyncio.to_thread(
                    self.llm_client.complete,
                    system_prompt="You are a helpful assistant generating clarification questions.",
                    messages=[{"role": "user", "content": prompt}],
                )
            else:
                return self._template_generate(
                    tool_name, missing_params, param_descriptions, user_request
                )

            return response.get("content", "").strip()

        except Exception as e:
            # Fallback to template
            print(f"LLM clarification failed: {e}")
            return self._template_generate(
                tool_name, missing_params, param_descriptions, user_request
            )

    def _template_generate(
        self,
        tool_name: str,
        missing_params: List[str],
        param_descriptions: Dict[str, str],
        user_request: str,
    ) -> str:
        """Generate clarification using templates (fallback)."""
        # Tool-specific templates
        templates = {
            "book_restaurant": {
                1: "I'd love to book that! Could you tell me the {param}?",
                2: "Great choice! I just need the {p1} and {p2} to complete the reservation.",
                3: "I can book that! I need a few details: {p1}, {p2}, and {p3}?",
            },
            "book_accommodation": {
                1: "Perfect! What's the {param}?",
                2: "I'll book that for you! Just need the {p1} and {p2}.",
                3: "Let me book that! I need: {p1}, {p2}, and {p3}?",
            },
            "send_family_message": {
                1: "I can send that! What {param} should I include?",
                2: "Sure! What should I include for {p1} and {p2}?",
                3: "I'll send that message! What should I include?",
            },
            "schedule_reminder": {
                1: "I'll set that reminder! {param}?",
                2: "Sure! When should I remind you, and {p2}?",
            },
            "plan_route": {
                1: "I can plan that route! What's the {param}?",
                2: "I'll map that out! Where are you {p1}, and {p2}?",
            },
        }

        # Get descriptions as readable text
        readable = [param_descriptions.get(p, p).lower() for p in missing_params]

        # Try tool-specific template
        if tool_name in templates:
            tool_templates = templates[tool_name]
            count = min(len(missing_params), max(tool_templates.keys()))

            if count in tool_templates:
                template = tool_templates[count]
                if count == 1:
                    return template.format(param=readable[0])
                elif count == 2:
                    return template.format(p1=readable[0], p2=readable[1])
                elif count == 3:
                    return template.format(p1=readable[0], p2=readable[1], p3=readable[2])

        # Generic fallback
        if len(missing_params) == 1:
            return f"Could you tell me the {readable[0]}?"
        elif len(missing_params) == 2:
            return f"I need the {readable[0]} and {readable[1]} to proceed."
        else:
            param_list = ", ".join(readable[:-1])
            return f"I need a few more details: {param_list}, and {readable[-1]}?"

    def _generate_param_hints(self, tool_name: str, missing_params: List[str]) -> Dict[str, str]:
        """Generate helpful hints for each missing parameter."""
        hints = {}

        # Common hints by parameter name
        common_hints = {
            "date": "e.g., 'next Saturday', 'February 15th'",
            "time": "e.g., '7pm', '19:00'",
            "party_size": "number of people",
            "location": "city, address, or place name",
            "check_in_date": "e.g., 'next Saturday', 'Feb 15'",
            "nights": "how many nights to stay",
            "message": "what to include in the message",
            "content": "the message content",
            "datetime": "e.g., 'Friday at 5pm', 'tomorrow morning'",
        }

        for param in missing_params:
            if param in common_hints:
                hints[param] = common_hints[param]

        return hints

    def generate_sync(
        self,
        tool_name: str,
        missing_params: List[str],
        param_descriptions: Dict[str, str],
        user_request: str,
    ) -> ClarificationResult:
        """Synchronous wrapper for generate_clarification."""
        import asyncio

        return asyncio.run(
            self.generate_clarification(tool_name, missing_params, param_descriptions, user_request)
        )

    def from_gap_analysis(self, analysis: GapAnalysis, user_request: str) -> ClarificationResult:
        """Generate clarification from a GapAnalysis result."""
        if not analysis.has_gaps:
            return ClarificationResult(
                question="",
                tool_name=analysis.tool_name,
                missing_params=[],
            )

        return self.generate_sync(
            tool_name=analysis.tool_name,
            missing_params=analysis.missing_params,
            param_descriptions=analysis.param_descriptions,
            user_request=user_request,
        )


def create_clarification_generator(
    llm_client: Optional[Any] = None,
) -> ClarificationGenerator:
    """Create a configured clarification generator."""
    return ClarificationGenerator(llm_client=llm_client)
