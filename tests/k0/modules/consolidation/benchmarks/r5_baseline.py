"""Baseline comparison framework for R5 benchmarks.

Provides naive baseline implementations for comparing algorithm performance:
- Random baselines (no intelligence)
- Greedy baselines (myopic optimization)
- Nearest neighbor baselines (simple heuristics)

Used to demonstrate that algorithms outperform trivial approaches.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Baseline Result Dataclasses
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class BaselineCounterfactual:
    """Random counterfactual for CPN baseline."""

    scenario_id: str
    base_episode_id: str
    intervention_node: str
    predicted_sentiment: float
    plausibility: float
    causal_path_length: int = 0
    scenario_type: str = "RANDOM"


@dataclass
class BaselineScenario:
    """Random/greedy scenario for MCTS baseline."""

    scenario_id: str
    action_sequence: Tuple[str, ...]
    expected_reward: float
    visit_count: int = 1
    plausibility: float = 1.0


@dataclass
class BaselineInsight:
    """Random/nearest neighbor insight for BGT baseline."""

    entity_a: str
    entity_b: str
    pmi_score: float
    semantic_distance: float
    novelty_score: float
    insight_text: str
    is_spurious: bool = False


@dataclass
class BaselineReconstruction:
    """Mode imputation reconstruction for SPC baseline."""

    episode_id: str
    reconstructed_fields: Dict[str, Any]
    confidence_score: float
    uncertainty_score: float


@dataclass
class BaselineComparison:
    """Comparison result between algorithm and baseline."""

    algorithm: str
    baseline_name: str
    algorithm_score: float
    baseline_score: float
    improvement: float  # Percentage improvement
    metric_name: str
    is_better: bool

    def __str__(self) -> str:
        direction = "↑" if self.improvement > 0 else "↓"
        return (
            f"{self.algorithm} vs {self.baseline_name} ({self.metric_name}): "
            f"{self.algorithm_score:.3f} vs {self.baseline_score:.3f} "
            f"({direction}{abs(self.improvement):.1%})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Baseline Comparator
# ─────────────────────────────────────────────────────────────────────────────


class BaselineComparator:
    """Compare algorithm outputs against simple baselines."""

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.np_rng = np.random.default_rng(seed)

    # ─────────────────────────────────────────────────────────────────────────
    # CPN Baselines
    # ─────────────────────────────────────────────────────────────────────────

    def random_counterfactual(
        self,
        episodes: List[Any],
        kg_edges: List[Any],
        n_counterfactuals: int = 10,
    ) -> List[BaselineCounterfactual]:
        """Generate random counterfactuals without causal reasoning.

        Randomly perturbs episode entities without following causal paths.

        Args:
            episodes: List of episode objects.
            kg_edges: List of causal edge objects (ignored in random baseline).
            n_counterfactuals: Number of counterfactuals to generate.

        Returns:
            List of random BaselineCounterfactual objects.
        """
        counterfactuals = []

        # Collect all entity IDs from episodes
        all_entities = set()
        for ep in episodes:
            if hasattr(ep, "entity_ids"):
                all_entities.update(ep.entity_ids)
            elif isinstance(ep, dict) and "entity_ids" in ep:
                all_entities.update(ep["entity_ids"])

        entity_list = list(all_entities) if all_entities else ["UNKNOWN"]

        for i in range(n_counterfactuals):
            # Pick random episode
            ep = self.rng.choice(episodes) if episodes else None
            ep_id = ""
            if ep:
                ep_id = ep.episode_id if hasattr(ep, "episode_id") else ep.get("id", "")

            # Random intervention
            intervention = self.rng.choice(entity_list)

            cf = BaselineCounterfactual(
                scenario_id=f"rand_cf_{i:03d}",
                base_episode_id=ep_id,
                intervention_node=intervention,
                predicted_sentiment=self.rng.uniform(-1, 1),
                plausibility=self.rng.uniform(0, 1),
                causal_path_length=0,  # Random baseline has no causal reasoning
                scenario_type="RANDOM",
            )
            counterfactuals.append(cf)

        return counterfactuals

    # ─────────────────────────────────────────────────────────────────────────
    # MCTS Baselines
    # ─────────────────────────────────────────────────────────────────────────

    def greedy_action_selection(
        self,
        state: Dict[str, Any],
        actions: List[Any],
        n_scenarios: int = 5,
        max_depth: int = 3,
    ) -> List[BaselineScenario]:
        """Select actions greedily by immediate reward.

        Always picks the highest immediate reward action without lookahead.

        Args:
            state: Initial state dict.
            actions: List of available action objects.
            n_scenarios: Number of greedy rollouts.
            max_depth: Maximum actions per scenario.

        Returns:
            List of greedy BaselineScenario objects.
        """
        scenarios = []

        if not actions:
            return scenarios

        # Sort actions by expected reward (descending)
        def get_reward(action) -> float:
            if hasattr(action, "expected_reward"):
                return action.expected_reward
            elif hasattr(action, "goal_alignment"):
                return action.goal_alignment
            elif isinstance(action, dict):
                return action.get("expected_reward", action.get("goal_alignment", 0.0))
            return 0.0

        sorted_actions = sorted(actions, key=get_reward, reverse=True)

        for i in range(min(n_scenarios, len(sorted_actions))):
            # Greedy: always pick top remaining action
            action = sorted_actions[i % len(sorted_actions)]
            action_id = (
                action.action_id
                if hasattr(action, "action_id")
                else action.get("action_id", f"ACT{i}")
            )

            scenario = BaselineScenario(
                scenario_id=f"greedy_{i:03d}",
                action_sequence=(action_id,),
                expected_reward=get_reward(action),
                visit_count=1,
                plausibility=0.9,
            )
            scenarios.append(scenario)

        return scenarios

    def random_action_selection(
        self,
        state: Dict[str, Any],
        actions: List[Any],
        n_scenarios: int = 10,
        max_depth: int = 3,
    ) -> List[BaselineScenario]:
        """Select actions randomly.

        Args:
            state: Initial state dict.
            actions: List of available action objects.
            n_scenarios: Number of random rollouts.
            max_depth: Maximum actions per scenario.

        Returns:
            List of random BaselineScenario objects.
        """
        scenarios = []

        if not actions:
            return scenarios

        def get_action_id(action) -> str:
            if hasattr(action, "action_id"):
                return action.action_id
            elif isinstance(action, dict):
                return action.get("action_id", "UNKNOWN")
            return "UNKNOWN"

        def get_reward(action) -> float:
            if hasattr(action, "expected_reward"):
                return action.expected_reward
            elif hasattr(action, "goal_alignment"):
                return action.goal_alignment
            elif isinstance(action, dict):
                return action.get("expected_reward", action.get("goal_alignment", 0.0))
            return 0.0

        for i in range(n_scenarios):
            # Random action sequence
            depth = self.rng.randint(1, max_depth)
            sequence = tuple(
                get_action_id(self.rng.choice(actions)) for _ in range(depth)
            )

            # Sum rewards (simplified)
            total_reward = sum(
                get_reward(a) for a in actions if get_action_id(a) in sequence
            ) / len(sequence)

            scenario = BaselineScenario(
                scenario_id=f"rand_{i:03d}",
                action_sequence=sequence,
                expected_reward=total_reward,
                visit_count=1,
                plausibility=0.5,
            )
            scenarios.append(scenario)

        return scenarios

    # ─────────────────────────────────────────────────────────────────────────
    # BGT-SM Baselines
    # ─────────────────────────────────────────────────────────────────────────

    def random_walk_no_pmi(
        self,
        entities: List[Any],
        edges: List[Any],
        n_insights: int = 5,
    ) -> List[BaselineInsight]:
        """Generate random insights without PMI filtering.

        Args:
            entities: List of entity objects.
            edges: List of edge objects.
            n_insights: Number of insights to generate.

        Returns:
            List of random BaselineInsight objects.
        """
        insights = []

        if len(entities) < 2:
            return insights

        def get_entity_id(entity) -> str:
            if hasattr(entity, "entity_id"):
                return entity.entity_id
            elif isinstance(entity, dict):
                return entity.get("entity_id", entity.get("id", "UNKNOWN"))
            return "UNKNOWN"

        def get_entity_name(entity) -> str:
            if hasattr(entity, "name"):
                return entity.name
            elif isinstance(entity, dict):
                return entity.get("name", "Unknown")
            return "Unknown"

        entity_ids = [get_entity_id(e) for e in entities]
        entity_names = {get_entity_id(e): get_entity_name(e) for e in entities}

        for i in range(n_insights):
            # Pick two random entities
            a, b = self.rng.sample(entity_ids, 2)

            insight = BaselineInsight(
                entity_a=a,
                entity_b=b,
                pmi_score=self.rng.uniform(0, 5),  # Random PMI
                semantic_distance=self.rng.uniform(0, 1),
                novelty_score=self.rng.uniform(0, 1),
                insight_text=f"Random connection between '{entity_names.get(a, a)}' and '{entity_names.get(b, b)}'",
                is_spurious=self.rng.random() > 0.5,  # 50% are spurious
            )
            insights.append(insight)

        return insights

    def nearest_neighbor(
        self,
        seed_entity: str,
        embeddings: Dict[str, List[float]],
        n_neighbors: int = 5,
    ) -> List[BaselineInsight]:
        """Return semantically closest entities as insights.

        Args:
            seed_entity: Entity ID to find neighbors for.
            embeddings: Dict mapping entity_id to embedding vector.
            n_neighbors: Number of nearest neighbors.

        Returns:
            List of nearest-neighbor BaselineInsight objects.
        """
        insights = []

        if seed_entity not in embeddings:
            return insights

        seed_emb = np.array(embeddings[seed_entity])

        # Compute distances to all other entities
        distances = []
        for entity_id, emb in embeddings.items():
            if entity_id == seed_entity:
                continue
            emb_arr = np.array(emb)
            # Cosine distance
            dot = np.dot(seed_emb, emb_arr)
            norm = np.linalg.norm(seed_emb) * np.linalg.norm(emb_arr)
            cos_sim = dot / norm if norm > 0 else 0
            cos_dist = 1 - cos_sim
            distances.append((entity_id, cos_dist))

        # Sort by distance (ascending = most similar first)
        distances.sort(key=lambda x: x[1])

        for entity_id, dist in distances[:n_neighbors]:
            insight = BaselineInsight(
                entity_a=seed_entity,
                entity_b=entity_id,
                pmi_score=0.0,  # No PMI in nearest neighbor
                semantic_distance=dist,
                novelty_score=1 - dist,  # Closer = less novel
                insight_text=f"Nearest neighbor: {seed_entity} <-> {entity_id} (dist={dist:.3f})",
                is_spurious=dist < 0.2,  # Too close = likely spurious (trivial)
            )
            insights.append(insight)

        return insights

    # ─────────────────────────────────────────────────────────────────────────
    # SPC-UQ Baselines
    # ─────────────────────────────────────────────────────────────────────────

    def mode_imputation(
        self,
        fragments: List[Any],
        incomplete_episodes: Optional[List[Any]] = None,
    ) -> List[BaselineReconstruction]:
        """Fill gaps with most common values (mode imputation).

        Args:
            fragments: List of fragment objects.
            incomplete_episodes: List of incomplete episode objects.

        Returns:
            List of mode-imputed BaselineReconstruction objects.
        """
        reconstructions = []

        if not incomplete_episodes:
            return reconstructions

        # Collect all values for mode calculation
        locations = []
        participants = []
        activity_types = []

        for frag in fragments:
            if hasattr(frag, "entities_mentioned"):
                participants.extend(frag.entities_mentioned)
            elif isinstance(frag, dict) and "entities_mentioned" in frag:
                participants.extend(frag["entities_mentioned"])

        # Find modes
        def mode(values: List[str]) -> str:
            if not values:
                return "unknown"
            from collections import Counter
            counts = Counter(values)
            return counts.most_common(1)[0][0]

        mode_participant = mode(participants) if participants else "self"

        for ep in incomplete_episodes:
            ep_id = ep.episode_id if hasattr(ep, "episode_id") else ep.get("id", "UNKNOWN")

            recon = BaselineReconstruction(
                episode_id=ep_id,
                reconstructed_fields={
                    "location_name": {"value": "home", "confidence": 0.3},
                    "participants": {"value": [mode_participant], "confidence": 0.3},
                },
                confidence_score=0.3,  # Low confidence for mode imputation
                uncertainty_score=0.7,
            )
            reconstructions.append(recon)

        return reconstructions


# ─────────────────────────────────────────────────────────────────────────────
# Comparison Functions
# ─────────────────────────────────────────────────────────────────────────────


def compare_to_baselines(
    algorithm_results: Dict[str, Any],
    baseline_results: Dict[str, Any],
    metrics_config: Optional[Dict[str, Dict[str, bool]]] = None,
) -> Dict[str, List[BaselineComparison]]:
    """Compute improvement metrics vs baselines.

    Args:
        algorithm_results: Dict with algorithm outputs keyed by algorithm name.
        baseline_results: Dict with baseline outputs keyed by baseline name.
        metrics_config: Dict mapping metric names to {higher_is_better: bool}.

    Returns:
        Dict mapping algorithm names to list of BaselineComparison.
    """
    default_config = {
        # CPN metrics
        "plausibility_mean": {"higher_is_better": True},
        "max_path_length": {"higher_is_better": True},
        "total_counterfactuals": {"higher_is_better": True},
        # MCTS metrics
        "reward_mean": {"higher_is_better": True},
        "budget_consumption_ratio": {"higher_is_better": True},
        # BGT metrics
        "novelty_mean": {"higher_is_better": True},
        "pmi_mean": {"higher_is_better": True},
        "false_positive_rate": {"higher_is_better": False},
        # SPC metrics
        "confidence_mean": {"higher_is_better": True},
        "uncertainty_mean": {"higher_is_better": False},  # Lower uncertainty is better
    }
    metrics_config = metrics_config or default_config

    comparisons: Dict[str, List[BaselineComparison]] = {}

    for algo_name, algo_metrics in algorithm_results.items():
        comparisons[algo_name] = []

        for baseline_name, baseline_metrics in baseline_results.items():
            if not baseline_name.startswith(algo_name.split("-")[0].lower()):
                continue  # Skip unrelated baselines

            for metric_name, config in metrics_config.items():
                if metric_name not in algo_metrics or metric_name not in baseline_metrics:
                    continue

                algo_score = algo_metrics[metric_name]
                baseline_score = baseline_metrics[metric_name]

                if baseline_score == 0:
                    improvement = float("inf") if algo_score > 0 else 0.0
                else:
                    improvement = (algo_score - baseline_score) / abs(baseline_score)

                higher_is_better = config.get("higher_is_better", True)
                is_better = (
                    (improvement > 0) if higher_is_better else (improvement < 0)
                )

                comparisons[algo_name].append(
                    BaselineComparison(
                        algorithm=algo_name,
                        baseline_name=baseline_name,
                        algorithm_score=algo_score,
                        baseline_score=baseline_score,
                        improvement=improvement,
                        metric_name=metric_name,
                        is_better=is_better,
                    )
                )

    return comparisons


def run_all_baselines(
    comparator: BaselineComparator,
    episodes: List[Any],
    kg_edges: List[Any],
    entities: List[Any],
    semantic_edges: List[Any],
    embeddings: Dict[str, List[float]],
    state: Dict[str, Any],
    actions: List[Any],
    fragments: List[Any],
    incomplete_episodes: List[Any],
) -> Dict[str, Any]:
    """Run all baseline algorithms and return their outputs.

    Args:
        comparator: BaselineComparator instance.
        episodes: Episode objects.
        kg_edges: Causal edge objects.
        entities: Entity objects.
        semantic_edges: Semantic edge objects.
        embeddings: Entity embeddings.
        state: MCTS initial state.
        actions: MCTS actions.
        fragments: SPC fragments.
        incomplete_episodes: SPC incomplete episodes.

    Returns:
        Dict with baseline outputs for each algorithm.
    """
    return {
        "cpn_random": comparator.random_counterfactual(episodes, kg_edges),
        "mcts_greedy": comparator.greedy_action_selection(state, actions),
        "mcts_random": comparator.random_action_selection(state, actions),
        "bgt_random": comparator.random_walk_no_pmi(entities, semantic_edges),
        "spc_mode": comparator.mode_imputation(fragments, incomplete_episodes),
    }
