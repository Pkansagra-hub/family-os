"""
Unit tests for ProactivePrompt dataclass.

Tests:
- ProactivePrompt creation
- to_dict() serialization
- mark_responded() method
- Timestamp handling
"""

from datetime import datetime

import pytest
from backend.models.proactive_prompt import ProactivePrompt


class TestProactivePrompt:
    """Test ProactivePrompt functionality."""

    def test_proactive_prompt_creation(self):
        """Test creating proactive prompt."""
        prompt = ProactivePrompt(
            text="Until nutritionist gathers data, tell me how uneasy it was?",
            prompt_type="fill_gap",
            information_target="pain_severity",
        )

        assert prompt.text == "Until nutritionist gathers data, tell me how uneasy it was?"
        assert prompt.prompt_type == "fill_gap"
        assert prompt.information_target == "pain_severity"
        assert prompt.user_responded is False
        assert prompt.response_text is None
        assert isinstance(prompt.sent_at, datetime)

    def test_proactive_prompt_all_types(self):
        """Test all three prompt types."""
        fill_gap = ProactivePrompt(
            text="Tell me more", prompt_type="fill_gap", information_target="severity"
        )

        future_action = ProactivePrompt(
            text="I'll remind you", prompt_type="future_action", information_target="doctor_visit"
        )

        clarify = ProactivePrompt(
            text="Do you mean X or Y?", prompt_type="clarify", information_target="ambiguous_term"
        )

        assert fill_gap.prompt_type == "fill_gap"
        assert future_action.prompt_type == "future_action"
        assert clarify.prompt_type == "clarify"

    def test_proactive_prompt_to_dict(self):
        """Test prompt serialization."""
        prompt = ProactivePrompt(
            text="Test prompt", prompt_type="fill_gap", information_target="test_target"
        )

        data = prompt.to_dict()

        assert data["text"] == "Test prompt"
        assert data["prompt_type"] == "fill_gap"
        assert data["information_target"] == "test_target"
        assert data["user_responded"] is False
        assert data["response_text"] is None
        assert "sent_at" in data

    def test_proactive_prompt_mark_responded(self):
        """Test marking prompt as responded."""
        prompt = ProactivePrompt(
            text="Tell me more?", prompt_type="fill_gap", information_target="details"
        )

        assert prompt.user_responded is False
        assert prompt.response_text is None

        prompt.mark_responded("pain in left side")

        assert prompt.user_responded is True
        assert prompt.response_text == "pain in left side"

    def test_proactive_prompt_default_timestamp(self):
        """Test that sent_at defaults to current time."""
        before = datetime.utcnow()
        prompt = ProactivePrompt(text="Test", prompt_type="fill_gap", information_target="test")
        after = datetime.utcnow()

        assert before <= prompt.sent_at <= after

    def test_proactive_prompt_serialization_preserves_data(self):
        """Test that serialization preserves all data."""
        prompt = ProactivePrompt(
            text="Until nutritionist finishes, where is the pain?",
            prompt_type="fill_gap",
            information_target="pain_location",
        )

        prompt.mark_responded("left side of stomach")

        data = prompt.to_dict()

        assert data["text"] == prompt.text
        assert data["prompt_type"] == prompt.prompt_type
        assert data["information_target"] == prompt.information_target
        assert data["user_responded"] is True
        assert data["response_text"] == "left side of stomach"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
    pytest.main([__file__, "-v"])
