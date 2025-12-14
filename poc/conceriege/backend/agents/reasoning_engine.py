"""
Reasoning Engine - Human Reasoning Markers & Uncertainty Expression

TOPIC 7: HUMAN REASONING

This module adds uncertainty markers, reasoning process visibility, and
causal language to make responses feel more human and less robotic.

Key Features:
- Detects message complexity and response confidence
- Selects appropriate reasoning style (uncertain, cautious, confident)
- Injects uncertainty markers based on confidence level
- Shows reasoning process: "hmm let me think", "I was comparing", "based on"
- Admits limitations: "can't know for sure", "would need more info"
- Uses causal phrasing: "that makes sense because", "probably due to"

Confidence-based variation:
- High (>0.8): Direct language, minimal hedging
- Medium (0.6-0.8): Cautious markers, "seems like", "probably"
- Low (<0.6): Uncertain markers, "not sure", "possibly", "might be"
"""

import json
from dataclasses import dataclass
from typing import Literal, Optional

from backend.services.llm_client import LLMClient


@dataclass
class ReasoningContext:
    """Context for human-like reasoning display"""

    confidence: float  # 0.0-1.0: how confident the response is
    reasoning_style: Literal["uncertain", "cautious", "confident"]
    """Style based on confidence: uncertain (<0.6), cautious (0.6-0.8), confident (>0.8)"""

    has_causal_link: bool = False
    """Does this response explain 'why' or 'how'?"""

    has_question: bool = False
    """Does the message ask a question?"""


class ReasoningEngine:
    """
    LLM or RULE-BASED reasoning confidence detection.

    Uses either LLM analysis or fast rule-based heuristics to detect
    how confident the response should be, then injects appropriate
    uncertainty markers and reasoning language.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        """
        Initialize reasoning engine.

        Args:
            llm_client: Optional LLMClient for LLM-based confidence detection
        """
        self.llm_client = llm_client

        # ====================================================================
        # TOPIC 7: REASONING MARKERS - Categories of uncertainty/reasoning
        # ====================================================================

        self.REASONING_MARKERS = {
            # Explicit uncertainty and hedging
            "uncertainty": [
                "not totally sure but",
                "might be",
                "possibly",
                "could be",
                "seems like",
                "I think",
                "appears to be",
                "looks like it could be",
                "I'm not 100% certain but",
                "best guess is",
                "if I had to guess",
                "not entirely sure",
            ],
            # Showing thinking/reasoning process
            "process": [
                "hmm let me think",
                "I was comparing",
                "looking at this",
                "based on what I see",
                "checking the pattern",
                "from what I can tell",
                "the way I see it",
                "examining the data",
                "thinking it through",
            ],
            # Causal/explanatory language
            "causal": [
                "that makes sense because",
                "probably due to",
                "likely caused by",
                "happens when",
                "usually means",
                "the reason being",
                "which explains",
                "so that would mean",
            ],
            # Admitting limitations
            "limitations": [
                "can't know for sure",
                "hard to say without more info",
                "would need more data",
                "based on limited information",
                "only seeing part of the picture",
                "might be missing something",
                "there's a chance I'm wrong",
                "could be other factors",
            ],
            # UPGRADE #4: Conversational Repair - Fix mistakes gracefully
            "repair": [
                "I might be off — want me to recheck?",
                "wait, let me reconsider that",
                "actually, thinking about it more",
                "hmm, that doesn't quite add up",
                "does that line up with what you feel?",
                "I may have missed something there",
                "let me double-check that logic",
                "hold on, I want to revisit that",
            ],
        }

    def estimate_confidence(
        self, message: str, conversation_history: Optional[list] = None
    ) -> float:
        """
        Estimate confidence level using fast RULE-BASED heuristics.

        FAST method: <5ms, no LLM calls

        Args:
            message: User message to analyze
            conversation_history: Optional conversation history

        Returns:
            Confidence score 0.0-1.0
        """
        confidence = 0.7  # Default neutral confidence

        # Reduce confidence if message is a question
        if "?" in message:
            confidence -= 0.2

        # Reduce confidence if message uses uncertainty markers
        uncertainty_words = ["maybe", "might", "not sure", "unsure", "possibly", "could"]
        if any(word in message.lower() for word in uncertainty_words):
            confidence -= 0.15

        # Increase confidence if message uses certainty markers
        certainty_words = ["definitely", "sure", "certain", "absolutely", "for sure", "clearly"]
        if any(word in message.lower() for word in certainty_words):
            confidence += 0.2

        # Reduce confidence if message is very short (incomplete thoughts)
        if len(message.split()) < 3:
            confidence -= 0.1

        # Increase confidence if message is detailed and specific
        if len(message.split()) > 15:
            confidence += 0.1

        # Clamp to 0.0-1.0
        return max(0.0, min(1.0, confidence))

    async def analyze_confidence(
        self, message: str, conversation_history: Optional[list] = None, use_llm: bool = False
    ) -> ReasoningContext:
        """
        Analyze message to determine reasoning context.

        Can use either RULE-BASED (fast) or LLM (accurate) analysis.

        Args:
            message: User message to analyze
            conversation_history: Optional conversation history
            use_llm: If True, use LLM; if False, use fast rule-based

        Returns:
            ReasoningContext with confidence and reasoning style
        """
        if use_llm and self.llm_client:
            return await self._analyze_confidence_llm(message, conversation_history)
        else:
            return self._analyze_confidence_rulebased(message, conversation_history)

    def _analyze_confidence_rulebased(
        self, message: str, conversation_history: Optional[list] = None
    ) -> ReasoningContext:
        """RULE-BASED confidence analysis - fast (<5ms)"""

        confidence = self.estimate_confidence(message, conversation_history)

        # Determine reasoning style based on confidence
        if confidence < 0.6:
            reasoning_style = "uncertain"
        elif confidence < 0.8:
            reasoning_style = "cautious"
        else:
            reasoning_style = "confident"

        # Detect if message asks a question or seeks causal understanding
        has_question = "?" in message
        has_causal = any(
            word in message.lower() for word in ["why", "how", "because", "cause", "reason", "what"]
        )

        return ReasoningContext(
            confidence=confidence,
            reasoning_style=reasoning_style,
            has_causal_link=has_causal,
            has_question=has_question,
        )

    async def _analyze_confidence_llm(
        self, message: str, conversation_history: Optional[list] = None
    ) -> ReasoningContext:
        """LLM-based confidence analysis - accurate but slower"""

        context_text = "None"
        if conversation_history and len(conversation_history) > 0:
            recent = (
                conversation_history[-2:]
                if len(conversation_history) >= 2
                else conversation_history
            )
            context_text = str(recent)

        prompt = f"""Analyze message to determine response confidence needed.

User message: "{message}"

Recent context: {context_text}

Return VALID JSON (no markdown):
{{
    "confidence": 0.0-1.0,
    "reasoning_style": "uncertain|cautious|confident",
    "has_causal_link": true/false,
    "has_question": true/false
}}

Guidance:
- confidence: 0.0 (very uncertain), 0.5 (neutral), 1.0 (very confident)
- reasoning_style: uncertain (<0.6), cautious (0.6-0.8), confident (>0.8)
- has_causal_link: True if asking why/how/explaining
- has_question: True if message contains question

Examples:
1. "maybe coffee affects my sleep?" → {{"confidence": 0.5, "reasoning_style": "cautious", "has_causal_link": true, "has_question": true}}
2. "coffee definitely makes me sleep bad" → {{"confidence": 0.9, "reasoning_style": "confident", "has_causal_link": true, "has_question": false}}
3. "not sure" → {{"confidence": 0.3, "reasoning_style": "uncertain", "has_causal_link": false, "has_question": false}}

Return ONLY JSON:"""

        response = await self.llm_client.generate_async(
            prompt, model_profile="creative", max_tokens=100
        )

        try:
            response_clean = response.strip()
            if response_clean.startswith("```"):
                response_clean = response_clean.split("```")[1]
                if response_clean.startswith("json"):
                    response_clean = response_clean[4:]
                response_clean = response_clean.strip()

            data = json.loads(response_clean)

            return ReasoningContext(
                confidence=float(data.get("confidence", 0.7)),
                reasoning_style=data.get("reasoning_style", "cautious"),
                has_causal_link=bool(data.get("has_causal_link", False)),
                has_question=bool(data.get("has_question", False)),
            )
        except (json.JSONDecodeError, ValueError, TypeError):
            # Fallback to rule-based
            return self._analyze_confidence_rulebased(message, conversation_history)

    def get_reasoning_instructions(
        self, confidence: float, has_causal_link: bool = False, has_question: bool = False
    ) -> str:
        """
        Generate reasoning instructions for LLM prompt.

        Uses confidence level to select appropriate uncertainty markers and
        reasoning language that makes the response feel more human.

        Args:
            confidence: Confidence score 0.0-1.0
            has_causal_link: Whether response should explain 'why'
            has_question: Whether original message was a question

        Returns:
            String with reasoning instructions for LLM prompt
        """

        # Determine reasoning style from confidence
        if confidence < 0.6:
            style = "uncertain"
            style_desc = "UNCERTAIN - Show thinking process, express doubt"
        elif confidence < 0.8:
            style = "cautious"
            style_desc = "CAUTIOUS - Hedge slightly, use softer language"
        else:
            style = "confident"
            style_desc = "CONFIDENT - Be direct but still show reasoning"

        # Build marker examples based on style
        if style == "uncertain":
            uncertainty_examples = ", ".join(self.REASONING_MARKERS["uncertainty"][:3])
            limitations_examples = ", ".join(self.REASONING_MARKERS["limitations"][:2])
            marker_guide = f"""Use uncertainty markers regularly:
Examples: {uncertainty_examples}, ...

Acknowledge limitations:
Examples: {limitations_examples}, ..."""

        elif style == "cautious":
            uncertainty_examples = ", ".join(self.REASONING_MARKERS["uncertainty"][3:6])
            causal_examples = ", ".join(self.REASONING_MARKERS["causal"][:2])
            marker_guide = f"""Use some uncertainty:
Examples: {uncertainty_examples}, ...

Explain causality:
Examples: {causal_examples}, ..."""

        else:  # confident
            causal_examples = ", ".join(self.REASONING_MARKERS["causal"][:3])
            process_examples = ", ".join(self.REASONING_MARKERS["process"][:2])
            marker_guide = f"""Show your reasoning without excessive hedging:
Examples: {causal_examples}, {process_examples}, ..."""

        # Add causal guidance if relevant
        causal_guidance = ""
        if has_causal_link:
            causal_guidance = f"""
EXPLAIN CAUSALITY:
Show cause-effect relationship. Use phrases like: "{self.REASONING_MARKERS['causal'][0]}", "{self.REASONING_MARKERS['causal'][1]}"
"""

        # Add question handling
        question_guidance = ""
        if has_question:
            question_guidance = """
ANSWERING QUESTION:
First acknowledge the question, then provide your reasoning. Show thinking process."""

        return f"""TOPIC 7: HUMAN REASONING - REASONING STYLE: {style.upper()}

Confidence level: {confidence:.1f}/1.0
{style_desc}

{marker_guide}
{causal_guidance}{question_guidance}

INSTRUCTIONS:
1. Show your thinking process occasionally: "hmm", "let me think about", "looking at this"
2. Use causal/explanatory language to connect ideas
3. Express uncertainty when appropriate - don't over-explain
4. Admit limitations: "can't know for sure", "would need more info"
5. Mix certainty with humility - be direct but not overconfident

CRITICAL: Sound human, not robotic. Vary your phrasing."""

    def select_markers_for_style(
        self, reasoning_style: Literal["uncertain", "cautious", "confident"]
    ) -> dict:
        """
        Select appropriate reasoning markers for a given style.

        Args:
            reasoning_style: "uncertain", "cautious", or "confident"

        Returns:
            Dict of marker categories with examples for this style
        """

        if reasoning_style == "uncertain":
            return {
                "primary": self.REASONING_MARKERS["uncertainty"][:4],
                "secondary": self.REASONING_MARKERS["limitations"][:3],
                "process": self.REASONING_MARKERS["process"][:2],
            }

        elif reasoning_style == "cautious":
            return {
                "primary": self.REASONING_MARKERS["uncertainty"][3:7],
                "secondary": self.REASONING_MARKERS["causal"][:2],
                "process": self.REASONING_MARKERS["process"][2:4],
            }

        else:  # confident
            return {
                "primary": self.REASONING_MARKERS["causal"][:3],
                "secondary": self.REASONING_MARKERS["process"][:3],
                "process": [],
            }
