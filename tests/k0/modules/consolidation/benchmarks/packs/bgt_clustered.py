"""BGT Clustered pack - Focus on cross-cluster insight discovery.

This pack tests BGT-SM's ability to:
- Identify distinct semantic clusters
- Find surprising cross-cluster connections
- Use PMI to filter trivial same-cluster associations
- Generate meaningful bisociative insights
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List

from ..r5_embeddings import get_embedding_service


@dataclass
class ClusteredEntity:
    """Entity with explicit cluster membership."""

    entity_id: str
    name: str
    entity_type: str
    category: str  # This defines the cluster!
    _observation_count: int = 1

    @property
    def observation_count(self) -> int:
        return self._observation_count


@dataclass
class ClusteredEdge:
    """Edge with cross-cluster indicator."""

    source_id: str
    target_id: str
    relation: str
    weight: float
    edge_type: str = "SEMANTIC"
    is_bridge: bool = False  # True if cross-cluster
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
class ClusteredEpisode:
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
class ClusteredGoal:
    """Goal for MCTS."""

    goal_id: str
    description: str
    priority: float
    target_value: float = 1.0


@dataclass
class ClusteredAction:
    """Action for MCTS."""

    action_id: str
    name: str
    duration_hours: float
    goal_alignment: float
    expected_reward: float


# ─────────────────────────────────────────────────────────────────────────────
# Cluster Design: 6 well-separated semantic clusters
# ─────────────────────────────────────────────────────────────────────────────
#
# Cluster 1: FAMILY (people, relationships)
# Cluster 2: EDUCATION (learning, school, knowledge)
# Cluster 3: WORK (career, professional)
# Cluster 4: ENTERTAINMENT (fun, leisure)
# Cluster 5: FINANCE (money, budgets)
# Cluster 6: HEALTH (wellness, exercise)
#
# Bridge edges (rare, high PMI):
# - homework <-> stress (education-health)
# - deadline <-> family_argument (work-family)
# - budget <-> vacation (finance-entertainment)
# - exercise <-> family_mood (health-family)


def _create_entities(seed: int) -> List[ClusteredEntity]:
    """Create entities organized into 6 clusters."""
    entities = []

    # Cluster 1: FAMILY (8 entities)
    family_entities = [
        ("ENT_SARAH", "Sarah", "person"),
        ("ENT_TOMMY", "Tommy", "person"),
        ("ENT_SPOUSE", "Spouse", "person"),
        ("ENT_GRANDMA", "Grandma", "person"),
        ("ENT_UNCLE", "Uncle Bob", "person"),
        ("ENT_FAMILY_DINNER", "Family Dinner", "event"),
        ("ENT_FAMILY_VACATION", "Family Vacation", "event"),
        ("ENT_FAMILY_MOOD", "Family Mood", "state"),
    ]
    for eid, name, etype in family_entities:
        entities.append(ClusteredEntity(eid, name, etype, "family", 20 + hash(eid) % 30))

    # Cluster 2: EDUCATION (8 entities)
    education_entities = [
        ("ENT_HOMEWORK", "Homework", "activity"),
        ("ENT_SCHOOL", "School", "location"),
        ("ENT_FRACTIONS", "Fractions", "topic"),
        ("ENT_TEACHER", "Teacher", "person"),
        ("ENT_GRADES", "Grades", "metric"),
        ("ENT_SCIENCE_PROJECT", "Science Project", "activity"),
        ("ENT_READING", "Reading", "activity"),
        ("ENT_TUTORING", "Tutoring", "service"),
    ]
    for eid, name, etype in education_entities:
        entities.append(ClusteredEntity(eid, name, etype, "education", 10 + hash(eid) % 20))

    # Cluster 3: WORK (8 entities)
    work_entities = [
        ("ENT_MEETING", "Meeting", "event"),
        ("ENT_BOSS", "Boss", "person"),
        ("ENT_DEADLINE", "Deadline", "event"),
        ("ENT_PROJECT", "Project", "activity"),
        ("ENT_EMAIL", "Email", "communication"),
        ("ENT_PROMOTION", "Promotion", "goal"),
        ("ENT_COWORKER", "Coworker", "person"),
        ("ENT_OFFICE", "Office", "location"),
    ]
    for eid, name, etype in work_entities:
        entities.append(ClusteredEntity(eid, name, etype, "work", 15 + hash(eid) % 25))

    # Cluster 4: ENTERTAINMENT (8 entities)
    entertainment_entities = [
        ("ENT_MOVIE", "Movie", "activity"),
        ("ENT_GAME", "Video Game", "activity"),
        ("ENT_PARK", "Park", "location"),
        ("ENT_BIRTHDAY", "Birthday Party", "event"),
        ("ENT_VACATION", "Vacation", "event"),
        ("ENT_STREAMING", "Streaming", "service"),
        ("ENT_CONCERT", "Concert", "event"),
        ("ENT_RESTAURANT", "Restaurant", "location"),
    ]
    for eid, name, etype in entertainment_entities:
        entities.append(ClusteredEntity(eid, name, etype, "entertainment", 12 + hash(eid) % 18))

    # Cluster 5: FINANCE (8 entities)
    finance_entities = [
        ("ENT_BUDGET", "Budget", "resource"),
        ("ENT_SAVINGS", "Savings", "resource"),
        ("ENT_BILLS", "Bills", "obligation"),
        ("ENT_GROCERY", "Grocery Shopping", "expense"),
        ("ENT_EXPENSES", "Expenses", "tracking"),
        ("ENT_INCOME", "Income", "resource"),
        ("ENT_INVESTMENT", "Investment", "asset"),
        ("ENT_DEBT", "Debt", "liability"),
    ]
    for eid, name, etype in finance_entities:
        entities.append(ClusteredEntity(eid, name, etype, "finance", 8 + hash(eid) % 15))

    # Cluster 6: HEALTH (8 entities)
    health_entities = [
        ("ENT_EXERCISE", "Exercise", "activity"),
        ("ENT_SLEEP", "Sleep", "state"),
        ("ENT_STRESS", "Stress", "state"),
        ("ENT_DOCTOR", "Doctor", "person"),
        ("ENT_MEDICINE", "Medicine", "treatment"),
        ("ENT_NUTRITION", "Nutrition", "practice"),
        ("ENT_MEDITATION", "Meditation", "practice"),
        ("ENT_ENERGY", "Energy Level", "state"),
    ]
    for eid, name, etype in health_entities:
        entities.append(ClusteredEntity(eid, name, etype, "health", 18 + hash(eid) % 22))

    return entities


def _create_semantic_edges(seed: int) -> List[ClusteredEdge]:
    """Create edges with within-cluster and bridge connections."""
    edges = []

    # Within-cluster edges (expected, low PMI)
    # Family cluster
    edges.append(ClusteredEdge("ENT_SARAH", "ENT_TOMMY", "sibling_of", 0.9))
    edges.append(ClusteredEdge("ENT_SPOUSE", "ENT_FAMILY_DINNER", "organizes", 0.8))
    edges.append(ClusteredEdge("ENT_GRANDMA", "ENT_FAMILY_VACATION", "attends", 0.7))
    edges.append(ClusteredEdge("ENT_SARAH", "ENT_FAMILY_MOOD", "affects", 0.6))

    # Education cluster
    edges.append(ClusteredEdge("ENT_HOMEWORK", "ENT_SCHOOL", "assigned_by", 0.9))
    edges.append(ClusteredEdge("ENT_TEACHER", "ENT_GRADES", "assigns", 0.85))
    edges.append(ClusteredEdge("ENT_FRACTIONS", "ENT_HOMEWORK", "part_of", 0.8))
    edges.append(ClusteredEdge("ENT_TUTORING", "ENT_SCIENCE_PROJECT", "helps_with", 0.7))

    # Work cluster
    edges.append(ClusteredEdge("ENT_BOSS", "ENT_MEETING", "schedules", 0.9))
    edges.append(ClusteredEdge("ENT_DEADLINE", "ENT_PROJECT", "constrains", 0.85))
    edges.append(ClusteredEdge("ENT_COWORKER", "ENT_EMAIL", "sends", 0.7))
    edges.append(ClusteredEdge("ENT_PROMOTION", "ENT_BOSS", "decided_by", 0.75))

    # Entertainment cluster
    edges.append(ClusteredEdge("ENT_MOVIE", "ENT_STREAMING", "available_on", 0.85))
    edges.append(ClusteredEdge("ENT_BIRTHDAY", "ENT_RESTAURANT", "celebrated_at", 0.8))
    edges.append(ClusteredEdge("ENT_PARK", "ENT_VACATION", "destination_of", 0.7))

    # Finance cluster
    edges.append(ClusteredEdge("ENT_INCOME", "ENT_BUDGET", "funds", 0.9))
    edges.append(ClusteredEdge("ENT_BILLS", "ENT_EXPENSES", "part_of", 0.85))
    edges.append(ClusteredEdge("ENT_SAVINGS", "ENT_INVESTMENT", "becomes", 0.7))

    # Health cluster
    edges.append(ClusteredEdge("ENT_EXERCISE", "ENT_ENERGY", "boosts", 0.85))
    edges.append(ClusteredEdge("ENT_SLEEP", "ENT_STRESS", "reduces", 0.8))
    edges.append(ClusteredEdge("ENT_DOCTOR", "ENT_MEDICINE", "prescribes", 0.9))
    edges.append(ClusteredEdge("ENT_NUTRITION", "ENT_ENERGY", "affects", 0.7))

    # BRIDGE EDGES (rare, cross-cluster, high PMI expected)
    # These are the insights BGT-SM should discover!

    # education-health bridge
    edges.append(ClusteredEdge(
        "ENT_HOMEWORK", "ENT_STRESS", "causes", 0.6, is_bridge=True
    ))

    # work-family bridge
    edges.append(ClusteredEdge(
        "ENT_DEADLINE", "ENT_FAMILY_MOOD", "negatively_affects", 0.5, is_bridge=True
    ))

    # finance-entertainment bridge
    edges.append(ClusteredEdge(
        "ENT_BUDGET", "ENT_VACATION", "constrains", 0.55, is_bridge=True
    ))

    # health-family bridge
    edges.append(ClusteredEdge(
        "ENT_EXERCISE", "ENT_FAMILY_MOOD", "improves", 0.6, is_bridge=True
    ))

    # work-health bridge
    edges.append(ClusteredEdge(
        "ENT_MEETING", "ENT_STRESS", "increases", 0.5, is_bridge=True
    ))

    # education-family bridge
    edges.append(ClusteredEdge(
        "ENT_GRADES", "ENT_FAMILY_MOOD", "influences", 0.65, is_bridge=True
    ))

    return edges


def _create_kg_edges(seed: int) -> List[ClusteredEdge]:
    """Create causal edges for CPN."""
    return [
        ClusteredEdge("ENT_HOMEWORK", "ENT_STRESS", "CAUSES", 0.6, "CAUSES"),
        ClusteredEdge("ENT_DEADLINE", "ENT_STRESS", "CAUSES", 0.7, "CAUSES"),
        ClusteredEdge("ENT_STRESS", "ENT_FAMILY_MOOD", "CAUSES", -0.5, "CAUSES"),
        ClusteredEdge("ENT_EXERCISE", "ENT_STRESS", "CAUSES", -0.4, "CAUSES"),
    ]


def _create_episodes(seed: int) -> List[ClusteredEpisode]:
    """Create context episodes."""
    base_time = int(datetime.now().timestamp() * 1000)
    day_ms = 24 * 60 * 60 * 1000

    return [
        ClusteredEpisode(
            episode_id="01CLUSTERED_001",
            summary="Helped Sarah with homework but felt stressed about work deadline.",
            timestamp=base_time - 3 * day_ms,
            emotional_valence=-0.3,
            participants=["self", "Sarah"],
            location="home",
            activity_type="mixed",
            entity_ids=["ENT_HOMEWORK", "ENT_DEADLINE", "ENT_STRESS"],
        ),
        ClusteredEpisode(
            episode_id="01CLUSTERED_002",
            summary="Family vacation planning constrained by budget discussions.",
            timestamp=base_time - 5 * day_ms,
            emotional_valence=0.4,
            participants=["self", "spouse"],
            location="home",
            activity_type="planning",
            entity_ids=["ENT_VACATION", "ENT_BUDGET", "ENT_FAMILY_MOOD"],
        ),
        ClusteredEpisode(
            episode_id="01CLUSTERED_003",
            summary="Exercise session helped reduce work stress, family mood improved.",
            timestamp=base_time - 1 * day_ms,
            emotional_valence=0.7,
            participants=["self"],
            location="gym",
            activity_type="health",
            entity_ids=["ENT_EXERCISE", "ENT_STRESS", "ENT_FAMILY_MOOD"],
        ),
    ]


def _create_actions(seed: int) -> List[ClusteredAction]:
    """Create actions for MCTS."""
    return [
        ClusteredAction("ACT001", "Help with homework", 1.0, 0.8, 0.7),
        ClusteredAction("ACT002", "Exercise together", 1.0, 0.75, 0.65),
        ClusteredAction("ACT003", "Plan vacation", 0.5, 0.7, 0.6),
        ClusteredAction("ACT004", "Review budget", 0.5, 0.5, 0.4),
    ]


def _create_goals(seed: int) -> List[ClusteredGoal]:
    """Create goals for MCTS."""
    return [
        ClusteredGoal("GOAL001", "Improve family connections", 0.9, 1.0),
        ClusteredGoal("GOAL002", "Reduce stress", 0.8, 1.0),
        ClusteredGoal("GOAL003", "Support kids education", 0.85, 1.0),
    ]


def _create_initial_state(seed: int) -> Dict[str, Any]:
    """Create initial state."""
    return {
        "time_of_day": "evening",
        "day": "Wednesday",
        "stress_level": "moderate",
        "family_mood": "neutral",
    }


BGT_CLUSTERED_EXPECTED_PROPERTIES = {
    # CPN
    "cpn_min_counterfactuals": 5,
    "cpn_path_length_ge_1_ratio": 0.2,
    # MCTS
    "mcts_budget_consumption_ratio": 0.5,
    "mcts_max_visit_count": 5,
    # BGT-SM - primary focus
    "bgt_insights_min": 5,
    "bgt_pmi_variance": True,
    "bgt_semantic_distance_range": (0.3, 0.8),
    "bgt_cross_cluster_ratio": 0.6,
    "bgt_no_same_cluster_insights": True,
    # SPC-UQ
    "spc_reconstructions_min": 1,
    "spc_provenance_types_min": 1,
}


def build_world(seed: int = 42, use_ultrabert: bool | None = None):
    """Build the bgt_clustered world.

    Args:
        seed: Random seed for reproducibility.
        use_ultrabert: If True, use UltraBERT embeddings.

    Returns:
        World instance with clustered semantic graph.
    """
    from ..r5_data_factory import World

    entities = _create_entities(seed)
    episodes = _create_episodes(seed)
    semantic_edges = _create_semantic_edges(seed)
    kg_edges = _create_kg_edges(seed)
    actions = _create_actions(seed)
    goals = _create_goals(seed)
    initial_state = _create_initial_state(seed)

    embedding_service = get_embedding_service(use_ultrabert)
    embeddings = embedding_service.embed_entities(entities)

    return World(
        pack_name="bgt_clustered",
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
        expected_properties=BGT_CLUSTERED_EXPECTED_PROPERTIES,
        difficulty="medium",
    )
