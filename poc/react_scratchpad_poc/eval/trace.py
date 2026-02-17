"""
ReAct loop trace -- step-by-step dissection of what happens end-to-end.

Shows every step of the ReAct loop in human-readable form:
  - User query -> LLM
  - LLM decision (which tools and why)
  - Tool execution and results
  - Findings extraction (smart only)
  - Context state after each iteration
  - Compaction events
  - Sub-agent lifecycle
  - Final answer delivery

Usage: python demo.py --scenarios 10 --trace
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.models import RunResult, Scenario
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# Max chars to display for any single field
_MAX_DISPLAY = 300


def _trunc(s: str, n: int = _MAX_DISPLAY) -> str:
    if len(s) <= n:
        return s
    return s[:n] + f"... ({len(s)} chars total)"


def trace_header(scenario: Scenario, runner_name: str) -> None:
    """Print the trace header with scenario info."""
    console.print()
    console.rule(
        f"[bold magenta]TRACE: {runner_name.upper()} -- {scenario.name}",
        style="magenta",
    )
    console.print(f"  [dim]Scenario:[/] {scenario.id}")
    console.print(f"  [dim]Registry:[/] {scenario.registry}")
    console.print(f"  [dim]Tier:[/] {scenario.tier.value}")
    console.print(
        f"  [dim]Budget:[/] {scenario.max_iterations} iterations, {scenario.max_tools} tools"
    )
    console.print(
        f"  [dim]Force tool call:[/] {scenario.force_tool_call} | "
        f"Min tool iterations: {scenario.min_tool_iterations}"
    )
    console.print()

    # System prompt
    console.print(
        Panel(
            _trunc(scenario.system_prompt, 600),
            title="[bold]System Prompt",
            border_style="blue",
            width=100,
        )
    )

    # User query
    console.print(
        Panel(
            scenario.user_query,
            title="[bold]User Query",
            border_style="cyan",
            width=100,
        )
    )
    console.print()


def trace_iteration_start(
    runner_name: str,
    iteration: int,
    context_tokens: int,
    message_count: int,
    tools_available: int,
    force_tool_call: bool,
    findings_available: Optional[List[str]] = None,
) -> None:
    """Print iteration start with context state."""
    tag = "SMART" if "smart" in runner_name else "NAIVE"
    color = "green" if tag == "SMART" else "yellow"

    console.rule(
        f"[bold {color}]ITERATION {iteration} ({tag})",
        style=color,
    )

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="dim", min_width=22)
    table.add_column("Value")

    table.add_row("Context tokens", f"{context_tokens:,}")
    table.add_row("Messages in context", str(message_count))
    table.add_row("Tools available", str(tools_available))
    table.add_row("Force tool call", str(force_tool_call))

    if findings_available:
        table.add_row(
            "Findings injected",
            f"{len(findings_available)} -- {', '.join(findings_available[:8])}"
            + ("..." if len(findings_available) > 8 else ""),
        )
    else:
        table.add_row("Findings injected", "[dim]none yet[/]")

    console.print(table)
    console.print()


def trace_llm_decision(
    iteration: int,
    tool_calls: List[Dict[str, Any]],
    reasoning_text: Optional[str] = None,
    is_final_answer: bool = False,
    final_answer_text: Optional[str] = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> None:
    """Print what the LLM decided to do."""
    if is_final_answer:
        console.print("[bold cyan]LLM DECISION:[/] Deliver final answer")
        if final_answer_text:
            console.print(
                Panel(
                    _trunc(final_answer_text, 500),
                    title="Final Answer",
                    border_style="green",
                    width=100,
                )
            )
        console.print(f"  [dim]Tokens: {tokens_in:,} in / {tokens_out:,} out[/]")
        console.print()
        return

    if not tool_calls:
        console.print("[bold cyan]LLM DECISION:[/] Text-only response (no tool calls)")
        if reasoning_text:
            console.print(f"  [dim]{_trunc(reasoning_text, 200)}[/]")
        console.print(f"  [dim]Tokens: {tokens_in:,} in / {tokens_out:,} out[/]")
        console.print()
        return

    console.print(
        f"[bold cyan]LLM DECISION:[/] Call {len(tool_calls)} tool(s)  "
        f"[dim]({tokens_in:,} in / {tokens_out:,} out)[/]"
    )
    if reasoning_text:
        console.print(f"  [dim italic]Reasoning: {_trunc(reasoning_text, 150)}[/]")

    for i, tc in enumerate(tool_calls, 1):
        name = tc.get("name", "?")
        args = tc.get("arguments", {})
        args_str = ", ".join(f"{k}={_trunc(str(v), 80)}" for k, v in args.items())
        console.print(f"  [bold]{i}. {name}[/]({args_str})")
    console.print()


def trace_tool_execution(
    tool_name: str,
    arguments: Dict[str, Any],
    ok: bool,
    output: Any = None,
    error: Optional[str] = None,
) -> None:
    """Print tool execution result."""
    args_str = ", ".join(f"{k}={_trunc(str(v), 60)}" for k, v in arguments.items())

    if ok:
        output_str = str(output) if output else "(empty)"
        token_est = len(output_str) // 4
        console.print(
            f"  [green]OK[/] [bold]{tool_name}[/]({args_str}) " f"[dim]-> {token_est} tokens[/]"
        )
        # Show a preview of output
        if output_str and len(output_str) > 10:
            console.print(f"      [dim]{_trunc(output_str, 150)}[/]")
    else:
        console.print(
            f"  [red]FAIL[/] [bold]{tool_name}[/]({args_str}) " f"-> {error or 'unknown error'}"
        )


def trace_findings_extracted(
    tool_name: str,
    findings: List[Dict[str, Any]],
) -> None:
    """Print findings extracted from a tool result (smart only)."""
    if not findings:
        return

    console.print(f"  [magenta]FINDINGS[/] from {tool_name}:")
    for f in findings[:6]:
        key = f.get("key", "?")
        value = _trunc(str(f.get("value", "")), 100)
        ftype = f.get("type", "fact")
        console.print(f"    [magenta]+[/] {key} = {value} [dim]({ftype})[/]")
    if len(findings) > 6:
        console.print(f"    [dim]... and {len(findings) - 6} more[/]")


def trace_compaction(
    messages_before: int,
    messages_after: int,
    iteration: int,
) -> None:
    """Print compaction event."""
    console.print(
        f"  [yellow]COMPACTION[/] at iteration {iteration}: "
        f"{messages_before} messages -> {messages_after} messages"
    )


def trace_sub_agent_spawn(
    agent_id: str,
    task: str,
    tool_budget: int,
    depth: int,
) -> None:
    """Print sub-agent spawn."""
    console.print(f"\n  [bold blue]SUB-AGENT SPAWNED[/] {agent_id} (depth={depth})")
    console.print(f"    [dim]Task:[/] {_trunc(task, 120)}")
    console.print(f"    [dim]Tool budget:[/] {tool_budget}")
    console.print()


def trace_sub_agent_complete(
    agent_id: str,
    status: str,
    findings_count: int,
    iterations_used: int,
    answer: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """Print sub-agent completion."""
    if status == "complete":
        console.print(
            f"  [bold green]SUB-AGENT DONE[/] {agent_id}: "
            f"{findings_count} findings, {iterations_used} iterations"
        )
        if answer:
            console.print(f"    [dim]Answer: {_trunc(answer, 150)}[/]")
    else:
        console.print(f"  [bold red]SUB-AGENT FAILED[/] {agent_id}: {error or 'unknown'}")


def trace_iteration_end(
    iteration: int,
    cumulative_findings: int,
    context_tokens: int,
    compacted: bool,
    tools_called: List[str],
) -> None:
    """Print iteration summary."""
    tools_str = ", ".join(tools_called) if tools_called else "none"
    compact_str = " [yellow][COMPACTED][/]" if compacted else ""
    console.print(
        f"\n  [dim]End iter {iteration}: "
        f"{cumulative_findings} findings | "
        f"{context_tokens:,} ctx tokens | "
        f"tools: {tools_str}{compact_str}[/]"
    )
    console.print()


def trace_run_summary(result: RunResult, scenario: Scenario) -> None:
    """Print complete run summary at end."""
    tag = "SMART" if "smart" in result.runner_name else "NAIVE"
    color = "green" if tag == "SMART" else "yellow"
    status = "[green]PASS[/]" if result.success else "[red]FAIL[/]"

    lines = [
        f"[bold]Status:[/] {status}",
        f"[bold]Iterations:[/] {result.metrics.get('iterations', 0)}",
        f"[bold]Tool calls:[/] {result.metrics.get('tool_calls', 0)}",
        f"[bold]Context tokens (final):[/] {result.metrics.get('context_tokens_final', 0):,}",
        f"[bold]Tokens in:[/] {result.metrics.get('token_input', 0):,}",
        f"[bold]Tokens out:[/] {result.metrics.get('token_output', 0):,}",
        f"[bold]Latency:[/] {result.metrics.get('latency_ms', 0):,}ms",
    ]

    if tag == "SMART":
        lines.extend(
            [
                "",
                f"[bold]Findings extracted:[/] {result.metrics.get('findings_count', 0)}",
                f"[bold]Compactions:[/] {result.metrics.get('compactions', 0)}",
                f"[bold]Sub-agents:[/] {result.metrics.get('sub_agent_count', 0)}",
                f"[bold]Max nesting depth:[/] {result.metrics.get('max_nesting_depth', 0)}",
            ]
        )

        # Show findings accumulation curve
        fpi = result.metrics.get("findings_per_iteration", [])
        if fpi:
            lines.append(f"[bold]Findings accumulation:[/] {' -> '.join(str(x) for x in fpi)}")

        # Show context growth curve
        cpi = result.metrics.get("context_tokens_per_iteration", [])
        if cpi:
            lines.append(f"[bold]Context growth:[/] {' -> '.join(str(x) for x in cpi)}")

    if result.errors:
        lines.append("")
        lines.append(f"[red]Errors:[/] {', '.join(result.errors[:3])}")

    panel = Panel(
        "\n".join(lines),
        title=f"[bold {color}]{tag} RUN SUMMARY",
        border_style=color,
        width=100,
    )
    console.print(panel)

    # Show final answer preview
    if result.final_answer:
        console.print(
            Panel(
                _trunc(result.final_answer, 400),
                title="Final Answer",
                border_style="green",
                width=100,
            )
        )
    console.print()
