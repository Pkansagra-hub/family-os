"""
Concierge Agent (Real LLM)
============================

Agent 1 in the pipeline. Receives user input, uses Google Gemini to:
  1. Classify intent and complexity (LOW/MEDIUM/HIGH)
  2. Extract domains and entities
  3. Route to Fabric direct (LOW) or Orchestrator (MEDIUM/HIGH)
  4. Generate user-facing responses with real tool results

Uses SimpleLLMClient from session_state_demo for Google AI integration.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from poc.session_state_demo.llm_client import SimpleLLMClient

from .types import ComplexityTier, TaskEnvelope

logger = logging.getLogger(__name__)

# -- System prompt for the Concierge classification call --

CLASSIFY_SYSTEM_PROMPT = """\
You are FamilyOS Concierge -- the front door of a family AI assistant.

Analyze what the user needs and classify it by calling classify_request.

Think about:
- How complex is this? One quick lookup? A couple related steps? A multi-domain plan?
- What domains does it touch? (WEATHER, RECIPES, NOTES, CALENDAR, META, GENERAL)
- META domain: creating new agents, agent composition, dynamic agent management
- What's the core intent in a few words?

Complexity guide:
- LOW: Single straightforward action
- MEDIUM: A couple related actions in the same area
- HIGH: Multiple domains or steps that need coordination
- META domain requests are ALWAYS HIGH -- they require planning to extract proper parameters
"""

CLASSIFY_TOOLS = [
    {
        "name": "classify_request",
        "description": "Classify the user's request into complexity tier, domains, and intent.",
        "parameters": {
            "type": "object",
            "properties": {
                "tier": {
                    "type": "string",
                    "enum": ["LOW", "MEDIUM", "HIGH"],
                    "description": "Complexity tier",
                },
                "intent": {
                    "type": "string",
                    "description": "Short intent phrase (e.g., 'get weather and create note')",
                },
                "domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of domains involved (WEATHER, RECIPES, NOTES, CALENDAR, META, GENERAL)",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Brief explanation of why this tier was chosen",
                },
            },
            "required": ["tier", "intent", "domains", "reasoning"],
        },
    }
]

# -- System prompt for the Concierge response synthesis call --

RESPONSE_SYSTEM_PROMPT = """\
You are a warm, helpful family AI assistant called FamilyOS.

You have just executed a plan for the user. The tool results are provided below.
Synthesize a natural, friendly response that:
1. Summarizes what was accomplished
2. Highlights key information from each step
3. Mentions any failures gracefully

Be concise but informative. Use a conversational tone.
"""


class Concierge:
    """
    Agent 1: Conversation conductor.

    Uses real Gemini LLM for:
      - Request classification (intent + complexity + domains)
      - Response synthesis (combining tool results into natural language)

    Routes:
      - LOW: Returns TaskEnvelope for direct Fabric execution
      - MEDIUM/HIGH: Returns TaskEnvelope for Orchestrator
    """

    def __init__(self, llm_client: SimpleLLMClient) -> None:
        self._llm = llm_client

    async def classify(self, user_input: str) -> TaskEnvelope:
        """
        Classify user input using real LLM.

        Calls Gemini with the classify_request tool to determine
        complexity tier, intent, and domains.

        Returns:
            TaskEnvelope ready for routing.
        """
        logger.info("[Concierge] Classifying: %s", user_input[:80])

        response = await self._llm.complete_with_tools(
            system_prompt=CLASSIFY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_input}],
            tools=CLASSIFY_TOOLS,
            force_tool_call=True,
        )

        # Parse the tool call
        tool_calls = response.get("tool_calls", [])
        if tool_calls:
            call = tool_calls[0]
            args = call.get("args", {})
            tier_str = str(args.get("tier", "HIGH"))
            intent = str(args.get("intent", user_input))
            # Gemini returns protobuf types -- force to plain Python list of str
            raw_domains = args.get("domains", ["GENERAL"])
            domains = list(str(d) for d in raw_domains) if raw_domains else ["GENERAL"]
            reasoning = str(args.get("reasoning", ""))

            try:
                tier = ComplexityTier(tier_str)
            except ValueError:
                tier = ComplexityTier.HIGH

            logger.info(
                "[Concierge] Classification: tier=%s intent='%s' domains=%s reason='%s'",
                tier.value,
                intent,
                domains,
                reasoning,
            )
        else:
            # LLM responded with text instead of tool call -- default to HIGH
            logger.warning(
                "[Concierge] LLM did not call classify tool, defaulting to HIGH. Response: %s",
                response.get("content", "")[:200],
            )
            tier = ComplexityTier.HIGH
            intent = user_input
            domains = ["GENERAL"]

        return TaskEnvelope(
            user_input=user_input,
            intent=intent,
            domains=domains,
            tier=tier,
        )

    async def synthesize_response(
        self,
        user_input: str,
        step_results: List[Dict[str, Any]],
    ) -> str:
        """
        Synthesize a user-facing response from DAG execution results.

        Uses real LLM to produce natural language from raw tool outputs.

        Args:
            user_input: Original user request.
            step_results: List of step results with data/errors.

        Returns:
            Natural language response string.
        """
        # Build context of what happened
        results_summary = []
        for sr in step_results:
            status = "SUCCESS" if sr.get("success") else "FAILED"
            results_summary.append(
                f"Step '{sr.get('description', sr.get('capability', 'unknown'))}': "
                f"{status}\n  Data: {json.dumps(sr.get('data', {}), default=str)[:500]}"
            )

        context = f"User asked: {user_input}\n\n" f"Execution results:\n" + "\n\n".join(
            results_summary
        )

        logger.info("[Concierge] Synthesizing response for %d steps", len(step_results))

        response_text = await self._llm.complete(
            system_prompt=RESPONSE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": context}],
        )

        return response_text or "I completed the tasks but couldn't generate a summary."
