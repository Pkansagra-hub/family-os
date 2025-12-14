"""
ProactiveGenerator - Proactive Prompt Generation During Background Work

Generates contextual proactive prompts to fill wait time while specialists analyze.
Identifies information gaps and suggests follow-up questions or future actions.

Research basis:
- Mixed-Initiative Dialogue (Horvitz 1999) - Agent-initiated interactions
- Information Gap (Groenendijk & Stokhof 1984) - What user hasn't told us
- Discourse Structure (Mann & Thompson 1988) - Natural dialogue flow
- Cognitive Load (Sweller 1988) - Optimal time to ask follow-ups

Performance targets:
- Gap identification: <50ms (LLM call)
- Prompt generation: <100ms (LLM call)
- Cooldown enforcement: Atomic, <1ms
- Prompt strategies: 3 implemented (fill_gap, future_action, clarify)

Architecture:
- Identifies information gaps from user message + specialist type
- Chooses strategy: fill_gap, future_action, or clarify
- Generates natural proactive prompt via LLM
- Enforces 5-second cooldown to prevent spam
- Only generates if background task >300ms (worth the wait)
"""

import time
from dataclasses import dataclass
from typing import Optional

from backend.models.conversation_state import ConversationState
from backend.models.proactive_prompt import ProactivePrompt
from backend.services.llm_client import LLMClient
from backend.services.metrics_collector import MetricsCollector


@dataclass
class InformationGap:
    """Represents a missing piece of information."""

    gap_name: str  # e.g., "pain_severity"
    example_question: str  # e.g., "How severe is the pain? (1-10)"
    relevance: float  # 0.0-1.0 confidence this gap is important


class GapIdentifier:
    """Identifies information gaps based on specialist type and user message."""

    # Common gaps for each specialist type
    SPECIALIST_GAPS = {
        "nutritionist": {
            "pain_severity": (
                "How severe is the symptom? (scale 1-10)",
                ["pain", "hurt", "ache", "discomfort"],
            ),
            "pain_location": (
                "Where exactly is the issue?",
                ["stomach", "gut", "digestive", "abdomen"],
            ),
            "symptom_timing": (
                "When did this start? (hours, days, weeks?)",
                ["since", "started", "began", "last"],
            ),
            "symptom_triggers": (
                "What makes it worse?",
                ["trigger", "worse", "after", "following"],
            ),
            "previous_episodes": (
                "Has this happened before?",
                ["before", "again", "previously", "used to"],
            ),
            "medication": (
                "Are you taking any medications?",
                ["medicine", "medication", "drug", "pill", "take"],
            ),
        },
        "psychiatrist": {
            "mood_severity": (
                "How is your mood? (1-10, 10=worst)",
                ["sad", "depressed", "anxious", "stressed"],
            ),
            "mood_duration": (
                "How long have you felt this way?",
                ["days", "weeks", "months", "for a while"],
            ),
            "mood_triggers": (
                "What triggered this mood?",
                ["trigger", "happened", "event", "because"],
            ),
            "support_system": (
                "Do you have people to talk to?",
                ["alone", "friends", "family", "support"],
            ),
            "coping_strategies": (
                "What helps you feel better?",
                ["helps", "better", "exercise", "sleep"],
            ),
            "sleep_quality": ("How's your sleep?", ["sleep", "tired", "fatigue", "rested"]),
        },
        "planner": {
            "priority": (
                "How urgent is this? (1-5, 5=urgent)",
                ["need", "asap", "urgent", "important"],
            ),
            "timeline": ("What's your deadline?", ["deadline", "due", "when", "by"]),
            "resources": ("What resources do you have?", ["have", "available", "can", "able"]),
            "constraints": (
                "What's holding you back?",
                ["can't", "difficult", "hard", "challenge"],
            ),
            "goal_clarity": ("What's the end goal?", ["want", "goal", "achieve", "want to"]),
        },
    }

    def __init__(self, llm_client: LLMClient):
        """Initialize gap identifier.

        Args:
            llm_client: LLM client for semantic analysis
        """
        self.llm_client = llm_client

    def identify_gaps(
        self, user_message: str, specialist_type: str, context: ConversationState
    ) -> list[InformationGap]:
        """Identify information gaps based on user message and specialist type.

        Args:
            user_message: User's message text
            specialist_type: Type of specialist (nutritionist, psychiatrist, etc.)
            context: Conversation state for additional context

        Returns:
            List of InformationGap objects, sorted by relevance (descending)
        """
        if specialist_type not in self.SPECIALIST_GAPS:
            return []

        gaps_dict = self.SPECIALIST_GAPS[specialist_type]
        message_lower = user_message.lower()

        # Identify gaps by keyword matching
        identified_gaps = []
        for gap_name, (example_q, keywords) in gaps_dict.items():
            # Check if gap keywords are NOT in message (i.e., gap exists)
            gap_mentioned = any(keyword in message_lower for keyword in keywords)

            if not gap_mentioned:
                # Gap is missing - user hasn't mentioned it
                relevance = 0.8  # Default relevance
                identified_gaps.append(
                    InformationGap(
                        gap_name=gap_name, example_question=example_q, relevance=relevance
                    )
                )

        # Sort by relevance descending, take top 3
        identified_gaps.sort(key=lambda g: g.relevance, reverse=True)
        return identified_gaps[:3]


class ProactiveGenerator:
    """Generates proactive prompts during background specialist work."""

    # Constants
    COOLDOWN_SECONDS = 5
    MIN_BACKGROUND_DURATION_MS = 300

    # Strategies for proactive prompts
    STRATEGIES = ["fill_gap", "future_action", "clarify"]

    def __init__(self, llm_client: LLMClient, metrics_collector: MetricsCollector):
        """Initialize proactive generator.

        Args:
            llm_client: LLM client for prompt generation
            metrics_collector: Metrics collector for tracking
        """
        self.llm_client = llm_client
        self.metrics_collector = metrics_collector
        self.gap_identifier = GapIdentifier(llm_client)
        self.last_proactive_time: Optional[float] = None

    def generate_prompt(
        self,
        user_message: str,
        specialist_type: str,
        context: ConversationState,
        background_task_duration_ms: int,
    ) -> Optional[ProactivePrompt]:
        """Generate a proactive prompt during background work.

        Args:
            user_message: Original user message
            specialist_type: Type of specialist working (nutritionist, psychiatrist, etc.)
            context: Conversation state for context
            background_task_duration_ms: Estimated duration of background task

        Returns:
            ProactivePrompt object, or None if prompt should not be generated
            (cooldown, too short, etc.)
        """
        # Check cooldown
        if not self._check_cooldown():
            return None

        # Check background duration is worth interrupting for
        if background_task_duration_ms < self.MIN_BACKGROUND_DURATION_MS:
            return None

        # Identify information gaps
        gaps = self.gap_identifier.identify_gaps(user_message, specialist_type, context)
        if not gaps:
            return None

        # Choose strategy
        strategy = self._choose_strategy(gaps, context)

        # Generate prompt
        prompt_text = self._generate_prompt_text(user_message, specialist_type, gaps, strategy)
        if not prompt_text:
            return None

        # Create ProactivePrompt
        prompt = ProactivePrompt(
            text=prompt_text,
            prompt_type=strategy,  # type: ignore
            information_target=gaps[0].gap_name if gaps else "",
        )

        # Update cooldown timer
        self.last_proactive_time = time.time()

        return prompt

    def _check_cooldown(self) -> bool:
        """Check if cooldown period has passed.

        Returns:
            True if can send proactive prompt, False if in cooldown
        """
        if self.last_proactive_time is None:
            return True

        elapsed = time.time() - self.last_proactive_time
        return elapsed >= self.COOLDOWN_SECONDS

    def _choose_strategy(self, gaps: list[InformationGap], context: ConversationState) -> str:
        """Choose proactive prompt strategy.

        Strategies:
        1. fill_gap: Ask for missing information
        2. future_action: Promise future action
        3. clarify: Clarify ambiguous user message

        Args:
            gaps: Identified information gaps
            context: Conversation state

        Returns:
            Strategy name: "fill_gap", "future_action", or "clarify"
        """
        # Prefer fill_gap if there are gaps
        if gaps:
            return "fill_gap"

        # Fall back to future_action
        return "future_action"

    def _generate_prompt_text(
        self,
        user_message: str,
        specialist_type: str,
        gaps: list[InformationGap],
        strategy: str,
    ) -> Optional[str]:
        """Generate natural proactive prompt text via LLM.

        Args:
            user_message: Original user message
            specialist_type: Type of specialist
            gaps: Identified information gaps
            strategy: Strategy to use

        Returns:
            Proactive prompt text, or None if generation fails
        """
        if strategy == "fill_gap":
            return self._generate_fill_gap_prompt(user_message, specialist_type, gaps)
        elif strategy == "future_action":
            return self._generate_future_action_prompt(user_message, specialist_type)
        elif strategy == "clarify":
            return self._generate_clarify_prompt(user_message)
        else:
            return None

    def _generate_fill_gap_prompt(
        self, user_message: str, specialist_type: str, gaps: list[InformationGap]
    ) -> str:
        """Generate 'fill_gap' strategy prompt.

        Acknowledges specialist is working, transitions naturally to asking for missing info.

        Args:
            user_message: Original user message
            specialist_type: Type of specialist
            gaps: Identified gaps

        Returns:
            Proactive prompt text
        """
        # Build gap list
        gap_text = "\n".join([f"- {gap.gap_name}: {gap.example_question}" for gap in gaps[:2]])

        prompt = f"""You are a conversational AI assistant maintaining natural dialogue while a specialist works.

Context:
- User concern: "{user_message}"
- Specialist working: {specialist_type} is analyzing data
- Background task duration: ~1 second
- Missing information:
{gap_text}

Your role:
1. Acknowledge the specialist is working ("Until {specialist_type} gathers data...")
2. Naturally ask for the most important missing information
3. Sound conversational, NOT robotic
4. 15-25 words

Examples of GOOD prompts (conversational, natural):
- "Until the nutritionist gathers data, what time of day did the issue start?"
- "While they're analyzing patterns, how severe would you rate it? Like 1-10?"
- "As the analysis happens in the background, how long has this been going on?"

Examples of BAD prompts (robotic, formal):
- "I am required to inform you that additional data is needed."
- "Please provide the following information immediately."

Generate ONE natural, conversational proactive prompt (15-25 words). Just the prompt, no explanation:"""

        try:
            response = self.llm_client.generate(prompt, model_profile="creative")
            text = response.strip().strip('"').strip("'")
            return text if text else "While I gather more analysis, could you tell me more?"
        except Exception:
            return "While I gather more analysis, could you tell me more?"

    def _generate_future_action_prompt(self, user_message: str, specialist_type: str) -> str:
        """Generate 'future_action' strategy prompt.

        Promises to remember and act on user's concern later.

        Args:
            user_message: Original user message
            specialist_type: Type of specialist

        Returns:
            Proactive prompt text
        """
        prompt = f"""Generate a brief promise to remember and follow up on user's concern later.

User concern: "{user_message}"
Specialist: {specialist_type}

The promise should:
1. Show you're listening and will remember
2. Suggest a specific follow-up action
3. Sound warm and natural
4. 10-15 words

Examples:
- "I'll flag this concern and check in with you about it next time."
- "I'll remember to ask you about this when we talk next."

Generate ONE natural promise (10-15 words). Just the promise, no explanation:"""

        try:
            response = self.llm_client.generate(prompt, model_profile="creative")
            text = response.strip().strip('"').strip("'")
            return text if text else "I'll remember this and follow up with you."
        except Exception:
            return "I'll remember this and follow up with you."

    def _generate_clarify_prompt(self, user_message: str) -> str:
        """Generate 'clarify' strategy prompt.

        Asks a clarifying question if the user's message is ambiguous.

        Args:
            user_message: Original user message

        Returns:
            Proactive prompt text
        """
        prompt = f"""Generate a natural clarifying question about the user's message.

User message: "{user_message}"

The question should:
1. Identify what's unclear
2. Offer possible interpretations
3. Sound conversational
4. 10-15 words

Examples:
- "Just to clarify - do you mean that milk specifically, or dairy in general?"
- "When you say it's making you sick, do you mean nausea or something else?"

Generate ONE natural clarifying question (10-15 words). Just the question, no explanation:"""

        try:
            response = self.llm_client.generate(prompt, model_profile="creative")
            text = response.strip().strip('"').strip("'")
            return text if text else "Just to clarify, could you tell me a bit more?"
        except Exception:
            return "Just to clarify, could you tell me a bit more?"

    def identify_gaps(
        self, user_message: str, specialist_type: str, context: ConversationState
    ) -> list[str]:
        """Public method to identify gaps (for testing).

        Args:
            user_message: User message
            specialist_type: Specialist type
            context: Conversation context

        Returns:
            List of gap names
        """
        gaps = self.gap_identifier.identify_gaps(user_message, specialist_type, context)
        return [g.gap_name for g in gaps]
