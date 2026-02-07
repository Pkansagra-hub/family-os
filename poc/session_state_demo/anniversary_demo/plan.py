"""
Canonical Plan Object
=====================

THE single source of truth for plan state.

Rule: If it's in the plan, the LLM cannot question it.

This is not a dashboard - it's a CONTROLLER.
- Locked items are FACTS, not suggestions
- Pending items drive behavior
- Completion pressure biases toward closing loops
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from poc.session_state_demo.bridge import SessionLLMBridge

logger = logging.getLogger(__name__)


class ItemStatus(Enum):
    """Status of a plan item."""

    PENDING = "pending"  # Not started
    IN_PROGRESS = "in_progress"  # Being worked on (searching)
    SELECTED = "selected"  # User chose an option, ready to book
    BOOKED = "booked"  # Confirmed - LOCKED
    COMPLETED = "completed"  # Done - LOCKED
    CANCELLED = "cancelled"  # Explicitly cancelled


@dataclass
class PlanItem:
    """A single item in the plan."""

    category: str  # accommodation, dinner, activity, spa, etc.
    name: Optional[str] = None
    status: ItemStatus = ItemStatus.PENDING
    confirmation: Optional[str] = None
    datetime_str: Optional[str] = None  # ISO format
    details: Dict[str, Any] = field(default_factory=dict)
    locked_at: Optional[str] = None  # When this became a fact

    @property
    def is_locked(self) -> bool:
        """Locked items are FACTS - LLM cannot question them."""
        return self.status in (ItemStatus.BOOKED, ItemStatus.COMPLETED, ItemStatus.CANCELLED)

    def lock(self, status: ItemStatus = ItemStatus.BOOKED) -> None:
        """Lock this item as a fact."""
        self.status = status
        self.locked_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "name": self.name,
            "status": self.status.value,
            "confirmation": self.confirmation,
            "datetime": self.datetime_str,
            "details": self.details,
            "locked_at": self.locked_at,
            "is_locked": self.is_locked,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlanItem":
        return cls(
            category=data["category"],
            name=data.get("name"),
            status=ItemStatus(data.get("status", "pending")),
            confirmation=data.get("confirmation"),
            datetime_str=data.get("datetime"),
            details=data.get("details", {}),
            locked_at=data.get("locked_at"),
        )


@dataclass
class CanonicalPlan:
    """
    THE authoritative plan state.

    Rule: If it's here and locked, the LLM MUST treat it as fact.
    """

    # Goal
    goal: str = ""

    # Resolved context (LOCKED - never ask again)
    location: Optional[str] = None
    start_date: Optional[str] = None  # ISO format
    end_date: Optional[str] = None
    party_size: int = 2
    budget_total: Optional[float] = None

    # Plan items
    items: Dict[str, PlanItem] = field(default_factory=dict)

    # Pending actions (drives behavior)
    pending_actions: List[str] = field(default_factory=list)

    # Completion tracking
    total_items: int = 0
    completed_items: int = 0

    @property
    def completion_percent(self) -> float:
        """How much of the plan is done."""
        if self.total_items == 0:
            return 0.0
        return (self.completed_items / self.total_items) * 100

    @property
    def locked_facts(self) -> Dict[str, Any]:
        """All facts that the LLM must not question."""
        facts = {}

        if self.location:
            facts["location"] = self.location
        if self.start_date:
            facts["start_date"] = self.start_date
        if self.end_date:
            facts["end_date"] = self.end_date
        if self.budget_total:
            facts["budget"] = self.budget_total

        for key, item in self.items.items():
            if item.is_locked:
                facts[f"{item.category}_{key}"] = {
                    "name": item.name,
                    "status": item.status.value,
                    "confirmation": item.confirmation,
                }

        return facts

    @property
    def open_items(self) -> List[PlanItem]:
        """Items that still need work."""
        return [item for item in self.items.values() if not item.is_locked]

    def add_item(self, key: str, item: PlanItem) -> None:
        """Add or update a plan item."""
        self.items[key] = item
        self._update_counts()

    def lock_item(self, key: str, confirmation: Optional[str] = None) -> bool:
        """Lock an item as a fact after booking/completion."""
        if key in self.items:
            item = self.items[key]
            item.lock()
            if confirmation:
                item.confirmation = confirmation
            self._update_counts()
            logger.info(f"Plan item LOCKED: {key} -> {item.status.value}")
            return True
        return False

    def lock_context(
        self,
        location: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        budget: Optional[float] = None,
    ) -> None:
        """Lock resolved context as facts."""
        if location:
            self.location = location
            logger.info(f"LOCKED location: {location}")
        if start_date:
            self.start_date = start_date
            logger.info(f"LOCKED start_date: {start_date}")
        if end_date:
            self.end_date = end_date
            logger.info(f"LOCKED end_date: {end_date}")
        if budget:
            self.budget_total = budget
            logger.info(f"LOCKED budget: {budget}")

    def _update_counts(self) -> None:
        """Update completion counts."""
        self.total_items = len(self.items)
        self.completed_items = sum(1 for item in self.items.values() if item.is_locked)

    def add_pending_action(self, action: str) -> None:
        """Add a pending action to drive behavior."""
        if action not in self.pending_actions:
            self.pending_actions.append(action)

    def remove_pending_action(self, action: str) -> None:
        """Remove a completed pending action."""
        if action in self.pending_actions:
            self.pending_actions.remove(action)

    def get_prompt_context(self) -> str:
        """
        Generate context for LLM prompt.

        This is AUTHORITATIVE - the LLM must respect these facts.
        """
        lines = ["="*60]
        lines.append("CANONICAL PLAN STATE (AUTHORITATIVE - READ CAREFULLY)")
        lines.append("="*60)

        if self.goal:
            lines.append(f"\nGOAL: {self.goal}")

        # Locked context
        lines.append("\nLOCKED FACTS (these are TRUE, do not re-ask):")
        if self.location:
            lines.append(f"  - Location: {self.location} [LOCKED]")
        if self.start_date:
            lines.append(f"  - Start: {self.start_date} [LOCKED]")
        if self.end_date:
            lines.append(f"  - End: {self.end_date} [LOCKED]")
        if self.budget_total:
            lines.append(f"  - Budget: ${self.budget_total} [LOCKED]")

        # Locked items with STRONG warnings
        locked = [item for item in self.items.values() if item.is_locked]
        if locked:
            lines.append("\n" + "!"*60)
            lines.append("CONFIRMED BOOKINGS - ALREADY DONE - DO NOT BOOK AGAIN:")
            lines.append("!"*60)
            for item in locked:
                conf = f" (Conf: {item.confirmation})" if item.confirmation else ""
                tool_name = f"book_{item.category.replace(' ', '_').lower()}"
                lines.append(f"  - {item.category}: {item.name} {conf}")
                lines.append(f"    >> DO NOT call {tool_name}() - ALREADY BOOKED!")

        # Selected items (user chose, ready to book)
        selected = [item for item in self.items.values() if item.status == ItemStatus.SELECTED]
        if selected:
            lines.append(
                "\nSELECTED (user chose these - ready to book, DO NOT ask what they want):"
            )
            for item in selected:
                lines.append(
                    f"  - {item.category}: {item.name} [SELECTED - book when user confirms]"
                )

        # Pending items (still need selection)
        pending = [
            item
            for item in self.items.values()
            if item.status in (ItemStatus.PENDING, ItemStatus.IN_PROGRESS)
        ]
        if pending:
            lines.append("\nPENDING ITEMS (still need selection):")
            for item in pending:
                lines.append(f"  - {item.category}: {item.name or 'TBD'} [{item.status.value}]")

        # Pending actions
        if self.pending_actions:
            lines.append("\nPENDING ACTIONS (prioritize these):")
            for action in self.pending_actions:
                lines.append(f"  - {action}")

        # Completion pressure
        lines.append("\n=== COMPLETION PRESSURE ===")
        lines.append(
            f"PROGRESS: {self.completion_percent:.0f}% complete ({self.completed_items}/{self.total_items} items)"
        )

        if self.completion_percent == 0:
            lines.append("STATUS: Just started - gather info and begin planning")
        elif self.completion_percent < 50:
            lines.append("STATUS: Early stage - focus on next actions, don't get distracted")
        elif self.completion_percent < 100:
            lines.append("STATUS: Home stretch - CLOSE remaining items, do not reopen closed ones")
        else:
            lines.append("STATUS: COMPLETE - confirm and wrap up")

        # Explicit behavioral directive
        if self.completion_percent < 100:
            lines.append("")
            lines.append("DIRECTIVE: Your PRIMARY goal is to move toward 100% completion.")
            lines.append("- DO NOT reopen locked items unless user explicitly requests changes")
            lines.append("- DO NOT ask about already-resolved context")
            lines.append("- FOCUS on the next pending action")

        # CRITICAL: Explicit list of blocked tool calls
        # Map categories to actual tool names
        category_to_tool = {
            "accommodation": "book_accommodation",
            "dinner": "book_restaurant",  # Tool is book_restaurant, not book_dinner
            "spa": "book_spa_service",    # Tool is book_spa_service, not book_spa
        }
        if locked:
            lines.append("\n" + "="*60)
            lines.append("BLOCKED TOOL CALLS (calling these will FAIL):")
            lines.append("="*60)
            for item in locked:
                tool_name = category_to_tool.get(item.category, f"book_{item.category}")
                lines.append(f"  X {tool_name}() -> BLOCKED (already booked as {item.name})")
                # Also add search tool as warning
                search_tool = tool_name.replace("book_", "search_").replace("_service", "s")
                if item.category == "dinner":
                    search_tool = "search_restaurants"
                lines.append(f"    (No need to call {search_tool} either - decision is final)")
            lines.append("")
            lines.append("IMPORTANT: If user mentions a locked item, CONFIRM it's already done.")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "location": self.location,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "party_size": self.party_size,
            "budget_total": self.budget_total,
            "items": {k: v.to_dict() for k, v in self.items.items()},
            "pending_actions": self.pending_actions,
            "completion_percent": self.completion_percent,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CanonicalPlan":
        plan = cls(
            goal=data.get("goal", ""),
            location=data.get("location"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            party_size=data.get("party_size", 2),
            budget_total=data.get("budget_total"),
            pending_actions=data.get("pending_actions", []),
        )
        for key, item_data in data.get("items", {}).items():
            plan.items[key] = PlanItem.from_dict(item_data)
        plan._update_counts()
        return plan


class PlanController:
    """
    Controls the canonical plan.

    - Listens to tool executions
    - Locks items when booked
    - Provides authoritative context to LLM
    """

    def __init__(self, bridge: Optional["SessionLLMBridge"] = None):
        self._bridge = bridge
        self._plan = CanonicalPlan()

    @property
    def plan(self) -> CanonicalPlan:
        return self._plan

    def initialize_plan(
        self,
        goal: str,
        location: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        budget: Optional[float] = None,
    ) -> None:
        """Initialize the plan with a goal and optional context."""
        self._plan.goal = goal
        if location:
            self._plan.location = location
        if start_date:
            self._plan.start_date = start_date
        if end_date:
            self._plan.end_date = end_date
        if budget:
            self._plan.budget_total = budget

        # Default plan items for anniversary demo
        self._plan.add_item("accommodation", PlanItem(category="accommodation"))
        self._plan.add_item("dinner", PlanItem(category="dinner"))
        self._plan.add_item("spa", PlanItem(category="spa"))

        logger.info(f"Plan initialized: {goal}")

    def on_tool_result(self, tool_name: str, args: Dict[str, Any], result: Any) -> None:
        """
        Handle tool execution result.

        This is where we CLOSE BRANCHES - tool outputs become facts.
        """
        # Booking tools lock their items
        if tool_name == "book_accommodation":
            self._handle_accommodation_booking(args, result)
        elif tool_name == "book_restaurant":
            self._handle_restaurant_booking(args, result)
        elif tool_name == "book_spa_service":
            self._handle_spa_booking(args, result)

        # Selection tools mark items as selected (ready to book)
        elif tool_name == "get_accommodation_details":
            self._handle_accommodation_selection(args, result)

        # Context resolution locks context
        elif tool_name == "add_belief":
            self._handle_belief(args)
        elif tool_name == "update_persona":
            self._handle_persona(args)

    def select_accommodation(self, name: str, details: Optional[Dict] = None) -> None:
        """Mark accommodation as SELECTED (user chose it, ready to book)."""
        item = self._plan.items.get("accommodation")
        if item:
            item.name = name
            item.status = ItemStatus.SELECTED
            if details:
                item.details.update(details)
            logger.info(f"Accommodation SELECTED: {name}")

    def _handle_accommodation_selection(self, args: Dict, result: Any) -> None:
        """Handle when user asks about a specific accommodation (they selected it)."""
        name = args.get("name")
        if name:
            self.select_accommodation(name)

    def _handle_accommodation_booking(self, args: Dict, result: Any) -> None:
        """Lock accommodation after booking."""
        item = self._plan.items.get("accommodation")
        if item:
            item.name = args.get("name") or args.get("property", "Unknown")
            item.datetime_str = args.get("check_in_date")
            item.details = {
                "guests": args.get("guests"),
                "nights": args.get("nights"),
                "location": args.get("location"),
            }

            # Extract confirmation from result
            confirmation = None
            if hasattr(result, "data"):
                confirmation = result.data.get("confirmation")
            elif isinstance(result, dict):
                confirmation = result.get("confirmation")

            # Use lock_item to ensure counts update
            self._plan.lock_item("accommodation", confirmation=confirmation)

            # Also lock location if not already
            if args.get("location") and not self._plan.location:
                self._plan.lock_context(location=args.get("location"))

            self._plan.remove_pending_action("book_accommodation")
            logger.info(f"BRANCH CLOSED: accommodation -> {item.name} ({confirmation})")

    def _handle_restaurant_booking(self, args: Dict, result: Any) -> None:
        """Lock restaurant after booking."""
        item = self._plan.items.get("dinner")
        if not item:
            item = PlanItem(category="dinner")
            self._plan.add_item("dinner", item)

        item.name = args.get("restaurant_name") or args.get("name", "Unknown")
        item.datetime_str = (
            args.get("datetime") or f"{args.get('date')}T{args.get('time', '19:00')}"
        )
        item.details = {
            "party_size": args.get("party_size"),
            "special_requests": args.get("special_requests"),
        }

        confirmation = None
        if hasattr(result, "data"):
            confirmation = result.data.get("confirmation")
        elif isinstance(result, dict):
            confirmation = result.get("confirmation")

        # Use lock_item to ensure counts update
        self._plan.lock_item("dinner", confirmation=confirmation)

        self._plan.remove_pending_action("book_restaurant")
        logger.info(f"BRANCH CLOSED: dinner -> {item.name} ({confirmation})")

    def _handle_spa_booking(self, args: Dict, result: Any) -> None:
        """Lock spa after booking."""
        item = self._plan.items.get("spa")
        if not item:
            item = PlanItem(category="spa")
            self._plan.add_item("spa", item)

        item.name = args.get("service_type", "Couples massage")
        item.datetime_str = f"{args.get('date')}T{args.get('time', '14:00')}"

        confirmation = None
        if hasattr(result, "data"):
            confirmation = result.data.get("confirmation")
        elif isinstance(result, dict):
            confirmation = result.get("confirmation")

        # Use lock_item to ensure counts update
        self._plan.lock_item("spa", confirmation=confirmation)

        self._plan.remove_pending_action("book_spa")
        logger.info(f"BRANCH CLOSED: spa -> {item.name} ({confirmation})")

    def _handle_belief(self, args: Dict) -> None:
        """Extract context from beliefs and lock if appropriate."""
        subject = args.get("subject", "").lower()
        predicate = args.get("predicate", "").lower()
        obj = args.get("object", "")

        # Location mentions
        if "sonoma" in obj.lower() or "napa" in obj.lower():
            if not self._plan.location:
                self._plan.lock_context(location=obj)

        # Date mentions
        if "date" in predicate or "saturday" in obj.lower():
            if not self._plan.start_date and any(c.isdigit() for c in obj):
                self._plan.lock_context(start_date=obj)

    def _handle_persona(self, args: Dict) -> None:
        """Extract preferences and lock context."""
        trait = args.get("trait", "").lower()
        value = args.get("value", "")

        if "wine" in trait or "region" in trait or "location" in trait:
            if "sonoma" in value.lower() and not self._plan.location:
                self._plan.lock_context(location="Sonoma")
            elif "napa" in value.lower() and not self._plan.location:
                self._plan.lock_context(location="Napa")

    def get_prompt_context(self) -> str:
        """Get authoritative plan context for LLM prompt."""
        return self._plan.get_prompt_context()

    def save_to_session(self) -> None:
        """Persist plan to SessionState."""
        if self._bridge:
            try:
                # Store in meta section
                self._bridge.update_section("meta", {"canonical_plan": self._plan.to_dict()})
            except Exception as e:
                logger.warning(f"Failed to save plan to session: {e}")

    def load_from_session(self) -> bool:
        """Load plan from SessionState (for crash recovery)."""
        if not self._bridge:
            return False
        try:
            meta = self._bridge.get_section_data("meta")
            if "canonical_plan" in meta:
                self._plan = CanonicalPlan.from_dict(meta["canonical_plan"])
                logger.info(
                    f"Plan restored: {self._plan.goal} ({self._plan.completion_percent:.0f}% complete)"
                )
                return True
        except Exception as e:
            logger.warning(f"Failed to load plan from session: {e}")
        return False
