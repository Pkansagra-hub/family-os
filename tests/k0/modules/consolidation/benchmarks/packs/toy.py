"""Toy pack - baseline small-world for R5 benchmarks.

This pack mirrors the current show_io.py demo data. It provides a simple
world for sanity testing all four algorithms.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..r5_embeddings import get_embedding_service

# ─────────────────────────────────────────────────────────────────────────────
# Data classes matching Protocol interfaces
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ToyEpisode:
    """Episode object matching EpisodeProtocol."""

    episode_id: str
    summary: str
    timestamp: int  # ms since epoch
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
        return 0.8

    @property
    def start_time_ms(self) -> int:
        return self.timestamp


@dataclass
class ToyEntity:
    """Entity object matching EntityProtocol."""

    entity_id: str
    name: str
    entity_type: str
    category: str
    _observation_count: int = 1

    @property
    def observation_count(self) -> int:
        return self._observation_count


@dataclass
class ToyEdge:
    """Edge object matching EdgeProtocol / KGEdgeProtocol."""

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
class ToyGoal:
    """Goal object for MCTS."""

    goal_id: str
    description: str
    priority: float
    target_value: float = 1.0


@dataclass
class ToyAction:
    """Action object for MCTS."""

    action_id: str
    name: str
    duration_hours: float
    goal_alignment: float
    expected_reward: float


@dataclass
class ToyFragment:
    """Episode fragment for SPC-UQ."""

    fragment_id: str
    source_episode_id: str
    source_event_id: str
    start_time_ms: int
    end_time_ms: int
    content: str
    attributes: tuple


@dataclass
class IncompleteEpisode:
    """Incomplete episode for SPC-UQ reconstruction."""

    episode_id: str
    summary: str
    timestamp: int
    location_name: Optional[str] = None
    participants: Optional[List[str]] = None
    activity_type: Optional[str] = None
    ambiguity_score: float = 0.7


# ─────────────────────────────────────────────────────────────────────────────
# Data generators
# ─────────────────────────────────────────────────────────────────────────────


def _create_episodes(seed: int) -> List[ToyEpisode]:
    """Create realistic family episodes for testing."""
    base_time = int(datetime.now().timestamp() * 1000)
    day_ms = 24 * 60 * 60 * 1000

    return [
        ToyEpisode(
            episode_id="01HWQR5X7KJMN3P4Q8R9S0T1V2",
            summary="Had breakfast with kids before school. Sarah was excited about her science project.",
            timestamp=base_time - 7 * day_ms,
            emotional_valence=0.8,
            participants=["self", "Sarah", "Tommy"],
            location="home_kitchen",
            activity_type="family_meal",
            entity_ids=["ENT_BREAKFAST", "ENT_SARAH", "ENT_TOMMY"],
        ),
        ToyEpisode(
            episode_id="01HWQR5X8LKNO4Q5R9S0T1U2W3",
            summary="Missed Tommy's soccer practice because of work meeting that ran late.",
            timestamp=base_time - 5 * day_ms,
            emotional_valence=-0.7,
            participants=["self", "Tommy"],
            location="office",
            activity_type="work_conflict",
            entity_ids=["ENT_WORK_MEETING", "ENT_SOCCER", "ENT_TOMMY"],
        ),
        ToyEpisode(
            episode_id="01HWQR5X9MLOP5R6S0T1U2V3X4",
            summary="Family movie night - watched kids' favorite animated film together.",
            timestamp=base_time - 3 * day_ms,
            emotional_valence=0.9,
            participants=["self", "Sarah", "Tommy", "spouse"],
            location="home_living_room",
            activity_type="family_entertainment",
            entity_ids=["ENT_MOVIE", "ENT_FAMILY_TIME"],
        ),
        ToyEpisode(
            episode_id="01HWQR5XANMPQ6S7T1U2V3W4Y5",
            summary="Argued with spouse about household budget. Felt stressed and frustrated.",
            timestamp=base_time - 2 * day_ms,
            emotional_valence=-0.65,
            participants=["self", "spouse"],
            location="home_bedroom",
            activity_type="relationship_conflict",
            entity_ids=["ENT_BUDGET", "ENT_SPOUSE", "ENT_STRESS"],
        ),
        ToyEpisode(
            episode_id="01HWQR5XBOQRS7T8U2V3W4X5Z6",
            summary="Helped Sarah with homework. She understood fractions after my explanation.",
            timestamp=base_time - 1 * day_ms,
            emotional_valence=0.7,
            participants=["self", "Sarah"],
            location="home_study",
            activity_type="parenting",
            entity_ids=["ENT_HOMEWORK", "ENT_SARAH", "ENT_FRACTIONS"],
        ),
    ]


def _create_entities(seed: int) -> List[ToyEntity]:
    """Create entities for BGT-SM with varied observation counts."""
    return [
        ToyEntity("ENT001", "Sarah", "person", "family", _observation_count=50),
        ToyEntity("ENT002", "Tommy", "person", "family", _observation_count=45),
        ToyEntity("ENT003", "spouse", "person", "family", _observation_count=40),
        ToyEntity("ENT004", "homework", "activity", "education", _observation_count=15),
        ToyEntity("ENT005", "soccer", "activity", "sports", _observation_count=8),
        ToyEntity("ENT006", "work_meeting", "activity", "work", _observation_count=25),
        ToyEntity("ENT007", "budget", "topic", "finance", _observation_count=5),
        ToyEntity("ENT008", "science_project", "activity", "education", _observation_count=3),
        ToyEntity("ENT009", "movie_night", "activity", "entertainment", _observation_count=10),
        ToyEntity("ENT010", "fractions", "topic", "education", _observation_count=2),
    ]


def _create_semantic_edges(seed: int) -> List[ToyEdge]:
    """Create semantic edges for BGT-SM with varied observation counts."""
    return [
        ToyEdge("ENT001", "ENT004", "does", 0.8, _observation_count=12),
        ToyEdge("ENT001", "ENT008", "works_on", 0.9, _observation_count=3),
        ToyEdge("ENT001", "ENT010", "learns", 0.7, _observation_count=2),
        ToyEdge("ENT002", "ENT005", "plays", 0.9, _observation_count=7),
        ToyEdge("ENT003", "ENT007", "discusses", 0.6, _observation_count=4),
        ToyEdge("ENT001", "ENT009", "enjoys", 0.8, _observation_count=8),
        ToyEdge("ENT002", "ENT009", "enjoys", 0.8, _observation_count=9),
        ToyEdge("ENT006", "ENT005", "conflicts_with", -0.5, _observation_count=2),
        ToyEdge("ENT004", "ENT005", "balances_with", 0.4, _observation_count=1),
        ToyEdge("ENT007", "ENT009", "funded_by", 0.3, _observation_count=1),
    ]


def _create_kg_edges(seed: int) -> List[ToyEdge]:
    """Create causal edges (CAUSES) for CPN."""
    return [
        ToyEdge(
            source_id="ENT_WORK_MEETING",
            target_id="ENT_STRESS",
            relation="CAUSES",
            weight=0.8,
            edge_type="CAUSES",
        ),
        ToyEdge(
            source_id="ENT_SOCCER",
            target_id="ENT_STRESS",
            relation="CAUSES",
            weight=0.7,
            edge_type="CAUSES",
        ),
        ToyEdge(
            source_id="ENT_STRESS",
            target_id="ENT_BUDGET",
            relation="CAUSES",
            weight=0.75,
            edge_type="CAUSES",
        ),
        ToyEdge(
            source_id="ENT_WORK_MEETING",
            target_id="ENT_SOCCER",
            relation="CAUSES",
            weight=0.9,
            edge_type="CAUSES",
        ),
    ]


def _create_actions(seed: int) -> List[ToyAction]:
    """Create actions for MCTS."""
    return [
        ToyAction("ACT001", "Take kids to park", 2.0, 0.9, 0.85),
        ToyAction("ACT002", "Go grocery shopping", 1.0, 0.3, 0.4),
        ToyAction("ACT003", "Family grocery trip", 1.5, 0.7, 0.65),
        ToyAction("ACT004", "Help with homework", 1.0, 0.8, 0.75),
        ToyAction("ACT005", "Exercise", 1.0, 0.5, 0.6),
        ToyAction("ACT006", "Family board game", 1.5, 0.85, 0.8),
    ]


def _create_goals(seed: int) -> List[ToyGoal]:
    """Create goals for MCTS."""
    return [
        ToyGoal("GOAL001", "Be more present with family", 0.9, 1.0),
        ToyGoal("GOAL002", "Help kids with school success", 0.8, 1.0),
        ToyGoal("GOAL003", "Improve work-life balance", 0.7, 1.0),
    ]


def _create_initial_state(seed: int) -> Dict[str, Any]:
    """Create initial state for MCTS."""
    return {
        "time_of_day": "morning",
        "day": "Saturday",
        "family_mood": "neutral",
        "pending_tasks": ["grocery shopping", "kids homework help", "exercise"],
    }


def _create_incomplete_episodes(seed: int) -> List[IncompleteEpisode]:
    """Create incomplete episodes for SPC-UQ."""
    base_time = int(datetime.now().timestamp() * 1000)
    return [
        IncompleteEpisode(
            episode_id="01INCOMPLETE00000000000001",
            summary="Something happened with Sarah in the morning... can't quite remember",
            timestamp=base_time,
        ),
    ]


def _create_fragments(seed: int, incomplete_id: str) -> List[ToyFragment]:
    """Create fragments for SPC-UQ."""
    base_time = int(datetime.now().timestamp() * 1000)
    return [
        ToyFragment(
            fragment_id="FRAG001",
            source_episode_id=incomplete_id,
            source_event_id="EVT001",
            start_time_ms=base_time - 3600000,
            end_time_ms=base_time - 3000000,
            content="making breakfast",
            attributes=(("activity", "cooking"), ("confidence", 0.8)),
        ),
        ToyFragment(
            fragment_id="FRAG002",
            source_episode_id=incomplete_id,
            source_event_id="EVT002",
            start_time_ms=base_time - 3000000,
            end_time_ms=base_time - 2400000,
            content="Sarah mentioned school",
            attributes=(("topic", "school"), ("confidence", 0.7)),
        ),
    ]


def _create_context(seed: int) -> Dict[str, Any]:
    """Create context for SPC-UQ."""
    return {
        "time_of_day": "morning",
        "day": "weekday",
        "nearby_locations": ["home_kitchen", "home_study", "school"],
        "known_locations": ["home_kitchen", "home_study", "school", "office"],
        "frequent_contacts": ["Sarah", "Tommy", "spouse"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Coverage thresholds for toy pack
# ─────────────────────────────────────────────────────────────────────────────

TOY_EXPECTED_PROPERTIES = {
    # CPN
    "cpn_min_counterfactuals": 5,
    "cpn_path_length_ge_1_ratio": 0.3,
    # MCTS
    "mcts_budget_consumption_ratio": 0.5,
    "mcts_max_visit_count": 3,
    # BGT-SM
    "bgt_insights_min": 1,
    "bgt_pmi_variance": True,
    # SPC-UQ
    "spc_reconstructions_min": 1,
    "spc_provenance_types_min": 1,
}


# ─────────────────────────────────────────────────────────────────────────────
# Main builder function
# ─────────────────────────────────────────────────────────────────────────────


def build_world(seed: int = 42, use_ultrabert: bool | None = None):
    """Build the toy world.

    Args:
        seed: Random seed for reproducibility.
        use_ultrabert: If True, use UltraBERT embeddings.
                       If False/None, use clustered embeddings.

    Returns:
        World instance with all toy data.
    """
    # Import here to avoid circular imports
    from ..r5_data_factory import World

    # Generate all components
    entities = _create_entities(seed)
    episodes = _create_episodes(seed)
    semantic_edges = _create_semantic_edges(seed)
    kg_edges = _create_kg_edges(seed)
    actions = _create_actions(seed)
    goals = _create_goals(seed)
    initial_state = _create_initial_state(seed)
    incomplete_episodes = _create_incomplete_episodes(seed)
    fragments = _create_fragments(seed, incomplete_episodes[0].episode_id)
    context = _create_context(seed)

    # Generate embeddings
    embedding_service = get_embedding_service(use_ultrabert)
    embeddings = embedding_service.embed_entities(entities)

    return World(
        pack_name="toy",
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
        incomplete_episodes=incomplete_episodes,
        fragments=fragments,
        schemas=None,  # No schemas for toy pack
        context=context,
        expected_properties=TOY_EXPECTED_PROPERTIES,
        difficulty="easy",
    )
