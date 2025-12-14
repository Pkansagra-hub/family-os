"""
Unit tests for ConversationStore service.

Tests:
- get_or_create: Creating and retrieving conversations
- update: Updating conversation state
- add_turn: Adding turns to history
- get_history: Retrieving conversation history with limits
- clear: Clearing conversation state
- Memory management: History limit enforcement
- Stats: Conversation statistics
"""

import pytest
from backend.models.conversation_state import Turn
from backend.services.conversation_store import (
    ConversationStore,
    get_conversation_store,
    reset_conversation_store,
)


class TestConversationStoreBasics:
    """Test basic CRUD operations."""

    def test_get_or_create_new_conversation(self):
        """Test creating new conversation."""
        store = ConversationStore()
        user_id = "user_123"

        state = store.get_or_create(user_id)

        assert state.user_id == user_id
        assert state.conversation_id.startswith(f"conv_{user_id}_")
        assert len(state.recent_history) == 0
        assert state.proactive_prompts_sent == 0

    def test_get_or_create_existing_conversation(self):
        """Test retrieving existing conversation."""
        store = ConversationStore()
        user_id = "user_123"

        # Create first
        state1 = store.get_or_create(user_id)
        conv_id = state1.conversation_id

        # Retrieve again
        state2 = store.get_or_create(user_id)

        assert state2.conversation_id == conv_id
        assert state2 is state1  # Same object

    def test_update_conversation_state(self):
        """Test updating conversation state."""
        store = ConversationStore()
        user_id = "user_123"

        # Create initial state
        state = store.get_or_create(user_id)
        state.update_qud("What foods trigger GERD?")
        state.update_gaps(["pain_severity", "duration"])

        # Update in store
        store.update(user_id, state)

        # Retrieve and verify
        retrieved = store.get_or_create(user_id)
        assert retrieved.qud == "What foods trigger GERD?"
        assert retrieved.information_gaps == ["pain_severity", "duration"]

    def test_update_mismatched_user_id(self):
        """Test update with mismatched user_id raises error."""
        store = ConversationStore()
        user_id1 = "user_123"
        user_id2 = "user_456"

        state = store.get_or_create(user_id1)

        # Try to update with different user_id
        with pytest.raises(ValueError, match="User ID mismatch"):
            store.update(user_id2, state)

    def test_clear_conversation(self):
        """Test clearing conversation state."""
        store = ConversationStore()
        user_id = "user_123"

        # Create and add data
        state = store.get_or_create(user_id)
        state.add_turn("test message", "test response")

        # Clear
        store.clear(user_id)

        # Should create new conversation on next access
        new_state = store.get_or_create(user_id)
        assert new_state.conversation_id != state.conversation_id
        assert len(new_state.recent_history) == 0


class TestTurnManagement:
    """Test turn addition and history management."""

    def test_add_turn_basic(self):
        """Test adding a turn to conversation."""
        store = ConversationStore()
        user_id = "user_123"

        turn = Turn(
            user_message="milk is making me sick",
            agent_response="That's sad to hear. Looping in nutritionist.",
            turn_type="reactive",
        )

        store.add_turn(user_id, turn)

        # Verify turn added
        state = store.get_or_create(user_id)
        assert len(state.recent_history) == 1
        assert state.recent_history[0].user_message == "milk is making me sick"

    def test_add_turn_creates_conversation(self):
        """Test add_turn creates conversation if needed."""
        store = ConversationStore()
        user_id = "user_new"

        turn = Turn(user_message="test", agent_response="response")
        store.add_turn(user_id, turn)

        # Conversation should be created
        state = store.get_or_create(user_id)
        assert state.user_id == user_id
        assert len(state.recent_history) == 1

    def test_add_multiple_turns(self):
        """Test adding multiple turns."""
        store = ConversationStore()
        user_id = "user_123"

        # Add 5 turns
        for i in range(5):
            turn = Turn(user_message=f"message {i}", agent_response=f"response {i}")
            store.add_turn(user_id, turn)

        # Verify all added
        state = store.get_or_create(user_id)
        assert len(state.recent_history) == 5
        assert state.recent_history[0].user_message == "message 0"
        assert state.recent_history[4].user_message == "message 4"

    def test_turn_salience_decay(self):
        """Test salience decay on turn addition."""
        store = ConversationStore()
        user_id = "user_123"

        # Create state with referent
        state = store.get_or_create(user_id)
        state.scoreboard.add_referent("milk", user_hypothesis=True)

        initial_salience = state.scoreboard.referents["milk"].salience

        # Add turn (should trigger salience decay)
        turn = Turn(user_message="test", agent_response="response")
        store.add_turn(user_id, turn)

        # Verify salience decayed
        state = store.get_or_create(user_id)
        assert state.scoreboard.referents["milk"].salience < initial_salience


class TestHistoryRetrieval:
    """Test conversation history retrieval."""

    def test_get_history_empty(self):
        """Test getting history from empty conversation."""
        store = ConversationStore()
        user_id = "user_123"

        history = store.get_history(user_id)

        assert history == []

    def test_get_history_with_turns(self):
        """Test getting history with multiple turns."""
        store = ConversationStore()
        user_id = "user_123"

        # Add 3 turns
        for i in range(3):
            turn = Turn(user_message=f"msg {i}", agent_response=f"resp {i}")
            store.add_turn(user_id, turn)

        history = store.get_history(user_id)

        assert len(history) == 3
        assert history[0].user_message == "msg 0"
        assert history[2].user_message == "msg 2"

    def test_get_history_with_limit(self):
        """Test history limit enforcement."""
        store = ConversationStore()
        user_id = "user_123"

        # Add 10 turns
        for i in range(10):
            turn = Turn(user_message=f"msg {i}", agent_response=f"resp {i}")
            store.add_turn(user_id, turn)

        # Get only last 5
        history = store.get_history(user_id, limit=5)

        assert len(history) == 5
        assert history[0].user_message == "msg 5"  # Last 5 starts at index 5
        assert history[4].user_message == "msg 9"

    def test_get_history_limit_larger_than_actual(self):
        """Test limit larger than actual history."""
        store = ConversationStore()
        user_id = "user_123"

        # Add 3 turns
        for i in range(3):
            turn = Turn(user_message=f"msg {i}", agent_response=f"resp {i}")
            store.add_turn(user_id, turn)

        # Request 10
        history = store.get_history(user_id, limit=10)

        assert len(history) == 3


class TestMemoryManagement:
    """Test memory limits and history management."""

    def test_max_history_turns_enforced(self):
        """Test that history is limited to max_history_turns."""
        store = ConversationStore(max_history_turns=5)
        user_id = "user_123"

        # Add 10 turns
        for i in range(10):
            turn = Turn(user_message=f"msg {i}", agent_response=f"resp {i}")
            store.add_turn(user_id, turn)

        # Should only keep last 5
        state = store.get_or_create(user_id)
        assert len(state.recent_history) == 5
        assert state.recent_history[0].user_message == "msg 5"
        assert state.recent_history[4].user_message == "msg 9"

    def test_default_max_history_turns(self):
        """Test default max_history_turns is 10."""
        store = ConversationStore()
        user_id = "user_123"

        # Add 15 turns
        for i in range(15):
            turn = Turn(user_message=f"msg {i}", agent_response=f"resp {i}")
            store.add_turn(user_id, turn)

        # Should only keep last 10
        state = store.get_or_create(user_id)
        assert len(state.recent_history) == 10
        assert state.recent_history[0].user_message == "msg 5"
        assert state.recent_history[9].user_message == "msg 14"


class TestMultiUserSupport:
    """Test handling multiple users."""

    def test_multiple_users_isolated(self):
        """Test that different users have separate conversations."""
        store = ConversationStore()
        user1 = "user_123"
        user2 = "user_456"

        # Add turns for user1
        turn1 = Turn(user_message="user1 msg", agent_response="user1 resp")
        store.add_turn(user1, turn1)

        # Add turns for user2
        turn2 = Turn(user_message="user2 msg", agent_response="user2 resp")
        store.add_turn(user2, turn2)

        # Verify isolation
        state1 = store.get_or_create(user1)
        state2 = store.get_or_create(user2)

        assert state1.recent_history[0].user_message == "user1 msg"
        assert state2.recent_history[0].user_message == "user2 msg"
        assert state1.conversation_id != state2.conversation_id

    def test_get_active_conversations(self):
        """Test getting list of active conversations."""
        store = ConversationStore()

        # Create 3 conversations
        store.get_or_create("user_1")
        store.get_or_create("user_2")
        store.get_or_create("user_3")

        active = store.get_active_conversations()

        assert len(active) == 3
        assert "user_1" in active
        assert "user_2" in active
        assert "user_3" in active


class TestStatistics:
    """Test conversation statistics."""

    def test_get_stats_empty(self):
        """Test stats with no conversations."""
        store = ConversationStore()

        stats = store.get_stats()

        assert stats["total_conversations"] == 0
        assert stats["total_turns"] == 0
        assert stats["avg_turns_per_conversation"] == 0
        assert stats["active_users"] == []

    def test_get_stats_with_data(self):
        """Test stats with multiple conversations."""
        store = ConversationStore()

        # User1: 5 turns
        for i in range(5):
            store.add_turn("user_1", Turn(user_message=f"msg {i}", agent_response="resp"))

        # User2: 3 turns
        for i in range(3):
            store.add_turn("user_2", Turn(user_message=f"msg {i}", agent_response="resp"))

        stats = store.get_stats()

        assert stats["total_conversations"] == 2
        assert stats["total_turns"] == 8
        assert stats["avg_turns_per_conversation"] == 4.0
        assert "user_1" in stats["active_users"]
        assert "user_2" in stats["active_users"]


class TestSingletonPattern:
    """Test singleton instance management."""

    def test_get_conversation_store_singleton(self):
        """Test singleton returns same instance."""
        reset_conversation_store()

        store1 = get_conversation_store()
        store2 = get_conversation_store()

        assert store1 is store2

    def test_reset_conversation_store(self):
        """Test resetting singleton."""
        reset_conversation_store()

        store1 = get_conversation_store()
        store1.get_or_create("user_123")

        reset_conversation_store()
        store2 = get_conversation_store()

        # Should be different instance
        assert store2 is not store1
        # Should be empty
        assert len(store2.get_active_conversations()) == 0


class TestConversationID:
    """Test conversation ID generation."""

    def test_conversation_id_format(self):
        """Test conversation ID has correct format."""
        store = ConversationStore()
        user_id = "user_123"

        state = store.get_or_create(user_id)

        assert state.conversation_id.startswith(f"conv_{user_id}_")
        # Should have 12 hex characters after prefix
        suffix = state.conversation_id.split("_")[-1]
        assert len(suffix) == 12
        assert all(c in "0123456789abcdef" for c in suffix)

    def test_conversation_id_uniqueness(self):
        """Test that conversation IDs are unique."""
        store = ConversationStore()

        # Create multiple conversations for same user (by clearing between)
        conv_ids = []
        for _ in range(3):
            state = store.get_or_create("user_123")
            conv_ids.append(state.conversation_id)
            store.clear("user_123")

        # All should be unique
        assert len(set(conv_ids)) == 3


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_get_history_nonexistent_user(self):
        """Test getting history for non-existent user."""
        store = ConversationStore()

        # Should create conversation and return empty history
        history = store.get_history("user_nonexistent")

        assert history == []

    def test_clear_nonexistent_user(self):
        """Test clearing non-existent user (no error)."""
        store = ConversationStore()

        # Should not raise error
        store.clear("user_nonexistent")

    def test_add_turn_with_none_messages(self):
        """Test adding turn with None messages (proactive prompt)."""
        store = ConversationStore()
        user_id = "user_123"

        turn = Turn(user_message=None, agent_response="Proactive prompt", turn_type="proactive")
        store.add_turn(user_id, turn)

        state = store.get_or_create(user_id)
        assert state.recent_history[0].user_message is None
        assert state.recent_history[0].turn_type == "proactive"

    def test_conversation_state_preservation(self):
        """Test that conversation state is preserved across operations."""
        store = ConversationStore()
        user_id = "user_123"

        # Create state with complex data
        state = store.get_or_create(user_id)
        state.update_qud("What triggers GERD?")
        state.scoreboard.add_referent("milk", user_hypothesis=True, sentiment="negative")
        state.scoreboard.add_referent("coffee", medical_condition=False)
        state.update_gaps(["severity", "duration"])

        # Add turns
        store.add_turn(user_id, Turn(user_message="msg1", agent_response="resp1"))

        # Retrieve and verify all state preserved
        retrieved = store.get_or_create(user_id)
        assert retrieved.qud == "What triggers GERD?"
        assert "milk" in retrieved.scoreboard.referents
        assert retrieved.scoreboard.referents["milk"].user_hypothesis is True
        assert retrieved.scoreboard.referents["milk"].sentiment == "negative"
        assert "coffee" in retrieved.scoreboard.referents
        assert retrieved.information_gaps == ["severity", "duration"]
        assert len(retrieved.recent_history) == 1
