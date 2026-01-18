"""
Dream Models — Data models for DreamExplorer outputs.

This module defines the core data models for M22 DreamExplorer:
- Insight: Creative insights from bisociative graph traversal
- CounterfactualScenario: What-if scenarios from CPN
- ProspectiveMemory: Future intentions and reminders
- RoutineOptimization: Behavioral pattern improvements

References:
- M8_EXECUTION.md Issue 8.1.3: M22 DreamExplorer scaffold
- Dossier section 4.6: R5 Dream-Like Exploration (REM)
- Dossier section 7.4.5: M22 DreamExplorer

TIMESTAMP CONVENTION: All timestamps use MILLISECONDS since Unix epoch.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, List, Optional, Tuple

if TYPE_CHECKING:
    from k0.modules.consolidation.algorithms.routine_detector import RoutineCandidate
    from k0.modules.consolidation.dream.intent_signals import IntentSignal


class InsightType(str, Enum):
    """Types of insights from dream exploration."""

    COUNTERFACTUAL = "COUNTERFACTUAL"  # What-if analysis
    PREDICTION = "PREDICTION"  # Future event prediction
    ASSOCIATION = "ASSOCIATION"  # Non-obvious connection
    ANOMALY = "ANOMALY"  # Unusual pattern detection
    PATTERN = "PATTERN"  # Recurring behavior pattern
    TREND = "TREND"  # Emerging trend discovery


class ScenarioType(str, Enum):
    """Types of counterfactual scenarios."""

    UPWARD = "UPWARD"  # Better outcome scenario
    DOWNWARD = "DOWNWARD"  # Worse outcome scenario
    SEMIFACTUAL = "SEMIFACTUAL"  # Different path, same outcome


@dataclass(frozen=True)
class Insight:
    """
    R5 insight from dream exploration.

    Represents a creative insight discovered through BGT-SM
    (Bisociative Graph Traversal for Semantic Memory).

    Frozen dataclass for immutability after creation.

    Attributes:
        insight_id: Unique identifier (ULID)
        insight_type: Classification of insight type
        description: Human-readable description of the insight
        confidence: Confidence score (0.0 to 1.0)
        supporting_evidence: Tuple of episode/event IDs that support this
        novelty_score: How unexpected/novel this insight is (0.0 to 1.0)
        created_at: Creation timestamp in MILLISECONDS
        concept_a_id: First concept in the association (optional)
        concept_b_id: Second concept in the association (optional)
        pmi_score: Pointwise mutual information score (optional)
        coherence_score: Logical coherence of the insight (0.0 to 1.0)
        semantic_distance: Distance between concepts (0.0 to 1.0)
        relevance_score: How relevant to user context (0.0 to 1.0)
        actionability_score: How actionable the insight is (0.0 to 1.0)
        serendipity_score: novelty × relevance × actionability (0.0 to 1.0)
    """

    insight_id: str
    insight_type: str
    description: str
    confidence: float
    supporting_evidence: Tuple[str, ...]
    novelty_score: float
    created_at: int
    concept_a_id: Optional[str] = None
    concept_b_id: Optional[str] = None
    pmi_score: Optional[float] = None
    coherence_score: float = 0.5
    semantic_distance: float = 0.0
    relevance_score: float = 0.5
    actionability_score: float = 0.5
    serendipity_score: float = 0.0

    @classmethod
    def create(
        cls,
        insight_id: str,
        insight_type: str,
        description: str,
        confidence: float,
        supporting_evidence: List[str],
        novelty_score: float,
        concept_a_id: Optional[str] = None,
        concept_b_id: Optional[str] = None,
        pmi_score: Optional[float] = None,
        coherence_score: float = 0.5,
        semantic_distance: float = 0.0,
        relevance_score: float = 0.5,
        actionability_score: float = 0.5,
    ) -> Insight:
        """Factory method with validation and serendipity calculation."""
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not 0.0 <= novelty_score <= 1.0:
            raise ValueError("novelty_score must be between 0 and 1")

        # Calculate serendipity: novelty × relevance × actionability
        # Per Issue 8.1.10: serendipity > 0.6 threshold for quality
        serendipity = novelty_score * relevance_score * actionability_score

        return cls(
            insight_id=insight_id,
            insight_type=insight_type,
            description=description,
            confidence=confidence,
            supporting_evidence=tuple(supporting_evidence),
            novelty_score=novelty_score,
            created_at=int(time.time() * 1000),
            concept_a_id=concept_a_id,
            concept_b_id=concept_b_id,
            semantic_distance=semantic_distance,
            relevance_score=relevance_score,
            actionability_score=actionability_score,
            serendipity_score=serendipity,
            pmi_score=pmi_score,
            coherence_score=coherence_score,
        )


@dataclass(frozen=True)
class CounterfactualScenario:
    """
    What-if scenario generated by CPN (Causal Perturbation Network).

    Explores alternative outcomes by perturbing episode parameters.

    Attributes:
        scenario_id: Unique identifier (ULID)
        scenario_type: UPWARD, DOWNWARD, or SEMIFACTUAL
        base_episode_id: Episode this scenario is based on
        perturbation_target: What was changed (entity, action, time)
        original_outcome: Description of actual outcome
        counterfactual_outcome: Description of hypothetical outcome
        plausibility: How realistic the scenario is (0.0 to 1.0)
        success_probability: Probability of desired outcome (0.0 to 1.0)
        utility_delta: Expected utility change vs original
        created_at: Creation timestamp in MILLISECONDS
    """

    scenario_id: str
    scenario_type: str
    base_episode_id: str
    perturbation_target: str
    original_outcome: str
    counterfactual_outcome: str
    plausibility: float
    success_probability: float
    utility_delta: float
    created_at: int

    @classmethod
    def create(
        cls,
        scenario_id: str,
        scenario_type: str,
        base_episode_id: str,
        perturbation_target: str,
        original_outcome: str,
        counterfactual_outcome: str,
        plausibility: float,
        success_probability: float,
        utility_delta: float,
    ) -> CounterfactualScenario:
        """Factory method with validation."""
        if not 0.0 <= plausibility <= 1.0:
            raise ValueError("plausibility must be between 0 and 1")
        if not 0.0 <= success_probability <= 1.0:
            raise ValueError("success_probability must be between 0 and 1")

        return cls(
            scenario_id=scenario_id,
            scenario_type=scenario_type,
            base_episode_id=base_episode_id,
            perturbation_target=perturbation_target,
            original_outcome=original_outcome,
            counterfactual_outcome=counterfactual_outcome,
            plausibility=plausibility,
            success_probability=success_probability,
            utility_delta=utility_delta,
            created_at=int(time.time() * 1000),
        )


@dataclass(frozen=True)
class ProspectiveMemory:
    """
    Future intention/reminder from SPC-UQ (Sparse Predictive Coding).

    Represents something the user may want to remember or do.

    Attributes:
        prosp_id: Unique identifier (ULID)
        intention_type: GOAL, REMINDER, DEADLINE, HABIT
        description: Human-readable description
        trigger_condition: When/what triggers this memory
        action_to_take: Suggested action
        deadline_ts: Optional deadline timestamp in MILLISECONDS
        importance: Importance score (0.0 to 1.0)
        confidence: Confidence in the prediction (0.0 to 1.0)
        source_episode_id: Episode that generated this prediction
        created_at: Creation timestamp in MILLISECONDS
    """

    prosp_id: str
    intention_type: str
    description: str
    trigger_condition: str
    action_to_take: str
    importance: float
    confidence: float
    source_episode_id: Optional[str]
    created_at: int
    deadline_ts: Optional[int] = None
    # Issue 7.7: Temporal anchor context
    anchor_time_utc: Optional[int] = None  # When user expressed the intention (MILLISECONDS)
    original_temporal_expr: Optional[str] = None  # Original expression ("next week", "tomorrow")

    @classmethod
    def create(
        cls,
        prosp_id: str,
        intention_type: str,
        description: str,
        trigger_condition: str,
        action_to_take: str,
        importance: float,
        confidence: float,
        source_episode_id: Optional[str] = None,
        deadline_ts: Optional[int] = None,
        anchor_time_utc: Optional[int] = None,
        original_temporal_expr: Optional[str] = None,
    ) -> ProspectiveMemory:
        """Factory method with validation."""
        if not 0.0 <= importance <= 1.0:
            raise ValueError("importance must be between 0 and 1")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")

        return cls(
            prosp_id=prosp_id,
            intention_type=intention_type,
            description=description,
            trigger_condition=trigger_condition,
            action_to_take=action_to_take,
            importance=importance,
            confidence=confidence,
            source_episode_id=source_episode_id,
            created_at=int(time.time() * 1000),
            deadline_ts=deadline_ts,
            anchor_time_utc=anchor_time_utc,
            original_temporal_expr=original_temporal_expr,
        )


@dataclass(frozen=True)
class RoutineOptimization:
    """
    Routine improvement suggestion from TDL-HCO.

    Identifies bottlenecks in repeated behavioral patterns.

    Attributes:
        routine_id: Unique identifier (ULID)
        routine_name: Name of the routine being optimized
        bottleneck_step: Description of the bottleneck
        bottleneck_position: Position in routine sequence
        value_drop: Value lost at bottleneck (negative number)
        suggested_action: Suggested improvement
        expected_improvement: Expected value gain from optimization
        confidence: Confidence in the suggestion (0.0 to 1.0)
        created_at: Creation timestamp in MILLISECONDS
    """

    routine_id: str
    routine_name: str
    bottleneck_step: str
    bottleneck_position: int
    value_drop: float
    suggested_action: str
    expected_improvement: float
    confidence: float
    created_at: int

    @classmethod
    def create(
        cls,
        routine_id: str,
        routine_name: str,
        bottleneck_step: str,
        bottleneck_position: int,
        value_drop: float,
        suggested_action: str,
        expected_improvement: float,
        confidence: float,
    ) -> RoutineOptimization:
        """Factory method with validation."""
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if bottleneck_position < 0:
            raise ValueError("bottleneck_position must be non-negative")

        return cls(
            routine_id=routine_id,
            routine_name=routine_name,
            bottleneck_step=bottleneck_step,
            bottleneck_position=bottleneck_position,
            value_drop=value_drop,
            suggested_action=suggested_action,
            expected_improvement=expected_improvement,
            confidence=confidence,
            created_at=int(time.time() * 1000),
        )


@dataclass
class DreamExplorerInput:
    """
    Input to DreamExplorer.explore() method.

    Encapsulates all data needed for dream exploration.

    Attributes:
        cycle_id: Unique cycle identifier for determinism
        tenant_id: Multi-tenant isolation
        space_id: User/family space
        recent_episodes: Recent episode clusters from R2
        kg_entities: Knowledge graph entities from R4
        kg_edges: Knowledge graph edges from R4
        event_states: Event states with importance scores from R1
    """

    cycle_id: str
    tenant_id: str
    space_id: str
    recent_episodes: List = field(default_factory=list)
    kg_entities: List = field(default_factory=list)
    kg_edges: List = field(default_factory=list)
    event_states: List = field(default_factory=list)


@dataclass
class DreamExplorerOutput:
    """
    Output from DreamExplorer.explore() method.

    Contains all generated dream exploration artifacts.

    Attributes:
        insights: Generated insights sorted by novelty
        counterfactuals: Counterfactual scenarios
        prospective_memories: Future intention predictions
        routine_optimizations: Routine improvement suggestions
        routine_candidates: Detected routines from RoutineDetector (GAP-003)
        intent_signals: Intent signals detected from events (GAP-001)
        mcts_decisions_evaluated: Number of MCTS tree evaluations
        compute_ms: Time spent in exploration (milliseconds)
    """

    insights: List[Insight] = field(default_factory=list)
    counterfactuals: List[CounterfactualScenario] = field(default_factory=list)
    prospective_memories: List[ProspectiveMemory] = field(default_factory=list)
    routine_optimizations: List[RoutineOptimization] = field(default_factory=list)
    routine_candidates: List["RoutineCandidate"] = field(default_factory=list)
    intent_signals: List["IntentSignal"] = field(default_factory=list)
    mcts_decisions_evaluated: int = 0
    compute_ms: int = 0

    @property
    def total_outputs(self) -> int:
        """Total number of outputs generated."""
        return (
            len(self.insights)
            + len(self.counterfactuals)
            + len(self.prospective_memories)
            + len(self.routine_optimizations)
            + len(self.routine_candidates)
            + len(self.intent_signals)
        )

    @property
    def is_empty(self) -> bool:
        """True if no outputs were generated."""
        return self.total_outputs == 0
