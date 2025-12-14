"""
Emotion Engine - Detects user emotional state and generates appropriate tone.

TOPIC 2: EMOTION & EMPATHY LAYER

This engine analyzes user messages for emotional context and provides tone guidance
to make the conversational response empathetic and emotionally appropriate.

Key Features:
- Detects sentiment: happy, sad, frustrated, anxious, neutral
- Measures intensity (0.0-1.0 scale)
- Selects appropriate tone mode: supportive, playful, concerned, analytical
- Generates empathy phrases ("ugh that sucks", "yay awesome!", etc.)
- Provides tone instructions for LLM-based response generation
"""

import json
from dataclasses import dataclass
from typing import Literal, Optional

from backend.services.llm_client import LLMClient


@dataclass
class EmotionContext:
    """Context from emotion analysis - used to guide response generation"""

    sentiment: Literal["happy", "sad", "frustrated", "anxious", "neutral"]
    intensity: float  # 0.0-1.0 scale
    tone_mode: Literal["supportive", "playful", "concerned", "analytical"]
    empathy_phrase: str  # 2-4 word empathy response


class EmotionEngine:
    """
    LLM-based emotion detection and tone guidance.

    Uses Groq API to analyze user messages and determine emotional context,
    then provides tone instructions for natural, empathetic responses.
    """

    def __init__(self, llm_client: LLMClient):
        """
        Initialize emotion engine with LLM client.

        Args:
            llm_client: LLMClient instance for Groq API access
        """
        self.llm_client = llm_client

    async def analyze_emotion(
        self, message: str, conversation_history: Optional[list] = None
    ) -> EmotionContext:
        """
        Detect user emotion using LLM analysis.

        Uses the Groq LLM to analyze the emotional tone of the user's message,
        considering recent conversation history for context.

        Args:
            message: User's message to analyze
            conversation_history: Optional list of recent conversation messages

        Returns:
            EmotionContext with detected sentiment, intensity, tone, and empathy phrase
        """
        # Build context from recent history
        context_text = "None"
        if conversation_history and len(conversation_history) > 0:
            # Get last 3 messages for context
            recent = (
                conversation_history[-3:]
                if len(conversation_history) >= 3
                else conversation_history
            )
            context_text = str(recent)

        # Prompt for LLM-based emotion analysis
        prompt = f"""Analyze emotional tone of user message. Be precise and accurate.

User message: "{message}"

Recent context: {context_text}

Return VALID JSON (no markdown, no code blocks, just pure JSON):
{{
    "sentiment": "happy|sad|frustrated|anxious|neutral",
    "intensity": 0.0-1.0,
    "tone_mode": "supportive|playful|concerned|analytical",
    "empathy_phrase": "2-4 word short empathy response"
}}

Analysis Examples:
1. "ugh still hurts" → {{"sentiment": "frustrated", "intensity": 0.7, "tone_mode": "concerned", "empathy_phrase": "ugh that sucks"}}
2. "yay better!" → {{"sentiment": "happy", "intensity": 0.8, "tone_mode": "playful", "empathy_phrase": "yay awesome"}}
3. "not sure if it's working" → {{"sentiment": "anxious", "intensity": 0.6, "tone_mode": "supportive", "empathy_phrase": "hmm I get it"}}
4. "thanks for asking" → {{"sentiment": "happy", "intensity": 0.5, "tone_mode": "playful", "empathy_phrase": "happy to help"}}
5. "nothing worked again" → {{"sentiment": "sad", "intensity": 0.8, "tone_mode": "supportive", "empathy_phrase": "oh that's tough"}}

Rules:
- intensity: 0.0 (not at all), 0.5 (moderate), 1.0 (very intense)
- tone_mode: match the emotional state appropriately
- empathy_phrase: casual, natural 2-4 words
- Return ONLY the JSON, no explanation

JSON:"""

        response = await self.llm_client.generate_async(
            prompt, model_profile="creative", max_tokens=100
        )

        # Parse JSON response
        try:
            response_clean = response.strip()
            # Remove markdown code blocks if present
            if response_clean.startswith("```"):
                response_clean = response_clean.split("```")[1]
                if response_clean.startswith("json"):
                    response_clean = response_clean[4:]
                response_clean = response_clean.strip()

            emotion_data = json.loads(response_clean)

            return EmotionContext(
                sentiment=emotion_data.get("sentiment", "neutral"),
                intensity=float(emotion_data.get("intensity", 0.5)),
                tone_mode=emotion_data.get("tone_mode", "analytical"),
                empathy_phrase=emotion_data.get("empathy_phrase", "okay"),
            )
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            # Fallback to neutral if parsing fails
            print(f"Emotion parsing error: {e}, response: {response}")
            return EmotionContext(
                sentiment="neutral",
                intensity=0.5,
                tone_mode="analytical",
                empathy_phrase="okay",
            )

    def get_tone_instructions(self, emotion: EmotionContext) -> str:
        """
        Generate LLM prompt instructions based on detected emotion.

        Returns text that should be prepended to the LLM prompt for response
        generation, guiding the model to match the user's emotional state.

        Args:
            emotion: EmotionContext from analyze_emotion()

        Returns:
            String with tone instructions for LLM prompt
        """
        # Detailed tone guides for each mode
        tone_guides = {
            "supportive": (
                "Use warm, encouraging language. Show genuine care. "
                "Validate their feelings. Be gentle but direct."
            ),
            "playful": (
                "Be light and friendly. Use casual language. "
                "Keep things fun and approachable. Avoid heavy topics."
            ),
            "concerned": (
                "Show genuine care and empathy. Be direct but kind. "
                "Acknowledge their difficulty. Take their concern seriously."
            ),
            "analytical": (
                "Be clear and informative. Stay calm and objective. "
                "Focus on facts and logic. Explain your reasoning."
            ),
        }

        tone_text = tone_guides.get(emotion.tone_mode, tone_guides["analytical"])

        return f"""EMOTIONAL CONTEXT:
User emotion: {emotion.sentiment} (intensity: {emotion.intensity:.1f}/1.0)
Tone mode: {emotion.tone_mode}

TONE GUIDANCE:
{tone_text}

EMPATHY REQUIREMENT:
Start with empathy: "{emotion.empathy_phrase}" (or similar natural response)
Then provide your actual response.

RULES:
- Use contractions ("you're", "it's", "gonna")
- Keep it SHORT (1-2 sentences max)
- NO formal phrases ("I understand", "I hear you", "Let me help")
- Sound natural and human
- Match their energy level"""
