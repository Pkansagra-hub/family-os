"""
ReactLoopScratchpad PoC -- Main entry point.

Benchmark comparing Naive ReAct (append everything) vs Smart ReAct (scratchpad)
across 10 scenarios using Gemini 2.5 Flash with canned tool responses.

Usage:
  python demo.py                          # Run all scenarios, both runners
  python demo.py --scenarios 1,4,8        # Run specific scenarios
  python demo.py --scenarios 10           # Run concierge full-suite scenario
  python demo.py --mode smart             # Only run smart runner
  python demo.py --scenarios 1 --verbose  # Verbose output for debugging
  python demo.py --scenarios 10 --trace    # Step-by-step ReAct loop dissection
  python demo.py --list                   # List available scenarios
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Ensure the PoC root is on sys.path
_POC_ROOT = Path(__file__).parent
if str(_POC_ROOT) not in sys.path:
    sys.path.insert(0, str(_POC_ROOT))

# Ensure the project root (D:\familyos) is on sys.path for k1 imports
_PROJECT_ROOT = _POC_ROOT.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from eval.report import BenchmarkProgress, display_results
from eval.runner import EvalRunner
from llm.gemini_client import GeminiClient
from rich.console import Console
from scenarios.loader import list_scenarios, load_scenarios
from tools.canned_registry import CannedToolRegistry

console = Console()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ReactLoopScratchpad PoC Benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--scenarios",
        "-s",
        type=str,
        default="all",
        help="Comma-separated scenario numbers (1-10) or 'all'. Default: all",
    )
    parser.add_argument(
        "--mode",
        "-m",
        choices=["both", "naive", "smart"],
        default="both",
        help="Which runner(s) to use. Default: both",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "--trace",
        "-t",
        action="store_true",
        help="Show step-by-step ReAct loop dissection (every iteration, tool call, finding)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=str,
        default=None,
        help="Output directory for results. Default: eval/results",
    )
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        dest="list_scenarios",
        help="List available scenarios and exit",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Override LLM model name",
    )
    return parser.parse_args()


async def main():
    args = parse_args()

    # Configure logging for debug output
    if args.verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(name)s | %(message)s",
        )
    else:
        logging.basicConfig(level=logging.WARNING)

    # List scenarios
    if args.list_scenarios:
        from rich.table import Table

        table = Table(title="Available Scenarios")
        table.add_column("#", justify="right")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="white")
        table.add_column("Description")
        table.add_column("Iter", justify="right")
        table.add_column("Tools", justify="right")
        table.add_column("Tier")
        table.add_column("Registry", style="magenta")
        table.add_column("Tags", style="dim")

        for s in list_scenarios():
            table.add_row(
                str(s["id"]),
                s["scenario_id"],
                s["name"],
                s["description"],
                str(s["max_iterations"]),
                str(s["max_tools"]),
                s["tier"],
                s["registry"],
                ", ".join(s["tags"]),
            )
        console.print(table)
        return

    # Parse scenario selection
    scenario_ids = None
    if args.scenarios != "all":
        try:
            scenario_ids = [int(x.strip()) for x in args.scenarios.split(",")]
        except ValueError:
            console.print("[red]Invalid scenario numbers. Use comma-separated integers (1-10).[/]")
            sys.exit(1)

    # Load scenarios
    scenarios = load_scenarios(scenario_ids)
    console.print(f"\n[bold]Loading {len(scenarios)} scenario(s)...[/]")

    # Initialize LLM
    console.print("[dim]Initializing Gemini client...[/]")
    try:
        llm = GeminiClient(model_name=args.model)
        console.print(f"[green]LLM ready: {llm.model_name}[/]")
    except Exception as e:
        console.print(f"[red]Failed to initialize LLM: {e}[/]")
        console.print("[yellow]Check GOOGLE_API_KEY in poc/chat_experience_poc/.env[/]")
        sys.exit(1)

    # Initialize tools
    tools = CannedToolRegistry()
    console.print(f"[green]Tools ready: {len(tools.get_tool_names())} tools registered[/]")

    # Output directory
    output_dir = args.output_dir or str(_POC_ROOT / "eval" / "results")

    # Initialize eval runner
    eval_runner = EvalRunner(
        llm=llm,
        tools=tools,
        output_dir=output_dir,
    )

    # Set up progress callbacks
    progress = BenchmarkProgress(len(scenarios))
    eval_runner.on_scenario_start = progress.on_scenario_start
    eval_runner.on_naive_complete = progress.on_naive_complete
    eval_runner.on_smart_complete = progress.on_smart_complete
    eval_runner.on_scenario_complete = progress.on_scenario_complete

    # Run benchmark
    console.print()
    console.rule("[bold]Starting Benchmark")
    console.print(f"  Mode: [cyan]{args.mode}[/]")
    console.print(f"  Scenarios: [cyan]{len(scenarios)}[/]")
    console.print(f"  Output: [cyan]{output_dir}[/]")
    if args.trace:
        console.print("  [magenta]Trace: ENABLED (step-by-step loop dissection)[/]")

    try:
        comparisons, aggregate = await eval_runner.run_benchmark(
            scenarios=scenarios,
            mode=args.mode,
            trace=args.trace,
        )

        # Display results
        if comparisons:
            display_results(comparisons, aggregate)
        else:
            console.print("[yellow]No comparisons to display (single-mode run).[/]")

        # Show LLM usage
        console.print()
        console.print(
            f"[dim]LLM calls: {llm.total_calls} | "
            f"Tokens in: {llm.total_tokens_in:,} | "
            f"Tokens out: {llm.total_tokens_out:,}[/]"
        )
        console.print(f"[dim]Results saved to: {output_dir}[/]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Benchmark interrupted by user.[/]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[red]Benchmark failed: {e}[/]")
        if args.verbose:
            console.print_exception()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
