"""Mixed stress pack exercising all algorithms at scale.

This pack generates a large-scale world with:
- 1000+ entities across multiple categories
- 100+ episodes with varied emotional valence
- Deep causal chains (5+ levels)
- Complex semantic networks
- Multiple provenance types for SPC-UQ

Used for performance testing, memory profiling, and stress testing.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class StressEpisode:
    """Episode for stress testing."""

    episode_id: str
    summary: str
    timestamp: int
    emotional_valence: float
    participants: List[str]
    location: str
    activity_type: str
    entity_ids: List[str] = field(default_factory=list)

    @property
    def sentiment_score(self) -> float:
        return self.emotional_valence

    @property
    def salience(self) -> float:
        return abs(self.emotional_valence)

    @property
    def start_time_ms(self) -> int:
        return self.timestamp


@dataclass
class StressEntity:
    """Entity for stress testing."""

    entity_id: str
    name: str
    entity_type: str
    category: str
    _observation_count: int = 1

    @property
    def observation_count(self) -> int:
        return self._observation_count


@dataclass
class StressEdge:
    """Edge for stress testing."""

    source_id: str
    target_id: str
    relation: str
    weight: float
    edge_type: str = "SEMANTIC"
    _observation_count: int = 1

    @property
    def source_entity_id(self) -> str:
        return self.source_id

    @property
    def target_entity_id(self) -> str:
        return self.target_id

    @property
    def observation_count(self) -> int:
        return self._observation_count

    @property
    def relation_type(self) -> str:
        return self.relation


@dataclass
class StressGoal:
    """Goal for MCTS stress testing."""

    goal_id: str
    description: str
    priority: float
    target_value: float = 1.0


@dataclass
class StressAction:
    """Action for MCTS stress testing."""

    action_id: str
    name: str
    duration_hours: float
    goal_alignment: float
    expected_reward: float
    preconditions: List[str] = field(default_factory=list)


@dataclass
class StressFragment:
    """Fragment for SPC-UQ stress testing."""

    fragment_id: str
    source_episode_id: str
    source_event_id: str
    start_time_ms: int
    end_time_ms: int
    content: str
    attributes: tuple


@dataclass
class StressIncompleteEpisode:
    """Incomplete episode for SPC-UQ stress testing."""

    episode_id: str
    summary: str
    timestamp: int
    location_name: Optional[str] = None
    participants: Optional[List[str]] = None
    activity_type: Optional[str] = None
    ambiguity_score: float = 0.7


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

CATEGORIES = [
    "family",
    "education",
    "work",
    "entertainment",
    "finance",
    "health",
    "social",
    "travel",
    "sports",
    "technology",
]

ENTITY_TYPES = ["person", "activity", "location", "topic", "object", "event"]

RELATIONS = [
    "related_to",
    "causes",
    "follows",
    "belongs_to",
    "participates_in",
    "located_at",
    "associated_with",
    "conflicts_with",
    "supports",
    "precedes",
]

LOCATIONS = [
    "home_kitchen",
    "home_living_room",
    "home_bedroom",
    "home_office",
    "school",
    "office",
    "park",
    "gym",
    "mall",
    "restaurant",
    "hospital",
    "library",
    "theater",
    "stadium",
    "airport",
]

ACTIVITY_TYPES = [
    "family_meal",
    "work_meeting",
    "exercise",
    "entertainment",
    "education",
    "travel",
    "shopping",
    "social_event",
    "healthcare",
    "hobby",
]

PROVENANCE_TYPES = ["calendar", "message", "sensory", "inferred", "photo", "voice"]


# ─────────────────────────────────────────────────────────────────────────────
# Generators
# ─────────────────────────────────────────────────────────────────────────────


def _create_entities(rng: random.Random, count: int = 1000) -> List[StressEntity]:
    """Generate a large set of entities."""
    entities = []

    # Create category distribution (more family/work entities)
    category_weights = {
        "family": 0.2,
        "work": 0.2,
        "education": 0.15,
        "entertainment": 0.1,
        "health": 0.1,
        "finance": 0.05,
        "social": 0.1,
        "travel": 0.05,
        "sports": 0.03,
        "technology": 0.02,
    }

    for i in range(count):
        # Weighted random category
        r = rng.random()
        cumulative = 0
        category = "family"
        for cat, weight in category_weights.items():
            cumulative += weight
            if r < cumulative:
                category = cat
                break

        entity_type = rng.choice(ENTITY_TYPES)
        obs_count = int(rng.paretovariate(1.5))  # Power law distribution
        obs_count = max(1, min(obs_count, 100))

        entity = StressEntity(
            entity_id=f"ENT_{i:05d}",
            name=f"{category}_{entity_type}_{i}",
            entity_type=entity_type,
            category=category,
            _observation_count=obs_count,
        )
        entities.append(entity)

    return entities


def _create_semantic_edges(
    rng: random.Random, entities: List[StressEntity], edge_count: int = 3000
) -> List[StressEdge]:
    """Generate semantic edges with preference for same-category connections."""
    edges = []
    entity_by_category: Dict[str, List[StressEntity]] = {}

    for e in entities:
        if e.category not in entity_by_category:
            entity_by_category[e.category] = []
        entity_by_category[e.category].append(e)

    entity_ids = [e.entity_id for e in entities]

    for i in range(edge_count):
        # 70% same category, 30% cross-category
        if rng.random() < 0.7:
            category = rng.choice(list(entity_by_category.keys()))
            cat_entities = entity_by_category[category]
            if len(cat_entities) >= 2:
                src, tgt = rng.sample(cat_entities, 2)
            else:
                src, tgt = rng.sample(entities, 2)
        else:
            src, tgt = rng.sample(entities, 2)

        edge = StressEdge(
            source_id=src.entity_id,
            target_id=tgt.entity_id,
            relation=rng.choice(RELATIONS),
            weight=rng.uniform(0.3, 1.0),
            edge_type="SEMANTIC",
            _observation_count=rng.randint(1, 20),
        )
        edges.append(edge)

    return edges


def _create_kg_edges(
    rng: random.Random, entities: List[StressEntity], chain_count: int = 50
) -> List[StressEdge]:
    """Generate causal edges forming deep chains (5+ levels)."""
    edges = []

    # Create multiple causal chains of varying depths
    for chain_idx in range(chain_count):
        depth = rng.randint(4, 7)  # 4-7 levels deep
        chain_entities = rng.sample(entities, min(depth + 1, len(entities)))

        for i in range(len(chain_entities) - 1):
            edge = StressEdge(
                source_id=chain_entities[i].entity_id,
                target_id=chain_entities[i + 1].entity_id,
                relation="CAUSES",
                weight=rng.uniform(0.6, 1.0),
                edge_type="CAUSES",
                _observation_count=rng.randint(1, 10),
            )
            edges.append(edge)

    # Add fork/join patterns
    for _ in range(chain_count // 2):
        if len(entities) < 4:
            continue
        cause, effect1, effect2, join = rng.sample(entities, 4)

        # Fork: one cause -> two effects
        edges.append(
            StressEdge(
                source_id=cause.entity_id,
                target_id=effect1.entity_id,
                relation="CAUSES",
                weight=rng.uniform(0.7, 1.0),
                edge_type="CAUSES",
            )
        )
        edges.append(
            StressEdge(
                source_id=cause.entity_id,
                target_id=effect2.entity_id,
                relation="CAUSES",
                weight=rng.uniform(0.7, 1.0),
                edge_type="CAUSES",
            )
        )

        # Join: two causes -> one effect
        edges.append(
            StressEdge(
                source_id=effect1.entity_id,
                target_id=join.entity_id,
                relation="CAUSES",
                weight=rng.uniform(0.6, 0.9),
                edge_type="CAUSES",
            )
        )
        edges.append(
            StressEdge(
                source_id=effect2.entity_id,
                target_id=join.entity_id,
                relation="CAUSES",
                weight=rng.uniform(0.6, 0.9),
                edge_type="CAUSES",
            )
        )

    return edges


def _create_episodes(
    rng: random.Random, entities: List[StressEntity], count: int = 150
) -> List[StressEpisode]:
    """Generate episodes with varied emotional valence."""
    episodes = []
    base_time = int(datetime.now().timestamp() * 1000)
    hour_ms = 60 * 60 * 1000

    for i in range(count):
        # Emotional valence distribution: mostly neutral with some extremes
        valence = rng.gauss(0.0, 0.4)
        valence = max(-1.0, min(1.0, valence))

        # Select random entities to mention
        entity_count = rng.randint(2, 6)
        mentioned = rng.sample(entities, min(entity_count, len(entities)))

        participants = []
        for e in mentioned:
            if e.entity_type == "person":
                participants.append(e.name)
        if not participants:
            participants = ["self"]

        episode = StressEpisode(
            episode_id=f"EP_{i:05d}",
            summary=f"Episode {i} involving {len(mentioned)} entities",
            timestamp=base_time - i * hour_ms * rng.randint(1, 24),
            emotional_valence=valence,
            participants=participants,
            location=rng.choice(LOCATIONS),
            activity_type=rng.choice(ACTIVITY_TYPES),
            entity_ids=[e.entity_id for e in mentioned],
        )
        episodes.append(episode)

    return episodes


def _create_actions(rng: random.Random, count: int = 100) -> List[StressAction]:
    """Generate actions for MCTS with varied rewards and preconditions."""
    actions = []

    action_templates = [
        ("Family time with {}", "family", 2.0, 0.9),
        ("Work on project {}", "work", 1.5, 0.5),
        ("Exercise routine {}", "health", 1.0, 0.6),
        ("Educational activity {}", "education", 1.0, 0.7),
        ("Entertainment {}", "entertainment", 1.5, 0.4),
        ("Social gathering {}", "social", 2.0, 0.7),
        ("Travel to {}", "travel", 3.0, 0.6),
        ("Shopping for {}", "finance", 1.0, 0.3),
        ("Sports activity {}", "sports", 1.5, 0.5),
        ("Tech project {}", "technology", 2.0, 0.5),
    ]

    for i in range(count):
        template_name, category, base_duration, base_alignment = rng.choice(action_templates)

        # Vary the parameters
        duration = base_duration * rng.uniform(0.5, 1.5)
        alignment = base_alignment * rng.uniform(0.8, 1.2)
        alignment = max(0.0, min(1.0, alignment))

        # Some actions have preconditions (delayed reward)
        preconditions = []
        if rng.random() < 0.3:
            preconditions = [f"ACT_{rng.randint(0, max(0, i - 1)):05d}"]

        action = StressAction(
            action_id=f"ACT_{i:05d}",
            name=template_name.format(i),
            duration_hours=duration,
            goal_alignment=alignment,
            expected_reward=alignment * rng.uniform(0.8, 1.0),
            preconditions=preconditions,
        )
        actions.append(action)

    return actions


def _create_goals(rng: random.Random, count: int = 20) -> List[StressGoal]:
    """Generate goals for MCTS."""
    goals = []

    goal_templates = [
        "Improve family relationships",
        "Advance career",
        "Maintain health",
        "Support education",
        "Manage finances",
        "Expand social network",
        "Travel more",
        "Reduce stress",
        "Learn new skills",
        "Exercise regularly",
    ]

    for i in range(count):
        template = rng.choice(goal_templates)
        goal = StressGoal(
            goal_id=f"GOAL_{i:03d}",
            description=f"{template} (variant {i})",
            priority=rng.uniform(0.5, 1.0),
            target_value=1.0,
        )
        goals.append(goal)

    return goals


def _create_initial_state(rng: random.Random) -> Dict[str, Any]:
    """Generate initial state for MCTS."""
    return {
        "time_of_day": rng.choice(["morning", "afternoon", "evening"]),
        "day": rng.choice(["weekday", "weekend"]),
        "family_mood": rng.choice(["happy", "neutral", "stressed"]),
        "energy_level": rng.uniform(0.3, 1.0),
        "pending_tasks": [f"task_{i}" for i in range(rng.randint(3, 10))],
        "budget_remaining": rng.uniform(100, 1000),
        "time_budget_hours": rng.uniform(2, 8),
    }


def _create_incomplete_episodes(
    rng: random.Random, count: int = 30
) -> List[StressIncompleteEpisode]:
    """Generate incomplete episodes for SPC-UQ."""
    episodes = []
    base_time = int(datetime.now().timestamp() * 1000)

    for i in range(count):
        # Randomly omit some fields
        location = rng.choice(LOCATIONS) if rng.random() > 0.4 else None
        participants = (
            [f"person_{j}" for j in range(rng.randint(1, 4))] if rng.random() > 0.5 else None
        )
        activity = rng.choice(ACTIVITY_TYPES) if rng.random() > 0.3 else None

        episode = StressIncompleteEpisode(
            episode_id=f"INC_{i:05d}",
            summary=f"Incomplete episode {i} - details missing",
            timestamp=base_time - i * 3600000,
            location_name=location,
            participants=participants,
            activity_type=activity,
            ambiguity_score=rng.uniform(0.4, 0.9),
        )
        episodes.append(episode)

    return episodes


def _create_fragments(
    rng: random.Random,
    incomplete_episodes: List[StressIncompleteEpisode],
    fragments_per_episode: int = 5,
) -> List[StressFragment]:
    """Generate fragments with multiple provenance types."""
    fragments = []
    base_time = int(datetime.now().timestamp() * 1000)

    for ep in incomplete_episodes:
        for i in range(rng.randint(2, fragments_per_episode)):
            prov_type = rng.choice(PROVENANCE_TYPES)
            confidence = {
                "calendar": rng.uniform(0.85, 0.98),
                "message": rng.uniform(0.6, 0.85),
                "sensory": rng.uniform(0.3, 0.6),
                "inferred": rng.uniform(0.2, 0.5),
                "photo": rng.uniform(0.75, 0.95),
                "voice": rng.uniform(0.5, 0.8),
            }[prov_type]

            fragment = StressFragment(
                fragment_id=f"FRAG_{ep.episode_id}_{i:02d}",
                source_episode_id=ep.episode_id,
                source_event_id=f"EVT_{rng.randint(1, 1000):04d}",
                start_time_ms=base_time - rng.randint(0, 86400000),
                end_time_ms=base_time - rng.randint(0, 43200000),
                content=f"Fragment content for {prov_type} provenance",
                attributes=(("prov", prov_type), ("confidence", confidence)),
            )
            fragments.append(fragment)

    return fragments


def _create_context(rng: random.Random) -> Dict[str, Any]:
    """Generate context for SPC-UQ."""
    return {
        "time_of_day": rng.choice(["morning", "afternoon", "evening", "night"]),
        "day": rng.choice(["weekday", "weekend"]),
        "nearby_locations": rng.sample(LOCATIONS, min(5, len(LOCATIONS))),
        "known_locations": LOCATIONS,
        "frequent_contacts": [f"contact_{i}" for i in range(rng.randint(5, 15))],
        "recent_activities": rng.sample(ACTIVITY_TYPES, min(3, len(ACTIVITY_TYPES))),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Coverage Thresholds
# ─────────────────────────────────────────────────────────────────────────────

STRESS_EXPECTED_PROPERTIES = {
    # CPN thresholds (challenging)
    "cpn_min_counterfactuals": 50,
    "cpn_path_length_ge_3_count": 20,
    "cpn_max_path_length": 5,
    "cpn_plausibility_variance_min": 0.02,
    "cpn_scenario_type_count": 3,
    # MCTS thresholds
    "mcts_budget_consumption_ratio": 0.8,
    "mcts_max_visit_count": 20,
    "mcts_visit_variance_required": True,
    "mcts_reward_spread_min": 0.4,
    # BGT-SM thresholds
    "bgt_insights_min": 10,
    "bgt_pmi_variance_required": True,
    "bgt_cross_cluster_ratio": 0.3,
    "bgt_semantic_distance_range": [0.2, 0.9],
    # SPC-UQ thresholds
    "spc_reconstructions_min": 10,
    "spc_provenance_types_min": 4,
    "spc_confidence_variance_min": 0.1,
    "spc_uncertainty_correlation_required": True,
}


# ─────────────────────────────────────────────────────────────────────────────
# Main Builder
# ─────────────────────────────────────────────────────────────────────────────


def build_world(
    seed: int = 42,
    use_ultrabert: bool | None = None,
    entity_count: int = 1000,
    episode_count: int = 150,
    action_count: int = 100,
):
    """Build the mixed stress world.

    Args:
        seed: Random seed for reproducibility.
        use_ultrabert: If True, use UltraBERT embeddings.
        entity_count: Number of entities to generate (default 1000).
        episode_count: Number of episodes to generate (default 150).
        action_count: Number of actions to generate (default 100).

    Returns:
        World instance with stress test data.
    """
    from ..r5_data_factory import World
    from ..r5_embeddings import get_embedding_service

    rng = random.Random(seed)

    # Generate all components
    entities = _create_entities(rng, entity_count)
    episodes = _create_episodes(rng, entities, episode_count)
    semantic_edges = _create_semantic_edges(rng, entities, entity_count * 3)
    kg_edges = _create_kg_edges(rng, entities, chain_count=50)
    actions = _create_actions(rng, action_count)
    goals = _create_goals(rng, 20)
    initial_state = _create_initial_state(rng)
    incomplete_episodes = _create_incomplete_episodes(rng, 30)
    fragments = _create_fragments(rng, incomplete_episodes)
    context = _create_context(rng)

    # Generate embeddings
    embedding_service = get_embedding_service(use_ultrabert)
    embeddings = embedding_service.embed_entities(entities)

    return World(
        pack_name="mixed_stress",
        seed=seed,
        episodes=episodes,
        kg_edges=kg_edges,
        entities=entities,
        semantic_edges=semantic_edges,
        embeddings=embeddings,
        initial_state=initial_state,
        actions=actions,
        goals=goals,
        constraints={"time_budget_hours": initial_state["time_budget_hours"]},
        incomplete_episodes=incomplete_episodes,
        fragments=fragments,
        schemas=None,
        context=context,
        expected_properties=STRESS_EXPECTED_PROPERTIES,
        difficulty="hard",
    )
