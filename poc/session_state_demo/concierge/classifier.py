"""
Intent Classifier
=================

Heuristic-based intent classification for the Concierge FSM.

Classifies user input into:
- Intent type (greeting, question, request, etc.)
- Complexity tier (LOW, MEDIUM, HIGH)
- Confidence score

Reference: k1_cognitive_architecture_skeleton.mmd
- ULTRABERT_INTENT: Intent Head (simplified to heuristics for POC)
- COMPLEXITY_CLASSIFIER: Tier assignment
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from poc.session_state_demo.concierge.gap_detector import GapDetector
from poc.session_state_demo.concierge.states import (
    ClassificationResult,
    ComplexityTier,
    Gap,
    IntentType,
)

# =============================================================================
# INTENT PATTERNS
# =============================================================================


@dataclass
class IntentPattern:
    """Pattern for intent detection."""

    intent: IntentType
    patterns: List[str]
    priority: int = 1  # Higher = checked first
    complexity_hint: ComplexityTier = ComplexityTier.LOW


# Patterns for each intent type
INTENT_PATTERNS: List[IntentPattern] = [
    # Requests - user wants action taken (HIGH PRIORITY - check first!)
    # These override greetings when message contains both
    IntentPattern(
        intent=IntentType.REQUEST,
        patterns=[
            r"\b(remind|set|schedule|book|order|buy|call|text|email|send|create|add|save)\b",
            r"\b(can you|could you|would you|please)\b",
            r"\b(i need|i want|i'd like|help me|planning|plan)\b",
            r"\b(surprise|birthday|anniversary|wedding|party|event)\b.*\b(plan|help|arrange)\b",
        ],
        priority=10,  # Highest - requests should override greetings
        complexity_hint=ComplexityTier.MEDIUM,
    ),
    # Greetings - ONLY match if it's a SHORT pure greeting
    # Don't match "Hey, I need help planning..." - that's a request with a greeting prefix
    IntentPattern(
        intent=IntentType.GREETING,
        patterns=[
            r"^(hi|hello|hey|good\s+(morning|afternoon|evening)|howdy|sup)[!.,]?\s*$",  # Pure greeting only
            r"^(what'?s\s+up|how\s+are\s+you|how'?s\s+it\s+going)[!?.,]?\s*$",  # Pure greeting only
        ],
        priority=5,  # Lower priority - real content takes precedence
        complexity_hint=ComplexityTier.LOW,
    ),
    # Clarification response - user answering our question
    IntentPattern(
        intent=IntentType.CLARIFICATION_RESPONSE,
        patterns=[
            r"^(yes|no|yeah|nope|sure|okay|ok|yep|nah)\b",
            r"^(at\s+)?\d{1,2}(:\d{2})?\s*(am|pm|AM|PM)?\b",  # Time response
            r"^(tomorrow|today|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
            r"^\d+\s*$",  # Just a number
        ],
        priority=9,
        complexity_hint=ComplexityTier.LOW,
    ),
    # Questions - user asking for information
    IntentPattern(
        intent=IntentType.QUESTION,
        patterns=[
            r"^(what|when|where|who|why|how|which)\b",
            r"\?$",  # Ends with question mark
            r"\b(do you know|can you tell me|what about)\b",
        ],
        priority=4,
        complexity_hint=ComplexityTier.MEDIUM,
    ),
    # Information sharing - user telling us about themselves
    IntentPattern(
        intent=IntentType.INFORMATION_SHARE,
        patterns=[
            r"\b(i am|i'm|we are|we're|my|our|i have|we have|i've|we've)\b",
            r"\b(i work|i live|i like|i love|i prefer|i enjoy)\b",
            r"\b(my (wife|husband|kids?|children|family|son|daughter|mother|father|mom|dad))\b",
            r"\b(just us|just the|both of us|the two of us|just me)\b",
            r"\b(she|he|they)\s+(can|will|is|are|has|have)\b",
            r"\b(she's|he's|they're)\s+\d+",
            r"\$\d+",  # Dollar amounts (sharing budget info)
            r"\b(around|about|roughly|maybe|approximately)\s+\$?\d+\b",
            r"\b(allerg|diet|restrict|intoleran)\b",  # Health info sharing
            r"\b(has a|have a)\s+(mild|severe|serious)?\s*(allerg|condition)\b",
        ],
        priority=3,
        complexity_hint=ComplexityTier.MEDIUM,
    ),
    # Decision / preference - user making a choice
    IntentPattern(
        intent=IntentType.DECISION,
        patterns=[
            r"\b(sounds? (better|good|great|perfect|nice))\b",
            r"\b(let'?s? (go|do|try|pick|choose|stick))\b",
            r"\b(i'?d? (prefer|rather|choose|pick|go with))\b",
            r"\b(more relaxed|better than|instead of|rather than)\b",
            r"\b(definitely|absolutely|for sure|that one|this one)\b",
            r"\b(option [a-d1-4]|the (first|second|third|last) one)\b",
        ],
        priority=7,
        complexity_hint=ComplexityTier.MEDIUM,
    ),
]


# =============================================================================
# COMPLEXITY RULES
# =============================================================================


@dataclass
class ComplexitySignal:
    """A signal that affects complexity assessment."""

    name: str
    pattern: Optional[str] = None
    detector: Optional[str] = None  # Function name to call
    tier_bump: int = 0  # How much to increase tier (0, 1, or 2)


COMPLEXITY_SIGNALS: List[ComplexitySignal] = [
    # Multi-step requests bump complexity
    ComplexitySignal(
        name="multi_step",
        pattern=r"\b(and then|after that|also|and also|then)\b",
        tier_bump=1,
    ),
    # Conditional requests are complex
    ComplexitySignal(
        name="conditional",
        pattern=r"\b(if|when|unless|only if|in case)\b",
        tier_bump=1,
    ),
    # Time-sensitive requests
    ComplexitySignal(
        name="time_sensitive",
        pattern=r"\b(urgent|asap|immediately|right now|quickly)\b",
        tier_bump=0,  # Urgent but not necessarily complex
    ),
    # Multiple entities mentioned
    ComplexitySignal(
        name="multi_entity",
        pattern=r"\b(both|all|everyone|each|every)\b",
        tier_bump=1,
    ),
    # Long input suggests complexity
    ComplexitySignal(
        name="long_input",
        detector="check_length",
        tier_bump=1,
    ),
    # Multiple sentences
    ComplexitySignal(
        name="multi_sentence",
        detector="check_sentences",
        tier_bump=1,
    ),
]


# =============================================================================
# CLASSIFIER
# =============================================================================


class IntentClassifier:
    """
    Classifies user input into intent type and complexity tier.

    Uses heuristic pattern matching as a fast Tier-1 classifier.
    Production system would use UltraBERT for more accurate classification.
    """

    def __init__(
        self,
        gap_detector: Optional[GapDetector] = None,
        enable_gap_detection: bool = True,
    ):
        """
        Initialize classifier.

        Args:
            gap_detector: Optional gap detector instance
            enable_gap_detection: Whether to run gap detection
        """
        self._gap_detector = gap_detector or GapDetector()
        self._enable_gap_detection = enable_gap_detection
        self._intent_patterns = INTENT_PATTERNS
        self._complexity_signals = COMPLEXITY_SIGNALS

    def classify(
        self,
        user_input: str,
        session_context: Optional[Dict[str, Any]] = None,
        is_clarification_response: bool = False,
    ) -> ClassificationResult:
        """
        Classify user input.

        Args:
            user_input: The user's message
            session_context: Optional context from SessionState
            is_clarification_response: Whether this is responding to our clarification

        Returns:
            ClassificationResult with intent, complexity, gaps
        """
        # If we're expecting clarification response, bias toward that
        if is_clarification_response:
            return self._classify_as_clarification(user_input)

        # Detect primary intent
        primary_intent, confidence = self._detect_primary_intent(user_input)

        # Detect secondary intents
        secondary_intents = self._detect_secondary_intents(user_input, primary_intent)

        # Calculate base complexity from intent
        base_complexity = self._get_base_complexity(primary_intent)

        # Apply complexity signals
        complexity, signals = self._calculate_complexity(
            user_input, base_complexity, len(secondary_intents)
        )

        # Detect gaps if enabled
        gaps: List[Gap] = []
        if self._enable_gap_detection and primary_intent in (
            IntentType.REQUEST,
            IntentType.QUESTION,
        ):
            gaps = self._gap_detector.detect_gaps(user_input, session_context)

        # Extract entities
        entities = self._extract_entities(user_input)

        return ClassificationResult(
            primary_intent=primary_intent,
            secondary_intents=secondary_intents,
            complexity=complexity,
            gaps=gaps,
            confidence=confidence,
            detected_entities=entities,
        )

    def _classify_as_clarification(self, user_input: str) -> ClassificationResult:
        """Classify input as a clarification response."""
        return ClassificationResult(
            primary_intent=IntentType.CLARIFICATION_RESPONSE,
            secondary_intents=[],
            complexity=ComplexityTier.LOW,
            gaps=[],
            confidence=0.9,
            detected_entities=self._extract_entities(user_input),
        )

    def _detect_primary_intent(self, user_input: str) -> Tuple[IntentType, float]:
        """Detect the primary intent from input."""
        input_lower = user_input.lower().strip()

        # Sort patterns by priority (higher first)
        sorted_patterns = sorted(self._intent_patterns, key=lambda p: p.priority, reverse=True)

        for intent_pattern in sorted_patterns:
            for pattern in intent_pattern.patterns:
                if re.search(pattern, input_lower, re.IGNORECASE):
                    # Calculate confidence based on pattern specificity
                    confidence = 0.7 + (intent_pattern.priority * 0.03)
                    return intent_pattern.intent, min(confidence, 0.95)

        # Default to unknown
        return IntentType.UNKNOWN, 0.5

    def _detect_secondary_intents(self, user_input: str, primary: IntentType) -> List[IntentType]:
        """Detect any secondary intents."""
        input_lower = user_input.lower()
        secondary: List[IntentType] = []

        for intent_pattern in self._intent_patterns:
            if intent_pattern.intent == primary:
                continue

            for pattern in intent_pattern.patterns:
                if re.search(pattern, input_lower, re.IGNORECASE):
                    if intent_pattern.intent not in secondary:
                        secondary.append(intent_pattern.intent)
                    break

        return secondary[:2]  # Limit to 2 secondary intents

    def _get_base_complexity(self, intent: IntentType) -> ComplexityTier:
        """Get base complexity for an intent type."""
        # Find the pattern and return its hint
        for pattern in self._intent_patterns:
            if pattern.intent == intent:
                return pattern.complexity_hint

        return ComplexityTier.MEDIUM

    def _calculate_complexity(
        self,
        user_input: str,
        base: ComplexityTier,
        secondary_count: int,
    ) -> Tuple[ComplexityTier, List[str]]:
        """Calculate final complexity from base and signals."""
        tier_value = {"low": 0, "medium": 1, "high": 2}
        current = tier_value[base.value]
        matched_signals: List[str] = []

        # Check each complexity signal
        for signal in self._complexity_signals:
            if signal.pattern:
                if re.search(signal.pattern, user_input, re.IGNORECASE):
                    current += signal.tier_bump
                    matched_signals.append(signal.name)
            elif signal.detector:
                if self._run_detector(signal.detector, user_input):
                    current += signal.tier_bump
                    matched_signals.append(signal.name)

        # Multi-intent bumps complexity
        if secondary_count > 0:
            current += 1
            matched_signals.append("multi_intent")

        # Cap at MEDIUM for POC (HIGH requires Planner)
        current = min(current, 1)

        # Convert back to tier
        tier_map = {0: ComplexityTier.LOW, 1: ComplexityTier.MEDIUM, 2: ComplexityTier.HIGH}
        return tier_map.get(current, ComplexityTier.MEDIUM), matched_signals

    def _run_detector(self, detector_name: str, user_input: str) -> bool:
        """Run a named detector function."""
        if detector_name == "check_length":
            return len(user_input) > 100
        elif detector_name == "check_sentences":
            return user_input.count(".") > 1 or user_input.count("!") > 1
        return False

    def _extract_entities(self, user_input: str) -> Dict[str, Any]:
        """Extract entities from user input."""
        entities: Dict[str, Any] = {}

        # Numbers
        numbers = re.findall(r"\b\d+\b", user_input)
        if numbers:
            entities["numbers"] = [int(n) for n in numbers]

        # Times
        times = re.findall(r"\b(\d{1,2}:\d{2}|\d{1,2}\s*(am|pm|AM|PM))\b", user_input)
        if times:
            entities["times"] = [t[0] if isinstance(t, tuple) else t for t in times]

        # Proper nouns (simple capitalized word detection)
        words = user_input.split()
        proper_nouns = [
            w
            for w in words
            if w[0].isupper() and len(w) > 1 and w not in ("I", "I'm", "I've", "I'd")
        ]
        if proper_nouns:
            entities["names"] = proper_nouns[:5]

        # Money amounts
        money = re.findall(r"\$\d+(?:,\d{3})*(?:\.\d{2})?", user_input)
        if money:
            entities["money"] = money

        return entities
