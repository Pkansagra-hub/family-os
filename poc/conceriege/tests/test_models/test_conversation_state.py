"""
Unit tests for ConversationState and related classes.

Tests:
- Referent creation and salience decay
- Scoreboard referent management
- Turn creation and tracking
- ConversationState management (QUD, history, gaps, proactive prompts)
"""

import pytest
from backend.models.conversation_state import ConversationState, Referent, Scoreboard, Turn


class TestReferent:
    """Test Referent dataclass."""

    def test_referent_creation(self):
        """Test creating referent with defaults."""
        ref = Referent(entity="milk")

        assert ref.entity == "milk"
        assert ref.salience == 1.0
        assert ref.user_hypothesis is False
        assert ref.sentiment is None
        assert ref.medical_condition is False
        assert ref.contradicted is False

    def test_referent_with_fields(self):
        """Test creating referent with all fields."""
        ref = Referent(
            entity="GERD",
            salience=0.9,
            user_hypothesis=False,
            sentiment="negative",
            medical_condition=True,
            contradicted=False,
        )

        assert ref.entity == "GERD"
        assert ref.salience == 0.9
        assert ref.medical_condition is True

    def test_referent_decay_salience(self):
        """Test salience decay."""
        ref = Referent(entity="milk", salience=1.0)

        ref.decay_salience(0.1)
        assert ref.salience == 0.9

        ref.decay_salience(0.2)
        assert ref.salience == 0.7

        # Should not go below 0
        ref.decay_salience(1.0)
        assert ref.salience == 0.0

    def test_referent_to_dict(self):
        """Test referent serialization."""
        ref = Referent(entity="milk", salience=0.9, user_hypothesis=True, sentiment="negative")

        data = ref.to_dict()

        assert data["entity"] == "milk"
        assert data["salience"] == 0.9
        assert data["user_hypothesis"] is True
        assert data["sentiment"] == "negative"
        assert "first_mentioned" in data


class TestScoreboard:
    """Test Scoreboard functionality."""

    def test_scoreboard_creation(self):
        """Test creating empty scoreboard."""
        scoreboard = Scoreboard()

        assert len(scoreboard.referents) == 0
        assert len(scoreboard.pending_specialists) == 0
        assert len(scoreboard.completed_tasks) == 0

    def test_scoreboard_add_referent(self):
        """Test adding referent."""
        scoreboard = Scoreboard()

        scoreboard.add_referent("milk", user_hypothesis=True, sentiment="negative")

        assert "milk" in scoreboard.referents
        assert scoreboard.referents["milk"].user_hypothesis is True
        assert scoreboard.referents["milk"].sentiment == "negative"
        assert scoreboard.referents["milk"].salience == 1.0

    def test_scoreboard_update_referent(self):
        """Test updating existing referent."""
        scoreboard = Scoreboard()

        # Add initial
        scoreboard.add_referent("milk")
        initial_salience = scoreboard.referents["milk"].salience
        assert initial_salience == 1.0  # Fresh referent

        # Decay it
        scoreboard.referents["milk"].decay_salience(0.5)
        assert scoreboard.referents["milk"].salience == 0.5

        # Re-add with new info (should refresh salience)
        scoreboard.add_referent("milk", user_hypothesis=True)
        assert scoreboard.referents["milk"].user_hypothesis is True
        assert scoreboard.referents["milk"].salience == 1.0  # Refreshed

    def test_scoreboard_update_salience(self):
        """Test salience decay for all referents."""
        scoreboard = Scoreboard()

        scoreboard.add_referent("milk")
        scoreboard.add_referent("coffee")
        scoreboard.add_referent("GERD")

        # All start at 1.0
        assert all(r.salience == 1.0 for r in scoreboard.referents.values())

        # Decay all
        scoreboard.update_salience(0.2)
        assert all(r.salience == 0.8 for r in scoreboard.referents.values())

    def test_scoreboard_get_top_referents(self):
        """Test getting top referents by salience."""
        scoreboard = Scoreboard()

        scoreboard.add_referent("milk")
        scoreboard.referents["milk"].salience = 0.5

        scoreboard.add_referent("coffee")
        scoreboard.referents["coffee"].salience = 0.9

        scoreboard.add_referent("GERD")
        scoreboard.referents["GERD"].salience = 1.0

        top_2 = scoreboard.get_top_referents(n=2)

        assert len(top_2) == 2
        assert top_2[0].entity == "GERD"
        assert top_2[1].entity == "coffee"

    def test_scoreboard_to_dict(self):
        """Test scoreboard serialization."""
        scoreboard = Scoreboard()
        scoreboard.add_referent("milk")
        scoreboard.pending_specialists.append("nutritionist")
        scoreboard.completed_tasks.append("task_123")

        data = scoreboard.to_dict()

        assert "milk" in data["referents"]
        assert "nutritionist" in data["pending_specialists"]
        assert "task_123" in data["completed_tasks"]


class TestTurn:
    """Test Turn dataclass."""

    def test_turn_creation_user(self):
        """Test creating user turn."""
        turn = Turn(
            user_message="milk is making me sick",
            agent_response="That's sad to hear. Looping in nutritionist.",
            turn_type="user",
        )

        assert turn.user_message == "milk is making me sick"
        assert turn.agent_response == "That's sad to hear. Looping in nutritionist."
        assert turn.turn_type == "user"

    def test_turn_creation_reactive(self):
        """Test creating reactive turn."""
        turn = Turn(user_message=None, agent_response="That's sad to hear.", turn_type="reactive")

        assert turn.user_message is None
        assert turn.turn_type == "reactive"

    def test_turn_to_dict(self):
        """Test turn serialization."""
        turn = Turn(
            user_message="test message", agent_response="test response", turn_type="proactive"
        )

        data = turn.to_dict()

        assert data["user_message"] == "test message"
        assert data["agent_response"] == "test response"
        assert data["turn_type"] == "proactive"
        assert "timestamp" in data


class TestConversationState:
    """Test ConversationState management."""

    def test_conversation_state_creation(self):
        """Test creating conversation state."""
        state = ConversationState(user_id="user_123", conversation_id="conv_abc")

        assert state.user_id == "user_123"
        assert state.conversation_id == "conv_abc"
        assert state.qud is None
        assert len(state.recent_history) == 0
        assert state.proactive_prompts_sent == 0

    def test_conversation_state_add_turn(self):
        """Test adding turns to history."""
        state = ConversationState(user_id="user_123", conversation_id="conv_abc")

        state.add_turn(
            user_message="milk is making me sick",
            agent_response="That's sad to hear.",
            turn_type="user",
        )

        assert len(state.recent_history) == 1
        assert state.recent_history[0].user_message == "milk is making me sick"

    def test_conversation_state_history_limit(self):
        """Test that history is limited to last 10 turns."""
        state = ConversationState(user_id="user_123", conversation_id="conv_abc")

        # Add 15 turns
        for i in range(15):
            state.add_turn(
                user_message=f"message {i}", agent_response=f"response {i}", turn_type="user"
            )

        # Should only keep last 10
        assert len(state.recent_history) == 10
        assert state.recent_history[0].user_message == "message 5"
        assert state.recent_history[-1].user_message == "message 14"

    def test_conversation_state_add_proactive_prompt(self):
        """Test tracking proactive prompts."""
        state = ConversationState(user_id="user_123", conversation_id="conv_abc")

        assert state.proactive_prompts_sent == 0
        assert state.last_proactive_at is None

        state.add_proactive_prompt("Tell me more?")

        assert state.proactive_prompts_sent == 1
        assert state.last_proactive_at is not None
        assert len(state.recent_history) == 1
        assert state.recent_history[0].turn_type == "proactive"

    def test_conversation_state_update_qud(self):
        """Test updating Question Under Discussion."""
        state = ConversationState(user_id="user_123", conversation_id="conv_abc")

        state.update_qud("What is causing my GERD?")

        assert state.qud == "What is causing my GERD?"

    def test_conversation_state_update_gaps(self):
        """Test updating information gaps."""
        state = ConversationState(user_id="user_123", conversation_id="conv_abc")

        gaps = ["pain_severity", "pain_location", "duration"]
        state.update_gaps(gaps)

        assert state.information_gaps == gaps

    def test_conversation_state_get_referents(self):
        """Test getting referents from scoreboard."""
        state = ConversationState(user_id="user_123", conversation_id="conv_abc")

        state.scoreboard.add_referent("milk")
        state.scoreboard.add_referent("GERD")

        referents = state.get_referents()

        assert "milk" in referents
        assert "GERD" in referents

    def test_conversation_state_to_dict(self):
        """Test conversation state serialization."""
        state = ConversationState(user_id="user_123", conversation_id="conv_abc")

        state.update_qud("What triggers GERD?")
        state.add_turn("test", "response", "user")
        state.update_gaps(["gap1"])

        data = state.to_dict()

        assert data["user_id"] == "user_123"
        assert data["conversation_id"] == "conv_abc"
        assert data["qud"] == "What triggers GERD?"
        assert len(data["recent_history"]) == 1
        assert data["information_gaps"] == ["gap1"]
        assert data["proactive_prompts_sent"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
