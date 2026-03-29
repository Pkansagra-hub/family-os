"""
Rich Terminal Display for Concierge-Planner-Orchestrator POC
==============================================================

Beautiful PowerShell/Terminal output with Unicode box-drawing,
ANSI colors, progress indicators, and dramatic visual effects.

Shows every internal operation:
  - LLM calls (Concierge, Planner, Synthesizer)
  - Classification results (tier, intent, domains)
  - Capability discovery
  - DAG plan visualization
  - Fabric execution step-by-step
  - Response synthesis
  - Timing and statistics
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List


def setup_unicode_console() -> None:
    """Enable Unicode output in Windows PowerShell/CMD."""
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleOutputCP(65001)
            kernel32.SetConsoleCP(65001)
        except Exception:
            pass
        if hasattr(sys.stdout, "reconfigure"):
            try:
                sys.stdout.reconfigure(encoding="utf-8")
            except Exception:
                pass


setup_unicode_console()

# ====================================================================
# Unicode Box-Drawing Characters
# ====================================================================

TL = "\u250c"
TR = "\u2510"
BL = "\u2514"
BR = "\u2518"
HZ = "\u2500"
VT = "\u2502"
TL_H = "\u250f"
TR_H = "\u2513"
BL_H = "\u2517"
BR_H = "\u251b"
HZ_H = "\u2501"
VT_H = "\u2503"
TL_D = "\u2554"
TR_D = "\u2557"
BL_D = "\u255a"
BR_D = "\u255d"
HZ_D = "\u2550"
VT_D = "\u2551"

PROG_FULL = "\u2588"
PROG_EMPTY = "\u2591"

CHECK = "\u2713"
CROSS = "\u2717"
ARROW_R = "\u25b6"
ARROW_D = "\u25bc"
BULLET = "\u2022"
STAR = "\u2605"
LIGHTNING = "\u26a1"
WARNING = "\u26a0"
GEAR = "\u2699"
DATABASE = "\u25a3"
CLOCK = "\u231b"
BRAIN = "\u2055"
NETWORK = "\u2726"
WAVE = "\u223f"

# ====================================================================
# ANSI Color Codes
# ====================================================================

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
WHITE = "\033[97m"
GRAY = "\033[90m"

BG_RED = "\033[41m"
BG_GREEN = "\033[42m"
BG_YELLOW = "\033[43m"
BG_BLUE = "\033[44m"
BG_MAGENTA = "\033[45m"
BG_CYAN = "\033[46m"


def c(text: str, color: str, bold: bool = False, dim: bool = False) -> str:
    """Apply color to text."""
    prefix = ""
    if bold:
        prefix += BOLD
    if dim:
        prefix += DIM
    return f"{prefix}{color}{text}{RESET}"


def clear_screen() -> None:
    """Clear terminal."""
    os.system("cls" if os.name == "nt" else "clear")


W = 72  # Standard box width


def _box_line(text: str, color: str, width: int = W) -> str:
    """Single line inside a box."""
    return c(VT_D, color) + f"  {text}".ljust(width) + c(VT_D, color)


# ====================================================================
# Pipeline Header
# ====================================================================


def print_pipeline_header() -> None:
    """Print the main pipeline banner."""
    clear_screen()
    print()
    print(c(TL_D + HZ_D * W + TR_D, CYAN, bold=True))
    print(_box_line("", CYAN))
    print(
        _box_line(
            c(
                f"  {NETWORK} CONCIERGE  {ARROW_R}  PLANNER  {ARROW_R}  ORCHESTRATOR  {ARROW_R}  FABRIC",
                CYAN,
                bold=True,
            ),
            CYAN,
        )
    )
    print(_box_line("", CYAN))
    print(_box_line(c("  Real LLMs (Google Gemini) + Real Capability Fabric", WHITE), CYAN))
    print(_box_line(c("  Full DAG Execution Pipeline POC", GRAY), CYAN))
    print(_box_line("", CYAN))
    print(c(BL_D + HZ_D * W + BR_D, CYAN, bold=True))
    print()


# ====================================================================
# Phase Headers
# ====================================================================


def print_phase(number: int, title: str, icon: str = GEAR) -> None:
    """Print a phase separator."""
    print()
    print(c(TL_H + HZ_H * W + TR_H, YELLOW))
    inner = f"  {icon} PHASE {number}: {title}"
    print(c(VT_H, YELLOW) + c(inner, YELLOW, bold=True).ljust(W + 9) + c(VT_H, YELLOW))
    print(c(BL_H + HZ_H * W + BR_H, YELLOW))
    print()


def print_divider(char: str = HZ, color: str = GRAY) -> None:
    """Print a thin divider."""
    print(c(char * (W + 4), color))


# ====================================================================
# User Input
# ====================================================================


def print_user_input(text: str) -> None:
    """Display the user's request."""
    print()
    print(c(TL_D + HZ_D * W + TR_D, GREEN))
    print(_box_line(c(f"{ARROW_R} USER REQUEST", GREEN, bold=True), GREEN))
    print(c(VT_D + HZ * W + VT_D, GREEN))
    # Word wrap
    words = text.split()
    line = ""
    for word in words:
        if len(line) + len(word) > W - 4:
            print(_box_line(f"  {line}", GREEN))
            line = ""
        line += word + " "
    if line.strip():
        print(_box_line(f"  {line}", GREEN))
    print(c(BL_D + HZ_D * W + BR_D, GREEN))
    print()


# ====================================================================
# LLM Calls
# ====================================================================


def print_llm_call_start(agent: str, purpose: str, model: str = "gemini-2.5-flash") -> None:
    """Print that an LLM call is starting."""
    print(c(f"  {LIGHTNING} [LLM CALL]", CYAN, bold=True) + f" {agent}")
    print(c(f"       {BULLET} Model: {model}", GRAY))
    print(c(f"       {BULLET} Purpose: {purpose}", GRAY))
    sys.stdout.flush()


def print_llm_call_end(latency_ms: int, tool_calls: int = 0, text_length: int = 0) -> None:
    """Print LLM call completion."""
    parts = [f"{latency_ms}ms"]
    if tool_calls:
        parts.append(f"{tool_calls} tool call(s)")
    if text_length:
        parts.append(f"{text_length} chars")
    print(c(f"  {CHECK} [LLM RESPONSE]", GREEN, bold=True) + f" {' | '.join(parts)}")
    print()


# ====================================================================
# Classification
# ====================================================================


def print_classification(
    tier: str,
    intent: str,
    domains: list,
    reasoning: str = "",
    latency_ms: int = 0,
) -> None:
    """Print Concierge classification result."""
    tier_color = GREEN if tier == "LOW" else YELLOW if tier == "MEDIUM" else RED

    print(c(TL_H + HZ_H * W + TR_H, BLUE))
    inner = f"  {GEAR} CLASSIFICATION RESULT"
    print(c(VT_H, BLUE) + c(inner, BLUE, bold=True).ljust(W + 9) + c(VT_H, BLUE))
    print(c(VT_H + HZ * W + VT_H, BLUE))

    print(
        c(VT_H, BLUE)
        + f"  {BULLET} Tier:    {c(tier, tier_color, bold=True)}".ljust(W + 18)
        + c(VT_H, BLUE)
    )
    print(c(VT_H, BLUE) + f"  {BULLET} Intent:  {c(intent, WHITE)}".ljust(W + 18) + c(VT_H, BLUE))
    print(
        c(VT_H, BLUE)
        + f"  {BULLET} Domains: {c(', '.join(domains), CYAN)}".ljust(W + 18)
        + c(VT_H, BLUE)
    )
    if reasoning:
        # Wrap reasoning
        r = reasoning[: W - 12] + "..." if len(reasoning) > W - 12 else reasoning
        print(
            c(VT_H, BLUE)
            + f"  {BULLET} Reason:  {c(r, GRAY, dim=True)}".ljust(W + 18)
            + c(VT_H, BLUE)
        )
    if latency_ms:
        print(c(VT_H, BLUE) + f"  {CLOCK} {latency_ms}ms".ljust(W + 2) + c(VT_H, BLUE))
    print(c(BL_H + HZ_H * W + BR_H, BLUE))
    print()


# ====================================================================
# Routing
# ====================================================================


def print_routing(tier: str) -> None:
    """Print the routing decision."""
    if tier == "LOW":
        path = f"Concierge {ARROW_R} Fabric (direct)"
        color = GREEN
    elif tier == "MEDIUM":
        path = f"Concierge {ARROW_R} Orchestrator {ARROW_R} Fabric"
        color = YELLOW
    else:
        path = f"Concierge {ARROW_R} Planner {ARROW_R} Orchestrator {ARROW_R} Fabric"
        color = RED

    print(f"  {ARROW_R} {c('ROUTING:', WHITE, bold=True)} {c(path, color, bold=True)}")
    print()


# ====================================================================
# Capability Discovery
# ====================================================================


def print_capabilities_discovered(
    total: int,
    filtered: int,
    domains: list,
    capabilities: List[Dict[str, Any]],
) -> None:
    """Print capability discovery results."""
    print(c(f"  {DATABASE} [DISCOVERY]", MAGENTA, bold=True) + f" Scanned {total} contracts")
    print(
        c(
            f"       {BULLET} Filtered to {filtered} capabilities for domains: {', '.join(domains)}",
            GRAY,
        )
    )
    print()
    for cap in capabilities[:8]:
        name = cap.get("name", "?")
        desc = cap.get("description", "")[:50]
        inputs = len(cap.get("required_inputs", []))
        print(
            f"       {c(ARROW_R, MAGENTA)} {c(name, WHITE)} - {c(desc, GRAY, dim=True)} ({inputs} inputs)"
        )
    if len(capabilities) > 8:
        print(f"       {c(f'... and {len(capabilities)-8} more', GRAY, dim=True)}")
    print()


def print_agentic_tool_call(
    tool_name: str,
    args: Dict[str, Any],
    result: Any,
    turn: int,
) -> None:
    """
    Print a single tool call from the Planner's agentic loop.

    Shows the LLM's discover_capabilities or commit_plan call
    with arguments, result count, and turn number.
    """
    if tool_name == "discover_capabilities":
        domain = args.get("domain", "ALL")
        intent = args.get("intent", "")
        found = 0
        if isinstance(result, dict):
            found = result.get("capabilities_found", 0)

        print(
            c(f"  {DATABASE} [DISCOVER]", MAGENTA, bold=True)
            + f" Turn {turn + 1}: domain={c(domain or 'ALL', CYAN)} "
            + f"intent={c(intent[:40] or '-', GRAY, dim=True)}"
        )
        print(c(f"       {CHECK} Found {found} capabilities", GREEN))
        if isinstance(result, dict):
            caps = result.get("capabilities", [])
            for cap in caps[:5]:
                name = cap.get("name", "?")
                desc = cap.get("description", "")[:45]
                print(
                    f"       {c(ARROW_R, MAGENTA)} {c(name, WHITE)} " f"- {c(desc, GRAY, dim=True)}"
                )
            if len(caps) > 5:
                print(f"       {c(f'... and {len(caps)-5} more', GRAY, dim=True)}")
        print()

    elif tool_name == "commit_plan":
        steps = args.get("steps", [])
        reasoning = str(args.get("reasoning", ""))[:60]
        print(
            c(f"  {STAR} [COMMIT]", GREEN, bold=True)
            + f" Turn {turn + 1}: {len(steps)} steps "
            + c(f'"{reasoning}"', GRAY, dim=True)
        )
        print()

    else:
        # Unknown tool
        print(c(f"  {GEAR} [{tool_name}]", YELLOW, bold=True) + f" Turn {turn + 1}: args={args}")
        print()


# ====================================================================
# DAG Plan Visualization
# ====================================================================


def print_plan(
    steps: list,
    reasoning: str = "",
    plan_id: str = "",
    latency_ms: int = 0,
) -> None:
    """Print the committed plan as a visual DAG."""
    print(c(TL_D + HZ_D * W + TR_D, MAGENTA))
    inner = f"  {STAR} COMMITTED PLAN — {len(steps)} steps"
    if plan_id:
        inner += f" [{plan_id[:8]}]"
    print(c(VT_D, MAGENTA) + c(inner, MAGENTA, bold=True).ljust(W + 9) + c(VT_D, MAGENTA))
    print(c(VT_D + HZ * W + VT_D, MAGENTA))

    if reasoning:
        r = reasoning[: W - 4]
        print(
            c(VT_D, MAGENTA)
            + c(f"  Reasoning: {r}", GRAY, dim=True).ljust(W + 9)
            + c(VT_D, MAGENTA)
        )
        print(c(VT_D + HZ * W + VT_D, MAGENTA))

    # Build dependency lookup
    step_map = {}
    for i, s in enumerate(steps):
        sid = s.step_id if hasattr(s, "step_id") else s.get("step_id", "")
        deps = s.depends_on if hasattr(s, "depends_on") else s.get("depends_on", [])
        name = s.capability_name if hasattr(s, "capability_name") else s.get("capability_name", "")
        desc = s.description if hasattr(s, "description") else s.get("description", "")
        step_map[sid] = {"deps": deps, "name": name, "desc": desc, "idx": i}

    # Compute waves (topological layers)
    waves = _compute_waves(steps)

    for wave_idx, wave in enumerate(waves):
        if wave_idx > 0:
            # Draw dependency arrows
            arrow_line = "     " + "      ".join([f"  {ARROW_D}  " for _ in wave])
            print(c(VT_D, MAGENTA) + c(arrow_line, YELLOW).ljust(W + 9) + c(VT_D, MAGENTA))

        is_parallel = len(wave) > 1
        prefix = f"  Wave {wave_idx + 1}" + (
            f" ({c('PARALLEL', GREEN, bold=True)})"
            if is_parallel
            else f" ({c('SEQUENTIAL', CYAN)})"
        )
        print(c(VT_D, MAGENTA) + f"  {prefix}".ljust(W + 27) + c(VT_D, MAGENTA))

        for sid in wave:
            info = step_map.get(sid, {})
            name_short = info.get("name", "?").rsplit(".", 1)[-1]
            desc = info.get("desc", "")[:40]
            deps = info.get("deps", [])

            step_line = f"    {c(f'[{sid}]', YELLOW, bold=True)} {c(name_short, WHITE)} — {c(desc, GRAY, dim=True)}"
            print(c(VT_D, MAGENTA) + f"  {step_line}".ljust(W + 36) + c(VT_D, MAGENTA))

            if deps:
                dep_str = ", ".join(deps)
                print(
                    c(VT_D, MAGENTA)
                    + c(f"         depends_on: [{dep_str}]", YELLOW, dim=True).ljust(W + 9)
                    + c(VT_D, MAGENTA)
                )

    print(c(VT_D + HZ * W + VT_D, MAGENTA))
    if latency_ms:
        print(
            c(VT_D, MAGENTA)
            + c(f"  {CLOCK} Plan built in {latency_ms}ms", GREEN).ljust(W + 9)
            + c(VT_D, MAGENTA)
        )
    print(c(BL_D + HZ_D * W + BR_D, MAGENTA))
    print()


def _compute_waves(steps: list) -> List[List[str]]:
    """Compute topological waves from plan steps."""
    step_ids = set()
    deps_map: Dict[str, List[str]] = {}
    for s in steps:
        sid = s.step_id if hasattr(s, "step_id") else s.get("step_id", "")
        deps = list(s.depends_on if hasattr(s, "depends_on") else s.get("depends_on", []))
        step_ids.add(sid)
        deps_map[sid] = deps

    placed = set()
    waves: List[List[str]] = []
    remaining = set(step_ids)

    while remaining:
        wave = []
        for sid in list(remaining):
            if all(d in placed for d in deps_map.get(sid, [])):
                wave.append(sid)
        if not wave:
            # Cycle or orphan — dump everything left
            wave = list(remaining)
        for sid in wave:
            remaining.discard(sid)
            placed.add(sid)
        waves.append(sorted(wave))

    return waves


# ====================================================================
# Fabric Execution
# ====================================================================


def print_fabric_start(step_count: int, strategy: str = "DAG") -> None:
    """Print Fabric execution start."""
    print(c(TL_H + HZ_H * W + TR_H, GREEN))
    inner = f"  {GEAR} FABRIC EXECUTION — {step_count} requests, strategy={strategy}"
    print(c(VT_H, GREEN) + c(inner, GREEN, bold=True).ljust(W + 9) + c(VT_H, GREEN))
    print(c(VT_H + HZ * W + VT_H, GREEN))
    sys.stdout.flush()


def print_fabric_step(
    step_id: str,
    capability: str,
    success: bool,
    duration_ms: int,
    data: Any = None,
    error: str | None = None,
) -> None:
    """Print a single Fabric execution step result."""
    icon = c(CHECK, GREEN, bold=True) if success else c(CROSS, RED, bold=True)
    status = c("OK", GREEN) if success else c("FAIL", RED)
    name_short = capability.rsplit(".", 1)[-1]

    line = f"  {icon} [{step_id}] {c(name_short, WHITE)} — {status}  {c(f'{duration_ms}ms', GRAY)}"
    print(c(VT_H, GREEN) + f"  {line}".ljust(W + 36) + c(VT_H, GREEN))

    if data:
        data_str = str(data)
        if len(data_str) > 60:
            data_str = data_str[:60] + "..."
        print(
            c(VT_H, GREEN)
            + c(f"        Data: {data_str}", GRAY, dim=True).ljust(W + 9)
            + c(VT_H, GREEN)
        )

    if error:
        err_str = error[:60] + "..." if len(error) > 60 else error
        print(
            c(VT_H, GREEN)
            + c(f"        Error: {err_str}", RED, dim=True).ljust(W + 9)
            + c(VT_H, GREEN)
        )

    sys.stdout.flush()


def print_fabric_end(total_ms: int, success_count: int, fail_count: int) -> None:
    """Print Fabric execution summary."""
    print(c(VT_H + HZ * W + VT_H, GREEN))
    summary = f"  {CLOCK} Total: {total_ms}ms | {c(f'{success_count} succeeded', GREEN)} | {c(f'{fail_count} failed', RED if fail_count else GREEN)}"
    print(c(VT_H, GREEN) + f"  {summary}".ljust(W + 36) + c(VT_H, GREEN))
    print(c(BL_H + HZ_H * W + BR_H, GREEN))
    print()


# ====================================================================
# Response Synthesis
# ====================================================================


def print_response(text: str) -> None:
    """Print the final synthesized response."""
    print(c(TL_D + HZ_D * W + TR_D, BLUE))
    inner = f"  {STAR} CONCIERGE RESPONSE"
    print(c(VT_D, BLUE) + c(inner, BLUE, bold=True).ljust(W + 9) + c(VT_D, BLUE))
    print(c(VT_D + HZ * W + VT_D, BLUE))

    # Word wrap
    words = text.split()
    line = ""
    for word in words:
        if len(line) + len(word) > W - 4:
            print(c(VT_D, BLUE) + f"  {line}".ljust(W + 2) + c(VT_D, BLUE))
            line = ""
        line += word + " "
    if line.strip():
        print(c(VT_D, BLUE) + f"  {line}".ljust(W + 2) + c(VT_D, BLUE))

    print(c(BL_D + HZ_D * W + BR_D, BLUE))
    print()


# ====================================================================
# Statistics
# ====================================================================


def print_stats(stats: Dict[str, Any]) -> None:
    """Print pipeline execution statistics."""
    print(c(TL_H + HZ_H * W + TR_H, YELLOW))
    inner = f"  {GEAR} PIPELINE STATISTICS"
    print(c(VT_H, YELLOW) + c(inner, YELLOW, bold=True).ljust(W + 9) + c(VT_H, YELLOW))
    print(c(VT_H + HZ * W + VT_H, YELLOW))

    rows = [
        (f"{LIGHTNING} LLM Calls", str(stats.get("llm_calls", 0))),
        (f"{DATABASE} Discovery Calls", str(stats.get("discovery_calls", 0))),
        (f"{DATABASE} Capabilities Discovered", str(stats.get("discovery_caps", 0))),
        (f"{CLOCK} Classify Latency", f"{stats.get('classify_ms', 0)}ms"),
        (f"{CLOCK} Plan Latency", f"{stats.get('plan_ms', 0)}ms"),
        (f"{CLOCK} Fabric Latency", f"{stats.get('fabric_ms', 0)}ms"),
        (f"{CLOCK} Synthesis Latency", f"{stats.get('synthesis_ms', 0)}ms"),
        (f"{CLOCK} Total End-to-End", f"{stats.get('total_ms', 0)}ms"),
        (f"{GEAR} DAG Steps Executed", str(stats.get("steps_executed", 0))),
        (f"{CHECK} Steps Succeeded", str(stats.get("steps_succeeded", 0))),
        (f"{CROSS} Steps Failed", str(stats.get("steps_failed", 0))),
        (f"{DATABASE} Capabilities Available", str(stats.get("capabilities_total", 0))),
    ]

    for label, value in rows:
        print(
            c(VT_H, YELLOW)
            + f"  {BULLET} {label}: {c(value, WHITE)}".ljust(W + 18)
            + c(VT_H, YELLOW)
        )

    print(c(BL_H + HZ_H * W + BR_H, YELLOW))
    print()


# ====================================================================
# Pipeline Complete
# ====================================================================


def print_pipeline_complete(success: bool = True) -> None:
    """Print pipeline completion banner."""
    if success:
        color = GREEN
        icon = CHECK
        text = "PIPELINE COMPLETE"
    else:
        color = RED
        icon = CROSS
        text = "PIPELINE PARTIAL"

    print(c("=" * (W + 4), color, bold=True))
    print(c(f"  {icon} {text} {icon}", color, bold=True).center(W + 15))
    print(c("=" * (W + 4), color, bold=True))
    print()


# ====================================================================
# Scenario Selection
# ====================================================================


def print_scenario_menu(scenarios: List[Dict[str, str]]) -> int:
    """Print scenario selection menu and return choice index (-1 for custom)."""
    print()
    print(c(f"  {ARROW_R} Available Scenarios:", WHITE, bold=True))
    print()
    for i, s in enumerate(scenarios, 1):
        print(f"    {c(str(i), CYAN, bold=True)}. {c(s['name'], WHITE)}")
        # Show preview of input
        preview = s["input"][:65] + "..." if len(s["input"]) > 65 else s["input"]
        print(f"       {c(preview, GRAY, dim=True)}")
        print()

    print(f"    {c(str(len(scenarios) + 1), CYAN, bold=True)}. {c('Custom input', YELLOW)}")
    print()

    try:
        choice = input(c(f"  {ARROW_R} Choose (1-{len(scenarios) + 1}): ", CYAN)).strip()
        idx = int(choice) - 1
        if 0 <= idx < len(scenarios):
            return idx
        return -1
    except (ValueError, EOFError):
        return 0


def print_thinking(message: str = "Thinking") -> None:
    """Print a thinking/wait indicator."""
    print(f"  {c(GEAR, CYAN)} {c(message + '...', GRAY, dim=True)}", end="", flush=True)


def print_thinking_done() -> None:
    """Clear thinking state."""
    print(f" {c('done', GREEN)}")


# ====================================================================
# Verbose / Debug Display Functions
# ====================================================================

# These are only shown when --verbose is active. They expose the full
# internal state of every LLM call: system prompts, user messages,
# tool definitions, raw tool call args/results, and response payloads.

SCROLL = "\u2261"  # triple horizontal bar (menu icon)
PENCIL = "\u270e"
INBOX = "\u2709"
WRENCH = "\u2692"
EYE = "\u25ce"


def print_system_prompt(agent: str, prompt: str) -> None:
    """Show the full system prompt sent to an LLM agent."""
    print()
    print(c(TL + HZ * W + TR, GRAY))
    print(
        c(VT, GRAY)
        + c(f"  {SCROLL} SYSTEM PROMPT [{agent}]", CYAN, bold=True).ljust(W + 9)
        + c(VT, GRAY)
    )
    print(c(VT + HZ * W + VT, GRAY))
    for line in prompt.strip().splitlines():
        # Truncate long lines
        display = line[: W - 4] if len(line) > W - 4 else line
        print(c(VT, GRAY) + c(f"  {display}", GRAY, dim=True).ljust(W + 9) + c(VT, GRAY))
    print(c(BL + HZ * W + BR, GRAY))
    print()


def print_user_message(agent: str, message: str) -> None:
    """Show the full user message sent to an LLM agent."""
    print(c(TL + HZ * W + TR, GREEN))
    print(
        c(VT, GREEN)
        + c(f"  {PENCIL} USER MESSAGE [{agent}]", GREEN, bold=True).ljust(W + 9)
        + c(VT, GREEN)
    )
    print(c(VT + HZ * W + VT, GREEN))
    for line in message.strip().splitlines():
        display = line[: W - 4] if len(line) > W - 4 else line
        print(c(VT, GREEN) + c(f"  {display}", WHITE).ljust(W + 9) + c(VT, GREEN))
    print(c(BL + HZ * W + BR, GREEN))
    print()


def print_tool_definitions(tools: List[Dict[str, Any]]) -> None:
    """Show the tool schemas available to the LLM."""
    print(c(TL + HZ * W + TR, MAGENTA))
    print(
        c(VT, MAGENTA)
        + c(f"  {WRENCH} TOOL DEFINITIONS ({len(tools)} tools)", MAGENTA, bold=True).ljust(W + 9)
        + c(VT, MAGENTA)
    )
    print(c(VT + HZ * W + VT, MAGENTA))
    for tool in tools:
        name = tool.get("name", "?")
        desc = tool.get("description", "")
        params = tool.get("parameters", {}).get("properties", {})
        param_names = list(params.keys())
        required = tool.get("parameters", {}).get("required", [])
        print(
            c(VT, MAGENTA)
            + f"  {c(ARROW_R, MAGENTA)} {c(name, WHITE, bold=True)}".ljust(W + 18)
            + c(VT, MAGENTA)
        )
        # Show description (wrap at box width)
        for i in range(0, len(desc), W - 8):
            chunk = desc[i : i + W - 8]
            print(
                c(VT, MAGENTA) + c(f"      {chunk}", GRAY, dim=True).ljust(W + 9) + c(VT, MAGENTA)
            )
        if param_names:
            print(
                c(VT, MAGENTA)
                + c(f"      Params: {', '.join(param_names)}", CYAN).ljust(W + 9)
                + c(VT, MAGENTA)
            )
        if required:
            print(
                c(VT, MAGENTA)
                + c(f"      Required: {', '.join(required)}", YELLOW).ljust(W + 9)
                + c(VT, MAGENTA)
            )
        # Show each param's type and description
        for pname, pinfo in params.items():
            ptype = pinfo.get("type", "?")
            pdesc = pinfo.get("description", "")[:50]
            print(
                c(VT, MAGENTA)
                + c(f"        {pname} ({ptype}): {pdesc}", GRAY, dim=True).ljust(W + 9)
                + c(VT, MAGENTA)
            )
    print(c(BL + HZ * W + BR, MAGENTA))
    print()


def print_raw_tool_call(name: str, args: Dict[str, Any]) -> None:
    """Show the raw arguments of a tool call from the LLM."""
    print(c(f"  {ARROW_R} {c('TOOL CALL:', CYAN, bold=True)} {c(name, WHITE, bold=True)}", ""))
    for key, value in args.items():
        val_str = str(value)
        if len(val_str) > 120:
            val_str = val_str[:120] + "..."
        print(c(f"       {BULLET} {key}: ", GRAY) + c(val_str, WHITE))
    print()


def print_raw_tool_result(name: str, result: Any, truncate: int = 500) -> None:
    """Show the raw result/output returned by a tool handler."""
    import json as _json

    print(c(f"  {ARROW_R} {c('TOOL RESULT:', GREEN, bold=True)} {c(name, WHITE)}", ""))
    if isinstance(result, dict):
        try:
            formatted = _json.dumps(result, indent=2, default=str)
        except Exception:
            formatted = str(result)
    else:
        formatted = str(result)
    lines = formatted.splitlines()
    shown = 0
    for line in lines:
        if shown >= 20:
            remaining = len(lines) - shown
            print(c(f"       ... {remaining} more lines", GRAY, dim=True))
            break
        display = line[:W] if len(line) > W else line
        print(c(f"       {display}", GRAY, dim=True))
        shown += 1
    print()


def print_llm_raw_response(content: str = "", tool_calls: list | None = None) -> None:
    """Show what the LLM actually returned (text + tool calls)."""
    print(c(TL + HZ * W + TR, BLUE))
    print(c(VT, BLUE) + c(f"  {EYE} RAW LLM RESPONSE", BLUE, bold=True).ljust(W + 9) + c(VT, BLUE))
    print(c(VT + HZ * W + VT, BLUE))
    if content:
        for line in content.strip().splitlines()[:15]:
            display = line[: W - 4] if len(line) > W - 4 else line
            print(c(VT, BLUE) + c(f"  {display}", WHITE).ljust(W + 9) + c(VT, BLUE))
    if tool_calls:
        print(c(VT + HZ * W + VT, BLUE))
        print(
            c(VT, BLUE)
            + c(f"  Tool calls: {len(tool_calls)}", CYAN, bold=True).ljust(W + 9)
            + c(VT, BLUE)
        )
        for tc in tool_calls:
            name = tc.get("name", "?")
            args = tc.get("args", {})
            args_str = str(args)
            if len(args_str) > W - 12:
                args_str = args_str[: W - 15] + "..."
            print(
                c(VT, BLUE)
                + c(f"    {ARROW_R} {name}({args_str})", YELLOW).ljust(W + 9)
                + c(VT, BLUE)
            )
    if not content and not tool_calls:
        print(c(VT, BLUE) + c("  (empty response)", GRAY, dim=True).ljust(W + 2) + c(VT, BLUE))
    print(c(BL + HZ * W + BR, BLUE))
    print()


def print_fabric_request_detail(
    step_id: str,
    capability: str,
    params: Dict[str, Any],
    safety_band: str = "AMBER",
    trace_id: str = "",
) -> None:
    """Show the full CapabilityRequest being sent to Fabric."""
    print(c(f"  {ARROW_R} [REQUEST {step_id}]", CYAN, bold=True) + f" {c(capability, WHITE)}")
    print(c(f"       {BULLET} safety_band: {safety_band}", GRAY))
    if trace_id:
        print(c(f"       {BULLET} trace_id: {trace_id[:16]}...", GRAY))
    for key, value in params.items():
        if key.startswith("_"):
            continue  # Skip internal params like _depends_on
        val_str = str(value)
        if len(val_str) > 80:
            val_str = val_str[:80] + "..."
        print(c(f"       {BULLET} {key}: {val_str}", GRAY, dim=True))
    print()


def print_fabric_response_detail(
    step_id: str,
    capability: str,
    success: bool,
    data: Any = None,
    error: str | None = None,
    duration_ms: int = 0,
) -> None:
    """Show the full response from a Fabric execution step."""
    import json as _json

    icon = c(CHECK, GREEN, bold=True) if success else c(CROSS, RED, bold=True)
    status = c("SUCCESS", GREEN, bold=True) if success else c("FAILED", RED, bold=True)
    name_short = capability.rsplit(".", 1)[-1]
    print(
        c(f"  {icon} [RESPONSE {step_id}]", "")
        + f" {c(name_short, WHITE)} {status} "
        + c(f"{duration_ms}ms", GRAY)
    )
    if data:
        if isinstance(data, dict):
            try:
                formatted = _json.dumps(data, indent=2, default=str)
            except Exception:
                formatted = str(data)
        else:
            formatted = str(data)
        lines = formatted.splitlines()
        for i, line in enumerate(lines[:12]):
            display = line[: W - 4] if len(line) > W - 4 else line
            print(c(f"       {display}", GRAY, dim=True))
        if len(lines) > 12:
            print(c(f"       ... {len(lines) - 12} more lines", GRAY, dim=True))
    if error:
        print(c(f"       Error: {error}", RED))
    print()


def print_synthesis_context(user_input: str, step_results: List[Dict[str, Any]]) -> None:
    """Show the context string sent to the Synthesis LLM."""

    print(c(TL + HZ * W + TR, BLUE))
    print(
        c(VT, BLUE)
        + c(f"  {PENCIL} SYNTHESIS INPUT CONTEXT", BLUE, bold=True).ljust(W + 9)
        + c(VT, BLUE)
    )
    print(c(VT + HZ * W + VT, BLUE))
    print(c(VT, BLUE) + c(f"  User: {user_input[:W-8]}", WHITE).ljust(W + 9) + c(VT, BLUE))
    print(c(VT + HZ * W + VT, BLUE))
    for sr in step_results:
        cap = sr.get("capability", sr.get("description", "?"))
        status = c("SUCCESS", GREEN) if sr.get("success") else c("FAILED", RED)
        name_short = cap.rsplit(".", 1)[-1] if "." in cap else cap
        print(
            c(VT, BLUE) + f"  {BULLET} {c(name_short, WHITE)} {status}".ljust(W + 18) + c(VT, BLUE)
        )
        data = sr.get("data", {})
        if data:
            data_str = str(data)
            if len(data_str) > W - 8:
                data_str = data_str[: W - 11] + "..."
            print(
                c(VT, BLUE) + c(f"    Data: {data_str}", GRAY, dim=True).ljust(W + 9) + c(VT, BLUE)
            )
        err = sr.get("error")
        if err:
            print(
                c(VT, BLUE)
                + c(f"    Error: {err[:W-12]}", RED, dim=True).ljust(W + 9)
                + c(VT, BLUE)
            )
    print(c(BL + HZ * W + BR, BLUE))
    print()
