"""
Reactive LLM Agent - Owns the user turn, triggers specialists, integrates results
"""

import asyncio
import logging
from typing import Any, Dict

from config.settings import settings
from contracts.messages import JobRequest, JobResult
from groq import AsyncGroq
from l5_infrastructure.handoff_space import get_handoff_space

logger = logging.getLogger(__name__)


class ReactiveLLM:
    """
    Reactive LLM Agent:
    - Owns the user turn
    - Detects when specialist is needed
    - Triggers tool call (posts job request)
    - Waits for specialist result
    - Integrates findings into final response
    """

    def __init__(self, thread_id: str, shared_context: Dict[str, Any]):
        self.thread_id = thread_id
        self.shared_context = shared_context  # Shared with Proactive
        self.client = AsyncGroq(api_key=settings.groq_api_key)
        self.handoff = get_handoff_space()

        # Subscribe to results
        self.result_queue = self.handoff.subscribe(f"job.result.{thread_id}")

        self.system_prompt = """You are the Reactive Agent in a dual-agent concierge system.

Your role:
1. Analyze user messages and detect when specialist knowledge is needed
2. When you need a specialist, use the tool call to request their help
3. Wait for specialist results
4. Integrate specialist findings into a comprehensive response

Available specialists:
- nutritionist: Analyzes dietary patterns, food sensitivities, nutrition advice

When specialist is needed, respond with:
NEED_SPECIALIST: <specialist_name>
QUERY: <what you need to know>

Otherwise, respond naturally to the user.

Context: You have full conversation history and background shared with Proactive agent."""

    async def process_message(self, user_message: str) -> str:
        """
        Process user message:
        1. Determine if specialist needed
        2. If yes, trigger specialist and wait
        3. Integrate result into response
        """
        logger.info(f"[Reactive] Processing: {user_message}")

        # Add to shared context
        self.shared_context["conversation_history"].append(
            {"role": "user", "content": user_message}
        )

        # Ask LLM if specialist is needed
        decision = await self._analyze_need_for_specialist(user_message)

        if decision["needs_specialist"]:
            logger.info(f"[Reactive] Specialist needed: {decision['specialist_name']}")

            # Trigger specialist
            await self._trigger_specialist(
                specialist_name=decision["specialist_name"], query=decision["query"]
            )

            # Mark Reactive as waiting
            self.shared_context["reactive_state"] = "waiting_for_specialist"

            # Wait for result
            result = await self._wait_for_result()

            # Mark Reactive as active again
            self.shared_context["reactive_state"] = "active"

            # Integrate result into response
            final_response = await self._integrate_result(user_message, result)

            # Add to context
            self.shared_context["conversation_history"].append(
                {"role": "assistant", "content": final_response, "source": "reactive"}
            )

            return final_response
        else:
            # Handle without specialist
            response = await self._generate_direct_response(user_message)

            self.shared_context["conversation_history"].append(
                {"role": "assistant", "content": response, "source": "reactive"}
            )

            return response

    async def _analyze_need_for_specialist(self, message: str) -> Dict[str, Any]:
        """
        Use LLM tool calling to determine if specialist is needed.
        Returns dict with needs_specialist, specialist_name, query
        """
        # Get available specialists from config (supports 300+ dynamically)
        available_specialists = await self._get_available_specialists()

        # Define available tools for the model with DYNAMIC enum
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "consult_specialist",
                    "description": "Consult with a domain specialist to get expert analysis",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "specialist_name": {
                                "type": "string",
                                "enum": available_specialists,  # DYNAMIC LIST
                                "description": "The specialist to consult",
                            },
                            "query": {
                                "type": "string",
                                "description": "The question or topic for the specialist",
                            },
                        },
                        "required": ["specialist_name", "query"],
                    },
                },
            }
        ]

        prompt = f"""User: "{message}"

Analyze if you need specialist expertise to answer this question effectively.

If specialist knowledge would help, use the consult_specialist tool.
Otherwise, respond directly without using the tool."""

        try:
            response = await self.client.chat.completions.create(
                model=settings.groq_model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                tools=tools,
                tool_choice="auto",  # Let model decide if tool is needed
                temperature=0.3,
                max_tokens=500,
            )

            # Check if model called a tool
            if response.choices[0].message.tool_calls:
                tool_call = response.choices[0].message.tool_calls[0]
                logger.info(f"[Reactive] ✅ tool.called: {tool_call.function.name}")

                # Parse tool arguments
                import json

                args = json.loads(tool_call.function.arguments)
                logger.info(
                    f"[Reactive] Tool args: specialist={args.get('specialist_name')}, query={args.get('query')[:50]}..."
                )

                return {
                    "needs_specialist": True,
                    "specialist_name": args.get("specialist_name", "nutritionist"),
                    "query": args.get("query", ""),
                    "tool_call_id": tool_call.id,
                }
            else:
                # Model responded without tool
                logger.info("[Reactive] Model decided: no specialist needed (direct response)")
                return {
                    "needs_specialist": False,
                    "specialist_name": None,
                    "query": None,
                    "tool_call_id": None,
                }

        except Exception as e:
            logger.error(f"[Reactive] Error in tool calling: {e}")
            return {
                "needs_specialist": False,
                "specialist_name": None,
                "query": None,
                "tool_call_id": None,
            }

    async def _trigger_specialist(self, specialist_name: str, query: str):
        """Post job request to handoff space"""
        job_request = JobRequest(
            thread_id=self.thread_id,
            specialist_name=specialist_name,
            query=query,
            context=self.shared_context.copy(),
        )

        await self.handoff.publish(f"job.request.{self.thread_id}", job_request)

        logger.info(f"[Reactive] Posted job request for {specialist_name}")

    async def _wait_for_result(self, timeout: float = 60.0) -> JobResult:
        """Wait for specialist result"""
        logger.info("[Reactive] Waiting for specialist result...")

        try:
            result = await asyncio.wait_for(self.result_queue.get(), timeout=timeout)
            logger.info(f"[Reactive] Received result from {result.specialist_name}")
            return result
        except asyncio.TimeoutError:
            logger.error("[Reactive] Timeout waiting for specialist")
            # Return dummy result
            return JobResult(
                thread_id=self.thread_id,
                specialist_name="unknown",
                findings="Specialist timed out",
                confidence=0.0,
                sources=[],
            )

    async def _integrate_result(self, original_message: str, result: JobResult) -> str:
        """Integrate specialist findings into final response"""

        # Log tool result
        logger.info(
            f"[Reactive] ✅ tool.result: specialist={result.specialist_name}, confidence={result.confidence}, sources={result.sources}"
        )

        prompt = f"""Original user message: "{original_message}"

The {result.specialist_name} specialist has analyzed this and found:

{result.findings}

Confidence: {result.confidence}
Sources: {', '.join(result.sources)}

Now craft a comprehensive, empathetic response to the user that:
1. Addresses their original concern
2. Incorporates the specialist's findings naturally
3. Provides actionable next steps
4. Maintains a conversational, caring tone

Response:"""

        try:
            response = await self.client.chat.completions.create(
                model=settings.groq_model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=500,
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"[Reactive] Error integrating result: {e}")
            return f"Based on the analysis: {result.findings}"

    async def _generate_direct_response(self, message: str) -> str:
        """Generate direct response without specialist"""

        try:
            response = await self.client.chat.completions.create(
                model=settings.groq_model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": message},
                ],
                temperature=0.7,
                max_tokens=300,
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"[Reactive] Error generating response: {e}")
            return "I'm having trouble processing that right now. Could you rephrase?"

    async def _get_available_specialists(self) -> list:
        """
        Load available specialists from config.
        Supports 300+ specialists without prompt overhead.

        Returns: List of specialist names for tool enum
        """
        # Option 1: Load from JSON config file (simplest)
        import os

        config_path = os.path.join(os.path.dirname(__file__), "../../config/specialists.json")

        if os.path.exists(config_path):
            import json

            with open(config_path, "r") as f:
                config = json.load(f)
                specialists = [s.get("id") for s in config.get("specialists", [])]
                logger.info(f"[Reactive] Loaded {len(specialists)} specialists from config")
                return specialists
        else:
            # Fallback: hardcoded list (for now)
            logger.warning("[Reactive] specialists.json not found, using fallback list")
            return ["nutritionist", "sleep_coach", "financial_advisor"]
