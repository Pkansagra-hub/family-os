"""
SearchAgent - Specialized Search Sub-Agent
==========================================

Handles search operations for:
- Accommodations (hotels, B&Bs, vacation rentals)
- Restaurants
- Activities and attractions

Has READ-ONLY access to SessionState.
Reports results via Delta Bus.

Reference: FULL_ARCHITECTURE_IMPLEMENTATION_PLAN.md - Milestone 8.2
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from poc.session_state_demo.anniversary_demo.agents.base import AgentResult, BaseSubAgent

if TYPE_CHECKING:
    from poc.session_state_demo.anniversary_demo.bus.delta_bus import DeltaBus
    from poc.session_state_demo.anniversary_demo.tools.executor import ToolExecutor
    from poc.session_state_demo.bridge import SessionLLMBridge
    from poc.session_state_demo.llm_client import SimpleLLMClient

logger = logging.getLogger(__name__)


# =============================================================================
# SEARCH AGENT SYSTEM PROMPT
# =============================================================================

SEARCH_AGENT_SYSTEM_PROMPT = """You are a SearchAgent - a specialized search assistant for FamilyOS.

YOUR ROLE:
- Search for accommodations, restaurants, and activities
- Filter results based on user preferences and constraints
- Return comprehensive search results

AVAILABLE TOOLS:
- search_accommodations: Search for hotels, B&Bs, vacation rentals
- search_restaurants: Search for restaurants by location, cuisine, etc.
- search_activities: Search for activities and attractions
- get_accommodation_details: Get details about a specific accommodation
- get_restaurant_details: Get details about a specific restaurant

CONSTRAINTS:
- You have READ-ONLY access to user data
- You cannot make bookings or reservations
- You cannot modify user preferences
- Always consider allergies and dietary restrictions when searching restaurants
- Stay within budget constraints when searching accommodations

RESPONSE FORMAT:
- Return structured search results
- Include key details: name, price, rating, relevant features
- Flag any items that match user preferences or have potential issues (allergies, budget)
"""


# =============================================================================
# MOCK SEARCH DATA (for demo purposes)
# =============================================================================

MOCK_ACCOMMODATIONS = [
    {
        "name": "Vineyard Inn & Spa",
        "type": "boutique_hotel",
        "location": "Sonoma",
        "price_per_night": 285,
        "rating": 4.8,
        "amenities": ["spa", "pool", "wine_tasting", "breakfast_included"],
        "available": True,
        "description": "Charming boutique hotel surrounded by vineyards with full-service spa",
    },
    {
        "name": "Sonoma Creek Inn",
        "type": "bnb",
        "location": "Sonoma",
        "price_per_night": 195,
        "rating": 4.6,
        "amenities": ["breakfast_included", "garden", "wifi"],
        "available": True,
        "description": "Cozy B&B with beautiful garden and homemade breakfast",
    },
    {
        "name": "The Lodge at Sonoma",
        "type": "resort",
        "location": "Sonoma",
        "price_per_night": 350,
        "rating": 4.9,
        "amenities": ["spa", "pool", "restaurant", "fitness_center", "wine_bar"],
        "available": True,
        "description": "Luxury resort with world-class amenities and vineyard views",
    },
    {
        "name": "Wine Country Cottage",
        "type": "vacation_rental",
        "location": "Sonoma",
        "price_per_night": 225,
        "rating": 4.7,
        "amenities": ["kitchen", "hot_tub", "vineyard_views", "private"],
        "available": True,
        "description": "Private cottage with hot tub and stunning vineyard views",
    },
]

MOCK_RESTAURANTS = [
    {
        "name": "The Girl & The Fig",
        "cuisine": "French",
        "location": "Sonoma",
        "price_range": "$$$",
        "rating": 4.7,
        "features": ["outdoor_seating", "wine_list", "local_ingredients"],
        "shellfish_safe": True,
        "description": "Farm-to-table French cuisine in historic Sonoma Plaza",
    },
    {
        "name": "Della Santina's",
        "cuisine": "Italian",
        "location": "Sonoma",
        "price_range": "$$",
        "rating": 4.5,
        "features": ["family_owned", "garden_patio", "birthday_specials"],
        "shellfish_safe": True,
        "description": "Authentic Italian trattoria with beautiful garden patio",
    },
    {
        "name": "LaSalette Restaurant",
        "cuisine": "Portuguese",
        "location": "Sonoma",
        "price_range": "$$$",
        "rating": 4.6,
        "features": ["romantic", "wine_pairings", "seafood"],
        "shellfish_safe": False,  # Has shellfish dishes
        "description": "Romantic Portuguese cuisine with extensive wine pairings",
    },
    {
        "name": "El Dorado Kitchen",
        "cuisine": "California",
        "location": "Sonoma",
        "price_range": "$$$",
        "rating": 4.8,
        "features": ["chef_driven", "seasonal_menu", "rooftop"],
        "shellfish_safe": True,
        "description": "Chef-driven California cuisine with rooftop dining",
    },
]

MOCK_ACTIVITIES = [
    {
        "name": "Benziger Family Winery Tour",
        "type": "wine_tasting",
        "location": "Sonoma",
        "price": 40,
        "duration": "2 hours",
        "rating": 4.9,
        "description": "Award-winning biodynamic winery with tram tour through vineyards",
    },
    {
        "name": "Sonoma Hot Air Balloon Ride",
        "type": "adventure",
        "location": "Sonoma",
        "price": 250,
        "duration": "3-4 hours",
        "rating": 4.8,
        "description": "Sunrise balloon ride over wine country with champagne toast",
    },
    {
        "name": "Sonoma Olive Oil Tasting",
        "type": "food_tour",
        "location": "Sonoma",
        "price": 25,
        "duration": "1 hour",
        "rating": 4.6,
        "description": "Sample award-winning olive oils at the Olive Press",
    },
    {
        "name": "Couples Spa at Vineyard Inn",
        "type": "spa",
        "location": "Sonoma",
        "price": 350,
        "duration": "2 hours",
        "rating": 4.9,
        "description": "Relaxing couples massage with vineyard views",
    },
]


# =============================================================================
# SEARCH AGENT IMPLEMENTATION
# =============================================================================


class SearchAgent(BaseSubAgent):
    """
    Specialized agent for search operations.

    Can search:
    - Accommodations (hotels, B&Bs, vacation rentals)
    - Restaurants
    - Activities and attractions

    Has READ-ONLY SessionState access.
    """

    AGENT_TYPE = "search"
    SYSTEM_PROMPT = SEARCH_AGENT_SYSTEM_PROMPT

    def __init__(
        self,
        bridge: "SessionLLMBridge",
        llm_client: "SimpleLLMClient",
        delta_bus: Optional["DeltaBus"] = None,
        tool_executor: Optional["ToolExecutor"] = None,
        agent_id: Optional[str] = None,
    ):
        """
        Initialize SearchAgent.

        Args:
            bridge: SessionLLMBridge (wrapped as READ-ONLY)
            llm_client: LLM client for agent's context
            delta_bus: Optional Delta bus for results
            tool_executor: Optional tool executor (for real tool execution)
            agent_id: Optional agent ID
        """
        super().__init__(bridge, llm_client, delta_bus, agent_id)
        self._tool_executor = tool_executor

    def get_available_tools(self) -> List[Dict[str, Any]]:
        """Get search-related tools."""
        return [
            {
                "name": "search_accommodations",
                "description": "Search for hotels, B&Bs, or vacation rentals",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "Location to search"},
                        "check_in_date": {"type": "string", "description": "Check-in date"},
                        "nights": {"type": "integer", "description": "Number of nights"},
                        "budget_per_night": {
                            "type": "number",
                            "description": "Max price per night",
                        },
                        "amenities": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["location"],
                },
            },
            {
                "name": "search_restaurants",
                "description": "Search for restaurants",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "Location to search"},
                        "cuisine": {"type": "string", "description": "Type of cuisine"},
                        "avoid_ingredients": {"type": "array", "items": {"type": "string"}},
                        "price_range": {"type": "string", "enum": ["$", "$$", "$$$", "$$$$"]},
                    },
                    "required": ["location"],
                },
            },
            {
                "name": "search_activities",
                "description": "Search for activities and attractions",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {"type": "string", "description": "Location to search"},
                        "activity_type": {"type": "string", "description": "Type of activity"},
                        "max_price": {"type": "number", "description": "Maximum price"},
                    },
                    "required": ["location"],
                },
            },
        ]

    async def execute_tool(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """Execute a search tool."""
        logger.info(f"SearchAgent executing: {tool_name}({args})")

        # Use tool executor if available, otherwise use mock data
        if self._tool_executor:
            try:
                result = self._tool_executor.execute(tool_name, args)
                return result
            except Exception as e:
                logger.warning(f"Tool executor failed, using mock: {e}")

        # Mock implementations for demo
        if tool_name == "search_accommodations":
            return self._mock_search_accommodations(args)
        elif tool_name == "search_restaurants":
            return self._mock_search_restaurants(args)
        elif tool_name == "search_activities":
            return self._mock_search_activities(args)
        else:
            return {"error": f"Unknown tool: {tool_name}"}

    def _mock_search_accommodations(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Mock accommodation search."""
        location = args.get("location", "").lower()
        budget = args.get("budget_per_night")
        amenities = args.get("amenities", [])

        results = []
        for acc in MOCK_ACCOMMODATIONS:
            if location and location not in acc["location"].lower():
                continue
            if budget and acc["price_per_night"] > budget:
                continue
            if amenities:
                if not any(a in acc["amenities"] for a in amenities):
                    continue
            results.append(acc)

        return {
            "location": args.get("location"),
            "results_count": len(results),
            "accommodations": results,
        }

    def _mock_search_restaurants(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Mock restaurant search with allergy awareness."""
        location = args.get("location", "").lower()
        cuisine = args.get("cuisine", "").lower()
        avoid = [a.lower() for a in args.get("avoid_ingredients", [])]

        # Check for shellfish allergy from session context
        beliefs = self._bridge.get_beliefs()
        has_shellfish_allergy = False
        for subject, predicates in beliefs.items():
            if isinstance(predicates, dict):
                for pred, obj in predicates.items():
                    if "allergy" in pred.lower() and "shellfish" in str(obj).lower():
                        has_shellfish_allergy = True
                        break

        if has_shellfish_allergy and "shellfish" not in avoid:
            avoid.append("shellfish")

        results = []
        for rest in MOCK_RESTAURANTS:
            if location and location not in rest["location"].lower():
                continue
            if cuisine and cuisine not in rest["cuisine"].lower():
                continue

            # Check shellfish safety
            if "shellfish" in avoid and not rest.get("shellfish_safe", True):
                # Still include but flag it
                rest_copy = dict(rest)
                rest_copy["warning"] = "Contains shellfish - may not be safe for Mike's allergy"
                results.append(rest_copy)
            else:
                results.append(rest)

        return {
            "location": args.get("location"),
            "cuisine_filter": cuisine or "any",
            "allergy_filter": avoid if avoid else None,
            "results_count": len(results),
            "restaurants": results,
        }

    def _mock_search_activities(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Mock activity search."""
        location = args.get("location", "").lower()
        activity_type = args.get("activity_type", "").lower()
        max_price = args.get("max_price")

        results = []
        for act in MOCK_ACTIVITIES:
            if location and location not in act["location"].lower():
                continue
            if activity_type and activity_type not in act["type"].lower():
                continue
            if max_price and act["price"] > max_price:
                continue
            results.append(act)

        return {
            "location": args.get("location"),
            "results_count": len(results),
            "activities": results,
        }

    async def search_accommodations(
        self,
        location: str,
        check_in_date: Optional[str] = None,
        nights: int = 2,
        budget_per_night: Optional[float] = None,
        amenities: Optional[List[str]] = None,
    ) -> AgentResult:
        """
        Convenience method to search accommodations.

        Args:
            location: Location to search
            check_in_date: Check-in date
            nights: Number of nights
            budget_per_night: Maximum price per night
            amenities: Desired amenities

        Returns:
            AgentResult with search results
        """
        params = {
            "location": location,
            "nights": nights,
        }
        if check_in_date:
            params["check_in_date"] = check_in_date
        if budget_per_night:
            params["budget_per_night"] = budget_per_night
        if amenities:
            params["amenities"] = amenities

        return await self.run_task("search_accommodations", params)

    async def search_restaurants(
        self,
        location: str,
        cuisine: Optional[str] = None,
        avoid_ingredients: Optional[List[str]] = None,
        price_range: Optional[str] = None,
    ) -> AgentResult:
        """
        Convenience method to search restaurants.

        Args:
            location: Location to search
            cuisine: Type of cuisine
            avoid_ingredients: Ingredients to avoid (allergies)
            price_range: Price range ($, $$, $$$, $$$$)

        Returns:
            AgentResult with search results
        """
        params = {"location": location}
        if cuisine:
            params["cuisine"] = cuisine
        if avoid_ingredients:
            params["avoid_ingredients"] = avoid_ingredients
        if price_range:
            params["price_range"] = price_range

        return await self.run_task("search_restaurants", params)

    async def search_activities(
        self,
        location: str,
        activity_type: Optional[str] = None,
        max_price: Optional[float] = None,
    ) -> AgentResult:
        """
        Convenience method to search activities.

        Args:
            location: Location to search
            activity_type: Type of activity
            max_price: Maximum price

        Returns:
            AgentResult with search results
        """
        params = {"location": location}
        if activity_type:
            params["activity_type"] = activity_type
        if max_price:
            params["max_price"] = max_price

        return await self.run_task("search_activities", params)
