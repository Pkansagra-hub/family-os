"""
BookingAgent - Specialized Booking Sub-Agent
============================================

Handles booking operations for:
- Accommodations (hotels, B&Bs)
- Restaurants
- Spa services
- Activities

Has READ-ONLY access to SessionState.
All bookings require Concierge confirmation before finalizing.
Reports results via Delta Bus.

Reference: FULL_ARCHITECTURE_IMPLEMENTATION_PLAN.md - Milestone 8.3
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
# BOOKING AGENT SYSTEM PROMPT
# =============================================================================

BOOKING_AGENT_SYSTEM_PROMPT = """You are a BookingAgent - a specialized booking assistant for FamilyOS.

YOUR ROLE:
- Make reservations for accommodations, restaurants, and activities
- Verify availability before booking
- Prepare booking confirmations for Concierge review

AVAILABLE TOOLS:
- book_accommodation: Book a hotel or B&B
- book_restaurant: Make a restaurant reservation
- book_spa_service: Book a spa treatment
- book_activity: Book an activity or tour

CONSTRAINTS:
- You have READ-ONLY access to user data
- All bookings are PENDING until Concierge confirms
- You cannot modify user preferences or beliefs
- Always include special requests (allergies, celebrations, etc.)
- Verify party size and dates are correct

BOOKING PROCESS:
1. Receive booking request with parameters
2. Validate all required information is present
3. Execute booking tool
4. Return confirmation details for Concierge review
5. Concierge finalizes with user

RESPONSE FORMAT:
- Return structured booking confirmations
- Include: confirmation number, details, total cost, cancellation policy
- Flag any special accommodations made (allergies, celebrations)
"""


# =============================================================================
# MOCK BOOKING DATA
# =============================================================================

MOCK_BOOKINGS = {
    "confirmations": {},
    "next_confirmation": 1001,
}


def generate_confirmation_number() -> str:
    """Generate a mock confirmation number."""
    num = MOCK_BOOKINGS["next_confirmation"]
    MOCK_BOOKINGS["next_confirmation"] += 1
    return f"FOS-{num}"


# =============================================================================
# BOOKING AGENT IMPLEMENTATION
# =============================================================================


class BookingAgent(BaseSubAgent):
    """
    Specialized agent for booking operations.

    Can book:
    - Accommodations
    - Restaurants
    - Spa services
    - Activities

    Has READ-ONLY SessionState access.
    All bookings require Concierge confirmation.
    """

    AGENT_TYPE = "booking"
    SYSTEM_PROMPT = BOOKING_AGENT_SYSTEM_PROMPT

    def __init__(
        self,
        bridge: "SessionLLMBridge",
        llm_client: "SimpleLLMClient",
        delta_bus: Optional["DeltaBus"] = None,
        tool_executor: Optional["ToolExecutor"] = None,
        agent_id: Optional[str] = None,
    ):
        """
        Initialize BookingAgent.

        Args:
            bridge: SessionLLMBridge (wrapped as READ-ONLY)
            llm_client: LLM client for agent's context
            delta_bus: Optional Delta bus for results
            tool_executor: Optional tool executor
            agent_id: Optional agent ID
        """
        super().__init__(bridge, llm_client, delta_bus, agent_id)
        self._tool_executor = tool_executor
        self._pending_bookings: Dict[str, Dict[str, Any]] = {}

    def get_available_tools(self) -> List[Dict[str, Any]]:
        """Get booking-related tools."""
        return [
            {
                "name": "book_accommodation",
                "description": "Book a hotel or vacation rental",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Accommodation name"},
                        "check_in_date": {"type": "string", "description": "Check-in date"},
                        "check_out_date": {"type": "string", "description": "Check-out date"},
                        "guests": {"type": "integer", "description": "Number of guests"},
                        "room_type": {"type": "string", "description": "Room type"},
                        "special_requests": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["name", "check_in_date", "check_out_date"],
                },
            },
            {
                "name": "book_restaurant",
                "description": "Make a restaurant reservation",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "restaurant_name": {"type": "string", "description": "Restaurant name"},
                        "date": {"type": "string", "description": "Reservation date"},
                        "time": {"type": "string", "description": "Reservation time"},
                        "party_size": {"type": "integer", "description": "Number of diners"},
                        "special_requests": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["restaurant_name", "date", "time", "party_size"],
                },
            },
            {
                "name": "book_spa_service",
                "description": "Book a spa treatment",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service_type": {"type": "string", "description": "Type of service"},
                        "date": {"type": "string", "description": "Date"},
                        "time": {"type": "string", "description": "Time"},
                        "guests": {"type": "integer", "description": "Number of guests"},
                        "special_requests": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["service_type", "date", "time"],
                },
            },
            {
                "name": "book_activity",
                "description": "Book an activity or tour",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "activity_name": {"type": "string", "description": "Activity name"},
                        "date": {"type": "string", "description": "Date"},
                        "time": {"type": "string", "description": "Time"},
                        "participants": {
                            "type": "integer",
                            "description": "Number of participants",
                        },
                    },
                    "required": ["activity_name", "date"],
                },
            },
        ]

    async def execute_tool(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """Execute a booking tool."""
        logger.info(f"BookingAgent executing: {tool_name}({args})")

        # Use tool executor if available
        if self._tool_executor:
            try:
                result = self._tool_executor.execute(tool_name, args)
                return result
            except Exception as e:
                logger.warning(f"Tool executor failed, using mock: {e}")

        # Mock implementations
        if tool_name == "book_accommodation":
            return self._mock_book_accommodation(args)
        elif tool_name == "book_restaurant":
            return self._mock_book_restaurant(args)
        elif tool_name == "book_spa_service":
            return self._mock_book_spa(args)
        elif tool_name == "book_activity":
            return self._mock_book_activity(args)
        else:
            return {"error": f"Unknown tool: {tool_name}"}

    def _get_allergy_notes(self) -> List[str]:
        """Get allergy information from session context."""
        allergies = []
        beliefs = self._bridge.get_beliefs()

        for subject, predicates in beliefs.items():
            if isinstance(predicates, dict):
                for pred, obj in predicates.items():
                    if "allergy" in pred.lower():
                        allergies.append(f"{subject} has {obj} allergy")

        return allergies

    def _mock_book_accommodation(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Mock accommodation booking."""
        confirmation = generate_confirmation_number()

        booking = {
            "confirmation_number": confirmation,
            "type": "accommodation",
            "status": "PENDING_CONFIRMATION",
            "details": {
                "property": args.get("name"),
                "check_in": args.get("check_in_date"),
                "check_out": args.get("check_out_date"),
                "guests": args.get("guests", 2),
                "room_type": args.get("room_type", "Standard"),
                "special_requests": args.get("special_requests", []),
            },
            "pricing": {
                "rate_per_night": 285,  # Mock price
                "nights": 2,
                "subtotal": 570,
                "taxes": 71.25,
                "total": 641.25,
            },
            "cancellation_policy": "Free cancellation until 48 hours before check-in",
            "requires_concierge_confirmation": True,
        }

        self._pending_bookings[confirmation] = booking
        return booking

    def _mock_book_restaurant(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Mock restaurant booking with allergy awareness."""
        confirmation = generate_confirmation_number()

        # Check for allergies
        allergies = self._get_allergy_notes()
        special_requests = list(args.get("special_requests", []))
        if allergies:
            special_requests.extend(allergies)

        booking = {
            "confirmation_number": confirmation,
            "type": "restaurant",
            "status": "PENDING_CONFIRMATION",
            "details": {
                "restaurant": args.get("restaurant_name"),
                "date": args.get("date"),
                "time": args.get("time"),
                "party_size": args.get("party_size", 2),
                "special_requests": special_requests,
            },
            "notes": "Kitchen will be notified of allergy requirements" if allergies else None,
            "cancellation_policy": "Please cancel at least 2 hours before reservation",
            "requires_concierge_confirmation": True,
        }

        self._pending_bookings[confirmation] = booking
        return booking

    def _mock_book_spa(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Mock spa booking."""
        confirmation = generate_confirmation_number()

        booking = {
            "confirmation_number": confirmation,
            "type": "spa",
            "status": "PENDING_CONFIRMATION",
            "details": {
                "service": args.get("service_type"),
                "date": args.get("date"),
                "time": args.get("time"),
                "guests": args.get("guests", 2),
                "special_requests": args.get("special_requests", []),
            },
            "pricing": {
                "service_price": 350,
                "gratuity_suggested": 52.50,
                "total": 350,
            },
            "notes": "Please arrive 15 minutes early. Robes and slippers provided.",
            "cancellation_policy": "24 hour cancellation policy",
            "requires_concierge_confirmation": True,
        }

        self._pending_bookings[confirmation] = booking
        return booking

    def _mock_book_activity(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Mock activity booking."""
        confirmation = generate_confirmation_number()

        booking = {
            "confirmation_number": confirmation,
            "type": "activity",
            "status": "PENDING_CONFIRMATION",
            "details": {
                "activity": args.get("activity_name"),
                "date": args.get("date"),
                "time": args.get("time", "morning"),
                "participants": args.get("participants", 2),
            },
            "pricing": {
                "per_person": 40,
                "participants": args.get("participants", 2),
                "total": 80,
            },
            "notes": "Confirmation email will be sent after Concierge approval",
            "cancellation_policy": "Full refund if cancelled 48 hours before",
            "requires_concierge_confirmation": True,
        }

        self._pending_bookings[confirmation] = booking
        return booking

    async def book_accommodation(
        self,
        name: str,
        check_in_date: str,
        check_out_date: str,
        guests: int = 2,
        room_type: Optional[str] = None,
        special_requests: Optional[List[str]] = None,
    ) -> AgentResult:
        """
        Convenience method to book accommodation.

        Args:
            name: Accommodation name
            check_in_date: Check-in date
            check_out_date: Check-out date
            guests: Number of guests
            room_type: Type of room
            special_requests: Special requests

        Returns:
            AgentResult with booking confirmation
        """
        params = {
            "name": name,
            "check_in_date": check_in_date,
            "check_out_date": check_out_date,
            "guests": guests,
        }
        if room_type:
            params["room_type"] = room_type
        if special_requests:
            params["special_requests"] = special_requests

        return await self.run_task("book_accommodation", params)

    async def book_restaurant(
        self,
        restaurant_name: str,
        date: str,
        time: str,
        party_size: int = 2,
        special_requests: Optional[List[str]] = None,
    ) -> AgentResult:
        """
        Convenience method to book restaurant.

        Args:
            restaurant_name: Restaurant name
            date: Reservation date
            time: Reservation time
            party_size: Number of diners
            special_requests: Special requests

        Returns:
            AgentResult with booking confirmation
        """
        params = {
            "restaurant_name": restaurant_name,
            "date": date,
            "time": time,
            "party_size": party_size,
        }
        if special_requests:
            params["special_requests"] = special_requests

        return await self.run_task("book_restaurant", params)

    async def book_spa_service(
        self,
        service_type: str,
        date: str,
        time: str,
        guests: int = 2,
        special_requests: Optional[List[str]] = None,
    ) -> AgentResult:
        """
        Convenience method to book spa service.

        Args:
            service_type: Type of spa service
            date: Date
            time: Time
            guests: Number of guests
            special_requests: Special requests

        Returns:
            AgentResult with booking confirmation
        """
        params = {
            "service_type": service_type,
            "date": date,
            "time": time,
            "guests": guests,
        }
        if special_requests:
            params["special_requests"] = special_requests

        return await self.run_task("book_spa_service", params)

    def get_pending_bookings(self) -> Dict[str, Dict[str, Any]]:
        """Get all pending bookings awaiting confirmation."""
        return dict(self._pending_bookings)

    def confirm_booking(self, confirmation_number: str) -> bool:
        """
        Mark a booking as confirmed (called by Concierge).

        Args:
            confirmation_number: The confirmation number to confirm

        Returns:
            True if booking was confirmed, False if not found
        """
        if confirmation_number in self._pending_bookings:
            self._pending_bookings[confirmation_number]["status"] = "CONFIRMED"
            return True
        return False
