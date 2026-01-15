"""MCTS Constrained pack - Focus on time/resource budget handling.

This pack tests MCTS's ability to:
- Respect time budget constraints
- Handle resource limits (energy, money)
- Make trade-offs between reward and feasibility
- Find solutions within hard constraints
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..r5_embeddings import get_embedding_service


@dataclass
class ConstrainedEntity:
    """Entity for constrained scenarios."""

    entity_id: str
    name: str
    entity_type: str
    category: str
    _observation_count: int = 1

    @property
    def observation_count(self) -> int:
        return self._observation_count


@dataclass
class ConstrainedEdge:
    """Edge in the scenario."""

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
class ConstrainedEpisode:
    """Episode for context."""

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
        return 0.8

    @property
    def start_time_ms(self) -> int:
        return self.timestamp


@dataclass
class ConstrainedGoal:
    """Goal with priority."""

    goal_id: str
    description: str
    priority: float
    target_value: float = 1.0


@dataclass
class ConstrainedAction:
    """Action with resource costs and constraints.

    Key features:
    - duration_hours: Time cost
    - energy_cost: Energy depletion
    - money_cost: Optional monetary cost
    - min_energy: Minimum energy required
    - time_window: Optional time restriction
    """

    action_id: str
    name: str
    duration_hours: float
    goal_alignment: float
    expected_reward: float
    energy_cost: float = 0.1
    money_cost: float = 0.0
    min_energy: float = 0.0
    time_window: Optional[tuple] = None  # (start_hour, end_hour)
    location_required: Optional[str] = None


def _create_entities(seed: int) -> List[ConstrainedEntity]:
    """Create entities for the scenario."""
    return [
        ConstrainedEntity("ENT_HOME", "Home", "location", "home", 50),
        ConstrainedEntity("ENT_PARK", "Park", "location", "recreation", 20),
        ConstrainedEntity("ENT_MALL", "Shopping Mall", "location", "commercial", 15),
        ConstrainedEntity("ENT_RESTAURANT", "Restaurant", "location", "dining", 25),
        ConstrainedEntity("ENT_GYM", "Gym", "location", "health", 18),
        ConstrainedEntity("ENT_KIDS", "Children", "person", "family", 45),
        ConstrainedEntity("ENT_SPOUSE", "Spouse", "person", "family", 50),
        ConstrainedEntity("ENT_ENERGY", "Energy Level", "state", "health", 30),
        ConstrainedEntity("ENT_BUDGET", "Budget", "resource", "finance", 20),
        ConstrainedEntity("ENT_TIME", "Available Time", "resource", "planning", 40),
    ]


def _create_semantic_edges(seed: int) -> List[ConstrainedEdge]:
    """Create semantic edges."""
    return [
        ConstrainedEdge("ENT_GYM", "ENT_ENERGY", "restores", 0.6),
        ConstrainedEdge("ENT_RESTAURANT", "ENT_BUDGET", "depletes", -0.4),
        ConstrainedEdge("ENT_PARK", "ENT_KIDS", "entertains", 0.8),
        ConstrainedEdge("ENT_MALL", "ENT_TIME", "consumes", -0.5),
    ]


def _create_kg_edges(seed: int) -> List[ConstrainedEdge]:
    """Create causal edges."""
    return [
        ConstrainedEdge("ENT_ENERGY", "ENT_GYM", "CAUSES", 0.5, "CAUSES"),
        ConstrainedEdge("ENT_TIME", "ENT_PARK", "CAUSES", 0.6, "CAUSES"),
    ]


def _create_episodes(seed: int) -> List[ConstrainedEpisode]:
    """Create context episodes."""
    base_time = int(datetime.now().timestamp() * 1000)
    day_ms = 24 * 60 * 60 * 1000

    return [
        ConstrainedEpisode(
            episode_id="01CONSTRAINED_001",
            summary="Saturday morning with limited time before evening event.",
            timestamp=base_time,
            emotional_valence=0.5,
            participants=["self", "spouse", "kids"],
            location="home",
            activity_type="planning",
            entity_ids=["ENT_HOME", "ENT_TIME", "ENT_BUDGET"],
        ),
    ]


def _create_actions(seed: int) -> List[ConstrainedAction]:
    """Create actions with various constraints.

    Scenario: Saturday 10am-5pm (7 hours), energy=0.7, budget=$100
    Must pick activities that fit within constraints.
    """
    return [
        # High-reward but expensive/time-consuming
        ConstrainedAction(
            action_id="ACT_AMUSEMENT_PARK",
            name="Go to amusement park",
            duration_hours=5.0,
            goal_alignment=0.95,
            expected_reward=0.9,
            energy_cost=0.4,
            money_cost=80.0,  # Expensive!
            min_energy=0.3,
        ),
        ConstrainedAction(
            action_id="ACT_FANCY_DINNER",
            name="Fancy restaurant dinner",
            duration_hours=2.5,
            goal_alignment=0.85,
            expected_reward=0.8,
            energy_cost=0.1,
            money_cost=60.0,
            min_energy=0.2,
            time_window=(17, 21),  # Dinner time only
        ),

        # Medium reward, moderate resources
        ConstrainedAction(
            action_id="ACT_PARK_PICNIC",
            name="Picnic in the park",
            duration_hours=2.0,
            goal_alignment=0.8,
            expected_reward=0.7,
            energy_cost=0.2,
            money_cost=15.0,
            min_energy=0.2,
        ),
        ConstrainedAction(
            action_id="ACT_MOVIE",
            name="Go to movies",
            duration_hours=3.0,
            goal_alignment=0.7,
            expected_reward=0.65,
            energy_cost=0.1,
            money_cost=40.0,
            min_energy=0.1,
        ),
        ConstrainedAction(
            action_id="ACT_GYM",
            name="Family gym session",
            duration_hours=1.5,
            goal_alignment=0.6,
            expected_reward=0.5,
            energy_cost=0.25,
            money_cost=0.0,  # Free membership
            min_energy=0.4,  # Requires good energy
        ),

        # Low cost but lower reward
        ConstrainedAction(
            action_id="ACT_BOARD_GAMES",
            name="Play board games at home",
            duration_hours=2.0,
            goal_alignment=0.75,
            expected_reward=0.6,
            energy_cost=0.05,
            money_cost=0.0,
            min_energy=0.1,
            location_required="home",
        ),
        ConstrainedAction(
            action_id="ACT_BACKYARD_PLAY",
            name="Backyard activities",
            duration_hours=1.5,
            goal_alignment=0.7,
            expected_reward=0.55,
            energy_cost=0.15,
            money_cost=0.0,
            min_energy=0.2,
            location_required="home",
        ),
        ConstrainedAction(
            action_id="ACT_NAP",
            name="Take a nap",
            duration_hours=1.0,
            goal_alignment=0.3,
            expected_reward=0.2,
            energy_cost=-0.3,  # Restores energy!
            money_cost=0.0,
            min_energy=0.0,
        ),

        # Quick activities
        ConstrainedAction(
            action_id="ACT_ICE_CREAM",
            name="Get ice cream",
            duration_hours=0.5,
            goal_alignment=0.5,
            expected_reward=0.4,
            energy_cost=0.05,
            money_cost=10.0,
            min_energy=0.1,
        ),
        ConstrainedAction(
            action_id="ACT_LIBRARY",
            name="Visit library",
            duration_hours=1.0,
            goal_alignment=0.6,
            expected_reward=0.45,
            energy_cost=0.1,
            money_cost=0.0,
            min_energy=0.1,
        ),
    ]


def _create_goals(seed: int) -> List[ConstrainedGoal]:
    """Create goals."""
    return [
        ConstrainedGoal("GOAL001", "Maximize family fun", 0.9, 1.0),
        ConstrainedGoal("GOAL002", "Stay within budget", 0.8, 1.0),
        ConstrainedGoal("GOAL003", "Not exhaust everyone", 0.7, 1.0),
    ]


def _create_initial_state(seed: int) -> Dict[str, Any]:
    """Create initial state with resource constraints."""
    return {
        "current_hour": 10,  # 10 AM
        "end_hour": 17,  # 5 PM (evening event)
        "time_remaining_hours": 7.0,
        "energy": 0.7,
        "budget_remaining": 100.0,
        "location": "home",
        "family_mood": "excited",
        "activities_done": [],
    }


def _create_constraints(seed: int) -> Dict[str, Any]:
    """Create hard constraints for the planning problem."""
    return {
        "time_budget_hours": 7.0,
        "money_budget": 100.0,
        "min_final_energy": 0.2,  # Can't exhaust completely
        "must_be_home_by": 17,
        "max_travel_transitions": 3,  # Can't jump around too much
    }


MCTS_CONSTRAINED_EXPECTED_PROPERTIES = {
    # CPN (secondary)
    "cpn_min_counterfactuals": 3,
    "cpn_path_length_ge_1_ratio": 0.1,
    # MCTS - primary focus
    "mcts_budget_consumption_ratio": 0.9,
    "mcts_max_visit_count": 20,
    "mcts_visit_variance": True,
    "mcts_respects_constraints": True,
    "mcts_reward_spread": 0.5,
    # BGT-SM
    "bgt_insights_min": 1,
    "bgt_pmi_variance": True,
    # SPC-UQ
    "spc_reconstructions_min": 1,
    "spc_provenance_types_min": 1,
}


def build_world(seed: int = 42, use_ultrabert: bool | None = None):
    """Build the mcts_constrained world.

    Args:
        seed: Random seed for reproducibility.
        use_ultrabert: If True, use UltraBERT embeddings.

    Returns:
        World instance testing constraint handling.
    """
    from ..r5_data_factory import World

    entities = _create_entities(seed)
    episodes = _create_episodes(seed)
    semantic_edges = _create_semantic_edges(seed)
    kg_edges = _create_kg_edges(seed)
    actions = _create_actions(seed)
    goals = _create_goals(seed)
    initial_state = _create_initial_state(seed)
    constraints = _create_constraints(seed)

    embedding_service = get_embedding_service(use_ultrabert)
    embeddings = embedding_service.embed_entities(entities)

    return World(
        pack_name="mcts_constrained",
        seed=seed,
        episodes=episodes,
        kg_edges=kg_edges,
        entities=entities,
        semantic_edges=semantic_edges,
        embeddings=embeddings,
        initial_state=initial_state,
        actions=actions,
        goals=goals,
        constraints=constraints,
        incomplete_episodes=None,
        fragments=None,
        schemas=None,
        context=None,
        expected_properties=MCTS_CONSTRAINED_EXPECTED_PROPERTIES,
        difficulty="hard",
    )
