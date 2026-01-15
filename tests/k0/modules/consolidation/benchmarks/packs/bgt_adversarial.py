"""BGT Adversarial pack - Focus on rejecting false positive insights.

This pack tests BGT-SM's ability to:
- Reject spurious correlations that look like insights
- Distinguish true bisociative connections from noise
- Handle entities with similar names but different meanings
- Filter out coincidental co-occurrences
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List

from ..r5_embeddings import get_embedding_service


@dataclass
class AdversarialEntity:
    """Entity potentially confusable with others."""

    entity_id: str
    name: str
    entity_type: str
    category: str
    is_decoy: bool = False  # True if this is a false-positive trap
    _observation_count: int = 1

    @property
    def observation_count(self) -> int:
        return self._observation_count


@dataclass
class AdversarialEdge:
    """Edge with true/spurious indicator."""

    source_id: str
    target_id: str
    relation: str
    weight: float
    edge_type: str = "SEMANTIC"
    is_spurious: bool = False  # True if this is a false correlation
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
class AdversarialEpisode:
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
class AdversarialGoal:
    """Goal for MCTS."""

    goal_id: str
    description: str
    priority: float
    target_value: float = 1.0


@dataclass
class AdversarialAction:
    """Action for MCTS."""

    action_id: str
    name: str
    duration_hours: float
    goal_alignment: float
    expected_reward: float


# ─────────────────────────────────────────────────────────────────────────────
# Adversarial Design: Traps for False Positives
# ─────────────────────────────────────────────────────────────────────────────
#
# Trap 1: Homonym trap
#   - "Bank" (financial) vs "Bank" (river)
#   - Look similar but should NOT be connected
#
# Trap 2: Coincidental co-occurrence
#   - Two unrelated things that happen to appear together
#   - High co-occurrence but no causal/semantic relationship
#
# Trap 3: Transitive confusion
#   - A -> B -> C exists, but A and C are unrelated
#   - Should not infer direct A -> C insight
#
# True insights (should be found):
#   - Cross-domain connections with real semantic meaning


def _create_entities(seed: int) -> List[AdversarialEntity]:
    """Create entities including decoys and traps."""
    return [
        # Real entities with meaning
        AdversarialEntity("ENT_WORK_STRESS", "Work Stress", "state", "health", False, 30),
        AdversarialEntity("ENT_FAMILY_TIME", "Family Time", "event", "family", False, 40),
        AdversarialEntity("ENT_EXERCISE", "Exercise", "activity", "health", False, 25),
        AdversarialEntity("ENT_SLEEP_QUALITY", "Sleep Quality", "state", "health", False, 35),
        AdversarialEntity("ENT_PRODUCTIVITY", "Productivity", "state", "work", False, 28),

        # Homonym trap: Bank (financial)
        AdversarialEntity("ENT_BANK_FINANCIAL", "Bank", "institution", "finance", False, 20),
        AdversarialEntity("ENT_SAVINGS", "Savings Account", "asset", "finance", False, 15),
        AdversarialEntity("ENT_LOAN", "Loan", "liability", "finance", False, 12),

        # Homonym trap: Bank (river) - DECOY
        AdversarialEntity("ENT_BANK_RIVER", "Bank", "location", "nature", True, 8),
        AdversarialEntity("ENT_RIVER", "River", "location", "nature", False, 10),
        AdversarialEntity("ENT_FISHING", "Fishing", "activity", "recreation", False, 6),

        # Coincidental co-occurrence trap
        AdversarialEntity("ENT_COFFEE", "Coffee", "consumable", "food", False, 50),
        AdversarialEntity("ENT_MONDAY", "Monday", "time", "temporal", True, 52),  # DECOY
        # Coffee and Monday co-occur often but no causal relationship

        # Transitive confusion trap
        AdversarialEntity("ENT_ALARM", "Alarm Clock", "device", "home", False, 30),
        AdversarialEntity("ENT_WAKEUP", "Waking Up", "event", "health", False, 30),
        AdversarialEntity("ENT_BREAKFAST", "Breakfast", "event", "food", False, 35),
        # Alarm -> WakeUp -> Breakfast, but Alarm and Breakfast not directly related

        # True cross-domain connections
        AdversarialEntity("ENT_MEDITATION", "Meditation", "activity", "health", False, 15),
        AdversarialEntity("ENT_CREATIVITY", "Creativity", "state", "work", False, 18),
        # Meditation -> Creativity is a real bisociative insight

        AdversarialEntity("ENT_READING", "Reading", "activity", "education", False, 22),
        AdversarialEntity("ENT_EMPATHY", "Empathy", "trait", "social", False, 12),
        # Reading -> Empathy is a real cross-domain insight

        # More noise entities
        AdversarialEntity("ENT_WEATHER", "Weather", "condition", "environment", True, 100),
        AdversarialEntity("ENT_TRAFFIC", "Traffic", "condition", "transport", True, 80),
        AdversarialEntity("ENT_NEWS", "News", "content", "media", True, 60),
    ]


def _create_semantic_edges(seed: int) -> List[AdversarialEdge]:
    """Create edges with true and spurious connections."""
    edges = []

    # Real, meaningful connections
    edges.append(AdversarialEdge(
        "ENT_WORK_STRESS", "ENT_SLEEP_QUALITY", "negatively_affects", 0.7
    ))
    edges.append(AdversarialEdge(
        "ENT_EXERCISE", "ENT_SLEEP_QUALITY", "improves", 0.75
    ))
    edges.append(AdversarialEdge(
        "ENT_SLEEP_QUALITY", "ENT_PRODUCTIVITY", "affects", 0.8
    ))
    edges.append(AdversarialEdge(
        "ENT_FAMILY_TIME", "ENT_WORK_STRESS", "reduces", 0.6
    ))

    # Financial bank connections (real)
    edges.append(AdversarialEdge(
        "ENT_BANK_FINANCIAL", "ENT_SAVINGS", "holds", 0.9
    ))
    edges.append(AdversarialEdge(
        "ENT_BANK_FINANCIAL", "ENT_LOAN", "provides", 0.85
    ))

    # River bank connections (real within domain)
    edges.append(AdversarialEdge(
        "ENT_BANK_RIVER", "ENT_RIVER", "part_of", 0.9
    ))
    edges.append(AdversarialEdge(
        "ENT_RIVER", "ENT_FISHING", "enables", 0.7
    ))

    # SPURIOUS: Bank homonym trap - should NOT be found as insight
    edges.append(AdversarialEdge(
        "ENT_BANK_FINANCIAL", "ENT_BANK_RIVER", "same_name", 0.1, is_spurious=True
    ))

    # SPURIOUS: Coffee-Monday coincidence
    edges.append(AdversarialEdge(
        "ENT_COFFEE", "ENT_MONDAY", "co_occurs_with", 0.8, is_spurious=True
    ))

    # Transitive chain (real connections)
    edges.append(AdversarialEdge(
        "ENT_ALARM", "ENT_WAKEUP", "triggers", 0.95
    ))
    edges.append(AdversarialEdge(
        "ENT_WAKEUP", "ENT_BREAKFAST", "leads_to", 0.85
    ))
    # Note: No direct Alarm -> Breakfast edge

    # TRUE CROSS-DOMAIN INSIGHTS (should be found)
    edges.append(AdversarialEdge(
        "ENT_MEDITATION", "ENT_CREATIVITY", "enhances", 0.65
    ))
    edges.append(AdversarialEdge(
        "ENT_READING", "ENT_EMPATHY", "develops", 0.6
    ))
    edges.append(AdversarialEdge(
        "ENT_EXERCISE", "ENT_CREATIVITY", "boosts", 0.55
    ))

    # Noise edges (high frequency, low meaning)
    edges.append(AdversarialEdge(
        "ENT_WEATHER", "ENT_TRAFFIC", "affects", 0.4, is_spurious=True
    ))
    edges.append(AdversarialEdge(
        "ENT_NEWS", "ENT_WORK_STRESS", "correlates", 0.3, is_spurious=True
    ))

    return edges


def _create_kg_edges(seed: int) -> List[AdversarialEdge]:
    """Create causal edges for CPN."""
    return [
        AdversarialEdge("ENT_WORK_STRESS", "ENT_SLEEP_QUALITY", "CAUSES", -0.5, "CAUSES"),
        AdversarialEdge("ENT_EXERCISE", "ENT_WORK_STRESS", "CAUSES", -0.3, "CAUSES"),
        AdversarialEdge("ENT_FAMILY_TIME", "ENT_WORK_STRESS", "CAUSES", -0.4, "CAUSES"),
    ]


def _create_episodes(seed: int) -> List[AdversarialEpisode]:
    """Create context episodes."""
    base_time = int(datetime.now().timestamp() * 1000)
    day_ms = 24 * 60 * 60 * 1000

    return [
        AdversarialEpisode(
            episode_id="01ADVERSARIAL_001",
            summary="Had coffee on Monday morning, usual routine.",
            timestamp=base_time - 3 * day_ms,
            emotional_valence=0.3,
            participants=["self"],
            location="home",
            activity_type="routine",
            entity_ids=["ENT_COFFEE", "ENT_MONDAY"],
        ),
        AdversarialEpisode(
            episode_id="01ADVERSARIAL_002",
            summary="Meditation session this morning led to creative breakthrough at work.",
            timestamp=base_time - 2 * day_ms,
            emotional_valence=0.8,
            participants=["self"],
            location="home",
            activity_type="wellness",
            entity_ids=["ENT_MEDITATION", "ENT_CREATIVITY"],
        ),
        AdversarialEpisode(
            episode_id="01ADVERSARIAL_003",
            summary="Went to the bank, then walked by the river bank.",
            timestamp=base_time - 1 * day_ms,
            emotional_valence=0.5,
            participants=["self"],
            location="town",
            activity_type="errands",
            entity_ids=["ENT_BANK_FINANCIAL", "ENT_BANK_RIVER"],
        ),
    ]


def _create_actions(seed: int) -> List[AdversarialAction]:
    """Create actions for MCTS."""
    return [
        AdversarialAction("ACT001", "Meditate", 0.5, 0.7, 0.6),
        AdversarialAction("ACT002", "Exercise", 1.0, 0.75, 0.65),
        AdversarialAction("ACT003", "Read a book", 1.0, 0.6, 0.5),
        AdversarialAction("ACT004", "Family time", 2.0, 0.85, 0.75),
    ]


def _create_goals(seed: int) -> List[AdversarialGoal]:
    """Create goals for MCTS."""
    return [
        AdversarialGoal("GOAL001", "Reduce stress", 0.9, 1.0),
        AdversarialGoal("GOAL002", "Boost creativity", 0.8, 1.0),
        AdversarialGoal("GOAL003", "Improve wellbeing", 0.85, 1.0),
    ]


def _create_initial_state(seed: int) -> Dict[str, Any]:
    """Create initial state."""
    return {
        "time_of_day": "morning",
        "day": "Tuesday",
        "stress_level": "moderate",
        "creativity": "low",
    }


BGT_ADVERSARIAL_EXPECTED_PROPERTIES = {
    # CPN
    "cpn_min_counterfactuals": 3,
    "cpn_path_length_ge_1_ratio": 0.1,
    # MCTS
    "mcts_budget_consumption_ratio": 0.5,
    "mcts_max_visit_count": 5,
    # BGT-SM - primary focus on rejection
    "bgt_insights_min": 3,
    "bgt_pmi_variance": True,
    "bgt_semantic_distance_range": (0.4, 0.9),
    "bgt_cross_cluster_ratio": 0.8,
    "bgt_false_positive_rate": 0.1,  # <10% spurious insights
    "bgt_rejects_homonyms": True,
    "bgt_rejects_coincidental": True,
    # SPC-UQ
    "spc_reconstructions_min": 1,
    "spc_provenance_types_min": 1,
}


def build_world(seed: int = 42, use_ultrabert: bool | None = None):
    """Build the bgt_adversarial world.

    Args:
        seed: Random seed for reproducibility.
        use_ultrabert: If True, use UltraBERT embeddings.

    Returns:
        World instance with adversarial examples.
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
        pack_name="bgt_adversarial",
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
        expected_properties=BGT_ADVERSARIAL_EXPECTED_PROPERTIES,
        difficulty="hard",
    )
