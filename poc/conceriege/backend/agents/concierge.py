"""
ConciergeAgent - Main Orchestrator for Reactive-Proactive Loop

Orchestrates the complete user interaction flow:
1. Receives user message
2. Runs ReactiveHandler for immediate intent/emotion/empathy response
3. Spawns specialist agent (nutritionist, psychiatrist, planner)
4. During specialist work (>300ms):
   - Generates proactive prompts (fill_gap, future_action, clarify)
   - Emits proactive events via SSE
5. Waits for specialist analysis
6. Synthesizes reactive + specialist insights + proactive context
7. Returns complete response

This implements:
- Reactive Layer (immediate response)
- Proactive Layer (during background work)
- Specialist Layer (domain analysis)
- Synthesis Layer (combining all)

Research basis:
- Mixed-Initiative Dialogue (Horvitz 1999) - Agent-initiated interactions
- Information Gap (Groenendijk & Stokhof 1984) - What user hasn't told us
- SEDA Architecture (Welsh 2001) - Staged async processing
"""

import asyncio
from typing import Optional

from backend.agents.base import BaseAgent
from backend.agents.nutritionist import NutritionistAgent
from backend.agents.planner import PlannerAgent
from backend.agents.proactive_generator import ProactiveGenerator
from backend.agents.psychiatrist import PsychiatristAgent
from backend.agents.reactive_handler import ReactiveHandler
from backend.agents.synthesis_engine import SynthesisEngine
from backend.models.analysis_result import AnalysisResult
from backend.models.conversation_state import ConversationState
from backend.models.intent import Intent
from backend.models.proactive_prompt import ProactivePrompt
from backend.services.k0_query_service import K0QueryService
from backend.services.llm_client import LLMClient
from backend.services.metrics_collector import MetricsCollector
from backend.services.progress_publisher import ProgressPublisher


class ConciergeAgent:
    """
    Main orchestrator for reactive-proactive specialist coordination.

    Flow:
    1. handle_message(user_message, context)
    2. ReactiveHandler.classify_intent_and_emotion()
    3. Emit reactive response (empathy + action)
    4. Spawn specialist based on intent
    5. Start background specialist work
    6. While specialist works (>300ms):
       - ProactiveGenerator.generate_prompt()
       - Emit proactive events
    7. Await specialist analysis
    8. Return combined response

    Example:
        concierge = ConciergeAgent(...)
        response = await concierge.handle_message("I think milk is making me sick", context)
        # Returns: reactive_response + proactive_prompts + specialist_analysis
    """

    def __init__(
        self,
        reactive_handler: ReactiveHandler,
        proactive_generator: ProactiveGenerator,
        llm_client: LLMClient,
        k0_query_service: K0QueryService,
        metrics_collector: MetricsCollector,
        progress_publisher: Optional[ProgressPublisher] = None,
    ):
        """
        Initialize ConciergeAgent.

        Args:
            reactive_handler: Handler for intent/emotion/empathy
            proactive_generator: Generator for proactive prompts
            llm_client: LLM for specialist analysis
            k0_query_service: K0 data access
            metrics_collector: Performance metrics
            progress_publisher: Optional progress event publisher
        """
        self.reactive_handler = reactive_handler
        self.proactive_generator = proactive_generator
        self.llm_client = llm_client
        self.k0_query_service = k0_query_service
        self.metrics_collector = metrics_collector
        self.progress_publisher = progress_publisher
        self.synthesis_engine = SynthesisEngine(llm_client, metrics_collector)

        # Specialist instances
        self.nutritionist = NutritionistAgent(
            llm_client=llm_client,
            k0_query_service=k0_query_service,
            metrics_collector=metrics_collector,
            progress_publisher=progress_publisher,
        )
        self.psychiatrist = PsychiatristAgent(
            llm_client=llm_client,
            k0_query_service=k0_query_service,
            metrics_collector=metrics_collector,
            progress_publisher=progress_publisher,
        )
        self.planner = PlannerAgent(
            llm_client=llm_client,
            k0_query_service=k0_query_service,
            metrics_collector=metrics_collector,
            progress_publisher=progress_publisher,
        )

        # Proactive prompts collected during background work
        self.proactive_prompts: list[ProactivePrompt] = []

    async def handle_message(self, user_message: str, context: ConversationState) -> dict:
        """
        Handle user message through reactive-proactive-specialist flow.

        Flow:
        1. REACTIVE: Classify intent, detect emotion, generate empathy
        2. SPAWN SPECIALIST: Based on intent domain
        3. PROACTIVE: Generate prompts during specialist work (if >300ms)
        4. SPECIALIST: Analyze user query
        5. COMBINE: Merge reactive + specialist insights

        Args:
            user_message: User's message
            context: Conversation state

        Returns:
            dict with:
            {
                "reactive_response": str,
                "proactive_prompts": list[ProactivePrompt],
                "specialist_analysis": AnalysisResult,
                "combined_response": str,
                "metrics": {
                    "reactive_time_ms": int,
                    "specialist_time_ms": int,
                    "total_time_ms": int,
                }
            }
        """
        start_time = asyncio.get_event_loop().time()

        # ============================================================
        # PHASE 1: REACTIVE - Immediate response
        # ============================================================
        reactive_start = asyncio.get_event_loop().time()

        # Classify intent and generate response
        intent = self.reactive_handler.classify_intent(user_message, context)
        reactive_response = self.reactive_handler.generate_response(user_message, intent, context)
        specialist_type = intent.specialist_type

        reactive_time_ms = int((asyncio.get_event_loop().time() - reactive_start) * 1000)

        # ============================================================
        # CHECK: Does this need specialist analysis?
        # ============================================================
        # Confidence-based routing:
        # - High confidence (>= 0.7) → Route to specialist
        # - Low confidence (< 0.7) but health domain → Ask clarifying question
        # - General domain → Casual conversation

        # Case 1: Clear general conversation (greetings, thanks, etc.)
        if intent.domain == "general":
            return {
                "reactive_response": None,
                "proactive_prompts": [],
                "specialist_analysis": None,
                "synthesis": reactive_response,
                "combined_response": reactive_response,
                "metrics": {
                    "reactive_time_ms": reactive_time_ms,
                    "specialist_time_ms": 0,
                    "total_time_ms": reactive_time_ms,
                },
            }

        # Case 2: Ambiguous health query (low confidence) → Ask clarifying question
        if intent.confidence < 0.7:
            clarifying_question = self._generate_clarifying_question(user_message, intent)
            return {
                "reactive_response": None,
                "proactive_prompts": [],
                "specialist_analysis": None,
                "synthesis": clarifying_question,
                "combined_response": clarifying_question,
                "metrics": {
                    "reactive_time_ms": reactive_time_ms,
                    "specialist_time_ms": 0,
                    "total_time_ms": reactive_time_ms,
                },
            }

        # Case 3: High confidence health query → Spawn specialist
        # ============================================================
        # PHASE 2: SPAWN SPECIALIST
        # ============================================================
        specialist = self._get_specialist(specialist_type)
        specialist_task = asyncio.create_task(
            specialist.analyze(user_message, context.user_id, context)
        )

        # ============================================================
        # PHASE 3: PROACTIVE - Generate prompts during background work
        # ============================================================
        self.proactive_prompts = []

        # Wait a bit then generate proactive prompts (if specialist still working)
        proactive_task = asyncio.create_task(
            self._generate_proactive_prompts(
                user_message, specialist_type, context, specialist_task
            )
        )

        # ============================================================
        # PHASE 4: SPECIALIST - Wait for analysis
        # ============================================================
        specialist_analysis = await specialist_task
        proactive_prompts = await proactive_task

        specialist_time_ms = specialist_analysis.duration_ms

        # ============================================================
        # PHASE 5: COMBINE - Merge results
        # ============================================================
        combined_response = await self._combine_responses(
            reactive_response, specialist_analysis, proactive_prompts, user_message, context
        )

        total_time_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)

        return {
            "reactive_response": reactive_response,
            "proactive_prompts": proactive_prompts,
            "specialist_analysis": specialist_analysis,
            "combined_response": combined_response,
            "metrics": {
                "reactive_time_ms": reactive_time_ms,
                "specialist_time_ms": specialist_time_ms,
                "proactive_count": len(proactive_prompts),
                "total_time_ms": total_time_ms,
            },
        }

    async def _generate_proactive_prompts(
        self,
        user_message: str,
        specialist_type: str,
        context: ConversationState,
        specialist_task: asyncio.Task,
    ) -> list[ProactivePrompt]:
        """
        Generate proactive prompts while specialist works.

        Strategy:
        1. Wait a bit (cooldown from reactive)
        2. While specialist is still working:
           - Generate proactive prompt
           - Emit via progress_publisher if available
           - Sleep until next prompt time (cooldown)
        3. Stop when specialist completes

        Args:
            user_message: Original user message
            specialist_type: Type of specialist
            context: Conversation state
            specialist_task: Task handle for specialist analysis

        Returns:
            list[ProactivePrompt] generated during background work
        """
        prompts = []

        try:
            # Initial delay to avoid immediate proactive (let reactive settle)
            await asyncio.sleep(0.2)

            # Generate prompts while specialist is working
            # Typically specialist takes 500-1500ms, so 1-2 proactive prompts
            while not specialist_task.done():
                # Generate prompt
                prompt = self.proactive_generator.generate_prompt(
                    user_message=user_message,
                    specialist_type=specialist_type,
                    context=context,
                    background_task_duration_ms=500,  # Assume ~500ms remaining
                )

                if prompt is not None:
                    prompts.append(prompt)

                    # Emit if publisher available
                    if self.progress_publisher is not None:
                        await self.progress_publisher.emit_event(
                            {
                                "type": "proactive_prompt",
                                "text": prompt.text,
                                "prompt_type": prompt.prompt_type,
                                "information_target": prompt.information_target,
                            }
                        )

                # Wait for cooldown before next prompt
                # (ProactiveGenerator enforces 5-second cooldown)
                await asyncio.sleep(0.5)  # Brief sleep before next check

        except Exception as e:
            # Log error but don't fail the whole flow
            self.metrics_collector.record_error("proactive_generation_error", str(e))

        return prompts

    def _get_specialist(self, specialist_type: str) -> BaseAgent:
        """
        Get specialist agent based on type.

        Args:
            specialist_type: Type (nutritionist, psychiatrist, planner)

        Returns:
            Specialist agent instance

        Raises:
            ValueError: If unknown specialist type
        """
        if specialist_type == "nutritionist":
            return self.nutritionist
        elif specialist_type == "psychiatrist":
            return self.psychiatrist
        elif specialist_type == "planner":
            return self.planner
        else:
            # Fallback to nutritionist
            return self.nutritionist

    async def _combine_responses(
        self,
        reactive_response: str,
        specialist_analysis: AnalysisResult,
        proactive_prompts: list[ProactivePrompt],
        user_message: str,
        context: ConversationState,
    ) -> str:
        """
        Combine reactive, specialist, and proactive into coherent response using SynthesisEngine.

        Flow:
        1. Call SynthesisEngine.synthesize() to generate natural synthesis
        2. Returns synthesis with contradiction detection
        3. Format final response with reactive + proactive + synthesis

        Args:
            reactive_response: Reactive response (empathy + action)
            specialist_analysis: Specialist's analysis result
            proactive_prompts: Proactive prompts generated during work
            user_message: Original user message
            context: Conversation state

        Returns:
            Combined response text with natural synthesis
        """
        # Build context for synthesis
        synthesis_context = {
            "user_message": user_message,
            "recent_history": getattr(context, "recent_history", []),
            "conversation_id": getattr(context, "conversation_id", ""),
        }

        # Generate synthesis via SynthesisEngine
        try:
            synthesis_result = await self.synthesis_engine.synthesize(
                specialist_analysis, synthesis_context
            )
            synthesis_text = synthesis_result["synthesis"]
        except Exception:
            # Fallback: simple combination if synthesis fails
            synthesis_text = self._fallback_combine(specialist_analysis)

        # Build final response
        parts = [reactive_response]

        # Add proactive prompts if generated
        if proactive_prompts:
            for prompt in proactive_prompts:
                parts.append(f"\n💭 {prompt.text}")

        # Add synthesis
        parts.append(f"\n\n{synthesis_text}")

        return "\n".join(parts)

    def _fallback_combine(self, specialist_analysis: AnalysisResult) -> str:
        """
        Fallback response when synthesis fails.

        Args:
            specialist_analysis: Specialist's analysis result

        Returns:
            Simple combined response
        """
        if specialist_analysis.insights:
            insight = specialist_analysis.insights[0]
            return f"The {specialist_analysis.specialist_type} found: {insight.summary}"
        else:
            return "Analysis complete."

    def _generate_clarifying_question(self, user_message: str, intent: Intent) -> str:
        """
        Generate natural clarifying question using LLM when intent is ambiguous.

        No templates - uses LLM to generate contextual, conversational questions.

        Args:
            user_message: User's message
            intent: Classified intent with low confidence

        Returns:
            Natural clarifying question
        """
        prompt = f"""Generate ONLY a natural clarifying question. Do not explain or justify it.

User said: "{user_message}"
Context: Unclear intent about {intent.domain} (confidence: {intent.confidence:.2f})

Requirements:
- 8-20 words
- Conversational tone
- Shows active listening
- References their specific situation

Good examples:
- "Are you feeling symptoms right now, or have you noticed a pattern over time?"
- "Would you like me to look at your budget, or is this more of a general concern?"
- "Is this physical discomfort, or more about how you're feeling emotionally?"

Bad examples (avoid):
- "Could you tell me more?" (too generic)
- "I want to make sure I understand you correctly" (too formal)

OUTPUT ONLY THE QUESTION, NOTHING ELSE:"""

        try:
            response = self.llm_client.generate(prompt, model_profile="creative")
            # Clean up response - remove any meta-text
            question = response.strip().strip('"').strip("'")

            # Remove common meta-text patterns
            if "Here's" in question or "here's" in question:
                # Extract just the question part
                if ":" in question:
                    parts = question.split(":", 1)
                    question = parts[1].strip().strip('"').strip("'")

            # Remove trailing explanatory text
            if "?" in question:
                question = question.split("?")[0] + "?"

            # Ensure it ends with a question mark
            if not question.endswith("?"):
                question += "?"

            return question
        except Exception:
            return "Could you tell me a bit more about what you're experiencing?"
