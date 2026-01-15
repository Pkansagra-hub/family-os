"""
TPN-MCTS — Temporal Projection Network with Monte Carlo Tree Search.

This module implements forward simulation using MCTS with UCT selection
for personal future scenario prediction.

Algorithms:
- UCT (Upper Confidence Bound for Trees) selection with c = √2
- Rollout simulation with action sampling
- DPP (Determinantal Point Process) for diverse scenario selection

References:
- M8_EXECUTION.md Issue 8.1.5: TPN-MCTS forward simulation with UCT
- M8_EXECUTION.md Issue 8.1.6: Adaptive rollout allocation
- Dossier §4.6.2: Forward Simulation (TPN-MCTS)
- Dossier Appendix C.6.2: TPN-MCTS Algorithm Details

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import hashlib
import logging
import math
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Tuple,
    Union,
    runtime_checkable,
)

if TYPE_CHECKING:
    from k0.modules.consolidation.dream.mcts_persistence import MCTSDecisionRecord

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS (from dossier and M8_EXECUTION.md)
# =============================================================================

# UCT exploration constant (sqrt(2) per UCT paper)
P03_MCTS_UCT_EXPLORATION_CONSTANT = 1.414

# Maximum rollout depth (days of simulation horizon)
P03_MCTS_MAX_ROLLOUT_DEPTH = 30

# Default rollouts per decision
P03_MCTS_DEFAULT_ROLLOUTS = 100

# Discount factor for future rewards
P03_MCTS_DISCOUNT_FACTOR = 0.9

# Goal achievement bonus
P03_MCTS_GOAL_BONUS = 10.0

# Early termination thresholds
P03_MCTS_CLEAR_WINNER_THRESHOLD = 0.90  # >90% visits to best action
P03_MCTS_CI_WIDTH_THRESHOLD = 0.05  # <5% confidence interval width


# =============================================================================
# DECISION TYPES AND ROLLOUT ALLOCATION (dossier §4.6.2.1)
# =============================================================================


class DecisionType(str, Enum):
    """Types of decisions for rollout allocation."""

    ENTITY_MERGE = "entity_merge"
    ENTITY_SPLIT = "entity_split"
    CAUSAL_EDGE = "causal_edge"
    CLUSTER_ASSIGN = "cluster_assign"
    MEMORY_REINFORCE = "memory_reinforce"
    DECAY_TUNE = "decay_tune"
    NOVELTY_ADJUST = "novelty_adjust"
    GENERIC = "generic"  # Fallback


# Rollout allocation table (from dossier §4.6.2.1)
ROLLOUT_ALLOCATION = {
    DecisionType.ENTITY_MERGE: 100,
    DecisionType.ENTITY_SPLIT: 100,
    DecisionType.CAUSAL_EDGE: 50,
    DecisionType.CLUSTER_ASSIGN: 30,
    DecisionType.MEMORY_REINFORCE: 20,
    DecisionType.DECAY_TUNE: 10,
    DecisionType.NOVELTY_ADJUST: 10,
    DecisionType.GENERIC: 20,
}


# =============================================================================
# PROTOCOLS
# =============================================================================


@runtime_checkable
class Action(Protocol):
    """Protocol for actions in MCTS tree."""

    action_id: str
    action_type: str

    def __hash__(self) -> int: ...

    def __eq__(self, other: object) -> bool: ...


@runtime_checkable
class State(Protocol):
    """Protocol for states in MCTS simulation."""

    state_id: str

    def copy(self) -> "State": ...


@runtime_checkable
class Goal(Protocol):
    """Protocol for goals in rollout evaluation."""

    goal_id: str
    goal_type: str


# =============================================================================
# CONFIGURATION
# =============================================================================


@dataclass
class MCTSConfig:
    """
    Configuration for MCTS algorithm.

    Attributes:
        exploration_constant: UCT exploration constant c (default √2)
        max_rollout_depth: Maximum simulation horizon in steps
        default_rollouts: Default rollouts per decision
        discount_factor: Discount for future rewards (gamma)
        goal_bonus: Bonus for achieving goal
        clear_winner_threshold: Visit ratio for clear winner detection
        ci_width_threshold: Confidence interval width for convergence
        max_total_rollouts: Per-cycle rollout budget (default 1000)
        seed: RNG seed for determinism
    """

    exploration_constant: float = P03_MCTS_UCT_EXPLORATION_CONSTANT
    max_rollout_depth: int = P03_MCTS_MAX_ROLLOUT_DEPTH
    default_rollouts: int = P03_MCTS_DEFAULT_ROLLOUTS
    discount_factor: float = P03_MCTS_DISCOUNT_FACTOR
    goal_bonus: float = P03_MCTS_GOAL_BONUS
    clear_winner_threshold: float = P03_MCTS_CLEAR_WINNER_THRESHOLD
    ci_width_threshold: float = P03_MCTS_CI_WIDTH_THRESHOLD
    max_total_rollouts: int = 1000  # Per-cycle budget
    seed: Optional[int] = None

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.exploration_constant <= 0:
            raise ValueError("exploration_constant must be positive")
        if self.max_rollout_depth < 1:
            raise ValueError("max_rollout_depth must be at least 1")
        if self.default_rollouts < 1:
            raise ValueError("default_rollouts must be at least 1")
        if not 0 < self.discount_factor <= 1:
            raise ValueError("discount_factor must be in (0, 1]")
        if self.max_total_rollouts < 1:
            raise ValueError("max_total_rollouts must be at least 1")


# =============================================================================
# COMPUTE BUDGET (dossier §4.6.2.1)
# =============================================================================


@dataclass
class ComputeBudget:
    """
    Shared compute budget for R5 cycle.

    Created ONCE per cycle and passed to all R5 algorithms.
    Enforces the 1000 rollouts per cycle cap.

    Attributes:
        max_mcts_rollouts: Maximum rollouts allowed (default 1000)
        used_rollouts: Rollouts already consumed
    """

    max_mcts_rollouts: int = 1000
    used_rollouts: int = 0

    def can_allocate(self, requested: int) -> bool:
        """Check if rollouts can be allocated."""
        return self.used_rollouts + requested <= self.max_mcts_rollouts

    def allocate(self, requested: int) -> int:
        """
        Allocate rollouts, returning actual allocated (may be less).

        Args:
            requested: Number of rollouts requested

        Returns:
            Number of rollouts actually allocated
        """
        available = self.max_mcts_rollouts - self.used_rollouts
        allocated = min(requested, available)
        self.used_rollouts += allocated
        return allocated

    @property
    def exhausted(self) -> bool:
        """Return True if budget is exhausted."""
        return self.used_rollouts >= self.max_mcts_rollouts

    @property
    def remaining(self) -> int:
        """Return remaining rollouts."""
        return max(0, self.max_mcts_rollouts - self.used_rollouts)


# =============================================================================
# MCTS NODE
# =============================================================================


@dataclass
class MCTSNode:
    """
    Node in the MCTS tree.

    Represents a state-action pair with statistics for UCT selection.

    Attributes:
        node_id: Unique identifier for this node
        action: Action that led to this node (None for root)
        parent: Parent node (None for root)
        children: Child nodes indexed by action
        visit_count: Number of times this node was visited
        total_reward: Sum of rewards from rollouts through this node
        is_terminal: Whether this is a terminal state
        depth: Depth in tree (root = 0)
    """

    node_id: str
    action: Optional[Action] = None
    parent: Optional["MCTSNode"] = None
    children: Dict[str, "MCTSNode"] = field(default_factory=dict)
    visit_count: int = 0
    total_reward: float = 0.0
    is_terminal: bool = False
    depth: int = 0

    @property
    def is_root(self) -> bool:
        """Return True if this is the root node."""
        return self.parent is None

    @property
    def is_leaf(self) -> bool:
        """Return True if this is a leaf node (no children)."""
        return len(self.children) == 0

    @property
    def average_reward(self) -> float:
        """Return average reward (Q-value)."""
        if self.visit_count == 0:
            return 0.0
        return self.total_reward / self.visit_count

    def add_child(self, action: Any) -> "MCTSNode":
        """
        Add a child node for the given action.

        Args:
            action: Action leading to the child state (must have action_id)

        Returns:
            Newly created child node
        """
        action_id = action.action_id
        if action_id in self.children:
            return self.children[action_id]

        child = MCTSNode(
            node_id=f"{self.node_id}_{action_id}",
            action=action,
            parent=self,
            depth=self.depth + 1,
        )
        self.children[action_id] = child
        return child

    def backpropagate(self, reward: float) -> None:
        """
        Backpropagate reward up the tree.

        Args:
            reward: Reward to propagate
        """
        self.visit_count += 1
        self.total_reward += reward

        if self.parent is not None:
            self.parent.backpropagate(reward)


# =============================================================================
# SCENARIO OUTPUT
# =============================================================================


@dataclass(frozen=True)
class MCTSScenario:
    """
    Scenario generated from MCTS forward simulation.

    Represents a predicted future path with probability estimates.

    Attributes:
        scenario_id: Unique identifier (ULID)
        action_sequence: Sequence of actions in this scenario
        predicted_outcome: Description of the outcome
        success_probability: Probability of success (0.0 to 1.0)
        expected_reward: Expected cumulative reward
        plausibility: Plausibility score (0.0 to 1.0)
        visit_count: Number of times this path was visited
        depth: Depth of the scenario (number of actions)
        created_at_ms: Creation timestamp in milliseconds
    """

    scenario_id: str
    action_sequence: Tuple[str, ...]
    predicted_outcome: str
    success_probability: float
    expected_reward: float
    plausibility: float
    visit_count: int
    depth: int
    created_at_ms: int

    @classmethod
    def create(
        cls,
        scenario_id: str,
        action_sequence: List[str],
        predicted_outcome: str,
        success_probability: float,
        expected_reward: float,
        plausibility: float,
        visit_count: int,
        depth: int,
    ) -> "MCTSScenario":
        """Factory method for creating scenarios."""
        return cls(
            scenario_id=scenario_id,
            action_sequence=tuple(action_sequence),
            predicted_outcome=predicted_outcome,
            success_probability=max(0.0, min(1.0, success_probability)),
            expected_reward=expected_reward,
            plausibility=max(0.0, min(1.0, plausibility)),
            visit_count=visit_count,
            depth=depth,
            created_at_ms=int(time.time() * 1000),
        )


# =============================================================================
# DECISION RECORD (for persistence)
# =============================================================================


@dataclass
class MCTSDecision:
    """
    Record of an MCTS decision for persistence.

    Tracks decision context, allocated/executed rollouts,
    and termination reason for metrics and debugging.

    Attributes:
        decision_id: Unique identifier (ULID)
        decision_type: Type of decision
        context: Additional context (entity_type, confidence, etc.)
        rollouts_allocated: Number of rollouts allocated
        rollouts_executed: Number of rollouts actually executed
        early_termination: Whether early termination was triggered
        termination_reason: Reason for termination (if early)
        chosen_action: ID of the chosen action
        value_estimate: Q-value of chosen action
        confidence_interval_width: CI width at termination
        compute_ms: Milliseconds spent on this decision
        created_at_ms: Creation timestamp in milliseconds
    """

    decision_id: str
    decision_type: str
    context: Dict[str, Any]
    rollouts_allocated: int
    rollouts_executed: int
    early_termination: bool
    termination_reason: Optional[str]
    chosen_action: Optional[str]
    value_estimate: float
    confidence_interval_width: float
    compute_ms: int
    created_at_ms: int

    def to_persistence_record(
        self,
        cycle_id: str,
    ) -> "MCTSDecisionRecord":
        """
        Convert to MCTSDecisionRecord for database persistence.

        Issue 8.1.7: Enables decision tracing in st_mcts_decisions.

        Args:
            cycle_id: Parent consolidation cycle ULID

        Returns:
            MCTSDecisionRecord ready for persistence
        """
        from k0.modules.consolidation.dream.mcts_persistence import (
            MCTSDecisionRecord,
            TerminationReason,
        )

        # Map termination reason string to enum
        term_reason = TerminationReason.NONE
        if self.termination_reason:
            try:
                term_reason = TerminationReason(self.termination_reason)
            except ValueError:
                term_reason = TerminationReason.NONE

        return MCTSDecisionRecord(
            decision_id=self.decision_id,
            cycle_id=cycle_id,
            decision_type=self.decision_type,
            context=self.context,
            rollouts_allocated=self.rollouts_allocated,
            rollouts_executed=self.rollouts_executed,
            early_termination=self.early_termination,
            termination_reason=term_reason.value,
            chosen_action=self.chosen_action,
            value_estimate=self.value_estimate,
            confidence_interval_width=self.confidence_interval_width,
            compute_ms=self.compute_ms,
            created_at_ms=self.created_at_ms,
        )


# =============================================================================
# MOCK ACTION/STATE FOR TESTING
# =============================================================================


@dataclass(frozen=True)
class SimpleAction:
    """Simple action implementation for testing."""

    action_id: str
    action_type: str = "generic"

    def __hash__(self) -> int:
        return hash(self.action_id)


@dataclass
class SimpleState:
    """Simple state implementation for testing."""

    state_id: str
    features: Dict[str, float] = field(default_factory=dict)

    def copy(self) -> "SimpleState":
        return SimpleState(
            state_id=self.state_id,
            features=dict(self.features),
        )


# =============================================================================
# TPN-MCTS ALGORITHM
# =============================================================================


class TemporalProjectionMCTS:
    """
    Monte Carlo Tree Search for personal future scenarios.

    Implements UCT selection with configurable exploration constant,
    adaptive rollout allocation, and early termination detection.

    This class orchestrates the MCTS algorithm:
    1. Selection: UCT-based child selection
    2. Expansion: Add new nodes for unexplored actions
    3. Simulation: Random rollout to estimate value
    4. Backpropagation: Update statistics up the tree

    Usage:
        config = MCTSConfig(exploration_constant=1.414)
        mcts = TemporalProjectionMCTS(config)
        budget = ComputeBudget(max_mcts_rollouts=1000)

        scenarios = mcts.simulate(
            initial_state=state,
            available_actions=actions,
            reward_fn=lambda s, a: compute_reward(s, a),
            budget=budget,
            rng_seed=42,
        )
    """

    def __init__(
        self,
        config: Optional[MCTSConfig] = None,
        transition_fn: Optional[Callable[[Any, Any], Any]] = None,
        reward_fn: Optional[Callable[[Any, Any], float]] = None,
        terminal_fn: Optional[Callable[[Any], bool]] = None,
        action_fn: Optional[Callable[[Any], List[Any]]] = None,
    ):
        """
        Initialize TPN-MCTS.

        Args:
            config: MCTS configuration
            transition_fn: Function (state, action) -> next_state
            reward_fn: Function (state, action) -> reward
            terminal_fn: Function (state) -> is_terminal
            action_fn: Function (state) -> available_actions
        """
        self.config = config or MCTSConfig()
        self._transition_fn = transition_fn
        self._reward_fn = reward_fn
        self._terminal_fn = terminal_fn
        self._action_fn = action_fn
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    # -------------------------------------------------------------------------
    # UCT Selection (dossier C.6.2)
    # -------------------------------------------------------------------------

    def compute_uct(self, node: MCTSNode, parent: MCTSNode) -> float:
        """
        Compute UCT value for a node.

        UCT = Q/N + c × √(ln(N_parent) / N)

        Args:
            node: Child node to evaluate
            parent: Parent node

        Returns:
            UCT value (float('inf') for unvisited nodes)
        """
        if node.visit_count == 0:
            return float("inf")  # Always explore unvisited

        exploitation = node.total_reward / node.visit_count
        exploration = self.config.exploration_constant * math.sqrt(
            math.log(parent.visit_count) / node.visit_count
        )

        return exploitation + exploration

    def uct_select(self, node: MCTSNode) -> MCTSNode:
        """
        Select best child using UCT.

        Args:
            node: Parent node

        Returns:
            Best child node by UCT value
        """
        if node.is_leaf:
            return node

        best_child = None
        best_uct = float("-inf")

        for child in node.children.values():
            if child.visit_count == 0:
                return child  # Always try unvisited first

            uct = self.compute_uct(child, node)
            if uct > best_uct:
                best_uct = uct
                best_child = child

        return best_child if best_child else node

    # -------------------------------------------------------------------------
    # Selection Phase
    # -------------------------------------------------------------------------

    def select(self, root: MCTSNode) -> MCTSNode:
        """
        Selection phase: traverse tree using UCT until leaf.

        Args:
            root: Root node of the tree

        Returns:
            Selected leaf node for expansion
        """
        current = root

        while not current.is_leaf and not current.is_terminal:
            current = self.uct_select(current)

        return current

    # -------------------------------------------------------------------------
    # Expansion Phase
    # -------------------------------------------------------------------------

    def expand(
        self,
        node: MCTSNode,
        actions: List[Any],
        rng: random.Random,
    ) -> MCTSNode:
        """
        Expansion phase: add child nodes for available actions.

        Args:
            node: Node to expand
            actions: Available actions from this state
            rng: Random number generator

        Returns:
            One of the newly added children (for rollout)
        """
        if not actions:
            node.is_terminal = True
            return node

        # Add children for all actions
        for action in actions:
            if hasattr(action, "action_id"):
                action_obj = action
            else:
                # Wrap primitive action
                action_obj = SimpleAction(action_id=str(action))
            node.add_child(action_obj)

        # Return a random child for rollout
        child_list = list(node.children.values())
        return rng.choice(child_list)

    # -------------------------------------------------------------------------
    # Simulation (Rollout) Phase
    # -------------------------------------------------------------------------

    def rollout(
        self,
        state: Any,
        goal: Optional[Any],
        rng: random.Random,
    ) -> float:
        """
        Simulation phase: random rollout to estimate value.

        Simulates random action sequence until terminal state
        or max depth, accumulating discounted rewards.

        Args:
            state: Current state
            goal: Optional goal for goal-based reward
            rng: Random number generator

        Returns:
            Total discounted reward from rollout
        """
        if state is None:
            return 0.0

        current_state = state.copy() if hasattr(state, "copy") else state
        total_reward = 0.0

        for step in range(self.config.max_rollout_depth):
            # Check terminal
            if self._terminal_fn and self._terminal_fn(current_state):
                # Goal bonus if achieved
                if goal is not None:
                    total_reward += self.config.goal_bonus
                break

            # Get available actions
            actions = []
            if self._action_fn:
                actions = self._action_fn(current_state)

            if not actions:
                break

            # Sample random action
            action = rng.choice(actions)

            # Compute reward
            reward = 0.0
            if self._reward_fn:
                reward = self._reward_fn(current_state, action)

            # Apply discount
            total_reward += reward * (self.config.discount_factor**step)

            # Transition to next state
            if self._transition_fn:
                current_state = self._transition_fn(current_state, action)
            else:
                break

        return total_reward

    # -------------------------------------------------------------------------
    # Early Termination Check (dossier §4.6.2.1)
    # -------------------------------------------------------------------------

    def should_terminate_early(self, root: MCTSNode) -> Tuple[bool, Optional[str]]:
        """
        Check if MCTS can terminate early.

        Criteria:
        1. Clear winner (>90% visits)
        2. Low uncertainty (<5% CI width)

        Args:
            root: Root node of the tree

        Returns:
            Tuple of (should_terminate, reason)
        """
        if root.visit_count == 0 or root.is_leaf:
            return False, None

        # Calculate visit ratios
        visit_counts = {action_id: child.visit_count for action_id, child in root.children.items()}
        total_visits = sum(visit_counts.values())

        if total_visits == 0:
            return False, None

        # Require minimum visits before considering early termination
        # This prevents declaring "clear winner" after just 1-2 visits
        min_visits_for_early_stop = max(10, len(root.children) * 2)
        if total_visits < min_visits_for_early_stop:
            return False, None

        best_action = max(visit_counts, key=lambda k: visit_counts[k])
        best_visit_ratio = visit_counts[best_action] / total_visits

        # Criterion 1: Clear winner (>90% visits to one action)
        if best_visit_ratio > self.config.clear_winner_threshold:
            return True, "clear_winner"

        # Criterion 2: Low uncertainty (approximate CI width)
        # Using Wilson score interval approximation
        if total_visits >= 30:  # Minimum samples for CI
            p = best_visit_ratio
            z = 1.96  # 95% confidence
            n = total_visits
            ci_width = z * math.sqrt(p * (1 - p) / n)

            if ci_width < self.config.ci_width_threshold:
                return True, "low_uncertainty"

        return False, None

    # -------------------------------------------------------------------------
    # Rollout Allocation (dossier §4.6.2.1)
    # -------------------------------------------------------------------------

    def classify_decision_importance(
        self,
        decision_type: Union[str, DecisionType],
        context: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Classify decision importance to determine rollout count.

        Args:
            decision_type: Type of decision
            context: Additional context (entity_type, confidence, etc.)

        Returns:
            Rollout count (10-100)
        """
        context = context or {}

        # Get base rollouts
        if isinstance(decision_type, str):
            try:
                decision_type = DecisionType(decision_type)
            except ValueError:
                decision_type = DecisionType.GENERIC

        rollouts = ROLLOUT_ALLOCATION.get(decision_type, 20)

        # Boost for high-value entities (e.g., FAMILY_MEMBER)
        if context.get("entity_type") == "FAMILY_MEMBER":
            rollouts = int(rollouts * 1.5)

        # Reduce for low-confidence contexts
        confidence = context.get("confidence", 1.0)
        if confidence < 0.60:
            rollouts = max(10, int(rollouts * 0.5))

        return min(rollouts, 100)  # Cap at 100

    # -------------------------------------------------------------------------
    # Main Simulation Entry Point
    # -------------------------------------------------------------------------

    def simulate(
        self,
        initial_state: Any,
        available_actions: List[Any],
        budget: Optional[ComputeBudget] = None,
        rng_seed: Optional[int] = None,
        decision_type: Union[str, DecisionType] = DecisionType.GENERIC,
        context: Optional[Dict[str, Any]] = None,
        goal: Optional[Any] = None,
    ) -> List[MCTSScenario]:
        """
        Run MCTS simulation and return generated scenarios.

        Args:
            initial_state: Starting state for simulation
            available_actions: Actions available from initial state
            budget: Shared compute budget (created if None)
            rng_seed: Seed for deterministic behavior
            decision_type: Type of decision for rollout allocation
            context: Additional context for rollout allocation
            goal: Optional goal for reward calculation

        Returns:
            List of generated scenarios sorted by expected reward
        """
        start_ms = int(time.time() * 1000)

        # Initialize RNG
        seed = rng_seed if rng_seed is not None else self.config.seed
        rng = random.Random(seed)

        # Initialize budget if not provided
        if budget is None:
            budget = ComputeBudget(max_mcts_rollouts=self.config.max_total_rollouts)

        # Determine rollout count
        rollouts_requested = self.classify_decision_importance(decision_type, context)
        rollouts_allocated = budget.allocate(rollouts_requested)

        if rollouts_allocated == 0:
            self._logger.warning("Budget exhausted, no rollouts allocated")
            return []

        # Create root node
        root_id = hashlib.sha256(f"{seed}:{initial_state}".encode()).hexdigest()[:16]
        root = MCTSNode(node_id=f"root_{root_id}")

        # Expand root with initial actions
        self.expand(root, available_actions, rng)

        # Run MCTS iterations
        rollouts_executed = 0
        termination_reason = None

        for _ in range(rollouts_allocated):
            # 1. Selection
            leaf = self.select(root)

            # 2. Expansion (if not terminal and is a leaf node)
            # NOTE: Expand newly selected leaves (visit_count=0) OR nodes that need re-expansion
            # The original condition "visit_count > 0" prevented expansion of fresh leaves
            if not leaf.is_terminal and leaf.is_leaf:
                actions = []
                if self._action_fn:
                    actions = self._action_fn(initial_state)
                else:
                    actions = available_actions

                leaf = self.expand(leaf, actions, rng)

            # 3. Simulation
            reward = self.rollout(initial_state, goal, rng)

            # 4. Backpropagation
            leaf.backpropagate(reward)

            rollouts_executed += 1

            # Check early termination
            should_stop, reason = self.should_terminate_early(root)
            if should_stop:
                termination_reason = reason
                self._logger.debug(
                    f"Early termination after {rollouts_executed} rollouts: {reason}"
                )
                break

        # Extract scenarios from tree (use 0 if seed is None)
        effective_seed = seed if seed is not None else 0
        scenarios = self._extract_scenarios(root, rng, effective_seed)

        compute_ms = int(time.time() * 1000) - start_ms

        self._logger.debug(
            "MCTS simulation complete",
            extra={
                "rollouts_allocated": rollouts_allocated,
                "rollouts_executed": rollouts_executed,
                "scenarios_generated": len(scenarios),
                "compute_ms": compute_ms,
                "early_termination": termination_reason,
            },
        )

        return scenarios

    # -------------------------------------------------------------------------
    # Scenario Extraction
    # -------------------------------------------------------------------------

    def _extract_scenarios(
        self,
        root: MCTSNode,
        rng: random.Random,
        seed: int,
    ) -> List[MCTSScenario]:
        """
        Extract scenarios from MCTS tree.

        Extracts paths through the tree as scenarios,
        sorted by expected reward.

        Args:
            root: Root node of the tree
            rng: Random number generator
            seed: Seed for scenario ID generation

        Returns:
            List of scenarios sorted by expected reward (descending)
        """
        scenarios = []

        if root.is_leaf:
            return scenarios

        # Extract paths from root to each child
        for action_id, child in root.children.items():
            if child.visit_count == 0:
                continue

            # Calculate success probability
            total_visits = sum(c.visit_count for c in root.children.values())
            success_prob = child.visit_count / total_visits if total_visits > 0 else 0.0

            # Calculate plausibility (decay with depth)
            plausibility = 1.0 / (1.0 + 0.1 * child.depth)

            # Generate scenario ID
            scenario_id = (
                hashlib.sha256(f"{seed}:{action_id}:{child.visit_count}".encode())
                .hexdigest()[:26]
                .upper()
            )

            scenario = MCTSScenario.create(
                scenario_id=scenario_id,
                action_sequence=[action_id],
                predicted_outcome=f"Action {action_id} outcome",
                success_probability=success_prob,
                expected_reward=child.average_reward,
                plausibility=plausibility,
                visit_count=child.visit_count,
                depth=child.depth,
            )
            scenarios.append(scenario)

        # Sort by expected reward (descending)
        scenarios.sort(key=lambda s: s.expected_reward, reverse=True)

        return scenarios

    # -------------------------------------------------------------------------
    # Decision Record Generation
    # -------------------------------------------------------------------------

    def create_decision_record(
        self,
        decision_id: str,
        decision_type: Union[str, DecisionType],
        context: Dict[str, Any],
        root: MCTSNode,
        rollouts_allocated: int,
        rollouts_executed: int,
        early_termination: bool,
        termination_reason: Optional[str],
        compute_ms: int,
    ) -> MCTSDecision:
        """
        Create a decision record for persistence.

        Args:
            decision_id: Unique decision identifier
            decision_type: Type of decision
            context: Decision context
            root: Root node of the tree
            rollouts_allocated: Allocated rollout count
            rollouts_executed: Executed rollout count
            early_termination: Whether early termination occurred
            termination_reason: Reason for early termination
            compute_ms: Computation time in milliseconds

        Returns:
            MCTSDecision record for persistence
        """
        # Get best action
        chosen_action = None
        value_estimate = 0.0

        if not root.is_leaf:
            best_child = max(
                root.children.values(),
                key=lambda c: c.visit_count,
                default=None,
            )
            if best_child:
                chosen_action = best_child.action.action_id if best_child.action else None
                value_estimate = best_child.average_reward

        # Calculate CI width
        ci_width = 0.0
        if root.visit_count > 0 and not root.is_leaf:
            total_visits = sum(c.visit_count for c in root.children.values())
            if total_visits >= 30:
                best_ratio = max(
                    c.visit_count / total_visits
                    for c in root.children.values()
                    if c.visit_count > 0
                )
                z = 1.96
                ci_width = z * math.sqrt(best_ratio * (1 - best_ratio) / total_visits)

        dt_str = decision_type.value if isinstance(decision_type, DecisionType) else decision_type

        return MCTSDecision(
            decision_id=decision_id,
            decision_type=dt_str,
            context=context,
            rollouts_allocated=rollouts_allocated,
            rollouts_executed=rollouts_executed,
            early_termination=early_termination,
            termination_reason=termination_reason,
            chosen_action=chosen_action,
            value_estimate=value_estimate,
            confidence_interval_width=ci_width,
            compute_ms=compute_ms,
            created_at_ms=int(time.time() * 1000),
        )
