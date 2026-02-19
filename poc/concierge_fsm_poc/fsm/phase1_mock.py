"""Mock Phase 1 Classifier -- Epic 1.2 (PH1-001, PH1-002).

Keyword-based drop-in replacing UltraBERT for the PoC.
Returns Phase1Result for any input string in under 1ms.
All 20 demo turns are covered by the keyword rules below.

Special flags (set on the classifier instance before calling classify()):
    raise_on_next    -- raises ClassifierError once, then resets (F26 test)
    force_cb_open    -- sets circuit-breaker flag for action mocks (F24 test)
    watchdog_timeout_ms -- exposes timeout value for ReAct loop (F15 test)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

# ---------------------------------------------------------------------------
# PH1-001: Phase1Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class Phase1Result:
    """Output of Phase 1 classification.

    Fields align to DISPATCHING routing requirements (tier, safety_band, gaps)
    and cognitive tool inputs (intent, entities, emotion).
    """

    intent: str
    tier: Literal["LOW", "MEDIUM"]
    safety_band: str  # "GREEN" | "AMBER" | "RED" | "CRISIS"
    entities: dict[str, str]
    emotion: str
    confidence: float  # 0.0 - 1.0
    gaps: list[str]
    classifier_degraded: bool = False  # True when heuristic fallback was used


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ClassifierError(Exception):
    """Raised by MockPhase1Classifier when raise_on_next is set (F26 test)."""


# ---------------------------------------------------------------------------
# PH1-002: MockPhase1Classifier
# ---------------------------------------------------------------------------

# Ordered rule table: (keywords, intent, tier, safety_band)
# First match wins.  All keywords are matched case-insensitively against the
# full source string (text + enriched_context).
#
# ORDERING RULES:
#  1. Safety-escalating rules first (CRISIS > RED > AMBER)
#  2. Most-specific intents before catch-all words like "plan"/"book"
#  3. LOW-tier rules that share keywords with MEDIUM rules come FIRST
_RULES: list[tuple[tuple[str, ...], str, Literal["LOW", "MEDIUM"], str]] = [
    # --- CRISIS (matched before everything else) ---
    (
        ("emergency", "crisis", "bleeding", "hurt", "danger"),
        "crisis",
        "LOW",
        "CRISIS",
    ),
    # --- RED: medical emergency lookup (word-boundary "er" avoids "reserve") ---
    (
        (" er ", "\ner", "e.r.", "hospital", "emergency room", "barton", "directions to"),
        "medical_lookup",
        "MEDIUM",
        "RED",
    ),
    # --- AMBER: medical info queries ---
    (
        ("allerg", "food restriction", "dietary"),
        "recall_family_info",
        "LOW",
        "AMBER",
    ),
    # --- LOW: these use keywords that also appear in MEDIUM rules -> match first ---
    (
        ("weather", "forecast", "temperature", "snow condition"),
        "weather_lookup",
        "LOW",
        "GREEN",
    ),
    (
        ("snowshoe", "rental", "ski lesson", "ski rental", "ski gear"),
        "rental_lookup",
        "LOW",
        "GREEN",
    ),
    (
        (
            "checkout time",
            "check out time",
            "check-out time",
            "pool heated",
            "is the pool",
            "pool open",
        ),
        "hotel_info",
        "LOW",
        "GREEN",
    ),
    (
        ("gondola", "cable car", "lift ticket", "start time"),
        "activity_search",
        "LOW",
        "GREEN",
    ),
    (
        ("remember that", "jake loves", "jake like"),
        "store_belief",
        "LOW",
        "GREEN",
    ),
    (
        ("cancel", "stop", "never mind", "forget it"),
        "cancel_signal",
        "LOW",
        "GREEN",
    ),
    # --- MEDIUM: specific intents before generic "plan"/"book" ---
    (
        (
            "special",
            "anniversary",
            "dinner",
            "restaurant",
            "dining",
            "vegetarian",
            "eat out",
            "reserve a dinner",
            "reserve a table",
            "reserve dinner",
        ),
        "restaurant_search",
        "MEDIUM",
        "GREEN",
    ),
    (
        (
            "drive to",
            "route to",
            "fly to",
            "fly instead",
            "take a flight",
            "book a flight",
            "plan the drive",
            "plan the route",
        ),
        "route_planner",
        "MEDIUM",
        "GREEN",
    ),
    (
        (
            "activity",
            "activities",
            "kid-friendly",
            "kid friendly",
            "fun things",
            "something fun",
            "plan fun",
            "things to do",
        ),
        "activity_search",
        "MEDIUM",
        "GREEN",
    ),
    (
        ("itinerary", "full itinerary", "plan tomorrow"),
        "trip_planning",
        "MEDIUM",
        "GREEN",
    ),
    (
        ("boat tour", "private tour", "lake tour"),
        "boat_tour",
        "LOW",
        "GREEN",
    ),
    # --- Generic hotel/booking (must come after more-specific rules) ---
    (
        (
            "hotel",
            "stay at",
            "hotel stay",
            "book a hotel",
            "reserve a hotel",
            "hotel prices",
            "hotel booking",
        ),
        "hotel_booking",
        "MEDIUM",
        "GREEN",
    ),
    # --- Broad fallback for plan/book/reserve (catches T4 "Plan our hotel stay") ---
    (
        ("plan our", "plan a", "book our", "book something", "reserve our"),
        "hotel_booking",
        "MEDIUM",
        "GREEN",
    ),
]

# Gap signatures: if intent is in this map, these required fields may be missing
_GAP_RULES: dict[str, list[str]] = {
    "hotel_booking": ["check_in", "check_out", "guests"],
    "restaurant_search": ["party_size", "time"],
    "route_planner": ["origin"],
    "trip_planning": ["dates", "family_size"],
    "activity_search": [],
    "boat_tour": ["date", "group_size"],
}

# Entity extraction patterns
_ENTITY_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    ("location", "Lake Tahoe", re.compile(r"lake\s+tahoe|tahoe", re.IGNORECASE)),
    ("budget", "", re.compile(r"\$(\d+)", re.IGNORECASE)),
    ("party_size", "", re.compile(r"(\d+)\s+(?:people|person|guests?|adult)", re.IGNORECASE)),
    (
        "dates",
        "",
        re.compile(
            r"(saturday|sunday|monday|tuesday|wednesday|thursday|friday"
            r"|sat\b|sun\b|mon\b|this\s+weekend|next\s+weekend"
            r"|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?)",
            re.IGNORECASE,
        ),
    ),
]


def _extract_entities(text: str) -> dict[str, str]:
    entities: dict[str, str] = {}
    for key, default, pattern in _ENTITY_PATTERNS:
        m = pattern.search(text)
        if m:
            value = m.group(1) if m.lastindex and m.lastindex >= 1 else (m.group(0) or default)
            entities[key] = value.strip()
    return entities


def _detect_emotion(text: str, safety_band: str) -> str:
    if safety_band == "CRISIS":
        return "scared"
    if safety_band == "RED":
        return "anxious"
    if safety_band == "AMBER":
        return "concerned"
    text_lower = text.lower()
    if any(w in text_lower for w in ("excited", "love", "amazing", "great", "fun")):
        return "excited"
    if any(w in text_lower for w in ("special", "anniversary", "birthday")):
        return "hopeful"
    return "neutral"


def _has_gap_trigger(text: str, intent: str, entities: dict[str, str]) -> list[str]:
    """Return list of missing required fields based on intent + extracted entities.

    Maps extracted entity keys to gap field names so that clarification
    answers (which add 'dates', 'party_size', etc.) satisfy the gaps
    (which use 'check_in', 'check_out', 'guests').
    """
    required = _GAP_RULES.get(intent, [])
    # Map: gap_field -> list of entity keys that satisfy it
    _SATISFIES: dict[str, tuple[str, ...]] = {
        "check_in": ("dates", "check_in"),
        "check_out": ("dates", "check_out"),
        "guests": ("party_size", "guests"),
        "party_size": ("party_size", "guests"),
        "origin": ("location", "origin"),
        "dates": ("dates", "check_in", "check_out"),
        "family_size": ("party_size", "family_size", "guests"),
        "date": ("dates", "date"),
        "group_size": ("party_size", "group_size", "guests"),
        "time": ("time", "dates"),
    }
    gaps: list[str] = []
    for field in required:
        satisfying_keys = _SATISFIES.get(field, (field,))
        if not any(k in entities for k in satisfying_keys):
            gaps.append(field)
    return gaps


# Fallback heuristic used when raise_on_next fires (F26)
def _heuristic_classify(text: str) -> Phase1Result:
    """Minimal keyword scan without the full rule engine.  Low confidence."""
    text_lower = text.lower()
    intent = "general"
    tier: Literal["LOW", "MEDIUM"] = "LOW"
    safety_band = "GREEN"
    if any(w in text_lower for w in ("plan", "hotel", "book", "trip")):
        intent = "trip_planning"
        tier = "MEDIUM"
    entities = _extract_entities(text)
    return Phase1Result(
        intent=intent,
        tier=tier,
        safety_band=safety_band,
        entities=entities,
        emotion="neutral",
        confidence=0.30,
        gaps=[],
        classifier_degraded=True,
    )


class MockPhase1Classifier:
    """Keyword-based Phase 1 classifier mock.

    Covers all 20 demo turns.  Designed to be featureful but instant: no model
    loading, no I/O, no async required.

    Special flags (set directly on the instance):
        raise_on_next (bool): next call to classify() raises ClassifierError,
            then resets.  Demo runner catches this and calls classify() again
            which routes via _heuristic_classify() on retry.  Simulates F26.
        force_cb_open (bool): injected into result.entities as a signal flag
            so action mocks can detect the F24 full-fallback scenario.
        watchdog_timeout_ms (int): exposed for ReAct loop to configure its
            watchdog timer.  Default 0 (disabled).
    """

    def __init__(self) -> None:
        self.raise_on_next: bool = False
        self.force_cb_open: bool = False
        self.watchdog_timeout_ms: int = 0

    def classify(self, text: str, enriched_context: str | None = None) -> Phase1Result:
        """Classify *text* using keyword rules.

        Args:
            text: Raw user message.
            enriched_context: Optional merged context string (e.g. after
                CLARIFICATION_RECEIVED merges user answer into original message).

        Returns:
            Phase1Result.

        Raises:
            ClassifierError: when raise_on_next is True (consumed on raise).
        """
        if self.raise_on_next:
            self.raise_on_next = False
            raise ClassifierError("Mock classifier failure (F26 simulation)")

        source = f"{text} {enriched_context or ''}".strip()
        source_lower = source.lower()

        # Match first rule
        matched_intent = "general"
        matched_tier: Literal["LOW", "MEDIUM"] = "LOW"
        matched_safety = "GREEN"
        matched = False

        for keywords, intent, tier, safety_band in _RULES:
            if any(kw in source_lower for kw in keywords):
                matched_intent = intent
                matched_tier = tier
                matched_safety = safety_band
                matched = True
                break

        entities = _extract_entities(source)

        # Inject CB-open signal for action mocks (F24)
        if self.force_cb_open:
            entities["_force_cb_open"] = "true"

        gaps = _detect_gaps(matched_intent, entities, matched_matched=matched)

        return Phase1Result(
            intent=matched_intent,
            tier=matched_tier,
            safety_band=matched_safety,
            entities=entities,
            emotion=_detect_emotion(source, matched_safety),
            confidence=0.87 if matched else 0.40,
            gaps=gaps,
        )

    def classify_with_fallback(
        self, text: str, enriched_context: str | None = None
    ) -> Phase1Result:
        """classify() with automatic heuristic fallback on ClassifierError.

        Used by demo runner to implement F26 seamlessly: fires the error path
        internally and returns a degraded result.

        Returns:
            Phase1Result (classifier_degraded=True on fallback).
        """
        try:
            return self.classify(text, enriched_context)
        except ClassifierError:
            return _heuristic_classify(f"{text} {enriched_context or ''}".strip())


def _detect_gaps(intent: str, entities: dict[str, str], *, matched_matched: bool) -> list[str]:
    """Return missing required fields for gap-triggering intents."""
    if not matched_matched:
        return []
    return _has_gap_trigger("", intent, entities)
