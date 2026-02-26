"""
Tool Schema Registry
====================

Central registry for all tool schemas with:
- Complete JSON Schema definitions
- Required vs optional parameter tracking
- Validation support
- Gap detection integration

This is the foundation for LLM-driven gap detection.
When the LLM attempts a tool call with missing required params,
the registry enables detection and clarification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set


class ParamType(Enum):
    """Parameter types for tool schemas."""

    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


@dataclass
class ParamSchema:
    """Schema for a single parameter."""

    name: str
    param_type: ParamType
    description: str
    required: bool = True
    default: Any = None
    enum: Optional[List[str]] = None
    items_type: Optional[ParamType] = None  # For arrays
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    pattern: Optional[str] = None  # Regex pattern for strings
    examples: List[Any] = field(default_factory=list)

    def to_json_schema(self) -> Dict[str, Any]:
        """Convert to JSON Schema format for LLM."""
        schema: Dict[str, Any] = {
            "type": self.param_type.value,
            "description": self.description,
        }

        if self.enum:
            schema["enum"] = self.enum

        if self.param_type == ParamType.ARRAY and self.items_type:
            schema["items"] = {"type": self.items_type.value}

        # NOTE: minimum/maximum/pattern/default not supported by Gemini function calling
        # They are kept in ParamSchema for validation but stripped from LLM schemas

        return schema


@dataclass
class ToolSchema:
    """Complete schema for a tool."""

    name: str
    description: str
    parameters: List[ParamSchema]
    category: str = "general"
    returns_description: str = ""
    execution_time_hint: str = "fast"  # fast, medium, slow
    can_fail: bool = True
    requires_confirmation: bool = False
    handler: Optional[Callable] = None

    @property
    def required_params(self) -> List[ParamSchema]:
        """Get all required parameters."""
        return [p for p in self.parameters if p.required]

    @property
    def optional_params(self) -> List[ParamSchema]:
        """Get all optional parameters."""
        return [p for p in self.parameters if not p.required]

    @property
    def required_param_names(self) -> Set[str]:
        """Get names of required parameters."""
        return {p.name for p in self.required_params}

    @property
    def all_param_names(self) -> Set[str]:
        """Get names of all parameters."""
        return {p.name for p in self.parameters}

    def to_json_schema(self) -> Dict[str, Any]:
        """Convert to JSON Schema format for LLM function calling."""
        properties = {}
        required = []

        for param in self.parameters:
            properties[param.name] = param.to_json_schema()
            if param.required:
                required.append(param.name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }

    def to_gemini_format(self) -> Dict[str, Any]:
        """Convert to Gemini function declaration format."""
        properties = {}
        required = []

        for param in self.parameters:
            properties[param.name] = param.to_json_schema()
            if param.required:
                required.append(param.name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }


@dataclass
class ValidationResult:
    """Result of parameter validation."""

    is_valid: bool
    missing_required: List[str] = field(default_factory=list)
    invalid_types: Dict[str, str] = field(default_factory=dict)  # param -> error
    unknown_params: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def needs_clarification(self) -> bool:
        """Check if clarification is needed."""
        return len(self.missing_required) > 0

    def get_clarification_context(self) -> Dict[str, Any]:
        """Get context for generating clarification question."""
        return {
            "missing_required": self.missing_required,
            "invalid_types": self.invalid_types,
            "param_count_missing": len(self.missing_required),
        }


class ToolRegistry:
    """
    Central registry for all tool schemas.

    Usage:
        registry = ToolRegistry()
        registry.register(search_accommodations_schema)

        # Validate a tool call
        result = registry.validate("search_accommodations", {"location": "Sonoma"})
        if result.needs_clarification:
            # Missing: check_in_date, nights
            pass

        # Get schema for LLM
        schemas = registry.get_all_schemas_for_llm()
    """

    def __init__(self):
        self._tools: Dict[str, ToolSchema] = {}
        self._categories: Dict[str, List[str]] = {}  # category -> tool names

    def register(self, schema: ToolSchema) -> None:
        """Register a tool schema."""
        self._tools[schema.name] = schema

        if schema.category not in self._categories:
            self._categories[schema.category] = []
        self._categories[schema.category].append(schema.name)

    def get(self, name: str) -> Optional[ToolSchema]:
        """Get a tool schema by name."""
        return self._tools.get(name)

    def get_by_category(self, category: str) -> List[ToolSchema]:
        """Get all tools in a category."""
        tool_names = self._categories.get(category, [])
        return [self._tools[name] for name in tool_names]

    def validate(self, tool_name: str, params: Dict[str, Any]) -> ValidationResult:
        """
        Validate parameters for a tool call.

        Returns ValidationResult with:
        - missing_required: List of required params not provided
        - invalid_types: Dict of param -> type error
        - unknown_params: List of params not in schema
        """
        schema = self.get(tool_name)
        if not schema:
            return ValidationResult(
                is_valid=False,
                warnings=[f"Unknown tool: {tool_name}"],
            )

        result = ValidationResult(is_valid=True)

        # Check for missing required params
        provided = set(params.keys())
        required = schema.required_param_names

        missing = required - provided
        if missing:
            result.is_valid = False
            result.missing_required = list(missing)

        # Check for unknown params
        all_known = schema.all_param_names
        unknown = provided - all_known
        if unknown:
            result.unknown_params = list(unknown)
            result.warnings.append(f"Unknown parameters: {unknown}")

        # Type validation (basic)
        for param_schema in schema.parameters:
            if param_schema.name in params:
                value = params[param_schema.name]
                type_error = self._validate_type(value, param_schema)
                if type_error:
                    result.is_valid = False
                    result.invalid_types[param_schema.name] = type_error

        return result

    def _validate_type(self, value: Any, param: ParamSchema) -> Optional[str]:
        """Validate a value against a parameter schema."""
        if value is None:
            if param.required:
                return "Value is required but got None"
            return None

        type_checks = {
            ParamType.STRING: lambda v: isinstance(v, str),
            ParamType.INTEGER: lambda v: isinstance(v, int) and not isinstance(v, bool),
            ParamType.NUMBER: lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            ParamType.BOOLEAN: lambda v: isinstance(v, bool),
            ParamType.ARRAY: lambda v: isinstance(v, list),
            ParamType.OBJECT: lambda v: isinstance(v, dict),
        }

        checker = type_checks.get(param.param_type)
        if checker and not checker(value):
            return f"Expected {param.param_type.value}, got {type(value).__name__}"

        # Enum validation
        if param.enum and value not in param.enum:
            return f"Value must be one of: {param.enum}"

        # Range validation
        if param.min_value is not None and isinstance(value, (int, float)):
            if value < param.min_value:
                return f"Value must be >= {param.min_value}"

        if param.max_value is not None and isinstance(value, (int, float)):
            if value > param.max_value:
                return f"Value must be <= {param.max_value}"

        return None

    def get_missing_param_descriptions(
        self, tool_name: str, missing_params: List[str]
    ) -> Dict[str, str]:
        """Get descriptions for missing parameters."""
        schema = self.get(tool_name)
        if not schema:
            return {}

        descriptions = {}
        for param in schema.parameters:
            if param.name in missing_params:
                descriptions[param.name] = param.description

        return descriptions

    def get_all_schemas_for_llm(self) -> List[Dict[str, Any]]:
        """Get all tool schemas in LLM-compatible format."""
        return [schema.to_json_schema() for schema in self._tools.values()]

    def get_gemini_function_declarations(self) -> List[Dict[str, Any]]:
        """Get all tool schemas in Gemini format."""
        return [schema.to_gemini_format() for schema in self._tools.values()]

    def get_tool_names(self) -> List[str]:
        """Get all registered tool names."""
        return list(self._tools.keys())

    def get_categories(self) -> List[str]:
        """Get all tool categories."""
        return list(self._categories.keys())

    def get_llm_declarations(self, tier: str) -> List[Dict[str, Any]]:
        """Return Gemini-compatible function-calling declarations filtered by tier.

        Tier filtering:
          LOW:    cognitive + essential functional tools (family, calendar, summary)
          MEDIUM: cognitive + search + booking + family + calendar tools
          HIGH:   all registered tools

        Each dict has ``name``, ``description``, ``parameters`` -- the shape
        Gemini ``tools=[{"function_declarations": [...]}]`` expects.
        """
        _COGNITIVE_TOOLS = frozenset(
            {
                "add_belief",
                "update_persona",
                "update_emotion",
                "acknowledge",
            }
        )
        _LOW_TOOLS = _COGNITIVE_TOOLS | frozenset(
            {
                "get_family_member_info",
                "send_family_message",
                "schedule_family_checkin",
                "generate_trip_summary",
                "search_accommodations",
                "search_restaurants",
            }
        )
        _MEDIUM_TOOLS = _LOW_TOOLS | frozenset(
            {
                "search_accommodations",
                "get_accommodation_details",
                "book_accommodation",
                "search_restaurants",
                "book_restaurant",
                "book_spa_service",
                "search_activities",
                "plan_route",
                "get_family_member_info",
                "send_family_message",
                "schedule_family_checkin",
                "create_calendar_event",
                "schedule_reminder",
                "generate_trip_summary",
            }
        )

        upper = tier.upper()
        if upper == "LOW":
            allowed = _LOW_TOOLS
        elif upper == "MEDIUM":
            allowed = _MEDIUM_TOOLS
        else:  # HIGH
            allowed = None  # all tools

        declarations = []
        for schema in sorted(self._tools.values(), key=lambda s: s.name):
            if allowed is None or schema.name in allowed:
                declarations.append(schema.to_gemini_format())
        return declarations

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


# =============================================================================
# PRE-DEFINED TOOL SCHEMAS FOR ANNIVERSARY DEMO
# =============================================================================


# =============================================================================
# TOOL CATEGORIES FOR VALIDATION
# =============================================================================

# Tools that have side effects and REQUIRE acknowledge() first
EFFECTFUL_TOOLS = {
    # Session state writes
    "update_persona",
    "add_belief",
    "update_emotion",
    # Bookings
    "book_accommodation",
    "book_restaurant",
    "book_spa_service",
    # Communications
    "send_family_message",
    "schedule_family_checkin",
    # Calendar
    "create_calendar_event",
    "schedule_reminder",
    # Background
    "start_background_monitor",
    "stop_background_monitor",
    # Agent spawning
    "spawn_agent",
    # Travel
    "plan_route",
    # Summary
    "generate_trip_summary",
}

# Tools that are read-only / query-only (no ACK required if called alone)
QUERY_ONLY_TOOLS = {
    "search_accommodations",
    "search_restaurants",
    "search_activities",
    "get_family_member_info",
    "list_active_monitors",
}

# All valid tools that can follow an ACK (for next_tool enum)
ALL_TOOL_NAMES = [
    "none",  # For pure ACK with text response
    # Session
    "update_persona",
    "add_belief",
    "update_emotion",
    # Travel search
    "search_accommodations",
    "search_restaurants",
    "search_activities",
    # Bookings
    "book_accommodation",
    "book_restaurant",
    "book_spa_service",
    # Family
    "send_family_message",
    "get_family_member_info",
    "schedule_family_checkin",
    # Calendar
    "create_calendar_event",
    "schedule_reminder",
    "generate_trip_summary",
    # Background
    "start_background_monitor",
    "stop_background_monitor",
    "list_active_monitors",
    # Travel
    "plan_route",
    # Agent
    "spawn_agent",
]


def create_demo_registry() -> ToolRegistry:
    """Create a registry with all demo tools pre-registered."""
    registry = ToolRegistry()

    # =========================================================================
    # ACKNOWLEDGMENT TOOL - MUST BE CALLED FIRST, BUNDLED WITH NEXT TOOL
    # =========================================================================

    registry.register(
        ToolSchema(
            name="acknowledge",
            description="""REQUIRED FIRST: Acknowledge user input before taking action.

RULES:
1. Call this BEFORE any effectful tool (booking, sending, creating, etc.)
2. MUST be bundled with the next tool in the SAME response
3. next_tool MUST match the actual tool you call next
4. Message must be SPECIFIC - no 'got it', 'understood', 'noted'

Example: acknowledge(ack_type='progress', message='Searching Sonoma hotels for Feb 7', next_tool='search_accommodations')
Then IMMEDIATELY call: search_accommodations(...)""",
            category="acknowledgment",
            parameters=[
                ParamSchema(
                    name="ack_type",
                    param_type=ParamType.STRING,
                    description="commit=state change happening, progress=work starting, closure=branch complete",
                    required=True,
                    enum=["commit", "progress", "closure"],
                ),
                ParamSchema(
                    name="message",
                    param_type=ParamType.STRING,
                    description="SPECIFIC acknowledgment. FORBIDDEN: 'got it', 'understood', 'noted', 'I see'. REQUIRED: actual object + action (e.g., 'Booking Della Santinas at 7pm')",
                    required=True,
                ),
                ParamSchema(
                    name="next_tool",
                    param_type=ParamType.STRING,
                    description="The EXACT tool name you will call immediately after this ACK. Use 'none' only for pure text responses.",
                    required=True,
                    enum=ALL_TOOL_NAMES,
                ),
            ],
        )
    )

    # =========================================================================
    # SESSION STATE TOOLS (from existing demo)
    # =========================================================================

    registry.register(
        ToolSchema(
            name="update_persona",
            description="Update a learned preference or trait about the user",
            category="session",
            parameters=[
                ParamSchema(
                    name="trait",
                    param_type=ParamType.STRING,
                    description="The trait or preference being learned (e.g., 'relaxation_preference', 'budget_flexibility')",
                    required=True,
                ),
                ParamSchema(
                    name="value",
                    param_type=ParamType.STRING,
                    description="The value of the trait (e.g., 'high', 'moderate', 'low')",
                    required=True,
                ),
                ParamSchema(
                    name="confidence",
                    param_type=ParamType.NUMBER,
                    description="Confidence level 0.0-1.0",
                    required=False,
                    default=0.8,
                    min_value=0.0,
                    max_value=1.0,
                ),
            ],
        )
    )

    registry.register(
        ToolSchema(
            name="add_belief",
            description="Record a fact or belief learned about the user or their context",
            category="session",
            parameters=[
                ParamSchema(
                    name="subject",
                    param_type=ParamType.STRING,
                    description="Who or what the belief is about (e.g., 'Mike', 'trip', 'user')",
                    required=True,
                ),
                ParamSchema(
                    name="predicate",
                    param_type=ParamType.STRING,
                    description="The relationship or property (e.g., 'has_allergy', 'prefers', 'age')",
                    required=True,
                ),
                ParamSchema(
                    name="object",
                    param_type=ParamType.STRING,
                    description="The value or target (e.g., 'shellfish', 'relaxation', '16')",
                    required=True,
                ),
                ParamSchema(
                    name="category",
                    param_type=ParamType.STRING,
                    description="Category for organization",
                    required=False,
                    default="general",
                    enum=["family", "health", "travel", "preferences", "general"],
                ),
                ParamSchema(
                    name="confidence",
                    param_type=ParamType.NUMBER,
                    description="Confidence level 0.0-1.0",
                    required=False,
                    default=0.9,
                    min_value=0.0,
                    max_value=1.0,
                ),
            ],
        )
    )

    registry.register(
        ToolSchema(
            name="update_emotion",
            description="Record the current emotional state of the conversation",
            category="session",
            parameters=[
                ParamSchema(
                    name="state",
                    param_type=ParamType.STRING,
                    description="The emotional state detected",
                    required=True,
                    enum=[
                        "happy",
                        "excited",
                        "grateful",
                        "anxious",
                        "stressed",
                        "neutral",
                        "frustrated",
                        "sad",
                    ],
                ),
                ParamSchema(
                    name="confidence",
                    param_type=ParamType.NUMBER,
                    description="Confidence level 0.0-1.0",
                    required=False,
                    default=0.8,
                    min_value=0.0,
                    max_value=1.0,
                ),
            ],
        )
    )

    # =========================================================================
    # TRAVEL TOOLS
    # =========================================================================

    registry.register(
        ToolSchema(
            name="search_accommodations",
            description="Search for hotels, B&Bs, or vacation rentals in a location",
            category="travel",
            execution_time_hint="medium",
            parameters=[
                ParamSchema(
                    name="location",
                    param_type=ParamType.STRING,
                    description="City, region, or area to search (e.g., 'Sonoma', 'Napa Valley')",
                    required=True,
                ),
                ParamSchema(
                    name="check_in_date",
                    param_type=ParamType.STRING,
                    description="Check-in date (e.g., 'next_saturday', '2026-02-14')",
                    required=True,
                ),
                ParamSchema(
                    name="nights",
                    param_type=ParamType.INTEGER,
                    description="Number of nights to stay",
                    required=True,
                    min_value=1,
                    max_value=30,
                ),
                ParamSchema(
                    name="party_size",
                    param_type=ParamType.INTEGER,
                    description="Number of guests",
                    required=False,
                    default=2,
                    min_value=1,
                    max_value=20,
                ),
                ParamSchema(
                    name="budget_per_night",
                    param_type=ParamType.NUMBER,
                    description="Maximum price per night in USD",
                    required=False,
                ),
                ParamSchema(
                    name="amenities",
                    param_type=ParamType.ARRAY,
                    description="Desired amenities (e.g., ['wifi', 'pool', 'spa'])",
                    required=False,
                    items_type=ParamType.STRING,
                ),
                ParamSchema(
                    name="property_type",
                    param_type=ParamType.STRING,
                    description="Type of accommodation",
                    required=False,
                    enum=["hotel", "bnb", "resort", "vacation_rental", "any"],
                ),
            ],
        )
    )

    registry.register(
        ToolSchema(
            name="get_accommodation_details",
            description="Get detailed information about a specific accommodation",
            category="travel",
            parameters=[
                ParamSchema(
                    name="name",
                    param_type=ParamType.STRING,
                    description="Name of the accommodation",
                    required=True,
                ),
                ParamSchema(
                    name="location",
                    param_type=ParamType.STRING,
                    description="Location for disambiguation",
                    required=False,
                ),
            ],
        )
    )

    registry.register(
        ToolSchema(
            name="book_accommodation",
            description="Book a room or property at an accommodation",
            category="travel",
            requires_confirmation=True,
            parameters=[
                ParamSchema(
                    name="name",
                    param_type=ParamType.STRING,
                    description="Name of the accommodation to book",
                    required=True,
                ),
                ParamSchema(
                    name="location",
                    param_type=ParamType.STRING,
                    description="Location of the accommodation",
                    required=True,
                ),
                ParamSchema(
                    name="check_in_date",
                    param_type=ParamType.STRING,
                    description="Check-in date",
                    required=True,
                ),
                ParamSchema(
                    name="nights",
                    param_type=ParamType.INTEGER,
                    description="Number of nights",
                    required=True,
                    min_value=1,
                ),
                ParamSchema(
                    name="guests",
                    param_type=ParamType.INTEGER,
                    description="Number of guests",
                    required=True,
                    min_value=1,
                ),
                ParamSchema(
                    name="special_requests",
                    param_type=ParamType.ARRAY,
                    description="Special requests or notes",
                    required=False,
                    items_type=ParamType.STRING,
                ),
            ],
        )
    )

    registry.register(
        ToolSchema(
            name="search_restaurants",
            description="Search for restaurants in a location",
            category="travel",
            execution_time_hint="medium",
            parameters=[
                ParamSchema(
                    name="location",
                    param_type=ParamType.STRING,
                    description="City or area to search",
                    required=True,
                ),
                ParamSchema(
                    name="cuisine",
                    param_type=ParamType.STRING,
                    description="Type of cuisine (e.g., 'Italian', 'Japanese', 'American')",
                    required=False,
                ),
                ParamSchema(
                    name="date",
                    param_type=ParamType.STRING,
                    description="Date for the reservation",
                    required=False,
                ),
                ParamSchema(
                    name="time",
                    param_type=ParamType.STRING,
                    description="Preferred time (e.g., '19:00', '7pm')",
                    required=False,
                ),
                ParamSchema(
                    name="party_size",
                    param_type=ParamType.INTEGER,
                    description="Number of diners",
                    required=False,
                    default=2,
                ),
                ParamSchema(
                    name="avoid_ingredients",
                    param_type=ParamType.ARRAY,
                    description="Ingredients to avoid due to allergies or preferences",
                    required=False,
                    items_type=ParamType.STRING,
                ),
                ParamSchema(
                    name="price_range",
                    param_type=ParamType.STRING,
                    description="Price range",
                    required=False,
                    enum=["$", "$$", "$$$", "$$$$"],
                ),
            ],
        )
    )

    registry.register(
        ToolSchema(
            name="get_restaurant_details",
            description="Get detailed information about a specific restaurant",
            category="travel",
            parameters=[
                ParamSchema(
                    name="name",
                    param_type=ParamType.STRING,
                    description="Name of the restaurant",
                    required=True,
                ),
                ParamSchema(
                    name="query",
                    param_type=ParamType.STRING,
                    description="Specific info to look for (e.g., 'birthday_specials', 'menu', 'reviews')",
                    required=False,
                ),
            ],
        )
    )

    registry.register(
        ToolSchema(
            name="book_restaurant",
            description="Make a restaurant reservation",
            category="travel",
            requires_confirmation=True,
            parameters=[
                ParamSchema(
                    name="restaurant_name",
                    param_type=ParamType.STRING,
                    description="Name of the restaurant",
                    required=True,
                ),
                ParamSchema(
                    name="date",
                    param_type=ParamType.STRING,
                    description="Date for the reservation",
                    required=True,
                ),
                ParamSchema(
                    name="time",
                    param_type=ParamType.STRING,
                    description="Time for the reservation",
                    required=True,
                ),
                ParamSchema(
                    name="party_size",
                    param_type=ParamType.INTEGER,
                    description="Number of diners",
                    required=True,
                    min_value=1,
                ),
                ParamSchema(
                    name="special_requests",
                    param_type=ParamType.ARRAY,
                    description="Special requests (e.g., birthday, anniversary, dietary needs)",
                    required=False,
                    items_type=ParamType.STRING,
                ),
            ],
        )
    )

    registry.register(
        ToolSchema(
            name="plan_route",
            description="Plan a driving route between locations",
            category="travel",
            parameters=[
                ParamSchema(
                    name="origin",
                    param_type=ParamType.STRING,
                    description="Starting location",
                    required=True,
                ),
                ParamSchema(
                    name="destination",
                    param_type=ParamType.STRING,
                    description="Destination location",
                    required=True,
                ),
                ParamSchema(
                    name="preference",
                    param_type=ParamType.STRING,
                    description="Route preference",
                    required=False,
                    default="fastest",
                    enum=["fastest", "scenic", "avoid_highways", "avoid_tolls"],
                ),
                ParamSchema(
                    name="departure_time",
                    param_type=ParamType.STRING,
                    description="When to leave",
                    required=False,
                ),
            ],
        )
    )

    registry.register(
        ToolSchema(
            name="search_activities",
            description="Search for activities and things to do in a location",
            category="travel",
            parameters=[
                ParamSchema(
                    name="location",
                    param_type=ParamType.STRING,
                    description="Location to search",
                    required=True,
                ),
                ParamSchema(
                    name="date",
                    param_type=ParamType.STRING,
                    description="Date for activities",
                    required=False,
                ),
                ParamSchema(
                    name="category",
                    param_type=ParamType.STRING,
                    description="Type of activity",
                    required=False,
                    enum=[
                        "relaxation",
                        "adventure",
                        "culture",
                        "food_wine",
                        "nature",
                        "family",
                        "romantic",
                    ],
                ),
                ParamSchema(
                    name="duration",
                    param_type=ParamType.STRING,
                    description="Preferred duration",
                    required=False,
                    enum=["1-2 hours", "half-day", "full-day"],
                ),
            ],
        )
    )

    registry.register(
        ToolSchema(
            name="book_spa_service",
            description="Book a spa service or treatment",
            category="travel",
            requires_confirmation=True,
            parameters=[
                ParamSchema(
                    name="location",
                    param_type=ParamType.STRING,
                    description="Spa or hotel name",
                    required=True,
                ),
                ParamSchema(
                    name="service",
                    param_type=ParamType.STRING,
                    description="Type of service",
                    required=True,
                    enum=[
                        "massage",
                        "couples_massage",
                        "facial",
                        "body_treatment",
                        "package",
                    ],
                ),
                ParamSchema(
                    name="date",
                    param_type=ParamType.STRING,
                    description="Date for appointment",
                    required=True,
                ),
                ParamSchema(
                    name="time",
                    param_type=ParamType.STRING,
                    description="Time for appointment",
                    required=True,
                ),
                ParamSchema(
                    name="guests",
                    param_type=ParamType.INTEGER,
                    description="Number of guests",
                    required=False,
                    default=1,
                ),
            ],
        )
    )

    # =========================================================================
    # FAMILY TOOLS
    # =========================================================================

    registry.register(
        ToolSchema(
            name="send_family_message",
            description="Send a message to a family member",
            category="family",
            parameters=[
                ParamSchema(
                    name="to",
                    param_type=ParamType.STRING,
                    description="Name of the family member to message",
                    required=True,
                ),
                ParamSchema(
                    name="subject",
                    param_type=ParamType.STRING,
                    description="Subject or title of the message",
                    required=True,
                ),
                ParamSchema(
                    name="content",
                    param_type=ParamType.STRING,
                    description="The message content to send",
                    required=True,
                ),
                ParamSchema(
                    name="priority",
                    param_type=ParamType.STRING,
                    description="Message priority",
                    required=False,
                    default="normal",
                    enum=["low", "normal", "high", "urgent"],
                ),
            ],
        )
    )

    registry.register(
        ToolSchema(
            name="schedule_family_checkin",
            description="Schedule an automated check-in message to a family member",
            category="family",
            parameters=[
                ParamSchema(
                    name="target",
                    param_type=ParamType.STRING,
                    description="Family member to check in with",
                    required=True,
                ),
                ParamSchema(
                    name="datetime",
                    param_type=ParamType.STRING,
                    description="When to send the check-in",
                    required=True,
                ),
                ParamSchema(
                    name="message",
                    param_type=ParamType.STRING,
                    description="The check-in message",
                    required=True,
                ),
                ParamSchema(
                    name="notify_user_on_response",
                    param_type=ParamType.BOOLEAN,
                    description="Whether to notify user when family member responds",
                    required=False,
                    default=True,
                ),
            ],
        )
    )

    registry.register(
        ToolSchema(
            name="get_family_member_info",
            description="Get stored information about a family member",
            category="family",
            parameters=[
                ParamSchema(
                    name="name",
                    param_type=ParamType.STRING,
                    description="Name of the family member",
                    required=True,
                ),
                ParamSchema(
                    name="info_type",
                    param_type=ParamType.STRING,
                    description="Type of information to retrieve",
                    required=False,
                    enum=["all", "contact", "schedule", "preferences", "health"],
                ),
            ],
        )
    )

    # =========================================================================
    # CALENDAR & REMINDER TOOLS
    # =========================================================================

    registry.register(
        ToolSchema(
            name="create_calendar_event",
            description="Create a calendar event",
            category="calendar",
            parameters=[
                ParamSchema(
                    name="title",
                    param_type=ParamType.STRING,
                    description="Event title",
                    required=True,
                ),
                ParamSchema(
                    name="start",
                    param_type=ParamType.STRING,
                    description="Start date/time",
                    required=True,
                ),
                ParamSchema(
                    name="end",
                    param_type=ParamType.STRING,
                    description="End date/time",
                    required=True,
                ),
                ParamSchema(
                    name="location",
                    param_type=ParamType.STRING,
                    description="Event location",
                    required=False,
                ),
                ParamSchema(
                    name="notes",
                    param_type=ParamType.STRING,
                    description="Additional notes",
                    required=False,
                ),
                ParamSchema(
                    name="visibility",
                    param_type=ParamType.STRING,
                    description="Event visibility",
                    required=False,
                    default="default",
                    enum=["default", "public", "private"],
                ),
                ParamSchema(
                    name="reminder_minutes",
                    param_type=ParamType.INTEGER,
                    description="Minutes before event to send reminder",
                    required=False,
                    default=30,
                ),
            ],
        )
    )

    registry.register(
        ToolSchema(
            name="schedule_reminder",
            description="Schedule a reminder for the user",
            category="calendar",
            parameters=[
                ParamSchema(
                    name="message",
                    param_type=ParamType.STRING,
                    description="The reminder message",
                    required=True,
                ),
                ParamSchema(
                    name="datetime",
                    param_type=ParamType.STRING,
                    description="When to send the reminder",
                    required=True,
                ),
                ParamSchema(
                    name="recipient",
                    param_type=ParamType.STRING,
                    description="Who to remind (default: user)",
                    required=False,
                    default="user",
                ),
                ParamSchema(
                    name="repeat",
                    param_type=ParamType.STRING,
                    description="Repeat pattern",
                    required=False,
                    enum=["none", "daily", "weekly", "monthly"],
                ),
            ],
        )
    )

    registry.register(
        ToolSchema(
            name="generate_trip_summary",
            description="Generate a complete summary of trip planning in the session",
            category="calendar",
            parameters=[
                ParamSchema(
                    name="format",
                    param_type=ParamType.STRING,
                    description="Output format",
                    required=False,
                    default="detailed",
                    enum=["brief", "detailed", "checklist"],
                ),
                ParamSchema(
                    name="include_costs",
                    param_type=ParamType.BOOLEAN,
                    description="Whether to include cost breakdown",
                    required=False,
                    default=True,
                ),
            ],
        )
    )

    # =========================================================================
    # BACKGROUND MONITOR TOOLS
    # =========================================================================

    registry.register(
        ToolSchema(
            name="start_background_monitor",
            description="Start monitoring something in the background with alerts",
            category="background",
            parameters=[
                ParamSchema(
                    name="monitor_type",
                    param_type=ParamType.STRING,
                    description="What to monitor",
                    required=True,
                    enum=[
                        "weather",
                        "price",
                        "availability",
                        "traffic",
                        "oven",
                        "laundry",
                        "smoke_detector",
                        "doorbell",
                        "thermostat",
                        "baby_monitor",
                    ],
                ),
                ParamSchema(
                    name="target",
                    param_type=ParamType.STRING,
                    description="What to monitor (location, item, route, etc.)",
                    required=True,
                ),
                ParamSchema(
                    name="dates",
                    param_type=ParamType.ARRAY,
                    description="Dates to monitor",
                    required=False,
                    items_type=ParamType.STRING,
                ),
                ParamSchema(
                    name="alert_conditions",
                    param_type=ParamType.ARRAY,
                    description="Conditions that trigger an alert",
                    required=False,
                    items_type=ParamType.STRING,
                ),
                ParamSchema(
                    name="check_interval_minutes",
                    param_type=ParamType.INTEGER,
                    description="How often to check (in demo, this is simulated)",
                    required=False,
                    default=60,
                ),
            ],
        )
    )

    registry.register(
        ToolSchema(
            name="stop_background_monitor",
            description="Stop a running background monitor",
            category="background",
            parameters=[
                ParamSchema(
                    name="monitor_id",
                    param_type=ParamType.STRING,
                    description="ID of the monitor to stop",
                    required=True,
                ),
            ],
        )
    )

    registry.register(
        ToolSchema(
            name="list_active_monitors",
            description="List all active background monitors",
            category="background",
            parameters=[],
        )
    )

    # =========================================================================
    # SUB-AGENT TOOLS - Spawn specialized agents for complex tasks
    # =========================================================================

    registry.register(
        ToolSchema(
            name="spawn_agent",
            description="""Spawn a specialized sub-agent to handle a complex task.
Sub-agents run in their own thread with READ-ONLY access to SessionState.
Use this when a task requires multiple tool calls or specialized reasoning.

Available agents:
- SearchAgent: For searching accommodations, restaurants, activities
- BookingAgent: For making reservations and bookings

The agent will execute the task and return results via the Delta Bus.""",
            category="agent",
            execution_time_hint="slow",
            parameters=[
                ParamSchema(
                    name="agent_type",
                    param_type=ParamType.STRING,
                    description="Type of agent to spawn",
                    required=True,
                    enum=["SearchAgent", "BookingAgent"],
                ),
                ParamSchema(
                    name="task_type",
                    param_type=ParamType.STRING,
                    description="Specific task for the agent (e.g., 'search_accommodations', 'book_restaurant')",
                    required=True,
                    enum=[
                        "search_accommodations",
                        "search_restaurants",
                        "search_activities",
                        "book_accommodation",
                        "book_restaurant",
                        "book_spa_service",
                    ],
                ),
                ParamSchema(
                    name="params",
                    param_type=ParamType.OBJECT,
                    description="Parameters for the task (e.g., location, dates, budget)",
                    required=True,
                ),
                ParamSchema(
                    name="priority",
                    param_type=ParamType.STRING,
                    description="Task priority",
                    required=False,
                    default="normal",
                    enum=["low", "normal", "high"],
                ),
            ],
        )
    )

    return registry


# Global registry instance
_global_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """Get the global tool registry, creating if needed."""
    global _global_registry
    if _global_registry is None:
        _global_registry = create_demo_registry()
    return _global_registry
