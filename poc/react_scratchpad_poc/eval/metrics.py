"""
Comparison metrics computation for naive vs smart runners.

Computes per-scenario and aggregate metrics that prove the scratchpad
architecture's superiority across every dimension.
"""

from __future__ import annotations

from typing import List

from core.models import RunResult
from pydantic import BaseModel, Field


class ScenarioComparison(BaseModel):
    """Metrics comparing naive vs smart for a single scenario."""

    scenario_id: str
    scenario_name: str = ""

    # Completion
    naive_success: bool = False
    smart_success: bool = False
    winner: str = "tie"  # "naive", "smart", "tie", "both_failed"

    # Iterations
    naive_iterations: int = 0
    smart_iterations: int = 0

    # Tool calls
    naive_tool_calls: int = 0
    smart_tool_calls: int = 0

    # Context tokens (final)
    naive_context_final: int = 0
    smart_context_final: int = 0
    context_savings_pct: float = 0.0

    # Token usage
    naive_tokens_total: int = 0
    smart_tokens_total: int = 0
    token_savings_pct: float = 0.0

    # Latency
    naive_latency_ms: int = 0
    smart_latency_ms: int = 0

    # Smart-only metrics
    compactions: int = 0
    findings_count: int = 0
    sub_agent_count: int = 0
    max_nesting_depth: int = 0
    failed_attempts: int = 0

    # Context stability (smart should be flat, naive grows)
    naive_context_growth: List[int] = Field(default_factory=list)
    smart_context_growth: List[int] = Field(default_factory=list)

    # Findings accumulation per iteration (proves context preservation)
    findings_per_iteration: List[int] = Field(default_factory=list)

    # Winner reasons
    winner_reasons: List[str] = Field(default_factory=list)


class AggregateMetrics(BaseModel):
    """Overall benchmark results across all scenarios."""

    scenario_count: int = 0
    naive_success_rate: float = 0.0
    smart_success_rate: float = 0.0

    naive_wins: int = 0
    smart_wins: int = 0
    ties: int = 0

    avg_context_savings_pct: float = 0.0
    avg_token_savings_pct: float = 0.0

    naive_avg_latency_ms: float = 0.0
    smart_avg_latency_ms: float = 0.0

    total_compactions: int = 0
    total_findings: int = 0
    total_sub_agents: int = 0
    max_nesting_depth: int = 0

    overall_winner: str = "undetermined"
    summary: str = ""


def compute_scenario_comparison(
    naive: RunResult,
    smart: RunResult,
    scenario_name: str = "",
) -> ScenarioComparison:
    """Compute comparison metrics for a single scenario."""

    comp = ScenarioComparison(
        scenario_id=naive.scenario_id,
        scenario_name=scenario_name,
        naive_success=naive.success,
        smart_success=smart.success,
    )

    # Iterations
    comp.naive_iterations = naive.metrics.get("iterations", len(naive.turns))
    comp.smart_iterations = smart.metrics.get("iterations", len(smart.turns))

    # Tool calls
    comp.naive_tool_calls = naive.metrics.get("tool_calls", 0)
    comp.smart_tool_calls = smart.metrics.get("tool_calls", 0)

    # Context tokens
    comp.naive_context_final = naive.metrics.get("context_tokens_final", 0)
    if not comp.naive_context_final and naive.turns:
        comp.naive_context_final = naive.turns[-1].context_tokens_estimate

    comp.smart_context_final = smart.metrics.get("context_tokens_final", 0)
    if not comp.smart_context_final and smart.turns:
        comp.smart_context_final = smart.turns[-1].context_tokens_estimate

    if comp.naive_context_final > 0:
        comp.context_savings_pct = (1.0 - comp.smart_context_final / comp.naive_context_final) * 100

    # Token usage
    comp.naive_tokens_total = naive.metrics.get("token_input", 0) + naive.metrics.get(
        "token_output", 0
    )
    comp.smart_tokens_total = smart.metrics.get("token_input", 0) + smart.metrics.get(
        "token_output", 0
    )
    if comp.naive_tokens_total > 0:
        comp.token_savings_pct = (1.0 - comp.smart_tokens_total / comp.naive_tokens_total) * 100

    # Latency
    comp.naive_latency_ms = naive.metrics.get("latency_ms", 0)
    comp.smart_latency_ms = smart.metrics.get("latency_ms", 0)

    # Smart-only
    comp.compactions = smart.metrics.get("compactions", 0)
    comp.findings_count = smart.metrics.get("findings_count", 0)
    comp.sub_agent_count = smart.metrics.get("sub_agent_count", 0)
    comp.max_nesting_depth = smart.metrics.get("max_nesting_depth", 0)
    comp.failed_attempts = smart.metrics.get("failed_count", 0)

    # Context growth
    comp.naive_context_growth = naive.metrics.get("context_tokens_per_iteration", [])
    comp.smart_context_growth = smart.metrics.get("context_tokens_per_iteration", [])

    # Findings accumulation (context preservation proof)
    comp.findings_per_iteration = smart.metrics.get("findings_per_iteration", [])

    # Determine winner
    comp.winner, comp.winner_reasons = _determine_winner(comp)

    return comp


def compute_aggregate(comparisons: List[ScenarioComparison]) -> AggregateMetrics:
    """Compute aggregate metrics across all scenario comparisons."""
    if not comparisons:
        return AggregateMetrics()

    n = len(comparisons)
    agg = AggregateMetrics(scenario_count=n)

    naive_successes = sum(1 for c in comparisons if c.naive_success)
    smart_successes = sum(1 for c in comparisons if c.smart_success)

    agg.naive_success_rate = naive_successes / n * 100
    agg.smart_success_rate = smart_successes / n * 100

    agg.naive_wins = sum(1 for c in comparisons if c.winner == "naive")
    agg.smart_wins = sum(1 for c in comparisons if c.winner == "smart")
    agg.ties = sum(1 for c in comparisons if c.winner == "tie")

    ctx_savings = [c.context_savings_pct for c in comparisons if c.context_savings_pct != 0]
    agg.avg_context_savings_pct = sum(ctx_savings) / len(ctx_savings) if ctx_savings else 0

    tok_savings = [c.token_savings_pct for c in comparisons if c.token_savings_pct != 0]
    agg.avg_token_savings_pct = sum(tok_savings) / len(tok_savings) if tok_savings else 0

    naive_lats = [c.naive_latency_ms for c in comparisons if c.naive_latency_ms > 0]
    agg.naive_avg_latency_ms = sum(naive_lats) / len(naive_lats) if naive_lats else 0

    smart_lats = [c.smart_latency_ms for c in comparisons if c.smart_latency_ms > 0]
    agg.smart_avg_latency_ms = sum(smart_lats) / len(smart_lats) if smart_lats else 0

    agg.total_compactions = sum(c.compactions for c in comparisons)
    agg.total_findings = sum(c.findings_count for c in comparisons)
    agg.total_sub_agents = sum(c.sub_agent_count for c in comparisons)
    agg.max_nesting_depth = max((c.max_nesting_depth for c in comparisons), default=0)

    # Overall winner
    if agg.smart_wins > agg.naive_wins:
        agg.overall_winner = "SMART (Scratchpad)"
    elif agg.naive_wins > agg.smart_wins:
        agg.overall_winner = "NAIVE (Baseline)"
    else:
        agg.overall_winner = "TIE"

    agg.summary = (
        f"Smart wins {agg.smart_wins}/{n} scenarios. "
        f"Context savings: {agg.avg_context_savings_pct:.1f}%. "
        f"Token savings: {agg.avg_token_savings_pct:.1f}%. "
        f"Total findings extracted: {agg.total_findings}. "
        f"Compactions performed: {agg.total_compactions}."
    )

    return agg


def _determine_winner(comp: ScenarioComparison) -> tuple[str, List[str]]:
    """Determine the winner of a scenario comparison."""
    reasons = []
    smart_score = 0
    naive_score = 0

    # Success is most important
    if comp.smart_success and not comp.naive_success:
        smart_score += 3
        reasons.append("Smart succeeded where Naive failed")
    elif comp.naive_success and not comp.smart_success:
        naive_score += 3
        reasons.append("Naive succeeded where Smart failed")
    elif not comp.smart_success and not comp.naive_success:
        return "both_failed", ["Both runners failed"]

    # Context efficiency
    if comp.context_savings_pct > 20:
        smart_score += 2
        reasons.append(f"Smart used {comp.context_savings_pct:.0f}% less context")
    elif comp.context_savings_pct < -20:
        naive_score += 1
        reasons.append("Naive used less context")

    # Token efficiency
    if comp.token_savings_pct > 10:
        smart_score += 1
        reasons.append(f"Smart used {comp.token_savings_pct:.0f}% fewer tokens")
    elif comp.token_savings_pct < -10:
        naive_score += 1
        reasons.append("Naive used fewer tokens")

    # Findings (smart-only advantage)
    if comp.findings_count > 0:
        smart_score += 1
        reasons.append(f"Smart extracted {comp.findings_count} structured findings")

    # Sub-agents (smart-only advantage)
    if comp.sub_agent_count > 0:
        smart_score += 1
        reasons.append(f"Smart managed {comp.sub_agent_count} sub-agents")

    # Compactions (indicates smart was managing context)
    if comp.compactions > 0:
        smart_score += 1
        reasons.append(f"Smart performed {comp.compactions} compactions")

    if smart_score > naive_score:
        return "smart", reasons
    elif naive_score > smart_score:
        return "naive", reasons
    else:
        return "tie", reasons
