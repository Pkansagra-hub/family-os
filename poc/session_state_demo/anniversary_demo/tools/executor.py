"""
Tool Executor
=============

Executes all 21 demo tools with:
- SessionState tools: Write to real SessionState via bridge
- Travel tools: Return realistic mock data for demo
- Family tools: Log and simulate messaging
- Calendar tools: Track events in session
- Background tools: Register monitors (simulated)
- Agent tools: Spawn sub-agents for complex tasks

The executor separates REAL writes (SessionState) from SIMULATED returns
(search results, bookings) to keep the demo realistic without external APIs.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from poc.session_state_demo.bridge import SessionLLMBridge

# Type for spawn_agent callback
SpawnAgentCallback = Callable[[str, str, Dict[str, Any]], "asyncio.Task[Any]"]


@dataclass
class ToolResult:
    """Result from executing a tool."""

    tool_name: str
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    message: str = ""
    execution_time_ms: int = 0
    wrote_to_session: bool = False


@dataclass
class BackgroundMonitor:
    """Tracks a background monitor."""

    monitor_id: str
    monitor_type: str
    target: str
    dates: List[str]
    started_at: float
    check_interval: int = 60


class ToolExecutor:
    """
    Executes all demo tools.

    SessionState tools write REAL data via bridge.
    Other tools return realistic mock data for the demo scenario.
    """

    def __init__(
        self,
        bridge: Optional[SessionLLMBridge] = None,
        spawn_agent_callback: Optional[SpawnAgentCallback] = None,
        plan_controller: Optional[Any] = None,
    ):
        self.bridge = bridge
        self._spawn_agent_callback = spawn_agent_callback
        self._plan_controller = plan_controller
        self._monitors: Dict[str, BackgroundMonitor] = {}
        self._bookings: List[Dict[str, Any]] = []
        self._messages_sent: List[Dict[str, Any]] = []
        self._calendar_events: List[Dict[str, Any]] = []
        self._reminders: List[Dict[str, Any]] = []
        self._spawned_agents: List[Dict[str, Any]] = []  # Track spawned agents

        # Demo data - realistic Sonoma options
        self._accommodations = self._init_accommodations()
        self._restaurants = self._init_restaurants()
        self._activities = self._init_activities()

    def set_spawn_callback(self, callback: SpawnAgentCallback) -> None:
        """Set the callback for spawning sub-agents."""
        self._spawn_agent_callback = callback

    def set_plan_controller(self, plan_controller: Any) -> None:
        """Set the plan controller for duplicate checking."""
        self._plan_controller = plan_controller

    def execute(self, tool_name: str, args: Dict[str, Any]) -> ToolResult:
        """Execute a tool by name with given arguments."""
        start = time.time()

        # Route to handler
        handler = getattr(self, f"_exec_{tool_name}", None)
        if handler:
            result = handler(args)
        else:
            result = ToolResult(
                tool_name=tool_name,
                success=False,
                message=f"Unknown tool: {tool_name}",
            )

        result.execution_time_ms = int((time.time() - start) * 1000)
        return result

    @property
    def bookings(self) -> List[Dict[str, Any]]:
        """Get all bookings made during this session."""
        return self._bookings.copy()

    @property
    def messages_sent(self) -> List[Dict[str, Any]]:
        """Get all messages sent during this session."""
        return self._messages_sent.copy()

    @property
    def calendar_events(self) -> List[Dict[str, Any]]:
        """Get all calendar events created during this session."""
        return self._calendar_events.copy()

    @property
    def spawned_agents(self) -> List[Dict[str, Any]]:
        """Get info about all agents spawned during this session."""
        return self._spawned_agents.copy()

    # =========================================================================
    # ACKNOWLEDGMENT TOOL - Called first to acknowledge user input
    # =========================================================================

    def _exec_acknowledge(self, args: Dict[str, Any]) -> ToolResult:
        """
        Acknowledge user input before taking action.

        This tool MUST be called first before any effectful tools.
        It provides immediate feedback to the user about what was understood
        and what action is about to be taken.

        Schema v2: Uses next_tool (enum) instead of free-text action_preview.
        """
        ack_type = args.get("ack_type", "progress")
        message = args.get("message", "")
        next_tool = args.get("next_tool", "none")

        if not message:
            return ToolResult(
                tool_name="acknowledge",
                success=False,
                message="Message is required for acknowledgment",
            )

        # Validate message doesn't contain banned phrases
        banned_phrases = ["got it", "understood", "noted", "i see", "i understand", "let me"]
        message_lower = message.lower()
        for phrase in banned_phrases:
            if phrase in message_lower:
                # Log warning but don't fail - let the LLM learn
                pass

        # No prefix added - message should be complete on its own
        formatted_message = message

        return ToolResult(
            tool_name="acknowledge",
            success=True,
            data={
                "ack_type": ack_type,
                "message": message,
                "next_tool": next_tool,
                "formatted_message": formatted_message,
                "display_immediately": True,
            },
            message=formatted_message,
        )

    # =========================================================================
    # SUB-AGENT TOOLS - Spawn specialized agents
    # =========================================================================

    def _exec_spawn_agent(self, args: Dict[str, Any]) -> ToolResult:
        """
        Spawn a sub-agent to handle a complex task.

        The agent runs in its own asyncio task with READ-ONLY SessionState access.
        Results are returned via the Delta Bus.
        """
        agent_type = args.get("agent_type", "")
        task_type = args.get("task_type", "")
        params = args.get("params", {})
        priority = args.get("priority", "normal")

        if not agent_type or not task_type:
            return ToolResult(
                tool_name="spawn_agent",
                success=False,
                message="Missing required parameters: agent_type and task_type",
            )

        # Validate agent type
        if agent_type not in ["SearchAgent", "BookingAgent"]:
            return ToolResult(
                tool_name="spawn_agent",
                success=False,
                message=f"Unknown agent type: {agent_type}. Use SearchAgent or BookingAgent.",
            )

        # Generate task ID
        task_id = f"task_{agent_type[:3].lower()}_{random.randint(10000, 99999)}"

        # Track the spawn
        spawn_info = {
            "task_id": task_id,
            "agent_type": agent_type,
            "task_type": task_type,
            "params": params,
            "priority": priority,
            "spawned_at": datetime.now().isoformat(),
            "status": "spawned",
        }
        self._spawned_agents.append(spawn_info)

        # Spawn via callback if available (runs in separate asyncio task)
        if self._spawn_agent_callback:
            try:
                # The callback should create an asyncio task that:
                # 1. Creates the appropriate agent
                # 2. Runs the task
                # 3. Publishes results to Delta Bus
                self._spawn_agent_callback(agent_type, task_type, params)
                spawn_info["status"] = "running"
            except Exception as e:
                spawn_info["status"] = "failed"
                spawn_info["error"] = str(e)
                return ToolResult(
                    tool_name="spawn_agent",
                    success=False,
                    message=f"Failed to spawn agent: {e}",
                    data=spawn_info,
                )

        return ToolResult(
            tool_name="spawn_agent",
            success=True,
            data={
                "task_id": task_id,
                "agent_type": agent_type,
                "task_type": task_type,
                "status": "spawned",
                "message": f"{agent_type} spawned for {task_type}. Results will arrive via Delta Bus.",
            },
            message=f"Spawned {agent_type} for {task_type} (task: {task_id})",
        )

    # =========================================================================
    # SESSION STATE TOOLS - Write to REAL SessionState
    # =========================================================================

    def _exec_update_persona(self, args: Dict[str, Any]) -> ToolResult:
        """Update persona in SessionState."""
        trait = args.get("trait", "")
        value = args.get("value", "")
        confidence = args.get("confidence", 0.8)

        if self.bridge:
            self.bridge.execute_tool_calls(
                [
                    {
                        "name": "update_persona",
                        "args": {
                            "preference_name": trait,
                            "preference_value": value,
                            "confidence": confidence,
                        },
                    }
                ]
            )

        return ToolResult(
            tool_name="update_persona",
            success=True,
            data={"trait": trait, "value": value},
            message=f"Learned: {trait} = {value}",
            wrote_to_session=True,
        )

    def _exec_add_belief(self, args: Dict[str, Any]) -> ToolResult:
        """Add belief to SessionState."""
        subject = args.get("subject", "")
        predicate = args.get("predicate", "")
        obj = args.get("object", "")
        category = args.get("category", "general")
        confidence = args.get("confidence", 0.9)

        if self.bridge:
            self.bridge.execute_tool_calls(
                [
                    {
                        "name": "add_belief",
                        "args": {
                            "subject": subject,
                            "predicate": predicate,
                            "object": obj,
                            "category": category,
                            "confidence": confidence,
                        },
                    }
                ]
            )

        return ToolResult(
            tool_name="add_belief",
            success=True,
            data={"subject": subject, "predicate": predicate, "object": obj},
            message=f"Recorded: {subject} {predicate} {obj}",
            wrote_to_session=True,
        )

    def _exec_update_emotion(self, args: Dict[str, Any]) -> ToolResult:
        """Update emotional state in SessionState."""
        state = args.get("state", "neutral")
        confidence = args.get("confidence", 0.8)

        if self.bridge:
            self.bridge.execute_tool_calls(
                [{"name": "update_emotion", "args": {"state": state, "confidence": confidence}}]
            )

        return ToolResult(
            tool_name="update_emotion",
            success=True,
            data={"state": state},
            message=f"Emotion updated: {state}",
            wrote_to_session=True,
        )

    # =========================================================================
    # TRAVEL TOOLS - Return mock data
    # =========================================================================

    def _exec_search_accommodations(self, args: Dict[str, Any]) -> ToolResult:
        """Search for accommodations - returns mock Sonoma results."""
        location = args.get("location", "Sonoma")
        budget = args.get("budget_per_night", 500)

        # Filter by budget
        results = [a for a in self._accommodations if a["price_per_night"] <= budget + 100]
        capped = results[:4]

        return ToolResult(
            tool_name="search_accommodations",
            success=True,
            data={"results": capped, "total_found": len(capped)},
            message=f"Found {len(capped)} accommodations in {location}",
        )

    def _exec_get_accommodation_details(self, args: Dict[str, Any]) -> ToolResult:
        """Get details for a specific accommodation."""
        name = args.get("name", "").lower()

        for a in self._accommodations:
            if name in a["name"].lower():
                return ToolResult(
                    tool_name="get_accommodation_details",
                    success=True,
                    data=a,
                    message=f"Details for {a['name']}",
                )

        return ToolResult(
            tool_name="get_accommodation_details",
            success=False,
            message=f"Accommodation not found: {name}",
        )

    def _exec_book_accommodation(self, args: Dict[str, Any]) -> ToolResult:
        """Book an accommodation - simulated."""
        name = args.get("name", "")
        check_in = args.get("check_in_date", "")
        nights = args.get("nights", 2)
        guests = args.get("guests", 2)

        # Validate name -- the LLM MUST specify which property to book
        if not name:
            avail = [a["name"] for a in self._accommodations]
            return ToolResult(
                tool_name="book_accommodation",
                success=False,
                data={"available_properties": avail},
                message=f"Missing required parameter 'name'. Available properties: {', '.join(avail)}",
            )

        # Check if accommodation is already booked via plan controller
        if self._plan_controller:
            accom_item = self._plan_controller.plan.items.get("accommodation")
            if accom_item and accom_item.is_locked:
                return ToolResult(
                    tool_name="book_accommodation",
                    success=False,
                    data={"existing_confirmation": accom_item.confirmation},
                    message=f"Accommodation already booked! Existing reservation: {accom_item.name} (Confirmation: {accom_item.confirmation}). Use modify_booking to change.",
                )

        # Find matching property
        matched = None
        for a in self._accommodations:
            if name.lower() in a["name"].lower():
                matched = a
                break
        if not matched:
            avail = [a["name"] for a in self._accommodations]
            return ToolResult(
                tool_name="book_accommodation",
                success=False,
                data={"available_properties": avail},
                message=f"Property '{name}' not found. Available: {', '.join(avail)}",
            )

        price = matched["price_per_night"]
        booking = {
            "confirmation_number": f"ACM-{random.randint(100000, 999999)}",
            "property": matched["name"],
            "check_in": check_in,
            "check_out": f"{nights} nights after {check_in}",
            "guests": guests,
            "status": "confirmed",
            "booked_at": datetime.now().isoformat(),
        }
        self._bookings.append(booking)

        return ToolResult(
            tool_name="book_accommodation",
            success=True,
            data={
                "confirmation": booking["confirmation_number"],
                "property": matched["name"],
                "check_in": check_in,
                "nights": nights,
                "total_cost": price * nights,
            },
            message=f"Booked {matched['name']} for {nights} nights (${price * nights} total)",
        )

    def _exec_search_restaurants(self, args: Dict[str, Any]) -> ToolResult:
        """Search for restaurants - returns mock Sonoma results."""
        location = args.get("location", "Sonoma")
        cuisine_raw = args.get("cuisine") or ""
        cuisine = cuisine_raw.lower()
        avoid = [i.lower() for i in (args.get("avoid_ingredients") or [])]

        results = self._restaurants.copy()

        # Filter by cuisine
        if cuisine:
            results = [r for r in results if cuisine in r["cuisine"].lower()]

        # Filter by allergies using structured contains_allergens list
        # (not substring matching on allergen_warning text)
        if avoid:
            results = [
                r
                for r in results
                if not any(a in [x.lower() for x in r.get("contains_allergens", [])] for a in avoid)
            ]

        capped = results[:4]

        return ToolResult(
            tool_name="search_restaurants",
            success=True,
            data={"results": capped, "total_found": len(capped)},
            message=f"Found {len(capped)} restaurants in {location}"
            + (f" avoiding {', '.join(avoid)}" if avoid else ""),
        )

    def _exec_get_restaurant_details(self, args: Dict[str, Any]) -> ToolResult:
        """Get details for a specific restaurant."""
        name = args.get("name", "").lower()
        query = args.get("query", "")

        for r in self._restaurants:
            if name in r["name"].lower():
                data = r.copy()
                if query == "birthday_specials":
                    data["birthday_specials"] = (
                        "Complimentary dessert with 'Happy Birthday' written in chocolate. Can arrange for a special table with balloons."
                    )
                return ToolResult(
                    tool_name="get_restaurant_details",
                    success=True,
                    data=data,
                    message=f"Details for {r['name']}",
                )

        return ToolResult(
            tool_name="get_restaurant_details",
            success=False,
            message=f"Restaurant not found: {name}",
        )

    def _exec_book_restaurant(self, args: Dict[str, Any]) -> ToolResult:
        """Book a restaurant reservation - simulated."""
        name = args.get("restaurant_name", "")
        date = args.get("date", "")
        time_slot = args.get("time", "")
        party_size = args.get("party_size", 2)
        special = args.get("special_requests", [])

        # Check if restaurant is already booked via plan controller
        if self._plan_controller:
            dinner_item = self._plan_controller.plan.items.get("dinner")
            if dinner_item and dinner_item.is_locked:
                return ToolResult(
                    tool_name="book_restaurant",
                    success=False,
                    data={"existing_confirmation": dinner_item.confirmation},
                    message=f"Restaurant already booked! Existing reservation: {dinner_item.name} (Confirmation: {dinner_item.confirmation}). Use modify_booking to change.",
                )

        booking = {
            "confirmation_number": f"RST-{random.randint(100000, 999999)}",
            "restaurant": name,
            "date": date,
            "time": time_slot,
            "party_size": party_size,
            "special_requests": special,
            "status": "confirmed",
        }
        self._bookings.append(booking)

        return ToolResult(
            tool_name="book_restaurant",
            success=True,
            data=booking,
            message=f"Reserved table at {name} for {party_size} on {date} at {time_slot}",
        )

    def _exec_plan_route(self, args: Dict[str, Any]) -> ToolResult:
        """Plan a driving route - simulated."""
        origin = args.get("origin", "")
        destination = args.get("destination", "")
        preference = args.get("preference", "fastest")

        routes = {
            "fastest": {"duration": "1 hour 15 minutes", "distance": "52 miles", "via": "US-101 N"},
            "scenic": {
                "duration": "1 hour 45 minutes",
                "distance": "58 miles",
                "via": "CA-1 N (Pacific Coast Highway)",
            },
        }

        route = routes.get(preference, routes["fastest"])
        route["origin"] = origin
        route["destination"] = destination
        route["stops"] = (
            ["Petaluma (coffee stop)", "Sonoma Plaza (arrival)"] if preference == "scenic" else []
        )

        return ToolResult(
            tool_name="plan_route",
            success=True,
            data=route,
            message=f"Route planned: {route['duration']} via {route['via']}",
        )

    def _exec_search_activities(self, args: Dict[str, Any]) -> ToolResult:
        """Search for activities - returns mock results."""
        location = args.get("location", "Sonoma")
        category = args.get("category", "")

        results = self._activities.copy()
        if category:
            results = [a for a in results if category.lower() in a.get("category", "").lower()]
        capped = results[:5]

        return ToolResult(
            tool_name="search_activities",
            success=True,
            data={"results": capped, "total_found": len(capped)},
            message=f"Found {len(capped)} activities in {location}",
        )

    def _exec_book_spa_service(self, args: Dict[str, Any]) -> ToolResult:
        """Book a spa service - simulated."""
        location = args.get("location", "")
        service = args.get("service", "massage")
        date = args.get("date", "")
        time_slot = args.get("time", "")
        guests = args.get("guests", 1)

        # Check if spa is already booked via plan controller
        if self._plan_controller:
            spa_item = self._plan_controller.plan.items.get("spa")
            if spa_item and spa_item.is_locked:
                return ToolResult(
                    tool_name="book_spa_service",
                    success=False,
                    data={"existing_confirmation": spa_item.confirmation},
                    message=f"Spa already booked! Existing reservation: {spa_item.name} (Confirmation: {spa_item.confirmation}). Use modify_booking to change.",
                )

        prices = {
            "massage": 150,
            "couples_massage": 280,
            "facial": 120,
            "body_treatment": 175,
            "package": 350,
        }

        booking = {
            "confirmation_number": f"SPA-{random.randint(100000, 999999)}",
            "location": location,
            "service": service,
            "date": date,
            "time": time_slot,
            "guests": guests,
            "price": prices.get(service, 150) * guests,
            "status": "confirmed",
        }
        self._bookings.append(booking)

        return ToolResult(
            tool_name="book_spa_service",
            success=True,
            data=booking,
            message=f"Booked {service} at {location} for {date} at {time_slot} (${booking['price']})",
        )

    # =========================================================================
    # FAMILY TOOLS
    # =========================================================================

    def _exec_send_family_message(self, args: Dict[str, Any]) -> ToolResult:
        """Send a message to a family member - simulated."""
        to = args.get("to", "")
        subject = args.get("subject", "")
        content = args.get("content", "")
        priority = args.get("priority", "normal")

        msg = {
            "id": f"MSG-{random.randint(10000, 99999)}",
            "to": to,
            "subject": subject,
            "content": content,
            "priority": priority,
            "sent_at": datetime.now().isoformat(),
            "status": "delivered",
        }
        self._messages_sent.append(msg)

        return ToolResult(
            tool_name="send_family_message",
            success=True,
            data=msg,
            message=f"Message sent to {to}: '{subject}'",
        )

    def _exec_schedule_family_checkin(self, args: Dict[str, Any]) -> ToolResult:
        """Schedule a family check-in - simulated."""
        target = args.get("target", "")
        when = args.get("datetime", "")
        message = args.get("message", "")

        checkin = {
            "id": f"CHK-{random.randint(10000, 99999)}",
            "target": target,
            "scheduled_for": when,
            "message": message,
            "status": "scheduled",
        }
        self._reminders.append(checkin)

        return ToolResult(
            tool_name="schedule_family_checkin",
            success=True,
            data=checkin,
            message=f"Check-in scheduled with {target} for {when}",
        )

    def _exec_get_family_member_info(self, args: Dict[str, Any]) -> ToolResult:
        """Get family member info from beliefs - queries SessionState."""
        name = args.get("name", "")

        # Would query SessionState beliefs about this person
        # For demo, return mock data
        info = {
            "Emma": {"age": 16, "relation": "daughter", "can_babysit": True},
            "Jake": {"age": 12, "relation": "son", "needs_supervision": True},
            "Mike": {"age": 49, "relation": "husband", "allergies": ["shellfish"]},
        }

        if name in info:
            return ToolResult(
                tool_name="get_family_member_info",
                success=True,
                data=info[name],
                message=f"Info for {name}",
            )

        return ToolResult(
            tool_name="get_family_member_info",
            success=False,
            message=f"No info found for {name}",
        )

    # =========================================================================
    # CALENDAR TOOLS
    # =========================================================================

    def _exec_create_calendar_event(self, args: Dict[str, Any]) -> ToolResult:
        """Create a calendar event - simulated."""
        title = args.get("title", "")
        start = args.get("start", "")
        end = args.get("end", "")
        location = args.get("location", "")

        event = {
            "id": f"EVT-{random.randint(10000, 99999)}",
            "title": title,
            "start": start,
            "end": end,
            "location": location,
            "notes": args.get("notes", ""),
            "visibility": args.get("visibility", "default"),
            "created_at": datetime.now().isoformat(),
        }
        self._calendar_events.append(event)

        return ToolResult(
            tool_name="create_calendar_event",
            success=True,
            data=event,
            message=f"Created event: {title} on {start}",
        )

    def _exec_schedule_reminder(self, args: Dict[str, Any]) -> ToolResult:
        """Schedule a reminder - simulated."""
        message = args.get("message", "")
        when = args.get("datetime", "")
        recipient = args.get("recipient", "user")

        reminder = {
            "id": f"REM-{random.randint(10000, 99999)}",
            "message": message,
            "scheduled_for": when,
            "recipient": recipient,
            "repeat": args.get("repeat", "none"),
            "status": "scheduled",
        }
        self._reminders.append(reminder)

        return ToolResult(
            tool_name="schedule_reminder",
            success=True,
            data=reminder,
            message=f"Reminder scheduled for {when}: {message[:50]}...",
        )

    def _exec_generate_trip_summary(self, args: Dict[str, Any]) -> ToolResult:
        """Generate a summary of all trip bookings."""
        fmt = args.get("format", "detailed")
        include_costs = args.get("include_costs", True)

        total_cost = sum(b.get("total_cost", b.get("price", 0)) for b in self._bookings)

        summary = {
            "bookings": self._bookings,
            "total_bookings": len(self._bookings),
            "messages_sent": len(self._messages_sent),
            "events_created": len(self._calendar_events),
            "reminders_set": len(self._reminders),
        }

        if include_costs:
            summary["estimated_total_cost"] = total_cost

        return ToolResult(
            tool_name="generate_trip_summary",
            success=True,
            data=summary,
            message=f"Trip summary: {len(self._bookings)} bookings, ${total_cost} estimated total",
        )

    # =========================================================================
    # BACKGROUND MONITOR TOOLS
    # =========================================================================

    def _exec_start_background_monitor(self, args: Dict[str, Any]) -> ToolResult:
        """Start a background monitor - simulated."""
        monitor_type = args.get("monitor_type", "weather")
        target = args.get("target", "")
        dates = args.get("dates", [])
        interval = args.get("check_interval_minutes", 60)

        monitor_id = f"MON-{monitor_type[:3].upper()}-{random.randint(1000, 9999)}"

        monitor = BackgroundMonitor(
            monitor_id=monitor_id,
            monitor_type=monitor_type,
            target=target,
            dates=dates,
            started_at=time.time(),
            check_interval=interval,
        )
        self._monitors[monitor_id] = monitor

        return ToolResult(
            tool_name="start_background_monitor",
            success=True,
            data={
                "monitor_id": monitor_id,
                "type": monitor_type,
                "target": target,
                "status": "active",
            },
            message=f"Started {monitor_type} monitor for {target} (ID: {monitor_id})",
        )

    def _exec_stop_background_monitor(self, args: Dict[str, Any]) -> ToolResult:
        """Stop a background monitor."""
        monitor_id = args.get("monitor_id", "")

        if monitor_id in self._monitors:
            del self._monitors[monitor_id]
            return ToolResult(
                tool_name="stop_background_monitor",
                success=True,
                data={"monitor_id": monitor_id, "status": "stopped"},
                message=f"Stopped monitor {monitor_id}",
            )

        return ToolResult(
            tool_name="stop_background_monitor",
            success=False,
            message=f"Monitor not found: {monitor_id}",
        )

    def _exec_list_active_monitors(self, args: Dict[str, Any]) -> ToolResult:
        """List all active monitors."""
        monitors = [
            {
                "id": m.monitor_id,
                "type": m.monitor_type,
                "target": m.target,
                "running_minutes": int((time.time() - m.started_at) / 60),
            }
            for m in self._monitors.values()
        ]

        return ToolResult(
            tool_name="list_active_monitors",
            success=True,
            data={"monitors": monitors, "count": len(monitors)},
            message=f"{len(monitors)} active monitors",
        )

    # =========================================================================
    # MOCK DATA INITIALIZATION
    # =========================================================================

    def _init_accommodations(self) -> List[Dict[str, Any]]:
        """Initialize mock Sonoma accommodations."""
        return [
            {
                "name": "Vineyard Inn",
                "type": "boutique_hotel",
                "location": "Sonoma",
                "price_per_night": 299,
                "rating": 4.8,
                "amenities": ["wifi", "breakfast", "spa", "wine_tasting", "pool"],
                "description": "Charming boutique hotel nestled among the vineyards with stunning views",
                "special_features": [
                    "Complimentary wine hour",
                    "Farm-to-table breakfast",
                    "Couples spa packages",
                ],
                "available": True,
            },
            {
                "name": "Sonoma Valley Lodge",
                "type": "resort",
                "location": "Sonoma",
                "price_per_night": 389,
                "rating": 4.6,
                "amenities": ["wifi", "breakfast", "pool", "fitness", "restaurant"],
                "description": "Full-service resort with excellent dining and pool area",
                "special_features": ["On-site fine dining", "Heated pool year-round"],
                "available": True,
            },
            {
                "name": "The Cottage at Glen Ellen",
                "type": "bnb",
                "location": "Glen Ellen, Sonoma",
                "price_per_night": 249,
                "rating": 4.9,
                "amenities": ["wifi", "breakfast", "garden", "fireplace"],
                "description": "Cozy private cottage with romantic garden setting",
                "special_features": [
                    "Private hot tub",
                    "Homemade breakfast",
                    "Walking distance to tasting rooms",
                ],
                "available": True,
            },
            {
                "name": "MacArthur Place",
                "type": "luxury_hotel",
                "location": "Sonoma",
                "price_per_night": 475,
                "rating": 4.7,
                "amenities": ["wifi", "spa", "pool", "fine_dining", "gardens"],
                "description": "Historic luxury estate with world-class spa",
                "special_features": [
                    "Award-winning spa",
                    "Beautiful gardens",
                    "Michelin-quality restaurant",
                ],
                "available": True,
            },
        ]

    def _init_restaurants(self) -> List[Dict[str, Any]]:
        """Initialize mock Sonoma restaurants."""
        return [
            {
                "name": "Della Santina's",
                "cuisine": "Italian",
                "location": "Sonoma Plaza",
                "price_range": "$$$",
                "rating": 4.7,
                "description": "Classic Tuscan cuisine with homemade pasta and warm ambiance",
                "specialties": ["Handmade pasta", "Veal piccata", "Tiramisu"],
                "allergen_warning": "Menu clearly marks allergens. Can accommodate shellfish allergies.",
                "contains_allergens": [],
                "reservations": "Recommended",
            },
            {
                "name": "The Girl & The Fig",
                "cuisine": "French Provincial",
                "location": "Sonoma Plaza",
                "price_range": "$$$",
                "rating": 4.8,
                "description": "Farm-to-table French cuisine with fig-themed dishes",
                "specialties": ["Duck confit", "Fig salad", "Cheese board"],
                "allergen_warning": "Some dishes contain shellfish. Ask server.",
                "contains_allergens": ["shellfish"],
                "reservations": "Required",
            },
            {
                "name": "LaSalette",
                "cuisine": "Portuguese",
                "location": "Sonoma",
                "price_range": "$$$",
                "rating": 4.6,
                "description": "Unique Portuguese cuisine with Sonoma wine pairings",
                "specialties": ["Bacalhau", "Pork and clams", "Pasteis de nata"],
                "allergen_warning": "Many dishes contain shellfish",
                "contains_allergens": ["shellfish"],
                "reservations": "Recommended",
            },
            {
                "name": "Oso Sonoma",
                "cuisine": "Modern American",
                "location": "Sonoma Plaza",
                "price_range": "$$",
                "rating": 4.5,
                "description": "Casual upscale with seasonal local ingredients",
                "specialties": ["Wood-fired pizzas", "Seasonal salads", "Local wines"],
                "allergen_warning": "Shellfish-free options available",
                "contains_allergens": [],
                "reservations": "Walk-ins welcome",
            },
            {
                "name": "Cafe La Haye",
                "cuisine": "California",
                "location": "East Napa Street",
                "price_range": "$$$$",
                "rating": 4.9,
                "description": "Intimate fine dining with exceptional tasting menus",
                "specialties": ["Tasting menu", "Wine pairings", "Seasonal specials"],
                "allergen_warning": "Can accommodate all allergies with advance notice",
                "contains_allergens": [],
                "reservations": "Essential",
            },
        ]

    def _init_activities(self) -> List[Dict[str, Any]]:
        """Initialize mock Sonoma activities."""
        return [
            {
                "name": "Wine Country Balloon Ride",
                "category": "adventure",
                "duration": "3-4 hours",
                "price": 275,
                "description": "Sunrise hot air balloon ride over Sonoma vineyards with champagne toast",
                "best_for": "romantic, special occasion",
            },
            {
                "name": "Sonoma Plaza Walking Tour",
                "category": "culture",
                "duration": "2 hours",
                "price": 35,
                "description": "Guided historical walking tour of downtown Sonoma",
                "best_for": "history buffs, casual exploration",
            },
            {
                "name": "Couples Wine Blending Experience",
                "category": "food_wine",
                "duration": "2-3 hours",
                "price": 150,
                "description": "Create your own custom wine blend together at a boutique winery",
                "best_for": "romantic, wine lovers",
            },
            {
                "name": "Jack London State Park Hike",
                "category": "nature",
                "duration": "2-4 hours",
                "price": 10,
                "description": "Beautiful trails through redwoods and historic ranch lands",
                "best_for": "nature lovers, active couples",
            },
            {
                "name": "Sonoma Spa Day",
                "category": "relaxation",
                "duration": "half-day",
                "price": 350,
                "description": "Full spa experience with massage, facial, and hot springs",
                "best_for": "relaxation, special treat",
            },
            {
                "name": "Sunset Vineyard Picnic",
                "category": "romantic",
                "duration": "2-3 hours",
                "price": 125,
                "description": "Catered gourmet picnic among the vines at sunset",
                "best_for": "romantic, special occasion",
            },
        ]
