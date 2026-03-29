"""
Context Resolver
=================

Resolves ambiguous references using SessionState context:
- Temporal references ("next Saturday" -> "2026-02-07")
- Entity references ("it", "the hotel" -> "Vineyard Inn")
- Location references ("there" -> "Sonoma")

Once resolved, references are LOCKED and should not be re-asked.

This prevents the "next Saturday" bug where the system asks 12+ times
for information it already has.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from poc.session_state_demo.bridge import SessionLLMBridge


@dataclass
class ResolvedReference:
    """A resolved reference that should not be re-asked."""

    original: str  # "next Saturday"
    resolved: str  # "2026-02-07"
    ref_type: str  # "temporal", "entity", "location"
    confidence: float  # 0.0-1.0
    source: str  # "user_input", "inference", "belief"
    turn_resolved: int
    locked: bool = True  # Once locked, don't ask again


@dataclass
class ContextResolution:
    """Result of context resolution."""

    resolved_refs: Dict[str, ResolvedReference] = field(default_factory=dict)
    inferred_entities: Dict[str, str] = field(default_factory=dict)
    active_referents: List[str] = field(default_factory=list)
    current_topic: Optional[str] = None


class ContextResolver:
    """
    Resolves ambiguous references to concrete values.

    Key principle: Once information is established (explicitly or implicitly),
    DON'T ASK AGAIN unless the user explicitly changes it.

    This is the MOST IMPORTANT class for preventing annoying re-asks.
    """

    # Temporal patterns
    TEMPORAL_PATTERNS = [
        (r"\bnext\s+saturday\b", "next_saturday"),
        (r"\bnext\s+sunday\b", "next_sunday"),
        (r"\bthis\s+saturday\b", "this_saturday"),
        (r"\bthis\s+sunday\b", "this_sunday"),
        (r"\bthis\s+weekend\b", "this_weekend"),
        (r"\bnext\s+weekend\b", "next_weekend"),
        (r"\btomorrow\b", "tomorrow"),
        (r"\btoday\b", "today"),
    ]

    # Pronoun patterns that need resolution
    PRONOUN_PATTERNS = [
        (r"\bit\b", "it"),
        (r"\bthem\b", "them"),
        (r"\bthere\b", "there"),
        (r"\bthat\s+one\b", "that_one"),
        (r"\bthe\s+hotel\b", "the_hotel"),
        (r"\bthe\s+restaurant\b", "the_restaurant"),
        (r"\bthe\s+inn\b", "the_inn"),
    ]

    def __init__(self, bridge: Optional["SessionLLMBridge"] = None):
        self._bridge = bridge
        self._resolved: Dict[str, ResolvedReference] = {}
        self._current_turn = 0

    def resolve(
        self,
        user_input: str,
        turn_number: int,
        scoreboard: Optional[Dict[str, Any]] = None,
        beliefs: Optional[Dict[str, Any]] = None,
    ) -> ContextResolution:
        """
        Resolve all references in user input.

        Args:
            user_input: The user's message
            turn_number: Current turn number
            scoreboard: Current scoreboard state (topic, referents)
            beliefs: Current beliefs from SessionState

        Returns:
            ContextResolution with all resolved references
        """
        self._current_turn = turn_number
        result = ContextResolution()

        # Get scoreboard data
        if scoreboard:
            result.current_topic = scoreboard.get("topic")
            result.active_referents = scoreboard.get("referents", [])
        elif self._bridge:
            try:
                data = self._bridge.get_section_data("scoreboard")
                if "error" not in data:
                    result.current_topic = data.get("topic")
                    result.active_referents = list(data.get("referents", {}).keys())
            except Exception:
                pass

        # Get beliefs
        if not beliefs and self._bridge:
            try:
                data = self._bridge.get_section_data("beliefs_active")
                if "error" not in data:
                    beliefs = data.get("beliefs", {})
            except Exception:
                pass

        # Resolve temporal references
        self._resolve_temporal(user_input, result, beliefs)

        # Resolve entity references (pronouns -> referents)
        self._resolve_entities(user_input, result, beliefs)

        # Add already-resolved refs
        result.resolved_refs.update(self._resolved)

        return result

    def _resolve_temporal(
        self,
        user_input: str,
        result: ContextResolution,
        beliefs: Optional[Dict[str, Any]],
    ) -> None:
        """Resolve temporal references like 'next Saturday'."""
        input_lower = user_input.lower()

        for pattern, ref_type in self.TEMPORAL_PATTERNS:
            if re.search(pattern, input_lower):
                # Check if already resolved
                if ref_type in self._resolved:
                    # Already resolved - don't change it
                    continue

                # Resolve it now
                resolved_date = self._calculate_date(ref_type)
                if resolved_date:
                    ref = ResolvedReference(
                        original=ref_type.replace("_", " "),
                        resolved=resolved_date,
                        ref_type="temporal",
                        confidence=0.9,
                        source="user_input",
                        turn_resolved=self._current_turn,
                        locked=True,
                    )
                    self._resolved[ref_type] = ref
                    result.resolved_refs[ref_type] = ref

                    # Also store in beliefs if bridge available
                    if self._bridge:
                        try:
                            self._bridge.add_belief(
                                subject="trip",
                                predicate="date",
                                obj=resolved_date,
                                confidence=0.9,
                            )
                        except Exception:
                            pass

        # Check beliefs for date info
        if beliefs:
            trip_info = beliefs.get("trip", {})
            if isinstance(trip_info, dict):
                if "date" in trip_info and "date" not in self._resolved:
                    ref = ResolvedReference(
                        original="trip date",
                        resolved=str(trip_info["date"]),
                        ref_type="temporal",
                        confidence=0.95,
                        source="belief",
                        turn_resolved=self._current_turn,
                        locked=True,
                    )
                    self._resolved["date"] = ref
                    result.resolved_refs["date"] = ref

    def _resolve_entities(
        self,
        user_input: str,
        result: ContextResolution,
        beliefs: Optional[Dict[str, Any]],
    ) -> None:
        """Resolve entity references using scoreboard referents."""
        input_lower = user_input.lower()

        for pattern, ref_type in self.PRONOUN_PATTERNS:
            if re.search(pattern, input_lower):
                # Try to resolve from active referents
                resolved = self._find_matching_referent(
                    ref_type,
                    result.active_referents,
                    beliefs,
                )
                if resolved:
                    result.inferred_entities[ref_type] = resolved

    def _find_matching_referent(
        self,
        ref_type: str,
        referents: List[str],
        beliefs: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        """Find matching referent for a pronoun."""
        # Map pronouns to likely entity types
        type_hints = {
            "it": ["hotel", "inn", "restaurant", "spa", "booking"],
            "the_hotel": ["hotel", "inn", "lodge", "resort"],
            "the_inn": ["inn", "hotel", "lodge"],
            "the_restaurant": ["restaurant", "cafe", "bistro"],
            "there": ["sonoma", "napa", "location"],
            "them": ["family", "guests", "people"],
        }

        hints = type_hints.get(ref_type, [])

        # Search referents
        for referent in referents:
            ref_lower = referent.lower()
            for hint in hints:
                if hint in ref_lower:
                    return referent

        # Search beliefs
        if beliefs:
            for subject, predicates in beliefs.items():
                if isinstance(predicates, dict):
                    for pred, obj in predicates.items():
                        for hint in hints:
                            if hint in str(obj).lower():
                                return str(obj)

        return None

    def _calculate_date(self, ref_type: str) -> Optional[str]:
        """Calculate actual date from relative reference."""
        today = datetime.now()
        weekday = today.weekday()  # Monday=0, Sunday=6

        if ref_type == "tomorrow":
            return (today + timedelta(days=1)).strftime("%Y-%m-%d")

        if ref_type == "today":
            return today.strftime("%Y-%m-%d")

        if ref_type in ("next_saturday", "this_saturday"):
            # Find next Saturday
            days_until_saturday = (5 - weekday) % 7
            if days_until_saturday == 0 and ref_type == "next_saturday":
                days_until_saturday = 7
            target = today + timedelta(days=days_until_saturday)
            return target.strftime("%Y-%m-%d")

        if ref_type in ("next_sunday", "this_sunday"):
            # Find next Sunday
            days_until_sunday = (6 - weekday) % 7
            if days_until_sunday == 0 and ref_type == "next_sunday":
                days_until_sunday = 7
            target = today + timedelta(days=days_until_sunday)
            return target.strftime("%Y-%m-%d")

        if ref_type in ("this_weekend", "next_weekend"):
            # Return Saturday of the weekend
            days_until_saturday = (5 - weekday) % 7
            if days_until_saturday <= 1 and ref_type == "next_weekend":
                days_until_saturday += 7
            target = today + timedelta(days=days_until_saturday)
            return target.strftime("%Y-%m-%d")

        return None

    def is_resolved(self, field: str) -> bool:
        """Check if a field is already resolved (and locked)."""
        if field in self._resolved:
            return self._resolved[field].locked
        return False

    def get_resolved(self, field: str) -> Optional[str]:
        """Get resolved value for a field."""
        if field in self._resolved:
            return self._resolved[field].resolved
        return None

    def get_all_resolved(self) -> Dict[str, str]:
        """Get all resolved references as field->value dict."""
        return {k: v.resolved for k, v in self._resolved.items()}

    def should_ask_for(self, field: str, beliefs: Optional[Dict] = None) -> bool:
        """
        Check if we should ask for a field.

        CRITICAL: Returns False if the field is already resolved,
        inferred, or present in beliefs.
        """
        # Already resolved -> don't ask
        if self.is_resolved(field):
            return False

        # Check beliefs for the field
        if beliefs:
            field_lower = field.lower()
            for subject, predicates in beliefs.items():
                if field_lower in subject.lower():
                    return False
                if isinstance(predicates, dict):
                    for pred, obj in predicates.items():
                        if field_lower in pred.lower() or field_lower in str(obj).lower():
                            return False

        return True


def create_context_resolver(bridge: Optional["SessionLLMBridge"] = None) -> ContextResolver:
    """Factory function to create a context resolver."""
    return ContextResolver(bridge=bridge)
