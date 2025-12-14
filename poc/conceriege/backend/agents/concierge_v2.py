"""
ConciergeAgent V2 - Continuous Conversation with Background Analysis

NEW APPROACH: No intent classification, continuous natural conversation.
- User mentions something → Concierge responds naturally
- In background, check if specialist can help
- When specialist done → "Hey btw, about that milk thing - I found it's triggering your GERD"

Flow:
1. User: "milk makes me sick"
2. Concierge: "That sounds uncomfortable. How often does this happen?"
3. [Background: Nutritionist analyzing milk patterns in K0 data]
4. User: "every morning after breakfast"
5. Concierge: "I see. Hey btw, I looked into your milk consumption - it's definitely triggering your GERD. Your symptoms spike 40% on days you have milk."

No routing, no classification, just natural conversation + background intelligence.

UPGRADE #15: Real-Time Progress Visibility
- Emits progress events to show backend processing to users
- Events: background_analysis_started, backchannel, insight_ready, permission_request
- Maintains transparency while preserving natural conversation flow

Progress Events Emitted:
1. background_analysis_started: When specialist task begins
   {"type": "background_analysis_started", "specialist_type": str, "topic": str, "message": str}

2. backchannel: Natural "thinking" signals during processing
   {"type": "backchannel", "text": "hmm...", "specialist_type": str}

3. insight_ready: When findings are available to inject
   {"type": "insight_ready", "specialist_type": str, "summary": str, "confidence": float, "message": str}

4. permission_request: Asking user if they want to hear findings (consentful proactivity)
   {"type": "permission_request", "specialist_type": str, "topic": str, "text": str}
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from backend.agents.context_manager import ContextManager
from backend.agents.emotion_engine import EmotionContext, EmotionEngine
from backend.agents.focus_tracker import ConversationFocusTracker
from backend.agents.memory_tracker import MemoryTracker
from backend.agents.nutritionist import NutritionistAgent
from backend.agents.psychiatrist import PsychiatristAgent
from backend.agents.reasoning_engine import ReasoningEngine
from backend.agents.style_mirror import StyleMirror, UserStyle
from backend.models.analysis_result import AnalysisResult
from backend.models.conversation_state import ConversationState
from backend.models.progress_event import ProgressEvent
from backend.services.k0_query_service import K0QueryService
from backend.services.llm_client import LLMClient
from backend.services.metrics_collector import MetricsCollector
from backend.services.progress_publisher import ProgressPublisher


@dataclass
class BackgroundTask:
    """Background analysis task with hygiene tracking"""

    task_id: str
    specialist_type: str
    user_query: str
    task: asyncio.Task
    result: Optional[AnalysisResult] = None
    topic: Optional[str] = None  # Topic this task is analyzing
    started_at: float = 0.0  # Timestamp when task started
    priority: int = 0  # Higher = more important (for queuing)


# ============================================================================
# TOPIC 4: SELF-EXPRESSION
# ============================================================================
# Personality modes that give the agent distinct communication styles
# Selected based on detected emotion to create varied, natural responses
# ============================================================================

PERSONALITY_MODES = {
    "caring": {
        "description": "Warm, supportive, empathetic",
        "phrases": ["hope you're okay", "take care", "you got this", "I'm here"],
        "tone": "Use gentle language, show care, validate feelings",
    },
    "analytical": {
        "description": "Clear, factual, logical",
        "phrases": ["let me check", "based on data", "the pattern shows", "makes sense"],
        "tone": "Be direct but kind, focus on facts and evidence",
    },
    "playful": {
        "description": "Light, friendly, casual",
        "phrases": ["btw", "you know", "honestly", "lol", "right?"],
        "tone": "Be casual, use light humor, keep things fun",
    },
    "concerned": {
        "description": "Serious but empathetic, direct",
        "phrases": ["that's tough", "ugh that sucks", "rough stuff", "I get it"],
        "tone": "Acknowledge difficulty strongly, be direct but kind",
    },
    "uncertain": {
        "description": "Not fully confident, showing thinking",
        "phrases": ["not sure but", "might be", "possibly", "I think", "seems like"],
        "tone": "Show thinking process, admit uncertainty, explore possibilities",
    },
}


# ============================================================================
# TOPIC 6: CONVERSATIONAL VARIETY
# ============================================================================
# Structural variation patterns to make responses feel natural and varied
# Rotates through different response structures to avoid template feel
# ============================================================================

RESPONSE_STRUCTURES = {
    "acknowledgment": {
        "description": "Simple acknowledgment of what they said",
        "patterns": [
            "acknowledge_only",  # "yeah" / "that makes sense"
            "acknowledge_then_question",  # "yeah, how long has that been?"
            "acknowledge_with_validation",  # "yeah that sounds tough"
        ],
    },
    "question": {
        "description": "Ask clarifying or curious questions",
        "patterns": [
            "single_question",  # "how often does that happen?"
            "question_chain",  # "is it after meals? or anytime?"
            "open_ended_question",  # "tell me more about that"
        ],
    },
    "observation": {
        "description": "Make an observation or connection",
        "patterns": [
            "pattern_observation",  # "sounds like a pattern"
            "connection_observation",  # "that's like when you mentioned..."
            "insight_observation",  # "interesting, I hadn't thought of that"
        ],
    },
    "statement": {
        "description": "Make a direct statement or assertion",
        "patterns": [
            "informative_statement",  # "coffee can actually trigger reflux"
            "empathetic_statement",  # "that's really frustrating"
            "directive_statement",  # "you should probably avoid that"
        ],
    },
}


# ============================================================================
# TOPIC 10: GRACEFUL CLOSURE
# ============================================================================
# Patterns for detecting when conversations naturally conclude
# and generating warm, satisfying endings
# ============================================================================

CLOSURE_PATTERNS = {
    "resolution_markers": [
        # User expresses resolution/understanding
        "got it",
        "understand",
        "thanks",
        "thank you",
        "appreciate",
        "that helps",
        "perfect",
        "exactly",
        "yep",
        "yeah",
        "okay",
        "ok",
        "cool",
        "great",
        "awesome",
        "makes sense",
        "all set",
        "done",
        "finished",
        "sorted",
    ],
    "correction_markers": [
        # User is correcting us or disagreeing
        "actually",
        "wait",
        "hold on",
        "no",
        "nope",
        "not really",
        "disagree",
        "different",
        "wrong",
        "incorrect",
        "but",
        "however",
    ],
    "warm_closures": [
        "Good luck! Let me know how it goes.",
        "Hope that helps! Feel free to ask if you need anything else.",
        "That should do it! Take care!",
        "You've got this! Reach out if you need more help.",
        "Glad I could help! Happy to chat anytime.",
        "Hope that clears things up! Let me know.",
        "That should solve it! All the best!",
        "Wishing you well! Don't hesitate to reach out.",
    ],
    "next_step_offers": [
        "Want to explore this more?",
        "Need help with anything else?",
        "Anything else on your mind?",
        "Want to dive deeper into this?",
        "Should we look at this from another angle?",
        "Anything else I can help with?",
    ],
    "acceptance_phrases": [
        "sounds good",
        "makes sense",
        "i'll try that",
        "that works",
        "alright",
        "fair point",
        "you're right",
        "good point",
        "i see",
        "got it",
    ],
}


class ConciergeAgentV2:
    """
    Continuous conversation concierge with background specialist analysis.

    Key differences from V1:
    - NO intent classification
    - NO routing decisions
    - Continuous natural conversation
    - Specialists work in background
    - Results injected naturally into conversation
    """

    def __init__(
        self,
        llm_client: LLMClient,
        k0_query_service: K0QueryService,
        metrics_collector: MetricsCollector,
        progress_publisher: Optional[ProgressPublisher] = None,
    ):
        self.llm_client = llm_client
        self.k0_query_service = k0_query_service
        self.metrics_collector = metrics_collector
        self.progress_publisher = progress_publisher

        # TOPIC 2: Emotion & Empathy Layer
        self.emotion_engine = EmotionEngine(llm_client=llm_client)
        self.current_emotion: Optional[EmotionContext] = None

        # TOPIC 7: Human Reasoning - Reasoning context
        self.reasoning_context: Optional[object] = None

        # TOPIC 3: Memory & Continuity - Memory Tracker
        self.memory = MemoryTracker()

        # TOPIC 8: Context Awareness - Context Manager
        self.context_manager = ContextManager()

        # TOPIC 5: Proactivity Timing - Focus Tracker
        self.focus_tracker = ConversationFocusTracker()

        # TOPIC 7: Human Reasoning - Reasoning Engine
        self.reasoning_engine = ReasoningEngine(llm_client=llm_client)

        # TOPIC 9: Style Mirror - User Style Tracking
        self.style_mirror = StyleMirror()
        self.user_style: Optional[UserStyle] = None

        # TOPIC 10: Graceful Closure - Closure detection
        self.last_user_input_resolution_attempted = False
        self.conversation_thread_resolved = False

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

        # Background tasks
        self.background_tasks: List[BackgroundTask] = []
        self.completed_analyses: List[AnalysisResult] = []

        # UPGRADE #2: Background Task Hygiene
        # Track pending topics with timestamps for debounce/dedupe
        self.pending_topics: dict[str, float] = {}  # topic -> last_start_timestamp
        self.last_topic_request: dict[str, float] = {}  # topic -> last_request_time
        self.current_topic: Optional[str] = None  # Track current conversation topic
        self.topic_pivot_count: int = 0  # Track topic changes
        self.max_concurrent_tasks: int = 2  # Concurrency cap

        # UPGRADE #3: Backchannel & Timing
        # Track user activity for backchannel signals
        self.last_user_message_time: float = 0.0  # Timestamp of last user message
        self.last_response_time: float = 0.0  # Timestamp of last bot response
        self.user_idle_threshold: float = 1.2  # Seconds before showing backchannel

        # UPGRADE #5: Micro-summaries
        # Track turn count for periodic summarization
        self.turn_count: int = 0  # Total turns in conversation
        self.turns_since_last_summary: int = 0  # Turns since last summary
        self.summary_interval: int = 6  # Summarize every N turns
        self.last_summary: Optional[str] = None  # Last generated summary

        # UPGRADE #10: Floor Control - Don't interrupt while user is typing
        self.user_is_typing: bool = False

        # UPGRADE #11: Topic TTL & Insight Ranking
        self.completed_ttl_secs: float = 120.0  # 2 minutes
        self.completed_queue: List[tuple[float, AnalysisResult]] = []

        # UPGRADE #12: Latency Budgets (milliseconds)
        self.NEGOTIATION_DEADLINE_MS: int = 50
        self.RESPONSE_P95_MS: int = 350
        self.INJECT_GAP_MS: int = 450

        # Conversation history for context
        self.conversation_history: List[dict] = []

    def set_user_typing(self, is_typing: bool):
        """
        UPGRADE #10: Floor Control - Signal when user is composing.

        Gate injections and backchannels to avoid interrupting.
        UI should call this when user starts/stops typing.

        Args:
            is_typing: True if user is currently typing
        """
        self.user_is_typing = is_typing

    def _extract_topic(self, message: str) -> Optional[str]:
        """
        Extract conversation topic from message using keyword matching.

        TOPIC 3: Memory & Continuity - Rule-based topic extraction
        Identifies which topic (coffee, gerd, sleep, etc.) is being discussed.

        Args:
            message: User message to analyze

        Returns:
            Topic name if found, None otherwise
        """
        message_lower = message.lower()

        # Check against known topics
        for topic, keywords in self.memory.TOPIC_KEYWORDS.items():
            if any(keyword in message_lower for keyword in keywords):
                return topic

        return None

    def _phrase_with_confidence(self, text: str, confidence: float) -> str:
        """
        Wrap findings with confidence-appropriate hedging language.

        Maps confidence scores to human-like hedging:
        - 0.0-0.49: "might be", "not sure yet..."
        - 0.5-0.79: "likely", "points to..."
        - 0.8-1.0: "pretty clearly", "strong pattern..."

        Args:
            text: Finding text to wrap
            confidence: Confidence score (0.0-1.0)

        Returns:
            Text with confidence-appropriate phrasing
        """
        if confidence >= 0.8:
            hedges = ["pretty clearly", "strong pattern", "definitely looks like", "clearly shows"]
        elif confidence >= 0.5:
            hedges = ["likely", "points to", "suggests", "seems like"]
        else:
            hedges = ["might be", "could be", "possibly", "not sure yet but maybe"]

        import random

        hedge = random.choice(hedges)
        return f"{hedge}: {text}"

    async def _maybe_permission_ping(self, topic: Optional[str] = None) -> Optional[str]:
        """
        Generate permission ping if we have pending findings.

        Consentful proactivity - ask before injecting unless user invited it.

        Args:
            topic: Current conversation topic

        Returns:
            Permission ping message, or None if no pending findings
        """
        if not self.completed_analyses:
            return None

        # Check if any completed analysis matches current topic
        relevant = self.completed_analyses[0]
        specialist_type = relevant.specialist_type.lower()

        # Generate natural permission request
        pings = [
            f"quick heads-up — want me to share what I just found about {specialist_type}?",
            f"btw I finished analyzing {specialist_type} — want to hear it?",
            f"got some insights on {specialist_type} if you're interested?",
            f"just wrapped up checking {specialist_type} — should I share?",
        ]

        import random

        return random.choice(pings)

    def _get_personality_instructions(self, mode: str = "caring") -> str:
        """
        Generate personality-guided instructions for LLM response generation.

        TOPIC 4: Self-Expression - Creates varied, personality-driven responses
        by prepending personality instructions to the LLM prompt.

        Args:
            mode: Personality mode ("caring", "analytical", "playful", "concerned", "uncertain")

        Returns:
            String with personality instructions to prepend to LLM prompt
        """
        personality = PERSONALITY_MODES.get(mode, PERSONALITY_MODES["caring"])

        return f"""TOPIC 4: SELF-EXPRESSION - PERSONALITY MODE: {mode.upper()}

Personality: {personality['description']}

{personality['tone']}

Common phrases to use naturally: {', '.join(personality['phrases'])}

CRITICAL RULES:
- Use contractions: "you're", "it's", "gonna", "btw", "lemme"
- Keep responses SHORT (1-2 sentences max)
- NO formal phrases: "I understand", "Let me help", "I appreciate", "I see"
- Vary sentence length - sometimes short, sometimes longer
- Use ellipses sometimes: "hmm...", "well..."
- Add metacomments occasionally: "not sure if this helps but...", "I might be overthinking this but..."
- Sound natural and human, not like a template

AVOID ROBOTIC PATTERNS:
❌ "I understand what you're going through"
❌ "Let me assist you with that"
❌ "I appreciate you sharing"
❌ "Thank you for letting me know"
✅ "yeah that sounds rough"
✅ "btw..."
✅ "hmm not sure but..."
✅ "you're good"
"""

    def _get_variety_instructions(self, message: str, response_length: str = "medium") -> str:
        """
        Generate structural variety instructions to avoid template responses.

        TOPIC 6: Conversational Variety - Alternates response structure and length
        to create more natural, varied conversation flow. Prevents LLM from falling
        into repetitive patterns.

        Args:
            message: User message (for content-aware structure selection)
            response_length: "short" (1 sentence) | "medium" (2 sentences) | "long" (3+ sentences)

        Returns:
            String with variety instructions to guide response structure
        """
        import random

        # Determine response structure based on content
        message_lower = message.lower()

        # If message is a question, sometimes answer directly
        has_question = "?" in message

        # If message is sharing emotion, sometimes acknowledge first
        has_emotion = any(
            word in message_lower
            for word in [
                "feel",
                "feeling",
                "upset",
                "happy",
                "sad",
                "angry",
                "frustrated",
                "worried",
                "anxious",
            ]
        )

        # Select random structure type
        if has_question and random.random() < 0.6:
            selected_structure = "question"  # Answer questions directly
        elif has_emotion and random.random() < 0.5:
            selected_structure = "acknowledgment"  # Acknowledge emotions first
        else:
            selected_structure = random.choice(
                ["acknowledgment", "question", "observation", "statement"]
            )

        # Build length-based guidance
        length_guidance = {
            "short": "Keep response to exactly 1 sentence. Be concise.",
            "medium": "Keep response to 2 sentences. Balance brevity with substance.",
            "long": "Response can be 2-3 sentences. You can expand a bit more here.",
        }.get(response_length, "Keep response to 2 sentences.")

        # Build structure-specific guidance
        structure_guidance = {
            "acknowledgment": """Response structure: Acknowledgment + optional follow-up
Examples:
- "yeah that makes sense"
- "ugh that sounds rough, how long has it been going on?"
- "totally get that, happens to me too"

Start by acknowledging what they said, then optionally ask a follow-up question.""",
            "question": """Response structure: Question(s) focused on understanding
Examples:
- "how often does that happen?"
- "is it after meals, or anytime?"
- "when did you first notice this?"

Ask genuine questions to understand better. Questions can be curious or clarifying.""",
            "observation": """Response structure: Observation or connection
Examples:
- "sounds like a pattern to me"
- "that's like when you mentioned the sleep thing before"
- "interesting, I hadn't thought of it that way"

Make an observation, draw a connection, or offer a new perspective.""",
            "statement": """Response structure: Direct statement or assertion
Examples:
- "coffee actually can trigger reflux"
- "that's really frustrating to deal with"
- "yeah, that's definitely worth paying attention to"

Make a direct statement, observation, or assertion based on what they said.""",
        }.get(selected_structure, "Respond naturally.")

        return f"""TOPIC 6: CONVERSATIONAL VARIETY - STRUCTURE & LENGTH VARIATION

{length_guidance}

{structure_guidance}

Variety rules:
- Don't repeat the same structure every response
- Mix acknowledgments, questions, observations, and statements
- Vary sentence starters: "yeah", "hmm", "interesting", "oh", "wait", "right?"
- Sometimes use short replies, sometimes longer ones
- Break up the monotony - this is your chance to add personality

Current structure type: {selected_structure.upper()}

Generate a response that fits this structure and length."""

    def _detect_thread_closure(self, message: str) -> bool:
        """
        Detect if user message indicates conversation thread is resolving.

        TOPIC 10: Graceful Closure - RULE-BASED detection

        Checks for resolution markers (thanks, got it, makes sense) or
        acceptance phrases indicating user has understood/accepted guidance.

        Args:
            message: User message to analyze

        Returns:
            True if closure indicators detected
        """
        message_lower = message.lower()

        # Check for resolution markers
        for marker in CLOSURE_PATTERNS["resolution_markers"]:
            if marker in message_lower:
                return True

        # Check for acceptance phrases
        for phrase in CLOSURE_PATTERNS["acceptance_phrases"]:
            if phrase in message_lower:
                return True

        return False

    def _detect_user_correction(self, message: str) -> bool:
        """
        Detect if user is correcting or disagreeing with agent guidance.

        TOPIC 10: Graceful Closure - Correction detection

        User might say "actually no, that's not right" or "wait, I disagree".
        Helps agent acknowledge correction gracefully.

        Args:
            message: User message to analyze

        Returns:
            True if correction/disagreement detected
        """
        message_lower = message.lower()

        # Check for correction markers
        for marker in CLOSURE_PATTERNS["correction_markers"]:
            if marker in message_lower:
                return True

        return False

    def _get_closure_instructions(self, message: str) -> str:
        """
        Generate LLM instructions for graceful closure or acceptance.

        TOPIC 10: Graceful Closure - Instruction generation

        If user shows signs of thread closure (thanks, got it, makes sense),
        generate instructions to wrap up warmly and offer next steps.

        Args:
            message: User message to analyze

        Returns:
            String with closure or acceptance instructions for LLM
        """
        import random

        has_closure = self._detect_thread_closure(message)
        has_correction = self._detect_user_correction(message)

        instructions = ["TOPIC 10: GRACEFUL CLOSURE"]

        if has_closure:
            # User is expressing resolution/understanding
            warm_closure = random.choice(CLOSURE_PATTERNS["warm_closures"])
            next_step = random.choice(CLOSURE_PATTERNS["next_step_offers"])
            instructions.append("- Conversation appears to be closing naturally")
            instructions.append(f"- Provide warm closing: '{warm_closure}'")
            instructions.append(f"- Optionally offer next step: '{next_step}'")
            instructions.append("- Keep response warm but brief (1-2 sentences)")
        elif has_correction:
            # User is correcting or disagreeing
            instructions.append("- User is correcting or disagreeing")
            instructions.append("- Acknowledge their correction gracefully")
            instructions.append("- Show flexibility: 'ah got it, so it's more like...'")
            instructions.append("- Don't be defensive, adjust understanding naturally")
        else:
            # Normal continuation
            instructions.append("- Continue conversation normally")

        return "\n".join(instructions)

    async def process_message(self, user_id: str, message: str) -> str:
        """
        Process user message with emotion, personality, and smart proactivity timing.

        Flow:
        1. TOPIC 2: Analyze user emotion FIRST (for empathetic tone)
        2. TOPIC 5: Use focus tracker to determine conversation mode
        3. If in insight_thread: continue discussing recent finding (no interruption)
        4. If inject_proactive + findings ready: inject naturally
        5. Otherwise: generate normal conversational response
        6. TOPIC 1: Send with rhythm (delays + chunking handled by web_ui.py)
        7. Start background analysis if relevant

        Args:
            user_id: User identifier
            message: User's message

        Returns:
            Natural conversational response with all humanization applied
        """
        import time

        # UPGRADE #3: Track user message timing for backchannel
        self.last_user_message_time = time.time()

        # UPGRADE #3: Check if should show backchannel (tasks running + user idle)
        # Note: Backchannel display handled by web_ui.py via should_show_backchannel check
        # For now we just track timing; web_ui can call _get_backchannel_message() when needed

        # TOPIC 2: Analyze emotion FIRST for empathetic response tone
        self.current_emotion = await self.emotion_engine.analyze_emotion(
            message, self.conversation_history
        )

        # TOPIC 3: Extract topic and update memory
        topic = self._extract_topic(message)
        if topic:
            self.memory.add_to_thread(topic, message, source="user")
            # TOPIC 8: Context Awareness - Update context manager
            self.context_manager.update_topic_context(topic)

        # TOPIC 7: Human Reasoning - Analyze confidence and reasoning context
        self.reasoning_context = await self.reasoning_engine.analyze_confidence(
            message, self.conversation_history
        )

        # TOPIC 9: Style Mirror - Analyze user communication style
        self.user_style = self.style_mirror.analyze_style(message)

        # TOPIC 10: Graceful Closure - Detect thread closure patterns
        self.last_user_input_resolution_attempted = self._detect_thread_closure(message)
        if self.last_user_input_resolution_attempted:
            # If user shows resolution signs and we're in topic context, mark topic resolved
            if self.context_manager and hasattr(self.context_manager, "current_context"):
                self.context_manager.mark_topic_resolved(None)

        # NEW: Detect permission for proactive injection
        if self.focus_tracker.detect_permission(message):
            self.focus_tracker.grant_permission()

        # Step 1: Check for completed background tasks
        await self._check_completed_tasks()

        # NEW: Check if we should ask permission before injecting
        import time

        if self.completed_analyses and not self.focus_tracker.state.has_permission:
            # Check if we can inject with consent
            can_inject = self.focus_tracker.can_inject(
                curr_topic=topic, now=time.time(), has_explicit_permission=False
            )

            if not can_inject:
                # Need permission - emit permission request event
                if self.progress_publisher and self.completed_analyses:
                    specialist_type = self.completed_analyses[0].specialist_type
                    await self._emit_permission_request(specialist_type, topic)

                # Send permission ping as response
                permission_ping = await self._maybe_permission_ping(topic)
                if permission_ping:
                    # Return permission ping instead of normal response
                    response = permission_ping
                    self.conversation_history.append({"role": "user", "content": message})
                    self.conversation_history.append({"role": "assistant", "content": response})
                    return response

        # TOPIC 5: Determine focus using rule-based tracker (ultra-fast)
        focus = self.focus_tracker.determine_focus(
            message, has_pending_proactive=bool(self.completed_analyses)
        )

        # Step 2: Decide response based on focus mode
        if focus == "continue_insight_thread":
            # User curious about recent insight - continue naturally
            response = await self._continue_insight_discussion(message)

        elif focus == "inject_proactive" and self.completed_analyses:
            # Check consent before injection
            can_inject = self.focus_tracker.can_inject(
                curr_topic=topic,
                now=time.time(),
                has_explicit_permission=self.focus_tracker.state.has_permission,
            )

            if can_inject:
                # Safe to inject proactive finding
                response = await self._respond_with_findings(message)
                # Track the injection for potential continuation
                self.focus_tracker.track_insight_injection(response, topic=topic)
            else:
                # Need permission first - generate normal response
                response = await self._generate_conversational_response(message)

        else:
            # Normal reactive conversation (no interruption)
            response = await self._generate_conversational_response(message)

        # UPGRADE #4: Apply conversational repair if needed
        # Check if response needs softening due to contradiction or uncertainty
        confidence = self.reasoning_context.confidence if self.reasoning_context else 0.7
        if self._should_apply_repair(message, response, confidence):
            response = self._apply_repair_move(response)

        # UPGRADE #5: Maybe append micro-summary
        # Increment turn counters
        self.turn_count += 1
        self.turns_since_last_summary += 1

        # Check if should generate summary
        if self._should_generate_summary():
            summary = await self._generate_micro_summary()
            if summary:
                # Append summary with natural separator
                response = f"{response}\n\n{summary}"
                # Reset counter after summary
                self.turns_since_last_summary = 0
                self.last_summary = summary

        # UPGRADE #7: Maybe append safety escalation
        response = await self._maybe_append_safety_escalation(message, response)

        # UPGRADE #8: Apply stoplist filter (remove AI phrases)
        response = self._apply_stoplist_filter(response)

        # Store in history
        self.conversation_history.append({"role": "user", "content": message})
        self.conversation_history.append({"role": "assistant", "content": response})

        # UPGRADE #3: Track response time for backchannel cooldown
        self.last_response_time = time.time()

        # Step 3: Detect if specialist could help (in background)
        await self._maybe_start_background_analysis(message, user_id)

        return response

    async def _check_completed_tasks(self):
        """
        Check if any background tasks completed and emit progress events.

        UPGRADE #15: Emits insight_ready events when analysis completes.
        """
        import time

        completed = []
        for task in self.background_tasks:
            if task.task.done():
                try:
                    result = task.task.result()
                    if result is not None:  # Type guard
                        task.result = result
                        # UPGRADE #13: Add to TTL queue instead of simple list
                        self.completed_queue.append((time.time(), result))
                        # Keep old list for backward compatibility
                        self.completed_analyses.append(result)

                        # UPGRADE #15: Emit insight_ready event
                        await self._emit_insight_ready(result)

                    completed.append(task)
                except Exception as e:
                    print(f"Background task failed: {e}")
                    completed.append(task)

        # Remove completed tasks and clean up tracking
        for task in completed:
            self.background_tasks.remove(task)
            # UPGRADE #2: Clean up pending_topics on completion
            if task.topic and task.topic in self.pending_topics:
                del self.pending_topics[task.topic]

    async def _respond_with_findings(self, current_message: str) -> str:
        """
        Respond naturally while mentioning background analysis findings.

        UPGRADE #11: Uses grounding lanes (assert/hedge/hypothesis)
        UPGRADE #13: Uses ranked fresh insights from TTL queue
        UPGRADE #14: Adds cognitive trace & evidence receipt

        Example:
        "Hey, btw about that milk thing you mentioned earlier -
        I looked into your data and it's definitely triggering your GERD.
        Your symptoms spike 40% on days you have milk."
        """
        # UPGRADE #13: Use ranked fresh insights instead of FIFO
        topic = self._extract_topic(current_message)
        analysis = self._pop_ranked_fresh(topic)

        # Fallback to old list if new queue is empty
        if not analysis and self.completed_analyses:
            analysis = self.completed_analyses.pop(0)

        if not analysis:
            # No analyses available
            return await self._generate_conversational_response(current_message)

        # UPGRADE #11: Determine grounding lane based on evidence
        lane = self._grounding_lane(analysis)
        lane_opener = self._get_lane_opener(lane)

        # Get primary insight
        primary_insight = analysis.get_primary_insight()
        insight_text = primary_insight.summary if primary_insight else "completed analysis"

        # Build complete findings summary with ALL evidence
        findings_summary = []
        if analysis.actual_finding:
            findings_summary.append(f"Main finding: {analysis.actual_finding}")

        if primary_insight:
            findings_summary.append(f"Insight: {primary_insight.summary}")
            if primary_insight.evidence:
                # Include ALL evidence, not just first one
                for i, evidence_item in enumerate(primary_insight.evidence[:3], 1):
                    findings_summary.append(f"Evidence {i}: {evidence_item}")

        findings_text = "\n".join(findings_summary) if findings_summary else insight_text

        # Apply confidence phrasing if confidence exists
        if analysis.confidence is not None:
            findings_text = self._phrase_with_confidence(findings_text, analysis.confidence)

        # UPGRADE #12: Check band tone (soften for AMBER topics)
        specialist_topic = getattr(analysis, "specialist_type", None)
        tone = self._band_tone(specialist_topic, analysis.confidence or 0.0)

        tone_guidance = ""
        if tone == "soften":
            tone_guidance = "\n\nTone: Use softer language. Avoid absolutes. Add 'if you want, we can try X' instead of 'you should do X'."

        # TOPIC 9: Get style mirroring instructions for findings response
        style_guidance = ""
        if self.user_style:
            style_guidance = f"\n\nCommunication style to match: {self.style_mirror.get_formality_tone(self.user_style)} (energy: {self.style_mirror.get_energy_descriptor(self.user_style)})"

        prompt = f"""You are a conversational AI assistant. You just completed analyzing something the user mentioned earlier.

User's current message: "{current_message}"

Background analysis you completed:
Topic: {analysis.specialist_type}
{findings_text}
Confidence: {analysis.confidence:.0%}
Lane: {lane} ({lane_opener}){tone_guidance}{style_guidance}

Generate a COMPLETE natural response (100-150 words) that:
1. Uses the lane opener: "{lane_opener}"
2. Shares ALL the key findings clearly and completely
3. Explains the evidence and what it means
4. Sounds conversational, not robotic
5. FINISH YOUR SENTENCES - don't cut off mid-thought

Example:
"Hey btw, I just finished analyzing your diet and GERD patterns. Here's what I found: out of 43 diet entries I analyzed, there's a strong correlation with late-night coffee consumption. Every time you had coffee after 8pm, you experienced GERD symptoms within 2 hours. The milk you mentioned actually shows zero correlation - you've had milk 8 times with no symptoms. So the real trigger appears to be evening coffee, not milk. Consider avoiding caffeine after dinner."

Generate COMPLETE natural response (don't cut off):"""

        response = await self.llm_client.generate_async(
            prompt,
            model_profile="creative",
            max_tokens=300,  # Ensure enough tokens for complete response
        )

        response = response.strip()

        # UPGRADE #14: Add cognitive trace & evidence receipt (optional - can be UI metadata)
        # Uncomment if you want receipts in response:
        # response += self._evidence_receipt(analysis)

        return response

    async def _continue_insight_discussion(self, message: str) -> str:
        """
        Continue natural discussion about a recent proactive finding.

        TOPIC 5: Insight Thread Continuation

        When user shows curiosity about a finding we shared, we continue
        discussing it naturally without context switching. This maintains
        conversation flow and makes the proactive intelligence feel natural.

        Args:
            message: User's response to our insight

        Returns:
            Continuation of the insight discussion
        """
        insight = self.focus_tracker.state.last_insight_message
        turn_count = self.focus_tracker.state.insight_turn_count

        # Build conversation context
        recent_history = (
            self.conversation_history[-8:] if len(self.conversation_history) > 0 else []
        )
        history_text = "\n".join(
            [
                f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['content']}"
                for msg in recent_history
            ]
        )

        context_prompt = f"\nRecent conversation:\n{history_text}\n" if history_text else ""

        # Get personality instructions
        mode = "caring"
        if self.current_emotion:
            emotion_to_mode = {
                "frustrated": "concerned",
                "anxious": "caring",
                "happy": "playful",
                "sad": "caring",
                "neutral": "analytical",
            }
            mode = emotion_to_mode.get(self.current_emotion.sentiment, "caring")

        personality_instructions = self._get_personality_instructions(mode)

        # Get emotion instructions
        emotion_instructions = ""
        if self.current_emotion:
            emotion_instructions = self.emotion_engine.get_tone_instructions(self.current_emotion)
            emotion_instructions = f"{emotion_instructions}\n\n"

        prompt = f"""{personality_instructions}

{emotion_instructions}You are continuing a discussion about a finding you shared.

Your previous finding: "{insight}"

User's turn {turn_count} reaction: "{message}"{context_prompt}

Continue the discussion naturally:
- Acknowledge their question or interest
- Provide more detail or evidence if they're curious
- Offer to investigate further if they're skeptical
- Keep the conversation going naturally (1-2 sentences)

Stay on topic. Don't switch subjects. Be conversational.

Response:"""

        response = await self.llm_client.generate_async(
            prompt, model_profile="creative", max_tokens=150
        )

        return response.strip().strip('"').strip("'")

    async def _generate_conversational_response(self, message: str) -> str:
        """
        Generate natural conversational response with emotion and personality.

        TOPIC 2: Integrates emotion context for empathetic, appropriate tone
        TOPIC 3: Integrates memory context for continuity
        TOPIC 4: Integrates personality mode for varied, human-like responses
        TOPIC 6: Integrates variety instructions for structural variation

        Selects personality mode based on detected emotion, then generates
        response with combined personality + emotion + memory + variety guidance.
        """
        import random

        # Build conversation context from recent history (last 4 turns)
        recent_history = (
            self.conversation_history[-8:] if len(self.conversation_history) > 0 else []
        )
        history_text = "\n".join(
            [
                f"{'User' if msg['role'] == 'user' else 'Assistant'}: {msg['content']}"
                for msg in recent_history
            ]
        )

        context_prompt = f"\nRecent conversation:\n{history_text}\n" if history_text else ""

        # TOPIC 3: Get memory context and suggestions
        memory_context = self.memory.generate_memory_context()
        memory_ref = self.memory.suggest_memory_reference(message)
        memory_prompt = ""
        if memory_context:
            memory_prompt = f"Memory context:\n{memory_context}\n\n"
        if memory_ref:
            memory_prompt += f"Memory hint: {memory_ref}\n\n"

        # TOPIC 4: Select personality mode based on detected emotion
        mode = "caring"  # Default personality
        if self.current_emotion:
            # Map emotions to personality modes
            emotion_to_mode = {
                "frustrated": "concerned",  # Frustrated users get concerned personality
                "anxious": "caring",  # Anxious users get caring personality
                "happy": "playful",  # Happy users get playful personality
                "sad": "caring",  # Sad users get caring personality
                "neutral": "analytical",  # Neutral users get analytical personality
            }
            mode = emotion_to_mode.get(self.current_emotion.sentiment, "caring")

        # TOPIC 4: Get personality instructions
        personality_instructions = self._get_personality_instructions(mode)

        # TOPIC 2: Build emotion-aware instructions
        emotion_instructions = ""
        if self.current_emotion:
            emotion_instructions = self.emotion_engine.get_tone_instructions(self.current_emotion)
            emotion_instructions = f"{emotion_instructions}\n\n"

        # TOPIC 6: Get variety instructions with random length and structure
        # Alternate between short, medium, and long responses
        response_lengths = ["short", "medium", "long"]
        selected_length = random.choice(response_lengths)
        variety_instructions = self._get_variety_instructions(
            message, response_length=selected_length
        )

        # TOPIC 8: Get context bridging and temporal awareness
        temporal_context = self.context_manager.generate_temporal_context()
        bridging_hint = self.context_manager.get_bridging_context(current_topic=None)
        context_bridging = ""
        if temporal_context and "No previous" not in temporal_context:
            context_bridging = f"Temporal context:\n{temporal_context}\n\n"
        if bridging_hint:
            context_bridging += f"Topic bridge opportunity: {bridging_hint}\n\n"

        # TOPIC 7: Get reasoning instructions based on confidence
        reasoning_instructions = ""
        if self.reasoning_context:
            reasoning_instructions = self.reasoning_engine.get_reasoning_instructions(
                confidence=self.reasoning_context.confidence,
                has_causal_link=self.reasoning_context.has_causal_link,
                has_question=self.reasoning_context.has_question,
            )
            reasoning_instructions = f"{reasoning_instructions}\n\n"

        # TOPIC 9: Get style mirroring instructions based on user style
        style_instructions = ""
        if self.user_style:
            style_instructions = self.style_mirror.get_style_instructions(self.user_style)
            style_instructions = f"{style_instructions}\n\n"

        # TOPIC 10: Get closure instructions if appropriate
        closure_instructions = self._get_closure_instructions(message)
        closure_instructions = f"{closure_instructions}\n\n"

        # Combine personality + emotion + memory + variety + context + reasoning + style + closure + conversation context
        prompt = f"""{personality_instructions}

{variety_instructions}

{emotion_instructions}{memory_prompt}{context_bridging}{reasoning_instructions}{style_instructions}{closure_instructions}You are a friendly, conversational AI assistant.{context_prompt}

User just said: "{message}"

Respond naturally and warmly using the structure and length guidelines above.
- If greeting → greet back naturally
- If sharing something → acknowledge empathetically
- If asking question → answer conversationally
- If expressing emotion → validate their feelings
- REMEMBER previous context and refer to it naturally
- Consider referencing related topics naturally if bridging opportunity exists

Be human, not robotic. Use your personality mode. No "I hear you" or template phrases.

Response:"""

        response = await self.llm_client.generate_async(
            prompt, model_profile="creative", max_tokens=150
        )
        return response.strip().strip('"').strip("'")

    # ============================================================================
    # UPGRADE #2: BACKGROUND TASK HYGIENE HELPERS
    # ============================================================================

    def _should_debounce(self, topic: str) -> bool:
        """
        Check if topic request should be debounced (too recent).

        Debounce: 500ms minimum between requests for same topic.
        Prevents duplicate tasks from rapid user messages.

        Args:
            topic: Topic to check

        Returns:
            True if should debounce (skip), False if safe to start
        """
        import time

        now = time.time()
        if topic in self.last_topic_request:
            time_since_last = now - self.last_topic_request[topic]
            if time_since_last < 0.5:  # 500ms debounce
                return True
        return False

    def _should_dedupe(self, topic: str) -> bool:
        """
        Check if topic analysis is already running or recent.

        Dedupe: 2min window - don't start same analysis twice.
        Checks both pending tasks and recent completions.

        Args:
            topic: Topic to check

        Returns:
            True if should dedupe (skip), False if safe to start
        """
        import time

        now = time.time()

        # Check if already running
        if topic in self.pending_topics:
            time_since_start = now - self.pending_topics[topic]
            if time_since_start <= 120:  # 2min dedupe window (inclusive)
                return True

        return False

    def _cancel_stale_tasks(self, current_topic: Optional[str]):
        """
        Cancel tasks for topics user has moved away from.

        Topic Pivot Cancellation: If user switches topic for 2+ turns,
        cancel background tasks for old topic (they're no longer relevant).

        Args:
            current_topic: Current conversation topic
        """
        if not current_topic:
            return

        # If topic changed, increment pivot count
        if self.current_topic and self.current_topic != current_topic:
            self.topic_pivot_count += 1
        elif self.current_topic == current_topic:
            # Same topic - reset pivot count
            self.topic_pivot_count = 0

        # Update current topic
        self.current_topic = current_topic

        # Cancel stale tasks after 2 topic changes (>2 turns on different topic)
        # Cancel ALL tasks that don't match current topic
        if self.topic_pivot_count >= 2:
            for task in self.background_tasks[:]:  # Copy list for safe removal
                if task.topic and task.topic != current_topic:
                    if not task.task.done():
                        task.task.cancel()
                        print(f"[Hygiene] Cancelled stale task for topic: {task.topic}")
                    self.background_tasks.remove(task)
                    # Clean up pending_topics
                    if task.topic in self.pending_topics:
                        del self.pending_topics[task.topic]

    def _at_concurrency_limit(self) -> bool:
        """
        Check if at max concurrent task limit.

        Concurrency Cap: Max 2 specialist tasks running simultaneously.
        Prevents resource exhaustion and keeps response times fast.

        Returns:
            True if at limit, False if can start more
        """
        running_count = sum(1 for task in self.background_tasks if not task.task.done())
        return running_count >= self.max_concurrent_tasks

    # ============================================================================
    # UPGRADE #3: BACKCHANNEL & TIMING HELPERS
    # ============================================================================

    def _should_show_backchannel(self) -> bool:
        """
        Check if should show backchannel message.

        Backchannel: "one sec...", "hmm..." when tasks running + user idle.
        Shows natural thinking/processing signals like humans do.

        Conditions:
        - User idle for >1.2 seconds
        - Background tasks are running
        - Haven't shown backchannel in last 3 seconds
        - UPGRADE #10: User is NOT typing (floor control)

        Returns:
            True if should show backchannel, False otherwise
        """
        import time

        # UPGRADE #10: Don't interrupt while user is typing
        if self.user_is_typing:
            return False

        now = time.time()

        # Check if user has been idle long enough
        time_since_message = now - self.last_user_message_time
        if time_since_message < self.user_idle_threshold:
            return False

        # Check if background tasks are running
        running_tasks = [t for t in self.background_tasks if not t.task.done()]
        if not running_tasks:
            return False

        # Check if we showed backchannel recently (prevent spam)
        time_since_response = now - self.last_response_time
        if time_since_response < 3.0:  # 3 second cooldown
            return False

        return True

    def _get_backchannel_message(self) -> str:
        """
        Generate natural backchannel/thinking message.

        Backchannel signals show the bot is processing, like humans do.
        Randomly selects from natural phrases to avoid repetition.

        Returns:
            Backchannel message string
        """
        import random

        backchannels = [
            "one sec...",
            "hmm...",
            "let me check that...",
            "pulling some dots together...",
            "looking into it...",
            "gimme a moment...",
            "checking...",
            "hold on...",
        ]

        return random.choice(backchannels)

    async def _respond_with_timing(self, message: str, generate_fn, delay_range=(0.4, 0.9)) -> str:
        """
        Short-then-expand response pattern with natural timing.

        Pattern: Immediate 1-liner ack → brief delay → detailed response
        Mimics human conversation flow (quick reaction, then elaboration).

        Args:
            message: User message to respond to
            generate_fn: Async function that generates the detailed response
            delay_range: Tuple of (min_delay, max_delay) in seconds

        Returns:
            Combined response with natural timing feel
        """
        import asyncio
        import random

        # Generate quick acknowledgment (1-liner)
        quick_acks = [
            "got it",
            "okay",
            "right",
            "makes sense",
            "gotcha",
            "understood",
            "yep",
            "sure",
        ]

        # For questions, use question-specific acks
        if "?" in message:
            quick_acks = [
                "good question",
                "let me think",
                "hmm",
                "interesting",
                "great question",
            ]

        quick_ack = random.choice(quick_acks)

        # Add natural delay (400-900ms)
        delay = random.uniform(delay_range[0], delay_range[1])
        await asyncio.sleep(delay)

        # Generate detailed response
        detailed_response = await generate_fn()

        # Combine: quick ack + detailed response
        # Use newline to separate for natural feel
        return f"{quick_ack}. {detailed_response}"

    # ============================================================================
    # UPGRADE #4: CONVERSATIONAL REPAIR HELPERS
    # ============================================================================

    def _detect_contradiction(self, message: str, response: str) -> bool:
        """
        Detect if response contradicts user's stated belief or experience.

        Contradiction Detection: Check if bot response dismisses or contradicts
        user's explicit statement. Used to trigger repair moves.

        Patterns:
        - User: "X makes me sick" → Bot: "X is fine"
        - User: "I feel Y" → Bot: "Y doesn't happen"
        - User expresses concern → Bot dismisses

        Args:
            message: User's original message
            response: Bot's generated response

        Returns:
            True if potential contradiction detected, False otherwise
        """
        import re

        message_lower = message.lower()
        response_lower = response.lower()

        # User states negative experience
        user_negative_patterns = [
            r"makes? me (sick|feel bad|uncomfortable|worse)",
            r"(hurts?|hurt|painful|bothers?)",
            r"i feel (bad|terrible|awful|sick)",
            r"(worried|concerned|anxious) about",
            r"not working",
            r"doesn't help",
        ]

        # Bot dismisses or contradicts
        bot_dismissive_patterns = [
            r"(should be|is) (fine|okay|safe|good)",
            r"(no|not a|isn't a) (problem|issue|concern)",
            r"(shouldn't|won't|doesn't) (cause|make|trigger)",
            r"(perfectly|completely) (safe|fine|normal)",
        ]

        # Check if user expressed negative AND bot dismissed
        user_negative = any(re.search(pattern, message_lower) for pattern in user_negative_patterns)
        bot_dismissive = any(
            re.search(pattern, response_lower) for pattern in bot_dismissive_patterns
        )

        return user_negative and bot_dismissive

    def _apply_repair_move(self, response: str) -> str:
        """
        Apply conversational repair to response.

        Repair Move: Add hedging/checking phrase to soften contradiction or
        acknowledge uncertainty. Makes bot feel more collaborative and less
        authoritative when there's potential conflict.

        Repair Templates (8 variations):
        - "I might be off — want me to recheck?"
        - "does that line up with what you feel?"
        - "wait, let me reconsider that"
        - etc. (see reasoning_engine.REASONING_MARKERS["repair"])

        Args:
            response: Original bot response

        Returns:
            Response with repair phrase added
        """
        import random

        # Get repair phrases from reasoning engine
        repair_phrases = self.reasoning_engine.REASONING_MARKERS.get("repair", [])

        if not repair_phrases:
            return response  # Fallback if no repair phrases available

        # Select random repair phrase
        repair = random.choice(repair_phrases)

        # Add repair phrase at end of response
        # Use " — " for natural pause/emphasis
        return f"{response} {repair}"

    def _should_apply_repair(self, message: str, response: str, confidence: float) -> bool:
        """
        Decide if should apply conversational repair.

        Repair Triggers:
        1. Detected contradiction with user's stated experience
        2. Low confidence (<0.6) on sensitive topic
        3. Response contains absolutes ("always", "never", "definitely") when uncertain

        Args:
            message: User's original message
            response: Bot's generated response
            confidence: Confidence score from reasoning engine

        Returns:
            True if should apply repair, False otherwise
        """
        # Trigger 1: Detected contradiction
        if self._detect_contradiction(message, response):
            return True

        # Trigger 2: Low confidence on health/medical topic
        if confidence < 0.6:
            health_keywords = ["sick", "pain", "symptom", "disease", "condition", "medication"]
            if any(keyword in message.lower() for keyword in health_keywords):
                return True

        # Trigger 3: Using absolutes with low confidence
        if confidence < 0.7:
            absolutes = ["always", "never", "definitely", "certainly", "absolutely", "must be"]
            if any(absolute in response.lower() for absolute in absolutes):
                return True

        return False

    # ============================================================================
    # UPGRADE #5: MICRO-SUMMARY HELPERS
    # ============================================================================

    def _should_generate_summary(self) -> bool:
        """
        Check if should generate micro-summary.

        Summary Trigger: Every 6 turns (configurable via summary_interval)
        Helps user maintain context and offers action planning opportunity.

        Returns:
            True if should generate summary, False otherwise
        """
        return self.turns_since_last_summary >= self.summary_interval

    async def _generate_micro_summary(self) -> str:
        """
        Generate micro-summary of recent conversation.

        Summary Format: "so far: X, Y, Z — want action plan?"
        - X, Y, Z: Key points from last 6 turns
        - Ends with action-oriented question

        Returns:
            Formatted micro-summary string
        """
        # Get last N turns (up to summary_interval * 2 messages)
        recent_turns = self.conversation_history[-(self.summary_interval * 2) :]

        if not recent_turns:
            return ""

        # Extract key points from user messages
        user_messages = [turn["content"] for turn in recent_turns if turn["role"] == "user"]

        if not user_messages:
            return ""

        # Create simple summary from recent topics
        topics_mentioned = []
        for msg in user_messages:
            topic = self._extract_topic(msg)
            if topic and topic not in topics_mentioned:
                topics_mentioned.append(topic)

        if not topics_mentioned:
            # Fallback: generic summary
            return f"so far we've talked through {len(user_messages)} questions — want me to suggest next steps?"

        # Format: "so far: X, Y, Z — want action plan?"
        if len(topics_mentioned) == 1:
            summary = f"so far we've covered {topics_mentioned[0]}"
        elif len(topics_mentioned) == 2:
            summary = f"so far we've covered {topics_mentioned[0]} and {topics_mentioned[1]}"
        else:
            # 3+ topics: "X, Y, and Z"
            topics_str = ", ".join(topics_mentioned[:-1]) + f", and {topics_mentioned[-1]}"
            summary = f"so far we've covered {topics_str}"

        # Add action-oriented question
        summary += " — want me to pull together an action plan?"

        return summary

    def _maybe_append_summary(self, response: str) -> str:
        """
        Append micro-summary to response if trigger conditions met.

        Appends summary after main response with natural separator.
        Resets turn counter after summary.

        Args:
            response: Original response text

        Returns:
            Response with optional summary appended
        """
        if not self._should_generate_summary():
            return response

        # Generate summary (synchronous wrapper for async call handled in process_message)
        # This is a flag check; actual generation happens in process_message
        return response  # Placeholder; actual logic in process_message

    async def _maybe_start_background_analysis(self, message: str, user_id: str):
        """
        Detect if specialist could help and start background task.

        NO intent classification - just pattern matching for help signals.

        UPGRADE #2: Background Task Hygiene
        - Debounce: 500ms minimum between same topic requests
        - Dedupe: 2min window - don't start duplicate analysis
        - Concurrency: Max 2 tasks running simultaneously
        - Cancellation: Cancel stale tasks on topic pivot

        UPGRADE #15: Real-Time Progress Visibility
        - Emit background_analysis_started event when task begins
        - Emit backchannel signals during processing
        """
        import time

        message_lower = message.lower()

        # Extract topic from message
        topic = self._extract_topic(message)

        # HYGIENE CHECK #1: Cancel stale tasks if topic pivoted
        self._cancel_stale_tasks(topic)

        # HYGIENE CHECK #2: Concurrency limit
        if self._at_concurrency_limit():
            print(f"[Hygiene] At concurrency limit ({self.max_concurrent_tasks} tasks), skipping")
            return

        # Simple keyword detection (not classification)
        health_keywords = [
            "sick",
            "pain",
            "hurt",
            "symptom",
            "feel",
            "stomach",
            "gerd",
            "milk",
            "food",
            "diet",
        ]
        mental_keywords = ["anxious", "depressed", "stress", "worry", "sleep", "panic", "overwhelm"]

        # Determine specialist type
        specialist_type = None
        if any(kw in message_lower for kw in health_keywords):
            specialist_type = "nutritionist"
        elif any(kw in message_lower for kw in mental_keywords):
            specialist_type = "psychiatrist"

        if not specialist_type:
            return

        # Use specialist_type as topic if no topic extracted
        analysis_topic = topic or specialist_type

        # HYGIENE CHECK #3: Debounce (500ms)
        if self._should_debounce(analysis_topic):
            print(f"[Hygiene] Debouncing {analysis_topic} (too recent)")
            return

        # HYGIENE CHECK #4: Dedupe (2min window)
        if self._should_dedupe(analysis_topic):
            print(f"[Hygiene] Deduping {analysis_topic} (already running/recent)")
            return

        # All checks passed - start task
        now = time.time()
        self.last_topic_request[analysis_topic] = now

        # UPGRADE #15: Emit background analysis started event
        if self.progress_publisher:
            await self.progress_publisher.emit_event(
                {
                    "type": "background_analysis_started",
                    "specialist_type": specialist_type,
                    "topic": analysis_topic,
                    "timestamp": now,
                    "message": f"🔍 Looking into {analysis_topic}...",
                }
            )

        task = asyncio.create_task(self._run_specialist_analysis(specialist_type, message, user_id))
        background_task = BackgroundTask(
            task_id=f"{specialist_type}_{len(self.background_tasks)}",
            specialist_type=specialist_type,
            user_query=message,
            task=task,
            topic=analysis_topic,
            started_at=now,
            priority=1,  # Default priority
        )
        self.background_tasks.append(background_task)
        self.pending_topics[analysis_topic] = now
        print(f"[Background] Started {specialist_type} analysis for topic: {analysis_topic}")

        # UPGRADE #15: Start backchannel emitter task
        asyncio.create_task(self._emit_backchannels_during_analysis(background_task))

    # ========================================================================
    # UPGRADE #15: REAL-TIME PROGRESS VISIBILITY
    # ========================================================================

    async def _emit_backchannels_during_analysis(self, background_task: BackgroundTask):
        """
        Emit backchannel signals while background task is running.

        Shows natural thinking/processing signals like humans do:
        - "hmm..." after 1.2s idle
        - "one sec..." if still processing
        - "pulling some dots together..." for long tasks

        Args:
            background_task: The background task to monitor
        """
        import time

        try:
            # Initial delay before first backchannel
            await asyncio.sleep(self.user_idle_threshold)

            # Emit backchannels while task is running
            while not background_task.task.done():
                # Check if should emit (user not typing, cooldown passed)
                if self._should_show_backchannel():
                    backchannel = self._get_backchannel_message()

                    if self.progress_publisher:
                        await self.progress_publisher.emit_event(
                            {
                                "type": "backchannel",
                                "text": backchannel,
                                "specialist_type": background_task.specialist_type,
                                "timestamp": time.time(),
                            }
                        )

                    # Update last response time to prevent spam
                    self.last_response_time = time.time()

                # Wait before next check
                await asyncio.sleep(1.5)  # Check every 1.5 seconds

        except asyncio.CancelledError:
            # Task was cancelled, stop emitting
            pass
        except Exception as e:
            # Log error but don't fail
            print(f"[Backchannel] Error emitting: {e}")

    async def _emit_insight_ready(self, analysis: AnalysisResult):
        """
        Emit event when insight is ready to inject.

        Notifies UI that findings are available and can be shown when appropriate.

        Args:
            analysis: Completed analysis result
        """
        import time

        if not self.progress_publisher:
            return

        # Extract primary insight
        primary_insight = analysis.get_primary_insight()
        summary = primary_insight.summary if primary_insight else "Analysis complete"

        await self.progress_publisher.emit_event(
            {
                "type": "insight_ready",
                "specialist_type": analysis.specialist_type,
                "summary": summary[:100],  # Truncate for preview
                "confidence": analysis.confidence,
                "timestamp": time.time(),
                "message": f"💡 Found something about {analysis.specialist_type}",
            }
        )

    async def _emit_permission_request(self, specialist_type: str, topic: Optional[str] = None):
        """
        Emit permission request event for consentful proactivity.

        Asks user if they want to hear the findings before injecting.

        Args:
            specialist_type: Type of specialist that found something
            topic: Optional topic of the finding
        """
        import time

        if not self.progress_publisher:
            return

        # Generate permission ping message
        permission_msg = await self._maybe_permission_ping(topic)

        if permission_msg:
            await self.progress_publisher.emit_event(
                {
                    "type": "permission_request",
                    "specialist_type": specialist_type,
                    "topic": topic,
                    "text": permission_msg,
                    "timestamp": time.time(),
                }
            )

    # ========================================================================
    # UPGRADE #7: CONTEXT-AWARE SAFETY
    # ========================================================================

    def _detect_severity_level(self, message: str) -> str:
        """
        Detect severity level of user message for intelligent escalation.

        Returns: "critical", "moderate", or "routine"

        Critical: Immediate attention needed (severe symptoms, emergency indicators)
        Moderate: Worth monitoring or mentioning at checkup
        Routine: Normal conversation, no escalation needed

        DOMAIN-AGNOSTIC: Works across all specialist types (health, mental health,
        finance, education, etc.)
        """
        message_lower = message.lower()

        # Critical keywords (immediate attention)
        critical_keywords = [
            "severe pain",
            "chest pain",
            "can't breathe",
            "difficulty breathing",
            "suicidal",
            "kill myself",
            "end it all",
            "heavy bleeding",
            "passed out",
            "unconscious",
            "emergency",
            "911",
            "help me now",
            "crisis",
        ]

        # Moderate keywords (worth monitoring)
        moderate_keywords = [
            "persistent",
            "worsening",
            "getting worse",
            "not improving",
            "recurring",
            "keeps happening",
            "concerned about",
            "worried about",
            "should i be worried",
        ]

        # Check for critical keywords
        for keyword in critical_keywords:
            if keyword in message_lower:
                return "critical"

        # Check for moderate keywords
        for keyword in moderate_keywords:
            if keyword in message_lower:
                return "moderate"

        # Otherwise routine
        return "routine"

    def _generate_context_aware_escalation(
        self, message: str, severity: str, family_context: Optional[dict] = None
    ) -> Optional[str]:
        """
        Generate intelligent escalation message based on severity and family context.

        NO GENERIC DISCLAIMERS. Use context and severity to provide smart guidance.

        Args:
            message: User's message
            severity: "critical", "moderate", or "routine"
            family_context: Optional family context (age, history, preferences)

        Returns:
            Escalation message if needed, None otherwise

        Examples:
            Critical: "This sounds serious - please contact your doctor today or call 911 if symptoms worsen."
            Moderate: "Worth mentioning at your next checkup to get it checked out."
            Routine: None (no escalation)
        """
        if severity == "critical":
            # Emergency-level concern
            return "\n\n⚠️ This sounds serious - please contact your doctor today or call 911 if symptoms worsen."

        elif severity == "moderate":
            # Worth monitoring
            return "\n\nℹ️ Worth mentioning at your next checkup to get it checked out."

        # Routine - no escalation
        return None

    async def _maybe_append_safety_escalation(self, message: str, response: str) -> str:
        """
        Check if response needs safety escalation and append if needed.

        Integrates context-aware safety into response generation pipeline.

        Args:
            message: User's original message
            response: Generated response

        Returns:
            Response with optional safety escalation appended
        """
        # Detect severity level
        severity = self._detect_severity_level(message)

        # Generate escalation if needed
        escalation = self._generate_context_aware_escalation(message, severity)

        # Append escalation if present
        if escalation:
            return f"{response}{escalation}"

        return response

    # ========================================================================
    # UPGRADE #8: STOPLIST ENFORCEMENT
    # ========================================================================

    def _apply_stoplist_filter(self, response: str) -> str:
        """
        Remove immersion-breaking AI phrases from responses.

        Banned phrases:
        - "as an AI" / "as a language model"
        - "I don't have personal experiences"
        - "I'm just a..." / "I'm only a..."
        - "I apologize for any confusion"
        - "I cannot" (when being overly cautious)

        This maintains natural conversation flow by removing robotic disclaimers.

        Args:
            response: Generated response text

        Returns:
            Filtered response with banned phrases removed
        """
        import re

        # Define stoplist patterns (case-insensitive)
        stoplist_patterns = [
            # "As an AI" variants
            r"as an ai[^.]*\.",
            r"as a language model[^.]*\.",
            r"as an artificial intelligence[^.]*\.",
            # "I don't have" disclaimers
            r"i don'?t have personal experiences?[^.]*\.",
            r"i don'?t have feelings?[^.]*\.",
            r"i don'?t have access to[^.]*\.",
            # "I'm just/only" hedging
            r"i'?m just an? (ai|assistant|bot|program)[^.]*\.",
            r"i'?m only an? (ai|assistant|bot|program)[^.]*\.",
            # Generic apologies
            r"i apologize for any confusion[^.]*\.",
            r"i'?m sorry for any confusion[^.]*\.",
            # Overly cautious disclaimers
            r"please note that i'?m an ai[^.]*\.",
            r"keep in mind that i'?m an ai[^.]*\.",
            r"remember that i'?m not a (doctor|therapist|professional)[^.]*\.",
        ]

        filtered_response = response

        # Apply each pattern
        for pattern in stoplist_patterns:
            filtered_response = re.sub(pattern, "", filtered_response, flags=re.IGNORECASE)

        # Clean up extra whitespace and double spaces
        filtered_response = re.sub(r"\s+", " ", filtered_response)
        filtered_response = filtered_response.strip()

        # Clean up double periods or leading punctuation
        filtered_response = re.sub(r"\.{2,}", ".", filtered_response)
        filtered_response = re.sub(r"^\s*[.,;]\s*", "", filtered_response)

        return filtered_response

    # ========================================================================
    # UPGRADE #9: EPISODIC ANCHORS
    # ========================================================================

    def _add_temporal_marker(self, memory_entry: str, timestamp: Optional[float] = None) -> dict:
        """
        Add temporal metadata to memory entry for episodic anchoring.

        Args:
            memory_entry: Memory content
            timestamp: Unix timestamp (defaults to current time)

        Returns:
            Dict with content, timestamp, and temporal markers
        """
        import time
        from datetime import datetime

        if timestamp is None:
            timestamp = time.time()

        dt = datetime.fromtimestamp(timestamp)

        return {
            "content": memory_entry,
            "timestamp": timestamp,
            "day_of_week": dt.strftime("%A"),  # "Monday", "Tuesday", etc.
            "date": dt.strftime("%Y-%m-%d"),
            "time_of_day": dt.strftime("%H:%M"),
            "relative_time": self._get_relative_time_label(timestamp),
        }

    def _get_relative_time_label(self, timestamp: float) -> str:
        """
        Generate relative time label for episodic reference.

        Examples: "just now", "earlier today", "yesterday", "last week", "last month"

        Args:
            timestamp: Unix timestamp to label

        Returns:
            Human-readable relative time label
        """
        import time
        from datetime import datetime

        now = time.time()
        diff_seconds = now - timestamp

        # Just now (< 1 minute)
        if diff_seconds < 60:
            return "just now"

        # Minutes ago (< 1 hour)
        if diff_seconds < 3600:
            minutes = int(diff_seconds / 60)
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"

        # Hours ago (< 1 day)
        if diff_seconds < 86400:
            hours = int(diff_seconds / 3600)
            if hours == 1:
                return "earlier today"
            return f"{hours} hours ago"

        # Yesterday
        if diff_seconds < 172800:  # 2 days
            return "yesterday"

        # This week (< 7 days)
        if diff_seconds < 604800:
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime("%A")  # "Monday", "Tuesday", etc.

        # Last week (< 14 days)
        if diff_seconds < 1209600:
            return "last week"

        # Last month (< 60 days)
        if diff_seconds < 5184000:
            weeks = int(diff_seconds / 604800)
            return f"{weeks} weeks ago"

        # Older
        months = int(diff_seconds / 2592000)  # ~30 days
        return f"{months} month{'s' if months > 1 else ''} ago"

    def _generate_temporal_reference(self, memory_with_timestamp: dict) -> str:
        """
        Generate natural temporal reference for memory recall.

        Examples:
        - "Monday's breakfast"
        - "last week's homework"
        - "yesterday's conversation"
        - "that thing we discussed earlier today"

        Args:
            memory_with_timestamp: Memory dict with temporal metadata

        Returns:
            Natural temporal reference string
        """
        relative_time = memory_with_timestamp.get("relative_time", "earlier")
        content_snippet = memory_with_timestamp.get("content", "")[:30]

        # Generate natural reference based on relative time
        if relative_time == "just now":
            return "what we just discussed"
        elif relative_time == "earlier today":
            return f"earlier today's {self._extract_topic_from_content(content_snippet)}"
        elif relative_time == "yesterday":
            return f"yesterday's {self._extract_topic_from_content(content_snippet)}"
        elif relative_time.endswith("ago"):
            return f"that thing from {relative_time}"
        elif relative_time in [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]:
            return f"{relative_time}'s {self._extract_topic_from_content(content_snippet)}"
        elif relative_time == "last week":
            return f"last week's {self._extract_topic_from_content(content_snippet)}"
        else:
            return f"that conversation {relative_time}"

    def _extract_topic_from_content(self, content: str) -> str:
        """
        Extract topic keyword from content for temporal reference.

        Args:
            content: Content snippet

        Returns:
            Topic keyword or "discussion"
        """
        # Simple keyword extraction (can be enhanced)
        keywords = [
            "breakfast",
            "lunch",
            "dinner",
            "homework",
            "meeting",
            "appointment",
            "symptom",
            "pain",
            "meal",
            "exercise",
            "conversation",
            "question",
        ]

        content_lower = content.lower()
        for keyword in keywords:
            if keyword in content_lower:
                return keyword

        return "discussion"

    # ========================================================================
    # UPGRADE #11: EVIDENCE THRESHOLD & GROUNDING LANES
    # ========================================================================

    def _grounding_lane(self, analysis: AnalysisResult) -> str:
        """
        Determine confidence level for findings based on evidence.

        Returns: "assert", "hedge", or "hypothesis"

        - assert: Strong evidence (3+ items, high effect size, high confidence)
        - hedge: Some evidence (1+ items, moderate effect/confidence)
        - hypothesis: Weak evidence (exploratory, needs more data)

        This prevents overconfident claims and maintains trust.
        """
        # Extract evidence metrics
        evidence_items = getattr(analysis, "evidence", []) or []
        k = len(evidence_items)

        # Effect size and confidence (with safe defaults)
        eff = getattr(analysis, "effect_size", 0.0) or 0.0
        conf = getattr(analysis, "confidence", 0.0) or 0.0

        # Strong evidence lane
        if k >= 3 and eff >= 0.25 and conf >= 0.7:
            return "assert"

        # Moderate evidence lane
        if k >= 1 and (eff >= 0.15 or conf >= 0.5):
            return "hedge"

        # Weak evidence lane
        return "hypothesis"

    def _get_lane_opener(self, lane: str) -> str:
        """Get natural language opener based on grounding lane."""
        if lane == "assert":
            return "Hey btw, I just finished analyzing this — pretty clearly"
        elif lane == "hedge":
            return "Hey btw, I looked into it — likely"
        else:
            return "Hey, quick thought — not sure yet but it might be"

    # ========================================================================
    # UPGRADE #12: BAND-AWARE TONE
    # ========================================================================

    def _band_tone(self, topic: Optional[str], confidence: float) -> str:
        """
        Determine tone based on topic sensitivity band.

        - GREEN: General topics, can be direct
        - AMBER: Health/mental health, soften language when confidence < 0.8
        - RED: Crisis situations (handled by safety escalation)

        Returns: "soften" or "normal"
        """
        # AMBER band topics (health, mental health)
        amber_topics = {
            "gerd",
            "sleep",
            "diet",
            "stomach",
            "medication",
            "symptom",
            "pain",
            "anxiety",
            "depression",
            "stress",
            "mental",
        }

        # Check if topic is in AMBER band
        is_amber = topic and any(amber_kw in topic.lower() for amber_kw in amber_topics)

        # Soften tone for AMBER topics with lower confidence
        if is_amber and confidence < 0.8:
            return "soften"

        return "normal"

    # ========================================================================
    # UPGRADE #13: TOPIC TTL & INSIGHT RANKING
    # ========================================================================

    def _pop_ranked_fresh(self, curr_topic: Optional[str]) -> Optional[AnalysisResult]:
        """
        Pop the most relevant, fresh analysis from completed queue.

        Ranking criteria:
        1. Topic match (2x weight if matches current topic)
        2. Confidence level
        3. Freshness (timestamp)

        Expires analyses older than TTL (2 minutes by default).

        Returns:
            Most relevant analysis or None if queue is empty/expired
        """
        import time

        now = time.time()

        # Filter expired analyses and build ranking
        ranked = [
            (
                ts,
                r,
                2 if curr_topic and getattr(r, "specialist_type", None) == curr_topic else 1,
            )
            for ts, r in self.completed_queue
            if now - ts <= self.completed_ttl_secs
        ]

        # No fresh analyses available
        if not ranked:
            self.completed_queue.clear()
            return None

        # Rank by: topic match, confidence, freshness
        ts, res, topic_weight = max(
            ranked,
            key=lambda x: (
                x[2],  # Topic match weight
                getattr(x[1], "confidence", 0.0),  # Confidence
                x[0],  # Timestamp (freshness)
            ),
        )

        # Remove from queue
        self.completed_queue = [(t, r) for (t, r) in self.completed_queue if r is not res]

        return res

    # ========================================================================
    # UPGRADE #14: COGNITIVE TRACE & RECEIPTS
    # ========================================================================

    def _trace(self) -> str:
        """
        Get or generate cognitive trace ID for this operation.

        Used for transparency and debugging. Every injection/finding
        should be stamped with a trace ID.
        """
        from uuid import uuid4

        # Get from context manager if available
        trace_id = getattr(self.context_manager, "current_trace_id", None)

        if not trace_id:
            trace_id = str(uuid4())
            # Store for this conversation turn
            if hasattr(self.context_manager, "set_trace_id"):
                self.context_manager.set_trace_id(trace_id)

        return trace_id

    def _evidence_receipt(self, analysis: AnalysisResult) -> str:
        """
        Generate evidence receipt footer for transparency.

        Shows trace ID and evidence count to build trust.
        Can be shown in UI or sent to metrics.
        """
        evidence_items = getattr(analysis, "evidence", []) or []
        evidence_count = len(evidence_items)
        trace_id = self._trace()

        return f"\n\n— trace {trace_id[:8]} · evidence {evidence_count}"

    async def _run_specialist_analysis(
        self, specialist_type: str, query: str, user_id: str
    ) -> AnalysisResult:
        """Run specialist analysis in background

        Builds a minimal ConversationState and invokes the specialist's analyze
        method with context. Emits start/completion events via progress_publisher
        when available.
        """
        # Build a minimal ConversationState for the specialist
        conv_id = f"{user_id}-{int(datetime.utcnow().timestamp()*1000)}"
        context = ConversationState(user_id=user_id, conversation_id=conv_id)

        # Emit specialist_started event (non-blocking publish)
        if self.progress_publisher:
            try:
                ev = ProgressEvent(
                    task_id=conv_id,
                    milestone=0,
                    percent=0,
                    message=f"Starting {specialist_type} analysis",
                )
                self.progress_publisher.publish(conv_id, ev)
            except Exception:
                pass

        # Run the specialist analysis
        if specialist_type == "nutritionist":
            result = await self.nutritionist.analyze(query, user_id, context)
        elif specialist_type == "psychiatrist":
            result = await self.psychiatrist.analyze(query, user_id, context)
        else:
            raise ValueError(f"Unknown specialist: {specialist_type}")

        # Emit specialist_completed event (non-blocking publish)
        if self.progress_publisher:
            try:
                summary = getattr(result, "actual_finding", "analysis complete")
                ev = ProgressEvent(
                    task_id=conv_id,
                    milestone=5,
                    percent=100,
                    message=f"{specialist_type} analysis complete: {summary}",
                )
                self.progress_publisher.publish(conv_id, ev)
            except Exception:
                pass

        return result
