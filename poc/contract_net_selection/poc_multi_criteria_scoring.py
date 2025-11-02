"""
PoC 2.2: Multi-Criteria Proposal Scoring - <5ms P95 Selection

Objective: Prove proposal scoring and agent selection in <5ms

Module: k1/l2_orchestration/orchestrator/selection.py
Reference ADR: ADR-0006b (Multi-Criteria Scoring Engine)

Performance SLO Target: <5ms P95 scoring latency
"""

import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np


@dataclass
class Proposal:
    """Agent proposal from Phase 1 (Negotiation)"""

    agent_id: str
    task_id: str
    estimated_latency_ms: int
    estimated_cost: float
    confidence: float
    strategy: str
    tools: List[str]
    reasoning: str


@dataclass
class ScoringWeights:
    """Weights for 6-factor scoring function"""

    confidence: float = 10.0  # Primary: agent confidence in success
    latency: float = 8.0  # Secondary: execution speed
    cost: float = -5.0  # Penalty: execution cost
    parallelism: float = 3.0  # Bonus: can parallelize
    track_record: float = 2.0  # Historical success rate
    load_penalty: float = -4.0  # Penalty: agent busy/loaded


@dataclass
class ScoreResult:
    """Scoring result for a proposal"""

    agent_id: str
    raw_score: float
    normalized_score: float
    confidence_score: float
    latency_score: float
    cost_score: float
    parallelism_score: float
    track_record_score: float
    load_score: float
    reasoning: str


class MultiCriteriaScoringEngine:
    """Scores proposals using weighted multi-criteria function"""

    def __init__(
        self,
        weights: Optional[ScoringWeights] = None,
        max_latency_ms: int = 5000,
        max_cost_usd: float = 10.0,
    ):
        self.weights = weights or ScoringWeights()
        self.max_latency_ms = max_latency_ms
        self.max_cost_usd = max_cost_usd
        self.scoring_count = 0

    def score_proposals(
        self, proposals: List[Proposal], task_requirements: Dict = None
    ) -> List[ScoreResult]:
        """Score all proposals and return sorted results"""
        if not proposals:
            return []

        task_requirements = task_requirements or {}
        scores = []

        for proposal in proposals:
            score_result = self._score_single_proposal(proposal, task_requirements, len(proposals))
            scores.append(score_result)

        # Sort by normalized score (descending)
        scores.sort(key=lambda x: x.normalized_score, reverse=True)
        self.scoring_count += len(proposals)

        return scores

    def _score_single_proposal(
        self, proposal: Proposal, task_requirements: Dict, total_proposals: int
    ) -> ScoreResult:
        """Score a single proposal using 6-factor formula"""

        # 1. Confidence score (0-1, already normalized)
        confidence_score = proposal.confidence

        # 2. Latency score (normalized: lower is better)
        latency_score = max(0, 1 - (proposal.estimated_latency_ms / self.max_latency_ms))

        # 3. Cost score (normalized: lower is better)
        cost_score = max(0, 1 - (proposal.estimated_cost / self.max_cost_usd))

        # 4. Parallelism score (bonus if strategy is parallel)
        parallelism_score = 0.8 if proposal.strategy == "parallel" else 0.5

        # 5. Track record score (simulated: higher confidence = better track record)
        track_record_score = proposal.confidence * 0.9

        # 6. Load penalty score (inverse: fewer proposals = agent less busy)
        # If only 1 proposal, agent is not competing (load=0)
        # If many proposals, agent is competing with others (load increases)
        load_score = 1 - min(0.5, total_proposals / 20)

        # Weighted combination
        raw_score = (
            self.weights.confidence * confidence_score
            + self.weights.latency * latency_score
            + self.weights.cost * cost_score
            + self.weights.parallelism * parallelism_score
            + self.weights.track_record * track_record_score
            + self.weights.load_penalty * (1 - load_score)
        )

        # Normalize to 0-100 range
        max_possible_score = (
            abs(self.weights.confidence)
            + abs(self.weights.latency)
            + abs(self.weights.parallelism)
            + abs(self.weights.track_record)
        )
        normalized_score = (raw_score / max_possible_score) * 100 if max_possible_score > 0 else 0

        reasoning = (
            f"conf={confidence_score:.2f} "
            f"lat={latency_score:.2f} "
            f"cost={cost_score:.2f} "
            f"par={parallelism_score:.2f} "
            f"track={track_record_score:.2f} "
            f"load={load_score:.2f}"
        )

        return ScoreResult(
            agent_id=proposal.agent_id,
            raw_score=raw_score,
            normalized_score=normalized_score,
            confidence_score=confidence_score,
            latency_score=latency_score,
            cost_score=cost_score,
            parallelism_score=parallelism_score,
            track_record_score=track_record_score,
            load_score=load_score,
            reasoning=reasoning,
        )

    def select_winner(self, scores: List[ScoreResult]) -> Optional[ScoreResult]:
        """Select best proposal (highest score)"""
        if not scores:
            return None
        return scores[0]

    def apply_tie_breaking(
        self, scores: List[ScoreResult], score_threshold: float = 1.0
    ) -> List[ScoreResult]:
        """Apply tie-breaking when scores are close"""
        if not scores or len(scores) < 2:
            return scores

        tied = [scores[0]]

        for i in range(1, len(scores)):
            diff = abs(scores[0].normalized_score - scores[i].normalized_score)
            if diff <= score_threshold:
                tied.append(scores[i])
            else:
                break

        # Tie-breaking order:
        # 1. By confidence (higher = better)
        # 2. By latency (lower = better)
        # 3. By cost (lower = better)
        # 4. By agent_id (deterministic/alphabetical)
        tied.sort(key=lambda x: (-x.confidence_score, x.latency_score, x.cost_score, x.agent_id))

        return tied


class SelectionPoC:
    """Benchmark harness for multi-criteria selection"""

    def __init__(self, num_proposals: int = 5, num_rounds: int = 1000):
        self.num_proposals = num_proposals
        self.num_rounds = num_rounds
        self.engine = MultiCriteriaScoringEngine()
        self.results = []

    def _generate_proposals(self, task_id: str) -> List[Proposal]:
        """Generate synthetic proposals for benchmarking"""
        proposals = []
        for i in range(self.num_proposals):
            proposal = Proposal(
                agent_id=f"agent_{i:02d}",
                task_id=task_id,
                estimated_latency_ms=int(np.random.uniform(100, 5000)),
                estimated_cost=np.random.uniform(0.1, 10.0),
                confidence=np.random.uniform(0.6, 1.0),
                strategy=np.random.choice(["parallel", "sequential", "hybrid"]),
                tools=[f"tool_{j}" for j in range(np.random.randint(1, 5))],
                reasoning=f"Agent {i} proposal",
            )
            proposals.append(proposal)
        return proposals

    def benchmark_scoring(self) -> Dict:
        """Run benchmark and measure scoring latency"""
        latencies = []

        for round_num in range(self.num_rounds):
            proposals = self._generate_proposals(f"task_{round_num:04d}")

            start = time.perf_counter()
            scores = self.engine.score_proposals(proposals)
            winner = self.engine.select_winner(scores)
            elapsed_ms = (time.perf_counter() - start) * 1000

            latencies.append(elapsed_ms)

        self.results = np.array(latencies)
        return self._compute_metrics()

    def _compute_metrics(self) -> Dict:
        """Compute performance metrics"""
        return {
            "p50": float(np.percentile(self.results, 50)),
            "p95": float(np.percentile(self.results, 95)),
            "p99": float(np.percentile(self.results, 99)),
            "mean": float(np.mean(self.results)),
            "std": float(np.std(self.results)),
            "min": float(np.min(self.results)),
            "max": float(np.max(self.results)),
            "count": len(self.results),
            "slo_passed": float(np.percentile(self.results, 95)) < 5.0,
        }


async def main():
    """Run selection PoC benchmark"""
    print("=" * 70)
    print("PoC 2.2: Multi-Criteria Proposal Scoring")
    print("=" * 70)
    print()

    poc = SelectionPoC(num_proposals=5, num_rounds=1000)
    print(f"Running {poc.num_rounds} selection rounds with {poc.num_proposals} proposals each...")

    metrics = poc.benchmark_scoring()

    print()
    print("LATENCY METRICS (ms):")
    print(
        f"  P50:    {metrics['p50']:7.3f}  ✅"
        if metrics["p50"] < 5
        else f"  P50:    {metrics['p50']:7.3f}  ⚠️"
    )
    print(
        f"  P95:    {metrics['p95']:7.3f}  ✅"
        if metrics["p95"] < 5
        else f"  P95:    {metrics['p95']:7.3f}  ❌"
    )
    print(f"  P99:    {metrics['p99']:7.3f}")
    print(f"  Mean:   {metrics['mean']:7.3f}ms")
    print(f"  StdDev: {metrics['std']:7.3f}ms")
    print(f"  Min:    {metrics['min']:7.3f}ms")
    print(f"  Max:    {metrics['max']:7.3f}ms")
    print()
    print(f"SLO (<5ms P95): {'✅ PASSED' if metrics['slo_passed'] else '❌ FAILED'}")
    print(f"Samples: {metrics['count']}")
    print()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
    asyncio.run(main())
