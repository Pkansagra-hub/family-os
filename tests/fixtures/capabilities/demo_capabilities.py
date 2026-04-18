"""
tests.fixtures.capabilities.demo_capabilities -- 7 Demo Capability Definitions + Handlers.

V2 Design Ref: Section 14 item 3, Section 15.4 (demo capabilities)

Epic 7.5.3 + 7.5.5: Pre-register demo capabilities with mock handlers.

7 capabilities across 3 domains:
  Travel (4):       hotel_search, hotel_booking, restaurant_search, restaurant_booking
  Productivity (2): weather_forecast, calendar_create
  Shopping (1):     product_search

Each mock handler returns deterministic data that matches the capability's
return schema. Mock data is realistic enough for demo scenarios but does
NOT call external APIs.

Key behaviors:
  - Capabilities with side_effects=False return artifact_type=None
  - Capabilities with side_effects=True return artifact_type (booking, appointment, etc.)
  - hotel_booking returns artifact_type="booking"
  - restaurant_booking returns artifact_type="booking"
  - calendar_create returns artifact_type="appointment"
"""

from __future__ import annotations

import hashlib
from typing import Any

# =========================================================================
# Capability definitions (7 total, 3 domains)
# =========================================================================

DEMO_CAPABILITIES: list[dict[str, Any]] = [
    # --- Travel domain (4) ---
    {
        "name": "tool.execute.hotel_search",
        "description": "Search for hotels by location, dates, and preferences",
        "required_inputs": ["location"],
        "optional_inputs": [
            "check_in",
            "check_out",
            "guests",
            "max_price",
            "amenities",
        ],
        "has_side_effects": False,
        "estimated_cost": "free",
        "domain": "travel",
    },
    {
        "name": "tool.execute.hotel_booking",
        "description": "Book a hotel room. Requires prior search to identify the hotel.",
        "required_inputs": ["hotel_id", "check_in", "nights"],
        "optional_inputs": [
            "guests",
            "payment_method",
            "special_requests",
        ],
        "has_side_effects": True,
        "estimated_cost": "varies",
        "domain": "travel",
    },
    {
        "name": "tool.execute.restaurant_search",
        "description": "Search for restaurants by location, cuisine, and preferences",
        "required_inputs": ["location"],
        "optional_inputs": [
            "cuisine",
            "price_range",
            "dietary",
            "outdoor_seating",
        ],
        "has_side_effects": False,
        "estimated_cost": "free",
        "domain": "travel",
    },
    {
        "name": "tool.execute.restaurant_booking",
        "description": "Make a restaurant reservation",
        "required_inputs": ["restaurant_id", "date", "time", "party_size"],
        "optional_inputs": ["special_requests"],
        "has_side_effects": True,
        "estimated_cost": "free",
        "domain": "travel",
    },
    # --- Productivity domain (2) ---
    {
        "name": "tool.execute.weather_forecast",
        "description": "Get weather forecast for a location and date range",
        "required_inputs": ["location"],
        "optional_inputs": ["date", "days"],
        "has_side_effects": False,
        "estimated_cost": "free",
        "domain": "productivity",
    },
    {
        "name": "tool.execute.calendar_create",
        "description": "Create a calendar event or appointment",
        "required_inputs": ["title", "date", "time"],
        "optional_inputs": [
            "duration",
            "location",
            "recurrence",
            "attendees",
        ],
        "has_side_effects": True,
        "estimated_cost": "free",
        "domain": "productivity",
    },
    # --- Shopping domain (1) ---
    {
        "name": "tool.execute.product_search",
        "description": "Search for products by query, category, and filters",
        "required_inputs": ["query"],
        "optional_inputs": [
            "category",
            "max_price",
            "sort",
            "brand",
        ],
        "has_side_effects": False,
        "estimated_cost": "free",
        "domain": "shopping",
    },
]


# =========================================================================
# Deterministic ID generation (no randomness for testability)
# =========================================================================


def _deterministic_id(prefix: str, seed: str) -> str:
    """Generate a deterministic ID from a seed string."""
    h = hashlib.md5(seed.encode(), usedforsecurity=False).hexdigest()[:8]
    return f"{prefix}-{h}"


# =========================================================================
# Mock handlers -- one per capability
# =========================================================================


async def mock_hotel_search(params: dict[str, Any]) -> dict[str, Any]:
    """Mock hotel search returning 3 results."""
    location = params.get("location", "unknown")
    max_price = params.get("max_price")

    results = [
        {
            "name": "Vineyard Inn",
            "location": location,
            "price": 185,
            "rating": 4.5,
            "amenities": ["pool", "spa", "restaurant"],
        },
        {
            "name": "Marriott",
            "location": location,
            "price": 298,
            "rating": 4.2,
            "amenities": ["gym", "business_center", "restaurant"],
        },
        {
            "name": "Holiday Inn",
            "location": location,
            "price": 129,
            "rating": 3.8,
            "amenities": ["wifi", "parking"],
        },
    ]

    if max_price:
        results = [r for r in results if r["price"] <= max_price]

    return {
        "success": True,
        "data": results,
        "artifact_type": None,
        "duration_ms": 150,
    }


async def mock_hotel_booking(params: dict[str, Any]) -> dict[str, Any]:
    """Mock hotel booking returning confirmation."""
    hotel_id = params.get("hotel_id", "unknown")
    nights = params.get("nights", 1)
    confirmation = _deterministic_id("ACM", f"{hotel_id}-{nights}")

    return {
        "success": True,
        "data": {
            "confirmation": confirmation,
            "property": hotel_id,
            "check_in": params.get("check_in", "2025-06-15"),
            "nights": nights,
            "total": nights * 185,
        },
        "artifact_type": "booking",
        "duration_ms": 350,
    }


async def mock_restaurant_search(params: dict[str, Any]) -> dict[str, Any]:
    """Mock restaurant search returning 3 results."""
    location = params.get("location", "unknown")
    cuisine = params.get("cuisine")

    results = [
        {
            "name": "Oenotri",
            "location": location,
            "cuisine": "Italian",
            "price_range": "$$$",
            "rating": 4.6,
            "outdoor_seating": True,
        },
        {
            "name": "The Girl & The Fig",
            "location": location,
            "cuisine": "French",
            "price_range": "$$$",
            "rating": 4.4,
            "outdoor_seating": True,
        },
        {
            "name": "Gott's Roadside",
            "location": location,
            "cuisine": "American",
            "price_range": "$$",
            "rating": 4.3,
            "outdoor_seating": True,
        },
    ]

    if cuisine:
        cuisine_lower = cuisine.lower()
        results = [r for r in results if r["cuisine"].lower() == cuisine_lower]

    return {
        "success": True,
        "data": results,
        "artifact_type": None,
        "duration_ms": 120,
    }


async def mock_restaurant_booking(params: dict[str, Any]) -> dict[str, Any]:
    """Mock restaurant reservation."""
    restaurant_id = params.get("restaurant_id", "unknown")
    party_size = params.get("party_size", 2)
    confirmation = _deterministic_id("RSV", f"{restaurant_id}-{party_size}")

    return {
        "success": True,
        "data": {
            "confirmation": confirmation,
            "restaurant": restaurant_id,
            "date": params.get("date", "2025-06-15"),
            "time": params.get("time", "19:00"),
            "party_size": party_size,
        },
        "artifact_type": "booking",
        "duration_ms": 200,
    }


async def mock_weather_forecast(params: dict[str, Any]) -> dict[str, Any]:
    """Mock weather forecast."""
    location = params.get("location", "unknown")
    days = params.get("days", 3)

    forecasts = []
    conditions = ["Sunny", "Partly Cloudy", "Clear", "Overcast", "Sunny"]
    for i in range(min(days, 5)):
        forecasts.append(
            {
                "day": i + 1,
                "condition": conditions[i % len(conditions)],
                "high_f": 78 + i * 2,
                "low_f": 55 + i,
                "humidity_pct": 40 + i * 5,
            }
        )

    return {
        "success": True,
        "data": {
            "location": location,
            "forecasts": forecasts,
        },
        "artifact_type": None,
        "duration_ms": 80,
    }


async def mock_calendar_create(params: dict[str, Any]) -> dict[str, Any]:
    """Mock calendar event creation."""
    title = params.get("title", "Untitled Event")
    date = params.get("date", "2025-06-15")
    time_str = params.get("time", "10:00")
    event_id = _deterministic_id("EVT", f"{title}-{date}-{time_str}")

    return {
        "success": True,
        "data": {
            "event_id": event_id,
            "title": title,
            "date": date,
            "time": time_str,
            "duration": params.get("duration", "1h"),
            "location": params.get("location"),
        },
        "artifact_type": "appointment",
        "duration_ms": 180,
    }


async def mock_product_search(params: dict[str, Any]) -> dict[str, Any]:
    """Mock product search returning 3 results."""
    query = params.get("query", "")
    max_price = params.get("max_price")

    results = [
        {
            "name": f"Premium {query}",
            "price": 89.99,
            "rating": 4.7,
            "brand": "TopBrand",
            "in_stock": True,
        },
        {
            "name": f"Standard {query}",
            "price": 49.99,
            "rating": 4.2,
            "brand": "MidBrand",
            "in_stock": True,
        },
        {
            "name": f"Budget {query}",
            "price": 24.99,
            "rating": 3.9,
            "brand": "ValueBrand",
            "in_stock": True,
        },
    ]

    if max_price:
        results = [r for r in results if r["price"] <= max_price]

    return {
        "success": True,
        "data": results,
        "artifact_type": None,
        "duration_ms": 100,
    }


# =========================================================================
# Handler map -- maps capability name to handler function
# =========================================================================

DEMO_HANDLERS: dict[str, Any] = {
    "tool.execute.hotel_search": mock_hotel_search,
    "tool.execute.hotel_booking": mock_hotel_booking,
    "tool.execute.restaurant_search": mock_restaurant_search,
    "tool.execute.restaurant_booking": mock_restaurant_booking,
    "tool.execute.weather_forecast": mock_weather_forecast,
    "tool.execute.calendar_create": mock_calendar_create,
    "tool.execute.product_search": mock_product_search,
}
