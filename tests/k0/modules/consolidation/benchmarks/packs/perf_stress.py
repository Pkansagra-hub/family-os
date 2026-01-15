"""Performance Stress pack - Edge case testing for near-real-time constraints.

Focus: Test all algorithms under strict performance constraints.
Key scenarios:
- Large data volumes with tight time budgets
- Concurrent processing simulation
- Memory-efficient processing requirements
- Latency-sensitive operations

Expected behavior:
- All algorithms should complete within time budgets
- Output quality should degrade gracefully under pressure
- No memory leaks or unbounded growth
- Predictable worst-case performance
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ─────────────────────────────────────────────────────────────────────────────
# Performance timing utilities
# ─────────────────────────────────────────────────────────────────────────────


class PerformanceTimer:
    """Utility for tracking execution time."""
    
    def __init__(self):
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.checkpoints: List[Tuple[str, float]] = []
    
    def start(self):
        self.start_time = time.perf_counter()
    
    def checkpoint(self, name: str):
        self.checkpoints.append((name, time.perf_counter()))
    
    def stop(self):
        self.end_time = time.perf_counter()
    
    @property
    def elapsed_ms(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Domain dataclasses
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class PerfEpisode:
    """Episode optimized for performance testing."""

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
        return 0.7

    @property
    def start_time_ms(self) -> int:
        return self.timestamp


@dataclass
class PerfEntity:
    """Entity for performance testing."""

    entity_id: str
    name: str
    entity_type: str
    category: str
    _observation_count: int = 1

    @property
    def observation_count(self) -> int:
        return self._observation_count


@dataclass
class PerfEdge:
    """Edge for performance testing."""

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
class PerfGoal:
    """Goal for MCTS performance testing."""

    goal_id: str
    description: str
    priority: float
    target_value: float = 1.0


@dataclass
class PerfAction:
    """Action for MCTS performance testing."""

    action_id: str
    name: str
    duration_hours: float
    goal_alignment: float
    expected_reward: float
    preconditions: List[str] = field(default_factory=list)
    effects: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerfState:
    """State for MCTS."""

    state_id: str
    values: Dict[str, Any]


@dataclass
class PerfFragment:
    """Fragment for SPC performance testing."""

    fragment_id: str
    content: str
    timestamp_ms: int
    provenance_type: str
    confidence: float
    
    @property
    def attributes(self) -> tuple:
        return (self.provenance_type,)


@dataclass
class PerfIncompleteEpisode:
    """Incomplete episode for SPC performance testing."""

    episode_id: str
    summary: str
    timestamp: int
    location_name: Optional[str] = None
    participants: Optional[List[str]] = None
    activity_type: Optional[str] = None
    ambiguity_score: float = 0.5


@dataclass
class PerfWorld:
    """World designed for performance stress testing."""

    seed: int
    # CPN data
    episodes: List[PerfEpisode]
    entities: List[PerfEntity]
    kg_edges: List[PerfEdge]
    # BGT data
    semantic_edges: List[PerfEdge]
    embeddings: Dict[str, List[float]]
    # MCTS data
    goals: List[PerfGoal]
    actions: List[PerfAction]
    initial_state: PerfState
    # SPC data
    incomplete_episodes: List[PerfIncompleteEpisode]
    fragments: List[PerfFragment]
    schemas: List[Any]
    context: Dict[str, Any]
    
    # Performance metadata
    data_scale: str  # "small", "medium", "large", "extreme"
    expected_cpn_budget_ms: int
    expected_mcts_budget_ms: int
    expected_bgt_budget_ms: int
    expected_spc_budget_ms: int


# ─────────────────────────────────────────────────────────────────────────────
# Coverage thresholds for performance testing
# ─────────────────────────────────────────────────────────────────────────────

COVERAGE_THRESHOLDS = {
    # CPN must complete within budget
    "min_counterfactuals": 10,
    "path_length_ge_1_ratio": 0.05,
    "plausibility_variance_min": 0.0,
    "scenario_type_count": 2,
    
    # MCTS must complete within budget  
    "min_scenarios": 5,
    "budget_consumption_ratio": 0.1,
    
    # BGT must complete within budget
    "min_insights": 3,
    
    # SPC must complete within budget
    "min_reconstructions": 5,
    
    # Performance hard limits (milliseconds)
    "max_cpn_execution_ms": 3000,   # 3 seconds for CPN
    "max_mcts_execution_ms": 2000,  # 2 seconds for MCTS
    "max_bgt_execution_ms": 2000,   # 2 seconds for BGT
    "max_spc_execution_ms": 2000,   # 2 seconds for SPC
    "max_total_execution_ms": 10000,  # 10 seconds total
}


# ─────────────────────────────────────────────────────────────────────────────
# World builder - generates large-scale data
# ─────────────────────────────────────────────────────────────────────────────


def build_world(
    seed: int = 42,
    use_ultrabert: bool = False,
    scale: str = "large",
) -> PerfWorld:
    """Build a world for performance stress testing.
    
    Args:
        seed: Random seed
        use_ultrabert: Whether to use real embeddings (slower)
        scale: Data scale - "small", "medium", "large", "extreme"
    
    Scale parameters:
        small:   100 episodes,  200 entities,   500 edges
        medium:  300 episodes,  500 entities,  1500 edges
        large:   500 episodes, 1000 entities,  3000 edges (default)
        extreme: 1000 episodes, 2000 entities, 6000 edges
    """
    rng = random.Random(seed)
    base_time = 1700000000000
    
    # Scale parameters
    scale_params = {
        "small": {"episodes": 100, "entities": 200, "edges": 500, "actions": 20, "fragments": 200},
        "medium": {"episodes": 300, "entities": 500, "edges": 1500, "actions": 50, "fragments": 500},
        "large": {"episodes": 500, "entities": 1000, "edges": 3000, "actions": 100, "fragments": 800},
        "extreme": {"episodes": 1000, "entities": 2000, "edges": 6000, "actions": 200, "fragments": 1500},
    }
    
    params = scale_params.get(scale, scale_params["large"])
    
    # ─── Generate entities ────────────────────────────────────────────────────
    categories = ["family", "work", "social", "health", "finance", "entertainment"]
    entity_types = ["person", "place", "event", "concept", "object"]
    
    entities = []
    for i in range(params["entities"]):
        entities.append(PerfEntity(
            entity_id=f"ENT_{i:05d}",
            name=f"Entity {i}",
            entity_type=rng.choice(entity_types),
            category=rng.choice(categories),
        ))
    
    # ─── Generate edges (causal graph) ────────────────────────────────────────
    # Create chains and some cross-connections
    kg_edges = []
    
    # Create causal chains
    chain_count = params["edges"] // 10
    for chain_id in range(chain_count):
        chain_length = rng.randint(3, 8)
        chain_start = rng.randint(0, len(entities) - chain_length - 1)
        
        for j in range(chain_length - 1):
            source = entities[chain_start + j]
            target = entities[chain_start + j + 1]
            kg_edges.append(PerfEdge(
                source_id=source.entity_id,
                target_id=target.entity_id,
                relation="CAUSES",
                weight=rng.uniform(0.5, 0.95),
            ))
    
    # Add random cross-connections
    remaining = params["edges"] - len(kg_edges)
    for _ in range(remaining):
        source = rng.choice(entities)
        target = rng.choice(entities)
        if source.entity_id != target.entity_id:
            kg_edges.append(PerfEdge(
                source_id=source.entity_id,
                target_id=target.entity_id,
                relation="CAUSES",
                weight=rng.uniform(0.3, 0.8),
            ))
    
    # ─── Generate episodes ────────────────────────────────────────────────────
    locations = ["home", "office", "park", "mall", "hospital", "school", "gym", "restaurant"]
    activities = ["meeting", "exercise", "meal", "work", "leisure", "healthcare", "shopping"]
    
    episodes = []
    for i in range(params["episodes"]):
        # Pick 2-5 entities for this episode
        num_entities = rng.randint(2, 5)
        episode_entities = rng.sample(entities, min(num_entities, len(entities)))
        
        episodes.append(PerfEpisode(
            episode_id=f"EP_{i:05d}",
            summary=f"Performance test episode {i} with {num_entities} entities",
            timestamp=base_time + i * 3600000,
            emotional_valence=rng.uniform(-0.9, 0.9),
            participants=[f"participant_{rng.randint(1, 20)}" for _ in range(rng.randint(1, 3))],
            location=rng.choice(locations),
            activity_type=rng.choice(activities),
            entity_ids=[e.entity_id for e in episode_entities],
        ))
    
    # ─── Generate semantic edges for BGT ──────────────────────────────────────
    semantic_edges = []
    for i in range(params["edges"] // 3):
        source = rng.choice(entities)
        target = rng.choice(entities)
        if source.entity_id != target.entity_id:
            semantic_edges.append(PerfEdge(
                source_id=source.entity_id,
                target_id=target.entity_id,
                relation="RELATES_TO",
                weight=rng.uniform(0.1, 1.0),
                edge_type="SEMANTIC",
            ))
    
    # ─── Generate embeddings ──────────────────────────────────────────────────
    embedding_dim = 384
    embeddings = {}
    for e in entities:
        embeddings[e.entity_id] = [rng.random() for _ in range(embedding_dim)]
    
    # ─── Generate MCTS data ───────────────────────────────────────────────────
    goals = [
        PerfGoal(f"GOAL_{i:03d}", f"Performance goal {i}", rng.uniform(0.5, 1.0))
        for i in range(5)
    ]
    
    actions = [
        PerfAction(
            action_id=f"ACT_{i:03d}",
            name=f"Action {i}",
            duration_hours=rng.uniform(0.5, 4.0),
            goal_alignment=rng.uniform(0.3, 0.9),
            expected_reward=rng.uniform(0.2, 0.8),
        )
        for i in range(params["actions"])
    ]
    
    initial_state = PerfState(
        state_id="INIT",
        values={"context": "performance_test", "complexity": scale},
    )
    
    # ─── Generate SPC data ────────────────────────────────────────────────────
    provenance_types = ["calendar", "message", "sensor", "routine", "inferred"]
    
    incomplete_episodes = []
    fragments = []
    
    num_incomplete = params["fragments"] // 10
    for i in range(num_incomplete):
        incomplete_episodes.append(PerfIncompleteEpisode(
            episode_id=f"INC_{i:04d}",
            summary=f"Incomplete episode {i} for performance testing",
            timestamp=base_time + i * 7200000,
            location_name=None if rng.random() > 0.5 else rng.choice(locations),
            participants=None if rng.random() > 0.5 else [f"person_{rng.randint(1, 10)}"],
            activity_type=None if rng.random() > 0.5 else rng.choice(activities),
            ambiguity_score=rng.uniform(0.4, 0.9),
        ))
        
        # Generate 5-15 fragments per incomplete episode
        num_frags = rng.randint(5, 15)
        for j in range(num_frags):
            frag_id = f"FRAG_{i:04d}_{j:02d}"
            # Use prefix to indicate provenance type
            prov_type = rng.choice(provenance_types)
            prefix_map = {
                "calendar": "frag_cal_",
                "message": "frag_msg_",
                "sensor": "frag_sens_",
                "routine": "frag_rout_",
                "inferred": "frag_inf_",
            }
            frag_id = f"{prefix_map[prov_type]}{i:04d}_{j:02d}"
            
            fragments.append(PerfFragment(
                fragment_id=frag_id,
                content=f"Fragment content for episode {i}, piece {j} ({prov_type})",
                timestamp_ms=base_time + i * 7200000 + j * 60000,
                provenance_type=prov_type,
                confidence=rng.uniform(0.3, 0.95),
            ))
    
    # Calculate expected budgets based on scale
    budget_multipliers = {
        "small": 0.5,
        "medium": 1.0,
        "large": 1.5,
        "extreme": 2.5,
    }
    mult = budget_multipliers.get(scale, 1.5)
    
    return PerfWorld(
        seed=seed,
        episodes=episodes,
        entities=entities,
        kg_edges=kg_edges,
        semantic_edges=semantic_edges,
        embeddings=embeddings,
        goals=goals,
        actions=actions,
        initial_state=initial_state,
        incomplete_episodes=incomplete_episodes,
        fragments=fragments,
        schemas=[],
        context={
            "scale": scale,
            "performance_mode": True,
            "nearby_locations": locations,
            "known_locations": locations[:5],
            "frequent_contacts": [f"contact_{i}" for i in range(10)],
        },
        data_scale=scale,
        expected_cpn_budget_ms=int(2000 * mult),
        expected_mcts_budget_ms=int(1500 * mult),
        expected_bgt_budget_ms=int(1500 * mult),
        expected_spc_budget_ms=int(1500 * mult),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Expected properties for validation
# ─────────────────────────────────────────────────────────────────────────────

EXPECTED_PROPERTIES = {
    "data_scale": "large",
    "min_episode_count": 500,
    "min_entity_count": 1000,
    "min_edge_count": 3000,
    "should_complete_in_budget": True,
    "should_not_crash": True,
    "should_produce_valid_output": True,
}
