"""
ReactiveHandler - Immediate Reactive Response System

Handles intent classification, emotion detection, empathy generation, and
reactive response generation for the Concierge PoC.

Research basis:
- Intent Classification from dialogue systems (Allen 1999, Purver 2004)
- Emotion detection in text (Picard 1997, Rosalind Picard's affective computing)
- Empathy in AI (Brave et al. 2005)
- Mixed-Initiative Dialogue (Horvitz 1999)

Performance targets:
- Intent classification: P95 <30ms (with caching)
- Emotion detection: P95 <20ms (rule-based), <50ms (LLM fallback)
- Total reactive response: P95 <50ms
"""

import json
import re
from typing import Dict

from backend.models.conversation_state import ConversationState
from backend.models.intent import Intent
from backend.services.conversation_store import ConversationStore
from backend.services.llm_client import LLMClient
from backend.services.metrics_collector import MetricsCollector


class EmotionDetector:
    """
    Detects emotion in user messages using LLM for contextual, nuanced detection.

    2025 approach: No keyword matching, pure natural language understanding.
    Detects subtle emotions, intensity, and context that patterns can't capture.
    """

    def __init__(self, llm_client: LLMClient):
        """
        Initialize emotion detector.

        Args:
            llm_client: LLM client for emotion detection
        """
        self.llm_client = llm_client

    def detect(self, user_message: str) -> Dict[str, str | float]:
        """
        Detect emotion in user message using LLM with contextual understanding.

        Args:
            user_message: User's message text

        Returns:
            Dictionary with label, confidence, intensity
            Example: {"label": "concerned", "confidence": 0.95, "intensity": "medium"}
        """
        emotion_data = self._llm_detect(user_message)
        return emotion_data

    def _llm_detect(self, message: str) -> Dict[str, str | float]:
        """
        LLM-based emotion detection with nuanced understanding.

        Args:
            message: User message

        Returns:
            Dict with emotion label, confidence, and intensity
        """
        prompt = f"""You are an empathetic emotion detector. Analyze the user's message and detect their emotional state.

User message: "{message}"

Consider:
- What emotion is the user expressing? (anger, fear, sadness, joy, surprise, disgust, frustration, concern, confusion, pain, neutral, hope, relief, anxiety)
- How intense is it? (low, medium, high)
- Is there urgency or distress?

Output JSON:
{{
  "emotion": "primary emotion label",
  "intensity": "low or medium or high",
  "confidence": 0.0-1.0
}}

JSON output:"""

        try:
            response = self.llm_client.generate(prompt, model_profile="fast")

            # Parse JSON response
            import json
            import re

            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return {
                    "label": data.get("emotion", "neutral"),
                    "confidence": float(data.get("confidence", 0.7)),
                    "intensity": data.get("intensity", "medium"),
                    "source": "llm",
                }

            # Fallback if JSON parsing fails
            return {
                "label": "neutral",
                "confidence": 0.5,
                "intensity": "low",
                "source": "llm_fallback",
            }

        except Exception:
            # Graceful fallback
            return {"label": "neutral", "confidence": 0.5, "intensity": "low", "source": "error"}


class EmpathyGenerator:
    """
    Generates contextual, natural empathetic responses using LLM.

    2025 approach: No templates, pure contextual understanding.
    Responds to user's actual situation, not generic emotion labels.
    """

    def __init__(self, llm_client: LLMClient):
        """
        Initialize empathy generator.

        Args:
            llm_client: LLM client for empathy generation
        """
        self.llm_client = llm_client

    def generate(self, user_message: str, emotion: str) -> str:
        """
        Generate contextual empathetic response using LLM.

        Args:
            user_message: User's message text
            emotion: Detected emotion label

        Returns:
            Natural empathetic response text
        """
        return self._llm_empathy(user_message, emotion)

    def _llm_empathy(self, user_message: str, emotion: str) -> str:
        """
        LLM-based contextual empathy generation.

        Args:
            user_message: User message
            emotion: Detected emotion

        Returns:
            Contextual empathy text
        """
        prompt = f"""You are a compassionate AI assistant. Generate a brief, natural empathetic response to the user's message.

User message: "{user_message}"
Detected emotion: {emotion}

Guidelines:
- Be warm and human-like (NOT robotic)
- Acknowledge their specific situation (NOT generic "I hear you")
- Keep it brief (5-15 words)
- Match their emotional tone
- Be genuine, not overly formal

Examples of GOOD responses:
- User: "milk is making me sick" → "That sounds really uncomfortable, especially if it's happening regularly"
- User: "I'm so frustrated" → "I can tell this is really getting to you"
- User: "I don't understand this" → "This can definitely be confusing, let me help"

Examples of BAD responses (avoid these):
- "I hear you" (too robotic)
- "I understand" (too generic)
- "That's concerning" (sounds like a script)

Generate empathetic response:"""

        try:
            response = self.llm_client.generate(prompt, model_profile="creative")
            # Clean up response
            empathy = response.strip().strip('"').strip("'")
            return empathy if empathy else "I understand how challenging this is"
        except Exception:
            return "I understand how challenging this is"


class ReactiveHandler:
    """
    Handles reactive response generation: intent classification, emotion detection,
    empathy, and action declaration.

    This is the first step in the reactive-proactive loop. Responds within 50ms.

    Research basis:
    - Intent classification from dialogue systems (Allen 1999)
    - Emotion detection in text (Picard 1997)
    - Empathy in AI (Brave et al. 2005)
    """

    def __init__(
        self,
        llm_client: LLMClient,
        conversation_store: ConversationStore,
        metrics_collector: MetricsCollector,
    ):
        """
        Initialize reactive handler.

        Args:
            llm_client: LLM client for intent classification
            conversation_store: Conversation state storage
            metrics_collector: Performance metrics tracker
        """
        self.llm_client = llm_client
        self.conversation_store = conversation_store
        self.metrics_collector = metrics_collector
        self.emotion_detector = EmotionDetector(llm_client)
        self.empathy_generator = EmpathyGenerator(llm_client)

    def classify_intent(self, user_message: str, context: ConversationState) -> Intent:
        """
        Classify user intent using LLM with conversation context.

        Args:
            user_message: User's message text
            context: Conversation state for context

        Returns:
            Intent object with classification

        Raises:
            ValueError: If confidence below threshold (0.7)
        """
        # Build prompt with conversation context
        prompt = self._build_intent_prompt(user_message, context)

        # Call LLM
        response = self.llm_client.generate(prompt, model_profile="fast")

        # Parse response
        intent = self._parse_intent_response(response)

        # DEBUG: Log intent classification
        print(f"[DEBUG] Intent Classification for '{user_message}':")
        print(f"  Domain: {intent.domain}")
        print(f"  Specialist: {intent.specialist_type}")
        print(f"  Confidence: {intent.confidence}")

        # Determine routing (PATH1 vs PATH2)
        routing = self._determine_routing(intent)
        intent.routing = routing

        return intent

    def _build_intent_prompt(self, user_message: str, context: ConversationState) -> str:
        """
        Build LLM prompt for intent classification with conversation context.

        Args:
            user_message: User's message
            context: Conversation state

        Returns:
            LLM prompt string
        """
        # Get recent conversation history (last 3 turns)
        recent_history = list(context.recent_history)[-3:]
        history_text = ""
        if recent_history:
            history_text = "\n".join(
                [
                    f"User: {turn.user_message}\nAgent: {turn.agent_response}"
                    for turn in recent_history
                    if turn.user_message
                ]
            )
        else:
            history_text = "(No previous conversation)"

        prompt = f"""You are an intent classifier for a conversational AI concierge.

**IMPORTANT: This is a CONVERSATION, not a help desk. Most messages should be classified as "general" conversation.**

Previous conversation:
{history_text}

Current user message: "{user_message}"

Classification rules (in priority order):

1. **GENERAL CONVERSATION** (default - use this for 80% of messages):
   - Greetings: "hello", "hi", "hey", "good morning", "heya"
   - Acknowledgments: "ok", "thanks", "got it", "I see", "alright"
   - Casual chat: "how are you", "what's up", "nice", "cool"
   - Continuing conversation: Follow-ups, clarifications, casual responses
   - Off-topic: Anything not clearly asking for specialist help
   - Goodbyes: "bye", "see you", "exit", "quit"
   → Domain: "general", Specialist: "none", Confidence: 0.9-1.0

2. **HEALTH - Physical/Nutrition** (only for CLEAR health/food issues):
   - Explicit symptoms: "I'm feeling sick", "my stomach hurts", "I have pain"
   - Food issues: "milk makes me sick", "allergic to", "GERD symptoms"
   - Diet help: "help me eat better", "what should I eat for"
   → Domain: "health", Specialist: "nutritionist", Confidence: 0.7-1.0

3. **HEALTH - Mental** (only for CLEAR mental health issues):
   - Explicit anxiety/depression: "I'm anxious", "I'm depressed", "panic attacks"
   - Sleep issues: "can't sleep", "insomnia"
   - Mental health help: "feeling overwhelmed", "need therapy"
   → Domain: "health", Specialist: "psychiatrist", Confidence: 0.7-1.0

4. **FINANCE** (only for CLEAR money issues):
   - Budget: "help with budget", "spending too much"
   - Money problems: "can't afford", "financial stress"
   → Domain: "finance", Specialist: "finance_analyst", Confidence: 0.7-1.0

**CRITICAL RULES:**
- If unsure → "general" (NOT health!)
- Vague statements like "feeling off" or "not happy" → "general" conversation (confidence < 0.5)
- Commands like "exit", "quit", "help" → "general"
- If user is just chatting/responding → "general"
- Only route to specialist if user is EXPLICITLY asking for help with a specific issue

Output JSON:
{{
  "type": "QUERY or ACTION",
  "domain": "general or health or finance or social",
  "complexity": "simple or multi_step",
  "specialist_type": "none or nutritionist or psychiatrist or finance_analyst or orchestrator",
  "confidence": 0.0-1.0,
  "entities": []
}}

JSON output:"""

        return prompt

    def _parse_intent_response(self, llm_response: str) -> Intent:
        """
        Parse LLM JSON response into Intent object.

        Args:
            llm_response: LLM output (JSON string)

        Returns:
            Intent object

        Raises:
            ValueError: If JSON parsing fails
        """
        try:
            # Extract JSON from response (LLM might add extra text)
            json_match = re.search(r"\{.*\}", llm_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = llm_response

            # Fix common JSON issues
            json_str = json_str.replace("'", '"')  # Single quotes -> double quotes
            json_str = re.sub(r",\s*}", "}", json_str)  # Remove trailing commas
            json_str = re.sub(r",\s*]", "]", json_str)  # Remove trailing commas in arrays

            data = json.loads(json_str)

            # Create Intent from parsed data
            intent = Intent(
                type=data.get("type", "QUERY"),
                domain=data.get("domain", "health"),
                complexity=data.get("complexity", "simple"),
                specialist_type=data.get("specialist_type", "nutritionist"),
                confidence=float(data.get("confidence", 0.8)),
                entities=data.get("entities", []),
            )
            return intent
        except (json.JSONDecodeError, KeyError, ValueError):
            # Fallback: Return default intent if parsing fails
            return Intent(
                type="QUERY",
                domain="health",
                complexity="simple",
                specialist_type="nutritionist",
                confidence=0.5,
                entities=[],
            )

    def _determine_routing(self, intent: Intent) -> str:
        """
        Determine routing path (PATH1 vs PATH2) based on intent.

        Routing logic:
        - specialist_type == "orchestrator" → PATH2 (always)
        - complexity == "multi_step" → PATH2
        - complexity == "simple" → PATH1

        Args:
            intent: Classified intent

        Returns:
            "PATH1" or "PATH2"
        """
        # Check specialist first (orchestrator always goes to PATH2)
        if intent.specialist_type == "orchestrator":
            return "PATH2"
        # Then check complexity
        elif intent.complexity == "multi_step":
            return "PATH2"
        elif intent.complexity == "simple":
            return "PATH1"
        else:
            return "PATH1"

    def generate_response(
        self, user_message: str, intent: Intent, context: ConversationState
    ) -> str:
        """
        Generate reactive response: "{empathy}. {action}." or just empathy for casual chat

        Args:
            user_message: User's message
            intent: Classified intent
            context: Conversation state

        Returns:
            Reactive response text

        Example:
            "That's sad to hear. Looping in nutritionist."
            "Hello! Nice to hear from you." (for casual greetings)
        """
        # For general conversation: Just empathy, no specialist action
        if intent.domain == "general":
            emotion_result = self.emotion_detector.detect(user_message)
            emotion = str(emotion_result["label"])
            empathy = self.empathy_generator.generate(user_message, emotion)
            return empathy

        # For specialist queries: Detect emotion
        emotion_result = self.emotion_detector.detect(user_message)
        emotion = str(emotion_result["label"])

        # Generate empathy
        empathy = self.empathy_generator.generate(user_message, emotion)

        # Get action declaration
        action = self._declare_action(intent, user_message)

        # Format response
        response = self._format_response(empathy, action)

        return response

    def _declare_action(self, intent: Intent, user_message: str) -> str:
        """
        Generate natural action declaration using LLM.

        No templates - generates contextual action phrases that sound natural.

        Args:
            intent: Classified intent
            user_message: User's original message

        Returns:
            Natural action declaration text
        """
        specialist = intent.specialist_type

        prompt = f"""You are generating a brief action announcement for a conversational AI assistant.

The user's query: "{user_message}"
Specialist being activated: {specialist}

Generate a brief (3-8 words), natural announcement that:
- Explains what you're doing without engineering jargon
- Sounds conversational, not robotic
- References the user's actual need

Examples of GOOD announcements:
- User asks about diet → "Let me analyze your diet patterns"
- User feels anxious → "Let me explore what's behind this with you"
- User needs budget help → "Let me look into your spending trends"

Examples of BAD announcements (avoid these):
- "Looping in nutritionist" (engineering jargon)
- "Connecting you with psychiatrist" (sounds like a call center)
- "Creating a plan for you" (too generic)

Generate brief action announcement:"""

        try:
            response = self.llm_client.generate(prompt, model_profile="creative")
            action = response.strip().strip('"').strip("'").rstrip(".!?")
            return action if action else "Let me look into this for you"
        except Exception:
            return "Let me look into this for you"

    def _format_response(self, empathy: str, action: str) -> str:
        """
        Format reactive response: "{empathy}. {action}."

        Args:
            empathy: Empathy text
            action: Action declaration

        Returns:
            Formatted response
        """
        # Ensure empathy doesn't end with punctuation (we'll add period)
        empathy = empathy.rstrip(".!?")

        # Ensure action doesn't end with punctuation
        action = action.rstrip(".!?")

        # Format: "{empathy}. {action}."
        return f"{empathy}. {action}."
