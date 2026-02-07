"""
Tests for Calendar & Reminder Tools
====================================

Tests for Epic 2.3: Calendar & Reminder Tools implementation.
Verifies all 3 calendar tools work correctly.
"""

from poc.session_state_demo.anniversary_demo.tools.calendar import (
    CALENDAR_TOOLS,
    CalendarStore,
    create_calendar_event,
    execute_calendar_tool,
    generate_trip_summary,
    get_demo_trip_summary,
    schedule_reminder,
)


class TestCreateCalendarEvent:
    """Tests for create_calendar_event tool."""

    def setup_method(self):
        """Clear calendar store before each test."""
        CalendarStore.get_instance().clear()

    def test_create_basic_event(self):
        """Test creating a basic calendar event."""
        result = create_calendar_event(
            title="Team Meeting",
            start="2026-02-14 10:00",
            end="2026-02-14 11:00",
        )

        assert result["success"] is True
        assert "event" in result
        assert result["event"]["title"] == "Team Meeting"
        assert result["event"]["event_id"].startswith("EVT-")

    def test_create_event_with_location(self):
        """Test creating event with location."""
        result = create_calendar_event(
            title="Tech Summit Napa",
            start="friday",
            end="sunday",
            location="Napa Convention Center",
        )

        assert result["success"] is True
        assert result["event"]["location"] == "Napa Convention Center"

    def test_create_private_event(self):
        """Test creating a private event."""
        result = create_calendar_event(
            title="Tech Summit Napa",
            start="friday",
            end="sunday",
            visibility="private",
            notes="COVER STORY - do not share",
        )

        assert result["success"] is True
        assert result["event"]["visibility"] == "private"
        assert "privacy_note" in result
        assert "PRIVATE" in result["privacy_note"]

    def test_create_event_with_reminder(self):
        """Test creating event with custom reminder time."""
        result = create_calendar_event(
            title="Birthday Dinner",
            start="2026-02-14 19:00",
            end="2026-02-14 21:00",
            reminder_minutes=60,
        )

        assert result["success"] is True
        assert result["event"]["reminder_minutes"] == 60

    def test_event_stored_in_store(self):
        """Test that events are stored."""
        create_calendar_event(
            title="Test Event",
            start="2026-02-14",
            end="2026-02-15",
        )

        store = CalendarStore.get_instance()
        events = store.get_all_events()
        assert len(events) == 1
        assert events[0].title == "Test Event"

    def test_invalid_visibility_defaults(self):
        """Test that invalid visibility defaults to 'default'."""
        result = create_calendar_event(
            title="Test",
            start="2026-02-14",
            end="2026-02-15",
            visibility="invalid_visibility",
        )

        assert result["success"] is True
        assert result["event"]["visibility"] == "default"


class TestScheduleReminder:
    """Tests for schedule_reminder tool."""

    def setup_method(self):
        """Clear calendar store before each test."""
        CalendarStore.get_instance().clear()

    def test_schedule_basic_reminder(self):
        """Test scheduling a basic reminder."""
        result = schedule_reminder(
            recipient="user",
            message="Brief Emma on Jake-sitting instructions",
            datetime_str="friday_evening",
        )

        assert result["success"] is True
        assert "reminder" in result
        assert result["reminder"]["message"] == "Brief Emma on Jake-sitting instructions"
        assert result["reminder"]["reminder_id"].startswith("REM-")

    def test_reminder_for_specific_person(self):
        """Test scheduling reminder for specific recipient."""
        result = schedule_reminder(
            recipient="Sarah",
            message="Pack for trip",
            datetime_str="thursday_night",
        )

        assert result["success"] is True
        assert result["will_notify"] == "Sarah"

    def test_reminder_stored_in_store(self):
        """Test that reminders are stored."""
        schedule_reminder(
            recipient="user",
            message="Test reminder",
            datetime_str="tomorrow",
        )

        store = CalendarStore.get_instance()
        reminders = store.get_all_reminders()
        assert len(reminders) == 1

    def test_get_reminders_for_recipient(self):
        """Test getting reminders for specific recipient."""
        schedule_reminder(
            recipient="user",
            message="Reminder 1",
            datetime_str="monday",
        )
        schedule_reminder(
            recipient="user",
            message="Reminder 2",
            datetime_str="tuesday",
        )
        schedule_reminder(
            recipient="sarah",
            message="Reminder 3",
            datetime_str="wednesday",
        )

        store = CalendarStore.get_instance()
        user_reminders = store.get_reminders_for("user")
        assert len(user_reminders) == 2


class TestGenerateTripSummary:
    """Tests for generate_trip_summary tool."""

    def setup_method(self):
        """Clear calendar store before each test."""
        CalendarStore.get_instance().clear()

    def test_generate_basic_summary(self):
        """Test generating a basic trip summary."""
        result = generate_trip_summary(
            session_id="test_session",
            accommodation={
                "name": "Test Hotel",
                "location": "Test City",
                "check_in": "Saturday",
                "nights": 2,
                "cost": 300.0,
            },
        )

        assert result["success"] is True
        assert "summary" in result
        assert "formatted_text" in result
        assert result["summary"]["session_id"] == "test_session"

    def test_generate_complete_summary(self):
        """Test generating a complete summary with all fields."""
        result = generate_trip_summary(
            session_id="complete_test",
            accommodation={
                "name": "Vineyard Inn",
                "location": "Sonoma",
                "check_in": "Saturday",
                "nights": 2,
                "confirmation": "ABC123",
                "cost": 578.00,
            },
            dining=[
                {
                    "name": "Della Santina's",
                    "date": "Saturday",
                    "time": "7:00 PM",
                    "party_size": 2,
                    "confirmation": "XYZ789",
                    "special_requests": ["Birthday", "No shellfish"],
                }
            ],
            activities=[
                {
                    "name": "Couples Massage",
                    "date": "Sunday",
                    "time": "11:00 AM",
                    "confirmation": "SPA123",
                    "cost": 320.00,
                }
            ],
            transportation={
                "origin": "San Francisco",
                "destination": "Sonoma",
                "route_type": "scenic",
                "distance": 52.8,
                "duration": 85,
            },
            weather={
                "Saturday": "Sunny, 72F",
                "Sunday": "Rain likely",
            },
            budget={
                "total": 1500.0,
                "spent": 898.0,
                "remaining": 602.0,
            },
            notes=["Important note 1", "Important note 2"],
        )

        assert result["success"] is True
        formatted = result["formatted_text"]

        # Check all sections are present
        assert "ACCOMMODATION" in formatted
        assert "Vineyard Inn" in formatted
        assert "DINING" in formatted
        assert "Della Santina's" in formatted
        assert "ACTIVITIES" in formatted
        assert "Couples Massage" in formatted
        assert "TRANSPORTATION" in formatted
        assert "scenic" in formatted
        assert "WEATHER" in formatted
        assert "BUDGET" in formatted
        assert "NOTES" in formatted

    def test_summary_stored_in_store(self):
        """Test that summaries are stored."""
        generate_trip_summary(
            session_id="stored_test",
        )

        store = CalendarStore.get_instance()
        summary = store.get_summary("stored_test")
        assert summary is not None
        assert summary.session_id == "stored_test"


class TestGetDemoTripSummary:
    """Tests for get_demo_trip_summary helper."""

    def setup_method(self):
        """Clear calendar store before each test."""
        CalendarStore.get_instance().clear()

    def test_demo_summary_complete(self):
        """Test demo summary has all expected data."""
        result = get_demo_trip_summary()

        assert result["success"] is True
        summary = result["summary"]

        # Check accommodation
        assert summary["accommodation"]["name"] == "Vineyard Inn"
        assert summary["accommodation"]["location"] == "Sonoma, CA"

        # Check dining
        assert len(summary["dining"]) == 1
        assert summary["dining"][0]["name"] == "Della Santina's"
        assert "shellfish allergy" in summary["dining"][0]["special_requests"][1]

        # Check activities
        assert len(summary["activities"]) == 1
        assert summary["activities"][0]["name"] == "Couples Massage"

        # Check transportation
        assert summary["transportation"]["origin"] == "San Francisco"
        assert summary["transportation"]["route_type"] == "scenic"

        # Check weather
        assert "Saturday" in summary["weather"]
        assert "Sunday" in summary["weather"]

        # Check family arrangements
        assert summary["family_arrangements"]["childcare"] == "Emma watching Jake"

        # Check budget
        assert summary["budget"]["total"] == 1750.00

    def test_demo_summary_formatted_text(self):
        """Test demo summary formatted text is complete."""
        result = get_demo_trip_summary()
        formatted = result["formatted_text"]

        # Should have all major sections
        assert "TRIP SUMMARY" in formatted
        assert "Vineyard Inn" in formatted
        assert "Della Santina's" in formatted
        assert "Couples Massage" in formatted
        assert "San Francisco" in formatted
        assert "Emma watching Jake" in formatted
        assert "Tech Summit Napa" in formatted


class TestExecuteCalendarTool:
    """Tests for execute_calendar_tool dispatcher."""

    def setup_method(self):
        """Clear calendar store before each test."""
        CalendarStore.get_instance().clear()

    def test_execute_known_tool(self):
        """Test executing a known tool by name."""
        result = execute_calendar_tool(
            "create_calendar_event",
            {"title": "Test", "start": "2026-02-14", "end": "2026-02-15"},
        )

        assert result["success"] is True
        assert "event" in result

    def test_execute_unknown_tool(self):
        """Test executing unknown tool returns error."""
        result = execute_calendar_tool(
            "unknown_tool",
            {},
        )

        assert result["success"] is False
        assert "available_tools" in result

    def test_execute_with_invalid_params(self):
        """Test executing tool with invalid params returns error."""
        result = execute_calendar_tool(
            "create_calendar_event",
            {"wrong_param": "value"},
        )

        assert result["success"] is False


class TestCalendarStore:
    """Tests for CalendarStore singleton."""

    def setup_method(self):
        """Clear store before each test."""
        CalendarStore.get_instance().clear()

    def test_singleton_instance(self):
        """Test CalendarStore is a singleton."""
        store1 = CalendarStore.get_instance()
        store2 = CalendarStore.get_instance()
        assert store1 is store2

    def test_get_event_by_id(self):
        """Test getting event by ID."""
        result = create_calendar_event(
            title="Test Event",
            start="2026-02-14",
            end="2026-02-15",
        )

        event_id = result["event"]["event_id"]
        store = CalendarStore.get_instance()
        event = store.get_event(event_id)

        assert event is not None
        assert event.title == "Test Event"

    def test_get_reminder_by_id(self):
        """Test getting reminder by ID."""
        result = schedule_reminder(
            recipient="user",
            message="Test",
            datetime_str="tomorrow",
        )

        reminder_id = result["reminder"]["reminder_id"]
        store = CalendarStore.get_instance()
        reminder = store.get_reminder(reminder_id)

        assert reminder is not None
        assert reminder.message == "Test"


class TestCalendarToolsRegistry:
    """Tests for CALENDAR_TOOLS registry."""

    def test_all_tools_registered(self):
        """Test all 3 calendar tools are in the registry."""
        expected_tools = [
            "create_calendar_event",
            "schedule_reminder",
            "generate_trip_summary",
        ]

        for tool_name in expected_tools:
            assert tool_name in CALENDAR_TOOLS, f"Missing tool: {tool_name}"

    def test_all_tools_are_callable(self):
        """Test all registered tools are callable."""
        for tool_name, tool_func in CALENDAR_TOOLS.items():
            assert callable(tool_func), f"Tool not callable: {tool_name}"


class TestTripSummaryFormatting:
    """Tests for TripSummary formatting."""

    def test_empty_summary_formatting(self):
        """Test formatting an empty summary."""
        result = generate_trip_summary(session_id="empty")
        formatted = result["formatted_text"]

        assert "TRIP SUMMARY" in formatted
        assert "Generated:" in formatted

    def test_summary_with_family_arrangements(self):
        """Test summary includes family arrangements."""
        result = generate_trip_summary(
            session_id="family_test",
            family_arrangements={
                "childcare": "Emma watching Jake",
                "check_ins": ["Saturday 2pm", "Sunday 10am"],
                "messages_sent": 2,
            },
        )
        formatted = result["formatted_text"]

        assert "FAMILY ARRANGEMENTS" in formatted
        assert "Emma watching Jake" in formatted
        assert "Saturday 2pm" in formatted

    def test_summary_with_reminders(self):
        """Test summary includes reminders."""
        result = generate_trip_summary(
            session_id="reminder_test",
            reminders=[
                {"datetime": "Friday 6pm", "message": "Pack bags"},
                {"datetime": "Friday 8pm", "message": "Confirm reservations"},
            ],
        )
        formatted = result["formatted_text"]

        assert "REMINDERS SET" in formatted
        assert "Pack bags" in formatted
        assert "Confirm reservations" in formatted
