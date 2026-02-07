"""
LLM-Driven Gap Detector
========================

Uses LLM reasoning to detect missing information in user requests.

Replaces heuristic pattern matching with intelligent gap detection that:
- Understands context from SessionState (beliefs, persona)
- Identifies missing required parameters for likely tools
- Generates natural clarification questions
- Provides confidence scores for detected gaps
- CHECKS RESOLVED CONTEXT before asking (prevents re-asks)

Reference: FULL_ARCHITECTURE_IMPLEMENTATION_PLAN.md - Milestone 7
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from poc.session_state_demo.concierge.gap_detector import GapDetector
from poc.session_state_demo.concierge.states import Gap

if TYPE_CHECKING:
    from poc.session_state_demo.bridge import SessionLLMBridge
    from poc.session_state_demo.llm_client import SimpleLLMClient

logger = logging.getLogger(__name__)


# =============================================================================
# TOOL SCHEMAS FOR GAP DETECTION
# =============================================================================

# Simplified tool schemas with required parameters
TOOL_SCHEMAS = {
    "book_accommodation": {
        "description": "Book a hotel or accommodation",
        "required_params": ["name", "check_in_date", "check_out_date", "guests"],
        "optional_params": ["room_type", "special_requests"],
    },
    "book_restaurant": {
        "description": "Make a restaurant reservation",
        "required_params": ["restaurant_name", "date", "time", "party_size"],
        "optional_params": ["special_requests", "dietary_restrictions"],
    },
    "book_spa_service": {
        "description": "Book a spa treatment",
        "required_params": ["service_type", "date", "time"],
        "optional_params": ["therapist_preference", "special_requests"],
    },
    "search_accommodations": {
        "description": "Search for hotels and accommodations",
        "required_params": ["location", "check_in_date", "check_out_date"],
        "optional_params": ["guests", "budget", "amenities"],
    },
    "search_restaurants": {
        "description": "Search for restaurants",
        "required_params": ["location"],
        "optional_params": ["cuisine", "price_range", "date", "time", "party_size"],
    },
    "search_activities": {
        "description": "Search for activities and attractions",
        "required_params": ["location"],
        "optional_params": ["activity_type", "date", "budget"],
    },
    "create_calendar_event": {
        "description": "Create a calendar event",
        "required_params": ["title", "date", "time"],
        "optional_params": ["duration", "location", "attendees"],
    },
    "schedule_reminder": {
        "description": "Schedule a reminder",
        "required_params": ["message", "reminder_time"],
        "optional_params": ["repeat"],
    },
    "send_family_message": {
        "description": "Send a message to family members",
        "required_params": ["recipient", "message"],
        "optional_params": ["urgency"],
    },
}


# =============================================================================
# GAP DETECTION PROMPT
# =============================================================================

GAP_DETECTION_SYSTEM_PROMPT = """You are a gap detection assistant. Your job is to identify GENUINELY missing information in user requests.

Given a user request and context, determine:
1. What tool/action the user likely wants
2. What required parameters are ACTUALLY MISSING (not already known)
3. Natural questions to ask for ONLY truly missing info

CRITICAL RULES - READ CAREFULLY:
- CHECK THE KNOWN FACTS AND CONTEXT FIRST before claiming something is missing
- If a date/time is mentioned anywhere (even relatively like "next Saturday"), it is NOT missing
- If a location/hotel/restaurant is in the active referents, it is NOT missing
- If the user says "book it" or "that one", check what "it" refers to from recent context
- NEVER ask for information that's already in the beliefs or scoreboard
- Only ask if you're 80%+ confident the info is truly needed AND missing
- Prefer SOFT CONFIRMATIONS over HARD QUESTIONS when possible

SOFT vs HARD:
- SOFT: "I'll book the Vineyard Inn for next Saturday - is that right?" (if inferred)
- HARD: "Which hotel would you like?" (only if truly unknown)

OUTPUT FORMAT (JSON):
{
    "likely_tool": "tool_name or null",
    "gaps": [
        {
            "gap_type": "what is missing (e.g., 'date', 'location', 'person')",
            "slot": "the parameter slot name",
            "description": "brief description of what's missing",
            "question": "natural question to ask user",
            "confidence": 0.8,
            "is_soft_confirm": false
        }
    ],
    "inferred_values": {
        "slot_name": "inferred value from context"
    },
    "reasoning": "brief explanation including what you found in context"
}

If nothing is genuinely missing, return: {"likely_tool": "tool_name", "gaps": [], "inferred_values": {...}, "reasoning": "All needed information is present or can be inferred"}
"""

GAP_DETECTION_USER_TEMPLATE = """USER REQUEST: "{user_input}"

KNOWN FACTS FROM SESSION (DO NOT ASK FOR THESE):
{beliefs}

USER PREFERENCES:
{persona}

ACTIVE REFERENTS (recently mentioned - use these to resolve "it", "the hotel", etc.):
{referents}

RESOLVED TEMPORAL REFERENCES (LOCKED - DO NOT ASK):
{resolved_temporal}

CURRENT TOPIC: {topic}

AVAILABLE TOOLS AND THEIR REQUIREMENTS:
{tool_info}

IMPORTANT: Check the known facts and referents BEFORE claiming something is missing.
If user says "book it" and "Vineyard Inn" is in referents, the hotel is NOT missing.
If "next Saturday" has been mentioned, the date is NOT missing.

Analyze what information might be GENUINELY missing. Output JSON only."""


# =============================================================================
# LLM GAP DETECTOR
# =============================================================================


@dataclass
class LLMGapResult:
    """Result from LLM gap detection."""

    likely_tool: Optional[str]
    gaps: List[Gap]
    reasoning: str
    raw_response: str = ""


class LLMGapDetector:
    """
    Use LLM to detect missing information in user requests.

    Unlike heuristic detection, this uses LLM reasoning to:
    - Understand what the user is trying to accomplish
    - Identify which tool parameters are missing
    - Consider context already known from SessionState
    - Generate natural clarification questions

    Usage:
        detector = LLMGapDetector(llm_client, bridge)
        result = await detector.detect_gaps("Book a hotel in Sonoma")

        if result.gaps:
            print(result.gaps[0].question)  # "When would you like to check in?"
    """

    def __init__(
        self,
        llm_client: "SimpleLLMClient",
        bridge: Optional["SessionLLMBridge"] = None,
        max_gaps: int = 3,
    ):
        """
        Initialize LLM gap detector.

        Args:
            llm_client: LLM client for making API calls
            bridge: Optional SessionState bridge for context
            max_gaps: Maximum number of gaps to return
        """
        self._llm = llm_client
        self._bridge = bridge
        self._max_gaps = max_gaps

    async def detect_gaps(
        self,
        user_input: str,
        session_context: Optional[Dict[str, Any]] = None,
        likely_intent: Optional[str] = None,
    ) -> LLMGapResult:
        """
        Detect information gaps in user input using LLM reasoning.

        Args:
            user_input: The user's message
            session_context: Optional context dict (overrides bridge lookup)
            likely_intent: Optional hint about user's intent

        Returns:
            LLMGapResult with detected gaps and reasoning
        """
        # Build context from SessionState
        beliefs = self._get_beliefs_context(session_context)
        persona = self._get_persona_context(session_context)
        tool_info = self._get_relevant_tools(user_input, likely_intent)

        # Get scoreboard context (referents, topic)
        referents = self._get_referents_context(session_context)
        topic = self._get_topic_context(session_context)
        resolved_temporal = self._get_resolved_temporal(session_context)

        # CRITICAL: Force ALL values to be strings for .format()
        # This prevents dict.__format__ errors when any method returns a dict
        def to_str(val: Any, default: str) -> str:
            """Convert any value to string, with default for empty/None."""
            if val is None:
                return default
            if isinstance(val, dict):
                return str(val) if val else default
            if isinstance(val, str):
                return val if val else default
            return str(val) if val else default

        beliefs = to_str(beliefs, "No facts known yet")
        persona = to_str(persona, "No preferences known yet")
        referents = to_str(referents, "No recent referents")
        topic = to_str(topic, "Not set")
        resolved_temporal = to_str(resolved_temporal, "None yet")
        tool_info = to_str(tool_info, "No tools")

        # Build prompt with full context
        user_prompt = GAP_DETECTION_USER_TEMPLATE.format(
            user_input=user_input,
            beliefs=beliefs,
            persona=persona,
            referents=referents,
            resolved_temporal=resolved_temporal,
            topic=topic,
            tool_info=tool_info,
        )

        try:
            # Call LLM (note: temperature not supported by SimpleLLMClient)
            response = await self._llm.complete(
                system_prompt=GAP_DETECTION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )

            # Parse response
            return self._parse_response(response, user_input)

        except Exception as e:
            logger.warning(f"LLM gap detection failed: {e}")
            # Return empty result on failure
            return LLMGapResult(
                likely_tool=None,
                gaps=[],
                reasoning=f"Gap detection failed: {e}",
                raw_response="",
            )

    def _get_referents_context(self, session_context: Optional[Dict] = None) -> str:
        """Get active referents from scoreboard for pronoun resolution."""
        if session_context and "scoreboard" in session_context:
            scoreboard = session_context["scoreboard"]
            if isinstance(scoreboard, dict):
                referents = scoreboard.get("referents", {})
                if referents:
                    lines = []
                    for name, data in list(referents.items())[:10]:
                        # Handle both formats: data could be a dict or a float
                        if isinstance(data, dict):
                            sal = data.get("salience", 0.5)
                        else:
                            sal = float(data) if data else 0.5
                        lines.append(f"- {name} (salience: {sal:.1f})")
                    return "\n".join(lines)
        if self._bridge:
            try:
                data = self._bridge.get_section_data("scoreboard")
                if "error" not in data:
                    referents = data.get("referents", {})
                    if referents:
                        lines = []
                        for name, ref_data in list(referents.items())[:10]:
                            # Handle both formats: data could be a dict or a float
                            if isinstance(ref_data, dict):
                                sal = ref_data.get("salience", 0.5)
                            else:
                                sal = float(ref_data) if ref_data else 0.5
                            lines.append(f"- {name} (salience: {sal:.1f})")
                        return "\n".join(lines)
            except Exception:
                pass
        return ""

    def _get_topic_context(self, session_context: Optional[Dict] = None) -> str:
        """Get current topic from scoreboard."""
        if session_context and "scoreboard" in session_context:
            scoreboard = session_context["scoreboard"]
            if isinstance(scoreboard, dict):
                return scoreboard.get("topic", "")
        if self._bridge:
            try:
                data = self._bridge.get_section_data("scoreboard")
                if "error" not in data:
                    return data.get("topic", "")
            except Exception:
                pass
        return ""

    def _get_resolved_temporal(self, session_context: Optional[Dict] = None) -> str:
        """Get resolved temporal references (dates that should NOT be asked about)."""
        lines = []

        # FIRST: Check resolved_refs from ContextResolver (most reliable)
        if session_context and "resolved_refs" in session_context:
            resolved = session_context["resolved_refs"]
            if isinstance(resolved, dict):
                for key, ref in resolved.items():
                    # ResolvedReference dataclass or dict
                    if hasattr(ref, "resolved"):
                        lines.append(f"- {ref.original}: {ref.resolved} (LOCKED)")
                    elif isinstance(ref, dict):
                        lines.append(
                            f"- {ref.get('original', key)}: {ref.get('resolved', '')} (LOCKED)"
                        )
                    else:
                        lines.append(f"- {key}: {ref} (LOCKED)")

        # Also check beliefs for date info (as fallback)
        if session_context and "beliefs" in session_context:
            beliefs = session_context["beliefs"]
            if isinstance(beliefs, dict):
                # Look for any date-related beliefs
                for subject, predicates in beliefs.items():
                    if isinstance(predicates, dict):
                        for pred, obj in predicates.items():
                            # Defensive: ensure pred is a string
                            if (
                                pred
                                and isinstance(pred, str)
                                and any(
                                    word in pred.lower()
                                    for word in ["date", "time", "when", "saturday", "sunday"]
                                )
                            ):
                                lines.append(f"- {subject} {pred}: {obj}")
                    elif (
                        subject
                        and isinstance(subject, str)
                        and ("date" in subject.lower() or "weekend" in subject.lower())
                    ):
                        lines.append(f"- {subject}: {predicates}")

        if self._bridge:
            try:
                data = self._bridge.get_section_data("beliefs_active")
                if "error" not in data:
                    beliefs = data.get("beliefs", {})
                    for subject, predicates in beliefs.items():
                        if isinstance(predicates, dict):
                            for pred, obj in predicates.items():
                                # Defensive: ensure pred is a string
                                if (
                                    pred
                                    and isinstance(pred, str)
                                    and any(
                                        word in pred.lower()
                                        for word in [
                                            "date",
                                            "time",
                                            "when",
                                            "check_in",
                                            "check_out",
                                        ]
                                    )
                                ):
                                    lines.append(f"- {subject} {pred}: {obj}")
            except Exception:
                pass

        return "\n".join(lines) if lines else ""

    def _get_beliefs_context(self, session_context: Optional[Dict] = None) -> str:
        """Get beliefs from SessionState for context."""
        if session_context and "beliefs" in session_context:
            beliefs = session_context["beliefs"]
            if isinstance(beliefs, dict):
                lines = []
                for subject, predicates in beliefs.items():
                    if isinstance(predicates, dict):
                        for pred, obj in predicates.items():
                            lines.append(f"- {subject} {pred} {obj}")
                    else:
                        lines.append(f"- {subject}: {predicates}")
                return "\n".join(lines[:15])
            return str(beliefs)

        if self._bridge:
            try:
                data = self._bridge.get_section_data("beliefs_active")
                if "error" not in data:
                    beliefs = data.get("beliefs", {})
                    lines = []
                    for subject, predicates in beliefs.items():
                        if isinstance(predicates, dict):
                            for pred, obj in predicates.items():
                                lines.append(f"- {subject} {pred} {obj}")
                    return "\n".join(lines[:15]) if lines else ""
            except Exception:
                pass

        return ""

    def _get_persona_context(self, session_context: Optional[Dict] = None) -> str:
        """Get persona from SessionState for context."""
        if session_context and "persona" in session_context:
            return str(session_context["persona"])

        if self._bridge:
            try:
                data = self._bridge.get_section_data("persona")
                if "error" not in data:
                    traits = data.get("traits", {})
                    lines = [f"- {k}: {v}" for k, v in list(traits.items())[:10]]
                    return "\n".join(lines) if lines else ""
            except Exception:
                pass

        return ""

    def _get_relevant_tools(
        self,
        user_input: str,
        likely_intent: Optional[str] = None,
    ) -> str:
        """Get relevant tool schemas based on input keywords."""
        input_lower = user_input.lower()

        # Keywords to tool mapping
        keyword_tools = {
            "book": ["book_accommodation", "book_restaurant", "book_spa_service"],
            "hotel": ["book_accommodation", "search_accommodations"],
            "accommodation": ["book_accommodation", "search_accommodations"],
            "restaurant": ["book_restaurant", "search_restaurants"],
            "dinner": ["book_restaurant", "search_restaurants"],
            "lunch": ["book_restaurant", "search_restaurants"],
            "spa": ["book_spa_service"],
            "massage": ["book_spa_service"],
            "search": ["search_accommodations", "search_restaurants", "search_activities"],
            "find": ["search_accommodations", "search_restaurants", "search_activities"],
            "activity": ["search_activities"],
            "remind": ["schedule_reminder"],
            "calendar": ["create_calendar_event"],
            "message": ["send_family_message"],
            "text": ["send_family_message"],
        }

        # Find relevant tools
        relevant = set()
        for keyword, tools in keyword_tools.items():
            if keyword in input_lower:
                relevant.update(tools)

        # If no matches, include common tools
        if not relevant:
            relevant = {"search_accommodations", "search_restaurants", "search_activities"}

        # Build tool info string
        lines = []
        for tool_name in relevant:
            if tool_name in TOOL_SCHEMAS:
                schema = TOOL_SCHEMAS[tool_name]
                lines.append(f"\n{tool_name}: {schema['description']}")
                lines.append(f"  Required: {', '.join(schema['required_params'])}")
                if schema["optional_params"]:
                    lines.append(f"  Optional: {', '.join(schema['optional_params'])}")

        return "\n".join(lines) if lines else "No specific tools identified"

    def _parse_response(self, response: str, user_input: str) -> LLMGapResult:
        """Parse LLM response into structured gaps."""
        raw_response = response

        try:
            # Try to extract JSON from response
            json_match = re.search(r"\{[\s\S]*\}", response)
            if json_match:
                data = json.loads(json_match.group())
            else:
                # No JSON found
                return LLMGapResult(
                    likely_tool=None,
                    gaps=[],
                    reasoning="Could not parse LLM response",
                    raw_response=raw_response,
                )

            # Extract fields
            likely_tool = data.get("likely_tool")
            reasoning = data.get("reasoning", "")
            raw_gaps = data.get("gaps", [])

            # Convert to Gap objects
            gaps: List[Gap] = []
            for g in raw_gaps[: self._max_gaps]:
                gap = Gap(
                    gap_type=g.get("gap_type", "unknown"),
                    description=g.get("description", g.get("gap_type", "")),
                    question=g.get(
                        "question",
                        f"Could you please provide the {g.get('gap_type', 'missing information')}?",
                    ),
                    context=user_input,
                    confidence=float(g.get("confidence", 0.8)),
                )
                # Store slot in gap_type if provided
                if "slot" in g:
                    gap.gap_type = g["slot"]
                gaps.append(gap)

            return LLMGapResult(
                likely_tool=likely_tool,
                gaps=gaps,
                reasoning=reasoning,
                raw_response=raw_response,
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse gap detection JSON: {e}")
            return LLMGapResult(
                likely_tool=None,
                gaps=[],
                reasoning=f"JSON parse error: {e}",
                raw_response=raw_response,
            )
        except Exception as e:
            logger.warning(f"Error parsing gap response: {e}")
            return LLMGapResult(
                likely_tool=None,
                gaps=[],
                reasoning=f"Parse error: {e}",
                raw_response=raw_response,
            )


# =============================================================================
# HYBRID GAP DETECTOR (Heuristic + LLM)
# =============================================================================


class HybridGapDetector:
    """
    Combines fast heuristic detection with LLM-powered detection.

    Strategy:
    1. Run heuristic detector first (fast, cheap)
    2. If heuristics find gaps with high confidence, use those
    3. Otherwise, fall back to LLM for complex cases

    This balances speed and accuracy while minimizing API costs.
    """

    def __init__(
        self,
        llm_detector: LLMGapDetector,
        heuristic_detector: Optional["GapDetector"] = None,
        llm_threshold: float = 0.7,
    ):
        """
        Initialize hybrid detector.

        Args:
            llm_detector: LLM-based gap detector
            heuristic_detector: Optional heuristic detector (falls back to LLM-only if None)
            llm_threshold: Min heuristic confidence before using LLM fallback
        """
        self._llm_detector = llm_detector
        self._heuristic_detector = heuristic_detector
        self._llm_threshold = llm_threshold

    async def detect_gaps(
        self,
        user_input: str,
        session_context: Optional[Dict[str, Any]] = None,
        force_llm: bool = False,
    ) -> List[Gap]:
        """
        Detect gaps using hybrid approach.

        Args:
            user_input: User's message
            session_context: Optional session context
            force_llm: Force LLM detection (skip heuristics)

        Returns:
            List of detected gaps
        """
        # Try heuristics first if available and not forced to use LLM
        if self._heuristic_detector and not force_llm:
            heuristic_gaps = self._heuristic_detector.detect_gaps(user_input, session_context)

            # If high-confidence gaps found, use them
            if heuristic_gaps and all(g.confidence >= self._llm_threshold for g in heuristic_gaps):
                logger.debug(f"Using heuristic gaps: {len(heuristic_gaps)}")
                return heuristic_gaps

        # Fall back to LLM for complex cases
        result = await self._llm_detector.detect_gaps(user_input, session_context)
        logger.debug(f"Using LLM gaps: {len(result.gaps)}, reasoning: {result.reasoning}")
        return result.gaps
