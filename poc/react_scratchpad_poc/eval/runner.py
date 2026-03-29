"""
Evaluation runner -- orchestrates naive vs smart comparison runs.

For each scenario:
  1. Reset tool state
  2. Run naive ReAct loop
  3. Reset tool state
  4. Run smart ReAct loop
  5. Compute comparison metrics
  6. Save results

Outputs JSON results and drives the Rich terminal dashboard.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.models import RunResult, Scenario
from core.protocols import LLMClient, ToolRegistry
from eval import trace as T
from eval.metrics import (
    AggregateMetrics,
    ScenarioComparison,
    compute_aggregate,
    compute_scenario_comparison,
)
from runners.naive_react import NaiveReactRunner
from runners.smart_react import SmartReactRunner


def _get_tools_for_scenario(scenario: Scenario, default_tools: ToolRegistry) -> ToolRegistry:
    """
    Return the correct ToolRegistry for a scenario based on its registry field.

    For 'concierge' scenarios, creates a fresh ConciergeToolRegistry with
    its own SessionState. For 'canned' (default), uses the provided tools.
    """
    if scenario.registry == "concierge":
        from tools.concierge_tools import ConciergeToolRegistry

        return ConciergeToolRegistry()
    return default_tools


class BenchmarkResult(dict):
    """Container for a single scenario's benchmark results."""

    pass


class EvalRunner:
    """
    Orchestrates the naive vs smart benchmark across scenarios.

    Each scenario is run twice: once with the naive runner, once with
    the smart runner. Results are compared and metrics computed.
    """

    def __init__(
        self,
        llm: LLMClient,
        tools: ToolRegistry,
        output_dir: Optional[str] = None,
    ):
        self.llm = llm
        self.tools = tools
        self.output_dir = Path(output_dir or "eval/results")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.naive_runner = NaiveReactRunner(max_iterations=50)
        self.smart_runner = SmartReactRunner(max_iterations=50)

        # Callbacks for progress reporting
        self.on_scenario_start: Optional[Callable] = None
        self.on_naive_complete: Optional[Callable] = None
        self.on_smart_complete: Optional[Callable] = None
        self.on_scenario_complete: Optional[Callable] = None
        self.on_iteration: Optional[Callable] = None

    async def run_benchmark(
        self,
        scenarios: List[Scenario],
        mode: str = "both",  # "both", "naive", "smart"
        skip_naive_on_sub_agents: bool = True,
        trace: bool = False,
    ) -> tuple[List[ScenarioComparison], AggregateMetrics]:
        """
        Run the full benchmark across all scenarios.

        Args:
            scenarios: List of scenarios to run
            mode: Which runner(s) to use
            skip_naive_on_sub_agents: Skip naive on sub-agent scenarios (it can't handle them)

        Returns:
            (comparisons, aggregate) tuple
        """
        comparisons: List[ScenarioComparison] = []
        all_results: List[Dict[str, Any]] = []

        for i, scenario in enumerate(scenarios):
            if self.on_scenario_start:
                self.on_scenario_start(i + 1, len(scenarios), scenario)

            # Check if naive should be skipped (sub-agent scenarios)
            has_sub_agents = any(
                tag in scenario.tags
                for tag in ["sub_agents", "deep_nesting", "parallel", "hierarchy"]
            )

            # Run naive
            naive_result = None
            if mode in ("both", "naive") and not (skip_naive_on_sub_agents and has_sub_agents):
                tools = _get_tools_for_scenario(scenario, self.tools)
                if hasattr(tools, "reset"):
                    tools.reset()

                if trace:
                    T.trace_header(scenario, "Naive ReAct")

                try:
                    naive_result = await self.naive_runner.run(
                        scenario=scenario,
                        tools=tools,
                        llm=self.llm,
                        trace=trace,
                    )
                except Exception as e:
                    naive_result = RunResult(
                        runner_name="naive_react",
                        scenario_id=scenario.id,
                        success=False,
                        errors=[f"Runner crashed: {str(e)}"],
                        started_at=datetime.now(timezone.utc).isoformat(),
                        finished_at=datetime.now(timezone.utc).isoformat(),
                    )

                if self.on_naive_complete:
                    self.on_naive_complete(scenario, naive_result)

                if trace:
                    T.trace_run_summary(naive_result, scenario)

            elif skip_naive_on_sub_agents and has_sub_agents:
                naive_result = RunResult(
                    runner_name="naive_react",
                    scenario_id=scenario.id,
                    success=False,
                    errors=["SKIPPED: Naive runner does not support sub-agents"],
                    started_at=datetime.now(timezone.utc).isoformat(),
                    finished_at=datetime.now(timezone.utc).isoformat(),
                )
                if self.on_naive_complete:
                    self.on_naive_complete(scenario, naive_result)

            # Run smart
            smart_result = None
            if mode in ("both", "smart"):
                # For concierge scenarios, create a FRESH registry so SessionState
                # is clean for the smart run (independent from naive run).
                tools = _get_tools_for_scenario(scenario, self.tools)
                if hasattr(tools, "reset"):
                    tools.reset()

                if trace:
                    T.trace_header(scenario, "Smart ReAct (Scratchpad)")

                try:
                    smart_result = await self.smart_runner.run(
                        scenario=scenario,
                        tools=tools,
                        llm=self.llm,
                        trace=trace,
                    )
                except Exception as e:
                    smart_result = RunResult(
                        runner_name="smart_react",
                        scenario_id=scenario.id,
                        success=False,
                        errors=[f"Runner crashed: {str(e)}"],
                        started_at=datetime.now(timezone.utc).isoformat(),
                        finished_at=datetime.now(timezone.utc).isoformat(),
                    )

                if self.on_smart_complete:
                    self.on_smart_complete(scenario, smart_result)

                if trace:
                    T.trace_run_summary(smart_result, scenario)

            # Compute comparison
            if naive_result and smart_result:
                comparison = compute_scenario_comparison(
                    naive=naive_result,
                    smart=smart_result,
                    scenario_name=scenario.name,
                )
                comparisons.append(comparison)

                if self.on_scenario_complete:
                    self.on_scenario_complete(scenario, comparison)

                # Save per-scenario result
                all_results.append(
                    {
                        "scenario_id": scenario.id,
                        "scenario_name": scenario.name,
                        "naive": naive_result.model_dump(),
                        "smart": smart_result.model_dump(),
                        "comparison": comparison.model_dump(),
                    }
                )

        # Compute aggregate
        aggregate = compute_aggregate(comparisons)

        # Save results
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self._save_results(all_results, aggregate, timestamp)

        return comparisons, aggregate

    def _save_results(
        self,
        results: List[Dict[str, Any]],
        aggregate: AggregateMetrics,
        timestamp: str,
    ) -> None:
        """Save benchmark results to JSON files."""
        # Detailed results
        detail_path = self.output_dir / f"benchmark_{timestamp}.json"
        with open(detail_path, "w") as f:
            json.dump(
                {
                    "timestamp": timestamp,
                    "scenario_count": len(results),
                    "results": results,
                    "aggregate": aggregate.model_dump(),
                },
                f,
                indent=2,
                default=str,
            )

        # Summary
        summary_path = self.output_dir / f"summary_{timestamp}.json"
        with open(summary_path, "w") as f:
            json.dump(aggregate.model_dump(), f, indent=2)
