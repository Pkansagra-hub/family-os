"""
Reactive LLM Agent - Two-Stage Tool Calling (OPTIMIZED)
Stage 1: search_specialists(query) → Returns 10 matching specialists
Stage 2: consult_specialist(name) → Routes to specialist

NO ENUM IN EVERY REQUEST - Token efficient!
"""

import asyncio
import json
import logging
from typing import Any, Dict

from config.settings import settings
from contracts.messages import JobRequest, JobResult
from groq import AsyncGroq
from l3_execution.specialist_search import get_specialist_search_engine
from l5_infrastructure.handoff_space import get_handoff_space

logger = logging.getLogger(__name__)


class ReactiveLLMOptimized:
    """
    Two-stage specialist selection:
    1. LLM searches for specialists (gets 10 results, not 300!)
    2. LLM chooses specialist by name

    BENEFIT:
      - No 6KB enum in every request
      - LLM sees filtered results only
      - Token efficient
      - Scales to 1000+ specialists
    """

    def __init__(self, thread_id: str, shared_context: Dict[str, Any]):
        self.thread_id = thread_id
        self.shared_context = shared_context
        self.client = AsyncGroq(api_key=settings.groq_api_key)
        self.handoff = get_handoff_space()
        self.search_engine = get_specialist_search_engine()

        # Subscribe to specialist results
        self.result_queue = self.handoff.subscribe(f"job.result.{thread_id}")

        self.system_prompt = """You are the Reactive Agent in a dual-agent concierge system.

Your role:
1. Analyze user messages and detect when specialist knowledge is needed
2. Search for the right specialist using search_specialists(query)
3. When you find a specialist, consult them using consult_specialist(specialist_name)
4. Wait for specialist results and integrate findings into your response

Two-stage process:
STAGE 1: If you need specialist help, search for them
   Use: search_specialists(query="health related")
   Get: List of 10 matching specialists

STAGE 2: Choose a specialist from results and consult them
   Use: consult_specialist(specialist_name="nutritionist")
   Wait for findings

Then respond naturally to the user with integrated findings."""

    async def process_message(self, user_message: str) -> str:
        """Process user message with two-stage specialist selection"""
        logger.info(f"[ReactiveLLM] Processing: {user_message}")

        self.shared_context["conversation_history"].append(
            {"role": "user", "content": user_message}
        )

        # Call LLM with TWO tools available
        decision = await self._analyze_with_search_and_consult(user_message)

        if decision["needs_specialist"]:
            logger.info(f"[ReactiveLLM] Specialist needed: {decision['specialist_name']}")

            # Trigger specialist
            await self._trigger_specialist(
                specialist_name=decision["specialist_name"], query=decision["query"]
            )

            # Mark waiting
            self.shared_context["reactive_state"] = "waiting_for_specialist"

            # Wait for result
            result = await self._wait_for_result()
            self.shared_context["reactive_state"] = "active"

            # Integrate and respond
            final_response = await self._integrate_result(user_message, result)

            self.shared_context["conversation_history"].append(
                {"role": "assistant", "content": final_response, "source": "reactive"}
            )

            return final_response
        else:
            # No specialist needed
            response = await self._generate_direct_response(user_message)
            self.shared_context["conversation_history"].append(
                {"role": "assistant", "content": response, "source": "reactive"}
            )
            return response

    async def _analyze_with_search_and_consult(self, user_message: str) -> Dict[str, Any]:
        """
        Two-stage LLM interaction:
        1. LLM can call search_specialists(query) → get 10 results
        2. LLM can call consult_specialist(name) → trigger specialist

        NO ENUM SENT - LLM searches and gets filtered results
        """
        # Define TWO tools (NO enum in either!)
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_specialists",
                    "description": "Search for available specialists by domain/query. Returns top 10 matching specialists.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "What kind of specialist? (e.g., 'health', 'nutrition', 'mental', 'fitness')",
                            }
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "consult_specialist",
                    "description": "Consult with a specific specialist (use after search_specialists)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "specialist_name": {
                                "type": "string",
                                "description": "The specialist ID to consult (from search results)",
                            },
                            "query": {
                                "type": "string",
                                "description": "What to ask the specialist",
                            },
                        },
                        "required": ["specialist_name", "query"],
                    },
                },
            },
        ]

        prompt = f"""User: "{user_message}"

Analyze if you need specialist expertise to answer this question effectively.

If specialist knowledge would help:
1. First, search for relevant specialists using search_specialists(query="...")
2. Review the search results
3. Then consult the best specialist using consult_specialist(specialist_name="...", query="...")

Otherwise, respond directly without using tools."""

        try:
            response = await self.client.chat.completions.create(
                model=settings.groq_model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                tools=tools,
                tool_choice="auto",
                temperature=0.3,
                max_tokens=1000,  # Slightly higher for search → consult flow
            )

            # Check if LLM called tools
            if response.choices[0].message.tool_calls:
                tool_calls = response.choices[0].message.tool_calls

                # STAGE 1: Handle search_specialists
                specialist_results = None
                for tool_call in tool_calls:
                    if tool_call.function.name == "search_specialists":
                        args = json.loads(tool_call.function.arguments)
                        query = args.get("query", "")
                        logger.info(
                            f"[ReactiveLLM] ✅ tool.called: search_specialists(query='{query}')"
                        )

                        # Search locally (NO API call!)
                        specialist_results = self.search_engine.search(query, limit=10)
                        logger.info(
                            f"[ReactiveLLM] ✅ search results: {len(specialist_results)} specialists found"
                        )

                        # Show LLM the results
                        logger.info(
                            f"[ReactiveLLM] Results: {[s['id'] for s in specialist_results]}"
                        )

                # STAGE 2: Handle consult_specialist
                for tool_call in tool_calls:
                    if tool_call.function.name == "consult_specialist":
                        args = json.loads(tool_call.function.arguments)
                        specialist_name = args.get("specialist_name", "")
                        query = args.get("query", "")

                        logger.info(
                            f"[ReactiveLLM] ✅ tool.called: consult_specialist(specialist='{specialist_name}')"
                        )

                        # Validate specialist exists
                        if self.search_engine.validate_specialist(specialist_name):
                            logger.info(f"[ReactiveLLM] ✅ specialist validated: {specialist_name}")
                            return {
                                "needs_specialist": True,
                                "specialist_name": specialist_name,
                                "query": query,
                            }
                        else:
                            logger.error(f"[ReactiveLLM] ❌ invalid specialist: {specialist_name}")

                # If we reach here, LLM searched but didn't consult
                return {
                    "needs_specialist": False,
                    "specialist_name": None,
                    "query": None,
                }
            else:
                # No tool calls - LLM responded directly
                logger.info("[ReactiveLLM] Model decided: no specialist needed")
                return {
                    "needs_specialist": False,
                    "specialist_name": None,
                    "query": None,
                }

        except Exception as e:
            logger.error(f"[ReactiveLLM] Error in tool calling: {e}")
            return {
                "needs_specialist": False,
                "specialist_name": None,
                "query": None,
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
        logger.info(f"[ReactiveLLM] Posted job request for {specialist_name}")

    async def _wait_for_result(self, timeout: float = 60.0) -> JobResult:
        """Wait for specialist result"""
        logger.info("[ReactiveLLM] Waiting for specialist result...")

        try:
            result = await asyncio.wait_for(self.result_queue.get(), timeout=timeout)
            logger.info(f"[ReactiveLLM] Received result from {result.specialist_name}")
            return result
        except asyncio.TimeoutError:
            logger.error("[ReactiveLLM] Timeout waiting for specialist")
            return JobResult(
                thread_id=self.thread_id,
                specialist_name="unknown",
                findings="Specialist timed out",
                confidence=0.0,
                sources=[],
            )

    async def _integrate_result(self, original_message: str, result: JobResult) -> str:
        """Integrate specialist findings into response"""
        logger.info(
            f"[ReactiveLLM] ✅ tool.result: specialist={result.specialist_name}, confidence={result.confidence}"
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
            logger.error(f"[ReactiveLLM] Error integrating result: {e}")
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
            logger.error(f"[ReactiveLLM] Error generating response: {e}")
            return "I'm having trouble processing that right now. Could you rephrase?"
