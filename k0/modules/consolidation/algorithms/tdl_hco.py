"""
TDL-HCO — Temporal Difference Learning for Habit/Cognitive Optimization.

This module implements motor rehearsal optimization using Temporal Difference
learning to identify bottlenecks in repeated behavioral patterns (routines).

Algorithm:
- TD(0) for value function V(s) learning
- Bottleneck detection via negative value gradients
- Routine optimization suggestions with expected improvement

References:
- M8_EXECUTION.md Issue 8.1.11: TDL-HCO Motor Rehearsal for Habits
- Dossier Section 4.6.6: Motor Rehearsal Analog (TDL-HCO)
- Dossier Appendix C.6.4: TDL-HCO Algorithm Details

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import hashlib
import logging
import math
import random
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable

if TYPE_CHECKING:
    from k0.modules.consolidation.dream.models import RoutineOptimization

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS (from M8_EXECUTION.md Issue 8.1.11)
# =============================================================================

# TD learning rate (alpha) per dossier
P03_TDL_LEARNING_RATE = 0.1

# Discount factor (gamma) per dossier
P03_TDL_DISCOUNT_FACTOR = 0.9

# Bottleneck detection threshold: V(s_{t+1}) - V(s_t) < -2.0
P03_TDL_BOTTLENECK_THRESHOLD = -2.0

# Minimum routine length for analysis
P03_TDL_MIN_ROUTINE_LENGTH = 3

# Minimum occurrences to consider a pattern a "routine"
P03_TDL_MIN_ROUTINE_OCCURRENCES = 3

# Maximum routines to analyze per cycle
P03_TDL_MAX_ROUTINES_PER_CYCLE = 10

# Maximum optimizations to return per cycle
P03_TDL_MAX_OPTIMIZATIONS_PER_CYCLE = 5


# =============================================================================
# PROTOCOLS
# =============================================================================


@runtime_checkable
class RoutineStep(Protocol):
    """Protocol for steps in a routine."""

    step_id: str
    step_name: str
    step_index: int


@runtime_checkable
class Routine(Protocol):
    """Protocol for a behavioral routine."""

    routine_id: str
    routine_name: str
    steps: List[RoutineStep]


# =============================================================================
# CONFIGURATION
# =============================================================================


@dataclass
class TDLConfig:
    """
    Configuration for TDL-HCO algorithm.

    Attributes:
        learning_rate: TD learning rate alpha (default 0.1)
        discount_factor: TD discount factor gamma (default 0.9)
        bottleneck_threshold: Value drop threshold for bottleneck detection (default -2.0)
        min_routine_length: Minimum steps to qualify as routine (default 3)
        min_routine_occurrences: Minimum times a routine must be observed (default 3)
        max_routines: Maximum routines to analyze per cycle (default 10)
        max_optimizations: Maximum optimizations to return (default 5)
        seed: RNG seed for determinism
    """

    learning_rate: float = P03_TDL_LEARNING_RATE
    discount_factor: float = P03_TDL_DISCOUNT_FACTOR
    bottleneck_threshold: float = P03_TDL_BOTTLENECK_THRESHOLD
    min_routine_length: int = P03_TDL_MIN_ROUTINE_LENGTH
    min_routine_occurrences: int = P03_TDL_MIN_ROUTINE_OCCURRENCES
    max_routines: int = P03_TDL_MAX_ROUTINES_PER_CYCLE
    max_optimizations: int = P03_TDL_MAX_OPTIMIZATIONS_PER_CYCLE
    seed: Optional[int] = None

    def __post_init__(self) -> None:
        """Validate configuration."""
        if not 0 < self.learning_rate <= 1:
            raise ValueError("learning_rate must be in (0, 1]")
        if not 0 < self.discount_factor <= 1:
            raise ValueError("discount_factor must be in (0, 1]")
        if self.min_routine_length < 2:
            raise ValueError("min_routine_length must be at least 2")
        if self.min_routine_occurrences < 1:
            raise ValueError("min_routine_occurrences must be at least 1")


# =============================================================================
# ROUTINE STEP DATA MODELS
# =============================================================================


@dataclass
class RoutineStepData:
    """
    A single step in a routine with execution metrics.

    Attributes:
        step_id: Unique step identifier
        step_name: Human-readable step name
        step_index: Position in routine (0-indexed)
        duration_ms: Time spent on this step (ms)
        success: Whether step completed successfully
        reward: Reward signal for this step (derived from success/duration)
    """

    step_id: str
    step_name: str
    step_index: int
    duration_ms: int = 0
    success: bool = True
    reward: float = 0.0


@dataclass
class RoutineExecution:
    """
    A single execution instance of a routine.

    Represents one observation of a routine being performed.

    Attributes:
        execution_id: Unique execution identifier
        routine_id: ID of the routine template
        routine_name: Name of the routine
        steps: Sequence of steps in this execution
        total_duration_ms: Total execution time
        completed: Whether routine completed fully
        success: Whether routine achieved its goal
        episode_id: Source episode (if from episodic memory)
        timestamp_ms: When this execution occurred
    """

    execution_id: str
    routine_id: str
    routine_name: str
    steps: List[RoutineStepData]
    total_duration_ms: int = 0
    completed: bool = True
    success: bool = True
    episode_id: Optional[str] = None
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))


@dataclass
class RoutineTemplate:
    """
    A recurring behavioral routine pattern.

    Aggregates multiple executions of the same routine.

    Attributes:
        routine_id: Unique routine identifier
        routine_name: Human-readable routine name
        canonical_steps: Standard sequence of step names
        execution_count: Number of times observed
        avg_duration_ms: Average execution time
        success_rate: Historical success rate
        executions: Recent execution instances
    """

    routine_id: str
    routine_name: str
    canonical_steps: List[str]
    execution_count: int = 0
    avg_duration_ms: int = 0
    success_rate: float = 1.0
    executions: List[RoutineExecution] = field(default_factory=list)


# =============================================================================
# VALUE FUNCTION
# =============================================================================


@dataclass
class ValueFunction:
    """
    Value function V(s) learned via TD(0).

    Maps state identifiers to learned value estimates.
    State is identified by (routine_id, step_index, step_name) tuple.

    Attributes:
        values: Dictionary of state -> value
        visit_counts: Number of times each state was visited
        learning_rate: TD learning rate alpha
        discount_factor: TD discount factor gamma
    """

    values: Dict[str, float] = field(default_factory=dict)
    visit_counts: Dict[str, int] = field(default_factory=dict)
    learning_rate: float = P03_TDL_LEARNING_RATE
    discount_factor: float = P03_TDL_DISCOUNT_FACTOR

    def get_state_key(
        self,
        routine_id: str,
        step_index: int,
        step_name: str,
    ) -> str:
        """Generate unique state key from routine + step."""
        return f"{routine_id}:{step_index}:{step_name}"

    def get_value(self, state_key: str) -> float:
        """Get current value estimate for state."""
        return self.values.get(state_key, 0.0)

    def get_visit_count(self, state_key: str) -> int:
        """Get visit count for state."""
        return self.visit_counts.get(state_key, 0)

    def td_update(
        self,
        state: str,
        reward: float,
        next_state: Optional[str],
    ) -> float:
        """
        TD(0) update: V(s) <- V(s) + alpha * [r + gamma * V(s') - V(s)]

        Per Issue 8.1.11 TD Update Rule:
        - alpha = 0.1 (learning rate)
        - gamma = 0.9 (discount factor)

        Args:
            state: Current state key
            reward: Immediate reward
            next_state: Next state key (None for terminal)

        Returns:
            TD error (delta) for this update
        """
        current_value = self.get_value(state)
        next_value = self.get_value(next_state) if next_state else 0.0

        # TD error: delta = r + gamma * V(s') - V(s)
        td_error = reward + self.discount_factor * next_value - current_value

        # Update: V(s) <- V(s) + alpha * delta
        new_value = current_value + self.learning_rate * td_error
        self.values[state] = new_value

        # Track visits
        self.visit_counts[state] = self.get_visit_count(state) + 1

        return td_error

    def compute_value_gradient(
        self,
        state: str,
        next_state: str,
    ) -> float:
        """
        Compute value gradient: delta_V = V(s_{t+1}) - V(s_t)

        Used for bottleneck detection per Issue 8.1.11:
        Bottleneck if delta_V < -2.0

        Args:
            state: Current state key
            next_state: Next state key

        Returns:
            Value gradient (positive = improving, negative = bottleneck)
        """
        return self.get_value(next_state) - self.get_value(state)


# =============================================================================
# BOTTLENECK DETECTION
# =============================================================================


@dataclass(frozen=True)
class Bottleneck:
    """
    Detected bottleneck in a routine.

    Represents a step where value drops significantly,
    indicating a problem or inefficiency.

    Attributes:
        routine_id: ID of the routine containing bottleneck
        routine_name: Name of the routine
        step_index: Position of bottleneck step
        step_name: Name of bottleneck step
        value_drop: Value gradient (negative)
        current_value: V(s_t) at bottleneck
        next_value: V(s_{t+1}) after bottleneck
        severity: Magnitude of the bottleneck (abs(value_drop))
    """

    routine_id: str
    routine_name: str
    step_index: int
    step_name: str
    value_drop: float
    current_value: float
    next_value: float
    severity: float


# =============================================================================
# OPTIMIZATION SUGGESTIONS
# =============================================================================


@dataclass(frozen=True)
class TDLOptimization:
    """
    Routine optimization suggestion from TDL-HCO.

    Generated when a bottleneck is detected in a routine.

    Attributes:
        optimization_id: Unique identifier (ULID-like)
        routine_id: ID of routine to optimize
        routine_name: Name of routine
        bottleneck: Detected bottleneck
        suggested_action: Proposed improvement
        expected_improvement: Expected value gain
        confidence: Confidence in suggestion (0.0-1.0)
        rationale: Explanation of why this optimization helps
        created_at_ms: Creation timestamp
    """

    optimization_id: str
    routine_id: str
    routine_name: str
    bottleneck: Bottleneck
    suggested_action: str
    expected_improvement: float
    confidence: float
    rationale: str
    created_at_ms: int

    def to_routine_optimization(self) -> "RoutineOptimization":
        """Convert to RoutineOptimization model for DreamExplorer output."""
        from k0.modules.consolidation.dream.models import RoutineOptimization

        return RoutineOptimization.create(
            routine_id=self.routine_id,
            routine_name=self.routine_name,
            bottleneck_step=self.bottleneck.step_name,
            bottleneck_position=self.bottleneck.step_index,
            value_drop=self.bottleneck.value_drop,
            suggested_action=self.suggested_action,
            expected_improvement=self.expected_improvement,
            confidence=self.confidence,
        )


# =============================================================================
# TDL-HCO ALGORITHM
# =============================================================================


class TemporalDifferenceLearning:
    """
    Temporal Difference Learning for Habit/Cognitive Optimization.

    Implements TD(0) learning to identify bottlenecks in repeated
    behavioral patterns and suggest optimizations.

    Algorithm Overview:
    1. Extract routines from episodic memory
    2. Learn value function V(s) from routine executions
    3. Detect bottlenecks where V drops sharply (gradient < -2.0)
    4. Generate optimization suggestions for detected bottlenecks

    Usage:
        config = TDLConfig(learning_rate=0.1, discount_factor=0.9)
        tdl = TemporalDifferenceLearning(config)

        optimizations = tdl.optimize(
            routines=routine_templates,
            rng_seed=42,
        )
    """

    def __init__(self, config: Optional[TDLConfig] = None):
        """
        Initialize TDL-HCO.

        Args:
            config: TDL configuration
        """
        self.config = config or TDLConfig()
        self._value_function = ValueFunction(
            learning_rate=self.config.learning_rate,
            discount_factor=self.config.discount_factor,
        )
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @property
    def value_function(self) -> ValueFunction:
        """Get learned value function."""
        return self._value_function

    # -------------------------------------------------------------------------
    # TD Learning
    # -------------------------------------------------------------------------

    def learn_from_execution(
        self,
        execution: RoutineExecution,
    ) -> List[float]:
        """
        Learn value function from a single routine execution.

        Processes steps in order, applying TD(0) updates.

        Args:
            execution: A routine execution to learn from

        Returns:
            List of TD errors for each step
        """
        td_errors = []
        steps = execution.steps

        for i, step in enumerate(steps):
            state_key = self._value_function.get_state_key(
                execution.routine_id,
                step.step_index,
                step.step_name,
            )

            # Compute reward for this step
            reward = self._compute_step_reward(step, execution)

            # Get next state (None if terminal)
            next_state_key = None
            if i + 1 < len(steps):
                next_step = steps[i + 1]
                next_state_key = self._value_function.get_state_key(
                    execution.routine_id,
                    next_step.step_index,
                    next_step.step_name,
                )

            # TD(0) update
            td_error = self._value_function.td_update(
                state=state_key,
                reward=reward,
                next_state=next_state_key,
            )
            td_errors.append(td_error)

        return td_errors

    def _compute_step_reward(
        self,
        step: RoutineStepData,
        execution: RoutineExecution,
    ) -> float:
        """
        Compute reward signal for a step.

        Reward is based on:
        - Step success: +1.0 for success, -1.0 for failure
        - Duration efficiency: bonus for faster completion
        - Position bonus: higher reward for later steps (progress)

        Args:
            step: The step to compute reward for
            execution: The execution context

        Returns:
            Reward value for this step
        """
        reward = 0.0

        # Success/failure signal
        if step.success:
            reward += 1.0
        else:
            reward -= 1.0

        # Duration efficiency (normalized against avg)
        if execution.total_duration_ms > 0 and len(execution.steps) > 0:
            avg_step_duration = execution.total_duration_ms / len(execution.steps)
            if avg_step_duration > 0:
                # Bonus for faster than average (capped at +0.5)
                efficiency = (avg_step_duration - step.duration_ms) / avg_step_duration
                reward += max(-0.5, min(0.5, efficiency * 0.5))

        # Progress bonus (small reward for advancing in routine)
        progress = step.step_index / max(1, len(execution.steps) - 1)
        reward += progress * 0.2

        # Use step's explicit reward if provided
        if step.reward != 0.0:
            reward += step.reward

        return reward

    # -------------------------------------------------------------------------
    # Bottleneck Detection
    # -------------------------------------------------------------------------

    def detect_bottlenecks(
        self,
        routine: RoutineTemplate,
    ) -> List[Bottleneck]:
        """
        Detect bottlenecks in a routine.

        A bottleneck is a step where the value gradient is sharply negative:
        delta_V = V(s_{t+1}) - V(s_t) < threshold (default -2.0)

        Per Issue 8.1.11 bottleneck detection rule.

        Args:
            routine: Routine template to analyze

        Returns:
            List of detected bottlenecks sorted by severity
        """
        bottlenecks = []
        steps = routine.canonical_steps

        for i in range(len(steps) - 1):
            current_state = self._value_function.get_state_key(
                routine.routine_id,
                i,
                steps[i],
            )
            next_state = self._value_function.get_state_key(
                routine.routine_id,
                i + 1,
                steps[i + 1],
            )

            # Compute value gradient
            value_drop = self._value_function.compute_value_gradient(
                current_state,
                next_state,
            )

            # Check bottleneck threshold
            if value_drop < self.config.bottleneck_threshold:
                bottleneck = Bottleneck(
                    routine_id=routine.routine_id,
                    routine_name=routine.routine_name,
                    step_index=i,
                    step_name=steps[i],
                    value_drop=value_drop,
                    current_value=self._value_function.get_value(current_state),
                    next_value=self._value_function.get_value(next_state),
                    severity=abs(value_drop),
                )
                bottlenecks.append(bottleneck)

        # Sort by severity (most severe first)
        bottlenecks.sort(key=lambda b: b.severity, reverse=True)

        return bottlenecks

    # -------------------------------------------------------------------------
    # Optimization Suggestion Generation
    # -------------------------------------------------------------------------

    def generate_suggestions(
        self,
        bottlenecks: List[Bottleneck],
        routine: RoutineTemplate,
        rng: random.Random,
    ) -> List[TDLOptimization]:
        """
        Generate optimization suggestions for detected bottlenecks.

        Creates actionable suggestions to address bottlenecks.

        Args:
            bottlenecks: List of detected bottlenecks
            routine: The routine containing bottlenecks
            rng: Random number generator for IDs

        Returns:
            List of optimization suggestions
        """
        suggestions = []

        for bottleneck in bottlenecks:
            suggestion = self._create_suggestion(bottleneck, routine, rng)
            if suggestion:
                suggestions.append(suggestion)

        return suggestions

    def _create_suggestion(
        self,
        bottleneck: Bottleneck,
        routine: RoutineTemplate,
        rng: random.Random,
    ) -> Optional[TDLOptimization]:
        """
        Create an optimization suggestion for a bottleneck.

        Args:
            bottleneck: Detected bottleneck
            routine: Containing routine
            rng: Random number generator

        Returns:
            Optimization suggestion or None if cannot suggest
        """
        # Generate optimization ID
        opt_id = hashlib.sha256(
            f"{bottleneck.routine_id}:{bottleneck.step_index}:{rng.random()}".encode()
        ).hexdigest()[:26].upper()

        # Determine suggested action based on bottleneck characteristics
        suggested_action = self._determine_suggested_action(bottleneck, routine)

        # Calculate expected improvement
        # Improvement is proportional to severity but bounded by learning uncertainty
        visit_count = self._value_function.get_visit_count(
            self._value_function.get_state_key(
                bottleneck.routine_id,
                bottleneck.step_index,
                bottleneck.step_name,
            )
        )

        # Confidence based on visit count (more observations = higher confidence)
        confidence = min(1.0, 0.3 + 0.1 * math.log1p(visit_count))

        # Expected improvement scales with severity but is bounded
        expected_improvement = min(
            abs(bottleneck.value_drop) * 0.5,  # 50% recovery expected
            5.0,  # Cap at 5.0
        ) * confidence

        # Generate rationale
        rationale = self._generate_rationale(bottleneck, routine)

        return TDLOptimization(
            optimization_id=opt_id,
            routine_id=bottleneck.routine_id,
            routine_name=bottleneck.routine_name,
            bottleneck=bottleneck,
            suggested_action=suggested_action,
            expected_improvement=expected_improvement,
            confidence=confidence,
            rationale=rationale,
            created_at_ms=int(time.time() * 1000),
        )

    def _determine_suggested_action(
        self,
        bottleneck: Bottleneck,
        routine: RoutineTemplate,
    ) -> str:
        """
        Determine appropriate suggested action for a bottleneck.

        Analyzes bottleneck characteristics to propose specific improvements.

        Args:
            bottleneck: The bottleneck to address
            routine: The containing routine

        Returns:
            Human-readable suggestion
        """
        step_name = bottleneck.step_name
        step_index = bottleneck.step_index
        severity = bottleneck.severity

        # High severity bottlenecks suggest restructuring
        if severity > 4.0:
            if step_index == 0:
                return f"Consider better preparation before starting '{step_name}'"
            elif step_index == len(routine.canonical_steps) - 2:
                return f"The step '{step_name}' may need to be broken into smaller parts"
            else:
                return f"Consider reordering or removing '{step_name}' from the routine"

        # Medium severity suggests optimization
        elif severity > 2.5:
            return f"Optimize '{step_name}' by reducing decision points or automating substeps"

        # Lower severity suggests minor improvements
        else:
            next_step = routine.canonical_steps[step_index + 1] if step_index + 1 < len(routine.canonical_steps) else "next step"
            return f"Improve transition from '{step_name}' to '{next_step}'"

    def _generate_rationale(
        self,
        bottleneck: Bottleneck,
        routine: RoutineTemplate,
    ) -> str:
        """
        Generate rationale explaining why the suggestion helps.

        Args:
            bottleneck: The detected bottleneck
            routine: The containing routine

        Returns:
            Human-readable rationale
        """
        return (
            f"Step '{bottleneck.step_name}' at position {bottleneck.step_index} "
            f"shows a value drop of {bottleneck.value_drop:.2f}, indicating "
            f"this transition is causing difficulty. Historical data from "
            f"{routine.execution_count} executions suggests this is a consistent pattern."
        )

    # -------------------------------------------------------------------------
    # Main Entry Point
    # -------------------------------------------------------------------------

    def optimize(
        self,
        routines: List[RoutineTemplate],
        rng_seed: Optional[int] = None,
    ) -> List[TDLOptimization]:
        """
        Run TDL-HCO optimization on routine templates.

        Main entry point for the algorithm:
        1. Filter to routines meeting minimum criteria
        2. Learn value function from executions
        3. Detect bottlenecks
        4. Generate optimization suggestions

        Args:
            routines: List of routine templates to analyze
            rng_seed: Seed for deterministic behavior

        Returns:
            List of optimization suggestions sorted by expected improvement
        """
        start_ms = int(time.time() * 1000)

        # Initialize RNG
        seed = rng_seed if rng_seed is not None else self.config.seed
        rng = random.Random(seed)

        # Filter routines to those meeting criteria
        qualified_routines = [
            r for r in routines
            if (
                len(r.canonical_steps) >= self.config.min_routine_length
                and r.execution_count >= self.config.min_routine_occurrences
            )
        ]

        # Limit to max routines per cycle
        if len(qualified_routines) > self.config.max_routines:
            # Sort by execution count (most observed first)
            qualified_routines.sort(key=lambda r: r.execution_count, reverse=True)
            qualified_routines = qualified_routines[: self.config.max_routines]

        self._logger.debug(
            "TDL-HCO starting optimization",
            extra={
                "total_routines": len(routines),
                "qualified_routines": len(qualified_routines),
                "seed": seed,
            },
        )

        all_optimizations: List[TDLOptimization] = []

        for routine in qualified_routines:
            # Learn from all executions
            for execution in routine.executions:
                self.learn_from_execution(execution)

            # Detect bottlenecks
            bottlenecks = self.detect_bottlenecks(routine)

            if bottlenecks:
                # Generate suggestions for top bottlenecks
                suggestions = self.generate_suggestions(
                    bottlenecks[: 3],  # Top 3 bottlenecks per routine
                    routine,
                    rng,
                )
                all_optimizations.extend(suggestions)

        # Sort by expected improvement (descending)
        all_optimizations.sort(key=lambda o: o.expected_improvement, reverse=True)

        # Limit to max optimizations
        result = all_optimizations[: self.config.max_optimizations]

        compute_ms = int(time.time() * 1000) - start_ms

        self._logger.info(
            "TDL-HCO completed",
            extra={
                "routines_analyzed": len(qualified_routines),
                "optimizations_found": len(result),
                "compute_ms": compute_ms,
            },
        )

        return result

    def reset(self) -> None:
        """Reset learned value function (for testing)."""
        self._value_function = ValueFunction(
            learning_rate=self.config.learning_rate,
            discount_factor=self.config.discount_factor,
        )


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================


def extract_routines_from_episodes(
    episodes: List[Any],
    min_routine_length: int = P03_TDL_MIN_ROUTINE_LENGTH,
    min_occurrences: int = P03_TDL_MIN_ROUTINE_OCCURRENCES,
) -> List[RoutineTemplate]:
    """
    Extract routine templates from episodic memory.

    Identifies repeated behavioral patterns across episodes
    and aggregates them into routine templates.

    This is a heuristic extraction that looks for:
    1. Episodes with similar action sequences
    2. Repeated locations/times suggesting habits
    3. Entity participation patterns

    Args:
        episodes: List of episodes from episodic memory
        min_routine_length: Minimum steps to qualify as routine
        min_occurrences: Minimum times pattern must be observed

    Returns:
        List of extracted routine templates
    """
    # Track patterns: pattern_hash -> (routine_template, executions)
    patterns: Dict[str, Tuple[List[str], List[RoutineExecution]]] = {}

    for episode in episodes:
        # Extract steps from episode
        steps = _extract_steps_from_episode(episode)

        if len(steps) < min_routine_length:
            continue

        # Hash the step sequence for pattern matching
        step_names = [s.step_name for s in steps]
        pattern_hash = hashlib.sha256(":".join(step_names).encode()).hexdigest()[:16]

        # Get episode metadata
        episode_id = getattr(episode, "episode_id", None) or str(hash(episode))

        # Create execution record
        execution = RoutineExecution(
            execution_id=f"exec_{episode_id}",
            routine_id=f"routine_{pattern_hash}",
            routine_name=_generate_routine_name(step_names),
            steps=steps,
            total_duration_ms=_estimate_episode_duration(episode),
            completed=True,
            success=True,
            episode_id=episode_id,
            timestamp_ms=getattr(episode, "start_time_ms", int(time.time() * 1000)),
        )

        # Track pattern
        if pattern_hash not in patterns:
            patterns[pattern_hash] = (step_names, [])
        patterns[pattern_hash][1].append(execution)

    # Convert to routine templates
    templates = []
    for pattern_hash, (step_names, executions) in patterns.items():
        if len(executions) >= min_occurrences:
            avg_duration = sum(e.total_duration_ms for e in executions) // len(executions)
            success_rate = sum(1 for e in executions if e.success) / len(executions)

            template = RoutineTemplate(
                routine_id=f"routine_{pattern_hash}",
                routine_name=_generate_routine_name(step_names),
                canonical_steps=step_names,
                execution_count=len(executions),
                avg_duration_ms=avg_duration,
                success_rate=success_rate,
                executions=executions,
            )
            templates.append(template)

    return templates


def _extract_steps_from_episode(episode: Any) -> List[RoutineStepData]:
    """
    Extract routine steps from an episode.

    Heuristically extracts meaningful steps from episode data.

    Args:
        episode: Episode object

    Returns:
        List of routine steps
    """
    steps = []

    # Try to extract from action_sequence attribute
    actions = getattr(episode, "action_sequence", None)
    if actions and isinstance(actions, (list, tuple)):
        for i, action in enumerate(actions):
            step_name = str(action) if not hasattr(action, "name") else action.name
            steps.append(
                RoutineStepData(
                    step_id=f"step_{i}",
                    step_name=step_name,
                    step_index=i,
                )
            )
        return steps

    # Try to extract from events attribute
    events = getattr(episode, "events", None)
    if events and isinstance(events, (list, tuple)):
        for i, event in enumerate(events):
            event_type = getattr(event, "event_type", None) or getattr(event, "type", f"event_{i}")
            steps.append(
                RoutineStepData(
                    step_id=f"step_{i}",
                    step_name=str(event_type),
                    step_index=i,
                )
            )
        return steps

    # Fallback: create synthetic steps from episode summary
    summary = getattr(episode, "summary", None)
    if summary:
        # Split summary into pseudo-steps
        parts = str(summary).split(".")[:5]  # Max 5 steps from summary
        for i, part in enumerate(parts):
            if part.strip():
                steps.append(
                    RoutineStepData(
                        step_id=f"step_{i}",
                        step_name=part.strip()[:50],  # Truncate long names
                        step_index=i,
                    )
                )

    return steps


def _generate_routine_name(step_names: List[str]) -> str:
    """Generate a human-readable routine name from step sequence."""
    if not step_names:
        return "Unknown Routine"

    # Use first and last step for name
    first = step_names[0][:20]
    last = step_names[-1][:20]

    if len(step_names) == 1:
        return first
    elif len(step_names) == 2:
        return f"{first} -> {last}"
    else:
        return f"{first} -> ... -> {last} ({len(step_names)} steps)"


def _estimate_episode_duration(episode: Any) -> int:
    """Estimate episode duration in milliseconds."""
    start = getattr(episode, "start_time_ms", 0)
    end = getattr(episode, "end_time_ms", 0)

    if end > start:
        return end - start

    # Default 1 hour if no timestamps
    return 3600000
