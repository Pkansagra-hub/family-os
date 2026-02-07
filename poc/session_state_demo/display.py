"""
Display Utilities for Session State Demo
=========================================

EPIC: 3 - CLI Interactive Demo
ISSUE: 3.4

Provides colorized output for the demo CLI.
"""

from typing import Any, Dict

# ANSI color codes
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

# Colors
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
WHITE = "\033[97m"
GRAY = "\033[90m"


def colorize(text: str, color: str, bold: bool = False) -> str:
    """Apply color to text."""
    prefix = BOLD if bold else ""
    return f"{prefix}{color}{text}{RESET}"


def print_header(title: str) -> None:
    """Print a header banner."""
    width = 70
    print()
    print(colorize("=" * width, CYAN))
    print(colorize(f"  {title}", CYAN, bold=True))
    print(colorize("=" * width, CYAN))


def print_subheader(title: str) -> None:
    """Print a subheader."""
    print()
    print(colorize(f"--- {title} ---", YELLOW))


def print_user_message(content: str) -> None:
    """Print user message."""
    print()
    print(colorize("YOU:", GREEN, bold=True))
    print(f"  {content}")


def print_assistant_message(content: str) -> None:
    """Print assistant message."""
    print()
    print(colorize("ASSISTANT:", BLUE, bold=True))
    # Word wrap at ~70 chars
    words = content.split()
    line = "  "
    for word in words:
        if len(line) + len(word) > 72:
            print(line)
            line = "  "
        line += word + " "
    if line.strip():
        print(line)


def print_state_change(
    section: str,
    operation: str,
    description: str,
    auto: bool = True,
    success: bool = True,
) -> None:
    """Print a state change notification."""
    # Handle blocked/duplicate writes from gate
    if operation == "BLOCKED":
        tag = "GATE"
        color = YELLOW
        status = colorize("[SKIP]", YELLOW)
        print(colorize(f"  [{tag}]", color) + f" {section}: {description} {status}")
        return

    tag = "AUTO" if auto else "TOOL"
    color = GRAY if auto else MAGENTA
    status = colorize("[OK]", GREEN) if success else colorize("[FAIL]", RED)

    print(colorize(f"  [{tag}]", color) + f" {section}.{operation}: {description} {status}")


def print_tool_call(name: str, args: Dict[str, Any]) -> None:
    """Print a tool call."""
    args_str = ", ".join(f"{k}={v!r}" for k, v in args.items())
    print(colorize("  [TOOL CALL]", MAGENTA, bold=True) + f" {name}({args_str})")


def print_command_result(message: str, success: bool = True) -> None:
    """Print command result."""
    if success:
        print(colorize(f"  [OK] {message}", GREEN))
    else:
        print(colorize(f"  [ERROR] {message}", RED))


def print_info(message: str) -> None:
    """Print info message."""
    print(colorize(f"  [INFO] {message}", CYAN))


def print_warning(message: str) -> None:
    """Print warning message."""
    print(colorize(f"  [WARN] {message}", YELLOW))


def print_error(message: str) -> None:
    """Print error message."""
    print(colorize(f"  [ERROR] {message}", RED))


def print_snapshot(snapshot: Dict[str, Any]) -> None:
    """Print session state snapshot."""
    print()
    print(colorize("Session State Snapshot:", YELLOW, bold=True))
    print(f"  Session ID: {snapshot.get('session_id', '?')}")
    print(f"  Turn Number: {snapshot.get('turn_number', 0)}")
    print(f"  Running: {snapshot.get('is_running', False)}")
    print(f"  Total Size: {snapshot.get('total_size_bytes', 0):,} bytes")
    print(f"  HOT Utilization: {snapshot.get('hot_utilization_pct', 0):.1f}%")
    print(f"  WARM Utilization: {snapshot.get('warm_utilization_pct', 0):.1f}%")
    print(f"  Pressure: {snapshot.get('pressure', 'unknown')}")

    sections = snapshot.get("sections", {})
    if sections:
        print()
        print("  Sections:")
        for name, info in sorted(sections.items()):
            size_bytes = info.get("size_bytes", 0)
            util = info.get("utilization_pct", 0)
            bar_filled = int(util / 5)
            bar = "=" * bar_filled + "-" * (20 - bar_filled)
            print(f"    {name:20} [{bar}] {util:5.1f}% ({size_bytes:,} bytes)")


def print_section_data(section: str, data: Dict[str, Any]) -> None:
    """Print section data."""
    print()
    print(colorize(f"Section: {section}", YELLOW, bold=True))

    if "error" in data:
        print(colorize(f"  Error: {data['error']}", RED))
        return

    for key, value in data.items():
        if isinstance(value, list):
            print(f"  {key}:")
            for item in value:
                if isinstance(item, dict):
                    # Handle history_active format (user/assistant keys)
                    if "user" in item and "assistant" in item:
                        user_text = item.get("user", "")[:50]
                        asst_text = item.get("assistant", "")[:50]
                        print(f"    [user] {user_text}")
                        print(f"    [assistant] {asst_text}")
                    # Handle standard role/content format
                    elif "role" in item or "content" in item:
                        role = item.get("role", "?")
                        content = item.get("content", "")[:60]
                        print(f"    [{role}] {content}")
                    else:
                        print(f"    {item}")
                else:
                    print(f"    - {item}")
        elif isinstance(value, dict):
            print(f"  {key}:")
            for k, v in value.items():
                print(f"    {k}: {v}")
        else:
            print(f"  {key}: {value}")


def print_stats(stats: Any) -> None:
    """Print session statistics."""
    print()
    print(colorize("Session Statistics:", YELLOW, bold=True))
    print(f"  Total Turns: {stats.total_turns}")
    print(f"  User Turns: {stats.user_turns}")
    print(f"  Assistant Turns: {stats.assistant_turns}")
    print(f"  Tool Calls Executed: {stats.tool_calls_executed}")
    print(f"  Tool Calls Blocked: {stats.tool_calls_rejected}")
    print(f"  Bytes Saved by Gate: {stats.bytes_saved_by_gate}")
    print(f"  Total Latency: {stats.total_latency_ms}ms")
    print(f"  Checkpoints: {stats.checkpoints_created}")
    print(f"  Restores: {stats.restores_performed}")


def print_gate_stats(gate_stats: Dict[str, Any]) -> None:
    """Print write gate statistics."""
    print()
    print(colorize("Write Gate Statistics:", YELLOW, bold=True))
    print(f"  Total Checks: {gate_stats.get('total_checks', 0)}")
    print(f"  Accepted: {colorize(str(gate_stats.get('accepted', 0)), GREEN)}")
    print(f"  Rejected: {colorize(str(gate_stats.get('rejected', 0)), YELLOW)}")
    print(f"  Upgraded: {colorize(str(gate_stats.get('upgraded', 0)), CYAN)}")
    print(f"  Bytes Saved: {gate_stats.get('bytes_saved', 0):,}")
    print(f"  Rejection Rate: {gate_stats.get('rejection_rate', '0%')}")


def print_latency_sli(sli: Dict[str, Any]) -> None:
    """Print latency SLI metrics against SLO targets."""
    print()
    print(colorize("Latency SLI/SLO (K1 Architecture Targets):", YELLOW, bold=True))

    if sli.get("turn_count", 0) == 0:
        print("  No turns recorded yet")
        return

    # Actual vs Target comparison
    p50 = sli.get("p50_ms", 0)
    p95 = sli.get("p95_ms", 0)
    p99 = sli.get("p99_ms", 0)
    p50_target = sli.get("slo_p50_target_ms", 1500)
    p95_target = sli.get("slo_p95_target_ms", 3000)
    p99_target = sli.get("slo_p99_target_ms", 5000)

    def status_icon(actual: int, target: int) -> str:
        if actual <= target:
            return colorize("OK", GREEN)
        elif actual <= target * 1.5:
            return colorize("WARN", YELLOW)
        else:
            return colorize("BREACH", RED)

    print(f"  Turns Measured: {sli.get('turn_count', 0)}")
    print()
    print(f"  {'Metric':<10} {'Actual':<10} {'Target':<10} {'Status':<10}")
    print(f"  {'-'*40}")
    print(f"  {'P50':<10} {p50:>7}ms  {p50_target:>7}ms  {status_icon(p50, p50_target)}")
    print(f"  {'P95':<10} {p95:>7}ms  {p95_target:>7}ms  {status_icon(p95, p95_target)}")
    print(f"  {'P99':<10} {p99:>7}ms  {p99_target:>7}ms  {status_icon(p99, p99_target)}")
    print()
    print(
        f"  Min: {sli.get('min_ms', 0)}ms  Max: {sli.get('max_ms', 0)}ms  Avg: {sli.get('avg_ms', 0)}ms"
    )
    print(f"  SLO Violations: {sli.get('slo_violations', 0)}")
    compliance = sli.get("slo_compliance_pct", 100)
    compliance_color = GREEN if compliance >= 95 else YELLOW if compliance >= 90 else RED
    print(f"  SLO Compliance: {colorize(f'{compliance}%', compliance_color)}")


def print_coverage_summary(include_fsm: bool = False) -> None:
    """Print demo coverage vs K1 architecture summary."""
    print()
    print(colorize("Demo Coverage vs K1 Concierge Architecture:", YELLOW, bold=True))
    print()

    # Coverage table - update based on whether FSM is included
    coverage = [
        ("L5: SessionState (Working Memory)", True, "Core of demo"),
        ("  - history_active", True, "Turn recording"),
        ("  - persona", True, "Learned traits"),
        ("  - beliefs_active", True, "Facts + categories"),
        ("  - affective_now", True, "Emotion tool"),
        ("  - telemetry", True, "Turn timing"),
        ("  - Checkpoint/Restore", True, "SQLite persistence"),
        ("Write Gate (Dedup)", True, "Spam prevention"),
        ("Latency SLO/SLI", True, "Performance tracking"),
        ("", None, ""),
        ("L1: Concierge FSM", include_fsm, "FSM loop" if include_fsm else "No state machine"),
        ("  - Intent Classifier", include_fsm, "Heuristic" if include_fsm else "No classification"),
        ("  - Complexity Router", include_fsm, "LOW/MEDIUM" if include_fsm else "No tier routing"),
        ("  - Gap Detection", include_fsm, "Pattern-based" if include_fsm else "No gap detection"),
        (
            "  - CLARIFYING state",
            include_fsm,
            "Asks questions" if include_fsm else "Not implemented",
        ),
        ("L2: Orchestrator", False, "No 3-phase"),
        ("L2.5: Capability Fabric", False, "No dynamic routing"),
        ("L3: Planner", False, "No 4-stage planning"),
        ("L4: Sub-Agents", False, "No agent lifecycle"),
        ("L6: K0 Storage", False, "No cold tier"),
        ("Bridge (K0/K1)", False, "No transport"),
        ("IFL Devices", False, "No adapters"),
    ]

    implemented = sum(1 for _, ok, _ in coverage if ok is True)
    not_implemented = sum(1 for _, ok, _ in coverage if ok is False)
    total = implemented + not_implemented

    for item, status, note in coverage:
        if status is None:
            print()
            continue
        icon = colorize("[x]", GREEN) if status else colorize("[ ]", GRAY)
        note_color = GREEN if status else GRAY
        print(f"  {icon} {item:<30} {colorize(note, note_color)}")

    print()
    coverage_pct = (implemented / total * 100) if total > 0 else 0
    print(
        f"  Estimated Coverage: {colorize(f'{coverage_pct:.0f}%', CYAN)} ({implemented}/{total} components)"
    )
    if include_fsm:
        print(f"  {colorize('This demo shows L1 (Concierge FSM) + L5 (SessionState)', GRAY)}")
        print(f"  {colorize('Next: L2.5 Capability Fabric or L2 Orchestrator', GRAY)}")
    else:
        print(f"  {colorize('This demo shows L5 (SessionState) + LLM integration', GRAY)}")
        print(f"  {colorize('Next: L1 Concierge FSM or L2.5 Capability Fabric', GRAY)}")


# =============================================================================
# FSM DISPLAY FUNCTIONS
# =============================================================================


def print_fsm_state(state: str, highlight: bool = True) -> None:
    """Print current FSM state."""
    state_colors = {
        "LISTENING": CYAN,
        "ACKING": YELLOW,
        "CLARIFYING": MAGENTA,
        "DISPATCHING": BLUE,
        "EXECUTING": GREEN,
        "DELIVERING": CYAN,
    }
    color = state_colors.get(state, WHITE)
    if highlight:
        print(colorize(f"  [{state}]", color, bold=True), end="")
    else:
        print(colorize(f"[{state}]", color), end="")


def print_fsm_transition(from_state: str, to_state: str) -> None:
    """Print FSM state transition."""
    print(colorize(f"    {from_state}", GRAY) + colorize(" -> ", WHITE) + colorize(to_state, CYAN))


def print_classification(classification: "ClassificationResult") -> None:
    """Print classification result."""

    print()
    print(colorize("  Classification:", YELLOW))
    print(f"    Intent: {colorize(classification.primary_intent.value, CYAN)}")
    print(f"    Tier: {colorize(classification.complexity.value.upper(), MAGENTA)}")
    print(f"    Confidence: {classification.confidence:.0%}")

    if classification.secondary_intents:
        secondary = ", ".join(i.value for i in classification.secondary_intents)
        print(f"    Secondary: {secondary}")

    if classification.gaps:
        print(f"    Gaps: {colorize(str(len(classification.gaps)), RED)}")
        for gap in classification.gaps:
            print(f"      - {gap.gap_type}: {gap.description}")

    if classification.detected_entities:
        entities = ", ".join(f"{k}={v}" for k, v in classification.detected_entities.items())
        print(f"    Entities: {entities[:60]}")


def print_clarification_request(question: str) -> None:
    """Print clarification request."""
    print()
    print(colorize("  [CLARIFICATION NEEDED]", MAGENTA, bold=True))
    print(f"  {colorize('?', MAGENTA)} {question}")


def print_routing_decision(tier: str, route: str) -> None:
    """Print routing decision."""
    tier_colors = {"LOW": GREEN, "MEDIUM": YELLOW, "HIGH": RED}
    color = tier_colors.get(tier.upper(), WHITE)
    print(colorize("  [ROUTE]", BLUE) + f" Tier: {colorize(tier.upper(), color)}, Path: {route}")


def print_state_history(history: list) -> None:
    """Print FSM state history."""
    print(colorize("  State Flow: ", GRAY), end="")
    for i, state in enumerate(history):
        if i > 0:
            print(colorize(" -> ", GRAY), end="")
        print(colorize(state, CYAN), end="")
    print()


def print_fsm_stats(stats: Dict[str, Any]) -> None:
    """Print FSM statistics."""
    print()
    print(colorize("Concierge FSM Statistics:", YELLOW, bold=True))
    print(f"  Total Turns: {stats.get('total_turns', 0)}")
    print(f"  Clarifications: {colorize(str(stats.get('clarifications_triggered', 0)), MAGENTA)}")
    print(f"  LOW Tier: {colorize(str(stats.get('low_tier_count', 0)), GREEN)}")
    print(f"  MEDIUM Tier: {colorize(str(stats.get('medium_tier_count', 0)), YELLOW)}")
    print(f"  Avg Classification: {stats.get('avg_classification_ms', 0):.1f}ms")
    print(f"  State Transitions: {stats.get('state_transition_count', 0)}")


def print_help() -> None:
    """Print help message."""
    print()
    print(colorize("Available Commands:", YELLOW, bold=True))
    print(f"  {colorize('/help', CYAN)}       - Show this help message")
    print(f"  {colorize('/state', CYAN)}      - Show session state snapshot")
    print(f"  {colorize('/history', CYAN)}    - Show conversation history")
    print(f"  {colorize('/persona', CYAN)}    - Show learned persona traits")
    print(f"  {colorize('/emotion', CYAN)}    - Show current emotional state")
    print(f"  {colorize('/stats', CYAN)}      - Show session statistics")
    print(f"  {colorize('/gate', CYAN)}       - Show write gate statistics")
    print(f"  {colorize('/checkpoint', CYAN)} - Save checkpoint")
    print(f"  {colorize('/crash', CYAN)}      - Simulate crash (no checkpoint)")
    print(f"  {colorize('/restore', CYAN)}    - Restore from last checkpoint")
    print(f"  {colorize('/quit', CYAN)}       - Exit the demo")
    print()
    print("  Or just type a message to chat!")


def print_welcome(session_id: str) -> None:
    """Print welcome message."""
    print_header("SESSION STATE DEMO - Interactive Mode")
    print()
    print(f"  Session ID: {colorize(session_id, CYAN)}")
    print(f"  Type {colorize('/help', YELLOW)} for commands, {colorize('/quit', YELLOW)} to exit")
    print()
    print(colorize("  This demo shows the K1 SessionState system in action.", GRAY))
    print(colorize("  Watch as your conversation is automatically recorded,", GRAY))
    print(colorize("  and the LLM learns your preferences using tool calls.", GRAY))
    print()
