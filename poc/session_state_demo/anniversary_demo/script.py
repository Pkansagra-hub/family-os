"""
30-Turn Demo Script
====================

Defines the complete 30-turn "Anniversary Weekend" scenario.
Each turn includes user input, expected behaviors, and demo triggers.

Reference: end_to_end_demo_story.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional


class Act(Enum):
    """Story acts for narrative grouping."""

    SETUP = "ACT 1: SETUP & LEARNING"
    GAP_DETECTION = "ACT 2: LLM-DRIVEN GAP DETECTION"
    BACKGROUND = "ACT 3: BACKGROUND TASKS + CRASH"
    PROACTIVE = "ACT 4: PROACTIVE CONCIERGE"
    RESOLUTION = "ACT 5: FAMILY COMPLEXITY + RESOLUTION"


class TurnEvent(Enum):
    """Special events that can trigger during a turn."""

    NONE = auto()
    CRASH = auto()  # Turn 20: Simulate crash
    WEATHER_ALERT = auto()  # Turn 24: Weather changes
    RESTORE = auto()  # After crash: Show restore


@dataclass
class ExpectedBehavior:
    """Expected system behavior for a turn."""

    # Expected tool calls
    expected_tools: List[str] = field(default_factory=list)

    # Expected gap detection
    expects_gap: bool = False
    gap_params: List[str] = field(default_factory=list)  # Missing params

    # Background task started
    starts_background_task: bool = False
    background_task_type: Optional[str] = None

    # Special conditions
    should_remember_allergy: bool = False  # Turn 11: Check shellfish
    is_clarification_response: bool = False


@dataclass
class DemoTurn:
    """Definition of a single demo turn."""

    turn_number: int
    user_input: str
    act: Act
    description: str

    # Expected behaviors
    expected: ExpectedBehavior = field(default_factory=ExpectedBehavior)

    # Response hints (for demo display, not actual response)
    response_theme: str = ""

    # Special events
    event: TurnEvent = TurnEvent.NONE

    # Display customization
    pause_before: bool = False  # Pause for dramatic effect
    pause_after: bool = False
    highlight: bool = False  # Draw extra attention


# ============================================================================
# THE 30-TURN SCRIPT
# ============================================================================


DEMO_SCRIPT: List[DemoTurn] = [
    # =========================================================================
    # ACT 1: SETUP & LEARNING (Turns 1-8)
    # =========================================================================
    DemoTurn(
        turn_number=1,
        user_input="Hey, I need help planning a surprise for Mike's 50th birthday next Saturday",
        act=Act.SETUP,
        description="Opening - introduce topic",
        expected=ExpectedBehavior(
            expected_tools=["add_belief"],
        ),
        response_theme="Warm acknowledgment, ask about type of celebration",
    ),
    DemoTurn(
        turn_number=2,
        user_input="Weekend getaway. He's been stressed at work, needs to relax. Maybe wine country?",
        act=Act.SETUP,
        description="Sharing preferences",
        expected=ExpectedBehavior(
            expected_tools=["update_persona", "add_belief"],
        ),
        response_theme="Validate the choice, ask Napa vs Sonoma, ask about kids",
    ),
    DemoTurn(
        turn_number=3,
        user_input="Just us two. Emma can watch Jake for the weekend, she's 16 now",
        act=Act.SETUP,
        description="Family structure",
        expected=ExpectedBehavior(
            expected_tools=["add_belief"],
        ),
        response_theme="Acknowledge romantic getaway, ask about budget",
    ),
    DemoTurn(
        turn_number=4,
        user_input="Around $1500 total, maybe a bit more for something special",
        act=Act.SETUP,
        description="Budget constraint",
        expected=ExpectedBehavior(
            expected_tools=["add_belief", "update_persona"],
        ),
        response_theme="Confirm budget, offer to find options",
    ),
    DemoTurn(
        turn_number=5,
        user_input="Yes, find me some options. Oh, and Mike has a mild shellfish allergy, so keep that in mind for restaurants",
        act=Act.SETUP,
        description="Critical health info",
        expected=ExpectedBehavior(
            expected_tools=["add_belief"],
            should_remember_allergy=True,
        ),
        response_theme="Acknowledge allergy (important!), start searching",
        highlight=True,
    ),
    DemoTurn(
        turn_number=6,
        user_input="Sonoma sounds better than Napa, more relaxed vibe",
        act=Act.SETUP,
        description="Location decision",
        expected=ExpectedBehavior(
            expected_tools=["add_belief", "update_persona"],
        ),
        response_theme="Confirm Sonoma, describe search progress",
    ),
    DemoTurn(
        turn_number=7,
        user_input="What did you find?",
        act=Act.SETUP,
        description="Request search results",
        expected=ExpectedBehavior(
            expected_tools=["search_accommodations"],
        ),
        response_theme="List options with prices, ratings, highlights",
    ),
    DemoTurn(
        turn_number=8,
        user_input="The Vineyard Inn sounds perfect. What's included?",
        act=Act.SETUP,
        description="Detail request",
        expected=ExpectedBehavior(
            expected_tools=["get_accommodation_details"],
        ),
        response_theme="Detailed breakdown, ask if user wants to book",
    ),
    # =========================================================================
    # ACT 2: LLM-DRIVEN GAP DETECTION (Turns 9-14)
    # =========================================================================
    DemoTurn(
        turn_number=9,
        user_input="Book it! Two nights, Saturday and Sunday",
        act=Act.GAP_DETECTION,
        description="Booking confirmation",
        expected=ExpectedBehavior(
            expected_tools=["book_accommodation"],
        ),
        response_theme="Confirmation with details, ask what's next",
    ),
    DemoTurn(
        turn_number=10,
        user_input="Now I need to arrange something special for his actual birthday dinner",
        act=Act.GAP_DETECTION,
        description="GAP DETECTION - missing params",
        expected=ExpectedBehavior(
            expects_gap=True,
            gap_params=["date", "time", "cuisine", "party_size"],
        ),
        response_theme="I'd love to book a birthday dinner! A few questions: Which evening - Saturday or Sunday? Any cuisine preference? And what time works best?",
        highlight=True,
    ),
    DemoTurn(
        turn_number=11,
        user_input="Saturday evening, around 7pm. He loves Italian food",
        act=Act.GAP_DETECTION,
        description="Clarification response - search restaurants",
        expected=ExpectedBehavior(
            expected_tools=["search_restaurants"],
            is_clarification_response=True,
            should_remember_allergy=True,  # System should remember and filter!
        ),
        response_theme="List Italian restaurants, note that shellfish-safe options prioritized",
        highlight=True,
    ),
    DemoTurn(
        turn_number=12,
        user_input="Della Santina's looks great. Can you check if they do anything special for birthdays?",
        act=Act.GAP_DETECTION,
        description="Detail query",
        expected=ExpectedBehavior(
            expected_tools=["get_restaurant_details"],
        ),
        response_theme="Details about birthday offerings",
    ),
    DemoTurn(
        turn_number=13,
        user_input="Perfect, book it. Oh wait - can you also add a note about the shellfish allergy?",
        act=Act.GAP_DETECTION,
        description="Booking with special request",
        expected=ExpectedBehavior(
            expected_tools=["book_restaurant"],
        ),
        response_theme="Confirmation with allergy note highlighted",
    ),
    DemoTurn(
        turn_number=14,
        user_input="Great. What about transportation? Should we drive or is there a better option?",
        act=Act.GAP_DETECTION,
        description="GAP DETECTION - missing origin/style",
        expected=ExpectedBehavior(
            expects_gap=True,
            gap_params=["origin", "travel_style"],
        ),
        response_theme="Are you driving from home, or flying in? And does Mike prefer scenic drives or quick routes?",
    ),
    # =========================================================================
    # ACT 3: BACKGROUND TASKS + CRASH (Turns 15-20)
    # =========================================================================
    DemoTurn(
        turn_number=15,
        user_input="We'll drive from San Francisco. He likes scenic routes. Oh, and can you keep an eye on the weather? I don't want rain to ruin the weekend",
        act=Act.BACKGROUND,
        description="Route + START BACKGROUND MONITOR",
        expected=ExpectedBehavior(
            expected_tools=["plan_route", "start_background_monitor"],
            is_clarification_response=True,
            starts_background_task=True,
            background_task_type="weather",
        ),
        response_theme="Route suggestion + confirmation that weather is being monitored",
        highlight=True,
    ),
    DemoTurn(
        turn_number=16,
        user_input="Perfect route! How long is the drive?",
        act=Act.BACKGROUND,
        description="Follow-up on route",
        expected=ExpectedBehavior(
            expected_tools=[],  # Cached response
        ),
        response_theme="Drive time, scenic highlights along the way",
    ),
    DemoTurn(
        turn_number=17,
        user_input="One more thing - I need to brief Emma on watching Jake. Can you remind me to do that on Friday?",
        act=Act.BACKGROUND,
        description="Schedule reminder",
        expected=ExpectedBehavior(
            expected_tools=["schedule_reminder"],
        ),
        response_theme="Confirmation of reminder",
    ),
    DemoTurn(
        turn_number=18,
        user_input="Actually, can FamilyOS just send Emma the instructions directly? She's in our family group",
        act=Act.BACKGROUND,
        description="GAP DETECTION - missing instructions",
        expected=ExpectedBehavior(
            expects_gap=True,
            gap_params=["instructions_content"],
        ),
        response_theme="I can send Emma the weekend instructions! What should I include? Emergency contacts, Jake's schedule, house rules?",
    ),
    DemoTurn(
        turn_number=19,
        user_input="Yes all of that. Jake has soccer practice Saturday at 9am, make sure she knows. And give her our hotel contact info in case of emergenc--",
        act=Act.BACKGROUND,
        description="Interrupted message - CRASH incoming",
        expected=ExpectedBehavior(
            expected_tools=["send_family_message"],
        ),
        response_theme="[Message being composed...]",
        pause_after=True,  # Dramatic pause before crash
    ),
    DemoTurn(
        turn_number=20,
        user_input="",  # No user input - this is the crash/restore turn
        act=Act.BACKGROUND,
        description="THE CRASH - Session terminated, then restored",
        event=TurnEvent.CRASH,
        expected=ExpectedBehavior(),
        response_theme="Welcome back, Sarah! I see we were in the middle of preparing instructions for Emma about watching Jake this weekend. You mentioned Jake's soccer at 9am Saturday and emergency contacts. Should I complete that message to Emma?",
        highlight=True,
        pause_before=True,
    ),
    # =========================================================================
    # ACT 4: PROACTIVE CONCIERGE (Turns 21-25)
    # =========================================================================
    DemoTurn(
        turn_number=21,
        user_input="Yes! Finish that message to Emma. Include everything she needs",
        act=Act.PROACTIVE,
        description="Complete interrupted task",
        expected=ExpectedBehavior(
            expected_tools=["send_family_message"],
        ),
        response_theme="Confirmation of message sent, summary of contents",
    ),
    DemoTurn(
        turn_number=22,
        user_input="Thanks. Let me think... is there anything else I'm forgetting?",
        act=Act.PROACTIVE,
        description="Proactive gap analysis",
        expected=ExpectedBehavior(
            expected_tools=[],
        ),
        response_theme="Checklist: Vineyard Inn, Della Santina's, scenic route, Emma briefed, weather monitored. You might also consider: gift for Mike? Cover story for the surprise? Sunday activities?",
    ),
    DemoTurn(
        turn_number=23,
        user_input="Oh good point about Sunday! What's there to do near the inn?",
        act=Act.PROACTIVE,
        description="Activity search",
        expected=ExpectedBehavior(
            expected_tools=["search_activities"],
        ),
        response_theme="List of activities: spa, wine tasting, walking trails",
    ),
    DemoTurn(
        turn_number=24,
        user_input="",  # Background alert interrupts
        act=Act.PROACTIVE,
        description="WEATHER ALERT - Background task triggers",
        event=TurnEvent.WEATHER_ALERT,
        expected=ExpectedBehavior(
            starts_background_task=False,
        ),
        response_theme="Quick heads up, Sarah - I've been watching the Sonoma weather. Saturday looks beautiful (72F, sunny), but there's now a 60% chance of rain Sunday afternoon. You might want to plan indoor activities for Sunday. The inn's spa does couples massages - want me to look into that?",
        highlight=True,
        pause_before=True,
    ),
    DemoTurn(
        turn_number=25,
        user_input="Yes, book a couples massage for Sunday! Late morning so we can check out after",
        act=Act.PROACTIVE,
        description="Book spa service",
        expected=ExpectedBehavior(
            expected_tools=["book_spa_service"],
        ),
        response_theme="Confirmation, note about checkout timing",
    ),
    # =========================================================================
    # ACT 5: FAMILY COMPLEXITY + RESOLUTION (Turns 26-30)
    # =========================================================================
    DemoTurn(
        turn_number=26,
        user_input="You mentioned a cover story - I told Mike I have a work conference in Napa. Should I add any details to make it believable?",
        act=Act.RESOLUTION,
        description="Cover story help",
        expected=ExpectedBehavior(
            expected_tools=[],
        ),
        response_theme="Suggest details: conference name, schedule, why he can't come. Offer to create calendar event as alibi.",
    ),
    DemoTurn(
        turn_number=27,
        user_input="Good idea. Create a fake calendar event for 'Tech Summit Napa' from Friday to Sunday. Just in case he looks at my calendar",
        act=Act.RESOLUTION,
        description="Create cover calendar event",
        expected=ExpectedBehavior(
            expected_tools=["create_calendar_event"],
        ),
        response_theme="Confirmation, note about privacy settings",
    ),
    DemoTurn(
        turn_number=28,
        user_input="Can FamilyOS check in on Emma Saturday afternoon? Just to make sure she and Jake are doing okay?",
        act=Act.RESOLUTION,
        description="Schedule family check-in",
        expected=ExpectedBehavior(
            expected_tools=["schedule_family_checkin"],
        ),
        response_theme="Confirmation of scheduled check-in, note that user will be notified of response",
    ),
    DemoTurn(
        turn_number=29,
        user_input="Perfect. I think we're all set. Can you give me a complete summary of everything?",
        act=Act.RESOLUTION,
        description="Generate trip summary",
        expected=ExpectedBehavior(
            expected_tools=["generate_trip_summary"],
        ),
        response_theme="Complete formatted summary with all details",
        highlight=True,
    ),
    DemoTurn(
        turn_number=30,
        user_input="This is incredible. Mike is going to be so surprised. Thank you!",
        act=Act.RESOLUTION,
        description="Emotional conclusion",
        expected=ExpectedBehavior(
            expected_tools=["update_emotion"],
        ),
        response_theme="Warm closing: You've put together an amazing surprise! Have a wonderful weekend celebrating Mike's 50th!",
        highlight=True,
    ),
]


def get_turn(turn_number: int) -> Optional[DemoTurn]:
    """Get a specific turn by number."""
    for turn in DEMO_SCRIPT:
        if turn.turn_number == turn_number:
            return turn
    return None


def get_turns_by_act(act: Act) -> List[DemoTurn]:
    """Get all turns in a specific act."""
    return [t for t in DEMO_SCRIPT if t.act == act]


def get_all_turns() -> List[DemoTurn]:
    """Get all turns."""
    return DEMO_SCRIPT.copy()


def get_total_turns() -> int:
    """Get total number of turns."""
    return len(DEMO_SCRIPT)


def get_act_for_turn(turn_number: int) -> Optional[Act]:
    """Get the act for a specific turn number."""
    turn = get_turn(turn_number)
    return turn.act if turn else None


# ============================================================================
# SCRIPT METADATA
# ============================================================================


SCRIPT_METADATA = {
    "title": "The Anniversary Weekend",
    "total_turns": 30,
    "total_acts": 5,
    "features_demonstrated": [
        "SessionState learning",
        "Intent classification",
        "LLM-driven gap detection",
        "Two-way concierge loop",
        "Background task monitoring",
        "Crash recovery",
        "Proactive notifications",
        "Family messaging",
        "Trip planning",
    ],
    "key_moments": {
        5: "Shellfish allergy stored (critical health info)",
        10: "First gap detection (missing dinner params)",
        11: "System remembers allergy for restaurant search",
        15: "Weather monitor started",
        19: "Message interrupted mid-sentence",
        20: "CRASH and RESTORE",
        24: "Weather alert fires proactively",
        29: "Complete trip summary generated",
    },
    "expected_tool_calls": {
        "add_belief": 8,
        "update_persona": 4,
        "search_accommodations": 1,
        "get_accommodation_details": 1,
        "book_accommodation": 1,
        "search_restaurants": 1,
        "get_restaurant_details": 1,
        "book_restaurant": 1,
        "plan_route": 1,
        "start_background_monitor": 1,
        "schedule_reminder": 1,
        "send_family_message": 2,
        "search_activities": 1,
        "book_spa_service": 1,
        "create_calendar_event": 1,
        "schedule_family_checkin": 1,
        "generate_trip_summary": 1,
        "update_emotion": 1,
    },
}
