"""
Realistic Data Generators for R5 Benchmarking.

This module provides production-like test data generators for benchmarking
the R5 Dream Phase algorithms. Data is generated with realistic patterns
that simulate actual user memory data.

Key Generators:
- RealisticEpisodeGenerator: Generates episodes with realistic temporal patterns
- RealisticKnowledgeGraphGenerator: Generates KG entities and edges
- RealisticGoalGenerator: Generates user goals for MCTS
- RealisticRoutineGenerator: Generates habit/routine data for TDL-HCO

Design Principles:
1. Deterministic with seed control for reproducibility
2. Configurable complexity levels (small, medium, large, production)
3. Realistic temporal distributions (weekday/weekend patterns)
4. Realistic entity co-occurrence patterns (power-law distribution)
5. Realistic sentiment distributions (slightly positive bias)

References:
- M8_EXECUTION.md: Issue 8.1.* for algorithm specifications
- Dossier Section 4.6: R5 Dream-Like Exploration
"""

from __future__ import annotations

import hashlib
import math
import random
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

# =============================================================================
# CONSTANTS
# =============================================================================

# Time constants
MS_PER_SECOND = 1000
MS_PER_MINUTE = MS_PER_SECOND * 60
MS_PER_HOUR = MS_PER_MINUTE * 60
MS_PER_DAY = MS_PER_HOUR * 24
MS_PER_WEEK = MS_PER_DAY * 7

# Realistic patterns
WEEKDAY_ACTIVITY_PEAKS = [8, 12, 18]  # Morning, lunch, evening
WEEKEND_ACTIVITY_PEAKS = [10, 14, 20]  # Late morning, afternoon, evening

# Entity type distributions (based on typical personal memory)
ENTITY_TYPE_WEIGHTS = {
    "person": 0.25,
    "location": 0.20,
    "event": 0.15,
    "organization": 0.10,
    "concept": 0.10,
    "activity": 0.08,
    "object": 0.07,
    "time_period": 0.05,
}

# Sentiment distribution parameters (slightly positive bias)
SENTIMENT_MEAN = 0.1
SENTIMENT_STD = 0.4

# Salience distribution parameters
SALIENCE_ALPHA = 2.0  # Beta distribution shape (right-skewed)
SALIENCE_BETA = 5.0


# =============================================================================
# ENUMS
# =============================================================================


class BenchmarkScale(str, Enum):
    """Scale of benchmark data generation."""

    SMALL = "small"  # Quick tests: ~10 episodes, ~50 entities
    MEDIUM = "medium"  # Normal tests: ~100 episodes, ~500 entities
    LARGE = "large"  # Stress tests: ~1000 episodes, ~5000 entities
    PRODUCTION = "production"  # Production-like: ~10000 episodes, ~50000 entities


@dataclass(frozen=True)
class ScaleConfig:
    """Configuration for each benchmark scale."""

    episode_count: int
    entity_count: int
    edge_count: int
    goal_count: int
    routine_count: int
    time_span_days: int


SCALE_CONFIGS = {
    BenchmarkScale.SMALL: ScaleConfig(
        episode_count=10,
        entity_count=50,
        edge_count=100,
        goal_count=3,
        routine_count=5,
        time_span_days=7,
    ),
    BenchmarkScale.MEDIUM: ScaleConfig(
        episode_count=100,
        entity_count=500,
        edge_count=1500,
        goal_count=10,
        routine_count=20,
        time_span_days=30,
    ),
    BenchmarkScale.LARGE: ScaleConfig(
        episode_count=1000,
        entity_count=5000,
        edge_count=20000,
        goal_count=50,
        routine_count=100,
        time_span_days=90,
    ),
    BenchmarkScale.PRODUCTION: ScaleConfig(
        episode_count=10000,
        entity_count=50000,
        edge_count=200000,
        goal_count=200,
        routine_count=500,
        time_span_days=365,
    ),
}


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class RealisticEpisode:
    """
    Realistic episode for testing.

    Matches EpisodeProtocol from CPN algorithm.
    """

    episode_id: str
    sentiment_score: float
    salience_score: float
    start_time_ms: int
    end_time_ms: int
    entity_ids: List[str]
    location_name: Optional[str] = None
    activity_type: Optional[str] = None
    participants: Optional[List[str]] = None
    ambiguity_score: float = 0.0
    summary: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate values."""
        if not -1.0 <= self.sentiment_score <= 1.0:
            raise ValueError(f"sentiment_score must be in [-1, 1]: {self.sentiment_score}")
        if not 0.0 <= self.salience_score <= 1.0:
            raise ValueError(f"salience_score must be in [0, 1]: {self.salience_score}")


@dataclass
class RealisticEntity:
    """
    Realistic knowledge graph entity.

    Matches EntityProtocol from BGT-SM algorithm.
    """

    entity_id: str
    entity_type: str
    name: str
    observation_count: int
    embedding: Optional[List[float]] = None

    def __post_init__(self) -> None:
        """Validate observation count."""
        if self.observation_count < 0:
            raise ValueError("observation_count must be non-negative")


@dataclass
class RealisticEdge:
    """
    Realistic knowledge graph edge.

    Matches EdgeProtocol and KGEdgeProtocol from algorithms.
    """

    edge_id: str
    source_id: str
    target_id: str
    relation_type: str
    observation_count: int
    confidence: float

    def __post_init__(self) -> None:
        """Validate values."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0, 1]: {self.confidence}")


@dataclass
class RealisticGoal:
    """Realistic user goal for MCTS testing."""

    goal_id: str
    goal_type: str
    description: str
    priority: float
    deadline_ms: Optional[int] = None
    progress: float = 0.0

    def __post_init__(self) -> None:
        """Validate values."""
        if not 0.0 <= self.priority <= 1.0:
            raise ValueError(f"priority must be in [0, 1]: {self.priority}")
        if not 0.0 <= self.progress <= 1.0:
            raise ValueError(f"progress must be in [0, 1]: {self.progress}")


@dataclass
class RealisticRoutine:
    """Realistic habit/routine for TDL-HCO testing."""

    routine_id: str
    name: str
    frequency: str  # daily, weekly, etc.
    typical_time_hour: int
    success_rate: float
    streak_days: int
    value_score: float

    def __post_init__(self) -> None:
        """Validate values."""
        if not 0 <= self.typical_time_hour <= 23:
            raise ValueError("typical_time_hour must be in [0, 23]")
        if not 0.0 <= self.success_rate <= 1.0:
            raise ValueError("success_rate must be in [0, 1]")


@dataclass
class BenchmarkDataset:
    """Complete dataset for benchmarking."""

    episodes: List[RealisticEpisode]
    entities: List[RealisticEntity]
    edges: List[RealisticEdge]
    goals: List[RealisticGoal]
    routines: List[RealisticRoutine]
    scale: BenchmarkScale
    seed: int
    generated_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    @property
    def entity_lookup(self) -> Dict[str, RealisticEntity]:
        """Get entity lookup by ID."""
        return {e.entity_id: e for e in self.entities}

    @property
    def edge_by_source(self) -> Dict[str, List[RealisticEdge]]:
        """Get edges grouped by source."""
        result: Dict[str, List[RealisticEdge]] = defaultdict(list)
        for edge in self.edges:
            result[edge.source_id].append(edge)
        return dict(result)


# =============================================================================
# ULID GENERATOR (compatible with project standard)
# =============================================================================


def generate_benchmark_ulid(seed: int, counter: int) -> str:
    """
    Generate deterministic ULID-like identifier for benchmarks.

    Args:
        seed: Base seed for determinism
        counter: Incrementing counter for uniqueness

    Returns:
        26-character ULID-like string
    """
    # Create a deterministic hash
    data = f"{seed}:{counter}".encode()
    hash_bytes = hashlib.sha256(data).digest()[:16]

    # Encode to base32-like characters (ULID alphabet)
    alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    result = []

    # Use bits from hash
    value = int.from_bytes(hash_bytes, "big")
    for _ in range(26):
        result.append(alphabet[value % 32])
        value //= 32

    return "".join(reversed(result))


# =============================================================================
# EPISODE GENERATOR
# =============================================================================


class RealisticEpisodeGenerator:
    """
    Generates realistic episodic memory data.

    Simulates typical patterns:
    - Higher activity during daytime
    - Weekend vs weekday patterns
    - Realistic sentiment distributions
    - Entity co-occurrence patterns
    """

    def __init__(self, seed: int = 42):
        """Initialize generator with seed."""
        self.seed = seed
        self.rng = random.Random(seed)
        self._counter = 0

        # Location pools
        self._locations = [
            "Home",
            "Office",
            "Coffee Shop",
            "Gym",
            "Restaurant",
            "Park",
            "Library",
            "Grocery Store",
            "Friend's House",
            "Downtown",
            "Beach",
            "Mall",
            "Cinema",
            "Hospital",
        ]

        # Activity types
        self._activities = [
            "working",
            "meeting",
            "eating",
            "exercising",
            "commuting",
            "shopping",
            "socializing",
            "relaxing",
            "studying",
            "cooking",
            "sleeping",
            "entertainment",
            "healthcare",
            "errands",
        ]

    def generate(
        self,
        count: int,
        entity_ids: List[str],
        time_span_days: int = 30,
        end_time_ms: Optional[int] = None,
    ) -> List[RealisticEpisode]:
        """
        Generate realistic episodes.

        Args:
            count: Number of episodes to generate
            entity_ids: Pool of entity IDs to associate with episodes
            time_span_days: Time span to distribute episodes over
            end_time_ms: End timestamp (default: now)

        Returns:
            List of RealisticEpisode objects
        """
        if end_time_ms is None:
            end_time_ms = int(time.time() * 1000)

        start_time_ms = end_time_ms - (time_span_days * MS_PER_DAY)

        episodes = []
        for _ in range(count):
            episode = self._generate_single_episode(
                entity_ids=entity_ids,
                start_time_ms=start_time_ms,
                end_time_ms=end_time_ms,
            )
            episodes.append(episode)

        # Sort by time
        episodes.sort(key=lambda e: e.start_time_ms)
        return episodes

    def _generate_single_episode(
        self,
        entity_ids: List[str],
        start_time_ms: int,
        end_time_ms: int,
    ) -> RealisticEpisode:
        """Generate a single realistic episode."""
        self._counter += 1
        episode_id = generate_benchmark_ulid(self.seed, self._counter)

        # Generate timestamp with realistic distribution
        episode_start_ms = self._generate_realistic_timestamp(start_time_ms, end_time_ms)

        # Episode duration: 5 min to 4 hours
        duration_ms = self.rng.randint(5 * MS_PER_MINUTE, 4 * MS_PER_HOUR)
        episode_end_ms = episode_start_ms + duration_ms

        # Generate sentiment (slightly positive bias)
        sentiment = self._generate_sentiment()

        # Generate salience (right-skewed, most events are low salience)
        salience = self._generate_salience()

        # Select entities (1-5 entities per episode, power-law selection)
        num_entities = min(len(entity_ids), self.rng.randint(1, 5))
        selected_entities = self._select_entities_power_law(entity_ids, num_entities)

        # Generate location and activity
        location = self.rng.choice(self._locations)
        activity = self.rng.choice(self._activities)

        # Generate ambiguity (most episodes are clear)
        ambiguity = self.rng.betavariate(1, 5)  # Skewed toward 0

        # Generate participants (subset of person entities)
        person_entities = [e for e in selected_entities if "person" in e.lower()]
        participants = person_entities[:3] if person_entities else None

        return RealisticEpisode(
            episode_id=episode_id,
            sentiment_score=sentiment,
            salience_score=salience,
            start_time_ms=episode_start_ms,
            end_time_ms=episode_end_ms,
            entity_ids=selected_entities,
            location_name=location,
            activity_type=activity,
            participants=participants,
            ambiguity_score=ambiguity,
            summary=f"{activity.capitalize()} at {location}",
        )

    def _generate_realistic_timestamp(
        self,
        start_ms: int,
        end_ms: int,
    ) -> int:
        """Generate timestamp with realistic daily/weekly patterns."""
        # Pick a random day
        day_offset = self.rng.randint(0, (end_ms - start_ms) // MS_PER_DAY)
        day_start_ms = start_ms + (day_offset * MS_PER_DAY)

        # Determine if weekend (simplified: based on hash of day)
        is_weekend = (day_offset % 7) >= 5

        # Generate hour with activity peak bias
        peaks = WEEKEND_ACTIVITY_PEAKS if is_weekend else WEEKDAY_ACTIVITY_PEAKS
        peak = self.rng.choice(peaks)
        hour = int(self.rng.gauss(peak, 3)) % 24

        # Generate minute
        minute = self.rng.randint(0, 59)

        return day_start_ms + (hour * MS_PER_HOUR) + (minute * MS_PER_MINUTE)

    def _generate_sentiment(self) -> float:
        """Generate realistic sentiment score."""
        # Gaussian with slight positive bias, clamped to [-1, 1]
        sentiment = self.rng.gauss(SENTIMENT_MEAN, SENTIMENT_STD)
        return max(-1.0, min(1.0, sentiment))

    def _generate_salience(self) -> float:
        """Generate realistic salience score (right-skewed)."""
        # Beta distribution: most events have low salience
        return self.rng.betavariate(SALIENCE_ALPHA, SALIENCE_BETA)

    def _select_entities_power_law(
        self,
        entity_ids: List[str],
        count: int,
    ) -> List[str]:
        """
        Select entities with power-law distribution.

        Some entities appear frequently, most appear rarely.
        """
        if not entity_ids:
            return []

        # Weight by position (first entities are "popular")
        weights = [1.0 / (i + 1) ** 0.5 for i in range(len(entity_ids))]
        total = sum(weights)
        weights = [w / total for w in weights]

        selected: Set[str] = set()
        attempts = 0
        max_attempts = count * 10

        while len(selected) < count and attempts < max_attempts:
            idx = self._weighted_choice(weights)
            selected.add(entity_ids[idx])
            attempts += 1

        return list(selected)

    def _weighted_choice(self, weights: List[float]) -> int:
        """Choose index based on weights."""
        r = self.rng.random()
        cumulative = 0.0
        for i, w in enumerate(weights):
            cumulative += w
            if r <= cumulative:
                return i
        return len(weights) - 1


# =============================================================================
# KNOWLEDGE GRAPH GENERATOR
# =============================================================================


class RealisticKnowledgeGraphGenerator:
    """
    Generates realistic knowledge graph data.

    Simulates:
    - Power-law entity observation counts
    - Realistic relation type distributions
    - Entity type clustering
    - Embedding vectors with semantic similarity
    """

    RELATION_TYPES = [
        "CAUSES",
        "RELATED_TO",
        "LOCATED_AT",
        "PARTICIPATES_IN",
        "BELONGS_TO",
        "KNOWS",
        "WORKS_AT",
        "OCCURS_BEFORE",
        "OCCURS_AFTER",
        "SIMILAR_TO",
    ]

    PERSON_NAMES = [
        "Alice",
        "Bob",
        "Charlie",
        "Diana",
        "Eve",
        "Frank",
        "Grace",
        "Henry",
        "Ivy",
        "Jack",
        "Kate",
        "Leo",
        "Maya",
        "Noah",
        "Olivia",
    ]

    LOCATION_NAMES = [
        "Home",
        "Office",
        "Cafe Central",
        "City Park",
        "Main Library",
        "Downtown Plaza",
        "Harbor View",
        "University Campus",
    ]

    def __init__(self, seed: int = 42, embedding_dim: int = 128):
        """Initialize generator."""
        self.seed = seed
        self.rng = random.Random(seed)
        self.embedding_dim = embedding_dim
        self._entity_counter = 0
        self._edge_counter = 0

    def generate_entities(
        self,
        count: int,
    ) -> List[RealisticEntity]:
        """
        Generate realistic entities with power-law observation counts.

        Args:
            count: Number of entities to generate

        Returns:
            List of RealisticEntity objects
        """
        entities = []

        # Distribute entities by type
        type_counts = self._distribute_by_type(count)

        for entity_type, type_count in type_counts.items():
            for i in range(type_count):
                entity = self._generate_entity(entity_type, i)
                entities.append(entity)

        return entities

    def generate_edges(
        self,
        entities: List[RealisticEntity],
        edge_count: int,
    ) -> List[RealisticEdge]:
        """
        Generate realistic edges with preferential attachment.

        Args:
            entities: List of entities to connect
            edge_count: Number of edges to generate

        Returns:
            List of RealisticEdge objects
        """
        if len(entities) < 2:
            return []

        edges = []
        entity_ids = [e.entity_id for e in entities]
        entity_types = {e.entity_id: e.entity_type for e in entities}

        # Track edge counts for preferential attachment
        edge_counts: Dict[str, int] = defaultdict(int)
        existing_edges: Set[Tuple[str, str]] = set()

        attempts = 0
        max_attempts = edge_count * 10

        while len(edges) < edge_count and attempts < max_attempts:
            attempts += 1

            # Select source with preferential attachment
            source_id = self._preferential_select(entity_ids, edge_counts)

            # Select target (different from source)
            target_id = self._preferential_select(
                [e for e in entity_ids if e != source_id],
                edge_counts,
            )

            # Skip duplicate edges
            edge_key = (source_id, target_id)
            if edge_key in existing_edges:
                continue
            existing_edges.add(edge_key)

            # Generate edge
            edge = self._generate_edge(
                source_id=source_id,
                target_id=target_id,
                source_type=entity_types[source_id],
                target_type=entity_types[target_id],
            )
            edges.append(edge)

            # Update counts
            edge_counts[source_id] += 1
            edge_counts[target_id] += 1

        return edges

    def _distribute_by_type(self, count: int) -> Dict[str, int]:
        """Distribute count across entity types."""
        result = {}
        remaining = count

        types = list(ENTITY_TYPE_WEIGHTS.items())
        for i, (entity_type, weight) in enumerate(types):
            if i == len(types) - 1:
                # Last type gets remainder
                result[entity_type] = remaining
            else:
                type_count = int(count * weight)
                result[entity_type] = type_count
                remaining -= type_count

        return result

    def _generate_entity(
        self,
        entity_type: str,
        index: int,
    ) -> RealisticEntity:
        """Generate a single entity."""
        self._entity_counter += 1
        entity_id = generate_benchmark_ulid(self.seed, self._entity_counter)

        # Generate name based on type
        if entity_type == "person":
            name = self.rng.choice(self.PERSON_NAMES) + f" {index + 1}"
        elif entity_type == "location":
            name = self.rng.choice(self.LOCATION_NAMES) + f" {index + 1}"
        else:
            name = f"{entity_type.capitalize()} {index + 1}"

        # Power-law observation count
        observation_count = int(self.rng.paretovariate(1.5))
        observation_count = max(1, min(observation_count, 1000))

        # Generate embedding
        embedding = self._generate_embedding(entity_type)

        return RealisticEntity(
            entity_id=entity_id,
            entity_type=entity_type,
            name=name,
            observation_count=observation_count,
            embedding=embedding,
        )

    def _generate_embedding(self, entity_type: str) -> List[float]:
        """
        Generate embedding with type-based clustering.

        Entities of the same type will have similar embeddings.
        """
        # Type-based base vector
        type_seed = hash(entity_type) % 10000
        type_rng = random.Random(type_seed)
        base = [type_rng.gauss(0, 0.5) for _ in range(self.embedding_dim)]

        # Add random noise
        noise = [self.rng.gauss(0, 0.3) for _ in range(self.embedding_dim)]

        # Combine and normalize
        embedding = [b + n for b, n in zip(base, noise)]
        magnitude = math.sqrt(sum(x * x for x in embedding))
        if magnitude > 0:
            embedding = [x / magnitude for x in embedding]

        return embedding

    def _generate_edge(
        self,
        source_id: str,
        target_id: str,
        source_type: str,
        target_type: str,
    ) -> RealisticEdge:
        """Generate a single edge."""
        self._edge_counter += 1
        edge_id = generate_benchmark_ulid(self.seed + 1000, self._edge_counter)

        # Select relation type based on entity types
        relation_type = self._select_relation_type(source_type, target_type)

        # Power-law observation count
        observation_count = int(self.rng.paretovariate(1.2))
        observation_count = max(1, min(observation_count, 100))

        # Confidence based on observation count
        confidence = min(0.95, 0.5 + 0.1 * math.log1p(observation_count))

        return RealisticEdge(
            edge_id=edge_id,
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            observation_count=observation_count,
            confidence=confidence,
        )

    def _select_relation_type(
        self,
        source_type: str,
        target_type: str,
    ) -> str:
        """Select appropriate relation type for entity types."""
        # Type-specific relations
        if source_type == "person" and target_type == "person":
            return self.rng.choice(["KNOWS", "RELATED_TO", "SIMILAR_TO"])
        elif source_type == "person" and target_type == "location":
            return self.rng.choice(["LOCATED_AT", "WORKS_AT"])
        elif source_type == "person" and target_type == "event":
            return self.rng.choice(["PARTICIPATES_IN", "CAUSES"])
        elif source_type == "event":
            return self.rng.choice(["OCCURS_BEFORE", "OCCURS_AFTER", "CAUSES"])
        else:
            return self.rng.choice(self.RELATION_TYPES)

    def _preferential_select(
        self,
        entity_ids: List[str],
        edge_counts: Dict[str, int],
    ) -> str:
        """Select entity with preferential attachment (rich get richer)."""
        if not entity_ids:
            raise ValueError("entity_ids cannot be empty")

        # Calculate weights (existing edges + 1 for smoothing)
        weights = [edge_counts.get(eid, 0) + 1 for eid in entity_ids]
        total = sum(weights)
        weights = [w / total for w in weights]

        # Weighted random selection
        r = self.rng.random()
        cumulative = 0.0
        for i, w in enumerate(weights):
            cumulative += w
            if r <= cumulative:
                return entity_ids[i]

        return entity_ids[-1]


# =============================================================================
# GOAL GENERATOR
# =============================================================================


class RealisticGoalGenerator:
    """Generates realistic user goals for MCTS testing."""

    GOAL_TYPES = [
        ("health", ["Exercise more", "Eat healthier", "Sleep better", "Reduce stress"]),
        ("career", ["Get promotion", "Learn new skill", "Network more", "Complete project"]),
        ("personal", ["Read more books", "Travel", "Learn language", "Hobby time"]),
        ("social", ["Reconnect with friends", "Family time", "Community involvement"]),
        ("financial", ["Save money", "Pay off debt", "Invest", "Budget better"]),
    ]

    def __init__(self, seed: int = 42):
        """Initialize generator."""
        self.seed = seed
        self.rng = random.Random(seed)
        self._counter = 0

    def generate(
        self,
        count: int,
        time_horizon_days: int = 90,
    ) -> List[RealisticGoal]:
        """Generate realistic goals."""
        goals = []

        for _ in range(count):
            self._counter += 1
            goal = self._generate_single_goal(time_horizon_days)
            goals.append(goal)

        return goals

    def _generate_single_goal(self, time_horizon_days: int) -> RealisticGoal:
        """Generate a single realistic goal."""
        goal_id = generate_benchmark_ulid(self.seed, self._counter)

        # Select goal type and description
        goal_type, descriptions = self.rng.choice(self.GOAL_TYPES)
        description = self.rng.choice(descriptions)

        # Generate priority (biased toward high priority)
        priority = self.rng.betavariate(3, 2)  # Skewed toward high

        # Generate deadline (if applicable)
        if self.rng.random() < 0.7:  # 70% have deadlines
            days_until = self.rng.randint(7, time_horizon_days)
            deadline_ms = int(time.time() * 1000) + (days_until * MS_PER_DAY)
        else:
            deadline_ms = None

        # Generate progress (newer goals have less progress)
        progress = self.rng.betavariate(1, 3)  # Skewed toward low

        return RealisticGoal(
            goal_id=goal_id,
            goal_type=goal_type,
            description=description,
            priority=priority,
            deadline_ms=deadline_ms,
            progress=progress,
        )


# =============================================================================
# ROUTINE GENERATOR
# =============================================================================


class RealisticRoutineGenerator:
    """Generates realistic habit/routine data for TDL-HCO testing."""

    ROUTINE_TEMPLATES = [
        ("Morning Exercise", "daily", 6, 0.7),
        ("Meditation", "daily", 7, 0.6),
        ("Read 30 min", "daily", 21, 0.5),
        ("Weekly Review", "weekly", 10, 0.8),
        ("Meal Prep", "weekly", 11, 0.65),
        ("Call Family", "weekly", 18, 0.75),
        ("Gym Workout", "daily", 18, 0.55),
        ("Journal", "daily", 22, 0.45),
        ("Language Study", "daily", 20, 0.4),
        ("Check Finances", "weekly", 9, 0.85),
    ]

    def __init__(self, seed: int = 42):
        """Initialize generator."""
        self.seed = seed
        self.rng = random.Random(seed)
        self._counter = 0

    def generate(self, count: int) -> List[RealisticRoutine]:
        """Generate realistic routines."""
        routines = []
        templates = list(self.ROUTINE_TEMPLATES)

        for i in range(count):
            self._counter += 1

            # Use template if available, otherwise generate
            if i < len(templates):
                name, frequency, hour, base_rate = templates[i]
            else:
                name = f"Habit {i + 1}"
                frequency = self.rng.choice(["daily", "weekly"])
                hour = self.rng.randint(6, 22)
                base_rate = self.rng.uniform(0.3, 0.8)

            routine = self._generate_routine(name, frequency, hour, base_rate)
            routines.append(routine)

        return routines

    def _generate_routine(
        self,
        name: str,
        frequency: str,
        hour: int,
        base_success_rate: float,
    ) -> RealisticRoutine:
        """Generate a single routine."""
        routine_id = generate_benchmark_ulid(self.seed, self._counter)

        # Add variation to success rate
        success_rate = base_success_rate + self.rng.gauss(0, 0.1)
        success_rate = max(0.1, min(0.95, success_rate))

        # Generate streak (based on success rate)
        max_streak = int(100 * success_rate)
        streak_days = self.rng.randint(0, max(1, max_streak))

        # Generate value score
        value_score = self.rng.betavariate(2, 2)  # Centered distribution

        return RealisticRoutine(
            routine_id=routine_id,
            name=name,
            frequency=frequency,
            typical_time_hour=hour,
            success_rate=success_rate,
            streak_days=streak_days,
            value_score=value_score,
        )


# =============================================================================
# MAIN DATASET GENERATOR
# =============================================================================


class BenchmarkDatasetGenerator:
    """
    Main generator that creates complete benchmark datasets.

    Usage:
        generator = BenchmarkDatasetGenerator(seed=42)
        dataset = generator.generate(BenchmarkScale.MEDIUM)
    """

    def __init__(self, seed: int = 42):
        """Initialize all sub-generators."""
        self.seed = seed
        self.kg_generator = RealisticKnowledgeGraphGenerator(seed)
        self.episode_generator = RealisticEpisodeGenerator(seed)
        self.goal_generator = RealisticGoalGenerator(seed)
        self.routine_generator = RealisticRoutineGenerator(seed)

    def generate(
        self,
        scale: BenchmarkScale = BenchmarkScale.MEDIUM,
    ) -> BenchmarkDataset:
        """
        Generate complete benchmark dataset.

        Args:
            scale: Size/complexity of the dataset

        Returns:
            Complete BenchmarkDataset
        """
        config = SCALE_CONFIGS[scale]

        # Generate entities first
        entities = self.kg_generator.generate_entities(config.entity_count)

        # Generate edges
        edges = self.kg_generator.generate_edges(entities, config.edge_count)

        # Generate episodes (using entity IDs)
        entity_ids = [e.entity_id for e in entities]
        episodes = self.episode_generator.generate(
            count=config.episode_count,
            entity_ids=entity_ids,
            time_span_days=config.time_span_days,
        )

        # Generate goals and routines
        goals = self.goal_generator.generate(config.goal_count)
        routines = self.routine_generator.generate(config.routine_count)

        return BenchmarkDataset(
            episodes=episodes,
            entities=entities,
            edges=edges,
            goals=goals,
            routines=routines,
            scale=scale,
            seed=self.seed,
        )

    def generate_custom(
        self,
        episode_count: int,
        entity_count: int,
        edge_count: int,
        goal_count: int = 10,
        routine_count: int = 10,
        time_span_days: int = 30,
    ) -> BenchmarkDataset:
        """Generate dataset with custom sizes."""
        # Generate entities first
        entities = self.kg_generator.generate_entities(entity_count)

        # Generate edges
        edges = self.kg_generator.generate_edges(entities, edge_count)

        # Generate episodes
        entity_ids = [e.entity_id for e in entities]
        episodes = self.episode_generator.generate(
            count=episode_count,
            entity_ids=entity_ids,
            time_span_days=time_span_days,
        )

        # Generate goals and routines
        goals = self.goal_generator.generate(goal_count)
        routines = self.routine_generator.generate(routine_count)

        return BenchmarkDataset(
            episodes=episodes,
            entities=entities,
            edges=edges,
            goals=goals,
            routines=routines,
            scale=BenchmarkScale.MEDIUM,  # Custom scale
            seed=self.seed,
        )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def create_benchmark_dataset(
    scale: BenchmarkScale = BenchmarkScale.MEDIUM,
    seed: int = 42,
) -> BenchmarkDataset:
    """
    Convenience function to create a benchmark dataset.

    Args:
        scale: Dataset scale
        seed: Random seed for reproducibility

    Returns:
        BenchmarkDataset
    """
    generator = BenchmarkDatasetGenerator(seed=seed)
    return generator.generate(scale)


def create_small_dataset(seed: int = 42) -> BenchmarkDataset:
    """Create small dataset for quick tests."""
    return create_benchmark_dataset(BenchmarkScale.SMALL, seed)


def create_medium_dataset(seed: int = 42) -> BenchmarkDataset:
    """Create medium dataset for normal tests."""
    return create_benchmark_dataset(BenchmarkScale.MEDIUM, seed)


def create_large_dataset(seed: int = 42) -> BenchmarkDataset:
    """Create large dataset for stress tests."""
    return create_benchmark_dataset(BenchmarkScale.LARGE, seed)
