"""Read Tool Mocks -- Epic 2.3 (READ-001 through READ-004).

All three canned-data read tools return deterministic data keyed by query keywords.
READ-003 and READ-004 use real SessionState via ``manager`` and are safe in any test tier.

Tools:
    READ-001  recall_memory()          -- K0 memory lookup mock (canned family data)
    READ-002  discover_capabilities()  -- Discovery registry mock (35+ capabilities)
    READ-003  summarize_context()      -- Real SessionState snapshot -> extractive summary
    READ-004  read_session_state()     -- Real SessionState section reader (structured data)

Gemini-compatible JSON schemas are in READ_SCHEMAS (list[dict]).
"""

from __future__ import annotations

import time
from typing import Any

# ---------------------------------------------------------------------------
# READ-001 canned memory corpus
# ---------------------------------------------------------------------------

# Scenario-specific corpus (Lake Tahoe demo family).
# In --user mode, _active_corpus is set to [] so recall_memory returns nothing.
_SCENARIO_MEMORY_CORPUS: list[dict[str, Any]] = [
    # Allergy / food restriction facts
    {
        "memory_id": "mem-001",
        "type": "belief",
        "subject": "Mom",
        "predicate": "allergic_to",
        "object": "shellfish",
        "confidence": 0.97,
        "source": "family_profile",
        "tags": ["allergy", "food", "health", "mom"],
    },
    {
        "memory_id": "mem-002",
        "type": "belief",
        "subject": "Jake",
        "predicate": "allergic_to",
        "object": "peanuts",
        "confidence": 0.95,
        "source": "family_profile",
        "tags": ["allergy", "food", "health", "jake"],
    },
    # Past trip history
    {
        "memory_id": "mem-003",
        "type": "event",
        "summary": "Family went to Lake Tahoe in 2024, stayed at Hyatt Regency",
        "date": "2024-02",
        "participants": ["Mom", "Dad", "Jake", "Emma"],
        "tags": ["lake tahoe", "trip", "travel", "2024", "hyatt"],
    },
    # Preferences
    {
        "memory_id": "mem-004",
        "type": "preference",
        "subject": "Jake",
        "predicate": "loves",
        "object": "snow activities",
        "confidence": 0.9,
        "source": "observed",
        "tags": ["jake", "snow", "activities", "outdoors"],
    },
    {
        "memory_id": "mem-005",
        "type": "preference",
        "subject": "Emma",
        "predicate": "prefers",
        "object": "indoor activities",
        "confidence": 0.8,
        "source": "stated",
        "tags": ["emma", "indoors", "activities"],
    },
    # Emergency
    {
        "memory_id": "mem-006",
        "type": "fact",
        "subject": "Barton Memorial Hospital",
        "predicate": "located_at",
        "object": "2170 South Ave, South Lake Tahoe, CA",
        "confidence": 1.0,
        "source": "public_data",
        "tags": ["hospital", "er", "emergency", "barton", "south lake tahoe", "directions"],
    },
    {
        "memory_id": "mem-007",
        "type": "fact",
        "subject": "Barton Memorial Hospital ER",
        "predicate": "phone",
        "object": "530-541-3420",
        "confidence": 1.0,
        "source": "public_data",
        "tags": ["hospital", "er", "emergency", "phone", "barton"],
    },
]

# Active corpus: points to scenario corpus by default, cleared for --user mode.
_active_corpus: list[dict[str, Any]] = list(_SCENARIO_MEMORY_CORPUS)


def clear_memory_corpus() -> None:
    """Clear the memory corpus (for --user mode where no pre-loaded family exists)."""
    global _active_corpus
    _active_corpus = []


def reset_memory_corpus() -> None:
    """Reset the memory corpus to the scenario default (for scripted/guided modes)."""
    global _active_corpus
    _active_corpus = list(_SCENARIO_MEMORY_CORPUS)


# Tag token sets for scoring (lower index = higher relevance)
_TAG_PRIORITY: dict[str, tuple[str, ...]] = {
    "allergy": ("allergy", "food", "health", "restriction"),
    "trip": ("lake tahoe", "trip", "travel"),
    "jake": ("jake", "snow"),
    "hospital": ("hospital", "er", "emergency", "barton", "directions"),
}

_MOCK_LATENCY_MS = 42
_DEFAULT_MEMORY = [
    {
        "memory_id": "mem-000",
        "type": "general",
        "summary": "No specific memories found for this query",
        "tags": [],
    }
]


def _score(entry: dict[str, Any], query_lower: str) -> int:
    """Return relevance score (higher = more relevant) for a memory entry."""
    score = 0
    for tag in entry.get("tags", []):
        # Use whole-word matching: tag must appear as a standalone token
        if f" {tag} " in f" {query_lower} ":
            score += 2
    # Also check meaningful content fields (not 'type' to avoid false positives)
    for field in ("summary", "subject", "object", "predicate"):
        value = str(entry.get(field, "")).lower()
        if value and len(value) > 2 and value in query_lower:
            score += 1
    return score


# ---------------------------------------------------------------------------
# READ-001: recall_memory()
# ---------------------------------------------------------------------------


def recall_memory(
    query: str = "",
    memory_type: str = "",
    subject: str = "",
    limit: int = 5,
) -> dict[str, Any]:
    """Return canned family memory items relevant to the query.

    Matches against pre-loaded memory corpus using keyword overlap.

    Args:
        query:        Free-text search query.
        memory_type:  Filter by type: ``"belief"``, ``"event"``, ``"preference"``, ``"fact"``
                      or ``""`` for all.
        subject:      Filter by subject field (case-insensitive).
        limit:        Maximum number of results to return.

    Returns:
        ``{"memories": list, "total_found": int, "query_latency_ms": int}``
    """
    q = f"{query} {subject}".lower()

    scored: list[tuple[int, dict[str, Any]]] = []
    for entry in _active_corpus:
        if memory_type and entry.get("type") != memory_type:
            continue
        if subject and subject.lower() not in entry.get("subject", "").lower():
            continue
        s = _score(entry, q)
        if s > 0:
            scored.append((s, entry))

    scored.sort(key=lambda t: t[0], reverse=True)
    results = [e for _, e in scored[:limit]]

    if not results:
        results = _DEFAULT_MEMORY

    # Render SVO triples as natural language so the LLM can use them
    # without needing to parse structured data.
    summaries: list[str] = []
    for entry in results:
        subj = entry.get("subject", "")
        pred = entry.get("predicate", "")
        obj = entry.get("object", "")
        summary = entry.get("summary", "")
        if subj and pred and obj:
            # SVO triple -> natural language
            readable_pred = pred.replace("_", " ")
            summaries.append(f"{subj} {readable_pred} {obj}")
        elif summary:
            summaries.append(summary)
    readable_summary = "; ".join(summaries) if summaries else ""

    return {
        "memories": results,
        "total_found": len(results),
        "query_latency_ms": _MOCK_LATENCY_MS,
        "readable_summary": readable_summary,
    }


# ---------------------------------------------------------------------------
# READ-002 capability corpus
# ---------------------------------------------------------------------------

DEMO_CAPABILITIES: list[dict[str, Any]] = [
    # ---- TRAVEL & LOGISTICS ----
    {
        "name": "tool.execute.weather_lookup",
        "version": "1.0",
        "domain": ["TRAVEL", "INFORMATION"],
        "safety_band": "GREEN",
        "description": "Look up weather conditions for a location and date range.",
        "required_inputs": ["location", "date_range"],
        "avg_latency_ms": 200,
    },
    {
        "name": "tool.execute.hotel_booking",
        "version": "2.1",
        "domain": ["TRAVEL", "BOOKING"],
        "safety_band": "AMBER",
        "description": "Search and book hotel rooms for a destination.",
        "required_inputs": ["location", "check_in", "check_out", "guests"],
        "avg_latency_ms": 1500,
    },
    {
        "name": "tool.execute.activity_search",
        "version": "1.3",
        "domain": ["TRAVEL", "FAMILY"],
        "safety_band": "GREEN",
        "description": "Discover family-friendly activities near a location.",
        "required_inputs": ["location", "domain"],
        "avg_latency_ms": 400,
    },
    {
        "name": "tool.execute.restaurant_search",
        "version": "1.1",
        "domain": ["FOOD", "FAMILY"],
        "safety_band": "GREEN",
        "description": "Find restaurants matching dietary and party requirements.",
        "required_inputs": ["location"],
        "avg_latency_ms": 350,
    },
    {
        "name": "tool.execute.flight_search",
        "version": "1.0",
        "domain": ["TRAVEL", "BOOKING"],
        "safety_band": "GREEN",
        "description": "Search flights between two airports for given dates and passengers.",
        "required_inputs": ["origin", "destination", "departure_date", "passengers"],
        "avg_latency_ms": 800,
    },
    {
        "name": "tool.execute.car_rental",
        "version": "1.0",
        "domain": ["TRAVEL", "BOOKING"],
        "safety_band": "AMBER",
        "description": "Search and reserve rental cars at a location for given dates.",
        "required_inputs": ["location", "pickup_date", "return_date"],
        "avg_latency_ms": 600,
    },
    {
        "name": "tool.execute.airport_transfer",
        "version": "1.0",
        "domain": ["TRAVEL", "TRANSPORTATION"],
        "safety_band": "GREEN",
        "description": "Book airport shuttle, taxi, or rideshare transfer.",
        "required_inputs": ["airport", "destination", "date", "time"],
        "avg_latency_ms": 300,
    },
    {
        "name": "tool.execute.travel_insurance",
        "version": "1.0",
        "domain": ["TRAVEL", "FINANCE"],
        "safety_band": "AMBER",
        "description": "Get travel insurance quotes for a trip.",
        "required_inputs": ["destination", "dates", "travelers"],
        "avg_latency_ms": 500,
    },
    # ---- FOOD & DINING ----
    {
        "name": "tool.execute.grocery_list",
        "version": "1.0",
        "domain": ["FOOD", "HOME"],
        "safety_band": "GREEN",
        "description": "Generate or manage a grocery shopping list based on meals and preferences.",
        "required_inputs": ["items_or_meals"],
        "avg_latency_ms": 100,
    },
    {
        "name": "tool.execute.meal_planning",
        "version": "1.0",
        "domain": ["FOOD", "FAMILY"],
        "safety_band": "GREEN",
        "description": "Plan weekly meals considering dietary restrictions and preferences.",
        "required_inputs": ["days", "family_size"],
        "avg_latency_ms": 300,
    },
    {
        "name": "tool.execute.recipe_search",
        "version": "1.0",
        "domain": ["FOOD", "INFORMATION"],
        "safety_band": "GREEN",
        "description": "Search recipes by ingredients, cuisine, dietary needs, or cooking time.",
        "required_inputs": ["query"],
        "avg_latency_ms": 250,
    },
    {
        "name": "tool.execute.food_delivery",
        "version": "1.0",
        "domain": ["FOOD", "BOOKING"],
        "safety_band": "AMBER",
        "description": "Order food delivery from local restaurants.",
        "required_inputs": ["restaurant", "items", "address"],
        "avg_latency_ms": 400,
    },
    # ---- HEALTH & WELLNESS ----
    {
        "name": "tool.execute.doctor_appointment",
        "version": "1.0",
        "domain": ["HEALTH", "BOOKING"],
        "safety_band": "AMBER",
        "description": "Search for doctors and book medical appointments.",
        "required_inputs": ["specialty", "location"],
        "avg_latency_ms": 700,
    },
    {
        "name": "tool.execute.pharmacy_search",
        "version": "1.0",
        "domain": ["HEALTH", "INFORMATION"],
        "safety_band": "GREEN",
        "description": "Find nearby pharmacies and check medication availability.",
        "required_inputs": ["location"],
        "avg_latency_ms": 300,
    },
    {
        "name": "tool.execute.fitness_tracker",
        "version": "1.0",
        "domain": ["HEALTH", "WELLNESS"],
        "safety_band": "GREEN",
        "description": "Log workouts, track fitness goals, and get exercise suggestions.",
        "required_inputs": ["activity_type"],
        "avg_latency_ms": 150,
    },
    {
        "name": "tool.execute.medication_reminder",
        "version": "1.0",
        "domain": ["HEALTH", "FAMILY"],
        "safety_band": "AMBER",
        "description": "Set up and manage medication reminders for family members.",
        "required_inputs": ["person", "medication", "schedule"],
        "avg_latency_ms": 100,
    },
    # ---- FINANCE ----
    {
        "name": "tool.execute.budget_tracker",
        "version": "1.0",
        "domain": ["FINANCE", "FAMILY"],
        "safety_band": "GREEN",
        "description": "Track expenses, set budget limits, and view spending summaries.",
        "required_inputs": ["category"],
        "avg_latency_ms": 200,
    },
    {
        "name": "tool.execute.bill_reminder",
        "version": "1.0",
        "domain": ["FINANCE", "HOME"],
        "safety_band": "GREEN",
        "description": "Set up bill payment reminders and track due dates.",
        "required_inputs": ["bill_name", "due_date"],
        "avg_latency_ms": 100,
    },
    # ---- EDUCATION ----
    {
        "name": "tool.execute.homework_help",
        "version": "1.0",
        "domain": ["EDUCATION", "FAMILY"],
        "safety_band": "GREEN",
        "description": "Get help with homework questions across subjects (math, science, etc.).",
        "required_inputs": ["subject", "question"],
        "avg_latency_ms": 500,
    },
    {
        "name": "tool.execute.tutor_search",
        "version": "1.0",
        "domain": ["EDUCATION", "BOOKING"],
        "safety_band": "GREEN",
        "description": "Find tutors for specific subjects and grade levels.",
        "required_inputs": ["subject", "grade_level", "location"],
        "avg_latency_ms": 400,
    },
    {
        "name": "tool.execute.school_calendar",
        "version": "1.0",
        "domain": ["EDUCATION", "FAMILY"],
        "safety_band": "GREEN",
        "description": "Look up school events, holidays, and important dates.",
        "required_inputs": ["school_name"],
        "avg_latency_ms": 200,
    },
    # ---- HOME ----
    {
        "name": "tool.execute.home_maintenance",
        "version": "1.0",
        "domain": ["HOME", "BOOKING"],
        "safety_band": "AMBER",
        "description": "Find and book home repair/maintenance professionals (plumber, electrician, etc.).",
        "required_inputs": ["service_type", "location"],
        "avg_latency_ms": 600,
    },
    {
        "name": "tool.execute.smart_home_control",
        "version": "1.0",
        "domain": ["HOME", "AUTOMATION"],
        "safety_band": "GREEN",
        "description": "Control smart home devices: lights, thermostat, locks, cameras.",
        "required_inputs": ["device", "action"],
        "avg_latency_ms": 100,
    },
    {
        "name": "tool.execute.chore_scheduler",
        "version": "1.0",
        "domain": ["HOME", "FAMILY"],
        "safety_band": "GREEN",
        "description": "Create and manage family chore schedules and assignments.",
        "required_inputs": ["family_members"],
        "avg_latency_ms": 150,
    },
    # ---- ENTERTAINMENT ----
    {
        "name": "tool.execute.movie_search",
        "version": "1.0",
        "domain": ["ENTERTAINMENT", "INFORMATION"],
        "safety_band": "GREEN",
        "description": "Search movies by genre, rating, and showtimes at nearby theaters.",
        "required_inputs": ["query"],
        "avg_latency_ms": 300,
    },
    {
        "name": "tool.execute.event_tickets",
        "version": "1.0",
        "domain": ["ENTERTAINMENT", "BOOKING"],
        "safety_band": "AMBER",
        "description": "Search and purchase tickets for concerts, sports, shows, and local events.",
        "required_inputs": ["event_type", "location"],
        "avg_latency_ms": 500,
    },
    {
        "name": "tool.execute.game_night_planner",
        "version": "1.0",
        "domain": ["ENTERTAINMENT", "FAMILY"],
        "safety_band": "GREEN",
        "description": "Suggest board games, party games, or activities for family game night.",
        "required_inputs": ["player_count", "age_range"],
        "avg_latency_ms": 100,
    },
    # ---- SOCIAL ----
    {
        "name": "tool.execute.gift_suggestions",
        "version": "1.0",
        "domain": ["SOCIAL", "SHOPPING"],
        "safety_band": "GREEN",
        "description": "Get gift ideas based on person, occasion, budget, and interests.",
        "required_inputs": ["person", "occasion"],
        "avg_latency_ms": 300,
    },
    {
        "name": "tool.execute.party_planner",
        "version": "1.0",
        "domain": ["SOCIAL", "FAMILY"],
        "safety_band": "GREEN",
        "description": "Plan birthday parties, celebrations, and family gatherings.",
        "required_inputs": ["event_type", "guest_count"],
        "avg_latency_ms": 400,
    },
    # ---- TRANSPORTATION ----
    {
        "name": "tool.execute.ride_booking",
        "version": "1.0",
        "domain": ["TRANSPORTATION", "BOOKING"],
        "safety_band": "AMBER",
        "description": "Book a rideshare (Uber/Lyft) or taxi for pickup.",
        "required_inputs": ["pickup", "destination"],
        "avg_latency_ms": 200,
    },
    {
        "name": "tool.execute.transit_info",
        "version": "1.0",
        "domain": ["TRANSPORTATION", "INFORMATION"],
        "safety_band": "GREEN",
        "description": "Get public transit routes, schedules, and real-time arrival info.",
        "required_inputs": ["origin", "destination"],
        "avg_latency_ms": 250,
    },
    # ---- SHOPPING ----
    {
        "name": "tool.execute.product_search",
        "version": "1.0",
        "domain": ["SHOPPING", "INFORMATION"],
        "safety_band": "GREEN",
        "description": "Search for products with price comparison across stores.",
        "required_inputs": ["query"],
        "avg_latency_ms": 400,
    },
    # ---- CALENDAR & SCHEDULING ----
    {
        "name": "tool.execute.calendar_manage",
        "version": "1.0",
        "domain": ["CALENDAR", "FAMILY"],
        "safety_band": "GREEN",
        "description": "View, create, and manage family calendar events and reminders.",
        "required_inputs": ["action", "event_details"],
        "avg_latency_ms": 150,
    },
    # ---- PETS ----
    {
        "name": "tool.execute.vet_appointment",
        "version": "1.0",
        "domain": ["PETS", "BOOKING"],
        "safety_band": "AMBER",
        "description": "Find veterinarians and book appointments for pets.",
        "required_inputs": ["pet_type", "reason", "location"],
        "avg_latency_ms": 500,
    },
    {
        "name": "tool.execute.pet_care",
        "version": "1.0",
        "domain": ["PETS", "INFORMATION"],
        "safety_band": "GREEN",
        "description": "Get pet care advice, feeding schedules, and grooming tips.",
        "required_inputs": ["pet_type", "query"],
        "avg_latency_ms": 200,
    },
    # ---- WORKFLOWS (composite) ----
    {
        "name": "workflow.trip_planning",
        "version": "3.0",
        "domain": ["TRAVEL", "PLANNING"],
        "safety_band": "AMBER",
        "description": "End-to-end multi-step trip planning workflow.",
        "required_inputs": ["destination", "dates", "family_size"],
        "avg_latency_ms": 4000,
    },
    {
        "name": "workflow.event_planning",
        "version": "1.0",
        "domain": ["SOCIAL", "PLANNING"],
        "safety_band": "AMBER",
        "description": "End-to-end event planning: venue, catering, invitations, timeline.",
        "required_inputs": ["event_type", "date", "guest_count"],
        "avg_latency_ms": 3000,
    },
]

_DISCOVERY_LATENCY_MS = 18


# ---------------------------------------------------------------------------
# READ-002: discover_capabilities()
# ---------------------------------------------------------------------------


def discover_capabilities(
    query: str = "",
    domain: str = "",
    safety_band: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    """Return the list of available demo capabilities.

    Optionally filters by ``domain`` and ``safety_band``.

    Args:
        query:       Free-text match against capability name or description.
        domain:      Filter: capability must include this domain string (case-insensitive).
        safety_band: Filter: capability safety_band must match (GREEN / AMBER / RED).
        limit:       Maximum results to return.

    Returns:
        ``{"capabilities": list, "total_found": int, "query_latency_ms": int}``
    """
    caps = list(DEMO_CAPABILITIES)

    if domain:
        upper = domain.upper()
        caps = [c for c in caps if upper in [d.upper() for d in c["domain"]]]

    if safety_band:
        upper = safety_band.upper()
        caps = [c for c in caps if c["safety_band"].upper() == upper]

    if query:
        q = query.lower()
        caps = [
            c
            for c in caps
            if q in c["name"].lower()
            or q in c["description"].lower()
            or any(q in d.lower() for d in c["domain"])
        ]

    return {
        "capabilities": caps[:limit],
        "total_found": len(caps),
        "query_latency_ms": _DISCOVERY_LATENCY_MS,
    }


# ---------------------------------------------------------------------------
# READ-003: summarize_context() -- semi-real (uses actual SessionState snapshot)
# ---------------------------------------------------------------------------


def summarize_context(
    manager: Any,  # SessionStateManager -- typed as Any to avoid circular import
    focus_sections: list[str] | None = None,
) -> dict[str, Any]:
    """Produce an extractive text summary of the current HOT SessionState.

    Reads the real SessionState snapshot via ``manager.get_snapshot()`` and
    flattens key-value pairs from each section. No LLM call.

    Args:
        manager:        Live ``SessionStateManager`` instance.
        focus_sections: If provided, only these section names are summarised.
                        Defaults to all HOT sections.

    Returns:
        ``{"summary": str, "original_tokens": int, "summary_tokens": int,
           "compression_ratio": float, "latency_ms": int}``
    """
    t0 = time.monotonic()

    snapshot = manager.get_snapshot()
    lines: list[str] = []
    original_chars = 0

    for name in snapshot.sections:
        if focus_sections and name not in focus_sections:
            continue
        try:
            section = manager.get_section(name)
            raw_bytes = section.serialize()
            data_str = raw_bytes.decode("utf-8", errors="replace") if raw_bytes else ""
        except Exception:
            data_str = ""
        original_chars += len(data_str)
        if not data_str or len(data_str.strip()) < 4:
            continue
        # Extractive: first 200 chars of each non-empty section
        excerpt = data_str[:200].replace("\n", " ").strip()
        lines.append(f"[{name}] {excerpt}")

    summary = "\n".join(lines) if lines else "(session state is empty)"
    latency_ms = int((time.monotonic() - t0) * 1000)

    # Rough token estimates: 1 token ≈ 4 chars
    original_tokens = max(1, original_chars // 4)
    summary_tokens = max(1, len(summary) // 4)
    ratio = round(summary_tokens / original_tokens, 3)

    return {
        "summary": summary,
        "original_tokens": original_tokens,
        "summary_tokens": summary_tokens,
        "compression_ratio": ratio,
        "latency_ms": latency_ms,
    }


# ---------------------------------------------------------------------------
# READ-004: read_session_state() -- active read of real SessionState sections
# ---------------------------------------------------------------------------

# Which sections are LLM-readable and what extractor to use for each.
_HOT_READABLE = (
    "beliefs_active",
    "scoreboard",
    "clarifications",
    "affective_now",
    "narrative_active",
)


def _extract_beliefs(section: Any) -> dict[str, Any]:
    """Extract structured data from BeliefsActiveSection."""
    facts = []
    for f in section.list_facts():
        facts.append(
            {
                "fact_id": f.id,
                "subject": f.subject,
                "predicate": f.predicate,
                "object": f.object,
                "confidence": f.confidence,
                "source": getattr(f, "source", ""),
                "is_pinned": getattr(f, "is_pinned", False),
            }
        )
    entities = []
    for e in section.list_entities():
        entities.append(
            {
                "entity_id": getattr(e, "id", str(e)),
                "type": getattr(e, "entity_type", ""),
                "name": getattr(e, "name", str(e)),
            }
        )
    return {
        "fact_count": section.get_fact_count(),
        "entity_count": section.get_entity_count(),
        "pinned_fact_ids": list(section.get_pinned_fact_ids()),
        "facts": facts,
        "entities": entities,
        "mentioned_location": section.get_mentioned_location(),
        "mentioned_time": section.get_mentioned_time(),
    }


def _extract_scoreboard(section: Any) -> dict[str, Any]:
    """Extract structured data from ScoreboardSection."""
    referents = []
    for r in section.list_referents():
        referents.append(
            {
                "id": r.id,
                "text": r.text,
                "entity_id": r.entity_id,
                "entity_type": r.entity_type,
                "salience": r.salience,
            }
        )
    topics = []
    for t in section.list_topics():
        topics.append(
            {
                "id": t.id,
                "name": t.name,
                "salience": t.salience,
                "is_primary": t.is_primary,
            }
        )
    questions = []
    for q in section.list_open_questions():
        questions.append(
            {
                "id": q.id,
                "text": q.text,
                "status": str(q.status),
                "asked_by": getattr(q, "asked_by", ""),
            }
        )
    return {
        "referents": referents,
        "topics": topics,
        "open_questions": questions,
        "user_intent": section.get_user_intent(),
    }


def _extract_clarifications(section: Any) -> dict[str, Any]:
    """Extract structured data from ClarificationsSection."""
    pending = []
    for c in section.get_pending():
        pending.append(
            {
                "id": c.id,
                "agent_id": c.agent_id,
                "question": c.question,
                "priority": str(c.priority),
                "status": str(c.status),
                "related_entity": c.related_entity,
                "options": [{"id": o.id, "text": o.text} for o in (c.options or [])],
            }
        )
    resolved = []
    for c in section.list_recently_resolved():
        resolved.append(
            {
                "id": c.id,
                "question": c.question,
                "answer": c.answer,
            }
        )
    return {
        "pending": pending,
        "recently_resolved": resolved,
        "is_blocked": section.is_blocked,
        "pending_count": len(pending),
    }


def _extract_affective(section: Any) -> dict[str, Any]:
    """Extract structured data from AffectiveNowSection."""
    md = section.get_metadata()
    return {
        "current_emotion": md.get("current_emotion", ""),
        "intensity": md.get("intensity", 0.0),
        "valence": md.get("valence", 0.0),
        "arousal": md.get("arousal", 0.0),
        "dominance": md.get("dominance", 0.5),
        "trajectory": md.get("trajectory", "STABLE"),
        "confidence": md.get("confidence", 0.0),
        "source": md.get("source", ""),
        "empathy_needed": md.get("empathy_needed", False),
        "celebration_appropriate": md.get("celebration_appropriate", False),
    }


def _extract_narrative(section: Any) -> dict[str, Any]:
    """Extract structured data from NarrativeActiveSection."""
    threads = []
    for t in section.get_all_threads():
        threads.append(
            {
                "id": t.id,
                "title": t.title,
                "goal": t.goal,
                "state": str(t.state),
                "is_goal_met": t.is_goal_met,
                "started_turn": t.started_turn,
                "last_active_turn": t.last_active_turn,
                "related_entities": list(t.related_entities),
            }
        )
    md = section.get_metadata()
    return {
        "threads": threads,
        "current_thread_id": md.get("current_thread_id"),
        "arc_position": md.get("arc_position", "EXPOSITION"),
        "arc_progress": md.get("arc_progress", 0.0),
    }


_SECTION_EXTRACTORS: dict[str, Any] = {
    "beliefs_active": _extract_beliefs,
    "scoreboard": _extract_scoreboard,
    "clarifications": _extract_clarifications,
    "affective_now": _extract_affective,
    "narrative_active": _extract_narrative,
}

# Valid section names the LLM may request
READABLE_SECTIONS = frozenset(_SECTION_EXTRACTORS.keys())


def read_session_state(
    manager: Any,
    section: str | None = None,
) -> dict[str, Any]:
    """Read current SessionState content as structured LLM-readable data.

    When ``section`` is ``None``, returns a brief overview of all readable HOT
    sections (counts, flags, current emotion).  When a specific section name is
    provided, returns the full structured content of that section.

    This gives the LLM **active agency** over what context it pulls --
    complementing the passive snapshot injection in the system prompt.

    Args:
        manager: Live ``SessionStateManager`` instance.
        section: Optional section name.  Valid values:
                 ``beliefs_active``, ``scoreboard``, ``clarifications``,
                 ``affective_now``, ``narrative_active``.
                 Pass ``None`` for an overview of all.

    Returns:
        ``{"section": str|None, "data": dict, "latency_ms": int}``

    Raises:
        ValueError: If ``section`` is not a recognised readable section.
    """
    t0 = time.monotonic()

    if section is not None and section not in _SECTION_EXTRACTORS:
        raise ValueError(
            f"Unknown section '{section}'. " f"Valid: {', '.join(sorted(READABLE_SECTIONS))}"
        )

    if section is not None:
        sec_obj = manager.get_section(section)
        data = _SECTION_EXTRACTORS[section](sec_obj)
        latency_ms = int((time.monotonic() - t0) * 1000)
        return {"section": section, "data": data, "latency_ms": latency_ms}

    # Overview mode -- brief counts / flags from each readable section
    overview: dict[str, Any] = {}
    for name in _HOT_READABLE:
        try:
            sec_obj = manager.get_section(name)
            md = sec_obj.get_metadata()
            overview[name] = {
                "size_bytes": md.get("current_size_bytes", 0),
            }
            # Add section-specific headline counters
            if name == "beliefs_active":
                overview[name]["fact_count"] = md.get("fact_count", 0)
                overview[name]["entity_count"] = md.get("entity_count", 0)
            elif name == "scoreboard":
                overview[name]["referent_count"] = md.get("referent_count", 0)
                overview[name]["topic_count"] = md.get("topic_count", 0)
                overview[name]["qud_count"] = md.get("qud_count", 0)
            elif name == "clarifications":
                overview[name]["pending_count"] = md.get("pending_count", 0)
                overview[name]["is_blocked"] = md.get("is_blocked", False)
            elif name == "affective_now":
                overview[name]["current_emotion"] = md.get("current_emotion", "")
                overview[name]["intensity"] = md.get("intensity", 0.0)
            elif name == "narrative_active":
                overview[name]["thread_count"] = md.get("total_threads_session", 0)
                overview[name]["arc_position"] = md.get("arc_position", "EXPOSITION")
        except Exception:
            overview[name] = {"error": "unavailable"}

    latency_ms = int((time.monotonic() - t0) * 1000)
    return {"section": None, "data": overview, "latency_ms": latency_ms}


# ---------------------------------------------------------------------------
# Gemini-compatible JSON schemas
# ---------------------------------------------------------------------------

READ_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "recall_memory",
        "description": (
            "Recall family memory items (beliefs, events, preferences, facts) "
            "from long-term K0 memory store. Returns past allergy info, trip "
            "history, individual preferences, or factual reference data. "
            "May return empty if no family history exists yet -- in that case "
            "rely on beliefs_active from session state instead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Free-text search query",
                },
                "memory_type": {
                    "type": "string",
                    "enum": ["belief", "event", "preference", "fact"],
                    "description": "Filter by memory type. Omit for all types.",
                },
                "subject": {
                    "type": "string",
                    "description": "Filter by subject name (e.g. 'Mom', 'Jake')",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results to return (default 5)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "discover_capabilities",
        "description": (
            "DIRECT TOOL -- call this function directly (do NOT wrap it inside "
            "invoke_capability). Lists all available system capabilities that "
            "can then be executed via invoke_capability(). Use this to discover "
            "what services exist and get the correct capability_name to pass "
            "to invoke_capability()."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Free-text search against capability names and descriptions",
                },
                "domain": {
                    "type": "string",
                    "description": "Filter by domain: TRAVEL, FOOD, FAMILY, PLANNING, etc.",
                },
                "safety_band": {
                    "type": "string",
                    "enum": ["GREEN", "AMBER", "RED"],
                    "description": "Filter by required minimum safety band",
                },
            },
            "required": [],
        },
    },
    {
        "name": "summarize_context",
        "description": (
            "Generate a concise extractive summary of the current session state. "
            "Use when the context is getting long and you need a compressed view "
            "of what has been established so far."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "focus_sections": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional list of section names to include. "
                        "Defaults to all non-empty HOT sections."
                    ),
                },
            },
            "required": [],
        },
    },
    {
        "name": "read_session_state",
        "description": (
            "Read current session state content as structured data. "
            "Call with no section to get a brief overview of all HOT sections "
            "(counts and flags). Call with a specific section name to get the "
            "full structured content of that section. Use this to actively pull "
            "beliefs, scoreboard, clarifications, affective state, or narrative "
            "threads on demand instead of relying solely on the system prompt."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "enum": [
                        "beliefs_active",
                        "scoreboard",
                        "clarifications",
                        "affective_now",
                        "narrative_active",
                    ],
                    "description": (
                        "Section to read. Omit for an overview of all readable sections."
                    ),
                },
            },
            "required": [],
        },
    },
]
