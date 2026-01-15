"""
HebbianLearner - Hebbian learning for knowledge graph edge weights.

This module implements Hebbian learning ("cells that fire together, wire together")
for strengthening knowledge graph edges between frequently co-occurring entities.
Also implements anti-Hebbian decay for weakening wrong associations.

Spec Reference:
    - Dossier §4.2.3: Association Strengthening (Hebbian Learning)
    - Dossier Appendix C.2.2: Hebbian Learning Algorithm
    - Dossier Appendix C.2.2.1: Anti-Hebbian Decay
    - M4_EXECUTION.md Issues 4.1.3, 4.1.4

Principles:
    - Hebbian: Entities appearing together strengthen connections
    - Anti-Hebbian: Wrong associations weaken/prune connections
    - Soft saturation: Weights approach max_weight asymptotically
    - Exponential decay: Unused edges decay over time

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Protocol, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================


@dataclass(frozen=True)
class HebbianConfig:
    """
    Configuration for Hebbian learning.

    Defaults from Dossier Appendix C.2.2:
        - learning_rate: 0.1 (how much each co-occurrence strengthens)
        - decay_rate: 0.01 (how much unused edges weaken per day)
        - max_weight: 1.0 (weight cap to prevent runaway)
        - min_weight: 0.01 (below this, edge is pruned)

    Anti-Hebbian (from Dossier C.2.2.1):
        - anti_learning_rate: 0.15 (faster than positive learning)
        - explicit_correction_multiplier: 1.3 (boost for user corrections)
        - prune_threshold: 0.05 (below this, mark for archive)
    """

    # Positive (Hebbian) learning
    learning_rate: float = 0.1
    decay_rate: float = 0.01
    max_weight: float = 1.0
    min_weight: float = 0.01

    # Anti-Hebbian learning
    anti_learning_rate: float = 0.15
    explicit_correction_multiplier: float = 1.3
    prune_threshold: float = 0.05

    def validate(self) -> None:
        """Validate configuration values."""
        if not 0.0 < self.learning_rate <= 1.0:
            raise ValueError(f"learning_rate must be in (0, 1], got {self.learning_rate}")
        if not 0.0 <= self.decay_rate <= 1.0:
            raise ValueError(f"decay_rate must be in [0, 1], got {self.decay_rate}")
        if not 0.0 < self.max_weight <= 1.0:
            raise ValueError(f"max_weight must be in (0, 1], got {self.max_weight}")
        if not 0.0 <= self.min_weight < self.max_weight:
            raise ValueError(f"min_weight must be in [0, max_weight), got {self.min_weight}")
        if not 0.0 < self.anti_learning_rate <= 1.0:
            raise ValueError(f"anti_learning_rate must be in (0, 1], got {self.anti_learning_rate}")


# =============================================================================
# Types and Protocols
# =============================================================================


class RelationType(str, Enum):
    """
    Edge relationship types for knowledge graph.

    From Dossier Appendix C.2.2:
        - INTERACTS_WITH: Actor-Actor co-occurrence
        - FREQUENTS: Actor-Location co-occurrence
        - DISCUSSES: Actor-Topic (NER entity) co-occurrence
    """

    INTERACTS_WITH = "INTERACTS_WITH"
    FREQUENTS = "FREQUENTS"
    DISCUSSES = "DISCUSSES"


class AntiHebbianSignal(str, Enum):
    """
    Signal types that trigger anti-Hebbian decay.

    From Dossier Appendix C.2.2.1:
        - ENTITY_MERGE_REJECTED: P06/User rejects entity merge
        - ASSOCIATION_WRONG: K1 correction of wrong association
        - MUTUAL_EXCLUSION: P03 R4 detects mutual exclusion
        - CONTRADICTION: P03 R7 detects contradiction
    """

    ENTITY_MERGE_REJECTED = "ENTITY_MERGE_REJECTED"
    ASSOCIATION_WRONG = "ASSOCIATION_WRONG"
    MUTUAL_EXCLUSION = "MUTUAL_EXCLUSION"
    CONTRADICTION = "CONTRADICTION"


# Penalty lookup for anti-Hebbian signals (from Dossier C.2.2.1)
ANTI_HEBBIAN_PENALTIES: Dict[AntiHebbianSignal, float] = {
    AntiHebbianSignal.ENTITY_MERGE_REJECTED: 0.2,
    AntiHebbianSignal.ASSOCIATION_WRONG: 0.3,
    AntiHebbianSignal.MUTUAL_EXCLUSION: 0.4,
    AntiHebbianSignal.CONTRADICTION: 0.15,
}


@dataclass
class KGEdge:
    """
    Represents a knowledge graph edge for Hebbian updates.

    Mirrors st_kg_edges schema from migration 0033.
    """

    edge_id: str
    source_id: str
    target_id: str
    relation_type: str
    weight: float
    co_occurrence_count: int = 1
    last_updated_at: int = 0  # Milliseconds timestamp
    space_id: str = ""
    tenant_id: str = ""
    archival_status: str = "ACTIVE"


@dataclass
class EdgeUpdate:
    """
    Aggregated edge update from batch processing.

    Tracks co-occurrences and importance sums across a batch of events.
    """

    source_id: str
    target_id: str
    relation_type: str
    cooccurrence_count: int = 0
    importance_sum: float = 0.0

    @property
    def avg_importance(self) -> float:
        """Average importance across all co-occurrences."""
        if self.cooccurrence_count == 0:
            return 0.0
        return self.importance_sum / self.cooccurrence_count


@dataclass
class CoOccurrence:
    """Single co-occurrence between two entities."""

    source_id: str
    target_id: str
    relation_type: RelationType
    event_importance: float = 0.0


class EventLike(Protocol):
    """
    Protocol for event objects that can be processed by HebbianLearner.

    Defines minimal interface needed for co-occurrence extraction.
    P03EventState implements this implicitly.
    """

    @property
    def event_id(self) -> str:
        """Unique event identifier."""
        ...

    @property
    def importance_score(self) -> float:
        """Importance score from R1 ImportanceScorer."""
        ...

    @property
    def ner_entities_json(self) -> str:
        """JSON array of NER entities."""
        ...

    def add_hebbian_update(
        self,
        source_entity_id: str,
        target_entity_id: str,
        old_weight: float,
        new_weight: float,
        update_type: str,
    ) -> None:
        """Record a Hebbian edge update."""
        ...


# =============================================================================
# NER Entity Parsing
# =============================================================================


@dataclass
class ParsedEntity:
    """Parsed entity from NER JSON."""

    entity_id: str
    entity_type: str  # PERSON, LOCATION, ORG, etc.
    text: str = ""
    confidence: float = 1.0


def parse_ner_entities(ner_json: str) -> List[ParsedEntity]:
    """
    Parse NER entities from JSON string.

    Expected JSON format (from P02 NLP):
    [
        {"entity_id": "...", "type": "PERSON", "text": "John"},
        {"entity_id": "...", "type": "LOCATION", "text": "Home"},
        ...
    ]

    Args:
        ner_json: JSON array string of NER entities

    Returns:
        List of ParsedEntity objects
    """
    if not ner_json or ner_json == "[]":
        return []

    try:
        entities = json.loads(ner_json)
        if not isinstance(entities, list):
            logger.warning("NER JSON is not a list: %s", type(entities))
            return []

        parsed = []
        for ent in entities:
            if isinstance(ent, dict):
                entity_id = ent.get("entity_id") or ent.get("id") or ""
                entity_type = ent.get("type") or ent.get("entity_type") or "UNKNOWN"
                text = ent.get("text") or ent.get("name") or ""
                confidence = ent.get("confidence", 1.0)

                if entity_id:
                    parsed.append(
                        ParsedEntity(
                            entity_id=entity_id,
                            entity_type=entity_type.upper(),
                            text=text,
                            confidence=float(confidence),
                        )
                    )
            elif isinstance(ent, str):
                # Simple string entity ID
                parsed.append(ParsedEntity(entity_id=ent, entity_type="UNKNOWN"))

        return parsed

    except json.JSONDecodeError as e:
        logger.warning("Failed to parse NER JSON: %s", e)
        return []


# =============================================================================
# HebbianLearner Implementation
# =============================================================================


class HebbianLearner:
    """
    Implements Hebbian learning for knowledge graph edge weights.

    Principle: "Cells that fire together, wire together" (Hebb, 1949)

    In FamilyOS context: Entities (people, places, concepts) that
    appear together in events strengthen their connection.

    Also implements anti-Hebbian decay ("cells that fire apart, unwire")
    for weakening wrong associations based on feedback signals.

    Usage:
        learner = HebbianLearner()

        # Extract co-occurrences from event
        cooccurrences = learner.extract_cooccurrences(event)

        # Update edge weight
        new_weight, new_count = learner.update_edge_weight(
            current_weight=0.5,
            current_count=10,
            event_importance=0.8,
        )

        # Process batch of events
        edge_updates = learner.process_batch(events)

        # Apply anti-Hebbian decay
        new_weight, should_prune = learner.apply_anti_decay(
            edge, signal_type="ASSOCIATION_WRONG", confidence=0.9
        )
    """

    def __init__(self, config: Optional[HebbianConfig] = None) -> None:
        """
        Initialize HebbianLearner with configuration.

        Args:
            config: Optional configuration; uses defaults if None
        """
        self.config = config or HebbianConfig()
        self.config.validate()

    # =========================================================================
    # Co-occurrence Extraction
    # =========================================================================

    def extract_cooccurrences(
        self,
        event: EventLike,
        actor_ids: Optional[List[str]] = None,
        location_entity_id: Optional[str] = None,
    ) -> List[CoOccurrence]:
        """
        Extract all entity pairs that co-occur in an event.

        Co-occurrence types:
            - INTERACTS_WITH: Actor-Actor (social relationships)
            - FREQUENTS: Actor-Location
            - DISCUSSES: Actor-Topic (from NER entities)

        Args:
            event: Event with NER entities and importance score
            actor_ids: Optional explicit actor IDs (if not in NER)
            location_entity_id: Optional explicit location entity ID

        Returns:
            List of co-occurrences with (source, target, relation_type)
        """
        cooccurrences: List[CoOccurrence] = []
        importance = event.importance_score

        # Parse NER entities
        parsed_entities = parse_ner_entities(event.ner_entities_json)

        # Separate entities by type
        actors = actor_ids or []
        location = location_entity_id
        topics: List[str] = []

        for entity in parsed_entities:
            if entity.entity_type == "PERSON":
                if entity.entity_id not in actors:
                    actors.append(entity.entity_id)
            elif entity.entity_type == "LOCATION":
                if not location:
                    location = entity.entity_id
            else:
                # Topics: ORG, EVENT, PRODUCT, etc.
                topics.append(entity.entity_id)

        # Actor-Actor co-occurrences (combinations, not permutations)
        for i, actor_a in enumerate(actors):
            for actor_b in actors[i + 1 :]:
                cooccurrences.append(
                    CoOccurrence(
                        source_id=actor_a,
                        target_id=actor_b,
                        relation_type=RelationType.INTERACTS_WITH,
                        event_importance=importance,
                    )
                )

        # Actor-Location co-occurrences
        if location:
            for actor in actors:
                cooccurrences.append(
                    CoOccurrence(
                        source_id=actor,
                        target_id=location,
                        relation_type=RelationType.FREQUENTS,
                        event_importance=importance,
                    )
                )

        # Actor-Topic co-occurrences
        for actor in actors:
            for topic in topics:
                cooccurrences.append(
                    CoOccurrence(
                        source_id=actor,
                        target_id=topic,
                        relation_type=RelationType.DISCUSSES,
                        event_importance=importance,
                    )
                )

        return cooccurrences

    # =========================================================================
    # Hebbian Weight Updates (Positive Learning)
    # =========================================================================

    def update_edge_weight(
        self,
        current_weight: float,
        current_count: int,
        event_importance: float,
    ) -> Tuple[float, int]:
        """
        Hebbian weight update formula with soft saturation.

        Formula (Dossier C.2.2):
            delta = learning_rate × (max_weight - current_weight) × event_importance

        The (max_weight - current_weight) term prevents weights from
        exceeding max_weight (soft saturation approach).

        Args:
            current_weight: Current edge weight [0, 1]
            current_count: Current co-occurrence count
            event_importance: Importance score of triggering event [0, 1]

        Returns:
            Tuple of (new_weight, new_count)
        """
        # Clamp inputs
        current_weight = max(0.0, min(self.config.max_weight, current_weight))
        event_importance = max(0.0, min(1.0, event_importance))

        # Soft saturation formula: approaches max asymptotically
        delta = (
            self.config.learning_rate * (self.config.max_weight - current_weight) * event_importance
        )

        new_weight = current_weight + delta
        new_count = current_count + 1

        # Hard clamp to max_weight
        new_weight = min(self.config.max_weight, new_weight)

        logger.debug(
            "Hebbian update: %.4f -> %.4f (delta=%.4f, importance=%.4f)",
            current_weight,
            new_weight,
            delta,
            event_importance,
        )

        return (new_weight, new_count)

    def compute_initial_weight(self, avg_importance: float) -> float:
        """
        Compute initial weight for a new edge.

        Formula: initial_weight = learning_rate × avg_importance

        Args:
            avg_importance: Average importance of co-occurrence events

        Returns:
            Initial edge weight
        """
        avg_importance = max(0.0, min(1.0, avg_importance))
        return self.config.learning_rate * avg_importance

    # =========================================================================
    # Decay (Time-based Weakening)
    # =========================================================================

    def apply_decay(
        self,
        edges: List[KGEdge],
        days_since_update: int,
    ) -> Tuple[List[KGEdge], List[str]]:
        """
        Apply exponential decay to edges that haven't been reinforced.

        Formula (Dossier C.2.2):
            new_weight = weight × exp(-decay_rate × days)

        Edges below min_weight are pruned (soft delete).

        Args:
            edges: List of edges to decay
            days_since_update: Days since last reinforcement

        Returns:
            Tuple of (surviving_edges, pruned_edge_ids)
        """
        if days_since_update <= 0:
            return edges, []

        surviving: List[KGEdge] = []
        pruned: List[str] = []

        decay_factor = math.exp(-self.config.decay_rate * days_since_update)

        for edge in edges:
            new_weight = edge.weight * decay_factor

            if new_weight >= self.config.min_weight:
                edge.weight = new_weight
                surviving.append(edge)
                logger.debug(
                    "Decay edge %s: %.4f -> %.4f (factor=%.4f, days=%d)",
                    edge.edge_id,
                    edge.weight / decay_factor,
                    new_weight,
                    decay_factor,
                    days_since_update,
                )
            else:
                pruned.append(edge.edge_id)
                logger.debug(
                    "Prune edge %s: weight %.4f below min %.4f",
                    edge.edge_id,
                    new_weight,
                    self.config.min_weight,
                )

        return surviving, pruned

    # =========================================================================
    # Anti-Hebbian Decay (Negative Learning)
    # =========================================================================

    def apply_anti_decay(
        self,
        edge: KGEdge,
        signal_type: str,
        confidence: float = 1.0,
        is_explicit_correction: bool = False,
    ) -> Tuple[float, bool]:
        """
        Apply anti-Hebbian decay to weaken wrong associations.

        Formula (Dossier C.2.2.1):
            Δw = -anti_lr × current_weight × confidence × penalty × multiplier

        Where:
            - anti_lr = 0.15 (faster than positive learning)
            - penalty = lookup by signal_type
            - multiplier = 1.3 if explicit_correction else 1.0

        Args:
            edge: Edge to weaken
            signal_type: Type of anti-Hebbian signal (from AntiHebbianSignal)
            confidence: Confidence in the correction [0, 1]
            is_explicit_correction: True if user explicitly corrected

        Returns:
            Tuple of (new_weight, should_prune)
        """
        # Lookup penalty by signal type
        try:
            signal = AntiHebbianSignal(signal_type)
            penalty = ANTI_HEBBIAN_PENALTIES.get(signal, 0.1)
        except ValueError:
            # Unknown signal type, use default penalty
            logger.warning("Unknown anti-Hebbian signal type: %s", signal_type)
            penalty = 0.1

        # Clamp confidence
        confidence = max(0.0, min(1.0, confidence))

        # Apply explicit correction multiplier
        multiplier = self.config.explicit_correction_multiplier if is_explicit_correction else 1.0

        # Anti-Hebbian formula
        delta = -self.config.anti_learning_rate * edge.weight * confidence * penalty * multiplier

        new_weight = max(0.0, edge.weight + delta)

        # Prune threshold check
        should_prune = new_weight < self.config.prune_threshold

        logger.debug(
            "Anti-Hebbian decay: edge=%s, signal=%s, weight %.4f -> %.4f "
            "(delta=%.4f, penalty=%.2f, explicit=%s, prune=%s)",
            edge.edge_id,
            signal_type,
            edge.weight,
            new_weight,
            delta,
            penalty,
            is_explicit_correction,
            should_prune,
        )

        return new_weight, should_prune

    def get_penalty_for_signal(self, signal_type: str) -> float:
        """
        Get the penalty multiplier for a given signal type.

        Args:
            signal_type: Anti-Hebbian signal type

        Returns:
            Penalty value (0.1 if unknown)
        """
        try:
            signal = AntiHebbianSignal(signal_type)
            return ANTI_HEBBIAN_PENALTIES.get(signal, 0.1)
        except ValueError:
            return 0.1

    # =========================================================================
    # Batch Processing
    # =========================================================================

    def process_batch(
        self,
        events: List[EventLike],
        actor_ids_map: Optional[Dict[str, List[str]]] = None,
        location_ids_map: Optional[Dict[str, str]] = None,
    ) -> Dict[Tuple[str, str, str], EdgeUpdate]:
        """
        Process batch and compute all edge updates.

        Aggregates co-occurrences across all events, tracking cumulative
        counts and importance sums per unique edge.

        Args:
            events: List of events to process
            actor_ids_map: Optional mapping of event_id -> actor_ids
            location_ids_map: Optional mapping of event_id -> location_entity_id

        Returns:
            Dict mapping (source, target, rel_type) -> EdgeUpdate
        """
        actor_ids_map = actor_ids_map or {}
        location_ids_map = location_ids_map or {}

        edge_updates: Dict[Tuple[str, str, str], EdgeUpdate] = {}

        for event in events:
            # Get optional explicit IDs
            actor_ids = actor_ids_map.get(event.event_id)
            location_id = location_ids_map.get(event.event_id)

            # Extract co-occurrences
            cooccurrences = self.extract_cooccurrences(
                event,
                actor_ids=actor_ids,
                location_entity_id=location_id,
            )

            for cooc in cooccurrences:
                key = (cooc.source_id, cooc.target_id, cooc.relation_type.value)

                if key not in edge_updates:
                    edge_updates[key] = EdgeUpdate(
                        source_id=cooc.source_id,
                        target_id=cooc.target_id,
                        relation_type=cooc.relation_type.value,
                        cooccurrence_count=0,
                        importance_sum=0.0,
                    )

                edge_updates[key].cooccurrence_count += 1
                edge_updates[key].importance_sum += cooc.event_importance

                # Record update in event state for audit trail
                try:
                    event.add_hebbian_update(
                        source_entity_id=cooc.source_id,
                        target_entity_id=cooc.target_id,
                        old_weight=0.0,  # Populated during actual DB update
                        new_weight=0.0,  # Populated during actual DB update
                        update_type=cooc.relation_type.value,
                    )
                except AttributeError:
                    # Event doesn't have add_hebbian_update method
                    logger.debug(
                        "Event %s missing add_hebbian_update method",
                        getattr(event, "event_id", "unknown"),
                    )

        logger.info(
            "Processed batch of %d events, found %d unique edge updates",
            len(events),
            len(edge_updates),
        )

        return edge_updates

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def normalize_weight(self, weight: float) -> float:
        """
        Normalize weight to [0.0, 1.0] range.

        Args:
            weight: Weight value to normalize

        Returns:
            Normalized weight clamped to [0.0, 1.0]
        """
        return max(0.0, min(1.0, weight))

    def weight_interpretation(self, weight: float) -> str:
        """
        Get human-readable interpretation of edge weight.

        From Dossier C.2.2:
            - 0.80 - 1.00: Very Strong (best friends, family)
            - 0.50 - 0.79: Strong (colleagues, close friends)
            - 0.20 - 0.49: Moderate (acquaintances)
            - 0.01 - 0.19: Weak (one-time interactions)

        Args:
            weight: Edge weight [0, 1]

        Returns:
            Interpretation string
        """
        if weight >= 0.80:
            return "Very Strong"
        elif weight >= 0.50:
            return "Strong"
        elif weight >= 0.20:
            return "Moderate"
        elif weight >= self.config.min_weight:
            return "Weak"
        else:
            return "Negligible"
