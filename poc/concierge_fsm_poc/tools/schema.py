"""Schema Tool -- Epic 2.5 (SCH-001).

Returns hardcoded capability schemas for the demo scenario.  The LLM calls
``get_capability_schema`` to discover what inputs a capability requires,
compares against what is already known in SessionState, and records gaps
via ``update_clarifications`` when required params are missing.

The Gemini-compatible JSON schema is in ``SCHEMA_SCHEMAS`` (list[dict]).
"""

from __future__ import annotations

import time
from typing import Any

# ---------------------------------------------------------------------------
# 9 demo capability schemas  (5 core + 4 story-specific)
# ---------------------------------------------------------------------------

CAPABILITY_SCHEMAS: dict[str, dict[str, Any]] = {
    # --- 5 core demo capabilities (match DEMO_CAPABILITIES in read_mock.py) ---
    "tool.execute.weather_lookup": {
        "name": "tool.execute.weather_lookup",
        "required_inputs": ["location", "date_range"],
        "optional_inputs": ["units"],
        "output_schema": {
            "temperature": "str",
            "conditions": "str",
            "snow": "str",
        },
        "safety_band_min": "GREEN",
        "avg_latency_ms": 200,
    },
    "tool.execute.hotel_booking": {
        "name": "tool.execute.hotel_booking",
        "required_inputs": ["location", "check_in", "check_out", "guests"],
        "optional_inputs": ["budget_max", "star_rating", "amenities"],
        "output_schema": {
            "hotel": "str",
            "rate": "str",
            "available": "bool",
        },
        "safety_band_min": "AMBER",
        "avg_latency_ms": 1500,
    },
    "tool.execute.activity_search": {
        "name": "tool.execute.activity_search",
        "required_inputs": ["location", "domain"],
        "optional_inputs": ["age_group", "max_results"],
        "output_schema": {
            "activities": "list[object]",
        },
        "safety_band_min": "GREEN",
        "avg_latency_ms": 800,
    },
    "tool.execute.restaurant_search": {
        "name": "tool.execute.restaurant_search",
        "required_inputs": ["location", "cuisine_type", "party_size", "time"],
        "optional_inputs": ["kid_friendly", "budget", "dietary_restrictions"],
        "output_schema": {
            "restaurants": "list[object]",
        },
        "safety_band_min": "GREEN",
        "avg_latency_ms": 900,
    },
    "workflow.trip_planning": {
        "name": "workflow.trip_planning",
        "required_inputs": ["destination", "dates", "family_size"],
        "optional_inputs": ["budget", "preferences"],
        "output_schema": {
            "hotel": "object",
            "activities": "list[object]",
            "total_cost_estimate": "str",
        },
        "safety_band_min": "AMBER",
        "avg_latency_ms": 3000,
    },
    # --- 4 additional story capabilities (used in specific turns) ---
    "tool.execute.rental_lookup": {
        "name": "tool.execute.rental_lookup",
        "required_inputs": ["location", "item_type"],
        "optional_inputs": ["duration", "quantity"],
        "output_schema": {
            "rentals": "list[object]",
        },
        "safety_band_min": "GREEN",
        "avg_latency_ms": 600,
    },
    "tool.execute.flight_search": {
        "name": "tool.execute.flight_search",
        "required_inputs": ["origin", "destination", "date", "passengers"],
        "optional_inputs": ["class", "budget"],
        "output_schema": {
            "flights": "list[object]",
        },
        "safety_band_min": "GREEN",
        "avg_latency_ms": 1200,
    },
    "tool.execute.route_planner": {
        "name": "tool.execute.route_planner",
        "required_inputs": ["origin", "destination", "stops"],
        "optional_inputs": ["avoid_highways", "traffic_model"],
        "output_schema": {
            "route": "object",
            "estimated_duration": "str",
        },
        "safety_band_min": "GREEN",
        "avg_latency_ms": 1000,
    },
    "tool.execute.boat_tour": {
        "name": "tool.execute.boat_tour",
        "required_inputs": ["location", "date", "group_size"],
        "optional_inputs": ["tour_type", "budget"],
        "output_schema": {
            "tours": "list[object]",
        },
        "safety_band_min": "GREEN",
        "avg_latency_ms": 700,
    },
}


def get_capability_schema(capability_name: str) -> dict[str, Any]:
    """SCH-001: Return the full schema for a named capability.

    Parameters
    ----------
    capability_name:
        Fully qualified capability name (e.g. ``tool.execute.weather_lookup``).

    Returns
    -------
    dict with the capability schema including ``required_inputs``,
    ``optional_inputs``, ``output_schema``, ``safety_band_min``,
    ``avg_latency_ms``, and ``found=True``.

    If the capability is unknown, returns ``found=False`` with an error
    message and the list of available capability names.
    """
    t0 = time.monotonic_ns()
    schema = CAPABILITY_SCHEMAS.get(capability_name)
    elapsed = max(1, (time.monotonic_ns() - t0) // 1_000_000)

    if schema is None:
        return {
            "found": False,
            "error": "not_found",
            "capability_name": capability_name,
            "available_capabilities": sorted(CAPABILITY_SCHEMAS.keys()),
            "query_latency_ms": elapsed,
        }

    return {
        "found": True,
        **schema,
        "query_latency_ms": elapsed,
    }


# ---------------------------------------------------------------------------
# Gemini-compatible JSON schema  (SCHEMA_SCHEMAS)
# ---------------------------------------------------------------------------

SCHEMA_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "get_capability_schema",
        "description": (
            "Look up the input/output schema for a capability before invoking it. "
            "Use this to discover required_inputs and detect information gaps "
            "that may need clarification from the user."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "capability_name": {
                    "type": "string",
                    "description": (
                        "Fully qualified capability name "
                        "(e.g. tool.execute.weather_lookup, workflow.trip_planning)."
                    ),
                },
            },
            "required": ["capability_name"],
        },
    },
]
