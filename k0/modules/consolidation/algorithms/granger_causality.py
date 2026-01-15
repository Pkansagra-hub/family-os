"""
GrangerCausalityInference - Simplified Granger causality for temporal patterns.

This module implements Granger causality inference for FamilyOS:
- If A consistently precedes B, infer A CAUSES B
- Distinguish causation from correlation via precedence ratio
- Persist causal edges to st_kg_edges

Spec Reference:
    - Dossier §4.5.4: Causal Inference (Granger Causality)
    - Dossier Appendix C.5.2: Granger Causality Algorithm
    - M4_EXECUTION.md Issue 4.4.9

Principle:
    If A consistently precedes B, and removing A reduces predictability of B,
    then A Granger-causes B.

    Simplified for FamilyOS: Use co-occurrence frequency with temporal ordering
    to infer causal direction.

Formula:
    precedence_ratio = a_before_b / (a_before_b + b_before_a + simultaneous)

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import List, Optional, Protocol, Tuple, runtime_checkable

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================


@dataclass(frozen=True)
class CausalityConfig:
    """
    Configuration for Granger causality inference.

    Defaults from Dossier §4.5.4 and M4_EXECUTION.md Issue 4.4.9:
        - min_observations: 5 (minimum observations for inference)
        - causality_threshold: 0.75 (default precedence threshold)
        - temporal_window_minutes: 60 (max time gap for causal consideration)
        - simultaneous_threshold_minutes: 1 (within this = simultaneous)
    """

    min_observations: int = 5
    causality_threshold: float = 0.75
    temporal_window_minutes: int = 60
    simultaneous_threshold_minutes: int = 1

    def validate(self) -> None:
        """Validate configuration values."""
        if self.min_observations < 1:
            raise ValueError(f"min_observations must be >= 1, got {self.min_observations}")
        if not 0.0 < self.causality_threshold < 1.0:
            raise ValueError(
                f"causality_threshold must be in (0, 1), got {self.causality_threshold}"
            )
        if self.temporal_window_minutes < 1:
            raise ValueError(
                f"temporal_window_minutes must be >= 1, got {self.temporal_window_minutes}"
            )
        if self.simultaneous_threshold_minutes < 0:
            raise ValueError(
                f"simultaneous_threshold_minutes must be >= 0, got {self.simultaneous_threshold_minutes}"
            )


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class CausalEdge:
    """
    Inferred causal relationship between two entities.

    From Dossier §4.5.4 and M4_EXECUTION.md Issue 4.4.9.
    """

    source_id: str
    target_id: str
    relation_type: str  # Always 'CAUSES'
    confidence: float
    observation_count: int
    precedence_ratio: float


@dataclass
class TemporalPrecedenceStats:
    """
    Statistics from temporal precedence analysis.

    Tracks how often A precedes B, B precedes A, or they occur simultaneously.
    """

    a_before_b: int
    b_before_a: int
    simultaneous: int
    total: int
    precedence_ratio: float


# =============================================================================
# Protocols
# =============================================================================


@runtime_checkable
class ObservationStore(Protocol):
    """Protocol for fetching co-occurrence timestamps."""

    async def get_cooccurrence_timestamps(
        self,
        entity_a: str,
        entity_b: str,
        db_conn,
    ) -> List[Tuple[int, int]]:
        """
        Get timestamp pairs for entity co-occurrences.

        Returns:
            List of (timestamp_a, timestamp_b) pairs in milliseconds
        """
        ...


@runtime_checkable
class DatabaseConnection(Protocol):
    """Protocol for database operations."""

    async def fetchrow(self, query: str, *args) -> Optional[dict]:
        """Fetch single row."""
        ...

    async def execute(self, query: str, *args) -> None:
        """Execute query."""
        ...


# =============================================================================
# Utility Functions
# =============================================================================


def now_ms() -> int:
    """Current time in milliseconds since Unix epoch."""
    return int(time.time() * 1000)


def generate_ulid() -> str:
    """
    Generate a ULID for new edge IDs.

    Uses time-based prefix for sortability.
    """
    import secrets

    # Time component (48 bits = 6 bytes)
    timestamp_ms = now_ms()
    time_bytes = timestamp_ms.to_bytes(6, byteorder="big")

    # Random component (80 bits = 10 bytes)
    random_bytes = secrets.token_bytes(10)

    # Combine and encode as base32
    ulid_bytes = time_bytes + random_bytes

    # Crockford base32 encoding
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    result = []
    value = int.from_bytes(ulid_bytes, byteorder="big")

    for _ in range(26):
        result.append(alphabet[value & 31])
        value >>= 5

    return "".join(reversed(result))


# =============================================================================
# GrangerCausalityInference
# =============================================================================


class GrangerCausalityInference:
    """
    Simplified Granger causality for temporal event patterns.

    Spec: Dossier Appendix C.5.2, M4_EXECUTION.md Issue 4.4.9

    Principle: If A consistently precedes B, and removing A
    reduces predictability of B, then A Granger-causes B.

    Simplified for FamilyOS: Use co-occurrence frequency
    with temporal ordering to infer causal direction.

    Example patterns:
        - Alarm (0.95) → Wake_up: Alarm CAUSES Wake_up
        - Coffee (0.82) → Work_start: Coffee CAUSES Work_start
        - Rain (0.55) ↔ Stay_home: No causal edge (correlation only)
    """

    def __init__(self, config: Optional[CausalityConfig] = None):
        """
        Initialize with optional config.

        Args:
            config: CausalityConfig instance, or None for defaults
        """
        self.config = config or CausalityConfig()
        self.config.validate()

    def compute_temporal_precedence(
        self,
        entity_a: str,
        entity_b: str,
        observations: List[Tuple[int, int]],
    ) -> TemporalPrecedenceStats:
        """
        Compute temporal precedence statistics.

        Applies the formula from Dossier §4.5.4:
            precedence_ratio = a_before_b / (a_before_b + b_before_a + simultaneous)

        Args:
            entity_a: First entity ID
            entity_b: Second entity ID
            observations: List of (ts_a, ts_b) timestamp pairs in milliseconds

        Returns:
            TemporalPrecedenceStats with counts and ratio

        Note:
            - diff_minutes > 0 means A happened before B
            - diff_minutes < 0 means B happened before A
            - abs(diff_minutes) < threshold means simultaneous
        """
        a_before_b = 0
        b_before_a = 0
        simultaneous = 0

        for ts_a, ts_b in observations:
            # Convert milliseconds to minutes
            diff_minutes = (ts_b - ts_a) / 60000.0

            if abs(diff_minutes) < self.config.simultaneous_threshold_minutes:
                simultaneous += 1
            elif diff_minutes > 0:
                # A happened first (ts_a < ts_b means ts_b - ts_a > 0)
                a_before_b += 1
            else:
                # B happened first
                b_before_a += 1

        total = a_before_b + b_before_a + simultaneous

        # Default to 0.5 if no observations (neutral)
        precedence_ratio = a_before_b / total if total > 0 else 0.5

        logger.debug(
            f"Precedence stats for {entity_a} → {entity_b}: "
            f"a_before_b={a_before_b}, b_before_a={b_before_a}, "
            f"simultaneous={simultaneous}, ratio={precedence_ratio:.3f}"
        )

        return TemporalPrecedenceStats(
            a_before_b=a_before_b,
            b_before_a=b_before_a,
            simultaneous=simultaneous,
            total=total,
            precedence_ratio=precedence_ratio,
        )

    def infer_causal_direction(
        self,
        entity_a: str,
        entity_b: str,
        observations: List[Tuple[int, int]],
        config: Optional[CausalityConfig] = None,
    ) -> Optional[CausalEdge]:
        """
        Infer causal direction between entities.

        Logic (from M4_EXECUTION.md Issue 4.4.9):
            - If observations < min_observations: return None
            - If precedence_ratio >= threshold: A CAUSES B
            - If precedence_ratio <= (1 - threshold): B CAUSES A
            - Otherwise: No clear causal direction

        Args:
            entity_a: First entity ID
            entity_b: Second entity ID
            observations: List of (ts_a, ts_b) timestamp pairs
            config: Optional override config

        Returns:
            CausalEdge if strong temporal pattern found, None otherwise
        """
        cfg = config or self.config

        # Check minimum observations
        if len(observations) < cfg.min_observations:
            logger.debug(
                f"Insufficient observations for {entity_a} → {entity_b}: "
                f"{len(observations)} < {cfg.min_observations}"
            )
            return None

        stats = self.compute_temporal_precedence(entity_a, entity_b, observations)

        # Strong precedence = likely causal (A → B)
        if stats.precedence_ratio >= cfg.causality_threshold:
            logger.info(
                f"Inferred causality: {entity_a} CAUSES {entity_b} "
                f"(ratio={stats.precedence_ratio:.2f}, threshold={cfg.causality_threshold})"
            )
            return CausalEdge(
                source_id=entity_a,
                target_id=entity_b,
                relation_type="CAUSES",
                confidence=stats.precedence_ratio,
                observation_count=len(observations),
                precedence_ratio=stats.precedence_ratio,
            )

        # Reverse direction (B → A)
        if stats.precedence_ratio <= (1 - cfg.causality_threshold):
            reverse_confidence = 1 - stats.precedence_ratio
            logger.info(
                f"Inferred reverse causality: {entity_b} CAUSES {entity_a} "
                f"(ratio={stats.precedence_ratio:.2f} → reverse={reverse_confidence:.2f})"
            )
            return CausalEdge(
                source_id=entity_b,
                target_id=entity_a,
                relation_type="CAUSES",
                confidence=reverse_confidence,
                observation_count=len(observations),
                precedence_ratio=reverse_confidence,
            )

        # No clear causal direction (correlation only)
        logger.debug(
            f"No causal direction for {entity_a} ↔ {entity_b}: "
            f"ratio={stats.precedence_ratio:.2f} (threshold={cfg.causality_threshold})"
        )
        return None

    async def analyze_cooccurrence_pairs(
        self,
        cooccurrence_pairs: List[Tuple[str, str]],
        observation_store: ObservationStore,
        db_conn: DatabaseConnection,
    ) -> List[CausalEdge]:
        """
        Analyze all co-occurrence pairs for causality.

        Processes each pair from Hebbian learning and infers causal edges.

        Args:
            cooccurrence_pairs: Entity ID pairs from Hebbian learning
            observation_store: Source of timestamp observations
            db_conn: Database connection for fetching observations

        Returns:
            List of inferred CausalEdge objects
        """
        causal_edges: List[CausalEdge] = []
        pairs_analyzed = 0
        pairs_with_causality = 0

        for entity_a, entity_b in cooccurrence_pairs:
            pairs_analyzed += 1

            # Fetch temporal observations for this pair
            try:
                observations = await observation_store.get_cooccurrence_timestamps(
                    entity_a, entity_b, db_conn
                )
            except Exception as e:
                logger.warning(f"Failed to fetch observations for {entity_a} ↔ {entity_b}: {e}")
                continue

            edge = self.infer_causal_direction(entity_a, entity_b, observations)
            if edge:
                causal_edges.append(edge)
                pairs_with_causality += 1

        logger.info(
            f"Granger causality: {pairs_with_causality} causal edges "
            f"from {pairs_analyzed} pairs analyzed"
        )

        return causal_edges

    async def persist_causal_edges(
        self,
        causal_edges: List[CausalEdge],
        space_id: str,
        db_conn: DatabaseConnection,
    ) -> int:
        """
        Persist inferred causal edges to st_kg_edges.

        Creates new edges or updates existing ones.

        Args:
            causal_edges: List of CausalEdge to persist
            space_id: Space ID for new edges
            db_conn: Database connection

        Returns:
            Count of edges created/updated
        """
        count = 0

        for edge in causal_edges:
            try:
                # Check if edge already exists
                existing = await db_conn.fetchrow(
                    """
                    SELECT edge_id, observation_count FROM st_kg_edges
                    WHERE source_entity_id = $1
                      AND target_entity_id = $2
                      AND relation_type = 'CAUSES'
                    """,
                    edge.source_id,
                    edge.target_id,
                )

                if existing:
                    # Update existing edge
                    await db_conn.execute(
                        """
                        UPDATE st_kg_edges
                        SET causal_confidence = $1,
                            observation_count = $2,
                            precedence_ratio = $3,
                            updated_at = $4
                        WHERE edge_id = $5
                        """,
                        edge.confidence,
                        edge.observation_count,
                        edge.precedence_ratio,
                        now_ms(),
                        existing["edge_id"],
                    )
                    logger.debug(
                        f"Updated causal edge {existing['edge_id']}: "
                        f"{edge.source_id} → {edge.target_id} "
                        f"(confidence={edge.confidence:.2f})"
                    )
                else:
                    # Create new causal edge
                    new_edge_id = generate_ulid()
                    await db_conn.execute(
                        """
                        INSERT INTO st_kg_edges (
                            edge_id, source_entity_id, target_entity_id,
                            relation_type, edge_type, causal_confidence,
                            observation_count, precedence_ratio,
                            space_id, created_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                        """,
                        new_edge_id,
                        edge.source_id,
                        edge.target_id,
                        "CAUSES",
                        "CAUSAL",
                        edge.confidence,
                        edge.observation_count,
                        edge.precedence_ratio,
                        space_id,
                        now_ms(),
                    )
                    logger.debug(
                        f"Created causal edge {new_edge_id}: "
                        f"{edge.source_id} → {edge.target_id} "
                        f"(confidence={edge.confidence:.2f})"
                    )

                count += 1

            except Exception as e:
                logger.error(
                    f"Failed to persist causal edge {edge.source_id} → {edge.target_id}: {e}"
                )

        logger.info(f"Persisted {count} causal edges to st_kg_edges")
        return count
