"""
Conversation Store Service

In-memory storage for conversation history and state management.
Provides CRUD operations for ConversationState objects.

Research basis:
- Dialogue State Tracking (Williams 2007)
- Conversational Memory Management (Grosz & Sidner 1986)
"""

import uuid
from typing import Dict, List, Optional

from backend.models.conversation_state import ConversationState, Turn


class ConversationStore:
    """
    In-memory storage for conversation states.

    Manages conversation state per user with history limits for memory efficiency.
    Suitable for PoC and single-instance deployments.

    Attributes:
        _conversations: Dictionary mapping user_id to ConversationState
        _max_history_turns: Maximum number of turns to keep per conversation
    """

    def __init__(self, max_history_turns: int = 10):
        """
        Initialize conversation store.

        Args:
            max_history_turns: Maximum number of turns to keep in history
        """
        self._conversations: Dict[str, ConversationState] = {}
        self._max_history_turns = max_history_turns

    def get_or_create(self, user_id: str) -> ConversationState:
        """
        Get existing conversation or create new one.

        Args:
            user_id: FamilyOS user ID

        Returns:
            ConversationState for the user
        """
        if user_id not in self._conversations:
            from collections import deque

            conversation_id = self._generate_conversation_id(user_id)
            state = ConversationState(user_id=user_id, conversation_id=conversation_id)

            # Override the default deque maxlen with store's configured value
            state.recent_history = deque(maxlen=self._max_history_turns)

            self._conversations[user_id] = state

        return self._conversations[user_id]

    def update(self, user_id: str, state: ConversationState) -> None:
        """
        Update conversation state for user.

        Args:
            user_id: FamilyOS user ID
            state: Updated ConversationState

        Raises:
            ValueError: If user_id doesn't match state.user_id
        """
        if state.user_id != user_id:
            raise ValueError(f"User ID mismatch: {user_id} != {state.user_id}")

        self._conversations[user_id] = state

    def add_turn(
        self,
        user_id: str,
        turn: Turn,
    ) -> None:
        """
        Add a turn to conversation history.

        Creates conversation if it doesn't exist.

        Args:
            user_id: FamilyOS user ID
            turn: Turn object to add
        """
        state = self.get_or_create(user_id)

        # Add turn to history (deque automatically limits size)
        state.recent_history.append(turn)

        # Update scoreboard salience decay
        state.scoreboard.update_salience(decay_rate=0.05)

    def get_history(self, user_id: str, limit: int = 10) -> List[Turn]:
        """
        Get recent conversation history.

        Args:
            user_id: FamilyOS user ID
            limit: Maximum number of turns to return

        Returns:
            List of Turn objects (most recent first)
        """
        state = self.get_or_create(user_id)

        # Convert deque to list and limit
        history = list(state.recent_history)
        return history[-limit:] if len(history) > limit else history

    def clear(self, user_id: str) -> None:
        """
        Clear conversation state for user.

        Useful for starting new demo or resetting conversation.

        Args:
            user_id: FamilyOS user ID
        """
        if user_id in self._conversations:
            del self._conversations[user_id]

    def get_active_conversations(self) -> List[str]:
        """
        Get list of all active user IDs.

        Returns:
            List of user IDs with active conversations
        """
        return list(self._conversations.keys())

    def get_stats(self) -> dict:
        """
        Get statistics about stored conversations.

        Returns:
            Dictionary with conversation statistics
        """
        total_turns = sum(len(state.recent_history) for state in self._conversations.values())

        return {
            "total_conversations": len(self._conversations),
            "total_turns": total_turns,
            "avg_turns_per_conversation": (
                total_turns / len(self._conversations) if self._conversations else 0
            ),
            "active_users": list(self._conversations.keys()),
        }

    def _generate_conversation_id(self, user_id: str) -> str:
        """
        Generate unique conversation ID.

        Args:
            user_id: FamilyOS user ID

        Returns:
            Unique conversation ID (ULID-like format)
        """
        # Use UUID4 for simplicity in PoC
        # In production, use ULID for sortable IDs
        return f"conv_{user_id}_{uuid.uuid4().hex[:12]}"


# Singleton instance for easy access across the application
_store_instance: Optional[ConversationStore] = None


def get_conversation_store(max_history_turns: int = 10) -> ConversationStore:
    """
    Get singleton conversation store instance.

    Args:
        max_history_turns: Maximum turns to keep (only used on first call)

    Returns:
        ConversationStore singleton instance
    """
    global _store_instance
    if _store_instance is None:
        _store_instance = ConversationStore(max_history_turns=max_history_turns)
    return _store_instance


def reset_conversation_store() -> None:
    """
    Reset singleton instance (useful for testing).
    """
    global _store_instance
    _store_instance = None
