"""
Demonstration script showing real inputs and outputs for R5 Dream Phase algorithms.

This script runs each algorithm with realistic data and prints the actual
inputs provided and outputs produced, so you can verify the models work correctly.

Usage:
    python -m tests.k0.modules.consolidation.benchmarks.show_io
    python -m tests.k0.modules.consolidation.benchmarks.show_io --pack toy
    python -m tests.k0.modules.consolidation.benchmarks.show_io --pack toy --ultrabert

Options:
    --pack PACK       Use scenario pack from factory (default: inline demo data)
    --ultrabert       Use UltraBERT embeddings (768-dim) instead of clustered (64-dim)
    --export          Export results to markdown file

Outputs:
    - Console output with full details
    - Markdown file: tests/k0/modules/consolidation/benchmarks/r5_algorithm_results.md
"""

from __future__ import annotations

import argparse
import json
import os
import random
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from typing import Any, Dict, List, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Global world reference (set when using --pack mode)
# ─────────────────────────────────────────────────────────────────────────────

_ACTIVE_WORLD: Any = None


def get_active_world():
    """Get the active world if using pack mode, else None."""
    return _ACTIVE_WORLD


# ─────────────────────────────────────────────────────────────────────────────
# Simple data classes that match the Protocol interfaces
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class DemoEpisode:
    """Episode object matching EpisodeProtocol."""

    episode_id: str
    summary: str
    timestamp: int  # ms since epoch
    emotional_valence: float
    participants: List[str]
    location: str
    activity_type: str
    entity_ids: List[str] = None  # For CPN causal chain extraction

    def __post_init__(self):
        if self.entity_ids is None:
            self.entity_ids = []

    # For compatibility with algorithms
    @property
    def sentiment_score(self) -> float:
        return self.emotional_valence

    @property
    def salience(self) -> float:
        return 0.8  # Default high salience

    @property
    def start_time_ms(self) -> int:
        return self.timestamp


@dataclass
class DemoEntity:
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
class DemoEdge:
    """Edge object matching EdgeProtocol / KGEdgeProtocol."""

    source_id: str
    target_id: str
    relation: str
    weight: float
    edge_type: str = "SEMANTIC"
    _observation_count: int = 1

    # For CPN causal chains
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
class DemoGoal:
    """Goal object for MCTS."""

    goal_id: str
    description: str
    priority: float
    target_value: float = 1.0


@dataclass
class DemoAction:
    """Action object for MCTS."""

    action_id: str
    name: str
    duration_hours: float
    goal_alignment: float
    expected_reward: float


# ─────────────────────────────────────────────────────────────────────────────
# Setup realistic test data
# ─────────────────────────────────────────────────────────────────────────────


def create_realistic_episodes() -> List[DemoEpisode]:
    """Create realistic family episodes for testing with entity IDs for CPN."""
    base_time = int(datetime.now().timestamp() * 1000)
    day_ms = 24 * 60 * 60 * 1000

    return [
        DemoEpisode(
            episode_id="01HWQR5X7KJMN3P4Q8R9S0T1V2",
            summary="Had breakfast with kids before school. Sarah was excited about her science project.",
            timestamp=base_time - 7 * day_ms,
            emotional_valence=0.8,
            participants=["self", "Sarah", "Tommy"],
            location="home_kitchen",
            activity_type="family_meal",
            entity_ids=["ENT_BREAKFAST", "ENT_SARAH", "ENT_TOMMY"],
        ),
        DemoEpisode(
            episode_id="01HWQR5X8LKNO4Q5R9S0T1U2W3",
            summary="Missed Tommy's soccer practice because of work meeting that ran late.",
            timestamp=base_time - 5 * day_ms,
            emotional_valence=-0.7,  # Strong negative for regret detection
            participants=["self", "Tommy"],
            location="office",
            activity_type="work_conflict",
            entity_ids=["ENT_WORK_MEETING", "ENT_SOCCER", "ENT_TOMMY"],
        ),
        DemoEpisode(
            episode_id="01HWQR5X9MLOP5R6S0T1U2V3X4",
            summary="Family movie night - watched kids' favorite animated film together.",
            timestamp=base_time - 3 * day_ms,
            emotional_valence=0.9,
            participants=["self", "Sarah", "Tommy", "spouse"],
            location="home_living_room",
            activity_type="family_entertainment",
            entity_ids=["ENT_MOVIE", "ENT_FAMILY_TIME"],
        ),
        DemoEpisode(
            episode_id="01HWQR5XANMPQ6S7T1U2V3W4Y5",
            summary="Argued with spouse about household budget. Felt stressed and frustrated.",
            timestamp=base_time - 2 * day_ms,
            emotional_valence=-0.65,  # Negative for regret detection
            participants=["self", "spouse"],
            location="home_bedroom",
            activity_type="relationship_conflict",
            entity_ids=["ENT_BUDGET", "ENT_SPOUSE", "ENT_STRESS"],
        ),
        DemoEpisode(
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


def create_realistic_entities() -> List[DemoEntity]:
    """Create realistic entity graph for BGT-SM.

    NOTE: observation_count varies per entity to enable meaningful PMI calculation.
    PMI = log2((c_ab * N) / (c_a * c_b)) requires variance in counts.
    """
    return [
        DemoEntity("ENT001", "Sarah", "person", "family", _observation_count=50),  # Very frequent
        DemoEntity("ENT002", "Tommy", "person", "family", _observation_count=45),  # Very frequent
        DemoEntity("ENT003", "spouse", "person", "family", _observation_count=40),
        DemoEntity("ENT004", "homework", "activity", "education", _observation_count=15),
        DemoEntity("ENT005", "soccer", "activity", "sports", _observation_count=8),  # Less common
        DemoEntity("ENT006", "work_meeting", "activity", "work", _observation_count=25),
        DemoEntity("ENT007", "budget", "topic", "finance", _observation_count=5),  # Rare
        DemoEntity(
            "ENT008", "science_project", "activity", "education", _observation_count=3
        ),  # Rare
        DemoEntity("ENT009", "movie_night", "activity", "entertainment", _observation_count=10),
        DemoEntity("ENT010", "fractions", "topic", "education", _observation_count=2),  # Very rare
    ]


def create_realistic_edges() -> List[DemoEdge]:
    """Create realistic edges between entities.

    NOTE: observation_count (cooccurrence) varies per edge for meaningful PMI.
    High cooccurrence = entities often appear together in episodes.
    """
    return [
        DemoEdge("ENT001", "ENT004", "does", 0.8, _observation_count=12),  # Sarah + homework often
        DemoEdge("ENT001", "ENT008", "works_on", 0.9, _observation_count=3),  # Sarah + science less
        DemoEdge("ENT001", "ENT010", "learns", 0.7, _observation_count=2),  # Sarah + fractions rare
        DemoEdge("ENT002", "ENT005", "plays", 0.9, _observation_count=7),  # Tommy + soccer
        DemoEdge("ENT003", "ENT007", "discusses", 0.6, _observation_count=4),  # Spouse + budget
        DemoEdge("ENT001", "ENT009", "enjoys", 0.8, _observation_count=8),  # Sarah + movies
        DemoEdge("ENT002", "ENT009", "enjoys", 0.8, _observation_count=9),  # Tommy + movies
        DemoEdge(
            "ENT006", "ENT005", "conflicts_with", -0.5, _observation_count=2
        ),  # Work vs soccer rare
        # Cross-domain edges for BGT insight discovery
        DemoEdge(
            "ENT004", "ENT005", "balances_with", 0.4, _observation_count=1
        ),  # homework/soccer rare
        DemoEdge(
            "ENT007", "ENT009", "funded_by", 0.3, _observation_count=1
        ),  # budget/movies very rare
    ]


def create_kg_edges_for_cpn() -> List[DemoEdge]:
    """
    Create causal edges for CPN (CAUSES relationships).

    CPN builds causal DAGs by following CAUSES edges between entity IDs.
    The entity_ids in episodes are the nodes; CAUSES edges connect them.
    """
    return [
        # Causal chain: Work meeting -> Missed soccer -> Stress -> Budget argument
        # Work meeting caused stress
        DemoEdge(
            source_id="ENT_WORK_MEETING",
            target_id="ENT_STRESS",
            relation="CAUSES",
            weight=0.8,
            edge_type="CAUSES",
        ),
        # Missed soccer caused stress
        DemoEdge(
            source_id="ENT_SOCCER",
            target_id="ENT_STRESS",
            relation="CAUSES",
            weight=0.7,
            edge_type="CAUSES",
        ),
        # Stress caused budget argument
        DemoEdge(
            source_id="ENT_STRESS",
            target_id="ENT_BUDGET",
            relation="CAUSES",
            weight=0.75,
            edge_type="CAUSES",
        ),
        # Work meeting indirectly caused soccer miss
        DemoEdge(
            source_id="ENT_WORK_MEETING",
            target_id="ENT_SOCCER",
            relation="CAUSES",
            weight=0.9,
            edge_type="CAUSES",
        ),
    ]


def create_realistic_actions() -> List[DemoAction]:
    """Create realistic actions for MCTS."""
    return [
        DemoAction("ACT001", "Take kids to park", 2.0, 0.9, 0.85),
        DemoAction("ACT002", "Go grocery shopping", 1.0, 0.3, 0.4),
        DemoAction("ACT003", "Family grocery trip", 1.5, 0.7, 0.65),
        DemoAction("ACT004", "Help with homework", 1.0, 0.8, 0.75),
        DemoAction("ACT005", "Exercise", 1.0, 0.5, 0.6),
        DemoAction("ACT006", "Family board game", 1.5, 0.85, 0.8),
    ]


def create_realistic_goals() -> List[DemoGoal]:
    """Create realistic user goals."""
    return [
        DemoGoal("GOAL001", "Be more present with family", 0.9, 1.0),
        DemoGoal("GOAL002", "Help kids with school success", 0.8, 1.0),
        DemoGoal("GOAL003", "Improve work-life balance", 0.7, 1.0),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Algorithm 1: CPN (Causal Perturbation Network)
# ─────────────────────────────────────────────────────────────────────────────


def demo_cpn():
    """Demonstrate CPN counterfactual generation."""
    print("\n" + "=" * 80)
    print("ALGORITHM 1: CPN (Causal Perturbation Network)")
    print("Purpose: Generate 'what-if' counterfactual scenarios from regretful events")
    print("=" * 80)

    from k0.modules.consolidation.algorithms.cpn import CausalPerturbationNetwork, CPNConfig

    episodes = create_realistic_episodes()
    kg_edges = create_kg_edges_for_cpn()

    print("\n[INPUT] Episodes with emotional valence")
    print("-" * 60)
    for ep in episodes:
        emoji = "positive" if ep.emotional_valence > 0 else "negative"
        print(f"  [{ep.episode_id}] {emoji} valence={ep.emotional_valence:+.1f}")
        print(f"    Summary: {ep.summary}")
        print(f"    Entity IDs: {ep.entity_ids}")

    print("\n[INPUT] Causal edges (cause -> effect relationships)")
    print("-" * 60)
    for edge in kg_edges:
        print(f"  {edge.source_id} -> {edge.target_id}")
        print(f"    relation: {edge.relation}, weight: {edge.weight}")

    # Configure CPN with lower threshold to catch our negative events
    config = CPNConfig(
        emotional_threshold=0.6,  # |valence| > 0.6 for regret
        top_k_regret_events=5,
        causal_chain_depth=3,
        seed=42,
    )

    cpn = CausalPerturbationNetwork(config=config)

    print("\n[PROCESSING] Selecting regret-worthy events (|valence| > 0.6)")
    print("-" * 60)
    regret_episodes = [e for e in episodes if abs(e.emotional_valence) >= 0.6]
    print(f"  Found {len(regret_episodes)} episodes with strong emotional charge:")
    for ep in regret_episodes:
        print(f"    {ep.summary} (valence={ep.emotional_valence:+.1f})")

    print("\n[PROCESSING] Generating counterfactual scenarios...")
    print("-" * 60)

    counterfactuals = cpn.generate(episodes=episodes, kg_edges=kg_edges, rng_seed=42)

    print("\n[OUTPUT] Counterfactual Scenarios Generated")
    print("-" * 60)
    if counterfactuals:
        for i, cf in enumerate(counterfactuals, 1):
            print(f"\n  Counterfactual #{i}:")
            print(f"    Base Episode ID: {cf.base_episode_id}")
            print(f"    Scenario ID: {cf.scenario_id}")
            print(f"    Scenario Type: {cf.scenario_type}")
            print(f"    Intervention Node: {cf.intervention_node_id}")
            print(f"    Perturbation Target: {cf.perturbation_target}")
            print(f"    Original Outcome: {cf.original_outcome}")
            print(f"    Counterfactual Outcome: {cf.counterfactual_outcome}")
            print(f"    Original Sentiment: {cf.original_sentiment:+.2f}")
            print(f"    Predicted Sentiment: {cf.predicted_sentiment:+.2f}")
            print(f"    Plausibility: {cf.plausibility:.2f}")
            print(f"    Success Probability: {cf.success_probability:.2f}")
            print(f"    Utility Delta: {cf.utility_delta:+.2f}")
            print(f"    Causal Path Length: {cf.causal_path_length}")
            if cf.mitigation:
                print(f"    Mitigation: {cf.mitigation}")
    else:
        print("  (No counterfactuals generated - may need more causal edges)")
        print("  The algorithm requires CAUSES edges between episodes to build DAGs")

    # ─────────────────────────────────────────────────────────────────────────
    # VERIFICATION FOOTER
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[VERIFICATION] CPN Algorithm Metrics")
    print("-" * 60)

    # Collect verification stats
    regret_count = len(regret_episodes)
    cf_count = len(counterfactuals) if counterfactuals else 0
    graph_edges = len(kg_edges)

    # Path length analysis
    path_lengths = [cf.causal_path_length for cf in counterfactuals] if counterfactuals else []
    nonzero_paths = sum(1 for p in path_lengths if p > 0)
    path_length_unique = set(path_lengths) if path_lengths else set()

    # Plausibility analysis
    plausibilities = [cf.plausibility for cf in counterfactuals] if counterfactuals else []
    plausibility_unique = set(round(p, 4) for p in plausibilities)

    # Scenario type breakdown
    type_counts = {}
    if counterfactuals:
        for cf in counterfactuals:
            stype = str(cf.scenario_type).replace("ScenarioType.", "")
            type_counts[stype] = type_counts.get(stype, 0) + 1

    print(f"  regret_candidates: {regret_count}")
    print(f"  counterfactuals_generated: {cf_count}")
    print(f"  graph_edges_used: {graph_edges}")
    print(f"  nonzero_path_length_count: {nonzero_paths} / {cf_count}")
    print(f"  path_length_unique_values: {path_length_unique}")
    print(f"  plausibility_unique_values: {plausibility_unique}")
    print(f"  scenario_type_breakdown: {type_counts}")

    # Warnings
    warnings = []
    if nonzero_paths == 0 and cf_count > 0:
        warnings.append("ALL path_lengths are 0 - DAG depth not being computed")
    if len(plausibility_unique) <= 2 and cf_count > 5:
        warnings.append(
            f"Only {len(plausibility_unique)} unique plausibility values - check DAG computation"
        )

    if warnings:
        print("  WARNINGS:")
        for w in warnings:
            print(f"    - {w}")

    return counterfactuals


# ─────────────────────────────────────────────────────────────────────────────
# Algorithm 2: TPN-MCTS (Temporal Projection Monte Carlo Tree Search)
# ─────────────────────────────────────────────────────────────────────────────


def demo_mcts():
    """Demonstrate MCTS forward simulation."""
    print("\n" + "=" * 80)
    print("ALGORITHM 2: TPN-MCTS (Temporal Projection MCTS)")
    print("Purpose: Simulate future scenarios via Monte Carlo tree search")
    print("=" * 80)

    from k0.modules.consolidation.algorithms.mcts import (
        ComputeBudget,
        DecisionType,
        MCTSConfig,
        TemporalProjectionMCTS,
    )

    goals = create_realistic_goals()
    actions = create_realistic_actions()

    print("\n[INPUT] Initial State")
    print("-" * 60)
    initial_state = {
        "time_of_day": "morning",
        "day": "Saturday",
        "family_mood": "neutral",
        "pending_tasks": ["grocery shopping", "kids homework help", "exercise"],
    }
    print(f"  {json.dumps(initial_state, indent=4)}")

    print("\n[INPUT] Available Actions")
    print("-" * 60)
    for act in actions:
        print(f"  {act.name}")
        print(f"    duration: {act.duration_hours}h, goal_alignment: {act.goal_alignment:.1f}")

    print("\n[INPUT] User Goals")
    print("-" * 60)
    for goal in goals:
        print(f"  {goal.description} (priority: {goal.priority})")

    # Configure MCTS
    config = MCTSConfig(
        exploration_constant=1.414,  # sqrt(2) per UCT
        max_rollout_depth=5,
        discount_factor=0.9,
        seed=42,
    )

    budget = ComputeBudget(max_mcts_rollouts=100)

    mcts = TemporalProjectionMCTS(config=config)

    print("\n[PROCESSING] Running MCTS simulation")
    print("-" * 60)
    print(f"  Exploration constant (c): {config.exploration_constant}")
    print(f"  Max rollout depth: {config.max_rollout_depth}")
    print(f"  Budget: {budget.max_mcts_rollouts} rollouts")

    scenarios = mcts.simulate(
        initial_state=initial_state,
        available_actions=actions,
        budget=budget,
        rng_seed=42,
        decision_type=DecisionType.GENERIC,  # Using GENERIC for family decisions
        goal=goals[0],  # Primary goal
    )

    print("\n[OUTPUT] Projected Future Scenarios")
    print("-" * 60)
    if scenarios:
        for i, scenario in enumerate(scenarios, 1):
            print(f"\n  Scenario #{i}:")
            print(f"    Scenario ID: {scenario.scenario_id}")
            print(f"    Expected Reward: {scenario.expected_reward:.4f}")
            print(f"    Visit Count: {scenario.visit_count}")
            print(f"    Success Probability: {scenario.success_probability:.4f}")
            print(f"    Plausibility: {scenario.plausibility:.4f}")
            if scenario.action_sequence:
                print(f"    Action Sequence: {scenario.action_sequence}")
    else:
        print("  (No scenarios generated)")

    # ─────────────────────────────────────────────────────────────────────────
    # VERIFICATION FOOTER
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[VERIFICATION] MCTS Algorithm Metrics")
    print("-" * 60)

    # Collect verification stats
    rollouts_requested = budget.max_mcts_rollouts
    scenarios_returned = len(scenarios) if scenarios else 0

    # Visit count analysis
    visit_counts = [s.visit_count for s in scenarios] if scenarios else []
    total_visits = sum(visit_counts)
    max_visits = max(visit_counts) if visit_counts else 0

    # Reward analysis
    rewards = [s.expected_reward for s in scenarios] if scenarios else []
    reward_unique = set(round(r, 6) for r in rewards)

    # Plausibility analysis
    plausibilities = [s.plausibility for s in scenarios] if scenarios else []
    plausibility_unique = set(round(p, 4) for p in plausibilities)

    print(f"  rollouts_requested: {rollouts_requested}")
    print(f"  scenarios_returned: {scenarios_returned}")
    print(f"  total_visit_count: {total_visits}")
    print(f"  max_visit_count: {max_visits}")
    print(f"  visit_counts: {visit_counts}")
    print(f"  reward_unique_values: {reward_unique}")
    print(f"  plausibility_unique_values: {plausibility_unique}")
    print(f"  budget_consumption_ratio: {total_visits / rollouts_requested:.4f}")

    # Warnings
    warnings = []
    if total_visits < rollouts_requested * 0.5:
        warnings.append(
            f"Budget underutilized: {total_visits}/{rollouts_requested} visits ({100*total_visits/rollouts_requested:.1f}%)"
        )
    if max_visits == 1 and rollouts_requested > 10:
        warnings.append(
            "All nodes have visit_count=1 - tree never expanded (check select/expand/backprop)"
        )
    if scenarios_returned == 0:
        warnings.append("No scenarios returned - check tree construction")
    elif scenarios_returned == 1 and rollouts_requested >= 10:
        warnings.append("Only 1 scenario returned - check _extract_scenarios / early termination")

    if warnings:
        print("  WARNINGS:")
        for w in warnings:
            print(f"    - {w}")
    else:
        print("  STATUS: OK - budget well-utilized")

    return scenarios

    return scenarios


# ─────────────────────────────────────────────────────────────────────────────
# Algorithm 3: BGT-SM (Bisociative Graph Traversal with Semantic Matching)
# ─────────────────────────────────────────────────────────────────────────────


def demo_bgt():
    """Demonstrate BGT-SM insight discovery."""
    print("\n" + "=" * 80)
    print("ALGORITHM 3: BGT-SM (Bisociative Graph Traversal)")
    print("Purpose: Discover unexpected connections between distant concepts")
    print("=" * 80)

    from k0.modules.consolidation.algorithms.bgt_sm import BGTConfig, BisociativeGraphTraversal

    entities = create_realistic_entities()
    edges = create_realistic_edges()

    print("\n[INPUT] Knowledge Graph Entities")
    print("-" * 60)
    for ent in entities:
        print(f"  [{ent.entity_id}] {ent.name} ({ent.entity_type}/{ent.category})")

    print("\n[INPUT] Knowledge Graph Edges")
    print("-" * 60)
    for edge in edges:
        src = next((e.name for e in entities if e.entity_id == edge.source_id), edge.source_id)
        tgt = next((e.name for e in entities if e.entity_id == edge.target_id), edge.target_id)
        print(f"  {src} --[{edge.relation}]--> {tgt} (weight: {edge.weight})")

    # Create embeddings for semantic distance calculation
    embeddings = {}
    for ent in entities:
        # Deterministic pseudo-embedding based on entity ID
        random.seed(hash(ent.entity_id) % 2**32)
        embeddings[ent.entity_id] = [random.gauss(0, 1) for _ in range(64)]

    print("\n[INPUT] Entity Embeddings")
    print("-" * 60)
    print(f"  Generated 64-dimensional embeddings for {len(embeddings)} entities")
    sample_emb = embeddings["ENT001"][:5]
    print(f"  Sample (ENT001/Sarah first 5 dims): {[f'{v:.2f}' for v in sample_emb]}")

    config = BGTConfig(
        pmi_threshold=1.0,  # Lower for demo
        semantic_distance_threshold=0.5,
        walk_steps=50,  # Shorter walks for demo
        max_walks_per_seed=3,
        seed=42,
    )

    bgt = BisociativeGraphTraversal(config=config)

    # Start exploration from family member entities
    seed_entities = ["ENT001", "ENT002"]  # Sarah and Tommy

    print("\n[PROCESSING] Random walks from seed entities")
    print("-" * 60)
    print("  Seed entities: Sarah (ENT001), Tommy (ENT002)")
    print(f"  Walk steps: {config.walk_steps}")
    print(f"  Number of walks per seed: {config.max_walks_per_seed}")
    print(f"  PMI threshold: {config.pmi_threshold}")
    print(f"  Semantic distance threshold: {config.semantic_distance_threshold}")

    insights = bgt.discover(
        entities=entities,
        edges=edges,
        seed_entity_ids=seed_entities,
        embeddings=embeddings,
        rng_seed=42,
    )

    print("\n[OUTPUT] Discovered Insights (Unexpected Connections)")
    print("-" * 60)
    if insights:
        for i, insight in enumerate(insights, 1):
            src = next(
                (e.name for e in entities if e.entity_id == insight.source_entity_id),
                insight.source_entity_id,
            )
            tgt = next(
                (e.name for e in entities if e.entity_id == insight.target_entity_id),
                insight.target_entity_id,
            )
            print(f"\n  Insight #{i}:")
            print(f"    Connection: {src} <-> {tgt}")
            print(f"    Insight Text: {insight.insight_text}")
            print(f"    Novelty Score: {insight.novelty_score:.3f}")
            print(f"    PMI Score: {insight.pmi_score:.3f}")
            print(f"    Semantic Distance: {insight.semantic_distance:.3f}")
    else:
        print("  (No novel insights discovered - graph may be too densely connected)")
        print("  BGT works best when finding connections between distant concepts")

    # ─────────────────────────────────────────────────────────────────────────
    # VERIFICATION FOOTER
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[VERIFICATION] BGT-SM Algorithm Metrics")
    print("-" * 60)

    # Collect verification stats
    insights_count = len(insights) if insights else 0
    entity_count = len(entities)
    edge_count = len(edges)
    seed_count = len(seed_entities)

    # PMI analysis
    pmi_scores = [insight.pmi_score for insight in insights] if insights else []
    pmi_unique = set(round(p, 4) for p in pmi_scores)

    # Semantic distance analysis
    sem_distances = [insight.semantic_distance for insight in insights] if insights else []
    sem_unique = set(round(d, 4) for d in sem_distances)

    # Novelty analysis
    novelties = [insight.novelty_score for insight in insights] if insights else []
    novelty_unique = set(round(n, 4) for n in novelties)

    # Check observation counts in input data
    entity_obs_counts = [ent.observation_count for ent in entities]
    edge_obs_counts = [edge.observation_count for edge in edges]
    entity_obs_unique = set(entity_obs_counts)
    edge_obs_unique = set(edge_obs_counts)

    print(f"  seeds_used: {seed_count}")
    print(f"  graph_entities: {entity_count}")
    print(f"  graph_edges: {edge_count}")
    print(f"  insights_discovered: {insights_count}")
    print(f"  pmi_scores: {pmi_scores}")
    print(f"  pmi_unique_values: {pmi_unique}")
    print(f"  semantic_distance_unique: {sem_unique}")
    print(f"  novelty_unique_values: {novelty_unique}")
    print(f"  input_entity_observation_counts: {entity_obs_unique}")
    print(f"  input_edge_observation_counts: {edge_obs_unique}")

    # Warnings
    warnings = []
    if len(pmi_unique) == 1 and insights_count > 2:
        warnings.append(
            f"Constant PMI={next(iter(pmi_unique))} - all pairs have same observation counts"
        )
    if len(entity_obs_unique) == 1:
        warnings.append(
            f"All entities have observation_count={next(iter(entity_obs_unique))} - need variance for PMI"
        )
    if len(edge_obs_unique) == 1:
        warnings.append(
            f"All edges have observation_count={next(iter(edge_obs_unique))} - need variance for cooccurrence"
        )
    if insights_count == 0:
        warnings.append("No insights discovered - check thresholds or graph connectivity")

    if warnings:
        print("  WARNINGS:")
        for w in warnings:
            print(f"    - {w}")
    else:
        print("  STATUS: OK - PMI/semantic variance detected")

    return insights


# ─────────────────────────────────────────────────────────────────────────────
# Algorithm 4: SPC-UQ (Schematic Pattern Completion with Uncertainty)
# ─────────────────────────────────────────────────────────────────────────────


def demo_spc_uq():
    """Demonstrate SPC-UQ episodic simulation."""
    print("\n" + "=" * 80)
    print("ALGORITHM 4: SPC-UQ (Episodic Simulation with Uncertainty)")
    print("Purpose: Reconstruct incomplete episodic memories with confidence bounds")
    print("=" * 80)

    from k0.modules.consolidation.algorithms.spc_uq import (
        EpisodeFragment,
        EpisodicSimulator,
        SPCConfig,
    )

    episodes = create_realistic_episodes()

    print("\n[INPUT] Historical Episodes (for pattern learning)")
    print("-" * 60)
    for ep in episodes:
        print(f"  {ep.activity_type}: {ep.summary[:50]}...")
        print(f"    Participants: {', '.join(ep.participants)}, Location: {ep.location}")

    # Create an incomplete episode to reconstruct
    # SPC-UQ looks for location_name, participants, activity_type, ambiguity_score
    @dataclass
    class IncompleteEpisode:
        episode_id: str
        summary: str
        timestamp: int
        # location_name is None -> triggers LOCATION gap
        location_name: Optional[str] = None
        # participants is None -> triggers PARTICIPANTS gap
        participants: Optional[List[str]] = None
        # activity_type is None -> triggers ACTIVITY gap
        activity_type: Optional[str] = None
        # High ambiguity triggers CONTENT gap
        ambiguity_score: float = 0.7

    incomplete = IncompleteEpisode(
        episode_id="01INCOMPLETE00000000000001",
        summary="Something happened with Sarah in the morning... can't quite remember",
        timestamp=int(datetime.now().timestamp() * 1000),
        # All key fields are None or ambiguous to trigger reconstruction
    )

    print("\n[INPUT] Incomplete Episode (to reconstruct)")
    print("-" * 60)
    print(f"  Episode ID: {incomplete.episode_id}")
    print(f"  Summary: {incomplete.summary}")
    print(f"  Activity Type: {incomplete.activity_type or '??? (MISSING)'}")
    print(f"  Location: {incomplete.location_name or '??? (MISSING)'}")
    print(f"  Participants: {incomplete.participants or '??? (MISSING)'}")
    print(f"  Ambiguity Score: {incomplete.ambiguity_score} (high = uncertain)")

    # Create episode fragments for reconstruction context
    base_time = int(datetime.now().timestamp() * 1000)
    fragments = [
        EpisodeFragment(
            fragment_id="FRAG001",
            source_episode_id=incomplete.episode_id,
            source_event_id="EVT001",
            start_time_ms=base_time - 3600000,  # 1 hour ago
            end_time_ms=base_time - 3000000,
            content="making breakfast",
            attributes=(("activity", "cooking"), ("confidence", 0.8)),
        ),
        EpisodeFragment(
            fragment_id="FRAG002",
            source_episode_id=incomplete.episode_id,
            source_event_id="EVT002",
            start_time_ms=base_time - 3000000,
            end_time_ms=base_time - 2400000,
            content="Sarah mentioned school",
            attributes=(("topic", "school"), ("confidence", 0.7)),
        ),
    ]

    print("\n[INPUT] Episode Fragments (memory traces)")
    print("-" * 60)
    for frag in fragments:
        print(f"  [{frag.fragment_id}] {frag.content}")
        print(f"    source_event: {frag.source_event_id}")

    config = SPCConfig(simulation_count=50, min_confidence=0.3, coherence_threshold=0.4, seed=42)

    simulator = EpisodicSimulator(config=config)

    # Context with nearby_locations and frequent_contacts for reconstruction
    context = {
        "time_of_day": "morning",
        "day": "weekday",
        "nearby_locations": ["home_kitchen", "home_study", "school"],
        "known_locations": ["home_kitchen", "home_study", "school", "office"],
        "frequent_contacts": ["Sarah", "Tommy", "spouse"],
    }

    print("\n[PROCESSING] Running episodic simulation")
    print("-" * 60)
    print(f"  Simulation count: {config.simulation_count}")
    print(f"  Min confidence threshold: {config.min_confidence}")
    print(f"  Coherence threshold: {config.coherence_threshold}")
    print(f"  Context: {list(context.keys())}")

    reconstructions = simulator.simulate(
        episodes=[incomplete],
        fragments=fragments,
        schemas=None,  # No schema patterns for this demo
        context=context,
        rng_seed=42,
    )

    print("\n[OUTPUT] Reconstructed Episodes")
    print("-" * 60)
    if reconstructions:
        for i, recon in enumerate(reconstructions, 1):
            print(f"\n  Reconstruction #{i}:")
            print(f"    New Episode ID: {recon.episode_id}")
            print(f"    Original ID: {recon.original_episode_id}")
            print(f"    Summary: {recon.summary}")
            print(f"    Confidence Score: {recon.confidence_score:.4f}")
            print(f"    Uncertainty Score: {recon.uncertainty_score:.4f}")
            print(f"    Temporal Coherence: {recon.temporal_coherence_score:.4f}")
            print(f"    Is Canonical: {recon.is_canonical} (always False for reconstructions)")

            if recon.reconstructed_fields:
                print("    Reconstructed Fields:")
                for field in recon.reconstructed_fields:
                    print(f"      - {field.attribute_name}: {field.value}")
                    print(f"        Confidence: {field.confidence:.4f}")
                    print(f"        Uncertainty: {field.uncertainty:.4f}")
                    print(f"        Provenance: {field.provenance}")
    else:
        print("  (No reconstructions generated - episode may be complete or confidence too low)")
        print("  SPC-UQ only reconstructs episodes with identified gaps")

    # ─────────────────────────────────────────────────────────────────────────
    # VERIFICATION FOOTER
    # ─────────────────────────────────────────────────────────────────────────
    print("\n[VERIFICATION] SPC-UQ Algorithm Metrics")
    print("-" * 60)

    # Collect verification stats
    recon_count = len(reconstructions) if reconstructions else 0
    fragments_count = len(fragments)
    simulations_requested = config.simulation_count

    # Reconstructed field analysis
    all_fields = []
    fields_by_type = {}
    provenance_types = set()

    if reconstructions:
        for recon in reconstructions:
            if recon.reconstructed_fields:
                for field in recon.reconstructed_fields:
                    all_fields.append(field)
                    attr_name = field.attribute_name
                    if attr_name not in fields_by_type:
                        fields_by_type[attr_name] = []
                    fields_by_type[attr_name].append(
                        {
                            "value": field.value,
                            "confidence": field.confidence,
                            "provenance": field.provenance,
                        }
                    )
                    provenance_types.add(field.provenance)

    # Confidence analysis
    confidences = [f.confidence for f in all_fields]
    confidence_unique = set(round(c, 4) for c in confidences)

    # Uncertainty analysis
    uncertainties = [f.uncertainty for f in all_fields]
    uncertainty_unique = set(round(u, 4) for u in uncertainties)

    print(f"  simulations_requested: {simulations_requested}")
    print(f"  reconstructions_returned: {recon_count}")
    print(f"  fragments_used: {fragments_count}")
    print(f"  total_fields_reconstructed: {len(all_fields)}")
    print(f"  provenance_types_used: {provenance_types}")
    print(f"  confidence_unique_values: {confidence_unique}")
    print(f"  uncertainty_unique_values: {uncertainty_unique}")

    # Per-field breakdown
    if fields_by_type:
        print("  per_field_breakdown:")
        for attr_name, field_list in fields_by_type.items():
            for field in field_list:
                print(
                    f"    {attr_name}: value={field['value']!r}, conf={field['confidence']:.4f}, prov={field['provenance']}"
                )

    # Warnings
    warnings = []
    if recon_count == 0:
        warnings.append("No reconstructions - check gap identification or confidence thresholds")
    if len(provenance_types) == 1 and recon_count > 0:
        warnings.append(
            f"Only one provenance type ({next(iter(provenance_types))}) - all fields from same source"
        )
    if len(confidence_unique) == 1 and len(all_fields) > 2:
        warnings.append(
            f"Constant confidence={next(iter(confidence_unique))} - check scoring function"
        )
    if fragments_count == 0:
        warnings.append("No fragments provided - reconstruction based only on context")

    if warnings:
        print("  WARNINGS:")
        for w in warnings:
            print(f"    - {w}")
    else:
        print("  STATUS: OK - field reconstruction with varied provenance")

    return reconstructions


# ─────────────────────────────────────────────────────────────────────────────
# Main demonstration
# ─────────────────────────────────────────────────────────────────────────────


def export_to_markdown(results: Dict[str, Any], errors: Dict[str, str]) -> str:
    """Export all results to markdown format."""
    md = StringIO()

    md.write("# R5 Dream Phase Algorithms - Full I/O Results\n\n")
    md.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    md.write("---\n\n")

    # Summary table
    md.write("## Summary\n\n")
    md.write("| Algorithm | Status | Outputs |\n")
    md.write("|-----------|--------|--------:|\n")

    for name in ["CPN", "MCTS", "BGT-SM", "SPC-UQ"]:
        if name in errors:
            md.write(f"| {name} | ❌ FAIL | Error |\n")
        elif results.get(name):
            count = len(results[name]) if hasattr(results[name], "__len__") else 1
            md.write(f"| {name} | ✅ OK | {count} |\n")
        else:
            md.write(f"| {name} | ⚠️ WARN | 0 |\n")

    md.write("\n---\n\n")

    # CPN Results
    md.write("## 1. CPN (Causal Perturbation Network)\n\n")
    md.write("**Purpose:** Generate 'what-if' counterfactual scenarios from regretful events\n\n")

    if "CPN" in errors:
        md.write(f"**Error:** {errors['CPN']}\n\n")
    elif results.get("CPN"):
        md.write(f"**Total Counterfactuals Generated:** {len(results['CPN'])}\n\n")

        # Group by scenario type
        by_type = {}
        for cf in results["CPN"]:
            stype = str(cf.scenario_type).replace("ScenarioType.", "")
            if stype not in by_type:
                by_type[stype] = []
            by_type[stype].append(cf)

        for stype, cfs in by_type.items():
            md.write(f"### {stype} Scenarios ({len(cfs)})\n\n")

            for i, cf in enumerate(cfs, 1):
                md.write(f"#### Counterfactual {i}\n\n")
                md.write(f"- **Base Episode ID:** `{cf.base_episode_id}`\n")
                md.write(f"- **Scenario ID:** `{cf.scenario_id}`\n")
                md.write(f"- **Intervention Node:** `{cf.intervention_node_id}`\n")
                md.write(f"- **Perturbation Target:** `{cf.perturbation_target}`\n")
                md.write(f"- **Original Outcome:** {cf.original_outcome}\n")
                md.write(f"- **Counterfactual Outcome:** {cf.counterfactual_outcome}\n")
                md.write(f"- **Original Sentiment:** {cf.original_sentiment:+.4f}\n")
                md.write(f"- **Predicted Sentiment:** {cf.predicted_sentiment:+.4f}\n")
                md.write(f"- **Plausibility:** {cf.plausibility:.4f}\n")
                md.write(f"- **Success Probability:** {cf.success_probability:.4f}\n")
                md.write(f"- **Utility Delta:** {cf.utility_delta:+.4f}\n")
                md.write(f"- **Causal Path Length:** {cf.causal_path_length}\n")
                if cf.mitigation:
                    md.write(f"- **Mitigation:** {cf.mitigation}\n")
                md.write("\n")
    else:
        md.write("*No counterfactuals generated*\n\n")

    md.write("---\n\n")

    # MCTS Results
    md.write("## 2. TPN-MCTS (Temporal Projection MCTS)\n\n")
    md.write("**Purpose:** Simulate future scenarios via Monte Carlo tree search\n\n")

    if "MCTS" in errors:
        md.write(f"**Error:** {errors['MCTS']}\n\n")
    elif results.get("MCTS"):
        md.write(f"**Total Scenarios Generated:** {len(results['MCTS'])}\n\n")

        for i, scenario in enumerate(results["MCTS"], 1):
            md.write(f"### Scenario {i}\n\n")
            md.write(f"- **Scenario ID:** `{scenario.scenario_id}`\n")
            md.write(f"- **Expected Reward:** {scenario.expected_reward:.6f}\n")
            md.write(f"- **Visit Count:** {scenario.visit_count}\n")
            md.write(f"- **Success Probability:** {scenario.success_probability:.6f}\n")
            md.write(f"- **Plausibility:** {scenario.plausibility:.6f}\n")
            if scenario.action_sequence:
                md.write(f"- **Action Sequence:** `{scenario.action_sequence}`\n")
            md.write("\n")
    else:
        md.write("*No scenarios generated*\n\n")

    md.write("---\n\n")

    # BGT-SM Results
    md.write("## 3. BGT-SM (Bisociative Graph Traversal)\n\n")
    md.write("**Purpose:** Discover unexpected connections between distant concepts\n\n")

    if "BGT-SM" in errors:
        md.write(f"**Error:** {errors['BGT-SM']}\n\n")
    elif results.get("BGT-SM"):
        md.write(f"**Total Insights Discovered:** {len(results['BGT-SM'])}\n\n")

        md.write("| # | Source | Target | Novelty | PMI | Semantic Distance |\n")
        md.write("|--:|--------|--------|--------:|----:|------------------:|\n")

        for i, insight in enumerate(results["BGT-SM"], 1):
            md.write(f"| {i} | {insight.source_entity_id} | {insight.target_entity_id} | ")
            md.write(
                f"{insight.novelty_score:.4f} | {insight.pmi_score:.4f} | {insight.semantic_distance:.4f} |\n"
            )

        md.write("\n### Detailed Insights\n\n")
        for i, insight in enumerate(results["BGT-SM"], 1):
            md.write(f"#### Insight {i}\n\n")
            md.write(f"- **Source Entity:** `{insight.source_entity_id}`\n")
            md.write(f"- **Target Entity:** `{insight.target_entity_id}`\n")
            md.write(f"- **Insight Text:** {insight.insight_text}\n")
            md.write(f"- **Novelty Score:** {insight.novelty_score:.6f}\n")
            md.write(f"- **PMI Score:** {insight.pmi_score:.6f}\n")
            md.write(f"- **Semantic Distance:** {insight.semantic_distance:.6f}\n")
            md.write("\n")
    else:
        md.write("*No insights discovered*\n\n")

    md.write("---\n\n")

    # SPC-UQ Results
    md.write("## 4. SPC-UQ (Episodic Simulation with Uncertainty)\n\n")
    md.write("**Purpose:** Reconstruct incomplete episodic memories with confidence bounds\n\n")
    md.write("**Note:** All reconstructions are NON-CANONICAL (never treated as ground truth)\n\n")

    if "SPC-UQ" in errors:
        md.write(f"**Error:** {errors['SPC-UQ']}\n\n")
    elif results.get("SPC-UQ"):
        md.write(f"**Total Reconstructions:** {len(results['SPC-UQ'])}\n\n")

        for i, recon in enumerate(results["SPC-UQ"], 1):
            md.write(f"### Reconstruction {i}\n\n")
            md.write(f"- **New Episode ID:** `{recon.episode_id}`\n")
            md.write(f"- **Original Episode ID:** `{recon.original_episode_id}`\n")
            md.write(f"- **Summary:** {recon.summary}\n")
            md.write(f"- **Confidence Score:** {recon.confidence_score:.6f}\n")
            md.write(f"- **Uncertainty Score:** {recon.uncertainty_score:.6f}\n")
            md.write(f"- **Temporal Coherence:** {recon.temporal_coherence_score:.6f}\n")
            md.write(f"- **Is Canonical:** {recon.is_canonical}\n")

            if recon.reconstructed_fields:
                md.write("\n**Reconstructed Fields:**\n\n")
                md.write("| Attribute | Value | Confidence | Uncertainty | Provenance |\n")
                md.write("|-----------|-------|----------:|------------:|------------|\n")
                for field in recon.reconstructed_fields:
                    prov = str(field.provenance).replace("ReconstructionProvenance.", "")
                    md.write(f"| {field.attribute_name} | {field.value} | ")
                    md.write(f"{field.confidence:.4f} | {field.uncertainty:.4f} | {prov} |\n")
            md.write("\n")
    else:
        md.write("*No reconstructions generated*\n\n")

    md.write("---\n\n")

    # Interpretation guide
    md.write("## Interpretation Guide\n\n")
    md.write("### CPN (Counterfactual)\n")
    md.write('- Generates "what-if" scenarios from emotionally charged events\n')
    md.write("- **UPWARD:** What if you had acted differently? (includes mitigation)\n")
    md.write("- **DOWNWARD:** What if things had gotten worse?\n")
    md.write("- **SEMIFACTUAL:** Would outcome have changed anyway?\n")
    md.write("- Requires causal edges (CAUSES relationships) to build DAGs\n\n")

    md.write("### MCTS (Forward Simulation)\n")
    md.write("- Projects future scenarios using Monte Carlo tree search\n")
    md.write("- Uses UCT selection with exploration constant c=√2\n")
    md.write("- Higher expected reward = better predicted outcome\n\n")

    md.write("### BGT-SM (Insight Generation)\n")
    md.write("- Finds surprising connections via random walks on knowledge graph\n")
    md.write("- Uses PMI (Pointwise Mutual Information) for surprise scoring\n")
    md.write("- Higher novelty = more unexpected connection\n\n")

    md.write("### SPC-UQ (Episodic Reconstruction)\n")
    md.write("- Fills gaps in incomplete memories using pattern completion\n")
    md.write("- All reconstructions are NON-CANONICAL (never treated as ground truth)\n")
    md.write("- Lower uncertainty = higher confidence in reconstruction\n")

    return md.getvalue()


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="R5 Dream Phase algorithm demonstration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--pack",
        type=str,
        default=None,
        help="Use scenario pack from factory (e.g., 'toy', 'causal_deep')",
    )
    parser.add_argument(
        "--ultrabert",
        action="store_true",
        help="Use UltraBERT embeddings (768-dim) instead of clustered (64-dim)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Export results to markdown file",
    )
    parser.add_argument(
        "--list-packs",
        action="store_true",
        help="List available scenario packs and exit",
    )
    return parser.parse_args()


def main():
    """Run all algorithm demonstrations and export to markdown."""
    global _ACTIVE_WORLD

    args = parse_args()

    # Handle --list-packs
    if args.list_packs:
        try:
            from .r5_data_factory import list_packs

            packs = list_packs()
            print("Available scenario packs:")
            for p in packs:
                print(f"  - {p}")
        except Exception as e:
            print(f"Error listing packs: {e}")
        return {}

    # Load pack if specified
    if args.pack:
        try:
            from .r5_data_factory import make_world

            print(f"\n[PACK] Loading world from pack: {args.pack}")
            _ACTIVE_WORLD = make_world(
                pack=args.pack,
                seed=args.seed,
                use_ultrabert=args.ultrabert if args.ultrabert else None,
            )
            summary = _ACTIVE_WORLD.summary()
            print(f"[PACK] World loaded: {summary}")
        except Exception as e:
            print(f"[ERROR] Failed to load pack '{args.pack}': {e}")
            import traceback

            traceback.print_exc()
            return {}

    print("\n" + "#" * 80)
    print("#" + " " * 22 + "R5 DREAM PHASE ALGORITHMS DEMO" + " " * 25 + "#")
    print("#" + " " * 18 + "Real Inputs -> Real Outputs Demonstration" + " " * 17 + "#")
    print("#" * 80)

    if _ACTIVE_WORLD:
        print(f"\n[MODE] Using pack: {_ACTIVE_WORLD.pack_name} (seed={_ACTIVE_WORLD.seed})")
        emb_dim = len(next(iter(_ACTIVE_WORLD.embeddings.values()), []))
        print(f"[MODE] Embedding dimension: {emb_dim}")

    results = {}
    errors = {}

    # Demo each algorithm with error handling
    algorithms = [
        ("CPN", demo_cpn),
        ("MCTS", demo_mcts),
        ("BGT-SM", demo_bgt),
        ("SPC-UQ", demo_spc_uq),
    ]

    for name, demo_fn in algorithms:
        try:
            results[name] = demo_fn()
        except Exception as e:
            import traceback

            print(f"\n[ERROR] {name}: {e}")
            errors[name] = str(e)
            traceback.print_exc()
            results[name] = None

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY: Algorithm Execution Results")
    print("=" * 80)

    for name, _ in algorithms:
        if name in errors:
            print(f"  [FAIL] {name}: Error - {errors[name]}")
        elif results.get(name):
            count = len(results[name]) if hasattr(results[name], "__len__") else 1
            print(f"  [OK] {name}: Produced {count} output(s)")
        else:
            print(f"  [WARN] {name}: No outputs (check algorithm conditions)")

    # Export to markdown
    if args.export:
        print("\n" + "=" * 80)
        print("EXPORTING TO MARKDOWN")
        print("=" * 80)

        md_content = export_to_markdown(results, errors)

        # Write to file
        script_dir = os.path.dirname(os.path.abspath(__file__))
        md_path = os.path.join(script_dir, "r5_algorithm_results.md")

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        print(f"\n  Markdown exported to: {md_path}")
        print(f"  File size: {len(md_content):,} bytes")
    else:
        print("\n  (Use --export to save markdown file)")

    # Also print interpretation guide
    print("\n" + "=" * 80)
    print("INTERPRETATION GUIDE")
    print("=" * 80)
    print(
        """
  CPN (Counterfactual):
    - Generates "what-if" scenarios from emotionally charged events
    - UPWARD: What if you had acted differently? (includes mitigation)
    - DOWNWARD: What if things had gotten worse?
    - SEMIFACTUAL: Would outcome have changed anyway?

  MCTS (Forward Simulation):
    - Projects future scenarios using Monte Carlo tree search
    - Uses UCT selection with exploration constant c=sqrt(2)
    - Outputs: scenario_id, expected_reward, visit_count, plausibility

  BGT-SM (Insight Generation):
    - Finds surprising connections via random walks on knowledge graph
    - Uses PMI (Pointwise Mutual Information) for surprise scoring
    - Outputs: insight_text, novelty_score, pmi_score, semantic_distance

  SPC-UQ (Episodic Reconstruction):
    - Fills gaps in incomplete memories using pattern completion
    - All reconstructions are NON-CANONICAL (never treated as ground truth)
    - Outputs: reconstructed_fields, confidence_score, uncertainty_score
    """
    )

    return results


if __name__ == "__main__":
    main()
