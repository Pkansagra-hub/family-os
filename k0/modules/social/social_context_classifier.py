"""
M07.3: social.social_context_classifier - Research-Backed Social Context Classification

Classifies social context and intimacy based on participant relationships,
implementing Dunbar's social layers and Granovetter's tie strength theory.

Research Foundation:
- Dunbar (1992): Social group sizes and cognitive limits
- Granovetter (1973): Strength of weak ties
- Hamilton (1964): Kin selection and inclusive fitness

Key Concepts:
1. Dunbar's Layers: intimate(5), close(15), friends(50), acquaintances(150)
2. Relationship Strength: Scored based on biological/social proximity
3. Social Distance: Graph distance in relationship network
4. Group Composition: Mixed groups handled via weighted classification

Performance target: <5ms P95
Contract: k0/contracts/modules/social.social_context_classifier.v1.yaml
ADR: docs/architecture/decisions-K0/modules/k008.3-social-context-classifier.md

Status: IMPLEMENTED (rule-based with research foundations)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================================
# Data Structures
# ============================================================================


class SocialContextType(str, Enum):
    """Social context categories."""

    SOLO = "solo"
    NUCLEAR_FAMILY = "nuclear_family"
    EXTENDED_FAMILY = "extended_family"
    CLOSE_FRIENDS = "close_friends"
    FRIENDS = "friends"
    WORK = "work"
    ACQUAINTANCES = "acquaintances"
    MIXED = "mixed"  # Family + non-family


class IntimacyLevel(str, Enum):
    """Intimacy levels based on relationship strength."""

    HIGH = "HIGH"  # Nuclear family, intimate partners
    MEDIUM = "MED"  # Extended family, close friends
    LOW = "LOW"  # Friends, acquaintances, solo


class DunbarLayer(str, Enum):
    """
    Dunbar's social layers based on cognitive limits.

    Research: Dunbar (1992) - Neocortex size constrains group sizes:
    - Support clique: ~5 (intimate relationships)
    - Sympathy group: ~15 (close relationships)
    - Band: ~50 (friends)
    - Clan: ~150 (acquaintances)
    """

    INTIMATE = "intimate"  # 1-5 people
    CLOSE = "close"  # 6-15 people
    FRIENDS = "friends"  # 16-50 people
    ACQUAINTANCES = "acquaintances"  # 51-150 people
    BEYOND = "beyond"  # 150+ (weak ties)


@dataclass
class SocialContextResult:
    """Result of social context classification."""

    context: SocialContextType
    intimacy: IntimacyLevel
    dunbar_layer: DunbarLayer
    group_size: int
    average_relationship_strength: float  # 0.0 - 1.0
    family_ratio: float  # Fraction of participants who are family
    explanation: str
    breakdown: dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Relationship Strength Scoring
# ============================================================================

# Relationship strengths based on Hamilton's kin selection (r coefficient)
# and social proximity research
RELATIONSHIP_STRENGTH: dict[str, float] = {
    # Nuclear family (r = 0.5 genetic relatedness)
    "SELF": 1.0,
    "SPOUSE": 0.9,  # Not genetic but highest social bond
    "CHILD": 0.85,  # r = 0.5, but very high caregiving investment
    "PARENT": 0.85,  # r = 0.5, but foundational relationship
    # Extended family
    "SIBLING": 0.7,  # r = 0.5, but typically less daily interaction
    "CAREGIVER": 0.6,  # High trust relationship
    "GRANDPARENT": 0.5,  # r = 0.25
    "GRANDCHILD": 0.5,  # r = 0.25
    "AUNT_UNCLE": 0.4,  # r = 0.25
    "COUSIN": 0.3,  # r = 0.125
    # Non-family
    "CLOSE_FRIEND": 0.5,  # Chosen family
    "FRIEND": 0.3,
    "COLLEAGUE": 0.2,
    "ACQUAINTANCE": 0.1,
    "OTHER": 0.1,  # Unknown relationship
}


def get_relationship_strength(role: str) -> float:
    """
    Get relationship strength score for a role.

    Args:
        role: Relationship role (SPOUSE, CHILD, PARENT, etc.)

    Returns:
        Strength score from 0.0 (stranger) to 1.0 (self)
    """
    return RELATIONSHIP_STRENGTH.get(role.upper(), 0.1)


# ============================================================================
# Dunbar Layer Classification
# ============================================================================


def classify_dunbar_layer(group_size: int, avg_strength: float) -> DunbarLayer:
    """
    Classify into Dunbar's social layer based on group size and relationship strength.

    Args:
        group_size: Number of participants in event
        avg_strength: Average relationship strength (0-1)

    Returns:
        Appropriate Dunbar layer
    """
    # Size-based initial classification
    if group_size <= 5:
        # Small group - check if truly intimate
        if avg_strength >= 0.6:
            return DunbarLayer.INTIMATE
        elif avg_strength >= 0.3:
            return DunbarLayer.CLOSE
        else:
            return DunbarLayer.FRIENDS

    elif group_size <= 15:
        # Medium group
        if avg_strength >= 0.5:
            return DunbarLayer.CLOSE
        else:
            return DunbarLayer.FRIENDS

    elif group_size <= 50:
        return DunbarLayer.FRIENDS

    elif group_size <= 150:
        return DunbarLayer.ACQUAINTANCES

    else:
        return DunbarLayer.BEYOND


# ============================================================================
# Social Context Classifier
# ============================================================================


class SocialContextClassifier:
    """
    Research-backed social context classifier.

    Research:
    - Dunbar (1992): Social group sizes
    - Granovetter (1973): Strength of weak ties
    - Hamilton (1964): Kin selection

    Features:
    - Group composition analysis
    - Relationship strength scoring
    - Social distance calculation
    - Context-appropriate intimacy levels
    - Mixed group handling (family + friends)
    """

    # Role classifications
    NUCLEAR_FAMILY_ROLES = {"SPOUSE", "PARENT", "CHILD"}
    EXTENDED_FAMILY_ROLES = {
        "SIBLING",
        "CAREGIVER",
        "GRANDPARENT",
        "GRANDCHILD",
        "AUNT_UNCLE",
        "COUSIN",
    }
    WORK_ROLES = {"COLLEAGUE", "BOSS", "EMPLOYEE"}
    ALL_FAMILY_ROLES = NUCLEAR_FAMILY_ROLES | EXTENDED_FAMILY_ROLES

    def __init__(self):
        """Initialize classifier."""
        pass

    def classify(
        self,
        participants: list[str],
        participant_roles: dict[str, str],
        actor_id: str,
    ) -> SocialContextResult:
        """
        Classify social context based on participant composition.

        Args:
            participants: List of participant IDs
            participant_roles: Dict mapping participant_id -> role
            actor_id: The event actor/owner

        Returns:
            SocialContextResult with full classification details
        """
        # Handle solo events
        if not participants or (len(participants) == 1 and participants[0] == actor_id):
            return SocialContextResult(
                context=SocialContextType.SOLO,
                intimacy=IntimacyLevel.LOW,
                dunbar_layer=DunbarLayer.INTIMATE,
                group_size=1,
                average_relationship_strength=1.0,
                family_ratio=0.0,
                explanation="Solo event (no other participants)",
                breakdown={"actor_only": True},
            )

        # Filter out actor from analysis (they're always SELF)
        other_participants = [p for p in participants if p != actor_id]
        if not other_participants:
            return self._solo_result()

        # Extract roles for other participants
        roles = [participant_roles.get(p, "OTHER") for p in other_participants]

        # Calculate metrics
        strengths = [get_relationship_strength(r) for r in roles]
        avg_strength = sum(strengths) / len(strengths) if strengths else 0.0

        # Count role categories
        roles_set = set(roles)
        nuclear_present = bool(roles_set & self.NUCLEAR_FAMILY_ROLES)
        extended_present = bool(roles_set & self.EXTENDED_FAMILY_ROLES)
        work_present = bool(roles_set & self.WORK_ROLES)
        family_present = nuclear_present or extended_present

        # Calculate family ratio
        family_count = sum(1 for r in roles if r in self.ALL_FAMILY_ROLES)
        family_ratio = family_count / len(roles) if roles else 0.0

        # Non-family present?
        non_family_count = len(roles) - family_count
        has_non_family = non_family_count > 0

        # Classify context
        context, explanation = self._determine_context(
            nuclear_present=nuclear_present,
            extended_present=extended_present,
            work_present=work_present,
            family_present=family_present,
            has_non_family=has_non_family,
            family_ratio=family_ratio,
            avg_strength=avg_strength,
            group_size=len(participants),
        )

        # Determine intimacy
        intimacy = self._determine_intimacy(context, avg_strength)

        # Determine Dunbar layer
        dunbar_layer = classify_dunbar_layer(len(participants), avg_strength)

        return SocialContextResult(
            context=context,
            intimacy=intimacy,
            dunbar_layer=dunbar_layer,
            group_size=len(participants),
            average_relationship_strength=round(avg_strength, 3),
            family_ratio=round(family_ratio, 3),
            explanation=explanation,
            breakdown={
                "nuclear_family_present": nuclear_present,
                "extended_family_present": extended_present,
                "work_present": work_present,
                "family_count": family_count,
                "non_family_count": non_family_count,
                "roles_distribution": self._count_roles(roles),
            },
        )

    def _determine_context(
        self,
        nuclear_present: bool,
        extended_present: bool,
        work_present: bool,
        family_present: bool,
        has_non_family: bool,
        family_ratio: float,
        avg_strength: float,
        group_size: int,
    ) -> tuple[SocialContextType, str]:
        """Determine social context based on composition."""
        # Mixed groups (family + non-family)
        if family_present and has_non_family:
            if family_ratio >= 0.7:
                # Mostly family with some friends
                if nuclear_present:
                    return (
                        SocialContextType.NUCLEAR_FAMILY,
                        f"Nuclear family with {int((1-family_ratio)*100)}% friends",
                    )
                else:
                    return (
                        SocialContextType.EXTENDED_FAMILY,
                        f"Extended family with {int((1-family_ratio)*100)}% friends",
                    )
            elif family_ratio >= 0.3:
                return (
                    SocialContextType.MIXED,
                    f"Mixed group ({int(family_ratio*100)}% family, {int((1-family_ratio)*100)}% non-family)",
                )
            else:
                # Mostly non-family
                return (
                    SocialContextType.FRIENDS,
                    f"Friends gathering with some family ({int(family_ratio*100)}%)",
                )

        # Pure family groups
        if nuclear_present:
            return (
                SocialContextType.NUCLEAR_FAMILY,
                "Nuclear family (spouse/parents/children present)",
            )

        if extended_present:
            return (
                SocialContextType.EXTENDED_FAMILY,
                "Extended family (siblings/caregivers present)",
            )

        # Work context
        if work_present:
            return (
                SocialContextType.WORK,
                "Work context (colleagues present)",
            )

        # Non-family groups - distinguish by strength
        if avg_strength >= 0.4:
            return (
                SocialContextType.CLOSE_FRIENDS,
                f"Close friends (avg strength: {avg_strength:.2f})",
            )
        elif avg_strength >= 0.2:
            return (
                SocialContextType.FRIENDS,
                f"Friends gathering (avg strength: {avg_strength:.2f})",
            )
        else:
            return (
                SocialContextType.ACQUAINTANCES,
                f"Acquaintances (avg strength: {avg_strength:.2f})",
            )

    def _determine_intimacy(
        self,
        context: SocialContextType,
        avg_strength: float,
    ) -> IntimacyLevel:
        """Determine intimacy level from context and strength."""
        # High intimacy contexts
        if context == SocialContextType.NUCLEAR_FAMILY:
            return IntimacyLevel.HIGH

        # Medium intimacy contexts
        if context in (SocialContextType.EXTENDED_FAMILY, SocialContextType.CLOSE_FRIENDS):
            return IntimacyLevel.MEDIUM

        # Mixed depends on strength
        if context == SocialContextType.MIXED:
            if avg_strength >= 0.5:
                return IntimacyLevel.MEDIUM
            return IntimacyLevel.LOW

        # Default to LOW
        return IntimacyLevel.LOW

    def _count_roles(self, roles: list[str]) -> dict[str, int]:
        """Count occurrences of each role."""
        counts: dict[str, int] = {}
        for role in roles:
            counts[role] = counts.get(role, 0) + 1
        return counts

    def _solo_result(self) -> SocialContextResult:
        """Return result for solo events."""
        return SocialContextResult(
            context=SocialContextType.SOLO,
            intimacy=IntimacyLevel.LOW,
            dunbar_layer=DunbarLayer.INTIMATE,
            group_size=1,
            average_relationship_strength=1.0,
            family_ratio=0.0,
            explanation="Solo event",
            breakdown={"actor_only": True},
        )


# ============================================================================
# Enhanced Intimacy Scoring (Granovetter's Tie Strength)
# ============================================================================


def calculate_tie_strength(
    frequency: int,
    recency_days: int,
    emotional_intensity: float,
    reciprocity: bool,
) -> float:
    """
    Calculate tie strength using Granovetter's dimensions.

    Research: Granovetter (1973) - Four dimensions of tie strength:
    1. Time/frequency of interaction
    2. Emotional intensity
    3. Intimacy (mutual confiding)
    4. Reciprocal services

    Args:
        frequency: Number of interactions in last 30 days
        recency_days: Days since last interaction
        emotional_intensity: Emotional content score (0-1)
        reciprocity: Whether relationship is bidirectional

    Returns:
        Tie strength score (0.0 - 1.0)
    """
    # Frequency factor (log scale, caps at ~0.9 for 30+ interactions)
    import math

    freq_factor = min(0.9, math.log1p(frequency) / math.log1p(30))

    # Recency factor (exponential decay, 50% at 7 days)
    recency_factor = math.exp(-recency_days / 10)

    # Emotional intensity directly contributes
    emotion_factor = emotional_intensity

    # Reciprocity bonus
    reciprocity_factor = 1.2 if reciprocity else 1.0

    # Weighted combination
    raw_strength = (
        0.3 * freq_factor
        + 0.2 * recency_factor
        + 0.3 * emotion_factor
        + 0.2 * (1.0 if reciprocity else 0.5)
    )

    return round(min(1.0, max(0.0, raw_strength * reciprocity_factor)), 3)


# ============================================================================
# Module-Level API
# ============================================================================

# Singleton instance
_classifier: SocialContextClassifier | None = None


def get_classifier() -> SocialContextClassifier:
    """Get singleton classifier instance."""
    global _classifier
    if _classifier is None:
        _classifier = SocialContextClassifier()
    return _classifier


def classify_social_context(
    participants: list[str],
    participant_roles: dict[str, str],
    actor_id: str,
) -> SocialContextResult:
    """
    Convenience function to classify social context.

    See SocialContextClassifier.classify for details.
    """
    classifier = get_classifier()
    return classifier.classify(
        participants=participants,
        participant_roles=participant_roles,
        actor_id=actor_id,
    )


def get_relationship_strength_for_role(role: str) -> float:
    """Get relationship strength for a role string."""
    return get_relationship_strength(role)
