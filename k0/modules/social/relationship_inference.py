"""
M07.2: social.relationship_inference - GNN-Inspired Relationship Inference

Infers likely relationships from behavioral patterns when explicit relationships
are not found in st_relationships. Uses co-occurrence analysis as foundation
with optional GNN enhancement.

Research Foundation:
- Hamilton et al. (2017) - GraphSAGE: Inductive Representation Learning
- Kipf & Welling (2016) - Graph Convolutional Networks
- Schlichtkrull et al. (2018) - Relational Graph Convolutional Networks

Inference Signals:
1. Co-occurrence patterns (who appears together frequently)
2. Event type patterns (meal events suggest family, work events suggest colleagues)
3. Name similarity (family naming patterns like "person_mom", "person_dad")
4. Temporal patterns (consistent presence suggests close relationship)

Performance target: <20ms P95
Contract: k0/contracts/modules/social.relationship_inference.v1.yaml
ADR: docs/architecture/decisions-K0/modules/k008.2-relationship-inference.md

Status: DESIGN (rule-based co-occurrence, GNN deferred to future enhancement)
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# Data Structures
# ============================================================================


class RelationType(str, Enum):
    """Relationship types that can be inferred."""

    SPOUSE_OF = "SPOUSE_OF"
    PARENT_OF = "PARENT_OF"
    CHILD_OF = "CHILD_OF"
    SIBLING_OF = "SIBLING_OF"
    CARETAKER_OF = "CARETAKER_OF"
    FRIEND = "FRIEND"
    COLLEAGUE = "COLLEAGUE"
    UNKNOWN = "UNKNOWN"


@dataclass
class InferredRelationship:
    """An inferred relationship with confidence and explanation."""

    person_id: str
    related_person_id: str
    relationship_type: RelationType
    confidence: float  # 0.0 - 1.0
    inference_method: str  # "cooccurrence", "name_pattern", "event_type", "gnn"
    explanation: str  # Human-readable reason
    supporting_evidence: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_high_confidence(self) -> bool:
        """Returns True if confidence >= 0.7."""
        return self.confidence >= 0.7


@dataclass
class CooccurrenceStats:
    """Statistics for person co-occurrence patterns."""

    person_id: str
    related_person_id: str
    total_events: int  # Total events with person_id
    shared_events: int  # Events where both appear
    event_types: Dict[str, int]  # Event type distribution
    recency_score: float  # How recent the co-occurrences are (0-1)

    @property
    def cooccurrence_rate(self) -> float:
        """Fraction of events where both appear together."""
        if self.total_events == 0:
            return 0.0
        return self.shared_events / self.total_events

    @property
    def is_significant(self) -> bool:
        """Returns True if co-occurrence is statistically significant."""
        # Require at least 3 shared events for significance
        return self.shared_events >= 3 and self.cooccurrence_rate >= 0.3


# ============================================================================
# Name Pattern Inference
# ============================================================================

# Family role patterns in person IDs
# Note: Patterns are checked in order, so more specific patterns should be first
# "person_mom" means they ARE a parent, so from actor's perspective, actor is CHILD_OF them
FAMILY_NAME_PATTERNS = {
    # Parent patterns - person named "mom/dad" IS a parent to the actor
    # So actor's relationship to them is CHILD_OF (actor is their child)
    RelationType.PARENT_OF: [
        r"person_mom",
        r"person_dad",
        r"person_mother",
        r"person_father",
        r"person_parent",
    ],
    # Child patterns - person named "kid/son/daughter" IS a child to the actor
    # So actor's relationship to them is PARENT_OF (actor is their parent)
    RelationType.CHILD_OF: [
        r"person_kid",
        r"person_child",
        r"person_son",
        r"person_daughter",
        r"person_baby",
    ],
    # Spouse patterns - symmetric relationship
    RelationType.SPOUSE_OF: [
        r"person_spouse",
        r"person_partner",
        r"person_wife",
        r"person_husband",
    ],
    # Sibling patterns - symmetric relationship
    RelationType.SIBLING_OF: [
        r"person_brother",
        r"person_sister",
        r"person_sibling",
    ],
}


def _infer_from_name_pattern(
    actor_id: str,
    participant_id: str,
) -> Optional[InferredRelationship]:
    """
    Infer relationship from person ID naming patterns.

    Examples:
        - "person_mom" -> PARENT_OF (from actor's perspective: they are parent)
        - "person_wife" -> SPOUSE_OF
        - "person_kid_emma" -> CHILD_OF (from actor's perspective: they are child)

    Args:
        actor_id: The actor (owner) of the event
        participant_id: The participant to infer relationship for

    Returns:
        InferredRelationship if pattern matches, None otherwise
    """
    participant_lower = participant_id.lower()

    for rel_type, patterns in FAMILY_NAME_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, participant_lower):
                # Map to actor's perspective
                # If participant is "person_mom", they are actor's PARENT
                # If participant is "person_kid", they are actor's CHILD
                actual_rel = _map_name_to_actor_perspective(rel_type)

                return InferredRelationship(
                    person_id=actor_id,
                    related_person_id=participant_id,
                    relationship_type=actual_rel,
                    confidence=0.6,  # Name pattern is moderate confidence
                    inference_method="name_pattern",
                    explanation=f"Name '{participant_id}' matches {rel_type.value} pattern",
                    supporting_evidence={"pattern": pattern, "matched": True},
                )

    return None


def _map_name_to_actor_perspective(rel_type: RelationType) -> RelationType:
    """
    Map name-derived relationship to actor's perspective.

    If participant is named "person_mom", from actor's view:
    - The relationship stored would be PARENT_OF (actor is parent of them? NO)
    - Actually: participant IS actor's parent, so actor has CHILD_OF relationship
    - But we store relationships as (actor -> related_person, type)
    - So if person_mom is related to actor as "parent", type = CHILD_OF
      (because actor is child of person_mom)

    Wait, the st_relationships stores: person_id -> related_person_id, relationship_type
    where relationship_type describes how person_id relates TO related_person_id.

    So for actor "person_prince" and participant "person_mom":
    - We infer person_prince CHILD_OF person_mom? No, inverse.
    - person_prince has person_mom as related, type = CHILD_OF means
      person_prince is CHILD OF person_mom

    Actually checking the existing code:
    - rel_type == "PARENT_OF" -> roles[participant_id] = "CHILD"
    - So if actor PARENT_OF participant, participant role is CHILD

    For name inference:
    - participant named "person_mom" means they ARE a parent
    - So from actor's perspective, actor is CHILD_OF person_mom
    - We return CHILD_OF (actor is child of this person)
    """
    # Name indicates participant's role, we need actor's relationship to them
    mapping = {
        RelationType.PARENT_OF: RelationType.CHILD_OF,  # If they're parent, actor is child
        RelationType.CHILD_OF: RelationType.PARENT_OF,  # If they're child, actor is parent
        RelationType.SPOUSE_OF: RelationType.SPOUSE_OF,  # Symmetric
        RelationType.SIBLING_OF: RelationType.SIBLING_OF,  # Symmetric
        RelationType.CARETAKER_OF: RelationType.CARETAKER_OF,  # Keep as is for now
    }
    return mapping.get(rel_type, rel_type)


# ============================================================================
# Co-occurrence Based Inference
# ============================================================================


class CooccurrenceInference:
    """
    Infer relationships from co-occurrence patterns in events.

    Based on research:
    - Frequent co-occurrence suggests close relationship
    - Event type distribution indicates relationship type
    - Meal events with small groups suggest family
    - Work events suggest colleagues
    """

    # Event type to likely relationship mapping
    EVENT_TYPE_WEIGHTS = {
        "meal": {
            RelationType.SPOUSE_OF: 0.3,
            RelationType.PARENT_OF: 0.3,
            RelationType.CHILD_OF: 0.3,
            RelationType.FRIEND: 0.1,
        },
        "celebration": {
            RelationType.SPOUSE_OF: 0.25,
            RelationType.PARENT_OF: 0.25,
            RelationType.CHILD_OF: 0.25,
            RelationType.FRIEND: 0.2,
            RelationType.SIBLING_OF: 0.05,
        },
        "outing": {
            RelationType.SPOUSE_OF: 0.2,
            RelationType.PARENT_OF: 0.2,
            RelationType.CHILD_OF: 0.2,
            RelationType.FRIEND: 0.4,
        },
        "work": {
            RelationType.COLLEAGUE: 0.8,
            RelationType.FRIEND: 0.2,
        },
        "medical": {
            RelationType.SPOUSE_OF: 0.4,
            RelationType.PARENT_OF: 0.3,
            RelationType.CHILD_OF: 0.2,
            RelationType.CARETAKER_OF: 0.1,
        },
    }

    # Minimum thresholds for inference
    MIN_SHARED_EVENTS = 2
    MIN_COOCCURRENCE_RATE = 0.25
    HIGH_CONFIDENCE_THRESHOLD = 5  # 5+ shared events = high confidence

    def __init__(self):
        self._stats_cache: Dict[Tuple[str, str], CooccurrenceStats] = {}

    async def infer_from_cooccurrence(
        self,
        actor_id: str,
        participant_id: str,
        cooccurrence_stats: CooccurrenceStats,
    ) -> Optional[InferredRelationship]:
        """
        Infer relationship from co-occurrence statistics.

        Args:
            actor_id: The actor (event owner)
            participant_id: The participant to infer relationship for
            cooccurrence_stats: Pre-computed co-occurrence statistics

        Returns:
            InferredRelationship if inference possible, None otherwise
        """
        stats = cooccurrence_stats

        # Check significance thresholds
        if stats.shared_events < self.MIN_SHARED_EVENTS:
            return None

        if stats.cooccurrence_rate < self.MIN_COOCCURRENCE_RATE:
            return None

        # Calculate relationship type probabilities from event types
        type_probs = self._calculate_type_probabilities(stats.event_types)

        if not type_probs:
            # Default to FRIEND if no event type info
            type_probs = {RelationType.FRIEND: 1.0}

        # Get most likely relationship type
        best_type = max(type_probs, key=lambda k: type_probs[k])
        best_prob = type_probs[best_type]

        # Calculate confidence based on evidence strength
        confidence = self._calculate_confidence(stats, best_prob)

        return InferredRelationship(
            person_id=actor_id,
            related_person_id=participant_id,
            relationship_type=best_type,
            confidence=confidence,
            inference_method="cooccurrence",
            explanation=self._generate_explanation(stats, best_type),
            supporting_evidence={
                "shared_events": stats.shared_events,
                "cooccurrence_rate": stats.cooccurrence_rate,
                "event_types": stats.event_types,
                "recency_score": stats.recency_score,
            },
        )

    def _calculate_type_probabilities(
        self,
        event_types: Dict[str, int],
    ) -> Dict[RelationType, float]:
        """Calculate relationship type probabilities from event type distribution."""
        if not event_types:
            return {}

        total_events = sum(event_types.values())
        type_scores: Dict[RelationType, float] = {}

        for event_type, count in event_types.items():
            weight = count / total_events
            type_weights = self.EVENT_TYPE_WEIGHTS.get(event_type, {})

            for rel_type, rel_weight in type_weights.items():
                if rel_type not in type_scores:
                    type_scores[rel_type] = 0.0
                type_scores[rel_type] += weight * rel_weight

        # Normalize to probabilities
        total_score = sum(type_scores.values())
        if total_score > 0:
            return {k: v / total_score for k, v in type_scores.items()}

        return type_scores

    def _calculate_confidence(
        self,
        stats: CooccurrenceStats,
        type_probability: float,
    ) -> float:
        """
        Calculate confidence score (0-1) based on evidence.

        Factors:
        - Number of shared events (more = higher confidence)
        - Co-occurrence rate (higher = more confident)
        - Type probability (how clear the relationship type is)
        - Recency (recent co-occurrences more relevant)
        """
        # Event count factor (logarithmic scaling, caps at ~0.9)
        event_factor = min(0.9, math.log1p(stats.shared_events) / math.log1p(20))

        # Co-occurrence rate factor
        rate_factor = min(1.0, stats.cooccurrence_rate / 0.5)

        # Type clarity factor
        type_factor = type_probability

        # Recency factor
        recency_factor = stats.recency_score

        # Weighted combination
        confidence = (
            0.35 * event_factor + 0.25 * rate_factor + 0.25 * type_factor + 0.15 * recency_factor
        )

        return round(min(1.0, max(0.0, confidence)), 3)

    def _generate_explanation(
        self,
        stats: CooccurrenceStats,
        rel_type: RelationType,
    ) -> str:
        """Generate human-readable explanation for inference."""
        rate_pct = int(stats.cooccurrence_rate * 100)
        events_str = "event" if stats.shared_events == 1 else "events"

        if stats.shared_events >= self.HIGH_CONFIDENCE_THRESHOLD:
            strength = "frequently"
        elif stats.shared_events >= 3:
            strength = "regularly"
        else:
            strength = "occasionally"

        return (
            f"Appears {strength} together ({stats.shared_events} shared {events_str}, "
            f"{rate_pct}% co-occurrence). "
            f"Event patterns suggest {rel_type.value.lower().replace('_', ' ')}."
        )


# ============================================================================
# Group Size Based Inference
# ============================================================================


def _infer_from_group_size(
    actor_id: str,
    participant_id: str,
    group_size: int,
    event_type: Optional[str],
) -> Optional[InferredRelationship]:
    """
    Infer relationship likelihood from group size and event type.

    Dunbar's research:
    - 2-person events: likely intimate (spouse, close family)
    - 3-5 person events: likely nuclear family or close friends
    - 6-15 person events: extended family or friend group
    - 15+ person events: acquaintances, work colleagues

    Args:
        actor_id: Event actor
        participant_id: Participant to infer
        group_size: Total participants in event
        event_type: Type of event (meal, celebration, etc.)

    Returns:
        InferredRelationship with low confidence, or None
    """
    # Only provide hints, not definitive inference
    if group_size == 2:
        # Two-person events strongly suggest close relationship
        if event_type in ("meal", "outing", "celebration"):
            return InferredRelationship(
                person_id=actor_id,
                related_person_id=participant_id,
                relationship_type=RelationType.SPOUSE_OF,
                confidence=0.4,  # Low confidence - just a hint
                inference_method="group_size",
                explanation=f"Two-person {event_type or 'event'} suggests close relationship",
                supporting_evidence={"group_size": group_size, "event_type": event_type},
            )

    return None


# ============================================================================
# Main Inference Engine
# ============================================================================


class RelationshipInferenceEngine:
    """
    Main engine for inferring relationships using multiple signals.

    Combines:
    1. Name pattern matching (highest priority)
    2. Co-occurrence analysis (primary method)
    3. Group size hints (supplementary)

    Future: GNN-based inference for complex patterns
    """

    def __init__(self):
        self.cooccurrence = CooccurrenceInference()

    async def infer_relationship(
        self,
        actor_id: str,
        participant_id: str,
        cooccurrence_stats: Optional[CooccurrenceStats] = None,
        event_type: Optional[str] = None,
        group_size: int = 2,
    ) -> Optional[InferredRelationship]:
        """
        Infer likely relationship between actor and participant.

        Tries inference methods in order of reliability:
        1. Name pattern (if participant ID contains family role)
        2. Co-occurrence (if stats available)
        3. Group size (fallback hint)

        Args:
            actor_id: The event actor/owner
            participant_id: Participant to infer relationship for
            cooccurrence_stats: Optional pre-computed co-occurrence data
            event_type: Optional event type for context
            group_size: Number of participants in current event

        Returns:
            InferredRelationship with best inference, or None if no inference possible
        """
        # Skip self-inference
        if actor_id == participant_id:
            return None

        # Method 1: Name pattern (fast, moderate confidence)
        name_inference = _infer_from_name_pattern(actor_id, participant_id)
        if name_inference and name_inference.confidence >= 0.5:
            return name_inference

        # Method 2: Co-occurrence (requires historical data)
        if cooccurrence_stats and cooccurrence_stats.is_significant:
            cooc_inference = await self.cooccurrence.infer_from_cooccurrence(
                actor_id, participant_id, cooccurrence_stats
            )
            if cooc_inference:
                # Boost confidence if name pattern also matched
                if name_inference:
                    cooc_inference.confidence = min(1.0, cooc_inference.confidence + 0.15)
                    cooc_inference.explanation += " (name pattern also matched)"
                return cooc_inference

        # Method 3: Group size hint (low confidence fallback)
        group_inference = _infer_from_group_size(actor_id, participant_id, group_size, event_type)
        if group_inference:
            return group_inference

        # No inference possible
        return None

    async def infer_all_relationships(
        self,
        actor_id: str,
        participants: List[str],
        cooccurrence_data: Optional[Dict[str, CooccurrenceStats]] = None,
        event_type: Optional[str] = None,
    ) -> Dict[str, InferredRelationship]:
        """
        Infer relationships for all participants.

        Args:
            actor_id: Event actor/owner
            participants: List of all participant IDs
            cooccurrence_data: Optional dict mapping participant_id -> CooccurrenceStats
            event_type: Optional event type for context

        Returns:
            Dict mapping participant_id -> InferredRelationship (only for inferred ones)
        """
        results = {}
        group_size = len(participants)

        for participant_id in participants:
            if participant_id == actor_id:
                continue

            stats = cooccurrence_data.get(participant_id) if cooccurrence_data else None

            inference = await self.infer_relationship(
                actor_id=actor_id,
                participant_id=participant_id,
                cooccurrence_stats=stats,
                event_type=event_type,
                group_size=group_size,
            )

            if inference:
                results[participant_id] = inference

        return results


# ============================================================================
# GNN Placeholder (Future Enhancement)
# ============================================================================


class GNNRelationshipInference:
    """
    Graph Neural Network for relationship inference.

    Research: Hamilton et al. (2017) - GraphSAGE
             Kipf & Welling (2016) - Graph Convolutional Networks

    Architecture (when implemented):
    - 2-layer GraphSAGE with mean aggregation
    - Node features: Person embeddings + activity history
    - Edge prediction: Binary classification (related/not)
    - Relation type: Multi-class classification

    Status: NOT IMPLEMENTED (placeholder for future enhancement)
    """

    def __init__(self):
        logger.info("GNNRelationshipInference initialized (placeholder - not implemented)")
        self._implemented = False

    def is_available(self) -> bool:
        """Check if GNN inference is available."""
        return self._implemented

    async def infer_relationship(
        self,
        person1: str,
        person2: str,
        graph_data: Any,
    ) -> Optional[InferredRelationship]:
        """
        Infer relationship using GNN (placeholder).

        When implemented, will use:
        - Node embeddings from GraphSAGE encoder
        - Edge predictor MLP for relationship existence
        - Relation classifier MLP for relationship type

        Raises:
            NotImplementedError: GNN not yet implemented
        """
        raise NotImplementedError(
            "GNN relationship inference not yet implemented. "
            "Use CooccurrenceInference for rule-based inference."
        )


# ============================================================================
# Module-Level API
# ============================================================================

# Singleton instance
_inference_engine: Optional[RelationshipInferenceEngine] = None


def get_inference_engine() -> RelationshipInferenceEngine:
    """Get singleton inference engine instance."""
    global _inference_engine
    if _inference_engine is None:
        _inference_engine = RelationshipInferenceEngine()
    return _inference_engine


async def infer_relationship(
    actor_id: str,
    participant_id: str,
    cooccurrence_stats: Optional[CooccurrenceStats] = None,
    event_type: Optional[str] = None,
    group_size: int = 2,
) -> Optional[InferredRelationship]:
    """
    Convenience function to infer a single relationship.

    See RelationshipInferenceEngine.infer_relationship for details.
    """
    engine = get_inference_engine()
    return await engine.infer_relationship(
        actor_id=actor_id,
        participant_id=participant_id,
        cooccurrence_stats=cooccurrence_stats,
        event_type=event_type,
        group_size=group_size,
    )


async def infer_all_relationships(
    actor_id: str,
    participants: List[str],
    cooccurrence_data: Optional[Dict[str, CooccurrenceStats]] = None,
    event_type: Optional[str] = None,
) -> Dict[str, InferredRelationship]:
    """
    Convenience function to infer all relationships.

    See RelationshipInferenceEngine.infer_all_relationships for details.
    """
    engine = get_inference_engine()
    return await engine.infer_all_relationships(
        actor_id=actor_id,
        participants=participants,
        cooccurrence_data=cooccurrence_data,
        event_type=event_type,
    )
