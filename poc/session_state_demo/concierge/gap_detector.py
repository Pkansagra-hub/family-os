"""
Gap Detector
============

Heuristic-based gap detection for the Concierge FSM.

Detects common information gaps that require clarification:
- Missing time/date
- Vague references (pronouns without context)
- Missing quantities
- Ambiguous locations
- Incomplete requests

Reference: k1_cognitive_architecture_skeleton.mmd
- CONTRACT_SIGNAL_GAPS: Contract & Signal Gap Detector
- SIGNAL_LIBRARY: Pronouns/conflicts/multi-entities/time vagueness
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from poc.session_state_demo.concierge.states import Gap

# =============================================================================
# GAP DETECTION PATTERNS
# =============================================================================


@dataclass
class GapPattern:
    """A pattern that triggers gap detection."""

    gap_type: str
    trigger_pattern: str  # Regex pattern
    anti_patterns: List[str]  # Patterns that indicate gap is filled
    question_template: str
    confidence: float = 0.8


# Patterns that suggest something is missing
GAP_PATTERNS: List[GapPattern] = [
    # Missing time
    GapPattern(
        gap_type="missing_time",
        trigger_pattern=r"\b(remind|reminder|schedule|book|appointment|set alarm|wake me)\b",
        anti_patterns=[
            r"\b(\d{1,2}:\d{2}|\d{1,2}\s*(am|pm|AM|PM))\b",  # Time like 9:00 or 9am
            r"\b(today|tomorrow|tonight|morning|afternoon|evening|noon|midnight)\b",
            r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
            r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\b",
            r"\b(in \d+ (minutes?|hours?|days?|weeks?))\b",
        ],
        question_template="When would you like me to {action}?",
        confidence=0.9,
    ),
    # Missing quantity
    GapPattern(
        gap_type="missing_quantity",
        trigger_pattern=r"\b(buy|order|get|purchase)\s+(some|a few|several)\b",
        anti_patterns=[
            r"\b\d+\b",  # Any number
            r"\b(one|two|three|four|five|six|seven|eight|nine|ten)\b",
            r"\b(a|an|the)\s+\w+\b",  # Specific item
        ],
        question_template="How many would you like?",
        confidence=0.7,
    ),
    # Vague pronoun reference (only when no context)
    GapPattern(
        gap_type="vague_reference",
        trigger_pattern=r"^(tell|remind|ask|call|message|email)\s+(them|him|her|it)\b",
        anti_patterns=[
            r"\b(my|the|a)\s+(wife|husband|mom|dad|brother|sister|friend|boss|doctor)\b",
            r"\b[A-Z][a-z]+\b",  # Proper noun (name)
        ],
        question_template="Who would you like me to {action}?",
        confidence=0.85,
    ),
    # Missing destination
    GapPattern(
        gap_type="missing_location",
        trigger_pattern=r"\b(directions|navigate|take me|drive|go)\b",
        anti_patterns=[
            r"\b(to|towards)\s+[A-Z]",  # "to Tokyo", "to Main Street"
            r"\b(home|work|office|school|airport|station)\b",
            r"\b\d+\s+\w+\s+(street|st|avenue|ave|road|rd|boulevard|blvd)\b",
        ],
        question_template="Where would you like to go?",
        confidence=0.8,
    ),
    # Missing person for family-related requests
    GapPattern(
        gap_type="missing_person",
        trigger_pattern=r"\b(call|text|message|email)\s+(my\s+)?family\b",
        anti_patterns=[
            r"\b(wife|husband|mom|dad|mother|father|brother|sister|son|daughter|kids?|children)\b",
            r"\b[A-Z][a-z]+\b",  # Specific name
        ],
        question_template="Which family member should I contact?",
        confidence=0.75,
    ),
]


# =============================================================================
# GAP DETECTOR
# =============================================================================


class GapDetector:
    """
    Detects information gaps in user input that need clarification.

    Uses heuristic pattern matching as a fast Tier-1 check.
    Production system would use UltraBERT for more accurate detection.
    """

    def __init__(self, context_resolver: Optional["ContextResolver"] = None):
        """
        Initialize detector.

        Args:
            context_resolver: Optional resolver to check SessionState for context
        """
        self._context_resolver = context_resolver
        self._patterns = GAP_PATTERNS

    def detect_gaps(
        self,
        user_input: str,
        session_context: Optional[dict] = None,
    ) -> List[Gap]:
        """
        Detect gaps in user input.

        Args:
            user_input: The user's message
            session_context: Optional context from SessionState

        Returns:
            List of detected gaps, sorted by confidence
        """
        gaps: List[Gap] = []
        input_lower = user_input.lower()

        for pattern in self._patterns:
            gap = self._check_pattern(user_input, input_lower, pattern, session_context)
            if gap:
                gaps.append(gap)

        # Sort by confidence (highest first)
        gaps.sort(key=lambda g: g.confidence, reverse=True)

        return gaps

    def _check_pattern(
        self,
        original_input: str,
        input_lower: str,
        pattern: GapPattern,
        context: Optional[dict],
    ) -> Optional[Gap]:
        """Check a single pattern against input."""
        # Check if trigger pattern matches
        trigger_match = re.search(pattern.trigger_pattern, input_lower, re.IGNORECASE)
        if not trigger_match:
            return None

        # Check if any anti-pattern matches (gap is filled)
        for anti_pattern in pattern.anti_patterns:
            if re.search(anti_pattern, original_input, re.IGNORECASE):
                return None

        # Check context for resolution
        if context and self._is_resolved_by_context(pattern.gap_type, context):
            return None

        # Extract action from input for question template
        action = self._extract_action(trigger_match.group(0))
        question = pattern.question_template.format(action=action)

        return Gap(
            gap_type=pattern.gap_type,
            description=f"Missing {pattern.gap_type.replace('_', ' ')}",
            question=question,
            context=original_input,
            confidence=pattern.confidence,
        )

    def _extract_action(self, matched_text: str) -> str:
        """Extract action verb for question template."""
        # Map common triggers to actions
        action_map = {
            "remind": "remind you",
            "reminder": "set the reminder",
            "schedule": "schedule it",
            "book": "book it",
            "appointment": "schedule the appointment",
            "alarm": "set the alarm",
            "wake": "wake you up",
            "buy": "get",
            "order": "order",
            "call": "contact",
            "text": "message",
            "message": "message",
            "email": "email",
            "directions": "navigate",
            "navigate": "navigate",
            "drive": "take you",
            "go": "go",
        }

        for trigger, action in action_map.items():
            if trigger in matched_text.lower():
                return action

        return "do that"

    def _is_resolved_by_context(self, gap_type: str, context: dict) -> bool:
        """Check if gap can be resolved from session context."""
        # Check if relevant context exists
        if gap_type == "vague_reference":
            # Check if we have recent person mentions
            recent_entities = context.get("recent_entities", {})
            if "person" in recent_entities:
                return True

        if gap_type == "missing_person":
            # Check if family members are known
            beliefs = context.get("beliefs", {})
            if any("family" in str(b).lower() for b in beliefs.values()):
                return True

        return False


class ContextResolver:
    """
    Resolves gaps using SessionState context.

    Can fill in missing information from:
    - Recent conversation history
    - Known beliefs about user
    - Persona traits
    """

    def __init__(self, bridge: "SessionLLMBridge"):
        """Initialize with bridge to SessionState."""
        self._bridge = bridge

    def get_context(self) -> dict:
        """Get relevant context for gap resolution."""
        context = {}

        # Get recent history for entity tracking
        try:
            history_data = self._bridge.get_section_data("history_active")
            context["recent_turns"] = history_data.get("turns", [])
        except Exception:
            context["recent_turns"] = []

        # Get beliefs for known facts
        try:
            beliefs_data = self._bridge.get_section_data("beliefs_active")
            context["beliefs"] = beliefs_data
        except Exception:
            context["beliefs"] = {}

        return context

    def can_resolve(self, gap: Gap) -> Tuple[bool, Optional[str]]:
        """
        Check if a gap can be resolved from context.

        Returns:
            Tuple of (can_resolve, resolved_value)
        """
        context = self.get_context()

        # Try to resolve based on gap type
        if gap.gap_type == "vague_reference":
            # Check recent history for names
            for turn in context.get("recent_turns", [])[-3:]:
                user_text = turn.get("user", "")
                # Look for names in recent turns
                names = re.findall(r"\b([A-Z][a-z]+)\b", user_text)
                if names:
                    return True, names[-1]

        return False, None
