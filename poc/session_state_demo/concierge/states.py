"""
Concierge FSM States
====================

State definitions and data classes for the Concierge FSM.

Reference: k1_cognitive_architecture_skeleton.mmd
- FSM_CORE_LOOP: LISTENING, ACKING, CLARIFYING, DISPATCHING, etc.
- Complexity tiers: LOW (<2s), MEDIUM (2-10s), HIGH (10-60s)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional

# =============================================================================
# NARRATIVE PHASES (M9.2.1)
# =============================================================================


class NarrativePhase(Enum):
    """
    Narrative phases for conversation tracking.

    Maps to the story arc of a typical multi-turn conversation.
    Used for context-aware responses and progress tracking.
    """

    SETUP = "setup"  # Learning context, initial gathering (Turns 1-8)
    BOOKING = "booking"  # Making reservations, executing plans (Turns 9-14)
    EXECUTION = "execution"  # Background tasks, monitoring (Turns 15-19)
    CRISIS = "crisis"  # Crash/restore, problem handling (Turn 20)
    RECOVERY = "recovery"  # Post-crash, re-establishing context (Turns 21-25)
    RESOLUTION = "resolution"  # Wrap up, confirmation (Turns 26-30)

    @property
    def description(self) -> str:
        """Human-readable description of the phase."""
        descriptions = {
            "setup": "Learning about the situation and gathering requirements",
            "booking": "Making reservations and executing plans",
            "execution": "Monitoring and background task processing",
            "crisis": "Handling problems or unexpected situations",
            "recovery": "Re-establishing context after disruption",
            "resolution": "Wrapping up and confirming final details",
        }
        return descriptions.get(self.value, "Unknown phase")

    @classmethod
    def from_turn_number(cls, turn: int) -> "NarrativePhase":
        """Determine phase from turn number (demo-specific)."""
        if turn <= 8:
            return cls.SETUP
        elif turn <= 14:
            return cls.BOOKING
        elif turn <= 19:
            return cls.EXECUTION
        elif turn == 20:
            return cls.CRISIS
        elif turn <= 25:
            return cls.RECOVERY
        else:
            return cls.RESOLUTION


# =============================================================================
# REFERENT TYPES (M9.1)
# =============================================================================


class ReferentType(Enum):
    """Types of discourse referents tracked in scoreboard."""

    PERSON = "person"  # Mike, Emma, Sarah, Jake
    PLACE = "place"  # Sonoma, Vineyard Inn, restaurants
    PLAN = "plan"  # trip, booking, reservation
    TIME = "time"  # Saturday, next week, 7:00 PM
    THING = "thing"  # allergy, budget, surprise
    EVENT = "event"  # birthday, anniversary, dinner


@dataclass
class Referent:
    """A discourse referent being tracked."""

    name: str  # Display name (e.g., "Mike")
    ref_type: ReferentType  # Type of referent
    salience: float = 0.5  # Current salience (0-1)
    last_mention_turn: int = 0  # Turn when last mentioned
    first_mention_turn: int = 0  # Turn when first introduced
    aliases: List[str] = field(default_factory=list)  # Alternative names
    properties: Dict[str, Any] = field(default_factory=dict)  # Extra info

    def decay(self, decay_factor: float = 0.9) -> None:
        """Decay salience over time."""
        self.salience = max(0.1, self.salience * decay_factor)

    def mention(self, turn: int, boost: float = 0.3) -> None:
        """Boost salience when mentioned."""
        self.last_mention_turn = turn
        self.salience = min(1.0, self.salience + boost)


# =============================================================================
# FSM STATES
# =============================================================================


class ConciergeState(Enum):
    """
    FSM states for the Concierge conversation loop.

    Simplified from full architecture (8 states → 6 states for POC).
    """

    LISTENING = auto()  # Waiting for user input
    ACKING = auto()  # Processing input, classifying intent
    CLARIFYING = auto()  # Need more info from user
    DISPATCHING = auto()  # Routing to execution path
    EXECUTING = auto()  # Running tools / LLM
    DELIVERING = auto()  # Sending response to user

    def __str__(self) -> str:
        return self.name


class ComplexityTier(Enum):
    """
    Complexity tiers for routing decisions.

    From architecture:
    - LOW: <2s, simple tool + response
    - MEDIUM: 2-10s, LLM reasoning + tools
    - HIGH: 10-60s, planning + orchestration (not in POC)
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"  # Not implemented in POC

    @property
    def description(self) -> str:
        descriptions = {
            "low": "Simple (direct tool execution)",
            "medium": "Moderate (LLM reasoning required)",
            "high": "Complex (planning required - not in POC)",
        }
        return descriptions.get(self.value, "Unknown")


class IntentType(Enum):
    """
    Intent types detected from user input.

    Simplified classification for POC.
    """

    GREETING = "greeting"
    INFORMATION_SHARE = "information_share"  # User sharing facts about themselves
    QUESTION = "question"  # User asking something
    REQUEST = "request"  # User requesting action
    CLARIFICATION_RESPONSE = "clarification_response"  # Answering our question
    DECISION = "decision"  # User making a choice or stating a preference
    UNKNOWN = "unknown"


@dataclass
class Gap:
    """A detected information gap that needs clarification."""

    gap_type: str  # e.g., "missing_time", "vague_reference"
    description: str  # What's missing
    question: str  # Question to ask user
    context: str = ""  # Original text that triggered gap
    confidence: float = 0.8


@dataclass
class ClassificationResult:
    """Result of intent classification and gap detection."""

    primary_intent: IntentType
    secondary_intents: List[IntentType] = field(default_factory=list)
    complexity: ComplexityTier = ComplexityTier.LOW
    gaps: List[Gap] = field(default_factory=list)
    confidence: float = 0.8
    detected_entities: Dict[str, Any] = field(default_factory=dict)

    @property
    def requires_clarification(self) -> bool:
        """Check if clarification is needed before proceeding."""
        return len(self.gaps) > 0 and self.gaps[0].confidence > 0.6

    @property
    def is_multi_intent(self) -> bool:
        """Check if multiple intents were detected."""
        return len(self.secondary_intents) > 0


@dataclass
class TurnResult:
    """Result of processing a single turn through the FSM."""

    # Final state after processing
    final_state: ConciergeState

    # Response to user (if any)
    response: str = ""

    # Did we need clarification?
    needs_clarification: bool = False
    clarification_question: str = ""

    # Classification info
    classification: Optional[ClassificationResult] = None

    # Complexity tier used
    tier: ComplexityTier = ComplexityTier.LOW

    # Tool calls made
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tools_executed: int = 0
    tools_blocked: int = 0

    # State transitions that occurred
    state_history: List[ConciergeState] = field(default_factory=list)

    # Timing
    total_ms: int = 0
    classification_ms: int = 0
    execution_ms: int = 0


@dataclass
class FSMStats:
    """Statistics about FSM operation."""

    total_turns: int = 0
    clarifications_triggered: int = 0
    low_tier_count: int = 0
    medium_tier_count: int = 0
    high_tier_count: int = 0
    avg_classification_ms: float = 0.0
    state_transition_count: int = 0

    def record_turn(self, result: TurnResult) -> None:
        """Update stats from a turn result."""
        self.total_turns += 1

        if result.needs_clarification:
            self.clarifications_triggered += 1

        if result.tier == ComplexityTier.LOW:
            self.low_tier_count += 1
        elif result.tier == ComplexityTier.MEDIUM:
            self.medium_tier_count += 1
        elif result.tier == ComplexityTier.HIGH:
            self.high_tier_count += 1

        self.state_transition_count += len(result.state_history)

        # Update running average for classification time
        if result.classification_ms > 0:
            prev_total = self.avg_classification_ms * (self.total_turns - 1)
            self.avg_classification_ms = (prev_total + result.classification_ms) / self.total_turns


# =============================================================================
# STATE TRANSITION RULES
# =============================================================================

# Valid state transitions
VALID_TRANSITIONS: Dict[ConciergeState, List[ConciergeState]] = {
    ConciergeState.LISTENING: [ConciergeState.ACKING],
    ConciergeState.ACKING: [ConciergeState.CLARIFYING, ConciergeState.DISPATCHING],
    ConciergeState.CLARIFYING: [ConciergeState.LISTENING],  # Wait for user response
    ConciergeState.DISPATCHING: [ConciergeState.EXECUTING],
    ConciergeState.EXECUTING: [ConciergeState.DELIVERING],
    ConciergeState.DELIVERING: [ConciergeState.LISTENING],
}


def is_valid_transition(from_state: ConciergeState, to_state: ConciergeState) -> bool:
    """Check if a state transition is valid."""
    valid_targets = VALID_TRANSITIONS.get(from_state, [])
    return to_state in valid_targets
