"""Story Timeline -- Epic 4.2 (STORY-001).

Defines the 20-turn Lake Tahoe family trip demo scenario with per-turn
hints, flow mapping, interrupt/clarification scripts, and special flags.

The demo runner uses ``TRIP_TIMELINE`` to display story hints and drive
automated/scripted playback.  Each ``TurnHint`` maps to a documented flow
from ``concierge_fsm_flows.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TurnHint:
    """Per-turn metadata for the 20-turn demo story.

    Attributes
    ----------
    turn_number:
        Sequential 1-based turn index.
    flow_id:
        Documented flow (F1, F2, ..., F32) from ``concierge_fsm_flows.md``.
    suggested_message:
        The user message that exercises this flow.
    interrupt_message:
        If set, the demo runner injects an interrupt during this turn.
    clarification_answers:
        Pre-scripted answers for clarification rounds (one per round).
    expected_tier:
        Expected Phase 1 classification tier.
    expected_safety:
        Expected Phase 1 safety band.
    expected_tools:
        Tool names expected to be called during this turn.
    description:
        Human-readable summary of what this turn tests.
    fsm_path:
        Expected FSM state path string (for display/verification).
    special_flags:
        Dict of flags to set on the classifier before this turn.
        Keys: ``raise_on_next``, ``force_cb_open``, ``watchdog_timeout_ms``.
    """

    turn_number: int
    flow_id: str
    suggested_message: str
    interrupt_message: str | None = None
    clarification_answers: list[str] = field(default_factory=list)
    expected_tier: str = "LOW"
    expected_safety: str = "GREEN"
    expected_tools: list[str] = field(default_factory=list)
    description: str = ""
    fsm_path: str = ""
    special_flags: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 20-Turn Lake Tahoe Trip Timeline
# ---------------------------------------------------------------------------

TRIP_TIMELINE: list[TurnHint] = [
    # ===== Part A: Getting Started (Turns 1-3, Happy Paths) ==============
    TurnHint(
        turn_number=1,
        flow_id="F1",
        suggested_message="What's the weather like in Lake Tahoe this weekend?",
        expected_tier="LOW",
        expected_safety="GREEN",
        expected_tools=[
            "invoke_capability",
            "update_beliefs",
            "update_scoreboard",
        ],
        description="Normal LOW: direct dispatch, no companion phase",
        fsm_path="L->A(P1C)->D(DC)->De(RD)->L",
    ),
    TurnHint(
        turn_number=2,
        flow_id="F2",
        suggested_message="Check for kid-friendly activities near Lake Tahoe",
        expected_tier="MEDIUM",
        expected_safety="GREEN",
        expected_tools=[
            "discover_capabilities",
            "invoke_capability",
            "update_scoreboard",
            "update_narrative",
        ],
        description="Normal MEDIUM: full companion + progress path",
        fsm_path="L->A(P1C)->D(PAS)->Co(PR)->P(DC)->De(RD)->L",
    ),
    TurnHint(
        turn_number=3,
        flow_id="F14",
        suggested_message="Does anyone have food allergies I should know about?",
        expected_tier="LOW",
        expected_safety="AMBER",
        expected_tools=[
            "recall_memory",
            "update_beliefs",
        ],
        description="AMBER safety band: medical query, enhanced logging",
        fsm_path="L->A(P1C)->D(DC)->De(RD)->L",
    ),
    # ===== Part B: Clarification Loops (Turns 4-5) =======================
    TurnHint(
        turn_number=4,
        flow_id="F4",
        suggested_message="Plan our hotel stay at Lake Tahoe",
        clarification_answers=["Saturday to Sunday, 4 people"],
        expected_tier="MEDIUM",
        expected_safety="GREEN",
        expected_tools=[
            "get_capability_schema",
            "update_clarifications",
            "execute_workflow",
            "update_scoreboard",
        ],
        description="Single-round clarification: hotel dates missing",
        fsm_path="L->A(GD)->Cl(CR)->A(P1C)->D(PAS)->Co(PR)->P(DC)->De(RD)->L",
    ),
    TurnHint(
        turn_number=5,
        flow_id="F5",
        suggested_message="Book something special for Mom's anniversary dinner",
        clarification_answers=[
            "Saturday evening",
            "4 people",
            "Lakeside with a view",
        ],
        expected_tier="MEDIUM",
        expected_safety="GREEN",
        expected_tools=[
            "get_capability_schema",
            "update_clarifications",
            "invoke_capability",
        ],
        description="Max-rounds clarification: 3 rounds, force-proceed",
        fsm_path="L->A(GD)->Cl(CR)->A(GD)->Cl(CR)->A(GD)->Cl(MRR)->D(DC)->De(RD)->L",
    ),
    # ===== Part C: Interrupt Handling (Turns 6-9) ========================
    TurnHint(
        turn_number=6,
        flow_id="F6",
        suggested_message="Find snowshoe rental places",
        interrupt_message="Wait, ski lessons instead",
        expected_tier="LOW",
        expected_safety="GREEN",
        expected_tools=["invoke_capability"],
        description="Interrupt at DISPATCHING: before work starts",
        fsm_path="L->A->D(ID)->IH(IHd)->A(P1C)->D(DC)->De(RD)->L",
    ),
    TurnHint(
        turn_number=7,
        flow_id="F7",
        suggested_message="Best family restaurants in Tahoe",
        interrupt_message="Vegetarian only please",
        expected_tier="MEDIUM",
        expected_safety="GREEN",
        expected_tools=[
            "invoke_capability",
            "update_scoreboard",
        ],
        description="Interrupt at COMPANIONING: refine query",
        fsm_path="L->A->D(PAS)->Co(ID)->IH(IHd)->A->D(PAS)->Co(PR)->P(DC)->De(RD)->L",
    ),
    TurnHint(
        turn_number=8,
        flow_id="F8",
        suggested_message="Compare hotel prices for Lake Tahoe",
        interrupt_message="Check Airbnb too",
        expected_tier="MEDIUM",
        expected_safety="GREEN",
        expected_tools=[
            "invoke_capability",
            "update_scoreboard",
        ],
        description="Interrupt at PROGRESSING: partial results preserved",
        fsm_path="L->A->D(PAS)->Co(PR)->P(ID)->IH(IHd)->A->D(PAS)->Co(PR)->P(DC)->De(RD)->L",
    ),
    TurnHint(
        turn_number=9,
        flow_id="F10",
        suggested_message="Plan the drive to Tahoe",
        interrupt_message="Actually, let's fly instead",
        clarification_answers=["From San Francisco"],
        expected_tier="MEDIUM",
        expected_safety="GREEN",
        expected_tools=[
            "update_clarifications",
            "invoke_capability",
        ],
        description="Interrupt at CLARIFYING: topic change",
        fsm_path="L->A(GD)->Cl(ID)->IH(IHd)->A(P1C)->D(DC)->De(RD)->L",
    ),
    # ===== Part D: Safety and Crisis (Turns 10-11) =======================
    TurnHint(
        turn_number=10,
        flow_id="F12",
        suggested_message="My kid just fell and is bleeding at the ski slope",
        expected_tier="LOW",
        expected_safety="CRISIS",
        expected_tools=[],
        description="CRISIS bypass: static response, no LLM, no tools",
        fsm_path="L->A(CD)->De(RD)->L",
    ),
    TurnHint(
        turn_number=11,
        flow_id="F13",
        suggested_message=("Look up the ER number and directions to Barton Memorial Hospital"),
        expected_tier="MEDIUM",
        expected_safety="RED",
        expected_tools=[
            "recall_memory",
            "discover_capabilities",
        ],
        description="RED safety band: action tools blocked",
        fsm_path="L->A(P1C)->D(PAS)->Co(PR)->P(DC)->De(RD)->L",
    ),
    # ===== Part E: Edge Cases (Turns 12-14) ==============================
    TurnHint(
        turn_number=12,
        flow_id="F17",
        suggested_message=("What's checkout time at the Hyatt? Also, is the pool heated?"),
        expected_tier="LOW",
        expected_safety="GREEN",
        expected_tools=[
            "recall_memory",
            "update_beliefs",
        ],
        description="Multi-message batch: merged, not interrupt",
        fsm_path="L->A(+MSG merged)->D(DC)->De(RD)->L",
    ),
    TurnHint(
        turn_number=13,
        flow_id="F18",
        suggested_message="Reserve a dinner spot tonight",
        interrupt_message="Just order pizza delivery instead",
        clarification_answers=["4 people"],
        expected_tier="MEDIUM",
        expected_safety="GREEN",
        expected_tools=[
            "update_clarifications",
            "invoke_capability",
        ],
        description="Clarify round 1, interrupt round 2",
        fsm_path="L->A(GD)->Cl(CR)->A(GD)->Cl(ID)->IH(IHd)->A(P1C)->D(DC)->De(RD)->L",
    ),
    TurnHint(
        turn_number=14,
        flow_id="F11",
        suggested_message="Actually make it 5 people",
        expected_tier="LOW",
        expected_safety="GREEN",
        expected_tools=["update_scoreboard"],
        description="Non-interruptible: msg queued during DELIVERING",
        fsm_path="De(MSG QUEUED)->L->A->D->De->L",
    ),
    # ===== Part F: Degradation and Failure (Turns 15-18) =================
    TurnHint(
        turn_number=15,
        flow_id="F15",
        suggested_message=(
            "Calculate optimal route with all stops, traffic, " "weather, road conditions"
        ),
        expected_tier="MEDIUM",
        expected_safety="GREEN",
        expected_tools=[
            "invoke_capability",
        ],
        description="Watchdog timeout: system-initiated interrupt",
        fsm_path="L->A->D(PAS)->Co(PR)->P(TIMEOUT)->IH(IHd)->A->fallback",
        special_flags={"watchdog_timeout_ms": 2000},
    ),
    TurnHint(
        turn_number=16,
        flow_id="F24",
        suggested_message="Book a private boat tour on the lake",
        expected_tier="LOW",
        expected_safety="GREEN",
        expected_tools=[],
        description="Full fallback: all circuit breakers open",
        fsm_path="L->A(P1C)->D(CB OPEN)->De(RD)->L",
        special_flags={"force_cb_open": True},
    ),
    TurnHint(
        turn_number=17,
        flow_id="F26",
        suggested_message="What time does the gondola start tomorrow?",
        expected_tier="LOW",
        expected_safety="GREEN",
        expected_tools=[
            "invoke_capability",
        ],
        description="Classifier failure: heuristic fallback",
        fsm_path="L->A(HEURISTIC)->D(DC)->De(RD)->L",
        special_flags={"raise_on_next": True},
    ),
    TurnHint(
        turn_number=18,
        flow_id="F27",
        suggested_message=("Remember that Jake loves the snow activities more than anything"),
        expected_tier="LOW",
        expected_safety="GREEN",
        expected_tools=[
            "update_beliefs",
        ],
        description="SessionState write failure: MutationGuard rejects",
        fsm_path="L->A->D(DC)->De(RD)->L",
    ),
    # ===== Part G: User Control and Timeout (Turns 19-20) ================
    TurnHint(
        turn_number=19,
        flow_id="F31",
        suggested_message="Start planning tomorrow's full itinerary",
        interrupt_message="cancel",
        expected_tier="MEDIUM",
        expected_safety="GREEN",
        expected_tools=[
            "execute_workflow",
        ],
        description="User cancel: explicit stop, no replacement topic",
        fsm_path="L->A->D(PAS)->Co(PR)->P(CANCEL)->IH(IHd)->A->...",
    ),
    TurnHint(
        turn_number=20,
        flow_id="F32",
        suggested_message="Plan something fun for the evening",
        expected_tier="MEDIUM",
        expected_safety="GREEN",
        expected_tools=["update_clarifications"],
        description="Clarification timeout: user walks away",
        fsm_path="L->A(GD)->Cl(TIMEOUT)->L",
    ),
]


# ---------------------------------------------------------------------------
# Persona data for session init pre-load
# ---------------------------------------------------------------------------

FAMILY_PERSONA: dict[str, Any] = {
    "family_name": "Demo Family",
    "members": [
        {
            "name": "Mom",
            "role": "parent",
            "allergies": ["shellfish"],
            "preferences": ["relaxation", "dining"],
        },
        {
            "name": "Dad",
            "role": "parent",
            "preferences": ["outdoors", "photography"],
        },
        {
            "name": "Jake",
            "role": "child",
            "age": 12,
            "allergies": ["peanuts"],
            "preferences": ["snow", "adventure"],
        },
        {
            "name": "Emma",
            "role": "child",
            "age": 8,
            "preferences": ["indoors", "crafts", "animals"],
        },
    ],
    "home_location": "San Francisco, CA",
    "vehicle": "SUV",
}


# ---------------------------------------------------------------------------
# Crisis response (static, no LLM)
# ---------------------------------------------------------------------------

CRISIS_RESPONSE = (
    "I understand this is an emergency. Here is what you should do "
    "immediately:\n\n"
    "1. Call 911 if the injury is severe\n"
    "2. Apply direct pressure to stop bleeding\n"
    "3. Keep the child calm and still\n"
    "4. The nearest hospital is Barton Memorial Hospital:\n"
    "   - Address: 2170 South Ave, South Lake Tahoe, CA\n"
    "   - ER Phone: 530-541-3420\n\n"
    "Stay safe. I am here when you need me."
)


def get_hint(turn_number: int) -> TurnHint | None:
    """Return the TurnHint for the given turn, or None if out of range."""
    for hint in TRIP_TIMELINE:
        if hint.turn_number == turn_number:
            return hint
    return None
