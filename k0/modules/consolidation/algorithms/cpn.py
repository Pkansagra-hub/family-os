"""
CPN — Causal Perturbation Network for Counterfactual Generation.

This module implements the CPN algorithm for R5 dream exploration,
generating "what if" scenarios by perturbing past events.

Algorithm Flow:
1. Select emotionally significant episodes (regret potential)
2. Extract causal chains from knowledge graph (CAUSES edges)
3. Identify modifiable nodes (actor-controllable actions)
4. Perturb nodes to generate UPWARD/DOWNWARD/SEMIFACTUAL scenarios
5. Evaluate plausibility and utility changes
6. Return ranked counterfactual scenarios

References:
- M8_EXECUTION.md Issue 8.1.4: CPN counterfactual generation
- Dossier §4.6.1: Counterfactual Thinking (CPN Algorithm)
- Dossier Appendix C.6.1: Causal Perturbation Network (CPN)

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import logging
import math
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, Set, Tuple, runtime_checkable

logger = logging.getLogger(__name__)


# =============================================================================
# TYPES AND ENUMS
# =============================================================================


class ScenarioType(str, Enum):
    """Types of counterfactual scenarios."""

    UPWARD = "UPWARD"  # Better outcome: "What if I had...?"
    DOWNWARD = "DOWNWARD"  # Worse outcome: "What if I also...?"
    SEMIFACTUAL = "SEMIFACTUAL"  # Same outcome: "Even if I had...?"


class NodeModifiability(str, Enum):
    """Whether a causal node is actor-controllable."""

    MODIFIABLE = "MODIFIABLE"  # Actor could have changed (left early)
    EXTERNAL = "EXTERNAL"  # Outside control (meeting ran long)


# =============================================================================
# CONFIGURATION
# =============================================================================


@dataclass(frozen=True)
class CPNConfig:
    """
    Configuration for Causal Perturbation Network.

    Attributes:
        emotional_threshold: Min |sentiment| for regret event selection (default: 0.3)
        top_k_regret_events: Number of events to analyze (default: 10)
        causal_chain_depth: Max hops in causal graph (default: 5)
        perturbation_std: Gaussian perturbation std (default: 0.1)
        min_plausibility: Min plausibility to keep scenario (default: 0.3)
        min_utility_delta: Min utility change for UPWARD/DOWNWARD (default: 0.3)
        counterfactual_types: Scenario types to generate (default: all three)
        seed: RNG seed for determinism (default: None)
    """

    emotional_threshold: float = 0.3  # GAP-001 M9.3: lowered from 0.6 for family events
    top_k_regret_events: int = 10
    causal_chain_depth: int = 5
    perturbation_std: float = 0.1
    min_plausibility: float = 0.3
    min_utility_delta: float = 0.3
    counterfactual_types: Tuple[str, ...] = ("UPWARD", "DOWNWARD", "SEMIFACTUAL")
    seed: Optional[int] = None

    def __post_init__(self) -> None:
        """Validate configuration."""
        if not 0.0 <= self.emotional_threshold <= 1.0:
            raise ValueError("emotional_threshold must be between 0 and 1")
        if self.top_k_regret_events < 1:
            raise ValueError("top_k_regret_events must be at least 1")
        if self.causal_chain_depth < 1:
            raise ValueError("causal_chain_depth must be at least 1")
        if self.perturbation_std <= 0:
            raise ValueError("perturbation_std must be positive")
        if not 0.0 <= self.min_plausibility <= 1.0:
            raise ValueError("min_plausibility must be between 0 and 1")


# =============================================================================
# PROTOCOLS (for dependency injection)
# =============================================================================


@runtime_checkable
class EpisodeProtocol(Protocol):
    """Protocol for episodic memory data."""

    @property
    def episode_id(self) -> str:
        """Unique episode identifier."""
        ...

    @property
    def sentiment_score(self) -> float:
        """Sentiment score (-1 to 1)."""
        ...

    @property
    def salience_score(self) -> float:
        """Importance/salience score (0 to 1)."""
        ...

    @property
    def start_time_ms(self) -> int:
        """Start timestamp in milliseconds."""
        ...

    @property
    def entity_ids(self) -> List[str]:
        """Entity IDs involved in episode."""
        ...


@runtime_checkable
class KGEdgeProtocol(Protocol):
    """Protocol for knowledge graph edges."""

    @property
    def source_id(self) -> str:
        """Source entity ID."""
        ...

    @property
    def target_id(self) -> str:
        """Target entity ID."""
        ...

    @property
    def relation_type(self) -> str:
        """Relationship type (e.g., 'CAUSES')."""
        ...

    @property
    def confidence(self) -> float:
        """Confidence score (0 to 1)."""
        ...


# =============================================================================
# CAUSAL DAG
# =============================================================================


@dataclass
class CausalNode:
    """A node in the causal DAG."""

    node_id: str
    modifiability: NodeModifiability
    depth: int  # Distance from target event
    entity_type: Optional[str] = None
    label: Optional[str] = None


@dataclass
class CausalEdge:
    """An edge in the causal DAG."""

    source_id: str
    target_id: str
    confidence: float


@dataclass
class CausalDAG:
    """
    Directed Acyclic Graph of causal relationships.

    Represents the causal chain leading to an event,
    with nodes tagged as MODIFIABLE or EXTERNAL.
    """

    nodes: Dict[str, CausalNode] = field(default_factory=dict)
    edges: List[CausalEdge] = field(default_factory=list)
    target_node_id: Optional[str] = None

    def add_node(
        self,
        node_id: str,
        modifiability: NodeModifiability,
        depth: int,
        entity_type: Optional[str] = None,
        label: Optional[str] = None,
    ) -> None:
        """Add a node to the DAG."""
        if node_id not in self.nodes:
            self.nodes[node_id] = CausalNode(
                node_id=node_id,
                modifiability=modifiability,
                depth=depth,
                entity_type=entity_type,
                label=label,
            )

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        confidence: float,
    ) -> None:
        """Add a causal edge to the DAG."""
        self.edges.append(
            CausalEdge(
                source_id=source_id,
                target_id=target_id,
                confidence=confidence,
            )
        )

    def get_modifiable_nodes(self) -> List[CausalNode]:
        """Return all modifiable nodes sorted by depth (closest first)."""
        modifiable = [
            n for n in self.nodes.values() if n.modifiability == NodeModifiability.MODIFIABLE
        ]
        return sorted(modifiable, key=lambda n: n.depth)

    def get_predecessors(self, node_id: str) -> List[str]:
        """Get direct predecessor node IDs."""
        return [e.source_id for e in self.edges if e.target_id == node_id]

    def get_successors(self, node_id: str) -> List[str]:
        """Get direct successor node IDs (nodes this node causes)."""
        return [e.target_id for e in self.edges if e.source_id == node_id]

    def compute_path_to_outcome(self, node_id: str) -> int:
        """
        Compute shortest path length from node to any outcome node (depth=0).

        Uses BFS to find the shortest path through the causal chain
        to any node with depth=0 (direct episode entities).

        Returns:
            Path length (0 if node is already at depth=0, -1 if no path found)
        """
        node = self.nodes.get(node_id)
        if node is None:
            return -1

        # If already at outcome level, path length is 0
        if node.depth == 0:
            return 0

        # BFS to find shortest path to a depth=0 node
        visited: set[str] = {node_id}
        queue: list[tuple[str, int]] = [(node_id, 0)]

        while queue:
            current_id, path_len = queue.pop(0)

            # Check successors (effects of current node)
            for succ_id in self.get_successors(current_id):
                if succ_id in visited:
                    continue
                visited.add(succ_id)

                succ_node = self.nodes.get(succ_id)
                if succ_node and succ_node.depth == 0:
                    return path_len + 1

                queue.append((succ_id, path_len + 1))

        # No path found - return node's depth as fallback
        return node.depth

    def get_edge_confidence(self, source_id: str, target_id: str) -> float:
        """Get confidence of edge between source and target."""
        for e in self.edges:
            if e.source_id == source_id and e.target_id == target_id:
                return e.confidence
        return 0.0

    @property
    def node_count(self) -> int:
        """Number of nodes in DAG."""
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        """Number of edges in DAG."""
        return len(self.edges)


# =============================================================================
# COUNTERFACTUAL SCENARIO (internal representation)
# =============================================================================


@dataclass(frozen=True)
class CPNCounterfactual:
    """
    Counterfactual scenario generated by CPN.

    Represents a "what if" scenario with perturbed outcome.
    """

    scenario_id: str
    scenario_type: ScenarioType
    base_episode_id: str
    intervention_node_id: str
    perturbation_target: str  # What was changed
    original_outcome: str  # Description of actual outcome
    counterfactual_outcome: str  # Description of hypothetical outcome
    original_sentiment: float
    predicted_sentiment: float
    plausibility: float  # How realistic (0-1)
    success_probability: float  # Probability of better outcome (0-1)
    utility_delta: float  # Change in utility
    mitigation: Optional[str]  # If-then rule for future
    causal_path_length: int
    created_at_ms: int

    @property
    def is_upward(self) -> bool:
        """True if this is an upward (improvement) scenario."""
        return self.scenario_type == ScenarioType.UPWARD

    @property
    def is_downward(self) -> bool:
        """True if this is a downward (worse) scenario."""
        return self.scenario_type == ScenarioType.DOWNWARD


# =============================================================================
# CPN ALGORITHM
# =============================================================================


class CausalPerturbationNetwork:
    """
    CPN: Counterfactual scenario generation via causal graph intervention.

    Generates "what if" scenarios by:
    1. Selecting emotionally significant events (regret potential)
    2. Building causal DAGs from knowledge graph
    3. Perturbing modifiable nodes
    4. Predicting alternative outcomes

    Usage:
        cpn = CausalPerturbationNetwork(config)
        scenarios = cpn.generate(episodes, kg_edges, rng_seed=123)
    """

    def __init__(self, config: Optional[CPNConfig] = None):
        """Initialize CPN with configuration."""
        self.config = config or CPNConfig()
        self._logger = logger

    def generate(
        self,
        episodes: List[Any],
        kg_edges: List[Any],
        rng_seed: Optional[int] = None,
    ) -> List[CPNCounterfactual]:
        """
        Generate counterfactual scenarios from episodes and knowledge graph.

        Args:
            episodes: List of episode objects (matching EpisodeProtocol)
            kg_edges: List of KG edge objects (matching KGEdgeProtocol)
            rng_seed: Optional RNG seed for determinism

        Returns:
            List of CPNCounterfactual scenarios
        """
        seed = rng_seed or self.config.seed
        rng = random.Random(seed) if seed else random.Random()

        self._logger.debug(
            "CPN starting generation",
            extra={
                "episodes_count": len(episodes),
                "edges_count": len(kg_edges),
                "seed": seed,
            },
        )

        # Step 1: Select regret-worthy events
        regret_events = self._select_regret_events(episodes, rng)

        if not regret_events:
            self._logger.debug("CPN: No regret events found")
            return []

        # Build edge lookup for efficient causal chain extraction
        edge_lookup = self._build_edge_lookup(kg_edges)

        # Step 2-4: For each regret event, build DAG and generate scenarios
        all_scenarios: List[CPNCounterfactual] = []

        for episode in regret_events:
            # Extract causal chain
            dag = self._extract_causal_chain(episode, edge_lookup)

            if dag.node_count == 0:
                continue

            # Generate counterfactuals from modifiable nodes
            scenarios = self._generate_counterfactuals_for_episode(
                episode=episode,
                dag=dag,
                rng=rng,
            )
            all_scenarios.extend(scenarios)

        # Sort by utility_delta descending (most impactful first)
        all_scenarios.sort(key=lambda s: abs(s.utility_delta), reverse=True)

        self._logger.info(
            "CPN completed generation",
            extra={
                "regret_events_count": len(regret_events),
                "scenarios_generated": len(all_scenarios),
            },
        )

        return all_scenarios

    def _select_regret_events(
        self,
        episodes: List[Any],
        rng: random.Random,
    ) -> List[Any]:
        """
        Select emotionally significant events for counterfactual analysis.

        Prioritizes:
        - High |sentiment| (emotionally charged)
        - High salience (important to user)
        - Recency (more relevant for learning)

        GAP-001 M9.3: Added fallback to select top episodes by salience
        when no episodes pass emotional threshold.

        Args:
            episodes: All episodes to consider
            rng: Random generator for tie-breaking

        Returns:
            Top-k regret-worthy episodes
        """
        scored: List[Tuple[Any, float]] = []

        for ep in episodes:
            # Get sentiment - handle both protocol and dict-like objects
            sentiment = self._get_episode_sentiment(ep)
            salience = self._get_episode_salience(ep)
            start_time = self._get_episode_start_time(ep)

            if abs(sentiment) < self.config.emotional_threshold:
                continue

            # Compute impact score
            recency_weight = self._compute_recency_weight(start_time)
            impact = abs(sentiment) * salience * recency_weight

            # Add small random jitter for deterministic tie-breaking
            impact += rng.random() * 0.0001

            scored.append((ep, impact))

        # GAP-001 M9.3: Fallback to salience-based selection if no emotional matches
        if not scored and episodes:
            logger.info(
                "CPN fallback: no episodes passed emotional threshold, selecting by salience",
                extra={
                    "emotional_threshold": self.config.emotional_threshold,
                    "episode_count": len(episodes),
                },
            )
            for ep in episodes:
                salience = self._get_episode_salience(ep)
                start_time = self._get_episode_start_time(ep)
                recency_weight = self._compute_recency_weight(start_time)
                impact = salience * recency_weight
                impact += rng.random() * 0.0001
                scored.append((ep, impact))

        # Sort by impact descending
        scored.sort(key=lambda x: x[1], reverse=True)

        return [ep for ep, _ in scored[: self.config.top_k_regret_events]]

    def _build_edge_lookup(
        self,
        kg_edges: List[Any],
    ) -> Dict[str, List[Tuple[str, float]]]:
        """
        Build lookup: target_id -> [(source_id, confidence), ...]

        Only includes CAUSES edges.
        """
        lookup: Dict[str, List[Tuple[str, float]]] = {}

        for edge in kg_edges:
            rel_type = self._get_edge_relation_type(edge)

            if rel_type != "CAUSES":
                continue

            target_id = self._get_edge_target(edge)
            source_id = self._get_edge_source(edge)
            confidence = self._get_edge_confidence(edge)

            if target_id not in lookup:
                lookup[target_id] = []
            lookup[target_id].append((source_id, confidence))

        return lookup

    def _extract_causal_chain(
        self,
        episode: Any,
        edge_lookup: Dict[str, List[Tuple[str, float]]],
    ) -> CausalDAG:
        """
        Build causal predecessor DAG from knowledge graph.

        Traverses CAUSES edges backward from episode entities.
        Tags nodes as MODIFIABLE or EXTERNAL.

        Args:
            episode: Episode to analyze
            edge_lookup: Pre-built edge lookup

        Returns:
            CausalDAG with tagged nodes
        """
        dag = CausalDAG()

        # Get entity IDs from episode
        entity_ids = self._get_episode_entities(episode)
        episode_id = self._get_episode_id(episode)

        if not entity_ids:
            return dag

        dag.target_node_id = episode_id

        # BFS to extract causal chain
        visited: Set[str] = set()
        queue: List[Tuple[str, int]] = [(eid, 0) for eid in entity_ids]

        while queue:
            node_id, depth = queue.pop(0)

            if node_id in visited:
                continue
            if depth >= self.config.causal_chain_depth:
                continue

            visited.add(node_id)

            # Determine modifiability (simplified heuristic)
            modifiability = self._determine_modifiability(node_id)

            dag.add_node(
                node_id=node_id,
                modifiability=modifiability,
                depth=depth,
            )

            # Get predecessors
            if node_id in edge_lookup:
                for source_id, confidence in edge_lookup[node_id]:
                    dag.add_edge(source_id, node_id, confidence)
                    if source_id not in visited:
                        queue.append((source_id, depth + 1))

        return dag

    def _generate_counterfactuals_for_episode(
        self,
        episode: Any,
        dag: CausalDAG,
        rng: random.Random,
    ) -> List[CPNCounterfactual]:
        """
        Generate counterfactual scenarios for a single episode.

        Args:
            episode: The regret episode
            dag: Causal DAG for the episode
            rng: Random generator

        Returns:
            List of counterfactual scenarios
        """
        scenarios: List[CPNCounterfactual] = []

        modifiable_nodes = dag.get_modifiable_nodes()

        if not modifiable_nodes:
            return scenarios

        for node in modifiable_nodes:
            # Generate scenarios based on configured types
            if "UPWARD" in self.config.counterfactual_types:
                upward = self._simulate_intervention(
                    episode=episode,
                    dag=dag,
                    node=node,
                    intervention_type=ScenarioType.UPWARD,
                    rng=rng,
                )
                if upward and upward.plausibility >= self.config.min_plausibility:
                    if upward.utility_delta >= self.config.min_utility_delta:
                        scenarios.append(upward)

            if "DOWNWARD" in self.config.counterfactual_types:
                downward = self._simulate_intervention(
                    episode=episode,
                    dag=dag,
                    node=node,
                    intervention_type=ScenarioType.DOWNWARD,
                    rng=rng,
                )
                if downward and downward.plausibility >= self.config.min_plausibility:
                    if abs(downward.utility_delta) >= self.config.min_utility_delta:
                        scenarios.append(downward)

            if "SEMIFACTUAL" in self.config.counterfactual_types:
                semifactual = self._simulate_intervention(
                    episode=episode,
                    dag=dag,
                    node=node,
                    intervention_type=ScenarioType.SEMIFACTUAL,
                    rng=rng,
                )
                if semifactual and semifactual.plausibility >= self.config.min_plausibility:
                    scenarios.append(semifactual)

        return scenarios

    def _simulate_intervention(
        self,
        episode: Any,
        dag: CausalDAG,
        node: CausalNode,
        intervention_type: ScenarioType,
        rng: random.Random,
    ) -> Optional[CPNCounterfactual]:
        """
        Simulate an intervention on a causal node.

        Args:
            episode: The base episode
            dag: Causal DAG
            node: Node to intervene on
            intervention_type: UPWARD/DOWNWARD/SEMIFACTUAL
            rng: Random generator

        Returns:
            CPNCounterfactual or None if intervention is not plausible
        """
        episode_id = self._get_episode_id(episode)
        original_sentiment = self._get_episode_sentiment(episode)

        # Compute perturbation based on intervention type
        perturbation = self._compute_perturbation(
            intervention_type=intervention_type,
            original_sentiment=original_sentiment,
            rng=rng,
        )

        # Predicted sentiment after intervention
        predicted_sentiment = original_sentiment + perturbation

        # Clamp to valid range
        predicted_sentiment = max(-1.0, min(1.0, predicted_sentiment))

        # Compute plausibility (simplified: based on causal path confidence)
        plausibility = self._compute_plausibility(dag, node)

        # Compute utility delta
        utility_delta = predicted_sentiment - original_sentiment

        # For SEMIFACTUAL, the outcome should be similar
        if intervention_type == ScenarioType.SEMIFACTUAL:
            if abs(utility_delta) > 0.15:
                return None  # Not a valid semifactual

        # Generate descriptions
        original_outcome = self._generate_outcome_description(episode, original_sentiment)
        counterfactual_outcome = self._generate_counterfactual_description(
            node, intervention_type, predicted_sentiment
        )

        # Generate mitigation suggestion for UPWARD scenarios
        mitigation = None
        if intervention_type == ScenarioType.UPWARD:
            mitigation = self._generate_mitigation(node)

        # Compute success probability (simplified)
        success_probability = plausibility * max(0.0, (1.0 + utility_delta) / 2.0)

        # Compute causal path length from intervention to outcome
        # Uses compute_path_to_outcome for actual path traversal instead of node.depth
        causal_path_length = dag.compute_path_to_outcome(node.node_id)

        return CPNCounterfactual(
            scenario_id=self._generate_scenario_id(episode_id, node.node_id, rng),
            scenario_type=intervention_type,
            base_episode_id=episode_id,
            intervention_node_id=node.node_id,
            perturbation_target=node.label or node.node_id,
            original_outcome=original_outcome,
            counterfactual_outcome=counterfactual_outcome,
            original_sentiment=original_sentiment,
            predicted_sentiment=predicted_sentiment,
            plausibility=plausibility,
            success_probability=success_probability,
            utility_delta=utility_delta,
            mitigation=mitigation,
            causal_path_length=causal_path_length,
            created_at_ms=int(time.time() * 1000),
        )

    def _compute_perturbation(
        self,
        intervention_type: ScenarioType,
        original_sentiment: float,
        rng: random.Random,
    ) -> float:
        """Compute sentiment perturbation based on intervention type."""
        base_perturbation = rng.gauss(0, self.config.perturbation_std)

        if intervention_type == ScenarioType.UPWARD:
            # Positive change
            return abs(base_perturbation) + 0.3  # Boost toward improvement
        elif intervention_type == ScenarioType.DOWNWARD:
            # Negative change
            return -abs(base_perturbation) - 0.3  # Push toward worse
        else:  # SEMIFACTUAL
            # Small change (same outcome)
            return base_perturbation * 0.3

    def _compute_plausibility(self, dag: CausalDAG, node: CausalNode) -> float:
        """
        Compute plausibility as geometric mean of causal path confidences.

        Higher depth = lower plausibility (longer causal chains are less certain).
        """
        if node.depth == 0:
            return 1.0

        # Get path confidences from node to target
        path_confidences: List[float] = []
        current_id = node.node_id

        # Simplified: use edges in dag that connect to target
        for edge in dag.edges:
            if edge.source_id == current_id:
                path_confidences.append(edge.confidence)
                current_id = edge.target_id

        if not path_confidences:
            # Decay based on depth
            return max(0.3, 1.0 - (node.depth * 0.15))

        # Geometric mean
        product = 1.0
        for conf in path_confidences:
            product *= conf
        return product ** (1.0 / len(path_confidences))

    def _determine_modifiability(self, node_id: str) -> NodeModifiability:
        """
        Determine if a node represents a modifiable (actor-controllable) action.

        Simplified heuristic: Assume nodes with certain patterns are modifiable.
        In production, this would use entity type from KG.
        """
        # Default to modifiable (most generous)
        return NodeModifiability.MODIFIABLE

    def _compute_recency_weight(self, start_time_ms: int) -> float:
        """Compute recency weight (exponential decay over 7 days)."""
        now_ms = int(time.time() * 1000)
        age_ms = now_ms - start_time_ms
        age_days = age_ms / (1000 * 60 * 60 * 24)

        # Exponential decay with 7-day half-life
        return math.exp(-age_days / 7.0)

    def _generate_outcome_description(
        self,
        episode: Any,
        sentiment: float,
    ) -> str:
        """Generate description of original outcome."""
        if sentiment > 0.3:
            return "Positive outcome"
        elif sentiment < -0.3:
            return "Negative outcome"
        else:
            return "Neutral outcome"

    def _generate_counterfactual_description(
        self,
        node: CausalNode,
        intervention_type: ScenarioType,
        predicted_sentiment: float,
    ) -> str:
        """Generate description of counterfactual outcome."""
        node_label = node.label or f"action at {node.node_id}"

        if intervention_type == ScenarioType.UPWARD:
            return f"If {node_label} had been different, outcome would be better"
        elif intervention_type == ScenarioType.DOWNWARD:
            return f"If {node_label} had also gone wrong, outcome would be worse"
        else:
            return f"Even if {node_label} changed, outcome would be similar"

    def _generate_mitigation(self, node: CausalNode) -> str:
        """Generate if-then mitigation rule for upward counterfactual."""
        node_label = node.label or node.node_id
        return f"Next time, consider changing {node_label} earlier"

    def _generate_scenario_id(
        self,
        episode_id: str,
        node_id: str,
        rng: random.Random,
    ) -> str:
        """Generate deterministic scenario ID."""
        # Simple hash-based ID for determinism
        import hashlib

        data = f"{episode_id}:{node_id}:{rng.random()}"
        hash_bytes = hashlib.sha256(data.encode()).hexdigest()[:16]
        return f"cf_{hash_bytes}"

    # =========================================================================
    # EPISODE ACCESS HELPERS (handle both protocol and dict-like objects)
    # =========================================================================

    def _get_episode_id(self, episode: Any) -> str:
        """Get episode ID from episode object."""
        if hasattr(episode, "episode_id"):
            return episode.episode_id
        elif isinstance(episode, dict):
            return episode.get("episode_id", "unknown")
        return str(id(episode))

    def _get_episode_sentiment(self, episode: Any) -> float:
        """Get sentiment score from episode object."""
        if hasattr(episode, "sentiment_score"):
            return episode.sentiment_score
        elif isinstance(episode, dict):
            return episode.get("sentiment_score", 0.0)
        return 0.0

    def _get_episode_salience(self, episode: Any) -> float:
        """Get salience score from episode object."""
        if hasattr(episode, "salience_score"):
            return episode.salience_score
        elif isinstance(episode, dict):
            return episode.get("salience_score", 0.5)
        return 0.5

    def _get_episode_start_time(self, episode: Any) -> int:
        """Get start time from episode object."""
        if hasattr(episode, "start_time_ms"):
            return episode.start_time_ms
        elif hasattr(episode, "start_time"):
            return episode.start_time
        elif isinstance(episode, dict):
            return episode.get("start_time_ms", episode.get("start_time", 0))
        return 0

    def _get_episode_entities(self, episode: Any) -> List[str]:
        """Get entity IDs from episode object."""
        if hasattr(episode, "entity_ids"):
            return list(episode.entity_ids)
        elif isinstance(episode, dict):
            return episode.get("entity_ids", [])
        return []

    # =========================================================================
    # EDGE ACCESS HELPERS
    # =========================================================================

    def _get_edge_source(self, edge: Any) -> str:
        """Get source ID from edge object."""
        if hasattr(edge, "source_id"):
            return edge.source_id
        elif isinstance(edge, dict):
            return edge.get("source_id", "")
        return ""

    def _get_edge_target(self, edge: Any) -> str:
        """Get target ID from edge object."""
        if hasattr(edge, "target_id"):
            return edge.target_id
        elif isinstance(edge, dict):
            return edge.get("target_id", "")
        return ""

    def _get_edge_relation_type(self, edge: Any) -> str:
        """Get relation type from edge object."""
        if hasattr(edge, "relation_type"):
            return edge.relation_type
        elif hasattr(edge, "relationship_type"):
            return edge.relationship_type
        elif isinstance(edge, dict):
            return edge.get("relation_type", edge.get("relationship_type", ""))
        return ""

    def _get_edge_confidence(self, edge: Any) -> float:
        """Get confidence from edge object."""
        if hasattr(edge, "confidence"):
            return edge.confidence
        elif hasattr(edge, "causal_confidence"):
            return edge.causal_confidence
        elif isinstance(edge, dict):
            return edge.get("confidence", edge.get("causal_confidence", 0.5))
        return 0.5
