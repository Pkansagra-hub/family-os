"""
poc.k1_poc.fabric.capability_registry -- In-Memory Capability Registry.

V2 Design Ref: Section 6.2 (invoke_capability routes through Fabric)

Epic 7.5.4: CapabilityRegistry with discover and invoke methods.

In production, this maps to the K0 Fabric's 9-step execution pipeline.
For POC, it is an in-memory registry with fuzzy intent matching (word
overlap) and direct handler dispatch.

The registry holds two maps:
  _capabilities: name -> capability definition dict
  _handlers:     name -> async handler callable

discover() does fuzzy matching against capability descriptions.
invoke() dispatches to the registered handler by exact name.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

# Domain aliases: LLM-generated domain names -> canonical domain names.
# The LLM often uses synonyms (e.g. "communication" instead of "messaging")
# which causes strict domain filter mismatches. This map normalises them.
DOMAIN_ALIASES: dict[str, str] = {
    # messaging aliases
    "communication": "messaging",
    "communications": "messaging",
    "notifications": "messaging",
    "alerts": "messaging",
    "texting": "messaging",
    "sms": "messaging",
    "chat": "messaging",
    "message": "messaging",
    # household aliases
    "home": "household",
    "chores": "household",
    "chores_management": "household",
    "cleaning": "household",
    "laundry": "household",
    # iot aliases
    "smart_home": "iot",
    "devices": "iot",
    "appliances": "iot",
    "home_automation": "iot",
    # school aliases
    "education": "school",
    "academic": "school",
    "homework": "school",
    "learning": "school",
    # health aliases
    "medical": "health",
    "wellness": "health",
    "medication": "health",
    "healthcare": "health",
    "fitness": "health",
    # transport aliases
    "driving": "transport",
    "commute": "transport",
    "ride": "transport",
    "transit": "transport",
    "transportation": "transport",
    # finance aliases
    "money": "finance",
    "banking": "finance",
    "payments": "finance",
    "budget": "finance",
    # calendar aliases
    "scheduling": "calendar",
    "calendar_management": "calendar",
    "appointments": "calendar",
    "events": "calendar",
    # family_activities aliases
    "activities": "family_activities",
    "family": "family_activities",
    "outings": "family_activities",
    "recreation": "family_activities",
    # productivity aliases
    "reminders": "productivity",
    "tasks": "productivity",
    "todo": "productivity",
    "to_do": "productivity",
    # travel aliases
    "trips": "travel",
    "vacation": "travel",
    "booking": "travel",
    # shopping aliases
    "groceries": "shopping",
    "grocery": "shopping",
    "purchases": "shopping",
}


def resolve_domain(domain: str) -> str:
    """Resolve a domain name through aliases to its canonical form."""
    if not domain:
        return domain
    normalised = domain.strip().lower().replace("-", "_").replace(" ", "_")
    return DOMAIN_ALIASES.get(normalised, normalised)


class CapabilityRegistry:
    """In-memory Fabric capability registry for POC.

    Each registered capability has a definition dict with:
      name:             Fully qualified name (e.g. "tool.execute.hotel_search")
      description:      Human-readable description
      required_inputs:  List of required parameter names
      optional_inputs:  List of optional parameter names
      has_side_effects: Whether the capability modifies external state
      estimated_cost:   Cost hint ("free", "varies", "$0.50")
      domain:           Domain category ("travel", "productivity", "shopping")

    And a handler callable:
      async (params: dict) -> dict
    """

    def __init__(self) -> None:
        self._capabilities: dict[str, dict[str, Any]] = {}
        self._handlers: dict[str, Callable[..., Coroutine[Any, Any, dict[str, Any]]]] = {}
        logger.info("CapabilityRegistry initialized (empty)")

    def register(
        self,
        capability: dict[str, Any],
        handler: Callable[..., Coroutine[Any, Any, dict[str, Any]]],
    ) -> None:
        """Register a capability with its handler.

        Args:
            capability: Capability definition dict (must have 'name').
            handler: Async callable (params: dict) -> dict.
        """
        name = capability["name"]
        self._capabilities[name] = capability
        self._handlers[name] = handler
        logger.debug("Registered capability: %s", name)

    def unregister(self, name: str) -> bool:
        """Remove a capability by name. Returns True if found."""
        found = name in self._capabilities
        self._capabilities.pop(name, None)
        self._handlers.pop(name, None)
        return found

    @property
    def count(self) -> int:
        """Number of registered capabilities."""
        return len(self._capabilities)

    def list_all(self) -> list[dict[str, Any]]:
        """Return all registered capability definitions."""
        return list(self._capabilities.values())

    def has(self, name: str) -> bool:
        """Check if a capability is registered by exact name."""
        return name in self._capabilities

    def get_definition(self, name: str) -> dict[str, Any] | None:
        """Get capability definition by exact name."""
        return self._capabilities.get(name)

    async def discover(
        self,
        intent: str,
        domain: str | None = None,
        constraints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Search registry by intent (fuzzy match) and optional domain filter.

        Fuzzy matching: splits intent into words, checks if any word
        appears in the capability's description (case-insensitive).
        This is sufficient for POC. Production would use semantic search
        via the K0 Fabric's capability discovery service.

        Domain aliases are resolved automatically (e.g. "communication" ->
        "messaging", "smart_home" -> "iot"). If domain-filtered search
        yields no results, a fallback intent-only search is attempted.

        Args:
            intent: Natural language description of what needs to be done.
            domain: Optional domain filter ("travel", "productivity", etc.).
            constraints: Optional constraints dict (unused in POC).

        Returns:
            Dict with 'capabilities' (list of matching defs) and 'count'.
        """
        # Resolve domain aliases (e.g. "communication" -> "messaging")
        resolved_domain = resolve_domain(domain) if domain else None

        matches = self._fuzzy_match(intent, resolved_domain)

        # Fallback: if domain filter yielded 0 results, retry intent-only.
        # This prevents empty results when the LLM guesses wrong domain.
        if not matches and resolved_domain:
            logger.info(
                "discover: domain '%s' (resolved='%s') yielded 0 matches, "
                "retrying intent-only for '%s'",
                domain,
                resolved_domain,
                intent[:60],
            )
            matches = self._fuzzy_match(intent, domain=None)

        result: dict[str, Any] = {"capabilities": matches, "count": len(matches)}

        # When no match found, include available domains and a hint
        # so the LLM can refine its query or use submit_result directly.
        if not matches:
            domains = sorted(
                {c.get("domain", "") for c in self._capabilities.values() if c.get("domain")}
            )
            result["hint"] = (
                f"No capabilities matched intent '{intent}'. "
                f"Available domains: {', '.join(domains)}. "
                f"Total registered: {len(self._capabilities)}. "
                "Try broader keywords or check domain filter."
            )
            logger.info(
                "discover: no match for intent=%s domain=%s resolved=%s (registered=%d)",
                intent[:60],
                domain,
                resolved_domain,
                len(self._capabilities),
            )

        return result

    def _fuzzy_match(
        self,
        intent: str,
        domain: str | None = None,
    ) -> list[dict[str, Any]]:
        """Core fuzzy matching: intent word overlap + optional domain filter."""
        matches: list[dict[str, Any]] = []
        intent_lower = intent.lower()
        intent_words = intent_lower.split()

        for name, cap in self._capabilities.items():
            # Domain filter (already resolved by caller)
            if domain and cap.get("domain", "").lower() != domain.lower():
                continue

            # Fuzzy match: any intent word in name or description
            desc_lower = cap.get("description", "").lower()
            name_lower = name.lower()

            if any(word in desc_lower or word in name_lower for word in intent_words):
                matches.append(cap)

        return matches

    async def invoke(
        self,
        capability_name: str,
        params: dict[str, Any],
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute a registered capability by exact name.

        Args:
            capability_name: Fully qualified capability name.
            params: Capability-specific parameters.
            session_id: Optional session ID for stateful capabilities.

        Returns:
            Result dict from the capability handler.

        Raises:
            KeyError: If capability_name is not registered.
        """
        if capability_name not in self._handlers:
            return {
                "success": False,
                "error": f"Unknown capability: {capability_name}",
                "data": None,
                "artifact_type": None,
                "duration_ms": 0,
            }

        handler = self._handlers[capability_name]
        try:
            result = await handler(params)
            return result
        except Exception as e:
            logger.error("Capability %s failed: %s", capability_name, e)
            return {
                "success": False,
                "error": str(e),
                "data": None,
                "artifact_type": None,
                "duration_ms": 0,
            }


def create_demo_registry() -> CapabilityRegistry:
    """Create a CapabilityRegistry pre-loaded with demo + family capabilities.

    Loads in order:
      1. 7 original demo capabilities (travel, productivity, shopping)
      2. 31 family capabilities (messaging, todo, chores, school, health,
         transport, smart home, calendar, finance, activity prep)

    Returns:
        CapabilityRegistry with all capabilities registered.
    """
    from poc.k1_poc.fabric.demo_capabilities import DEMO_CAPABILITIES, DEMO_HANDLERS
    from poc.k1_poc.fabric.family_capabilities import register_family_capabilities

    registry = CapabilityRegistry()
    for cap in DEMO_CAPABILITIES:
        name = cap["name"]
        handler = DEMO_HANDLERS.get(name)
        if handler:
            registry.register(cap, handler)
        else:
            logger.warning("No handler for demo capability: %s", name)

    demo_count = registry.count

    # Load comprehensive family capabilities (messaging, todo, chores, etc.)
    family_count = register_family_capabilities(registry)

    logger.info(
        "create_demo_registry: loaded %d demo + %d family = %d total capabilities",
        demo_count,
        family_count,
        registry.count,
    )
    return registry
