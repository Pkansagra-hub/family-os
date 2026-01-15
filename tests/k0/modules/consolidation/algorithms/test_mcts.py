"""
TPN-MCTS Unit Tests — Issue 8.1.5

Test Categories:
1. MCTSConfig validation
2. MCTSNode operations (add_child, backpropagate)
3. UCT calculation
4. Rollout allocation
5. Early termination detection
6. ComputeBudget tracking
7. Scenario generation

References:
- M8_EXECUTION.md Issue 8.1.5: TPN-MCTS forward simulation
- M8_EXECUTION.md Issue 8.1.6: Adaptive rollout allocation
- Dossier §4.6.2: Forward Simulation (TPN-MCTS)
- Dossier Appendix C.6.2: TPN-MCTS Algorithm Details
"""

from __future__ import annotations

import math
from typing import List

import pytest

from k0.modules.consolidation.algorithms.mcts import (
    P03_MCTS_UCT_EXPLORATION_CONSTANT,
    ROLLOUT_ALLOCATION,
    ComputeBudget,
    DecisionType,
    MCTSConfig,
    MCTSNode,
    MCTSScenario,
    SimpleAction,
    SimpleState,
    TemporalProjectionMCTS,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def default_config() -> MCTSConfig:
    """Default MCTS configuration."""
    return MCTSConfig()


@pytest.fixture
def strict_config() -> MCTSConfig:
    """Strict MCTS config with tight thresholds."""
    return MCTSConfig(
        clear_winner_threshold=0.80,
        ci_width_threshold=0.03,
        max_total_rollouts=500,
    )


@pytest.fixture
def sample_actions() -> List[SimpleAction]:
    """Sample actions for testing."""
    return [
        SimpleAction(action_id="action-1", action_type="move"),
        SimpleAction(action_id="action-2", action_type="wait"),
        SimpleAction(action_id="action-3", action_type="interact"),
    ]


@pytest.fixture
def sample_state() -> SimpleState:
    """Sample state for testing."""
    return SimpleState(
        state_id="state-001",
        features={"energy": 0.8, "progress": 0.3},
    )


@pytest.fixture
def mcts(default_config: MCTSConfig) -> TemporalProjectionMCTS:
    """MCTS instance with default config."""
    return TemporalProjectionMCTS(config=default_config)


# =============================================================================
# TEST: MCTSConfig Validation
# =============================================================================


class TestMCTSConfigValidation:
    """Test MCTSConfig dataclass validation."""

    def test_default_values(self) -> None:
        """MCTSConfig should have sensible defaults."""
        config = MCTSConfig()

        assert config.exploration_constant == P03_MCTS_UCT_EXPLORATION_CONSTANT
        assert config.max_rollout_depth == 30
        assert config.default_rollouts == 100
        assert config.discount_factor == 0.9
        assert config.max_total_rollouts == 1000

    def test_custom_values(self) -> None:
        """MCTSConfig should accept custom values."""
        config = MCTSConfig(
            exploration_constant=2.0,
            max_rollout_depth=50,
            default_rollouts=50,
        )

        assert config.exploration_constant == 2.0
        assert config.max_rollout_depth == 50
        assert config.default_rollouts == 50

    def test_invalid_exploration_constant(self) -> None:
        """MCTSConfig should reject invalid exploration_constant."""
        with pytest.raises(ValueError, match="exploration_constant"):
            MCTSConfig(exploration_constant=0)

        with pytest.raises(ValueError, match="exploration_constant"):
            MCTSConfig(exploration_constant=-1)

    def test_invalid_max_rollout_depth(self) -> None:
        """MCTSConfig should reject invalid max_rollout_depth."""
        with pytest.raises(ValueError, match="max_rollout_depth"):
            MCTSConfig(max_rollout_depth=0)

    def test_invalid_discount_factor(self) -> None:
        """MCTSConfig should reject discount_factor outside (0, 1]."""
        with pytest.raises(ValueError, match="discount_factor"):
            MCTSConfig(discount_factor=0)

        with pytest.raises(ValueError, match="discount_factor"):
            MCTSConfig(discount_factor=1.1)


# =============================================================================
# TEST: ComputeBudget
# =============================================================================


class TestComputeBudget:
    """Test ComputeBudget tracking."""

    def test_initial_state(self) -> None:
        """ComputeBudget should start with zero used."""
        budget = ComputeBudget(max_mcts_rollouts=1000)

        assert budget.used_rollouts == 0
        assert budget.remaining == 1000
        assert not budget.exhausted

    def test_allocate_full(self) -> None:
        """Allocation should return full request when available."""
        budget = ComputeBudget(max_mcts_rollouts=1000)

        allocated = budget.allocate(100)

        assert allocated == 100
        assert budget.used_rollouts == 100
        assert budget.remaining == 900

    def test_allocate_partial(self) -> None:
        """Allocation should return partial when limited."""
        budget = ComputeBudget(max_mcts_rollouts=50)

        allocated = budget.allocate(100)

        assert allocated == 50
        assert budget.used_rollouts == 50
        assert budget.exhausted

    def test_can_allocate(self) -> None:
        """can_allocate should check availability."""
        budget = ComputeBudget(max_mcts_rollouts=100)
        budget.allocate(80)

        assert budget.can_allocate(20)
        assert not budget.can_allocate(30)

    def test_exhausted_state(self) -> None:
        """exhausted should be True when fully used."""
        budget = ComputeBudget(max_mcts_rollouts=100)
        budget.allocate(100)

        assert budget.exhausted
        assert budget.remaining == 0


# =============================================================================
# TEST: MCTSNode
# =============================================================================


class TestMCTSNode:
    """Test MCTSNode operations."""

    def test_root_node(self) -> None:
        """Root node should have correct properties."""
        root = MCTSNode(node_id="root")

        assert root.is_root
        assert root.is_leaf
        assert root.visit_count == 0
        assert root.average_reward == 0.0
        assert root.depth == 0

    def test_add_child(self) -> None:
        """add_child should create child node."""
        root = MCTSNode(node_id="root")
        action = SimpleAction(action_id="move")

        child = root.add_child(action)

        assert child.action == action
        assert child.parent == root
        assert child.depth == 1
        assert not root.is_leaf
        assert "move" in root.children

    def test_add_child_duplicate(self) -> None:
        """Adding same action twice should return existing child."""
        root = MCTSNode(node_id="root")
        action = SimpleAction(action_id="move")

        child1 = root.add_child(action)
        child2 = root.add_child(action)

        assert child1 is child2
        assert len(root.children) == 1

    def test_backpropagate(self) -> None:
        """backpropagate should update visit counts and rewards."""
        root = MCTSNode(node_id="root")
        action = SimpleAction(action_id="move")
        child = root.add_child(action)

        child.backpropagate(1.5)

        assert child.visit_count == 1
        assert child.total_reward == 1.5
        assert root.visit_count == 1
        assert root.total_reward == 1.5

    def test_average_reward(self) -> None:
        """average_reward should return Q-value."""
        node = MCTSNode(node_id="test")
        node.visit_count = 4
        node.total_reward = 2.0

        assert node.average_reward == 0.5


# =============================================================================
# TEST: UCT Calculation
# =============================================================================


class TestUCTCalculation:
    """Test UCT selection formula."""

    def test_unvisited_node_infinite(
        self,
        mcts: TemporalProjectionMCTS,
    ) -> None:
        """Unvisited nodes should have infinite UCT."""
        parent = MCTSNode(node_id="parent")
        parent.visit_count = 10
        child = MCTSNode(node_id="child")
        child.visit_count = 0

        uct = mcts.compute_uct(child, parent)

        assert uct == float("inf")

    def test_uct_formula(
        self,
        mcts: TemporalProjectionMCTS,
    ) -> None:
        """UCT should follow Q/N + c*sqrt(ln(Np)/N)."""
        parent = MCTSNode(node_id="parent")
        parent.visit_count = 100
        child = MCTSNode(node_id="child")
        child.visit_count = 10
        child.total_reward = 5.0

        uct = mcts.compute_uct(child, parent)

        # Expected: 0.5 + 1.414 * sqrt(ln(100)/10)
        exploitation = 5.0 / 10.0
        exploration = P03_MCTS_UCT_EXPLORATION_CONSTANT * math.sqrt(math.log(100) / 10)
        expected = exploitation + exploration

        assert abs(uct - expected) < 0.001

    def test_uct_select_unvisited_first(
        self,
        mcts: TemporalProjectionMCTS,
    ) -> None:
        """uct_select should prioritize unvisited children."""
        root = MCTSNode(node_id="root")
        root.visit_count = 10

        action1 = SimpleAction(action_id="visited")
        child1 = root.add_child(action1)
        child1.visit_count = 5
        child1.total_reward = 2.0

        action2 = SimpleAction(action_id="unvisited")
        child2 = root.add_child(action2)
        child2.visit_count = 0

        selected = mcts.uct_select(root)

        assert selected == child2


# =============================================================================
# TEST: Rollout Allocation
# =============================================================================


class TestRolloutAllocation:
    """Test decision importance classification."""

    def test_allocation_table(self) -> None:
        """Rollout allocation should follow dossier table."""
        assert ROLLOUT_ALLOCATION[DecisionType.ENTITY_MERGE] == 100
        assert ROLLOUT_ALLOCATION[DecisionType.CAUSAL_EDGE] == 50
        assert ROLLOUT_ALLOCATION[DecisionType.CLUSTER_ASSIGN] == 30
        assert ROLLOUT_ALLOCATION[DecisionType.DECAY_TUNE] == 10

    def test_classify_base_rollouts(
        self,
        mcts: TemporalProjectionMCTS,
    ) -> None:
        """Classification should return base rollouts for decision type."""
        rollouts = mcts.classify_decision_importance(DecisionType.ENTITY_MERGE)
        assert rollouts == 100

        rollouts = mcts.classify_decision_importance(DecisionType.DECAY_TUNE)
        assert rollouts == 10

    def test_classify_boost_family_member(
        self,
        mcts: TemporalProjectionMCTS,
    ) -> None:
        """Family member entities should boost rollouts."""
        context = {"entity_type": "FAMILY_MEMBER"}
        rollouts = mcts.classify_decision_importance(
            DecisionType.CLUSTER_ASSIGN,
            context=context,
        )

        # 30 * 1.5 = 45
        assert rollouts == 45

    def test_classify_reduce_low_confidence(
        self,
        mcts: TemporalProjectionMCTS,
    ) -> None:
        """Low confidence contexts should reduce rollouts."""
        context = {"confidence": 0.5}  # Below 0.60
        rollouts = mcts.classify_decision_importance(
            DecisionType.ENTITY_MERGE,
            context=context,
        )

        # 100 * 0.5 = 50
        assert rollouts == 50

    def test_classify_cap_at_100(
        self,
        mcts: TemporalProjectionMCTS,
    ) -> None:
        """Rollouts should be capped at 100."""
        context = {"entity_type": "FAMILY_MEMBER"}
        rollouts = mcts.classify_decision_importance(
            DecisionType.ENTITY_MERGE,  # 100 base
            context=context,  # Would be 150 with boost
        )

        assert rollouts == 100


# =============================================================================
# TEST: Early Termination
# =============================================================================


class TestEarlyTermination:
    """Test early termination detection."""

    def test_clear_winner(
        self,
        mcts: TemporalProjectionMCTS,
    ) -> None:
        """Clear winner (>90% visits) should trigger termination."""
        root = MCTSNode(node_id="root")
        root.visit_count = 100  # Root must have visits for termination check

        action1 = SimpleAction(action_id="best")
        child1 = root.add_child(action1)
        child1.visit_count = 95

        action2 = SimpleAction(action_id="other")
        child2 = root.add_child(action2)
        child2.visit_count = 5

        should_stop, reason = mcts.should_terminate_early(root)

        assert should_stop
        assert reason == "clear_winner"

    def test_no_clear_winner(
        self,
        mcts: TemporalProjectionMCTS,
    ) -> None:
        """Close race should not trigger termination."""
        root = MCTSNode(node_id="root")
        root.visit_count = 100  # Root must have visits

        action1 = SimpleAction(action_id="a")
        child1 = root.add_child(action1)
        child1.visit_count = 55

        action2 = SimpleAction(action_id="b")
        child2 = root.add_child(action2)
        child2.visit_count = 45

        should_stop, reason = mcts.should_terminate_early(root)

        assert not should_stop
        assert reason is None

    def test_leaf_node_no_termination(
        self,
        mcts: TemporalProjectionMCTS,
    ) -> None:
        """Leaf nodes should not trigger termination."""
        root = MCTSNode(node_id="root")
        root.visit_count = 10

        should_stop, reason = mcts.should_terminate_early(root)

        assert not should_stop


# =============================================================================
# TEST: Simulation
# =============================================================================


class TestSimulation:
    """Test MCTS simulation."""

    def test_simulate_returns_scenarios(
        self,
        mcts: TemporalProjectionMCTS,
        sample_state: SimpleState,
        sample_actions: List[SimpleAction],
    ) -> None:
        """simulate should return list of scenarios."""
        scenarios = mcts.simulate(
            initial_state=sample_state,
            available_actions=sample_actions,
            rng_seed=42,
        )

        assert isinstance(scenarios, list)
        # May or may not have scenarios depending on rollouts
        for s in scenarios:
            assert isinstance(s, MCTSScenario)

    def test_simulate_deterministic(
        self,
        mcts: TemporalProjectionMCTS,
        sample_state: SimpleState,
        sample_actions: List[SimpleAction],
    ) -> None:
        """Same seed should produce same results."""
        scenarios1 = mcts.simulate(
            initial_state=sample_state,
            available_actions=sample_actions,
            rng_seed=42,
        )
        scenarios2 = mcts.simulate(
            initial_state=sample_state,
            available_actions=sample_actions,
            rng_seed=42,
        )

        ids1 = [s.scenario_id for s in scenarios1]
        ids2 = [s.scenario_id for s in scenarios2]

        assert ids1 == ids2

    def test_simulate_respects_budget(
        self,
        sample_state: SimpleState,
        sample_actions: List[SimpleAction],
    ) -> None:
        """simulate should respect compute budget."""
        config = MCTSConfig(max_total_rollouts=50)
        mcts = TemporalProjectionMCTS(config=config)
        budget = ComputeBudget(max_mcts_rollouts=50)

        # First simulation exhausts budget
        mcts.simulate(
            initial_state=sample_state,
            available_actions=sample_actions,
            budget=budget,
            decision_type=DecisionType.ENTITY_MERGE,  # 100 requested
        )

        assert budget.used_rollouts == 50  # Capped at budget

        # Second simulation gets nothing
        scenarios = mcts.simulate(
            initial_state=sample_state,
            available_actions=sample_actions,
            budget=budget,
        )

        assert scenarios == []

    def test_simulate_empty_actions(
        self,
        mcts: TemporalProjectionMCTS,
        sample_state: SimpleState,
    ) -> None:
        """Empty action list should return empty scenarios."""
        scenarios = mcts.simulate(
            initial_state=sample_state,
            available_actions=[],
            rng_seed=42,
        )

        assert scenarios == []


# =============================================================================
# TEST: MCTSScenario
# =============================================================================


class TestMCTSScenario:
    """Test MCTSScenario dataclass."""

    def test_create_scenario(self) -> None:
        """MCTSScenario.create should produce valid scenario."""
        scenario = MCTSScenario.create(
            scenario_id="test-001",
            action_sequence=["move", "wait"],
            predicted_outcome="Success",
            success_probability=0.8,
            expected_reward=5.5,
            plausibility=0.7,
            visit_count=10,
            depth=2,
        )

        assert scenario.scenario_id == "test-001"
        assert scenario.action_sequence == ("move", "wait")
        assert scenario.success_probability == 0.8
        assert scenario.depth == 2

    def test_create_clamps_probability(self) -> None:
        """MCTSScenario.create should clamp probabilities to [0, 1]."""
        scenario = MCTSScenario.create(
            scenario_id="test-002",
            action_sequence=["x"],
            predicted_outcome="",
            success_probability=1.5,  # Out of range
            expected_reward=0,
            plausibility=-0.1,  # Out of range
            visit_count=1,
            depth=1,
        )

        assert scenario.success_probability == 1.0
        assert scenario.plausibility == 0.0
