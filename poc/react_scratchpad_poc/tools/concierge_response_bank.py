"""Canned response data for Concierge Read and Action tools.

These simulate the outputs of K0 Bridge (recall_memory), Fabric Registry
(discover_capabilities), and Fabric execution (invoke_capability,
spawn_via_fabric, execute_workflow) without requiring the actual services.

Each dataset is sized deliberately:
  - recall_memory: ~1,500 tokens (realistic K0 results)
  - discover_capabilities: ~2,000 tokens (ranked capability list)
  - invoke_capability/restaurant_search: ~1,800 tokens (venue list)
  - spawn_via_fabric: ~200 tokens (registration response)
  - execute_workflow: ~300 tokens (queued response)
  - summarize_context: varies by strategy
"""

from __future__ import annotations

from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# recall_memory -- K0 long-term memory results
# ---------------------------------------------------------------------------

MEMORY_RESULTS: Dict[str, List[Dict[str, Any]]] = {
    "mom_birthday": [
        {
            "memory_id": "mem-001",
            "type": "event",
            "content": "Mom's birthday is March 15. Last year we celebrated at Giovanni's Italian restaurant with 8 family members.",
            "confidence": 0.95,
            "timestamp": "2024-03-15T18:00:00Z",
            "source": "user_stated",
            "tags": ["birthday", "mom", "family_event"],
        },
        {
            "memory_id": "mem-002",
            "type": "preference",
            "content": "Mom loves flowers, especially roses and tulips. She also enjoys classical music.",
            "confidence": 0.88,
            "timestamp": "2024-06-12T10:30:00Z",
            "source": "inferred",
            "tags": ["mom", "preferences", "flowers", "music"],
        },
        {
            "memory_id": "mem-003",
            "type": "belief",
            "content": "Mom was vegetarian for 3 years before going fully vegan in January 2025.",
            "confidence": 0.75,
            "timestamp": "2024-09-20T14:15:00Z",
            "source": "user_stated",
            "tags": ["mom", "diet", "vegetarian"],
        },
        {
            "memory_id": "mem-004",
            "type": "relationship",
            "content": "Family members: Dad (Robert), Mom (Catherine), Sister (Sarah, age 28), Brother (Jake, age 22). Sarah is vegetarian. Jake has a nut allergy.",
            "confidence": 0.92,
            "timestamp": "2024-01-05T09:00:00Z",
            "source": "user_stated",
            "tags": ["family", "relationships", "dietary"],
        },
        {
            "memory_id": "mem-005",
            "type": "event",
            "content": "Previous birthday dinners: 2023 at La Bella (Italian, 6 guests), 2024 at Giovanni's (Italian, 8 guests). Mom's favorite dish was the risotto both times.",
            "confidence": 0.85,
            "timestamp": "2025-01-10T20:00:00Z",
            "source": "conversation_summary",
            "tags": ["birthday", "mom", "restaurants", "history"],
        },
    ],
    "dietary": [
        {
            "memory_id": "mem-010",
            "type": "belief",
            "content": "Family dietary requirements: Mom (vegan), Sarah (vegetarian), Jake (nut allergy), Dad and User (no restrictions).",
            "confidence": 0.90,
            "timestamp": "2025-01-15T12:00:00Z",
            "source": "aggregated",
            "tags": ["family", "dietary", "allergies"],
        },
        {
            "memory_id": "mem-011",
            "type": "preference",
            "content": "Family generally prefers sit-down restaurants over casual dining for celebrations. Budget is usually $50-80 per person.",
            "confidence": 0.78,
            "timestamp": "2024-11-01T16:30:00Z",
            "source": "inferred",
            "tags": ["family", "dining", "budget", "preferences"],
        },
    ],
    "default": [
        {
            "memory_id": "mem-099",
            "type": "conversation",
            "content": "No specific memories found for this query. Showing general family context.",
            "confidence": 0.5,
            "timestamp": "2025-01-01T00:00:00Z",
            "source": "fallback",
            "tags": ["general"],
        },
    ],
}


def get_memory_results(query: str, selectors: List[str] | None = None) -> Dict[str, Any]:
    """Return canned K0 memory results based on query keywords."""
    query_lower = query.lower()

    results = []
    if any(kw in query_lower for kw in ["birthday", "mom", "catherine", "celebration"]):
        results.extend(MEMORY_RESULTS["mom_birthday"])
    if any(kw in query_lower for kw in ["diet", "vegan", "food", "allergy", "restriction"]):
        results.extend(MEMORY_RESULTS["dietary"])
    if not results:
        results = MEMORY_RESULTS["default"]

    if selectors:
        results = [r for r in results if r["type"] in selectors or not selectors]

    return {
        "results": results[:10],
        "total_matched": len(results),
        "query_latency_ms": 85,
        "source": "k0_bridge",
    }


# ---------------------------------------------------------------------------
# discover_capabilities -- Fabric Registry results
# ---------------------------------------------------------------------------

CAPABILITIES: List[Dict[str, Any]] = [
    {
        "capability_id": "cap-001",
        "name": "tool.execute.restaurant_search",
        "description": "Search restaurants by cuisine, location, and dietary requirements. Returns up to 20 venues with ratings, pricing, and availability.",
        "domain": ["DINING", "LIFESTYLE"],
        "safety_band": "GREEN",
        "score": 0.95,
        "score_breakdown": {"semantic": 0.96, "domain": 1.0, "success": 0.92, "cost": 0.90},
        "provider": "opentable_mcp",
        "avg_latency_ms": 450,
        "success_rate": 0.97,
        "suggested_inputs": ["cuisine", "location", "party_size"],
        "defaults_note": "All inputs accept reasonable defaults if not specified by user.",
        "optional_inputs": ["dietary_requirements", "price_range", "date"],
    },
    {
        "capability_id": "cap-002",
        "name": "tool.execute.restaurant_booking",
        "description": "Reserve a table at a specified restaurant. Handles party size, date/time, and special requests.",
        "domain": ["DINING"],
        "safety_band": "AMBER",
        "score": 0.91,
        "score_breakdown": {"semantic": 0.88, "domain": 1.0, "success": 0.95, "cost": 0.80},
        "provider": "opentable_mcp",
        "avg_latency_ms": 800,
        "success_rate": 0.94,
        "suggested_inputs": ["restaurant_id", "date", "time", "party_size"],
        "defaults_note": "All inputs accept reasonable defaults if not specified by user.",
        "optional_inputs": ["special_requests", "seating_preference"],
    },
    {
        "capability_id": "cap-003",
        "name": "tool.execute.menu_lookup",
        "description": "Retrieve menu items and dietary labels for a specific restaurant. Supports vegan, vegetarian, gluten-free, nut-free filters.",
        "domain": ["DINING", "HEALTH"],
        "safety_band": "GREEN",
        "score": 0.87,
        "score_breakdown": {"semantic": 0.90, "domain": 0.95, "success": 0.88, "cost": 0.75},
        "provider": "restaurant_api_native",
        "avg_latency_ms": 350,
        "success_rate": 0.91,
        "suggested_inputs": ["restaurant_id"],
        "defaults_note": "All inputs accept reasonable defaults if not specified by user.",
        "optional_inputs": ["dietary_filter", "course_type"],
    },
    {
        "capability_id": "cap-004",
        "name": "tool.execute.florist_search",
        "description": "Find florists and arrange flower delivery. Supports bouquet customization and same-day delivery.",
        "domain": ["LIFESTYLE", "GIFTING"],
        "safety_band": "GREEN",
        "score": 0.72,
        "score_breakdown": {"semantic": 0.65, "domain": 0.70, "success": 0.85, "cost": 0.70},
        "provider": "floral_mcp",
        "avg_latency_ms": 600,
        "success_rate": 0.89,
        "suggested_inputs": ["occasion", "flower_types"],
        "defaults_note": "All inputs accept reasonable defaults if not specified by user.",
        "optional_inputs": ["delivery_date", "budget", "message"],
    },
    {
        "capability_id": "cap-005",
        "name": "tool.execute.calendar_check",
        "description": "Query family calendar for availability on a specific date/time range.",
        "domain": ["SCHEDULING", "FAMILY"],
        "safety_band": "GREEN",
        "score": 0.68,
        "score_breakdown": {"semantic": 0.60, "domain": 0.80, "success": 0.90, "cost": 0.95},
        "provider": "google_calendar_native",
        "avg_latency_ms": 200,
        "success_rate": 0.98,
        "suggested_inputs": ["date_range"],
        "defaults_note": "All inputs accept reasonable defaults if not specified by user.",
        "optional_inputs": ["family_members", "event_type"],
    },
    {
        "capability_id": "cap-006",
        "name": "agent.execute.party_coordinator",
        "description": "Specialized agent for coordinating multi-aspect party planning including venue, catering, decorations, and guest management.",
        "domain": ["LIFESTYLE", "FAMILY", "DINING"],
        "safety_band": "AMBER",
        "score": 0.65,
        "score_breakdown": {"semantic": 0.75, "domain": 0.85, "success": 0.50, "cost": 0.45},
        "provider": "fabric_dynamic_agent",
        "avg_latency_ms": 5000,
        "success_rate": 0.82,
        "suggested_inputs": ["event_type", "date", "guest_count"],
        "defaults_note": "All inputs accept reasonable defaults if not specified by user.",
        "optional_inputs": ["budget", "dietary_requirements", "theme"],
    },
]


def get_capability_results(intent: str, domain: List[str], top_k: int = 10) -> Dict[str, Any]:
    """Return canned Fabric capability discovery results."""
    # Case-insensitive domain filtering
    upper_domain = [d.upper() for d in domain] if domain else []
    scored = []
    for cap in CAPABILITIES:
        domain_match = any(d in cap["domain"] for d in upper_domain) if upper_domain else True
        if domain_match:
            scored.append(cap)

    scored.sort(key=lambda c: c["score"], reverse=True)
    results = scored[:top_k]

    return {
        "capabilities": results,
        "total_matched": len(results),
        "query_latency_ms": 18,
    }


# ---------------------------------------------------------------------------
# invoke_capability -- restaurant search results
# ---------------------------------------------------------------------------

RESTAURANT_SEARCH_RESULTS: Dict[str, Any] = {
    "success": True,
    "provider_id": "opentable_mcp",
    "duration_ms": 420,
    "trace_id": "tr-cap-rest-001",
    "data": {
        "restaurants": [
            {
                "id": "rest-001",
                "name": "The Green Garden",
                "cuisine": "Modern Vegan",
                "rating": 4.8,
                "price_range": "$$$$",
                "avg_price_per_person": 75,
                "location": "Downtown",
                "distance_km": 3.2,
                "vegan_options": 28,
                "vegetarian_options": 28,
                "nut_free_options": 22,
                "gluten_free_options": 18,
                "ambiance": "Fine Dining",
                "private_dining": True,
                "max_party_size": 20,
                "next_availability": "2026-03-15 18:00",
                "reviews_summary": "Outstanding vegan fine dining. Creative menu changes seasonally. Excellent wine list with organic options.",
            },
            {
                "id": "rest-002",
                "name": "Sage & Thyme",
                "cuisine": "Plant-Based Contemporary",
                "rating": 4.6,
                "price_range": "$$$",
                "avg_price_per_person": 55,
                "location": "Midtown",
                "distance_km": 5.1,
                "vegan_options": 22,
                "vegetarian_options": 22,
                "nut_free_options": 15,
                "gluten_free_options": 12,
                "ambiance": "Casual Elegant",
                "private_dining": True,
                "max_party_size": 16,
                "next_availability": "2026-03-15 19:00",
                "reviews_summary": "Beautiful plant-based dishes with a focus on local ingredients. Great for special occasions.",
            },
            {
                "id": "rest-003",
                "name": "Harvest Moon",
                "cuisine": "Farm-to-Table Vegan",
                "rating": 4.5,
                "price_range": "$$$",
                "avg_price_per_person": 60,
                "location": "West End",
                "distance_km": 4.8,
                "vegan_options": 20,
                "vegetarian_options": 25,
                "nut_free_options": 18,
                "gluten_free_options": 16,
                "ambiance": "Rustic Elegant",
                "private_dining": False,
                "max_party_size": 12,
                "next_availability": "2026-03-15 18:30",
                "reviews_summary": "Farm-to-table concept with organic produce. Intimate setting. Limited party size.",
            },
            {
                "id": "rest-004",
                "name": "Verde Kitchen",
                "cuisine": "Mediterranean Vegan",
                "rating": 4.3,
                "price_range": "$$",
                "avg_price_per_person": 40,
                "location": "East Side",
                "distance_km": 6.5,
                "vegan_options": 18,
                "vegetarian_options": 24,
                "nut_free_options": 14,
                "gluten_free_options": 10,
                "ambiance": "Casual",
                "private_dining": False,
                "max_party_size": 30,
                "next_availability": "2026-03-15 17:30",
                "reviews_summary": "Great value Mediterranean vegan food. Large venue, good for groups. Quality varies.",
            },
            {
                "id": "rest-005",
                "name": "Lotus Blossom",
                "cuisine": "Asian Vegan Fusion",
                "rating": 4.7,
                "price_range": "$$$",
                "avg_price_per_person": 65,
                "location": "Chinatown",
                "distance_km": 7.2,
                "vegan_options": 35,
                "vegetarian_options": 35,
                "nut_free_options": 20,
                "gluten_free_options": 25,
                "ambiance": "Upscale Asian",
                "private_dining": True,
                "max_party_size": 14,
                "next_availability": "2026-03-15 19:30",
                "reviews_summary": "Exceptional Asian fusion vegan cuisine. Beautiful presentation. Must try the dim sum and ramen.",
            },
        ],
        "total_results": 5,
        "search_criteria": {
            "cuisine": "vegan",
            "date": "2026-03-15",
            "party_size": 8,
            "dietary": ["vegan", "vegetarian", "nut-free"],
        },
    },
}


def get_capability_result(capability: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Return canned result for a capability invocation."""
    if "restaurant" in capability.lower() and "search" in capability.lower():
        return RESTAURANT_SEARCH_RESULTS
    if "restaurant" in capability.lower() and "book" in capability.lower():
        return {
            "success": True,
            "provider_id": "opentable_mcp",
            "duration_ms": 780,
            "trace_id": "tr-cap-book-001",
            "data": {
                "booking_id": "BK-2026-03-15-001",
                "restaurant": params.get("restaurant_id", "rest-001"),
                "date": params.get("date", "2026-03-15"),
                "time": params.get("time", "18:00"),
                "party_size": params.get("party_size", 8),
                "status": "confirmed",
                "special_requests": params.get(
                    "special_requests", "Birthday celebration, vegan menu"
                ),
                "confirmation_code": "GG-8K7M2P",
            },
        }
    # Generic fallback
    return {
        "success": True,
        "provider_id": "generic_provider",
        "duration_ms": 500,
        "trace_id": "tr-cap-gen-001",
        "data": {"result": f"Capability {capability} executed", "params": params},
    }


# ---------------------------------------------------------------------------
# spawn_via_fabric -- agent creation
# ---------------------------------------------------------------------------


def get_spawn_result(agent_name: str, **kwargs: Any) -> Dict[str, Any]:
    """Return canned spawn result."""
    return {
        "success": True,
        "agent_name": agent_name,
        "status": "registered",
        "errors": [],
        "agent_id": f"agent-{agent_name.split('.')[-1]}-001",
        "capabilities_granted": kwargs.get("tools_granted", []),
        "token_budget": kwargs.get("llm_budget_tokens", 4096),
    }


# ---------------------------------------------------------------------------
# execute_workflow -- orchestrator result
# ---------------------------------------------------------------------------


def get_workflow_result(workflow_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Return canned workflow execution result."""
    return {
        "success": True,
        "envelope_id": f"env-{workflow_id.split('.')[-1]}-001",
        "status": "queued",
        "rejection_reason": None,
        "estimated_duration_ms": 45000,
        "dag_steps": [
            {"step": "venue_confirmation", "status": "pending"},
            {"step": "dietary_menu_check", "status": "pending"},
            {"step": "guest_notification", "status": "pending"},
            {"step": "decoration_coordination", "status": "pending"},
            {"step": "final_confirmation", "status": "pending"},
        ],
        "workflow_id": workflow_id,
        "params": params,
    }
