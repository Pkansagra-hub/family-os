"""
Context Manager - Temporal Topic Tracking

TOPIC 8: Context Awareness - Topic tracking with time references

Manages conversation context by:
1. Tracking when topics were mentioned (timestamps)
2. Calculating time deltas (how long since mentioned)
3. Classifying topic status (fresh/warm/cold/stale)
4. Suggesting topic bridges (connecting related topics)
5. Generating temporal context for LLM prompts

Example:
- Turn 1: User mentions "coffee" (fresh topic)
- Turn 3: User mentions "sleep" (fresh topic)
- Turn 5: Need to reference coffee again? System knows it's 4 turns old (warm)
- Response can bridge: "You mentioned coffee earlier... that might affect your sleep"
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class TopicContext:
    """Tracks temporal and state information for a conversation topic"""

    topic: str
    first_mentioned_at: datetime
    last_mentioned_at: datetime
    mention_count: int = 1
    status: str = "fresh"  # fresh, warm, cold, stale

    def __post_init__(self):
        """Update status after initialization"""
        self._update_status()

    def update_mention(self):
        """Update when topic is mentioned again"""
        self.last_mentioned_at = datetime.now()
        self.mention_count += 1
        self._update_status()

    def _update_status(self):
        """Classify topic status based on time since mention"""
        time_since = datetime.now() - self.last_mentioned_at
        seconds = time_since.total_seconds()

        # Status classification based on time
        if seconds < 30:  # Mentioned in last 30 seconds
            self.status = "fresh"
        elif seconds < 120:  # Mentioned in last 2 minutes
            self.status = "warm"
        elif seconds < 300:  # Mentioned in last 5 minutes
            self.status = "cold"
        else:
            self.status = "stale"

    @property
    def time_since_mention(self) -> float:
        """Return seconds since topic was last mentioned"""
        return (datetime.now() - self.last_mentioned_at).total_seconds()

    @property
    def time_since_mention_minutes(self) -> float:
        """Return minutes since topic was last mentioned"""
        return self.time_since_mention / 60.0

    @property
    def time_since_first_mention(self) -> float:
        """Return seconds since topic was first mentioned"""
        return (datetime.now() - self.first_mentioned_at).total_seconds()


class ContextManager:
    """
    Manages conversation context with temporal awareness.

    TOPIC 8: Context Awareness - RULE-BASED temporal tracking
    Tracks topics and their temporal properties to enable natural
    conversation bridging and context-aware responses.
    """

    def __init__(self):
        """Initialize context manager"""
        self.topic_contexts: Dict[str, TopicContext] = {}

        # Time thresholds for status classification (in seconds)
        self.FRESH_THRESHOLD = 30  # < 30 sec = fresh
        self.WARM_THRESHOLD = 120  # < 2 min = warm
        self.COLD_THRESHOLD = 300  # < 5 min = cold
        self.STALE_THRESHOLD = 600  # >= 10 min = stale

    def update_topic_context(self, topic: str) -> TopicContext:
        """
        Update context for a topic (called when topic is mentioned).

        Creates new context if topic not seen before, updates existing context.

        Args:
            topic: Topic name (e.g., "coffee", "sleep", "gerd")

        Returns:
            Updated TopicContext for the topic
        """
        if topic not in self.topic_contexts:
            # First mention of this topic
            self.topic_contexts[topic] = TopicContext(
                topic=topic, first_mentioned_at=datetime.now(), last_mentioned_at=datetime.now()
            )
        else:
            # Topic mentioned again - update
            self.topic_contexts[topic].update_mention()

        return self.topic_contexts[topic]

    def get_topic_context(self, topic: str) -> Optional[TopicContext]:
        """
        Get context information for a topic.

        Args:
            topic: Topic name

        Returns:
            TopicContext if topic has been mentioned, None otherwise
        """
        return self.topic_contexts.get(topic)

    def get_time_since_mention(self, topic: str) -> Optional[float]:
        """
        Get seconds since topic was last mentioned.

        Args:
            topic: Topic name

        Returns:
            Seconds since mention, or None if topic never mentioned
        """
        context = self.topic_contexts.get(topic)
        return context.time_since_mention if context else None

    def get_topic_status(self, topic: str) -> Optional[str]:
        """
        Get current status of a topic (fresh/warm/cold/stale).

        Args:
            topic: Topic name

        Returns:
            Status string or None if topic never mentioned
        """
        context = self.topic_contexts.get(topic)
        if context:
            context._update_status()
            return context.status
        return None

    def get_active_topics(self, max_age_minutes: float = 5.0) -> List[TopicContext]:
        """
        Get topics mentioned recently (within time threshold).

        Args:
            max_age_minutes: Maximum age in minutes to consider "active"

        Returns:
            List of TopicContext objects for active topics
        """
        max_age_seconds = max_age_minutes * 60
        active = []

        for context in self.topic_contexts.values():
            if context.time_since_mention <= max_age_seconds:
                active.append(context)

        # Sort by recency (most recent first)
        return sorted(active, key=lambda c: c.time_since_mention)

    def get_stale_topics(self, min_age_minutes: float = 10.0) -> List[TopicContext]:
        """
        Get topics mentioned long ago (not mentioned recently).

        Args:
            min_age_minutes: Minimum age in minutes to consider "stale"

        Returns:
            List of TopicContext objects for stale topics
        """
        min_age_seconds = min_age_minutes * 60
        stale = []

        for context in self.topic_contexts.values():
            if context.time_since_mention >= min_age_seconds:
                stale.append(context)

        return sorted(stale, key=lambda c: c.time_since_mention, reverse=True)

    def get_bridging_context(self, current_topic: Optional[str] = None) -> Optional[str]:
        """
        Get context to bridge from current topic to other topics.

        TOPIC 8: Context Awareness - LLM-based topic bridging
        Suggests which other topics might be relevant to reference
        based on temporal proximity and mention patterns.

        Args:
            current_topic: Current topic being discussed (or None)

        Returns:
            String suggestion for topic bridging, or None if no bridges available
        """
        active = self.get_active_topics(max_age_minutes=5.0)

        # Remove current topic from suggestions
        if current_topic:
            active = [t for t in active if t.topic != current_topic]

        if not active:
            return None

        # Build bridging suggestion
        bridge_topics = [t.topic for t in active[:2]]  # Top 2 most recent

        if len(bridge_topics) == 1:
            return f"You mentioned {bridge_topics[0]} recently"
        elif len(bridge_topics) == 2:
            return f"You mentioned {bridge_topics[0]} and {bridge_topics[1]} recently"

        return None

    def generate_temporal_context(self) -> str:
        """
        Generate temporal context description for LLM prompts.

        TOPIC 8: Context Awareness - Temporal context formatting
        Formats topic timings into natural language for inclusion
        in LLM prompts, helping model understand conversation flow.

        Returns:
            Formatted temporal context string (empty if no topics)
        """
        active = self.get_active_topics(max_age_minutes=10.0)

        if not active:
            return "No previous topics being discussed."

        context_lines = ["Topic timing context:"]

        for topic_ctx in active:
            # Build status description
            status_desc = {
                "fresh": f"just mentioned ({int(topic_ctx.time_since_mention)} sec ago)",
                "warm": f"mentioned recently ({topic_ctx.time_since_mention_minutes:.1f} min ago)",
                "cold": f"mentioned a bit ago ({topic_ctx.time_since_mention_minutes:.1f} min ago)",
                "stale": f"mentioned earlier ({topic_ctx.time_since_mention_minutes:.1f} min ago)",
            }

            description = status_desc.get(topic_ctx.status, "mentioned")
            context_lines.append(
                f"- {topic_ctx.topic}: {description} ({topic_ctx.mention_count} times)"
            )

        return "\n".join(context_lines)

    def get_stats(self) -> dict:
        """
        Get context manager statistics.

        Returns:
            Dictionary with stats (total_topics, active_count, stale_count)
        """
        active = self.get_active_topics()
        stale = self.get_stale_topics()

        return {
            "total_topics": len(self.topic_contexts),
            "active_topics": len(active),
            "stale_topics": len(stale),
            "fresh_topics": len([t for t in active if t.status == "fresh"]),
            "warm_topics": len([t for t in active if t.status == "warm"]),
        }

    def get_all_topics(self) -> List[TopicContext]:
        """Get all topics that have been mentioned"""
        return list(self.topic_contexts.values())

    def clear(self):
        """Clear all context"""
        self.topic_contexts.clear()
