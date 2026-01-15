"""Causal Deep pack - CPN focus with deep causal chains.

This pack tests CPN's ability to trace causal paths of depth 3+.
Includes linear chains (depth 4-5), fork patterns, and join patterns.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List

from ..r5_embeddings import get_embedding_service

# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class CausalEpisode:
    """Episode object with deep causal context."""

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
class CausalEntity:
    """Entity in the causal chain."""

    entity_id: str
    name: str
    entity_type: str
    category: str
    _observation_count: int = 1

    @property
    def observation_count(self) -> int:
        return self._observation_count


@dataclass
class CausalEdge:
    """Causal edge with weight."""

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
class CausalGoal:
    """Goal for MCTS."""

    goal_id: str
    description: str
    priority: float
    target_value: float = 1.0


@dataclass
class CausalAction:
    """Action for MCTS."""

    action_id: str
    name: str
    duration_hours: float
    goal_alignment: float
    expected_reward: float


# ─────────────────────────────────────────────────────────────────────────────
# Entity definitions - Deep causal chains
# ─────────────────────────────────────────────────────────────────────────────

# Chain 1: Work stress cascade (depth 5)
# WORK_OVERLOAD -> MISSED_DEADLINE -> BOSS_DISAPPOINTED -> PERFORMANCE_REVIEW -> STRESS -> FAMILY_ARGUMENT

# Chain 2: Health cascade (depth 4)
# SKIPPED_LUNCH -> FATIGUE -> POOR_FOCUS -> WORK_ERRORS -> FRUSTRATION

# Fork: WORK_OVERLOAD branches to both chains
# Join: STRESS + FRUSTRATION -> GUILT


def _create_entities(seed: int) -> List[CausalEntity]:
    """Create entities for deep causal chains."""
    return [
        # Chain 1: Work stress cascade
        CausalEntity("ENT_WORK_OVERLOAD", "Work Overload", "event", "work", 30),
        CausalEntity("ENT_MISSED_DEADLINE", "Missed Deadline", "event", "work", 15),
        CausalEntity("ENT_BOSS_DISAPPOINTED", "Boss Disappointed", "emotion", "work", 10),
        CausalEntity("ENT_PERFORMANCE_REVIEW", "Performance Review", "event", "work", 5),
        CausalEntity("ENT_STRESS", "Stress", "emotion", "health", 40),
        CausalEntity("ENT_FAMILY_ARGUMENT", "Family Argument", "event", "family", 20),
        # Chain 2: Health cascade
        CausalEntity("ENT_SKIPPED_LUNCH", "Skipped Lunch", "event", "health", 25),
        CausalEntity("ENT_FATIGUE", "Fatigue", "state", "health", 35),
        CausalEntity("ENT_POOR_FOCUS", "Poor Focus", "state", "work", 20),
        CausalEntity("ENT_WORK_ERRORS", "Work Errors", "event", "work", 12),
        CausalEntity("ENT_FRUSTRATION", "Frustration", "emotion", "health", 30),
        # Join result
        CausalEntity("ENT_GUILT", "Guilt", "emotion", "health", 15),
        CausalEntity("ENT_APOLOGY", "Apology", "action", "family", 8),
        CausalEntity("ENT_REPAIR_TALK", "Repair Talk", "action", "family", 5),
        CausalEntity("ENT_QUALITY_TIME", "Quality Time", "action", "family", 25),
        # Parallel branch: External stressors
        CausalEntity("ENT_LATE_ARRIVAL", "Late Arrival", "event", "work", 10),
        CausalEntity("ENT_MISSED_EVENT", "Missed Event", "event", "family", 7),
        CausalEntity("ENT_CHILD_SAD", "Child Sad", "emotion", "family", 12),
        # Recovery path
        CausalEntity("ENT_EXERCISE", "Exercise", "action", "health", 20),
        CausalEntity("ENT_RELAXATION", "Relaxation", "state", "health", 15),
    ]


def _create_kg_edges(seed: int) -> List[CausalEdge]:
    """Create deep causal chains (CAUSES edges)."""
    return [
        # Chain 1: Work stress cascade (depth 5)
        CausalEdge("ENT_WORK_OVERLOAD", "ENT_MISSED_DEADLINE", "CAUSES", 0.9),
        CausalEdge("ENT_MISSED_DEADLINE", "ENT_BOSS_DISAPPOINTED", "CAUSES", 0.85),
        CausalEdge("ENT_BOSS_DISAPPOINTED", "ENT_PERFORMANCE_REVIEW", "CAUSES", 0.7),
        CausalEdge("ENT_PERFORMANCE_REVIEW", "ENT_STRESS", "CAUSES", 0.8),
        CausalEdge("ENT_STRESS", "ENT_FAMILY_ARGUMENT", "CAUSES", 0.75),
        # Chain 2: Health cascade (depth 4)
        CausalEdge("ENT_WORK_OVERLOAD", "ENT_SKIPPED_LUNCH", "CAUSES", 0.7),
        CausalEdge("ENT_SKIPPED_LUNCH", "ENT_FATIGUE", "CAUSES", 0.85),
        CausalEdge("ENT_FATIGUE", "ENT_POOR_FOCUS", "CAUSES", 0.8),
        CausalEdge("ENT_POOR_FOCUS", "ENT_WORK_ERRORS", "CAUSES", 0.75),
        CausalEdge("ENT_WORK_ERRORS", "ENT_FRUSTRATION", "CAUSES", 0.8),
        # Join pattern: Two causes -> one effect
        CausalEdge("ENT_STRESS", "ENT_GUILT", "CAUSES", 0.6),
        CausalEdge("ENT_FRUSTRATION", "ENT_GUILT", "CAUSES", 0.65),
        CausalEdge("ENT_FAMILY_ARGUMENT", "ENT_GUILT", "CAUSES", 0.7),
        # Recovery path
        CausalEdge("ENT_GUILT", "ENT_APOLOGY", "CAUSES", 0.8),
        CausalEdge("ENT_APOLOGY", "ENT_REPAIR_TALK", "CAUSES", 0.75),
        CausalEdge("ENT_REPAIR_TALK", "ENT_QUALITY_TIME", "CAUSES", 0.7),
        # Parallel branch
        CausalEdge("ENT_WORK_OVERLOAD", "ENT_LATE_ARRIVAL", "CAUSES", 0.5),
        CausalEdge("ENT_LATE_ARRIVAL", "ENT_MISSED_EVENT", "CAUSES", 0.6),
        CausalEdge("ENT_MISSED_EVENT", "ENT_CHILD_SAD", "CAUSES", 0.8),
        CausalEdge("ENT_CHILD_SAD", "ENT_GUILT", "CAUSES", 0.7),
        # Cross-chain connections
        CausalEdge("ENT_FATIGUE", "ENT_STRESS", "CAUSES", 0.5),
        CausalEdge("ENT_FRUSTRATION", "ENT_FAMILY_ARGUMENT", "CAUSES", 0.55),
        # Counter-path (positive recovery)
        CausalEdge("ENT_STRESS", "ENT_EXERCISE", "CAUSES", 0.4),
        CausalEdge("ENT_EXERCISE", "ENT_RELAXATION", "CAUSES", 0.8),
    ]


def _create_semantic_edges(seed: int) -> List[CausalEdge]:
    """Create semantic edges for BGT-SM (non-causal associations)."""
    return [
        CausalEdge("ENT_WORK_OVERLOAD", "ENT_STRESS", "correlates_with", 0.7, "SEMANTIC"),
        CausalEdge("ENT_STRESS", "ENT_FATIGUE", "correlates_with", 0.6, "SEMANTIC"),
        CausalEdge("ENT_FAMILY_ARGUMENT", "ENT_GUILT", "leads_to", 0.5, "SEMANTIC"),
        CausalEdge("ENT_APOLOGY", "ENT_QUALITY_TIME", "enables", 0.6, "SEMANTIC"),
        CausalEdge("ENT_EXERCISE", "ENT_RELAXATION", "produces", 0.7, "SEMANTIC"),
    ]


def _create_episodes(seed: int) -> List[CausalEpisode]:
    """Create episodes with deep causal implications."""
    base_time = int(datetime.now().timestamp() * 1000)
    day_ms = 24 * 60 * 60 * 1000

    return [
        # Regret episodes (negative valence) with deep causal chains
        CausalEpisode(
            episode_id="01CAUSAL_DEEP_001",
            summary="Took on too many projects at work. Ended up working through lunch and missing a key deadline.",
            timestamp=base_time - 10 * day_ms,
            emotional_valence=-0.8,
            participants=["self"],
            location="office",
            activity_type="work_overload",
            entity_ids=["ENT_WORK_OVERLOAD", "ENT_MISSED_DEADLINE", "ENT_SKIPPED_LUNCH"],
        ),
        CausalEpisode(
            episode_id="01CAUSAL_DEEP_002",
            summary="Boss expressed disappointment about missed deadline. Mentioned upcoming performance review.",
            timestamp=base_time - 9 * day_ms,
            emotional_valence=-0.75,
            participants=["self", "boss"],
            location="office",
            activity_type="work_conflict",
            entity_ids=["ENT_BOSS_DISAPPOINTED", "ENT_PERFORMANCE_REVIEW"],
        ),
        CausalEpisode(
            episode_id="01CAUSAL_DEEP_003",
            summary="Felt exhausted and unfocused all day. Made several errors in the report.",
            timestamp=base_time - 8 * day_ms,
            emotional_valence=-0.6,
            participants=["self"],
            location="office",
            activity_type="work_struggle",
            entity_ids=["ENT_FATIGUE", "ENT_POOR_FOCUS", "ENT_WORK_ERRORS"],
        ),
        CausalEpisode(
            episode_id="01CAUSAL_DEEP_004",
            summary="Came home stressed and snapped at spouse over small things. Kids saw the argument.",
            timestamp=base_time - 7 * day_ms,
            emotional_valence=-0.85,
            participants=["self", "spouse", "kids"],
            location="home",
            activity_type="family_conflict",
            entity_ids=["ENT_STRESS", "ENT_FRUSTRATION", "ENT_FAMILY_ARGUMENT"],
        ),
        CausalEpisode(
            episode_id="01CAUSAL_DEEP_005",
            summary="Missed Tommy's school play because I was late leaving the office. He was sad.",
            timestamp=base_time - 6 * day_ms,
            emotional_valence=-0.9,
            participants=["self", "Tommy"],
            location="school",
            activity_type="missed_event",
            entity_ids=["ENT_LATE_ARRIVAL", "ENT_MISSED_EVENT", "ENT_CHILD_SAD"],
        ),
        CausalEpisode(
            episode_id="01CAUSAL_DEEP_006",
            summary="Feeling overwhelmed by guilt. Everything seems connected to that overload decision.",
            timestamp=base_time - 5 * day_ms,
            emotional_valence=-0.7,
            participants=["self"],
            location="home",
            activity_type="reflection",
            entity_ids=["ENT_GUILT", "ENT_STRESS"],
        ),
        # Positive/recovery episodes
        CausalEpisode(
            episode_id="01CAUSAL_DEEP_007",
            summary="Apologized to spouse and kids. Had a good conversation about boundaries.",
            timestamp=base_time - 4 * day_ms,
            emotional_valence=0.6,
            participants=["self", "spouse", "kids"],
            location="home",
            activity_type="repair",
            entity_ids=["ENT_APOLOGY", "ENT_REPAIR_TALK"],
        ),
        CausalEpisode(
            episode_id="01CAUSAL_DEEP_008",
            summary="Went for a long run to clear my head. Felt much better afterward.",
            timestamp=base_time - 3 * day_ms,
            emotional_valence=0.7,
            participants=["self"],
            location="park",
            activity_type="self_care",
            entity_ids=["ENT_EXERCISE", "ENT_RELAXATION"],
        ),
    ]


def _create_actions(seed: int) -> List[CausalAction]:
    """Create actions for MCTS."""
    return [
        CausalAction("ACT001", "Apologize to family", 0.5, 0.9, 0.7),
        CausalAction("ACT002", "Take a mental health day", 8.0, 0.8, 0.6),
        CausalAction("ACT003", "Exercise", 1.0, 0.7, 0.65),
        CausalAction("ACT004", "Have repair conversation", 1.5, 0.85, 0.75),
        CausalAction("ACT005", "Plan quality time with kids", 2.0, 0.9, 0.8),
        CausalAction("ACT006", "Talk to boss about workload", 0.5, 0.6, 0.5),
    ]


def _create_goals(seed: int) -> List[CausalGoal]:
    """Create goals for MCTS."""
    return [
        CausalGoal("GOAL001", "Repair family relationships", 0.95, 1.0),
        CausalGoal("GOAL002", "Reduce stress levels", 0.85, 1.0),
        CausalGoal("GOAL003", "Prevent future burnout", 0.8, 1.0),
    ]


def _create_initial_state(seed: int) -> Dict[str, Any]:
    """Create initial state for MCTS."""
    return {
        "time_of_day": "evening",
        "day": "Friday",
        "stress_level": "high",
        "family_mood": "strained",
        "relationship_debt": 0.6,
        "pending_apologies": ["spouse", "Tommy"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Coverage thresholds for causal_deep pack
# ─────────────────────────────────────────────────────────────────────────────

CAUSAL_DEEP_EXPECTED_PROPERTIES = {
    # CPN - primary focus
    "cpn_min_counterfactuals": 15,
    "cpn_path_length_ge_2_ratio": 0.5,
    "cpn_path_length_ge_3_count": 3,
    "cpn_max_path_length": 4,
    "cpn_plausibility_variance": 0.01,
    "cpn_scenario_type_count": 3,
    # MCTS
    "mcts_budget_consumption_ratio": 0.6,
    "mcts_max_visit_count": 5,
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
    """Build the causal_deep world.

    Args:
        seed: Random seed for reproducibility.
        use_ultrabert: If True, use UltraBERT embeddings.

    Returns:
        World instance with deep causal chain data.
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
        pack_name="causal_deep",
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
        expected_properties=CAUSAL_DEEP_EXPECTED_PROPERTIES,
        difficulty="medium",
    )
