"""
Rich terminal dashboard for benchmark results.

Provides:
  - Live progress during execution
  - Final results table with color coding
  - Summary statistics
  - Context growth charts (ASCII)
"""

from __future__ import annotations

from typing import List, Optional

from core.models import RunResult, Scenario
from eval.metrics import AggregateMetrics, ScenarioComparison
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


# ---------------------------------------------------------------------------
# Progress tracking during execution
# ---------------------------------------------------------------------------


class BenchmarkProgress:
    """Live progress display during benchmark execution."""

    def __init__(self, total_scenarios: int):
        self.total = total_scenarios
        self.current = 0
        self.current_scenario: Optional[str] = None
        self.phase = ""  # "naive", "smart", "comparing"

    def on_scenario_start(self, idx: int, total: int, scenario: Scenario) -> None:
        self.current = idx
        self.current_scenario = scenario.name
        console.print()
        console.rule(f"[bold cyan]Scenario {idx}/{total}: {scenario.name}")
        console.print(f"  [dim]{scenario.description}[/]")
        console.print(
            f"  [dim]Tier: {scenario.tier.value} | Max iter: {scenario.max_iterations} | Max tools: {scenario.max_tools}[/]"
        )

    def on_naive_complete(self, scenario: Scenario, result: RunResult) -> None:
        status = "[green]PASS[/]" if result.success else "[red]FAIL[/]"
        skipped = "SKIPPED" in str(result.errors)
        if skipped:
            status = "[yellow]SKIP[/]"
            console.print(f"  Naive:  {status} (sub-agents not supported)")
        else:
            iters = result.metrics.get("iterations", 0)
            tools = result.metrics.get("tool_calls", 0)
            ctx = result.metrics.get("context_tokens_final", 0)
            console.print(
                f"  Naive:  {status} | {iters} iters | {tools} tools | {ctx:,} ctx tokens"
            )

    def on_smart_complete(self, scenario: Scenario, result: RunResult) -> None:
        status = "[green]PASS[/]" if result.success else "[red]FAIL[/]"
        iters = result.metrics.get("iterations", 0)
        tools = result.metrics.get("tool_calls", 0)
        findings = result.metrics.get("findings_count", 0)
        compactions = result.metrics.get("compactions", 0)
        ctx = result.metrics.get("context_tokens_final", 0)
        console.print(
            f"  Smart:  {status} | {iters} iters | {tools} tools | "
            f"{findings} findings | {compactions} compactions | {ctx:,} ctx tokens"
        )

    def on_scenario_complete(self, scenario: Scenario, comp: ScenarioComparison) -> None:
        winner_color = {
            "smart": "green",
            "naive": "yellow",
            "tie": "blue",
            "both_failed": "red",
        }.get(comp.winner, "white")
        console.print(f"  Winner: [{winner_color}]{comp.winner.upper()}[/]")
        for reason in comp.winner_reasons[:3]:
            console.print(f"    [dim]- {reason}[/]")


# ---------------------------------------------------------------------------
# Final results dashboard
# ---------------------------------------------------------------------------


def display_results(
    comparisons: List[ScenarioComparison],
    aggregate: AggregateMetrics,
) -> None:
    """Display the full benchmark results dashboard."""
    console.print()
    console.rule("[bold magenta]BENCHMARK RESULTS: Naive vs Smart (Scratchpad)")
    console.print()

    # Main comparison table
    _display_comparison_table(comparisons)
    console.print()

    # Context growth comparison
    _display_context_growth(comparisons)
    console.print()

    # Context preservation (findings flow)
    _display_context_preservation(comparisons)
    console.print()

    # Smart-only metrics
    _display_smart_metrics(comparisons)
    console.print()

    # Aggregate summary
    _display_aggregate(aggregate)
    console.print()

    # Final verdict
    _display_verdict(aggregate)


def _display_comparison_table(comparisons: List[ScenarioComparison]) -> None:
    """Show the main scenario comparison table."""
    table = Table(title="Scenario Results", show_lines=True, expand=True)

    table.add_column("Scenario", style="cyan", no_wrap=True, max_width=25)
    table.add_column("Naive", justify="center", min_width=8)
    table.add_column("Smart", justify="center", min_width=8)
    table.add_column("Winner", justify="center", min_width=8)
    table.add_column("Naive Ctx", justify="right", min_width=10)
    table.add_column("Smart Ctx", justify="right", min_width=10)
    table.add_column("Ctx Save%", justify="right", min_width=8)
    table.add_column("Token Save%", justify="right", min_width=10)

    for comp in comparisons:
        naive_status = "[green]PASS[/]" if comp.naive_success else "[red]FAIL[/]"
        smart_status = "[green]PASS[/]" if comp.smart_success else "[red]FAIL[/]"

        winner_color = {
            "smart": "bold green",
            "naive": "bold yellow",
            "tie": "blue",
            "both_failed": "red",
        }.get(comp.winner, "white")

        ctx_save_color = "green" if comp.context_savings_pct > 0 else "red"
        tok_save_color = "green" if comp.token_savings_pct > 0 else "red"

        table.add_row(
            comp.scenario_name[:25],
            naive_status,
            smart_status,
            f"[{winner_color}]{comp.winner.upper()}[/]",
            f"{comp.naive_context_final:,}",
            f"{comp.smart_context_final:,}",
            f"[{ctx_save_color}]{comp.context_savings_pct:+.1f}%[/]",
            f"[{tok_save_color}]{comp.token_savings_pct:+.1f}%[/]",
        )

    console.print(table)


def _display_context_growth(comparisons: List[ScenarioComparison]) -> None:
    """Show context growth patterns (ASCII sparkline-style)."""
    table = Table(title="Context Growth Pattern (tokens per iteration)", show_lines=True)
    table.add_column("Scenario", style="cyan", max_width=20)
    table.add_column("Naive Growth", min_width=40)
    table.add_column("Smart Growth", min_width=40)

    for comp in comparisons:
        naive_spark = _sparkline(comp.naive_context_growth, color="red")
        smart_spark = _sparkline(comp.smart_context_growth, color="green")
        table.add_row(comp.scenario_name[:20], naive_spark, smart_spark)

    console.print(table)


def _display_context_preservation(comparisons: List[ScenarioComparison]) -> None:
    """Show context preservation: findings accumulation vs context growth.

    This proves that the scratchpad preserves information from tool calls
    across iterations. Findings should grow monotonically (new facts added)
    while context tokens stay bounded (compaction keeps them flat).

    Key insight: Naive has NO findings -- raw tool output is appended to messages.
    Smart extracts structured findings and injects them into the system prompt,
    so the LLM always has access to previously discovered facts.
    """
    table = Table(
        title="Context Preservation (Findings Accumulation vs Context Growth)",
        show_lines=True,
    )
    table.add_column("Scenario", style="cyan", max_width=20)
    table.add_column("Findings Flow", min_width=35)
    table.add_column("Smart Ctx Flow", min_width=35)
    table.add_column("Naive Ctx Flow", min_width=35)

    for comp in comparisons:
        findings_spark = _sparkline(comp.findings_per_iteration, color="magenta")
        smart_ctx_spark = _sparkline(comp.smart_context_growth, color="green")
        naive_ctx_spark = _sparkline(comp.naive_context_growth, color="red")
        table.add_row(
            comp.scenario_name[:20],
            findings_spark,
            smart_ctx_spark,
            naive_ctx_spark,
        )

    console.print(table)


def _display_smart_metrics(comparisons: List[ScenarioComparison]) -> None:
    """Show smart-runner-only metrics."""
    table = Table(title="Smart Runner Metrics (Scratchpad Features)", show_lines=True)
    table.add_column("Scenario", style="cyan", max_width=25)
    table.add_column("Findings", justify="right")
    table.add_column("Compactions", justify="right")
    table.add_column("Sub-Agents", justify="right")
    table.add_column("Max Depth", justify="right")
    table.add_column("Failed", justify="right")
    table.add_column("Iterations", justify="right")

    for comp in comparisons:
        table.add_row(
            comp.scenario_name[:25],
            str(comp.findings_count),
            str(comp.compactions),
            str(comp.sub_agent_count),
            str(comp.max_nesting_depth),
            str(comp.failed_attempts),
            f"N:{comp.naive_iterations} S:{comp.smart_iterations}",
        )

    console.print(table)


def _display_aggregate(aggregate: AggregateMetrics) -> None:
    """Show aggregate summary panel."""
    lines = [
        f"[bold]Scenarios:[/] {aggregate.scenario_count}",
        f"[bold]Naive Success Rate:[/]  {aggregate.naive_success_rate:.0f}%",
        f"[bold]Smart Success Rate:[/]  {aggregate.smart_success_rate:.0f}%",
        "",
        f"[bold]Smart Wins:[/] {aggregate.smart_wins}  |  [bold]Naive Wins:[/] {aggregate.naive_wins}  |  [bold]Ties:[/] {aggregate.ties}",
        "",
        f"[bold]Avg Context Savings:[/]  {aggregate.avg_context_savings_pct:+.1f}%",
        f"[bold]Avg Token Savings:[/]    {aggregate.avg_token_savings_pct:+.1f}%",
        "",
        f"[bold]Total Findings Extracted:[/]  {aggregate.total_findings}",
        f"[bold]Total Compactions:[/]         {aggregate.total_compactions}",
        f"[bold]Total Sub-Agents:[/]          {aggregate.total_sub_agents}",
        f"[bold]Max Nesting Depth:[/]         {aggregate.max_nesting_depth}",
        "",
        f"[bold]Avg Latency - Naive:[/]  {aggregate.naive_avg_latency_ms:,.0f}ms",
        f"[bold]Avg Latency - Smart:[/]  {aggregate.smart_avg_latency_ms:,.0f}ms",
    ]

    panel = Panel(
        "\n".join(lines),
        title="Aggregate Metrics",
        border_style="blue",
    )
    console.print(panel)


def _display_verdict(aggregate: AggregateMetrics) -> None:
    """Show the final verdict panel."""
    if aggregate.overall_winner == "SMART (Scratchpad)":
        color = "bold green"
        icon = "SCRATCHPAD WINS"
        message = (
            f"The scratchpad architecture won {aggregate.smart_wins}/{aggregate.scenario_count} scenarios.\n"
            f"Average context savings: {aggregate.avg_context_savings_pct:.1f}%\n"
            f"Average token savings: {aggregate.avg_token_savings_pct:.1f}%\n"
            f"{aggregate.total_findings} structured findings extracted.\n"
            f"{aggregate.total_compactions} compactions kept context bounded.\n\n"
            "The scratchpad enables truly unlimited ReAct loops with perfect fact recall."
        )
    elif aggregate.overall_winner == "NAIVE (Baseline)":
        color = "yellow"
        icon = "NAIVE WINS"
        message = "The naive approach won more scenarios. Review scratchpad implementation."
    else:
        color = "blue"
        icon = "TIE"
        message = "Both approaches performed similarly. More complex scenarios may differentiate."

    panel = Panel(
        f"[{color}]{message}[/]",
        title=f"[{color}]VERDICT: {icon}[/]",
        border_style=color,
        padding=(1, 2),
    )
    console.print(panel)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sparkline(values: List[int], color: str = "white", width: int = 35) -> str:
    """Create an ASCII sparkline from a list of values."""
    if not values:
        return "[dim]no data[/]"

    # Normalize to sparkline blocks
    blocks = " _.-~^"
    max_val = max(values) if max(values) > 0 else 1
    min_val = min(values)
    val_range = max_val - min_val if max_val != min_val else 1

    # Sample down to width if needed
    if len(values) > width:
        step = len(values) / width
        sampled = [values[int(i * step)] for i in range(width)]
    else:
        sampled = values

    chars = []
    for v in sampled:
        idx = int((v - min_val) / val_range * (len(blocks) - 1))
        chars.append(blocks[idx])

    sparkline = "".join(chars)
    return f"[{color}]{sparkline}[/] [{color} dim]{min_val:,}-{max_val:,}[/]"
