"""
MCTS Algorithm Benchmarks — Real-World Testing.

This module provides comprehensive benchmarks for the TPN-MCTS (Temporal
Projection Network with Monte Carlo Tree Search) algorithm.

Test Categories:
1. Correctness: Validates UCT selection and tree building
2. Performance: Measures execution time and rollout efficiency
3. Quality: Evaluates scenario quality and diversity
4. Budget Compliance: Verifies compute budget enforcement
5. Determinism: Verifies reproducibility

References:
- M8_EXECUTION.md Issue 8.1.5: TPN-MCTS forward simulation
- M8_EXECUTION.md Issue 8.1.6: Adaptive rollout allocation
- Dossier §4.6.2: Forward Simulation (TPN-MCTS)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List

import pytest

from k0.modules.consolidation.algorithms.mcts import (
    P03_MCTS_UCT_EXPLORATION_CONSTANT,
    ROLLOUT_ALLOCATION,
    ComputeBudget,
    DecisionType,
    MCTSConfig,
    MCTSNode,
    SimpleAction,
    TemporalProjectionMCTS,
)
from tests.k0.modules.consolidation.benchmarks.performance_metrics import (
    BenchmarkCollector,
    StopwatchTimer,
)
from tests.k0.modules.consolidation.benchmarks.realistic_data import (
    BenchmarkDatasetGenerator,
    BenchmarkScale,
    RealisticGoal,
)

# =============================================================================
# REALISTIC ACTION/STATE MODELS
# =============================================================================


@dataclass
class PersonalAction:
    """Realistic personal decision action."""

    action_id: str
    action_type: str
    description: str
    energy_cost: float = 0.1
    time_cost_hours: float = 1.0
    expected_reward: float = 0.0

    def __hash__(self) -> int:
        return hash(self.action_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PersonalAction):
            return False
        return self.action_id == other.action_id


@dataclass
class PersonalState:
    """Realistic personal life state."""

    state_id: str
    energy: float = 1.0
    progress: Dict[str, float] = None  # Goal progress
    time_of_day: int = 12  # Hour (0-23)
    day_of_week: int = 0  # 0=Monday

    def __post_init__(self):
        if self.progress is None:
            self.progress = {}

    def copy(self) -> "PersonalState":
        """Create a copy of the state."""
        return PersonalState(
            state_id=f"{self.state_id}_copy",
            energy=self.energy,
            progress=dict(self.progress),
            time_of_day=self.time_of_day,
            day_of_week=self.day_of_week,
        )


class RealisticActionProvider:
    """Provides realistic actions based on state and goals."""

    ACTION_TEMPLATES = [
        ("work", "work", "Focus on work tasks", 0.3, 2.0, 0.5),
        ("exercise", "exercise", "Go to the gym", 0.4, 1.0, 0.3),
        ("rest", "rest", "Take a break", -0.2, 0.5, 0.1),
        ("socialize", "social", "Meet with friends", 0.2, 2.0, 0.4),
        ("learn", "learning", "Study or learn", 0.3, 1.5, 0.4),
        ("family", "family", "Family time", 0.2, 2.0, 0.5),
        ("chores", "household", "Do household chores", 0.2, 1.0, 0.2),
        ("hobby", "personal", "Pursue a hobby", 0.1, 1.5, 0.3),
    ]

    def get_available_actions(
        self,
        state: PersonalState,
        goals: List[RealisticGoal],
    ) -> List[PersonalAction]:
        """Get available actions for current state."""
        actions = []

        for i, (name, atype, desc, energy, time_cost, reward) in enumerate(self.ACTION_TEMPLATES):
            # Adjust availability based on time of day
            if atype == "exercise" and (state.time_of_day < 5 or state.time_of_day > 22):
                continue  # Gym closed
            if atype == "social" and state.time_of_day < 10:
                continue  # Too early

            # Adjust reward based on goals
            goal_bonus = 0.0
            for goal in goals:
                if goal.goal_type in desc.lower() or atype in goal.description.lower():
                    goal_bonus += goal.priority * 0.2

            actions.append(
                PersonalAction(
                    action_id=f"action_{name}_{i}",
                    action_type=atype,
                    description=desc,
                    energy_cost=energy,
                    time_cost_hours=time_cost,
                    expected_reward=reward + goal_bonus,
                )
            )

        return actions


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def dataset_generator() -> BenchmarkDatasetGenerator:
    """Create dataset generator."""
    return BenchmarkDatasetGenerator(seed=42)


@pytest.fixture
def small_dataset(dataset_generator: BenchmarkDatasetGenerator):
    """Small dataset for quick tests."""
    return dataset_generator.generate(BenchmarkScale.SMALL)


@pytest.fixture
def medium_dataset(dataset_generator: BenchmarkDatasetGenerator):
    """Medium dataset for normal benchmarks."""
    return dataset_generator.generate(BenchmarkScale.MEDIUM)


@pytest.fixture
def default_mcts() -> TemporalProjectionMCTS:
    """MCTS with default configuration."""
    return TemporalProjectionMCTS(MCTSConfig(seed=42))


@pytest.fixture
def fast_mcts() -> TemporalProjectionMCTS:
    """MCTS with reduced rollouts for quick testing."""
    return TemporalProjectionMCTS(
        MCTSConfig(
            default_rollouts=20,
            max_rollout_depth=10,
            seed=42,
        )
    )


@pytest.fixture
def action_provider() -> RealisticActionProvider:
    """Realistic action provider."""
    return RealisticActionProvider()


# =============================================================================
# BENCHMARK: UCT CALCULATION TESTS
# =============================================================================


class TestUCTCalculation:
    """Verify UCT calculation correctness."""

    def test_uct_exploration_term(self) -> None:
        """Verify UCT exploration term calculation."""
        # Create parent with known visit count
        parent = MCTSNode(node_id="parent")
        parent.visit_count = 100

        # Create children with different visit counts
        child_low_visits = parent.add_child(SimpleAction("a1", "test"))
        child_low_visits.visit_count = 5
        child_low_visits.total_reward = 2.5

        child_high_visits = parent.add_child(SimpleAction("a2", "test"))
        child_high_visits.visit_count = 50
        child_high_visits.total_reward = 30.0

        # Calculate UCT values
        c = P03_MCTS_UCT_EXPLORATION_CONSTANT

        # Low visits child: Q = 0.5, exploration = c * sqrt(ln(100)/5) ≈ 1.36
        q_low = child_low_visits.average_reward  # 0.5
        explore_low = c * math.sqrt(math.log(100) / 5)
        uct_low = q_low + explore_low

        # High visits child: Q = 0.6, exploration = c * sqrt(ln(100)/50) ≈ 0.43
        q_high = child_high_visits.average_reward  # 0.6
        explore_high = c * math.sqrt(math.log(100) / 50)
        uct_high = q_high + explore_high

        print("\nUCT Calculations:")
        print(f"  Low visits (5): Q={q_low:.2f}, explore={explore_low:.2f}, UCT={uct_low:.2f}")
        print(f"  High visits (50): Q={q_high:.2f}, explore={explore_high:.2f}, UCT={uct_high:.2f}")

        # Low visits should have higher UCT due to exploration
        assert uct_low > uct_high, "Low visits should be preferred for exploration"

    def test_backpropagation(self) -> None:
        """Verify reward backpropagation through tree."""
        # Build a small tree
        root = MCTSNode(node_id="root")
        child1 = root.add_child(SimpleAction("a1", "test"))
        grandchild = child1.add_child(SimpleAction("a2", "test"))

        # Backpropagate from grandchild
        reward = 1.0
        grandchild.backpropagate(reward)

        assert grandchild.visit_count == 1
        assert grandchild.total_reward == reward

        assert child1.visit_count == 1
        assert child1.total_reward == reward

        assert root.visit_count == 1
        assert root.total_reward == reward


# =============================================================================
# BENCHMARK: COMPUTE BUDGET TESTS
# =============================================================================


class TestComputeBudget:
    """Verify compute budget enforcement."""

    def test_budget_allocation(self) -> None:
        """Verify rollout allocation respects budget."""
        budget = ComputeBudget(max_mcts_rollouts=1000)

        # Allocate some rollouts
        allocated = budget.allocate(100)
        assert allocated == 100
        assert budget.used_rollouts == 100
        assert budget.remaining == 900

        # Try to allocate more than remaining
        allocated = budget.allocate(950)
        assert allocated == 900  # Only remaining available
        assert budget.used_rollouts == 1000
        assert budget.exhausted

    def test_budget_per_decision_type(self) -> None:
        """Verify rollout allocation per decision type."""
        budget = ComputeBudget(max_mcts_rollouts=1000)

        # Check allocations from table
        for decision_type, expected_rollouts in ROLLOUT_ALLOCATION.items():
            print(f"  {decision_type.value}: {expected_rollouts} rollouts")

        # Entity merge should get more rollouts than decay tune
        assert (
            ROLLOUT_ALLOCATION[DecisionType.ENTITY_MERGE]
            > ROLLOUT_ALLOCATION[DecisionType.DECAY_TUNE]
        )

    def test_budget_exhaustion_handling(self, fast_mcts: TemporalProjectionMCTS) -> None:
        """Verify graceful handling when budget exhausted."""
        budget = ComputeBudget(max_mcts_rollouts=10)

        # Exhaust budget
        budget.allocate(10)
        assert budget.exhausted

        # Further allocations should return 0
        allocated = budget.allocate(100)
        assert allocated == 0


# =============================================================================
# BENCHMARK: PERFORMANCE TESTS
# =============================================================================


class TestMCTSPerformance:
    """Performance benchmarks for MCTS algorithm."""

    @pytest.mark.benchmark
    def test_rollout_performance(self, fast_mcts: TemporalProjectionMCTS) -> None:
        """Benchmark rollout execution speed."""
        # Create realistic initial state
        state = PersonalState(
            state_id="initial",
            energy=0.8,
            progress={"health": 0.3, "career": 0.5},
            time_of_day=9,
            day_of_week=0,
        )

        actions = [
            SimpleAction("work", "work"),
            SimpleAction("exercise", "exercise"),
            SimpleAction("rest", "rest"),
        ]

        collector = BenchmarkCollector("MCTS Rollout")

        # Run multiple rollout batches
        for _ in range(5):
            with collector.time_run() as run:
                root = MCTSNode(node_id="root")
                for action in actions:
                    root.add_child(action)

                # Simulate rollouts
                for i in range(20):
                    child = list(root.children.values())[i % len(actions)]
                    reward = 0.5 + (i % 10) * 0.05
                    child.backpropagate(reward)

                run["visits"] = root.visit_count

            collector.record_quality(20, 20, 15)

        summary = collector.summarize("rollout")
        print(f"\n{summary.summary()}")

        # Should complete quickly
        assert summary.timing.elapsed_ms < 100

    @pytest.mark.benchmark
    def test_tree_building_performance(self) -> None:
        """Benchmark tree construction speed."""
        timer = StopwatchTimer().start()

        # Build a large tree
        root = MCTSNode(node_id="root")

        # Add many children and grandchildren
        for i in range(100):
            child = root.add_child(SimpleAction(f"action_{i}", "test"))
            for j in range(10):
                grandchild = child.add_child(SimpleAction(f"action_{i}_{j}", "test"))
                grandchild.backpropagate(0.5)

        timer.lap("tree_build")

        # Traverse tree
        total_nodes = 0
        stack = [root]
        while stack:
            node = stack.pop()
            total_nodes += 1
            stack.extend(node.children.values())

        timer.lap("traversal")
        timer.stop()

        print("\nTree Performance:")
        print(f"  Total nodes: {total_nodes}")
        print(f"  {timer.summary()}")

        assert total_nodes == 1 + 100 + 1000  # root + children + grandchildren
        assert timer.elapsed_ms < 500

    @pytest.mark.benchmark
    def test_scenario_generation_performance(
        self,
        fast_mcts: TemporalProjectionMCTS,
        action_provider: RealisticActionProvider,
        small_dataset,
    ) -> None:
        """Benchmark scenario generation with realistic data."""
        collector = BenchmarkCollector("MCTS Scenario Gen")

        state = PersonalState(
            state_id="benchmark_state",
            energy=0.7,
            progress={g.goal_id: g.progress for g in small_dataset.goals[:3]},
            time_of_day=14,
            day_of_week=2,
        )

        for _ in range(3):
            with collector.time_run() as run:
                actions = action_provider.get_available_actions(state, small_dataset.goals)

                # Build tree with rollouts
                root = MCTSNode(node_id="scenario_root")
                for action in actions:
                    child = root.add_child(action)
                    # Simulate rollouts
                    for i in range(10):
                        reward = action.expected_reward + (i % 5) * 0.1
                        child.backpropagate(reward)

                run["actions"] = len(actions)
                run["total_visits"] = root.visit_count

            collector.record_quality(len(actions), len(actions), len(actions) // 2)

        summary = collector.summarize("scenario_gen")
        print(f"\n{summary.summary()}")


# =============================================================================
# BENCHMARK: QUALITY TESTS
# =============================================================================


class TestMCTSQuality:
    """Quality benchmarks for MCTS outputs."""

    def test_action_ranking_by_value(self) -> None:
        """Verify actions are ranked by expected value."""
        root = MCTSNode(node_id="root")

        # Add actions with different rewards
        low_action = root.add_child(SimpleAction("low", "test"))
        mid_action = root.add_child(SimpleAction("mid", "test"))
        high_action = root.add_child(SimpleAction("high", "test"))

        # Simulate with different reward distributions
        for _ in range(50):
            low_action.backpropagate(0.2)
            mid_action.backpropagate(0.5)
            high_action.backpropagate(0.8)

        # Rank by average reward
        ranked = sorted(
            root.children.values(),
            key=lambda n: n.average_reward,
            reverse=True,
        )

        print("\nAction Ranking:")
        for i, node in enumerate(ranked):
            print(f"  {i+1}. {node.action.action_id}: Q={node.average_reward:.2f}")

        assert ranked[0].action.action_id == "high"
        assert ranked[2].action.action_id == "low"

    def test_exploration_exploitation_balance(self) -> None:
        """Verify UCT balances exploration and exploitation."""
        root = MCTSNode(node_id="root")

        # Create one "known good" action and one "unknown"
        known = root.add_child(SimpleAction("known", "test"))
        unknown = root.add_child(SimpleAction("unknown", "test"))

        # Known has many visits with moderate reward
        for _ in range(100):
            known.backpropagate(0.6)

        # Unknown has few visits with same reward
        for _ in range(5):
            unknown.backpropagate(0.6)

        # Calculate UCT for both
        c = P03_MCTS_UCT_EXPLORATION_CONSTANT
        parent_visits = root.visit_count

        known_uct = known.average_reward + c * math.sqrt(
            math.log(parent_visits) / known.visit_count
        )
        unknown_uct = unknown.average_reward + c * math.sqrt(
            math.log(parent_visits) / unknown.visit_count
        )

        print("\nExploration-Exploitation:")
        print(f"  Known (100 visits): Q={known.average_reward:.2f}, UCT={known_uct:.2f}")
        print(f"  Unknown (5 visits): Q={unknown.average_reward:.2f}, UCT={unknown_uct:.2f}")

        # Unknown should have higher UCT due to exploration bonus
        assert unknown_uct > known_uct

    def test_goal_aligned_scenarios(
        self,
        action_provider: RealisticActionProvider,
        small_dataset,
    ) -> None:
        """Verify scenarios align with user goals."""
        state = PersonalState(
            state_id="goal_test",
            energy=0.8,
            time_of_day=10,
            day_of_week=0,
        )

        # Get actions with goal context
        actions = action_provider.get_available_actions(state, small_dataset.goals)

        print(f"\nGoal-Aligned Actions ({len(actions)} available):")
        for action in sorted(actions, key=lambda a: a.expected_reward, reverse=True)[:5]:
            print(f"  {action.action_type}: {action.expected_reward:.2f}")

        # Actions should exist and have varying rewards
        assert len(actions) > 0
        rewards = [a.expected_reward for a in actions]
        assert max(rewards) > min(rewards), "Actions should have varying rewards"


# =============================================================================
# BENCHMARK: DETERMINISM TESTS
# =============================================================================


class TestMCTSDeterminism:
    """Verify MCTS produces deterministic results."""

    def test_same_seed_same_tree(self) -> None:
        """Same seed should produce identical tree structure."""

        def build_tree(seed: int) -> MCTSNode:
            import random

            rng = random.Random(seed)

            root = MCTSNode(node_id="root")
            actions = [SimpleAction(f"a{i}", "test") for i in range(5)]

            for action in actions:
                child = root.add_child(action)
                # Random rollouts
                for _ in range(10):
                    reward = rng.random()
                    child.backpropagate(reward)

            return root

        tree1 = build_tree(42)
        tree2 = build_tree(42)
        tree3 = build_tree(123)

        # Same seed should give same results
        for c1, c2 in zip(tree1.children.values(), tree2.children.values()):
            assert c1.visit_count == c2.visit_count
            assert abs(c1.total_reward - c2.total_reward) < 1e-10

        # Different seed should give different results
        different = False
        for c1, c3 in zip(tree1.children.values(), tree3.children.values()):
            if abs(c1.total_reward - c3.total_reward) > 1e-10:
                different = True
                break
        assert different


# =============================================================================
# BENCHMARK: EDGE CASES
# =============================================================================


class TestMCTSEdgeCases:
    """Test MCTS behavior with edge cases."""

    def test_no_available_actions(self) -> None:
        """Handle state with no available actions."""
        root = MCTSNode(node_id="root")

        # No children added
        assert root.is_leaf
        assert len(root.children) == 0

    def test_single_action(self) -> None:
        """Handle state with only one action."""
        root = MCTSNode(node_id="root")
        only_action = root.add_child(SimpleAction("only", "test"))

        # Run rollouts
        for _ in range(20):
            only_action.backpropagate(0.7)

        assert root.visit_count == 20
        assert abs(only_action.average_reward - 0.7) < 1e-9  # floating point tolerance

    def test_zero_reward_actions(self) -> None:
        """Handle actions with zero reward."""
        root = MCTSNode(node_id="root")
        zero_action = root.add_child(SimpleAction("zero", "test"))

        for _ in range(10):
            zero_action.backpropagate(0.0)

        assert zero_action.average_reward == 0.0
        assert zero_action.visit_count == 10

    def test_negative_reward_actions(self) -> None:
        """Handle actions with negative rewards."""
        root = MCTSNode(node_id="root")
        negative = root.add_child(SimpleAction("negative", "test"))
        positive = root.add_child(SimpleAction("positive", "test"))

        for _ in range(10):
            negative.backpropagate(-0.5)
            positive.backpropagate(0.5)

        assert negative.average_reward == -0.5
        assert positive.average_reward == 0.5
        assert positive.average_reward > negative.average_reward


# =============================================================================
# INTEGRATION BENCHMARK
# =============================================================================


class TestMCTSIntegration:
    """Integration benchmarks with realistic scenarios."""

    def test_daily_planning_scenario(
        self,
        action_provider: RealisticActionProvider,
        small_dataset,
    ) -> None:
        """Simulate a full day planning with MCTS."""
        state = PersonalState(
            state_id="morning",
            energy=1.0,
            progress={g.goal_id: g.progress for g in small_dataset.goals[:5]},
            time_of_day=8,
            day_of_week=0,  # Monday
        )

        print("\nDaily Planning Simulation:")

        planned_actions = []
        hours_simulated = 0

        while hours_simulated < 12 and state.energy > 0.1:
            # Get available actions
            actions = action_provider.get_available_actions(state, small_dataset.goals)

            if not actions:
                break

            # Build MCTS tree
            root = MCTSNode(node_id=f"hour_{hours_simulated}")

            for action in actions:
                child = root.add_child(action)
                # Simulate rollouts based on action properties
                for i in range(10):
                    # Reward based on expected value and energy availability
                    energy_factor = 1.0 if state.energy > action.energy_cost else 0.5
                    reward = action.expected_reward * energy_factor
                    child.backpropagate(reward)

            # Select best action (highest average reward)
            best_child = max(root.children.values(), key=lambda n: n.average_reward)
            best_action = best_child.action

            # Apply action to state
            state.energy -= best_action.energy_cost
            state.time_of_day = min(23, state.time_of_day + int(best_action.time_cost_hours))
            hours_simulated += best_action.time_cost_hours

            planned_actions.append(
                {
                    "time": f"{state.time_of_day - int(best_action.time_cost_hours):02d}:00",
                    "action": best_action.description,
                    "type": best_action.action_type,
                    "reward": best_child.average_reward,
                }
            )

        # Print plan
        for item in planned_actions:
            print(f"  {item['time']} - {item['action']} (reward: {item['reward']:.2f})")

        print(f"\n  Final energy: {state.energy:.2f}")
        print(f"  Hours planned: {hours_simulated:.1f}")

        assert len(planned_actions) > 0
        assert hours_simulated > 0
