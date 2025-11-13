"""
Memory Tracker - Conversation Topic & User Detail Tracking

TOPIC 3: MEMORY & CONTINUITY

This module tracks conversation topics, user details, and generates natural memory
references to maintain conversation continuity and coherence.

Key Features:
- Tracks conversation threads (coffee, gerd, sleep, gym, etc.)
- Stores user details with confidence scores
- Generates natural memory context for LLM prompts
- Suggests memory references for current messages
- Manages thread status (active, resolved, deferred)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class ConversationThread:
    """Tracks a conversation topic across multiple turns"""

    topic: str
    """Topic name (e.g., 'coffee', 'gerd', 'sleep')"""

    mentions: List[str] = field(default_factory=list)
    """User statements about this topic"""

    insights: List[str] = field(default_factory=list)
    """Agent findings/insights about this topic"""

    status: str = "active"
    """Topic status: 'active', 'resolved', or 'deferred'"""

    last_mentioned: datetime = field(default_factory=datetime.now)
    """Last time this topic was mentioned"""

    mention_count: int = 0
    """Number of times user mentioned this topic"""


@dataclass
class UserDetail:
    """Stores user preferences, hypotheses, and details"""

    key: str
    """Detail key (e.g., 'milk_hypothesis', 'gym_routine')"""

    value: str
    """Detail value/content"""

    confidence: float = 0.8
    """Confidence score (0.0-1.0): how sure we are about this detail"""

    first_mentioned: datetime = field(default_factory=datetime.now)
    """When this detail was first mentioned"""

    updated_at: datetime = field(default_factory=datetime.now)
    """Last time this detail was updated"""


class MemoryTracker:
    """
    Tracks conversation history and user details across turns.

    Maintains ConversationThread objects for each topic and UserDetail objects
    for facts about the user. Generates memory context for LLM prompts and
    suggests natural memory references when relevant.
    """

    # Topic keywords for rule-based topic extraction
    TOPIC_KEYWORDS = {
        "coffee": ["coffee", "caffeine", "espresso", "cup", "tea", "drink"],
        "gerd": ["gerd", "reflux", "heartburn", "acid", "stomach", "digestive"],
        "sleep": ["sleep", "sleeping", "bedtime", "night", "insomnia", "tired"],
        "gym": ["gym", "exercise", "workout", "fitness", "weights", "cardio"],
        "milk": ["milk", "dairy", "cheese", "lactose", "yogurt", "butter"],
        "stress": ["stress", "anxiety", "worried", "anxious", "tense", "pressure"],
    }

    def __init__(self):
        """Initialize empty memory storage"""
        self.threads: Dict[str, ConversationThread] = {}
        self.user_details: Dict[str, UserDetail] = {}

    def add_to_thread(self, topic: str, text: str, source: str = "user") -> ConversationThread:
        """
        Add statement to conversation thread.

        Creates new thread if doesn't exist, appends to existing thread if it does.
        Updates last_mentioned timestamp and mention_count.

        Args:
            topic: Topic name (e.g., 'coffee')
            text: Statement to add
            source: 'user' or 'agent'

        Returns:
            Updated ConversationThread object
        """
        if topic not in self.threads:
            self.threads[topic] = ConversationThread(topic=topic)

        thread = self.threads[topic]

        if source == "user":
            thread.mentions.append(text)
            thread.mention_count += 1
        else:  # agent
            thread.insights.append(text)

        thread.last_mentioned = datetime.now()
        return thread

    def store_detail(self, key: str, value: str, confidence: float = 0.8) -> UserDetail:
        """
        Store or update user detail.

        Stores user preferences, hypotheses, observations with confidence score.
        Updates if key already exists.

        Args:
            key: Detail key (e.g., 'milk_hypothesis')
            value: Detail value
            confidence: Confidence score (0.0-1.0)

        Returns:
            UserDetail object
        """
        now = datetime.now()

        if key in self.user_details:
            # Update existing detail
            detail = self.user_details[key]
            detail.value = value
            detail.confidence = confidence
            detail.updated_at = now
        else:
            # Create new detail
            detail = UserDetail(key=key, value=value, confidence=confidence)
            self.user_details[key] = detail

        return detail

    def get_thread_history(self, topic: str) -> Optional[ConversationThread]:
        """
        Retrieve conversation thread by topic.

        Args:
            topic: Topic name

        Returns:
            ConversationThread if exists, None otherwise
        """
        return self.threads.get(topic)

    def get_active_threads(self) -> List[ConversationThread]:
        """
        Get all active conversation threads.

        Returns:
            List of threads with status='active'
        """
        return [t for t in self.threads.values() if t.status == "active"]

    def get_resolved_threads(self) -> List[ConversationThread]:
        """
        Get all resolved conversation threads.

        Returns:
            List of threads with status='resolved'
        """
        return [t for t in self.threads.values() if t.status == "resolved"]

    def generate_memory_context(self, current_topic: Optional[str] = None) -> str:
        """
        Generate context string for LLM with relevant memories.

        Formats active threads, recent details, and provides context about
        conversation state for inclusion in LLM prompts.

        Args:
            current_topic: Current topic being discussed (optional)

        Returns:
            Formatted memory context string
        """
        context_parts = []

        # Active topics
        active = self.get_active_threads()
        if active:
            active_names = ", ".join([t.topic for t in active])
            context_parts.append(f"Active topics: {active_names}")

        # Recent user mentions (last 3 topics mentioned)
        if self.threads:
            recent = sorted(self.threads.values(), key=lambda t: t.last_mentioned, reverse=True)[:3]
            if recent:
                recent_names = ", ".join([t.topic for t in recent])
                context_parts.append(f"Recently discussed: {recent_names}")

        # User details (high confidence)
        high_confidence = [d for d in self.user_details.values() if d.confidence >= 0.7]
        if high_confidence:
            details_text = "; ".join([f"{d.key}: {d.value}" for d in high_confidence])
            context_parts.append(f"User details: {details_text}")

        # Current topic context
        if current_topic and current_topic in self.threads:
            thread = self.threads[current_topic]
            if thread.insights:
                latest_insight = thread.insights[-1]
                context_parts.append(f"Latest on {current_topic}: {latest_insight}")

        return "\n".join(context_parts) if context_parts else "No previous context"

    def suggest_memory_reference(self, current_message: str) -> Optional[str]:
        """
        Suggest natural memory reference if relevant to current message.

        Analyzes current message for keywords that match stored topics/details.
        Returns suggestion text if relevant match found.

        Args:
            current_message: User's current message

        Returns:
            Memory reference suggestion string, or None if no match
        """
        message_lower = current_message.lower()

        # Check if message mentions known topics
        for topic in self.threads:
            if topic in message_lower:
                thread = self.threads[topic]
                if thread.mentions:
                    # Generate suggestion based on thread history
                    mention_count = len(thread.mentions)
                    if thread.insights:
                        return f"Consider referencing {topic}: {thread.insights[-1]}"
                    else:
                        return f"You've mentioned {topic} {mention_count} times before"

        # Check if message mentions keywords from user details
        for key, detail in self.user_details.items():
            if any(word in message_lower for word in detail.value.lower().split()):
                if detail.confidence >= 0.7:
                    return f"Recall: {detail.value}"

        return None

    def update_thread_status(self, topic: str, message: str) -> str:
        """
        Update thread status based on resolution/deferral markers in message.

        Uses rule-based detection to identify when topic is resolved or deferred.

        Args:
            topic: Topic to update
            message: Message to analyze

        Returns:
            New status string
        """
        if topic not in self.threads:
            return "unknown"

        thread = self.threads[topic]
        message_lower = message.lower()

        # Resolution markers
        resolution_markers = [
            "got it",
            "thanks",
            "okay",
            "ok",
            "cool",
            "makes sense",
            "yeah",
            "right",
            "sure",
            "alright",
            "good",
            "perfect",
            "awesome",
            "great",
            "fixed",
            "solved",
        ]

        # Deferral markers
        deferral_markers = [
            "later",
            "next time",
            "we'll see",
            "not now",
            "maybe",
            "possibly",
            "eventually",
            "some time",
        ]

        if any(marker in message_lower for marker in resolution_markers):
            thread.status = "resolved"
        elif any(marker in message_lower for marker in deferral_markers):
            thread.status = "deferred"

        return thread.status

    def get_stats(self) -> Dict[str, int]:
        """
        Get memory statistics.

        Returns:
            Dict with counts: total_threads, active_threads, user_details, etc.
        """
        return {
            "total_threads": len(self.threads),
            "active_threads": len(self.get_active_threads()),
            "resolved_threads": len(self.get_resolved_threads()),
            "user_details": len(self.user_details),
            "high_confidence_details": len(
                [d for d in self.user_details.values() if d.confidence >= 0.7]
            ),
        }

    def clear_old_threads(self, max_age_minutes: int = 60) -> int:
        """
        Clear threads older than max_age_minutes.

        Useful for maintaining fresh conversation context.

        Args:
            max_age_minutes: Remove threads not mentioned in this many minutes

        Returns:
            Number of threads removed
        """
        now = datetime.now()
        cutoff = max_age_minutes * 60  # Convert to seconds

        removed_count = 0
        topics_to_remove = []

        for topic, thread in self.threads.items():
            age = (now - thread.last_mentioned).total_seconds()
            if age > cutoff:
                topics_to_remove.append(topic)
                removed_count += 1

        for topic in topics_to_remove:
            del self.threads[topic]

        return removed_count
