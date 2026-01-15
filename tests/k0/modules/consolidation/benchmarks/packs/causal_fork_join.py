"""Causal Fork-Join pack - CPN focus with diamond DAG patterns.

This pack tests CPN's ability to handle complex causal structures:
- Fork patterns: 1 cause -> multiple effects
- Join patterns: multiple causes -> 1 effect
- Diamond patterns: A -> (B, C) -> D
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List

from ..r5_embeddings import get_embedding_service

# ─────────────────────────────────────────────────────────────────────────────
# Data classes (reuse pattern from causal_deep)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ForkJoinEpisode:
    """Episode with fork-join causal structure."""

    episode_id: str
    summary: str
    timestamp: int
    emotional_valence: float
    participants: List[str]
    location: str
    activity_type: str
    entity_ids: List[str] = None

    def __post_init__(self):
        if self.entity_ids is None:
            self.entity_ids = []

    @property
    def sentiment_score(self) -> float:
        return self.emotional_valence

    @property
    def salience(self) -> float:
        return 0.9

    @property
    def start_time_ms(self) -> int:
        return self.timestamp


@dataclass
class ForkJoinEntity:
    """Entity in fork-join DAG."""

    entity_id: str
    name: str
    entity_type: str
    category: str
    _observation_count: int = 1

    @property
    def observation_count(self) -> int:
        return self._observation_count


@dataclass
class ForkJoinEdge:
    """Causal or semantic edge."""

    source_id: str
    target_id: str
    relation: str
    weight: float
    edge_type: str = "CAUSES"
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
class ForkJoinGoal:
    """Goal for MCTS."""

    goal_id: str
    description: str
    priority: float
    target_value: float = 1.0


@dataclass
class ForkJoinAction:
    """Action for MCTS."""

    action_id: str
    name: str
    duration_hours: float
    goal_alignment: float
    expected_reward: float


# ─────────────────────────────────────────────────────────────────────────────
# Fork-Join DAG Patterns
# ─────────────────────────────────────────────────────────────────────────────
#
# Diamond 1 (Family Stress):
#   OVERCOMMITMENT
#       /       \
#   WORK_LATE   FORGOT_PROMISE
#       \       /
#      SPOUSE_UPSET
#           |
#   RELATIONSHIP_TENSION
#
# Diamond 2 (Health Impact):
#   POOR_SLEEP
#       /       \
#   IRRITABLE    LOW_ENERGY
#       \       /
#      POOR_DECISIONS
#           |
#   REGRET
#
# Wide Fork (Birthday Planning):
#   PARTY_PLANNING
#     /  |  |  \
#  CAKE VENUE GUESTS DECORATIONS
#     \  |  |  /
#   SUCCESSFUL_PARTY
#
# Chain with Multiple Joins:
#   A -> B -> D
#   C ------> D -> E
#             F -> E -> G


def _create_entities(seed: int) -> List[ForkJoinEntity]:
    """Create entities for fork-join patterns."""
    return [
        # Diamond 1: Family Stress
        ForkJoinEntity("ENT_OVERCOMMITMENT", "Overcommitment", "event", "work", 25),
        ForkJoinEntity("ENT_WORK_LATE", "Working Late", "event", "work", 30),
        ForkJoinEntity("ENT_FORGOT_PROMISE", "Forgot Promise", "event", "family", 15),
        ForkJoinEntity("ENT_SPOUSE_UPSET", "Spouse Upset", "emotion", "family", 20),
        ForkJoinEntity("ENT_RELATIONSHIP_TENSION", "Relationship Tension", "state", "family", 18),
        # Diamond 2: Health Impact
        ForkJoinEntity("ENT_POOR_SLEEP", "Poor Sleep", "state", "health", 35),
        ForkJoinEntity("ENT_IRRITABLE", "Irritability", "emotion", "health", 25),
        ForkJoinEntity("ENT_LOW_ENERGY", "Low Energy", "state", "health", 30),
        ForkJoinEntity("ENT_POOR_DECISIONS", "Poor Decisions", "event", "work", 12),
        ForkJoinEntity("ENT_REGRET", "Regret", "emotion", "health", 20),
        # Wide Fork: Party Planning
        ForkJoinEntity("ENT_PARTY_PLANNING", "Party Planning", "event", "family", 10),
        ForkJoinEntity("ENT_CAKE", "Cake Preparation", "task", "family", 8),
        ForkJoinEntity("ENT_VENUE", "Venue Booking", "task", "family", 5),
        ForkJoinEntity("ENT_GUESTS", "Guest Invitations", "task", "family", 12),
        ForkJoinEntity("ENT_DECORATIONS", "Decorations", "task", "family", 7),
        ForkJoinEntity("ENT_SUCCESSFUL_PARTY", "Successful Party", "event", "family", 15),
        # Complex Chain
        ForkJoinEntity("ENT_INITIAL_MISTAKE", "Initial Mistake", "event", "work", 8),
        ForkJoinEntity("ENT_COVER_UP_ATTEMPT", "Cover Up Attempt", "event", "work", 5),
        ForkJoinEntity("ENT_DISCOVERED", "Discovery", "event", "work", 10),
        ForkJoinEntity("ENT_EXTERNAL_PRESSURE", "External Pressure", "event", "work", 15),
        ForkJoinEntity("ENT_CONFESSION", "Confession", "event", "work", 7),
        ForkJoinEntity("ENT_TRUST_DAMAGE", "Trust Damage", "state", "family", 12),
        ForkJoinEntity("ENT_REBUILDING", "Rebuilding Trust", "event", "family", 20),
        # Resolution nodes
        ForkJoinEntity("ENT_COMMUNICATION", "Open Communication", "action", "family", 18),
        ForkJoinEntity("ENT_UNDERSTANDING", "Mutual Understanding", "state", "family", 22),
    ]


def _create_kg_edges(seed: int) -> List[ForkJoinEdge]:
    """Create fork-join causal patterns."""
    return [
        # Diamond 1: Family Stress (fork then join)
        ForkJoinEdge("ENT_OVERCOMMITMENT", "ENT_WORK_LATE", "CAUSES", 0.85),
        ForkJoinEdge("ENT_OVERCOMMITMENT", "ENT_FORGOT_PROMISE", "CAUSES", 0.7),
        ForkJoinEdge("ENT_WORK_LATE", "ENT_SPOUSE_UPSET", "CAUSES", 0.75),
        ForkJoinEdge("ENT_FORGOT_PROMISE", "ENT_SPOUSE_UPSET", "CAUSES", 0.8),
        ForkJoinEdge("ENT_SPOUSE_UPSET", "ENT_RELATIONSHIP_TENSION", "CAUSES", 0.85),
        # Diamond 2: Health Impact
        ForkJoinEdge("ENT_POOR_SLEEP", "ENT_IRRITABLE", "CAUSES", 0.8),
        ForkJoinEdge("ENT_POOR_SLEEP", "ENT_LOW_ENERGY", "CAUSES", 0.85),
        ForkJoinEdge("ENT_IRRITABLE", "ENT_POOR_DECISIONS", "CAUSES", 0.6),
        ForkJoinEdge("ENT_LOW_ENERGY", "ENT_POOR_DECISIONS", "CAUSES", 0.65),
        ForkJoinEdge("ENT_POOR_DECISIONS", "ENT_REGRET", "CAUSES", 0.75),
        # Wide Fork: Party Planning (4-way fork, 4-way join)
        ForkJoinEdge("ENT_PARTY_PLANNING", "ENT_CAKE", "CAUSES", 0.9),
        ForkJoinEdge("ENT_PARTY_PLANNING", "ENT_VENUE", "CAUSES", 0.9),
        ForkJoinEdge("ENT_PARTY_PLANNING", "ENT_GUESTS", "CAUSES", 0.9),
        ForkJoinEdge("ENT_PARTY_PLANNING", "ENT_DECORATIONS", "CAUSES", 0.9),
        ForkJoinEdge("ENT_CAKE", "ENT_SUCCESSFUL_PARTY", "CAUSES", 0.7),
        ForkJoinEdge("ENT_VENUE", "ENT_SUCCESSFUL_PARTY", "CAUSES", 0.8),
        ForkJoinEdge("ENT_GUESTS", "ENT_SUCCESSFUL_PARTY", "CAUSES", 0.85),
        ForkJoinEdge("ENT_DECORATIONS", "ENT_SUCCESSFUL_PARTY", "CAUSES", 0.6),
        # Complex chain with multiple joins
        ForkJoinEdge("ENT_INITIAL_MISTAKE", "ENT_COVER_UP_ATTEMPT", "CAUSES", 0.7),
        ForkJoinEdge("ENT_COVER_UP_ATTEMPT", "ENT_DISCOVERED", "CAUSES", 0.8),
        ForkJoinEdge("ENT_EXTERNAL_PRESSURE", "ENT_DISCOVERED", "CAUSES", 0.6),
        ForkJoinEdge("ENT_DISCOVERED", "ENT_CONFESSION", "CAUSES", 0.75),
        ForkJoinEdge("ENT_TRUST_DAMAGE", "ENT_CONFESSION", "CAUSES", 0.5),
        ForkJoinEdge("ENT_CONFESSION", "ENT_REBUILDING", "CAUSES", 0.8),
        # Cross-diamond connections (creates depth 5 paths)
        ForkJoinEdge("ENT_RELATIONSHIP_TENSION", "ENT_POOR_SLEEP", "CAUSES", 0.7),
        ForkJoinEdge("ENT_REGRET", "ENT_COMMUNICATION", "CAUSES", 0.65),
        ForkJoinEdge("ENT_COMMUNICATION", "ENT_UNDERSTANDING", "CAUSES", 0.8),
        ForkJoinEdge("ENT_UNDERSTANDING", "ENT_REBUILDING", "CAUSES", 0.75),
        # Additional fork from regret
        ForkJoinEdge("ENT_REGRET", "ENT_TRUST_DAMAGE", "CAUSES", 0.55),
    ]


def _create_semantic_edges(seed: int) -> List[ForkJoinEdge]:
    """Create semantic edges for BGT-SM."""
    return [
        ForkJoinEdge("ENT_OVERCOMMITMENT", "ENT_POOR_SLEEP", "correlates_with", 0.6, "SEMANTIC"),
        ForkJoinEdge("ENT_IRRITABLE", "ENT_SPOUSE_UPSET", "correlates_with", 0.5, "SEMANTIC"),
        ForkJoinEdge("ENT_COMMUNICATION", "ENT_SUCCESSFUL_PARTY", "enables", 0.4, "SEMANTIC"),
        ForkJoinEdge("ENT_REBUILDING", "ENT_UNDERSTANDING", "requires", 0.7, "SEMANTIC"),
    ]


def _create_episodes(seed: int) -> List[ForkJoinEpisode]:
    """Create episodes with fork-join causal structures."""
    base_time = int(datetime.now().timestamp() * 1000)
    day_ms = 24 * 60 * 60 * 1000

    return [
        # Diamond 1 trigger
        ForkJoinEpisode(
            episode_id="01FORK_JOIN_001",
            summary="Said yes to too many projects. Ended up working late AND forgot anniversary dinner.",
            timestamp=base_time - 14 * day_ms,
            emotional_valence=-0.85,
            participants=["self", "spouse"],
            location="office",
            activity_type="overcommitment",
            entity_ids=["ENT_OVERCOMMITMENT", "ENT_WORK_LATE", "ENT_FORGOT_PROMISE"],
        ),
        ForkJoinEpisode(
            episode_id="01FORK_JOIN_002",
            summary="Spouse was really hurt about the forgotten anniversary. Tension is building.",
            timestamp=base_time - 13 * day_ms,
            emotional_valence=-0.75,
            participants=["self", "spouse"],
            location="home",
            activity_type="relationship_conflict",
            entity_ids=["ENT_SPOUSE_UPSET", "ENT_RELATIONSHIP_TENSION"],
        ),
        # Diamond 2 trigger
        ForkJoinEpisode(
            episode_id="01FORK_JOIN_003",
            summary="Haven't been sleeping well due to relationship stress. Feeling irritable and tired.",
            timestamp=base_time - 12 * day_ms,
            emotional_valence=-0.6,
            participants=["self"],
            location="home",
            activity_type="health_impact",
            entity_ids=["ENT_POOR_SLEEP", "ENT_IRRITABLE", "ENT_LOW_ENERGY"],
        ),
        ForkJoinEpisode(
            episode_id="01FORK_JOIN_004",
            summary="Made a bad call at work due to being tired. Now regretting the whole cascade.",
            timestamp=base_time - 11 * day_ms,
            emotional_valence=-0.7,
            participants=["self"],
            location="office",
            activity_type="poor_judgment",
            entity_ids=["ENT_POOR_DECISIONS", "ENT_REGRET"],
        ),
        # Wide fork: positive scenario
        ForkJoinEpisode(
            episode_id="01FORK_JOIN_005",
            summary="Started planning Tommy's birthday party. Lots of tasks to coordinate.",
            timestamp=base_time - 8 * day_ms,
            emotional_valence=0.7,
            participants=["self", "spouse", "Tommy"],
            location="home",
            activity_type="event_planning",
            entity_ids=[
                "ENT_PARTY_PLANNING",
                "ENT_CAKE",
                "ENT_VENUE",
                "ENT_GUESTS",
                "ENT_DECORATIONS",
            ],
        ),
        ForkJoinEpisode(
            episode_id="01FORK_JOIN_006",
            summary="The party was a success! Everything came together perfectly.",
            timestamp=base_time - 5 * day_ms,
            emotional_valence=0.9,
            participants=["self", "spouse", "Tommy", "guests"],
            location="venue",
            activity_type="celebration",
            entity_ids=["ENT_SUCCESSFUL_PARTY"],
        ),
        # Complex chain
        ForkJoinEpisode(
            episode_id="01FORK_JOIN_007",
            summary="Made a mistake at work and tried to hide it. External audit discovered it.",
            timestamp=base_time - 4 * day_ms,
            emotional_valence=-0.8,
            participants=["self", "boss"],
            location="office",
            activity_type="work_crisis",
            entity_ids=["ENT_INITIAL_MISTAKE", "ENT_COVER_UP_ATTEMPT", "ENT_DISCOVERED"],
        ),
        ForkJoinEpisode(
            episode_id="01FORK_JOIN_008",
            summary="Had an honest conversation with spouse about everything. Starting to rebuild trust.",
            timestamp=base_time - 2 * day_ms,
            emotional_valence=0.5,
            participants=["self", "spouse"],
            location="home",
            activity_type="reconciliation",
            entity_ids=["ENT_CONFESSION", "ENT_COMMUNICATION", "ENT_REBUILDING"],
        ),
    ]


def _create_actions(seed: int) -> List[ForkJoinAction]:
    """Create actions for MCTS."""
    return [
        ForkJoinAction("ACT001", "Have honest conversation", 1.0, 0.9, 0.75),
        ForkJoinAction("ACT002", "Plan special date night", 3.0, 0.85, 0.7),
        ForkJoinAction("ACT003", "Delegate work tasks", 0.5, 0.7, 0.6),
        ForkJoinAction("ACT004", "Set boundaries at work", 0.5, 0.75, 0.65),
        ForkJoinAction("ACT005", "Get more sleep", 8.0, 0.8, 0.7),
        ForkJoinAction("ACT006", "Plan family activity", 2.0, 0.85, 0.75),
    ]


def _create_goals(seed: int) -> List[ForkJoinGoal]:
    """Create goals for MCTS."""
    return [
        ForkJoinGoal("GOAL001", "Repair relationship with spouse", 0.95, 1.0),
        ForkJoinGoal("GOAL002", "Restore work-life balance", 0.85, 1.0),
        ForkJoinGoal("GOAL003", "Improve health and sleep", 0.8, 1.0),
    ]


def _create_initial_state(seed: int) -> Dict[str, Any]:
    """Create initial state for MCTS."""
    return {
        "time_of_day": "evening",
        "day": "Sunday",
        "relationship_status": "strained",
        "sleep_quality": "poor",
        "work_stress": "high",
        "pending_conversations": ["spouse", "boss"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Coverage thresholds for causal_fork_join pack
# ─────────────────────────────────────────────────────────────────────────────

FORK_JOIN_EXPECTED_PROPERTIES = {
    # CPN - primary focus with fork-join patterns
    "cpn_min_counterfactuals": 20,
    "cpn_path_length_ge_2_ratio": 0.6,
    "cpn_path_length_ge_3_count": 5,
    "cpn_max_path_length": 5,
    "cpn_plausibility_variance": 0.02,
    "cpn_scenario_type_count": 3,
    # MCTS
    "mcts_budget_consumption_ratio": 0.6,
    "mcts_max_visit_count": 6,
    # BGT-SM
    "bgt_insights_min": 2,
    "bgt_pmi_variance": True,
    # SPC-UQ
    "spc_reconstructions_min": 1,
    "spc_provenance_types_min": 1,
}


# ─────────────────────────────────────────────────────────────────────────────
# Main builder function
# ─────────────────────────────────────────────────────────────────────────────


def build_world(seed: int = 42, use_ultrabert: bool | None = None):
    """Build the causal_fork_join world.

    Args:
        seed: Random seed for reproducibility.
        use_ultrabert: If True, use UltraBERT embeddings.

    Returns:
        World instance with fork-join DAG patterns.
    """
    from ..r5_data_factory import World

    entities = _create_entities(seed)
    episodes = _create_episodes(seed)
    semantic_edges = _create_semantic_edges(seed)
    kg_edges = _create_kg_edges(seed)
    actions = _create_actions(seed)
    goals = _create_goals(seed)
    initial_state = _create_initial_state(seed)

    # Generate embeddings
    embedding_service = get_embedding_service(use_ultrabert)
    embeddings = embedding_service.embed_entities(entities)

    return World(
        pack_name="causal_fork_join",
        seed=seed,
        episodes=episodes,
        kg_edges=kg_edges,
        entities=entities,
        semantic_edges=semantic_edges,
        embeddings=embeddings,
        initial_state=initial_state,
        actions=actions,
        goals=goals,
        constraints=None,
        incomplete_episodes=None,
        fragments=None,
        schemas=None,
        context=None,
        expected_properties=FORK_JOIN_EXPECTED_PROPERTIES,
        difficulty="hard",
    )
