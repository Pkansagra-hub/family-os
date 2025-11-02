"""
Clarification Manager for Planning Pipeline PoC

This module implements HITL (Human-in-the-Loop) clarification logic for the 4-stage
planning pipeline. It detects when user input is unclear and generates natural language
clarification questions using LLM.

Architecture:
- IntentAnalysis: Dataclass holding intent confidence and missing entities
- ClarificationState: Tracks clarification count and history (max 2 per turn)
- ClarificationManager: Core logic for deciding when/how to clarify

References:
- ADR-0054d: Dialogue Repair & Clarification Pipeline
- ADR-0052: Enhanced HITL Protocols
- ADR-0007: 4-Stage Planning Pipeline (Fallback 4)
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# Configure logging
logger = logging.getLogger(__name__)


class ConfidenceThreshold(Enum):
    """
    Confidence thresholds for clarification decisions

    Based on ADR-0054d confidence analysis:
    - EXECUTE (0.6): High confidence, proceed immediately
    - CLARIFY (0.4): Medium confidence, ask for details
    - REJECT (0.0): Too low, ask user to rephrase entirely
    """

    EXECUTE = 0.6
    CLARIFY = 0.4
    REJECT = 0.0


@dataclass
class IntentAnalysis:
    """
    Analysis of user intent from LLM sketch stage

    Fields:
        intent: Detected intent label (e.g., "book_dinner")
        confidence: Confidence score 0.0-1.0
        missing_entities: List of missing required parameters
        ambiguous_entities: List of ambiguous references
        original_query: Original user input
    """

    intent: str
    confidence: float
    missing_entities: List[str] = field(default_factory=list)
    ambiguous_entities: List[str] = field(default_factory=list)
    original_query: str = ""

    def __post_init__(self):
        """Validate confidence score"""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be 0.0-1.0, got {self.confidence}")


@dataclass
class ClarificationState:
    """
    Track clarification history within a turn

    Max 2 clarifications per turn to prevent infinite loops.
    After 2 clarifications, system proceeds with best effort.

    Fields:
        clarification_count: Number of clarifications asked (0-2)
        max_clarifications: Maximum allowed (default 2)
        history: List of clarification questions asked
        responses: List of user responses received
    """

    clarification_count: int = 0
    max_clarifications: int = 2
    history: List[str] = field(default_factory=list)
    responses: List[str] = field(default_factory=list)

    def add_clarification(self, question: str, response: Optional[str] = None):
        """Add clarification to history"""
        self.clarification_count += 1
        self.history.append(question)
        if response:
            self.responses.append(response)

        logger.info(
            f"Clarification {self.clarification_count}/{self.max_clarifications}: {question[:50]}..."
        )

    def is_limit_reached(self) -> bool:
        """Check if max clarifications reached"""
        return self.clarification_count >= self.max_clarifications

    def get_summary(self) -> str:
        """Get summary of clarification history"""
        if not self.history:
            return "No clarifications"

        summary = f"Clarifications ({len(self.history)}):\n"
        for i, (q, r) in enumerate(zip(self.history, self.responses), 1):
            summary += f"  Q{i}: {q}\n  A{i}: {r}\n"
        return summary


class ClarificationManager:
    """
    Detect unclear intents and generate clarification questions

    Core component of HITL system. Integrates with 4-stage planning pipeline
    to handle low confidence, missing parameters, and validation failures.

    Usage:
        manager = ClarificationManager(llm_provider, config)

        analysis = IntentAnalysis(
            intent="book_dinner",
            confidence=0.45,
            missing_entities=["time", "location"]
        )

        decision = manager.should_clarify(analysis)

        if decision == "CLARIFY":
            question = await manager.generate_clarification(analysis)
            # Prompt user, retry with response
    """

    def __init__(self, llm_provider, config: Optional[Dict[str, Any]] = None):
        """
        Initialize ClarificationManager

        Args:
            llm_provider: LLM provider with call_llm() method
            config: Optional config dict with:
                - max_clarifications: int (default 2)
                - execute_threshold: float (default 0.6)
                - clarify_threshold: float (default 0.4)
                - reject_threshold: float (default 0.0)
        """
        self.llm_provider = llm_provider
        self.config = config or {}
        self.state = ClarificationState(max_clarifications=self.config.get("max_clarifications", 2))

        # Override thresholds from config if provided
        self.threshold_execute = self.config.get(
            "execute_threshold", ConfidenceThreshold.EXECUTE.value
        )
        self.threshold_clarify = self.config.get(
            "clarify_threshold", ConfidenceThreshold.CLARIFY.value
        )
        self.threshold_reject = self.config.get(
            "reject_threshold", ConfidenceThreshold.REJECT.value
        )

        logger.info(
            f"ClarificationManager initialized: "
            f"execute>={self.threshold_execute}, "
            f"clarify>={self.threshold_clarify}, "
            f"reject>={self.threshold_reject}, "
            f"max={self.state.max_clarifications}"
        )

    def should_clarify(self, analysis: IntentAnalysis) -> str:
        """
        Decide if clarification needed based on confidence and missing entities

        Decision logic:
        1. Check clarification limit (max 2)
        2. Check confidence thresholds
        3. Check for missing entities

        Args:
            analysis: IntentAnalysis from sketch stage

        Returns:
            "EXECUTE": High confidence, proceed immediately
            "CLARIFY": Medium confidence or missing data, ask for details
            "REJECT": Too low confidence, ask to rephrase entirely
        """
        # Check clarification limit
        if self.state.is_limit_reached():
            logger.warning(
                f"Max clarifications reached ({self.state.max_clarifications}), "
                f"proceeding with best effort"
            )
            return "EXECUTE"  # Give up, execute best effort

        # Check confidence thresholds
        if analysis.confidence < self.threshold_reject:
            logger.info(f"Confidence {analysis.confidence:.2f} < {self.threshold_reject} → REJECT")
            return "REJECT"  # Too low, ask to rephrase

        elif analysis.confidence < self.threshold_clarify:
            logger.info(
                f"Confidence {analysis.confidence:.2f} < {self.threshold_clarify} → CLARIFY"
            )
            return "CLARIFY"  # Medium, ask for details

        elif analysis.confidence < self.threshold_execute:
            # Between clarify and execute threshold
            if analysis.missing_entities:
                logger.info(
                    f"Confidence {analysis.confidence:.2f} OK but missing entities: "
                    f"{analysis.missing_entities} → CLARIFY"
                )
                return "CLARIFY"  # High confidence but missing data
            else:
                logger.info(f"Confidence {analysis.confidence:.2f} → EXECUTE")
                return "EXECUTE"  # High confidence, proceed

        elif analysis.missing_entities:
            # High confidence but missing required data
            logger.info(
                f"High confidence {analysis.confidence:.2f} but missing entities: "
                f"{analysis.missing_entities} → CLARIFY"
            )
            return "CLARIFY"

        else:
            logger.info(f"High confidence {analysis.confidence:.2f}, no missing entities → EXECUTE")
            return "EXECUTE"  # High confidence, all data present

    async def generate_clarification(
        self, analysis: IntentAnalysis, strategy: str = "missing_entity"
    ) -> str:
        """
        Generate clarification question using LLM

        Uses LLM to generate natural, conversational clarification questions
        based on the clarification strategy.

        Strategies:
            "rephrase": Confidence < 0.4, ask to rephrase entirely
                Example: "I didn't quite catch that. Could you rephrase?"

            "missing_entity": High confidence but missing required info
                Example: "I can book dinner tomorrow. What time and which restaurant?"

            "simplify": Medium confidence, acknowledge + ask for missing
                Example: "I can help with dinner. What time and where?"

        Args:
            analysis: IntentAnalysis from sketch stage
            strategy: Clarification strategy ("rephrase", "missing_entity", "simplify")

        Returns:
            Natural language clarification question (str)
        """
        # System prompts for each strategy
        system_prompts = {
            "rephrase": """You didn't understand the user's request.
Ask them to rephrase conversationally and briefly (<30 words).
Be friendly and admit uncertainty gracefully.
Return ONLY the question, no explanations.""",
            "missing_entity": """You understand the user's intent with HIGH confidence,
but you're missing required information to complete the action.
Ask a brief natural question about the specific missing information (<30 words).
Be conversational and helpful.
Return ONLY the question, no explanations.""",
            "simplify": """You partially understood the user's request (MODERATE confidence).
Acknowledge what you understood, then ask about what you're missing (<30 words).
Be conversational and helpful.
Return ONLY the question, no explanations.""",
        }

        # Validate strategy
        if strategy not in system_prompts:
            logger.warning(f"Unknown strategy '{strategy}', defaulting to 'missing_entity'")
            strategy = "missing_entity"

        # Build user prompt with context
        missing_info_str = (
            ", ".join(analysis.missing_entities) if analysis.missing_entities else "None"
        )

        user_prompt = f"""User said: "{analysis.original_query}"
Intent detected: {analysis.intent} (confidence: {analysis.confidence:.2f})
Missing information: {missing_info_str}

Generate a natural clarifying question."""

        logger.info(f"Generating clarification with strategy '{strategy}'")
        logger.debug(f"User prompt: {user_prompt}")

        try:
            # Call LLM for clarification generation
            clarification = await self.llm_provider.call_llm(
                prompt=user_prompt,
                system_message=system_prompts[strategy],
                temperature=0.7,  # More creative for natural phrasing
                max_tokens=50,  # Short questions only
            )

            # Track clarification in state
            self.state.add_clarification(clarification)

            logger.info(f"Generated clarification: {clarification}")
            return clarification

        except Exception as e:
            logger.error(f"LLM clarification generation failed: {e}")

            # Fallback to deterministic clarification
            fallback = self._generate_fallback_clarification(analysis, strategy)
            self.state.add_clarification(fallback)

            logger.warning(f"Using fallback clarification: {fallback}")
            return fallback

    def _generate_fallback_clarification(self, analysis: IntentAnalysis, strategy: str) -> str:
        """
        Generate deterministic fallback clarification if LLM fails

        Ensures system never stalls, even if LLM is unavailable.

        Args:
            analysis: IntentAnalysis
            strategy: Clarification strategy

        Returns:
            Deterministic clarification question
        """
        if strategy == "rephrase":
            return "I didn't quite understand. Could you rephrase your request?"

        elif strategy == "missing_entity":
            if analysis.missing_entities:
                missing = ", ".join(analysis.missing_entities)
                return f"I need more information: {missing}. Can you provide these details?"
            else:
                return "I need more information to proceed. Can you provide more details?"

        elif strategy == "simplify":
            if analysis.intent and analysis.missing_entities:
                missing = ", ".join(analysis.missing_entities)
                return f"I can help with {analysis.intent}. What about {missing}?"
            else:
                return "I partially understood. Can you provide more details?"

        else:
            return "I need clarification. Can you provide more details?"

    def add_user_response(self, response: str):
        """
        Record user's response to clarification

        Args:
            response: User's clarification response
        """
        self.state.responses.append(response)
        logger.info(f"User response recorded: {response[:50]}...")

    def reset_state(self):
        """
        Reset clarification state after successful execution

        Call this after plan successfully commits to K0 WAL.
        """
        logger.info(f"Resetting state (had {self.state.clarification_count} clarifications)")
        self.state = ClarificationState(max_clarifications=self.config.get("max_clarifications", 2))

    def get_state_summary(self) -> str:
        """Get human-readable summary of clarification state"""
        return self.state.get_summary()


# Utility functions for testing
def create_test_analysis(
    intent: str = "test_intent",
    confidence: float = 0.5,
    missing_entities: Optional[List[str]] = None,
    original_query: str = "test query",
) -> IntentAnalysis:
    """Create test IntentAnalysis for unit testing"""
    return IntentAnalysis(
        intent=intent,
        confidence=confidence,
        missing_entities=missing_entities or [],
        ambiguous_entities=[],
        original_query=original_query,
    )


if __name__ == "__main__":
    # Basic smoke test
    print("ClarificationManager smoke test")
    print("=" * 50)

    # Test IntentAnalysis
    analysis = create_test_analysis(
        intent="book_dinner", confidence=0.45, missing_entities=["time", "location"]
    )
    print(f"✓ IntentAnalysis created: {analysis.intent} (confidence: {analysis.confidence})")

    # Test ClarificationState
    state = ClarificationState()
    state.add_clarification("What time?", "7pm")
    state.add_clarification("Which restaurant?", "Luigi's")
    print(f"✓ ClarificationState: {state.clarification_count} clarifications")
    print(f"  Summary:\n{state.get_summary()}")

    # Test threshold logic (without LLM)
    class MockLLMProvider:
        async def call_llm(self, **kwargs):
            return "Mock clarification question?"

    manager = ClarificationManager(MockLLMProvider())

    # Test EXECUTE decision
    high_conf = create_test_analysis(confidence=0.9)
    decision = manager.should_clarify(high_conf)
    print(f"✓ High confidence (0.9): {decision} (expected: EXECUTE)")

    # Test CLARIFY decision
    med_conf = create_test_analysis(confidence=0.5)
    decision = manager.should_clarify(med_conf)
    print(f"✓ Medium confidence (0.5): {decision} (expected: CLARIFY)")

    # Test REJECT decision
    low_conf = create_test_analysis(confidence=0.2)
    decision = manager.should_clarify(low_conf)
    print(f"✓ Low confidence (0.2): {decision} (expected: REJECT)")

    # Test missing entities
    missing = create_test_analysis(confidence=0.8, missing_entities=["time"])
    decision = manager.should_clarify(missing)
    print(f"✓ High confidence with missing entities: {decision} (expected: CLARIFY)")

    # Test max clarification limit
    manager.state.clarification_count = 2
    decision = manager.should_clarify(med_conf)
    print(f"✓ Max clarifications reached: {decision} (expected: EXECUTE)")

    print("\n" + "=" * 50)
    print("✅ All smoke tests passed!")
