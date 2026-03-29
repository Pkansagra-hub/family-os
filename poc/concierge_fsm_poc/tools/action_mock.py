"""Action Tool Mocks -- Epic 2.4 (ACT-001 through ACT-003).

All three action tools return canned deterministic data for the PoC demo.
In production these would dispatch to real fabric / orchestrator endpoints.

Tools:
    ACT-001  invoke_capability()   -- Execute a single capability (canned results)
    ACT-002  spawn_via_fabric()    -- Register an agent via fabric (always succeeds)
    ACT-003  execute_workflow()    -- Run a multi-step workflow (canned trip plan)

Gemini-compatible JSON schemas are in ACTION_SCHEMAS (list[dict]).
"""

from __future__ import annotations

import time
import uuid
from typing import Any

# ---------------------------------------------------------------------------
# ACT-001 canned capability results
# ---------------------------------------------------------------------------

_CAPABILITY_RESULTS: dict[str, dict[str, Any]] = {
    "tool.execute.weather_lookup": {
        "temperature": "45F",
        "conditions": "Partly cloudy",
        "snow": "4 inches base",
        "forecast": "Clear skies expected through the weekend with highs around 48F",
    },
    "tool.execute.hotel_booking": {
        "hotel": "Hyatt Regency Lake Tahoe",
        "rate": "$289/night",
        "available": True,
        "checkout_time": "11:00 AM",
        "pool": "Yes, heated outdoor pool and hot tub",
        "amenities": ["heated pool", "hot tub", "ski shuttle", "kids club"],
    },
    "tool.execute.activity_search": {
        "activities": [
            {
                "name": "Heavenly Ski Resort",
                "kid_friendly": True,
                "hours": "8:30 AM - 4:00 PM",
                "gondola_hours": "9:00 AM - 4:00 PM",
                "type": "outdoor",
                "description": "Premier ski resort with gondola, ski lessons, and Kids Zone",
            },
            {
                "name": "Lake Tahoe Snowshoe Tour",
                "kid_friendly": True,
                "hours": "9:00 AM - 12:00 PM",
                "type": "outdoor",
                "description": "Guided family-friendly snowshoe adventure through scenic trails",
            },
            {
                "name": "Tahoe Family Game Night",
                "kid_friendly": True,
                "hours": "6:00 PM - 9:00 PM",
                "type": "evening",
                "description": "Board games, hot chocolate, and s'mores by the fire",
            },
            {
                "name": "Stargazing at Sand Harbor",
                "kid_friendly": True,
                "hours": "7:00 PM - 9:30 PM",
                "type": "evening",
                "description": "Guided astronomy session with telescopes at Sand Harbor",
            },
        ],
    },
    "tool.execute.restaurant_search": {
        "restaurants": [
            {
                "name": "Gar Woods Grill",
                "kid_friendly": True,
                "cuisine": "American",
                "vegetarian_options": False,
                "price_range": "$$",
            },
            {
                "name": "Sunnyside Restaurant",
                "cuisine": "Lakeside seafood",
                "kid_friendly": True,
                "vegetarian_options": False,
                "price_range": "$$",
            },
            {
                "name": "Sprouts Cafe",
                "cuisine": "Vegetarian & Vegan",
                "kid_friendly": True,
                "vegetarian_options": True,
                "price_range": "$",
                "description": "Farm-to-table vegetarian cafe with family seating",
            },
            {
                "name": "Fire Sign Cafe",
                "cuisine": "Organic American",
                "kid_friendly": True,
                "vegetarian_options": True,
                "price_range": "$",
                "description": "Organic cafe with extensive vegetarian menu",
            },
        ],
    },
    # ---- NEW CAPABILITIES ----
    "tool.execute.flight_search": {
        "flights": [
            {
                "airline": "United Airlines",
                "flight": "UA 1234",
                "departure": "8:00 AM",
                "arrival": "11:30 AM",
                "price": "$349/person",
                "stops": 0,
            },
            {
                "airline": "Southwest",
                "flight": "WN 567",
                "departure": "10:15 AM",
                "arrival": "2:00 PM",
                "price": "$279/person",
                "stops": 1,
            },
            {
                "airline": "Delta",
                "flight": "DL 890",
                "departure": "6:30 AM",
                "arrival": "9:45 AM",
                "price": "$399/person",
                "stops": 0,
            },
        ],
    },
    "tool.execute.car_rental": {
        "cars": [
            {"company": "Hertz", "type": "Compact", "rate": "$45/day", "available": True},
            {"company": "Enterprise", "type": "SUV", "rate": "$72/day", "available": True},
            {"company": "Budget", "type": "Midsize", "rate": "$38/day", "available": True},
        ],
    },
    "tool.execute.airport_transfer": {
        "options": [
            {"type": "Shuttle", "provider": "SuperShuttle", "price": "$25/person", "eta": "20 min"},
            {"type": "Rideshare", "provider": "Uber", "price": "$35-45", "eta": "8 min"},
            {"type": "Taxi", "provider": "Local Taxi Co", "price": "$50 flat", "eta": "15 min"},
        ],
    },
    "tool.execute.travel_insurance": {
        "quotes": [
            {
                "provider": "Allianz",
                "plan": "Basic",
                "price": "$89/person",
                "coverage": "medical + cancellation",
            },
            {
                "provider": "World Nomads",
                "plan": "Standard",
                "price": "$120/person",
                "coverage": "medical + cancellation + adventure sports",
            },
        ],
    },
    "tool.execute.grocery_list": {
        "list": ["milk", "eggs", "bread", "chicken breast", "broccoli", "rice", "olive oil"],
        "estimated_cost": "$45-55",
        "store_suggestion": "Whole Foods Market",
    },
    "tool.execute.meal_planning": {
        "weekly_plan": {
            "Monday": {"dinner": "Grilled chicken with roasted vegetables"},
            "Tuesday": {"dinner": "Pasta primavera"},
            "Wednesday": {"dinner": "Fish tacos with slaw"},
            "Thursday": {"dinner": "Stir-fry with tofu and rice"},
            "Friday": {"dinner": "Homemade pizza night"},
            "Saturday": {"dinner": "BBQ burgers and corn"},
            "Sunday": {"dinner": "Slow cooker pot roast"},
        },
        "dietary_notes": "Nut-free, balanced macros",
    },
    "tool.execute.recipe_search": {
        "recipes": [
            {
                "name": "One-Pot Chicken Alfredo",
                "time": "30 min",
                "difficulty": "Easy",
                "servings": 4,
            },
            {"name": "Sheet Pan Salmon", "time": "25 min", "difficulty": "Easy", "servings": 4},
            {"name": "Veggie Stir Fry", "time": "20 min", "difficulty": "Easy", "servings": 4},
        ],
    },
    "tool.execute.food_delivery": {
        "order_id": "FD-20260218-001",
        "status": "confirmed",
        "estimated_delivery": "35-45 minutes",
        "total": "$42.50",
    },
    "tool.execute.doctor_appointment": {
        "doctors": [
            {
                "name": "Dr. Sarah Chen",
                "specialty": "Family Medicine",
                "next_available": "Feb 20, 2:30 PM",
                "rating": 4.8,
            },
            {
                "name": "Dr. James Park",
                "specialty": "Family Medicine",
                "next_available": "Feb 21, 10:00 AM",
                "rating": 4.6,
            },
        ],
    },
    "tool.execute.pharmacy_search": {
        "pharmacies": [
            {
                "name": "CVS Pharmacy",
                "distance": "0.8 miles",
                "hours": "8 AM - 10 PM",
                "drive_thru": True,
            },
            {
                "name": "Walgreens",
                "distance": "1.2 miles",
                "hours": "7 AM - 11 PM",
                "drive_thru": True,
            },
        ],
    },
    "tool.execute.fitness_tracker": {
        "suggestion": "30-minute moderate jog",
        "calories_burned_estimate": 350,
        "weekly_progress": "3 of 5 workouts completed",
    },
    "tool.execute.medication_reminder": {
        "reminder_id": "MR-001",
        "status": "scheduled",
        "message": "Reminder set successfully",
    },
    "tool.execute.budget_tracker": {
        "month": "February 2026",
        "total_spent": "$2,340",
        "budget_remaining": "$1,660",
        "top_categories": {"Groceries": "$620", "Dining": "$280", "Transportation": "$190"},
    },
    "tool.execute.bill_reminder": {
        "reminder_id": "BR-001",
        "status": "scheduled",
        "message": "Bill reminder set",
    },
    "tool.execute.homework_help": {
        "subject": "Math",
        "explanation": "Step-by-step solution provided",
        "answer_summary": "The derivative of x^2 is 2x (power rule)",
        "resources": ["Khan Academy - Derivatives", "Math is Fun - Calculus"],
    },
    "tool.execute.tutor_search": {
        "tutors": [
            {
                "name": "Alex Rivera",
                "subject": "Mathematics",
                "rate": "$40/hr",
                "rating": 4.9,
                "available": "weekday evenings",
            },
            {
                "name": "Maria Lopez",
                "subject": "Mathematics",
                "rate": "$35/hr",
                "rating": 4.7,
                "available": "weekends",
            },
        ],
    },
    "tool.execute.school_calendar": {
        "upcoming_events": [
            {"event": "Spring Break", "date": "March 15-22, 2026"},
            {"event": "Parent-Teacher Conference", "date": "March 5, 2026"},
            {"event": "Science Fair", "date": "April 2, 2026"},
        ],
    },
    "tool.execute.home_maintenance": {
        "professionals": [
            {
                "name": "QuickFix Plumbing",
                "service": "Plumbing",
                "rating": 4.7,
                "available": "next day",
                "estimate": "$85-150",
            },
            {
                "name": "Bright Spark Electric",
                "service": "Electrical",
                "rating": 4.8,
                "available": "same day",
                "estimate": "$100-200",
            },
        ],
    },
    "tool.execute.smart_home_control": {
        "device": "thermostat",
        "action": "set_temperature",
        "status": "success",
        "current_state": "72F, heating mode",
    },
    "tool.execute.chore_scheduler": {
        "schedule": {
            "Monday": "Vacuuming (shared)",
            "Wednesday": "Laundry",
            "Friday": "Kitchen deep clean",
            "Saturday": "Yard work",
        },
        "status": "created",
    },
    "tool.execute.movie_search": {
        "movies": [
            {
                "title": "The Great Adventure",
                "rating": "PG",
                "genre": "Adventure/Comedy",
                "showtime": "7:00 PM",
                "theater": "AMC 16",
            },
            {
                "title": "Ocean Dreams",
                "rating": "G",
                "genre": "Animation",
                "showtime": "4:30 PM",
                "theater": "Regal Cinema",
            },
        ],
    },
    "tool.execute.event_tickets": {
        "events": [
            {
                "name": "Jazz in the Park",
                "date": "Feb 22, 2026",
                "price": "$25-45",
                "venue": "City Park Amphitheater",
            },
            {
                "name": "Family Fun Run 5K",
                "date": "March 1, 2026",
                "price": "$15/person",
                "venue": "Riverside Trail",
            },
        ],
    },
    "tool.execute.game_night_planner": {
        "suggestions": [
            {"game": "Ticket to Ride", "players": "2-5", "age": "8+", "duration": "60 min"},
            {"game": "Codenames", "players": "4-8", "age": "10+", "duration": "30 min"},
            {"game": "Uno", "players": "2-10", "age": "7+", "duration": "20 min"},
        ],
    },
    "tool.execute.gift_suggestions": {
        "ideas": [
            {"item": "Personalized Star Map", "price": "$45", "category": "sentimental"},
            {"item": "Cooking Class for Two", "price": "$120", "category": "experience"},
            {"item": "Wireless Earbuds", "price": "$79", "category": "practical"},
        ],
    },
    "tool.execute.party_planner": {
        "plan": {
            "venue_suggestions": ["Home backyard", "Community center", "Local park pavilion"],
            "catering_estimate": "$15-25/person",
            "activities": ["Photo booth", "Music playlist", "Lawn games"],
            "checklist_items": 12,
        },
    },
    "tool.execute.ride_booking": {
        "ride_id": "RIDE-001",
        "provider": "Uber",
        "estimated_arrival": "8 minutes",
        "estimated_fare": "$18-24",
        "status": "driver_assigned",
    },
    "tool.execute.transit_info": {
        "routes": [
            {"line": "Bus 42", "departure": "3:15 PM", "arrival": "3:45 PM", "fare": "$2.50"},
            {"line": "Metro Blue", "departure": "3:20 PM", "arrival": "3:35 PM", "fare": "$3.00"},
        ],
    },
    "tool.execute.product_search": {
        "products": [
            {"name": "Kindle Paperwhite", "price": "$139", "store": "Amazon", "rating": 4.7},
            {"name": "Kindle Paperwhite", "price": "$149", "store": "Best Buy", "rating": 4.7},
        ],
    },
    "tool.execute.calendar_manage": {
        "status": "event_created",
        "event_id": "CAL-001",
        "message": "Calendar event created successfully",
    },
    "tool.execute.vet_appointment": {
        "vets": [
            {
                "name": "Happy Paws Veterinary",
                "next_available": "Feb 20, 3:00 PM",
                "rating": 4.9,
                "distance": "1.5 miles",
            },
        ],
    },
    "tool.execute.pet_care": {
        "advice": "For a medium-sized dog, feed twice daily (morning and evening), ensure fresh water always available.",
        "tips": [
            "Regular brushing 2-3 times per week",
            "Monthly nail trimming",
            "Annual dental checkup",
        ],
    },
}

# Provider IDs per capability (stable for test assertions)
_PROVIDER_IDS: dict[str, str] = {
    "tool.execute.weather_lookup": "provider-weather-001",
    "tool.execute.hotel_booking": "provider-hotel-001",
    "tool.execute.activity_search": "provider-activity-001",
    "tool.execute.restaurant_search": "provider-restaurant-001",
    "tool.execute.flight_search": "provider-flight-001",
    "tool.execute.car_rental": "provider-car-001",
    "tool.execute.airport_transfer": "provider-transfer-001",
    "tool.execute.travel_insurance": "provider-insurance-001",
    "tool.execute.grocery_list": "provider-grocery-001",
    "tool.execute.meal_planning": "provider-meal-001",
    "tool.execute.recipe_search": "provider-recipe-001",
    "tool.execute.food_delivery": "provider-delivery-001",
    "tool.execute.doctor_appointment": "provider-doctor-001",
    "tool.execute.pharmacy_search": "provider-pharmacy-001",
    "tool.execute.fitness_tracker": "provider-fitness-001",
    "tool.execute.medication_reminder": "provider-medication-001",
    "tool.execute.budget_tracker": "provider-budget-001",
    "tool.execute.bill_reminder": "provider-bill-001",
    "tool.execute.homework_help": "provider-homework-001",
    "tool.execute.tutor_search": "provider-tutor-001",
    "tool.execute.school_calendar": "provider-school-001",
    "tool.execute.home_maintenance": "provider-home-001",
    "tool.execute.smart_home_control": "provider-smarthome-001",
    "tool.execute.chore_scheduler": "provider-chore-001",
    "tool.execute.movie_search": "provider-movie-001",
    "tool.execute.event_tickets": "provider-tickets-001",
    "tool.execute.game_night_planner": "provider-games-001",
    "tool.execute.gift_suggestions": "provider-gifts-001",
    "tool.execute.party_planner": "provider-party-001",
    "tool.execute.ride_booking": "provider-ride-001",
    "tool.execute.transit_info": "provider-transit-001",
    "tool.execute.product_search": "provider-product-001",
    "tool.execute.calendar_manage": "provider-calendar-001",
    "tool.execute.vet_appointment": "provider-vet-001",
    "tool.execute.pet_care": "provider-petcare-001",
}


class CircuitBreakerOpenError(Exception):
    """Raised when invoke_capability is called with force_cb_open=True (F24)."""

    def __init__(self, capability_name: str) -> None:
        self.capability_name = capability_name
        super().__init__(
            f"Circuit breaker OPEN for {capability_name}. All capabilities unavailable."
        )


def _filter_results(
    capability_name: str,
    data: dict[str, Any],
    inputs: dict[str, Any],
) -> dict[str, Any]:
    """Apply keyword-based constraint filtering to mock results.

    For restaurant_search: filters by vegetarian, cuisine, delivery/pizza.
    For activity_search: filters by time-of-day (evening vs daytime).
    Returns a copy with filtered lists; never mutates the original.
    """
    import copy

    data = copy.deepcopy(data)

    # Collect all input values into a single lowercase search string
    input_text = " ".join(str(v) for v in inputs.values()).lower()

    if capability_name == "tool.execute.restaurant_search" and "restaurants" in data:
        restaurants = data["restaurants"]

        # Vegetarian constraint
        if "vegetarian" in input_text or "vegan" in input_text:
            filtered = [r for r in restaurants if r.get("vegetarian_options")]
            if filtered:
                data["restaurants"] = filtered
                data["filter_applied"] = "vegetarian"

        # Pizza / delivery
        if "pizza" in input_text or "delivery" in input_text:
            data["restaurants"] = [
                {
                    "name": "Mountain Pizza Co.",
                    "cuisine": "Pizza",
                    "kid_friendly": True,
                    "delivery": True,
                    "price_range": "$",
                    "description": "Family pizza delivery, 30-min delivery to all Lake Tahoe hotels",
                }
            ]
            data["filter_applied"] = "pizza_delivery"

    elif capability_name == "tool.execute.activity_search" and "activities" in data:
        activities = data["activities"]

        # Evening filter
        if "evening" in input_text or "night" in input_text or "tonight" in input_text:
            filtered = [a for a in activities if a.get("type") == "evening"]
            if filtered:
                data["activities"] = filtered
                data["filter_applied"] = "evening"

        # Daytime filter (explicit)
        if "morning" in input_text or "daytime" in input_text:
            filtered = [a for a in activities if a.get("type") != "evening"]
            if filtered:
                data["activities"] = filtered
                data["filter_applied"] = "daytime"

    return data


def invoke_capability(
    capability_name: str,
    *,
    force_cb_open: bool = False,
    **inputs: Any,
) -> dict[str, Any]:
    """ACT-001: Execute a single capability and return canned results.

    Parameters
    ----------
    capability_name:
        Fully qualified capability name (e.g. ``tool.execute.weather_lookup``).
    force_cb_open:
        If ``True``, raises ``CircuitBreakerOpenError`` for *any* capability
        (used by F24 full-fallback test).
    **inputs:
        Keyword args passed to the capability. Used for constraint
        filtering (e.g. ``cuisine="vegetarian"``).

    Returns
    -------
    dict with ``success``, ``data``, ``provider_id``, ``duration_ms``,
    ``capability_name``.
    """
    t0 = time.monotonic_ns()

    if force_cb_open:
        raise CircuitBreakerOpenError(capability_name)

    data = _CAPABILITY_RESULTS.get(capability_name)
    if data is None:
        elapsed = max(1, (time.monotonic_ns() - t0) // 1_000_000)
        return {
            "success": False,
            "data": {"error": "Capability not found"},
            "provider_id": None,
            "duration_ms": elapsed,
            "capability_name": capability_name,
        }

    # Apply constraint filtering based on inputs
    data = _filter_results(capability_name, data, inputs)

    elapsed = max(1, (time.monotonic_ns() - t0) // 1_000_000)
    return {
        "success": True,
        "data": data,
        "provider_id": _PROVIDER_IDS.get(capability_name, "provider-unknown"),
        "duration_ms": elapsed,
        "capability_name": capability_name,
    }


# ---------------------------------------------------------------------------
# ACT-002 spawn_via_fabric
# ---------------------------------------------------------------------------


def spawn_via_fabric(
    agent_name: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """ACT-002: Register an agent via fabric (always succeeds in mock).

    Parameters
    ----------
    agent_name:
        Name of the agent to register.
    **kwargs:
        Additional configuration (ignored in mock).

    Returns
    -------
    dict with ``success``, ``agent_name``, ``status``, ``agent_id``.
    """
    return {
        "success": True,
        "agent_name": agent_name,
        "status": "registered",
        "agent_id": f"agent-{uuid.uuid4().hex[:8]}",
    }


# ---------------------------------------------------------------------------
# ACT-003 execute_workflow
# ---------------------------------------------------------------------------

_WORKFLOW_RESULTS: dict[str, dict[str, Any]] = {
    "workflow.trip_planning": {
        "success": True,
        "envelope_id": "env-trip-001",
        "status": "completed",
        "results": {
            "hotel": {
                "name": "Hyatt Regency Lake Tahoe",
                "rate": "$289/night",
                "confirmed": True,
            },
            "activities": [
                {
                    "name": "Heavenly Ski Resort - Kids Zone",
                    "time": "Saturday 10am-2pm",
                },
                {
                    "name": "Lake Tahoe Snowshoe Tour",
                    "time": "Sunday 9am-12pm",
                },
            ],
            "total_cost_estimate": "$850",
        },
    },
}


def execute_workflow(
    workflow_name: str,
    **inputs: Any,
) -> dict[str, Any]:
    """ACT-003: Execute a multi-step workflow and return canned results.

    Parameters
    ----------
    workflow_name:
        Fully qualified workflow name (e.g. ``workflow.trip_planning``).
    **inputs:
        Arbitrary keyword args passed to the workflow (ignored in mock).

    Returns
    -------
    dict with ``success``, ``envelope_id``, ``status``, ``results``,
    ``workflow_name``, ``duration_ms``.
    """
    t0 = time.monotonic_ns()

    result = _WORKFLOW_RESULTS.get(workflow_name)
    elapsed = max(1, (time.monotonic_ns() - t0) // 1_000_000)

    if result is None:
        return {
            "success": False,
            "envelope_id": None,
            "status": "rejected",
            "results": None,
            "workflow_name": workflow_name,
            "duration_ms": elapsed,
        }

    return {
        **result,
        "workflow_name": workflow_name,
        "duration_ms": elapsed,
    }


# ---------------------------------------------------------------------------
# Gemini-compatible JSON schemas  (ACTION_SCHEMAS)
# ---------------------------------------------------------------------------

ACTION_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "invoke_capability",
        "description": (
            "Execute a single capability by name and return its result. "
            "Use after discover_capabilities to call a specific service."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "capability_name": {
                    "type": "string",
                    "description": "Fully qualified capability name (e.g. tool.execute.weather_lookup).",
                },
                "inputs": {
                    "type": "object",
                    "description": "Key-value inputs required by the capability.",
                },
            },
            "required": ["capability_name"],
        },
    },
    {
        "name": "spawn_via_fabric",
        "description": (
            "Register a new agent via the fabric runtime. " "Returns registration status."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "agent_name": {
                    "type": "string",
                    "description": "Name of the agent to register.",
                },
                "config": {
                    "type": "object",
                    "description": "Optional agent configuration.",
                },
            },
            "required": ["agent_name"],
        },
    },
    {
        "name": "execute_workflow",
        "description": (
            "Execute a multi-step workflow (e.g. trip planning) and return "
            "aggregated results. For complex operations spanning multiple capabilities."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "workflow_name": {
                    "type": "string",
                    "description": "Fully qualified workflow name (e.g. workflow.trip_planning).",
                },
                "inputs": {
                    "type": "object",
                    "description": "Key-value inputs required by the workflow.",
                },
            },
            "required": ["workflow_name"],
        },
    },
]
