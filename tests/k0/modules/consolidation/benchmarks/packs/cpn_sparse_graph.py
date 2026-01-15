"""CPN Sparse Graph pack - Edge case testing with extremely sparse causal graphs.

Focus: Test CPN behavior when causal relationships are minimal or fragmented.
Key scenarios:
- Isolated nodes (entities with no causal connections)
- Single-edge chains (no branching)
- Disconnected subgraphs
- High-valence episodes with no causal support

Expected behavior:
- CPN should still produce valid counterfactuals
- Plausibility should reflect sparse support
- Algorithm should not hang on sparse data
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List

# ─────────────────────────────────────────────────────────────────────────────
# Domain dataclasses
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class SparseEpisode:
    """Episode in a sparsely-connected causal world."""

    episode_id: str
    summary: str
    timestamp: int
    emotional_valence: float
    participants: List[str]
    location: str
    activity_type: str
    entity_ids: List[str] = field(default_factory=list)
    is_isolated: bool = False  # True if this episode has no causal connections

    @property
    def sentiment_score(self) -> float:
        return self.emotional_valence

    @property
    def salience(self) -> float:
        return 0.8 if not self.is_isolated else 0.3

    @property
    def start_time_ms(self) -> int:
        return self.timestamp


@dataclass
@dataclass
class SparseEntity:
    """Entity that may or may not have causal connections."""

    entity_id: str
    name: str
    entity_type: str
    category: str
    is_orphan: bool = False  # True if entity has no edges
    _observation_count: int = 1

    @property
    def observation_count(self) -> int:
        return self._observation_count


@dataclass
class SparseEdge:
    """Causal edge - sparse graphs have very few of these."""

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
class SparseGoal:
    """Goal for MCTS in sparse scenarios."""

    goal_id: str
    description: str
    priority: float
    target_value: float = 1.0


@dataclass
class SparseAction:
    """Action with limited preconditions due to sparse graph."""

    action_id: str
    name: str
    duration_hours: float
    goal_alignment: float
    expected_reward: float
    preconditions: List[str] = field(default_factory=list)
    effects: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SparseState:
    """State in sparse scenario."""

    context: str
    has_causal_support: bool
    uncertainty_level: float


@dataclass
class SparseWorld:
    """World with extremely sparse causal structure."""

    seed: int
    episodes: List[SparseEpisode]
    entities: List[SparseEntity]
    kg_edges: List[SparseEdge]
    semantic_edges: List[SparseEdge]
    embeddings: Dict[str, List[float]]
    goals: List[SparseGoal]
    actions: List[SparseAction]
    initial_state: SparseState
    incomplete_episodes: List[Any]
    fragments: List[Any]
    schemas: List[Any]
    context: Dict[str, Any]

    # Sparse-specific metrics
    orphan_entity_count: int = 0
    isolated_episode_count: int = 0
    graph_density: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Coverage thresholds for sparse graph testing
# ─────────────────────────────────────────────────────────────────────────────

COVERAGE_THRESHOLDS = {
    # CPN should still produce SOME counterfactuals even with sparse data
    "min_counterfactuals": 1,
    "path_length_ge_1_ratio": 0.0,  # May have no deep paths
    "path_length_ge_2_ratio": 0.0,
    "path_length_ge_3_count": 0,
    "max_path_length": 0,  # Sparse graphs may have no causal chains
    "plausibility_variance_min": 0.0,  # May have uniform plausibility
    "scenario_type_count": 1,  # At least one type

    # Performance constraints - should not hang
    "max_execution_time_ms": 5000,  # 5 second timeout
}


# ─────────────────────────────────────────────────────────────────────────────
# World builder
# ─────────────────────────────────────────────────────────────────────────────


def build_world(seed: int = 42, use_ultrabert: bool = False) -> SparseWorld:
    """Build a world with extremely sparse causal structure.

    Structure:
    - 20 entities, but only 5 have any causal connections
    - 15 "orphan" entities with no edges
    - 10 episodes, but 6 are "isolated" (no entity overlap with edges)
    - Only 3 causal edges total (vs normal 50+)
    - Graph density < 0.02
    """
    rng = random.Random(seed)
    base_time = 1700000000000  # Base timestamp

    # Create entities - mostly orphans
    entities = []
    connected_entity_ids = ["ENT_ROOT", "ENT_CAUSE_A", "ENT_EFFECT_A", "ENT_CAUSE_B", "ENT_EFFECT_B"]

    for eid in connected_entity_ids:
        entities.append(SparseEntity(
            entity_id=eid,
            name=f"Connected {eid}",
            entity_type="concept",
            category="connected",
            is_orphan=False,
        ))

    # Add orphan entities (no connections)
    for i in range(15):
        entities.append(SparseEntity(
            entity_id=f"ENT_ORPHAN_{i:02d}",
            name=f"Orphan Entity {i}",
            entity_type="concept",
            category="orphan",
            is_orphan=True,
        ))

    # Create MINIMAL edges - only 3 causal connections
    kg_edges = [
        SparseEdge(
            source_id="ENT_ROOT",
            target_id="ENT_CAUSE_A",
            relation="CAUSES",
            weight=0.8,
        ),
        SparseEdge(
            source_id="ENT_CAUSE_A",
            target_id="ENT_EFFECT_A",
            relation="CAUSES",
            weight=0.7,
        ),
        SparseEdge(
            source_id="ENT_ROOT",
            target_id="ENT_CAUSE_B",
            relation="CAUSES",
            weight=0.6,
        ),
    ]

    # Semantic edges - also sparse
    semantic_edges = [
        SparseEdge(
            source_id="ENT_ROOT",
            target_id="ENT_CAUSE_A",
            relation="RELATES_TO",
            weight=0.5,
        ),
    ]

    # Episodes - some connected to causal entities, most isolated
    episodes = []

    # Connected episodes (reference entities in the causal graph)
    for i, (eid, valence) in enumerate([
        ("ENT_ROOT", 0.6),
        ("ENT_CAUSE_A", -0.4),
        ("ENT_EFFECT_A", 0.7),
        ("ENT_CAUSE_B", -0.3),
    ]):
        episodes.append(SparseEpisode(
            episode_id=f"EP_CONNECTED_{i:02d}",
            summary=f"Episode involving {eid} with causal context",
            timestamp=base_time + i * 3600000,
            emotional_valence=valence,
            participants=["self"],
            location="home",
            activity_type="reflection",
            entity_ids=[eid],
            is_isolated=False,
        ))

    # Isolated episodes (reference only orphan entities)
    for i in range(6):
        orphan_id = f"ENT_ORPHAN_{i:02d}"
        valence = rng.uniform(-0.8, 0.8)
        episodes.append(SparseEpisode(
            episode_id=f"EP_ISOLATED_{i:02d}",
            summary=f"Isolated episode with no causal support - orphan {i}",
            timestamp=base_time + (4 + i) * 3600000,
            emotional_valence=valence,
            participants=["self"],
            location="unknown",
            activity_type="isolated_event",
            entity_ids=[orphan_id],
            is_isolated=True,
        ))

    # Generate mock embeddings
    embeddings = {}
    for e in entities:
        embeddings[e.entity_id] = [rng.random() for _ in range(384)]

    # Goals and actions (minimal for sparse scenario)
    goals = [
        SparseGoal(
            goal_id="GOAL_UNDERSTAND",
            description="Understand sparse causal relationships",
            priority=0.8,
        ),
    ]

    actions = [
        SparseAction(
            action_id="ACT_INVESTIGATE",
            name="Investigate connections",
            duration_hours=1.0,
            goal_alignment=0.7,
            expected_reward=0.5,
        ),
    ]

    initial_state = SparseState(
        context="sparse_causal_world",
        has_causal_support=False,
        uncertainty_level=0.9,
    )

    # Calculate graph density
    num_entities = len(entities)
    max_edges = num_entities * (num_entities - 1)
    actual_edges = len(kg_edges)
    density = actual_edges / max_edges if max_edges > 0 else 0.0

    return SparseWorld(
        seed=seed,
        episodes=episodes,
        entities=entities,
        kg_edges=kg_edges,
        semantic_edges=semantic_edges,
        embeddings=embeddings,
        goals=goals,
        actions=actions,
        initial_state=initial_state,
        incomplete_episodes=[],
        fragments=[],
        schemas=[],
        context={"sparse": True, "density": density},
        orphan_entity_count=15,
        isolated_episode_count=6,
        graph_density=density,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Expected properties for validation
# ─────────────────────────────────────────────────────────────────────────────

EXPECTED_PROPERTIES = {
    "graph_density_max": 0.02,  # Very sparse
    "orphan_entity_ratio_min": 0.7,  # Most entities are orphans
    "isolated_episode_ratio_min": 0.5,  # Many episodes are isolated
    "should_not_timeout": True,
    "produces_valid_output": True,
}
