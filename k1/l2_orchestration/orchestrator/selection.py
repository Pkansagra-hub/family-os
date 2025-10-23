"""
Module: k1.l2_orchestration.orchestrator.selection
Purpose: Phase 2 of 3-Phase Orchestration - MADM 6-factor agent selection

ADR References:
- ADR-0006: 3-Phase Orchestration (main architecture)
- ADR-0006b: Multi-Criteria Agent Scoring (MADM implementation)
- ADR-0024: Performance Budgets (P95 <5ms target)

This module implements Multi-Attribute Decision Making (MADM) to score agent proposals
using 6 weighted factors:
  1. Confidence (weight 10.0) - Agent self-reported capability match
  2. Latency (weight 8.0) - Estimated execution time
  3. Cost (weight -5.0) - Cheaper is better (negative weight)
  4. Parallelism (weight 3.0) - Can run in parallel with other steps
  5. Track record (weight 2.0) - Historical success rate
  6. Busy penalty (weight -4.0) - Current load (inverse)

Performance Budget: <5ms P95, 3ms typical
Research: MADM (Hwang & Yoon 1981), TOPSIS method

Input:
  - List[Proposal] from negotiation phase
  - ScoringWeights configuration (customizable per session)
  - Historical performance data (from K0 metrics)

Output:
  - TaskAssignment (winning agent + score + tie-break reason)
  - Rejected proposals with scores (for telemetry)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class TieBreakStrategy(Enum):
    """Tie-breaking strategies when scores are equal"""

    RESIDENT = "RESIDENT"  # Prefer agent with SessionState loaded
    FASTEST = "FASTEST"  # Prefer lowest latency estimate
    CHEAPEST = "CHEAPEST"  # Prefer lowest cost estimate
    RANDOM = "RANDOM"  # Random selection


@dataclass
class ScoringWeights:
    """
    MADM scoring weights - customizable per session

    ADR-0006b specifies default weights:
      - confidence: 10.0 (highest - agent knows best)
      - latency: 8.0 (speed matters)
      - cost: -5.0 (negative - cheaper is better)
      - parallelism: 3.0 (parallel execution is good)
      - track_record: 2.0 (history is useful)
      - busy_penalty: -4.0 (negative - avoid overloaded agents)
    """

    confidence: float = 10.0
    latency: float = 8.0
    cost: float = -5.0
    parallelism: float = 3.0
    track_record: float = 2.0
    busy_penalty: float = -4.0


@dataclass
class Proposal:
    """
    Agent proposal from negotiation phase

    TODO: Import from k1.l2_orchestration.orchestrator.negotiation
    """

    agent_id: str
    confidence: float  # 0.0-1.0
    latency_estimate_ms: int
    cost_estimate: float
    can_parallelize: bool
    message: str
    session_resident: bool  # Has SessionState loaded


@dataclass
class TaskAssignment:
    """
    Final task assignment after selection

    TODO: Serialize to FlatBuffers for mailbox delivery
    """

    agent_id: str
    task_id: str
    score: float
    tie_break_reason: Optional[str]  # e.g., "RESIDENT", "FASTEST"
    runner_up_score: Optional[float]  # For telemetry


class Selector:
    """
    Phase 2: Multi-Attribute Decision Making (MADM) agent selection

    ADR-0006b: Scores agent proposals using 6-factor weighted formula.
    Performance: <5ms P95, 3ms typical

    Usage:
        selector = Selector(weights=ScoringWeights(), tie_break=TieBreakStrategy.RESIDENT)
        assignment = await selector.select(proposals, task_id, historical_data)

    Fallback:
      - If all scores are negative → select highest score (least bad)
      - If no proposals → return None (negotiation should handle)
      - If tie → apply tie-break strategy
    """

    def __init__(
        self,
        weights: ScoringWeights,
        tie_break: TieBreakStrategy = TieBreakStrategy.RESIDENT,
    ):
        """
        Initialize selector with scoring weights and tie-break strategy

        Args:
            weights: MADM scoring weights (see ADR-0006b for defaults)
            tie_break: Strategy for breaking score ties (default: RESIDENT)
        """
        self.weights = weights
        self.tie_break = tie_break
        # TODO: Initialize metrics
        # self.score_histogram = Histogram('orchestrator_selection_score', ...)
        # self.tie_break_counter = Counter('orchestrator_tie_breaks_total', ['strategy'])

    async def select(
        self,
        proposals: List[Proposal],
        task_id: str,
        historical_data: Dict[str, float],
    ) -> Optional[TaskAssignment]:
        """
        Select winning agent using MADM 6-factor scoring

        ADR-0006b: Weighted scoring formula
        Score = Σ(factor × weight)

        Args:
            proposals: List of agent proposals from negotiation phase
            task_id: Task identifier for assignment
            historical_data: {agent_id: success_rate} from K0 metrics

        Returns:
            TaskAssignment with winning agent, or None if no proposals

        Performance: <5ms P95
        TODO: Implement MADM scoring, normalization, tie-breaking
        """
        if not proposals:
            return None

        # TODO: 1. Normalize latency/cost to 0-1 scale
        #       - latency_norm = 1 - (latency / max_latency)
        #       - cost_norm = 1 - (cost / max_cost)

        # TODO: 2. Calculate scores for each proposal
        #       scores = []
        #       for proposal in proposals:
        #           score = (
        #               proposal.confidence * weights.confidence +
        #               latency_norm * weights.latency +
        #               cost_norm * weights.cost +
        #               (1.0 if proposal.can_parallelize else 0.0) * weights.parallelism +
        #               historical_data.get(proposal.agent_id, 0.5) * weights.track_record +
        #               busy_penalty_norm * weights.busy_penalty
        #           )
        #           scores.append((proposal, score))

        # TODO: 3. Sort by score descending
        #       scores.sort(key=lambda x: x[1], reverse=True)

        # TODO: 4. Check for tie (top 2 scores within 0.01)
        #       if len(scores) > 1 and abs(scores[0][1] - scores[1][1]) < 0.01:
        #           winner = self._apply_tie_break(scores[0][0], scores[1][0])
        #       else:
        #           winner = scores[0][0]

        # TODO: 5. Build TaskAssignment
        #       assignment = TaskAssignment(
        #           agent_id=winner.agent_id,
        #           task_id=task_id,
        #           score=scores[0][1],
        #           tie_break_reason=...,
        #           runner_up_score=scores[1][1] if len(scores) > 1 else None
        #       )

        # TODO: 6. Emit metrics
        #       self.score_histogram.observe(scores[0][1])

        # Placeholder return
        return TaskAssignment(
            agent_id=proposals[0].agent_id,
            task_id=task_id,
            score=0.0,
            tie_break_reason=None,
            runner_up_score=None,
        )

    def _apply_tie_break(self, proposal_a: Proposal, proposal_b: Proposal) -> Proposal:
        """
        Apply tie-breaking strategy when scores are equal

        ADR-0006b: 4 tie-break strategies
          - RESIDENT: Prefer agent with SessionState loaded (cache hit)
          - FASTEST: Prefer lowest latency estimate
          - CHEAPEST: Prefer lowest cost estimate
          - RANDOM: Random selection (for load balancing)

        Args:
            proposal_a: First proposal (tied)
            proposal_b: Second proposal (tied)

        Returns:
            Winning proposal after tie-break

        TODO: Implement all 4 strategies
        """
        if self.tie_break == TieBreakStrategy.RESIDENT:
            # TODO: Prefer session_resident=True
            return proposal_a if proposal_a.session_resident else proposal_b

        elif self.tie_break == TieBreakStrategy.FASTEST:
            # TODO: Prefer lower latency_estimate_ms
            return (
                proposal_a
                if proposal_a.latency_estimate_ms < proposal_b.latency_estimate_ms
                else proposal_b
            )

        elif self.tie_break == TieBreakStrategy.CHEAPEST:
            # TODO: Prefer lower cost_estimate
            return (
                proposal_a
                if proposal_a.cost_estimate < proposal_b.cost_estimate
                else proposal_b
            )

        elif self.tie_break == TieBreakStrategy.RANDOM:
            # TODO: Random selection using secrets module (cryptographically secure)
            import random

            return random.choice([proposal_a, proposal_b])

        # Default: return first proposal
        return proposal_a

    def _normalize_latency(self, latencies: List[int]) -> List[float]:
        """
        Normalize latency estimates to 0-1 scale (higher is better)

        Formula: 1 - (latency / max_latency)

        Args:
            latencies: List of latency estimates in milliseconds

        Returns:
            List of normalized values (0.0-1.0)

        TODO: Handle edge case where all latencies are equal (return [1.0, 1.0, ...])
        """
        max_latency = max(latencies) if latencies else 1
        return [1.0 - (lat / max_latency) for lat in latencies]

    def _normalize_cost(self, costs: List[float]) -> List[float]:
        """
        Normalize cost estimates to 0-1 scale (higher is better, i.e., cheaper)

        Formula: 1 - (cost / max_cost)

        Args:
            costs: List of cost estimates

        Returns:
            List of normalized values (0.0-1.0)

        TODO: Handle edge case where all costs are zero (return [1.0, 1.0, ...])
        """
        max_cost = max(costs) if costs else 1.0
        return [1.0 - (cost / max_cost) for cost in costs]

    def _calculate_busy_penalty(self, agent_id: str, mailbox_depth: int) -> float:
        """
        Calculate busy penalty based on agent mailbox depth

        ADR-0006b: Penalize overloaded agents
        Penalty = 1 - (mailbox_depth / 100)  # Normalize to 0-1

        Args:
            agent_id: Agent identifier
            mailbox_depth: Current mailbox message count

        Returns:
            Normalized penalty (0.0-1.0, higher is better = less busy)

        TODO: Query agent registry for current mailbox depth
        """
        # TODO: Implement mailbox depth lookup
        # depth = await self.agent_registry.get_mailbox_depth(agent_id)
        # return max(0.0, 1.0 - (depth / 100.0))
        return 1.0  # Placeholder
