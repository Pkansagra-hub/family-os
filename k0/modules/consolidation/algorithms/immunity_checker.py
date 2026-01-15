"""
Decay Immunity Checker.

Issue: 4.3.9
Spec Reference: Dossier §4.4.3.1 (lines 3887-3980)

Two-Level Immunity System:
1. Entity-Level Immunity: FAMILY_MEMBER → entire entity immune
2. Attribute-Level Immunity: PERSON.birthday → entity immune if attribute present

Purpose: Prevent decay of core identity facts (family, birthdays, home address).
Human Memory Analogy: We don't forget our own birthday, family members' names,
or where we live.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Set, Union

# =============================================================================
# Enums
# =============================================================================


class ImmunityLevel(Enum):
    """Immunity classification levels."""

    NONE = "none"  # Standard decay applies
    ATTRIBUTE = "attribute"  # Specific attributes protected
    ENTITY = "entity"  # Entire entity protected


# =============================================================================
# Data Classes
# =============================================================================


@dataclass(frozen=True)
class ImmunityResult:
    """Result from immunity check.

    Attributes:
        is_immune: Whether entity should be immune to decay.
        level: Classification level (NONE, ATTRIBUTE, ENTITY).
        reason: Human-readable explanation for decision.
        protected_attributes: List of attributes that triggered immunity.
    """

    is_immune: bool
    level: ImmunityLevel
    reason: str
    protected_attributes: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "is_immune": self.is_immune,
            "level": self.level.value,
            "reason": self.reason,
            "protected_attributes": list(self.protected_attributes),
        }


@dataclass
class ImmunityOntologyEntry:
    """Configuration for entity type immunity.

    Attributes:
        entity_immune: Whether entire entity type is immune.
        attributes: Protected attributes or '*' for all.
    """

    entity_immune: bool
    attributes: Union[frozenset[str], str]  # frozenset or '*'

    def has_all_immune(self) -> bool:
        """Check if all attributes are immune."""
        return self.attributes == "*"


@dataclass
class ImmunityCheckerConfig:
    """Configuration for ImmunityChecker.

    Attributes:
        enabled: Master switch for immunity system.
        family_member_immune: Auto-mark FAMILY_MEMBER immune.
        milestone_events_immune: Auto-mark milestone events immune.
    """

    enabled: bool = True
    family_member_immune: bool = True
    milestone_events_immune: bool = True

    def validate(self) -> None:
        """Validate configuration."""
        # Currently no validation needed, all booleans
        pass


# =============================================================================
# Ontology Constants (from Dossier §4.4.3.1)
# =============================================================================


# Level 1: Entity-level immunity (entire entity never decays)
ENTITY_LEVEL_IMMUNE_TYPES: FrozenSet[str] = frozenset({"FAMILY_MEMBER"})

# Level 2: Attribute-level immunity (specific fields protected)
ATTRIBUTE_LEVEL_IMMUNITY: Dict[str, FrozenSet[str]] = {
    "PERSON": frozenset({"birthday", "name", "relationship_to_user"}),
    "PLACE": frozenset({"home_address", "work_address"}),
    "EVENT": frozenset({"wedding_date", "birth_date", "death_date"}),
    "ORGANIZATION": frozenset({"employer", "school"}),
    "CONCEPT": frozenset({"core_value", "religion", "political_affiliation"}),
}

# Combined ontology dictionary (Dossier §4.4.3.1)
IMMUNITY_ONTOLOGY: Dict[str, ImmunityOntologyEntry] = {
    "FAMILY_MEMBER": ImmunityOntologyEntry(
        entity_immune=True,
        attributes="*",  # All attributes
    ),
    "PERSON": ImmunityOntologyEntry(
        entity_immune=False,
        attributes=frozenset({"birthday", "name", "relationship_to_user"}),
    ),
    "PLACE": ImmunityOntologyEntry(
        entity_immune=False,
        attributes=frozenset({"home_address", "work_address"}),
    ),
    "EVENT": ImmunityOntologyEntry(
        entity_immune=False,
        attributes=frozenset({"wedding_date", "birth_date", "death_date"}),
    ),
    "ORGANIZATION": ImmunityOntologyEntry(
        entity_immune=False,
        attributes=frozenset({"employer", "school"}),
    ),
    "CONCEPT": ImmunityOntologyEntry(
        entity_immune=False,
        attributes=frozenset({"core_value", "religion", "political_affiliation"}),
    ),
}


# =============================================================================
# ImmunityChecker Class
# =============================================================================


class ImmunityChecker:
    """
    Determine if entity should be immune to decay.

    Spec: Dossier §4.4.3.1

    Two-level system:
    1. Entity-level: FAMILY_MEMBER → entire entity immune
    2. Attribute-level: PERSON.birthday → entity immune if attribute present

    Usage:
        checker = ImmunityChecker()
        result = checker.should_mark_immune("PERSON", {"birthday": "1990-01-01"})
        if result.is_immune:
            entity.decay_immune = True
    """

    def __init__(
        self,
        config: Optional[ImmunityCheckerConfig] = None,
        custom_ontology: Optional[Dict[str, ImmunityOntologyEntry]] = None,
    ) -> None:
        """
        Initialize ImmunityChecker.

        Args:
            config: Configuration overrides.
            custom_ontology: Custom ontology dictionary (for testing).
        """
        self.config = config or ImmunityCheckerConfig()
        self.ontology = custom_ontology or IMMUNITY_ONTOLOGY

    def should_mark_immune(
        self,
        entity_type: str,
        entity_attributes: Dict[str, Any],
    ) -> ImmunityResult:
        """
        Determine if entity should be marked decay_immune=TRUE.

        Algorithm (from Dossier §4.4.3.1):
        1. Check if entity_type has entity-level immunity
        2. If not, check if any immune attributes are present
        3. Return result with reason and protected attributes

        Args:
            entity_type: Type of entity (e.g., "PERSON", "FAMILY_MEMBER").
            entity_attributes: Dictionary of entity attributes.

        Returns:
            ImmunityResult with is_immune, level, reason, protected_attributes.
        """
        if not self.config.enabled:
            return ImmunityResult(
                is_immune=False,
                level=ImmunityLevel.NONE,
                reason="Immunity system disabled",
                protected_attributes=(),
            )

        # Normalize entity type to uppercase
        entity_type_upper = entity_type.upper()

        if entity_type_upper not in self.ontology:
            return ImmunityResult(
                is_immune=False,
                level=ImmunityLevel.NONE,
                reason=f"Entity type '{entity_type}' not in ontology",
                protected_attributes=(),
            )

        ontology_entry = self.ontology[entity_type_upper]

        # Level 1: Entity-level immunity (e.g., FAMILY_MEMBER)
        if ontology_entry.entity_immune:
            # FAMILY_MEMBER check
            if not self.config.family_member_immune and entity_type_upper == "FAMILY_MEMBER":
                return ImmunityResult(
                    is_immune=False,
                    level=ImmunityLevel.NONE,
                    reason="Family member immunity disabled by config",
                    protected_attributes=(),
                )

            all_attrs = tuple(sorted(entity_attributes.keys()))
            return ImmunityResult(
                is_immune=True,
                level=ImmunityLevel.ENTITY,
                reason=f"{entity_type_upper} has full entity immunity",
                protected_attributes=all_attrs,
            )

        # Level 2: Attribute-level immunity
        if ontology_entry.has_all_immune():
            # All attributes protected (shouldn't reach here for non-entity-immune)
            all_attrs = tuple(sorted(entity_attributes.keys()))
            return ImmunityResult(
                is_immune=True,
                level=ImmunityLevel.ENTITY,
                reason="All attributes protected",
                protected_attributes=all_attrs,
            )

        # Check if any immune attribute is present and has a value
        immune_attrs = ontology_entry.attributes
        if isinstance(immune_attrs, str):  # '*' case
            immune_attrs = frozenset()

        present_immune: List[str] = []
        for attr in immune_attrs:
            if attr in entity_attributes:
                value = entity_attributes[attr]
                # Attribute must have a truthy value
                if value is not None and value != "" and value != []:
                    present_immune.append(attr)

        if present_immune:
            # Check milestone events config for EVENT type
            if entity_type_upper == "EVENT" and not self.config.milestone_events_immune:
                return ImmunityResult(
                    is_immune=False,
                    level=ImmunityLevel.NONE,
                    reason="Milestone events immunity disabled by config",
                    protected_attributes=(),
                )

            return ImmunityResult(
                is_immune=True,
                level=ImmunityLevel.ATTRIBUTE,
                reason=f"Protected attributes present: {present_immune}",
                protected_attributes=tuple(sorted(present_immune)),
            )

        return ImmunityResult(
            is_immune=False,
            level=ImmunityLevel.NONE,
            reason="No protected attributes found",
            protected_attributes=(),
        )

    def check_record_immunity(
        self,
        record: Any,  # Record with decay_immune attribute
    ) -> bool:
        """
        Check if a record is already marked immune.

        Args:
            record: Record object with decay_immune attribute.

        Returns:
            True if record has decay_immune=True.
        """
        return getattr(record, "decay_immune", False) is True

    def get_immune_entity_types(self) -> Set[str]:
        """Return set of entity types with full entity immunity."""
        return {etype for etype, entry in self.ontology.items() if entry.entity_immune}

    def get_protected_attributes(self, entity_type: str) -> List[str]:
        """Return list of protected attributes for an entity type.

        Args:
            entity_type: Type of entity.

        Returns:
            List of protected attribute names, or ['*'] if all protected.
        """
        entity_type_upper = entity_type.upper()

        if entity_type_upper not in self.ontology:
            return []

        entry = self.ontology[entity_type_upper]
        if entry.has_all_immune():
            return ["*"]

        if isinstance(entry.attributes, str):
            return [entry.attributes]

        return sorted(list(entry.attributes))

    def is_entity_type_immune(self, entity_type: str) -> bool:
        """Check if an entity type has full entity-level immunity.

        Args:
            entity_type: Type of entity.

        Returns:
            True if entire entity type is immune.
        """
        entity_type_upper = entity_type.upper()
        if entity_type_upper not in self.ontology:
            return False
        return self.ontology[entity_type_upper].entity_immune


# =============================================================================
# Integration Helpers
# =============================================================================


def auto_mark_immunity(
    entity_type: str,
    attributes: Dict[str, Any],
    checker: Optional[ImmunityChecker] = None,
) -> bool:
    """
    Auto-mark entity immunity on creation.

    Used in P03 Phase 7 (R4 Entity Extraction).

    Args:
        entity_type: Type of entity being created.
        attributes: Entity attributes dictionary.
        checker: Optional ImmunityChecker instance.

    Returns:
        True if entity should be marked decay_immune.
    """
    if checker is None:
        checker = ImmunityChecker()

    result = checker.should_mark_immune(entity_type, attributes)
    return result.is_immune


async def set_entity_immunity(
    db_conn: Any,
    entity_id: str,
    table_name: str,
    set_immune: bool,
    reason: str = "Manual override",
) -> None:
    """
    Set entity immunity via K1 command.

    Commands:
    - "Never forget this" → set_immune=True
    - "You can forget this" → set_immune=False

    Args:
        db_conn: Database connection.
        entity_id: Entity ID to update.
        table_name: Table containing entity.
        set_immune: Whether to set or clear immunity.
        reason: Reason for manual override.
    """
    import time

    now_ms = int(time.time() * 1000)

    # Validate table name against allowed tables
    allowed_tables = {"st_kg_dom", "st_kg_edges", "st_sem", "st_social", "st_epi"}
    if table_name not in allowed_tables:
        raise ValueError(f"Invalid table name: {table_name}")

    # Build query safely (table name validated above)
    query = f"""
        UPDATE {table_name}
        SET decay_immune = $1, updated_at = $2
        WHERE entity_id = $3
    """

    await db_conn.execute(query, set_immune, now_ms, entity_id)


# =============================================================================
# Metrics Helpers
# =============================================================================


class ImmunityMetricsCollector:
    """Collect immunity-related metrics.

    Metrics (from Dossier §4.4.3.1):
    - p03_decay_immune_entities: Gauge of immune entities by type and level
    - p03_decay_immune_skipped: Counter of decay updates skipped
    - p03_decay_immunity_auto_marked: Counter of entities auto-marked
    """

    def __init__(self) -> None:
        """Initialize metrics collector."""
        # Counters for tracking
        self._auto_marked_count: Dict[str, int] = {}
        self._skipped_count: Dict[str, int] = {}

    def record_auto_marked(
        self,
        entity_type: str,
        level: ImmunityLevel,
    ) -> None:
        """Record entity auto-marked immune."""
        key = f"{entity_type}:{level.value}"
        self._auto_marked_count[key] = self._auto_marked_count.get(key, 0) + 1

    def record_decay_skipped(self, layer: str) -> None:
        """Record decay update skipped due to immunity."""
        self._skipped_count[layer] = self._skipped_count.get(layer, 0) + 1

    def get_auto_marked_count(self, entity_type: str, level: ImmunityLevel) -> int:
        """Get count of auto-marked entities."""
        key = f"{entity_type}:{level.value}"
        return self._auto_marked_count.get(key, 0)

    def get_skipped_count(self, layer: str) -> int:
        """Get count of skipped decay updates."""
        return self._skipped_count.get(layer, 0)

    def reset(self) -> None:
        """Reset all counters."""
        self._auto_marked_count.clear()
        self._skipped_count.clear()
