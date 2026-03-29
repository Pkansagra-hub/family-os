"""
Tests for Family Tools
======================

Tests for Epic 2.2: Family Tools implementation.
Verifies all 3 family tools work correctly with mock data.
"""

from poc.session_state_demo.anniversary_demo.tools.family import (
    FAMILY_TOOLS,
    FamilyMessageStore,
    compose_weekend_instructions,
    execute_family_tool,
    get_family_member_info,
    schedule_family_checkin,
    send_family_message,
    simulate_checkin_response,
)


class TestSendFamilyMessage:
    """Tests for send_family_message tool."""

    def setup_method(self):
        """Clear message store before each test."""
        FamilyMessageStore.get_instance().clear()

    def test_send_message_to_emma(self):
        """Test sending a message to Emma."""
        result = send_family_message(
            to="Emma",
            subject="Weekend Instructions",
            content="Please watch Jake this weekend. Soccer practice Saturday at 9am.",
        )

        assert result["success"] is True
        assert "message" in result
        assert result["message"]["to"] == "Emma"
        assert result["message"]["subject"] == "Weekend Instructions"
        assert result["message"]["status"] == "delivered"

    def test_send_message_with_priority(self):
        """Test sending a high priority message."""
        result = send_family_message(
            to="Emma",
            subject="Emergency",
            content="Call me ASAP",
            priority="urgent",
        )

        assert result["success"] is True
        assert result["message"]["priority"] == "urgent"

    def test_send_message_to_unknown_member(self):
        """Test sending to unknown family member fails."""
        result = send_family_message(
            to="Unknown Person",
            subject="Test",
            content="Test message",
        )

        assert result["success"] is False
        assert "available_members" in result

    def test_message_stored_in_store(self):
        """Test that sent messages are stored."""
        send_family_message(
            to="Emma",
            subject="Test",
            content="Test message",
        )

        store = FamilyMessageStore.get_instance()
        messages = store.get_messages_to("Emma")
        assert len(messages) == 1
        assert messages[0].subject == "Test"

    def test_send_message_case_insensitive(self):
        """Test recipient name is case insensitive."""
        result = send_family_message(
            to="emma",
            subject="Test",
            content="Test message",
        )

        assert result["success"] is True
        assert result["message"]["to"] == "Emma"


class TestScheduleFamilyCheckin:
    """Tests for schedule_family_checkin tool."""

    def setup_method(self):
        """Clear message store before each test."""
        FamilyMessageStore.get_instance().clear()

    def test_schedule_checkin_with_emma(self):
        """Test scheduling a check-in with Emma."""
        result = schedule_family_checkin(
            target="Emma",
            datetime_str="saturday_14:00",
            message="Hi Emma! How's everything going with Jake?",
        )

        assert result["success"] is True
        assert "checkin" in result
        assert result["checkin"]["target"] == "Emma"
        assert result["checkin"]["status"] == "scheduled"
        assert result["will_notify_on_response"] is True

    def test_schedule_checkin_no_notification(self):
        """Test scheduling check-in without response notification."""
        result = schedule_family_checkin(
            target="Emma",
            datetime_str="saturday_14:00",
            message="Just checking in",
            notify_user_on_response=False,
        )

        assert result["success"] is True
        assert result["will_notify_on_response"] is False

    def test_schedule_checkin_unknown_target(self):
        """Test scheduling check-in with unknown target fails."""
        result = schedule_family_checkin(
            target="Unknown",
            datetime_str="saturday_14:00",
            message="Hello",
        )

        assert result["success"] is False
        assert "available_members" in result

    def test_checkin_stored_in_store(self):
        """Test that scheduled check-ins are stored."""
        schedule_family_checkin(
            target="Emma",
            datetime_str="saturday_14:00",
            message="Check in message",
        )

        store = FamilyMessageStore.get_instance()
        checkins = store.get_checkins_for("Emma")
        assert len(checkins) == 1
        assert "Check in message" in checkins[0].message


class TestGetFamilyMemberInfo:
    """Tests for get_family_member_info tool."""

    def test_get_mike_all_info(self):
        """Test getting all info about Mike."""
        result = get_family_member_info(name="Mike")

        assert result["success"] is True
        assert "member" in result
        member = result["member"]
        assert member["name"] == "Mike"
        assert member["relationship"] == "husband"
        assert member["age"] == 50
        assert "shellfish" in member["health"]["allergies"]

    def test_get_emma_schedule(self):
        """Test getting Emma's schedule."""
        result = get_family_member_info(name="Emma", info_type="schedule")

        assert result["success"] is True
        assert result["info_type"] == "schedule"
        assert "schedule" in result["info"]
        # Emma should have school schedule
        schedules = result["info"]["schedule"]
        assert any("School" in s.get("activity", "") for s in schedules)

    def test_get_jake_health(self):
        """Test getting Jake's health info."""
        result = get_family_member_info(name="Jake", info_type="health")

        assert result["success"] is True
        assert result["info_type"] == "health"
        assert "health" in result["info"]

    def test_get_mike_preferences(self):
        """Test getting Mike's preferences."""
        result = get_family_member_info(name="Mike", info_type="preferences")

        assert result["success"] is True
        assert "relaxation" in result["info"]["preferences"]

    def test_get_contact_info(self):
        """Test getting contact info."""
        result = get_family_member_info(name="Emma", info_type="contact")

        assert result["success"] is True
        assert "contact" in result["info"]
        assert "phone" in result["info"]["contact"]

    def test_get_unknown_member(self):
        """Test getting info for unknown member fails."""
        result = get_family_member_info(name="Unknown")

        assert result["success"] is False
        assert "available_members" in result

    def test_get_invalid_info_type(self):
        """Test getting invalid info type fails."""
        result = get_family_member_info(name="Mike", info_type="invalid")

        assert result["success"] is False
        assert "available_types" in result


class TestComposeWeekendInstructions:
    """Tests for compose_weekend_instructions helper."""

    def test_compose_full_instructions(self):
        """Test composing comprehensive weekend instructions."""
        content = compose_weekend_instructions(
            emergency_contacts={
                "Mom (cell)": "(555) 123-4560",
                "Grandma": "(555) 987-6543",
                "Neighbor (Mrs. Johnson)": "(555) 111-2222",
            },
            jake_schedule=[
                {"day": "Saturday", "activity": "Soccer practice", "time": "9am"},
                {"day": "Saturday", "activity": "Free time", "time": "afternoon"},
                {"day": "Sunday", "activity": "Homework", "time": "afternoon"},
            ],
            hotel_info={
                "name": "Vineyard Inn",
                "phone": "(707) 555-0123",
                "address": "1234 Vineyard Lane, Sonoma, CA",
            },
            house_rules=[
                "No friends over after 9pm",
                "Jake's bedtime is 10pm",
                "Keep phone charged",
            ],
        )

        assert "EMERGENCY CONTACTS" in content
        assert "Mom (cell)" in content
        assert "JAKE'S SCHEDULE" in content
        assert "Soccer practice" in content
        assert "Vineyard Inn" in content
        assert "HOUSE RULES" in content
        assert "bedtime is 10pm" in content


class TestSimulateCheckinResponse:
    """Tests for simulate_checkin_response helper."""

    def setup_method(self):
        """Clear message store before each test."""
        FamilyMessageStore.get_instance().clear()

    def test_simulate_response(self):
        """Test simulating a check-in response."""
        # First schedule a check-in
        checkin_result = schedule_family_checkin(
            target="Emma",
            datetime_str="saturday_14:00",
            message="How's it going?",
            notify_user_on_response=True,
        )

        checkin_id = checkin_result["checkin"]["checkin_id"]

        # Simulate response
        response_result = simulate_checkin_response(
            checkin_id=checkin_id,
            response="All good! Jake is watching TV.",
        )

        assert response_result["success"] is True
        assert response_result["checkin"]["status"] == "responded"
        assert response_result["checkin"]["response"] == "All good! Jake is watching TV."
        assert response_result["notification_sent"] is True

    def test_simulate_response_unknown_checkin(self):
        """Test simulating response for unknown check-in fails."""
        result = simulate_checkin_response(
            checkin_id="CHK-UNKNOWN",
            response="Test",
        )

        assert result["success"] is False


class TestExecuteFamilyTool:
    """Tests for execute_family_tool dispatcher."""

    def setup_method(self):
        """Clear message store before each test."""
        FamilyMessageStore.get_instance().clear()

    def test_execute_known_tool(self):
        """Test executing a known tool by name."""
        result = execute_family_tool(
            "get_family_member_info",
            {"name": "Mike"},
        )

        assert result["success"] is True
        assert "member" in result

    def test_execute_unknown_tool(self):
        """Test executing unknown tool returns error."""
        result = execute_family_tool(
            "unknown_tool",
            {},
        )

        assert result["success"] is False
        assert "available_tools" in result

    def test_execute_with_invalid_params(self):
        """Test executing tool with invalid params returns error."""
        result = execute_family_tool(
            "send_family_message",
            {"wrong_param": "value"},
        )

        assert result["success"] is False


class TestFamilyMessageStore:
    """Tests for FamilyMessageStore singleton."""

    def setup_method(self):
        """Clear store before each test."""
        FamilyMessageStore.get_instance().clear()

    def test_singleton_instance(self):
        """Test FamilyMessageStore is a singleton."""
        store1 = FamilyMessageStore.get_instance()
        store2 = FamilyMessageStore.get_instance()
        assert store1 is store2

    def test_get_all_messages(self):
        """Test getting all messages."""
        send_family_message(to="Emma", subject="Test 1", content="Content 1")
        send_family_message(to="Jake", subject="Test 2", content="Content 2")

        store = FamilyMessageStore.get_instance()
        all_messages = store.get_all_messages()

        assert len(all_messages) == 2

    def test_get_all_checkins(self):
        """Test getting all check-ins."""
        schedule_family_checkin(
            target="Emma",
            datetime_str="saturday_14:00",
            message="Check 1",
        )
        schedule_family_checkin(
            target="Jake",
            datetime_str="saturday_16:00",
            message="Check 2",
        )

        store = FamilyMessageStore.get_instance()
        all_checkins = store.get_all_checkins()

        assert len(all_checkins) == 2


class TestFamilyToolsRegistry:
    """Tests for FAMILY_TOOLS registry."""

    def test_all_tools_registered(self):
        """Test all 3 family tools are in the registry."""
        expected_tools = [
            "send_family_message",
            "schedule_family_checkin",
            "get_family_member_info",
        ]

        for tool_name in expected_tools:
            assert tool_name in FAMILY_TOOLS, f"Missing tool: {tool_name}"

    def test_all_tools_are_callable(self):
        """Test all registered tools are callable."""
        for tool_name, tool_func in FAMILY_TOOLS.items():
            assert callable(tool_func), f"Tool not callable: {tool_name}"


class TestFamilyMemberData:
    """Tests for mock family member data completeness."""

    def test_mike_has_shellfish_allergy(self):
        """Test Mike's shellfish allergy is recorded."""
        result = get_family_member_info(name="Mike", info_type="health")

        assert "shellfish" in result["info"]["health"]["allergies"]

    def test_jake_has_soccer_schedule(self):
        """Test Jake's soccer schedule is recorded."""
        result = get_family_member_info(name="Jake", info_type="schedule")

        schedules = result["info"]["schedule"]
        soccer = [s for s in schedules if "Soccer" in s.get("activity", "")]
        assert len(soccer) > 0
        assert "9am" in soccer[0]["time"]

    def test_emma_is_16(self):
        """Test Emma's age is correctly recorded."""
        result = get_family_member_info(name="Emma")

        assert result["member"]["age"] == 16
