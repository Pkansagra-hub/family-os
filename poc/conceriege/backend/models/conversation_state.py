"""
Conversation State Management Models

Tracks conversation history, common ground (scoreboard), and user context for
maintaining human-like dialogue flow.

Research basis:
- Conversational Grounding (Clark & Brennan 1991) - Common ground tracking
- QUD Framework (Roberts 2012) - Question Under Discussion
- Dialogue State Tracking (Williams 2007)
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Literal, Optional


@dataclass
class Referent:
    """
    Represents an entity mentioned in conversation with salience tracking.

    Research basis: Clark's Common Ground Theory - entities build up shared context

    Fields:
        entity: The entity text (e.g., "milk", "coffee", "GERD")
        first_mentioned: When this entity was first mentioned
        salience: Current salience score (0.0-1.0), decays over time
        user_hypothesis: Whether user believes this entity is relevant to their problem
        sentiment: User's sentiment towards entity (positive, negative, neutral)
        medical_condition: Whether this is a medical condition
        contradicted: Whether specialist findings contradicted user's hypothesis
    """

    entity: str
    first_mentioned: datetime = field(default_factory=datetime.utcnow)
    salience: float = 1.0
    user_hypothesis: bool = False
    sentiment: Optional[Literal["positive", "negative", "neutral"]] = None
    medical_condition: bool = False
    contradicted: bool = False

    def decay_salience(self, decay_rate: float = 0.1):
        """
        Decay salience over time (entities become less relevant).

        Args:
            decay_rate: How much to decay (0.0-1.0)
        """
        self.salience = max(0.0, self.salience - decay_rate)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "entity": self.entity,
            "first_mentioned": self.first_mentioned.isoformat(),
            "salience": self.salience,
            "user_hypothesis": self.user_hypothesis,
            "sentiment": self.sentiment,
            "medical_condition": self.medical_condition,
            "contradicted": self.contradicted,
        }


@dataclass
class Scoreboard:
    """
    Tracks common ground between user and agent (Clark's Scoreboard concept).

    Research basis: Conversational Grounding (Clark 1991)

    Fields:
        referents: Dictionary of entities mentioned with salience tracking
        pending_specialists: List of specialists currently working in background
        completed_tasks: List of completed specialist tasks in this conversation
    """

    referents: Dict[str, Referent] = field(default_factory=dict)
    pending_specialists: List[str] = field(default_factory=list)
    completed_tasks: List[str] = field(default_factory=list)

    def add_referent(
        self,
        entity: str,
        user_hypothesis: bool = False,
        sentiment: Optional[Literal["positive", "negative", "neutral"]] = None,
        medical_condition: bool = False,
    ):
        """
        Add or update referent in scoreboard.

        Args:
            entity: Entity text
            user_hypothesis: Whether user believes this is relevant
            sentiment: User's sentiment (positive, negative, neutral)
            medical_condition: Whether this is a medical condition
        """
        if entity in self.referents:
            # Update existing referent
            self.referents[entity].salience = 1.0  # Refresh salience
            if user_hypothesis:
                self.referents[entity].user_hypothesis = True
            if sentiment:
                self.referents[entity].sentiment = sentiment
        else:
            # Create new referent
            self.referents[entity] = Referent(
                entity=entity,
                salience=1.0,
                user_hypothesis=user_hypothesis,
                sentiment=sentiment,
                medical_condition=medical_condition,
            )

    def update_salience(self, decay_rate: float = 0.1):
        """
        Decay salience for all referents.

        Args:
            decay_rate: How much to decay per update
        """
        for referent in self.referents.values():
            referent.decay_salience(decay_rate)

    def get_top_referents(self, n: int = 5) -> List[Referent]:
        """
        Get top N referents by salience.

        Args:
            n: Number of referents to return

        Returns:
            List of top N referents
        """
        sorted_referents = sorted(self.referents.values(), key=lambda r: r.salience, reverse=True)
        return sorted_referents[:n]

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "referents": {entity: ref.to_dict() for entity, ref in self.referents.items()},
            "pending_specialists": self.pending_specialists,
            "completed_tasks": self.completed_tasks,
        }


@dataclass
class Turn:
    """
    Represents a single conversation turn (user message + agent response).

    Fields:
        timestamp: When this turn occurred
        user_message: User's message (None for agent-initiated turns)
        agent_response: Agent's response
        turn_type: Type of turn (user, reactive, proactive, synthesis)
    """

    timestamp: datetime = field(default_factory=datetime.utcnow)
    user_message: Optional[str] = None
    agent_response: str = ""
    turn_type: Literal["user", "reactive", "proactive", "synthesis"] = "user"

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "user_message": self.user_message,
            "agent_response": self.agent_response,
            "turn_type": self.turn_type,
        }


@dataclass
class ConversationState:
    """
    Manages complete conversation state for reactive-proactive loop.

    Research basis:
    - QUD Framework (Roberts 2012) - Question Under Discussion
    - Dialogue State Tracking (Williams 2007)
    - Scoreboard (Clark 1991)

    Fields:
        user_id: FamilyOS user ID
        conversation_id: Unique conversation identifier
        qud: Question Under Discussion (what user wants to know)
        scoreboard: Common ground tracking
        recent_history: Last N turns (for context)
        information_gaps: Missing information identified by proactive generator
        proactive_prompts_sent: Count of proactive prompts sent
        last_proactive_at: Timestamp of last proactive prompt
    """

    user_id: str
    conversation_id: str
    qud: Optional[str] = None
    scoreboard: Scoreboard = field(default_factory=Scoreboard)
    recent_history: deque = field(default_factory=lambda: deque(maxlen=10))
    information_gaps: List[str] = field(default_factory=list)
    proactive_prompts_sent: int = 0
    last_proactive_at: Optional[datetime] = None

    def add_turn(
        self,
        user_message: Optional[str],
        agent_response: str,
        turn_type: Literal["user", "reactive", "proactive", "synthesis"] = "user",
    ):
        """
        Add a turn to conversation history.

        Args:
            user_message: User's message (None for agent-initiated)
            agent_response: Agent's response
            turn_type: Type of turn
        """
        turn = Turn(user_message=user_message, agent_response=agent_response, turn_type=turn_type)
        self.recent_history.append(turn)

    def add_proactive_prompt(self, prompt_text: str):
        """
        Track proactive prompt sent to user.

        Args:
            prompt_text: The proactive prompt text
        """
        self.proactive_prompts_sent += 1
        self.last_proactive_at = datetime.utcnow()
        self.add_turn(user_message=None, agent_response=prompt_text, turn_type="proactive")

    def update_qud(self, new_qud: str):
        """
        Update Question Under Discussion.

        Args:
            new_qud: New question/topic
        """
        self.qud = new_qud

    def update_gaps(self, gaps: List[str]):
        """
        Update information gaps identified.

        Args:
            gaps: List of missing information types
        """
        self.information_gaps = gaps

    def get_referents(self) -> Dict[str, Referent]:
        """
        Get all referents from scoreboard.

        Returns:
            Dictionary of entity -> Referent
        """
        return self.scoreboard.referents

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "qud": self.qud,
            "scoreboard": self.scoreboard.to_dict(),
            "recent_history": [turn.to_dict() for turn in self.recent_history],
            "information_gaps": self.information_gaps,
            "proactive_prompts_sent": self.proactive_prompts_sent,
            "last_proactive_at": (
                self.last_proactive_at.isoformat() if self.last_proactive_at else None
            ),
        }
