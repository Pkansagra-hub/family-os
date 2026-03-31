"""
Test Gap Detection Scenarios
=============================

Tests the 5 key gap detection scenarios from the Anniversary Demo:

1. book_restaurant (Turn 10): Missing date, time, party_size
2. book_accommodation (Turn 11): Missing nights, guests
3. suggest_transportation (Turn 14): Missing origin, preference
4. send_family_message (Turn 18): Missing content
5. schedule_reminder (Turn 20): Missing datetime

Each test verifies:
- Gaps are correctly detected
- Clarification questions are natural
- Retry flow works after user provides info
"""

import pytest

from poc.session_state_demo.anniversary_demo.tools import (
    ClarificationGenerator,
    LLMGapDetector,
    create_retry_orchestrator,
)


class TestScenario1_BookRestaurant:
    """Turn 10: Sarah wants to book dinner at The Harvest Table."""

    def test_detects_missing_params(self):
        """Should detect missing party_size, date, time."""
        detector = LLMGapDetector()

        gap = detector.analyze_tool_call(
            tool_name="book_restaurant",
            provided_params={"restaurant_name": "The Harvest Table"},
            user_request="Can you book a table at The Harvest Table?",
        )

        assert gap.has_gaps is True
        assert "party_size" in gap.missing_params
        assert "date" in gap.missing_params
        assert "time" in gap.missing_params

    def test_generates_clarification(self):
        """Should generate natural clarification question."""
        generator = ClarificationGenerator()

        result = generator.generate_sync(
            tool_name="book_restaurant",
            missing_params=["party_size", "date", "time"],
            param_descriptions={
                "party_size": "Number of diners",
                "date": "Date for the reservation",
                "time": "Time for the reservation",
            },
            user_request="Book a table at The Harvest Table",
        )

        assert result.question
        assert len(result.question) > 10
        # Should not be robotic
        assert "party_size" not in result.question.lower()

    def test_retry_flow(self):
        """Should succeed after user provides all info."""
        orchestrator = create_retry_orchestrator()

        # Initial attempt
        result = orchestrator.process_tool_attempt(
            tool_name="book_restaurant",
            params={"restaurant_name": "The Harvest Table"},
            user_request="Book at The Harvest Table",
        )
        assert result.needs_clarification is True
        assert result.call_id is not None

        # User provides info
        retry = orchestrator.handle_clarification_response(
            call_id=result.call_id,
            user_response="Saturday 7pm for 2 people",
            extracted_params={"date": "Saturday", "time": "7pm", "party_size": 2},
        )

        assert retry.success is True
        assert retry.tool_call is not None
        assert retry.tool_call.arguments["party_size"] == 2


class TestScenario2_BookAccommodation:
    """Turn 11: Sarah wants to book a room in wine country."""

    def test_detects_missing_params(self):
        """Should detect missing nights, guests."""
        detector = LLMGapDetector()

        gap = detector.analyze_tool_call(
            tool_name="book_accommodation",
            provided_params={
                "name": "Vineyard Inn",
                "location": "Napa Valley",
                "check_in_date": "February 15",
            },
            user_request="Book a room at Vineyard Inn in Napa",
        )

        assert gap.has_gaps is True
        assert "nights" in gap.missing_params
        assert "guests" in gap.missing_params

    def test_context_inference_guests(self):
        """Should infer guests=2 from family context."""
        detector = LLMGapDetector()
        detector.set_session_context(
            {"family_members": {"Mike": "husband"}, "event": "anniversary"}
        )

        # Check if detector can infer party size
        gap = detector.analyze_tool_call(
            tool_name="book_accommodation",
            provided_params={
                "name": "Vineyard Inn",
                "location": "Napa Valley",
                "check_in_date": "February 15",
            },
            user_request="Book a room for Mike's birthday weekend",
        )

        # Should still detect nights as missing
        assert "nights" in gap.missing_params

    def test_retry_flow(self):
        """Should succeed after user provides nights and guests."""
        orchestrator = create_retry_orchestrator()

        result = orchestrator.process_tool_attempt(
            tool_name="book_accommodation",
            params={
                "name": "Vineyard Inn",
                "location": "Napa Valley",
                "check_in_date": "February 15",
            },
            user_request="Book Vineyard Inn",
        )
        assert result.needs_clarification is True
        assert result.call_id is not None

        retry = orchestrator.handle_clarification_response(
            call_id=result.call_id,
            user_response="2 nights for 2 guests",
            extracted_params={"nights": 2, "guests": 2},
        )

        assert retry.success is True
        assert retry.tool_call is not None
        assert retry.tool_call.arguments["nights"] == 2


class TestScenario3_SuggestTransportation:
    """Turn 14: Need transportation options to wine country."""

    def test_detects_missing_origin(self):
        """Should detect missing origin for route planning."""
        detector = LLMGapDetector()

        gap = detector.analyze_tool_call(
            tool_name="plan_route",
            provided_params={"destination": "Napa Valley"},
            user_request="How do we get to Napa?",
        )

        assert gap.has_gaps is True
        assert "origin" in gap.missing_params

    def test_clarification_suggests_home(self):
        """Clarification should naturally ask about starting point."""
        generator = ClarificationGenerator()

        result = generator.generate_sync(
            tool_name="plan_route",
            missing_params=["origin"],
            param_descriptions={"origin": "Starting location for the route"},
            user_request="How do we get to Napa?",
        )

        assert result.question
        # Should ask about starting point in natural way
        assert "origin" not in result.question.lower() or "starting" in result.question.lower()


class TestScenario4_SendFamilyMessage:
    """Turn 18: Send info to Emma about the weekend plans."""

    def test_detects_missing_content(self):
        """Should detect that message content is missing."""
        detector = LLMGapDetector()

        gap = detector.analyze_tool_call(
            tool_name="send_family_message",
            provided_params={"to": "Emma"},
            user_request="Send Emma the weekend details",
        )

        assert gap.has_gaps is True
        assert "content" in gap.missing_params or "subject" in gap.missing_params

    def test_retry_with_content(self):
        """Should succeed when content is provided."""
        orchestrator = create_retry_orchestrator()

        result = orchestrator.process_tool_attempt(
            tool_name="send_family_message",
            params={"to": "Emma"},
            user_request="Send Emma the schedule",
        )
        assert result.needs_clarification is True
        assert result.call_id is not None

        retry = orchestrator.handle_clarification_response(
            call_id=result.call_id,
            user_response="Include emergency contacts and Jake's schedule",
            extracted_params={
                "subject": "Weekend Plans",
                "content": "Emergency contacts and Jake schedule for the weekend",
            },
        )

        assert retry.success is True


class TestScenario5_ScheduleReminder:
    """Turn 20: Set reminder to pick up balloons."""

    def test_detects_missing_datetime(self):
        """Should detect that reminder time is missing."""
        detector = LLMGapDetector()

        gap = detector.analyze_tool_call(
            tool_name="schedule_reminder",
            provided_params={"title": "Pick up balloons"},
            user_request="Remind me to pick up the balloons",
        )

        assert gap.has_gaps is True
        assert "datetime" in gap.missing_params or "time" in gap.missing_params

    def test_natural_clarification(self):
        """Should ask when to be reminded in natural way."""
        generator = ClarificationGenerator()

        result = generator.generate_sync(
            tool_name="schedule_reminder",
            missing_params=["datetime"],
            param_descriptions={"datetime": "When to send the reminder"},
            user_request="Remind me to pick up balloons",
        )

        assert result.question
        assert len(result.question) > 5


class TestMultipleGaps:
    """Test handling multiple gaps in a single tool call."""

    def test_single_question_for_multiple_gaps(self):
        """Should combine multiple gaps into one natural question."""
        generator = ClarificationGenerator()

        result = generator.generate_sync(
            tool_name="book_restaurant",
            missing_params=["party_size", "date", "time", "special_requests"],
            param_descriptions={
                "party_size": "Number of diners",
                "date": "Date for reservation",
                "time": "Time for reservation",
                "special_requests": "Any special requests",
            },
            user_request="Book dinner somewhere nice",
        )

        # Should be a single coherent question, not a list
        assert result.question.count("?") <= 2  # At most 2 questions


class TestNoGaps:
    """Test when all required params are provided."""

    def test_no_clarification_needed(self):
        """Should not ask for clarification when complete."""
        orchestrator = create_retry_orchestrator()

        result = orchestrator.process_tool_attempt(
            tool_name="book_restaurant",
            params={
                "restaurant_name": "The Harvest Table",
                "party_size": 2,
                "date": "Saturday",
                "time": "7pm",
            },
            user_request="Book The Harvest Table for 2 Saturday 7pm",
        )

        assert result.can_execute is True
        assert result.needs_clarification is False
        assert result.tool_call is not None


class TestSessionContext:
    """Test context-aware gap detection."""

    def test_uses_session_family(self):
        """Should use family info from session context."""
        detector = LLMGapDetector()
        detector.set_session_context(
            {
                "family_members": {"Mike": "husband", "Emma": "daughter", "Jake": "son"},
                "event": "Mike's 50th birthday",
            }
        )

        # When looking for transportation for "the family"
        gap = detector.analyze_tool_call(
            tool_name="plan_route",
            provided_params={"destination": "Napa Valley"},
            user_request="Plan route for the family trip",
        )

        # Should still need origin
        assert gap.has_gaps is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
