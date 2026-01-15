"""MCTS Delayed Reward pack - Focus on delayed reward discovery.

This pack tests MCTS's ability to find strategies where:
- Immediate reward is low/negative
- Delayed reward (after setup actions) is high
- Requires action sequencing: unlock -> execute -> reward
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..r5_embeddings import get_embedding_service

# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class DelayedEntity:
    """Entity for delayed reward scenarios."""

    entity_id: str
    name: str
    entity_type: str
    category: str
    _observation_count: int = 1

    @property
    def observation_count(self) -> int:
        return self._observation_count


@dataclass
class DelayedEdge:
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
class DelayedEpisode:
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
class DelayedGoal:
    """Goal with priority."""

    goal_id: str
    description: str
    priority: float
    target_value: float = 1.0


@dataclass
class DelayedAction:
    """Action with preconditions and unlock effects.

    Key features:
    - preconditions: List of state conditions that must be true
    - unlocks: Actions that become available after this one
    - effects: State changes after execution
    """

    action_id: str
    name: str
    duration_hours: float
    goal_alignment: float
    expected_reward: float
    preconditions: Optional[List[str]] = None
    unlocks: Optional[List[str]] = None
    effects: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.preconditions is None:
            self.preconditions = []
        if self.unlocks is None:
            self.unlocks = []
        if self.effects is None:
            self.effects = {}


# ─────────────────────────────────────────────────────────────────────────────
# Delayed Reward Scenario Design
# ─────────────────────────────────────────────────────────────────────────────
#
# Scenario: "Repair before reward"
#
# Current state: Spouse is frustrated, relationship_debt = 0.4
#
# Immediate reward actions (tempting but suboptimal):
#   - Watch TV (reward: 0.3) - easy escape
#   - Go for solo run (reward: 0.4) - self-care but avoids issue
#
# Setup actions (low/no immediate reward, unlocks better actions):
#   - Apologize to spouse (reward: 0.1) -> unlocks "Meaningful conversation"
#   - Meaningful conversation (reward: 0.2) -> sets spouse_mood = "receptive"
#   - When spouse_mood = receptive: Family activity (reward: 0.9)
#
# Optimal path: Apologize -> Conversation -> Family activity = 1.2 total
# Greedy path: Watch TV + Solo run = 0.7 total
#
# MCTS should discover the delayed reward path.


def _create_entities(seed: int) -> List[DelayedEntity]:
    """Create entities for the scenario."""
    return [
        DelayedEntity("ENT_SPOUSE", "Spouse", "person", "family", 50),
        DelayedEntity("ENT_KIDS", "Children", "person", "family", 45),
        DelayedEntity("ENT_TV", "Television", "object", "entertainment", 20),
        DelayedEntity("ENT_PARK", "Park", "location", "recreation", 15),
        DelayedEntity("ENT_KITCHEN", "Kitchen", "location", "home", 25),
        DelayedEntity("ENT_APOLOGY", "Apology", "action", "social", 10),
        DelayedEntity("ENT_CONVERSATION", "Deep Conversation", "action", "social", 12),
        DelayedEntity("ENT_FAMILY_TIME", "Quality Family Time", "event", "family", 30),
        DelayedEntity("ENT_RELATIONSHIP", "Relationship Health", "state", "family", 40),
        DelayedEntity("ENT_STRESS", "Stress Level", "state", "health", 35),
    ]


def _create_semantic_edges(seed: int) -> List[DelayedEdge]:
    """Create semantic edges."""
    return [
        DelayedEdge("ENT_APOLOGY", "ENT_CONVERSATION", "enables", 0.8),
        DelayedEdge("ENT_CONVERSATION", "ENT_FAMILY_TIME", "enables", 0.9),
        DelayedEdge("ENT_FAMILY_TIME", "ENT_RELATIONSHIP", "improves", 0.85),
        DelayedEdge("ENT_TV", "ENT_STRESS", "reduces", 0.3),
        DelayedEdge("ENT_PARK", "ENT_STRESS", "reduces", 0.5),
    ]


def _create_kg_edges(seed: int) -> List[DelayedEdge]:
    """Create causal edges."""
    return [
        DelayedEdge("ENT_STRESS", "ENT_RELATIONSHIP", "CAUSES", -0.5, "CAUSES"),
        DelayedEdge("ENT_APOLOGY", "ENT_RELATIONSHIP", "CAUSES", 0.3, "CAUSES"),
        DelayedEdge("ENT_CONVERSATION", "ENT_RELATIONSHIP", "CAUSES", 0.5, "CAUSES"),
        DelayedEdge("ENT_FAMILY_TIME", "ENT_RELATIONSHIP", "CAUSES", 0.8, "CAUSES"),
    ]


def _create_episodes(seed: int) -> List[DelayedEpisode]:
    """Create context episodes."""
    base_time = int(datetime.now().timestamp() * 1000)
    day_ms = 24 * 60 * 60 * 1000

    return [
        DelayedEpisode(
            episode_id="01DELAYED_001",
            summary="Had an argument with spouse yesterday. They're still upset.",
            timestamp=base_time - 1 * day_ms,
            emotional_valence=-0.6,
            participants=["self", "spouse"],
            location="home",
            activity_type="conflict",
            entity_ids=["ENT_SPOUSE", "ENT_STRESS", "ENT_RELATIONSHIP"],
        ),
        DelayedEpisode(
            episode_id="01DELAYED_002",
            summary="Kids have been asking for family time. Haven't done anything together lately.",
            timestamp=base_time - 3 * day_ms,
            emotional_valence=-0.3,
            participants=["self", "kids"],
            location="home",
            activity_type="reminder",
            entity_ids=["ENT_KIDS", "ENT_FAMILY_TIME"],
        ),
    ]


def _create_actions(seed: int) -> List[DelayedAction]:
    """Create actions with delayed reward structure.

    Key insight: The optimal path requires low-reward setup actions
    before high-reward payoff actions become available.
    """
    return [
        # Immediate reward actions (tempting but suboptimal)
        DelayedAction(
            action_id="ACT_WATCH_TV",
            name="Watch TV alone",
            duration_hours=2.0,
            goal_alignment=0.2,
            expected_reward=0.3,
            preconditions=[],
            unlocks=[],
            effects={"stress": -0.1},
        ),
        DelayedAction(
            action_id="ACT_SOLO_RUN",
            name="Go for a solo run",
            duration_hours=1.0,
            goal_alignment=0.4,
            expected_reward=0.4,
            preconditions=[],
            unlocks=[],
            effects={"stress": -0.2, "energy": 0.1},
        ),
        DelayedAction(
            action_id="ACT_BROWSE_PHONE",
            name="Browse phone",
            duration_hours=1.0,
            goal_alignment=0.1,
            expected_reward=0.2,
            preconditions=[],
            unlocks=[],
            effects={},
        ),
        # Setup actions (low immediate reward, unlock better actions)
        DelayedAction(
            action_id="ACT_APOLOGIZE",
            name="Apologize to spouse",
            duration_hours=0.5,
            goal_alignment=0.7,
            expected_reward=0.1,  # Low immediate reward
            preconditions=[],
            unlocks=["ACT_CONVERSATION"],  # Unlocks next step
            effects={"spouse_mood": "open"},
        ),
        DelayedAction(
            action_id="ACT_CONVERSATION",
            name="Have meaningful conversation",
            duration_hours=1.0,
            goal_alignment=0.8,
            expected_reward=0.2,  # Still low reward
            preconditions=["spouse_mood == open"],
            unlocks=["ACT_FAMILY_ACTIVITY"],  # Unlocks high-reward action
            effects={"spouse_mood": "receptive", "relationship_debt": -0.2},
        ),
        # High-reward payoff actions (require setup)
        DelayedAction(
            action_id="ACT_FAMILY_ACTIVITY",
            name="Family activity together",
            duration_hours=2.0,
            goal_alignment=0.95,
            expected_reward=0.9,  # HIGH reward after setup
            preconditions=["spouse_mood == receptive"],
            unlocks=[],
            effects={"relationship_debt": -0.3, "family_happiness": 0.4},
        ),
        DelayedAction(
            action_id="ACT_FAMILY_DINNER",
            name="Cook and enjoy family dinner",
            duration_hours=2.5,
            goal_alignment=0.9,
            expected_reward=0.8,  # HIGH reward after setup
            preconditions=["spouse_mood == receptive"],
            unlocks=[],
            effects={"relationship_debt": -0.2, "family_happiness": 0.3},
        ),
        # Alternative delayed path
        DelayedAction(
            action_id="ACT_HELP_CHORES",
            name="Help with household chores",
            duration_hours=1.5,
            goal_alignment=0.6,
            expected_reward=0.15,  # Low immediate
            preconditions=[],
            unlocks=["ACT_THANK_YOU"],
            effects={"spouse_appreciation": 0.2},
        ),
        DelayedAction(
            action_id="ACT_THANK_YOU",
            name="Receive spouse's thanks",
            duration_hours=0.1,
            goal_alignment=0.5,
            expected_reward=0.3,
            preconditions=["spouse_appreciation >= 0.2"],
            unlocks=["ACT_CONVERSATION"],
            effects={"spouse_mood": "open"},
        ),
    ]


def _create_goals(seed: int) -> List[DelayedGoal]:
    """Create goals emphasizing family and relationship."""
    return [
        DelayedGoal("GOAL001", "Repair relationship with spouse", 0.95, 1.0),
        DelayedGoal("GOAL002", "Spend quality time with family", 0.9, 1.0),
        DelayedGoal("GOAL003", "Reduce personal stress", 0.6, 1.0),
    ]


def _create_initial_state(seed: int) -> Dict[str, Any]:
    """Create initial state with relationship debt."""
    return {
        "time_of_day": "afternoon",
        "day": "Saturday",
        "time_remaining_hours": 6.0,
        "energy": 0.7,
        "stress": 0.5,
        "family_mood": "neutral",
        "spouse_mood": "frustrated",  # Key: requires repair first
        "relationship_debt": 0.4,  # Accumulated from past conflicts
        "spouse_appreciation": 0.0,
        "family_happiness": 0.3,
        "pending_tasks": ["apologize", "family_time"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Coverage thresholds for mcts_delayed pack
# ─────────────────────────────────────────────────────────────────────────────

MCTS_DELAYED_EXPECTED_PROPERTIES = {
    # CPN (secondary)
    "cpn_min_counterfactuals": 5,
    "cpn_path_length_ge_1_ratio": 0.2,
    # MCTS - primary focus
    "mcts_budget_consumption_ratio": 0.8,
    "mcts_max_visit_count": 15,
    "mcts_visit_variance": True,
    "mcts_finds_delayed_reward": True,  # Must find apologize -> conversation -> activity
    "mcts_reward_spread": 0.4,
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
    """Build the mcts_delayed world.

    Args:
        seed: Random seed for reproducibility.
        use_ultrabert: If True, use UltraBERT embeddings.

    Returns:
        World instance testing delayed reward discovery.
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
        pack_name="mcts_delayed",
        seed=seed,
        episodes=episodes,
        kg_edges=kg_edges,
        entities=entities,
        semantic_edges=semantic_edges,
        embeddings=embeddings,
        initial_state=initial_state,
        actions=actions,
        goals=goals,
        constraints={
            "time_budget_hours": 6.0,
            "min_energy": 0.2,
        },
        incomplete_episodes=None,
        fragments=None,
        schemas=None,
        context=None,
        expected_properties=MCTS_DELAYED_EXPECTED_PROPERTIES,
        difficulty="medium",
    )
