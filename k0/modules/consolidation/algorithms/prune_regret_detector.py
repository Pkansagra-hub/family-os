"""
PruneRegretDetector — Detect when pruned entities are later queried.

Tracks pruned entities for 14 days and matches against incoming queries
to detect "regret" (when user needs data that was pruned).

Scientific Basis:
- Weekly patterns: Users may query data on 7-day cycles
- Biweekly patterns: Payday reminders (14-day cycle)
- 90% of regrets occur within 14 days (empirical observation)

Spec Reference:
- Dossier §4.4.2: Prune Regret Detection
- Dossier §6.19.1: st_pruned_entities schema
- M4_EXECUTION.md Issue 4.3.6

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

import numpy as np

# =============================================================================
# Constants
# =============================================================================

# Time constants
MS_PER_DAY = 24 * 60 * 60 * 1000  # 86,400,000 ms

# Retention periods (from Dossier §4.4.2)
DEFAULT_UNMATCHED_RETENTION_DAYS = 14
DEFAULT_MATCHED_RETENTION_DAYS = 30

# Match thresholds (from Dossier §4.4.2)
STRONG_MATCH_THRESHOLD = 0.90
LIKELY_MATCH_THRESHOLD = 0.85
SEMANTIC_MATCH_THRESHOLD = 0.80

# Default cleanup hour (2am)
DEFAULT_CLEANUP_HOUR = 2

# Storage alert threshold
DEFAULT_MAX_STORAGE_MB = 50

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================


class MatchType(Enum):
    """Match confidence levels for regret detection."""

    STRONG_MATCH = "STRONG_MATCH"  # cosine >= 0.90
    LIKELY_MATCH = "LIKELY_MATCH"  # cosine >= 0.85
    SEMANTIC_MATCH = "SEMANTIC_MATCH"  # cosine >= 0.80
    NO_MATCH = "NO_MATCH"  # cosine < 0.80


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class PrunedEntity:
    """
    A pruned entity tracked for regret detection.

    Corresponds to a row in st_pruned_entities.
    """

    prune_id: str
    entity_id: str
    entity_type: str
    canonical_name: str
    embedding: np.ndarray
    space_id: str
    layer_table: str
    decay_factor_at_prune: float
    lambda_at_prune: float
    pruned_at: int  # epoch ms
    matched_query_id: Optional[str] = None
    matched_at: Optional[int] = None
    match_type: Optional[MatchType] = None
    match_confidence: Optional[float] = None


@dataclass
class RegretMatch:
    """
    Result from regret detection when a query matches a pruned entity.
    """

    prune_id: str
    entity_id: str
    entity_type: str
    match_type: MatchType
    match_confidence: float
    query_id: str
    pruned_at: int
    matched_at: int
    canonical_name: str = ""
    layer_table: str = ""


@dataclass
class PruneRegretConfig:
    """
    Configuration for prune regret detection.

    Attributes:
        unmatched_retention_days: Days to keep unmatched pruned entities
        matched_retention_days: Days to keep matched (regret) entities
        strong_threshold: Cosine similarity threshold for STRONG_MATCH
        likely_threshold: Cosine similarity threshold for LIKELY_MATCH
        semantic_threshold: Cosine similarity threshold for SEMANTIC_MATCH
        cleanup_hour: Hour of day to run cleanup (0-23)
        max_storage_mb: Alert threshold for storage
    """

    unmatched_retention_days: int = DEFAULT_UNMATCHED_RETENTION_DAYS
    matched_retention_days: int = DEFAULT_MATCHED_RETENTION_DAYS
    strong_threshold: float = STRONG_MATCH_THRESHOLD
    likely_threshold: float = LIKELY_MATCH_THRESHOLD
    semantic_threshold: float = SEMANTIC_MATCH_THRESHOLD
    cleanup_hour: int = DEFAULT_CLEANUP_HOUR
    max_storage_mb: int = DEFAULT_MAX_STORAGE_MB

    def validate(self) -> None:
        """Validate configuration."""
        if self.unmatched_retention_days < 1:
            raise ValueError("unmatched_retention_days must be >= 1")
        if self.matched_retention_days < self.unmatched_retention_days:
            raise ValueError("matched_retention_days must be >= unmatched_retention_days")
        if not (0 < self.strong_threshold <= 1.0):
            raise ValueError("strong_threshold must be in (0, 1]")
        if not (0 < self.likely_threshold <= self.strong_threshold):
            raise ValueError("likely_threshold must be in (0, strong_threshold]")
        if not (0 < self.semantic_threshold <= self.likely_threshold):
            raise ValueError("semantic_threshold must be in (0, likely_threshold]")
        if not (0 <= self.cleanup_hour <= 23):
            raise ValueError("cleanup_hour must be in [0, 23]")


# =============================================================================
# Storage Protocol
# =============================================================================


@runtime_checkable
class PrunedEntityStoreProtocol(Protocol):
    """Protocol for pruned entity storage operations."""

    async def insert_pruned_entity(self, entity: PrunedEntity) -> None:
        """Insert a pruned entity."""
        ...

    async def get_unmatched_entities(self, space_id: str) -> List[PrunedEntity]:
        """Get unmatched pruned entities for a space."""
        ...

    async def update_match(
        self,
        prune_id: str,
        query_id: str,
        matched_at: int,
        match_type: MatchType,
        match_confidence: float,
    ) -> None:
        """Update a pruned entity with match information."""
        ...

    async def delete_old_entities(
        self,
        unmatched_cutoff_ms: int,
        matched_cutoff_ms: int,
    ) -> int:
        """Delete entities older than retention periods. Returns count deleted."""
        ...

    async def insert_feedback_signal(
        self,
        signal_type: str,
        entity_id: str,
        space_id: str,
        confidence: float,
        metadata: Dict[str, Any],
    ) -> None:
        """Insert a feedback signal."""
        ...


class InMemoryPrunedEntityStore:
    """
    In-memory implementation for testing.

    Not for production use.
    """

    def __init__(self) -> None:
        self._entities: Dict[str, PrunedEntity] = {}
        self._signals: List[Dict[str, Any]] = []

    async def insert_pruned_entity(self, entity: PrunedEntity) -> None:
        """Insert a pruned entity."""
        self._entities[entity.prune_id] = entity

    async def get_unmatched_entities(self, space_id: str) -> List[PrunedEntity]:
        """Get unmatched pruned entities for a space."""
        return [
            e for e in self._entities.values() if e.space_id == space_id and e.matched_at is None
        ]

    async def update_match(
        self,
        prune_id: str,
        query_id: str,
        matched_at: int,
        match_type: MatchType,
        match_confidence: float,
    ) -> None:
        """Update a pruned entity with match information."""
        if prune_id in self._entities:
            entity = self._entities[prune_id]
            entity.matched_query_id = query_id
            entity.matched_at = matched_at
            entity.match_type = match_type
            entity.match_confidence = match_confidence

    async def delete_old_entities(
        self,
        unmatched_cutoff_ms: int,
        matched_cutoff_ms: int,
    ) -> int:
        """Delete entities older than retention periods."""
        to_delete = []
        for prune_id, entity in self._entities.items():
            if entity.matched_at is None:
                # Unmatched: delete if pruned before unmatched_cutoff
                if entity.pruned_at < unmatched_cutoff_ms:
                    to_delete.append(prune_id)
            else:
                # Matched: delete if matched before matched_cutoff
                if entity.matched_at < matched_cutoff_ms:
                    to_delete.append(prune_id)

        for prune_id in to_delete:
            del self._entities[prune_id]

        return len(to_delete)

    async def insert_feedback_signal(
        self,
        signal_type: str,
        entity_id: str,
        space_id: str,
        confidence: float,
        metadata: Dict[str, Any],
    ) -> None:
        """Insert a feedback signal."""
        self._signals.append(
            {
                "signal_type": signal_type,
                "entity_id": entity_id,
                "space_id": space_id,
                "confidence": confidence,
                "metadata": metadata,
            }
        )

    def get_entity(self, prune_id: str) -> Optional[PrunedEntity]:
        """Get entity by prune_id (for testing)."""
        return self._entities.get(prune_id)

    def get_all_entities(self) -> List[PrunedEntity]:
        """Get all entities (for testing)."""
        return list(self._entities.values())

    def get_signals(self) -> List[Dict[str, Any]]:
        """Get all feedback signals (for testing)."""
        return self._signals.copy()


# =============================================================================
# PrunedEntityTracker
# =============================================================================


class PrunedEntityTracker:
    """
    Track pruned entities for regret detection.

    Called when an entity transitions to TOMBSTONE status during R3 decay.
    Stores entity metadata and embedding for later query matching.

    Spec: Dossier §6.19.3
    """

    def __init__(self, config: Optional[PruneRegretConfig] = None) -> None:
        self._config = config or PruneRegretConfig()
        self._config.validate()

    async def track_pruned_entity(
        self,
        entity_id: str,
        entity_type: str,
        canonical_name: str,
        embedding: np.ndarray,
        space_id: str,
        layer_table: str,
        decay_factor: float,
        lambda_value: float,
        pruned_at: int,
        store: PrunedEntityStoreProtocol,
    ) -> str:
        """
        Track a pruned entity for regret detection.

        Called from R3 when entity transitions to TOMBSTONE.

        Args:
            entity_id: Original entity ID
            entity_type: PERSON, PLACE, THING, etc.
            canonical_name: Normalized name for fuzzy matching
            embedding: Entity embedding (1024 dims)
            space_id: Space isolation
            layer_table: Source table (st_epi, st_sem, etc.)
            decay_factor: Decay factor at time of pruning
            lambda_value: Lambda value used
            pruned_at: Timestamp when pruned (epoch ms)
            store: Storage implementation

        Returns:
            prune_id: Unique identifier for this prune event
        """
        prune_id = f"prune_{uuid.uuid4().hex[:16]}"

        entity = PrunedEntity(
            prune_id=prune_id,
            entity_id=entity_id,
            entity_type=entity_type,
            canonical_name=canonical_name,
            embedding=embedding,
            space_id=space_id,
            layer_table=layer_table,
            decay_factor_at_prune=decay_factor,
            lambda_at_prune=lambda_value,
            pruned_at=pruned_at,
        )

        await store.insert_pruned_entity(entity)

        logger.debug(
            "Tracked pruned entity",
            extra={
                "prune_id": prune_id,
                "entity_id": entity_id,
                "entity_type": entity_type,
                "space_id": space_id,
                "layer_table": layer_table,
            },
        )

        return prune_id


# =============================================================================
# PruneRegretDetector
# =============================================================================


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """
    Compute cosine similarity between two vectors.

    Returns value in [-1, 1], where 1 = identical, 0 = orthogonal, -1 = opposite.
    """
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return float(np.dot(a, b) / (norm_a * norm_b))


def classify_match(similarity: float, config: PruneRegretConfig) -> MatchType:
    """
    Classify match type based on cosine similarity.

    Args:
        similarity: Cosine similarity value
        config: Configuration with thresholds

    Returns:
        MatchType enum value
    """
    if similarity >= config.strong_threshold:
        return MatchType.STRONG_MATCH
    elif similarity >= config.likely_threshold:
        return MatchType.LIKELY_MATCH
    elif similarity >= config.semantic_threshold:
        return MatchType.SEMANTIC_MATCH
    else:
        return MatchType.NO_MATCH


class PruneRegretDetector:
    """
    Detect regret when query matches recently pruned entity.

    Checks incoming query embeddings against pruned entities to detect
    when user needs data that was pruned ("regret").

    Spec: Dossier §4.4.2
    """

    def __init__(self, config: Optional[PruneRegretConfig] = None) -> None:
        self._config = config or PruneRegretConfig()
        self._config.validate()

    async def check_query(
        self,
        query_embedding: np.ndarray,
        space_id: str,
        query_id: str,
        current_time_ms: int,
        store: PrunedEntityStoreProtocol,
    ) -> List[RegretMatch]:
        """
        Check if query matches any recently pruned entities.

        Algorithm (from Dossier §4.4.2):
        1. Query st_pruned_entities for unmatched entries in space
        2. Compute cosine similarity with query embedding
        3. If similarity >= semantic_threshold (0.80), classify match type
        4. If similarity >= likely_threshold (0.85), mark as regret
        5. Update st_pruned_entities with match info

        Args:
            query_embedding: Embedding of the query
            space_id: Space to search in
            query_id: Unique query identifier
            current_time_ms: Current timestamp in epoch ms
            store: Storage implementation

        Returns:
            List of RegretMatch objects for matches >= likely_threshold
        """
        # Get unmatched pruned entities for this space
        entities = await store.get_unmatched_entities(space_id)

        if not entities:
            return []

        matches: List[RegretMatch] = []

        for entity in entities:
            # Compute similarity
            similarity = cosine_similarity(query_embedding, entity.embedding)

            # Classify match type
            match_type = classify_match(similarity, self._config)

            # Only consider LIKELY_MATCH or STRONG_MATCH as regret
            # (SEMANTIC_MATCH at 0.80 is logged but not treated as regret)
            if match_type in (MatchType.STRONG_MATCH, MatchType.LIKELY_MATCH):
                # Update entity with match info
                await store.update_match(
                    prune_id=entity.prune_id,
                    query_id=query_id,
                    matched_at=current_time_ms,
                    match_type=match_type,
                    match_confidence=similarity,
                )

                match = RegretMatch(
                    prune_id=entity.prune_id,
                    entity_id=entity.entity_id,
                    entity_type=entity.entity_type,
                    match_type=match_type,
                    match_confidence=similarity,
                    query_id=query_id,
                    pruned_at=entity.pruned_at,
                    matched_at=current_time_ms,
                    canonical_name=entity.canonical_name,
                    layer_table=entity.layer_table,
                )

                matches.append(match)

                logger.info(
                    "Prune regret detected",
                    extra={
                        "prune_id": entity.prune_id,
                        "entity_id": entity.entity_id,
                        "query_id": query_id,
                        "match_type": match_type.value,
                        "confidence": similarity,
                        "space_id": space_id,
                    },
                )

        return matches

    async def emit_regret_signal(
        self,
        match: RegretMatch,
        space_id: str,
        store: PrunedEntityStoreProtocol,
    ) -> None:
        """
        Emit regret signal to st_feedback_signals for λ adjustment.

        Signal type: 'PRUNE_REGRET'
        This signal is consumed by P21 (Feedback Loop) to adjust decay rates.

        Args:
            match: The regret match to signal
            space_id: Space ID
            store: Storage implementation
        """
        metadata = {
            "prune_id": match.prune_id,
            "entity_type": match.entity_type,
            "match_type": match.match_type.value,
            "query_id": match.query_id,
            "pruned_at": match.pruned_at,
            "matched_at": match.matched_at,
            "canonical_name": match.canonical_name,
            "layer_table": match.layer_table,
        }

        await store.insert_feedback_signal(
            signal_type="PRUNE_REGRET",
            entity_id=match.entity_id,
            space_id=space_id,
            confidence=match.match_confidence,
            metadata=metadata,
        )

        logger.info(
            "Emitted PRUNE_REGRET signal",
            extra={
                "entity_id": match.entity_id,
                "prune_id": match.prune_id,
                "confidence": match.match_confidence,
                "space_id": space_id,
            },
        )


# =============================================================================
# PrunedEntitiesCleanup
# =============================================================================


class PrunedEntitiesCleanup:
    """
    Clean up old pruned entities.

    Runs daily (typically at 2am) to remove:
    - Unmatched entities older than 14 days
    - Matched entities (regrets) older than 30 days

    Spec: Dossier §6.19.4
    """

    def __init__(self, config: Optional[PruneRegretConfig] = None) -> None:
        self._config = config or PruneRegretConfig()
        self._config.validate()

    async def cleanup_old_pruned_entities(
        self,
        current_time_ms: int,
        store: PrunedEntityStoreProtocol,
    ) -> int:
        """
        Delete pruned entities older than retention period.

        - Unmatched: Delete after 14 days (configurable)
        - Matched (regrets): Keep for 30 days for analysis (configurable)

        Args:
            current_time_ms: Current time in epoch ms
            store: Storage implementation

        Returns:
            Count of deleted rows
        """
        # Calculate cutoffs
        unmatched_cutoff = current_time_ms - (self._config.unmatched_retention_days * MS_PER_DAY)
        matched_cutoff = current_time_ms - (self._config.matched_retention_days * MS_PER_DAY)

        deleted_count = await store.delete_old_entities(
            unmatched_cutoff_ms=unmatched_cutoff,
            matched_cutoff_ms=matched_cutoff,
        )

        logger.info(
            "Cleaned up old pruned entities",
            extra={
                "deleted_count": deleted_count,
                "unmatched_retention_days": self._config.unmatched_retention_days,
                "matched_retention_days": self._config.matched_retention_days,
            },
        )

        return deleted_count


# =============================================================================
# Utility Functions
# =============================================================================


def get_current_time_ms() -> int:
    """Get current time in milliseconds since epoch."""
    import time

    return int(time.time() * 1000)


def should_run_cleanup(current_hour: int, config: PruneRegretConfig) -> bool:
    """Check if cleanup should run based on configured hour."""
    return current_hour == config.cleanup_hour
