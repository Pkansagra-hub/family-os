"""
BGT-SM — Bisociative Graph Traversal for Semantic Memory.

This module implements the BGT-SM algorithm for R5 dream exploration,
discovering surprising connections between remote concepts through
random walks and information-theoretic surprise scoring.

Algorithm Flow:
1. Select seed entities from recent episodes (high importance/salience)
2. Execute random walk with restart (RWR) to explore knowledge graph
3. Identify remote associates (semantic distance > threshold)
4. Compute PMI (Pointwise Mutual Information) for surprise quantification
5. Calculate novelty score: distance × PMI / (visit_count + 1)
6. Generate human-readable insight descriptions
7. Return ranked insights above quality thresholds

Key Concepts:
- Bisociation: Connecting concepts from normally separate associative contexts
- PMI: log2((c_ab × N) / (c_a × c_b)) — measures co-occurrence surprise
- Remote Associates: Concepts with low semantic similarity but meaningful connection
- RWR: Random Walk with Restart — biased exploration with restart probability

References:
- M8_EXECUTION.md Issue 8.1.9: BGT-SM Bisociative Insight Generation
- M8_EXECUTION.md Issue 8.1.10: Insight Quality Thresholds + Ranking
- Dossier §4.6.4: Insight Generation (BGT-SM)
- Dossier Appendix C.6.3: BGT-SM (Insight Generation)
- Mednick (1962): The Associative Basis of the Creative Process
- Koestler (1964): The Act of Creation — Bisociation theory

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.

DETERMINISM:
- All random walks seeded with cycle_id for reproducibility
- Outputs sorted by novelty_score for deterministic ordering
- Co-occurrence counts are snapshot-consistent within cycle
"""

from __future__ import annotations

import math
import random
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from logging import getLogger
from typing import (
    TYPE_CHECKING,
    Dict,
    FrozenSet,
    List,
    Optional,
    Protocol,
    Set,
    Tuple,
    runtime_checkable,
)

from k0.pipelines.p03.context import generate_ulid

if TYPE_CHECKING:
    from k0.modules.consolidation.dream.config import DreamConfig
    from k0.modules.consolidation.dream.models import Insight

logger = getLogger(__name__)


# =============================================================================
# CONSTANTS (per Dossier Appendix C.6.3)
# =============================================================================

# Random Walk with Restart (RWR) parameters
P03_BGT_RESTART_PROBABILITY = 0.15  # Probability to restart at seed
P03_BGT_WALK_STEPS = 1000  # Steps per exploration walk
P03_BGT_MAX_WALKS_PER_SEED = 3  # Maximum walks per seed entity

# Thresholds (per Issue 8.1.9, 8.1.10, M3-E2 cold-start tuning)
# Lowered for cold-start: semantic 0.7->0.5, PMI 3.0->1.5, novelty 0.5->0.3
P03_BGT_SEMANTIC_DISTANCE_THRESHOLD = 0.5  # Min distance for remote associate (cold-start)
P03_BGT_PMI_THRESHOLD = 1.5  # Min PMI for surprising connection (2^1.5 = 3x expected)
P03_BGT_NOVELTY_THRESHOLD = 0.3  # Min novelty score to surface insight (cold-start)
P03_BGT_SERENDIPITY_THRESHOLD = 0.6  # novelty × relevance × actionability

# Default corpus size for PMI calculation
P03_BGT_DEFAULT_CORPUS_SIZE = 10000

# Cold start threshold (Issue 8.1.20, GAP-001 M9.1)
# Minimum corpus size required for meaningful PMI calculation
# Lowered from 10_000 to 100 for early-stage KG cold start support
P03_BGT_COLD_START_THRESHOLD = 100

# Insight generation limits
P03_BGT_MAX_INSIGHTS_PER_SEED = 5
P03_BGT_MAX_TOTAL_INSIGHTS = 20


# =============================================================================
# ENUMS
# =============================================================================


class InsightCategory(str, Enum):
    """Categories of bisociative insights."""

    OPPORTUNITY = "opportunity"  # Potential benefit from connection
    WARNING = "warning"  # Risk or concern from connection
    OPTIMIZATION = "optimization"  # Efficiency improvement
    PATTERN = "pattern"  # Recurring relationship discovered
    ANOMALY = "anomaly"  # Unexpected deviation from norm


class ConnectionType(str, Enum):
    """Types of discovered connections."""

    CAUSAL = "causal"  # A causes or influences B
    TEMPORAL = "temporal"  # A and B co-occur in time
    SEMANTIC = "semantic"  # A and B share meaning/context
    STRUCTURAL = "structural"  # A and B share graph topology
    BEHAVIORAL = "behavioral"  # A and B share action patterns


# =============================================================================
# PROTOCOLS
# =============================================================================


@runtime_checkable
class EntityProtocol(Protocol):
    """Protocol for knowledge graph entities."""

    @property
    def entity_id(self) -> str:
        """Unique entity identifier."""
        ...

    @property
    def entity_type(self) -> str:
        """Entity type (person, location, event, etc.)."""
        ...

    @property
    def name(self) -> str:
        """Human-readable entity name."""
        ...

    @property
    def observation_count(self) -> int:
        """Number of times entity has been observed."""
        ...


@runtime_checkable
class EdgeProtocol(Protocol):
    """Protocol for knowledge graph edges."""

    @property
    def source_id(self) -> str:
        """Source entity ID."""
        ...

    @property
    def target_id(self) -> str:
        """Target entity ID."""
        ...

    @property
    def relation_type(self) -> str:
        """Type of relationship."""
        ...

    @property
    def observation_count(self) -> int:
        """Number of times edge has been observed."""
        ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol for entity embedding retrieval."""

    def get_embedding(self, entity_id: str) -> Optional[List[float]]:
        """Get embedding vector for entity."""
        ...


# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass(frozen=True)
class BGTConfig:
    """
    Configuration for BGT-SM algorithm.

    Attributes:
        restart_probability: RWR restart probability (default: 0.15)
        walk_steps: Steps per random walk (default: 1000)
        max_walks_per_seed: Maximum walks from each seed (default: 3)
        semantic_distance_threshold: Min distance for remote associates (default: 0.7)
        pmi_threshold: Min PMI for surprising connections (default: 3.0)
        novelty_threshold: Min novelty score for insights (default: 0.5)
        corpus_size_n: Corpus size N for PMI calculation (default: 10000)
        max_insights_per_seed: Max insights from each seed (default: 5)
        max_total_insights: Max total insights to generate (default: 20)
        seed: RNG seed for determinism
    """

    restart_probability: float = P03_BGT_RESTART_PROBABILITY
    walk_steps: int = P03_BGT_WALK_STEPS
    max_walks_per_seed: int = P03_BGT_MAX_WALKS_PER_SEED
    semantic_distance_threshold: float = P03_BGT_SEMANTIC_DISTANCE_THRESHOLD
    pmi_threshold: float = P03_BGT_PMI_THRESHOLD
    novelty_threshold: float = P03_BGT_NOVELTY_THRESHOLD
    corpus_size_n: int = P03_BGT_DEFAULT_CORPUS_SIZE
    cold_start_threshold: int = P03_BGT_COLD_START_THRESHOLD
    max_insights_per_seed: int = P03_BGT_MAX_INSIGHTS_PER_SEED
    max_total_insights: int = P03_BGT_MAX_TOTAL_INSIGHTS
    seed: Optional[int] = None

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if not 0.0 < self.restart_probability < 1.0:
            raise ValueError("restart_probability must be between 0 and 1 (exclusive)")
        if self.walk_steps < 1:
            raise ValueError("walk_steps must be at least 1")
        if self.max_walks_per_seed < 1:
            raise ValueError("max_walks_per_seed must be at least 1")
        if not 0.0 <= self.semantic_distance_threshold <= 1.0:
            raise ValueError("semantic_distance_threshold must be between 0 and 1")
        if self.pmi_threshold < 0:
            raise ValueError("pmi_threshold must be non-negative")
        if self.corpus_size_n < 1:
            raise ValueError("corpus_size_n must be at least 1")


@dataclass
class VisitRecord:
    """Record of a node visit during random walk."""

    entity_id: str
    visit_count: int = 0
    first_visit_step: int = 0
    path_from_seed: Tuple[str, ...] = field(default_factory=tuple)


@dataclass
class RemoteAssociate:
    """
    A remote associate discovered through random walk.

    Remote associates are entities that are:
    1. Reachable from seed via graph traversal
    2. Semantically distant (low embedding similarity)
    3. Co-occur with seed more than expected (high PMI)
    """

    seed_entity_id: str
    target_entity_id: str
    visit_count: int
    semantic_distance: float
    pmi_score: float
    novelty_score: float
    connection_path: Tuple[str, ...]
    connection_type: ConnectionType = ConnectionType.SEMANTIC

    @property
    def is_surprising(self) -> bool:
        """Check if association meets surprise threshold."""
        return self.pmi_score >= P03_BGT_PMI_THRESHOLD

    @property
    def is_remote(self) -> bool:
        """Check if association is semantically remote."""
        return self.semantic_distance >= P03_BGT_SEMANTIC_DISTANCE_THRESHOLD


@dataclass
class BGTInsight:
    """
    A bisociative insight generated by BGT-SM.

    This is the algorithm's internal representation before
    conversion to the standard Insight model.

    Issue 8.1.10: Includes relevance and actionability for serendipity scoring.
    """

    insight_id: str
    source_entity_id: str
    target_entity_id: str
    source_entity_name: str
    target_entity_name: str
    semantic_distance: float
    pmi_score: float
    novelty_score: float
    insight_text: str
    category: InsightCategory
    connection_type: ConnectionType
    connection_path: Tuple[str, ...]
    supporting_evidence: Tuple[str, ...]
    confidence: float
    relevance_score: float = 0.5  # Issue 8.1.10: relevance for serendipity
    actionability_score: float = 0.5  # Issue 8.1.10: actionability for serendipity
    created_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    @property
    def serendipity_score(self) -> float:
        """Calculate serendipity: novelty × relevance × actionability."""
        return self.novelty_score * self.relevance_score * self.actionability_score

    def to_insight(self) -> "Insight":
        """Convert to standard Insight model with serendipity calculation."""
        from k0.modules.consolidation.dream.models import Insight

        return Insight.create(
            insight_id=self.insight_id,
            insight_type="ASSOCIATION",
            description=self.insight_text,
            confidence=self.confidence,
            supporting_evidence=list(self.supporting_evidence),
            novelty_score=self.novelty_score,
            concept_a_id=self.source_entity_id,
            concept_b_id=self.target_entity_id,
            pmi_score=self.pmi_score,
            coherence_score=1.0 - self.semantic_distance,
            semantic_distance=self.semantic_distance,
            relevance_score=self.relevance_score,
            actionability_score=self.actionability_score,
        )


# =============================================================================
# KNOWLEDGE GRAPH INTERFACE
# =============================================================================


class KnowledgeGraphView:
    """
    Read-only view of knowledge graph for BGT-SM traversal.

    Provides efficient neighbor lookup and co-occurrence statistics.
    """

    def __init__(
        self,
        entities: List[EntityProtocol],
        edges: List[EdgeProtocol],
    ) -> None:
        """
        Initialize graph view from entities and edges.

        Args:
            entities: List of knowledge graph entities
            edges: List of knowledge graph edges
        """
        self._entities: Dict[str, EntityProtocol] = {e.entity_id: e for e in entities}
        self._edges = edges

        # Build adjacency lists
        self._outgoing: Dict[str, List[EdgeProtocol]] = defaultdict(list)
        self._incoming: Dict[str, List[EdgeProtocol]] = defaultdict(list)
        for edge in edges:
            self._outgoing[edge.source_id].append(edge)
            self._incoming[edge.target_id].append(edge)

        # Build co-occurrence index (bidirectional edge counts)
        self._cooccurrence: Dict[FrozenSet[str], int] = defaultdict(int)
        for edge in edges:
            key = frozenset([edge.source_id, edge.target_id])
            self._cooccurrence[key] += edge.observation_count

        # Calculate corpus size (total entity observations)
        self._corpus_size = sum(e.observation_count for e in entities) or 1

    @property
    def corpus_size(self) -> int:
        """Total entity observations (corpus size N)."""
        return self._corpus_size

    def get_entity(self, entity_id: str) -> Optional[EntityProtocol]:
        """Get entity by ID."""
        return self._entities.get(entity_id)

    def get_entity_name(self, entity_id: str) -> str:
        """Get entity name, falling back to ID if not found."""
        entity = self._entities.get(entity_id)
        return entity.name if entity else entity_id

    def get_neighbors(self, entity_id: str) -> List[EdgeProtocol]:
        """Get outgoing edges from entity."""
        return self._outgoing.get(entity_id, [])

    def get_all_neighbors(self, entity_id: str) -> List[EdgeProtocol]:
        """Get all edges (incoming + outgoing) for entity."""
        outgoing = self._outgoing.get(entity_id, [])
        incoming = self._incoming.get(entity_id, [])
        return outgoing + incoming

    def get_observation_count(self, entity_id: str) -> int:
        """Get observation count for entity."""
        entity = self._entities.get(entity_id)
        return entity.observation_count if entity else 0

    def get_cooccurrence_count(self, entity_a: str, entity_b: str) -> int:
        """Get co-occurrence count between two entities."""
        key = frozenset([entity_a, entity_b])
        return self._cooccurrence.get(key, 0)

    def has_entity(self, entity_id: str) -> bool:
        """Check if entity exists in graph."""
        return entity_id in self._entities


# =============================================================================
# EMBEDDING CACHE
# =============================================================================


class EmbeddingCache:
    """
    Cache for entity embeddings with similarity computation.

    Provides efficient semantic distance calculations.
    """

    def __init__(
        self,
        embeddings: Optional[Dict[str, List[float]]] = None,
    ) -> None:
        """
        Initialize embedding cache.

        Args:
            embeddings: Pre-loaded embeddings {entity_id: vector}
        """
        self._embeddings = embeddings or {}
        self._similarity_cache: Dict[FrozenSet[str], float] = {}

    def add_embedding(self, entity_id: str, embedding: List[float]) -> None:
        """Add or update embedding for entity."""
        self._embeddings[entity_id] = embedding
        # Invalidate similarity cache for this entity
        keys_to_remove = [k for k in self._similarity_cache if entity_id in k]
        for key in keys_to_remove:
            del self._similarity_cache[key]

    def get_embedding(self, entity_id: str) -> Optional[List[float]]:
        """Get embedding for entity."""
        return self._embeddings.get(entity_id)

    def has_embedding(self, entity_id: str) -> bool:
        """Check if embedding exists for entity."""
        return entity_id in self._embeddings

    def compute_cosine_similarity(
        self,
        entity_a: str,
        entity_b: str,
    ) -> Optional[float]:
        """
        Compute cosine similarity between two entities.

        Returns:
            Similarity score [0, 1] or None if embeddings missing
        """
        # Check cache
        cache_key = frozenset([entity_a, entity_b])
        if cache_key in self._similarity_cache:
            return self._similarity_cache[cache_key]

        # Get embeddings
        emb_a = self._embeddings.get(entity_a)
        emb_b = self._embeddings.get(entity_b)

        if emb_a is None or emb_b is None:
            return None

        # Compute cosine similarity
        similarity = self._cosine_similarity(emb_a, emb_b)
        self._similarity_cache[cache_key] = similarity
        return similarity

    def compute_semantic_distance(
        self,
        entity_a: str,
        entity_b: str,
    ) -> Optional[float]:
        """
        Compute semantic distance (1 - similarity) between entities.

        Returns:
            Distance score [0, 1] or None if embeddings missing
        """
        similarity = self.compute_cosine_similarity(entity_a, entity_b)
        if similarity is None:
            return None
        return 1.0 - similarity

    @staticmethod
    def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if len(vec_a) != len(vec_b):
            return 0.0

        dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        # Clamp to [0, 1] for normalized embeddings
        return max(0.0, min(1.0, dot_product / (norm_a * norm_b)))


# =============================================================================
# RANDOM WALK ENGINE
# =============================================================================


class RandomWalkEngine:
    """
    Random Walk with Restart (RWR) engine for graph exploration.

    Implements personalized PageRank-style traversal with restart
    probability to maintain seed entity influence.
    """

    def __init__(
        self,
        graph: KnowledgeGraphView,
        config: BGTConfig,
        rng: random.Random,
    ) -> None:
        """
        Initialize random walk engine.

        Args:
            graph: Knowledge graph view
            config: BGT configuration
            rng: Seeded random number generator
        """
        self._graph = graph
        self._config = config
        self._rng = rng

    def random_walk_with_restart(
        self,
        seed_entity_id: str,
    ) -> Dict[str, VisitRecord]:
        """
        Execute random walk with restart from seed entity.

        With probability `restart_probability`, restart at seed.
        Otherwise, follow random edge weighted by inverse observation count
        (favoring unexplored paths).

        Args:
            seed_entity_id: Entity to start walk from

        Returns:
            Dictionary of visit records {entity_id: VisitRecord}
        """
        visits: Dict[str, VisitRecord] = {}
        current = seed_entity_id
        path: List[str] = [seed_entity_id]

        for step in range(self._config.walk_steps):
            # Record visit
            if current not in visits:
                visits[current] = VisitRecord(
                    entity_id=current,
                    visit_count=0,
                    first_visit_step=step,
                    path_from_seed=tuple(path),
                )
            visits[current].visit_count += 1

            # Restart with probability
            if self._rng.random() < self._config.restart_probability:
                current = seed_entity_id
                path = [seed_entity_id]
                continue

            # Get neighbors (all directions for undirected exploration)
            neighbors = self._graph.get_all_neighbors(current)
            if not neighbors:
                # Dead end, restart at seed
                current = seed_entity_id
                path = [seed_entity_id]
                continue

            # Weight by inverse observation count (explore unexplored)
            weights = [1.0 / (edge.observation_count + 1) for edge in neighbors]

            # Select next node
            selected_edge = self._rng.choices(neighbors, weights=weights, k=1)[0]

            # Determine next node (could be source or target depending on direction)
            if selected_edge.source_id == current:
                next_node = selected_edge.target_id
            else:
                next_node = selected_edge.source_id

            current = next_node
            path.append(current)

            # Limit path length to prevent memory issues
            if len(path) > 100:
                path = path[-50:]  # Keep recent history

        return visits

    def aggregate_walks(
        self,
        seed_entity_id: str,
        num_walks: int,
    ) -> Dict[str, VisitRecord]:
        """
        Execute multiple walks and aggregate visit counts.

        Args:
            seed_entity_id: Entity to start walks from
            num_walks: Number of walks to execute

        Returns:
            Aggregated visit records
        """
        aggregated: Dict[str, VisitRecord] = {}

        for _ in range(num_walks):
            walk_visits = self.random_walk_with_restart(seed_entity_id)

            for entity_id, record in walk_visits.items():
                if entity_id not in aggregated:
                    aggregated[entity_id] = VisitRecord(
                        entity_id=entity_id,
                        visit_count=0,
                        first_visit_step=record.first_visit_step,
                        path_from_seed=record.path_from_seed,
                    )
                aggregated[entity_id].visit_count += record.visit_count

        return aggregated


# =============================================================================
# PMI CALCULATOR
# =============================================================================


class PMICalculator:
    """
    Pointwise Mutual Information calculator for surprise quantification.

    PMI = log2((c_ab × N) / (c_a × c_b))

    where:
    - c_ab = co-occurrence count
    - c_a, c_b = individual occurrence counts
    - N = corpus size (total entity mentions)

    PMI > 3.0 means entities co-occur 8× more than random chance.
    """

    def __init__(
        self,
        graph: KnowledgeGraphView,
        corpus_size_override: Optional[int] = None,
    ) -> None:
        """
        Initialize PMI calculator.

        Args:
            graph: Knowledge graph view
            corpus_size_override: Override corpus size N (default: from graph)
        """
        self._graph = graph
        self._corpus_size = corpus_size_override or graph.corpus_size or P03_BGT_DEFAULT_CORPUS_SIZE

    def compute_pmi(self, entity_a: str, entity_b: str) -> float:
        """
        Compute PMI between two entities.

        Per A.0.7 invariant — uses counts with corpus size N.

        Args:
            entity_a: First entity ID
            entity_b: Second entity ID

        Returns:
            PMI score (0.0 if insufficient data)
        """
        c_a = self._graph.get_observation_count(entity_a)
        c_b = self._graph.get_observation_count(entity_b)
        c_ab = self._graph.get_cooccurrence_count(entity_a, entity_b)

        if c_ab == 0 or c_a == 0 or c_b == 0:
            return 0.0

        # PMI with corpus normalization
        # PMI = log2((c_ab * N) / (c_a * c_b))
        numerator = c_ab * self._corpus_size
        denominator = c_a * c_b

        if denominator == 0:
            return 0.0

        return math.log2(numerator / denominator)


# =============================================================================
# INSIGHT GENERATOR
# =============================================================================


class InsightTextGenerator:
    """
    Generate human-readable insight text from remote associations.

    Templates are categorized by insight category and connection type.
    """

    # Templates indexed by (category, connection_type)
    _TEMPLATES: Dict[Tuple[InsightCategory, ConnectionType], List[str]] = {
        (InsightCategory.OPPORTUNITY, ConnectionType.SEMANTIC): [
            "Interesting connection between '{source}' and '{target}' — "
            "they share unexpected semantic relationships that could reveal new perspectives.",
            "'{source}' and '{target}' appear unrelated but may offer complementary insights.",
        ],
        (InsightCategory.OPPORTUNITY, ConnectionType.TEMPORAL): [
            "'{source}' and '{target}' tend to occur together in time — "
            "consider exploring this temporal pattern.",
            "There's a recurring timing relationship between '{source}' and '{target}'.",
        ],
        (InsightCategory.PATTERN, ConnectionType.BEHAVIORAL): [
            "A behavioral pattern connects '{source}' and '{target}' — "
            "they may influence each other's outcomes.",
            "Actions involving '{source}' appear related to '{target}' behaviors.",
        ],
        (InsightCategory.WARNING, ConnectionType.CAUSAL): [
            "Potential causal link between '{source}' and '{target}' — "
            "changes to one may affect the other.",
            "'{source}' may have downstream effects on '{target}'.",
        ],
        (InsightCategory.ANOMALY, ConnectionType.STRUCTURAL): [
            "Unusual structural connection between '{source}' and '{target}' — "
            "this relationship appears stronger than expected.",
            "'{source}' and '{target}' share an unexpectedly strong network position.",
        ],
    }

    # Default template for uncategorized combinations
    _DEFAULT_TEMPLATE = (
        "Discovered surprising connection between '{source}' and '{target}' "
        "(PMI: {pmi:.2f}, distance: {distance:.2f})."
    )

    def __init__(self, rng: random.Random) -> None:
        """Initialize with seeded RNG for deterministic template selection."""
        self._rng = rng

    def generate(
        self,
        associate: RemoteAssociate,
        source_name: str,
        target_name: str,
    ) -> Tuple[str, InsightCategory]:
        """
        Generate insight text and determine category.

        Args:
            associate: Remote associate data
            source_name: Human-readable source entity name
            target_name: Human-readable target entity name

        Returns:
            Tuple of (insight_text, category)
        """
        # Determine category based on PMI and distance
        category = self._determine_category(associate)

        # Get templates for this combination
        key = (category, associate.connection_type)
        templates = self._TEMPLATES.get(key, [self._DEFAULT_TEMPLATE])

        # Select template deterministically based on entity IDs
        template_idx = hash(associate.seed_entity_id + associate.target_entity_id) % len(templates)
        template = templates[template_idx]

        # Format template
        text = template.format(
            source=source_name,
            target=target_name,
            pmi=associate.pmi_score,
            distance=associate.semantic_distance,
        )

        return text, category

    def _determine_category(self, associate: RemoteAssociate) -> InsightCategory:
        """Determine insight category based on association characteristics."""
        if associate.pmi_score > 5.0:
            # Very high PMI suggests anomaly
            return InsightCategory.ANOMALY
        if associate.semantic_distance > 0.85:
            # Very remote suggests opportunity
            return InsightCategory.OPPORTUNITY
        if associate.connection_type == ConnectionType.BEHAVIORAL:
            return InsightCategory.PATTERN
        if associate.connection_type == ConnectionType.CAUSAL:
            return InsightCategory.WARNING
        return InsightCategory.PATTERN


# =============================================================================
# BISOCIATIVE GRAPH TRAVERSAL
# =============================================================================


class BisociativeGraphTraversal:
    """
    BGT-SM: Bisociative Graph Traversal for Semantic Memory.

    Main class for discovering surprising connections through:
    1. Random walks to discover remote associates
    2. PMI scoring to quantify surprise
    3. Novelty scoring for insight ranking
    4. Human-readable insight generation

    Thread Safety:
    - Thread-safe for concurrent reads
    - Not safe for concurrent configuration changes

    Usage:
        config = BGTConfig(seed=12345)
        bgt = BisociativeGraphTraversal(config)

        insights = bgt.discover(
            entities=kg_entities,
            edges=kg_edges,
            seed_entity_ids=["entity_001", "entity_002"],
            embeddings={"entity_001": [0.1, 0.2, ...], ...},
        )

        for insight in insights:
            print(f"{insight.insight_text} (novelty: {insight.novelty_score:.2f})")
    """

    def __init__(self, config: Optional[BGTConfig] = None) -> None:
        """
        Initialize BGT-SM with configuration.

        Args:
            config: BGT configuration (uses defaults if None)
        """
        self.config = config or BGTConfig()
        self._logger = logger

    def is_cold_start(self) -> bool:
        """
        Check if BGT-SM is in cold start state.

        Issue 8.1.20: Cold start occurs when corpus_size < threshold.
        In this state, PMI calculations are unreliable and discovery is skipped.

        Returns:
            True if corpus is too small for meaningful insights
        """
        return self.config.corpus_size_n < self.config.cold_start_threshold

    def get_cold_start_info(self) -> dict:
        """
        Get cold start diagnostic information.

        Returns:
            Dict with corpus_size, threshold, and is_cold_start flag
        """
        return {
            "corpus_size": self.config.corpus_size_n,
            "cold_start_threshold": self.config.cold_start_threshold,
            "is_cold_start": self.is_cold_start(),
        }

    def discover(
        self,
        entities: List[EntityProtocol],
        edges: List[EdgeProtocol],
        seed_entity_ids: List[str],
        embeddings: Optional[Dict[str, List[float]]] = None,
        rng_seed: Optional[int] = None,
    ) -> List[BGTInsight]:
        """
        Discover bisociative insights from knowledge graph.

        Args:
            entities: Knowledge graph entities
            edges: Knowledge graph edges
            seed_entity_ids: Entity IDs to start exploration from
            embeddings: Entity embeddings for semantic distance
            rng_seed: Override RNG seed for determinism

        Returns:
            List of insights sorted by novelty score (descending)
        """
        start_ms = int(time.time() * 1000)

        # =====================================================================
        # COLD START CHECK (Issue 8.1.20)
        # PMI requires sufficient corpus for meaningful probability estimates.
        # Skip discovery if corpus too small to avoid spurious insights.
        # =====================================================================
        if self.config.corpus_size_n < self.config.cold_start_threshold:
            self._logger.info(
                "BGT-SM cold start: corpus_size=%d < threshold=%d, skipping",
                self.config.corpus_size_n,
                self.config.cold_start_threshold,
            )
            # Return empty list - no error, just insufficient data
            return []

        # Initialize RNG
        seed = rng_seed if rng_seed is not None else self.config.seed
        rng = random.Random(seed)

        # Build graph view
        graph = KnowledgeGraphView(entities, edges)

        # Build embedding cache
        embedding_cache = EmbeddingCache(embeddings)

        # Initialize components
        walk_engine = RandomWalkEngine(graph, self.config, rng)
        pmi_calculator = PMICalculator(graph, self.config.corpus_size_n)
        text_generator = InsightTextGenerator(rng)

        self._logger.debug(
            "BGT-SM starting discovery",
            extra={
                "seed_count": len(seed_entity_ids),
                "entity_count": len(entities),
                "edge_count": len(edges),
                "embedding_count": len(embeddings) if embeddings else 0,
                "rng_seed": seed,
            },
        )

        # Collect insights from all seeds
        all_insights: List[BGTInsight] = []
        seen_pairs: Set[FrozenSet[str]] = set()

        for seed_entity_id in seed_entity_ids:
            if not graph.has_entity(seed_entity_id):
                self._logger.warning(f"Seed entity not found in graph: {seed_entity_id}")
                continue

            # Execute random walks
            visits = walk_engine.aggregate_walks(
                seed_entity_id,
                self.config.max_walks_per_seed,
            )

            # Find remote associates
            associates = self._find_remote_associates(
                seed_entity_id=seed_entity_id,
                visits=visits,
                graph=graph,
                embedding_cache=embedding_cache,
                pmi_calculator=pmi_calculator,
            )

            # Generate insights from associates
            seed_insights = 0
            for associate in associates:
                if seed_insights >= self.config.max_insights_per_seed:
                    break

                # Skip duplicate pairs
                pair_key = frozenset([associate.seed_entity_id, associate.target_entity_id])
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                # Generate insight
                insight = self._create_insight(
                    associate=associate,
                    graph=graph,
                    text_generator=text_generator,
                )
                all_insights.append(insight)
                seed_insights += 1

            if len(all_insights) >= self.config.max_total_insights:
                break

        # Sort by novelty and limit
        all_insights.sort(key=lambda i: i.novelty_score, reverse=True)
        all_insights = all_insights[: self.config.max_total_insights]

        compute_ms = int(time.time() * 1000) - start_ms

        self._logger.info(
            "BGT-SM discovery complete",
            extra={
                "insights_generated": len(all_insights),
                "seeds_explored": len(seed_entity_ids),
                "compute_ms": compute_ms,
            },
        )

        return all_insights

    def _find_remote_associates(
        self,
        seed_entity_id: str,
        visits: Dict[str, VisitRecord],
        graph: KnowledgeGraphView,
        embedding_cache: EmbeddingCache,
        pmi_calculator: PMICalculator,
    ) -> List[RemoteAssociate]:
        """
        Find remote associates from visit records.

        Filters by:
        1. Semantic distance > threshold
        2. PMI > threshold
        3. Sorts by novelty score

        Args:
            seed_entity_id: Seed entity for this walk
            visits: Visit records from random walk
            graph: Knowledge graph view
            embedding_cache: Embedding cache for distance
            pmi_calculator: PMI calculator

        Returns:
            List of remote associates sorted by novelty (descending)
        """
        associates: List[RemoteAssociate] = []

        for entity_id, record in visits.items():
            if entity_id == seed_entity_id:
                continue

            # Compute semantic distance
            distance = embedding_cache.compute_semantic_distance(
                seed_entity_id,
                entity_id,
            )

            # Skip if no embeddings or not remote
            if distance is None:
                # If no embeddings, use path length as proxy
                distance = min(1.0, len(record.path_from_seed) / 10.0)

            if distance < self.config.semantic_distance_threshold:
                continue

            # Compute PMI
            pmi = pmi_calculator.compute_pmi(seed_entity_id, entity_id)

            if pmi < self.config.pmi_threshold:
                continue

            # Compute novelty score: distance × pmi / (visit_count + 1)
            novelty = distance * pmi / (record.visit_count + 1)

            if novelty < self.config.novelty_threshold:
                continue

            # Determine connection type from path
            connection_type = self._infer_connection_type(
                record.path_from_seed,
                graph,
            )

            associates.append(
                RemoteAssociate(
                    seed_entity_id=seed_entity_id,
                    target_entity_id=entity_id,
                    visit_count=record.visit_count,
                    semantic_distance=distance,
                    pmi_score=pmi,
                    novelty_score=novelty,
                    connection_path=record.path_from_seed,
                    connection_type=connection_type,
                )
            )

        # Sort by novelty
        associates.sort(key=lambda a: a.novelty_score, reverse=True)
        return associates

    def _infer_connection_type(
        self,
        path: Tuple[str, ...],
        graph: KnowledgeGraphView,
    ) -> ConnectionType:
        """Infer connection type from path edges."""
        if len(path) < 2:
            return ConnectionType.SEMANTIC

        # Check first edge type
        first_edge = graph.get_neighbors(path[0])
        for edge in first_edge:
            if len(path) > 1 and edge.target_id == path[1]:
                relation = edge.relation_type.lower()
                if "cause" in relation or "lead" in relation:
                    return ConnectionType.CAUSAL
                if "time" in relation or "when" in relation or "during" in relation:
                    return ConnectionType.TEMPORAL
                if "do" in relation or "act" in relation or "perform" in relation:
                    return ConnectionType.BEHAVIORAL

        return ConnectionType.SEMANTIC

    def _create_insight(
        self,
        associate: RemoteAssociate,
        graph: KnowledgeGraphView,
        text_generator: InsightTextGenerator,
    ) -> BGTInsight:
        """Create BGTInsight from remote associate."""
        source_name = graph.get_entity_name(associate.seed_entity_id)
        target_name = graph.get_entity_name(associate.target_entity_id)

        text, category = text_generator.generate(
            associate,
            source_name,
            target_name,
        )

        # Confidence based on PMI and visit count
        # Higher PMI and more visits → higher confidence
        confidence = min(0.95, 0.3 + (associate.pmi_score / 10.0) + (associate.visit_count / 100.0))

        # Issue 8.1.10: Compute relevance based on connection type
        # Causal/temporal connections are more relevant than pure semantic
        relevance_map = {
            ConnectionType.CAUSAL: 0.9,
            ConnectionType.TEMPORAL: 0.8,
            ConnectionType.STRUCTURAL: 0.7,
            ConnectionType.SEMANTIC: 0.6,
            ConnectionType.BEHAVIORAL: 0.75,
        }
        relevance_score = relevance_map.get(associate.connection_type, 0.5)

        # Issue 8.1.10: Compute actionability based on category
        # Opportunity and warning insights are more actionable than patterns
        actionability_map = {
            InsightCategory.OPPORTUNITY: 0.9,
            InsightCategory.WARNING: 0.85,
            InsightCategory.OPTIMIZATION: 0.8,
            InsightCategory.PATTERN: 0.7,
            InsightCategory.ANOMALY: 0.6,
        }
        actionability_score = actionability_map.get(category, 0.5)

        return BGTInsight(
            insight_id=generate_ulid(),
            source_entity_id=associate.seed_entity_id,
            target_entity_id=associate.target_entity_id,
            source_entity_name=source_name,
            target_entity_name=target_name,
            semantic_distance=associate.semantic_distance,
            pmi_score=associate.pmi_score,
            novelty_score=associate.novelty_score,
            insight_text=text,
            category=category,
            connection_type=associate.connection_type,
            connection_path=associate.connection_path,
            supporting_evidence=(associate.seed_entity_id, associate.target_entity_id),
            confidence=confidence,
            relevance_score=relevance_score,
            actionability_score=actionability_score,
        )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def create_bgt_from_config(
    config: Optional["DreamConfig"] = None,
) -> BisociativeGraphTraversal:
    """
    Create BGT-SM instance from DreamConfig.

    Args:
        config: DreamConfig with BGT parameters

    Returns:
        Configured BisociativeGraphTraversal instance
    """
    if config is None:
        return BisociativeGraphTraversal()

    bgt_config = BGTConfig(
        semantic_distance_threshold=config.semantic_distance_threshold,
        pmi_threshold=config.pmi_threshold,
        corpus_size_n=config.corpus_size_n,
        max_total_insights=config.max_insights,
    )
    return BisociativeGraphTraversal(bgt_config)
