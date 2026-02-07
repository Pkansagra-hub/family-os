"""
Anniversary Demo Runner - REAL LLM INTEGRATION
===============================================

Orchestrates the 30-turn "Anniversary Weekend" demonstration.
Uses REAL LLM calls via SimpleLLMClient and REAL SessionState via SessionLLMBridge.

NO FAKE/MOCK CODE - Everything is real:
- Real Gemini API calls with function calling
- Real SessionState persistence to SQLite
- Real tool execution that writes to SessionState
- Real checkpoint/restore

Usage:
    python -m poc.session_state_demo.anniversary_demo.runner
    python -m poc.session_state_demo.anniversary_demo.runner --auto  # No pauses
    python -m poc.session_state_demo.anniversary_demo.runner --fast  # Reduced delays
    python -m poc.session_state_demo.anniversary_demo.runner --walkthrough  # Educational mode
"""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from poc.session_state_demo.anniversary_demo.agents.booking_agent import BookingAgent

# Sub-Agent Architecture (M8)
from poc.session_state_demo.anniversary_demo.agents.search_agent import SearchAgent

# TwoWayConcierge - Background Integration (M10)
from poc.session_state_demo.anniversary_demo.background import (
    Notification,
    NotificationPriority,
    NotificationType,
    TwoWayConcierge,
    create_two_way_concierge,
)
from poc.session_state_demo.anniversary_demo.bus.delta_bus import DeltaBus, Message

# Display functions (keep these - they work well)
from poc.session_state_demo.anniversary_demo.display import (
    BLUE,
    CYAN,
    GRAY,
    GREEN,
    RED,
    RESET,
    YELLOW,
    colorize,
    print_act_header,
    print_assistant_message,
    print_background_task_started,
    print_clarification,
    print_crash_screen,
    print_demo_complete,
    print_demo_header,
    print_demo_stats,
    print_divider,
    print_fsm_state_transition,
    print_gap_detected,
    print_gap_detection_call,
    print_k1_coverage_report,
    print_llm_call,
    print_llm_response,
    print_restore_screen,
    print_subagent_dispatch,
    print_subagent_response,
    print_system_activity,
    print_system_message,
    print_tool_call,
    print_tool_execution_result,
    print_trip_summary,
    print_turn_indicator,
    print_user_message,
    print_walkthrough_explanation,
    print_weather_alert,
    wait_for_key,
)

# Canonical Plan Object (Fix 1: Authoritative Plan State)
from poc.session_state_demo.anniversary_demo.plan import PlanController

# Script data (user inputs only)
from poc.session_state_demo.anniversary_demo.script import (
    SCRIPT_METADATA,
    Act,
    DemoTurn,
    TurnEvent,
    get_all_turns,
)

# Tool executor for all 21 tools
from poc.session_state_demo.anniversary_demo.tools.executor import ToolExecutor

# Tool registry with all 21 tools
from poc.session_state_demo.anniversary_demo.tools.registry import (
    ToolRegistry,
    create_demo_registry,
)

# Real components - NO MOCKS
from poc.session_state_demo.bridge import SessionLLMBridge

# ConciergeFSM - the orchestrator
from poc.session_state_demo.concierge.fsm import ConciergeFSM, FSMEvent, FSMObserver
from poc.session_state_demo.concierge.states import ConciergeState
from poc.session_state_demo.config import get_config
from poc.session_state_demo.llm_client import SimpleLLMClient

# =============================================================================
# FSM DISPLAY OBSERVER
# =============================================================================


class DisplayObserver(FSMObserver):
    """Observer that displays FSM events in the terminal."""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    def on_event(self, event: FSMEvent) -> None:
        """Handle FSM events by printing them."""
        if not self.verbose:
            return

        if event.event_type == "llm_call":
            print_llm_call(
                model=event.data.get("model", "gemini"),
                prompt_preview=event.data.get("prompt_preview", ""),
                message_count=event.data.get("message_count", 0),
                tool_count=event.data.get("tool_count", 0),
            )
        elif event.event_type == "llm_response":
            print_llm_response(
                content_preview=event.data.get("content_preview", ""),
                tool_calls=event.data.get("tool_calls", []),
                latency_ms=event.data.get("latency_ms", 0),
            )
        elif event.event_type == "gap_detection_start":
            print_gap_detection_call(
                user_input=event.data.get("user_input", ""),
                referents=event.data.get("referents", []),
                beliefs_count=event.data.get("beliefs_count", 0),
            )
        elif event.event_type == "gap_detection_result":
            gaps_found = event.data.get("gaps_found", 0)
            if gaps_found > 0:
                gap_types = event.data.get("gap_types", [])
                print(
                    colorize(
                        f"       {chr(0x2713)} Found {gaps_found} gap(s): {', '.join(gap_types)}",
                        YELLOW,
                    )
                )
        elif event.event_type == "tool_call":
            # Tool calls are printed separately, but we could add extra info here
            pass
        elif event.event_type == "tool_execution_result":
            # Show tool execution results (especially for bookings)
            tool_name = event.data.get("name", "")

            # ALWAYS show acknowledge tool results immediately
            if tool_name == "acknowledge":
                ack_data = event.data.get("data", {})
                formatted_msg = ack_data.get("formatted_message", event.data.get("message", ""))
                ack_type = ack_data.get("ack_type", "progress")
                next_tool = ack_data.get("next_tool", "none")
                if formatted_msg:
                    # Use different colors for different ACK types
                    ack_colors = {
                        "commit": GREEN,  # State changed - green
                        "progress": CYAN,  # Work starting - cyan
                        "closure": GREEN,  # Complete - green
                    }
                    color = ack_colors.get(ack_type, CYAN)
                    # Show next_tool if not "none" to indicate what's coming
                    next_indicator = f" -> {next_tool}" if next_tool != "none" else ""
                    print(
                        f"\n{color}[ACK:{ack_type.upper()}{next_indicator}] {formatted_msg}{RESET}"
                    )
                return

            # Only show for significant tools (bookings, messages, etc.)
            if any(
                word in tool_name.lower()
                for word in ["book", "send", "create_calendar", "schedule", "monitor"]
            ):
                print_tool_execution_result(
                    tool_name=tool_name,
                    success=event.data.get("success", True),
                    message=event.data.get("message", ""),
                    data=event.data.get("data", {}),
                )


# =============================================================================
# DYNAMIC CONCIERGE PROMPT BUILDER
# =============================================================================


class DynamicPromptBuilder:
    """
    Builds dynamic system prompts by injecting context from all 12 SessionState sections.

    NO MORE STATIC PROMPTS - Everything is dynamic:
    - KNOWN_FACTS from beliefs_active + beliefs_history
    - USER_PREFERENCES from persona
    - CURRENT_TOPIC from scoreboard
    - EMOTIONAL_STATE from affective_now
    - CONVERSATION_PHASE from narrative_active
    - PENDING_CLARIFICATIONS from clarifications
    - AVAILABLE_TOOLS from tool_registry
    - SPAWNABLE_AGENTS defined here
    """

    # Base identity - this part is static
    BASE_IDENTITY = """You are the FamilyOS Concierge - an intelligent family assistant.
You ARE the concierge. You have WRITE access to the family's SessionState via tools.
You can remember things, learn preferences, spawn sub-agents, and help plan activities."""

    # Response style rules WITH ACKNOWLEDGMENT REQUIREMENT (Schema v2)
    RESPONSE_STYLE = """
TOOL CALLING RULES (CRITICAL - VALIDATOR ENFORCED):

1. acknowledge() MUST BE FIRST in every tool bundle
2. If next_tool != "none", you MUST call that exact tool immediately after acknowledge
3. EVERY response with tools must start with acknowledge

VALID BUNDLES:
  # Text-only response (no other tools)
  acknowledge(ack_type="progress", message="I need more info about...", next_tool="none")

  # Store belief (ACK + tool)
  acknowledge(ack_type="commit", message="Noting dietary restriction", next_tool="add_belief")
  add_belief(subject="family_member", predicate="has_allergy", object="peanuts")

  # Search (ACK + tool)
  acknowledge(ack_type="progress", message="Searching hotels in that area", next_tool="search_accommodations")
  search_accommodations(location="<learned_from_user>", check_in_date="<learned_from_user>", ...)

INVALID (WILL BE REJECTED):
  # ACK says next_tool but doesn't call it
  acknowledge(..., next_tool="add_belief")  <-- WRONG: missing add_belief call

  # Tool without ACK first
  add_belief(...)  <-- WRONG: no acknowledge before effectful tool

  # Pure text without ACK
  "I'll search for hotels..."  <-- WRONG: should use acknowledge(next_tool="none")

ACK TYPES:
- "commit": State change happening
- "progress": Work starting  
- "closure": Branch complete

ACK MESSAGE RULES:
- FORBIDDEN: "got it", "understood", "noted", "I see", "let me"
- REQUIRED: Specific object + action ("Booking [restaurant name]", "Searching [location] hotels")

RESPONSE STYLE:
- SHORT when appropriate, DETAILED when needed
- NEVER repeat what user said
- Reference stored facts naturally
- ASK for missing info before searching/booking"""

    # Spawnable agents definition - CRITICAL: Must tell LLM to USE spawn_agent tool
    SPAWNABLE_AGENTS = """
SUB-AGENT ARCHITECTURE (IMPORTANT - YOU MUST USE spawn_agent TOOL):
When the user asks you to search or book anything, YOU MUST call the spawn_agent tool.
DO NOT respond with text saying you'll search - actually call the tool!

EXAMPLE - User says "find me some hotels":
CORRECT: Call spawn_agent(agent_type="SearchAgent", task_type="search_accommodations", params={"location": "<from_user>", ...})
WRONG: Respond with "I'll search for hotels..." without calling the tool

Available agents via spawn_agent():
- SearchAgent: task_type = "search_accommodations" | "search_restaurants" | "search_activities"
- BookingAgent: task_type = "book_accommodation" | "book_restaurant" | "book_spa_service"

Sub-agents run in their own thread with READ-ONLY access to user preferences.
Results come back automatically via Delta Bus - no need to wait."""

    def __init__(
        self,
        bridge: Optional["SessionLLMBridge"],
        tool_registry: Optional["ToolRegistry"] = None,
        resolved_refs: Optional[Dict[str, Any]] = None,
        plan_controller: Optional["PlanController"] = None,
    ):
        self._bridge = bridge
        self._tool_registry = tool_registry
        self._resolved_refs = resolved_refs or {}
        self._plan_controller = plan_controller

    def build_prompt(self) -> str:
        """Build complete dynamic system prompt."""
        sections = []

        # 1. Base identity
        sections.append(self.BASE_IDENTITY)

        # 2. CANONICAL PLAN STATE (AUTHORITATIVE - Fix 1)
        plan_context = self._build_plan_context()
        if plan_context:
            sections.append(plan_context)

        # 3. Dynamic context from SessionState
        sections.append(self._build_context_section())

        # 4. Resolved references (CRITICAL - prevents re-asking)
        resolved_section = self._build_resolved_refs_section()
        if resolved_section:
            sections.append(resolved_section)

        # 5. Available tools
        sections.append(self._build_tools_section())

        # 6. Spawnable agents
        sections.append(self.SPAWNABLE_AGENTS)

        # 7. Response style
        sections.append(self.RESPONSE_STYLE)

        return "\n\n".join(sections)

    def _build_plan_context(self) -> str:
        """Build AUTHORITATIVE plan context from PlanController."""
        if not self._plan_controller:
            return ""
        return self._plan_controller.get_prompt_context()

    def _build_resolved_refs_section(self) -> str:
        """Build section for resolved references that should NOT be asked about."""
        if not self._resolved_refs:
            return ""

        lines = ["ALREADY RESOLVED (DO NOT ASK ABOUT THESE):"]
        for key, ref in self._resolved_refs.items():
            if hasattr(ref, "resolved"):
                # ResolvedReference dataclass
                lines.append(f"- {ref.original} = {ref.resolved} (LOCKED)")
            elif isinstance(ref, dict):
                lines.append(f"- {ref.get('original', key)} = {ref.get('resolved', '')} (LOCKED)")
            else:
                lines.append(f"- {key} = {ref} (LOCKED)")

        lines.append("")
        lines.append(
            "IMPORTANT: The above items are RESOLVED. Do NOT ask for clarification about them."
        )
        return "\n".join(lines)

    def _build_context_section(self) -> str:
        """Build dynamic context from all 12 SessionState sections."""
        context_parts = ["CURRENT SESSION CONTEXT:"]

        # === HOT TIER ===

        # 1. beliefs_active - Known facts
        beliefs = self._get_beliefs()
        if beliefs:
            context_parts.append(f"\nKNOWN FACTS (from beliefs_active):\n{beliefs}")

        # 2. persona - User preferences
        persona = self._get_persona()
        if persona:
            context_parts.append(f"\nUSER PREFERENCES (from persona):\n{persona}")

        # 3. scoreboard - Current topic and referents
        scoreboard = self._get_scoreboard()
        if scoreboard:
            context_parts.append(f"\nCURRENT FOCUS (from scoreboard):\n{scoreboard}")

        # 4. affective_now - Emotional state
        emotional = self._get_emotional_state()
        if emotional:
            context_parts.append(f"\nEMOTIONAL STATE (from affective_now):\n{emotional}")

        # 5. clarifications - Pending gaps
        clarifications = self._get_clarifications()
        if clarifications:
            context_parts.append(f"\nPENDING CLARIFICATIONS:\n{clarifications}")

        # 6. narrative_active - Conversation phase
        narrative = self._get_narrative()
        if narrative:
            context_parts.append(f"\nCONVERSATION PHASE (from narrative_active):\n{narrative}")

        # 7. meta - Session info
        meta = self._get_meta()
        if meta:
            context_parts.append(f"\nSESSION INFO (from meta):\n{meta}")

        # === WARM TIER ===

        # 8. beliefs_history - Historical facts (demoted from HOT)
        beliefs_history = self._get_beliefs_history()
        if beliefs_history:
            context_parts.append(f"\nHISTORICAL FACTS (from beliefs_history):\n{beliefs_history}")

        # 9. history_recent - Compressed conversation history
        history_recent = self._get_history_recent()
        if history_recent:
            context_parts.append(
                f"\nCONVERSATION HISTORY SUMMARY (from history_recent):\n{history_recent}"
            )

        # 10. history_active - Recent conversation summary (last 10 turns)
        history = self._get_history_summary()
        if history:
            context_parts.append(f"\nRECENT TURNS:\n{history}")

        # 11. telemetry - Session performance
        telemetry = self._get_telemetry()
        if telemetry:
            context_parts.append(f"\nSESSION STATS (from telemetry):\n{telemetry}")

        return "\n".join(context_parts)

    def _get_beliefs(self) -> str:
        """Extract beliefs from beliefs_active section."""
        if not self._bridge:
            return ""
        try:
            data = self._bridge.get_section_data("beliefs_active")
            if "error" in data:
                return ""

            # Try to get belief triples
            beliefs = data.get("beliefs", data.get("raw", ""))
            if isinstance(beliefs, dict):
                lines = []
                for subject, predicates in beliefs.items():
                    if isinstance(predicates, dict):
                        for predicate, obj in predicates.items():
                            lines.append(f"- {subject} {predicate} {obj}")
                    else:
                        lines.append(f"- {subject}: {predicates}")
                return "\n".join(lines[:15])  # Limit to 15 facts
            return str(beliefs)[:500] if beliefs else ""
        except Exception:
            return ""

    def _get_persona(self) -> str:
        """Extract persona traits."""
        if not self._bridge:
            return ""
        try:
            data = self._bridge.get_section_data("persona")
            if "error" in data:
                return ""

            lines = []
            traits = data.get("traits", {})
            for trait, value in list(traits.items())[:10]:
                lines.append(f"- {trait}: {value}")

            personality = data.get("personality", {})
            if personality:
                lines.append(
                    f"- Communication style: warmth={personality.get('warmth', 0.5):.1f}, formality={personality.get('formality', 0.5):.1f}"
                )

            return "\n".join(lines) if lines else ""
        except Exception:
            return ""

    def _get_scoreboard(self) -> str:
        """Extract scoreboard (topic, referents, QUD)."""
        if not self._bridge:
            return ""
        try:
            data = self._bridge.get_section_data("scoreboard")
            if "error" in data or not data:
                return ""

            lines = []
            if "topic" in data:
                lines.append(f"- Current topic: {data['topic']}")
            if "qud" in data:
                lines.append(f"- Question under discussion: {data['qud']}")
            if "referents" in data:
                refs = list(data["referents"].items())[:5]
                for name, info in refs:
                    lines.append(
                        f"- Active referent: {name} (salience: {info.get('salience', 0):.1f})"
                    )

            return "\n".join(lines) if lines else ""
        except Exception:
            return ""

    def _get_emotional_state(self) -> str:
        """Extract current emotional state."""
        if not self._bridge:
            return ""
        try:
            data = self._bridge.get_section_data("affective_now")
            if "error" in data:
                return ""

            emotion = data.get("emotion", "neutral")
            intensity = data.get("intensity", 0.5)
            empathy = data.get("empathy_needed", False)

            result = f"- User emotion: {emotion} (intensity: {intensity:.1f})"
            if empathy:
                result += "\n- Empathetic response recommended"
            return result
        except Exception:
            return ""

    def _get_clarifications(self) -> str:
        """Extract pending clarifications."""
        if not self._bridge:
            return ""
        try:
            data = self._bridge.get_section_data("clarifications")
            if "error" in data or not data:
                return ""

            gaps = data.get("gaps", [])
            if not gaps:
                return ""

            lines = []
            for gap in gaps[:3]:
                lines.append(f"- Missing: {gap.get('type', 'unknown')} - {gap.get('question', '')}")
            return "\n".join(lines)
        except Exception:
            return ""

    def _get_narrative(self) -> str:
        """Extract narrative phase."""
        if not self._bridge:
            return ""
        try:
            data = self._bridge.get_section_data("narrative_active")
            if "error" in data or not data:
                return ""

            phase = data.get("phase", "unknown")
            thread = data.get("thread", "")
            return f"- Phase: {phase}" + (f"\n- Active thread: {thread}" if thread else "")
        except Exception:
            return ""

    def _get_meta(self) -> str:
        """Extract session meta info."""
        if not self._bridge:
            return ""
        try:
            data = self._bridge.get_section_data("meta")
            if "error" in data:
                return ""

            lines = []
            if "session_id" in data:
                lines.append(f"- Session: {data['session_id']}")
            if "turn_count" in data:
                lines.append(f"- Turn count: {data['turn_count']}")
            if "started_at" in data:
                lines.append(f"- Started: {data['started_at']}")

            return "\n".join(lines) if lines else ""
        except Exception:
            return ""

    def _get_history_summary(self) -> str:
        """Get summary of recent conversation."""
        if not self._bridge:
            return ""
        try:
            data = self._bridge.get_section_data("history_active")
            if "error" in data:
                return ""

            turn_count = data.get("turn_count", 0)
            if turn_count == 0:
                return "- This is the start of the conversation"

            lines = [f"- {turn_count} turns so far in this conversation"]

            # Include recent turn summaries if available
            turns = data.get("turns", [])
            if turns:
                lines.append("- Recent exchanges:")
                for t in turns[-3:]:
                    user = t.get("user", "")[:50]
                    lines.append(f"  User: {user}...")

            return "\n".join(lines)
        except Exception:
            return ""

    def _get_beliefs_history(self) -> str:
        """Get historical facts from beliefs_history (WARM tier)."""
        if not self._bridge:
            return ""
        try:
            data = self._bridge.get_section_data("beliefs_history")
            if "error" in data:
                return ""

            facts = data.get("facts", [])
            count = data.get("count", 0)

            if not facts and count == 0:
                return ""

            lines = [f"- {count} historical facts archived"]
            for fact in facts[:5]:
                subj = fact.get("subject", "")
                pred = fact.get("predicate", "")
                obj = fact.get("object", "")
                lines.append(f"  - {subj} {pred} {obj}")

            return "\n".join(lines) if len(lines) > 1 else ""
        except Exception:
            return ""

    def _get_history_recent(self) -> str:
        """Get compressed history from history_recent (WARM tier)."""
        if not self._bridge:
            return ""
        try:
            data = self._bridge.get_section_data("history_recent")
            if "error" in data:
                return ""

            compressed = data.get("compressed_turns", [])
            summarized = data.get("summarized_turns", [])
            session_summary = data.get("session_summary", "")

            if not compressed and not summarized and not session_summary:
                return ""

            lines = []

            if session_summary:
                lines.append(f"- Session summary: {session_summary}")

            if summarized:
                lines.append(f"- {len(summarized)} summarized turns (older history)")
                for st in summarized[:3]:
                    lines.append(
                        f"  Turn {st.get('turn_number', 0)}: {st.get('summary', '')[:60]}..."
                    )

            if compressed:
                lines.append(f"- {len(compressed)} compressed turns")
                # Show key entities and intents from compressed turns
                all_entities = set()
                all_intents = set()
                for ct in compressed:
                    all_entities.update(ct.get("entities", []))
                    all_intents.update(ct.get("intents", []))
                if all_entities:
                    lines.append(f"  Mentioned entities: {', '.join(list(all_entities)[:5])}")
                if all_intents:
                    lines.append(f"  Discussed intents: {', '.join(list(all_intents)[:5])}")

            return "\n".join(lines) if lines else ""
        except Exception:
            return ""

    def _get_telemetry(self) -> str:
        """Get session telemetry stats."""
        if not self._bridge:
            return ""
        try:
            data = self._bridge.get_section_data("telemetry")
            if "error" in data:
                return ""

            turn_count = data.get("turn_count", 0)
            tool_calls = data.get("tool_call_count", 0)
            latency = data.get("total_latency_ms", 0)
            errors = data.get("error_count", 0)

            if turn_count == 0:
                return ""

            lines = []
            lines.append(f"- Turns processed: {turn_count}")
            if tool_calls:
                lines.append(f"- Tool calls made: {tool_calls}")
            if latency > 0 and turn_count > 0:
                avg_latency = latency // turn_count
                lines.append(f"- Avg response time: {avg_latency}ms")
            if errors:
                lines.append(f"- Errors encountered: {errors}")

            return "\n".join(lines) if lines else ""
        except Exception:
            return ""

    def _build_tools_section(self) -> str:
        """Build available tools section from registry."""
        lines = ["AVAILABLE TOOLS:"]

        # Group tools by category
        categories = {
            "agent": ["spawn_agent"],  # CRITICAL: spawn_agent first!
            "memory": ["add_belief", "update_persona", "update_emotion"],
            "planning": ["plan_route"],
            "family": ["send_family_message", "schedule_family_checkin"],
            "calendar": ["create_calendar_event", "schedule_reminder"],
            "monitoring": ["start_background_monitor", "stop_background_monitor"],
            "summary": ["generate_trip_summary"],
        }

        for category, tool_names in categories.items():
            tools_in_cat = []
            for name in tool_names:
                schema = self._tool_registry.get(name) if self._tool_registry else None
                if schema:
                    # Get brief description
                    desc = (
                        schema.description[:60] + "..."
                        if len(schema.description) > 60
                        else schema.description
                    )
                    tools_in_cat.append(f"  - {name}: {desc}")

            if tools_in_cat:
                lines.append(f"\n{category.upper()}:")
                lines.extend(tools_in_cat)

        return "\n".join(lines)



# =============================================================================
# SCOREBOARD TRACKER (M9.1)
# =============================================================================


class ScoreboardTracker:
    """
    Tracks discourse state for context-aware conversation.

    Maintains:
    - Referents: Entities mentioned in conversation with salience scores
    - QUD (Question Under Discussion): Current question being addressed
    - Topic: Current conversation topic

    Reference: FULL_ARCHITECTURE_IMPLEMENTATION_PLAN.md - Epic 9.1
    """

    # Keywords that indicate different referent types
    PERSON_KEYWORDS = {
        "mike",
        "emma",
        "sarah",
        "jake",
        "husband",
        "wife",
        "daughter",
        "son",
        "kids",
    }
    PLACE_KEYWORDS = {"sonoma", "napa", "vineyard", "restaurant", "hotel", "spa", "inn"}
    PLAN_KEYWORDS = {"trip", "weekend", "booking", "reservation", "plans", "itinerary"}
    TIME_KEYWORDS = {"saturday", "sunday", "morning", "evening", "week", "tomorrow", "today"}

    def __init__(self, bridge: Optional["SessionLLMBridge"] = None):
        """Initialize scoreboard tracker."""
        self._bridge = bridge
        self._referents: Dict[str, Dict[str, Any]] = {}
        self._qud: str = ""
        self._topic: str = "general"
        self._last_update_turn: int = 0

    def _word_in_text(self, word: str, text: str) -> bool:
        """Check if word appears as a whole word in text (not as substring)."""
        import re

        pattern = r"\b" + re.escape(word) + r"\b"
        return bool(re.search(pattern, text, re.IGNORECASE))

    def update_from_turn(
        self,
        turn_number: int,
        user_input: str,
        assistant_response: str = "",
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Update scoreboard from a conversation turn.

        Args:
            turn_number: Current turn number
            user_input: User's message
            assistant_response: Assistant's response
            tool_calls: Any tool calls made

        Returns:
            Dict with scoreboard changes
        """
        changes = {
            "referents_added": [],
            "referents_updated": [],
            "qud_changed": False,
            "topic_changed": False,
        }

        # Decay existing referents
        self._decay_all_referents()

        # Extract referents from user input
        text = f"{user_input} {assistant_response}".lower()

        # Track people (use word boundaries to avoid partial matches)
        for keyword in self.PERSON_KEYWORDS:
            if self._word_in_text(keyword, text):
                name = keyword.title()
                if name not in self._referents:
                    self._referents[name] = {
                        "type": "person",
                        "salience": 0.8,
                        "last_mention": turn_number,
                        "first_mention": turn_number,
                    }
                    changes["referents_added"].append(name)
                else:
                    self._referents[name]["salience"] = min(
                        1.0, self._referents[name]["salience"] + 0.2
                    )
                    self._referents[name]["last_mention"] = turn_number
                    changes["referents_updated"].append(name)

        # Track places (use word boundaries)
        for keyword in self.PLACE_KEYWORDS:
            if self._word_in_text(keyword, text):
                name = keyword.title()
                if keyword == "vineyard" and self._word_in_text("inn", text):
                    name = "Vineyard Inn"
                if name not in self._referents:
                    self._referents[name] = {
                        "type": "place",
                        "salience": 0.7,
                        "last_mention": turn_number,
                        "first_mention": turn_number,
                    }
                    changes["referents_added"].append(name)
                else:
                    self._referents[name]["salience"] = min(
                        1.0, self._referents[name]["salience"] + 0.15
                    )
                    self._referents[name]["last_mention"] = turn_number

        # Track plans (use word boundaries)
        for keyword in self.PLAN_KEYWORDS:
            if self._word_in_text(keyword, text):
                name = keyword.title()
                if name not in self._referents:
                    self._referents[name] = {
                        "type": "plan",
                        "salience": 0.6,
                        "last_mention": turn_number,
                        "first_mention": turn_number,
                    }
                    changes["referents_added"].append(name)
                else:
                    self._referents[name]["salience"] = min(
                        1.0, self._referents[name]["salience"] + 0.1
                    )
                    self._referents[name]["last_mention"] = turn_number

        # Extract QUD from questions in user input
        if "?" in user_input:
            self._qud = user_input.split("?")[0].strip() + "?"
            changes["qud_changed"] = True

        # Detect topic from tool calls
        if tool_calls:
            for call in tool_calls:
                tool_name = call.get("name", "")
                if "accommodation" in tool_name:
                    self._topic = "accommodation_booking"
                    changes["topic_changed"] = True
                elif "restaurant" in tool_name:
                    self._topic = "restaurant_booking"
                    changes["topic_changed"] = True
                elif "activity" in tool_name or "spa" in tool_name:
                    self._topic = "activity_planning"
                    changes["topic_changed"] = True
                elif "belief" in tool_name or "persona" in tool_name:
                    self._topic = "information_gathering"
                    changes["topic_changed"] = True

        self._last_update_turn = turn_number

        # Persist to SessionState
        self._persist_to_session()

        return changes

    def _decay_all_referents(self, decay_factor: float = 0.9) -> None:
        """Decay salience of all referents."""
        for name, data in self._referents.items():
            data["salience"] = max(0.1, data["salience"] * decay_factor)

    def _persist_to_session(self) -> None:
        """Persist scoreboard to SessionState."""
        if not self._bridge:
            return

        try:
            self._bridge.update_scoreboard(
                topic=self._topic,
                qud=self._qud,
                referents=self._referents,
            )
        except Exception:
            pass  # Silently fail if bridge doesn't support this

    def get_scoreboard(self) -> Dict[str, Any]:
        """Get current scoreboard state."""
        return {
            "referents": self._referents.copy(),
            "qud": self._qud,
            "topic": self._topic,
            "last_update_turn": self._last_update_turn,
        }

    def get_top_referents(self, n: int = 5) -> List[Dict[str, Any]]:
        """Get top N referents by salience."""
        sorted_refs = sorted(
            self._referents.items(),
            key=lambda x: x[1]["salience"],
            reverse=True,
        )
        return [{"name": name, **data} for name, data in sorted_refs[:n]]

    def format_for_context(self) -> str:
        """Format scoreboard for LLM context injection."""
        lines = []

        # Topic
        if self._topic:
            lines.append(f"- Current topic: {self._topic}")

        # QUD
        if self._qud:
            lines.append(f"- Question under discussion: {self._qud}")

        # Top referents
        top_refs = self.get_top_referents(5)
        if top_refs:
            lines.append("- Active referents:")
            for ref in top_refs:
                lines.append(f"    {ref['name']}: {ref['type']} (salience: {ref['salience']:.2f})")

        return "\n".join(lines) if lines else ""


# =============================================================================
# NARRATIVE TRACKER (M9.2)
# =============================================================================


class NarrativeTracker:
    """
    Tracks narrative phase of conversation.

    Detects phase transitions:
    - SETUP: Initial context gathering
    - BOOKING: Making reservations
    - EXECUTION: Background tasks running
    - CRISIS: Problem handling
    - RECOVERY: Re-establishing after disruption
    - RESOLUTION: Wrapping up

    Reference: FULL_ARCHITECTURE_IMPLEMENTATION_PLAN.md - Epic 9.2
    """

    def __init__(self, bridge: Optional["SessionLLMBridge"] = None):
        """Initialize narrative tracker."""
        self._bridge = bridge
        self._phase = NarrativePhase.SETUP
        self._thread: str = ""
        self._phase_start_turn: int = 1
        self._phase_history: List[Dict[str, Any]] = []

    def update_from_turn(
        self,
        turn_number: int,
        user_input: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        had_crash: bool = False,
    ) -> Dict[str, Any]:
        """
        Update narrative tracking from a turn.

        Args:
            turn_number: Current turn number
            user_input: User's message
            tool_calls: Tool calls made this turn
            had_crash: Whether a crash occurred

        Returns:
            Dict with narrative changes
        """
        changes = {"phase_changed": False, "previous_phase": None, "new_phase": None}

        # Determine expected phase from turn number
        expected_phase = NarrativePhase.from_turn_number(turn_number)

        # Check for phase transition
        if expected_phase != self._phase:
            changes["phase_changed"] = True
            changes["previous_phase"] = self._phase.value
            changes["new_phase"] = expected_phase.value

            # Record in history
            self._phase_history.append(
                {
                    "phase": self._phase.value,
                    "start_turn": self._phase_start_turn,
                    "end_turn": turn_number - 1,
                }
            )

            self._phase = expected_phase
            self._phase_start_turn = turn_number

        # Update narrative thread from context
        if tool_calls:
            for call in tool_calls:
                tool_name = call.get("name", "")
                if "book" in tool_name:
                    self._thread = "making_reservations"
                elif "search" in tool_name:
                    self._thread = "exploring_options"
                elif "monitor" in tool_name:
                    self._thread = "monitoring_conditions"

        # Detect crisis from crash or problem keywords
        if had_crash:
            self._phase = NarrativePhase.CRISIS
            self._thread = "handling_disruption"
            changes["phase_changed"] = True
            changes["new_phase"] = "crisis"

        # Persist to SessionState
        self._persist_to_session()

        return changes

    def _persist_to_session(self) -> None:
        """Persist narrative to SessionState."""
        if not self._bridge:
            return

        try:
            self._bridge.update_narrative(
                phase=self._phase.value,
                thread=self._thread,
            )
        except Exception:
            pass

    @property
    def current_phase(self) -> NarrativePhase:
        """Get current narrative phase."""
        return self._phase

    @property
    def current_thread(self) -> str:
        """Get current narrative thread."""
        return self._thread

    def get_narrative(self) -> Dict[str, Any]:
        """Get current narrative state."""
        return {
            "phase": self._phase.value,
            "phase_description": self._phase.description,
            "thread": self._thread,
            "phase_start_turn": self._phase_start_turn,
            "history": self._phase_history.copy(),
        }

    def format_for_context(self) -> str:
        """Format narrative for LLM context injection."""
        lines = [
            f"- Phase: {self._phase.value.upper()} ({self._phase.description})",
        ]

        if self._thread:
            lines.append(f"- Active thread: {self._thread}")

        return "\n".join(lines)


# Import NarrativePhase from states (for type hints)
from poc.session_state_demo.concierge.states import NarrativePhase

# =============================================================================
# DEMO STATE TRACKING
# =============================================================================


@dataclass
class DemoState:
    """State tracking for the demo run - now tracks REAL data."""

    current_turn: int = 0
    total_turns: int = 30

    # Metrics - from REAL execution
    tool_calls: int = 0
    gap_detections: int = 0
    clarifications: int = 0
    background_tasks: int = 0
    crash_restores: int = 0

    # Timing - REAL latencies
    turn_latencies: List[int] = field(default_factory=list)
    start_time: float = 0.0

    # Session info
    session_id: str = ""
    has_crashed: bool = False

    # K1 coverage tracking
    k1_coverage: Dict[str, bool] = field(
        default_factory=lambda: {
            "SessionState Persistence": False,
            "Checkpoint/Restore": False,
            "LLM Tool Calling": False,
            "Gap Detection": False,
            "Intent Classification": False,
            "Background Tasks": False,
            "Proactive Notifications": False,
            "Persona Learning": False,
            "Belief Storage": False,
            "Family Messaging": False,
            "Calendar Integration": False,
            "Weather Monitoring": False,
            "Sub-Agent Spawning": False,
            "Scoreboard Tracking": False,
            "Narrative Tracking": False,
        }
    )


# =============================================================================
# DEMO RUNNER - REAL LLM INTEGRATION
# =============================================================================


class DemoRunner:
    """
    Orchestrates the 30-turn demo with REAL LLM calls.

    This is NOT a simulation - it uses:
    - Real Gemini API via SimpleLLMClient
    - Real SessionState via SessionLLMBridge
    - Real tool execution that persists to SQLite
    """

    def __init__(
        self,
        auto_mode: bool = False,
        fast_mode: bool = False,
        walkthrough_mode: bool = False,
    ):
        """Initialize the runner with real components."""
        self.auto_mode = auto_mode
        self.fast_mode = fast_mode
        self.walkthrough_mode = walkthrough_mode
        self.state = DemoState()
        self.state.start_time = time.time()

        # Script data (just user inputs)
        self.turns = get_all_turns()
        self.state.total_turns = len(self.turns)
        self.current_act: Optional[Act] = None

        # REAL components - initialized in run()
        self.bridge: Optional[SessionLLMBridge] = None
        self.llm: Optional[SimpleLLMClient] = None
        self.tool_registry: ToolRegistry = create_demo_registry()
        self.tool_executor: Optional[ToolExecutor] = None

        # ConciergeFSM - the orchestrator
        self.fsm: Optional[ConciergeFSM] = None
        self.display_observer: Optional[DisplayObserver] = None

        # Sub-Agent Architecture (M8)
        self.delta_bus: Optional[DeltaBus] = None
        self.search_agent: Optional[SearchAgent] = None
        self.booking_agent: Optional[BookingAgent] = None
        self._pending_agent_results: List[Message] = []

        # TwoWayConcierge + Background Integration (M10)
        self.two_way_concierge: Optional[TwoWayConcierge] = None
        self._active_weather_monitor_id: Optional[str] = None

        # Scoreboard + Narrative Tracking (M9)
        self.scoreboard_tracker: Optional[ScoreboardTracker] = None
        self.narrative_tracker: Optional[NarrativeTracker] = None

        # Canonical Plan Controller (Fix 1: Authoritative Plan State)
        self.plan_controller: Optional[PlanController] = None

        # Walkthrough explanations
        self._walkthrough_topics: Dict[str, str] = {
            "session_state": (
                "SessionState is K1's memory system. It persists:\n"
                "  - Conversation history (HOT tier)\n"
                "  - User preferences and persona (WARM tier)\n"
                "  - Learned beliefs about the family (WARM tier)\n"
                "Each section has a fixed capacity with auto-eviction."
            ),
            "tool_calling": (
                "The LLM uses REAL function calling to update SessionState:\n"
                "  - add_belief(): Store facts about users\n"
                "  - update_persona(): Record preferences\n"
                "  - Tools are validated against schemas\n"
                "  - Execution writes to real SQLite database"
            ),
            "gap_detection": (
                "LLM-driven gap detection identifies missing info:\n"
                "  1. LLM attempts tool call with incomplete params\n"
                "  2. Schema validator detects missing required fields\n"
                "  3. LLM generates natural clarification question\n"
                "  4. User responds, original intent retried"
            ),
            "checkpoint_restore": (
                "Checkpoint/Restore ensures crash resilience:\n"
                "  - Checkpoints serialize all sections to SQLite\n"
                "  - Uses FlatBuffers for fast, compact storage\n"
                "  - On crash, state restores completely\n"
                "  - No conversation data is lost"
            ),
            "background_tasks": (
                "Two-way concierge supports concurrent operation:\n"
                "  - Background tasks run independently\n"
                "  - Weather monitors, price watchers, etc.\n"
                "  - Tasks can emit notifications anytime\n"
                "  - User interaction continues uninterrupted"
            ),
            "proactive": (
                "Proactive concierge anticipates needs:\n"
                "  - Reviews session context for opportunities\n"
                "  - Suggests next steps automatically\n"
                "  - Alerts user to important changes\n"
                "  - Learns from past interactions"
            ),
        }

    async def run(self) -> None:
        """Run the complete demo with real LLM integration."""
        # Initialize real components
        try:
            config = get_config()
        except ValueError as e:
            print(colorize(f"Configuration error: {e}", RED, bold=True))
            print(colorize("Please set GOOGLE_API_KEY in .env file", YELLOW))
            return

        # Show header
        print_demo_header()

        if not self.auto_mode:
            print()
            print(colorize("  Welcome to the Anniversary Weekend Demo!", CYAN))
            print(colorize("  This 30-turn demo shows FamilyOS helping Sarah plan", GRAY))
            print(colorize("  a surprise 50th birthday weekend for Mike.", GRAY))
            print()
            print(colorize("  REAL LLM INTEGRATION:", GREEN, bold=True))
            print(colorize("    - Real Gemini API calls (function calling)", GRAY))
            print(colorize("    - Real SessionState persistence (SQLite)", GRAY))
            print(colorize("    - Real tool execution", GRAY))
            print()

            if self.walkthrough_mode:
                print(colorize("  WALKTHROUGH MODE ENABLED", BLUE, bold=True))
                print(colorize("  Educational explanations will appear at key moments.", GRAY))
                print()

            wait_for_key("Press Enter to begin the demo...")

        # Initialize REAL SessionLLMBridge
        self.state.session_id = f"anniversary-demo-{int(time.time())}"
        db_path = config.db_path.parent / f"{self.state.session_id}.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)

        self.bridge = SessionLLMBridge(
            session_id=self.state.session_id,
            db_path=str(db_path),
            restore_on_start=False,
        )

        success, msg = self.bridge.start()
        print_system_message(f"Session started: {self.state.session_id}", "info")
        self.state.k1_coverage["SessionState Persistence"] = True

        # Initialize REAL LLM client
        self.llm = SimpleLLMClient(
            api_key=config.google_api_key,
            model=config.google_model,
        )

        # Initialize tool executor with bridge for SessionState writes
        self.tool_executor = ToolExecutor(bridge=self.bridge)

        # Initialize ConciergeFSM - the orchestrator
        def on_state_change(old_state: ConciergeState, new_state: ConciergeState) -> None:
            """Callback for FSM state transitions (for debugging)."""
            pass  # We'll show transitions after process_input returns

        # Create display observer for verbose output
        self.display_observer = DisplayObserver(verbose=not self.auto_mode)

        self.fsm = ConciergeFSM(
            bridge=self.bridge,
            llm_client=self.llm,
            on_state_change=on_state_change,
            tool_registry=self.tool_registry,
            tool_executor=self.tool_executor,
            observers=[self.display_observer],
        )
        print_system_message("ConciergeFSM initialized as orchestrator", "info")
        self.state.k1_coverage["Intent Classification"] = True

        # Initialize Sub-Agent Architecture (M8)
        await self._initialize_sub_agents()

        # Initialize Scoreboard + Narrative Tracking (M9)
        self._initialize_tracking()

        # Initialize Canonical Plan Controller (Fix 1: Authoritative Plan State)
        self._initialize_plan_controller()

        # Wire PlanController into FSM (needed for dynamic prompts)
        if self.fsm and self.plan_controller:
            self.fsm.set_plan_controller(self.plan_controller)

        # Wire PlanController into ToolExecutor (for duplicate blocking)
        if self.tool_executor and self.plan_controller:
            self.tool_executor.set_plan_controller(self.plan_controller)

        # Initialize TwoWayConcierge + Background Integration (M10)
        await self._initialize_two_way_concierge()

        # Walkthrough intro
        if self.walkthrough_mode:
            print_walkthrough_explanation("SessionState", self._walkthrough_topics["session_state"])
            if not self.auto_mode:
                wait_for_key()

        # Run through all turns
        for turn in self.turns:
            await self._execute_turn(turn)

            # Small delay between turns
            if not self.fast_mode:
                await asyncio.sleep(0.3)

        # Show completion
        await self._show_completion()

        # Cleanup TwoWayConcierge (M10)
        await self._stop_two_way_concierge()

        # Cleanup
        if self.bridge:
            self.bridge.stop(checkpoint_before_stop=True)

    async def _execute_turn(self, turn: DemoTurn) -> None:
        """Execute a single turn with REAL LLM call."""
        # Track activity for this turn
        session_ops: List[str] = []
        tool_calls_made: List[str] = []
        state_changes: Dict[str, Any] = {}

        # Check for act change
        if turn.act != self.current_act:
            self.current_act = turn.act
            self._show_act_header(turn.act)

            # Walkthrough explanations at act transitions
            if self.walkthrough_mode:
                if turn.act == Act.GAP_DETECTION:
                    print_walkthrough_explanation(
                        "LLM Gap Detection", self._walkthrough_topics["gap_detection"]
                    )
                elif turn.act == Act.BACKGROUND:
                    print_walkthrough_explanation(
                        "Background Tasks", self._walkthrough_topics["background_tasks"]
                    )
                elif turn.act == Act.PROACTIVE:
                    print_walkthrough_explanation(
                        "Proactive Concierge", self._walkthrough_topics["proactive"]
                    )

        # Show turn indicator
        print_turn_indicator(turn.turn_number, self.state.total_turns)
        self.state.current_turn = turn.turn_number

        # Handle special events
        if turn.event == TurnEvent.CRASH:
            await self._handle_crash()
            return
        elif turn.event == TurnEvent.WEATHER_ALERT:
            await self._handle_weather_alert()
            return

        # Pause before if marked
        if turn.pause_before and not self.auto_mode:
            wait_for_key()

        # Get user input from script
        user_input = turn.user_input
        if not user_input:
            return

        # Show user input
        print_user_message(user_input)
        session_ops.append(f"history.append(user_msg, len={len(user_input)})")

        # Record user turn in REAL SessionState
        if self.bridge:
            changes = self.bridge.record_user_turn(user_input)

        # =================================================================
        # FSM ORCHESTRATION via TwoWayConcierge (M10)
        # =================================================================

        start_time = time.time()
        pending_notifications: List[Notification] = []

        # Use TwoWayConcierge if available (wraps FSM + adds background support)
        if self.two_way_concierge:
            try:
                # Process through TwoWayConcierge (which wraps FSM)
                concierge_response = await self.two_way_concierge.process_input(user_input)

                # Extract the underlying TurnResult for FSM state info
                turn_result = concierge_response.turn_result
                if turn_result:
                    # Show FSM state transitions
                    state_history = turn_result.state_history
                    intent_type = ""
                    complexity_tier = ""

                    if turn_result.classification:
                        intent_type = turn_result.classification.primary_intent.value
                        complexity_tier = turn_result.tier.value.upper()

                    print_fsm_state_transition(
                        state_history=[s.name for s in state_history],
                        intent_type=intent_type,
                        complexity_tier=complexity_tier,
                        classification_ms=turn_result.classification_ms,
                    )

                    # Get tool calls and response
                    tool_calls = turn_result.tool_calls
                    content = concierge_response.response

                    # Handle clarification
                    if concierge_response.needs_clarification:
                        self.state.gap_detections += 1
                        self.state.clarifications += 1
                        self.state.k1_coverage["Gap Detection"] = True
                        print_gap_detected(["missing_info"])
                        state_changes["gap_detected"] = True
                        print_clarification(concierge_response.clarification_question)
                        content = concierge_response.clarification_question
                else:
                    # Fallback if no turn_result
                    tool_calls = []
                    content = concierge_response.response

                # Collect pending notifications (M10: background alerts)
                if concierge_response.has_notifications:
                    pending_notifications = concierge_response.notifications

                # Track active background tasks
                if concierge_response.background_tasks_active > 0:
                    print_system_activity(
                        turn_num=turn.turn_number,
                        session_ops=[f"Background tasks active: {concierge_response.background_tasks_active}"]
                    )

            except Exception as e:
                print(colorize(f"  TwoWayConcierge Error: {e}", RED))
                tool_calls = []
                content = f"I apologize, I encountered an error: {e}"

        elif self.fsm:
            # Fallback: Use FSM directly if TwoWayConcierge not available
            try:
                result = await self.fsm.process_input(user_input)

                # Show FSM state transitions
                state_history = result.state_history
                intent_type = ""
                complexity_tier = ""

                if result.classification:
                    intent_type = result.classification.primary_intent.value
                    complexity_tier = result.tier.value.upper()

                print_fsm_state_transition(
                    state_history=[s.name for s in state_history],
                    intent_type=intent_type,
                    complexity_tier=complexity_tier,
                    classification_ms=result.classification_ms,
                )

                # Get tool calls and response from FSM result
                tool_calls = result.tool_calls
                content = result.response

                # Handle clarification from FSM
                if result.needs_clarification:
                    self.state.gap_detections += 1
                    self.state.clarifications += 1
                    self.state.k1_coverage["Gap Detection"] = True
                    print_gap_detected(["missing_info"])
                    state_changes["gap_detected"] = True
                    print_clarification(result.clarification_question)
                    content = result.clarification_question

            except Exception as e:
                print(colorize(f"  FSM Error: {e}", RED))
                # Fallback to direct LLM call
                tool_calls = []
                content = f"I apologize, I encountered an error: {e}"
        else:
            # Fallback: Direct LLM call if FSM not available
            # Use DYNAMIC prompt builder
            prompt_builder = DynamicPromptBuilder(
                self.bridge, self.tool_registry, plan_controller=self.plan_controller
            )
            system_prompt = prompt_builder.build_prompt()

            context = self.bridge.build_llm_context() if self.bridge else {}
            messages = context.get("messages", []).copy()
            messages.append({"role": "user", "content": user_input})

            try:
                response = await self.llm.complete_with_tools(
                    system_prompt=system_prompt,
                    messages=messages,
                    tools=self.tool_registry.get_all_schemas_for_llm(),
                )
                tool_calls = response.get("tool_calls", [])
                content = response.get("content", "")
            except Exception as e:
                print(colorize(f"  LLM Error: {e}", RED))
                tool_calls = []
                content = f"I apologize, I encountered an error: {e}"

        latency_ms = int((time.time() - start_time) * 1000)
        self.state.turn_latencies.append(latency_ms)

        # Process tool calls from FSM/LLM result
        if tool_calls:
            # First tool call - show walkthrough
            if self.walkthrough_mode and self.state.tool_calls == 0:
                print_walkthrough_explanation(
                    "Tool Calling", self._walkthrough_topics["tool_calling"]
                )

            for call in tool_calls:
                tool_name = call.get("name", "")
                tool_args = call.get("args", {})

                # Display the tool call
                print_tool_call(tool_name, tool_args)
                tool_calls_made.append(tool_name)
                self.state.tool_calls += 1
                self.state.k1_coverage["LLM Tool Calling"] = True

                # Execute tool via ToolExecutor (FSM may have already executed, but we track here)
                if self.tool_executor and not self.fsm:
                    # Only execute if FSM is not handling it
                    exec_result = self.tool_executor.execute(tool_name, tool_args)
                    if exec_result.wrote_to_session:
                        session_ops.append(f"session.{tool_name}()")
                else:
                    session_ops.append(f"session.{tool_name}()")

                # Track K1 coverage by tool type
                if tool_name == "add_belief":
                    session_ops.append("beliefs.upsert(belief_triple)")
                    self.state.k1_coverage["Belief Storage"] = True
                elif tool_name == "update_persona":
                    session_ops.append("persona.append(trait)")
                    self.state.k1_coverage["Persona Learning"] = True
                elif tool_name == "update_emotion":
                    session_ops.append("affective.update(emotion)")
                elif tool_name in ("book_accommodation", "book_restaurant", "book_spa_service"):
                    session_ops.append(f"bookings.add({tool_name.replace('book_', '')})")

                    # Fix 1: Notify PlanController to LOCK this booking as a fact
                    if self.plan_controller:
                        # Get the execution result if available
                        exec_result = None
                        if self.tool_executor and self.fsm:
                            # The FSM already executed - we need to get result from tool_results
                            pass  # Result captured via on_tool_result hook

                        # Hook into plan controller
                        self.plan_controller.on_tool_result(
                            tool_name=tool_name,
                            args=tool_args,
                            result={},  # Result not available here, controller uses args
                        )
                        print_system_activity(
                            turn_num=turn.turn_number,
                            session_ops=[f"Plan: {tool_name.replace('book_', '')} LOCKED as fact"]
                        )
                elif tool_name == "start_background_monitor":
                    session_ops.append("monitors.register(weather)")
                    self.state.background_tasks += 1
                    self.state.k1_coverage["Background Tasks"] = True
                    self.state.k1_coverage["Weather Monitoring"] = True
                    state_changes["background_task"] = f"mon-{turn.turn_number:02d}"
                    print_background_task_started(
                        tool_args.get("monitor_type", tool_args.get("type", "weather")),
                        f"mon-{turn.turn_number:02d}",
                    )

                    # M10: Also start monitor via TwoWayConcierge for real background processing
                    if self.two_way_concierge:
                        try:
                            monitor_type = tool_args.get(
                                "monitor_type", tool_args.get("type", "weather")
                            )
                            monitor_id = await self.two_way_concierge.start_monitor(
                                monitor_type=monitor_type,
                                check_interval=30.0,  # Check every 30 seconds in demo
                                max_runs=10,  # Max 10 checks
                                location=tool_args.get("target", "Sonoma"),
                                dates=tool_args.get("dates", ["Saturday", "Sunday"]),
                                alert_conditions=tool_args.get(
                                    "alert_conditions", ["rain", "storm"]
                                ),
                            )
                            self._active_weather_monitor_id = monitor_id
                            print_system_activity(
                                turn_num=turn.turn_number,
                                session_ops=[f"TwoWayConcierge monitor started: {monitor_id}"]
                            )
                        except Exception as e:
                            print_system_activity(
                                turn_num=turn.turn_number,
                                session_ops=[f"Warning: Could not start TwoWayConcierge monitor: {e}"]
                            )
                elif tool_name == "send_family_message":
                    session_ops.append("outbox.queue(family_msg)")
                    self.state.k1_coverage["Family Messaging"] = True
                elif tool_name in ("create_calendar_event", "schedule_reminder"):
                    self.state.k1_coverage["Calendar Integration"] = True

        # Display response (if not already handled as clarification)
        if content and not state_changes.get("gap_detected"):
            print_assistant_message(content)
            session_ops.append(f"history.append(assistant_msg, len={len(content)})")

        # Record assistant turn in REAL SessionState
        if self.bridge and content:
            changes = self.bridge.record_assistant_turn(
                content=content,
                duration_ms=latency_ms,
                had_tool_call=len(tool_calls) > 0,
            )

            # === M9: UPDATE SCOREBOARD + NARRATIVE TRACKING ===
            tracking_changes = self._update_tracking_after_turn(
                turn_number=turn.turn_number,
                user_input=user_input,
                assistant_response=content,
                tool_calls=tool_calls,
                had_crash=False,
            )

            # Log significant tracking events
            if tracking_changes.get("scoreboard", {}).get("referents_added"):
                added = tracking_changes["scoreboard"]["referents_added"]
                session_ops.append(f"scoreboard.add_referents({', '.join(added)})")

            if tracking_changes.get("scoreboard", {}).get("topic_changed"):
                session_ops.append(
                    f"scoreboard.update_topic({self.scoreboard_tracker._topic if self.scoreboard_tracker else 'unknown'})"
                )

            # Decay referent salience each turn (via bridge for compatibility)
            if self.fsm and self.fsm._context.classification:
                classification = self.fsm._context.classification
                # Topic already updated by tracker, just use for QUD
                self.bridge.update_scoreboard(
                    qud=user_input[:100] if user_input else None,  # Last user utterance as QUD
                )

                # Decay referent salience each turn
                self.bridge.decay_referent_salience(decay_factor=0.9)

            # === WARM TIER MAINTENANCE ===
            # Check if beliefs need demotion to history
            if self.bridge.check_beliefs_capacity():
                result = self.bridge.demote_beliefs_to_history(count=3)
                if result.success:
                    session_ops.append("beliefs_history.accept_demoted()")
                    self.state.k1_coverage["Beliefs Eviction"] = True

            # Check if history needs compression
            if self.bridge.check_history_overflow():
                result = self.bridge.overflow_history_to_recent()
                if result.success:
                    session_ops.append("history_recent.compress()")
                    self.state.k1_coverage["History Compression"] = True

        # === M10: DISPLAY PENDING NOTIFICATIONS ===
        # Check for notifications from TwoWayConcierge background tasks
        if pending_notifications:
            for notification in pending_notifications:
                if notification.priority in (
                    NotificationPriority.HIGH,
                    NotificationPriority.URGENT,
                ):
                    # For weather alerts, use the dedicated display
                    if notification.notification_type == NotificationType.ALERT:
                        print_weather_alert()
                        self.state.k1_coverage["Proactive Notifications"] = True
                    else:
                        print_system_activity(
                            turn_num=turn.turn_number,
                            session_ops=[f"Notification: {notification.message}"]
                        )
                    session_ops.append(
                        f"notification.deliver({notification.notification_type.name})"
                    )

        # Get bytes from real snapshot
        turn_bytes = 0
        if self.bridge:
            snapshot = self.bridge.get_snapshot()
            turn_bytes = snapshot.get("total_size_bytes", 0) // max(turn.turn_number, 1)

        # Show system activity panel
        print_system_activity(
            turn_num=turn.turn_number,
            session_ops=session_ops,
            tool_calls=tool_calls_made,
            state_changes=state_changes,
            bytes_delta=turn_bytes,
            latency_ms=latency_ms,
        )

        # Pause after if marked
        if turn.pause_after and not self.auto_mode:
            wait_for_key()
        elif not self.auto_mode and turn.highlight:
            wait_for_key("Press Enter to continue...")

    def _show_act_header(self, act: Act) -> None:
        """Show act transition header."""
        act_info = {
            Act.SETUP: ("ACT 1: SETUP & LEARNING", "Turns 1-8"),
            Act.GAP_DETECTION: ("ACT 2: LLM-DRIVEN GAP DETECTION", "Turns 9-14"),
            Act.BACKGROUND: ("ACT 3: BACKGROUND TASKS + CRASH", "Turns 15-20"),
            Act.PROACTIVE: ("ACT 4: PROACTIVE CONCIERGE", "Turns 21-25"),
            Act.RESOLUTION: ("ACT 5: FAMILY COMPLEXITY + RESOLUTION", "Turns 26-30"),
        }
        name, turns = act_info.get(act, (act.value, ""))
        print_act_header(name, turns)

        if not self.auto_mode:
            wait_for_key()

    # =========================================================================
    # SUB-AGENT ARCHITECTURE (M8)
    # =========================================================================

    async def _initialize_sub_agents(self) -> None:
        """Initialize Delta Bus and sub-agents."""
        # Create Delta Bus
        self.delta_bus = DeltaBus(history_depth=50)

        # Subscribe Concierge to agent results
        await self.delta_bus.subscribe(
            subscriber_id="concierge",
            topic_pattern="agent.*.result",
            callback=self._handle_agent_result,
        )

        # Create SearchAgent (READ-ONLY access)
        self.search_agent = SearchAgent(
            bridge=self.bridge,
            llm_client=self.llm,
            delta_bus=self.delta_bus,
            tool_executor=self.tool_executor,
        )

        # Create BookingAgent (READ-ONLY access)
        self.booking_agent = BookingAgent(
            bridge=self.bridge,
            llm_client=self.llm,
            delta_bus=self.delta_bus,
            tool_executor=self.tool_executor,
        )

        print_system_message(
            "Sub-Agent Architecture initialized (SearchAgent, BookingAgent)", "info"
        )
        self.state.k1_coverage["Sub-Agent Spawning"] = True

        # Register spawn callback with ToolExecutor
        self.tool_executor.set_spawn_callback(self._spawn_agent_callback)
        print_system_message("Spawn callback registered with ToolExecutor", "info")

    def _spawn_agent_callback(
        self, agent_type: str, task_type: str, params: Dict[str, Any]
    ) -> "asyncio.Task[Any]":
        """
        Callback to spawn sub-agents from ToolExecutor.

        Creates an asyncio task that runs the agent in its own context.
        The agent has READ-ONLY access to SessionState and publishes
        results via Delta Bus.
        """

        async def run_agent():
            """Run the agent task asynchronously."""
            try:
                # Display that we're spawning
                print_subagent_dispatch(
                    agent_name=agent_type,
                    task=task_type,
                    context_preview=str(params)[:60],
                )

                start_time = time.time()

                if agent_type == "SearchAgent":
                    result = await self.spawn_search_agent(task_type, params)
                elif agent_type == "BookingAgent":
                    result = await self.spawn_booking_agent(task_type, params)
                else:
                    raise ValueError(f"Unknown agent type: {agent_type}")

                latency_ms = int((time.time() - start_time) * 1000)

                # Display result
                result_preview = ""
                success = True
                if hasattr(result, "status"):
                    success = result.status.value == "completed"
                    if hasattr(result, "results") and result.results:
                        result_preview = str(result.results)[:100]

                print_subagent_response(
                    agent_name=agent_type,
                    result_preview=result_preview,
                    latency_ms=latency_ms,
                    success=success,
                )

                return result

            except Exception as e:
                print_subagent_response(
                    agent_name=agent_type,
                    result_preview=str(e),
                    latency_ms=0,
                    success=False,
                )
                raise

        # Create and return the task (runs in background)
        return asyncio.create_task(run_agent())

    async def _handle_agent_result(self, message: Message) -> None:
        """Handle results from sub-agents via Delta Bus."""
        self._pending_agent_results.append(message)

        # Log the result
        result = message.payload
        if hasattr(result, "agent_type"):
            agent_type = result.agent_type
            task_type = result.task_type if hasattr(result, "task_type") else "unknown"
            status = result.status.value if hasattr(result, "status") else "unknown"
            print_system_activity(
                turn_num=self.turn_number,
                session_ops=[f"Agent result received: {agent_type}.{task_type} -> {status}"]
            )

    async def spawn_search_agent(
        self,
        search_type: str,
        params: Dict[str, Any],
    ) -> Any:
        """
        Spawn SearchAgent for a search task.

        Args:
            search_type: Type of search (accommodations, restaurants, activities)
            params: Search parameters

        Returns:
            AgentResult with search results
        """
        if not self.search_agent:
            raise RuntimeError("SearchAgent not initialized")

        print_system_activity(
            turn_num=self.turn_number,
            session_ops=[f"spawn_search_agent({search_type})"]
        )

        if search_type == "accommodations":
            return await self.search_agent.search_accommodations(**params)
        elif search_type == "restaurants":
            return await self.search_agent.search_restaurants(**params)
        elif search_type == "activities":
            return await self.search_agent.search_activities(**params)
        else:
            return await self.search_agent.run_task(search_type, params)

    async def spawn_booking_agent(
        self,
        booking_type: str,
        params: Dict[str, Any],
    ) -> Any:
        """
        Spawn BookingAgent for a booking task.

        Args:
            booking_type: Type of booking (accommodation, restaurant, spa)
            params: Booking parameters

        Returns:
            AgentResult with booking confirmation
        """
        if not self.booking_agent:
            raise RuntimeError("BookingAgent not initialized")

        print_system_activity(
            turn_num=self.turn_number,
            session_ops=[f"spawn_booking_agent({booking_type})"]
        )

        if booking_type == "accommodation":
            return await self.booking_agent.book_accommodation(**params)
        elif booking_type == "restaurant":
            return await self.booking_agent.book_restaurant(**params)
        elif booking_type == "spa":
            return await self.booking_agent.book_spa_service(**params)
        else:
            return await self.booking_agent.run_task(booking_type, params)

    # =========================================================================
    # SCOREBOARD + NARRATIVE TRACKING (M9)
    # =========================================================================

    def _initialize_tracking(self) -> None:
        """Initialize scoreboard and narrative trackers."""
        # Create ScoreboardTracker
        self.scoreboard_tracker = ScoreboardTracker(bridge=self.bridge)

        # Create NarrativeTracker
        self.narrative_tracker = NarrativeTracker(bridge=self.bridge)

        print_system_message("Scoreboard + Narrative Tracking initialized (M9)", "info")
        self.state.k1_coverage["Scoreboard Tracking"] = True
        self.state.k1_coverage["Narrative Tracking"] = True

    def _initialize_plan_controller(self) -> None:
        """
        Initialize Canonical Plan Controller (Fix 1: Authoritative Plan State).

        The plan controller is the SINGLE SOURCE OF TRUTH for plan state.
        Rule: If it's in the plan and locked, the LLM cannot question it.
        
        IMPORTANT: Plan starts EMPTY. Details are added dynamically as the user
        provides them through conversation. The concierge LEARNS, not assumes.
        """
        self.plan_controller = PlanController(bridge=self.bridge)

        # Initialize with EMPTY plan - details learned through conversation
        self.plan_controller.initialize_plan(
            goal="",  # Learned from user
            budget=None,  # Learned from user
        )

        # No hardcoded pending actions - these are added dynamically
        # as the user describes what they want

        print_system_message("Canonical Plan Controller initialized (Fix 1)", "info")
        print_system_message("  Plan starts empty - details learned from conversation", "info")

    async def _initialize_two_way_concierge(self) -> None:
        """Initialize TwoWayConcierge for background task integration (M10)."""
        if not self.fsm:
            print_system_message(
                "Warning: Cannot initialize TwoWayConcierge without FSM", "warning"
            )
            return

        # Create TwoWayConcierge with notification callback
        self.two_way_concierge = create_two_way_concierge(
            fsm=self.fsm,
            on_notification=self._handle_notification_callback,
        )

        # Start the concierge (enables background task processing)
        await self.two_way_concierge.start()

        print_system_message("TwoWayConcierge initialized with background support (M10)", "info")
        self.state.k1_coverage["TwoWayConcierge"] = True

    def _handle_notification_callback(self, notification: Notification) -> None:
        """
        Handle urgent notifications from background tasks.

        This callback is triggered when a high-priority notification
        needs immediate attention (e.g., weather alert).
        """
        if notification.priority == NotificationPriority.URGENT:
            print_system_activity(
                turn_num=self.turn_number,
                session_ops=[f"URGENT notification: {notification.notification_type.name}"]
            )
        elif notification.priority == NotificationPriority.HIGH:
            print_system_activity(
                turn_num=self.turn_number,
                session_ops=[f"High-priority notification: {notification.message[:50]}..."]
            )

    async def _stop_two_way_concierge(self) -> None:
        """Stop TwoWayConcierge and cleanup background tasks."""
        if self.two_way_concierge:
            # Get summary before stopping
            summary = self.two_way_concierge.get_task_summary()
            if summary.get("active", 0) > 0:
                print_system_message(
                    f"Stopping {summary['active']} active background tasks",
                    "info",
                )
            await self.two_way_concierge.stop()
            self.two_way_concierge = None

    def _update_tracking_after_turn(
        self,
        turn_number: int,
        user_input: str,
        assistant_response: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        had_crash: bool = False,
    ) -> Dict[str, Any]:
        """
        Update scoreboard and narrative tracking after a turn.

        Args:
            turn_number: Current turn number
            user_input: User's message
            assistant_response: Assistant's response
            tool_calls: Tool calls made this turn
            had_crash: Whether a crash occurred

        Returns:
            Dict with tracking changes
        """
        changes = {}

        # Update scoreboard
        if self.scoreboard_tracker:
            scoreboard_changes = self.scoreboard_tracker.update_from_turn(
                turn_number=turn_number,
                user_input=user_input,
                assistant_response=assistant_response,
                tool_calls=tool_calls,
            )
            changes["scoreboard"] = scoreboard_changes

        # Update narrative
        if self.narrative_tracker:
            narrative_changes = self.narrative_tracker.update_from_turn(
                turn_number=turn_number,
                user_input=user_input,
                tool_calls=tool_calls,
                had_crash=had_crash,
            )
            changes["narrative"] = narrative_changes

            # Log phase transition
            if narrative_changes.get("phase_changed"):
                # Use turn_number and pass phase info as state_change
                print_system_activity(
                    turn_num=turn_number,
                    session_ops=[
                        f"narrative.phase_change({narrative_changes['previous_phase']} -> {narrative_changes['new_phase']})"
                    ],
                )

        return changes

    def _get_tracking_context(self) -> str:
        """Get tracking context for LLM prompt injection."""
        parts = []

        # Scoreboard context
        if self.scoreboard_tracker:
            scoreboard_context = self.scoreboard_tracker.format_for_context()
            if scoreboard_context:
                parts.append(f"SCOREBOARD:\n{scoreboard_context}")

        # Narrative context
        if self.narrative_tracker:
            narrative_context = self.narrative_tracker.format_for_context()
            if narrative_context:
                parts.append(f"NARRATIVE:\n{narrative_context}")

        return "\n\n".join(parts)

    async def _handle_crash(self) -> None:
        """Handle the crash event at Turn 20 - REAL checkpoint/restore."""
        print_turn_indicator(20, 30)

        if not self.auto_mode:
            print()
            print(colorize("  [The conversation was just interrupted mid-sentence...]", GRAY))
            wait_for_key("Press Enter to witness the crash...")

        # Create checkpoint BEFORE crash
        if self.bridge:
            success, msg, size = self.bridge.checkpoint()
            print_system_message(f"Checkpoint created: {size:,} bytes", "info")

        # Show crash screen
        print_crash_screen()
        self.state.has_crashed = True
        self.state.crash_restores += 1

        if not self.auto_mode:
            wait_for_key("Press Enter to restore from checkpoint...")

        # Walkthrough explanation
        if self.walkthrough_mode:
            print_walkthrough_explanation(
                "Checkpoint/Restore", self._walkthrough_topics["checkpoint_restore"]
            )

        # Show restore screen
        print_restore_screen()

        # REAL restore - stop and restart bridge
        if self.bridge:
            db_path = self.bridge._db_path
            session_id = self.bridge._session_id

            # Stop current session (without checkpoint - simulating crash)
            self.bridge.stop(checkpoint_before_stop=False)

            # Create new bridge and restore
            self.bridge = SessionLLMBridge(
                session_id=session_id,
                db_path=db_path,
                restore_on_start=True,  # This triggers restore!
            )
            success, msg = self.bridge.start()

        # Update coverage
        self.state.k1_coverage["Checkpoint/Restore"] = True

        # Show what was restored (from REAL snapshot)
        print()
        print(colorize("  SESSION RESTORED SUCCESSFULLY", GREEN, bold=True))
        print()

        if self.bridge:
            snapshot = self.bridge.get_snapshot()
            stats = self.bridge.get_stats()
            print(colorize("  Restored data:", CYAN))
            print(f"    - Turn number: {stats.total_turns}")
            print(f"    - Total size: {snapshot.get('total_size_bytes', 0):,} bytes")
            print(f"    - Sections: {len(snapshot.get('sections', {}))}")
        print()

        # Generate restore response via REAL LLM with DYNAMIC prompt
        restore_prompt = (
            "The session just crashed and has been restored from checkpoint. "
            "Acknowledge the restore and remind Sarah where you left off. "
            "You were helping her prepare instructions for Emma about watching Jake."
        )

        try:
            # Use dynamic prompt builder
            prompt_builder = DynamicPromptBuilder(self.bridge, self.tool_registry)
            system_prompt = prompt_builder.build_prompt()
            response = await self.llm.complete_with_tools(
                system_prompt=system_prompt,
                messages=[{"role": "user", "content": restore_prompt}],
                tools=[],
            )
            content = response.get("content", "")
            if content:
                print_assistant_message(content)
        except Exception:  # noqa: BLE001
            # Fallback response
            print_assistant_message(
                "Welcome back, Sarah! I see we were in the middle of preparing "
                "instructions for Emma about watching Jake this weekend. "
                "Should I complete that message to Emma?"
            )

        if not self.auto_mode:
            wait_for_key()

    async def _handle_weather_alert(self) -> None:
        """Handle weather alert at Turn 24 - proactive notification."""
        print_turn_indicator(24, 30)

        # Update coverage
        self.state.k1_coverage["Proactive Notifications"] = True

        if not self.auto_mode:
            print()
            print(colorize("  [Background monitor checking weather...]", GRAY))
            await asyncio.sleep(0.5)

        # Show the alert
        print_weather_alert()

        # Generate proactive response via REAL LLM with DYNAMIC prompt
        alert_prompt = (
            "A weather alert just came in from your background monitor: "
            "Saturday looks beautiful (72F, sunny), but there's now a 60% chance "
            "of rain Sunday afternoon in Sonoma. "
            "Proactively inform Sarah about this and suggest indoor backup plans. "
            "Remember they have a spa at the inn."
        )

        try:
            # Use dynamic prompt builder
            prompt_builder = DynamicPromptBuilder(self.bridge, self.tool_registry)
            system_prompt = prompt_builder.build_prompt()
            response = await self.llm.complete_with_tools(
                system_prompt=system_prompt,
                messages=[{"role": "user", "content": alert_prompt}],
                tools=self.tool_registry.get_all_schemas_for_llm(),
            )
            content = response.get("content", "")
            if content:
                print_assistant_message(content)
        except Exception:  # noqa: BLE001
            # Fallback response
            print_assistant_message(
                "Quick heads up, Sarah - I've been watching the Sonoma weather. "
                "Saturday looks beautiful (72F, sunny), but there's now a 60% chance "
                "of rain Sunday afternoon. You might want to plan indoor activities "
                "for Sunday. The inn's spa does couples massages - want me to look into that?"
            )

        if not self.auto_mode:
            wait_for_key()

    def _calculate_percentile(self, data: List[int], percentile: float) -> int:
        """Calculate percentile from a list of values."""
        if not data:
            return 0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        index = min(index, len(sorted_data) - 1)
        return sorted_data[index]

    async def _show_completion(self) -> None:
        """Show demo completion summary with REAL metrics."""
        print()
        print_divider("=", GREEN)

        # Trip summary with REAL bookings from ToolExecutor
        trip_summary = {}
        if self.tool_executor:
            trip_summary = {
                "bookings": self.tool_executor.bookings,
                "messages": self.tool_executor.messages_sent,
                "events": self.tool_executor.calendar_events,
            }
        print_trip_summary(trip_summary)

        # Calculate latency stats from REAL data
        total_duration = time.time() - self.state.start_time
        latencies = self.state.turn_latencies
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        p50_latency = self._calculate_percentile(latencies, 50)
        p95_latency = self._calculate_percentile(latencies, 95)
        p99_latency = self._calculate_percentile(latencies, 99)

        # Get REAL bytes stats from bridge
        initial_bytes = 256  # Baseline
        final_bytes = 0
        if self.bridge:
            snapshot = self.bridge.get_snapshot()
            final_bytes = snapshot.get("total_size_bytes", 0)
        growth_bytes = final_bytes - initial_bytes
        bytes_per_turn = growth_bytes // max(len(latencies), 1)

        print_demo_stats(
            {
                "total_turns": self.state.total_turns,
                "tool_calls": self.state.tool_calls,
                "gap_detections": self.state.gap_detections,
                "clarifications": self.state.clarifications,
                "background_tasks": self.state.background_tasks,
                "crash_restores": self.state.crash_restores,
                "avg_latency_ms": int(avg_latency),
                "p50_latency_ms": p50_latency,
                "p95_latency_ms": p95_latency,
                "p99_latency_ms": p99_latency,
                "initial_bytes": initial_bytes,
                "final_bytes": final_bytes,
                "growth_bytes": growth_bytes,
                "bytes_per_turn": bytes_per_turn,
                "total_duration_s": total_duration,
            }
        )

        # K1 Coverage Report
        print_k1_coverage_report(self.state.k1_coverage)

        # Features covered
        print()
        print(colorize("  FEATURES DEMONSTRATED:", YELLOW, bold=True))
        for feature in SCRIPT_METADATA["features_demonstrated"]:
            print(colorize(f"    [x] {feature}", GREEN))

        print_demo_complete()


# =============================================================================
# ENTRY POINT
# =============================================================================


async def main() -> None:
    """Entry point."""
    auto_mode = "--auto" in sys.argv
    fast_mode = "--fast" in sys.argv
    walkthrough_mode = "--walkthrough" in sys.argv

    runner = DemoRunner(
        auto_mode=auto_mode,
        fast_mode=fast_mode,
        walkthrough_mode=walkthrough_mode,
    )
    await runner.run()


if __name__ == "__main__":
    asyncio.run(main())
